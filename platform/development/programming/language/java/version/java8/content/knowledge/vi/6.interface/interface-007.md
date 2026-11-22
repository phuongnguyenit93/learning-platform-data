# Static method và phạm vi gắn với interface trong Java

## 1. Mục tiêu và ý tưởng cốt lõi

Kể từ Java 8, một interface có thể khai báo phương thức **`static` có thân triển khai**, bên cạnh phương thức abstract và `default`. Static method thuộc về **chính interface khai báo nó**, không thuộc về từng đối tượng của lớp triển khai. Đây là cách tổ chức các tiện ích, factory method và hành vi hỗ trợ có liên quan trực tiếp đến hợp đồng của interface mà không phải tạo thêm lớp tiện ích riêng.

Ví dụ ngắn:

~~~java
interface TextRule {
    boolean test(String text); // Phương thức chức năng (SAM)

    static boolean hasText(String text) {
        return text != null && !text.isBlank();
    }
}
~~~

Trong một phương thức khác, cách gọi đúng là:

~~~java
boolean valid = TextRule.hasText("Java");
~~~

`TextRule.hasText` thuộc interface `TextRule`; một đối tượng đang triển khai `TextRule` **không tự nhận được** static method này như instance method. Đặc biệt, Java **không kế thừa các static method của interface** xuống subinterface hay lớp `implements` interface đó.

Ví dụ trên dùng `String.isBlank()` có từ Java 11, phù hợp với Java 17+. Chính cú pháp static method trong interface đã tồn tại từ Java 8 và vẫn được hỗ trợ hiện nay.

Bốn điểm cần nhớ:

1. **Khai báo:** `static ReturnType methodName(...)` kèm thân trong interface.
2. **Phạm vi gọi:** thường dùng `TenInterface.methodName(...)`.
3. **Không kế thừa:** `extends` và `implements` không làm static interface method trở thành method được kế thừa của kiểu con.
4. **Không override:** static interface method không tham gia dynamic dispatch của instance method; một method cùng tên ở kiểu khác là khai báo riêng.

## 2. Cú pháp và phạm vi truy cập

Trong một interface, khai báo:

~~~java
interface TemperatureRules {
    static boolean isFreezing(int celsius) {
        return celsius <= 0;
    }

    static int toFahrenheit(int celsius) {
        return celsius * 9 / 5 + 32;
    }
}
~~~

Các phương thức trên là **public static** dù không viết từ khóa `public`. Java cho phép viết tường minh:

~~~java
interface TemperatureRules {
    public static boolean isFreezing(int celsius) {
        return celsius <= 0;
    }
}
~~~

Hai cách có cùng mức truy cập. Các đoạn ví dụ trong phần này là **mảnh mã minh họa**, không phải hai khai báo được phép đặt đồng thời với cùng tên `TemperatureRules` trong một tệp; chọn một biến thể khi thử.

### Phạm vi truy cập được hỗ trợ

| Khai báo | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `static int code() { ... }` | Có | Trong interface, mặc định là `public static` |
| `public static int code() { ... }` | Có | Viết tường minh modifier public |
| `private static int code() { ... }` | Có, Java 9+ | Helper nội bộ của interface |
| `protected static int code() { ... }` | Không | Interface method không dùng `protected` |
| `abstract static int code();` | Không | `static` phải có thân, không đồng thời là `abstract` |
| `static int code();` | Không | Thiếu thân cho static method |
| `final static int code() { ... }` | Không | Không dùng `final` như một modifier hợp lệ của interface method |

**Lưu ý phiên bản:** `private static` method trong interface là tính năng từ Java 9, tiếp tục dùng tốt trong Java 17+. Nếu dự án có yêu cầu biên dịch nguyên văn trên Java 8, chỉ có public static method ở phạm vi bài này; không dùng private static helper ngay trong interface.

### Interface là chủ sở hữu của static method

Với một public static method:

~~~java
boolean cold = TemperatureRules.isFreezing(-3); // true
~~~

Không cần tạo `new TemperatureRules()` (interface cũng không thể được khởi tạo trực tiếp), và không cần bất kỳ lớp nào `implements TemperatureRules` để gọi phương thức. Public static method có thể được các lớp khác gọi thông qua tên interface, miễn mã được phép truy cập kiểu/interface đó.

