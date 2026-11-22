# `Consumer<T>` trong Java: thực hiện thao tác không trả về kết quả

## 1. `Consumer<T>` là gì?

`Consumer<T>` là **functional interface** thuộc package `java.util.function`. Nó mô tả một thao tác **nhận một giá trị kiểu `T`, thực thi hành động và không trả về kết quả**. Tên `Consumer` gợi ý rằng thao tác *tiêu thụ* đầu vào: ghi log, in dữ liệu, gửi thông báo, cập nhật một đối tượng, gọi một dịch vụ hoặc chuyển dữ liệu tới một nơi nhận.

Phương thức trừu tượng duy nhất (SAM) là:

~~~java
void accept(T value);
~~~

Đây là **chữ ký minh họa** của một phương thức bên trong interface, không phải chương trình Java độc lập. Gọi `accept(value)` để thực hiện hành động. Với functional interface, có thể cung cấp hành động bằng **lambda** hoặc **method reference**. Ví dụ:

~~~java
Consumer<String> print = message -> System.out.println(message);
print.accept("Hello Java");
~~~

Đoạn trên được đặt bên trong phương thức có import `java.util.function.Consumer`. Kết quả in ra:

~~~text
Hello Java
~~~

Điểm quan trọng: **`accept` có kiểu trả về `void`**, không có nghĩa nó không thực hiện công việc hoặc không thay đổi trạng thái. Trái lại, `Consumer` thường được chọn khi mục đích là một tác dụng phụ (*side effect*) có chủ đích. Tuy nhiên, lambda của `Consumer` cũng có thể chỉ quan sát dữ liệu, hoặc không làm gì; API không buộc nó phải gây ra thay đổi.

### Mục tiêu sau bài học

Người học cần có khả năng:

- Khai báo, nhận và gọi `Consumer<T>` bằng `accept`; đọc được kiểu của `T`.
- Dùng lambda hoặc method reference để biểu diễn hành động không trả về kết quả.
- Phân biệt `Consumer<T>` với `Function<T,R>`, `Predicate<T>`, `Supplier<T>` và `Runnable`.
- Kết hợp các hành động bằng `andThen` và hiểu đúng thứ tự, lỗi, hành vi với `null`.
- Dùng `Consumer` tại các điểm xử lý phù hợp như `Iterable.forEach`, `Stream.forEach`, callback hoặc hàm nhận hành động.
- Kiểm soát side effect, hiệu ứng khi chạy song song và các lỗi phổ biến.

Các ví dụ độc lập trong bài dùng **Java 17 trở lên**.

## 2. Cấu trúc và hợp đồng API

Có thể hình dung các thành viên công khai chính như bảng sau:

| Thành viên | Loại | Vai trò |
| --- | --- | --- |
| `void accept(T t)` | **Abstract method duy nhất** | Thực hiện hành động với một đầu vào |
| `Consumer<T> andThen(Consumer<? super T> after)` | **Default method** | Tạo `Consumer` kết hợp, chạy hành động hiện tại rồi đến `after` |

Interface cũng được gắn `@FunctionalInterface` trong thư viện chuẩn. Phương thức `andThen` có phần thân mặc định nên **không thêm SAM**. Đó là lý do `Consumer<T>` vẫn dùng được với lambda.

### Vì sao dùng kiểu generic `T`?

`T` là kiểu đầu vào, được kiểm tra tại thời điểm biên dịch. Ví dụ:

~~~java
Consumer<String> printName = System.out::println;
Consumer<Integer> printNumber = System.out::println;
~~~

Với `printName`, `accept` nhận `String`; với `printNumber`, `accept` nhận `Integer`. Cùng một method reference `System.out::println` có thể phù hợp nhiều chữ ký, và compiler chọn overload theo **target type**.

Một `Consumer<Order>` không mặc nhiên là `Consumer<Object>` vì generic Java là invariant. Khi API muốn nhận một hành động xử lý `T` hoặc các kiểu cha của `T`, mẫu tham số hữu ích là `Consumer<? super T>`; phần `andThen` của `Consumer` cũng dùng mẫu này. Không dùng ép kiểu tùy tiện để đánh lừa compiler.

