# Lambda và method reference cho các phép toán Stream

> **Chương:** Hàm hành vi và kiểu dữ liệu  
> **Module:** JAVA_STREAM_API  
> **Trọng tâm:** Viết, đọc và lựa chọn lambda hoặc method reference để truyền hành vi vào các phép toán Stream một cách rõ ràng, đúng kiểu và an toàn.

Java Stream API cho phép mô tả việc xử lý dữ liệu theo kiểu khai báo: **chọn phần tử nào** bằng `filter`, **biến đổi thế nào** bằng `map`, **tổng hợp ra sao** bằng `reduce` hoặc `collect`. Các phép toán ấy cần được cung cấp *hành vi*; trong Java, hành vi thường được biểu diễn bằng **biểu thức lambda** hoặc **method reference** tương ứng với một *functional interface* (giao diện hàm).

Bài này tập trung vào cách viết hành vi, chọn đúng kiểu hàm và hiểu tác động của hành vi đối với pipeline lazy. Đây là nền tảng để học tiếp grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers trong module **JAVA_STREAM_API**, cũng như nhận diện giới hạn về trạng thái, tài nguyên và hiệu năng.

## 1. Vì sao Stream nhận hàm như một tham số?

Giả sử cần lấy tên khách hàng đã thanh toán cho các đơn hàng từ 100.000 đồng trở lên:

```java
import java.util.List;

class LambdaIntro {
    record Order(String customer, long amount, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("An", 150_000, true),
            new Order("Bình", 70_000, true),
            new Order("Chi", 210_000, false),
            new Order("Dung", 180_000, true)
        );

        List<String> customers = orders.stream()
            .filter(order -> order.paid() && order.amount() >= 100_000)
            .map(Order::customer)
            .toList();

        System.out.println(customers); // [An, Dung]
    }
}
```

Một pipeline bao gồm ba vai trò:

1. **Nguồn:** `orders.stream()` cung cấp từng đối tượng `Order`.
2. **Phép toán trung gian:** `filter(...)` cần một hàm trả về `boolean`; `map(...)` cần một hàm biến `Order` thành `String`.
3. **Phép toán kết thúc:** `toList()` yêu cầu đánh giá pipeline để tạo danh sách kết quả.

`order -> order.paid() && order.amount() >= 100_000` là một **lambda**. `Order::customer` là một **method reference**. Chúng là hai cách cung cấp hành vi cho API, không phải hai loại pipeline khác nhau.

Trong `filter(...)`, Java đã biết cần loại hành vi nào: một đối tượng thực hiện giao diện `Predicate<Order>`. Trong `map(...)`, Java cần một hành vi tương thích với `Function<Order, String>`. Kiểu kỳ vọng đó được gọi là **target type**, và nó giải thích tại sao không cần khai báo kiểu tham số `order` trong đa số lambda.

## 2. Lambda expression là gì?

Lambda là một biểu thức đại diện cho việc triển khai phương thức trừu tượng duy nhất của một functional interface.

Cú pháp tổng quát:

```java
(thamSo1, thamSo2) -> bieuThuc

(thamSo1, thamSo2) -> {
    // Một hoặc nhiều câu lệnh
    return ketQua;
}
```

Ví dụ các dạng thường gặp:

```java
Predicate<String> nonBlank = s -> !s.isBlank();
Function<String, Integer> length = s -> s.length();
Consumer<String> printer = s -> System.out.println(s);
BinaryOperator<Integer> add = (a, b) -> a + b;

Predicate<String> longName = (String s) -> {
    String trimmed = s.trim();
    return trimmed.length() >= 3;
};
```

Đoạn ví dụ cần các import tương ứng từ `java.util.function`; `String.isBlank()` có từ Java 11.

| Cách viết | Ý nghĩa |
| --- | --- |
| `s -> s.trim()` | Một tham số, thân là một biểu thức có kết quả. |
| `(s) -> s.trim()` | Tương đương, đặt tham số trong ngoặc. |
| `(String s) -> s.trim()` | Khai báo kiểu tường minh. |
| `(a, b) -> a + b` | Hai tham số. |
| `() -> "default"` | Không có tham số. |
| `s -> { return s.trim(); }` | Thân dạng block, cần `return` khi phương thức đích trả về giá trị. |

**Lưu ý cú pháp:** với lambda nhiều tham số, các tham số phải đặt trong ngoặc. Không trộn tham số khai báo kiểu tường minh với tham số suy luận kiểu trong cùng danh sách, ví dụ `(String s, n) -> ...` là không hợp lệ.

### 2.1. Lambda cần một kiểu đích

Lambda không có kiểu độc lập theo kiểu `String` hay `int`; Java diễn giải nó trong ngữ cảnh một functional interface cụ thể:

```java
Predicate<String> hasText = s -> !s.isBlank();
Function<String, Integer> countChars = s -> s.length();

boolean a = hasText.test("Java");   // true
int b = countChars.apply("Java");   // 4
```

Cùng cú pháp `s -> ...` nhưng phương thức được triển khai khác nhau: `Predicate.test` hoặc `Function.apply`.

Ví dụ sau không biên dịch:

```java
// var operation = value -> value.trim(); // Lỗi: lambda thiếu target type
```

Có thể cung cấp kiểu đích bằng khai báo biến, tham số của phương thức, ép kiểu hoặc lời gọi API thích hợp:

```java
Function<String, String> operation = value -> value.trim();

List<String> cleaned = List.of("  An  ", " Bình ").stream()
    .map(value -> value.trim()) // Target type được suy luận từ map
    .toList();
```

Lambda chỉ triển khai một phương thức trừu tượng theo hợp đồng functional interface; bản thân biểu thức lambda không phải một lời gọi phương thức được thực thi ngay.

## 3. Functional interface: cầu nối giữa lambda và Stream

Một **functional interface** có đúng một phương thức trừu tượng cần triển khai; nó vẫn có thể có phương thức `default`, `static` hoặc các phương thức tương ứng với `Object`. Annotation `@FunctionalInterface` giúp trình biên dịch kiểm tra ràng buộc này.

Các kiểu hay gặp nằm trong `java.util.function`:

| Kiểu | Phương thức trừu tượng | Hình dạng hành vi | Ví dụ sử dụng |
| --- | --- | --- | --- |
| `Predicate<T>` | `boolean test(T t)` | `T → boolean` | `filter`, `anyMatch`, `allMatch` |
| `Function<T,R>` | `R apply(T t)` | `T → R` | `map`, `groupingBy` |
| `Consumer<T>` | `void accept(T t)` | `T → tác động` | `forEach`, `peek` |
| `Supplier<T>` | `T get()` | `() → T` | Tạo giá trị hoặc nguồn dữ liệu theo nhu cầu |
| `UnaryOperator<T>` | `T apply(T t)` | `T → T` | `Stream.iterate`, biến đổi cùng kiểu |
| `BinaryOperator<T>` | `T apply(T a, T b)` | `(T,T) → T` | `reduce` |
| `Comparator<T>` | `int compare(T a, T b)` | `(T,T) → int` | `sorted`, `min`, `max` |
| `BiFunction<T,U,R>` | `R apply(T t, U u)` | `(T,U) → R` | Hàm tích lũy có hai đầu vào trong `reduce` ba tham số |

`Comparator<T>` nằm trong `java.util`; những kiểu còn lại trong bảng nằm trong `java.util.function`.

Có cả biến thể tránh boxing cho dữ liệu nguyên thủy:

| Kiểu | Công dụng |
| --- | --- |
| `IntPredicate`, `LongPredicate`, `DoublePredicate` | Điều kiện trên giá trị nguyên thủy. |
| `IntFunction<R>` | Biến `int` thành `R`. |
| `ToIntFunction<T>`, `ToLongFunction<T>`, `ToDoubleFunction<T>` | Biến đối tượng thành giá trị nguyên thủy; dùng với `mapToInt`, `mapToLong`, `mapToDouble`. |
| `IntUnaryOperator`, `LongUnaryOperator`, `DoubleUnaryOperator` | Biến đổi cùng kiểu nguyên thủy. |
| `IntBinaryOperator`, `LongBinaryOperator`, `DoubleBinaryOperator` | Kết hợp hai giá trị nguyên thủy cùng kiểu. |
| `ObjIntConsumer<T>` và các biến thể tương ứng | Nhận một đối tượng và một đối số nguyên thủy. |

Ví dụ:

```java
List<String> names = List.of("An", "Bình", "Chi");

Predicate<String> longEnough = name -> name.length() >= 3;
Function<String, String> normalize = String::trim;
ToIntFunction<String> nameLength = String::length;

List<String> selected = names.stream()
    .map(normalize)
    .filter(longEnough)
    .toList(); // [Bình, Chi]

int totalCharacters = names.stream()
    .mapToInt(nameLength)
    .sum(); // 9
```

Với các tên đã cho, `"An"` có 2 ký tự, `"Bình"` có 4 và `"Chi"` có 3, nên tổng là **9**. `String.length()` đếm đơn vị mã UTF-16; với một số ký tự Unicode ngoài BMP, kết quả này không bằng số ký tự theo cách người dùng nhìn thấy.

### 3.1. Đọc chữ ký của các phép toán Stream

Các phương thức trong `Stream<T>` có chữ ký kiểu generic. Chẳng hạn, dạng rút gọn:

```java
Stream<T> filter(Predicate<? super T> predicate);

<R> Stream<R> map(Function<? super T, ? extends R> mapper);

IntStream mapToInt(ToIntFunction<? super T> mapper);

boolean anyMatch(Predicate<? super T> predicate);

Optional<T> reduce(BinaryOperator<T> accumulator);

<R, A> R collect(Collector<? super T, A, R> collector);
```

Ở đây `T` là kiểu phần tử hiện tại; `R` là kiểu đầu ra sau ánh xạ. Các dấu `? super` và `? extends` là wildcard variance, giúp API chấp nhận hàm có kiểu đầu vào/đầu ra tương thích thay vì buộc trùng khớp tuyệt đối.

Với `Stream<Order>`, `filter` chờ một điều kiện nhận `Order`; `map` có thể biến phần tử thành kiểu khác:

```java
List<Long> amounts = orders.stream()
    .filter(Order::paid)    // Predicate<Order>
    .map(Order::amount)     // Function<Order, Long>, có boxing
    .toList();
```

Nếu mục tiêu là tính tổng, dùng biến thể nguyên thủy sẽ thích hợp hơn:

```java
long total = orders.stream()
    .filter(Order::paid)
    .mapToLong(Order::amount) // ToLongFunction<Order>
    .sum();
```

Các đoạn trên sử dụng kiểu `Order` đã định nghĩa ở mục 1.

## 4. Method reference: tham chiếu một phương thức có sẵn

**Method reference** dùng cú pháp `::` để biểu diễn lời gọi một phương thức hoặc constructor phù hợp với target type. Nó giúp rút gọn lambda khi lambda chỉ chuyển tiếp tham số tới phương thức đã có.

Bốn nhóm quan trọng:

| Dạng | Method reference | Lambda tương đương về hành vi | Kiểu đích ví dụ |
| --- | --- | --- | --- |
| Phương thức `static` | `Integer::parseInt` | `s -> Integer.parseInt(s)` | `Function<String,Integer>` |
| Phương thức instance của một đối tượng cụ thể (*bound*) | `System.out::println` | `s -> System.out.println(s)` | `Consumer<String>` |
| Phương thức instance của đối tượng sẽ được truyền vào (*unbound*) | `String::trim` | `s -> s.trim()` | `Function<String,String>` |
| Constructor | `ArrayList::new` | `() -> new ArrayList<>()` | `Supplier<ArrayList<String>>` |

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

class MethodReferenceKinds {
    public static void main(String[] args) {
        Function<String, Integer> parse = Integer::parseInt;
        Function<String, String> trim = String::trim;
        Consumer<String> print = System.out::println;
        Supplier<ArrayList<String>> factory = ArrayList::new;

        List<Integer> nums = List.of(" 10 ", " 20 ").stream()
            .map(trim)
            .map(parse)
            .toList();

        ArrayList<String> output = factory.get();
        output.add("OK");

        nums.forEach(n -> print.accept(String.valueOf(n)));
        System.out.println(output); // [OK]
    }
}
```

`String::trim` không tạo trước một đối tượng `String` nào: mỗi giá trị đầu vào trở thành **receiver** khi phương thức `trim()` được gọi. Ngược lại, `System.out::println` tham chiếu phương thức của một đối tượng `PrintStream` cụ thể.

### 4.1. Nhìn chữ ký để hiểu method reference không tham số và có tham số

`String::length` trông như không nhận tham số vì `length()` không khai báo tham số. Nhưng với kiểu đích `Function<String,Integer>`, `String` đầu vào chính là receiver:

```java
Function<String, Integer> length = String::length;
int n = length.apply("Stream"); // 6
```

Một method reference dạng unbound cũng có thể nhận thêm đối số của phương thức:

```java
BiPredicate<String, String> startsWith = String::startsWith;

boolean ok = startsWith.test("stream-api", "stream"); // true
```

Ở đây tham số đầu của `BiPredicate` là receiver, tham số thứ hai là đối số của `String.startsWith(String prefix)`.

### 4.2. Constructor reference và array constructor reference

Constructor reference thường được dùng khi tạo collection đầu ra hoặc đối tượng mới:

```java
Supplier<List<String>> listFactory = ArrayList::new;
List<String> list = listFactory.get();

IntFunction<String[]> arrayFactory = String[]::new;
String[] array = arrayFactory.apply(3); // Độ dài 3
```

`ArrayList::new` tương thích với nhiều target type khác nhau nếu có constructor thích hợp; `String[]::new` cần một độ dài, nên nhận `int` qua `IntFunction<String[]>`.

Trong một collector:

```java
ArrayList<String> result = Stream.of(" An ", " Bình ")
    .map(String::trim)
    .collect(Collectors.toCollection(ArrayList::new));
