# Phân loại phương thức `abstract`, `default`, `static` và `private` trong Java interface

## 1. Vì sao interface có nhiều loại phương thức?

Trong Java, `interface` xác định hợp đồng mà các lớp thực hiện (`implements`) phải tuân theo. Từ Java 8, interface không chỉ chứa các phương thức trừu tượng mà còn có thể cung cấp mã triển khai bằng phương thức `default` và `static`. Từ Java 9, interface có thể khai báo thêm các phương thức `private` để tái sử dụng logic nội bộ.

Bốn nhóm phương thức cần phân biệt theo **có thân hay không**, **cách gọi**, **phạm vi truy cập** và **khả năng kế thừa/ghi đè**.

| Loại phương thức | Cú pháp điển hình | Thân phương thức | Phạm vi truy cập | Cách sử dụng |
|---|---|---|---|---|
| `abstract` | `void execute();` hoặc `public abstract void execute();` | **Không có**, kết thúc bằng `;` | Luôn là `public` | Lớp thực hiện phải cung cấp triển khai nếu chưa có triển khai phù hợp được kế thừa và là lớp cụ thể. |
| `default` | `default void log() { ... }` | **Bắt buộc có** | Luôn là `public` | Gọi trên đối tượng triển khai interface; lớp triển khai có thể override. |
| `static` | `static boolean valid() { ... }` | **Bắt buộc có** | Mặc định là `public`; có thể khai báo `private static` để dùng nội bộ | Phương thức công khai được gọi qua **tên interface**; không được kế thừa như phương thức instance. |
| `private` (instance) | `private void helper() { ... }` | **Bắt buộc có** | Chỉ trong chính interface | Hỗ trợ mã dùng chung giữa các phương thức instance có thân, không phải API bên ngoài. |
| `private static` | `private static String normalize(...) { ... }` | **Bắt buộc có** | Chỉ trong chính interface | Hàm trợ giúp nội bộ dùng được từ cả ngữ cảnh `static` và ngữ cảnh instance của interface. |

**Mốc phiên bản:** `abstract` thuộc mô hình interface từ đầu; `default` và `static` có thân được hỗ trợ từ **Java 8**; `private` và `private static` trong interface được hỗ trợ từ **Java 9**. Tất cả ví dụ dưới đây dùng cú pháp hợp lệ trong **Java 17+**.

## 2. Phương thức `abstract`: hợp đồng chưa có cách triển khai

Phương thức interface không có thân được hiểu ngầm là **`public abstract`**. Chẳng hạn, `boolean pay(long amount);` dưới đây là hợp đồng công khai dù không viết hai modifier:

~~~java
interface PaymentMethod {
    boolean pay(long amount);
}

final class CardPayment implements PaymentMethod {
    @Override
    public boolean pay(long amount) {
        return amount > 0; // Minh họa một quy tắc kiểm tra tối giản
    }
}
~~~

Đoạn này minh họa khai báo hợp lệ, chưa có `main`. Một class cụ thể phải đáp ứng các phương thức trừu tượng còn thiếu bằng triển khai tương thích có quyền truy cập **`public`**; class `abstract` có thể hoãn việc này. Phương thức `abstract` không có thân và không được kết hợp `private`, `protected`, `final` hay `static`.

Phương thức công khai đã được kế thừa từ `Object`, ví dụ `equals(Object)`, có thể đáp ứng một khai báo abstract tương ứng trong interface. Để kiểm chứng modifier bằng reflection và phân biệt với abstract method của class, xem bài **Phương thức abstract ngầm định public**.
## 3. Phương thức `default`: triển khai mặc định cho đối tượng

`default` cho phép interface khai báo **phương thức instance có thân**. Lớp triển khai có thể sử dụng hành vi có sẵn hoặc override nếu cần:

~~~java
interface Named {
    String name();

    default String displayName() {
        return "Tên: " + name();
    }
}

