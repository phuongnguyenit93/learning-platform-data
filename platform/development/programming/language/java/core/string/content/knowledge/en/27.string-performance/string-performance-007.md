# Đo hiệu năng String bằng JMH với warmup, chống bỏ mã và tránh gấp hằng

## 1. Vì sao cần JMH?

Các thao tác `String` như `indexOf`, `equals`, `substring` hoặc nối chuỗi chạy rất nhanh, nên phép đo thủ công dễ trở nên sai lệch. Xét đoạn **mã cố ý sai**:

~~~java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    "mississippi".indexOf('s');
}
System.out.println(System.nanoTime() - start);
~~~

Kết quả của `indexOf` không được sử dụng; JVM có thể loại công việc đó. Hơn nữa, đầu vào là literal cố định nên JVM có thể tính trước kết quả, thay vì thực hiện tìm kiếm một triệu lần. Dùng `nanoTime` không giúp khắc phục vấn đề nếu đoạn code được đo không còn thực thi như dự tính.

**JMH (Java Microbenchmark Harness)** của OpenJDK được thiết kế để đo microbenchmark Java/JVM. JMH điều phối các phép đo, các iteration, việc làm nóng (warmup), JVM fork, annotation processing và sử dụng kết quả tính toán. Nó giúp hạn chế ba bẫy trọng tâm:

1. **Warmup thiếu:** số đo bị trộn với nạp lớp, interpreter, JIT compilation, profiling và deoptimization.
2. **Dead-code elimination (DCE):** kết quả không được quan sát nên trình tối ưu bỏ luôn phép tính.
3. **Constant folding:** đầu vào là hằng, trình tối ưu trả một hằng kết quả thay vì thực hiện thuật toán cần đo.

**JMH không bảo đảm một benchmark thiết kế sai trở thành đúng.** Kết quả chỉ có ý nghĩa khi workload, dữ liệu, môi trường và cách đọc score được xác định rõ.

## 2. Vòng đời phép đo: fork, warmup, measurement

JMH chạy mỗi `@Benchmark` thông qua mã harness được tạo bởi annotation processor. Trong quá trình chạy, nó có thể khởi động các **fork JVM độc lập**; trong mỗi fork, nó chạy các warmup iteration rồi measurement iteration.

| Thành phần | Ý nghĩa |
| --- | --- |
| `@Benchmark` | Đánh dấu method chứa công việc cần đo. |
| `@Warmup` | Chạy workload để JVM có thời gian tối ưu, nhưng không đưa các iteration đó vào điểm đo chính. |
| `@Measurement` | Các iteration thu thập số liệu; trong mỗi iteration có nhiều lần gọi benchmark. |
| `@Fork` | Số JVM con tách biệt, giúp phát hiện khác biệt qua lần khởi động/runtime. |
| `@BenchmarkMode` | Chọn cách diễn giải score như AverageTime, Throughput hoặc SampleTime. |
| `@OutputTimeUnit` | Chọn đơn vị hiển thị như nano giây hoặc micro giây. |
| `@Threads` hoặc `-t` | Số worker thread cùng chạy benchmark. |

Ví dụ cấu hình annotation (fragment trong class benchmark):

~~~java
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
~~~

Ở cấu hình này, mỗi fork dùng 5 warmup iteration và 5 measurement iteration, mỗi iteration chạy khoảng một giây. Hai fork giúp quan sát biến thiên ở hai JVM riêng. Đây chỉ là **cấu hình khởi đầu**, không phải chứng minh JVM đã ổn định. Nếu score còn thay đổi xu hướng rõ ràng ở các iteration cuối, xem lại warmup, workload và môi trường.

JIT HotSpot có thể diễn giải bytecode, biên dịch ở nhiều mức và deoptimize khi giả định thay đổi. Chỉ đo lần chạy đầu có thể vô tình đo quá trình **làm nóng JVM** thay vì hiệu năng sau khi chương trình đã chạy lâu.

