# Lợi ích của việc tách logic nghiệp vụ khỏi quyết định chọn biến thể

Trong một ứng dụng, **logic nghiệp vụ** trả lời câu hỏi *hệ thống cần làm gì theo quy tắc của miền bài toán?*; còn **quyết định chọn biến thể** trả lời câu hỏi *sử dụng bộ implementation nào để thực hiện công việc đó?* Khi hai trách nhiệm này bị trộn với nhau, mỗi lần thêm một nền tảng, nhà cung cấp hoặc cách triển khai mới đều có nguy cơ buộc lập trình viên sửa các lớp nghiệp vụ vốn không thay đổi về quy tắc.

**Abstract Factory** là một cách giải quyết khi ứng dụng cần tạo **nhiều loại đối tượng liên quan trong cùng một họ sản phẩm**. Thay vì để mã nghiệp vụ chọn từng lớp cụ thể, ứng dụng chọn một concrete factory ở ranh giới khởi tạo và cung cấp factory ấy cho phần cần sử dụng sản phẩm. Phần nghiệp vụ làm việc với **interface sản phẩm**; các factory cụ thể chịu trách nhiệm tạo ra bộ sản phẩm phù hợp với biến thể đã chọn.

Bài thuộc phần **Tổng quan** của module `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY` trong lộ trình **Học về abstract factory trong design pattern**. Trọng tâm là hiểu **lợi ích và giới hạn** của việc tách hai trách nhiệm, không chỉ học cách viết các lớp có hậu tố `Factory`.

Sau bài này, bạn sẽ có thể:

- Nhận biết phần nào là quy tắc nghiệp vụ, phần nào là logic chọn implementation.
- Giải thích tác động của sự phụ thuộc vào lớp cụ thể đối với bảo trì, mở rộng và kiểm thử.
- Trình bày cách Abstract Factory tập trung việc chọn một họ sản phẩm tại điểm cấu hình.
- Đọc ví dụ Java trước và sau khi tách trách nhiệm, chỉ ra những chỗ thay đổi khi thêm biến thể.
- Nhận ra khi Abstract Factory có ích và khi một cơ chế đơn giản hơn là đủ.

## 1. Phân biệt hai loại quyết định

Giả sử hệ thống bán hàng gửi thông báo khi một đơn hàng được bàn giao cho đơn vị vận chuyển. Có hai kênh gửi: **Email** và **SMS**.

Để gửi một thông báo, ứng dụng cần thực hiện ba việc:

1. Xác định **sự kiện nghiệp vụ**: đơn hàng đã được bàn giao và cần thông báo cho khách.
2. Soạn **nội dung nghiệp vụ**: mã đơn hàng và thông tin trạng thái cần báo.
3. **Định dạng và chuyển phát** nội dung theo kênh được chọn: Email cần cách định dạng và bộ gửi Email; SMS cần cách định dạng và bộ gửi SMS.

Hai công việc đầu trả lời *nội dung và thời điểm nào phải thông báo*. Công việc thứ ba trả lời *bộ công nghệ nào thực hiện thông báo*. Một thay đổi như “thông báo thêm mã vận đơn” tác động tới nội dung nghiệp vụ; còn “chuyển từ SMS sang Email” chủ yếu thay đổi cách định dạng, gửi và chọn kênh.

| Câu hỏi cần giải quyết | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| Khi nào khách được thông báo? | Nghiệp vụ / điều phối ca sử dụng | Khi đơn chuyển sang trạng thái đã bàn giao |
| Khách cần biết thông tin gì? | Nghiệp vụ | Mã đơn, trạng thái, mã vận đơn nếu có |
| Nội dung hiển thị theo định dạng nào? | Sản phẩm của một biến thể | Tiêu đề và thân Email hoặc thông điệp SMS |
| Nội dung được chuyển phát bằng gì? | Sản phẩm của một biến thể | Email transport hoặc SMS gateway |
| Dùng bộ Email hay SMS cho lần gửi này? | Cấu hình / ranh giới điều phối | Cấu hình hệ thống hoặc tùy chọn của khách |

Ví dụ có **hai loại sản phẩm liên quan**: bộ định dạng (`MessageFormatter`) và bộ gửi (`MessageSender`). Chúng cần thuộc cùng kênh để tránh việc định dạng thành Email rồi lại chuyển phát qua SMS.

> Việc chọn một họ sản phẩm không phải lúc nào cũng là quyết định cố định khi khởi động: nếu kênh do từng khách hàng lựa chọn, ứng dụng có thể chọn factory tại ranh giới của **mỗi yêu cầu**. Điều quan trọng là quyết định chọn implementation nằm ở nơi thích hợp, không bị lặp trong mọi lớp nghiệp vụ.

