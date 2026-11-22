# ObjectProvider để lấy bean khi cần hoặc chọn nhiều ứng viên

Trong Spring, constructor injection là cách phù hợp để khai báo những dependency mà một bean cần có ngay khi được tạo. Tuy nhiên, có những trường hợp ứng dụng chỉ cần một bean **khi thực sự thực hiện một thao tác**, bean đó có thể không tồn tại ở một số cấu hình, hoặc có nhiều implementation cùng đáp ứng một interface và cần chọn ở thời điểm chạy.

`ObjectProvider<T>` giải quyết những trường hợp này bằng cách cung cấp một đối tượng tra cứu bean từ Spring container. Ta có thể nhận provider trong constructor, rồi gọi nó khi cần lấy bean, kiểm tra bean có sẵn hay duyệt qua nhiều ứng viên. Provider giúp trì hoãn việc phân giải dependency; nó **không tự tạo ra bean**, không thay thế container và cũng không mặc định tạo một instance mới mỗi lần gọi.

## 1. ObjectProvider là gì?

`ObjectProvider<T>` thuộc Spring Framework, trong package:

~~~java
import org.springframework.beans.factory.ObjectProvider;
~~~

Nó mở rộng `ObjectFactory<T>` và bổ sung các thao tác hữu ích cho việc tra cứu dependency trong một `BeanFactory`:

- Lấy một bean khi cần bằng `getObject()`.
- Lấy bean nếu có, hoặc nhận `null` khi không có bằng `getIfAvailable()`.
- Lấy bean khi có một ứng viên phù hợp duy nhất bằng `getIfUnique()`.
- Thực hiện hành động nếu bean có sẵn hoặc nếu có ứng viên duy nhất.
- Duyệt các bean cùng kiểu bằng `stream()` và `orderedStream()`.

Có thể hình dung:

~~~text
Spring tạo ReportService
        |
        | constructor injection
        v
ObjectProvider<ReportExporter>
        |
        | chưa cần lấy exporter tại thời điểm này
        |
        +---- khi người dùng yêu cầu export
                    |
                    v
              provider.getObject()
                    |
                    v
              Spring BeanFactory
                    |
             tìm ứng viên phù hợp
                    |
             trả bean hoặc báo lỗi
~~~

Điểm quan trọng là constructor nhận được **provider** ngay khi tạo bean. Việc tìm và lấy `ReportExporter` được thực hiện khi code gọi một phương thức trên provider. Vì vậy, một dependency tùy chọn có thể chưa được yêu cầu trong suốt vòng đời của bean sử dụng nó.

`ObjectProvider` không chỉ dành cho Spring Boot. Đây là API của Spring Framework, nên có thể dùng trong ứng dụng Spring thông thường và trong ứng dụng Spring Boot.

## 2. Vì sao không inject trực tiếp dependency?

Giả sử ứng dụng có một tính năng gửi báo cáo qua email. Một số môi trường có cấu hình mail, một số môi trường chỉ tạo báo cáo để tải xuống.

Nếu inject trực tiếp:

~~~java
@Service
public class ReportService {
    private final EmailSender emailSender;

    public ReportService(EmailSender emailSender) {
        this.emailSender = emailSender;
    }
}
~~~

Spring phải phân giải `EmailSender` khi tạo `ReportService`. Nếu không có bean phù hợp, context có thể không khởi động được. Điều này không phù hợp khi email là tính năng tùy chọn.

Có thể dùng `ObjectProvider`:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ObjectProvider<EmailSender> emailSenders;

    public ReportService(ObjectProvider<EmailSender> emailSenders) {
        this.emailSenders = emailSenders;
    }

    public void sendByEmail(String address, byte[] report) {
        EmailSender sender = emailSenders.getIfAvailable();
        if (sender == null) {
            throw new IllegalStateException(
                    "Email delivery is not configured");
        }
        sender.send(address, report);
    }
}
~~~

Khi tạo `ReportService`, Spring có thể cung cấp provider dù hiện tại không có bean `EmailSender`. Chỉ khi gọi `sendByEmail`, code mới yêu cầu provider tìm bean. Nếu không có, `getIfAvailable()` trả về `null` và ứng dụng xử lý theo chính sách của mình.

