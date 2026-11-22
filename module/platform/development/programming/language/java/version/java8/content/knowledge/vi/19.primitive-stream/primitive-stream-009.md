# Lựa chọn primitive stream theo dữ liệu nguồn trong Java

## 1. Mục tiêu

Java Stream API có ba **primitive stream** chuyên biệt để xử lý giá trị số nguyên thủy:

- `IntStream` — các phần tử kiểu `int`.
- `LongStream` — các phần tử kiểu `long`.
- `DoubleStream` — các phần tử kiểu `double`.

Chúng tồn tại từ Java 8 và vẫn được hỗ trợ trong Java hiện đại. Khi nguồn dữ liệu hoặc phép tính chủ yếu là số nguyên thủy, các stream chuyên biệt thường giúp giảm **boxing/unboxing** so với `Stream<Integer>`, `Stream<Long>`, `Stream<Double>`; đồng thời cung cấp sẵn `sum()`, `average()`, `summaryStatistics()`, `min()`, `max()` và `range(...)` ở những kiểu thích hợp.

**Nguyên tắc chọn:** Bắt đầu từ **kiểu dữ liệu thật của nguồn** và **miền giá trị đầu ra cần tính**, sau đó chọn stream có biểu diễn và các phép tính phù hợp. Không chọn `IntStream` cho mọi số chỉ vì nó có cú pháp ngắn; không chuyển mọi dữ liệu sang `DoubleStream` chỉ để lấy trung bình; không thay `BigDecimal` bằng `double` khi cần số thập phân chính xác.

| Nguồn dữ liệu / yêu cầu | Nên dùng | Cách bắt đầu điển hình | Lý do |
| --- | --- | --- | --- |
| Mảng `int[]` | `IntStream` | `Arrays.stream(ints)` | Không boxing phần tử của mảng |
| Mảng `long[]` | `LongStream` | `Arrays.stream(longs)` | Bảo toàn giá trị trong miền `long` |
| Mảng `double[]` | `DoubleStream` | `Arrays.stream(doubles)` | Tính toán số thực `double` |
| `List<Integer>`, không có null | `IntStream` nếu chủ yếu tính số | `list.stream().mapToInt(Integer::intValue)` | Unbox tại ranh giới |
| `List<Long>`, không có null | `LongStream` | `list.stream().mapToLong(Long::longValue)` | Giữ nguyên độ rộng `long` |
| `List<Double>`, không có null | `DoubleStream` | `list.stream().mapToDouble(Double::doubleValue)` | Tính toán kiểu `double` |
| Danh sách đối tượng có trường `int`, `long`, `double` | Chọn stream theo trường cần lấy | `orders.stream().mapToLong(Order::cents)` | Tính toán trên trường số |
| Chuỗi số cần parse | `Stream<String>` rồi `mapToInt`/`mapToLong`/`mapToDouble` | `tokens.stream().mapToInt(Integer::parseInt)` | Tách bước chuyển kiểu khỏi nguồn |
| Dãy chỉ số liên tiếp | `IntStream` hoặc `LongStream` | `IntStream.range(0, n)` | Không cần tạo mảng hay danh sách |
| Số tiền thập phân chính xác hoặc số lớn tùy ý | `Stream<BigDecimal>` / `Stream<BigInteger>` | `amounts.stream()` | Không có primitive stream tương ứng |
| Dữ liệu dạng văn bản cần thao tác ở cấp đối tượng | `Stream<String>` | `names.stream()` | Primitive stream không thay thế được loại dữ liệu tham chiếu |

Bài này sử dụng các API hiện hành; những ví dụ hoàn chỉnh dùng **Java 17+** (vì dùng `record`, có trong Java hiện đại). Các primitive stream và phần lớn phép chuyển đổi cốt lõi đã có từ Java 8.

## 2. Vì sao `Stream<Integer>` không tương đương về hiệu năng với `IntStream`?

`Stream<Integer>` chứa **tham chiếu đến các đối tượng `Integer`**; `IntStream` chứa các giá trị primitive `int` dưới góc nhìn API. Với phép cộng hoặc tính trung bình nhiều phần tử, `IntStream` có thể tránh lượng boxing/unboxing trung gian không cần thiết.

Ví dụ:

```java
List<Integer> values = List.of(2, 3, 5);

// Stream<Integer>: dùng boxing qua kiểu Integer.
int first = values.stream().reduce(0, Integer::sum);

// IntStream: sau ranh giới unboxing, xử lý kiểu int.
int second = values.stream().mapToInt(Integer::intValue).sum();
```

Hai cách trên đều trả `10` trong ví dụ. Đoạn mã giả định `List` đã được import và dùng Java 17+. Với một số trường hợp đơn giản, việc đổi sang primitive không bảo đảm nhanh hơn trên mọi JVM/dữ liệu: đo bằng benchmark phù hợp khi hiệu năng quan trọng.

