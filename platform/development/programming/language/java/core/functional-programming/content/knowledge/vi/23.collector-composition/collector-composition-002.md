# `summarizingInt()`, `summarizingLong()` và `summarizingDouble()` trong Java Stream

Khi xử lý dữ liệu bằng Java Stream, nhiều tình huống cần **đồng thời** biết số lượng phần tử, tổng, giá trị nhỏ nhất, giá trị lớn nhất và trung bình của một thuộc tính số. Thay vì chạy năm terminal operation riêng biệt, `Collectors.summarizingInt()`, `Collectors.summarizingLong()` và `Collectors.summarizingDouble()` thực hiện **một lần thu thập kết quả** thành đối tượng thống kê tương ứng.

Ba collector đều nhận **hàm trích xuất khóa số** (*numeric extractor*) từ từng phần tử `T`, nhưng khác nhau về kiểu số và kiểu kết quả:

| Collector | Hàm trích xuất | Kiểu đối tượng kết quả |
| --- | --- | --- |
| `Collectors.summarizingInt(extractor)` | `ToIntFunction<? super T>`, trả `int` | `IntSummaryStatistics` |
| `Collectors.summarizingLong(extractor)` | `ToLongFunction<? super T>`, trả `long` | `LongSummaryStatistics` |
| `Collectors.summarizingDouble(extractor)` | `ToDoubleFunction<? super T>`, trả `double` | `DoubleSummaryStatistics` |

Các lớp thống kê nằm trong `java.util`; các collector nằm trong `java.util.stream.Collectors`. Có thể dùng từ Java 8; ví dụ trong bài ưu tiên **Java 17+**.

**Điểm cần nhớ:** `summarizingInt/Long/Double` là **factory tạo Collector**; chính `stream.collect(...)` mới là **terminal operation** thực thi việc tổng hợp. Kết quả không phải `Map` hay một số trung bình đơn lẻ, mà là một đối tượng chứa nhiều số liệu.

## 1. Ý nghĩa và cách đọc kết quả

Mỗi đối tượng thống kê cung cấp các phương thức:

| Phương thức | Ý nghĩa | Kiểu trả về với Int | Kiểu trả về với Long | Kiểu trả về với Double |
| --- | --- | --- | --- | --- |
| `getCount()` | Số giá trị đã thu thập | `long` | `long` | `long` |
| `getSum()` | Tổng giá trị | `long` | `long` | `double` |
| `getMin()` | Giá trị nhỏ nhất | `int` | `long` | `double` |
| `getMax()` | Giá trị lớn nhất | `int` | `long` | `double` |
| `getAverage()` | Trung bình cộng | `double` | `double` | `double` |

Một số điểm quan trọng:

- Với `IntSummaryStatistics`, **`getSum()` trả `long`**, không phải `int`. Điều này giúp lưu tổng của nhiều số `int` vượt giới hạn `int`; nhưng nếu cộng quá giới hạn `long` thì vẫn có thể tràn.
- `LongSummaryStatistics.getSum()` trả `long`: không tự chuyển sang `BigInteger`, nên có thể tràn khi tổng vượt giới hạn.
- `DoubleSummaryStatistics` sử dụng số thực `double`, có sai số làm tròn; không phù hợp để đảm bảo tính toán tiền tệ chính xác tuyệt đối.
- `getAverage()` trả `double` ngay cả với hai collector nguyên. Không được giả định kết quả là phép chia nguyên hoặc là một `OptionalDouble`.
- `getCount()` đếm số **giá trị thực sự đi qua collector sau các bước lọc/chuyển đổi**, không phải kích thước gốc của collection trước pipeline.

Công thức trực quan với một tập không rỗng gồm `n` phần tử số:

~~~text
count   = n
sum     = tổng các giá trị
min     = giá trị nhỏ nhất
max     = giá trị lớn nhất
average = sum / n  (biểu diễn bằng double, có thể làm tròn)
~~~

Đó là mô hình ý nghĩa. Với `double`, JDK có thể dùng cộng bù sai số và tính toán trung bình theo cách cải thiện độ ổn định số học; không nên giả định phép cộng nhị phân là hoàn toàn chính xác.

## 2. Ví dụ chạy độc lập: cùng một nguồn, ba kiểu thống kê

Tạo file `SummaryCollectorsDemo.java`:

