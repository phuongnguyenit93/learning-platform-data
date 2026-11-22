# Tham chiếu phương thức static bằng `Type::method` trong Java

## 1. Khái niệm và mục tiêu

**Method reference** (tham chiếu phương thức) là cú pháp dùng `::` để chỉ một phương thức đã có, nhằm cung cấp cách triển khai cho một **functional interface** mà không cần viết lại thân lambda. Khi phương thức được tham chiếu là `static`, hình thức thường gặp là:

```java
TypeName::staticMethodName
```

Ví dụ `Integer::parseInt`, `Math::max`, `Integer::sum` hoặc `MyClass::convert`. Cú pháp `::` **không gọi phương thức ngay**. Java sử dụng ngữ cảnh kiểu đích (target type) để tạo một giá trị functional interface; khi gọi phương thức trừu tượng của interface ấy, phương thức static được tham chiếu mới được thực thi.

Ví dụ ngắn:

```java
import java.util.function.Function;

Function<String, Integer> parse = Integer::parseInt;
int value = parse.apply("42"); // 42
```

`Integer.parseInt("42")` là **lời gọi phương thức** thông thường. `Integer::parseInt` là **tham chiếu phương thức** để làm hàm `String → Integer`. Khi gán vào `Function<String, Integer>`, Java hiểu cần một phương thức nhận một `String` và trả kết quả tương thích với `Integer`; `parseInt(String)` trả `int`, kết quả được boxing thành `Integer` nếu cần.

Bài học tập trung vào cách viết tham chiếu **đến phương thức static**, cách Java ánh xạ tham số và kết quả vào functional interface, áp dụng trong stream và các tình huống dễ nhầm với tham chiếu instance.

## 2. Nhận diện ba thành phần của `Type::method`

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `Type` | Tên lớp hoặc kiểu khai báo phương thức static | `Integer`, `Math`, `OrderFunctions` |
| `::` | Toán tử method reference | `Integer::parseInt` |
| `method` | Tên phương thức, **không** có `()` và danh sách đối số | `parseInt` |
| **Target type** | Functional interface quyết định chữ ký cần ghép | `Function<String,Integer>` |
| **Invocation** | Lời gọi phương thức của functional interface | `parse.apply("42")` |

Hãy so sánh:

```java
int direct = Integer.parseInt("42");            // Gọi ngay, kết quả là 42.
Function<String, Integer> viaLambda = text -> Integer.parseInt(text);
Function<String, Integer> viaReference = Integer::parseInt;
int deferred = viaReference.apply("42");        // Lúc này mới parse.
```

`viaLambda` và `viaReference` đều biểu diễn phép chuyển `String → Integer`. Method reference giúp giảm mã lặp khi lambda **chỉ chuyển tiếp tham số vào một phương thức có sẵn**.

Một method reference có thể làm target cho `Function`, `Predicate`, `Consumer`, `Supplier`, `BiFunction`, `Comparator` hoặc một functional interface tự định nghĩa, nếu kiểu tham số/kiểu trả về tương thích.

> Lưu ý về ký hiệu: `Type::method` **không luôn có nghĩa static**. Ví dụ `String::length` là **tham chiếu phương thức instance không gắn sẵn đối tượng nhận**; `String` ở đây chỉ là kiểu của receiver. Muốn nhận diện dạng static, kiểm tra phương thức được chọn thực sự khai báo `static`.

## 3. Cách ánh xạ tham số và kiểu trả về

Giả sử có phương thức:

```java
static String format(String code, int quantity) {
    return code + " x " + quantity;
}
```

Nếu thuộc lớp `OrderTools`, có thể viết:

```java
BiFunction<String, Integer, String> formatter = OrderTools::format;
String result = formatter.apply("BOOK", 3); // "BOOK x 3"
```

Hai đoạn chỉ **minh họa chữ ký**, cần khai báo `format` bên trong lớp `OrderTools` và import `java.util.function.BiFunction` để biên dịch. Phương thức `format(String,int)` nhận hai tham số; `BiFunction<String,Integer,String>` cũng nhận hai tham số và trả `String`. Java unboxing `Integer` thành `int` khi cần.

