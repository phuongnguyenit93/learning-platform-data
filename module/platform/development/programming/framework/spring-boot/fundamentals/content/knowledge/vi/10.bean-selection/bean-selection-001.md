# Chọn ứng viên theo type và xử lý khi có nhiều bean phù hợp

Trong Spring, bạn thường khai báo dependency bằng kiểu Java rồi để container inject implementation phù hợp:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway paymentGateway;

    public CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
~~~

Điều này hoạt động đơn giản khi trong ApplicationContext chỉ có một bean phù hợp với kiểu **PaymentGateway**. Nhưng một ứng dụng thực tế có thể tích hợp nhiều cổng thanh toán: thanh toán nội địa, thẻ quốc tế, ví điện tử hoặc implementation giả dùng trong kiểm thử. Khi có nhiều bean cùng đáp ứng một kiểu dependency, Spring cần xác định bean nào được inject.

Chủ đề này giải thích cách Spring **tìm ứng viên theo type**, cách thu hẹp và chọn ứng viên bằng **@Qualifier** và **@Primary**, cách inject nhiều implementation cùng lúc, và cách xử lý lỗi khi không có hoặc có quá nhiều bean phù hợp.

## 1. Spring tìm bean theo type như thế nào?

Giả sử có một interface:

~~~java
public interface PaymentGateway {
    PaymentResult charge(PaymentCommand command);
}
~~~

Và một implementation:

~~~java
@Component
public class BankTransferGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(PaymentCommand command) {
        // Gọi dịch vụ chuyển khoản ngân hàng.
        return PaymentResult.accepted();
    }
}
~~~

Khi constructor yêu cầu **PaymentGateway**, Spring tìm bean có type tương thích với kiểu đó. Bean **BankTransferGateway** có thể được dùng vì nó implements interface **PaymentGateway**.

~~~text
Injection point:
PaymentGateway
       │
       ▼
Spring tìm bean có type tương thích
       │
       ▼
BankTransferGateway implements PaymentGateway
       │
       ▼
Inject bean vào constructor
~~~

Đây là **type-based dependency injection**. Code của service phụ thuộc vào abstraction, còn container quyết định implementation cụ thể dựa trên những bean đã được đăng ký và các metadata đi kèm.

### Bean phải có mặt trong ApplicationContext

Một class implements interface không tự động trở thành bean chỉ vì quan hệ kiểu Java tồn tại. Nó cần được đăng ký thông qua một cơ chế phù hợp, ví dụ:

- Component scanning với **@Component**, **@Service**, **@Repository** hoặc stereotype tương ứng.
- Factory method **@Bean** trong một class **@Configuration**.
- Auto-configuration hoặc một cơ chế đăng ký bean khác.

Nếu implementation chưa nằm trên runtime classpath, chưa được scan, không được khai báo hoặc bị điều kiện cấu hình loại bỏ, Spring không thể inject nó.

### Một ví dụ có hai ứng viên

~~~java
@Component
public class CardPaymentGateway implements PaymentGateway {
    // Xử lý thanh toán thẻ.
}

@Component
public class BankTransferGateway implements PaymentGateway {
    // Xử lý chuyển khoản.
}
~~~

Lúc này cả hai bean đều phù hợp với dependency kiểu **PaymentGateway**. Nếu service vẫn khai báo:

~~~java
public CheckoutService(PaymentGateway paymentGateway) {
    this.paymentGateway = paymentGateway;
}
~~~

Spring không thể tự suy luận rằng ứng dụng muốn dùng thẻ hay chuyển khoản. Khi không có metadata hoặc quy tắc lựa chọn thích hợp, việc khởi tạo bean có thể thất bại với lỗi **NoUniqueBeanDefinitionException** (thường được hiển thị qua thông báo *expected single matching bean but found 2*).

## 2. Quy tắc type matching và generic type

Spring tìm ứng viên dựa trên type của injection point và type mà bean khai báo. Quan hệ kế thừa/interface được tính đến; một bean của class implements interface có thể đáp ứng dependency khai báo bằng interface.

Ví dụ:

~~~java
public interface MessageSender {
    void send(String message);
}

@Component
public class EmailSender implements MessageSender {
    public void send(String message) {
        // Gửi email.
    }
}
~~~

Dependency kiểu **MessageSender** có thể nhận bean **EmailSender**. Ngược lại, dependency kiểu **EmailSender** yêu cầu bean cụ thể tương thích với **EmailSender**; một implementation khác của **MessageSender** không đáp ứng chỉ vì nó cùng implements interface.

