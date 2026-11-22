# BiPredicate, BiFunction và BiConsumer trong Java 8: hợp đồng hai tham số và cách dùng hiện nay

## 1. Mục tiêu bài học

Ba interface `BiPredicate<T,U>`, `BiFunction<T,U,R>` và `BiConsumer<T,U>` thuộc `java.util.function`, được giới thiệu từ Java 8 và **vẫn là API chuẩn đang được sử dụng trên JDK hiện đại**. Chúng giúp truyền hành vi nhận **hai đối số**, với ba loại kết quả khác nhau: điều kiện boolean, kết quả tính toán và hành động không trả giá trị.

Sau bài này, bạn có thể:

- Chọn đúng interface khi cần xử lý hai tham số; đọc và giải thích chính xác các kiểu generic `T`, `U`, `R`.
- Viết lambda hoặc method reference đúng chữ ký; gọi `test`, `apply`, `accept`.
- Kết hợp điều kiện bằng `and`, `or`, `negate`; nối phép biến đổi bằng `andThen`; nối hành động với `BiConsumer.andThen`.
- Dùng các interface này trong `Map.forEach`, `Map.replaceAll` và khi tích hợp với Stream; hiểu các giới hạn về side effect, null, exception và thread safety.
- Biên dịch, chạy một chương trình Java độc lập và đối chiếu kết quả đầu ra.

Dùng **JDK được nhà cung cấp hỗ trợ/cập nhật**, ví dụ dòng JDK LTS phù hợp với dự án. Các ví dụ chính sử dụng cú pháp và API từ Java 8 để thuận tiện kiểm tra tương thích bằng `javac --release 8`; không đòi cài runtime Java 8 cũ. Không đưa vào API lỗi thời hoặc cách lập trình dựa trên hành vi nội bộ của JDK.

## 2. So sánh chính xác ba hợp đồng

| Functional interface | Phương thức trừu tượng (SAM) | Đầu vào | Đầu ra | Mục đích |
| --- | --- | --- | --- | --- |
| `BiPredicate<T,U>` | `boolean test(T t, U u)` | Hai giá trị có kiểu `T` và `U` | `boolean` | Kiểm tra một điều kiện |
| `BiFunction<T,U,R>` | `R apply(T t, U u)` | Hai giá trị có kiểu `T` và `U` | Một giá trị kiểu `R` | Biến đổi hoặc tính toán |
| `BiConsumer<T,U>` | `void accept(T t, U u)` | Hai giá trị có kiểu `T` và `U` | Không trả giá trị | Thực hiện một tác động/hành động |

Đây đều là **functional interface**: mỗi loại có một phương thức trừu tượng được triển khai bằng lambda hoặc method reference. Chúng có thể có thêm default method mà vẫn là functional interface. Generic `T` và `U` có thể giống hoặc khác nhau, tùy bài toán; chỉ `BiFunction` có kiểu kết quả `R`.

### Ví dụ nhỏ nhất

~~~java
import java.util.function.BiConsumer;
import java.util.function.BiFunction;
import java.util.function.BiPredicate;

// Các câu lệnh đặt bên trong một phương thức:
BiPredicate<String, Integer> longEnough =
    (text, minimum) -> text != null && text.length() >= minimum;

BiFunction<Integer, Integer, Integer> sum =
    (left, right) -> left + right;

BiConsumer<String, Integer> printScore =
    (name, score) -> System.out.println(name + ": " + score);

System.out.println(longEnough.test("Java", 4)); // true
System.out.println(sum.apply(2, 3));             // 5
printScore.accept("Lan", 90);                    // Lan: 90
~~~

Trong `BiPredicate<String,Integer>`, compiler hiểu `text` là `String` và `minimum` là `Integer`. Với `BiFunction<Integer,Integer,Integer>`, cả hai đối số và kết quả đều là `Integer`; khi cần hiệu năng cho phép toán nguyên thủy, có thể chọn biến thể chuyên biệt để giảm boxing (mục 9).

