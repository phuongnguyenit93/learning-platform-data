# Mốc Java 8 cho default, static method và interface hàm

Java 8 mở rộng khả năng của interface theo ba hướng quan trọng: **default method** cho phép interface cung cấp hành vi mặc định, **static method** đặt các hàm tiện ích gắn với chính interface, và **functional interface** tạo kiểu đích cho lambda expression cùng method reference. Những thay đổi này giúp thư viện Java phát triển API mà vẫn hỗ trợ nhiều lớp triển khai cũ.

Interface vẫn mô tả một hợp đồng. Default method bổ sung cách thực hiện có thể dùng chung; static method là thao tác gọi qua tên interface; functional interface là interface có một phương thức trừu tượng phù hợp để biểu diễn một hành động.

## 1. Vì sao Java 8 cần mở rộng interface?

Trước Java 8, interface chủ yếu khai báo các phương thức trừu tượng và hằng số. Khi một thư viện muốn thêm phương thức vào interface đã được nhiều lớp triển khai, các lớp đó có thể phải bổ sung phần triển khai mới. Việc thay đổi một hợp đồng dùng rộng rãi vì vậy rất tốn kém.

Java 8 bổ sung default method để interface có thể cung cấp phần thân cho một phương thức mới. Lớp triển khai có thể dùng hành vi mặc định ngay hoặc ghi đè khi cần. Java 8 cũng bổ sung static method để gom các hàm tiện ích vào đúng nơi sở hữu API, đồng thời giới thiệu lambda expression và Stream API, vốn dựa nhiều vào functional interface.

Ví dụ về ba loại phương thức trong cùng một interface:

~~~java
interface TextRule {
    String apply(String text); // phương thức trừu tượng

    default String bracket(String text) {
        return "[" + apply(text) + "]";
    }

    static TextRule trim() {
        return String::trim;
    }
}
~~~

`apply` xác định hành động mà mỗi implementation phải cung cấp. `bracket` là hành vi dùng chung dựa trên `apply`. `trim` là hàm tiện ích tĩnh tạo ra một `TextRule` có nhiệm vụ loại bỏ khoảng trắng ở đầu và cuối chuỗi.

Interface có thể chứa cả phương thức trừu tượng, default và static. Việc có thêm default hoặc static method **không tự động làm interface mất tính functional**.

## 2. Default method: hành vi mặc định trong hợp đồng

Default method là phương thức interface có từ khóa `default` và có phần thân. Lớp triển khai không bắt buộc ghi đè phương thức này. Nếu không ghi đè, lời gọi có thể sử dụng phần triển khai mặc định.

~~~java
interface Printable {
    void print(String text);

    default void printLine(String text) {
        print(text);
        System.out.println();
    }
}
~~~

Lớp triển khai chỉ cần cung cấp `print`:

~~~java
class ConsolePrinter implements Printable {
    @Override
    public void print(String text) {
        System.out.print(text);
    }
}
~~~

Khi gọi `new ConsolePrinter().printLine("Hello")`, phương thức mặc định gọi `print` trên cùng đối tượng, nên implementation `ConsolePrinter.print` được sử dụng. Default method có thể gọi các phương thức khác của interface và có thể bị lớp triển khai ghi đè.

Một default method không làm interface có trạng thái instance riêng. Interface không có các trường instance thông thường; các trường được khai báo trong interface là hằng số `public static final`. Nếu hành vi cần trạng thái riêng cho từng đối tượng, một lớp cụ thể hoặc abstract class thường phù hợp hơn.

### Quy tắc chọn phương thức khi có nhiều implementation

Khi lớp kế thừa hành vi từ lớp cha và interface, Java áp dụng quy tắc phân giải:

1. **Phương thức cụ thể của lớp thắng default method từ interface.** Nếu lớp cha đã có một phương thức instance tương thích, phương thức lớp được ưu tiên.
2. **Interface cụ thể hơn thắng interface cha.** Nếu `Child` kế thừa `Parent` và cả hai định nghĩa default cùng chữ ký, default của `Child` được ưu tiên.
3. **Hai interface không có quan hệ kế thừa cùng định nghĩa default trùng chữ ký gây xung đột.** Lớp triển khai phải ghi đè phương thức đó để quyết định hành vi.
4. Trong phần ghi đè, có thể gọi rõ phần triển khai mặc định bằng `InterfaceName.super.methodName()` khi phù hợp.

