# Ánh xạ bằng `mapToInt`, `mapToLong` và `mapToDouble`

Trong **Java Stream API**, `Stream<T>` xử lý các phần tử là đối tượng, còn `IntStream`, `LongStream` và `DoubleStream` được chuyên biệt hóa để xử lý ba kiểu nguyên thủy `int`, `long`, `double`. Khi dữ liệu ban đầu là đối tượng nhưng kết quả cần tính là số, `mapToInt`, `mapToLong` và `mapToDouble` là cầu nối giữa hai thế giới.

Đây là một phần của kỹ thuật xây dựng **pipeline lazy**: dùng các phép toán trung gian để mô tả cách trích xuất giá trị số, sau đó dùng phép toán kết thúc như `sum`, `average`, `min`, `max` hoặc `summaryStatistics` để tính toán. Chọn đúng kiểu stream giúp biểu đạt ý định, giảm nhu cầu boxing/unboxing và quản lý rõ ràng phạm vi giá trị cũng như sai số.

## 1. Ba phương thức chuyển từ `Stream<T>` sang stream nguyên thủy

| Phương thức gọi trên `Stream<T>` | Hàm đầu vào | Kiểu stream trả về | Tình huống thường gặp |
| --- | --- | --- | --- |
| `mapToInt(ToIntFunction<? super T>)` | `T → int` | `IntStream` | Độ dài chuỗi, tuổi, số lượng nhỏ. |
| `mapToLong(ToLongFunction<? super T>)` | `T → long` | `LongStream` | Số lượng lớn, thời gian dạng epoch, tổng vượt phạm vi `int`. |
| `mapToDouble(ToDoubleFunction<? super T>)` | `T → double` | `DoubleStream` | Phép đo, tỷ lệ, kết quả tính toán số thực. |

Ba functional interface `ToIntFunction`, `ToLongFunction` và `ToDoubleFunction` nằm trong `java.util.function`. Mỗi interface nhận một đối tượng `T` và trả về đúng kiểu nguyên thủy tương ứng, không phải `Integer`, `Long` hoặc `Double`.

Ví dụ ngắn nhất:

```java
import java.util.Arrays;
import java.util.List;

List<String> words = Arrays.asList("Java", "Stream", "API");

int totalCharacters = words.stream()
    .mapToInt(String::length)
    .sum();

System.out.println(totalCharacters); // 13 = 4 + 6 + 3
```

`String::length` đáp ứng `ToIntFunction<String>` vì nhận một `String` và trả `int`. Sau bước `mapToInt`, kiểu pipeline là **`IntStream`**, nên gọi trực tiếp `sum()` hoặc `average()` được.

### Khác gì `map` thông thường?

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;
import java.util.stream.IntStream;

List<String> words = Arrays.asList("Java", "Stream", "API");

Stream<Integer> boxedLengths = words.stream()
    .map(String::length);

IntStream primitiveLengths = words.stream()
    .mapToInt(String::length);

int total = primitiveLengths.sum(); // 13
int boxedTotal = boxedLengths.mapToInt(Integer::intValue).sum(); // 13
```

`map(String::length)` tạo `Stream<Integer>`: giá trị `int` từ `length()` được **boxing** thành đối tượng `Integer`. Trong khi đó, `mapToInt(String::length)` cho `IntStream` và tránh lớp đối tượng trung gian ấy. Kết quả cuối cùng trong ví dụ giống nhau, nhưng API được phép dùng ở các bước sau khác nhau.

Không thể gọi `sum()` trực tiếp trên `Stream<Integer>`, vì `Stream<T>` không có phương thức terminal `sum`. Có thể dùng `reduce(0, Integer::sum)` trên `Stream<Integer>`, nhưng thường nên dùng primitive stream nếu mục tiêu đơn thuần là tổng hợp số.

## 2. `mapToInt`: đếm, đo độ dài và thống kê số nguyên

`mapToInt` phù hợp khi giá trị tính ra nằm trong phạm vi của `int` (từ `-2_147_483_648` đến `2_147_483_647`) và các phép tính tiếp theo chấp nhận kiểu số nguyên 32 bit.

Ví dụ lấy độ dài chuỗi, chỉ giữ từ dài ít nhất bốn ký tự rồi tính trung bình:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.OptionalDouble;

List<String> words = Arrays.asList("Java", "API", "Stream", "Code");

OptionalDouble averageLength = words.stream()
    .mapToInt(String::length)
    .filter(length -> length >= 4)
    .average();

System.out.println(averageLength.orElse(0.0)); // 14 / 3 = 4.666...

IntSummaryStatistics stats = words.stream()
    .mapToInt(String::length)
    .summaryStatistics();

System.out.println(stats.getCount());   // 4
System.out.println(stats.getSum());     // 17
System.out.println(stats.getMin());     // 3
System.out.println(stats.getMax());     // 6
System.out.println(stats.getAverage()); // 4.25
```

