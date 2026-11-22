# Lambda cần kiểu đích là functional interface

## Mục tiêu

Lambda trong Java biểu diễn một phần hành vi có thể truyền đi, nhưng **một biểu thức lambda không tự có một kiểu lớp hoặc interface độc lập**. Để biên dịch, Java cần **kiểu đích (target type)** là một functional interface phù hợp. Trình biên dịch dựa trên kiểu đích để biết số tham số, kiểu tham số, kiểu kết quả và ngoại lệ được phép của lambda.

Sau bài này, bạn sẽ:

- Nhận diện functional interface và **function descriptor** của phương thức trừu tượng duy nhất (SAM).
- Hiểu tại sao `s -> s.length()` không thể đứng một mình hoặc gán trực tiếp cho `Object`, nhưng gán được cho `Function<String,Integer>`.
- Xác định kiểu đích qua phép gán, đối số phương thức, `return`, ép kiểu và những ngữ cảnh khác.
- Giải thích vai trò của generic và cách lambda tham gia suy luận kiểu khi dùng Stream hay API khác.
- Phân biệt target typing với kiểu của biến `var` và phân biệt lỗi về tham số, kết quả, checked exception.
- Biên dịch và chạy ví dụ Java 17, rồi tự xác định kiểu đích trong các tình huống mới.

## 1. Functional interface là hợp đồng kiểu của lambda

Một **functional interface** là interface có đúng một phương thức trừu tượng theo các quy tắc SAM của Java. Annotation `@FunctionalInterface` giúp compiler kiểm tra điều kiện nhưng không bắt buộc để một interface đủ điều kiện. Các phương thức `default` và `static` không tính là phương thức trừu tượng. Các phương thức trừu tượng tương ứng với các phương thức `public` của `Object` cũng không biến interface thành giao diện có nhiều SAM.

Ví dụ:

```java
@FunctionalInterface
interface TextRule {
    boolean matches(String text);

    default TextRule negateRule() {
        return value -> !matches(value);
    }
}
```

Ở đây, `matches` là phương thức hàm duy nhất. Nó tạo **function descriptor**:

```text
(String) -> boolean
```

Nghĩa là một triển khai phải nhận đúng một `String` và tạo kết quả `boolean`; chẳng hạn:

```java
TextRule nonBlank = text -> !text.isBlank();
```

Khi gán lambda cho `TextRule`, compiler kiểm tra body theo descriptor của `TextRule`. Lambda được chuyển thành đối tượng có thể gọi qua phương thức `matches`:

```java
boolean ok = nonBlank.matches("Java"); // true
```

Lambda có thể được hiện thực ở runtime bằng cơ chế riêng của JVM; không nên giả định nó tương đương một anonymous class cố định về danh tính hay cấu trúc. Điều cần dùng trong thiết kế là **hợp đồng functional interface**.

Trong thư viện chuẩn, những target thường gặp:

| Interface | Phương thức SAM | Function descriptor |
| --- | --- | --- |
| `Predicate<T>` | `boolean test(T value)` | `(T) -> boolean` |
| `Function<T,R>` | `R apply(T value)` | `(T) -> R` |
| `Consumer<T>` | `void accept(T value)` | `(T) -> void` |
| `Supplier<T>` | `T get()` | `() -> T` |
| `UnaryOperator<T>` | `T apply(T value)` | `(T) -> T` |
| `BiFunction<T,U,R>` | `R apply(T a,U b)` | `(T,U) -> R` |
| `Runnable` | `void run()` | `() -> void` |
| `Callable<T>` | `T call() throws Exception` | `() -> T throws Exception` |

`Runnable` thuộc `java.lang`, `Callable` thuộc `java.util.concurrent`, còn `Predicate`, `Function`, `Supplier`, `Consumer` và các biến thể thuộc `java.util.function`. Có nhiều loại SAM khác; điều quan trọng là **số và kiểu tham số, kết quả, ngoại lệ** chứ không phải chỉ tên interface.

## 2. Vì sao lambda cần một kiểu đích?

Hãy xem:

```java
// Sai: không có kiểu đích để suy luận.
var f = text -> text.length();
```

