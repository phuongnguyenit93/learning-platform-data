# Benchmark Java: tránh constant folding và dead-code elimination

Một phép toán Java chạy mất "0 ns" hoặc nhanh hơn cả việc đọc một biến chưa chắc là thuật toán đã được tối ưu xuất sắc. Đôi khi JVM đã chứng minh **đầu ra luôn là hằng số** rồi thay cả phép tính bằng một giá trị có sẵn (*constant folding*), hoặc đã chứng minh **kết quả không ảnh hưởng điều gì có thể quan sát** rồi loại phép tính (*dead-code elimination*, DCE). Nếu mục tiêu là đo chi phí của một phép tính thực sự được ứng dụng sử dụng, hai tối ưu hợp lệ của JVM này có thể làm benchmark đo sai đối tượng.

Bài học thuộc chủ đề **Hiệu năng** trong Java Core - Numbers. Mục tiêu là hiểu khi nào benchmark số học bị JVM tối ưu mất, cách thiết kế đầu vào/đầu ra để đo đúng công việc, cách dùng **Java Microbenchmark Harness (JMH)** và cách đọc kết quả thận trọng. Bài dùng cú pháp Java 17+, giải thích cả trường hợp mã “chạy đúng” nhưng phép đo không còn đại diện cho workload thật.

## 1. Benchmark đo điều gì?

Một *microbenchmark* cô lập một thao tác nhỏ, chẳng hạn phép nhân `long`, hàm chuyển đổi số, `BigDecimal.add()`, hoặc một hàm kiểm tra điều kiện. Mục tiêu là ước lượng chi phí và/hoặc thông lượng khi JVM đã thực thi mã trong bối cảnh tương ứng.

Một phép đo chỉ có ý nghĩa khi ta trả lời được:

1. **Tác vụ được đo:** chính xác phương thức và đầu vào nào?
2. **Kết quả có được sử dụng?** Trong ứng dụng thật, phép tính có tác động đến kết quả trả về, dữ liệu lưu trữ, hoặc trạng thái quan sát được không?
3. **Đầu vào thay đổi ở mức nào?** Một hằng số trong bytecode, trường `final`, trường trạng thái được gán lúc chạy, hay dữ liệu thật?
4. **Có đang đo cả thứ khác không?** Tạo đối tượng, đọc I/O, cấp phát, khởi tạo thư viện, chuyển đổi dữ liệu và gọi hàm có thể đã bị trộn vào thời gian tính toán.
5. **JIT đã warm up chưa?** JVM có thể diễn dịch và biên dịch tối ưu cùng phương thức ở các giai đoạn khác nhau; lần đầu chạy thường không đại diện cho trạng thái ổn định.
6. **Chi phí đo và điều kiện chạy:** có fork JVM độc lập, warmup, chu kỳ đo, GC, CPU contention và cách xử lý thống kê hay chưa?

Đơn vị báo cáo `ns/op` nghĩa là **nanosecond trên một đơn vị công việc benchmark** theo cấu hình harness. Nó không tự chứng minh đồng hồ đo có độ phân giải một nanosecond hay thao tác tương đương sẽ mất chừng ấy thời gian trong mọi ứng dụng.

## 2. JVM được phép tối ưu những gì?

Java cho phép compiler/JIT thực hiện những biến đổi giữ nguyên **hành vi quan sát được** của chương trình. Đối với các phép tính thuần túy, không có tác động phụ, việc bỏ đi hoặc thay bằng hằng số là hợp lệ khi nó không làm thay đổi đầu ra cần quan sát.

Mô hình đơn giản:

~~~text
Java source
    |
    v
javac tạo bytecode
    |
    v
JVM diễn dịch / biên dịch JIT các đoạn nóng
    |
    +--> constant propagation / constant folding
    +--> inline method / hoist loop-invariant work
    +--> dead-code elimination / escape analysis
    |
    v
Machine code được thực thi
~~~

Đây là sơ đồ khái niệm; vị trí và mức độ tối ưu thay đổi giữa JVM, phiên bản, workload và profile chạy. `javac` có thể rút gọn một số biểu thức hằng từ thời điểm biên dịch, còn JIT có thể tối ưu sau khi đã biết thêm thông tin về các lời gọi thực tế.

**Benchmark cần đo mã *sau tối ưu*** vì đó là mã ứng dụng thực sự chạy. Ta không cố “tắt mọi tối ưu”. Ta cần tạo bối cảnh đầu vào và đầu ra **đúng với tình huống thực tế**, để JIT không biến mất chính công việc mà benchmark giả định đang đo.

