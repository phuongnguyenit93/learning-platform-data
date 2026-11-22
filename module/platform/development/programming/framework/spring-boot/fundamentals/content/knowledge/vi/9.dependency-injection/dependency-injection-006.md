# Tiêm List, Set hoặc Map của nhiều bean cùng kiểu

Trong một ứng dụng Spring Boot, có những lúc một service cần sử dụng **nhiều implementation của cùng một interface**. Ví dụ hệ thống thanh toán có thể hỗ trợ thẻ, ví điện tử và chuyển khoản; hệ thống thông báo có thể có email, SMS và push notification. Nếu mỗi lần thêm một implementation ta lại sửa constructor để khai báo thêm một tham số, code sẽ nhanh chóng trở nên cồng kềnh.

Spring hỗ trợ **collection injection**: khi một dependency có kiểu phần tử xác định, container có thể tìm tất cả bean phù hợp và cung cấp chúng dưới dạng **List**, **Set**, mảng hoặc **Map<String, T>**.

Ví dụ:

~~~java
public interface PaymentHandler {
    boolean supports(String method);
    void pay(long orderId);
}
~~~

Nếu context có ba bean cùng implement PaymentHandler, một constructor có thể nhận:

~~~java
public PaymentDispatcher(List<PaymentHandler> handlers) {
    this.handlers = handlers;
}
~~~

Spring sẽ resolve các bean phù hợp và truyền collection vào constructor. Cách này giúp service làm việc với một tập implementation được cấu hình trong context, đồng thời giảm sự phụ thuộc vào từng class cụ thể.

## 1. Collection injection hoạt động như thế nào?

Spring IoC container không chỉ resolve một bean cho một dependency đơn. Với một số kiểu dependency đặc biệt, Spring có thể tìm **nhiều candidate cùng kiểu** và tổng hợp chúng thành collection.

Các dạng thường dùng:

| Kiểu dependency | Kết quả |
|---|---|
| **T[]** | Mảng chứa các bean phù hợp kiểu T. |
| **List<T>** | Danh sách các bean phù hợp kiểu T. |
| **Set<T>** | Tập các bean phù hợp kiểu T. |
| **Map<String, T>** | Map từ bean name sang bean phù hợp kiểu T. |

Trong đó, **T** có thể là class cụ thể hoặc interface. Cách dùng phổ biến nhất là khai báo dependency theo interface để các implementation có thể thay thế hoặc mở rộng.

~~~text
ApplicationContext
    ├── cardPaymentHandler : PaymentHandler
    ├── walletPaymentHandler : PaymentHandler
    └── bankTransferHandler : PaymentHandler
                  │
                  ▼
       Injection point: List<PaymentHandler>
                  │
                  ▼
       [card, wallet, bank transfer]
~~~

Điều quan trọng: các phần tử collection là **bean do container resolve**. Spring không đơn giản quét tất cả class Java trong project rồi gọi new cho mọi class implement interface. Mỗi implementation phải được đăng ký làm bean bằng component scanning, @Bean, import, auto-configuration hoặc một cơ chế đăng ký bean phù hợp khác.

## 2. Chuẩn bị các implementation cùng kiểu

Giả sử ứng dụng cần nhiều kênh thanh toán:

~~~java
package com.example.payment;

public interface PaymentHandler {
    String method();
    void pay(long orderId);
}
~~~

Implementation thanh toán bằng thẻ:

~~~java
package com.example.payment;

import org.springframework.stereotype.Component;

@Component("cardPaymentHandler")
public class CardPaymentHandler implements PaymentHandler {
    @Override
    public String method() {
        return "card";
    }

    @Override
    public void pay(long orderId) {
        System.out.println("Thanh toán thẻ cho đơn " + orderId);
    }
}
~~~

Implementation ví điện tử:

~~~java
package com.example.payment;

import org.springframework.stereotype.Component;

@Component("walletPaymentHandler")
public class WalletPaymentHandler implements PaymentHandler {
    @Override
    public String method() {
        return "wallet";
    }

    @Override
    public void pay(long orderId) {
        System.out.println("Thanh toán ví cho đơn " + orderId);
    }
}
~~~

Implementation chuyển khoản:

~~~java
package com.example.payment;

import org.springframework.stereotype.Component;

@Component("bankTransferPaymentHandler")
public class BankTransferPaymentHandler implements PaymentHandler {
    @Override
    public String method() {
        return "bank-transfer";
    }

    @Override
    public void pay(long orderId) {
        System.out.println("Thanh toán chuyển khoản cho đơn " + orderId);
    }
}
~~~

Nếu package nằm trong phạm vi component scan, Spring có thể đăng ký ba class này thành ba bean. Mỗi bean có cùng kiểu assignable là **PaymentHandler**, nhưng có bean name khác nhau.

Ngoài component annotation, ta cũng có thể đăng ký implementation bằng cấu hình Java:

~~~java
@Configuration
public class PaymentConfiguration {
    @Bean
    PaymentHandler cardPaymentHandler() {
        return new CardPaymentHandler();
    }

