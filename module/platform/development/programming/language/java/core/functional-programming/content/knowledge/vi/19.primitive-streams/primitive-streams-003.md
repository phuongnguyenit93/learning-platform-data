# sum(), average(), min(), max() và summaryStatistics() trên primitive stream Java

## 1. Mục tiêu bài học

Java có ba kiểu **primitive stream** chuyên cho dữ liệu số nguyên thủy:

- **IntStream** xử lý `int`.
- **LongStream** xử lý `long`.
- **DoubleStream** xử lý `double`.

Trong module functional programming, các luồng này thường được tạo bằng `IntStream.of(...)`, `LongStream.range(...)`, `DoubleStream.of(...)`, hoặc chuyển từ `Stream<T>` thông qua `mapToInt`, `mapToLong`, `mapToDouble`. Chúng tránh việc phải đóng hộp từng giá trị số thành **Integer/Long/Double** ở các bước xử lý tương ứng.

Nhóm phương thức quan trọng để **tổng hợp dữ liệu (aggregation)**:

| Terminal operation | Mục đích | Kết quả cơ bản |
| --- | --- | --- |
| **sum()** | Cộng các phần tử | `int`, `long` hoặc `double` tương ứng loại stream |
| **average()** | Trung bình cộng | `OptionalDouble` |
| **min()** | Giá trị nhỏ nhất | `OptionalInt`, `OptionalLong`, `OptionalDouble` |
| **max()** | Giá trị lớn nhất | `OptionalInt`, `OptionalLong`, `OptionalDouble` |
| **summaryStatistics()** | Gộp count, sum, min, max, average | `IntSummaryStatistics`, `LongSummaryStatistics` hoặc `DoubleSummaryStatistics` |

Tất cả đều là **terminal operation**: khi một trong các phương thức này tiêu thụ stream, stream đó không thể được tái sử dụng. Điểm này ảnh hưởng cách viết code khi cùng lúc cần tổng, trung bình, min và max.

Ví dụ:

~~~java
int total = IntStream.of(2, 4, 6).sum();           // 12
OptionalDouble average = IntStream.of(2, 4, 6).average();
OptionalInt minimum = IntStream.of(2, 4, 6).min();
OptionalInt maximum = IntStream.of(2, 4, 6).max();
~~~

Đây là các đoạn minh họa cần import `java.util.stream.IntStream`, `java.util.OptionalDouble` và `java.util.OptionalInt`. Chúng tạo **bốn stream mới** riêng biệt, không tái sử dụng một stream đã tiêu thụ.

**Tư duy chính:** Chọn phương thức dựa trên kết quả cần tính và ý nghĩa của dữ liệu rỗng; nếu cần nhiều chỉ số cùng một lúc, `summaryStatistics()` thường gọn hơn việc duyệt nguồn lặp lại.

## 2. Các primitive stream được tạo như thế nào?

### 2.1. Tạo trực tiếp từ giá trị

~~~java
IntStream integers = IntStream.of(3, 6, 9);
LongStream longs = LongStream.of(100L, 200L, 300L);
DoubleStream decimals = DoubleStream.of(1.5, 2.0, 4.5);
~~~

Đây là đoạn minh họa cần import ba interface tương ứng từ `java.util.stream`. Các biến là stream có thể tiêu thụ một lần; chưa có terminal operation nên chưa có kết quả tổng hợp.

### 2.2. Sinh dãy số bằng range và rangeClosed

~~~java
IntStream firstFive = IntStream.range(1, 6);       // 1, 2, 3, 4, 5
LongStream inclusive = LongStream.rangeClosed(1, 5); // 1, 2, 3, 4, 5
~~~

- **range(start, endExclusive)** không chứa endExclusive.
- **rangeClosed(start, endInclusive)** có chứa endInclusive nếu khoảng hợp lệ.

Dùng `range(1,6).sum()` cho tổng 1+2+3+4+5 = 15. Với một dãy rất lớn, nên xét giới hạn số, hiệu năng và nguy cơ tràn số trước khi chỉ định kiểu dữ liệu.

### 2.3. Chuyển từ object stream

Ví dụ một record sản phẩm:

~~~java
record Item(String name, int quantity, long priceCents) {}
~~~

Nếu có `List<Item> items`:

~~~java
int totalQuantity = items.stream()
        .mapToInt(Item::quantity)
        .sum();

long totalPrices = items.stream()
        .mapToLong(Item::priceCents)
        .sum();
~~~

Đây là đoạn minh họa, giả định `items` đã có và các giá trị phù hợp mô hình. **mapToInt** và **mapToLong** tạo primitive streams để dùng các phương thức tổng hợp, thay vì `map(Item::quantity)` tạo Stream<Integer> rồi phải reduce/collect.

Nếu thuộc tính `Integer quantity` hoặc `Long priceCents` có thể **null**, phép unboxing trong `mapToInt`/ `mapToLong` có thể ném NullPointerException. Khi đó cần kiểm tra null và chính sách dữ liệu thiếu trước khi chuyển sang primitive.

## 3. sum(): trả số trực tiếp và hành vi với stream rỗng

**sum()** trả về một giá trị primitive:

~~~java
int intSum = IntStream.of(1, 2, 3).sum();           // 6
long longSum = LongStream.of(10L, 20L, 30L).sum(); // 60
double doubleSum = DoubleStream.of(1.5, 2.5).sum();// 4.0
~~~

Đây là đoạn minh họa cần các import primitive stream.

Không giống min/max/average, `sum()` **không** trả Optional. Với **stream rỗng**, `sum()` trả **0** đúng kiểu tương ứng:

~~~java
int noneInt = IntStream.empty().sum();       // 0
long noneLong = LongStream.empty().sum();    // 0L
double noneDouble = DoubleStream.empty().sum(); // 0.0
~~~

