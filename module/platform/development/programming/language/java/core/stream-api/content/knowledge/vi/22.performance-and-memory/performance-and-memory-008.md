# Đo hiệu năng bằng JMH: warmup, fork và chống loại bỏ mã

Khi so sánh vòng lặp `for` với Java Stream API, một đoạn đo kiểu `System.nanoTime()` chạy một lần rất dễ tạo kết luận sai. Lần đầu một phương thức chạy, JVM có thể đang nạp lớp, xác minh bytecode, cấp phát bộ nhớ và biên dịch Just-in-Time (JIT). Sau vài nghìn lần gọi, bộ tối ưu có thể inlining, khử cấp phát, loại bỏ phép tính không dùng kết quả hoặc thay đổi cách biên dịch theo dữ liệu thực thi. Kết quả của lần chạy đầu **không đại diện** cho giai đoạn hoạt động ổn định.

**JMH (Java Microbenchmark Harness)** là bộ công cụ chuyên dụng trong hệ sinh thái OpenJDK để thiết kế và chạy *microbenchmark* cho Java. Nó giúp điều phối **warmup** (làm nóng), **measurement** (đo), **fork** (tách tiến trình JVM), thời gian đo, số luồng, cơ chế tiêu thụ kết quả, định dạng báo cáo và profiler. JMH **không bảo đảm** mọi benchmark đều đúng: người viết vẫn phải chọn workload đại diện và ngăn các tối ưu hóa làm phép đo trở nên vô nghĩa.

Bài học thuộc chương **Hiệu năng và bộ nhớ** của mô-đun **JAVA_STREAM_API**. Ta sẽ học cách đo pipeline lazy, `filter`, `map`, `reduce` và `collect`; phân biệt chi phí boxing, cấp phát, `Spliterator` và xử lý song song; thực hành thiết kế benchmark công bằng, đọc kết quả có sai số, dùng `Blackhole` hoặc giá trị trả về để chống **dead-code elimination**, và nhận diện khi nào nên chuyển từ microbenchmark sang đo hiệu năng toàn hệ thống. Các ví dụ cơ bản dùng Java 17 trở lên; không cần Stream Gatherers của Java 24 để học JMH.

## 1. Vì sao đo một lần bằng `System.nanoTime()` không đủ?

Ví dụ ngắn sau **không phải benchmark đáng tin**:

```java
import java.util.stream.IntStream;

public class NaiveTiming {
    public static void main(String[] args) {
        long start = System.nanoTime();

        long sum = IntStream.range(0, 1_000_000)
            .filter(n -> n % 2 == 0)
            .mapToLong(n -> n)
            .sum();

        long elapsed = System.nanoTime() - start;

        System.out.println("sum = " + sum);
        System.out.println("elapsed ns = " + elapsed);
    }
}
```

Đoạn mã cho một khoảng thời gian thực tế của **lần chạy cụ thể đó**, nhưng khoảng thời gian ấy có thể bao gồm các yếu tố không thuộc mục tiêu so sánh:

- Nạp lớp Stream/JDK và khởi tạo cấu trúc lần đầu.
- Biên dịch JIT chưa diễn ra hoặc đang diễn ra.
- JVM chọn mức tối ưu khác nhau qua các lần chạy.
- GC, cấp phát, cache CPU, tần số CPU và scheduling của hệ điều hành.
- Kích thước dữ liệu và nhánh điều kiện quá đơn giản so với workload thực tế.
- Sai số của phương pháp đo, nhất là khi thao tác rất ngắn.

Nếu lặp phép đo thủ công trong một vòng `for`, vẫn còn những vấn đề như **đo cả chi phí vòng lặp**, **không cô lập tiến trình JVM** và **để compiler tối ưu bỏ việc**. JMH không thay thế tư duy thí nghiệm, nhưng giúp chuẩn hóa phần lớn cơ chế đo này.

### 1.1. Phải biết chính xác mình đang đo gì

Trước khi viết benchmark, hãy hoàn thành câu:

> “Tôi muốn so sánh **thời gian hoặc throughput của việc tính tổng bình phương số chẵn** trên cùng một mảng `int[]`, giữa vòng lặp, `IntStream` tuần tự và `IntStream` song song.”

Đây là mục tiêu cụ thể. Nó khác hẳn với những câu mơ hồ như “Stream chậm hơn vòng lặp không?” hoặc “Parallel Stream nhanh không?”.

Một kết quả chỉ có ý nghĩa trong phạm vi:

- Dữ liệu đầu vào đã chọn.
- Phiên bản Java, JVM và cấu hình chạy.
- Định nghĩa chính xác của thao tác.
- Benchmark mode và cách báo cáo đơn vị.
- Điều kiện đo (CPU, GC, contention, fork, warmup).

## 2. JMH là gì và không phải là gì?

JMH tổ chức thực thi những phương thức được đánh dấu `@Benchmark` bằng một harness riêng. Harness có thể chạy warmup trước khi ghi số liệu, thực hiện nhiều iteration, tạo nhiều JVM fork và tổng hợp điểm số.

| JMH hỗ trợ | JMH không tự giải quyết |
| --- | --- |
| Khung chạy benchmark có thống kê | Chọn workload có thực sự đại diện cho sản phẩm không |
| Warmup và measurement có cấu hình | Logic thuật toán có đúng không |
| Fork ra các JVM độc lập | Máy có bị tiến trình khác cạnh tranh CPU không |
| Nhiều benchmark mode và đơn vị | Lựa chọn metric có phù hợp mục tiêu kinh doanh không |
| Tiêu thụ giá trị trả về, `Blackhole` | Mọi cách constant folding hoặc tính toán giả có ý nghĩa thực |
| `@State`, `@Param` và `@Setup` | Trạng thái dùng chung có bị thiết kế sai không |
| `-prof gc` và tích hợp profiler | Kết luận tự động về heap retention hoặc rò rỉ bộ nhớ |

**Microbenchmark** thường đo một thao tác hoặc nhóm thao tác nhỏ trong môi trường có kiểm soát. Nó **không tương đương** với đo độ trễ HTTP end-to-end, throughput của hệ thống có database hoặc thời gian xử lý tệp lớn trên đĩa thật.

JMH được duy trì trong dự án OpenJDK; các tài liệu tham khảo chính thức được ghi ở cuối bài. Với dự án Java mới, nên sử dụng một bản JMH tương thích JDK đang dùng và **khóa phiên bản dependency** để bảo đảm chạy lại được phép đo.

## 3. Ba tầng quan trọng: warmup, measurement, fork

```text
JMH Runner
    |
    +-- Fork #1: JVM mới
    |      |
    |      +-- @Setup(Level.Trial)
    |      +-- Warmup iteration 1
    |      +-- Warmup iteration 2
    |      +-- Warmup iteration 3
    |      +-- Measurement iteration 1
    |      +-- Measurement iteration 2
    |      +-- Measurement iteration 3 ...
    |
    +-- Fork #2: JVM mới
           |
           +-- @Setup(Level.Trial)
           +-- Warmup iterations
           +-- Measurement iterations

        => JMH tổng hợp các phép đo và sai số
```

Ba khái niệm không thay thế nhau:

- **Warmup**: cho workload chạy trước giai đoạn ghi điểm để JVM có cơ hội tối ưu và trạng thái chương trình ổn định hơn.
- **Measurement**: các khoảng chạy được JMH dùng để tính điểm benchmark.
- **Fork**: một **tiến trình JVM mới**, với heap/JIT/runtime state độc lập, để giảm lệ thuộc một lần khởi động và một trạng thái tối ưu cụ thể.

