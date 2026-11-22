# Functional interface generic và wildcard trong Java 8

## 1. Mục tiêu

Functional interface giúp biểu diễn một hành vi bằng lambda hoặc method reference. Trong ứng dụng thực tế, một callback thường phải xử lý nhiều kiểu dữ liệu có quan hệ kế thừa. **Generic** diễn đạt quan hệ giữa kiểu đầu vào và đầu ra, còn **wildcard** giúp tái sử dụng callback với những kiểu phù hợp mà compiler vẫn bảo vệ an toàn kiểu.

Bài này tập trung vào các kiến thức của Java 8 **vẫn được sử dụng trong Java hiện đại**: `@FunctionalInterface`, `Function<T,R>`, `Predicate<T>`, `Consumer<T>`, `Supplier<T>`, target typing, `? extends`, `? super`, PECS và wildcard trong Stream API. Không sử dụng các API cũ đã bị loại bỏ.

Sau khi học, bạn sẽ biết khai báo interface generic có một phương thức trừu tượng, suy luận kiểu lambda, thiết kế callback nhận kiểu cha hoặc trả kiểu con, tránh nhầm generic invariance với đa hình và viết kiểm thử biên dịch/chạy để kiểm tra contract.

## 2. Generic functional interface là gì?

Một **functional interface** có đúng một abstract method theo quy tắc đếm phương thức của Java. Interface này có thể có **type parameter** mà vẫn là functional interface:

```java
@FunctionalInterface
interface Mapper<T, R> {
    R map(T input);
}
```

Ở đây, `T` là kiểu dữ liệu được nhận, `R` là kiểu được trả. Phương thức `map` là *single abstract method* (SAM). `@FunctionalInterface` làm compiler báo lỗi nếu cấu trúc interface không còn đáp ứng quy tắc SAM; annotation hữu ích nhưng không phải điều kiện bắt buộc để một interface được sử dụng bằng lambda.

Ví dụ bên trong một class/method có khai báo `Mapper`:

```java
Mapper<String, Integer> length = text -> text.length();
Mapper<Integer, String> label = number -> "item-" + number;
```

Với `Mapper<String,Integer>`, compiler biết `text` là `String`, `text.length()` trả `int` và kết quả được boxing thành `Integer`. Với `Mapper<Integer,String>`, đầu vào được suy luận là `Integer`.

Trong Java, **generic interface** (`interface Mapper<T,R> { R map(T x); }`) và **generic abstract method** (`<T> T map(T x)`) là hai thiết kế khác nhau. Với callback lambda thông thường, việc đưa type parameter lên interface thường đúng mục tiêu: mỗi kiểu đích của lambda cố định một cặp loại đầu vào/đầu ra. Một abstract method tự khai báo type parameter cho mỗi lần gọi đặt ra yêu cầu đa hình mạnh hơn; đừng tùy tiện thay thế hai hình thức này cho nhau.

### Lambda cần target type

Lambda được kiểm tra dựa trên một **kiểu đích là functional interface**, chẳng hạn biến nhận kết quả, tham số của phương thức, kiểu trả về hoặc cast có chủ đích:

```java
java.util.function.Function<String, Integer> size = s -> s.length();
java.util.function.Predicate<String> present = s -> !s.isEmpty();
```

Nếu viết một biểu thức lambda riêng lẻ mà không có target type, compiler không biết chữ ký SAM cần thỏa mãn. Khi overload giữa nhiều functional interface khiến lời gọi nhập nhằng, hãy đặt biến trung gian có kiểu rõ ràng hoặc khai báo kiểu tham số lambda để hỗ trợ suy luận. Không xử lý vấn đề bằng raw type hay unchecked cast.

## 3. Vì sao cần wildcard: generic là invariant

Dù `Integer extends Number`, Java **không** mặc định coi `Function<Integer,String>` là subtype của `Function<Number,String>`, hoặc ngược lại. Đó là **invariance của generic**.

Ví dụ sau **cố ý không biên dịch** nếu mở dòng cuối:

```java
java.util.function.Function<Number, String> formatter =
        n -> "N" + n.intValue();
// java.util.function.Function<Integer, String> invalid = formatter;
```

Không nên xem đây là thiếu sót phải sửa bằng cast. Một callback nhận `Integer` không đủ khả năng đảm bảo nhận mọi `Number` (bao gồm `Double`). Còn một callback nhận `Number` hoàn toàn xử lý được `Integer` nếu lời gọi qua API có giới hạn đúng.

Java giải quyết nhu cầu này bằng **wildcard ở nơi sử dụng**:

```java
java.util.function.Function<Number, String> formatter =
        n -> "N" + n.intValue();

java.util.function.Function<? super Integer, ? extends CharSequence>
        flexible = formatter;

CharSequence label = flexible.apply(5); // Hợp lệ: nhận một Integer.
```

Trong kiểu `Function<? super Integer, ? extends CharSequence>`:

- `? super Integer`: kiểu mà hàm tiêu thụ có thể là `Integer` hoặc một superclass như `Number`, `Object`; truyền `Integer` là an toàn.
- `? extends CharSequence`: kiểu hàm trả có thể là `CharSequence` hoặc subtype như `String`; đọc kết quả dưới kiểu `CharSequence` là an toàn.
- `flexible.apply(3.5)` không bảo đảm hợp lệ: kiểu input thực tế có thể chỉ là `Integer`. Giới hạn `? super Integer` không nói rõ đó là `Number`.

**Điểm cần nhớ:** wildcard cho phép **tham chiếu và lời gọi phù hợp**; nó không thay đổi việc generic class/interface thông thường vẫn invariant.

## 4. PECS áp dụng cho functional interface

PECS là cách ghi nhớ hướng dòng dữ liệu trong generic: **Producer Extends, Consumer Super**.

- Nếu một thành phần **cung cấp** đối tượng mà chúng ta đọc dưới kiểu `T`, thường dùng `? extends T`.
- Nếu một thành phần **nhận** đối tượng `T` do chúng ta truyền vào, thường dùng `? super T`.
- Nếu một functional interface vừa có input vừa có output, hãy xét **từng type parameter** của nó.

| Callback | Chữ ký muốn chấp nhận linh hoạt | Vai trò |
| --- | --- | --- |
| `Consumer<T>` | `Consumer<? super T>` | Nhận giá trị T hoặc subtype đã chọn. |
| `Predicate<T>` | `Predicate<? super T>` | Kiểm tra một giá trị T. |
| `Function<T,R>` | `Function<? super T, ? extends R>` | Nhận T, cung cấp R. |
| `Supplier<T>` | `Supplier<? extends T>` | Cung cấp giá trị T. |
| `Comparator<T>` | `Comparator<? super T>` | So sánh hai giá trị T. |
| `List<T>` chỉ dùng làm nguồn | `List<? extends T>` | Cung cấp các phần tử đọc được như T. |

### Consumer và Predicate: super ở đầu vào

Một consumer xử lý được `Number` chắc chắn xử lý được `Integer`:

```java
java.util.function.Consumer<Number> printNumber =
        n -> System.out.println(n);
java.util.function.Consumer<? super Integer> printInteger = printNumber;
printInteger.accept(42);
```

Tương tự `Predicate<Number>` dùng được nơi API muốn kiểm tra `Integer` nếu tham số API được khai báo `Predicate<? super Integer>`.

### Supplier: extends ở đầu ra

Một `Supplier<Integer>` có thể làm nguồn cho API chỉ yêu cầu `Number`:

```java
java.util.function.Supplier<Integer> integerSource = () -> 7;
java.util.function.Supplier<? extends Number> numberSource = integerSource;
Number answer = numberSource.get();
```

Ở đây ta **đọc Number ra**, không đưa `Number` vào supplier. Chọn `? super Number` sẽ không đảm bảo kết quả trả ra là Number, vì kiểu ẩn có thể là `Object`.

### Function: áp dụng cả hai hướng

`Function<T,R>` vừa **consume T** vừa **produce R**. Vì thế:

```java
java.util.function.Function<Number, Integer> doubleValue =
        n -> n.intValue() * 2;

java.util.function.Function<? super Integer, ? extends Number>
        callback = doubleValue;

Number result = callback.apply(5);
```

Ở đầu vào dùng `super`; ở đầu ra dùng `extends`. Không thể kết luận tự động rằng `Function<Integer,Number>` sử dụng được ở mọi nơi cần `Function<Number,Integer>` vì hướng nhận và trả đã thay đổi.

## 5. Ví dụ Java hoàn chỉnh: generic mapper, wildcard và callback chuẩn

Ví dụ sử dụng `Mapper<T,R>` tự định nghĩa và những interface có sẵn từ Java 8. Toàn bộ chương trình nằm trong tệp **`GenericFunctionalDemo.java`**.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class GenericFunctionalDemo {
    @FunctionalInterface
    interface Mapper<T, R> {
        R map(T value);
    }

    static <T, R> List<R> transform(
            List<? extends T> source,
            Mapper<? super T, ? extends R> mapper) {
        List<R> output = new ArrayList<>();
        for (T value : source) {
            output.add(mapper.map(value));
        }
        return output;
    }

    static <T> long countMatching(
            Iterable<? extends T> source,
            Predicate<? super T> test) {
        long count = 0;
        for (T value : source) {
            if (test.test(value)) {
                count++;
            }
        }
        return count;
    }

    static <T> void consume(T value, Consumer<? super T> sink) {
        sink.accept(value);
    }

    public static void main(String[] args) {
        List<Integer> values = Arrays.asList(2, 4, 6);

        Mapper<Number, String> format =
                value -> "N" + value.intValue();
        List<CharSequence> labels = transform(values, format);
        System.out.println("labels: " + labels);

        Predicate<Number> isEven =
                value -> value.intValue() % 2 == 0;
        System.out.println("matches: " + countMatching(values, isEven));

        Consumer<Object> log = value ->
                System.out.println("consumed: " + value);
        consume(42, log);

        Function<Number, Integer> twice =
                value -> value.intValue() * 2;
        Function<? super Integer, ? extends Number> adaptable = twice;
        Number answer = adaptable.apply(5);
        System.out.println("mapped: " + answer);

        Supplier<Integer> source = () -> 7;
        Supplier<? extends Number> numberSource = source;
        System.out.println("supplied: " + numberSource.get());

        Function<Integer, String> annotate = value -> "v=" + value;
        Function<String, Integer> length = String::length;
        System.out.println("chained: " + annotate.andThen(length).apply(8));
    }
}
```

Biên dịch và chạy với JDK 17+ (code cũng tương thích cú pháp và API Java 8):

```bash
javac GenericFunctionalDemo.java
java GenericFunctionalDemo
```

**Stdout:**

```text
labels: [N2, N4, N6]
matches: 3
consumed: 42
mapped: 10
supplied: 7
chained: 3
```

Chương trình sử dụng generic và wildcard an toàn, không cần unchecked cast hoặc raw type. Diễn giải từng phần:

1. `transform` lấy dữ liệu từ `List<? extends T>`. Với `values`, mỗi phần tử có thể đọc như `T`, và phương thức không thêm phần tử bất kỳ vào danh sách nguồn.
2. `Mapper<? super T, ? extends R>` chấp nhận `Mapper<Number,String>` khi nguồn có `Integer` và đích cần `CharSequence`. Một callback nhận `Number` xử lý được `Integer`, còn `String` trả về dùng được như `CharSequence`.
3. `countMatching` nhận `Predicate<? super T>`. Predicate viết cho `Number` dùng lại với danh sách `Integer`.
4. `consume` nhận `Consumer<? super T>`; `Consumer<Object>` hoàn toàn có thể nhận giá trị `Integer` 42.
5. `adaptable` minh họa đồng thời contravariance của input và covariance của output: truyền `Integer` 5, nhận kết quả dưới kiểu `Number`.
6. `numberSource` cho thấy `Supplier<Integer>` đủ để cung cấp `Number`.
7. `annotate.andThen(length)` là chuỗi `Integer -> String -> Integer`. Chuỗi `v=8` có độ dài 3, nên dòng cuối in `chained: 3`.

**Giới hạn của ví dụ:** các callback không tự xác định chính sách xử lý `null`, exception, concurrency hay thời gian thực thi. Những ràng buộc đó phải được chỉ rõ trong hợp đồng của API thực tế; wildcard chỉ kiểm tra **quan hệ kiểu**.

## 6. Tại sao Java API chuẩn cũng dùng wildcard?

Các phương thức trong `java.util.function` và `java.util.stream` dùng wildcard để caller không phải tạo callback mới chỉ vì kiểu dữ liệu là subtype.

### `Function.andThen` và `compose`

Chữ ký cốt lõi của `andThen`:

```java
default <V> Function<T, V> andThen(
        Function<? super R, ? extends V> after)