`average()` trả `OptionalDouble` vì stream có thể rỗng; `min()` và `max()` trên `IntStream` trả `OptionalInt`. Với `summaryStatistics()`, các trường `count`, `sum`, `min`, `max`, `average` có trong một đối tượng. Trên stream rỗng, `getCount()` bằng 0; các giá trị của thống kê khác cần được diễn giải theo hợp đồng của lớp và yêu cầu nghiệp vụ, không nên coi min/max của tập rỗng là một quan sát thực tế.

### Đọc dữ liệu từ chuỗi

Trong dữ liệu nhập vào, số thường được lưu dạng văn bản. `mapToInt` có thể kết hợp trực tiếp với `Integer::parseInt`:

```java
import java.util.Arrays;

int[] numbers = Arrays.asList("10", "20", "30").stream()
    .mapToInt(Integer::parseInt)
    .toArray();

System.out.println(Arrays.toString(numbers)); // [10, 20, 30]
```

Ở đây, `parseInt` có thể ném `NumberFormatException` nếu văn bản không hợp lệ hoặc vượt phạm vi `int`. `mapToInt` **không** tự kiểm tra dữ liệu và cũng không tự bỏ qua chuỗi lỗi.

## 3. `mapToLong`: giảm rủi ro tràn `int` khi tổng hợp

Giá trị từng phần tử có thể vừa `int`, nhưng **tổng** của chúng vượt quá `int`. Khi đó, nên chuyển sang `LongStream` *trước khi thực hiện phép cộng*:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> views = Arrays.asList(1_500_000_000, 1_500_000_000);

long totalViews = views.stream()
    .mapToLong(Integer::longValue)
    .sum();

System.out.println(totalViews); // 3000000000
```

Nếu thay bằng `mapToInt(Integer::intValue).sum()`, tổng sử dụng `int` và bị tràn. `mapToLong` tránh tràn 32 bit, **nhưng `long` vẫn có giới hạn**: `LongStream.sum()` cũng có thể tràn khi tổng vượt phạm vi 64 bit.

Điều quan trọng không chỉ là kiểu của stream, mà còn là **thời điểm chuyển kiểu**:

```java
import java.util.stream.IntStream;

long correct = IntStream.of(50_000, 60_000)
    .mapToLong(n -> (long) n * n)
    .sum();

long wrong = IntStream.of(50_000, 60_000)
    .mapToLong(n -> n * n) // Nhân bằng int trước, có thể đã tràn!
    .sum();

System.out.println(correct); // 6100000000
System.out.println(wrong);   // Không phải 6100000000
```

Trong biểu thức `(long) n * n`, phép nhân dùng `long`. Trong `n * n`, phép nhân thực hiện bằng `int` rồi mới mở rộng kết quả đã tràn sang `long`.

Một tình huống thực tế là tính tổng doanh thu theo **đơn vị nhỏ nhất** của tiền (chẳng hạn số đồng hoặc số xu) để tránh việc dùng số thực trong phép tính tiền tệ:

```java
import java.util.Arrays;
import java.util.List;

final class OrderLine {
    final int quantity;
    final long unitPriceInMinorUnit;

    OrderLine(int quantity, long unitPriceInMinorUnit) {
        this.quantity = quantity;
        this.unitPriceInMinorUnit = unitPriceInMinorUnit;
    }
}

