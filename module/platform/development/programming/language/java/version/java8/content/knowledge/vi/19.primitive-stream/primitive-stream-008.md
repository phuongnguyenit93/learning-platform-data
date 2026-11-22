# NaN, vô cực, tràn và sai số trong Primitive Stream (Java 8+)

`IntStream`, `LongStream` và `DoubleStream` là ba loại **primitive stream** có từ Java 8 và vẫn được hỗ trợ trong Java hiện hành. Chúng giúp xử lý `int`, `long`, `double` mà không cần boxing từng phần tử thành `Integer`, `Long`, `Double`. Tuy nhiên, việc dùng Stream **không thay đổi quy tắc số học của Java**: số nguyên có thể tràn, số thực có thể thành `NaN` hoặc vô cực, và phép tính `double` có sai số biểu diễn/làm tròn.

Đây là những tình huống rất quan trọng khi tính tổng, trung bình, min/max, thống kê, chuyển kiểu và xử lý dữ liệu ngoài hệ thống. Kết quả sai có thể trông vẫn hợp lệ nếu ứng dụng chỉ gọi `sum()` mà không kiểm tra miền giá trị.

## 1. Phân biệt các vấn đề số học

| Vấn đề | Ví dụ | Hậu quả thường gặp |
|---|---|---|
| `NaN` (*Not a Number*) | `0.0 / 0.0`, `Math.sqrt(-1.0)` | Kết quả không đại diện cho số hữu hạn; nhiều so sánh trả false |
| Vô cực dương/âm | `1.0 / 0.0`, `-1.0 / 0.0` | `double` vượt miền hữu hạn hoặc đến từ phép chia cho 0.0 |
| Tràn `int`/`long` | `Integer.MAX_VALUE + 1` | Số nguyên quay vòng theo biểu diễn hai bù; không tự ném exception |
| Tràn `double` | `Double.MAX_VALUE * 2` | Thành `Infinity`, không ném lỗi số học |
| Underflow của `double` | `Double.MIN_VALUE / 2` | Giá trị quá nhỏ, làm tròn thành 0.0; đôi khi thành subnormal |
| Sai số dấu phẩy động | `0.1 + 0.2` | Kết quả có thể là `0.30000000000000004` thay vì đúng 0.3 |
| Mất độ chính xác số nguyên lớn | Chuyển long lớn sang double | Hai số nguyên khác nhau có thể trở thành cùng một `double` |

**Không nhầm lẫn:** `NaN` và `Infinity` là các giá trị đặc biệt của `float`/`double`. `int` và `long` **không có** giá trị NaN hoặc vô cực. Không có `FloatStream` riêng trong Java Stream API; nếu nguồn là `float`, thường phải chọn kiểu chuyển đổi thích hợp, ví dụ sang `DoubleStream`, rồi tính toán theo quy tắc của `double`.

## 2. NaN: phát sinh, lan truyền và cách kiểm tra

### 2.1. NaN là gì?

`Double.NaN` biểu thị một kết quả dấu phẩy động không có giá trị số được xác định theo IEEE 754, như:

~~~java
double a = 0.0 / 0.0;       // NaN
double b = Math.sqrt(-1.0); // NaN
double c = Double.NaN;
~~~

Đây là **mảnh mã đặt trong phương thức**, không phải chương trình độc lập. `NaN` **không phải null**, không phải 0 và không đồng nghĩa với dữ liệu bị thiếu. Nó có thể xuất hiện vì phép toán không xác định hoặc đã có sẵn trong dữ liệu nguồn.

Không kiểm tra NaN bằng `value == Double.NaN`:

~~~java
double value = Double.NaN;

System.out.println(value == Double.NaN); // false
System.out.println(value != Double.NaN); // true
System.out.println(Double.isNaN(value));  // true
~~~

Đoạn mã đặt trong `main`. Với quy tắc so sánh số học Java, **NaN không bằng chính nó khi dùng `==`**; các so sánh số học như `<`, `>`, `<=`, `>=` với NaN đều trả `false`. Dùng `Double.isNaN(value)` để kiểm tra. `Double.compare` có quy tắc thứ tự tổng riêng: hai NaN được coi là bằng nhau theo phương thức này, và NaN đứng sau mọi giá trị khác, kể cả `+Infinity`.

