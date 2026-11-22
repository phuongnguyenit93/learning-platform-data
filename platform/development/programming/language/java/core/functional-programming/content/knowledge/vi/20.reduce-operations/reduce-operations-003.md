# Phần tử đơn vị và `reduce()` có giá trị khởi đầu trong Java Stream

## 1. Vì sao phép rút gọn cần phần tử đơn vị?

Trong Java Stream API, `reduce` (*reduction*) là thao tác kết thúc (*terminal operation*) kết hợp nhiều phần tử thành **một giá trị tổng hợp**, chẳng hạn tổng số, tích, chuỗi ghép, giá trị lớn nhất hoặc một kết quả được tính dần.

~~~java
List<Integer> numbers = List.of(2, 3, 4);

int total = numbers.stream()
        .reduce(0, Integer::sum);

System.out.println(total); // 9
~~~

Hai thành phần của lệnh trên là:

- **`0`**: giá trị khởi đầu và đồng thời phải là **phần tử đơn vị** (*identity element*) đối với phép cộng.
- **`Integer::sum`**: hàm gộp hai giá trị `Integer` thành một `Integer`, ở đây là phép cộng.

Với luồng tuần tự, ta có thể đọc theo sơ đồ:

~~~text
identity = 0
0 + 2  = 2
2 + 3  = 5
5 + 4  = 9
result = 9
~~~

Điểm quan trọng: `0` không được chọn chỉ vì “muốn bắt đầu từ số 0”. Nó đúng vì **cộng 0 ở cả bên trái hoặc bên phải không làm thay đổi giá trị**. Trong phép nhân, phần tử đơn vị là `1`; trong ghép chuỗi, nó là chuỗi rỗng `""`. Dùng sai phần tử đơn vị có thể khiến kết quả sai, đặc biệt khi chạy song song.

Bài này tập trung vào hai overload `reduce` có **giá trị khởi đầu (identity)** và những điều kiện phải thỏa để dùng chúng chính xác trong Java 17+.

## 2. Chữ ký hai dạng `reduce` cần hiểu

### 2.1. Dạng hai tham số — `reduce(identity, accumulator)`

Trên `Stream<T>`:

~~~java
T reduce(T identity, BinaryOperator<T> accumulator);
~~~

`BinaryOperator<T>` là functional interface có hành vi:

~~~java
T apply(T left, T right);
~~~

Nó nhận hai giá trị cùng kiểu `T` và tạo một kết quả cùng kiểu. Bởi vậy với `Stream<Integer>`:

~~~java
int sum = Stream.of(1, 2, 3)
        .reduce(0, (a, b) -> a + b);

int product = Stream.of(1, 2, 3)
        .reduce(1, (a, b) -> a * b);
~~~

Kết quả lần lượt là `6` và `6`. Tuy số ví dụ tình cờ bằng nhau, **phần tử đơn vị khác nhau**: cộng dùng 0, nhân dùng 1.

- `identity` có kiểu `T`, chính là kiểu phần tử của stream.
- `accumulator` kết hợp trạng thái tổng hợp hiện tại với một phần tử tiếp theo, trả lại một `T` mới.
- Dạng này trả thẳng **`T`**, không trả `Optional<T>`.
- Khi stream rỗng, kết quả là **chính identity**.

### 2.2. Dạng ba tham số — `reduce(identity, accumulator, combiner)`

Trên `Stream<T>`:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner);
~~~

Dạng này cho phép **kiểu kết quả `U` khác kiểu phần tử `T`**:

- `identity` có kiểu `U`.
- `accumulator` nhận giá trị tích lũy `U` và phần tử nguồn `T`, trả `U`.
- `combiner` kết hợp hai kết quả tích lũy `U`, thường cần thiết để nối các kết quả phân vùng trong parallel stream.

Ví dụ: nguồn là chuỗi, kết quả là tổng độ dài dạng số nguyên.

~~~java
int totalLength = Stream.of("Java", "API", "Stream")
        .reduce(
                0,
                (lengthSoFar, word) -> lengthSoFar + word.length(),
                Integer::sum);

System.out.println(totalLength); // 13
~~~

`Stream<String>` đã được rút gọn thành `Integer`. Với bài toán này, `mapToInt(String::length).sum()` thường ngắn và rõ hơn; nhưng ví dụ ba tham số cho thấy cơ chế `accumulator` khác `combiner`.