class User implements Named {
    @Override
    public String name() {
        return "Lan";
    }
}
~~~

Ở đây `name()` là `public abstract` ngầm định. `displayName()` là `public default` ngầm định về phạm vi truy cập; nó gọi `name()` và nhận được triển khai của đối tượng thực tế. Đối tượng `new User()` có thể gọi `displayName()` dù lớp `User` không tự viết phương thức này.

Quy tắc quan trọng:

1. Phương thức `default` **phải có thân**, được viết với từ khóa `default` và có quyền truy cập `public` (ngầm định hoặc tường minh).
2. Đây là **phương thức instance**; lời gọi được thực hiện qua đối tượng như `user.displayName()`, có thể tham gia đa hình và được lớp triển khai override.
3. Khi lớp override một phương thức `default`, phương thức đó vẫn phải là `public`. Nếu lớp triển khai trực tiếp interface và muốn gọi bản mặc định từ phương thức override, có thể dùng `InterfaceName.super.method()` theo các điều kiện cú pháp Java.
4. `default` không được đi cùng `abstract`, `static` hoặc `private` trên cùng phương thức.
5. Interface không được cung cấp phương thức `default` override những phương thức `public` của `Object`, chẳng hạn `default String toString() { ... }`. Lớp thực hiện vẫn có thể tự override `toString()` như bình thường.

Một ứng dụng là **bổ sung hành vi mặc định khi phát triển API interface** mà không bắt tất cả lớp hiện tại phải khai báo ngay phương thức mới. Tuy nhiên, việc thêm `default` vẫn có thể tạo xung đột với những interface khác mà một lớp đang thực hiện; đó không phải bảo đảm tương thích trong mọi trường hợp.

## 4. Phương thức `static`: tiện ích gắn với chính interface

Phương thức `static` có thân và **không phụ thuộc vào một đối tượng triển khai**:

~~~java
interface TextRules {
    static boolean hasText(String input) {
        return input != null && !input.isBlank();
    }
}
~~~

Gọi đúng:

~~~java
boolean result = TextRules.hasText("Java");
~~~

`result` có giá trị `true`. Với phương thức `static` công khai trong interface, tên interface là điểm truy cập rõ ràng. Nếu có biến kiểu `TextRules`, gọi `variable.hasText(...)` sẽ không hợp lệ; một lớp `implements TextRules` cũng **không kế thừa** phương thức `hasText` để gọi như phương thức static của chính lớp đó. Tương tự, một subinterface không được thừa kế phương thức static từ superinterface theo cách kế thừa phương thức instance.

Một phương thức `static` của interface:

- Có thể gọi trực tiếp các phương thức static khác trong interface, kể cả `private static`.
- Không thể gọi trực tiếp phương thức instance `default` hoặc `private` instance khi không có đối tượng thích hợp.
- Không được override theo nghĩa đa hình của phương thức instance; việc trùng tên với phương thức static khác không biến phương thức đó thành `default` hoặc `abstract`.
- Khi không ghi modifier truy cập, nó là `public static`; muốn chỉ dùng nội bộ thì ghi **`private static`** (Java 9+).

Dùng `static` khi hàm liên quan chặt chẽ đến hợp đồng interface, chẳng hạn thao tác tạo đối tượng, kiểm tra đối số hoặc chuyển đổi độc lập với trạng thái instance.

## 5. Phương thức `private` và `private static`: mã hỗ trợ nội bộ

Java 9 cho phép interface ẩn những phương thức có thân, tránh phải lặp logic trong nhiều `default`/`static` methods:

~~~java
interface Formatter {
    default String emphasize(String text) {
        return wrap(text);
    }

    default String label(String text) {
        return "Nhãn " + wrap(text);
    }

    static String normalize(String text) {
        return trim(text).toLowerCase(java.util.Locale.ROOT);
    }

    private String wrap(String text) {
        return "[" + trim(text) + "]";
    }