    @Bean
    PaymentHandler walletPaymentHandler() {
        return new WalletPaymentHandler();
    }
}
~~~

Tên bean mặc định trong ví dụ trên là tên phương thức factory: **cardPaymentHandler** và **walletPaymentHandler**. Khi khai báo bằng @Bean, lớp implementation không cần mang @Component.

Không nên vừa component-scan một class vừa khai báo thêm một @Bean tạo cùng implementation nếu không có chủ ý, vì có thể đăng ký hai bean khác nhau cho cùng một vai trò.

## 3. Tiêm List<T>

**List<T>** là lựa chọn thuận tiện khi service cần duyệt các implementation theo một thứ tự có ý nghĩa.

~~~java
package com.example.payment;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class PaymentDispatcher {
    private final List<PaymentHandler> handlers;

    public PaymentDispatcher(List<PaymentHandler> handlers) {
        this.handlers = handlers;
    }

    public void pay(String method, long orderId) {
        PaymentHandler handler = handlers.stream()
                .filter(candidate -> candidate.method().equals(method))
                .findFirst()
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Không hỗ trợ phương thức: " + method));

        handler.pay(orderId);
    }
}
~~~

Nếu có ba bean PaymentHandler, Spring có thể truyền một List chứa cả ba. Service chỉ phụ thuộc interface, nên khi thêm implementation mới đã được đăng ký, danh sách có thể nhận thêm phần tử mà không cần sửa constructor.

### 3.1. Thứ tự phần tử trong List

Spring hỗ trợ sắp xếp các bean trong những dependency collection có thứ tự, điển hình là mảng và List, dựa trên các cơ chế như:

- Interface **Ordered**.
- Annotation **@Order**.
- **@Priority** trong các trường hợp Spring hỗ trợ.

Ví dụ:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(1)
public class CardPaymentHandler implements PaymentHandler {
    // ...
}
~~~

~~~java
@Component
@Order(2)
public class WalletPaymentHandler implements PaymentHandler {
    // ...
}
~~~

~~~java
@Component
@Order(3)
public class BankTransferPaymentHandler implements PaymentHandler {
    // ...
}
~~~

Giá trị order nhỏ hơn có độ ưu tiên cao hơn trong thứ tự sắp xếp thông thường. Nếu không khai báo order, không nên dựa vào thứ tự tình cờ của quá trình scan hoặc đăng ký bean như một hợp đồng nghiệp vụ.

Một implementation có thể triển khai Ordered:

~~~java
import org.springframework.core.Ordered;

public class CardPaymentHandler implements PaymentHandler, Ordered {
    @Override
    public int getOrder() {
        return 10;
    }

    // Các phương thức PaymentHandler...
}
~~~

Không nên trộn nhiều nguồn order mà không hiểu quy tắc ưu tiên và cách comparator của Spring xử lý. Chọn một quy ước nhất quán cho các implementation sẽ dễ bảo trì hơn.

**@Order điều khiển thứ tự trong các điểm injection được sắp xếp; nó không quyết định thứ tự khởi tạo singleton.** Thứ tự khởi tạo bean là vấn đề khác, liên quan dependency, lazy initialization, @DependsOn và lifecycle.

### 3.2. Khi nào List phù hợp?

List phù hợp khi:

- Cần chạy tất cả implementation theo một trình tự.
- Cần áp dụng nhiều validator hoặc rule theo thứ tự.
- Cần pipeline gồm nhiều processor.
- Cần duyệt các strategy và tìm strategy phù hợp.
- Muốn kiểm tra danh sách implementation trong test.

Nếu thứ tự là một phần của nghiệp vụ, hãy khai báo **@Order** rõ ràng và kiểm thử thứ tự đó. Không nên để kết quả phụ thuộc vào tên class hoặc thứ tự file.

## 4. Tiêm Set<T>

**Set<T>** phù hợp khi cần tập các bean cùng kiểu và không muốn biểu diễn thứ tự xử lý như một phần của hợp đồng.

~~~java
import java.util.Set;
import org.springframework.stereotype.Service;

@Service
public class PaymentCapabilityRegistry {
    private final Set<PaymentHandler> handlers;

    public PaymentCapabilityRegistry(Set<PaymentHandler> handlers) {
        this.handlers = handlers;
    }

    public boolean supports(String method) {
        return handlers.stream()
                .anyMatch(handler -> handler.method().equals(method));
    }
}
~~~

Spring resolve các bean phù hợp và chuyển chúng thành kiểu Set yêu cầu. Vì Set không biểu diễn thứ tự như List, **không nên dựa vào iteration order** để quyết định chiến lược nghiệp vụ. Nếu cần thứ tự, dùng List và @Order.

### 4.1. Set không tự loại các bean khác nhau chỉ vì cùng kiểu

Ba bean CardPaymentHandler, WalletPaymentHandler và BankTransferPaymentHandler là ba instance khác nhau, nên một Set thông thường có thể chứa cả ba.

