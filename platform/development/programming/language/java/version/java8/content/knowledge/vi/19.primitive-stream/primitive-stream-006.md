# IntSummaryStatistics, LongSummaryStatistics, DoubleSummaryStatistics trong Java Primitive Stream

Ba lớp `IntSummaryStatistics`, `LongSummaryStatistics` và `DoubleSummaryStatistics` của gói `java.util` là những đối tượng tổng hợp thống kê cơ bản cho các luồng số nguyên thủy `IntStream`, `LongStream` và `DoubleStream`. Chúng cho phép lấy **số lượng, tổng, nhỏ nhất, lớn nhất và trung bình** trong **một phép reduction**, thay vì tạo nhiều stream độc lập để tính từng chỉ số.

Các API này xuất hiện từ Java 8 và **vẫn được sử dụng trong Java hiện đại**; những ví dụ dưới đây dùng API tương thích Java 8 và có thể biên dịch/chạy với JDK 17+. Trọng tâm là hiểu đúng hợp đồng, kiểu dữ liệu, hành vi với stream rỗng và giới hạn độ chính xác.

## 1. Khi nào nên dùng `summaryStatistics()`?

Nếu chỉ cần tổng, có thể dùng `IntStream.sum()`; nếu chỉ cần nhỏ nhất/lớn nhất, có thể dùng `min()`/`max()`. Nhưng khi cần nhiều chỉ số từ **cùng tập dữ liệu**, `summaryStatistics()` gom tất cả trong một lần tiêu thụ stream:

~~~java
IntSummaryStatistics stats = IntStream.of(2, 4, 6).summaryStatistics();

long count = stats.getCount();     // 3
long sum = stats.getSum();         // 12
int min = stats.getMin();          // 2
int max = stats.getMax();          // 6
double average = stats.getAverage(); // 4.0
~~~

Đây là đoạn minh họa, cần import `java.util.IntSummaryStatistics` và `java.util.stream.IntStream` nếu đưa vào một chương trình. Đặt tên biến `stats` vì kết quả là **một đối tượng chứa năm chỉ số**, không phải chính một con số.

Điểm hữu ích: mỗi stream thường chỉ tiêu thụ **một lần**. Không thể gọi `count()` rồi `min()` tiếp trên cùng một stream đã kết thúc. Có thể tạo stream mới từ nguồn nếu cần, nhưng khi muốn đủ các chỉ số, `summaryStatistics()` làm ý định rõ hơn.

## 2. So sánh chính xác ba lớp

| Chức năng | `IntSummaryStatistics` | `LongSummaryStatistics` | `DoubleSummaryStatistics` |
| --- | --- | --- | --- |
| Nguồn thường dùng | `IntStream` | `LongStream` | `DoubleStream` |
| Trả từ terminal | `IntStream.summaryStatistics()` | `LongStream.summaryStatistics()` | `DoubleStream.summaryStatistics()` |
| `getCount()` | `long` | `long` | `long` |
| `getSum()` | **`long`** | `long` | `double` |
| `getMin()` / `getMax()` | `int` | `long` | `double` |
| `getAverage()` | `double` | `double` | `double` |
| `accept(value)` | `int` | `long` | `double` |
| `combine(other)` | Nhập thống kê của cùng lớp | Nhập thống kê của cùng lớp | Nhập thống kê của cùng lớp |

**Điểm dễ nhầm nhất:** `IntSummaryStatistics.getSum()` trả **`long`**, không phải `int`. Chẳng hạn tổng hai số nguyên dương gần giới hạn `int` có thể vượt `Integer.MAX_VALUE`, nhưng vẫn nằm trong `long`. Tuy vậy, `LongSummaryStatistics.getSum()` vẫn là `long` nên **có thể tràn long**. `DoubleSummaryStatistics` dùng số thực, chịu quy tắc làm tròn IEEE 754.

Tất cả `getCount()` đều trả `long`. Cả ba `getAverage()` đều trả `double`, ngay cả khi dữ liệu ban đầu là số nguyên; tránh tự viết `sum / count` với phép chia nguyên vì có thể mất phần thập phân và còn phải xử lý mẫu số bằng 0.

## 3. Cơ chế sử dụng với Primitive Stream

### 3.1. `IntSummaryStatistics`

~~~java
IntSummaryStatistics scores =
    IntStream.of(10, 20, 30, 40).summaryStatistics();
