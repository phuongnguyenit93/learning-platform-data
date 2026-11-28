# Composition, delegation và giảm phụ thuộc vào kế thừa

Trong Java 27, kế thừa lớp (`extends`), triển khai giao diện (`implements`), composition và delegation đều là những công cụ thiết kế hướng đối tượng còn được sử dụng. Vấn đề không phải chọn một cơ chế cho mọi trường hợp, mà là xác định **quan hệ thực sự giữa các đối tượng**, hợp đồng hành vi cần duy trì và tác động của mỗi thay đổi lên các thành phần còn lại.

**Composition** xây dựng một đối tượng bằng cách kết hợp các đối tượng cộng tác. **Delegation** là kỹ thuật để một đối tượng chuyển một phần công việc cho đối tượng khác thực hiện. Hai kỹ thuật thường đi cùng nhau: một lớp lưu đối tượng cộng tác trong field rồi gọi phương thức của đối tượng đó khi cần.

Chủ đề này thuộc phần *Kế thừa và thiết kế hướng đối tượng* của Java 27. Nội dung dùng các quy tắc và API hiện hành, đặc biệt là `interface`, constructor injection, `final`, `record` và `sealed`. Các ví dụ chỉ dùng tính năng Java ổn định, không cần bật Preview hay dùng API đã lỗi thời.

## 1. Phân biệt inheritance, composition và delegation

### 1.1. Kế thừa lớp: quan hệ is-a

Khi một lớp dùng `extends`, nó tạo quan hệ lớp con với lớp cha:

~~~java
class Vehicle {
    void move() {
        System.out.println("Moving");
    }
}

class Bicycle extends Vehicle {
    @Override
    void move() {
        System.out.println("Pedaling");
    }
}
~~~

Một đối tượng `Bicycle` là một `Vehicle` theo hệ kiểu Java. Lớp con có thể kế thừa và ghi đè các phương thức có thể override của lớp cha. Đây là quan hệ **is-a** và tạo cơ chế đa hình qua kiểu lớp cha.

Tuy nhiên, việc hai lớp cùng cần một đoạn mã không tự động chứng minh giữa chúng có quan hệ is-a. Nếu lớp A chỉ muốn tận dụng một hàm tiện ích của lớp B, cho A kế thừa B có thể làm lộ API hoặc ràng buộc hành vi không phù hợp.

Java cho phép một lớp mở rộng tối đa một lớp cha trực tiếp, đồng thời có thể triển khai nhiều interface. Khả năng kế thừa lớp và triển khai interface là hai khái niệm cần phân biệt khi thiết kế.

### 1.2. Composition: đối tượng có hoặc sử dụng đối tượng khác

Composition dùng một field để giữ tham chiếu đến đối tượng cộng tác:

~~~java
interface Formatter {
    String format(String input);
}

final class UppercaseFormatter implements Formatter {
    @Override
    public String format(String input) {
        return input.toUpperCase();
    }
}

final class ReportService {
    private final Formatter formatter;

    ReportService(Formatter formatter) {
        this.formatter = java.util.Objects.requireNonNull(formatter);
    }

    String prepare(String text) {
        return formatter.format(text);
    }
}
~~~

`ReportService` **có một** `Formatter` và sử dụng nó; `ReportService` không phải là một `Formatter`. Lớp phục vụ nghiệp vụ giữ trách nhiệm điều phối, còn logic định dạng thuộc về thành phần được truyền vào.

Một quan hệ composition không bắt buộc đối tượng chủ tự tạo collaborator bằng `new`. Đối tượng cộng tác có thể được tạo ở nơi khác rồi truyền qua constructor, factory hoặc phương thức cấu hình. Trong thiết kế ứng dụng, cơ chế này thường được gọi là **constructor injection** khi dependency được truyền qua constructor.

### 1.3. Delegation: chuyển hành vi sang đối tượng cộng tác

Delegation nói về **hành vi lúc thực thi**:

~~~java
final class SafeFormatter implements Formatter {
    private final Formatter delegate;

    SafeFormatter(Formatter delegate) {
        this.delegate = java.util.Objects.requireNonNull(delegate);
    }

    @Override
    public String format(String input) {
        String safeInput = java.util.Objects.requireNonNullElse(input, "");
        return delegate.format(safeInput);
    }
}
~~~

`SafeFormatter` tự triển khai contract `Formatter` nhưng ủy quyền phần định dạng chính cho `delegate`. Nó bổ sung quy tắc xử lý null trước khi chuyển tiếp lời gọi.

Chữ `delegate` chỉ là tên biến thông dụng, không phải từ khóa Java. Java không tự chuyển tiếp toàn bộ phương thức của đối tượng cộng tác: lớp phải khai báo rõ phương thức nào được chuyển tiếp và có thể bổ sung xử lý trước hoặc sau.

### 1.4. So sánh ba cơ chế

