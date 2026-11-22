# Chọn functional interface theo số đối số, kiểu kết quả và ý nghĩa thao tác trong Java

## 1. Mục tiêu: chọn đúng hợp đồng cho hành vi

Trong Java, lambda và method reference phải có **kiểu đích** là một functional interface. Việc chọn interface có ý nghĩa thiết kế: khi nhìn vào một tham số kiểu `Predicate<T>`, người đọc hiểu ngay bên gọi cần cung cấp **điều kiện**; `Function<T,R>` thể hiện **biến đổi**; `Consumer<T>` thể hiện **nhận giá trị và thực hiện hành động**.

Phần lớn các kiểu chuẩn nằm trong package `java.util.function` (có từ Java 8). Thay vì ghi nhớ tên một cách rời rạc, hãy quyết định dựa trên ba câu hỏi theo đúng thứ tự:

1. **Có bao nhiêu đối số?** Không có, một hay hai?
2. **Kết quả là gì?** Trả `boolean`, trả giá trị `R`, trả cùng kiểu `T`, hay không trả kết quả (`void`)?
3. **Ý nghĩa nghiệp vụ của thao tác là gì?** Kiểm tra điều kiện, chuyển đổi dữ liệu, cập nhật/ghi nhận, cung cấp giá trị, hoặc kết hợp hai giá trị?

Chọn kiểu mang **ý nghĩa rõ nhất** khi nhiều kiểu về mặt kỹ thuật đều dùng được. Ví dụ một lambda nhận `String` và trả `boolean` có thể viết thành `Function<String,Boolean>`, nhưng `Predicate<String>` diễn đạt điều kiện tốt hơn và hỗ trợ `and`, `or`, `negate`.

## 2. Bảng quyết định nhanh cho kiểu tham chiếu

| Số đối số | Kiểu trả về | Ý nghĩa | Functional interface | Phương thức trừu tượng |
| --- | --- | --- | --- | --- |
| 0 | `T` | Cung cấp hoặc tạo giá trị | `Supplier<T>` | `T get()` |
| 1 `T` | `boolean` | Kiểm tra điều kiện | `Predicate<T>` | `boolean test(T)` |
| 1 `T` | `R` | Ánh xạ/chuyển đổi | `Function<T,R>` | `R apply(T)` |
| 1 `T` | `T` | Biến đổi giữ nguyên kiểu | `UnaryOperator<T>` | `T apply(T)` |
| 1 `T` | `void` | Tiếp nhận, xử lý có tác dụng | `Consumer<T>` | `void accept(T)` |
| 2 `T,U` | `boolean` | Kiểm tra quan hệ/điều kiện | `BiPredicate<T,U>` | `boolean test(T,U)` |
| 2 `T,U` | `R` | Kết hợp hoặc ánh xạ hai giá trị | `BiFunction<T,U,R>` | `R apply(T,U)` |
| 2 cùng kiểu `T` | `T` | Kết hợp hai giá trị cùng kiểu | `BinaryOperator<T>` | `T apply(T,T)` |
| 2 `T,U` | `void` | Xử lý/ghi nhận cả hai giá trị | `BiConsumer<T,U>` | `void accept(T,U)` |

`UnaryOperator<T>` **mở rộng** `Function<T,T>`; `BinaryOperator<T>` **mở rộng** `BiFunction<T,T,T>`. Đây là các kiểu chuyên biệt diễn đạt rằng giá trị đầu ra cùng kiểu với đầu vào, chứ không phải một cơ chế thực thi lambda khác.

**Luồng chọn nhanh:**

~~~text
Hành vi cần truyền
├── 0 đối số
│   └── Trả giá trị T                  -> Supplier<T>
├── 1 đối số T
│   ├── Trả boolean                   -> Predicate<T>
│   ├── Không trả kết quả             -> Consumer<T>
│   ├── Trả chính kiểu T              -> UnaryOperator<T>
│   └── Trả kiểu R khác/không ràng buộc -> Function<T,R>
└── 2 đối số
    ├── Trả boolean                   -> BiPredicate<T,U>
    ├── Không trả kết quả             -> BiConsumer<T,U>
    ├── Hai T, trả T                  -> BinaryOperator<T>
    └── Trả R bất kỳ                 -> BiFunction<T,U,R>