// count = 4, sum = 100L, min = 10, max = 40, average = 25.0
~~~

Chọn khi mỗi phần tử phù hợp `int`: số lượng nhỏ, điểm số, số sự kiện trong phạm vi `int`. `getSum()` được nâng lên kiểu `long`; nhưng số đếm và tổng vẫn có giới hạn dung lượng theo hợp đồng kiểu số.

### 3.2. `LongSummaryStatistics`

~~~java
LongSummaryStatistics sizes =
    LongStream.of(1_000_000_000L, 2_000_000_000L, 3_000_000_000L)
              .summaryStatistics();
// count = 3, sum = 6_000_000_000L
// min = 1_000_000_000L, max = 3_000_000_000L
// average = 2_000_000_000.0
~~~

Chọn khi một **phần tử** có thể vượt phạm vi `int` (kích thước byte, ID số lớn khi có ý nghĩa tính toán, thời lượng hoặc bộ đếm dài). `LongSummaryStatistics` không chuyển tổng sang `BigInteger`: nếu cộng vượt `Long.MAX_VALUE` hoặc dưới `Long.MIN_VALUE`, phép cộng có thể tràn.

### 3.3. `DoubleSummaryStatistics`

~~~java
DoubleSummaryStatistics rates =
    DoubleStream.of(2.5, 3.5, 6.0).summaryStatistics();
// count = 3, sum = 12.0, min = 2.5, max = 6.0, average = 4.0
~~~

Chọn khi dữ liệu thực sự là `double`: tỷ lệ, đo lường, giá trị có phần thập phân. Chú ý `double` biểu diễn số thực hữu hạn bằng nhị phân với **độ chính xác giới hạn**; một số thập phân không thể biểu diễn chính xác. `getSum()` và `getAverage()` có thể thay đổi những bit cuối do cách cộng/phân nhóm, nhất là khi chạy song song hoặc tổng có các độ lớn rất khác nhau.

Trong các bản JDK hiện hành, cách tính tổng có thể dùng **compensated summation** để giảm sai số so với phép cộng đơn giản, nhưng không có cam kết sẽ tạo tổng toán học chính xác hay kết quả bitwise giống nhau trong mọi pipeline. Với tiền tệ hoặc yêu cầu chính xác thập phân, cân nhắc `BigDecimal` cùng quy tắc làm tròn phù hợp thay vì `DoubleSummaryStatistics`.

## 4. Stream rỗng: các giá trị mặc định không phải dữ liệu thật

Khi stream không có phần tử, cả ba đối tượng thống kê vẫn được trả về, **không phải `Optional.empty()`**. Các giá trị như sau:

| Getter với nguồn rỗng | `IntSummaryStatistics` | `LongSummaryStatistics` | `DoubleSummaryStatistics` |
| --- | --- | --- | --- |
| `getCount()` | `0L` | `0L` | `0L` |
| `getSum()` | `0L` | `0L` | `0.0` |
| `getMin()` | `Integer.MAX_VALUE` | `Long.MAX_VALUE` | `Double.POSITIVE_INFINITY` |
| `getMax()` | `Integer.MIN_VALUE` | `Long.MIN_VALUE` | `Double.NEGATIVE_INFINITY` |
| `getAverage()` | `0.0` | `0.0` | `0.0` |

Các giá trị min/max trong bảng là **sentinel khi chưa ghi nhận phần tử nào**, không phải “kết quả nhỏ nhất/lớn nhất của dữ liệu thực”. Đừng hiển thị chúng thành “min thực tế” khi `count == 0`.

Ví dụ:

~~~java
IntSummaryStatistics empty = IntStream.empty().summaryStatistics();
if (empty.getCount() == 0) {
    System.out.println("Không có dữ liệu thống kê");
} else {
    System.out.println("Min = " + empty.getMin());
}
~~~

Tương tự, `getAverage() == 0.0` **không chứng minh** tập dữ liệu rỗng: nó có thể là trung bình thật của `[-2, 2]`. Muốn phân biệt “không có dữ liệu”, luôn kiểm tra `getCount()`, hoặc dùng `IntStream.min()`/`LongStream.max()` trả `OptionalInt`/`OptionalLong` nếu chỉ cần một phép đo.

## 5. Áp dụng cho Stream đối tượng bằng `Collectors.summarizing*`

