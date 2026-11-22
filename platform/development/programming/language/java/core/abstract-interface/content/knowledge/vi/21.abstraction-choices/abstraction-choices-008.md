# Đảo ngược phụ thuộc bằng tham số hoặc constructor trong Java

Đảo ngược phụ thuộc (Dependency Inversion Principle, DIP) là một trong năm nguyên tắc SOLID. Ý tưởng chính là **mã nghiệp vụ cấp cao nên phụ thuộc vào abstraction (giao diện hoặc lớp trừu tượng), còn chi tiết cấp thấp cũng triển khai hoặc phụ thuộc vào abstraction đó**. Nhờ vậy, logic nghiệp vụ không bị khóa vào một cách gửi thông báo, lưu dữ liệu hay gọi dịch vụ cụ thể.

Trong Java, có thể truyền dependency vào một đối tượng qua constructor hoặc truyền vào một phương thức qua tham số. Đây là các cách tiêm phụ thuộc (dependency injection, DI). Chúng giúp áp dụng DIP, nhưng bản thân việc truyền tham số chưa đủ để bảo đảm kiến trúc tuân thủ DIP: kiểu tham số và hướng phụ thuộc vẫn cần được thiết kế đúng.

## 1. Vấn đề khi phụ thuộc trực tiếp vào lớp cụ thể

Giả sử dịch vụ cảnh báo phải gửi thông báo qua email:

~~~java
final class AlertService {
    private final EmailChannel email = new EmailChannel();

    void alert(String recipient, String message) {
        email.send(recipient, message);
    }
}
~~~

Lớp `AlertService` tự tạo `EmailChannel`. Nó vừa quyết định khi nào gửi cảnh báo, vừa quyết định sử dụng cơ chế gửi nào. Nếu muốn gửi SMS, dùng một nhà cung cấp khác hoặc kiểm thử mà không gửi email thật, ta phải sửa hoặc thay thế cách tạo dependency bên trong dịch vụ.

Vấn đề không nằm ở việc `EmailChannel` là một class. Vấn đề là logic cấp cao bị gắn chặt với một chi tiết triển khai. Một abstraction nhỏ cho phép dịch vụ chỉ biết rằng nó có thể gửi thông báo, không cần biết cách gửi cụ thể.

## 2. Tách hợp đồng bằng interface

Định nghĩa một interface mô tả khả năng mà nghiệp vụ cần:

~~~java
interface NotificationChannel {
    void send(String recipient, String message);
}
~~~

Các cách gửi khác nhau triển khai cùng hợp đồng:

~~~java
final class EmailChannel implements NotificationChannel {
    @Override
    public void send(String recipient, String message) {
        System.out.println("EMAIL to " + recipient + ": " + message);
    }
}

final class SmsChannel implements NotificationChannel {
    @Override
    public void send(String recipient, String message) {
        System.out.println("SMS to " + recipient + ": " + message);
    }
}
~~~

Giờ `AlertService` có thể phụ thuộc vào `NotificationChannel`. `EmailChannel` và `SmsChannel` là các chi tiết cụ thể cùng triển khai abstraction. Khi thêm một kênh khác, chẳng hạn push notification, chỉ cần triển khai interface nếu hợp đồng hiện tại đáp ứng nhu cầu.

## 3. Tiêm dependency qua constructor

Constructor injection truyền dependency vào lúc tạo đối tượng. Đây thường là lựa chọn phù hợp khi dependency là bắt buộc và cần được giữ ổn định trong suốt vòng đời đối tượng.

~~~java
import java.util.Objects;

final class AlertService {
    private final NotificationChannel channel;

    AlertService(NotificationChannel channel) {
        this.channel = Objects.requireNonNull(channel, "channel must not be null");
    }

    void alert(String recipient, String message) {
        channel.send(recipient, message);
    }
}
~~~

Các điểm quan trọng:

- Trường `channel` khai báo theo interface, không theo `EmailChannel` hay `SmsChannel`.
- Constructor nhận dependency từ bên ngoài. `AlertService` không tự gọi `new EmailChannel()`.
- Trường `final` giúp dependency không bị thay thế sau khi đối tượng được khởi tạo.
- `Objects.requireNonNull` làm lỗi cấu hình lộ ra ngay khi tạo đối tượng, thay vì phát sinh muộn khi gửi thông báo.

