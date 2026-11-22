# OptionalInt, OptionalLong và OptionalDouble trong Java

## 1. Mục tiêu và bối cảnh

`OptionalInt`, `OptionalLong` và `OptionalDouble` là ba lớp trong `java.util` biểu diễn **một giá trị primitive có thể hiện diện hoặc vắng mặt**. Chúng xuất hiện từ Java 8 và vẫn là API hiện hành trong các phiên bản Java mới. Mỗi đối tượng đại diện cho **tối đa một giá trị**, không phải một danh sách hay một Stream.

- `OptionalInt` chứa một `int` hoặc không chứa gì.
- `OptionalLong` chứa một `long` hoặc không chứa gì.
- `OptionalDouble` chứa một `double` hoặc không chứa gì.

Chúng thường xuất hiện ở kết quả của `IntStream`, `LongStream` và `DoubleStream` khi phép tính **có thể không có đáp án**: `min()`, `max()`, `average()`, `findFirst()`, `findAny()` và `reduce(operator)` (không có identity).

**Tư tưởng quan trọng:** “Không tìm được kết quả” **khác** với một kết quả bằng `0`, `0L` hay `0.0`. Ba lớp này biểu đạt sự khác biệt đó bằng hai trạng thái rõ ràng: *present* và *empty*.

Ví dụ:

```java
OptionalInt minimum = IntStream.of(4, 9, 2).min(); // OptionalInt[2]
OptionalInt missing = IntStream.empty().min();     // OptionalInt.empty
OptionalInt zero = OptionalInt.of(0);              // Giá trị 0 CÓ mặt
```

Đây là **đoạn mã minh họa**, cần import `java.util.*` và `java.util.stream.*` trong chương trình Java.

### Học xong cần làm được gì?

1. Chọn đúng `OptionalInt`, `OptionalLong` hoặc `OptionalDouble` từ kiểu số và kết quả Stream.
2. Phân biệt `empty()` với `of(0)`; xử lý nguồn rỗng mà không tùy tiện đổi “không có dữ liệu” thành số 0.
3. Dùng `isPresent`, `isEmpty`, `ifPresent`, `ifPresentOrElse`, `orElse`, `orElseGet` và `orElseThrow` đúng tình huống.
4. Biết API nào của primitive Optional **không tương đương** với `Optional<T>`.
5. Dùng `stream()` khi cần tích hợp với primitive stream, đổi sang object stream hoặc chuyển sang kiểu số khác.
6. Xử lý đặc thù `double` như `NaN` và dấu của số không, cũng như overflow và sai số số học.
7. Viết kiểm thử được cả giá trị hiện diện, nguồn rỗng và nhánh lỗi.

Các ví dụ runnable được viết cho **Java 17+**. Chức năng cơ bản của các primitive Optional đã có từ Java 8; một số tiện ích được bổ sung ở Java 9–11 và vẫn được dùng hiện nay.

## 2. Chọn lớp nào và kết quả đến từ đâu?

| Kiểu dữ liệu cần biểu diễn | Loại Optional | Lấy dữ liệu khi có mặt | Stream thường tạo ra |
| --- | --- | --- | --- |
| `int` | `OptionalInt` | `getAsInt()` | `IntStream.min/max/findFirst/findAny/reduce(operator)` |
| `long` | `OptionalLong` | `getAsLong()` | `LongStream.min/max/findFirst/findAny/reduce(operator)` |
| `double` | `OptionalDouble` | `getAsDouble()` | `DoubleStream.min/max/average/findFirst/findAny/reduce(operator)` |
| Trung bình từ `IntStream` | `OptionalDouble` | `getAsDouble()` | `IntStream.average()` |
| Trung bình từ `LongStream` | `OptionalDouble` | `getAsDouble()` | `LongStream.average()` |

Cả `IntStream.average()` và `LongStream.average()` đều trả **`OptionalDouble`**, không trả `OptionalInt` hoặc `OptionalLong`, vì trung bình số nguyên có thể mang phần thập phân.

Ví dụ:

```java
OptionalDouble mean = IntStream.of(2, 3).average();
// Có giá trị 2.5, nên cần OptionalDouble.

OptionalLong maxId = LongStream.of(3_000_000_000L, 5L).max();
// Có giá trị 3_000_000_000L, vượt miền int.
```

**Không chọn `OptionalInt` chỉ vì nguồn có các số “trông nhỏ”.** Cần xét kiểu dữ liệu và miền giá trị. ID hoặc số lượng có độ rộng `long` nên được giữ dưới `OptionalLong` khi cần nguyên vẹn.

### Khi nào kết quả không có Optional?

Không phải mọi terminal operation của primitive stream đều trả Optional.

| Biểu thức | Kiểu trả về | Kết quả khi rỗng |
| --- | --- | --- |
| `IntStream.empty().sum()` | `int` | `0` |
| `LongStream.empty().sum()` | `long` | `0L` |
| `DoubleStream.empty().sum()` | `double` | `0.0` |
| `IntStream.empty().count()` | `long` | `0L` |
| `IntStream.empty().average()` | `OptionalDouble` | Rỗng |
| `IntStream.empty().min()` | `OptionalInt` | Rỗng |
| `LongStream.empty().max()` | `OptionalLong` | Rỗng |
| `DoubleStream.empty().findFirst()` | `OptionalDouble` | Rỗng |
| `IntStream.empty().reduce(10, Integer::sum)` | `int` | `10` |
| `IntStream.empty().reduce(Integer::sum)` | `OptionalInt` | Rỗng |

