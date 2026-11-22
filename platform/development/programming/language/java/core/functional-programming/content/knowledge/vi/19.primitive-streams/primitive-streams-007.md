# Tràn số nguyên và sai số số thực trong phép tổng hợp Stream Java

## 1. Vì sao sum() và average() có thể cho kết quả bất ngờ?

Các stream nguyên thủy `IntStream`, `LongStream`, `DoubleStream` cho phép tính tổng, trung bình, cực trị và thống kê mà không cần boxing từng phần tử. Ví dụ:

```java
int total = java.util.stream.IntStream.of(1, 2, 3).sum(); // 6
double mean = java.util.stream.DoubleStream.of(1.0, 2.0, 3.0)
        .average().orElseThrow(); // 2.0
```

Hai câu lệnh này đặt trong thân một phương thức Java. Khi dữ liệu lớn, nhiều phần tử hoặc có giá trị chênh lệch đáng kể, người học phải kiểm soát hai **nhóm vấn đề khác nhau**:

1. **Tràn số nguyên (*integer overflow*)**: kết quả toán học vượt khỏi miền biểu diễn của `int` hoặc `long`, làm tổng nguyên thủy bị cuộn vòng (*wraparound*) và **không tự ném ngoại lệ**.
2. **Sai số số thực (*floating-point error*)**: các số kiểu `double` có biểu diễn nhị phân hữu hạn và phép cộng cần làm tròn. Tổng hoặc trung bình có thể không trùng kết quả thập phân mong đợi; **thứ tự nhóm/cộng** có thể thay đổi giá trị gần đúng.

Ví dụ đáng nhớ:

```text
Integer.MAX_VALUE + 1 = 2147483648 (toán học)
IntStream.sum() trả        -2147483648 (int bị tràn)

0.1 + 0.2 = 0.3            (toán học thập phân)
double có thể biểu diễn    0.30000000000000004
```

Điểm chính: **Stream API không biến phép cộng kiểu nguyên thủy thành phép tính chính xác không giới hạn**. Phải quyết định kiểu dữ liệu, cách phát hiện tràn và mức sai số chấp nhận được **trước khi** tổng hợp.

## 2. Nhắc lại các kiểu stream nguyên thủy

| API | Kiểu phần tử | Kiểu trả của `sum()` | Kiểu trả của `average()` | Ghi chú |
| --- | --- | --- | --- | --- |
| `IntStream` | `int` có dấu, 32 bit | `int` | `OptionalDouble` | `sum()` có thể tràn `int` |
| `LongStream` | `long` có dấu, 64 bit | `long` | `OptionalDouble` | `sum()` có thể tràn `long` |
| `DoubleStream` | `double` IEEE 754, 64 bit | `double` | `OptionalDouble` | Có sai số biểu diễn/làm tròn, `Infinity`/`NaN` |

Miền của `int`: từ `-2_147_483_648` đến `2_147_483_647`; `long`: từ `-9_223_372_036_854_775_808L` đến `9_223_372_036_854_775_807L`.

Tổng của một dãy có thể vượt miền kiểu dữ liệu **ngay cả khi mọi phần tử đều nằm trong miền**. Ví dụ hai số nguyên dương `2_000_000_000` đều hợp lệ ở kiểu `int`, nhưng tổng `4_000_000_000` thì không.

`average()` trả `OptionalDouble` vì nguồn có thể rỗng; cách tính trung bình không nên được suy diễn là “gọi `sum()` rồi chia bằng `int`” trong mọi triển khai. Chẳng hạn trung bình của hai `int` lớn vẫn có thể hợp lệ mặc dù `IntStream.sum()` tràn. Tuy nhiên giá trị `double` trả về cũng có thể cần làm tròn.

## 3. IntStream.sum(): tràn mà không cảnh báo

Ví dụ:

```java
int max = Integer.MAX_VALUE;
int result = IntStream.of(max, 1).sum();
System.out.println(result); // -2147483648
```

Đây là các lệnh thuộc một phương thức đã import `java.util.stream.IntStream`. `Integer.MAX_VALUE` là `2_147_483_647`. Cộng thêm `1` cho kết quả toán học `2_147_483_648`, vượt `int`.

`IntStream.sum()` dùng ngữ nghĩa cộng `int`: Java **không tự ném `ArithmeticException`** cho phép cộng nguyên thông thường. Kết quả lưu trong `int` bị cuộn vòng theo biểu diễn 32 bit, ở đây là số âm `-2_147_483_648`.

Một nguy cơ trong ứng dụng:

```text
Số lượng đặt hàng/giá trị gộp đáng ra lớn dương
              |
       IntStream.sum()
              |
       tràn thành âm
              |
   kiểm tra nghiệp vụ kết luận sai
```

Tác động không chỉ là “sai vài đơn vị”, mà có thể làm đổi dấu giá trị; điều kiện `total > 0` cũng có thể trả kết quả ngược.

**Không thể nhận diện mọi trường hợp tràn bằng dấu của tổng.** Phép cộng với số âm, nhiều bước cộng hoặc các phần tử thay đổi dấu có thể khiến kết quả cuối trông hợp lý dù đã tràn trung gian.

## 4. Mở rộng kiểu **trước** phép cộng

