# Predicate, Function, Consumer, Supplier và các biến thể nguyên thủy trong Java 27

Trong Java, **functional interface** mô tả một hành vi có thể được truyền vào phương thức, lưu trong biến, kết hợp với hành vi khác hoặc sử dụng trong các API như Stream, Optional và Map. Bốn giao diện được dùng thường xuyên nhất trong `java.util.function` là:

- `Predicate<T>`: kiểm tra một điều kiện, trả về `boolean`.
- `Function<T, R>`: biến đổi dữ liệu từ `T` sang `R`.
- `Consumer<T>`: tiếp nhận dữ liệu và thực hiện hành động, không trả về kết quả.
- `Supplier<T>`: cung cấp dữ liệu khi được gọi, không nhận đối số.

Java còn cung cấp các biến thể cho hai đầu vào, phép toán cùng kiểu và kiểu nguyên thủy (`int`, `long`, `double`, `boolean` ở một số nhóm), nhằm diễn đạt ý định rõ hơn và tránh boxing/unboxing không cần thiết.

Bài này thuộc chương **Lambda và interface hàm**, nằm trong module **Java 27 và các kiến thức liên quan**. Nội dung tập trung vào các API chính thức, đang được hỗ trợ trong Java hiện hành; không sử dụng tính năng preview hoặc kỹ thuật đã lỗi thời.

## 1. Kiến thức nền: functional interface và lambda

Functional interface là interface có **một phương thức trừu tượng chức năng** (*single abstract method*, SAM) theo quy tắc của ngôn ngữ Java. Nó vẫn có thể có `default` method, `static` method, `private` method và những khai báo phương thức tương ứng với các public method của `Object` mà không làm tăng số phương thức trừu tượng chức năng.

```java
@FunctionalInterface
interface TextRule {
    boolean accepts(String input);

    default boolean rejects(String input) {
        return !accepts(input);
    }
}
```

Một lambda có thể cung cấp cách triển khai cho phương thức trừu tượng:

```java
TextRule nonBlank = text -> text != null && !text.isBlank();

System.out.println(nonBlank.accepts("Java")); // true
System.out.println(nonBlank.accepts("   "));   // false
```

Annotation `@FunctionalInterface` không bắt buộc để interface được xem là functional interface, nhưng nên sử dụng khi tự định nghĩa hợp đồng SAM: compiler sẽ cảnh báo nếu sau này vô tình thay đổi interface khiến nó không còn đúng quy tắc.

### 1.1. Target typing

Lambda không có một kiểu tự thân như `String` hay `int`; compiler cần ngữ cảnh để xác định *target type*:

```java
java.util.function.Predicate<String> check = s -> s.length() >= 3;
java.util.function.Function<String, Integer> length = s -> s.length();
java.util.function.Consumer<String> print = s -> System.out.println(s);
java.util.function.Supplier<String> greeting = () -> "Xin chào";
```

Cùng tham số `s` nhưng:

- `check` có phương thức `test(String)` trả `boolean`.
- `length` có phương thức `apply(String)` trả `Integer`; giá trị `int` từ `length()` được boxing.
- `print` có phương thức `accept(String)` trả `void`.
- `greeting` có phương thức `get()` trả `String` và không nhận đối số.

Nếu không có target type phù hợp, trình biên dịch không thể hiểu một lambda trần như một biểu thức độc lập:

```java
// Không hợp lệ: chưa có target type.
// var rule = s -> s.isBlank();
```

Có thể khai báo rõ kiểu hoặc truyền trực tiếp lambda vào tham số method có kiểu functional interface.

### 1.2. Lambda không đồng nghĩa với hàm thuần

Kiểu `Function` không buộc lời gọi `apply` phải thuần túy hay không có side effect. `Supplier` không tự động cache, `Consumer` không tự động chạy bất đồng bộ, và `Predicate` không được runtime đảm bảo luôn trả cùng kết quả cho cùng đầu vào.

**Hợp đồng nghiệp vụ và cách sử dụng** mới quyết định hành vi có thuần, thread-safe, idempotent hay tốn tài nguyên hay không.

## 2. Bảng so sánh bốn giao diện cốt lõi

| Interface | SAM | Hình dung | Khi sử dụng |
|---|---|---|---|
| `Predicate<T>` | `boolean test(T value)` | `T -> boolean` | Lọc, kiểm tra, xác thực |
| `Function<T, R>` | `R apply(T value)` | `T -> R` | Chuyển đổi, ánh xạ dữ liệu |
| `Consumer<T>` | `void accept(T value)` | `T -> void` | In, ghi log, gửi sự kiện, cập nhật đích |
| `Supplier<T>` | `T get()` | `() -> T` | Giá trị dự phòng, khởi tạo theo nhu cầu, factory |

Ví dụ cùng làm việc với một chuỗi:

```java
import java.util.function.*;

Predicate<String> valid = text -> text != null && !text.isBlank();
Function<String, Integer> count = String::length;
Consumer<String> logger = System.out::println;
Supplier<String> fallback = () -> "Chưa có giá trị";

String name = "Java";

System.out.println(valid.test(name)); // true
System.out.println(count.apply(name)); // 4
logger.accept(name);                  // Java
System.out.println(fallback.get());    // Chưa có giá trị
```

Không cần tạo interface tùy chỉnh khi một interface tiêu chuẩn đã biểu diễn chính xác mục đích. Ngược lại, nếu contract có ngữ nghĩa quan trọng, nhiều phương thức liên quan hoặc checked exception chuyên biệt, một interface do dự án định nghĩa có thể hợp lý hơn.

## 3. Predicate<T>: mô tả điều kiện

`Predicate<T>` được dùng để kiểm tra một đối tượng có thỏa một điều kiện hay không.

```java
import java.util.function.Predicate;

Predicate<Integer> positive = number -> number > 0;

System.out.println(positive.test(10)); // true
System.out.println(positive.test(-3)); // false
```

Trong ví dụ, `Predicate<Integer>` nhận một `Integer` và `test` trả về `boolean` nguyên thủy.

### 3.1. Kết hợp điều kiện bằng and, or và negate

`Predicate` có các default method giúp kết hợp quy tắc:

- `and(other)`: cả hai điều kiện đều đúng.
- `or(other)`: ít nhất một điều kiện đúng.
- `negate()`: phủ định điều kiện.

```java
Predicate<Integer> positive = n -> n > 0;
Predicate<Integer> lessThan100 = n -> n < 100;

Predicate<Integer> valid = positive.and(lessThan100);
Predicate<Integer> invalid = valid.negate();

System.out.println(valid.test(50));    // true
System.out.println(valid.test(150));   // false
System.out.println(invalid.test(-2));  // true
```

`and` và `or` có **short-circuit evaluation**:

- `left.and(right)` không gọi `right.test(value)` nếu `left` trả `false`.
- `left.or(right)` không gọi `right.test(value)` nếu `left` trả `true`.
- Nếu lần đánh giá cần thiết ném exception thì exception lan ra theo lời gọi; không có kết quả `boolean` bình thường.

Ví dụ xử lý `null` an toàn:

```java
import java.util.Objects;

Predicate<String> nonNull = Objects::nonNull;
Predicate<String> nonBlank = text -> !text.isBlank();

Predicate<String> validText = nonNull.and(nonBlank);

System.out.println(validText.test(null));    // false
System.out.println(validText.test("Java"));  // true
```

Ở đầu vào `null`, `nonNull` trả `false`, nên `nonBlank` không chạy và không gọi `isBlank()` trên `null`.