Overload `reduce(identity, operator)` có phần tử đơn vị nên trả **primitive trực tiếp**, khác overload không có identity. Vì vậy không thể suy ra “Stream rỗng luôn tạo Optional rỗng”; phụ thuộc **terminal operation**.

## 3. Tạo giá trị và hiểu đúng trạng thái

Mỗi lớp cung cấp hai factory cơ bản:

```java
OptionalInt age = OptionalInt.of(20);
OptionalInt noAge = OptionalInt.empty();

OptionalLong totalBytes = OptionalLong.of(5_000_000_000L);
OptionalLong noBytes = OptionalLong.empty();

OptionalDouble ratio = OptionalDouble.of(0.0);
OptionalDouble noRatio = OptionalDouble.empty();
```

Đây là đoạn code minh họa với `import java.util.*;`.

**`of(value)` luôn tạo trạng thái có mặt**, kể cả khi value bằng `0`, số âm, `0.0`, `-0.0` hay `Double.NaN`. Với primitive, không có `null`; ba lớp này cũng **không có `ofNullable(...)`** vì không nhận object có thể null.

**`empty()` không phải số 0:**

```java
OptionalInt none = OptionalInt.empty();
OptionalInt actualZero = OptionalInt.of(0);

boolean a = none.isEmpty();        // true
boolean b = actualZero.isPresent(); // true
int n = actualZero.orElse(99);      // 0, không phải 99
```

Dùng `OptionalInt.empty()` thay vì giá trị giả như `-1` nếu `-1` có thể là kết quả hợp lệ. Khi nghiệp vụ cần phân biệt “không có dữ liệu” và “dữ liệu bằng không”, Optional giúp loại bỏ sự mơ hồ.

### Trường hợp nguồn rỗng

```java
OptionalInt max = IntStream.empty().max();
OptionalLong first = LongStream.empty().findFirst();
OptionalDouble mean = DoubleStream.empty().average();

System.out.println(max.isEmpty());   // true
System.out.println(first.isEmpty()); // true
System.out.println(mean.isEmpty());  // true
```

Ví dụ dùng `isEmpty()` là phương thức có từ Java 11, hiện vẫn được hỗ trợ. Nếu dự án bị ràng buộc phải tương thích chính xác Java 8, dùng `!isPresent()` thay thế (nhưng bài học ưu tiên API hiện hành).

## 4. Đọc và xử lý kết quả mà không gây lỗi

### 4.1. `isPresent()` và `isEmpty()`

- `isPresent()`: `true` nếu chứa một primitive.
- `isEmpty()`: `true` nếu không chứa giá trị.

`isEmpty` được bổ sung sau Java 8, không phải API lỗi thời; với Java 17+ dùng được bình thường.

### 4.2. `getAsInt()`, `getAsLong()`, `getAsDouble()`

Chúng trả primitive nhưng **ném `NoSuchElementException` nếu Optional rỗng**:

```java
OptionalInt found = IntStream.of(2, 8).max();
int answer = found.getAsInt(); // 8, vì biết rõ đây là non-empty

// OptionalInt.empty().getAsInt(); // Ném NoSuchElementException.
```

Không nên gọi `getAsInt()` sau một phép tìm kiếm có thể thất bại mà chưa định nghĩa nhánh rỗng. Chọn một trong các cách sau sẽ rõ hợp đồng hơn:

- `orElse(defaultValue)` khi có giá trị mặc định hợp lệ.
- `orElseGet(supplier)` khi tính giá trị dự phòng cần được thực hiện **chỉ lúc rỗng**.
- `orElseThrow()` hoặc `orElseThrow(exceptionSupplier)` khi thiếu giá trị là lỗi.
- `ifPresent(action)` nếu chỉ cần thực hiện thao tác khi có giá trị.
- `ifPresentOrElse(action, emptyAction)` khi cần hai nhánh.

### 4.3. Giá trị dự phòng: `orElse` và `orElseGet`

```java
int score = OptionalInt.empty().orElse(-1);
long bytes = OptionalLong.empty().orElse(0L);
double price = OptionalDouble.empty().orElse(Double.NaN);
```

Những biểu thức trên là **minh họa chính sách**, không có ý nghĩa rằng `-1`, `0L` hay `NaN` là fallback đúng cho mọi nghiệp vụ. Chỉ dùng sentinel khi hợp đồng đã quy định rõ và không làm mất thông tin.

`orElseGet` nhận supplier primitive:

```java
int value = result.orElseGet(() -> queryDefaultScore());
```

Đây là ví dụ trong ngữ cảnh `OptionalInt result` và phương thức `int queryDefaultScore()` đã tồn tại. Supplier **không được gọi nếu giá trị có mặt**. Các kiểu hàm tương ứng là `IntSupplier`, `LongSupplier`, `DoubleSupplier`.

Khác nhau:

| API | Đối số | Khi có giá trị | Khi rỗng |
| --- | --- | --- | --- |
| `orElse(10)` | Primitive cụ thể | Trả giá trị có sẵn | Trả 10 |
| `orElseGet(() -> calculate())` | Supplier primitive | Không gọi supplier | Gọi supplier rồi trả kết quả |
| `orElseThrow()` | Không tham số | Trả giá trị có sẵn | Ném `NoSuchElementException` |
| `orElseThrow(() -> new ErrorType(...))` | Supplier exception | Trả giá trị có sẵn | Tạo và ném exception đã chọn |

Lưu ý: đối số biểu thức của `orElse(...)` được Java đánh giá **trước khi gọi phương thức**, dù Optional đã có giá trị. Vì vậy `result.orElse(expensiveCalculation())` vẫn thực thi phép tính; `orElseGet(...)` mới là dạng lười khi fallback tốn chi phí hoặc có side effect.

### 4.4. Ném lỗi có chủ đích với `orElseThrow`

```java
int required = IntStream.of(3, 4)
        .max()
        .orElseThrow(() -> new IllegalStateException("Không có giá trị"));
```

Overload nhận exception supplier đã có từ Java 8. Overload `orElseThrow()` **không tham số** có từ Java 10 và được dùng trong Java 17+.

Nếu xử lý một yêu cầu nghiệp vụ mà rỗng là bình thường, đừng dùng `orElseThrow` chỉ để tránh viết nhánh rỗng. Ngược lại, nếu không có dữ liệu là lỗi bắt buộc phải báo, ném exception mô tả rõ nguyên nhân là chính xác.

### 4.5. `ifPresent` và `ifPresentOrElse`

`ifPresent` nhận consumer kiểu primitive và không trả về giá trị:

```java
OptionalLong.of(100L).ifPresent(value -> System.out.println(value));
```

`ifPresentOrElse` cho thêm một nhánh khi rỗng:

```java
OptionalDouble.empty().ifPresentOrElse(
        value -> System.out.println("Average: " + value),
        () -> System.out.println("Không có dữ liệu"));
```

Cú pháp `ifPresentOrElse` có từ Java 9. Cần phân biệt việc **lấy một primitive để tiếp tục tính toán** (thường dùng `orElse`/`orElseThrow`) với việc **gây tác dụng** như ghi log hoặc cập nhật UI (dùng `ifPresent`).

## 5. Khác biệt giữa primitive Optional và `Optional<T>`

`Optional<Integer>` là object Optional chứa một tham chiếu `Integer`. `OptionalInt` chứa primitive `int` theo API, giúp tránh lớp wrapper `Integer` cho giá trị được giữ, dù bản thân `OptionalInt` cũng là một object. Tương tự cho `OptionalLong`/`OptionalDouble`.

| Nhu cầu | `Optional<T>` | Primitive Optional |
| --- | --- | --- |
| Kiểu giá trị | Bất kỳ reference type `T` | Chỉ `int` / `long` / `double` |
| Tạo empty | `Optional.empty()` | `OptionalInt.empty()`, v.v. |
| Có mặt | `Optional.of(value)` | `OptionalInt.of(int)`, v.v. |
| Đọc | `get()` / `orElse...` | `getAsInt` / `getAsLong` / `getAsDouble` |
| `ifPresent` | `Consumer<? super T>` | `IntConsumer` / `LongConsumer` / `DoubleConsumer` |
| `orElseGet` | `Supplier<T>` | `IntSupplier` / `LongSupplier` / `DoubleSupplier` |
| Chuyển từng giá trị | `map`, `flatMap` | **Không có** `map`/`flatMap` trực tiếp trên primitive Optional |
| Lọc tùy điều kiện | `filter` | **Không có** `filter` trực tiếp |
| Chuyển thành stream | `stream(): Stream<T>` | `stream(): IntStream/LongStream/DoubleStream` |

**Không có `OptionalInt.map(...)`, `OptionalLong.flatMap(...)` hoặc `OptionalDouble.filter(...)` trong API tiêu chuẩn.** Nếu muốn biến đổi một giá trị primitive mà vẫn giữ trạng thái empty, dùng `stream()` và terminal operation phù hợp, hoặc `isPresent` và `OptionalX.of(...)` trong code nghiệp vụ.

Ví dụ biến đổi mà vẫn giữ kiểu optional:

```java
OptionalInt source = OptionalInt.of(7);
OptionalInt doubled = source.stream().map(x -> x * 2).findFirst();
// OptionalInt[14]

OptionalInt empty = OptionalInt.empty();
OptionalInt stillEmpty = empty.stream().map(x -> x * 2).findFirst();
// OptionalInt.empty()
```

Đoạn trên dùng `OptionalInt.stream()` từ Java 9; không có một lời gọi `source.map(...)` tương đương trực tiếp.

**Chọn `Optional<T>` khi nào?** Khi kết quả là đối tượng (như `User`, `String`, `BigDecimal`) hoặc cần kết hợp/phép biến đổi phong phú của `Optional<T>`. Chọn primitive Optional khi kết quả là một số primitive đơn và phù hợp với nguồn primitive stream.

## 6. `stream()`: kết nối Optional primitive và Stream

Từ Java 9, ba lớp có `stream()`:

| Optional | Khi có giá trị | Khi empty |
| --- | --- | --- |
| `OptionalInt.stream()` | Một `IntStream` chứa 1 phần tử `int` | `IntStream.empty()` |
| `OptionalLong.stream()` | Một `LongStream` chứa 1 phần tử `long` | `LongStream.empty()` |
| `OptionalDouble.stream()` | Một `DoubleStream` chứa 1 phần tử `double` | `DoubleStream.empty()` |

Điểm quan trọng: `stream()` không trả về chính giá trị; nó trả một **Stream có 0 hoặc 1 phần tử**. Điều này hữu ích khi muốn nối, ánh xạ hoặc kết hợp với pipeline khác mà không phải tự viết nhánh if.

Ví dụ:

```java
IntStream merged = IntStream.concat(
        OptionalInt.of(3).stream(),
        OptionalInt.empty().stream());
int[] numbers = merged.toArray(); // [3]
```

Với danh sách các `OptionalInt` (cần object stream để chứa chúng), dùng `flatMapToInt`:

```java
List<OptionalInt> sources = List.of(
        OptionalInt.of(2),
        OptionalInt.empty(),
        OptionalInt.of(5)
);

int[] values = sources.stream()
        .flatMapToInt(OptionalInt::stream)
        .toArray(); // [2, 5]
```

Thao tác `flatMapToInt` chạy trên **`Stream<OptionalInt>`**, không chạy trên một `OptionalInt` đơn lẻ.

### 6.1. Chuyển sang `Optional<Integer>` khi API cần object Optional

Có thể dùng đường chuyển qua stream:

```java
Optional<Integer> boxed = OptionalInt.of(7)
        .stream()
        .boxed()
        .findFirst(); // Optional[7]

Optional<Integer> emptyBoxed = OptionalInt.empty()
        .stream()
        .boxed()
        .findFirst(); // Optional.empty()
```

Lời gọi `boxed()` thuộc `IntStream`, không thuộc `OptionalInt`. Nó chuyển phần tử primitive thành `Integer`. Khi chỉ cần giữ kiểu primitive, không boxing ngược lại một cách không cần thiết.

Đường ngược lại, từ `Optional<Integer>` sang `OptionalInt`:

```java
Optional<Integer> boxed = Optional.of(9);
OptionalInt primitive = boxed.stream()
        .mapToInt(Integer::intValue)
        .findFirst(); // OptionalInt[9]
```

Cú pháp này sử dụng `Optional.stream` (Java 9+). Một cách tường minh hơn là kiểm tra trạng thái rồi gọi `OptionalInt.of(...)` nếu không muốn dựng pipeline.

### 6.2. Mở rộng sang kiểu số khác

Nếu đã có `OptionalInt` và muốn `OptionalLong`:

```java
OptionalLong widened = OptionalInt.of(Integer.MAX_VALUE)
        .stream()
        .asLongStream()
        .findFirst();
```

Đây là chuyển đổi `int` → `long` không mất dữ liệu. Nhưng `long` → `double` có thể mất chính xác với số nguyên lớn, và phép chuyển đổi số học không tự bảo toàn hoàn toàn trạng thái nghiệp vụ nếu bạn thay đổi ý nghĩa trường dữ liệu.

### 6.3. Đừng tái sử dụng Stream

`OptionalInt.stream()` tạo **một stream mới ở mỗi lần gọi**. Bản thân `OptionalInt` là value object biểu diễn trạng thái, có thể đọc lại; nhưng mỗi stream nhận được chỉ nên tiêu thụ một lần:

```java
OptionalInt value = OptionalInt.of(12);
long count = value.stream().count();     // 1
int sum = value.stream().sum();          // 12: stream mới
```

Đừng viết `IntStream s = value.stream(); s.sum(); s.count();` vì `s` đã bị terminal operation đầu tiên tiêu thụ.

## 7. Trường hợp đặc biệt của `OptionalDouble`

### 7.1. Empty khác `0.0`, `-0.0` và `NaN`

`OptionalDouble.empty()` không chứa giá trị. Nhưng `OptionalDouble.of(0.0d)`, `OptionalDouble.of(-0.0d)`, `OptionalDouble.of(Double.NaN)` và `OptionalDouble.of(Double.POSITIVE_INFINITY)` đều **có mặt**.

Điều này đặc biệt quan trọng khi dùng kết quả từ tính toán dữ liệu thực:

- “Không có mẫu đo” là `OptionalDouble.empty()` trong những API như `average()` của nguồn rỗng.
- “Có một mẫu đo bằng 0” là `OptionalDouble.of(0.0)`.
- “Có kết quả NaN” không tự động đồng nghĩa không có kết quả: đó là giá trị `double` mà phép tính đã trả ra.
- Dữ liệu `NaN` hoặc vô cực cần có chính sách chất lượng dữ liệu riêng nếu ứng dụng không cho phép.

### 7.2. Quy tắc so sánh và kiểm thử

`OptionalDouble.equals` khi cả hai có giá trị sử dụng so sánh tương đương với `Double.compare`, **không** đơn giản thay thế bằng toán tử `==` của primitive:

```java
boolean sameNan = OptionalDouble.of(Double.NaN)
        .equals(OptionalDouble.of(Double.NaN)); // true

boolean sameSignedZero = OptionalDouble.of(-0.0d)
        .equals(OptionalDouble.of(+0.0d)); // false
```

