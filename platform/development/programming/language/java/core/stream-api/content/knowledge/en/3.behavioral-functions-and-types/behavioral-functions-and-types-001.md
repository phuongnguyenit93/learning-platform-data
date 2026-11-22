# Dùng Predicate, Function và Consumer trong pipeline

Trong **Java Stream API**, một pipeline thường đọc như một câu mô tả yêu cầu: “lọc đơn hàng đã thanh toán, biến mỗi đơn thành một dòng báo cáo, rồi in kết quả”. Ba bước đó tương ứng với ba *kiểu hàm hành vi* rất quan trọng trong Java: **`Predicate`**, **`Function`** và **`Consumer`**.

Ba kiểu này thuộc gói `java.util.function`, được giới thiệu cùng lập trình hàm trong Java 8. Chúng là các **functional interface**: mỗi giao diện có một phương thức trừu tượng chính, nên ta có thể cung cấp cách thực hiện bằng **lambda** hoặc **method reference**. Nhờ đó, `filter`, `map` và `forEach` nhận *hành vi cần áp dụng* thay vì bắt người viết tự điều khiển vòng lặp.

Bài này thuộc chương **Hàm hành vi và kiểu dữ liệu** của module **JAVA_STREAM_API**. Mục tiêu là hiểu đúng hợp đồng đầu vào/đầu ra của ba kiểu hàm, phối hợp chúng trong pipeline lazy và tránh lỗi do tác dụng phụ, trạng thái chia sẻ hoặc giả định sai về thứ tự thực thi. Đây cũng là nền tảng để học `reduce`, `collect`, grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers ở các phần tiếp theo.

## 1. Nhìn nhanh: ba kiểu hàm khác nhau ở đâu?

| Functional interface | Phương thức chính | Nhận vào | Trả về | Vai trò tiêu biểu trong Stream |
|---|---|---|---|---|
| `Predicate<T>` | `boolean test(T value)` | Một phần tử kiểu `T` | `boolean` | Chọn phần tử bằng `filter`; kiểm tra bằng `anyMatch`, `allMatch`, `noneMatch` |
| `Function<T, R>` | `R apply(T value)` | Một phần tử kiểu `T` | Giá trị kiểu `R` | Chuyển đổi phần tử bằng `map`; làm khóa grouping; ánh xạ giá trị khi collect |
| `Consumer<T>` | `void accept(T value)` | Một phần tử kiểu `T` | Không trả giá trị | Thực hiện tác động cuối bằng `forEach`, `forEachOrdered`, `Optional.ifPresent` |

Ví dụ với một đơn hàng:

- **Predicate:** “Đơn này đã thanh toán chưa?” → `true` hoặc `false`.
- **Function:** “Biến đơn này thành chuỗi hiển thị thế nào?” → `String`.
- **Consumer:** “In chuỗi hiển thị này ra đâu?” → không có giá trị trả về.

Chú ý chữ cái kiểu:

- `T` trong `Predicate<T>` và `Consumer<T>` là **kiểu phần tử được nhận**.
- `T` trong `Function<T, R>` là **kiểu đầu vào**, còn `R` là **kiểu kết quả**. Hai kiểu này có thể giống hoặc khác nhau.
- `Consumer` không giống `Function<T, Void>`: phương thức `accept` có kiểu trả về `void` thật sự, nên lambda Consumer không cần và không được trả về một giá trị.

~~~mermaid
flowchart LR
    A["Stream<Order>"] --> B["filter(Predicate<Order>)"]
    B --> C["map(Function<Order, String>)"]
    C --> D["Stream<String>"]
    D --> E["forEach(Consumer<String>)"]
    E --> F["Hiệu ứng: in báo cáo"]
~~~

`filter` và `map` là **phép toán trung gian (intermediate operation)**, còn `forEach` là **phép toán kết thúc (terminal operation)**. Phân biệt này quyết định thời điểm lambda được chạy.

## 2. Ví dụ đầy đủ: chọn đơn hàng và xuất báo cáo

