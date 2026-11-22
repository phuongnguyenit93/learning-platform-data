# Gọi static method qua đúng tên interface

Khi một `static method` được khai báo trong interface, tên interface đó là chủ thể của lời gọi. Ví dụ, nếu `hasText` được khai báo trong `TextRules`, cách gọi rõ ràng là:

~~~java
TextRules.hasText("Java");
~~~

Đừng suy ra nơi khai báo method từ kiểu của biến đang cầm hoặc từ class có `implements` interface đó. Lời gọi static được xác định theo tên kiểu ghi trong biểu thức, không theo runtime class của đối tượng.

## 1. Ví dụ chạy được

Lưu toàn bộ mã sau thành `InterfaceStaticDemo.java`:

~~~java
interface TextRules {
    static boolean hasText(String value) {
        return value != null && !value.trim().isEmpty();
    }

    default boolean accepts(String value) {
        return TextRules.hasText(value);
    }
}

final class BasicRules implements TextRules {
}

public class InterfaceStaticDemo {
    public static void main(String[] args) {
        System.out.println(TextRules.hasText("Java"));
        System.out.println(TextRules.hasText("   "));

        TextRules rules = new BasicRules();
        System.out.println(rules.accepts(" Java "));

        java.util.function.Predicate<String> check = TextRules::hasText;
        System.out.println(check.test("API"));
    }
}
~~~

Biên dịch và chạy trên JDK 8 trở lên:

~~~bash
javac -encoding UTF-8 --release 8 InterfaceStaticDemo.java
java InterfaceStaticDemo
~~~

Stdout:

~~~text
true
false
true
true
~~~

`TextRules.hasText(...)` là lời gọi static. Ngược lại, `rules.accepts(...)` là lời gọi instance đến một default method. Bên trong `accepts`, mã vẫn gọi helper static bằng `TextRules.hasText(value)`.

`TextRules::hasText` là method reference đến static method được interface khai báo. Nó có thể được truyền vào API nhận functional interface như `Predicate<String>`.

## 2. Những lời gọi không hợp lệ

Trong ví dụ trên, hai dòng sau cố ý được để thành comment vì chúng gây lỗi biên dịch nếu bỏ comment:

~~~java
// BasicRules.hasText("Java"); // BasicRules không kế thừa static method của TextRules.
// rules.hasText("Java");      // Static interface method không phải instance method.
~~~

`implements TextRules` chỉ kết nối class với hợp đồng instance của interface; nó không đưa các static method của interface thành thành viên kế thừa của class. Nếu `BasicRules` tự khai báo một static method cùng tên, đó là method của chính `BasicRules`, không phải override của `TextRules.hasText`.

## 3. Static import và lựa chọn API

Trong một tệp khác thuộc package phù hợp, Java cho phép static import một phương thức công khai:

~~~java
import static com.example.rules.TextRules.hasText;

class Caller {
    boolean check() {
        return hasText("Java");
    }
}
~~~

Ví dụ import này minh họa cú pháp; package phải khớp với nơi `TextRules` thực sự được khai báo. Static import chỉ rút gọn cách viết. Nó không thay đổi chủ sở hữu method, quyền truy cập hay quy tắc dispatch.

Nếu muốn một thao tác là hành vi có thể tùy biến theo implementation, hãy khai báo abstract/default instance method và gọi qua object. Đừng dùng static method rồi kỳ vọng class triển khai sẽ override nó.

**Checklist trước khi gọi**

1. Xác định interface thực sự khai báo method.
2. Dùng `InterfaceName.method(...)` hoặc method reference `InterfaceName::method`.
3. Nếu cần gọi qua đối tượng và có đa hình, kiểm tra xem method có phải instance method hay không.
4. Nếu compiler báo không tìm thấy method trên class triển khai hoặc interface con, quay lại kiểu khai báo gốc để xác định owner.