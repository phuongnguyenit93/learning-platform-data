# Factory tạo lớp cụ thể nhưng trả về kiểu trừu tượng trong Java

## Mục tiêu

Hiểu vì sao factory có thể gọi constructor của một lớp cụ thể nhưng khai báo kiểu trả về là `interface` hoặc `abstract class`; phân biệt kiểu tham chiếu và kiểu đối tượng lúc chạy; tự viết, sử dụng, kiểm thử và mở rộng một factory đơn giản trong Java 17+.

## 1. Bản chất: đối tượng cụ thể, hợp đồng trừu tượng

Trong Java, `interface` định nghĩa tập hành vi các lớp triển khai phải cung cấp. `abstract class` có thể định nghĩa hành vi chung, trạng thái và các phương thức abstract cho lớp con. Không thể khởi tạo trực tiếp interface hay abstract class bằng `new`; ta chỉ tạo đối tượng của **lớp cụ thể**.

Một đối tượng của lớp triển khai interface hoặc kế thừa abstract class có thể được tham chiếu bằng **kiểu trừu tượng tương ứng**:

```java
MessageSender sender = MessageSenderFactory.create("email");
sender.send("an@example.com", "Xin chào");
```

Đoạn trên minh họa cách sử dụng; định nghĩa đầy đủ của các lớp nằm ở mục 3. Factory có thể gọi `new EmailSender()` bên trong nhưng công bố chữ ký `static MessageSender create(String channel)`. Sau khi gán, `sender` là **biến kiểu `MessageSender`** chứa tham chiếu đến **đối tượng thực tế kiểu `EmailSender`**. Đối tượng không bị biến đổi thành interface.

Đây là upcasting hợp lệ: Java cho phép dùng đối tượng lớp con ở vị trí yêu cầu lớp cha/interface mà nó đáp ứng. Khi gọi `sender.send(...)`, Java chọn triển khai của lớp thực tế lúc chạy (**dynamic dispatch**). Trong khi đó, compiler dùng kiểu khai báo `MessageSender` để kiểm tra những phương thức mà mã người gọi được phép gọi.

Ví dụ, `EmailSender` có thêm phương thức riêng `configureSmtp()` nhưng `MessageSender` không có thì `sender.configureSmtp()` không biên dịch được. Việc ẩn API riêng giúp người gọi phụ thuộc vào hợp đồng chung.

## 2. Vì sao dùng factory?

Nếu mọi nơi tự `new EmailSender()` hay `new SmsSender()`, việc lựa chọn implementation bị rải ở các nơi sử dụng. Một factory tập trung quyết định tạo đối tượng:

1. Người gọi yêu cầu một khả năng, chẳng hạn `create("sms")`.
2. Factory kiểm tra đầu vào, chọn lớp cụ thể tương ứng.
3. Factory gọi `new SmsSender()` để khởi tạo đối tượng.
4. Factory trả về tham chiếu dưới kiểu `MessageSender`.
5. Người gọi sử dụng `send` mà không cần biết constructor hay lớp vừa được chọn.

Factory không loại bỏ sự tồn tại của lớp cụ thể: **chính factory vẫn biết** những lớp mà nó khởi tạo. Lợi ích là mã nghiệp vụ không cần đưa logic lựa chọn ấy vào mọi nơi. Nếu thay Email bằng một implementation khác vẫn đáp ứng hợp đồng, các đoạn chỉ phụ thuộc `MessageSender` thường giữ nguyên.

## 3. Chương trình Java 17+ chạy được

Tạo tệp `Main.java` với nội dung sau:

```java
import java.util.Locale;

public class Main {
    interface MessageSender {
        void send(String recipient, String message);
    }

    static final class EmailSender implements MessageSender {
        @Override
        public void send(String recipient, String message) {
            System.out.println("Email -> " + recipient + ": " + message);
        }
    }

    static final class SmsSender implements MessageSender {
        @Override
        public void send(String recipient, String message) {
            System.out.println("SMS -> " + recipient + ": " + message);
        }
    }

    static final class MessageSenderFactory {
        private MessageSenderFactory() {
            // Không cần tạo instance của lớp factory tiện ích này.
        }

        static MessageSender create(String channel) {
            if (channel == null) {
                throw new IllegalArgumentException("Kênh không được null");
            }

            return switch (channel.trim().toLowerCase(Locale.ROOT)) {
                case "email" -> new EmailSender();
                case "sms" -> new SmsSender();
                default -> throw new IllegalArgumentException(
                    "Kênh không hỗ trợ: " + channel
                );
            };
        }
    }

    public static void main(String[] args) {
        MessageSender email = MessageSenderFactory.create("email");
        MessageSender sms = MessageSenderFactory.create("sms");

        email.send("an@example.com", "Xin chào");
        sms.send("0900000000", "Xin chào");

        System.out.println("Lớp thực tế: " + email.getClass().getSimpleName());
    }
}
```

Chạy bằng JDK 17 trở lên, tại thư mục chứa file:

```bash
javac Main.java
java Main
```

Stdout:

```text
Email -> an@example.com: Xin chào
SMS -> 0900000000: Xin chào
Lớp thực tế: EmailSender
```

**Đọc mã theo quan hệ kiểu:**

- `MessageSender` là hợp đồng của người gọi: nó chỉ yêu cầu `send(String, String)`.
- `EmailSender` và `SmsSender` là lớp cụ thể có thể `new`. Mỗi lớp `implements MessageSender` và ghi đè `send`.
- `MessageSenderFactory.create` khai báo kiểu trả về là `MessageSender`. Mỗi nhánh `switch` trả một đối tượng của lớp cụ thể. Cả hai nhánh đều hợp lệ nhờ quan hệ `implements`.
- `channel.trim().toLowerCase(Locale.ROOT)` giúp `" EMAIL "` khớp `"email"` mà không phụ thuộc locale máy chạy. `null` và kênh không hỗ trợ nhận lỗi rõ ràng.
- Trong `main`, hai biến đều khai báo `MessageSender` nhưng `email.send` chạy triển khai Email, `sms.send` chạy triển khai SMS. `getClass().getSimpleName()` chỉ được dùng để quan sát lớp runtime.
- Mỗi lời gọi thành công của **factory cụ thể trong ví dụ này** thực hiện `new`, do đó tạo đối tượng mới. Đó không phải là bảo đảm chung của mọi factory.

Thử đổi `create("email")` thành `create("sms")` ở dòng tạo biến `email`. Không cần sửa lệnh `email.send(...)`; chỉ kết quả hành vi khác đi. Nếu đổi thành `create("push")`, factory ném `IllegalArgumentException` với thông báo `Kênh không hỗ trợ: push`.

## 4. Factory cũng có thể trả về abstract class

Không chỉ `interface`: factory có thể trả `abstract class` khi nhiều lớp con chia sẻ một phần thuật toán hoặc trạng thái. Ví dụ độc lập sau đặt trong tệp `MainAbstract.java`:

```java
public class MainAbstract {
    abstract static class Greeting {
        final void greet(String name) {
            System.out.print("Xin chào, ");
            sayName(name);
        }

        protected abstract void sayName(String name);
    }

    static final class FormalGreeting extends Greeting {
        @Override
        protected void sayName(String name) {
            System.out.println("anh/chị " + name + "!");
        }
    }

    static class GreetingFactory {
        static Greeting create() {
            return new FormalGreeting();
        }
    }

    public static void main(String[] args) {
        Greeting greeting = GreetingFactory.create();
        greeting.greet("An");
    }
}
```

Chạy `javac MainAbstract.java` rồi `java MainAbstract`. Stdout:

```text
Xin chào, anh/chị An!
```

Ở đây `Greeting` không thể khởi tạo trực tiếp, nhưng `new FormalGreeting()` hoàn toàn hợp lệ. `GreetingFactory.create()` trả một `Greeting` tham chiếu đến đối tượng `FormalGreeting`. Phương thức `greet` là phần thuật toán dùng chung; khi gọi `sayName`, Java chạy phần cài đặt ở lớp con. Nếu chỉ cần hợp đồng hành vi, thường chọn interface; nếu cần kế thừa phần cài đặt/trạng thái chung thực sự, abstract class có thể phù hợp hơn.

