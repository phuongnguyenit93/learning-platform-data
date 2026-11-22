# mapToInt(), mapToLong() và mapToDouble() trong Java Stream

## Mục tiêu

Trong Java Stream API, ba phương thức **`mapToInt()`, `mapToLong()` và `mapToDouble()`** dùng để chuyển từng phần tử của một **`Stream<T>`** thành một giá trị số nguyên thủy tương ứng. Kết quả không còn là `Stream<Integer>`, `Stream<Long>` hoặc `Stream<Double>` mà lần lượt là **`IntStream`, `LongStream` và `DoubleStream`**. Những primitive stream này cung cấp các phép tổng hợp như `sum()`, `average()`, `min()`, `max()` và `summaryStatistics()`, đồng thời tránh việc boxing/unboxing từng phần tử trong những giai đoạn xử lý số nguyên thủy phù hợp.

Sau bài này, bạn có thể:

- Đọc đúng chữ ký, đầu vào mapper và kiểu Stream kết quả của ba phương thức.
- Phân biệt `map()` trả `Stream<R>` với `mapToInt/Long/Double()` trả primitive stream.
- Kết hợp mapper với lambda hoặc method reference; hiểu target type `ToIntFunction`, `ToLongFunction`, `ToDoubleFunction`.
- Tính tổng, trung bình, cực trị, thống kê và xử lý Stream rỗng qua `OptionalInt`, `OptionalLong`, `OptionalDouble`.
- Chuyển ngược về Stream object bằng `boxed()` hoặc `mapToObj()` khi cần.
- Phân biệt kiểu primitive, chuyển kiểu số, tràn số, sai số `double` và chi phí boxing.
- Kiểm thử chương trình Java 17 và tránh những lỗi thường gặp khi biến đổi dữ liệu số.

## 1. Vì sao có các primitive stream?

Giả sử ta có danh sách chuỗi và muốn tính tổng độ dài:

```java
List<String> words = List.of("Java", "Go", "API");
```

Một cách dùng `map`:

```java
int sum = words.stream()
        .map(String::length)
        .mapToInt(Integer::intValue)
        .sum();
```

`String.length()` trả primitive `int`, nhưng `Stream.map` tạo `Stream<Integer>`, khiến các số được boxing thành `Integer` trước khi chuyển lại về `int`. Cách thường gọn và sát mục tiêu hơn:

```java
int sum = words.stream()
        .mapToInt(String::length)
        .sum(); // 9
```

`Stream<String>` được biến thành `IntStream` ngay sau `mapToInt`. Sau đó `sum()` trả primitive `int`. Không cần tạo `Integer` cho từng kết quả của mapper chỉ để cộng các số.

Ba kiểu primitive stream là:

| Loại | Phần tử | Ví dụ kết quả |
| --- | --- | --- |
| `IntStream` | `int` | Độ dài chuỗi, số lượng, chỉ số |
| `LongStream` | `long` | Timestamp dạng số, số lượt lớn, giá trị tiền đã quy đổi ra đơn vị nhỏ |
| `DoubleStream` | `double` | Trọng lượng, tỉ lệ, đo lường thực |

**Chú ý:** các kiểu này phục vụ **xử lý giá trị số primitive**; chúng không mặc nhiên thay thế mô hình nghiệp vụ. Tiền tệ có quy tắc làm tròn thường cần `BigDecimal` hoặc số nguyên đơn vị nhỏ; việc dùng `double` có thể tạo sai số biểu diễn.

Các ví dụ nhỏ trong tài liệu có thể cần import `java.util.List`, `java.util.stream.*` và các lớp mô hình dữ liệu tương ứng; chương trình hoàn chỉnh ở phần sau có đầy đủ import.

## 2. Chữ ký ba phương thức và target type của lambda

Trên `Stream<T>`, API tương đương:

```java
IntStream mapToInt(ToIntFunction<? super T> mapper);
LongStream mapToLong(ToLongFunction<? super T> mapper);
DoubleStream mapToDouble(ToDoubleFunction<? super T> mapper);
```

Đây là **các khai báo API rút gọn** để học, không phải mã cần tự thêm vào ứng dụng. Mapper phải khác `null`. Ba functional interface thuộc `java.util.function` và có function descriptor:

| Mapper | Phương thức hàm | Descriptor | Kết quả |
| --- | --- | --- | --- |
| `ToIntFunction<T>` | `int applyAsInt(T value)` | `(T) -> int` | `IntStream` |
| `ToLongFunction<T>` | `long applyAsLong(T value)` | `(T) -> long` | `LongStream` |
| `ToDoubleFunction<T>` | `double applyAsDouble(T value)` | `(T) -> double` | `DoubleStream` |

Nếu nguồn là `Stream<Order>`, `mapToInt(Order::units)` yêu cầu một hàm nhận `Order` và trả `int`. Method reference `Order::units` hợp lệ khi record `Order` có accessor `int units()`.

Ví dụ đọc mapper:

```java
IntStream lengths = Stream.of("Java", "Go")
        .mapToInt(text -> text.length());
```

