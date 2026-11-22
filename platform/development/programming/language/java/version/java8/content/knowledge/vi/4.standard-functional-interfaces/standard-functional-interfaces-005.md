# UnaryOperator và BinaryOperator trong Java

## Mục tiêu học tập

`UnaryOperator<T>` và `BinaryOperator<T>` thuộc gói `java.util.function`, được cung cấp từ **Java 8** và vẫn là hai functional interface chuẩn trong Java hiện đại. Chúng mô tả các phép biến đổi hoặc phép kết hợp **giữ nguyên kiểu dữ liệu**: đầu vào và kết quả đều thuộc cùng một kiểu `T`. Chúng thường xuất hiện trong xử lý dữ liệu, chuẩn hóa chuỗi, cập nhật phần tử danh sách, kết hợp kết quả và phép rút gọn (`reduce`).

Sau bài này, bạn có thể:
- Phân biệt `UnaryOperator<T>` với `Function<T,R>`, và `BinaryOperator<T>` với `BiFunction<T,U,R>`.
- Dùng lambda, method reference và các factory `UnaryOperator.identity()`, `BinaryOperator.minBy()`, `BinaryOperator.maxBy()`.
- Giải thích vì sao toán tử chỉ có **một generic type parameter** `T` và hệ quả đối với kiểu kết quả.
- Dùng đúng `List.replaceAll`, `Stream.reduce` và các chuyên biệt nguyên thủy như `IntUnaryOperator`, `IntBinaryOperator`.
- Nhận diện lỗi về kiểu, `null`, side effect, overflow và phép toán **không kết hợp** khi giảm song song.

## 1. Operator là gì trong ngữ cảnh functional interface?

Trong Java, “operator” ở đây là một **hành vi được biểu diễn bằng đối tượng functional interface**, không phải một từ khóa hay toán tử cú pháp mới. Bạn có thể truyền hành vi đó vào phương thức khác, lưu nó trong biến, hoặc viết lambda để triển khai phương thức trừu tượng duy nhất (SAM).

Hai định nghĩa quan trọng:

~~~java
@FunctionalInterface
public interface UnaryOperator<T> extends Function<T, T> {
    // Kế thừa R apply(T t) với R cũng chính là T.
}

@FunctionalInterface
public interface BinaryOperator<T> extends BiFunction<T, T, T> {
    // Kế thừa R apply(T t, U u), cả T, U, R đều là T.
}
~~~

Đây là **minh họa hình dạng generic**, không phải mã nguồn đầy đủ của JDK: hai interface còn có những thành phần được API định nghĩa; bạn không cần và không nên tự khai báo lại chúng để sử dụng.

| Functional interface | Số tham số của SAM | Chữ ký sau khi thay generic | Mục đích |
| --- | --- | --- | --- |
| `Function<T,R>` | 1 | `R apply(T value)` | Chuyển `T` thành `R`, có thể khác kiểu |
| **`UnaryOperator<T>`** | **1** | **`T apply(T value)`** | Biến đổi `T` thành `T` |
| `BiFunction<T,U,R>` | 2 | `R apply(T left, U right)` | Kết hợp hai kiểu đầu vào có thể khác nhau |
| **`BinaryOperator<T>`** | **2** | **`T apply(T left, T right)`** | Kết hợp hai giá trị `T` thành `T` |

**Nhớ nhanh:**
- `UnaryOperator<T>`: **`T -> T`**.
- `BinaryOperator<T>`: **`(T, T) -> T`**.

Một điểm quan trọng: “giữ nguyên kiểu” **không có nghĩa giữ nguyên giá trị** hoặc **trả về chính đối tượng đầu vào**. `UnaryOperator<String>` có thể trả về một `String` mới đã được chuẩn hóa; `UnaryOperator<List<String>>` có thể trả về một danh sách khác. Điều cốt lõi là **kiểu kết quả** được ràng buộc bởi `T`.

## 2. UnaryOperator<T>: phép biến đổi một đầu vào, cùng kiểu đầu ra

Import:

~~~java
import java.util.function.UnaryOperator;
~~~

Ví dụ chuyển một chuỗi sang chữ hoa:

~~~java
UnaryOperator<String> upper = text -> text.toUpperCase();
String result = upper.apply("java"); // "JAVA"
~~~