Khi viết code bên trong **chính interface khai báo method**, có thể gọi nó bằng tên đơn giản hoặc bằng tên interface nếu không gây nhầm lẫn:

~~~java
interface TemperatureRules {
    static boolean isFreezing(int value) {
        return value <= 0;
    }

    static String describe(int value) {
        return isFreezing(value) ? "cold" : "warm";
    }
}
~~~

Tại đây `isFreezing(value)` là lời gọi static method ở cùng interface. Từ bên ngoài, dùng `TemperatureRules.describe(...)`.

## 3. Vì sao static method không phải instance method?

Static method không gắn với một đối tượng cụ thể. Nó không có receiver instance kiểu `this`, không tham gia override theo đối tượng và không trực tiếp truy cập trạng thái instance như một default method có thể làm.

Trong class, static method cũng không có `this`. Với interface, khác biệt còn rõ hơn vì interface **không khai báo field instance**; các field được khai báo trong interface mặc nhiên là `public static final`.

~~~java
interface Thresholds {
    int MIN = 0; // Ngầm định public static final

    static boolean valid(int value) {
        return value >= MIN;
    }
}
~~~

Việc đọc `MIN` hợp lệ do nó là static field. Nhưng static method không có một object đại diện cho “interface instance hiện tại” để gọi `this.someMethod()`.

Ví dụ **cố ý không biên dịch**:

~~~java
interface InvalidRule {
    boolean accepts(String value);

    static boolean invalid(String value) {
        return this.accepts(value); // Lỗi: không có this trong static context
    }
}
~~~

Để dùng instance behavior, hãy truyền một đối tượng theo tham số:

~~~java
interface TextRule {
    boolean test(String text);

    static boolean evaluate(TextRule rule, String text) {
        java.util.Objects.requireNonNull(rule, "rule");
        return rule.test(text);
    }
}
~~~

`evaluate` vẫn là static method: nó không ngầm có `this`, mà nhận `rule` tường minh. Đoạn này là mảnh mã minh họa; các ví dụ đầy đủ ở phần sau sẽ chỉ rõ tệp và cách chạy.

## 4. Static method trong interface không được kế thừa

Đây là khác biệt quan trọng nhất cần hiểu về “phạm vi gắn với interface”.

Giả sử:

~~~java
interface ParentTools {
    static String help() {
        return "parent";
    }
}

interface ChildTools extends ParentTools {
}

class Worker implements ChildTools {
}
~~~

Lời gọi hợp lệ:

~~~java
System.out.println(ParentTools.help()); // parent
~~~

Các lời gọi **cố ý không biên dịch**:

~~~java
ChildTools.help();      // Lỗi: static method không kế thừa qua extends
Worker.help();          // Lỗi: static method không kế thừa qua implements
new Worker().help();    // Lỗi: không có instance method help được kế thừa
~~~

Mặc dù `ChildTools` kế thừa các nghĩa vụ instance phù hợp của `ParentTools`, nó **không** kế thừa static method `help`. `Worker` cũng không được tự động sở hữu `help`.

### “Không kế thừa” khác với “không thể khai báo trùng tên”

Subinterface hoặc lớp triển khai có thể khai báo một static method riêng có cùng tên và chữ ký tương thích; việc này không biến method đó thành bản override của `ParentTools.help`. Mỗi method vẫn được chọn theo **tên kiểu dùng tại lời gọi**.

~~~java
interface ParentTools {
    static String label() {
        return "parent";
    }
}

interface ChildTools extends ParentTools {
    static String label() {
        return "child";
    }
}

class Worker implements ChildTools {
    static String label() {
        return "worker";
    }
}
~~~

Các định nghĩa trên là mảnh mã minh họa cho một ví dụ cùng tồn tại. Nếu gọi `ParentTools.label()`, `ChildTools.label()`, `Worker.label()`, ta lần lượt nhận `parent`, `child`, `worker`.

Không gọi đó là **override** hoặc **dynamic dispatch**. Method được chọn tĩnh bằng kiểu xuất hiện trước dấu chấm. `@Override` không áp dụng cho static interface method.

## 5. Ví dụ Java hoàn chỉnh 1: chứng minh phạm vi gắn với interface

Tạo tệp **InterfaceStaticScopeDemo.java**:

~~~java
public class InterfaceStaticScopeDemo {

    interface ParentTools {
        static String label() {
            return "parent";
        }