Trong hệ thống thực tế, nguồn thường là `Stream<Product>` hay `Stream<Order>` thay vì Primitive Stream đã có sẵn. Khi đó có hai cách chính:

**Cách A — Chuyển sang primitive rồi lấy thống kê:**

~~~java
IntSummaryStatistics qtyStats = products.stream()
    .mapToInt(Product::getQuantity)
    .summaryStatistics();
~~~

**Cách B — Thu thập trực tiếp bằng collector:**

~~~java
IntSummaryStatistics qtyStats = products.stream()
    .collect(Collectors.summarizingInt(Product::getQuantity));
~~~

Hai đoạn đều là **minh họa, không phải chương trình độc lập**; giả sử `Product`, `products` và `getQuantity()` đã tồn tại. Nhớ import `java.util.IntSummaryStatistics` và `java.util.stream.Collectors`.

Các collector có sẵn, tương ứng với ba kiểu:

~~~java
Collectors.summarizingInt(Product::getQuantity)    // IntSummaryStatistics
Collectors.summarizingLong(Product::getFileSize)   // LongSummaryStatistics
Collectors.summarizingDouble(Product::getRating)   // DoubleSummaryStatistics
~~~

Có thể dùng trong `groupingBy` để tạo **thống kê mỗi nhóm**, ví dụ:

~~~java
Map<String, DoubleSummaryStatistics> byCategory =
    products.stream().collect(
        Collectors.groupingBy(
            Product::getCategory,
            Collectors.summarizingDouble(Product::getRating)
        ));
~~~

Đoạn trên là minh họa. Thay vì chỉ lưu danh sách đối tượng cho từng category, nó gom ngay count/sum/min/max/average theo rating. `Collectors.summarizingInt`, `summarizingLong` và `summarizingDouble` đều là API Java 8 hiện hành.

**Chọn cách nào?** `mapToInt(...).summaryStatistics()` dễ hiểu khi chỉ muốn một bộ thống kê toàn cục. `Collectors.summarizingInt(...)` thuận tiện trong `groupingBy`, `partitioningBy` hoặc khi đang xây dựng pipeline collector cho Stream đối tượng. Không nhất thiết phải tạo ba primitive stream chỉ vì có ba kiểu; chọn kiểu dựa vào thuộc tính cần thống kê.

## 6. Ví dụ Java đầy đủ, có đầu ra kiểm chứng được

Lưu mã dưới đây vào **`PrimitiveStatisticsDemo.java`**. Lớp `Measurement` chứa ba thuộc tính kiểu `int`, `long` và `double`, cùng một khóa nhóm; ta dùng cả hai đường API primitive stream và collector.

