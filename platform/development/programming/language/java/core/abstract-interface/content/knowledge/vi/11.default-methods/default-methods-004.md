# Ghi đè default method trong lớp triển khai Java

Lớp triển khai có thể dùng nguyên default method của interface hoặc override nó để cung cấp hành vi riêng. Override là một phương thức instance bình thường trong class; nó phải đáp ứng hợp đồng công khai của interface.

## 1. Dùng mặc định hoặc thay thế

```java
public class DefaultOverrideDemo {
    interface Messenger {
        default String send(String message) {
            return "Default: " + message;
        }

        default String channel() {
            return "unspecified";
        }
    }

    static final class BasicMessenger implements Messenger {
        // Dùng cả hai default method.
    }

    static final class EmailMessenger implements Messenger {
        @Override
        public String send(String message) {
            return "Email: " + message;
        }
    }

    public static void main(String[] args) {
        Messenger basic = new BasicMessenger();
        Messenger email = new EmailMessenger();

        System.out.println(basic.send("hello"));
        System.out.println(email.send("hello"));
        System.out.println(email.channel());
    }
}
```

Kết quả:

```text
Default: hello
Email: hello
unspecified
```

`BasicMessenger` kế thừa cả hai phương thức. `EmailMessenger` chỉ override `send`; `channel` vẫn đến từ interface. Tham chiếu có kiểu `Messenger` vẫn gọi override của đối tượng thực tế theo quy tắc đa hình.

## 2. Quy tắc khi override

| Thành phần | Yêu cầu |
| --- | --- |
| Tên và tham số | Phải có chữ ký override tương thích. `execute(int)` và `execute(long)` là hai chữ ký khác nhau. |
| Truy cập | Phải giữ `public` vì default method của interface là public. |
| Kiểu trả về | Giữ kiểu tương thích; với kiểu tham chiếu có thể dùng kiểu trả về đồng biến hợp lệ. |
| Checked exception | Không thêm checked exception rộng hơn hợp đồng của phương thức bị override cho phép. |
| `static` | Không thể dùng static method để override một default instance method. |
| `final` | Override trong class có thể là `final` để ngăn lớp con override tiếp, nếu cấu trúc class cho phép. |

Nên đặt `@Override` trên phương thức. Annotation không tạo ra đa hình, nhưng giúp trình biên dịch phát hiện ý định override sai chữ ký. Class không ghi từ khóa `default` trước phương thức override.

Ví dụ sau sai vì giảm quyền truy cập:

```java
interface Renderer {
    default String render() {
        return "default";
    }
}

class BrokenRenderer implements Renderer {
    @Override
    String render() { // Sai: package-private hẹp hơn public.
        return "hidden";
    }
}
```

Hãy viết `public String render()`. Tương tự, một phương thức cùng tên nhưng khác tham số chỉ là overload, không thay thế default method gốc.

## 3. Phương thức lớp cha và default method

Khi class hoặc superclass có một phương thức instance concrete phù hợp, phương thức từ class được ưu tiên so với default method cùng chữ ký. Đây thường được gọi là quy tắc *class wins*.

```java
interface Named {
    default String name() {
        return "interface";
    }
}

class BaseNamed {
    public String name() {
        return "class";
    }
}

class UserNamed extends BaseNamed implements Named {
}
```

`new UserNamed().name()` trả về `class`. Kiểu khai báo của biến không làm default method thắng phương thức được kế thừa từ class. Trường hợp class có phương thức abstract hoặc chữ ký/truy cập không tương thích cần được đánh giá theo quy tắc override của Java, không thể kết luận chỉ từ việc hai tên giống nhau.

## 4. Khi nào override?

Override khi mặc định không đáp ứng nghiệp vụ của lớp, khi cần bổ sung xử lý trước/sau, hoặc khi cần giải quyết xung đột kế thừa. Nếu chỉ muốn gọi lại default method rồi trả nguyên kết quả, override thường không đem lại giá trị. Cú pháp gọi trực tiếp một default implementation cụ thể có các điều kiện riêng và được giải thích ở bài về `InterfaceName.super`.

**Ghi nhớ:** dùng `@Override public` với chữ ký tương thích. Một lớp có thể override một số default method và kế thừa các phương thức còn lại; phương thức instance của class có ưu tiên trong việc chọn implementation theo quy tắc kế thừa Java.