## 3. Định nghĩa toán học: thế nào là phần tử đơn vị?

Cho phép toán nhị phân `⊕` trên kiểu `T`. Giá trị `e` là **phần tử đơn vị hai phía** nếu với mọi `x` trong miền dữ liệu hợp lệ:

\[
e \oplus x = x \quad \text{và} \quad x \oplus e = x.
\]

Điều kiện này đặc biệt quan trọng khi thuật toán chia nguồn thành nhiều phần và gộp lại. Đối với `reduce(identity, accumulator)`, hợp đồng yêu cầu accumulator có tính **kết hợp** (*associativity*) và identity là phần tử đơn vị của phép đó.

Tính kết hợp:

\[
(a \oplus b) \oplus c = a \oplus (b \oplus c).
\]

Tính kết hợp không giống tính giao hoán: phép ghép chuỗi là kết hợp nhưng không giao hoán vì `"A" + "B"` khác `"B" + "A"`. Do đó, **không bắt buộc phép gộp phải giao hoán** mới sử dụng được `reduce`, nhưng phải tuân thủ hợp đồng về kết hợp và không can thiệp trạng thái bên ngoài.

Bảng các trường hợp quen thuộc:

| Mục tiêu | Phép gộp | Identity đúng | Vì sao trung hòa? |
| --- | --- | --- | --- |
| Tổng số nguyên | `a + b` | `0` | `0 + x = x + 0 = x` |
| Tích số nguyên | `a * b` | `1` | `1 * x = x * 1 = x` |
| Ghép chuỗi | `String::concat` | `""` | Chuỗi rỗng ghép hai phía không đổi nội dung |
| AND boolean | `a && b` | `true` | `true && x = x && true = x` |
| OR boolean | `a \|\| b` | `false` | `false \|\| x = x \|\| false = x` |
| Lấy max của `int` | `Integer::max` | `Integer.MIN_VALUE` | Mọi giá trị `int` đều không nhỏ hơn `MIN_VALUE` |
| Lấy min của `int` | `Integer::min` | `Integer.MAX_VALUE` | Mọi giá trị `int` đều không lớn hơn `MAX_VALUE` |

Các identity max/min trong bảng dựa vào **miền giá trị `int` đầy đủ**, nơi `MIN_VALUE` và `MAX_VALUE` thực sự thuộc miền. Nếu không muốn coi sentinel là kết quả hợp lệ cho stream rỗng, dùng overload `reduce(BinaryOperator)` trả `Optional` hoặc các terminal `min`/`max` tương ứng sẽ diễn đạt “không có kết quả” rõ hơn.

Với phép trừ, `0 - x = -x` nhưng `x - 0 = x`, nên 0 **không phải phần tử đơn vị hai phía**. Phép trừ cũng không kết hợp: `(10 - 3) - 2 = 5`, trong khi `10 - (3 - 2) = 9`. Vì vậy không sử dụng `reduce(0, (a,b) -> a-b)` như một reduction song song hợp lệ chỉ vì ở tuần tự kết quả có vẻ dự đoán được.

## 4. Hành vi khi stream rỗng

Một lợi ích quan trọng của overload có identity là **luôn có giá trị trả về thuộc kiểu T/U**, kể cả không có phần tử:

~~~java
int emptySum = Stream.<Integer>empty()
        .reduce(0, Integer::sum);

int emptyProduct = Stream.<Integer>empty()
        .reduce(1, (a, b) -> a * b);

String emptyConcat = Stream.<String>empty()
        .reduce("", String::concat);

System.out.println(emptySum);                // 0
System.out.println(emptyProduct);            // 1
System.out.println(emptyConcat.isEmpty());   // true
~~~

Kết quả stream rỗng không phải “null ngầm định”, không phải ngoại lệ, cũng không phải giá trị sinh bởi accumulator. Nó là **identity được cung cấp**.

Nếu muốn phân biệt rõ “không có dữ liệu” với “giá trị tổng hợp bằng 0”, overload không identity phù hợp hơn:

~~~java
Optional<Integer> noResult = Stream.<Integer>empty()
        .reduce(Integer::sum);

System.out.println(noResult.isEmpty()); // true
~~~