Set loại phần tử trùng theo quy tắc equality/hash code của object. Nếu các bean được thiết kế với equals/hashCode đặc biệt khiến hai instance được xem là bằng nhau, collection Set có thể chỉ giữ một phần tử trong tập được tạo. Đối với Spring strategy bean, thường không nên override equality theo cách khiến các implementation độc lập bị xem là cùng một phần tử nếu mục tiêu là giữ tất cả.

### 4.2. Không dùng Set khi thứ tự có ý nghĩa

Ví dụ một danh sách validator cần chạy theo thứ tự:

~~~text
1. Kiểm tra định dạng
2. Kiểm tra quyền
3. Kiểm tra giới hạn
4. Kiểm tra trạng thái nghiệp vụ
~~~

Nếu thứ tự ảnh hưởng kết quả, **List<Validator>** với @Order diễn đạt ý định rõ hơn **Set<Validator>**. Set thích hợp hơn cho việc hỏi “có những capability nào?” hoặc “có implementation nào đáp ứng điều kiện?” mà không phụ thuộc thứ tự.

## 5. Tiêm Map<String, T>

**Map<String, T>** hữu ích khi cần tra cứu bean bằng tên. Với collection injection, key của map là **bean name**, value là instance của bean có kiểu T.

~~~java
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class PaymentHandlerRegistry {
    private final Map<String, PaymentHandler> handlersByBeanName;

    public PaymentHandlerRegistry(
            Map<String, PaymentHandler> handlersByBeanName) {
        this.handlersByBeanName = handlersByBeanName;
    }

    public PaymentHandler getByBeanName(String beanName) {
        PaymentHandler handler = handlersByBeanName.get(beanName);
        if (handler == null) {
            throw new IllegalArgumentException(
                    "Không có bean PaymentHandler: " + beanName);
        }
        return handler;
    }
}
~~~

Nếu context có các bean đã khai báo tên:

- **cardPaymentHandler**
- **walletPaymentHandler**
- **bankTransferPaymentHandler**

thì map có thể có cấu trúc:

~~~text
handlersByBeanName
├── "cardPaymentHandler"          → CardPaymentHandler
├── "walletPaymentHandler"        → WalletPaymentHandler
└── "bankTransferPaymentHandler"  → BankTransferPaymentHandler
~~~

Map này không phải map từ tên phương thức thanh toán sang handler trừ khi bean name được thiết kế trùng với method. Key phản ánh **bean name**, không tự lấy kết quả từ handler.method().

### 5.1. Tên bean mặc định và tên tùy chỉnh

Với component:

~~~java
@Component
public class CardPaymentHandler implements PaymentHandler {
}
~~~

Tên bean mặc định thường là **cardPaymentHandler**, theo quy tắc đặt tên component. Với:

~~~java
@Component("creditCard")
public class CardPaymentHandler implements PaymentHandler {
}
~~~

key sẽ là **creditCard**. Với @Bean:

~~~java
@Bean
PaymentHandler walletHandler() {
    return new WalletPaymentHandler();
}
~~~

tên bean mặc định là **walletHandler**.

Nếu ứng dụng đổi tên bean, các đoạn code tra cứu map theo tên phải cập nhật tương ứng. Do đó, khi tên là một phần của hợp đồng nghiệp vụ bên ngoài, hãy định nghĩa key nghiệp vụ riêng thay vì buộc API công khai phụ thuộc vào tên bean nội bộ.

### 5.2. Map<String, T> khác Map<DomainKey, T>

Spring collection injection đặc biệt hỗ trợ **Map có key kiểu String** để dùng bean name làm key. Ví dụ:

~~~java
Map<String, PaymentHandler> handlers;
~~~

Không nên kỳ vọng Spring tự tạo:

~~~java
Map<PaymentMethod, PaymentHandler> handlers;
~~~

với PaymentMethod là enum hoặc kiểu domain tùy ý, rồi tự suy luận key từ một method trên từng bean. Nếu muốn map theo mã nghiệp vụ, hãy inject List hoặc Map<String, T> rồi tự xây dựng registry:

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<String, PaymentHandler> handlersByMethod =
        handlers.stream().collect(Collectors.toMap(
                PaymentHandler::method,
                Function.identity()
        ));
~~~

Đoạn code này minh họa chuyển List thành map theo **method()**. Nếu hai handler trả về cùng một method, Collectors.toMap sẽ báo lỗi do key trùng nếu không cung cấp merge function. Đây thường là điều tốt vì giúp phát hiện cấu hình trùng capability thay vì âm thầm chọn một bean.

## 6. Ví dụ so sánh ba kiểu collection

Giả sử có ba implementation PaymentHandler được đăng ký. Một class có thể nhận từng kiểu collection tùy mục đích:

~~~java
@Service
public class PaymentCatalog {
    private final List<PaymentHandler> orderedHandlers;
    private final Set<PaymentHandler> handlerSet;
    private final Map<String, PaymentHandler> handlersByName;

    public PaymentCatalog(
            List<PaymentHandler> orderedHandlers,
            Set<PaymentHandler> handlerSet,
            Map<String, PaymentHandler> handlersByName) {
        this.orderedHandlers = orderedHandlers;
        this.handlerSet = handlerSet;
        this.handlersByName = handlersByName;
    }
}
~~~