### Đọc đúng các mode

- `Mode.AverageTime` (`-bm avgt`) báo thời gian trung bình mỗi operation: ví dụ `ns/op`; nhỏ hơn thường tốt hơn khi mọi điều kiện khác như nhau.
- `Mode.Throughput` (`-bm thrpt`) báo số operation trong một đơn vị thời gian; cao hơn thường tốt hơn.
- `Mode.SampleTime` (`-bm sample`) lấy mẫu thời gian và có thể giúp xem phân bố/tail latency.
- `Mode.SingleShotTime` (`-bm ss`) phù hợp với một số trường hợp cần đo single-shot, không tương đương phép đo throughput ổn định.

Đừng so hai thuật toán với mode, đơn vị, thread count hay tập đầu vào khác nhau mà rút ra kết luận tốc độ.

## 3. Chống dead-code elimination

### Ví dụ sai: bỏ kết quả

~~~java
@Benchmark
public void wrongDiscardedResult() {
    text.indexOf(needle);
}
~~~

`String.indexOf` trả về một `int`. Nếu không ai dùng giá trị ấy và JVM thấy phép gọi không có hiệu ứng quan sát được, JIT **có thể** loại tính toán. Một score rất nhỏ chưa chứng minh `indexOf` thật sự nhanh.

### Cách 1: return kết quả

~~~java
@Benchmark
public int correctReturn() {
    return text.indexOf(needle);
}
~~~

JMH tiêu thụ giá trị mà method `@Benchmark` trả về. Với một kết quả, đây thường là cách đơn giản nhất để giữ công việc có thể quan sát.

### Cách 2: Blackhole

~~~java
@Benchmark
public void correctBlackhole(Blackhole bh) {
    int position = text.indexOf(needle);
    bh.consume(position);
}
~~~

`Blackhole` thuộc package `org.openjdk.jmh.infra`. Đối tượng được JMH cung cấp có thể tiêu thụ một hoặc nhiều kết quả để chống tối ưu bỏ công việc không mong muốn.

~~~java
@Benchmark
public void twoResults(Blackhole bh) {
    bh.consume(text.indexOf("a"));
    bh.consume(text.indexOf("Z"));
}
~~~

Các ví dụ là fragment trong class benchmark với các field/input thích hợp. Class hoàn chỉnh ở phần 7.

**Tránh dùng `System.out.println` hoặc logging trong đoạn đo để chống DCE:** chi phí I/O hoặc khóa log có thể nhiều hơn rất xa chi phí xử lý String. Cũng không nên thêm truy cập `volatile` ngẫu nhiên, bởi nó đưa ngữ nghĩa đồng bộ và overhead mới vào thí nghiệm.

`correctReturn` và `correctBlackhole` là hai cách sử dụng kết quả **của cùng phép tính**; không nên đối chiếu chúng như hai thuật toán cạnh tranh. Sink/harness có overhead riêng, nhất là với phép đo chỉ vài nano giây.

## 4. Tránh constant folding

Một benchmark vẫn có thể sai **dù đã return**:

~~~java
@Benchmark
public int wrongConstantFolded() {
    return "mississippi".indexOf('s');
}
~~~

Đầu vào là literal và kết quả luôn là `2`. JVM **có thể** rút gọn toàn bộ phép tìm kiếm thành trả hằng `2`; đo điều đó không đại diện cho thời gian tìm trên `String` nhận từ runtime. Đưa literal vào field `static final` hoặc bọc nó bằng helper không loại được nguy cơ này.

### Đầu vào qua State và Param

Đối với benchmark cần đo tìm kiếm trên chuỗi đã có, JMH cho phép tạo input ở thời điểm setup:

~~~java
@State(Scope.Thread)
public class InputState {
    @Param({"128", "4096"})
    public int length;

    String text;
    String needle;

