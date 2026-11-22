# `Function<T, R>`: biến đổi một đầu vào thành kết quả trong Java

## 1. Ý tưởng và trường hợp sử dụng

Trong Java, `java.util.function.Function<T, R>` biểu diễn **một phép biến đổi**: nhận **một giá trị kiểu `T`**, trả về **một giá trị kiểu `R`**. Đây là *functional interface* có một phương thức trừu tượng duy nhất là `R apply(T input)`. Ta có thể truyền hàm như một giá trị, lưu vào biến, đưa vào phương thức khác hoặc kết hợp nhiều hàm để tạo pipeline.

Ví dụ:

- Nhận `String` là tên người dùng rồi trả về `String` đã chuẩn hóa.
- Nhận `Order` rồi trả về `BigDecimal` là tổng tiền đơn hàng.
- Nhận `Order` rồi trả về `OrderView` dành cho hiển thị.
- Nhận `String` rồi trả về `Integer` là độ dài chuỗi hoặc số đã phân tích.
- Truyền phép biến đổi vào `Stream.map(...)`, `Optional.map(...)` hoặc một hàm tiện ích có thể tái sử dụng.

Có thể hình dung:

```text
T (dữ liệu vào) ──[ Function<T, R> / apply ]──> R (kết quả)
Order            ──[ tính tổng tiền ]─────────> BigDecimal
String           ──[ chuẩn hóa mã ]───────────> String
Order            ──[ dựng dữ liệu hiển thị ]──> OrderView
```

**Phân biệt ba thao tác:** `filter` quyết định **giữ hay bỏ** phần tử theo `Predicate<T>`; `map` dùng `Function<T,R>` để **chuyển một phần tử thành một kết quả**; `forEach` thường dùng `Consumer<T>` để thực hiện một hành động không trả về giá trị. Việc `Function` nhận một đầu vào không có nghĩa mọi pipeline đều phải giữ nguyên kiểu dữ liệu: `T` và `R` có thể khác nhau.

## 2. Đọc chữ ký kiểu `Function<T, R>`

`Function` nằm trong package `java.util.function`:

```java
import java.util.function.Function;

Function<String, Integer> length = text -> text.length();
int size = length.apply("Java"); // 4
```

Đoạn trên là mã đặt trong một phương thức hoặc trong `jshell`. Giải nghĩa:

| Thành phần | Ý nghĩa |
| --- | --- |
| `T` | Kiểu đầu vào (*input*) của hàm |
| `R` | Kiểu đầu ra (*result*) của hàm |
| `apply(T t)` | Thực thi phép biến đổi; trả kết quả kiểu `R` |
| `text -> text.length()` | Lambda biểu diễn phép biến đổi `String → Integer` |
| `Function<String, Integer>` | Hợp đồng kiểu giúp compiler phát hiện việc trả sai kiểu |
| `Function<String, String>` | Biến đổi một chuỗi thành chuỗi khác; `T` và `R` có thể cùng kiểu |

Khi viết `Function<String, Integer> length`, giá trị trả về của `apply` có kiểu `Integer`. Ví dụ gán vào biến `int` sử dụng **unboxing** tự động. Generic không nhận kiểu nguyên thủy trực tiếp, nên `Function<String, int>` là sai cú pháp; dùng `Integer` hoặc các interface chuyên biệt sẽ được giới thiệu bên dưới.

### `@FunctionalInterface` và lambda

Về mặt ý tưởng, `Function` tương đương một interface có hợp đồng chính như sau:

```java
@FunctionalInterface
interface Converter<T, R> {
    R apply(T value);
}
```

Đây là **interface tự định nghĩa để minh họa**, không cần tạo khi đã dùng `java.util.function.Function`. Functional interface có **một phương thức trừu tượng**, do đó compiler có thể chuyển lambda hoặc method reference thành một instance đáp ứng interface đó. Các phương thức `default`/`static` của interface không làm mất tính chất functional interface.

Ví dụ cùng một phép biến đổi với ba cách biểu diễn:

```java
Function<String, Integer> viaLambda = s -> s.length();
Function<String, Integer> viaReference = String::length;
Function<String, Integer> viaAnonymous = new Function<>() {
    @Override
    public Integer apply(String s) {
        return s.length();
    }
};
```