`var` có thể suy luận kiểu của một biến cục bộ từ initializer có kiểu phù hợp, nhưng **không thể tự suy luận functional interface cho một lambda trần**. Đổi thành `(String text) -> text.length()` vẫn không làm `var f = ...` hợp lệ: lambda dù khai báo kiểu tham số vẫn cần một target functional interface cụ thể.

Tương tự:

```java
// Sai: Object không phải functional interface.
Object f = text -> text.length();
```

`Object` là lớp cha phổ biến nhưng không có một SAM để chỉ ra lambda sẽ triển khai phương thức nào. Java cũng không cho phép viết `(text -> text.length()).toString()` như thể lambda là giá trị đã có kiểu độc lập.

Cách đúng là cung cấp target type:

```java
java.util.function.Function<String,Integer> length =
        text -> text.length();

int size = length.apply("Java"); // 4
```

Java thay `T = String` và `R = Integer` trong `Function<T,R>`, nên descriptor cụ thể là `(String) -> Integer`. Lambda nhận `text` kiểu `String` (cho phép gọi `length()`), kết quả primitive `int` có thể boxing thành `Integer`.

Viết kiểu tham số tường minh cũng hợp lệ:

```java
java.util.function.Function<String,Integer> length =
        (String text) -> text.length();
```

Cả hai cách có cùng target. Điều này gọi là **target typing**: kiểm tra kiểu biểu thức theo ngữ cảnh cần một kiểu cụ thể, thay vì cố suy luận một kiểu độc lập từ biểu thức trước khi biết nơi dùng.

## 3. Poly expression và các ngữ cảnh tạo target type

Lambda là một loại **poly expression** trong Java. Khi đứng ở vị trí hỗ trợ target typing, nó có thể được kiểm tra theo một functional interface được mong đợi.

### 3.1. Phép gán vào biến hoặc field

```java
java.util.function.Predicate<String> startsWithJ =
        text -> text.startsWith("J");

java.util.function.Function<String,Integer> size =
        text -> text.length();

java.util.function.Supplier<String> greeting =
        () -> "Xin chào";
```

Mỗi kiểu ở vế trái đưa cho compiler một descriptor khác nhau. `startsWithJ` cần trả `boolean`; `size` cần trả `Integer`; `greeting` không có tham số và trả `String`. Cùng cách dùng mũi tên `->` nhưng hợp đồng hoàn toàn khác.

Trong trường hợp field của một class:

```java
class PriceService {
    private final java.util.function.IntUnaryOperator tax =
            amount -> amount + 10;
}
```

Kiểu field `IntUnaryOperator` là target `(int) -> int`. Việc field là `final` không làm đổi nguồn suy luận kiểu; `final` ở đây chỉ giới hạn việc gán lại field.

### 3.2. Đối số truyền vào phương thức

Xét API:

```java
static String decorate(
        String text,
        java.util.function.UnaryOperator<String> action) {
    return "[" + action.apply(text) + "]";
}
```

Khi gọi:

```java
String result = decorate("java", s -> s.toUpperCase());
```

Kiểu của đối số thứ hai là `UnaryOperator<String>`, một subtype của `Function<String,String>`. Descriptor `(String) -> String` cho biết `s` là `String`, ngay cả khi lambda không được lưu vào biến riêng. Kết quả ở đây là `"[JAVA]"`.

**Không cần ghi `(String s)` chỉ để compiler tìm được target**, vì chữ ký phương thức `decorate` đã cung cấp target đó.

### 3.3. Giá trị trả về từ phương thức

```java
static java.util.function.Supplier<String> greetingFactory() {
    return () -> "Xin chào";
}
```

Phương thức khai báo trả `Supplier<String>`, nên biểu thức lambda trong `return` nhận descriptor `() -> String`. Caller nhận một Supplier và chỉ thực thi body khi gọi `get()`:

```java
String message = greetingFactory().get();
```

Đặt lambda vào `return` không tự biến lambda thành giá trị `String`; nó trả **đối tượng thực thi functional interface**, sau đó mới gọi `get()` để lấy chuỗi.

### 3.4. Ép kiểu và ngữ cảnh có target được chỉ rõ

Đôi khi cần ghi functional interface trong biểu thức ép kiểu:

```java
Object value = (java.util.function.Function<String,Integer>)
        text -> text.length();
```