Ba phương thức có tên khác nhau và **không hoán đổi được**: `test` trả boolean; `apply` trả `R`; `accept` trả `void`. Đừng gán lambda chỉ thực hiện `println` vào `BiFunction<String,Integer,String>`: method này bắt buộc phải trả về `String`.

## 3. BiPredicate<T,U>: điều kiện nhận hai tham số

Một `BiPredicate<T,U>` mô tả mệnh đề phụ thuộc vào **cả hai đối số** hoặc một đối số cộng cấu hình. Ví dụ kiểm tra đơn hàng có giá trị tối thiểu:

~~~java
import java.util.function.BiPredicate;

// Trong một phương thức, cùng kiểu Order có phương thức subtotal():
BiPredicate<Order, Integer> meetsMinimum =
    (order, minimum) -> order.subtotal() >= minimum;

// meetsMinimum.test(order, 200) trả true hoặc false.
~~~

Đây là trích đoạn cần một class `Order`, được khai báo đầy đủ trong chương trình mục 7. Tham số thứ hai giúp tái dùng cùng điều kiện cho nhiều ngưỡng, thay vì hard-code `200` vào thân lambda.

### Kết hợp với and, or, negate

`BiPredicate` có ba default method quan trọng:

- `first.and(second)`: kết quả chỉ true khi cả hai đúng, **dừng ngắn mạch** nếu `first` trả false.
- `first.or(second)`: kết quả true nếu ít nhất một điều kiện đúng, **dừng ngắn mạch** nếu `first` trả true.
- `first.negate()`: đảo kết quả boolean của điều kiện hiện có.

~~~java
import java.util.function.BiPredicate;

// Đoạn này đặt trong một phương thức:
BiPredicate<Integer, Integer> greaterThan =
    (number, limit) -> number > limit;

BiPredicate<Integer, Integer> even =
    (number, ignoredLimit) -> number % 2 == 0;

BiPredicate<Integer, Integer> bigAndEven = greaterThan.and(even);
BiPredicate<Integer, Integer> bigOrEven = greaterThan.or(even);

System.out.println(bigAndEven.test(8, 5)); // true
System.out.println(bigAndEven.test(7, 5)); // false
System.out.println(bigOrEven.test(4, 5));  // true
System.out.println(greaterThan.negate().test(3, 5)); // true
~~~

**Điểm tinh tế:** Trong `and`/`or`, cả hai predicate nhận **cùng cặp đối số và cùng thứ tự**. `even` trong ví dụ không cần dùng đối số ngưỡng, nên đặt tên `ignoredLimit` để làm rõ. Một predicate có thể bỏ qua một đối số, nhưng nếu hai điều kiện thực chất cần hai tham số mang ý nghĩa **khác nhau**, đừng ép kết hợp bằng `and` rồi làm người đọc hiểu sai dữ liệu truyền vào.

**Không dựa vào side effect** trong predicate: thứ tự short-circuit khiến predicate thứ hai đôi khi không chạy. Với điều kiện dự kiến dùng trong Stream hoặc các API song song, hãy ưu tiên hàm không sửa trạng thái chung.

### Cẩn thận với null và negate

~~~java
BiPredicate<String, Integer> valid =
    (text, minLength) -> text != null && text.length() >= minLength;

// valid.test(null, 1) là false.
// valid.negate().test(null, 1) sẽ là true!
~~~

Đảo phủ định của một điều kiện có kiểm tra null có thể khiến null được coi là thỏa điều kiện phủ định. Nếu null đại diện dữ liệu không hợp lệ, xác thực đầu vào **trước** khi gọi predicate hoặc tách rạch ròi "dữ liệu hợp lệ" và "điều kiện nghiệp vụ". Không suy ra rằng `negate()` đồng nghĩa với "kiểm tra hợp lệ ngược lại".