Nơi khởi tạo ứng dụng quyết định implementation nào được dùng:

~~~java
AlertService emailAlerts = new AlertService(new EmailChannel());
AlertService smsAlerts = new AlertService(new SmsChannel());
~~~

Cùng một lớp nghiệp vụ có thể được cấu hình bằng hai implementation khác nhau. Khi muốn thay đổi kênh mặc định, phần cấu hình khởi tạo đổi cách truyền dependency; logic bên trong `AlertService` vẫn giữ nguyên.

## 4. Tiêm dependency qua tham số phương thức

Đôi khi dependency chỉ cần cho một thao tác, hoặc mỗi lần gọi cần một implementation khác nhau. Khi đó, có thể truyền abstraction qua tham số:

~~~java
final class NotificationWorkflow {
    static void sendOnce(
            NotificationChannel channel,
            String recipient,
            String message) {
        Objects.requireNonNull(channel, "channel must not be null")
               .send(recipient, message);
    }
}
~~~

Ví dụ sử dụng:

~~~java
NotificationWorkflow.sendOnce(
        new EmailChannel(), "ops@example.com", "Daily report ready");
NotificationWorkflow.sendOnce(
        new SmsChannel(), "+84901234567", "Deployment started");
~~~

Phương thức chỉ yêu cầu một `NotificationChannel`; nó không cần biết implementation cụ thể. Người gọi chọn dependency phù hợp cho từng lần thực thi. Vì ví dụ sử dụng `Objects.requireNonNull`, file hoàn chỉnh ở phần tiếp theo có import `java.util.Objects`.

Constructor injection và parameter injection giải quyết hai nhu cầu khác nhau:

| Cách truyền | Phù hợp khi | Đặc điểm |
|---|---|---|
| Constructor | Dependency bắt buộc cho hầu hết hành vi của đối tượng | Có sẵn sau khi khởi tạo; dễ giữ bất biến và dễ nhận ra dependency cần thiết |
| Tham số phương thức | Dependency chỉ cần cho một thao tác hoặc thay đổi theo lần gọi | Phạm vi sử dụng hẹp; người gọi chọn implementation ở từng lần gọi |
| Setter | Dependency thực sự tùy chọn hoặc có thể cấu hình lại sau khi tạo | Đối tượng có thể tồn tại ở trạng thái chưa được cấu hình; cần quản lý tính hợp lệ cẩn thận |

Không nên chọn parameter injection chỉ vì nó có vẻ linh hoạt hơn. Nếu mọi thao tác của dịch vụ đều cần cùng một dependency bắt buộc, constructor thường biểu đạt ý định rõ ràng hơn. Ngược lại, nếu mỗi lần gọi cần một chiến lược riêng, truyền qua tham số có thể tự nhiên hơn.

## 5. Ví dụ hoàn chỉnh chạy được trên Java 17

Lưu mã dưới đây vào file `DependencyInversionDemo.java`. Ví dụ minh họa constructor injection và parameter injection trong một chương trình độc lập.

~~~java
import java.util.Objects;

public class DependencyInversionDemo {
    public static void main(String[] args) {
        AlertService emailAlerts = new AlertService(new EmailChannel());
        emailAlerts.alert("linh@example.com", "Build succeeded");

        AlertService smsAlerts = new AlertService(new SmsChannel());
        smsAlerts.alert("+84901234567", "Deployment started");

        NotificationWorkflow.sendOnce(
                new EmailChannel(), "ops@example.com", "Daily report ready");
    }
}

interface NotificationChannel {
    void send(String recipient, String message);
}

final class EmailChannel implements NotificationChannel {
    @Override
    public void send(String recipient, String message) {
        System.out.println("EMAIL to " + recipient + ": " + message);
    }
}

final class SmsChannel implements NotificationChannel {
    @Override
    public void send(String recipient, String message) {
        System.out.println("SMS to " + recipient + ": " + message);
    }
}