**Giới hạn quan trọng:** Dù nguồn dùng `int`, **kết quả của phép cộng có thể vượt `int`**. `IntStream.sum()` trả `int`, không tự tăng lên `long`. Khi tổng cần độ rộng lớn hơn, chuyển sớm sang `LongStream` rồi tính:

```java
long correct = java.util.stream.IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum();
// 2147483648L
```

Không dùng `IntStream.sum()` nếu cần tổng toán học vượt miền `int`. Ngược lại, `LongStream.sum()` vẫn có thể tràn `long` với dữ liệu đủ lớn; lúc đó cân nhắc `Math.addExact`, `BigInteger` hoặc chính sách nghiệp vụ phù hợp.

## 3. Nguồn là mảng số nguyên thủy: dùng `Arrays.stream` / `XxxStream.of`

Với mảng `int[]`, `long[]` và `double[]`, `java.util.Arrays.stream` có overload tương ứng trả primitive stream:

```java
int[] quantities = {2, 3, 5};
long[] visitCounts = {2_000_000_000L, 3_000_000_000L};
double[] weights = {1.25, 2.50, 3.75};

int totalQuantity = Arrays.stream(quantities).sum();        // 10
long totalVisits = Arrays.stream(visitCounts).sum();        // 5_000_000_000L
double totalWeight = Arrays.stream(weights).sum();          // 7.5
```

Đây là đoạn minh họa cần `import java.util.Arrays;` trong một chương trình Java.

Các lựa chọn tương đương khi có sẵn giá trị:

```java
IntStream numbers = IntStream.of(2, 3, 5);
LongStream visits = LongStream.of(2_000_000_000L, 3_000_000_000L);
DoubleStream measures = DoubleStream.of(1.25, 2.5, 3.75);
```

Đây là đoạn khai báo minh họa; cần import `java.util.stream.*`. Một đối tượng Stream chỉ tiêu thụ **một lần**, nên hãy tạo lại Stream cho mỗi phép tính hoặc mỗi assertion.

**Lỗi dễ mắc khi dùng `Stream.of` với mảng nguyên thủy:**

```java
int[] source = {10, 20, 30};

long wrongCount = Stream.of(source).count();   // 1, vì đây là Stream<int[]>
long rightCount = Arrays.stream(source).count(); // 3
```

`Stream.of(source)` nhìn cả mảng `int[]` là **một phần tử object**, vì kiểu `int[]` không phải `Integer[]`. Nó không trải ra thành ba số. Chọn `Arrays.stream(source)` hoặc `IntStream.of(source)`.

`Arrays.stream(ints, fromInclusive, toExclusive)` còn cho phép chỉ lấy một đoạn của mảng. Java kiểm tra chỉ số đoạn; không tự âm thầm sửa phạm vi sai.

Với `byte[]`, `short[]` hoặc `char[]` **không có** overload `Arrays.stream(...)` tương ứng trả `ByteStream`, `ShortStream` hay `CharStream`. Java chỉ định nghĩa ba primitive stream `int`, `long`, `double`. Khi cần xử lý các mảng khác, có thể tạo `IntStream.range(0, array.length)` rồi `map(i -> array[i])`; với `byte` cần xác định muốn hiểu giá trị signed hay unsigned (ví dụ `Byte.toUnsignedInt`).

## 4. Nguồn là collection của wrapper: chuyển ở ranh giới rõ ràng

Java collections như `List<Integer>`, `Set<Long>` giữ đối tượng wrapper vì generic Java không dùng primitive làm type argument. Khi cần xử lý số, chuyển bằng method phù hợp:

```java
List<Integer> ages = List.of(18, 20, 21);
int ageSum = ages.stream().mapToInt(Integer::intValue).sum(); // 59

List<Long> bytesByFile = List.of(1_000L, 2_000L);
long totalBytes = bytesByFile.stream()
        .mapToLong(Long::longValue).sum(); // 3000

List<Double> measurements = List.of(1.5, 2.5);
double mean = measurements.stream()
        .mapToDouble(Double::doubleValue)
        .average()
        .orElseThrow(); // 2.0
```

Đoạn minh họa cần `import java.util.*;` và dùng Java 17+.

Các API tương ứng trên `Stream<T>`:

| Phương thức | Kiểu trả về | Khi nên dùng |
| --- | --- | --- |
| `mapToInt(ToIntFunction<? super T>)` | `IntStream` | Trường số nguyên `int`, số lượng, điểm |
| `mapToLong(ToLongFunction<? super T>)` | `LongStream` | Giá trị `long`, thời lượng, kích thước, tổng có thể lớn |
| `mapToDouble(ToDoubleFunction<? super T>)` | `DoubleStream` | Đại lượng số thực và xử lý xấp xỉ |