**Một fork không phải là một thread.** Bên trong mỗi fork có thể có một hoặc nhiều worker thread của JMH. Một pipeline `parallel()` lại có chiến lược phân chia tác vụ riêng; phải phân biệt **số worker JMH** với **số tác vụ song song bên trong Stream**.

## 4. Warmup: JVM cần thời gian tối ưu, nhưng không có “con số thần kỳ”

JVM HotSpot thường thực thi bytecode với sự kết hợp giữa interpreter và các tầng compiler JIT, đồng thời thu thập thông tin về mức độ “nóng” của phương thức và những dạng dữ liệu đi qua. Trong quá trình chạy, JVM có thể:

- Inline lời gọi phương thức, kể cả nhiều lambda được compiler biểu diễn qua `invokedynamic`.
- Chuyên biệt hóa đường thực thi dựa trên profile.
- Tối ưu phạm vi cấp phát thông qua escape analysis khi điều kiện cho phép.
- Thực hiện constant folding và dead-code elimination.
- Biên dịch lại hoặc deoptimize khi giả định tối ưu không còn phù hợp.

JMH có thể cấu hình warmup bằng annotation:

```java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Warmup;

@Warmup(
    iterations = 3,
    time = 1,
    timeUnit = TimeUnit.SECONDS
)
```

Tức là **ba iteration warmup**, mỗi iteration khoảng một giây. Dữ liệu warmup **không được tính như các iteration đo chính** trong thống kê kết quả thông thường.

### 4.1. Warmup bao nhiêu là đủ?

Không có một cấu hình warmup đúng cho mọi bài toán. Một phép cộng vài nanosecond có yêu cầu khác pipeline tạo nhiều đối tượng, thuật toán có cache, hoặc dịch vụ có giai đoạn khởi tạo dài.

Cách lựa chọn:

1. Bắt đầu với cấu hình rõ ràng, ví dụ `3–5` warmup iterations.
2. Quan sát độ ổn định của các iteration và các JVM fork.
3. Tăng warmup khi thấy quá trình đo vẫn còn xu hướng thay đổi mạnh.
4. Nếu mục tiêu là **cold start**, thiết kế một thí nghiệm riêng; không gọi warmup dài là phép đo cold start.
5. Ghi lại cấu hình để lần sau có thể tái lập.

**Cảnh báo:** Warmup không phải cách sửa một benchmark sai về dead-code elimination, dữ liệu hoặc trạng thái. Nếu phép tính đã bị tối ưu bỏ, chạy warmup lâu hơn không khiến kết quả đáng tin hơn.

### 4.2. Warmup và dữ liệu có trạng thái

Nếu benchmark mutate một collection hoặc làm cạn một iterator qua nhiều invocation, warmup có thể thay đổi chính dữ liệu đầu vào. Measurement lúc đó không còn đo cùng bài toán với những iteration ban đầu.

Chẳng hạn, không nên dùng một `Iterator` được tạo một lần rồi duyệt hết trong benchmark mà không thiết lập lại đúng vòng đời. Với dữ liệu bất biến hoặc mảng chỉ đọc, rủi ro này nhỏ hơn.

## 5. Fork: tách tiến trình JVM để giảm lệ thuộc trạng thái trước đó

Ví dụ:

```java
import org.openjdk.jmh.annotations.Fork;

@Fork(2)
```

JMH sẽ thực hiện benchmark với **hai JVM fork** theo cấu hình. Mỗi fork có quá trình khởi động, warmup, JIT và measurement riêng.

Vì sao cần nhiều fork?

- Các quyết định JIT và profile có thể khác giữa các tiến trình.
- Trạng thái runtime, layout bộ nhớ và nhiễu nền không hoàn toàn giống nhau.
- Một fork duy nhất có thể vô tình là trường hợp bất thường.
- Kết quả nhiều fork giúp quan sát tính lặp lại thay vì suy luận từ một phiên chạy.

### 5.1. Fork bằng 0 có được không?

JMH có chế độ chạy không fork để phục vụ một số tình huống phát triển/debug, nhưng **không nên dùng làm mặc định cho phép so sánh hiệu năng đáng tin**. Khi không fork, benchmark có thể chịu ảnh hưởng từ JVM đang chạy harness và benchmark khác.

Trong các kết quả cần ra quyết định, nên chọn ít nhất một fork phù hợp, thường thử nhiều hơn một fork nếu thời gian và tài nguyên cho phép.

### 5.2. Fork và JVM arguments

Nếu so sánh trên hai cấu hình JVM, cần cố định hoặc ghi lại các tham số như:

```text
-Xms
-Xmx
-XX:+UseG1GC
-XX:ActiveProcessorCount=...
```

Đây là ví dụ tham số có thể ảnh hưởng môi trường, **không phải khuyến nghị bật tất cả**. Chỉ thay đổi những tham số thực sự thuộc câu hỏi thí nghiệm, và khi so sánh hai thuật toán hãy giữ JVM options tương đương.

Đừng dùng một phép đo trên máy phát triển rồi một phép đo trên máy CI bận và gán mọi khác biệt cho `Stream`.

## 6. Measurement: iteration, thời gian chạy và benchmark mode

JMH có nhiều cách ghi điểm:

| Mode | Chỉ số điển hình | Câu hỏi |
| --- | --- | --- |
| `Mode.Throughput` | operations/second | Làm được bao nhiêu lần gọi benchmark trong một đơn vị thời gian? |
| `Mode.AverageTime` | ns/op, µs/op, ms/op | Thời gian trung bình của một invocation là bao nhiêu? |
| `Mode.SampleTime` | Phân bố thời gian từ mẫu | Độ trễ của các phép gọi có hình dạng ra sao? |
| `Mode.SingleShotTime` | Thời gian mỗi lần gọi đơn lẻ | Workload rất dài hoặc trường hợp cần cách đo đặc thù |
| `Mode.All` | Nhiều mode | Cần đo đủ nhưng chi phí chạy lớn hơn |

Với một pipeline tính toán dữ liệu cố định trong mảng, `Mode.AverageTime` thường dễ giải thích:

```java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Measurement(
    iterations = 5,
    time = 1,
    timeUnit = TimeUnit.SECONDS
)
```

Khi report ghi `us/op`, “op” là **một lời gọi phương thức `@Benchmark`**, không mặc nhiên là một phần tử trong Stream.

### 6.1. Phân biệt `ns/op` và `ns/element`

Giả sử **ví dụ minh họa giả định**, không phải kết quả đo thật:

```text
Benchmark: tính tổng trên mảng gồm 10.000 phần tử
AverageTime: 80.000 ns/op
```

Một invocation xử lý **toàn bộ mảng**. Ta có thể tính chỉ số quy đổi:

\[
\text{ns/phần tử} = \frac{80.000\ \text{ns/op}}{10.000\ \text{phần tử/op}}
= 8\ \text{ns/phần tử}.
\]

Nhưng phép chia này chỉ là **quy đổi kế toán**: nó không chứng minh từng phần tử được xử lý độc lập trong 8 ns, cũng không loại được overhead cố định, cache effects hoặc scheduling.

Nếu so sánh một benchmark xử lý `N` phần tử với một benchmark xử lý `1` phần tử nhưng cả hai đều báo `ns/op`, cần chuẩn hóa đơn vị và mục tiêu trước khi kết luận.

## 7. Dead-code elimination: phép tính có thể biến mất

**Dead-code elimination (DCE)** là tối ưu hợp lệ của compiler/JIT: nếu phép tính không có tác dụng quan sát được và kết quả không được sử dụng, compiler có thể bỏ nó.

Benchmark dễ sai:

```java
import org.openjdk.jmh.annotations.Benchmark;
import java.util.Arrays;

@Benchmark
public void wrongIgnoredResult() {
    long total = Arrays.stream(data)
        .filter(v -> (v & 1) == 0)
        .mapToLong(v -> (long) v * v)
        .sum();

    // total không được trả về, không truyền đi, không được dùng.
    // JIT có thể loại một phần hoặc toàn bộ công việc.
}
```

Giả sử `data` là một mảng đã chuẩn bị trong state. Phương thức hợp lệ về cú pháp Java, nhưng **không phải thiết kế đo đáng tin** cho mục tiêu tính tổng.

Một lỗi khác xảy ra riêng với Stream API:

```java
@Benchmark
public void wrongNoTerminalOperation() {
    Arrays.stream(data)
        .filter(v -> (v & 1) == 0)
        .map(v -> v * v);

    // Không có terminal operation: pipeline chưa thực hiện
    // phép lọc và biến đổi toàn bộ dữ liệu.
}
```

Ở đây còn có **tính lazy** của Stream: tạo pipeline không tự duyệt dữ liệu. Benchmark có thể chỉ đo việc dựng pipeline (và thậm chí phần dựng đó cũng có thể bị tối ưu), **không** đo phép lọc và tính bình phương mà người viết tưởng tượng.

### 7.1. Kết quả không quan sát được có thể biến phép đo thành một con số “đẹp”

Nếu benchmark không dùng kết quả, một phương án có thể trông “nhanh vượt trội” chỉ vì JIT loại được nhiều công việc hơn. Không so sánh theo con số đó mà chưa kiểm tra *có thật cùng một công việc được thực hiện không*.

**Quy tắc:** Phép đo phải có một đầu ra hoặc tác dụng quan sát đúng với mục tiêu, và harness phải giữ đầu ra đó sống đủ lâu để JIT không thể xem toàn bộ công việc là thừa.

## 8. Cách chống DCE 1: trả về kết quả từ `@Benchmark`

Đây thường là cách đơn giản và nên ưu tiên:

```java
import org.openjdk.jmh.annotations.Benchmark;

@Benchmark
public long streamFilteredSum() {
    return Arrays.stream(data)
        .filter(v -> (v & 1) == 0)
        .mapToLong(v -> (long) v * v)
        .sum();
}
```

JMH có cơ chế tiêu thụ giá trị trả về của benchmark để tránh việc toàn bộ kết quả bị xem là không có người dùng.

Tại sao trả về `long`?

- Chỉ số tổng hợp cuối là một **giá trị quan sát được**.
- Phù hợp mục tiêu “tính tổng bình phương số chẵn”.
- Không làm nhiễu phép đo bằng việc in log hoặc ghi tệp.
- Không cần tự cập nhật một biến mutable toàn cục.

Trả về kết quả không có nghĩa mọi nhánh tính toán bên trong đều bắt buộc được thực thi y nguyên code nguồn; JIT vẫn được phép tối ưu **giữ nguyên ngữ nghĩa kết quả**. Đó là điều tốt: ta muốn đo mã được JVM tối ưu như khi chạy thực, miễn là công việc và đầu ra đúng.

### 8.1. Không `System.out.println` trong mỗi invocation

Ví dụ không phù hợp:

```java
@Benchmark
public void printResult() {
    System.out.println(Arrays.stream(data).sum());
}
```

Thời gian đo bị chi phối bởi thao tác in, đồng bộ, buffer và thiết bị đầu ra. Phương pháp này không trả lời câu hỏi về hiệu năng tính tổng Stream.

Không dùng việc “có in ra số đúng” làm cách chống DCE trong benchmark; dùng `return` hoặc `Blackhole`.

## 9. Cách chống DCE 2: dùng `Blackhole`

JMH cung cấp `org.openjdk.jmh.infra.Blackhole`, một kênh tiêu thụ giá trị được thiết kế cho benchmark. Harness có thể truyền nó làm tham số của phương thức `@Benchmark`:

```java
import java.util.Arrays;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.infra.Blackhole;

@Benchmark
public void consumeWithBlackhole(Blackhole blackhole) {
    long total = Arrays.stream(data)
        .filter(v -> (v & 1) == 0)
        .mapToLong(v -> (long) v * v)
        .sum();

    blackhole.consume(total);
}
```

Dùng `Blackhole` khi benchmark có một hoặc nhiều giá trị cần tiêu thụ nhưng không phù hợp trả về một đối tượng kết quả duy nhất. Với ví dụ chỉ có `long total`, **trả về `long` đơn giản hơn**.

### 9.1. Không vô tình đo chi phí tiêu thụ cho từng phần tử

Giả sử đang so sánh:

```java
@Benchmark
public void perElementConsume(Blackhole blackhole) {
    for (int value : data) {
        blackhole.consume(value);
    }
}
```

Đây là phép đo có **một lần `consume` cho mỗi phần tử**, không phải benchmark cộng tổng bình phương số chẵn. Nếu phương án thứ hai chỉ `consume` một giá trị tổng cuối, hai bên đã khác lượng công việc đo.

Để so sánh công bằng:

- Giữ **cùng kết quả nghiệp vụ** cho mỗi phương án.
- Tiêu thụ kết quả cuối theo cách tương đương.
- Tránh thêm `Blackhole.consume` trong một nhánh nhiều hơn nhánh khác nếu chi phí đó không phải đối tượng nghiên cứu.

### 9.2. `Blackhole` không thay thế kiểm tra dữ liệu

Một phép tính vô nghĩa nhưng được đưa vào `Blackhole` vẫn có thể là benchmark **không đại diện**. `Blackhole` chỉ giúp giữ kết quả có thể quan sát; nó không chứng minh đầu vào, hành vi, số lượng và tính đúng của thuật toán.

## 10. Constant folding và công việc giả

DCE không phải vấn đề tối ưu duy nhất. **Constant folding** có thể biến một biểu thức bất biến thành một hằng:

```java
@Benchmark
public double suspiciousConstant() {
    return Math.sqrt(144.0);
}
```

Nếu mục tiêu là đo phép căn bậc hai trên dữ liệu runtime, đoạn này không phù hợp: compiler có thể biết ngay kết quả là `12.0` hoặc áp dụng các tối ưu đặc thù.

Một phiên bản dùng dữ liệu do JMH cung cấp:

```java
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;

@State(Scope.Thread)
public class SquareRootBench {
    @Param({"144.0", "275.5", "10000.0"})
    public double input;

    @Benchmark
    public double squareRoot() {
        return Math.sqrt(input);
    }
}
```

`@Param` cho JMH tạo các trường hợp đầu vào và gán giá trị từ ngoài phương thức benchmark. Điều này giúp tránh một số dạng tính toán hằng hoàn toàn ở code nguồn, đồng thời giúp so sánh nhiều trường hợp.

**Nhưng `@Param` không tạo ngẫu nhiên dữ liệu và không bảo đảm loại mọi tối ưu.** Nếu sản phẩm xử lý nhiều loại giá trị, hãy chọn bộ dữ liệu và cách phân bố phản ánh tình huống thực tế.

## 11. `@State`: quản lý dữ liệu đầu vào theo vòng đời benchmark

`@State` xác định đối tượng chứa dữ liệu hoặc trạng thái mà các benchmark method sử dụng.

```java
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;

@State(Scope.Thread)
public class StreamPipelineBenchmark {
    // Mỗi worker benchmark có một instance state riêng.
}
```

Các scope thường gặp:

| Scope | Ý nghĩa | Khi nào phù hợp |
| --- | --- | --- |
| `Scope.Thread` | Mỗi JMH worker thread có một state instance riêng | Đo thuật toán trên dữ liệu độc lập, tránh contention ngoài ý muốn |
| `Scope.Benchmark` | State được chia sẻ giữa các worker trong benchmark tương ứng | Muốn đo tranh chấp, synchronization hoặc trạng thái chia sẻ thực sự |
| `Scope.Group` | State chia sẻ trong một group benchmark theo hợp đồng JMH | Mô phỏng một số tình huống nhiều vai trò/luồng trong group |

Với bài so sánh thuật toán tính tổng trên mảng đọc-only, `Scope.Thread` là điểm bắt đầu hợp lý. Nếu chuyển sang `Scope.Benchmark` cùng một `ArrayList` mutable rồi cho nhiều worker ghi vào, bạn có thể đang đo một lỗi race, không phải hiệu năng Stream.

### 11.1. `@Param` giúp thử nhiều kích thước

```java
@Param({"1000", "100000", "1000000"})
public int size;
```

JMH chạy các tổ hợp benchmark và giá trị `size`. Vì kích thước nguồn ảnh hưởng rất mạnh tới tỷ lệ **chi phí khởi tạo pipeline / chi phí duyệt dữ liệu**, đây là một chiều tham số cần có khi so sánh Stream và vòng lặp.

Thay vì một câu tuyệt đối “vòng lặp nhanh hơn Stream”, ta có thể có kết luận có điều kiện:

> “Ở tập dữ liệu N và cấu hình JDK được đo, phương án A có thời gian trung bình thấp hơn B trong cùng workload.”

## 12. `@Setup`: chuẩn bị dữ liệu ngoài phần việc định đo

Khi muốn so sánh **thuần chi phí xử lý một mảng đã có sẵn**, phải tạo mảng ở thời điểm setup, không tạo lại trong mỗi benchmark invocation.

```java
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Setup;

private int[] data;

@Setup(Level.Trial)
public void setUp() {
    data = new int[size];

    for (int i = 0; i < data.length; i++) {
        data[i] = (i * 31 + 7) & 1023;
    }
}
```

Với `Level.Trial`, dữ liệu được chuẩn bị cho một lượt thử JMH theo lifecycle của state, không được tạo lại trong thân phép đo.

### 12.1. Ba mức setup/teardown

| Level | Khi chạy | Cẩn trọng |
| --- | --- | --- |
| `Level.Trial` | Một lần trong vòng đời trial/state tương ứng | Dữ liệu có thể bị benchmark mutate về sau |
| `Level.Iteration` | Trước mỗi warmup/measurement iteration | Cần thiết nếu phải reset trạng thái giữa iteration |
| `Level.Invocation` | Trước từng invocation | Có thể làm sai mục tiêu đo và phát sinh chi phí/điều phối rất lớn |

**Không dùng `Level.Invocation` một cách máy móc** để reset dữ liệu khi benchmark cực ngắn. Nó có thể làm thay đổi mô hình thực thi và độ chính xác phép đo. Nếu cần khôi phục state giữa từng invocation, hãy cân nhắc thiết kế thí nghiệm khác hoặc chọn workload bất biến để tránh chi phí này.

### 12.2. Nếu muốn đo cả khởi tạo?

Khi sản phẩm thật sự cần đo **tạo nguồn + xây collection + chạy Stream** trong cùng một request, hãy tạo một benchmark **khác** bao gồm chi phí cấp phát đó. Đừng vô tình đưa phần chuẩn bị vào một phương án còn loại khỏi phương án khác.

**Câu hỏi quyết định:** Đang đo *thao tác trên dữ liệu đã có* hay *toàn bộ pipeline gồm chuẩn bị nguồn*? Cần đặt tên hai thí nghiệm khác nhau nếu đó là hai câu hỏi.

## 13. Benchmark JMH hoàn chỉnh: vòng lặp, Stream và parallel Stream

Bài toán: từ một mảng `int[]`, **chỉ chọn số chẵn**, tính **bình phương ở kiểu `long`**, rồi cộng tổng ở kiểu `long`. Ba phương án phải nhận **chính xác cùng dữ liệu** và trả **cùng giá trị**.

Tệp ví dụ: `StreamPipelineBenchmark.java`

```java
package vn.example.bench;

import java.util.Arrays;
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
@Warmup(iterations = 3, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(2)
public class StreamPipelineBenchmark {

    @Param({"1000", "100000", "1000000"})
    public int size;

    private int[] data;

    @Setup(Level.Trial)
    public void setUp() {
        data = new int[size];

        // Cùng dữ liệu xác định cho cả ba phương án.
        for (int i = 0; i < size; i++) {
            data[i] = (i * 31 + 7) & 1023;
        }
    }

    @Benchmark
    public long forLoop() {
        long total = 0L;

        for (int value : data) {
            if ((value & 1) == 0) {
                total += (long) value * value;
            }
        }

        return total;
    }

    @Benchmark
    public long sequentialIntStream() {
        return Arrays.stream(data)
            .filter(value -> (value & 1) == 0)
            .mapToLong(value -> (long) value * value)
            .sum();
    }

    @Benchmark
    public long parallelIntStream() {
        return Arrays.stream(data)
            .parallel()
            .filter(value -> (value & 1) == 0)
            .mapToLong(value -> (long) value * value)
            .sum();
    }
}
```

### Vì sao ba phương án có thể so sánh?

- Cùng mảng `int[]` và cùng phân bố dữ liệu.
- Cùng điều kiện chọn số chẵn: `(value & 1) == 0`.
- Cùng công thức bình phương sau khi chuyển sang `long`, tránh tràn `int` ở phép nhân.
- Cùng kết quả tổng: `long` trả về và được harness tiêu thụ.
- Không in log, không cấp phát lại mảng trong thân benchmark.
- Có cả trường hợp mảng nhỏ, vừa và lớn.
- Cấu hình warmup, measurement và fork được áp dụng nhất quán.

Ví dụ này **không chứng minh** `parallel()` nhanh hơn. Với mảng nhỏ, overhead chia tác vụ có thể lớn hơn lợi ích; với mảng lớn, kết quả còn tùy số core, bandwidth, công việc trên mỗi phần tử và môi trường. Mục tiêu của benchmark là **đo thay vì đoán**.

### 13.1. Một phép tính phải có kết quả đúng trước khi đo

Trước khi tin vào số JMH, hãy xác định kết quả của ba triển khai là tương đương trên dữ liệu nhỏ.

Với `[1, 2, 3, 4, 5]`, phần tử chẵn là `2` và `4`, nên:

\[
2^2 + 4^2 = 4+16 = 20.
\]

Nếu một phương án cộng tất cả giá trị, dùng `map(value -> value * value)` gây tràn `int`, hoặc biến đổi thứ tự phép tính khiến kết quả khác nghiệp vụ, thì **so sánh thời gian không còn công bằng**.

Khi benchmark nghiệp vụ tài chính dùng số thập phân, tính đúng có thể cần `BigDecimal` và quy tắc rounding; khi benchmark tổng trên `double`, sai số và thứ tự phép cộng song song cần được đánh giá bằng dung sai phù hợp, không đòi bình đẳng bit trong mọi trường hợp.

## 14. Tạo dự án JMH riêng và chạy từ command line

JMH thường được dùng qua một **dự án benchmark riêng**, với dependencies và annotation processor của JMH. Một cách thuận tiện là sử dụng Maven archetype do JMH cung cấp.

Ví dụ lệnh tạo dự án (chạy trong môi trường đã cài Maven/JDK thích hợp):

```bash
mvn archetype:generate \
  -DinteractiveMode=false \
  -DarchetypeGroupId=org.openjdk.jmh \
  -DarchetypeArtifactId=jmh-java-benchmark-archetype \
  -DarchetypeVersion=1.37 \
  -DgroupId=vn.example \
  -DartifactId=stream-jmh \
  -Dversion=1.0-SNAPSHOT
```