~~~java
import java.util.IntSummaryStatistics;
import java.util.LongSummaryStatistics;
import java.util.DoubleSummaryStatistics;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class SummaryCollectorsDemo {
    record Sale(String region, int units, long revenueCents,
                double weight) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("North", 3, 1200L, 1.5),
                new Sale("South", 5, 1800L, 2.25),
                new Sale("North", 2, 600L, 1.25)
        );

        IntSummaryStatistics units = sales.stream()
                .collect(Collectors.summarizingInt(Sale::units));

        LongSummaryStatistics revenue = sales.stream()
                .collect(Collectors.summarizingLong(Sale::revenueCents));

        DoubleSummaryStatistics weights = sales.stream()
                .collect(Collectors.summarizingDouble(Sale::weight));

        System.out.printf(Locale.ROOT,
                "units count=%d sum=%d min=%d max=%d avg=%.2f%n",
                units.getCount(), units.getSum(), units.getMin(),
                units.getMax(), units.getAverage());

        System.out.printf(Locale.ROOT,
                "cents count=%d sum=%d min=%d max=%d avg=%.2f%n",
                revenue.getCount(), revenue.getSum(), revenue.getMin(),
                revenue.getMax(), revenue.getAverage());

        System.out.printf(Locale.ROOT,
                "weight count=%d sum=%.1f min=%.2f max=%.2f avg=%.2f%n",
                weights.getCount(), weights.getSum(), weights.getMin(),
                weights.getMax(), weights.getAverage());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 SummaryCollectorsDemo.java
java SummaryCollectorsDemo
~~~

Stdout:

~~~text
units count=3 sum=10 min=2 max=5 avg=3.33
cents count=3 sum=3600 min=600 max=1800 avg=1200.00
weight count=3 sum=5.0 min=1.25 max=2.25 avg=1.67
~~~

Giải thích từng bước:

1. `sales.stream()` có kiểu `Stream<Sale>`.
2. `Sale::units` là extractor `Sale -> int`; `summarizingInt` tạo `IntSummaryStatistics`.
3. `Sale::revenueCents` trả `long`; `summarizingLong` tạo `LongSummaryStatistics`.
4. `Sale::weight` trả `double`; `summarizingDouble` tạo `DoubleSummaryStatistics`.
5. Kết quả count bằng 3 vì có ba `Sale`; tổng units là `3 + 5 + 2 = 10`; tổng cents `1200 + 1800 + 600 = 3600`; tổng weight là `1.5 + 2.25 + 1.25 = 5.0`.
6. `printf(Locale.ROOT, ...)` cố định dấu thập phân là dấu chấm, dùng định dạng `%.2f` để stdout có số chữ số nhất định, tránh phụ thuộc locale mặc định.

Trong ví dụ có **ba phép collect độc lập**, vì ta muốn ba loại thống kê khác nhau. Nếu chỉ cần một nhóm số liệu, một lần collect là đủ. Với nguồn chỉ được duyệt một lần, có thể cân nhắc `Collectors.teeing` hoặc collector tổng hợp khác thay vì tiêu thụ lại cùng một `Stream`.

## 3. Sự khác nhau giữa số nguyên 32-bit, 64-bit và double

Ba collector không phải ba tên gọi thay thế cho cùng kết quả. Chọn theo kiểu và miền giá trị cần xử lý:

- Dùng **`summarizingInt`** cho số lượng, tuổi, điểm hoặc các thuộc tính là `int`; kết quả sum kiểu `long`.
- Dùng **`summarizingLong`** cho bộ đếm dài, timestamp số hoặc số tiền biểu diễn bằng đơn vị nhỏ với kiểu `long`; kết quả sum vẫn kiểu `long`.
- Dùng **`summarizingDouble`** cho số đo thực, khối lượng, nhiệt độ hoặc các chỉ số chấp nhận sai số `double`; kết quả có thể chứa `NaN` hoặc các giá trị vô hạn nếu đầu vào có những giá trị này.

Ví dụ với `int` lớn:

~~~java
// Minh họa trong một phương thức:
IntSummaryStatistics stats =
        java.util.stream.Stream.of(Integer.MAX_VALUE, Integer.MAX_VALUE)
                .collect(java.util.stream.Collectors.summarizingInt(
                        Integer::intValue));

System.out.println(stats.getSum()); // 4294967294
~~~

