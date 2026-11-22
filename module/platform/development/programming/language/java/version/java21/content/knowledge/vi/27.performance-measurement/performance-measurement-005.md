# JMH cho microbenchmark API và phép biến đổi dữ liệu

JMH (Java Microbenchmark Harness) là bộ công cụ của OpenJDK dùng để xây dựng, chạy và phân tích benchmark cho code chạy trên JVM. JMH phù hợp khi cần so sánh chi phí của một API, thuật toán hoặc phép biến đổi dữ liệu ở phạm vi nhỏ, chẳng hạn `String.indexOf()` với regex đã biên dịch, vòng lặp với Stream API hoặc hai cách tạo cấu trúc dữ liệu.

Microbenchmark rất dễ cho kết quả sai nếu tự đo bằng một vòng `System.nanoTime()` hoặc lặp một lời gọi method trong vòng `for` rồi lấy trung bình. JIT compiler, dead-code elimination, constant folding, warm-up, GC và cách JVM phân bổ thread đều có thể làm sai lệch phép đo. JMH xử lý nhiều vấn đề này bằng harness được sinh từ annotation processor, warm-up, measurement iteration và fork JVM riêng. Dù vậy, JMH không tự biến một benchmark thiết kế sai thành kết quả đáng tin cậy: dữ liệu, trạng thái và câu hỏi đo vẫn phải được thiết kế đúng.

## 1. Khi nào nên dùng JMH?

JMH phù hợp khi câu hỏi cần trả lời tập trung vào code chạy trên JVM:

- Một API hoặc thao tác thư viện có chi phí bao nhiêu trong điều kiện xác định?
- Hai cách thực hiện cùng một phép biến đổi dữ liệu có throughput hoặc latency khác nhau không?
- Kích thước đầu vào ảnh hưởng thế nào đến chi phí của thuật toán?
- Một cách triển khai tạo bao nhiêu allocation hoặc gây áp lực GC?
- Thay đổi code có cải thiện hiệu năng trong cùng môi trường JVM hay không?

Ví dụ những câu hỏi có thể benchmark:

| Câu hỏi | Đối tượng đo |
|---|---|
| Tìm chuỗi literal bằng `indexOf()` hay regex đã biên dịch | API lookup trên chuỗi trong bộ nhớ |
| Vòng lặp hay Stream API biến đổi một mảng số | Phép biến đổi cùng dữ liệu và cùng kết quả |
| `HashMap` hay `TreeMap` cho thao tác tra cứu | Một thao tác map với phân bố key xác định |
| Tạo object bằng hai factory method | Chi phí tạo object và allocation |
| Một formatter có tái sử dụng formatter hay tạo mới | Chi phí format với cùng dữ liệu đầu vào |

JMH không thay thế benchmark tải cho toàn bộ hệ thống. Nếu câu hỏi liên quan đến HTTP end-to-end, database, message broker, network latency, connection pool hoặc hành vi dưới tải của nhiều service, cần một bài load test hoặc benchmark hệ thống có kiểm soát. Có thể dùng JMH cho phần code CPU cục bộ nằm bên trong hệ thống đó.

## 2. Tạo project JMH đúng cách

JMH không phải thư viện test thông thường. Chỉ thêm `jmh-core` vào project rồi gọi method benchmark trực tiếp sẽ bỏ qua annotation processor và generated harness code mà JMH cần để chạy đúng.

Hướng dẫn của dự án OpenJDK khuyến nghị tạo một Maven project độc lập bằng JMH archetype. Project benchmark có thể phụ thuộc vào JAR/module của ứng dụng cần đo, giúp tách cấu hình benchmark khỏi ứng dụng chính.

Ví dụ tạo project Java benchmark với JMH 1.37:

```bash
mvn archetype:generate \
  -DinteractiveMode=false \
  -DarchetypeGroupId=org.openjdk.jmh \
  -DarchetypeArtifactId=jmh-java-benchmark-archetype \
  -DarchetypeVersion=1.37 \
  -DgroupId=org.example \
  -DartifactId=java21-benchmarks \
  -Dversion=1.0
```

