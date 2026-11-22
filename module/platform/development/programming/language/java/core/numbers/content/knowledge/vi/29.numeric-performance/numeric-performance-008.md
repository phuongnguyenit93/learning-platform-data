# Đo hiệu năng tính toán số với miền dữ liệu thực tế và tình huống biên trong Java

## 1. Đo nhanh trên một vài số đẹp chưa phản ánh hiệu năng thực tế

Giả sử có hai cách cộng, chia hoặc chuẩn hóa số trong Java. Một cách có vẻ nhanh hơn khi chạy với 100 số nguyên nhỏ hoặc vài giá trị thập phân ngắn. Kết luận đó có thể đảo ngược khi dữ liệu thực tế gồm nhiều chữ số, scale chênh lệch lớn, số âm, số 0 hoặc tỷ lệ ngoại lệ cao.

Vì vậy, đo hiệu năng có ý nghĩa đòi hỏi **cả hai**:

1. **Miền dữ liệu đại diện:** kích thước đầu vào, phân bố giá trị, precision/scale, tần suất phép toán và tỷ lệ đầu vào thông thường phải gần với tải công việc cần tối ưu.
2. **Tình huống biên:** dữ liệu ở các giới hạn có thể khiến thuật toán đổi nhánh, overflow, phải cấp phát nhiều hơn, ném ngoại lệ hoặc chạy với độ phức tạp khác hẳn.

Bài học tập trung vào cách thiết kế, kiểm chứng và đọc kết quả phép đo cho các kiểu số `int`, `long`, `double`, `BigInteger`, `BigDecimal` và các thao tác tổng hợp liên quan. Mục tiêu là chọn triển khai **đúng yêu cầu số học** và **đủ nhanh với tải thực**, thay vì chọn mã chỉ nhanh trong một bài thử nhỏ.

Ba câu hỏi phải được trả lời trước khi benchmark:

- **Đo thao tác nào?** Ví dụ parse chuỗi thành `BigDecimal`, cộng các `BigDecimal` đã được tạo sẵn, nhân `BigInteger`, tính tổng `IntStream`, hoặc format đầu ra.
- **Đầu vào thật trông như thế nào?** Bao nhiêu phần tử một lần gọi? Bao nhiêu chữ số? Có dữ liệu âm, 0, số rất lớn, scale khác nhau, số bất thường?
- **Định nghĩa đúng là gì?** Kết quả phải chính xác tuyệt đối, được làm tròn theo quy tắc nào, có được overflow không, và xử lý đầu vào không hợp lệ ra sao?

Không thể so sánh hai phép tính chỉ vì chúng trả về một con số nhìn có vẻ giống nhau. Ví dụ, thay `BigDecimal` bằng `double` có thể nhanh nhưng làm mất bảo đảm chính xác thập phân cần cho tiền tệ. Đó là **thay đổi ngữ nghĩa**, không phải chỉ tối ưu.

## 2. Xây dựng hồ sơ dữ liệu trước khi đo

Một benchmark có thể đo đúng thời gian chạy của dữ liệu nó nhận, nhưng vẫn trả lời sai câu hỏi nếu dữ liệu đó không đại diện cho sản phẩm thật.

Ví dụ một dịch vụ xử lý giao dịch nhận số tiền ở dạng chuỗi:

- Phần lớn số tiền có hai chữ số thập phân và nằm trong giới hạn thường gặp.
- Một tỷ lệ nhỏ là số tiền 0, số âm (hoàn tiền), số rất lớn hoặc có nhiều chữ số lẻ.
- Một số dòng là dữ liệu đầu vào sai định dạng và phải bị từ chối.
- Khối lượng giao dịch mỗi batch có thể là 1, 100, 10.000 hoặc nhiều hơn.

Nếu chỉ đo `new BigDecimal("1.00").add(new BigDecimal("2.00"))` trong vòng lặp, ta đã bỏ qua parse, bộ nhớ, số lượng phần tử, scale, giá trị cực lớn và tính chất batch.

### 2.1. Ma trận dữ liệu đại diện

| Trục dữ liệu | Cần ghi nhận | Vì sao tác động hiệu năng |
|---|---|---|
| Kích thước tập | 0, 1, vài chục, hàng nghìn, hàng triệu; phân bố thực tế | Chi phí khởi tạo pipeline, vòng lặp, cache, phân bổ và GC |
| Độ lớn số nguyên | Giá trị nhỏ, sát `Integer.MAX_VALUE`/`Long.MAX_VALUE`, số `BigInteger` rất dài | Overflow, số limb nội bộ, thuật toán nhân/chia |
| `BigDecimal.precision()` | Ít chữ số, nhiều chữ số, độ dài cực lớn hợp lệ | Chi phí phép toán và định dạng thay đổi |
| `BigDecimal.scale()` | Scale 0, 2, âm, lớn, chênh lệch scale | Phép cộng có thể cần căn chỉnh scale; `setScale`/`divide` cần thêm xử lý |
| Dấu và giá trị | Số dương, âm, 0, gần 0, đổi dấu liên tục | Nhánh điều kiện, hủy số, quy tắc làm tròn |
| Phép tính | Cộng, nhân, chia, làm tròn, parse, format | Mỗi phép có độ phức tạp và kiểu cấp phát riêng |
| Dạng đầu vào | Chuỗi, primitive array, wrapper collection | Chi phí parse, boxing/unboxing, chuyển đổi |
| Kiểu truy cập | Tuần tự, song song, nhiều request đồng thời | Cạnh tranh CPU, cache, allocator và GC |