| Cơ chế | Quan hệ chính | Cách viết trong Java | Hệ quả thiết kế |
|---|---|---|---|
| Kế thừa lớp | A **là một loại** B | `class A extends B` | A nhận quan hệ subtype, chịu hợp đồng và thay đổi của lớp B |
| Composition | A **có/sử dụng** B | Field, constructor, đối tượng cộng tác | A quyết định khi nào và cách nào dùng B |
| Delegation | A **giao việc** cho B | Phương thức A gọi phương thức B | Hành vi được chuyển tiếp có chủ đích |
| Triển khai interface | A **đáp ứng contract** I | `class A implements I` | Các implementation có thể thay thế qua kiểu I mà không cần chung lớp cha ứng dụng |

Composition và delegation thường kết hợp với `implements`. Một lớp có thể là một `Sender` theo interface, đồng thời dùng composition để chuyển việc gửi cho một `Sender` khác.

## 2. Vì sao lạm dụng kế thừa làm tăng phụ thuộc?

### 2.1. Tái sử dụng mã chưa đủ để tạo quan hệ is-a

Xét một dịch vụ xử lý đơn hàng muốn dùng chức năng gửi thông báo:

~~~java
class EmailSender {
    void sendEmail(String address, String text) {
        System.out.println("Email to " + address + ": " + text);
    }
}

class OrderService extends EmailSender {
    void completeOrder(String customerEmail) {
        sendEmail(customerEmail, "Đơn hàng đã hoàn tất");
    }
}
~~~

Mã có thể chạy, nhưng `OrderService` không phải một loại `EmailSender` về mặt nghiệp vụ. Việc kế thừa còn làm `sendEmail` trở thành phương thức được kế thừa, khiến API của `OrderService` bị gắn với chi tiết gửi email.

Nếu ngày mai hệ thống chuyển sang SMS, gửi qua API bên ngoài hoặc lưu vào hàng đợi, thay đổi phương thức gửi có thể buộc sửa cây kế thừa. Kế thừa được dùng chỉ để tái sử dụng vài dòng mã đang tạo ra một quan hệ subtype sai về ngữ nghĩa.

### 2.2. Phụ thuộc vào chi tiết triển khai của lớp cha

Khi lớp con override một phương thức hoặc gọi `super.method()`, nó có thể phụ thuộc vào:

- Thứ tự lớp cha gọi các phương thức có thể override.
- Trạng thái `protected` và các giả định nội bộ của lớp cha.
- Quy tắc khởi tạo của lớp cha và lớp con.
- Hợp đồng exception và bất biến (invariant) do lớp cha đặt ra.
- Các điểm mở rộng mà lớp cha công bố cho subclass.

Khi lớp cha thay đổi triển khai, subclass có thể đổi hành vi dù mã của subclass không sửa. Đây là một dạng rủi ro **fragile base class**. Nó đặc biệt đáng chú ý khi lớp cha do thư viện khác cung cấp hoặc được duy trì bởi một nhóm khác.

Composition giới hạn bề mặt tương tác vào các phương thức mà lớp chủ thực sự gọi trên collaborator. Khi collaborator được khai báo qua interface nhỏ và ổn định, thay đổi trong implementation ít lan sang lớp chủ hơn.

### 2.3. Liskov Substitution Principle (LSP)

Một subtype phải có khả năng được dùng tại những nơi mong đợi supertype mà vẫn duy trì hợp đồng hành vi. Đây là nguyên tắc thay thế Liskov, thường viết tắt là **LSP**.

Ví dụ, một lớp con có thể override phương thức nhưng thay đổi điều kiện đầu vào hoặc ngữ nghĩa trả về theo cách làm hỏng giả định của người gọi. Trình biên dịch Java kiểm tra tính hợp lệ của override theo kiểu và một số quy tắc ngôn ngữ; trình biên dịch không thể tự chứng minh mọi hợp đồng nghiệp vụ đều được giữ nguyên.

Composition giúp tránh tuyên bố sai về subtype khi quan hệ thực tế chỉ là sử dụng một dịch vụ. Dù vậy, implementation của interface cũng phải giữ đúng contract. Chuyển sang composition không tự động giải quyết mọi vi phạm LSP.

## 3. Ví dụ hoàn chỉnh: gửi thông báo bằng composition và delegation

Ví dụ sau tách ba vai trò:

1. `WelcomeService` quyết định **khi nào** cần gửi thông báo chào mừng.
2. `MessageSender` định nghĩa contract **gửi** một thông báo.
3. Các implementation quyết định **gửi bằng cách nào** hoặc **ghi nhận kết quả**.

Một wrapper `AuditedSender` minh họa delegation: nó nhận một `MessageSender`, chuyển tiếp lời gọi gửi và bổ sung hành vi ghi nhận audit sau khi gửi thành công.

### 3.1. Mã nguồn độc lập, có thể chạy

Lưu đoạn mã sau thành file `CompositionDemo.java`. Ví dụ chỉ dùng Java chuẩn; không dùng framework hoặc tính năng Preview.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Consumer;

public final class CompositionDemo {

    public record Notice(String recipient, String body) {
        public Notice {
            Objects.requireNonNull(recipient, "recipient");
            Objects.requireNonNull(body, "body");
        }
    }

    public interface MessageSender {
        void send(Notice notice);
    }

    public static final class ConsoleSender implements MessageSender {
        @Override
        public void send(Notice notice) {
            System.out.println("To " + notice.recipient()
                    + ": " + notice.body());
        }
    }