List<OrderLine> lines = Arrays.asList(
    new OrderLine(2, 15_000L),
    new OrderLine(3, 20_000L)
);

long totalMinorUnits = lines.stream()
    .mapToLong(line -> Math.multiplyExact(
        line.unitPriceInMinorUnit, (long) line.quantity
    ))
    .sum();

System.out.println(totalMinorUnits); // 90000
```

`Math.multiplyExact` ném `ArithmeticException` nếu **một phép nhân** tràn `long`. Nó không bảo vệ tổng từ `LongStream.sum()`; nếu tổng cũng có thể vượt `long`, cần cơ chế cộng có kiểm tra như `Math.addExact` (kèm hợp đồng reduction phù hợp) hoặc dùng `BigInteger` / `BigDecimal` theo bài toán. Khi cần phép tính thập phân tiền tệ, lựa chọn kiểu dữ liệu cần xuất phát từ đơn vị tiền, quy tắc làm tròn và giới hạn số.

## 4. `mapToDouble`: xử lý số thực và giá trị đo

`mapToDouble` trả về `DoubleStream` để tính trên `double`. Nó phù hợp với giá trị đo, điểm số có phần thập phân, xác suất hoặc phép tính xấp xỉ:

```java
import java.util.Arrays;
import java.util.DoubleSummaryStatistics;
import java.util.List;

List<String> measurements = Arrays.asList("1.25", "2.50", "3.75");

double total = measurements.stream()
    .mapToDouble(Double::parseDouble)
    .sum();

DoubleSummaryStatistics summary = measurements.stream()
    .mapToDouble(Double::parseDouble)
    .summaryStatistics();

System.out.println(total);                // 7.5
System.out.println(summary.getCount());   // 3
System.out.println(summary.getAverage()); // 2.5
```

Giống `mapToInt`, phép chuyển `Double::parseDouble` có thể ném ngoại lệ nếu dữ liệu không hợp lệ. `Double.parseDouble` cũng có thể chấp nhận các giá trị đặc biệt như `NaN` và `Infinity`; mô phỏng hoặc thống kê thường cần chính sách kiểm soát chúng.

### Lưu ý độ chính xác của `double`

`double` là số dấu phẩy động nhị phân, có giới hạn độ chính xác. Kết quả `0.1 + 0.2` không nhất thiết biểu diễn chính xác giá trị thập phân `0.3`. `DoubleStream.sum()` không làm cho số thực trở thành số thập phân chính xác.

```java
import java.util.stream.DoubleStream;

double result = DoubleStream.of(0.1, 0.2).sum();
System.out.println(result == 0.3); // Không nên dùng == để kiểm tra thuật toán số thực
System.out.println(Math.abs(result - 0.3) < 1e-12); // true
```

Ví dụ này minh họa cách so sánh bằng **ngưỡng sai số**. Ngưỡng phù hợp phải được chọn theo quy mô dữ liệu, tính chất phép toán và yêu cầu ứng dụng. Không mặc định `1e-12` phù hợp mọi bài toán.

Cần chú ý khi chuyển từ `long` sang `double`: mọi giá trị `int` đều biểu diễn chính xác bằng `double`, nhưng các `long` có độ lớn vượt quá giới hạn 53 bit của phần định trị có thể **mất thông tin nguyên**.

```java
import java.util.stream.LongStream;

long original = 9_007_199_254_740_993L; // 2^53 + 1
double converted = LongStream.of(original)
    .mapToDouble(value -> value)
    .findFirst()
    .orElseThrow(IllegalStateException::new);