Ở đây compiler xác định `text` là `String` từ target type `UnaryOperator<String>`; kết quả `apply` cũng là `String`.

Ví dụ với kiểu số:

~~~java
UnaryOperator<Integer> twice = n -> n * 2;
Integer result = twice.apply(7); // 14
~~~

`Integer` là lớp bao (`wrapper`), nên phép nhân tự mở hộp (`unboxing`) thành `int` và kết quả được boxing trở lại `Integer`. Đây là cơ chế quen thuộc của Java; bản thân `UnaryOperator<T>` không biến `T` thành một kiểu nguyên thủy.

### Có thể triển khai bằng method reference

Khi phương thức phù hợp với chữ ký `T -> T`:

~~~java
UnaryOperator<String> withoutEdges = String::strip;
~~~

`String.strip()` được bổ sung từ **Java 11** và vẫn có trong JDK hiện đại. Nó phù hợp vì `String::strip` tương ứng một phép gọi trên một đối tượng `String`, trả về `String`.

Nếu dự án cần `--release 8`, dùng API có trong baseline đó, chẳng hạn `String::trim` **chỉ khi** quy tắc xử lý khoảng trắng `trim` đáp ứng đúng yêu cầu. Không nên coi `trim` và `strip` hoàn toàn đồng nghĩa đối với mọi ký tự Unicode.

### Phân biệt với Function<T,R>

~~~java
UnaryOperator<String> normalize = String::strip;
java.util.function.Function<String, Integer> countUnits =
        String::length;
~~~

`normalize` trả về `String` nên phù hợp `UnaryOperator<String>`. `countUnits` trả về `Integer`/`int` nên phù hợp `Function<String, Integer>`, **không** phải `UnaryOperator<String>`.

Ví dụ sai:

~~~java
// KHÔNG BIÊN DỊCH: kết quả length() là int,
// không tương thích kiểu String của UnaryOperator<String>.
// UnaryOperator<String> invalid = String::length;
~~~

Nếu muốn một phép biến đổi trả về kiểu khác, chọn `Function<T,R>`. Cố dùng operator chỉ vì nó có tên ngắn sẽ làm sai ý nghĩa kiểu.

## 3. UnaryOperator.identity(): phép đồng nhất

`UnaryOperator.identity()` trả về một unary operator nhận giá trị và trả lại giá trị đó, tức **`x -> x`**.

~~~java
UnaryOperator<String> unchanged = UnaryOperator.identity();

System.out.println(unchanged.apply("Java")); // Java
~~~

Nó hữu ích khi cần một default transformation nhưng không muốn thay đổi dữ liệu, ví dụ cấu hình một pipeline có bước biến đổi tùy chọn.

Vì `UnaryOperator<T>` cũng là `Function<T,T>` nên có thể dùng nó ở vị trí API nhận `Function<T,T>`:

~~~java
java.util.function.Function<String, String> noChange =
        UnaryOperator.identity();
~~~

**Lưu ý:** `Function.identity()` cũng tồn tại và trả về `Function<T,T>`. Nếu khai báo mục tiêu là `UnaryOperator<T>`, dùng `UnaryOperator.identity()` để có đúng kiểu chuyên biệt:

~~~java
UnaryOperator<String> operator = UnaryOperator.identity();

// Phép gán sau không hợp lệ nếu không có chuyển đổi thích hợp:
// UnaryOperator<String> wrong = java.util.function.Function.identity();
~~~

Hệ thống kiểu Java không tự coi mọi đối tượng có kiểu `Function<T,T>` là `UnaryOperator<T>`, bởi `UnaryOperator` là interface **con**, dù hai interface có cùng hình dạng SAM trong trường hợp đó.

## 4. Ghép các phép biến đổi: compose và andThen

`UnaryOperator<T>` kế thừa hai phương thức default từ `Function<T,R>`:

- `andThen(after)`: áp dụng phép hiện tại **trước**, rồi áp dụng `after`.
- `compose(before)`: áp dụng `before` **trước**, sau đó mới phép hiện tại.

Ví dụ:

~~~java
import java.util.function.Function;
import java.util.function.UnaryOperator;

UnaryOperator<Integer> doubleIt = n -> n * 2;
UnaryOperator<Integer> addThree = n -> n + 3;

Function<Integer, Integer> a = doubleIt.andThen(addThree);
Function<Integer, Integer> b = doubleIt.compose(addThree);