Compiler biết `text` có kiểu `String` từ `Stream<String>` và target `ToIntFunction<? super String>`. Kết quả là một `IntStream`, không phải `List<Integer>` hoặc `Stream<Integer>`.

Có thể ghi kiểu tường minh:

```java
IntStream lengths = Stream.of("Java", "Go")
        .mapToInt((String text) -> text.length());
```

hoặc dùng method reference:

```java
IntStream lengths = Stream.of("Java", "Go")
        .mapToInt(String::length);
```

Ba đoạn là **ba phương án độc lập** (không đặt cùng biến `lengths` trong một scope). Nếu dữ liệu trả về của lambda phù hợp descriptor, chọn dạng ngắn, dễ hiểu nhất.

## 3. mapToInt(): biến object thành int

`mapToInt` rất thích hợp khi đối tượng đã có thuộc tính kiểu `int`:

```java
record Product(String name, int quantity) {}

List<Product> products = List.of(
        new Product("Book", 2),
        new Product("Pen", 5)
);

int totalQuantity = products.stream()
        .mapToInt(Product::quantity)
        .sum(); // 7
```

Ở đoạn minh họa, accessor `Product::quantity` trả primitive `int`. Sau `mapToInt`, có thể tiếp tục các phương thức chuyên cho `IntStream`:

```java
IntStream counts = products.stream()
        .mapToInt(Product::quantity);

int total = counts.sum();
```

Không gọi tiếp `counts.average()` trên cùng biến sau `sum()` vì **Stream là single-use**. Cần tạo một Stream mới hoặc dùng `summaryStatistics()` để lấy nhiều số liệu trong một terminal operation.

### 3.1. Khi nguồn String cần parse thành số

```java
List<String> raw = List.of("10", "20", "30");

int total = raw.stream()
        .mapToInt(Integer::parseInt)
        .sum(); // 60
```

`Integer.parseInt` trả `int`. Nếu có phần tử `"abc"` thì lúc mapper chạy sẽ ném `NumberFormatException`; `mapToInt` **không tự bỏ qua chuỗi sai**.

Đối với dữ liệu người dùng, nên xác định chính sách rõ: từ chối cả dữ liệu, ghi nhận lỗi, hoặc parse từng phần tử thành một kết quả biểu đạt thành công/thất bại. Không âm thầm bắt mọi lỗi rồi trả `0` nếu `0` có thể mang ý nghĩa nghiệp vụ hợp lệ.

### 3.2. Tổng, trung bình và giá trị lớn nhất

```java
int sum = products.stream().mapToInt(Product::quantity).sum();

OptionalDouble average = products.stream()
        .mapToInt(Product::quantity)
        .average();

OptionalInt max = products.stream()
        .mapToInt(Product::quantity)
        .max();
```

`average()` trả **`OptionalDouble`**, không trả `double` trực tiếp, vì nguồn có thể rỗng; `max()` trả **`OptionalInt`**. Với nguồn `[2, 5]`, trung bình là `3.5` và cực đại là `5`. Nếu nguồn rỗng, các Optional tương ứng rỗng.

`sum()` trả `0` khi IntStream rỗng. Cần phân biệt “không có số liệu” và “có dữ liệu nhưng tổng bằng 0” nếu yêu cầu nghiệp vụ cần biết số lượng phần tử.

## 4. mapToLong(): biến object thành long

`mapToLong` thường dùng cho một trường có kiểu `long` hoặc phép tính có thể vượt phạm vi `int`:

```java
record Item(long priceCents, int units) {}

List<Item> items = List.of(
        new Item(1_250, 2),
        new Item(2_500, 3)
);

long revenue = items.stream()
        .mapToLong(item -> item.priceCents() * item.units())
        .sum(); // 10000
```

Trong phép nhân trên, `item.priceCents()` là `long` và `units()` là `int`; Java nâng `int` thành `long` để thực hiện phép nhân kiểu `long`. Kết quả đúng cho dữ liệu mẫu là `1_250*2 + 2_500*3 = 10_000`.

Nếu cả hai toán hạng ban đầu đều là `int`, **phải ép lên long trước khi nhân** nếu kết quả có thể lớn:

```java
int price = 1_500_000_000;
int quantity = 3;

// Sai ý định khi tính số lớn: phép nhân int tràn trước khi gán long.
long wrong = price * quantity;

// Đúng về phạm vi int, kết quả là long.
long correct = (long) price * quantity; // 4500000000
```

Mặc dù `mapToLong` yêu cầu mapper trả `long`, nếu body đã thực hiện một phép nhân `int * int` bị tràn, việc chuyển kết quả tràn sang `long` sau đó không phục hồi giá trị đúng. Cần nâng kiểu **trước** phép nhân.

`LongStream.sum()` cũng có thể tràn nếu tổng vượt phạm vi `long`; Java không tự ném ngoại lệ khi dùng `+` thông thường. Với yêu cầu phát hiện tràn, có thể dùng phép toán có kiểm tra như `Math.addExact`/`Math.multiplyExact` trong một thiết kế tổng hợp phù hợp, hoặc dùng `BigInteger` nếu cần phạm vi lớn hơn.