Ví dụ này giả định `EmailSender` là một kiểu bean trong ứng dụng. Trong dự án thật, ta có thể dùng interface như `ReportDeliveryChannel` để service phụ thuộc vào hợp đồng, không phụ thuộc implementation cụ thể.

## 3. Các phương thức tra cứu quan trọng

### 3.1. `getObject()` — yêu cầu một bean

~~~java
ReportExporter exporter = exporters.getObject();
~~~

`getObject()` yêu cầu Spring phân giải một bean phù hợp với kiểu `T` và các qualifier trên injection point. Hành vi lỗi thường gặp:

- Không tìm thấy bean phù hợp: ném `NoSuchBeanDefinitionException`.
- Có nhiều ứng viên nhưng không thể chọn duy nhất: ném `NoUniqueBeanDefinitionException`.
- Có một ứng viên duy nhất, hoặc có ứng viên được ưu tiên theo quy tắc dependency resolution: trả về bean đó.

Đây là lựa chọn phù hợp khi thao tác hiện tại **bắt buộc phải có dependency**. Việc inject provider không có nghĩa dependency bên trong cũng luôn tùy chọn; lời gọi `getObject()` vẫn có thể thất bại nếu cấu hình thiếu hoặc mơ hồ.

`ObjectProvider` cũng có overload `getObject(Object... args)` để truyền đối số tường minh khi tạo bean qua factory method hỗ trợ arguments, thường hữu ích với bean prototype. Chỉ sử dụng khi bean được định nghĩa theo cách chấp nhận các đối số đó; không thể truyền tùy ý tham số cho mọi bean.

### 3.2. `getIfAvailable()` — bean có thì lấy, không có thì trả null

~~~java
EmailSender sender = emailSenders.getIfAvailable();
if (sender != null) {
    sender.send(address, report);
}
~~~

Phương thức này biểu đạt dependency có thể không tồn tại. Nếu không có ứng viên phù hợp, kết quả là `null`. Nếu có nhiều ứng viên mà Spring không thể xác định một ứng viên phù hợp duy nhất, lời gọi vẫn có thể ném `NoUniqueBeanDefinitionException`.

Có thể cung cấp giá trị dự phòng:

~~~java
EmailSender sender = emailSenders.getIfAvailable(
        () -> EmailSender.disabled()
);
~~~

Supplier chỉ được dùng khi không có bean phù hợp. Ví dụ giả định `EmailSender.disabled()` là factory method do ứng dụng tự định nghĩa. Giá trị dự phòng này **không tự được đăng ký thành Spring bean**; nó chỉ là giá trị mà đoạn code nhận về.

### 3.3. `getIfUnique()` — chỉ lấy khi có ứng viên duy nhất

~~~java
PaymentGateway gateway = gateways.getIfUnique();
if (gateway == null) {
    // Không có ứng viên hoặc không xác định được một ứng viên duy nhất.
}
~~~

Phương thức này hữu ích khi ứng dụng chấp nhận không có lựa chọn mặc định. Nếu có một ứng viên được xác định là duy nhất theo quy tắc phân giải dependency của Spring, provider trả bean đó; nếu không có ứng viên hoặc nhiều ứng viên ngang nhau khiến việc lựa chọn không rõ ràng, kết quả là `null`.

Có thể truyền supplier mặc định:

~~~java
PaymentGateway gateway = gateways.getIfUnique(
        () -> PaymentGateway.manualReview()
);
~~~

Trong trường hợp có nhiều implementation và không có ứng viên duy nhất, supplier có thể cung cấp chính sách dự phòng. Ví dụ này giả định interface có factory method tĩnh tương ứng.

### 3.4. `ifAvailable(...)` và `ifUnique(...)` — thực hiện hành động có điều kiện

Thay vì lấy bean rồi tự kiểm tra null:

~~~java
EmailSender sender = emailSenders.getIfAvailable();
if (sender != null) {
    sender.send(address, report);
}
~~~

có thể viết:

~~~java
emailSenders.ifAvailable(
        sender -> sender.send(address, report)
);
~~~

Tương tự:

~~~java
gateways.ifUnique(
        gateway -> gateway.authorize(payment)
);
~~~

Consumer chỉ được gọi khi provider tìm được bean đáp ứng điều kiện tương ứng. Các phương thức này giúp thể hiện rõ hành vi tùy chọn, đặc biệt với callback ngắn.