System.out.println((long) converted == original); // false
```

Vì thế, đừng chuyển `long` chứa mã định danh, số đếm lớn hoặc số tiền chính xác sang `double` chỉ để dùng `average` mà không cân nhắc sai số. Nếu cần độ chính xác thập phân tuyệt đối, có thể dùng `BigDecimal` cùng `Stream<BigDecimal>`, chấp nhận chi phí đối tượng và quy tắc làm tròn phù hợp.

## 5. Chuyển đổi tiếp giữa ba primitive stream

Sau bước ánh xạ đầu tiên, ta đang làm việc với **primitive stream**, và các phương thức chuyển tiếp không hoàn toàn giống `Stream<T>`:

| Nguồn hiện tại | Phương thức chuyển | Kết quả |
| --- | --- | --- |
| `IntStream` | `mapToLong(IntToLongFunction)` | `LongStream` |
| `IntStream` | `mapToDouble(IntToDoubleFunction)` | `DoubleStream` |
| `LongStream` | `mapToInt(LongToIntFunction)` | `IntStream` |
| `LongStream` | `mapToDouble(LongToDoubleFunction)` | `DoubleStream` |
| `DoubleStream` | `mapToInt(DoubleToIntFunction)` | `IntStream` |
| `DoubleStream` | `mapToLong(DoubleToLongFunction)` | `LongStream` |
| `IntStream`, `LongStream`, `DoubleStream` | `mapToObj(...)` | `Stream<R>` |
| `IntStream`, `LongStream`, `DoubleStream` | `boxed()` | `Stream<Integer>`, `Stream<Long>`, `Stream<Double>` |

Với chuyển đổi mở rộng **không cần biến đổi logic**, `IntStream.asLongStream()`, `IntStream.asDoubleStream()` và `LongStream.asDoubleStream()` diễn đạt rõ hơn `mapToLong(n -> n)` hoặc `mapToDouble(n -> n)`.

```java
import java.util.stream.IntStream;

long sumAsLong = IntStream.rangeClosed(1, 100_000)
    .asLongStream()
    .sum();

double mean = IntStream.rangeClosed(1, 5)
    .asDoubleStream()
    .average()
    .orElseThrow(IllegalStateException::new);

System.out.println(sumAsLong); // 5000050000
System.out.println(mean);      // 3.0
```

Lưu ý `asLongStream` chỉ mở rộng **từng phần tử** sang `long`; nó không thay đổi kết quả phép toán số nguyên nếu bạn đã tính toán và tràn trước bước chuyển.

### Thu hẹp `long` hoặc `double` sang `int` cần có chủ đích

Các phương thức `mapToInt` cũng cho phép viết biểu thức ép kiểu. Tuy nhiên, từ `long` sang `int` có thể mất các bit cao; từ `double` sang `int` làm mất phần thập phân, `NaN` được chuyển thành 0 và giá trị ngoài phạm vi có thể bị chặn về giới hạn đầu mút theo quy tắc của Java.

```java
import java.util.Arrays;
import java.util.stream.DoubleStream;

int[] truncated = DoubleStream.of(2.9, -2.9, 5.0)
    .mapToInt(x -> (int) x)
    .toArray();

System.out.println(Arrays.toString(truncated)); // [2, -2, 5]
```

Ép kiểu `(int) x` **cắt phần thập phân về phía 0**, không làm tròn đến số nguyên gần nhất. Nếu nghiệp vụ yêu cầu làm tròn, cần chọn rõ quy tắc như `Math.round` (trả về `long` đối với `double`), đồng thời xử lý biên và tràn kiểu khi cần chuyển tiếp.

### Chuyển trở lại object stream

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;

List<String> labels = IntStream.rangeClosed(1, 3)
    .mapToObj(n -> "item-" + n)
    .collect(java.util.stream.Collectors.toList());

List<Integer> boxed = IntStream.of(4, 5, 6)
    .boxed()
    .collect(java.util.stream.Collectors.toList());

System.out.println(labels); // [item-1, item-2, item-3]
System.out.println(boxed);  // [4, 5, 6]
```

`mapToObj` tạo đối tượng mới theo quy tắc, còn `boxed` chỉ bọc các số nguyên thủy vào wrapper tương ứng. Dùng `boxed` khi API tiếp theo cần `Stream<Integer>` hoặc một `Collector` nhận đối tượng; tránh boxing nếu phần sau chỉ tính số.

## 6. Một phần tử thành một số: `mapTo*` khác `flatMapTo*`

`mapToInt`, `mapToLong` và `mapToDouble` luôn ánh xạ **một phần tử đầu vào sang một giá trị số**. Nếu một phần tử đầu vào có thể tạo **nhiều** số (hoặc không có số nào), dùng `flatMapToInt`, `flatMapToLong` hoặc `flatMapToDouble`.