Giả sử có danh sách đơn hàng. Ta muốn lấy những đơn **đã thanh toán và có giá trị từ 100.000 đồng**, biến chúng thành các dòng báo cáo và in từng dòng.

Ví dụ hoàn chỉnh sau dùng **JDK 17 trở lên** vì có `record`, `List.of` và `Stream.toList()`:

~~~java
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;

public class BehavioralFunctionsDemo {
    record Order(String id, String customer, long amountVnd, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("DH01", "An",   120_000, true),
            new Order("DH02", "Bình",  190_000, false),
            new Order("DH03", "Chi",   150_000, true),
            new Order("DH04", "An",    70_000, true)
        );

        // Predicate<Order>: quyết định giữ lại đơn nào.
        Predicate<Order> isPaid = Order::paid;
        Predicate<Order> isHighValue = order -> order.amountVnd() >= 100_000;

        // Function<Order, String>: chuyển đơn thành dòng báo cáo.
        Function<Order, String> toReportLine = order ->
            order.id() + " | " + order.customer() + " | " + order.amountVnd();

        // Consumer<String>: sử dụng kết quả, không trả giá trị.
        Consumer<String> printLine = System.out::println;

        List<String> report = orders.stream()
            .filter(isPaid.and(isHighValue))
            .map(toReportLine)
            .toList();

        report.forEach(printLine);
    }
}
~~~

Kết quả:

~~~text
DH01 | An | 120000
DH03 | Chi | 150000
~~~

Đọc pipeline theo thứ tự:

1. `orders.stream()` tạo nguồn `Stream<Order>` từ danh sách.
2. `filter(isPaid.and(isHighValue))` nhận một `Predicate<Order>` đã kết hợp hai điều kiện, giữ lại `DH01` và `DH03`.
3. `map(toReportLine)` nhận `Function<Order, String>`, chuyển `Stream<Order>` thành `Stream<String>`.
4. `toList()` là phép toán kết thúc, thực sự tính toán và tạo ra danh sách chuỗi.
5. `report.forEach(printLine)` là lời gọi trên **`List` kết quả** để in từng dòng. Nó sử dụng `Consumer<String>` nhưng không còn thuộc Stream đầu tiên.

Có thể viết tất cả thành một pipeline Stream trực tiếp:

~~~java
orders.stream()
    .filter(isPaid.and(isHighValue))
    .map(toReportLine)
    .forEach(printLine);
~~~

Khi đó chính `forEach` kết thúc pipeline. Hai cách mang mục đích khác nhau: **`toList`** phù hợp khi cần lưu và dùng tiếp kết quả; **`forEach`** phù hợp khi cần thực hiện một tác động cuối cùng. Để tính tổng, đếm, nhóm hoặc tạo báo cáo có cấu trúc, thường nên chọn phép toán kết thúc như `sum`, `count` hoặc `collect` thay vì tự thêm phần tử vào collection ngoài bằng `forEach`.

## 3. Predicate<T>: biểu diễn quy tắc đúng/sai

`Predicate<T>` có một phương thức trừu tượng:

~~~java
@FunctionalInterface
public interface Predicate<T> {
    boolean test(T value);
    // Các phương thức mặc định như and, or, negate; phương thức tĩnh như not.
}
~~~

Đây là dạng rút gọn để hiểu hợp đồng, không phải bản chép đầy đủ mã nguồn JDK. Phần quan trọng là một Predicate **nhận một giá trị và trả kết quả logic**.

### 3.1. Tạo và gọi Predicate

~~~java
import java.util.function.Predicate;

Predicate<String> notEmpty = text -> !text.isEmpty();
Predicate<String> startsWithJ = text -> text.startsWith("J");

System.out.println(notEmpty.test("Java"));    // true
System.out.println(notEmpty.test(""));        // false
System.out.println(startsWithJ.test("Kotlin")); // false
~~~

`test` có thể gọi trực tiếp, nhưng trong Stream ta thường **truyền Predicate vào `filter`**:

~~~java
List<String> names = List.of("Java", "", "Kotlin", "JavaScript");

List<String> validNames = names.stream()
    .filter(notEmpty)
    .toList(); // [Java, Kotlin, JavaScript]
