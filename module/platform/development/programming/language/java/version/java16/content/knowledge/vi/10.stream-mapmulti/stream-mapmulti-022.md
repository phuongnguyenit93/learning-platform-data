# Đo cấp phát và thời gian trước khi kết luận mapMulti nhanh hơn flatMap

`Stream.mapMulti` và `flatMap` đều có thể biến một phần tử nguồn thành không, một hoặc nhiều phần tử đầu ra. `mapMulti` thường giúp viết phép mở rộng dữ liệu bằng vòng lặp và Consumer trực tiếp; `flatMap` biểu diễn phép biến đổi bằng một Stream con. Cách viết khác nhau không đủ để kết luận cách nào nhanh hơn hoặc cấp phát ít hơn.

Muốn so sánh có ý nghĩa, hãy đo bằng workload đại diện, giữ ngữ nghĩa hai pipeline tương đương và quan sát cả thời gian lẫn lượng cấp phát. Với microbenchmark trên JVM, `JMH (Java Microbenchmark Harness)` là công cụ phù hợp hơn việc tự đo bằng `System.nanoTime()`.

## 1. Vì sao không thể kết luận chỉ từ hình dạng API?

`flatMap` thường tạo Stream con cho mỗi phần tử nguồn. `mapMulti` nhận Consumer để phát kết quả trực tiếp trong mapper. Điều này có thể làm thay đổi chi phí tạo đối tượng và cách pipeline được triển khai.

Tuy nhiên, hiệu năng thực tế còn phụ thuộc:

- Số phần tử nguồn.
- Số phần tử đầu ra từ mỗi phần tử nguồn (fan-out).
- Logic tạo từng phần tử đầu ra.
- Kiểu dữ liệu: object Stream hay primitive Stream.
- Các thao tác trung gian và terminal operation phía sau.
- JDK, JVM, garbage collector, phần cứng và dữ liệu đầu vào.
- Khả năng tối ưu của JIT compiler sau warmup.

Một pipeline chỉ xây dựng Stream mà không có terminal operation chưa thực hiện phần lớn công việc xử lý dữ liệu. Vì vậy, benchmark phải tiêu thụ kết quả bằng một terminal operation thực tế như `sum()`, `toArray()` hoặc `toList()`.

## 2. Dùng JMH thay cho phép đo nanoTime tự viết

Đo thời gian bằng một vòng lặp `System.nanoTime()` dễ bị ảnh hưởng bởi các yếu tố như:

- JVM chưa warmup và JIT chưa tối ưu mã.
- Dead-code elimination nếu kết quả không được sử dụng.
- Garbage collection xảy ra không đều.
- Chi phí tạo dữ liệu hoặc khởi tạo nằm lẫn trong vùng đo.
- Tần số CPU, tiến trình nền và tải hệ thống thay đổi.
- Một lần chạy duy nhất không đại diện cho hiệu năng ổn định.

JMH cung cấp cơ chế benchmark có warmup, measurement iterations, fork JVM và cách tiêu thụ kết quả để giảm các sai lệch phổ biến.

Có thể tạo project benchmark từ JMH Maven archetype hoặc cấu hình Maven/Gradle tương đương. Với Maven, cần thư viện lõi và annotation processor:

```xml
<dependencies>
    <dependency>
        <groupId>org.openjdk.jmh</groupId>
        <artifactId>jmh-core</artifactId>
        <version>${jmh.version}</version>
    </dependency>
    <dependency>
        <groupId>org.openjdk.jmh</groupId>
        <artifactId>jmh-generator-annprocess</artifactId>
        <version>${jmh.version}</version>
        <scope>provided</scope>
    </dependency>
</dependencies>
```

Khai báo property `jmh.version` bằng một phiên bản JMH ổn định tương thích với JDK và hệ thống build của dự án. Cấu hình đóng gói cần tạo executable benchmark JAR có entry point `org.openjdk.jmh.Main`; project được sinh từ archetype JMH đã thiết lập sẵn phần này.

## 3. Nguyên tắc giữ hai phép đo tương đương

Trước khi đo, hãy kiểm tra hai pipeline thực hiện cùng một công việc:

| Yếu tố | Yêu cầu khi so sánh |
|---|---|
| Nguồn | Cùng dữ liệu, cùng thứ tự và cùng số phần tử |
| Fan-out | Mỗi phần tử nguồn phát cùng số lượng đầu ra |
| Giá trị | Hai cách tạo ra cùng tập giá trị |
| Thứ tự | Cùng yêu cầu encounter order |
| Xử lý lỗi | Cùng chính sách khi đầu vào không hợp lệ |
| Terminal operation | Cùng phép tiêu thụ và kiểu kết quả |
| Chế độ chạy | Cùng tuần tự hoặc cùng parallel |
| Môi trường | Cùng JDK, JVM flags, heap và máy chạy |

Không so sánh `mapMulti` tuần tự với `flatMap` song song, hoặc một pipeline trả về primitive với pipeline phải boxing thành wrapper. Khi thay đổi nhiều yếu tố cùng lúc, kết quả không cho biết khác biệt đến từ API nào.

Cũng cần đo đúng kiểu API đang dùng trong ứng dụng. `Stream<T>.mapMulti` và `Stream<T>.flatMap` là cặp so sánh cho reference Stream; `IntStream.mapMulti` và `IntStream.flatMap` là cặp khác cho primitive Stream.

## 4. Benchmark reference Stream: mapMulti và flatMap

Ví dụ dưới đây dùng cùng nguồn `List<Integer>`. Với mỗi số, hai pipeline đều phát các giá trị từ `value` đến `value + fanOut - 1`, sau đó tính tổng dưới dạng `long`.

```java
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.stream.IntStream;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
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
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(3)
public class MapMultiVsFlatMapBenchmark {

    @Param({"0", "1", "4", "16"})
    public int fanOut;

    private List<Integer> source;

    @Setup
    public void setup() {
        source = IntStream.range(0, 10_000)
            .boxed()
            .toList();
    }

    @Benchmark
    public long flatMapReference() {
        return source.stream()
            .flatMap(value ->
                IntStream.range(0, fanOut)
                    .mapToObj(offset -> value + offset)
            )
            .mapToLong(Integer::longValue)
            .sum();
    }

    @Benchmark
    public long mapMultiReference() {
        return source.stream()
            .<Integer>mapMulti((value, emit) -> {
                for (int offset = 0; offset < fanOut; offset++) {
                    emit.accept(value + offset);
                }
            })
            .mapToLong(Integer::longValue)
            .sum();
    }
}
```

Các điểm quan trọng:

- `@Setup` tạo dữ liệu ngoài phần đo của từng benchmark invocation.
- `@Param` chạy cùng benchmark với nhiều fan-out khác nhau.
- `@Warmup` cho JVM thời gian khởi động và tối ưu mã.
- `@Measurement` quy định các vòng đo.
- `@Fork(3)` chạy các fork JVM riêng để giảm ảnh hưởng trạng thái của một tiến trình.
- Cả hai phương thức trả về tổng kiểu `long` để kết quả được sử dụng.
- Cả hai pipeline đều kết thúc bằng `mapToLong(...).sum()`.

Trong cặp reference Stream này, cả hai đều tạo đầu ra `Integer`. Phép cộng `value + offset` tạo giá trị `int` rồi boxing khi phát qua `Consumer<Integer>` hoặc khi tạo phần tử của Stream con. Phần boxing đó là một phần workload đang được đo, không được bỏ qua khi diễn giải kết quả.

## 5. Benchmark primitive Stream riêng biệt

Nếu ứng dụng thực hiện phép toán số học, hãy đo thêm cặp primitive Stream. Ví dụ dưới đây chuyển cùng nguồn wrapper sang `IntStream` rồi so sánh `flatMap` và `mapMulti` trên kiểu `int`:

```java
@Benchmark
public long flatMapPrimitive() {
    return source.stream()
        .mapToInt(Integer::intValue)
        .flatMap(value ->
            IntStream.range(0, fanOut)
                .map(offset -> value + offset)
        )
        .asLongStream()
        .sum();
}

@Benchmark
public long mapMultiPrimitive() {
    return source.stream()
        .mapToInt(Integer::intValue)
        .mapMulti((value, emit) -> {
            for (int offset = 0; offset < fanOut; offset++) {
                emit.accept(value + offset);
            }
        })
        .asLongStream()
        .sum();
}
```