```java
import java.util.Arrays;
import java.util.List;

List<int[]> batches = Arrays.asList(
    new int[] {2, 4},
    new int[] {7},
    new int[] {1, 3, 5}
);

int[] batchSizes = batches.stream()
    .mapToInt(batch -> batch.length)
    .toArray();

int[] allValues = batches.stream()
    .flatMapToInt(Arrays::stream)
    .toArray();

System.out.println(Arrays.toString(batchSizes)); // [2, 1, 3]
System.out.println(Arrays.toString(allValues));  // [2, 4, 7, 1, 3, 5]
```

`mapToInt(batch -> batch.length)` lấy **một kích thước cho mỗi mảng**. `flatMapToInt(Arrays::stream)` trải các mảng thành **một dãy số duy nhất**. Chọn phương thức theo hình dạng dữ liệu đầu ra, không chỉ theo kiểu primitive mong muốn.

## 7. Tính lazy, lọc dữ liệu và xử lý lỗi

`mapTo*` là **phép toán trung gian**: chỉ định cách tạo số, chưa thực thi ngay toàn bộ việc chuyển đổi. Pipeline bắt đầu duyệt khi có terminal operation.

```java
import java.util.Arrays;
import java.util.List;

List<String> raw = Arrays.asList(" 10 ", "", "20", "  ");

long total = raw.stream()
    .map(String::trim)
    .filter(text -> !text.isEmpty())
    .mapToLong(Long::parseLong)
    .sum();

System.out.println(total); // 30
```

Điều kiện `filter` loại chuỗi rỗng trước `mapToLong`, nhưng chưa xử lý chuỗi như `"N/A"` hoặc số vượt `long`. Một luồng nhập liệu nghiêm túc nên xác định trước chính sách cho dữ liệu sai: báo lỗi, lưu danh sách bản ghi lỗi, hoặc loại bỏ có ghi nhận. Không nên bắt mọi `NumberFormatException` rồi thay bằng 0 nếu **0 là giá trị có ý nghĩa nghiệp vụ**, vì điều đó làm kết quả thống kê bị sai khó phát hiện.

### Giá trị `null` và unboxing

```java
import java.util.Arrays;
import java.util.Objects;

long total = Arrays.asList(10, null, 20).stream()
    .filter(Objects::nonNull)
    .mapToLong(Integer::longValue)
    .sum();

System.out.println(total); // 30
```

Nếu dùng `Integer::intValue` hoặc `Integer::longValue` trên `null`, lambda sẽ ném `NullPointerException`. Primitive stream không có phần tử `null`; phải quyết định có bỏ, thay thế, hay từ chối giá trị thiếu **trước khi** chuyển kiểu.

Các terminal operation có khả năng ngắn mạch như `findFirst`, `findAny`, `anyMatch` hoặc việc giới hạn bằng `limit` có thể khiến chỉ một phần nguồn được xử lý. Vì thế không dùng lambda của `mapTo*` để thực hiện hiệu ứng phụ phải chạy với mọi phần tử, như cập nhật sổ giao dịch.

## 8. Song song và hiệu năng: lợi ích có điều kiện

Primitive stream thường tránh được boxing/unboxing và giảm lượng đối tượng tạm khi dữ liệu là số. Điều đó **không tự bảo đảm** rằng mọi pipeline primitive đều nhanh hơn: hiệu năng còn phụ thuộc nguồn, chi phí ánh xạ, độ lớn dữ liệu, số lần phân bổ, tối ưu của JVM và bộ lập lịch song song.

```java
import java.util.stream.IntStream;

long sumOfSquares = IntStream.rangeClosed(1, 100_000)
    .parallel()
    .mapToLong(n -> (long) n * n)
    .sum();

System.out.println(sumOfSquares); // 333338333350000
```

Trong ví dụ này, hàm ánh xạ chỉ phụ thuộc vào tham số `n`; từng phần tử có thể tính độc lập. Phép cộng `long` kết hợp các phần tử cho kết quả xác định **khi tổng không tràn**. Tuy nhiên, `parallel()` có chi phí chia việc và gộp kết quả; với nguồn nhỏ, tuần tự có thể nhanh hơn.