`1.37` là phiên bản ví dụ được pin trong lệnh để build có thể tái lập. Khi tạo project mới hoặc nâng cấp harness, hãy kiểm tra phiên bản được dự án JMH và Maven Central công bố tại thời điểm thực hiện; không giả định số phiên bản trong tài liệu luôn là bản mới nhất.

Trong project được tạo, giữ cấu hình annotation processing và cấu hình đóng gói executable JAR do archetype cung cấp. Đặt Java release là 21 nếu project cần biên dịch source theo Java 21:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Build và chạy benchmark:

```bash
cd java21-benchmarks
mvn clean verify
java -jar target/benchmarks.jar
```

JAR được tạo chứa benchmark và hạ tầng JMH cần thiết. Không chạy benchmark bằng cách gọi method trực tiếp từ JUnit hoặc bằng nút Run một method trong IDE rồi coi thời gian hiển thị là kết quả JMH. Có thể dùng IDE để sửa code và build project, nhưng nên chạy benchmark qua executable JAR trong môi trường kiểm soát.

## 3. Cấu trúc tối thiểu của một benchmark

Một benchmark JMH thường có các thành phần:

| Thành phần | Mục đích |
|---|---|
| `@Benchmark` | Đánh dấu method mà JMH cần đo |
| `@State` | Xác định vòng đời và phạm vi chia sẻ dữ liệu benchmark |
| `@Setup` | Tạo dữ liệu hoặc chuẩn bị fixture trước phép đo |
| `@Param` | Chạy benchmark với nhiều bộ tham số đầu vào |
| `@BenchmarkMode` | Chọn cách biểu diễn kết quả, ví dụ latency hoặc throughput |
| `@Warmup` | Cho JVM và JIT có thời gian ổn định trước measurement |
| `@Measurement` | Cấu hình các iteration dùng để lấy kết quả |
| `@Fork` | Chạy benchmark trong JVM process mới để giảm ảnh hưởng profile giữa các lần đo |

Ví dụ một benchmark nhỏ:

```java
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Warmup;

import java.util.concurrent.TimeUnit;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(3)
public class SimpleBenchmark {
    private final String text = "Java 21 microbenchmark";

    @Benchmark
    public int findWord() {
        return text.indexOf("benchmark");
    }
}
```

JMH gọi `findWord()` nhiều lần trong các iteration đã cấu hình. Method trả về kết quả để harness tiêu thụ, giúp tránh trường hợp kết quả bị loại bỏ hoàn toàn như một phép tính không có tác dụng quan sát được.

## 4. Benchmark API: String.indexOf() và regex đã biên dịch

Khi so sánh hai API, cần đảm bảo chúng trả lời cùng một câu hỏi và nhận cùng dữ liệu. Ví dụ sau so sánh việc tìm chuỗi literal `needle` trong một chuỗi lớn bằng `String.indexOf()` và bằng `Pattern` đã biên dịch.

```java
package org.example;

import org.openjdk.jmh.annotations.*;

import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(3)
public class LookupBenchmark {

    @Param({"128", "4096", "65536"})
    public int prefixLength;

    private String text;
    private Pattern pattern;

    @Setup(Level.Trial)
    public void setup() {
        text = "x".repeat(prefixLength) + "needle";
        pattern = Pattern.compile(Pattern.quote("needle"));
    }

    @Benchmark
    public int indexOf() {
        return text.indexOf("needle");
    }

    @Benchmark
    public int precompiledPattern() {
        Matcher matcher = pattern.matcher(text);
        return matcher.find() ? matcher.start() : -1;
    }

    @Benchmark
    public int compileAndSearch() {
        Matcher matcher = Pattern.compile(Pattern.quote("needle"))
                .matcher(text);
        return matcher.find() ? matcher.start() : -1;
    }
}
```

Ba method `indexOf()` và `precompiledPattern()` đều tìm vị trí xuất hiện đầu tiên của cùng chuỗi literal. `Pattern` được compile trong `@Setup(Level.Trial)`, nằm ngoài vùng đo của method `precompiledPattern()`. Method `compileAndSearch()` cố ý tính cả chi phí compile pattern để trả lời một câu hỏi khác: nếu mỗi lần gọi đều tạo regex mới thì tổng chi phí là bao nhiêu?

