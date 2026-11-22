# Một ví dụ xuyên suốt: nhiều cách xử lý cùng một yêu cầu

Trong chủ đề **abstract class, interface và đa hình của Java**, cách dễ nhất để thấy sự khác biệt giữa các công cụ là giữ nguyên một yêu cầu nghiệp vụ rồi thay đổi cách xử lý. Ví dụ dưới đây dùng yêu cầu: **“Thông báo cho khách hàng KH-42 rằng đơn hàng đã được xác nhận”**. Cùng một thông điệp có thể được xử lý bằng email, SMS hoặc thông báo trong ứng dụng.

Mục tiêu của bài:

- Nhận ra phần **ổn định** của yêu cầu (mã khách hàng, nội dung, thao tác gửi và kết quả) và phần **thay đổi** (cách gửi theo từng kênh).
- Hiểu cách `interface` biểu diễn hợp đồng chung, `abstract class` tái sử dụng quy trình chung và **đa hình** chọn triển khai lúc chạy.
- Biết khi nào nên dùng lớp trừu tượng, khi nào nên dùng interface, và vì sao nên kết hợp chúng bằng thành phần gọi chung.
- Đọc, biên dịch và giải thích một chương trình Java 17 hoàn chỉnh; thấy rõ giới hạn giữa ví dụ mô phỏng và hệ thống gửi thông báo thực.

## 1. Xác định một yêu cầu, nhiều cách đáp ứng

Hãy hình dung dịch vụ nhận một đối tượng yêu cầu:

| Thông tin | Giá trị ví dụ | Có thay đổi theo kênh không? |
| --- | --- | --- |
| Mã khách hàng | `KH-42` | Không |
| Nội dung | `Đơn hàng đã được xác nhận` | Không |
| Hành động | Gửi thông báo | Không |
| Cách thực hiện | Email, SMS, thông báo trong ứng dụng | **Có** |
| Kết quả | Kênh xử lý và trạng thái | Cùng một cấu trúc, giá trị kênh khác nhau |

Nếu viết toàn bộ logic trong một khối `if/else` hoặc `switch` phân nhánh theo tên kênh, mỗi kênh mới lại buộc ta mở khối phân nhánh. Những trường hợp khác nhau còn dễ chia sẻ sai dữ liệu, trùng mã kiểm tra và khiến kiểm thử khó tách biệt. Với vài nhánh ngắn, lựa chọn đó vẫn có thể đủ đơn giản; vấn đề xuất hiện khi số cách xử lý và quy tắc tăng lên.

Ta tách ba vai trò:

1. **Yêu cầu** (`NotificationRequest`): dữ liệu bất biến mà mọi kênh nhận.
2. **Hợp đồng** (`NotificationChannel`): mọi kênh đều có `name()` và `send(request)`.
3. **Bộ điều phối** (`NotificationService`): sử dụng danh sách các kênh qua cùng kiểu `NotificationChannel`, không cần biết chi tiết email, SMS hoặc thông báo trong ứng dụng.

## 2. Interface: thống nhất cách gọi, cho phép triển khai khác nhau

`interface NotificationChannel` chỉ công bố thao tác mà bên gọi được phép dựa vào:

```java
interface NotificationChannel {
    String name();
    SendResult send(NotificationRequest request);
}
```

`EmailChannel`, `SmsChannel` và `InAppChannel` đều có thể được xem là `NotificationChannel`. Khi `NotificationService` gọi `channel.send(request)`, Java chọn phiên bản phương thức của **đối tượng thực tế** tại thời điểm chạy (dynamic dispatch). Kiểu biến là interface; hành vi thực thi đến từ lớp triển khai.

Hợp đồng ở đây cần được hiểu cả về **ý nghĩa**, không chỉ chữ ký: nhận một yêu cầu hợp lệ, thực hiện thao tác của kênh và trả `SendResult`; nếu xảy ra lỗi thì phải có chính sách báo lỗi rõ ràng. Việc khai báo interface **không tự động** bảo đảm mọi lớp có cùng chất lượng xử lý, validation hay tính an toàn khi gửi nhiều lần.

Một interface còn có thể khai báo `default`, `static` và phương thức `private` hỗ trợ triển khai. Tuy nhiên interface không có constructor và không giữ trạng thái instance như một lớp cơ sở. Các trường khai báo trên interface là hằng `public static final`; tránh đặt dữ liệu thay đổi của từng kênh ở đây.

## 3. Abstract class: chia sẻ quy trình chung khi các lớp thực sự có quan hệ

Email và SMS trong ví dụ cùng có các bước: kiểm tra đối tượng yêu cầu, ghi nhận bước kiểm tra, thực hiện gửi rồi tạo kết quả. Ta có thể gom phần **quy trình giống nhau** vào lớp trừu tượng:

