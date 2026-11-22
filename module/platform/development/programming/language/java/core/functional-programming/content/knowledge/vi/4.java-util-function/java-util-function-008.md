# Các biến thể primitive cho `int`, `long`, `double` và `boolean` trong `java.util.function`

## 1. Bối cảnh: vì sao Java có các functional interface chuyên biệt?

Các interface tổng quát như `Function<T,R>`, `Predicate<T>`, `Consumer<T>`, `Supplier<T>`, `UnaryOperator<T>` và `BinaryOperator<T>` hoạt động với **kiểu tham chiếu**. Java generics không nhận kiểu nguyên thủy làm type argument: `Function<int,int>` không hợp lệ. Nếu dùng `Function<Integer,Integer>`, các giá trị `int` có thể phải chuyển giữa `int` và wrapper `Integer` (*boxing/unboxing*).

Để biểu diễn trực tiếp phép xử lý số nguyên, số thực và điều kiện boolean, JDK cung cấp các functional interface chuyên biệt trong **`java.util.function`**:

- `Int...`: nhận/trả về `int` trong các vị trí được chuyên biệt.
- `Long...`: nhận/trả về `long`.
- `Double...`: nhận/trả về `double`.
- `...ToIntFunction`, `...ToLongFunction`, `...ToDoubleFunction`: chuyển kết quả sang primitive tương ứng.
- `BooleanSupplier`: cung cấp trực tiếp một `boolean`, không có đầu vào.

Các biến thể này giữ **contract kiểu** rõ ràng, giúp tránh boxing/unboxing không cần thiết ở phần được chuyên biệt hóa và khớp với `IntStream`, `LongStream`, `DoubleStream`. Tuy nhiên, chúng **không tự đảm bảo hiệu năng nhanh hơn trong mọi tình huống**: chi phí tính toán, I/O, tạo object, số phần tử và JVM tối ưu hóa vẫn quyết định kết quả thực tế.

> **Ranh giới quan trọng:** không có bộ biến thể `BooleanFunction`, `BooleanConsumer`, `BooleanPredicate` hay `BooleanStream` tiêu chuẩn trong Java 17. `boolean` được hỗ trợ trực tiếp ở **kết quả** của `Predicate` và các predicate primitive, cùng `BooleanSupplier` cho trường hợp không nhận tham số. Các trường hợp nhận boolean làm đầu vào thường dùng `Boolean` với generic interface, hoặc tự định nghĩa functional interface nhỏ khi thật sự cần tránh boxing.

## 2. Tổng quan interface theo mục đích

| Nhu cầu | Với `int` | Với `long` | Với `double` |
| --- | --- | --- | --- |
| Một primitive → chính primitive ấy | `IntUnaryOperator`: `applyAsInt(int)` | `LongUnaryOperator`: `applyAsLong(long)` | `DoubleUnaryOperator`: `applyAsDouble(double)` |
| Hai primitive cùng kiểu → một kết quả cùng kiểu | `IntBinaryOperator`: `applyAsInt(int,int)` | `LongBinaryOperator`: `applyAsLong(long,long)` | `DoubleBinaryOperator`: `applyAsDouble(double,double)` |
| Primitive → `boolean` | `IntPredicate`: `test(int)` | `LongPredicate`: `test(long)` | `DoublePredicate`: `test(double)` |
| Primitive → không trả kết quả | `IntConsumer`: `accept(int)` | `LongConsumer`: `accept(long)` | `DoubleConsumer`: `accept(double)` |
| Không có đầu vào → primitive | `IntSupplier`: `getAsInt()` | `LongSupplier`: `getAsLong()` | `DoubleSupplier`: `getAsDouble()` |
| Primitive → kiểu tham chiếu `R` | `IntFunction<R>`: `apply(int)` | `LongFunction<R>`: `apply(long)` | `DoubleFunction<R>`: `apply(double)` |

Hai họ bổ sung nối giữa **kiểu tham chiếu** và **kiểu nguyên thủy**:

| Kiểu | Chữ ký chức năng chính | Ví dụ |
| --- | --- | --- |
| `ToIntFunction<T>` | `int applyAsInt(T)` | Chuỗi → độ dài |
| `ToLongFunction<T>` | `long applyAsLong(T)` | Đơn hàng → số mili giây xử lý |
| `ToDoubleFunction<T>` | `double applyAsDouble(T)` | Đối tượng đo lường → cân nặng |
| `ToIntBiFunction<T,U>` | `int applyAsInt(T,U)` | Hai đối tượng → chỉ số nguyên |
| `ToLongBiFunction<T,U>` | `long applyAsLong(T,U)` | Hai đối tượng → kết quả `long` |
| `ToDoubleBiFunction<T,U>` | `double applyAsDouble(T,U)` | Hai đối tượng → kết quả `double` |

