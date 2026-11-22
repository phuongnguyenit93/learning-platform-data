# Phương thức có thân và mã triển khai dùng chung trong lớp trừu tượng (Java)

## 1. Bản chất: lớp trừu tượng vẫn có thể triển khai phương thức

Trong Java, một `abstract class` không thể được tạo đối tượng trực tiếp bằng `new`, nhưng **không bắt buộc mọi phương thức của nó đều trừu tượng**. Nó có thể kết hợp:

- **Phương thức có thân (concrete method):** có khối lệnh `{ ... }`, cung cấp hành vi mặc định hoặc quy trình dùng chung cho các lớp con.
- **Phương thức trừu tượng (abstract method):** chỉ khai báo hợp đồng, kết thúc bằng dấu `;`, không có thân. Lớp con cụ thể phải triển khai những phương thức trừu tượng chưa được triển khai trên chuỗi kế thừa.
- **Trường dữ liệu và constructor:** lưu trạng thái chung, bảo đảm điều kiện khởi tạo mà các phương thức dùng chung cần.

Ví dụ hình thức:

```java
abstract class BaseTask {
    public void start() {                    // Có thân: dùng chung
        System.out.println("Bắt đầu");
        execute();
    }

    protected abstract void execute();       // Không có thân: lớp con cung cấp
}
```

`start()` là phương thức đã được triển khai trong lớp cha. Mỗi lớp con kế thừa `BaseTask` có thể dùng lại `start()` mà không viết lại câu lệnh in thông báo và gọi `execute()`. Khi `execute()` chạy, Java chọn bản triển khai tương ứng với đối tượng thật ở thời điểm chạy.

Một lớp được khai báo `abstract` **vẫn hợp lệ dù không có phương thức `abstract`**; khi đó từ khóa này chủ yếu ngăn khởi tạo trực tiếp và dành lớp làm nền cho các lớp con.

## 2. Vì sao cần mã triển khai dùng chung?

Giả sử nhiều loại bộ gửi thông báo đều phải kiểm tra đầu vào, chuẩn hóa nội dung và ghi log, nhưng mỗi loại gửi thông báo bằng một cơ chế khác nhau. Nếu mỗi lớp chép lại ba thao tác chung, lỗi sửa chữa dễ bị bỏ sót và hành vi dần không nhất quán.

Đưa các bước giống nhau vào một lớp cha trừu tượng sẽ tạo ra một điểm bảo trì chung:

1. Lớp cha chứa **phần bất biến của quy trình**: kiểm tra, chuẩn hóa, ghi log và trình tự gọi.
2. Lớp cha khai báo **điểm biến thiên** dưới dạng phương thức trừu tượng hoặc phương thức có thân cho phép override.
3. Lớp con chỉ viết phần thực sự khác biệt: cách gửi qua email, SMS hoặc kênh khác.

Đây là cơ sở của mẫu thiết kế **Template Method**: phương thức khung trong lớp cha xác định các bước, còn lớp con cung cấp một số bước cụ thể. Không phải mọi phương thức dùng chung đều phải tham gia Template Method; một tiện ích `protected` có thân để các lớp con gọi lại cũng là tái sử dụng hợp lệ.

## 3. Ví dụ Java 17+: dùng chung luồng gửi thông báo

Lưu toàn bộ chương trình sau vào tệp `Main.java`:

```java
import java.util.Objects;

abstract class NotificationSender {
    private final String channelName;

    protected NotificationSender(String channelName) {
        this.channelName = Objects.requireNonNull(channelName);
    }

    // Quy trình dùng chung: lớp con không được thay đổi thứ tự các bước.
    public final void send(String recipient, String message) {
        Objects.requireNonNull(recipient, "recipient");
        Objects.requireNonNull(message, "message");

        if (recipient.isBlank()) {
            throw new IllegalArgumentException("recipient không được trống");
        }

        String normalized = normalize(message);
        log(recipient);
        deliver(recipient, normalized);
    }

    // Có thân mặc định; lớp con được tùy chỉnh nếu cần.
    protected String normalize(String message) {
        return message.strip();
    }

    // Có thân, dùng lại nguyên vẹn cho mọi kênh gửi.
    private void log(String recipient) {
        System.out.println("[" + channelName + "] Chuẩn bị gửi tới " + recipient);
    }

    // Phần khác biệt: mỗi kênh phải tự triển khai.
    protected abstract void deliver(String recipient, String message);
}

final class EmailSender extends NotificationSender {
    EmailSender() {
        super("email");
    }

    @Override
    protected void deliver(String recipient, String message) {
        System.out.println("EMAIL tới " + recipient + ": " + message);
    }
}

final class SmsSender extends NotificationSender {
    SmsSender() {
        super("sms");
    }

    // Chỉ thay đổi bước chuẩn hóa; vẫn tái sử dụng bước của lớp cha.
    @Override
    protected String normalize(String message) {
        return super.normalize(message).replaceAll("\\s+", " ");
    }

    @Override
    protected void deliver(String recipient, String message) {
        System.out.println("SMS tới " + recipient + ": " + message);
    }
}

public class Main {
    public static void main(String[] args) {
        NotificationSender email = new EmailSender();
        NotificationSender sms = new SmsSender();

        email.send("an@example.com", "  Xin chào An  ");
        sms.send("0901234567", "  Hẹn     gặp  ");
    }
}
```