**Không nên** đổi thứ tự thành `nonBlank.and(nonNull)` nếu `nonBlank` không tự kiểm tra null: phép đánh giá đầu tiên có thể ném `NullPointerException`.

### 3.2. Predicate.not và Predicate.isEqual

Java có các static method hữu ích:

```java
Predicate<String> notBlank = Predicate.not(String::isBlank);
Predicate<String> isJava = Predicate.isEqual("Java");

System.out.println(notBlank.test("abc")); // true
System.out.println(isJava.test("Java"));   // true
System.out.println(isJava.test(null));     // false
```

`Predicate.not(predicate)` trả về phép phủ định của predicate đã cho. Nó có thể đọc rõ hơn `predicate.negate()` khi kết hợp method reference.

`Predicate.isEqual(target)` kiểm tra bằng ngữ nghĩa tương đương `Objects.equals(target, value)`, do đó có thể xét `null` mà không cần tự gọi `equals` trên tham chiếu nullable.

### 3.3. Predicate trong Stream và Optional

`Stream.filter` nhận một predicate (chính xác hơn là một kiểu tương thích với `Predicate<? super T>`):

```java
import java.util.List;
import java.util.function.Predicate;

List<String> names = List.of("An", " ", "Bình", "Java");

List<String> meaningful = names.stream()
        .filter(Predicate.not(String::isBlank))
        .toList();

System.out.println(meaningful); // [An, Bình, Java]
```

`Optional.filter` cũng nhận predicate:

```java
import java.util.Optional;

Optional<String> result = Optional.of("Java")
        .filter(text -> text.length() >= 3);

System.out.println(result.orElse("Không phù hợp")); // Java
```

Nếu predicate không đạt, `Optional.filter` trả về một `Optional` rỗng. Nếu đối tượng `Optional` vốn rỗng, predicate không được gọi.

### 3.4. Predicate không thay thế một kết quả giải thích lỗi

Một predicate chỉ trả `true` hoặc `false`. Nếu kiểm tra đầu vào cần giải thích chi tiết tại sao sai, không nên gộp toàn bộ validation nghiệp vụ vào một predicate phức tạp rồi mất thông tin lỗi.

Có thể dùng predicate để sàng lọc nhanh và một loại kết quả có cấu trúc (ví dụ record mô tả lỗi) ở bước validation chính thức.

## 4. Function<T, R>: biến đổi dữ liệu

`Function<T, R>` nhận một giá trị kiểu `T`, trả một giá trị kiểu `R`:

```java
import java.util.function.Function;

Function<String, Integer> parseNumber = Integer::parseInt;

Integer number = parseNumber.apply("42");
System.out.println(number); // 42
```

`Function<String, Integer>` không tự xử lý dữ liệu không hợp lệ. `Integer.parseInt("abc")` vẫn ném `NumberFormatException`; điều đó thuộc về hành vi của function được truyền vào.

### 4.1. andThen: xử lý theo thứ tự trước rồi sau

`f.andThen(g)` tương đương ý tưởng `g(f(x))`:

```java
Function<String, Integer> parse = Integer::parseInt;
Function<Integer, Integer> doubleValue = n -> n * 2;

Function<String, Integer> parseAndDouble = parse.andThen(doubleValue);

System.out.println(parseAndDouble.apply("21")); // 42
```

Các bước:

1. `parse.apply("21")` trả `21`.
2. `doubleValue.apply(21)` trả `42`.

Nếu `parse` ném exception thì `doubleValue` không được gọi.

### 4.2. compose: chạy hàm trước đầu vào của hàm hiện tại

`f.compose(g)` tương đương `f(g(x))`:

```java
Function<String, Integer> parse = Integer::parseInt;
Function<Integer, Integer> doubleValue = n -> n * 2;

Function<String, Integer> result = doubleValue.compose(parse);

System.out.println(result.apply("21")); // 42
```

Bảng ghi nhớ:

| Cú pháp | Trình tự thực thi |
|---|---|
| `f.andThen(g)` | Chạy `f`, rồi `g` |
| `f.compose(g)` | Chạy `g`, rồi `f` |

Không chỉ tên method mà **kiểu đầu vào và đầu ra** phải khớp nhau khi kết hợp. `andThen` và `compose` từ chối function đối số `null` bằng `NullPointerException` theo hợp đồng API.

### 4.3. Function.identity()

`Function.identity()` trả function giữ nguyên giá trị:

```java
Function<String, String> unchanged = Function.identity();

System.out.println(unchanged.apply("Java")); // Java
```

Nó hữu ích khi API cần truyền một phép biến đổi, nhưng hiện tại muốn giữ nguyên đối tượng đầu vào.

### 4.4. Function trong Stream.map

`Stream.map` biến từng phần tử bằng một function:

```java
List<String> words = List.of("java", "lambda");

List<Integer> lengths = words.stream()
        .map(String::length)
        .toList();

System.out.println(lengths); // [4, 6]
```

Ở đây `String::length` có thể thích nghi với `Function<String, Integer>`; giá trị nguyên thủy `int` được boxing thành `Integer`.

Nếu chỉ cần tính toán số nguyên, `mapToInt` thường biểu đạt nhu cầu chính xác hơn; phần biến thể nguyên thủy sẽ giải thích điều này.

### 4.5. Function trong Map.computeIfAbsent

`Map.computeIfAbsent` nhận một mapping function để tạo giá trị khi khóa chưa ánh xạ tới giá trị khác null:

```java
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> lengths = new HashMap<>();

int value = lengths.computeIfAbsent("Java", String::length);
System.out.println(value); // 4
```

Nếu mapping function trả `null`, `computeIfAbsent` không tạo ánh xạ mới cho khóa đó. Với các map có hành vi đồng thời đặc biệt, cần đọc contract của implementation, không tự suy rằng việc tính toán luôn chỉ diễn ra một lần.

## 5. Consumer<T>: thực hiện hành động

`Consumer<T>` nhận giá trị kiểu `T` và không trả kết quả:

```java
import java.util.function.Consumer;

Consumer<String> show = System.out::println;
show.accept("Xin chào Java");
```

Các ứng dụng thường gặp: in dữ liệu, gửi sự kiện, ghi log, cập nhật một đối tượng đích hoặc chuyển dữ liệu sang hệ thống khác.

**Consumer không đồng nghĩa nhất thiết có side effect**; nhưng loại này thường được chọn khi mục đích quan trọng là thực hiện hành động, chứ không tạo giá trị để tiếp tục biến đổi.

### 5.1. Ghép hành động bằng andThen

`Consumer.andThen(other)` chạy consumer hiện tại trước rồi chạy consumer thứ hai với **cùng một đầu vào**:

```java
Consumer<String> printUpper = text ->
        System.out.println(text.toUpperCase());

Consumer<String> printLength = text ->
        System.out.println("Độ dài: " + text.length());

Consumer<String> combined = printUpper.andThen(printLength);

combined.accept("Java");
```

Kết quả:

```text
JAVA
Độ dài: 4
```

Nếu consumer đầu tiên ném exception, consumer thứ hai **không** được gọi. `andThen(null)` không phải cách khai báo "không có hành động tiếp theo"; đối số phải khác `null`.

### 5.2. Consumer trong forEach

`Iterable.forEach`, `Stream.forEach` và `Map.forEach` dùng các biến thể consumer:

```java
List<String> names = List.of("An", "Bình", "Chi");

names.forEach(System.out::println);
```