**Vì sao có giá trị 0?** Về mặt phép cộng, 0 là **giá trị trung hòa**. Cộng không phần tử có thể định nghĩa bằng 0, nên API trả số trực tiếp.

Cần phân biệt:

- **Không có phần tử** → `sum()` trả 0.
- **Có phần tử nhưng tổng bằng 0** → `sum()` cũng trả 0.

Nếu nghiệp vụ cần phân biệt hai trường hợp này, chỉ dùng `sum()` là **không đủ**. Có thể dùng `summaryStatistics()` và xem `getCount()`, hoặc thiết kế kết quả trả về có ngữ nghĩa “không có dữ liệu”.

### 3.1. Tràn số với IntStream.sum

`IntStream.sum()` trả về **int**, có thể tràn số theo phép cộng int. Ví dụ:

~~~java
int overflowed = IntStream.of(Integer.MAX_VALUE, 1).sum();
// Kết quả theo phép cộng int: Integer.MIN_VALUE.
~~~

Đây là đoạn minh họa. Việc dùng primitive stream không tự kiểm tra overflow. Với giá trị có khả năng vượt phạm vi int, có thể **nâng lên long trước khi cộng**:

~~~java
long safeIntTotal = IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum();  // 2147483648L
~~~

Lưu ý long cũng có giới hạn và `LongStream.sum()` cũng có thể tràn nếu vượt phạm vi long. Với số lớn hơn long, cân nhắc **BigInteger**, với tiền tệ/độ chính xác thập phân cân nhắc **BigDecimal** hoặc mô hình minor units phù hợp.

### 3.2. DoubleStream.sum và sai số dấu phẩy động

`DoubleStream.sum()` trả **double**. Phép cộng dấu phẩy động **không hoàn toàn kết hợp** do làm tròn theo biểu diễn IEEE 754; kết quả có thể thay đổi đôi chút khi thay đổi cách nhóm, thứ tự cộng hoặc song song hóa. Tính toán còn có thể gặp **NaN**, vô cực hoặc mất độ chính xác khi các độ lớn chênh nhau đáng kể.

Ví dụ:

~~~java
double sum = DoubleStream.of(0.1, 0.2).sum();
~~~

Đây là đoạn minh họa. Không nên buộc kết quả theo quy tắc “mọi phép cộng decimal đều chính xác tuyệt đối”; `0.1` và `0.2` không được biểu diễn chính xác bằng double nhị phân.

**Không dùng DoubleStream.sum cho bài toán kế toán đòi hỏi số thập phân chính xác** mà chưa có chính sách xử lý sai số. Dùng BigDecimal với dữ liệu đầu vào và quy tắc rounding đúng yêu cầu nghiệp vụ.

## 4. average(): luôn trả OptionalDouble

Trung bình cộng bằng **tổng / số phần tử**. Với stream rỗng, không có số phần tử làm mẫu số, nên không có một giá trị trung bình hợp lệ.

Vì vậy:

~~~java
OptionalDouble a = IntStream.of(2, 4, 6).average();
OptionalDouble b = LongStream.of(10L, 20L).average();
OptionalDouble c = DoubleStream.of(1.0, 2.0).average();
~~~

Tất cả trả **OptionalDouble** (không phải OptionalInt, OptionalLong, hay double trực tiếp). Đây là đoạn minh họa với các import tương ứng.

- `a.orElse(-1)` cho **4.0**.
- `b.orElse(-1)` cho **15.0**.
- `c.orElse(-1)` cho **1.5**.
- `IntStream.empty().average().isEmpty()` cho **true**.

Tại sao không trả int với IntStream? Trung bình của các số int có thể là số phân số. Ví dụ 1 và 2 có trung bình là **1.5**, nên dùng `OptionalDouble` phù hợp.

Nếu nghiệp vụ bắt buộc có ít nhất một giá trị, hãy định nghĩa cách xử lý vắng mặt:

~~~java
double average = scores.stream()
        .mapToInt(Integer::intValue)
        .average()
        .orElseThrow(() -> new IllegalStateException("No scores"));
~~~

Đây là đoạn minh họa, giả định scores là List<Integer> không chứa null. **orElseThrow** biến sự vắng mặt thành exception có chủ đích. Nếu empty là tình huống hợp lệ, `orElse(0.0)` hoặc trả OptionalDouble cho caller có thể phù hợp hơn, nhưng cần nói rõ **0.0 khi rỗng là fallback nghiệp vụ**, không phải trung bình toán học của tập rỗng.

### 4.1. Sự khác nhau giữa trung bình và tổng số nguyên

Với `IntStream`, `average()` tính trung bình mà không cần người viết thực hiện phép chia **int/int** (gây chia nguyên). Tránh:

~~~java
int sum = 5;
int count = 2;
double wrong = sum / count; // 2.0, vì phép chia nguyên diễn ra trước.
~~~

Đây là đoạn minh họa; `sum / count` cho int 2, rồi mới chuyển thành double 2.0. Nếu tính thủ công, cần ép sang double trước khi chia:

~~~java
double correct = (double) sum / count; // 2.5
~~~

**average()** giúp diễn đạt ý định rõ hơn, nhưng vẫn phải xử lý trường hợp stream rỗng bằng OptionalDouble.

### 4.2. Sai số của average trên dữ liệu lớn

`IntStream.average()` hoặc `LongStream.average()` trả double: các giá trị long lớn có thể không được biểu diễn chính xác mọi đơn vị nhỏ nhất trong double. `DoubleStream.average()` cũng chịu giới hạn floating-point, nhất là khi có giá trị rất lớn, rất nhỏ hoặc vô cực. Nếu cần trung bình chính xác đến đơn vị thập phân quy định, có thể phải dùng BigDecimal hoặc thuật toán chuyên biệt kèm chính sách làm tròn.