## 4. BiFunction<T,U,R>: tính toán từ hai tham số

`BiFunction<T,U,R>` nhận hai giá trị và trả một kết quả kiểu `R`. Kết quả có thể cùng kiểu với tham số hoặc khác hoàn toàn:

~~~java
import java.util.function.BiFunction;

BiFunction<Integer, Integer, Integer> multiply =
    (a, b) -> a * b;

BiFunction<String, Integer, String> label =
    (name, quantity) -> name + " x " + quantity;

System.out.println(multiply.apply(3, 4)); // 12
System.out.println(label.apply("Sách", 2)); // Sách x 2
~~~

Không bắt buộc giữ cùng kiểu `T`/`U`/`R`. Ví dụ `BiFunction<Order, Integer, String>` có thể nhận một đơn hàng, phí giao hàng và trả chuỗi hiển thị; nhưng nên tách bước tính tổng kiểu số khỏi bước trình bày nếu còn cần làm việc với giá trị số.

### andThen chỉ biến đổi kết quả

`BiFunction.andThen(Function<? super R,? extends V>)` nối thêm một hàm **một tham số**, chỉ xử lý giá trị trả về của `apply`:

~~~java
import java.util.function.BiFunction;

BiFunction<Integer, Integer, Integer> total =
    (price, fee) -> price + fee;

BiFunction<Integer, Integer, String> display =
    total.andThen(value -> value + " VND");

System.out.println(display.apply(100, 15)); // 115 VND
~~~

Luồng xử lý:

~~~text
(price=100, fee=15)
        |
        v
BiFunction.apply -> 115
        |
        v
Function<Integer,String> -> "115 VND"
~~~

`andThen` không thêm đối số thứ ba cho `BiFunction` và không chạy trước `apply`. Nếu `apply` ném exception, bước sau không chạy. Nếu `after` là null, `andThen(null)` ném `NullPointerException`. Khi tính tiền thật, cân nhắc `BigDecimal` hoặc đơn vị số nguyên rõ ràng và xử lý tràn số; ví dụ đơn giản chỉ nhằm học hợp đồng hai tham số.

### Khi nào dùng BinaryOperator thay BiFunction?

`BinaryOperator<T>` **kế thừa** `BiFunction<T,T,T>`, phù hợp khi **hai đầu vào và đầu ra cùng một kiểu**, đặc biệt các phép kết hợp/giảm:

~~~java
import java.util.function.BinaryOperator;

BinaryOperator<Integer> max = (a, b) -> a >= b ? a : b;
System.out.println(max.apply(3, 8)); // 8
~~~

`BinaryOperator` diễn đạt ràng buộc kiểu chặt hơn; nhưng vẫn có thể dùng `BiFunction<Integer,Integer,Integer>`. Khi kiểu kết quả khác kiểu đầu vào, `BiFunction` là lựa chọn phù hợp hơn.

## 5. BiConsumer<T,U>: thực hiện hành động với hai tham số

`BiConsumer<T,U>` không trả kết quả. Nó thường được dùng với hành động có side effect rõ ràng, chẳng hạn ghi log, cập nhật một giá trị được quản lý, hoặc xử lý từng cặp key/value.

~~~java
import java.util.function.BiConsumer;

BiConsumer<String, Integer> announce =
    (name, count) -> System.out.println(name + " có " + count + " đơn");

announce.accept("Lan", 3);
// In: Lan có 3 đơn
~~~

### andThen nối hai hành động theo thứ tự

~~~java
import java.util.function.BiConsumer;

BiConsumer<String, Integer> print =
    (name, score) -> System.out.println(name + ": " + score);

BiConsumer<String, Integer> audit =
    (name, score) -> System.out.println("Đã ghi: " + name);

BiConsumer<String, Integer> both = print.andThen(audit);
both.accept("Mai", 8);
~~~

Stdout:

~~~text
Mai: 8
Đã ghi: Mai
~~~

Cả hai consumer nhận **cùng hai đối số**, chạy theo thứ tự `print` rồi `audit`. Nếu consumer đầu ném exception, consumer thứ hai **không** được chạy. `andThen` không phải transaction: side effect của consumer đầu có thể đã xảy ra ngay cả khi consumer thứ hai thất bại.

**Lưu ý production:** Ghi log không nên lộ thông tin nhạy cảm. Khi consumer gọi mạng, ghi DB hoặc đổi state, xác định quy tắc lỗi/retry/idempotency riêng; ghép `andThen` không tạo rollback tự động.

## 6. Ba giao diện này xuất hiện ở đâu trong Java API?

### Map.forEach dùng BiConsumer

`Map.forEach(BiConsumer<? super K,? super V>)` gửi mỗi cặp khóa/giá trị tới `accept`:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Integer> stock = new LinkedHashMap<String, Integer>();
stock.put("A", 3);
stock.put("B", 1);

stock.forEach((code, amount) ->
    System.out.println(code + "=" + amount));
// A=3
// B=1
~~~

Ở đây `LinkedHashMap` lưu thứ tự duyệt theo thứ tự thêm đối với cấu hình mặc định; `HashMap` không cam kết cùng thứ tự. Nếu output hoặc nghiệp vụ phụ thuộc thứ tự, chọn cấu trúc có hợp đồng thứ tự tương ứng.

### Map.replaceAll dùng BiFunction

`Map.replaceAll(BiFunction<? super K,? super V,? extends V>)` nhận key/value cũ và trả value mới:

~~~java
stock.replaceAll((code, quantity) -> quantity + 1);
// A chuyển từ 3 thành 4; B chuyển từ 1 thành 2.
~~~

Đây là thao tác **thay đổi map**, khác `Stream.map` vốn tạo ra một Stream kết quả. Không dùng `replaceAll` nếu chỉ muốn đọc/biến đổi đầu ra mà không cập nhật dữ liệu. Với một số triển khai Map, thao tác sửa có thể không được hỗ trợ hoặc có ràng buộc concurrent khác nhau; kiểm tra hợp đồng triển khai đang dùng.

### Map.compute/merge và giới hạn null

`Map.compute` nhận `BiFunction<? super K,? super V,? extends V>` để tính lại value dựa trên key và giá trị hiện có. Một số lời gọi có thể truyền `null` làm value cũ (khi không có ánh xạ phù hợp); kết quả `null` có thể **xóa ánh xạ**. Vì vậy, không trả `null` vô tình.

~~~java
// Dùng trong một method có Map<String, Integer> stock đã khởi tạo:
stock.compute("A", (code, oldValue) ->
    oldValue == null ? 1 : oldValue + 1);
~~~

Ví dụ trên tăng giá trị A hoặc tạo A với giá trị 1 nếu chưa có. Khi xử lý đồng thời, đặc biệt với `ConcurrentHashMap`, đọc và tuân theo semantics của từng implementation: callback có thể chịu các quy tắc retry/atomicity và không nên chứa tác động bên ngoài khó lặp lại.

### Dùng BiPredicate với Stream.filter

`Stream.filter` nhận `Predicate<T>` (**một tham số**), vì vậy không truyền trực tiếp `BiPredicate<Order,Integer>` vào `filter`. Bạn có thể **cố định một tham số** bằng lambda:

~~~java
// Có List<Order> orders và BiPredicate<Order,Integer> accepted:
int minimum = 200;
List<Order> result = orders.stream()
    .filter(order -> accepted.test(order, minimum))
    .collect(java.util.stream.Collectors.toList());
~~~

Đây là đoạn tích hợp cần `Order` và `accepted` đã định nghĩa, như trong mục 7. Hành vi lọc nên thuần, không sửa `orders` hoặc trạng thái chia sẻ bên trong predicate. Đừng giả định Stream được xử lý song song hoặc nhanh hơn loop trong mọi trường hợp.

