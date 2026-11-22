# Factory Method: tách quyết định chọn lớp cụ thể

## 1. Bài toán và ý tưởng

Factory Method là mẫu thiết kế khởi tạo thuộc nhóm Creational trong GoF. Mẫu này định nghĩa một phương thức tạo đối tượng trong lớp cơ sở, sau đó để các lớp con quyết định sẽ tạo ra lớp sản phẩm cụ thể nào. Phần nghiệp vụ ổn định chỉ làm việc với kiểu trừu tượng của sản phẩm.

Hãy tưởng tượng một dịch vụ gửi thông báo. Quy trình gửi có thể giống nhau với email và SMS, nhưng cách tạo đối tượng gửi tin khác nhau. Nếu lớp nghiệp vụ trực tiếp gọi `new EmailNotification()` hoặc rải `if/else` để chọn nhiều lớp cụ thể, mỗi lần thêm kênh mới có thể buộc phải sửa các lớp đang có.

Factory Method đưa điểm thay đổi vào một phương thức có thể được ghi đè:

1. Lớp cơ sở khai báo phương thức tạo sản phẩm và dùng nó trong quy trình chung.
2. Mỗi lớp con cụ thể ghi đè phương thức tạo để trả về một sản phẩm phù hợp.
3. Mã gọi chọn một lớp dịch vụ cụ thể, nhưng quy trình gửi chỉ biết giao diện `Notification`.

## 2. Các vai trò trong mẫu GoF

| Vai trò | Trách nhiệm | Trong ví dụ |
| --- | --- | --- |
| Product | Hợp đồng chung cho sản phẩm được tạo | `Notification` |
| Concrete Product | Cài đặt một loại sản phẩm | `EmailNotification`, `SmsNotification` |
| Creator | Khai báo Factory Method và chứa quy trình sử dụng sản phẩm | `NotificationService` |
| Concrete Creator | Ghi đè Factory Method để chọn loại sản phẩm | `EmailNotificationService`, `SmsNotificationService` |
| Client | Chọn creator phù hợp và gọi nghiệp vụ qua kiểu trừu tượng | `Main` |

Quan hệ quan trọng là `NotificationService` không cần biết tên lớp cụ thể của sản phẩm. Nó gọi `createNotification()` và làm việc với giá trị trả về qua kiểu `Notification`.

## 3. Ví dụ Java 17 hoàn chỉnh

Ví dụ dưới đây tạo hai dịch vụ có cùng quy trình gửi nhưng tạo hai loại thông báo khác nhau. Tất cả lớp đều nằm trong một tệp để có thể biên dịch trực tiếp.

Lưu thành `Main.java`:

```java
import java.util.Objects;

public class Main {
    public static void main(String[] args) {
        NotificationService email = new EmailNotificationService();
        email.notifyUser("alice@example.com", "Your report is ready.");

        NotificationService sms = new SmsNotificationService();
        sms.notifyUser("+84901234567", "Your report is ready.");
    }
}

interface Notification {
    void send(String recipient, String message);
}

final class EmailNotification implements Notification {
    @Override
    public void send(String recipient, String message) {
        System.out.println("EMAIL -> " + recipient + ": " + message);
    }
}

final class SmsNotification implements Notification {
    @Override
    public void send(String recipient, String message) {
        System.out.println("SMS -> " + recipient + ": " + message);
    }
}

abstract class NotificationService {
    public final void notifyUser(String recipient, String message) {
        Objects.requireNonNull(recipient, "recipient");
        Objects.requireNonNull(message, "message");

        Notification notification = createNotification();
        notification.send(recipient, message);
    }

    protected abstract Notification createNotification();
}

final class EmailNotificationService extends NotificationService {
    @Override
    protected Notification createNotification() {
        return new EmailNotification();
    }
}

final class SmsNotificationService extends NotificationService {
    @Override
    protected Notification createNotification() {
        return new SmsNotification();
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```text
javac --release 17 Main.java
java Main
```

Stdout chính xác:

```text
EMAIL -> alice@example.com: Your report is ready.
SMS -> +84901234567: Your report is ready.
```

## 4. Cách chương trình hoạt động

Khi gọi `email.notifyUser(...)`, Java thực thi phương thức `notifyUser` được định nghĩa ở `NotificationService`. Phương thức này gọi `createNotification()`. Vì đối tượng thực tế là `EmailNotificationService`, cơ chế dynamic dispatch chạy phần ghi đè của lớp đó và tạo `EmailNotification`. Sản phẩm sau đó được sử dụng qua giao diện `Notification`.

Khi gọi `sms.notifyUser(...)`, cùng quy trình ở lớp cơ sở được giữ nguyên, nhưng phần ghi đè của `SmsNotificationService` tạo `SmsNotification`. Lớp cơ sở không cần nhánh `if/else` để phân biệt email và SMS.

`notifyUser` thể hiện quy trình chung; `createNotification` là điểm mở rộng. Nếu muốn thêm kênh push notification, có thể tạo `PushNotification` và `PushNotificationService` mà không cần sửa phần quy trình gửi ở `NotificationService`.

Trong ứng dụng thực tế, lớp creator thường được chọn tại điểm khởi tạo ứng dụng hoặc thông qua cấu hình dependency injection. Factory Method xử lý cách tạo sản phẩm bên trong creator; việc chọn creator nào vẫn thuộc về nơi cấu hình ứng dụng.

## 5. Factory Method khác các cách tạo đối tượng khác ra sao?

### Gọi constructor trực tiếp

```java
Notification notification = new EmailNotification();
```

Cách này rõ ràng và hoàn toàn hợp lý nếu loại sản phẩm đã cố định. Tuy nhiên, lớp gọi phụ thuộc trực tiếp vào `EmailNotification`; nếu nhiều loại sản phẩm cần được chọn theo môi trường hoặc nghiệp vụ, các điểm tạo đối tượng có thể bị phân tán.

### Simple Factory hoặc static factory method

Một Simple Factory thường nhận tham số như `"email"` hoặc `"sms"` rồi dùng điều kiện để trả về một sản phẩm. Đây là cách gom logic chọn lớp vào một nơi, nhưng thường phải sửa factory đó mỗi khi thêm loại sản phẩm mới. Nó không phải mẫu Factory Method GoF theo nghĩa chặt chẽ, vì không dựa vào lớp con ghi đè phương thức tạo.

Thuật ngữ Java `static factory method` cũng có nghĩa rộng hơn: một phương thức tĩnh như `List.of(...)` tạo hoặc cung cấp đối tượng. Nó không tự động là mẫu Factory Method GoF.

### Factory Method

Factory Method dùng tính đa hình: lớp con quyết định loại sản phẩm bằng cách ghi đè một phương thức tạo. Mẫu này phù hợp khi có một quy trình chung nhưng có nhiều biến thể của sản phẩm cần được lựa chọn qua các creator khác nhau.

### Abstract Factory

Abstract Factory cung cấp một giao diện để tạo một họ sản phẩm liên quan, thường gồm nhiều loại sản phẩm phải tương thích với nhau. Factory Method thường tập trung vào một điểm tạo sản phẩm trong một creator; Abstract Factory hữu ích khi cần phối hợp nhiều phương thức tạo trong cùng một họ.

### Builder

Builder tách quá trình xây dựng một đối tượng phức tạp thành nhiều bước, thường để cấu hình nhiều trường tùy chọn hoặc biểu diễn các cách xây dựng khác nhau. Factory Method chủ yếu tách quyết định chọn lớp sản phẩm cụ thể.

## 6. Khi nào nên dùng?

Factory Method phù hợp khi:

- Một lớp có quy trình ổn định nhưng cần nhiều biến thể sản phẩm.
- Mã gọi nên phụ thuộc vào interface hoặc abstract class của sản phẩm thay vì lớp cụ thể.
- Một framework cần cung cấp quy trình mặc định và cho phép lớp con mở rộng cách tạo đối tượng.
- Cần thay sản phẩm trong kiểm thử, ví dụ creator kiểm thử trả về một fake hoặc stub triển khai cùng interface.
- Các lớp con có trách nhiệm rõ ràng: mỗi creator đại diện cho một lựa chọn sản phẩm có ý nghĩa.

Ví dụ thực tế có thể gồm bộ đọc tệp theo định dạng, bộ xuất báo cáo, bộ phân tích cú pháp, bộ lưu trữ hoặc dịch vụ gửi thông báo. Chỉ nên áp dụng khi có một điểm thay đổi thật sự; không cần tạo một hierarchy creator cho mỗi lời gọi `new` đơn giản.

## 7. Lợi ích và chi phí

**Lợi ích**

- Tách phần nghiệp vụ khỏi tên lớp sản phẩm cụ thể.
- Giữ quy trình chung ở một chỗ, tránh lặp lại quy trình cho từng loại sản phẩm.
- Mở rộng bằng cách thêm creator và product mới khi thiết kế cho phép, thay vì sửa logic tạo sản phẩm trong lớp cơ sở.
- Hỗ trợ kiểm thử vì mã nghiệp vụ sử dụng hợp đồng chung.
- Tạo điểm mở rộng có chủ đích cho thư viện hoặc framework.

**Chi phí**

- Tăng số lớp và mức gián tiếp; với một sản phẩm duy nhất, thiết kế có thể trở nên nặng nề.
- Người dùng vẫn cần biết hoặc cấu hình creator cụ thể ở điểm khởi tạo.
- Nếu mọi biến thể đều được gom vào một lớp creator với nhiều điều kiện, lợi ích của đa hình có thể biến mất.
- Mẫu này không tự cung cấp quản lý vòng đời, cache, thread safety, connection pooling hay dependency injection; các yêu cầu đó cần được thiết kế riêng.

## 8. Lỗi thiết kế thường gặp

1. **Trả về lớp cụ thể từ quy trình chung.** Nếu `notifyUser` phụ thuộc vào `EmailNotification`, thêm sản phẩm mới vẫn buộc phải sửa lớp cơ sở. Nên trả về và sử dụng kiểu `Notification`.
2. **Đặt toàn bộ điều kiện chọn sản phẩm trong creator cơ sở.** Một `switch` lớn trong `createNotification` có thể chỉ là Simple Factory. Nếu mục tiêu là Factory Method GoF, hãy để creator con ghi đè phương thức tạo.
3. **Nhầm Factory Method với bất kỳ phương thức tên `create...` nào.** Tên phương thức không quyết định mẫu thiết kế; vai trò của nó trong quan hệ creator, product và ghi đè mới là điều quan trọng.
4. **Tạo lớp con nhưng không có biến thể thực sự.** Nếu các creator đều tạo cùng một sản phẩm và không có lý do mở rộng, có thể dùng constructor trực tiếp hoặc factory đơn giản.
5. **Để client tự kiểm tra kiểu sản phẩm sau khi tạo.** Nếu mã gọi phải liên tục dùng `instanceof` để quyết định cách sử dụng, hợp đồng Product có thể chưa thể hiện đủ hành vi cần thiết.
6. **Quên xử lý phụ thuộc khi tạo sản phẩm.** Nếu sản phẩm cần gateway, cấu hình hoặc logger, hãy truyền các phụ thuộc đó qua constructor hoặc cơ chế injection thích hợp. Không nên giấu tài nguyên dùng chung trong biến toàn cục.
7. **Cho rằng mẫu này luôn loại bỏ mọi thay đổi.** Khi thêm loại sản phẩm, thường vẫn cần thêm Concrete Product, Concrete Creator và cấu hình creator tại nơi khởi tạo ứng dụng. Mẫu giảm phạm vi thay đổi và ghép nối, chứ không làm thay đổi mới biến mất.

## 9. Cách triển khai từng bước

1. Xác định phần nghiệp vụ ổn định cần dùng sản phẩm, chẳng hạn `notifyUser`.
2. Định nghĩa Product interface với các hành vi mà quy trình cần gọi.
3. Tạo các Concrete Product triển khai interface đó.
4. Tạo Creator chứa quy trình chung và khai báo Factory Method trả về Product.
5. Tạo Concrete Creator ghi đè Factory Method để trả về loại sản phẩm mong muốn.
6. Chọn creator ở composition root hoặc thông qua cấu hình ứng dụng.
7. Kiểm thử từng creator và quy trình chung; xác minh thêm sản phẩm mới không yêu cầu sửa mã sử dụng Product abstraction.

## 10. Checklist đánh giá thiết kế

- Có nhiều loại sản phẩm thật sự cần được tạo theo những cách khác nhau không?
- Quy trình sử dụng sản phẩm có thể giữ nguyên giữa các loại không?
- Product interface có thể hiện đủ hành vi mà quy trình chung cần không?
- Factory Method có được ghi đè bởi Concrete Creator, và có trả về kiểu trừu tượng không?
- Điểm chọn creator đã rõ ràng ở nơi cấu hình ứng dụng chưa?
- Chi phí của các lớp bổ sung có xứng đáng với lợi ích mở rộng và kiểm thử không?
- Có đang cần Abstract Factory vì phải tạo cả một họ sản phẩm, hoặc Builder vì quá trình xây dựng có nhiều bước không?

Factory Method hữu ích nhất khi nó cô lập một quyết định tạo sản phẩm đang thay đổi, trong khi giữ quy trình nghiệp vụ ổn định và phụ thuộc vào hợp đồng chung.
