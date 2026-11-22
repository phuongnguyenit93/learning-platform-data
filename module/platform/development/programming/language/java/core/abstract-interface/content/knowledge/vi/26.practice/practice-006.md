# Thay cây kế thừa khó mở rộng bằng composition

Khi một hệ thống có nhiều cách gửi thông báo, nhiều định dạng nội dung và nhiều chính sách xử lý, dùng một subclass cho mọi tổ hợp sẽ nhanh chóng tạo ra một cây kế thừa khó duy trì. **Composition** giải quyết vấn đề bằng cách để một đối tượng giữ và phối hợp các thành phần có trách nhiệm riêng, thay vì mã hóa mọi biến thể vào quan hệ `extends`.

Bài thực hành này đi từ thiết kế dễ phình to sang thiết kế kết hợp các hành vi độc lập, sau đó kiểm tra bằng một chương trình Java 17+ chạy được.

## 1. Nhận diện cây kế thừa đang khó mở rộng

Giả sử ứng dụng gửi thông báo và có các chiều thay đổi sau:

- Kênh gửi: email, SMS, push notification.
- Cách trình bày: văn bản thường, có tiền tố ưu tiên, hoặc mẫu theo ngôn ngữ.
- Chính sách gửi: gửi một lần, thử lại khi thất bại, hoặc ghi log chi tiết.

Nếu mỗi subclass đại diện cho một tổ hợp, ta có thể phải tạo `EmailNotifier`, `UrgentEmailNotifier`, `SmsNotifier`, `UrgentSmsNotifier`, `RetryingEmailNotifier`, `UrgentRetryingSmsNotifier` và tiếp tục thêm lớp khi có biến thể mới. Với nhiều chiều độc lập, số tổ hợp có thể tăng theo tích số lựa chọn của từng chiều. Ví dụ 3 kênh × 3 cách trình bày × 2 chính sách đã tạo ra 18 tổ hợp tiềm năng.

Vấn đề không phải là “có nhiều subclass thì luôn sai”. Kế thừa vẫn hữu ích khi lớp con thực sự là một dạng chuyên biệt của lớp cha và có thể tuân thủ hợp đồng của lớp cha. Vấn đề xuất hiện khi ta dùng kế thừa chỉ để ghép các tính năng độc lập với nhau.

Các dấu hiệu thường gặp:

- Thêm một kênh mới buộc phải tạo nhiều subclass cho từng mức ưu tiên hoặc chính sách.
- Cùng một đoạn code gửi hoặc định dạng bị sao chép trong nhiều subclass.
- Muốn đổi hành vi lúc chạy thì phải chọn một class khác hoặc xây lại cả cây đối tượng.
- Một subclass kế thừa hành vi không cần dùng, hoặc override nhiều phương thức để vô hiệu hóa hành vi từ lớp cha.
- Thay đổi ở superclass gây ảnh hưởng ngoài dự kiến đến các lớp con.

## 2. Vì sao composition phù hợp?

Composition có nghĩa là một đối tượng sử dụng các đối tượng khác để thực hiện công việc. Đối tượng cấp cao chịu trách nhiệm điều phối; mỗi thành phần chịu trách nhiệm về một hành vi cụ thể.

Với ví dụ thông báo, ta có thể tách thành:

- `MessageSender`: gửi thông điệp qua một kênh.
- `MessageFormatter`: chuyển nội dung đầu vào thành nội dung sẽ gửi.
- `NotificationService`: phối hợp formatter và sender theo đúng thứ tự.

Nhờ đó, kênh gửi và cách trình bày trở thành hai chiều độc lập. Ta có thể kết hợp `EmailSender` với `PlainFormatter`, hoặc `SmsSender` với `PriorityFormatter` mà không cần viết một subclass cho từng cặp.

Composition thường đi cùng dependency injection: các thành phần được truyền vào qua constructor. Cách này giúp thay thế implementation dễ dàng, kiểm thử bằng fake/mock thuận tiện và thể hiện rõ những dependency mà một class cần.

## 3. Thiết kế Java bằng các interface nhỏ

Định nghĩa hợp đồng theo vai trò thay vì theo từng tổ hợp:

```java
interface MessageSender {
    void send(String message);
}

interface MessageFormatter {
    String format(String message);
}
```

`MessageSender` chỉ quan tâm đến việc gửi chuỗi. `MessageFormatter` chỉ quan tâm đến cách biến đổi chuỗi. Chúng không cần biết nhau và không phụ thuộc vào `NotificationService`.

Đối tượng điều phối giữ các dependency và ủy quyền công việc:

```java
final class NotificationService {
    private final MessageSender sender;
    private final MessageFormatter formatter;

    NotificationService(MessageSender sender, MessageFormatter formatter) {
        this.sender = java.util.Objects.requireNonNull(sender);
        this.formatter = java.util.Objects.requireNonNull(formatter);
    }

    void notify(String message) {
        String formatted = formatter.format(message);
        sender.send(formatted);
    }
}
```

