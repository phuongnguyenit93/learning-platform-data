# Các biến thể primitive giúp tránh boxing trong Java

Khi dùng lambda và Stream với dữ liệu số, Java có hai thế giới kiểu dữ liệu: **primitive** (`int`, `long`, `double`...) và **reference type** như `Integer`, `Long`, `Double`. Các functional interface tổng quát (`Function<T,R>`, `Predicate<T>`, `Consumer<T>`, `Supplier<T>`) sử dụng **generic type arguments**, mà Java không cho dùng primitive trực tiếp. Vì thế, đối với một số phép xử lý số, ta buộc phải dùng wrapper object hoặc chọn các **functional interface chuyên biệt cho primitive** trong `java.util.function`.

Đây không phải mẹo riêng của Java 8 đã lỗi thời: các interface như `IntUnaryOperator`, `ToIntFunction<T>` và `IntPredicate` cùng `IntStream`, `LongStream`, `DoubleStream` vẫn được sử dụng trong Java hiện đại, đặc biệt ở pipeline tính toán có nhiều phần tử. Mục tiêu là **diễn đạt đúng kiểu đầu vào/đầu ra và giảm chuyển đổi boxing/unboxing không cần thiết**; không nên tối ưu mù quáng khi dữ liệu hoặc API vốn đã cần object.

## 1. Boxing và unboxing thực sự là gì?

**Boxing** chuyển giá trị primitive thành đối tượng wrapper tương ứng, còn **unboxing** lấy primitive từ wrapper:

```java
int quantity = 5;
Integer boxed = quantity;   // autoboxing: int -> Integer
int restored = boxed;       // unboxing: Integer -> int
```

Đây là **đoạn mã minh họa**, chưa phải chương trình độc lập. Trong thực tế, wrapper thường cần khi lưu `Integer` vào `List<Integer>`, truyền vào API generic, hoặc thể hiện giá trị `null`. Nhưng khi phép toán chỉ tính số, chuỗi chuyển `int -> Integer -> int` có thể bổ sung công việc chuyển đổi và áp lực bộ nhớ nếu thực sự phát sinh object. JIT có thể tối ưu một số trường hợp, nên lợi ích hiệu năng **không phải bảo đảm tuyệt đối cho mọi chương trình**.

Ví dụ:

```java
Function<Integer, Integer> squareBoxed = x -> x * x;
IntUnaryOperator squarePrimitive = x -> x * x;
```

Đây là hai khai báo minh họa, cần `import java.util.function.*;`. Cả hai đều tính bình phương, nhưng hợp đồng khác nhau:

- `Function<Integer,Integer>.apply(Integer)` nhận và trả **wrapper**; phép nhân trong body sử dụng unboxing và kết quả có thể cần boxing.
- `IntUnaryOperator.applyAsInt(int)` nhận và trả **int**, không đòi chuyển sang `Integer` trên đường dữ liệu primitive của chính interface.

**Không thể viết `Function<int, int>`:** generic type arguments trong Java phải là reference type. Khi yêu cầu giữ primitive trên đường xử lý, chọn đúng specialization thay vì cố dùng generic với primitive.

## 2. Các họ functional interface cho int, long và double

`java.util.function` có nhiều specialization; không cần học thuộc tất cả tên. Hãy xác định **kiểu đầu vào, số lượng tham số, kiểu kết quả** rồi tìm interface tương ứng.