## 2. Trước khi tách: mã nghiệp vụ tự chọn từng implementation

Một triển khai ban đầu có thể vừa soạn nội dung vừa khởi tạo các thành phần cụ thể:

~~~java
final class OrderNotificationService {

    void notifyShipped(Order order, Recipient recipient, Channel channel) {
        String content = "Don " + order.id() + " da duoc ban giao.";

        if (channel == Channel.EMAIL) {
            MessageFormatter formatter = new EmailFormatter();
            MessageSender sender = new EmailSender();
            sender.send(recipient, formatter.format(content));
        } else if (channel == Channel.SMS) {
            MessageFormatter formatter = new SmsFormatter();
            MessageSender sender = new SmsSender();
            sender.send(recipient, formatter.format(content));
        } else {
            throw new IllegalArgumentException("Unsupported channel");
        }
    }
}
~~~

Đoạn trên là **một phần của ví dụ**: `Order`, `Recipient`, `Channel`, các interface và implementation sẽ được khai báo ở các phần sau.

Nhìn vào một phương thức, có thể thấy nó đang chịu đồng thời hai nhóm trách nhiệm:

- **Nghiệp vụ:** xây dựng nội dung thông báo cho đơn vừa bàn giao.
- **Chọn và khởi tạo biến thể:** phân nhánh `channel`, biết tên các lớp `EmailFormatter`, `EmailSender`, `SmsFormatter`, `SmsSender`.

Khi thêm kênh thứ ba, chẳng hạn thông báo đẩy (Push), lập trình viên phải cập nhật nhánh chọn implementation ngay trong `OrderNotificationService`. Nếu hệ thống còn các ca sử dụng *đơn bị hủy*, *đơn giao thành công* hoặc *yêu cầu xác nhận*, rất dễ xuất hiện lại cùng một logic chọn kênh ở nhiều nơi.

Điểm đáng chú ý không chỉ là có một câu lệnh `if`. Vấn đề là **lớp nghiệp vụ đang biết những lớp hạ tầng cụ thể nào phải đi cùng nhau**. Khi cấu trúc ứng dụng lớn lên, kiến thức đó có thể bị nhân bản và sinh lỗi trộn biến thể.

~~~java
// Biên dịch vẫn có thể hợp lệ vì cả hai đối tượng
// đều đáp ứng các interface tương ứng:
MessageFormatter formatter = new EmailFormatter();
MessageSender sender = new SmsSender(); // Không cùng họ
~~~

Ví dụ trên là lỗi về **tính nhất quán của họ sản phẩm**. Trình biên dịch Java không biết rằng `EmailFormatter` và `SmsSender` không nên được ghép với nhau; đó là một quy tắc thiết kế phải được thể hiện rõ trong kiến trúc và kiểm thử.

## 3. Cấu trúc Abstract Factory tách quyết định lựa chọn như thế nào?

Đầu tiên, định nghĩa hai **interface sản phẩm** mà phần nghiệp vụ cần sử dụng:

~~~java
interface MessageFormatter {
    String format(String businessContent);
}

interface MessageSender {
    void send(Recipient recipient, String formattedContent);
}
~~~

Sau đó khai báo **Abstract Factory** cho cả hai loại sản phẩm:

~~~java
interface NotificationFactory {
    MessageFormatter createFormatter();
    MessageSender createSender();
}
~~~

Mỗi **Concrete Factory** tạo một bộ implementation tương ứng:

~~~java
final class EmailNotificationFactory implements NotificationFactory {
    @Override
    public MessageFormatter createFormatter() {
        return new EmailFormatter();
    }

    @Override
    public MessageSender createSender() {
        return new EmailSender();
    }
}

final class SmsNotificationFactory implements NotificationFactory {
    @Override
    public MessageFormatter createFormatter() {
        return new SmsFormatter();
    }

    @Override
    public MessageSender createSender() {
        return new SmsSender();
    }
}
~~~

Sơ đồ quan hệ:

~~~mermaid
classDiagram
    class NotificationFactory {
        <<interface>>
        +createFormatter() MessageFormatter
        +createSender() MessageSender
    }
    class EmailNotificationFactory
    class SmsNotificationFactory
    class MessageFormatter {
        <<interface>>
        +format(String) String
    }
    class MessageSender {
        <<interface>>
        +send(Recipient, String) void
    }
    class EmailFormatter
    class SmsFormatter
    class EmailSender
    class SmsSender
    NotificationFactory <|.. EmailNotificationFactory
    NotificationFactory <|.. SmsNotificationFactory
    MessageFormatter <|.. EmailFormatter
    MessageFormatter <|.. SmsFormatter
    MessageSender <|.. EmailSender
    MessageSender <|.. SmsSender
    EmailNotificationFactory ..> EmailFormatter : creates
    EmailNotificationFactory ..> EmailSender : creates
    SmsNotificationFactory ..> SmsFormatter : creates
    SmsNotificationFactory ..> SmsSender : creates
