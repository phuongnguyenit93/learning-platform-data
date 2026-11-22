# Decorator: bổ sung hành vi qua cùng interface

Decorator là mẫu thiết kế cấu trúc dùng để bổ sung trách nhiệm cho một đối tượng bằng cách bọc đối tượng đó trong một đối tượng khác có cùng interface. Client tiếp tục gọi cùng các phương thức như trước, trong khi decorator có thể thêm hành vi trước hoặc sau khi chuyển tiếp lời gọi đến đối tượng được bọc.

Mẫu này hữu ích khi cần kết hợp các tính năng tùy chọn tại thời điểm chạy, chẳng hạn gửi thông báo qua nhiều kênh, thêm logging, đo thời gian, mã hóa dữ liệu hoặc lưu cache. Trong Java, Decorator thường được triển khai bằng composition: decorator giữ một tham chiếu đến đối tượng cần bọc và triển khai cùng interface với nó.

## 1. Vấn đề mà Decorator giải quyết

Giả sử ứng dụng có interface `Notifier` và một triển khai gửi email. Sau đó yêu cầu bổ sung gửi SMS, thêm tiền tố quan trọng, ghi log và đo thời gian xử lý. Có thể tạo một lớp con cho từng tổ hợp, nhưng số lớp sẽ tăng nhanh:

- Email thông thường
- Email kèm SMS
- Email có tiền tố
- Email kèm SMS và tiền tố
- Các tổ hợp mới khi thêm logging hoặc retry

Đây là sự bùng nổ số lượng lớp do kế thừa để biểu diễn mọi tổ hợp hành vi. Decorator cho phép kết hợp những phần bổ sung độc lập bằng cách bọc đối tượng nhiều lần. Mỗi decorator chịu trách nhiệm cho một phần hành vi và các decorator có thể được lắp ghép khi khởi tạo ứng dụng.

## 2. Cấu trúc và vai trò

Một thiết kế Decorator phổ biến gồm bốn vai trò:

1. **Component**: interface chung mà client sử dụng.
2. **Concrete Component**: đối tượng cơ sở cung cấp hành vi ban đầu.
3. **Base Decorator**: cũng triển khai Component, giữ tham chiếu đến một Component khác và chuyển tiếp lời gọi.
4. **Concrete Decorator**: kế thừa base decorator, thêm hành vi rồi chuyển tiếp hoặc bổ sung xử lý trước/sau lời gọi.

Sơ đồ quan hệ:

~~~mermaid
classDiagram
    class Notifier {
        <<interface>>
        +send(message)
    }
    class EmailNotifier {
        +send(message)
    }
    class NotifierDecorator {
        #delegate
        +send(message)
    }
    class PrefixDecorator {
        +send(message)
    }
    class SmsDecorator {
        +send(message)
    }
    Notifier <|.. EmailNotifier
    Notifier <|.. NotifierDecorator
    NotifierDecorator <|-- PrefixDecorator
    NotifierDecorator <|-- SmsDecorator
    NotifierDecorator o--> Notifier : delegates to
~~~

Mấu chốt là cả đối tượng gốc và decorator đều có thể được gán cho biến kiểu Component. Vì vậy, client không cần biết đang gọi trực tiếp đối tượng gốc hay một chuỗi decorator.

## 3. Ví dụ Java chạy được

Ví dụ sau dùng email làm hành vi cơ sở. `PrefixDecorator` bổ sung tiền tố vào thông điệp, còn `SmsDecorator` gửi thêm một bản thông báo SMS. Hai decorator đều triển khai cùng interface `Notifier`.

Lưu thành tệp `DecoratorDemo.java`:

~~~java
import java.util.Objects;

interface Notifier {
    void send(String message);
}

final class EmailNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println("Email: " + message);
    }
}

abstract class NotifierDecorator implements Notifier {
    protected final Notifier delegate;

    protected NotifierDecorator(Notifier delegate) {
        this.delegate = Objects.requireNonNull(delegate, "delegate");
    }
}

final class PrefixDecorator extends NotifierDecorator {
    PrefixDecorator(Notifier delegate) {
        super(delegate);
    }

    @Override
    public void send(String message) {
        delegate.send("[IMPORTANT] " + message);
    }
}

final class SmsDecorator extends NotifierDecorator {
    SmsDecorator(Notifier delegate) {
        super(delegate);
    }

    @Override
    public void send(String message) {
        delegate.send(message);
        System.out.println("SMS: " + message);
    }
}

