# Cung cấp kiểu đích tường minh cho biểu thức hàm trong Java

## 1. Vấn đề: biểu thức hàm cần biết mình sẽ trở thành kiểu nào

Trong Java hiện đại, **biểu thức lambda** (ví dụ `text -> text.isBlank()`) và **tham chiếu phương thức** (*method reference*, ví dụ `String::length`) cho phép truyền hành vi giống như truyền một giá trị. Nhưng bản thân cú pháp lambda/method reference **không tự xác định một kiểu độc lập**: trình biên dịch cần biết **kiểu đích** (*target type*) từ ngữ cảnh.

Kiểu đích phù hợp thông thường là một **functional interface**, tức interface có một phương thức trừu tượng duy nhất theo quy tắc của Java. Ví dụ `Predicate<String>` có phương thức hàm `boolean test(String value)`, còn `Function<String, Integer>` có phương thức hàm `Integer apply(String value)`.

Bài này nằm trong phần **`var` và biểu thức** của Java 10, vì có một giới hạn rất quan trọng: `var` suy luận kiểu của biến cục bộ từ **biểu thức khởi tạo có thể xác định kiểu**, nhưng một lambda hoặc method reference đứng riêng cần kiểu đích trước khi trình biên dịch hoàn thành việc kiểm tra. Do đó:

~~~java
// KHÔNG HỢP LỆ: các đoạn này chỉ minh họa lỗi biên dịch.
var isLong = text -> text.length() >= 4;
var length = String::length;
~~~

Kể cả khi ghi rõ kiểu tham số trong lambda, `var` vẫn không thể tự tạo ra một functional interface để gán:

~~~java
// KHÔNG HỢP LỆ: biết kiểu của text chưa đồng nghĩa biết kiểu interface đích.
var isLong = (String text) -> text.length() >= 4;
~~~

Cách được khuyến nghị là **công bố functional interface ở đúng vị trí cung cấp kiểu đích**:

~~~java
// HỢP LỆ: đoạn khai báo biến cục bộ, đặt trong thân phương thức.
java.util.function.Predicate<String> isLong =
        text -> text.length() >= 4;

java.util.function.Function<String, Integer> length =
        String::length;
~~~

Giờ `text` có kiểu `String` theo `Predicate<String>`; `String::length` khớp với hàm nhận `String` và trả `Integer` (kết quả `int` được boxing thành `Integer`). Khi đã có đối tượng functional interface, bạn có thể gọi `isLong.test("Java")` hoặc `length.apply("Java")`.

**Cần phân biệt:** `var` dành cho suy luận **kiểu biến cục bộ** (Java 10+), còn lambda và method reference đã có từ Java 8 và vẫn được hỗ trợ. Từ Java 11, `var` cũng được phép xuất hiện trong **danh sách tham số lambda**, nhưng tính năng đó không làm mất yêu cầu về kiểu đích.

## 2. Kiểu đích là gì và được hình thành như thế nào?

Một lambda là **poly expression**: kiểu của nó phụ thuộc vào ngữ cảnh. Ví dụ cùng hình thức `value -> value.isEmpty()` có thể hiện diện trong nhiều API nhận các functional interface khác nhau; ngữ cảnh xác định kiểu của `value` và hợp đồng mà lambda cần đáp ứng.

~~~java
// Hai khai báo biến cục bộ minh họa, đặt trong thân phương thức.
java.util.function.Predicate<String> check =
        value -> value.isEmpty();

java.util.function.Function<String, Boolean> checkAsFunction =
        value -> value.isEmpty();
~~~

Hai biểu thức có thân giống nhau nhưng **kiểu đích khác nhau**. `check.test("x")` trả `false`, còn `checkAsFunction.apply("x")` trả `Boolean.FALSE`. Chúng không tự chuyển thành cùng một kiểu: ngữ cảnh khai báo đã quyết định interface mà compiler xây dựng.

Trình biên dịch xác minh sự phù hợp dựa trên:

1. **Số lượng và kiểu tham số** trong phương thức trừu tượng của functional interface.
2. **Kiểu của biểu thức hoặc lệnh `return`** trong thân lambda có phù hợp kiểu trả về của phương thức trừu tượng không; với interface trả `void`, áp dụng quy tắc về *void-compatible lambda body*.
3. **Khả năng phân giải method reference**: overload nào, phương thức `static` hay instance, và kiểu đầu vào/đầu ra nào khớp với functional interface.
4. **Ngoại lệ kiểm tra (checked exceptions)** nếu lambda hoặc method reference gọi phương thức có `throws`. Không phải mọi hành vi có cùng kiểu tham số/trả về đều hợp lệ với mọi interface.

Functional interface không bắt buộc phải thuộc `java.util.function`. Bạn có thể tự định nghĩa:

~~~java
@FunctionalInterface
interface NameRule {
    boolean accepts(String name);
}
~~~

Đây là **khai báo interface minh họa**, có thể đặt ở cấp file hoặc trong lớp; nó có đúng một phương thức trừu tượng. `@FunctionalInterface` giúp compiler kiểm tra ý định thiết kế, nhưng bản thân annotation không tạo ra quy tắc suy luận mới.

~~~java
// Đặt trong một phương thức có thể nhìn thấy interface NameRule.
NameRule isJava = name -> name.startsWith("Java");
boolean matched = isJava.accepts("Java 10");
~~~

Ở đây kiểu đích `NameRule` cung cấp tên phương thức hàm và kiểu tham số/trả về. Với `matched`, giá trị là `true`.

**Không thể thay kiểu đích bằng `Object`:** `Object lambda = s -> s.length();` không hợp lệ vì `Object` không phải functional interface. “Mọi interface đều là Object” không có nghĩa compiler biết cần hiện thực phương thức trừu tượng nào.

## 3. Cách 1 — Khai báo functional interface tường minh ở biến nhận

Đây là cách rõ ràng nhất khi bạn muốn giữ một lambda hoặc method reference để sử dụng nhiều lần:

~~~java
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;
import java.util.function.UnaryOperator;

// Các khai báo sau được đặt trong thân một phương thức.
Predicate<String> nonBlank = text -> !text.isBlank();
Function<String, Integer> length = String::length;
Supplier<String> greeting = () -> "Xin chào";
UnaryOperator<String> trim = String::trim;
~~~

**Giải thích kiểu đích:**

| Kiểu đích | Phương thức hàm | Ý nghĩa |
| --- | --- | --- |
| `Predicate<T>` | `boolean test(T value)` | Kiểm tra điều kiện, trả `boolean` |
| `Function<T, R>` | `R apply(T value)` | Biến đổi từ `T` sang `R` |
| `Supplier<T>` | `T get()` | Tạo/cung cấp giá trị, không có tham số |
| `Consumer<T>` | `void accept(T value)` | Tiêu thụ dữ liệu, không yêu cầu trả kết quả |
| `UnaryOperator<T>` | `T apply(T value)` | Trường hợp đặc biệt của `Function<T, T>` |
| `BiFunction<T, U, R>` | `R apply(T first, U second)` | Nhận hai giá trị, trả kết quả |
| `ToIntFunction<T>` | `int applyAsInt(T value)` | Nhận `T`, trả `int` nguyên thủy |
| `Runnable` | `void run()` | Hành vi không tham số, không trả kết quả |

Khi chọn interface, hãy ưu tiên **hợp đồng đúng ý nghĩa**: nếu chỉ cần xác nhận đúng/sai, `Predicate<String>` thường diễn đạt mục đích rõ hơn `Function<String, Boolean>`. Nếu cần nhận chuỗi và trả độ dài nguyên thủy, `ToIntFunction<String>` tránh boxing mà `Function<String, Integer>` có thể phải thực hiện.

Ví dụ các lời gọi sau đều đúng:

~~~java
// Đoạn minh họa tiếp theo các biến đã khai báo.
boolean ok = nonBlank.test("Java");        // true
int count = length.apply("Java");          // 4 (unboxing Integer)
String message = greeting.get();           // "Xin chào"
String cleaned = trim.apply(" Java ");    // "Java"
~~~

**Điều cần hiểu:** kiểu đích mô tả **chữ ký**, không mô tả mọi đặc tính của phép tính. Một `Function<String, Integer>` có thể đếm ký tự hoặc tìm chỉ số; tên biến và tài liệu API vẫn cần giúp người đọc biết hành vi thực tế.