Với stream tuần tự có thứ tự gặp phần tử như ví dụ này, kết quả thường theo thứ tự dữ liệu. Nhưng với **parallel stream**, không được giả định `forEach` luôn xử lý theo thứ tự đầu vào:

```java
names.parallelStream().forEach(System.out::println);
```

Nếu thứ tự hành động quan trọng với stream có encounter order, `forEachOrdered` duy trì thứ tự đó:

```java
names.parallelStream().forEachOrdered(System.out::println);
```

Dù vậy, thiết kế pipeline thường nên tránh side effect dùng chung, nhất là khi chạy song song. Nếu mục đích là tạo collection kết quả, nên dùng `map`, `filter`, `collect` hoặc `toList()` thay vì sửa một danh sách bên ngoài từ `forEach`.

### 5.3. Không dựa vào Consumer để bảo đảm giao dịch

`Consumer<T>` không mô tả chính sách retry, khả năng phát lại, tính idempotent hay transaction. Nếu nó ghi database hoặc phát message, cần thiết kế riêng cách xử lý khi tác vụ thành công một phần hoặc ném exception.

## 6. Supplier<T>: cung cấp giá trị khi được gọi

`Supplier<T>` không nhận đối số, trả một giá trị kiểu `T`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

Supplier<List<String>> newList = ArrayList::new;

List<String> first = newList.get();
List<String> second = newList.get();

System.out.println(first == second); // false
```

Mỗi lời gọi ở đây tạo một `ArrayList` mới vì **đó là cách lambda/method reference được định nghĩa**. Interface `Supplier` không tự yêu cầu tạo mới hay tự cache.

### 6.1. Lazy fallback với Optional.orElseGet

`Optional.orElseGet` nhận `Supplier<? extends T>`. Supplier chỉ được gọi khi `Optional` rỗng:

```java
import java.util.Optional;

static String expensiveFallback() {
    System.out.println("Tạo giá trị dự phòng");
    return "Khách";
}

static void example() {
    String present = Optional.of("An")
            .orElseGet(() -> expensiveFallback());

    System.out.println(present); // An
}
```

Trong ví dụ, `expensiveFallback()` không chạy vì `Optional` có sẵn giá trị.

So sánh với:

```java
String result = Optional.of("An").orElse(expensiveFallback());
```

Ở đây Java phải đánh giá đối số `expensiveFallback()` trước khi gọi `orElse`, nên việc tạo giá trị dự phòng xảy ra **kể cả khi không cần**.

Dùng `orElseGet` khi fallback có chi phí hoặc tác dụng phụ cần tránh, còn `orElse` thường ổn khi truyền một hằng hoặc biểu thức rất rẻ.

### 6.2. Supplier trong Stream.generate

`Stream.generate` nhận Supplier để tạo phần tử theo nhu cầu xử lý của stream:

```java
import java.util.stream.Stream;

List<String> values = Stream.generate(() -> "tick")
        .limit(3)
        .toList();

System.out.println(values); // [tick, tick, tick]
```

`Stream.generate` có thể sinh stream không giới hạn; hãy dùng `limit` hoặc một cơ chế giới hạn phù hợp nếu muốn duyệt hết kết quả. Với supplier có trạng thái, việc dùng trong pipeline song song cần đặc biệt cẩn trọng về khả năng dùng lại và đồng thời.

### 6.3. Supplier không tự bảo đảm thread-safety

Hai thread có thể gọi cùng một `Supplier`. Nếu supplier đọc/ghi trạng thái mutable không đồng bộ, vẫn có nguy cơ race condition. Cần bảo đảm thread-safety bằng thiết kế của hàm và đối tượng nó sử dụng, không dựa vào tên interface.

## 7. Khi nào dùng interface nào?

| Tình huống | Chọn interface | Ví dụ |
|---|---|---|
| Kiểm tra đơn hàng đạt điều kiện | `Predicate<Order>` | `order -> order.total() > 0` |
| Đổi đơn hàng thành DTO | `Function<Order, OrderDto>` | `OrderDto::from` |
| Ghi log một sự kiện | `Consumer<Event>` | `logger::record` |
| Cung cấp thời điểm hiện tại | `Supplier<Instant>` | `Instant::now` |
| So sánh hai đầu vào | `BiPredicate<A, B>` | `(a, b) -> a.equals(b)` nếu a không null |
| Kết hợp hai giá trị | `BiFunction<A, B, R>` | `(a, b) -> a + b` |
| Xử lý cặp khóa và giá trị | `BiConsumer<K, V>` | `(k, v) -> ...` |
| Chuyển đổi một giá trị cùng kiểu | `UnaryOperator<T>` | `String::strip` |
| Kết hợp hai giá trị cùng kiểu | `BinaryOperator<T>` | `Integer::sum` |

Hãy đặt tên theo **hành vi quan sát được**, không dựa trên số dòng trong lambda. Một phép biến đổi vẫn có thể phát sinh exception; một consumer vẫn có thể phức tạp; quan trọng là contract của API.

## 8. BiPredicate, BiFunction và BiConsumer: hai tham số đầu vào

Bốn interface cốt lõi có những biến thể nhận hai đầu vào cho ba nhóm Predicate, Function và Consumer:

```java
import java.util.function.*;

BiPredicate<String, Integer> minLength =
        (text, min) -> text.length() >= min;

BiFunction<Integer, Integer, Integer> add = Integer::sum;

BiConsumer<String, Integer> printScore =
        (name, score) -> System.out.println(name + ": " + score);

System.out.println(minLength.test("Java", 3)); // true
System.out.println(add.apply(20, 22));        // 42
printScore.accept("An", 9);
```

| Interface | Phương thức trừu tượng | Trả về |
|---|---|---|
| `BiPredicate<T, U>` | `test(T, U)` | `boolean` |
| `BiFunction<T, U, R>` | `apply(T, U)` | `R` |
| `BiConsumer<T, U>` | `accept(T, U)` | `void` |

- `BiPredicate` có `and`, `or` và `negate` tương tự `Predicate`.
- `BiFunction` có `andThen`, nhưng không có `compose` tương ứng như `Function`.
- `BiConsumer` có `andThen`; hai consumer nhận cùng cặp đầu vào.
- Không có `BiSupplier` tiêu chuẩn, vì Supplier vốn được định nghĩa không nhận đầu vào.

### 8.1. Map.forEach dùng BiConsumer

```java
import java.util.Map;

Map<String, Integer> stock = Map.of("Bút", 10, "Vở", 5);

stock.forEach((name, quantity) ->
        System.out.println(name + ": " + quantity));
```

`Map.forEach` chuyển cả khóa và giá trị cho hành động. Với `Map.of`, **không nên giả định thứ tự duyệt cố định**; nếu cần thứ tự cụ thể, dùng cấu trúc có contract về thứ tự hoặc sắp xếp trước.

### 8.2. BiFunction.andThen

```java
BiFunction<Integer, Integer, Integer> sum = Integer::sum;
Function<Integer, String> label = total -> "Tổng = " + total;

BiFunction<Integer, Integer, String> described = sum.andThen(label);

System.out.println(described.apply(10, 20)); // Tổng = 30
```

Hàm `label` được áp dụng lên **kết quả** của `sum`, không chạy độc lập trên từng đối số.

## 9. UnaryOperator và BinaryOperator: cùng kiểu đầu vào, đầu ra

`UnaryOperator<T>` là một dạng chuyên biệt của `Function<T, T>`: đầu vào và đầu ra cùng kiểu.

```java
import java.util.function.UnaryOperator;