Quy tắc tổng quát:

- **Số tham số:** phương thức static nhận những đối số tương ứng với danh sách tham số của phương thức trừu tượng trong target functional interface.
- **Kiểu tham số:** Java xét khả năng chuyển đổi kiểu hợp lệ trong ngữ cảnh lời gọi, gồm boxing/unboxing và generic type inference khi áp dụng.
- **Giá trị trả về:** phương thức static phải trả giá trị tương thích với kết quả target interface; nếu target trả `void`, trong những trường hợp hợp lệ, kết quả của lời gọi có thể bị bỏ qua.
- **Ngoại lệ:** exception được ném từ phương thức tham chiếu không tự được bắt hoặc chuyển đổi. Checked exception phải phù hợp với hợp đồng `throws` của target interface, hoặc được xử lý qua wrapper phù hợp.

Bảng ánh xạ một số trường hợp phổ biến:

| Static method | Target functional interface | Ý nghĩa |
| --- | --- | --- |
| `Integer.parseInt(String)` | `Function<String,Integer>` | Chuyển chuỗi thành số nguyên |
| `Math.abs(int)` | `IntUnaryOperator` | Đổi một `int` thành trị tuyệt đối |
| `Math.max(int,int)` | `IntBinaryOperator` | Lấy số lớn hơn trong hai số nguyên |
| `Integer.sum(int,int)` | `BinaryOperator<Integer>` | Cộng hai `Integer` sau khi unboxing |
| `String.valueOf(int)` | `IntFunction<String>` | Tạo chuỗi từ `int` |
| `System.currentTimeMillis()` | `LongSupplier` | Cung cấp thời gian hiện tại dưới dạng `long` |

`System::currentTimeMillis` là tham chiếu static hợp lệ nhưng kết quả phụ thuộc thời gian, vì thế dùng method reference **không đồng nghĩa** với hàm thuần hoặc kết quả bất biến.

## 4. Chương trình Java 17 hoàn chỉnh: xử lý đơn hàng bằng static method reference

Ta có dữ liệu đơn hàng ban đầu ở dạng chuỗi. Yêu cầu:

1. Biến đổi mỗi `RawOrder` thành `Order` sau khi chuẩn hóa mã/khách và phân tích tiền.
2. Lọc các đơn có số tiền **ít nhất 100000**.
3. Sắp xếp đơn theo số tiền tăng dần, khi bằng nhau theo mã đơn.
4. Chuyển mỗi đơn thành một dòng báo cáo và tính tổng tiền.
5. Minh họa method reference static có một hoặc hai đối số.

