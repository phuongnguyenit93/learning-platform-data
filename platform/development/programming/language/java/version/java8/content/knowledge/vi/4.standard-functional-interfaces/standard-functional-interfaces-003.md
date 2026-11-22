# Consumer và thao tác không trả kết quả trong Java

`Consumer<T>` là **functional interface** tiêu chuẩn trong `java.util.function`, dùng để diễn tả một thao tác **nhận một giá trị kiểu `T` và không trả kết quả cho người gọi**. Phương thức chức năng của nó là `void accept(T value)`. Vì không tạo ra kết quả, `Consumer` thường thích hợp với tác vụ có **side effect** rõ ràng: ghi log, phát sự kiện, cập nhật đối tượng đích, hiển thị dữ liệu, gọi một API mang ý nghĩa thực thi hành động.

Một lambda phù hợp `Consumer` diễn tả **làm gì với dữ liệu**, khác với `Function<T,R>` diễn tả **biến dữ liệu thành giá trị nào**. Chọn đúng giao diện giúp thiết kế API rõ hơn và tránh lỗi bỏ phí kết quả tính toán.

Các nguyên tắc ở đây đã có từ Java 8 và **vẫn áp dụng trong Java hiện đại**; ví dụ được biên dịch trên JDK 17, không phụ thuộc cơ chế đã lỗi thời.

## 1. Hợp đồng của `Consumer<T>`

Chữ ký quan trọng:

~~~java
@FunctionalInterface
public interface Consumer<T> {
    void accept(T value);
    default Consumer<T> andThen(Consumer<? super T> after) { /* ... */ }
}
~~~

Đây là **sơ đồ chữ ký rút gọn** để học, không phải mã cần cài lại hoặc định nghĩa thay cho thư viện chuẩn. `andThen` có phần thân thực tế do JDK cung cấp. Sử dụng bằng cách import:

~~~java
import java.util.function.Consumer;
~~~

Và viết:

~~~java
Consumer<String> print = message -> System.out.println(message);
print.accept("Hello");
~~~

Hai dòng sau `import` là **đoạn mã minh họa trong một phương thức**. `message` được suy ra là `String` từ `Consumer<String>`. Gọi `accept("Hello")` thực hiện hành động in chuỗi. Bản thân `accept` trả `void`: không có một giá trị để gán cho biến, truyền vào `map` hoặc dùng trong biểu thức tiếp theo.

Điều đó **không có nghĩa** `Consumer` “không làm gì”: kết quả hữu ích của nó có thể là một hiệu ứng bên ngoài, ví dụ hàng đợi nhận sự kiện, bộ đếm tăng, tệp được ghi hoặc danh sách bị thay đổi.

### Đặt cạnh các functional interface khác

| Interface | Phương thức trừu tượng | Ý nghĩa khi dùng |
| --- | --- | --- |
| `Consumer<T>` | `void accept(T t)` | Nhận 1 đối số, thực hiện hành động, không trả kết quả |
| `BiConsumer<T,U>` | `void accept(T t, U u)` | Nhận 2 đối số, thực hiện hành động |
| `Function<T,R>` | `R apply(T t)` | Chuyển đổi T thành R và giữ kết quả |
| `UnaryOperator<T>` | `T apply(T t)` | Chuyển đổi T thành cùng kiểu T |
| `Predicate<T>` | `boolean test(T t)` | Kiểm tra điều kiện |
| `Supplier<T>` | `T get()` | Tạo hoặc cung cấp giá trị, không nhận đối số |
| `Runnable` | `void run()` | Hành động không nhận đối số và không trả kết quả |

`Runnable` cũng có `void`, nhưng không nhận dữ liệu đầu vào. Khi API cần truyền một đối tượng cho callback, `Consumer<T>` phù hợp hơn. Khi chỉ cần thông báo “hãy chạy hành động này” mà không có đối số, `Runnable` là lựa chọn phổ biến.

## 2. Ba cách tạo Consumer

### 2.1. Lambda dạng biểu thức

~~~java
Consumer<String> print = value -> System.out.println(value);
Consumer<String> normalizeAndLog =
        value -> System.out.println(value.trim());
~~~

Cách thứ hai gọi `trim()` rồi in giá trị đã trim. **Chỉ gọi `value -> value.trim()` làm một Consumer không tương đương**: `trim()` tạo chuỗi mới nhưng kết quả của nó bị bỏ, vì `accept` trả `void`.