Ví dụ về xung đột:

~~~java
interface HasCode {
    default String code() {
        return "A";
    }
}

interface HasName {
    default String code() {
        return "B";
    }
}

class Item implements HasCode, HasName {
    @Override
    public String code() {
        return HasCode.super.code() + "-" + HasName.super.code();
    }
}
~~~

Nếu `Item` không ghi đè `code`, trình biên dịch báo lỗi vì không thể tự chọn giữa hai default method. Bản triển khai trên chủ động kết hợp cả hai hành vi, nên `new Item().code()` trả về `"A-B"`.

Default method cũng có thể được một interface con khai báo lại dưới dạng abstract để yêu cầu implementation cụ thể cung cấp hành vi. Vì vậy, khi thiết kế API, cần xem xét cả quan hệ kế thừa interface và các phương thức mà lớp triển khai đã có.

## 3. Static method trong interface

Static method được khai báo bằng từ khóa `static` và có phần thân. Nó thuộc về interface, nên được gọi bằng tên interface:

~~~java
interface NumberTools {
    static boolean isEven(int number) {
        return number % 2 == 0;
    }
}

boolean result = NumberTools.isEven(8);
~~~

Static method hữu ích để đặt hàm tạo đối tượng, hàm kiểm tra hoặc tiện ích liên quan ngay trong API của interface. Người dùng không phải tìm một lớp tiện ích riêng nếu hành vi đó thuộc về interface.

Khác với default method, static method của interface **không được kế thừa như một phương thức instance** bởi lớp triển khai hoặc interface con, và không tham gia dispatch đa hình. Hãy gọi `NumberTools.isEven(8)`, không gọi `instance.isEven(8)`. Một static method có cùng tên ở lớp triển khai là một phương thức tĩnh riêng, không ghi đè static method của interface.

Các static method trong interface cũng không được gọi bằng `InterfaceName.super`. Cú pháp `InterfaceName.super.method()` dành cho việc chọn một triển khai instance mặc định.

## 4. Functional interface: một phương thức trừu tượng, nhiều khả năng

Functional interface (interface hàm) là interface có đúng một phương thức trừu tượng phù hợp làm mục tiêu của lambda expression hoặc method reference. Annotation `@FunctionalInterface` không bắt buộc để interface trở thành functional interface, nhưng nên dùng để trình biên dịch kiểm tra ý định thiết kế.

~~~java
@FunctionalInterface
interface TextRule {
    String apply(String text);

    default String bracket(String text) {
        return "[" + apply(text) + "]";
    }

    static TextRule trim() {
        return String::trim;
    }
}
~~~

`TextRule` vẫn là functional interface dù có thêm một default method và một static method, vì chỉ `apply` là phương thức trừu tượng cần implementation. Lambda như `text -> text.trim()` có thể tạo một đối tượng phù hợp với kiểu đích `TextRule`.

Các functional interface chuẩn trong `java.util.function` thường gặp:

| Interface | Phương thức trừu tượng | Công dụng |
|---|---|---|
| `Predicate<T>` | `boolean test(T value)` | Kiểm tra điều kiện, trả về đúng/sai. |
| `Function<T, R>` | `R apply(T value)` | Chuyển đổi một giá trị thành giá trị khác. |
| `Consumer<T>` | `void accept(T value)` | Nhận một giá trị và thực hiện tác động. |
| `Supplier<T>` | `T get()` | Cung cấp một giá trị mà không nhận tham số. |
| `UnaryOperator<T>` | `T apply(T value)` | Biến đổi giá trị và trả về cùng kiểu. |
| `BinaryOperator<T>` | `T apply(T left, T right)` | Kết hợp hai giá trị cùng kiểu để tạo một giá trị cùng kiểu. |