```

Nếu hàm hiện tại trả `R`, callback chạy sau có thể nhận `R` hoặc supertype, và kết quả của callback có thể là subtype của `V`. Đó là đúng thứ tự **đầu ra hàm trước → đầu vào hàm sau**.

`compose` là chiều ngược lại, với ý tưởng `before` tạo giá trị đầu vào cho hàm hiện tại. Chữ ký tiêu biểu:

```java
default <V> Function<V, R> compose(
        Function<? super V, ? extends T> before)
```

Với các phép kết hợp, hãy đọc cả kiểu dữ liệu chảy qua mỗi giai đoạn thay vì học thuộc cú pháp wildcard.

### `Consumer.andThen` và `Predicate.and`

`Consumer<T>.andThen(Consumer<? super T> after)` cho phép kết hợp consumer nhận supertype của `T`. `Predicate<T>.and(Predicate<? super T> other)` cho phép kiểm tra cùng dữ liệu bằng predicate viết cho kiểu rộng hơn.

Wildcard không có nghĩa các callback có cùng hành vi; ví dụ consumer có side effect vẫn phải được đánh giá về thứ tự chạy và exception.

### `Stream.map`, `filter`, `forEach`

Những chữ ký chính:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper)
Stream<T> filter(Predicate<? super T> predicate)
void forEach(Consumer<? super T> action)
```

Ví dụ với `Stream<Integer>`, ta có thể dùng `Function<Number,String>` cho `map`, `Predicate<Number>` cho `filter` và `Consumer<Object>` cho `forEach`. Đây là áp dụng trực tiếp PECS.

**Lưu ý độc lập với generic:** `forEach` trên parallel stream không cam kết encounter order cho action; nếu cần thứ tự trên stream có encounter order, cân nhắc `forEachOrdered`. Không biến wildcard thành một bảo đảm về thread safety hoặc thứ tự chạy.

### Comparator

Khi một phương thức cần so sánh `Integer`, `Comparator<Number>` đủ để so sánh hai `Integer`, vì comparator **tiêu thụ** các đối số. Do đó nhiều API sử dụng `Comparator<? super T>`. Comparator vẫn cần thỏa mãn quy tắc so sánh nhất quán, bắc cầu; compiler không thể tự kiểm tra logic nghiệp vụ.

## 7. Khi nào dùng `<T, R>` và khi nào dùng dấu `?`?

**Type parameter có tên** như `<T, R>` giúp liên kết kiểu ở nhiều vị trí. **Wildcard** cho biết một kiểu chưa biết nhưng nằm trong giới hạn được phép.

So sánh:

```java
static <T, R> List<R> transform(
        List<? extends T> source,
        Mapper<? super T, ? extends R> mapper)
```

Ở đây, `T` diễn tả loại dữ liệu đang xử lý và `R` diễn tả loại kết quả. Wildcard chỉ mở phạm vi các nguồn/callback chấp nhận được. Nếu thay mọi vị trí bằng `?`, chữ ký sẽ mất mối quan hệ kiểu để trả một `List<R>` hữu ích.

Ví dụ với `List<? extends Number>`:

- Đọc phần tử dưới kiểu `Number` là an toàn.
- Không được `add(1)` vào danh sách qua tham chiếu ấy, vì kiểu thực có thể là `List<Double>`. Ngoại lệ có thể thêm `null` không giải quyết nhu cầu thêm Number.
- Với `List<? super Integer>`, có thể thêm `Integer` nhưng chỉ bảo đảm phần tử lấy ra có kiểu `Object`.

Trong `Function<?, String>`, kiểu input chưa biết; không thể gọi `apply(5)` an toàn qua tham chiếu này dù kết quả có thể đọc dưới kiểu `String`. Hãy chọn `Function<? super Integer,String>` nếu muốn có quyền truyền Integer.

**Gợi ý thiết kế API:** đặt wildcard tại **tham số phương thức** để tăng khả năng tái sử dụng, giữ **kiểu trả về dễ sử dụng** như `List<R>` khi có thể, và dùng type parameter có tên khi thực sự cần ràng buộc các vị trí. Đừng thêm wildcard vào API đơn giản chỉ vì muốn nó trông tổng quát.

## 8. Những lỗi thường gặp với generic lambda và wildcard

### Dùng `extends` cho callback tiêu thụ dữ liệu

Đoạn minh họa sau có vấn đề ở lời gọi:

```java
java.util.function.Predicate<? extends Number> p =
        (Number n) -> n.intValue() > 0;
// p.test(1); // Lỗi: kiểu thực của ? extends Number chưa xác định.
```

Compiler không thể đảm bảo callback thực tế nhận `Integer`; nó có thể là callback chỉ nhận `Double`. Để kiểm tra Integer, chọn `Predicate<? super Integer>`. Nếu callback thực sự nhận mọi Number, khai báo trực tiếp `Predicate<Number>`.

### Gán subtype generic bằng trực giác kế thừa

```java
java.util.function.Function<Number, String> f = n -> n.toString();
// java.util.function.Function<Integer, String> invalid = f;
java.util.function.Function<? super Integer, ? extends CharSequence> ok = f;
```

Dòng `invalid` nếu mở sẽ không biên dịch vì invariance. Dòng `ok` hợp lệ theo vai trò input/output. Không dùng unchecked cast để cưỡng ép kiểu không tương thích.

### Nhầm wildcard capture với lambda capture

Đây là hai khái niệm khác nhau:

- **Lambda capture** là việc lambda truy cập biến local/parameter ở scope bên ngoài; biến local đó phải `final` hoặc `effectively final`.
- **Wildcard capture** là cách compiler biểu diễn kiểu ẩn tương ứng với `?`; thông báo lỗi có thể hiển thị `CAP#1`. Hãy đọc bound của wildcard và hướng dữ liệu khi xử lý lỗi.

Ví dụ capture biến local hợp lệ:

```java
String prefix = "id-";
java.util.function.Function<Integer, String> render =
        number -> prefix + number;
```

`prefix` không được gán lại sau khi capture. Nếu một reference effectively final trỏ đến object mutable, nội dung object vẫn có thể thay đổi; tính effectively final không làm object bất biến hay thread-safe.

### Bỏ target type hoặc dùng raw type

```java
java.util.function.Function<String, Integer> length =
        s -> s.length();
// Không thể suy luận một lambda trần không có target functional interface.
```

Raw type như `Function` làm mất thông tin kiểu đầu vào/đầu ra, có thể tạo cảnh báo unchecked và dời lỗi về runtime. Khi compiler không suy luận được chuỗi generic method phức tạp, hãy tách biểu thức thành biến có kiểu rõ ràng hoặc đưa type witness hợp lệ, thay vì bỏ generic.

### Nhầm wildcard với giới hạn null/exception

`? extends R` không bảo đảm kết quả khác `null`; `? super T` không bảo đảm callback nhận `null`; wildcard không can thiệp vào checked exception, side effect hay thread safety. Mỗi yếu tố cần được tài liệu hóa và kiểm thử riêng.

## 9. Type erasure và lựa chọn interface chuẩn