## 7. Bài thực hành hoàn chỉnh, output xác định

Tạo file **`BiInterfacesPractice.java`** lưu UTF-8. Ví dụ mô phỏng đơn hàng, kết hợp bộ lọc, tính tổng có phí giao, thực hiện hai hành động và cập nhật tồn kho. Tất cả đều sử dụng API có từ Java 8, nhưng chạy được trên JDK hiện đại.

~~~java
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BiConsumer;
import java.util.function.BiFunction;
import java.util.function.BiPredicate;
import java.util.stream.Collectors;

public class BiInterfacesPractice {
    static final class Order {
        final String code;
        final int quantity;
        final int unitPrice;

        Order(String code, int quantity, int unitPrice) {
            this.code = code;
            this.quantity = quantity;
            this.unitPrice = unitPrice;
        }

        int subtotal() {
            return quantity * unitPrice;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
            new Order("A", 2, 120),
            new Order("B", 1, 80),
            new Order("C", 3, 100)
        );

        BiPredicate<Order, Integer> meetsMinimum =
            (order, minimum) -> order.subtotal() >= minimum;

        BiPredicate<Order, Integer> validOrder =
            (order, minimum) ->
                order.quantity > 0
                && order.unitPrice > 0
                && minimum >= 0;

        BiPredicate<Order, Integer> accepted =
            meetsMinimum.and(validOrder);

        List<String> acceptedCodes = orders.stream()
            .filter(order -> accepted.test(order, 200))
            .map(order -> order.code)
            .collect(Collectors.toList());

        System.out.println(
            "Đơn đạt: " + String.join(", ", acceptedCodes));

        BiFunction<Order, Integer, Integer> addDelivery =
            (order, deliveryFee) -> order.subtotal() + deliveryFee;

        BiFunction<Order, Integer, String> display =
            addDelivery.andThen(total -> total + " VND");

        System.out.println("Tổng A: " + display.apply(orders.get(0), 10));

        BiConsumer<Order, String> print =
            (order, prefix) -> System.out.println(prefix + order.code);

        BiConsumer<Order, String> audit =
            (order, prefix) ->
                System.out.println("Đã ghi: " + order.code);

        print.andThen(audit).accept(orders.get(0), "Kiểm tra: ");

        Map<String, Integer> stock = new LinkedHashMap<String, Integer>();
        stock.put("A", 3);
        stock.put("B", 1);

        stock.replaceAll((code, quantity) -> quantity + 1);
        stock.forEach((code, quantity) ->
            System.out.println("Kho " + code + ": " + quantity));

        System.out.println(
            "B bị loại: " + accepted.negate().test(orders.get(1), 200));
    }
}
~~~

Trong terminal, ở thư mục chứa file, với `javac` hỗ trợ target 8:

~~~text
javac --release 8 -encoding UTF-8 BiInterfacesPractice.java
java BiInterfacesPractice
~~~

Nếu dự án chỉ chạy JDK hiện tại, bạn có thể biên dịch bằng `javac -encoding UTF-8 BiInterfacesPractice.java` theo toolchain tương ứng. `--release 8` chỉ cần khi có yêu cầu API/bytecode tương thích Java 8 và không thay thế kiểm thử thư viện phụ thuộc.

**Stdout dự kiến (7 dòng, đúng thứ tự):**

~~~text
Đơn đạt: A, C
Tổng A: 250 VND
Kiểm tra: A
Đã ghi: A
Kho A: 4
Kho B: 2
B bị loại: true
~~~

### Giải thích kết quả chi tiết