## 4. Cách 2 — Để tham số phương thức hoặc API cung cấp kiểu đích

Không phải lúc nào cũng cần khai báo biến trung gian. Một phương thức nhận functional interface sẽ cung cấp kiểu đích cho lambda ngay trong lời gọi.

~~~java
import java.util.function.Predicate;

// Hai phương thức sau là các phần của cùng một class.
static boolean matches(String input, Predicate<String> condition) {
    return condition.test(input);
}

static void demo() {
    boolean result = matches("Java", text -> text.startsWith("J"));
    System.out.println(result); // true
}
~~~

**Cơ chế:**
- Compiler biết tham số thứ hai của `matches` có kiểu `Predicate<String>`.
- Vì vậy `text` trong lambda có kiểu `String`, và phần thân `text.startsWith("J")` trả `boolean` đúng yêu cầu.
- `matches(...)` trả `boolean` như phương thức đã khai báo; không cần viết `var` cho lambda.

Các API hiện đại như `Stream.filter`, `Stream.map`, `List.removeIf` và `Optional.map` cũng cung cấp kiểu đích cho lambda/method reference qua chữ ký tham số:

~~~java
import java.util.List;

// Đoạn đặt trong phương thức, Java 17+.
var names = List.of("Java", "Kotlin", "JS");
var filtered = names.stream()
        .filter(name -> name.startsWith("J"))
        .toList();
System.out.println(filtered); // [Java, JS]
~~~

Ở đây `var names` và `var filtered` **đều hợp lệ**: biểu thức khởi tạo tương ứng `List.of(...)` và lời gọi `toList()` đã có kiểu kết quả. Lambda của `filter` nhận kiểu đích `Predicate<? super String>` thông qua API `Stream<String>`.

**Phân biệt rõ:** compiler suy luận kiểu trong lời gọi API và compiler suy luận kiểu của biến `var` là hai bước có ngữ cảnh khác nhau. Việc `var filtered = ...` hợp lệ không làm cho `var filter = name -> ...` hợp lệ.

## 5. Cách 3 — Dùng kiểu trả về tường minh của phương thức

Khi API của bạn trả về một hành vi, hãy khai báo kiểu trả về functional interface. Từ đó, biểu thức lambda hoặc method reference trong câu lệnh `return` có kiểu đích rõ ràng:

~~~java
import java.util.function.UnaryOperator;

// Phương thức minh họa, đặt bên trong một class.
public static UnaryOperator<String> createNormalizer() {
    return String::trim;
}
~~~

Lời gọi `createNormalizer()` đã có kiểu trả về `UnaryOperator<String>`. Do đó:

~~~java
// Đoạn đặt trong phương thức.
var normalizer = createNormalizer();         // HỢP LỆ
var output = normalizer.apply("  Java  ");   // "Java"
~~~

`var normalizer` hợp lệ **vì biểu thức khởi tạo là lời gọi phương thức đã khai báo kiểu trả về**, không phải method reference đứng riêng.

Tương tự, với phương thức trả về `Predicate<String>`:

~~~java
// Phương thức minh họa, đặt bên trong một class.
public static java.util.function.Predicate<String> nonEmptyRule() {
    return text -> !text.isEmpty();
}
~~~

Cách này đặc biệt hữu ích nếu nhiều nơi cần dùng cùng một quy tắc và bạn muốn người gọi dựa trên hợp đồng interface thay vì phải biết nội dung lambda bên trong.

## 6. Cách 4 — Ép kiểu sang functional interface tại biểu thức

Khi bắt buộc phải giữ `var` ở vế trái, có thể cung cấp kiểu đích bằng **cast tường minh**:

~~~java
// Các khai báo biến cục bộ hợp lệ trên Java 17+.
var isLong = (java.util.function.Predicate<String>)
        (text -> text.length() >= 4);

var length = (java.util.function.ToIntFunction<String>)
        String::length;
~~~