Constructor bảo đảm các dependency không phải `null`, và các field `final` giúp những dependency này không bị thay thế vô tình sau khi tạo service. Phương thức `notify` không cần biết gửi qua email hay SMS, cũng không cần biết nội dung được định dạng theo cách nào.

## 4. Chương trình hoàn chỉnh có thể chạy

Lưu đoạn mã dưới đây thành `CompositionDemo.java`. Các sender trong ví dụ chỉ in ra console để minh họa kiến trúc; chúng không gửi email hay SMS thật.

```java
public class CompositionDemo {
    interface MessageSender {
        void send(String message);
    }

    interface MessageFormatter {
        String format(String message);
    }

    static final class EmailSender implements MessageSender {
        @Override
        public void send(String message) {
            System.out.println("EMAIL: " + message);
        }
    }

    static final class SmsSender implements MessageSender {
        @Override
        public void send(String message) {
            System.out.println("SMS: " + message);
        }
    }

    static final class PlainFormatter implements MessageFormatter {
        @Override
        public String format(String message) {
            return message;
        }
    }

    static final class PriorityFormatter implements MessageFormatter {
        @Override
        public String format(String message) {
            return "[PRIORITY] " + message;
        }
    }

    static final class NotificationService {
        private final MessageSender sender;
        private final MessageFormatter formatter;

        NotificationService(MessageSender sender, MessageFormatter formatter) {
            this.sender = java.util.Objects.requireNonNull(sender);
            this.formatter = java.util.Objects.requireNonNull(formatter);
        }

        void notify(String message) {
            sender.send(formatter.format(message));
        }
    }

    public static void main(String[] args) {
        NotificationService normalEmail = new NotificationService(
                new EmailSender(), new PlainFormatter());
        normalEmail.notify("Build completed");

        NotificationService prioritySms = new NotificationService(
                new SmsSender(), new PriorityFormatter());
        prioritySms.notify("Server is down");

        NotificationService priorityEmail = new NotificationService(
                new EmailSender(), new PriorityFormatter());
        priorityEmail.notify("Deployment started");
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac CompositionDemo.java
java CompositionDemo
```

Stdout chính xác:

```text
EMAIL: Build completed
SMS: [PRIORITY] Server is down
EMAIL: [PRIORITY] Deployment started
```

Ba cấu hình sử dụng hai loại sender và hai loại formatter mà không cần các class như `PriorityEmailNotifier` hay `PrioritySmsNotifier`. `NotificationService` chỉ phối hợp các hành vi, còn mỗi implementation nhỏ tập trung vào một trách nhiệm.

## 5. Thêm biến thể mà không sửa service

Giả sử cần gửi thông báo qua push notification. Ta thêm một implementation mới:

```java
static final class PushSender implements MessageSender {
    @Override
    public void send(String message) {
        System.out.println("PUSH: " + message);
    }
}
```

Sau đó tạo service với `new PushSender()` và formatter mong muốn. Không cần thêm nhánh `if/else` vào `NotificationService`, và cũng không cần tạo subclass mới cho mọi kiểu trình bày.

Tương tự, muốn thêm định dạng có mã sự kiện, ta tạo một implementation `MessageFormatter` mới. Chỉ những cấu hình cần hành vi mới sẽ dùng formatter đó. Các thành phần hiện có tiếp tục hoạt động độc lập.

Trong ứng dụng thực tế, có thể cấu hình các dependency bằng constructor trực tiếp, factory hoặc dependency injection framework. Framework không phải điều kiện để áp dụng composition; việc truyền dependency qua constructor đã thể hiện nguyên tắc này.

## 6. So sánh kế thừa và composition

| Tiêu chí | Cây kế thừa cho từng tổ hợp | Composition |
| --- | --- | --- |
| Thêm kênh mới | Có thể phải tạo nhiều subclass mới. | Thêm một `MessageSender` implementation. |
| Thêm cách định dạng | Có thể nhân số subclass theo các biến thể hiện có. | Thêm một `MessageFormatter` implementation. |
| Kết hợp hành vi | Các tổ hợp thường được mã hóa trong tên và cấu trúc class. | Chọn dependency khi tạo đối tượng. |
| Kiểm thử | Có thể cần khởi tạo một cây class phức tạp. | Có thể truyền fake sender và formatter đơn giản. |
| Quan hệ mô hình | Phù hợp khi lớp con thật sự là một dạng của lớp cha. | Phù hợp khi đối tượng phối hợp các vai trò độc lập. |
| Chi phí | Cây class có thể phình to và tạo phụ thuộc chặt. | Có thêm interface/đối tượng và bước cấu hình. |