Ép kiểu cung cấp target `Function<String,Integer>` cho lambda; kết quả của biểu thức ép kiểu sau đó có thể được gán cho `Object`. Điều này khác hoàn toàn với phép gán `Object value = text -> text.length()` vốn không hợp lệ.

Có thể gán qua kiểu intersection phù hợp, chẳng hạn khi một giá trị lambda phải đồng thời đáp ứng một functional interface và một marker interface:

```java
Runnable serializableTask =
        (Runnable & java.io.Serializable) () -> {};
```

Ví dụ này có target là intersection gồm `Runnable` (có SAM `run()`) và marker interface `Serializable` (không có phương thức trừu tượng). Tuy nhiên, **khả năng serializable về mặt kiểu không tự động bảo đảm thiết kế serialization dài hạn an toàn cho lambda**; chỉ dùng khi có yêu cầu cụ thể và hiểu rủi ro thay đổi implementation.

### 3.5. Biểu thức điều kiện

Các nhánh của một biểu thức điều kiện có thể nhận target type từ ngữ cảnh:

```java
boolean excited = true;
java.util.function.Supplier<String> message =
        excited ? () -> "Wow!" : () -> "Hello";
```

Ở đây hai lambda nhận target `Supplier<String>` thông qua ngữ cảnh phép gán, nên cùng có descriptor `() -> String`. Nếu bỏ target và yêu cầu compiler suy luận một kiểu độc lập từ hai lambda, có thể không có đủ thông tin; khi cần, khai báo biến trung gian có functional interface rõ ràng.

## 4. Target type dẫn dắt cả kiểu tham số lẫn kiểu kết quả

Một lambda có body trông giống nhau có thể hợp lệ với nhiều target khác nhau, miễn phù hợp descriptor.

```java
java.util.function.Predicate<String> hasFour =
        text -> text.length() >= 4;

java.util.function.Function<String,Boolean> boxedHasFour =
        text -> text.length() >= 4;
```

Cùng body, nhưng một target trả `boolean` primitive và một target trả `Boolean` wrapper. Compiler có thể boxing khi kiểm tra tính tương thích của kiểu kết quả.

Mặt khác:

```java
// Sai: Function<Object,Integer> cho text kiểu Object,
// Object không có phương thức length().
java.util.function.Function<Object,Integer> wrong =
        text -> text.length();
```

Tên tham số `text` không khiến compiler tự coi nó là `String`. Target đã cho kiểu `Object`, nên body bị từ chối.

Có thể viết tham số tường minh nhưng phải khớp function descriptor:

```java
// Hợp lệ.
java.util.function.IntUnaryOperator twice =
        (int value) -> value * 2;

// Sai: target nhận int, lambda tự khai báo String.
java.util.function.IntUnaryOperator wrong =
        (String value) -> value.length();
```

Target còn quyết định kiểu kết quả. Ví dụ:

```java
// Sai: Predicate<String> yêu cầu boolean, không phải int.
java.util.function.Predicate<String> invalid =
        text -> text.length();

// Hợp lệ.
java.util.function.Predicate<String> valid =
        text -> text.length() > 0;
```

Không thể chỉ nhìn phần tham số để quyết định lambda có tương thích hay không. Cần kiểm tra **toàn bộ function descriptor**.

### Value-compatible và void-compatible

Một body dạng biểu thức là *statement expression*, chẳng hạn một lời gọi phương thức, có thể tương thích với ngữ cảnh trả `void` khi giá trị kết quả bị bỏ qua:

```java
java.util.function.Function<String,Integer> getLength =
        text -> text.length();

java.util.function.Consumer<String> ignoreLength =
        text -> text.length();
```

Cả hai ví dụ **đều hợp lệ**: lời gọi `text.length()` là statement expression, nên với `Consumer` có thể thực hiện lời gọi và bỏ kết quả. Tuy nhiên, nếu ngữ nghĩa ứng dụng cần giữ độ dài, nên dùng `Function` hoặc `ToIntFunction`, tránh `Consumer` làm mất giá trị hữu ích.

Ngược lại, với lambda viết body dạng block, các quy tắc về `return` trở nên rõ hơn:

```java
java.util.function.Function<String,Integer> length = text -> {
    return text.length();
};

java.util.function.Consumer<String> print = text -> {
    System.out.println(text);
};
```