Nếu tổng các giá trị `int` có thể vượt `int` nhưng vẫn nằm trong `long`, cách đơn giản thường là tạo `LongStream` **trước khi** `sum()`:

```java
long correct = IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum(); // 2147483648
```

Có thể dùng:

```java
long alsoCorrect = IntStream.of(Integer.MAX_VALUE, 1)
        .mapToLong(n -> n)
        .sum(); // 2147483648
```

Các đoạn là lệnh trong phương thức đã import `IntStream`. `asLongStream()` chuyển mỗi phần tử `int` sang `long` trước khi tổng hợp; `mapToLong` có hiệu ứng tương tự trong trường hợp này.

**Đây là cách sai:**

```java
long wrong = (long) IntStream.of(Integer.MAX_VALUE, 1).sum();
```

`sum()` đã trả về `int` bị tràn (`-2_147_483_648`). Ép kết quả sai đó thành `long` chỉ tạo `-2_147_483_648L`, **không khôi phục tổng đúng**.

So sánh:

| Biểu thức | Thời điểm mở rộng kiểu | Giá trị |
| --- | --- | --- |
| `(long) IntStream.of(MAX, 1).sum()` | **Sau** tổng hợp | `-2147483648` (sai) |
| `IntStream.of(MAX, 1).asLongStream().sum()` | **Trước** tổng hợp | `2147483648` |
| `IntStream.of(MAX, 1).mapToLong(n -> n).sum()` | **Trước** tổng hợp | `2147483648` |

**Giới hạn:** `long` cũng có miền hữu hạn. Mở rộng `int → long` chỉ giải quyết bài toán khi **tổng dự kiến vừa trong `long`**. Đừng xem đây là giải pháp số nguyên không giới hạn.

## 5. LongStream.sum(): tràn 64 bit vẫn có thể xảy ra

`LongStream.sum()` trả `long`; nó không tự nâng lên `BigInteger`.

```java
long wrapped = LongStream.of(Long.MAX_VALUE, 1L).sum();
// -9223372036854775808
```

Đây là đoạn đặt trong phương thức có import `java.util.stream.LongStream`.

Với đầu vào `Long.MAX_VALUE` (`9_223_372_036_854_775_807`) và `1`, tổng toán học là `9_223_372_036_854_775_808`. Kết quả `long` bị cuộn về `Long.MIN_VALUE`.

Không thể “mở rộng sang `double`” rồi mặc nhiên có độ chính xác số nguyên. `double` có phần định trị hữu hạn (53 bit precision), không biểu diễn được chính xác mọi giá trị nguyên `long` lớn. Chuyển sang `double` chỉ đổi **lỗi tràn** thành một bài toán **làm tròn/độ chính xác** khác.

Khi giá trị có thể vượt `long` mà vẫn cần tổng chính xác, hãy cân nhắc `BigInteger` hoặc thiết kế dữ liệu theo miền nghiệp vụ.

## 6. Cần phát hiện tràn? Dùng Math.addExact()

Nếu vượt miền kiểu là **lỗi cần báo**, có thể sử dụng `Math.addExact` trong phép tổng hợp:

```java
int checked = IntStream.of(1, 2, 3)
        .reduce(0, Math::addExact); // 6
```

Đây là các lệnh minh họa trong phương thức có `IntStream`. Phương thức `Math.addExact(int, int)` (và overload `long`) **ném `ArithmeticException`** nếu phép cộng tại bước đó tràn.

Ví dụ bắt lỗi:

```java
try {
    int checked = IntStream.of(Integer.MAX_VALUE, 1)
            .reduce(0, Math::addExact);
    System.out.println(checked);
} catch (ArithmeticException e) {
    System.out.println("overflow");
}
```

Kết quả `overflow` trên Java 17. `LongStream.of(Long.MAX_VALUE,1L).reduce(0L, Math::addExact)` cũng ném `ArithmeticException`.

**Cảnh báo về tổng trung gian:** ngay cả khi **tổng toán học cuối** nằm trong miền, thứ tự phép cộng vẫn có thể đi qua giá trị ngoài miền. Ví dụ `[Integer.MAX_VALUE, 1, -1]` có tổng cuối bằng `Integer.MAX_VALUE`, nhưng khi tuần tự cộng `MAX + 1` trước, `Math.addExact` sẽ phát hiện tràn. Vì thế `reduce(0, Math::addExact)` là một cách **kiểm tra các bước cộng thực tế**, không có nghĩa thuật toán tính tổng không giới hạn rồi mới kiểm tra kết quả cuối.

Trong xử lý song song, cách nhóm phần tử có thể khác; điều này càng củng cố nhu cầu sử dụng `BigInteger` khi bạn yêu cầu **tổng toán học chính xác** rồi mới kiểm tra miền đầu ra.

## 7. BigInteger: chính xác cho tổng số nguyên lớn

`BigInteger` biểu diễn số nguyên có độ lớn thực tế chỉ bị giới hạn bởi tài nguyên bộ nhớ, không bị giới hạn ở 32 hay 64 bit như `int`/`long`.

```java
BigInteger exact = LongStream.of(Long.MAX_VALUE, 1L)
        .mapToObj(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

System.out.println(exact); // 9223372036854775808
```