// a.apply(4) == 11: (4 * 2) + 3
// b.apply(4) == 14: (4 + 3) * 2
~~~

**Cẩn thận về kiểu trả về:** hai phương thức này được **kế thừa từ `Function`**, và kiểu trả về được khai báo là `Function<...>`, **không phải `UnaryOperator<T>`**. Vì vậy, không nên viết:

~~~java
// Không hợp lệ: andThen trả về Function<Integer, Integer>,
// không có bảo đảm trả về UnaryOperator<Integer>.
// UnaryOperator<Integer> bad = doubleIt.andThen(addThree);
~~~

Thay vào đó khai báo biến `Function<Integer,Integer>` như ví dụ trên, hoặc viết một lambda mới nếu API đòi hỏi chính xác `UnaryOperator<T>`:

~~~java
UnaryOperator<Integer> composed = n -> addThree.apply(doubleIt.apply(n));
~~~

Đây là khác biệt nhỏ nhưng thực tế quan trọng khi làm việc với generic và tổ hợp hàm. Thứ tự ghép cũng có thể làm thay đổi kết quả, đặc biệt với phép làm tròn, làm sạch dữ liệu hoặc phép toán không giao hoán.

### UnaryOperator và List.replaceAll

`List<E>.replaceAll(UnaryOperator<E>)` (có từ Java 8) áp dụng operator cho **mỗi phần tử** và **thay thế phần tử trong danh sách**:

~~~java
java.util.List<String> labels =
        new java.util.ArrayList<>(
                java.util.Arrays.asList(" java ", " stream "));

labels.replaceAll(String::strip);
// labels là ["java", "stream"] sau khi gọi.
~~~

Phương thức này **sửa danh sách tại chỗ**; đó là side effect của API `List.replaceAll`, không có nghĩa `UnaryOperator` luôn bắt buộc đột biến dữ liệu. Phải dùng danh sách cho phép thay thế phần tử; `List.of(...)` tạo danh sách không sửa được, nên `replaceAll` không phải thao tác phù hợp trên đó.

## 5. BinaryOperator<T>: hai đầu vào cùng kiểu, một kết quả cùng kiểu

Import:

~~~java
import java.util.function.BinaryOperator;
~~~

Ví dụ cộng hai số nguyên:

~~~java
BinaryOperator<Integer> add = (a, b) -> a + b;

System.out.println(add.apply(7, 5)); // 12
~~~

Có thể dùng method reference cho phương thức hai tham số phù hợp:

~~~java
BinaryOperator<Integer> add = Integer::sum;
BinaryOperator<Integer> max = Integer::max;
BinaryOperator<String> concatenate = (left, right) -> left + right;
~~~

- `Integer::sum` nhận hai `int` và trả về `int`; Java thực hiện boxing/unboxing khi làm việc với `BinaryOperator<Integer>`.
- `Integer::max` trả về số lớn hơn.
- Phép nối chuỗi nhận hai `String` và trả về `String`.

Các phép cộng, lấy max, nối chuỗi đều là **trường hợp sử dụng**, không phải yêu cầu bắt buộc của `BinaryOperator<T>`. Một binary operator có thể là phép trừ, chọn phần tử hoặc hợp nhất hai đối tượng, miễn đầu vào/đầu ra thỏa `(T,T)->T`.

### Phân biệt với BiFunction<T,U,R>

~~~java
java.util.function.BiFunction<String, Integer, String> repeat =
        (text, count) -> text.repeat(count);
~~~

`repeat` nhận `String` và `Integer`, rồi trả `String`: hai loại đầu vào **khác nhau**. Nó phù hợp `BiFunction<String,Integer,String>`, **không** phải `BinaryOperator<String>`.

`String.repeat(int)` có từ **Java 11**; ví dụ chỉ dùng trong chương trình chạy với API mức Java 11+. Khi cần Java 8, tránh sử dụng phương thức này hoặc cài đặt logic lặp khác phù hợp.

## 6. BinaryOperator.minBy và maxBy

`BinaryOperator.minBy(Comparator<? super T>)` và `BinaryOperator.maxBy(Comparator<? super T>)` là hai static factory chuẩn:

- `minBy` tạo operator chọn phần tử **nhỏ hơn theo comparator**.
- `maxBy` tạo operator chọn phần tử **lớn hơn theo comparator**.