### Generic type cũng có thể giúp phân biệt

Spring có thể sử dụng thông tin generic được giữ trong khai báo bean và injection point để thu hẹp ứng viên:

~~~java
public interface Store<T> {
    void save(T value);
}
~~~

Hai implementation:

~~~java
@Component
public class StringStore implements Store<String> {

    public void save(String value) {
        // Lưu chuỗi.
    }
}

@Component
public class IntegerStore implements Store<Integer> {

    public void save(Integer value) {
        // Lưu số nguyên.
    }
}
~~~

Injection point:

~~~java
@Service
public class TextImportService {

    private final Store<String> store;

    public TextImportService(Store<String> store) {
        this.store = store;
    }
}
~~~

Trong trường hợp Spring giữ được generic metadata như trên, **Store<String>** có thể được phân biệt với **Store<Integer>**. Đây là một cách hữu ích để dùng cùng abstraction cho nhiều kiểu dữ liệu.

Tuy nhiên, nếu dùng raw type:

~~~java
private final Store store;
~~~

thông tin generic không còn giúp phân biệt rõ ràng như trước. Khi có nhiều implementation tương thích, bạn có thể lại gặp ambiguity. Nên khai báo generic type đầy đủ tại injection point và tránh raw type khi không có lý do đặc biệt.

**Lưu ý:** generic matching phụ thuộc metadata kiểu mà Spring có thể suy ra từ bean definition và class. Những factory method trả về raw type hoặc cấu trúc generic phức tạp có thể làm mất thông tin mà bạn kỳ vọng; hãy khai báo kiểu trả về cụ thể và dễ suy luận.

## 3. @Primary: đánh dấu ứng viên ưu tiên

Khi một type có nhiều implementation nhưng phần lớn ứng dụng nên dùng một implementation mặc định, có thể đánh dấu bean đó bằng **@Primary**.

~~~java
@Component
@Primary
public class CardPaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(PaymentCommand command) {
        // Xử lý thanh toán thẻ.
        return PaymentResult.accepted();
    }
}

@Component
public class BankTransferGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(PaymentCommand command) {
        // Xử lý chuyển khoản.
        return PaymentResult.accepted();
    }
}
~~~

Service không cần biết tên implementation:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway paymentGateway;

    public CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
~~~

Khi Spring cần inject **một bean PaymentGateway**, **CardPaymentGateway** được chọn làm ứng viên primary trong số các ứng viên phù hợp.

### @Primary không xóa bean còn lại

**BankTransferGateway** vẫn là bean trong ApplicationContext. Nó vẫn có thể được inject bằng qualifier, được lấy qua provider hoặc xuất hiện trong collection injection.

Có thể hình dung:

~~~text
PaymentGateway candidates
    ├── CardPaymentGateway       @Primary  ← chọn mặc định cho một dependency
    └── BankTransferGateway                ← vẫn tồn tại
~~~

**@Primary** là metadata ưu tiên khi chọn một ứng viên cho một dependency đơn. Nó không có nghĩa chỉ còn một implementation hoạt động trong ứng dụng.

### Đặt @Primary ở đâu?

Có thể đánh dấu class component:

~~~java
@Component
@Primary
public class CardPaymentGateway implements PaymentGateway {
}
~~~

Hoặc đánh dấu phương thức **@Bean**:

~~~java
@Configuration
public class PaymentConfiguration {

    @Bean
    @Primary
    PaymentGateway defaultPaymentGateway() {
        return new CardPaymentGateway();
    }
}
~~~

Không nên đồng thời đăng ký cùng một implementation bằng component scanning và một factory method khác nếu điều đó tạo ra hai bean ngoài dự kiến. Hãy xác định một cơ chế đăng ký rõ ràng cho mỗi bean.

### Khi có nhiều @Primary thì sao?

Nếu nhiều ứng viên cùng được đánh dấu **@Primary** cho cùng type và injection point, Spring vẫn không có một ứng viên primary duy nhất để chọn. Kết quả có thể là lỗi không xác định được bean phù hợp. Mỗi dependency đơn cần một quy tắc lựa chọn rõ ràng.

## 4. @Qualifier: chỉ rõ nhóm bean phù hợp

**@Qualifier** giúp thu hẹp tập ứng viên theo một nhãn. Ví dụ, thay vì luôn dùng cổng thanh toán primary, một service chuyên xử lý chuyển khoản có thể chỉ định qualifier:

~~~java
@Component
@Qualifier("bankTransfer")
public class BankTransferGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(PaymentCommand command) {
        return PaymentResult.accepted();
    }
}
~~~

Tại injection point:

~~~java
@Service
public class BankPayoutService {

    private final PaymentGateway paymentGateway;

    public BankPayoutService(
            @Qualifier("bankTransfer")
            PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
~~~

Spring trước hết tìm những bean tương thích với **PaymentGateway**, sau đó dùng qualifier để chọn ứng viên có metadata phù hợp. Nếu qualifier không khớp bean nào, dependency không thể được resolve.

### Qualifier không nhất thiết là tên bean

Giá trị trong **@Qualifier("bankTransfer")** thường được hiểu là một qualifier label. Nó có thể trùng với bean name, nhưng ý nghĩa chính là **nhãn dùng để lọc ứng viên**, không phải yêu cầu rằng class phải có đúng tên đó.

Ví dụ, có thể dùng một qualifier theo môi trường hoặc vai trò:

~~~java
@Component
@Qualifier("external")
public class ExternalPaymentGateway implements PaymentGateway {
    // ...
}

@Component
@Qualifier("sandbox")
public class SandboxPaymentGateway implements PaymentGateway {
    // ...
}
~~~

Service có thể yêu cầu **@Qualifier("sandbox")** mà không cần biết tên class cụ thể. Điều này làm ý định của injection point dễ đọc hơn.

### @Qualifier có thể kết hợp với @Primary

**@Qualifier** lọc nhóm ứng viên theo nhãn; **@Primary** đánh dấu ứng viên ưu tiên trong nhóm còn lại khi cần chọn một bean. Vì vậy, qualifier có thể dùng để chọn một implementation khác với bean primary mặc định.

Ví dụ:

~~~java
@Component
@Primary
@Qualifier("card")
public class CardPaymentGateway implements PaymentGateway {
    // ...
}

@Component
@Qualifier("bank")
public class BankTransferGateway implements PaymentGateway {
    // ...
}
~~~

Dependency không ghi qualifier sẽ ưu tiên **CardPaymentGateway**. Dependency yêu cầu **@Qualifier("bank")** sẽ chọn **BankTransferGateway** nếu đó là ứng viên phù hợp duy nhất cho qualifier đó.

### Có thể dùng nhiều qualifier?

Qualifier có thể được dùng để lọc theo nhiều tiêu chí khi thiết kế metadata phù hợp. Ví dụ, ứng dụng có thể muốn chọn implementation vừa thuộc nhóm **external** vừa hỗ trợ khu vực **vn**. Spring hỗ trợ qualifier annotation tùy chỉnh có thuộc tính để biểu diễn những metadata như vậy.

## 5. Tạo custom qualifier để tránh chuỗi khó quản lý

Khi ứng dụng có nhiều integration, những chuỗi như **"bankTransfer"**, **"sandbox"**, **"production"** có thể bị lặp ở nhiều nơi. Bạn có thể định nghĩa annotation qualifier riêng:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.beans.factory.annotation.Qualifier;

@Target({
    ElementType.FIELD,
    ElementType.PARAMETER,
    ElementType.TYPE,
    ElementType.METHOD
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface BankPayment {
}
~~~

Đánh dấu implementation:

~~~java
@Component
@BankPayment
public class BankTransferGateway implements PaymentGateway {
    // ...
}
~~~

Và dùng tại injection point:

~~~java
@Service
public class BankPayoutService {

    private final PaymentGateway gateway;

    public BankPayoutService(@BankPayment PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Custom qualifier biến một nhãn kỹ thuật thành tên có ý nghĩa trong domain tích hợp. Nó cũng giúp IDE hỗ trợ điều hướng và refactor tốt hơn so với chuỗi literal.

### Qualifier có thuộc tính

Khi cần nhiều chiều metadata, có thể định nghĩa qualifier annotation có thuộc tính:

~~~java
@Target({
    ElementType.FIELD,
    ElementType.PARAMETER,
    ElementType.TYPE,
    ElementType.METHOD
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface PaymentRegion {
    String value();
}
~~~

Implementation:

~~~java
@Component
@PaymentRegion("VN")
public class VietnamPaymentGateway implements PaymentGateway {
    // ...
}
~~~

Injection:

~~~java
public BankPayoutService(
        @PaymentRegion("VN") PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Spring có thể dùng thuộc tính qualifier để so khớp metadata. Khi có nhiều tiêu chí, có thể kết hợp các qualifier hoặc thiết kế một annotation chuyên biệt cho một vai trò cụ thể.

## 6. Bean name và qualifier: đừng nhầm hai khái niệm

Một bean thường có tên. Với component scanning, tên mặc định thường được tạo từ tên class theo quy tắc bean naming; với **@Bean**, tên mặc định thường là tên phương thức factory.

Ví dụ:

~~~java
@Configuration
public class PaymentConfiguration {

    @Bean
    PaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    PaymentGateway bankGateway() {
        return new BankTransferGateway();
    }
}
~~~

Ở đây bean name lần lượt là **cardGateway** và **bankGateway**. Có thể dùng:

~~~java
public BankPayoutService(
        @Qualifier("bankGateway") PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Spring hỗ trợ tên bean như một giá trị qualifier khi cần lọc ứng viên. Nhưng trong thiết kế, nên xem **bean name** là danh tính của bean trong container, còn **qualifier** là metadata thể hiện loại/nhóm bean phù hợp với một dependency. Hai giá trị có thể trùng nhau nhưng không nhất thiết phải như vậy.

Nếu thay tên bean vì lý do cấu trúc, qualifier theo vai trò có thể vẫn giữ nguyên. Điều này giúp giảm sự phụ thuộc của nghiệp vụ vào tên factory method hoặc tên class.

### @Autowired và @Resource khác nhau ở đâu?

**@Autowired** của Spring chủ yếu giải quyết dependency theo type, sau đó có thể dùng qualifier và metadata để chọn ứng viên.

**@Resource** (từ Jakarta Annotations) thường biểu đạt việc tìm dependency theo tên trước; khi cần, nó cũng có thể sử dụng kiểu để resolve theo quy tắc của annotation và môi trường.

Không nên chọn **@Resource** chỉ vì muốn né lỗi nhiều bean mà không xác định ý định rõ. Nếu mục tiêu là “cần implementation thuộc nhóm bank”, **@Qualifier** hoặc custom qualifier thường diễn đạt đúng hơn. Nếu mục tiêu là “cần bean có tên cụ thể”, name-based injection có thể phù hợp nhưng tạo liên hệ trực tiếp với bean name.

## 7. Inject nhiều bean cùng type: List, Set và Map

Không phải lúc nào ứng dụng cũng muốn chọn đúng một implementation. Có những trường hợp cần gọi **tất cả** các implementation phù hợp.

Ví dụ, ứng dụng có nhiều bộ kiểm tra một đơn hàng:

~~~java
public interface OrderRule {
    void validate(Order order);
}
~~~

Các implementation:

~~~java
@Component
public class StockRule implements OrderRule {
    public void validate(Order order) {
        // Kiểm tra tồn kho.
    }
}

@Component
public class CreditRule implements OrderRule {
    public void validate(Order order) {
        // Kiểm tra hạn mức tín dụng.
    }
}

@Component
public class AddressRule implements OrderRule {
    public void validate(Order order) {
        // Kiểm tra địa chỉ giao hàng.
    }
}
~~~

Service nhận collection:

~~~java
@Service
public class OrderValidationService {

    private final List<OrderRule> rules;

    public OrderValidationService(List<OrderRule> rules) {
        this.rules = rules;
    }

    public void validate(Order order) {
        for (OrderRule rule : rules) {
            rule.validate(order);
        }
    }
}
~~~

Spring có thể inject tất cả bean phù hợp vào **List<OrderRule>**. Điều này giải quyết bài toán nhiều implementation bằng cách **tập hợp chúng**, không phải chọn một ứng viên duy nhất.

### Collection injection và @Primary

Một điểm quan trọng: **@Primary** chủ yếu quyết định ứng viên cho dependency đơn. Khi inject **List<OrderRule>**, Spring vẫn cung cấp collection các bean phù hợp, thay vì chỉ đưa bean primary vào list.

~~~text
List<OrderRule>
    ├── StockRule
    ├── CreditRule
    └── AddressRule
~~~

Nếu collection injection có qualifier, qualifier có thể lọc collection xuống nhóm bean mang metadata phù hợp.

### Thứ tự của collection và @Order

Nếu thứ tự thực thi rule có ý nghĩa, có thể dùng **@Order**:

~~~java
@Component
@Order(10)
public class StockRule implements OrderRule {
    // ...
}

@Component
@Order(20)
public class CreditRule implements OrderRule {
    // ...
}
~~~

Với collection injection có thứ tự như **List**, Spring có thể sắp xếp theo order metadata. Giá trị order nhỏ hơn có mức ưu tiên sắp xếp cao hơn. Nếu thứ tự nghiệp vụ là bắt buộc, nên thể hiện nó một cách rõ ràng và kiểm thử; đừng dựa vào thứ tự tình cờ của component scan.

**@Order không phải cách chọn bean duy nhất cho một constructor parameter.** Nó chủ yếu ảnh hưởng thứ tự của collection/ordered stream. Nếu cần một bean cụ thể cho dependency đơn, hãy dùng **@Primary**, **@Qualifier** hoặc một quy tắc lựa chọn rõ ràng khác.

### Inject Map<String, T>

Spring cũng có thể inject map với key là bean name và value là bean tương ứng:

~~~java
@Service
public class PaymentRouter {

    private final Map<String, PaymentGateway> gateways;

    public PaymentRouter(Map<String, PaymentGateway> gateways) {
        this.gateways = gateways;
    }

    public PaymentResult pay(
            String gatewayName,
            PaymentCommand command) {
        PaymentGateway gateway = gateways.get(gatewayName);

        if (gateway == null) {
            throw new IllegalArgumentException(
                    "Không hỗ trợ gateway: " + gatewayName);
        }

        return gateway.charge(command);
    }
}
~~~

Map này giúp lựa chọn theo tên bean một cách tường minh. Tuy nhiên, việc lấy tên gateway từ request người dùng rồi truy cập map trực tiếp có thể tạo rủi ro nếu không kiểm soát danh sách được phép. Ứng dụng nên ánh xạ input bên ngoài sang một enum/identifier hợp lệ và kiểm tra quyền trước khi chọn adapter.

## 8. ObjectProvider khi muốn chọn bean tại thời điểm cần

Khi ứng dụng không muốn inject trực tiếp một bean đơn mà muốn trì hoãn việc lấy bean, Spring cung cấp **ObjectProvider<T>**:

~~~java
@Service
public class OptionalReportService {

    private final ObjectProvider<ReportExporter> exporters;

    public OptionalReportService(
            ObjectProvider<ReportExporter> exporters) {
        this.exporters = exporters;
    }

    public void export(Report report) {
        ReportExporter exporter = exporters.getIfAvailable();
        if (exporter == null) {
            throw new IllegalStateException(
                    "Chưa cấu hình report exporter");
        }

        exporter.export(report);
    }
}
~~~

Một số phương thức đáng chú ý:

| API | Ý nghĩa |
|---|---|
| **getObject()** | Lấy bean; lỗi nếu không resolve được dependency duy nhất |
| **getIfAvailable()** | Trả bean nếu có; trả null nếu không có; trường hợp có nhiều ứng viên không thể chọn duy nhất vẫn có thể phát sinh lỗi |
| **getIfUnique()** | Trả bean nếu có một ứng viên duy nhất hoặc có thể chọn duy nhất; trả null nếu không có hoặc không xác định được duy nhất |
| **ifAvailable(Consumer)** | Thực hiện callback khi có bean phù hợp |
| **orderedStream()** | Lấy các bean phù hợp dưới dạng stream có xét thứ tự |

**ObjectProvider không tự giải quyết ambiguity bằng cách đoán.** Nó cung cấp API để ứng dụng quyết định lấy bean khi nào và xử lý trường hợp vắng mặt/không duy nhất ra sao.

Nếu cần nhiều implementation, có thể dùng **orderedStream()** hoặc collection injection. Nếu cần một implementation cụ thể theo vai trò, qualifier thường rõ hơn.

## 9. Không có bean và có nhiều bean là hai lỗi khác nhau

Hai tình huống này thường bị gộp thành “Spring không inject được”, nhưng nguyên nhân khác nhau.

### Không có bean phù hợp

~~~text
Injection point: PaymentGateway
Candidates:      (không có)
Result:          không resolve được dependency bắt buộc
~~~

Thông báo thường liên quan tới **NoSuchBeanDefinitionException** hoặc lỗi tạo bean bao ngoài, ví dụ:

~~~text
No qualifying bean of type 'PaymentGateway' available
~~~

Nguyên nhân thường gặp:

- Chưa có implementation.
- Implementation chưa được gắn stereotype hoặc đăng ký bằng **@Bean**.
- Package của implementation nằm ngoài component scan.
- Module/JAR chứa implementation chưa có trong runtime classpath.
- Bean bị **@Profile**, **@Conditional** hoặc điều kiện cấu hình loại bỏ.
- Kiểu dependency không khớp, kể cả generic type.

### Có nhiều bean phù hợp

~~~text
Injection point: PaymentGateway
Candidates:
  - CardPaymentGateway
  - BankTransferGateway
Result:          không xác định được một bean duy nhất
~~~

Thông báo thường liên quan tới **NoUniqueBeanDefinitionException**:

~~~text
expected single matching bean but found 2
~~~

Nguyên nhân thường gặp:

- Có nhiều implementation cùng type.
- Một implementation được đăng ký cả qua component scanning và **@Bean**.
- Nhiều configuration cùng tạo bean cùng type.
- Một module mới được import làm xuất hiện implementation thứ hai.

Cách giải quyết:

- Dùng **@Primary** nếu có một implementation mặc định.
- Dùng **@Qualifier** nếu từng injection point cần một vai trò cụ thể.
- Dùng **List<T>**, **Map<String, T>** hoặc provider nếu cần nhiều implementation.
- Loại bỏ bean đăng ký trùng nếu đó là lỗi cấu hình.

## 10. Quy trình xử lý lỗi NoUniqueBeanDefinitionException

Khi thấy thông báo nhiều bean cùng type, không nên thêm **@Primary** ngay mà chưa hiểu vì sao chúng cùng tồn tại. Hãy lần theo:

**Bước 1 — Xác định injection point.** Đọc class, constructor hoặc phương thức đang yêu cầu type nào. Ví dụ **PaymentGateway**.

**Bước 2 — Liệt kê các candidate.** Đọc danh sách bean trong thông báo lỗi. Xác định bean nào đến từ component scan, bean nào do **@Bean**, bean nào đến từ auto-configuration hoặc module phụ.

**Bước 3 — Xác định ý định của ứng dụng.** Ứng dụng cần một implementation mặc định, một implementation theo từng use case, hay cần gọi tất cả implementation?

**Bước 4 — Chọn cơ chế phù hợp.**

| Ý định | Cơ chế |
|---|---|
| Một bean mặc định cho phần lớn injection point | **@Primary** |
| Từng nơi cần implementation khác nhau | **@Qualifier** hoặc custom qualifier |
| Cần chạy tất cả implementation | **List<T>**, **Set<T>**, array hoặc stream |
| Cần truy cập theo bean name | **Map<String, T>** hoặc provider có lựa chọn rõ |
| Bean chỉ có ở một số môi trường | **@Profile**, **@Conditional** và optional dependency phù hợp |
| Có bean bị đăng ký trùng ngoài ý muốn | Sửa nguồn đăng ký để chỉ tạo bean cần thiết |

**Bước 5 — Kiểm tra hành vi lúc chạy.** Xác nhận đúng implementation được inject, đúng thứ tự collection nếu có yêu cầu, và không có bean không mong muốn trong context.

## 11. @Primary, @Qualifier và @Order không thay thế nhau

Ba annotation này thường bị nhầm lẫn:

| Annotation | Câu hỏi nó trả lời | Trường hợp điển hình |
|---|---|---|
| **@Primary** | Trong các ứng viên phù hợp, bean nào là lựa chọn ưu tiên cho dependency đơn? | Cổng thanh toán mặc định |
| **@Qualifier** | Injection point này cần ứng viên thuộc nhóm/vai trò nào? | Service yêu cầu cổng bank |
| **@Order** | Các bean trong collection/ordered processing nên sắp xếp theo thứ tự nào? | Các bước validate chạy theo thứ tự |

Ví dụ:

~~~java
@Component
@Primary
public class CardGateway implements PaymentGateway {
}

@Component
@Qualifier("bank")
public class BankGateway implements PaymentGateway {
}

@Component
@Order(1)
public class StockRule implements OrderRule {
}
~~~

- **CheckoutService(PaymentGateway gateway)** có thể nhận **CardGateway** vì primary.
- **BankPayoutService(@Qualifier("bank") PaymentGateway gateway)** nhận **BankGateway**.
- **OrderValidationService(List<OrderRule> rules)** nhận nhiều rule và thứ tự có thể được điều khiển bằng **@Order**.

Không nên dùng **@Order(1)** để mong Spring chọn bean đó cho một tham số đơn thay cho **@Primary** hoặc **@Qualifier**.

## 12. Chọn implementation theo profile hoặc điều kiện cấu hình

Đôi khi ứng dụng chỉ muốn đăng ký một implementation tùy theo môi trường. Ví dụ, môi trường phát triển dùng gateway giả; môi trường production dùng gateway thật.

~~~java
@Configuration
public class PaymentConfiguration {

    @Bean
    @Profile("dev")
    PaymentGateway sandboxGateway() {
        return new SandboxPaymentGateway();
    }

    @Bean
    @Profile("prod")
    PaymentGateway productionGateway() {
        return new ProductionPaymentGateway();
    }
}
~~~

Khi chạy với profile **dev**, bean sandbox được đăng ký; với profile **prod**, bean production được đăng ký. Cần bảo đảm profile được kích hoạt đúng và không có implementation khác cùng type gây ambiguity.

Trong Spring Boot, các điều kiện như **@ConditionalOnProperty** hoặc **@ConditionalOnMissingBean** cũng thường được dùng trong auto-configuration để chọn hoặc cung cấp bean mặc định. Chúng giải quyết câu hỏi **bean nào được đăng ký trong context**, trong khi **@Primary** và **@Qualifier** giải quyết việc chọn trong các candidate đã có.

Đừng dùng profile để biểu diễn từng khách hàng hoặc từng request. Profile thường là lựa chọn cấu hình ở cấp application context; lựa chọn nghiệp vụ theo request cần được thực hiện trong service dựa trên dữ liệu và quy tắc hợp lệ.

## 13. Một ví dụ đầy đủ: mặc định và lựa chọn theo qualifier

Giả sử ứng dụng có hai gateway:

~~~java
public interface PaymentGateway {
    String name();
}
~~~

Implementation mặc định:

~~~java
@Component
@Primary
public class CardPaymentGateway implements PaymentGateway {

    @Override
    public String name() {
        return "card";
    }
}
~~~

Implementation chuyển khoản:

~~~java
@Component
@Qualifier("bank")
public class BankTransferGateway implements PaymentGateway {

    @Override
    public String name() {
        return "bank";
    }
}
~~~

Service dùng gateway mặc định:

~~~java
@Service
public class DefaultCheckoutService {

    private final PaymentGateway gateway;

    public DefaultCheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public String selectedGateway() {
        return gateway.name();
    }
}
~~~

Service chuyên xử lý chuyển khoản:

~~~java
@Service
public class BankPayoutService {

    private final PaymentGateway gateway;

    public BankPayoutService(
            @Qualifier("bank") PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public String selectedGateway() {
        return gateway.name();
    }
}
~~~

Kết quả:

| Injection point | Bean được inject |
|---|---|
| **DefaultCheckoutService(PaymentGateway)** | **CardPaymentGateway** |
| **BankPayoutService(@Qualifier("bank") PaymentGateway)** | **BankTransferGateway** |

Cả hai bean đều tồn tại trong ApplicationContext. Container không xóa implementation chuyển khoản chỉ vì thẻ được đánh dấu **@Primary**.

## 14. Một số quy tắc bổ sung khi thiết kế candidate

### Tên bean nên ổn định và có ý nghĩa

Khi dùng **@Bean**, tên method thường trở thành bean name mặc định. Nếu code khác phụ thuộc vào tên này qua qualifier dạng chuỗi, việc đổi tên method có thể ảnh hưởng wiring. Custom qualifier có thể biểu đạt vai trò ổn định hơn.

### Không lạm dụng @Primary

Nếu có nhiều service với ý định khác nhau nhưng tất cả đều vô tình nhận implementation primary, một bean mặc định có thể che giấu việc service cần một vai trò cụ thể. Với integration quan trọng, qualifier tường minh thường dễ đọc hơn.

### Không dùng collection nếu chỉ muốn chọn một bean

Inject **List<PaymentGateway>** rồi lấy phần tử đầu tiên là cách lựa chọn mong manh nếu không có quy tắc thứ tự được thiết kế rõ. Dùng qualifier hoặc một registry/router có quy tắc cụ thể sẽ dễ hiểu hơn.

### Cẩn thận khi thay đổi dependency trong module

Thêm một implementation mới vào classpath có thể làm một injection point trước đây chỉ có một candidate trở thành ambiguous. Vì vậy, việc thêm bean là thay đổi có thể ảnh hưởng quá trình khởi động của những module khác, dù không sửa trực tiếp service đang dùng nó.

### Phân biệt bean candidate với đối tượng theo request

Spring inject bean theo context và scope. Một request mang giá trị **paymentMethod = "bank"** không tự khiến container chọn bean khác cho riêng request đó. Nếu một service phải định tuyến theo từng request, hãy inject một tập implementation hoặc một router rồi để logic ứng dụng chọn adapter phù hợp theo input đã được xác thực.

## 15. Thực hành quan sát cách Spring chọn bean

Tạo project Spring Boot với dependency **Spring Context** (hoặc Spring Boot starter phù hợp), rồi thêm interface **PaymentGateway**, hai implementation và một service như ví dụ trên.

Thử từng trường hợp:

1. **Chỉ có một implementation.** Khởi động context và quan sát constructor injection thành công.
2. **Thêm implementation thứ hai.** Bỏ qualifier và primary; quan sát lỗi nhiều candidate khi tạo service.
3. **Đánh dấu một bean @Primary.** Khởi động lại; quan sát service nhận bean ưu tiên.
4. **Dùng @Qualifier.** Tạo service khác yêu cầu qualifier bank; xác nhận hai service nhận hai implementation khác nhau.
5. **Inject List<PaymentGateway>.** Quan sát cả hai bean xuất hiện trong collection, kể cả bean primary.
6. **Thêm @Order.** Inject List và quan sát thứ tự sắp xếp.
7. **Bỏ implementation khỏi profile đang chạy.** Quan sát khác biệt giữa thiếu bean và nhiều bean.
8. **Đổi interface generic.** Thử Store<String> và Store<Integer>, rồi thử raw Store để thấy generic metadata ảnh hưởng việc chọn ứng viên.

Khi debug, hãy quan sát log khởi động và thông báo exception. Nếu có Actuator hoặc công cụ kiểm tra bean phù hợp trong môi trường phát triển, có thể dùng để xem những bean nào đang được đăng ký. Không nên mở thông tin quản trị bean cho người dùng không có quyền trong môi trường production.

## 16. Tư duy chọn ứng viên trong thiết kế thực tế

Trước khi thêm **@Primary** hay **@Qualifier**, hãy trả lời:

- Dependency này cần **một implementation mặc định**, **một implementation theo vai trò**, hay **tất cả implementation**?
- Có nhiều bean vì ứng dụng chủ ý hỗ trợ nhiều chiến lược, hay vì cùng một bean bị đăng ký trùng?
- Việc lựa chọn thuộc cấu hình lúc startup hay thuộc quyết định nghiệp vụ cho từng request?
- Type và generic type ở injection point đã mô tả đủ ý định chưa?
- Qualifier nên là nhãn đơn giản hay một custom annotation mang ý nghĩa rõ?
- Nếu bean vắng mặt, ứng dụng phải fail fast, dùng fallback hợp lệ hay bỏ qua tính năng phụ?
- Nếu collection có thứ tự, thứ tự đó có phải một phần của hành vi nghiệp vụ và đã được kiểm soát chưa?

Một quy tắc tốt là **để kiểu Java biểu diễn hợp đồng, qualifier biểu diễn vai trò, primary biểu diễn lựa chọn mặc định, còn collection biểu diễn nhu cầu sử dụng nhiều implementation**.

## Kết luận

Spring thường tìm bean phù hợp bằng **type của dependency**. Khi chỉ có một candidate phù hợp, container có thể inject trực tiếp. Khi có nhiều candidate, ứng dụng cần diễn đạt rõ ý định:

- Dùng **@Primary** để đánh dấu bean ưu tiên cho dependency đơn.
- Dùng **@Qualifier** hoặc custom qualifier để chọn bean theo vai trò.
- Dùng **List<T>**, **Set<T>**, array hoặc **Map<String, T>** khi cần nhiều implementation.
- Dùng **ObjectProvider<T>** khi cần truy cập bean theo nhu cầu và xử lý trường hợp vắng mặt hoặc không duy nhất.
- Dùng **@Profile** hoặc conditional configuration khi cần quyết định bean nào được đăng ký theo môi trường.

Khi gặp lỗi, hãy phân biệt **không có bean phù hợp** với **có nhiều bean phù hợp**. Kiểm tra classpath, component scan, điều kiện đăng ký và metadata trước khi sửa. Việc chọn bean là một phần của thiết kế dependency: Spring thực hiện quy tắc mà ứng dụng khai báo, còn ứng dụng phải xác định implementation nào thực sự phù hợp với từng ca sử dụng.