UnaryOperator<String> normalize = String::strip;

System.out.println(normalize.apply("  Java  ")); // Java
```

`BinaryOperator<T>` là dạng chuyên biệt của `BiFunction<T, T, T>`:

```java
import java.util.function.BinaryOperator;

BinaryOperator<Integer> sum = Integer::sum;

System.out.println(sum.apply(10, 32)); // 42
```

`BinaryOperator.minBy(comparator)` và `BinaryOperator.maxBy(comparator)` tạo phép chọn phần tử nhỏ nhất/lớn nhất theo comparator. Chúng có ích với `Stream.reduce` khi hai toán hạng có cùng kiểu và kết quả cũng cùng kiểu.

**Lưu ý về phép gộp:** nếu dùng toán tử trong `reduce` chạy song song, phép toán cần đáp ứng contract về tính kết hợp (*associativity*) mà reduction yêu cầu. Không phải bất kỳ `BinaryOperator` nào cũng thích hợp để giảm song song; chẳng hạn phép trừ thông thường không có tính kết hợp.

## 10. Tại sao Java có primitive functional interfaces?

Một lambda dùng `Predicate<Integer>` hoạt động với wrapper `Integer`:

```java
Predicate<Integer> isEven = value -> value % 2 == 0;
```

Khi làm việc với dữ liệu `int`, các thao tác chuyển giữa `int` và `Integer` có thể phát sinh boxing/unboxing. Trong vòng lặp lớn hay pipeline số học, đây có thể là chi phí không cần thiết, mặc dù mức ảnh hưởng thực tế còn phụ thuộc JVM và ngữ cảnh.

Java cung cấp các interface chuyên biệt như `IntPredicate`:

```java
import java.util.function.IntPredicate;

IntPredicate isEven = value -> value % 2 == 0;

System.out.println(isEven.test(8)); // true
```

`IntPredicate.test` nhận trực tiếp `int`, không yêu cầu đầu vào `Integer` theo chữ ký.

### 10.1. Phân biệt kiểu đầu vào và đầu ra

Có ba hướng chuyên biệt hóa:

1. **Đầu vào nguyên thủy**: `IntFunction<R>` nhận `int` nhưng trả `R`.
2. **Đầu ra nguyên thủy**: `ToIntFunction<T>` nhận `T` nhưng trả `int`.
3. **Cả đầu vào và đầu ra nguyên thủy**: `IntUnaryOperator` nhận và trả `int`; `IntToLongFunction` nhận `int` và trả `long`.

Tương tự cho `long` và `double`, với những tổ hợp được thư viện chuẩn định nghĩa.

## 11. Nhóm Predicate nguyên thủy

| Interface | SAM | Công dụng |
|---|---|---|
| `IntPredicate` | `boolean test(int value)` | Điều kiện trên `int` |
| `LongPredicate` | `boolean test(long value)` | Điều kiện trên `long` |
| `DoublePredicate` | `boolean test(double value)` | Điều kiện trên `double` |

```java
import java.util.function.*;

IntPredicate positive = n -> n > 0;
LongPredicate large = n -> n > 1_000_000L;
DoublePredicate finite = Double::isFinite;

System.out.println(positive.test(5));         // true
System.out.println(large.test(2_000_000L));  // true
System.out.println(finite.test(Double.NaN)); // false
```

Ba loại primitive predicate đều có `and`, `or` và `negate` tương ứng, đồng thời giữ giá trị nguyên thủy xuyên suốt lời gọi.

```java
IntPredicate positiveEven =
        ((IntPredicate) (n -> n > 0))
                .and(n -> n % 2 == 0);

System.out.println(positiveEven.test(12)); // true
```

Để tránh phải cast lambda trong ví dụ thực tế, thường dễ đọc hơn khi đặt tên các predicate riêng rồi kết hợp:

```java
IntPredicate positive = n -> n > 0;
IntPredicate even = n -> n % 2 == 0;
IntPredicate positiveEven = positive.and(even);
```

## 12. Nhóm Function chuyên biệt theo kiểu đầu vào hoặc đầu ra

Các interface sau **không đồng nghĩa** dù cùng có từ "Int":

| Interface | Phương thức | Ý nghĩa |
|---|---|---|
| `IntFunction<R>` | `R apply(int value)` | `int -> R` |
| `LongFunction<R>` | `R apply(long value)` | `long -> R` |
| `DoubleFunction<R>` | `R apply(double value)` | `double -> R` |
| `ToIntFunction<T>` | `int applyAsInt(T value)` | `T -> int` |
| `ToLongFunction<T>` | `long applyAsLong(T value)` | `T -> long` |
| `ToDoubleFunction<T>` | `double applyAsDouble(T value)` | `T -> double` |

Ví dụ:

```java
import java.util.function.*;

IntFunction<String> numberLabel = n -> "Mã #" + n;
ToIntFunction<String> textLength = String::length;

System.out.println(numberLabel.apply(7));       // Mã #7
System.out.println(textLength.applyAsInt("Java")); // 4
```

Chú ý tên phương thức:

- `IntFunction<R>` dùng `apply(int)` vì kết quả kiểu tham chiếu `R`.
- `ToIntFunction<T>` dùng `applyAsInt(T)` vì kết quả `int`.
- `ToLongFunction` và `ToDoubleFunction` dùng `applyAsLong`, `applyAsDouble`.

### 12.1. Tạo mảng bằng IntFunction<R[]>

Một nơi API tiêu chuẩn sử dụng primitive input là `Stream.toArray(IntFunction<A[]>)`:

```java
import java.util.stream.Stream;

String[] words = Stream.of("Java", "Lambda")
        .toArray(String[]::new);

System.out.println(words.length); // 2
```

`String[]::new` thích nghi với `IntFunction<String[]>`: hàm nhận **độ dài `int`** để tạo một mảng mới.

Điều này khác với `Supplier<String[]>`, vốn không có tham số số lượng.

### 12.2. Chuyển sang primitive stream bằng mapToInt

```java
import java.util.List;

List<String> words = List.of("Java", "API", "Lambda");

int totalCharacters = words.stream()
        .mapToInt(String::length)
        .sum();

System.out.println(totalCharacters); // 13
```

`mapToInt` nhận kiểu tương thích với `ToIntFunction<String>` và trả về `IntStream`. Các phép toán tiếp theo như `sum` làm việc trực tiếp trên `int`.

## 13. Nhóm UnaryOperator và BinaryOperator nguyên thủy

Khi **cả đầu vào và đầu ra** là nguyên thủy cùng kiểu, các interface operator thường ngắn gọn nhất:

| Interface | SAM | Ý nghĩa |
|---|---|---|
| `IntUnaryOperator` | `int applyAsInt(int x)` | `int -> int` |
| `LongUnaryOperator` | `long applyAsLong(long x)` | `long -> long` |
| `DoubleUnaryOperator` | `double applyAsDouble(double x)` | `double -> double` |
| `IntBinaryOperator` | `int applyAsInt(int a, int b)` | `(int, int) -> int` |
| `LongBinaryOperator` | `long applyAsLong(long a, long b)` | `(long, long) -> long` |
| `DoubleBinaryOperator` | `double applyAsDouble(double a, double b)` | `(double, double) -> double` |

```java
import java.util.function.*;

IntUnaryOperator twice = n -> n * 2;
IntBinaryOperator sum = Integer::sum;