### 2.2. Lambda dạng khối

~~~java
Consumer<String> printNonBlank = value -> {
    if (value == null || value.isBlank()) {
        return;
    }
    System.out.println(value.trim());
};
~~~

Đoạn minh họa này dùng `String.isBlank()` (Java 11+), phù hợp dự án JDK 17+. `return;` thoát khỏi **lần gọi lambda hiện tại**. Nó không thoát phương thức bao ngoài và không trả dữ liệu. Khi `accept` nhận giá trị null hoặc rỗng theo quy tắc kiểm tra, callback kết thúc mà không in.

Với block body gán cho `Consumer`, có thể để block kết thúc tự nhiên hoặc viết `return;`. **Không thể viết `return expression;`** vì target type trả `void`:

~~~java
// SAI – ví dụ cố ý không biên dịch:
Consumer<String> wrong = text -> {
    return text.trim();
};
~~~

Nếu cần lấy chuỗi đã chuẩn hóa, dùng `Function<String,String>` và `return text.trim();` trong block, hoặc `text -> text.trim()` ở dạng expression.

### 2.3. Method reference

~~~java
Consumer<String> print = System.out::println;
Consumer<String> addToList = names::add;
~~~

`names::add` giả định `names` đã được khai báo là một `List<String>`. Đây là **đoạn minh họa**, chưa phải chương trình độc lập.

Điểm đáng chú ý: `List.add(E)` **trả `boolean`**, nhưng method reference vẫn dùng được với `Consumer<String>` vì lời gọi tại target `void` được phép bỏ kết quả trả về. Nếu cần biết thao tác có làm danh sách thay đổi hay không, đừng bỏ `boolean`: chọn functional interface có giá trị trả về, chẳng hạn `Function<String,Boolean> added = names::add;`, đồng thời xem xét ý nghĩa thay đổi trạng thái.

## 3. Tại sao một phương thức trả giá trị vẫn có thể nằm trong Consumer?

Đối với **lambda expression body**, Java cho phép target trả `void` khi thân bên phải `->` là một **statement expression**, trong đó có lời gọi phương thức, phép gán, tăng/giảm và tạo đối tượng. Nếu một statement expression có trả giá trị, giá trị đó có thể bị bỏ.

~~~java
Consumer<List<String>> clear = values -> values.clear();   // clear trả void
Consumer<List<String>> addOne = values -> values.add("X"); // add trả boolean, bị bỏ
Consumer<Integer> computeAndDiscard = n -> Math.abs(n);    // abs trả int, bị bỏ
~~~

Tất cả những lambda này có thể hợp lệ. Tuy nhiên, `computeAndDiscard` **không đem lại giá trị tính toán cho caller**; nếu không có side effect có ý nghĩa thì việc tính rồi bỏ kết quả rất dễ là lỗi logic.

Không phải biểu thức bất kỳ đều đứng được trong lambda `void`:

~~~java
// SAI – phép cộng không phải statement expression:
Consumer<Integer> wrong = n -> n + 1;

// ĐÚNG nếu cần chuyển đổi:
Function<Integer, Integer> plusOne = n -> n + 1;

// ĐÚNG nếu cần hành động:
Consumer<Integer> printPlusOne = n -> System.out.println(n + 1);
~~~

`Function` trong đoạn trên cần `import java.util.function.Function;`.

Khi dùng **block body**, những câu lệnh như `values.add("X");` vẫn có thể bỏ kết quả, nhưng `return values.add("X");` không hợp lệ với `Consumer`. Quy tắc gõ kiểu này là một phần của **Java Language Specification `15.27.2 và `15.27.3** và vẫn được áp dụng.

## 4. `andThen`: ghép các hành động theo thứ tự

`Consumer<T>` cung cấp default method:

~~~java
Consumer<T> andThen(Consumer<? super T> after)
~~~

Nó tạo Consumer mới thực hiện lần lượt:

1. `this.accept(value)`.
2. `after.accept(value)`.

**Cả hai hành động nhận cùng đối số đầu vào**, không phải đầu ra của hành động trước. Vì `Consumer` không trả kết quả, `andThen` ở đây là **nối tiếp side effects**, khác với `Function.andThen` dùng kết quả hàm trước làm đầu vào hàm sau.