~~~

`NotificationFactory` mô tả **cần tạo những loại sản phẩm nào**, trong khi `EmailNotificationFactory` và `SmsNotificationFactory` quyết định **tạo phiên bản nào của từng loại**.

Mã nghiệp vụ có thể nhận factory từ bên ngoài rồi sử dụng qua abstraction:

~~~java
final class OrderNotificationService {
    private final MessageFormatter formatter;
    private final MessageSender sender;

    OrderNotificationService(NotificationFactory factory) {
        this.formatter = factory.createFormatter();
        this.sender = factory.createSender();
    }

    void notifyShipped(Order order, Recipient recipient) {
        String content = "Don " + order.id() + " da duoc ban giao.";
        sender.send(recipient, formatter.format(content));
    }
}
~~~

Phần nghiệp vụ giờ **không biết tên lớp Email hoặc SMS**, cũng không hỏi `channel` để chọn implementation. Nó chỉ biết nội dung cần thông báo và hai hoạt động trừu tượng: định dạng, chuyển phát.

Ở cách viết này, sản phẩm được tạo trong constructor và sử dụng suốt vòng đời của `OrderNotificationService`. Đây là lựa chọn phù hợp nếu mỗi instance được gắn với **một kênh ổn định**. Nếu kênh thay đổi giữa các lần gọi, hãy tạo service/factory tương ứng theo từng yêu cầu hoặc thiết kế lại ranh giới để nhận factory của yêu cầu đó.

## 4. Ví dụ Java tự chứa: chọn biến thể ở điểm khởi tạo

Ví dụ sau chứa đầy đủ các kiểu cần thiết trong **một file `Demo.java`** để bạn có thể đọc toàn bộ luồng. Các lớp hỗ trợ được khai báo package-private, chỉ `Demo` là `public`. Ví dụ dùng các cú pháp có trong Java 8+ và mô phỏng thao tác gửi bằng `System.out.println` để không cần dịch vụ mạng.

~~~java
import java.util.Objects;

enum Channel {
    EMAIL, SMS
}

final class Order {
    private final String id;

    Order(String id) {
        this.id = Objects.requireNonNull(id, "id");
    }

    String id() {
        return id;
    }
}

final class Recipient {
    private final String email;
    private final String phone;

    Recipient(String email, String phone) {
        this.email = email;
        this.phone = phone;
    }

    String email() {
        return email;
    }

    String phone() {
        return phone;
    }
}

interface MessageFormatter {
    String format(String businessContent);
}

interface MessageSender {
    void send(Recipient recipient, String formattedContent);
}

interface NotificationFactory {
    MessageFormatter createFormatter();
    MessageSender createSender();
}

final class EmailFormatter implements MessageFormatter {
    @Override
    public String format(String businessContent) {
        return "Subject: Order update\n\n" + businessContent;
    }
}

final class SmsFormatter implements MessageFormatter {
    @Override
    public String format(String businessContent) {
        return "SMS: " + businessContent;
    }
}

final class EmailSender implements MessageSender {
    @Override
    public void send(Recipient recipient, String formattedContent) {
        System.out.println("EMAIL to " + recipient.email()
                + ": " + formattedContent);
    }
}

final class SmsSender implements MessageSender {
    @Override
    public void send(Recipient recipient, String formattedContent) {
        System.out.println("SMS to " + recipient.phone()
                + ": " + formattedContent);
    }
}

final class EmailNotificationFactory implements NotificationFactory {
    @Override
    public MessageFormatter createFormatter() {
        return new EmailFormatter();
    }

    @Override
    public MessageSender createSender() {
        return new EmailSender();
    }
}

final class SmsNotificationFactory implements NotificationFactory {
    @Override
    public MessageFormatter createFormatter() {
        return new SmsFormatter();
    }

    @Override
    public MessageSender createSender() {
        return new SmsSender();
    }
}

final class NotificationFactorySelector {
    private NotificationFactorySelector() {}

    static NotificationFactory forChannel(Channel channel) {
        Objects.requireNonNull(channel, "channel");
        switch (channel) {
            case EMAIL:
                return new EmailNotificationFactory();
            case SMS:
                return new SmsNotificationFactory();
            default:
                throw new IllegalArgumentException("Unsupported channel");
        }
    }
}

final class OrderNotificationService {
    private final MessageFormatter formatter;
    private final MessageSender sender;