Đây là các lệnh trong phương thức đã import `java.math.BigInteger` và `LongStream`. Mỗi phần tử được chuyển sang `BigInteger` **trước** khi cộng. Giá trị `BigInteger.ZERO` là phần tử đơn vị của phép cộng.

Ví dụ tương tự với `IntStream`:

```java
BigInteger exactInt = IntStream.of(Integer.MAX_VALUE, 1)
        .mapToObj(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);
```

Tổng là `2147483648`, không tràn.

Đánh đổi: các phép toán `BigInteger` có thể tốn cấp phát/bộ nhớ và CPU hơn phép cộng primitive. Hãy chọn theo **miền giá trị thực tế** và yêu cầu chính xác, không dùng `BigInteger` vô điều kiện cho mọi dãy nhỏ.

Nếu cần chuyển `BigInteger` về `long` nhưng muốn phát hiện vượt miền, dùng `longValueExact()` thay vì `longValue()`: phương thức `Exact` ném `ArithmeticException` khi không biểu diễn được chính xác.

## 8. summaryStatistics() và average() không giống sum() về kiểu tổng

Java có `IntStream.summaryStatistics()` trả `IntSummaryStatistics`. Đối tượng này lưu tổng ở kiểu `long`, khác với `IntStream.sum()` trả `int`:

```java
IntSummaryStatistics stats =
        IntStream.of(Integer.MAX_VALUE, 1).summaryStatistics();

System.out.println(stats.getSum()); // 2147483648
System.out.println(stats.getAverage()); // 1.073741824E9
```

Đoạn minh họa có import `java.util.IntSummaryStatistics` và `IntStream`. `getAverage()` trả `double`, trong trường hợp này biểu diễn được chính xác `1_073_741_824.0`.

`IntStream.of(Integer.MAX_VALUE,1).average().orElseThrow()` cũng trả trung bình biểu diễn thành `1.073741824E9` trên chương trình kiểm thử Java 17. **Không suy ra** rằng `average()` luôn tính trung bình bằng cách gọi `IntStream.sum()` rồi chia số lượng, bởi `sum()` có thể đã tràn `int`.

Tuy nhiên vẫn phải kiểm tra giới hạn:

- `IntSummaryStatistics.getSum()` có kiểu `long`, vẫn hữu hạn.
- `LongStream.summaryStatistics()` và `LongSummaryStatistics.getSum()` sử dụng `long`; không tự cứu được tổng vượt `long`.
- Các trung bình biểu diễn bằng `double` có thể **làm tròn** với số nguyên lớn hoặc dữ liệu nhạy cảm độ chính xác.
- Với stream rỗng, `average()` trả `OptionalDouble.empty()`; gọi `orElseThrow()` khi rỗng sẽ phát sinh ngoại lệ.

`summaryStatistics` hữu ích khi cần đồng thời `count`, `sum`, `min`, `max`, `average`, nhưng **không phải công cụ tổng hợp chính xác tùy ý**.

## 9. Chương trình Java 17 hoàn chỉnh: tràn số nguyên

Tạo tệp `IntegerAggregateSafetyDemo.java`:

```java
import java.math.BigInteger;
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class IntegerAggregateSafetyDemo {
    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        System.out.println("intMax=" + max);
        System.out.println("intSumOverflow=" + IntStream.of(max, 1).sum());
        System.out.println("widenAfterOverflow=" + (long) IntStream.of(max, 1).sum());
        System.out.println("intToLongBeforeSum=" + IntStream.of(max, 1).asLongStream().sum());
        System.out.println("mapToLongBeforeSum=" +
                IntStream.of(max, 1).mapToLong(n -> n).sum());

        IntSummaryStatistics stats = IntStream.of(max, 1).summaryStatistics();
        System.out.println("intStatsSum=" + stats.getSum());
        System.out.println("intStatsAverage=" + stats.getAverage());
        System.out.println("intAverage=" +
                IntStream.of(max, 1).average().orElseThrow());

        System.out.println("longMax=" + Long.MAX_VALUE);
        System.out.println("longSumOverflow=" +
                LongStream.of(Long.MAX_VALUE, 1L).sum());
        BigInteger exactLong = LongStream.of(Long.MAX_VALUE, 1L)
                .mapToObj(BigInteger::valueOf)
                .reduce(BigInteger.ZERO, BigInteger::add);
        System.out.println("bigIntegerSum=" + exactLong);

        try {
            System.out.println("checkedIntSum=" +
                    IntStream.of(max, 1).reduce(0, Math::addExact));
        } catch (ArithmeticException e) {
            System.out.println("checkedIntSum=overflow");
        }

        try {
            System.out.println("checkedLongSum=" +
                    LongStream.of(Long.MAX_VALUE, 1L)
                            .reduce(0L, Math::addExact));
        } catch (ArithmeticException e) {
            System.out.println("checkedLongSum=overflow");
        }

        System.out.println("exactIntBigInteger=" + IntStream.of(max, 1)
                .mapToObj(BigInteger::valueOf)
                .reduce(BigInteger.ZERO, BigInteger::add));

        try {
            IntStream.of(max, 1, -1).reduce(0, Math::addExact);
            System.out.println("intermediate=ok");
        } catch (ArithmeticException e) {
            System.out.println("intermediate=overflow");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 IntegerAggregateSafetyDemo.java
java IntegerAggregateSafetyDemo
```

