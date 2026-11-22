# Thiết kế lớp tiện ích với hàm khởi tạo `private` trong Java

## 1. Lớp tiện ích (*utility class*) là gì?

**Utility class** là một lớp dùng để **gom những thao tác liên quan về mặt chức năng**, thường được cung cấp dưới dạng **`static methods`** và các hằng số cần thiết, **không đại diện cho một thực thể có trạng thái instance riêng**.

Các API quen thuộc của Java cho thấy phong cách này:

- `Math.max(3, 7)`: tính giá trị lớn hơn trong hai số.
- `Arrays.toString(values)`, `Arrays.sort(values)`: thao tác hỗ trợ cho mảng.
- `Objects.requireNonNull(value)`: kiểm tra giá trị tham chiếu.
- `Collections.unmodifiableList(list)`: cung cấp view không cho phép sửa qua view theo contract.
- `Integer.parseInt("42")`: chuyển chuỗi thành `int`. Đây là **static method trên một lớp cũng có những mục đích khác**, không phải ví dụ cho rằng mọi lớp có static method đều là utility-only class.

Khi tự xây dựng utility class, chẳng hạn `TextUtils` hoặc `NumberUtils`, mục đích thông thường là:

1. Gọi tính năng qua **tên lớp**: `TextUtils.normalize(input)`.
2. Không cần tạo đối tượng kiểu `TextUtils`.
3. Không có instance fields cần giữ qua các lần gọi.
4. Không gợi ý sai rằng từng đối tượng utility có danh tính hay vòng đời riêng.
5. Chỉ phơi bày **API dùng chung** thực sự có ý nghĩa.

Vì không cần object của utility class, một quyết định thiết kế quan trọng là **khóa đường tạo instance không cần thiết bằng constructor `private`**.

> **Mẫu thường gặp:** `public final class XUtils { private XUtils() { ... } public static ... }`. Nhưng `public`, `final` và `private` giải quyết **ba vấn đề khác nhau**; cần hiểu rõ từng modifier thay vì sao chép khuôn mẫu máy móc.

## 2. Vì sao chỉ viết static methods vẫn chưa đủ?

Nếu viết:

```java
public class NumberUtils {
    public static int square(int value) {
        return value * value;
    }
}
```

Đây là một lớp có static method. **Nhưng** vì lớp không khai báo constructor nào, Java tự cung cấp **default constructor** phù hợp. Với một `public class` như trên, constructor mặc định là `public`; caller có thể viết:

```java
NumberUtils utils = new NumberUtils();
System.out.println(utils.square(4)); // Có thể biên dịch nhưng diễn đạt sai ý định.
```

Đoạn gọi này là **mảnh mã minh họa trong method**. Nó tạo một object `NumberUtils` không mang state hữu ích, rồi gọi một static method qua biến instance. Tính toán vẫn trả 16, nhưng cách viết gây hiểu nhầm rằng method phụ thuộc vào object `utils`.

Không có lý do nghiệp vụ để tồn tại nhiều instances kiểu:

```java
NumberUtils a = new NumberUtils();
NumberUtils b = new NumberUtils();
```

Hai `NumberUtils` objects khác nhau về identity, nhưng không cung cấp thông tin riêng nào cần thiết cho `square`. Tạo chúng là chi phí và gây nhiễu API, dù chi phí nhỏ đến đâu.

**Sửa:** khai báo constructor không thể truy cập từ code bên ngoài lớp:

```java
public final class NumberUtils {
    private NumberUtils() {
    }

    public static int square(int value) {
        return value * value;
    }
}
```

Khi đó client sử dụng:

```java
int result = NumberUtils.square(4);
```

Không cần tạo `NumberUtils` instance và không thể viết `new NumberUtils()` từ một lớp unrelated theo quy tắc truy cập nguồn Java.

## 3. Ba modifier trong mẫu utility class

| Modifier | Đặt ở đâu? | Mục đích | Không có nghĩa |
| --- | --- | --- | --- |
| `public` | Top-level utility class khi dùng ngoài package | Cho client đặt tên lớp | Không làm tất cả fields/methods tự public |
| `final` | Utility class | Không cho class bị subclass | Không làm constructor tự private |
| `private` | Constructor | Ngăn caller bên ngoài phạm vi được phép trực tiếp gọi constructor | Không làm static methods ngừng hoạt động |
| `static` | Utility methods và các shared members thích hợp | Gọi qua tên lớp, không cần receiver | Không có nghĩa chỉ chạy một lần |
| `private static` | Helper methods/fields nội bộ | Không đưa implementation detail vào API | Không tự bảo đảm thread safety |
| `public static final` | Hằng số public có contract ổn định | Đặt hằng ở cấp lớp, không gán lại field | Không tự đóng băng object mutable mà field tham chiếu |

**Điểm then chốt:** Constructor `private` và modifier `final` **không thay thế nhau**:

- Chỉ `private` constructor: chặn những lời gọi `new Utility()` thông thường từ lớp unrelated; cần cân nhắc những quy tắc truy cập từ enclosing/nest.
- Chỉ `final` class: chặn inheritance nhưng **không chặn việc tạo instance** nếu constructor accessible.
- Dùng cả hai thường diễn đạt rõ ý định “không tạo instance, không subclass”.

Dùng `final` cho utility class là một lựa chọn thường hợp lý, nhưng **không bắt buộc để static methods hoạt động**. Nếu một class được cố ý thiết kế cho subclass/extension, có thể nó không nên được phân loại là utility-only class.

## 4. Ví dụ hoàn chỉnh đầu tiên: utility class không thể tạo instance từ client

Tạo tệp **`UtilityClassDemo.java`**:

```java
final class TextUtils {
    private TextUtils() {
        throw new AssertionError("No TextUtils instances");
    }

    static String normalize(String text) {
        if (text == null) {
            throw new IllegalArgumentException("text is required");
        }
        return text.trim().toLowerCase();
    }

    static boolean sameNormalized(String left, String right) {
        return normalize(left).equals(normalize(right));
    }
}

public class UtilityClassDemo {
    public static void main(String[] args) {
        System.out.println(TextUtils.normalize("  JAVA  "));
        System.out.println(TextUtils.sameNormalized(" Java ", "java"));

        // TextUtils helper = new TextUtils();
        // Nếu bỏ comment: lỗi vì constructor private.
    }
}
```

Biên dịch và chạy với **Java 17+**:

```bash
javac UtilityClassDemo.java
java UtilityClassDemo
```

**Standard output:**

```text
java
true
```

Diễn giải:

- `TextUtils` là top-level package-private `final` class. Trong chương trình demo, `UtilityClassDemo` ở cùng package nên được gọi các static methods package-private của `TextUtils`.
- `TextUtils.normalize(...)` hoạt động mà **không có `TextUtils` object**.
- Constructor là `private`; client ở lớp khác không được gọi trực tiếp.
- Constructor cố ý ném `AssertionError` để nhấn mạnh utility không mong đợi có instance; đây là một phương án, không phải yêu cầu bắt buộc.
- Hai static methods làm việc với tham số, không duy trì mutable instance state.

**Lưu ý biên dịch:** ví dụ trên có đúng **một public top-level class** `UtilityClassDemo`. `TextUtils` không public nên có thể nằm trong cùng tệp. Nếu muốn `TextUtils` là API public cho package khác, nên đưa vào tệp `TextUtils.java` và khai báo `public final class TextUtils`, đồng thời công khai những method dự kiến cho caller bên ngoài.

## 5. Constructor `private` thực sự chặn điều gì?

Một constructor private quy định **nơi code Java bình thường được phép gọi constructor**. Ví dụ:

```java
final class ParserUtils {
    private ParserUtils() {
    }

    static int parsePositive(String raw) {
        int value = Integer.parseInt(raw);
        if (value <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }
        return value;
    }
}
```

Caller vẫn được dùng static API khi quyền truy cập cho phép:

```java
int number = ParserUtils.parsePositive("12");
```

Nhưng một class unrelated không được:

```java
// ParserUtils parser = new ParserUtils(); // Lỗi compile-time.
```

**Điểm quan trọng:** private constructor **không ngăn class được nạp hoặc khởi tạo tĩnh**, không ngăn gọi static methods, không tạo singleton instance và không có nghĩa “lớp không tồn tại tại runtime”.

Java còn có các tình huống **truy cập private được phép** trong quan hệ enclosing/nestmate của các nested classes. Vì vậy phát biểu chính xác là “constructor private chặn việc tạo instance thông thường từ code không có quyền”, **không** phải “không chương trình nào có thể tạo object này trong mọi hoàn cảnh”.

### Có nên viết constructor rỗng hay ném `AssertionError`?

Cả hai phiên bản sau đều phổ biến:

```java
private ParserUtils() {
}
```

```java
private ParserUtils() {
    throw new AssertionError("Utility class");
}
```

- **Constructor rỗng**: đủ để chặn code bên ngoài phạm vi truy cập hợp lệ gọi constructor.
- **Constructor ném `AssertionError`**: thể hiện rõ rằng ngay cả code có quyền truy cập private nhưng vô tình gọi constructor cũng sẽ thất bại khi chạy.
- **Không có yêu cầu** utility constructor phải ném exception; code sử dụng `throw` là lựa chọn thiết kế/đội nhóm.
- `AssertionError` không phải cơ chế bảo mật chống reflection hoặc mọi cách tạo object phi chuẩn.
- Đừng nhầm kiểu `AssertionError` với keyword `assert`: chúng khác nhau; ném `new AssertionError(...)` **không phụ thuộc** việc bật JVM assertions bằng `-ea`.

**Khuyến nghị:** chọn một convention đơn giản, nhất quán. Việc có một constructor private tường minh quan trọng hơn tranh luận giữa thân rỗng và thân ném lỗi.

## 6. Constructor không có kiểu trả về, kể cả `void`

Constructor là cú pháp riêng của Java: tên **trùng tên class**, không khai báo return type.

Đúng:

```java
final class Constants {
    private Constants() {
    }
}
```

Sai về ý định:

```java
class Constants {
    private void Constants() {
        // Đây là method tên Constants, KHÔNG phải constructor.
    }
}
```

Trong ví dụ thứ hai, `private void Constants()` là **một method hợp lệ** nếu không xung đột các quy tắc khác. Vì class **không khai báo constructor thực sự**, compiler vẫn có thể cung cấp default constructor. Việc thêm `void` vô tình **không chặn tạo instance**.

Đây là lỗi rất nguy hiểm khi người học cố “tạo private constructor” nhưng lại viết thành private method. Cách kiểm tra: constructor không có `void`, `int`, `String` hay kiểu trả về nào.

## 7. Khi không khai báo constructor, Java tự tạo default constructor

Khác biệt giữa:

```java
public class Utility {
    public static int doubleOf(int x) {
        return x * 2;
    }
}
```

và:

```java
public class Utility {
    private Utility() {
    }

    public static int doubleOf(int x) {
        return x * 2;
    }
}
```

Đây là **hai phiên bản thay thế**, không biên dịch cùng lúc với trùng tên `Utility`.

Ở phiên bản đầu, vì class không có constructor được khai báo, compiler bổ sung **default constructor** với access modifier tương ứng theo quy tắc Java. Với public top-level class thông thường, default constructor public, nên client có thể viết `new Utility()`.

Ở phiên bản sau, constructor được khai báo tường minh và private; compiler **không tự thêm một public no-arg constructor nữa**. Đó là lý do kiểu utility class phải ghi constructor private **chứ không chỉ bỏ constructor ra khỏi mã nguồn**.

### Một constructor có tham số cũng ngăn default no-arg constructor

Nếu class khai báo `Utility(int code)`, Java không thêm `Utility()` mặc định. Nhưng caller có thể tạo object qua `new Utility(1)` khi constructor này accessible. Để tuyên bố “không cần instance”, nên giữ **chỉ những constructors private có chủ đích**; một public constructor bất kỳ vẫn cho phép tạo instance.

## 8. Vì sao `final` thường đi kèm private constructor?

`final class` không thể được subclass. Với một utility-only class, kế thừa thường không có ý nghĩa vì:

1. Static methods không được override bằng cơ chế đa hình instance thông thường; một static method trùng chữ ký ở subclass có thể là **hiding**, không phải dynamic dispatch.
2. Không có instance state hoặc instance behavior cần mở rộng.
3. Kế thừa utility class chủ yếu để gọi static members bằng tên subclass gây hiểu nhầm về chủ sở hữu API.
4. `final` làm ý định “đây là nhóm tiện ích, không phải base class” rõ ràng.

Ví dụ:

```java
public final class DateTextUtils {
    private DateTextUtils() {
    }

    public static String yearMonth(int year, int month) {
        return year + "-" + String.format("%02d", month);
    }
}
```

Code trên là một utility class; không cần tạo object hoặc kế thừa để dùng `DateTextUtils.yearMonth(2026, 10)`.

**Lưu ý thiết kế:** Nếu mục tiêu thật sự là hỗ trợ subclass override logic định dạng, hãy cân nhắc **instance interface/strategy** thay vì cố gắng override một static method. `final` và private constructor không phải “tối ưu performance” bắt buộc; chúng truyền đạt hợp đồng.

## 9. Ví dụ thực tế: tiện ích kiểm tra và chuẩn hóa mã