~~~

Với kiểu nguyên thủy `int`, `long`, `double`, cần cân nhắc **biến thể primitive** ở phần 5 để tránh boxing/unboxing.

## 3. Chọn theo ý nghĩa thao tác

### 3.1. `Supplier<T>`: cung cấp giá trị khi được gọi

`Supplier<T>` không nhận đối số và trả một `T` qua `get()`. Dùng cho factory đơn giản, giá trị mặc định, hoặc cung cấp đầu vào khi API yêu cầu.

~~~java
Supplier<String> greeting = () -> "Xin chào";
Supplier<List<String>> emptyNames = ArrayList::new;
~~~

Đây là **đoạn minh họa trong một phương thức**, cần import `java.util.function.Supplier`, `java.util.List`, `java.util.ArrayList`. `get()` có thể tạo mới hoặc trả giá trị sẵn có tùy cách viết; **Supplier không tự bảo đảm cache**, cũng không mặc nhiên là hàm thuần. API quyết định thời điểm và số lần gọi `get()`.

Phân biệt `Supplier<T>` với `Function<Void,T>`: dùng `Void` làm đối số giả vừa khó đọc, vừa đòi hỏi truyền một giá trị tham số; `Supplier` diễn đạt đúng không đối số.

### 3.2. `Predicate<T>`: một câu hỏi đúng/sai

Dùng `Predicate<T>` khi cần điều kiện đầu vào `T` và kết quả `boolean`, chẳng hạn lọc đơn hàng, xác minh tên hợp lệ, kiểm tra chính sách.

~~~java
Predicate<String> notBlank = value -> value != null && !value.isBlank();
Predicate<String> shortEnough = value -> value != null && value.length() <= 8;
Predicate<String> accepted = notBlank.and(shortEnough);
~~~

`Predicate` có các phép ghép `and`, `or`, `negate` và phương thức tĩnh `Predicate.not(...)`. `and` và `or` là các phép kết hợp điều kiện có **short-circuit** (có thể không đánh giá vế sau nếu kết quả đã xác định), tương tự toán tử logic tương ứng. Lập trình kiểu này thích hợp khi các điều kiện không tạo tác dụng phụ.

Chọn `BiPredicate<T,U>` khi điều kiện cần **hai** đầu vào, ví dụ `(password, minLength) -> password.length() >= minLength`. Tham số kiểu `T` và `U` không cần giống nhau.

### 3.3. `Function<T,R>`: chuyển đổi đầu vào thành đầu ra

`Function<T,R>` dành cho chuyển đổi một giá trị thành một giá trị khác: từ đơn hàng sang tên khách, từ DTO sang domain model, từ chuỗi sang đối tượng đã phân tích.

~~~java
Function<String, Integer> length = String::length;
Function<Integer, String> label = count -> "Độ dài: " + count;
Function<String, String> describe = length.andThen(label);
~~~

Trong đoạn minh họa (import `java.util.function.Function`), `describe.apply("Java")` trả `"Độ dài: 4"`. `andThen` thực hiện hàm hiện tại trước rồi hàm sau; `compose` thực hiện hàm truyền vào trước. Hai phương thức có thể ghép được khi kiểu đầu ra/đầu vào tương thích.

Dùng `UnaryOperator<T>` nếu đầu vào và đầu ra **đều là T** (ví dụ chuẩn hóa `String`, cập nhật một value object thành một bản mới). `Function<T,T>` vẫn đúng, nhưng `UnaryOperator<T>` nêu ý định chặt chẽ hơn. Không cần chọn `UnaryOperator` nếu kết quả thực chất là kiểu khác.

### 3.4. `Consumer<T>`: thực hiện hành động, không trả dữ liệu

`Consumer<T>` nhận `T` và trả `void`. Trường hợp điển hình: log, hiển thị, gửi sự kiện hoặc gọi một hành động mà kết quả không truyền về.

~~~java
Consumer<String> print = System.out::println;
print.accept("Đã xử lý");
~~~

`Consumer` có `andThen` để thực hiện hai thao tác theo thứ tự. Hãy chú ý rằng tác dụng phụ như in console hoặc sửa trạng thái ngoài không phù hợp để nhét vào mọi bước `Stream.map`/`filter`; khi cần tạo danh sách kết quả, ưu tiên `map` rồi `toList` hoặc collector.