Đầu ra đã được kiểm chứng:

```text
intMax=2147483647
intSumOverflow=-2147483648
widenAfterOverflow=-2147483648
intToLongBeforeSum=2147483648
mapToLongBeforeSum=2147483648
intStatsSum=2147483648
intStatsAverage=1.073741824E9
intAverage=1.073741824E9
longMax=9223372036854775807
longSumOverflow=-9223372036854775808
bigIntegerSum=9223372036854775808
checkedIntSum=overflow
checkedLongSum=overflow
exactIntBigInteger=2147483648
intermediate=overflow
```

Các nhóm kết quả được cố tình đặt cạnh nhau: **ép kiểu sau tràn** vẫn sai; **nâng lên long trước khi sum** đúng khi tổng vừa long; **Math.addExact** phát hiện tràn; **BigInteger** giữ đúng tổng toán học.

Với đầu vào chứa các phần tử có thể đổi dấu, lưu ý `intermediate=overflow` minh họa đường cộng tuần tự qua giá trị ngoài miền, dù tổng toán học cuối của ba phần tử vẫn nằm trong miền `int`.

## 10. DoubleStream: vì sao 0.1 + 0.2 có thể không bằng 0.3?

Kiểu `double` dùng biểu diễn dấu phẩy động **nhị phân** (theo IEEE 754). Những số thập phân như `0.1`, `0.2`, `0.3` thường **không có biểu diễn nhị phân hữu hạn chính xác**. Khi chúng được lưu dưới dạng `double`, giá trị đã bị làm tròn đến một số nhị phân biểu diễn được.

Vì vậy:

```java
double total = DoubleStream.of(0.1, 0.2).sum();
System.out.println(total); // 0.30000000000000004 trên Java 17 kiểm thử
```

Đoạn thuộc phương thức có import `DoubleStream`. Kết quả không phải do “Stream cộng sai phép toán”, mà đến từ **giới hạn biểu diễn và làm tròn của số thực**. Ngay cả `0.1 + 0.2` không dùng Stream cũng cho giá trị đó trong chương trình kiểm thử.

Sai số thường nhỏ theo quy mô của số, nhưng **không thể kết luận mọi sai số đều không đáng kể**: khi cộng số lượng lớn, trừ các số gần nhau, hoặc có yêu cầu tài chính/chính xác cao, sai số có thể ảnh hưởng đến quyết định nghiệp vụ.

`DoubleStream.sum()` có thể sử dụng kỹ thuật cộng bù (*compensated summation*) để giảm sai số, tùy triển khai, nhưng **không hứa kết quả thập phân chính xác tuyệt đối**; Javadoc nêu rõ việc cộng số thực có thể phụ thuộc thứ tự tổng hợp.

## 11. Thứ tự cộng có thể làm thay đổi kết quả double

Trong số thực toán học, phép cộng có tính kết hợp: `(a + b) + c = a + (b + c)`. Trong phép cộng dấu phẩy động làm tròn, đẳng thức đó **không được đảm bảo**.

Xét ba số `1e16`, `1.0`, `-1e16`. Theo toán học, tổng là `1.0`. Tuy nhiên, khi cộng `1e16 + 1.0`, phần `1.0` rất nhỏ so với `1e16` nên có thể bị mất do làm tròn. Một thứ tự cộng khác có thể giữ lại được `1.0`.

Chương trình Java 17 được kiểm thử cho:

```java
double first = DoubleStream.of(1e16, 1.0, -1e16).sum();
double second = DoubleStream.of(1e16, -1e16, 1.0).sum();
```

Kết quả quan sát của chương trình ở mục 13 là `first = 0.0`, `second = 1.0`. **Không nên dùng hai con số cụ thể này làm cam kết bắt buộc cho mọi JDK/thuật toán tổng hợp**: đặc tả `DoubleStream.sum()` không cố định thứ tự cộng, và một triển khai có thể sử dụng cách giảm sai số khác. Điểm được minh họa là **phép tổng hợp số thực có thể nhạy với thứ tự và cách nhóm phép cộng**.

Với stream **song song**, các phần tổng có thể được tính theo từng nhóm rồi kết hợp, không nhất thiết giống cách cộng từ trái sang phải. Vì thế, dùng `parallel()` có thể thay đổi kết quả làm tròn ở các chữ số thấp, ngay cả khi nguồn dữ liệu không thay đổi.

Nếu quy trình cần **khả năng tái lập kết quả** ở độ chính xác cao, hãy xác định trước thứ tự, thuật toán và kiểu số phù hợp; không chỉ dựa vào việc giá trị được trả dưới dạng `double`.

## 12. average(), Infinity và NaN

`DoubleStream.average()` trả `OptionalDouble`; nó chịu ảnh hưởng của việc biểu diễn và tổng hợp bằng dấu phẩy động. Ví dụ:

```java
double average = DoubleStream.of(0.1, 0.2)
        .average().orElseThrow();
```