```

`Collectors.toCollection` nhận một `Supplier` để tạo collection tích lũy, phù hợp với constructor reference.

### 4.3. Khi nào method reference không phù hợp?

Method reference chỉ gọn khi ý định có thể đọc trực tiếp từ tên phương thức. Lambda rõ hơn nếu cần kết hợp điều kiện, biến đổi tham số, bắt ngoại lệ hoặc diễn đạt logic nhiều bước:

```java
.filter(order -> order.paid() && order.amount() > 100_000)

.map(name -> name.trim().toUpperCase())

.sorted((left, right) ->
    Integer.compare(left.length(), right.length()))
```

Đừng cố tạo thêm một phương thức chỉ để thay mọi lambda thành method reference. Nếu một method reference gây khó hiểu vì overload hoặc generic type inference, lambda tường minh có thể dễ bảo trì hơn.

## 5. Áp dụng lambda và method reference cho từng phép toán

### 5.1. `filter`: chọn phần tử bằng `Predicate<T>`

`filter` giữ phần tử khi điều kiện trả về `true`:

```java
List<String> names = List.of("An", "", " Bình ", "Chi");

List<String> valid = names.stream()
    .map(String::trim)
    .filter(name -> !name.isEmpty())
    .toList();

// [An, Bình, Chi]
```

Nếu đã có phương thức kiểm tra, có thể tham chiếu trực tiếp:

```java
List<String> nonEmpty = names.stream()
    .filter(Predicate.not(String::isBlank)) // Java 11+
    .toList();
```

`Predicate` còn hỗ trợ kết hợp điều kiện bằng `and`, `or`, `negate`:

```java
Predicate<String> hasLength = name -> name.length() >= 3;
Predicate<String> beginsWithB = name -> name.startsWith("B");

Predicate<String> selected = hasLength.and(beginsWithB);

boolean b = selected.test("Bình"); // true
```

Sự kết hợp dùng ngữ nghĩa short-circuit tương tự toán tử `&&` và `||`. Hãy cân nhắc thứ tự điều kiện khi việc đánh giá có chi phí khác nhau.

### 5.2. `map` và `flatMap`: biến đổi bằng `Function`

`map` nhận mỗi phần tử và trả một kết quả:

```java
List<String> ids = List.of(" A01 ", " B02 ");

List<String> normalized = ids.stream()
    .map(String::trim)
    .map(String::toLowerCase)
    .toList(); // [a01, b02]
```

`flatMap` cần một hàm có đầu ra là Stream để trải phẳng:

```java
List<List<String>> teams = List.of(
    List.of("An", "Bình"),
    List.of("Chi")
);

List<String> members = teams.stream()
    .flatMap(List::stream)
    .toList(); // [An, Bình, Chi]
```

Với `Stream<List<String>>`, `List::stream` là method reference tương ứng `team -> team.stream()`. Mỗi danh sách tạo một Stream con; `flatMap` hợp nhất chúng thành `Stream<String>`.

### 5.3. `sorted`, `min` và `max`: so sánh bằng `Comparator<T>`

Khi cần sắp xếp theo độ dài tên, có thể viết:

```java
List<String> sorted = List.of("Bình", "An", "Chi").stream()
    .sorted((a, b) -> Integer.compare(a.length(), b.length()))
    .toList(); // [An, Chi, Bình]
```

Cách diễn đạt ý định rõ hơn là:

```java
List<String> sorted = List.of("Bình", "An", "Chi").stream()
    .sorted(Comparator.comparingInt(String::length))
    .toList(); // [An, Chi, Bình]
```

`Comparator.comparingInt` nhận `ToIntFunction<String>`, nên `String::length` đóng vai trò trích xuất khóa số nguyên để so sánh. Với đối tượng nghiệp vụ:

```java
Comparator<Order> byAmountDescending =
    Comparator.comparingLong(Order::amount).reversed();

List<Order> expensiveFirst = orders.stream()
    .sorted(byAmountDescending)
    .toList();
```

Nếu cần thứ tự thứ cấp:

```java
Comparator<Order> byAmountThenName = Comparator
    .comparingLong(Order::amount)
    .thenComparing(Order::customer);
```

Khi dùng `sorted`, chú ý chi phí lưu trữ/sắp xếp; trên nguồn không giới hạn, phép toán sắp xếp toàn cục có thể không bao giờ cho kết quả.

### 5.4. `reduce`: gộp bằng `BinaryOperator<T>`

`reduce` hai tham số gồm **identity** và hàm kết hợp:

```java
int sum = Stream.of(10, 20, 30)
    .reduce(0, Integer::sum); // 60