Ba cách đều trả `4` khi gọi `apply("Java")`. Lambda và method reference thường gọn, diễn đạt **mục đích chuyển đổi** rõ hơn một lớp vô danh có nhiều cú pháp bao quanh.

## 3. Bốn thao tác cần nắm: `apply`, `andThen`, `compose`, `identity`

| Thao tác | Tác dụng | Thứ tự thực hiện |
| --- | --- | --- |
| `f.apply(x)` | Biến đổi trực tiếp đầu vào | Chạy `f` |
| `f.andThen(g)` | Tạo hàm ghép đầu ra của `f` vào đầu vào của `g` | `g(f(x))`: **f trước, g sau** |
| `f.compose(g)` | Tạo hàm cho `g` xử lý đầu vào trước khi gọi `f` | `f(g(x))`: **g trước, f sau** |
| `Function.identity()` | Tạo hàm trả đúng giá trị đầu vào | `x -> x` |

Giả sử muốn chuẩn hóa mã sản phẩm bằng cách bỏ khoảng trắng đầu/cuối rồi đổi thành chữ hoa theo `Locale.ROOT`:

```java
Function<String, String> trim = String::trim;
Function<String, String> upper =
        value -> value.toUpperCase(java.util.Locale.ROOT);

Function<String, String> firstTrimThenUpper = trim.andThen(upper);
Function<String, String> upperAfterTrim = upper.compose(trim);

System.out.println(firstTrimThenUpper.apply("  book  ")); // BOOK
System.out.println(upperAfterTrim.apply("  book  "));     // BOOK
```

Hai hàm ghép trên tương đương vì đều có thứ tự **trim → upper**. Ngược lại, `trim.compose(upper)` thực hiện **upper → trim**. Với phép đổi chữ hoa và loại khoảng trắng, hai thứ tự có thể cho cùng kết quả ở ví dụ đơn giản; với những phép biến đổi phụ thuộc thứ tự (như “nhân đôi” và “cộng ba”), kết quả có thể khác nhau rõ rệt.

Ví dụ thể hiện tính **không giao hoán**:

```java
Function<Integer, Integer> doubleIt = x -> x * 2;
Function<Integer, Integer> plusThree = x -> x + 3;

System.out.println(doubleIt.andThen(plusThree).apply(4)); // 11
System.out.println(doubleIt.compose(plusThree).apply(4)); // 14
```

- `andThen`: `4 × 2 + 3 = 11`.
- `compose`: `(4 + 3) × 2 = 14`.

Ở đây `andThen`/`compose` **trả về một `Function` mới**, chúng không lập tức chạy trên dữ liệu. Phép biến đổi chỉ chạy khi gọi `apply` hoặc khi một API khác gọi hàm đó.

### Điều kiện kiểu khi ghép hàm

Để `f.andThen(g)` hợp lệ, **kết quả của `f` phải dùng được làm đầu vào của `g`**. Ví dụ:

```java
Function<String, Integer> parse = Integer::parseInt;
Function<Integer, String> label = n -> "Quantity = " + n;
Function<String, String> parseThenLabel = parse.andThen(label);
System.out.println(parseThenLabel.apply("7")); // Quantity = 7
```

`String → Integer → String` hợp lệ. Nếu cố ghép `parse.andThen(String::trim)`, compiler không thể biến `Integer` thành đầu vào `String` cho `trim`. Quy tắc kiểm tra kiểu của generic giúp phát hiện lỗi khi biên dịch.

Tham số `before`/`after` truyền cho `compose`/`andThen` không được `null`; nếu `null`, việc tạo hàm ghép có thể phát sinh `NullPointerException`. Riêng đầu vào của `apply` có chấp nhận `null` hay không **phụ thuộc triển khai hàm**: ví dụ `String::length` sẽ lỗi nếu nhận `null`.

### `identity()` có ý nghĩa gì?

`Function.identity()` tạo phép ánh xạ giữ nguyên giá trị:

```java
Function<String, String> keep = Function.identity();
System.out.println(keep.apply("A01")); // A01
```