~~~java
import java.util.Arrays;
import java.util.DoubleSummaryStatistics;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Locale;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class PrimitiveStatisticsDemo {

    static final class Measurement {
        private final String area;
        private final int units;
        private final long bytes;
        private final double score;

        Measurement(String area, int units, long bytes, double score) {
            this.area = area;
            this.units = units;
            this.bytes = bytes;
            this.score = score;
        }

        String getArea() {
            return area;
        }

        int getUnits() {
            return units;
        }

        long getBytes() {
            return bytes;
        }

        double getScore() {
            return score;
        }
    }

    public static void main(String[] args) {
        List<Measurement> data = Arrays.asList(
                new Measurement("east", 2, 1_000_000_000L, 2.5),
                new Measurement("west", 4, 2_000_000_000L, 3.5),
                new Measurement("east", 6, 3_000_000_000L, 6.0)
        );

        IntSummaryStatistics units = data.stream()
                .mapToInt(Measurement::getUnits)
                .summaryStatistics();

        LongSummaryStatistics sizes = data.parallelStream()
                .mapToLong(Measurement::getBytes)
                .summaryStatistics();

        DoubleSummaryStatistics scores = data.stream()
                .mapToDouble(Measurement::getScore)
                .summaryStatistics();

        IntSummaryStatistics usingCollector = data.stream()
                .collect(Collectors.summarizingInt(
                        Measurement::getUnits
                ));

        Map<String, DoubleSummaryStatistics> byArea = data.stream()
                .collect(Collectors.groupingBy(
                        Measurement::getArea,
                        Collectors.summarizingDouble(
                                Measurement::getScore
                        )
                ));

        IntSummaryStatistics emptyInt =
                IntStream.empty().summaryStatistics();
        LongSummaryStatistics emptyLong =
                LongStream.empty().summaryStatistics();
        DoubleSummaryStatistics emptyDouble =
                DoubleStream.empty().summaryStatistics();

        IntSummaryStatistics left = new IntSummaryStatistics();
        left.accept(2);
        left.accept(4);
        IntSummaryStatistics right = new IntSummaryStatistics();
        right.accept(6);
        left.combine(right);

        DoubleSummaryStatistics withNaN =
                DoubleStream.of(1.0, Double.NaN, 2.0)
                            .summaryStatistics();
        DoubleSummaryStatistics signedZeros =
                DoubleStream.of(-0.0, 0.0)
                            .summaryStatistics();

        System.out.println("int: count=" + units.getCount()
                + " sum=" + units.getSum()
                + " min=" + units.getMin()
                + " max=" + units.getMax()
                + " avg=" + units.getAverage());

        System.out.printf(Locale.ROOT,
                "long: count=%d sum=%d min=%d max=%d avg=%.1f%n",
                sizes.getCount(), sizes.getSum(),
                sizes.getMin(), sizes.getMax(), sizes.getAverage());

        System.out.println("double: count=" + scores.getCount()
                + " sum=" + scores.getSum()
                + " min=" + scores.getMin()
                + " max=" + scores.getMax()
                + " avg=" + scores.getAverage());

        System.out.println("collector sum="
                + usingCollector.getSum());
        System.out.println("east: count="
                + byArea.get("east").getCount()
                + " avg=" + byArea.get("east").getAverage());

        System.out.println("emptyInt: count="
                + emptyInt.getCount()
                + " min=" + emptyInt.getMin()
                + " max=" + emptyInt.getMax()
                + " avg=" + emptyInt.getAverage());

        System.out.println("emptyLong: count="
                + emptyLong.getCount()
                + " minIsLongMax="
                + (emptyLong.getMin() == Long.MAX_VALUE));

        System.out.println("emptyDouble: min="
                + emptyDouble.getMin()
                + " max=" + emptyDouble.getMax()
                + " avg=" + emptyDouble.getAverage());

        System.out.println("combined: count="
                + left.getCount()
                + " sum=" + left.getSum());

        System.out.println("NaN: minIsNaN="
                + Double.isNaN(withNaN.getMin())
                + " sumIsNaN="
                + Double.isNaN(withNaN.getSum()));

        System.out.println("signedZeros: min="
                + signedZeros.getMin()
                + " max=" + signedZeros.getMax());
    }
}
~~~

Biên dịch và chạy từ thư mục chứa mã (JDK 17+):

~~~bash
javac -encoding UTF-8 PrimitiveStatisticsDemo.java
java PrimitiveStatisticsDemo
~~~

Đầu ra:

~~~text
int: count=3 sum=12 min=2 max=6 avg=4.0
long: count=3 sum=6000000000 min=1000000000 max=3000000000 avg=2000000000.0
double: count=3 sum=12.0 min=2.5 max=6.0 avg=4.0
collector sum=12
east: count=2 avg=4.25
emptyInt: count=0 min=2147483647 max=-2147483648 avg=0.0
emptyLong: count=0 minIsLongMax=true
emptyDouble: min=Infinity max=-Infinity avg=0.0
combined: count=3 sum=12
NaN: minIsNaN=true sumIsNaN=true
signedZeros: min=-0.0 max=0.0
~~~

Giải thích các kết quả:

1. `IntSummaryStatistics` có `sum = 12L` và `average = 4.0`; `getSum()` là `long` dù `units` là `int`.
2. `LongSummaryStatistics` tính đúng `6_000_000_000L`, vượt trần `int` nhưng còn trong `long`. Dùng `printf(Locale.ROOT, "%.1f")` để in trung bình theo định dạng ổn định.
3. `DoubleSummaryStatistics` trên `2.5, 3.5, 6.0` cho tổng 12.0 và trung bình 4.0; những giá trị này biểu diễn được chính xác trong nhị phân.
4. Collector từ `Stream<Measurement>` cho cùng tổng; `groupingBy` tạo thống kê riêng cho `east` gồm `2.5` và `6.0`, trung bình `4.25`.
5. Stream rỗng tạo sentinel min/max; `count=0` là dấu hiệu đáng tin để không hiển thị min/max đó như số đo.
6. `accept` rồi `combine` có cùng thống kê với việc xử lý tất cả số trong một stream.
7. Có `NaN` thì `getMin()` và `getSum()` có thể mang `NaN` theo hợp đồng; với cặp `-0.0` và `+0.0`, giá trị min là `-0.0` và max là `+0.0`.