~~~

`filter` có hành vi: với mỗi phần tử, nếu `predicate.test(element)` là `true` thì giữ, ngược lại bỏ. **Kiểu phần tử không đổi** sau `filter`: đầu vào `Stream<String>` thì đầu ra vẫn là `Stream<String>`.

### 3.2. Ghép quy tắc với and, or, negate

Thay vì nhồi nhiều điều kiện vào một lambda dài, có thể đặt tên từng quy tắc:

~~~java
Predicate<String> hasText = text -> !text.isBlank();
Predicate<String> startsWithJ = text -> text.startsWith("J");

Predicate<String> both = hasText.and(startsWithJ);
Predicate<String> either = hasText.or(startsWithJ);
Predicate<String> doesNotStartWithJ = startsWithJ.negate();

System.out.println(both.test("Java"));     // true
System.out.println(both.test("Kotlin"));   // false
System.out.println(either.test("Kotlin")); // true
System.out.println(doesNotStartWithJ.test("Go")); // true
~~~

- `a.and(b)` chỉ đúng khi cả hai điều kiện đều đúng.
- `a.or(b)` đúng khi ít nhất một điều kiện đúng.
- `a.negate()` đảo kết quả.
- `and` và `or` **dừng đánh giá sớm (short-circuit)**: `and` bỏ qua `b` nếu `a` sai; `or` bỏ qua `b` nếu `a` đúng.

`String.isBlank()` cần JDK 11+. Ngoài ra, từ JDK 11 có thể viết `Predicate.not(String::isBlank)` khi cần biểu diễn phủ định của method reference. Với Java 8, có thể dùng `s -> !s.trim().isEmpty()` nếu quy tắc khoảng trắng đó phù hợp.

**Chú ý:** việc `Predicate.and` dừng đánh giá sớm là **ở cấp độ biểu thức điều kiện cho một phần tử**. Nó khác với phép toán Stream như `findFirst` hoặc `anyMatch` có thể **dừng duyệt toàn bộ nguồn** khi đủ thông tin.

### 3.3. Predicate còn dùng ở phép toán kết thúc

~~~java
List<Integer> scores = List.of(6, 8, 9, 3);

Predicate<Integer> passing = score -> score >= 5;

boolean anyPass = scores.stream().anyMatch(passing);    // true
boolean allPass = scores.stream().allMatch(passing);    // false
boolean nonePass = scores.stream().noneMatch(passing);  // false
~~~

`anyMatch`, `allMatch` và `noneMatch` đều là **terminal operation**, có thể dừng sớm khi xác định được kết quả. Đối với Stream rỗng, `allMatch` và `noneMatch` trả `true` theo định nghĩa logic; đừng nhầm điều đó với việc đã có phần tử đạt điều kiện.

## 4. Function<T, R>: ánh xạ một giá trị sang giá trị khác

`Function<T, R>` có phương thức:

~~~java
@FunctionalInterface
public interface Function<T, R> {
    R apply(T value);
    // Các phương thức mặc định compose, andThen; phương thức tĩnh identity.
}
~~~

Nó trả về **một kết quả** cho mỗi lần gọi. Kết quả có thể cùng kiểu đầu vào hoặc một kiểu khác hoàn toàn.

~~~java
import java.util.function.Function;

Function<String, Integer> length = String::length;
System.out.println(length.apply("Stream")); // 6

Function<Integer, String> display = number -> "Giá trị: " + number;
System.out.println(display.apply(12)); // Giá trị: 12
~~~

### 4.1. Function đi cùng map

~~~java
List<String> names = List.of("An", "Bình", "Chi");

Function<String, Integer> toLength = String::length;

List<Integer> lengths = names.stream()
    .map(toLength)
    .toList(); // [2, 4, 3]
~~~

`map` nhận một `Function<? super T, ? extends R>` và tạo `Stream<R>`. Nó **thay đổi giá trị và có thể thay đổi kiểu phần tử**: `Stream<String>` chuyển thành `Stream<Integer>` trong ví dụ. Một phần tử đầu vào thông thường tương ứng một phần tử đầu ra; nếu muốn chuyển một phần tử thành nhiều phần tử thì tìm hiểu `flatMap`, vốn nhận hàm trả về một Stream.