        static String parentOnly() {
            return "only-parent";
        }
    }

    interface ChildTools extends ParentTools {
        static String label() {
            return "child";
        }
    }

    static final class Worker implements ChildTools {
        static String label() {
            return "worker";
        }
    }

    public static void main(String[] args) {
        System.out.println(ParentTools.label());
        System.out.println(ChildTools.label());
        System.out.println(Worker.label());
        System.out.println(ParentTools.parentOnly());

        Worker worker = new Worker();
        System.out.println(worker instanceof ChildTools);
    }
}
~~~

Biên dịch và chạy với JDK 17+ (toàn bộ cấu trúc của chương trình này tương thích Java 8):

~~~bash
javac InterfaceStaticScopeDemo.java
java InterfaceStaticScopeDemo
~~~

**Stdout chính xác:**

~~~text
parent
child
worker
only-parent
true
~~~

Vì sao kết quả như vậy?

1. `ParentTools.label()` gọi phương thức được khai báo tại `ParentTools`; không xét đối tượng `Worker`.
2. `ChildTools.label()` gọi phương thức riêng tại `ChildTools`, không phải một override của `ParentTools.label()`.
3. `Worker.label()` gọi phương thức riêng được khai báo trong lớp `Worker`.
4. `ParentTools.parentOnly()` hoạt động. Nếu thay bằng `ChildTools.parentOnly()` hoặc `Worker.parentOnly()`, lỗi biên dịch xuất hiện vì method đó không được kế thừa.
5. `worker instanceof ChildTools` là `true` do `Worker` triển khai interface. **Quan hệ kiểu instance này không khiến static method của interface trở thành instance method.**

### Đặt cạnh default method để thấy khác biệt

Default method thuộc hợp đồng instance và có thể được thừa hưởng, override theo quy tắc Java:

~~~java
interface HasName {
    default String name() {
        return "default";
    }

    static String category() {
        return "tools";
    }
}

class NamedItem implements HasName {
}
~~~

Mảnh mã minh họa:

~~~java
NamedItem item = new NamedItem();

System.out.println(item.name());    // default
System.out.println(HasName.category()); // tools
~~~

`item.name()` hoạt động vì `name` là instance default method. `item.category()` và `NamedItem.category()` **không hợp lệ** nếu lớp không tự khai báo phương thức riêng cùng tên. Dùng `HasName.category()`.

## 6. Static method không ảnh hưởng số lượng SAM

Một **functional interface** phải có một hợp đồng phương thức abstract phù hợp. Thêm các phương thức static có thân **không tạo abstract method mới**, nên interface vẫn có thể nhận lambda hoặc method reference.

~~~java
@FunctionalInterface
interface NameRule {
    boolean accepts(String name); // SAM

    static NameRule longerThan(int minimum) {
        return name -> name != null && name.length() > minimum;
    }
}
~~~

`NameRule.longerThan(3)` trả về một đối tượng `NameRule` (được cài đặt bởi lambda); static factory method **không phải** phương thức chức năng thứ hai.

Mảnh mã minh họa:

~~~java
NameRule rule = NameRule.longerThan(3);

System.out.println(rule.accepts("Java")); // true
System.out.println(rule.accepts("Go"));   // false
~~~

Đây là một hướng thiết kế API rất hữu ích: interface **cung cấp hợp đồng instance** và **các factory/helper static liên quan đến chính hợp đồng đó**. Không phải vì static method tạo một lớp đối tượng mới có thể override; nó chỉ đóng vai trò tạo hoặc hỗ trợ hành vi.

### Phương thức static có thể trả về chính interface

Ví dụ:

~~~java
@FunctionalInterface
interface IntegerRule {
    boolean test(int value);

    static IntegerRule atLeast(int threshold) {
        return value -> value >= threshold;
    }
}
~~~

Caller có thể viết `IntegerRule.atLeast(10)` để nhận predicate tùy biến. Không phải tạo class riêng cho mỗi ngưỡng. Nếu API cần hệ sinh thái `IntPredicate` chuẩn, có thể chọn trực tiếp `java.util.function.IntPredicate`; tạo interface riêng chỉ khi thật sự có ý nghĩa về tên, hợp đồng hay tính năng.

## 7. Ví dụ Java hoàn chỉnh 2: static factory, SAM và default method