Java 8 cung cấp thêm các biến thể cho kiểu nguyên thủy, chẳng hạn `IntPredicate`, `IntFunction<R>` và `ToIntFunction<T>`, giúp giảm boxing/unboxing trong một số trường hợp.

Một interface vẫn có thể là functional interface khi khai báo default và static method. Các phương thức trừu tượng tương thích được kế thừa từ nhiều interface cha có thể đại diện cho cùng một chữ ký logic; tiêu chí quan trọng là hợp đồng trừu tượng cuối cùng có một phương thức chức năng, chứ không đơn giản là đếm số dòng khai báo trong toàn bộ cây kế thừa. `@FunctionalInterface` giúp phát hiện khi một thay đổi vô tình phá vỡ điều kiện này.

## 5. Ví dụ Java 17+ chạy được

Lưu đoạn mã dưới đây vào `Java8InterfaceEvolution.java`. Mã sử dụng cú pháp Java 8 trở lên và chạy được trên JDK 17.

~~~java
@FunctionalInterface
interface TextRule {
    String apply(String text);

    default String bracket(String text) {
        return "[" + apply(text) + "]";
    }

    static TextRule trim() {
        return String::trim;
    }
}

interface HasCode {
    default String code() {
        return "A";
    }
}

interface HasName {
    default String code() {
        return "B";
    }
}

class Item implements HasCode, HasName {
    @Override
    public String code() {
        return HasCode.super.code() + "-" + HasName.super.code();
    }
}

public class Java8InterfaceEvolution {
    public static void main(String[] args) {
        TextRule trim = TextRule.trim();
        TextRule upper = text -> text.toUpperCase(java.util.Locale.ROOT);

        System.out.println("trim=" + trim.apply("  Java  "));
        System.out.println("bracket=" + trim.bracket("  Java  "));
        System.out.println("upper=" + upper.apply("java 8"));
        System.out.println("default=" + upper.bracket("java"));
        System.out.println("conflict=" + new Item().code());
    }
}
~~~

Biên dịch và chạy:

~~~text
javac Java8InterfaceEvolution.java
java Java8InterfaceEvolution
~~~

Kết quả chuẩn:

~~~text
trim=Java
bracket=[Java]
upper=JAVA 8
default=[JAVA]
conflict=A-B
~~~

Trong ví dụ này, `TextRule.trim()` là static method được gọi qua tên interface. Giá trị trả về là một functional interface, nên có thể gán vào biến `TextRule`. `String::trim` là method reference tương thích với phương thức `apply(String)`. Phương thức `bracket` là default method và gọi `apply` trên implementation hiện tại; với `upper`, kết quả vì thế được chuyển thành chữ hoa trước khi đặt trong dấu ngoặc. `Item.code()` giải quyết xung đột bằng cách gọi tường minh default method của từng interface cha.

## 6. Java 8 đã áp dụng những ý tưởng này trong thư viện chuẩn

Các API Java 8 minh họa rõ vai trò của default và static method:

- `Comparator.comparing(...)` là static method tạo comparator dựa trên một hàm trích xuất khóa.
- `Predicate.and(...)`, `Predicate.or(...)` và `Predicate.negate()` là default method kết hợp hoặc đảo điều kiện.
- `Function.andThen(...)` và `Function.compose(...)` là default method ghép các phép biến đổi.
- `Collection.removeIf(...)` là default method cho phép xóa phần tử thỏa predicate.
- `Map.computeIfAbsent(...)` là default method hỗ trợ tính toán và lưu giá trị khi khóa chưa có giá trị ánh xạ phù hợp.

Ví dụ sử dụng API chuẩn:

~~~java
import java.util.List;
import java.util.function.Predicate;

List<String> names = List.of("An", "Binh", "Chi");
Predicate<String> startsWithB = name -> name.startsWith("B");
Predicate<String> longEnough = name -> name.length() >= 3;

List<String> selected = names.stream()
        .filter(startsWithB.and(longEnough))
        .toList();
~~~

Với JDK 17, `selected` chứa `"Binh"`. Ví dụ này cho thấy functional interface giúp biểu diễn điều kiện bằng lambda, còn default method `and` cho phép kết hợp hai điều kiện mà không cần tạo lớp kết hợp riêng.