```java
abstract class AbstractNotificationChannel implements NotificationChannel {
    @Override
    public final SendResult send(NotificationRequest request) {
        // Kiểm tra chung -> thực hiện riêng -> tạo kết quả chung.
        ...
    }

    protected abstract void deliver(NotificationRequest request);
}
```

*Đây là đoạn minh họa cấu trúc, chưa phải một chương trình độc lập; mã chạy đầy đủ nằm ở mục 4.*

- `abstract class` **không thể khởi tạo trực tiếp** bằng `new AbstractNotificationChannel()`, nhưng có thể có constructor, thuộc tính instance, phương thức cụ thể và phương thức abstract.
- `send()` đã được triển khai và đánh dấu `final`: lớp con không thể bỏ qua thứ tự xử lý đã ấn định.
- `deliver()` là “điểm mở rộng” do lớp con hiện thực. Đây là dạng đơn giản của **Template Method**: lớp cha giữ khung thuật toán, lớp con cung cấp bước thay đổi.
- Email và SMS kế thừa `AbstractNotificationChannel`; chúng cũng thỏa interface `NotificationChannel` vì lớp cha đã `implements` interface ấy.
- Một lớp Java chỉ `extends` **một** lớp trực tiếp, nhưng có thể `implements` nhiều interface. Do đó không ép mọi kênh vào cùng lớp cha nếu chúng không chia sẻ được một quy trình có ý nghĩa.

`InAppChannel` sẽ **implements interface trực tiếp** để chứng minh đây là hợp đồng độc lập với hệ kế thừa. Nó không cần thực hiện bước ghi nhận kiểm tra mà lớp cha đặt ra.

## 4. Chương trình Java 17 hoàn chỉnh

Lưu mã sau vào **`Main.java`**. Toàn bộ kiểu phụ đều là thành phần lồng trong `Main`, nên có thể biên dịch bằng một tệp. Đây là **mô phỏng gửi thông báo trên console**: không gọi SMTP, nhà cung cấp SMS hay API đẩy thông báo; `SENT` là kết quả mô phỏng.

```java
import java.util.List;
import java.util.Objects;

public class Main {
    record NotificationRequest(String customerId, String message) {
        NotificationRequest {
            Objects.requireNonNull(customerId, "customerId");
            Objects.requireNonNull(message, "message");
            if (customerId.isBlank() || message.isBlank()) {
                throw new IllegalArgumentException("Thông tin không được để trống");
            }
        }
    }

    record SendResult(String channel, String status) {}

    interface NotificationChannel {
        String name();
        SendResult send(NotificationRequest request);
    }

    static abstract class AbstractNotificationChannel
            implements NotificationChannel {
        @Override
        public final SendResult send(NotificationRequest request) {
            Objects.requireNonNull(request, "request");
            System.out.println("Kiểm tra yêu cầu: " + request.customerId());
            deliver(request);
            return new SendResult(name(), "SENT");
        }

        protected abstract void deliver(NotificationRequest request);
    }

    static final class EmailChannel extends AbstractNotificationChannel {
        @Override
        public String name() {
            return "EMAIL";
        }

        @Override
        protected void deliver(NotificationRequest request) {
            System.out.println("EMAIL -> " + request.customerId()
                    + ": " + request.message());
        }
    }

    static final class SmsChannel extends AbstractNotificationChannel {
        @Override
        public String name() {
            return "SMS";
        }

        @Override
        protected void deliver(NotificationRequest request) {
            System.out.println("SMS -> " + request.customerId()
                    + ": " + request.message());
        }
    }

    static final class InAppChannel implements NotificationChannel {
        @Override
        public String name() {
            return "IN_APP";
        }

        @Override
        public SendResult send(NotificationRequest request) {
            Objects.requireNonNull(request, "request");
            System.out.println("IN_APP -> " + request.customerId()
                    + ": " + request.message());
            return new SendResult(name(), "SENT");
        }
    }

    static final class NotificationService {
        private final List<NotificationChannel> channels;

        NotificationService(List<NotificationChannel> channels) {
            this.channels = List.copyOf(channels);
        }

        void sendAll(NotificationRequest request) {
            for (NotificationChannel channel : channels) {
                SendResult result = channel.send(request);
                System.out.println("Kết quả " + result.channel()
                        + ": " + result.status());
            }
        }
    }

    public static void main(String[] args) {
        NotificationRequest request = new NotificationRequest(
                "KH-42", "Đơn hàng đã được xác nhận");

        NotificationService service = new NotificationService(List.of(
                new EmailChannel(),
                new SmsChannel(),
                new InAppChannel()));

        service.sendAll(request);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac Main.java
java Main
```