Lưu ý: nếu có nhiều ứng viên không thể phân giải duy nhất, `ifAvailable` không có nghĩa là “chọn đại một bean”; nó vẫn có thể báo lỗi không duy nhất. `ifUnique` phù hợp khi muốn bỏ qua hành động nếu không có một lựa chọn rõ ràng.

## 4. So sánh getObject, getIfAvailable và getIfUnique

| Phương thức | Không có bean | Có một bean phù hợp | Có nhiều bean không phân giải được |
|---|---|---|---|
| `getObject()` | Ném lỗi không tìm thấy | Trả bean | Ném lỗi không duy nhất |
| `getIfAvailable()` | Trả `null` | Trả bean | Có thể ném lỗi không duy nhất |
| `getIfUnique()` | Trả `null` | Trả bean | Trả `null` nếu không có ứng viên duy nhất |

Trong cả ba trường hợp, quy tắc lựa chọn bean của Spring vẫn áp dụng, bao gồm qualifier và ứng viên ưu tiên phù hợp. Do đó, “nhiều bean cùng kiểu” không nhất thiết luôn là tình huống không phân giải được: `@Primary` hoặc qualifier có thể giúp xác định ứng viên.

Chọn phương thức dựa trên chính sách nghiệp vụ:

- Bắt buộc có bean: `getObject()`.
- Không có bean thì bỏ qua hoặc xử lý tùy chọn: `getIfAvailable()`.
- Chỉ thực hiện khi lựa chọn rõ ràng và duy nhất: `getIfUnique()`.

## 5. Lấy nhiều ứng viên bằng stream và orderedStream

Khi có nhiều implementation cùng kiểu và ứng dụng cần xem tất cả, không nên gọi `getObject()` để mong Spring tự chọn một bean bất kỳ. `ObjectProvider` cung cấp hai cách duyệt:

- `stream()`: stream tất cả bean instance phù hợp với kiểu và qualifier của provider.
- `orderedStream()`: stream các bean phù hợp theo thứ tự áp dụng quy tắc `Ordered` của Spring.

Ví dụ:

~~~java
import java.util.List;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class ExportCoordinator {
    private final ObjectProvider<ReportExporter> exporters;

    public ExportCoordinator(ObjectProvider<ReportExporter> exporters) {
        this.exporters = exporters;
    }

    public List<String> supportedFormats() {
        return exporters.orderedStream()
                .map(ReportExporter::format)
                .toList();
    }
}
~~~

Giả sử có các implementation:

~~~java
public interface ReportExporter {
    String format();
    byte[] export(Report report);
}
~~~

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
class PdfReportExporter implements ReportExporter {
    public String format() {
        return "pdf";
    }

    public byte[] export(Report report) {
        return new byte[0];
    }
}
~~~

~~~java
@Component
@Order(20)
class CsvReportExporter implements ReportExporter {
    public String format() {
        return "csv";
    }

    public byte[] export(Report report) {
        return new byte[0];
    }
}
~~~

`orderedStream()` sắp xếp theo quy tắc thứ tự của Spring, có thể đến từ `Ordered`, `@Order` hoặc metadata thứ tự phù hợp. Trong ví dụ, PDF đứng trước CSV. Nếu dùng `stream()`, không nên dựa vào thứ tự duyệt để thể hiện ưu tiên nghiệp vụ.

### 5.1. Chọn implementation theo đầu vào nghiệp vụ

Provider có thể cung cấp tập ứng viên, sau đó service chọn theo dữ liệu request:

~~~java
@Service
public class ExportCoordinator {
    private final ObjectProvider<ReportExporter> exporters;

    public ExportCoordinator(ObjectProvider<ReportExporter> exporters) {
        this.exporters = exporters;
    }

    public byte[] export(Report report, String requestedFormat) {
        ReportExporter exporter = exporters.orderedStream()
                .filter(candidate ->
                        candidate.format().equalsIgnoreCase(requestedFormat))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unsupported format: " + requestedFormat));

        return exporter.export(report);
    }
}
~~~

