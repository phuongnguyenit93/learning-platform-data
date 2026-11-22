# asLongStream, asDoubleStream và chuyển đổi giá trị trong Primitive Stream

Khi xử lý số bằng Java Stream, kiểu phần tử quyết định **phạm vi số nguyên, độ chính xác số thực, kiểu phép tính và kiểu kết quả**. Hai phương thức `asLongStream()` và `asDoubleStream()` cho phép chuyển các primitive stream sang kiểu rộng hơn mà không cần tự boxing phần tử thành `Integer`, `Long` hay `Double`.

Trong Java hiện hành, ba loại primitive stream chuẩn là `IntStream`, `LongStream` và `DoubleStream`. Không có `FloatStream` hay `ShortStream` chuẩn trong `java.util.stream`. Các API chuyển kiểu được giới thiệu từ Java 8 vẫn sử dụng được trên JDK hiện nay; các chương trình mẫu trong bài chạy với Java 17+.

Bài học hướng đến bốn câu hỏi:

1. **Đang có stream kiểu gì?** `IntStream`, `LongStream` hay `DoubleStream`?
2. **Muốn chuyển sang kiểu gì?** Khi nào dùng `asLongStream`, `asDoubleStream`, khi nào dùng `mapToLong` hoặc `mapToDouble`?
3. **Chuyển kiểu có giữ nguyên giá trị không?** `int → long` và `int → double` chính xác; `long → double` có thể mất chữ số nguyên.
4. **Thời điểm chuyển kiểu có ảnh hưởng phép tính không?** Có: tính toán ở `int` rồi mới chuyển `long` vẫn có thể bị tràn số trước khi chuyển.

## 1. Bảng phương thức chuyển kiểu có sẵn

| Kiểu nguồn | Phương thức | Kiểu kết quả | Chuyển đổi từng phần tử | Có thể mất giá trị gốc? |
| --- | --- | --- | --- | --- |
| `IntStream` | `asLongStream()` | `LongStream` | Widening `int → long` | Không |
| `IntStream` | `asDoubleStream()` | `DoubleStream` | Widening `int → double` | Không, riêng giá trị từng `int` luôn biểu diễn chính xác |
| `LongStream` | `asDoubleStream()` | `DoubleStream` | Widening `long → double` | **Có**, với một số `long` lớn |
| `IntStream` | `mapToLong(IntToLongFunction)` | `LongStream` | Tính giá trị `long` theo lambda | Phụ thuộc phép tính trong lambda |
| `IntStream` | `mapToDouble(IntToDoubleFunction)` | `DoubleStream` | Tính giá trị `double` theo lambda | Phụ thuộc phép tính trong lambda |
| `LongStream` | `mapToDouble(LongToDoubleFunction)` | `DoubleStream` | Tính giá trị `double` theo lambda | Có thể mất chính xác |
| `LongStream` | `mapToInt(LongToIntFunction)` | `IntStream` | Chuyển về miền `int` bằng quy tắc tự chọn | Có thể mất phần giá trị/tràn miền |
| `DoubleStream` | `mapToLong(DoubleToLongFunction)` hoặc `mapToInt(DoubleToIntFunction)` | `LongStream` hoặc `IntStream` | Chuyển số thực sang số nguyên theo hàm tự viết | Có thể mất phần thập phân hoặc vượt miền |

Các phương thức `asLongStream()` và `asDoubleStream()` là **intermediate operations**: xây dựng pipeline mới, chưa tự kích hoạt duyệt dữ liệu. Một terminal operation như `sum()`, `average()`, `toArray()`, `collect()` hay `forEach()` mới tiêu thụ pipeline.

Không có phương thức `DoubleStream.asLongStream()` hay `LongStream.asIntStream()` trong API chuẩn. Chiều chuyển xuống miền giá trị hẹp dùng `mapToInt`/`mapToLong` với chính sách kiểm tra rõ ràng. `IntStream.asLongStream` không thể được gọi trên một `Stream<Integer>` tham chiếu: cần chuyển `Stream<Integer>` thành primitive stream trước, ví dụ `mapToInt(Integer::intValue)`.

### Widening khác với boxing

- `IntStream.asLongStream()`: đổi phần tử primitive `int` thành primitive `long`.
- `IntStream.asDoubleStream()`: đổi primitive `int` thành primitive `double`.
- `LongStream.asDoubleStream()`: đổi primitive `long` thành primitive `double`.
- `IntStream.boxed()`: chuyển primitive `int` thành wrapper `Integer`, cho ra `Stream<Integer>`. Đây là **boxing**, không phải mở rộng miền số.
- `IntStream.mapToObj(String::valueOf)`: tạo `Stream<String>` theo hàm ánh xạ, cũng không phải `asDoubleStream`.