### 2.2. NaN trong DoubleStream

~~~java
double total = java.util.stream.DoubleStream
        .of(2.0, Double.NaN, 4.0)
        .sum();

boolean invalid = Double.isNaN(total); // true
~~~

Đây là mảnh mã độc lập khi đặt trong phương thức. Theo hợp đồng hiện hành, nếu dữ liệu đưa vào `DoubleStream.sum()` chứa NaN thì tổng trả NaN. `DoubleStream.min()` và `max()` cũng trả `OptionalDouble` chứa NaN khi có bất kỳ phần tử nào là NaN; `OptionalDouble` chỉ rỗng nếu **không có phần tử**, chứ không tự loại NaN.

`DoubleStream.summaryStatistics()` tổng hợp count, sum, min, max và average. Khi có NaN, các thống kê liên quan có thể thành NaN. **Đừng nhầm `count` vẫn có giá trị với việc số liệu đã hợp lệ**: số phần tử vẫn đếm được dù giá trị của chúng là NaN.

### 2.3. Kiểm tra NaN và số hữu hạn

Các API còn áp dụng:

~~~java
Double.isNaN(value);       // Chỉ NaN.
Double.isInfinite(value);  // Chỉ vô cực dương hoặc âm.
Double.isFinite(value);    // Chỉ các giá trị hữu hạn.
~~~

Đây là các lời gọi minh họa khi đã có biến `double value`.

Có thể lọc giá trị không hữu hạn trong một pipeline:

~~~java
double validOnlySum = java.util.stream.DoubleStream
        .of(1.5, Double.NaN, Double.POSITIVE_INFINITY, 2.5)
        .filter(Double::isFinite)
        .sum(); // 4.0
~~~

**Chỉ lọc nếu nghiệp vụ cho phép bỏ những phần tử ấy.** Nếu dữ liệu tài chính, đo lường, hóa đơn hoặc tín hiệu đầu vào bắt buộc hợp lệ, silently drop NaN/Infinity sẽ khiến thống kê không phản ánh nguồn. Chính sách tốt hơn thường là **phát hiện và từ chối dữ liệu có lỗi**, đồng thời ghi nhận vị trí/nguồn dữ liệu.

## 3. Vô cực dương và âm

### 3.1. Nguồn gốc và sự khác biệt với chia số nguyên

~~~java
System.out.println(1.0 / 0.0);  // Infinity
System.out.println(-1.0 / 0.0); // -Infinity
System.out.println(0.0 / 0.0);  // NaN
~~~

Ở kiểu số thực, phép chia cho `0.0` có thể cho vô cực hoặc NaN theo quy tắc IEEE 754. Trái lại, biểu thức chia **số nguyên** cho 0, ví dụ `int denominator = 0; int n = 1 / denominator;`, ném `ArithmeticException` khi thực thi.

`Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY` có thứ tự theo phép so sánh số học và không bằng NaN. `Double.isInfinite(x)` nhận biết cả hai dấu. `Double.isFinite(x)` trả `false` với NaN hoặc bất kỳ vô cực nào.

### 3.2. Tổng, trung bình, min và max có thể phi hữu hạn

~~~java
double total = java.util.stream.DoubleStream
        .of(Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY)
        .sum();

System.out.println(Double.isNaN(total)); // true
~~~

Vô cực **khác dấu** cộng với nhau cho NaN. Khi tổng chứa một hay nhiều vô cực cùng dấu, kết quả thường là vô cực cùng dấu; với dữ liệu phức tạp, quy tắc `DoubleStream.sum()` còn cho phép NaN do các tổng trung gian tràn trong quá trình gộp.

Đặc biệt, **ngay cả khi mọi phần tử đều hữu hạn**, tổng các số quá lớn vẫn có thể tràn thành vô cực, hoặc trong các cách gộp trung gian nhất định có thể dẫn tới NaN. Đừng chỉ xét `anyMatch(Double::isNaN)` trên đầu vào rồi mặc định tổng luôn hữu hạn.