1. `A` có tổng `2 × 120 = 240` và `C` có tổng `3 × 100 = 300`; cả hai đạt ngưỡng `200` và dữ liệu hợp lệ. `B` chỉ `1 × 80 = 80`, không đạt. Stream giữ thứ tự A rồi C, nên in `Đơn đạt: A, C`.
2. `addDelivery.apply(A, 10)` lấy `240 + 10 = 250`. `andThen` chỉ đổi kết quả số nguyên thành chuỗi `"250 VND"`.
3. `print.andThen(audit)` nhận cùng `Order A` và prefix; `print` in `Kiểm tra: A` rồi `audit` in `Đã ghi: A`.
4. `LinkedHashMap` bảo toàn thứ tự chèn A rồi B. `replaceAll` tăng `3→4` và `1→2`; `forEach` in đúng thứ tự đó.
5. `accepted.test(B,200)` là false; `accepted.negate().test(B,200)` là true.

### Kiểm tra nhanh bằng assertion nghiệp vụ

Muốn kiểm tra logic thay vì chỉ đọc stdout, có thể đặt **trước dấu đóng `main`**:

~~~java
if (!accepted.test(orders.get(0), 200)
        || accepted.test(orders.get(1), 200)
        || !accepted.test(orders.get(2), 200)
        || addDelivery.apply(orders.get(0), 10) != 250) {
    throw new AssertionError("Kết quả kiểm tra không đúng");
}
~~~

Nếu điều kiện sai, chương trình ném `AssertionError`. Đây là đoạn bổ sung, không phải tệp độc lập. Trong dự án thực tế, đưa các kiểm tra tương tự vào JUnit và bổ sung các ca lỗi/biên.

## 8. Những lỗi thường gặp khi làm việc với hai tham số

### Sai interface vì hiểu nhầm đầu ra

~~~java
// SAI: BiConsumer không trả kết quả, BiFunction phải trả kết quả.
// BiFunction<Integer, Integer, Integer> bad = (a, b) -> System.out.println(a + b);

// ĐÚNG: muốn tính thì dùng BiFunction.
BiFunction<Integer, Integer, Integer> sum = (a, b) -> a + b;

// ĐÚNG: muốn in ra thì dùng BiConsumer.
BiConsumer<Integer, Integer> log = (a, b) -> System.out.println(a + b);
~~~

### Dùng BiPredicate trong filter không bọc tham số thứ hai

~~~java
// SAI: filter nhận Predicate<Order>, không phải BiPredicate<Order,Integer>.
// orders.stream().filter(accepted);

// ĐÚNG:
orders.stream().filter(order -> accepted.test(order, 200));
~~~

### Hiểu sai andThen

Với `BiFunction`, `andThen` nhận một `Function<R,V>` xử lý **kết quả**; nó không sửa đầu vào thứ nhất hoặc thứ hai. Với `BiConsumer`, `andThen` nhận thêm `BiConsumer<T,U>`, chạy hai hành động **cùng một cặp đối số**. Hai kiểu `andThen` khác nhau hoàn toàn về hợp đồng.

### Sai thứ tự kiểu generic

`BiFunction<String,Integer,Boolean>` nhận `String` trước, `Integer` sau và trả `Boolean`. Đổi chỗ `apply(2, "A")` sẽ lỗi compiler. Tên biến trong lambda không quyết định kiểu; **target type** quyết định.

### Hiểu lầm về checked exception

Các phương thức SAM `test`/`apply`/`accept` **không khai báo checked exception**. Nếu thân lambda gọi `Files.readAllBytes(...)` có thể ném `IOException`, phải xử lý trong lambda hoặc thiết kế interface/adapter khác có hợp đồng phù hợp. Đừng cố thêm `throws IOException` vào lambda hay chữ ký method bao quanh rồi cho rằng vấn đề tự giải quyết.

### Giả định lambda được chạy ngay khi tạo

Biểu thức lambda tạo hành vi. Thân lambda chạy khi được gọi qua `test`/`apply`/`accept` hoặc qua framework sử dụng nó. Tương tự, Stream trung gian như `filter` thường lazy; hành vi thực tế xuất hiện khi terminal operation chạy. Điều này ảnh hưởng thời điểm phát sinh ngoại lệ và side effect.