`map` không có nghĩa là lọc; giá trị trả về từ Function **không được hiểu như điều kiện đúng/sai**. Nếu cần bỏ phần tử, hãy dùng `filter`.

### 4.2. Phối hợp Function bằng andThen và compose

Đôi khi cần chuẩn hóa chuỗi qua nhiều bước:

~~~java
import java.util.Locale;
import java.util.function.Function;

Function<String, String> trim = String::trim;
Function<String, String> uppercase = text -> text.toUpperCase(Locale.ROOT);

Function<String, String> normalizeA = trim.andThen(uppercase);
Function<String, String> normalizeB = uppercase.compose(trim);

System.out.println(normalizeA.apply(" java ")); // JAVA
System.out.println(normalizeB.apply(" java ")); // JAVA
~~~

- `f.andThen(g)` thực hiện **`f` rồi đến `g`**, tức `g(f(x))`.
- `g.compose(f)` thực hiện **`f` rồi đến `g`**, cũng là `g(f(x))`.

Thứ tự rất quan trọng nếu hai phép biến đổi không giao hoán. Ví dụ “cắt khoảng trắng rồi lấy độ dài” có thể cho kết quả khác “lấy độ dài rồi tính tiếp”.

Có thể truyền hàm đã ghép vào `map`:

~~~java
List<String> normalized = List.of(" java ", " Kotlin ", "go").stream()
    .map(normalizeA)
    .toList(); // [JAVA, KOTLIN, GO]
~~~

Ngoài ra, `Function.identity()` là hàm trả lại nguyên giá trị đầu vào. Nó đặc biệt hữu ích trong các collector, chẳng hạn khi muốn dùng chính phần tử làm giá trị trong một `Map`.

### 4.3. Ánh xạ ra số nguyên thủy

Với phép tổng hợp số lượng hoặc số tiền, dùng `mapToInt`, `mapToLong` hoặc `mapToDouble` để nhận Stream nguyên thủy:

~~~java
import java.util.List;
import java.util.function.ToIntFunction;

List<String> names = List.of("Java", "Go", "Kotlin");
ToIntFunction<String> length = String::length;

int totalCharacters = names.stream()
    .mapToInt(length)
    .sum(); // 12
~~~

`ToIntFunction<T>` có phương thức `int applyAsInt(T value)`. Nó là biến thể chuyên biệt của họ Function, tránh boxing qua `Integer` trong đường xử lý số. Tương tự có `ToLongFunction`, `ToDoubleFunction`, cùng với `IntFunction<R>` để nhận một `int` làm đầu vào.

Khi đọc các API `Collectors.groupingBy(classifier)` hoặc `Collectors.toMap(keyMapper, valueMapper)`, bạn cũng sẽ gặp Function: chúng quyết định **khóa nhóm**, **khóa của Map** hoặc **giá trị được thu thập**, chứ không chỉ dùng cho `map`.

## 5. Consumer<T>: nhận giá trị và thực hiện một tác động

`Consumer<T>` có phương thức:

~~~java
@FunctionalInterface
public interface Consumer<T> {
    void accept(T value);
    // Phương thức mặc định andThen.
}
~~~

Consumer dành cho hành động như in log, ghi kết quả ra đầu ra, gửi dữ liệu tới một bộ phận nhận hoặc cập nhật giao diện. **Nó không trả về kết quả để đưa tiếp vào pipeline**.

~~~java
import java.util.function.Consumer;

Consumer<String> print = System.out::println;
print.accept("Xin chào Stream API"); // In một dòng
~~~

### 5.1. forEach và forEachOrdered

~~~java
List<String> names = List.of("An", "Bình", "Chi");
Consumer<String> print = name -> System.out.println("Tên: " + name);

names.stream().forEach(print);
~~~

`forEach` là terminal operation. Đối với Stream chạy **tuần tự** từ `List` như ví dụ, các dòng được in theo thứ tự duyệt. Với **parallel Stream**, `forEach` không đảm bảo thứ tự xuất ra, kể cả nguồn có encounter order. Nếu buộc phải giữ encounter order của nguồn, dùng `forEachOrdered`:

~~~java
names.parallelStream()
    .forEachOrdered(print);
~~~

Điều này giữ thứ tự đối với nguồn có thứ tự nhưng có thể làm giảm lợi ích chạy song song. Nếu công việc có thể hoàn thành bằng phép tổng hợp thuần túy, thường nên thu kết quả trước bằng `collect` hoặc `toList` và chỉ thực hiện I/O ở bước cuối.

### 5.2. Ghép Consumer bằng andThen

~~~java
Consumer<String> announce = name -> System.out.println("Tên: " + name);
Consumer<String> separator = name -> System.out.println("---");

Consumer<String> printWithSeparator = announce.andThen(separator);
printWithSeparator.accept("An");
~~~

Kết quả:

~~~text
Tên: An
---
~~~

`first.andThen(second)` chạy Consumer thứ nhất rồi đến thứ hai **cho cùng một giá trị**. Nếu hành động đầu ném ngoại lệ, hành động tiếp theo sẽ không chạy. Khác với `Function.andThen`, nó **không tạo ra giá trị mới**.

Ngoài Stream, `Optional.ifPresent(consumer)` cũng nhận Consumer để xử lý giá trị khi có mặt:

~~~java
java.util.Optional.of("Java")
    .ifPresent(System.out::println); // Java
~~~

### 5.3. Tại sao không dùng Consumer để tự gom danh sách?

Đoạn sau có vẻ hợp lý nhưng đưa **trạng thái thay đổi bên ngoài pipeline** vào luồng xử lý:

~~~java
List<String> collected = new java.util.ArrayList<>();

names.stream()
    .map(String::toUpperCase)
    .forEach(collected::add); // Không nên dùng để thu thập kết quả.
~~~

Trong pipeline tuần tự đơn giản, đoạn này có thể chạy đúng. Nhưng ở Stream song song, `ArrayList` không bảo đảm an toàn luồng; thêm phần tử đồng thời có thể làm mất dữ liệu hoặc gây lỗi. Thay bằng:

~~~java
List<String> collected = names.stream()
    .map(String::toUpperCase)
    .toList();
~~~

`toList` tạo danh sách kết quả không thể sửa từ JDK 16. Nếu cần Java 8, có thể dùng `collect(Collectors.toList())`, lưu ý API không bảo đảm danh sách thu được có thể chỉnh sửa. Nếu thật sự cần danh sách thay đổi được, chỉ rõ nhà cung cấp: `collect(Collectors.toCollection(ArrayList::new))`.

**Quy tắc thực hành:** Consumer hữu ích cho *tác động ở ranh giới chương trình* (in ra màn hình, ghi I/O có kiểm soát). Khi muốn tạo giá trị, hãy ưu tiên Function và phép toán kết thúc sinh kết quả.

## 6. Lambda, method reference và kiểu đích

Các functional interface định nghĩa **hợp đồng kiểu**; lambda hoặc method reference là các cách **cung cấp hành vi** phù hợp với hợp đồng đó.

| Viết bằng lambda | Viết bằng method reference | Kiểu đích |
|---|---|---|
| `order -> order.paid()` | `Order::paid` | `Predicate<Order>` |
| `order -> order.customer()` | `Order::customer` | `Function<Order, String>` |
| `text -> text.length()` | `String::length` | `Function<String, Integer>` |
| `text -> System.out.println(text)` | `System.out::println` | `Consumer<String>` |

Một lời gọi phương thức có thể được dùng với các interface khác nhau **nếu kiểu tham số và kiểu trả về tương thích**. Trình biên dịch dựa vào *target type* của biến hoặc tham số phương thức để hiểu lambda.

~~~java
Predicate<String> isLong = text -> text.length() >= 5;
Function<String, Integer> length = String::length;
Consumer<Integer> printLength = System.out::println;

Stream.of("Java", "Kotlin")
    .filter(isLong)
    .map(length)
    .forEach(printLength); // In 6
~~~

