# JIT, làm nóng và ảnh hưởng tới phép đo trong Java 17

Java chạy trên JVM nên thời gian thực thi của một đoạn code không nhất thiết ổn định ngay từ lần gọi đầu tiên. Trên HotSpot JDK 17, một method có thể bắt đầu chạy bằng interpreter, sau đó được biên dịch thành mã máy bởi JIT compiler khi JVM thu thập đủ thông tin về tần suất gọi và hành vi thực tế. Các lần chạy sau có thể nhanh hơn vì JVM đã tối ưu method, dữ liệu đã nằm trong cache, class đã được nạp và nhiều công việc khởi tạo đã hoàn tất.

Quá trình này ảnh hưởng trực tiếp đến benchmark. Nếu chỉ đo một lần chạy đầu, kết quả có thể bao gồm class loading, khởi tạo, JIT compilation và các chi phí khởi động. Nếu đo sau khi chương trình đã chạy lâu, kết quả có thể phản ánh trạng thái steady state đã được tối ưu. Hai con số trả lời hai câu hỏi khác nhau.

Để đo hiệu năng Java 17 đáng tin cậy, cần hiểu **JIT hoạt động theo giai đoạn nào, warmup làm thay đổi điều gì, benchmark đang đo trạng thái nào và JVM có thực hiện đúng công việc mà ta muốn đo hay không**. Với microbenchmark, JMH là công cụ phù hợp hơn một vòng lặp tự bấm giờ bằng System.nanoTime().

## 1. JVM thực thi bytecode như thế nào?

Khi biên dịch chương trình Java, javac thường tạo bytecode trong file class. Bytecode không phải mã máy dành riêng cho một CPU. JVM nạp class, kiểm tra bytecode, liên kết các kiểu cần thiết và thực thi theo cơ chế của runtime.

Trong HotSpot, các thành phần chính có thể được hình dung như sau:

~~~text
Java source
    |
    v
javac
    |
    v
class files (bytecode)
    |
    v
Class loading / verification / linking / initialization
    |
    v
Interpreter executes bytecode
    |
    +---- profiling: call counts, branches, type information
    |
    v
JIT compiler compiles hot methods
    |
    v
Optimized machine code
    |
    +---- more profiling / possible recompilation
    |
    +---- deoptimization if assumptions become invalid
~~~

Interpreter giúp JVM bắt đầu thực thi mà không cần biên dịch toàn bộ chương trình thành mã máy trước. Trong lúc chạy, JVM thu thập thông tin về method và đường đi thường gặp. JIT sử dụng thông tin đó để biên dịch các phần được thực thi nhiều lần.

Không phải mọi method đều được biên dịch ngay, và không phải mọi method đều cần được biên dịch. Một method hiếm khi chạy có thể tiếp tục được interpreter thực thi vì chi phí biên dịch nó không đem lại lợi ích tương xứng.

### Bytecode và mã máy là hai tầng khác nhau

Bytecode được thiết kế để JVM thực thi và có tính di động giữa các nền tảng tương thích. Mã máy được JIT tạo ra phụ thuộc kiến trúc CPU, runtime và các giả định tối ưu tại thời điểm biên dịch.

Vì thế:

- Cùng một file class có thể được JIT thành mã máy khác nhau trên x86-64 và AArch64.
- Cùng một ứng dụng có thể có thời gian chạy khác nhau trên các bản JDK hoặc cấu hình JVM.
- Tối ưu hóa có thể phụ thuộc dữ liệu đầu vào và kiểu object thực tế.
- Một method có thể được biên dịch lại hoặc deoptimize trong quá trình chạy.

Java Language Specification và JVM Specification quy định ngữ nghĩa chương trình và bytecode. Cơ chế tiered compilation, ngưỡng biên dịch và các tối ưu cụ thể là chi tiết triển khai của JVM như HotSpot; không nên coi mọi JVM đều phải dùng cùng thuật toán JIT.

## 2. JIT là gì và vì sao có lợi?

JIT (Just-In-Time compiler) biên dịch một phần chương trình trong lúc chạy. Thay vì biên dịch toàn bộ ứng dụng trước khi chạy, JVM đợi cho tới khi có dữ liệu runtime để nhận biết đoạn code nào thực sự nóng và cách nó được sử dụng.

Ví dụ:

~~~java
static long sumSquares(int limit) {
    long sum = 0;
    for (int i = 0; i < limit; i++) {
        sum += (long) i * i;
    }
    return sum;
}
~~~

Nếu method được gọi một lần, chi phí biên dịch có thể không đáng. Nếu được gọi hàng triệu lần, JIT có thể tối ưu vòng lặp và tạo mã máy hiệu quả hơn việc interpreter thực thi bytecode lặp đi lặp lại.

JIT có thể sử dụng thông tin runtime để:

- Inline method nhỏ hoặc thường xuyên được gọi.
- Loại bỏ một số kiểm tra hoặc nhánh khi có giả định hợp lệ.
- Tối ưu vòng lặp và biểu thức.
- Loại bỏ allocation không cần thiết trong một số trường hợp.
- Tận dụng kiểu object thực tế và call site có tính ổn định.
- Sắp xếp lại lệnh trong giới hạn ngữ nghĩa Java và mô hình bộ nhớ.

JIT không bảo đảm mọi method đều nhanh hơn theo cùng tỷ lệ. Một method có thể bị giới hạn bởi memory bandwidth, cache miss, lock contention, I/O hoặc allocation/GC. Nếu bottleneck nằm ngoài phần tính toán được JIT tối ưu, warmup không thể loại bỏ giới hạn đó.

## 3. Tiered compilation trong HotSpot Java 17

HotSpot JDK 17 thường bật tiered compilation mặc định. Mô hình này kết hợp interpreter và các mức biên dịch để cân bằng thời gian khởi động, chi phí profiling và hiệu năng steady state.

Các mức thường được mô tả:

| Level | Cách thực thi | Mục tiêu |
| ---: | --- | --- |
| 0 | Interpreter | Bắt đầu thực thi và thu thập thông tin ban đầu |
| 1 | C1, không profiling đầy đủ | Biên dịch nhanh để giảm chi phí interpreter |
| 2 | C1 với profiling giới hạn | Thu thập một phần thông tin runtime |
| 3 | C1 với profiling đầy đủ | Thu thập thông tin phục vụ tối ưu sâu hơn |
| 4 | C2, optimizing compiler | Tối ưu mạnh cho code nóng và ổn định |

C1 là compiler tối ưu nhanh, thường được dùng ở các mức biên dịch thấp hơn. C2 là optimizing compiler của HotSpot, có thể thực hiện các tối ưu sâu hơn nhưng thời gian biên dịch cũng cao hơn.

Một method có thể chuyển từ interpreter sang C1, rồi lên C2 khi đủ nóng và có đủ profile. Không phải method nào cũng đi qua mọi level; quyết định còn phụ thuộc ngưỡng, cấu hình, trạng thái runtime và khả năng biên dịch.

### Vì sao không biên dịch mọi thứ bằng C2 ngay từ đầu?

Biên dịch tối ưu cần thời gian CPU và dữ liệu để phân tích. Nếu biên dịch mọi method bằng compiler tối ưu ngay khi khởi động:

- Startup có thể chậm hơn.
- Tốn CPU cho code có thể chỉ chạy một lần.
- JVM mất lợi ích từ profiling thực tế.
- Các giả định tối ưu chưa có đủ dữ liệu có thể không phù hợp với workload.

Tiered compilation giúp JVM bắt đầu nhanh hơn rồi đầu tư tối ưu vào phần code thực sự nóng. Đây là lý do hiệu năng của cùng một method có thể khác đáng kể giữa những lần gọi đầu và các lần gọi sau.

### Tiered compilation không phải một hợp đồng của ngôn ngữ Java

Các level 0–4 mô tả HotSpot, không phải quy tắc bắt buộc của mọi JVM. OpenJ9 hoặc một runtime khác có thể dùng kiến trúc JIT khác. Khi benchmark, ghi lại vendor, phiên bản JDK, JVM flags và runtime thực tế; không suy rộng một kết quả HotSpot thành quy luật cho mọi JVM.

## 4. Profiling và những thông tin JIT thu thập

JIT có thể thu thập thông tin về:

- Method được gọi thường xuyên đến mức nào.
- Call site thường nhận object thuộc class nào.
- Nhánh điều kiện nào được đi qua thường xuyên.
- Vòng lặp thực hiện bao nhiêu lần.
- Một số phép kiểm tra có thường xuyên thành công hay không.

Thông tin này gọi chung là runtime profile. Nó giúp JIT tối ưu dựa trên cách chương trình thực sự chạy, thay vì chỉ dựa vào bytecode tĩnh.

### Monomorphic và polymorphic call site

Giả sử có interface:

~~~java
interface PriceRule {
    int apply(int price);
}

final class DiscountRule implements PriceRule {
    public int apply(int price) {
        return price - price / 10;
    }
}

static int calculate(PriceRule rule, int price) {
    return rule.apply(price);
}
~~~

Nếu call site thường xuyên chỉ nhận một implementation, JIT có thể nhận biết kiểu receiver ổn định và inline lời gọi trong một số điều kiện. Nếu cùng call site nhận nhiều implementation khác nhau, việc tối ưu có thể phức tạp hơn.

Một benchmark chỉ chạy một implementation có thể cho kết quả rất tốt nhờ profile monomorphic. Trong production, nếu cùng method được gọi với nhiều implementation, kết quả có thể khác.

Vì vậy, dữ liệu warmup cần đại diện cho workload thực tế. Nếu warmup chỉ dùng một kiểu dữ liệu nhưng production dùng nhiều kiểu, profile thu được có thể không phản ánh trạng thái triển khai thật.

### Branch profile

JIT cũng có thể tối ưu dựa trên nhánh thường gặp. Ví dụ:

~~~java
static int classify(int value) {
    if (value >= 0) {
        return value + 1;
    }
    return -value;
}
~~~

Nếu dữ liệu warmup luôn không âm, JVM có thể có profile nghiêng mạnh về nhánh đầu. Khi workload thực tế có phân bố khác, hiệu năng có thể thay đổi; trong một số trường hợp giả định tối ưu bị vi phạm và code phải deoptimize.

Benchmark nên dùng dữ liệu có phân phối phù hợp với production hoặc đo nhiều profile đại diện.

## 5. Warmup là gì?

Warmup là giai đoạn chạy workload trước khi thu thập số liệu chính. Mục đích là đưa JVM và môi trường thực thi tới trạng thái phù hợp với câu hỏi benchmark.

Warmup có thể giúp:

- Nạp class và thực hiện class initialization.
- Làm nóng đường code thường dùng.
- Thu thập runtime profile.
- Kích hoạt C1/C2 compilation cho method nóng.
- Tạo và làm nóng cache dữ liệu.
- Đưa allocator, GC và các cấu trúc runtime vào trạng thái hoạt động đại diện.
- Giảm ảnh hưởng của lần gọi đầu tiên khi benchmark mục tiêu là steady state.

Warmup không phải chỉ là chạy một vòng lặp bất kỳ. Nó cần thực hiện cùng loại công việc và dữ liệu đủ đại diện để profile được thu thập có ý nghĩa.

### Warmup phải gần với workload được đo

Ví dụ benchmark tìm phần tử:

~~~java
static int findFirstPositive(int[] values) {
    for (int value : values) {
        if (value > 0) {
            return value;
        }
    }
    return -1;
}
~~~

Nếu warmup luôn dùng mảng mà phần tử đầu tiên dương, nhưng measurement dùng mảng mà phần tử dương nằm cuối, số vòng lặp và branch behavior khác nhau. Warmup không đại diện có thể làm profile và cache state lệch khỏi workload đo.

Tương tự, warmup với object nhỏ, một class duy nhất hoặc dữ liệu nằm trọn trong cache không đại diện cho workload có object graph lớn và nhiều kiểu runtime.

### Warmup không làm mọi thứ ổn định vĩnh viễn