| Hợp đồng mong muốn | Phiên bản object/generic | Primitive specialization thường dùng | Phương thức SAM |
| --- | --- | --- | --- |
| `int -> boolean` | `Predicate<Integer>` | `IntPredicate` | `boolean test(int)` |
| `long -> boolean` | `Predicate<Long>` | `LongPredicate` | `boolean test(long)` |
| `double -> boolean` | `Predicate<Double>` | `DoublePredicate` | `boolean test(double)` |
| `int -> void` | `Consumer<Integer>` | `IntConsumer` | `void accept(int)` |
| `long -> void` | `Consumer<Long>` | `LongConsumer` | `void accept(long)` |
| `double -> void` | `Consumer<Double>` | `DoubleConsumer` | `void accept(double)` |
| `() -> int` | `Supplier<Integer>` | `IntSupplier` | `int getAsInt()` |
| `() -> long` | `Supplier<Long>` | `LongSupplier` | `long getAsLong()` |
| `() -> double` | `Supplier<Double>` | `DoubleSupplier` | `double getAsDouble()` |
| `int -> int` | `UnaryOperator<Integer>` | `IntUnaryOperator` | `int applyAsInt(int)` |
| `long -> long` | `UnaryOperator<Long>` | `LongUnaryOperator` | `long applyAsLong(long)` |
| `double -> double` | `UnaryOperator<Double>` | `DoubleUnaryOperator` | `double applyAsDouble(double)` |
| `(int,int) -> int` | `BinaryOperator<Integer>` | `IntBinaryOperator` | `int applyAsInt(int,int)` |
| `(long,long) -> long` | `BinaryOperator<Long>` | `LongBinaryOperator` | `long applyAsLong(long,long)` |
| `(double,double) -> double` | `BinaryOperator<Double>` | `DoubleBinaryOperator` | `double applyAsDouble(double,double)` |

Một vài ví dụ ngắn, **chỉ minh họa** (cần `import java.util.function.*;`):

```java
IntPredicate even = n -> n % 2 == 0;
LongPredicate positive = n -> n > 0;
DoublePredicate inRange = v -> v >= 0.0 && v <= 1.0;

IntConsumer show = System.out::println;
IntSupplier nextFixed = () -> 42;
IntUnaryOperator doubleIt = n -> n * 2;
LongBinaryOperator addLong = Long::sum;
DoubleUnaryOperator square = v -> v * v;
```

`IntPredicate.test`, `IntUnaryOperator.applyAsInt`, `DoubleUnaryOperator.applyAsDouble`... cho thấy Java dùng **tên phương thức khác nhau** để biểu thị chính xác loại kết quả. Đừng gọi `apply` lên `IntUnaryOperator` vì nó có `applyAsInt`. Đừng gọi `get` lên `IntSupplier` vì nó có `getAsInt`.

### Những primitive khác thì sao?

Các specialization chuẩn trong `java.util.function` chủ yếu bao phủ `int`, `long`, `double`. Không có một bộ tương tự đầy đủ cho từng `byte`, `short`, `char`, `float` hay `boolean`; riêng predicate biểu diễn **kết quả boolean**, không phải một `BooleanUnaryOperator` trong thư viện chuẩn. Có thể dùng phép mở rộng kiểu hợp lệ (chẳng hạn `char` hoặc `short` sang `int`) khi logic cho phép, nhưng phải tự bảo đảm ngữ nghĩa và chuyển đổi đầu ra. Nếu API đặc thù thật sự cần kiểu khác, có thể định nghĩa functional interface riêng, không nên giả định JDK có sẵn mọi biến thể.

## 3. Chuyển từ object sang primitive: ToIntFunction, ToLongFunction, ToDoubleFunction

Dữ liệu đầu vào của ứng dụng thường là object nghiệp vụ, nhưng kết quả muốn lấy là primitive. Đây là nhóm specialization thiết thực nhất:

- `ToIntFunction<T>`: `int applyAsInt(T value)`.
- `ToLongFunction<T>`: `long applyAsLong(T value)`.
- `ToDoubleFunction<T>`: `double applyAsDouble(T value)`.

Ví dụ:

```java
ToIntFunction<String> length = String::length;
int size = length.applyAsInt("Lambda"); // 6
```

Đây là đoạn minh họa cần import `java.util.function.ToIntFunction`. Nếu viết `Function<String,Integer>`, đầu ra của method reference vẫn hợp lệ nhưng phải thích ứng với wrapper `Integer`. `ToIntFunction` diễn đạt chính xác rằng kết quả là `int`.

Một ví dụ object nghiệp vụ:

```java
record Product(String name, long priceInCents) {}

ToLongFunction<Product> price = Product::priceInCents;
long cents = price.applyAsLong(new Product("Book", 1250L)); // 1250
```

Đây là đoạn minh họa, cần import `java.util.function.ToLongFunction` và đặt record/khai báo tại vị trí hợp lệ trong tệp Java. `record` có từ Java 16, nên thích hợp khi bạn biên dịch ví dụ trên Java 17+. Nếu dự án chỉ dùng Java 8, thay record bằng một class với getter tương ứng; **các functional interface `ToLongFunction` vẫn là tính năng Java 8**.