## 5. min() và max(): Optional theo từng loại primitive

Các giá trị nhỏ nhất/lớn nhất **không tồn tại với stream rỗng** nếu không định nghĩa một giá trị sentinel ngoài dữ liệu, nên các phương thức trả Optional:

| Stream | min() | max() |
| --- | --- | --- |
| **IntStream** | **OptionalInt** | **OptionalInt** |
| **LongStream** | **OptionalLong** | **OptionalLong** |
| **DoubleStream** | **OptionalDouble** | **OptionalDouble** |

Ví dụ:

~~~java
OptionalInt smallest = IntStream.of(9, 3, 7).min();  // chứa 3
OptionalLong greatest = LongStream.of(4L, 10L).max(); // chứa 10
OptionalDouble maxDouble = DoubleStream.of(1.5, 3.2).max(); // chứa 3.2
~~~

Đây là đoạn minh họa cần import các Optional primitive và primitive streams.

### 5.1. Khi stream rỗng

~~~java
OptionalInt emptyMin = IntStream.empty().min();
OptionalLong emptyMax = LongStream.empty().max();
OptionalDouble emptyAvg = DoubleStream.empty().average();
~~~

Cả ba Optional đều **rỗng**. `isPresent()` trả false; `isEmpty()` trả true (phương thức isEmpty có từ Java 11 trên Optional primitive).

Nếu gọi **getAsInt()**, **getAsLong()** hoặc **getAsDouble()** trên Optional rỗng, Java ném **NoSuchElementException**. Vì thế, dùng `orElse`, `orElseGet` (nếu API cụ thể hỗ trợ), `orElseThrow` hoặc kiểm tra sự hiện diện theo nhu cầu.

Ví dụ:

~~~java
int min = IntStream.of(5, 7).min().orElse(-1); // 5
int fallback = IntStream.empty().min().orElse(-1); // -1
~~~

**Cẩn trọng với sentinel:** nếu -1 cũng có thể xuất hiện trong dữ liệu, nó không giúp phân biệt “không có phần tử”. Tốt hơn là giữ OptionalInt nếu caller cần biết sự vắng mặt.

### 5.2. Số âm và lựa chọn identity sai

Không nên thay thế tùy tiện:

~~~java
int wrongMax = IntStream.of(-7, -3, -9)
        .reduce(0, Integer::max); // 0 (sai ý nghĩa max dữ liệu)
~~~

Ở đây 0 **không phải identity cho phép max trên miền mọi int**, vì max(0, x) không bằng x khi x âm. Nếu dùng **max()**, kết quả đúng là -3, đồng thời có OptionalInt xử lý stream rỗng.

**Cách tốt:** `IntStream.of(-7,-3,-9).max().orElseThrow()` trả -3. Tương tự, `min()` giúp tránh tự tạo sentinel không phù hợp với miền dữ liệu.

### 5.3. DoubleStream.min/max và NaN

Với số thực double, **NaN** (Not a Number) có quy tắc đặc biệt. `DoubleStream.min()` và `max()` tuân theo ngữ nghĩa `Math.min`/`Math.max`: nếu có một phần tử **NaN**, kết quả của phép giảm tương ứng là **NaN**. Khi tồn tại **-0.0** và **+0.0**, so sánh min/max cũng phân biệt dấu zero theo quy tắc của các phương thức này.

Không dùng `filter(Double::isFinite)` một cách máy móc: bỏ NaN/vô cực sẽ thay đổi dữ liệu. Hãy xác định xem NaN là dữ liệu không hợp lệ cần báo, giá trị cần loại theo chính sách, hay thuộc miền phép tính có ý nghĩa cụ thể.

## 6. Ví dụ Java 17 đầy đủ: năm phép tổng hợp cơ bản

Tạo tệp **PrimitiveAggregatesDemo.java**:

~~~java
import java.util.IntSummaryStatistics;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.stream.IntStream;

public class PrimitiveAggregatesDemo {
    public static void main(String[] args) {
        int[] values = {8, 3, 5, 4};

        int sum = IntStream.of(values).sum();
        OptionalDouble average = IntStream.of(values).average();
        OptionalInt min = IntStream.of(values).min();
        OptionalInt max = IntStream.of(values).max();
        IntSummaryStatistics stats =
                IntStream.of(values).summaryStatistics();

        System.out.println("sum=" + sum);
        System.out.println("average=" + average.orElse(-1));
        System.out.println("min=" + min.orElse(-1));
        System.out.println("max=" + max.orElse(-1));

        System.out.println("count=" + stats.getCount());
        System.out.println("stats sum=" + stats.getSum());
        System.out.println("stats min=" + stats.getMin());
        System.out.println("stats max=" + stats.getMax());
        System.out.println("stats average=" + stats.getAverage());

        System.out.println("empty sum=" + IntStream.empty().sum());
        System.out.println("empty average present="
                + IntStream.empty().average().isPresent());
        System.out.println("empty min present="
                + IntStream.empty().min().isPresent());
    }
}
~~~

Biên dịch/chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 PrimitiveAggregatesDemo.java
java PrimitiveAggregatesDemo
~~~

Stdout:

~~~text
sum=20
average=5.0
min=3
max=8
count=4
stats sum=20
stats min=3
stats max=8
stats average=5.0
empty sum=0
empty average present=false
empty min present=false
~~~

**Giải thích kết quả:**