Ngay cả sau warmup, JVM vẫn có thể:

- Biên dịch method khác khi chúng trở nên nóng.
- Biên dịch lại method khi profile thay đổi.
- Deoptimize code khi một giả định không còn đúng.
- Thực hiện GC và thay đổi trạng thái heap.
- Thay đổi mức sử dụng CPU theo tải hệ thống.

Do đó, không nên kết luận rằng sau một số vòng warmup cố định, JVM luôn ở trạng thái bất biến. Hãy quan sát độ ổn định của nhiều measurement iteration và kiểm tra log/profile khi cần hiểu sâu.

## 6. Warmup và cold start trả lời hai câu hỏi khác nhau

Một ứng dụng có thể được đánh giá theo ít nhất hai mục tiêu:

**Cold-start performance**: thời gian từ khi bắt đầu tiến trình tới khi ứng dụng sẵn sàng hoặc hoàn thành một tác vụ đầu tiên. Chỉ tiêu này quan trọng với CLI, serverless, autoscaling, job ngắn hạn và ứng dụng thường xuyên restart.

**Steady-state performance**: hiệu năng sau khi ứng dụng đã khởi động, nạp class, thu thập profile và JIT tối ưu các đường chạy nóng. Chỉ tiêu này quan trọng với service chạy lâu, batch dài và hệ thống xử lý liên tục.

| Khía cạnh | Cold start | Steady state |
| --- | --- | --- |
| JIT profile | Chưa có hoặc còn ít | Đã tích lũy theo workload |
| Class loading | Có thể chiếm phần đáng kể | Phần lớn class cần thiết đã được nạp |
| JIT compilation | Có thể xuất hiện trong thời gian đo | Code nóng thường đã được biên dịch |
| Cache | Chưa nóng | Có thể đã nóng theo workload |
| Mục tiêu | Thời gian sẵn sàng/lần chạy đầu | Throughput hoặc latency ổn định |
| Phương pháp | Đo tiến trình mới hoặc request đầu | Warmup rồi đo nhiều iteration |

Không dùng một benchmark warmup lâu để trả lời câu hỏi cold start. Cũng không dùng một lần chạy mới khởi động để kết luận throughput steady state.

### Cold start gồm nhiều chi phí

Cold start không chỉ là JIT:

- Khởi chạy tiến trình JVM.
- Nạp và xác minh class.
- Khởi tạo static field và singleton.
- Đọc cấu hình, nạp thư viện và resource.
- Tạo connection pool hoặc client.
- Mở kết nối tới database/dịch vụ ngoài.
- JIT compilation của đường code đầu tiên.
- Các chi phí hệ điều hành và filesystem cache.

Nếu mục tiêu là thời gian ứng dụng sẵn sàng, đo từ bên ngoài tiến trình tới khi health check hoặc tác vụ đầu tiên hoàn thành. Đừng chỉ đo một method bằng JMH rồi gọi đó là cold-start time của cả ứng dụng.

## 7. Những tối ưu JIT có thể làm thay đổi phép đo

### Method inlining

JIT có thể thay lời gọi method bằng phần thân method tại call site nếu điều kiện tối ưu phù hợp. Điều này giảm overhead gọi hàm và tạo cơ hội tối ưu liên tiếp.

~~~java
static int addOne(int value) {
    return value + 1;
}

static int calculate(int value) {
    return addOne(value) * 2;
}
~~~

Nếu addOne được inline, mã máy có thể không còn một lời gọi hàm riêng ở call site đó. Benchmark đo addOne đơn lẻ không nhất thiết dự đoán chính xác hiệu năng khi nó được inline trong pipeline thực.

### Escape analysis và scalar replacement

JIT có thể phân tích object có thoát khỏi phạm vi sử dụng hay không. Trong một số trường hợp, allocation có thể được loại bỏ hoặc object được thay bằng các scalar value/register thay vì tồn tại như một object heap đầy đủ.

~~~java
static int calculatePoint(int x, int y) {
    Point point = new Point(x, y);
    return point.x() + point.y();
}

record Point(int x, int y) {}
~~~

Tùy context và tối ưu của JIT, object trung gian có thể không cần được cấp phát thực sự. Nếu benchmark chỉ tạo object rồi không dùng kết quả có ý nghĩa, compiler có thể loại bỏ cả phần công việc. Hãy thiết kế benchmark để kết quả được quan sát hoặc tiêu thụ đúng cách.

### Constant folding và dead-code elimination

JIT có thể tính trước biểu thức chỉ phụ thuộc hằng số, hoặc loại bỏ code không ảnh hưởng kết quả có thể quan sát.

Ví dụ benchmark ngây thơ:

~~~java
@Benchmark
public void wrongBenchmark() {
    int result = 100 * 200;
}
~~~

Phép tính không được sử dụng và có thể bị loại bỏ. Benchmark khi đó không đo phép nhân theo cách người viết mong muốn.

Một benchmark đúng hơn trả về kết quả:

~~~java
@Benchmark
public int calculate() {
    return 100 * 200;
}
~~~

Nhưng ngay cả vậy, hằng số vẫn có thể được constant-fold thành một giá trị cố định. Nếu muốn đo phép tính trên input, hãy dùng dữ liệu runtime thích hợp và đảm bảo không biến toàn bộ đầu vào thành compile-time constant.

### Loop unrolling và vectorization

JIT có thể biến đổi vòng lặp, gộp hoặc mở rộng các phép tính theo kiến trúc CPU. Một benchmark vòng lặp nhỏ có thể đo code đã được tối ưu khác đáng kể với bytecode ban đầu.

Không nên cố tình vô hiệu hóa mọi tối ưu của JVM để “đo code Java thuần”. Mục tiêu thông thường là đo hiệu năng ứng dụng khi JVM được phép hoạt động như production. Nếu cần nghiên cứu một tối ưu cụ thể, hãy mô tả rõ điều kiện và cấu hình thử nghiệm.

## 8. Deoptimization: khi giả định tối ưu không còn đúng