**Tập phổ biến** và **tập biên** nên là hai nhóm kết quả riêng. Một trường hợp cực đoan hiếm gặp có thể được ghi nhận, nhưng không nên đánh đồng nó với thời gian trung bình của mọi request. Đồng thời, tình huống biên có thể là một yêu cầu chính thức, ví dụ ngưỡng latency tối đa hoặc giới hạn chống quá tải; khi đó nó cần có tiêu chí riêng.

### 2.2. Phân bố quan trọng hơn giá trị trung bình

Giả sử một triệu request có 99% đầu vào là `BigDecimal` 6 chữ số và 1% là số dài hàng nghìn chữ số. Lấy độ dài trung bình rồi chỉ benchmark một giá trị có độ dài trung bình **không tương đương** với benchmark hỗn hợp thật: thời gian của phép nhân/chia và cấp phát bộ nhớ có thể tăng không tuyến tính theo số chữ số.

Thực hành tốt:

1. Tách **bucket** theo kích thước: ví dụ 1–9, 10–99, 100–999, từ 1000 chữ số trở lên (chỉ là ví dụ; ranh giới phải theo dữ liệu thực).
2. Đo từng bucket để biết chi phí của từng lớp đầu vào.
3. Đo một workload **hỗn hợp có trọng số theo tỷ lệ thật** để ước lượng tải phổ biến.
4. Đo trường hợp xấu riêng nếu cần đáp ứng ngưỡng SLO hoặc giới hạn an toàn.

Khi nguồn production chứa dữ liệu nhạy cảm, tạo dữ liệu tổng hợp có **cùng đặc điểm thống kê**; không sao chép nguyên thông tin cá nhân hoặc giá trị nhạy cảm vào benchmark.

## 3. Bộ tình huống biên theo từng kiểu số

Các loại biên phải xuất phát từ miền số và thao tác thực sự được sử dụng.

### 3.1. int và long: kiểm tra giới hạn và overflow

~~~java
int maxInt = Integer.MAX_VALUE;            // 2147483647
long beyondInt = (long) maxInt + 1;        // 2147483648

int overflow = maxInt + 1;                 // -2147483648 (wrap)
~~~

Cần kiểm tra tối thiểu các giá trị `0`, `1`, `-1`, `MIN_VALUE`, `MAX_VALUE`, và các tổ hợp cộng/nhân gần ngưỡng. Khi dùng `Math.addExact` hoặc `Math.multiplyExact`, kiểm tra cả đường thành công lẫn đường ném `ArithmeticException`.

**Đo hai phương án chỉ khi ngữ nghĩa phù hợp**: so sánh phép cộng int có wrap với `Math.addExact` không phải cuộc đua tương đương nếu nghiệp vụ yêu cầu phát hiện tràn số. Trong hệ thống thực, đường ném exception có thể chiếm chi phí đáng kể nhưng không được tự ý bỏ kiểm tra chỉ vì chậm.

### 3.2. double: độ chính xác, NaN, Infinity và độ lớn

~~~java
double[] sample = {
        0.0, -0.0, 0.1, -0.1,
        Double.MIN_VALUE,
        Double.MIN_NORMAL,
        Double.MAX_VALUE,
        Double.NaN,
        Double.POSITIVE_INFINITY,
        Double.NEGATIVE_INFINITY
};
~~~

Cần thử số gần 0, subnormal, số rất lớn, nhiều giá trị triệt tiêu nhau và trường hợp tính ra `Infinity`/`NaN`. `Double.MIN_VALUE` là số dương nhỏ nhất khác 0 dạng subnormal, **không phải** giá trị âm lớn nhất về độ lớn; hãy nhớ `-Double.MAX_VALUE` khi cần giá trị âm hữu hạn cực trị.

Tổng `double` phụ thuộc thứ tự tính vì phép cộng số thực không kết hợp tuyệt đối. Chạy parallel hoặc dùng thuật toán cộng bù có thể cho kết quả hơi khác; nên xác định dung sai phù hợp thay vì kiểm tra mọi kết quả bằng `==`. Với `NaN`, so sánh thường cần `Double.isNaN(...)`.

### 3.3. BigInteger: số chữ số và phép toán cụ thể

~~~java
BigInteger small = BigInteger.valueOf(7);
BigInteger large = BigInteger.TEN.pow(1000);
BigInteger boundary = BigInteger.valueOf(Long.MAX_VALUE)
        .add(BigInteger.ONE);