### `accept` không có kết quả để dùng tiếp

Ví dụ dưới đây **không hợp lệ**:

~~~java
// Lỗi biên dịch: accept(...) trả về void, không thể gán vào biến.
Consumer<String> printer = System.out::println;
String text = printer.accept("Java");
~~~

Đây là ví dụ lỗi có chủ đích. Nếu muốn **biến đổi `String` thành `String`**, hãy dùng `Function<String,String>`; nếu muốn **kiểm tra điều kiện**, dùng `Predicate<String>`. Chọn interface theo hợp đồng đầu vào và đầu ra, không chỉ theo việc cú pháp lambda trông giống nhau.

## 3. Viết `Consumer` bằng lambda và method reference

### 3.1. Lambda một biểu thức

~~~java
Consumer<String> print = text -> System.out.println(text);
print.accept("Java");
~~~

Vế trái `text` là tham số được compiler suy luận kiểu `String` từ `Consumer<String>`. Vế phải thực hiện một lệnh in. Không có `return` giá trị.

### 3.2. Lambda dạng block nhiều lệnh

~~~java
Consumer<String> printUpper = text -> {
    String normalized = text.trim().toUpperCase(java.util.Locale.ROOT);
    System.out.println(normalized);
};
printUpper.accept("  java  "); // In JAVA
~~~

Với block lambda của `Consumer`, có thể dùng `return;` để kết thúc sớm, **không thể viết `return someValue;`**. Một biểu thức có giá trị trả về như `list.add(item)` đôi khi vẫn được phép làm *statement expression* của một lambda tương thích `void`; nhưng để người đọc thấy rõ side effect, có thể dùng block và bỏ qua kết quả một cách tường minh.

### 3.3. Method reference

Nếu lambda chỉ gọi thẳng một phương thức phù hợp, method reference thường gọn hơn:

~~~java
Consumer<String> print = System.out::println;
print.accept("One");
~~~

`System.out` là đối tượng cụ thể; `::println` là tham chiếu tới instance method. Một ví dụ khác: `Consumer<String> action = logger::info;` chỉ có ý nghĩa nếu `logger` hiện hữu và phương thức `info` nhận kiểu phù hợp. Không phải method reference nào cũng khớp với `Consumer`: compiler vẫn kiểm tra số và kiểu tham số, ngoại lệ và khả năng tương thích với `void`.

### 3.4. Callback nhận `Consumer`

API tự viết có thể nhận hành động như một tham số:

~~~java
static void processName(String name, Consumer<String> action) {
    action.accept(name);
}
~~~

Đây là **phương thức minh họa**, cần đặt trong class có import `Consumer`. Có thể gọi `processName("Lan", System.out::println)` hoặc truyền lambda ghi log. Việc chuyển hành động thành tham số giúp tái sử dụng phần điều phối trong khi người gọi quyết định làm gì với dữ liệu.

Nếu `action` là `null`, lời gọi `action.accept` sẽ gây `NullPointerException`; khi thiết kế API công khai, có thể dùng `Objects.requireNonNull(action, "action")` để phát hiện lỗi sớm và thông báo rõ hơn.

## 4. `andThen`: ghép các thao tác theo thứ tự

Phương thức:

~~~java
Consumer<T> andThen(Consumer<? super T> after)
~~~

là **chữ ký API minh họa**, không phải chương trình độc lập. Với `first.andThen(second)`, `Consumer` được trả về sẽ:

1. Chạy `first.accept(input)`.
2. Sau khi bước một hoàn thành bình thường, chạy `second.accept(input)`.

**Hai hành động nhận cùng một giá trị đầu vào**; kết quả của hành động đầu không được truyền sang hành động sau vì `accept` trả `void`. `andThen` tạo đối tượng hành động kết hợp; nó chưa chạy gì cho tới khi được gọi `accept` (hoặc API như `forEach` gọi hộ).

Ví dụ minh họa:

~~~java
Consumer<String> mark = s -> System.out.println("START " + s);
Consumer<String> save = s -> System.out.println("SAVE " + s);
Consumer<String> pipeline = mark.andThen(save);
pipeline.accept("A1");
~~~

Kết quả:

~~~text
START A1
SAVE A1
~~~