Tạo tệp **InterfaceStaticFactoryDemo.java**:

~~~java
import java.util.Objects;

public class InterfaceStaticFactoryDemo {

    @FunctionalInterface
    interface TextRule {
        boolean accepts(String value); // SAM duy nhất

        static boolean hasText(String value) {
            return value != null && !value.isBlank();
        }

        static TextRule minLength(int minimum) {
            if (minimum < 0) {
                throw new IllegalArgumentException(
                        "minimum must be non-negative"
                );
            }
            return value -> hasText(value)
                    && value.length() >= minimum;
        }

        default TextRule and(TextRule other) {
            Objects.requireNonNull(other, "other");
            return value -> accepts(value) && other.accepts(value);
        }
    }

    public static void main(String[] args) {
        TextRule minFour = TextRule.minLength(4);
        TextRule startsWithJ =
                value -> value != null && value.startsWith("J");

        TextRule combined = minFour.and(startsWithJ);

        System.out.println(TextRule.hasText("   "));
        System.out.println(TextRule.hasText("Java"));
        System.out.println(combined.accepts("Java"));
        System.out.println(combined.accepts("John"));
        System.out.println(combined.accepts("Jo"));
        System.out.println(combined.accepts(null));
        System.out.println(TextRule.minLength(0).accepts("x"));
    }
}
~~~

Biên dịch/chạy bằng JDK 17+; vì dùng `String.isBlank` (Java 11+), không biên dịch nguyên văn bằng Java 8:

~~~bash
javac InterfaceStaticFactoryDemo.java
java InterfaceStaticFactoryDemo
~~~

**Stdout chính xác:**

~~~text
false
true
true
true
false
false
true
~~~

Giải thích chi tiết:

1. `TextRule.hasText` là static method của interface: `null` và chuỗi toàn khoảng trắng không có nội dung theo `String.isBlank()`.
2. `TextRule.minLength(4)` là factory static trả một `TextRule`. Giá trị `minimum` được lambda capture; không thay đổi sau khi tạo nên thỏa `effectively final`.
3. `startsWithJ` là lambda tương thích với SAM `boolean accepts(String)`.
4. `minFour.and(startsWithJ)` gọi **default instance method** `and` trên đối tượng `minFour`, tạo quy tắc hợp cả hai điều kiện.
5. `combined.accepts("Java")` và `combined.accepts("John")` đều đúng vì dài ít nhất 4 và bắt đầu bằng chữ `J`.
6. `combined.accepts("Jo")` sai vì chỉ có 2 ký tự; `combined.accepts(null)` sai do kiểm tra `hasText` trả false trước, có short-circuit.
7. `minLength(0).accepts("x")` đúng vì `"x"` không blank và có độ dài ít nhất 0. Chính sách này không chấp nhận chuỗi rỗng khi minimum=0; đây là quyết định nghiệp vụ của factory, không phải hành vi mặc định của Java.

**Thiết kế liên quan:** `minimum < 0` được kiểm tra ngay khi gọi static factory. Điều này giúp API từ chối tham số không hợp lệ tại thời điểm cấu hình rule thay vì đợi đến lần gọi `accepts` sau này.

## 8. Private static helper trong interface từ Java 9

Java 9 cho phép interface chứa **private method**, gồm cả `private static`. Đây là cách chia sẻ logic nội bộ giữa các static method mà không đưa helper ra public API.

~~~java
interface SlugRules {
    static boolean acceptable(String value) {
        return value != null
                && !value.isEmpty()
                && hasAllowedCharacters(value);
    }

    private static boolean hasAllowedCharacters(String value) {
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            boolean allowed =
                    (c >= 'a' && c <= 'z')
                    || (c >= '0' && c <= '9')
                    || c == '_';
            if (!allowed) {
                return false;
            }
        }
        return true;
    }
}
~~~

Ở đây `acceptable` là public static method; `hasAllowedCharacters` là private static helper. Caller bên ngoài chỉ dùng `SlugRules.acceptable(text)`, **không** gọi được `SlugRules.hasAllowedCharacters(text)`.

### Vì sao không chỉ tạo thêm public static method?

Khi helper chỉ tồn tại để phục vụ triển khai, biến nó thành `public` sẽ mở rộng API không cần thiết. Một khi nhiều thành phần bên ngoài sử dụng public method, việc đổi tên/chữ ký có thể trở thành thay đổi gây vỡ tương thích. `private static` giữ phần triển khai ở đúng phạm vi, hỗ trợ refactor.