Không nên gộp hai câu hỏi này vào một kết luận duy nhất. Nếu ứng dụng thực tế cache `Pattern`, hãy so sánh `indexOf()` với pattern đã biên dịch. Nếu ứng dụng thực sự compile regex ở mỗi request, benchmark compile-and-search có thể phản ánh đúng hơn đường chạy đó.

`@Param` làm JMH chạy với nhiều độ dài prefix. Dữ liệu được tạo trước phép đo, không phải tạo lại trong mỗi lần gọi benchmark. Nếu muốn kiểm tra trường hợp không tìm thấy hoặc match ở đầu chuỗi, hãy tạo bộ input riêng cho những tình huống đó thay vì trộn ngẫu nhiên vào một phép đo không kiểm soát.

## 5. Benchmark phép biến đổi dữ liệu: loop và Stream API

Khi so sánh hai cách biến đổi collection hoặc array, phải bảo đảm chúng thực hiện cùng một công việc, tạo kết quả có cùng ý nghĩa và sử dụng cùng bộ input. Ví dụ sau biến đổi từng số nguyên theo công thức `value * 31 + 7` rồi tạo một mảng kết quả mới.

```java
package org.example;

import org.openjdk.jmh.annotations.*;

import java.util.Arrays;
import java.util.concurrent.TimeUnit;
import java.util.stream.IntStream;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(3)
public class TransformBenchmark {

    @Param({"128", "4096", "65536"})
    public int size;

    private int[] input;

    @Setup(Level.Trial)
    public void setup() {
        input = IntStream.range(0, size).toArray();
    }

    @Benchmark
    public int[] transformWithLoop() {
        int[] output = new int[input.length];

        for (int i = 0; i < input.length; i++) {
            output[i] = transform(input[i]);
        }

        return output;
    }

    @Benchmark
    public int[] transformWithStream() {
        return Arrays.stream(input)
                .map(TransformBenchmark::transform)
                .toArray();
    }

    private static int transform(int value) {
        return value * 31 + 7;
    }
}
```

Cả hai method đều đọc cùng `input`, tạo một mảng mới có cùng số phần tử và áp dụng cùng phép biến đổi. Kết quả được trả về để JMH tiêu thụ; không cần thêm một biến static chỉ để giữ kết quả. Việc tạo mảng đầu ra nằm trong vùng đo vì đó là một phần của phép biến đổi mà benchmark đang so sánh.

Nếu câu hỏi chỉ là chi phí tính toán mà không tính allocation đầu ra, hãy thiết kế một benchmark khác trả về checksum hoặc tổng kết quả. Không so sánh một method chỉ tính tổng với một method tạo mảng rồi kết luận method nào biến đổi dữ liệu nhanh hơn: chúng không thực hiện cùng công việc.

## 6. State và vòng đời dữ liệu benchmark

`@State` xác định dữ liệu được chia sẻ giữa các benchmark thread như thế nào:

| Scope | Cách chia sẻ | Trường hợp dùng |
|---|---|---|
| `Scope.Thread` | Mỗi benchmark thread có một instance state riêng | Input mutable hoặc fixture riêng cho từng thread |
| `Scope.Benchmark` | Mọi benchmark thread chia sẻ một instance | Đo cấu trúc dữ liệu hoặc service dùng chung; cần xử lý cạnh tranh truy cập đúng cách |
| `Scope.Group` | Các thread trong cùng group chia sẻ state | Benchmark phối hợp nhiều loại thao tác trong một nhóm |

Các mức setup thường dùng:

- `Level.Trial`: chạy một lần cho mỗi trial/fork; phù hợp tạo input tương đối ổn định.
- `Level.Iteration`: chạy trước mỗi warm-up hoặc measurement iteration.
- `Level.Invocation`: chạy trước mỗi invocation; chỉ dùng khi thật sự cần reset state cho từng lần gọi vì setup ở mức này có thể ảnh hưởng đáng kể đến cache và GC dù thời gian setup không được tính trực tiếp vào method benchmark.

Không tạo dữ liệu lớn hoặc compile regex trong benchmark method nếu câu hỏi không bao gồm chi phí đó. Ngược lại, không chuyển một bước chuẩn bị ra `@Setup` nếu trong ứng dụng thực tế bước đó được thực hiện ở mỗi lần gọi và chi phí của nó là một phần cần đo. Phạm vi setup phải phản ánh chính xác câu hỏi benchmark.

