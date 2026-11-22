# Function<T, R> và biến đổi giá trị trong Java hiện đại

`Function<T, R>` là functional interface thuộc `java.util.function`, được giới thiệu trong Java 8 và vẫn là một phần nền tảng của Java hiện đại. Nó biểu diễn quy tắc **nhận một giá trị kiểu `T` và tạo ra một giá trị kiểu `R`**. Khi đọc code, một `Function` nên trả lời được câu hỏi: “Dữ liệu đầu vào được biến đổi thành đầu ra như thế nào?”

Ví dụ: từ chuỗi nhập vào lấy độ dài; từ `Order` tạo `OrderView`; từ dữ liệu thô tạo tên hiển thị; từ mã sản phẩm tạo khóa tra cứu. `Function` giúp truyền phép biến đổi như một tham số, ghép nhiều phép biến đổi và dùng thống nhất trong `Stream.map`, `Optional.map` hoặc những API nhận callback.

Bài này giải thích bản chất, chữ ký, cách sử dụng `apply`, `compose`, `andThen`, `identity`, xử lý lỗi và tác dụng phụ, cùng các ví dụ chạy được với JDK 17 trở lên. Những API Java được dùng ở đây vẫn phù hợp trong các JDK mới.

## 1. Hợp đồng: T đi vào, R đi ra

Định nghĩa cốt lõi của `Function<T, R>` có thể hình dung như sau:

```java
@FunctionalInterface
public interface Function<T, R> {
    R apply(T value);
    // Còn có các phương thức default và static để ghép hành vi.
}
```

Đây là **mô hình rút gọn để giải thích**, không phải bản sao toàn bộ mã nguồn JDK. Phương thức trừu tượng duy nhất là `R apply(T value)`. Vì vậy có thể tạo một `Function` bằng lambda hoặc method reference:

```java
Function<String, Integer> length = text -> text.length();
Function<Integer, String> label = number -> "Số " + number;
Function<String, String> trim = String::trim;
```

Đây là những **đoạn minh họa**, cần `import java.util.function.Function;` và đặt trong một phương thức hoặc lớp phù hợp.

- `Function<String, Integer>` nhận `String` và trả `Integer`. Gọi `length.apply("Java")` cho kết quả `4`.
- `Function<Integer, String>` nhận `Integer` và trả `String`. `label.apply(8)` trả `"Số 8"`.
- `Function<String, String>` giữ nguyên kiểu dữ liệu nhưng thay đổi giá trị. `trim.apply("  Hi  ")` trả `"Hi"`.

`T` và `R` là **tham số kiểu**; chúng có thể giống hoặc khác nhau. `Function` không giới hạn bạn vào các kiểu `String`/`Integer`: nó cũng nhận object nghiệp vụ, record, DTO, collection hay kiểu miền riêng. Generic type giúp trình biên dịch phát hiện nhiều lỗi ghép kiểu ngay lúc biên dịch.

Dù body là lambda hay method reference, kiểu trả về thực tế phải tương thích `R`. Java có thể suy luận kiểu của tham số lambda từ *target type*: viết `text -> text.length()` thay vì luôn ghi `(String text) -> text.length()`.

## 2. apply(): thực thi phép biến đổi

`apply` là điểm gọi chính. Gán một lambda vào biến chưa thực thi body; mã chạy khi gọi `apply` hoặc khi một API như `Stream.map` áp dụng nó.

```java
Function<String, Integer> parse = Integer::parseInt;
int value = parse.apply("42");  // 42 nhờ tự unbox Integer sang int
```

Ví dụ chỉ minh họa. `Integer.parseInt` có kiểu trả `int`, Java thực hiện boxing sang `Integer` khi cần để đáp ứng kiểu `R`. Một số tình huống với dữ liệu số lớn có thể hưởng lợi từ các functional interface chuyên cho primitive, được trình bày ở phần sau.

Nếu lambda trả kết quả bằng **expression body**, giá trị của biểu thức được trả về ngầm định:

```java
Function<Integer, Integer> doubleValue = number -> number * 2;
```

Nếu có nhiều câu lệnh, dùng **block body** và `return` tường minh:

```java
Function<String, String> display = raw -> {
    String normalized = raw == null ? "" : raw.trim();
    if (normalized.isEmpty()) {
        return "(không có tên)";
    }
    return normalized;
};
```