Với hai đối số, dùng `BiConsumer<T,U>`, chẳng hạn `(key, value) -> log(key, value)`. `Map.forEach` nhận `BiConsumer<? super K, ? super V>`, vì mỗi entry đưa ra cả khóa và giá trị.

### 3.5. `BiFunction<T,U,R>` và `BinaryOperator<T>`: phối hợp hai giá trị

Một phép tính cần hai tham số thường hợp với `BiFunction<T,U,R>`:

~~~java
BiFunction<String, Integer, String> repeat =
        (text, count) -> text.repeat(count);
String result = repeat.apply("ha", 3);  // "hahaha"
~~~

Nếu **hai đầu vào và đầu ra đều cùng kiểu**, dùng `BinaryOperator<T>` để biểu đạt phép kết hợp:

~~~java
BinaryOperator<String> chooseLonger =
        (left, right) -> left.length() >= right.length() ? left : right;
~~~

Hai đoạn giả định đã import `java.util.function.BiFunction` và `BinaryOperator`, đặt trong một phương thức. `BinaryOperator` có các tiện ích `minBy(Comparator)`, `maxBy(Comparator)`. Khi dùng kiểu này trong `Stream.reduce`, cần tuân thủ yêu cầu riêng của phép gộp như tính kết hợp (*associativity*) khi API đòi hỏi; không phải mọi phép tính hai đối số đều thích hợp làm phép reduce song song.

## 4. Ví dụ cùng hình dạng nhưng ý nghĩa khác nhau

Một lambda có đầu vào `String` có thể phục vụ nhiều mục đích:

| Câu lệnh cần diễn đạt | Chọn | Vì sao |
| --- | --- | --- |
| “Chuỗi này có hợp lệ không?” | `Predicate<String>` | Kết quả là điều kiện `boolean` |
| “Chuỗi này dài bao nhiêu?” | `ToIntFunction<String>` | Trả `int` nguyên thủy; có thể dùng `Function<String,Integer>` nhưng phát sinh boxing |
| “Chuẩn hóa chuỗi” | `UnaryOperator<String>` | Đầu vào/đầu ra cùng `String` |
| “Chuyển chuỗi thành `User`” | `Function<String,User>` | Chuyển sang kiểu khác |
| “In chuỗi ra console” | `Consumer<String>` | Hành động `void` |
| “Tạo chuỗi mặc định” | `Supplier<String>` | Không cần đối số |
| “Kiểm tra chuỗi dài ít nhất n” | `BiPredicate<String,Integer>` | Hai đối số, trả `boolean` |
| “Ghép hai chuỗi thành một” | `BinaryOperator<String>` | Hai `String`, trả `String` |

**Chọn theo hợp đồng API:** với `Consumer<String>`, lambda `s -> s.length()` vẫn hợp lệ vì lời gọi phương thức là *statement expression* và Java có thể bỏ qua giá trị `int` trả về. Tuy vậy, gọi `length()` rồi bỏ kết quả thường không có tác dụng hữu ích; nếu cần lấy độ dài, dùng `Function<String,Integer>` hoặc `ToIntFunction<String>`, còn `Consumer` nên thể hiện một hành động có chủ đích. Không biến `Consumer` thành “hàm trả null” qua `Function<T,Void>` nếu hợp đồng vốn chỉ là hành động.

Với kiểu `Boolean`, cần phân biệt một phép **kiểm tra boolean nguyên thủy** phù hợp `Predicate` với một API thực sự cần **đối tượng `Boolean` có thể null**. `Predicate.test` luôn trả primitive `boolean`, nên không thể đại diện một kết quả ba trạng thái `true`/`false`/`null` nếu không đặt quy tắc chuyển đổi rõ ràng.

## 5. Khi nào dùng các interface chuyên biệt cho primitive?

Các kiểu tổng quát `Function<T,R>`, `Supplier<T>`, `UnaryOperator<T>` nhận tham số kiểu **tham chiếu**, không nhận trực tiếp `int`, `long`, `double`. Viết `Function<int,long>` là lỗi biên dịch; phải dùng wrapper `Integer`/`Long`, hoặc ưu tiên các interface primitive.