### Đối chiếu `private` và `private static`

- `private static`: không cần instance; dùng được bởi các method phù hợp trong cùng interface, đặc biệt để dùng chung cho nhiều static method.
- `private` **instance method** (Java 9+) có receiver instance; hỗ trợ chia sẻ logic giữa các default method hoặc những method instance khác ở trong interface.
- Cả hai không được kế thừa như public/default instance method để lớp triển khai override.

Trong JDK 17+, đây là cách tổ chức code hoàn toàn bình thường. Nếu dự án vẫn chạy Java 8 và không thể nâng phiên bản, cần chuyển helper riêng sang cách triển khai khác phù hợp mục tiêu tương thích, thay vì dùng cú pháp `private static` không được JDK 8 hiểu.

## 9. Ví dụ Java hoàn chỉnh 3: giới hạn public/private của static interface method

Tạo tệp **InterfacePrivateStaticDemo.java**:

~~~java
public class InterfacePrivateStaticDemo {

    interface SlugRules {
        static boolean acceptable(String value) {
            return value != null
                    && !value.isEmpty()
                    && hasAllowedCharacters(value);
        }

        private static boolean hasAllowedCharacters(String value) {
            for (int i = 0; i < value.length(); i++) {
                char c = value.charAt(i);
                boolean allowed =
                        (c >= 'a' && c <= 'z')
                        || (c >= '0' && c <= '9')
                        || c == '_';
                if (!allowed) {
                    return false;
                }
            }
            return true;
        }
    }

    public static void main(String[] args) {
        System.out.println(SlugRules.acceptable("java_17"));
        System.out.println(SlugRules.acceptable("Java"));
        System.out.println(SlugRules.acceptable("java-17"));
        System.out.println(SlugRules.acceptable(""));
        System.out.println(SlugRules.acceptable(null));
    }
}
~~~

Biên dịch/chạy bằng JDK 17+ (`private static` trong interface cần Java 9+):

~~~bash
javac InterfacePrivateStaticDemo.java
java InterfacePrivateStaticDemo
~~~

**Stdout chính xác:**

~~~text
true
false
false
false
false
~~~

- `java_17` chỉ chứa chữ cái thường ASCII, chữ số và gạch dưới nên hợp lệ.
- `Java` có chữ `J` hoa; ví dụ này cố ý **không** cho phép chữ hoa.
- `java-17` có dấu gạch ngang `-` bị loại.
- Chuỗi rỗng và `null` bị loại trước khi vào helper.
- Helper được gọi bên trong interface nhưng không phải public API.

**Phân biệt yêu cầu nghiệp vụ:** đây là quy tắc slug minh họa, không phải một validator chung cho mọi URL, identifier hoặc Unicode. Khi áp dụng thực tế, cần xác định chính xác bộ ký tự và cách chuẩn hóa mong muốn.

## 10. Static method có generic riêng nhưng không dùng kiểu tham số instance của interface

Vì static method không gắn với một instance thuộc `Box<T>`, nó **không thể tham chiếu trực tiếp `T` là type parameter khai báo ở interface**:

~~~java
// Cố ý KHÔNG biên dịch:
interface Box<T> {
    static T echo(T value) {
        return value;
    }
}
~~~

`T` thuộc về khai báo generic của interface và chỉ có ý nghĩa theo một lần dùng kiểu `Box<T>`; static method không có instance/type argument `T` tương ứng.

Giải pháp là khai báo **type parameter của chính static method**:

~~~java
interface Box<T> {
    T get();

    static <U> U echo(U value) {
        return value;
    }
}
~~~

Khi gọi:

~~~java
String s = Box.echo("Java");
Integer n = Box.echo(42);
~~~

Trình biên dịch suy luận `U` từ đối số và kiểu đích, nhưng static method vẫn gắn với **`Box`**, không gắn với một `Box<String>` hay `Box<Integer>` cụ thể. Đừng viết `Box<String>.echo("Java")` như thể static call được xác định bằng một đối tượng generic; hãy dùng `Box.echo(...)`.

### Generics với static factory trả functional interface

~~~java
interface Mapper<I, O> {
    O apply(I input);