    public static final class RecordingSender implements MessageSender {
        private final List<Notice> sent = new ArrayList<>();

        @Override
        public void send(Notice notice) {
            sent.add(Objects.requireNonNull(notice));
        }

        public List<Notice> sentMessages() {
            return List.copyOf(sent);
        }
    }

    public static final class AuditedSender implements MessageSender {
        private final MessageSender delegate;
        private final Consumer<Notice> audit;

        public AuditedSender(MessageSender delegate,
                             Consumer<Notice> audit) {
            this.delegate = Objects.requireNonNull(delegate);
            this.audit = Objects.requireNonNull(audit);
        }

        @Override
        public void send(Notice notice) {
            delegate.send(notice);
            audit.accept(notice);
        }
    }

    public static final class WelcomeService {
        private final MessageSender sender;

        public WelcomeService(MessageSender sender) {
            this.sender = Objects.requireNonNull(sender);
        }

        public void welcome(String recipient) {
            sender.send(new Notice(recipient, "Chào mừng Java 27"));
        }
    }

    public static void main(String[] args) {
        var recording = new RecordingSender();

        MessageSender audited = new AuditedSender(
                recording,
                notice -> System.out.println("Audited recipient: "
                        + notice.recipient())
        );

        var service = new WelcomeService(audited);
        service.welcome("developer@example.com");

        System.out.println(recording.sentMessages().size()); // 1

        var consoleService = new WelcomeService(new ConsoleSender());
        consoleService.welcome("team@example.com");
    }
}
~~~

Để chạy:

~~~bash
javac CompositionDemo.java
java CompositionDemo
~~~

Kết quả bao gồm một dòng audit, số lượng thông báo đã được ghi nhận và một dòng hiển thị thông báo ở console.

### 3.2. Những quan hệ có trong ví dụ

~~~mermaid
flowchart LR
    A[WelcomeService] -->|giữ tham chiếu| B[MessageSender]
    C[ConsoleSender] -.->|implements| B
    D[RecordingSender] -.->|implements| B
    E[AuditedSender] -.->|implements| B
    E -->|ủy quyền send| B
~~~

`WelcomeService` không có quan hệ `extends` với bất kỳ sender nào. Nó chỉ biết contract `MessageSender`. Vì vậy, cùng một đối tượng nghiệp vụ có thể dùng implementation khác nhau, miễn implementation tuân thủ contract.

`AuditedSender` vừa **implements** interface, vừa **compose** một implementation khác. Nó có thể được sử dụng ở bất kỳ nơi nào chấp nhận `MessageSender`. Đây là sự kết hợp giữa đa hình theo interface và delegation để tái sử dụng hành vi.

### 3.3. Điều gì diễn ra khi gọi phương thức?

Với lời gọi `service.welcome("developer@example.com")`:

1. `WelcomeService` tạo một `Notice` hợp lệ.
2. `WelcomeService` gọi `send` trên đối tượng được khai báo kiểu `MessageSender`.
3. Runtime dispatch chọn implementation `AuditedSender.send`.
4. `AuditedSender` gọi `delegate.send`, ở đây là `RecordingSender.send`.
5. `RecordingSender` ghi nhận thông báo.
6. `AuditedSender` gọi hàm audit, rồi trả quyền điều khiển cho `WelcomeService`.

Nếu `delegate.send` ném exception, dòng audit phía sau không được thực hiện trong ví dụ. Đây là một quyết định về hợp đồng hành vi: audit sau khi gửi thành công khác với audit mọi lần cố gắng gửi. Khi xây dựng hệ thống thật, cần mô tả rõ cách xử lý lỗi, retry, tính idempotent và thứ tự các side effect.

### 3.4. Thay đổi implementation mà không sửa dịch vụ

Với thiết kế dùng inheritance ở mục 2, đổi phương thức gửi có thể khiến lớp nghiệp vụ phải sửa quan hệ lớp cha. Ở thiết kế composition, caller lựa chọn collaborator:

~~~java
var serviceA = new CompositionDemo.WelcomeService(
        new CompositionDemo.ConsoleSender()
);

var serviceB = new CompositionDemo.WelcomeService(
        new CompositionDemo.RecordingSender()
);
~~~

Mã `WelcomeService` không đổi. Thay đổi được tập trung ở nơi lắp ghép các đối tượng (composition root) và implementation của `MessageSender`.

Điều đó không có nghĩa chi phí thay đổi biến mất: nếu contract `MessageSender` đổi, các implementation và người sử dụng contract vẫn có thể phải cập nhật. Lợi ích thực tế đến từ việc **giữ contract nhỏ và ổn định**, đồng thời không làm lớp nghiệp vụ phụ thuộc trực tiếp vào chi tiết gửi.

## 4. Delegation không đồng nghĩa kế thừa tự động

### 4.1. Forwarding phải được viết rõ

Java không tự ủy quyền mọi phương thức của collaborator:

~~~java
interface Clock {
    long nowMillis();
}

final class Timer {
    private final Clock clock;

    Timer(Clock clock) {
        this.clock = java.util.Objects.requireNonNull(clock);
    }