final class AlertService {
    private final NotificationChannel channel;

    AlertService(NotificationChannel channel) {
        this.channel = Objects.requireNonNull(
                channel, "channel must not be null");
    }

    void alert(String recipient, String message) {
        channel.send(recipient, message);
    }
}

final class NotificationWorkflow {
    static void sendOnce(
            NotificationChannel channel,
            String recipient,
            String message) {
        Objects.requireNonNull(channel, "channel must not be null")
               .send(recipient, message);
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 DependencyInversionDemo.java
java DependencyInversionDemo
~~~

Stdout chính xác:

~~~text
EMAIL to linh@example.com: Build succeeded
SMS to +84901234567: Deployment started
EMAIL to ops@example.com: Daily report ready
~~~

Tất cả các kiểu phụ trợ không khai báo `public` nên có thể nằm cùng file với lớp `public` `DependencyInversionDemo`. Lệnh biên dịch trên dùng Java 17 làm phiên bản đích và không cần framework DI.

## 6. Vì sao đây là đảo ngược phụ thuộc?

Có hai hướng phụ thuộc cần quan sát:

- **Trước khi tách abstraction:** `AlertService` biết và tự tạo `EmailChannel`. Thay đổi chi tiết gửi email có thể buộc phải sửa lớp nghiệp vụ.
- **Sau khi tách abstraction:** `AlertService` chỉ tham chiếu `NotificationChannel`. `EmailChannel` và `SmsChannel` triển khai interface; phần khởi tạo bên ngoài kết nối một implementation với dịch vụ.

Sơ đồ quan hệ sau khi thiết kế lại (mũi tên thể hiện phụ thuộc ở mã nguồn hoặc thao tác tại nơi khởi tạo):

~~~text
AlertService --------- sử dụng --------> NotificationChannel
                                            ^              ^
                                            | implements   | implements
                                       EmailChannel     SmsChannel

CompositionRoot --- tạo --------> EmailChannel hoặc SmsChannel
CompositionRoot --- truyền -----> new AlertService(channel)
~~~

`AlertService` chỉ biết kiểu `NotificationChannel`. Hai channel cụ thể triển khai hợp đồng đó, còn `CompositionRoot` là phần mã ở `main` quyết định tạo channel nào và truyền nó vào constructor. Hướng phụ thuộc mã nguồn không bị đảo sai: chính `AlertService` phụ thuộc vào interface, còn implementation cũng phụ thuộc vào cùng interface.

DIP là nguyên tắc kiến trúc về hướng phụ thuộc. DI là kỹ thuật cung cấp một đối tượng mà lớp cần dùng. Constructor hoặc parameter injection có thể hỗ trợ DIP khi dependency được khai báo qua abstraction. Nếu constructor nhận trực tiếp `EmailChannel`, dù dependency được truyền từ ngoài vào, lớp vẫn bị gắn với chi tiết email.

## 7. Kiểm thử dễ hơn khi dependency được tiêm vào

Có thể truyền một implementation giả (fake) hoặc mock để kiểm tra logic mà không gọi mạng, gửi email thật hay phụ thuộc vào nhà cung cấp bên ngoài. Ví dụ fake đơn giản:

~~~java
final class RecordingChannel implements NotificationChannel {
    String lastRecipient;
    String lastMessage;

    @Override
    public void send(String recipient, String message) {
        lastRecipient = recipient;
        lastMessage = message;
    }
}
~~~

Trong bài kiểm thử, tạo `RecordingChannel`, truyền nó vào `AlertService`, gọi `alert`, rồi kiểm tra `lastRecipient` và `lastMessage`. Vì fake triển khai cùng interface, lớp nghiệp vụ không cần nhánh đặc biệt dành riêng cho môi trường kiểm thử.

Đây là một lợi ích lớn của việc phụ thuộc vào abstraction: hành vi bên ngoài có thể được thay thế trong kiểm thử, còn logic nghiệp vụ được kiểm tra một cách có kiểm soát.

## 8. Những lỗi thiết kế thường gặp

**Tự tạo lớp cụ thể bên trong dịch vụ.** Nếu `AlertService` vẫn gọi `new EmailChannel()`, việc thêm constructor nhận interface không giải quyết triệt để coupling nếu dependency được bỏ qua hoặc ghi đè bằng một đối tượng tự tạo bên trong.

**Truyền lớp cụ thể thay vì abstraction.** Tham số `EmailChannel channel` giới hạn người gọi vào một implementation. Nếu nghiệp vụ cần nhiều loại kênh, nên nhận `NotificationChannel`.

**Nhầm DI với DIP.** Nhận dependency từ constructor chưa đủ. Nếu kiểu của dependency là lớp triển khai cụ thể, hoặc module cấp cao vẫn phụ thuộc vào chi tiết cấp thấp, nguyên tắc đảo ngược phụ thuộc chưa được thể hiện đầy đủ.

**Dùng setter cho dependency bắt buộc.** Đối tượng có thể được tạo rồi gọi trước khi setter cấu hình dependency. Với dependency cần thiết để đối tượng hoạt động hợp lệ, constructor thường an toàn hơn.

**Cho phép dependency null.** Nếu null không phải một trạng thái hợp lệ, kiểm tra ngay tại điểm tiếp nhận. Cần thống nhất hợp đồng nullability thay vì để lỗi xảy ra sâu bên trong xử lý.

**Tạo abstraction không có giá trị.** Không cần thêm interface cho mọi class chỉ để tuân thủ một mẫu. Abstraction hữu ích khi biểu đạt một hợp đồng ổn định, tách chính sách nghiệp vụ khỏi chi tiết triển khai hoặc cho phép thay thế/kiểm thử có ý nghĩa.

**Đưa việc lựa chọn implementation vào khắp nơi.** Nếu nhiều lớp nghiệp vụ tự quyết định bằng `new EmailChannel()` hoặc `new SmsChannel()`, coupling vẫn lan rộng. Tập trung việc tạo và kết nối các đối tượng ở nơi cấu hình ứng dụng, thường được gọi là composition root.

## 9. Có cần framework dependency injection không?

Không. Java hỗ trợ truyền đối tượng trực tiếp qua constructor và tham số phương thức; ví dụ ở trên không dùng thư viện ngoài.

Trong ứng dụng lớn, framework DI có thể tự tạo dependency, quản lý vòng đời và kết nối các thành phần theo cấu hình. Framework thay đổi cách đối tượng được tạo và lắp ghép, nhưng không thay thế việc thiết kế đúng abstraction. Một lớp nhận trực tiếp lớp triển khai cụ thể vẫn có coupling đó dù được framework khởi tạo.

## 10. Checklist áp dụng

- Xác định phần nghiệp vụ cấp cao cần khả năng gì, rồi biểu diễn khả năng đó bằng interface hoặc abstraction phù hợp.
- Để các lớp cụ thể triển khai hợp đồng và chứa chi tiết thực thi.
- Dùng constructor cho dependency bắt buộc, ổn định theo vòng đời đối tượng.
- Dùng tham số phương thức khi dependency chỉ cần cho một thao tác hoặc lựa chọn thay đổi theo lần gọi.
- Tạo và kết nối implementation ở nơi khởi tạo ứng dụng, thay vì rải `new ConcreteClass()` trong logic nghiệp vụ.
- Kiểm tra nullability, quyền sở hữu và vòng đời của dependency theo hợp đồng của ứng dụng.
- Viết kiểm thử bằng fake hoặc mock để xác nhận hành vi mà không gọi hệ thống bên ngoài.
- Xem xét liệu việc thay một implementation có buộc phải sửa lớp nghiệp vụ hay không; nếu có, kiểm tra lại hướng phụ thuộc.

Thiết kế hướng abstraction giúp mã nghiệp vụ ổn định trước các thay đổi của chi tiết kỹ thuật. Constructor injection làm dependency bắt buộc trở nên rõ ràng; parameter injection giúp một thao tác sử dụng implementation do bên gọi lựa chọn. Cả hai đều hữu ích khi được dùng đúng phạm vi và kết hợp với hợp đồng abstraction được thiết kế hợp lý.