Nếu dùng `IntStream.sum()`, tổng của các phần tử `int` có kiểu `int` và có thể tràn khi vượt giới hạn. `IntSummaryStatistics.getSum()` dùng `long` nên lưu được tổng `4294967294` ở ví dụ trên. Điều này **không** đồng nghĩa hỗ trợ số lớn tùy ý: sau ngưỡng `Long.MAX_VALUE` vẫn có nguy cơ tràn.

Trên `LongSummaryStatistics`, phép cộng là số nguyên `long`; không tự phát hiện mọi trường hợp overflow. Với dữ liệu tài chính hoặc kế toán đòi hỏi phát hiện tràn, nên cân nhắc chiến lược số học có kiểm tra, `BigDecimal`/`BigInteger` hoặc mô hình khác phù hợp nghiệp vụ thay vì dựa vào summary statistics.

## 4. Khi Stream rỗng: kết quả không phải `Optional`

Đây là điểm dễ nhầm với các terminal operation như `average()`, `min()`, `max()` trên primitive stream. Các collector `summarizing...` **vẫn tạo ra một đối tượng thống kê hợp lệ**, kể cả khi không có phần tử.

| Giá trị khi nguồn rỗng | `IntSummaryStatistics` | `LongSummaryStatistics` | `DoubleSummaryStatistics` |
| --- | --- | --- | --- |
| `getCount()` | `0` | `0` | `0` |
| `getSum()` | `0` (long) | `0` (long) | `0.0` |
| `getMin()` | `Integer.MAX_VALUE` | `Long.MAX_VALUE` | `Double.POSITIVE_INFINITY` |
| `getMax()` | `Integer.MIN_VALUE` | `Long.MIN_VALUE` | `Double.NEGATIVE_INFINITY` |
| `getAverage()` | `0.0` | `0.0` | `0.0` |

Các giá trị min/max của trường hợp rỗng là **sentinel dùng làm giá trị khởi đầu cho phép tổng hợp**, không phải bằng chứng rằng dữ liệu có giá trị min/max thật. Muốn trình bày min/max hoặc average như một thống kê có ý nghĩa, nên kiểm tra `getCount() > 0` trước. Không lấy `getMin() == Integer.MAX_VALUE` để suy ra rỗng, vì giá trị đó cũng có thể thực sự xuất hiện trong dữ liệu.

File `EmptySummaryDemo.java`:

~~~java
import java.util.IntSummaryStatistics;
import java.util.LongSummaryStatistics;
import java.util.DoubleSummaryStatistics;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class EmptySummaryDemo {
    public static void main(String[] args) {
        IntSummaryStatistics ints = Stream.<Integer>empty()
                .collect(Collectors.summarizingInt(Integer::intValue));
        LongSummaryStatistics longs = Stream.<Long>empty()
                .collect(Collectors.summarizingLong(Long::longValue));
        DoubleSummaryStatistics doubles = Stream.<Double>empty()
                .collect(Collectors.summarizingDouble(Double::doubleValue));

        System.out.println("int count=" + ints.getCount()
                + ", sum=" + ints.getSum()
                + ", min=" + ints.getMin()
                + ", max=" + ints.getMax()
                + ", avg=" + ints.getAverage());

        System.out.println("long count=" + longs.getCount()
                + ", sum=" + longs.getSum()
                + ", min=" + longs.getMin()
                + ", max=" + longs.getMax()
                + ", avg=" + longs.getAverage());

        System.out.println("double count=" + doubles.getCount()
                + ", sum=" + doubles.getSum()
                + ", min=" + doubles.getMin()
                + ", max=" + doubles.getMax()
                + ", avg=" + doubles.getAverage());
    }
}
~~~

~~~bash
javac --release 17 EmptySummaryDemo.java
java EmptySummaryDemo
~~~

Stdout:

~~~text
int count=0, sum=0, min=2147483647, max=-2147483648, avg=0.0
long count=0, sum=0, min=9223372036854775807, max=-9223372036854775808, avg=0.0
double count=0, sum=0.0, min=Infinity, max=-Infinity, avg=0.0
~~~

Ở đây, **nguồn rỗng không tạo `Optional.empty()`**. Nếu nghiệp vụ yêu cầu hiển thị “không có dữ liệu” thay vì số trung bình bằng 0, hãy xét count:

~~~java
// Đoạn minh họa nằm trong phương thức có IntSummaryStatistics stats.
String averageText = stats.getCount() == 0
        ? "Không có dữ liệu" : Double.toString(stats.getAverage());