`DoubleStream.average()` trả `OptionalDouble.empty()` nếu Stream rỗng; nếu không rỗng, giá trị trung bình tính bằng `double` cũng chịu giới hạn số thực. Khi yêu cầu kết quả hữu hạn, hãy kiểm cả **đầu vào** lẫn **kết quả** tính toán.

### 3.3. Zero có dấu và cách so sánh

IEEE 754 phân biệt `+0.0` với `-0.0` ở biểu diễn bit. `-0.0 == +0.0` trả true, nhưng dấu có thể ảnh hưởng đến phép chia: `1.0 / -0.0` là `-Infinity`.

`DoubleStream.min()` coi `-0.0` nhỏ hơn `+0.0`; `max()` chọn `+0.0` nếu cả hai có mặt. Khi muốn kiểm đúng dấu, dùng:

~~~java
double result = java.util.stream.DoubleStream
        .of(-0.0, +0.0)
        .min().orElseThrow();

boolean negativeZero = Double.doubleToRawLongBits(result)
        == Double.doubleToRawLongBits(-0.0);
~~~

Đoạn code dùng `OptionalDouble.orElseThrow()` và chạy trong `main` trên JDK 17+. Không dùng `result == -0.0` để kiểm dấu, vì hai giá trị zero bằng nhau theo `==`.

## 4. Tràn số nguyên trong IntStream và LongStream

### 4.1. `sum()` vẫn tuân thủ số học nguyên Java

~~~java
int wrapped = java.util.stream.IntStream
        .of(Integer.MAX_VALUE, 1)
        .sum(); // -2147483648
~~~

`IntStream.sum()` tương đương về ý nghĩa với `reduce(0, Integer::sum)`. `Integer.MAX_VALUE` là `2_147_483_647`, cộng 1 không thể biểu diễn bằng `int` nên quay về `Integer.MIN_VALUE`, tức `-2_147_483_648`. **Không có `ArithmeticException` tự động.**

Tương tự:

~~~java
long wrappedLong = java.util.stream.LongStream
        .of(Long.MAX_VALUE, 1L)
        .sum(); // -9223372036854775808
~~~

`LongStream.sum()` cũng có thể tràn trong phạm vi 64 bit. Điều này đặc biệt nguy hiểm khi tính tổng tiền theo đơn vị nhỏ nhất, số lượng giao dịch hay bộ đếm khối lượng lớn.

### 4.2. Mở rộng kiểu trước khi cộng

Nếu mỗi phần tử là `int` nhưng tổng có thể lớn hơn `Integer.MAX_VALUE`, chuyển sang `LongStream` **trước** khi gọi `sum()`:

~~~java
long total = java.util.stream.IntStream
        .of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum(); // 2147483648
~~~

Điểm mấu chốt là thứ tự: `.asLongStream().sum()` cộng bằng `long`; còn `.sum()` rồi mới cast sang `long` **đã tràn trước khi đổi kiểu**.

Tương tự khi nhân:

~~~java
long correct = java.util.stream.IntStream.of(50_000)
        .mapToLong(n -> (long) n * n)
        .sum(); // 2500000000
~~~

Phải cast **ít nhất một toán hạng trước phép nhân**. `mapToLong(n -> n * n)` sẽ thực hiện phép nhân `int` trước, có thể tràn, rồi mới đưa giá trị sai sang `long`.

Mở rộng sang `long` chỉ giải quyết khi **tổng thật vẫn nằm trong phạm vi long**. Nếu còn có thể vượt `Long.MAX_VALUE`, cần mô hình số lớn hơn, chẳng hạn `BigInteger`, hoặc phát hiện lỗi và từ chối phép tính.

### 4.3. Phát hiện tràn một cách tường minh

`Math.addExact(int, int)` và `Math.addExact(long, long)` ném `ArithmeticException` khi phép cộng không biểu diễn được trong kiểu tương ứng. Có thể dùng với `reduce`:

~~~java
try {
    int total = java.util.stream.IntStream
            .of(Integer.MAX_VALUE, 1)
            .reduce(0, Math::addExact);
    System.out.println(total);
} catch (ArithmeticException expected) {
    System.out.println("Overflow detected");
}
~~~

