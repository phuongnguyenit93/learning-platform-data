# Abstract class và interface trong thiết kế hợp đồng

## 1. Hợp đồng hướng đối tượng là gì?

Trong Java 27, **interface** và **abstract class** đều cho phép khai báo hành vi mà nhiều lớp cụ thể có thể cung cấp. Chúng giúp mã nguồn làm việc với một kiểu tổng quát, trong khi việc triển khai chi tiết được quyết định bởi lớp cụ thể. Tuy nhiên, hai cấu trúc giải quyết các nhu cầu thiết kế khác nhau.

Một **hợp đồng (contract)** của thành phần gồm ít nhất hai lớp ý nghĩa:

- **Hợp đồng kiểu:** tên phương thức, tham số, kiểu trả về, mức truy cập và những ngoại lệ được khai báo. Trình biên dịch Java có thể kiểm tra phần lớn cấu trúc này.
- **Hợp đồng hành vi:** đầu vào hợp lệ, kết quả mong đợi, bất biến phải được giữ, cách báo lỗi, tính nhất quán khi gọi lặp lại và yêu cầu an toàn đa luồng. Đây là các cam kết thiết kế cần tài liệu và kiểm thử; trình biên dịch không tự chứng minh chúng.

Ví dụ, phương thức **charge(Charge request)** có thể được khai báo ở một interface. Một lớp thực hiện qua API ngân hàng, một lớp giả lập phục vụ kiểm thử và một lớp mô phỏng nội bộ đều có thể triển khai cùng chữ ký. Để thật sự thay thế được nhau, chúng còn phải tuân thủ cùng chính sách về số tiền hợp lệ, giá trị trả về và trường hợp giao dịch thất bại.

~~~mermaid
flowchart TD
    A[CheckoutService] -->|depends on contract| B[PaymentGateway interface]
    B --> C[BankPaymentGateway]
    B --> D[SandboxPaymentGateway]
    B --> E[TestFakeGateway]
    F[AbstractGatewayBase] -->|implements| B
    C -->|may extend| F
~~~

**Interface** là lựa chọn phù hợp khi muốn định nghĩa năng lực mà nhiều lớp không cùng tổ tiên triển khai. **Abstract class** hữu ích khi các lớp liên quan cần chia sẻ trạng thái hoặc quy trình chung nhưng vẫn dành một số bước để lớp con tự hoàn thiện.

## 2. Interface định nghĩa năng lực của một kiểu

Một interface khai báo những phương thức mà đối tượng triển khai cam kết cung cấp. Lớp sử dụng từ khóa **implements** để hiện thực interface, và một lớp có thể triển khai nhiều interface.

Ví dụ một hợp đồng xử lý thanh toán nhỏ, chỉ dùng API đã được chuẩn hóa trong Java:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

record Charge(String orderId, BigDecimal amount) {
    Charge {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(amount, "amount");

        if (orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
        if (amount.signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
    }
}

record Receipt(String reference) {
    Receipt {
        Objects.requireNonNull(reference, "reference");
    }
}

@FunctionalInterface
interface PaymentGateway {
    Receipt charge(Charge request);
}

final class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }

    Receipt checkout(String orderId, BigDecimal amount) {
        return gateway.charge(new Charge(orderId, amount));
    }
}

public class CheckoutDemo {
    public static void main(String[] args) {
        PaymentGateway sandbox =
            request -> new Receipt("demo-" + request.orderId());

        CheckoutService checkout = new CheckoutService(sandbox);
        Receipt result = checkout.checkout(
            "ORDER-42", new BigDecimal("125.00")
        );

        System.out.println(result);
    }
}
~~~

Lưu ví dụ vào **CheckoutDemo.java**, sau đó chạy với JDK 27:

~~~bash
javac CheckoutDemo.java
java CheckoutDemo
~~~

Kết quả dự kiến:

~~~text
Receipt[reference=demo-ORDER-42]
~~~

**CheckoutService** chỉ biết kiểu **PaymentGateway**. Nó không cần biết phía sau là cổng thanh toán thật, sandbox hay một triển khai dùng trong kiểm thử. Khi thay triển khai, mã của CheckoutService không cần thay đổi miễn là hợp đồng được giữ.