Khi chỉ cần đổi kiểu số theo quy tắc widening có sẵn, `asLongStream/asDoubleStream` diễn đạt ý định gọn và trực tiếp. Khi cần tính toán thêm trên từng phần tử, dùng `mapToLong` hoặc `mapToDouble` với phép biến đổi cụ thể.

## 2. `IntStream.asLongStream()`: mở rộng số nguyên chính xác

`int` là số nguyên có dấu 32 bit; `long` là số nguyên có dấu 64 bit. Mọi giá trị `int` đều nằm trong miền `long`, nên chuyển `int → long` **không mất thông tin**. Ví dụ:

```java
long x = (long) Integer.MAX_VALUE; // 2147483647L
long y = (long) Integer.MIN_VALUE; // -2147483648L
```

`asLongStream()` áp dụng phép widening tương đương cho từng phần tử:

```java
LongStream longNumbers = IntStream.of(-2, 0, 3).asLongStream();
```

Hãy chú ý **đổi kiểu trước khi làm phép cộng/nhân có nguy cơ tràn `int`**. Nếu `IntStream.sum()` được gọi trước, kết quả đã bị tính theo `int`; ép kết quả sau đó sang `long` không khôi phục tổng đúng.

Một ứng dụng thường gặp là tổng các giá trị đếm, số lượng hoặc số tiền lưu tạm dưới kiểu `int` nhưng tổng có thể vượt `Integer.MAX_VALUE`:

```java
long total = IntStream.of(2_000_000_000, 2_000_000_000)
        .asLongStream()
        .sum(); // 4_000_000_000L
```

Tổng `4_000_000_000L` nằm ngoài miền `int` nhưng nằm trong miền `long`. Dù vậy, **`long` cũng có giới hạn**: `LongStream.sum()` có thể tràn nếu kết quả toán học vượt miền `long`. Cần định nghĩa miền giá trị và chính sách tràn, nhất là với tài chính hoặc số lượng rất lớn.

## 3. `IntStream.asDoubleStream()`: chuyển sang số thực để tính toán

`double` là kiểu số dấu phẩy động 64 bit theo IEEE 754 (binary64), có khoảng **53 bit độ chính xác ở phần trị**. Vì `int` chỉ có 32 bit có dấu, mọi giá trị nguyên `int` được chuyển sang `double` **chính xác về giá trị số**. Ví dụ:

```java
DoubleStream ds = IntStream.of(-2, 0, 3).asDoubleStream();
// Khi đưa vào mảng double[]: [-2.0, 0.0, 3.0]
```

Sau chuyển đổi, có thể dùng các phép toán của `DoubleStream` như `map` với hệ số thực, `sum`, `average` và `summaryStatistics`. Nếu đơn giản chỉ muốn trung bình các số nguyên, `IntStream.average()` **đã trả `OptionalDouble`**, nên không bắt buộc chuyển sang `DoubleStream`:

```java
OptionalDouble mean1 = IntStream.rangeClosed(1, 4).average();
OptionalDouble mean2 = IntStream.rangeClosed(1, 4).asDoubleStream().average();
// Cả hai là OptionalDouble[2.5]
```

Mặc dù phép chuyển **mỗi `int` sang `double`** giữ giá trị chính xác, phép cộng, chia, nhân `double` về sau vẫn có thể chịu sai số làm tròn của số dấu phẩy động. Không suy ra từ `int → double` chính xác rằng **mọi kết quả tính toán trên DoubleStream đều chính xác tuyệt đối**.

## 4. `LongStream.asDoubleStream()`: widening nhưng có thể mất độ chính xác nguyên

Mọi số `long` đều có thể chuyển thành một giá trị `double` hữu hạn, nhưng **không phải mọi số nguyên `long` đều được biểu diễn chính xác** bằng binary64.

Lý do: `long` có 64 bit có dấu, còn phần trị `double` cho độ chính xác khoảng 53 bit. Các số nguyên có độ lớn từ `-(2^53)` đến `2^53` đều biểu diễn được chính xác; **ngoài khoảng này**, một số nguyên vẫn chính xác nhưng một số nguyên khác phải được làm tròn.

Giá trị biên quan trọng:

```text
2^53     = 9007199254740992    (biểu diễn chính xác bằng double)
2^53 + 1 = 9007199254740993    (không biểu diễn chính xác bằng double)
```

`LongStream.of(9_007_199_254_740_993L).asDoubleStream()` cho phần tử xấp xỉ `9.007199254740992E15`, bằng giá trị của `2^53`. Chuyển trở lại `long` không ra con số ban đầu.