Mỗi tham số được resolve như một dependency riêng:

| Tham số | Dùng cho việc gì? |
|---|---|
| **orderedHandlers** | Duyệt các handler theo thứ tự đã cấu hình. |
| **handlerSet** | Biểu diễn tập handler mà context cung cấp. |
| **handlersByName** | Tra cứu một handler theo bean name. |

Trong code thực tế, không nhất thiết phải inject cả ba nếu chỉ cần một. Mỗi collection có thể chứa cùng các bean nhưng cách truy cập và hợp đồng khác nhau.

## 7. @Qualifier khi chỉ muốn một nhóm bean

Đôi khi context có nhiều bean cùng kiểu, nhưng một consumer chỉ cần một **nhóm con**. Khi đó có thể dùng qualifier.

Ví dụ các processor được đánh dấu:

~~~java
@Component
@org.springframework.beans.factory.annotation.Qualifier("online")
public class CardPaymentHandler implements PaymentHandler {
    // ...
}
~~~

~~~java
@Component
@org.springframework.beans.factory.annotation.Qualifier("online")
public class WalletPaymentHandler implements PaymentHandler {
    // ...
}
~~~

~~~java
@Component
@org.springframework.beans.factory.annotation.Qualifier("offline")
public class BankTransferPaymentHandler implements PaymentHandler {
    // ...
}
~~~

Consumer chỉ nhận nhóm online:

~~~java
@Service
public class OnlinePaymentDispatcher {
    private final List<PaymentHandler> handlers;

    public OnlinePaymentDispatcher(
            @org.springframework.beans.factory.annotation.Qualifier("online")
            List<PaymentHandler> handlers) {
        this.handlers = handlers;
    }
}
~~~

Ở injection point collection, qualifier có thể **lọc các candidate** để chỉ lấy những bean có qualifier phù hợp. Nó không nhất thiết chọn đúng một bean như khi inject một dependency đơn.

### 7.1. Qualifier không chỉ là tên bean

Tên bean có thể được dùng như một fallback qualifier trong một số trường hợp, nhưng ý nghĩa chính của **@Qualifier** là metadata để lọc ứng viên theo ngữ nghĩa. Nên đặt qualifier theo vai trò như **online**, **retryable**, **regional** thay vì phụ thuộc hoàn toàn vào tên class.

Có thể định nghĩa annotation qualifier riêng:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.beans.factory.annotation.Qualifier;