Kiểu suy luận của `isLong` là `Predicate<String>`; kiểu của `length` là `ToIntFunction<String>`. Cast tạo **ngữ cảnh kiểm tra kiểu** cho lambda/method reference, nên compiler biết cần khớp chữ ký nào trước khi suy luận kiểu của `var`.

**Lưu ý thiết kế:** ở code mới, viết thẳng `Predicate<String> isLong = ...` thường dễ đọc hơn. Cast hữu ích khi có biểu thức phức tạp, cần chọn một overload hoặc giữ cú pháp `var` vì lý do cụ thể; không nên lạm dụng để che giấu kiểu.

Cast **không** biến một lambda bất kỳ thành mọi loại object hoặc sửa được một lambda có chữ ký không tương thích. Ví dụ `(Runnable) () -> 42` không hợp lệ vì `Runnable.run()` trả `void`, còn thân `() -> 42` là biểu thức trả giá trị và không phải *statement expression* phù hợp một lambda trả `void`. Compiler vẫn kiểm tra đầy đủ hợp đồng của functional interface.

## 7. Method reference cũng cần kiểu đích

Method reference có thể gọn hơn lambda khi hành vi chỉ chuyển tiếp tới một phương thức/constructor đã tồn tại. Nhưng chính kiểu đích giúp compiler xác định **ngữ cảnh gọi**.

| Loại tham chiếu | Ví dụ có kiểu đích | Cách hiểu |
| --- | --- | --- |
| Phương thức `static` | `Function<String, Integer> parse = Integer::parseInt;` | `s -> Integer.parseInt(s)`; kết quả `int` được boxing |
| Phương thức instance không gắn sẵn receiver | `Function<String, String> trim = String::trim;` | `s -> s.trim()` |
| Phương thức instance đã gắn receiver | `Supplier<String> text = " Java "::trim;` | `() -> " Java ".trim()` |
| Constructor | `Supplier<StringBuilder> newBuilder = StringBuilder::new;` | `() -> new StringBuilder()` |

Đặc biệt, `String::length` không chứa đối tượng `String` cụ thể nào. Với `ToIntFunction<String>`, đối tượng receiver trở thành **tham số đầu tiên**; còn `"Java"::length` gắn sẵn receiver và khớp với kiểu đích không có tham số như `IntSupplier`.

Ví dụ:

~~~java
// Đoạn minh họa trong phương thức.
java.util.function.ToIntFunction<String> unbound = String::length;
java.util.function.IntSupplier bound = "Java"::length;
System.out.println(unbound.applyAsInt("Hello")); // 5
System.out.println(bound.getAsInt());             // 4
~~~

Ngược lại, `var reference = String::length;` vẫn **không hợp lệ**, bởi chưa có functional interface để xác định method reference được sử dụng theo chữ ký nào. Việc một phương thức tồn tại và có kiểu trả về không đủ để xác định kiểu của **đối tượng hành vi**.

## 8. Java 11+ cho phép `var` ở tham số lambda, nhưng vẫn cần kiểu đích

Một chỗ thường gây hiểu nhầm là cú pháp:

~~~java
// HỢP LỆ từ Java 11, vì có kiểu đích Predicate<String>.
java.util.function.Predicate<String> blank =
        (var text) -> text.isBlank();
~~~

Tại đây `var text` là **khai báo tham số bên trong lambda**. Kiểu của `text` vẫn đến từ functional interface `Predicate<String>`. Cú pháp này **không liên quan** đến việc dùng `var` làm kiểu tham số của phương thức thông thường (vẫn không được phép), và không giúp gán một lambda đứng riêng trực tiếp vào biến `var`.

~~~java
// KHÔNG HỢP LỆ — var ở cả hai phía vẫn thiếu kiểu đích.
var blank = (var text) -> text.isBlank();
~~~

Khi có nhiều tham số, phải dùng nhất quán cách viết trong một lambda:

~~~java
// HỢP LỆ từ Java 11:
java.util.function.BiFunction<String, String, String> join =
        (var a, var b) -> a + b;

// KHÔNG HỢP LỆ — trộn tham số var với tham số suy luận không có var:
java.util.function.BiFunction<String, String, String> bad =
        (var a, b) -> a + b;
~~~