**Không nhầm vị trí primitive:**

```java
IntFunction<String> label = score -> "score=" + score;
// int -> String; gọi label.apply(80)

ToIntFunction<String> length = String::length;
// String -> int; gọi length.applyAsInt("Java")
```

`IntFunction<R>` chuyên biệt **đầu vào**, còn `ToIntFunction<T>` chuyên biệt **đầu ra**. Tương tự với `LongFunction`/`ToLongFunction` và `DoubleFunction`/`ToDoubleFunction`. Đoạn trên cần import `java.util.function.IntFunction` và `java.util.function.ToIntFunction`, đặt trong phương thức hoặc `jshell`.

## 3. Các phép biến đổi giữa những kiểu primitive

Khi muốn đi từ một primitive sang **primitive khác**, Java có sáu interface:

| Chuyển đổi | Interface | Phương thức |
| --- | --- | --- |
| `int → long` | `IntToLongFunction` | `long applyAsLong(int)` |
| `int → double` | `IntToDoubleFunction` | `double applyAsDouble(int)` |
| `long → int` | `LongToIntFunction` | `int applyAsInt(long)` |
| `long → double` | `LongToDoubleFunction` | `double applyAsDouble(long)` |
| `double → int` | `DoubleToIntFunction` | `int applyAsInt(double)` |
| `double → long` | `DoubleToLongFunction` | `long applyAsLong(double)` |

Ví dụ:

```java
IntToLongFunction secondsToNanos = s -> s * 1_000_000_000L;
LongToDoubleFunction toBillions = n -> n / 1_000_000_000.0;
LongToIntFunction checkedLongToInt = Math::toIntExact;
DoubleToLongFunction metersToMillimeters = m -> Math.round(m * 1000);

System.out.println(secondsToNanos.applyAsLong(3)); // 3000000000
System.out.println(toBillions.applyAsDouble(2_500_000_000L)); // 2.5
System.out.println(checkedLongToInt.applyAsInt(42L)); // 42
System.out.println(metersToMillimeters.applyAsLong(1.25)); // 1250
```

Đoạn này đặt trong phương thức có import `java.util.function.*`. Biến đổi kiểu là **quy tắc nghiệp vụ rõ ràng**, không mặc định an toàn cho mọi giá trị:

- `long → int` có thể vượt phạm vi `int`. `(int) longValue` có thể làm mất bit; `Math.toIntExact` ném `ArithmeticException` nếu vượt giới hạn.
- `int/long → double` có thể mất độ chính xác với số nguyên lớn vì `double` chỉ có độ chính xác hữu hạn (53 bit significand).
- `double → int/long` cần chọn **quy tắc làm tròn**. Ép kiểu và `Math.round` không tương đương. `Math.round(double)` trả `long`, không phải `int`.
- Khi chuyển đơn vị, hãy kiểm tra overflow của phép nhân: dùng literal `1_000_000_000L` để phép nhân `int → long` ở ví dụ được thực hiện theo số học `long`.

## 4. Các phép chuyên biệt với `boolean`

Trong Java, kiểu `boolean` có hai giá trị logic `true`/`false`. Không dùng `0`/`1` như boolean, và không có `BooleanStream` trong JDK 17.

### `BooleanSupplier`: nguồn cung cấp boolean không có đầu vào

```java
import java.util.function.BooleanSupplier;

BooleanSupplier featureEnabled = () -> true;
boolean enabled = featureEnabled.getAsBoolean(); // true
```

`getAsBoolean()` phù hợp khi cần hoãn việc đọc một **điều kiện không có tham số**; chẳng hạn hỏi một provider xem tính năng đang bật hay không. Nếu lambda đọc trạng thái cấu hình đang thay đổi, kết quả ở các lần gọi có thể khác nhau; `BooleanSupplier` không bảo đảm tính thuần hay thread safety.

### `Predicate` và các predicate primitive trả boolean

```java
IntPredicate atLeast70 = value -> value >= 70;
LongPredicate positiveId = id -> id > 0L;
DoublePredicate finite = Double::isFinite;

System.out.println(atLeast70.test(85));         // true
System.out.println(positiveId.test(-1L));       // false
System.out.println(finite.test(Double.NaN));    // false
```

