# Giảm lặp logic giữa các phương thức `default` bằng `private` method trong interface

Một interface có thể cung cấp nhiều phương thức `default` để các lớp triển khai dùng chung hành vi. Khi các phương thức này cùng phải kiểm tra dữ liệu, chuẩn hóa đầu vào hoặc tạo kết quả theo một quy tắc giống nhau, phần xử lý đó dễ bị sao chép ở nhiều nơi. Mỗi bản sao phải được cập nhật riêng, vì vậy chúng có thể dần cho kết quả khác nhau khi quy tắc thay đổi.

Java hỗ trợ phương thức `private` bên trong interface từ Java 9. Đây vẫn là khả năng được hỗ trợ trong các phiên bản Java hiện đại. Ta có thể chuyển phần xử lý lặp lại thành một helper `private`, rồi để các phương thức `default` gọi helper đó. Phần dùng chung được gom về một nơi mà không trở thành một phần của API công khai.

## 1. Vì sao các phương thức `default` dễ lặp logic?

Giả sử interface có hai thao tác tạo thông báo: một thao tác tạo nội dung thông báo mới và một thao tác tạo nội dung nhắc nhở. Cả hai đều cần:

- Kiểm tra người nhận có hợp lệ hay không.
- Loại bỏ khoảng trắng thừa ở đầu và cuối.
- Kết hợp tên kênh, loại thông báo và người nhận thành một chuỗi.

Nếu mỗi phương thức `default` tự viết lại các bước này, một thay đổi nhỏ như cách kiểm tra dữ liệu hoặc định dạng chuỗi sẽ phải sửa ở nhiều vị trí. Bỏ sót một vị trí có thể khiến hai thao tác xử lý cùng loại dữ liệu theo hai cách khác nhau.

Vì phần xử lý này chỉ phục vụ các phương thức bên trong cùng interface, một phương thức `private` là ranh giới phù hợp: các phương thức `default` có thể tái sử dụng nó, còn lớp triển khai và mã gọi bên ngoài không thể gọi trực tiếp helper.

## 2. Tách phần dùng chung thành phương thức `private`

Một interface có thể khai báo phương thức `private` dạng instance hoặc `private static`:

- Phương thức `private` instance có thể dùng ngữ cảnh của đối tượng và gọi các phương thức instance khác của interface. Nó phù hợp khi xử lý chung cần dựa vào hành vi do lớp triển khai cung cấp.
- Phương thức `private static` không có `this` và không phụ thuộc vào một đối tượng cụ thể. Nó phù hợp với thao tác tiện ích thuần túy như kiểm tra hoặc chuẩn hóa dữ liệu.

Cả hai loại đều phải có thân hàm. Phương thức `private` không phải điểm mở rộng để lớp triển khai ghi đè và không được kế thừa như một phương thức công khai của interface.

## 3. Ví dụ hoàn chỉnh

Ví dụ dưới đây dùng một private instance method để định dạng thông báo và một private static method để chuẩn hóa người nhận. Hai phương thức `default` dùng chung quy trình, trong khi mỗi lớp triển khai vẫn cung cấp tên kênh riêng qua `channelName()`.

Phần `private` method trong interface có từ Java 9. Ví dụ chạy trên Java 17+ và sử dụng `String.isBlank()` cùng `String.strip()`.

Tạo tệp `Main.java`:

```java
interface Notification {
    String channelName();

    default String createdMessage(String recipient) {
        return formatMessage("Created", recipient);
    }

    default String reminderMessage(String recipient) {
        return formatMessage("Reminder", recipient);
    }

    private String formatMessage(String event, String recipient) {
        return channelName() + ": " + event + " notification for "
                + normalizeRecipient(recipient);
    }

    private static String normalizeRecipient(String recipient) {
        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException("recipient must not be blank");
        }
        return recipient.strip();
    }
}

final class EmailNotification implements Notification {
    @Override
    public String channelName() {
        return "Email";
    }
}

final class SmsNotification implements Notification {
    @Override
    public String channelName() {
        return "SMS";
    }
}

public class Main {
    public static void main(String[] args) {
        Notification email = new EmailNotification();
        Notification sms = new SmsNotification();

        System.out.println(email.createdMessage("  Linh  "));
        System.out.println(sms.reminderMessage("  An  "));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 Main.java
java Main
```

Kết quả chuẩn trên stdout:

```text
Email: Created notification for Linh
SMS: Reminder notification for An
```