## 3. Constant folding: khi cả phép tính chỉ còn hằng số

*Constant folding* xảy ra khi compiler biết các toán hạng và có thể xác định kết quả trước, ví dụ:

~~~java
int result = 12 * 12; // Kết quả 144 có thể được tính sẵn.
~~~

Đối với benchmark, tình huống nguy hiểm là đưa toàn bộ đầu vào như hằng số:

~~~java
static long compute(long x) {
    long result = x;
    for (int i = 0; i < 8; i++) {
        result = (result * 31 + i) ^ (result >>> 3);
    }
    return result;
}

// Phép tính với đầu vào cố định:
long result = compute(7L);
~~~

Nếu JIT inline `compute` rồi suy luận được vòng lặp và `x = 7L` không đổi, nó **có thể** precompute hoặc rút gọn phần lớn công việc. Một hàm có nhiều phép nhân, phép cộng và XOR ở mã nguồn không bảo đảm số lượng lệnh máy tương ứng thực sự được chạy ở mỗi iteration đo.

Lưu ý ba cấp độ:

- **Constant folding:** rút gọn một biểu thức khi đã biết đầu vào.
- **Constant propagation:** truyền thông tin về giá trị hằng qua biến hoặc lời gọi, mở cơ hội folding.
- **Loop-invariant code motion:** đưa một phép tính không đổi giữa các vòng ra ngoài vòng lặp khi hợp lệ; benchmark thủ công lặp lại cùng phép tính có thể thực hiện công việc chỉ một lần.

Một số tối ưu có thể diễn ra ngay trong `javac`, số khác do JIT quyết định. Không nên nói rằng JVM **luôn** tối ưu mọi hàm thuần thành hằng; đúng hay không phụ thuộc cấu trúc chương trình, khả năng inline, điều kiện chạy và trình biên dịch. Nguy cơ benchmark là **JVM được phép và có cơ hội làm điều đó**, nên kết quả cực nhanh chưa đủ chứng minh phép tính đã được thực hiện như mong đợi.

## 4. Dead-code elimination: tính xong nhưng không ai dùng

*Dead-code elimination* (DCE) loại những thao tác mà kết quả của chúng không được chương trình quan sát. Ví dụ:

~~~java
static long compute(long x) {
    return (x * 31 + 17) ^ (x >>> 3);
}

static void wrongBenchmark(long input) {
    compute(input); // Kết quả bị bỏ; không có side effect.
}
~~~

Đoạn trên là minh họa **không phải chương trình hoàn chỉnh**. Nếu `compute` được inline, JVM có thể nhận ra phép tính không thay đổi trạng thái quan sát được rồi xóa toàn bộ. Benchmark có thể chủ yếu đo overhead của harness hoặc biến đổi còn sót lại, không đo chi phí phép toán.

Điểm cần hiểu: **đầu vào biến đổi vẫn chưa đủ** nếu đầu ra bị bỏ. Ngược lại, **đầu ra được dùng vẫn chưa đủ** nếu toàn bộ công việc có thể được thay bằng kết quả hằng. Một benchmark tốt phải bảo vệ cả hai đầu:

~~~text
Dữ liệu đầu vào thực tế, không bị compiler coi là hằng
                        |
                        v
                   Công việc đo
                        |
                        v
Kết quả được dùng/tiêu thụ theo cách harness có thể quan sát
~~~

Đừng sửa bằng cách thêm `System.out.println(result)` **trong chính vòng benchmark**: I/O console đắt và biến động hơn nhiều phép toán số học, khiến phép đo trở thành benchmark in log. Đừng dùng `Thread.sleep()` để làm số đo “thấy rõ”: nó đo việc chờ và scheduler, không đo phép tính.

## 5. Hai lỗi có thể cùng xuất hiện

Xét một benchmark thủ công:

~~~java
long start = System.nanoTime();

for (int i = 0; i < 1_000_000; i++) {
    long result = compute(7L);
}

long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
~~~

Mã có thể báo số rất nhỏ hoặc thay đổi thất thường dù một triệu lượt lặp xuất hiện trong source:

- `result` không được dùng; JVM có thể loại việc tính `compute`.
- Đầu vào `7L` cố định; compiler có thể rút gọn hoặc đưa công việc ra ngoài vòng lặp.
- Việc tự đo bằng `nanoTime()` thiếu warmup/fork kiểm soát, mắc nhiễu JIT/GC/OS scheduling; timing overhead có thể đáng kể so với phép toán nhỏ.
- Nếu thay kết quả bằng một biến cộng dồn dùng ở cuối, JIT vẫn có thể biến đổi phép tính lặp, và khi phép toán quá nhỏ thì chính vòng lặp/accumulator trở thành phần lớn chi phí.
- Nếu đo mà in kết quả trong mỗi lượt, chi phí I/O áp đảo phép tính.