~~~

Thử độ dài operand khác nhau (ví dụ 1, 20, 100, 1000 chữ số), dấu âm/dương, zero và các tổ hợp có operand chênh lệch độ dài. Chi phí phép nhân và phép chia có thể thay đổi theo cỡ số, thậm chí theo thuật toán nội bộ được JVM chọn. Chỉ benchmark phép cộng các `BigInteger` nhỏ rồi ngoại suy tới phép nhân số có hàng nghìn chữ số là thiếu căn cứ.

**Lưu ý:** `BigInteger.TEN.pow(1000)` tạo số giá trị `10^1000`, tức 1001 chữ số thập phân. Khi tạo dữ liệu theo số chữ số cần đo, phải phân biệt "lũy thừa 1000" với "có đúng 1000 chữ số".

### 3.4. BigDecimal: precision, scale, rounding và định dạng

~~~java
BigDecimal[] values = {
        new BigDecimal("0"),
        new BigDecimal("0.00"),
        new BigDecimal("-0.005"),
        new BigDecimal("1.00"),
        new BigDecimal("1E+8"),
        new BigDecimal("0.00000001"),
        new BigDecimal("999999999999999999.99")
};
~~~

Các đối tượng bằng nhau về giá trị có thể có **scale khác nhau**. Ví dụ `new BigDecimal("1.0")` và `new BigDecimal("1.00")` so sánh `compareTo() == 0`, nhưng `equals()` trả false. Benchmark chỉ một scale sẽ không đại diện cho workload có scale hỗn hợp.

Với phép chia, dữ liệu biên phải có cả kết quả thập phân hữu hạn và vô hạn:

~~~java
BigDecimal.ONE.divide(new BigDecimal("8")); // 0.125

// BigDecimal.ONE.divide(new BigDecimal("3"));
// ArithmeticException vì không biểu diễn chính xác hữu hạn.
BigDecimal rounded = BigDecimal.ONE.divide(
        new BigDecimal("3"),
        new java.math.MathContext(12, java.math.RoundingMode.HALF_EVEN));
~~~

Không thể coi một bản cài đặt "nhanh hơn" nếu nó âm thầm thay đổi scale, làm tròn ở bước khác hoặc bỏ ngoại lệ bắt buộc. Benchmark có độ lớn `BigDecimal` cao cần giới hạn thực tế để tránh vô tình dùng tài nguyên quá mức; ghi rõ giới hạn đầu vào được hệ thống hỗ trợ.

## 4. Tách chi phí tạo dữ liệu khỏi phép toán đang đo

Phép đo có thể vô tình tính cả công đoạn **parse từ chuỗi** hoặc **tạo đối tượng**:

~~~java
// Bao gồm cả parse và cộng: hợp lý nếu đây là toàn bộ đường xử lý thực.
BigDecimal result = new BigDecimal("123.45")
        .add(new BigDecimal("67.89"));
~~~

Nhưng nếu câu hỏi là "`BigDecimal.add` nhanh đến đâu với hai operand đã chuẩn bị sẵn?", phải tạo operand trước vùng thời gian đo:

~~~java
BigDecimal left = new BigDecimal("123.45");
BigDecimal right = new BigDecimal("67.89");

// Chỉ phép toán add là đối tượng của benchmark.
BigDecimal result = left.add(right);
~~~

Cả hai phép đo đều có giá trị, **nếu được đặt tên chính xác**:

- **Operation benchmark:** operand đã có sẵn; đo cộng/nhân/chia.
- **End-to-end benchmark:** gồm parse, kiểm tra dữ liệu, tính toán, làm tròn và format, phản ánh đường request thực.
- **Allocation benchmark:** theo dõi số byte/operation và GC khi tạo/biến đổi nhiều số.

Với các số bất biến, thao tác có thể tạo đối tượng kết quả mới. Nếu bạn chỉ đo thời gian CPU mà bỏ qua cấp phát, phương án "nhanh hơn" có thể gây tần suất GC cao khi hệ thống tải lớn.

Không dùng cùng một đối tượng mutable bị thay đổi liên tục trong các lần đo nếu điều đó khiến đầu vào thay đổi hoặc làm xuất hiện tranh chấp ngoài chủ ý. Tách rõ dữ liệu chuẩn bị trước, dữ liệu cho từng invocation và trạng thái mà benchmark được phép thay đổi.

## 5. Độ đúng là điều kiện trước khi so tốc độ

Mỗi candidate phải vượt qua **đối chiếu kết quả** trên cùng tập dữ liệu trước khi báo cáo tốc độ. Có thể dùng một triển khai chuẩn dễ hiểu để làm đối chứng (*oracle*), nhưng oracle cũng cần được kiểm thử.

Ví dụ đo hai cách tính tổng các `BigDecimal` đã tạo sẵn:

~~~java
import java.math.BigDecimal;
import java.util.Arrays;

BigDecimal[] input = {
        new BigDecimal("12.50"),
        new BigDecimal("-3.20"),
        new BigDecimal("0.70")
};

BigDecimal loop = BigDecimal.ZERO;
for (BigDecimal x : input) {
    loop = loop.add(x);
}

BigDecimal stream = Arrays.stream(input)
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(loop.toPlainString());   // 10.00
System.out.println(stream.toPlainString()); // 10.00
~~~

Phải kiểm tra kết quả trước. Nếu yêu cầu chỉ xét giá trị toán học, dùng `compareTo(...) == 0`. Nếu scale/format là một phần của hợp đồng, cần kiểm tra `scale()` hoặc biểu diễn chuỗi. Với một số phép toán như chia hay làm tròn ở bước trung gian, thay đổi thứ tự có thể dẫn đến kết quả khác ngay cả khi không có lỗi concurrency.

Các kiểm tra nên bao gồm:

- Tổng đúng cho tập 0 phần tử và 1 phần tử.
- Dấu âm/0; các giá trị cùng dấu và trái dấu.
- Overflow đối với primitive; xử lý exception nếu cần.
- Precision/scale và `RoundingMode` đối với thập phân.
- Đường đầu vào sai định dạng/không hợp lệ nếu có trong ứng dụng.
- Đúng trong các tình huống có xử lý song song khi triển khai sử dụng parallel.

**Không được bỏ qua validation/exception theo nghiệp vụ để khiến benchmark nhìn nhanh hơn.** Nếu hai triển khai khác hợp đồng đầu ra, kết quả thời gian không đủ để thay thế lẫn nhau.

## 6. Ví dụ Java 17+ chạy độc lập: tạo dữ liệu thường và biên, so sánh kết quả

Chương trình bên dưới kiểm tra các tập mẫu cố định và đo **thời gian thô để quan sát sơ bộ**. Số nanosecond in ra phụ thuộc máy, JDK, tải CPU và trạng thái JVM; chương trình này **không phải microbenchmark đáng tin cậy**. Mục tiêu là minh họa cách giữ tập đầu vào, kiểm tra kết quả, và phát hiện nhầm lẫn giữa dữ liệu thường với dữ liệu biên.