Trong đoạn ví dụ này, dòng `bad` là **minh họa lỗi biên dịch**. Không đặt dòng đó vào chương trình chạy được. Cách viết `(a, b) -> a + b`, `(String a, String b) -> a + b` hoặc `(var a, var b) -> a + b` đều có thể hợp lệ trong ngữ cảnh kiểu đích phù hợp trên Java 17+.

## 9. Chương trình hoàn chỉnh chạy trên Java 17+

Chương trình sau so sánh bốn cách cung cấp kiểu đích: khai báo biến functional interface, tham số của phương thức, kiểu trả về của phương thức và cast. Đồng thời chỉ dùng những API/cú pháp còn áp dụng trên JDK hiện đại.

Lưu tệp đúng tên **`FunctionalTargetDemo.java`**:

~~~java
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;
import java.util.function.ToIntFunction;
import java.util.function.UnaryOperator;

public class FunctionalTargetDemo {

    public static boolean matches(String input, Predicate<String> rule) {
        return rule.test(input);
    }

    public static UnaryOperator<String> normalizer() {
        return String::trim;
    }

    public static void main(String[] args) {
        Predicate<String> startsWithJ =
                text -> text.startsWith("J");

        Function<String, Integer> length =
                String::length;

        Supplier<String> title =
                () -> "Java 10";

        UnaryOperator<String> trim = normalizer();

        var hasFourChars = (Predicate<String>)
                (text -> text.length() >= 4);

        var countChars = (ToIntFunction<String>)
                String::length;

        var value = trim.apply(" Java ");

        System.out.println(value);
        System.out.println(startsWithJ.test(value));
        System.out.println(length.apply(value));
        System.out.println(matches(value, s -> s.contains("av")));
        System.out.println(hasFourChars.test(value));
        System.out.println(countChars.applyAsInt(value));
        System.out.println(title.get());
    }
}
~~~

Biên dịch và chạy bằng JDK hỗ trợ Java 17:

~~~bash
javac --release 17 FunctionalTargetDemo.java
java FunctionalTargetDemo
~~~

**Stdout chính xác:**

~~~text
Java
true
4
true
true
4
Java 10
~~~

Giải thích kết quả:

1. `normalizer()` công bố kiểu `UnaryOperator<String>` cho `String::trim`. Biến `var trim = normalizer()` hợp lệ, và `trim.apply(" Java ")` trả `"Java"`.
2. `startsWithJ` có kiểu đích `Predicate<String>` nên `text` trong lambda là `String`; thử với `"Java"` cho `true`.
3. `length` có kiểu `Function<String, Integer>`, nên `String::length` trả số `4` được boxing sang `Integer` rồi `println` in `4`.
4. `matches(value, s -> s.contains("av"))` cho lambda kiểu đích `Predicate<String>` từ tham số thứ hai; `"Java".contains("av")` trả `true`.
5. Cast `(Predicate<String>)` giúp `var hasFourChars` suy luận kiểu đúng; `"Java"` có bốn ký tự nên trả `true`.
6. Cast `(ToIntFunction<String>)` giúp `var countChars` nhận method reference và `applyAsInt("Java")` trả `4` nguyên thủy.
7. `title` có kiểu đích `Supplier<String>`, vì thế lambda không tham số `() -> "Java 10"` hợp lệ; `title.get()` in `Java 10`.

**Tự kiểm thử:** thử xóa kiểu `Predicate<String>` ở dòng `startsWithJ` và thay bằng `var`; compiler sẽ báo không suy luận được kiểu lambda. Để sửa, khôi phục `Predicate<String>` hoặc chuyển sang cast functional interface tường minh như `hasFourChars`. Không thay đổi phần chương trình chính khi thử ví dụ lỗi biên dịch này.

## 10. Khi nhiều overload cùng nhận biểu thức hàm

Một lời gọi có nhiều overload nhận những functional interface khác nhau có thể trở nên **mơ hồ** nếu cùng một lambda phù hợp với cả hai. Khi ấy, đặt một **biến mang kiểu đích rõ ràng** hoặc cast lambda sẽ giúp chọn đúng overload.

Ví dụ minh họa cấu trúc, các phương thức nằm bên trong cùng một class:

~~~java
@FunctionalInterface
interface RuleA {
    boolean check(String value);
}