@Target({ElementType.TYPE, ElementType.FIELD, ElementType.PARAMETER,
         ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface OnlinePayment {
}
~~~

Đánh dấu implementation:

~~~java
@Component
@OnlinePayment
public class CardPaymentHandler implements PaymentHandler {
    // ...
}
~~~

Inject nhóm:

~~~java
public OnlinePaymentDispatcher(
        @OnlinePayment List<PaymentHandler> handlers) {
    this.handlers = handlers;
}
~~~

Qualifier riêng giúp biểu đạt vai trò rõ ràng và giảm lỗi chính tả ở chuỗi tên.

## 8. @Primary có ảnh hưởng đến collection injection không?

**@Primary** được dùng để ưu tiên một bean khi có nhiều candidate cho một dependency đơn theo kiểu. Ví dụ:

~~~java
@Component
@Primary
public class CardPaymentHandler implements PaymentHandler {
    // ...
}
~~~

Khi một constructor cần:

~~~java
public CheckoutService(PaymentHandler handler) {
    this.handler = handler;
}
~~~

Spring có thể chọn CardPaymentHandler làm candidate ưu tiên nếu không có qualifier hoặc yếu tố khác quyết định.

Nhưng khi dependency là:

~~~java
public PaymentCatalog(List<PaymentHandler> handlers) {
    this.handlers = handlers;
}
~~~

thì mục tiêu là nhận **tất cả candidate phù hợp**. @Primary không loại những bean còn lại khỏi collection. Đây là khác biệt quan trọng giữa injection một bean và injection một tập bean.

Nếu chỉ muốn một nhóm, dùng qualifier. Nếu muốn tất cả, không dùng @Primary với kỳ vọng nó làm collection chỉ còn một phần tử.

## 9. Điều gì xảy ra khi không có bean phù hợp?

Collection injection không có nghĩa luôn nhận được collection rỗng. Với một dependency bắt buộc, nếu Spring không tìm thấy candidate thỏa mãn, quá trình resolve có thể thất bại và context không khởi động được.

Ví dụ:

~~~java
@Service
public class PaymentDispatcher {
    private final List<PaymentHandler> handlers;

    public PaymentDispatcher(List<PaymentHandler> handlers) {
        this.handlers = handlers;
    }
}
~~~

Nếu không có bean PaymentHandler phù hợp và dependency được xem là required, Spring có thể báo lỗi không tìm thấy dependency tương ứng. Hành vi cụ thể còn phụ thuộc cách khai báo injection và cơ chế resolution.

Nếu nghiệp vụ cho phép **không có implementation nào**, nên diễn đạt rõ tính optional thay vì dựa vào giả định collection sẽ luôn rỗng.

### 9.1. Dùng ObjectProvider khi muốn collection có thể rỗng

Spring cung cấp **ObjectProvider<T>** để truy vấn bean theo nhu cầu:

~~~java
import java.util.List;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class OptionalPaymentRegistry {
    private final ObjectProvider<PaymentHandler> handlerProvider;

    public OptionalPaymentRegistry(
            ObjectProvider<PaymentHandler> handlerProvider) {
        this.handlerProvider = handlerProvider;
    }

    public List<PaymentHandler> getHandlers() {
        return handlerProvider.orderedStream().toList();
    }
}
~~~

Nếu không có PaymentHandler nào, **orderedStream()** có thể cung cấp stream rỗng và kết quả list là danh sách rỗng. Cách này còn trì hoãn việc resolve/khởi tạo bean đến lúc gọi provider.

### 9.2. Dùng Optional cho dependency đơn

Nếu chỉ có thể có một bean và sự hiện diện của nó là tùy chọn, có thể dùng:

~~~java
public NotificationService(
        Optional<NotificationGateway> gateway) {
    this.gateway = gateway;
}
~~~

Optional diễn đạt dependency đơn có thể vắng mặt. Nó không phải cách thay thế tự động cho **List<T>** hoặc **Map<String, T>** khi muốn nhận nhiều implementation.

### 9.3. @Autowired(required = false) cần thận trọng

Field hoặc method injection với **@Autowired(required = false)** cho phép bỏ qua dependency không tìm thấy. Nhưng khi không có bean, field collection có thể không được gán như bạn mong đợi; cần xử lý trường hợp null phù hợp. Nếu muốn collection luôn có giá trị và có thể rỗng, **ObjectProvider.orderedStream()** thường biểu đạt rõ hơn.

## 10. Generic type quyết định Spring tìm bean nào

Spring dùng thông tin kiểu ở injection point để xác định candidate. Ví dụ:

~~~java
List<PaymentHandler> handlers;
~~~

yêu cầu các bean phù hợp với **PaymentHandler**, không phải mọi bean trong context.

Tương tự:

~~~java
Map<String, PaymentHandler> handlers;
~~~

được hiểu là map từ bean name sang các bean kiểu PaymentHandler.

### 10.1. Dùng interface để tập hợp nhiều implementation

Đây là mẫu thiết kế phổ biến:

~~~java
public interface FileExporter {
    String format();
    byte[] export(Object data);
}
~~~

~~~java
@Component
class CsvExporter implements FileExporter {
    public String format() { return "csv"; }
    public byte[] export(Object data) { return new byte[0]; }
}
~~~

~~~java
@Component
class JsonExporter implements FileExporter {
    public String format() { return "json"; }
    public byte[] export(Object data) { return new byte[0]; }
}
~~~

Consumer:

~~~java
public ExportService(List<FileExporter> exporters) {
    this.exporters = exporters;
}
~~~

Spring tập hợp các bean implement interface và phù hợp với generic type. Consumer không cần import CsvExporter hay JsonExporter.

### 10.2. Generic type có thể phân biệt các bean

Spring hỗ trợ generic-aware type matching trong autowiring. Ví dụ một interface generic:

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
        // ...
    }
}
~~~

~~~java
@Component
public class IntegerStore implements Store<Integer> {
    public void save(Integer value) {
        // ...
    }
}
~~~

Injection:

~~~java
public StringStoreConsumer(List<Store<String>> stores) {
    this.stores = stores;
}
~~~

Spring có thể dùng generic metadata để phân biệt **Store<String>** với **Store<Integer>** khi xác định candidate. Điều này hữu ích khi nhiều bean có cùng raw interface nhưng biểu diễn các loại dữ liệu khác nhau.

Generic matching vẫn phụ thuộc metadata kiểu mà Spring có thể suy luận. Nếu implementation dùng raw type, generic bị mất do cấu trúc kế thừa hoặc factory method khai báo kiểu quá rộng, việc phân biệt có thể không đạt như mong muốn. Khi gặp trường hợp đó, hãy kiểm tra chữ ký generic và cân nhắc qualifier tường minh.

## 11. Thứ tự, trùng lặp và cách chọn implementation

Khi nhận nhiều bean, cần quyết định cách consumer sử dụng chúng.

### 11.1. List và @Order

Ví dụ validator:

~~~java
public interface OrderValidator {
    void validate(OrderRequest request);
}
~~~

~~~java
@Component
@Order(10)
class RequiredFieldsValidator implements OrderValidator {
    public void validate(OrderRequest request) {
        // Kiểm tra field bắt buộc.
    }
}
~~~

~~~java
@Component
@Order(20)
class StockValidator implements OrderValidator {
    public void validate(OrderRequest request) {
        // Kiểm tra tồn kho.
    }
}
~~~

~~~java
@Service
class OrderValidationPipeline {
    private final List<OrderValidator> validators;

    OrderValidationPipeline(List<OrderValidator> validators) {
        this.validators = validators;
    }