Hệ quả thực tế:
- **ID, số thứ tự, timestamp dạng epoch lớn, số đếm nguyên lớn**: không chuyển sang `double` rồi mong giữ đúng từng đơn vị.
- **Tiền tính bằng đơn vị nhỏ nhất (cents, đồng...)**: nếu yêu cầu chính xác tuyệt đối, ưu tiên giữ `long` trong miền an toàn hoặc `BigDecimal` và kiểm tra tràn. Đừng dùng `asDoubleStream` chỉ để có thể tính toán số thực mà bỏ qua yêu cầu chính xác.
- **Đo đạc, thống kê chấp nhận xấp xỉ**: `double` có thể phù hợp, nhưng cần hiểu chính sách sai số, dữ liệu ngoại lai và phép tổng.

`asDoubleStream` chỉ là phép chuyển kiểu phần tử. Nó **không** cung cấp cơ chế tự động khôi phục chữ số bị làm tròn, cũng không làm cho phép cộng số thực trở thành phép cộng số nguyên chính xác.

## 5. Ví dụ Java 17+ đầy đủ: phương thức, kiểu kết quả và nguồn rỗng

Tạo tệp `PrimitiveWideningDemo.java`:

```java
import java.util.Arrays;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class PrimitiveWideningDemo {
    public static void main(String[] args) {
        int[] numbers = {-2, 0, 3};

        System.out.println("int = "
                + Arrays.toString(IntStream.of(numbers).toArray()));
        System.out.println("long = "
                + Arrays.toString(IntStream.of(numbers).asLongStream().toArray()));
        System.out.println("double = "
                + Arrays.toString(IntStream.of(numbers).asDoubleStream().toArray()));

        System.out.println("long to double = "
                + Arrays.toString(
                        LongStream.of(-2L, 3L).asDoubleStream().toArray()));

        System.out.println("average = "
                + IntStream.rangeClosed(1, 4).asDoubleStream().average());
        System.out.println("empty average = "
                + IntStream.empty().asDoubleStream().average());

        System.out.println("ordered = "
                + Arrays.toString(
                        IntStream.rangeClosed(1, 4)
                                .asLongStream()
                                .parallel()
                                .filter(x -> x % 2L == 0)
                                .toArray()));
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac -encoding UTF-8 PrimitiveWideningDemo.java
java PrimitiveWideningDemo
```

Đầu ra đã kiểm chứng:

```text
int = [-2, 0, 3]
long = [-2, 0, 3]
double = [-2.0, 0.0, 3.0]
long to double = [-2.0, 3.0]
average = OptionalDouble[2.5]
empty average = OptionalDouble.empty
ordered = [2, 4]
```

Giải thích:

- `toArray()` là terminal operation; mỗi biểu thức tạo **một Stream mới** từ mảng `numbers`.
- `IntStream.asLongStream().toArray()` trả `long[]`, còn `IntStream.asDoubleStream().toArray()` trả `double[]`. Khi in, các phần tử double hiển thị dạng `-2.0`, `0.0`, `3.0`.
- `average()` trả `OptionalDouble` vì Stream có thể rỗng. `OptionalDouble.empty` là kết quả hợp lệ, không phải lỗi.
- `parallel()` không xóa thứ tự encounter order của nguồn có thứ tự trong kết quả `toArray()`; `filter` giữ các số chẵn 2 và 4. Không mặc định giả định mọi terminal operation song song đều in theo thứ tự: `forEach` không bảo đảm thứ tự, còn `forEachOrdered` được thiết kế cho yêu cầu thứ tự.

## 6. Ví dụ Java 17+ đầy đủ: mất độ chính xác và tràn số

Tạo tệp `PrecisionDemo.java`:

```java
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class PrecisionDemo {
    public static void main(String[] args) {
        long n = 9_007_199_254_740_993L; // 2^53 + 1
        double d = LongStream.of(n).asDoubleStream()
                .findFirst()
                .orElseThrow();

        System.out.println("original = " + n);
        System.out.println("asDouble = " + d);
        System.out.println("cast back = " + (long) d);
        System.out.println("same after round trip = " + (n == (long) d));

        int maxInt = Integer.MAX_VALUE;
        double exactInt = IntStream.of(maxInt)
                .asDoubleStream()
                .findFirst()
                .orElseThrow();
        System.out.println("max int exact = " + (exactInt == maxInt));

        System.out.println("int overflow sum = "
                + IntStream.of(2_000_000_000, 2_000_000_000).sum());
        System.out.println("long safe sum = "
                + IntStream.of(2_000_000_000, 2_000_000_000)
                        .asLongStream()
                        .sum());
        System.out.println("double sum = "
                + IntStream.of(2_000_000_000, 2_000_000_000)
                        .asDoubleStream()
                        .sum());
        System.out.println("long overflow sum = "
                + LongStream.of(Long.MAX_VALUE, 1L).sum());
    }
}
```