@FunctionalInterface
interface RuleB {
    boolean check(String value);
}

static void inspect(RuleA rule) {
    // Xử lý A
}

static void inspect(RuleB rule) {
    // Xử lý B
}

static void example() {
    // KHÔNG HỢP LỆ: lambda này phù hợp với cả RuleA và RuleB.
    // inspect(text -> text.isEmpty());

    // HỢP LỆ: kiểu đích tường minh chọn overload RuleA.
    RuleA rule = text -> text.isEmpty();
    inspect(rule);

    // HỢP LỆ: cast chọn overload RuleB.
    inspect((RuleB) (text -> text.isEmpty()));
}
~~~

Đây là **đoạn code minh họa các thành phần trong class**, chưa phải chương trình `main` độc lập; dòng gọi mơ hồ được comment để không làm lỗi biên dịch đoạn còn lại.

**Quan trọng:** đôi khi compiler có quy tắc chọn một overload cụ thể theo “phương thức phù hợp hơn” hoặc kết quả lambda; không phải mọi lời gọi với lambda và overload đều mơ hồ. Khi có lỗi `reference to ... is ambiguous`, hãy xem chữ ký thật của các overload và làm rõ kiểu đích thay vì ép kiểu bừa.

## 11. Sai lầm thường gặp

| Viết sai hoặc hiểu sai | Tại sao có vấn đề | Cách đúng |
| --- | --- | --- |
| `var f = x -> x.isBlank();` | Lambda cần target type; `var` không tự suy luận ra functional interface. | `Predicate<String> f = x -> x.isBlank();` |
| `var f = String::trim;` | Method reference không có kiểu độc lập. | `UnaryOperator<String> f = String::trim;` |
| `Object f = x -> x.isBlank();` | `Object` không phải functional interface. | Chọn `Predicate<String>`, `Function<..., ...>` hoặc interface tự định nghĩa. |
| `var f = (String x) -> x.isBlank();` | Khai báo kiểu tham số lambda không chỉ ra interface cần hiện thực. | Khai báo kiểu đích ở biến hoặc dùng cast. |
| `var f = (var x) -> x.isBlank();` | `var` trong tham số lambda (Java 11+) cũng cần target type. | `Predicate<String> f = (var x) -> x.isBlank();` |
| Thấy `var f = someFactory();` biên dịch rồi kết luận `var f = () -> ...` cũng được | `someFactory()` là lời gọi đã có kiểu kết quả, lambda đứng riêng không có. | Phân biệt biểu thức khởi tạo có kiểu với lambda/method reference trực tiếp. |
| Chọn `Function<String, Object>` chỉ để code “chạy được” | Làm yếu thông tin kiểu trả về, có thể che giấu hợp đồng thực tế. | Chọn interface và generic thể hiện đúng kết quả mong muốn. |
| Cố tạo functional interface tùy ý nhưng có nhiều phương thức trừu tượng | Lambda chỉ tương thích functional interface theo quy tắc của Java. | Tách chức năng hoặc khai báo đúng một phương thức trừu tượng. |

Một vấn đề khác là checked exception: chẳng hạn lambda gọi API ném `IOException` không thể mặc nhiên gán vào `Function<T,R>` nếu thân lambda để ngoại lệ checked đó thoát ra ngoài mà `apply` không khai báo `throws`. Cần xử lý ngoại lệ thích hợp hoặc sử dụng một interface có hợp đồng `throws` phù hợp.

Đừng nhầm lambda với **việc thực thi lambda**. Gán `Predicate<String> rule = s -> s.isBlank();` tạo đối tượng hành vi; chỉ khi gọi `rule.test(...)` thì nội dung thân lambda mới được thực thi.

## 12. Checklist áp dụng khi phát triển