Không kết luận "phép nhân Java tốn 0 ns" từ số đo này. Có thể **phép nhân không còn nằm trong đoạn máy được thực thi để đo**.

## 6. JMH: harness dành cho microbenchmark JVM

**Java Microbenchmark Harness (JMH)** là dự án OpenJDK được tạo để thiết kế và chạy microbenchmark trên JVM, có hỗ trợ warmup, measurement iterations, fork JVM, chế độ đo và cơ chế tiêu thụ kết quả. Với benchmark hiệu năng Java nhỏ, đây là điểm bắt đầu đáng tin cậy hơn vòng lặp `nanoTime()` tự viết.

JMH giúp kiểm soát điều kiện đo, **không thể tự biết nghiệp vụ muốn đo gì**. Nếu tác giả đưa đầu vào hằng, bỏ kết quả hoặc đo sai công việc, JMH vẫn có thể chạy benchmark đó và trả số đo hợp lệ cho đoạn mã *thực sự được thực thi*. Thiết kế workload vẫn là trách nhiệm của người viết benchmark.

Để có cấu hình annotation processing và đóng gói chuẩn, dùng Maven archetype của JMH tạo một dự án biệt lập. Ví dụ dùng JMH 1.37:

~~~bash
mvn archetype:generate -B -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DarchetypeVersion=1.37 -DgroupId=example.bench -DartifactId=jmh-demo -Dversion=1.0-SNAPSHOT
cd jmh-demo
~~~

Lệnh cần Maven và khả năng tải dependency khi chưa có cache. Dự án tạo ra có `pom.xml`, mã mẫu và cấu hình JMH. Những ví dụ tiếp theo đặt trong `src/main/java/example/bench/`. Phiên bản `1.37` là phiên bản đã được đối chiếu trong Maven Central; khi dự án có quy trình quản lý phiên bản dependency riêng, sử dụng phiên bản phù hợp được kiểm thử trong môi trường của dự án.

Không chạy `@Benchmark` như một hàm thông thường rồi tự gọi `System.nanoTime()` quanh nó; như vậy không sử dụng các tính năng của harness.

## 7. Ví dụ JMH đầy đủ: giữ đầu vào runtime và dùng kết quả

Tạo `src/main/java/example/bench/ComputeBench.java` trong dự án archetype:

~~~java
package example.bench;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.infra.Blackhole;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class ComputeBench {

    @Param({"7", "11", "19"})
    public long input;

    private static long compute(long x) {
        for (int i = 0; i < 8; i++) {
            x = (x * 31 + i) ^ (x >>> 3);
        }
        return x;
    }

    @Benchmark
    public long resultReturned() {
        return compute(input);
    }

    @Benchmark
    public void resultConsumed(Blackhole blackhole) {
        blackhole.consume(compute(input));
    }
}
~~~

Biên dịch/đóng gói bằng Maven trong thư mục dự án:

~~~bash
mvn clean verify
java -jar target/benchmarks.jar ComputeBench -t 1
~~~

**Giải thích những điểm chống benchmark sai:**

1. `@State(Scope.Thread)` cung cấp một trạng thái trên mỗi thread benchmark. Ta đo trên đối tượng do JMH quản lý, không phụ thuộc một biến cục bộ có thể được compiler nhận ngay là hằng.
2. `@Param({"7", "11", "19"})` yêu cầu JMH chạy các trường hợp tham số. Trường `input` không khai báo `final` và được harness gán tại runtime. Đây là cách tránh việc đưa trực tiếp cùng một literal vào phép tính có thể gập thành hằng. Nếu ứng dụng thật chỉ có vài hằng và JIT thực sự được phép gập, benchmark đó cần mục tiêu khác, không nên cố “cản JIT” ngoài ngữ cảnh.
3. `resultReturned()` trả kết quả từ `@Benchmark`. JMH **tiêu thụ kết quả trả về** để hạn chế DCE; trả một giá trị khác hoặc một hằng giả thay cho kết quả thật sẽ không đạt mục tiêu.
4. `resultConsumed(Blackhole)` minh họa cách chuyển kết quả trực tiếp vào `Blackhole.consume(...)` khi phương thức benchmark cần kiểu `void` hoặc xử lý nhiều kết quả trung gian. JMH sử dụng cơ chế này để hạn chế compiler coi giá trị đầu ra là không cần thiết.
5. `@Warmup` và `@Measurement` tách giai đoạn khởi động tối ưu và giai đoạn lấy số liệu; `@Fork(2)` chạy hai JVM fork độc lập để giảm phụ thuộc trạng thái một phiên chạy.
6. `@BenchmarkMode(Mode.AverageTime)` cùng `@OutputTimeUnit(NANOSECONDS)` yêu cầu JMH báo thời gian trung bình trên một operation. Đây **không phải** hứa hẹn latency từng lời gọi là chính xác một số nano giây cố định.

