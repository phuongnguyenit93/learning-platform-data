# Trả về Supplier hoặc Function từ phương thức trong Java

Một phương thức Java không chỉ trả về số, chuỗi hoặc đối tượng dữ liệu. Nó còn có thể trả về **hành vi** thông qua một functional interface, chẳng hạn `Supplier<T>` hoặc `Function<T,R>`. Người gọi nhận một đối tượng biểu diễn thao tác rồi **quyết định khi nào gọi thao tác đó**.

Đây là kỹ thuật quan trọng của lập trình hàm và thiết kế API nhận/trả hành vi (*higher-order functions*): thay vì cố định toàn bộ logic ở nơi định nghĩa, một phương thức có thể **tạo ra quy tắc, chiến lược, phép biến đổi hoặc tác vụ** phù hợp với tham số cấu hình.

Hai hợp đồng cốt lõi trong `java.util.function`:

- `Supplier<T>`: phương thức chức năng `T get()` **không nhận đầu vào** và **trả một giá trị** khi được gọi.
- `Function<T,R>`: phương thức chức năng `R apply(T input)` **nhận một đầu vào** kiểu `T` và **trả kết quả** kiểu `R`.

Cả hai đều là **functional interfaces**, nên phương thức tạo ra chúng có thể trả về một lambda, một method reference hoặc một instance đã thực thi interface. Chúng không tự chạy khi được trả về.

Sau bài học, bạn có thể:
1. Khai báo phương thức có kiểu trả về là `Supplier<T>` hay `Function<T,R>`.
2. Trả về lambda/method reference có target type hợp lệ và gọi `get()` hoặc `apply()` ở nơi sử dụng.
3. Thiết kế factory nhận tham số cấu hình và **capture** tham số đó trong hành vi được trả về.
4. Phân biệt **tạo đối tượng hành vi**, **đánh giá cấu hình ở thời điểm tạo** và **thực hiện thân lambda ở thời điểm gọi**.
5. Tạo pipeline từ `Function.compose`/`andThen`, hiểu trạng thái mutable, side effect và lỗi phổ biến.

## 1. Trả về functional interface nghĩa là gì?

Một phương thức thông thường trả về giá trị ngay:

```java
static String greetNow(String name) {
    return "Xin chào, " + name;
}
```

Khi gọi `greetNow("Lan")`, phép nối chuỗi xảy ra trong lần gọi phương thức đó và trả một `String`.

Một phương thức khác có thể trả về **quy tắc để tạo chuỗi khi cần**:

```java
static java.util.function.Supplier<String> greeting(String name) {
    return () -> "Xin chào, " + name;
}
```

Lời gọi `greeting("Lan")` trả về một `Supplier<String>`. Lúc này phần thân `() -> ...` chưa được chạy để tạo lời chào; người nhận gọi `get()` khi muốn kết quả:

```java
java.util.function.Supplier<String> supplier = greeting("Lan");
String message = supplier.get(); // "Xin chào, Lan"
```

Ba đoạn trên là **mảnh mã minh họa ghép theo ngữ cảnh**: hai phương thức `static` thuộc một class, còn phép gán nằm trong phương thức gọi. Không đặt khai báo phương thức `static` bên trong `main`.

**Hãy phân biệt:** một `Supplier<String>` là một đối tượng có thể tạo/trả `String`, chứ không phải bản thân `String`. Tương tự, `Function<String,Integer>` là quy tắc chuyển đổi `String` sang `Integer`, không phải một số nguyên đã tính sẵn.

## 2. Cấu trúc phương thức trả về Supplier<T>

Mẫu cơ bản:

```java
static java.util.function.Supplier<Integer> answerFactory() {
    return () -> 42;
}
```

`answerFactory()` không cần trả `42` trực tiếp. Nó trả một lambda tương thích với `Supplier<Integer>`. Kiểu trả về khai báo của phương thức cung cấp **target type** cho lambda trong câu lệnh `return`.

Lời gọi:

```java
java.util.function.Supplier<Integer> answer = answerFactory();
System.out.println(answer.get()); // 42
```

**Supplier không có tham số tại thời điểm gọi `get()`.** Nhưng phương thức factory hoàn toàn có thể nhận tham số để **cấu hình** Supplier:

```java
static java.util.function.Supplier<String> repeatLater(String word) {
    return () -> word + word;
}
```

Ví dụ `repeatLater("Hi").get()` trả `"HiHi"`. Tham số `word` thuộc lần gọi `repeatLater` và được **capture** trong lambda trả về. Mỗi lần gọi factory với tham số khác nhau có thể tạo hành vi khác nhau.

Các trường hợp hữu ích của `Supplier<T>` gồm: tạo giá trị khi cần, cung cấp fallback, factory không tham số cho một đối tượng, đóng gói việc đọc dữ liệu, và truyền một phép tính chưa thực thi vào API.

### Supplier không đồng nghĩa cache

`Supplier<T>` không mặc định tính một lần hoặc ghi nhớ kết quả. Nếu `get()` gọi một phương thức tốn kém hoặc đọc trạng thái thay đổi, mỗi lần `get()` có thể thực hiện lại công việc hoặc trả kết quả khác. Muốn memoization/caching, phải thiết kế riêng và xem xét đồng bộ khi dùng nhiều thread.

## 3. Cấu trúc phương thức trả về Function<T,R>

Ví dụ tạo phép biến đổi một chuỗi bằng tiền tố:

```java
static java.util.function.Function<String, String> prefixer(String prefix) {
    return value -> prefix + value;
}
```

`prefixer("ID-")` không trả trực tiếp `"ID-123"`, bởi tại thời điểm tạo factory chưa có đầu vào `value`. Nó trả `Function<String,String>`, và caller cung cấp dữ liệu sau:

```java
java.util.function.Function<String, String> withId = prefixer("ID-");
String output = withId.apply("123"); // "ID-123"
```

Kiểu đích `Function<String,String>` được khai báo trên phương thức factory. Vì thế compiler suy luận `value` là `String` và kiểm tra kết quả phép nối chuỗi tương thích với `String`.

Một ví dụ khác dùng tham số kiểu số:

```java
static java.util.function.Function<Integer, Integer> add(int offset) {
    return number -> number + offset;
}
```

`add(5).apply(7)` trả `12`. `offset` là cấu hình được capture; `number` là đầu vào mới được cung cấp mỗi lần gọi `apply`. Đây là sự phân biệt **tham số cấu hình tại thời điểm tạo Function** và **tham số xử lý tại thời điểm chạy Function**.

Trong tính toán nhiều với primitive `int`, có thể dùng `IntUnaryOperator` (`int applyAsInt(int)`) thay cho `Function<Integer,Integer>` để tránh boxing/unboxing. Bài này dùng `Function` để làm rõ API trả về hành vi.

## 4. Ví dụ Java 17 hoàn chỉnh: factory trả Supplier và Function

Tạo tệp **`BehaviorFactoryDemo.java`**:

```java
import java.util.function.Function;
import java.util.function.Supplier;

public class BehaviorFactoryDemo {

    static Supplier<String> greeting(String name) {
        String safeName = name == null ? "bạn" : name.strip();
        return () -> "Xin chào, " + safeName;
    }

    static Function<String, String> withPrefix(String prefix) {
        String safePrefix = prefix == null ? "" : prefix;
        return text -> safePrefix + text;
    }

    static Function<Integer, Integer> add(int offset) {
        return number -> number + offset;
    }

    static <T> Supplier<T> constant(T value) {
        return () -> value;
    }

    public static void main(String[] args) {
        Supplier<String> hello = greeting("Lan");
        Function<String, String> withId = withPrefix("ID-");
        Function<Integer, Integer> plus5 = add(5);
        Supplier<Integer> fortyTwo = constant(42);

        System.out.println(hello.get());
        System.out.println(withId.apply("007"));
        System.out.println(plus5.apply(3));
        System.out.println(fortyTwo.get());

        Function<String, String> trimmed = String::strip;
        Function<String, String> normalizedId =
                trimmed.andThen(withPrefix("USER:"));
        System.out.println(normalizedId.apply("  Mai  "));

        Supplier<String> anonymous = greeting(null);
        System.out.println(anonymous.get());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 BehaviorFactoryDemo.java
java BehaviorFactoryDemo
```

**Stdout chính xác:**

```text
Xin chào, Lan
ID-007
8
42
USER:Mai
Xin chào, bạn
```

Giải thích:

1. `greeting("Lan")` trả một `Supplier<String>`; thân lambda thực hiện khi `hello.get()` chạy.
2. `withPrefix("ID-")` trả `Function<String,String>`; `apply("007")` sử dụng cả tiền tố được capture lẫn đối số mới.
3. `add(5)` tạo phép cộng cấu hình; `apply(3)` trả `8`.
4. `constant(42)` là factory generic `<T> Supplier<T>`; Java suy luận `T` là `Integer` tại phép gán này.
5. `trimmed.andThen(withPrefix("USER:"))` tạo pipeline: `String::strip` chạy trước, rồi thêm tiền tố; đầu vào `"  Mai  "` được chuyển thành `"USER:Mai"`.
6. `greeting(null)` chọn tên mặc định `"bạn"` **khi tạo Supplier** và lambda sau đó dùng giá trị `safeName`.

Lưu ý `String::strip` có từ Java 11; Java 17 hỗ trợ đầy đủ. Các đoạn mã dùng null ở ví dụ này là chủ đích; mọi API khác cần quy định rõ chính sách null của mình.

## 5. Lúc nào hành vi được tạo, lúc nào nó được thực thi?

Khi gọi một factory kiểu:

```java
static Supplier<String> makeLabel(String raw) {
    String trimmed = raw.strip();
    return () -> trimmed.toUpperCase(java.util.Locale.ROOT);
}
```

có **hai thời điểm**:
1. Lúc gọi `makeLabel("  java  ")`, phương thức chạy ngay; `raw.strip()` tạo `trimmed = "java"`, rồi trả một lambda.
2. Lúc gọi `get()` trên Supplier đã nhận, thân lambda mới chạy `toUpperCase` và tạo `"JAVA"`.

Không phải mọi biểu thức bên trong factory đều được trì hoãn. Chỉ **thân lambda** chưa chạy cho đến khi functional method được gọi; việc tính toán bên ngoài thân lambda vẫn diễn ra trong lúc tạo hành vi.

Tương tự, với `Function`, các tham số cấu hình có thể được chuẩn hóa ngay khi tạo, còn đối số `apply(input)` xuất hiện sau đó.

### Ví dụ chạy được: in log xác nhận thứ tự

Tạo tệp **`DeferredExecutionDemo.java`**:

```java
import java.util.function.Function;
import java.util.function.Supplier;

public class DeferredExecutionDemo {

    static Supplier<String> delayedMessage(String name) {
        System.out.println("Tạo Supplier cho " + name);
        return () -> {
            System.out.println("Chạy Supplier");
            return "Hello " + name;
        };
    }

    static Function<Integer, Integer> multiplyBy(int factor) {
        System.out.println("Tạo Function nhân " + factor);
        return number -> {
            System.out.println("Chạy Function với " + number);
            return number * factor;
        };
    }

    public static void main(String[] args) {
        Supplier<String> message = delayedMessage("Lan");
        Function<Integer, Integer> times3 = multiplyBy(3);

        System.out.println("Đã tạo hành vi");
        System.out.println(message.get());
        System.out.println(times3.apply(4));
        System.out.println(message.get());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 DeferredExecutionDemo.java
java DeferredExecutionDemo
```

**Stdout chính xác:**

```text
Tạo Supplier cho Lan
Tạo Function nhân 3
Đã tạo hành vi
Chạy Supplier
Hello Lan
Chạy Function với 4
12
Chạy Supplier
Hello Lan
```

Ở đây hai dòng “Tạo ...” xuất hiện trước “Đã tạo hành vi” vì phần ngoài thân lambda của factory thực thi **ngay**. “Chạy Supplier” xuất hiện **hai lần** vì `get()` được gọi hai lần. `Function` chỉ chạy một lần do `apply(4)` chỉ được gọi một lần.

**Không đánh đồng việc trả về lambda với chạy bất đồng bộ.** Cả hai ví dụ trên chạy trên thread gọi `get()`/`apply()`; chúng không tự tạo thread, task scheduler hoặc Future. Nếu cần bất đồng bộ, API gọi hành vi phải thực sự cung cấp cơ chế như `ExecutorService` hoặc `CompletableFuture`.

## 6. Biến được capture: final và effectively final