Nếu block dành cho `Function` có đường đi kết thúc bình thường mà không `return` giá trị, sẽ lỗi biên dịch. Nếu block dành cho `Consumer` dùng `return text.length();` thì không tương thích với kiểu `void`.

## 5. Target type và cú pháp tham số lambda

Khi target đã biết, có ba cách khai báo tham số:

```java
java.util.function.Function<String,Integer> inferred =
        text -> text.length();

java.util.function.Function<String,Integer> explicit =
        (String text) -> text.length();

java.util.function.Function<String,Integer> usingVar =
        (var text) -> text.length();
```

Với target `Function<String,Integer>`, cả ba đều nhận `String` và cho cùng kết quả. Cú pháp dùng `var` ở tham số lambda có từ Java 11. Nó **khác** với `var fn = text -> text.length()`, nơi `var` đứng ở khai báo biến cục bộ và không cung cấp target.

Những quy tắc quan trọng:

- Lambda không có tham số dùng `() -> expression`.
- Một tham số suy luận ngầm định có thể viết `text -> expression` hoặc `(text) -> expression`.
- Một tham số **khai báo kiểu tường minh** hoặc dùng `var` cần dấu ngoặc: `(String text)`, `(var text)`.
- Hai tham số trở lên luôn cần dấu ngoặc, ví dụ `(a,b) -> a + b`.
- Không trộn kiểu ngầm định, kiểu tường minh và `var` trong cùng danh sách tham số: `(var a, int b)` và `(String a, b)` đều không hợp lệ.
- Kiểu khai báo tường minh phải tương thích với descriptor; `(Integer x)` không được coi là giống hệt `(int x)` trong khai báo tham số lambda.

Ví dụ:

```java
@FunctionalInterface
interface Formatter {
    String format(String text, int times);
}

Formatter repeat = (text, times) -> text.repeat(times);
Formatter same = (String text, int times) -> text.repeat(times);
Formatter alsoSame = (var text, var times) -> text.repeat(times);
```

Tất cả đều dùng descriptor `(String,int) -> String`. Chúng không thay hợp đồng của interface, chỉ khác cách viết tham số.

## 6. Generic method và Stream cung cấp target như thế nào?

Khi API generic nhận một hàm, target type của lambda được xác định từ các ràng buộc kiểu liên quan đến cả lời gọi.

```java
static <T,R> R convert(
        T value,
        java.util.function.Function<T,R> mapper) {
    return mapper.apply(value);
}
```

Một lời gọi hợp lệ:

```java
int size = convert("Lambda", text -> text.length());
```

Đối số `"Lambda"` giúp compiler suy luận `T` phù hợp với `String`. Lambda được kiểm tra với target `Function<T,R>` sau khi xem xét ràng buộc, và `text.length()` góp phần xác định kiểu kết quả `R`. Kết quả là `6`.

Suy luận generic có nhiều bước và ràng buộc (chẳng hạn wildcard, kiểu dự kiến của kết quả hoặc overload), nên không nên tự quy mọi trường hợp thành quy tắc “Java luôn suy ra từ biến bên trái”. Nếu compiler không tìm được kiểu nhất quán, có thể tách lambda ra một biến `Function<String,Integer>`, thêm type witness cho phương thức generic hoặc điều chỉnh API.

Trong Stream:

```java
java.util.List<Integer> lengths =
        java.util.List.of("A", "BB", "CCC")
                .stream()
                .map(String::length)
                .toList();
```

`Stream<String>.map` nhận một `Function<? super String,? extends R>`. Phương thức được tham chiếu `String::length` cho kết quả `int`, có thể boxing thành `Integer`; kết quả cuối là `[1, 2, 3]`. Cũng có thể viết `.map(s -> s.length())` với ngữ cảnh suy luận tương tự.

Khi muốn tránh boxing:

```java
int sum = java.util.List.of("A", "BB", "CCC")
        .stream()
        .mapToInt(String::length)
        .sum(); // 6
```

`mapToInt` có target `ToIntFunction<? super String>` với descriptor trả `int`. Việc chọn API đích ảnh hưởng đến cả kiểu kết quả lẫn các phép toán tiếp theo.

## 7. Mơ hồ khi overload có nhiều target