### Điều gì xảy ra khi có lỗi?

Nếu `first.accept(input)` ném exception, `second.accept(input)` **không chạy**; exception được chuyển tiếp tới người gọi. Nếu `second` ném exception, hành động đầu tiên đã có thể tạo ra side effect, và không có cơ chế tự rollback. Vì vậy, `andThen` **không phải transaction**.

`first.andThen(null)` gây `NullPointerException` theo hợp đồng API của `Consumer.andThen`. Điều này khác với việc gọi `first.accept(null)`: `Consumer` không tự cấm input `null`; hành vi nhận `null` phụ thuộc vào implementation.

Một điểm hữu ích của `Consumer<? super T>`: có thể nối `Consumer<Object>` sau một `Consumer<String>`, vì hành động chấp nhận `Object` có thể xử lý mọi `String`. Tuy nhiên, đây vẫn là chuỗi hành động; nếu cần **truyền đầu ra của phép biến đổi trước sang bước sau**, hãy dùng `Function.andThen` hoặc thiết kế pipeline dữ liệu.

### Cảnh báo về thứ tự và đối tượng mutable

Cùng một tham chiếu `input` được truyền cho cả hai hành động. Nếu `first` sửa trạng thái đối tượng mutable, `second` có thể nhìn thấy trạng thái đã thay đổi. Do đó thứ tự trong `andThen` quan trọng và thường không được đảo lại tùy tiện.

Ví dụ, `validate.andThen(save)` có thể hợp lý khi `validate` ném exception nếu dữ liệu sai; `save.andThen(validate)` có thể ghi dữ liệu trước khi kiểm tra, gây hậu quả khác. Với xử lý yêu cầu tính nguyên tử, phải dùng cơ chế transaction hoặc bù trừ thích hợp thay vì trông đợi `andThen` cung cấp.

## 5. Chương trình Java 17 hoàn chỉnh

Bài toán: xử lý ba đơn hàng. Với mỗi đơn, ghi một sự kiện vào danh sách và cộng số tiền vào bộ đếm. Dùng `Consumer<Order>` riêng cho từng hành động rồi ghép bằng `andThen`. Ví dụ dùng tuần tự để thứ tự dễ quan sát.