    OrderNotificationService(NotificationFactory factory) {
        Objects.requireNonNull(factory, "factory");
        this.formatter = Objects.requireNonNull(
                factory.createFormatter(), "formatter");
        this.sender = Objects.requireNonNull(
                factory.createSender(), "sender");
    }

    void notifyShipped(Order order, Recipient recipient) {
        Objects.requireNonNull(order, "order");
        Objects.requireNonNull(recipient, "recipient");

        String content = "Don " + order.id() + " da duoc ban giao.";
        sender.send(recipient, formatter.format(content));
    }
}

public final class Demo {
    public static void main(String[] args) {
        Order order = new Order("A-123");
        Recipient recipient = new Recipient(
                "customer@example.test", "+84900000000");

        Channel selectedChannel = Channel.EMAIL;
        NotificationFactory factory =
                NotificationFactorySelector.forChannel(selectedChannel);

        OrderNotificationService service =
                new OrderNotificationService(factory);
        service.notifyShipped(order, recipient);
    }
}
~~~

Với `Channel.EMAIL`, đầu ra mô phỏng dự kiến:

~~~text
EMAIL to customer@example.test: Subject: Order update

Don A-123 da duoc ban giao.
~~~

Đổi duy nhất `selectedChannel` thành `Channel.SMS` tại `Demo.main()`, đầu ra dự kiến thành:

~~~text
SMS to +84900000000: SMS: Don A-123 da duoc ban giao.
~~~

Điểm quan sát quan trọng là **phương thức `notifyShipped()` không đổi** giữa hai lần sử dụng. Nó vẫn xây dựng thông điệp nghiệp vụ và gọi hai interface như trước. Việc chuyển kênh được giải quyết tại nơi chọn factory.

Trong hệ thống thực, `EmailSender` và `SmsSender` có thể dùng SMTP, API bên thứ ba hoặc hàng đợi. Nếu nội dung phải hỗ trợ tiếng Việt có dấu, quốc tế hóa, giới hạn chiều dài SMS hoặc chính sách retry, cần xác định chúng thuộc hợp đồng của formatter/sender hay thuộc quy tắc nghiệp vụ chung trước khi triển khai. `System.out.println` chỉ là cơ chế mô phỏng.

## 5. Luồng phụ thuộc trước và sau khi tách

Trước khi refactor, lớp nghiệp vụ thường phụ thuộc trực tiếp vào các implementation:

~~~mermaid
flowchart TD
    A["OrderNotificationService"] --> B{"Chọn Channel"}
    B --> C["EmailFormatter + EmailSender"]
    B --> D["SmsFormatter + SmsSender"]
~~~

Sau khi refactor, quyết định chọn kênh được đưa ra ngoài `OrderNotificationService`:

~~~mermaid
flowchart TD
    A["Cấu hình / ca sử dụng"] --> B["NotificationFactorySelector"]
    B --> C["Concrete NotificationFactory"]
    C --> D["OrderNotificationService"]
    D --> E["MessageFormatter"]
    D --> F["MessageSender"]
    C -.-> G["Bộ sản phẩm cùng họ"]
    G -.-> E
    G -.-> F
~~~

Ở góc nhìn phụ thuộc trong mã nguồn:

- `OrderNotificationService` chỉ **tham chiếu đến interface** `NotificationFactory`, `MessageFormatter` và `MessageSender`.
- `EmailNotificationFactory` và `SmsNotificationFactory` biết **các lớp cụ thể** để lắp ráp bộ sản phẩm.
- `NotificationFactorySelector` là nơi biết ánh xạ `Channel.EMAIL → EmailNotificationFactory` và `Channel.SMS → SmsNotificationFactory`.
- Điểm tạo service cung cấp một concrete factory đã chọn; service sử dụng nó mà không chứa nhánh chọn biến thể.

Đây là ứng dụng của **phụ thuộc vào abstraction** và **đảo chiều phụ thuộc (Dependency Inversion Principle)**: logic mức cao không cần nhập các tên lớp hạ tầng cụ thể, trong khi các implementation tuân theo hợp đồng mà logic mức cao sử dụng.

Lưu ý: quan hệ giữa **đối tượng tại runtime** và **phụ thuộc trong mã nguồn** là hai thứ khác nhau. Khi chạy, service vẫn sử dụng một `EmailSender` hoặc `SmsSender` cụ thể; điểm khác biệt là **mã nguồn của service không phụ thuộc trực tiếp vào tên lớp** ấy.

## 6. Các lợi ích thực tế của việc tách trách nhiệm

### 6.1. Giảm coupling giữa nghiệp vụ và hạ tầng

Nếu mã nghiệp vụ chứa `new EmailSender()`, nó cần biết lớp triển khai, có thể cả tham số khởi tạo và thư viện hạ tầng. Một thay đổi ở SDK gửi Email có thể kéo theo sửa mã nghiệp vụ.