`IntPredicate`, `LongPredicate` và `DoublePredicate` có các phương thức mặc định `and`, `or`, `negate` để ghép điều kiện. `and` và `or` **đánh giá ngắn mạch**: nếu kết quả đã xác định thì predicate phía sau không cần chạy. Không nên dựa vào side effect bên trong predicate để chắc chắn một đoạn mã sẽ được thực thi.

```java
IntPredicate between0And100 =
        ((IntPredicate) n -> n >= 0).and(n -> n <= 100);

System.out.println(between0And100.test(80));  // true
System.out.println(between0And100.test(120)); // false
```

### Nếu boolean là **đầu vào** thì sao?

JDK không cung cấp `BooleanFunction<R>` hay `BooleanConsumer` trong `java.util.function`. Có thể dùng wrapper `Boolean`:

```java
Function<Boolean, String> stateLabel =
        value -> Boolean.TRUE.equals(value) ? "ON" : "OFF";

System.out.println(stateLabel.apply(Boolean.TRUE));  // ON
System.out.println(stateLabel.apply(Boolean.FALSE)); // OFF
System.out.println(stateLabel.apply(null));          // OFF
```

Đây là lựa chọn cố ý: `Boolean.TRUE.equals(value)` xử lý cả `null` theo quy ước “không phải TRUE thì OFF”. Nếu `null` cần được xem là lỗi, hãy xác thực đầu vào và ném exception thay vì âm thầm chọn OFF. Với nhiều giá trị boolean, có thể xử lý `Stream<Boolean>` nhưng phải hiểu đó là **stream đối tượng wrapper**, khác ba primitive stream `IntStream`, `LongStream`, `DoubleStream`.

Khi bắt buộc biểu diễn hợp đồng `boolean → boolean` mà không boxing, có thể tự định nghĩa:

```java
@FunctionalInterface
interface BooleanOperator {
    boolean apply(boolean value);
}
```

Đây là **interface do ứng dụng tự tạo**, không phải một interface của JDK. Với các trường hợp đơn giản, dùng `boolean` trực tiếp thường sáng sủa hơn thiết kế abstraction riêng.

## 5. Chương trình Java 17 hoàn chỉnh: lọc, biến đổi, tổng hợp bằng primitive

Tạo tệp **`PrimitiveFunctionsDemo.java`** và chép toàn bộ chương trình sau. Ví dụ chỉ dùng JDK, chạy với Java 17 trở lên.

```java
import java.util.Arrays;
import java.util.function.*;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class PrimitiveFunctionsDemo {
    public static void main(String[] args) {
        // int: lọc điểm qua môn, thưởng tối đa đến 100.
        IntPredicate passing = score -> score >= 70;
        IntUnaryOperator bonus = score -> Math.min(100, score + 5);
        int[] scores = IntStream.of(42, 70, 85, 100)
                .filter(passing)
                .map(bonus)
                .toArray();
        System.out.println("Int result: " + Arrays.toString(scores));

        IntToLongFunction secondsToNanos =
                seconds -> seconds * 1_000_000_000L;
        System.out.println("Int to long: "
                + secondsToNanos.applyAsLong(3));

        ToIntFunction<String> textLength = String::length;
        IntFunction<String> scoreLabel = n -> "S-" + n;
        System.out.println("ToIntFunction: "
                + textLength.applyAsInt("Java"));
        System.out.println("IntFunction: " + scoreLabel.apply(75));

        // Chứng minh thứ tự thực thi của andThen/compose.
        IntUnaryOperator doubleIt = x -> x * 2;
        IntUnaryOperator plusThree = x -> x + 3;
        System.out.println("andThen: "
                + doubleIt.andThen(plusThree).applyAsInt(4));
        System.out.println("compose: "
                + doubleIt.compose(plusThree).applyAsInt(4));

        IntBinaryOperator add = Integer::sum;
        System.out.println("Int reduce: "
                + IntStream.rangeClosed(1, 4).reduce(0, add));

        // long: kết quả tổng có thể vượt giới hạn int.
        LongPredicate large = n -> n >= 2_000_000_000L;
        LongUnaryOperator addHundred = n -> n + 100L;
        long longTotal = LongStream.of(
                        1_500_000_000L,
                        2_000_000_000L,
                        3_000_000_000L
                )
                .filter(large)
                .map(addHundred)
                .sum();
        System.out.println("Long result: " + longTotal);

        LongToDoubleFunction toBillions =
                n -> n / 1_000_000_000.0;
        LongToIntFunction checkedLongToInt = Math::toIntExact;
        System.out.println("Long to double: "
                + toBillions.applyAsDouble(2_500_000_000L));
        System.out.println("Long to int: "
                + checkedLongToInt.applyAsInt(42L));

        // double: xử lý đại lượng đo có thể có phần thập phân.
        DoublePredicate atLeastTwo = n -> n >= 2.0;
        DoubleUnaryOperator twice = n -> n * 2.0;
        double total = DoubleStream.of(1.5, 2.0, 3.5)
                .filter(atLeastTwo)
                .map(twice)
                .sum();
        System.out.println("Double result: " + total);

        DoubleToIntFunction nearestInt =
                n -> (int) Math.round(n);
        DoubleToLongFunction metersToMillimeters =
                meters -> Math.round(meters * 1000);
        System.out.println("Double to int: "
                + nearestInt.applyAsInt(2.6));
        System.out.println("Double to long: "
                + metersToMillimeters.applyAsLong(1.25));

        // boolean: nguồn điều kiện và kết quả của predicate.
        BooleanSupplier featureEnabled = () -> true;
        System.out.println("BooleanSupplier: "
                + featureEnabled.getAsBoolean());
        System.out.println("IntPredicate: " + passing.test(69));

        Function<Boolean, String> stateLabel =
                flag -> Boolean.TRUE.equals(flag) ? "ON" : "OFF";
        System.out.println("Boxed boolean: "
                + stateLabel.apply(Boolean.TRUE));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac --release 17 PrimitiveFunctionsDemo.java
java PrimitiveFunctionsDemo
```