~~~

Một bộ thống kê có `getCount() == 1` mới thực sự có một giá trị quan sát; khi đó min và max của nó đều là chính giá trị đó, average tương ứng với giá trị đã chuyển sang double.

## 5. Dùng `summarizingInt` làm downstream collector của `groupingBy`

Một ứng dụng rất hữu ích là **thống kê theo từng nhóm** thay vì toàn bộ stream. `Collectors.groupingBy(classifier, downstream)` tạo ra `Map<K,D>`; `downstream` có thể là một trong ba collector tổng hợp.

Ví dụ: thống kê số lượng bán theo vùng, với kết quả `Map<String,IntSummaryStatistics>`:

~~~text
Stream<Purchase>
    .collect(groupingBy(Purchase::region,
                        summarizingInt(Purchase::units)))
                   ↓
Map<String, IntSummaryStatistics>
~~~

Tạo file `GroupedSummaryDemo.java`:

~~~java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupedSummaryDemo {
    record Purchase(String region, int units) {}

    public static void main(String[] args) {
        List<Purchase> purchases = List.of(
                new Purchase("North", 2),
                new Purchase("South", 4),
                new Purchase("North", 6)
        );

        Map<String, IntSummaryStatistics> perRegion = purchases.stream()
                .collect(Collectors.groupingBy(
                        Purchase::region,
                        TreeMap::new,
                        Collectors.summarizingInt(Purchase::units)));

        perRegion.forEach((region, summary) ->
                System.out.println(region
                        + ": count=" + summary.getCount()
                        + ", sum=" + summary.getSum()
                        + ", avg=" + summary.getAverage()));
    }
}
~~~

~~~bash
javac --release 17 GroupedSummaryDemo.java
java GroupedSummaryDemo
~~~

Stdout:

~~~text
North: count=2, sum=8, avg=4.0
South: count=1, sum=4, avg=4.0
~~~

`TreeMap::new` sắp khóa theo thứ tự tự nhiên, nên thứ tự hai dòng `North` và `South` có thể dự đoán. Overload `groupingBy` mặc định không hứa kiểu Map hay thứ tự duyệt nhất định.

Quan trọng: nếu nguồn rỗng, **Map kết quả của `groupingBy` rỗng**; collector không tự tạo sẵn các nhóm chưa xuất hiện. Nếu một nhóm tồn tại và downstream nhận các phần tử của nhóm đó, `IntSummaryStatistics` chứa số liệu ứng với nhóm. Nếu cần cả những nhóm không có bản ghi, phải bổ sung chúng theo hợp đồng dữ liệu ở một bước riêng.

Bạn cũng có thể đổi `summarizingInt(Purchase::units)` thành `summarizingLong(Purchase::longValue)` hoặc `summarizingDouble(Purchase::measurement)` khi domain model có getter phù hợp. Kiểu giá trị trong Map sẽ đổi theo.

## 6. Chuyển đối tượng thống kê thành giá trị nghiệp vụ

Không phải lúc nào API đầu ra cũng cần cả năm trường. Nếu chỉ muốn **trung bình theo nhóm**, có thể dùng `Collectors.collectingAndThen` để chuyển `IntSummaryStatistics` thành `Double`:

~~~java
// Đoạn minh họa trong phương thức có List<Purchase> purchases.
Map<String, Double> averageByRegion = purchases.stream()
        .collect(Collectors.groupingBy(
                Purchase::region,
                java.util.TreeMap::new,
                Collectors.collectingAndThen(
                        Collectors.summarizingInt(Purchase::units),
                        IntSummaryStatistics::getAverage)));
~~~

Cấu trúc kiểu:

~~~text
summarizingInt(Purchase::units)
       → IntSummaryStatistics
collectingAndThen(..., IntSummaryStatistics::getAverage)
       → Double
groupingBy(Purchase::region, ...)
       → Map<String, Double>
~~~

Nếu chỉ cần trung bình mà không cần count/min/max, `Collectors.averagingInt(Purchase::units)` là collector chuyên biệt, thường rõ ý hơn và tạo trực tiếp `Double`. Nếu cần cả bộ thống kê, `summarizingInt` tránh việc phải tính lại từng đại lượng.

Để tạo báo cáo cần hiển thị min/max có thể rỗng, cân nhắc chuyển đối tượng thống kê thành DTO bất biến sau khi `collect`, đồng thời biểu diễn riêng `count == 0` thay vì đưa min/max sentinel ra ngoài như dữ liệu thật.