### 4.1. Trường hợp đếm và tổng hợp

`IntStream.sum()` là `int`, còn `LongStream.sum()` là `long`. `Stream.count()` trả `long` vì nó đếm số phần tử (không phải tổng các giá trị). Đừng nhầm:

```java
long numberOfItems = items.stream().count(); // 2

long totalCents = items.stream()
        .mapToLong(Item::priceCents)
        .sum(); // 3750
```

`count()` không cần `mapToLong` vì đếm số phần tử, còn `sum()` cộng giá trị số đã ánh xạ.

## 5. mapToDouble(): biến object thành double

`mapToDouble` dùng cho dữ liệu đo lường, tỉ lệ hoặc phép tính trả `double`:

```java
record Measure(String id, double weightKg) {}

List<Measure> measures = List.of(
        new Measure("A", 1.25),
        new Measure("B", 2.00)
);

double totalWeight = measures.stream()
        .mapToDouble(Measure::weightKg)
        .sum(); // 3.25
```

`DoubleStream` có `sum()`, `average()`, `min()`, `max()` và `summaryStatistics()`. Trung bình của một Stream rỗng là `OptionalDouble.empty()`:

```java
OptionalDouble average = measures.stream()
        .mapToDouble(Measure::weightKg)
        .average();

double value = average.orElse(0.0);
```

Chỉ dùng `orElse(0.0)` nếu nghiệp vụ thực sự muốn coi thiếu số liệu như `0.0`. Với báo cáo hoặc chỉ số thống kê, thiếu dữ liệu có thể cần phân biệt với đo lường bằng 0.

### 5.1. Độ chính xác dấu phẩy động

`double` biểu diễn giá trị nhị phân theo chuẩn dấu phẩy động; nhiều số thập phân thông dụng không biểu diễn chính xác tuyệt đối. Ví dụ phép cộng `0.1 + 0.2` không có cùng biểu diễn bit như `0.3` trong nhiều phép so sánh trực tiếp.

`DoubleStream.sum()` có thể dùng kỹ thuật giảm sai số tổng, nhưng **không bảo đảm kết quả toán học chính xác tuyệt đối**, đặc biệt với giá trị rất lớn/nhỏ, `NaN`, vô cực hoặc khác thứ tự đánh giá trong pipeline song song. Không nên dùng `==` để kiểm tra kết quả tổng hợp gần đúng nếu yêu cầu có sai số chấp nhận được.

Đối với tiền tệ, nên cân nhắc:

- Số nguyên đơn vị nhỏ như `long cents` khi đơn vị tiền tệ và phạm vi tính phù hợp.
- `BigDecimal` khi cần số thập phân chính xác, làm tròn và quy tắc tài chính rõ ràng.
- `double` cho số đo, khoa học hoặc thống kê có quy tắc sai số được chấp nhận.

Không chọn `mapToDouble` chỉ vì doanh thu chứa dấu thập phân trong giao diện. **Kiểu số là một quyết định về tính đúng đắn**, không chỉ hiệu năng.

## 6. map() so với mapToInt(), mapToLong(), mapToDouble()

| Cách ánh xạ | Mapper | Stream kết quả | Ví dụ terminal |
| --- | --- | --- | --- |
| `map(f)` | `Function<T,R>` | `Stream<R>` | `toList()`, `collect()` |
| `mapToInt(f)` | `ToIntFunction<T>` | `IntStream` | `sum()` trả `int` |
| `mapToLong(f)` | `ToLongFunction<T>` | `LongStream` | `sum()` trả `long` |
| `mapToDouble(f)` | `ToDoubleFunction<T>` | `DoubleStream` | `average()` trả `OptionalDouble` |

Một phép ánh xạ bằng `map` phù hợp khi cần giữ kết quả là object, record hoặc các kiểu như `BigDecimal`:

```java
List<String> uppercase = words.stream()
        .map(String::toUpperCase)
        .toList();
```

Còn với số để tổng hợp:

```java
int characters = words.stream()
        .mapToInt(String::length)
        .sum();
```

Nếu dùng `map(String::length)`, kết quả là `Stream<Integer>` và không có `sum()` trực tiếp như `IntStream`. Có thể thêm `reduce(0, Integer::sum)` hoặc chuyển sang primitive stream, nhưng lựa chọn `mapToInt` thường dễ hiểu hơn cho phép cộng giá trị `int`.

### 6.1. Chi phí boxing và giới hạn suy luận hiệu năng

Một `Stream<Integer>` làm việc với wrapper `Integer`; `IntStream` làm việc với primitive `int`. Primitive streams có thể giảm boxing/unboxing ở những giai đoạn tính toán số, nhưng **không tự động bảo đảm mọi chương trình nhanh hơn**. Hiệu năng phụ thuộc chi phí mapper, kích thước dữ liệu, JVM/JIT, cấu trúc nguồn, cache và thao tác terminal.