    long elapsedSince(long startedAt) {
        return clock.nowMillis() - startedAt;
    }
}
~~~

`Timer` sử dụng `Clock` để tính thời gian đã trôi qua nhưng không tự có phương thức `nowMillis()` trong API public. Nếu muốn công bố phương thức đó, người viết lớp phải khai báo phương thức forwarding một cách tường minh.

Đây là ưu điểm của composition: lớp chủ chọn API nào được đưa ra ngoài. Đồng thời, nó có chi phí là phải viết những phương thức forwarding thực sự cần thiết.

### 4.2. Điều chỉnh hành vi trước và sau khi ủy quyền

Một wrapper có thể bổ sung validation, metrics, tracing, cache, retry hoặc kiểm soát truy cập. Tuy nhiên, mỗi lớp bổ sung đều có thể thay đổi thứ tự side effect, thời gian phản hồi hoặc cách exception được xử lý.

Ví dụ một wrapper kiểm tra đầu vào:

~~~java
final class ValidatingSender implements CompositionDemo.MessageSender {
    private final CompositionDemo.MessageSender delegate;

    ValidatingSender(CompositionDemo.MessageSender delegate) {
        this.delegate = java.util.Objects.requireNonNull(delegate);
    }

    @Override
    public void send(CompositionDemo.Notice notice) {
        java.util.Objects.requireNonNull(notice, "notice");

        if (notice.recipient().isBlank()) {
            throw new IllegalArgumentException("Recipient is blank");
        }

        delegate.send(notice);
    }
}
~~~

Wrapper vẫn bảo đảm contract `MessageSender` nhưng đặt thêm chính sách validation trước khi gọi collaborator. Hãy xác định validation là trách nhiệm chung của tầng nào để tránh kiểm tra trùng lặp hoặc có nhiều nơi đưa ra quyết định khác nhau.

### 4.3. Delegation không phải inheritance hay override

| Đặc điểm | Ghi đè phương thức trong subclass | Delegation |
|---|---|---|
| Quan hệ kiểu | Subclass là subtype của superclass | Lớp chủ không cần là subtype của delegate |
| Cách gọi lại hành vi | Thường gọi `super.method()` hoặc phương thức kế thừa | Gọi `delegate.method()` |
| Quyền chọn implementation | Ràng buộc bởi quan hệ lớp cha | Có thể truyền một implementation khác tại thời điểm tạo đối tượng |
| API được công bố | Có thể nhận các thành viên kế thừa theo quy tắc Java | Chỉ những phương thức lớp chủ khai báo hoặc kế thừa từ contract riêng |
| Rủi ro chính | Phụ thuộc lớp cha, override và invariant | Contract không rõ, wrapper dài, vòng delegation và side effect |

Khi đối tượng triển khai một interface rồi forwarding sang một implementation khác của chính interface đó, phương thức forwarding vẫn là một phương thức bình thường, không phải lời gọi `super`.

## 5. Giảm coupling bằng interface và dependency injection

### 5.1. Phụ thuộc vào contract, không phụ thuộc cách triển khai

Đặt đối tượng cộng tác trong một field kiểu interface:

~~~java
interface TaxPolicy {
    long taxFor(long amountCents);
}

final class InvoiceService {
    private final TaxPolicy taxPolicy;

    InvoiceService(TaxPolicy taxPolicy) {
        this.taxPolicy = java.util.Objects.requireNonNull(taxPolicy);
    }

    long total(long subtotalCents) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        long tax = taxPolicy.taxFor(subtotalCents);
        return Math.addExact(subtotalCents, tax);
    }
}
~~~

`InvoiceService` chỉ cần biết rằng collaborator có phương thức `taxFor`. Nó không cần biết implementation lưu cấu hình ở đâu, gọi HTTP hay tính toán trực tiếp.

Có thể cung cấp các chính sách khác nhau:

~~~java
TaxPolicy noTax = amount -> 0L;
TaxPolicy flatTax = amount -> 5_000L;

var first = new InvoiceService(noTax);
var second = new InvoiceService(flatTax);

System.out.println(first.total(100_000L));  // 100000
System.out.println(second.total(100_000L)); // 105000
~~~

Đây là kỹ thuật tương tự **Strategy pattern**: hành vi có thể thay đổi được đóng gói sau một contract rồi được chọn khi lắp ghép object graph.

Trong mã sản phẩm, công thức tính thuế phải phản ánh quy định và yêu cầu nghiệp vụ thực tế; hai chính sách ở trên chỉ minh họa cơ chế thay thế implementation.

### 5.2. Constructor injection giúp nhìn rõ dependency

Một constructor khai báo các cộng tác viên bắt buộc:

~~~java
final class CheckoutService {
    private final PaymentGateway payments;
    private final ReceiptSender receipts;

    CheckoutService(PaymentGateway payments, ReceiptSender receipts) {
        this.payments = java.util.Objects.requireNonNull(payments);
        this.receipts = java.util.Objects.requireNonNull(receipts);
    }

    void checkout(Order order) {
        payments.charge(order);
        receipts.sendReceipt(order);
    }
}
~~~