Tạo tệp `NumericWorkloadsDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.Arrays;

public class NumericWorkloadsDemo {
    private record Case(String name, String[] values) {}

    private static final Case[] CASES = {
        new Case("typical",
                new String[] {"12.50", "-3.20", "0.70"}),
        new Case("zeros",
                new String[] {"0.00", "0.00", "0.00"}),
        new Case("different-scale",
                new String[] {"1E+8", "0.00000001", "-0.00000001"}),
        new Case("large",
                new String[] {"999999999999999999.99", "0.01", "-1.00"}),
        new Case("empty", new String[] {})
    };

    private static BigDecimal sumLoop(BigDecimal[] values) {
        BigDecimal total = BigDecimal.ZERO;
        for (BigDecimal value : values) {
            total = total.add(value);
        }
        return total;
    }

    private static BigDecimal sumStream(BigDecimal[] values) {
        return Arrays.stream(values)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    public static void main(String[] args) {
        for (Case testCase : CASES) {
            // Chuẩn bị input bên ngoài phép đo:
            BigDecimal[] data = Arrays.stream(testCase.values())
                    .map(BigDecimal::new)
                    .toArray(BigDecimal[]::new);

            // Kiểm tra đúng trước khi đo:
            BigDecimal expected = sumLoop(data);
            BigDecimal actual = sumStream(data);
            if (expected.compareTo(actual) != 0
                    || expected.scale() != actual.scale()) {
                throw new AssertionError("Mismatch: " + testCase.name());
            }

            System.out.println(testCase.name()
                    + " | inputs=" + data.length
                    + " | sum=" + actual.toPlainString());

            // Chỉ mang tính chẩn đoán sơ bộ, không dùng để xếp hạng:
            long start = System.nanoTime();
            BigDecimal measured = sumLoop(data);
            long elapsed = System.nanoTime() - start;
            if (measured.compareTo(expected) != 0) {
                throw new AssertionError("Unexpected result");
            }
            System.out.println("  timing-ns=" + elapsed);
        }
    }
}
~~~

Chạy:

~~~bash
javac NumericWorkloadsDemo.java
java NumericWorkloadsDemo
~~~

Các dòng kết quả **ổn định về mặt số học** (cứ sau mỗi dòng sẽ có thêm một dòng `timing-ns=...` với giá trị không cố định):

~~~text
typical | inputs=3 | sum=10.00
zeros | inputs=3 | sum=0.00
different-scale | inputs=3 | sum=100000000.00000000
large | inputs=3 | sum=999999999999999999.00
empty | inputs=0 | sum=0
~~~

Kết quả thực tế sẽ có xen kẽ một dòng thời gian sau mỗi dòng số học, ví dụ `timing-ns=12345`; con số đó **không ổn định** và không được diễn giải là kết luận hiệu năng. Trên chương trình nhỏ, nhiễu từ JIT, GC, hệ điều hành, phân giải đồng hồ và overhead của phép đo có thể lớn hơn chính thao tác. Ngoài ra, chương trình chỉ tính một lần mỗi case. Để xếp hạng các phương án, dùng benchmark được thiết kế riêng, chẳng hạn JMH ở mục kế tiếp.

Đáng chú ý ở đầu vào `different-scale`: dù các số `0.00000001` và `-0.00000001` triệt tiêu nhau, tổng vẫn giữ scale 8 do quy tắc `BigDecimal.add`. Đây là lý do test cả giá trị và scale.

## 7. Dùng JMH khi cần đo vi mô đáng tin cậy

**JMH (Java Microbenchmark Harness)** là công cụ benchmark chuẩn thường dùng cho mã JVM. Nó hỗ trợ warmup, measurement iterations, forks, các kiểu kết quả (`AverageTime`, `Throughput`...), tham số đầu vào và cơ chế tiêu thụ kết quả giúp giảm rủi ro benchmark bị JVM tối ưu theo cách không đại diện.

Một benchmark tối thiểu dành cho phép cộng các `BigDecimal` đã parse trước có thể viết như sau (đây là **fragment JMH**, không chạy trực tiếp chỉ bằng `javac` của JDK; project phải thêm dependency JMH và annotation processor tương ứng):

~~~java
import java.math.BigDecimal;
import java.util.concurrent.TimeUnit;
import java.util.stream.IntStream;
import org.openjdk.jmh.annotations.*;
import org.openjdk.jmh.infra.Blackhole;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
public class DecimalAddBenchmark {
    @Param({"8", "64", "512"})
    public int elements;

    private BigDecimal[] values;

    @Setup(Level.Trial)
    public void prepare() {
        values = IntStream.range(0, elements)
                .mapToObj(i -> new BigDecimal(
                        i % 2 == 0 ? "123.45" : "-23.40"))
                .toArray(BigDecimal[]::new);
    }

    @Benchmark
    public void sumLoop(Blackhole blackhole) {
        BigDecimal total = BigDecimal.ZERO;
        for (BigDecimal value : values) {
            total = total.add(value);
        }
        blackhole.consume(total);
    }

    @Benchmark
    public void sumStream(Blackhole blackhole) {
        BigDecimal total = java.util.Arrays.stream(values)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        blackhole.consume(total);
    }
}
~~~

Ý nghĩa:

- `@Param` đo nhiều kích thước tập, thay vì một danh sách ngắn duy nhất.
- `@Setup(Level.Trial)` chuẩn bị dữ liệu **ngoài đoạn được đo**; vì thế benchmark so sánh phần cộng đã có operand.
- `Blackhole.consume(...)` ngăn việc vô tình bỏ đi kết quả được tính, giúp benchmark diễn đạt rằng kết quả có giá trị.
- `@BenchmarkMode(Mode.AverageTime)` yêu cầu thời gian trung bình của invocation trong các measurement; không phải thời gian latency p99 của hệ thống thật.
- `@State(Scope.Thread)` cho mỗi worker một state riêng. Khi cần mô phỏng tranh chấp trên một state chia sẻ, phải chọn state/luồng thích hợp theo tình huống muốn đo, nhưng benchmark đó là câu hỏi khác.

Ví dụ này **chưa đại diện cho mọi dữ liệu thực tế**, vì mỗi phần tử chỉ là một trong hai chuỗi ngắn. Để đo workload thực, thay `prepare()` bằng bộ dữ liệu có phân bố precision, scale, dấu và độ dài lấy từ phân tích dữ liệu nguồn; các nhóm biên nên tách thành các tham số case khác nhau. Với đầu vào random, tạo theo **seed cố định** trước giai đoạn đo để các candidate làm việc trên cùng dữ liệu; tránh tạo random trong chính benchmark nếu không chủ đích đo bộ sinh số ngẫu nhiên.

### 7.1. Quy trình đo có thể tái lập

1. **Định nghĩa phép toán và output:** nêu tên trường hợp, input, đơn vị đo, đúng/sai, và điều kiện hoàn thành.
2. **Chuẩn bị corpus:** dữ liệu thường có tỷ lệ thực tế, case kích thước khác nhau, case biên và case lỗi rõ ràng.
3. **Xác thực correctness:** chạy oracle/test cho mọi triển khai, bao gồm giá trị và scale khi cần.
4. **Warmup:** cho JVM biên dịch và tối ưu các đường mã được gọi thường xuyên trước khi thu kết quả.
5. **Measurement:** chạy nhiều iteration và nhiều fork JVM độc lập, ghi nhận độ phân tán và sai số do harness báo.
6. **Ghi môi trường:** JDK/vendor/version, CPU, RAM, JVM flags, hệ điều hành, GC, số thread, kích thước heap và nguồn dữ liệu.
7. **Đo allocation/GC:** dùng profiler hoặc tính năng profiling của JMH nếu việc tạo `BigDecimal`/`BigInteger` là chi phí đáng kể.
8. **Lặp lại trên tải mục tiêu:** kiểm tra workload đầu-cuối và tải đồng thời phù hợp, vì kết quả microbenchmark chỉ mô tả đoạn mã được đo.

Không chọn một kết quả duy nhất sau một vòng chạy làm kết luận. Nếu chênh lệch nhỏ so với độ biến động của phép đo, phải coi chưa đủ bằng chứng.

### 7.2. Cạm bẫy của microbenchmark

| Cạm bẫy | Vì sao nguy hiểm | Cách phòng tránh |
|---|---|---|
| Benchmark code chỉ dùng hằng số | JVM có thể constant-fold hoặc tối ưu phần tính | Dữ liệu biến thiên từ `@State`/`@Param`, tiêu thụ kết quả |
| Không sử dụng output | JVM có thể loại phép tính không quan sát được | Trả kết quả từ benchmark hoặc dùng `Blackhole` |
| Không warmup | Đo cả interpreter/class loading/JIT | Cấu hình warmup + measurement riêng |
| Một lần `nanoTime` với vài phép toán | Chi phí đồng hồ và nhiễu áp đảo | JMH với iterations/forks |
| Tạo đối tượng bên trong phép đo dù chỉ muốn tính toán | Kết quả đo chủ yếu parse/cấp phát | Chuẩn bị trong `@Setup` khi hợp đồng cần |
| Chuẩn bị sẵn input dù mục tiêu là end-to-end | Bỏ qua parse/format/validation | Benchmark riêng đường request thực |
| Dùng random mỗi lần trong benchmark | Đo cả random, dữ liệu candidate khác nhau | Tạo corpus seed cố định ngoài đoạn đo |
| Chạy hai candidate trên tải hệ thống khác nhau | Nhiễu khiến kết quả khó so sánh | Môi trường ổn định, nhiều lần thử/forks |
| Đồng nhất average với p99 | Không đo được tail latency thực của hệ thống | Đo latency distribution ở cấp request |
| So code có quy tắc overflow/rounding khác | "Nhanh hơn" nhờ đổi semantics | Correctness gate trước performance |
| Chọn một dataset cực trị làm đại diện duy nhất | Không phản ánh tần suất sản xuất | Cả mixed workload và case biên riêng |

## 8. Chọn thước đo gắn với mục tiêu

Không có một chỉ số tốc độ phù hợp mọi hệ thống. Khi báo cáo, xác định **đơn vị và phạm vi**:

| Chỉ số | Trả lời câu hỏi | Khi hữu ích |
|---|---|---|
| `ns/op` hoặc `µs/op` | Một lần tính toán trong benchmark vi mô tốn bao lâu? | So hai thuật toán cho cùng thao tác |
| `ops/s` | Một worker/hệ thống xử lý được bao nhiêu phép trong một giây? | Throughput tổng hợp |
| `bytes/op` | Mỗi thao tác cấp phát bao nhiêu bộ nhớ? | `BigDecimal`/`BigInteger` tạo nhiều đối tượng |
| `GC pauses`, allocation rate | Dữ liệu lớn hoặc nhiều lần cấp phát gây áp lực GC ra sao? | Dịch vụ chạy lâu, tải cao |
| `p50/p95/p99 latency` | Nửa, 95%, 99% request hoàn thành trong bao lâu? | Đảm bảo thời gian phản hồi |
| `CPU utilization`, request concurrency | Tải đồng thời ảnh hưởng hiệu năng thế nào? | Phục vụ thực tế trên server |

Ví dụ một phép nhân `BigInteger` hiếm gặp mất nhiều thời gian có thể ít ảnh hưởng đến throughput trung bình nhưng làm đuôi latency tăng. Ngược lại, thêm một allocation nhỏ ở mỗi phép tính lặp hàng triệu lần có thể gây GC đáng kể dù mỗi invocation rất nhanh.

**Không diễn giải trung bình số học của một microbenchmark thành p99 của request.** Request có thể chứa parse, I/O, queueing, phân phối nhiều phép tính và pause GC. Nếu hệ thống có SLO p99, đo bằng công cụ tạo tải ở tầng yêu cầu thực với tỷ lệ request và mức concurrency đúng.

## 9. Tập biên phải thử cả lỗi, không chỉ số lớn

Dữ liệu biên gồm cả **đường lỗi có ý nghĩa nghiệp vụ**:

- `new BigDecimal("invalid")` ném `NumberFormatException`.
- `BigDecimal.ONE.divide(new BigDecimal("3"))` ném `ArithmeticException` nếu yêu cầu chia chính xác hữu hạn.
- `Math.addExact(Integer.MAX_VALUE, 1)` ném `ArithmeticException`.
- `BigDecimal` với precision/scale rất lớn có thể gây áp lực bộ nhớ hoặc gặp giới hạn thực thi/biểu diễn.
- `DoubleStream` chứa `NaN` có thể làm phép tổng hợp trả `NaN`, cần xử lý theo quy tắc ứng dụng.

Phải xác định tỷ lệ lỗi trong sản phẩm: nhiều trường hợp hiếm nhưng hợp lệ cần có benchmark riêng, còn yêu cầu sai định dạng có thể cần được đo ở đường kiểm tra đầu vào. Tuy nhiên, không cố tạo vô hạn dữ liệu nguy hiểm chỉ để chứng minh một điểm; thiết kế giới hạn đầu vào hợp lệ và thử ở ngay các mốc đó.

Nếu tài nguyên khan hiếm, dùng một bộ kiểm thử chức năng đầy đủ cho input cực đoan và một bộ benchmark giới hạn có thể tái lập; ghi rõ giới hạn đã đo để tránh ngoại suy quá xa.

## 10. Thiết kế thí nghiệm so sánh hai cách hiện thực

Giả sử mục tiêu là chọn giữa vòng lặp `for` và `Stream.reduce` để cộng một mảng `BigDecimal`.

### Bước 1 — định nghĩa hợp đồng

Đầu vào là `BigDecimal[]` đã được parse; phần tử không `null`. Cả hai giải pháp dùng cộng chính xác (`add` không có `MathContext`) và kết quả phải cùng giá trị **và scale**. Không thay đổi dữ liệu đầu vào.

### Bước 2 — thiết kế tập đo

- **Typical:** mảng có độ dài xuất hiện thường xuyên, chủ yếu precision thấp và scale 2.
- **Large batch:** số phần tử lớn đại diện batch đỉnh.
- **Mixed scale:** bao gồm scale âm, scale 0, scale 2, scale cao.
- **Long precision:** `BigDecimal` có hàng trăm/hàng nghìn chữ số ở những ngưỡng được phép.
- **Empty/single:** 0 hoặc 1 phần tử; kiểm tra overhead của pipeline.
- **Mixed sign:** số dương/âm/0, gồm trường hợp gần triệt tiêu nhau.

Mỗi case được đo riêng. Sau đó có thể xây dựng workload hỗn hợp theo tỷ lệ production để ước tính hiệu ứng tổng quát.

### Bước 3 — kiểm tra correctness trước

So `compareTo` và `scale` hoặc so chuỗi chuẩn nếu hợp đồng yêu cầu. Tránh chuẩn hóa bằng `stripTrailingZeros()` trong bài test nếu việc bảo toàn scale là bắt buộc: thao tác này thay đổi biểu diễn.

### Bước 4 — benchmark và đo phụ

Dùng JMH để đo thời gian mỗi lần cộng mảng cùng dữ liệu. Bật thêm profiling allocation khi cần. Với microbenchmark trên một vài operand, chênh lệch có thể rất nhỏ; với batch lớn, chi phí stream setup, vòng lặp và số lượng đối tượng kết quả đều góp vào kết quả.

### Bước 5 — diễn giải trong phạm vi chứng cứ

Một báo cáo tốt không chỉ viết "A nhanh hơn B 30%". Nó nêu **dataset**, **JDK/CPU**, **mode**, **số lần thử**, **độ biến động**, **allocation**, **correctness**, và trường hợp nào thắng/thua. Kết luận có thể là "Với batch 100 phần tử, A nhanh hơn có ý nghĩa; với batch 10.000 phần tử kết quả tương đương trong sai số", thay vì một lựa chọn tuyệt đối.

Bảng ghi nhận kết quả (điền bằng số đo thực, **không tự bịa giá trị**):

| Case | Size | Precision/scale | Cách A ns/op | Cách B ns/op | bytes/op | Correctness | Ghi chú |
|---|---:|---|---:|---:|---:|---|---|
| Typical | Theo dữ liệu thực | Ngắn, scale 2 | *Điền số đo* | *Điền số đo* | *Điền số đo* | PASS/FAIL | Warmup/fork |
| Mixed scale | Theo dữ liệu thực | Scale hỗn hợp | *Điền số đo* | *Điền số đo* | *Điền số đo* | PASS/FAIL | Kiểm tra scale |
| Large precision | Theo dữ liệu thực | Hàng trăm chữ số | *Điền số đo* | *Điền số đo* | *Điền số đo* | PASS/FAIL | Bộ nhớ/GC |
| Empty/single | 0 hoặc 1 | Biên cardinality | *Điền số đo* | *Điền số đo* | *Điền số đo* | PASS/FAIL | Overhead |

Đây là khung **ghi chép đo kiểm**, không phải kết quả benchmark. Không được thay các ô bằng số ước đoán rồi khẳng định đã đo trên môi trường sản xuất.

## 11. Các lỗi phổ biến và cách khắc phục

| Lỗi | Tác động | Cách khắc phục |
|---|---|---|
| Dùng duy nhất một giá trị số nhỏ | Bỏ qua các nhánh/độ phức tạp ở dữ liệu khác | Dùng phân bố thực + nhiều bucket |
| Đo tập biên rồi lấy làm "hiệu năng trung bình" | Sai tỷ lệ xảy ra | Tách kết quả biên với workload theo trọng số |
| Chỉ đo average time | Bỏ qua request chậm và GC pause | Thu p95/p99 ở tầng hệ thống khi có SLO |
| Dùng `new BigDecimal("1.00")` bên trong vòng loop không chủ đích | Lẫn chi phí parse với phép toán | Chọn rõ operation vs end-to-end |
| Benchmark nhận hằng, output bỏ đi | JIT có thể tối ưu mất thao tác | Dùng JMH `@State`, `@Param` và consume kết quả |
| Không kiểm tra output trước benchmark | Chọn phương án sai số học | Correctness gate và oracle |
| Bỏ qua overflow/trường hợp vô hạn | Sản phẩm sai dù benchmark nhanh | Test ở ranh giới và tình huống lỗi |
| So `double` với `BigDecimal` như cùng semantics | Đánh đổi precision không được công bố | Làm rõ hợp đồng số học |
| Mặc định parallel nhanh | Có overhead, tranh chấp và kết quả số thực thay đổi | Đo theo workload + core count |
| Thay data giữa các candidate | Không còn so cùng công việc | Dùng seed/dataset cố định |
| Không ghi JDK/flags/CPU | Khó tái lập kết luận | Lưu đầy đủ cấu hình |
| Báo "ns/op" như latency thật | Microbenchmark không mô phỏng request | Đo cả end-to-end dưới tải thật |

## 12. Bài tập tự kiểm tra

**Câu 1.** Vì sao một phép cộng `BigInteger` nhanh với các số có một chữ số không chứng minh nó nhanh với operand có hàng nghìn chữ số?

**Đáp án:** Chi phí số học phụ thuộc vào độ dài biểu diễn và thuật toán được dùng. Benchmark phải có các bucket độ dài đại diện cho miền được hỗ trợ.

**Câu 2.** Một hệ thống trả tiền bằng `BigDecimal` có scale bắt buộc 2. Nếu bản tối ưu trả cùng giá trị nhưng scale 1, có được coi là đúng không?

**Đáp án:** Nếu scale là một phần hợp đồng, không. Cần xác nhận giá trị và scale trước khi đo hiệu năng.

**Câu 3.** Benchmark chỉ gọi `sumLoop(input)` với operand parse sẵn. Nó đo được chi phí parse từ request không?

**Đáp án:** Không. Benchmark đó đo bước cộng trên dữ liệu đã chuẩn bị. Muốn đo end-to-end, phải đưa parse và các bước thực tế vào vùng được đo trong một benchmark riêng.

**Câu 4.** `IntStream.of(Integer.MAX_VALUE, 1).sum()` trả gì và có ý nghĩa gì đối với benchmark?

**Đáp án:** Trả `-2147483648` do overflow `int`. Một bản cài đặt có hiệu năng tốt nhưng kết quả này sai với nghiệp vụ cần tổng số nguyên lớn, nên phải sửa contract/kiểu dữ liệu trước khi xếp hạng hiệu năng.

**Câu 5.** Nếu 1% request có dữ liệu lớn và chậm, chỉ đo 99% dữ liệu phổ biến có đủ để báo latency p99 không?

**Đáp án:** Không. Phải quan sát phân bố latency trên toàn bộ request theo tỷ lệ thực và kiểm tra tail latency; đo riêng trường hợp lớn cũng hữu ích để hiểu nguyên nhân.

**Câu 6.** Tại sao cần warmup/forks khi benchmark mã Java ngắn?

**Đáp án:** JVM có thể khởi chạy ở interpreter, sau đó JIT tối ưu; trạng thái heap và cache có thể khác giữa lần chạy. Warmup và forks giúp giảm thiên lệch, nhưng vẫn cần báo độ biến động.

**Câu 7.** Một phương án dùng ít CPU hơn nhưng cấp phát gấp nhiều lần. Có thể tuyên bố nó chắc chắn tốt hơn không?

**Đáp án:** Chưa. Cấp phát thêm có thể làm tăng GC và p99 latency khi tải lớn. Cần đối chiếu nhiều chỉ số và giới hạn sản phẩm.

---

**Ghi nhớ:** Benchmark số học trong Java phải dùng **miền dữ liệu đại diện** và **tình huống biên được lựa chọn có lý do**, kiểm tra đúng giá trị/precision/scale/exception **trước khi so tốc độ**, rồi đo có warmup, nhiều lần thử và ghi rõ môi trường. Để ra quyết định thực tế, kết hợp microbenchmark với dữ liệu end-to-end, throughput, tail latency, allocation và GC; không suy rộng từ một phép cộng hoặc một `System.nanoTime()` đơn lẻ.