Đây là các đoạn minh họa cần import `Function`. Cả hai hình thức đều thực hiện cùng hợp đồng `T -> R`. Đừng ép một phép biến đổi phức tạp thành một lambda một dòng; đặt tên phương thức như `normalizeDisplayName` và truyền `MyFormatter::normalizeDisplayName` sẽ rõ ràng hơn khi logic có nhiều quy tắc.

## 3. compose() và andThen(): ghép các phép biến đổi đúng thứ tự

Một lợi ích lớn của `Function` là kết hợp các hàm nhỏ thành một pipeline. **Thứ tự rất quan trọng**.

Giả sử có:
- `trim`: `String -> String`, bỏ khoảng trắng hai đầu.
- `length`: `String -> Integer`, lấy chiều dài chuỗi.

Có thể ghép:

```java
Function<String, String> trim = String::trim;
Function<String, Integer> length = String::length;

Function<String, Integer> withAndThen = trim.andThen(length);
Function<String, Integer> withCompose = length.compose(trim);
```

Hai cách đều có nghĩa **trim trước, lấy độ dài sau**.

### andThen(): làm hàm hiện tại trước, hàm tiếp theo sau

`f.andThen(g)` tương đương hàm `x -> g.apply(f.apply(x))`.

```java
Function<Integer, Integer> doubleIt = n -> n * 2;
Function<Integer, Integer> plusThree = n -> n + 3;

int result = doubleIt.andThen(plusThree).apply(4);
// (4 * 2) + 3 = 11
```

Đoạn minh họa cần import `Function`. Đọc từ trái sang phải: “nhân hai, rồi cộng ba”. Đó là lý do `andThen` thường phù hợp khi viết chuỗi bước xử lý dữ liệu.

### compose(): làm hàm được truyền vào trước, hàm hiện tại sau

`f.compose(g)` tương đương `x -> f.apply(g.apply(x))`.

```java
Function<Integer, Integer> doubleIt = n -> n * 2;
Function<Integer, Integer> plusThree = n -> n + 3;

int result = doubleIt.compose(plusThree).apply(4);
// (4 + 3) * 2 = 14
```

`compose` đọc là “áp dụng `plusThree` trước, rồi `doubleIt`”. Cả hai API đều trả về **một Function mới**; bản thân các `Function` ban đầu vẫn dùng được. Khi viết code dễ nhầm thứ tự, đặt tên từng phép biến đổi rõ ràng và viết test với dữ liệu mà hai thứ tự cho kết quả khác nhau.

### Điều kiện để ghép kiểu

Hàm sau phải nhận kiểu tương thích với đầu ra của hàm trước:

| Bước thứ nhất | Bước thứ hai | Có thể dùng `andThen`? |
| --- | --- | --- |
| `Function<String, Integer>` | `Function<Integer, String>` | Có: `String -> Integer -> String` |
| `Function<String, String>` | `Function<CharSequence, Integer>` | Có: `String` là `CharSequence` |
| `Function<Integer, String>` | `Function<Double, String>` | Không trực tiếp: đầu ra `String` không phải `Double` |

Đây là bảng khái niệm; chữ ký tổng quát của `andThen` là `<V> Function<T, V> andThen(Function<? super R, ? extends V> after)`. Các wildcard giúp ghép kiểu tổng quát hơn khi đầu ra là subtype mà hàm tiếp theo chấp nhận supertype. `compose` có chữ ký tương tự theo chiều ngược lại.

## 4. identity(): giữ nguyên giá trị

`Function.identity()` là static factory trả về một phép biến đổi **đồng nhất**: đưa giá trị nào vào sẽ trả lại chính giá trị đó.

```java
Function<String, String> same = Function.identity();
String value = same.apply("Java"); // "Java"
```

Một ví dụ thực tế là nơi API yêu cầu một `Function` nhưng bạn muốn giữ nguyên phần tử, hoặc dùng phần tử như khóa khi thu thập dữ liệu:

```java
Map<String, String> byName = names.stream()
        .collect(Collectors.toMap(
                Function.identity(),
                String::toUpperCase
        ));
```

Đây là **đoạn minh họa**, cần định nghĩa `names` và import `java.util.Map`, `java.util.function.Function`, `java.util.stream.Collectors`. `Function.identity()` lấy chính chuỗi làm key; `String::toUpperCase` tạo value. Nếu đầu vào có khóa trùng, `Collectors.toMap` phiên bản hai tham số sẽ ném `IllegalStateException`; khi có thể trùng, cung cấp hàm merge phù hợp. Đối với xử lý không cần bản đồ, đừng dùng `identity()` chỉ để khiến cú pháp dài thêm.