    private static String trim(String text) {
        return text.trim();
    }
}
~~~

Phân biệt hai dạng:

- `private String wrap(String text)` là **phương thức instance**. Nó chỉ được gọi từ mã trong interface với ngữ cảnh instance thích hợp; ví dụ, cả `emphasize` và `label` gọi được nó.
- `private static String trim(String text)` là **phương thức static**. Cả phương thức instance `wrap` lẫn phương thức static `normalize` đều có thể gọi nó.
- Phương thức `private` và `private static` **phải có thân**, không thể đồng thời là `abstract` hoặc `default`; chúng không phải thành viên API có thể gọi từ lớp triển khai.
- Lớp triển khai **không kế thừa** và không được override phương thức `private` của interface. Viết cùng tên trong lớp triển khai là một phương thức khác, không phải ghi đè.
- Phương thức `private` interface không làm tăng số phương thức trừu tượng phải triển khai, và không tham gia hợp đồng triển khai của `implements`.

Nếu chỉ có một đoạn helper duy nhất và không cần ẩn phần triển khai, đôi khi viết logic ngay trong `default`/`static` sẽ đơn giản hơn. Dùng `private` khi việc đặt tên một bước xử lý hoặc tái sử dụng logic thực sự làm mã dễ hiểu hơn.

## 6. Ví dụ tổng hợp đầy đủ: đủ bốn loại phương thức

Trong ví dụ sau, `Notifier` có phương thức `abstract`, `default`, `static`, `private` instance và `private static`. Một lớp sử dụng bản mặc định, một lớp chủ động override bản mặc định.

Lưu **toàn bộ** mã vào tệp **`Demo.java`**:

~~~java
import java.util.Locale;

interface Notifier {
    // Ngầm định public abstract.
    String recipient();

    // Ngầm định public; có thân và là phương thức instance.
    default String message() {
        return decorate(recipient());
    }

    // Ngầm định public; gọi qua Notifier.supports(...).
    static boolean supports(String languageCode) {
        return normalize(languageCode).equals("vi");
    }

    // Java 9+: chỉ dùng trong chính interface.
    private String decorate(String rawName) {
        return "Xin chào " + rawName.trim() + "!";
    }

    // Java 9+: helper dùng được từ static và instance methods.
    private static String normalize(String code) {
        return code.trim().toLowerCase(Locale.ROOT);
    }
}

final class StandardNotifier implements Notifier {
    private final String name;

    StandardNotifier(String name) {
        this.name = name;
    }

    @Override
    public String recipient() {
        return name;
    }
}

final class CustomNotifier implements Notifier {
    @Override
    public String recipient() {
        return "Mai";
    }

    @Override
    public String message() {
        return "Thông báo dành cho " + recipient();
    }
}

public class Demo {
    public static void main(String[] args) {
        Notifier standard = new StandardNotifier(" Lan ");
        Notifier custom = new CustomNotifier();

        System.out.println(standard.recipient().trim());
        System.out.println(standard.message());
        System.out.println(custom.message());
        System.out.println(Notifier.supports(" VI "));
    }
}
~~~

Biên dịch/chạy bằng Java 17+:

~~~bash
javac Demo.java
java Demo
~~~

**Kết quả stdout chính xác:**

~~~text
Lan
Xin chào Lan!
Thông báo dành cho Mai
true
~~~

Phân tích dòng gọi:

1. `standard.recipient()` gọi triển khai **abstract contract** của `StandardNotifier`; `trim()` trong lệnh in loại khoảng trắng đầu/cuối nên in `Lan`.
2. `standard.message()` sử dụng phương thức **default** từ `Notifier`. Bên trong `message()` gọi `decorate(...)` **private instance**; phương thức đó lấy `recipient()` của đối tượng thực và loại khoảng trắng.
3. `custom.message()` gọi bản **override** của `CustomNotifier` nên không sử dụng nội dung `message()` mặc định.
4. `Notifier.supports(" VI ")` gọi phương thức **static công khai** qua tên interface. Nó gọi `normalize(...)` **private static**: bỏ khoảng trắng, chuyển chữ thường theo `Locale.ROOT`, sau đó so với `"vi"` nên trả về `true`.

