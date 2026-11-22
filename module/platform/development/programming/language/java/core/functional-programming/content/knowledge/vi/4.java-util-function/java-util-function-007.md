# IntFunction, ToIntFunction và phân biệt chiều chuyển đổi kiểu trong Java

## 1. Vấn đề cốt lõi: tên interface cho biết hướng đi của dữ liệu

Trong package `java.util.function`, **`IntFunction<R>` và `ToIntFunction<T>` đều là functional interface**, nhưng chúng thực hiện hai phép biến đổi theo **hai chiều khác nhau**:

- **`IntFunction<R>`**: nhận **`int` nguyên thủy** và trả về một giá trị kiểu **`R`** (kiểu tham chiếu).
- **`ToIntFunction<T>`**: nhận một giá trị kiểu **`T`** (kiểu tham chiếu) và trả về **`int` nguyên thủy**.

Viết bằng ký hiệu:

~~~text
IntFunction<R>:    int  ──apply(int)──────► R
ToIntFunction<T>:  T    ──applyAsInt(T)───► int
~~~

Chữ **`Int` ở đầu** `IntFunction` chỉ **kiểu đầu vào** được chuyên biệt hóa thành `int`. Cụm **`ToInt` ở đầu** `ToIntFunction` chỉ **kiểu đầu ra** là `int`.

Đây là quy tắc đặt tên quan trọng khi học functional programming trong Java. Không nên đoán ý nghĩa chỉ từ việc cả hai có chữ `Int`: hãy đọc **chữ ký phương thức trừu tượng duy nhất** (SAM) trước.

## 2. Chữ ký và cách gọi chính xác

Hai interface có thể hình dung qua các khai báo rút gọn sau:

~~~java
// Minh họa các chữ ký từ java.util.function; không khai báo lại
// các interface chuẩn này trong chương trình của bạn.
@FunctionalInterface
public interface IntFunction<R> {
    R apply(int value);
}

@FunctionalInterface
public interface ToIntFunction<T> {
    int applyAsInt(T value);
}
~~~

Bảng đối chiếu:

| Tiêu chí | `IntFunction<R>` | `ToIntFunction<T>` |
|---|---|---|
| SAM | `R apply(int value)` | `int applyAsInt(T value)` |
| Kiểu đầu vào | `int` nguyên thủy | `T` là kiểu tham chiếu |
| Kiểu đầu ra | `R` là kiểu tham chiếu | `int` nguyên thủy |
| Tham số generic đại diện | Kết quả `R` | Đầu vào `T` |
| Ví dụ | `int → String`, `int → String[]` | `String → int`, `Product → int` |
| API tiêu biểu | `IntStream.mapToObj`, `Stream.toArray` | `Stream.mapToInt`, `Comparator.comparingInt` |
| Phương thức gọi | `f.apply(5)` | `f.applyAsInt("Java")` |

Đặc biệt lưu ý:

1. `IntFunction<R>` **không phải** `Function<Integer, R>`. Cả hai có thể diễn tả một phép chuyển số sang `R`, nhưng `IntFunction` nhận primitive `int` trực tiếp, trong khi `Function<Integer, R>` nhận boxed `Integer`.
2. `ToIntFunction<T>` **không phải** `Function<T, Integer>`. `ToIntFunction` trả primitive `int`, còn `Function<T, Integer>` trả đối tượng `Integer`.
3. Với generic `R` hoặc `T`, không thể viết `IntFunction<int>` hay `ToIntFunction<int>`: tham số generic của Java phải là **reference type**. `IntFunction<Integer>` là hợp lệ nhưng khi đó kết quả `int` ở đầu ra biểu diễn qua `Integer`, tức có thể xảy ra boxing.
4. Hai SAM có tên **khác nhau**. Nhầm `apply` với `applyAsInt` là lỗi biên dịch thường gặp.

## 3. Ví dụ đơn giản: chuyển `int` sang `String` và `String` sang `int`

~~~java
import java.util.function.IntFunction;
import java.util.function.ToIntFunction;

class Example {
    void demonstrate() {
        IntFunction<String> toLabel = number -> "ID-" + number;
        ToIntFunction<String> length = String::length;

        String label = toLabel.apply(12);       // "ID-12"
        int count = length.applyAsInt("Java");   // 4
    }
}
~~~

Đây là **đoạn minh họa**: lớp có thể biên dịch, nhưng không có `main` để chạy độc lập.

Phân tích:

- `number -> "ID-" + number` được gán cho `IntFunction<String>`: đầu vào của lambda được suy ra là `int`; đầu ra là `String`.
- `String::length` phù hợp với `ToIntFunction<String>`: một đối tượng `String` là đầu vào và giá trị `length()` là `int`.
- `toLabel.apply(12)` và `length.applyAsInt("Java")` sử dụng đúng tên SAM của từng interface.
- Lambda không tự quyết định kiểu của mình: kiểu đích `IntFunction<String>` hoặc `ToIntFunction<String>` quyết định hợp đồng mà lambda/method reference phải đáp ứng.

Đặt cạnh nhau cho dễ nhớ:

~~~text
number ── IntFunction<String> ──► "ID-12"
"Java" ── ToIntFunction<String> ──► 4
~~~

## 4. Chương trình hoàn chỉnh: hai chiều chuyển đổi trong xử lý dữ liệu

Lưu thành file `ConversionDirectionDemo.java` (JDK 17+):

~~~java
import java.util.List;
import java.util.function.IntFunction;
import java.util.function.ToIntFunction;
import java.util.stream.IntStream;

public class ConversionDirectionDemo {
    record Item(String name, int price, int quantity) {}

    public static void main(String[] args) {
        IntFunction<String> label = n -> "ID-" + n;
        ToIntFunction<String> length = String::length;

        List<Item> items = List.of(
                new Item("Pen", 5, 3),
                new Item("Book", 20, 2)
        );

        ToIntFunction<Item> lineTotal =
                item -> Math.multiplyExact(item.price(), item.quantity());

        System.out.println(label.apply(7));
        System.out.println(length.applyAsInt("Java"));
        System.out.println(IntStream.rangeClosed(1, 3)
                .mapToObj(label)
                .toList());
        System.out.println(items.stream()
                .mapToInt(lineTotal)
                .sum());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ConversionDirectionDemo.java
java ConversionDirectionDemo
~~~

Stdout:

~~~text
ID-7
4
[ID-1, ID-2, ID-3]
55
~~~

**Đọc kết quả theo luồng dữ liệu:**

1. `label.apply(7)` nhận primitive `7` rồi trả `"ID-7"`. Đây là hướng **`int → String`**.
2. `length.applyAsInt("Java")` nhận đối tượng `String` rồi trả primitive `4`. Đây là hướng **`String → int`**.
3. `IntStream.rangeClosed(1, 3)` sinh các giá trị `1`, `2`, `3`; `mapToObj(label)` chuyển từng `int` thành `String`; `toList()` tạo kết quả `[ID-1, ID-2, ID-3]`.
4. `items.stream()` là `Stream<Item>`; `mapToInt(lineTotal)` chuyển mỗi `Item` thành tổng tiền dòng hàng kiểu `int`; `sum()` thu được `5 × 3 + 20 × 2 = 55`.
5. `Math.multiplyExact` minh họa việc phát hiện tràn ở phép nhân. Phép cộng trong `IntStream.sum()` vẫn có thể tràn `int` nếu tổng vượt miền giá trị; với tiền tệ thật cần mô hình đơn vị và số học phù hợp.

Trong cùng một chương trình, **`IntFunction` đứng ở vị trí bước ra khỏi primitive stream**, còn **`ToIntFunction` đứng ở vị trí bước đi vào primitive stream**.

## 5. Gắn với Stream API: `mapToObj` và `mapToInt`

Hai chữ ký quan trọng:

~~~java
// Chữ ký lược giản từ Stream API, không phải mã khai báo lại.
<R> java.util.stream.Stream<R> mapToObj(
        java.util.function.IntFunction<? extends R> mapper);

java.util.stream.IntStream mapToInt(
        java.util.function.ToIntFunction<? super T> mapper);
~~~

Chữ ký thứ nhất thuộc **`IntStream`**, chữ ký thứ hai thuộc **`Stream<T>`**. Trên đây là ký pháp minh họa, không phải một đoạn file Java biên dịch độc lập vì đã lược bớt khai báo các lớp generic bao quanh.

### 5.1. Từ `IntStream` sang `Stream<R>`

~~~java
java.util.stream.Stream<String> names =
        java.util.stream.IntStream.of(2, 4, 6)
                .mapToObj(n -> "N" + n);
~~~

Nguồn là các `int` nguyên thủy; mapper nhận `int` và trả `String`. Vì vậy `mapToObj` cần **`IntFunction<? extends R>`**, với `R` là `String`.

### 5.2. Từ `Stream<T>` sang `IntStream`

~~~java
java.util.stream.IntStream lengths =
        java.util.stream.Stream.of("a", "bbb", "cc")
                .mapToInt(String::length);
~~~

Nguồn là các đối tượng `String`; mapper nhận `String` và trả `int`. Vì vậy `mapToInt` cần **`ToIntFunction<? super T>`**, với `T` là `String`.

**Ký hiệu wildcard nên hiểu thế nào?** `? extends R` cho phép `mapToObj` nhận mapper tạo ra một kiểu con của `R`; `? super T` cho phép `mapToInt` nhận mapper chấp nhận `T` hoặc một kiểu cha của `T`. Điều này theo nguyên tắc *producer extends, consumer super* (PECS), ở đây áp dụng vào vị trí kết quả và tham số của hàm.

### 5.3. Tránh nhầm với `map`

`IntStream.map` **không** nhận `IntFunction<R>`; nó cần **`IntUnaryOperator`** với chữ ký `int applyAsInt(int)` vì cả đầu vào lẫn đầu ra đều là primitive `int`.

~~~java
java.util.stream.IntStream doubled =
        java.util.stream.IntStream.of(1, 2, 3)
                .map(n -> n * 2); // IntUnaryOperator: int -> int.
~~~

Ngược lại, `Stream<T>.map` nhận `Function<? super T, ? extends R>` và tạo `Stream<R>`. Khi cần kết quả primitive `int`, `mapToInt` thường phù hợp hơn, đặc biệt nếu tiếp tục dùng `sum()`, `average()` hoặc `max()`.

## 6. `IntFunction` còn được dùng làm bộ tạo mảng

Một ứng dụng đặc biệt dễ gặp của `IntFunction<A[]>` là overload:

~~~java
<A> A[] toArray(java.util.function.IntFunction<A[]> generator);
~~~

Đây là chữ ký lược giản của `Stream.toArray(IntFunction<A[]>)`: đối số truyền vào hàm generator là **kích thước mảng cần tạo** (primitive `int`); hàm trả một mảng `A[]` (mảng là kiểu tham chiếu). Vì vậy API cần `IntFunction<A[]>` chứ không phải `ToIntFunction<A[]>`.

Lưu thành `ArrayGeneratorDemo.java`:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.function.IntFunction;

public class ArrayGeneratorDemo {
    public static void main(String[] args) {
        IntFunction<String[]> newStringArray = String[]::new;

        String[] words = List.of("A", "BB", "CCC")
                .stream()
                .toArray(newStringArray);

        IntFunction<int[]> newIntArray = int[]::new;
        int[] zeros = newIntArray.apply(3);

        System.out.println(Arrays.toString(words));
        System.out.println(words.length);
        System.out.println(Arrays.toString(zeros));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ArrayGeneratorDemo.java
java ArrayGeneratorDemo
~~~

Stdout:

~~~text
[A, BB, CCC]
3
[0, 0, 0]
~~~

**Vì sao `String[]::new` phù hợp?** Nó biểu diễn hành vi nhận một độ dài `int` và tạo `String[]`. `int[]::new` cũng là một hàm `int → int[]`, không phải `int → int`: **mảng `int[]` là đối tượng**, khác kiểu primitive `int`. Do đó `IntFunction<int[]>` hợp lệ trong khi `IntFunction<int>` không hợp lệ.

Nếu generator nhận kích thước âm, phép tạo mảng có thể ném `NegativeArraySizeException`. Khi dùng `Stream.toArray`, API chịu trách nhiệm cung cấp kích thước mà nó cần; người dùng vẫn nên tránh tạo generator có tác dụng phụ phụ thuộc trạng thái bên ngoài.

## 7. Phân biệt với `Function`, `IntUnaryOperator` và các biến thể gần tên

| Hợp đồng | SAM | Chiều chuyển đổi | Khi phù hợp |
|---|---|---|---|
| `Function<T,R>` | `R apply(T)` | Đối tượng → đối tượng | Chuyển từ kiểu tham chiếu này sang kiểu khác |
| `IntFunction<R>` | `R apply(int)` | `int` → đối tượng | Chuyển từ primitive `int` thành nhãn, mảng, object |
| `ToIntFunction<T>` | `int applyAsInt(T)` | Đối tượng → `int` | Trích xuất độ dài, số lượng, trọng số, mã số nguyên |
| `IntUnaryOperator` | `int applyAsInt(int)` | `int` → `int` | Biến đổi một số `int` thành số `int` khác |
| `IntPredicate` | `boolean test(int)` | `int` → `boolean` | Kiểm tra điều kiện trên `int` |
| `IntConsumer` | `void accept(int)` | `int` → `void` | Nhận `int` để thực hiện tác vụ |
| `IntSupplier` | `int getAsInt()` | Không đối số → `int` | Cung cấp primitive `int` |
| `IntBinaryOperator` | `int applyAsInt(int,int)` | Hai `int` → `int` | Kết hợp hai số nguyên |
| `ToLongFunction<T>` | `long applyAsLong(T)` | Đối tượng → `long` | Trích giá trị nguyên 64 bit |
| `IntToLongFunction` | `long applyAsLong(int)` | `int` → `long` | Chuyển từ primitive `int` sang primitive `long` |

Các kiểu nhận hoặc trả primitive được thiết kế để tránh boxing/unboxing không cần thiết ở **ranh giới** lời gọi, nhưng không có nghĩa bản thân lambda sẽ tự động nhanh hơn trong mọi trường hợp. Luôn xem chi phí thực tế, kích thước dữ liệu và nhu cầu đọc hiểu code.

Nếu cần **`int → int`**, chọn `IntUnaryOperator` thay vì `IntFunction<Integer>`: kiểu sau trả đối tượng `Integer` và có thể phát sinh boxing. Nếu cần **`String → int`**, chọn `ToIntFunction<String>` thay vì `Function<String,Integer>` khi kết quả được xử lý như primitive trong pipeline số.

### Ví dụ về boxing và kiểu đích

~~~java
// Đoạn code minh họa, không phải chương trình chạy độc lập.
java.util.function.IntFunction<Integer> boxedOutput = n -> n + 1;
java.util.function.ToIntFunction<Integer> boxedInput = n -> n + 1;
java.util.function.IntUnaryOperator bothPrimitive = n -> n + 1;
~~~

- `boxedOutput.apply(3)` nhận primitive `int`, nhưng **trả `Integer`**, vì vậy có chuyển đổi boxing ở kết quả khi cần.
- `boxedInput.applyAsInt(3)` có tham số khai báo là `Integer`; literal `3` phải được boxing thành `Integer` trước lời gọi, sau đó lambda dùng số đó trong phép cộng.
- `bothPrimitive.applyAsInt(3)` nhận và trả primitive `int`, không cần kiểu wrapper ở ranh giới lời gọi.

JVM có các tối ưu hóa như cache wrapper và escape analysis trong những tình huống cụ thể; không nên suy đoán số đối tượng được cấp phát chỉ bằng cách nhìn một biểu thức. Ý nghĩa quan trọng là **hợp đồng kiểu** của từng functional interface.

## 8. Kết hợp hai chiều thành một pipeline

Đôi khi cần trích xuất một `int` từ đối tượng rồi dùng số đó để tạo một object khác:

~~~text
T --ToIntFunction<T>--> int --IntFunction<R>--> R
~~~

Ví dụ `String → độ dài int → nhãn String`. Có thể viết hàm bậc cao để kết hợp hai hợp đồng.

Lưu thành `FunctionPipelineDemo.java`:

~~~java
import java.util.function.Function;
import java.util.function.IntFunction;
import java.util.function.ToIntFunction;

public class FunctionPipelineDemo {
    static <T, R> Function<T, R> viaInt(
            ToIntFunction<? super T> extractor,
            IntFunction<? extends R> formatter) {
        return value -> formatter.apply(extractor.applyAsInt(value));
    }

    public static void main(String[] args) {
        Function<String, String> describeLength =
                viaInt(String::length, n -> "length=" + n);

        ToIntFunction<String> parseAge = Integer::parseInt;
        IntFunction<String> ageGroup =
                n -> n >= 18 ? "adult" : "minor";

        Function<String, String> describeAge = viaInt(parseAge, ageGroup);

        System.out.println(describeLength.apply("lambda"));
        System.out.println(describeAge.apply("21"));
        System.out.println(describeAge.apply("15"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FunctionPipelineDemo.java
java FunctionPipelineDemo
~~~

Stdout:

~~~text
length=6
adult
minor
~~~

**Đọc từng bước:**

1. `String::length` là `ToIntFunction<String>` khi dùng trong `viaInt`; nó nhận `String`, trả `int`.
2. `n -> "length=" + n` là `IntFunction<String>`; nó nhận `int` và trả `String`.
3. `viaInt` ghép hai bước thành `Function<String,String>`, phản ánh việc **kiểu đầu vào ban đầu và kiểu kết quả cuối đều là tham chiếu**.
4. Trong ví dụ thứ hai, `Integer::parseInt` cung cấp chiều `String → int`. `ageGroup` cung cấp chiều `int → String`.
5. Thứ tự rất quan trọng: `formatter.apply(extractor.applyAsInt(value))`. Đảo thứ tự sẽ sai chữ ký trong trường hợp này.

Với chuỗi không phải số nguyên hợp lệ (ví dụ `"abc"`), `Integer.parseInt` ném `NumberFormatException`. Trong ứng dụng thực tế cần kiểm tra hoặc xử lý dữ liệu đầu vào; functional interface không tự kiểm soát ngoại lệ. Đây là ví dụ minh họa phép hợp thành, không phải logic xác minh tuổi dùng trong hệ thống sản xuất.

### Có thể gọi `andThen` trực tiếp không?

`Function<T,R>` cung cấp các phương thức `compose`/`andThen`, nhưng **`IntFunction<R>` và `ToIntFunction<T>` không khai báo `andThen`/`compose` như `Function`**. Trong ví dụ trên, ta kết hợp chúng bằng một lambda mới và trả về `Function<T,R>`. Cách viết này giữ nguyên đầu vào/đầu ra primitive `int` ở bước trung gian trong logic của hàm, dù `Function<T,R>` cuối cùng có các kiểu tham chiếu ở hai đầu.

## 9. Các trường hợp dễ gây lỗi biên dịch

### 9.1. Chọn sai hướng

~~~java
// SAI: IntFunction<String> cần nhận int, không nhận String.
// java.util.function.IntFunction<String> wrong = s -> s.toUpperCase();

// ĐÚNG: tham số là int, kết quả là String.
java.util.function.IntFunction<String> label = n -> "N" + n;
~~~

Dòng sai được bình luận để minh họa. Vì `s` được suy ra là `int`, nó không có phương thức `toUpperCase()`. Nếu cần `String → String`, dùng `Function<String,String>`.

### 9.2. Dùng kiểu trả về không tương thích

~~~java
// SAI: ToIntFunction<String> phải trả int.
// java.util.function.ToIntFunction<String> wrong = s -> "length=" + s.length();

// ĐÚNG:
java.util.function.ToIntFunction<String> length = String::length;
~~~

`ToIntFunction` yêu cầu một kết quả `int`, không phải chuỗi mô tả. Nếu muốn chuỗi mô tả, dùng `Function<String,String>` hoặc kết hợp `ToIntFunction` với `IntFunction<String>`.

### 9.3. Sai phương thức SAM

~~~java
java.util.function.IntFunction<String> show = n -> "value=" + n;
java.util.function.ToIntFunction<String> size = String::length;

// ĐÚNG:
String a = show.apply(5);
int b = size.applyAsInt("hi");

// SAI:
// show.applyAsInt(5);
// size.apply("hi");
~~~

Tên method thuộc interface, không phụ thuộc tên biến hay nội dung lambda.

### 9.4. Sử dụng primitive trong tham số generic

~~~java
// SAI: generic không nhận kiểu primitive.
// IntFunction<int> invalid = n -> n + 1;

// ĐÚNG khi cần int -> int:
java.util.function.IntUnaryOperator increment = n -> n + 1;

// Hợp lệ nhưng boxed output:
java.util.function.IntFunction<Integer> boxed = n -> n + 1;
~~~

Tương tự, `ToIntFunction<int>` không hợp lệ; nếu muốn `int → int`, sử dụng `IntUnaryOperator`.

### 9.5. Nhầm cách dùng với Stream

~~~java
// SAI: Stream<String>.mapToInt không nhận IntFunction.
// Stream.of("a", "bb").mapToInt(n -> "ID-" + n);

// ĐÚNG:
int count = java.util.stream.Stream.of("a", "bb")
        .mapToInt(String::length)
        .sum();
~~~

`mapToInt` nhận **một phần tử của `Stream<String>`** và biến nó thành `int`. Ở ví dụ trên tổng độ dài là `1 + 2 = 3`. Hãy đọc kiểu source của Stream và kiểu Stream cần trả về trước khi chọn hàm.

## 10. Lưu ý về null, kiểu dữ liệu và độ an toàn

- **`int` không có `null`.** `IntFunction<R>` luôn nhận một giá trị `int`. Tuy nhiên `R` là kiểu tham chiếu nên `apply` có thể trả `null` nếu triển khai cho phép.
- **`ToIntFunction<T>` có đầu vào tham chiếu.** Caller có thể truyền `null` (nếu API không ngăn), và lambda như `String::length` sẽ ném `NullPointerException`. Hãy xác định chính sách null ở ranh giới.
- **Kết quả `int` không là `null`.** `ToIntFunction<T>.applyAsInt` luôn trả một `int` khi hoàn tất bình thường; nó vẫn có thể ném unchecked exception như `NumberFormatException`.
- **Miền số hữu hạn.** Nếu trích tổng tiền, số lượng hoặc độ dài vào `int`, kiểm tra phạm vi và tràn số. Chuyển sang `ToLongFunction<T>` và `mapToLong` khi cần miền `long` lớn hơn.
- **Không giả định lambda thuần khiết.** Dù kiểu `IntFunction` hay `ToIntFunction` nói rõ đầu vào/đầu ra, thân lambda vẫn có thể đọc biến mutable hoặc gây tác dụng phụ.
- **Không bắt buộc dùng Stream.** Hai interface là các kiểu hành vi tái sử dụng được trong bất kỳ phương thức nhận callback nào, không riêng `Stream`.

## 11. Cách chọn nhanh theo đề bài

Thử tự mô tả yêu cầu thành một câu có “từ ... sang ...” rồi đi theo bảng:

| Yêu cầu | Hướng | Chọn |
|---|---|---|
| Từ số thứ tự `int` tạo nhãn `String` | `int → String` | `IntFunction<String>` |
| Từ kích thước `int` tạo `String[]` | `int → String[]` | `IntFunction<String[]>` |
| Từ đối tượng `Student` lấy điểm `int` | `Student → int` | `ToIntFunction<Student>` |
| Từ `String` lấy độ dài `int` | `String → int` | `ToIntFunction<String>` |
| Từ `int` tính `int` kế tiếp | `int → int` | `IntUnaryOperator` |
| Từ `String` sinh `Integer` boxed | `String → Integer` | `Function<String,Integer>` (hoặc `ToIntFunction<String>` nếu cần `int`) |
| Từ `int` xác định đúng/sai | `int → boolean` | `IntPredicate` |
| Từ `String` chuyển thành `String` khác | `String → String` | `Function<String,String>` |

Quy tắc chọn không yêu cầu đoán từ tên lambda. Hãy nhìn **kiểu tham số gốc, kiểu kết quả cần thiết và chữ ký SAM**; sau đó cân nhắc nên dùng loại primitive hay boxed.

## 12. Câu hỏi tự kiểm tra

1. `IntFunction<String>` và `ToIntFunction<String>` khác nhau ở tham số/giá trị trả về nào?
2. Vì sao `IntStream.mapToObj` cần `IntFunction` nhưng `Stream<String>.mapToInt` cần `ToIntFunction<String>`?
3. `String[]::new` nhận một kích thước `int` rồi trả `String[]`. Nó tương thích với interface nào? Mảng là primitive hay reference?
4. Nếu cần `int → int`, vì sao `IntUnaryOperator` diễn đạt hợp đồng tốt hơn `IntFunction<Integer>`?
5. Một `ToIntFunction<String>` nhận `"42"` và trả `42` có thể viết bằng method reference nào?
6. `ToIntFunction<String>` có đảm bảo không ném `NumberFormatException` khi nhận `"abc"` không?
7. Khi kết hợp `String → int → String`, hai interface nào thực hiện hai chặng, và kiểu cuối cùng của toàn phép biến đổi là gì?

**Đáp án tóm lược:** (1) `IntFunction<String>: int → String`; `ToIntFunction<String>: String → int`. (2) Vì kiểu đầu vào của mapper là `int` ở `IntStream` và kiểu đầu ra cần `int` ở `Stream<String>`. (3) `IntFunction<String[]>`; mảng là object/reference type. (4) Vì cả tham số và kết quả đều primitive `int`, giảm nhu cầu boxing. (5) `Integer::parseInt`. (6) Không: parser có thể ném ngoại lệ cho chuỗi không hợp lệ. (7) `ToIntFunction<String>` rồi `IntFunction<String>`; sau khi kết hợp, có thể biểu diễn bằng `Function<String,String>`.

**Ghi nhớ:** `IntFunction<R>` nghĩa là **từ `int` sang `R`** (đi **ra** khỏi primitive `int`), còn `ToIntFunction<T>` nghĩa là **từ `T` sang `int`** (đi **vào** primitive `int`). Đây là sự khác biệt về **hướng chuyển đổi**, phương thức SAM và lựa chọn API, không chỉ khác tên gọi.