## 7. So sánh với `averagingInt`, `summingInt` và primitive `summaryStatistics()`

Các API gần nhau nhưng khác kiểu trả về:

| API | Kiểu kết quả | Thích hợp khi |
| --- | --- | --- |
| `collect(summarizingInt(T::value))` | `IntSummaryStatistics` | Cần count, sum, min, max, average cùng lúc; dùng downstream `groupingBy`. |
| `collect(summarizingLong(T::value))` | `LongSummaryStatistics` | Cần bộ thống kê của khóa `long`. |
| `collect(summarizingDouble(T::value))` | `DoubleSummaryStatistics` | Cần bộ thống kê của khóa `double`. |
| `collect(averagingInt(T::value))` | `Double` | Chỉ cần trung bình. |
| `collect(summingInt(T::value))` | `Integer` | Chỉ cần tổng kiểu `int` (có thể overflow). |
| `stream.mapToInt(T::value).summaryStatistics()` | `IntSummaryStatistics` | Đã/đang làm việc với `IntStream`. |
| `stream.mapToLong(T::value).summaryStatistics()` | `LongSummaryStatistics` | Đã/đang làm việc với `LongStream`. |
| `stream.mapToDouble(T::value).summaryStatistics()` | `DoubleSummaryStatistics` | Đã/đang làm việc với `DoubleStream`. |

Ví dụ:

~~~java
// Minh họa trong ngữ cảnh có List<Sale> sales.
IntSummaryStatistics a = sales.stream()
        .collect(Collectors.summarizingInt(Sale::units));

IntSummaryStatistics b = sales.stream()
        .mapToInt(Sale::units)
        .summaryStatistics();
~~~

Hai biểu thức cùng tổng hợp `units`, nhưng theo hai đường:

- `summarizingInt` là **collector** cho `Stream<Sale>`; thuận tiện khi truyền vào `groupingBy`, `mapping` và hệ thống collector.
- `mapToInt(...).summaryStatistics()` chuyển sang `IntStream` rồi gọi **terminal operation chuyên biệt**.

Đừng nhầm `IntStream.average()` trả `OptionalDouble` với `IntSummaryStatistics.getAverage()` trả `double`. Trên stream rỗng, `OptionalDouble.empty()` khác `0.0`; vì vậy khi dùng đối tượng summary cần kiểm tra count nếu yêu cầu không cho phép ngầm coi rỗng là trung bình 0.

## 8. Hàm extractor phải đúng kiểu và xử lý null rõ ràng

Ba hàm `summarizing...` nhận extractor primitive:

~~~java
// Chữ ký kiểu functional interface để tham khảo:
int applyAsInt(T element);
long applyAsLong(T element);
double applyAsDouble(T element);
~~~

Nếu getter trả `Integer`, `Long` hoặc `Double` wrapper, Java có thể **auto-unbox** để phù hợp với extractor. Điều đó có nghĩa **getter trả null có thể ném `NullPointerException`**, dù bản thân đối tượng chứa trường còn tồn tại.

Ví dụ:

~~~java
// Đoạn minh họa: Product.stock() trả Integer nullable.
products.stream()
        .collect(Collectors.summarizingInt(Product::stock));
~~~

Nếu một `Product` có stock null, phép unbox có thể thất bại. Có ba chính sách khác nhau:

1. **Từ chối dữ liệu thiếu**: validate/throw exception khi stock null.
2. **Bỏ qua bản ghi thiếu**: `.filter(p -> p.stock() != null)` trước collect. Khi đó `getCount()` đếm **các bản ghi có stock**, không phải toàn bộ products.
3. **Xem giá trị thiếu là 0**: `p -> p.stock() == null ? 0 : p.stock()`. Khi đó count vẫn tính cả bản ghi thiếu, còn tổng/average bị tác động bởi số 0 giả định.

Không chọn chính sách chỉ để tránh NPE; phải xuất phát từ ý nghĩa nghiệp vụ. **Bỏ qua null** khác với **thay null bằng 0**, đặc biệt khi tính average.

Với **phần tử nguồn null**, method reference kiểu `Product::stock` cũng không an toàn. `List.of(...)` không chấp nhận phần tử null, nhưng `Arrays.asList(...)` hoặc một số stream vẫn có thể chứa chúng. Nếu có thể, xác định chính sách null ngay tại nguồn thay vì để getter gây lỗi giữa pipeline.