Đoạn trên giả định `PaymentGateway`, `ReceiptSender` và `Order` là các kiểu đã được định nghĩa trong hệ thống. Nó cho thấy một lớp có thể có nhiều collaborator theo chức năng, không cần kế thừa từ một class khổng lồ chỉ để sử dụng các chức năng đó.

Constructor injection thường đem lại các lợi ích:

- Dependency bắt buộc xuất hiện trong chữ ký constructor.
- Không cần mở rộng lớp cha để thay implementation.
- Dễ tạo đối tượng kiểm thử bằng fake hoặc stub.
- Có thể dùng field `final` để tránh thay đổi tham chiếu collaborator sau khi tạo.

Các lợi ích này không phụ thuộc một framework DI cụ thể. Framework có thể hỗ trợ lắp ghép object graph, nhưng bản thân composition hoạt động hoàn toàn bằng Java thuần.

### 5.3. Interface nhỏ giúp tránh phụ thuộc không cần thiết

Nếu một dịch vụ chỉ cần gửi thông báo, không nhất thiết phải biết mọi thao tác quản trị của sender:

~~~java
interface MessageSender {
    void send(String recipient, String content);
}

interface MessageAdministration {
    void purgeFailedMessages();
    void pauseDelivery();
}
~~~

Một class có thể triển khai cả hai interface nếu thực sự hỗ trợ cả hai chức năng. Dịch vụ nghiệp vụ chỉ nhận `MessageSender`, nên không phụ thuộc vào các thao tác quản trị.

Điều này liên quan đến **Interface Segregation Principle (ISP)**: client nên phụ thuộc vào những khả năng mà nó sử dụng. Tuy vậy, không nên tạo quá nhiều interface một phương thức chỉ vì một quy tắc hình thức; contract nên phản ánh ranh giới thay đổi và trách nhiệm thực tế.

## 6. Composition với pattern hiện hành

### 6.1. Strategy: thay đổi thuật toán

Một interface như `TaxPolicy` hoặc `ShippingPolicy` có thể đại diện cho nhiều thuật toán. Service giữ tham chiếu đến strategy và gọi nó. Khi thuật toán đổi, chỉ cần lắp ghép implementation mới trong phạm vi contract.

Strategy phù hợp khi nhiều thuật toán cùng mục đích, cần thử nghiệm độc lập hoặc được chọn theo cấu hình.

### 6.2. Decorator: thêm khả năng quanh một contract

`AuditedSender` trong ví dụ chính là dạng decorator: lớp wrapper implements cùng interface với collaborator và ủy quyền thao tác chính.

Có thể xâu chuỗi các decorator:

~~~java
CompositionDemo.MessageSender sender =
        new CompositionDemo.AuditedSender(
                new CompositionDemo.ConsoleSender(),
                notice -> System.out.println("Audit recorded")
        );
~~~

Trong hệ thống lớn, decorator có thể là lớp đo metrics, theo dõi thời gian, validate, retry hoặc cache. Thứ tự decorator có ý nghĩa: ví dụ, audit ở bên ngoài retry có thể ghi một lần cho toàn bộ yêu cầu, còn audit bên trong retry có thể ghi từng lần thử.

### 6.3. Adapter: chuyển đổi interface

Adapter dùng composition để kết nối hai API khác contract. Ví dụ, ứng dụng cần interface `MessageSender` nhưng thư viện thứ ba cung cấp method `deliver(String, String)`.

~~~java
interface ExternalMessenger {
    void deliver(String destination, String payload);
}

final class ExternalMessageAdapter
        implements CompositionDemo.MessageSender {

    private final ExternalMessenger external;

    ExternalMessageAdapter(ExternalMessenger external) {
        this.external = java.util.Objects.requireNonNull(external);
    }

    @Override
    public void send(CompositionDemo.Notice notice) {
        external.deliver(notice.recipient(), notice.body());
    }
}
~~~

Khi thay nhà cung cấp, lớp adapter có thể thay mà `WelcomeService` vẫn làm việc qua interface ban đầu.

### 6.4. Composite pattern khác với composition nói chung

Tên **Composite pattern** dễ gây nhầm với **composition**.

- *Composition* là kỹ thuật ghép các đối tượng để hoàn thành nhiệm vụ.
- *Composite pattern* là một mẫu thiết kế chuyên biệt để biểu diễn cấu trúc cây, nơi một thành phần tổng hợp có thể chứa các thành phần cùng interface, chẳng hạn nhóm thành phần giao diện hoặc cây biểu thức.

Không phải hệ thống nào dùng composition cũng đang áp dụng Composite pattern.

## 7. Java 27: interface, record, sealed và final liên quan thế nào?

### 7.1. Interface hỗ trợ đa hình mà không cần chung lớp cha ứng dụng

Một class có thể `implements` nhiều interface, trong khi chỉ `extends` một class trực tiếp. Nhờ đó, các implementation độc lập có thể được dùng qua cùng một contract.

~~~java
interface Exportable {
    String export();
}

interface Validatable {
    boolean valid();
}

final class Document implements Exportable, Validatable {
    private final String text;