Composition không tự động tốt hơn trong mọi trường hợp. Nếu chỉ có một hành vi ổn định, không có nhiều biến thể và quan hệ “là một” thực sự rõ ràng, một class đơn giản hoặc kế thừa có thể dễ hiểu hơn. Tránh tạo interface và lớp bọc chỉ để chuyển tiếp một lời gọi mà không mang lại lợi ích thiết kế.

## 7. Lỗi thường gặp khi chuyển sang composition

### Tách thành quá nhiều abstraction

Không nên tạo interface cho mọi class theo thói quen. Hãy tách một trách nhiệm khi có lý do thực tế: hành vi thay đổi độc lập, có nhiều implementation, cần thay thế trong kiểm thử hoặc ranh giới đó làm thiết kế dễ hiểu hơn.

### Đưa điều phối vào sai nơi

`NotificationService` nên điều phối trình tự format rồi send. `EmailSender` không nên tự quyết định định dạng ưu tiên nếu định dạng đó là một chiều thay đổi riêng. Nếu mỗi sender chứa cùng một logic định dạng, ta lại tạo ra trùng lặp.

### Dùng kế thừa trong các thành phần nhỏ không cần thiết

Các implementation có thể là class cụ thể độc lập. Chỉ dùng `extends` khi thực sự cần tái sử dụng hoặc chuyên biệt hóa một loại có quan hệ phù hợp; không cần tạo một superclass chung chỉ vì vài class tình cờ có một dòng code giống nhau.

### Tạo dependency có thể thay đổi không kiểm soát

Nếu dependency không cần thay đổi sau khi tạo service, hãy dùng field `final` và truyền qua constructor. Nếu cần đổi hành vi trong vòng đời đối tượng, hãy thiết kế điểm thay đổi rõ ràng thay vì cho phép mọi field bị thay thế tùy ý.

### Quên các quy tắc nghiệp vụ khi ghép thành phần

Composition chỉ giúp ghép hành vi; nó không tự giải quyết thứ tự gửi, retry, timeout, xử lý lỗi hoặc tính nhất quán. Nếu thêm retry, hãy xác định thao tác nào được thử lại, exception nào được xem là tạm thời và nguy cơ gửi trùng. Những quy tắc đó cần hợp đồng và kiểm thử riêng.

## 8. Cách thực hành refactor an toàn

Khi gặp một cây kế thừa khó mở rộng trong dự án, hãy tiến hành theo từng bước:

1. Liệt kê các chiều thay đổi độc lập, chẳng hạn kênh gửi, định dạng và chính sách retry.
2. Tìm phần code trùng lặp hoặc subclass chỉ khác nhau ở một hành vi nhỏ.
3. Chọn một trách nhiệm có ranh giới rõ và định nghĩa interface nhỏ nếu cần nhiều implementation hoặc cần thay thế dễ dàng.
4. Di chuyển hành vi đó sang một thành phần riêng; để đối tượng chính giữ vai trò điều phối.
5. Truyền thành phần qua constructor và giữ hợp đồng hiện có của đối tượng công khai.
6. Thêm kiểm thử để chứng minh hành vi trước và sau refactor tương đương với các tình huống đang được hỗ trợ.
7. Thêm một biến thể mới để kiểm tra thiết kế: nếu chỉ cần thêm implementation và cấu hình lại dependency, ranh giới thường đã hợp lý.

Không cần chuyển cả cây class trong một lần. Refactor một nhánh có giá trị, giữ kiểm thử chạy ổn định, rồi tiếp tục khi xuất hiện nhu cầu cụ thể.

## 9. Bài tập tự kiểm tra

1. Nếu có 4 kênh gửi và 3 định dạng, một thiết kế subclass theo từng tổ hợp có thể cần bao nhiêu class tổ hợp? Vì sao con số đó có thể tăng thêm khi có retry?
2. Trong ví dụ, vì sao `NotificationService` không cần biết lớp sender cụ thể?
3. Hãy thêm `UppercaseFormatter` chuyển thông điệp thành chữ hoa. Bạn có phải sửa `NotificationService` không?
4. Hãy viết một `MessageSender` giả chỉ ghi lại thông điệp nhận được, sau đó kiểm thử rằng formatter chạy trước sender.
5. Khi nào composition trở thành phức tạp không cần thiết? Hãy nêu một trường hợp mà một class đơn giản sẽ rõ ràng hơn.

## Kết luận

Khi một cây kế thừa mã hóa nhiều chiều thay đổi độc lập, hãy cân nhắc chuyển từng hành vi thành thành phần có trách nhiệm rõ ràng và để đối tượng chính phối hợp chúng bằng composition. Thiết kế này giúp kết hợp linh hoạt, thêm biến thể với ít thay đổi hơn và kiểm thử từng hành vi riêng. Hãy giữ abstraction ở mức cần thiết, bảo toàn hợp đồng hiện tại và refactor từng bước có kiểm thử.