Đặt hai phương thức này trong cùng lớp benchmark ở mục trước. Chúng dùng cùng dữ liệu, cùng phép chuyển wrapper sang primitive và cùng terminal operation `asLongStream().sum()`.

Trong cặp này, các phần tử đầu ra là `int` và được xử lý trong `IntStream`. Không có boxing đầu ra thành `Integer` trong hợp đồng phần tử của pipeline. Bước `mapToInt(Integer::intValue)` vẫn unbox dữ liệu nguồn vì nguồn ban đầu là `List<Integer>`.

Không gộp kết quả reference và primitive thành một kết luận chung. Chúng là hai workload khác nhau và có thể cho thấy trade-off khác nhau.

## 6. Đo lượng cấp phát bằng JMH GC profiler

Để quan sát lượng cấp phát, chạy benchmark với profiler `gc`:

```bash
java -jar target/benchmarks.jar MapMultiVsFlatMapBenchmark -prof gc
```

JMH GC profiler cung cấp các chỉ số hữu ích, trong đó:

| Chỉ số | Ý nghĩa |
|---|---|
| `gc.alloc.rate.norm` | Lượng cấp phát chuẩn hóa trên mỗi benchmark operation, thường hiển thị bytes/op |
| `gc.alloc.rate` | Tốc độ cấp phát theo thời gian, thường là MB/sec |
| `gc.count` | Số lần garbage collection quan sát được |
| `gc.time` | Tổng thời gian garbage collection được profiler ghi nhận |

Khi so sánh lượng cấp phát của hai phương thức, `gc.alloc.rate.norm` thường hữu ích hơn `gc.alloc.rate` vì nó biểu diễn lượng byte trên mỗi operation. Tốc độ cấp phát theo giây còn phụ thuộc benchmark xử lý được bao nhiêu operation trong một giây.

Lượng cấp phát đo được bao gồm toàn bộ pipeline và terminal operation trong benchmark. Nó không tự phân loại chính xác bao nhiêu byte đến từ Stream con, wrapper, buffer hoặc phần logic khác. Muốn xác định nguồn cấp phát cụ thể, cần profiling sâu hơn bằng công cụ phù hợp như Java Flight Recorder hoặc profiler allocation.

## 7. Thay đổi fan-out để tìm vùng workload phù hợp

Fan-out là số lượng phần tử đầu ra mà một phần tử nguồn tạo ra. Đây là biến quan trọng khi so sánh hai API.

Ví dụ tham số:

```java
@Param({"0", "1", "4", "16"})
public int fanOut;
```

Có thể mở rộng dải đo theo workload thực tế, chẳng hạn:

- `0`: mapper không phát kết quả.
- `1`: mỗi phần tử nguồn tạo đúng một phần tử.
- `4`: mở rộng thành nhóm nhỏ.
- `16`: mở rộng thành nhóm lớn hơn.

Không chọn tham số chỉ để làm một API có lợi thế. Hãy lấy fan-out từ dữ liệu thực tế hoặc các trường hợp biên có ý nghĩa trong ứng dụng.

Khi fan-out tăng, tổng số phần tử downstream cũng tăng. Cần quan sát cả thời gian và bytes/op để hiểu liệu chi phí đến từ tạo Stream con, boxing, buffer, xử lý Consumer hay terminal operation.

Nếu ứng dụng có phân bố fan-out không đồng đều, hãy tạo dataset có phân bố tương tự thay vì chỉ dùng một fan-out cố định cho mọi phần tử.

## 8. Chạy benchmark và đọc kết quả

Sau khi đóng gói executable JAR, có thể chạy tất cả benchmark trong lớp:

```bash
java -jar target/benchmarks.jar MapMultiVsFlatMapBenchmark -prof gc
```

Hoặc chạy một cặp phương thức cụ thể:

```bash
java -jar target/benchmarks.jar ".*(flatMapReference|mapMultiReference).*" -prof gc
```

