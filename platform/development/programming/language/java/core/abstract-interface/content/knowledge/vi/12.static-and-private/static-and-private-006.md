# Private static method và giới hạn truy cập thành viên instance

Hai từ khóa `private` và `static` trả lời hai câu hỏi khác nhau. `private` quyết định nơi nào có quyền truy cập; `static` cho biết method thuộc về kiểu khai báo và không có instance hiện tại ngầm định. Vì thế, `private static` thường phù hợp với helper nội bộ chỉ cần tham số đầu vào.

## 1. Private static helper trong interface từ Java 9

Trong interface, `private static` gom xử lý nội bộ dùng được từ cả `default` method lẫn `static` method của chính interface. Nó không cần đối tượng nhận lời gọi nên thích hợp cho chuẩn hóa tham số hoặc kiểm tra đầu vào. Khác với một phương thức instance, nó không thể gọi trực tiếp `prefix()` hoặc dùng `this` vì không có đối tượng hiện tại.

Lưu chương trình sau thành `InterfacePrivateStaticDemo.java` và chạy với Java 9 trở lên:

~~~java
import java.util.Locale;

interface DisplayRule {
    String prefix();

    default String label(String value) {
        return prefix() + ": " + clean(value);
    }

    static String normalize(String value) {
        return clean(value);
    }

    static String labelFor(DisplayRule rule, String value) {
        return rule.prefix() + ": " + clean(value);
    }

    private static String clean(String value) {
        return value == null ? "(empty)" : value.trim().toUpperCase(Locale.ROOT);
    }
}

final class BasicDisplay implements DisplayRule {
    @Override
    public String prefix() {
        return "VIEW";
    }
}