**Chú ý null:** `List.of(...)` từ Java 9 không cho chứa null; tuy nhiên nhiều collection khác có thể chứa `null`. `Integer::intValue`, `Long::longValue` hay `Double::doubleValue` sẽ gây `NullPointerException` khi gặp phần tử null. Đừng tự bỏ qua null nếu nó có nghĩa nghiệp vụ. Xác định một trong ba chính sách: từ chối dữ liệu, bỏ qua có chủ đích, hoặc quy đổi thành giá trị thay thế có ghi rõ.

Ví dụ **bỏ qua null theo chính sách đã chọn**:

```java
List<Integer> nullable = Arrays.asList(2, null, 3);

int total = nullable.stream()
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum(); // 5
```

Nếu null có nghĩa “chưa nhập” hoặc “dữ liệu lỗi”, nên báo lỗi hay thống kê thiếu dữ liệu trước khi tính. `filter(Objects::nonNull)` không phải giải pháp mặc định cho mọi trường hợp.

## 5. Nguồn là đối tượng nghiệp vụ: chọn theo trường và miền kết quả

Ví dụ danh sách `Order` gồm giá đơn vị theo **cent** (kiểu `long`) và số lượng (kiểu `int`). Cần tính tổng tiền:

```java
record Order(long unitPriceCents, int quantity) {}

List<Order> orders = List.of(
        new Order(1500L, 2),
        new Order(250L, 4)
);

long totalCents = orders.stream()
        .mapToLong(o -> Math.multiplyExact(
                o.unitPriceCents(), (long) o.quantity()))
        .reduce(0L, Math::addExact);
// 4000L
```

Đây là **đoạn trích có thể đưa vào một chương trình Java 17+** với import tương ứng. `Order` là Java record. Chọn `LongStream` vì miền kết quả là số nguyên `long` (cent), trong khi `int` có thể thiếu độ rộng nếu lượng giao dịch lớn.

`Math.multiplyExact` và `Math.addExact` phát hiện tràn kiểu `long` bằng `ArithmeticException`; nếu dự án cần xử lý tổng vượt phạm vi `long`, hãy dùng mô hình số lớn phù hợp. Khi miền dữ liệu cần số thập phân chính xác thay vì cent nguyên, chọn `BigDecimal` và `Stream<BigDecimal>`.

Một số lựa chọn theo kiểu trường:

```java
int itemCount = orders.stream()
        .mapToInt(Order::quantity)
        .sum();

long amountCents = orders.stream()
        .mapToLong(Order::unitPriceCents)
        .sum();
```

Hai biểu thức minh họa này tính **hai chỉ số khác nhau**: tổng số lượng và tổng **giá đơn vị**, không phải tổng giá trị đơn hàng. Đừng chọn `mapToLong(Order::unitPriceCents).sum()` để tính doanh thu khi còn phải nhân số lượng.

Khi dữ liệu đầu vào là `Map<K, Integer>`, có thể duyệt `entrySet().stream().mapToInt(Map.Entry::getValue)` để lấy các giá trị; cách unbox qua return `Integer` cần chính sách null giống collection.

## 6. Nguồn là dải số: `range` và `rangeClosed`

Nếu muốn tạo số tăng liên tiếp mà không có sẵn collection, dùng factory:

```java
int sum1To4 = IntStream.range(1, 5).sum();      // 1+2+3+4 = 10
int sum1To5 = IntStream.rangeClosed(1, 5).sum(); // 1+2+3+4+5 = 15

long count = LongStream.range(0, 1_000_000L).count(); // 1_000_000L
```

| API | Biên đầu | Biên cuối | Ví dụ đầu vào |
| --- | --- | --- | --- |
| `IntStream.range(a, b)` | Bao gồm `a` | Không bao gồm `b` | `range(1, 5)` cho `1,2,3,4` |
| `IntStream.rangeClosed(a, b)` | Bao gồm `a` | Bao gồm `b` | `rangeClosed(1, 5)` cho `1,2,3,4,5` |
| `LongStream.range(a, b)` | Bao gồm `a` | Không bao gồm `b` | Khi biên hoặc miền chỉ số cần `long` |
| `LongStream.rangeClosed(a, b)` | Bao gồm cả hai | Bao gồm cả hai | Dải `long` khép kín |

**Không có** `DoubleStream.range(...)` tiêu chuẩn: dãy số thực với bước tùy ý dễ gặp vấn đề về làm tròn. Khi thực sự cần chỉ số để tính số thực, tạo `IntStream.range(...)` rồi `mapToDouble(i -> ...)`, đồng thời quy định rõ độ chính xác và giới hạn.