Tổng của một tập rỗng có thể được quy ước là 0 trong toán học và nhiều nghiệp vụ thống kê; nhưng nếu hệ thống cần báo “chưa có bản ghi”, trả Optional rỗng có thể là lựa chọn đúng hơn.

## 5. Phân biệt ba overload của `reduce`

Java cung cấp ba dạng thường gặp trên reference stream:

| Cú pháp | Kiểu trả về | Khi nguồn rỗng | Khi nên dùng |
| --- | --- | --- | --- |
| `reduce(BinaryOperator<T>)` | `Optional<T>` | `Optional.empty()` | Không có identity phù hợp hoặc cần biểu diễn thiếu dữ liệu |
| `reduce(T identity, BinaryOperator<T>)` | `T` | Identity | Nguồn và kết quả cùng kiểu, phép gộp có đơn vị |
| `reduce(U identity, BiFunction<U,T,U>, BinaryOperator<U>)` | `U` | Identity | Cần kết quả kiểu khác hoặc mô tả tích lũy/kết hợp riêng |

Ví dụ tổng không có identity:

~~~java
Optional<Integer> sumMaybe = Stream.of(2, 3, 4)
        .reduce(Integer::sum);

System.out.println(sumMaybe.orElseThrow()); // 9
~~~

Ví dụ cùng nguồn nhưng có identity:

~~~java
int sumAlways = Stream.of(2, 3, 4)
        .reduce(0, Integer::sum);

System.out.println(sumAlways); // 9
~~~

Hai kết quả có ý nghĩa số học giống nhau với nguồn không rỗng, nhưng **hình thức kiểu và hành vi khi rỗng khác nhau**.

Với `IntStream`, `LongStream` và `DoubleStream` cũng có overload `reduce(identity, operator)` tương ứng, cũng như overload không identity trả `OptionalInt`, `OptionalLong`, `OptionalDouble`. Tuy nhiên, primitive stream có các terminal chuyên dụng như `sum()`, `min()` và `max()` thường rõ nghĩa và có thể được tối ưu tốt hơn.

## 6. Giá trị khởi đầu không phải “khoản cộng thêm tùy ý”

Đây là lỗi phổ biến nhất:

~~~java
int result = Stream.of(1, 2, 3)
        .reduce(10, Integer::sum);

System.out.println(result); // 16 khi chạy tuần tự
~~~

Nếu chỉ xét chạy tuần tự, diễn tiến là `10 + 1 + 2 + 3 = 16`. Nhưng `10` **không phải identity của phép cộng**. Hợp đồng `reduce` yêu cầu `0` là identity, nên đoạn code trên **không phải một phép reduction hợp lệ để dựa vào khi chuyển sang parallel**.

Với parallel stream, các nhóm dữ liệu có thể được rút gọn riêng, mỗi nhóm được khởi tạo với identity, sau đó gộp bằng accumulator/combiner. Do đó, kết quả dùng “identity = 10” **có thể phụ thuộc cách phân chia** và không được hứa bằng `16`:

~~~java
// Không dùng cách này để diễn đạt "10 cộng với tổng các phần tử":
int wrongInParallel = Stream.of(1, 2, 3)
        .parallel()
        .reduce(10, Integer::sum);
~~~

Nếu nghiệp vụ thực sự cần “cộng khoản cố định 10 đúng một lần vào tổng”, hãy viết:

~~~java
int correct = 10 + Stream.of(1, 2, 3)
        .parallel()
        .reduce(0, Integer::sum);

System.out.println(correct); // 16
~~~

**Quy tắc:** chỉ đưa vào tham số `identity` một phần tử đơn vị thật sự đối với phép gộp. Mọi khoản cộng thêm cố định, phí xử lý, bù trừ hay hệ số nghiệp vụ khác nên được áp dụng **sau khi reduction** hoặc diễn đạt bằng một thiết kế kết hợp khác bảo đảm luật đại số.

Tương tự, với phép nhân:

~~~java
int product = Stream.of(2, 3, 4)
        .reduce(1, (a, b) -> a * b); // 24
~~~

Không dùng `0` làm identity nhân: `0 * x = 0` nên phép rút gọn sẽ sai mục tiêu. `0` là *phần tử hấp thụ* (*annihilator*) của phép nhân, **không phải** phần tử đơn vị.