Lambda được trả về thường cần ghi nhớ cấu hình từ tham số hoặc biến cục bộ trong phương thức factory:

```java
static Function<Integer, Integer> addTax(int tax) {
    int normalizedTax = Math.max(tax, 0);
    return amount -> amount + normalizedTax;
}
```

`tax` được đọc để tạo `normalizedTax`, còn `normalizedTax` là local **effectively final** vì không bị gán lại. Java cho phép lambda capture biến local hoặc tham số khi biến đó là `final` hoặc **effectively final**. Chúng vẫn được lambda dùng sau khi lời gọi factory đã kết thúc.

Không được gán lại local đã được capture:

```java
// CỐ Ý KHÔNG BIÊN DỊCH:
static Function<Integer, Integer> broken(int offset) {
    Function<Integer, Integer> operation = x -> x + offset;
    offset++; // offset không còn effectively final
    return operation;
}
```

Cách sửa là tính cấu hình mới vào một biến local được gán một lần:

```java
static Function<Integer, Integer> corrected(int offset) {
    int adjusted = offset + 1;
    return x -> x + adjusted;
}
```

Lưu ý: **`final` khóa phép gán lại biến tham chiếu, không làm object trở nên immutable**. Ví dụ factory có thể capture một `List` hoặc `AtomicInteger` và thấy trạng thái thay đổi theo thời gian. Nếu API cần hành vi thuần và có kết quả ổn định, nên chụp dữ liệu cần thiết trước khi trả về lambda.

## 7. Snapshot và trạng thái mutable khi trả về Supplier

Hai supplier có thể đọc từ cùng một nguồn nhưng với chiến lược khác nhau:
- **Snapshot:** lấy giá trị một lần khi tạo factory, sau đó trả lại giá trị đã lưu.
- **Live view:** giữ tham chiếu tới đối tượng mutable rồi đọc trạng thái của nó mỗi lần `get()`.

Tạo tệp **`SupplierStateDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class SupplierStateDemo {

    static Supplier<String> snapshot(StringBuilder source) {
        String captured = source.toString();
        return () -> captured;
    }

    static Supplier<String> live(StringBuilder source) {
        return source::toString;
    }

    static Supplier<Integer> nextSequence(AtomicInteger counter) {
        return counter::incrementAndGet;
    }

    public static void main(String[] args) {
        StringBuilder source = new StringBuilder("A");
        Supplier<String> frozen = snapshot(source);
        Supplier<String> current = live(source);

        System.out.println("Trước: " + frozen.get() + "/" + current.get());
        source.append("B");
        System.out.println("Sau: " + frozen.get() + "/" + current.get());

        Supplier<Integer> next = nextSequence(new AtomicInteger(10));
        System.out.println("Số tiếp: " + next.get());
        System.out.println("Số tiếp: " + next.get());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 SupplierStateDemo.java
java SupplierStateDemo
```

**Stdout chính xác:**

```text
Trước: A/A
Sau: A/AB
Số tiếp: 11
Số tiếp: 12
```

`frozen` capture một `String` bất biến đã được tạo tại thời điểm gọi `snapshot`. `current` giữ receiver `source` cho method reference `source::toString`, nên thấy nội dung cập nhật. `next` giữ một `AtomicInteger` và gọi `incrementAndGet` mỗi lần `get()`, tạo số tăng dần.

`AtomicInteger` hỗ trợ các thao tác nguyên tử trên giá trị số của nó, nhưng **không làm mọi logic kết hợp nhiều biến trở nên thread-safe**. `StringBuilder` không an toàn khi nhiều thread cùng đọc/ghi mà không có phối hợp phù hợp. Ví dụ trên chạy tuần tự nên stdout xác định rõ.

Đừng nhầm factory trả `Supplier<T>` với factory luôn trả đối tượng mới: `Supplier` có thể trả cùng instance, một snapshot, giá trị mới mỗi lần, hoặc giá trị đọc từ trạng thái hiện tại. **Hợp đồng nghiệp vụ** phải làm rõ hành vi này.

## 8. Kết hợp Function được trả về thành pipeline

`Function<T,R>` có các default methods giúp kết hợp phép biến đổi:
- `andThen(after)`: chạy Function hiện tại **trước**, sau đó chạy Function `after`.
- `compose(before)`: chạy Function `before` **trước**, rồi mới chạy Function hiện tại.
- `Function.identity()`: trả Function giữ nguyên giá trị đầu vào.