Kết quả chuẩn (UTF-8 khi terminal hỗ trợ tiếng Việt):

```text
Kiểm tra yêu cầu: KH-42
EMAIL -> KH-42: Đơn hàng đã được xác nhận
Kết quả EMAIL: SENT
Kiểm tra yêu cầu: KH-42
SMS -> KH-42: Đơn hàng đã được xác nhận
Kết quả SMS: SENT
IN_APP -> KH-42: Đơn hàng đã được xác nhận
Kết quả IN_APP: SENT
```

**Theo dõi luồng xử lý:** `main()` tạo **một** `NotificationRequest`, sau đó đưa đúng đối tượng đó lần lượt vào ba triển khai. `NotificationService` chỉ thấy ba phần tử kiểu `NotificationChannel`. Hai phần tử đầu chạy `send()` dùng chung của `AbstractNotificationChannel`, rồi lần lượt gọi `EmailChannel.deliver()` và `SmsChannel.deliver()`; phần tử cuối chạy `InAppChannel.send()` trực tiếp. Vì thế hai kênh đầu in thêm dòng “Kiểm tra yêu cầu”, còn kênh thứ ba thì không.

`record` cung cấp đối tượng mang dữ liệu với các accessor `customerId()`, `message()`. Constructor rút gọn kiểm tra `null` và chuỗi chỉ gồm khoảng trắng, nên ví dụ có điểm kiểm tra tính hợp lệ thống nhất khi tạo yêu cầu. `List.copyOf(channels)` tạo danh sách không thể thêm/xóa phần tử qua biến `channels`; nó **không** biến các đối tượng kênh thành bất biến.

## 5. Điều gì thực sự mang lại đa hình?

Quan sát dòng gọi trong vòng lặp:

```java
for (NotificationChannel channel : channels) {
    SendResult result = channel.send(request);
    // ...
}
```

Lệnh gọi giống nhau nhưng hành vi được chọn theo đối tượng:

| Đối tượng runtime | Kiểu tham chiếu trong vòng lặp | Phần triển khai `send()` chạy | Bước riêng |
| --- | --- | --- | --- |
| `EmailChannel` | `NotificationChannel` | `AbstractNotificationChannel.send()` | `EmailChannel.deliver()` |
| `SmsChannel` | `NotificationChannel` | `AbstractNotificationChannel.send()` | `SmsChannel.deliver()` |
| `InAppChannel` | `NotificationChannel` | `InAppChannel.send()` | Không sử dụng lớp cha trừu tượng |

Hợp đồng interface là **đa hình theo kiểu**; việc override phương thức trong hệ kế thừa là một cách cung cấp **đa hình hành vi**. Một tham chiếu có kiểu interface chỉ gọi trực tiếp được những phương thức mà interface công bố, dù lớp cụ thể có thêm phương thức riêng.

Trong ví dụ, chương trình có *cả* hai ý tưởng: `NotificationService` phụ thuộc vào **interface**, còn một số lớp triển khai chọn tái sử dụng **abstract class**. Đây là lựa chọn độc lập và có thể phối hợp.

## 6. Mở rộng một cách xử lý mới mà không sửa bộ điều phối

Giả sử cần thêm kênh `WebhookChannel`. Ta có thể `implements NotificationChannel` trực tiếp, tương tự `InAppChannel`, rồi thêm một đối tượng vào danh sách tại nơi cấu hình:

```java
// Ví dụ về điểm cấu hình; đoạn này không phải tệp Java độc lập.
NotificationService service = new NotificationService(List.of(
        new EmailChannel(),
        new SmsChannel(),
        new InAppChannel(),
        new WebhookChannel()));
```

`WebhookChannel` phải được định nghĩa để ví dụ mở rộng ở trên biên dịch. Điểm cần thấy là **mã của `NotificationService.sendAll()` không cần sửa**. Nơi lắp ghép đối tượng (ở đây là `main()`) vẫn phải được cập nhật để biết kênh mới. Trong ứng dụng lớn, có thể cấu hình danh sách thông qua dependency injection; interface tự nó không tự phát hiện lớp triển khai.

Khi nào chọn `extends AbstractNotificationChannel`? Khi kênh mới cần chính quy trình kiểm tra → giao việc → tạo kết quả, với thứ tự không được thay đổi. Khi nào `implements NotificationChannel` trực tiếp? Khi kênh dùng quy trình khác nhưng vẫn đáp ứng hợp đồng chung. Nếu hai lớp chỉ trùng vài dòng nhỏ, một **thành phần dùng chung được truyền vào** (composition) đôi khi phù hợp hơn một lớp cha.

## 7. Giới hạn của ví dụ và những quyết định khi áp dụng thực tế