Chú thích **@FunctionalInterface** xác nhận PaymentGateway có đúng một phương thức abstract cần hiện thực; vì vậy có thể dùng lambda trong ví dụ. Interface có nhiều phương thức abstract vẫn hoàn toàn hợp lệ, nhưng không phải functional interface.

## 3. Các quy tắc cốt lõi của interface

Một interface là kiểu tham chiếu; không thể tạo instance trực tiếp bằng **new PaymentGateway()**. Interface không có instance field và không khai báo constructor. Những lớp triển khai nó có thể có constructor và trạng thái instance của riêng mình.

Các quy tắc quan trọng:

- Phương thức thông thường không có thân trong interface là **public abstract** theo ngầm định. Lớp cụ thể triển khai phải khai báo phương thức tương ứng với mức truy cập **public**.
- Field được khai báo trong interface luôn là **public static final** theo ngầm định và phải có biểu thức khởi tạo. Chúng biểu diễn giá trị cấp kiểu, không phải trạng thái instance.
- Interface có thể khai báo **default**, **static** và **private** methods có thân; chúng là các khả năng hiện hành của Java.
- Một interface có thể **extends** nhiều interface khác. Một class có thể **implements** nhiều interface.
- Interface không thể được đánh dấu **final**; có thể dùng **sealed** để giới hạn tập kiểu được phép triển khai.
- Interface có thể là generic, ví dụ **Repository<T, ID>**, nhằm biểu đạt hợp đồng cho nhiều kiểu dữ liệu.

Ví dụ:

~~~java
interface Identified {
    String id();
}

interface Timestamped {
    java.time.Instant createdAt();
}

interface AuditedEntity extends Identified, Timestamped {
    String changedBy();
}

record AuditEntry(
    String id,
    java.time.Instant createdAt,
    String changedBy
) implements AuditedEntity {
}
~~~

Record **AuditEntry** triển khai ba phương thức theo hợp đồng nhờ các accessor tự sinh từ record components. Nhờ vậy, các đối tượng kiểu record vẫn có thể tham gia hệ thống đa hình thông qua interface.

Về mặt thiết kế, không nên đưa dữ liệu mutable dùng chung vào field của interface. Nếu cần trạng thái hoặc tài nguyên có vòng đời cụ thể, đặt chúng trong lớp triển khai, thành phần được inject hoặc một đối tượng cấu hình riêng.

## 4. Abstract class định nghĩa nền tảng chung

Một **abstract class** là lớp được khai báo bằng từ khóa **abstract**. Nó có thể chứa field instance, constructor, phương thức đã hiện thực và phương thức abstract không có thân. Không thể tạo instance trực tiếp từ abstract class, nhưng có thể tạo instance từ lớp con cụ thể.

Ví dụ xuất dữ liệu theo một quy trình thống nhất:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Objects;

abstract class ReportEncoder {
    private final Charset charset;

    protected ReportEncoder(Charset charset) {
        this.charset = Objects.requireNonNull(charset, "charset");
    }

    public final byte[] encode(List<String> rows) {
        List<String> snapshot =
            List.copyOf(Objects.requireNonNull(rows, "rows"));

        String rendered = Objects.requireNonNull(
            render(snapshot), "render must not return null"
        );

        return rendered.getBytes(charset);
    }

    protected abstract String render(List<String> rows);
}

final class PlainTextEncoder extends ReportEncoder {
    PlainTextEncoder() {
        super(StandardCharsets.UTF_8);
    }

    @Override
    protected String render(List<String> rows) {
        return String.join("\n", rows);
    }
}
~~~

Sử dụng:

~~~java
ReportEncoder encoder = new PlainTextEncoder();
byte[] document = encoder.encode(List.of("Header", "Row 1", "Row 2"));
~~~

Trong ví dụ này:

1. Constructor của ReportEncoder nhận và lưu **charset**; các lớp con dùng chung chính sách chuyển chuỗi thành byte.
2. **encode** đã có thân và được đánh dấu **final** để mọi lớp con thực hiện cùng các bước kiểm tra và mã hóa.
3. **render** là phương thức **protected abstract**; mỗi lớp con phải định nghĩa cách biến các hàng dữ liệu thành văn bản.
4. **PlainTextEncoder** kế thừa phần chung và chỉ hoàn thiện bước định dạng.