Trong ví dụ, `Predicate` loại `Java` (4 ký tự), `Function` biến `Kotlin` thành số 6, `Consumer` in 6. Nếu lỡ gán `String::length` vào `Predicate<String>`, trình biên dịch sẽ báo lỗi vì `length()` trả về `int`, không phải `boolean`.

Lambda còn có thể *capture* biến ở phạm vi ngoài, nhưng biến cục bộ được capture phải là **final hoặc effectively final** (không bị gán lại):

~~~java
int minimumLength = 4;
Predicate<String> longEnough = value -> value.length() >= minimumLength;

// minimumLength = 6; // Nếu bỏ comment, lambda trên sẽ không biên dịch.
~~~

Quy tắc này hạn chế một số lỗi trạng thái, nhưng không biến mọi đối tượng được capture thành bất biến. Ví dụ capture một `ArrayList` rồi thêm phần tử từ nhiều luồng vẫn có rủi ro race condition.

## 7. Lazy pipeline: khi nào ba hàm thực sự được gọi?

Việc tạo một pipeline với `filter` và `map` **chưa nhất thiết gọi** `Predicate.test` hay `Function.apply`. Phần lớn phép toán trung gian của Stream là *lazy*. Công việc được thực hiện khi có terminal operation, và Stream có thể chỉ xử lý số phần tử cần thiết.

~~~java
import java.util.stream.Stream;

Stream<Integer> pipeline = Stream.of(-1, 2, 3)
    .filter(n -> {
        System.out.println("test " + n);
        return n > 0;
    })
    .map(n -> {
        System.out.println("apply " + n);
        return n * 2;
    });

System.out.println("Pipeline đã được tạo");

pipeline.forEach(n -> System.out.println("accept " + n));
~~~

Kết quả của pipeline tuần tự này:

~~~text
Pipeline đã được tạo
test -1
test 2
apply 2
accept 4
test 3
apply 3
accept 6
~~~

Lưu ý **mỗi phần tử** có thể đi qua nhiều bước trước khi phần tử kế tiếp được xử lý; Stream không nhất thiết chạy toàn bộ `filter` rồi toàn bộ `map` như hai vòng lặp riêng biệt. Chỉ có dòng “Pipeline đã được tạo” xuất hiện trước khi terminal operation chạy.

Tuy nhiên, **không được dựa vào số lần gọi hoặc thứ tự gọi lambda để làm nghiệp vụ**. Với các phép toán có trạng thái như `sorted`, với Stream song song, với phép toán dừng sớm như `findFirst` hoặc khi JDK có thể tối ưu bỏ qua bước không cần thiết, cách đánh giá có thể khác.

Ví dụ sau minh họa một giả định sai:

~~~java
long count = List.of("A", "B", "C").stream()
    .map(text -> {
        System.out.println("map: " + text);
        return text.toLowerCase();
    })
    .count();

System.out.println(count); // 3
~~~

Đừng dự đoán rằng ba dòng `map: ...` luôn xuất hiện. Với nguồn đã biết kích thước và pipeline không thay đổi số phần tử, triển khai có thể tính `count` mà **không cần gọi mapper**. `map` nên mô tả phép biến đổi giá trị, không nên được dùng làm nơi bắt buộc phát sinh log, ghi dữ liệu hoặc thay đổi trạng thái.

Sau khi `forEach`, `count` hoặc `toList` kết thúc, Stream đã được tiêu thụ; muốn xử lý lại dữ liệu, hãy tạo Stream **mới từ nguồn** nếu nguồn đó hỗ trợ duyệt lại.

## 8. Quy tắc thiết kế Predicate và Function an toàn

Các hàm cung cấp cho pipeline nên đáp ứng hai nguyên tắc chính:

1. **Non-interfering:** không sửa nguồn dữ liệu đang được duyệt.
2. **Stateless:** kết quả xử lý một phần tử không phụ thuộc vào trạng thái ngoài đang thay đổi trong khi duyệt.

Ví dụ không nên viết:

~~~java
List<Integer> values = new java.util.ArrayList<>(List.of(1, 2, 3));