Nó thường dùng khi API yêu cầu một mapper nhưng muốn lấy nguyên phần tử. Ví dụ `Collectors.toMap(Order::id, Function.identity())` (với `Order` là kiểu của bài toán và mã đơn không trùng) tạo map `id → chính Order`. **Identity không sao chép object hoặc làm object bất biến**: với kiểu tham chiếu, nó trả về đúng tham chiếu được truyền vào.

## 4. Ví dụ Java 17 hoàn chỉnh: từ đơn hàng đến dữ liệu hiển thị

Bài toán: có các đơn hàng, mỗi đơn gồm một số dòng sản phẩm. Ta muốn định nghĩa các phép biến đổi nhỏ, sau đó **kết hợp chúng** để xây chuỗi kết quả hiển thị. Các phép biến đổi không sửa dữ liệu đầu vào.

Tạo tệp **`FunctionTransformDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.Locale;
import java.util.function.Function;

public class FunctionTransformDemo {
    record Line(String sku, int quantity, BigDecimal unitPrice) {}

    record Order(String id, List<Line> lines) {
        Order {
            lines = List.copyOf(lines);
        }
    }

    record OrderView(String id, BigDecimal total) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A01", List.of(
                        new Line("BOOK", 2, new BigDecimal("120000")),
                        new Line("PEN", 3, new BigDecimal("10000"))
                )),
                new Order("A02", List.of(
                        new Line("BAG", 1, new BigDecimal("200000"))
                )),
                new Order("A03", List.of(
                        new Line("PEN", 5, new BigDecimal("10000"))
                ))
        );

        // Mỗi phép biến đổi diễn đạt đúng một việc.
        Function<Line, BigDecimal> lineAmount =
                line -> line.unitPrice()
                        .multiply(BigDecimal.valueOf(line.quantity()));

        Function<Order, BigDecimal> orderTotal =
                order -> order.lines().stream()
                        .map(lineAmount)
                        .reduce(BigDecimal.ZERO, BigDecimal::add);

        Function<Order, OrderView> toView =
                order -> new OrderView(order.id(), orderTotal.apply(order));

        Function<OrderView, String> format =
                view -> view.id() + " = " + view.total().toPlainString();

        // Order -> OrderView -> String.
        Function<Order, String> show = toView.andThen(format);

        System.out.println("Order lines:");
        orders.stream()
                .map(show)
                .forEach(System.out::println);

        BigDecimal revenue = orders.stream()
                .map(orderTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println("Total = " + revenue.toPlainString());

        Function<String, String> trim = String::trim;
        Function<String, String> upper =
                value -> value.toUpperCase(Locale.ROOT);

        Function<String, String> normalize = trim.andThen(upper);
        Function<String, String> sameByCompose = upper.compose(trim);
        Function<String, Integer> normalizedLength =
                normalize.andThen(String::length);

        System.out.println("Code = " + normalize.apply("  book  "));
        System.out.println("Length = "
                + normalizedLength.apply("  book  "));
        System.out.println("Compose = "
                + sameByCompose.apply("  book  "));

        Function<String, Integer> parse = Integer::parseInt;
        Function<Integer, String> label = n -> "Quantity = " + n;
        System.out.println(parse.andThen(label).apply("7"));

        Function<Order, Order> identity = Function.identity();
        System.out.println("Same object = "
                + (identity.apply(orders.get(0)) == orders.get(0)));
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac --release 17 FunctionTransformDemo.java
java FunctionTransformDemo
```

**Stdout chính xác**:

```text
Order lines:
A01 = 270000
A02 = 200000
A03 = 50000
Total = 520000
Code = BOOK
Length = 4
Compose = BOOK
Quantity = 7
Same object = true
```

Kiểm tra số học:

- A01: `2 × 120000 + 3 × 10000 = 270000`.
- A02: `1 × 200000 = 200000`.
- A03: `5 × 10000 = 50000`.
- Tổng: `270000 + 200000 + 50000 = 520000`.

`List.of` giữ thứ tự phần tử theo thứ tự viết trong mẫu; `orders.stream()` là stream có thứ tự, và `forEach` ở stream tuần tự này in theo thứ tự duyệt. Nếu chuyển ví dụ sang `parallelStream().forEach(...)`, thứ tự in không còn được đảm bảo; muốn giữ *encounter order*, dùng `forEachOrdered` hoặc thu thập trước khi in.