System.out.println(twice.applyAsInt(21)); // 42
System.out.println(sum.applyAsInt(20, 22)); // 42
```

Primitive unary operators có `compose`, `andThen` và `identity`:

```java
IntUnaryOperator plusOne = n -> n + 1;
IntUnaryOperator doubleIt = n -> n * 2;

IntUnaryOperator firstPlusThenDouble = plusOne.andThen(doubleIt);
IntUnaryOperator firstDoubleThenPlus = plusOne.compose(doubleIt);

System.out.println(firstPlusThenDouble.applyAsInt(3)); // 8
System.out.println(firstDoubleThenPlus.applyAsInt(3)); // 7
```

Phân tích:

- `plusOne.andThen(doubleIt)`: `(3 + 1) * 2 = 8`.
- `plusOne.compose(doubleIt)`: `3 * 2 + 1 = 7`.

**Tràn số nguyên:** một `IntUnaryOperator` không tự động kiểm tra overflow. Nếu nghiệp vụ yêu cầu báo lỗi, dùng `Math.addExact` hoặc `Math.multiplyExact` khi phù hợp.

### 13.1. Phép biến đổi giữa các kiểu nguyên thủy

Các interface chuyển từ một kiểu nguyên thủy sang kiểu khác:

| Interface | SAM |
|---|---|
| `IntToLongFunction` | `long applyAsLong(int value)` |
| `IntToDoubleFunction` | `double applyAsDouble(int value)` |
| `LongToIntFunction` | `int applyAsInt(long value)` |
| `LongToDoubleFunction` | `double applyAsDouble(long value)` |
| `DoubleToIntFunction` | `int applyAsInt(double value)` |
| `DoubleToLongFunction` | `long applyAsLong(double value)` |

Ví dụ:

```java
IntToLongFunction toMilliseconds = seconds -> seconds * 1_000L;
DoubleToIntFunction toInt = value -> (int) value;

System.out.println(toMilliseconds.applyAsLong(10)); // 10000
System.out.println(toInt.applyAsInt(3.9));            // 3
```

Phép chuyển `double` sang `int` trong ví dụ là **ép kiểu có mất thông tin** và có các quy tắc xử lý riêng cho NaN, infinity, giá trị ngoài miền `int`. Khi ứng dụng cần quy tắc làm tròn hoặc phát hiện giá trị không hợp lệ, phải tự định nghĩa rõ, không dùng cast mặc định một cách vô ý.

## 14. Nhóm Consumer nguyên thủy

| Interface | SAM | Tình huống |
|---|---|---|
| `IntConsumer` | `void accept(int)` | Xử lý `int` |
| `LongConsumer` | `void accept(long)` | Xử lý `long` |
| `DoubleConsumer` | `void accept(double)` | Xử lý `double` |
| `ObjIntConsumer<T>` | `void accept(T, int)` | Đối tượng và số `int` |
| `ObjLongConsumer<T>` | `void accept(T, long)` | Đối tượng và số `long` |
| `ObjDoubleConsumer<T>` | `void accept(T, double)` | Đối tượng và số `double` |

```java
import java.util.function.*;

IntConsumer printInt = System.out::println;
ObjLongConsumer<String> printAmount =
        (label, amount) -> System.out.println(label + ": " + amount);

printInt.accept(42);                      // 42
printAmount.accept("Tổng VND", 150_000L); // Tổng VND: 150000
```

`IntConsumer`, `LongConsumer` và `DoubleConsumer` có `andThen` với consumer cùng kiểu primitive. Các biến thể `ObjIntConsumer`, `ObjLongConsumer` và `ObjDoubleConsumer` chủ yếu cung cấp SAM tương ứng; **không nên giả định chúng có cùng đầy đủ các default method như `BiConsumer`**.

### 14.1. Stream nguyên thủy và forEach

```java
import java.util.stream.IntStream;

IntStream.rangeClosed(1, 3)
        .forEach(System.out::println);
```

`IntStream.forEach` nhận `IntConsumer`, không phải `Consumer<Integer>`. Do đó pipeline có thể truyền `int` mà không cần biểu diễn từng phần tử bằng wrapper trong chữ ký xử lý.

## 15. Nhóm Supplier nguyên thủy

| Interface | SAM | Giá trị trả về |
|---|---|---|
| `IntSupplier` | `int getAsInt()` | `int` |
| `LongSupplier` | `long getAsLong()` | `long` |
| `DoubleSupplier` | `double getAsDouble()` | `double` |
| `BooleanSupplier` | `boolean getAsBoolean()` | `boolean` |

```java
import java.util.function.*;

IntSupplier answer = () -> 42;
LongSupplier epochMillis = System::currentTimeMillis;
DoubleSupplier pi = () -> Math.PI;
BooleanSupplier enabled = () -> true;

System.out.println(answer.getAsInt());       // 42
System.out.println(pi.getAsDouble());         // 3.141592653589793
System.out.println(enabled.getAsBoolean());   // true
```

`BooleanSupplier` là biến thể quan trọng dành cho `boolean`. Không có toàn bộ một họ `BooleanPredicate`, `BooleanFunction` hay `BooleanConsumer` tiêu chuẩn tương ứng với họ `Int...`.

Lưu ý: `BooleanSupplier` **không phải subtype của** `Supplier<Boolean>`. Nếu một API yêu cầu `Supplier<Boolean>`, có thể cung cấp lambda hoặc method reference phù hợp với target type đó, nhưng sẽ có chuyển đổi kiểu tương ứng khi lấy giá trị.

## 16. Các biến thể nhận hai đầu vào và trả kết quả nguyên thủy

Một số API cần hai đối tượng nhưng trả số nguyên thủy. Khi đó có:

| Interface | SAM |
|---|---|
| `ToIntBiFunction<T, U>` | `int applyAsInt(T left, U right)` |
| `ToLongBiFunction<T, U>` | `long applyAsLong(T left, U right)` |
| `ToDoubleBiFunction<T, U>` | `double applyAsDouble(T left, U right)` |

Ví dụ:

```java
import java.util.function.ToLongBiFunction;

ToLongBiFunction<Long, Integer> total =
        (unitPrice, quantity) -> Math.multiplyExact(unitPrice, quantity);

System.out.println(total.applyAsLong(5_000L, 3)); // 15000
```

Chữ ký vẫn nhận hai wrapper/reference type (`Long`, `Integer`), nhưng trả primitive `long`. Vì vậy không nên hiểu tên `ToLongBiFunction` là "mọi đối số đều là long".

Nếu **cả hai đối số** đều là `long` và kết quả là `long`, hãy chọn `LongBinaryOperator` để tránh boxing ở đầu vào.

## 17. Biến thể nguyên thủy trong Stream

Một lợi ích thực tế nhất là các stream chuyên biệt:

- `IntStream` dùng `IntPredicate` cho `filter`, `IntUnaryOperator` cho `map` và `IntConsumer` cho `forEach`.
- `LongStream` dùng `LongPredicate`, `LongUnaryOperator` và `LongConsumer`.
- `DoubleStream` dùng `DoublePredicate`, `DoubleUnaryOperator` và `DoubleConsumer`.
- `Stream<T>.mapToInt`, `mapToLong` và `mapToDouble` dùng các interface `ToIntFunction<T>`, `ToLongFunction<T>` và `ToDoubleFunction<T>` tương ứng.

Ví dụ hoàn chỉnh:

```java
import java.util.stream.IntStream;

int result = IntStream.rangeClosed(1, 6)
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .sum();