Đây là đoạn chạy được trong `main`. Nếu kết quả cần giới hạn `int`, cách này rõ ràng hơn việc lặng lẽ nhận số âm sau khi tràn. Khi dùng parallel reduction, phép cộng exact có thể phát hiện tràn ở một nhánh trung gian dù các số dương/âm khác sau cùng bù trừ; cần chọn quy tắc kiểm tra phù hợp miền dữ liệu thực tế. Với bài toán yêu cầu **tổng toán học chính xác**, có thể tích lũy bằng `BigInteger` thay vì dựa vào gộp trung gian trong kiểu quá nhỏ.

**Lưu ý:** `IntSummaryStatistics.getSum()` trả `long` và do đó có miền rộng hơn `IntStream.sum()`, nhưng vẫn không miễn nhiễm tràn `long` khi tổng quá lớn. `LongSummaryStatistics` cũng dùng `long` cho sum.

## 5. Sai số biểu diễn và làm tròn của double

### 5.1. Vì sao 0.1 + 0.2 không đúng bằng 0.3?

`double` theo IEEE 754 binary64 có độ chính xác hữu hạn, khoảng 15–17 chữ số thập phân có nghĩa. Phần lớn phân số thập phân như `0.1` và `0.2` **không biểu diễn chính xác bằng nhị phân hữu hạn**. Việc làm tròn khi lưu và cộng dẫn đến:

~~~java
System.out.println(0.1 + 0.2);
// 0.30000000000000004
~~~

Không phải Stream tự tạo ra vấn đề này. `DoubleStream` thao tác trên các giá trị `double` sẵn có nên cũng chịu sai số ấy.

### 5.2. `DoubleStream.sum()` không có bảo đảm cùng bit ở mọi cách tính

Phép cộng dấu phẩy động nói chung **không kết hợp tuyệt đối** vì làm tròn. Đổi thứ tự tính hoặc chia dữ liệu cho parallel Stream có thể làm tổng sai khác một chút.

Ví dụ về mất độ chính xác khi cộng số lớn với số nhỏ:

~~~java
double a = 1e16;
double b = 1.0;
double c = -1e16;

double leftGrouped = (a + b) + c;
double rightGrouped = a + (b + c);
~~~

Đây là ví dụ minh họa cách **kết hợp phép cộng** cho kết quả có thể khác, không phải lời hứa hai phép tính sẽ luôn thể hiện cùng sai số trên mọi dữ liệu. Theo tài liệu hiện hành, `DoubleStream.sum()` **không quy định thứ tự cộng và thuật toán gộp cụ thể**; implementation có thể dùng compensated summation để cải thiện độ chính xác. Vì thế **không được kiểm thử `DoubleStream.sum()` bằng cách giả định nó luôn là vòng lặp `total += value` với một thứ tự cố định**.

Một cách giảm sai số trong một số tình huống là cộng các giá trị từ nhỏ đến lớn theo **độ lớn tuyệt đối**, nhưng đây không phải giải pháp bảo đảm kết quả chính xác tuyệt đối. Nếu ứng dụng cần kết quả lặp lại bit-for-bit hoặc kiểm toán được, hãy quy định thuật toán, thứ tự và kiểu số phù hợp ngoài việc chỉ gọi `sum()`.

### 5.3. Underflow và số nguyên mất chính xác khi đổi sang double

`Double.MAX_VALUE` là số `double` hữu hạn dương lớn nhất. `Double.MIN_VALUE` **không phải số âm nhỏ nhất**; nó là số dương nhỏ nhất khác 0 có thể biểu diễn (subnormal). Khi chia tiếp cho 2:

~~~java
double tiny = Double.MIN_VALUE / 2.0;
System.out.println(tiny); // 0.0
~~~

Đây là **underflow** (độ lớn quá nhỏ so với miền biểu diễn), khác với tràn lên vô cực.

`double` có 53 bit significand. Các số nguyên đủ lớn không còn được biểu diễn một cách phân biệt theo từng đơn vị:

~~~java
double value = 9_007_199_254_740_992d; // 2^53
System.out.println(value + 1.0 == value); // true
~~~

Điều đó giải thích vì sao **không chuyển `long` lớn sang `double` để thực hiện đối soát ID hoặc tổng chính xác**. Chuyển `LongStream` thành `DoubleStream` để dùng thống kê có thể mất độ chính xác với số nguyên rất lớn; hãy xác định độ chính xác chấp nhận được trước khi chuyển.