Ví dụ chọn chuỗi ngắn/dài theo độ dài:

~~~java
import java.util.Comparator;
import java.util.function.BinaryOperator;

Comparator<String> byLength =
        Comparator.comparingInt(String::length);

BinaryOperator<String> shorter =
        BinaryOperator.minBy(byLength);

BinaryOperator<String> longer =
        BinaryOperator.maxBy(byLength);

// shorter.apply("lambda", "java") == "java"
// longer.apply("lambda", "java") == "lambda"
~~~

Kết quả phụ thuộc **quy tắc comparator**, không nhất thiết tương ứng `Comparable.compareTo` của kiểu `T`. Bạn có thể chọn theo độ dài, giá, mức ưu tiên, thời gian hoặc những thuộc tính nghiệp vụ khác.

Nếu comparator coi hai phần tử là **bằng nhau** (`compare(a,b)==0`), về mặt hợp đồng chọn min/max thì cả hai đều là đáp án phù hợp; nếu thứ tự phụ ổn định là quan trọng, hãy **thêm tiêu chí tie-break vào comparator**:

~~~java
Comparator<String> byLengthThenName =
        Comparator.comparingInt(String::length)
                  .thenComparing(Comparator.naturalOrder());
~~~

Với comparator này, hai chuỗi cùng độ dài vẫn được phân biệt theo thứ tự từ điển khi cần. Đừng dựa vào chi tiết chọn “phần tử đầu”/“phần tử sau” khi các phần tử so sánh bằng nhau nếu đặc tả ứng dụng cần một quyết định rõ ràng.

### Điều kiện để comparator đáng tin cậy

Theo hợp đồng `Comparator`, kết quả so sánh cần có tính nhất quán (đối xứng về dấu, tính bắc cầu và xử lý `compare(a,b)==0` phù hợp). Một comparator không đúng có thể khiến chọn min/max hoặc sắp xếp cho ra kết quả khó dự đoán.

Tránh dạng:

~~~java
// Không nên: phép trừ có thể overflow.
// Comparator<Integer> unsafe = (a, b) -> a - b;
~~~

Thay bằng:

~~~java
Comparator<Integer> ascending = Integer::compare;
~~~

Nếu dữ liệu có `null`, hãy quyết định rõ chính sách `null` và sử dụng comparator hỗ trợ điều đó (ví dụ `Comparator.nullsFirst(...)` hoặc `nullsLast(...)`) khi phù hợp. `minBy` và `maxBy` không tự đặt ra quy tắc xử lý `null` thay cho bạn.

## 7. Chương trình Java 17+ hoàn chỉnh: cả UnaryOperator và BinaryOperator