```bash
javac -encoding UTF-8 PrecisionDemo.java
java PrecisionDemo
```

```text
original = 9007199254740993
asDouble = 9.007199254740992E15
cast back = 9007199254740992
same after round trip = false
max int exact = true
int overflow sum = -294967296
long safe sum = 4000000000
double sum = 4.0E9
long overflow sum = -9223372036854775808
```

**Ba loại hiện tượng phải phân biệt:**

1. **Widening `long → double` bị làm tròn**: `2^53 + 1` trở thành `2^53`. Không có ngoại lệ tự động cảnh báo vì đây là phép chuyển primitive hợp lệ.
2. **Tổng `int` bị overflow**: cộng hai số `2_000_000_000` trả số âm `-294967296` theo phép tính `int`. Chuyển các phần tử thành `long` **trước khi tổng** trả `4000000000`.
3. **Tổng `long` cũng có thể overflow**: `Long.MAX_VALUE + 1` cho `Long.MIN_VALUE` theo toán học modulo của kiểu nguyên. `asLongStream` không làm `long` có miền giá trị vô hạn.

`IntStream.asDoubleStream().sum()` cũng cho `4.0E9` trong ví dụ này vì các số và tổng này còn biểu diễn chính xác, nhưng đó không phải cơ sở để thay `long` bằng `double` cho mọi bài toán số nguyên.

## 7. Thứ tự chuyển kiểu và phép toán: “widen sau” không chữa overflow trước đó

Không chỉ cần chọn đúng kiểu đích, mà phải chuyển đúng **thời điểm**.

Xét việc nhân `2_000_000_000` với `3`:

```text
Sai thứ tự: int * int → có thể overflow → asLongStream() giữ nguyên số đã sai.
Đúng thứ tự: int → asLongStream() → long * long → nhận 6000000000 trong miền long.
```

Tạo tệp `ConversionOrderDemo.java`:

```java
import java.util.stream.IntStream;

public class ConversionOrderDemo {
    public static void main(String[] args) {
        int n = 2_000_000_000;

        long after = IntStream.of(n)
                .map(x -> x * 3)
                .asLongStream()
                .sum();

        long before = IntStream.of(n)
                .asLongStream()
                .map(x -> x * 3L)
                .sum();

        long direct = IntStream.of(n)
                .mapToLong(x -> x * 3L)
                .sum();

        System.out.println("multiply before widen = " + after);
        System.out.println("widen before multiply = " + before);
        System.out.println("mapToLong = " + direct);
    }
}
```

```bash
javac -encoding UTF-8 ConversionOrderDemo.java
java ConversionOrderDemo
```

```text
multiply before widen = 1705032704
widen before multiply = 6000000000
mapToLong = 6000000000
```

`map(x -> x * 3)` chạy trên `IntStream` nên phép nhân dùng `int`, tràn số trước khi `asLongStream` chạy. `mapToLong(x -> x * 3L)` khiến biểu thức nhân được đánh giá trong miền `long`; đây là cách trực tiếp khi cần vừa đổi kiểu vừa tính toán.

Nguyên tắc tổng quát: **kiểu của biểu thức trong lambda quyết định phép tính**, không chỉ kiểu của stream ở phía sau. Cùng lý do, `(long) (a * b)` vẫn có thể tràn nếu `a` và `b` là `int`; `(long) a * b` mới mở rộng một toán hạng trước phép nhân.

Nếu phép tính còn có thể vượt `long`, hãy dùng `Math.multiplyExact`/`Math.addExact` để phát hiện tràn khi phù hợp, hoặc dùng `BigInteger`/`BigDecimal` tùy miền bài toán.

## 8. Khi nào chọn `mapToLong`, `mapToDouble`, `boxed` hoặc `mapToObj`?

`asLongStream` và `asDoubleStream` chỉ đơn thuần đổi kiểu theo Java primitive widening. Các phương thức `mapTo*` linh hoạt hơn, vì callback có thể biến đổi từng giá trị:

| Mục đích | Ví dụ |
| --- | --- |
| Chỉ đổi `int → long` | `intStream.asLongStream()` |
| Nhân từng số nguyên, tính trong miền `long` | `intStream.mapToLong(x -> x * 1000L)` |
| Chỉ đổi `int → double` | `intStream.asDoubleStream()` |
| Tính phân số từ `int` | `intStream.mapToDouble(x -> x / 4.0)` |
| Chỉ đổi `long → double` | `longStream.asDoubleStream()`, có thể mất chính xác |
| Chia đổi đơn vị với `long` | `longStream.mapToDouble(x -> x / 1000.0)`, cần cân nhắc sai số |
| Đưa primitive vào API yêu cầu wrapper | `intStream.boxed()` / `longStream.boxed()` |
| Tạo chuỗi hoặc object theo từng số | `intStream.mapToObj(String::valueOf)` |
| Chuyển `Stream<Integer>` trở lại primitive | `streamOfInteger.mapToInt(Integer::intValue)`, chú ý phần tử null |