`identity()` **không có nghĩa tạo bản sao**. Nếu `T` là object, nó trả về cùng tham chiếu object. Đừng xem nó là cơ chế sao chép hay bất biến hóa dữ liệu.

## 5. Function trong Stream.map(): chuyển từng phần tử

`Stream.map` nhận một `Function<? super T, ? extends R>`, áp dụng phép biến đổi cho mỗi phần tử mà Stream xử lý rồi tạo một Stream kết quả kiểu `R`. Đây là ứng dụng phổ biến của `Function`:

```java
List<String> rawNames = Arrays.asList("  An  ", " Binh ", "Chi");
Function<String, String> trim = String::trim;

List<Integer> lengths = rawNames.stream()
        .map(trim)
        .map(String::length)
        .collect(Collectors.toList());
// lengths chứa [2, 4, 3]
```

Đoạn minh họa cần import `java.util.*`, `java.util.function.Function` và `java.util.stream.Collectors`. Pipeline trên là **Stream<String> -> Stream<String> -> Stream<Integer> -> List<Integer>**. `map` không thay đổi phần tử nguồn chỉ vì tên gọi “map”; nó lấy các giá trị do Function trả về. Tuy nhiên, nếu lambda gọi setter trên object, chính bạn đang gây tác dụng phụ, nên cần cân nhắc thiết kế.

**Phân biệt `map` và `flatMap`:** `map` biến một phần tử thành **một kết quả** tương ứng (kết quả có thể là object hoặc collection). `flatMap` dùng khi muốn chuyển mỗi phần tử thành một Stream con rồi *trải phẳng* thành một Stream duy nhất. Ví dụ, `List<List<String>>` mà gọi `map(List::stream)` sẽ cho Stream các Stream, còn `flatMap(List::stream)` sẽ cho Stream các String. Cả hai vẫn nhận hành vi dưới dạng hàm, nhưng `flatMap` mong đợi hàm trả về Stream tương ứng.

### Kết hợp filter trước hay map trước?

`filter` nhận `Predicate<T>`, tức phép thử trả `boolean`; `map` nhận `Function<T,R>`, tức phép biến đổi trả `R`.

```java
List<Integer> lengths = rawNames.stream()
        .map(String::trim)
        .filter(name -> !name.isEmpty())
        .map(String::length)
        .collect(Collectors.toList());
```

Đây là minh họa. Nếu filter phụ thuộc vào **giá trị sau chuẩn hóa**, cần gọi `map(String::trim)` trước. Nếu filter có thể áp dụng an toàn trên dữ liệu gốc và loại được nhiều phần tử, đặt filter trước có thể giảm công việc, nhưng phải đảm bảo ngữ nghĩa không thay đổi. Đừng đảo thứ tự chỉ vì mục tiêu tối ưu khi hai cách cho kết quả khác nhau.

Một Stream là pipeline *lazy*: các bước trung gian thường chỉ thực thi khi có terminal operation. Vì vậy, không dùng `map` làm nơi bắt buộc ghi log hoặc audit, vì không thể dựa vào số lần Function được gọi khi có short-circuit hoặc tối ưu hóa.

## 6. Function trong Optional.map() và API khác

`Optional.map` cũng nhận `Function`, nhưng chỉ áp dụng phép biến đổi khi Optional có giá trị. Nếu mapper trả về `null`, kết quả là `Optional.empty()`; nếu Optional đã rỗng, mapper không chạy.

```java
Optional<String> maybeName = Optional.of("  An  ");
int length = maybeName
        .map(String::trim)
        .map(String::length)
        .orElse(0);
// length = 2
```

Đoạn minh họa cần `import java.util.Optional;`. Có thể dùng phương thức `Optional.map` để tiếp tục biến đổi giá trị một cách an toàn thay vì gọi `get()` ngay khi chưa biết có dữ liệu.

**Khác biệt giữa `map` và `flatMap` của Optional:** nếu mapper trả về `Optional<R>`, dùng `flatMap` để tránh `Optional<Optional<R>>`. Chỉ dùng `map` khi mapper trả về một giá trị `R` bình thường (có thể `null`, khi đó kết quả rỗng). Quy tắc “map giữ cấu trúc bao, flatMap nối cấu trúc bao” cũng có ích khi học Stream và các API chức năng khác.