## 7. Rút gọn song song: tính kết hợp quan trọng hơn thứ tự chạy

Trong pipeline tuần tự, ta thường hình dung phép gộp chạy từ trái sang phải. Nhưng Stream API được thiết kế cho cả parallel stream, nơi kết quả trung gian có thể được tính ở những nhánh khác nhau rồi kết hợp lại.

Với phép cộng số nguyên và identity 0:

~~~java
int total = IntStream.rangeClosed(1, 100)
        .parallel()
        .reduce(0, Integer::sum);

System.out.println(total); // 5050
~~~

`Integer::sum` có tính kết hợp theo ngữ nghĩa số nguyên Java, còn 0 là đơn vị. Dù chia nguồn thành những phần nào, kết quả của phép cộng các số từ 1 đến 100 vẫn là 5050 (không có overflow trong ví dụ).

Mô hình tư duy:

~~~text
Nguồn: [1,2,3,4]

Nhánh A: reduce(0, +) trên [1,2] -> 3
Nhánh B: reduce(0, +) trên [3,4] -> 7
Gộp kết quả: 3 + 7 -> 10

Tương đương phép cộng tuần tự:
(((0 + 1) + 2) + 3) + 4 -> 10
~~~

Sơ đồ chỉ minh họa một cách phân chia hợp lệ, **không mô tả lịch phân chia cố định** của JVM.

### 7.1. Tính kết hợp không đồng nghĩa tính giao hoán

~~~java
String combined = Stream.of("A", "B", "C")
        .reduce("", String::concat);

System.out.println(combined); // ABC
~~~

Ghép chuỗi có tính kết hợp và `""` là identity, nhưng thứ tự chuỗi quan trọng. Với nguồn có encounter order, một ordered reduction có thể bảo toàn thứ tự kết hợp logic để tạo kết quả tương ứng. Không được hiểu parallel sẽ tùy tiện đổi `ABC` thành `CBA` nếu operation và nguồn mang hợp đồng thứ tự thích hợp.

### 7.2. Phép toán dấu phẩy động có thể không kết hợp chính xác

Cộng số thực `double` không kết hợp tuyệt đối về mặt bit vì quy tắc làm tròn IEEE 754:

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

// (a + b) + c có thể là 1.0.
// a + (b + c) có thể là 0.0 theo arithmetic double.
~~~

Do đó, rút gọn dấu phẩy động có thể cho kết quả hơi khác theo thứ tự gộp, nhất là song song. Với bài toán độ chính xác cao, phải chọn thuật toán/kiểu dữ liệu và tiêu chí sai số phù hợp, không mặc định phép cộng double có tính kết hợp toán học hoàn hảo.

## 8. Dạng ba tham số: identity thuộc kiểu kết quả U

Tình huống: từ `Stream<String>` tính tổng độ dài `Integer`.

~~~java
List<String> words = List.of("Java", "API", "Stream");

int totalLength = words.stream()
        .reduce(
                0,
                (lengthSoFar, word) -> lengthSoFar + word.length(),
                Integer::sum);

System.out.println(totalLength); // 13
~~~

Đọc theo chữ ký:

~~~text
T = String
U = Integer

identity:     Integer = 0
accumulator:  (Integer, String) -> Integer
combiner:     (Integer, Integer) -> Integer
result:       Integer
~~~

Khi chạy song song, từng phần có thể tạo ra một `Integer` rồi `combiner` gộp các phần đó. Vì identity là 0 cho phép cộng các kết quả `Integer`, nó không làm thay đổi kết quả của một nhánh.

### 8.1. Điều kiện tương thích accumulator/combiner

Dạng ba tham số không chỉ yêu cầu combiner kết hợp và identity trung hòa. Java còn yêu cầu **accumulator tương thích với combiner**:

\[
\text{combiner}(u,\ \text{accumulator}(identity,t))
=
\text{accumulator}(u,t).
\]

Đẳng thức phải đúng với các giá trị thích hợp `u` (kết quả tích lũy) và `t` (phần tử nguồn). Với phép tính độ dài:

~~~text
combiner(u, accumulator(0, word))
= u + (0 + word.length())
= u + word.length()
= accumulator(u, word)
~~~