    @Setup(Level.Trial)
    public void prepare() {
        char[] chars = new char[length];
        java.util.Arrays.fill(chars, 'a');
        text = new String(chars) + "Z";
        needle = "Z";
    }
}
~~~

- `@State(Scope.Thread)` cấp state riêng cho mỗi worker thread, tránh chia sẻ một đối tượng mutable ngoài ý muốn.
- `@Param` cho JMH thử các giá trị input khác nhau; `length` không phải hằng được nhúng trực tiếp vào benchmark method.
- `@Setup(Level.Trial)` chuẩn bị input trước khi đo, để ta chỉ đo tìm kiếm trên String đã có.
- Dữ liệu được cấp tại runtime giúp giảm đường constant folding phi thực tế.

Đây là ví dụ kỹ thuật về **cách cấp input**, chưa phải class độc lập. Mã hoàn chỉnh ở phần 7 tích hợp các annotation trên.

**Không đồng nghĩa “cấm JIT tối ưu”.** HotSpot vẫn có thể inline `indexOf`, dùng intrinsic, branch prediction và cache. Đây có thể là các tối ưu hợp lệ của ứng dụng thực sự.

### Chọn lúc setup

| Annotation | Dùng khi | Lưu ý |
| --- | --- | --- |
| `@Setup(Level.Trial)` | Đầu vào dùng suốt một trial, ví dụ chuỗi chuẩn bị để tìm kiếm. | Chi phí khởi tạo không tính vào thao tác đo. |
| `@Setup(Level.Iteration)` | Muốn làm mới đầu vào giữa các iteration. | Có thể thay đổi trạng thái cache/profile. |
| `@Setup(Level.Invocation)` | Buộc làm mới dữ liệu cho từng invocation. | Overhead có thể ảnh hưởng nghiêm trọng microbenchmark nhỏ; tránh dùng mặc định. |

Nếu mục đích là đo **tạo String**, thao tác tạo phải nằm trong method benchmark. Nếu chỉ đo **indexOf trên String đã có**, nên tạo String trước như trên.

## 5. Tạo project JMH Maven

Khuyến nghị dùng Maven archetype chính thức của JMH để có đủ JMH core, annotation processor và đóng gói runnable benchmark runner. Chỉ thêm annotation `@Benchmark` vào source rồi gọi method bằng `main` sẽ không tự tạo ra quá trình đo JMH.

Yêu cầu: cài Maven và JDK 17+. Trong thư mục làm việc riêng chưa có dự án Maven trùng tên, chạy:

~~~bash
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DarchetypeVersion=1.37 -DgroupId=org.example.bench -DartifactId=string-jmh-demo -Dversion=1.0-SNAPSHOT
cd string-jmh-demo
~~~

`1.37` là một phiên bản JMH **ghim cụ thể** cho ví dụ để người học có thể tái hiện; không có nghĩa đây luôn là phiên bản mới nhất.

Thêm file `src/main/java/org/example/bench/StringJmhPitfalls.java` với code ở phần 7. Có thể dùng project benchmark riêng tham chiếu module sản phẩm bằng Maven dependency. Khi đóng gói, chú ý giữ cấu hình annotation processing của archetype để JMH tạo runner và metadata benchmark.

Các API trong ví dụ dùng được trên Java 17+. Nếu project của bạn đặt compiler release/target khác, cấu hình Maven compiler phù hợp với JDK đang sử dụng.

## 6. Thiết kế workload tìm kiếm String

Ví dụ dùng `String.indexOf("Z")` trên chuỗi có `length` chữ `a` và ký tự `Z` ở cuối. Đây là một workload đơn giản:

- Với `length=128`, `indexOf("Z")` trả 128.
- Với `length=4096`, `indexOf("Z")` trả 4096.
- `@Param` kiểm tra hai kích thước, không gộp chúng thành một score.
- `@Setup` tạo String trước khi bắt đầu measurement.
- Benchmark tiêu thụ kết quả qua return hoặc Blackhole.