Trong ví dụ này, service duyệt các exporter và chọn implementation phù hợp với định dạng người dùng yêu cầu. Nếu nhiều exporter cùng khai báo một format, thứ tự của Spring quyết định ứng viên đầu tiên; nếu điều đó không phải chính sách mong muốn, nên kiểm tra trường hợp trùng format và báo lỗi cấu hình thay vì âm thầm chọn một implementation.

`stream()` và `orderedStream()` có thể tạo bean instance khi stream được duyệt, tùy scope và trạng thái bean. Chúng không phải truy vấn metadata thuần túy.

## 6. Kết hợp ObjectProvider với @Qualifier

Giả sử có hai bean cùng triển khai `PaymentGateway`:

~~~java
public interface PaymentGateway {
    String providerName();
    void charge(long amount);
}
~~~

~~~java
@Component("cardGateway")
class CardPaymentGateway implements PaymentGateway {
    public String providerName() {
        return "card";
    }

    public void charge(long amount) {
        // Gọi cổng thanh toán thẻ.
    }
}
~~~

~~~java
@Component("bankGateway")
class BankPaymentGateway implements PaymentGateway {
    public String providerName() {
        return "bank";
    }

    public void charge(long amount) {
        // Gọi cổng thanh toán ngân hàng.
    }
}
~~~

Nếu một service chỉ được phép dùng cổng thẻ, có thể giới hạn provider ngay tại injection point:

~~~java
@Service
public class CardCheckoutService {
    private final ObjectProvider<PaymentGateway> cardGateways;

    public CardCheckoutService(
            @Qualifier("cardGateway")
            ObjectProvider<PaymentGateway> cardGateways) {
        this.cardGateways = cardGateways;
    }

    public void checkout(long amount) {
        cardGateways.getObject().charge(amount);
    }
}
~~~

`@Qualifier("cardGateway")` áp dụng cho việc phân giải dependency của provider, nên các lần tra cứu qua provider tuân theo qualifier đó. Nếu bean không tồn tại, `getObject()` vẫn báo lỗi; nếu mục đích là tùy chọn, cân nhắc `getIfAvailable()`.

Qualifier cũng có thể là annotation tùy chỉnh thay vì chuỗi tên bean. Cách này hữu ích khi muốn phân loại bean theo vai trò như “primary region”, “external provider” hoặc “read-only repository”, trong khi tên bean chỉ là định danh kỹ thuật.

## 7. ObjectProvider và @Primary khi có nhiều bean

`@Primary` đánh dấu một bean là ứng viên ưu tiên khi Spring cần chọn một dependency theo kiểu mà có nhiều ứng viên phù hợp:

~~~java
@Primary
@Component("defaultGateway")
class DefaultPaymentGateway implements PaymentGateway {
    // ...
}
~~~

Nếu provider không gắn qualifier cụ thể, `getObject()` hoặc `getIfAvailable()` có thể phân giải đến ứng viên primary theo quy tắc dependency resolution. `getIfUnique()` cũng có thể trả ứng viên được xem là duy nhất theo quy tắc đó.

Tuy nhiên, `@Primary` **không loại bỏ các bean còn lại khỏi container**. Khi gọi `stream()` hoặc `orderedStream()`, provider vẫn có thể trả toàn bộ ứng viên phù hợp, bao gồm cả bean không primary. Primary giúp chọn một dependency đơn, không phải bộ lọc cho danh sách.

Nếu ứng dụng có nhiều implementation và quyết định phải phụ thuộc vào request, tenant, loại tài liệu hoặc trạng thái nghiệp vụ, dùng `stream()` để chọn theo quy tắc rõ ràng thường phù hợp hơn việc dựa vào một bean primary cố định.

## 8. ObjectProvider và phạm vi bean (scope)

`ObjectProvider` trì hoãn việc tra cứu, nhưng **scope của bean đích vẫn quyết định instance nhận được**.

### 8.1. Singleton

Singleton là scope mặc định. Nếu `ReportExporter` là singleton, nhiều lần gọi:

~~~java
ReportExporter first = exporters.getObject();
ReportExporter second = exporters.getObject();
~~~

thường trả về cùng một instance singleton (trong cùng bean factory/context).

### 8.2. Prototype

Nếu bean đích là prototype:

~~~java
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
class TemporaryReportBuilder {
    // Trạng thái chỉ dùng cho một lần dựng báo cáo.
}
~~~