public class DecoratorDemo {
    public static void main(String[] args) {
        Notifier notifier =
                new PrefixDecorator(new SmsDecorator(new EmailNotifier()));

        notifier.send("Deployment complete");
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~text
javac DecoratorDemo.java
java DecoratorDemo
~~~

Kết quả stdout:

~~~text
Email: [IMPORTANT] Deployment complete
SMS: [IMPORTANT] Deployment complete
~~~

Luồng gọi diễn ra như sau:

1. Client gọi `notifier.send("Deployment complete")`.
2. `PrefixDecorator` thêm tiền tố `[IMPORTANT] ` và chuyển tiếp thông điệp mới đến `SmsDecorator`.
3. `SmsDecorator` chuyển tiếp thông điệp đã được bổ sung đến `EmailNotifier`, nên email được gửi trước.
4. Sau khi lời gọi bên trong hoàn tất, `SmsDecorator` gửi thêm SMS với chính thông điệp mà nó nhận được.

Trong ví dụ, thứ tự bọc là `PrefixDecorator(SmsDecorator(EmailNotifier))`. Đổi thứ tự bọc có thể làm thay đổi hành vi vì decorator ngoài cùng nhận lời gọi trước. Hãy xác định rõ mỗi lớp cần sửa dữ liệu, thực hiện hành động bổ sung hay xử lý sau khi delegate hoàn thành.

## 4. Cách triển khai decorator đúng

Một decorator nên giữ hợp đồng của Component và chuyển tiếp các phương thức mà nó không cần thay đổi. Với interface có nhiều phương thức, base decorator thường triển khai tất cả phương thức bằng cách gọi delegate tương ứng; lớp con chỉ ghi đè phương thức cần mở rộng.

Một số nguyên tắc thực hành:

- **Cùng interface:** cả component gốc và decorator phải có thể sử dụng thông qua cùng kiểu Component.
- **Ủy quyền rõ ràng:** decorator giữ một đối tượng delegate và gọi nó ở thời điểm phù hợp.
- **Một trách nhiệm bổ sung:** mỗi decorator nên làm một việc có tên gọi và mục đích rõ ràng, ví dụ thêm logging hoặc mã hóa.
- **Cho phép kết hợp:** caller có thể bọc một component bằng nhiều decorator theo cấu hình lúc chạy.
- **Giữ hợp đồng:** nếu phương thức được kỳ vọng trả về một giá trị, ném loại exception cụ thể hoặc bảo đảm một hậu điều kiện, decorator phải duy trì các cam kết đó.
- **Kiểm soát null và vòng lặp:** constructor nên xác thực delegate nếu null không phải giá trị hợp lệ; tránh cấu hình một decorator tự tham chiếu lại chính nó.
- **Bảo toàn thứ tự và lỗi:** quyết định rõ decorator thực hiện hành vi trước hay sau delegate, và điều gì xảy ra nếu delegate ném exception.

Base decorator là tùy chọn. Với interface nhỏ hoặc chỉ có một phương thức, từng decorator có thể triển khai interface trực tiếp. Với interface lớn, base decorator giúp giảm mã lặp khi chuyển tiếp các phương thức.

## 5. Kết hợp decorator và cấu hình lúc chạy

Có thể xây dựng chuỗi decorator có điều kiện mà không đổi kiểu biến mà client sử dụng:

~~~java
Notifier notifier = new EmailNotifier();

if (sendSms) {
    notifier = new SmsDecorator(notifier);
}
if (markImportant) {
    notifier = new PrefixDecorator(notifier);
}

notifier.send("Deployment complete");
~~~

Đoạn này là ví dụ minh họa một phần; các biến `sendSms` và `markImportant` cần được khai báo trong ngữ cảnh chứa nó. Cả trước và sau khi bọc, kiểu tham chiếu vẫn là `Notifier`. Client chỉ gọi `send`, còn cấu hình quyết định hành vi nào được thêm vào.

Khi số lượng decorator lớn hơn, nên tập trung việc xây dựng chuỗi vào một factory hoặc hàm cấu hình để quy tắc khởi tạo dễ kiểm thử. Tránh để nhiều nơi trong ứng dụng tự xây dựng chuỗi khác nhau nếu thứ tự decorator có ý nghĩa với nghiệp vụ.

## 6. Decorator khác kế thừa thông thường như thế nào?

Kế thừa mở rộng hành vi bằng cách tạo lớp con có quan hệ kiểu cố định với lớp cha. Decorator mở rộng hành vi bằng cách giữ một đối tượng khác và chuyển tiếp lời gọi. Một decorator có thể bọc nhiều loại Concrete Component miễn là chúng cùng triển khai Component.

| Tiêu chí | Kế thừa | Decorator |
|---|---|---|
| Cách bổ sung hành vi | Định nghĩa lớp con | Bọc đối tượng và ủy quyền |
| Kết hợp tính năng | Thường cần lớp con cho các tổ hợp | Có thể xếp nhiều decorator |
| Quyết định lúc nào | Thường gắn với kiểu lớp đã biên dịch | Có thể quyết định lúc chạy |
| Phụ thuộc chính | Quan hệ với lớp cha | Interface và delegate |
| Giới hạn | Có thể tạo nhiều lớp con, khó kết hợp độc lập | Chuỗi bọc có thể phức tạp nếu không quản lý rõ |

Decorator không loại bỏ hoàn toàn kế thừa. Trong ví dụ, các decorator cụ thể kế thừa `NotifierDecorator` để dùng lại cơ chế lưu delegate và chuyển tiếp. Phần quan trọng là hành vi mở rộng được áp dụng lên một đối tượng delegate qua composition, thay vì chỉ dựa vào việc kế thừa từ lớp triển khai cơ sở.

## 7. So sánh với các mẫu thiết kế gần giống

- **Adapter:** chuyển đổi một interface thành interface khác để hai thành phần không tương thích có thể làm việc cùng nhau. Decorator giữ interface gốc để bổ sung trách nhiệm.
- **Proxy:** cũng giữ tham chiếu đến đối tượng và chuyển tiếp lời gọi, nhưng mục tiêu chính thường là kiểm soát truy cập, tạo đối tượng theo nhu cầu, phân phối từ xa hoặc quản lý vòng đời.
- **Chain of Responsibility:** chuyển một yêu cầu qua chuỗi handler để mỗi handler quyết định xử lý hay chuyển tiếp. Decorator thường bọc component để mở rộng hành vi của nó, và các lớp bọc có thể thực hiện cả hành vi trước lẫn sau delegate.
- **Strategy:** thay đổi thuật toán được sử dụng thông qua một interface. Decorator tập trung vào việc kết hợp hành vi xung quanh một component; hai mẫu có thể được dùng cùng nhau.

Tên gọi không quyết định mẫu thiết kế; hãy xem mục tiêu và luồng điều khiển thực tế của mã. Một wrapper có thể trông giống Decorator nhưng về mục đích lại là Proxy hoặc Adapter.

## 8. Ví dụ trong thư viện Java

Thư viện chuẩn Java dùng cách bọc đối tượng ở nhiều API. Ví dụ, `BufferedInputStream` bọc một `InputStream` để thêm buffering, còn `DataInputStream` bổ sung khả năng đọc dữ liệu nguyên thủy. Chúng vẫn được sử dụng thông qua các kiểu stream tương ứng, nên có thể kết hợp nhiều lớp bọc:

~~~java
InputStream input = new BufferedInputStream(
        new FileInputStream("data.bin"));
~~~

Ví dụ trên chỉ minh họa cấu trúc bọc; mã thực tế cần import các lớp và xử lý hoặc khai báo `IOException`. Khi kết hợp stream, hãy tuân thủ quy tắc đóng tài nguyên, thường bằng try-with-resources. Đóng stream ngoài cùng thường sẽ đóng các stream bên trong thông qua cơ chế delegate.

## 9. Lỗi thường gặp

- **Không gọi delegate:** decorator vô tình thay thế toàn bộ hành vi gốc, dù mục tiêu chỉ là bổ sung một phần. Hãy quyết định rõ có chủ ý chặn lời gọi hay cần chuyển tiếp.
- **Thêm hành vi sai thời điểm:** hành vi chạy trước hay sau delegate ảnh hưởng đến kết quả, đặc biệt nếu delegate có thể ném exception.
- **Đảo thứ tự decorator:** tiền xử lý, mã hóa, logging hoặc chuyển đổi dữ liệu có thể không giao hoán. Kiểm thử đúng thứ tự bọc được cấu hình trong ứng dụng.
- **Làm thay đổi hợp đồng:** decorator trả kết quả không hợp lệ, nuốt exception hoặc làm thay đổi trạng thái theo cách caller không mong đợi.
- **Tạo chuỗi quá sâu:** nhiều lớp bọc làm stack trace và quá trình debug khó đọc. Đặt tên rõ ràng cho từng decorator và gom việc cấu hình chuỗi ở một nơi.
- **Nhầm Decorator với Adapter:** nếu phải chuyển đổi sang một interface khác, có thể Adapter mới là lựa chọn đúng.
- **Giữ trạng thái dùng chung không an toàn:** nếu nhiều luồng dùng cùng một decorator, các trường trạng thái có thể cần bất biến, đồng bộ hoặc thiết kế an toàn luồng.

## 10. Cách kiểm thử và quyết định sử dụng

Kiểm thử decorator riêng bằng cách cung cấp một component giả (fake) hoặc mock để xác minh rằng delegate được gọi với đúng đối số và số lần mong muốn. Với decorator thêm hành vi sau delegate, kiểm tra cả thứ tự và trường hợp delegate ném exception. Sau đó kiểm thử chuỗi hoàn chỉnh để xác minh thứ tự bọc tạo ra kết quả đúng.

Decorator phù hợp khi cần thêm các tính năng tùy chọn, độc lập, có thể kết hợp mà vẫn giữ interface cho client. Nếu hành vi mới làm thay đổi hoàn toàn mục đích của API, cần chuyển đổi interface hoặc điều phối một quy trình nhiều bước, hãy cân nhắc Adapter, Strategy hoặc Chain of Responsibility.

Một câu hỏi hữu ích khi thiết kế là: “Tôi có thể bọc component này bằng một đối tượng khác cùng interface, bổ sung một trách nhiệm rõ ràng và vẫn giữ đúng hợp đồng của component không?” Nếu có, Decorator là ứng viên tốt.