Tạo tệp **`OperatorsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.function.IntBinaryOperator;
import java.util.function.IntUnaryOperator;
import java.util.function.UnaryOperator;

public class OperatorsDemo {
    public static void main(String[] args) {
        UnaryOperator<String> trimSpace = String::strip;
        UnaryOperator<String> upper =
                s -> s.toUpperCase(Locale.ROOT);

        Function<String, String> normalize =
                trimSpace.andThen(upper);

        UnaryOperator<String> same =
                UnaryOperator.identity();

        System.out.println("normalize=" +
                normalize.apply("  java  "));
        System.out.println("identity=" +
                same.apply("hello"));

        List<String> names = new ArrayList<>(
                Arrays.asList(" an ", " binh ", " chi "));
        names.replaceAll(trimSpace);
        System.out.println("names=" + names);

        BinaryOperator<Integer> add = Integer::sum;
        BinaryOperator<Integer> max = Integer::max;

        System.out.println("add=" + add.apply(7, 5));
        System.out.println("max=" + max.apply(7, 5));

        Comparator<String> byLengthThenName =
                Comparator.comparingInt(String::length)
                          .thenComparing(Comparator.naturalOrder());

        BinaryOperator<String> shorter =
                BinaryOperator.minBy(byLengthThenName);
        BinaryOperator<String> longer =
                BinaryOperator.maxBy(byLengthThenName);

        System.out.println("shorter=" +
                shorter.apply("lambda", "java"));
        System.out.println("longer=" +
                longer.apply("lambda", "java"));

        List<Integer> numbers = Arrays.asList(2, 3, 4);
        int sum = numbers.stream()
                         .reduce(0, Integer::sum);
        int product = numbers.stream()
                             .reduce(1, (a, b) -> a * b);

        System.out.println("reduce-sum=" + sum);
        System.out.println("reduce-product=" + product);

        IntUnaryOperator triple = n -> n * 3;
        IntBinaryOperator bigger = Integer::max;

        System.out.println("triple=" +
                triple.applyAsInt(5));
        System.out.println("primitive-max=" +
                bigger.applyAsInt(8, 11));
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc bản mới hơn có hỗ trợ `--release 17`:

~~~bash
javac --release 17 OperatorsDemo.java
java OperatorsDemo
~~~

**Stdout chính xác:**

~~~text
normalize=JAVA
identity=hello
names=[an, binh, chi]
add=12
max=7
shorter=java
longer=lambda
reduce-sum=9
reduce-product=24
triple=15
primitive-max=11
~~~

Giải thích:

1. `trimSpace` và `upper` là hai `UnaryOperator<String>`; `andThen` tạo **`Function<String,String>`** thực hiện lần lượt hai bước.
2. `UnaryOperator.identity()` giữ nguyên `hello`.
3. `names.replaceAll(trimSpace)` dùng phép biến đổi một-đầu-vào cho từng phần tử danh sách có thể thay đổi.
4. `BinaryOperator<Integer>` áp dụng phép cộng và max; `apply(7,5)` trả kết quả đúng theo từng toán tử.
5. `minBy` và `maxBy` chọn theo comparator độ dài (và tên khi độ dài bằng nhau).
6. `Stream.reduce` nhận hành vi `BinaryOperator<Integer>` để gộp nhiều phần tử thành một giá trị; `0` là identity của phép cộng, `1` là identity của phép nhân.
7. `IntUnaryOperator` và `IntBinaryOperator` làm việc trực tiếp với `int`, giảm nhu cầu boxing/unboxing trong các luồng tính toán nguyên thủy.

Ví dụ dùng `String.strip()` (Java 11+) và `Locale.ROOT` để tránh phụ thuộc locale hệ thống khi chuyển chữ hoa; còn hai operator cùng API `Stream.reduce` và `List.replaceAll` đã hiện diện từ Java 8. Không đánh đồng **tên chủ đề Java 8** với yêu cầu phải chạy trên runtime Java 8 trong một ứng dụng mới.

## 8. BinaryOperator và Stream.reduce: cần hiểu tính kết hợp

`Stream<T>.reduce(T identity, BinaryOperator<T> accumulator)` nhận:
- Một **identity**: giá trị trung tính với phép kết hợp.
- Một **BinaryOperator<T>`: gộp hai giá trị `T` thành một `T`.

Ví dụ:

~~~java
int total = java.util.stream.Stream.of(2, 3, 4)
        .reduce(0, Integer::sum); // 9
~~~

Phép cộng thỏa:

~~~text
0 + x = x + 0 = x
(a + b) + c = a + (b + c)
~~~

Nhờ có identity và tính kết hợp (**associativity**), các phần tử có thể được nhóm lại mà không đổi kết quả toán học, một điều đặc biệt quan trọng khi thực hiện **parallel stream**.

### BinaryOperator<T> không tự bảo đảm associative

Interface chỉ yêu cầu chữ ký `(T,T)->T`. Nó **không** tự kiểm tra tính kết hợp. Ví dụ phép trừ:

~~~java
BinaryOperator<Integer> subtract = (a, b) -> a - b;
~~~

Phép trừ có thể có:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

Hai kết quả khác nhau, nên phép trừ **không kết hợp**. Không dùng nó như phép reduction đòi hỏi kết hợp trong một parallel stream và mong kết quả giống cách tính tuần tự. Việc code biên dịch không chứng minh phép reduce có ý nghĩa toán học đúng.

### Identity phải thật sự trung tính

Ví dụ:

~~~java
BinaryOperator<Integer> multiply = (a, b) -> a * b;

int product = java.util.stream.Stream.of(2, 3, 4)
        .reduce(1, multiply); // 24
~~~

`1` là identity của phép nhân; `0` **không** phải identity của phép nhân vì `0 * x = 0`. Với tổng số nguyên, `0` là identity cộng; với phép nối chuỗi, chuỗi rỗng có thể là identity.