Nếu mapper chủ yếu gọi database hoặc HTTP, chi phí I/O sẽ chi phối, còn micro-optimization boxing có thể không đáng kể. Hãy đo bằng benchmark phù hợp nếu tối ưu hiệu năng là yêu cầu quan trọng.

## 7. Ví dụ Java 17 đầy đủ: từ dữ liệu Order đến ba primitive stream

Tạo file **`PrimitiveMappingDemo.java`**:

```java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Locale;
import java.util.OptionalDouble;
import java.util.stream.IntStream;

public class PrimitiveMappingDemo {
    record Order(String code, int units, long unitPriceCents, double weightKg) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("A", 2, 1_250, 1.25),
            new Order("B", 3, 2_500, 2.00),
            new Order("C", 1, 750, 0.75)
        );

        int units = orders.stream().mapToInt(Order::units).sum();
        long priceSum = orders.stream()
                .mapToLong(Order::unitPriceCents).sum();
        long revenue = orders.stream()
                .mapToLong(o -> o.unitPriceCents() * o.units()).sum();
        double weight = orders.stream()
                .mapToDouble(Order::weightKg).sum();
        OptionalDouble averageWeight = orders.stream()
                .mapToDouble(Order::weightKg).average();

        IntSummaryStatistics statistics = orders.stream()
                .mapToInt(Order::units).summaryStatistics();
        List<Integer> lengths = List.of("Java", "Go", "")
                .stream().mapToInt(String::length).boxed().toList();

        long billions = IntStream.rangeClosed(1, 3)
                .mapToLong(n -> n * 1_000_000_000L).sum();
        double halves = IntStream.rangeClosed(1, 3)
                .mapToDouble(n -> n / 2.0).sum();

        System.out.println("Units: " + units);
        System.out.println("Price sum cents: " + priceSum);
        System.out.println("Revenue cents: " + revenue);
        System.out.printf(Locale.ROOT, "Weight total kg: %.2f%n", weight);
        System.out.printf(Locale.ROOT, "Weight average kg: %.2f%n",
                averageWeight.orElse(0));
        System.out.println("Units stats: count=" + statistics.getCount()
                + ", min=" + statistics.getMin()
                + ", max=" + statistics.getMax()
                + ", sum=" + statistics.getSum());
        System.out.println("Lengths boxed: " + lengths);
        System.out.println("Billions: " + billions);
        System.out.printf(Locale.ROOT, "Halves: %.1f%n", halves);
        System.out.println("Empty average: "
                + java.util.stream.DoubleStream.empty().average().isEmpty());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac PrimitiveMappingDemo.java
java PrimitiveMappingDemo
```

**Stdout chính xác:**

```text
Units: 6
Price sum cents: 4500
Revenue cents: 10750
Weight total kg: 4.00
Weight average kg: 1.33
Units stats: count=3, min=1, max=3, sum=6
Lengths boxed: [4, 2, 0]
Billions: 6000000000
Halves: 3.0
Empty average: true
```

### 7.1. Giải thích từng kết quả

1. Các đơn có `units` bằng `2, 3, 1` nên `mapToInt(Order::units).sum()` trả `6`.
2. Tổng giá đơn vị theo trường `unitPriceCents` là `1250 + 2500 + 750 = 4500`, được lưu thành `long`. Đây **không phải doanh thu**, vì mỗi đơn có số lượng khác nhau.
3. Doanh thu thực tế tính theo đơn vị xu là `1250*2 + 2500*3 + 750*1 = 10750`; lambda `mapToLong(o -> o.unitPriceCents() * o.units())` tạo một giá trị `long` cho mỗi dòng.
4. Trọng lượng mẫu cộng lại là `1.25 + 2.00 + 0.75 = 4.00` và trung bình là `4.00 / 3 ≈ 1.33` theo định dạng hai chữ số thập phân từ `Locale.ROOT`.
5. `IntSummaryStatistics` thu trong một lần: `count=3`, `min=1`, `max=3`, `sum=6`. Điều này tránh việc cố chạy nhiều terminal operations trên cùng một Stream đã tiêu thụ.
6. `mapToInt(String::length)` tạo các số primitive `4, 2, 0`; `boxed()` chuyển sang `Stream<Integer>` rồi `toList()` thu thành `[4, 2, 0]`.
7. `IntStream.rangeClosed(1,3)` sinh `1,2,3`. `mapToLong(n -> n * 1_000_000_000L)` tính phép nhân `long` nên tổng là `6_000_000_000`, vượt phạm vi `int` nhưng hợp lệ trong `long`.
8. `mapToDouble(n -> n / 2.0)` cho `0.5,1.0,1.5` nên tổng là `3.0`.
9. `DoubleStream.empty().average()` trả `OptionalDouble.empty()`, vì vậy `isEmpty()` là `true`.

Code dùng `record` (có trong Java 17), `Stream.toList()` và các primitive stream chuẩn. Không có dữ liệu ngẫu nhiên hoặc truy cập mạng; kết quả có thể kiểm chứng độc lập.