Đây là một dạng **Template Method**: lớp cha giữ khung quy trình, lớp con cung cấp một hoặc vài bước thay đổi. Nó hữu ích khi các triển khai thật sự chia sẻ quy trình và bất biến. Nếu các triển khai không có logic hay trạng thái chung, một interface đơn giản thường dễ bảo trì hơn.

## 5. Khả năng và giới hạn của abstract class

Abstract class có gần như toàn bộ khả năng của lớp thông thường:

| Khả năng | Abstract class |
|---|---|
| Instance field và static field | Có |
| Constructor | Có, được gọi khi khởi tạo lớp con |
| Phương thức đã có thân | Có |
| Phương thức abstract không có thân | Có |
| Phương thức private, protected, public | Có |
| Phương thức final | Có, nếu có thân |
| Triển khai interface | Có |
| Kế thừa từ một superclass | Có |
| Khởi tạo trực tiếp bằng new | Không |
| Vừa abstract vừa final ở cấp lớp | Không |

Phương thức được khai báo **abstract** không có thân. Nó không thể đồng thời là **private**, **static** hoặc **final** vì các đặc tính đó mâu thuẫn với việc lớp con phải có khả năng cung cấp hành vi.

Một abstract class không bắt buộc phải chứa phương thức abstract. Đôi khi tác giả muốn ngăn khởi tạo trực tiếp và chỉ cho các kiểu con sử dụng một khung chung; khi đó abstract class vẫn hợp lệ. Tuy nhiên, hãy chọn abstract class vì mô hình thiết kế thực sự cần kế thừa, không chỉ để tạo một lớp tiện ích.

Lớp con **concrete** phải hiện thực tất cả phương thức abstract còn chưa được hiện thực; nếu không, chính lớp con cũng phải được khai báo abstract.

~~~java
abstract class MessageSource {
    public abstract String read();

    public String readOrDefault(String fallback) {
        String result = read();
        return result == null ? fallback : result;
    }
}

abstract class BufferedMessageSource extends MessageSource {
    // Chưa bắt buộc triển khai read() vì lớp vẫn là abstract.
}

final class FixedMessageSource extends BufferedMessageSource {
    @Override
    public String read() {
        return "Hello";
    }
}
~~~

Lớp con chỉ được kế thừa trực tiếp từ một lớp cha, vì Java sử dụng **single inheritance** cho class. Nếu một lớp đã **extends AbstractRepository**, nó không thể đồng thời **extends AbstractCache**, nhưng vẫn có thể implements nhiều interface.

## 6. Khi nào dùng interface, khi nào dùng abstract class?

| Nhu cầu thiết kế | Interface | Abstract class |
|---|---|---|
| Định nghĩa năng lực chung cho các lớp không liên quan | Phù hợp | Thường không cần |
| Cho một lớp tham gia nhiều hợp đồng | Phù hợp | Một class chỉ có một superclass trực tiếp |
| Chia sẻ instance field hoặc constructor | Không | Phù hợp |
| Chia sẻ quy trình gồm nhiều bước cố định | Có thể dùng default method đơn giản | Phù hợp khi cần Template Method và trạng thái |
| Làm ranh giới giữa nghiệp vụ và hạ tầng | Thường ưu tiên | Dùng khi các triển khai có nền tảng chung |
| Bảo vệ bất biến bằng phương thức final | Không dùng final trên default method | Có |
| Tạo một hệ phân cấp đóng | Có thể dùng sealed interface | Có thể dùng sealed abstract class |
| Dễ thay thế bằng lambda | Nếu là functional interface | Không |
| Biểu diễn quan hệ kiểu | “Có năng lực thực hiện” | “Là một biến thể của cùng lớp nền” |

Ví dụ, **PaymentGateway**, **NotificationSender** hoặc **ClockProvider** thường là interface vì các triển khai có thể sử dụng công nghệ rất khác nhau. Ngược lại, các bộ mã hóa chia sẻ cùng trạng thái, quy trình kiểm tra và bước khởi tạo có thể cần abstract class.