Đối với nguồn kích thước rất lớn, chọn `LongStream.range` khi biên vượt `int`. Tránh dùng dải vô hạn hoặc `iterate` không có điều kiện dừng nếu phép tính cần kết thúc; `range`/`rangeClosed` hữu hạn và rõ ranh giới hơn. Đừng tự động chọn parallel cho dải nhỏ: chi phí chia việc có thể lớn hơn lợi ích.

## 7. Văn bản và dữ liệu chuyển đổi: parse sau khi xác thực

Khi dữ liệu đến từ chuỗi, file CSV hoặc một nguồn ngoại vi, ban đầu các phần tử thường là `String`. Hãy kiểm tra/chuẩn hóa theo quy tắc nghiệp vụ, rồi chuyển sang primitive:

```java
List<String> quantities = List.of("2", "10", "5");

int total = quantities.stream()
        .map(String::trim)
        .mapToInt(Integer::parseInt)
        .sum(); // 17
```

- `Integer.parseInt` ném `NumberFormatException` nếu không thể parse số nguyên trong phạm vi `int`.
- Nếu giá trị cần `long`, dùng `Long.parseLong` và `mapToLong`.
- Nếu là số thực xấp xỉ, dùng `Double.parseDouble` và `mapToDouble`, nhưng xem xét xử lý `NaN` / `Infinity` và định dạng đầu vào.
- Nếu dữ liệu là tiền thập phân cần độ chính xác, dùng `new BigDecimal(String)` và `Stream<BigDecimal>`.

**Đừng dùng `filter(...)` đơn giản để “lọc sạch lỗi parse”** nếu loại bỏ dữ liệu ảnh hưởng tổng hoặc tỷ lệ. Với dữ liệu sản xuất, lỗi thường cần được ghi nhận cùng vị trí và giá trị đầu vào, hoặc toàn bộ batch phải thất bại theo hợp đồng.

Nếu đọc từ `Files.lines(...)`, đây là Stream gắn với tài nguyên I/O: dùng **try-with-resources** để đóng tệp khi hoàn tất. Chỉ chọn `mapTo...` sau khi đã giải quyết việc phân tách, định dạng, encoding và chính sách lỗi.

### Văn bản Unicode: `String.chars()` và `String.codePoints()`

Hai phương thức này đều trả `IntStream`, nhưng **không biểu diễn cùng một đơn vị**:

- `String.chars()` cho các **đơn vị UTF-16 `char`**, có thể bao gồm các surrogate của cùng một Unicode code point.
- `String.codePoints()` cho **Unicode code points**; cặp surrogate hợp lệ được gộp thành một phần tử `int`.

Ví dụ Java 17+ (tạo ký tự bổ sung bằng mã để tránh vấn đề font/encoding):

```java
String text = "A" + new String(Character.toChars(0x1F33F)) + "B";

long codePointCount = text.codePoints().count(); // 3
long utf16UnitCount = text.chars().count();       // 4
```

`0x1F33F` là Unicode code point của ký tự 🌿. Code point count **không** đồng nghĩa với số grapheme clusters (ký tự mà người dùng nhìn thấy) trong mọi chuỗi; tổ hợp dấu/emoji nối vẫn có thể gồm nhiều code point. Chọn cách xử lý dựa trên yêu cầu text, không chỉ tên `IntStream`.

## 8. Chuyển giữa primitive stream và object stream khi cần thiết

| Chuyển đổi | API hiện hành | Kết quả |
| --- | --- | --- |
| `Stream<Integer>` → `IntStream` | `mapToInt(Integer::intValue)` | Giá trị `int` |
| `Stream<Long>` → `LongStream` | `mapToLong(Long::longValue)` | Giá trị `long` |
| `Stream<Double>` → `DoubleStream` | `mapToDouble(Double::doubleValue)` | Giá trị `double` |
| `IntStream` → `LongStream` | `asLongStream()` | Mở rộng `int` thành `long` không mất thông tin |
| `IntStream` → `DoubleStream` | `asDoubleStream()` | Mọi `int` đều biểu diễn chính xác trong `double` |
| `LongStream` → `DoubleStream` | `asDoubleStream()` | Có thể mất độ chính xác với số nguyên lớn |
| `IntStream` → `Stream<Integer>` | `boxed()` | Boxing, dùng khi API cần object |
| `LongStream` → `Stream<Long>` | `boxed()` | Boxing |
| `DoubleStream` → `Stream<Double>` | `boxed()` | Boxing |
| `IntStream` → `Stream<R>` | `mapToObj(intFunction)` | Tạo đối tượng từ từng `int` |

Ví dụ:

```java
List<Integer> sorted = IntStream.of(3, 1, 2)
        .boxed()
        .sorted()
        .toList(); // [1, 2, 3]

List<String> labels = IntStream.rangeClosed(1, 3)
        .mapToObj(i -> "item-" + i)
        .toList(); // [item-1, item-2, item-3]
```

`Stream.toList()` có từ Java 16 và trả List không sửa được. Dùng `boxed()` khi cần truyền vào API yêu cầu `Stream<Integer>`, lấy `List<Integer>`, hoặc collector hoạt động trên đối tượng; tránh boxing trở lại quá sớm nếu đang làm phép toán số.

**Cảnh báo `long` → `double`:** `double` có 53 bit độ chính xác cho phần trị; một số `long` lớn không thể biểu diễn chính xác. Do vậy không chuyển ID, tiền, bộ đếm lớn hoặc timestamp sang `double` nếu cần bảo toàn từng đơn vị.

**Về collector:** `IntStream`, `LongStream`, `DoubleStream` có overload `collect(supplier, accumulator, combiner)` với functional interface cho primitive, chứ không gọi trực tiếp `collect(Collector<T,A,R>)` của `Stream<T>`. Nếu cần một `Collector<Integer,...>` chỉ hoạt động với object, có thể `boxed()` ở ranh giới rõ ràng; còn tính tổng, thống kê thông thường có phương thức nguyên thủy sẵn.

## 9. Chọn thao tác kết thúc phù hợp với ý nghĩa dữ liệu

Primitive streams có nhiều terminal operations:

| Nhu cầu | IntStream | LongStream | DoubleStream |
| --- | --- | --- | --- |
| Tổng | `sum(): int` | `sum(): long` | `sum(): double` |
| Trung bình | `average(): OptionalDouble` | `average(): OptionalDouble` | `average(): OptionalDouble` |
| Nhỏ nhất / lớn nhất | `OptionalInt` | `OptionalLong` | `OptionalDouble` |
| Đếm phần tử | `count(): long` | `count(): long` | `count(): long` |
| Thống kê tổng hợp | `IntSummaryStatistics` | `LongSummaryStatistics` | `DoubleSummaryStatistics` |
| Đưa ra mảng nguyên thủy | `toArray(): int[]` | `toArray(): long[]` | `toArray(): double[]` |

**Nguồn rỗng:**

```java
int total = IntStream.empty().sum();                // 0
long count = IntStream.empty().count();             // 0L
boolean noAverage = IntStream.empty().average().isEmpty(); // true
boolean noMax = IntStream.empty().max().isEmpty();         // true
```

`OptionalInt`, `OptionalLong`, `OptionalDouble` biểu diễn “có hoặc không có giá trị” **không cần boxing**. `average()` của cả ba primitive stream trả `OptionalDouble`, kể cả đầu vào toàn số nguyên, vì trung bình có thể không nguyên.

Đối với dữ liệu thực, không nên tự động dùng `orElse(0)` cho trung bình rỗng nếu “không có dữ liệu” khác “trung bình bằng 0”. Dùng `isPresent()`, `orElseThrow(...)` hoặc một giá trị đại diện theo hợp đồng ứng dụng.

`summaryStatistics()` tiện khi cùng một pipeline cần count/sum/min/max/average. Khi số lượng bằng 0, không suy diễn `getMin()`/`getMax()` là số đo hợp lệ: kiểm tra `getCount() > 0` trước khi diễn giải cực trị.

## 10. Chương trình Java 17+ hoàn chỉnh

Tạo tệp **`PrimitiveChoiceDemo.java`**:

```java
import java.util.*;
import java.util.stream.*;
import java.math.*;

public class PrimitiveChoiceDemo {
    record Order(long unitPriceCents, int quantity) {}

    public static void main(String[] args) {
        // Mảng primitive: chọn stream cùng kiểu phần tử.
        int[] scores = {70, 85, 95};
        long[] visits = {2_000_000_000L, 3_000_000_000L};
        double[] measurements = {1.25, 2.50, 3.75};

        System.out.println("scoreSum=" + Arrays.stream(scores).sum());
        System.out.printf(Locale.ROOT, "scoreAverage=%.2f%n",
                Arrays.stream(scores).average().orElseThrow());
        System.out.println("visitSum=" + Arrays.stream(visits).sum());
        System.out.println("measurementSum=" + Arrays.stream(measurements).sum());

        // Collection của Integer: unboxing đúng một lần ở đầu pipeline số.
        List<Integer> ages = List.of(18, 20, 21);
        System.out.println("ageSum=" +
                ages.stream().mapToInt(Integer::intValue).sum());

        // Object nguồn có trường số long: chuyển theo miền tổng cần tính.
        List<Order> orders = List.of(
                new Order(1500, 2),
                new Order(250, 4)
        );
        long totalCents = orders.stream()
                .mapToLong(o -> Math.multiplyExact(
                        o.unitPriceCents(), (long) o.quantity()))
                .reduce(0L, Math::addExact);
        System.out.println("totalCents=" + totalCents);

        // Sinh dải số và boxing lại chỉ khi đầu ra cần List<Integer>.
        System.out.println("rangeSum=" + IntStream.range(1, 5).sum());
        System.out.println("boxed=" +
                IntStream.of(3, 1, 2).boxed().sorted().toList());

        // Stream.of(int[]) chỉ tạo 1 phần tử kiểu int[].
        System.out.println("arrayWrappedCount=" + Stream.of(scores).count());

        // Code point khác đơn vị UTF-16.
        String text = "A" + new String(Character.toChars(0x1F33F)) + "B";
        System.out.println("codePoints=" + text.codePoints().count());
        System.out.println("utf16Units=" + text.chars().count());

        // Null trong wrapper collection: chỉ bỏ qua vì ví dụ chọn chính sách này.
        List<Integer> nullable = Arrays.asList(2, null, 3);
        System.out.println("filteredNullSum=" + nullable.stream()
                .filter(Objects::nonNull)
                .mapToInt(Integer::intValue)
                .sum());

        // Widen int -> long trước khi cộng để không tràn int.
        System.out.println("widenedSum=" +
                IntStream.of(Integer.MAX_VALUE, 1).asLongStream().sum());
        System.out.println("emptyAverage=" +
                IntStream.empty().average().isEmpty());

        // Số thập phân chính xác: dùng Stream<BigDecimal>.
        System.out.println("decimalExact=" +
                Stream.of("0.10", "0.20")
                        .map(BigDecimal::new)
                        .reduce(BigDecimal.ZERO, BigDecimal::add));
    }
}
```

Biên dịch, chạy bằng JDK 17 trở lên:

```bash
javac PrimitiveChoiceDemo.java
java PrimitiveChoiceDemo
```

Đầu ra chuẩn:

```text
scoreSum=250
scoreAverage=83.33
visitSum=5000000000
measurementSum=7.5
ageSum=59
totalCents=4000
rangeSum=10
boxed=[1, 2, 3]
arrayWrappedCount=1
codePoints=3
utf16Units=4
filteredNullSum=5
widenedSum=2147483648
emptyAverage=true
decimalExact=0.30
```

Giải thích kiểm chứng:

1. Mảng `int[]` cho tổng 70 + 85 + 95 = 250, trung bình 83.33 khi định dạng hai chữ số thập phân với `Locale.ROOT`.
2. Mảng `long[]` biểu diễn được tổng 5.000.000.000, lớn hơn giá trị tối đa của `int`. Mảng `double[]` cộng ra 7.5.
3. `List<Integer>` dùng `mapToInt(Integer::intValue)` rồi tổng bằng 59.
4. Hai đơn hàng cho tổng `1500×2 + 250×4 = 4000` cent; mã dùng `Math.multiplyExact` và `Math.addExact` để phát hiện overflow.
5. `IntStream.range(1, 5)` không gồm 5 nên tổng bằng 10. `boxed().sorted().toList()` đưa về danh sách đối tượng `[1, 2, 3]`.
6. `Stream.of(scores).count()` bằng 1 vì đây là `Stream<int[]>`. Để đếm ba số, dùng `Arrays.stream(scores).count()`.
7. `String.codePoints()` đếm 3 code points, `chars()` đếm 4 code units do một ký tự Unicode ngoài BMP chiếm cặp surrogate.
8. Danh sách có null được lọc có chủ đích trước khi unbox, nên tổng 2 + 3 = 5.
9. `Integer.MAX_VALUE + 1` vượt `int`, nhưng `asLongStream()` chuyển trước khi cộng cho ra 2147483648.
10. Trung bình trên Stream rỗng không có giá trị nên `isEmpty()` là true. `BigDecimal` từ chuỗi cộng chính xác ra `0.30`.

## 11. Tính chính xác: integral overflow, floating-point và miền nghiệp vụ

### 11.1. Tổng số nguyên

`IntStream.sum()` trả `int` và có thể tràn. `LongStream.sum()` trả `long` và cũng có thể tràn. Chọn `LongStream` khi cần mở rộng từ `int`, dùng `Math.addExact` khi cần phát hiện tràn, hoặc `BigInteger` khi miền kết quả vượt `long`.

Ví dụ tránh tràn int:

```java
long expected = IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum(); // 2147483648
```

Đừng chỉ dùng `mapToLong(i -> i)` sau khi phép cộng `int` đã xảy ra: chuyển **trước** khi gộp. Với tổng tiền, chọn đơn vị và kiểu phù hợp như `long` cent hoặc `BigDecimal` tùy miền nghiệp vụ, không chọn `double` chỉ vì phép cộng có vẻ tiện.