## 8. summaryStatistics(): lấy nhiều phép đo trong một lần

Nếu cần `count`, `min`, `max`, `sum` và `average` của cùng một Stream số nguyên, dùng `summaryStatistics()`:

```java
IntSummaryStatistics stats = products.stream()
        .mapToInt(Product::quantity)
        .summaryStatistics();

System.out.println(stats.getCount());
System.out.println(stats.getMin());
System.out.println(stats.getMax());
System.out.println(stats.getSum());
System.out.println(stats.getAverage());
```

Đoạn trên minh họa với `products`, `Product` đã định nghĩa trong ngữ cảnh. Ngoài `IntSummaryStatistics` còn có `LongSummaryStatistics` và `DoubleSummaryStatistics` tương ứng.

Lợi ích:

- Có thể lấy nhiều số liệu sau **một terminal operation** thay vì tạo lại Stream cho từng thống kê.
- Các getter có kiểu rõ: `getCount()` trả `long`, `getAverage()` trả `double`; `getSum()` trả kiểu tổng phù hợp với loại thống kê.
- Không đánh đồng loại số của dữ liệu đầu vào với kiểu của mọi chỉ số thống kê.

**Lưu ý Stream rỗng:** `summaryStatistics()` vẫn trả một đối tượng statistics; `getCount()` là `0`. Các getter `getMin/getMax` có giá trị khởi tạo đặc biệt tùy loại statistics, nên khi báo cáo cực trị, hãy kiểm tra `getCount() > 0`. Với `average()` trực tiếp trên primitive stream, trạng thái rỗng được phản ánh rõ bằng `OptionalDouble.empty()`.

## 9. Phân biệt mapTo* trên Stream<T> với chuyển đổi giữa primitive streams

Ba phương thức đang học thuộc `Stream<T>` và nhận mapper từ object `T` sang số primitive. Nhưng khi **đã có một primitive stream**, cũng có những phép chuyển kiểu khác.

### 9.1. Từ IntStream sang LongStream hoặc DoubleStream

```java
long sum = IntStream.of(1, 2, 3)
        .mapToLong(n -> n * 1_000_000_000L)
        .sum(); // 6000000000
```

`IntStream.mapToLong` nhận `IntToLongFunction` với descriptor `(int) -> long`, **không phải `ToLongFunction<T>`** trên `Stream<T>`. Cùng tên `mapToLong` nhưng target mapper và nguồn đầu vào khác nhau.

```java
double total = IntStream.of(1, 2, 3)
        .mapToDouble(n -> n / 2.0)
        .sum(); // 3.0
```

`IntStream.mapToDouble` nhận `IntToDoubleFunction`. Nếu viết `n / 2` thay vì `n / 2.0`, toán học được thực hiện dưới dạng **phép chia nguyên** trước khi chuyển sang `double`; kết quả sẽ khác. Chú ý kiểu toán hạng trong body, không chỉ kiểu kết quả cuối.

### 9.2. Các đường chuyển đổi khác

- `IntStream.asLongStream()` chuyển các phần tử `int` thành `long` bằng widening.
- `IntStream.asDoubleStream()` chuyển các phần tử `int` thành `double`.
- `LongStream.asDoubleStream()` chuyển các phần tử `long` thành `double`; các số `long` rất lớn có thể mất độ chính xác khi biểu diễn bằng `double`.
- `IntStream.boxed()`, `LongStream.boxed()`, `DoubleStream.boxed()` biến phần tử primitive thành wrapper để dùng `Stream<Integer/Long/Double>`.

Ví dụ:

```java
List<Long> longs = IntStream.rangeClosed(1, 3)
        .asLongStream()
        .boxed()
        .toList(); // [1, 2, 3]
```

Khi chỉ cần **nâng kiểu số giữ nguyên giá trị**, `asLongStream` thường rõ mục đích hơn việc viết `mapToLong(n -> n)`. Khi cần **biến đổi theo công thức**, dùng mapper tương ứng.

## 10. boxed() và mapToObj(): trở về kết quả object

Một primitive stream không có tất cả phương thức của `Stream<T>` theo cùng dạng; khi cần thu thập vào một collection đối tượng hoặc tạo record từ giá trị số, có thể chuyển về object stream.

### 10.1. boxed()

```java
List<Integer> lengths = Stream.of("A", "Java")
        .mapToInt(String::length)
        .boxed()
        .toList(); // [1, 4]
```

`boxed()` biến mỗi `int` thành `Integer`. Sau đó `toList()` tạo một `List<Integer>`. Đây là lựa chọn đúng khi yêu cầu đầu ra thực sự là danh sách wrapper; nhưng nếu chỉ cần tính `sum`, nên giữ primitive stream.

### 10.2. mapToObj()

```java
List<String> labels = IntStream.of(1, 2, 3)
        .mapToObj(n -> "No." + n)
        .toList(); // [No.1, No.2, No.3]
```

