# Thiết kế phép đo có warmup và đầu vào đại diện để tránh kết luận sai

JIT compiler của JVM cần thời gian quan sát chương trình trước khi tạo mã máy được tối ưu. Một benchmark quá ngắn, dùng dữ liệu quá đơn giản hoặc chỉ chạy một lần có thể đo nhầm giai đoạn khởi động, đo cả chi phí chuẩn bị dữ liệu hoặc khiến compiler loại bỏ phần tính toán không được sử dụng.

Muốn đánh giá một thay đổi hiệu năng trong Java hiện đại, cần thiết kế phép đo sao cho phản ánh đúng câu hỏi: đang đo cold-start hay steady-state, đo một method hay toàn bộ request, và dữ liệu thử có giống phân bố đầu vào thực tế hay không. JMH giúp kiểm soát warmup, measurement, fork và input; JFR giúp quan sát hành vi JVM trong workload tích hợp.

Bài học này trình bày cách xây dựng benchmark có thể lặp lại, chọn đầu vào đại diện, tránh các lỗi phổ biến do JIT và diễn giải kết quả với giới hạn phù hợp.

## 1. Vì sao benchmark Java dễ cho kết quả sai?

Một phép đo đơn giản thường có dạng:

~~~java
long start = System.nanoTime();
runTask();
long elapsed = System.nanoTime() - start;
~~~

Cách đo này hữu ích để đo một khoảng thời gian trong ứng dụng, nhưng chưa đủ để xây dựng microbenchmark đáng tin cậy. Kết quả có thể bị ảnh hưởng bởi:

- JVM đang ở interpreter hoặc tầng biên dịch thấp khi bắt đầu đo.
- JIT chưa thu thập đủ profile để tối ưu method.
- Class loading, linking và khởi tạo static xảy ra trong khoảng đo.
- Garbage collection hoặc compilation thread chạy đồng thời.
- CPU frequency, scheduler, cache và tải nền thay đổi.
- Compiler loại bỏ phép tính vì kết quả không được quan sát.
- Dữ liệu thử quá đơn giản khiến compiler tối ưu theo một trường hợp không đại diện.
- Benchmark chạy một lần nên không thể phân biệt hiệu ứng thật với nhiễu.

Ví dụ, đo một method trong vài microsecond ngay sau khi khởi chạy JVM có thể phản ánh interpreter, class loading và JIT compilation thay vì chi phí steady-state của method. Ngược lại, chỉ đo sau warmup với dữ liệu luôn giống nhau có thể tạo profile quá thuận lợi so với production.

Trước khi viết benchmark, hãy xác định rõ đại lượng cần đo và giai đoạn hoạt động của ứng dụng.

## 2. Phân biệt cold-start với steady-state

Hai mục tiêu này cần hai phương pháp đo khác nhau.

| Mục tiêu | Điều cần đo | Cách tiếp cận |
| --- | --- | --- |
| Cold-start | Thời gian từ khi launch process đến khi ứng dụng sẵn sàng | Khởi chạy JVM mới cho mỗi lần đo; đo từ bên ngoài process hoặc bằng startup instrumentation |
| Warm-up | Thời gian và số lần thực thi cần để code đạt hành vi ổn định | Theo dõi nhiều iteration và compilation profile |
| Steady-state | Hiệu năng sau khi JVM đã nạp class, thu thập profile và tối ưu code nóng | JMH với warmup, measurement và nhiều fork |
| End-to-end request | Thời gian xử lý request qua framework, network và dependency | Load test hoặc tracing ở tầng ứng dụng |

JMH được thiết kế chủ yếu cho microbenchmark và có cơ chế warmup để đo code sau giai đoạn khởi động. Nếu mục tiêu là thời gian startup của ứng dụng, không nên lấy điểm số steady-state từ JMH làm đại diện.

Cold-start có thể phụ thuộc classpath, module loading, dependency injection, kết nối database, cache initialization và các tác vụ khởi động. Hãy đo toàn bộ process bằng một harness khởi chạy JVM mới nhiều lần và xác định rõ mốc “sẵn sàng” của ứng dụng.

## 3. Warmup giúp JIT quan sát và tối ưu code

HotSpot thường thực thi method ban đầu bằng interpreter và có thể biên dịch qua các tầng compiler. Với tiered compilation, JVM thu thập thông tin thực thi, biên dịch ở mức phù hợp và có thể nâng cấp method nóng lên mức tối ưu cao hơn.