Lý do: `Double.compare` coi các bit quy ước của NaN là bằng nhau cho so sánh này, nhưng phân biệt `-0.0` với `+0.0`. Vì thế khi unit test so các OptionalDouble, phải phân biệt so bằng `equals` và so với dung sai số học phù hợp nghiệp vụ.

**Điều `OptionalDouble` không giải quyết:** lỗi làm tròn IEEE 754. Tính tổng hoặc trung bình `double` vẫn chịu đặc tính dấu phẩy động. Không dùng `OptionalDouble` để thay thế `BigDecimal` khi cần tiền hoặc số thập phân chính xác.

### 7.3. Trung bình và nguồn rỗng

`IntStream.average()` trả `OptionalDouble`:

```java
OptionalDouble avg = IntStream.of(2, 3).average();
System.out.println(avg.orElseThrow()); // 2.5
```

Với nguồn rỗng:

```java
OptionalDouble none = IntStream.empty().average();
System.out.println(none.isEmpty()); // true
```

Nếu ứng dụng hiển thị “N/A” khi thiếu dữ liệu, nên giữ `OptionalDouble` đến tầng trình bày thay vì tự thay bằng `0.0`:

```java
String display = avg.isPresent()
        ? Double.toString(avg.getAsDouble())
        : "N/A";
```

Đây là đoạn minh họa với `avg` đã tồn tại. Không coi `0.0` là một sentinel rỗng nếu một trung bình thực sự bằng 0 là hợp lệ.

## 8. Chương trình hoàn chỉnh có thể chạy (Java 17+)

Tạo tệp **`PrimitiveOptionalDemo.java`**:

```java
import java.util.*;
import java.util.stream.*;

public class PrimitiveOptionalDemo {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        OptionalInt minimum = IntStream.of(8, 3, 5).min();
        OptionalLong maximum = LongStream.of(7_000_000_000L, 10L).max();
        OptionalDouble average = IntStream.of(2, 3).average();

        check(minimum.orElseThrow() == 3, "minimum");
        check(maximum.orElseThrow() == 7_000_000_000L, "maximum");
        check(average.orElseThrow() == 2.5, "average");

        System.out.println("intMin=" + minimum.orElseThrow());
        System.out.println("longMax=" + maximum.orElseThrow());
        System.out.println("intAverage=" + average.orElseThrow());

        // Empty không đồng nghĩa với một giá trị bằng không.
        OptionalInt missing = IntStream.empty().max();
        OptionalInt zero = OptionalInt.of(0);
        check(missing.isEmpty() && zero.isPresent(), "empty is not zero");
        System.out.println("missingEmpty=" + missing.isEmpty());
        System.out.println("zeroPresent=" + zero.isPresent());
        System.out.println("fallback=" + missing.orElse(-1));

        // orElseGet chỉ chạy supplier khi không có giá trị.
        int[] fallbackCalls = {0};
        int present = OptionalInt.of(9).orElseGet(() -> {
            fallbackCalls[0]++;
            return 100;
        });
        int absent = missing.orElseGet(() -> {
            fallbackCalls[0]++;
            return 100;
        });
        check(present == 9 && absent == 100 && fallbackCalls[0] == 1,
                "lazy fallback");
        System.out.println("lazyFallback=" + present + "/" + absent
                + ", calls=" + fallbackCalls[0]);

        // ifPresent/ifPresentOrElse với primitive consumer.
        int[] observed = {0};
        OptionalLong.of(12L).ifPresent(value -> observed[0] += value);
        OptionalLong.empty().ifPresentOrElse(
                value -> observed[0] += value,
                () -> observed[0] += 1);
        check(observed[0] == 13, "ifPresentOrElse");
        System.out.println("observed=" + observed[0]);

        // stream() có 0 hoặc 1 phần tử; boxed() hoạt động trên IntStream.
        List<Integer> values = IntStream.concat(
                OptionalInt.of(3).stream(),
                OptionalInt.empty().stream()).boxed().toList();
        check(values.equals(List.of(3)), "stream flatten");
        System.out.println("flattened=" + values);

        Optional<Integer> boxed =
                OptionalInt.of(7).stream().boxed().findFirst();
        System.out.println("boxed=" + boxed);
        System.out.println("emptyLongCount=" +
                OptionalLong.empty().stream().count());
        System.out.println("doubleStreamCount=" +
                OptionalDouble.of(2.5).stream().count());

        // OptionalDouble.equals có ngữ nghĩa so sánh của Double.
        System.out.println("nanEqual=" + OptionalDouble.of(Double.NaN)
                .equals(OptionalDouble.of(Double.NaN)));
        System.out.println("signedZeroEqual=" + OptionalDouble.of(-0.0d)
                .equals(OptionalDouble.of(+0.0d)));

        System.out.println("ALL CHECKS PASSED");
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac PrimitiveOptionalDemo.java
java PrimitiveOptionalDemo
```

**Stdout chính xác:**

```text
intMin=3
longMax=7000000000
intAverage=2.5
missingEmpty=true
zeroPresent=true
fallback=-1
lazyFallback=9/100, calls=1
observed=13
flattened=[3]
boxed=Optional[7]
emptyLongCount=0
doubleStreamCount=1
nanEqual=true
signedZeroEqual=false
ALL CHECKS PASSED
```