### Ví dụ đầy đủ: bỏ giá trị thiếu và thay bằng 0 cho kết quả khác nhau

File `NullableValueSummaryDemo.java`:

~~~java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.stream.Collectors;

public class NullableValueSummaryDemo {
    record Item(String code, Integer stock) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("A", 4),
                new Item("B", null),
                new Item("C", 2));

        IntSummaryStatistics skipMissing = items.stream()
                .filter(item -> item.stock() != null)
                .collect(Collectors.summarizingInt(Item::stock));

        IntSummaryStatistics missingAsZero = items.stream()
                .collect(Collectors.summarizingInt(
                        item -> item.stock() == null ? 0 : item.stock()));

        System.out.println("skip count=" + skipMissing.getCount()
                + ", sum=" + skipMissing.getSum()
                + ", avg=" + skipMissing.getAverage());

        System.out.println("zero count=" + missingAsZero.getCount()
                + ", sum=" + missingAsZero.getSum()
                + ", avg=" + missingAsZero.getAverage());
    }
}
~~~

~~~bash
javac --release 17 NullableValueSummaryDemo.java
java NullableValueSummaryDemo
~~~

Stdout:

~~~text
skip count=2, sum=6, avg=3.0
zero count=3, sum=6, avg=2.0
~~~

Hai cách đều có sum 6, nhưng count và average khác nhau. Vì vậy, trong báo cáo, nên nêu rõ **mẫu số của trung bình** có bao gồm bản ghi thiếu hay không.

## 9. Đặc điểm của `DoubleSummaryStatistics`: độ chính xác và giá trị đặc biệt

Các số `double` không thể biểu diễn chính xác tất cả số thập phân. Ví dụ, `0.1 + 0.2` thường không bằng chính xác `0.3` trong so sánh double. Khi thu thập số thực:

- **Tổng/average có thể làm tròn**. JDK dùng kỹ thuật cộng bù trong `DoubleSummaryStatistics` để giảm một số sai số, nhưng không biến double thành số học thập phân chính xác.
- **Thứ tự kết hợp có thể ảnh hưởng kết quả cuối**; parallel pipeline có thể phân chia và gộp theo thứ tự khác. Không đặt yêu cầu “bit-for-bit luôn như nhau” cho tổng double từ mọi cách thực thi.
- Nếu có **`Double.NaN`**, `getMin()` và `getMax()` trở thành `NaN`, và thống kê tổng/trung bình cũng có thể là `NaN`.
- Nếu tổng có cả **`Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY`**, phép cộng có thể cho `NaN`.
- `-0.0` và `+0.0` có quy tắc so sánh min/max theo số thực Java; không tự coi chúng giống hoàn toàn ở mọi phép toán.
- **Độ chính xác tài chính:** với tiền tệ cần tổng chính xác, dùng số nguyên đơn vị nhỏ khi không tràn hoặc `BigDecimal` với collector/giải pháp tổng hợp thích hợp.

Nếu dữ liệu đo lường có thể chứa `NaN` hay infinity, xác định rõ có **loại bỏ, báo lỗi hay cho phép** các giá trị đó trước `summarizingDouble`. Một collector thống kê không tự phát minh quy tắc nghiệp vụ cho số đo bất thường.

Ngoài ra, **trung bình ở đây là trung bình cộng không trọng số**. Nếu muốn trung bình theo khối lượng, thời lượng hay tần suất, phải đồng thời tính `sum(value * weight)` và `sum(weight)` rồi chia khi tổng trọng số hợp lệ; `summarizingDouble(value)` đơn thuần không thực hiện weighted average.

## 10. Dùng đối tượng thống kê và tính mutable

`IntSummaryStatistics`, `LongSummaryStatistics`, `DoubleSummaryStatistics` là **đối tượng mutable**, có các phương thức như `accept(value)` và `combine(other)`. `Collectors.summarizing...` sử dụng cơ chế tích lũy/gộp số liệu để tạo kết quả cuối; nhưng khi nhận kết quả `stats`, lập trình viên vẫn có thể sửa trạng thái của nó nếu gọi `accept` hoặc `combine`.

Ví dụ đoạn minh họa:

~~~java
IntSummaryStatistics stats = new IntSummaryStatistics();
stats.accept(4);
stats.accept(6);
System.out.println(stats.getSum()); // 10
~~~

Vì thế:

- Đừng trả trực tiếp đối tượng summary mutable qua API cần tính bất biến nếu caller có thể chỉnh số liệu.
- Nếu cần lưu snapshot cố định, trích `count`, `sum`, `min`, `max`, `average` vào record/DTO và quy định rõ cách diễn đạt trường hợp rỗng.
- Đừng chia sẻ một đối tượng statistics để nhiều thread tự gọi `accept` mà không có cơ chế đồng bộ. Các collector trong pipeline song song có cơ chế tích lũy/kết hợp phù hợp của chúng; điều đó không biến một instance summary tùy ý thành đối tượng thread-safe.
- Không dùng extractor có side effect hoặc đọc trạng thái mutable thay đổi khi stream đang xử lý; kết quả count/sum/min/max có thể không phản ánh một snapshot nhất quán.

Một đối tượng statistics sau khi được trả từ collector có thể được truy xuất nhiều lần qua getters mà không cần chạy lại stream, miễn không có ai tiếp tục sửa nó.

## 11. Hiệu năng, parallel stream và collector kết hợp

Lợi ích chính của summary collector là **một lượt tích lũy** cho nhiều chỉ số. Việc tính count, sum, min, max và average trong cùng accumulator thường hiệu quả và rõ ràng hơn việc chạy năm stream pipelines tách biệt trên nguồn có chi phí đọc cao.

Tuy nhiên:

1. **Extractor có thể tốn thời gian** (chuyển đổi, truy xuất giá trị từ đối tượng). Nên giữ nó thuần, ngắn, không truy vấn database/mạng trên mỗi phần tử nếu tránh được.
2. **Truyền dữ liệu qua stream vẫn có chi phí**; với tập cực nhỏ, một vòng lặp đơn giản cũng có thể phù hợp. Không có bảo đảm stream nhanh hơn mọi cách khác.
3. **Parallel stream** có thể tạo nhiều container thống kê rồi `combine`, nên không dựa vào thứ tự gọi extractor. Với double, thứ tự kết hợp có thể ảnh hưởng sai số.
4. **Không tạo nhiều stream trên cùng instance** đã tiêu thụ: nếu cần thống kê các thuộc tính khác nhau, phải dùng stream mới từ collection hoặc một collector tổng hợp nhiều kết quả trong một lượt.
5. Các lớp summary hoạt động trên giá trị primitive, giúp tránh boxing không cần thiết trong quá trình thống kê nếu extractor trả primitive trực tiếp.

Nếu ứng dụng cần **cả** thống kê lượng bán và tổng tiền trong **một lượt duy nhất**, Java 12+ có `Collectors.teeing` để kết hợp hai collector và một hàm tạo kết quả cuối. Còn với các nhóm, `groupingBy(classifier, summarizingInt(...))` là cách kết hợp rõ ràng, thường là lựa chọn đầu tiên.

## 12. Tránh sai kiểu khi ghép `map`, `filter` và downstream collector

Ví dụ:

~~~java
// Giả sử sales: List<Sale>.
sales.stream()
        .filter(sale -> sale.units() > 0)
        .collect(Collectors.summarizingInt(Sale::units));
~~~

Sau `filter`, kiểu phần tử vẫn là `Sale`, nên `Sale::units` hợp lệ. Nhưng nếu thêm `.map(Sale::region)` trước collect thì stream chuyển thành `Stream<String>`; `Sale::units` **không còn đúng kiểu**.

Một cách khác hợp lệ:

~~~java
// Chỉ muốn thống kê độ dài tên vùng (Stream<String>):
sales.stream()
        .map(Sale::region)
        .collect(Collectors.summarizingInt(String::length));
~~~

Lúc này `getCount()` đếm số chuỗi vùng đi qua pipeline; `getMin()` và `getMax()` là **độ dài chuỗi**, không còn là lượng hàng bán. Khi đọc pipeline, phải luôn xác định kiểu `T` tại thời điểm gọi collector và điều gì thực sự được trích xuất.

Trong `groupingBy`, `downstream` nhận phần tử **sau các bước trung gian** của stream, không nhận key của Map do classifier trả về. Ví dụ `groupingBy(Sale::region, summarizingInt(Sale::units))` vẫn đưa từng `Sale` vào summary của vùng tương ứng.