Một bean singleton có thể inject `ObjectProvider<TemporaryReportBuilder>` rồi gọi `getObject()` mỗi lần cần một builder mới:

~~~java
@Service
class ReportJobService {
    private final ObjectProvider<TemporaryReportBuilder> builders;

    ReportJobService(
            ObjectProvider<TemporaryReportBuilder> builders) {
        this.builders = builders;
    }

    void createReport() {
        TemporaryReportBuilder builder = builders.getObject();
        // Dùng builder cho lần xử lý này.
    }
}
~~~

Mỗi lần tra cứu prototype thông thường sẽ tạo một instance mới. Đây là một ứng dụng quan trọng của provider: nếu inject trực tiếp prototype vào singleton, dependency được phân giải khi tạo singleton và singleton sẽ giữ instance đó; provider cho phép yêu cầu instance prototype ở từng lần gọi.

Spring không tự quản lý đầy đủ vòng đời hủy của prototype như singleton. Nếu prototype giữ tài nguyên cần đóng, code chịu trách nhiệm giải phóng tài nguyên theo thiết kế phù hợp.

### 8.3. Request/session scope và các scope khác

Với bean theo request hoặc session, provider có thể trì hoãn việc tra cứu đến khi thao tác xảy ra trong scope tương ứng. Nhưng scope đó phải đang hoạt động. Gọi provider từ background thread không có request context, chẳng hạn, có thể dẫn đến lỗi scope chưa được kích hoạt.

Provider không tự tạo request context và cũng không làm một bean request-scoped trở thành singleton. Cần hiểu scope của bean đích và nơi gọi provider.

## 9. Phân biệt ObjectProvider với Optional, ObjectFactory, @Lazy và collection injection

Các công cụ này giải quyết những nhu cầu gần nhau nhưng có thời điểm phân giải và mức linh hoạt khác nhau.

| Cơ chế | Ý nghĩa chính | Thời điểm lấy dependency |
|---|---|---|
| Inject trực tiếp `T` | Dependency bắt buộc | Khi tạo bean sử dụng |
| `Optional<T>` | Dependency có thể vắng mặt | Khi Spring phân giải injection point |
| `ObjectFactory<T>` | Factory/lookup đơn giản để lấy object | Khi gọi `getObject()` |
| `ObjectProvider<T>` | Lookup linh hoạt: bắt buộc, tùy chọn, duy nhất, nhiều ứng viên | Khi gọi phương thức provider |
| `@Lazy` trên dependency | Trì hoãn khởi tạo/tra cứu thông qua proxy | Khi proxy được sử dụng lần đầu |
| Inject `List<T>` hoặc `Map<String,T>` | Nhận tất cả ứng viên phù hợp | Khi tạo bean sử dụng |

### 9.1. Optional<T>

~~~java
public ReportService(Optional<EmailSender> emailSender) {
    this.emailSender = emailSender.orElse(null);
}
~~~

`Optional` biểu đạt rõ sự hiện diện/vắng mặt của dependency ngay lúc khởi tạo. Nó phù hợp nếu ứng dụng cần quyết định một lần khi tạo bean. Nhưng nó không cung cấp API tra cứu lại theo yêu cầu, duyệt nhiều ứng viên hay truyền factory arguments như `ObjectProvider`.

### 9.2. ObjectFactory<T>

~~~java
public ReportService(ObjectFactory<ReportExporter> exporters) {
    this.exporters = exporters;
}
~~~

`ObjectFactory<T>` là abstraction đơn giản hơn, chủ yếu cung cấp `getObject()`. Dùng nó khi chỉ cần trì hoãn lookup. Nếu cần `getIfAvailable`, `getIfUnique` hoặc stream các ứng viên, `ObjectProvider` phù hợp hơn.

### 9.3. @Lazy

~~~java
public ReportService(@Lazy ReportExporter exporter) {
    this.exporter = exporter;
}
~~~

`@Lazy` tại injection point thường khiến Spring cung cấp proxy để trì hoãn phân giải target cho đến khi proxy được dùng. Nó hữu ích khi muốn giữ API dependency trực tiếp, nhưng không cung cấp cùng bộ thao tác lựa chọn/tùy chọn/nhiều bean như provider. Việc dùng proxy cũng có hệ quả về identity, lỗi có thể xuất hiện muộn hơn và cách tương tác với scope.