Biên dịch và chạy (JDK 17 trở lên):

```bash
javac -encoding UTF-8 Main.java
java Main
```

Kết quả tiêu chuẩn:

```text
[email] Chuẩn bị gửi tới an@example.com
EMAIL tới an@example.com: Xin chào An
[sms] Chuẩn bị gửi tới 0901234567
SMS tới 0901234567: Hẹn gặp
```

Giải thích từng vai trò:

| Thành phần | Kiểu phương thức | Vai trò |
| --- | --- | --- |
| `send(...)` | `public final`, có thân | Cung cấp toàn bộ luồng xử lý chung; `final` cấm lớp con override để không bỏ qua kiểm tra và ghi log. |
| `normalize(...)` | `protected`, có thân | Cung cấp mặc định `strip()`; `SmsSender` override rồi gọi `super.normalize(...)` để tận dụng phần đã có. |
| `log(...)` | `private`, có thân | Chi tiết nội bộ chỉ lớp cha gọi; mọi lớp con vẫn hưởng hành vi ghi log qua `send(...)`. |
| `deliver(...)` | `protected abstract`, không thân | Bắt buộc mỗi lớp con cụ thể cung cấp thao tác gửi riêng. |
| `NotificationSender(...)` | Constructor `protected` | Khởi tạo `channelName` khi một lớp con được tạo; không tạo trực tiếp `NotificationSender`. |

Điểm then chốt: biến `email` có kiểu khai báo `NotificationSender`, nhưng đối tượng thật là `EmailSender`. Lời gọi `email.send(...)` sử dụng thân `send` kế thừa từ lớp cha; bên trong, lời gọi `deliver(...)` được phân giải động đến `EmailSender.deliver(...)`. Tương tự, đối tượng `SmsSender` sử dụng bản `normalize(...)` đã override. Việc gọi phương thức có thân của lớp cha **không làm mất tính đa hình** của các bước được lớp con ghi đè.

Trong ví dụ, `SmsSender.normalize` gọi `super.normalize(message)` để lấy logic cắt khoảng trắng hai đầu, sau đó thu gọn chuỗi khoảng trắng bên trong. `super` là cách tái sử dụng trực tiếp bản triển khai của lớp cha khi override; nó không tạo đối tượng lớp cha mới.

## 4. Phân biệt kế thừa, override và gọi `super`

Nếu lớp con không override một phương thức có thân có thể kế thừa, nó dùng lại triển khai đó nguyên trạng. Chỉ override khi hành vi cần biến thể; dùng `@Override` để trình biên dịch xác minh chữ ký. Khi cần giữ một phần hành vi cũ, lớp con có thể gọi `super.method(...)`, như `SmsSender.normalize` trong ví dụ.

Override phải giữ chữ ký tương thích và không được thu hẹp quyền truy cập. Phương thức `private` không phải hook để override, phương thức `static` bị hiding thay vì dynamic dispatch, còn phương thức `final` cấm override. Bài chuyên về modifier đi sâu vào ma trận hợp lệ; bài này tập trung vào việc tổ chức các bước dùng chung và điểm biến thiên.

## 5. Quan hệ với trạng thái và constructor

Phương thức có thân có thể đọc trạng thái của lớp cha và gọi các hook khác; constructor cha thiết lập trạng thái đó trước khi quy trình dùng chung được gọi. Tránh gọi hook có thể override trong constructor, bởi lớp con có thể chưa khởi tạo xong các trường của mình. Quy tắc về constructor, access modifier và thứ tự khởi tạo được giải thích riêng trong bài về constructor.

## 6. Chọn phương thức có thân, abstract hay final như thế nào?

| Nhu cầu | Cách khai báo gợi ý | Lý do |
| --- | --- | --- |
| Mọi lớp con phải có cùng một bước xử lý | `final` method có thân | Giữ đúng quy tắc chung, tránh override trái ý. |
| Có hành vi mặc định hợp lý, đôi khi cần biến thể | Method có thân và cho phép override | Có thể dùng nguyên trạng hoặc tùy chỉnh, kể cả gọi `super`. |
| Không có triển khai mặc định đúng cho mọi lớp con | `abstract` method | Buộc lớp con cụ thể đưa ra cách thực hiện. |
| Chi tiết chỉ lớp cha tự sử dụng | `private` method có thân | Đóng gói, giảm bề mặt API kế thừa. |
| Hàm tiện ích dùng chung cho lớp con | `protected` method có thân, cân nhắc `final` | Tái sử dụng mà không buộc sao chép thuật toán. |