## 5. So sánh kiểu trả về

| Cách viết | Người gọi biết gì? | Hệ quả |
| --- | --- | --- |
| `EmailSender e = new EmailSender();` | Biết lớp và constructor cụ thể. | Gắn trực tiếp với EmailSender. |
| `EmailSender e = Factory.createEmail();` | Biết lớp cụ thể dù logic tạo nằm trong factory. | Vẫn có thể phụ thuộc các phương thức riêng của EmailSender. |
| `MessageSender s = Factory.create("email");` | Biết hợp đồng `MessageSender` và yêu cầu lựa chọn. | Dễ thay lớp triển khai miễn là giữ hợp đồng. |
| `MessageSender s = new EmailSender();` | Dùng hợp đồng nhưng vẫn tự chọn lớp cụ thể. | Phép gán hợp lệ, nhưng nơi sử dụng còn phụ thuộc constructor. |

Một kiểu trả về trừu tượng làm API rõ ràng hơn: “Bạn cần một đối tượng biết gửi thông điệp”, chứ không yêu cầu người gọi sử dụng các chi tiết đặc thù của Email hoặc SMS. Đây là một cách áp dụng lập trình dựa trên interface, phù hợp với polymorphism và mục tiêu giảm coupling.

Tuy vậy, interface không tự bảo đảm immutable, thread-safe, singleton hay lazy initialization. Các đặc tính ấy phụ thuộc vào implementation và quy ước vòng đời mà factory cam kết.

## 6. Thiết kế factory tốt

**Hợp đồng vừa đủ.** Đặt trong `MessageSender` đúng hành vi cần được sử dụng chung. Nếu bắt mọi implementation triển khai nhiều phương thức vô nghĩa, interface quá rộng và khó mở rộng.

**Tham số rõ ràng.** Trong ví dụ, đầu vào là chuỗi `"email"` hoặc `"sms"`. Với tập lựa chọn hữu hạn ở ứng dụng thực, một `enum` có thể giúp tránh chuỗi gõ sai. Nhưng input từ HTTP, config hoặc file vẫn cần được kiểm tra tại ranh giới và báo lỗi có ý nghĩa. Factory không nên âm thầm trả `null` cho mọi lựa chọn không hỗ trợ nếu contract không nói rõ điều đó.

**Vòng đời đối tượng có chủ ý.** Có factory luôn tạo mới, có factory trả đối tượng cache hoặc instance dùng chung. Nếu đối tượng có mutable state hoặc giữ tài nguyên, cân nhắc cạnh tranh truy cập, thread safety và trách nhiệm đóng tài nguyên. Việc khai báo kiểu trừu tượng không thay thế thiết kế vòng đời.

**Chọn static hoặc instance theo nhu cầu.** `static create` đủ phù hợp với logic đơn giản. Nếu việc tạo sender cần cấu hình, HTTP client hoặc dependency khác, có thể dùng factory instance được inject. Công thức cốt lõi vẫn là: tạo lớp cụ thể và công bố kiểu trừu tượng.

**Tách việc chọn implementation khỏi nghiệp vụ.** Mã nghiệp vụ nhận `MessageSender` qua constructor hoặc tham số sẽ dễ được kiểm thử bằng một implementation giả ghi nhận `send`. Test factory riêng để xác minh `"email"` tạo `EmailSender`, `"sms"` tạo `SmsSender`, và đầu vào sai được xử lý đúng. Nếu mọi phương thức nghiệp vụ đều tự gọi một static factory thì chính mã nghiệp vụ vẫn gắn với factory đó, dù kiểu trả về đã là interface.

**Mở rộng khi cần.** Để thêm `PushSender`, hãy triển khai `MessageSender` rồi cập nhật logic chọn trong factory. Ở hệ thống lớn, có thể dùng registry hoặc dependency injection thay `switch`; không nhất thiết cần cơ chế ấy khi chỉ có vài lựa chọn ổn định.

## 7. Phân biệt với các khái niệm Factory khác