### 9.4. Collection injection

~~~java
public ExportCoordinator(List<ReportExporter> exporters) {
    this.exporters = exporters;
}
~~~

Collection injection phù hợp khi bean cần **toàn bộ danh sách ứng viên ngay từ lúc được tạo**. Nếu chỉ cần lấy danh sách khi người dùng thực hiện một thao tác hoặc muốn tránh tạo/khởi tạo dependency cho đến lúc cần, provider stream có thể phù hợp hơn.

## 10. Ví dụ hoàn chỉnh: chọn plugin theo loại yêu cầu

Giả sử ứng dụng có nhiều bộ xử lý file:

~~~java
public interface DocumentProcessor {
    boolean supports(String extension);
    void process(byte[] content);
}
~~~

Các implementation được đăng ký:

~~~java
@Component
@Order(10)
class PdfProcessor implements DocumentProcessor {
    public boolean supports(String extension) {
        return "pdf".equalsIgnoreCase(extension);
    }

    public void process(byte[] content) {
        // Xử lý PDF.
    }
}
~~~

~~~java
@Component
@Order(20)
class CsvProcessor implements DocumentProcessor {
    public boolean supports(String extension) {
        return "csv".equalsIgnoreCase(extension);
    }

    public void process(byte[] content) {
        // Xử lý CSV.
    }
}
~~~

Service không cần biết trước tất cả implementation:

~~~java
@Service
public class DocumentProcessingService {
    private final ObjectProvider<DocumentProcessor> processors;

    public DocumentProcessingService(
            ObjectProvider<DocumentProcessor> processors) {
        this.processors = processors;
    }

    public void process(String extension, byte[] content) {
        DocumentProcessor processor = processors.orderedStream()
                .filter(candidate -> candidate.supports(extension))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(
                        "No processor for: " + extension));

        processor.process(content);
    }
}
~~~

Khi thêm một implementation mới được Spring phát hiện, service có thể sử dụng nó mà không cần thay đổi constructor hoặc danh sách phụ thuộc tĩnh. Đây là một cách xây dựng **plugin-style architecture** đơn giản bằng Spring beans.

Trong ứng dụng cần tính xác định cao, nên kiểm tra trường hợp không có processor và trường hợp nhiều processor cùng nhận một extension. Có thể yêu cầu chỉ đúng một processor hỗ trợ extension, hoặc định nghĩa thứ tự ưu tiên rõ ràng. Không nên để thứ tự đăng ký tình cờ quyết định nghiệp vụ.

## 11. Một số lưu ý khi dùng ObjectProvider

**Provider không làm dependency trở thành tùy chọn về mặt nghiệp vụ.** Nếu code gọi `getObject()` mà bean không có, lỗi vẫn xảy ra. Hãy quyết định rõ có fallback, bỏ qua hay báo lỗi cho người dùng.

**Provider không tự tạo instance mới.** Singleton vẫn là singleton; muốn instance mới cho mỗi lần gọi, bean đích cần scope phù hợp như prototype.

**Provider không biến thao tác blocking thành non-blocking.** Nếu bean đích gọi JDBC/JPA hoặc thực hiện I/O đồng bộ, gọi nó thông qua provider vẫn là thao tác blocking.

**Provider không bảo đảm chọn bean theo tên tùy ý.** Dùng qualifier, primary hoặc logic duyệt stream để thể hiện tiêu chí lựa chọn.

**Không nên lạm dụng service locator.** Nếu một class có hàng chục provider và tự tra cứu đủ loại bean, quan hệ dependency sẽ khó nhìn thấy và khó kiểm thử. Hãy dùng provider cho những dependency thực sự cần lookup trì hoãn, optional hoặc đa ứng viên; các dependency cốt lõi vẫn nên inject trực tiếp.

**Chú ý lỗi xuất hiện muộn.** Một dependency thiếu có thể không làm context khởi động thất bại nếu provider chưa được gọi. Cần kiểm thử đường code sử dụng provider, đặc biệt ở các profile hoặc cấu hình triển khai khác nhau.

**Chú ý scope và tài nguyên.** Prototype hoặc request-scoped bean có yêu cầu vòng đời riêng. Việc lấy được bean không đồng nghĩa mọi tài nguyên nó sở hữu đã được giải phóng tự động.