### Giữ state mutable trong lambda

Nếu `BiConsumer` ghi vào danh sách dùng chung từ nhiều thread, chương trình có thể gặp race condition. `Map.forEach` trên loại Map thông thường không tự biến việc xử lý thành atomic/thread-safe. Dùng thiết kế không chia sẻ mutable state khi có thể; nếu bắt buộc chia sẻ, chọn công cụ đồng bộ hoặc cấu trúc concurrent với hợp đồng đúng.

## 9. API liên quan đang hữu ích và cách chọn

| API | Khác biệt | Dùng khi |
| --- | --- | --- |
| `Predicate<T>` | Một đối số → boolean | Điều kiện một đầu vào, ví dụ `Stream.filter` |
| `BiPredicate<T,U>` | Hai đối số → boolean | Điều kiện cần đối tượng và ngưỡng/cấu hình |
| `Function<T,R>` | Một đối số → `R` | Biến đổi một giá trị |
| `BiFunction<T,U,R>` | Hai đối số → `R` | Phối hợp hai dữ liệu để tính/biến đổi |
| `BinaryOperator<T>` | Hai `T` → một `T` | Phép kết hợp, `reduce`, giá trị đồng kiểu |
| `Consumer<T>` | Một đối số → `void` | Hành động một đầu vào |
| `BiConsumer<T,U>` | Hai đối số → `void` | Hành động với key/value hoặc đối tượng/ngữ cảnh |
| `ToIntBiFunction<T,U>` | Hai đối số → `int` primitive | Kết quả số nguyên, giảm boxing khi phù hợp |
| `ObjIntConsumer<T>` | Một đối tượng và một `int` → `void` | Hành động cần đối tượng và tham số int primitive |

`BiPredicate` dùng kết quả boolean primitive nên không boxing ở **kết quả**, nhưng `T`/`U` vẫn là tham số reference (generic không nhận primitive trực tiếp). `ToIntBiFunction<T,U>` trả kiểu `int` nguyên thủy và có phương thức `applyAsInt`; `ObjIntConsumer<T>` nhận `T` và `int` với phương thức `accept`.

Tránh tối ưu sớm bằng cách đổi tất cả callback sang biến thể primitive. Chỉ cần quan tâm boxing khi số lượng xử lý và số đo hiệu năng cho thấy nó đáng kể, đồng thời API sử dụng có chấp nhận đúng kiểu chức năng.

## 10. Thiết kế code rõ ràng với functional interface

1. **Chọn interface theo ý nghĩa**, không theo độ ngắn của lambda. Điều kiện dùng `BiPredicate`, phép tính dùng `BiFunction`, hành động dùng `BiConsumer`.
2. **Đặt tên tham số theo vai trò**: `(order, minimumTotal)` dễ hiểu hơn `(x, y)` trong nghiệp vụ. Tham số thứ hai có thể là context, ngưỡng hoặc cấu hình; tài liệu phải nêu đơn vị của nó.
3. **Tách tính toán và side effect**: có thể dùng `BiFunction` tính số và `BiConsumer` hiển thị/ghi nhận; quy tắc này giúp test dễ hơn.
4. **Giữ thứ tự/điều kiện có chủ đích**: `and`/`or` short-circuit; `andThen` thực hiện theo thứ tự. Không dựa vào tác động phụ trong predicate để bảo đảm mọi bước chạy.
5. **Kiểm tra dữ liệu không hợp lệ trước**: null, số âm, đơn vị sai, tràn số. Các ví dụ tính tiền dạng `int` phục vụ bài học về interface, chưa phải mô hình tiền tệ production.
6. **Giữ API được bảo trì**: chọn JDK và phiên bản dependency được cập nhật; các interface này vẫn là API chuẩn, không cần dùng tiện ích custom thay thế không rõ lợi ích.
7. **Test đường thành công và thất bại**: với `BiPredicate` kiểm thử biên true/false; với `BiFunction` kiểm thử đầu ra/exception; với `BiConsumer` kiểm thử thứ tự tác động và cách xử lý lỗi nếu bước sau thất bại.
8. **Không ép mọi callback thành lambda**: method reference hoặc phương thức có tên thường rõ nghĩa hơn khi thân lambda phức tạp hoặc được sử dụng nhiều lần.