**Một lỗi phổ biến:** dùng giá trị khởi tạo là phần tử đầu tiên trong `reduce(identity, op)` để “bắt đầu tính”. Khi stream không rỗng, identity được xem là giá trị trung tính tham gia reduction, không phải giá trị mẫu tùy ý. Nếu không có identity phù hợp, hãy xét overload `reduce(BinaryOperator<T>)`:

~~~java
java.util.Optional<Integer> result =
        java.util.stream.Stream.of(2, 3, 4)
                .reduce(Integer::max);

// result có giá trị 4; stream rỗng -> Optional.empty().
~~~

`Optional<T>` biểu đạt rằng có thể không có kết quả trên stream rỗng. Khi dùng overload trả `Optional`, phép kết hợp vẫn cần phù hợp hợp đồng reduce; riêng null result có các ràng buộc từ API, nên tránh phép kết hợp trả `null`.

### Stateless và không can thiệp vào nguồn

Accumulator dùng cho reduce nên **không có side effect tác động vào dữ liệu nguồn** và tuân thủ yêu cầu non-interfering, stateless mà Stream API áp đặt. Đừng xây phép reduce bằng cách ghi vào một `ArrayList` ngoài luồng từ nhiều thread. Với bài toán tạo collection, dùng `collect` với collector phù hợp thay vì lạm dụng `reduce`.

Nếu dùng overload ba tham số `reduce(identity, accumulator, combiner)` của stream, chữ ký và quy tắc kết hợp phức tạp hơn; các giá trị identity và combiner phải tương thích với accumulator. Bài học này tập trung vào overload đúng với `BinaryOperator<T>`, nhưng nguyên tắc associative/non-interfering vẫn cần chú ý.

## 9. Chuyên biệt primitive: Int/Long/Double UnaryOperator và BinaryOperator

Generic `UnaryOperator<Integer>` hay `BinaryOperator<Integer>` làm việc qua wrapper `Integer`. Khi xử lý lượng lớn số nguyên thủy trong vòng lặp hoặc primitive streams, Java cung cấp các interface chuyên biệt:

| Loại | Unary | Binary | Phương thức SAM |
| --- | --- | --- | --- |
| `int` | `IntUnaryOperator` | `IntBinaryOperator` | `int applyAsInt(int)` / `int applyAsInt(int,int)` |
| `long` | `LongUnaryOperator` | `LongBinaryOperator` | `long applyAsLong(long)` / `long applyAsLong(long,long)` |
| `double` | `DoubleUnaryOperator` | `DoubleBinaryOperator` | `double applyAsDouble(double)` / `double applyAsDouble(double,double)` |

Ví dụ:

~~~java
java.util.function.IntUnaryOperator square =
        x -> x * x;

java.util.function.IntBinaryOperator sum =
        Integer::sum;

int a = square.applyAsInt(4); // 16
int b = sum.applyAsInt(4, 5); // 9
~~~

Các kiểu nguyên thủy chuyên biệt sử dụng `applyAsInt`, `applyAsLong` hoặc `applyAsDouble`, **không phải `apply`**. Sử dụng chúng đúng cách giúp tránh nhiều chuyển đổi boxing/unboxing, đặc biệt trong `IntStream`, `LongStream`, `DoubleStream` và các thao tác tính toán thường xuyên.

**Không có** các cặp `FloatUnaryOperator` hay `BooleanBinaryOperator` tương ứng trong `java.util.function` chuẩn; không tự suy ra tên interface dựa trên mẫu đặt tên. Với kiểu khác, dùng functional interface sẵn có phù hợp hoặc định nghĩa interface riêng nếu hợp đồng thực sự cần.

### Chuyển từ boxed sang primitive: cần cân nhắc null

`UnaryOperator<Integer>` có thể nhận `null` ở mức kiểu tham chiếu, nhưng phép toán số thường sẽ unbox và có thể ném `NullPointerException`. `IntUnaryOperator` nhận `int` nên bản thân tham số không thể là `null`. Khi dữ liệu đầu vào cho phép thiếu giá trị, nên xác định cách biểu diễn/trả lỗi rõ ràng, thay vì dựa vào unboxing vô tình.

## 10. Generic, type inference và lựa chọn đúng interface

Với một operator generic:

~~~java
static <T> T applyOnce(
        T value,
        java.util.function.UnaryOperator<T> change) {
    return change.apply(value);
}
~~~