Trong warmup, JVM có cơ hội:

- Nạp và khởi tạo class được dùng trong workload.
- Thu thập call-site profile và branch profile.
- Biên dịch method nóng.
- Inline những lời gọi phù hợp.
- Tối ưu dựa trên kiểu dữ liệu và đường thực thi thường gặp.
- Ổn định một phần trạng thái cache và runtime.

Warmup không phải một con số cố định bảo đảm mọi method đều đã tối ưu. Nếu workload có nhiều đường code, một warmup chỉ chạy một nhánh có thể không đại diện cho những nhánh còn lại. Một số method hiếm có thể chưa nóng đủ để được biên dịch.

Vì vậy, warmup cần chạy cùng loại workload và phân bố đầu vào với giai đoạn measurement. Nếu production có nhiều loại request, warmup chỉ dùng một loại request có thể tạo profile không phù hợp.

### Chọn số iteration và thời lượng warmup

JMH cho phép khai báo warmup bằng annotation:

~~~java
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
~~~

Ví dụ này chạy năm iteration warmup, mỗi iteration một giây. Đây là cấu hình minh họa, không phải giá trị tối ưu cho mọi benchmark.

Cần xem xét:

- Method rất ngắn có thể cần nhiều iteration để thu thập đủ số lần gọi.
- Method nặng có thể cần thời gian iteration dài hơn để giảm ảnh hưởng của harness.
- Workload nhiều nhánh cần warmup các nhánh quan trọng.
- Benchmark có allocation hoặc GC đáng kể cần đủ thời gian để quan sát hành vi ổn định.
- Nếu score vẫn thay đổi mạnh qua các iteration, hãy tìm nguyên nhân thay vì tự động tăng warmup vô hạn.

Có thể xem log JMH và compilation log riêng khi nghi ngờ warmup chưa đủ. Không nên kết luận steady-state chỉ từ việc đã chạy một số iteration cố định.

## 4. Measurement và fork có vai trò gì?

Sau warmup, JMH chạy các measurement iteration để thu thập kết quả. Có thể khai báo:

~~~java
@Measurement(iterations = 8, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(3)
~~~

Trong ví dụ, JMH đo tám iteration, mỗi iteration một giây và chạy benchmark trong ba fork JVM riêng.

**Measurement iteration** cung cấp nhiều quan sát hơn để đánh giá độ dao động. **Fork** tạo process JVM mới, giúp giảm ảnh hưởng từ trạng thái compiler, profile, heap và class loading của một lần chạy trước.

Nếu không dùng fork, benchmark có thể chịu ảnh hưởng của các benchmark method chạy trước đó trong cùng JVM. Fork giúp cô lập trạng thái runtime tốt hơn, nhưng cũng làm tổng thời gian benchmark tăng.

Một số nguyên tắc:

- Dùng nhiều fork để kiểm tra tính lặp lại giữa các JVM.
- Không chỉ chọn fork có score đẹp nhất.
- Xem score, error và độ dao động giữa các lần chạy.
- Nếu kết quả giữa các fork khác nhau lớn, tìm nguyên nhân như CPU noise, profile khác nhau hoặc input chưa ổn định.
- Không tăng số iteration để che một benchmark có thiết kế sai.

## 5. Đầu vào phải đại diện cho workload thật

JIT tối ưu theo những gì JVM quan sát trong lúc chạy. Nếu benchmark luôn dùng một giá trị, một nhánh hoặc một kiểu object, compiler có thể tạo profile rất khác production.

Đầu vào đại diện cần xem xét nhiều đặc điểm:

| Đặc điểm | Ví dụ cần cân nhắc |
| --- | --- |
| Kích thước | Danh sách 10, 1.000 hay 100.000 phần tử |
| Phân bố giá trị | Gần đồng đều, lệch mạnh, nhiều giá trị lặp |
| Tỷ lệ nhánh | 50/50, 95/5 hoặc hầu hết cùng một nhánh |
| Tỷ lệ cache hit/miss | Cache nóng, cache lạnh, key mới |
| Kiểu dữ liệu | Một implementation hay nhiều implementation |
| Độ dài chuỗi | Ngắn, dài, Unicode và dữ liệu hỗn hợp |
| Collection | Kích thước, load factor, số lần resize |
| Tính hợp lệ | Dữ liệu hợp lệ, thiếu field, biên và lỗi |
| Tính đồng thời | Một thread, nhiều thread, tranh chấp tài nguyên |

Nếu ứng dụng production có 90% request đọc thành công và 10% request không tìm thấy dữ liệu, benchmark chỉ dùng trường hợp thành công sẽ không mô tả đầy đủ workload. Tương tự, nếu một call site nhận nhiều implementation khác nhau trong production, benchmark chỉ dùng một implementation có thể khiến JIT tối ưu theo profile đơn hình.

Đầu vào không cần sao chép dữ liệu nhạy cảm từ production. Có thể tạo dữ liệu tổng hợp có cùng kích thước, phân bố, tỷ lệ hit/miss và cấu trúc; cần ghi lại cách tạo để người khác tái lập phép đo.

## 6. Chuẩn bị dữ liệu ngoài phần được đo

Nếu câu hỏi là chi phí xử lý một mảng đã có sẵn, hãy tạo mảng trong setup thay vì tạo mới trong benchmark method. Như vậy, phép đo tập trung vào xử lý dữ liệu.

JMH cung cấp các mức setup như:

- **Level.Trial:** chạy một lần cho mỗi trial, phù hợp chuẩn bị dữ liệu dùng chung trong suốt trial.
- **Level.Iteration:** chạy trước mỗi measurement hoặc warmup iteration.
- **Level.Invocation:** chạy trước mỗi lần gọi benchmark; chỉ dùng khi thực sự cần reset trạng thái cho từng invocation vì thao tác này có thể làm thay đổi cache và tăng chi phí harness.

Không đưa chi phí setup ra ngoài phép đo nếu mục tiêu thực tế là đo toàn bộ thao tác bao gồm chuẩn bị dữ liệu. Chẳng hạn, nếu request production phải parse JSON rồi mới xử lý, benchmark end-to-end nên tính cả parse. Có thể tạo hai benchmark riêng: một đo phần xử lý lõi, một đo toàn bộ pipeline.

### Ví dụ tạo dữ liệu có phân bố kiểm soát

Đoạn code sau tạo mảng số nguyên có ba phân bố dấu khác nhau. Dữ liệu được chuẩn bị trước khi measurement bắt đầu:

~~~java
import java.util.SplittableRandom;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 8, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(3)
public class BranchBenchmark {
    @Param({"1024", "65536"})
    public int size;

    @Param({"mostly-positive", "balanced", "mostly-negative"})
    public String distribution;

    private int[] values;

    @Setup(Level.Trial)
    public void setup() {
        values = new int[size];
        SplittableRandom random = new SplittableRandom(0x5EEDL);

        int negativePercent;
        switch (distribution) {
            case "mostly-positive" -> negativePercent = 5;
            case "balanced" -> negativePercent = 50;
            case "mostly-negative" -> negativePercent = 95;
            default -> throw new IllegalArgumentException(distribution);
        }

        for (int i = 0; i < values.length; i++) {
            int magnitude = random.nextInt(1, 1001);
            boolean negative = random.nextInt(100) < negativePercent;
            values[i] = negative ? -magnitude : magnitude;
        }
    }

    @Benchmark
    public long branchBased() {
        long sum = 0;
        for (int value : values) {
            sum += value >= 0 ? value : -value;
        }
        return sum;
    }

    @Benchmark
    public long mathAbs() {
        long sum = 0;
        for (int value : values) {
            sum += Math.abs(value);
        }
        return sum;
    }
}
~~~

Hai phương thức thực hiện cùng phép tính trên cùng mảng. Giá trị đầu vào nằm trong khoảng -1000 đến 1000 nên không có trường hợp Integer.MIN_VALUE làm Math.abs(int) vẫn âm. Mỗi kết quả được trả về để JMH tiêu thụ, tránh việc toàn bộ phép tính bị loại bỏ như dead code.

Các tham số tạo ra nhiều trial với kích thước và phân bố khác nhau. Cấu hình này giúp kiểm tra xem kết quả có thay đổi khi tỷ lệ nhánh hoặc working set thay đổi hay không. Đây là ví dụ minh họa cách thiết kế benchmark; không nên mặc định phép dùng Math.abs nhanh hơn hoặc chậm hơn biểu thức điều kiện.

## 7. Tránh dead-code elimination và constant folding

JIT được phép loại bỏ phép tính không ảnh hưởng kết quả quan sát. Vì vậy, benchmark phải khiến kết quả của công việc được sử dụng.

Ví dụ không tốt:

~~~java
@Benchmark
public void badBenchmark() {
    int result = 100 * 200;
}
~~~

Kết quả không được sử dụng và các toán hạng là hằng số. Compiler có thể tính trước hoặc loại bỏ phần lớn công việc.

Cách tốt hơn là trả về kết quả:

~~~java
@Benchmark
public int calculate() {
    return calculateFrom(input);
}
~~~

Nếu benchmark có nhiều kết quả trung gian, có thể dùng **Blackhole**:

~~~java
@Benchmark
public void consumeResults(Blackhole blackhole) {
    blackhole.consume(calculateFrom(inputA));
    blackhole.consume(calculateFrom(inputB));
}
~~~

JMH cung cấp cơ chế chống dead-code elimination trong harness. Hãy ưu tiên trả kết quả hoặc dùng Blackhole thay vì tự tạo thủ thuật như ghi vào biến static hoặc in console.

Constant folding không phải lúc nào cũng là lỗi. Nếu production thực sự xử lý một hằng số đã biết tại compile time, đó có thể là tình huống cần đo. Nhưng nếu mục tiêu là đo thuật toán trên dữ liệu động, hãy cung cấp input đủ đa dạng và không để toàn bộ kết quả được xác định từ hằng số.

## 8. Tránh benchmark vòng lặp sai cách

Một lỗi thường gặp là gọi method cần đo hàng nghìn lần trong một benchmark invocation để “giảm overhead”:

~~~java
@Benchmark
public int badLoopBenchmark() {
    int result = 0;
    for (int i = 0; i < 10000; i++) {
        result += calculate(10);
    }
    return result;
}
~~~

Nếu mỗi lần gọi dùng cùng giá trị, JIT có thể inline, gộp hoặc tối ưu toàn bộ vòng lặp theo cách không giống một lời gọi thực tế. Việc tự lặp cũng làm thay đổi profile và có thể khiến compiler unroll loop.

Điều đó không có nghĩa mọi vòng lặp trong benchmark đều sai. Nếu nghiệp vụ thực sự xử lý một mảng hoặc collection, vòng lặp duyệt dữ liệu là một phần của operation cần đo, như ví dụ BranchBenchmark ở trên.

Phân biệt:

- **Vòng lặp nghiệp vụ:** duyệt toàn bộ input như ứng dụng thực tế; nên giữ trong benchmark.
- **Vòng lặp nhân tạo:** gọi cùng một thao tác nhỏ lặp đi lặp lại chỉ để amortize harness; có thể làm thay đổi hành vi compiler và sai lệch phép đo.

Nếu method quá nhỏ để đo ổn định, hãy benchmark một đơn vị công việc hợp lý hoặc dùng các kỹ thuật benchmark được JMH hỗ trợ, không tự nhân số lần gọi một cách tùy tiện.

## 9. Phân bố dữ liệu ảnh hưởng tới JIT và CPU

Một nhánh có xác suất đúng 99% có thể được CPU branch predictor xử lý khác với nhánh 50/50. Một call site chỉ nhận một implementation có thể được JIT tối ưu khác với call site đa hình. Một mảng vừa cache có thể có hành vi khác với working set lớn hơn cache.

Một số trường hợp cần tạo input riêng:

### Branch distribution

So sánh 95/5, 50/50 và 5/95 nếu production có tỷ lệ nhánh khác nhau. Đừng chỉ dùng dữ liệu ngẫu nhiên đều nếu dữ liệu thật bị lệch mạnh.

### Polymorphic call site

Nếu production truyền nhiều implementation vào một interface, benchmark cũng cần phản ánh tỷ lệ các implementation. Chạy từng implementation trong trial riêng có thể tạo profile đơn hình và không mô tả call site đa hình trong ứng dụng.

### Cache hit/miss

Nếu benchmark cache, cần xác định đang đo cache nóng, cache lạnh hay tỷ lệ hit/miss thực tế. Setup có thể làm nóng cache ngoài ý muốn; dữ liệu quá nhỏ có thể nằm hoàn toàn trong CPU cache.

### Kích thước working set

Dùng nhiều kích thước input để thấy điểm thay đổi khi dữ liệu vượt L1, L2, LLC hoặc heap pressure. Không suy rộng kết quả với mảng nhỏ sang xử lý dữ liệu lớn.

### Dữ liệu lỗi và biên

Parser, validator và mapper nên có tỷ lệ input lỗi, chuỗi dài, giá trị null hoặc biên giống workload thật nếu các trường hợp này ảnh hưởng tới đường code.

## 10. Chọn Scope để mô phỏng mức đồng thời

JMH dùng state scope để xác định state được chia sẻ như thế nào:

| Scope | Cách chia sẻ | Khi phù hợp |
| --- | --- | --- |
| **Scope.Thread** | Mỗi benchmark thread có state riêng | Đo thuật toán độc lập, tránh tranh chấp state |
| **Scope.Benchmark** | Các benchmark thread chia sẻ cùng state | Đo cấu trúc dữ liệu hoặc tài nguyên dùng chung |
| **Scope.Group** | Chia sẻ state giữa các thread trong cùng group | Mô phỏng nhóm reader/writer hoặc vai trò khác nhau |

Nếu production có nhiều request đồng thời truy cập cùng cache, benchmark chỉ dùng Scope.Thread có thể bỏ qua contention. Ngược lại, dùng state chia sẻ trong khi production mỗi request có state riêng có thể tạo contention không tồn tại trong ứng dụng.

Chọn scope theo ownership và sharing thực tế. Với benchmark concurrency, khai báo số thread và group rõ ràng; không tăng thread tùy ý rồi coi kết quả là hiệu năng production.

## 11. Chạy JMH và đọc kết quả

Sau khi project đã được cấu hình JMH, có thể chạy benchmark:

~~~bash
java -jar target/benchmarks.jar ".*BranchBenchmark.*"
~~~

Các tham số warmup, measurement và fork trong annotation sẽ được áp dụng. Có thể override từ command line:

~~~bash
java -jar target/benchmarks.jar ".*BranchBenchmark.*" -f 3 -wi 5 -w 1s -i 8 -r 1s
~~~

Để xem allocation theo operation:

~~~bash
java -jar target/benchmarks.jar ".*BranchBenchmark.*" -prof gc
~~~

GC profiler có thể cung cấp chỉ số như **gc.alloc.rate.norm**, thường được biểu diễn bằng B/op. Chỉ số này giúp so sánh lượng cấp phát chuẩn hóa trên một operation trong benchmark. Nó không thay thế việc phân tích allocation site bằng JFR.

Có thể lưu kết quả dạng JSON để so sánh và lưu trữ:

~~~bash
java -jar target/benchmarks.jar ".*BranchBenchmark.*" -rf json -rff results.json
~~~

Khi đọc output, chú ý:

- **Score:** giá trị đo theo benchmark mode và output unit.
- **Error:** mức sai số được báo bởi JMH.
- **Units:** đơn vị của score; AverageTime và Throughput có cách diễn giải khác nhau.
- **Parameters:** kích thước và phân bố input đang được đo.
- **Forks:** kết quả có ổn định giữa các JVM độc lập không.
- **GC profiler:** allocation và GC có thay đổi theo phương án không.

Không chọn duy nhất một dòng score tốt nhất. Hãy xem kết quả của tất cả parameter, iteration và fork, đồng thời đánh giá độ dao động. Nếu hai phương án chênh lệch nhỏ hơn nhiễu tự nhiên, chưa đủ căn cứ để khẳng định một phương án nhanh hơn.

## 12. Kết hợp JMH và JFR đúng mục đích

JMH và JFR bổ sung cho nhau:

| Công cụ | Vai trò |
| --- | --- |
| JMH | Đo thời gian, throughput hoặc allocation trên một operation trong môi trường benchmark có kiểm soát |
| JFR | Tìm class, method, thread, GC và event liên quan trong một workload runtime |
| GC log | Quan sát chu kỳ GC, pause và thay đổi heap |
| Application metrics/tracing | Đo latency và throughput của request thực tế |

Quy trình hợp lý:

1. Dùng JFR hoặc production profile để xác định hot path cần điều tra.
2. Tạo JMH benchmark đại diện cho logic đó.
3. Chuẩn bị input cùng kích thước và phân bố.
4. Chạy warmup, measurement và nhiều fork.
5. Dùng GC profiler khi cần đo allocation/op.
6. Nếu cần stack trace và allocation site, chạy JFR trong một lần điều tra riêng.
7. Xác nhận lại thay đổi bằng load test hoặc metric ứng dụng.

Không nên mặc định bật JFR với cấu hình profile trong mọi lần JMH rồi coi kết quả là benchmark sạch. Việc thu thập thêm event có thể làm thay đổi overhead. Hãy dùng JMH profiler cho phép đo phù hợp và dùng JFR riêng để hiểu call site, sau đó đối chiếu với workload tích hợp.

## 13. Những lỗi benchmark thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Không warmup | Đo interpreter, class loading hoặc compilation | Dùng warmup iteration đủ dài và workload đại diện |
| Chỉ chạy một fork | Kết quả phụ thuộc trạng thái một JVM | Chạy nhiều fork độc lập |
| Input luôn là hằng số | Constant folding và profile không đại diện | Tạo input động, có phân bố kiểm soát |
| Không sử dụng kết quả | Dead-code elimination | Trả kết quả hoặc dùng Blackhole |
| Tạo dữ liệu trong method nhưng không cần đo setup | Đo nhầm chi phí tạo input | Chuẩn bị ở Setup Level.Trial |
| Setup quá thường xuyên | Thay đổi cache và làm sai workload | Chọn đúng Level.Trial/Iteration/Invocation |
| Benchmark một nhánh duy nhất | JIT và CPU predictor thấy profile quá thuận lợi | Dùng phân bố giống production |
| Benchmark một implementation nhưng production đa hình | Profile call site khác thực tế | Mô phỏng tỷ lệ implementation cùng call site |
| Tự lặp method nhỏ hàng nghìn lần | JIT unroll/gộp và thay đổi đơn vị công việc | Benchmark operation hợp lý, để JMH điều khiển |
| Dùng một score duy nhất | Bỏ qua noise và sai số | Xem error, fork, iteration và lặp lại |
| Dùng microbenchmark để kết luận latency service | Bỏ qua network, queue, database và concurrency | Xác nhận bằng load test/tracing |

## 14. Checklist thiết kế phép đo

Trước khi tin vào một benchmark, hãy kiểm tra:

- Đã xác định đo cold-start, steady-state hay end-to-end chưa?
- Warmup có chạy đúng đường code và phân bố input cần đo không?
- Có nhiều measurement iteration và fork độc lập không?
- Input có cùng kích thước, skew, hit/miss và tỷ lệ lỗi như workload mục tiêu không?
- Dữ liệu được chuẩn bị ngoài vùng đo hay được tính vào theo đúng mục tiêu?
- Kết quả có được trả về hoặc tiêu thụ để tránh dead-code elimination không?
- Có vô tình benchmark một hằng số hoặc một implementation duy nhất không?
- State scope và số thread có phản ánh cách chia sẻ dữ liệu trong production không?
- Có ghi lại JDK, JVM flags, GC, CPU, heap và phiên bản benchmark không?
- Có xem sai số và độ dao động giữa các fork không?
- Có xác nhận lại bằng JFR, GC log hoặc load test khi cần không?

## 15. Kết luận

Một benchmark Java đáng tin cậy cần warmup để JIT quan sát workload, measurement đủ dài và nhiều fork để kiểm tra tính lặp lại. Đầu vào cần phản ánh kích thước, phân bố, tỷ lệ nhánh, cache hit/miss và mức đa hình của ứng dụng. Dữ liệu phải được chuẩn bị đúng với mục tiêu đo, kết quả phải được sử dụng để tránh dead-code elimination và phép đo không nên tự nhân vòng lặp một cách tùy tiện.

Dùng JMH để đo operation trong điều kiện có kiểm soát, JFR để tìm allocation và method hot spot, rồi xác nhận bằng workload tích hợp cùng response-time metrics. Phân biệt cold-start với steady-state, ghi lại môi trường thử nghiệm và không kết luận từ một score đơn lẻ. Những bước này giúp phép đo có thể tái lập và tránh biến một kết quả thuận lợi trong benchmark thành giả định sai về production.

## Tài liệu tham khảo

- [OpenJDK JMH — Project and Documentation](https://openjdk.org/projects/code-tools/jmh/)
- [OpenJDK JMH Samples — Source Repository](https://github.com/openjdk/jmh/tree/master/jmh-samples/src/main/java/org/openjdk/jmh/samples)
- [JMH Sample 08 — Dead Code](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java)
- [JMH Sample 09 — Blackholes](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_09_Blackholes.java)
- [JMH Sample 12 — Forking](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_12_Forking.java)
- [JMH Sample 13 — Run to Run](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_13_RunToRun.java)
- [JMH Sample 27 — Params](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_27_Params.java)
- [JMH Sample 35 — Profilers](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_35_Profilers.java)
- [JDK Mission Control 9 — Using JDK Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html)