Hai phương thức dùng hai cách khác nhau để giữ kết quả; chúng **không được kỳ vọng cho số đo giống hệt từng chữ số**, vì đường đi tiêu thụ kết quả/harness có overhead và đặc tính tối ưu khác nhau. Mục tiêu bài là thiết kế một phép đo không vô tình bỏ toàn bộ công việc. Kết quả thời gian tùy CPU, JVM, môi trường và phiên chạy; **không cung cấp bảng số ns/op giả định**.

Nếu Maven build báo không tìm `org.openjdk.jmh.generated` hay benchmark không được đăng ký, hãy kiểm tra annotation processor JMH trong cấu hình archetype/build. Chỉ chép lớp `ComputeBench` vào một chương trình Java thường rồi gọi `main` không đủ để JMH tự chạy.

## 8. Phân biệt ví dụ sai và ví dụ đúng

Các đoạn sau là **minh họa về vấn đề**, không phải các benchmark JMH độc lập nên chạy để rút kết luận hiệu năng.

### Sai A: dùng đầu vào hằng

~~~java
@Benchmark
public long foldable() {
    return compute(7L);
}
~~~

Dù trả kết quả về harness, JIT vẫn có thể inline và constant-fold `compute(7L)`. Đầu ra đã được sử dụng **nhưng công việc cần đo có thể đã bị gập**. So với ví dụ đúng `compute(input)` mà `input` là trường trạng thái runtime.

### Sai B: bỏ kết quả

~~~java
@Benchmark
public void unused() {
    compute(input);
}
~~~

Dù `input` đến từ một trạng thái runtime, phép tính thuần không có hiệu ứng quan sát khi kết quả bị bỏ. DCE có thể loại bỏ nó. So với ví dụ đúng `return compute(input)` hoặc `blackhole.consume(compute(input))`.

### Sai C: tạo hằng với `final`

~~~java
private static final long FIXED = 7L;

@Benchmark
public long foldedConstant() {
    return compute(FIXED);
}
~~~

Khai báo `final` thường có ý nghĩa tốt trong mã ứng dụng; nhưng khi mục tiêu benchmark là **tính toán với dữ liệu thay đổi**, `static final` và literal tạo điều kiện cho folding. Không “cấm final” ở mọi nơi; hãy phân biệt dữ liệu benchmark phải động với các thông số thực sự cố định theo hợp đồng ứng dụng.

### Đúng theo mục tiêu đo dữ liệu runtime

~~~java
@State(Scope.Thread)
public static class Inputs {
    @Param({"7", "11", "19"})
    public long value;
}

@Benchmark
public long runtimeInput(Inputs inputs) {
    return compute(inputs.value);
}
~~~

Đoạn này cần nằm trong lớp benchmark có phương thức `compute` và các import JMH tương ứng. `@Param`/`@State` không bảo đảm tuyệt đối mọi phép tính đều còn tồn tại ở máy; chúng giúp benchmark phản ánh dữ liệu được cung cấp ở runtime và giảm nguy cơ gập thành hằng. Kiểm chứng đầu ra máy khi phép đo cực nhỏ hoặc bất thường vẫn có giá trị.

## 9. Chương trình Java 17 độc lập để kiểm tra chức năng, không đo hiệu năng

Trước khi đo thời gian, hãy chứng minh hàm tính toán **thực sự phụ thuộc đầu vào** và kết quả kỳ vọng là gì. Ví dụ đơn giản không phụ thuộc JMH:

Tạo tệp `BenchmarkPitfallsDemo.java`:

~~~java
public final class BenchmarkPitfallsDemo {
    private static volatile long sink;

    static long compute(long x) {
        for (int i = 0; i < 8; i++) {
            x = (x * 31 + i) ^ (x >>> 3);
        }
        return x;
    }