**Chọn đúng bộ đo:** `priceInCents` trả `long` vì tiền được lưu theo đơn vị nguyên nhỏ nhất; ví dụ không khẳng định `long` phù hợp cho mọi nghiệp vụ tiền tệ. Với tiền có phần lẻ và quy tắc làm tròn, thường dùng `BigDecimal` và contract riêng, không chuyển bừa thành `double` chỉ để dùng primitive.

## 4. Chuyển từ primitive sang object: IntFunction, LongFunction, DoubleFunction

Khi đầu vào là primitive nhưng kết quả là reference type, dùng:

| Interface | Phương thức | Ví dụ |
| --- | --- | --- |
| `IntFunction<R>` | `R apply(int value)` | Tạo nhãn từ chỉ số nguyên |
| `LongFunction<R>` | `R apply(long value)` | Tạo object từ thời điểm dạng `long` |
| `DoubleFunction<R>` | `R apply(double value)` | Format số thực thành chuỗi |

```java
IntFunction<String> label = n -> "item-" + n;
String text = label.apply(7); // "item-7"
```

Đây là đoạn minh họa cần import `java.util.function.IntFunction`. Mặc dù **đầu vào `int`** không cần boxing khi gọi `apply(7)`, kết quả là một `String` object theo bản chất bài toán. Dùng specialization không có nghĩa mọi object trong pipeline biến mất.

Các API JDK thường dùng `IntFunction` trong `IntStream.mapToObj` và các phép tạo mảng object. Khi cần kết quả thuộc primitive khác, chuyển qua nhóm ở phần tiếp theo để không bắt buộc tạo wrapper object ở ranh giới.

## 5. Chuyển đổi giữa các primitive và các interface hai đối số

Các phép chuyển kiểu hoặc tính tổng thường có specialization cụ thể:

- `IntToLongFunction`: `long applyAsLong(int)`.
- `IntToDoubleFunction`: `double applyAsDouble(int)`.
- `LongToIntFunction`: `int applyAsInt(long)`.
- `LongToDoubleFunction`: `double applyAsDouble(long)`.
- `DoubleToIntFunction`: `int applyAsInt(double)`.
- `DoubleToLongFunction`: `long applyAsLong(double)`.

```java
IntToLongFunction widen = n -> (long) n;
IntToDoubleFunction half = n -> n / 2.0;
LongToIntFunction narrow = n -> Math.toIntExact(n);
```

Đoạn minh họa cần `import java.util.function.*;`. `Math.toIntExact(long)` ném `ArithmeticException` nếu giá trị `long` ngoài miền `int`, đáng tin cậy hơn cast âm thầm khi việc mất dữ liệu là lỗi nghiệp vụ. Với `DoubleToIntFunction`, chuyển `double` sang `int` còn cần chính sách làm tròn, NaN, vô cực và giá trị ngoài miền; không phải “tránh boxing” là đủ để có kết quả số học đúng.

Khi có hai object và muốn trả primitive, `ToIntBiFunction<T,U>`, `ToLongBiFunction<T,U>`, `ToDoubleBiFunction<T,U>` biểu diễn chính xác hợp đồng:

```java
ToIntBiFunction<String, String> totalLength =
        (a, b) -> a.length() + b.length();
```

Đây là minh họa cần `java.util.function.ToIntBiFunction`. Cả hai đầu vào là object, nhưng kết quả là `int`.

Khi có một object và một primitive làm đầu vào, JDK có `ObjIntConsumer<T>`, `ObjLongConsumer<T>`, `ObjDoubleConsumer<T>`:

```java
ObjIntConsumer<StringBuilder> appendNumber =
        (builder, number) -> builder.append(number);
```

Đây là minh họa cần `java.util.function.ObjIntConsumer`. `StringBuilder.append(int)` hỗ trợ primitive trực tiếp, không cần chuyển sang `Integer` chỉ để nối chuỗi. Tuy nhiên, nó **sửa trạng thái StringBuilder**, vì vậy đây là hành động có tác dụng phụ có chủ đích; không dùng để thay thế phép biến đổi thuần trong Stream khi có trạng thái chia sẻ.

## 6. Primitive Stream: giữ phép toán số ở dạng nguyên thủy