    Document(String text) {
        this.text = java.util.Objects.requireNonNull(text);
    }

    @Override
    public String export() {
        return text;
    }

    @Override
    public boolean valid() {
        return !text.isBlank();
    }
}
~~~

Đây vẫn là quan hệ subtype ở mức interface. Câu “ưu tiên composition hơn kế thừa” chủ yếu cảnh báo việc dùng `extends` để tái sử dụng triển khai lớp cha không phù hợp; nó **không** có nghĩa là phải tránh `implements`.

### 7.2. Record thể hiện dữ liệu, không thay cho mọi service

`record` phù hợp với đối tượng dữ liệu có thành phần được khai báo rõ ràng:

~~~java
record Address(String city, String street) {
    Address {
        java.util.Objects.requireNonNull(city);
        java.util.Objects.requireNonNull(street);
    }
}

record Customer(String id, Address address) {
    Customer {
        java.util.Objects.requireNonNull(id);
        java.util.Objects.requireNonNull(address);
    }
}
~~~

`Customer` **có một** `Address` — một ví dụ composition ở mức dữ liệu. Một record là `final` ngầm định và không thể kế thừa từ class ứng dụng khác; record vẫn có thể triển khai interface.

Record chỉ cung cấp bất biến đối với **tham chiếu tới các component**, không tự biến mọi object bên trong thành bất biến sâu. Nếu component chứa một list có thể sửa, người thiết kế phải quyết định có cần sao chép phòng vệ bằng `List.copyOf` hay không.

~~~java
record Batch(List<String> ids) {
    Batch {
        ids = List.copyOf(ids);
    }
}
~~~

`List.copyOf` tạo một list không cho sửa cấu trúc từ API List, nhưng nếu phần tử là object có thể sửa thì bản thân các object phần tử vẫn có thể thay đổi.

### 7.3. Sealed hierarchy dùng khi tập biến thể đã biết

Java SE 27 hỗ trợ `sealed` class và interface. Đây là công cụ giới hạn những subtype trực tiếp được phép tồn tại, phù hợp khi mô hình domain có một tập biến thể hữu hạn:

~~~java
sealed interface PaymentOutcome permits Paid, Declined {
}

record Paid(String transactionId) implements PaymentOutcome {
}

record Declined(String reason) implements PaymentOutcome {
}
~~~

`Paid` và `Declined` là hai implementation hợp lệ của `PaymentOutcome`; vì record ngầm định `final`, chúng đáp ứng yêu cầu đóng nhánh của sealed hierarchy.

`sealed` là một cơ chế **kiểm soát kế thừa/subtyping**, không phải một cách thay thế mọi quan hệ bằng composition. Nó đặc biệt hữu ích khi các biến thể là một phần mô hình miền, cần phân biệt rõ và kiểm soát tập subtype.

### 7.4. final giúp giới hạn mở rộng lớp

Một lớp `final` không thể bị subclass. Việc dùng `final` cho service hoặc implementation không được thiết kế làm extension point giúp tránh việc người dùng dựa vào các phương thức và trạng thái nội bộ để viết subclass.

~~~java
final class OrderCoordinator {
    private final CompositionDemo.MessageSender sender;

    OrderCoordinator(CompositionDemo.MessageSender sender) {
        this.sender = java.util.Objects.requireNonNull(sender);
    }
}
~~~

`final` của class ngăn kế thừa lớp. `final` của field ngăn gán lại field sau khi khởi tạo, nhưng không bảo đảm object mà field tham chiếu là bất biến hoặc an toàn luồng.

## 8. Khi nào kế thừa vẫn phù hợp?

Không có quy tắc cứng rằng mọi thiết kế đều phải thay `extends` bằng composition. Kế thừa lớp vẫn hữu ích nếu:

1. Lớp con thực sự là một chuyên biệt của lớp cha và giữ trọn hợp đồng hành vi.
2. Lớp cha được thiết kế rõ ràng để subclass, với extension points và invariant được công bố.
3. Cần khai thác một quan hệ phân cấp mà mọi subtype đều được dùng an toàn qua supertype.
4. Framework hoặc API có contract kế thừa rõ ràng mà việc triển khai interface/composition không diễn đạt tương đương.

Ví dụ, một base class trừu tượng có thể định nghĩa quy trình ổn định và chỉ cho subclass tùy biến một bước:

~~~java
abstract class DocumentRenderer {
    public final String render(String content) {
        String checked = java.util.Objects.requireNonNull(content);
        return renderBody(checked);
    }

    protected abstract String renderBody(String content);
}

final class PlainTextRenderer extends DocumentRenderer {
    @Override
    protected String renderBody(String content) {
        return content;
    }
}
~~~

Lớp cha sở hữu toàn bộ quy trình và công bố hook `renderBody`; subclass đáp ứng hợp đồng đó. Đây là dạng template method. Nếu nhu cầu thực tế chỉ là chọn thuật toán định dạng, một collaborator `Formatter` như ở mục 1 cũng có thể phù hợp và thường linh hoạt hơn.

Khi chọn inheritance, cần viết rõ những phương thức nào được override, invariant phải duy trì và hợp đồng cho subclass. Nếu không có lý do nghiệp vụ cho quan hệ subtype, hãy cân nhắc composition.