Một lambda không gắn cố định với một functional interface trước khi compiler xem xét lời gọi; nếu một tên phương thức có nhiều overload nhận những functional interface khác nhau, có thể có **mơ hồ**.

Ví dụ minh họa:

```java
@FunctionalInterface
interface TextRule {
    boolean check(String value);
}

@FunctionalInterface
interface TextMapper {
    String map(String value);
}

static void run(TextRule rule) { /* ... */ }
static void run(TextMapper mapper) { /* ... */ }
```

Hai interface đều nhận một `String` nhưng trả về khác nhau. Với một lambda có body phù hợp chỉ một interface, compiler có thể chọn overload thích hợp dựa trên quy tắc overload và tính tương thích của lambda. Nhưng không phải mọi trường hợp compiler đều chọn được duy nhất: những cặp functional interface có descriptor gần nhau, generic phức tạp, hoặc biểu thức lambda phù hợp cả hai có thể dẫn tới `reference to run is ambiguous`.

Cách làm rõ ý định:

```java
TextRule rule = s -> s.startsWith("J");
run(rule);

run((TextRule) s -> s.startsWith("J"));
```

Biến `rule` hoặc cast `(TextRule)` đưa ra target cụ thể. Khi thiết kế API công khai, nên tránh nhiều overload chỉ khác nhau ở các functional interface khó phân biệt; có thể dùng tên phương thức rõ nghĩa như `filterBy` và `mapWith`.

**Phân biệt target của lambda với kiểu trả về của phương thức bao quanh.** Java không chọn overload chỉ từ “bên trái phép gán là `String`” trong mọi tình huống; quy tắc overload và kiểm tra tính thích dụng của lambda phải được xét theo đặc tả Java. Nếu không chắc, viết ví dụ tối thiểu và biên dịch để thấy lỗi thực tế.

## 8. Ngoại lệ và giới hạn của kiểu đích

Function descriptor có thể nêu checked exception được phép. Hai interface nhận và trả kiểu giống nhau nhưng có hợp đồng ngoại lệ khác nhau:

```java
@FunctionalInterface
interface CheckedReader {
    String read(String path) throws java.io.IOException;
}
```

Nếu tồn tại phương thức:

```java
// Minh họa chữ ký, phương thức thực tế cần được định nghĩa.
static String load(String path) throws java.io.IOException;
```

Lambda sau tương thích với `CheckedReader`:

```java
CheckedReader reader = path -> load(path);
```

Nhưng không tương thích với `Function<String,String>`:

```java
// Không biên dịch vì Function.apply không khai báo IOException.
java.util.function.Function<String,String> reader =
        path -> load(path);
```

`main throws Exception` ở bên ngoài không sửa được hợp đồng của `Function.apply`. Phải bắt ngoại lệ bên trong lambda, chuyển sang unchecked theo chính sách có chủ đích, hoặc định nghĩa một functional interface đích có `throws` phù hợp.

Các đoạn ở mục này **chỉ minh họa chữ ký và khả năng tương thích**; không phải một chương trình Java độc lập (vì `load` không có body thực tế).

## 9. Ví dụ Java 17 hoàn chỉnh

Ví dụ sau diễn giải target type ở bốn vị trí: biến đích, đối số phương thức, giá trị trả về và phương thức generic. Đồng thời chứng minh một lambda có thể triển khai những functional interface khác nhau nếu tương thích descriptor.

Tạo tệp **`LambdaTargetTypeDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;
import java.util.function.UnaryOperator;

public class LambdaTargetTypeDemo {
    @FunctionalInterface
    interface Formatter {
        String format(String text, int times);
    }

    static String decorate(String text, UnaryOperator<String> operation) {
        return "[" + operation.apply(text) + "]";
    }

    static <T, R> R convert(T value, Function<T, R> mapper) {
        return mapper.apply(value);
    }

    static Supplier<String> greetingFactory() {
        return () -> "Xin chào";
    }

    public static void main(String[] args) {
        Function<String, Integer> length = text -> text.length();
        Predicate<String> atLeastFour = text -> text.length() >= 4;
        Consumer<String> show = text ->
                System.out.println("Consumer: " + text);
        Formatter repeat = (text, times) -> text.repeat(times);
        UnaryOperator<String> upper = text ->
                text.toUpperCase(Locale.ROOT);

        Supplier<String> greeting = greetingFactory();
        String decorated = decorate("java", upper);
        int converted = convert("Lambda", String::length);
        List<Integer> lengths = List.of("A", "BB", "CCC")
                .stream().map(String::length).toList();

        System.out.println("Function: " + length.apply("Java"));
        System.out.println("Predicate: " + atLeastFour.test("Go"));
        System.out.println("Formatter: " + repeat.format("Hi", 2));
        System.out.println("Decorate: " + decorated);
        System.out.println("Generic: " + converted);
        System.out.println("Supplier: " + greeting.get());
        System.out.println("Stream: " + lengths);
        show.accept("Done");
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac LambdaTargetTypeDemo.java
java LambdaTargetTypeDemo
```