`CompletableFuture.thenApply` nhận một `Function` để chuyển đổi kết quả thành kiểu khác; `thenCompose` dùng khi bản thân phép biến đổi trả về một `CompletionStage`. Các API này vẫn sử dụng cùng tư duy: **một hàm biến đổi `T -> R` có thể được truyền và ghép ở những ngữ cảnh khác nhau**.

## 7. Khi nào nên dùng Function, UnaryOperator, Predicate, Consumer hoặc BiFunction?

Những functional interface này dễ nhầm vì đều có thể nhận lambda.

| Nhu cầu | Interface | Phương thức chức năng |
| --- | --- | --- |
| Một đầu vào, một đầu ra bất kỳ | `Function<T, R>` | `R apply(T)` |
| Một đầu vào, đầu ra cùng kiểu | `UnaryOperator<T>` | `T apply(T)` |
| Một đầu vào, kiểm tra đúng/sai | `Predicate<T>` | `boolean test(T)` |
| Nhận dữ liệu rồi thực hiện hành động, không trả kết quả | `Consumer<T>` | `void accept(T)` |
| Không nhận dữ liệu, cung cấp kết quả | `Supplier<T>` | `T get()` |
| Hai đầu vào, một đầu ra | `BiFunction<T, U, R>` | `R apply(T, U)` |

`UnaryOperator<T>` là một specialization của `Function<T,T>` nên mang đúng ý nghĩa “cùng kiểu”; chọn nó khi API muốn diễn đạt hợp đồng này rõ ràng. `Predicate<T>` tách việc **kiểm tra điều kiện** khỏi việc **biến đổi giá trị**. `Consumer<T>` phù hợp cho thao tác có tác dụng phụ được công khai như gửi kết quả đến một sink hoặc in ra.

```java
Function<String, Integer> parse = Integer::parseInt;
UnaryOperator<String> trim = String::trim;
Predicate<Integer> positive = n -> n > 0;
Consumer<String> print = System.out::println;
BiFunction<Integer, Integer, Integer> add = Integer::sum;
```

Đây là đoạn minh họa cần `import java.util.function.*;`. Chọn interface theo ý nghĩa API trước; đừng ép mọi lambda thành `Function` chỉ vì nó là kiểu linh hoạt.

## 8. Chuyên biệt hóa cho kiểu nguyên thủy để giảm boxing

`Function<T, R>` dùng các **kiểu tham chiếu**, nên phép biến đổi số có thể cần boxing/unboxing khi phối hợp `int`, `long`, `double`.

Những interface quan trọng vẫn còn dùng rộng rãi:

- `IntFunction<R>`: `R apply(int value)` — input `int`, output object.
- `ToIntFunction<T>`: `int applyAsInt(T value)` — input object, output `int`.
- `IntUnaryOperator`: `int applyAsInt(int operand)` — input và output `int`.
- `IntToLongFunction`, `LongToDoubleFunction` và các dạng tương tự khi cần chuyển giữa các primitive.

Ví dụ tính tổng độ dài các chuỗi mà không cần tạo Stream<Integer> trung gian:

```java
int totalLength = names.stream()
        .mapToInt(String::length)
        .sum();
```

Đây là đoạn minh họa cần một `List<String> names`. `mapToInt` nhận `ToIntFunction<? super String>`, trả về `IntStream` rồi dùng `sum()`. Với dữ liệu nhỏ, sự rõ ràng là ưu tiên; với pipeline tính toán lớn, chuyên biệt hóa primitive còn có thể giảm lượng object trung gian.

## 9. Dữ liệu null, ngoại lệ và hợp đồng biến đổi

`Function` không tự động kiểm tra `null` hoặc bắt lỗi. Lambda do bạn cung cấp có thể ném exception và có thể trả `null` tùy hợp đồng:

```java
Function<String, Integer> parse = Integer::parseInt;
int number = parse.apply("100"); // hợp lệ
// parse.apply("abc"); // NumberFormatException
// parse.apply(null);  // NumberFormatException
```

Đây là đoạn minh họa; hai dòng comment chỉ ra tình huống lỗi, không được thực thi. Với dữ liệu đến từ người dùng, có thể thiết kế phương thức parse riêng để phân biệt thành công/thất bại thay vì bất ngờ ném lỗi sâu trong pipeline.