Một lớp hoàn toàn có thể vừa **extends** một abstract class vừa **implements** nhiều interface:

~~~java
interface ByteTransformer {
    byte[] transform(byte[] data);
}

interface Auditable {
    String auditDescription();
}

abstract class BaseProcessor {
    protected final String name;

    protected BaseProcessor(String name) {
        this.name = java.util.Objects.requireNonNull(name);
    }
}

final class CopyingProcessor extends BaseProcessor
        implements ByteTransformer, Auditable {

    CopyingProcessor() {
        super("copy");
    }

    @Override
    public byte[] transform(byte[] data) {
        java.util.Objects.requireNonNull(data, "data");
        return java.util.Arrays.copyOf(data, data.length);
    }

    @Override
    public String auditDescription() {
        return "Processor: " + name;
    }
}
~~~

Ví dụ này kết hợp một superclass cung cấp tên bộ xử lý với hai hợp đồng độc lập. **CopyingProcessor** tạo bản sao byte array, tránh để caller vô tình dùng chung dữ liệu mutable; **auditDescription** cung cấp mô tả phục vụ ghi nhận.

## 7. Default, static và private methods trong interface

Interface không chỉ chứa phương thức abstract. Java hiện cho phép đặt một số hành vi dùng chung ngay trong interface khi chúng không đòi hỏi instance field riêng của interface.

~~~java
import java.util.Locale;
import java.util.Objects;

interface TextFormatter {
    String format(String input);

    default String formatTrimmed(String input) {
        return format(trimInput(input));
    }

    private static String trimInput(String input) {
        return Objects.requireNonNull(input, "input").strip();
    }

    static TextFormatter upperCase() {
        return value ->
            Objects.requireNonNull(value).toUpperCase(Locale.ROOT);
    }
}
~~~

Sử dụng:

~~~java
TextFormatter formatter = TextFormatter.upperCase();
System.out.println(formatter.formatTrimmed("  hello java  "));
// HELLO JAVA
~~~

Các vai trò khác nhau:

- **Abstract method format:** phương thức bắt buộc lớp triển khai cung cấp.
- **Default method formatTrimmed:** hành vi chung mà lớp triển khai nhận được theo mặc định; lớp triển khai có thể override.
- **Private static method trimInput:** tiện ích nội bộ của interface để tránh lặp logic; không thuộc API công khai.
- **Static method upperCase:** factory method thuộc về chính interface; gọi qua tên **TextFormatter.upperCase()**.

Không thể khai báo default method để override các phương thức public của **Object**, chẳng hạn **equals**, **hashCode** hoặc **toString**. Nếu cần chính sách so sánh, lớp hoặc record cụ thể phải tự hiện thực theo hợp đồng thích hợp.

Default method là công cụ hỗ trợ hành vi chung hoặc mở rộng API có kiểm soát. Nó không thay thế abstract class trong các trường hợp cần trạng thái instance, constructor hoặc bảo vệ một thuật toán bằng phương thức final.

## 8. Đa hình và lập trình hướng đến hợp đồng

**Đa hình (polymorphism)** cho phép một biến có kiểu interface hoặc superclass trỏ đến đối tượng của lớp triển khai, rồi gọi hành vi thông qua hợp đồng chung.

~~~java
interface Notifier {
    void send(String destination, String message);
}

final class ConsoleNotifier implements Notifier {
    @Override
    public void send(String destination, String message) {
        System.out.println(destination + ": " + message);
    }
}

final class NotificationService {
    private final Notifier notifier;

    NotificationService(Notifier notifier) {
        this.notifier = java.util.Objects.requireNonNull(notifier);
    }

    void notifyCustomer(String customerId, String message) {
        notifier.send(customerId, message);
    }
}
~~~

~~~java
Notifier notifier = new ConsoleNotifier();
NotificationService service = new NotificationService(notifier);
service.notifyCustomer("customer-1", "Đơn hàng đã được xác nhận");
~~~

**NotificationService** chỉ phụ thuộc vào Notifier, không phụ thuộc vào lớp ConsoleNotifier. Với hợp đồng giữ nguyên, có thể thay bằng triển khai gửi email, message broker hoặc fake phục vụ kiểm thử.