// Không được sửa nguồn trong lúc duyệt bằng Stream.
values.stream().filter(n -> {
    values.remove(n);
    return n > 1;
}).toList();
~~~

Thao tác sửa nguồn có thể dẫn đến `ConcurrentModificationException`, bỏ sót phần tử hoặc hành vi khó đoán tùy nguồn và cách xử lý. Nếu muốn lọc để lấy danh sách mới:

~~~java
List<Integer> remaining = values.stream()
    .filter(n -> n > 1)
    .toList();
~~~

Nếu muốn cập nhật chính collection, hãy sử dụng thao tác phù hợp như `values.removeIf(n -> n <= 1)` ở ngoài một pipeline đang duyệt cùng collection.

Một Predicate tốt kiểm tra cùng đầu vào thường cho cùng kết quả khi điều kiện nghiệp vụ không đổi. Một Function tốt chuyển đổi dựa trên đầu vào và không thực hiện hiệu ứng ngoài ý muốn. Điều này làm việc tái sử dụng trong `parallelStream()` an toàn hơn, nhưng chạy song song vẫn phải đánh giá thêm chi phí chia việc, kết hợp, thứ tự và tài nguyên.

### Xử lý null và ngoại lệ

- `List.of(...)` không chấp nhận phần tử `null`, nhưng nguồn Stream khác có thể chứa `null`. Predicate kiểu `text -> text.isBlank()` sẽ ném `NullPointerException` nếu `text` là null.
- Nếu nguồn có thể chứa null, đặt điều kiện rõ ràng trước khi ánh xạ:

~~~java
List<String> result = java.util.Arrays.asList("Java", null, "Go").stream()
    .filter(java.util.Objects::nonNull)
    .map(String::toUpperCase)
    .toList(); // [JAVA, GO]
~~~

- Các phương thức chính `test`, `apply` và `accept` không khai báo checked exception. Nếu lời gọi bên trong lambda có checked exception, cần xử lý theo chính sách ứng dụng (xử lý tại chỗ, chuyển đổi ngoại lệ có ngữ cảnh hoặc tách phần I/O ra khỏi pipeline). Không nên “nuốt” lỗi bằng cách âm thầm trả giá trị thay thế không hợp lệ.
- `map` có thể trả `null` nhưng một số thao tác cuối, ví dụ `findFirst` khi chọn trúng null, sẽ ném lỗi. Hãy xác định quy tắc null trước khi xây pipeline.

## 9. Chọn đúng kiểu hàm trong những tình huống thường gặp

| Nhiệm vụ | Chọn | Vì sao |
|---|---|---|
| Chỉ giữ tài khoản đang hoạt động | `Predicate<Account>` + `filter` | Trả về đúng/sai; không đổi kiểu phần tử |
| Chuyển `Account` thành email | `Function<Account, String>` + `map` | Trả một giá trị mới; có thể đổi kiểu |
| Tính tổng số ký tự từ danh sách chuỗi | `ToIntFunction<String>` + `mapToInt` + `sum` | Xử lý kiểu `int` trực tiếp |
| Kiểm tra xem có đơn quá hạn | `Predicate<Order>` + `anyMatch` | Kết quả logic và có thể dừng sớm |
| Nhóm hóa đơn theo khách hàng | `Function<Order, String>` + `groupingBy` | Tính khóa nhóm từ mỗi phần tử |
| In từng kết quả đã xử lý | `Consumer<String>` + `forEach` | Tạo tác động, không trả về giá trị |
| Tạo `List` từ các phần tử được biến đổi | `map` + `toList` hoặc `collect` | Thu thập giá trị thông qua terminal operation |

Các kiểu hàm rất dễ nhầm khi tên biến không rõ ý. Nên đặt tên thể hiện mục đích: `isPaid`, `hasValidEmail` cho Predicate; `toSummary`, `extractId` cho Function; `printLine`, `sendNotification` cho Consumer. Nếu lambda dài, có nhiều nhánh và khó đặt tên, cân nhắc chuyển nó thành một phương thức có tên rồi dùng method reference.

## 10. Bài tập thực hành kèm lời giải