Nhờ đó, tích lũy từng nhánh rồi gộp lại có ý nghĩa tương đương tích lũy trực tiếp. Nếu accumulator sinh giá trị khác nhau tùy số lần hoặc vị trí được gọi, chẳng hạn tự gắn dấu phân cách ở đầu mỗi nhánh, có thể vi phạm quy tắc này.

### 8.2. Ví dụ đếm phần tử theo điều kiện

~~~java
long countLongWords = Stream.of("a", "java", "stream", "io")
        .reduce(
                0L,
                (count, word) -> count + (word.length() >= 4 ? 1L : 0L),
                Long::sum);

System.out.println(countLongWords); // 2
~~~

Đây là một reduction hợp lệ: accumulator tạo số đếm từ `String`, combiner cộng các số đếm, identity là `0L`. Tuy vậy, nếu chỉ cần đếm, `filter(...).count()` thường diễn đạt đơn giản hơn:

~~~java
long count = Stream.of("a", "java", "stream", "io")
        .filter(word -> word.length() >= 4)
        .count();
~~~

Một API mạnh không có nghĩa phải dùng ở mọi nơi. Chọn terminal chuyên biệt nếu nó rõ nghĩa hơn.

## 9. Khi nào không nên dùng `reduce` để tích lũy mutable?

Hợp đồng của `reduce` yêu cầu hàm tích lũy không can thiệp dữ liệu nguồn, stateless và phù hợp với cách chia/gộp. Đặc biệt, **không được lấy một đối tượng mutable làm identity rồi sửa chính nó** như một bộ chứa chia sẻ:

~~~java
// Ví dụ SAI về thiết kế reduction; không dùng trong thực tế:
// StringBuilder joined = words.parallelStream().reduce(
//         new StringBuilder(),
//         (builder, word) -> builder.append(word),
//         (left, right) -> left.append(right));
// Identity mutable bị chia sẻ và accumulator sửa trực tiếp đối tượng.
~~~

Với parallel stream, các nhánh có thể cùng tham chiếu tới một identity mutable và thực hiện mutation không an toàn. Ngay cả tuần tự, thiết kế đó cũng không theo ý nghĩa của phép gộp giá trị không đổi mà `reduce` yêu cầu.

Nếu cần ghép nhiều chuỗi, dùng collector chuyên biệt:

~~~java
String joined = Stream.of("A", "B", "C")
        .collect(Collectors.joining(","));

System.out.println(joined); // A,B,C
~~~

Nếu cần xây dựng một `List`:

~~~java
List<String> collected = Stream.of("A", "B", "C")
        .collect(Collectors.toList());
~~~

`collect` là thao tác **mutable reduction** với supplier tạo container, accumulator cập nhật container, combiner gộp container. Nó có hợp đồng riêng để hỗ trợ container mutable an toàn hơn, thay vì ép mutation vào `reduce`. Với luồng số, `sum`, `summaryStatistics` hoặc collector thống kê có thể là lựa chọn rõ ràng.

### 9.1. Identity phải bất biến hay chỉ cần không bị sửa?

Điểm cốt lõi không phải Java cấm mọi object mutable xuất hiện trong toán tử reduction, mà là thiết kế reduction **không được làm thay đổi identity chia sẻ hoặc trạng thái ngoài theo cách phá tính kết hợp, không can thiệp và tương thích song song**. Trong thực tế, ưu tiên các accumulator tạo kết quả mới, và dùng `collect` nếu cần biến đổi một container mutable.

Nếu dùng `String` hay `Integer` như identity, những kiểu bất biến này giúp giảm nguy cơ chia sẻ trạng thái. Với custom type, cần xác định operation và identity theo một mô hình đại số rõ ràng.

## 10. Vấn đề null, overflow và trường hợp không có giá trị đơn vị tự nhiên

### 10.1. Null không phải identity mặc định

~~~java
// Không coi null là "khởi đầu rỗng" một cách tùy tiện:
Stream<String> words = Stream.of("A", "B");
// String joined = words.reduce(null, String::concat);
// Có thể gây NullPointerException khi accumulator áp dụng String::concat.
~~~

Nếu muốn ghép chuỗi, dùng `""` làm identity. Nếu muốn biểu diễn không có phần tử, cân nhắc `Optional`, không phải null. Trong reference streams, một số bước có thể chứa giá trị null, nhưng accumulator vẫn phải được thiết kế để xử lý an toàn và hợp đồng kết quả phù hợp.