## 5. Bóc tách các phép biến đổi trong ví dụ

### `Function<Line, BigDecimal>` — một dòng hàng thành thành tiền

```java
Function<Line, BigDecimal> lineAmount =
        line -> line.unitPrice().multiply(
                BigDecimal.valueOf(line.quantity()));
```

Đầu vào là `Line`; đầu ra là `BigDecimal`. Hàm chỉ đọc các component và tạo một đối tượng số tiền mới. Vì đang xử lý tiền, `BigDecimal` thích hợp hơn `double` để tránh sai số biểu diễn số thập phân nhị phân. Trong sản phẩm thật cần kiểm tra số lượng, đơn giá, thuế, phí, làm tròn và quy tắc hoàn trả theo nghiệp vụ.

### `Function<Order, BigDecimal>` — toàn bộ đơn thành tổng tiền

```java
Function<Order, BigDecimal> orderTotal =
        order -> order.lines().stream()
                .map(lineAmount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
```

`map(lineAmount)` biến mỗi `Line` thành `BigDecimal`. `reduce` cộng các thành tiền. Với đơn có danh sách dòng hàng rỗng, `reduce` bắt đầu và kết thúc ở `BigDecimal.ZERO`. Mọi phép tổng hợp nằm bên trong một hàm `Order → BigDecimal`, nên cùng một chức năng có thể dùng cho nhiều mục đích: dựng `OrderView` hoặc tính doanh thu.

### `Function<Order, OrderView>` — tạo giá trị hiển thị mới

```java
Function<Order, OrderView> toView =
        order -> new OrderView(order.id(), orderTotal.apply(order));
```

Kiểu đầu ra **khác** đầu vào. `OrderView` là một record lưu mã đơn và tổng tiền, không cần sửa `Order` hay thêm trường “cachedTotal” vào domain object. Trong ví dụ, `Order` sao chép cấu trúc danh sách bằng `List.copyOf` để tránh chỉnh sửa ngoài ý muốn; component `Line` là record với các kiểu dữ liệu bất biến.

### `andThen` — kết hợp phép chuyển đổi và định dạng

```java
Function<Order, String> show = toView.andThen(format);
String first = show.apply(orders.get(0)); // "A01 = 270000"
```

`toView` tạo `OrderView`, `format` nhận `OrderView` và tạo chuỗi. Nhờ ghép hàm, mã gọi không cần tự thực hiện hai thao tác lặp đi lặp lại. `show.apply(order)` có ý nghĩa tương đương `format.apply(toView.apply(order))`.

### `Stream.map` — áp dụng Function cho từng phần tử

```java
orders.stream()
        .map(show)
        .forEach(System.out::println);
```

`Stream.map` có dạng khái niệm `Stream<T> → Stream<R>`; với `orders` ở trên, `T = Order` và `R = String`. Mỗi phần tử vào tạo một phần tử ra trong `map`, kể cả khi giá trị ra có thể là `null` (nếu mapper trả về `null`; những bước tiếp theo có thể không hỗ trợ nó).

`map` là **intermediate operation** và thực thi lười: không duyệt và biến đổi dữ liệu cho tới khi có terminal operation như `toList`, `reduce`, `collect` hoặc `forEach`. Stream chỉ nên được tiêu thụ một lần; ví dụ chủ động gọi `orders.stream()` mới cho báo cáo doanh thu.

## 6. So sánh `Function` với các functional interface gần nhất

Tất cả nằm trong hoặc liên quan tới package `java.util.function`:

| Interface | Hợp đồng cốt lõi | Khi nên dùng |
| --- | --- | --- |
| `Function<T,R>` | `R apply(T)` | Chuyển **một đầu vào** thành **một kết quả** |
| `Predicate<T>` | `boolean test(T)` | Quyết định đúng/sai, thường truyền vào `filter` |
| `Consumer<T>` | `void accept(T)` | Nhận một giá trị và thực hiện hành động, ví dụ in/log |
| `Supplier<T>` | `T get()` | Cung cấp giá trị **không cần đầu vào** |
| `BiFunction<T,U,R>` | `R apply(T,U)` | Hai đầu vào để tính một kết quả |
| `UnaryOperator<T>` | Kế thừa `Function<T,T>` | Phép biến đổi giữ nguyên **kiểu** |
| `BinaryOperator<T>` | Kế thừa `BiFunction<T,T,T>` | Gộp hai giá trị cùng kiểu thành giá trị cùng kiểu |