Tạo **`CodeUtilsDemo.java`**:

```java
final class CodeUtils {
    private CodeUtils() {
        throw new AssertionError("No instances");
    }

    static String canonical(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("code required");
        }

        String value = raw.trim().toUpperCase();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("blank code");
        }

        return value;
    }

    static boolean same(String first, String second) {
        return canonical(first).equals(canonical(second));
    }

    static String withPrefix(String prefix, String raw) {
        return canonical(prefix) + "-" + canonical(raw);
    }
}

public class CodeUtilsDemo {
    public static void main(String[] args) {
        System.out.println(CodeUtils.canonical("  ab-12  "));
        System.out.println(CodeUtils.same(" a1 ", "A1"));
        System.out.println(CodeUtils.withPrefix(" item ", " b2 "));
    }
}
```

```bash
javac CodeUtilsDemo.java
java CodeUtilsDemo
```

```text
AB-12
true
ITEM-B2
```

Bài học:

- `canonical` là static method thuần về mặt trạng thái đối tượng utility; giá trị trả về dựa trên đối số.
- `same` và `withPrefix` tái sử dụng `canonical` để tránh lặp validation.
- Không có field instance hay object `CodeUtils` nào.
- Method có thể ném exception khi input không hợp lệ; static không đồng nghĩa “không thể thất bại”.
- `toUpperCase()` và `toLowerCase()` mặc định có thể phụ thuộc locale khi dùng mà không chỉ định locale. Với **mã định danh giao thức** cần tính ổn định xuyên máy, nên cân nhắc `toUpperCase(Locale.ROOT)`. Ví dụ trên dùng input ASCII để stdout xác định; phần thiết kế production cần làm rõ quy tắc locale.

### Phiên bản thân thiện với mã định danh không phụ thuộc locale

```java
import java.util.Locale;

final class CanonicalIds {
    private CanonicalIds() {
    }

    static String of(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("id required");
        }
        return input.trim().toUpperCase(Locale.ROOT);
    }
}
```

Đây là **khai báo class minh họa**; import nằm ở đầu file khi dùng. `Locale.ROOT` giúp phép chuyển case theo quy tắc locale-neutral cho nhiều trường hợp xử lý identifier; không tự biến phép normalize này thành một chính sách Unicode/security identifier hoàn chỉnh.

## 10. Phân biệt utility class với object có trạng thái

Một utility class thích hợp với thao tác kiểu:

```java
int max = Math.max(a, b);
String key = CodeUtils.canonical(raw);
```

Nhưng nếu bài toán cần trạng thái khác nhau theo người dùng, session, cấu hình hoặc vòng đời, một **instance class** thường phù hợp hơn.

Ví dụ không nên nhét toàn bộ vào mutable static field:

```java
class BadCartUtils {
    static int total;

    static void add(int amount) {
        total += amount;
    }
}
```

Các người dùng/caller trong cùng tiến trình có thể vô tình chia sẻ một biến `total` chung. Method `add` là static nhưng dữ liệu **thuộc từng giỏ hàng**, không phải cấp ứng dụng.

Một thiết kế đúng ngữ nghĩa:

```java
class ShoppingCart {
    private int total;

    void add(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        total += amount;
    }

    int total() {
        return total;
    }
}
```

Mỗi `new ShoppingCart()` tạo một object có `total` riêng. `cart.add(...)` là instance method, có receiver cụ thể. Có thể có một static helper hỗ trợ tính phí, nhưng bản thân **trạng thái giỏ hàng** nên thuộc về object giỏ hàng.

**Nguyên tắc:** đừng dùng utility class để tránh học class/object hoặc để biến state riêng của mỗi instance thành state toàn cục.

## 11. Ví dụ so sánh stateless utility và stateful object

Tạo tệp **`UtilityVsObjectDemo.java`**:

```java
final class PriceUtils {
    private PriceUtils() {
    }

    static int withFee(int price, int fee) {
        if (price < 0 || fee < 0) {
            throw new IllegalArgumentException("negative value");
        }
        return Math.addExact(price, fee);
    }
}

class Cart {
    private int total;

    void addItem(int price, int fee) {
        total = Math.addExact(total, PriceUtils.withFee(price, fee));
    }

    int total() {
        return total;
    }
}

public class UtilityVsObjectDemo {
    public static void main(String[] args) {
        Cart first = new Cart();
        Cart second = new Cart();

        first.addItem(100, 10);
        first.addItem(50, 5);
        second.addItem(20, 2);

        System.out.println("first=" + first.total());
        System.out.println("second=" + second.total());
    }
}
```

```bash
javac UtilityVsObjectDemo.java
java UtilityVsObjectDemo
```

```text
first=165
second=22
```

Ở đây:

- `PriceUtils.withFee` là static utility: chỉ dựa vào `price` và `fee`, không cần state instance.
- `Cart.addItem` là instance method: nó sửa `total` thuộc về từng giỏ.
- Các phép cộng dùng `Math.addExact` để lỗi tràn số xảy ra **trước khi phép gán vào total hoàn thành**, tránh làm hỏng field ở trường hợp overflow.
- Một utility class không thay thế được vai trò lưu trạng thái của `Cart`.

Chọn tách utility và instance class theo **ranh giới trách nhiệm**, không vì “static tiện gọi hơn”.

## 12. Utility class không phải singleton

Một **singleton** là mẫu thiết kế cố gắng cung cấp **một instance được chia sẻ**, trong khi utility class với constructor private và chỉ static methods thường **không cần instance nào**.

So sánh:

| Tiêu chí | Utility class | Singleton/service có một instance |
| --- | --- | --- |
| API chính | `TypeName.staticMethod()` | `getInstance().instanceMethod()` hoặc inject service |
| Instance cần thiết | Không | Có |
| State per instance | Thường không có | Có thể có |
| Constructor private | Ngăn tạo instance thông thường | Có thể kiểm soát số instance |
| Đa hình qua instance | Không cho static methods | Có thể nếu API là instance và thiết kế hỗ trợ |
| Test dependency substitution | Thường phải refactor/cấu hình wrapper | Có thể thay implementation bằng interface/DI |
| Vòng đời và cleanup | Không có utility object để đóng | Có thể quản lý vòng đời/service |

**Một private constructor không tự tạo singleton.** Nó chỉ hạn chế quyền gọi constructor. Để có singleton cần cơ chế tạo, giữ và công bố instance với hợp đồng thích hợp.

Ví dụ singleton (chỉ để đối chiếu):

```java
final class ConfigService {
    private static final ConfigService INSTANCE = new ConfigService();

    private ConfigService() {
    }

    static ConfigService getInstance() {
        return INSTANCE;
    }

    String mode() {
        return "demo";
    }
}
```