| Hình dạng | Kiểu chuyên biệt | Phương thức SAM |
| --- | --- | --- |
| `int -> boolean` | `IntPredicate` | `boolean test(int)` |
| `long -> boolean` | `LongPredicate` | `boolean test(long)` |
| `double -> boolean` | `DoublePredicate` | `boolean test(double)` |
| `int -> int` | `IntUnaryOperator` | `int applyAsInt(int)` |
| `long -> long` | `LongUnaryOperator` | `long applyAsLong(long)` |
| `double -> double` | `DoubleUnaryOperator` | `double applyAsDouble(double)` |
| `(int,int) -> int` | `IntBinaryOperator` | `int applyAsInt(int,int)` |
| `(long,long) -> long` | `LongBinaryOperator` | `long applyAsLong(long,long)` |
| `() -> int` | `IntSupplier` | `int getAsInt()` |
| `() -> long` | `LongSupplier` | `long getAsLong()` |
| `() -> double` | `DoubleSupplier` | `double getAsDouble()` |
| `() -> boolean` | `BooleanSupplier` | `boolean getAsBoolean()` |
| `int -> void` | `IntConsumer` | `void accept(int)` |
| `long -> void` | `LongConsumer` | `void accept(long)` |
| `double -> void` | `DoubleConsumer` | `void accept(double)` |
| `T -> int` | `ToIntFunction<T>` | `int applyAsInt(T)` |
| `T -> long` | `ToLongFunction<T>` | `long applyAsLong(T)` |
| `T -> double` | `ToDoubleFunction<T>` | `double applyAsDouble(T)` |
| `int -> R` | `IntFunction<R>` | `R apply(int)` |
| `double -> R` | `DoubleFunction<R>` | `R apply(double)` |
| `int -> long` | `IntToLongFunction` | `long applyAsLong(int)` |
| `long -> int` | `LongToIntFunction` | `int applyAsInt(long)` |
| `(T,U) -> int` | `ToIntBiFunction<T,U>` | `int applyAsInt(T,U)` |
| `(T,int) -> void` | `ObjIntConsumer<T>` | `void accept(T,int)` |

Có thêm các biến thể đối xứng như `LongFunction<R>`, `DoubleToLongFunction`, `IntToDoubleFunction`, `LongToDoubleFunction`, `DoubleToIntFunction`, `ToLongBiFunction<T,U>`, `ToDoubleBiFunction<T,U>`, `ObjLongConsumer<T>`, `ObjDoubleConsumer<T>`. Đọc tên theo khuôn: **nguồn kiểu nào, đích kiểu nào, bao nhiêu đối số**.

Ví dụ minh họa:

~~~java
IntPredicate positive = n -> n > 0;
IntUnaryOperator squared = n -> n * n;
ToLongFunction<String> countLetters = value -> value.length();
LongBinaryOperator sum = Long::sum;
~~~

Đoạn này cần import `java.util.function.*`, đặt trong một phương thức. `countLetters` trả primitive `long` nhờ widening conversion từ `int`; nếu chỉ cần độ dài dạng `int`, `ToIntFunction<String>` thích hợp hơn.

**Vì sao lựa chọn primitive có ích?** Các kiểu chuyên biệt tránh boxing/unboxing khi chuyển đổi các primitive trong pipeline, đặc biệt trong `IntStream`/`LongStream`/`DoubleStream`. Nhưng không nên khẳng định primitive luôn nhanh hơn trong mọi tác vụ; cần đo chi phí thực tế nếu hiệu năng là yêu cầu quan trọng.

Ví dụ:

~~~java
long total = orders.stream()
        .mapToLong(order -> order.unitPrice() * order.quantity())
        .sum();
~~~

`mapToLong` nhận `ToLongFunction<? super Order>`, trả `LongStream`, sau đó `sum()` cộng các phần tử `long`. Đây là ví dụ truyền một hàm vào API Stream mà không tạo `Long` wrapper cho từng giá trị.

## 6. Ví dụ Java 17 hoàn chỉnh: chọn interface trong một bài toán