Stream tổng quát `Stream<T>` mang **object references**. Java cung cấp `IntStream`, `LongStream` và `DoubleStream` để xử lý ba loại primitive phổ biến. Điều này cho phép thực hiện `sum`, `average`, `min`, `max`, `summaryStatistics` và các phép biến đổi theo primitive mà không buộc từng phần tử phải đi qua wrapper object ở các bước đó.

Ví dụ tính tổng chiều dài:

```java
List<String> names = List.of("An", "Binh", "Chi");
int total = names.stream()
        .mapToInt(String::length)
        .sum();
// total = 2 + 4 + 3 = 9
```

Đây là đoạn minh họa, cần `import java.util.List;`. `mapToInt` nhận `ToIntFunction<? super String>` và trả `IntStream`. Nếu dùng `map(String::length)`, kết quả là `Stream<Integer>`; nếu lại cộng các giá trị đó trong một pipeline object, có thể cần boxing/unboxing không cần thiết.

### map, mapToInt, mapToLong, mapToDouble

| Nguồn | Phép biến đổi | Kết quả |
| --- | --- | --- |
| `Stream<Person>` | `map(Person::name)` | `Stream<String>` |
| `Stream<Person>` | `mapToInt(Person::age)` | `IntStream` |
| `Stream<Person>` | `mapToLong(Person::id)` | `LongStream` |
| `Stream<Person>` | `mapToDouble(Person::score)` | `DoubleStream` |
| `IntStream` | `map(n -> n * n)` | `IntStream` |
| `IntStream` | `mapToLong(n -> n)` | `LongStream` |
| `IntStream` | `mapToObj(n -> "id=" + n)` | `Stream<String>` |

`Person` là kiểu miền minh họa, không phải class có sẵn trong JDK. Điểm quan trọng là **`map` có thể có ý nghĩa khác tùy kiểu nguồn**: `Stream<T>.map` nhận `Function<T,R>`, còn `IntStream.map` nhận `IntUnaryOperator`.

```java
int[] squares = IntStream.rangeClosed(1, 5)
        .map(n -> n * n)
        .toArray();
// [1, 4, 9, 16, 25]
```

Đây là đoạn minh họa cần `java.util.stream.IntStream`. `IntStream.rangeClosed(1,5)` phát các giá trị `1` đến `5` **bao gồm 5**; `range(1,5)` chỉ lấy từ `1` tới `4`. `toArray()` trả `int[]`, không phải `Integer[]`.

### boxed(): quay lại thế giới object khi cần

```java
List<Integer> numbers = IntStream.rangeClosed(1, 3)
        .boxed()
        .collect(Collectors.toList());
```

Đoạn minh họa cần `List`, `IntStream`, `Collectors`. `boxed()` chuyển `IntStream` thành `Stream<Integer>`. Đây là bước **box rõ ràng** để tích hợp với collection API generic. Việc boxing lúc này là cần thiết nếu dữ liệu thực sự cần `List<Integer>`; chuyên biệt hóa primitive giúp bạn kiểm soát nó xảy ra ở đâu, không phải cấm wrapper ở mọi nơi.

Nếu cần dữ liệu dạng mảng nguyên thủy, ưu tiên `int[] values = intStream.toArray();` thay vì `List<Integer>` chỉ để lưu các số. Nếu đầu vào vốn là `List<Integer>`, phương thức `mapToInt(Integer::intValue)` vẫn phải unbox các wrapper đã có; nó không thể xóa chi phí cấp phát object đã xảy ra trước đó.

### OptionalInt, OptionalLong, OptionalDouble

Các thao tác `min()`, `max()`, `average()` của primitive stream trả về kiểu Optional phù hợp vì Stream có thể **rỗng**:

```java
OptionalInt maximum = IntStream.of(5, 8, 2).max();
int max = maximum.orElse(0); // 8

OptionalDouble mean = IntStream.of(5, 7, 9).average();
double average = mean.orElse(0.0); // 7.0
```