Các kiểm tra generic của Java chủ yếu diễn ra ở **compile time**. Do **type erasure**, các kiểu `Function<String,Integer>` và `Function<Integer,String>` không có hai runtime class generic riêng mà bạn có thể dùng để overload hai method chỉ khác type argument.

Không thể viết `instanceof List<String>` để kiểm tra chính xác phần tử ở runtime, cũng không thể tạo `new T()` từ type variable thông thường. Nếu logic runtime cần biết kiểu, hãy đưa metadata như `Class<T>` hoặc type token có thiết kế rõ ràng. Đừng cố lấy generic type từ tên class động của lambda.

Các functional interface còn dùng tốt trong Java hiện đại:

| Mục tiêu | Interface |
| --- | --- |
| Nhận T, trả R | `Function<T,R>` |
| Nhận T, trả boolean | `Predicate<T>` |
| Nhận T, xử lý side effect | `Consumer<T>` |
| Không nhận input, tạo T | `Supplier<T>` |
| Nhận T, trả cùng T | `UnaryOperator<T>` |
| Nhận T và U, trả R | `BiFunction<T,U,R>` |
| Xử lý primitive int | `IntUnaryOperator`, `IntPredicate`, `IntConsumer`, `IntSupplier` theo mục tiêu |

Các primitive specialization tránh boxing/unboxing khi xử lý lượng dữ liệu lớn; hãy lựa chọn theo contract và đo lường thay vì tối ưu theo cảm tính.

### Kiểm thử một generic API

Nên có các bài kiểm tra **biên dịch** cho callback nhận kiểu cha, callback trả kiểu con và trường hợp dùng lambda/method reference. Sau đó kiểm tra hành vi thực thi, giá trị rỗng, `null`, exception, mutation và concurrency nếu có trong contract. Code biên dịch được chứng minh quan hệ kiểu hợp lệ, chứ chưa chứng minh callback xử lý đúng nghiệp vụ.

## 10. Bài tập tự kiểm tra

**1.** Một `Predicate<Number>` cần được truyền cho phương thức lọc `Integer`. Dùng `Predicate<? super Integer>` hay `Predicate<? extends Integer>`? **Đáp án:** `? super Integer` vì predicate tiêu thụ Integer.

**2.** Một `Supplier<Integer>` cần được truyền cho phương thức muốn nhận `Number`. Dùng `Supplier<? extends Number>` hay `Supplier<? super Number>`? **Đáp án:** `? extends Number` vì supplier cung cấp kết quả.

**3.** Có `Function<Number,String>` nhưng client chỉ đưa `Integer` và cần kết quả `CharSequence`. **Đáp án:** khai báo chỗ nhận là `Function<? super Integer, ? extends CharSequence>`.

**4.** Có `Function<Integer,String>`; có an toàn khi gán thẳng vào `Function<Number,String>`? **Không**; kiểu đích cam kết nhận mọi Number, còn hàm gốc chỉ cam kết nhận Integer.

**5.** Một `List<? extends Number>` có thể thêm `Integer` không? **Không**, vì loại danh sách thực có thể là `List<Double>`. Có thể đọc phần tử như `Number`.

## 11. Kết luận

Functional interface generic giúp định nghĩa **quan hệ kiểu cụ thể** giữa callback và dữ liệu. Wildcard giúp chấp nhận callback **rộng về đầu vào, hẹp về đầu ra**: `? super T` cho vị trí consume và `? extends R` cho vị trí produce. PECS là điểm bắt đầu hữu ích; để đúng trong các API phức tạp, luôn truy vết hướng dữ liệu từng type parameter.

Đây là kiến thức vẫn áp dụng với Java hiện đại, đặc biệt khi thiết kế method nhận `Function`, `Predicate`, `Consumer`, `Supplier` hoặc Stream. Hãy ưu tiên chữ ký diễn đạt contract rõ ràng, type inference kiểm chứng được, không dùng raw type/unchecked cast và không nhầm wildcard với bảo đảm runtime.

Đặc tả/API tham khảo: [JLS §15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27), [JLS §4.5.1 — Type Arguments](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.5.1), [java.util.function.Function](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Function.html), [java.util.stream.Stream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html).