## 9. Những giới hạn và rủi ro của composition

Composition không tự động làm một thiết kế trở nên tốt. Nó cũng có những chi phí và bẫy thường gặp.

### 9.1. Wrapper có thể quá nhiều tầng

Nếu mọi chức năng đều được bọc thêm một lớp, quá trình debug sẽ phải lần theo nhiều lời gọi forwarding. Điều này làm log, stack trace và hành vi lỗi khó hiểu.

Nên tạo abstraction khi có ranh giới thay đổi, yêu cầu kiểm thử hoặc chính sách thực sự cần tách. Một lớp chỉ chuyển tiếp hàng chục phương thức mà không có contract rõ có thể là dấu hiệu thiết kế quá phức tạp.

### 9.2. Phụ thuộc implementation cụ thể vẫn tạo coupling

~~~java
final class TightCoupling {
    private final CompositionDemo.ConsoleSender sender =
            new CompositionDemo.ConsoleSender();
}
~~~

Đây vẫn là composition, nhưng lớp đã tự quyết định implementation và cách tạo dependency. Khi cần thay thế sender, phải sửa lớp này.

So sánh với việc nhận dependency thông qua constructor:

~~~java
final class LooserCoupling {
    private final CompositionDemo.MessageSender sender;

    LooserCoupling(CompositionDemo.MessageSender sender) {
        this.sender = java.util.Objects.requireNonNull(sender);
    }
}
~~~

Vì vậy, mức độ coupling phụ thuộc vào **kiểu contract, khả năng thay thế và ranh giới trách nhiệm**, chứ không chỉ vào việc có dùng một field thay vì `extends`.

### 9.3. Chia sẻ tham chiếu đến object có thể sửa

Khi nhiều object cùng giữ tham chiếu tới một collaborator mutable, thay đổi trạng thái từ nơi này có thể tác động nơi khác. Cần xác định ai có quyền sở hữu, ai được phép sửa và có cần đồng bộ khi sử dụng nhiều thread.

Constructor injection và field `final` không tự bảo đảm thread safety. Nếu collaborator có trạng thái mutable như `RecordingSender` ở ví dụ, cần thêm cơ chế đồng bộ phù hợp khi dùng đồng thời trên nhiều thread.

### 9.4. Tính đúng đắn của forwarding

Khi wrapper implements cùng contract như delegate, nó phải tôn trọng hành vi mà caller kỳ vọng, bao gồm validation, exception, thứ tự thao tác và các thuộc tính như idempotency.

Ví dụ, decorator retry một yêu cầu thanh toán có side effect có thể vô tình tạo giao dịch lặp nếu collaborator không hỗ trợ idempotency. Thiết kế tốt cần hiểu nghiệp vụ và hợp đồng vận hành, không chỉ thêm một lớp decorator.

### 9.5. API và khả năng tương thích

Thay public superclass bằng composition có thể làm thay đổi khả năng gán kiểu, phương thức kế thừa và cách dùng API của các caller hiện hữu. Đây có thể là thay đổi phá vỡ tương thích mã nguồn hoặc nhị phân.

Khi refactor một API đã phát hành, phải đánh giá người dùng của API, những method hoặc type contract đang công bố và cách di chuyển sang thiết kế mới. Không nên đổi `extends` thành field một cách máy móc nếu superclass là một phần public contract.

## 10. Cách chuyển từ inheritance sang composition

Một quy trình chuyển đổi có thể triển khai từng bước:

1. **Xác định lý do kế thừa:** lớp con có thực sự là subtype của lớp cha, hay chỉ đang dùng vài phương thức?
2. **Liệt kê hành vi được sử dụng:** đánh dấu phương thức lớp cha được gọi, override, trạng thái `protected` và các giả định về thứ tự gọi.
3. **Tách contract nhỏ:** tạo interface mô tả đúng khả năng mà client cần, tránh sao chép toàn bộ API của lớp cha.
4. **Chuyển implementation ra collaborator:** đặt logic tái sử dụng trong một class riêng và gọi qua interface.
5. **Truyền dependency qua constructor:** để nơi lắp ghép quyết định implementation phù hợp.
6. **Giữ các hành vi hiện có:** kiểm tra kết quả, exception, side effect, concurrency và API công khai có thay đổi không.
7. **Giảm dần sự phụ thuộc vào lớp cha:** chỉ bỏ quan hệ `extends` khi mọi caller và hợp đồng liên quan đã được chuyển đổi an toàn.

Ví dụ chuyển từ kế thừa dùng sai nghĩa:

~~~java
// Thiết kế ban đầu: OrderService bị coi như một EmailSender.
class EmailSender {
    void send(String text) {
        System.out.println(text);
    }
}

class OrderService extends EmailSender {
    void complete() {
        send("Order completed");
    }
}
~~~

Sang composition:

~~~java
interface Sender {
    void send(String text);
}

final class ConsoleSender implements Sender {
    @Override
    public void send(String text) {
        System.out.println(text);
    }
}

final class OrderService {
    private final Sender sender;