**Stdout chính xác**:

```text
Int result: [75, 90, 100]
Int to long: 3000000000
ToIntFunction: 4
IntFunction: S-75
andThen: 11
compose: 14
Int reduce: 10
Long result: 5000000200
Long to double: 2.5
Long to int: 42
Double result: 11.0
Double to int: 3
Double to long: 1250
BooleanSupplier: true
IntPredicate: false
Boxed boolean: ON
```

Đối chiếu đầu ra:

- `IntStream` ban đầu là `42, 70, 85, 100`. Lọc `>=70` còn `70, 85, 100`; cộng 5 và chặn ở 100 thành `75, 90, 100`.
- `doubleIt.andThen(plusThree)` trên 4 là `4 × 2 + 3 = 11`; `doubleIt.compose(plusThree)` là `(4 + 3) × 2 = 14`.
- `rangeClosed(1,4)` cho `1 + 2 + 3 + 4 = 10`.
- Với `long`, phần tử `1_500_000_000` bị loại. Hai phần tử còn lại thành `2_000_000_100 + 3_000_000_100 = 5_000_000_200`, vượt `Integer.MAX_VALUE` nhưng nằm trong phạm vi `long`.
- Với `double`, `1.5` bị loại, còn `2.0` và `3.5`; sau nhân đôi là `4.0` và `7.0`, tổng `11.0`. Các số ví dụ này biểu diễn được chính xác theo nhị phân nên kết quả trên ổn định.
- `Math.round(2.6)` là `3L`, ép sang `int` được `3`; `Math.round(1.25 × 1000)` là `1250L`.

## 6. `IntStream`, `LongStream` và `DoubleStream` liên hệ với các interface như thế nào?

Một số phương thức thông dụng của ba primitive stream:

| Pipeline operation | `IntStream` | `LongStream` | `DoubleStream` |
| --- | --- | --- | --- |
| Lọc | `filter(IntPredicate)` | `filter(LongPredicate)` | `filter(DoublePredicate)` |
| Biến đổi giữ kiểu | `map(IntUnaryOperator)` | `map(LongUnaryOperator)` | `map(DoubleUnaryOperator)` |
| Biến đổi sang object | `mapToObj(IntFunction<R>)` | `mapToObj(LongFunction<R>)` | `mapToObj(DoubleFunction<R>)` |
| Biến đổi sang primitive khác | `mapToLong(IntToLongFunction)`, `mapToDouble(IntToDoubleFunction)` | `mapToInt(LongToIntFunction)`, `mapToDouble(LongToDoubleFunction)` | `mapToInt(DoubleToIntFunction)`, `mapToLong(DoubleToLongFunction)` |
| Duyệt có hành động | `forEach(IntConsumer)` | `forEach(LongConsumer)` | `forEach(DoubleConsumer)` |
| Rút gọn hai giá trị | `reduce(IntBinaryOperator)` | `reduce(LongBinaryOperator)` | `reduce(DoubleBinaryOperator)` |
| Lấy tổng | `sum()` | `sum()` | `sum()` |

Ví dụ `IntStream.mapToObj` khác `map`:

```java
IntFunction<String> label = n -> "N=" + n;
List<String> labels = IntStream.of(1, 2, 3)
        .mapToObj(label)
        .toList();
// labels = ["N=1", "N=2", "N=3"]
```

`IntStream.map(IntUnaryOperator)` trả về **`IntStream`**; `IntStream.mapToObj(IntFunction<R>)` trả về **`Stream<R>`**. Chọn phương thức dựa vào *kiểu đầu ra*, không chỉ tên logic của hàm. Ví dụ đặt trong class/phương thức, có import `java.util.List`, `java.util.function.IntFunction` và `java.util.stream.IntStream`.

### Từ `Stream<T>` sang primitive stream

Dữ liệu thường khởi đầu là danh sách object. Dùng `mapToInt`/`mapToLong`/`mapToDouble` để chuyển một trường của object thành primitive stream rồi tổng hợp:

```java
record Product(String code, int quantity, long unitPriceInDong) {}

List<Product> items = List.of(
        new Product("BOOK", 2, 120000L),
        new Product("PEN", 3, 10000L)
);

ToLongFunction<Product> lineAmount =
        p -> p.unitPriceInDong() * p.quantity();

long total = items.stream().mapToLong(lineAmount).sum();
// total = 270000L
```

`record` khai báo trong block có thể dùng như **local record** trong phương thức Java 17; snippet cần các import `List` và `ToLongFunction`. `unitPriceInDong()` là `long`, nên phép nhân thực hiện theo số học `long`. **Vẫn có thể tràn `long`** nếu giá trị lớn; kiểm tra biên hoặc dùng `Math.multiplyExact`/`Math.addExact` khi cần phát hiện overflow. Với tiền có số lẻ thập phân, số thuế hoặc quy tắc làm tròn, có thể dùng `BigDecimal` hoặc đơn vị tiền nhỏ nhất theo hợp đồng nghiệp vụ.

## 7. Boxing và unboxing: lợi ích và những giới hạn

So sánh hai cách ghi phép nhân đôi:

```java
Function<Integer, Integer> boxedDouble = n -> n * 2;
IntUnaryOperator primitiveDouble = n -> n * 2;

int a = boxedDouble.apply(7);
int b = primitiveDouble.applyAsInt(7);
// a == 14, b == 14
```

Với `Function<Integer,Integer>`, hợp đồng ở biên là **`Integer → Integer`**. Khi thao tác số học `n * 2`, Java cần lấy giá trị primitive từ `Integer` (*unboxing*); khi trả kết quả theo kiểu `Integer`, có thể cần boxing. Với `IntUnaryOperator`, hợp đồng là `int → int`. Compiler/JIT có thể tối ưu allocation trong trường hợp cụ thể, vì vậy không nên tuyên bố mỗi lần gọi `Function<Integer,Integer>` chắc chắn cấp phát object mới.

**Unboxing `null`** là một nguồn lỗi:

```java
Function<Integer, Integer> boxedDouble = n -> n * 2;
// boxedDouble.apply(null); // NullPointerException khi unboxing n
```

Ngược lại, primitive `int`/`long`/`double`/`boolean` không biểu diễn `null`. Nếu dữ liệu nghiệp vụ cho phép trạng thái “thiếu giá trị”, cần quy ước riêng; có thể dùng wrapper hoặc `OptionalInt`, `OptionalLong`, `OptionalDouble` tùy ngữ nghĩa. `OptionalInt`/`OptionalLong`/`OptionalDouble` là **container tùy chọn cho primitive**, không phải functional interface.

### Có phải lúc nào cũng chọn primitive?

Không. Với vài phần tử hoặc API chủ yếu trao đổi object, `Function<Integer,Integer>` có thể đơn giản và tích hợp tốt. Chọn primitive interface khi:

1. Ý nghĩa dữ liệu thật sự là một primitive không nullable.
2. API được gọi tương thích, ví dụ `IntStream.map` hay `Stream.mapToInt`.
3. Muốn tránh boxing/unboxing trong đường xử lý nhiều phần tử.
4. Đã xác minh hành vi, độ chính xác và các phép biến đổi primitive phù hợp.

Nếu buộc gọi `Stream<Integer>` vì đầu vào là dữ liệu boxed, có thể dùng `mapToInt(Integer::intValue)` để mở ra các phép toán primitive; nhưng **nếu phần tử là `null`, unboxing có thể ném `NullPointerException`**.

## 8. `int` và `long`: giới hạn biểu diễn, phép cộng và conversion