Cho danh sách mã sản phẩm:

~~~java
List<String> rawCodes = List.of(" java ", "", "KOTLIN", " go ", "Java");
~~~

**Yêu cầu:**

1. Bỏ các mã rỗng hoặc toàn dấu cách.
2. Chuẩn hóa mã bằng cách cắt khoảng trắng và chuyển sang chữ hoa.
3. Loại bỏ mã trùng.
4. Sắp xếp theo thứ tự tự nhiên và in từng mã theo mẫu `Mã: ...`.
5. Đặt tên riêng cho mỗi Predicate, Function và Consumer.

**Lời giải tham khảo (JDK 17+):**

~~~java
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;

public class BehaviorExercise {
    public static void main(String[] args) {
        List<String> rawCodes = List.of(" java ", "", "KOTLIN", " go ", "Java");

        Predicate<String> hasContent = code -> !code.isBlank();
        Function<String, String> normalize =
            code -> code.trim().toUpperCase(Locale.ROOT);
        Consumer<String> printCode =
            code -> System.out.println("Mã: " + code);

        List<String> normalizedCodes = rawCodes.stream()
            .filter(hasContent)
            .map(normalize)
            .distinct()
            .sorted()
            .toList();

        normalizedCodes.forEach(printCode);
    }
}
~~~

Kết quả:

~~~text
Mã: GO
Mã: JAVA
Mã: KOTLIN
~~~

Trong bài này, `hasContent` là `Predicate<String>` vì trả `boolean`; `normalize` là `Function<String, String>` vì trả chuỗi chuẩn hóa; `printCode` là `Consumer<String>` vì chỉ in. `distinct` và `sorted` giúp kết quả không trùng và có thứ tự; `toList` kết thúc Stream để tạo dữ liệu trước khi thực hiện tác động in.

**Câu hỏi tự kiểm tra:**

1. Nếu bỏ `toList()` và viết `...sorted().forEach(printCode)`, pipeline có chạy không? — **Có**, khi đó `forEach` là terminal operation.
2. `filter(hasContent)` có thể đổi `Stream<String>` thành `Stream<Integer>` không? — **Không**; để đổi kiểu dùng `map`.
3. `Function<String, String>` có tự loại bỏ mã trùng không? — **Không**; cần `distinct` hoặc quy tắc xử lý tương đương.
4. Nếu thay `stream()` bằng `parallelStream()` rồi dùng `forEach(printCode)`, thứ tự in có chắc chắn không? — **Không**; cần cân nhắc `forEachOrdered` khi nguồn có thứ tự, và xử lý tác dụng phụ phù hợp.
5. Có nên ghi dữ liệu vào database trong `map` chỉ để kích hoạt việc ghi khi `count` chạy không? — **Không**; mapper có thể không được gọi trong một số pipeline, và hiệu ứng ghi không thuộc hợp đồng biến đổi dữ liệu.

## 11. Ghi nhớ và hướng học tiếp

Hãy đọc ba kiểu hàm theo cách sau:

- **`Predicate<T>`:** *có giữ giá trị này không?* → `test` → `boolean`.
- **`Function<T, R>`:** *biến giá trị này thành gì?* → `apply` → `R`.
- **`Consumer<T>`:** *làm gì với giá trị này?* → `accept` → `void`.

Trong Java Stream API, chúng thường tương ứng với `filter` → `map` → `forEach`, nhưng không bị giới hạn vào ba phương thức này: Predicate còn dùng để match; Function còn dùng để phân nhóm và ánh xạ trong collector; Consumer còn dùng với `Optional` và thao tác nhận dữ liệu khác.

Khi pipeline ngày càng phức tạp, hãy giữ rõ **hợp đồng kiểu**, **điều kiện thực thi lazy**, **đặc tính không can thiệp nguồn**, và **giới hạn của tác dụng phụ**. Nắm được điều này sẽ giúp bạn hiểu các hàm tổng hợp trong `reduce` và `collect`, cũng như những yêu cầu chặt chẽ hơn ở xử lý song song, collector tùy chỉnh, `Spliterator` và Stream Gatherers.