Các lợi ích thực tế:

- Giảm sự phụ thuộc giữa tầng nghiệp vụ và công nghệ triển khai.
- Giữ API nhỏ, rõ ràng và dễ xem xét.
- Cho phép thay công nghệ hoặc triển khai mà không phải sửa phần gọi.
- Giúp thử nghiệm logic với fake/stub mà không cần kết nối hệ thống ngoài.

Tuy nhiên, không nên tạo interface cho mọi class một cách máy móc. Một lớp chỉ có một triển khai nội bộ và không có nhu cầu thay thế hoặc tách ranh giới có thể không cần interface riêng.

## 9. Kế thừa hợp đồng từ nhiều interface và xử lý xung đột

Một class có thể implements nhiều interface. Khi hai interface khai báo các phương thức abstract tương thích, lớp triển khai có thể cung cấp một phương thức để đáp ứng cả hai. Nhưng nếu hai interface đưa ra **default method** cùng chữ ký mà không có cách phân giải ưu tiên, lớp triển khai phải override tường minh.

~~~java
interface EnglishLabel {
    default String label() {
        return "ready";
    }
}

interface VietnameseLabel {
    default String label() {
        return "sẵn sàng";
    }
}

final class BilingualLabel implements EnglishLabel, VietnameseLabel {
    @Override
    public String label() {
        return EnglishLabel.super.label()
            + " / " + VietnameseLabel.super.label();
    }
}
~~~

Từ khóa **InterfaceName.super.method()** trong lớp triển khai cho phép gọi hành vi default của superinterface trực tiếp tương ứng. Điều này khác với đa kế thừa lớp: Java chỉ cho một superclass nhưng cho nhiều superinterface.

Khi superclass cung cấp một phương thức instance cụ thể có thể kế thừa, phương thức từ class thường có ưu tiên so với default method của interface cùng chữ ký. Khi một interface con chuyên biệt override default method của interface cha, khai báo chuyên biệt hơn cũng có ưu tiên. Tuy vậy, nên thiết kế các hợp đồng để tránh va chạm tên phương thức có ý nghĩa khác nhau.

## 10. Thiết kế hợp đồng hành vi, không chỉ chữ ký

Trình biên dịch kiểm tra một class có hiện thực đúng chữ ký phương thức hay không. Nó không biết một phương thức có tuân thủ những điều ứng dụng thực sự mong đợi hay không.

Một hợp đồng chất lượng nên trả lời rõ các câu hỏi:

1. **Tiền điều kiện:** tham số có được null không, số tiền có phải dương không, khóa định danh có được để trống không?
2. **Hậu điều kiện:** giá trị trả về có bao giờ null không, kết quả có phản ánh trạng thái đã cập nhật không?
3. **Lỗi:** khi nào ném ngoại lệ, khi nào trả về đối tượng kết quả thất bại, khi nào có thể retry?
4. **Tác dụng phụ:** phương thức có ghi dữ liệu, gửi sự kiện hoặc gọi hệ thống khác không?
5. **Tính đồng thời:** triển khai có an toàn khi được gọi từ nhiều thread không?
6. **Vòng đời tài nguyên:** caller có phải đóng kết nối, stream hoặc handle được trả về không?

Ví dụ Javadoc cho một hợp đồng giả định:

~~~java
record ReservationResult(boolean reserved, String detail) {
}

public interface InventoryReservation {
    /**
     * Đặt giữ hàng cho một yêu cầu có mã định danh hợp lệ.
     *
     * @param sku mã sản phẩm khác null và không rỗng
     * @param quantity số lượng lớn hơn 0
     * @return kết quả giữ hàng, không trả về null
     * @throws IllegalArgumentException nếu đầu vào không hợp lệ
     */
    ReservationResult reserve(String sku, int quantity);
}
~~~

Tất cả triển khai của **InventoryReservation** cần giữ cùng các cam kết đã được công bố. Ví dụ, một triển khai bất ngờ trả **null** khi hết hàng trong khi các triển khai khác trả về **ReservationResult** biểu diễn trạng thái thất bại sẽ làm caller khó xử lý thống nhất.