Ví dụ:

```java
Function<String, String> strip = String::strip;
Function<String, String> prefix = text -> "ID:" + text;

Function<String, String> a = strip.andThen(prefix);
Function<String, String> b = prefix.compose(strip);
```

Đây là **mảnh mã minh họa**, cần `import java.util.function.Function;` và đặt trong phương thức. Với cùng input, `a` và `b` đều strip trước rồi prefix sau. `Function` mới tạo ra bởi `andThen`/`compose` vẫn là hành vi chưa thực thi; chỉ khi gọi `apply(input)` thì chuỗi phép biến đổi mới chạy.

Một factory tạo pipeline:

```java
static Function<String, String> createNormalizer(String prefix) {
    Function<String, String> strip = String::strip;
    Function<String, String> upper =
            text -> text.toUpperCase(java.util.Locale.ROOT);
    Function<String, String> decorate =
            text -> prefix + text;
    return strip.andThen(upper).andThen(decorate);
}
```

Với `createNormalizer("CODE:").apply(" java ")`, kết quả là `"CODE:JAVA"`. `prefix` được capture khi tạo `decorate`; biểu thức `andThen` xây dựng Function kết hợp nhưng không chạy biến đổi trên `" java "` trước khi được gọi `apply`.

**Thứ tự có ý nghĩa.** Đổi `upper.andThen(decorate)` thành `decorate.andThen(upper)` có thể làm thay đổi cả phần tiền tố. Khi biến đổi có side effect hoặc checked exceptions được bọc lại, thứ tự cũng ảnh hưởng hành vi quan sát được.

## 9. Thiết kế API trả hành vi: static factory, instance method và generics

Không bắt buộc dùng `static`; một instance method có thể trả Supplier hoặc Function và đọc field của đối tượng:

```java
class TextService {
    private final String prefix;

    TextService(String prefix) {
        this.prefix = prefix;
    }

    java.util.function.Function<String, String> formatter() {
        return value -> prefix + value;
    }
}
```

Mảnh mã này là một class hợp lệ; trong phương thức gọi, có thể viết:

```java
TextService service = new TextService("TAG-");
java.util.function.Function<String, String> format = service.formatter();
String output = format.apply("1"); // "TAG-1"
```

Lambda có thể truy cập field thông qua instance bao quanh. Quy tắc `final`/`effectively final` áp dụng cho biến local/parameter được capture, **không yêu cầu mọi field được lambda truy cập phải final**. Tuy nhiên, field mutable khiến kết quả có thể phụ thuộc trạng thái khi gọi `apply`; hãy xác định rõ API mong muốn chụp snapshot hay đọc live state.

Với generics, factory có thể được dùng cho nhiều kiểu:

```java
static <T> Supplier<T> constant(T value) {
    return () -> value;
}
```

Ví dụ `Supplier<String> a = constant("Java");` và `Supplier<Integer> b = constant(10);` đều hợp lệ. Cách đặt kiểu trả về rõ ràng giúp caller biết mình nhận **hành vi** chứ không phải dữ liệu trực tiếp.

Không thể khai báo một phương thức `var make() { ... }` để tự suy luận return type; `var` dành cho một số ngữ cảnh suy luận kiểu cục bộ, không thay thế kiểu trả về phương thức. Ngoài ra, khai báo `var f = () -> 42;` là **cố ý sai** vì lambda đứng riêng cần target type. Trong `return () -> 42;` của một phương thức có kiểu trả về `Supplier<Integer>`, chính kiểu trả về đã cung cấp target type nên biểu thức hợp lệ.

## 10. Chọn Supplier hay Function?

| Bài toán | Lựa chọn | Lý do |
| --- | --- | --- |
| Tạo giá trị khi được yêu cầu, không có đối số mới | `Supplier<T>` | Caller chỉ gọi `get()`. |
| Trả quy tắc biến đổi đầu vào do caller cung cấp sau | `Function<T,R>` | Caller gọi `apply(input)`. |
| Trả điều kiện đúng/sai cho đầu vào | `Predicate<T>` | `test(input)` biểu đạt boolean rõ hơn. |
| Trả hành động không đầu vào, không kết quả | `Runnable` | `run()` đơn giản, ở `java.lang`. |
| Trả hành động nhận đầu vào nhưng không kết quả | `Consumer<T>` | `accept(input)`. |
| Trả phép biến đổi có hai đối số | `BiFunction<T,U,R>` | `apply(left,right)`. |
| Trả factory có thể ném checked exception | `Callable<T>` hoặc interface riêng thích hợp | `Callable.call()` khai báo `throws Exception`; không tự biến Supplier thành kiểu có checked exception. |