    static <T> Mapper<T, T> identity() {
        return value -> value;
    }
}
~~~

Mảnh mã minh họa:

~~~java
Mapper<String, String> same = Mapper.identity();
System.out.println(same.apply("Java")); // Java
~~~

`identity` là generic static factory, còn `Mapper.apply` là instance abstract method. Hai thứ không nhầm lẫn nhau. Các interface chuẩn `Function`, `Predicate` và `Comparator` cũng có các static factory/helper phù hợp mục tiêu sử dụng của chúng.

## 11. Static method reference và method resolution

Có thể truyền một static method của interface làm **method reference**:

~~~java
interface Validators {
    static boolean nonBlank(String value) {
        return value != null && !value.isBlank();
    }
}
~~~

Mảnh mã trong phương thức:

~~~java
java.util.function.Predicate<String> valid =
        Validators::nonBlank;

System.out.println(valid.test("Java")); // true
System.out.println(valid.test("  "));   // false
~~~

`Validators::nonBlank` không cần receiver instance. `Predicate<String>` cung cấp target type có descriptor `(String) -> boolean`; Java so khớp nó với static method `boolean nonBlank(String)`.

Khác với `someObject::instanceMethod`, không có biểu thức đối tượng ở bên trái `::` cần được đánh giá và kiểm tra null lúc tạo. Phần thân method `nonBlank` chỉ chạy khi predicate được gọi.

### Quá tải phương thức

Một interface có thể overload static method nếu chữ ký hợp lệ:

~~~java
interface Formatters {
    static String format(int value) {
        return "number:" + value;
    }

    static String format(String value) {
        return "text:" + value;
    }
}
~~~

Ở nơi dùng:

~~~java
java.util.function.IntFunction<String> number =
        Formatters::format;

java.util.function.Function<String, String> text =
        Formatters::format;
~~~

Hai target types giúp chọn overload thích hợp. Cần tránh các overload gây mơ hồ với lambda/method reference tại nơi gọi; thông báo biên dịch lúc này thường liên quan khả năng chọn kiểu, không phải “thiếu kế thừa”.

## 12. Đối chiếu static interface method với các loại method khác

| Đặc tính | Abstract | Default | Public static | Private static |
| --- | --- | --- | --- | --- |
| Có thân ngay trong interface | Không | Có | Có | Có |
| Gắn với instance | Có | Có | Không | Không |
| Lớp triển khai có thể override | Có, để triển khai | Có, theo quy tắc Java | Không | Không |
| Có thể được kế thừa qua `extends` | Có, tùy xung đột | Có, tùy xung đột | Không | Không |
| Cách gọi thông thường | `object.method()` | `object.method()` | `Interface.method()` | Chỉ từ code được phép bên trong interface |
| Được tính là SAM abstract contract | Có thể | Không | Không | Không |
| Phiên bản | Từ trước Java 8 | Java 8+ | Java 8+ | Java 9+ |

**Lưu ý:** bảng tóm tắt tình huống thông thường. Các quy tắc kế thừa instance/default method có thể liên quan xung đột giữa nhiều interface, method của class cha, và quy tắc override phức tạp. Điều đó không đổi quy tắc riêng: **static method của interface không được thừa hưởng như static method của class**.

### Static method của class khác thế nào?

Trong **class**, static method có thể được kế thừa và bị *hide* (che tên) bởi static method ở subclass theo các quy tắc của Java. Với **interface**, static method **không được kế thừa** bởi subinterface hoặc lớp triển khai; do đó không dùng các lập luận về hiding của class để giải thích các method riêng `ParentTools.label`, `ChildTools.label`, `Worker.label`.

Tránh hướng dẫn người khác gọi static method qua object chỉ vì một số static **class** method có thể được gọi bằng cú pháp instance (một thói quen kém rõ ràng). Với static **interface** method, hãy gọi bằng tên interface khai báo nó.

## 13. Khi nào nên đặt static method vào interface?

Dùng static method trong interface khi hành vi mang ý nghĩa **gắn tự nhiên với hợp đồng interface**:

1. **Factory tạo đối tượng triển khai:** `Rule.of(...)`, `Rule.alwaysTrue()`, hoặc một công thức tạo rule trả về interface.
2. **Định nghĩa thuật toán/tiện ích chung cho hợp đồng:** xác định hoặc chuẩn hóa dữ liệu chung mà các implementation sẽ sử dụng.
3. **Tổ chức API khám phá được:** người dùng viết `InterfaceName.methodName` và thấy tập method liên quan.
4. **Static generic factory:** tạo hành vi có kiểu mà không bắt người dùng tự viết lambda lặp lại.
5. **Helper nội bộ (Java 9+):** `private static` hỗ trợ các public static hoặc logic khác trong interface mà không làm phình public API.

Ví dụ trong thư viện chuẩn Java:

- `java.util.Comparator.comparing(...)` là static factory tạo `Comparator` từ một key extractor.
- `java.util.function.Predicate.isEqual(...)` là static factory tạo `Predicate` kiểm tra bình đẳng.
- `java.util.function.Function.identity()` là static factory tạo hàm đồng nhất.
- `java.util.function.Predicate.not(...)` là static factory phủ định được thêm từ Java 11.

Chúng thể hiện mô hình hiện đại: **interface mô tả khả năng**, còn static method cung cấp cách tạo/kết hợp một hành vi thỏa khả năng đó.

### Khi nào không nên?

- Chỉ vì một method “có liên quan chung chung” đến interface không có nghĩa phải chuyển tất cả logic nghiệp vụ vào đó.
- Nếu method phụ thuộc trạng thái của mỗi instance và cần polymorphism, hãy dùng abstract/default instance method.
- Nếu logic cần dependency injection, cấu hình môi trường, database, HTTP client hoặc resource lifecycle phức tạp, tách sang service/class riêng sẽ dễ kiểm thử hơn.
- Nếu private helper ngày càng nhiều và interface trở thành một triển khai đồ sộ, cân nhắc tách thành class hỗ trợ hoặc module riêng theo trách nhiệm.
- Không giấu mutable global state trong static field của interface để “chia sẻ” giữa implementation. Interface field phải là `public static final`; `final` cố định reference chứ không tự biến trạng thái object thành bất biến/an toàn đồng thời.

### Tránh tạo API gây bất ngờ

Public static method xuất hiện như một phần API của interface. Tên như `from`, `of`, `empty`, `alwaysTrue`, `isValid` có thể rất rõ nếu hợp đồng và trường hợp biên được mô tả. Cần ghi lại chính sách `null`, tính mutable, ngoại lệ, và liệu kết quả là object mới hay object được dùng lại. Static method không tự động làm API trở nên thread-safe hoặc không tác dụng phụ.

## 14. Lỗi thường gặp và cách khắc phục

| Lỗi/quan niệm | Vấn đề | Cách xử lý |
| --- | --- | --- |
| `ChildInterface.utility()` gọi static method từ interface cha | Không kế thừa static interface method | Dùng `ParentInterface.utility()` |
| `Implementation.utility()` gọi static method của interface | `implements` không kế thừa method đó | Dùng `InterfaceName.utility()` |
| `object.utility()` với static method chỉ có trong interface | Không phải instance method được kế thừa | Dùng `InterfaceName.utility()` |
| Coi static method như override/hành vi đa hình | Static method không nhận dispatch theo instance | Dùng abstract/default instance method khi cần đa hình |
| `@Override` trên static method | Không có quan hệ override ở đây | Bỏ annotation; thiết kế lại mục tiêu |
| Dùng `this` trong static method | Static context không có instance receiver | Truyền object tường minh hoặc đổi sang instance method |
| Dùng `static T` với `T` của `interface Foo<T>` | Static context không dùng type parameter của interface | Khai báo `static <U> ...` cho method |
| Thêm abstract static method | `abstract` và `static` không tương thích | Chọn abstract instance method hoặc static có thân |
| Dùng `private static` rồi biên dịch dưới Java 8 | Java 8 không hỗ trợ private interface method | Cần Java 9+ hoặc thay tổ chức helper |
| Public helper chứa chi tiết nội bộ | Khó thay đổi API về sau | Dùng private static Java 9+ |
| Giả định static method làm functional interface mất tính functional | Static không thêm abstract contract | Kiểm tra một SAM, dùng `@FunctionalInterface` |
| Suy rằng static field `final` luôn bất biến sâu | `final` không đóng băng object mutable | Ưu tiên immutable data, tránh mutable shared state |

## 15. Bài tập tự luyện

**Bài 1 — Đọc đúng scope.** Cho:

~~~java
interface A {
    static String name() { return "A"; }
}
interface B extends A {
}
class C implements B {
}
~~~

Trong một phương thức khác, hãy xác định biểu thức nào hợp lệ: `A.name()`, `B.name()`, `C.name()`, `new C().name()`. Đáp án: chỉ `A.name()`; method static của interface không được kế thừa.

**Bài 2 — Static hay default?** Thiết kế interface `DiscountRule` có phương thức abstract `int apply(int amount)`, một static factory `percentage(int rate)` trả `DiscountRule`, và một default method `andThen(DiscountRule other)`. Phân biệt cách gọi `DiscountRule.percentage(10)` với `rule.andThen(other)`. Xác định cách xử lý biên như `rate < 0`, `rate > 100`, overflow khi tính toán.

**Bài 3 — Refactor helper.** Trong JDK 17, hai static method public `isCode` và `isTag` cùng sử dụng logic kiểm tra chữ cái/chữ số. Hãy tách một private static method trong interface để dùng chung. Giải thích vì sao nên giữ helper private nếu client không cần sử dụng.

**Bài 4 — Static generic.** Đoán vì sao `interface Container<T> { static T identity(T x) { return x; } }` không hợp lệ. Viết lại bằng method type parameter `<U>`, rồi gọi nó với `String` và `Integer`.

**Bài 5 — SAM có thay đổi không?** Cho:

~~~java
@FunctionalInterface
interface Check {
    boolean test(String s);

    static Check startsWith(String prefix) {
        return s -> s != null && s.startsWith(prefix);
    }

    default Check negate() {
        return s -> !test(s);
    }
}
~~~

Giải thích vì sao đây vẫn là functional interface, và xác định thời điểm `startsWith(prefix)` kiểm tra điều kiện (tạo rule hay gọi `test`). Nếu `prefix` null, `String.startsWith(null)` có thể ném NPE khi test một chuỗi không null; hãy thiết kế kiểm tra `Objects.requireNonNull(prefix)` ở factory nếu muốn từ chối sớm.

**Bài 6 — Thiết kế API.** Một interface `FileValidator` cần kiểm tra một `Path` theo quy tắc của từng implementation, đồng thời có factory tạo các validator chuẩn. Hãy quyết định method nào cần abstract, method nào nên static factory, helper nào private static, và các kiểm tra `null`, I/O error được xử lý ở đâu. Nhớ rằng `Predicate.test` chuẩn không khai báo checked exception.

## 16. Checklist trước khi đưa static method vào interface

- Method có thật sự là **hành vi chung của hợp đồng interface** hay đang lẫn trách nhiệm của service?
- Nó có cần **receiver instance/polymorphism** không? Nếu có, static không phù hợp.
- Call site có được viết là **`InterfaceName.methodName(...)`** không?
- Có ai đang kỳ vọng **subinterface/class implementing** được kế thừa method? Nếu có, cần sửa kỳ vọng hoặc thiết kế.
- Nếu interface generic, method static có khai báo **type parameter riêng** khi cần không?
- Helper có thực sự cần public? JDK hiện tại có hỗ trợ **`private static`** không?
- Tham số `null`, giới hạn số, giá trị rỗng, exception và thread safety đã được nêu rõ chưa?
- Method static có làm tăng abstract contract/SAM không? Không; hãy kiểm tra riêng abstract method.
- Code đã có test chứng minh lời gọi đúng theo interface khai báo, thay vì ngẫu nhiên dựa vào hành vi của class static method chưa?

## 17. Ghi nhớ

- **Static method của interface** được khai báo bằng `static` với thân triển khai; public static có từ Java 8 và private static có từ Java 9.
- **Scope** của method thuộc **interface khai báo**, nên gọi bằng `TenInterface.staticMethod(...)`. Không gọi qua đối tượng thực thi và không giả định subinterface hay class `implements` kế thừa được method.
- Static interface method **không override, không dynamic dispatch**; những method cùng tên ở interface con hoặc lớp khác là những khai báo độc lập.
- Static method không có `this`, không truy cập trực tiếp instance state, và không làm tăng số lượng abstract method của functional interface.
- Static factory, generic method và private static helper là những cách dùng hiện đại và có ích, nhưng vẫn phải thiết kế API, điều kiện biên và trách nhiệm rõ ràng.