Ở đây `getInstance()` là static, nhưng `mode()` là **instance method** trên singleton object. Ngược lại, một utility class thuần không tạo `INSTANCE` và không có `mode()` gắn state object.

**Lưu ý:** nếu mục tiêu là singleton mạnh và tránh nhiều trường hợp serialization/reflection, `enum` singleton thường là lựa chọn đáng cân nhắc. Đây là một bài toán khác với utility class và không cần dùng enum chỉ để chứa static helpers.

## 13. Không nên thêm mutable static fields tùy tiện

Static utility chỉ dựa vào input thường dễ dùng lại và dễ kiểm thử. Nhưng nếu đưa mutable static field vào utility, nó trở thành **shared application state**:

```java
final class RequestUtils {
    private static int counter;

    private RequestUtils() {
    }

    static int next() {
        return ++counter;
    }
}
```

`RequestUtils.next()` gọi ở đâu cũng sửa cùng một field `counter` của class theo class loader/định danh lớp tương ứng. Trong nhiều thread, `++counter` có nguy cơ lost updates; `static` **không đảm bảo atomicity hoặc thread safety**.

Phiên bản khi thực sự muốn shared counter:

```java
import java.util.concurrent.atomic.AtomicInteger;

final class RequestUtils {
    private static final AtomicInteger COUNTER = new AtomicInteger();

    private RequestUtils() {
    }

    static int next() {
        return COUNTER.incrementAndGet();
    }
}
```

Hai đoạn `RequestUtils` là **hai phiên bản thay thế**. `AtomicInteger.incrementAndGet` hỗ trợ tăng nguyên tử theo contract của loại này. Tuy nhiên, nếu cần ID duy nhất giữa nhiều JVM hoặc sau restart, một static counter trong một tiến trình vẫn không đủ.

**Câu hỏi thiết kế:** dữ liệu ấy thuộc cả ứng dụng hay thuộc một object cụ thể? Nếu có session/tenant/test scope riêng, ưu tiên giữ state trong instance/service có vòng đời tường minh thay vì giấu trong utility class.

## 14. Static methods nên giữ đơn giản và rõ ràng về side effect

Một utility method được đặt tên `normalize` hoặc `calculate` thường tạo kỳ vọng **ít side effect**. Không có quy tắc Java bắt buộc static method pure, nhưng việc giữ utility behavior rõ ràng giúp client tin cậy hơn.

So sánh hai cách:

```java
static int sortedMaximum(int[] values) {
    java.util.Arrays.sort(values);
    return values[values.length - 1];
}
```

Method này **sửa mảng đầu vào** và còn lỗi với mảng rỗng. Nếu API chỉ mang nghĩa “tìm max”, mutation không cần thiết.

Một lựa chọn không mutate đầu vào:

```java
static int maximum(int[] values) {
    if (values == null || values.length == 0) {
        throw new IllegalArgumentException("values required");
    }

    int max = values[0];
    for (int value : values) {
        if (value > max) {
            max = value;
        }
    }
    return max;
}
```

Đây là **hai mảnh static methods minh họa**; đặt một trong một utility class phù hợp. Bản thứ hai đọc mảng mà không sắp xếp/thay slots, nêu rõ precondition và bảo vệ đầu vào rỗng/null.

**Thiết kế tốt:** document nếu method **mutate arguments**, có side effect I/O, truy cập shared mutable state, cache hoặc dùng thời gian hiện tại. `static` không bảo đảm purity; chính implementation và contract quyết định.

## 15. Public API và private helper methods

Một utility class có thể có **public static methods** phục vụ client và **private static helpers** chỉ phục vụ implementation.

Tệp **`ApiHelperDemo.java`**:

```java
final class KeyUtils {
    private KeyUtils() {
    }

    static String key(String prefix, String raw) {
        return requirePart(prefix) + ":" + requirePart(raw);
    }

    private static String requirePart(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("blank part");
        }
        return input.trim().toUpperCase(java.util.Locale.ROOT);
    }
}

public class ApiHelperDemo {
    public static void main(String[] args) {
        System.out.println(KeyUtils.key(" user ", " a42 "));

        // KeyUtils.requirePart("x"); // Lỗi: private.
    }
}
```

```bash
javac ApiHelperDemo.java
java ApiHelperDemo
```

```text
USER:A42
```

Trong demo này `KeyUtils.key` package-private vì client ở cùng package. Khi cung cấp public library, có thể khai báo `public final class KeyUtils` và `public static String key(...)`; giữ `requirePart` private.

**Nguyên tắc đóng gói:** public utility class không cần biến mọi helper method/field thành public. Chỉ mở những lời gọi có contract ổn định; private helpers có thể thay đổi tên và implementation mà client không phụ thuộc trực tiếp.

### Top-level utility class có thể package-private

Không nhất thiết helper phải public. Nếu một tiện ích chỉ được dùng bởi các classes trong package `app.internal`, dùng:

```java
final class InternalMath {
    private InternalMath() {
    }

    static int clamp(int value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("invalid bounds");
        }
        return Math.max(min, Math.min(value, max));
    }
}
```

`InternalMath` là top-level package-private class. Mọi class trong cùng package có thể gọi `InternalMath.clamp(...)` theo quyền truy cập; code package khác không tự dùng được. Constructor vẫn private vì không cần tạo instance.

## 16. Static imports: viết gọn nhưng không đổi bản chất utility

Giả sử utility public:

```java
package demo.util;

public final class CheckUtils {
    private CheckUtils() {
    }

    public static boolean positive(int value) {
        return value > 0;
    }
}
```

Tệp nên lưu tên **`CheckUtils.java`** trong package `demo.util`. Caller khác package có thể gọi:

```java
boolean valid = demo.util.CheckUtils.positive(5);
```

Hoặc static import:

```java
import static demo.util.CheckUtils.positive;
```

rồi:

```java
boolean valid = positive(5);
```

Đây là **các mảnh source minh họa, không phải một file ghép nguyên văn**; `import` phải nằm đúng vị trí đầu compilation unit.

`import static` không tạo instance, không gọi method và không thay đổi modifier truy cập. Nó chỉ giúp giải quyết tên method không cần qualification ở chỗ gọi; access rules vẫn áp dụng.

Không nên static import tràn lan mọi method có tên chung như `parse`, `get`, `check` nếu điều đó làm code khó biết implementation thuộc đâu. Với API tiện ích rõ nghĩa, `CheckUtils.positive(...)` thường dễ theo dõi hơn.

## 17. Công khai hằng số trong utility class có cần không?

Một utility class có thể lưu các hằng số:

```java
public final class Limits {
    public static final int MAX_BATCH_SIZE = 100;

    private Limits() {
    }
}
```