    public static void main(String[] args) {
        long a = compute(7);
        long b = compute(11);
        sink = a;
        System.out.println("a = " + a);
        System.out.println("b = " + b);
        System.out.println("different results = " + (a != b));
        System.out.println("sink = " + sink);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 BenchmarkPitfallsDemo.java
java BenchmarkPitfallsDemo
~~~

Kết quả xác định cho các giá trị minh họa:

~~~text
a = 5985353341353
b = 9465354105287
different results = true
sink = 5985353341353
~~~

Chương trình chứng minh hàm `compute` có hai kết quả khác nhau theo hai đầu vào; biến `volatile sink` cho phép một cách sử dụng kết quả có thể quan sát. **Đây không phải benchmark thời gian.** Việc thêm `volatile` không thay thế warmup, fork, thống kê và cơ chế chống compiler tối ưu sai ngữ cảnh của JMH. Nếu viết thêm vòng lặp đo quanh chương trình này, vẫn phải phân tích các tối ưu và chi phí truy cập `volatile` riêng.

## 10. Blackhole: tiêu thụ kết quả đúng cách

JMH cung cấp `org.openjdk.jmh.infra.Blackhole`. Ta có thể dùng:

~~~java
@Benchmark
public void benchmark(Blackhole blackhole) {
    long value = compute(input);
    blackhole.consume(value);
}
~~~

Nếu benchmark là `public long benchmark()`, chỉ cần `return compute(input)` thường là đủ: JMH xử lý giá trị trả về. Blackhole hữu ích hơn khi một iteration tính nhiều kết quả hoặc thao tác benchmark không có kiểu trả về thuận tiện.

**Không gọi `Blackhole.consumeCPU(...)` chỉ để đảm bảo CPU làm việc**: phương thức này được dùng cho những mục tiêu mô phỏng tải CPU riêng; nó không chứng minh công việc cần đo đã chạy và có thể tạo thêm chi phí không thuộc workload.

**Không tự viết một biến static `volatile` thành giải pháp phổ quát.** Ghi volatile có chi phí, hiệu ứng bộ nhớ và cạnh tranh trạng thái khi nhiều thread dùng chung. Nó có thể làm kết quả so sánh hai thuật toán lệch theo chi phí phụ do chính benchmark thêm vào.

**Không in kết quả trong `@Benchmark`** và tránh cập nhật shared `List`/`Map` chỉ để giữ kết quả nếu ứng dụng thật không yêu cầu hoạt động đó. Việc làm giả “observable use” có thể đo cả allocation, synchronization và contention không liên quan. Chọn `return` hoặc `Blackhole` trước, sau đó xác minh JVM không loại/biến đổi phần quan trọng.

## 11. @State, @Param và dữ liệu đầu vào thực tế

Một benchmark đáng tin cậy phải phản ánh **phân bố đầu vào** của ứng dụng, không chỉ một hằng thuận tiện.

`@Param` cho phép báo cáo nhiều trường hợp, ví dụ các số nguyên nhỏ, lớn, âm và gần biên. Với bài toán số học, thời gian có thể phụ thuộc số chữ số hoặc kích thước nội bộ, đặc biệt với `BigInteger` và `BigDecimal`. Đo một đối tượng đặc biệt như `BigInteger.ONE` rồi suy ra hiệu năng cho hàng nghìn chữ số là thiếu căn cứ.

`@State(Scope.Thread)` tạo state riêng trên mỗi benchmark thread; `Scope.Benchmark` tạo state chia sẻ trong phạm vi benchmark theo hợp đồng JMH, phù hợp nếu bạn **thực sự muốn đo contention**. Nếu mục tiêu là tốc độ tính toán đơn luồng, vô tình dùng shared mutable state có thể khiến ta đo tranh chấp thay vì thuật toán.

Với dữ liệu số phức tạp, có thể dùng `@Setup(Level.Trial)` để chuẩn bị dữ liệu ngoài đường đo:

~~~java
@State(Scope.Thread)
public static class DecimalInputs {
    @Param({"16", "128"})
    public int digits;

    public java.math.BigInteger value;

    @Setup(Level.Trial)
    public void setup() {
        value = java.math.BigInteger.TEN.pow(digits)
                .add(java.math.BigInteger.valueOf(12345));
    }
}
~~~

Đoạn này cần các import JMH `@State`, `Scope`, `@Param`, `@Setup` và `Level`. Không xây dựng `BigInteger` lớn bên trong mỗi `@Benchmark` nếu mục tiêu là **chỉ đo phép toán trên số đã có sẵn**; còn nếu ứng dụng thật phải parse/chuyển đổi số trong mỗi tác vụ, việc đưa công đoạn đó vào lại hợp lý. Hãy phát biểu phạm vi đo trong tên benchmark và giải thích.

Đừng chuyển mọi đầu vào thành `final static` để giảm noise nếu bạn cần biết hiệu năng trên dữ liệu runtime. Và đừng cập nhật tham số theo một quy luật giả tạo ngay trong mỗi invocation nếu chính việc cập nhật tham số sẽ áp đảo phép tính nhỏ được đo.

## 12. Warmup, fork và các mode đo

Khi chạy Java, JVM có thể trải qua thông dịch, compiler tầng khác nhau, thu thập profile, inline, cache warming, tải class và GC. Nếu đo vài lời gọi ban đầu rồi chia thời gian, kết quả phụ thuộc mạnh vào trạng thái khởi tạo.

Các thuộc tính JMH quan trọng:

| Cấu hình | Ý nghĩa |
|---|---|
| `@Warmup(iterations = 3, time = 1)` | Chạy các khoảng warmup không dùng làm kết quả cuối |
| `@Measurement(iterations = 5, time = 1)` | Lấy 5 khoảng đo trong mỗi fork |
| `@Fork(2)` | Chạy hai JVM fork độc lập |
| `@BenchmarkMode(Mode.AverageTime)` | Báo thời gian trung bình trên operation |
| `@BenchmarkMode(Mode.Throughput)` | Báo số operation mỗi đơn vị thời gian |
| `@OutputTimeUnit(TimeUnit.NANOSECONDS)` | Chỉ định đơn vị báo cáo |
| `-t 1` | Chạy một benchmark thread, tránh trộn contention vào phép đo đơn luồng |

Ví dụ chạy JMH sau khi build có thể ghi đè cấu hình annotation:

~~~bash
java -jar target/benchmarks.jar ComputeBench -wi 3 -i 5 -w 1s -r 1s -f 2 -t 1
~~~

Các tùy chọn này chọn warmup 3 iteration, measurement 5 iteration, mỗi khoảng một giây, hai fork và một thread. Điều kiện CPU, nhiệt độ, hệ điều hành, power plan và workload cạnh tranh đều có thể tác động số đo.

JMH output thường có tên benchmark, số lượng mẫu, mode, score, error và units. `Score Error` là chỉ báo bất định theo cách tính của harness, **không có nghĩa tất cả phép đo của ứng dụng ngoài đời đều nằm trong đúng khoảng đó**. Khi khác biệt nhỏ hơn noise hoặc phụ thuộc hệ thống, không tuyên bố chiến thắng hiệu năng chỉ từ một lần benchmark.

## 13. Các tối ưu khác cũng làm benchmark lệch mục tiêu

Constant folding và DCE là hai ví dụ nổi bật, nhưng microbenchmark Java còn gặp:

- **Inlining:** JIT thay lời gọi method bằng thân hàm. Đó là tối ưu thực tế cần cân nhắc; nếu benchmark cố đo “overhead lời gọi”, hãy xác định ứng dụng có thực sự không được inline hay không.
- **Escape analysis và scalar replacement:** object được tạo nhưng không “thoát” có thể được JVM loại allocation hoặc thay bằng trường scalar. Nếu đo allocation thật, bảo đảm tình huống object sống/thoát phù hợp ứng dụng, nhưng đừng cố tình giữ object sai mục tiêu.
- **Loop unrolling và loop-invariant hoisting:** vòng lặp lặp lại cùng đầu vào có thể được rút gọn/đưa phép tính ra ngoài. JMH thường điều khiển lặp nội bộ, nên tránh tự thêm vòng `for` lớn vào benchmark nếu không thật sự đang đo batch.
- **Profile-guided/speculative optimization:** JVM tối ưu theo kiểu/nhánh thường gặp; đầu vào benchmark quá đồng nhất có thể khiến branch prediction và việc inline thuận lợi hơn workload thực tế.
- **Cấp phát và GC:** benchmark tạo mảng hoặc `BigDecimal` mới có thể có chi phí garbage collection không đều giữa lần chạy. Chọn đo cả cấp phát hay chỉ xử lý dữ liệu có sẵn.
- **Cache locality và memory layout:** dữ liệu nhỏ luôn nằm trong cache có thể tạo kết quả khác hẳn input lớn trên máy thật.
- **Autoboxing:** đo `Long`/`Integer` trong khi ứng dụng sử dụng primitive hoặc ngược lại sẽ pha thêm chi phí không mong muốn.

Các tối ưu này **không xấu**. Chúng làm benchmark lệch khi thiết lập dữ liệu hoặc việc sử dụng kết quả khác với mục tiêu cần đo. Mục tiêu là có một phép đo tương ứng với workload, không phải chống compiler bằng mọi giá.

## 14. Ví dụ với Numbers: đo BigDecimal đúng phạm vi

Giả sử cần so sánh chi phí `BigDecimal.add()` và `BigDecimal.multiply()`. Tạo hai đối tượng từ chuỗi bên trong mỗi `@Benchmark` sẽ khiến thời gian bao gồm **parse decimal + cấp phát + phép toán**, khác với trường hợp ứng dụng đã có sẵn dữ liệu.

Thiết kế gợi ý:

~~~java
@State(Scope.Thread)
public static class NumberState {
    @Param({"12.345", "123456789.012345"})
    public String text;

    public BigDecimal left;
    public BigDecimal right;

    @Setup(Level.Trial)
    public void setup() {
        left = new BigDecimal(text);
        right = new BigDecimal("7.8901");
    }
}

@Benchmark
public BigDecimal add(NumberState state) {
    return state.left.add(state.right);
}

@Benchmark
public BigDecimal multiply(NumberState state) {
    return state.left.multiply(state.right);
}
~~~

Đây là **đoạn minh họa cần đặt trong lớp JMH** với import `BigDecimal`, các annotation JMH và `Level`; không phải tệp Java chạy trực tiếp. Bên ngoài đường đo, `@Setup(Level.Trial)` dựng dữ liệu để benchmark phản ánh phép toán trên các `BigDecimal` đã tồn tại. Kết quả `BigDecimal` được trả về và JMH tiêu thụ, tránh để DCE xóa thao tác.

Tuy nhiên, chọn trước `left/right` cố định có thể giúp JIT khai thác thêm đặc tính dữ liệu và phép toán tùy cấu trúc mã; nó không tự chứng minh benchmark bao trùm mọi giá trị thực tế. Để đo phân bố đầu vào lớn/nhỏ, âm/dương hoặc các `scale` khác nhau, cần nhiều case và dữ liệu thay đổi hợp lý theo nghiệp vụ. Khi muốn so sánh bộ xử lý, luôn kiểm chứng phép toán thực sự được tính chứ không đã được “trả về từ cache” theo một đặc điểm riêng của input.

## 15. Checklist đánh giá một microbenchmark

Trước khi tin kết luận hiệu năng, kiểm tra lần lượt:

1. **Định nghĩa phép toán:** Bạn đang đo hàm thuần, parse, khởi tạo, I/O, đồng bộ hay cả quy trình?
2. **Chặn constant folding không phù hợp:** Dữ liệu ứng dụng thật có biến đổi không? Nếu có, tham số benchmark có đến từ state runtime (ví dụ `@Param`) thay vì literal hoặc `static final` không?
3. **Chặn DCE:** Kết quả của công việc cần đo có được `return` hoặc `Blackhole.consume` trong JMH không? Có side effect phù hợp thực tế không?
4. **Không đưa chi phí ngoại lai vào đường đo:** In console, sleep, cấp phát test fixture, tạo RNG, parse không cần thiết hoặc cập nhật global `volatile` có đang chiếm thời gian không?
5. **Dùng JMH đúng cách:** Annotation processor hoạt động, benchmark chạy qua harness, có warmup, measurement, fork phù hợp.
6. **Đảm bảo chức năng:** Kết quả tính toán với các đầu vào có thể kiểm chứng; benchmark sai logic nhưng rất nhanh không có giá trị.
7. **Xem xét tối ưu máy:** Với phép đo quá nhanh/bất thường, có thể kiểm tra profiling/disassembly nếu môi trường hỗ trợ để hiểu mã máy và tỷ lệ công việc bị bỏ; không suy đoán từ số ns/op một mình.
8. **Kiểm soát nguồn nhiễu:** JVM/JDK version, CPU, GC, load hệ thống, mức song song và điều kiện nhiệt/điện phải được ghi lại.
9. **Không nhầm khác biệt ngắn hạn với cải tiến:** Chạy lại khi có lý do, xem sai số và phạm vi ứng dụng; báo kết quả kèm điều kiện, không suy ra một con số tuyệt đối cho mọi máy.
10. **So sánh công bằng:** Hai phương án phải cùng đầu vào, cùng tiêu chí đầu ra đúng, cùng loại chi phí được tính. Không để một bên thực hiện ít công việc hơn chỉ nhờ benchmark quên tiêu thụ kết quả.

Không có một “anti-optimizer trick” duy nhất đủ cho mọi bài benchmark. `Blackhole` giúp hạn chế DCE, `@State`/`@Param` giúp cung cấp runtime input, còn **thiết kế thí nghiệm** quyết định tính đại diện cho bài toán.

## 16. Bài tập dự đoán và sửa lỗi

**Bài 1 — Kết quả bị bỏ.** Phương thức dưới đây sai ở đâu?

~~~java
@Benchmark
public void test() {
    expensivePureCalculation(input);
}
~~~

**Đáp án:** Nếu hàm không có side effect, đầu ra bị bỏ nên JVM có thể DCE. Đổi thành benchmark trả kết quả hoặc truyền kết quả vào `Blackhole.consume`. Đồng thời kiểm tra `input` không là hằng số ngoài ý muốn.

**Bài 2 — Có return vẫn có thể sai.**

~~~java
@Benchmark
public long test() {
    return compute(123L);
}
~~~

**Đáp án:** Trả kết quả giúp chống DCE nhưng `123L` cố định tạo điều kiện cho constant folding, inlining và hoisting. Nếu ứng dụng xử lý nhiều số runtime, dùng `@State` và `@Param` hoặc dữ liệu runtime tương ứng.

**Bài 3 — Dùng volatile là đủ chưa?** Một lập trình viên thay `Blackhole` bằng `private static volatile long sink;`, rồi ghi `sink = compute(7L);` sau mỗi lần gọi. Đã an toàn để so sánh hiệu năng chưa?

**Đáp án:** Chưa. Phép tính với literal vẫn có thể gập thành hằng; ghi volatile trở thành phần đáng kể của chi phí. Cần JMH, đầu vào runtime và tiêu thụ kết quả đúng ngữ cảnh.

**Bài 4 — Đầu vào cố định khi nào hợp lệ?** Ứng dụng thật luôn gọi `compute(7L)` và JIT thực sự biến nó thành hằng. Có nên cố buộc benchmark thực hiện tám vòng phép tính?

**Đáp án:** Nếu mục tiêu là đo **chi phí thực tế của đúng call-site này**, để JIT tối ưu theo điều kiện thật có thể là lựa chọn hợp lý. Chỉ khi muốn đo thuật toán với đầu vào biến đổi mới cần thiết kế state runtime để tránh kết quả bị gập. Benchmark phải phản ánh yêu cầu, không máy móc “ngăn mọi tối ưu”.

**Bài 5 — Kết quả 0.001 ns/op.** Một phép nhân phức tạp được báo ở tốc độ khó tin. Nên làm gì trước khi quảng bá đây là tối ưu vượt trội?

**Đáp án:** Kiểm tra kết quả có được tiêu thụ không, input có constant-fold được không, benchmark có lặp batch khiến đơn vị `op` bị chia sai không, có chạy đúng JMH không, và nếu cần kiểm tra phần mã máy/JIT. Không được kết luận thuật toán nhanh từ số đo bất thường mà chưa kiểm chứng nội dung phép đo.

## 17. Ghi nhớ và nguồn tham khảo

- **Constant folding:** nếu dữ liệu/biểu thức đủ xác định, JVM có thể thay phép tính bằng kết quả biết trước. Với benchmark cần đo dữ liệu runtime, dùng trường trạng thái không `final`, `@Param` và tình huống có phân bố input đại diện.
- **Dead-code elimination:** nếu kết quả không được dùng, JVM có thể bỏ hẳn phép tính thuần. Trong JMH, hãy `return` kết quả hoặc `Blackhole.consume(...)`.
- **Hai điều kiện là độc lập:** dùng kết quả chưa chắc chống folding; dùng runtime input chưa chắc chống DCE.
- **JMH cung cấp harness**, warmup, fork, đo và xử lý kết quả; người viết vẫn phải chọn đúng công việc, dữ liệu và cách quan sát.
- **Đánh giá kết quả theo hợp đồng workload và điều kiện máy**, không suy ra một quy luật tuyệt đối từ số ns/op đơn lẻ.

Tài liệu chính thức và ví dụ nên đọc:
- [OpenJDK JMH](https://github.com/openjdk/jmh): dự án, cách khởi tạo bằng Maven archetype, cấu hình chạy microbenchmark.
- [JMHSample_08_DeadCode](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java): so sánh benchmark bỏ kết quả với benchmark trả kết quả.
- [JMHSample_09_Blackholes](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_09_Blackholes.java): sử dụng `Blackhole` khi kết quả cần được tiêu thụ.
- [JMHSample_10_ConstantFold](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java): đầu vào `final`, constant folding và dữ liệu trong trường trạng thái runtime.
- [JMH Core trên Maven Central](https://central.sonatype.com/artifact/org.openjdk.jmh/jmh-core): phiên bản dependency được xuất bản.