```java
static Optional<Integer> tryParseInt(String input) {
    if (input == null) {
        return Optional.empty();
    }
    try {
        return Optional.of(Integer.parseInt(input.trim()));
    } catch (NumberFormatException ex) {
        return Optional.empty();
    }
}
```

Đây là **một phương thức minh họa**, cần `import java.util.Optional;` và đặt trong class. Hành vi này hợp lý khi “không phải số nguyên hợp lệ” được xem là dữ liệu vắng mặt. Nếu ứng dụng cần **báo chính xác nguyên nhân lỗi nhập**, nên trả về một kiểu kết quả có thông tin lỗi hoặc ném ngoại lệ với bối cảnh rõ ràng; không được âm thầm chuyển mọi lỗi bất kỳ thành Optional rỗng.

Đối với `compose` và `andThen`, nếu bước trước ném ngoại lệ, bước sau không thực thi. Nếu bước trước trả `null` và bước sau không chấp nhận `null`, pipeline có thể phát sinh `NullPointerException`; các phương thức ghép **không** có cơ chế tự lọc `null`. Khi contract yêu cầu giá trị non-null, hãy xác nhận đầu vào hoặc dùng `Objects.requireNonNull` ở ranh giới thích hợp.

Các hàm `java.util.function.Function` chuẩn không khai báo checked exception trong `apply`. Vì vậy, lambda gọi một API ném checked exception phải bắt lỗi hoặc chuyển logic sang abstraction đã được thiết kế cho loại lỗi đó; đừng nuốt ngoại lệ hoặc bọc tùy tiện chỉ để viết một dòng lambda.

### Tác dụng phụ làm giảm khả năng kết hợp

Để các bước `compose`, `andThen` và `Stream.map` đáng tin cậy, hãy ưu tiên những phép biến đổi **không sửa nguồn và không phụ thuộc mutable state bên ngoài**:

```java
// NÊN: biến đổi giá trị, không sửa đầu vào.
Function<String, String> normalized = String::trim;

// CẦN CÂN NHẮC: cập nhật dữ liệu ngoài rồi trả kết quả.
List<String> audit = new ArrayList<>();
Function<String, String> hiddenWrite = s -> {
    audit.add(s);
    return s.trim();
};
```

Đây là minh họa cần `java.util.List`, `java.util.ArrayList` và `Function`. `audit` được lambda capture hợp lệ khi biến tham chiếu effectively final, nhưng danh sách vẫn mutable. Nếu dùng trong parallel Stream, việc sửa `ArrayList` dùng chung không an toàn; ngoài ra, Stream có thể xử lý ngắn mạch nên **số lần chạy mapper không phải một cơ chế audit đáng tin**.

Tách chuyển đổi dữ liệu khỏi ghi log, lưu database hoặc gửi sự kiện. Với thao tác có tác dụng phụ, dùng một bước riêng có contract lỗi, retry và concurrency rõ ràng.

## 10. Ví dụ hoàn chỉnh: áp dụng, ghép hàm và map dữ liệu

Chương trình dưới đây minh họa đủ `apply`, `compose`, `andThen`, `identity`, chuyển đổi dữ liệu Stream và Optional. Các giá trị đầu vào được cố định để stdout có thể kiểm chứng.

Lưu toàn bộ vào **FunctionTransformationDemo.java**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.function.Function;
import java.util.stream.Collectors;

public class FunctionTransformationDemo {

    static final class Order {
        final String customer;
        final int amount;

        Order(String customer, int amount) {
            this.customer = customer;
            this.amount = amount;
        }
    }