    void validate(OrderRequest request) {
        validators.forEach(validator -> validator.validate(request));
    }
}
~~~

Trong trường hợp này, thứ tự validation là một phần của behavior, nên annotation order giúp thể hiện ý định.

### 11.2. Map khi cần lookup theo key

Nếu service cần tìm exporter theo format:

~~~java
public FileExporter findExporter(String format) {
    return exporters.stream()
            .filter(exporter -> exporter.format().equalsIgnoreCase(format))
            .findFirst()
            .orElseThrow(() ->
                    new IllegalArgumentException("Format không hỗ trợ"));
}
~~~

Có thể xây dựng map một lần trong constructor:

~~~java
this.exportersByFormat = exporters.stream().collect(
        Collectors.toUnmodifiableMap(
                exporter -> exporter.format().toLowerCase(),
                Function.identity()
        )
);
~~~

Điều này tránh duyệt list mỗi lần tra cứu. Nhưng cần xử lý rõ nếu hai exporter khai báo cùng format, bởi map không thể có hai value cho một key duy nhất theo cách này.

### 11.3. Set khi không cần thứ tự

Nếu chỉ cần biết tập capability, Set có thể diễn đạt tốt:

~~~java
Set<String> supportedFormats = exporters.stream()
        .map(FileExporter::format)
        .collect(Collectors.toUnmodifiableSet());
~~~

Đừng chuyển List sang Set chỉ để “loại trùng” nếu hai bean cùng class nhưng có state/configuration khác nhau; hãy xác định identity và ý nghĩa trùng lặp trước.

## 12. Bean scope và vòng đời của phần tử trong collection

Collection injection không làm thay đổi scope của bean được inject. Nếu một consumer singleton nhận List các singleton bean, các phần tử thường là những instance được dùng lại trong context.

Nếu collection chứa prototype bean, các instance prototype thường được tạo tại thời điểm Spring resolve dependency cho consumer. Một singleton giữ collection đó sẽ tiếp tục giữ các reference đã inject; **Spring không tự tạo prototype mới mỗi lần consumer gọi phương thức**.

Ví dụ:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class WorkUnit {
}
~~~

~~~java
@Service
public class WorkCoordinator {
    private final List<WorkUnit> workUnits;

    public WorkCoordinator(List<WorkUnit> workUnits) {
        this.workUnits = workUnits;
    }
}
~~~

Với WorkCoordinator là singleton, list được resolve khi coordinator được tạo. Các phần tử prototype đã được tạo lúc đó và không tự thay đổi ở mỗi lần gọi.

Nếu cần một instance prototype mới cho mỗi lần xử lý, inject **ObjectProvider<WorkUnit>** và gọi **getObject()** tại thời điểm cần:

~~~java
public class WorkCoordinator {
    private final ObjectProvider<WorkUnit> workUnitProvider;

    public WorkCoordinator(ObjectProvider<WorkUnit> workUnitProvider) {
        this.workUnitProvider = workUnitProvider;
    }

    public void execute() {
        WorkUnit unit = workUnitProvider.getObject();
        // Xử lý unit mới.
    }
}
~~~

Với request/session scoped bean, hãy hiểu thêm scope proxy hoặc provider phù hợp. Collection được inject vào một singleton không tự biến các phần tử request-scoped thành state riêng cho mỗi request nếu cơ chế scope không được sử dụng đúng.

## 13. Collection injection và điều kiện đăng ký bean

Danh sách phần tử phản ánh những bean mà container có thể resolve **trong context và tại thời điểm tạo dependency**.

Một implementation có thể không xuất hiện vì:

- Class không nằm trong component scan.
- Bean configuration chưa được import.
- Profile không active.
- @Conditional hoặc auto-configuration condition không thỏa.
- Dependency chứa class implementation không có trên classpath.
- Bean definition bị loại trừ hoặc đăng ký với kiểu không tương thích.

Ví dụ:

~~~java
@Component
@Profile("production")
public class RealPaymentHandler implements PaymentHandler {
    // ...
}
~~~

~~~java
@Component
@Profile("test")
public class FakePaymentHandler implements PaymentHandler {
    // ...
}
~~~

Khi profile production active, tập candidate sẽ khác với khi profile test active. Collection injection không tự tạo implementation thay thế; nó phản ánh cấu hình bean đang được dùng.

Điều này giúp xây dựng nhiều strategy theo môi trường, nhưng cũng có nghĩa test cần kích hoạt đúng profile nếu muốn kiểm tra tập bean production.

## 14. Kiểm tra collection injection trong test

Một test context có thể xác nhận Spring đã inject đúng các implementation.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class PaymentHandlerInjectionTest {

    @Autowired
    List<PaymentHandler> handlers;

    @Autowired
    Map<String, PaymentHandler> handlersByName;

    @Test
    void injectsAllPaymentHandlers() {
        assertThat(handlers).hasSize(3);
        assertThat(handlersByName)
                .containsKeys(
                        "cardPaymentHandler",
                        "walletPaymentHandler",
                        "bankTransferPaymentHandler"
                );
    }
}
~~~