Đây là **ví dụ cấu hình JMH 1.37**, không phải tuyên bố rằng nó luôn là bản mới nhất. Với dự án thật, kiểm tra bản JMH phù hợp toolchain và chính sách dependency trước khi dùng.

Sau khi tạo dự án, đặt class benchmark ở package phù hợp, ví dụ `src/main/java/vn/example/bench/StreamPipelineBenchmark.java`. Khởi tạo build:

```bash
mvn clean verify
```

Archetype JMH thông dụng tạo một JAR chạy độc lập, thường là `target/benchmarks.jar`. Từ thư mục dự án, chạy:

```bash
java -jar target/benchmarks.jar StreamPipelineBenchmark
```

Nếu file JAR được đặt tên khác theo cấu hình build, phải dùng đúng artifact mà Maven đã tạo; không giả định mọi dự án dùng một đường dẫn giống nhau.

### 14.1. Chạy với tham số JMH qua CLI

Có thể chỉ định rõ số warmup/measurement iterations, fork và số JMH worker threads:

```bash
java -jar target/benchmarks.jar StreamPipelineBenchmark \
  -wi 3 -i 5 -w 1s -r 1s -f 2 -t 1 \
  -bm avgt -tu us
```

Ý nghĩa:

| Tham số | Công dụng |
| --- | --- |
| `-wi 3` | Ba warmup iterations |
| `-i 5` | Năm measurement iterations |
| `-w 1s` | Mỗi warmup iteration một giây |
| `-r 1s` | Mỗi measurement iteration một giây |
| `-f 2` | Hai fork JVM |
| `-t 1` | Một JMH worker thread thực thi benchmark; không quyết định số tác vụ nội bộ của parallel Stream |
| `-bm avgt` | Average Time |
| `-tu us` | Đơn vị microsecond |

Tùy chọn CLI có thể ghi đè annotation tương ứng. Cần ghi lại **lệnh thực tế đã chạy**, không chỉ annotation có trong source.

### 14.2. Đo cấp phát bằng GC profiler

```bash
java -jar target/benchmarks.jar StreamPipelineBenchmark \
  -wi 3 -i 5 -f 2 -t 1 -prof gc
```

Profiler có thể cung cấp các chỉ số như:

- `gc.alloc.rate`: tốc độ cấp phát ước tính.
- `gc.alloc.rate.norm`: số byte cấp phát chuẩn hóa theo một operation.
- `gc.count`: số đợt GC quan sát được.
- `gc.time`: thời gian GC quan sát được.

Các chỉ số khả dụng và độ chính xác còn phụ thuộc JVM, JMH và môi trường. **Bộ nhớ cấp phát (allocation)** không đồng nghĩa **bộ nhớ còn sống (retained heap)** hay rò rỉ bộ nhớ. Benchmark có thể cấp phát nhiều object ngắn hạn nhưng không làm heap sau GC tăng dài hạn.

### 14.3. Xuất báo cáo để so sánh sau này

```bash
java -jar target/benchmarks.jar StreamPipelineBenchmark \
  -wi 3 -i 5 -f 2 -rf json -rff stream-results.json
```

Lưu cùng kết quả:

- Phiên bản JDK và vendor JVM.
- Version JMH và dependency build.
- Số core, CPU, hệ điều hành và tải nền.
- JVM arguments, GC, heap sizing.
- Các tùy chọn `@Param`, warmup, iterations, fork và threads.
- Hash/phiên bản mã benchmark và dữ liệu được dùng.

Không nên chỉ lưu ảnh chụp một dòng kết quả rồi không biết lần sau có đang so sánh cùng workload hay không.

## 15. Đọc output JMH: Score, Error, Units, Params

Một kết quả JMH thường có các cột như:

```text
Benchmark                         (size)     Mode  Cnt    Score    Error  Units
StreamPipelineBenchmark.forLoop     100000    avgt   ...    ...      ...   us/op
StreamPipelineBenchmark.sequentialIntStream ...
StreamPipelineBenchmark.parallelIntStream   ...
```

Ý nghĩa:

- **Benchmark**: phương thức được đo.
- **Params**: bộ tham số của lần chạy, ví dụ kích thước `size`.
- **Mode**: phương pháp tổng hợp, ví dụ `avgt`.
- **Cnt**: số mẫu/iteration được tổng hợp theo dạng báo cáo.
- **Score**: ước lượng giá trị trung tâm của phép đo.
- **Error**: ước lượng sai số thống kê do JMH trình bày; không phải bảo đảm tuyệt đối của độ chính xác ngoài đời.
- **Units**: đơn vị, ví dụ `us/op` hay `ops/s`.

### 15.1. Thấp hơn hay cao hơn là tốt?

| Mode | Khi Score thấp hơn | Khi Score cao hơn |
| --- | --- | --- |
| `AverageTime` | Thường nhanh hơn trên mỗi invocation | Thường chậm hơn |
| `Throughput` | Ít operations/giây hơn | Nhiều operations/giây hơn |

Đừng so sánh trực tiếp `ns/op` với `ops/s` bằng việc nhìn số lớn nhỏ. Chúng đo những chiều khác nhau, với điều kiện benchmark có thể khác.

### 15.2. Sai số chồng lấn và biến động giữa fork

Nếu hai Score gần nhau và Error lớn, rất khó nói chắc phương án nào tốt hơn trên cơ sở đo hiện tại. Hãy nhìn:

1. Dữ liệu từng fork và từng iteration.
2. Mức dao động và xu hướng theo thời gian.
3. Chênh lệch có lặp lại qua lần chạy mới không.
4. Benchmark có bị ảnh hưởng GC, scheduling, CPU throttling hay contention không.
5. Mức chênh lệch có **ý nghĩa thực tiễn** đối với sản phẩm không.

**Không kết luận chỉ từ một Score thấp hơn vài phần trăm** khi benchmark dao động mạnh. Sai số thống kê không bao phủ toàn bộ sai lệch có hệ thống từ workload không đại diện.

## 16. So sánh Stream với vòng lặp: những điều phải giữ công bằng

Một phép so sánh có giá trị phải giữ cùng:

| Thành phần | Ví dụ kiểm tra |
| --- | --- |
| Nguồn | Cùng `int[]`; không so `ArrayList<Integer>` với `int[]` rồi gán mọi khác biệt cho API |
| Số phần tử | Cùng kích thước và phân bố giá trị |
| Công thức | Cùng điều kiện số chẵn, cùng kiểu `long` cho bình phương/tổng |
| Kết quả quan sát | Cả hai trả cùng `long` hoặc tiêu thụ theo cách tương đương |
| Thứ tự | Nếu nghiệp vụ cần thứ tự, cả hai giữ cùng ràng buộc |
| Chuẩn bị dữ liệu | Cả hai dùng dữ liệu đã tạo trong `@Setup` |
| Trạng thái | Không để một bên tái sử dụng cache còn bên kia làm mới cache ngoài ý muốn |
| JVM | Cùng JDK/vendor/JVM flags, heap, GC |
| Môi trường | Cùng phần cứng, tải nền và chính sách CPU |
| Cấu hình JMH | Cùng warmup, measurement, fork, thread và mode |

### 16.1. Boxing là một biến thực nghiệm, không phải chi phí bắt buộc của mọi Stream

So sánh:

```java
// Primitive path: IntStream -> LongStream, tránh boxing trong phần chính.
long primitiveSum = Arrays.stream(data)
    .filter(v -> (v & 1) == 0)
    .mapToLong(v -> (long) v * v)
    .sum();
```

