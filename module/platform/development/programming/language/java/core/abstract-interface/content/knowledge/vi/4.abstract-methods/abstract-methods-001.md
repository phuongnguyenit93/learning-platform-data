# Cú pháp khai báo phương thức `abstract` và dấu chấm phẩy

Phương thức `abstract` công bố **một hành vi cần được cung cấp phần triển khai** nhưng không chứa thân phương thức tại nơi khai báo. Trong một lớp, điểm nhận diện cú pháp là từ khóa `abstract` và dấu chấm phẩy `;` ở cuối khai báo.

## 1. Mẫu khai báo trong class

```java
[access-modifier] abstract [TypeParameters] ReturnType methodName(Parameters)
        [throws ExceptionTypes];
```

Dấu ngoặc vuông trong mẫu chỉ đánh dấu phần tùy chọn; không gõ chúng vào mã Java. `TypeParameters` là phần khai báo generic như `<T>`, `Parameters` có thể rỗng, còn `throws` chỉ xuất hiện khi hợp đồng cần công bố ngoại lệ. Ví dụ:

```java
abstract class Shape {
    public abstract double area();
    protected abstract void describe(String label);
}
```

`area()` trả về `double`, còn `describe(String)` nhận một tham số và trả về `void`. Cả hai kết thúc bằng `;` và không có `{ ... }`. Vì `Shape` trực tiếp khai báo phương thức abstract, `Shape` cũng phải là `abstract class`.

## 2. Vì sao khai báo kết thúc bằng `;`?

Dấu `;` kết thúc chữ ký mà không khai báo phần thân:

```java
abstract class Worker {
    abstract void work(); // Hợp lệ: chưa có phần triển khai
}

class ConcreteWorker {
    void work() { }       // Hợp lệ: thân rỗng vẫn là một thân cụ thể
}
```

Hai cách viết mang ý nghĩa khác nhau. `abstract void work();` yêu cầu lớp concrete cung cấp một implementation hợp lệ; `void work() { }` đã có implementation, dù thân chưa làm gì.

Không được viết:

```java
abstract class InvalidWorker {
    abstract void work() { } // Lỗi: abstract method không được có thân
}
```

Muốn khai báo hợp đồng, bỏ `{ ... }` và dùng `;`. Muốn triển khai hành vi tại lớp hiện tại, bỏ `abstract` và viết thân phương thức.

## 3. Vị trí của generic, tham số và `throws`

Generic method đặt danh sách kiểu trước kiểu trả về. Nếu có `throws`, dấu `;` vẫn nằm sau toàn bộ mệnh đề đó:

```java
abstract class Parser {
    protected abstract <T> T parse(
            String source, Class<T> targetType)
            throws java.text.ParseException;
}
```

Ở đây `<T>` là tham số kiểu của phương thức, `String` và `Class<T>` là các kiểu tham số, `T` là kiểu trả về, còn `ParseException` là ngoại lệ được công bố. Khai báo không chứa mã phân tích chuỗi; lớp triển khai sẽ cung cấp phần thân. Các quy tắc chi tiết về tương thích tham số, kiểu trả về và checked exception khi override thuộc phạm vi của bài học về hợp đồng chữ ký.

## 4. Cú pháp tương ứng trong interface

Phương thức instance thông thường không có thân trong interface mặc định là `public abstract`; có thể lược bỏ cả hai từ khóa:

```java
interface Sender {
    void send(String message); // Tương đương public abstract
}
```

Khi một lớp triển khai `Sender`, phương thức `send` phải là `public`. Đừng suy luận rằng mọi phương thức interface đều abstract: `default`, `static` và `private` là các dạng phương thức khác và phải có thân theo quy tắc của chúng.

```java
interface MessageSender {
    void send(String message);

    default void sendWelcome() {
        send("Welcome");
    }

    static String protocol() {
        return "v1";
    }

    private String normalize(String message) {
        return message.strip();
    }
}
```

`send` là hợp đồng abstract; `sendWelcome` có triển khai mặc định; `protocol` thuộc về interface; `normalize` là helper nội bộ có thân. Ví dụ này minh họa cú pháp interface, không phải một ứng dụng có `main`.

## 5. Ví dụ Java 17+ chạy được

Lưu đoạn mã dưới đây vào `AbstractMethodSyntaxDemo.java`:

```java
abstract class MessageFormatter {
    protected abstract String format(String message);

    public String show(String message) {
        return format(message);
    }
}

final class UppercaseFormatter extends MessageFormatter {
    @Override
    protected String format(String message) {
        return message.toUpperCase(java.util.Locale.ROOT);
    }
}

public class AbstractMethodSyntaxDemo {
    public static void main(String[] args) {
        MessageFormatter formatter = new UppercaseFormatter();
        System.out.println(formatter.show("hello java"));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac AbstractMethodSyntaxDemo.java
java AbstractMethodSyntaxDemo
```

Kết quả:

```text
HELLO JAVA
```

`MessageFormatter` khai báo hợp đồng `format`; `show` đã có thân và gọi phương thức đó. `UppercaseFormatter` cung cấp phần triển khai. Lời gọi qua biến kiểu `MessageFormatter` vẫn chạy implementation của đối tượng thực tế `UppercaseFormatter`.

## 6. Lỗi cú pháp thường gặp

| Khai báo | Kết quả | Cách sửa |
|---|---|---|
| `abstract void run()` trong class | Lỗi nếu thiếu dấu kết thúc khai báo | Viết `abstract void run();` |
| `abstract void run() { }` | Lỗi vì abstract method có thân | Bỏ thân hoặc bỏ `abstract` |
| `class A { abstract void run(); }` | Lỗi vì class trực tiếp khai báo abstract method nhưng không abstract | Khai báo `abstract class A` hoặc cung cấp thân cụ thể |
| `class A { void run(); }` | Lỗi vì phương thức concrete trong class cần thân | Viết `void run() { ... }` hoặc đổi thiết kế thành abstract class |
| Lớp implement interface bằng `void send(...)` không có `public` | Lỗi nếu method đang implement public interface method | Khai báo `public void send(...)` |

Một checklist nhanh khi đọc khai báo: xác định kiểu chứa là `class` hay `interface`; kiểm tra từ khóa `abstract`; tìm dấu `;` cuối khai báo; xác nhận không có thân `{ ... }`; sau đó kiểm tra lớp concrete có implementation hợp lệ. Những tổ hợp modifier mâu thuẫn như `private abstract`, `static abstract` và `final abstract` được giải thích riêng trong các bài về modifier.