~~~java
Consumer<String> validate = value -> {
    if (value == null || value.isBlank()) {
        throw new IllegalArgumentException("missing value");
    }
};

Consumer<String> print = System.out::println;
Consumer<String> validateThenPrint = validate.andThen(print);
validateThenPrint.accept("OK");
~~~

Đây là đoạn minh họa trong phương thức, sử dụng `String.isBlank()` của Java 11+. Nếu validation báo lỗi, lệnh in không chạy.

### Ngoại lệ và `andThen`

Theo API `Consumer`:

- Nếu thao tác **đầu tiên** ném exception, exception được truyền ra người gọi; thao tác **thứ hai không thực hiện**.
- Nếu thao tác thứ hai ném exception, thao tác đầu tiên đã thực hiện; exception cũng được truyền ra người gọi.
- Truyền `null` làm Consumer `after` vào `andThen(null)` sẽ ném `NullPointerException` khi ghép.
- `andThen` **không tự rollback** những thay đổi trạng thái đã xảy ra trước exception. Nó không tự tạo transaction hay cơ chế bù trừ.

Ví dụ thứ tự:

~~~java
Consumer<String> first = s -> System.out.println("first: " + s);
Consumer<String> second = s -> System.out.println("second: " + s);
first.andThen(second).accept("A");
~~~

Stdout của đoạn minh họa trên:

~~~text
first: A
second: A
~~~

Trường hợp thứ nhất ném lỗi được kiểm thử trong chương trình đầy đủ ở phần sau. Trong hệ thống thật, nếu gọi hai dịch vụ hay ghi dữ liệu qua các bước, cần quản lý transaction, retry, idempotency hoặc lỗi từng bước theo nghiệp vụ; `andThen` chỉ nối lời gọi.

## 5. `Consumer` trong Collection và Stream

### 5.1. `Iterable.forEach`

`List` triển khai `Iterable`; từ Java 8, `Iterable.forEach(Consumer<? super T>)` gọi hành động cho mỗi phần tử. Với một `List` tuần tự thông thường:

~~~java
List<String> names = Arrays.asList("Lan", "An");
Consumer<String> log = System.out::println;
names.forEach(log);
~~~

Đây là đoạn mã trong phương thức, cần `import java.util.*;` và `import java.util.function.*;`. Hành động nhận từng `String`, không tạo ra một danh sách mới.

### 5.2. `Stream.forEach` là terminal operation

~~~java
List<String> names = Arrays.asList("  Lan ", "  An ");
names.stream()
     .map(String::trim)
     .filter(s -> !s.isEmpty())
     .forEach(System.out::println);
~~~

`map` và `filter` chuẩn bị phép chuyển đổi/điều kiện; `forEach` là thao tác **kết thúc** kích hoạt pipeline và gọi `Consumer`. Với stream **tuần tự** từ `List` như ví dụ, kết quả thường là:

~~~text
Lan
An
~~~

`Stream.forEach` có kiểu trả về `void`. Sau đó không còn một Stream để gọi `map` tiếp. Nếu muốn **thu được kết quả biến đổi**, dùng terminal operation `toList()` (Java 16+) hoặc collector phù hợp thay vì `forEach`.

~~~java
List<String> normalized = names.stream()
    .map(String::trim)
    .filter(s -> !s.isEmpty())
    .toList(); // Java 16+: danh sách không sửa được
~~~

Đừng dùng:

~~~java
// Anti-pattern – minh họa, không khuyến nghị:
List<String> result = new ArrayList<>();
names.stream().map(String::trim).forEach(result::add);
~~~

Đoạn sau có thể hoạt động trong pipeline tuần tự, nhưng đẩy side effect ra collection ngoài làm code kém rõ, dễ tạo race condition nếu chuyển sang stream song song. Hãy dùng `map(...).toList()` hoặc `collect(Collectors.toCollection(ArrayList::new))` nếu cần `ArrayList` sửa được.

### 5.3. Thứ tự và luồng song song

- `Iterable.forEach` tuân theo thứ tự lặp do kiểu Iterable quy định, nếu kiểu đó có thứ tự xác định. Một `List` duyệt bình thường có thứ tự.
- `Stream.forEach` **không bảo đảm thứ tự encounter order** trên parallel stream. Các callback có thể được gọi ở nhiều thread và thứ tự quan sát khác thứ tự nguồn.
- `Stream.forEachOrdered` bảo đảm áp dụng action theo **encounter order nếu stream có encounter order**. Nó có thể làm giảm lợi ích song song và **không tự bảo đảm an toàn luồng của những trạng thái ngoài pipeline**.
- Nguồn như một `HashSet` không có encounter order đáng tin, nên `forEachOrdered` không “phát minh” ra thứ tự nghiệp vụ cho nó.