### 5.4. So sánh số thực theo chính sách dung sai

Để so sánh gần đúng hai kết quả hữu hạn, ứng dụng có thể dùng ngưỡng tuyệt đối hoặc kết hợp ngưỡng tương đối:

~~~java
static boolean nearlyEqual(double a, double b,
                           double absoluteTolerance) {
    return Double.isFinite(a)
            && Double.isFinite(b)
            && absoluteTolerance >= 0.0
            && Math.abs(a - b) <= absoluteTolerance;
}
~~~

Đây là **mẫu phương thức** có thể đưa vào một class, không phải chương trình độc lập. Ngưỡng phải được chọn dựa trên **đơn vị và quy tắc của bài toán**, không có một epsilon phù hợp cho mọi đại lượng. Với số rất lớn hoặc rất gần 0, thường cần kết hợp ngưỡng tuyệt đối và tương đối, cân nhắc tràn khi tính `a - b`. Không dùng kiểu so sánh gần đúng để bỏ qua NaN/Infinity hoặc biến số liệu không hợp lệ thành hợp lệ.

### 5.5. Khi cần giá trị thập phân chính xác

Đối với tiền tệ và quy tắc làm tròn thập phân, thường nên dùng `BigDecimal` hoặc số nguyên đại diện đơn vị nhỏ nhất (ví dụ đồng/cent), thay vì tin vào `double`.

~~~java
java.math.BigDecimal exact = java.util.stream.Stream
        .of("0.1", "0.2")
        .map(java.math.BigDecimal::new)
        .reduce(java.math.BigDecimal.ZERO,
                java.math.BigDecimal::add);

System.out.println(exact.toPlainString()); // 0.3
~~~

Đây là đoạn chạy được khi đặt trong `main`. `BigDecimal` thuộc **object Stream**, không có `BigDecimalStream` primitive. Khi bắt đầu từ giá trị thập phân được biểu diễn trong chuỗi, `new BigDecimal(String)` giữ ý nghĩa chữ số thập phân đã cung cấp. Nếu nhận một `double` hữu hạn, `BigDecimal.valueOf(double)` thường phù hợp hơn `new BigDecimal(double)` cho cách biểu diễn decimal round-trip, nhưng không thể phục hồi độ chính xác đã mất ở các phép tính `double` trước đó. `BigDecimal.valueOf(Double.NaN)` hoặc đối số vô cực không tạo được số thập phân hợp lệ; hãy validate trước khi chuyển.

Khi kết quả cần cố định số chữ số thập phân, chọn `setScale(scale, RoundingMode)` phù hợp **chính sách nghiệp vụ**; đừng mặc định mọi ứng dụng đều phải làm tròn như nhau.

## 6. Chương trình chạy được: các trường hợp biên quan trọng

Tạo file `PrimitiveStreamEdgeDemo.java`. Chương trình dùng API hiện hành, chạy trên **JDK 17+**; các Stream API và `Double.isFinite` liên quan đều có từ Java 8. Chương trình cố ý in kiểu kết quả ở những ca biên đã xác định rõ, thay vì dự đoán đầu ra không ổn định của parallel sum.