Workload này đại diện cho tìm token ở cuối **chuỗi ASCII có cấu trúc đều**. Nó **không** đại diện cho mọi `String.indexOf`: ứng dụng thực có thể có trường hợp match ở đầu, không match, input Unicode, độ dài hoặc phân bố ký tự khác. Benchmark có ý nghĩa phải gắn với tập input và một câu hỏi rõ ràng.

## 7. Benchmark hoàn chỉnh chạy trên Java 17+

File: **`src/main/java/org/example/bench/StringJmhPitfalls.java`**.

~~~java
package org.example.bench;

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
import org.openjdk.jmh.infra.Blackhole;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(2)
public class StringJmhPitfalls {

    @Param({"128", "4096"})
    public int length;

    private String text;
    private String needle;

    @Setup(Level.Trial)
    public void prepare() {
        char[] chars = new char[length];
        Arrays.fill(chars, 'a');
        text = new String(chars) + "Z";
        needle = "Z";
    }

    // Phản ví dụ: JIT có thể xóa công việc nếu bỏ kết quả.
    @Benchmark
    public void wrongDiscardedResult() {
        text.indexOf(needle);
    }

    // Phản ví dụ: literal có thể được gấp thành hằng.
    @Benchmark
    public int wrongConstantFolded() {
        return "mississippi".indexOf('s');
    }

    // Cách giữ kết quả đơn giản nhất.
    @Benchmark
    public int correctReturn() {
        return text.indexOf(needle);
    }

    // Giữ kết quả qua Blackhole.
    @Benchmark
    public void correctBlackhole(Blackhole bh) {
        bh.consume(text.indexOf(needle));
    }
}
~~~

Đây là **benchmark JMH**, không cần viết `main`: mã runner của JMH được đóng gói trong `target/benchmarks.jar`. Nếu chỉ gọi `javac StringJmhPitfalls.java` mà không có dependency và annotation processor, biên dịch sẽ thất bại do thiếu class JMH.

| Method | Vấn đề hoặc biện pháp | Có dùng kết quả để quyết định tốc độ thuật toán? |
| --- | --- | --- |
| `wrongDiscardedResult` | Kết quả bị bỏ → nguy cơ DCE. | Không. |
| `wrongConstantFolded` | Toàn literal → nguy cơ constant folding. | Không. |
| `correctReturn` | Input qua state, return được JMH xử lý. | Có thể, với workload đúng đã mô tả. |
| `correctBlackhole` | Input qua state, Blackhole tiêu thụ. | Có thể, nhưng không so riêng overhead sink như một thuật toán. |

Hai method có tiền tố `wrong` chỉ là **minh họa vì sao benchmark có thể báo score đánh lừa**. Mã này đo `indexOf` trên String đã có; nếu cần đo cả tạo String/GC, hãy viết workload khác với các phép cấp phát trong method cần đo.

## 8. Biên dịch, chạy và đọc JMH report

Trong thư mục Maven project vừa tạo:

~~~bash
mvn clean verify
java -jar target/benchmarks.jar StringJmhPitfalls -wi 5 -i 5 -w 1s -r 1s -f 2 -t 1 -bm avgt -tu ns
~~~

Lệnh thứ hai lọc các method thuộc `StringJmhPitfalls` và chạy với:

| Cờ | Ý nghĩa |
| --- | --- |
| `-wi 5` | 5 warmup iterations. |
| `-w 1s` | Khoảng 1 giây mỗi warmup iteration. |
| `-i 5` | 5 measurement iterations. |
| `-r 1s` | Khoảng 1 giây mỗi measurement iteration. |
| `-f 2` | 2 JVM fork riêng. |
| `-t 1` | 1 worker thread. |
| `-bm avgt` | Average time mỗi operation. |
| `-tu ns` | Đơn vị nano giây. |