System.out.println(result); // 56 = 2² + 4² + 6²
```

Về mặt target type, lambda trong `filter` là `IntPredicate`, còn lambda trong `map` là `IntUnaryOperator`.

### 17.1. boxed() khi cần đối tượng

Nếu API sau đó cần một `Stream<Integer>`, có thể chuyển qua `boxed()`:

```java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> values = IntStream.range(1, 4)
        .boxed()
        .toList();

System.out.println(values); // [1, 2, 3]
```

Chỉ dùng `boxed()` khi cần làm việc với kiểu wrapper/reference. Việc chuyên biệt hóa primitive thường giúp tránh boxing không cần thiết, nhưng **không bảo đảm một pipeline luôn nhanh hơn**: hiệu suất phải đánh giá trên dữ liệu và JVM thực tế.

### 17.2. Tổng hợp dữ liệu bằng primitive pipeline

```java
record Line(String item, long unitPrice, int quantity) {}

List<Line> lines = List.of(
        new Line("Bút", 5_000L, 3),
        new Line("Vở", 12_000L, 2)
);

long total = lines.stream()
        .mapToLong(line ->
                Math.multiplyExact(line.unitPrice(), line.quantity()))
        .sum();

System.out.println(total); // 39000
```

`mapToLong` dùng contract giống `ToLongFunction<Line>`. Ở đây `Math.multiplyExact` phát hiện tràn số khi nhân từng dòng, nhưng `LongStream.sum()` **không kiểm tra overflow theo cách tương đương `Math.addExact`**. Nếu dữ liệu tiền có thể vượt giới hạn `long`, hãy chọn biểu diễn và phép cộng có kiểm tra thích hợp.

## 18. Ví dụ chạy được: phối hợp cả bốn vai trò và primitive specialization

Chương trình sau tự chứa trong file `FunctionalInterfacesDemo.java`. Nó áp dụng:

1. `Predicate<Item>` để chọn mặt hàng.
2. `Function<Item, String>` để tạo nhãn hiển thị.
3. `Consumer<String>` để xuất kết quả.
4. `Supplier<String>` làm giá trị dự phòng.
5. `ToLongFunction<Item>` để tính tiền từ một mặt hàng.
6. `IntPredicate` và `IntUnaryOperator` qua `IntStream`.
7. `ObjLongConsumer<String>` để in tên chỉ tiêu cùng giá trị `long`.

```java
import java.util.List;
import java.util.Objects;
import java.util.function.*;
import java.util.stream.IntStream;

record Item(String name, int quantity, long unitPriceVnd) {
    Item {
        Objects.requireNonNull(name, "name");

        if (name.isBlank()) {
            throw new IllegalArgumentException("Blank item name");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (unitPriceVnd < 0) {
            throw new IllegalArgumentException("Negative price");
        }
    }
}

public class FunctionalInterfacesDemo {

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("Bút", 3, 5_000L),
                new Item("Vở", 1, 12_000L),
                new Item("Cặp", 2, 30_000L),
                new Item("Tẩy", 2, 0L)
        );

        Predicate<Item> bulk = item -> item.quantity() >= 2;
        Predicate<Item> priced = item -> item.unitPriceVnd() > 0;
        Predicate<Item> selected = bulk.and(priced);

        Function<Item, String> toLabel =
                item -> item.name() + " x" + item.quantity();

        Consumer<String> output = System.out::println;
        Supplier<String> fallback =
                () -> "Chưa có sản phẩm phù hợp";

        ToLongFunction<Item> lineTotal = item ->
                Math.multiplyExact(
                        item.unitPriceVnd(),
                        item.quantity()
                );

        List<String> labels = items.stream()
                .filter(selected)
                .map(toLabel)
                .toList();

        output.accept("Đã chọn: " + labels);

        long total = items.stream()
                .filter(selected)
                .mapToLong(lineTotal)
                .reduce(0L, Math::addExact);

        ObjLongConsumer<String> printAmount =
                (label, value) ->
                        System.out.println(label + ": " + value);

        printAmount.accept("Tổng tiền (VND)", total);

        String firstOrFallback =
                labels.stream().findFirst().orElseGet(fallback);

        output.accept("Đầu tiên: " + firstOrFallback);

        IntPredicate even = n -> n % 2 == 0;
        IntUnaryOperator square = n -> n * n;

        int score = IntStream.rangeClosed(1, 6)
                .filter(even)
                .map(square)
                .sum();

        System.out.println("Điểm: " + score);
    }
}
```

Biên dịch và chạy:

```bash
javac FunctionalInterfacesDemo.java
java FunctionalInterfacesDemo
```

Kết quả dự kiến:

```text
Đã chọn: [Bút x3, Cặp x2]
Tổng tiền (VND): 75000
Đầu tiên: Bút x3
Điểm: 56
```

### 18.1. Phân tích thiết kế

`Predicate<Item>` chỉ quan tâm điều kiện chọn hàng. `Function<Item, String>` xử lý trình bày nhãn. `ToLongFunction<Item>` tạo số tiền dưới dạng `long` để không phải trả `Long` wrapper. `Consumer<String>` xử lý hành động xuất, còn `Supplier<String>` chỉ được dùng khi tìm phần tử đầu tiên không thành công.

Hai phép lọc và biến đổi được mô tả bằng functional interface nhưng không cần tự viết class riêng cho từng hành vi. Đồng thời, phép cộng tiền dùng `Math.addExact` bên trong `reduce` để phát hiện tràn số.

### 18.2. Vì sao không biến mọi hành vi thành lambda?

Việc viết lambda không tự làm thiết kế tốt hơn. Nếu quy tắc nghiệp vụ trở nên phức tạp, cần nhiều dependency, nhiều nhánh kiểm tra hoặc thông báo lỗi chi tiết, nên đặt nó vào method/class có tên và hợp đồng rõ ràng rồi truyền qua method reference khi cần.

Ví dụ một method `isEligible(Item item)` trong service phù hợp có thể được truyền dưới dạng `service::isEligible` mà không cần nhồi logic vào một biểu thức lambda dài.

## 19. Method reference và tương thích chữ ký

Lambda có thể được thay bằng method reference khi biểu thức có thể liên kết trực tiếp đến một method/constructor phù hợp với target type.

| Lambda | Method reference tương ứng | Target type ví dụ |
|---|---|---|
| `s -> s.length()` | `String::length` | `ToIntFunction<String>` |
| `s -> Integer.parseInt(s)` | `Integer::parseInt` | `ToIntFunction<String>` |
| `s -> System.out.println(s)` | `System.out::println` | `Consumer<String>` |
| `() -> new ArrayList<String>()` | `ArrayList<String>::new` | `Supplier<List<String>>` |
| `(a, b) -> Integer.sum(a, b)` | `Integer::sum` | `IntBinaryOperator` |
| `size -> new String[size]` | `String[]::new` | `IntFunction<String[]>` |

Ví dụ:

```java
ToIntFunction<String> length = String::length;
Supplier<List<String>> listFactory = ArrayList::new;
IntBinaryOperator add = Integer::sum;
```

Với method reference tới method instance chưa gắn receiver, ví dụ `String::length`, tham số đầu tiên của functional interface đóng vai trò **receiver**.

Không phải method reference nào cũng có ý nghĩa trong mọi ngữ cảnh: compiler phải đối chiếu số đối số, kiểu tham số, kiểu kết quả, khả năng truy cập và quy tắc về exception của target SAM.

### 19.1. Overload và target type

Một lambda có thể tương thích với nhiều overload, khiến lời gọi trở nên mơ hồ.

```java
// Minh họa API có overload:
// static void choose(Predicate<String> p) { ... }
// static void choose(Function<String, Boolean> f) { ... }
//
// choose(s -> !s.isBlank()); // Có thể mơ hồ giữa hai target type.
```

Giải pháp là sử dụng biến có kiểu khai báo rõ hoặc ép kiểu có chủ đích ở lời gọi:

```java
Predicate<String> rule = s -> !s.isBlank();
// choose(rule);
```

Không nên sửa bằng cast raw hoặc unchecked cast. Hãy diễn đạt target type mong muốn.

## 20. Checked exception và functional interface

Các SAM tiêu chuẩn trong `java.util.function` nói chung **không khai báo checked exception** như `IOException`. Vì vậy, không thể tùy ý truyền method có checked exception vào `Function<T, R>` nếu chưa xử lý ngoại lệ.

Ví dụ sau không hợp lệ:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.Function;

// Không biên dịch: Files.readString có thể ném IOException.
// Function<Path, String> reader = Files::readString;
```