Mẫu này cho thấy cả ba kiểu kết quả và cả hai cách tạo thống kê: terminal trên Primitive Stream, hoặc collector trên Stream đối tượng.

## 7. Vòng đời đối tượng thống kê: `accept`, `combine` và tính mutable

Ba lớp đều có constructor rỗng, `accept(value)` và `combine(other)`. Bản chất chúng là **mutable reduction result**:

~~~java
IntSummaryStatistics a = new IntSummaryStatistics();
a.accept(10);
a.accept(20); // count=2, sum=30, min=10, max=20
IntSummaryStatistics b = new IntSummaryStatistics();
b.accept(30);
a.combine(b); // a: count=3, sum=60, min=10, max=30
~~~

Đoạn trên chỉ minh họa logic `accept`/`combine`; khi dùng ngoài chương trình ví dụ, import `java.util.IntSummaryStatistics`. Phép `combine` **thay đổi đối tượng đích** (`a`) và bổ sung thống kê từ `b`; đừng giả định nó tạo đối tượng bất biến mới hoặc tự làm sạch `b`.

Không có phương thức `reset()` chuẩn. Muốn mở phiên thống kê mới, tạo một instance mới hoặc tạo stream mới rồi gọi `summaryStatistics()`. Đối tượng stats đã trả về không tự cập nhật khi collection nguồn thay đổi, trừ khi chính bạn gọi `accept` hay `combine` vào nó.

### Thread-safety khi chạy parallel

Các đối tượng `IntSummaryStatistics`, `LongSummaryStatistics`, `DoubleSummaryStatistics` **không phải cấu trúc thread-safe để nhiều thread cùng gọi `accept` trên một instance**. Tuy nhiên, sử dụng `summaryStatistics()` hoặc `Collectors.summarizingInt(...)` với `parallelStream()` là hợp lệ: framework điều phối việc phân vùng, tách accumulator và hợp nhất các kết quả theo hợp đồng reduction.

~~~java
IntSummaryStatistics parallel = data.parallelStream()
    .mapToInt(Measurement::getUnits)
    .summaryStatistics();
~~~

Mã trên là minh họa, giả sử `data` và lớp `Measurement` của ví dụ đầy đủ. Chạy parallel **không bảo đảm nhanh hơn** với dữ liệu nhỏ; chi phí chia việc và kết hợp có thể lớn hơn lợi ích. Đừng đưa cùng một stats mutable toàn cục vào `forEach` song song và gọi `accept` mà không có thiết kế đồng bộ an toàn.

Nếu muốn so sánh tuần tự và song song, kiểm tra các chỉ số theo ngữ nghĩa; với `double`, sum/average có thể có sai khác làm tròn nên phép so sánh gần đúng có thể thích hợp hơn so sánh `==`.

## 8. Những điểm cần cẩn thận với `double`

### 8.1. `NaN`, infinities, và dấu của zero

Với `DoubleSummaryStatistics`:

- Nếu ghi nhận bất kỳ `Double.NaN` nào, `getMin()` và `getMax()` trả `NaN`; tổng và trung bình cũng mang tính phi hữu hạn theo điều kiện của phép cộng.
- Nếu nguồn có `Double.POSITIVE_INFINITY` hoặc `Double.NEGATIVE_INFINITY`, tổng có thể là vô cực hoặc `NaN` (đặc biệt khi có cả vô cực dương và âm).
- Với so sánh min/max, `-0.0` được coi là **nhỏ hơn** `+0.0` dù phép so sánh số học `-0.0 == 0.0` là `true`.
- Khi nguồn rỗng, min là `+Infinity`, max là `-Infinity`. Những giá trị này chính là sentinel mặc định, không chứng minh dữ liệu có vô cực thật.
- `getSum()` của các giá trị `double` có thể phụ thuộc thứ tự cộng; nếu tất cả phần tử là zero, dấu của tổng zero cũng không được bảo đảm duy trì.

Nếu không muốn chấp nhận `NaN`/Infinity trong thống kê, hãy xác định và áp dụng một quy tắc lọc rõ ràng. Ví dụ `Double.isFinite(value)` (Java 8+) nhận biết giá trị hữu hạn; **lọc** hay **từ chối** giá trị phi hữu hạn là quyết định nghiệp vụ, không có lựa chọn mặc định đúng cho mọi bài toán.