```

`Integer::sum` tương đương `(left, right) -> left + right` và phù hợp với `BinaryOperator<Integer>`. `0` là identity của phép cộng.

Không phải mọi lambda hai tham số đều phù hợp để `reduce`. Phép kết hợp phải có tính **kết hợp (associative)** để cho kết quả đúng khi tổ chức lại nhóm tính toán. Phép trừ không thỏa điều kiện:

```java
// Không phù hợp để làm phép reduce tổng quát, đặc biệt khi chạy song song:
int value = Stream.of(10, 3, 2)
    .reduce(0, (a, b) -> a - b);
```

Thứ tự gom nhóm có thể khiến kết quả phép trừ thay đổi. Với dữ liệu số và mục tiêu tổng, dùng `sum` hoặc `Integer::sum`.

### 5.5. `collect`: truyền hàm vào collector

Collector cũng cần hành vi, chẳng hạn hàm phân nhóm và hàm trích số tiền:

```java
Map<String, Long> revenueByCustomer = orders.stream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::customer,
        Collectors.summingLong(Order::amount)
    ));
```

Trong ví dụ:

- `Order::paid` là điều kiện `Predicate<Order>`.
- `Order::customer` là classifier `Function<Order,String>`.
- `Order::amount` được `summingLong` sử dụng như `ToLongFunction<Order>`.

Phương thức `Collectors.toMap` có thể nhận thêm `BinaryOperator` để giải quyết khóa trùng:

```java
Map<String, Long> maxOrderByCustomer = orders.stream()
    .collect(Collectors.toMap(
        Order::customer,
        Order::amount,
        Long::max
    ));
```

Nếu bỏ hàm gộp và hai phần tử sinh ra cùng khóa, `toMap` dạng hai đối số sẽ ném `IllegalStateException`. Chọn hàm gộp theo quy tắc dữ liệu: tính tổng, chọn lớn nhất hoặc xác định bản ghi ưu tiên.

### 5.6. `forEach` và `peek`: hành động bằng `Consumer<T>`

`forEach` nhận một `Consumer<T>`, thường thấy với thao tác in:

```java
Stream.of("An", "Bình").forEach(System.out::println);
```

`peek` là phép toán trung gian, thường dùng để quan sát quá trình xử lý khi gỡ lỗi:

```java
List<Integer> doubled = Stream.of(1, 2, 3)
    .peek(n -> System.out.println("Saw: " + n))
    .map(n -> n * 2)
    .toList();
```

Không dùng `peek` để cập nhật dữ liệu nghiệp vụ hoặc đếm số phần tử một cách bắt buộc: Stream là lazy và một số phép kết thúc có thể tối ưu bỏ qua duyệt phần tử. `forEach` trên Stream song song cũng không đảm bảo thứ tự gặp phần tử; khi cần giữ thứ tự, cân nhắc `forEachOrdered`.

## 6. Tái sử dụng và kết hợp các hàm đã định nghĩa

Có thể tách các quy tắc xử lý thành biến có kiểu rõ ràng để dùng nhiều lần:

```java
Predicate<String> isUseful = Predicate.not(String::isBlank);
Function<String, String> trim = String::trim;
Function<String, String> upper = String::toUpperCase;

List<String> result = Stream.of("  java ", "", " stream ")
    .map(trim)
    .filter(isUseful)
    .map(upper)
    .toList(); // [JAVA, STREAM]
```

`Function` cung cấp hai phép tổ hợp quan trọng:

- `f.andThen(g)`: thực hiện `f` trước, sau đó `g`.
- `f.compose(g)`: thực hiện `g` trước, sau đó `f`.

```java
Function<String, String> trim = String::trim;
Function<String, String> upper = String::toUpperCase;

Function<String, String> normalize = trim.andThen(upper);

String a = normalize.apply("  java "); // JAVA
String b = upper.compose(trim).apply("  java "); // JAVA
```

Với `Predicate`, các phép `and`, `or`, `negate` giúp biểu diễn quy tắc phức tạp theo từng điều kiện dễ kiểm tra.

**Chú ý:** hàm được tách ra phải có kiểu tương thích với nơi sử dụng. Ví dụ `Predicate<Object>` có thể nhận `String` nếu điều kiện chỉ cần `Object`, nhưng `Predicate<Integer>` không phù hợp với một `Stream<String>`.

## 7. Biến bên ngoài lambda và quy tắc effectively final

Lambda có thể dùng biến cục bộ trong phạm vi bao quanh nếu biến được khai báo `final` hoặc **effectively final** (không bị gán lại sau khi khởi tạo):

```java
long minimum = 100_000;

List<Order> chosen = orders.stream()
    .filter(order -> order.amount() >= minimum)
    .toList();
```

Dù không có từ khóa `final`, `minimum` là effectively final. Ví dụ không hợp lệ:

```java
long minimum = 100_000;
minimum = 200_000;