    public static void main(String[] args) {
        Function<String, String> trim = String::trim;
        Function<String, Integer> length = String::length;

        Function<String, Integer> trimThenLength =
                trim.andThen(length);
        Function<String, Integer> lengthAfterTrim =
                length.compose(trim);

        System.out.println(trimThenLength.apply("  Java  "));
        System.out.println(lengthAfterTrim.apply("  Java  "));

        Function<Integer, Integer> twice = n -> n * 2;
        Function<Integer, Integer> plusThree = n -> n + 3;

        System.out.println(twice.andThen(plusThree).apply(4));
        System.out.println(twice.compose(plusThree).apply(4));

        Function<String, String> unchanged = Function.identity();
        System.out.println(unchanged.apply("same"));

        Function<String, String> uppercase =
                text -> text.toUpperCase(Locale.ROOT);

        List<String> names = Arrays.asList(
                "  An  ", " Binh ", "Chi"
        );

        List<String> normalized = names.stream()
                .map(trim)
                .map(uppercase)
                .collect(Collectors.toList());

        System.out.println(normalized);

        Function<String, Integer> parse = Integer::parseInt;
        System.out.println(trim.andThen(parse).apply(" 42 "));

        List<Order> orders = Arrays.asList(
                new Order("An", 100),
                new Order("Binh", 80)
        );

        Function<Order, String> summary =
                order -> order.customer + ":" + order.amount;

        System.out.println(orders.stream()
                .map(summary)
                .collect(Collectors.joining(", ")));

        int optionalLength = Optional.of("  An  ")
                .map(trim)
                .map(length)
                .orElse(0);

        System.out.println(optionalLength);
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac FunctionTransformationDemo.java
java FunctionTransformationDemo
```

**Kết quả chuẩn (stdout):**

```text
4
4
11
14
same
[AN, BINH, CHI]
42
An:100, Binh:80
2
```

Diễn giải theo thứ tự:

1. `trim.andThen(length)` và `length.compose(trim)` cùng biến `"  Java  "` thành `"Java"` rồi tính `4`.
2. `twice.andThen(plusThree)` thực hiện `4 * 2 + 3 = 11`; `twice.compose(plusThree)` thực hiện `(4 + 3) * 2 = 14`.
3. `Function.identity()` trả lại `"same"`.
4. Hai bước `Stream.map` chuẩn hóa tên và chuyển chữ hoa bằng `Locale.ROOT`. `Collectors.toList()` thu thập thành danh sách; thứ tự của nguồn `List` được bảo toàn trong kết quả collector này.
5. `trim.andThen(parse)` biến `" 42 "` thành số `42`.
6. `summary` chuyển từng `Order` thành chuỗi tên và số tiền; `Collectors.joining(", ")` nối những chuỗi đó.
7. `Optional.map(trim).map(length)` xử lý giá trị hiện diện `"  An  "`, kết quả `2`; nếu Optional rỗng, mapper sẽ không chạy và `orElse(0)` trả `0`.

Tất cả API ở ví dụ đều có từ Java 8 và tiếp tục có sẵn trên những JDK hiện đại. Ví dụ chủ ý không thực hiện I/O, mạng hoặc mutation ngoài pipeline để kết quả dễ kiểm chứng.

## 11. Lỗi thường gặp và cách sửa

### Nhầm thứ tự compose và andThen

```java
Function<Integer, Integer> f = n -> n * 2;
Function<Integer, Integer> g = n -> n + 3;

// f.andThen(g): g(f(4)) = 11
// f.compose(g): f(g(4)) = 14
```

Đây là ví dụ minh họa. Hãy đọc thành hai câu khác nhau và kiểm tra thứ tự bằng test có kết quả phân biệt.

### Nhầm Function với Consumer

```java
// SAI: println trả void, nhưng Function cần kết quả R.
// Function<String, String> invalid = s -> System.out.println(s);

// ĐÚNG: hành động không trả về giá trị.
Consumer<String> print = System.out::println;

// ĐÚNG: phép biến đổi trả về một giá trị.
Function<String, String> normalized = String::trim;
```

Đây là minh họa; các khai báo hợp lệ cần import `java.util.function.*;`. Khi thao tác chỉ tạo tác dụng phụ, chọn `Consumer` hoặc phương thức hành động có tên thay vì ngụy trang nó thành `Function`.

### Đoán sai cách xử lý null

```java
Function<String, Integer> length = String::length;
// length.apply(null) sẽ ném NullPointerException.
```

`Function` không “null-safe” theo mặc định. Xác định chính sách chấp nhận, từ chối hoặc chuyển `null` ở ranh giới API. Với dữ liệu có thể vắng mặt, `Optional.map` có thể diễn đạt cách xử lý phù hợp.

### Nghĩ identity là copy hoặc immutable

```java
Function<List<String>, List<String>> sameList = Function.identity();
```

Đây là minh họa; cần `List` và `Function`. `sameList.apply(list)` trả về cùng tham chiếu `list`. Nếu muốn tạo bản sao, phải có phép sao chép cụ thể, ví dụ `new ArrayList<>(list)`, đồng thời hiểu đó chỉ là bản sao nông.

### Sử dụng map cho tác dụng phụ

```java
// KHÔNG NÊN: ghi vào danh sách khác bên trong map.
List<String> collected = new ArrayList<>();
names.stream()
     .map(name -> {
         collected.add(name); 
         return name.trim();
     })
     .count();
```

Đây là ví dụ phản diện, không phải chương trình chạy độc lập. Ngoài rủi ro trạng thái chia sẻ, việc dùng `count()` có thể làm các thao tác trung gian không chạy nếu runtime tối ưu hóa trên nguồn biết kích thước. Không có gì bảo đảm `collected` sẽ có số phần tử như mong đợi. Muốn tạo danh sách kết quả, dùng `map(...).collect(Collectors.toList())`. Muốn audit, tạo một bước ghi rõ ràng bên ngoài pipeline.

### Ép Function thành một lambda quá dài

Nếu lambda kiểm tra, truy vấn, biến đổi, format, ghi log rồi xử lý lỗi trong cùng body, hãy tách thành những phương thức nhỏ với contract cụ thể. Ghép bằng `andThen` chỉ khi từng bước có ý nghĩa và cùng mô hình dữ liệu; đừng biến chuỗi hàm thành “ẩn thuật” khó debug. Sự rõ ràng quan trọng hơn số dòng.

## 12. Checklist thiết kế và luyện tập

Trước khi đưa `Function<T,R>` vào code production, kiểm tra:

1. **Kiểu:** `T` và `R` biểu diễn đầu vào/đầu ra thực tế; target type có phù hợp không?
2. **Ý định:** tên hàm, lambda hoặc method reference có nêu phép biến đổi rõ ràng không?
3. **Thứ tự:** `compose` và `andThen` có áp dụng theo đúng ý nghĩa nghiệp vụ không?
4. **Thiếu dữ liệu:** xử lý `null`, giá trị không hợp lệ và ngoại lệ có chính sách rõ không?
5. **Tác dụng phụ:** mapper có sửa trạng thái ngoài, gây I/O hoặc dựa vào số lần gọi trong Stream không?
6. **Hiệu năng:** với lượng dữ liệu số lớn, `ToIntFunction`, `IntUnaryOperator` hoặc `mapToInt` có phù hợp hơn boxing không?
7. **Kiểm thử:** có test cho đầu vào bình thường, rỗng, bất thường và cả thứ tự ghép hàm không?

**Bài tập 1.** Tạo `Function<String,String> trim` và `Function<String,Integer> length`. Dùng `andThen` và `compose` để cùng tính chiều dài của `"  Lambda  "`. Dự kiến cả hai trả `6`.

**Bài tập 2.** Tạo `Function<Integer,Integer> square` và `Function<Integer,Integer> minusOne`. Với đầu vào `3`, xác định giá trị của `square.andThen(minusOne).apply(3)` và `square.compose(minusOne).apply(3)`. Đáp án: `8` và `4`.

**Bài tập 3.** Cho danh sách `List<String>` gồm các chuỗi có khoảng trắng. Dùng `map(String::trim)` rồi `map(String::length)` lấy danh sách độ dài. Sau đó dùng `mapToInt(String::length).sum()` để tính tổng; giải thích ý nghĩa của `ToIntFunction`.

**Bài tập 4.** Một API nhận `Function<String,Integer>` để đọc số nguyên. Hãy đề xuất cách xử lý dữ liệu nhập sai khác nhau cho hai yêu cầu: (a) “không đọc được coi như thiếu” và (b) “phải báo lỗi chi tiết”. Giải thích vì sao không nên bắt mọi `Exception` và trả `0`.

**Bài tập 5.** Sửa một `stream.map(...)` vừa tính nhãn vừa ghi danh sách audit bên ngoài thành hai bước: tạo dữ liệu đầu ra bằng một phép biến đổi, sau đó ghi audit bằng một thao tác có chính sách lỗi rõ ràng.

### Tài liệu chuẩn

- [Java SE 25 — Function<T,R>](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Function.html)
- [Java SE 25 — package java.util.function](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/package-summary.html)
- [Java SE 25 — Stream.map](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html#map(java.util.function.Function))
- [Java SE 25 — Optional.map](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html#map(java.util.function.Function))
- [Java SE 25 — Collectors](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html)