~~~java
List<Integer> values = Arrays.asList(3, 1, 2);
values.parallelStream()
      .forEachOrdered(System.out::println);
~~~

Output theo thứ tự encounter của `List`:

~~~text
3
1
2
~~~

Đoạn trên minh họa hành động theo thứ tự, không chứng minh rằng toàn bộ các bước trước nó cũng chạy tuần tự trên cùng một thread. Khi side effect cần thứ tự nghiêm ngặt hoặc cập nhật biến chia sẻ, nên cân nhắc mô hình xử lý riêng thay vì chỉ dựa vào `forEachOrdered`.

### 5.4. Cẩn thận với `peek`

`Stream.peek(Consumer<? super T>)` cũng nhận `Consumer` nhưng là **intermediate operation**, thường được dùng để quan sát khi debug. Vì stream có thể tối ưu hóa hoặc short-circuit, không nên đặt side effect nghiệp vụ bắt buộc trong `peek` rồi kỳ vọng nó luôn được gọi chính xác một lần cho mọi phần tử.

~~~java
long count = names.stream()
    .peek(System.out::println) // Không nên xem đây là thao tác nghiệp vụ bắt buộc
    .count();
~~~

Một số pipeline có thể tính `count` mà không cần duyệt các phần tử, nên đừng dựa vào việc in. Với logging hoặc ghi dữ liệu cần bảo đảm, thiết kế một bước chủ động rõ ràng ngoài phép biến đổi hoặc dùng terminal operation phù hợp.

## 6. `BiConsumer<T,U>` và các Consumer chuyên biệt

Khi thao tác cần **hai đối số**, dùng `BiConsumer<T,U>`:

~~~java
BiConsumer<String, Integer> printScore =
    (name, score) -> System.out.println(name + "=" + score);
printScore.accept("Lan", 90);
~~~

`BiConsumer` có `void accept(T,U)` và `andThen(BiConsumer<? super T, ? super U>)`. Nó thường xuất hiện trong `Map.forEach`:

~~~java
Map<String, Integer> scores = new LinkedHashMap<>();
scores.put("Lan", 90);
scores.put("An", 85);
scores.forEach((name, score) -> System.out.println(name + "=" + score));
~~~

Một `BiConsumer<Map<String,Integer>,Order>` có thể nhận cả map đích và đơn hàng để cập nhật. Nếu mục tiêu là **tính map kết quả từ một Stream**, hãy cân nhắc `Collectors.toMap`/`groupingBy` hoặc collector tương ứng thay vì mutate map ngoài trong parallel stream.

Các biến thể phục vụ primitive hoặc phối hợp primitive còn hữu ích:

| Interface | Chữ ký nhận dữ liệu | Ví dụ vai trò |
| --- | --- | --- |
| `IntConsumer` | `void accept(int value)` | Nhận `int`, tránh boxing |
| `LongConsumer` | `void accept(long value)` | Xử lý giá trị `long` |
| `DoubleConsumer` | `void accept(double value)` | Thao tác trên `double` |
| `ObjIntConsumer<T>` | `void accept(T object, int value)` | Nhận đối tượng và số `int` |
| `ObjLongConsumer<T>` | `void accept(T object, long value)` | Nhận đối tượng và số `long` |
| `ObjDoubleConsumer<T>` | `void accept(T object, double value)` | Nhận đối tượng và số `double` |

Ví dụ:

~~~java
IntConsumer printDouble = n -> System.out.println(n * 2);
printDouble.accept(7);
~~~

Một `Consumer<Integer>` thường có boxing/unboxing khi phối hợp với primitive. Không phải mọi đoạn code cần tối ưu vi mô: chọn `IntConsumer`/`IntStream` khi đường dữ liệu primitive thực sự phù hợp, dễ đọc và có ý nghĩa hiệu năng.

Lưu ý các interface `ObjIntConsumer`, `ObjLongConsumer`, `ObjDoubleConsumer` không nhất thiết có cùng tập default methods như `Consumer`; hãy tra Javadoc thay vì giả định chúng đều có `andThen`.