Đây là đoạn minh họa, cần `java.util.OptionalInt`, `java.util.OptionalDouble` và `java.util.stream.IntStream`. Primitive Optional tránh phải gói kết quả vào `Optional<Integer>` hay `Optional<Double>`. Tuy nhiên, `orElse(0)` hoặc `orElse(0.0)` là **chính sách nghiệp vụ**, không phải lúc nào cũng đúng: với danh sách rỗng, “không có trung bình” có thể khác “trung bình bằng 0”. Khi cần phân biệt, dùng `isPresent()`/`isEmpty()` hoặc xử lý `OptionalInt`/`OptionalDouble` thích hợp.

## 7. Ghép logic với primitive operator và predicate

Các specialization không chỉ là chữ ký primitive; nhiều interface còn cung cấp default/static methods giúp ghép phép toán giống bản generic.

```java
IntUnaryOperator plusTwo = n -> n + 2;
IntUnaryOperator triple = n -> n * 3;

IntUnaryOperator step1 = plusTwo.andThen(triple);
IntUnaryOperator step2 = plusTwo.compose(triple);

// step1.applyAsInt(4) = (4 + 2) * 3 = 18
// step2.applyAsInt(4) = 4 * 3 + 2 = 14
```

Đây là minh họa cần `java.util.function.IntUnaryOperator`. `andThen` thực hiện phép toán hiện tại rồi tới toán tử sau; `compose` thực hiện toán tử đầu vào trước. Có thể dùng `IntUnaryOperator.identity()` nếu cần phép biến đổi đồng nhất. Không nên lặp lại các thao tác “chuyển sang Integer rồi về int” chỉ để ghép hàm số.

```java
IntPredicate positive = n -> n > 0;
IntPredicate even = n -> n % 2 == 0;
IntPredicate positiveEven = positive.and(even);

// positiveEven.test(4) == true
// positiveEven.test(-2) == false
```

Đây là minh họa cần `IntPredicate`. `and` và `or` có short-circuit như các toán tử logic Java; `negate` đảo predicate. Hãy để predicate dùng **kết quả boolean** chứ không giấu những thao tác sửa dữ liệu ngoài trong body.

## 8. Những lợi ích, giới hạn và hiểu nhầm về hiệu năng

**Lợi ích có cơ sở:**

- Chữ ký thể hiện chính xác giá trị là primitive hay object; người gọi không thể truyền `null` vào tham số `int`, `long` hoặc `double`.
- Đường tính toán có thể tránh một số boxing/unboxing và object trung gian không cần thiết.
- Primitive streams cung cấp reduction số học thuận tiện như `sum`, `average`, `summaryStatistics`.
- Với pipeline nhiều phần tử hoặc mã thực thi lặp lại, giảm chi phí chuyển đổi **có thể** có ý nghĩa.

**Những giới hạn phải biết:**

1. **Không phải lời hứa tăng tốc:** JIT, escape analysis, kích thước dữ liệu, bộ nhớ đệm, nhánh điều kiện, thiết bị và thuật toán đều ảnh hưởng. Khi hiệu năng quan trọng, đo benchmark đúng cách (chẳng hạn với JMH) và đánh giá allocation/GC trong workload thực.
2. **Không loại bỏ boxing ở API boundary:** `List<Integer>`, `Map<Integer, ...>`, `Stream<Integer>` hoặc dữ liệu cần giá trị `null` vẫn dùng wrapper. `ObjIntConsumer<List<Integer>>` có thể nhận `int` không boxing tại call site nhưng khi gọi `list.add(n)` vẫn cần boxing để chứa trong danh sách.
3. **Primitive stream không tự giúp truy vấn nhanh hơn:** chọn cấu trúc dữ liệu và thuật toán đúng trước; pipeline Stream có thể tạo thêm overhead so với vòng lặp đơn giản trên mảng.
4. **Primitive không chữa lỗi số học:** `int` và `long` có thể overflow; `double` là số dấu phẩy động nhị phân, không thích hợp cho mọi yêu cầu làm tròn thập phân.
5. **API dễ đọc vẫn là tiêu chí quan trọng:** một bước chuyển đổi đơn giản trên vài giá trị không cần được viết thành chuỗi operator rối chỉ để tránh một lần boxing.

### Ví dụ overflow khác với boxing

```java
int wrapped = IntStream.of(Integer.MAX_VALUE, 1).sum();
// wrapped == Integer.MIN_VALUE do tràn int

long widened = IntStream.of(Integer.MAX_VALUE, 1)
        .mapToLong(n -> n)
        .sum();
// widened == 2147483648L
```