Ví dụ minh họa **không phải chương trình độc lập**:

```java
Predicate<String> notBlank = s -> !s.isBlank();
Consumer<String> printer = System.out::println;
Supplier<String> defaultCode = () -> "UNKNOWN";
BiFunction<Integer, Integer, Integer> sum = Integer::sum;
UnaryOperator<String> trim = String::trim;
```

Các khai báo này cần `import java.util.function.*;` hoặc import từng interface trong một class/phương thức. Khi cần giá trị `boolean` có ý nghĩa điều kiện, `Predicate<T>` truyền đạt ý định rõ hơn `Function<T, Boolean>`. Khi cần side effect mà không có kết quả, `Consumer<T>` rõ ràng hơn một `Function<T,Void>` phải trả `null`.

Với đầu vào/đầu ra nguyên thủy và lượng dữ liệu lớn, có thể dùng các interface chuyên biệt để giảm boxing/unboxing:

- `IntFunction<R>`: nhận `int`, trả `R`.
- `ToIntFunction<T>`: nhận `T`, trả `int`; chẳng hạn `String::length`.
- `IntUnaryOperator`: nhận `int` và trả `int`.
- `DoubleFunction<R>`, `ToDoubleFunction<T>` và những biến thể tương tự cho `double`.

## 7. Khi nào dùng lambda, khi nào dùng method reference?

Hai cách có thể diễn tả cùng phép chuyển đổi:

```java
Function<String, Integer> length1 = text -> text.length();
Function<String, Integer> length2 = String::length;

Function<String, String> trim1 = text -> text.trim();
Function<String, String> trim2 = String::trim;
```

Dùng **method reference** khi nó biểu đạt thẳng một phương thức đã có, rõ mục đích và khớp kiểu. Dùng **lambda** khi cần kết hợp nhiều thao tác, hằng số, điều kiện hoặc logic nghiệp vụ:

```java
Function<String, String> normalize =
        text -> text.trim().toUpperCase(java.util.Locale.ROOT);
```

Java không cho tự động coi mọi phương thức là `Function` khi ngữ cảnh kiểu chưa rõ. Ví dụ `String::length` cần một **target type** tương thích như `Function<String,Integer>` hoặc `ToIntFunction<String>`; lambda/method reference có thể dùng trực tiếp tại lời gọi `map(...)` nhờ compiler suy ra kiểu từ API đó.

## 8. Tính “functional” không tự đảm bảo hàm thuần

`Function<T,R>` chỉ định kiểu đầu vào và đầu ra, **không bắt buộc** triển khai phải là hàm thuần (*pure function*). Một lambda có thể sửa biến toàn cục, ghi file, truy vấn database hoặc trả kết quả dựa trên thời gian hiện tại:

```java
// Phản ví dụ về side effect; đặt trong class phù hợp.
java.util.concurrent.atomic.AtomicInteger counter =
        new java.util.concurrent.atomic.AtomicInteger();

Function<String, String> addSerial =
        code -> code + "-" + counter.incrementAndGet();
```

Hàm `addSerial.apply("BOOK")` có thể cho kết quả khác nhau ở các lần gọi vì phụ thuộc trạng thái ngoài đầu vào. `AtomicInteger` bảo vệ phép tăng đơn lẻ khỏi data race, nhưng **không** biến hàm thành thuần và không tự bảo đảm một quy tắc nghiệp vụ nhiều bước.

Trong `Stream.map(...)`, ưu tiên các hàm chỉ biến đổi dữ liệu:

```java
Function<String, String> clean =
        text -> text.trim().toLowerCase(java.util.Locale.ROOT);

List<String> codes = List.of(" BOOK ", " PEN ")
        .stream()
        .map(clean)
        .toList();
```