Nguyên tắc thay thế kiểu con (*Liskov Substitution Principle*) có thể hiểu thực dụng: nếu một vị trí mong đợi **InventoryReservation**, việc thay triển khai không được phá hỏng các giả định hợp lệ của caller. Triển khai không nên tự ý đòi hỏi tiền điều kiện chặt hơn hoặc trả kết quả yếu hơn so với hợp đồng đã công bố.

## 11. Abstract class và bảo vệ bất biến

Abstract class đặc biệt có ích khi một họ triển khai cần tuân thủ một chuỗi bước cố định, chẳng hạn kiểm tra đầu vào, đo thời gian, lưu audit và giải phóng tài nguyên. Lớp cha có thể cho phép lớp con tùy biến một bước **protected abstract**, nhưng giữ phần còn lại không bị thay đổi bằng **final**.

~~~java
abstract class ValidatingProcessor {
    public final String execute(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("input is required");
        }

        String output = processValidated(input.strip());
        return java.util.Objects.requireNonNull(
            output, "processor must return a value"
        );
    }

    protected abstract String processValidated(String normalizedInput);
}

final class UppercaseProcessor extends ValidatingProcessor {
    @Override
    protected String processValidated(String normalizedInput) {
        return normalizedInput.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Với cấu trúc này, mọi phương thức **execute** đều kiểm tra đầu vào và hậu điều kiện; lớp con chỉ thay đổi nội dung xử lý. Cơ chế này vẫn không thể tự đảm bảo mọi hợp đồng nghiệp vụ: nếu lớp con thực hiện tác dụng phụ không mong muốn hoặc không thread-safe thì vẫn cần kiểm thử và review.

Không nên gọi phương thức có thể override từ constructor của abstract class. Phương thức của lớp con có thể chạy trước khi trạng thái lớp con hoàn tất khởi tạo, tạo ra hành vi khó dự đoán. Hãy khởi tạo bất biến trong constructor, sau đó gọi hành vi mở rộng khi object đã được xây dựng đầy đủ.

## 12. Sealed interface cho hợp đồng có tập biến thể đóng

Một interface thông thường cho phép nhiều class triển khai ở những vị trí khác nhau. Khi mô hình nghiệp vụ có số biến thể được kiểm soát và cần xử lý đầy đủ từng trường hợp, **sealed interface** là lựa chọn hiện hành, được chuẩn hóa từ Java 17.

~~~java
sealed interface OperationResult permits Completed, Rejected {
}

record Completed(String transactionId) implements OperationResult {
}

record Rejected(String reason) implements OperationResult {
}
~~~

Kết hợp record, sealed interface và pattern matching trong switch để xử lý kết quả:

~~~java
static String describe(OperationResult result) {
    return switch (result) {
        case Completed(String transactionId) ->
            "Completed: " + transactionId;
        case Rejected(String reason) ->
            "Rejected: " + reason;
    };
}
~~~

Đây là cú pháp Java 27 có sẵn mà không cần bật preview: record, sealed type, record pattern và pattern matching trong switch đều đã được chuẩn hóa. Nếu thêm một kiểu con được phép mới, trình biên dịch có thể yêu cầu cập nhật switch expression để giữ tính đầy đủ.

Các lớp triển khai trực tiếp sealed interface phải là **final**, **sealed** hoặc **non-sealed** theo quy tắc tương ứng; record vốn đã là final nên phù hợp làm biến thể kết quả. Ràng buộc vị trí khai báo còn phụ thuộc vào named module hay unnamed module. Đừng sealed một interface được thiết kế để bên thứ ba tự do tạo plugin hoặc adapter; điều đó sẽ ngăn họ triển khai hợp đồng mới.

Lưu ý: switch không có **case null** vẫn ném **NullPointerException** khi selector là null; tính đầy đủ của sealed type không có nghĩa rằng null được xử lý tự động.

## 13. Mở rộng API và tương thích qua các phiên bản

Khi một interface đã được nhiều dịch vụ hoặc thư viện sử dụng, thay đổi hợp đồng có thể khiến mã triển khai không còn biên dịch hoặc thay đổi hành vi runtime.

Một số trường hợp cần đánh giá kỹ:

| Thay đổi | Tác động cần xem xét |
|---|---|
| Thêm abstract method vào interface public | Các lớp triển khai có thể cần cập nhật; gọi phương thức mới trên triển khai cũ có thể gây lỗi liên kết hoặc thực thi |
| Thêm default method | Có thể hỗ trợ mở rộng API nhưng vẫn có nguy cơ xung đột tên hoặc hành vi không phù hợp |
| Đổi tham số hoặc kiểu trả về | Có thể ảnh hưởng source compatibility và binary compatibility |
| Đổi tiền điều kiện hoặc cách báo lỗi | Có thể làm hỏng hợp đồng hành vi dù chữ ký vẫn giữ nguyên |
| Đổi constructor hoặc protected member của abstract class | Có thể buộc lớp con cập nhật |
| Đánh dấu interface sealed | Giới hạn tập triển khai và có thể chặn các adapter hiện có |

Không nên coi default method là giải pháp tự động cho mọi thay đổi tương thích. Chỉ nên cung cấp hành vi mặc định khi nó có nghĩa đúng cho mọi triển khai hợp lệ. Nếu không có hành vi mặc định an toàn, cân nhắc khai báo interface mới, thêm adapter rõ ràng hoặc thực hiện quy trình migration với phiên bản API được quản lý.

Trên thư viện công khai, cần xem xét cả tương thích mã nguồn, tương thích nhị phân và tính tương thích về hành vi. Unit test, contract test và kiểm thử tích hợp có vai trò khác nhau; cùng biên dịch thành công chưa chứng minh rằng khách hàng sử dụng API vẫn hoạt động đúng.

## 14. Kiểm thử các triển khai theo một hợp đồng chung

Một lợi ích của việc phụ thuộc interface là có thể kiểm thử phần nghiệp vụ bằng fake đơn giản. Với **PaymentGateway** ở ví dụ đầu bài, ta có thể truyền lambda giả lập:

~~~java
PaymentGateway fake = request ->
    new Receipt("test-" + request.orderId());

CheckoutService service = new CheckoutService(fake);
Receipt receipt = service.checkout(
    "ORDER-1", new java.math.BigDecimal("10.00")
);

if (!"test-ORDER-1".equals(receipt.reference())) {
    throw new AssertionError("Unexpected receipt");
}
~~~

Đây là kiểm tra rất nhỏ, không phụ thuộc mạng. Với triển khai thật, cần bổ sung contract tests để xác minh chính sách xử lý null, lỗi, retry, idempotency (nếu đã cam kết), thời gian chờ và tài nguyên.

Có thể xây dựng một bộ contract test dùng chung cho nhiều triển khai:

- Mỗi triển khai đều từ chối đầu vào trái hợp đồng theo cùng cách đã công bố.
- Mỗi triển khai đều trả về giá trị theo hậu điều kiện.
- Mỗi triển khai đều bảo toàn các bất biến nghiệp vụ.
- Khi hợp đồng tuyên bố thread-safe, kiểm thử cả việc gọi đồng thời.
- Nếu hợp đồng cho phép thay thế triển khai, hành vi ở ranh giới mà caller quan sát được phải nhất quán.

Việc kiểm thử hành vi đặc biệt quan trọng khi dùng abstract class vì lớp con có thể thêm trạng thái riêng, thay đổi thuật toán hoặc làm xuất hiện tác dụng phụ mà chữ ký phương thức không thể diễn đạt.

## 15. Các lỗi thiết kế thường gặp

| Vấn đề | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Class implements interface nhưng báo access yếu hơn | Phương thức interface là public, lớp triển khai để package-private hoặc protected | Khai báo phương thức triển khai **public** |
| Không thể tạo object từ abstract class | Abstract class không thể được khởi tạo trực tiếp | Tạo lớp con concrete rồi khởi tạo lớp con |
| Lớp concrete chưa triển khai hết phương thức | Còn abstract methods chưa được hiện thực | Override đủ hoặc đánh dấu lớp con abstract |
| Một class muốn extends hai class | Java chỉ cho một superclass trực tiếp | Dùng composition hoặc thêm interface cho các năng lực |
| Hai default methods bị xung đột | Nhiều interface có cùng chữ ký default | Override trong lớp và chọn hành vi rõ ràng |
| Code phụ thuộc chặt vào triển khai | Service tạo trực tiếp adapter hạ tầng bên trong | Inject hợp đồng qua constructor khi có ranh giới thay thế |
| Abstract base class ngày càng phình to | Nhét nhiều trách nhiệm không liên quan vào lớp cha | Tách interface nhỏ và dùng composition |
| Default method có tác dụng phụ ngoài dự kiến | Hành vi mặc định không phù hợp cho mọi triển khai | Xóa mặc định không an toàn hoặc thay bằng hợp đồng rõ ràng |
| Lớp con phá bất biến của lớp cha | Hook có quyền thay đổi quá nhiều trạng thái | Thu hẹp điểm mở rộng, dùng private/final và contract tests |
| Chỉ kiểm tra chữ ký mà bỏ qua hành vi | Thiếu tài liệu, tiền điều kiện và hậu điều kiện | Viết Javadoc, contract tests và trường hợp lỗi |

## 16. Bài tập thực hành

**Bài tập 1 — Thiết kế interface nhỏ.** Xây dựng **NotificationSender** với phương thức **send(Notification)** và hai lớp triển khai: một lớp in nội dung ra console, một lớp lưu thông báo vào collection trong bộ nhớ. Viết **NotificationService** chỉ phụ thuộc NotificationSender và thay hai lớp triển khai mà không sửa code nghiệp vụ.

**Bài tập 2 — Dùng abstract class có kiểm soát.** Xây dựng abstract class **FileReportWriter** có constructor nhận charset, phương thức final **write(...)** thực hiện xác thực và phương thức protected abstract **render(...)** tạo nội dung. Viết hai lớp con định dạng văn bản khác nhau. Kiểm tra rằng cả hai triển khai đều tôn trọng tiền điều kiện và cách báo lỗi chung.

**Bài tập 3 — Hợp đồng đóng.** Tạo sealed interface **ValidationResult** với record **Valid** và **Invalid**. Viết switch expression xử lý đầy đủ cả hai dạng kết quả. Sau đó bổ sung một biến thể thứ ba và quan sát yêu cầu cập nhật nhánh xử lý khi biên dịch lại.

## 17. Checklist trước khi công bố một hợp đồng Java

- [ ] Hợp đồng đã mô tả đúng một năng lực hoặc tập hành vi liên quan.
- [ ] Chọn interface nếu chỉ cần khai báo năng lực; chọn abstract class nếu thật sự có trạng thái hoặc khung xử lý chung.
- [ ] Các phương thức public có tên, tham số, kiểu trả về và ngoại lệ rõ ràng.
- [ ] Tiền điều kiện, hậu điều kiện, chính sách null và lỗi được tài liệu hóa.
- [ ] Mọi triển khai đều có thể thay thế nhau theo hành vi đã công bố.
- [ ] Default method chỉ được dùng khi hành vi mặc định hợp lệ cho mọi triển khai.
- [ ] Abstract class không gọi phương thức có thể override trong constructor.
- [ ] Chỉ sealed những hệ phân cấp chủ động giới hạn tập triển khai.
- [ ] Contract tests kiểm tra các cam kết quan trọng cho từng implementation.
- [ ] Thay đổi API được đánh giá về source, binary và behavioral compatibility.
- [ ] Các lớp nghiệp vụ phụ thuộc vào hợp đồng phù hợp, còn việc chọn triển khai nằm ở điểm cấu hình/khởi tạo.

Thiết kế tốt sử dụng **interface** để mô tả những gì một thành phần cam kết làm và **abstract class** để tái sử dụng trạng thái, quy trình chung khi các thành phần có cùng nền tảng. Dù chọn cấu trúc nào, giá trị lớn nhất nằm ở hợp đồng hành vi rõ ràng, khả năng thay thế triển khai và các kiểm thử chứng minh hợp đồng đó được tuân thủ.

## Tài liệu tham khảo

- [Java Language Specification 27, Chapter 8 — Classes](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html): abstract class, method overriding, constructor và kế thừa lớp.
- [Java Language Specification 27, Chapter 9 — Interfaces](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html): khai báo interface, default/static/private methods, functional interface và sealed interface.