Các lời gọi sau **không hợp lệ** bên ngoài `Notifier` (minh họa lỗi, không đưa vào `Demo.java`):

~~~java
// standard.supports("vi");        // Lỗi: static method không gọi qua instance
// StandardNotifier.supports("vi"); // Lỗi: static method interface không kế thừa vào lớp
// standard.decorate("Lan");       // Lỗi: private interface method không truy cập được
// Notifier.normalize("vi");       // Lỗi: private static method không truy cập được
~~~

## 7. Kế thừa, ghi đè và xung đột `default` methods

Khi nhiều interface có phương thức cùng chữ ký, hiểu quy tắc chọn triển khai là rất quan trọng:

1. **Phương thức instance cụ thể từ lớp cha được ưu tiên** so với triển khai `default` tương ứng của interface, nếu chữ ký và kiểu trả về tương thích.
2. Trong hệ interface có quan hệ kế thừa, triển khai `default` từ interface **cụ thể hơn** thường được ưu tiên so với `default` ở superinterface theo quy tắc Java.
3. Nếu một lớp nhận **hai triển khai `default` không liên quan** cùng chữ ký từ hai interface, nó phải giải quyết xung đột bằng cách override rõ ràng.
4. Phương thức `abstract` vẫn quy định hợp đồng; một `default` phù hợp có thể đáp ứng hợp đồng đó trong những cấu trúc kế thừa hợp lệ.
5. `static` interface và `private` interface không phải đối tượng của quá trình override `default` theo đa hình.

Ví dụ xung đột `default`, lưu riêng trong **`ConflictDemo.java`**:

~~~java
interface Left {
    default String label() {
        return "L";
    }
}

interface Right {
    default String label() {
        return "R";
    }
}

final class Combined implements Left, Right {
    @Override
    public String label() {
        return Left.super.label() + "+" + Right.super.label();
    }
}

public class ConflictDemo {
    public static void main(String[] args) {
        System.out.println(new Combined().label());
    }
}
~~~

Chạy:

~~~bash
javac ConflictDemo.java
java ConflictDemo
~~~

Stdout:

~~~text
L+R
~~~

Nếu bỏ `Combined.label()`, mã sẽ không biên dịch vì lớp nhận hai phương thức `default` cùng chữ ký mà chưa chỉ ra cách giải quyết. Cú pháp `Left.super.label()` và `Right.super.label()` cho phép gọi các triển khai mặc định cụ thể trong ngữ cảnh kế thừa hợp lệ. Cũng có thể viết override mới hoàn toàn, không cần gọi một trong hai bản mặc định.

**Chú ý:** chỉ có phương thức cụ thể từ lớp cha là đủ để giải quyết ưu tiên theo quy tắc “class wins” thông thường. Nếu lớp cha để lại một phương thức trừu tượng cùng chữ ký hoặc các chữ ký/kiểu trả về không tương thích, có thể vẫn cần triển khai rõ ràng và xử lý lỗi theo quy tắc Java; đừng suy luận rằng mọi khai báo trong class tự động giải quyết mọi xung đột.

## 8. Lỗi phổ biến khi phân loại phương thức trong interface

