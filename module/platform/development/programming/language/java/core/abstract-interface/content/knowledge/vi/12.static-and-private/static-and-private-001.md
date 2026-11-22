# Phương thức `static` trong interface từ Java 8

Từ **Java 8**, interface có thể khai báo phương thức `static` có thân hàm. Phương thức này thuộc về chính interface, phù hợp với thao tác gắn với kiểu dữ liệu như kiểm tra đầu vào, chuẩn hóa dữ liệu hoặc tạo một implementation. Nó không mô tả hành vi cần được lựa chọn theo từng đối tượng.

## 1. Phân biệt ba loại phương thức

| Loại | Vai trò | Cách gọi thường dùng | Có thể override như hành vi instance? |
|---|---|---|---|
| Abstract instance method | Khai báo việc đối tượng phải làm | `sender.send(message)` | Có; lớp concrete phải cung cấp implementation phù hợp |
| `default` instance method | Cung cấp hành vi mặc định cho đối tượng | `sender.description()` | Có |
| `static` method | Cung cấp thao tác thuộc về interface | `MessageSender.normalize(text)` | Không |

Ví dụ, `send` là hành vi của từng sender, còn `normalize` là quy tắc xử lý chuỗi có thể dùng chung mà không cần một đối tượng `MessageSender`.

## 2. Cú pháp và các quy tắc chính

~~~java
interface MessageSender {
    void send(String message);

    static String normalize(String message) {
        if (message == null) {
            return "";
        }
        return message.trim().toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Phương thức `static` trong interface phải có thân hàm. Nếu không ghi access modifier, nó là `public`; có thể viết rõ `public static` để nhấn mạnh API công khai.

Một phương thức không thể đồng thời là `static` và `abstract` hoặc `default`. Phương thức `static` không có `this` đại diện cho instance hiện tại, vì vậy không thể gọi trực tiếp một instance method nếu chưa có đối tượng nhận lời gọi.

Phương thức `static` của interface được gọi bằng tên interface đã khai báo nó. Quy tắc này khác với cách gọi instance method qua đối tượng; bài kế tiếp đi sâu vào cách viết lời gọi đúng.

## 3. Ví dụ hoàn chỉnh

Lưu đoạn sau thành `Main.java`. Ví dụ tương thích Java 8.

~~~java
interface MessageSender {
    void send(String message);

    static String normalize(String message) {
        if (message == null) {
            return "";
        }
        return message.trim().toUpperCase(java.util.Locale.ROOT);
    }
}

final class ConsoleSender implements MessageSender {
    @Override
    public void send(String message) {
        System.out.println("Sent: " + MessageSender.normalize(message));
    }
}

public class Main {
    public static void main(String[] args) {
        MessageSender sender = new ConsoleSender();
        sender.send("  hello Java  ");
        System.out.println("Normalized: " + MessageSender.normalize(" java "));
    }
}
~~~

Biên dịch và chạy trên JDK 9 trở lên:

~~~bash
javac -encoding UTF-8 --release 8 Main.java
java Main
~~~

Stdout:

~~~text
Sent: HELLO JAVA
Normalized: JAVA
~~~

Lời gọi `sender.send(...)` được phân giải theo đối tượng thực tế và gọi implementation của `ConsoleSender`. Lời gọi `MessageSender.normalize(...)` được xác định theo interface ghi trước dấu chấm; nó không cần tạo sender và không tham gia đa hình instance.

## 4. Phương thức static trong interface generic

Static method không gắn với một đối tượng `Box<T>` cụ thể, nên không thể dùng trực tiếp type parameter `T` của interface. Nếu chính phương thức cần generic, hãy khai báo type parameter riêng:

~~~java
interface Box<T> {
    T get();

    static <U> U identity(U value) {
        return value;
    }
}
~~~

`Box.identity("Java")` suy luận `U` là `String`, còn `Box.identity(42)` suy luận `U` là `Integer`. Type parameter `U` thuộc về method; nó không phụ thuộc vào `T` của một instance `Box<T>`.

## 5. Khi nào nên dùng?

Cân nhắc `static` khi thao tác có ý nghĩa trực tiếp với interface và không cần trạng thái của đối tượng, ví dụ kiểm tra dữ liệu hoặc factory method. Nếu mỗi implementation cần cung cấp hành vi riêng, hãy dùng abstract instance method; nếu cần hành vi mặc định có thể thay đổi theo đối tượng, cân nhắc `default`.

Không đưa mọi tiện ích vào interface một cách máy móc. Nếu logic không thuộc hợp đồng của interface, một utility class có thể diễn đạt trách nhiệm rõ hơn.

**Tự kiểm tra**

- Phương thức `static` trong interface có bắt buộc có thân hàm không? **Có.**
- Có thể gọi nó qua biến instance để nhận dispatch đa hình không? **Không.**
- Nếu một static method cần generic riêng, dùng type parameter của interface hay khai báo type parameter của method? **Khai báo type parameter của method.**