## 7. Ví dụ hoàn chỉnh, biên dịch và chạy được

Tình huống: ghi dấu audit và số tiền cho mỗi đơn, gom tổng số tiền theo mã đơn bằng một `BiConsumer`, in thông báo bằng method reference, xử lý primitive bằng `IntConsumer`, và chứng minh `andThen` dừng khi hành động đầu tiên ném lỗi.

Lưu mã sau thành **ConsumerDemo.java**. Chương trình chạy trên JDK 17+ và chủ yếu dùng API đã có từ Java 8:

~~~java
import java.util.*;
import java.util.function.*;

public class ConsumerDemo {
    static final class Order {
        final String id;
        final int amount;

        Order(String id, int amount) {
            this.id = id;
            this.amount = amount;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("A1", 120),
                new Order("B2", 250)
        );

        List<String> events = new ArrayList<>();
        Consumer<Order> audit = order -> events.add("audit:" + order.id);
        Consumer<Order> metric = order -> events.add("amount:" + order.amount);
        Consumer<Order> record = audit.andThen(metric);
        orders.forEach(record);
        System.out.println(events);

        BiConsumer<Map<String, Integer>, Order> accumulate =
                (map, order) -> map.merge(order.id, order.amount, Integer::sum);
        Map<String, Integer> totals = new LinkedHashMap<>();
        orders.forEach(order -> accumulate.accept(totals, order));
        System.out.println(totals);

        Consumer<String> display = System.out::println;
        display.accept("complete");

        IntConsumer printDouble =
                n -> System.out.println("double=" + (n * 2));
        printDouble.accept(7);

        List<String> trace = new ArrayList<>();
        Consumer<String> first = s -> {
            trace.add("first");
            throw new IllegalStateException("broken");
        };
        Consumer<String> second = s -> trace.add("second");
        try {
            first.andThen(second).accept("x");
        } catch (IllegalStateException expected) {
            System.out.println("trace=" + trace);
        }
    }
}
~~~

Chạy từ thư mục chứa tệp:

~~~bash
javac --release 17 -encoding UTF-8 ConsumerDemo.java
java ConsumerDemo
~~~

Stdout chính xác (đã biên dịch và chạy thực tế):

~~~text
[audit:A1, amount:120, audit:B2, amount:250]
{A1=120, B2=250}
complete
double=14
trace=[first]
~~~

### Phân tích đầu ra

1. `Consumer<Order> audit` và `metric` đều gọi `events.add(...)`. `List.add` trả `boolean`, nhưng `Consumer.accept` trả `void` nên giá trị boolean bị bỏ. Hiệu ứng thêm phần tử vẫn được thực hiện.
2. `audit.andThen(metric)` gọi **audit trước metric cho cùng một đơn**; `orders.forEach(record)` duyệt `List` tuần tự nên thứ tự danh sách sự kiện là audit/amount cho A1, rồi audit/amount cho B2.
3. `BiConsumer<Map<String,Integer>,Order>` nhận hai tham số và thực thi `Map.merge`. `merge` trả một giá trị nhưng nó bị bỏ ở callback `void`; map vẫn có các phần tử `A1=120` và `B2=250`. `LinkedHashMap` giữ thứ tự duyệt chèn trong trường hợp này.
4. `System.out::println` là method reference đáp ứng `Consumer<String>`. `IntConsumer` dùng `int` để in `14`.
5. `first` ghi `"first"` rồi ném `IllegalStateException`. `andThen` không chạy `second`; `catch` chỉ in `trace=[first]`. Việc `first` đã thêm phần tử không bị rollback.
6. Các hiệu ứng thay đổi `ArrayList` và `LinkedHashMap` trong ví dụ chỉ diễn ra **tuần tự, trong một thread**. Đừng sao chép cách này sang `parallelStream()` hoặc callback chạy đồng thời mà thiếu chiến lược an toàn luồng.

Chương trình cũng minh họa sự khác nhau giữa **hợp lệ về cú pháp** và **đúng mục đích**: `events.add` được gọi vì cần side effect; `Math.abs(n)` mà tính rồi bỏ trong Consumer sẽ ít có ý nghĩa nếu không có hành động khác.

## 8. Null, checked exception và hợp đồng đầu vào

### Đầu vào null

Generic `Consumer<T>` **không tự cấm null**. Một Consumer có thể chấp nhận null theo hợp đồng, hoặc từ chối nó:

~~~java
Consumer<String> rejectNull = value -> {
    Objects.requireNonNull(value, "value");
    System.out.println(value);
};
~~~

Đây là đoạn minh họa trong phương thức, cần `import java.util.Objects;` và `import java.util.function.Consumer;`. Hãy định nghĩa chính sách null tại API: “null nghĩa là không có dữ liệu” hay “null là lỗi người gọi”. Đừng mặc định mọi Consumer đều null-safe.

### Checked exception

`Consumer.accept` **không khai báo `throws` checked exception**. Vì vậy lambda được gán cho `Consumer` không thể ném `IOException` hay `SQLException` chưa bắt hoặc chưa được xử lý, dù logic trong thân thật sự gọi I/O.

~~~java
Consumer<java.nio.file.Path> readAndLog = path -> {
    try {
        System.out.println(java.nio.file.Files.readString(path));
    } catch (java.io.IOException ex) {
        throw new java.io.UncheckedIOException(ex);
    }
};
~~~

Đây là đoạn minh họa trong phương thức trên **JDK 11+** vì `Files.readString` có từ Java 11; `UncheckedIOException` đã có từ Java 8. Việc chuyển lỗi sang unchecked exception là **một quyết định API** cần xem xét; không tự nuốt lỗi chỉ để lambda vừa chữ ký. Nếu API thực sự phải truyền checked exception cho caller, có thể thiết kế functional interface riêng với `throws` hoặc xử lý lỗi ở ranh giới thích hợp.

### Một Consumer nhận object có thể sửa được

Ngay cả khi biến địa phương được capture là `final` hoặc *effectively final*, đối tượng mà nó tham chiếu vẫn có thể thay đổi:

~~~java
List<String> log = new ArrayList<>();
Consumer<String> append = value -> log.add(value);
append.accept("A");
~~~

`log` không bị gán lại, nhưng danh sách được thêm phần tử. Đây là side effect bình thường trong ví dụ tuần tự, và cũng là lý do phải cân nhắc đồng thời/concurrency.

## 9. Consumer trong callback và API bất đồng bộ

Bên cạnh Collection/Stream, nhiều API hiện đại nhận `Consumer` làm callback:

- `Optional.ifPresent(Consumer<? super T>)`: gọi action chỉ khi có giá trị; không trả về kết quả từ action.
- `Optional.ifPresentOrElse(Consumer<? super T>, Runnable)` (Java 9+): nhánh có giá trị dùng Consumer, nhánh rỗng dùng Runnable.
- `Map.forEach(BiConsumer<? super K,? super V>)`: thực thi action trên cặp khóa/giá trị.
- `CompletableFuture<T>.thenAccept(Consumer<? super T>)`: thực thi action khi stage trước **hoàn thành bình thường**, nhận kết quả và trả `CompletableFuture<Void>` biểu diễn hoàn tất của bước callback.
- `CompletableFuture<T>.thenApply(Function<? super T,? extends U>)`: trái lại, **biến kết quả** thành giá trị kiểu mới.
- `CompletableFuture<T>.thenRun(Runnable)`: gọi action không cần nhận kết quả stage trước.

Ví dụ minh họa `Optional`:

~~~java
Optional<String> maybeName = Optional.of("Lan");
maybeName.ifPresent(name -> System.out.println("found=" + name));
~~~

Cần import `java.util.Optional`. Với `Optional.empty()`, callback không được gọi.

Ví dụ minh họa `CompletableFuture`:

~~~java
CompletableFuture<String> stage =
        CompletableFuture.completedFuture("READY");

CompletableFuture<Void> logged =
        stage.thenAccept(System.out::println);

logged.join();
~~~

Cần import `java.util.concurrent.CompletableFuture`. `thenAccept` **không trả bản thân String** mà trả stage với kiểu `Void` để theo dõi hoàn thành hoặc lỗi. Nếu stage nguồn thất bại, callback Consumer không được chạy theo nhánh hoàn thành bình thường; lỗi được phản ánh qua stage kế tiếp. Với callback bất đồng bộ, đừng suy đoán thread thực thi: lựa chọn `thenAccept`, `thenAcceptAsync` và `Executor` ảnh hưởng nơi chạy và điều kiện đồng thời. Những tác vụ ghi log/gửi thông báo trong callback cần chính sách exception và idempotency riêng khi có retry.