| Vấn đề | Ví dụ hiện tại | Khi triển khai hệ thống thật |
| --- | --- | --- |
| Gửi dữ liệu | `System.out.println()` | Adapter tích hợp SMTP/SMS/push; credentials và cấu hình tách riêng |
| Trạng thái | Trả `SENT` sau khi in | Phân biệt chấp nhận xử lý, gửi đến provider, giao thành công và thất bại |
| Kiểm tra yêu cầu | `record` không cho null/rỗng | Kiểm tra thêm định dạng, quyền truy cập, độ dài, định tuyến đích |
| Khi một kênh lỗi | Ngoại lệ dừng `sendAll()` | Quyết định fail-fast, tiếp tục kênh khác, retry, timeout và idempotency |
| Gọi tuần tự | Thực hiện theo thứ tự danh sách | Cân nhắc bất đồng bộ, đồng thời và giới hạn tài nguyên |
| Lưu dấu vết | In console | Log có ngữ cảnh, metrics, tracing; không ghi lộ dữ liệu nhạy cảm |

Không nên mặc định rằng “gọi `send()` trả `SENT`” đồng nghĩa khách đã nhận được thông báo. Trong hệ thống phân tán, giao thành công có thể chỉ được xác nhận bằng callback hoặc sự kiện từ provider. Hãy định nghĩa nghĩa của `SendResult` phù hợp với hệ thống thực và chính sách lỗi trước khi đổi mã mô phỏng thành mã sản xuất.

## 8. Những nhầm lẫn thường gặp

- **“Có interface thì khỏi cần lớp trừu tượng.”** Interface thống nhất hợp đồng; abstract class có thể lưu state và quy trình dùng chung. Có thể dùng cả hai như chương trình trên.
- **“Abstract class bắt buộc chỉ chứa abstract methods.”** Sai: nó có thể chứa constructor, field, phương thức cụ thể, `final` và phương thức abstract; thậm chí một lớp `abstract` có thể không khai báo abstract method nào.
- **“Mọi subclass đều phải override `send()`.”** Sai: hai lớp kế thừa `final send()` từ lớp cha và chỉ hiện thực `deliver()`. Override phương thức `final` là lỗi biên dịch.
- **“Thêm interface là tự động có tính mở rộng.”** Cần giữ hợp đồng ổn định, chọn nơi khởi tạo/đăng ký implementation và tránh đưa `instanceof` hoặc `switch` trên từng lớp cụ thể trở lại `NotificationService`.
- **“Kế thừa chỉ để tránh trùng mã.”** Nếu các lớp không chia sẻ cùng bản chất/quy trình, kế thừa có thể tạo ràng buộc sai. Ưu tiên composition khi chỉ muốn dùng chung một phụ thuộc hoặc chính sách.
- **“Đa hình là overload.”** Overload chọn chữ ký phù hợp theo tham số ở thời điểm biên dịch; ví dụ này dùng override/triển khai interface và dynamic dispatch lúc chạy.
- **“Kiểm tra một lần thì hệ thống chắc chắn an toàn.”** Validation khi tạo `NotificationRequest` bảo vệ dữ liệu của record; vẫn cần xử lý request `null`, lỗi provider và các điều kiện nghiệp vụ riêng.

## 9. Tự kiểm tra hiểu bài

1. Vì sao `NotificationService` vẫn biên dịch nếu một kênh mới được viết bằng cách `implements NotificationChannel` mà không `extends AbstractNotificationChannel`?
2. Nếu xóa từ khóa `final` khỏi `AbstractNotificationChannel.send()`, lớp con có thể làm gì khiến quy trình kiểm tra chung không còn được thực thi?
3. Vì sao chỉ email và SMS in dòng “Kiểm tra yêu cầu”, dù cả ba cùng nhận một `NotificationRequest`?
4. Thử thêm `ConsoleChannel` implements `NotificationChannel` và đưa vào danh sách. Kiểm tra rằng `NotificationService.sendAll()` không thay đổi.
5. Thử làm `EmailChannel.deliver()` ném `IllegalStateException`. Dự đoán các kênh còn lại có chạy hay không trong bản hiện tại; sau đó thiết kế chính sách xử lý lỗi phù hợp với yêu cầu nghiệp vụ.

**Kết luận học tập:** Khi **một yêu cầu có nhiều cách xử lý**, mô hình hữu ích là một dữ liệu đầu vào chung + một interface thể hiện khả năng + các lớp triển khai độc lập. Chỉ thêm abstract class ở nơi thật sự có quy trình chung cần tái sử dụng. Đa hình cho phép bên điều phối gửi cùng một lệnh qua hợp đồng đó, còn quyết định cụ thể được thực hiện bởi đối tượng tại runtime.