    OrderService(Sender sender) {
        this.sender = java.util.Objects.requireNonNull(sender);
    }

    void complete() {
        sender.send("Order completed");
    }
}
~~~

Ở phiên bản mới, `OrderService` có một dependency `Sender` và giao việc gửi thông báo cho nó. Quan hệ subtype không còn bị tuyên bố sai. Các caller có thể chọn một sender khác mà không sửa nghiệp vụ `complete()`.

## 11. Cách kiểm tra chất lượng thiết kế

Trước khi chốt thiết kế, có thể tự hỏi:

| Câu hỏi | Dấu hiệu tốt |
|---|---|
| A có thực sự là B không? | Nếu dùng `extends`, mọi nơi chấp nhận B đều có thể dùng A đúng contract |
| Lớp có quá nhiều nhiệm vụ không? | Logic nghiệp vụ, truy cập dữ liệu, gửi thông báo có ranh giới rõ |
| Có thể thay implementation không? | Caller dùng interface hoặc contract thích hợp |
| Có thể kiểm thử độc lập không? | Dễ truyền fake/stub vào constructor |
| Trạng thái có bị chia sẻ ngoài ý muốn không? | Quyền sở hữu và mutation của collaborator rõ ràng |
| Wrapper có giữ contract không? | Exception, retry, thứ tự side effect và kết quả được xác định |
| Có quá nhiều abstraction không? | Mỗi interface/lớp có mục đích, ranh giới thay đổi cụ thể |
| API công khai có ổn định không? | Refactor không vô tình thay đổi những quan hệ subtype được caller sử dụng |

Một chỉ báo thực tế của composition tốt là khi thay một dependency từ A sang B, lớp sử dụng dependency không cần thay đổi mã nguồn, còn các bài kiểm tra contract vẫn qua.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Composition chỉ có nghĩa tạo field bằng `new` | Collaborator cũng có thể được truyền từ bên ngoài bằng constructor |
| Delegation là từ khóa hoặc cơ chế tự động của Java | Đây là kỹ thuật gọi đối tượng khác và thường cần viết forwarding tường minh |
| Composition có nghĩa là không được dùng interface | Một class có thể implements interface và compose implementation khác |
| Dùng composition luôn giảm coupling | Coupling còn phụ thuộc kiểu contract, cách tạo dependency và API được công bố |
| Mọi `extends` đều là thiết kế xấu | Kế thừa phù hợp khi subtype thật sự giữ hợp đồng và lớp cha được thiết kế để mở rộng |
| Class `final` và field `final` khiến toàn bộ object bất biến | `final` chỉ có tác dụng phù hợp với class/field; mutable collaborator vẫn có thể đổi trạng thái |
| Record có bất biến sâu | Record chỉ cố định các component; object tham chiếu bên trong có thể mutable |
| `sealed` thay thế cho composition | `sealed` giới hạn subtype; composition vẫn là cách kết hợp trách nhiệm |
| Decorator chỉ thêm mã, không thay đổi ngữ nghĩa | Thứ tự wrapper, exception và side effect có thể làm khác hành vi |
| Thay `extends` bằng một field sẽ luôn tương thích API | Caller phụ thuộc subtype hoặc thành viên kế thừa có thể bị ảnh hưởng |

## 13. Câu hỏi tự kiểm tra

1. Vì sao `OrderService extends EmailSender` là quan hệ subtype đáng nghi ngờ?
2. Composition khác delegation ở điểm nào? Một class có thể dùng cả hai không?
3. Tại sao `MessageSender` nên là interface trong ví dụ `WelcomeService`?
4. Khi `AuditedSender` gọi `delegate.send`, đây có phải là lời gọi `super.send` không?
5. Điều gì xảy ra nếu `delegate.send` ném exception trước khi đến bước audit?
6. Việc khai báo một field `final` có làm collaborator an toàn luồng không?
7. Khi nào một sealed interface hợp lý hơn một interface mở rộng tự do?
8. Vì sao một record có component kiểu `List` vẫn có thể chứa các phần tử mutable?
9. Cần kiểm tra gì trước khi chuyển một public subclass đang dùng trong dự án sang composition?
10. Một thiết kế có 12 tầng decorator có nhất thiết tốt hơn một class đơn giản không? Vì sao?

## 14. Nguồn tham khảo chính thức

- [Java Language Specification, Java SE 27 — Chapter 8: Classes](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html): lớp, kế thừa, `final`, `sealed`, override và record.
- [JLS §8.1.4 — Superclasses and Subclasses](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.1.4): quan hệ lớp cha/lớp con.
- [JLS §8.4.8 — Inheritance, Overriding, and Hiding](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.4.8): ngữ nghĩa kế thừa và override.
- [JLS §8.10 — Record Classes](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.10): record là dạng lớp dữ liệu và ngầm định `final`.
- [Java Language Specification, Java SE 27 — Chapter 9: Interfaces](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html): quan hệ supertype theo interface và triển khai interface.
- [Java SE 27 API — Objects](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Objects.html): kiểm tra tham chiếu đầu vào với `requireNonNull`.
- [Java SE 27 API — List](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html): `List.copyOf` và đặc tính của unmodifiable list.