Nếu cần chỉ định fan-out:

```bash
java -jar target/benchmarks.jar MapMultiVsFlatMapBenchmark -p fanOut=0,1,4,16 -prof gc
```

JMH sẽ in kết quả thời gian theo đơn vị đã cấu hình, ví dụ `us/op`, cùng các chỉ số profiler nếu bật `-prof gc`.

Khi đọc bảng kết quả:

1. So sánh hai phương thức trong cùng cặp và cùng giá trị fan-out.
2. Kiểm tra độ lệch giữa các fork và độ ổn định của các iteration.
3. Đọc thời gian trung bình cùng sai số/độ phân tán mà JMH báo cáo.
4. So sánh `gc.alloc.rate.norm` theo bytes/op.
5. Kiểm tra số lần GC và thời gian GC để hiểu áp lực bộ nhớ.
6. Lặp lại trên workload và JDK mà ứng dụng thực sự sử dụng.

Không chỉ nhìn một con số thấp nhất. Nếu chênh lệch nhỏ hơn mức dao động giữa các lần chạy, dữ liệu chưa đủ mạnh để kết luận.

## 9. Những sai lầm làm benchmark mất giá trị

**Không có terminal operation.** Stream là lazy; chỉ tạo pipeline không đo đầy đủ việc xử lý phần tử. Hãy tiêu thụ kết quả như ứng dụng thật.

**Không warmup.** Đo ngay lần đầu có thể phản ánh interpreter hoặc mã chưa được JIT tối ưu. Dùng warmup iterations và nhiều fork.

**Đo một lần duy nhất.** Một lần chạy có thể bị ảnh hưởng bởi GC, tiến trình nền hoặc trạng thái CPU. Dùng nhiều measurement iterations và fork.

**Kết quả không được sử dụng.** JIT có thể loại bỏ công việc không ảnh hưởng tới kết quả quan sát. Trả về kết quả benchmark hoặc dùng `Blackhole` khi cần.

**Đưa setup vào vùng đo.** Tạo danh sách hoặc đọc file trong benchmark method nếu đó không phải workload cần đo sẽ làm nhiễu phép so sánh. Tạo dữ liệu cố định trong `@Setup`.

**Hai pipeline không tương đương.** Khác fan-out, kiểu đầu ra, thứ tự hoặc terminal operation sẽ khiến kết quả không còn là so sánh riêng giữa hai API.

**Chỉ đo thời gian mà bỏ qua allocation.** Hai pipeline có thể có thời gian gần nhau nhưng áp lực GC khác nhau. Dùng `-prof gc` khi lượng cấp phát là câu hỏi cần trả lời.

**Chỉ đo allocation mà bỏ qua thời gian.** Ít cấp phát hơn không tự động đồng nghĩa nhanh hơn. Chi phí tính toán, truy cập bộ nhớ và tối ưu JIT vẫn ảnh hưởng thời gian.

**Trộn sequential và parallel.** Benchmark parallel cần workload đủ lớn và phải được đo như một kịch bản riêng. Không so sánh một pipeline sequential với một pipeline parallel rồi quy kết chênh lệch cho `mapMulti`.

**Chỉ chạy trên một JDK.** Hành vi tối ưu hóa có thể thay đổi giữa các phiên bản JVM. Đo trên JDK triển khai thực tế và ghi lại phiên bản dùng cho từng kết quả.

## 10. Khi nào cần profiling sâu hơn?

JMH trả lời câu hỏi phương thức nào có thời gian hoặc lượng cấp phát trung bình thấp hơn trong benchmark đã thiết kế. Nếu cần biết đối tượng nào được cấp phát, call path nào nóng hoặc GC tác động thế nào trong ứng dụng, hãy dùng profiler.

Các lựa chọn phổ biến:

- **Java Flight Recorder (JFR):** thu thập sự kiện runtime như allocation, GC, CPU và thread với overhead thường thấp khi cấu hình phù hợp.
- **Java Mission Control (JMC):** phân tích recording JFR để tìm allocation hotspot, CPU hotspot và hành vi GC.
- **Async-profiler:** lấy mẫu CPU, allocation và một số sự kiện runtime khác khi cần phân tích sâu.