Ví dụ:

```java
double[] quarters = IntStream.of(10, 20)
        .mapToDouble(x -> x / 4.0)
        .toArray();
// [2.5, 5.0]

List<Long> boxed = IntStream.of(5, 6)
        .asLongStream()
        .boxed()
        .toList();
// [5, 6], kiểu List<Long> (Java 16+ Stream.toList)
```

Đây là **đoạn mã minh họa đặt trong phương thức** có import `java.util.List` và `java.util.stream.IntStream`. Dùng `boxed()` khi API cần wrapper/`Stream<T>`, nhưng nên giữ primitive stream trong đường xử lý số lớn nếu không cần tạo wrapper. `Stream.toList()` có từ Java 16; trên Java 8 có thể dùng `collect(Collectors.toList())` cho reference stream.

Cần phân biệt **ép kiểu để phục vụ API** và **biến đổi nghiệp vụ**. Chẳng hạn đổi đơn vị mét sang kilômét hoặc tiền từ cents sang đơn vị lớn hơn đòi hỏi quy tắc chia/làm tròn riêng. `asDoubleStream` không tự biết tỷ lệ hoặc độ chính xác mong muốn.

## 9. Chuyển xuống kiểu hẹp: không có `asIntStream`, phải quyết định cách mất dữ liệu

Chiều `long → int` hoặc `double → int/long` không phải widening và không có các phương thức `as...` tương ứng. Khi cần chuyển xuống, dùng `mapToInt`/`mapToLong` với callback và kiểm soát kết quả.

### 9.1. `long → int`: cast có thể thay đổi giá trị

`(int) someLong` chỉ giữ 32 bit thấp của giá trị `long` (theo quy tắc narrowing), nên số nằm ngoài miền `int` có thể thành số âm hoặc giá trị khác:

```java
int wrapped = LongStream.of(2_147_483_648L)
        .mapToInt(x -> (int) x)
        .findFirst()
        .orElseThrow();
// wrapped == -2147483648
```

Nếu **không cho phép mất dữ liệu**, dùng `Math.toIntExact(long)` (có từ Java 8). Với giá trị vượt miền `int`, nó ném `ArithmeticException` và giúp phát hiện lỗi dữ liệu thay vì âm thầm làm sai.

```java
int exact = LongStream.of(123L)
        .mapToInt(Math::toIntExact)
        .findFirst()
        .orElseThrow();
// exact == 123
```

### 9.2. `double → int/long`: bỏ phần lẻ và xử lý giá trị đặc biệt

Với cast số thực sang số nguyên:
- Số hữu hạn có phần lẻ: **cắt phần lẻ về phía 0**, ví dụ `3.9 → 3` và `-3.9 → -3`; đây không phải `Math.round`.
- `Double.NaN`: cast sang `int` hoặc `long` cho `0`.
- Giá trị vượt miền hoặc vô cực: kết quả cast bị giới hạn về giá trị cực trị của kiểu đích (ví dụ `double` dương quá lớn sang `int` cho `Integer.MAX_VALUE`).
- Kiểu số nguyên đích không giữ được trạng thái NaN, vô cực hay phần thập phân; nên **kiểm tra `Double.isFinite`, khoảng giá trị và quy tắc làm tròn** nếu API yêu cầu chính xác, rồi mới chuyển.

Không thể “chữa” `long → double` mất chính xác bằng cách dùng `mapToLong(d -> (long) d)` sau đó: dữ liệu gốc đã được làm tròn trước.

### Ví dụ Java 17+ đầy đủ: cả widening, boxing và narrowing

Tạo tệp `NarrowingDemo.java`:

```java
import java.util.Arrays;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class NarrowingDemo {
    public static void main(String[] args) {
        int[] trunc = DoubleStream.of(3.9, -3.9, Double.NaN, 1e100)
                .mapToInt(x -> (int) x)
                .toArray();
        System.out.println("double to int = " + Arrays.toString(trunc));

        int wrapped = LongStream.of(2_147_483_648L)
                .mapToInt(x -> (int) x)
                .findFirst()
                .orElseThrow();
        System.out.println("long to int cast = " + wrapped);

        try {
            LongStream.of(2_147_483_648L)
                    .mapToInt(Math::toIntExact)
                    .sum();
        } catch (ArithmeticException e) {
            System.out.println("toIntExact = ArithmeticException");
        }

        System.out.println("boxed longs = "
                + IntStream.of(5, 6).asLongStream().boxed().toList());
        System.out.println("map numeric = "
                + Arrays.toString(
                        IntStream.of(10, 20)
                                .mapToDouble(x -> x / 4.0)
                                .toArray()));
    }
}
```