JIT dùng profile và giả định để tạo mã máy nhanh. Nếu giả định không còn hợp lệ, JVM có thể deoptimize: rời mã máy tối ưu và quay lại mức thực thi khác để bảo toàn ngữ nghĩa chương trình.

Ví dụ call site trước đó chỉ thấy một implementation, sau đó xuất hiện implementation mới. Một số tối ưu phụ thuộc kiểu receiver có thể không còn áp dụng. JVM có thể vô hiệu hóa compiled code hoặc đưa execution về interpreter để tiếp tục thu thập profile và biên dịch lại.

Deoptimization không phải lỗi logic của Java; đó là cơ chế runtime bảo đảm chương trình vẫn chạy đúng khi profile thay đổi. Nhưng nó có thể tạo biến động latency hoặc throughput.

Các dấu hiệu có thể quan sát trong log JIT:

- Một method được biên dịch.
- Một nmethod bị invalidated hoặc made not entrant.
- Một sự kiện deoptimization.
- Method được biên dịch lại ở level khác.

Không nên suy luận deoptimization chỉ từ một spike latency. GC, scheduling, page fault, network và contention cũng có thể tạo spike. Dùng log/profile phù hợp để xác định nguyên nhân.

## 9. Vì sao phép đo bằng vòng lặp và System.nanoTime dễ sai?

Một ví dụ thường thấy:

~~~java
long start = System.nanoTime();
for (int i = 0; i < 1000; i++) {
    operation();
}
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
~~~

Đoạn này có thể hữu ích để kiểm tra sơ bộ thời gian end-to-end của một thao tác đủ dài, nhưng không phải microbenchmark JVM đáng tin cậy nếu dùng để so sánh các method nhỏ.

Các vấn đề:

1. Lần chạy đầu có thể bao gồm class loading, JIT compilation và initialization.
2. Lần chạy sau có thể dùng mã máy đã tối ưu.
3. JIT có thể loại bỏ operation nếu kết quả không quan sát được.
4. Constant folding có thể biến phép tính thành hằng số.
5. Vòng lặp ngoài có thể bị tối ưu hoặc biến đổi theo cách khác với production.
6. GC có thể xảy ra trong một lần đo nhưng không xảy ra ở lần khác.
7. CPU frequency scaling và tiến trình khác làm số đo dao động.
8. Một lần đo không cho biết phân phối hoặc độ ổn định.
9. Không có fork JVM độc lập để tách profile và trạng thái runtime giữa các thử nghiệm.

System.nanoTime() vẫn là API phù hợp để đo khoảng thời gian trong ứng dụng vì nó dùng đồng hồ đơn điệu cho elapsed time. Vấn đề không nằm ở nanoTime mà nằm ở cách thiết kế microbenchmark, số lần lặp và trạng thái JVM.

## 10. Dùng JMH để benchmark code Java

JMH (Java Microbenchmark Harness) là framework benchmark dành cho JVM. Nó quản lý các phần quan trọng như warmup, measurement, fork, tham số, kết quả và một số kỹ thuật tránh dead-code elimination.

Các annotation thường gặp:

| Annotation | Mục đích |
| --- | --- |
| @Benchmark | Đánh dấu phương thức được đo |
| @State | Khai báo phạm vi và lifecycle của dữ liệu benchmark |
| @Setup | Chuẩn bị dữ liệu trước benchmark hoặc iteration |
| @TearDown | Dọn dẹp sau benchmark hoặc iteration |
| @Warmup | Cấu hình số iteration warmup và thời lượng |
| @Measurement | Cấu hình iteration đo chính thức |
| @Fork | Chạy benchmark trong JVM process riêng |
| @BenchmarkMode | Chọn AverageTime, Throughput, SampleTime, SingleShotTime hoặc All |
| @OutputTimeUnit | Đơn vị kết quả |
| @Param | Chạy benchmark với nhiều giá trị tham số |

### Ví dụ benchmark có warmup và measurement

Ví dụ sau so sánh hai cách tính tổng trên cùng một mảng:

~~~java
import java.util.concurrent.TimeUnit;
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
@Measurement(iterations = 8, time = 1)
@Fork(3)
public class SumBenchmark {

    @Param({"100", "10000", "1000000"})
    public int size;

    private int[] values;

    @Setup
    public void setup() {
        values = new int[size];
        for (int i = 0; i < values.length; i++) {
            values[i] = (i * 31) % 1000;
        }
    }

    @Benchmark
    public long loopSum() {
        long sum = 0;
        for (int value : values) {
            sum += value;
        }
        return sum;
    }

    @Benchmark
    public long streamSum() {
        return java.util.Arrays.stream(values)
                .asLongStream()
                .sum();
    }
}
~~~

Ý nghĩa cấu hình:

- Mỗi kích thước mảng được benchmark riêng qua @Param.
- @Setup tạo dữ liệu một lần cho mỗi trial, không tính thời gian tạo mảng vào mỗi invocation.
- 5 warmup iterations cho JVM cơ hội nạp class, profiling và JIT compile.
- 8 measurement iterations được dùng để thu số liệu.
- 3 fork tạo các JVM process độc lập, giảm việc benchmark trước ảnh hưởng profile/compiled code của benchmark sau.
- AverageTime đo thời gian trung bình cho một invocation, hiển thị theo microseconds.

Các giá trị này là cấu hình minh họa, không phải con số bắt buộc. Một benchmark phức tạp có thể cần warmup lâu hơn hoặc ít hơn. Hãy xem kết quả từng iteration và độ ổn định trước khi kết luận.

### Chạy JMH

Trong project Maven/Gradle, cần cấu hình dependency JMH và annotation processor theo hướng dẫn chính thức của JMH. Sau khi tạo benchmark jar có runner:

~~~bash
java -jar target/benchmarks.jar SumBenchmark
~~~

Tên đường dẫn phụ thuộc cấu hình build. Không chỉ thêm dependency JMH vào runtime production; nên giữ benchmark trong source set/module riêng để tránh đưa harness vào artifact ứng dụng.

### Vì sao có fork?