Profiler cũng có overhead và cách lấy mẫu riêng. Không dùng số liệu từ một phiên profiling có instrumentation nặng để thay thế kết quả benchmark thuần mà không ghi rõ cách đo.

Nên dùng JMH để so sánh có kiểm soát, sau đó dùng profiler để tìm nguyên nhân khi thấy khác biệt có ý nghĩa.

## 11. Benchmark trên JDK nào?

`mapMulti` được giới thiệu trong Java 16. Khi đánh giá một ứng dụng hiện đại:

- Chạy benchmark trên JDK đang dùng để triển khai ứng dụng.
- Nếu cần so sánh tác động của phiên bản JVM, chạy cùng benchmark trên các JDK mục tiêu bằng cùng dữ liệu và cấu hình tương đương.
- Ghi rõ phiên bản JDK, JVM flags, GC, CPU, hệ điều hành và phiên bản JMH.
- Không suy luận hiệu năng của JDK hiện tại từ kết quả cũ trên Java 16.

Mã benchmark ở trên dùng `List.toList()`, API có từ Java 16. Nếu cần chạy trên JDK cũ hơn, hãy điều chỉnh cách tạo danh sách cho tương thích và ghi nhận thay đổi đó trong cấu hình benchmark.

## 12. Quy trình đưa ra kết luận

Có thể dùng quy trình sau trước khi thay `flatMap` bằng `mapMulti` hoặc ngược lại:

1. Xác định pipeline thực tế và số lượng đầu ra trên mỗi phần tử.
2. Viết hai phiên bản có cùng ngữ nghĩa và cùng terminal operation.
3. Kiểm tra kết quả hai phiên bản tương đương trước khi benchmark.
4. Dùng JMH với warmup, measurement và nhiều fork.
5. Đo thời gian và bytes/op bằng GC profiler.
6. Lặp lại với fan-out và kích thước dữ liệu đại diện.
7. Chạy trên JDK triển khai thực tế.
8. Dùng JFR hoặc profiler sâu hơn khi cần tìm nguyên nhân cấp phát và CPU.
9. Chỉ kết luận khi chênh lệch ổn định và đủ lớn để có ý nghĩa với ứng dụng.

Nếu hai phương thức có kết quả gần nhau trong sai số đo, hãy ưu tiên cách viết dễ đọc và phù hợp với hình dạng dữ liệu. Nếu một phương thức giảm cấp phát nhưng không cải thiện thời gian, cân nhắc xem áp lực GC có phải vấn đề thực tế của ứng dụng hay không.

## 13. Ghi nhớ

- Không thể kết luận `mapMulti` nhanh hơn `flatMap` chỉ từ hình dạng API.
- Dùng JMH thay cho một vòng lặp `System.nanoTime()` tự viết.
- Benchmark phải có terminal operation để pipeline thực sự xử lý dữ liệu.
- Hai pipeline cần cùng nguồn, fan-out, giá trị, thứ tự, kiểu dữ liệu và terminal operation.
- Đo reference Stream và primitive Stream thành các cặp riêng.
- Dùng warmup, measurement iterations và nhiều fork để giảm sai lệch.
- Dùng `-prof gc` và đọc `gc.alloc.rate.norm` để so sánh bytes/op.
- Allocation profiler đo toàn bộ benchmark operation, không tự quy allocation cho riêng `mapMulti` hay `flatMap`.
- Thử nhiều fan-out và dữ liệu có phân bố gần workload thực tế.
- Ghi lại JDK, JVM flags, GC, phần cứng và phiên bản JMH.
- Dùng JFR hoặc profiler sâu hơn khi cần tìm nguyên nhân.
- Chỉ kết luận từ kết quả ổn định trên môi trường triển khai mục tiêu.

`mapMulti` có thể là cách biểu đạt phù hợp cho mapper phát nhiều kết quả trực tiếp, còn `flatMap` phù hợp khi phép biến đổi tự nhiên tạo Stream con. Đo thời gian và allocation bằng JMH trên workload tương đương sẽ cho cơ sở thực tế để chọn API, thay vì giả định một phương thức luôn nhanh hơn.