Giả sử danh sách đơn hàng gồm tên khách, số lượng, đơn giá và trạng thái thanh toán. Ta muốn lọc đơn đã thanh toán, lấy danh sách khách, tính tổng tiền, cộng phí dịch vụ, kiểm tra tên và in kết quả. Mỗi thao tác cần một hợp đồng có ý nghĩa riêng.

Tạo tệp **InterfaceChoiceDemo.java**:

~~~java
import java.util.List;
import java.util.function.*;

public class InterfaceChoiceDemo {
    record Order(String customer, int quantity, long unitPrice, boolean paid) {}

    static long amount(Order order) {
        return order.quantity() * order.unitPrice();
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("An", 2, 15_000, true),
                new Order("Binh", 1, 25_000, false),
                new Order("Chi", 3, 10_000, true)
        );

        Predicate<Order> isPaid = Order::paid;
        Function<Order, String> getCustomer = Order::customer;
        ToLongFunction<Order> getAmount = InterfaceChoiceDemo::amount;
        Supplier<String> title = () -> "Đơn đã thanh toán";
        Consumer<String> output = System.out::println;
        BiPredicate<String, Integer> minLength =
                (name, min) -> name != null && name.length() >= min;
        BiConsumer<String, Long> showMoney =
                (label, value) -> System.out.println(label + ": " + value);
        LongUnaryOperator addServiceFee = value -> value + 5_000;
        UnaryOperator<String> trim = String::trim;
        BinaryOperator<String> join = (left, right) -> left + " / " + right;

        List<Order> paidOrders = orders.stream().filter(isPaid).toList();
        List<String> customers = paidOrders.stream().map(getCustomer).toList();
        long subtotal = paidOrders.stream().mapToLong(getAmount).sum();