`mapToObj` nhận mapper từ primitive sang object và trả `Stream<R>`. Nó không chỉ boxing: người viết quyết định object được tạo. Phân biệt `IntStream.mapToObj` với `Stream<T>.map`; cả hai cho Stream object nhưng nguồn đầu vào có loại khác nhau.

### Khi nào cần quay lại object stream?

Dùng `boxed()` khi cần wrapper để tương tác với API generic hoặc thu danh sách. Dùng `mapToObj()` khi muốn tạo một object khác từ số (chuỗi, record, đối tượng domain). Không chuyển qua lại primitive → wrapper → primitive nhiều lần không có lý do, vì sẽ khiến pipeline dài hơn và có thể phát sinh chi phí không cần thiết.

## 11. Lazy evaluation và giới hạn sử dụng Stream

`mapToInt`, `mapToLong` và `mapToDouble` là **intermediate operations**. Body mapper thường chỉ thực thi khi terminal operation yêu cầu phần tử.

```java
IntStream pipeline = Stream.of("A", "BB")
        .mapToInt(s -> {
            System.out.println("mapping " + s);
            return s.length();
        });

// Chưa in "mapping A" hay "mapping BB" ở thời điểm tạo pipeline.
int sum = pipeline.sum();
```

Khi `sum` chạy trong pipeline tuần tự này, mapper xử lý hai phần tử để tạo tổng. Nhưng đừng sử dụng side effect trong `mapToInt` làm cơ chế nghiệp vụ đúng một lần cho mọi pipeline: short-circuit và các tối ưu hóa Stream có thể thay đổi số lần quan sát mapper.

### Mỗi Stream chỉ được tiêu thụ một lần

```java
IntStream numbers = Stream.of("A", "BB")
        .mapToInt(String::length);

int sum = numbers.sum();

// Không gọi numbers.average() sau đó:
// cùng Stream đã được tiêu thụ.
```

Để tính cả tổng và trung bình, tạo lại Stream từ nguồn có thể tái sử dụng:

```java
int sum = words.stream().mapToInt(String::length).sum();
OptionalDouble avg = words.stream()
        .mapToInt(String::length)
        .average();
```

Hoặc dùng `summaryStatistics` một lần. Nếu nguồn đến từ tệp hoặc I/O và không thể tạo lại tùy ý, thiết kế một phép tổng hợp duy nhất hoặc dùng collection trung gian theo nhu cầu bộ nhớ và vòng đời tài nguyên.

## 12. Xử lý null, dữ liệu lỗi và checked exception

### 12.1. Null trong nguồn object

`Stream<T>` có thể chứa `null` từ những nguồn nhất định. Một mapper như `String::length` hoặc `s -> s.length()` sẽ ném `NullPointerException` nếu phần tử là null:

```java
// Minh họa nguồn có null (không tạo bằng List.of vì List.of cấm null).
List<String> names = new ArrayList<>();
names.add("Java");
names.add(null);

int total = names.stream()
        .mapToInt(String::length)
        .sum(); // Có thể ném NullPointerException
```

Nếu null cần được bỏ qua theo nghiệp vụ:

```java
int total = names.stream()
        .filter(java.util.Objects::nonNull)
        .mapToInt(String::length)
        .sum(); // 4
```

Không lọc null bừa bãi nếu thiếu dữ liệu là lỗi phải báo. Với wrapper `Integer`, unboxing null cũng có thể ném `NullPointerException`:

```java
// Minh họa: numericValues là một List<Integer> có thể chứa null.
int total = numericValues.stream()
        .mapToInt(Integer::intValue)
        .sum();
```

Đoạn này không độc lập vì `numericValues` cần được khai báo; nó chỉ ra rằng primitive stream không thể biểu diễn phần tử số kiểu primitive là `null`.

### 12.2. Parse thất bại

`Integer::parseInt` và `Long::parseLong` có thể ném `NumberFormatException`. Không nên chuyển chuỗi không hợp lệ thành số không một cách âm thầm, nhất là khi nó có thể làm báo cáo tổng và trung bình sai.

Nếu cần parse hàng loạt dữ liệu có lỗi, cân nhắc xử lý validation trước, ghi lại lỗi theo từng record hoặc tách stream kết quả thành các nhánh thành công/thất bại bằng cấu trúc dữ liệu thích hợp.

### 12.3. Checked exception trong mapper

`ToIntFunction.applyAsInt`, `ToLongFunction.applyAsLong` và `ToDoubleFunction.applyAsDouble` không khai báo checked exception. Nếu mapper gọi API ném `IOException`, lambda phải bắt/chuyển theo quy tắc hoặc tách I/O khỏi pipeline; không tự thêm `throws IOException` vào target type được.

Không nên tự ý bọc mọi ngoại lệ thành unchecked chỉ để code ngắn. Hãy xác định ai sở hữu xử lý lỗi, retry, logging và dữ liệu cần bồi hoàn.

## 13. Ranh giới số học: overflow, precision, chia nguyên

### 13.1. Tràn số trước khi mapper trả long