Không nên dùng Consumer để giấu một phép biến đổi thực sự cần kết quả. Trong trường hợp đó, `thenApply`/`map` hoặc một API trả dữ liệu tương ứng diễn tả mục đích rõ hơn.

## 10. Side effect, thứ tự và thiết kế an toàn

`Consumer` có mục đích gắn với side effect nhưng **side effect không đồng nghĩa với an toàn**. Ba tình huống cần phân biệt:

1. **Dữ liệu cục bộ, tuần tự:** Ghi vào danh sách riêng trong một phương thức, như `ConsumerDemo`, là đơn giản và có thể dự đoán.
2. **Nhiều thread cùng ghi:** `ArrayList` hoặc `HashMap` không được tự động bảo vệ chỉ vì được gọi qua Consumer; cần thiết kế đồng bộ/đối tượng concurrent hoặc giảm phụ thuộc trạng thái chia sẻ.
3. **Hệ thống bên ngoài:** Gọi API thanh toán, gửi thông báo hoặc ghi database có lỗi mạng, khả năng gọi lặp và giao dịch riêng. `Consumer` chỉ mô tả chữ ký, không đảm bảo “exactly once”, rollback, transaction hay retry.

Nếu cần tính toán hoặc gom dữ liệu từ Stream, chọn operation trả giá trị/collector để tránh việc nhiều lambda cùng mutate state ngoài:

~~~java
List<String> ids = orders.stream()
    .map(order -> order.id)
    .toList();
~~~

Ở đây `orders` là danh sách đối tượng `Order` từ ví dụ; đoạn code nằm trong một phương thức. `Stream.toList()` có từ Java 16, trả danh sách không sửa được. Việc sử dụng `Function` qua `map` phù hợp vì mục tiêu là **danh sách id mới**; không cần `Consumer`.

Nếu chỉ cần thông báo cho từng phần tử và chấp nhận điều kiện thực thi, `forEach(Consumer)` hợp lý. Nếu cần đảm bảo hành động trên mỗi bản ghi được ghi đúng một lần qua môi trường có retry, phải thiết kế cơ chế nghiệp vụ tương ứng ngoài Consumer.

### Một checklist thực hành

- **Tôi cần trả giá trị cho caller không?** Nếu có, cân nhắc `Function`, `Predicate` hoặc `Supplier`.
- **Tôi có đúng một đối số không?** `Consumer<T>` nhận một; `BiConsumer<T,U>` nhận hai; `Runnable` nhận không.
- **Hành động có side effect hữu ích và cố ý không?** Nếu chỉ tính ra giá trị rồi bỏ, đó thường là sai abstraction.
- **Các hành động có phụ thuộc thứ tự không?** `andThen` có thứ tự trong một invocation; stream song song cần đánh giá encounter order và concurrency riêng.
- **Nếu hành động lỗi, xử lý thế nào?** `andThen` không chạy bước sau nếu bước trước ném lỗi; không rollback bước trước.
- **Có thể nhận null không?** Viết rõ hợp đồng và kiểm tra ở ranh giới.
- **API có được dùng bởi nhiều thread không?** Tránh giả định “có lambda” đồng nghĩa thread-safe.
- **Có cần kết quả sau xử lý không?** Dùng stream `map` + `toList`/collector khi mục tiêu là biến đổi collection.

## 11. Các lỗi thường gặp