        output.accept(title.get() + ": " + customers);
        showMoney.accept("Tổng", subtotal);
        showMoney.accept("Cộng phí", addServiceFee.applyAsLong(subtotal));
        output.accept("Tên hợp lệ: " + minLength.test("An", 2));
        output.accept(join.apply(trim.apply("  An "), "Chi"));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp bằng JDK 17+:

~~~bash
javac --release 17 InterfaceChoiceDemo.java
java InterfaceChoiceDemo
~~~

**Kết quả đã kiểm chứng khi chạy:**

~~~text
Đơn đã thanh toán: [An, Chi]
Tổng: 60000
Cộng phí: 65000
Tên hợp lệ: true
An / Chi
~~~

Diễn giải theo đúng vai trò của từng interface:

1. `Predicate<Order>` định nghĩa **điều kiện giữ đơn** `paid == true`. `Stream.filter` sử dụng trực tiếp predicate đó.
2. `Function<Order,String>` biến `Order` thành `String` là tên khách qua `Stream.map`.
3. `ToLongFunction<Order>` lấy số tiền primitive `long` qua `Stream.mapToLong`, giúp cộng qua `LongStream.sum()`.
4. `Supplier<String>` cung cấp tiêu đề khi gọi `get()`; tiêu đề không cần tham số đầu vào.
5. `Consumer<String>` gọi `println` để xuất thông tin, không trả dữ liệu cho bên gọi.
6. `BiPredicate<String,Integer>` so độ dài tên với ngưỡng, nhận hai kiểu đầu vào và trả `boolean`.
7. `BiConsumer<String,Long>` nhận một nhãn và một số tiền để hiển thị.
8. `LongUnaryOperator` nhận `long` và trả `long`, biểu diễn phép cộng phí với đầu ra cùng kiểu.
9. `UnaryOperator<String>` giữ kiểu `String` khi `trim`; `BinaryOperator<String>` kết hợp hai chuỗi thành một.

Dữ liệu có hai đơn đã thanh toán: `An` 2 × 15.000 = 30.000; `Chi` 3 × 10.000 = 30.000; tổng là 60.000, cộng phí 5.000 thành 65.000. Không có thứ tự đầu ra ngẫu nhiên: nguồn `List.of` giữ encounter order và các thao tác `filter`, `map`, `toList` trong ví dụ giữ thứ tự tương ứng.

`BiConsumer<String, Long>` dùng kiểu tham chiếu `Long`, nên tham số `long subtotal` được boxing khi truyền vào `accept`. Nếu thao tác hai tham số gồm một object nhãn và một `long` là phần nóng về hiệu năng, hãy cân nhắc `ObjLongConsumer<String>`. Điều này minh họa cách chọn theo **hình dạng hàm**, rồi tinh chỉnh theo **kiểu dữ liệu thực tế**.

## 7. Chọn interface theo API nhận lambda

Khi một API đã tồn tại, **kiểu tham số của API quyết định kiểu đích**; ta không tự đổi sang một interface “thấy hợp hơn” nếu API không chấp nhận nó.

| API / thao tác | Hợp đồng mà API nhận | Ý nghĩa |
| --- | --- | --- |
| `Stream<T>.filter(...)` | `Predicate<? super T>` | Giữ hoặc loại phần tử |
| `Stream<T>.map(...)` | `Function<? super T,? extends R>` | Biến đổi mỗi phần tử |
| `Stream<T>.mapToInt(...)` | `ToIntFunction<? super T>` | Chuyển thành primitive `int` |
| `Stream<T>.mapToLong(...)` | `ToLongFunction<? super T>` | Chuyển thành primitive `long` |
| `Stream<T>.forEach(...)` | `Consumer<? super T>` | Thực hiện một hành động |
| `Optional<T>.orElseGet(...)` | `Supplier<? extends T>` | Tạo giá trị thay thế khi thiếu |
| `Map<K,V>.forEach(...)` | `BiConsumer<? super K,? super V>` | Nhận khóa và giá trị |
| `Map<K,V>.computeIfAbsent(...)` | `Function<? super K,? extends V>` | Tính giá trị theo khóa khi vắng mặt |
| `Stream<T>.reduce(identity, accumulator)` | `BinaryOperator<T>` | Gộp các giá trị cùng kiểu |
| `IntStream.map(...)` | `IntUnaryOperator` | Chuyển `int` thành `int` |
| `IntStream.filter(...)` | `IntPredicate` | Lọc theo `int` |
| `IntStream.mapToObj(...)` | `IntFunction<? extends U>` | Chuyển `int` sang object |
| `LongStream.sum()` | Không nhận callback | API tự tổng hợp; không cần tự truyền operator |

Dấu `? super T` và `? extends R` là wildcard về phương sai: giúp API chấp nhận hàm xử lý kiểu cha của phần tử hoặc trả kiểu con của kết quả mong đợi. Hãy xem chữ ký thực tế của phương thức trong IDE/Javadoc trước khi chọn interface.

**Phân biệt các API gần nhau:** `Optional.orElse(value)` nhận giá trị đã tính sẵn, còn `Optional.orElseGet(supplier)` nhận hành vi cung cấp để có thể gọi khi thực sự cần thay thế. `Map.computeIfAbsent` nhận `Function<K,V>` vì hàm phải biết **khóa**; không thể thay nó trực tiếp bằng `Supplier<V>` nếu chữ ký API yêu cầu Function.

## 8. Kết hợp hành vi: ưu tiên đúng kiểu cho phép ghép

Nhiều interface cung cấp phương thức kết hợp, giúp mô hình hóa chuỗi xử lý theo đúng ngữ nghĩa:

~~~java
Predicate<String> nonBlank = text -> text != null && !text.isBlank();
Predicate<String> shortText = text -> text != null && text.length() <= 10;
Predicate<String> valid = nonBlank.and(shortText);

Function<String, String> trim = String::trim;
Function<String, Integer> length = String::length;
Function<String, Integer> normalizedLength = trim.andThen(length);

Consumer<String> first = text -> System.out.println("A:" + text);
Consumer<String> second = text -> System.out.println("B:" + text);
Consumer<String> both = first.andThen(second);
~~~

Đây là **các đoạn minh họa đặt trong phương thức**, cần import `java.util.function.Predicate`, `Function`, `Consumer`. `valid` kiểm tra cả hai điều kiện; `normalizedLength.apply(" Java ")` trả 4; `both.accept("X")` lần lượt in `A:X` và `B:X`.

Những phép ghép có tác dụng phụ vẫn phụ thuộc vào thứ tự, trạng thái và ngoại lệ. Chẳng hạn nếu Consumer đầu ném ngoại lệ, Consumer thứ hai không được thực thi. Với `Predicate` chứa tác dụng phụ, `and`/`or` có thể bỏ qua phần sau vì short-circuit. Nên ưu tiên các hàm kiểm tra/chuyển đổi thuần khi cần logic dễ kiểm thử.

## 9. Khi không dùng trực tiếp các kiểu trong java.util.function?

Một số hành vi đã có functional interface **chuyên ngành** ngoài package `java.util.function`. Hãy dùng chúng khi API hoặc ngữ nghĩa miền yêu cầu.

- `Runnable` ở `java.lang` diễn đạt `() -> void`, thường là công việc cần thực thi, ví dụ giao cho `Thread` hoặc `Executor`. Nó không trả kết quả.
- `Callable<V>` ở `java.util.concurrent` diễn đạt `() -> V`, có thể khai báo `throws Exception`. Nó thích hợp cho công việc có kết quả và khả năng checked exception; không giống `Supplier<V>` về hợp đồng checked exception.
- `Comparator<T>` ở `java.util` diễn đạt `(T,T) -> int` để so sánh thứ tự. Không thay bằng `BiFunction<T,T,Integer>` khi API yêu cầu Comparator; ý nghĩa so sánh bao gồm các hợp đồng thứ tự riêng.
- `java.util.EventListener` không mặc nhiên là functional interface; từng subtype cụ thể cần được kiểm tra hợp đồng abstract.
- Khi cần **ba đối số**, bộ interface chuẩn `java.util.function` không có `TriFunction<T,U,V,R>` phổ thông. Có thể tạo functional interface phù hợp với domain hoặc gói các đối số liên quan trong record/value object rồi truyền vào `Function`.

Ví dụ một interface đặt tên theo nghiệp vụ (đoạn mã khai báo **ở mức class/interface, không đặt bên trong một phương thức**):

~~~java
@FunctionalInterface
interface PricePolicy {
    long calculate(long basePrice);
}
~~~

`PricePolicy` có chữ ký tương tự `LongUnaryOperator`, nhưng tên miền nghiệp vụ có thể giúp API rõ ràng hơn. Chọn interface riêng khi nó có ý nghĩa công khai ổn định hoặc cần tài liệu/hợp đồng chuyên biệt; với callback tiện ích thông thường, kiểu chuẩn giảm số abstraction không cần thiết.

Với checked exception, các `Function`, `Predicate`, `Supplier` chuẩn không tự thêm `throws IOException`/SQL exception vào phương thức SAM. Một lambda ném checked exception không tương thích sẽ không biên dịch, trừ khi được xử lý bên trong lambda hoặc dùng interface khác có hợp đồng `throws` thích hợp. Không nên lặng lẽ bọc mọi ngoại lệ thành RuntimeException khi API yêu cầu người gọi xử lý có chủ đích.

## 10. Các sai lầm chọn interface thường gặp

1. **Chọn `Function<T,Boolean>` thay `Predicate<T>` cho điều kiện nhị phân** mà không có lý do: mất các phép kết hợp điều kiện chuyên dụng và có thể boxing. Nếu thật sự cần kết quả `Boolean` nullable, đó là yêu cầu khác cần diễn đạt rõ.
2. **Dùng `Consumer<T>` để tích lũy kết quả có thể trả về:** việc sửa danh sách ngoài từ `forEach` khó hiểu và không an toàn khi chạy song song. Với dữ liệu mới, dùng `map`, `reduce`, `collect` hoặc `toList` tùy tác vụ.
3. **Dùng `Function<Void,T>` thay `Supplier<T>`:** tạo tham số không có nghĩa. Dùng `Supplier` nếu không có đầu vào.
4. **Mặc định dùng `BiFunction` cho phép gộp `(T,T)->T`:** `BinaryOperator<T>` cho biết rõ cả ba vị trí cùng kiểu, phù hợp với nhiều API reduce.
5. **Nhầm kiểu trả về `void` với kiểu `Void`:** `Void` là một kiểu tham chiếu, không phải từ khóa `void`; `Consumer` dành cho không trả kết quả.
6. **Dùng wrapper trong luồng primitive mà không cần:** `Function<Integer,Integer>` có boxing, trong khi `IntUnaryOperator` nhận và trả `int`. Chọn kiểu chuyên biệt khi phù hợp.
7. **Cho rằng tên interface quyết định độ thuần:** `Function` cũng có thể gây tác dụng phụ, `Supplier` có thể trả giá trị thay đổi theo thời gian, `Predicate` có thể đọc trạng thái chia sẻ. Sự thuần khiết đến từ thân thực thi và dữ liệu liên quan.
8. **Cố ép callback nhiều đối số vào biến lambda không có target type:** Java cần functional interface rõ ràng để xác định chữ ký. Nếu API cần kiểu riêng, khai báo interface có đúng một SAM hoặc dùng kiểu phù hợp khác.
9. **Nhầm `BiPredicate<T,U>` với `BinaryOperator<T>`:** cả hai nhận hai đối số, nhưng cái đầu trả `boolean`, cái sau trả `T`. Hãy bắt đầu bằng câu hỏi về **kiểu kết quả**.

## 11. Bài tập chọn interface

Chọn kiểu thích hợp, rồi so sánh với đáp án:

| Tình huống | Đáp án gợi ý | Giải thích |
| --- | --- | --- |
| Cấp mã đơn hàng mới, không có tham số | `Supplier<String>` | Không đối số, trả String |
| Kiểm tra số tuổi nguyên thủy có lớn hơn 18 | `IntPredicate` | Nhận int, trả boolean |
| Chuyển `User` thành `UserDto` | `Function<User,UserDto>` | Hai kiểu tham chiếu khác nhau |
| Tăng giá trị long lên 1 | `LongUnaryOperator` | long → long |
| So sánh `User` và quyền `Role` | `BiPredicate<User,Role>` | Hai đối số, kiểm tra điều kiện |
| Cập nhật giao diện theo tên và số đếm | `BiConsumer<String,Integer>` | Nhận hai giá trị, không trả kết quả |
| Lấy số phần tử của chuỗi `String` | `ToIntFunction<String>` | Object → int |
| Ghép hai `BigDecimal` thành một tổng | `BinaryOperator<BigDecimal>` | Hai đầu vào và kết quả cùng BigDecimal |
| Biến `double` thành chuỗi hiển thị | `DoubleFunction<String>` | double → String |
| Tạo công việc trả dữ liệu và khai báo checked exception | `Callable<V>` | Ngữ nghĩa công việc, có checked exception |

**Thử giải thích thêm:** với bài toán “tính phí cho một đơn”, nên dùng `Function<Order,Long>` hay `ToLongFunction<Order>`? Nếu phí là primitive long và được dùng cho tính toán/Stream, `ToLongFunction<Order>` thường bộc lộ kiểu đích tốt hơn và tránh boxing. Nếu API nhận `Function<Order,Long>` thì phải dùng đúng chữ ký API; không tự đổi kiểu tham số.

## 12. Checklist trước khi viết lambda

Trước khi chọn interface, hãy tự kiểm tra:

1. API cụ thể nhận kiểu callback nào? Nếu chưa có API, mình đang định nghĩa hợp đồng nào?
2. Có 0, 1 hay 2 tham số? Chúng là kiểu tham chiếu hay nguyên thủy?
3. Kiểu trả về thực sự là `void`, `boolean`, `T`, `R` hay primitive?
4. Có interface diễn đạt rõ ý nghĩa điều kiện, chuyển đổi, cung cấp, tiêu thụ hoặc kết hợp không?
5. Lambda có cần xử lý checked exception hoặc mang ngữ nghĩa domain riêng không?
6. Có nguy cơ boxing, thay đổi trạng thái chia sẻ, chi phí tính toán hoặc lạm dụng callback trong Stream không?

**Kết luận:** Để chọn functional interface đúng, hãy suy ra **số đối số → kiểu kết quả → ý nghĩa thao tác**, rồi so với hợp đồng API đích. `Supplier`, `Predicate`, `Function`, `Consumer`, `UnaryOperator`, `BinaryOperator` và các biến thể `Bi...` bao phủ phần lớn callback kiểu tham chiếu; các biến thể `Int...`, `Long...`, `Double...`, `To...`, `Obj...` giúp xử lý primitive phù hợp. Cách chọn tốt giúp code tự nói rõ chủ đích và giúp người gọi biết chính xác phải cung cấp hành vi nào.