Khi chuyển sang `MessageSender` và `NotificationFactory`, thay đổi liên quan đến cấu hình kết nối và constructor chủ yếu nằm ở factory hoặc implementation của sender. Lớp nghiệp vụ chỉ bị ảnh hưởng nếu **hợp đồng sản phẩm hoặc quy tắc nghiệp vụ thật sự thay đổi**.

Điều này giảm mức độ biết nhau giữa các lớp, nhưng không xóa hết phụ thuộc: các thành phần vẫn phụ thuộc vào **hợp đồng chung**. Đổi interface `MessageSender` vẫn có thể làm thay đổi nhiều nơi sử dụng nó.

### 6.2. Dễ mở rộng theo **họ sản phẩm**

Nếu thêm biến thể `PUSH` với `PushFormatter` và `PushSender`, có thể:

1. Tạo hai lớp sản phẩm implement `MessageFormatter` và `MessageSender`.
2. Tạo `PushNotificationFactory implements NotificationFactory` trả về cặp sản phẩm đó.
3. Bổ sung ánh xạ `Channel.PUSH` tại điểm lựa chọn factory, cùng cấu hình liên quan.

`OrderNotificationService.notifyShipped()` có thể giữ nguyên nếu yêu cầu nghiệp vụ vẫn là “tạo và gửi thông báo đơn đã bàn giao”.

Đây là lợi ích thường được gắn với **Open/Closed Principle**: mở rộng theo biến thể mới nhưng giảm nhu cầu sửa các lớp sử dụng sản phẩm. Tuy nhiên, **không có nghĩa là toàn hệ thống hoàn toàn không cần sửa**. Enum `Channel`, lớp chọn factory, cấu hình, tài liệu và bộ test vẫn có thể phải cập nhật.

### 6.3. Hạn chế phân tán điều kiện chọn biến thể

Nếu nhiều nơi dùng cùng cấu hình kênh, việc lặp các nhánh `if (channel == ...)` khiến mỗi lần bổ sung biến thể phải tìm và sửa nhiều điểm. Một factory được lựa chọn tại ranh giới thích hợp giúp **tập trung quy tắc ánh xạ biến thể → bộ sản phẩm**.

Lợi ích không đến từ việc triệt tiêu toàn bộ câu lệnh `if` hoặc `switch`. Một đoạn `switch` ở `NotificationFactorySelector` là hợp lý, vì **chọn implementation chính là trách nhiệm của thành phần đó**.

### 6.4. Giảm nguy cơ trộn nhầm các sản phẩm không tương thích

Khi một yêu cầu chọn `EmailNotificationFactory`, cả `createFormatter()` lẫn `createSender()` đều được định nghĩa cho họ Email. Mã nghiệp vụ không cần tự nhớ “dùng `EmailFormatter` thì phải dùng `EmailSender`”.

Điều này **giảm điểm có thể gây lỗi**, nhưng không phải sự bảo đảm tuyệt đối: một lập trình viên vẫn có thể viết nhầm `EmailNotificationFactory.createSender()` trả `new SmsSender()`. Kiểu trả về `MessageSender` không ngăn được lỗi đó. Cần kiểm thử **mỗi concrete factory** và kiểm tra tương thích thực tế giữa các sản phẩm.

### 6.5. Dễ thay implementation và viết unit test

Một lớp nghiệp vụ biết interface có thể nhận **test double** thay vì hạ tầng thật. Chẳng hạn, ta có thể quan sát nội dung mà `OrderNotificationService` gửi mà không cần tài khoản Email hay SMS.

Ví dụ minh họa sau dùng JUnit Jupiter (JUnit 5); các lớp `Order`, `Recipient`, `NotificationFactory` và `OrderNotificationService` đã được định nghĩa ở ví dụ trên. Đặt bài test trong cùng một project với mã chính và cấu hình JUnit Jupiter phù hợp:

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderNotificationServiceTest {

    static final class CapturingSender implements MessageSender {
        String sentContent;

        @Override
        public void send(Recipient recipient, String content) {
            this.sentContent = content;
        }
    }

    @Test
    void createsBusinessMessageWithoutKnowingConcreteChannel() {
        CapturingSender sender = new CapturingSender();

        NotificationFactory fakeFactory = new NotificationFactory() {
            @Override
            public MessageFormatter createFormatter() {
                return content -> content;
            }

            @Override
            public MessageSender createSender() {
                return sender;
            }
        };

        OrderNotificationService service =
                new OrderNotificationService(fakeFactory);

        service.notifyShipped(
                new Order("A-123"),
                new Recipient("customer@example.test", "+84900000000"));

        assertEquals("Don A-123 da duoc ban giao.",
                sender.sentContent);
    }
}
~~~