Tạo tệp **`StaticReferenceDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.function.IntBinaryOperator;
import java.util.function.Predicate;

public class StaticReferenceDemo {
    record RawOrder(String id, String customer, String amount) {}

    record Order(String id, String customer, BigDecimal amount) {}

    // Một đầu vào RawOrder, một kết quả Order.
    static Order parseOrder(RawOrder raw) {
        return new Order(
                raw.id().trim(),
                raw.customer().trim(),
                new BigDecimal(raw.amount())
        );
    }

    // Một đầu vào Order, một kết quả boolean.
    static boolean isLarge(Order order) {
        return order.amount().compareTo(new BigDecimal("100000")) >= 0;
    }

    // Hai đầu vào Order, một kết quả int cho Comparator.
    static int compareByAmount(Order left, Order right) {
        int byAmount = left.amount().compareTo(right.amount());
        return byAmount != 0
                ? byAmount
                : left.id().compareTo(right.id());
    }

    // Một Order thành chuỗi trình bày.
    static String render(Order order) {
        return order.id()
                + " | " + order.customer()
                + " | " + order.amount().toPlainString();
    }

    // Hai BigDecimal thành tổng BigDecimal.
    static BigDecimal add(BigDecimal left, BigDecimal right) {
        return left.add(right);
    }

    // Hai chuỗi thành một chuỗi.
    static String join(String left, String right) {
        return left + ":" + right;
    }

    public static void main(String[] args) {
        List<RawOrder> rawOrders = List.of(
                new RawOrder(" A01 ", " Lan ", "120000"),
                new RawOrder(" A02 ", " Minh ", "80000"),
                new RawOrder(" A03 ", " Lan ", "200000")
        );

        // Static method references đến các phương thức của chính lớp này.
        Function<RawOrder, Order> parser = StaticReferenceDemo::parseOrder;
        Predicate<Order> large = StaticReferenceDemo::isLarge;
        Comparator<Order> byAmount = StaticReferenceDemo::compareByAmount;
        Function<Order, String> formatter = StaticReferenceDemo::render;
        BinaryOperator<BigDecimal> sum = StaticReferenceDemo::add;
        BiFunction<String, String, String> joiner = StaticReferenceDemo::join;

        List<Order> orders = rawOrders.stream()
                .map(parser)
                .toList();

        System.out.println("All orders:");
        orders.stream()
                .map(formatter)
                .forEach(System.out::println);

        System.out.println("Large orders:");
        orders.stream()
                .filter(large)
                .map(formatter)
                .forEach(System.out::println);

        System.out.println("Sorted ascending:");
        orders.stream()
                .sorted(byAmount)
                .map(formatter)
                .forEach(System.out::println);

        BigDecimal total = orders.stream()
                .map(Order::amount)
                .reduce(BigDecimal.ZERO, sum);
        System.out.println("Total: " + total.toPlainString());

        // Các static method reference có sẵn trong JDK.
        Function<String, Integer> numberParser = Integer::parseInt;
        IntBinaryOperator maximum = Math::max;

        System.out.println("Parsed: " + numberParser.apply("42"));
        System.out.println("Max: " + maximum.applyAsInt(7, 9));
        System.out.println("Label: " + joiner.apply("Lan", "A01"));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 StaticReferenceDemo.java
java StaticReferenceDemo
```

**Stdout của chương trình:**

```text
All orders:
A01 | Lan | 120000
A02 | Minh | 80000
A03 | Lan | 200000
Large orders:
A01 | Lan | 120000
A03 | Lan | 200000
Sorted ascending:
A02 | Minh | 80000
A01 | Lan | 120000
A03 | Lan | 200000
Total: 400000
Parsed: 42
Max: 9
Label: Lan:A01
```

Kiểm tra kết quả:

- `parseOrder` loại khoảng trắng đầu/cuối bằng `trim()`, rồi tạo `BigDecimal` từ chuỗi số. Vì sử dụng dữ liệu số nguyên dạng chuỗi nên `toPlainString()` in `120000`, `80000`, `200000`.
- `isLarge` dùng `compareTo`; `120000` và `200000` thỏa ngưỡng `>= 100000`, còn `80000` thì không.
- `compareByAmount` sắp tăng dần: `80000 → 120000 → 200000`; mã đơn chỉ dùng phá hòa nếu tổng tiền bằng nhau.
- `reduce(BigDecimal.ZERO, sum)` trả `120000 + 80000 + 200000 = 400000`.
- `Integer.parseInt("42")` trả `int 42`, được boxing phù hợp `Function<String,Integer>`.
- `Math.max(7,9)` trả `9`, `join("Lan","A01")` trả `"Lan:A01"`.

Đoạn `.map(Order::amount)` và `System.out::println` trong ví dụ là **method reference instance** để cho thấy pipeline có thể kết hợp nhiều dạng tham chiếu; những tham chiếu **static** được minh họa rõ bằng `StaticReferenceDemo::parseOrder`, `::isLarge`, `::compareByAmount`, `::render`, `::add`, `::join`, `Integer::parseInt` và `Math::max`.

## 5. Chuyển đổi từng lambda sang method reference static

Đọc cả hai cách như cùng một lời gọi có tham số:

### Một tham số và có kết quả

```java
Function<RawOrder, Order> lambda =
        raw -> StaticReferenceDemo.parseOrder(raw);

Function<RawOrder, Order> reference =
        StaticReferenceDemo::parseOrder;
```