Nếu gọi:

~~~java
String result = applyOnce("java", String::toUpperCase);
~~~

compiler suy ra `T` là `String` (trong ngữ cảnh phù hợp) và kiểm tra `String::toUpperCase` có chữ ký tương ứng `String -> String`.

Tương tự:

~~~java
static <T> T combine(
        T first,
        T second,
        java.util.function.BinaryOperator<T> op) {
    return op.apply(first, second);
}
~~~

Chọn tên tham số có ý nghĩa sẽ giúp người đọc hiểu `op` là phép cộng, phép min, phép hợp nhất hay phép nối. Interface **không** quy định tên thuật toán, tính kết hợp, tính giao hoán hay độ thuần của một phép toán.

### T không bắt buộc là immutable

Ví dụ:

~~~java
UnaryOperator<StringBuilder> appendMark =
        builder -> builder.append("!");
~~~

Đây là toán tử hợp lệ theo kiểu vì nhận và trả `StringBuilder`. Tuy nhiên nó **mutate** đối tượng đầu vào rồi trả lại chính đối tượng đó. Nếu áp dụng nhiều lần, kết quả phụ thuộc trạng thái; việc gọi đồng thời trên cùng `StringBuilder` còn có rủi ro thread-safety.

Đây là lý do trong xử lý stream và pipeline, bạn phải xét hợp đồng **side effect** chứ không mặc định mọi operator là hàm thuần. Với dữ liệu immutable và phép biến đổi thuần, lập luận và kiểm thử thường dễ hơn, nhưng không phải mọi use case đều buộc phải immutable.

## 11. Những lỗi phổ biến và cách sửa

1. **Nhầm UnaryOperator<T> với Function<T,R>:** `UnaryOperator<String> length = String::length` sai vì trả `int`; dùng `Function<String,Integer>`.
2. **Nhầm BinaryOperator<T> với BiFunction<T,U,R>:** hai tham số khác kiểu không thể biểu diễn bằng `BinaryOperator<T>` chung nếu kết quả không cùng kiểu.
3. **Gán nhầm kết quả andThen/compose:** hai phương thức kế thừa trả `Function<...>`, không tự biến thành `UnaryOperator<T>`.
4. **Tưởng identity() là “khởi tạo mặc định một giá trị”:** `UnaryOperator.identity()` đơn giản trả lại đầu vào, không tạo ra `new T()`.
5. **Dùng minBy/maxBy mà không hiểu Comparator:** kết quả được quyết định theo comparator, không mặc nhiên theo giá trị số/tên tự nhiên.
6. **Dùng `a - b` để làm Comparator<Integer>:** có thể overflow; thay bằng `Integer.compare(a,b)`.
7. **Dùng operator không associative trong parallel reduce:** đầu ra phụ thuộc cách nhóm; chọn phép gộp đáp ứng hợp đồng reduce.
8. **Dùng sai identity trong reduce:** `0` không phải identity của phép nhân; `1` không phải identity của phép cộng.
9. **Dùng phép cộng số nguyên không kiểm soát overflow:** `Integer::sum` có kiểu `int` và có thể overflow; khi nghiệp vụ cần báo lỗi, cân nhắc `Math.addExact` hoặc kiểu số thích hợp.
10. **Quên null và boxing:** wrapper `Integer` có thể null, phép toán nguyên thủy có thể gây NPE khi unbox.
11. **Không nhận biết List.replaceAll có thay đổi danh sách:** đừng dùng trên danh sách không hỗ trợ thay thế phần tử; cân nhắc `stream().map(...)` nếu muốn tạo collection mới.
12. **Dựa vào hành vi chia nhánh/tie không được đặc tả:** với `minBy/maxBy` có hai giá trị comparator coi bằng nhau, bổ sung tie-break khi cần quy tắc lựa chọn rõ ràng.
13. **Mặc định Java 8 có mọi API trong ví dụ Java mới:** `String.strip()`/`String.repeat()` thuộc Java 11+, trong khi chính `UnaryOperator`, `BinaryOperator` và các phương thức static quan trọng của chúng đã có từ Java 8.

## 12. Bài tập thực hành