**Standard output** (chạy với terminal dùng UTF-8 để hiển thị đầy đủ dấu tiếng Việt):

```text
Function: 4
Predicate: false
Formatter: HiHi
Decorate: [JAVA]
Generic: 6
Supplier: Xin chào
Stream: [1, 2, 3]
Consumer: Done
```

Giải thích:

1. `length` có target `Function<String,Integer>`, nên `text` là `String`, `length()` trả `int` rồi boxing nếu cần; `"Java"` có độ dài `4`.
2. `atLeastFour` có target `Predicate<String>`, trả `boolean`. `"Go"` có độ dài `2` nên kết quả `false`.
3. `repeat` có target `Formatter` với descriptor `(String,int) -> String`; `"Hi".repeat(2)` cho `"HiHi"`.
4. `upper` có target `UnaryOperator<String>`, còn `decorate` nhận chính kiểu này làm tham số thứ hai; `"java"` được viết hoa và bọc thành `"[JAVA]"`.
5. `convert` là phương thức generic; compiler suy luận kiểu từ `"Lambda"`, method reference `String::length` và ngữ cảnh kết quả, cho `6`.
6. `greetingFactory` cung cấp target `Supplier<String>` ngay ở kiểu trả về, nên `() -> "Xin chào"` hợp lệ trong câu lệnh `return`.
7. `Stream<String>.map` yêu cầu mapper tương thích `Function`; `String::length` tạo danh sách độ dài `[1, 2, 3]`.
8. `show` có target `Consumer<String>`; body in `Consumer: Done` và không có giá trị trả về cần sử dụng.

Chương trình được viết đủ trong một lớp `public`, tên file khớp tên lớp, chỉ dùng API có trong Java 17.

## 10. Các lỗi thường gặp

### 10.1. Dùng lambda trần với var hoặc Object

```java
// Sai: thiếu functional interface target.
var action = () -> 42;
Object any = () -> 42;

// Đúng:
java.util.function.Supplier<Integer> action = () -> 42;
Object any = (java.util.function.Supplier<Integer>) () -> 42;
```

Trên đây là các dòng đối chiếu **không dùng chung trong một chương trình** vì tên `action` và `any` được khai báo lặp lại; các dòng sai chỉ nhằm minh họa lỗi biên dịch.

### 10.2. Dùng class hoặc interface không phải functional interface

```java
// Sai vì List không có duy nhất một phương thức trừu tượng:
java.util.List<String> list = () -> "text";
```

Một interface có nhiều phương thức trừu tượng độc lập cũng không thể là target của lambda. Dùng lớp/record để mô hình dữ liệu, dùng functional interface để mô hình một hợp đồng hành vi SAM.

### 10.3. Chỉ kiểm tra số tham số mà quên kiểu kết quả

```java
// Sai: Predicate<String> đòi boolean.
java.util.function.Predicate<String> invalid =
        s -> s.length();
```

Kiểm tra cả kiểu trả về. Đổi thành `s -> s.length() > 0` nếu mục tiêu là điều kiện, hoặc dùng `Function<String,Integer>` nếu mục tiêu là độ dài.

### 10.4. Viết rõ kiểu tham số nhưng sai target

```java
// Sai: IntUnaryOperator nhận int, không nhận String.
java.util.function.IntUnaryOperator wrong =
        (String s) -> s.length();
```

Ghi kiểu tường minh không có quyền thay đổi descriptor của target. Đổi sang `(int n) -> n * 2` hoặc chọn interface thật sự nhận `String`.