Nếu chạy nhiều benchmark trong cùng một JVM, benchmark trước có thể làm nóng class, thay đổi profile, cấp phát object hoặc ảnh hưởng code được JIT compile cho benchmark sau. Fork khởi chạy JVM process mới để tách trạng thái runtime giữa các lần thử.

Fork không xóa mọi nguồn biến động: CPU, filesystem cache, OS scheduling, nhiệt độ và tải máy vẫn có thể ảnh hưởng. Nhưng nó giúp cô lập trạng thái JVM tốt hơn.

## 11. Chọn warmup duration và số iteration

Không có một cấu hình warmup phù hợp cho mọi benchmark. Cần cân nhắc:

- Method được gọi bao nhiêu lần trước khi trở thành hot.
- Đường code có nhiều branch/type profile hay không.
- Class loading và initialization có tốn thời gian không.
- Workload có cần nhiều thời gian để cache ổn định không.
- Benchmark có allocation và GC đáng kể không.
- Có cần đo trạng thái sau nhiều chu kỳ hoạt động không.

Warmup quá ngắn có thể khiến measurement vẫn bao gồm interpreter/C1 hoặc JIT compilation. Warmup quá dài có thể lãng phí thời gian và chỉ đo một trạng thái steady state không đại diện nếu production thường restart hoặc workload thay đổi liên tục.

### Quan sát từng iteration

JMH thường hiển thị kết quả cho từng measurement iteration. Nếu thời gian giảm mạnh từ iteration đầu tới iteration sau rồi ổn định, có thể runtime đang tiến tới trạng thái ổn định. Nếu kết quả dao động lớn liên tục, cần xem GC, contention, tải máy, profile thay đổi hoặc benchmark không ổn định.

Không nên chỉ lấy một iteration nhanh nhất làm kết quả. Giá trị nhanh nhất có thể là trường hợp thuận lợi ngẫu nhiên. Xem toàn bộ phân phối, mean/score error hoặc percentile tùy benchmark mode.

### Warmup không được dùng để che vấn đề startup

Nếu sản phẩm phải xử lý request đầu trong 100 ms sau khi tiến trình khởi động, benchmark với 30 giây warmup không trả lời câu hỏi đó. Có thể cần đo startup hoặc request đầu bằng process mới, rồi đo steady-state riêng.

## 12. JMH và dead-code elimination

JIT có quyền loại bỏ code không tạo tác động quan sát được theo ngữ nghĩa chương trình. Điều này có thể khiến benchmark đo một công việc khác với ý định.

### Trả kết quả từ benchmark

JMH tiêu thụ giá trị trả về của phương thức @Benchmark. Đây là cách đơn giản để làm kết quả trở nên quan sát được:

~~~java
@Benchmark
public int compute() {
    return calculate(input);
}
~~~

Nếu method trả về void và cần tiêu thụ một kết quả trung gian, dùng Blackhole:

~~~java
@Benchmark
public void compute(Blackhole blackhole) {
    int result = calculate(input);
    blackhole.consume(result);
}
~~~

Blackhole giúp ngăn JVM loại bỏ phép tính chỉ vì kết quả không được dùng. Tuy nhiên, không nên consume quá nhiều giá trị không liên quan; overhead của harness cũng có thể ảnh hưởng benchmark rất nhỏ.

### Tránh constant folding

Không benchmark biểu thức mà mọi đầu vào đều là hằng số compile-time:

~~~java
@Benchmark
public int constantExpression() {
    return 12345 * 67890;
}
~~~

JVM có thể tính kết quả trước và benchmark chỉ đo việc trả một hằng số. Dùng state/input runtime có ý nghĩa:

~~~java
@State(Scope.Thread)
public static class Input {
    @Param({"12345", "23456"})
    int value;
}

@Benchmark
public int multiply(Input input) {
    return input.value * 31;
}
~~~

Ngay cả với input runtime, JIT vẫn có thể tối ưu nếu pattern dữ liệu hoặc cách dùng khiến giá trị được dự đoán. Hãy thiết kế benchmark sát với cách ứng dụng thực sự gọi method.

### Tránh benchmark một vòng lặp tự tạo nếu mục tiêu là một invocation

Nếu method cần đo một thao tác, hãy để JMH gọi method theo harness. Tự viết vòng lặp lớn trong @Benchmark có thể làm JIT tối ưu toàn bộ vòng lặp khác với cách production gọi method nhiều lần; đồng thời khó tách latency mỗi lần gọi.

Nếu production thực sự xử lý một batch trong vòng lặp, benchmark batch đó là hợp lý, nhưng hãy xác định rõ đơn vị đo là một batch hay một phần tử.

## 13. Chọn benchmark mode theo câu hỏi

JMH hỗ trợ nhiều mode:

| Mode | Đo điều gì? | Khi phù hợp |
| --- | --- | --- |
| AverageTime | Thời gian trung bình mỗi operation | So sánh latency trung bình của một invocation |
| Throughput | Số operation trên đơn vị thời gian | Đo khả năng xử lý tổng thể |
| SampleTime | Lấy mẫu thời gian operation | Quan sát phân phối latency |
| SingleShotTime | Đo một lần thực thi mỗi iteration | Đo thao tác một lần, nhưng cần thiết kế riêng cho cold/one-shot |
| All | Chạy các mode được hỗ trợ | Khảo sát rộng, tốn thời gian hơn |

AverageTime không đồng nghĩa p99 latency. Throughput cao không bảo đảm từng request có latency thấp. Chọn mode theo câu hỏi và bổ sung benchmark tải hệ thống nếu mục tiêu là latency tail.

### SingleShotTime không tự động là cold start của ứng dụng

SingleShotTime đo một invocation theo cấu hình JMH. Nếu fork JVM mới và không warmup, nó có thể phản ánh một lần gọi ở trạng thái JVM mới, nhưng vẫn không nhất thiết đo toàn bộ startup của tiến trình production, classpath, dependency initialization và readiness.

Nếu mục tiêu là cold-start end-to-end, đo từ process launch ở bên ngoài bằng harness điều khiển tiến trình. Nếu mục tiêu là latency của method đầu tiên trong một JVM đã khởi động, hãy định nghĩa rõ phần setup nào nằm trong thời gian đo và dùng benchmark tương ứng.