| Viết sai hoặc hiểu sai | Nguyên nhân | Cách sửa |
|---|---|---|
| `interface A { void run() {} }` | Phương thức thiếu modifier loại có thân được hiểu là abstract. | Viết `void run();` hoặc `default void run() {}`. |
| `interface A { default void run(); }` | `default` phải có thân. | Thêm `{ ... }` hoặc khai báo abstract. |
| `interface A { private void helper(); }` | `private` interface phải có thân. | Viết `private void helper() { ... }`. |
| `interface A { static void work(); }` | `static` interface phải có thân. | Viết `static void work() { ... }`. |
| `new Notifier()` | Không thể khởi tạo trực tiếp interface. | Khởi tạo lớp triển khai, ví dụ `new StandardNotifier("Lan")`. |
| `StandardNotifier.supports("vi")` | Phương thức `static` của interface không được kế thừa vào class. | Gọi `Notifier.supports("vi")`. |
| Hai interface không liên quan có cùng `default void f()` mà lớp triển khai không override | Hai triển khai mặc định xung đột. | Override `public void f()` để giải quyết. |
| `default String toString() { ... }` | `default` không được override phương thức public của `Object`. | Để lớp triển khai tự override `toString()`. |

Các mẫu sai chỉ minh họa một lỗi, không phải tệp Java hoàn chỉnh. Bài **Giới hạn truy cập và modifier không hợp lệ** có ma trận riêng cho `private`, `protected`, `final` và các tổ hợp modifier bị cấm; bài **Phương thức abstract ngầm định public** đi sâu vào việc class triển khai giữ quyền `public`.
## 9. Cách chọn đúng loại phương thức

- Chọn **`abstract`** khi định nghĩa **hành vi bắt buộc** nhưng không có triển khai chung: ví dụ `save()`, `calculate()`, `validate()`.
- Chọn **`default`** khi có **hành vi instance dùng chung** cho các đối tượng triển khai và có thể cho phép lớp triển khai override. Cẩn trọng với xung đột khi interface được dùng chung hoặc kế thừa từ nhiều nhánh.
- Chọn **`static`** khi có **hàm công khai liên quan đến interface** nhưng không cần nhận đối tượng triển khai, ví dụ kiểm tra định dạng đầu vào hoặc factory method.
- Chọn **`private` instance** khi cần trích ra logic hỗ trợ cho các **`default` hoặc phương thức instance có thân** của cùng interface.
- Chọn **`private static`** khi helper không phụ thuộc vào đối tượng và cần dùng nội bộ, kể cả từ những phương thức `static` công khai.

Ghi nhớ sự khác nhau giữa **kế thừa** và **khả năng truy cập**: một phương thức `default` được lớp triển khai thừa hưởng dưới dạng hành vi instance; phương thức `static` công khai có thể được gọi từ mã bên ngoài nhưng qua **tên interface**, không được kế thừa vào lớp triển khai; phương thức `private` tồn tại chỉ để hỗ trợ việc triển khai bên trong interface.

Một interface được đánh dấu `@FunctionalInterface` vẫn có thể chứa `default`, `static` và `private` methods. Những phương thức có thân này **không tính là phương thức trừu tượng duy nhất** (single abstract method, SAM) của functional interface. Điều kiện chính của functional interface là chỉ có một hợp đồng phương thức trừu tượng phù hợp sau khi xét các quy tắc của Java.

### Tự kiểm tra

1. `void run();` trong interface có phạm vi gì? — **`public abstract` ngầm định**.
2. Lớp triển khai có bắt buộc viết `default void log()` không? — **Không**, nếu bản mặc định thỏa mãn và không có xung đột; vẫn có thể override.
3. `MyInterface.check()` và `object.check()`: dạng nào đúng khi `check` là `static` công khai của interface? — **`MyInterface.check()`**.
4. Một phương thức `private` của interface có thể bị lớp triển khai override không? — **Không**, vì nó không được kế thừa và chỉ truy cập được bên trong interface.
5. Khi nào dùng `private static` thay cho `private` instance? — Khi helper **không cần ngữ cảnh đối tượng**, nhất là khi phương thức `static` của interface cũng cần gọi helper đó.

**Điểm cốt lõi:** `abstract` = hợp đồng chưa có thân; `default` = triển khai instance có thể override; `static` = hành vi gắn với tên interface; `private`/`private static` = logic trợ giúp chỉ dùng nội bộ.