Để kết quả đúng và dễ dự đoán:

1. Giữ hàm ánh xạ **không can thiệp vào nguồn** (*non-interfering*) và **không dùng trạng thái chia sẻ có thể thay đổi** (*stateless*) khi có thể.
2. Không thay đổi collection nguồn trong lúc pipeline đang duyệt.
3. Không dùng `peek`, `mapToInt` hay `mapToDouble` để tăng một biến đếm dùng chung rồi xem nó là kết quả chính.
4. Khi dùng `reduce` tự viết, chọn phép kết hợp và phần tử đơn vị đúng hợp đồng; phép trừ không phải ví dụ phù hợp cho reduction song song.
5. Với `DoubleStream`, chấp nhận rằng kết quả số thực có thể khác rất nhỏ theo thứ tự và cách gộp phần tử. Khi tính tài chính cần độ chính xác, cân nhắc mô hình số khác.

## 9. Chọn phương thức theo ý định

| Nhu cầu | Pipeline đề xuất | Điểm cần kiểm tra |
| --- | --- | --- |
| Tổng độ dài các chuỗi | `stream.mapToInt(String::length).sum()` | Tổng có vượt `int` không? |
| Tổng lượng truy cập rất lớn | `stream.mapToLong(Integer::longValue).sum()` | Có phải chuyển sang `long` **trước** phép cộng không? |
| Trung bình giá trị đo | `stream.mapToDouble(...).average()` | `OptionalDouble` rỗng, `NaN`, sai số. |
| Thống kê min/max/count/sum/average | `mapToInt(...).summaryStatistics()` hoặc kiểu tương ứng | Dữ liệu rỗng và phạm vi kiểu số. |
| Chuyển `IntStream` thành `LongStream` đơn thuần | `intStream.asLongStream()` | Có bước tính toán nào đã tràn trước đó không? |
| Tạo chuỗi nhãn từ số | `intStream.mapToObj(...)` | Cần stream đối tượng, không phải primitive. |
| Gộp nhiều mảng `int[]` | `stream.flatMapToInt(Arrays::stream)` | Một nguồn có thể sinh nhiều phần tử. |
| Tập hợp các giá trị nguyên thành `List<Integer>` | `intStream.boxed().collect(...)` | Chấp nhận chi phí boxing khi cần collection đối tượng. |

### Bài tập thực hành

**Bài 1.** Cho `List<String> texts = Arrays.asList("A", "Java", "Stream")`. Dùng `mapToInt` lấy độ dài, sau đó tính tổng và trung bình. Dự đoán kết quả **11** và **11 / 3.0**. Giải thích vì sao `average` trả `OptionalDouble`.

**Bài 2.** Cho `List<Integer> quantities = Arrays.asList(2_000_000_000, 2_000_000_000)`. Tính tổng bằng `mapToLong`, so sánh với `mapToInt`. Vì sao chuyển sang `long` *sau khi* đã gọi `IntStream.sum()` không sửa được kết quả tràn?

**Bài 3.** Cho các số thực `2.2`, `-2.2`, `5.9`. Dùng `DoubleStream.mapToInt(x -> (int) x)` rồi in mảng. So sánh với việc dùng `Math.round` và lý giải vì sao hai thao tác có ngữ nghĩa khác nhau.

**Bài 4.** Cho `List<int[]>` gồm `[1, 2]`, `[]`, `[3, 4, 5]`. Dùng `mapToInt` để lấy kích thước mỗi mảng, sau đó dùng `flatMapToInt` để gom toàn bộ số thành một `IntStream`. Dự đoán kết quả của mỗi pipeline.

**Ghi nhớ:** `mapToInt`, `mapToLong`, `mapToDouble` chuyển các đối tượng đầu vào thành phần tử số nguyên thủy để tiếp tục xử lý bằng `IntStream`, `LongStream`, `DoubleStream`. Chọn kiểu theo **phạm vi giá trị và phép tính tiếp theo**, xử lý dữ liệu thiếu hoặc lỗi trước khi chuyển, chú ý tràn số nguyên và sai số số thực, rồi mới cân nhắc tối ưu hiệu năng hoặc chạy song song.