// Lỗi biên dịch: biến minimum không còn effectively final.
// List<Order> chosen = orders.stream()
//     .filter(order -> order.amount() >= minimum)
//     .toList();
```

**Phân biệt biến và đối tượng:** không gán lại biến tham chiếu không đồng nghĩa với việc đối tượng được tham chiếu là bất biến. Ví dụ sau có thể biên dịch nhưng là thiết kế nguy hiểm:

```java
List<String> output = new ArrayList<>();

names.stream().forEach(output::add); // Biên dịch được, nhưng dùng trạng thái ngoài.
```

Đặc biệt với `parallelStream()`, `ArrayList` không an toàn cho nhiều luồng đồng thời thêm phần tử. Nên diễn đạt việc tích lũy bằng `toList()` hoặc `collect(...)`:

```java
List<String> output = names.stream()
    .filter(Predicate.not(String::isBlank))
    .toList();
```

Lambda còn có thể ghi/đọc thuộc tính của đối tượng bên ngoài, nhưng **tính hợp lệ về cú pháp không đảm bảo an toàn đồng thời** hay phù hợp với non-interference. Khi chạy pipeline, tránh sửa nguồn đang được duyệt và tránh phụ thuộc vào trạng thái mutable chung.

### 7.1. Lambda không tự bảo đảm thời điểm thực thi

`filter`, `map` và nhiều phép toán trung gian là lazy:

```java
Stream<String> pipeline = Stream.of("An", "Bình")
    .map(value -> {
        System.out.println("Mapping: " + value);
        return value.toUpperCase();
    });

System.out.println("Configured");
List<String> result = pipeline.toList();
```

Ở đây `Configured` được in trước khi lambda `map` chạy; `toList()` kích hoạt việc đánh giá. Với `findFirst` hoặc `anyMatch`, chỉ một phần nguồn có thể cần đi qua lambda. Một số phép kết thúc còn có thể dùng tối ưu không phải duyệt từng phần tử.

Do đó, lambda trong các phép toán trung gian nên mô tả **phép tính**, không nên ẩn các tác động phụ mà chương trình bắt buộc phải thực hiện.

## 8. Method reference, overload và suy luận kiểu

Compiler chọn phương thức tham chiếu dựa trên target type, số tham số và kiểu trả về tương thích. Một tên phương thức có overload vẫn có thể dùng bằng `::` nếu ngữ cảnh đủ rõ:

```java
Function<String, Integer> parse = Integer::valueOf;
int n = parse.apply("42");
```

Tương tự, `System.out::println` có nhiều overload nhưng `Consumer<String>` cho biết cần phương thức chấp nhận một `String`.

Khi compiler không đủ thông tin để chọn phương thức, hãy khai báo functional interface rõ ràng hoặc dùng lambda tường minh:

```java
Function<String, Integer> converter = text -> Integer.parseInt(text);
```

Không nên ép kiểu chỉ để giảm số ký tự. Đặt tên biến theo ý định nghiệp vụ thường khiến code dễ đọc hơn.

### 8.1. Trường hợp bound reference cần chú ý

Với method reference dạng `obj::method`, **biểu thức nhận đối tượng `obj` được đánh giá khi tạo method reference**, dù lời gọi phương thức có thể xảy ra sau đó.

```java
String prefix = "ID-";
Function<String, String> addPrefix = prefix::concat;

String id = addPrefix.apply("123"); // ID-123
```

Đối chiếu với dạng unbound `String::concat`: nó cần hai giá trị (receiver và đối số):

```java
BinaryOperator<String> join = String::concat;

String result = join.apply("ID-", "123"); // ID-123
```

Nếu receiver của một bound method reference là `null`, việc tạo reference có thể ném `NullPointerException` ngay tại thời điểm đánh giá. Với lambda `x -> obj.method(x)`, việc truy cập `obj` nằm trong thân lambda và xảy ra lúc gọi lambda. Đây là một khác biệt ngữ nghĩa khi xử lý giá trị có thể null.

## 9. Lambda và ngoại lệ

Các functional interface chuẩn như `Function` và `Predicate` **không khai báo checked exception** trong phương thức trừu tượng. Vì thế, không thể truyền trực tiếp lambda gọi một phương thức ném `IOException` mà không xử lý ngoại lệ:

```java
// Không biên dịch vì IOException là checked exception:
//
// List<String> contents = paths.stream()
//     .map(path -> Files.readString(path))
//     .toList();
```

Một cách xử lý là chuyển lỗi I/O thành `UncheckedIOException` và giữ nguyên nguyên nhân:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

class ReadFilesExample {
    public static void main(String[] args) {
        List<Path> paths = List.of(Path.of("a.txt"), Path.of("b.txt"));

        List<String> contents = paths.stream()
            .map(path -> {
                try {
                    return Files.readString(path);
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            })
            .toList();

        System.out.println(contents.size());
    }
}
```