```bash
javac -encoding UTF-8 NarrowingDemo.java
java NarrowingDemo
```

```text
double to int = [3, -3, 0, 2147483647]
long to int cast = -2147483648
toIntExact = ArithmeticException
boxed longs = [5, 6]
map numeric = [2.5, 5.0]
```

Đây là ví dụ **quan sát hành vi** của cast và ngoại lệ, không phải khuyến nghị âm thầm chuyển NaN hay số quá miền thành số nguyên. Trong hệ thống thực tế, đặt chính sách từ chối/kiểm tra dữ liệu trước bước `mapToInt`/`mapToLong`.

## 10. Hành vi của pipeline: rỗng, lazy, thứ tự và tái sử dụng

### 10.1. Chuyển kiểu không tự sinh thêm phần tử

`IntStream.empty().asLongStream()` trả `LongStream` rỗng; `IntStream.empty().asDoubleStream()` và `LongStream.empty().asDoubleStream()` trả `DoubleStream` rỗng. Không xuất hiện số `0` hoặc `0.0` giả chỉ do chuyển kiểu.

Tuy nhiên terminal operation có quy tắc riêng:

| Pipeline rỗng | Terminal | Kết quả |
| --- | --- | --- |
| `IntStream.empty().asLongStream()` | `sum()` | `0L` |
| `IntStream.empty().asDoubleStream()` | `sum()` | `0.0` |
| `IntStream.empty().asDoubleStream()` | `average()` | `OptionalDouble.empty()` |
| `LongStream.empty().asDoubleStream()` | `findFirst()` | `OptionalDouble.empty()` |
| `IntStream.empty().asLongStream()` | `findFirst()` | `OptionalLong.empty()` |
| `IntStream.empty().asLongStream()` | `count()` | `0L` |

`OptionalDouble.empty()` và `OptionalLong.empty()` biểu diễn **không có phần tử**; gọi `getAsDouble()` hoặc `getAsLong()` trên Optional rỗng sẽ ném `NoSuchElementException`. Đừng nhầm “không có kết quả” với phép chuyển tự sinh giá trị 0.

### 10.2. Lazy và single-use

Các `asLongStream`/`asDoubleStream` là intermediate operations. Chúng không lưu sẵn toàn bộ dữ liệu thành một collection và không chạy mapper nghiệp vụ tùy ý cho đến khi terminal operation cần dữ liệu. Đừng dựa vào tác động phụ của `peek` hoặc `map` để kết luận số lần phần tử được xử lý: tối ưu hóa của pipeline có thể bỏ qua callback không cần thiết hoặc dừng sớm nếu terminal dạng short-circuit.

Một `Stream` chỉ dùng cho một lần xử lý terminal:

```java
IntStream source = IntStream.of(1, 2, 3);
long sum = source.asLongStream().sum(); // 6L
// source.asDoubleStream().sum();       // Sai: source đã bị tiêu thụ.
```

Mỗi lần muốn phép tính mới từ nguồn có thể tái tạo (như `List` hoặc array), tạo Stream mới. Không tái sử dụng pipeline đã tiêu thụ hoặc đã đóng.

### 10.3. Thứ tự và song song

Các phép widening chuyển từng phần tử, không tự sắp xếp hoặc đảo phần tử. Khi nguồn có **encounter order**, pipeline như `IntStream.rangeClosed(1, 4).asLongStream().filter(...).toArray()` giữ thứ tự phần tử tương ứng. Với nguồn không có thứ tự xác định, không được suy luận thứ tự ổn định chỉ từ việc chuyển kiểu.

`parallel()` là chế độ thực thi, không phải quy tắc thay đổi giá trị. Nhưng tính toán floating-point không có tính kết hợp chính xác như phép cộng số nguyên trong miền an toàn; thứ tự gom nhóm tính tổng song song có thể ảnh hưởng chữ số làm tròn. Không dùng `parallel()` với kỳ vọng tăng tốc mặc định khi dữ liệu nhỏ; đo đạc và kiểm chứng yêu cầu chính xác nếu có.

## 11. Các lỗi thiết kế thường gặp