### 10.2. Overflow số nguyên

Phần tử đơn vị đúng không tự động ngăn overflow:

~~~java
int sum = IntStream.of(Integer.MAX_VALUE, 1)
        .reduce(0, Integer::sum);

System.out.println(sum); // -2147483648 (overflow kiểu int)
~~~

Phép cộng `int` Java theo arithmetic 32-bit cho kết quả wraparound khi overflow; nếu dữ liệu có thể vượt phạm vi, cân nhắc chuyển sang `long` trước khi cộng hoặc sử dụng `Math.addExact` để phát hiện overflow theo chính sách lỗi. Chú ý `Math.addExact` có thể ném `ArithmeticException` tùy dữ liệu và thứ tự thực thi.

### 10.3. Không có identity tự nhiên cho mọi bài toán

Với bài toán “chọn phần tử tốt nhất”, nếu miền dữ liệu không có giá trị nhỏ nhất hoặc lớn nhất toàn cục đúng nghĩa, không nên tự bịa sentinel:

~~~java
Optional<Integer> max = Stream.of(-7, -3, -9)
        .reduce(Integer::max);

System.out.println(max.orElseThrow()); // -3
~~~

Viết `reduce(0, Integer::max)` sẽ cho `0` sai khi mọi số đều âm vì 0 không phải identity của `max` trên miền số nguyên đầy đủ. Có thể dùng `Integer.MIN_VALUE` cho `int`, nhưng khi stream rỗng thì sentinel cũng là kết quả; nếu cần phân biệt “không có dữ liệu” với “giá trị MIN_VALUE”, `Optional` diễn đạt đúng hơn.

### 10.4. Lỗi trong accumulator không biến thành empty

Nếu accumulator ném ngoại lệ (như lỗi parse hoặc validation), `reduce` không tự thay bằng identity và tiếp tục. Terminal thường kết thúc bằng lỗi được ném ra. Vì vậy identity không phải cơ chế **xử lý lỗi hoặc fallback**; nó là phần tử trung hòa của toán tử tổng hợp.

## 11. Chương trình Java 17+ hoàn chỉnh, stdout xác định

Tạo tệp **`ReduceIdentityDemo.java`**:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.stream.IntStream;
import java.util.stream.Stream;
import java.util.stream.Collectors;

public class ReduceIdentityDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4);

        int sum = numbers.stream()
                .reduce(0, Integer::sum);
        int product = numbers.stream()
                .reduce(1, (a, b) -> a * b);
        System.out.println("sum=" + sum);
        System.out.println("product=" + product);

        int emptySum = Stream.<Integer>empty()
                .reduce(0, Integer::sum);
        int emptyProduct = Stream.<Integer>empty()
                .reduce(1, (a, b) -> a * b);
        System.out.println("emptySum=" + emptySum);
        System.out.println("emptyProduct=" + emptyProduct);

        Optional<Integer> emptyWithoutIdentity =
                Stream.<Integer>empty().reduce(Integer::sum);
        System.out.println("emptyOptional="
                + emptyWithoutIdentity.isEmpty());

        int withOffsetSequential = numbers.stream()
                .reduce(10, Integer::sum);
        int correctOffsetParallel = 10 + numbers.parallelStream()
                .reduce(0, Integer::sum);
        System.out.println("offsetSequential=" + withOffsetSequential);
        System.out.println("offsetParallelCorrect=" + correctOffsetParallel);

        String joined = Stream.of("A", "B", "C")
                .reduce("", String::concat);
        System.out.println("joined=" + joined);

        int totalLength = Stream.of("Java", "API", "Stream")
                .reduce(
                        0,
                        (current, word) -> current + word.length(),
                        Integer::sum);
        System.out.println("totalLength=" + totalLength);

        long longWords = Stream.of("a", "java", "stream", "io")
                .parallel()
                .reduce(
                        0L,
                        (count, word) ->
                                count + (word.length() >= 4 ? 1L : 0L),
                        Long::sum);
        System.out.println("longWords=" + longWords);

        int parallelSum = IntStream.rangeClosed(1, 100)
                .parallel()
                .reduce(0, Integer::sum);
        System.out.println("parallelSum=" + parallelSum);

        OptionalInt max = IntStream.of(-7, -3, -9)
                .reduce(Integer::max);
        System.out.println("max=" + max.orElseThrow());

        String collected = Stream.of("A", "B", "C")
                .collect(Collectors.joining(","));
        System.out.println("collected=" + collected);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ReduceIdentityDemo.java