Khi `apply(raw)` chạy, cả hai gọi `parseOrder(raw)`. `Function<RawOrder,Order>` định hình đầu vào và đầu ra. Khi một phép biến đổi chỉ là “chuyển tiếp đối số”, tham chiếu thường dễ đọc hơn.

### Một tham số và kết quả boolean

```java
Predicate<Order> lambda =
        order -> StaticReferenceDemo.isLarge(order);

Predicate<Order> reference =
        StaticReferenceDemo::isLarge;
```

Dùng trong `Stream.filter(...)` vì filter yêu cầu một `Predicate<? super T>`. `Predicate<Order>` có phương thức `boolean test(Order)`; phương thức static `isLarge(Order)` trả đúng boolean.

### Hai tham số và kết quả số nguyên

```java
Comparator<Order> lambda =
        (a, b) -> StaticReferenceDemo.compareByAmount(a, b);

Comparator<Order> reference =
        StaticReferenceDemo::compareByAmount;
```

`Comparator<T>` có phương thức `int compare(T a, T b)`. Kết quả âm, 0, dương diễn đạt thứ tự so sánh; không dùng boolean `true/false` để thay thế.

### Hai tham số và kết quả cùng kiểu

```java
BinaryOperator<BigDecimal> lambda =
        (a, b) -> StaticReferenceDemo.add(a, b);

BinaryOperator<BigDecimal> reference =
        StaticReferenceDemo::add;
```

`BinaryOperator<T>` là trường hợp chuyên biệt của `BiFunction<T,T,T>`. Phép cộng `BigDecimal` có giá trị đơn vị `BigDecimal.ZERO` và tạo một giá trị mới, phù hợp để tổng hợp số tiền. Dùng `BigDecimal` với dữ liệu tiền tránh lỗi biểu diễn số thập phân do `double`, dù yêu cầu về làm tròn vẫn phải định nghĩa nếu có phép chia/thuế.

## 6. Static method reference và kiểm tra kiểu tại thời điểm biên dịch

Một method reference là một **poly expression**: kiểu của nó được suy ra từ target functional interface, không phải từ mỗi chuỗi `Type::method`. Vì thế cách dùng sau có kiểu rõ ràng:

```java
Function<String, Integer> parser = Integer::parseInt;
IntBinaryOperator maxOfTwo = Math::max;
Predicate<String> blank = String::isBlank;
```

Trong ba dòng, `parser` và `maxOfTwo` dùng **static method references**. Dòng `String::isBlank` lại là **unbound instance method reference**: đối tượng `String` nhận được từ tham số `Predicate.test(String)` trở thành receiver của `isBlank()`.

Không thể khai báo một method reference như một biểu thức độc lập mà không có target type phù hợp:

```java
// SAI: compiler không thể suy ra functional interface cho method reference.
// var parser = Integer::parseInt;

// ĐÚNG: cung cấp target type.
Function<String, Integer> parser = Integer::parseInt;
```

Đoạn comment là minh họa lỗi, không ghép vào chương trình chính. Với method reference ở vị trí đối số `map(Integer::parseInt)`, API `map` và kiểu nguồn cung cấp phần ngữ cảnh cho compiler suy luận target type.

### Overload được chọn bằng target type

`Math` có nhiều overload `abs` và `max`. Java có thể chọn overload phù hợp theo chữ ký của interface:

```java
java.util.function.IntUnaryOperator intAbs = Math::abs;
java.util.function.DoubleUnaryOperator doubleAbs = Math::abs;

System.out.println(intAbs.applyAsInt(-7));       // 7
System.out.println(doubleAbs.applyAsDouble(-2.5)); // 2.5
```

Không phải method reference “chứa sẵn” một overload duy nhất. Khi target type khác nhau, việc phân giải phương thức cũng có thể khác nhau. Nếu có nhiều overload cùng khả thi và không có phương thức phù hợp nhất, compiler sẽ báo **ambiguous method reference**; khi đó thêm target type rõ ràng, lambda ghi tường minh hoặc đổi tên API sẽ giúp làm rõ.

### Generic static methods

Phương thức static có thể là generic; compiler suy luận kiểu khi target interface được biết:

```java
import java.util.Objects;
import java.util.function.Function;

Function<String, String> requireString = Objects::requireNonNull;
System.out.println(requireString.apply("Java")); // Java
```

`Objects.requireNonNull(T)` trả lại đúng tham chiếu không null, hoặc ném `NullPointerException` nếu null. Với target `Function<String,String>`, compiler có thể chọn overload một tham số và suy luận `T` phù hợp. Tính generic của method reference không loại bỏ yêu cầu về target type.

## 7. Phân biệt các dạng method reference thường bị nhầm

| Cú pháp | Loại | Cách hiểu |
| --- | --- | --- |
| `Integer::parseInt` | Static | `s -> Integer.parseInt(s)` |
| `Math::max` | Static | `(a,b) -> Math.max(a,b)` |
| `StaticReferenceDemo::render` | Static | `order -> StaticReferenceDemo.render(order)` |
| `String::length` | Instance không gắn trước receiver | `s -> s.length()` |
| `Order::amount` | Instance không gắn trước receiver | `order -> order.amount()` |
| `System.out::println` | Instance gắn trước receiver | `x -> System.out.println(x)` |
| `somePrinter::print` | Instance gắn trước receiver | `x -> somePrinter.print(x)` |
| `ArrayList::new` | Constructor | `() -> new ArrayList<>()` trong ngữ cảnh supplier phù hợp |

**Dạng static** không thêm một tham số receiver. Nếu phương thức static nhận hai tham số, target functional interface cần hai tham số tương thích. Với **unbound instance reference** như `String::length`, tham số đầu tiên của functional interface đóng vai trò **receiver**; phương thức `length()` tự nó không có tham số, nhưng `ToIntFunction<String>` có một tham số `String` để gọi method trên đối tượng đó.

`System.out::println` thoạt nhìn chứa tên lớp `System` nhưng là **bound instance reference**: `out` là trường static của `System`, còn `println` là phương thức instance của `PrintStream`. Đọc chính xác biểu thức nằm **trước `::`**, rồi xác định phương thức được tham chiếu là static hay instance.

### Cẩn thận với phương thức static cùng tên phương thức instance

Java có quy tắc tìm kiếm và phân giải method reference theo cú pháp, arity, kiểu, overload và khả năng áp dụng. Với dạng `Type::method`, có thể tồn tại cả ứng viên static và instance; một method reference có thể trở nên mơ hồ trong trường hợp chữ ký và target interface khiến nhiều cách diễn giải đều khả thi. Không kết luận rằng dấu `Type::` mặc nhiên buộc Java chọn phương thức static.

Khi muốn diễn đạt rõ ý định và compiler báo mơ hồ, viết lambda tường minh, ví dụ `(String s) -> Utility.parse(s)`, hoặc sửa API để tên phương thức không gây nhầm.

## 8. Chọn interface phù hợp để tránh boxing và diễn đạt ý định

Với method reference static, nên chọn interface thể hiện đúng số tham số, đầu vào và đầu ra:

```java
Function<String, Integer> boxed = Integer::parseInt;

java.util.function.ToIntFunction<String> primitive =
        Integer::parseInt;

java.util.function.IntBinaryOperator sum =
        Integer::sum;

java.util.function.LongSupplier currentMillis =
        System::currentTimeMillis;
```

- `Function<String,Integer>` gọi `apply` và trả `Integer`. Khi tham chiếu phương thức trả primitive `int`, boxing có thể xảy ra.
- `ToIntFunction<String>` gọi `applyAsInt` và trả `int` trực tiếp, phù hợp khi muốn tránh boxing trong các vòng xử lý nhiều dữ liệu.
- `IntBinaryOperator` gọi `applyAsInt(int,int)`.
- `LongSupplier` gọi `getAsLong()` và không nhận đầu vào.

Đừng ép mọi method reference vào `Function<T,R>`. Nếu phương thức static trả `boolean`, `Predicate<T>` thường rõ nghĩa hơn. Nếu hai tham số và kết quả cùng kiểu, `BinaryOperator<T>` thuận tiện. Nếu phương thức không có đầu vào, `Supplier<R>` hoặc biến thể primitive thường hợp lý hơn.