### 11.2. Tổng số thực

`DoubleStream` phù hợp đo lường xấp xỉ, dữ liệu khoa học hoặc tín hiệu mà `double` là kiểu đúng của nguồn. Các số nhị phân dấu phẩy động không thể biểu diễn chính xác mọi số thập phân, và thứ tự gộp (nhất là song song) có thể ảnh hưởng kết quả. Các hàm `sum()` có thể dùng thuật toán cộng bù để cải thiện độ chính xác, nhưng **không biến `double` thành số thập phân chính xác tuyệt đối**.

- Kiểm tra dữ liệu có `Double.NaN`, `POSITIVE_INFINITY`, `NEGATIVE_INFINITY` theo yêu cầu.
- Không giả định `sum()` trên số thực bằng công thức toán học đến từng bit trong mọi thứ tự.
- Với phép so sánh trong test, chọn dung sai phù hợp miền dữ liệu khi có xử lý `double`.
- Với tiền tệ hoặc số thập phân cần chính xác, dùng `BigDecimal` từ **chuỗi chính xác** và `Stream<BigDecimal>`; tránh tạo `new BigDecimal(0.1)` rồi mong kết quả là số thập phân 0.1 chính xác.

### 11.3. Null, missing, và dữ liệu dạng đối tượng

Primitive stream không có phần tử `null`. Giá trị thiếu của dữ liệu đầu vào dạng wrapper cần được xử lý **trước khi unbox**. Đừng dùng `0` hoặc `Double.NaN` để ngầm biểu diễn null trừ khi đã có hợp đồng cụ thể: giá trị 0 có thể là số liệu hợp lệ, còn NaN có ngữ nghĩa số thực khác với “chưa nhập”.

## 12. Hiệu năng và cách chọn trong ứng dụng thực

**Chọn primitive stream khi:**

- Đầu vào là `int[]`, `long[]`, `double[]` hoặc cần tính số từ các trường nguyên thủy.
- Pipeline dài và có nhiều bước `filter`/`map`/`sum`/`average` trên số nguyên thủy.
- Muốn tránh boxing/unboxing không cần thiết hoặc dùng các thống kê chuyên biệt.

**Giữ object stream khi:**

- Cần xử lý object phức tạp, grouping theo đối tượng, giữ giá trị có thể null và chính sách null cụ thể.
- Dữ liệu là `BigDecimal`/`BigInteger` hoặc cần phép gộp chính xác tùy ý.
- API đích yêu cầu `Stream<T>`, `Collector<T,...>` hay một loại đối tượng không thể biểu diễn bằng primitive.
- Chuyển sang primitive sẽ làm mất thông tin, mất độ chính xác hoặc tăng phức tạp không cần thiết.

**Lưu ý về thực thi:**

- Stream là pipeline **lazy** ở các intermediate operations; `sum()`, `count()`, `average()`, `toArray()` là terminal operation. Sau đó không dùng lại cùng một object Stream.
- Các phép trung gian như `mapToInt` thường không thực thi cho đến khi có terminal operation; nếu mã dùng `peek` để ghi log hoặc phụ thuộc side effect thì không nên coi số lần gọi là bảo đảm.
- `parallel()`/`parallelStream()` không bảo đảm nhanh hơn, nhất là với nguồn nhỏ; yêu cầu hàm xử lý stateless và non-interfering, benchmark trong môi trường thực tế khi cần tối ưu.
- `Arrays.stream(array)` không có nghĩa sao chép mảng từ đầu. Đừng sửa mảng nguồn đồng thời trong lúc tiêu thụ Stream.
- `Stream.toList()` trả list không sửa được trong Java 16+; nếu cần một danh sách mutable, phải tự tạo container thích hợp.

## 13. Các lỗi phổ biến khi lựa chọn primitive stream

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `Stream.of(intArray)` để duyệt từng số | Tạo `Stream<int[]>` một phần tử | `Arrays.stream(intArray)` / `IntStream.of(intArray)` |
| Dùng `IntStream.sum()` cho tổng vượt `int` | Tràn số | `asLongStream()` trước khi cộng, hoặc kiểu lớn hơn |
| Chọn `DoubleStream` cho tiền thập phân chính xác | Sai số biểu diễn | `Stream<BigDecimal>` |
| `mapToInt(Integer::intValue)` trên collection có null | `NullPointerException` | Xác định policy null trước khi unbox |
| Gọi `sum()` rồi gọi `average()` trên cùng Stream | Stream đã tiêu thụ | Tạo Stream mới hoặc dùng `summaryStatistics()` |
| Giả định `chars()` đếm ký tự Unicode code point | Sai với surrogate pair | `codePoints()` nếu cần code point |
| Hiểu `range(1,5)` có cả số 5 | Lệch 1 | `rangeClosed(1,5)` khi cần gồm biên cuối |
| Chuyển `long` lớn sang `double` mà yêu cầu giữ nguyên giá trị | Có thể mất bit chính xác | Giữ `long` / `BigInteger` |
| Dùng `average().orElse(0)` mặc định | Không phân biệt trống với trung bình 0 | Giữ `OptionalDouble` hoặc policy rõ ràng |
| Dùng `parallel` cho mọi nguồn | Có thể chậm hơn, khó kiểm soát | Đo hiệu năng, ưu tiên xử lý rõ ràng |
| Viết `Arrays.stream(byte[])` | Không có overload tương ứng | Tạo dải index hoặc cách xử lý byte phù hợp |