với:

```java
// Object path: boxing, tạo Stream<Integer>.
long boxedSum = Arrays.stream(data)
    .boxed()
    .filter(v -> (v & 1) == 0)
    .mapToLong(v -> (long) v * v)
    .sum();
```

Hai pipeline có thể cho cùng giá trị nhưng khác chi phí cấp phát và tối ưu. Nếu câu hỏi là “`IntStream` so với vòng lặp”, dùng primitive Stream. Nếu câu hỏi là “boxing ảnh hưởng thế nào?”, đây mới là hai phương án cần benchmark riêng.

JIT có thể loại bớt một số cấp phát trong các tình huống nhất định; không được tự suy rằng mỗi phần tử chắc chắn cấp phát một `Integer` mới hoặc toàn bộ boxing đều biến mất. Dùng `-prof gc` và công cụ profiler phù hợp để tìm bằng chứng.

### 16.2. `collect(toList())` là công việc khác `sum()`

```java
var list = Arrays.stream(data)
    .filter(v -> (v & 1) == 0)
    .boxed()
    .toList();
```

Pipeline này tạo **một collection kết quả**. Nó không thể được so với `forLoop()` chỉ trả `long total` rồi kết luận “collect chậm hơn vòng lặp”: hai chương trình **không cùng chức năng**.

Nếu so sánh khả năng xây danh sách, cả nhánh vòng lặp và nhánh Stream đều phải trả một danh sách có cùng nội dung và chính sách thứ tự/mutability phù hợp với mục tiêu.

## 17. Parallel Stream: điều gì phải đo thêm?

`parallel()` có thể giúp khi:

- Nguồn đủ lớn và `Spliterator` chia việc hiệu quả.
- Mỗi phần tử có đủ công việc tính toán độc lập.
- Có nhiều tài nguyên CPU thực sự khả dụng.
- Phép `reduce`/`collect` có cách kết hợp đúng và chi phí hợp lý.
- Không có synchronized/atomic contention lớn hoặc ràng buộc thứ tự quá đắt.

Nhưng `parallel()` có thể **chậm hơn** vì:

- Tạo và lập lịch các tác vụ song song.
- Phân chia nguồn và gộp các kết quả từng phần.
- Tranh chấp memory bandwidth/cache.
- Ràng buộc encounter order (`forEachOrdered`, một số `limit`/`distinct`).
- Các thao tác có trạng thái như `sorted`, cửa sổ hoặc grouping theo khóa nóng.
- Các workload quá nhỏ so với overhead.

### 17.1. `-t 1` không biến `parallelStream()` thành tuần tự

Trong lệnh JMH, `-t 1` xác định **một JMH worker thread gọi benchmark** tại một thời điểm. Bên trong phương thức đó, `parallelStream()` vẫn có thể sử dụng nhiều tác vụ/worker theo runtime.

Vì vậy cần nhìn:

- **Bậc song song nội bộ của Stream**.
- **Số lời gọi benchmark diễn ra đồng thời do JMH**.
- **Số core CPU khả dụng** và tải nền.
- Có workload khác cùng tranh tài nguyên hay không.

Nếu đo throughput của dịch vụ có nhiều request đồng thời, nên có thí nghiệm riêng với nhiều JMH worker và mô hình concurrency đúng. Đừng dùng kết quả một worker để kết luận tất cả tình huống tải nhiều người dùng.

### 17.2. Không dùng shared mutable accumulator để “làm nhanh”

Ví dụ sai:

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> shared = new ArrayList<>();

Arrays.stream(data)
    .parallel()
    .filter(v -> (v & 1) == 0)
    .forEach(shared::add); // Không thread-safe!