1. **Xác định biểu thức:** vế phải có phải lambda `->` hoặc method reference `::` trực tiếp không? Nếu có, phải tìm kiểu đích.
2. **Chọn functional interface hợp đồng đúng:** `Predicate` cho điều kiện, `Function` cho biến đổi, `Supplier` cho nguồn giá trị, `Consumer` cho thao tác không trả kết quả, hoặc interface tự định nghĩa nếu nghiệp vụ cần tên rõ ràng.
3. **Cung cấp kiểu đích tại nơi dễ đọc:** ưu tiên kiểu tường minh cho biến; có thể dùng kiểu tham số method, kiểu trả về method hoặc cast trong trường hợp cụ thể.
4. **Chỉ sử dụng `var` khi biểu thức khởi tạo đã có kiểu phù hợp:** ví dụ kết quả gọi method trả `Predicate<String>`, kết quả `Function.apply(...)` hoặc biểu thức đã cast sang functional interface.
5. **Kiểm tra version:** suy luận biến cục bộ `var` từ Java 10; `var` ở **tham số lambda** từ Java 11; code trên nhắm Java 17+ và không dựa vào API đã deprecated.
6. **Kiểm chứng tại compile time:** biên dịch bằng toolchain và `--release` đúng runtime mục tiêu; kiểm tra kỹ lỗi khi thay đổi kiểu đích, overload hoặc generic.
7. **Đọc lại ý nghĩa API:** dùng tên biến/phương thức mô tả hành vi để tránh lạm dụng cast hoặc `var` khiến người đọc khó xác định chức năng.

### Tự đánh giá

**Câu 1.** `var test = s -> s.length() > 2;` có hợp lệ không?

Không. Compiler chưa biết functional interface đích. `Predicate<String> test = s -> s.length() > 2;` hợp lệ.

**Câu 2.** `var test = (Predicate<String>) (s -> s.length() > 2);` có hợp lệ không?

Có, khi import `java.util.function.Predicate`. Cast cung cấp kiểu đích; kiểu `test` được suy luận là `Predicate<String>`. Tuy nhiên, khai báo kiểu biến trực tiếp thường dễ đọc hơn.

**Câu 3.** `var test = ruleFactory();` có hợp lệ nếu `ruleFactory()` trả `Predicate<String>` không?

Có. Kiểu của biểu thức khởi tạo đã được xác định qua kiểu trả về khai báo của phương thức.

**Câu 4.** `Predicate<String> test = (var s) -> s.isBlank();` có hợp lệ trên Java 17 không?

Có. Cú pháp `var` trong tham số lambda tồn tại từ Java 11, còn kiểu đích vẫn được `Predicate<String>` cung cấp.

**Câu 5.** Vì sao `ToIntFunction<String> fn = String::length;` hợp lệ nhưng `var fn = String::length;` không?

Trường hợp đầu đã xác định hàm nhận `String` và trả `int`. Trường hợp sau không chỉ ra kiểu functional interface mà method reference cần hiện thực.

## 13. Tài liệu chính thức vẫn áp dụng hiện nay

- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): phạm vi suy luận kiểu với `var` từ Java 10 và nguyên tắc suy luận từ initializer.
- [OpenJDK — Local Variable Type Inference FAQ](https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-faq.md): giải thích vì sao lambda/method reference không thể trực tiếp làm initializer cho `var` khi thiếu target type.
- [Dev.java — Writing Your First Lambda Expression](https://dev.java/learn/lambdas/first-lambdas/): giới thiệu functional interface và cách xác định kiểu đích.
- [Dev.java — Type Inference](https://dev.java/learn/generics/type-inference/): target typing của lambda trong khai báo biến, lời gọi method và các ngữ cảnh khác.
- [Dev.java — Writing Lambda Expressions as Method References](https://dev.java/learn/language/fp/lambdas/method-references/): giải thích các dạng method reference có kiểu đích.
- [OpenJDK JEP 323 — Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323): phân biệt cú pháp `var` ở tham số lambda từ Java 11.
- [Java Language Specification, Java SE 17 — Chapter 15: Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html): các quy tắc ngôn ngữ về lambda, method reference và poly expression.

**Kết quả cần nắm vững:** nếu khởi tạo một biến trực tiếp bằng lambda hoặc method reference, hãy cung cấp một **functional interface đích cụ thể**. Khi biểu thức đã có kiểu từ lời gọi phương thức hoặc từ cast functional interface, `var` lại có thể suy luận kiểu biến cục bộ bình thường. Quy tắc này vẫn đúng trên các JDK hiện đại.