| Viết như vậy | Vấn đề | Cách phù hợp |
| --- | --- | --- |
| `Consumer<String> c = s -> s.trim();` rồi mong chuỗi gốc được trim | `String` bất biến; kết quả `trim()` bị bỏ | `Function<String,String> f = String::trim;` và dùng kết quả |
| `Consumer<Integer> c = n -> n + 1;` | Biểu thức cộng không phải statement expression của target void | Dùng `Function` để trả số, hoặc method call có hiệu ứng |
| `Consumer<T> c = x -> { return transform(x); };` | Block body target void không cho `return expression;` | Chọn `Function`; hoặc gọi action rồi `return;` nếu đúng mục đích |
| `list.stream().forEach(...)` rồi nối tiếp `.map(...)` | `forEach` là terminal operation trả `void` | `map` trước terminal operation hoặc tạo stream mới từ nguồn |
| `list.parallelStream().forEach(log::add)` | `ArrayList` không thread-safe; thứ tự cũng không bảo đảm | Dùng collector nếu gom dữ liệu; kiểm soát concurrency nếu phải side effect |
| `stream.peek(sendNotification)` để bắt buộc gửi sự kiện | `peek` là intermediate; pipeline có thể không gọi callback như mong đợi | Tách bước nghiệp vụ rõ ràng và xử lý lỗi/idempotency |
| `first.andThen(second)` rồi mong second chạy khi first ném lỗi | `andThen` không thực thi after nếu first thất bại | Bắt lỗi/khôi phục rõ ràng nếu nghiệp vụ yêu cầu |
| `first.andThen(null)` | API từ chối callback `after` null | Truyền Consumer hợp lệ hoặc chủ động chọn nhánh |
| `Consumer<T> c = ...` rồi mong `accept` tạo dữ liệu mới | `accept` trả `void` | Chọn `Function`/`BiFunction` cho biến đổi |
| Dùng Consumer để gọi I/O ném checked exception mà không xử lý | `accept` không khai báo checked throws | Xử lý/biến đổi lỗi theo hợp đồng, hoặc khai báo interface phù hợp |
| Gọi `forEachOrdered` trên nguồn không có encounter order rồi mong thứ tự cố định | Không có thứ tự nguồn để bảo toàn | Sắp xếp/định nghĩa thứ tự trước nếu nghiệp vụ cần |
| Sử dụng side effect trong `map`/`filter` | Hành vi khó lý luận, đặc biệt khi tối ưu pipeline hoặc parallel | Dùng phép biến đổi thuần, thực hiện side effect ở ranh giới rõ ràng |

## 12. Bài tập tự kiểm tra

1. Viết `Consumer<String>` in chuỗi viết hoa. Vì sao `Consumer<String> c = String::toUpperCase;` có thể biên dịch nhưng không có tác dụng in/biến đổi đối tượng String gốc?
2. Viết hai Consumer: một kiểm tra input không null, một ghi log. Ghép bằng `andThen` và dự đoán hành vi nếu kiểm tra ném exception.
3. Với `List<String>`, hãy tạo danh sách mới chứa các chuỗi đã trim. Tại sao nên dùng `map(String::trim).toList()` thay vì `forEach(s -> s.trim())`?
4. `List.add` trả boolean. Vì sao method reference `list::add` vẫn được gán cho `Consumer<String>`? Khi nào bỏ boolean là vấn đề?
5. So sánh `Consumer<Integer>` và `IntConsumer`: chữ ký khác nhau thế nào, và khi nào dạng primitive phù hợp?
6. Với `Map<String,Integer>`, viết `map.forEach((key,value) -> ...)` in từng cặp; giải thích vì sao tham số lambda là hai giá trị.
7. Một `parallelStream()` gọi `forEach` ghi vào `ArrayList` chia sẻ. Phân tích hai vấn đề: thread safety và encounter order.
8. Phân biệt `CompletableFuture.thenAccept`, `thenApply` và `thenRun` theo loại callback và kiểu dữ liệu nhận/trả.
9. Nếu `Consumer.andThen` có thao tác đầu ghi dữ liệu, thao tác sau ném lỗi, trạng thái đã ghi tự động được khôi phục không? Cần thêm cơ chế nào khi nghiệp vụ đòi hỏi tính nguyên tử?
10. Vì sao `peek` không nên chứa một thao tác bắt buộc như “trừ tiền tài khoản” trong pipeline?

## Tài liệu API và đặc tả

- [Java SE 17 – Consumer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Consumer.html)
- [Java SE 17 – BiConsumer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/BiConsumer.html)
- [Java SE 17 – java.util.function](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html)
- [Java SE 17 – Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html)
- [Java SE 17 – CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java Language Specification – Lambda Body (`15.27.2)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27.2)

**Ý chính:** `Consumer<T>` mô tả **hành động nhận một đối số và không trả kết quả**, phù hợp cho callback có side effect được kiểm soát. `andThen` sắp xếp hai hành động nối tiếp, `forEach` thực thi một Consumer trên tập dữ liệu, `BiConsumer` hỗ trợ hai đối số, còn `Function` nên được chọn khi kết quả biến đổi cần được giữ lại. Hiểu đúng kiểu trả về `void`, khả năng bỏ kết quả của method invocation và quy tắc lỗi/thứ tự giúp Consumer trở thành một API rõ ràng, an toàn và dễ bảo trì.