```

Đoạn này có thể mất phần tử hoặc hỏng trạng thái. Một benchmark chạy nhanh do **không bảo đảm tính đúng** không phải kết quả đáng tin.

Dùng một terminal operation/collector được thiết kế đúng, ví dụ `toArray`, `sum` hoặc `collect`; nếu cần cấu trúc concurrent, xác định rõ hợp đồng và đo contention.

## 18. `Spliterator` và hình dạng nguồn tác động hiệu năng

Stream API không tự đảm bảo mọi nguồn có thể chia hiệu quả. Một phần đáng kể khả năng xử lý song song dựa vào `Spliterator`:

- `trySplit()` có thể tách phần tử thành các phần độc lập.
- `SIZED` cho phép biết kích thước ước lượng chính xác theo hợp đồng.
- `SUBSIZED` nói rằng các Spliterator con vẫn đáp ứng hợp đồng kích thước.
- `ORDERED` quy định encounter order; bảo toàn thứ tự có thể làm tăng điều phối.
- `CONCURRENT` có ý nghĩa riêng về khả năng nguồn bị sửa đồng thời.

Khi benchmark `List.stream().parallel()` với một nguồn `StreamSupport.stream(customSpliterator, true)`, có thể đang so sánh **đặc điểm Spliterator** chứ không đơn thuần so sánh lambdas.

### 18.1. Benchmark nguồn và pipeline riêng khi cần

Nếu mục tiêu là hiệu năng **chuyển đổi dữ liệu** trên một nguồn đã có sẵn, chuẩn bị nguồn trước và giữ cách tạo Stream phù hợp. Nếu mục tiêu là hiệu năng **đọc nguồn I/O hoặc sinh dữ liệu**, bài toán đã khác, cần benchmark bao gồm chi phí nguồn.

Đừng sắp xếp dữ liệu ở một nhánh rồi không sắp xếp ở nhánh còn lại trừ khi đó chính là biến muốn thử.

## 19. Phân biệt allocation, heap usage và memory leak

Trong Java, ba câu hỏi khác nhau thường bị gộp thành “tốn bộ nhớ”:

| Câu hỏi | Chỉ số/phương pháp phù hợp |
| --- | --- |
| Mỗi invocation cấp phát bao nhiêu byte mới? | JMH `-prof gc`, nhất là `gc.alloc.rate.norm` |
| Sau GC, bao nhiêu object vẫn còn được giữ? | Heap profiling, heap dump, retained size |
| Qua nhiều giờ, bộ nhớ tiến triển thế nào? | Application monitoring, GC logs, long-running tests |

Ví dụ `windowSliding(k)` tạo danh sách cửa sổ và `toList` giữ mọi cửa sổ có thể khiến lượng object còn sống tăng theo `N` và `k`; một custom Gatherer tính tổng trượt có thể giữ ít dữ liệu hơn. Nhưng JMH microbenchmark chỉ chạy trong một phạm vi xác định và **không thể tự chứng minh hoặc bác bỏ memory leak của hệ thống lâu dài**.

### 19.1. Một kết quả cấp phát bằng 0 không có nghĩa “không bao giờ tốn bộ nhớ”

Nếu `gc.alloc.rate.norm` rất thấp hoặc bằng 0 trong phép đo, có thể do tối ưu bỏ cấp phát, escape analysis, hoặc một đặc tính cụ thể của workload. Cần xác nhận benchmark còn thực hiện đúng công việc và kết quả có được tiêu thụ không.

Một class `record`, lambda hoặc Stream object không nhất thiết tương ứng một allocation sống lâu; JVM được phép tối ưu nếu ngữ nghĩa cho phép. Ngược lại, số phần tử lớn, boxing và materialization có thể làm allocation tăng mạnh.

## 20. Benchmark mức thao tác và benchmark mức hệ thống

Không nên dùng JMH để trả lời mọi câu hỏi hiệu năng.

| Câu hỏi | Phương pháp |
| --- | --- |
| `IntStream` có nhanh hơn một vòng lặp trong phép tổng mảng này? | JMH microbenchmark |
| `groupingBy` hay `groupingByConcurrent` nhanh hơn với phân bố khóa này? | JMH workload đại diện, kiểm tra đúng result |
| Công cụ đọc file log và tạo báo cáo mất bao lâu? | Benchmark luồng xử lý thật, đo I/O và GC |
| API xử lý 10.000 request/phút có ổn định không? | Load test/service benchmark |
| P99 latency của giao dịch có bị ảnh hưởng do contention? | Load test, tracing, profiler, metrics |
| Có memory leak sau hai ngày chạy không? | Soak test, heap analysis, GC monitoring |

JMH thường là **một tầng bằng chứng**, hữu ích để thu hẹp nguyên nhân và xác định lựa chọn thuật toán. Quyết định tối ưu hệ thống cần thêm chỉ số ở cấp workload cuối cùng.

### 20.1. Cẩn trọng với benchmark I/O

Nếu benchmark đọc `Files.lines(path)`, kết quả phụ thuộc cache hệ điều hành, filesystem, tốc độ đĩa, dữ liệu tệp và cách đóng stream.

Nếu muốn đo **chi phí xử lý chuỗi đã có trong bộ nhớ**, hãy chuẩn bị `List<String>` trong `@Setup`. Nếu muốn đo **pipeline đọc và xử lý tệp thực**, hãy bao gồm `Files.lines` và `try-with-resources` trong đúng phạm vi công việc được đo. Hai thí nghiệm này không được nhập làm một.

## 21. Thiết kế một thí nghiệm Stream có thể kiểm chứng

Một quy trình thực tế:

### Bước 1 — Phát biểu giả thuyết có thể bác bỏ

Ví dụ: “Trên dữ liệu một triệu `int`, một `IntStream` tuần tự sẽ có độ trễ khác vòng lặp ở mức đủ lớn để đo được, còn parallel Stream phụ thuộc số core và overhead chia việc.”

Đây là câu hỏi để **đo**, chưa phải kết luận.

### Bước 2 — Viết thuật toán đúng trước

Kiểm thử trên đầu vào nhỏ, rỗng, âm, gần giới hạn kiểu số, phân bố chẵn/lẻ khác nhau. Đảm bảo cả ba phương án tính cùng hàm toán học.

### Bước 3 — Kiểm soát dữ liệu và trạng thái

Dùng `@Param` cho `size`, `@Setup(Level.Trial)` tạo dữ liệu, tránh mutation giữa invocation trừ khi đó là mục tiêu đo.

### Bước 4 — Chống DCE và constant folding

Trả về kết quả thật từ `@Benchmark`, hoặc dùng `Blackhole.consume` khi cần. Không tạo pipeline lazy rồi không có terminal operation.

### Bước 5 — Cấu hình warmup, measurement và fork

Chọn cấu hình đo đủ dài để bớt nhiễu, sau đó kiểm tra dao động giữa fork. Ghi lệnh CLI và các lựa chọn JVM.

### Bước 6 — Đọc đúng đơn vị và độ bất định

Phân biệt `us/op` với `ops/s`, xem Error, raw iteration và mức chênh lặp lại. Không suy ra tốc độ mỗi phần tử nếu một invocation gồm nhiều phần tử mà chưa quy đổi.

### Bước 7 — Đo thêm allocation và contention

Dùng `-prof gc`, CPU/heap profiler hoặc công cụ hệ thống phù hợp. Nếu một phương án nhanh hơn nhưng cấp phát hoặc tranh tài nguyên lớn hơn, cần xem mức ưu tiên của hệ thống.

### Bước 8 — Kiểm tra trên workload thật

Một phép đo thuật toán nhanh hơn 10% có thể không làm dịch vụ nhanh hơn 10% nếu phần lớn thời gian nằm ở database hoặc network. Dùng profiling toàn hệ thống trước khi tối ưu quá mức.

## 22. Các kiểu benchmark sai thường gặp

| Sai lầm | Vì sao làm số đo không đáng tin | Cách sửa |
| --- | --- | --- |
| Gọi `System.nanoTime()` một lần | JIT, GC và noise chi phối | Dùng JMH có warmup/iterations/forks |
| Gọi `stream().map(...)` nhưng không có terminal | Pipeline lazy chưa thực hiện phép xử lý | Thêm terminal đúng nghiệp vụ và tiêu thụ kết quả |
| Tính `sum()` nhưng bỏ kết quả | Có nguy cơ dead-code elimination | Trả về `long` hoặc `Blackhole.consume` |
| Benchmark `Math.sqrt(144.0)` để kết luận tốc độ căn bậc hai chung | Constant folding | Dùng dữ liệu runtime có kiểm soát |
| Mỗi invocation tạo bộ dữ liệu mới trong một nhánh | Đo cả allocation mà nhánh kia không có | Dùng `@Setup` hoặc thiết kế benchmark riêng |
| Đo phép tính chỉ vài ns kèm `println` | Đo I/O và synchronization | Không in trong benchmark |
| Dùng một fork rồi kết luận tuyệt đối | Phụ thuộc một trạng thái JIT | Chạy nhiều fork nếu phép đo quan trọng |
| Warmup bằng 0 rồi gọi kết quả “steady state” | JIT chưa ổn định | Warmup phù hợp; cold start đo riêng |
| Cho Stream dùng `int[]` còn vòng lặp dùng `List<Integer>` | Khác nguồn/boxing/cache | Giữ cùng nguồn khi so sánh API |
| Một nhánh dùng `collect(toList())`, nhánh kia tính tổng | Công việc không tương đương | Đo hai chức năng như hai câu hỏi khác |
| Tăng `-t` nhưng không xét `parallelStream` đã có worker nội bộ | Oversubscription/contending CPU | Phân biệt threads JMH và mức song song Stream |
| Dùng `ArrayList` chung trong `parallel().forEach` | Data race, kết quả sai | Dùng terminal/collector an toàn |
| `@State(Scope.Benchmark)` chia sẻ mutable state vô tình | Đo contention ngoài ý muốn | Chọn Scope phù hợp |
| Benchmark sửa source qua nhiều invocation | Workload đổi dần qua thời gian | Dùng input bất biến hoặc reset đúng |
| Không kiểm thử kết quả | Có thể đo thuật toán sai nhanh hơn | Test trước khi benchmark |
| So Score khi units khác nhau | Không cùng đại lượng | Chuẩn hóa mode, đơn vị và workload |
| Chỉ nhìn Score, bỏ Error và fork | Dễ kết luận từ nhiễu | Xem phân bố và chạy lại |
| Gọi allocation thấp là “không có leak” | Nhầm cấp phát với retained heap | Heap profiling/soak test |
| Kết luận JMH nhanh hơn tương đương hệ thống nhanh hơn | Microbenchmark bỏ qua các bottleneck khác | Xác nhận bằng benchmark/load test tổng thể |

## 23. Bài tập thực hành

### Bài 1 — Nhận diện lỗi DCE

Một benchmark có nội dung:

```java
@Benchmark
public void ignored() {
    long total = Arrays.stream(data).asLongStream().sum();
}
```

Giải thích hai rủi ro: bỏ giá trị `total` và việc compiler có thể loại bỏ tính toán. Viết lại phương thức trả `long` và một phiên bản dùng `Blackhole`.

### Bài 2 — Phân biệt lazy pipeline với tính toán đã thực hiện

So sánh:

```java
@Benchmark
public void buildOnly() {
    Arrays.stream(data).filter(x -> x > 0).map(x -> x * x);
}
```

với:

```java
@Benchmark
public long withTerminal() {
    return Arrays.stream(data)
        .filter(x -> x > 0)
        .mapToLong(x -> (long) x * x)
        .sum();
}
```

Bài nào thật sự mô tả việc tính tổng bình phương của các phần tử dương? Vì sao không được gọi đây là hai implementation tương đương?

### Bài 3 — Thiết kế warmup/fork

Đề xuất cấu hình warmup, measurement và fork cho một phép tính có thời gian khoảng microsecond/invocation. Nêu tại sao phải xem tính ổn định kết quả trước khi kết luận, thay vì coi một cấu hình cố định là luôn đúng.

### Bài 4 — Chạy nhiều kích thước dữ liệu

Bổ sung `@Param({"100", "1000", "100000", "1000000"})` vào benchmark. Phân tích dự đoán về tỷ lệ overhead cố định của Stream khi `N` nhỏ, và kiểm tra dự đoán bằng đo thực tế.

### Bài 5 — So sánh primitive Stream và boxed Stream

Viết hai benchmark cùng tính tổng bình phương số chẵn: một dùng `Arrays.stream(data)` trực tiếp, một dùng `boxed()`. Mỗi benchmark trả cùng `long`. Dùng `-prof gc` để xem có sự khác biệt trong allocation không.

### Bài 6 — Thay `sum()` bằng `collect()` có công bằng không?

Một người so sánh `IntStream.sum()` với `Stream<Integer>.collect(toList())` rồi kết luận rằng collect kém hiệu quả. Chỉ ra sự khác biệt về **đầu ra cần tạo** và thiết kế một phép so sánh công bằng hơn.

### Bài 7 — Đọc kết quả JMH giả định

Hai phép đo **giả định** có điểm:

```text
A: 100 ± 15 us/op
B: 105 ± 16 us/op
```

Có thể kết luận B chậm hơn A chắc chắn không? Cần xem thêm những thông tin nào (fork, iteration, workload, environment) trước khi đề xuất thay đổi production?

### Bài 8 — Đo `parallel()` trên dữ liệu nhỏ và lớn

Với mảng `int[]` gồm 1.000 và 1.000.000 phần tử, chạy benchmark sequential và parallel. Trình bày lý do vì sao kết quả có thể đảo chiều theo kích thước; giải thích vai trò Spliterator, điều phối task và băng thông bộ nhớ.

### Bài 9 — Mục tiêu là throughput nhiều request

Nếu hệ thống có 32 request đồng thời, liệu `-t 1` có phản ánh đúng điều kiện tải không? Đề xuất benchmark bổ sung với nhiều JMH workers, nói rõ dữ liệu có được chia sẻ hay không và cân nhắc oversubscription từ parallel Stream.

### Bài 10 — Phân biệt allocation và memory leak

Một báo cáo có `gc.alloc.rate.norm` cao nhưng heap sau GC ổn định. Có đủ chứng cứ kết luận ứng dụng rò rỉ bộ nhớ không? Cần thêm loại thí nghiệm hoặc số liệu nào?

### Bài 11 — Giữ kết quả kiểm chứng được

Tạo một hàm Java 17 thuần có đầu vào `int[]`, trả tổng bình phương số chẵn. Viết test đơn giản trên `[1,2,3,4,5]` mong `20L`. Dùng chính hàm đó hoặc cùng quy tắc trong JMH để kiểm chứng hai phiên bản Stream/loop trả cùng kết quả.

### Bài 12 — Thiết kế benchmark cho `groupingBy`

Cho một triệu giao dịch và các khóa vùng phân bố không đều. Đề xuất benchmark so sánh `groupingBy` với `groupingByConcurrent` và cả hai trong pipeline parallel. Cần kiểm tra điều gì về tính đúng, số khóa nóng, thứ tự, chi phí merge và contention?

### Bài 13 — Benchmark đọc tệp

Một benchmark tạo `Files.lines(path)` và đọc tệp đã nằm trong cache OS. Liệu kết quả này có đại diện cho một máy chủ đọc tệp lạnh từ đĩa thật không? Hãy tách các câu hỏi: xử lý chuỗi trong bộ nhớ, đọc từ page cache, đọc qua thiết bị thực.

## 24. Câu hỏi tự kiểm tra kiến thức

- Tại sao phép đo một lần bằng `System.nanoTime()` khó đáng tin cho JIT?
- Khác nhau giữa warmup, measurement iteration và fork JVM là gì?
- Fork có giống tăng số thread `-t` không?
- Tại sao warmup không tự sửa được một benchmark bị DCE?
- `@Benchmark` cần trả về kết quả khi nào?
- `Blackhole.consume` bảo vệ điều gì và có hạn chế nào?
- Vì sao việc gọi `stream().map(...)` mà không có terminal không đo phép biến đổi toàn bộ nguồn?
- Constant folding có thể làm sai ý định của phép đo bằng cách nào?
- Vai trò của `@State`, `@Param` và `@Setup(Level.Trial)` là gì?
- Khi nào dùng `Scope.Thread`, khi nào dùng `Scope.Benchmark`?
- Trong JMH, một `op` là một phần tử Stream hay một invocation?
- `avgt` và `thrpt` khác nhau như thế nào? Score tốt hơn theo hướng nào?
- Vì sao phải xét `Error` và kết quả nhiều fork?
- Cách so sánh `IntStream` với vòng lặp để tránh khác biệt nguồn/boxing là gì?
- `-prof gc` giúp nhìn allocation như thế nào? Vì sao không đủ kết luận leak?
- Vì sao `parallelStream()` có thể chậm hơn tuần tự?
- Việc thêm `-t 1` có làm code `parallel()` chạy tuần tự không?
- Khi nào một benchmark Stream nhỏ không đủ bằng chứng để tối ưu toàn bộ dịch vụ?
- Tại sao phải kiểm thử tính đúng trước khi đo hiệu năng?

## 25. Tài liệu tham khảo

- [OpenJDK — JMH](https://github.com/openjdk/jmh): mã nguồn, hướng dẫn sử dụng harness, Maven archetype và các tùy chọn chạy.
- [JMH Samples](https://github.com/openjdk/jmh/tree/master/jmh-samples/src/main/java/org/openjdk/jmh/samples): ví dụ chính thức về dead-code elimination, Blackhole, state, forks, warmup, benchmark modes và measurement.
- [JMH `JMHSample_08_DeadCode`](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java): minh họa giá trị không dùng có thể bị JIT loại bỏ.
- [JMH `JMHSample_09_Blackholes`](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_09_Blackholes.java): minh họa kết quả trả về và Blackhole.
- [JMH `JMHSample_10_ConstantFold`](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java): minh họa constant folding.
- [Java SE 17 — `Stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): tính lazy, đặc tính pipeline, side effect và các terminal operation.
- [Java SE 17 — `IntStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): xử lý primitive và các terminal operation `sum`, `average`, `summaryStatistics`.
- [Java SE 17 — `Spliterator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html): cơ chế chia nguồn và characteristic phục vụ parallel Stream.

**Ghi nhớ:** Một phép đo JMH tốt phải **đo đúng công việc**, **giữ kết quả quan sát được**, **cho JVM warmup**, **lặp lại trên nhiều iteration và fork**, và **giữ cùng điều kiện so sánh**. Với Java Stream API, đặc biệt phải nhớ **intermediate operation là lazy**, `map`/`filter` không tự chạy khi thiếu terminal, boxing/`collect` có thể đổi workload, và `parallel()` có overhead. Trả kết quả hoặc dùng `Blackhole` để chống DCE, đọc đúng `Score/Error/Units`, kiểm tra allocation/GC khi cần và chỉ dùng microbenchmark như một nguồn bằng chứng cho quyết định hiệu năng.