Đây là ví dụ khi ứng dụng thực sự có ba bean với tên như trên và test context sử dụng component scan phù hợp. Nếu có thêm bean PaymentHandler từ cấu hình khác, số lượng mong đợi phải phản ánh cấu hình đó.

Nếu muốn kiểm tra thứ tự:

~~~java
assertThat(handlers)
        .extracting(PaymentHandler::method)
        .containsExactly("card", "wallet", "bank-transfer");
~~~

Chỉ dùng **containsExactly** khi các implementation có order được định nghĩa rõ. Nếu không có hợp đồng thứ tự, nên kiểm tra nội dung bằng **contains** hoặc so sánh tập giá trị để test không phụ thuộc thứ tự tình cờ.

### 14.1. Kiểm tra qualifier

Test có thể inject một collection với qualifier để xác nhận chỉ nhận nhóm tương ứng:

~~~java
@Autowired
@Qualifier("online")
List<PaymentHandler> onlineHandlers;
~~~

Sau đó kiểm tra tập method hoặc bean name dự kiến. Cách này xác nhận qualifier metadata và cấu hình context cùng hoạt động.

### 14.2. Unit test không có context không kiểm tra được DI

Nếu test viết:

~~~java
PaymentDispatcher dispatcher =
        new PaymentDispatcher(List.of(fakeHandler));
~~~

thì test đang xác nhận logic dispatcher với một List do test tự cung cấp. Nó **không kiểm tra Spring đã tìm thấy bean nào, qualifier có lọc đúng hay @Order có sắp xếp collection không**.

Để kiểm tra wiring, hãy dùng Spring context test. Để kiểm tra logic nghiệp vụ độc lập, constructor injection vẫn giúp unit test nhẹ bằng collection tự tạo.

## 15. Một số lỗi thường gặp

### 15.1. NoSuchBeanDefinitionException khi inject collection

Nguyên nhân thường là không có candidate nào phù hợp với kiểu hoặc qualifier. Kiểm tra:

- Implementation có được đăng ký làm bean không?
- Component scan có bao phủ package không?
- Profile và điều kiện có đang loại bean không?
- Generic type có khớp không?
- Qualifier tại injection point có lọc hết candidate không?

Nếu không có implementation là tình huống hợp lệ, cân nhắc ObjectProvider thay vì dependency collection bắt buộc.

### 15.2. NoUniqueBeanDefinitionException khi inject một bean đơn

Nếu constructor nhận **PaymentHandler** đơn mà context có ba bean, Spring không biết chọn cái nào nếu không có candidate ưu tiên hoặc qualifier phù hợp. Đổi sang **List<PaymentHandler>** nếu thật sự cần tất cả; dùng @Primary/@Qualifier nếu chỉ cần một.

### 15.3. Map không có key như mong đợi

Map collection injection dùng **bean name** làm key. Nếu bean được khai báo bằng @Component("card") thì key là **card**, không phải tên class hay kết quả method().

Kiểm tra tên bean qua context hoặc Actuator thay vì tự suy luận.

### 15.4. Thứ tự List thay đổi

Nếu chưa khai báo @Order/Ordered, đừng dựa vào thứ tự đăng ký. Hãy định nghĩa thứ tự rõ nếu behavior cần nó. Nếu collection là Set, không dùng iteration order làm hợp đồng.

### 15.5. @Primary làm mất các phần tử khác?

Không. @Primary phục vụ lựa chọn một candidate cho dependency đơn; collection injection vẫn hướng đến tất cả candidate phù hợp. Dùng qualifier để lọc nhóm.

### 15.6. Bean prototype không mới ở mỗi lần gọi

Khi prototype được inject vào singleton collection, instance được resolve khi singleton được tạo. Dùng ObjectProvider để lấy instance mới khi cần.

### 15.7. Hai implementation trùng một mã nghiệp vụ

Nếu hai handler cùng trả về method **"card"**, việc tìm phần tử đầu tiên trong List có thể phụ thuộc thứ tự. Nên xác định đây là cấu hình hợp lệ hay lỗi đăng ký trùng. Có thể tạo registry Map theo method và fail-fast khi phát hiện key trùng.

### 15.8. Collection có bean từ auto-configuration ngoài dự kiến

Một starter có thể đăng ký implementation mặc định. Khi collection đột nhiên có thêm phần tử, xem bean name, nguồn definition và condition report. Nếu bean mặc định được thiết kế để back off, hãy kiểm tra điều kiện @ConditionalOnMissingBean; nếu cần, tùy chỉnh hoặc loại cấu hình theo cơ chế được hỗ trợ.

## 16. Khi nào chọn List, Set, Map hoặc ObjectProvider?