- **Constructor** `new EmailSender()` trực tiếp khởi tạo lớp cụ thể.
- **Simple factory / factory function**, giống `MessageSenderFactory.create`, gom logic tạo và lựa chọn đối tượng. Đó là cách tổ chức code thông dụng, không nhất thiết là một design pattern GoF riêng.
- **Static factory method** là một phương thức static trả/cung cấp instance. Nó có thể tạo mới, dùng cache hay trả singleton theo hợp đồng.
- **Factory Method pattern (GoF)** định nghĩa phương thức tạo sản phẩm ở lớp cha, để lớp con quyết định kiểu sản phẩm được tạo. Không thể suy ra một phương thức `static create()` bất kỳ là Factory Method pattern.
- **Abstract Factory pattern (GoF)** biểu diễn một giao diện tạo *họ sản phẩm liên quan* mà không phụ thuộc lớp cụ thể. Nó giải quyết phạm vi rộng hơn ví dụ chọn một sender.

Tên bài “Factory tạo lớp cụ thể nhưng trả về kiểu trừu tượng” diễn đạt nguyên tắc **tách API sử dụng khỏi chi tiết khởi tạo**. Nguyên tắc có thể được áp dụng trong nhiều biến thể factory, không cần áp dụng toàn bộ pattern phức tạp cho một bài toán nhỏ.

## 8. Các lỗi thường gặp

1. **Cố `new` interface hoặc abstract class:** `new MessageSender()` và `new Greeting()` không hợp lệ. Hãy khởi tạo một lớp cụ thể triển khai/kế thừa đúng hợp đồng.
2. **Cho rằng biến trừu tượng mất kiểu thực tế:** object vẫn có class runtime như `EmailSender`; lời gọi phương thức được phân phối động.
3. **Gọi API riêng của lớp con qua interface:** chỉ những phương thức thuộc hợp đồng chung mới có thể gọi trực tiếp. Đừng ép kiểu xuống chỉ để lách API, trừ khi có yêu cầu và kiểm tra kiểu an toàn.
4. **Ép kiểu sai:** `(EmailSender) MessageSenderFactory.create("sms")` có thể biên dịch nhưng lúc chạy ném `ClassCastException`. Nếu cần cả hai khả năng, ưu tiên thiết kế interface chung thích hợp.
5. **Không xác định trường hợp kênh lạ/`null`:** dẫn đến lỗi mơ hồ hoặc `NullPointerException` ở xa nguồn. Hãy kiểm tra và thông báo thất bại tại factory.
6. **Đánh đồng static factory với singleton:** một phương thức static vẫn có thể gọi `new` mỗi lần; hai lần gọi có thể trả hai đối tượng khác nhau.
7. **Lạm dụng `instanceof` ở nơi sử dụng:** nếu nghiệp vụ cứ tách nhánh Email/SMS để chọn hành vi, xem lại hợp đồng và cách dùng đa hình.
8. **Factory phức tạp khi không cần thiết:** chỉ thêm lớp factory khi việc chọn, cấu hình, điều khiển lifecycle hoặc tách dependency thực sự giúp code dễ hiểu.

## 9. Câu hỏi tự luyện

1. Vì sao `MessageSender sender = MessageSenderFactory.create("email")` hợp lệ dù không thể `new MessageSender()`?
2. Khi đổi kênh thành `"sms"`, điều gì xảy ra ở lệnh `sender.send(...)` và vì sao không cần sửa kiểu biến?
3. Hai lời gọi `create("email")` trong **ví dụ hiện tại** có trả cùng một đối tượng không? Nếu muốn cache, phần cài đặt nào phải thay đổi?
4. Nếu thêm lớp `PushSender implements MessageSender`, cần bổ sung gì trong factory, và đoạn mã người gọi chỉ sử dụng `send` có phải sửa không?
5. Nếu muốn kiểm thử một service gọi `sender.send(...)` mà không gửi tin thật, bạn sẽ truyền dependency kiểu gì vào service?

Ghi nhớ: **factory có thể biết và `new` lớp cụ thể, nhưng khai báo trả về interface/abstract class để người gọi phụ thuộc vào hợp đồng chung.** Compiler kiểm tra thao tác theo kiểu khai báo; JVM thực thi phương thức được ghi đè theo lớp thực tế của đối tượng.