Đọc bằng `Limits.MAX_BATCH_SIZE`. Nhưng chỉ dùng `public` khi đây là một phần **API contract** cần cho client. Hằng nội bộ nên `private static final` hoặc package-private theo yêu cầu.

### Phân biệt `static final` với bất biến sâu

`public static final int MAX_BATCH_SIZE` là primitive constant không thể bị gán lại từ code khác.

Ngược lại:

```java
public static final java.util.List<String> NAMES =
        new java.util.ArrayList<>();
```

Mặc dù field reference là `final`, **list object vẫn mutable**; caller có thể viết `SomeUtils.NAMES.add("X")` nếu field accessible. Với dữ liệu dùng chung công khai, cân nhắc `List.of(...)` hoặc trả defensive copy/unmodifiable view theo contract.

**Một sai lầm phổ biến:** utility class không có instances nên “mọi dữ liệu trong đó đều an toàn”. Static mutable objects có thể là nguồn side effects khó thấy hơn so với state instance.

## 18. Tổ chức file Java và tên public class

Một public top-level utility class nên đặt trong file trùng tên class:

```text
src/
  demo/
    util/
      TextUtils.java
    app/
      Main.java
```

**Tệp `src/demo/util/TextUtils.java`:**

```java
package demo.util;

public final class TextUtils {
    private TextUtils() {
    }

    public static String headline(String text) {
        if (text == null) {
            throw new IllegalArgumentException("text required");
        }
        return text.trim().toUpperCase(java.util.Locale.ROOT);
    }
}
```

**Tệp `src/demo/app/Main.java`:**

```java
package demo.app;

import demo.util.TextUtils;

public class Main {
    public static void main(String[] args) {
        System.out.println(TextUtils.headline(" java core "));
    }
}
```

Từ thư mục chứa `src`:

```bash
javac -encoding UTF-8 -d out src/demo/util/TextUtils.java src/demo/app/Main.java
java -cp out demo.app.Main
```

**Output:**

```text
JAVA CORE
```

Ở đây:

- `TextUtils` top-level public để code ở `demo.app` đặt tên được.
- Constructor private giữ ý định không tạo object.
- Static method public để caller package khác dùng.
- `Main` chỉ phụ thuộc static API, không cần `new TextUtils()`.

Nếu dự án dùng **JPMS named modules**, package có class public còn phải được export thích hợp cho module khác. `public` không tự vượt qua ranh giới `module-info.java`.

## 19. Không nên cất cấu hình thay đổi vào static utility

Một utility class như:

```java
final class FormatUtils {
    static String language = "vi";

    private FormatUtils() {
    }

    static String greeting() {
        return language.equals("vi") ? "Xin chào" : "Hello";
    }
}
```

tạo một điểm chia sẻ mutable state theo class. Nếu hai người dùng hoặc hai test cần locale khác nhau, việc sửa `FormatUtils.language` có thể gây tác động lẫn nhau. Ngoài ra, có rủi ro concurrency.

Thiết kế stateful object:

```java
final class Greeter {
    private final String language;

    Greeter(String language) {
        this.language = language;
    }

    String greeting() {
        return "vi".equals(language) ? "Xin chào" : "Hello";
    }
}
```

Mỗi `Greeter` giữ cấu hình riêng. Một utility class có thể vẫn cung cấp **phép tính nhận language làm tham số**, nhưng không nhất thiết sở hữu cấu hình global:

```java
static String greeting(String language) {
    return "vi".equals(language) ? "Xin chào" : "Hello";
}
```

Mảnh method này đặt trong utility class. **Quy tắc chọn:** nếu biến thiên theo người dùng/request/tenant/lifecycle, truyền cấu hình tường minh hoặc dùng instance service/strategy thường an toàn và rõ hơn một mutable static field.

## 20. Utility class và dependency injection/testability

Static helper thuần, không phụ thuộc môi trường, thường dễ kiểm thử:

```java
int result = PriceUtils.withFee(100, 10);
```

Nhưng static method tự đọc thời gian thực, biến môi trường hoặc gọi mạng có thể khó kiểm soát trong tests:

```java
// Mảnh ví dụ về thiết kế dễ phụ thuộc môi trường:
static java.time.Instant now() {
    return java.time.Instant.now();
}
```

Nếu code nghiệp vụ cần một “clock” có thể giả lập, truyền dependency phù hợp:

```java
class ReportService {
    private final java.time.Clock clock;

    ReportService(java.time.Clock clock) {
        this.clock = clock;
    }

    java.time.Instant generatedAt() {
        return java.time.Instant.now(clock);
    }
}
```

Ở đây `ReportService` là instance service có dependency tường minh; trong test có thể truyền `Clock.fixed(...)`, trong production truyền clock hệ thống. `Instant.now(clock)` là static factory nhưng đọc clock được cung cấp, dễ test hơn API buộc dùng clock hệ thống.

**Không phải static method luôn khó test:** pure static utility methods có đầu vào/đầu ra ổn định thường rất dễ test. Khó khăn xuất hiện khi static method **ẩn dependency mutable/không xác định** hoặc cần thay implementation ở runtime.

## 21. Ví dụ chạy: thiết kế utility cho kiểm tra khoảng giá trị

Tệp **`RangeUtilsDemo.java`**:

```java
final class RangeUtils {
    private RangeUtils() {
        throw new AssertionError("No RangeUtils instances");
    }

    static boolean contains(int value, int min, int max) {
        checkBounds(min, max);
        return value >= min && value <= max;
    }

    static int clamp(int value, int min, int max) {
        checkBounds(min, max);
        return Math.max(min, Math.min(value, max));
    }

    private static void checkBounds(int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
    }
}

public class RangeUtilsDemo {
    public static void main(String[] args) {
        System.out.println(RangeUtils.contains(7, 1, 10));
        System.out.println(RangeUtils.contains(12, 1, 10));
        System.out.println(RangeUtils.clamp(-3, 0, 100));
        System.out.println(RangeUtils.clamp(150, 0, 100));
    }
}
```

```bash
javac RangeUtilsDemo.java
java RangeUtilsDemo
```

```text
true
false
0
100
```

Điểm đáng chú ý:

- `contains` và `clamp` là **static API** rõ nghĩa.
- `checkBounds` là private static helper, tránh lặp validation nhưng không phơi chi tiết nội bộ.
- Constructor private bảo vệ thiết kế không-instance.
- `final` class ngăn kế thừa.
- Mỗi lần gọi tự thực hiện kiểm tra; không có object state cần lưu giữa các lời gọi.

**Giới hạn phạm vi:** utility `RangeUtils` xử lý số nguyên và hai biên inclusive; nếu muốn API khác như half-open interval, nên đặt method tên/contract khác thay vì âm thầm đổi ý nghĩa `contains`.