## 7. Benchmark mode và cách đọc kết quả

JMH hỗ trợ nhiều mode, mỗi mode trả lời một câu hỏi khác nhau:

| Mode | Ý nghĩa | Đơn vị thường gặp |
|---|---|---|
| `Mode.AverageTime` | Thời gian trung bình cho một operation | ns/op, us/op, ms/op |
| `Mode.Throughput` | Số operation hoàn thành trong một đơn vị thời gian | ops/s, ops/ms |
| `Mode.SampleTime` | Lấy mẫu thời gian operation để quan sát phân bố | ns/op, us/op |
| `Mode.SingleShotTime` | Đo thời gian cho một lần thực thi trong mỗi iteration | ns/op, ms/op |
| `Mode.All` | Chạy tất cả mode | Nhiều loại kết quả |

Ví dụ chạy một benchmark với cấu hình rõ ràng:

```bash
java -jar target/benchmarks.jar '.*LookupBenchmark.*' \
  -f 3 \
  -wi 5 \
  -i 5 \
  -bm avgt \
  -tu ns
```

Trong output, chú ý các cột `Mode`, `Cnt`, `Score`, `Error` và `Units`. `Score` là kết quả đo theo mode; `Error` thể hiện sai số được JMH báo cáo cho các iteration/fork. Đây không phải bảo đảm rằng mọi lần chạy tương lai sẽ nằm trong khoảng đó, và không nên dùng một chênh lệch rất nhỏ làm kết luận nếu độ biến thiên giữa các lần chạy lớn.

Ví dụ định dạng output minh họa (số liệu không phải kết quả benchmark thực tế):

```text
Benchmark                 Mode  Cnt   Score   Error  Units
LookupBenchmark.indexOf   avgt   15   12.4    0.3    ns/op
```

Nếu muốn so sánh khả năng xử lý nhiều operation đồng thời, dùng `Throughput` và cấu hình số benchmark thread phù hợp. Nếu quan tâm tail behavior của operation, `SampleTime` cung cấp mẫu phân bố; cần hiểu cách lấy mẫu và không coi nó là latency end-to-end của service.

## 8. Warm-up, measurement và fork

JVM là runtime có JIT compiler và nhiều tầng tối ưu hóa. Kết quả ở những invocation đầu có thể khác xa trạng thái ổn định. Một cấu hình cơ bản thường có warm-up, measurement và nhiều fork:

```java
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(3)
```

- Warm-up cho code được thực thi đủ để JVM nạp class, profiling và tối ưu các đường chạy nóng.
- Measurement thu kết quả sau giai đoạn warm-up.
- Fork chạy benchmark trong JVM process riêng, giảm ảnh hưởng profile/JIT hoặc trạng thái còn sót giữa các lần chạy.

Các con số trên chỉ là điểm bắt đầu. Benchmark có workload phức tạp, input lớn hoặc JIT compilation lâu có thể cần warm-up và measurement dài hơn. Không giảm iteration chỉ để lấy kết quả nhanh nếu mục tiêu là so sánh những chênh lệch nhỏ.

Không chạy nhiều benchmark nặng cùng lúc trên cùng máy nếu muốn so sánh hiệu năng CPU. Background load, thermal throttling, CPU frequency scaling và giới hạn CPU của container đều có thể làm kết quả dao động.

## 9. Tránh dead-code elimination và constant folding

### Dead-code elimination

Nếu benchmark tính kết quả nhưng không trả về, không ghi vào state và không đưa kết quả cho `Blackhole`, JIT có thể loại bỏ phần tính toán vì kết quả không ảnh hưởng đến hành vi quan sát được.

Không nên viết:

```java
@Benchmark
public void wrong() {
    int result = expensiveCalculation();
}
```

Nếu kết quả có thể trả về, hãy trả về trực tiếp:

```java
@Benchmark
public int better() {
    return expensiveCalculation();
}
```

Nếu benchmark cần tiêu thụ nhiều kết quả hoặc không thể trả về trực tiếp, dùng `org.openjdk.jmh.infra.Blackhole`:

```java
@Benchmark
public void consumeResults(Blackhole blackhole) {
    blackhole.consume(calculateFirst());
    blackhole.consume(calculateSecond());
}
```