Với 4 benchmark method × 2 cấu hình `length` × 2 forks, cấu hình này thực sự tốn thời gian do mỗi fork chạy warmup và measurement nhiều giây. Nếu chỉ muốn xác nhận project/build có thể chạy, giảm số iteration/thời lượng **cho smoke test**; khi báo cáo hiệu năng, dùng cấu hình đo đủ tin cậy.

JMH in quá trình warmup, đo và kết quả với các cột như `Benchmark`, `(length)`, `Mode`, `Cnt`, `Score`, `Error`, `Units`. Ở đây `Score` thường biểu thị `ns/op`; `Error` thể hiện mức bất định JMH ước lượng từ dữ liệu quan sát. **Không có một stdout số ns/op chính xác cố định** giữa các máy, JDK hay lần chạy. Không được bịa kết quả benchmark trước khi thật sự đo.

Lưu kết quả có cấu trúc:

~~~bash
java -jar target/benchmarks.jar StringJmhPitfalls.correctReturn -wi 5 -i 5 -w 1s -r 1s -f 2 -t 1 -bm avgt -tu ns -rf json -rff jmh-results.json
~~~

Lệnh trên chỉ chạy `correctReturn`, xuất báo cáo JSON. Khi so sánh số liệu về sau, ghi lại JDK vendor/version, JVM flags, phiên bản JMH, loại CPU, hệ điều hành, thread count, GC, chế độ điện năng, phiên bản code và input.

## 9. Các lỗi thực nghiệm ngoài warmup/DCE/folding

### Tối ưu hợp lệ của JVM

JIT có thể inline method hoặc dùng intrinsic cho thao tác `String`. Những tối ưu này có thể là đường thực thi thực tế, vì vậy đừng mặc định vô hiệu hóa mọi tối ưu. Nhưng nếu công việc không được dùng, JIT có thể **loại cả thuật toán**; đó là lỗi benchmark.

**Loop-invariant code motion** có thể đẩy tính toán không đổi ra khỏi vòng lặp; **escape analysis/scalar replacement** có thể khiến một đối tượng tạm không cần cấp phát trên heap. Benchmark có đối tượng được tạo rồi không dùng có thể báo chi phí thấp một cách vô nghĩa so với kịch bản thật.

### GC, cache và thread

- JMH không cách ly hoàn toàn CPU khỏi tải nền, cache, branch prediction, nhiệt độ hoặc thay đổi tần số xung.
- `@State(Scope.Benchmark)` có thể chia sẻ state giữa các thread. Nếu không định đo tranh chấp, dùng `Scope.Thread` như mẫu và `-t 1` khi học cơ bản.
- `@Setup(Level.Invocation)` có overhead; dùng nó cho mọi benchmark nhỏ thường làm méo số liệu.
- Nếu mục tiêu liên quan allocation, có thể thử profiler `-prof gc` để bổ sung thông tin GC/allocation; đọc theo ý nghĩa profiler, không suy ra chỉ từ score.
- Khi một invocation cố ý xử lý N phần tử, nên mô tả đúng mỗi operation gồm gì; `@OperationsPerInvocation(N)` chỉ thích hợp khi N được xác định chính xác và cố định.

### Dữ liệu không đại diện

Đo trên một `String` lặp chữ `a` giúp học JMH nhưng không đủ đại diện cho log đa ngôn ngữ, đường dẫn URL, chuỗi Unicode, token đầu/cuối hoặc trường hợp không tìm thấy. Muốn đo ảnh hưởng của độ dài, xác suất match, bộ chữ, kích thước cache, hãy đưa từng chiều vào `@Param` hoặc một workload được định nghĩa rõ.

## 10. Quy trình thiết kế và diễn giải benchmark có ích