### 8.2. Trung bình và độ chính xác số học

`getAverage()` trả `double`, không phải một phân số chính xác vô hạn. Với `LongSummaryStatistics` trên các số lớn vượt mức biểu diễn nguyên liên tiếp của `double`, trung bình có thể mất một phần độ chính xác do chuyển đổi kiểu. Với `DoubleSummaryStatistics`, thuật toán có thể đổi cách cộng để cải thiện sai số, nhưng không cho phép coi kết quả là số thập phân chính xác tuyệt đối.

Nếu dùng số liệu tài chính, báo cáo cần đối soát hoặc phép tính có yêu cầu rounding cụ thể, cân nhắc một phép tổng hợp thích hợp hơn, chẳng hạn dùng `BigDecimal` với nguồn đầu vào và `MathContext`/`RoundingMode` được định nghĩa rõ.

### 8.3. Kết quả trung bình bằng 0 khi không có dữ liệu

Với `DoubleStream.empty().summaryStatistics().getAverage()`, kết quả là `0.0`; điều này có thể nhầm với bộ dữ liệu có trung bình thực bằng 0. Hãy luôn đưa `count` kèm average khi dựng báo cáo để phân biệt trường hợp không có mẫu.

## 9. Lựa chọn API và lưu ý hiệu năng

| Mục tiêu | Cách viết nên cân nhắc |
| --- | --- |
| Chỉ cần tổng `int` hoặc `long` | `mapToInt(...).sum()`, `mapToLong(...).sum()` |
| Chỉ cần trung bình | `average()` trả `OptionalDouble` |
| Chỉ cần min/max và muốn biểu diễn rỗng rõ ràng | `min()`/`max()` trả `OptionalInt`, `OptionalLong` hoặc `OptionalDouble` |
| Cần count + sum + min + max + average | `summaryStatistics()` |
| Có `Stream<T>`, cần thống kê thuộc tính | `Collectors.summarizingInt/Long/Double(mapper)` |
| Cần thống kê theo từng nhóm | `groupingBy(keyMapper, summarizingX(valueMapper))` |
| Cần độ chính xác thập phân tuyệt đối | Tự thiết kế tổng hợp theo `BigDecimal`/quy tắc rounding phù hợp |

Độ phức tạp thông thường của summary statistics là **`O(n)` thời gian** cho `n` phần tử. Kết quả chỉ có vài trường dữ liệu nên dung lượng lưu **O(1) cho mỗi accumulator**, ngoài nguồn và các accumulator tạm khi xử lý parallel. `summaryStatistics()` không lưu toàn bộ các phần tử như `collect(toList())`.

Nếu làm ba phép `min()`, `max()`, `sum()` riêng biệt từ ba stream mới trên cùng nguồn, chương trình phải duyệt nguồn nhiều lần; nếu nguồn có I/O hoặc tính toán mapper đắt, chi phí ấy đáng kể. Tuy vậy, với một chỉ số đơn lẻ, API chuyên dụng vẫn rõ nghĩa và có thể tối ưu dễ dàng.

**Tối ưu theo dữ liệu thực tế:** primitive streams giúp tránh nhiều boxing/unboxing khi thao tác trên số nguyên thủy; tạo `Stream<Integer>` chỉ để xử lý số lượng lớn có thể tốn đối tượng và GC hơn `IntStream`. Nếu chỉ có nguồn đối tượng, `mapToInt`/`mapToLong`/`mapToDouble` là cầu nối tự nhiên.

## 10. Các lỗi thường gặp