Đoạn minh họa cần `IntStream`. `mapToLong` mở rộng từng số trước khi cộng, nhờ đó tổng ở ví dụ nằm trong miền `long`; nó không phải “cách chữa” mọi overflow nếu tổng `long` cũng vượt giới hạn. Khi cần an toàn toán học, chọn kiểu và phép kiểm tra phạm vi dựa trên miền giá trị thật.

### Đừng gọi boxed() chỉ để lại unbox ngay

```java
// KHÔNG NÊN nếu mục tiêu chỉ là tổng:
int sum = IntStream.rangeClosed(1, 10)
        .boxed()
        .mapToInt(Integer::intValue)
        .sum();

// RÕ HƠN: giữ primitive xuyên suốt phép tính:
int directSum = IntStream.rangeClosed(1, 10).sum();
```

Đây là ví dụ minh họa. Cả hai cho `55`. Java có thể tối ưu một phần trường hợp đầu, nhưng phiên bản sau nói rõ ý định và không yêu cầu chuyển đổi vô ích trong mô hình API.

## 9. Chương trình đầy đủ chạy được trên Java 17+

Chương trình sau minh họa: operator/predicate/consumer/supplier cho primitive, `ToIntFunction`, `IntFunction`, chuyển kiểu, `ObjIntConsumer`, primitive stream, ranh giới boxed và mở rộng `int` sang `long` để cộng an toàn. Không cần thư viện bên ngoài.