public class InterfacePrivateStaticDemo {
    public static void main(String[] args) {
        DisplayRule rule = new BasicDisplay();
        System.out.println(rule.label(" java "));
        System.out.println(DisplayRule.normalize(" private "));
        System.out.println(DisplayRule.labelFor(rule, " api "));
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 9 InterfacePrivateStaticDemo.java
java InterfacePrivateStaticDemo
~~~

Stdout:

~~~text
VIEW: JAVA
PRIVATE
VIEW: API
~~~

`label` là instance default method nên gọi được `prefix()` trên đối tượng thực tế. `normalize` và `labelFor` là các static method công khai do `DisplayRule` khai báo; chúng đều gọi private static `clean`. Trong `labelFor`, biểu thức `rule.prefix()` hợp lệ vì `rule` cung cấp **receiver rõ ràng**, còn `prefix()` đứng một mình trong static method sẽ không biên dịch. Chính hai điều kiện độc lập — có receiver và có quyền truy cập — quyết định việc tham chiếu thành viên instance có hợp lệ hay không. Caller bên ngoài không thể gọi `DisplayRule.clean(...)` vì `clean` là private.

## 2. Ví dụ bổ trợ: helper tĩnh trong class

Lưu chương trình thành `PrivateStaticDemo.java`:

~~~java
import java.util.Locale;

public class PrivateStaticDemo {
    public static void main(String[] args) {
        Ticket first = new Ticket("  t-01  ");
        Ticket second = new Ticket("t-02");

        System.out.println(first.code() + " / " + second.code());
        System.out.println("Created: " + Ticket.createdCount());
    }
}

final class Ticket {
    private static int created;
    private final String code;

    Ticket(String rawCode) {
        this.code = normalize(rawCode);
        created++;
    }

    private static String normalize(String rawCode) {
        if (rawCode == null || rawCode.trim().isEmpty()) {
            throw new IllegalArgumentException("code is required");
        }
        return rawCode.trim().toUpperCase(Locale.ROOT);
    }

    String code() {
        return code;
    }

    static int createdCount() {
        return created;
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PrivateStaticDemo.java
java PrivateStaticDemo
~~~

Stdout:

~~~text
T-01 / T-02
Created: 2
~~~

Constructor instance gọi được `normalize` vì nó nằm trong chính class `Ticket`. Helper chỉ cần chuỗi được truyền vào, nên không cần `this`. Trường `code` thuộc từng ticket, còn `created` là một biến static được chia sẻ bởi các đối tượng của class đó.

`Ticket.normalize("abc")` không được gọi từ `PrivateStaticDemo` vì helper là private. Quyền truy cập được kiểm tra theo nơi code xuất hiện; dùng cú pháp tên lớp bên trong chính `Ticket` vẫn hợp lệ.

Lưu ý, `created++` chỉ minh họa trạng thái static dùng chung; nó không phải bộ đếm an toàn khi nhiều thread cùng tăng giá trị.

## 3. Static context không có instance hiện tại

Một static method không có tham chiếu `this` ngầm định. Nếu muốn đọc số dư của một `Wallet`, Java cần biết đối tượng nào được đọc.

~~~java
class Wallet {
    private int balance;

    private int getBalance() {
        return balance;
    }

    private static int invalid() {
        // return balance;       // Lỗi: thiếu object nhận.
        // return this.balance;  // Lỗi: không có this trong static context.
        // return getBalance();  // Lỗi: thiếu object nhận.
        return 0;
    }

    private static int readBalance(Wallet wallet) {
        return wallet.balance;
    }
}
~~~

Ba dòng bị comment là các ví dụ cố ý sai. `readBalance` hợp lệ vì `wallet` chỉ rõ đối tượng nhận lời gọi. Code đó nằm trong chính class `Wallet` nên cũng có quyền truy cập trường private `balance`.

Hai điều kiện cần được kiểm tra độc lập:

- **Có receiver cụ thể không?** `wallet.balance` có; `balance` trần trong static method thì không.
- **Có quyền truy cập không?** Một tham chiếu đối tượng không tự cấp quyền đọc private field cho class không liên quan.

Vì vậy, nói “static method không bao giờ truy cập được instance member” là không chính xác. Nó không có instance hiện tại tự động, nhưng có thể xử lý một đối tượng được truyền vào hoặc được lấy từ một nguồn tham chiếu hợp lệ.

Nested class có thể truy cập private member của outer class theo quy tắc Java, nhưng static nested class không có `Outer.this`; nó vẫn cần một tham chiếu object cụ thể để đọc instance state.

## 4. Private static không phải private instance method

| Thành viên | Có `this` ngầm định? | Ví dụ phù hợp |
|---|---|---|
| `private void update() { ... }` | Có | Cập nhật trạng thái của đối tượng hiện tại |
| `private static String normalize(String value) { ... }` | Không | Chuẩn hóa tham số, kiểm tra dữ liệu, parse |
| `private static int total(Counter a, Counter b) { ... }` | Không; nhưng có receiver rõ ràng qua `a` và `b` | Tính toán dựa trên nhiều đối tượng được truyền vào |

Ví dụ, một helper static trong chính class có thể đọc private field của các instance được truyền vào:

~~~java
final class Counter {
    private final int value;

    Counter(int value) {
        this.value = value;
    }

    private static int total(Counter left, Counter right) {
        return left.value + right.value;
    }
}
~~~

`left.value` và `right.value` hợp lệ vì method có tham chiếu đến hai đối tượng cụ thể và đang ở trong class khai báo field. Nếu code nằm ngoài `Counter`, có tham chiếu `Counter` thôi vẫn không đủ quyền đọc `value` trực tiếp.

## 5. Kế thừa, hiding và interface

Private static method của class cha không tạo ra điểm override cho class con. Nếu class con tự khai báo một method cùng tên, đó là method riêng của class con. Với static method của class có thể truy cập và được kế thừa, class con có thể khai báo method tương ứng để *hide* method cha; cả hai vẫn không tham gia dynamic dispatch qua instance.

Trong interface, private static method cũng là helper nội bộ. Java hỗ trợ `private static` method trong interface từ **Java 9**; Java 8 chưa có private interface method. Helper đó phải có body, chỉ được gọi từ code có quyền truy cập bên trong interface khai báo nó, và không phải API cho class triển khai gọi trực tiếp.

Không nhầm private với static: một method có thể là private instance hoặc private static. Cũng không nhầm static với public: access modifier và ngữ cảnh instance là hai trục riêng.

## 6. Chọn đúng dạng method

- Dùng `private static` khi xử lý không cần trạng thái của `this` và các đầu vào cần thiết có thể truyền qua tham số.
- Dùng private instance method khi logic cần trạng thái của đối tượng hiện tại.
- Nếu một class khác cần gọi thao tác, thiết kế API công khai có chủ đích; đừng nới quyền private chỉ để tránh lỗi compiler.
- Nếu hành vi cần được subclass thay đổi, hãy tạo extension point bằng instance method phù hợp. Static/private helper không phải hook đa hình.
- Trạng thái mutable trong static field được chia sẻ; cân nhắc đồng bộ hoặc atomic nếu nhiều thread có thể cập nhật đồng thời.

**Tự kiểm tra**

1. Vì sao constructor gọi được private static `normalize`? Vì code constructor nằm trong class khai báo helper.
2. Vì sao `return balance` sai trong static method nhưng `return wallet.balance` có thể hợp lệ? Cách thứ hai chỉ rõ object nhận và quyền private được kiểm tra riêng.
3. Class con có override private static method của cha không? Không; method private không được kế thừa để override, và static method không phải instance override.