`mapToLong` không bảo vệ một phép cộng hoặc nhân đã bị tràn `int` trong body:

```java
int price = 1_500_000_000;
int units = 3;

long wrong = price * units;        // Tràn trong int
long correct = (long) price * units;
```

Với dữ liệu có thể vượt cả `long`, dùng `BigInteger` hoặc cơ chế kiểm tra tràn theo yêu cầu. Nếu muốn phát hiện chính xác lỗi khi từng phép toán vượt miền giá trị, sử dụng `Math.multiplyExact` và `Math.addExact` ở vị trí phù hợp.

### 13.2. int / int vẫn là phép chia nguyên

```java
double average = IntStream.of(1, 2, 3)
        .mapToDouble(n -> n / 2)
        .sum(); // 2.0, vì 1/2=0, 2/2=1, 3/2=1
```

Nếu mục tiêu là chia thực:

```java
double total = IntStream.of(1, 2, 3)
        .mapToDouble(n -> n / 2.0)
        .sum(); // 3.0
```

Chỉ thay `mapToDouble` không bắt buộc mọi phép toán **bên trong** body dùng `double`. Cần làm ít nhất một toán hạng thành số thực trước khi chia.

### 13.3. Double không bảo đảm chính xác thập phân

Với tiền tệ, việc dùng `double` rồi định dạng hai chữ số thập phân không đồng nghĩa giá trị được lưu chính xác theo quy tắc tiền. Nếu cần tính giá sau giảm, thuế, làm tròn tại từng dòng hoặc cuối giao dịch, hãy xác định quy tắc rõ và dùng loại số phù hợp.

### 13.4. NaN và Infinity

`DoubleStream` có thể chứa `Double.NaN` hoặc `Double.POSITIVE_INFINITY` từ mapper. Các phép `sum`, `average`, `min`, `max` có quy tắc riêng với giá trị này; không giả định mọi kết quả luôn là một số hữu hạn. Khi xử lý số đo, kiểm tra đầu vào bằng `Double.isFinite(value)` nếu miền dữ liệu yêu cầu số thực hữu hạn.

## 14. Khi nào nên dùng từng phương thức?

| Tình huống | Phương thức gợi ý | Lý do |
| --- | --- | --- |
| Đếm tổng số lượng hàng hóa trong các record | `mapToInt(Order::units).sum()` | Thuộc tính dạng `int`, phép tổng đơn giản |
| Tính tổng doanh thu đơn vị nhỏ | `mapToLong(order -> ...)` | Kết quả có thể lớn hơn `int` |
| Tính trung bình trọng lượng | `mapToDouble(Measure::weightKg).average()` | Dữ liệu đo lường dạng `double` |
| Tính độ dài chuỗi | `mapToInt(String::length)` | Không cần boxing mỗi độ dài |
| Chuyển số nguyên sang đơn vị lớn | `IntStream.mapToLong` | Thực hiện công thức với kết quả `long` |
| Chuyển int sang double để chia thực | `IntStream.mapToDouble` | Dùng số thực trong biểu thức |
| Cần `List<Integer>` thành kết quả | `mapToInt(...).boxed().toList()` | Chuyển về wrapper khi thực sự cần |
| Cần object nghiệp vụ hoặc `BigDecimal` | `map(...)` | Kiểu kết quả không phải primitive số |
| Cần nhiều thống kê trên cùng dòng dữ liệu | `summaryStatistics()` | Một lần terminal cho nhiều phép đo |

Hãy ưu tiên kiểu kết quả phù hợp **ngữ nghĩa và phạm vi dữ liệu**, sau đó chọn primitive stream khi phép tính cần số nguyên thủy. Đừng chọn `mapToInt` cho giá trị có thể vượt `int` chỉ vì giá trị ban đầu đang được lưu bằng `int`; có thể cần nâng kiểu trước khi tính.

## 15. Sai lầm thường gặp

1. **Nhầm `mapToInt` trả `Stream<Integer>`:** nó trả `IntStream`; muốn object stream, gọi `boxed()`.
2. **Viết `map(...).sum()`:** `Stream<Integer>` không có `sum()` trực tiếp như `IntStream`. Chọn `mapToInt` hoặc phép reduce phù hợp.
3. **Dùng sai mapper:** `mapToInt` cần kết quả có thể dùng làm `int`; mapper trả `String` không khớp target.
4. **Tưởng `mapToLong` sửa được phép nhân `int` đã tràn:** phải nâng kiểu trước phép tính.
5. **Tưởng `mapToDouble` biến `int/int` thành chia thực:** phải dùng một toán hạng double, ví dụ `2.0`.
6. **Gọi `average().getAsDouble()` không kiểm tra nguồn rỗng:** có thể ném `NoSuchElementException`; dùng `isPresent`, `orElse` hoặc chính sách thiếu dữ liệu.
7. **Quên null trong Stream object:** method reference và phép unboxing có thể ném NPE.
8. **Quên nguồn sai định dạng:** `parseInt` không tự bỏ giá trị không hợp lệ; cần xử lý validation.
9. **Tưởng sum luôn chính xác và không tràn:** `int`/`long` có miền hữu hạn, còn `double` có sai số.
10. **Dùng cùng một primitive stream cho nhiều terminal operations:** Stream là single-use.
11. **Dùng `boxed` quá sớm:** có thể tạo boxing khi không cần; giữ primitive cho phép tính số.
12. **Dùng `double` cho tiền chỉ vì muốn phép tính trung bình:** hãy chọn kiểu số theo quy tắc tài chính.
13. **Cho rằng `mapToInt` chạy ngay:** đây là intermediate operation; mapper thường chỉ chạy khi terminal yêu cầu.
14. **Lạm dụng side effect trong lambda:** số lần chạy mapper có thể bị ảnh hưởng bởi short-circuit và tối ưu hóa.