Quy trình lựa chọn thực tế: trước tiên xác định bước nào **giống nhau** và bước nào **thực sự biến đổi** giữa các lớp con; đưa phần giống nhau vào method có thân, biểu diễn phần bắt buộc khác nhau bằng method `abstract`. Chỉ mở quyền override tại các điểm mở rộng đã được thiết kế.

## 7. Khi nào nên dùng lớp trừu tượng để chia sẻ code?

Phù hợp khi các lớp con có quan hệ **is-a** tự nhiên và cùng chia sẻ một phần thuật toán hoặc trạng thái, ví dụ các loại bộ xử lý, trình đọc tệp hay bộ gửi thông báo có vòng đời và quy tắc nền giống nhau. Nó đặc biệt hữu ích khi phải bảo vệ **thứ tự các bước** bằng Template Method và vẫn cho phép tùy biến một số bước.

Tuy vậy, kế thừa Java chỉ cho phép một lớp cha trực tiếp (`extends` một class). Nếu mục tiêu chỉ là dùng lại vài tiện ích độc lập, chưa chắc nên tạo cả hệ phân cấp:

- **Composition / dependency injection:** chuyển hành vi tái sử dụng sang một đối tượng dịch vụ được các lớp khác gọi. Cách này linh hoạt nếu nhiều kiểu đối tượng không cùng họ vẫn cần logic ấy.
- **Interface với `default method`:** hợp lý khi nhiều lớp cần chia sẻ hành vi mặc định nhỏ, không cần trạng thái instance hay constructor từ cùng một lớp cha. `default method` không thay thế mọi vai trò của abstract class.
- **Utility method `static`:** hợp lý cho phép biến đổi thuần túy không cần trạng thái và không cần đa hình.

Nên ưu tiên cấu trúc đơn giản nhất diễn tả đúng quan hệ nghiệp vụ; không tạo base class chỉ vì hai lớp tình cờ có vài dòng code giống nhau.

## 8. Lỗi thường gặp và cách tự kiểm tra

1. **Nhầm “abstract class” với “toàn phương thức abstract”.** Lớp trừu tượng được phép có rất nhiều phương thức có thân, thậm chí không có phương thức abstract.
2. **Viết thân cho phương thức `abstract`.** Khai báo `protected abstract void execute();` không được kèm `{ ... }`. Muốn có logic mặc định, bỏ `abstract` và cung cấp thân.
3. **Định nghĩa method abstract trong class thường.** Class chứa method `abstract` phải được đánh dấu `abstract`; class con cụ thể phải triển khai các method abstract còn tồn đọng.
4. **Override nhầm phương thức `private`/`final`/`static`.** `private` không thể override, `final` cấm override, `static` chỉ hiding. Dùng `@Override` và biên dịch để bắt lỗi.
5. **Nhân bản phần kiểm tra trong từng lớp con.** Điều này dễ tạo sai lệch. Đặt validation trong một phương thức khung `final`, để lớp con chỉ xử lý phần chuyên biệt.
6. **Thay đổi logic chung trong override mà không hiểu hợp đồng.** Nếu được phép mở rộng, chỉ override đúng hook; gọi `super` khi cần bảo toàn phần mặc định.
7. **Gọi hook có thể override từ constructor.** Chuyển lời gọi đó sang một phương thức được thực thi sau khi đối tượng khởi tạo hoàn chỉnh.
8. **Lạm dụng kế thừa để chia sẻ vài hàm.** Cân nhắc composition hoặc utility method để giảm phụ thuộc vào một lớp cha cố định.

Để kiểm chứng ví dụ, hãy thử thêm một lớp `PushSender` extends `NotificationSender` chỉ triển khai `deliver(...)`: lớp mới tự động nhận toàn bộ kiểm tra đầu vào, chuẩn hóa mặc định và ghi log. Tiếp đó thử gọi `send("  ", "test")`: chương trình ném `IllegalArgumentException` **trước khi** ghi log và gọi `deliver`. Hai phép thử xác nhận mã chung được dùng nhất quán giữa các lớp con.

**Ghi nhớ:** phương thức có thân trong abstract class tạo ra hành vi kế thừa dùng chung; phương thức abstract xác định việc lớp con phải bổ sung; phương thức `final` bảo vệ những bước hoặc thuật toán không được thay đổi. Kết hợp ba loại này có chủ đích giúp vừa tái sử dụng code vừa giữ quyền tùy biến đúng chỗ.