1. Bốn số **8,3,5,4** có tổng **20**, trung bình **20/4 = 5.0**.
2. Giá trị nhỏ nhất **3**, lớn nhất **8**.
3. `IntSummaryStatistics` cung cấp cả bốn chỉ số và **count=4** sau một lần xử lý stream do summaryStatistics thực hiện.
4. `IntStream.empty().sum()` trả 0; `average()` và `min()` trả Optional rỗng.
5. Những phép tính riêng ở phần đầu dùng **các stream mới** tạo từ `int[] values`; không có việc dùng lại một Stream sau terminal operation.

**Ghi nhớ:** Ví dụ minh họa tổng hợp trên cùng một mảng nhỏ. Trong pipeline có I/O, phép lọc tốn kém hoặc nguồn chỉ có thể duyệt một lần, việc tạo bốn stream độc lập để tính bốn chỉ số có thể không khả thi hoặc không hiệu quả. `summaryStatistics()` giúp tránh lặp lại nguồn.

## 7. summaryStatistics(): một lần duyệt để có nhiều chỉ số

Các phương thức tương ứng:

~~~java
IntSummaryStatistics ints = IntStream.of(1, 3, 5).summaryStatistics();
LongSummaryStatistics longs = LongStream.of(10, 20).summaryStatistics();
DoubleSummaryStatistics doubles = DoubleStream.of(1.0, 2.5).summaryStatistics();
~~~

Đây là đoạn minh họa cần import **java.util.IntSummaryStatistics**, **LongSummaryStatistics**, **DoubleSummaryStatistics**, và các primitive stream.

Mỗi đối tượng statistics cung cấp những getter:

- **getCount()** → số phần tử được nhận, kiểu **long**.
- **getSum()** → tổng, kiểu tùy statistics.
- **getMin()** → min, kiểu primitive tương ứng.
- **getMax()** → max, kiểu primitive tương ứng.
- **getAverage()** → trung bình, kiểu **double**.

| Getter | IntSummaryStatistics | LongSummaryStatistics | DoubleSummaryStatistics |
| --- | --- | --- | --- |
| getCount() | long | long | long |
| getSum() | **long** | long | double |
| getMin() | int | long | double |
| getMax() | int | long | double |
| getAverage() | double | double | double |

**Điểm dễ nhầm quan trọng:** `IntStream.sum()` trả **int**, còn **IntSummaryStatistics.getSum() trả long**. Vì vậy, `IntSummaryStatistics` có thể giữ tổng lớn hơn miền int trong những trường hợp mà `IntStream.sum()` sẽ tràn int. Nhưng **long vẫn có giới hạn**, và `LongSummaryStatistics.getSum()` vẫn có thể overflow long.

### 7.1. Mục đích của statistics object

Trong ví dụ xử lý điểm kiểm tra:

~~~java
IntSummaryStatistics stats = scores.stream()
        .mapToInt(Integer::intValue)
        .summaryStatistics();
~~~

Đây là đoạn minh họa giả định scores là List<Integer> không null. Thay vì:

~~~java
long count = scores.size();
int sum = scores.stream().mapToInt(Integer::intValue).sum();
int min = scores.stream().mapToInt(Integer::intValue).min()
        .orElseThrow();
int max = scores.stream().mapToInt(Integer::intValue).max()
        .orElseThrow();
double average = scores.stream().mapToInt(Integer::intValue).average()
        .orElseThrow();
~~~

ta có thể lấy tất cả số liệu từ một kết quả thống kê. Đoạn minh họa thứ hai duyệt stream nhiều lần và dùng `orElseThrow()` nên không xử lý danh sách rỗng theo dạng có fallback. Đừng coi hai đoạn có cùng mọi semantics: `IntSummaryStatistics.getSum()` là long, và getter min/max có giá trị đặc biệt khi rỗng.

### 7.2. Khi stream rỗng, statistics object vẫn tồn tại

Khác với `min()`/`average()`, `summaryStatistics()` trả một object thống kê **kể cả khi stream rỗng**. Trạng thái ban đầu của các đối tượng:

| Statistics của nguồn rỗng | count | sum | min | max | average |
| --- | ---: | ---: | --- | --- | ---: |
| IntSummaryStatistics | 0 | 0L | Integer.MAX_VALUE | Integer.MIN_VALUE | 0.0 |
| LongSummaryStatistics | 0 | 0L | Long.MAX_VALUE | Long.MIN_VALUE | 0.0 |
| DoubleSummaryStatistics | 0 | 0.0 | Double.POSITIVE_INFINITY | Double.NEGATIVE_INFINITY | 0.0 |

**Đây là các giá trị khởi tạo/sentinel**, không phải “min/max thật của tập rỗng”. Vì vậy, luôn **kiểm tra getCount() > 0** trước khi trình bày min/max/average như kết quả thống kê của tập dữ liệu.

~~~java
IntSummaryStatistics stats = IntStream.empty().summaryStatistics();
if (stats.getCount() == 0L) {
    System.out.println("No data");
} else {
    System.out.println(stats.getMin());
}
~~~

Đây là đoạn minh họa, với import IntSummaryStatistics và IntStream. Với đầu vào rỗng, chương trình in **No data**.

**Phân biệt API:**

- **`stream.min()`** trả Optional rỗng khi không có phần tử.
- **`stream.summaryStatistics().getMin()`** trả sentinel khi không có phần tử.
- **`stats.getCount()`** là cách để biết các getter min/max có ý nghĩa trên dữ liệu thực hay chưa.

### 7.3. DoubleSummaryStatistics và số không hữu hạn

Với DoubleSummaryStatistics, nếu có phần tử **NaN**, min/max và sum/average có thể trở thành NaN theo các quy tắc của phép tính. Nếu có vô cực dương hoặc âm, các phép cộng và trung bình có thể cho Infinity hoặc NaN tùy dãy số.

Không nên trình bày mọi giá trị getSum/getAverage của DoubleSummaryStatistics như tiền tệ chính xác; chúng vẫn mang ngữ nghĩa floating-point. Với dữ liệu không hữu hạn, quy định từ trước chính sách: loại, báo lỗi, hay chấp nhận theo miền dữ liệu.