## 9. Khi nên dùng lambda thay vì static method reference?

Method reference tốt khi nó diễn đạt **đúng một lời gọi hiện có**. Lambda vẫn phù hợp nếu muốn thêm logic, biến đổi tham số hoặc làm rõ một lời gọi mơ hồ.

### Phương thức đòi tham số bổ sung

```java
// Muốn mọi số đều được parse theo hệ 16.
Function<String, Integer> parseHex =
        text -> Integer.parseInt(text, 16);

// Không thể dùng Integer::parseInt trực tiếp cho Function<String,Integer>
// để tự ràng buộc tham số radix = 16.
```

`Integer::parseInt` có thể trỏ đến overload hai tham số khi target là `BiFunction<String,Integer,Integer>`, nhưng `Function<String,Integer>` không có cách truyền tham số radix cố định nếu chỉ ghi method reference. Lambda giải quyết phần tham số được cố định.

### Cần xử lý lỗi có chủ đích

```java
Function<String, Integer> parseOrZero = text -> {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ex) {
        return 0;
    }
};
```

Đây là **chính sách minh họa**: dữ liệu không hợp lệ sẽ được biến thành 0. Trong nghiệp vụ thực, 0 có thể là giá trị hợp lệ; nên cân nhắc trả `Optional<Integer>`, một kiểu Result hoặc báo lỗi rõ ràng để tránh che lỗi. Method reference không tích hợp xử lý ngoại lệ hoặc retry.

### Cần kiểm soát side effect hoặc biểu diễn rõ nghiệp vụ

```java
Function<String, String> normalizedCode =
        text -> text.trim().toUpperCase(java.util.Locale.ROOT);
```

Một lambda gồm hai phép chuyển đổi sẽ diễn đạt được quá trình này. Nếu đã có phương thức static `normalizeCode(String)` thực hiện đúng quy tắc, chuyển thành `CodeTools::normalizeCode` giúp tránh sao chép logic ở nhiều nơi.

## 10. Quy tắc lỗi và những ngộ nhận thường gặp

**Nhầm `::` với lời gọi ngay.** `Integer::parseInt` không lập tức nhận chuỗi hay trả `int`; nó cung cấp hành vi tương ứng với target interface. `Integer.parseInt("42")` mới là lời gọi trực tiếp.

**Viết dấu ngoặc khi tạo reference.** `Integer::parseInt("42")` không phải cú pháp Java hợp lệ. Cú pháp đúng là `Integer::parseInt`, rồi gọi `apply("42")` trên functional interface, hoặc dùng `Integer.parseInt("42")` trực tiếp.

**Thiếu target type.** `var f = Integer::parseInt` không tự đủ thông tin để xác định functional interface. Khai báo `Function<String,Integer> f` hoặc truyền vào API có tham số chức năng phù hợp.

**Chọn interface sai chữ ký.** `Supplier<Integer> parser = Integer::parseInt` không hợp lệ vì `parseInt` cần ít nhất một đối số, còn `Supplier.get()` không nhận đối số. `Function<String,Integer>` phù hợp hơn.

**Nhầm static và instance.** `String::length` khác `Integer::parseInt` về receiver. Dạng có tên lớp trước `::` có thể biểu diễn một trong hai cách tùy phương thức.

**Nhầm `System.out::println` là static.** `System.out` là biểu thức truy cập một đối tượng `PrintStream`, `println` là method instance trên đối tượng ấy.

**Không kiểm tra dữ liệu parse.** `Integer::parseInt` ném `NumberFormatException` với chuỗi không đúng định dạng hoặc vượt phạm vi `int`; `new BigDecimal(text)` cũng cần dữ liệu hợp lệ. Method reference không bảo vệ khỏi lỗi dữ liệu.

**Nghĩ method reference tạo hàm thuần.** `System::currentTimeMillis` là tham chiếu static nhưng cho kết quả thay đổi theo thời gian. Một phương thức static có thể cập nhật trạng thái chung hoặc gọi dịch vụ ngoài; tính thuần phụ thuộc triển khai, không phụ thuộc cú pháp.