**Bài 1.** Khai báo `UnaryOperator<String>` chuẩn hóa chuỗi bằng cách bỏ khoảng trắng ở hai đầu và chuyển sang chữ thường không phụ thuộc locale. Test với `"  JAVA  "`. Giải thích vì sao `String::length` không thể thay thế operator này.

**Bài 2.** Viết `BinaryOperator<Integer>` chọn số nhỏ hơn bằng lambda và bằng `BinaryOperator.minBy(Integer::compare)`. So sánh kết quả với các cặp `(7, 3)`, `(-5, 4)`, `(0, 0)`.

**Bài 3.** Cho `UnaryOperator<Integer> minusOne = n -> n - 1` và `UnaryOperator<Integer> square = n -> n * n`. Tính kết quả khi áp dụng lần lượt **square rồi minusOne** cho `5` và chiều ngược lại. Lưu ý kiểu của `andThen`.

**Bài 4.** Dùng `List.replaceAll` để biến `[" An ", " Binh "]` thành `["An", "Binh"]`. Phân biệt thao tác này với `stream().map(String::strip).toList()` về việc tạo collection mới; `Stream.toList()` chỉ được bổ sung từ Java 16.

**Bài 5.** Dùng `Stream.of(2,3,4)` tính tổng, tích và max bằng `reduce`. Chọn identity đúng khi dùng overload có identity; giải thích vì sao reduction trên stream rỗng cần được xét riêng.

**Bài 6.** Cho `BinaryOperator<Integer> subtract = (a,b) -> a-b`. Nêu một bộ ba số cho thấy không associative. Giải thích tại sao không nên dựa vào kết quả reduce song song với toán tử đó.

**Bài 7.** Thay `UnaryOperator<Integer>` và `BinaryOperator<Integer>` bằng `IntUnaryOperator` và `IntBinaryOperator`. Nêu sự khác biệt về tên phương thức SAM và khả năng nhận `null`.

**Bài 8.** Viết một comparator chọn chuỗi có độ dài ngắn nhất, nếu bằng nhau chọn chuỗi nhỏ hơn theo thứ tự từ điển, rồi tạo `BinaryOperator.minBy(comparator)`. Thử `"cat"` và `"ant"`.

## Tổng kết

- **`UnaryOperator<T>` là `Function<T,T>`:** một đầu vào `T`, một kết quả `T`, SAM `apply(T)`.
- **`BinaryOperator<T>` là `BiFunction<T,T,T>`:** hai đầu vào cùng `T`, một kết quả `T`, SAM `apply(T,T)`.
- Dùng **`UnaryOperator.identity()`** khi cần phép giữ nguyên, **`BinaryOperator.minBy/maxBy`** khi cần chọn theo comparator.
- `UnaryOperator` hợp với các phép biến đổi từng phần tử như **`List.replaceAll`**; `BinaryOperator` hợp với phép kết hợp như **`Stream.reduce`**.
- **Kiểu cùng T không kéo theo tính thuần, associative, commutative hay thread-safe**. Những tính chất này phụ thuộc hợp đồng phép toán và cách API sử dụng nó.
- Với dữ liệu primitive, cân nhắc **`Int/Long/DoubleUnaryOperator`** và **`Int/Long/DoubleBinaryOperator`**.
- Các interface trên vẫn là phần chuẩn của Java hiện đại; chỉ khác biệt rõ baseline giữa tính năng từ Java 8 và API như `String.strip`/`repeat` từ Java 11 hoặc `Stream.toList` từ Java 16.

## Tài liệu chuẩn để tra cứu

- Java SE 17, `UnaryOperator<T>`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/UnaryOperator.html
- Java SE 17, `BinaryOperator<T>`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/BinaryOperator.html
- Java SE 17, `Function<T,R>` (`compose`, `andThen`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html
- Java SE 17, `BiFunction<T,U,R>`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/BiFunction.html
- Java SE 17, `IntUnaryOperator` và `IntBinaryOperator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/IntUnaryOperator.html và https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/IntBinaryOperator.html
- Java SE 17, `List.replaceAll`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#replaceAll(java.util.function.UnaryOperator)
- Java SE 17, `Stream.reduce`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html
- Java SE 17, `Comparator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html

Khi cần viết phần mềm chạy trên baseline khác, đối chiếu Javadoc và `@since` của **chính API được sử dụng**; không coi mọi API xuất hiện trong bài minh họa JDK 17 là API đã có ở Java 8.