`codes` chứa `["book", "pen"]` và danh sách đầu vào không bị sửa. Tránh dùng `map` để vừa biến đổi vừa tự cập nhật một `ArrayList` dùng chung; hãy để terminal operation `toList`/`collect` quản lý việc tập hợp kết quả. Những yêu cầu có side effect thật sự như ghi database nên đặt ở ranh giới điều phối để dễ hiểu và kiểm thử.

## 9. Sử dụng `Function` ngoài `Stream.map`

### `Optional.map`

Với một giá trị có thể vắng mặt:

```java
java.util.Optional<String> raw = java.util.Optional.of("  book  ");
String code = raw
        .map(String::trim)
        .map(s -> s.toUpperCase(java.util.Locale.ROOT))
        .orElse("UNKNOWN");
// code == "BOOK"
```

`Optional.map` nhận một `Function` để biến đổi giá trị *nếu có*. Nếu mapper trả `null`, `Optional.map` tạo `Optional.empty()`. Nếu cần một hàm trả `Optional<U>`, dùng `flatMap` để tránh lồng `Optional<Optional<U>>`.

### `Map.computeIfAbsent`

Khi muốn tính giá trị cho một khóa **chỉ nếu chưa có mapping phù hợp**:

```java
Map<String, Integer> lengths = new java.util.HashMap<>();
int result = lengths.computeIfAbsent("BOOK", String::length);
// result == 4; lengths.get("BOOK") == 4
```

Ví dụ cần `import java.util.Map;` nếu không dùng tên đầy đủ. `computeIfAbsent` nhận `Function<? super K,? extends V>`, nên `String::length` hợp lệ khi `K=String`, `V=Integer`. Lưu ý: thao tác này **cập nhật Map**, khác với `Stream.map`; nên xem xét quy tắc đồng thời và hành vi của implementation khi nhiều thread cùng truy cập. Trong ví dụ, `HashMap` được sử dụng một luồng; nếu nhiều thread ghi chung, cần loại map/cơ chế đồng bộ phù hợp.

### Truyền phép biến đổi vào phương thức riêng

Một phương thức generic có thể nhận `Function` từ caller, nhờ đó tái sử dụng thuật toán thay vì cố định cách chuyển đổi:

```java
static <T, R> List<R> transform(
        List<T> source, Function<? super T, ? extends R> mapper) {
    return source.stream().map(mapper).toList();
}
```

Đây là **phương thức minh họa** cần đặt trong class và import `List`, `Function`. Khi gọi `transform(List.of(1, 2, 3), x -> "N=" + x)`, đầu ra là `List<String>` chứa `["N=1", "N=2", "N=3"]`. Dùng `? super T` cho đầu vào của mapper và `? extends R` cho đầu ra giúp chấp nhận những hàm có kiểu linh hoạt theo nguyên tắc *producer extends, consumer super* (PECS). Trong pipeline, mapper “tiêu thụ” phần tử `T` và “sản xuất” kết quả `R`.

## 10. Hạn chế và lỗi thường gặp

**Nhầm `apply` với `accept` hoặc `test`.** `Function` dùng `apply` và phải trả giá trị `R`; `Consumer` dùng `accept` và không trả kết quả; `Predicate` dùng `test` trả boolean.

**Ghép hàm sai thứ tự.** `f.andThen(g)` khác `f.compose(g)`. Hãy ghi cụ thể luồng kiểu `T → U → R` trước khi viết, nhất là khi nhiều bước đổi kiểu.

**Ghép hàm không tương thích kiểu.** `Function<String,Integer>` chỉ ghép với hàm nhận kiểu tương thích `Integer` ở phía sau. Compiler từ chối nhiều tổ hợp sai ngay khi biên dịch.

**Hiểu nhầm mapper luôn được chạy.** `Stream.map` thực thi lười và có thể bị short-circuit bởi `findFirst`, `limit`, `anyMatch`, v.v. Không đặt side effect cần chạy đủ số lần trong mapper. Trường hợp pipeline có tối ưu, không nên dựa vào số lần gọi mapper để xác định nghiệp vụ.

**Không xử lý dữ liệu không hợp lệ.** `Integer::parseInt` với `"7"` thành công, nhưng với `"seven"` ném `NumberFormatException`. Với dữ liệu nhập bên ngoài, cân nhắc validate hoặc một hàm chuyển đổi trả kiểu kết quả biểu diễn lỗi như `Optional`/Result type, rồi xử lý tại ranh giới phù hợp.