`int` là số nguyên có dấu 32 bit; `long` là số nguyên có dấu 64 bit. Không có cơ chế tự động kiểm tra overflow đối với cộng/nhân thông thường. Ví dụ:

```java
IntUnaryOperator addOne = n -> n + 1;
System.out.println(addOne.applyAsInt(Integer.MAX_VALUE));
// -2147483648 (tràn int theo số học bù hai)
```

Khi overflow là lỗi nghiệp vụ, dùng các phương thức `Math.addExact`, `Math.multiplyExact`, `Math.toIntExact`:

```java
IntBinaryOperator checkedAdd = Math::addExact;
LongToIntFunction checkedNarrowing = Math::toIntExact;

System.out.println(checkedAdd.applyAsInt(20, 22)); // 42
System.out.println(checkedNarrowing.applyAsInt(42L)); // 42

// checkedAdd.applyAsInt(Integer.MAX_VALUE, 1)
// -> ArithmeticException: integer overflow
// checkedNarrowing.applyAsInt(3_000_000_000L)
// -> ArithmeticException: integer overflow
```

Các dòng gây exception được comment để không ảnh hưởng chương trình. Với `LongBinaryOperator checkedLongAdd = Math::addExact`, compiler chọn overload nhận hai `long` theo target type, phát hiện overflow của `long`. Việc `LongStream.sum()` trả `long` không có nghĩa nó tự phát hiện mọi overflow; nếu tổng có thể vượt phạm vi `long`, cần cách tính hoặc representation khác.

### `int`, `long` và tên hàm dễ nhầm

Các tên phương thức nhất quán với **kiểu trả về**:

- `IntSupplier.getAsInt()`, `LongSupplier.getAsLong()`, `DoubleSupplier.getAsDouble()`.
- `IntUnaryOperator.applyAsInt(int)`, `LongUnaryOperator.applyAsLong(long)`, `DoubleUnaryOperator.applyAsDouble(double)`.
- `IntFunction<R>.apply(int)` trả **`R`**, không phải luôn `int`.
- `ToIntFunction<T>.applyAsInt(T)`, `ToLongFunction<T>.applyAsLong(T)`, `ToDoubleFunction<T>.applyAsDouble(T)`.

Đây là lý do viết `IntFunction<String> fn = n -> "N=" + n; fn.apply(3)` mới đúng; `fn.applyAsInt(3)` không tồn tại.

## 9. `double`: precision, NaN, Infinity và phép tổng hợp

`double` là số thực dấu phẩy động nhị phân IEEE 754. Nó thích hợp với nhiều phép đo kỹ thuật, phân tích dữ liệu và những bài toán chấp nhận sai số số học dấu phẩy động. Nhưng không phải mọi số thập phân đều biểu diễn chính xác:

```java
DoubleBinaryOperator add = Double::sum;
double result = add.applyAsDouble(0.1, 0.2);
System.out.println(result); // 0.30000000000000004
```

Do đó không nên so sánh kết quả tính dấu phẩy động bằng `==` khi yêu cầu “xấp xỉ bằng nhau”; cần một tiêu chí sai số theo đơn vị và phạm vi dữ liệu. Với **tiền tệ thập phân** cần tính chính xác theo luật nghiệp vụ, ưu tiên `BigDecimal` hoặc biểu diễn số đơn vị tiền nhỏ nhất bằng số nguyên, đi kèm xử lý scale/rounding phù hợp.

### Xử lý các giá trị đặc biệt

`DoublePredicate` hữu ích để loại giá trị không hữu hạn:

```java
DoublePredicate finite = Double::isFinite;
double[] clean = java.util.stream.DoubleStream
        .of(2.5, Double.NaN, Double.POSITIVE_INFINITY, 3.5)
        .filter(finite)
        .toArray();
// clean = [2.5, 3.5]
```

- `Double.NaN` (Not a Number) không bằng chính nó theo toán tử `==`.
- `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY` biểu thị vô cực.
- `Double.isFinite` trả `false` cho NaN và các giá trị vô cực.
- `DoubleStream.sum()` có thể bị ảnh hưởng bởi thứ tự và sai số làm tròn; phép cộng dấu phẩy động không thực sự kết hợp theo mọi trường hợp. Tổng trong parallel stream có thể khác một lượng nhỏ so với stream tuần tự, dù phép toán nghiệp vụ giống nhau.
- `Math.round(double)` có quy tắc riêng cho NaN và các giá trị vượt giới hạn. Phải xác thực dữ liệu đầu vào nếu chuyển sang số nguyên là bước quan trọng.

Một ví dụ cho quy tắc giới hạn ở đầu vào:

```java
DoublePredicate accepted =
        Double::isFinite;
DoubleUnaryOperator convertMetersToCentimeters = m -> m * 100.0;

double[] centimeters = DoubleStream.of(1.5, Double.NaN, 2.25)
        .filter(accepted)
        .map(convertMetersToCentimeters)
        .toArray();
// centimeters = [150.0, 225.0]
```

## 10. Interface nhiều tham số hoặc kết hợp với object

Đôi khi một hàm phải nhận một object **và** một primitive. JDK cung cấp thêm những interface sau:

| Interface | Chữ ký | Khi hữu ích |
| --- | --- | --- |
| `ObjIntConsumer<T>` | `void accept(T,int)` | Đưa một chỉ số/số lượng `int` vào một đối tượng |
| `ObjLongConsumer<T>` | `void accept(T,long)` | Nhận object và timestamp/số lượng `long` |
| `ObjDoubleConsumer<T>` | `void accept(T,double)` | Nhận object và giá trị đo `double` |
| `ToIntBiFunction<T,U>` | `int applyAsInt(T,U)` | Tổng hợp hai object ra `int` |
| `ToLongBiFunction<T,U>` | `long applyAsLong(T,U)` | Tổng hợp hai object ra `long` |
| `ToDoubleBiFunction<T,U>` | `double applyAsDouble(T,U)` | Tổng hợp hai object ra `double` |

Ví dụ `ObjIntConsumer`:

```java
ObjIntConsumer<StringBuilder> appendNumber =
        (builder, number) -> builder.append(number);

StringBuilder builder = new StringBuilder("Order-");
appendNumber.accept(builder, 7);
System.out.println(builder); // Order-7
```

Đoạn này cố ý có **side effect cục bộ** trên `builder`. Trong thực tế, không nên để nhiều luồng cùng gọi `appendNumber` trên cùng một `StringBuilder` không được bảo vệ. Một functional interface có primitive trong signature **không có nghĩa lambda là pure, thread-safe hoặc không cấp phát**.

## 11. Những lỗi thường gặp khi học các primitive interface

**Lỗi 1 — Ghi kiểu nguyên thủy làm type argument generic.** `Function<int,long>` không biên dịch. Dùng `IntToLongFunction` hoặc `Function<Integer,Long>` tùy API.

**Lỗi 2 — Nhầm `IntFunction` với `ToIntFunction`.** Cái đầu nhận `int` và trả `R`; cái sau nhận `T` và trả `int`. Gọi nhầm `apply`/`applyAsInt` sẽ gây lỗi biên dịch.

**Lỗi 3 — Tin rằng mọi primitive đều có đủ bộ interface giống nhau.** `boolean` không có bộ `BooleanUnaryOperator`, `BooleanFunction` hay `BooleanStream` chuẩn trong `java.util.function`/`java.util.stream` của Java 17. Dùng `BooleanSupplier`, các predicate, wrapper `Boolean` hoặc interface ứng dụng theo nhu cầu.

**Lỗi 4 — Đánh đồng primitive với không thể tràn/không sai số.** `IntStream.sum` có thể tràn `int`, `LongStream.sum` có thể tràn `long`, và `DoubleStream.sum` có sai số dấu phẩy động. Lựa chọn kiểu dữ liệu không thay thế được kiểm tra miền giá trị.

**Lỗi 5 — Quên `null` trong wrapper.** `Stream<Integer>.mapToInt(Integer::intValue)` cần unboxing và có thể lỗi nếu gặp `null`. Primitive stream không có phần tử `null`; khi giá trị có thể vắng mặt, chọn chính sách biểu diễn thiếu dữ liệu rõ ràng.

**Lỗi 6 — Dùng một lambda side effect để tích lũy trong parallel stream.** `IntStream.parallel().forEach(n -> shared[0] += n)` có data race nếu nhiều thread ghi cùng phần tử mảng. Ưu tiên `sum`, `reduce` hoặc collector phù hợp; nếu thật sự cần trạng thái chung, dùng cơ chế đồng bộ và xác định quyền sở hữu.

**Lỗi 7 — Ghép `andThen`/`compose` sai thứ tự.** `IntUnaryOperator`, `LongUnaryOperator` và `DoubleUnaryOperator` có `andThen` và `compose` tương tự `UnaryOperator<T>`; kết quả khác nhau khi hai phép không giao hoán.