Ví dụ giả định các tệp tồn tại. Trong hệ thống thực, cần quyết định chính sách lỗi: dừng toàn bộ pipeline, ghi nhận lỗi theo từng phần tử hay trả về một kiểu kết quả có lỗi. Đừng bỏ qua ngoại lệ để tạo vẻ như mọi dữ liệu đều hợp lệ.

Khi Stream gắn với tài nguyên như `Files.lines(path)`, cần quản lý vòng đời bằng `try-with-resources`. Method reference và lambda không tự giải phóng tài nguyên ngoài phạm vi quản lý của API.

## 10. Ví dụ đầy đủ: một pipeline sử dụng nhiều kiểu hàm

Bài toán: từ danh sách đơn hàng, chuẩn hóa tên khách hàng, lọc đơn đã thanh toán với số tiền dương, tính doanh thu theo khách hàng và liệt kê tên theo doanh thu giảm dần.

Ví dụ Java 17+; lưu vào tệp `BehavioralFunctionsDemo.java`:

```java
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class BehavioralFunctionsDemo {
    record Order(String customer, long amount, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order(" An ",   150_000, true),
            new Order("Bình",    75_000, true),
            new Order("An",      90_000, true),
            new Order("Chi",    220_000, false),
            new Order("Dung",    -5_000, true)
        );

        Predicate<Order> valid = order ->
            order.paid() && order.amount() > 0;

        Function<String, String> normalizeName = String::trim;

        Map<String, Long> revenue = orders.stream()
            .filter(valid)
            .collect(Collectors.groupingBy(
                order -> normalizeName.apply(order.customer()),
                Collectors.summingLong(Order::amount)
            ));

        Comparator<Map.Entry<String, Long>> byRevenueDesc =
            Map.Entry.<String, Long>comparingByValue()
                .reversed()
                .thenComparing(Map.Entry.comparingByKey());

        LinkedHashMap<String, Long> ranked = revenue.entrySet().stream()
            .sorted(byRevenueDesc)
            .collect(Collectors.toMap(
                Map.Entry::getKey,
                Map.Entry::getValue,
                (left, right) -> left,
                LinkedHashMap::new
            ));

        System.out.println(ranked);
        // {An=240000, Bình=75000}
    }
}
```

Phân tích:

| Đoạn mã | Kiểu hàm | Vai trò |
| --- | --- | --- |
| `order -> order.paid() && order.amount() > 0` | `Predicate<Order>` | Xác định đơn hợp lệ. |
| `String::trim` | `Function<String,String>` | Chuẩn hóa tên khi gom nhóm. |
| `order -> normalizeName.apply(order.customer())` | `Function<Order,String>` | Trích khóa nhóm đã chuẩn hóa. |
| `Order::amount` | `ToLongFunction<Order>` | Lấy số tiền cho `summingLong`. |
| `Map.Entry.comparingByValue()` và `thenComparing(...)` | `Comparator<Map.Entry<...>>` | Xếp hạng doanh thu; cùng doanh thu thì theo tên. |
| `Map.Entry::getKey`, `Map.Entry::getValue` | `Function` | Chuyển entry trở lại map. |
| `(left, right) -> left` | `BinaryOperator<Long>` | Hàm gộp nếu phát sinh khóa trùng khi `toMap`. |
| `LinkedHashMap::new` | `Supplier<LinkedHashMap<...>>` | Bảo toàn thứ tự đưa phần tử vào map. |

Ở bài toán này, mỗi khóa của `revenue` đã duy nhất nên hàm gộp trong `toMap` không phải xử lý va chạm. `LinkedHashMap` giúp kết quả duy trì thứ tự được tạo sau `sorted`, nhờ đó thứ tự in phản ánh xếp hạng.

### 10.1. Điều gì xảy ra nếu muốn chạy song song?

Có thể đổi `orders.stream()` thành `orders.parallelStream()` để sử dụng cơ chế xử lý song song. Tuy nhiên:

- `valid` và `normalizeName` nên không có trạng thái thay đổi và không phụ thuộc thứ tự gọi.
- `groupingBy` có thể tốn chi phí phối hợp map khi thực thi song song; tốc độ thực tế phụ thuộc kích thước dữ liệu và số nhóm.
- `sorted` phải thiết lập thứ tự kết quả và thường có chi phí đáng kể.
- Không dùng biến `ArrayList` bên ngoài rồi thêm phần tử bằng `forEach` từ nhiều luồng.
- Chỉ chọn thực thi song song khi đã đo đạc trên khối lượng dữ liệu thật và hiểu tính chất nguồn/collector.

Các quy tắc này cũng áp dụng khi viết collector tùy chỉnh, khai thác `Spliterator` hoặc dùng Stream Gatherers để tạo phép toán trung gian mạnh hơn: tính đúng đắn của các hàm hành vi quan trọng hơn việc tiết kiệm vài ký tự khi viết lambda.

