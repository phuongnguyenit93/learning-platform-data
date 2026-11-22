# Hợp đồng, cách triển khai và mã sử dụng hợp đồng trong Java

Trong Java, thiết kế theo **hợp đồng** giúp một phần chương trình mô tả *điều có thể yêu cầu* mà không buộc bên sử dụng phải biết *công việc được thực hiện bằng cách nào*. Ba vai trò cần phân biệt là **hợp đồng (contract)**, **lớp triển khai (implementation)** và **mã sử dụng hợp đồng (consumer/client)**. Đây là nền tảng của đa hình, thay thế implementation, kiểm thử độc lập và giảm phụ thuộc giữa các thành phần.

Sau bài này, bạn cần giải thích được ba vai trò, đọc được luồng gọi phương thức, tự thiết kế một interface có ý nghĩa, hoán đổi implementation mà không sửa consumer, và nhận diện được các trường hợp “đúng chữ ký nhưng sai hành vi”.

## 1. Ba vai trò trong cùng một thiết kế

| Vai trò | Trách nhiệm chính | Biết điều gì? | Ví dụ |
| --- | --- | --- | --- |
| **Hợp đồng** | Công bố các thao tác được phép dùng và quy tắc hành vi mong đợi | Kiểu tham số, kiểu trả về, ngoại lệ, ý nghĩa của thao tác | Interface MessageSender |
| **Implementation** | Thực hiện các thao tác của hợp đồng bằng một cơ chế cụ thể | Cách gửi email, ghi log, gọi API hoặc lưu dữ liệu | EmailSender, ConsoleSender |
| **Consumer** | Gọi thao tác để giải quyết nghiệp vụ | Chỉ cần năng lực do hợp đồng cung cấp | AlertService |

Quan hệ thông thường:

~~~text
                 sử dụng qua kiểu MessageSender
AlertService ------------------------------------------> MessageSender
                                                              ^
                                                              |
                                                 implements   |   implements
                                                EmailSender   |   ConsoleSender
~~~

Mũi tên từ consumer đến interface biểu diễn **phụ thuộc ở mức mã nguồn**: consumer khai báo trường, tham số hoặc biến bằng kiểu hợp đồng. Ở thời điểm chạy, một đối tượng triển khai cụ thể được truyền vào consumer, và phương thức thực thi của đối tượng đó được gọi.

Ví dụ, AlertService cần khả năng “gửi thông báo”, không cần biết gửi qua SMTP, REST, bộ nhớ hay màn hình console. Nếu AlertService tự tạo EmailSender và gọi các phương thức riêng của EmailSender, hai thành phần bị gắn chặt vào nhau; việc thay phương thức gửi hoặc kiểm thử sẽ khó hơn.

**Phân biệt hai lớp nghĩa của từ “hợp đồng”:**

- **Hợp đồng cấu trúc**: những thành phần Java kiểm tra được tại thời điểm biên dịch, như tên phương thức, tham số, kiểu trả về, khả năng truy cập và quy tắc override.
- **Hợp đồng hành vi**: ý nghĩa của phương thức, điều kiện đầu vào, kết quả, lỗi có thể phát sinh và tác động phụ mà người viết và người dùng thống nhất. Trình biên dịch Java **không tự chứng minh** một implementation tuân thủ đầy đủ những quy tắc này.

Ví dụ, interface khai báo phương thức send(Message) không đảm bảo phương thức thật sự gửi, xử lý đúng lỗi hay tránh gửi trùng. Các điều đó cần mô tả và kiểm thử.

## 2. Ví dụ hoàn chỉnh: một hợp đồng, hai cách triển khai, một consumer

Tạo tệp **ContractDemo.java** với nội dung dưới đây. Mọi kiểu ở ví dụ cùng nằm trong một tệp; chỉ ContractDemo là lớp public. Hai sender chỉ **mô phỏng gửi thông báo qua console**, không kết nối mạng hoặc gửi email thật.

~~~java
import java.util.Objects;

// Dữ liệu truyền qua ranh giới hợp đồng.
record Message(String recipient, String body) {
    Message {
        Objects.requireNonNull(recipient, "recipient");
        Objects.requireNonNull(body, "body");
        if (recipient.isBlank() || body.isBlank()) {
            throw new IllegalArgumentException("recipient/body khong duoc trong");
        }
    }
}

// (1) HOP DONG: consumer chi can biet phuong thuc nay.
interface MessageSender {
    void send(Message message);
}

// (2a) IMPLEMENTATION thu nhat.
final class EmailSender implements MessageSender {
    @Override
    public void send(Message message) {
        System.out.println("EMAIL (mo phong) -> "
                + message.recipient() + ": " + message.body());
    }
}