1. **Cho rằng widening luôn chính xác.** `int → long` và `int → double` giữ từng giá trị; `long → double` có thể làm tròn. Widening nghĩa là đổi sang kiểu có miền biểu diễn rộng hơn, **không hứa mọi giá trị nguồn vẫn nguyên vẹn**.
2. **Dùng `IntStream.sum()` rồi mới ép `long`.** `long total = (long) intStream.sum();` vẫn có thể nhận giá trị `int` đã overflow. Chuyển từng phần tử bằng `asLongStream()` trước terminal.
3. **Nhân trong `IntStream.map` rồi mới `asLongStream`.** Biểu thức `x * 3` thực thi ở miền `int`; nếu tràn thì chuyển `long` sau đó không giúp. Chuyển trước hoặc dùng `mapToLong(x -> x * 3L)`.
4. **Dùng `asDoubleStream()` cho mã định danh `long`.** Những ID lớn hơn ngưỡng chính xác của `double` có thể bị gộp thành một giá trị. Giữ dạng `long`/`String` cho ID, không dùng phép tính dấu phẩy động để thay thế.
5. **Dùng `double` như số tiền thập phân chính xác.** `double` là binary floating-point, không biểu diễn chính xác mọi số thập phân, có thể làm tròn. Khi đòi hỏi chính xác kế toán, chọn biểu diễn phù hợp như `BigDecimal`, số nguyên đơn vị nhỏ nhất, quy tắc làm tròn/miền giá trị rõ ràng.
6. **Trộn lẫn boxing và widening.** `boxed()` trả reference stream như `Stream<Integer>`; `asLongStream()` trả primitive `LongStream`. Kiểu đầu ra quyết định những API tiếp theo có thể gọi.
7. **Cho rằng `DoubleStream` có `asLongStream()`.** API không có chiều chuyển xuống tự động này; dùng `mapToLong` với chính sách xử lý phần thập phân, NaN, vô cực và phạm vi.
8. **Cast `long` xuống `int` không kiểm tra.** Giá trị ngoài miền `int` có thể đổi dấu; dùng `Math.toIntExact` nếu cần kết quả nguyên chính xác và muốn phát hiện tràn.
9. **Coi kết quả `sum() == 0` trên Stream rỗng là một phần tử thực.** Terminal `sum` trả giá trị trung hòa khi rỗng; dùng `count`/`Optional` nếu nghiệp vụ cần phân biệt “không có dữ liệu”.
10. **Tính `average()` rồi gọi `getAsDouble()` không kiểm tra.** `average()` trả `OptionalDouble`, nguồn rỗng sẽ không có giá trị. Chọn xử lý `isPresent`/`orElse`/`orElseThrow` theo yêu cầu.
11. **Giả định double sum giống phép cộng nguyên.** Kể cả khi từng số `int` chuyển chính xác, cộng nhiều số `double` có thể bị làm tròn và chịu khác biệt thứ tự tính toán. Yêu cầu tổng nguyên chính xác thì dùng miền nguyên đủ lớn hoặc số học độ chính xác tùy ý.
12. **Dùng lại cùng primitive Stream sau terminal.** `sum`, `toArray`, `average` đều là terminal operation; tạo pipeline mới từ nguồn mỗi lần muốn tính thêm.

## 12. Chọn cách chuyển kiểu trong thực tế

| Tình huống | Gợi ý | Lý do |
| --- | --- | --- |
| Cộng nhiều lượng `int`, tổng có thể vượt 2,1 tỷ | `intStream.asLongStream().sum()` | Widen trước khi cộng, giữ số nguyên chính xác trong miền `long` |
| Đổi các giá trị `int` sang `double` để tính tỷ lệ | `asDoubleStream()` hoặc `mapToDouble` | Mỗi `int` chuyển chính xác; phép tính thực có thể làm tròn |
| Chỉ tính trung bình các `int` | `intStream.average()` | API trả ngay `OptionalDouble`, không cần dựng DoubleStream |
| Giữ mã ID `long` lớn | Duy trì `long` hoặc chuỗi | `long → double` không đảm bảo giữ mọi giá trị |
| Nhân `int` với hệ số lớn, cần kết quả `long` | `mapToLong(x -> x * factorLong)` | Biểu thức tính trong miền `long` |
| Gọi API yêu cầu `Stream<Long>` | `intStream.asLongStream().boxed()` | Widen primitive rồi boxing khi thực sự cần |
| Chuyển `long` về `int` khi dữ liệu phải đúng nguyên vẹn | `longStream.mapToInt(Math::toIntExact)` | Báo lỗi nếu vượt miền `int` |
| Chuyển `double` về số nguyên | Kiểm tra hữu hạn, phần thập phân, miền rồi `mapToLong/mapToInt` | Cast có thể cắt phần lẻ và bão hòa giá trị vượt miền |
| Tổng giá trị vượt miền `long` hoặc tiền cần chính xác | `BigInteger`/`BigDecimal` sau khi chọn cấu trúc dữ liệu | Primitive stream không hỗ trợ số học chính xác vô hạn |