Trong chương trình kiểm thử, giá trị in ra là `0.15000000000000002`, không phải chuỗi thập phân `0.15` đúng tuyệt đối.

Có thêm hai giá trị đặc biệt cần quan tâm:

- **`Infinity`**: cộng những giá trị `double` hữu hạn rất lớn có thể tràn miền số thực hữu hạn và cho `Double.POSITIVE_INFINITY` (hoặc âm vô cực tương ứng).
- **`NaN`** (*not a number*): nếu đầu vào chứa `Double.NaN`, `DoubleStream.sum()` trả `NaN`; kết quả có thể trở nên vô nghĩa nếu bỏ qua việc kiểm tra đầu vào.

Ví dụ kiểm thử:

```java
System.out.println(DoubleStream.of(
        Double.MAX_VALUE, Double.MAX_VALUE).sum()); // Infinity
System.out.println(DoubleStream.of(
        1.0, Double.NaN).sum()); // NaN
```

Đây là các lệnh minh họa trong phương thức đã import `DoubleStream`.

Khi xây dựng phần tổng hợp cho báo cáo, cần xác định chính sách **đối với giá trị không hữu hạn** (`Double.isFinite(value)`, `Double.isNaN(value)`) thay vì tự động làm tròn hoặc hiển thị chúng như giá trị hợp lệ.

## 13. Khi nào nên dùng BigDecimal?

Với các phép tính thập phân cần kết quả đúng theo quy tắc thập phân (đặc biệt tiền tệ), `BigDecimal` thường phù hợp hơn `double`.

```java
BigDecimal exact = Stream.of("0.1", "0.2")
        .map(BigDecimal::new)
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(exact); // 0.3
```

Đây là đoạn minh họa nằm trong phương thức, cần import `java.math.BigDecimal`, `java.util.stream.Stream`. Việc tạo `BigDecimal` từ **chuỗi thập phân gốc** cho phép biểu diễn chính xác các giá trị `0.1`, `0.2`.

Trong chương trình đầy đủ, ta cũng dùng:

```java
BigDecimal value = DoubleStream.of(0.1, 0.2)
        .mapToObj(BigDecimal::valueOf)
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

`BigDecimal.valueOf(double)` chuyển qua biểu diễn thập phân chuẩn của `Double.toString`, nên ở **ví dụ cụ thể** này cho `0.3`. Tuy nhiên, nếu giá trị `double` đã bị làm tròn trong một phép toán trước đó, chuyển sang `BigDecimal` **không khôi phục được dữ liệu thập phân gốc đã mất**. Khi có lựa chọn, hãy đọc số tiền trực tiếp từ chuỗi, số nguyên đơn vị nhỏ nhất hoặc dữ liệu `BigDecimal` ngay từ đầu.

Tránh:

```text
new BigDecimal(0.1) // Không biểu diễn đúng "0.1" theo nghĩa thập phân
```

Đây là biểu thức cảnh báo, không phải một chương trình độc lập. Constructor này nhận **giá trị nhị phân thực tế** của `double`, có thể sinh ra một chuỗi chữ số thập phân dài. Ưu tiên `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)` khi hiểu rõ ý nghĩa chuyển đổi.

`BigDecimal` không tự biến toàn bộ nghiệp vụ thành “không có sai số”: phép **chia** có thể cho thập phân vô hạn và cần `MathContext`, `scale` hoặc `RoundingMode` phù hợp. Quy tắc làm tròn phải thuộc thiết kế nghiệp vụ.

## 14. Chương trình Java 17 hoàn chỉnh: sai số số thực

Tạo tệp `FloatingAggregatePrecisionDemo.java`:

```java
import java.math.BigDecimal;
import java.util.stream.DoubleStream;