## 11. Các lỗi thường gặp và cách xử lý

| Sai lầm | Tại sao không phù hợp | Cách khắc phục |
| --- | --- | --- |
| Viết `var f = x -> ...` | Lambda thiếu target type. | Khai báo `Function<T,R>` hoặc kiểu hàm tương ứng. |
| Truyền `name -> name.length()` cho `filter` | `filter` yêu cầu `boolean`, còn `length()` trả `int`. | Dùng `name -> name.length() > 0`. |
| Dùng `map` khi cần trải phẳng danh sách con | Kết quả vẫn là `Stream<List<T>>`. | Dùng `flatMap(List::stream)`. |
| Chọn `Function<Order,Long>` để tính tổng rất lớn mà không cần boxing | Boxing gây thêm chi phí. | Dùng `ToLongFunction<Order>` và `mapToLong`. |
| Dùng `peek` cho tác động phụ bắt buộc | Pipeline có thể dừng sớm hoặc tối ưu bỏ duyệt. | Dùng phép kết thúc hoặc tách hành động nghiệp vụ rõ ràng. |
| Đưa `(a,b) -> a-b` vào `reduce` | Phép trừ không kết hợp. | Chọn phép toán có tính kết hợp và identity phù hợp. |
| Dùng danh sách mutable chung trong `parallelStream` | Dễ gây race condition hoặc mất dữ liệu. | Dùng collector phù hợp. |
| Dùng method reference quá khó đọc | Overload hoặc suy luận kiểu làm che ý định. | Viết lambda rõ tên tham số và logic. |
| Không xử lý checked exception | `Function.apply` không khai báo `IOException`. | Xử lý ngoại lệ trong lambda hoặc xây dựng abstraction có chính sách lỗi. |
| Giả định mọi Stream có thể dùng nhiều lần | Một đối tượng Stream chỉ tiêu thụ một lần. | Tạo Stream mới từ nguồn có thể duyệt lại. |

## 12. Tự kiểm tra cách hiểu

1. Vì sao `filter(String::isBlank)` hợp lệ, còn `filter(String::length)` thì không?
2. `String::trim` là method reference dạng bound hay unbound? Tham số của `Function<String,String>` đóng vai trò gì?
3. Khi nào dùng `mapToLong(Order::amount)` thay cho `map(Order::amount)`?
4. Vì sao `(a,b) -> a-b` không thích hợp để `reduce` song song?
5. Trong `Collectors.groupingBy(Order::customer, Collectors.summingLong(Order::amount))`, hai method reference cần hai target type nào?
6. Tại sao biến cục bộ được lambda capture phải effectively final nhưng đối tượng được biến đó tham chiếu vẫn có thể mutable?
7. Nếu một method reference khó đọc vì overloaded method, có thể thay thế bằng cú pháp nào?
8. Vì sao lambda của `map` thường không chạy ngay khi gọi `map(...)`?

**Đối chiếu nhanh:** (1) `filter` cần `Predicate<String>` trả `boolean`; (2) unbound, tham số là receiver; (3) khi cần luồng `long` nguyên thủy để xử lý số hiệu quả; (4) phép trừ không associative; (5) `Function<Order,String>` và `ToLongFunction<Order>`; (6) quy tắc capture ràng buộc việc gán lại biến, không biến đối tượng thành immutable; (7) lambda tường minh; (8) phép trung gian Stream thường lazy.

## 13. Ghi nhớ cốt lõi

- **Lambda** là cách viết triển khai hành vi ngắn gọn, được suy luận theo functional interface mà API yêu cầu.
- **Method reference** là cách dùng lại phương thức/constructor đã tồn tại khi chữ ký tương thích với target type; nó giúp code ngắn hơn nếu ý định vẫn rõ.
- **`Predicate`, `Function`, `Consumer`, `Supplier`, `Comparator` và `BinaryOperator`** là những kiểu hàm chủ chốt trong Stream API. Hiểu target type giúp chọn đúng hành vi cho từng phép toán.
- **Các biến thể nguyên thủy** như `ToLongFunction` và `IntUnaryOperator` tránh boxing không cần thiết và giúp sử dụng đúng API của `IntStream`, `LongStream` và `DoubleStream`.
- **Lambda trong pipeline lazy** có thể chạy muộn, chỉ một phần hoặc bị tối ưu bỏ qua trong vài trường hợp; đừng đặt tác động phụ thiết yếu vào các phép toán trung gian.
- **Tính kết hợp, non-interference và tránh trạng thái mutable chia sẻ** là những yêu cầu quan trọng khi đi từ pipeline đơn giản sang `reduce`, `collect`, xử lý song song, collector tùy chỉnh và Gatherers.