### 10.5. Đồng nhất method reference với kiểu hàm độc lập

Method reference, giống lambda, thường cũng cần target functional interface:

```java
java.util.function.ToIntFunction<String> length =
        String::length;
```

Kiểu này có descriptor `(String) -> int`. Không được mong `var length = String::length;` tự đoán phải là `ToIntFunction<String>` thay vì những functional interface khác cũng có thể tương thích.

### 10.6. Xử lý checked exception theo sai tầng

`Function<T,R>` không có `throws IOException`; dù phương thức gọi bên ngoài khai báo `throws IOException`, lambda vẫn không thể để checked exception đó thoát từ `apply`. Nếu cần đúng hợp đồng, tạo interface `CheckedFunction<T,R>` hoặc xử lý ngoại lệ bên trong lambda theo chính sách được xác định.

### 10.7. Tưởng lambda mặc định là hàm thuần

Target type chỉ đảm bảo hợp đồng phương thức, **không đảm bảo** không có side effect, không thay đổi trạng thái và không phụ thuộc đồng hồ. `Supplier<Integer> next = counter::incrementAndGet` vẫn có tác dụng phụ; `Consumer` thường dùng để làm hành động có thể quan sát được. Hãy đánh giá body và cách API sử dụng, không suy tính thuần chỉ từ cú pháp `->`.

## 11. Bài tập tự luyện

1. Cho `Function<String,Integer> f = s -> s.length();`. Hãy nêu target type và function descriptor, sau đó viết lại lambda với `(String s)` và `(var s)`.
2. Giải thích vì sao `var f = s -> s.trim();` không biên dịch, ngay cả khi đổi thành `var f = (String s) -> s.trim();`.
3. Cho `static void run(Predicate<String> check)`. Compiler suy luận kiểu `x` trong `run(x -> x.startsWith("J"))` từ đâu?
4. Với `Supplier<String> supplier = () -> "hi";`, nếu đổi body thành `s -> "hi"`, vấn đề nằm ở số lượng tham số hay kiểu kết quả?
5. Viết một `UnaryOperator<String>` để thêm ký tự `"!"` vào cuối chuỗi, truyền nó vào một phương thức nhận `UnaryOperator<String>`.
6. Giải thích vì sao `Predicate<String> p = s -> s.length();` không hợp lệ, dù `s` là `String` hợp lệ.
7. Cho `TextRule rule = text -> !text.isBlank();`. Nếu một target khác nhận `Object`, điều gì xảy ra khi body vẫn gọi `isBlank()`?
8. Xem xét `Object x = (Supplier<String>) () -> "ready";`. Cast có vai trò gì? Vì sao bỏ cast dẫn đến lỗi?
9. Sửa lỗi khi `Function<Path,String>` nhận lambda gọi phương thức khai báo `throws IOException`.
10. Với `Stream.of("a", "bb").map(s -> s.length()).toList()`, suy luận kiểu phần tử đầu vào, kết quả mapper và phần tử danh sách kết quả.

**Gợi ý đáp án:** (1) `Function<String,Integer>`, descriptor `(String) -> Integer`. (2) Lambda trần không có functional interface target. (3) Từ tham số của phương thức `run`: `Predicate<String>`. (4) `Supplier` yêu cầu 0 tham số. (5) `s -> s + "!"`. (6) `Predicate` cần `boolean`, body trả `int`. (7) Nếu chỉ có `Object`, compiler không thấy `isBlank()`. (8) Cast cung cấp target `Supplier<String>`. (9) Bắt/chuyển ngoại lệ theo quy tắc nghiệp vụ hoặc dùng functional interface có `throws`. (10) `String` vào, `int` có thể boxing thành `Integer`, kết quả `List<Integer>`.

## Kết luận

**Lambda trong Java cần một functional interface làm kiểu đích** để compiler xác định function descriptor và kiểm tra tính tương thích của phần thân. Kiểu đích có thể được cung cấp bởi phép gán, đối số phương thức, kiểu trả về, cast hoặc các ngữ cảnh hỗ trợ target typing. Biết xác định target trước khi đọc lambda giúp xử lý lỗi suy luận, dùng generic/Stream chính xác và thiết kế API có hợp đồng hành vi rõ ràng.