public class FloatingAggregatePrecisionDemo {
    public static void main(String[] args) {
        System.out.println("binarySum=" + DoubleStream.of(0.1, 0.2).sum());
        System.out.println("naiveAddition=" + (0.1 + 0.2));

        double a = DoubleStream.of(1e16, 1.0, -1e16).sum();
        double b = DoubleStream.of(1e16, -1e16, 1.0).sum();
        System.out.println("orderedA=" + a);
        System.out.println("orderedB=" + b);

        System.out.println("average=" +
                DoubleStream.of(0.1, 0.2).average().orElseThrow());

        BigDecimal exact = DoubleStream.of(0.1, 0.2)
                .mapToObj(BigDecimal::valueOf)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println("bigDecimalSum=" + exact);
        System.out.println("stringDecimal=" +
                new BigDecimal("0.1").add(new BigDecimal("0.2")));

        System.out.println("positiveInfinity=" +
                DoubleStream.of(Double.MAX_VALUE, Double.MAX_VALUE).sum());
        System.out.println("containsNaN=" +
                DoubleStream.of(1.0, Double.NaN).sum());
        System.out.println("equality=" +
                (DoubleStream.of(0.1, 0.2).sum() == 0.3));
        System.out.println("closeEnough=" +
                (Math.abs(DoubleStream.of(0.1, 0.2).sum() - 0.3) <= 1e-12));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 FloatingAggregatePrecisionDemo.java
java FloatingAggregatePrecisionDemo
```

Đầu ra thực tế trên môi trường Java 17 dùng để kiểm chứng bài:

```text
binarySum=0.30000000000000004
naiveAddition=0.30000000000000004
orderedA=0.0
orderedB=1.0
average=0.15000000000000002
bigDecimalSum=0.3
stringDecimal=0.3
positiveInfinity=Infinity
containsNaN=NaN
equality=false
closeEnough=true
```

**Quan trọng:** các dòng thể hiện thứ tự cộng của `DoubleStream.sum()` được ghi lại từ JDK chạy thử; đặc tả không buộc mọi triển khai đều in đúng `orderedA=0.0`, `orderedB=1.0`. Khi dạy hoặc kiểm thử trên JDK khác, tập trung vào hợp đồng số thực và những rủi ro sai số, không khóa logic nghiệp vụ vào hai output thứ tự đó.

Ví dụ `equality=false` minh họa việc so sánh trực tiếp `double` bằng `==` có thể gây bất ngờ. `closeEnough=true` minh họa so sánh gần đúng với một dung sai phù hợp cho bài ví dụ; cách chọn dung sai thực tế sẽ được giải thích ở mục tiếp.

## 15. So sánh double bằng dung sai (tolerance)

Với tính toán khoa học hoặc dữ liệu số thực có sai số dự kiến, so sánh thường cần **dung sai tuyệt đối** hoặc **tương đối**, thay vì mặc định sử dụng `a == b`:

```java
static boolean approximatelyEqual(
        double a, double b,
        double absoluteTolerance,
        double relativeTolerance) {
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }
    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return difference <= Math.max(
            absoluteTolerance, relativeTolerance * scale);
}
```

Đây là **phương thức minh họa** để đặt trong lớp Java, không phải lời gọi độc lập. Chọn `absoluteTolerance` thích hợp gần số không, `relativeTolerance` thích hợp khi quy mô lớn. Trong ứng dụng thực cần kiểm tra hai dung sai là số hữu hạn, không âm và xem xét kỹ sự tràn của các phép tính trung gian; ví dụ đơn giản trên không phải thư viện so sánh mọi trường hợp IEEE 754.

Không nên chọn `1e-12` như một hằng số vạn năng. Cùng một sai số tuyệt đối có thể là rất lớn với dữ liệu cỡ `1e-15` nhưng không đáng kể với dữ liệu cỡ `1e9`. Hãy căn cứ yêu cầu đo lường, miền giá trị và sai số có thể chấp nhận.

Đối với **tiền tệ, số lượng hàng hóa rời rạc, số dư hay điều kiện pháp lý cần bằng nhau chính xác**, lựa chọn tốt hơn thường là mô hình dữ liệu chính xác (`long` đơn vị nhỏ nhất trong miền an toàn, `BigInteger` hoặc `BigDecimal`) thay vì “so sánh số tiền gần bằng”.

## 16. Cẩn trọng với reduce(), parallel() và thuật toán cộng

Một số cách tổng hợp tùy biến:

```java
int total = IntStream.of(1, 2, 3).reduce(0, Integer::sum);
double amount = DoubleStream.of(0.1, 0.2)
        .reduce(0.0, Double::sum);
```

Hai lệnh này đặt trong phương thức đã import `IntStream`, `DoubleStream`.

Dùng `reduce` **không tự giải quyết** tràn hoặc sai số: `Integer::sum` vẫn cộng `int` và có thể tràn; `Double::sum` vẫn làm tròn `double`. Ngoài ra, `DoubleStream.sum()` có thể sử dụng thuật toán cộng bù, nên không nên giả định `reduce(0.0, Double::sum)` luôn cho cùng độ chính xác hoặc cùng kết quả với `sum()`.

Trong parallel reduction, stream có thể kết hợp các phần tổng ở một cấu trúc khác. Phép cộng dấu phẩy động **không kết hợp chính xác về mặt biểu diễn**; vì vậy các chữ số thấp của kết quả có thể thay đổi. Với `Math.addExact`, cách nhóm khác có thể làm xuất hiện overflow tại các bước khác, kể cả khi tổng toán học cuối vẫn biểu diễn được.

Khi cần tổng hợp số nguyên **chính xác dù thứ tự nhóm thay đổi**, `BigInteger::add` là một phép toán phù hợp với ý nghĩa toán học. Khi cần kết quả thập phân chính xác, `BigDecimal::add` thường phù hợp nếu các toán hạng được tạo chính xác và không bị làm tròn trước đó.

## 17. Lựa chọn kỹ thuật theo yêu cầu

| Yêu cầu | Cách thường phù hợp | Điều cần kiểm tra |
| --- | --- | --- |
| Tổng `int` chắc chắn vừa `int` | `IntStream.sum()` | Biết rõ giới hạn số phần tử và giá trị |
| Tổng `int` có thể vượt `int`, chắc chắn vừa `long` | `asLongStream().sum()` | Mở rộng **trước** khi sum |
| Tổng `long` chắc chắn vừa `long` | `LongStream.sum()` | Giới hạn tổng, không chỉ giới hạn phần tử |
| Muốn lỗi rõ khi phép cộng tràn | `reduce(0, Math::addExact)` | Có thể ném lỗi ở tổng trung gian |
| Tổng nguyên vượt `long`, yêu cầu chính xác | `BigInteger` + `reduce(BigInteger.ZERO, BigInteger::add)` | Chi phí cấp phát, độ lớn dữ liệu |
| Tổng `double` dùng cho tính toán có sai số chấp nhận | `DoubleStream.sum()` | Kiểm soát NaN/Infinity, dung sai, thứ tự |
| Tổng số tiền thập phân chính xác | `BigDecimal` từ dữ liệu thập phân chuẩn | Scale, rounding, nhập liệu |
| Cần trung bình khi stream có thể rỗng | `average()` + xử lý `OptionalDouble` | Không gọi `getAsDouble` khi không có giá trị |
| Cần thống kê `IntStream` | `summaryStatistics()` | `getSum()` là long, vẫn hữu hạn |
| Cần kết quả có thể tái lập nghiêm ngặt | Định nghĩa thuật toán, thứ tự và kiểu số | Không dựa vào thứ tự reduction ngẫu nhiên |

Cách chọn trước khi lập trình: xác định **miền giá trị từng phần tử**, **giới hạn số phần tử**, **giới hạn tổng toán học**, yêu cầu **sai số/độ chính xác**, và việc pipeline có chạy **song song** hay không.

## 18. Lỗi thường gặp và cách sửa

| Lỗi / hiểu nhầm | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Gán `IntStream.sum()` vào `long` để tránh tràn | Tràn xảy ra **trước** phép gán | `asLongStream()` hoặc `mapToLong()` trước `sum()` |
| Cho rằng `LongStream.sum()` không bao giờ tràn | `long` chỉ có 64 bit | Dùng `BigInteger` nếu vượt miền |
| Dùng `Integer::sum` trong `reduce` để “kiểm tra” overflow | `Integer::sum` không báo tràn | `Math.addExact` khi muốn fail-fast |
| Nghĩ `Math.addExact` chỉ kiểm tra tổng cuối | Nó kiểm tra **mỗi phép cộng thực hiện** | Dùng `BigInteger` nếu cần tổng cuối chính xác bất kể nhóm |
| Chuyển `long` lớn sang `double` để giữ tổng | `double` không biểu diễn mọi số nguyên lớn | `BigInteger` khi cần số nguyên chính xác |
| Cho rằng `0.1 + 0.2 == 0.3` luôn đúng | Biểu diễn nhị phân của số thập phân có sai số | Dùng tolerance phù hợp hoặc `BigDecimal` |
| Cho rằng `DoubleStream.sum()` luôn có cùng kết quả ở mọi thứ tự | Cộng số thực làm tròn và không kết hợp tuyệt đối | Thiết kế thuật toán/kiểu số theo yêu cầu |
| `new BigDecimal(0.1)` luôn bằng thập phân `0.1` | Constructor nhận số `double` nhị phân thực tế | `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)` |
| Chuyển dữ liệu `double` đã tính sang `BigDecimal` để khôi phục chính xác | Sai số từ trước không thể phục hồi | Đọc/lưu dữ liệu chính xác ngay từ đầu |
| Dùng `average().orElseThrow()` trên stream rỗng | `OptionalDouble` rỗng | Dùng `isPresent()`, `orElse(...)` hoặc chính sách phù hợp |
| Bỏ qua `NaN`/`Infinity` trong báo cáo | Có thể đưa ra kết quả vô nghĩa/không hữu hạn | Xác định chính sách kiểm tra và xử lý |
| Dùng tolerance bất kỳ cho số tiền | Có thể chấp nhận sai lệch nghiệp vụ không cho phép | Mô hình giá trị thập phân chính xác |

## 19. Bài tập tự kiểm tra (có đáp án)

**Bài 1 — Tràn int.** Kết quả của `IntStream.of(Integer.MAX_VALUE, 1).sum()` là gì? `long n = ...sum()` có sửa được không?

Đáp án: kết quả kiểu `int` là `-2147483648`. Gán vào `long` **không sửa được**, vì tràn xảy ra trước. Phải chuyển từng phần tử sang `long` trước khi cộng.

**Bài 2 — LongStream.** `IntStream.of(Integer.MAX_VALUE, 1).asLongStream().sum()` cho bao nhiêu?

Đáp án: `2147483648`, vì hai phần tử được mở rộng thành `long` trước khi cộng.

**Bài 3 — Long tràn.** Tổng toán học của `Long.MAX_VALUE + 1` là bao nhiêu và nên dùng kiểu gì để biểu diễn chính xác?

Đáp án: `9223372036854775808`, vượt `long`. Dùng `BigInteger`, ví dụ map `BigInteger::valueOf` rồi `reduce(BigInteger.ZERO, BigInteger::add)`.

**Bài 4 — Kiểm tra tràn.** `IntStream.of(Integer.MAX_VALUE,1,-1).reduce(0,Math::addExact)` có thể ném `ArithmeticException` mặc dù tổng toán học cuối là `Integer.MAX_VALUE` không?

Đáp án: **Có**. Thứ tự cộng tuần tự gặp `MAX+1` trước, vượt miền `int`; `Math.addExact` báo tràn ở phép cộng trung gian.

**Bài 5 — Sai số thập phân.** Vì sao `DoubleStream.of(0.1,0.2).sum() == 0.3` có thể là `false`?

Đáp án: `double` dùng biểu diễn nhị phân làm tròn, nên tổng có thể là `0.30000000000000004`. Hãy dùng `BigDecimal` cho giá trị thập phân chính xác hoặc so sánh có dung sai nếu bài toán chấp nhận sai số.

**Bài 6 — Thứ tự.** Tại sao `DoubleStream.of(1e16,1,-1e16).sum()` có thể khác `DoubleStream.of(1e16,-1e16,1).sum()`?

Đáp án: phép cộng double làm tròn từng bước; khi cộng số rất lớn với số rất nhỏ, phần nhỏ có thể bị mất. Cách nhóm/thứ tự và thuật toán tổng hợp ảnh hưởng sai số; JDK không hứa cố định một cách cộng cho mọi triển khai.

**Bài 7 — BigDecimal.** Nêu cách tạo hai số thập phân `0.1`, `0.2` để tổng là `0.3` chính xác.

Đáp án: `new BigDecimal("0.1").add(new BigDecimal("0.2"))`, hoặc đọc hai chuỗi rồi `Stream.of(...).map(BigDecimal::new).reduce(...)`. Tránh dựa vào số `double` đã mất thông tin.

**Bài 8 — Average.** Vì sao không nên thay `IntStream.average()` bằng `(double) intStream.sum()/count` khi các giá trị lớn?

Đáp án: `IntStream.sum()` có thể tràn kiểu `int` **trước khi** đổi sang `double`. Phải chọn thuật toán/trung gian phù hợp; `average()` là API chuyên dụng và vẫn cần lưu ý `OptionalDouble` cùng độ chính xác.

**Bài 9 — Tính hữu hạn.** `DoubleStream.of(Double.MAX_VALUE, Double.MAX_VALUE).sum()` có thể trả gì?

Đáp án: `Infinity`, dù từng phần tử đầu vào hữu hạn, vì tổng vượt miền biểu diễn hữu hạn. Nên kiểm tra bằng `Double.isFinite(result)` nếu nghiệp vụ không chấp nhận vô cực.

## 20. Checklist trước khi đưa phép tổng hợp vào sản xuất

1. **Xác định nguồn:** `IntStream`, `LongStream`, `DoubleStream`, hay dữ liệu thập phân chính xác?
2. **Xác định miền tổng:** không chỉ từng phần tử, mà cả `count × max magnitude` và những bước cộng trung gian có thể vượt miền không?
3. **Chọn cách xử lý tràn:** mở rộng kiểu trước `sum()`, `Math.addExact` báo lỗi, hay `BigInteger` để chính xác không giới hạn kiểu nguyên thủy?
4. **Xác định yêu cầu số thực:** sai số bao nhiêu được chấp nhận, có cần kết quả cố định, dữ liệu có nguồn gốc thập phân chính xác không?
5. **Kiểm tra giá trị đặc biệt:** stream rỗng, `NaN`, `Infinity`, số âm, số rất lớn và số rất nhỏ trộn nhau.
6. **Thử test biên:** `Integer.MAX_VALUE + 1`, `Long.MAX_VALUE + 1`, `0.1 + 0.2`, `1e16 + 1 - 1e16`.
7. **Kiểm thử mode song song nếu dùng:** tránh phụ thuộc chữ số thấp của `double` hoặc các side effects của phép reduction.
8. **Ghi rõ policy nghiệp vụ:** fail-fast, giới hạn giá trị, làm tròn theo quy tắc, hay tính chính xác bằng kiểu dữ liệu khác.

## 21. Ghi nhớ

- `IntStream.sum()` trả `int` và **có thể tràn không báo lỗi**; `LongStream.sum()` tương tự với `long`.
- **Mở rộng kiểu trước khi cộng**: `asLongStream().sum()`, không phải `(long) intStream.sum()`.
- Dùng `Math.addExact` khi muốn kiểm tra tràn **ở từng phép cộng thực hiện**, dùng `BigInteger` khi cần tổng nguyên chính xác không giới hạn theo primitive.
- `IntSummaryStatistics.getSum()` dùng `long`; `average()` trả `OptionalDouble`. Không xem mọi API thống kê là bản sao của `IntStream.sum()`.
- `DoubleStream.sum()` chịu **sai số làm tròn**, có thể khác theo thứ tự/cách nhóm và không bảo đảm kết quả thập phân chính xác; các giá trị đặc biệt `NaN`, `Infinity` cũng cần được xét.
- **Tiền tệ, dữ liệu thập phân cần đúng tuyệt đối**: ưu tiên `BigDecimal` được tạo từ dữ liệu chính xác; đừng kỳ vọng chuyển từ `double` đã sai sang `BigDecimal` là phục hồi được dữ liệu gốc.
- Chọn kiểu số và chính sách sai số theo **yêu cầu nghiệp vụ**, không chỉ theo cú pháp Stream dễ viết.

Tham khảo chính thống: [Java 17 IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html), [LongStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/LongStream.html), [DoubleStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/DoubleStream.html), [Math.addExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(int,int)), [BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html), [BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).