java ReduceIdentityDemo
~~~

**Stdout:**

~~~text
sum=10
product=24
emptySum=0
emptyProduct=1
emptyOptional=true
offsetSequential=20
offsetParallelCorrect=20
joined=ABC
totalLength=13
longWords=2
parallelSum=5050
max=-3
collected=A,B,C
~~~

Giải thích:

1. `sum=10` vì `0+1+2+3+4=10`; `product=24` vì `1×1×2×3×4=24`.
2. Hai stream rỗng trả về lần lượt identity `0` và `1`, không có accumulator nào cần áp dụng cho phần tử nguồn.
3. Overload không identity trên stream rỗng cho `Optional.empty()`.
4. `offsetSequential=20` chỉ minh họa kết quả quan sát khi chạy **tuần tự** với “khởi đầu 10”; đó không phải identity hợp lệ cho phép cộng. `offsetParallelCorrect=20` dùng tổng với identity 0, rồi cộng khoản 10 đúng một lần bên ngoài.
5. `joined=ABC` vì chuỗi rỗng là đơn vị của phép nối chuỗi.
6. `totalLength=13` vì `"Java"` dài 4, `"API"` dài 3 và `"Stream"` dài 6.
7. `longWords=2` đếm `"java"` và `"stream"`, sử dụng accumulator/combiner tương thích trên parallel stream.
8. `parallelSum=5050` với phép cộng có identity và tính kết hợp đúng.
9. `max=-3` dùng overload trả `OptionalInt`, không cần chọn sentinel.
10. `collected=A,B,C` minh họa collector thích hợp khi cần dựng chuỗi có dấu ngăn cách.

Ví dụ được thiết kế để stdout không phụ thuộc thứ tự scheduling của parallel stream. Chúng chỉ tổng hợp bằng các hàm thỏa điều kiện kết hợp và identity, không in từng callback từ các worker song song.

## 12. Những lỗi phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Dùng `reduce(1, Integer::sum)` để cộng | `1` không phải identity cộng | Dùng `0` |
| Dùng `reduce(0, (a,b)->a*b)` để nhân | `0` hấp thụ mọi số | Dùng `1` |
| Muốn cộng phí 10 đúng một lần nên dùng `reduce(10, sum)` | Parallel có thể áp identity cho nhiều nhánh | `10 + stream.reduce(0, sum)` |
| Dùng phép trừ trong `reduce` rồi parallel | Trừ không kết hợp, 0 không trung hòa hai phía | Chọn phép gộp kết hợp và identity đúng |
| Dùng `reduce(0, Integer::max)` cho số âm | Identity 0 không trung hòa với max trên số âm | Dùng `max()`/`reduce(Integer::max)` trả Optional |
| Nghĩ `reduce(identity, op)` trả Optional | Overload có identity trả `T` trực tiếp | Xem đúng chữ ký |
| Nghĩ stream rỗng trả null | Dạng có identity trả identity | Thiết kế identity rõ ràng |
| Dùng mutable identity rồi append/add | Mutation và chia sẻ trạng thái phá hợp đồng reduce | Dùng `collect` |
| Dùng `reduce` để ghép chuỗi với dấu phẩy bằng cách thêm dấu vào mọi phần tử | Có thể sai khi chia nhánh và ghép lại | Dùng `Collectors.joining(",")` |
| Dùng phép cộng `double` và đòi kết quả bitwise giống nhau ở mọi cách gộp | Double có sai số làm tròn, không kết hợp tuyệt đối | Chọn thuật toán/độ chính xác phù hợp |
| Tưởng identity là bộ xử lý lỗi hoặc giá trị fallback | Identity chỉ trung hòa phép gộp | Xử lý lỗi riêng, dùng Optional khi cần |
| Tự sửa collection nguồn trong accumulator | Vi phạm non-interference và rủi ro song song | Giữ phép gộp không có side effect |

## 13. Bài tập và lời giải