## 12. Cách kiểm tra và kiểm thử code sử dụng ObjectProvider

Khi kiểm thử service dùng provider, nên bao phủ chính sách tra cứu thay vì chỉ kiểm tra constructor tạo được.

Ví dụ dùng Spring context test có thể kiểm tra trường hợp provider không có bean tùy chọn:

~~~java
@Configuration
class OptionalSenderTestConfiguration {
    @Bean
    ReportService reportService(ObjectProvider<EmailSender> senders) {
        return new ReportService(senders);
    }
}
~~~

Nếu ứng dụng cần xác nhận nhiều implementation được phát hiện, có thể khởi tạo context với các bean thử nghiệm và kiểm tra `orderedStream()` trả về đúng các ứng viên. Khi test logic chọn plugin, nên kiểm tra cả:

- Có đúng một implementation hỗ trợ định dạng yêu cầu.
- Không có implementation nào hỗ trợ.
- Có nhiều implementation cùng hỗ trợ và chính sách xử lý trùng được áp dụng.
- Có qualifier hoặc primary khi cần chọn một bean đơn.
- Provider truy cập prototype tạo instance theo scope dự kiến.

Với unit test thuần, có thể mock `ObjectProvider<T>` để kiểm tra service gọi phương thức nào. Tuy nhiên, mock không chứng minh Spring container thật sự phân giải bean theo qualifier, primary và scope như mong đợi. Những quy tắc đó cần ít nhất một bài kiểm thử tích hợp với application context.

Khi chẩn đoán lỗi runtime, hãy phân biệt:

| Triệu chứng | Nguyên nhân cần xem |
|---|---|
| `NoSuchBeanDefinitionException` từ `getObject()` | Không có bean phù hợp, bean bị loại bởi profile/condition, hoặc package không được scan |
| `NoUniqueBeanDefinitionException` | Nhiều ứng viên mà qualifier/primary không giải quyết được |
| Provider trả `null` | Dùng `getIfAvailable`/`getIfUnique` và không có ứng viên phù hợp với điều kiện |
| Lấy prototype nhưng vẫn thấy trạng thái cũ | Bean thực tế có thể vẫn là singleton, hoặc code giữ lại instance đã lấy |
| Request-scoped bean báo scope chưa hoạt động | Tra cứu diễn ra ngoài request/session context hợp lệ |

## 13. Cách chọn API trong từng tình huống

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Bean bắt buộc có và cần ngay | Inject trực tiếp `T` |
| Bean có thể không tồn tại, chỉ cần quyết định khi khởi tạo | `Optional<T>` |
| Bean có thể không tồn tại, chỉ kiểm tra khi thực hiện thao tác | `ObjectProvider<T>.getIfAvailable()` |
| Bắt buộc lấy một bean tại thời điểm chạy | `ObjectProvider<T>.getObject()` |
| Chỉ tiếp tục nếu có một ứng viên rõ ràng | `ObjectProvider<T>.getIfUnique()` |
| Duyệt nhiều implementation | `stream()` hoặc `orderedStream()` |
| Chỉ cần trì hoãn một factory lookup đơn giản | `ObjectFactory<T>` |
| Muốn proxy lazy cho dependency đơn | `@Lazy` |
| Cần toàn bộ implementation ngay khi tạo bean | Inject `List<T>`/`Map<String,T>` |

Trong một ứng dụng Spring Boot, `ObjectProvider` đặc biệt hữu ích khi xây dựng module mở rộng, tích hợp tùy chọn theo profile, plugin theo chiến lược, hoặc làm việc với bean prototype từ một singleton. Hãy dùng đúng phương thức theo ý nghĩa nghiệp vụ: `getObject()` cho dependency bắt buộc, `getIfAvailable()` cho dependency tùy chọn, `getIfUnique()` cho lựa chọn không mơ hồ, và `orderedStream()` khi cần xem nhiều implementation theo thứ tự của Spring.

Khi đã hiểu provider chỉ là **cửa ngõ tra cứu bean có kiểm soát**, ta có thể tổ chức dependency linh hoạt mà vẫn giữ việc tạo object, scope, qualifier và vòng đời bean dưới sự quản lý của Spring container.