1. **Đặt câu hỏi:** đo tìm kiếm, dựng chuỗi hay nối chuỗi? Đưa đúng thao tác vào method benchmark.
2. **Xác minh correctness:** các phương án so sánh cần cho cùng kết quả trên cùng input. JMH không thay thế unit test.
3. **Thiết kế input:** dùng state/param runtime, thử vài kích thước và kịch bản đại diện.
4. **Giữ kết quả sống:** return hoặc `Blackhole.consume`; tránh log hay I/O.
5. **Loại nguy cơ gấp hằng phi thực tế:** không benchmark một biểu thức literal cố định rồi suy rộng.
6. **Làm nóng, đo, fork:** dùng đủ iteration/thời lượng để quan sát ổn định và biến thiên.
7. **Bảo đảm điều kiện tương đương:** cùng JDK, flags, máy, thread count, input, mode và đơn vị.
8. **Đọc score cùng error:** tránh tuyên bố thắng nếu khác biệt quá nhỏ so với nhiễu.
9. **Đối chiếu với ứng dụng thật:** microbenchmark đo một điểm rất nhỏ; latency/throughput end-to-end còn phụ thuộc nhiều tầng và GC.

### Dấu hiệu cần nghi ngờ

| Quan sát | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Method bỏ kết quả nhanh ngang benchmark rỗng | DCE. | Dùng return hoặc Blackhole. |
| Phép tìm kiếm literal “nhanh bất thường” | Constant folding. | Dùng input từ state runtime. |
| Iteration đầu chậm rồi giảm rõ rệt | JVM vẫn warmup/JIT. | Tăng warmup, xem từng iteration/fork. |
| Fork dao động mạnh | GC, tải CPU, profile hoặc môi trường khác. | Kiểm tra môi trường, chạy lại, phân tích biến thiên. |
| Thêm println làm score tăng vọt | Benchmark đo I/O. | Loại log khỏi vùng đo. |
| Hai kết quả rất sát nhau, error chồng lấn | Tín hiệu nhỏ so với nhiễu. | Không kết luận quá mức; điều chỉnh thí nghiệm. |

## 11. Câu hỏi tự kiểm tra

**1. Dùng `System.nanoTime` và vòng lặp triệu lần đã đủ chính xác chưa?** Chưa. Compiler có thể xóa/gấp mã và phép đo chưa kiểm soát warmup/fork.

**2. `@Warmup(iterations=5)` có chắc tạo steady state?** Không. Cần xem xu hướng qua iteration và nhiều fork.

**3. `return "mississippi".indexOf('s')` đã chống DCE, còn bẫy nào?** Constant folding, vì kết quả có thể được tính trước là `2`.

**4. Khi nào dùng Blackhole?** Khi muốn JMH tiêu thụ một hoặc nhiều giá trị được tính trong benchmark.

**5. Đo `indexOf` trên chuỗi sẵn có thì tạo chuỗi ở đâu?** Thường ở `@Setup(Level.Trial)`, ngoài thời gian invocation cần đo.

**6. Vì sao không có stdout ns/op duy nhất cho ví dụ?** JMH đo runtime thực, phụ thuộc máy, JVM, input, tải hệ thống và sự tối ưu.

**7. Có nên so `correctReturn` với `correctBlackhole` để chọn thuật toán nhanh?** Không. Chúng cùng làm một phép tính và chỉ khác cách sink nhận kết quả.

## Tài liệu tham khảo

- [OpenJDK JMH — README](https://github.com/openjdk/jmh/blob/master/README.md): tạo project benchmark bằng Maven archetype, runner và lệnh build.
- [JMHSample_08_DeadCode](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java): ví dụ dead-code elimination.
- [JMHSample_09_Blackholes](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_09_Blackholes.java): tiêu thụ kết quả benchmark.
- [JMHSample_10_ConstantFold](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java): nguy cơ constant folding.
- [JMH 1.37 — Maven Central](https://central.sonatype.com/artifact/org.openjdk.jmh/jmh-core/1.37): phiên bản cố định trong ví dụ.