Việc chọn interface theo ý nghĩa giúp tránh code như `Function<Void,T>` để giả lập một hành động không đầu vào: `Supplier<T>` thường đúng hơn, vì `Function<Void,T>` vẫn có functional method nhận một đối số `Void` và yêu cầu gọi `apply(null)` nếu dùng theo cách đó.

Cũng không cần tự tạo một functional interface mới khi các kiểu chuẩn đã thể hiện đủ hợp đồng. Ngược lại, nếu API cần ngữ nghĩa nghiệp vụ đặc thù, checked exception riêng, nhiều tham số hoặc default methods mang ý nghĩa miền, có thể định nghĩa interface riêng và trả về nó.

## 11. Ngoại lệ, null và an toàn tài nguyên

### 11.1. Checked exceptions

`Supplier.get()` và `Function.apply()` không khai báo checked exceptions. Nếu thân lambda gọi một API ném `IOException`, compiler yêu cầu bắt và xử lý (hoặc chuyển thành unchecked exception phù hợp), hay dùng một interface có hợp đồng `throws` phù hợp.

**Không nên** dùng lambda có catch rộng rồi âm thầm bỏ lỗi chỉ để ép chữ ký cho vừa `Supplier` hoặc `Function`; hành vi cần báo lỗi rõ ràng theo yêu cầu API.

### 11.2. Null

Java không tự bảo đảm Supplier không trả null hoặc Function không nhận null. Ví dụ:

```java
static java.util.function.Function<String, String> safeUpper() {
    return value -> value == null
            ? ""
            : value.toUpperCase(java.util.Locale.ROOT);
}
```

Đây là mảnh khai báo phương thức hợp lệ; ứng dụng có thể chọn chính sách khác như `Objects.requireNonNull(value)`. Điều quan trọng là tài liệu hóa hợp đồng: null có được phép hay không, kết quả null có ý nghĩa gì, và lỗi phát sinh khi nào.

### 11.3. Tài nguyên đóng sớm

Cẩn thận khi trả về lambda sử dụng một tài nguyên đã đóng:

```java
// MẪU NGUY HIỂM: không dùng cho ứng dụng thực tế.
static Supplier<String> broken(java.io.BufferedReader reader) {
    return () -> reader.toString(); // minh họa capture tham chiếu
}
```

Đoạn này chỉ cho thấy lambda giữ tham chiếu tới `reader`; `toString()` không đọc dữ liệu từ reader và vì vậy **không phải một ví dụ tạo lỗi đọc tài nguyên đóng**. Vấn đề thực sự xảy ra khi callback cố thực hiện thao tác trên tài nguyên đã bị đóng (ví dụ đọc dòng dữ liệu trong `get()`), vì thế cần gắn vòng đời tài nguyên với thời gian sử dụng hành vi, hoặc thiết kế factory mở/đóng tài nguyên trong mỗi lần gọi khi phù hợp.

Không trả Stream hoặc callback phụ thuộc vào nguồn đã đóng rồi giả định “tạo lambda trước thì tài nguyên còn mở”. Thời điểm chạy mới quyết định tài nguyên cần tồn tại.

## 12. Những lỗi phổ biến