Chương trình chỉ tạo chuỗi nội dung để minh họa việc dùng chung logic; nó chưa thực hiện gửi email hoặc SMS.

## 4. Theo dõi luồng gọi trong ví dụ

1. Mã gọi `createdMessage()` hoặc `reminderMessage()`. Đây là các phương thức `default` công khai và có thể được lớp triển khai kế thừa hoặc ghi đè.
2. Mỗi phương thức `default` chuyển phần định dạng sang `formatMessage()`. Vì đây là private instance method, nó được dùng bên trong interface và có thể gọi `channelName()`.
3. Lời gọi `channelName()` được phân giải theo đối tượng thực tế. `EmailNotification` trả về `Email`, còn `SmsNotification` trả về `SMS`; phần xử lý chung vẫn được tái sử dụng.
4. `formatMessage()` gọi `normalizeRecipient()`. Đây là private static method vì việc kiểm tra và loại bỏ khoảng trắng không cần trạng thái của đối tượng.

Nhờ vậy, hai phương thức `default` không phải lặp lại việc kiểm tra, chuẩn hóa và ghép chuỗi. Khi quy tắc định dạng thay đổi, ta có một helper duy nhất cần xem xét.

## 5. Chọn private instance method hay private static method

Dùng private instance method khi phần xử lý chung cần gọi một phương thức instance của interface, cần dựa vào hành vi mà lớp triển khai cung cấp, hoặc cần ngữ cảnh của đối tượng. Trong ví dụ, `formatMessage()` gọi `channelName()` nên là phương thức instance.

Dùng private static method khi thao tác không cần đối tượng cụ thể. Hàm chuẩn hóa trong ví dụ chỉ nhận dữ liệu đầu vào và trả về dữ liệu đã chuẩn hóa, vì vậy `normalizeRecipient()` là static. Một private static method có thể được gọi từ các phương thức static hoặc instance khác trong cùng interface.

Không cần biến mọi helper thành static theo thói quen. Hãy chọn loại phương thức dựa trên việc helper có cần ngữ cảnh instance hay không.

## 6. Phạm vi truy cập và những giới hạn cần nhớ

- Phương thức `private` chỉ phục vụ mã bên trong interface khai báo nó. Mã gọi không thể gọi `email.formatMessage(...)` hoặc `email.normalizeRecipient(...)`.
- Lớp triển khai không kế thừa và không ghi đè private helper. Nếu lớp triển khai khai báo một phương thức trùng tên, đó không phải là cách ghi đè helper private của interface.
- Phương thức `default` là phương thức instance công khai có thân hàm; phương thức `private` là chi tiết triển khai nội bộ. Không dùng `private default` hoặc `private abstract`: helper private phải có phần thân triển khai.
- Private helper không giải quyết xung đột giữa hai phương thức `default` cùng chữ ký đến từ hai interface độc lập. Lớp triển khai vẫn phải xử lý xung đột đó bằng cách cung cấp cách triển khai phù hợp.
- Private interface method chỉ phù hợp khi phần dùng chung thuộc về chính interface đó. Nếu nhiều interface hoặc nhiều lớp không liên quan cần cùng một thuật toán, hãy đặt phần xử lý ở một thành phần dùng chung có trách nhiệm rõ ràng.

Tránh tạo helper chỉ để đổi tên một dòng đơn giản hoặc tạo chuỗi gọi lồng nhau quá sâu. Helper nên gom một quy tắc có ý nghĩa, có thể được tái sử dụng và có tên mô tả đúng trách nhiệm.

## 7. Cách áp dụng khi refactor

Khi thấy nhiều phương thức `default` có đoạn xử lý giống nhau, hãy xác định chính xác phần chung và phần khác biệt. Đưa phần chung vào private helper; giữ phần khác biệt trong tham số hoặc trong các phương thức instance mà interface yêu cầu lớp triển khai cung cấp. Sau đó kiểm tra cả trường hợp dữ liệu hợp lệ, dữ liệu rỗng và dữ liệu không hợp lệ để bảo đảm các phương thức `default` vẫn giữ đúng hành vi.

Private method trong interface giúp tổ chức phần triển khai dùng chung mà không mở rộng hợp đồng công khai. Dùng private instance method cho logic cần ngữ cảnh đối tượng, private static method cho logic độc lập với đối tượng, và giữ các phương thức `default` tập trung vào hành vi mà người dùng interface thực sự cần.