Không tự tạo một `Blackhole` bằng constructor hoặc thay thế cơ chế tiêu thụ kết quả của JMH bằng biến static. Dùng đối tượng mà JMH truyền vào benchmark method.

### Constant folding

Nếu đầu vào là hằng số có thể biết ngay lúc biên dịch, JIT có thể tính trước kết quả hoặc đơn giản hóa phép toán. Khi muốn đo phụ thuộc vào dữ liệu, dùng `@State`, `@Param` và input được chuẩn bị trong `@Setup`.

Ví dụ, benchmark `return 100 * 200;` không đại diện cho một phép nhân runtime với dữ liệu thực. Hãy đọc operand từ state hoặc parameter để giữ câu hỏi đo sát với ứng dụng.

### Tránh benchmark một vòng lặp tự chế

Không nên dùng một vòng `for` lặp hàng triệu lần quanh một lời gọi nhỏ rồi chia tổng thời gian cho số lần lặp. Cách đó dễ bị loop optimization, hoisting, unrolling và sai số timer chi phối. Hãy để JMH điều phối invocation. Vòng lặp vẫn hợp lệ khi chính vòng lặp là thuật toán cần đo, ví dụ biến đổi tất cả phần tử của một mảng như `transformWithLoop()` ở trên.

## 10. Đo allocation và áp lực GC

Một API có thể nhanh hơn về thời gian nhưng tạo nhiều object hơn. Với phép biến đổi dữ liệu, allocation thường ảnh hưởng đến throughput và GC khi chạy lâu hoặc chạy đồng thời.

JMH có GC profiler:

```bash
java -jar target/benchmarks.jar '.*TransformBenchmark.*' -prof gc
```

Các chỉ số thường được quan sát gồm:

- `gc.alloc.rate`: tốc độ cấp phát bộ nhớ.
- `gc.alloc.rate.norm`: lượng byte cấp phát chuẩn hóa theo operation.
- `gc.count`: số lần GC trong quá trình đo.
- `gc.time`: tổng thời gian GC được profiler ghi nhận.

GC profiler giúp nhận ra một phương án tạo allocation nhiều hơn, nhưng không thay thế profiling toàn ứng dụng. Kết quả phụ thuộc heap size, collector, JDK build và workload. Nếu muốn so sánh GC, hãy giữ cùng collector, heap flags và môi trường giữa các phương án.

## 11. Chạy benchmark và lưu kết quả có thể tái lập

Chạy một nhóm benchmark cụ thể:

```bash
java -jar target/benchmarks.jar '.*TransformBenchmark.*'
```

Chạy với nhiều thread nếu câu hỏi là throughput khi có cạnh tranh:

```bash
java -jar target/benchmarks.jar '.*TransformBenchmark.*' -t 4 -bm thrpt
```

Đo allocation:

```bash
java -jar target/benchmarks.jar '.*TransformBenchmark.*' -prof gc
```

Xuất kết quả JSON để phân tích hoặc lưu cùng báo cáo:

```bash
java -jar target/benchmarks.jar '.*LookupBenchmark.*' \
  -rf json \
  -rff results.json
```

Khi lưu kết quả, ghi kèm metadata:

- Phiên bản JDK, vendor và build number (`java -version`).
- Phiên bản JMH và commit của benchmark source.
- CPU model, số core khả dụng, RAM và hệ điều hành.
- JVM flags, heap size, collector và giới hạn CPU/RAM của container.
- Input size, phân bố dữ liệu, `@Param`, số thread, warm-up, measurement và fork.
- Thời điểm chạy và các workload khác đang hoạt động trên máy.

Một file JSON không có metadata môi trường thường không đủ để giải thích vì sao kết quả của hai ngày hoặc hai máy khác nhau.

## 12. Quy tắc so sánh hai API hoặc hai thuật toán

Trước khi so sánh, hãy kiểm tra:

1. Hai phương án có cùng semantics và trả cùng kết quả không?
2. Có cùng dữ liệu đầu vào, kích thước và phân bố dữ liệu không?
3. Chi phí chuẩn bị input có được đưa vào hoặc loại khỏi cả hai phương án giống nhau không?
4. Có cùng JDK build, JVM flags, heap, collector và phần cứng không?
5. Có đủ warm-up, measurement iteration và fork không?
6. Kết quả có bị dead-code elimination hoặc constant folding không?
7. Có đo allocation/GC khi hai phương án tạo lượng object khác nhau không?
8. Chênh lệch có lớn hơn độ biến thiên và có ý nghĩa với workload thật không?

Không so sánh `String.indexOf()` với regex compile mỗi lần nếu ứng dụng thực tế cache `Pattern`, trừ khi câu hỏi chính là chi phí compile. Không so sánh vòng lặp tạo mảng mới với Stream chỉ trả checksum. Không thay đổi đồng thời thuật toán, input size, số thread và JVM flags rồi kết luận một nguyên nhân duy nhất.

## 13. Các lỗi thường gặp

| Lỗi | Vì sao kết quả không đáng tin | Cách sửa |
|---|---|---|
| Đo bằng một vòng `System.nanoTime()` | Không kiểm soát warm-up, JIT, fork và sai số timer | Dùng JMH harness |
| Chạy benchmark method như JUnit test | Bỏ qua generated harness và quy trình measurement | Tạo project JMH và chạy executable JAR |
| Chỉ thêm `jmh-core` | Thiếu annotation processing/generated benchmark code | Dùng archetype hoặc cấu hình annotation processor đúng |
| Không trả hoặc consume kết quả | JIT có thể loại bỏ phép tính | Return kết quả hoặc dùng `Blackhole` |
| Dùng input compile-time constant | JIT có thể constant-fold phép tính | Dùng state, `@Param` và dữ liệu runtime |
| Đưa toàn bộ setup vào benchmark method | Đo cả công việc không thuộc câu hỏi | Chuyển fixture sang `@Setup` nếu setup không phải chi phí cần đo |
| Setup quá nhiều ở mỗi invocation | Làm thay đổi cache/GC và tăng nhiễu | Chọn `Level.Trial` hoặc `Level.Iteration` phù hợp |
| Không có warm-up hoặc fork | Đo cả trạng thái JVM chưa ổn định hoặc profile bị nhiễm | Cấu hình warm-up, measurement và fork |
| Benchmark hai cách làm khác semantics | Kết quả không phải so sánh tương đương | Chuẩn hóa output và công việc trước khi đo |
| Chạy benchmark trong IDE khi máy đang tải | Môi trường không kiểm soát và có background noise | Chạy JAR từ command line trên máy ổn định |
| Dùng JMH cho latency database/network end-to-end | Kết quả bị chi phối bởi hệ thống ngoài phạm vi microbenchmark | Dùng load test hoặc benchmark tích hợp phù hợp |

## 14. Quy trình thực hiện một microbenchmark

1. Viết rõ giả thuyết cần kiểm tra, ví dụ “lookup literal có chi phí thấp hơn regex đã compile ở input dài”.
2. Chọn hai hoặc nhiều cách triển khai có cùng semantics.
3. Tạo project JMH độc lập bằng archetype và dùng đúng JDK mục tiêu.
4. Đưa input vào `@State`, tạo fixture trong `@Setup`, dùng `@Param` cho các kích thước cần khảo sát.
5. Viết method `@Benchmark`, trả kết quả hoặc dùng `Blackhole`.
6. Chọn mode, output unit, warm-up, measurement và fork phù hợp.
7. Build bằng `mvn clean verify`, chạy executable JAR từ command line.
8. Chạy GC profiler nếu allocation là một phần của câu hỏi.
9. Lặp lại trên môi trường tương đương và lưu JSON cùng metadata.
10. Đối chiếu kết quả với workload thực tế trước khi quyết định tối ưu.

## Tài liệu tham khảo chính thức

- [OpenJDK JMH — Project README and usage guide](https://github.com/openjdk/jmh)
- [OpenJDK JMH — Samples](https://github.com/openjdk/jmh/tree/master/jmh-samples/src/main/java/org/openjdk/jmh/samples)
- [Maven Central — org.openjdk.jmh:jmh-core](https://central.sonatype.com/artifact/org.openjdk.jmh/jmh-core)
- [Java SE 21 — Java Virtual Machine Specification](https://docs.oracle.com/javase/specs/jvms/se21/html/index.html)