**Câu 1.** Identity của phép cộng `Integer::sum` là gì? Nếu stream rỗng, `Stream.<Integer>empty().reduce(0, Integer::sum)` trả gì?

**Lời giải:** Identity là `0`. Stream rỗng trả `0`.

**Câu 2.** Vì sao `1` là identity cho phép nhân nhưng `0` không phải?

**Lời giải:** `1*x = x*1 = x`, trong khi `0*x=0`. `0` là phần tử hấp thụ đối với nhân.

**Câu 3.** `Stream.of(2,3,4).reduce(10, Integer::sum)` chạy tuần tự cho số mấy? Có nên dùng biểu thức ấy trong parallel nếu muốn cộng 10 một lần?

**Lời giải:** Tuần tự cho `19`. Không nên: `10` không là identity của phép cộng, và song song có thể khởi tạo nhiều nhánh bằng 10. Dùng `10 + Stream.of(2,3,4).parallel().reduce(0,Integer::sum)`.

**Câu 4.** Muốn tính tổng độ dài các chuỗi bằng dạng `reduce` ba tham số, kiểu `T` và `U` tương ứng là gì?

**Lời giải:** `T=String`, `U=Integer`. Identity là `0`, accumulator là `(sum,s)->sum+s.length()`, combiner là `Integer::sum`.

**Câu 5.** Vì sao accumulator ba tham số cần tương thích với combiner?

**Lời giải:** Để kết quả rút gọn từng nhánh rồi gộp tương đương với tích lũy trực tiếp. Quy tắc: `combiner(u, accumulator(identity,t)) == accumulator(u,t)` theo tương đương giá trị của phép toán.

**Câu 6.** Với nguồn `[-7,-3,-9]`, `reduce(0,Integer::max)` cho giá trị gì và sai ở đâu?

**Lời giải:** Kết quả là `0`, nhưng max thực tế là `-3`. Identity 0 không trung hòa với phép max trên các số âm. Dùng `stream.max()` hoặc overload `reduce(Integer::max)`.

**Câu 7.** Với nguồn rỗng, dạng `reduce(BinaryOperator)` và `reduce(identity, BinaryOperator)` khác gì?

**Lời giải:** Dạng không identity trả Optional rỗng. Dạng có identity trả chính giá trị identity đã cung cấp.

**Câu 8.** Muốn ghép chuỗi với dấu ngăn cách và hỗ trợ parallel stream, có nên dùng `reduce(new StringBuilder(), StringBuilder::append, ...)`?

**Lời giải:** Không. Mutation lên một identity mutable vi phạm hợp đồng sử dụng reduction an toàn. Dùng `Collectors.joining(delimiter)`, hoặc `collect` với collector thích hợp.

## 14. Ghi nhớ

**Phần tử đơn vị không chỉ là “giá trị bắt đầu”**. Nó phải thỏa luật trung hòa với phép gộp: `e ⊕ x = x ⊕ e = x`. Cùng với **tính kết hợp** của accumulator, điều kiện đó cho phép `reduce(identity, accumulator)` trả kết quả đúng khi stream rỗng và khi pipeline có thể chia/gộp để chạy song song.

- `reduce(T identity, BinaryOperator<T>)` trả trực tiếp `T`, stream rỗng trả identity.
- `reduce(U identity, BiFunction<U,T,U>, BinaryOperator<U>)` cho phép nguồn `T` và kết quả `U` khác nhau, đồng thời yêu cầu accumulator tương thích với combiner.
- Đừng đưa khoản cộng thêm nghiệp vụ vào identity nếu nó không trung hòa với phép toán; hãy áp dụng khoản đó **sau reduction**.
- Không lấy đối tượng mutable làm identity rồi sửa nó trong accumulator; dùng `collect` cho mutable reduction.
- Khi không có identity thích hợp hoặc cần phân biệt trường hợp không có dữ liệu, dùng overload `reduce(BinaryOperator)` trả `Optional` hoặc terminal chuyên biệt.
- Các phép toán số, nhất là floating point, cần cân nhắc overflow, sai số và tính kết hợp.

Hiểu luật đại số của identity giúp viết reduction không chỉ “đúng khi chạy tuần tự”, mà còn đúng về hợp đồng, rõ nghĩa và an toàn hơn khi chuyển sang parallel stream.