## 16. Bài tập thực hành

1. Cho `List<String> words = List.of("Java","Go","API");`. Viết pipeline dùng `mapToInt` để lấy tổng độ dài. Kết quả là bao nhiêu?
2. Cho `record Item(String id,int count) {}` và danh sách 3 Item có số lượng 2,4,6. Dùng `mapToInt` để tính tổng, trung bình và cực đại.
3. Cho danh sách chuỗi số `"100"`, `"200"`, `"300"`. Dùng `mapToLong(Long::parseLong)` để tính tổng; điều gì xảy ra nếu có `"abc"`?
4. Với hai trường `int unitPrice` và `int quantity` có thể lớn, viết lambda cho `mapToLong` sao cho phép nhân được thực hiện bằng `long` ngay từ đầu.
5. Giả sử `record Sensor(double temperature) {}`. Tính `OptionalDouble` trung bình nhiệt độ bằng `mapToDouble`. Chọn chính sách khi danh sách rỗng.
6. Viết pipeline từ `Stream.of("A","BB","CCC")` qua `mapToInt(String::length)` rồi `boxed()` để lấy `List<Integer>`.
7. Phân biệt `IntStream.of(1,2,3).mapToDouble(n -> n/2).sum()` với `mapToDouble(n -> n/2.0).sum()`.
8. Tại sao `Stream<Integer>` có thể chứa phần tử `null` mà `IntStream` không có giá trị primitive `null`? NPE có thể xảy ra ở đâu?
9. Sau `IntStream.mapToLong` có thể gọi `sum()` kiểu gì? Vì sao tên mapper trên primitive stream không đồng nghĩa cùng functional interface như trên `Stream<T>`?
10. Một báo cáo cần tổng, min, max và trung bình số lượng trên cùng dữ liệu. Vì sao `summaryStatistics()` có thể phù hợp hơn cố sử dụng cùng Stream cho bốn terminal operations?

### Gợi ý đáp án

1. `words.stream().mapToInt(String::length).sum()` trả `9`.
2. `summaryStatistics()` cho `sum=12`, `count=3`, `average=4.0`, `max=6`; hoặc tạo Stream mới cho từng phép đo.
3. Tổng `600`; `"abc"` làm phát sinh `NumberFormatException` khi mapper chạy.
4. `mapToLong(x -> (long) x.unitPrice() * x.quantity())` khi record có accessor thích hợp; ép long trước phép nhân.
5. `sensors.stream().mapToDouble(Sensor::temperature).average()`; khi rỗng trả `OptionalDouble.empty()`, caller quyết định thiếu dữ liệu.
6. `Stream.of("A","BB","CCC").mapToInt(String::length).boxed().toList()` trả `[1,2,3]`.
7. Bản chia nguyên trả tổng `2.0`; bản chia thực trả tổng `3.0`.
8. `Integer` là object có thể null; khi `mapToInt(Integer::intValue)` dereference hoặc unboxing một phần tử null thì NPE.
9. Trả `long`; `IntStream.mapToLong` cần `IntToLongFunction` còn `Stream<T>.mapToLong` cần `ToLongFunction<? super T>`.
10. `summaryStatistics()` tính nhiều thống kê trong một terminal operation, trong khi mỗi Stream chỉ tiêu thụ một lần.

## Kết luận

**`mapToInt()`, `mapToLong()` và `mapToDouble()`** là cầu nối từ `Stream<T>` sang ba loại **primitive stream**. Chúng cho phép biến đối tượng thành số theo function descriptor cụ thể rồi tiếp tục tính `sum`, `average`, `max`, `min` hoặc `summaryStatistics` mà không phải quay về wrapper không cần thiết.

Khi thiết kế pipeline, hãy chọn loại số theo phạm vi dữ liệu và nghiệp vụ, kiểm soát `null`/parse error, nhớ kiểm tra Optional khi nguồn rỗng, nâng kiểu trước phép toán có nguy cơ tràn và tách dữ liệu đo lường gần đúng khỏi phép tính tài chính đòi độ chính xác. Việc hiểu đúng cả **kiểu kết quả** và **ngữ nghĩa phép toán trong mapper** quan trọng hơn việc chỉ thay tên `map` thành `mapTo...`.