Test chỉ tập trung vào **thông điệp nghiệp vụ cần gửi**. Nó không gọi API gửi Email hay SMS và cũng không cần sửa class nghiệp vụ để gắn `CapturingSender`.

Nên có **nhóm test thứ hai** cho từng concrete factory: kiểm tra factory trả sản phẩm khác `null`, tạo đúng họ, đồng thời formatter và sender tương thích theo yêu cầu. Unit test của service và unit test của factory kiểm tra **hai trách nhiệm khác nhau**.

### 6.6. Rõ ràng hơn khi thay đổi và giao việc

Khi phân chia công việc, đội nghiệp vụ có thể tập trung vào điều kiện thông báo, nội dung và luồng đặt hàng; đội tích hợp xử lý provider, timeout, retry và cơ chế gửi. Hợp đồng `MessageFormatter`, `MessageSender` và `NotificationFactory` giúp các phần gặp nhau tại ranh giới rõ ràng.

Đây không phải bảo đảm tổ chức nhóm tự động tốt hơn; lợi ích đến khi ranh giới kỹ thuật phản ánh đúng **trách nhiệm có lý do thay đổi khác nhau**.

## 7. So sánh tác động khi yêu cầu thay đổi

| Tình huống thay đổi | Khi lớp nghiệp vụ tự chọn lớp cụ thể | Khi chọn Abstract Factory ở ranh giới |
| --- | --- | --- |
| Thêm kênh Push | Có thể phải sửa từng nhánh chọn trong nhiều service | Thêm họ sản phẩm và concrete factory; sửa nơi chọn factory |
| Thay SDK gửi SMS | Các chỗ khởi tạo `SmsSender` có thể bị ảnh hưởng | Thường tập trung ở `SmsSender` và `SmsNotificationFactory` |
| Đổi nội dung “đơn đã bàn giao” | Sửa logic soạn nội dung nghiệp vụ | Vẫn sửa logic soạn nội dung nghiệp vụ |
| Đổi định dạng Email | Logic định dạng có thể lẫn trong service | Sửa `EmailFormatter` nếu hợp đồng không đổi |
| Test nội dung thông báo mà không gửi thật | Khó cô lập nếu service trực tiếp `new` các sender | Tiêm factory/test double để ghi nhận nội dung |
| Giữ formatter và sender thuộc cùng kênh | Mỗi chỗ khởi tạo phải tự giữ quy tắc ghép cặp | Concrete factory quản lý quy tắc ghép cặp, vẫn cần test |
| Thêm loại sản phẩm thứ ba, ví dụ `DeliveryReceipt` | Có thể phải điều chỉnh các nhánh tự tạo | Phải bổ sung phương thức vào Abstract Factory và cập nhật **mọi** concrete factory |

Hàng cuối là một **đánh đổi quan trọng**: Abstract Factory thuận tiện cho **thêm biến thể mới của một bộ loại sản phẩm đã ổn định**, nhưng không nhất thiết thuận tiện khi **thêm một loại sản phẩm hoàn toàn mới** vào bộ đó.

## 8. Ranh giới chọn biến thể cần đặt ở đâu?

“Tách logic nghiệp vụ khỏi quyết định chọn biến thể” không có nghĩa mọi ứng dụng phải chọn factory **một lần khi khởi động**.

**Trường hợp 1: biến thể cố định cho toàn ứng dụng.** Ví dụ chương trình desktop chạy trên Windows hoặc macOS. Thành phần khởi tạo ứng dụng có thể chọn `WindowsGUIFactory` hoặc `MacGUIFactory` một lần và đưa factory đó vào các màn hình.

**Trường hợp 2: biến thể cố định cho một phiên hoặc tenant.** Ví dụ một tổ chức sử dụng nhà cung cấp thanh toán đã cấu hình. Tại điểm tạo request scope/tenant scope, ứng dụng chọn một factory phù hợp cho phiên hoặc tenant đó.

**Trường hợp 3: biến thể thay đổi theo từng yêu cầu.** Ví dụ người dùng chọn Email cho một thông báo và SMS cho thông báo khác. Lớp điều phối ở **biên của ca sử dụng** đọc tùy chọn, chọn concrete factory rồi tạo hoặc gọi service được cung cấp factory phù hợp. Tránh giữ một factory toàn cục nếu điều đó khiến request của người dùng này ảnh hưởng request của người dùng khác.

Ví dụ sơ đồ cho trường hợp chọn theo yêu cầu:

~~~mermaid
sequenceDiagram
    participant R as Request handler
    participant S as Factory selector
    participant N as OrderNotificationService
    participant F as MessageFormatter
    participant M as MessageSender
    R->>S: select(channel)
    S-->>R: NotificationFactory
    R->>N: new Service(factory)
    R->>N: notifyShipped(order, recipient)
    N->>F: format(businessContent)
    F-->>N: formattedContent
    N->>M: send(recipient, formattedContent)
~~~

Điểm chọn nằm ngoài mã nghiệp vụ, nhưng **nguồn quyết định** có thể vẫn là dữ liệu nghiệp vụ (ví dụ khách đã đăng ký nhận SMS). Nếu quy tắc chọn kênh dựa trên mức độ ưu tiên, chi phí hay quyền riêng tư, chính **quy tắc chọn đó có thể là một chính sách nghiệp vụ**; cần có abstraction hoặc policy phù hợp, thay vì tự động chuyển toàn bộ quy tắc sang tầng hạ tầng.

## 9. Không nhầm “tách trách nhiệm” với “thêm factory cho mọi đối tượng”

Không phải hệ thống nào có nhiều `new` hoặc nhiều `if` cũng cần Abstract Factory.

| Tình huống | Hướng cân nhắc |
| --- | --- |
| Có **nhiều loại sản phẩm** phải được chọn đồng bộ theo cùng một biến thể | Abstract Factory thường phù hợp |
| Chỉ thay đổi **một loại đối tượng**, ví dụ một cách tính phí | Factory đơn giản, Dependency Injection hoặc Strategy có thể đủ |
| Điều kiện phân nhánh chính là **quy tắc nghiệp vụ** | Giữ trong lớp nghiệp vụ/policy phù hợp; không đẩy nhầm sang factory |
| Cơ chế DI đã lắp ráp đúng bộ sản phẩm tại composition root | Có thể dùng trực tiếp DI, chỉ thêm Abstract Factory khi nó làm rõ trách nhiệm hoặc hỗ trợ nhu cầu runtime |
| Hệ thống chỉ có một biến thể và không có ràng buộc giữa các sản phẩm | Có thể chưa cần thêm nhiều interface/concrete factory |

Một **Factory Method** thường tập trung vào cách chọn một đối tượng để tạo (thường thông qua cơ chế ghi đè của lớp con); **Abstract Factory** diễn đạt một hợp đồng tạo **cả nhóm loại sản phẩm liên quan**. Cần lựa chọn mẫu theo **cấu trúc biến thể và yêu cầu của hệ thống**, không theo sự xuất hiện của từ khóa `new`.

Tạo quá nhiều abstraction có chi phí: nhiều lớp hơn, nhiều nơi để tra cứu và thêm công việc khi mở rộng một loại sản phẩm mới. Mục tiêu là **giảm chi phí thay đổi tổng thể**, không phải tối đa số lượng interface.

## 10. Giới hạn và điều cần bảo toàn khi refactor

Tách cấu trúc phụ thuộc là một thay đổi kiến trúc; khi thực hiện trên mã đang chạy, cần lưu ý:

1. **Tính tương thích của sản phẩm:** kiểm tra tất cả concrete factory tạo đúng bộ sản phẩm. Java chỉ kiểm tra kiểu interface, không tự bảo đảm cùng họ.
2. **Hợp đồng về `null` và ngoại lệ:** khai báo `MessageSender createSender()` không ngăn implementation trả `null`. Ghi rõ và kiểm thử chính sách xử lý.
3. **Vòng đời đối tượng:** factory có thể tạo mới hoặc dùng lại sản phẩm. Nếu sender có trạng thái mutable hoặc không thread-safe, việc chia sẻ instance giữa các request có thể gây lỗi.
4. **Thời điểm tạo đối tượng:** chuyển constructor từ mỗi lần gửi sang lúc tạo service có thể thay đổi thời điểm mở kết nối, cấp tài nguyên và ném lỗi. Chỉ cache sản phẩm nếu vòng đời phù hợp.
5. **Cấu hình thay đổi trong runtime:** chọn factory lúc khởi động không đáp ứng việc người dùng đổi kênh theo từng thông báo; phải đưa quyết định chọn đến đúng scope.
6. **Độ ổn định của interface:** nếu mọi biến thể cần thêm loại sản phẩm mới, tất cả concrete factory phải cập nhật. Đừng vội đưa vào factory các phương thức không thuộc cùng một họ trách nhiệm.
7. **Đặc thù thực tế:** định dạng Email và SMS có thể có nhu cầu khác nhau (title, encoding, segment SMS, retry). Cần giữ hợp đồng chung có ý nghĩa mà không che mất những khác biệt quan trọng. Nếu hai loại sản phẩm không thật sự hình thành một bộ tương thích, không nên ép chúng vào một Abstract Factory.

Một phản ví dụ đơn giản:

~~~java
if (order.total() >= 1_000_000) {
    discount = 0.10;
} else {
    discount = 0.05;
}
~~~

Đây là **quy tắc nghiệp vụ về chiết khấu**. Nó không tạo họ sản phẩm nào và không tự trở thành ứng viên cho Abstract Factory chỉ vì có `if/else`. Nếu quy tắc ngày càng phức tạp, cân nhắc tách thành một `DiscountPolicy` hoặc Strategy phù hợp với mục đích thực tế.

## 11. Bài tập phân tích

### Tình huống A: giao diện đa nền tảng

Một màn hình có:

~~~java
if (os == OS.WINDOWS) {
    button = new WindowsButton();
    checkbox = new WindowsCheckbox();
} else {
    button = new MacButton();
    checkbox = new MacCheckbox();
}
~~~

**Hãy xác định:** quy tắc nghiệp vụ của màn hình là gì; phần chọn biến thể nằm ở đâu; hai loại sản phẩm có nên chung một factory không; nếu thêm Linux, những phần nào cần sửa sau khi tách trách nhiệm?

*Gợi ý:* màn hình cần hành vi của `Button` và `Checkbox`; một `GUIFactory` với `createButton()` và `createCheckbox()` có thể tạo bộ sản phẩm cùng nền tảng, còn màn hình chỉ dùng interface.

### Tình huống B: thanh toán với hai nhà cung cấp

Một hệ thống cần tạo `PaymentClient` và `RefundClient` tương thích theo nhà cung cấp A hoặc B. `CheckoutService` đang chứa `switch(provider)` để tự tạo cả hai client.

**Hãy trả lời:** khi chuyển sang `PaymentFactory`, quy tắc nào còn thuộc `CheckoutService` (ví dụ xác định khi nào hoàn tiền), và quy tắc nào thuộc `PaymentFactory` (ví dụ ghép client thanh toán và hoàn tiền của cùng nhà cung cấp)? Việc chọn provider nên đặt ở đâu nếu mỗi merchant dùng một provider riêng?

### Tình huống C: một loại sản phẩm

Một hệ thống chỉ cần tạo `PdfExporter` **hoặc** `CsvExporter`, không có loại sản phẩm liên quan nào khác.

**Hãy đánh giá:** một Abstract Factory nhiều phương thức có mang lại lợi ích không, hay có thể chỉ cần interface `Exporter` cùng một factory đơn giản hoặc DI?

### Tình huống D: phản biện lợi ích

Có ý kiến: “Sau khi áp dụng Abstract Factory, thêm biến thể mới sẽ không phải sửa bất kỳ dòng mã cũ nào.”

**Hãy phản biện:** ngoài những concrete factory/sản phẩm mới, vẫn có thể phải cập nhật nơi chọn factory, enum/cấu hình, bộ test, mapping dependency và tài liệu. Lợi ích chính là **giữ ổn định những lớp nghiệp vụ không liên quan đến lựa chọn implementation**.

## 12. Checklist trước khi chọn cách tách

- [ ] Đã phân biệt quy tắc nghiệp vụ với quyết định tạo implementation.
- [ ] Có **ít nhất hai loại sản phẩm liên quan** cần được chọn nhất quán theo cùng một biến thể.
- [ ] Mã nghiệp vụ hiện phụ thuộc vào lớp cụ thể hoặc lặp điều kiện chọn biến thể ở nhiều vị trí.
- [ ] Có thể viết interface sản phẩm ổn định mà lớp nghiệp vụ sử dụng.
- [ ] Có ranh giới phù hợp để chọn concrete factory theo application/request/tenant scope.
- [ ] Các concrete factory có trách nhiệm tạo đúng họ sản phẩm và có kiểm thử bảo vệ quy tắc ấy.
- [ ] Đã cân nhắc ảnh hưởng của thời điểm khởi tạo, vòng đời, tài nguyên và thread safety.
- [ ] Đã nhận diện các quy tắc chọn kênh thực sự thuộc nghiệp vụ để không chuyển sai trách nhiệm.
- [ ] Đã so sánh chi phí thêm abstraction với giải pháp đơn giản hơn như DI, factory thông thường hoặc Strategy.

**Ghi nhớ:** Tách logic nghiệp vụ khỏi quyết định chọn biến thể giúp **giảm coupling, tập trung nơi lắp ráp các sản phẩm cùng họ, làm rõ điểm thay đổi và tăng khả năng kiểm thử độc lập**. Abstract Factory phát huy hiệu quả nhất khi ứng dụng phải chuyển đổi giữa **những họ gồm nhiều loại sản phẩm liên quan**, trong khi nghiệp vụ sử dụng các sản phẩm ấy có thể tiếp tục làm việc qua cùng một bộ interface.