## 8. Ví dụ Java 17 hoàn chỉnh: thống kê điểm theo tập dữ liệu

Tạo tệp **SummaryStatisticsDemo.java**:

~~~java
import java.util.IntSummaryStatistics;
import java.util.List;

record Exam(String student, int score) {}

public class SummaryStatisticsDemo {
    public static void main(String[] args) {
        List<Exam> exams = List.of(
                new Exam("An", 75),
                new Exam("Bình", 92),
                new Exam("Chi", 83),
                new Exam("Dung", 90)
        );

        IntSummaryStatistics stats = exams.stream()
                .mapToInt(Exam::score)
                .summaryStatistics();

        System.out.println("Count: " + stats.getCount());
        System.out.println("Sum: " + stats.getSum());
        System.out.println("Min: " + stats.getMin());
        System.out.println("Max: " + stats.getMax());
        System.out.println("Average: " + stats.getAverage());

        List<Exam> empty = List.of();
        IntSummaryStatistics noScores = empty.stream()
                .mapToInt(Exam::score)
                .summaryStatistics();

        System.out.println("Has scores: "
                + (noScores.getCount() > 0));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SummaryStatisticsDemo.java
java SummaryStatisticsDemo
~~~

Stdout:

~~~text
Count: 4
Sum: 340
Min: 75
Max: 92
Average: 85.0
Has scores: false
~~~

**Giải thích:**

- Điểm **75 + 92 + 83 + 90 = 340**, chia 4 được **85.0**.
- Min **75**, max **92**, count **4**.
- Với danh sách rỗng, **summaryStatistics()** vẫn trả IntSummaryStatistics; count bằng 0 nên **Has scores: false**.
- Nếu một danh sách `List<Exam>` có **phần tử null**, `Exam::score` sẽ gây NPE; cần kiểm tra nguồn hoặc lọc `Objects::nonNull` khi chính sách cho phép bỏ qua.
- Nếu điểm số phải nằm trong khoảng 0..100, cần **validation** riêng. Statistics chỉ tổng hợp số, không kiểm chứng dữ liệu đúng quy tắc.

### 8.1. Kết quả có count = 0 nên biểu diễn ra sao?

Thay vì hiển thị `Min: 2147483647` hoặc `Max: -2147483648` với tập rỗng, hãy thể hiện thông báo “chưa có dữ liệu”. Trong API, có thể trả một **record có count và các Optional** hoặc chuyển tình trạng empty thành một kết quả nghiệp vụ phù hợp. Không tự nhầm sentinel nội bộ với số đo.

## 9. IntSummaryStatistics có getSum kiểu long: ví dụ vượt giới hạn int

Tạo tệp **IntSumWidthDemo.java**:

~~~java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

public class IntSumWidthDemo {
    public static void main(String[] args) {
        int[] values = {Integer.MAX_VALUE, 1};

        int intSum = IntStream.of(values).sum();
        long statsSum = IntStream.of(values)
                .summaryStatistics().getSum();
        long widenedSum = IntStream.of(values)
                .asLongStream().sum();

        System.out.println("int sum: " + intSum);
        System.out.println("statistics sum: " + statsSum);
        System.out.println("long sum: " + widenedSum);
    }
}
~~~

Chạy:

~~~bash
javac IntSumWidthDemo.java
java IntSumWidthDemo
~~~

Stdout:

~~~text
int sum: -2147483648
statistics sum: 2147483648
long sum: 2147483648
~~~

**Vì sao ba dòng khác nhau?**

1. **IntStream.sum** trả int, nên `Integer.MAX_VALUE + 1` vượt 32-bit signed và wrap sang `Integer.MIN_VALUE`.
2. **IntSummaryStatistics.getSum** có kiểu long, giữ được 2147483648.
3. **IntStream.asLongStream().sum()** chuyển các phần tử int thành long trước khi tính tổng, cũng giữ được 2147483648.
4. Ví dụ này chỉ minh họa **độ rộng kiểu số**. Với số liệu vượt long, cả hai cách dùng long cũng không đủ an toàn.

**Không dùng `Math.addExact` ở vị trí không được áp dụng cho phép cộng nội bộ** rồi kỳ vọng API sum tự ném exception khi tràn. Muốn kiểm soát overflow, cần thiết kế phép cộng có kiểm tra, ví dụ reduce với `Math::addExact` cho miền phù hợp, hoặc loại số đủ rộng.

## 10. LongStream và DoubleStream: cùng API, khác miền dữ liệu

### 10.1. LongStream

~~~java
LongSummaryStatistics stats = LongStream.of(
        100_000_000_000L,
        200_000_000_000L,
        300_000_000_000L
).summaryStatistics();
~~~

Đây là đoạn minh họa cần import LongSummaryStatistics và LongStream. `getCount()` = 3, `getSum()` = 600000000000L, `getMin()` = 100000000000L, `getMax()` = 300000000000L, `getAverage()` = 200000000000.0 trong miền giá trị này.

**Chú ý:** `LongStream.sum()` và `LongSummaryStatistics.getSum()` đều trả **long**, không tự chuyển lên BigInteger. Nếu các số vượt tổng cho phép của long, tràn số có thể xảy ra.

### 10.2. DoubleStream

~~~java
DoubleSummaryStatistics stats = DoubleStream.of(
        1.5, 2.5, 4.0
).summaryStatistics();
~~~

Đây là đoạn minh họa cần import DoubleSummaryStatistics, DoubleStream. Kết quả với các giá trị này: count = 3, sum = 8.0, min = 1.5, max = 4.0, average có giá trị xấp xỉ 8.0/3 = 2.6666666666666665.

Với double, **không phải mọi giá trị decimal được biểu diễn chính xác**. Nếu hệ thống đòi hỏi equality chính xác đến từng đồng, hãy dùng kiểu dữ liệu và chính sách làm tròn thích hợp thay vì chỉ đổi sang DoubleStream.

### 10.3. NaN và vô cực

Các phép min/max của DoubleStream mang quy tắc so sánh double; tổng và average có thể bị ảnh hưởng mạnh bởi NaN/vô cực. Để kiểm tra dữ liệu:

~~~java
long invalid = DoubleStream.of(
        1.0, Double.NaN, Double.POSITIVE_INFINITY, 2.0)
        .filter(x -> !Double.isFinite(x))
        .count(); // 2
~~~

Đây là đoạn minh họa với import DoubleStream. **Double.isFinite(x)** trả false cho NaN và vô cực, nên `invalid` = 2.

Chọn loại bỏ hay báo lỗi phải dựa trên nghĩa nghiệp vụ. Việc âm thầm lọc bỏ giá trị không hữu hạn rồi tính average có thể biến tập dữ liệu lỗi thành một thống kê trông bình thường.

## 11. Có thể dùng cùng một stream cho sum và average không?

**Không.** Stream chỉ tiêu thụ một lần. Đoạn sau có thể biên dịch nhưng ném **IllegalStateException** khi chạy:

~~~java
IntStream stream = IntStream.of(1, 2, 3);
int sum = stream.sum();
OptionalDouble average = stream.average(); // Stream đã bị tiêu thụ.
~~~

Đây là **đoạn cố ý không chạy thành công**, minh họa lỗi tái sử dụng stream. Sau một terminal operation như sum(), một stream không thể được tiêu thụ lại.

Có ba phương án:

1. **Tạo stream mới từ nguồn có thể duyệt lại:** `IntStream.of(values).sum()` và `IntStream.of(values).average()`.
2. **Dùng `summaryStatistics()` một lần** nếu cần nhiều số đo cùng bộ dữ liệu.
3. **Dùng `Supplier<IntStream>` tạo stream mới** khi cần làm nhiều lần và nguồn cho phép, nhưng đừng giả định nguồn I/O, dòng mạng, cursor hay stream vô hạn tự hỗ trợ đọc lại.

Ví dụ một nguồn tạo lại:

~~~java
Supplier<IntStream> source = () -> IntStream.of(1, 2, 3);
int total = source.get().sum();
double mean = source.get().average().orElseThrow();
~~~

Đây là đoạn minh họa với import Supplier và IntStream. Hai lần `get()` trả hai stream mới riêng; với nguồn bất biến cho kết quả ổn định, tổng 6 và trung bình 2.0. Nếu source đọc dữ liệu thay đổi qua thời gian, hai phép tính không chắc dựa trên cùng một tập dữ liệu.

## 12. summaryStatistics và phép song song

Primitive streams có thể dùng **parallel()**, và `summaryStatistics()` hỗ trợ kết hợp các thống kê từng phần để tạo kết quả tổng. Ví dụ:

~~~java
IntSummaryStatistics stats = IntStream.rangeClosed(1, 1000)
        .parallel()
        .summaryStatistics();
~~~

Đây là đoạn minh họa cần import IntSummaryStatistics và IntStream. Với dữ liệu 1..1000, count 1000, sum 500500, min 1, max 1000, average 500.5. Đặc tính tổng hợp cho phép phân chia và kết hợp nhiều nhóm.

**Những điều cần thận trọng:**

- Với **int/long**, tổng có giới hạn miền dữ liệu; parallel không sửa được lỗi overflow.
- Với **double**, thay đổi thứ tự kết hợp có thể gây khác biệt ở một số bit kết quả.
- Không dùng side effect trong mapper/filter để đếm số lần gọi khi chạy song song.
- Với tập dữ liệu nhỏ, parallel có overhead và không nhất thiết nhanh hơn sequential.
- Các thao tác lấy dữ liệu phải tuân thủ hợp đồng **non-interference** và **statelessness** của Stream để có kết quả đáng tin cậy.

**Một lợi điểm của summaryStatistics:** thay vì chạy sum, average, min, max trên bốn stream độc lập rồi ghép thủ công, một terminal operation tổng hợp các chỉ số vào một đối tượng. Điều này đặc biệt hữu ích khi nguồn là pipeline filter/map phức tạp.

## 13. Rủi ro khi tổng hợp dữ liệu nghiệp vụ

### 13.1. Giá tiền và kiểu số

Với hệ thống tiền tệ, cần chọn kiểu theo **đơn vị lưu trữ, khoảng giá trị và quy tắc làm tròn**. `int` có nguy cơ overflow nếu số lượng/đơn giá lớn. `long` có miền rộng hơn nhưng không vô hạn. `double` có sai số nhị phân, không mặc nhiên phù hợp cho thanh toán chính xác.

Ví dụ `mapToLong(Order::amountInCents).sum()` có thể đúng nếu toàn bộ dữ liệu được biểu diễn bằng đơn vị nhỏ nhất, tổng vẫn trong giới hạn long và miền nghiệp vụ cho phép. Nếu cần nhiều thập phân hoặc tổng cực lớn, dùng **BigDecimal** hoặc **BigInteger** đúng hợp đồng.

### 13.2. Dữ liệu thiếu hoặc không hợp lệ

`mapToInt(Employee::age)` sẽ gọi accessor trên Employee, nên null element có thể gây NPE. Nếu accessor trả **Integer nullable**, việc unboxing cũng có thể gây NPE. `summaryStatistics()` không có cơ chế tự sửa dữ liệu thiếu.

Một pipeline có thể lọc dữ liệu hợp lệ:

~~~java
IntSummaryStatistics ages = employees.stream()
        .filter(Objects::nonNull)
        .map(Employee::age)
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .summaryStatistics();
~~~

Đây là đoạn minh họa, giả định `Employee.age()` trả Integer và đã import Objects cùng IntSummaryStatistics. Nó **bỏ** Employee hoặc age null. Nếu đó là bản ghi bắt buộc phải báo lỗi, đừng âm thầm filter: hãy validate và báo kết quả hỏng theo hợp đồng.

### 13.3. Lấy trung bình của các nhóm trung bình

Giả sử nhóm A có 2 giá trị, trung bình 10; nhóm B có 8 giá trị, trung bình 20. Trung bình của hai trung bình là 15, nhưng trung bình chung của 10 giá trị phải là:

~~~text
(2 * 10 + 8 * 20) / (2 + 8) = 18
~~~

Vì vậy, nếu tổng hợp báo cáo từ nhiều nhóm, cần giữ **count và sum**, hoặc gộp các statistics phù hợp, chứ không chỉ tính trung bình của `getAverage()` giữa các nhóm.

`IntSummaryStatistics.combine(other)`, `LongSummaryStatistics.combine(other)`, `DoubleSummaryStatistics.combine(other)` cho phép gộp thống kê tương thích, nhưng caller phải chắc chắn không tính trùng dữ liệu và không trộn các miền/đơn vị khác nhau. Các object statistics là **mutable accumulator**, không nên coi chúng là immutable snapshot để chia sẻ tùy tiện giữa các thread.

## 14. Kết hợp nhiều nguồn bằng summaryStatistics

Với dữ liệu đã phân nhóm, có thể gộp hai đối tượng thống kê:

~~~java
IntSummaryStatistics groupA = IntStream.of(10, 20)
        .summaryStatistics();
IntSummaryStatistics groupB = IntStream.of(30, 40, 50)
        .summaryStatistics();

groupA.combine(groupB);

System.out.println(groupA.getCount());   // 5
System.out.println(groupA.getSum());     // 150
System.out.println(groupA.getAverage()); // 30.0
~~~

Đây là đoạn minh họa cần import IntStream và IntSummaryStatistics. `combine` cập nhật **groupA** tại chỗ bằng cách thêm thống kê từ **groupB**; nó không trả một đối tượng mới. `groupB` được giữ làm thống kê của nhóm riêng theo ví dụ.

**Không viết `IntSummaryStatistics combined = groupA.combine(groupB);`** vì `combine` trả void. Nếu cần giữ groupA gốc, hãy tạo accumulator riêng rồi `combine` hai nguồn vào accumulator đó hoặc tính trực tiếp trên stream hợp nhất.

Khi hợp nhất thống kê trong parallel stream, JDK cũng dùng cơ chế kết hợp các phần thống kê tương ứng. Với dữ liệu double, thứ tự kết hợp có thể ảnh hưởng sai số cuối; với dữ liệu lớn và biến động cao, cần đánh giá yêu cầu độ chính xác.

## 15. Điểm khác biệt giữa summaryStatistics và Collectors.summarizing*

Với `Stream<T>` kiểu object, Java có nhóm collector:

- **Collectors.summarizingInt(ToIntFunction<T>)**
- **Collectors.summarizingLong(ToLongFunction<T>)**
- **Collectors.summarizingDouble(ToDoubleFunction<T>)**

Ví dụ từ `List<Order>`:

~~~java
IntSummaryStatistics stats = orders.stream()
        .collect(Collectors.summarizingInt(Order::quantity));
~~~

Đây là đoạn minh họa, giả định Order.quantity trả int, orders đã có và import Collectors, IntSummaryStatistics. Nó cho kết quả loại statistics tương tự:

~~~java
IntSummaryStatistics stats = orders.stream()
        .mapToInt(Order::quantity)
        .summaryStatistics();
~~~

Cả hai giúp tổng hợp count/sum/min/max/average. Sự khác biệt là kiểu Stream và cách API kết hợp với collector, ví dụ trong `groupingBy(..., summarizingInt(...))` để thống kê **theo nhóm**.

Không có quy tắc bắt buộc phải dùng collector trong mọi trường hợp. Với một primitive stream đã có, `summaryStatistics()` trực tiếp thường dễ đọc. Khi cần thống kê nhiều nhóm theo khóa, collector có thể giúp giảm phần mã tổ chức dữ liệu.

## 16. Những lỗi thường gặp

| Lỗi hoặc ngộ nhận | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Nghĩ `average()` trả double | Sai kiểu, bỏ qua trường hợp rỗng | Nhớ `OptionalDouble`, xử lý empty |
| Nghĩ `min/max` trả primitive trực tiếp | Không xử lý stream rỗng | Dùng OptionalInt/Long/Double |
| Gọi `getAsInt()` trên OptionalInt rỗng | NoSuchElementException | Dùng orElse/kiểm tra/isPresent/orElseThrow |
| Dùng `sum()` rồi `average()` trên cùng stream | IllegalStateException | Tạo stream mới hoặc summaryStatistics |
| Nghĩ mọi `sum()` tự chuyển lên long | IntStream.sum trả int, có thể overflow | asLongStream hoặc statistics/getSum hoặc kiểu số khác |
| Nghĩ IntSummaryStatistics.getSum trả int | Có thể sai hợp đồng kiểu | getSum của IntSummaryStatistics là long |
| Đọc min/max của summaryStatistics khi count=0 | Nhận sentinel, gây báo cáo sai | Kiểm tra getCount() > 0 |
| Coi average 0.0 khi rỗng là trung bình toán học | Che dữ liệu vắng mặt | Xử lý count=0 hoặc dùng OptionalDouble |
| Dùng double cho tiền tệ chính xác | Sai số floating-point | Chọn BigDecimal/minor units theo miền |
| Tính trung bình các trung bình mà quên trọng số | Kết quả tổng hợp sai | Gộp count/sum hoặc combine statistics |
| Dữ liệu null đi vào mapToInt/mapToLong | NPE khi dereference/unboxing | Validate null hoặc xử lý theo chính sách |
| Dùng parallel và đòi kết quả double giống từng bit | Thứ tự cộng có thể khác | Định nghĩa dung sai/chọn thuật toán phù hợp |
| Dùng count của statistics thay vì total source và coi như bằng nhau | filter có thể đã loại phần tử | Hiểu count là số phần tử đi đến bước thống kê |

## 17. Bài tập thực hành

### Bài 1: Dự đoán kết quả

Cho `IntStream.of(4, 8, 12)`, hãy tính bằng tay `sum()`, `average()`, `min()`, `max()`, và `summaryStatistics()`. Trình bày kiểu trả về của mỗi API.

**Gợi ý:** sum=24, average=8.0, min=4, max=12, count=3.

### Bài 2: Kiểm tra stream rỗng

Dùng `IntStream.empty()`, `LongStream.empty()`, `DoubleStream.empty()` và kiểm tra `sum()`, `average()`, `min()`, `max()`, `summaryStatistics().getCount()`. Giải thích vì sao min/max ở statistics không nên dùng trực tiếp với count=0.

### Bài 3: Quan sát overflow

Tính tổng `Integer.MAX_VALUE` và `1` bằng `IntStream.sum()`, `asLongStream().sum()` và `IntSummaryStatistics.getSum()`. Vì sao kết quả khác nhau? Tình huống nào vẫn có thể vượt long?

### Bài 4: Biến đổi từ danh sách object

Cho List<Product> có thuộc tính `long priceCents`, viết phương thức dùng `mapToLong(Product::priceCents).summaryStatistics()`. Trả báo cáo count, sum, min, max, average; xử lý trường hợp List rỗng mà không hiện sentinel giả.

### Bài 5: Trung bình có trọng số

Nhóm một có 3 điểm trung bình 7; nhóm hai có 12 điểm trung bình 9. Tính trung bình chung bằng count/sum thay vì trung bình hai con số 7 và 9. Tạo hai IntSummaryStatistics phù hợp rồi dùng combine.

### Bài 6: Floating-point và dữ liệu không hợp lệ

Thử `DoubleStream.of(0.1, 0.2, 0.3).sum()` và giải thích vì sao không nên so sánh trực tiếp với các giá trị thập phân theo tư duy tuyệt đối. Thử thêm NaN, Infinity, rồi xác định chính sách input cần thiết khi báo cáo số liệu.

### Bài 7: Tính nhiều chỉ số trong một lần xử lý

Có nguồn Stream từ một thao tác lọc tốn công. So sánh cách tạo lại nguồn bốn lần để gọi sum/average/min/max với cách tạo một IntSummaryStatistics trong một terminal operation. Nêu tình huống nguồn không thể duyệt lại, và vì sao tạo lại nguồn có thể thay đổi dữ liệu.

## 18. Checklist trước khi dùng aggregate trên primitive stream

1. **Kiểu số nào đúng với miền dữ liệu?** int/long/double có giới hạn khác nhau.
2. **Có thể rỗng không?** Với min/max/average dùng Optional; với statistics kiểm tra count.
3. **Có cần nhiều thống kê cùng bộ dữ liệu không?** Cân nhắc summaryStatistics để giảm số lượt duyệt.
4. **Đang tái sử dụng stream đã tiêu thụ không?** Mỗi terminal operation đóng lượt tiêu thụ đó.
5. **Có nguy cơ overflow không?** Đừng để sum sai âm thầm.
6. **Có yêu cầu chính xác thập phân cao không?** Double có sai số biểu diễn và làm tròn.
7. **Dữ liệu chứa null hoặc không hợp lệ không?** Bảo vệ dereference/unboxing và validation.
8. **Có lọc trước statistics không?** Count/sum/min/max chỉ phản ánh những phần tử đi qua pipeline.
9. **Có song song hóa không?** Cẩn trọng với floating-point, side effect và thứ tự.
10. **Có cần kết quả theo nhóm không?** Cân nhắc Collectors.summarizingInt/Long/Double cùng groupingBy.
11. **Có đang trộn số liệu từ nhiều nhóm không?** Gộp count/sum hoặc combine đúng cách, tránh trung bình trung bình thiếu trọng số.
12. **Có kiểm thử các cận miền và tập rỗng không?** Đây là hai nguồn lỗi phổ biến nhất trong báo cáo tổng hợp.

## 19. Ghi nhớ

**sum()** trả số primitive và trả 0 với stream rỗng. **average()** trả OptionalDouble; **min()/max()** trả OptionalInt/OptionalLong/OptionalDouble phù hợp kiểu stream, tất cả đều rỗng nếu không có phần tử. **summaryStatistics()** trả object thống kê cung cấp count, sum, min, max, average trong một terminal operation.

Với statistics của tập rỗng, **getCount()==0** mới là tín hiệu đáng tin; min/max là **sentinel** chứ không phải giá trị dữ liệu. **IntSummaryStatistics.getSum() là long**, khác với **IntStream.sum() là int**; LongStream và DoubleStream cũng có những giới hạn số học cần hiểu.

Chọn công cụ bằng câu hỏi: **“Tôi cần một kết quả đơn lẻ hay cả bộ số liệu, nguồn có thể rỗng không, và kiểu số có giữ được kết quả chính xác trong miền nghiệp vụ không?”** Trả lời được ba điểm đó sẽ giúp viết aggregate trên primitive stream đúng, rõ và dễ kiểm thử.