## 22. Tránh duplicate helper classes và tên quá chung

Một utility class có thể trở thành “thùng chứa đủ thứ” nếu gom những method không liên quan chỉ vì chúng đều static:

```java
class Utils {
    static String normalizeName(String name) { /* ... */ return name; }
    static int calculateTax(int value) { /* ... */ return value; }
    static void sendEmail(String email) { /* ... */ }
}
```

Đây là **mảnh mã minh họa cấu trúc**, thân methods đã giản lược. Tên `Utils` không nói rõ trách nhiệm; testability và ownership có thể kém.

Tốt hơn là nhóm theo domain cụ thể:

- `NameNormalizer` hoặc `NameUtils` cho xử lý tên.
- `TaxCalculator` cho tính thuế (có thể là instance nếu có chính sách/cấu hình).
- `EmailService` cho gửi email (thường là service có dependency, không nên vô tư đặt trong static helper nếu cần kết nối, retry, log, config).

Mục tiêu không phải càng nhiều class càng tốt. Một utility class tốt **có tính gắn kết chức năng (cohesion)**: các methods liên quan, một contract dễ hiểu, ít shared state và không che giấu dependency.

## 23. Những trường hợp `private constructor` là thiết kế không phù hợp

Không nên áp dụng mẫu “private constructor + static methods” nếu:

1. **Object có state riêng**: `BankAccount`, `Order`, `ShoppingCart` nên có instance lifecycle phù hợp.
2. **Cần polymorphism/strategy**: các implementation có thể thay thế nhau, interface và instance methods thường phù hợp hơn.
3. **Cần dependency injection**: một service phụ thuộc `Clock`, repository, HTTP client... thường cần constructor/factory nhận dependency, không nên tự giấu mọi thứ vào static global.
4. **Cần giữ resource và đóng nó**: database connection/session/file handle cần vòng đời/cleanup rõ, không nên mô phỏng bằng mutable static fields không kiểm soát.
5. **Class là base class có chủ đích kế thừa**: private constructor có thể khiến subclass không gọi được constructor superclass từ ngữ cảnh thích hợp; `final` trực tiếp cấm kế thừa.
6. **Static factory trả đối tượng là mục đích chính nhưng lớp cũng là kiểu dữ liệu**: ví dụ `UserId.of(...)` với private constructor là *immutable value object có factory*, **không nhất thiết là utility class**; `UserId` vẫn có instances với value riêng.
7. **Framework cần khởi tạo class bằng cách riêng**: hãy đọc hợp đồng framework (ORM, serializer, dependency injection) trước khi khóa constructor. Không giả định utility pattern dùng cho entity/component class.

**Tiêu chí đánh giá:** Nếu việc tạo nhiều instances của class là **có ý nghĩa với miền nghiệp vụ**, nó thường không phải utility-only class.

## 24. Cạm bẫy liên quan đến kế thừa và static method hiding

Viết `final` utility class ngăn việc người khác tạo subclass. Ngay cả nếu bỏ `final`, static methods **không** tham gia polymorphic overriding như instance methods.

Ví dụ:

```java
class BaseUtils {
    static String name() {
        return "Base";
    }
}

class ChildUtils extends BaseUtils {
    static String name() {
        return "Child";
    }
}
```

Nếu có `BaseUtils ref = new ChildUtils();`, lời gọi `ref.name()` vẫn chọn `BaseUtils.name()` theo static method resolution, không phải Child dựa trên object runtime. Trong thiết kế utility, việc `extends BaseUtils` thường không đem lại đa hình người ta mong muốn.

**Chú ý:** ví dụ trên cho phép tạo instances để minh họa method hiding, **không phải** mẫu utility class chuẩn vì các constructors không private. Bản utility-only thật nên dùng `final` và private constructor nếu không có mục tiêu inheritance.

## 25. Nested utility helper có thể `private static class`

Nếu helper chỉ phục vụ một public class, không nhất thiết cần một top-level utility class mới:

```java
public class ReportService {
    private static final class Text {
        private Text() {
        }

        static String tidy(String value) {
            return value == null ? "" : value.trim();
        }
    }

    public String report(String title) {
        return "Report:" + Text.tidy(title);
    }
}
```

Trong ví dụ này:

- `Text` là **private static nested class**, chỉ serving implementation của `ReportService`.
- `static` trên nested class nghĩa nó **không cần enclosing `ReportService` instance** để tồn tại.
- `private` trên nested class quyết định phạm vi truy cập tên kiểu.
- Constructor private bên trong `Text` chặn tạo object utility không cần thiết.
- `Text.tidy` static method có thể được `ReportService` gọi theo các quy tắc truy cập giữa enclosing/nested classes.

Không cần biến `Text` thành public top-level utility chỉ để một method gọi nó. Tuy nhiên nếu chỉ có một helper method rất nhỏ, có thể đơn giản hơn đặt `private static String tidy(...)` trực tiếp trong `ReportService`, không tạo thêm nested type.

## 26. Constructor private vẫn có thể được code có quyền gọi

Một quy tắc cần hiểu chính xác: code trong **chính class** luôn có thể gọi private constructor; các trường hợp nestmate/enclosing cũng có thể truy cập theo quy tắc ngôn ngữ.

Tệp **`PrivateConstructorScopeDemo.java`**:

```java
public class PrivateConstructorScopeDemo {
    private PrivateConstructorScopeDemo() {
        System.out.println("constructor called internally");
    }

    public static void main(String[] args) {
        // Cùng class nên private constructor vẫn accessible.
        PrivateConstructorScopeDemo instance =
                new PrivateConstructorScopeDemo();

        System.out.println(instance != null);
    }
}
```

```bash
javac PrivateConstructorScopeDemo.java
java PrivateConstructorScopeDemo
```

```text
constructor called internally
true
```

Ví dụ trên **cố ý** gọi private constructor từ chính class để minh họa giới hạn quyền truy cập. Nó **không phải mẫu utility class thực hành** (vì utility class không nên tạo instance vô nghĩa). Nếu muốn class tự ngăn cả lỗi vô tình này ở runtime, có thể ném `AssertionError` trong constructor, nhưng vẫn không coi đó là cơ chế “bất khả tạo object” trước mọi kỹ thuật reflection/VM.

**Kết luận về `private`:** xác định quyền của **source code** theo ngữ cảnh. Nó không biến constructor thành cú pháp bất hợp lệ ở mọi nơi.

## 27. Có nên dùng `abstract` thay vì constructor `private`?

Một người học có thể đề xuất:

```java
abstract class Utility {
    static int square(int x) {
        return x * x;
    }
}
```

Vì abstract class không được khởi tạo trực tiếp bằng `new Utility()`, nhưng:

- Class có thể được **subclass** nếu không bị những hạn chế khác.
- Nếu không khai báo constructor, nó vẫn có default constructor thích hợp cho subclass.
- Từ khóa `abstract` đưa ra ý nghĩa “có thể là base class cho implementations”, dễ đánh lạc hướng.
- `abstract final class Utility` là tổ hợp modifier bất hợp lệ trong Java đối với class.

Vì vậy với utility-only class **không cần instance và không cần inheritance**, thường chọn **`final class + private constructor`** thay vì dùng `abstract` để chặn `new` một cách gián tiếp.

## 28. Unit testing utility class

Pure static methods nhận input và trả output tương đối dễ test. Đặc biệt hãy kiểm:

- Input bình thường và biên (0, âm, giá trị lớn, null khi API có thể nhận null).
- Ranh giới số học (`Integer.MAX_VALUE`, overflow, chia cho 0 nếu liên quan).
- Locale, Unicode, encoding khi xử lý chuỗi.
- Những input không hợp lệ phải ném exception đúng contract.
- Nếu method mutate array/list do caller cung cấp, cần test side effects hoặc xác nhận không mutate.
- Nếu có shared state/static cache, cần test isolation và concurrency phù hợp.

Một ví dụ test thủ công không cần framework:

Tệp **`UtilitySelfTestDemo.java`**:

```java
final class NumberUtils {
    private NumberUtils() {
    }

    static int positiveSquare(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("negative");
        }
        return Math.multiplyExact(value, value);
    }
}

public class UtilitySelfTestDemo {
    public static void main(String[] args) {
        if (NumberUtils.positiveSquare(3) != 9) {
            throw new AssertionError("3^2 should be 9");
        }

        boolean invalidRejected = false;
        try {
            NumberUtils.positiveSquare(-1);
        } catch (IllegalArgumentException ex) {
            invalidRejected = true;
        }

        if (!invalidRejected) {
            throw new AssertionError("negative input accepted");
        }

        System.out.println("tests passed");
    }
}
```

```bash
javac UtilitySelfTestDemo.java
java UtilitySelfTestDemo
```

```text
tests passed
```

`NumberUtils.positiveSquare` kiểm input âm và dùng `Math.multiplyExact` để ném lỗi khi bình phương tràn số `int`, trước khi có bất kỳ mutable state nào cần khôi phục. `assert` statement không xuất hiện nên phép kiểm không phụ thuộc `-ea`.

**Không bắt buộc kiểm thử constructor private bằng reflection** chỉ để đạt code coverage. Giá trị thiết kế ở đây là constructor **không nằm trong API accessible** với client bình thường. Test nên ưu tiên contract của static methods và các failure cases hữu ích.

## 29. Câu hỏi thực hành: thiết kế đúng utility cho tập hợp giá trị

Tạo tệp **`CollectionUtilsDemo.java`**:

```java
import java.util.List;

final class NumberListUtils {
    private NumberListUtils() {
        throw new AssertionError("No instances");
    }

    static int sum(List<Integer> numbers) {
        if (numbers == null) {
            throw new IllegalArgumentException("numbers required");
        }

        int total = 0;
        for (Integer number : numbers) {
            if (number == null) {
                throw new IllegalArgumentException("null element");
            }
            total = Math.addExact(total, number);
        }
        return total;
    }

    static int countPositive(List<Integer> numbers) {
        if (numbers == null) {
            throw new IllegalArgumentException("numbers required");
        }

        int count = 0;
        for (Integer number : numbers) {
            if (number == null) {
                throw new IllegalArgumentException("null element");
            }
            if (number > 0) {
                count++;
            }
        }
        return count;
    }
}

public class CollectionUtilsDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(-2, 4, 7);

        System.out.println(NumberListUtils.sum(numbers));
        System.out.println(NumberListUtils.countPositive(numbers));
        System.out.println(numbers);
    }
}
```

```bash
javac CollectionUtilsDemo.java
java CollectionUtilsDemo
```

```text
9
2
[-2, 4, 7]
```

- `NumberListUtils` chứa các phép tính liên quan cùng domain là danh sách số nguyên.
- Constructor private, class final: không cần utility instance.
- Methods static, không lưu mutable state giữa các lần gọi.
- Validate list và phần tử null theo contract đã chọn.
- Dùng `Math.addExact` để tránh âm thầm overflow khi cộng.
- Không gọi `remove`/`set`/`sort`, nên ví dụ không sửa structure hoặc element references của list đầu vào.

Trong Java tổng quát, `List<Integer>` có thể là một danh sách mutable/unmodifiable và có thể chứa null tùy implementation. Contract utility phải xác định null policy, không mặc định mọi list đều giống `List.of(...)`.

## 30. Chẩn đoán lỗi thường gặp

| Tình huống | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Viết static methods nhưng vẫn `new Utils()` được | Compiler thêm default constructor | Khai báo private constructor thật sự |
| Viết `private void Utils()` | Đây là method, không phải constructor | Bỏ return type `void` |
| Có private constructor nhưng vẫn có public constructor khác | Caller dùng constructor public còn lại | Rà soát toàn bộ constructors |
| Tưởng `final` ngăn tạo object | `final` chỉ ngăn subclass | Thêm private constructor |
| Tưởng private constructor chặn mọi cách tạo instance trên JVM | `private` là access control thông thường, không chứng minh bất khả thi tuyệt đối | Diễn đạt đúng contract; không dựa vào đây làm security boundary |
| Đặt `new Utils()` trong static utility method | Không cần instance utility | Gọi static helper trực tiếp |
| Gọi `utils.method()` khi method static | Cú pháp gây hiểu nhầm receiver | Viết `Utils.method()` |
| Dùng `this.field` trong static method | Static context không có `this` | Dùng tham số/object cụ thể hoặc instance method |
| Chuyển mutable field sang static để dễ gọi | Tạo shared state ngoài ý muốn | Giữ state trong instance/service |
| Dùng `abstract` làm utility class | Dễ gợi ý inheritance không mong muốn | `final` + private constructor |
| Đặt helper private cần dùng qua client | Access hẹp hơn nhu cầu public API | Chỉ mở API thực sự cần, giữ detail private |
| Công khai mutable `static final List` | final không làm list immutable | Dùng immutable/unmodifiable data, defensive copy |
| Utility chứa mọi helper không liên quan | Cohesion thấp | Chia theo trách nhiệm rõ |
| Mọi method thành static dù cần polymorphism | Static không override | Dùng instance interface/strategy |
| Dùng static clock/config global | Test và multi-tenant phụ thuộc môi trường | Truyền dependency qua tham số/constructor |
| Tưởng static method tự thread-safe | Static không cung cấp đồng bộ | Dùng atomic/lock hoặc loại shared mutation |
| Constructor private làm framework không tạo được entity | Framework cần hợp đồng construction riêng | Chọn pattern hợp với entity/framework thay vì utility |
| Dùng static import vô tội vạ | Source khó biết method thuộc class nào | Chỉ import rõ khi tăng khả năng đọc |