## 11. Bài tập tự luyện

**Bài 1 — BiPredicate và ngưỡng:** Cho danh sách đơn A/B/C trong mục 7, thay ngưỡng `200` bằng `250`. Hãy dự đoán đơn được chọn. Đáp án: chỉ **C**, vì A=240, B=80, C=300. Thử `accepted.negate().test(A,250)` và giải thích vì sao true.

**Bài 2 — Kết hợp or:** Định nghĩa `BiPredicate<Order,Integer> highQuantity = (order, ignored) -> order.quantity >= 3;`. Ghép `meetsMinimum.or(highQuantity)`. Thử ngưỡng 250; C thỏa cả hai, A/B không thỏa. Đổi B thành quantity 3 để quan sát ngắn mạch và kết quả mới.

**Bài 3 — andThen của BiFunction:** Thay phí giao hàng A từ 10 thành 20; kết quả `display.apply(A,20)` sẽ là `260 VND`. Viết thêm `andThen` để trả đối tượng DTO chứa số tiền và nhãn, thay vì chỉ nối chuỗi.

**Bài 4 — BiConsumer và lỗi:** Tạo consumer đầu in `"Đã nhận"`, consumer thứ hai cố ý ném `IllegalStateException`. Kiểm tra bước đầu vẫn in ra trước exception; giải thích tại sao `andThen` không tự rollback.

**Bài 5 — Map và thứ tự:** Thử thay `LinkedHashMap` bằng `HashMap`. Giải thích vì sao không được viết test đòi thứ tự in giống nhau trên mọi môi trường nếu contract của Map không quy định thứ tự. Thực hiện `replaceAll`, kiểm tra giá trị mới theo key thay vì dựa vào thứ tự.

**Bài 6 — Stream adapter:** Tạo hàm lọc nhận `BiPredicate<Order,Integer>` và giá trị minimum, trả một `Predicate<Order>` bằng `order -> rule.test(order, minimum)`. Dùng nó với `Stream.filter`; giải thích khái niệm "cố định" tham số thứ hai.

**Bài 7 — Kiểu nguyên thủy:** Thay `BiFunction<Order,Integer,Integer>` bằng `ToIntBiFunction<Order,Integer>` cho phép tính số; dùng `applyAsInt` thay `apply` và quan sát sự khác biệt trong kiểu trả về. Nếu cần định dạng chuỗi, chuyển kết quả thành chuỗi ở bước riêng.

**Đạt mục tiêu khi** bạn chọn đúng ba interface, biết chữ ký phương thức của từng loại, dùng được `and`/`or`/`negate` và `andThen` đúng ý nghĩa, giải thích được `Map`/`Stream` integration, chạy chương trình độc lập với stdout chính xác và phân biệt được logic thuần với side effect.

## 12. Tài liệu chính thức

- Java SE API `BiPredicate`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/BiPredicate.html
- Java SE API `BiFunction`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/BiFunction.html
- Java SE API `BiConsumer`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/BiConsumer.html
- Java SE API `Map` và các method `forEach`/`replaceAll`/`compute`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html
- Java Language Specification, lambda expressions: https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27

Các liên kết dùng để xác minh API và hành vi trên JDK hiện hành. Kiểm tra tài liệu đúng phiên bản dự án khi triển khai, nhất là semantics concurrency và giới hạn thư viện phụ thuộc.