## 13. Những lỗi thường gặp

1. **Nghĩ `summarizingInt` chỉ trả một `int` tổng.** Thực ra trả `IntSummaryStatistics`; tổng lấy bằng `getSum()` có kiểu `long`.
2. **Nhầm kết quả nguồn rỗng với `Optional.empty()`.** Summary collector trả đối tượng statistics với count 0, sum 0, average 0.0 và sentinel min/max.
3. **Hiển thị min/max sentinel của nguồn rỗng như giá trị thật.** Phải xem `getCount() > 0` trước khi công bố ý nghĩa của min/max.
4. **Cho rằng average luôn là số nguyên.** `getAverage()` trả `double`; ví dụ tổng 10 trên 3 phần tử cho 3.333...
5. **Không phân biệt `summarizingLong` với `summarizingInt`.** Long nhận `long` và tổng `long`; Int nhận `int`, tổng cũng lưu trong `long`.
6. **Giả định tổng `long` không bao giờ tràn.** `long` vẫn hữu hạn; cần giải pháp số lớn/kiểm tra overflow khi miền dữ liệu yêu cầu.
7. **Dùng `summarizingDouble` để cộng tiền cần chính xác tuyệt đối.** Double có sai số; dùng `BigDecimal` hoặc đơn vị nhỏ phù hợp.
8. **Không xử lý `NaN`/infinity.** Chúng ảnh hưởng ý nghĩa min, max, sum và average của thống kê số thực.
9. **Dùng extractor trả wrapper nullable mà không kiểm tra.** Auto-unboxing `null` ném `NullPointerException`.
10. **Lọc bỏ giá trị null mà vẫn nghĩ count bằng số bản ghi gốc.** Count chỉ tính số phần tử được đưa vào collector.
11. **Dùng `groupingBy` và mong xuất hiện cả nhóm không có bản ghi.** Map không tự tạo khóa nhóm vắng mặt.
12. **Dựa vào thứ tự duyệt của Map mặc định.** Muốn thứ tự khóa xác định, chọn `TreeMap::new` hoặc quy tắc khác đúng hợp đồng.
13. **Dùng cùng stream cho nhiều lần collect.** Terminal operation tiêu thụ stream; tạo stream mới từ nguồn nếu cần.
14. **Chia sẻ statistics mutable giữa các thread rồi tự gọi `accept`.** Không mặc nhiên thread-safe.
15. **Dùng `summarizingDouble` để tính weighted average.** Đây là trung bình cộng thông thường, không có trọng số.
16. **Tin rằng chạy parallel luôn nhanh hơn.** Nguồn, kích thước, chi phí kết hợp và loại số quyết định hiệu quả thực tế.

## 14. Checklist trước khi áp dụng

- Cần **cả năm chỉ số** hay chỉ cần một số cụ thể như `sum`/`average`?
- Kiểu dữ liệu đầu vào là `int`, `long` hay `double`? Có nguy cơ overflow hoặc sai số?
- Extractor có trả đúng primitive và xử lý wrapper `null` an toàn không?
- Nguồn có thể rỗng không? Nếu rỗng, có kiểm tra `getCount()` trước khi hiển thị min/max/average không?
- Cần thống kê **toàn bộ nguồn** hay từng nhóm theo `groupingBy`?
- Tập dữ liệu có `NaN`, infinity, giá trị âm hoặc lượng đo bất thường không?
- Nếu chạy song song, extractor có stateless, không can thiệp nguồn và không tạo side effect không?
- Có cần biến đối tượng thống kê mutable thành DTO bất biến trước khi chia sẻ ra ngoài không?
- Các phép biến đổi `filter/map` trước collector đã làm thay đổi kiểu hoặc số phần tử được thống kê chưa?
- Test đã bao gồm dữ liệu rỗng, một phần tử, nhiều phần tử, giá trị null, giá trị biên và số thực khó biểu diễn chưa?

**Ghi nhớ:** `Collectors.summarizingInt/Long/Double(extractor)` giúp một `Stream<T>` tạo một đối tượng chứa **count, sum, min, max, average** dựa trên giá trị số mà extractor lấy ra. Dùng `groupingBy(..., summarizing...)` để thống kê theo nhóm; kiểm tra `count == 0` để không diễn giải sai sentinel khi nguồn rỗng, và chọn đúng kiểu số để tránh tràn hoặc sai số ngoài ý muốn.