## 31. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** `public class Utils { public static int add(...); }` có chặn `new Utils()` không?

**Đáp án:** Không. Nếu không khai báo constructor nào, compiler cung cấp default constructor có quyền truy cập tương ứng, nên với public class thường có thể tạo instance.

**Câu 2.** Vì sao private constructor không làm `Utils.add(...)` ngừng hoạt động?

**Đáp án:** Static method được gọi qua kiểu; nó không cần object được tạo bởi constructor.

**Câu 3.** `private void Utils() { }` có phải private constructor không?

**Đáp án:** Không. Có `void` thì đó là method, còn default constructor có thể vẫn tồn tại.

**Câu 4.** `final class Utils` nhưng constructor public có cho phép `new Utils()` không?

**Đáp án:** Có. `final` cấm subclass chứ không cấm tạo instance.

**Câu 5.** Nếu constructor private có thân rỗng, code bên ngoài class unrelated có tạo object không?

**Đáp án:** Không theo quyền truy cập Java thông thường. Trong class/nest có quyền vẫn có thể gọi; thân rỗng không tự ném lỗi.

**Câu 6.** Có bắt buộc constructor private phải `throw new AssertionError(...)` không?

**Đáp án:** Không. Đây là tùy chọn để phát hiện lời gọi không mong đợi từ mã có quyền truy cập constructor.

**Câu 7.** Một utility class nên chứa nhiều mutable static fields theo từng người dùng không?

**Đáp án:** Thường không. Những giá trị thay đổi theo user/session/tenant nên nằm trong object/service hoặc tham số có vòng đời rõ.

**Câu 8.** `public static final List<String> DATA = new ArrayList<>();` có immutable không?

**Đáp án:** Không. Field reference final, nhưng list object vẫn mutable và có thể bị thay qua alias.

**Câu 9.** Phương thức `normalize(String)` có cần là static không?

**Đáp án:** Nếu không phụ thuộc instance state và có contract xử lý input rõ, static utility là lựa chọn tự nhiên; không phải yêu cầu tuyệt đối của ngôn ngữ.

**Câu 10.** Tại sao utility class khác singleton?

**Đáp án:** Utility không cần instance; singleton chủ động quản lý và cung cấp một instance.

**Câu 11.** Có thể dùng private constructor để tạo `UserId.of("A")` nhưng UserId vẫn là value object không?

**Đáp án:** Có. `of` là static factory, nhưng UserId instances mang giá trị riêng; đó không nhất thiết là utility class.

**Câu 12.** Static utility có thể nhận object mutable và sửa nó không?

**Đáp án:** Có nếu implementation thực hiện mutation hợp lệ. `static` không bảo đảm pure/side-effect-free.

**Câu 13.** `package-private final class InternalUtils` có cần public không?

**Đáp án:** Không nếu chỉ các classes cùng package cần truy cập. Constructor vẫn có thể private.

**Câu 14.** Tại sao `Math.max` là ví dụ tốt về static API?

**Đáp án:** Kết quả tính từ đối số; không cần một `Math` receiver object cụ thể.

**Câu 15.** Nếu unit test muốn thay implementation mỗi lần gọi mà static utility truy cập mạng trực tiếp, nên cân nhắc gì?

**Đáp án:** Tách dependency thành interface/service, inject client/config, hoặc truyền tham số phù hợp. Không nên vội dùng mutable static globals làm cấu hình kiểm thử.

**Câu 16.** Một private nested utility class có thể được outer class dùng không?

**Đáp án:** Có. Enclosing/nestmates có các quyền private access thích hợp theo Java.

**Câu 17.** Static utility có thể dùng generic method không?

**Đáp án:** Có. Nó có thể khai báo `static <T> ...` type parameter của riêng method, không cần instance.

**Câu 18.** Chỉ cần private constructor là chắc chắn class không bao giờ bị khởi tạo ở runtime?

**Đáp án:** Không. Class initialization và static method invocation vẫn có thể xảy ra. Private constructor hạn chế việc tạo instance theo access control, không chặn class được nạp/khởi tạo tĩnh.

## 32. Checklist khi review một utility class

- [ ] Tên lớp có gợi rõ nhóm chức năng, tránh `Utils` quá chung?
- [ ] Những methods có thật sự không cần receiver state hoặc identity?
- [ ] Không có instance fields không cần thiết?
- [ ] Constructor được khai báo `private` **không có return type**?
- [ ] Đã xem còn constructor public/protected/package-private nào vô tình để lộ không?
- [ ] Class có thể đặt `final` nếu không có contract subclass?
- [ ] Static methods được gọi theo dạng `ClassName.method(...)`?
- [ ] Helper methods nội bộ giữ `private static` khi thích hợp?
- [ ] Public class/methods chỉ mở khi client ngoài package thực sự cần?
- [ ] Static API có mô tả null policy, exception, range/overflow và side effects?
- [ ] Mutable input arrays/lists có bị sửa không mong muốn?
- [ ] Các hằng `static final` có thực sự bất biến về ý nghĩa, đặc biệt với object tham chiếu?
- [ ] Có static mutable fields gây test contamination hoặc concurrency issue không?
- [ ] Có đang nhầm static utility class với singleton, factory hoặc stateful service?
- [ ] Nếu gọi thư viện/framework, có cần dependency injection, lifecycle hoặc override thay static API không?
- [ ] Đã có ví dụ `javac`/`java` xác nhận static API dùng được mà không `new Utils()`?
- [ ] Nếu xử lý strings/identifiers, đã kiểm tra locale, Unicode và normalization contract?
- [ ] Nếu generic/static import/method reference được dùng, cú pháp và phạm vi truy cập có đúng?
- [ ] Khi refactor, có giữ public API stable và tránh công khai implementation helper không?

---

**Ghi nhớ:** Utility class dùng để gom **những thao tác cấp lớp không cần một object nhận lời gọi riêng**. Chỉ khai báo static methods **không đủ để chặn tạo object**, vì Java có thể sinh default constructor. Mẫu rõ nghĩa thường là **`final class` + constructor `private` + static API**: constructor private giới hạn lời gọi `new` từ bên ngoài, `final` cấm subclass, static methods gọi qua tên lớp. Đừng nhầm pattern này với singleton, đừng lạm dụng mutable static fields, và hãy chọn instance service/interface khi bài toán cần trạng thái, vòng đời hoặc đa hình.