~~~java
public class PrimitiveStreamEdgeDemo {
    public static void main(String[] args) {
        int wrapped = java.util.stream.IntStream
                .of(Integer.MAX_VALUE, 1).sum();
        long widened = java.util.stream.IntStream
                .of(Integer.MAX_VALUE, 1).asLongStream().sum();

        System.out.println("IntStream sum: " + wrapped);
        System.out.println("As LongStream sum: " + widened);

        try {
            java.util.stream.IntStream.of(Integer.MAX_VALUE, 1)
                    .reduce(0, Math::addExact);
            System.out.println("No overflow");
        } catch (ArithmeticException expected) {
            System.out.println("Math.addExact: overflow detected");
        }

        long longWrapped = java.util.stream.LongStream
                .of(Long.MAX_VALUE, 1L).sum();
        System.out.println("LongStream sum: " + longWrapped);

        System.out.println("0.1 + 0.2 = " + (0.1 + 0.2));

        double nanSum = java.util.stream.DoubleStream
                .of(1.0, Double.NaN, 3.0).sum();
        System.out.println("NaN sum? " + Double.isNaN(nanSum));

        double oppositeInfinities = java.util.stream.DoubleStream
                .of(Double.POSITIVE_INFINITY,
                        Double.NEGATIVE_INFINITY).sum();
        System.out.println("Opposite infinities NaN? "
                + Double.isNaN(oppositeInfinities));

        double hugeSum = java.util.stream.DoubleStream
                .of(Double.MAX_VALUE, Double.MAX_VALUE).sum();
        System.out.println("Double overflow infinite? "
                + Double.isInfinite(hugeSum));

        long finiteCount = java.util.stream.DoubleStream
                .of(1.5, Double.NaN,
                        Double.POSITIVE_INFINITY, 2.5)
                .filter(Double::isFinite).count();
        System.out.println("Finite count: " + finiteCount);

        boolean maxIsNaN = Double.isNaN(
                java.util.stream.DoubleStream
                        .of(2.0, Double.NaN, 4.0)
                        .max().orElseThrow());
        System.out.println("Max propagates NaN? " + maxIsNaN);

        double minZero = java.util.stream.DoubleStream
                .of(-0.0, +0.0).min().orElseThrow();
        System.out.println("Min signed zero: " + minZero);

        System.out.println("Empty average: "
                + java.util.stream.DoubleStream.empty().average());
        System.out.println("Underflow to zero? "
                + (Double.MIN_VALUE / 2.0 == 0.0));

        double twoTo53 = 9_007_199_254_740_992d;
        System.out.println("2^53 + 1 indistinguishable? "
                + (twoTo53 + 1.0 == twoTo53));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PrimitiveStreamEdgeDemo.java
java PrimitiveStreamEdgeDemo
~~~

Stdout:

~~~text
IntStream sum: -2147483648
As LongStream sum: 2147483648
Math.addExact: overflow detected
LongStream sum: -9223372036854775808
0.1 + 0.2 = 0.30000000000000004
NaN sum? true
Opposite infinities NaN? true
Double overflow infinite? true
Finite count: 2
Max propagates NaN? true
Min signed zero: -0.0
Empty average: OptionalDouble.empty
Underflow to zero? true
2^53 + 1 indistinguishable? true
~~~

Đọc kết quả:

1. `IntStream.sum()` của `Integer.MAX_VALUE + 1` quay vòng thành `Integer.MIN_VALUE`; khi chuyển sang `asLongStream()` **trước khi cộng**, tổng chính xác là `2147483648`.
2. `reduce(0, Math::addExact)` nhận ra tràn `int` và báo bằng exception; `LongStream.sum()` cũng có thể quay vòng nếu vượt `long`.
3. `0.1 + 0.2` biểu lộ sai số nhị phân; tổng chứa NaN trả NaN, và hai vô cực khác dấu cho NaN.
4. Tổng hai `Double.MAX_VALUE` không còn hữu hạn. `filter(Double::isFinite)` chỉ giữ `1.5` và `2.5` trong bốn phần tử được thử.
5. `DoubleStream.max()` trả NaN khi có NaN; `min(-0.0, +0.0)` trả `-0.0`.
6. `average()` của Stream rỗng là `OptionalDouble.empty`; underflow có thể trả `0.0`; ở `2^53`, cộng thêm `1.0` không làm giá trị `double` thay đổi.

**Không viết test dựa vào việc `DoubleStream.sum()` gọi callback hay gộp theo cùng thứ tự mỗi lần chạy.** Chương trình trên chỉ khẳng định các tính chất mà Java có hợp đồng rõ ràng và các biểu thức cụ thể được in ra.

## 7. Quy trình kiểm tra số liệu trong pipeline thật

Một quy trình an toàn thường là:

1. **Xác định miền giá trị đầu vào**: cho phép thiếu dữ liệu, NaN, Infinity, âm, bằng 0, giá trị cực lớn hay không?
2. **Chọn kiểu tích lũy**: `int` đủ không, cần `long`, `BigInteger`, `BigDecimal` hay `double` với dung sai chấp nhận được?
3. **Xác minh trước khi tổng hợp**: nếu nghiệp vụ không cho phép giá trị phi hữu hạn, từ chối ngay khi phát hiện. Không mặc định `filter(Double::isFinite)` luôn là sửa lỗi đúng.
4. **Tổng hợp và kiểm kết quả**: một tập toàn số hữu hạn vẫn có thể tạo tổng vô cực; nếu kết quả bắt buộc hữu hạn, kiểm `Double.isFinite(result)` sau khi tính.
5. **Định nghĩa chính sách cho Stream rỗng**: `sum()` trả zero thích hợp với số học, nhưng `average()`, `min()`, `max()` dùng các loại `Optional...` để biểu thị không có phần tử.
6. **Viết test cho các biên**: mức lớn nhất/nhỏ nhất, tổng vừa chạm/vượt biên, NaN, vô cực cùng và khác dấu, zero có dấu, đầu vào rỗng, số gần 0 và số rất lớn.
7. **Kiểm tra kết quả khi parallel**: không giả định thứ tự cộng hay số bit cuối cố định nếu hợp đồng floating-point không bảo đảm; tách test về *miền hợp lệ* và *dung sai số học*.

Ví dụ **từ chối nguồn không hợp lệ** (đoạn trong một phương thức):

~~~java
double[] measurements = {1.2, 3.4, 5.6};

boolean validInput = java.util.Arrays.stream(measurements)
        .allMatch(Double::isFinite);

if (!validInput) {
    throw new IllegalArgumentException(
            "Measurements must be finite");
}

double total = java.util.Arrays.stream(measurements).sum();
if (!Double.isFinite(total)) {
    throw new ArithmeticException(
            "Sum is not finite");
}
~~~

Đoạn trên tạo **Stream mới** ở mỗi lần duyệt mảng: một Stream đã tiêu thụ bằng terminal operation không thể dùng lại. Với dữ liệu vô hạn kích thước hay nguồn đọc một lần, cần thiết kế cơ chế validate/tính toán phù hợp để tránh đọc lại nguồn.

## 8. Những sai lầm thường gặp

**Sai lầm 1 — Cho rằng sum của primitive stream không thể tràn.** `IntStream.sum()` và `LongStream.sum()` vẫn dùng số học primitive. Chọn kiểu đủ lớn hoặc dùng `Math.addExact` / `BigInteger` theo yêu cầu.

**Sai lầm 2 — Cast sau phép cộng hoặc phép nhân.** `(long) IntStream.sum()` không cứu được tổng `int` đã tràn. Tương tự, `(long) (a * b)` vẫn có thể tràn trong phép nhân `int`; cần cast trước phép toán.

**Sai lầm 3 — Viết `x == Double.NaN` hoặc `x != Double.NaN` để lọc.** Cả hai là cách kiểm tra sai; dùng `Double.isNaN` hoặc `Double.isFinite` tùy ý nghĩa.

**Sai lầm 4 — Tin rằng nguồn không có NaN thì tổng luôn hữu hạn.** Các phép cộng hữu hạn vẫn có thể overflow thành Infinity hoặc gây NaN ở tổng trung gian; kiểm cả đầu vào lẫn kết quả.

**Sai lầm 5 — Coi Infinity là số rất lớn có thể tiếp tục gộp như bình thường.** Vô cực khác dấu tạo NaN; trung bình/min/max có thể bị ảnh hưởng. Phải định nghĩa cách xử lý trước khi dùng kết quả.

**Sai lầm 6 — Bằng nhau tuyệt đối giữa các phép tính double.** `0.1 + 0.2 == 0.3` là false. Dùng dung sai có căn cứ cho bài toán đo lường, hoặc `BigDecimal` khi cần số thập phân chính xác.

**Sai lầm 7 — Cho rằng `DoubleStream.sum()` luôn gộp từ trái sang phải.** Hợp đồng API không bảo đảm thứ tự cộng và cho phép thuật toán bù sai số. Parallel có thể cho kết quả hơi khác dù cùng dữ liệu.

**Sai lầm 8 — Hiểu sai `Double.MIN_VALUE`.** Đây là số dương nhỏ nhất khác 0 có thể biểu diễn, **không** phải số âm có độ lớn lớn nhất.

**Sai lầm 9 — Chỉ kiểm sum mà không kiểm Optional và dữ liệu rỗng.** `DoubleStream.empty().sum()` trả `0.0`; `DoubleStream.empty().average()` trả `OptionalDouble.empty()`. Đừng gọi `getAsDouble()` khi Optional rỗng.

**Sai lầm 10 — Lọc sạch NaN/Infinity mà không có chính sách.** Bỏ phần tử làm thay đổi số mẫu và thống kê; trong một số hệ thống phải ném lỗi, lưu dấu sự kiện hoặc đo lường tỷ lệ lỗi thay vì âm thầm bỏ qua.

## 9. Bài tập tự luyện

1. Dự đoán `IntStream.of(Integer.MAX_VALUE, 10).sum()` có ném exception không. Nêu cách viết trả tổng kiểu `long` chính xác.
2. Vì sao `DoubleStream.of(Double.MAX_VALUE, Double.MAX_VALUE).sum()` có thể không hữu hạn dù mọi phần tử đều hữu hạn?
3. Tại sao `Double.NaN == Double.NaN` là false nhưng `Double.isNaN(Double.NaN)` là true?
4. Nếu đầu vào gồm `1.0, Double.NaN, 2.0`, khi nào nên lọc NaN, khi nào phải từ chối toàn bộ dữ liệu?
5. Vì sao tiền tệ thường không nên tích lũy bằng `DoubleStream.sum()` nếu hệ thống yêu cầu chính xác đến đơn vị nhỏ nhất?
6. Với các giá trị `-0.0` và `+0.0`, tại sao phép `==` không chứng minh được `DoubleStream.min()` đã giữ đúng dấu?

**Gợi ý đáp án:** (1) Không ném, mà quay vòng trong `int`; chuyển qua `asLongStream().sum()` trước khi cộng. (2) Tổng toán học vượt giới hạn `double` và làm tròn thành vô cực. (3) Đây là quy tắc NaN của so sánh IEEE 754; dùng API `isNaN` để phân loại. (4) Cần theo quy tắc dữ liệu nghiệp vụ, không tự ý bỏ bản ghi. (5) Sai số nhị phân có thể ảnh hưởng đối soát; dùng `BigDecimal` hoặc `long` biểu diễn đơn vị tiền nhỏ nhất nếu không tràn. (6) `-0.0 == +0.0` là true; kiểm bằng bit hoặc quan sát đúng hợp đồng `min()`.

## Ghi nhớ

- `IntStream`, `LongStream` và `DoubleStream` đang được hỗ trợ. Chúng **không thay đổi quy tắc số học primitive**.
- `NaN` không được kiểm bằng `==`; dùng `Double.isNaN`. Muốn giữ lại chỉ các số hữu hạn, `Double.isFinite` là công cụ hiện hành, nhưng phải có chính sách dữ liệu rõ ràng.
- `IntStream.sum()`/`LongStream.sum()` có thể **tràn và quay vòng**. Chuyển kiểu trước phép toán hoặc dùng `Math.addExact`/kiểu số lớn khi cần chính xác.
- `DoubleStream.sum()` có thể thành Infinity/NaN và chịu **sai số làm tròn**, kể cả khi nguồn toàn số hữu hạn. Không giả định thứ tự cộng cố định.
- Khi yêu cầu thập phân chính xác hoặc kiểm toán kết quả, chọn `BigDecimal` hoặc biểu diễn số nguyên trong miền đủ lớn; không dùng `double` chỉ vì nó có miền giá trị rộng.

### Nguồn tham khảo API và quy tắc Java hiện hành

- [Oracle Java SE 26 — DoubleStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/DoubleStream.html)
- [Oracle Java SE 26 — IntStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html)
- [Oracle Java SE 26 — LongStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/LongStream.html)
- [Oracle Java SE 26 — Double.isFinite, isNaN, isInfinite](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Double.html)
- [Oracle Java SE 26 — Math.addExact](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html)
- [Oracle Java SE 26 — BigDecimal](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigDecimal.html)
- [Java Language Specification 26 — Numerical arithmetic](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html)