Tạo tệp **`ConsumerDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

public class ConsumerDemo {
    record Order(String id, int amount) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A1", 120),
                new Order("B2", 80),
                new Order("C3", 50)
        );

        List<String> events = new ArrayList<>();
        AtomicInteger total = new AtomicInteger();

        Consumer<Order> recordEvent =
                order -> events.add("Processed " + order.id());

        Consumer<Order> addAmount =
                order -> total.addAndGet(order.amount());

        Consumer<Order> process =
                recordEvent.andThen(addAmount);

        orders.forEach(process);

        System.out.println(events);
        System.out.println(total.get());

        Consumer<String> printUpper =
                value -> System.out.println(value.toUpperCase(Locale.ROOT));
        printUpper.accept("done");
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 ConsumerDemo.java
java ConsumerDemo
~~~

**Stdout chính xác:**

~~~text
[Processed A1, Processed B2, Processed C3]
250
DONE
~~~

Giải thích:

- `record Order(String id, int amount)` tạo kiểu dữ liệu bất biến theo các thành phần ở mức record, phù hợp lưu thông tin đơn hàng đơn giản.
- `recordEvent` ghi thêm chuỗi mô tả vào `events`; đây là **tác dụng phụ** và `List` sử dụng ở đây là mutable.
- `addAmount` cập nhật một bộ đếm. Phương thức `AtomicInteger.addAndGet` trả về số mới nhưng lambda `Consumer` không sử dụng giá trị trả về.
- `recordEvent.andThen(addAmount)` tạo hành động kép; `orders.forEach(process)` gọi hành động đó trên từng phần tử theo thứ tự của danh sách.
- Dòng `System.out.println(events)` in ba sự kiện theo thứ tự xử lý; tổng `120 + 80 + 50 = 250`.
- `printUpper` là `Consumer<String>` không lưu kết quả và chỉ in chuỗi sau biến đổi.

**Giới hạn thực tế:** `AtomicInteger` giúp phép cập nhật số đếm riêng lẻ an toàn khi có nhiều thread, nhưng `ArrayList events` ở ví dụ **không an toàn để nhiều thread cùng sửa**. Không chuyển tùy tiện ví dụ này sang `parallelStream().forEach(process)`. Ngoài ra, dù từng phép cộng có thể an toàn, sự phối hợp giữa ghi sự kiện và cộng tổng không trở thành một thao tác nguyên tử.

## 6. `Consumer` với Collections và Stream

### 6.1. `Iterable.forEach`

`Iterable.forEach(Consumer<? super T> action)` nhận một `Consumer` và gọi nó với các phần tử được duyệt. Với `List` có thứ tự, người học thường thấy các hành động chạy theo thứ tự duyệt. Dùng khi mục đích chính là **thực hiện hành động trên từng phần tử**:

~~~java
List<String> names = List.of("An", "Bình", "Chi");
names.forEach(System.out::println);
~~~

Đây là **đoạn mã trong phương thức** với import `java.util.List`. Nó in lần lượt `An`, `Bình`, `Chi`. Nếu mục đích là **tạo danh sách mới**, hãy ưu tiên phép biến đổi dữ liệu và thu kết quả thay vì dùng `forEach` để sửa danh sách bên ngoài.

### 6.2. `Stream.forEach`

Trong Stream API, `forEach(Consumer<? super T> action)` là **terminal operation**. Ví dụ:

~~~java
List.of("a", "bb", "ccc").stream()
        .filter(s -> s.length() >= 2)
        .forEach(System.out::println);
~~~

Chương trình trên in `bb` và `ccc` trong trường hợp stream tuần tự nêu trên. Pipeline không trả về collection kết quả từ `forEach`; thao tác chủ yếu là side effect. `Stream.forEach` được định nghĩa là thao tác không bảo đảm thứ tự khi thực thi với stream song song, và mỗi hành động có thể chạy ở thread khác nhau.

Nếu cần giữ thứ tự *encounter order* với stream có thứ tự, có `forEachOrdered`. Tuy nhiên, **bảo toàn thứ tự không đồng nghĩa toàn bộ shared state trở nên thread-safe** hoặc có transaction. Nếu cần kết quả là một cấu trúc dữ liệu, nên dùng `map`, `filter`, `collect`, `toList` hoặc phép giảm thích hợp.

### 6.3. Vì sao `peek` không phải chỗ xử lý nghiệp vụ?

`Stream.peek(Consumer<? super T>)` là thao tác **trung gian**; nó hữu ích khi quan sát/debug một pipeline, nhưng các thao tác trung gian thường lazy. Một pipeline có thể không thực thi thao tác phụ nếu không có terminal operation; ngoài ra tối ưu hóa của Stream có thể bỏ qua các bước hoặc phần tử không cần thiết, chẳng hạn `count()` trong một số trường hợp. Không đặt hành vi quan trọng như ghi tiền, gửi email, cập nhật trạng thái nghiệp vụ trong `peek` rồi giả định chắc chắn mỗi phần tử được xử lý đúng một lần.

Khi side effect là mục tiêu cuối, `forEach` có thể phù hợp. Khi mục tiêu là chuyển dữ liệu thành kết quả, ưu tiên thao tác thuần và collector.

## 7. So sánh `Consumer` với các functional interface liên quan

| Functional interface | Chữ ký khái quát | Chọn khi |
| --- | --- | --- |
| `Consumer<T>` | `T -> void` | Thực hiện hành động với một đầu vào |
| `BiConsumer<T,U>` | `(T,U) -> void` | Hành động cần hai đầu vào |
| `Function<T,R>` | `T -> R` | Chuyển đổi dữ liệu và cần kết quả |
| `Predicate<T>` | `T -> boolean` | Đánh giá điều kiện đúng/sai |
| `Supplier<T>` | `() -> T` | Tạo/cung cấp giá trị khi được gọi |
| `Runnable` | `() -> void` | Chạy hành động không có đầu vào |

**Tình huống thực tế:** nếu hệ thống cần chuyển một `Order` thành DTO, hãy dùng `Function<Order,OrderDto>`; nếu cần kiểm tra đơn có hợp lệ, dùng `Predicate<Order>`; nếu cần log hoặc gửi sự kiện về đơn, `Consumer<Order>` thường phù hợp.

`Runnable` thuộc `java.lang`, có phương thức `run()` không nhận tham số. `Consumer<T>` có `accept(T)` nên nhận dữ liệu từ nơi gọi. Chọn đúng interface giúp API phản ánh ý định.

### Kiểu nguyên thủy và tự động boxing

`Consumer<Integer>` nhận đối tượng `Integer`; nếu liên tục xử lý các `int`, có thể dùng `IntConsumer` để tránh boxing không cần thiết. Package `java.util.function` còn có:

- `IntConsumer`, `LongConsumer`, `DoubleConsumer`: nhận một giá trị nguyên thủy tương ứng và trả `void`.
- `BiConsumer<T,U>`: nhận hai đối tượng và trả `void`.
- `ObjIntConsumer<T>`, `ObjLongConsumer<T>`, `ObjDoubleConsumer<T>`: nhận một object và một giá trị nguyên thủy tương ứng.

Ví dụ đoạn mã trong phương thức:

~~~java
java.util.function.IntConsumer printDouble =
        value -> System.out.println(value * 2);
printDouble.accept(6); // In 12

java.util.function.BiConsumer<String, Integer> printEntry =
        (name, score) -> System.out.println(name + ": " + score);
printEntry.accept("An", 9); // In An: 9
~~~

`BiConsumer` cũng có `andThen`, nhưng với hai tham số; không nhầm sang `BiFunction<T,U,R>` vì BiFunction phải trả về giá trị.

## 8. Tác dụng phụ, biến captured và lỗi về trạng thái

### 8.1. Lambda và effectively final

Lambda có thể sử dụng biến cục bộ được khai báo `final` hoặc **effectively final**. Ví dụ hợp lệ:

~~~java
List<String> log = new ArrayList<>();
Consumer<String> addLog = item -> log.add(item);
addLog.accept("saved");
~~~

Đây là code đặt trong phương thức với import phù hợp. Biến tham chiếu `log` không bị gán lại, nên là effectively final, nhưng **nội dung của đối tượng List vẫn có thể thay đổi**. `Consumer` không làm cho side effect trở nên thuần hoặc thread-safe.

Ví dụ lỗi có chủ đích:

~~~java
int count = 0;
Consumer<String> counter = text -> count++; // Không biên dịch
~~~

`count` là biến cục bộ bị lambda capture rồi thay đổi nên vi phạm quy tắc effectively final. Đừng khắc phục máy móc bằng một mảng `int[]` chỉ để có thể sửa giá trị; điều đó thường làm trạng thái khó quản lý và không bảo đảm an toàn concurrent.

### 8.2. Có nên dùng `AtomicInteger` để cộng tổng?

Nếu mục tiêu chính là **tính toán tổng**, hãy ưu tiên reduction:

~~~java
int sum = List.of(10, 20, 30).stream()
        .mapToInt(Integer::intValue)
        .sum(); // 60
~~~

Đoạn này trả về một kết quả rõ ràng, không cần cập nhật biến ngoài pipeline. Dùng `Consumer` cập nhật `AtomicInteger` sẽ phù hợp hơn khi bản thân hành động cập nhật trạng thái là mục đích rõ ràng, và phải xét tính đúng trong môi trường thực thi cụ thể.

### 8.3. Stream song song và thread safety

Không giả định `parallelStream().forEach(consumer)` sẽ gọi `Consumer` tuần tự hoặc theo thứ tự nguồn. Nếu nhiều thread sửa `ArrayList`, `HashMap` hoặc biến có thể thay đổi khác mà không có phối hợp phù hợp, có thể xảy ra race condition, mất dữ liệu hoặc kết quả không dự đoán được. Đồng thời, chỉ vì một đối tượng như `AtomicInteger` có cập nhật nguyên tử không có nghĩa toàn bộ workflow gồm nhiều side effect an toàn.

Chỉ chọn thực thi song song khi thuật toán có thể chia nhỏ an toàn, phép gộp đáp ứng hợp đồng và có bằng chứng về lợi ích. Với công việc cần kết quả tổng hợp, collector/reduction đúng hợp đồng thường đơn giản và dễ kiểm thử hơn.

### 8.4. Checked exception trong `Consumer`

`Consumer.accept(T)` không khai báo checked exception. Vì thế, một lambda của `Consumer` không thể trực tiếp ném checked exception từ phương thức gọi mà không xử lý hoặc chuyển đổi phù hợp. Ví dụ `Files.writeString(path, text)` có thể ném `IOException`; nếu đặt vào lambda truyền cho `forEach`, cần quyết định xử lý tại chỗ, đưa lỗi vào kết quả nghiệp vụ, dùng API có hợp đồng cho phép checked exception, hoặc chuyển thành unchecked exception **với ngữ cảnh lỗi rõ ràng**.

Không nuốt exception bằng `catch (Exception ignored) {}` chỉ để làm code biên dịch. Trong `andThen`, exception của bước đầu sẽ khiến bước sau không chạy; exception của bước sau không tự hoàn tác hành động đầu.

### 8.5. `null` và validation

`Consumer<T>` không đảm bảo không nhận `null`. Ví dụ `Consumer<String> printUpper = s -> System.out.println(s.toUpperCase());` sẽ ném `NullPointerException` nếu gọi `accept(null)`. Nếu hợp đồng yêu cầu dữ liệu khác `null`, kiểm tra rõ ở phía trước hoặc trong hành động. Nếu `null` là giá trị hợp lệ, cần định nghĩa cách xử lý thay vì mặc định mọi Consumer có hành vi thống nhất.

## 9. Các lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| Cố gán kết quả `consumer.accept(x)` | `accept` trả `void` | Dùng `Function` khi cần đầu ra |
| Nghĩ `andThen` chạy ngay khi khai báo | Nó chỉ tạo Consumer mới | Gọi `accept` hoặc truyền vào API thực thi |
| Dùng `andThen` như `Function.andThen` | Hai consumer nhận **cùng** input, không truyền kết quả | Dùng `Function` cho pipeline biến đổi |
| Gọi `andThen(null)` | `after` bắt buộc không `null` | Truyền hành động hợp lệ |
| Coi `andThen` là transaction | Bước sau lỗi không hoàn tác bước đầu | Thiết kế xử lý lỗi/transaction riêng |
| Gán lại biến cục bộ bị lambda capture | Vi phạm effectively final | Trả kết quả hoặc dùng đối tượng quản lý trạng thái phù hợp |
| Dùng `forEach` để tạo `List` mới bằng `add` | Side effect ngoài pipeline, khó kiểm soát | Dùng `map(...).toList()` hoặc `collect` |
| Dùng `parallelStream().forEach` sửa `ArrayList` chung | Tranh chấp truy cập shared state | Tránh mutable shared state, dùng collector đúng |
| Dựa vào `peek` để ghi nghiệp vụ | Lazy/optimization có thể bỏ qua lời gọi | Chọn terminal action rõ ràng hoặc xử lý ngoài pipeline |
| Giấu checked exception trong lambda | Mất thông tin lỗi nghiệp vụ | Xây hợp đồng xử lý lỗi phù hợp |
| Quá nhiều side effect trong một Consumer | Khó debug và khó tái sử dụng | Tách hành động có tên, giữ thứ tự rõ bằng `andThen` khi phù hợp |
| Dùng `Consumer<Integer>` trong hot path số nguyên lớn | Boxing/unboxing có thể gây chi phí | Cân nhắc `IntConsumer` và đo benchmark phù hợp |

## 10. Bài tập thực hành có định hướng

### Bài 1 — In nội dung có tiền tố

Viết `Consumer<String> printer` để in `"LOG: "` cộng với thông điệp. Gọi `printer.accept("start")`; kết quả mong đợi là `LOG: start`. Viết lại bằng method reference nếu có sẵn một phương thức instance khớp chữ ký.

### Bài 2 — Chạy hai hành động nối tiếp

Tạo `Consumer<String> first` in `"A:"` + chuỗi và `Consumer<String> second` in `"B:"` + chuỗi. Ghép `first.andThen(second)`, gọi với `"x"`, xác nhận output lần lượt `A:x` rồi `B:x`. Sau đó sửa `first` để ném `IllegalStateException` và xem vì sao `second` không chạy.

### Bài 3 — Tạo callback ghi kết quả

Viết phương thức `static void notifyName(String name, Consumer<String> callback)`, trong đó chỉ gọi `callback.accept(name)` khi tên không trống. Truyền `System.out::println` hoặc lambda ghi vào danh sách. Thử với tên rỗng, `null` và tên hợp lệ; nêu hợp đồng xử lý của phương thức.

### Bài 4 — Phân biệt tiêu thụ và chuyển đổi

Cho `List<String> words = List.of("a", "bb", "ccc");`. Hãy:
1. Dùng `Consumer<String>` và `forEach` để in từ.
2. Dùng `Function<String,Integer>` kết hợp `map` để tạo danh sách độ dài `[1, 2, 3]`.
3. Giải thích vì sao không thể thay thế trực tiếp `Function` bằng `Consumer` trong bước 2.

### Bài 5 — Kiểm tra tính đúng trong tác dụng phụ

Từ danh sách đơn hàng có `amount`, so sánh hai cách tính tổng: cập nhật trạng thái ngoài qua `Consumer<Order>` và dùng `mapToInt(...).sum()`. Kiểm tra danh sách rỗng, dữ liệu trùng lặp và thứ tự khác nhau. Với tổng có thể vượt `int`, cân nhắc `mapToLong` hoặc mô hình số tiền thích hợp. Giải thích lựa chọn cho code sản xuất.

### Bài 6 — Consumer chuyên biệt

Viết `IntConsumer` in bình phương của số nguyên và `BiConsumer<String,Integer>` in tên cùng điểm. Giải thích khác biệt kiểu tham số và tại sao `IntConsumer` có thể tránh boxing so với `Consumer<Integer>`.

## 11. Câu hỏi tự kiểm tra

**1. `Consumer<T>` nhận gì và trả gì?** Nhận một giá trị `T`; `accept` trả `void`.

**2. `Consumer<T>` có bao nhiêu SAM?** Một, là `accept(T)`. `andThen` là default method nên không tăng SAM.

**3. `andThen` có chuyển giá trị từ action thứ nhất sang thứ hai?** Không. Hai action nhận cùng input, chạy tuần tự khi composed consumer được gọi.

**4. Action thứ nhất ném exception thì điều gì xảy ra?** Action sau không được thực thi, exception được chuyển tiếp. Các side effect đã thực hiện trước lỗi có thể vẫn tồn tại.

**5. `Consumer` có buộc phải tạo tác dụng phụ không?** Không. `void` chỉ xác định việc không trả giá trị; tác dụng thực tế tùy implementation.

**6. Khi nào tránh `Consumer`?** Khi cần kết quả để tính tiếp (`Function`), kiểm tra boolean (`Predicate`), hoặc thu tập kết quả qua Stream mà không cần shared state.

**7. Vì sao gọi `accept(null)` có thể lỗi?** Vì generic `T` là kiểu tham chiếu không đảm bảo non-null; lambda hoặc method reference có thể dereference `null`.

**8. Với stream song song, `Consumer` có tự động an toàn không?** Không. Shared mutable state và tính độc lập của side effect cần được xem xét riêng.

## 12. Tóm lược và tài liệu tham chiếu

**`Consumer<T>` là một functional interface chuyên biểu diễn hành động `T -> void`.** `accept` là phương thức trừu tượng duy nhất; `andThen` cho phép nối các hành động theo thứ tự, với cùng đầu vào và không có rollback tự động. Khi cần kết quả mới, dùng `Function` hoặc phép tổng hợp dữ liệu. Khi muốn thực hiện hành động, có thể truyền `Consumer` làm callback, dùng với `Iterable.forEach` hay `Stream.forEach`, đồng thời quản lý rõ side effect, ngoại lệ, `null`, thứ tự và concurrency.

Tài liệu chuẩn để tra cứu hợp đồng chính xác: Javadoc Java SE 17 của `java.util.function.Consumer`, `java.util.function.BiConsumer`, `java.util.function.IntConsumer`, `java.lang.Iterable` và `java.util.stream.Stream`.