### Giải thích kết quả

- `minimum` là `OptionalInt[3]`, `maximum` là `OptionalLong[7000000000]`; kiểu `long` bảo toàn số vượt miền `int`.
- Trung bình hai số nguyên 2 và 3 bằng 2.5 nên trả `OptionalDouble`.
- `missingEmpty=true` và `zeroPresent=true` cho thấy một kết quả rỗng không đồng nghĩa giá trị 0.
- `fallback=-1` chỉ là giá trị mặc định được lựa chọn trong ví dụ; nghiệp vụ thật phải xác định xem `-1` có hợp lệ hay không.
- `orElseGet` trên `OptionalInt.of(9)` không gọi supplier; trên nguồn rỗng gọi một lần, vì vậy `calls=1`.
- `observed=13`: `ifPresent` cộng 12 khi có dữ liệu, `ifPresentOrElse` trên OptionalLong rỗng chạy nhánh `Runnable` cộng thêm 1.
- `flattened=[3]`: `OptionalInt.of(3).stream()` có một phần tử, `OptionalInt.empty().stream()` không có phần tử. `boxed` tạo `Optional<Integer>` qua stream khi cần object API.
- `emptyLongCount=0` và `doubleStreamCount=1` xác nhận kích thước stream của Optional absent/present.
- `nanEqual=true`, `signedZeroEqual=false` đến từ hợp đồng `equals` của `OptionalDouble`.
- Chương trình dùng `check(...)` để xác minh các điều kiện; không cần bật cờ JVM `-ea` như khi dùng từ khóa `assert`.

## 9. Ví dụ nghiệp vụ: chọn Optional primitive đúng mục đích

### 9.1. Lấy tuổi nhỏ nhất từ hồ sơ

```java
record Person(String name, int age) {}

OptionalInt youngestAge = people.stream()
        .mapToInt(Person::age)
        .min();

youngestAge.ifPresentOrElse(
        age -> System.out.println("Youngest age=" + age),
        () -> System.out.println("Không có hồ sơ"));
```

Đây là đoạn minh họa cần `List<Person> people` và import Stream/API; định nghĩa record yêu cầu Java 16+. Nếu danh sách rỗng, `min()` trả `OptionalInt.empty()`. **Không** dùng `orElse(0)` vì tuổi 0 có thể là tuổi thực sự của trẻ sơ sinh.

### 9.2. Tìm dung lượng lớn nhất

```java
List<Long> sizes = List.of(10_000L, 6_000_000_000L);

OptionalLong biggest = sizes.stream()
        .mapToLong(Long::longValue)
        .max();

long requiredSize = biggest.orElseThrow(
        () -> new IllegalStateException("Không có tệp"));
```

Kiểu `long` phù hợp với giá trị lớn hơn `Integer.MAX_VALUE`. Thiếu dữ liệu được xử lý thành lỗi theo chính sách minh họa. Nếu danh sách trống là bình thường, giữ `OptionalLong` hoặc chọn fallback có ý nghĩa thay vì ném exception.

### 9.3. Trung bình số đo

```java
double[] readings = {1.5, 2.0, 2.5};

OptionalDouble average = Arrays.stream(readings).average();
String display = average.isPresent()
        ? String.format(Locale.ROOT, "%.2f", average.getAsDouble())
        : "N/A";
```

Với một số đo trung bình bằng đúng 0.0, đầu ra là `"0.00"`. Với **không có** số đo, đầu ra là `"N/A"`. Đó là lý do dùng `OptionalDouble` thay vì luôn trả số `double`.

### 9.4. Duy trì Optional khi lọc các kết quả tìm kiếm

Ví dụ danh sách nhiều nguồn, mỗi nguồn có thể tìm được số lượng hoặc không:

```java
List<OptionalInt> candidates = List.of(
        OptionalInt.empty(),
        OptionalInt.of(0),
        OptionalInt.of(7)
);

int[] presentValues = candidates.stream()
        .flatMapToInt(OptionalInt::stream)
        .toArray(); // [0, 7]
```

Chuyển `OptionalInt.empty()` thành 0 **trước** khi ghép nguồn sẽ làm sai số lượng dữ liệu hợp lệ. Dùng `stream()` giữ nguyên sự khác biệt: empty đóng góp 0 phần tử, `of(0)` đóng góp một phần tử có giá trị 0.

## 10. Các lỗi thường gặp

### 10.1. Gọi `getAsX()` khi có thể rỗng

**Sai:**

```java
int first = IntStream.empty().findFirst().getAsInt();
// Ném NoSuchElementException.
```

Đây là đoạn anti-pattern cố tình tạo exception. **Sửa:** xử lý rỗng bằng `orElse`, `orElseGet`, `orElseThrow` với thông báo rõ, hoặc giữ `OptionalInt` để caller quyết định.

### 10.2. Dùng số 0 làm sentinel cho “không có dữ liệu”

**Sai về ngữ nghĩa** nếu 0 hợp lệ:

```java
int min = IntStream.empty().min().orElse(0);
```