## 14. Bài luyện tập theo nguồn dữ liệu

**Bài 1.** Có `int[] prices = {120, 300, 40}`, muốn tổng ở kiểu `long`. Chọn gì?

Đáp án:

```java
long sum = Arrays.stream(prices).asLongStream().sum(); // 460L
```

Kể cả ví dụ nhỏ cũng có thể chọn `long` nếu hợp đồng kết quả là tổng số nguyên lớn.

**Bài 2.** Có `List<Product> products` với `Product` chứa phương thức `int stock()`. Muốn tổng tồn kho:

```java
long totalStock = products.stream()
        .mapToInt(Product::stock)
        .asLongStream()
        .sum();
```

Đây là **đoạn minh họa**, yêu cầu đã định nghĩa kiểu `Product` và biến `products`. Tổng được mở rộng sang `long` trước khi cộng.

**Bài 3.** Có `List<String> values = List.of("1.50", "2.75")` và muốn tổng **thập phân chính xác**. Chọn gì?

```java
BigDecimal result = values.stream()
        .map(BigDecimal::new)
        .reduce(BigDecimal.ZERO, BigDecimal::add); // 4.25
```

Đây là đoạn minh họa khi đã import `java.math.BigDecimal` và `java.util.*`. Không dùng `DoubleStream` nếu yêu cầu độ chính xác thập phân.

**Bài 4.** `IntStream.range(0, 3).boxed().toList()` cho gì? **`[0, 1, 2]`**. `range` không gồm biên cuối.

**Bài 5.** Tại sao `List.of(1, 2, 3).stream().mapToInt(Integer::intValue).average()` trả `OptionalDouble`? Vì trung bình có thể là số thực; trường hợp nguồn rỗng không có giá trị phải được biểu diễn riêng.

**Bài 6.** Với `long[] counts`, có nên chuyển thành `Stream<Long>` rồi `mapToLong` chỉ để tính tổng? Thường **không**; `Arrays.stream(counts).sum()` trực tiếp hơn và tránh vòng boxing/unboxing.

## 15. Checklist quyết định nhanh

1. **Nguồn đã là `int[]`, `long[]` hoặc `double[]`?** Bắt đầu với `Arrays.stream(...)` cùng kiểu.
2. **Nguồn là wrapper collection?** Chuyển bằng `mapToInt`, `mapToLong`, `mapToDouble` khi cần toán học; xử lý null trước.
3. **Nguồn là object?** Chọn kiểu theo **trường cần tính và miền kết quả**, không theo hình thức của entity.
4. **Cần dải số?** Dùng `IntStream.range/rangeClosed` hoặc `LongStream.range/rangeClosed` tùy độ rộng biên.
5. **Cần dữ liệu Unicode?** `codePoints()` cho code point; `chars()` cho UTF-16 unit; đừng nhầm với grapheme.
6. **Cần tổng chính xác?** Xem tràn int/long, giới hạn double, `BigDecimal` và `BigInteger`.
7. **Cần Optional khi rỗng?** `average()`, `min()`, `max()` trả các Optional primitive; xác định chính sách rỗng.
8. **Cần object ở đầu ra?** Dùng `boxed()` hoặc `mapToObj` tại ranh giới, không boxing không cần thiết.
9. **Đã kiểm tra một Stream chỉ dùng một lần và dữ liệu nguồn không bị sửa trong khi chạy?**
10. **Có cần benchmark?** Chỉ tối ưu parallel/boxing khi có khối lượng dữ liệu và bằng chứng phù hợp.

## Tài liệu tham khảo chính thức

- [Oracle JDK 26 — IntStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html)
- [Oracle JDK 26 — LongStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/LongStream.html)
- [Oracle JDK 26 — DoubleStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/DoubleStream.html)
- [Oracle JDK 26 — Stream<T>, mapToInt/mapToLong/mapToDouble](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle JDK 26 — Arrays.stream overloads](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html)
- [Oracle JDK 26 — String.chars và String.codePoints](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html)