| Nhu cầu | Lựa chọn gợi ý | Vì sao |
|---|---|---|
| Chạy tất cả strategy theo thứ tự | **List<T>** | Có thể sắp xếp qua @Order/Ordered. |
| Lưu tập capability, không phụ thuộc thứ tự | **Set<T>** | Thể hiện tập phần tử. |
| Tra cứu bằng tên bean | **Map<String, T>** | Key là bean name. |
| Chỉ nhận một nhóm bean có qualifier | **@Qualifier + List/Set/Map** | Lọc candidate theo metadata. |
| Một bean có thể vắng mặt | **Optional<T>** hoặc **ObjectProvider<T>** | Biểu đạt dependency tùy chọn. |
| Nhiều bean có thể vắng mặt, cần danh sách rỗng | **ObjectProvider<T>.orderedStream()** | Truy vấn theo nhu cầu, có thể trả stream rỗng. |
| Cần instance prototype mới mỗi lần | **ObjectProvider<T>** | Yêu cầu bean tại thời điểm sử dụng. |
| Cần một implementation duy nhất | **T + @Primary/@Qualifier** | Chọn một candidate rõ ràng. |

Không có collection nào tốt nhất trong mọi trường hợp. Hãy chọn kiểu dữ liệu thể hiện đúng cách consumer sẽ sử dụng tập bean.

## 17. Các nguyên tắc thiết kế khi mở rộng hệ thống bằng nhiều bean

Khi xây dựng một module có thể thêm implementation về sau, nên:

1. **Định nghĩa interface ổn định** cho vai trò mà consumer cần.
2. **Đăng ký từng implementation rõ ràng** qua component scanning hoặc @Bean.
3. **Inject interface collection** thay vì liệt kê từng implementation trong constructor.
4. **Dùng @Order khi thứ tự có ý nghĩa**; không dựa vào thứ tự ngẫu nhiên.
5. **Dùng qualifier cho nhóm có ý nghĩa** như online/offline hoặc primary/backup.
6. **Dùng Map<String, T> khi key là bean name**, và tự xây registry khác khi key là dữ liệu nghiệp vụ.
7. **Xác định behavior khi không có candidate**, dùng ObjectProvider nếu collection rỗng là trường hợp hợp lệ.
8. **Chú ý scope và mutable state**, nhất là khi singleton chứa collection các bean dùng chung.
9. **Test wiring trong Spring context**, và unit test logic consumer bằng collection giả khi cần.
10. **Tránh đăng ký trùng implementation ngoài ý muốn**, đặc biệt khi vừa component scan vừa khai báo @Bean.

## 18. Những hiểu nhầm thường gặp

**“Inject List<T> chỉ lấy một bean được đánh dấu @Primary.”**  
Không. Collection injection có mục đích thu thập các candidate phù hợp; @Primary chủ yếu giải quyết lựa chọn cho dependency đơn.

**“Set<T> tự sắp xếp theo @Order.”**  
Không nên dựa vào thứ tự iteration của Set. Dùng List khi thứ tự là một phần của behavior.

**“Map<String, T> dùng tên method() của bean làm key.”**  
Không. Key là bean name trong context. Nếu muốn key theo nghiệp vụ, hãy tự xây registry.

**“Thêm implementation mới là nó chắc chắn tự xuất hiện trong collection.”**  
Chỉ khi implementation được đăng ký thành bean và thỏa các điều kiện/profile/qualifier của injection point.

**“Không có candidate thì Spring luôn inject collection rỗng.”**  
Không nên giả định như vậy cho dependency bắt buộc. Nếu không có bean là trường hợp hợp lệ, dùng cơ chế optional rõ ràng như ObjectProvider.

**“@Qualifier chỉ chọn một bean.”**  
Qualifier có thể lọc tập candidate ở collection injection; nó không nhất thiết giới hạn kết quả còn một phần tử.

**“@Order quyết định thứ tự khởi tạo bean.”**  
Không. Nó hỗ trợ sắp xếp ở các điểm injection collection có thứ tự; startup order là vấn đề lifecycle khác.

**“Prototype bean trong List được tạo lại mỗi lần gọi service.”**  
Không. Collection đã inject vào singleton giữ những reference được resolve lúc singleton tạo. Dùng ObjectProvider nếu cần instance mới theo từng lần sử dụng.

**“Inject collection nghĩa collection đó là bean.”**  
Không nhất thiết. Collection là dependency value được Spring tổng hợp từ các bean phần tử. Bản thân List/Set/Map được inject không đồng nghĩa nó có bean definition riêng.

## Ghi nhớ cốt lõi

Spring có thể inject nhiều bean cùng kiểu dưới dạng **List<T>**, **Set<T>** hoặc **Map<String, T>**. **List** phù hợp khi cần duyệt theo thứ tự được cấu hình; **Set** biểu diễn tập không phụ thuộc thứ tự; **Map<String, T>** cho phép tra cứu theo bean name. Qualifier giúp lọc nhóm, còn @Primary chủ yếu chọn một candidate khi dependency là đơn.

Collection chỉ chứa những bean đã được đăng ký và phù hợp với kiểu, qualifier, profile và điều kiện trong context. Nếu không có implementation là tình huống hợp lệ, dùng ObjectProvider để truy vấn theo nhu cầu và xử lý collection rỗng một cách rõ ràng. Khi hiểu đúng cách Spring resolve collection, bạn có thể xây dựng hệ thống plugin/strategy mở rộng được mà consumer không phải phụ thuộc vào từng implementation cụ thể.