Khi nhìn vào `min` sau đó, code không phân biệt được tập rỗng và tập chứa giá trị 0. Nếu 0 thực sự là giá trị mặc định trong đặc tả thì `orElse(0)` hợp lệ; quan trọng là **có chủ đích**, không làm mặc định để tiện code.

### 10.3. Nhầm `average()` với kiểu Optional của nguồn

`IntStream.average()` và `LongStream.average()` trả `OptionalDouble`. Không thể gán trực tiếp cho `OptionalInt`/`OptionalLong`:

```java
OptionalDouble average = IntStream.of(1, 2).average();
// 1.5
```

### 10.4. Dùng API của `Optional<T>` trên primitive Optional

`OptionalInt` **không có** `map`, `filter`, `flatMap` hoặc `get()`. Để chuyển một giá trị int sang int khác, có thể dùng `optionalInt.stream().map(...).findFirst()`; để chuyển sang object, `stream().mapToObj(...).findFirst()` hoặc code điều kiện phù hợp.

### 10.5. Hiểu rằng primitive Optional “không tạo object nào”

Chúng tránh boxing cho số chứa bên trong, nhưng `OptionalInt`/`OptionalLong`/`OptionalDouble` **vẫn là các object**. Không khẳng định chúng luôn nhanh hơn `Optional<Integer>` trong mọi ngữ cảnh; đo bằng benchmark nếu tối ưu hóa là mục tiêu.

### 10.6. Dùng `==` để so Optional

Các Optional là **value-based classes**; đừng dùng `==` để suy luận chúng đại diện cùng giá trị, đừng dùng identity hash code hoặc đồng bộ `synchronized` trên Optional. Dùng `equals` để so trạng thái có/không và giá trị. Không dựa vào việc `empty()` hiện tại có vẻ dùng cùng một singleton.

### 10.7. Không xử lý `NaN`, `Infinity` và sai số `double`

`OptionalDouble.of(Double.NaN)` là một giá trị *có mặt*. Nếu ứng dụng xem `NaN` là dữ liệu không hợp lệ, cần chính sách riêng. Cộng `double` cũng có thể có sai số làm tròn; Optional không biến phép tính thành số thập phân chính xác.

### 10.8. Suy ra “có phần tử” từ `sum() == 0`

`IntStream.empty().sum() == 0` nhưng `IntStream.of(-2, 2).sum() == 0` cũng đúng. Nếu cần biết tập có phần tử, dùng `count()` hoặc một terminal operation trả Optional theo nghiệp vụ; không dùng tổng bằng 0 để suy luận rỗng. Không tiêu thụ cùng Stream hai lần.

### 10.9. Tùy tiện lấy `findAny()` rồi kỳ vọng đúng “phần tử đầu”

Với ordered stream, `findFirst()` biểu thị mục tiêu phần tử đầu theo encounter order. `findAny()` cho phép chọn bất kỳ phần tử nào và đặc biệt có thể khác khi song song. Cả hai trả Optional cùng loại primitive; nội dung **không cam kết giống nhau**.

### 10.10. Trả Optional primitive ở mọi nơi

Optional chủ yếu phù hợp **kiểu trả về** khi có thể thiếu kết quả. Không nhất thiết bọc tất cả field/parameter bằng Optional; với DTO, JSON, cơ sở dữ liệu hoặc framework, cần cân nhắc khả năng serialize/map và tính tương thích. Chọn biểu diễn phù hợp ở biên hệ thống, giữ Optional ở API nghiệp vụ nơi nó mang lại ý nghĩa rõ ràng.

## 11. Thiết kế kiểm thử cho các trường hợp rỗng và có giá trị

| Trường hợp | Test nên khẳng định | Lỗi giúp phát hiện |
| --- | --- | --- |
| `OptionalInt.of(0)` | `isPresent() == true` và giá trị là 0 | Nhầm 0 với empty |
| `OptionalInt.empty()` | `isEmpty() == true`, fallback hợp lệ | Truy cập getAsInt không an toàn |
| `OptionalLong.of(6_000_000_000L)` | Giữ nguyên long, không truncate | Ép xuống int |
| `IntStream.of(2,3).average()` | `OptionalDouble` chứa 2.5 | Mong đợi kiểu int |
| `IntStream.empty().average()` | `OptionalDouble.empty()` | Bỏ qua nguồn rỗng |
| `orElseGet` trên present | Supplier không được gọi | Fallback có side effect ngoài ý muốn |
| `orElseGet` trên empty | Supplier được gọi và trả primitive đúng | Logic dự phòng bị bỏ qua |
| `OptionalInt.stream()` khi empty/present | Lần lượt 0/1 phần tử | Mất phân biệt 0 và empty |
| `OptionalDouble.of(Double.NaN)` | Có mặt; quy tắc kiểm tra NaN rõ ràng | Nhầm NaN với empty |
| `findFirst` vs `findAny` | Chỉ kỳ vọng thứ tự khi API cam kết | Test song song không ổn định |

**Không chỉ kiểm tra success path:** nguồn rỗng là một trường hợp hợp lệ của `min`, `max`, `findFirst`, `findAny`, `average` và `reduce(operator)`. Unit test nên kiểm tra cả ba kiểu primitive, trường hợp không có kết quả và nhánh thay thế/exception.

### Khi nào dùng ngoại lệ?

Nếu API nghiệp vụ bắt buộc phải có dữ liệu, test có thể xác nhận:

```java
try {
    OptionalInt.empty().orElseThrow(
            () -> new IllegalArgumentException("Thiếu dữ liệu"));
    throw new AssertionError("Đáng lẽ phải ném ngoại lệ");
} catch (IllegalArgumentException expected) {
    // Nhánh lỗi đã được xác nhận.
}
```

Đây là đoạn **test minh họa**, không phải logic chạy thông thường. Với JUnit Jupiter, có thể dùng `assertThrows(...)` để viết gọn hơn khi đã có dependency test framework.

### Khi nào dùng giá trị mặc định?

Dùng `orElse` nếu nghiệp vụ quy định ví dụ “kết quả không tìm được thì hiển thị -1”. Nhưng không tự lấy fallback để ghi đè thông tin rỗng ở các tầng khác nếu còn cần phân biệt dữ liệu thiếu. Giá trị “chưa có” nên được giải quyết tại đúng ranh giới nghiệp vụ.

## 12. Câu hỏi thực hành và đáp án

**Câu 1.** `OptionalInt.empty().orElse(0)` và `OptionalInt.of(0).orElse(10)` có cùng kết quả không?

Có, cùng trả 0 **trong ví dụ cụ thể**, nhưng trạng thái gốc khác nhau: một empty, một present. Để phân biệt phải kiểm tra Optional trước khi lấy fallback.

**Câu 2.** `IntStream.of(1,2).average()` trả loại nào?

`OptionalDouble`, chứa giá trị `1.5`.

**Câu 3.** `OptionalLong.empty().stream().count()` trả gì?

`0L`, vì stream của empty không có phần tử.

**Câu 4.** Muốn nhân đôi giá trị `OptionalInt` nếu hiện diện, giữ nguyên empty thì viết thế nào?

```java
OptionalInt result = source.stream()
        .map(x -> x * 2)
        .findFirst();
```

Đây là đoạn code trong ngữ cảnh có `OptionalInt source`. Với dữ liệu có thể tràn `int`, thay `x * 2` bằng `Math.multiplyExact(x, 2)` hoặc kiểu rộng hơn nếu có yêu cầu.

**Câu 5.** Khi nào `orElseGet` thực sự hữu ích hơn `orElse`?

Khi fallback phải tính tốn chi phí, đọc trạng thái hoặc có side effect: `orElseGet` chỉ gọi supplier khi rỗng. Với hằng số như `0`, `orElse(0)` đơn giản và thường hợp lý hơn.

**Câu 6.** `OptionalDouble.of(Double.NaN).isPresent()` là `true` hay `false`?

`true`. `NaN` là một giá trị `double`, khác trạng thái empty.

**Câu 7.** `OptionalInt.of(8).getAsInt()` có an toàn không? `OptionalInt.empty().getAsInt()` thì sao?

Trường hợp đầu trả 8. Trường hợp sau ném `NoSuchElementException`; nên chọn API biểu đạt chính sách rỗng nếu không bảo đảm dữ liệu có mặt.

**Câu 8.** `OptionalInt` có phải là subtype của `Optional<Integer>` không?

**Không.** Hai lớp độc lập, không thể cast trực tiếp. Dùng chuyển đổi tường minh qua `stream().boxed().findFirst()` khi API yêu cầu `Optional<Integer>`.

## 13. Checklist áp dụng

- [ ] Chọn `OptionalInt`, `OptionalLong` hay `OptionalDouble` theo **kiểu kết quả thực**, không chỉ tên nguồn.
- [ ] Biết terminal operation nào trả Optional và terminal operation nào trả primitive trực tiếp.
- [ ] Phân biệt absent với số 0, -1, NaN hoặc giá trị sentinel khác.
- [ ] Tránh `getAsInt/getAsLong/getAsDouble` khi không biết chắc dữ liệu có mặt.
- [ ] Định nghĩa rõ: trả fallback, thực hiện action hay ném lỗi khi rỗng.
- [ ] Dùng `orElseGet` nếu cần fallback lazy; không dùng `orElse(expensiveCall())` rồi mong nó lazy.
- [ ] Nhớ primitive Optional không có `map/filter/flatMap` trực tiếp; dùng `stream()` hoặc code tường minh khi cần.
- [ ] Khi đổi sang `Optional<T>`, hiểu boxing và kiểu Stream trung gian.
- [ ] Với `double`, xử lý NaN/infinity/signed zero và sai số theo nghiệp vụ.
- [ ] Test nguồn rỗng, một giá trị bằng 0, giá trị lớn, fallback, conversion và nhánh lỗi.
- [ ] Không dựa vào object identity hay đồng bộ trên Optional; ưu tiên so `equals`.

## Tài liệu tham khảo chính thức (API hiện hành)

- [Oracle Java SE 25 — OptionalInt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalInt.html)
- [Oracle Java SE 25 — OptionalLong](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalLong.html)
- [Oracle Java SE 25 — OptionalDouble](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalDouble.html)
- [Oracle Java SE 25 — Optional<T>](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html)
- [Oracle Java SE 25 — IntStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/IntStream.html)
- [Oracle Java SE 25 — LongStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/LongStream.html)
- [Oracle Java SE 25 — DoubleStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/DoubleStream.html)