1. **Khai báo tổng của `IntSummaryStatistics` là `int`.** `getSum()` thực sự trả `long`; lưu vào `int` cần cast hoặc kiểm tra phạm vi, có nguy cơ mất dữ liệu.
2. **Giả định `LongSummaryStatistics` không bao giờ tràn.** Nó vẫn tích lũy vào `long`. Nếu miền dữ liệu vượt long, hãy dùng cách tổng hợp khác.
3. **Đọc min/max của stream rỗng như số đo thật.** Phải kiểm tra `getCount() > 0` trước khi diễn giải sentinel.
4. **Cho rằng average bằng 0 nghĩa là tập rỗng.** Tập có dữ liệu vẫn có thể trung bình 0; count mới giúp phân biệt.
5. **Dùng `DoubleSummaryStatistics` cho tiền mà không xét sai số.** `double` không bảo đảm số thập phân chính xác; cần thiết kế theo yêu cầu tài chính.
6. **Bỏ qua `NaN`/Infinity.** Các giá trị phi hữu hạn ảnh hưởng min/max/sum/average theo hợp đồng, đôi khi che dấu dữ liệu lỗi.
7. **Tự chia `getSum()/getCount()` bằng toán học số nguyên.** Có thể bị chia nguyên, chia cho 0, hoặc sai kiểu; `getAverage()` xử lý mẫu số rỗng và trả `double`.
8. **Dùng cùng stats instance trong `parallelStream().forEach(stats::accept)`.** Stats mutable không thread-safe; dùng terminal `summaryStatistics()` hoặc `summarizingX` của Stream.
9. **Dựa vào `toString()` như định dạng output ổn định.** Các lớp có `toString()` tiện debug nhưng định dạng chính xác không phải hợp đồng trình bày; tạo output từ các getter nếu cần máy đọc.
10. **Dùng lại stream đã tiêu thụ.** Sau một terminal operation như `summaryStatistics()`, muốn chạy pipeline khác thì tạo stream mới từ nguồn.
11. **Không xử lý null trong object mapper.** `mapToInt(Item::getValue)` với phần tử null hoặc unboxing `Integer` null có thể ném `NullPointerException`; xác định rõ cách lọc/bù dữ liệu thiếu.
12. **Dùng kết quả stats như đối tượng bất biến.** Chúng có `accept` và `combine` nên giá trị getter có thể thay đổi nếu tiếp tục sửa chính đối tượng đó.

## 11. Checklist triển khai

1. Chọn **kiểu số gốc**: `int`, `long` hay `double`? Xem phạm vi và yêu cầu chính xác của dữ liệu.
2. Xác định cần **một chỉ số** hay **cả năm chỉ số**. Chọn API cụ thể cho ý định rõ ràng.
3. Với stream đối tượng, xác định mapper trả primitive hợp lệ: `ToIntFunction`, `ToLongFunction`, `ToDoubleFunction`; xử lý null nếu có.
4. Với stream rỗng, dùng `getCount()` để quyết định hiển thị min/max/average, đừng gán ý nghĩa cho sentinel.
5. Với `double`, xét `NaN`, Infinity, `-0.0`, rounding và tính lặp lại của kết quả parallel.
6. Với kiểu nguyên, xét overflow; `getSum()` của `IntSummaryStatistics` là long, của `LongSummaryStatistics` cũng là long.
7. Nếu cần thống kê theo nhóm, dùng `groupingBy` + `summarizingX` để giảm số bước duyệt/tạo danh sách trung gian.
8. Khi cần chạy parallel, dùng các terminal/collector của Stream theo đúng hợp đồng; không cập nhật thủ công một stats mutable chung từ nhiều thread.
9. Tự kiểm tra stream rỗng, một phần tử, giá trị âm, min/max trùng nhau, giới hạn số học, nhiều nhóm, và dữ liệu đo có NaN.
10. Khi xuất báo cáo, hiển thị count cùng các chỉ số và tự chọn định dạng, không phụ thuộc `toString()`.

**Ghi nhớ:** `IntSummaryStatistics`, `LongSummaryStatistics` và `DoubleSummaryStatistics` là ba cách thống kê **một lần qua primitive stream**. Chúng giống nhau về bộ getter và khác nhau ở kiểu dữ liệu, sentinel khi rỗng và độ chính xác. Hãy kiểm tra `count` trước khi diễn giải min/max, chọn đúng kiểu cho tổng và sử dụng `Collectors.summarizingX` khi muốn áp dụng thống kê vào từng nhóm đối tượng.

## Tài liệu chính thức

- [Oracle Java SE 26 — IntSummaryStatistics](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/IntSummaryStatistics.html)
- [Oracle Java SE 26 — LongSummaryStatistics](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/LongSummaryStatistics.html)
- [Oracle Java SE 26 — DoubleSummaryStatistics](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/DoubleSummaryStatistics.html)
- [Oracle Java SE 26 — Primitive Stream: IntStream, LongStream, DoubleStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html)
- [Oracle Java SE 26 — Collectors.summarizingInt/Long/Double](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html)