// (2b) IMPLEMENTATION thu hai.
final class ConsoleSender implements MessageSender {
    @Override
    public void send(Message message) {
        System.out.println("CONSOLE -> "
                + message.recipient() + ": " + message.body());
    }
}

// (3) CONSUMER: chi phu thuoc MessageSender.
final class AlertService {
    private final MessageSender sender;

    AlertService(MessageSender sender) {
        this.sender = Objects.requireNonNull(sender, "sender");
    }

    void notifyUser(String recipient, String body) {
        sender.send(new Message(recipient, body));
    }
}

public class ContractDemo {
    public static void main(String[] args) {
        AlertService productionLike =
                new AlertService(new EmailSender());
        productionLike.notifyUser(
                "an@example.com", "Don hang da duoc duyet");

        AlertService consoleMode =
                new AlertService(new ConsoleSender());
        consoleMode.notifyUser("tester", "Da gui thong bao");
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 ContractDemo.java
java ContractDemo
~~~

Kết quả chuẩn:

~~~text
EMAIL (mo phong) -> an@example.com: Don hang da duoc duyet
CONSOLE -> tester: Da gui thong bao
~~~

Đọc ví dụ theo trình tự:

1. **MessageSender** nói rằng một sender nhận một Message và thực hiện send; nó không quyết định cách in hoặc gửi.
2. **EmailSender** và **ConsoleSender** cùng tuyên bố implements MessageSender và cung cấp send(Message). Từ khóa **@Override** giúp trình biên dịch phát hiện một số lỗi viết sai phương thức.
3. **AlertService** nhận MessageSender qua constructor, lưu ở trường cùng kiểu và chỉ gọi send. Cả hai implementation đều có thể được truyền vào mà không cần sửa mã AlertService.
4. Trong main, biểu thức new EmailSender() và new ConsoleSender() quyết định **đối tượng cụ thể** tại thời điểm tạo consumer. Đó là cách “kết nối” các thành phần (wiring/composition).
5. **Message** là record lưu dữ liệu và kiểm tra đầu vào rỗng. Quy tắc này giảm khả năng consumer vô tình gửi yêu cầu có nội dung trống; nó không bảo đảm một dịch vụ bên ngoài đã gửi thành công.

Điểm cần nhớ: consumer vẫn *cần một đối tượng thực hiện công việc*; “phụ thuộc vào interface” không có nghĩa là có thể chạy chương trình mà không cung cấp implementation.

## 3. Kiểu tham chiếu và dispatch động

Trong Java, kiểu khai báo của một biến quyết định **những phương thức có thể gọi ở lúc biên dịch**. Với phương thức instance được override, lớp thực tế của đối tượng quyết định **implementation được thực thi tại runtime**.

~~~java
MessageSender sender = new EmailSender();
sender.send(new Message("an@example.com", "Xin chao"));
~~~

Đoạn trên là minh họa đặt trong một phương thức của tệp ví dụ trước. Biến sender có kiểu tĩnh MessageSender, còn đối tượng thực là EmailSender. Trình biên dịch chấp nhận lời gọi vì MessageSender khai báo send; khi chạy, phương thức EmailSender.send được gọi.

Nếu EmailSender có thêm phương thức riêng connectSmtp(), biểu thức sender.connectSmtp() **không biên dịch**, vì connectSmtp() không thuộc API của MessageSender. Việc ép kiểu xuống EmailSender có thể làm code chạy với một implementation nhưng phá khả năng thay thế; chỉ dùng khi thật sự cần logic đặc thù và đã kiểm tra kiểu.

Không nhầm **đa hình qua phương thức override** với **overload**: overload chọn chữ ký thích hợp chủ yếu dựa trên kiểu tham số tại lúc biên dịch; override của phương thức instance được phân phối dựa trên đối tượng runtime. Static method không được override theo kiểu dispatch này.

## 4. Thiết kế một hợp đồng tốt

Hãy bắt đầu từ việc **consumer cần làm gì**, sau đó xác định tên thao tác, dữ liệu vào/ra, quy tắc lỗi và tác động phụ. Tránh đưa chi tiết kỹ thuật riêng của một implementation vào interface dùng chung.

Với MessageSender, một thỏa thuận hành vi thực tế có thể ghi rõ:

| Câu hỏi hợp đồng | Quy tắc cần định nghĩa |
| --- | --- |
| Điều kiện đầu vào | Message không null; recipient và body không rỗng |
| Thành công có nghĩa gì? | send hoàn tất sau khi bàn giao cho bộ gửi, hay sau khi hệ thống nhận xác nhận? Phải chọn một nghĩa |
| Khi gửi thất bại? | Ném ngoại lệ, trả về kết quả thất bại hoặc thử lại? Quy định nhất quán |
| Có gửi trùng không? | Nếu retry, cần hay không cần mã idempotency? |
| Có side effect nào? | Gửi mạng, ghi log, thay đổi trạng thái, tính phí... |
| Thread-safe không? | Có cho phép nhiều luồng gọi chung một sender? Nếu có, bảo đảm ở mức nào? |

Trong ví dụ chạy được ở trên, send chỉ in ra console. Vì vậy không thể suy ra **đã giao email thành công**, cơ chế retry hay thread safety của một hệ thống gửi thực. Những bảo đảm đó chỉ được thêm vào hợp đồng và implementation khi thực sự cần.

**Nguyên tắc khi thay thế implementation:** consumer không nên phải đổi logic hay chịu kết quả trái với những bảo đảm đã công bố. Ví dụ, nếu hợp đồng hứa rằng một lệnh gửi lỗi sẽ báo thất bại, implementation âm thầm bỏ qua lỗi là sai **hợp đồng hành vi** dù vẫn biên dịch. Đây là tinh thần của khả năng thay thế (Liskov substitution): implementation không được làm suy yếu những điều kiện mà consumer có quyền kỳ vọng.

Đặt tên theo **năng lực** thường giúp hợp đồng rõ hơn tên theo công nghệ: MessageSender diễn tả “gửi thông báo”; SmtpMessageSender hoặc EmailSender mô tả một cách thực hiện. Tuy nhiên, đừng tạo interface một phương thức vô nghĩa cho mọi class; hợp đồng có giá trị khi nó biểu diễn một ranh giới thật sự được dùng hoặc có khả năng thay thế/kiểm thử.

## 5. Interface, abstract class và lớp cụ thể

Java cung cấp nhiều cách biểu diễn hợp đồng. Chọn dựa trên nhu cầu chia sẻ API, trạng thái và logic.

| Đặc điểm | Interface | Abstract class |
| --- | --- | --- |
| Mục đích nổi bật | Công bố năng lực để nhiều kiểu cùng triển khai | Cung cấp khuôn mẫu và phần triển khai dùng chung cho các lớp có quan hệ kế thừa |
| Quan hệ từ lớp cụ thể | implements nhiều interface | extends tối đa một lớp cha |
| Trạng thái instance | Không có trường instance; trường khai báo trong interface ngầm là public static final | Có trường instance, constructor và trạng thái được bảo vệ |
| Phương thức | Có abstract, default, static và private (theo phiên bản Java phù hợp) | Có abstract và phương thức có thân; có thể dùng protected |
| Constructor | Không có constructor | Có constructor để khởi tạo phần trạng thái của lớp cha |

Một interface có thể khai báo phương thức default để chia sẻ hành vi mặc định, nhưng **default method không biến interface thành nơi chứa trạng thái instance**. Từ Java 9, interface còn có private method để tái sử dụng logic nội bộ giữa các default/static method.

Abstract class thích hợp khi những lớp con thật sự chia sẻ quy trình hoặc invariant. Ví dụ minh họa (không phải chương trình độc lập):

~~~java
abstract class BaseSender implements MessageSender {
    protected void validate(Message message) {
        Objects.requireNonNull(message, "message");
    }
}

final class LoggingSender extends BaseSender {
    @Override
    public void send(Message message) {
        validate(message);
        System.out.println("Logging: " + message.body());
    }
}
~~~

Đoạn này sử dụng import java.util.Objects và record/interface Message, MessageSender đã khai báo ở ví dụ trước. Nó cho thấy một abstract class có thể **triển khai interface** và cung cấp logic dùng chung. Việc có sẵn logic validate chưa đủ để kết luận bắt buộc dùng kế thừa; nhiều trường hợp một đối tượng Validator riêng được truyền vào theo **composition** sẽ linh hoạt hơn.

Một số quy tắc biên dịch quan trọng:

- Khi class triển khai một interface, phương thức thực hiện phương thức public của interface phải có mức truy cập **public** (không thể giảm xuống package-private hay private).
- Kiểu trả về của phương thức override phải phù hợp, có thể là kiểu con theo quy tắc covariant return của Java.
- Implementation không được khai báo thêm checked exception rộng hơn những gì phương thức ở hợp đồng cho phép. Unchecked exception vẫn có thể phát sinh nhưng cần mô tả ý nghĩa hợp đồng.
- Một lớp cụ thể phải cài đặt đầy đủ các phương thức abstract được thừa kế, nếu không nó cũng phải được khai báo abstract.
- Nếu hai interface cung cấp default method trùng chữ ký mà không có cách phân giải ưu tiên hợp lệ, lớp triển khai phải override để giải quyết xung đột.
- Interface không tự động làm một đối tượng bất biến. Tính bất biến và thread safety là đặc tính của implementation và dữ liệu liên quan.

## 6. Ai tạo implementation, ai sử dụng?

Thiết kế có hai loại công việc khác nhau:

- **Composition/wiring**: quyết định tạo đối tượng cụ thể nào và truyền nó vào đâu. Trong ví dụ, main làm việc này bằng new EmailSender() hoặc new ConsoleSender().
- **Business behavior**: consumer gọi hợp đồng để thực hiện nghiệp vụ. AlertService không xây sender; nó nhận sender qua constructor.

Truyền phụ thuộc qua constructor (constructor injection) có ba lợi ích: mã consumer trình bày rõ thứ nó cần, đối tượng sau khi tạo có trạng thái phụ thuộc hợp lệ, và có thể thay implementation ở vị trí wiring. Một framework DI như Spring có thể hỗ trợ tự tạo và nối đối tượng, nhưng nguyên tắc thiết kế đã áp dụng đầy đủ trong **Java thuần** và không yêu cầu framework.

So sánh:

~~~java
// Gan chat vao cach trien khai cu the:
final class TightlyCoupledAlertService {
    private final EmailSender sender = new EmailSender();
}

// Linh hoat qua hop dong:
final class LooselyCoupledAlertService {
    private final MessageSender sender;

    LooselyCoupledAlertService(MessageSender sender) {
        this.sender = Objects.requireNonNull(sender, "sender");
    }
}
~~~

Đây là các đoạn minh họa dùng lại EmailSender/MessageSender và import java.util.Objects của ví dụ đầu, không phải tệp độc lập. Khác biệt chính không nằm ở việc có dùng new ở bất kỳ đâu hay không: new vẫn xuất hiện ở **vùng wiring**; điều cần tránh là consumer tự chọn và phụ thuộc vào chi tiết bên gửi.

Cũng cần tránh cấu trúc quá mức: nếu một chức năng chỉ có một implementation, không có ranh giới cần kiểm thử/hoán đổi và API đơn giản, một lớp cụ thể trực tiếp có thể là lựa chọn tốt. Đánh giá theo nhu cầu sử dụng thực tế.

## 7. Kiểm thử consumer bằng implementation giả

Một lợi ích cụ thể của hợp đồng là có thể kiểm tra **AlertService đã gửi đúng thông điệp** mà không cần mạng và không phải nhìn output console. Tạo tệp thứ hai **ContractDemoTest.java** cạnh ContractDemo.java:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ContractDemoTest {
    static final class RecordingSender implements MessageSender {
        final List<Message> sent = new ArrayList<>();

        @Override
        public void send(Message message) {
            sent.add(message);
        }
    }

    public static void main(String[] args) {
        RecordingSender fake = new RecordingSender();
        AlertService service = new AlertService(fake);

        service.notifyUser("tester", "Da gui thong bao");

        Message expected = new Message("tester", "Da gui thong bao");
        if (fake.sent.size() != 1 || !fake.sent.get(0).equals(expected)) {
            throw new AssertionError("Sai so lan gui hoac noi dung");
        }
        System.out.println("PASS: 1 message");
    }
}
~~~

Biên dịch và chạy (hai tệp cùng thư mục, không khai báo package):

~~~bash
javac -encoding UTF-8 ContractDemo.java ContractDemoTest.java
java ContractDemoTest
~~~

Kết quả:

~~~text
PASS: 1 message
~~~

RecordingSender là một **test double/fake**: nó tuân thủ cùng interface, nhưng thay việc gửi thực bằng ghi nhận lời gọi. Kiểm thử trên chứng minh consumer tạo và chuyển đúng thông điệp; nó **không chứng minh** EmailSender kết nối được SMTP hoặc nhà cung cấp email hoạt động. Các implementation thật cần kiểm thử riêng cho phần tích hợp bên ngoài và các quy tắc hành vi của chúng.

## 8. Thay đổi hợp đồng và tương thích

Hợp đồng là điểm kết nối giữa nhiều phần mã nên thay đổi nó có thể lan đến cả consumer lẫn implementation:

1. **Thêm một phương thức abstract vào interface**: các lớp implement hiện hữu thường phải bổ sung phương thức, nếu không sẽ có lỗi biên dịch khi build lại.
2. **Thêm một default method**: có thể giữ được tương thích nguồn cho nhiều implementation, nhưng vẫn cần xét xung đột default method, ý nghĩa mặc định và các loại tương thích (source/binary/behavior).
3. **Đổi kiểu tham số, tên phương thức hoặc kiểu trả về**: có thể buộc consumer và implementation sửa code; phải đánh giá tác động thay vì coi là thay đổi nội bộ.
4. **Đổi hành vi dù chữ ký không đổi**: cũng là thay đổi hợp đồng. Ví dụ chuyển từ “ném lỗi khi gửi thất bại” sang “bỏ qua lỗi” có thể làm consumer xử lý sai, mặc dù mã vẫn biên dịch.

Cách mở rộng an toàn là mô tả trước kỳ vọng, xem xét mọi implementation, chạy kiểm thử contract và consumer, rồi mới đưa API mới vào sử dụng. Nếu cần một năng lực riêng cho số ít implementation, cân nhắc tạo một hợp đồng khác thay vì ép toàn bộ lớp hiện hữu gánh phương thức không hợp lệ với chúng. Đây là ý tưởng phân tách interface theo nhu cầu thực của bên dùng.

Đối với thư viện đã phát hành, mức độ tương thích cần đánh giá cả mã đã biên dịch và các client ngoài repository; không nên kết luận một thay đổi “tương thích” chỉ vì một project Java nội bộ vẫn build được.

## 9. Các lỗi hay gặp và cách tự kiểm tra

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Consumer khai báo trường bằng implementation cụ thể và tự new | Gắn chặt vào một công nghệ; khó thay thế | Nhận tham số mang kiểu hợp đồng ở constructor hoặc phương thức |
| Interface mang tên chung nhưng chứa quá nhiều phương thức không liên quan | Lớp triển khai buộc có các thao tác vô nghĩa | Tách hợp đồng theo nhóm consumer/năng lực |
| Cho rằng implements bảo đảm đúng nghiệp vụ | Implementation có thể trả giá trị sai, nuốt lỗi, gây side effect bất ngờ | Ghi hợp đồng hành vi và kiểm thử từng implementation |
| Ép kiểu từ interface sang class cụ thể để gọi API riêng | Thay implementation có thể gây ClassCastException hoặc hỏng logic | Đưa năng lực thực sự chung vào interface phù hợp hoặc tách luồng riêng |
| Dùng abstract class chỉ để tái sử dụng vài dòng tiện ích | Bị khóa bởi một superclass; kế thừa gượng ép | Xem xét composition hoặc utility phù hợp |
| Dùng default method làm nơi giấu hành vi nguy hiểm | Implementation cũ âm thầm nhận hành vi không mong muốn | Chỉ dùng khi mặc định có ý nghĩa hợp đồng và được kiểm thử |
| Chỉ kiểm tra fake rồi tuyên bố đã tích hợp thành công | Bỏ sót lỗi hạ tầng/IO và khác biệt implementation | Tách unit test consumer và integration/contract test implementation |

Khi đọc một đoạn Java có interface, hãy tự trả lời:

1. **Ai là contract?** Phương thức nào consumer được phép gọi và quy tắc hành vi nào đã được cam kết?
2. **Ai là implementation?** Lớp nào khai báo implements hoặc kế thừa, phần nào chứa xử lý thật?
3. **Ai là consumer?** Nó khai báo phụ thuộc bằng kiểu gì? Nó có biết chi tiết implementation không?
4. **Ai wiring?** Đối tượng cụ thể được tạo ở đâu và được đưa đến consumer bằng cách nào?
5. **Có thể thay implementation?** Nếu thay EmailSender bằng RecordingSender hoặc ConsoleSender, business logic có chạy đúng kỳ vọng mà không sửa không?
6. **Bằng chứng nào xác nhận?** Lệnh biên dịch, output minh họa, unit test consumer và kiểm thử hành vi/tích hợp của implementation có trả lời đúng câu hỏi riêng của chúng không?

## 10. Tổng kết tư duy áp dụng

Một thiết kế tốt bắt đầu từ **nhu cầu của consumer**: định nghĩa một API nhỏ, dễ hiểu cùng bảo đảm hành vi cần thiết; cung cấp một hoặc nhiều implementation; rồi đưa implementation vào consumer qua hợp đồng. **Interface mô tả năng lực, implementation cung cấp cơ chế, consumer giải quyết nghiệp vụ, còn vùng wiring chọn đối tượng thực tế.**

Cấu trúc này phát huy tác dụng khi cần đa hình, thay thế chiến lược, cấu hình môi trường, kiểm thử độc lập và quản lý phụ thuộc. Nó không thay thế việc đặc tả hành vi, kiểm thử thực tế hay chọn ranh giới module hợp lý.