Một cách xử lý là đặt logic tại ranh giới thích hợp và chuyển exception theo một hợp đồng được thiết kế rõ:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.Function;

static Function<Path, String> uncheckedReader() {
    return path -> {
        try {
            return Files.readString(path);
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
    };
}
```

Ví dụ này **chuyển checked exception sang unchecked exception**; không làm lỗi I/O biến mất. Caller vẫn cần quyết định cách xử lý `UncheckedIOException`.

Nếu checked exception là phần thiết yếu của API, một functional interface tùy chỉnh khai báo `throws` có thể đúng hơn việc ép mọi lỗi thành unchecked exception. Việc chọn cách nào cần phản ánh hợp đồng thực tế.

## 21. Captured variables và tính effectively final

Lambda có thể đọc biến cục bộ từ phạm vi bao quanh khi biến đó là `final` hoặc **effectively final** (không bị gán lại).

```java
int minimum = 10;

Predicate<Integer> valid = n -> n >= minimum;

System.out.println(valid.test(12)); // true
```

Không hợp lệ:

```java
// int minimum = 10;
// Predicate<Integer> valid = n -> n >= minimum;
// minimum = 20; // Không biên dịch: minimum không effectively final.
```

Quy tắc này áp dụng cho **biến tham chiếu cục bộ**, không tự động làm bất biến trạng thái của đối tượng mà biến ấy trỏ đến. Một lambda có thể gọi method thay đổi đối tượng mutable được capture, nhưng phải cân nhắc thread safety và side effect.

### 21.1. Stateful lambda trong parallel stream

Ví dụ nên tránh:

```java
// Không nên dùng với parallel stream:
// List<Integer> result = new ArrayList<>();
// IntStream.range(0, 1_000).parallel()
//         .forEach(result::add); // ArrayList không thread-safe.
```

Thay vì sửa một collection dùng chung, hãy ưu tiên collector phù hợp hoặc biểu diễn kết quả bằng pipeline thuần:

```java
List<Integer> result = IntStream.range(0, 1_000)
        .parallel()
        .boxed()
        .toList();
```

Cách này giao việc phối hợp kết quả cho pipeline, không cập nhật `ArrayList` dùng chung từ nhiều thread. Với bài toán cần thứ tự, hãy hiểu contract về encounter order của nguồn và thao tác terminal được dùng.

## 22. Generics, wildcard và variance trong chữ ký API

Dù một lambda có thể dùng trên subtype, `Predicate<Number>` không phải subtype trực tiếp của `Predicate<Integer>`: Java generics **bất biến** theo type argument. Các API chuẩn sử dụng wildcard để thể hiện linh hoạt đầu vào/đầu ra.

Ví dụ chữ ký phổ biến:

- `Stream<T>.filter(Predicate<? super T>)`: nhận một predicate có thể kiểm tra đối tượng kiểu `T`.
- `Stream<T>.map(Function<? super T, ? extends R>)`: nhận đầu vào ở kiểu phù hợp và trả một subtype của `R`.
- `Stream<T>.forEach(Consumer<? super T>)`: chấp nhận consumer xử lý được `T`.
- `Optional<T>.orElseGet(Supplier<? extends T>)`: supplier có thể trả một subtype của `T`.

Ví dụ:

```java
import java.util.List;
import java.util.function.Predicate;

Predicate<Number> nonNegative = n -> n.doubleValue() >= 0;

List<Integer> values = List.of(-2, 0, 3);

List<Integer> kept = values.stream()
        .filter(nonNegative)
        .toList();

System.out.println(kept); // [0, 3]
```

`Predicate<Number>` xử lý được `Integer` vì `Integer extends Number`. Điều này hợp lệ nhờ `filter` nhận `Predicate<? super Integer>`; không cần ép kiểu thủ công.

**Quy tắc gợi nhớ PECS** cũng có ích: các tham số làm nguồn dữ liệu thường dùng `? extends T`, còn nơi nhận và tiêu thụ dữ liệu thường dùng `? super T`. Hãy xem chữ ký cụ thể thay vì suy ra mọi method của `java.util.function` đều giống nhau.

## 23. Chi phí boxing và giới hạn của tối ưu hóa

So sánh hai pipeline:

```java
// Có wrapper Integer trong kiểu Stream<Integer>.
long sum1 = java.util.stream.IntStream.range(0, 1000)
        .boxed()
        .filter(n -> n % 2 == 0)
        .mapToLong(Integer::longValue)
        .sum();

// Ở mức chữ ký, giữ dữ liệu ở dạng int lâu hơn.
long sum2 = java.util.stream.IntStream.range(0, 1000)
        .filter(n -> n % 2 == 0)
        .asLongStream()
        .sum();
```

Cả hai đều tính tổng các số chẵn trong khoảng từ 0 đến 999. Pipeline thứ hai tránh nhu cầu chuyển sang `Stream<Integer>` ở mức API.

Tuy nhiên, **không khẳng định mỗi giá trị boxing nhất thiết tạo một object mới**, hoặc mọi primitive stream đều nhanh hơn đáng kể. JVM có caching, escape analysis và tối ưu hóa khác; hiệu suất phụ thuộc workload, JDK, JIT và môi trường chạy.

Khi hiệu năng quan trọng, đo bằng công cụ benchmark phù hợp (ví dụ JMH) thay vì dựa trên giả định từ tên interface. Trước hết hãy chọn API có ngữ nghĩa rõ ràng.

## 24. Những lỗi thường gặp

| Sai lầm | Vì sao sai hoặc rủi ro | Cách tránh |
|---|---|---|
| Nhầm `Predicate` với `Function<T, Boolean>` | Predicate có SAM trả primitive `boolean`; Function trả object `Boolean` | Chọn theo ngữ nghĩa, chú ý boxing |
| Dùng `Consumer` khi cần giá trị trả về | `accept` trả `void` | Dùng Function hoặc operator |
| Cho rằng `Supplier` tự memoize | `get` không có hợp đồng caching | Tự thiết kế cache/lazy holder khi cần |
| Nghĩ `Supplier` mặc định chạy bất đồng bộ | Interface không quyết định thời điểm/thread thực thi | Xem API gọi supplier, ví dụ CompletableFuture |
| Đảo thứ tự `compose` và `andThen` | Hai phép có thứ tự đánh giá khác nhau | Viết `f.andThen(g) = g(f(x))` |
| Đặt predicate không an toàn với null trước `and` | Short-circuit chỉ bảo vệ vế phải | Đặt kiểm tra null ở trước |
| Dùng `forEach` để sửa dữ liệu dùng chung trong parallel stream | Race condition và thứ tự không bảo đảm | Dùng collector/terminal operation phù hợp |
| Cho rằng `Consumer.andThen` vẫn chạy phần sau khi phần đầu lỗi | Nếu đầu tiên ném exception, phần sau không chạy | Xử lý lỗi theo contract |
| Dùng `Function<String, Integer>` trong pipeline số học lớn dù chỉ cần `int` | Có thể boxing/unboxing | Cân nhắc `ToIntFunction` và `IntStream` |
| Nhầm `IntFunction<R>` với `ToIntFunction<T>` | Một loại nhận primitive, loại còn lại trả primitive | Đọc chữ ký `apply` / `applyAsInt` |
| Gọi `get()` trên `IntSupplier` | SAM đúng là `getAsInt()` | Dùng tên method chuyên biệt |
| Nghĩ `BooleanSupplier` là `Supplier<Boolean>` | Hai interface khác nhau | Chuyển qua lambda/method reference nếu cần |
| Dùng lambda với checked exception chưa xử lý | SAM không khai báo checked exception tương ứng | Xử lý lỗi hoặc định nghĩa interface có `throws` |
| Capture biến cục bộ rồi gán lại | Biến không còn effectively final | Dùng biến không thay đổi hoặc thiết kế trạng thái rõ ràng |
| Kỳ vọng method reference luôn suy luận được | Có thể thiếu target type hoặc overload mơ hồ | Khai báo kiểu rõ |
| Xem lambda là thread-safe vì cú pháp ngắn | Mutable captured state vẫn có thể race | Thiết kế bất biến hoặc đồng bộ phù hợp |
| Quên contract của `Map.computeIfAbsent` | Mapping function có thể không chạy hoặc trả null | Thiết kế function an toàn và hiểu Map implementation |

## 25. Bài tập thực hành

### Bài 1: Predicate và short-circuit

Tạo `Predicate<String>` kiểm tra chuỗi khác null, không blank và dài không quá 50 ký tự. Sử dụng `and` để kết hợp, bảo đảm đầu vào null không gây `NullPointerException`. Kiểm tra với `null`, `""`, `"Java"` và chuỗi dài 51 ký tự.

### Bài 2: Function compose và andThen

Viết `Function<String, Integer>` parse số và `Function<Integer, Integer>` nhân đôi. Tạo một function bằng `andThen` và một function bằng `compose`, kiểm tra cả hai với `"21"`. Thử `"abc"`, giải thích exception phát sinh ở bước nào.

### Bài 3: Consumer kết hợp

Tạo hai `Consumer<String>`: một ghi nhãn "START" và chuỗi, một ghi nhãn "END" và độ dài chuỗi. Ghép bằng `andThen`. Sau đó làm consumer đầu tiên ném exception để quan sát consumer thứ hai có chạy không.

### Bài 4: Supplier và Optional

Viết method dự phòng có thể quan sát được (ví dụ in log "Generating default"). So sánh `Optional.of("value").orElse(...)` với `orElseGet(...)`; mô tả số lần fallback được gọi khi Optional có giá trị và khi Optional rỗng.

### Bài 5: Primitive Predicate và Operator

Dùng `IntStream.rangeClosed(1, 100)`, một `IntPredicate` chọn số chia hết cho 3, một `IntUnaryOperator` tính bình phương, rồi tính tổng bằng `sum()`. Giải thích vì sao phép biến đổi không cần `Integer` theo chữ ký của các interface này.

### Bài 6: IntFunction và ToIntFunction

Tạo `IntFunction<String[]>` nhận độ dài và tạo mảng `String[]`. Tạo `ToIntFunction<String>` trả độ dài chuỗi. Giải thích đâu là kiểu đầu vào và đầu ra nguyên thủy ở từng trường hợp.

### Bài 7: BiFunction và ObjLongConsumer

Dùng `ToLongBiFunction<Long, Integer>` tính tổng tiền dòng hàng bằng `Math.multiplyExact`. Dùng `ObjLongConsumer<String>` in tên mặt hàng và tổng tiền dưới dạng `long`. Thử giá trị lớn để quan sát cách phát hiện overflow.

### Bài 8: Refactor một pipeline

Cho một danh sách record `Student(String name, int score)`. Dùng `Predicate<Student>` lọc điểm từ 60 trở lên, `Function<Student, String>` lấy tên và `Consumer<String>` in kết quả. Sau đó tính tổng điểm bằng `mapToInt(Student::score).sum()` và giải thích lựa chọn `ToIntFunction` của `mapToInt`.

### Bài 9: Interface tự định nghĩa khi có checked exception

Giả sử cần đọc file và giữ nguyên `IOException` ở hợp đồng. Thiết kế functional interface chỉ có một abstract method `read(Path) throws IOException`. Viết lambda triển khai và so sánh nó với việc buộc dùng `Function<Path, String>`.

### Bài 10: Chọn đúng interface

Đối với các hành vi sau, chọn interface chính xác và tên SAM: kiểm tra số `double` hữu hạn, đổi `long` thành `double`, tạo timestamp `long`, ghi một số `int`, tính giá trị lớn nhất của hai số `int` và chuyển một `String` thành `int`. Giải thích khi nào wrapper type là cần thiết.

## 26. Tóm tắt

Bốn functional interface chính có thể ghi nhớ như sau:

- **`Predicate<T>` — `test(T)`**: trả `boolean` để mô tả điều kiện; hỗ trợ `and`, `or` và `negate`.
- **`Function<T, R>` — `apply(T)`**: biến đổi dữ liệu; hỗ trợ `compose`, `andThen` và `identity`.
- **`Consumer<T>` — `accept(T)`**: thực hiện hành động không trả kết quả; có `andThen`.
- **`Supplier<T>` — `get()`**: cung cấp giá trị không nhận đối số, phù hợp với dữ liệu dự phòng hoặc factory theo nhu cầu.

Các biến thể như `BiPredicate`, `BiFunction`, `BiConsumer`, `UnaryOperator` và `BinaryOperator` mô tả chính xác hơn số lượng tham số và mối quan hệ kiểu. Các interface nguyên thủy (`IntPredicate`, `ToLongFunction`, `IntUnaryOperator`, `IntConsumer`, `IntSupplier`, `ObjLongConsumer`...) giúp giữ `int`, `long` và `double` trong chữ ký khi cần, đồng thời cải thiện tính rõ ràng của các pipeline số học.

Chọn interface dựa trên **hợp đồng hành vi**, không dựa vào thói quen viết lambda. Hãy chú ý null, short-circuit, thứ tự composition, checked exception, biến bị capture, side effect và khả năng chạy song song. Khi cần tối ưu hiệu năng, primitive specialization là công cụ hữu ích nhưng không thay thế việc đo đạc thực tế.

## Tài liệu tham khảo

- [Java SE 27 API — java.util.function (package summary)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/function/package-summary.html)
- [Java SE 27 API — Predicate](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/function/Predicate.html)
- [Java SE 27 API — Function](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/function/Function.html)
- [Java SE 27 API — Consumer](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/function/Consumer.html)
- [Java SE 27 API — Supplier](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/function/Supplier.html)
- [Java SE 27 API — IntStream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/IntStream.html)
- [Java Language Specification — Section 15.27: Lambda Expressions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.27)
- [Java Language Specification — Section 9.8: Functional Interfaces](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.8)