Lưu thành **PrimitiveFunctionalDemo.java**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.OptionalDouble;
import java.util.function.DoubleUnaryOperator;
import java.util.function.IntBinaryOperator;
import java.util.function.IntFunction;
import java.util.function.IntPredicate;
import java.util.function.IntSupplier;
import java.util.function.IntUnaryOperator;
import java.util.function.IntToDoubleFunction;
import java.util.function.ObjIntConsumer;
import java.util.function.ToIntFunction;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class PrimitiveFunctionalDemo {
    public static void main(String[] args) {
        IntPredicate even = n -> n % 2 == 0;
        IntUnaryOperator timesTen = n -> n * 10;
        IntBinaryOperator add = Integer::sum;

        int filteredSum = IntStream.rangeClosed(1, 6)
                .filter(even)
                .map(timesTen)
                .sum();
        System.out.println("Even x10 sum: " + filteredSum);
        System.out.println("Reduced: " +
                IntStream.of(2, 4, 6).reduce(0, add));

        IntSupplier answer = () -> 42;
        System.out.println("Supplier: " + answer.getAsInt());

        ToIntFunction<String> length = String::length;
        IntFunction<String> label = n -> "item-" + n;
        System.out.println("Length: " + length.applyAsInt("Java"));
        System.out.println("Label: " + label.apply(7));

        List<String> names = Arrays.asList("An", "Binh", "Chi");
        int totalNameLength = names.stream()
                .mapToInt(length)
                .sum();
        System.out.println("Name lengths: " + totalNameLength);

        IntToDoubleFunction half = n -> n / 2.0;
        System.out.println("Half of 7: " + half.applyAsDouble(7));

        DoubleUnaryOperator addTenPercent = value -> value * 1.10;
        System.out.printf(Locale.ROOT, "Price: %.2f%n",
                addTenPercent.applyAsDouble(20.0));

        StringBuilder builder = new StringBuilder("id=");
        ObjIntConsumer<StringBuilder> append = (b, n) -> b.append(n);
        append.accept(builder, 42);
        System.out.println(builder);

        OptionalDouble average = IntStream.of(10, 20, 30).average();
        System.out.println("Average: " + average.orElse(0.0));

        int[] squares = IntStream.rangeClosed(1, 5)
                .map(n -> n * n)
                .toArray();
        System.out.println("Squares: " + Arrays.toString(squares));

        List<Integer> boxed = IntStream.rangeClosed(1, 3)
                .boxed()
                .collect(Collectors.toList());
        System.out.println("Boxed: " + boxed);

        long safeSum = IntStream.of(Integer.MAX_VALUE, 1)
                .mapToLong(n -> n)
                .sum();
        System.out.println("Widened sum: " + safeSum);
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac PrimitiveFunctionalDemo.java
java PrimitiveFunctionalDemo
```

**Standard output:**

```text
Even x10 sum: 120
Reduced: 12
Supplier: 42
Length: 4
Label: item-7
Name lengths: 9
Half of 7: 3.5
Price: 22.00
id=42
Average: 20.0
Squares: [1, 4, 9, 16, 25]
Boxed: [1, 2, 3]
Widened sum: 2147483648
```

**Vì sao kết quả như vậy?**

1. `IntStream.rangeClosed(1,6)` tạo `1..6`. `IntPredicate` giữ `2,4,6`, `IntUnaryOperator` nhân mười và `sum()` trả `20 + 40 + 60 = 120`.
2. `IntBinaryOperator` cộng các số trong `reduce(0, add)`, cho `12`; đây là reduction có giá trị khởi tạo `0`.
3. `IntSupplier` trả một `int` cố định `42`; `ToIntFunction<String>` đọc độ dài `"Java"` là `4` và `IntFunction<String>` tạo chuỗi `"item-7"`.
4. `List<String>.stream().mapToInt(length).sum()` thu được `2 + 4 + 3 = 9`; pipeline tính tổng vẫn ở dạng primitive.
5. `IntToDoubleFunction` trả `3.5` từ `7 / 2.0`. `DoubleUnaryOperator` nhân giá trị `20.0` với `1.10`; `printf(Locale.ROOT, "%.2f%n", ...)` in chính xác định dạng `22.00` với dấu chấm thập phân.
6. `ObjIntConsumer<StringBuilder>` nối `42` vào builder, đây là thay đổi đối tượng ở ranh giới được chỉ rõ.
7. `average()` trả `OptionalDouble` chứa `20.0`; `toArray()` của `IntStream` trả `int[]`; `boxed()` chuyển sang `Stream<Integer>` trước `Collectors.toList()`.
8. `mapToLong(n -> n)` mở rộng cả hai số sang `long` trước khi cộng nên `Integer.MAX_VALUE + 1` được biểu diễn là `2147483648` thay vì tràn trong `int`.

## 10. Các lỗi phổ biến khi áp dụng specialization

### Lỗi: nhầm tên phương thức

```java
IntUnaryOperator twice = n -> n * 2;
// SAI: twice.apply(4)
// ĐÚNG:
int result = twice.applyAsInt(4);
```

Đoạn minh họa cần import `IntUnaryOperator`. Tra cứu chữ ký SAM chính xác; các nhóm `IntFunction<R>` và `IntUnaryOperator` có tên `apply`/`applyAsInt` khác nhau.

### Lỗi: tưởng primitive có thể là type argument generic

```java
// SAI: Function<int, int> f = n -> n + 1;
// ĐÚNG khi muốn tránh boxing tại interface:
IntUnaryOperator f = n -> n + 1;
```

Generic type arguments phải là reference type. Nếu API yêu cầu `Function<Integer,Integer>` thì bạn phải làm việc theo hợp đồng đó; không thể truyền thẳng `IntUnaryOperator` mà không có bước thích ứng tương ứng.

### Lỗi: thay đổi list nguồn trong Stream

```java
// KHÔNG NÊN: không can thiệp nguồn Stream khi đang duyệt.
List<Integer> items = new java.util.ArrayList<>(
        Arrays.asList(1, 2, 3));
items.stream().mapToInt(n -> {
    items.remove(n);
    return n;
}).sum();
```

Đây là **ví dụ phản diện, không dùng trong chương trình chạy**. Stream behavioral parameter phải non-interfering; ngoài ra, `ArrayList` không an toàn cho mutation đồng thời. Dùng phép biến đổi không đổi nguồn, collector, hoặc một thao tác collection tại chỗ phù hợp ngoài pipeline đang duyệt.

### Lỗi: dùng boxed Stream rồi nghĩ đã hết boxing

```java
List<Integer> values = IntStream.range(0, 3)
        .boxed()
        .collect(Collectors.toList());
```

Đoạn minh họa cần `List`, `IntStream` và `Collectors`. `List<Integer>` chứa wrapper chứ không chứa trực tiếp phần tử `int`; boxing vẫn xảy ra ở điểm chuyển đổi theo mô hình kiểu. Đây có thể là thiết kế đúng nếu API phía sau cần `List<Integer>`.

### Lỗi: nhầm phép chia nguyên và số thực

```java
IntToDoubleFunction wrongHalf = n -> n / 2;
IntToDoubleFunction correctHalf = n -> n / 2.0;
// wrongHalf.applyAsDouble(7) == 3.0
// correctHalf.applyAsDouble(7) == 3.5
```

Đoạn minh họa cần `IntToDoubleFunction`. Đầu ra `double` không tự sửa phép toán chia `int / int` đã thực hiện trước đó.

### Lỗi: tin rằng primitive luôn giải quyết bài toán hiệu năng

Với vài phần tử, chi phí code phức tạp có thể lớn hơn lợi ích tiết kiệm boxing. Với API cuối cùng phải tạo `Integer` hoặc lưu đối tượng, bước boxing chưa biến mất. Nên chọn loại primitive vì **hợp đồng đầu ra đúng và dữ liệu thuộc loại số**, sau đó dùng benchmark/measurement để kết luận về tối ưu hiệu năng.

## 11. Checklist và bài tập thực hành

**Checklist khi chọn một functional interface:**

1. Đầu vào có phải `int`, `long` hoặc `double` không? Nếu phải, ưu tiên specialization tương ứng ở ranh giới tính toán.
2. Kết quả là primitive hay object? Phân biệt `IntFunction<R>` với `ToIntFunction<T>` và `IntUnaryOperator`.
3. Có hai đầu vào không? Xem `IntBinaryOperator`, `ToIntBiFunction`, `ObjIntConsumer` theo hợp đồng.
4. Dùng `Stream<T>` hay `IntStream`/`LongStream`/`DoubleStream`? Có bước `boxed()` hoặc unbox không cần thiết không?
5. Giá trị có thể rỗng không? Dùng `OptionalInt`/`OptionalLong`/`OptionalDouble` và chính sách default có ý nghĩa.
6. Có nguy cơ overflow, mất độ chính xác hoặc tác dụng phụ trong callback không? Primitive giúp tối ưu biểu diễn chứ không tự bảo đảm đúng nghiệp vụ.
7. Với workload lớn, có đo benchmark/GC/allocations để xác nhận lợi ích thay vì suy đoán không?

**Bài tập 1 — lọc và tổng:** Dùng `IntStream.rangeClosed(1, 10)`, `IntPredicate` giữ các số chia hết cho 3, rồi tính tổng bình phương bằng `IntUnaryOperator`. Đáp án: `3² + 6² + 9² = 126`.

**Bài tập 2 — object sang primitive:** Từ `List<String>` gồm `"A"`, `"Java"`, `"Lambda"`, viết `ToIntFunction<String>` lấy độ dài và `mapToInt(...).average()`. Tính trung bình độ dài: `(1 + 4 + 6) / 3.0 = 3.666...`. Xác định chính sách khi danh sách rỗng.

**Bài tập 3 — primitive sang object:** Dùng `IntStream.range(1, 4).mapToObj(n -> "id-" + n)` tạo `List<String>`; chỉ ra chính xác đầu ra kiểu gì và vì sao đối tượng `String` vẫn được tạo.

**Bài tập 4 — thứ tự operator:** Với `IntUnaryOperator multiply = n -> n * 5` và `plusOne = n -> n + 1`, tính `multiply.andThen(plusOne).applyAsInt(2)` và `multiply.compose(plusOne).applyAsInt(2)`. Đáp án: `11` và `15`.

**Bài tập 5 — overflow:** Tại sao `IntStream.of(Integer.MAX_VALUE, 1).sum()` không tạo kết quả `2147483648`? Sửa bằng `mapToLong(n -> n).sum()`, và giải thích khi nào `BigInteger` hoặc một chính sách số học có kiểm tra sẽ cần thiết.

### Tài liệu chính thức để tra cứu

- [Java SE 25: java.util.function](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/package-summary.html)
- [Java SE 25: IntUnaryOperator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/IntUnaryOperator.html)
- [Java SE 25: ToIntFunction](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/ToIntFunction.html)
- [Java SE 25: IntStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/IntStream.html)
- [Java SE 25: Stream.mapToInt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html#mapToInt(java.util.function.ToIntFunction))
- [Java SE 25: OptionalInt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalInt.html)