Các API này còn giúp phát triển thư viện theo hướng tương thích: có thể thêm thao tác tiện dụng vào interface và cung cấp cách triển khai mặc định. Tuy nhiên, việc thêm default method vẫn cần đánh giá tác động đến các lớp triển khai và các interface khác trong cây kế thừa.

## 7. Khả năng tương thích và giới hạn

Default method giúp giảm nhu cầu buộc mọi lớp triển khai phải bổ sung mã khi interface được mở rộng, nhưng không đảm bảo mọi thay đổi đều an toàn:

- **Thêm phương thức abstract:** các lớp triển khai có thể cần bổ sung phần thân; mã nguồn cũ có thể không còn biên dịch.
- **Thêm default method:** thường dễ tương thích hơn, nhưng có thể tạo xung đột với default từ interface khác hoặc làm thay đổi hành vi mà lớp trước đó vốn kế thừa.
- **Thêm static method:** không yêu cầu lớp triển khai thêm phần thân, nhưng cần cân nhắc tên và cách sử dụng để tránh gây nhầm lẫn với các API hiện hữu.
- **Thay đổi hợp đồng hành vi:** dù mã vẫn biên dịch, default method mới có thể làm thay đổi kết quả khi được gọi trên implementation cũ.

Default method không phải cơ chế để thay thế hoàn toàn abstract class. Nếu cần trạng thái instance, constructor, hoặc chia sẻ trạng thái giữa các phương thức, abstract class có thể phù hợp hơn. Interface phù hợp để mô tả khả năng mà nhiều lớp không liên quan có thể cùng triển khai; default method cung cấp hành vi chung khi hành vi đó thực sự có ý nghĩa với hợp đồng.

## 8. Lỗi thường gặp

- **Cho rằng functional interface chỉ được khai báo một phương thức tổng cộng:** không đúng. Interface có thể có nhiều default và static method, nhưng chỉ có một phương thức trừu tượng chức năng.
- **Quên `@Override` khi giải quyết default conflict:** lớp triển khai phải cung cấp phương thức instance tương thích để loại bỏ xung đột; dùng annotation giúp trình biên dịch kiểm tra chữ ký.
- **Gọi static method qua biến instance:** static method thuộc về tên interface, ví dụ `NumberTools.isEven(8)`.
- **Cho rằng static method của interface được kế thừa hoặc ghi đè:** static method của interface không có dispatch đa hình qua lớp triển khai.
- **Dùng `InterfaceName.super.method()` cho static method:** cú pháp này chỉ chọn default method instance.
- **Thêm default method mà không rà soát các interface khác:** lớp triển khai nhiều interface có thể gặp xung đột cùng chữ ký.
- **Cho rằng `@FunctionalInterface` là điều kiện bắt buộc để dùng lambda:** annotation chỉ xác nhận ý định và yêu cầu kiểm tra của compiler; điều quyết định là kiểu đích có thỏa quy tắc functional interface hay không.

## 9. Checklist khi thiết kế interface

1. Phương thức mới có thực sự là hành vi mặc định hợp lý cho mọi implementation không? Nếu không, hãy cân nhắc abstract method hoặc một API riêng.
2. Có interface nào khác mà lớp triển khai thường dùng cùng lúc định nghĩa default cùng chữ ký không?
3. Static method có thực sự thuộc về API của interface, chẳng hạn hàm factory hoặc helper liên quan, không?
4. Nếu interface được dùng làm kiểu đích cho lambda, nó có giữ đúng một phương thức trừu tượng chức năng không?
5. Có thể viết ví dụ kiểm thử cho lớp triển khai cũ và cho tình huống kế thừa nhiều interface để phát hiện thay đổi hành vi không?

Khi dùng đúng mục đích, ba khả năng của Java 8 bổ sung cho nhau: default method giúp mở rộng hợp đồng với hành vi chung, static method gom tiện ích vào đúng API, và functional interface cung cấp hình dạng kiểu cho lambda, method reference cùng các pipeline xử lý dữ liệu.