**Null đầu vào hoặc null trả về.** `Function` không tự động từ chối `null`. `String::trim` lỗi nếu đầu vào là `null`; mapper trả `null` có thể làm bước sau lỗi. Xây rõ hợp đồng null của từng phép biến đổi, ưu tiên xác thực đầu vào. `Optional.map` và `Stream.map` có hành vi khác nhau khi mapper trả null; không suy diễn một quy tắc chung.

**Dùng `Function<T,R>` thay cho mọi loại hàm.** Với điều kiện, hành động, hai đầu vào hoặc biến đổi nguyên thủy, `Predicate`, `Consumer`, `BiFunction`, `ToIntFunction` thường mô tả ý định tốt hơn. Việc dùng đúng interface còn giúp API tự nói lên mục đích.

**Dựa vào biến mutable bên ngoài lambda.** Biến cục bộ được capture phải `final` hoặc *effectively final*, nhưng điều đó không cấm sửa trạng thái bên trong object được tham chiếu. Việc đẩy state ra ngoài lambda có thể khiến kết quả khác nhau giữa các lần chạy hoặc gây race condition trong parallel stream.

**Cho rằng `andThen` tự xử lý exception.** Nếu phép biến đổi đầu tiên ném exception, phép thứ hai không chạy và exception được truyền ra ngoài; cần xử lý theo hợp đồng nghiệp vụ. `Function` không tích hợp kiểu lỗi hay retry tự động.

**Nhầm `identity` là copy.** `Function.identity()` trả chính đối tượng ban đầu, không deep copy, không tạo snapshot và không đảm bảo thread safety nếu đối tượng đó mutable.

## 11. Bài tập áp dụng và đối chiếu

1. Viết `Function<String, String>` biến `"  pen  "` thành `"PEN"` qua hai cách: `trim.andThen(upper)` và `upper.compose(trim)`. Kiểm chứng cả hai cho cùng kết quả.
2. Viết `Function<String,Integer>` chuyển một chuỗi thành số nguyên, sau đó `andThen` với hàm nhân đôi. Với `"7"` phải ra `14`. Thử `"abc"` và giải thích exception.
3. Với chương trình đơn hàng, thay `orders.stream().map(show)` bằng `orders.stream().map(toView).map(format)`. Kết quả stdout của ba dòng đơn phải không đổi; chỉ thay cách tổ chức các phép biến đổi.
4. Viết `Function<Order,Boolean>` kiểm tra tổng tiền lớn hơn `100000`, rồi chuyển sang `Predicate<Order>` và dùng `filter`. Đối với ba đơn mẫu, kết quả giữ lại A01 và A02. Giải thích tại sao `Predicate` thể hiện ý định tốt hơn.
5. Thêm `Function<Order,String>` trả mã đơn; dùng `orders.stream().map(...)` để tạo `List<String>`. Kết quả phải là `["A01", "A02", "A03"]`.
6. Tạo `Function<Integer,Integer>` cộng 3 và nhân 2; kiểm chứng `andThen` trên giá trị `4` cho `14` khi cộng 3 trước rồi nhân 2, còn đảo thứ tự cho `11`.
7. Viết hàm `transform` nhận `List<T>` và `Function<? super T, ? extends R>`; gọi với danh sách số và mapper sang chuỗi, kiểm tra đầu vào không bị sửa và đầu ra có đúng số phần tử.
8. Nêu trường hợp `Function.identity()` phù hợp khi xây `Collectors.toMap`. Nếu hai phần tử có khóa trùng và không cung cấp merge function, điều gì xảy ra?

**Gợi ý tự kiểm tra:** xác định rõ `T` và `R`; đọc phép biến đổi thành câu “nhận một ... trả một ...”; kiểm tra thứ tự `compose`/`andThen`; nêu khi nào `apply` thật sự chạy; tránh side effect trong mapper; thử các trường hợp rỗng, null, lỗi parsing và khóa trùng. Khi làm chủ các bước này, có thể dùng `Function<T,R>` để tổ chức các phép biến đổi rõ ràng, có thể ghép lại và kiểm thử độc lập trong Java.