1. **Trả dữ liệu thay vì hành vi:** phương thức khai báo `Supplier<String>` cần trả một Supplier (ví dụ `() -> "x"`), không trả thẳng `"x"`.
2. **Gọi sai functional method:** `Supplier.get()` không nhận tham số; `Function.apply(input)` cần một đối số.
3. **Nhầm thời điểm thực thi:** tính toán trước `return` chạy lúc tạo factory; thân lambda chỉ chạy khi được gọi.
4. **Tưởng Supplier tự cache:** `get()` có thể chạy lại và trả giá trị khác.
5. **Gán lại local được capture:** biến local/parameter được bắt giữ phải final/effectively final.
6. **Tưởng final làm object immutable:** lambda có thể nhìn thấy trạng thái đối tượng mutable thay đổi.
7. **Tưởng lambda tự chạy bất đồng bộ:** cần executor/scheduler nếu muốn async thực sự.
8. **Sai kiểu đích:** `Function<String,Integer>` khác `Supplier<Integer>` dù cả hai có thể tạo một số.
9. **Cho rằng var tự suy ra kiểu lambda:** `var f = x -> x + 1;` thiếu target type; return type phương thức hay biến khai báo tường minh có thể cung cấp nó.
10. **Bỏ qua checked exception:** `Supplier`/`Function` chuẩn không khai báo checked exception ở functional method.
11. **Sai thứ tự compose/andThen:** `f.andThen(g)` thực hiện `f` trước; `f.compose(g)` thực hiện `g` trước.
12. **Để hành vi giữ tài nguyên đã đóng:** factory và callback có vòng đời khác nhau.
13. **Dùng shared mutable state trong parallel Stream mà không kiểm soát:** trả về lambda được không có nghĩa là thread-safe.
14. **Mã API khó đọc vì trả `Function` quá tổng quát:** khi hành vi có nghĩa nghiệp vụ riêng, đặt tên phương thức factory rõ ràng và tài liệu hóa null, side effect và thời điểm chạy.

## 13. Bài tập tự kiểm tra

**Câu 1.** Phương thức `static Supplier<Integer> make(int n) { return () -> n * 2; }` trả gì khi gọi `make(4)`?

**Đáp án:** Trả một `Supplier<Integer>`, chưa phải số `8`. Sau đó `make(4).get()` mới trả `8`.

**Câu 2.** Viết một factory tạo Function nhân giá trị với hệ số truyền vào:

```java
static java.util.function.Function<Integer, Integer> multiplyBy(int factor) {
    return value -> value * factor;
}
```

`multiplyBy(3).apply(5)` trả `15`. `factor` được capture, còn `value` được cung cấp tại thời điểm áp dụng.

**Câu 3.** `Supplier<List<String>>` có bảo đảm trả danh sách mới mỗi lần `get()`?

**Không.** Functional interface chỉ quy định `get()` trả một `List<String>`; việc tạo mới, dùng cache hay trả chung instance phụ thuộc implementation.

**Câu 4.** Vì sao `var supplier = () -> 42;` không hợp lệ, còn `static Supplier<Integer> make() { return () -> 42; }` hợp lệ?

Vì trường hợp thứ nhất thiếu **target type** cho lambda, còn kiểu trả về `Supplier<Integer>` của `make` cung cấp target type trong câu lệnh `return`.

**Câu 5.** `Function<String,String> a = String::strip;` và `Function<String,String> b = s -> "ID:" + s;`. `a.andThen(b).apply("  Java  ")` trả gì?

**Đáp án:** `"ID:Java"`, vì strip chạy trước rồi mới thêm tiền tố.

**Câu 6.** Nếu một Supplier giữ tham chiếu tới `StringBuilder`, caller sửa nội dung sau khi tạo Supplier, kết quả `get()` có thay đổi không?

**Có thể thay đổi**, nếu Supplier đọc trạng thái `StringBuilder` khi `get()` chạy. Nếu factory đã tạo một `String` snapshot rồi capture chuỗi đó thì kết quả không đổi theo sửa đổi trên builder.

**Câu 7.** Cách viết nào nên dùng khi chỉ cần tính giá trị ngay, không cần trì hoãn hoặc tái sử dụng hành vi?

Dùng phương thức trả dữ liệu trực tiếp thường rõ ràng hơn. Trả về `Supplier`/`Function` có giá trị khi API thực sự cần truyền, kết hợp, cấu hình hoặc trì hoãn hành vi.

**Ghi nhớ:** Phương thức trả `Supplier<T>` hoặc `Function<T,R>` là một **factory tạo hành vi**. `Supplier` được gọi bằng `get()` không đối số; `Function` dùng `apply(input)`. Hãy xác định rõ **kiểu đích, giá trị được capture, thời điểm thực thi và hợp đồng trạng thái** để người sử dụng API hiểu đúng kết quả.