## 13. Bài tập tự kiểm tra

**Câu 1.** `IntStream.of(Integer.MAX_VALUE).asDoubleStream().findFirst()` có mất chữ số nguyên không?  
**Đáp án:** Không. Mọi `int` đều được biểu diễn chính xác bằng `double`. Nhưng các phép tính `double` sau đó vẫn có thể làm tròn.

**Câu 2.** `LongStream.of(9_007_199_254_740_993L).asDoubleStream()` có giữ đúng `2^53 + 1` không?  
**Đáp án:** Không. Số này làm tròn thành giá trị biểu diễn được ở `2^53`. Không dùng kết quả chuyển kiểu để so sánh ID nguyên lớn.

**Câu 3.** Vì sao `IntStream.of(2_000_000_000, 2_000_000_000).sum()` không bằng `4_000_000_000`?  
**Đáp án:** Terminal `sum` trên `IntStream` trả `int` và tràn miền. Dùng `asLongStream().sum()` trước phép cộng nếu tổng nằm trong miền `long`.

**Câu 4.** `IntStream.of(2_000_000_000).map(x -> x * 3).asLongStream().sum()` có an toàn không?  
**Đáp án:** Không. Phép nhân dùng `int` và đã tràn trước khi widening. Dùng `asLongStream().map(x -> x * 3L)` hoặc `mapToLong(x -> x * 3L)`.

**Câu 5.** `IntStream.empty().asDoubleStream().average()` trả giá trị gì?  
**Đáp án:** `OptionalDouble.empty()`. Không có giá trị trung bình cho nguồn rỗng.

**Câu 6.** Có `DoubleStream.asLongStream()` không?  
**Đáp án:** Không. Dùng `mapToLong` với quy tắc chuyển được kiểm soát; cast mặc định có thể bỏ phần thập phân hoặc mất thông tin.

**Câu 7.** `LongStream.of(2_147_483_648L).mapToInt(x -> (int) x)` tạo số nào, và có lựa chọn nào phát hiện lỗi?  
**Đáp án:** `-2147483648` do narrowing. Dùng `mapToInt(Math::toIntExact)` để ném `ArithmeticException` nếu vượt miền.

**Câu 8.** `IntStream.asLongStream()` có giống `IntStream.boxed()` không?  
**Đáp án:** Không. Phương thức đầu trả `LongStream` primitive với phần tử `long`; phương thức sau trả `Stream<Integer>` chứa wrapper.

## 14. Ghi nhớ

- `IntStream.asLongStream()`: **`int → long` chính xác** cho từng phần tử.
- `IntStream.asDoubleStream()`: **`int → double` chính xác** cho từng phần tử, nhưng phép tính trên `double` có thể làm tròn.
- `LongStream.asDoubleStream()`: **`long → double` có thể mất độ chính xác**, đặc biệt với số nguyên vượt ngưỡng 53 bit độ chính xác.
- **Đổi kiểu trước phép toán** nếu muốn phép toán diễn ra ở miền rộng hơn; đổi sau khi overflow không cứu được giá trị.
- `mapToLong`/`mapToDouble` dùng khi cần ánh xạ có logic; `boxed` dùng khi cần đối tượng wrapper; `mapToInt`/`mapToLong` cho narrowing đòi hỏi chính sách an toàn.
- Stream rỗng vẫn rỗng sau chuyển kiểu; terminal operations như `sum`/`average` có quy tắc kết quả riêng. Primitive stream là pipeline dùng một lần.
- Với ID nguyên, số tiền và số lượng đòi hỏi chính xác, chọn kiểu dữ liệu theo miền và chính sách sai số, không dùng `double` chỉ vì nó chứa được giá trị lớn.

### Tài liệu Java API chính thức còn áp dụng

- [`IntStream`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html): `asLongStream`, `asDoubleStream`, `mapToLong`, `mapToDouble`, `boxed`, `sum`, `average`.
- [`LongStream`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/LongStream.html): `asDoubleStream`, `mapToInt`, `mapToDouble` và các terminal operations.
- [`DoubleStream`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/DoubleStream.html): `mapToInt`, `mapToLong`, `sum`, `average`.
- [Java Language Specification — Widening Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se26/html/jls-5.html#jls-5.1.2): chuyển `int → long/double`, `long → double` và quy tắc mất độ chính xác.
- [Java Language Specification — Narrowing Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se26/html/jls-5.html#jls-5.1.3): chuyển `long → int` và `double → int/long`.
- [`Math.toIntExact`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html): chuyển `long` sang `int` và báo overflow.