## 14. JIT logging và công cụ quan sát

Khi cần xác nhận method có được biên dịch hay không, có thể dùng log của HotSpot. Trên JDK 17, unified logging hỗ trợ tag liên quan tới compilation:

~~~bash
java -Xlog:jit+compilation=debug ...
~~~

Log có thể cho biết method nào được biên dịch và ở level nào. Đầu ra rất lớn với ứng dụng có nhiều method; chỉ bật trong môi trường phân tích và lọc theo nhu cầu.

Một số tùy chọn chẩn đoán khác:

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation ...
~~~

Các tùy chọn diagnostic có thể thay đổi theo build/vendor và không nên được đưa vào production nếu chưa hiểu tác động. Không dựa vào nội dung log nội bộ như một API ổn định cho logic ứng dụng.

### JFR và profiling

Java Flight Recorder (JFR) có thể ghi sự kiện runtime như compilation, class loading, GC, thread activity và nhiều thông tin khác tùy cấu hình recording. Dùng JFR khi cần nối một spike latency với sự kiện runtime thay vì đoán nguyên nhân từ một con số tổng.

JFR có thể được khởi động từ command line:

~~~bash
java -XX:StartFlightRecording=filename=app.jfr,duration=60s ...
~~~

Sau đó mở file bằng Java Mission Control hoặc công cụ phân tích JFR phù hợp. Recording cũng có overhead; cấu hình sự kiện và thời lượng theo mục tiêu điều tra.

### Compilation log không thay thế benchmark

Thấy method được biên dịch ở C2 không chứng minh benchmark đã đo đúng hoặc code nhanh. Log giải thích trạng thái JIT; benchmark đo thời gian/throughput; profiler giúp xác định nơi CPU và thời gian đang được dùng. Kết hợp chúng khi cần, không thay thế cái này bằng cái kia.

## 15. Các yếu tố ngoài JIT cũng làm phép đo thay đổi

Warmup thường làm nhiều trạng thái cùng thay đổi, không chỉ compilation.

| Yếu tố | Ảnh hưởng tới phép đo |
| --- | --- |
| Class loading và initialization | Lần đầu có thể tốn thời gian đọc class, verify và chạy static initializer |
| CPU cache | Dữ liệu và instruction được dùng gần đây có thể nằm trong cache |
| Branch predictor | Pattern nhánh lặp lại có thể được dự đoán tốt hơn |
| Heap/GC | Allocation và GC pause làm thời gian biến động |
| Tần số CPU | Turbo/frequency scaling và nhiệt độ làm throughput thay đổi |
| OS scheduling | Thread có thể bị preempt hoặc tranh CPU |
| Memory bandwidth | Nhiều worker có thể cùng tranh băng thông RAM |
| Lock contention | Tăng thread có thể làm throughput giảm |
| Filesystem/page cache | Đọc lần đầu và đọc lại có thể có chi phí khác |
| Network connection | Kết nối mới và kết nối tái sử dụng có latency khác |
| Common pool/executor | Tác vụ khác có thể tranh worker |

Vì vậy, khi thời gian giảm sau warmup, không nên tự động kết luận toàn bộ mức cải thiện đến từ JIT. Cần đo/quan sát thêm nếu muốn phân rã nguyên nhân.

### GC có thể làm một iteration chậm

Benchmark tạo nhiều object có thể kích hoạt GC ở một iteration nhưng không phải iteration khác. Một iteration chậm không nhất thiết là JIT compile; nó có thể là GC pause hoặc allocation pressure.

JMH có profiler tích hợp cho một số chỉ số GC:

~~~bash
java -jar target/benchmarks.jar SumBenchmark -prof gc
~~~

Profiler có thể báo allocation rate và số liệu liên quan GC tùy môi trường. So sánh allocation/op giữa các cách triển khai có thể giải thích tại sao một phiên bản chậm hơn dù số phép toán tương tự.

## 16. Không tối ưu benchmark khác với tối ưu ứng dụng

Một benchmark nhỏ có thể đo một method trong điều kiện rất thuận lợi:

- Dữ liệu nằm trong L1/L2 cache.
- Chỉ có một thread.
- Không có request khác.
- Profile chỉ có một implementation.
- Không có logging, serialization hoặc network.

Production có thể khác:

- Nhiều request đồng thời.
- Dữ liệu lớn hơn và phân phối khác.
- Nhiều kiểu object và branch.
- Cache miss, memory pressure và GC.
- Lock contention hoặc pool saturation.
- Cấu hình CPU/container khác.

Một tối ưu làm benchmark đơn luồng nhanh hơn có thể làm allocation tăng, khiến GC nặng hơn dưới tải. Một tối ưu dựa trên monomorphic call site có thể không còn hiệu quả khi production polymorphic. Do đó, microbenchmark là công cụ trả lời câu hỏi hẹp, không thay thế load test, profiling và quan sát production.

## 17. So sánh cold, warm và steady-state measurement

Một kế hoạch đo có thể tách thành ba loại:

| Loại đo | Cách chuẩn bị | Chỉ tiêu |
| --- | --- | --- |
| Cold | JVM/process mới, không chạy warmup trước phần đo | Startup hoặc thao tác đầu |
| Warm-up transition | Chạy workload liên tục và ghi theo thời gian | Tốc độ chuyển từ interpreter/C1 sang trạng thái tối ưu |
| Steady state | Warmup đủ và đo nhiều iteration | Throughput/latency sau khi ổn định |

### Cold-start đo từ bên ngoài

Để đo startup của ứng dụng:

1. Tạo process JVM mới cho mỗi lần thử.
2. Bắt đầu đồng hồ ngay trước khi launch.
3. Xác định mốc sẵn sàng rõ ràng, ví dụ health endpoint trả success hoặc job đầu tiên hoàn thành.
4. Ghi thời gian từ launch tới mốc đó.
5. Lặp lại nhiều lần trong môi trường tương đương.
6. Ghi riêng ảnh hưởng filesystem cache, image/container startup và kết nối ngoài.