**Bỏ qua side effect hoặc thứ tự thực thi.** Nếu hàm static vừa tính vừa sửa một biến static dùng chung, chạy nó trong `parallelStream().map(Type::method)` có thể gây race. Giữ phép biến đổi chỉ đọc dữ liệu và trả kết quả mới khi phù hợp; việc tổng hợp nên dùng reduce/collector có contract đúng.

**Giả định `sorted` sửa list gốc.** `stream().sorted(...)` tạo một stream theo thứ tự so sánh, không sửa trực tiếp `List`. Trong ví dụ, `orders` ban đầu vẫn theo thứ tự A01, A02, A03.

**Dựa vào `==` để so sánh method reference.** Hai reference có cùng thân không được bảo đảm có cùng object identity. Sử dụng chúng để gọi hành vi qua target interface, không để làm khóa định danh nghiệp vụ.

## 11. Bài tập vận dụng

1. Viết `Function<String,Integer> parse = Integer::parseInt` rồi gọi `parse.apply("17")`. Giải thích vì sao không thể gán `String::length` vào `Supplier<Integer>` nếu chưa gắn receiver.
2. Viết `IntUnaryOperator abs = Math::abs`. Gọi với `-12` và giải thích cách compiler chọn overload `abs(int)`.
3. Viết `IntBinaryOperator larger = Math::max` và gọi với `5`, `9`. Hãy so sánh lambda `(a,b) -> Math.max(a,b)` với reference `Math::max`.
4. Trong `StaticReferenceDemo`, đổi `Function<RawOrder,Order> parser` thành lambda `raw -> StaticReferenceDemo.parseOrder(raw)`. Kiểm tra stdout không thay đổi.
5. Thay `Predicate<Order> large` bằng lambda tương đương, rồi dùng `orders.stream().filter(large).count()`. Kết quả phải là `2`.
6. Sắp xếp các đơn theo số tiền giảm dần bằng comparator `StaticReferenceDemo::compareByAmount` và `reversed()`; dự đoán `A03, A01, A02`.
7. Thêm dữ liệu có `amount = "not-a-number"`. Chỉ ra exception trong `parseOrder`, rồi thiết kế chính sách lỗi rõ ràng trước khi đưa dữ liệu vào stream.
8. Viết `BiFunction<String,Integer,String>` nối mã sản phẩm và số lượng bằng một phương thức static. So sánh chữ ký method với chữ ký `apply`.
9. So sánh `System.out::println`, `String::toUpperCase` và `String::valueOf`: cái nào là bound instance, unbound instance, static? Chọn target type phù hợp cho mỗi cái.
10. Dùng `Map<String,Integer>` để thử `Integer::parseInt` trên từng giá trị chuỗi. Cân nhắc cách xử lý khóa trùng, giá trị không hợp lệ và bất biến đầu ra khi xây bản đồ kết quả.

## 12. Checklist khi đọc hoặc viết tham chiếu static

1. Phương thức mục tiêu **có khai báo `static`** không? Nếu không, hãy xác định receiver của dạng instance reference.
2. Target functional interface có **bao nhiêu tham số**, kiểu tham số ra sao và kết quả là gì?
3. Method overload nào được chọn? Có boxing/unboxing hoặc type inference không?
4. Phương thức có ném checked exception, có thể ném runtime exception, hoặc có side effect không?
5. Method reference có thực sự **rõ hơn lambda** cho người đọc không?
6. Khi dùng trong Stream, có cần giữ thứ tự, tránh mutate state và kiểm tra tính kết hợp của phép reduce không?

Hãy đọc `Type::method` thành “dùng phương thức này như cách thực hiện functional interface được yêu cầu”. Với phương thức static, các tham số của target interface truyền thẳng vào lời gọi static tương ứng; **không có receiver object bổ sung**. Nắm vững chữ ký và target type là chìa khóa để dùng `Type::method` đúng, đặc biệt khi viết pipeline biến đổi, lọc, so sánh và tổng hợp dữ liệu.