**Lỗi 8 — Bỏ qua điều kiện đầu vào.** `DoublePredicate` có thể nhận NaN/Infinity; `LongToIntFunction` có thể làm mất dữ liệu khi thu hẹp; `IntToLongFunction` vẫn có thể tràn `long` sau nhiều phép toán. Tách validation khỏi phép biến đổi chính hoặc làm validation rõ ràng.

**Lỗi 9 — Tưởng primitive stream luôn nhanh hơn `Stream<Integer>` trong mọi hoàn cảnh.** Primitive interface giảm nhu cầu boxing ở các bước xử lý tương ứng, nhưng pipeline có nguồn dữ liệu object, I/O hoặc biến đổi nhiều tầng vẫn có chi phí khác. Đo bằng benchmark phù hợp trước khi kết luận về hiệu năng.

**Lỗi 10 — Dùng `double` cho tiền mà không có quy tắc làm tròn.** Nếu bài toán yêu cầu biểu diễn số tiền chính xác, các interface primitive có thể không phù hợp cho *toàn bộ* pipeline tính tiền; dùng `BigDecimal` và functional interface generic khi cần.

## 12. Bài tập có kết quả đối chiếu

1. Tạo `IntPredicate` kiểm tra số chẵn và một `IntUnaryOperator` bình phương. Áp dụng trên `IntStream.rangeClosed(1,6)`: lọc được `2,4,6`, sau biến đổi thành `4,16,36`; tổng phải là `56`.
2. Viết `IntToLongFunction` chuyển số giây thành nano giây, thử `3` và giải thích vì sao literal `1_000_000_000L` quan trọng khi làm phép nhân lớn.
3. Với `LongStream.of(1_500_000_000L, 2_000_000_000L, 3_000_000_000L)`, lọc số từ 2 tỷ rồi cộng 100 cho mỗi số. Tổng đúng là `5000000200`. Vì sao `int` không phù hợp?
4. Tạo `DoublePredicate` loại `NaN`/infinity và `DoubleUnaryOperator` nhân 100. Áp dụng `DoubleStream.of(1.5, Double.NaN, 2.25)` và so kết quả với `[150.0, 225.0]`.
5. Viết `ToIntFunction<String>` trả độ dài chuỗi và `IntFunction<String>` đổi độ dài thành `"length=" + n`. Từ `Stream.of("Java", "API")`, dùng `mapToInt` rồi `mapToObj` để nhận `["length=4", "length=3"]`.
6. Giải thích khác nhau giữa `BooleanSupplier` và `IntPredicate`: interface nào nhận đầu vào? interface nào phù hợp cho `IntStream.filter`? Nêu lý do không có `BooleanStream` trong Java 17.
7. Chứng minh phép `andThen` khác `compose` với hai phép “nhân 2” và “cộng 3” khi đầu vào bằng `4`: lần lượt `11` và `14`.
8. Thử `Math.toIntExact(3_000_000_000L)` để quan sát `ArithmeticException`. Sau đó dùng `LongToIntFunction` để diễn đạt conversion có kiểm tra.
9. Xác định khi nào dùng `Function<Integer,Integer>`, khi nào dùng `IntUnaryOperator` và khi nào `ToIntFunction<T>`. Đánh giá cả kiểu đầu vào/đầu ra, nhu cầu null và API tiếp nhận mapper.

## 13. Checklist áp dụng

Khi chọn functional interface primitive, hãy trả lời theo thứ tự:

1. **Đầu vào là gì?** Một số nguyên `int`, `long`, số thực `double`, một object, hai đầu vào hay không có đầu vào?
2. **Đầu ra là gì?** `boolean`, primitive cùng kiểu, primitive khác kiểu, object hay không trả kết quả?
3. **API cần loại mapper nào?** `map`, `mapToObj`, `mapToInt`, `filter`, `forEach`, `reduce` có kiểu tham số khác nhau.
4. **Có thể có null, overflow, NaN hoặc Infinity không?** Chọn hợp đồng dữ liệu và xử lý lỗi cụ thể.
5. **Có side effect hay shared mutable state không?** Giữ pipeline dễ suy luận, đặc biệt khi dùng parallel stream.
6. **Có thực sự cần tối ưu boxing không?** Bắt đầu với API rõ ràng và đo hiệu năng khi dữ liệu đủ lớn.

Chọn đúng interface giúp chương trình thể hiện **ý nghĩa của phép biến đổi ngay trong kiểu dữ liệu**, giảm chuyển đổi không cần thiết và kết nối tự nhiên với Java Stream API. Nhưng sự đúng đắn vẫn đến từ quy tắc nghiệp vụ, giới hạn kiểu số, cách xử lý thiếu dữ liệu và việc kiểm soát tác dụng phụ.