Không trộn startup time với thời gian xử lý một request sau khi server đã sẵn sàng.

### Warm-up transition đo theo iteration

Nếu muốn quan sát JIT warmup, chạy workload lặp và ghi thời gian từng batch/iteration. Bật compilation log hoặc JFR trong một lần chạy chẩn đoán để xem thời điểm method được biên dịch. Không nhất thiết bật logging trong phép đo hiệu năng chính vì log có thể thêm overhead.

### Steady-state đo bằng JMH

Dùng warmup, measurement và fork. Kiểm tra rằng kết quả các iteration đã tương đối ổn định và không bị một sự kiện GC hoặc tải máy làm sai lệch. Báo cáo cả cấu hình benchmark và runtime.

## 18. Đọc một báo cáo benchmark

Giả sử một báo cáo minh họa:

| Benchmark | Score | Error | Unit |
| --- | ---: | ---: | --- |
| loopSum | 120.4 | ± 3.1 | microseconds/op |
| streamSum | 135.8 | ± 4.0 | microseconds/op |

Các con số này chỉ minh họa cách đọc, không phải kết quả chạy thực tế. Trong ví dụ, loopSum có AverageTime thấp hơn, nhưng cần xem khoảng sai số, fork, kích thước dữ liệu và cấu hình trước khi kết luận chênh lệch có ý nghĩa.

Khi đọc báo cáo:

- Xác định mode và đơn vị.
- Kiểm tra số fork, warmup và measurement iteration.
- Kiểm tra dữ liệu đầu vào và @Param.
- Xem error/độ biến động.
- Kiểm tra allocation và GC nếu có.
- Xem môi trường JDK, CPU, OS và giới hạn container.
- Đảm bảo benchmark trả kết quả và không bị dead-code elimination.
- Không chọn chỉ số tốt nhất trong nhiều lần chạy mà bỏ qua các lần khác.

### So sánh theo tỷ lệ

Với AverageTime, nếu A = 100 microseconds/op và B = 80 microseconds/op, B nhanh hơn khoảng 20% về thời gian so với A. Speedup theo thời gian là 100/80 = 1.25 lần. Không gọi đó là tăng throughput 25% trong mọi điều kiện; quan hệ phụ thuộc benchmark mode và workload.

## 19. Những lỗi thường gặp khi xử lý warmup và JIT

| Lỗi | Vì sao sai | Cách làm phù hợp |
| --- | --- | --- |
| Chỉ đo lần gọi đầu tiên rồi kết luận method chậm | Đo cả class loading, initialization và JIT startup | Tách cold-start và steady-state |
| Chỉ đo sau warmup rồi kết luận startup nhanh | Warmup đã loại khỏi phép đo nhiều chi phí startup | Đo process launch riêng nếu startup quan trọng |
| Warmup bằng dữ liệu khác production | Runtime profile không đại diện | Dùng input/profile sát workload thật |
| Dùng vòng lặp nanoTime cho method rất nhỏ | JIT/GC/OS noise lớn hơn tín hiệu | Dùng JMH |
| Benchmark không trả hoặc consume kết quả | JIT có thể loại bỏ công việc | Return result hoặc dùng Blackhole |
| Dùng hằng số trong mọi phép tính | Constant folding có thể loại phép tính | Dùng input runtime phù hợp |
| Chạy mọi benchmark trong một JVM không fork | Profile và compiled code bị ảnh hưởng lẫn nhau | Dùng JMH @Fork |
| Chỉ lấy iteration nhanh nhất | Bỏ qua biến động và trạng thái runtime | Xem nhiều iteration và error |
| Cho rằng mọi method đều lên C2 | Method lạnh có thể không cần biên dịch | Quan sát compilation log khi cần |
| Cho rằng warmup xong JVM không đổi nữa | Profile, GC và deoptimization vẫn tiếp diễn | Quan sát độ ổn định và runtime event |
| Quy mọi spike cho JIT | GC, scheduling, I/O và contention cũng gây spike | Dùng JFR/profiler/log phù hợp |
| Dùng benchmark micro để đại diện production | Thiếu concurrency, dữ liệu và tài nguyên thật | Bổ sung load test và profiling |
| Tắt JIT để đo “tốc độ Java thật” | Đo một chế độ runtime khác production | Giữ cấu hình thực tế trừ khi đang nghiên cứu interpreter |
| Chỉnh ngưỡng compiler tùy tiện | Có thể làm thay đổi startup, throughput và profile | Đo baseline, thay một biến và ghi lại cấu hình |

## 20. Quy trình benchmark có thể lặp lại

Một quy trình thực tế cho Java 17:

### Bước 1: Xác định câu hỏi

Bạn muốn biết startup, latency request đầu, latency steady-state, throughput batch hay chi phí của một method? Không bắt đầu benchmark khi chưa xác định đơn vị đo và mục tiêu.

### Bước 2: Xây workload đại diện

Chọn dữ liệu, phân phối, kích thước, kiểu object, branch và concurrency giống ứng dụng. Ghi lại input seed hoặc fixture để có thể tái lập.

### Bước 3: Tạo benchmark đúng

Dùng JMH cho microbenchmark. Tách setup khỏi invocation khi setup không thuộc phần đo. Dùng @State, @Param, @Setup, @Warmup, @Measurement và @Fork phù hợp.

### Bước 4: Kiểm tra kết quả có được sử dụng

Return kết quả hoặc dùng Blackhole. Tránh constant folding và dead-code elimination. Đảm bảo benchmark thực hiện đúng logic muốn đo.

### Bước 5: Chạy baseline

Ghi phiên bản JDK/vendor, JVM flags, CPU, OS, container quota, heap, GC, benchmark parameters và kết quả từng iteration.

### Bước 6: Quan sát JIT/GC khi cần

Dùng JIT compilation log hoặc JFR trong lần chẩn đoán riêng. Dùng profiler để tìm CPU hotspot, allocation và contention. Không mặc định bật mọi diagnostic trong lần đo chính.

### Bước 7: Đo nhiều lần và so sánh có kiểm soát

Giữ cùng môi trường, chỉ thay một yếu tố mỗi lần. Xem độ biến động và sai số. Nếu thay JDK, GC hoặc compiler flag, ghi rõ vì đó là một thí nghiệm khác.

### Bước 8: Xác nhận ở cấp ứng dụng

Microbenchmark cho biết một thành phần. Chạy load test hoặc đo production-like workload để xác nhận cải thiện có tồn tại khi có request đồng thời, GC, I/O và giới hạn tài nguyên.

## 21. Ghi lại môi trường để kết quả có ý nghĩa

Một báo cáo benchmark nên có tối thiểu:

| Thông tin | Ví dụ cần ghi |
| --- | --- |
| JDK vendor/version | OpenJDK/Oracle JDK và bản cập nhật cụ thể |
| JVM | HotSpot hoặc runtime khác |
| JVM flags | Heap, GC, tiered compilation và các tùy chọn đã thay đổi |
| CPU | Model, số core, SMT và architecture |
| Hệ điều hành | Version và kernel |
| Container | CPU quota, memory limit và runtime container |
| Benchmark tool | JMH version |
| Warmup | Iterations và thời lượng |
| Measurement | Iterations và thời lượng |
| Fork | Số process độc lập |
| Input | Kích thước, phân phối, seed/fixture |
| Mode | AverageTime, Throughput, SampleTime hoặc mode khác |
| Profiler | GC/JFR/JIT log nếu có |

Khi so sánh hai kết quả từ hai máy hoặc hai JDK, thiếu thông tin môi trường có thể khiến kết luận sai. Một chênh lệch nhỏ có thể đến từ CPU frequency, container quota hoặc GC thay vì thay đổi code.

## 22. Khi nào nên thay đổi cấu hình JIT?

HotSpot có nhiều tùy chọn -XX liên quan compiler và tiered compilation. Hầu hết ứng dụng nên bắt đầu với mặc định của JDK 17 và chỉ thay đổi sau khi có bằng chứng từ benchmark/profile.

Các nguyên tắc:

- Không tắt tiered compilation chỉ vì một microbenchmark ngắn cho kết quả khác.
- Không ép biên dịch mọi method ngay từ đầu nếu chưa đo startup và CPU cost.
- Không thay threshold compiler để làm một benchmark riêng nhanh hơn rồi áp dụng production.
- Không dựa vào cờ diagnostic như một hợp đồng ứng dụng.
- Nếu phải thay đổi flag, ghi lại cấu hình, đo cold-start và steady-state, kiểm tra memory/CPU và chạy workload đại diện.

Có thể xem các cờ hỗ trợ trong runtime mục tiêu bằng:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Danh sách và giá trị mặc định có thể thay đổi giữa JDK/vendor/build. Không sao chép một bộ flags tối ưu từ bài viết khác mà không xác minh trên môi trường của mình.

## 23. Ví dụ: cùng method, hai cách đo khác nhau

Method cần đo:

~~~java
public final class TextCounter {
    public int countDigits(String text) {
        int count = 0;
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (ch >= '0' && ch <= '9') {
                count++;
            }
        }
        return count;
    }
}
~~~

### Đo steady state

Một JMH benchmark có thể giữ input trong State, warmup method và đo nhiều invocation:

~~~java
@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 10)
@Fork(3)
public class TextCounterBenchmark {
    private final TextCounter counter = new TextCounter();
    private String input;

    @Setup
    public void setup() {
        input = "order-2026-user-123456789";
    }

    @Benchmark
    public int countDigits() {
        return counter.countDigits(input);
    }
}
~~~

Đây là benchmark method trong trạng thái đã warmup. Kết quả chủ yếu phản ánh chi phí gọi và xử lý chuỗi ở trạng thái runtime đã được làm nóng theo workload benchmark.

### Đo lần gọi đầu trong process mới

Nếu câu hỏi là chi phí lần gọi đầu sau khi khởi động JVM, cần một harness riêng:

1. Khởi chạy JVM mới.
2. Nạp class và tạo đối tượng như ứng dụng thật.
3. Gọi method một lần với input xác định.
4. Ghi thời gian theo mốc đã định.
5. Kết thúc process và lặp lại nhiều lần.

Nếu tính từ lúc process launch, đồng hồ phải bắt đầu ở parent process trước khi khởi chạy Java. Nếu chỉ tính method invocation, setup class/object phải được xác định là nằm ngoài hay trong mốc đo. Hai cách đo này không thể hoán đổi cho nhau.

## 24. Nguyên tắc thực hành

Khi phân tích JIT, warmup và phép đo trên Java 17:

1. Hiểu rằng bytecode có thể được interpreter thực thi trước khi method nóng được JIT biên dịch.
2. Nhận biết tiered compilation C1/C2 của HotSpot là chi tiết runtime, không phải hợp đồng của mọi JVM.
3. Warmup bằng workload và dữ liệu đại diện với mục tiêu đo.
4. Tách cold-start, warmup transition và steady-state thành các phép đo riêng.
5. Dùng JMH cho microbenchmark, với warmup, measurement, fork và kết quả được tiêu thụ đúng cách.
6. Tránh dead-code elimination, constant folding và benchmark loop không đại diện.
7. Quan sát GC, class loading, JIT compilation, CPU và cache khi số đo biến động.
8. Dùng JFR/profiler/log để giải thích nguyên nhân, không suy luận từ một con số.
9. Ghi đầy đủ JDK, JVM flags, phần cứng, môi trường và cấu hình benchmark.
10. Xác nhận cải thiện bằng workload ở cấp ứng dụng trước khi áp dụng production.

JIT giúp JVM tối ưu code dựa trên hành vi thực tế, nhưng chính sự tối ưu theo thời gian đó làm phép đo Java nhạy với trạng thái runtime. Warmup có ích khi mục tiêu là steady state; cold-start cần một phép đo riêng. Khi xác định đúng câu hỏi, dùng JMH và quan sát runtime có hệ thống, số liệu benchmark sẽ phản ánh công việc cần đo thay vì ngẫu nhiên phản ánh trạng thái của lần chạy.
