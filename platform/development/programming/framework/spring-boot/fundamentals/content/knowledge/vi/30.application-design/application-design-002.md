# Thiết kế constructor để biểu lộ dependency bắt buộc

Một Spring bean thường cần những đối tượng khác để thực hiện nhiệm vụ: service cần repository, controller cần service, publisher cần message client, hoặc một module cần clock và policy dùng chung. Cách khai báo các dependency này ảnh hưởng trực tiếp đến việc class có dễ hiểu, dễ kiểm thử và dễ khởi tạo hay không.

**Constructor injection** đặt các dependency bắt buộc ngay trong constructor. Người đọc nhìn vào chữ ký constructor có thể biết object cần gì để tồn tại hợp lệ; Spring cũng biết phải cung cấp những bean nào trước khi tạo object.

Ví dụ:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final PaymentService paymentService;

    public OrderService(
            OrderRepository orderRepository,
            PaymentService paymentService) {
        this.orderRepository = orderRepository;
        this.paymentService = paymentService;
    }
}
~~~

Từ constructor này có thể đọc được hợp đồng của `OrderService`: không thể tạo service nếu thiếu `OrderRepository` hoặc `PaymentService`. Hai field là `final` nên dependency không thể bị thay thế tùy tiện sau khi object được tạo.

Bài học tập trung vào cách thiết kế constructor để phân biệt dependency bắt buộc và tùy chọn, vì sao constructor injection thường phù hợp hơn field/setter injection cho dependency cốt lõi, cách Spring giải quyết constructor, xử lý nhiều ứng viên, tránh circular dependency và kiểm thử class mà không cần khởi động toàn bộ ứng dụng.

## 1. Dependency là một phần của hợp đồng object

Một object chỉ nên được tạo khi các điều kiện cần thiết để nó hoạt động đã được đáp ứng.

Giả sử một service tính giá đơn hàng luôn cần một bộ quy tắc thuế:

~~~java
public class OrderPricingService {

    private final TaxPolicy taxPolicy;

    public OrderPricingService(TaxPolicy taxPolicy) {
        this.taxPolicy = taxPolicy;
    }

    public Money calculate(Order order) {
        return taxPolicy.calculate(order);
    }
}
~~~

`TaxPolicy` không phải một tiện ích có thể bỏ qua. Nếu thiếu policy, service không thể tính giá đúng. Đặt nó trong constructor làm điều đó trở thành một điều kiện tạo object.

So sánh với một class có field injection:

~~~java
@Service
public class OrderPricingService {

    @Autowired
    private TaxPolicy taxPolicy;

    public Money calculate(Order order) {
        return taxPolicy.calculate(order);
    }
}
~~~

Khi đọc constructor mặc định (do Java tự sinh), người khác không thấy `TaxPolicy` là dependency. Object có thể được tạo bằng `new OrderPricingService()` nhưng chưa có dependency; chỉ sau khi Spring xử lý field injection, field mới được gán. Điều này làm class phụ thuộc nhiều hơn vào lifecycle container và khó tạo đúng trạng thái bên ngoài Spring.

**Hợp đồng tạo object nên thể hiện các dependency mà object không thể hoạt động nếu thiếu.**

## 2. Constructor injection hoạt động như thế nào trong Spring?

Spring IoC container tạo bean bằng cách tìm bean definitions và giải quyết các dependency cần thiết. Với constructor injection, các tham số constructor là những dependency cần được resolve trước khi gọi constructor.

~~~text
ApplicationContext
       |
       v
Cần tạo OrderService
       |
       v
Đọc constructor parameters
       |
       +----------------------+
       |                      |
       v                      v
OrderRepository          PaymentService
       |                      |
       v                      v
Resolve bean             Resolve bean
       |                      |
       +----------+-----------+
                  |
                  v
     Gọi new OrderService(repo, payment)
                  |
                  v
        Object đã có dependency
                  |
                  v
          Bean được quản lý
~~~

Nếu một dependency bắt buộc không tồn tại hoặc có nhiều candidate mà Spring không thể chọn, quá trình tạo bean thất bại. Đây là lợi ích quan trọng: lỗi wiring thường được phát hiện lúc khởi động, trước khi request đầu tiên đi vào service.

### 2.1. Constructor injection không phải tự tạo dependency

Spring vẫn chịu trách nhiệm tìm và cung cấp bean. Constructor chỉ khai báo object cần gì:

~~~java
public OrderService(
        OrderRepository repository,
        PaymentService paymentService) {
    this.repository = repository;
    this.paymentService = paymentService;
}
~~~

Code không cần tự gọi:

~~~java
new OrderRepository();
new PaymentService();
~~~

Các dependency có thể cần proxy, transaction, configuration, lifecycle callback hoặc những bean khác. Để Spring tạo và inject chúng giúp giữ đúng container lifecycle.

### 2.2. Một constructor duy nhất thường không cần @Autowired

Từ Spring Framework 4.3, nếu bean class chỉ có một constructor, Spring tự sử dụng constructor đó để inject dependency. Ví dụ:

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
~~~

Không cần thêm `@Autowired` trên constructor duy nhất:

~~~java
// Không bắt buộc nếu đây là constructor duy nhất.
@Autowired
public OrderService(OrderRepository repository) {
    this.repository = repository;
}
~~~

Có thể giữ annotation nếu dự án có convention riêng, nhưng thường constructor duy nhất đã đủ rõ ràng.

## 3. Dependency bắt buộc: đặt trong constructor

Một dependency nên được xem là bắt buộc khi class không thể thực hiện trách nhiệm chính nếu thiếu nó.

Ví dụ:

~~~java
@Service
public class InvoiceService {

    private final InvoiceRepository invoiceRepository;
    private final TaxCalculator taxCalculator;
    private final Clock clock;

    public InvoiceService(
            InvoiceRepository invoiceRepository,
            TaxCalculator taxCalculator,
            Clock clock) {
        this.invoiceRepository = invoiceRepository;
        this.taxCalculator = taxCalculator;
        this.clock = clock;
    }
}
~~~

Ba dependency này đều là thành phần cốt lõi:

- Repository đọc và lưu hóa đơn.
- Tax calculator tính nghĩa vụ thuế.
- Clock cung cấp thời điểm hiện tại theo một abstraction có thể kiểm thử.

Nếu một trong các bean này không được cấu hình, Spring không thể tạo `InvoiceService`. Đây thường là hành vi đúng hơn việc cho phép service tồn tại rồi chỉ thất bại khi một method được gọi.

### 3.1. Dùng final cho dependency sau khi inject

~~~java
private final InvoiceRepository invoiceRepository;
~~~

`final` đảm bảo field phải được gán trong constructor và không thể gán lại sau đó. Điều này không làm object bất biến hoàn toàn nếu dependency bản thân mutable, nhưng nó bảo vệ cấu trúc tham chiếu của service.

Một service thường không cần setter để thay repository hoặc payment client sau khi khởi tạo. Nếu cần thay đổi cấu hình runtime, hãy thiết kế cơ chế thay đổi state riêng có đồng bộ và lifecycle rõ ràng, thay vì mở setter cho mọi dependency.

### 3.2. Kiểm tra null và invariant

Spring thông thường không truyền `null` cho dependency bắt buộc nếu không có bean phù hợp. Tuy vậy, class có thể được tạo thủ công trong unit test hoặc code khác. Có thể kiểm tra invariant ngay trong constructor:

~~~java
public InvoiceService(InvoiceRepository repository) {
    this.invoiceRepository = Objects.requireNonNull(repository);
}
~~~

Với nhiều field, dùng constructor gán trực tiếp thường đủ; thêm `Objects.requireNonNull` khi nó giúp hợp đồng class rõ ràng hoặc class có thể được khởi tạo từ nhiều nơi.

Không nên biến constructor thành nơi thực hiện logic nghiệp vụ, truy vấn database hoặc gọi dịch vụ ngoài. Constructor nên nhận dependency, xác nhận tham số và thiết lập state ban đầu.

## 4. Dependency tùy chọn không nên giả làm dependency bắt buộc

Không phải mọi dependency đều luôn có mặt. Ví dụ một service có thể gửi thông báo nếu có notifier, nhưng tính toán đơn hàng vẫn hoạt động khi không bật tính năng thông báo.

Nếu dependency thật sự tùy chọn, hãy biểu đạt optionality trong chữ ký hoặc cấu trúc thiết kế.

### 4.1. Dùng Optional<T> khi vắng mặt là trường hợp hợp lệ

~~~java
@Service
public class OrderSummaryService {

    private final Optional<PromotionBanner> promotionBanner;

    public OrderSummaryService(
            Optional<PromotionBanner> promotionBanner) {
        this.promotionBanner = promotionBanner;
    }

    public Summary summarize(Order order) {
        Summary summary = Summary.from(order);

        promotionBanner.ifPresent(
                banner -> banner.attachTo(summary)
        );

        return summary;
    }
}
~~~

Spring hỗ trợ inject `Optional<T>` tại dependency injection point. Nếu không có bean phù hợp, Optional có thể rỗng; nếu có nhiều candidate mà không thể chọn duy nhất, ambiguity vẫn cần được giải quyết.

`Optional` giúp caller thấy rõ rằng dependency có thể vắng mặt. Không nên dùng Optional cho dependency cốt lõi chỉ để tránh lỗi startup.

### 4.2. Dùng ObjectProvider<T> khi cần truy vấn linh hoạt hoặc lazy

~~~java
@Service
public class ReportService {

    private final ObjectProvider<ReportExporter> exporterProvider;

    public ReportService(
            ObjectProvider<ReportExporter> exporterProvider) {
        this.exporterProvider = exporterProvider;
    }

    public void exportIfConfigured(Report report) {
        ReportExporter exporter =
                exporterProvider.getIfAvailable();

        if (exporter != null) {
            exporter.export(report);
        }
    }
}
~~~

`ObjectProvider<T>` hữu ích khi:

- Bean có thể không tồn tại.
- Muốn trì hoãn việc resolve cho đến khi cần.
- Cần truy vấn một candidate tại thời điểm sử dụng.
- Cần duyệt nhiều candidate qua `stream()` hoặc `orderedStream()`.

Nó không tự giải quyết ambiguity. Nếu có nhiều candidate không phân biệt được, `getIfAvailable()` vẫn có thể ném lỗi không unique.

### 4.3. Dùng @Nullable khi null là một phần hợp đồng

Một số hệ thống dùng annotation `@Nullable` để biểu đạt tham số có thể nhận null:

~~~java
public OrderService(
        OrderRepository repository,
        @Nullable PromotionPolicy promotionPolicy) {
    this.repository = repository;
    this.promotionPolicy = promotionPolicy;
}
~~~

Cách xử lý chính xác phụ thuộc annotation package và Spring version. Nếu dùng null, code phải xử lý nó rõ ràng ở mọi nơi. Trong nhiều trường hợp, `Optional` hoặc một implementation mặc định sẽ thể hiện ý định tốt hơn.

### 4.4. Đừng dùng default null cho một dependency bắt buộc

Ví dụ:

~~~java
public OrderService(OrderRepository repository) {
    this.repository = repository;
}
~~~

Nếu service không thể làm việc mà không có repository, không nên tạo một constructor khác nhận null hoặc dùng `@Autowired(required = false)` để ứng dụng vẫn khởi động. Điều đó chỉ trì hoãn lỗi đến runtime và khiến object ở trạng thái không hợp lệ.

## 5. Dependency tùy chọn có thể được thay bằng implementation mặc định

Nếu một chức năng nên luôn có thể gọi nhưng hành vi mặc định là “không làm gì”, có thể cung cấp Null Object/No-op implementation.

~~~java
public interface NotificationSender {
    void send(OrderPlaced event);
}
~~~

~~~java
@Component
public class NoopNotificationSender implements NotificationSender {

    @Override
    public void send(OrderPlaced event) {
        // Không gửi thông báo.
    }
}
~~~

~~~java
@Component
@Primary
public class EmailNotificationSender implements NotificationSender {

    @Override
    public void send(OrderPlaced event) {
        // Gửi email.
    }
}
~~~

Service luôn nhận một `NotificationSender`:

~~~java
@Service
public class OrderNotificationService {

    private final NotificationSender sender;

    public OrderNotificationService(NotificationSender sender) {
        this.sender = sender;
    }
}
~~~

Tuy nhiên, chỉ dùng No-op nếu im lặng không thực hiện hành động là behavior hợp lệ. Với thanh toán, authorization hoặc lưu dữ liệu bắt buộc, một implementation no-op có thể che giấu lỗi nghiêm trọng. Dependency mặc định phải phản ánh chính sách nghiệp vụ, không chỉ giúp context khởi động.

## 6. Constructor injection và setter injection khác nhau thế nào?

Spring hỗ trợ nhiều kiểu dependency injection. Mỗi kiểu có ý nghĩa thiết kế khác nhau.

### Constructor injection

~~~java
@Service
public class CatalogService {

    private final CatalogRepository repository;

    public CatalogService(CatalogRepository repository) {
        this.repository = repository;
    }
}
~~~

Dùng khi dependency là bắt buộc để object hoạt động.

### Setter injection

~~~java
@Component
public class CatalogFormatter {

    private Locale locale = Locale.ROOT;

    @Autowired
    public void setLocaleProvider(LocaleProvider provider) {
        this.locale = provider.defaultLocale();
    }
}
~~~

Setter injection có thể phù hợp khi dependency thực sự tùy chọn, có thể thay đổi sau khi object được tạo hoặc cần cấu hình theo một quy trình riêng. Tuy nhiên, setter công khai cho dependency cốt lõi khiến object có thể tồn tại trong trạng thái chưa hoàn chỉnh hoặc bị thay đổi sau khởi tạo.

### Field injection

~~~java
@Service
public class CatalogService {

    @Autowired
    private CatalogRepository repository;
}
~~~

Field injection ngắn nhưng có nhược điểm:

- Dependency không xuất hiện trong constructor/API tạo object.
- Field thường không thể là `final`.
- Unit test phải dùng reflection, Spring test context hoặc cơ chế inject riêng.
- Object có thể được tạo bằng `new` nhưng dependency chưa được gán.
- Class gắn chặt hơn với Spring annotation/infrastructure.

### So sánh

| Tiêu chí | Constructor | Setter | Field |
|---|---|---|---|
| Biểu lộ dependency bắt buộc | Rất rõ | Ít rõ hơn | Khó thấy từ API |
| Có thể dùng final field | Có | Không với setter thông thường | Không |
| Object hoàn chỉnh ngay sau constructor | Có, nếu constructor đúng | Có thể chưa | Không trước injection |
| Unit test bằng new | Dễ | Có thể cần gọi setter | Khó nếu không có injection |
| Phù hợp với optional dependency | Có, qua Optional/Provider | Có thể phù hợp | Có thể, nhưng ít rõ |
| Khả năng tạo circular dependency | Constructor cycle thường bị phát hiện | Có thể che một số cycle | Có thể che một số cycle |
| Khuyến nghị cho dependency cốt lõi | Thường ưu tiên | Chỉ khi có lý do | Thường tránh |

Không phải mọi setter injection đều sai. Vấn đề là dùng setter/field cho dependency mà class không thể hoạt động nếu thiếu.

## 7. Thiết kế constructor duy nhất cho dependency cốt lõi

Một bean thông thường nên có một constructor mô tả đầy đủ dependency cần thiết:

~~~java
@Service
public class CheckoutService {

    private final CartRepository cartRepository;
    private final PaymentGateway paymentGateway;
    private final OrderRepository orderRepository;
    private final Clock clock;

    public CheckoutService(
            CartRepository cartRepository,
            PaymentGateway paymentGateway,
            OrderRepository orderRepository,
            Clock clock) {
        this.cartRepository = cartRepository;
        this.paymentGateway = paymentGateway;
        this.orderRepository = orderRepository;
        this.clock = clock;
    }
}
~~~

Khi có một constructor duy nhất, Spring tự dùng nó để inject; không cần `@Autowired`.

Constructor dài có thể là tín hiệu class có quá nhiều trách nhiệm. Không nên giải quyết bằng cách chuyển một nửa dependency sang field injection. Hãy xem xét:

- Class có đang điều phối nhiều use case không liên quan?
- Có thể tách một nhóm hành vi thành collaborator có trách nhiệm rõ ràng không?
- Dependency có thực sự cần thiết hay chỉ được dùng trong một nhánh hiếm?
- Có đang inject nhiều repository riêng lẻ khi một domain service/facade có thể thể hiện hợp đồng tốt hơn không?

Không nên tạo một “GodService” hoặc một object chứa 15 dependency chỉ để giảm số dòng code. Cũng không nên chia class thành nhiều bean nhỏ vô nghĩa chỉ để constructor ngắn. Hãy để trách nhiệm nghiệp vụ quyết định ranh giới.

### 7.1. Đừng gom dependency vào một service locator

Ví dụ:

~~~java
@Service
public class CheckoutService {

    private final ApplicationContext context;

    public CheckoutService(ApplicationContext context) {
        this.context = context;
    }

    public void checkout() {
        PaymentGateway gateway =
                context.getBean(PaymentGateway.class);
        // ...
    }
}
~~~

Constructor chỉ thể hiện `ApplicationContext`, trong khi dependency thực tế bị ẩn trong method. Việc này làm lỗi wiring có thể chỉ xuất hiện khi method chạy và khiến unit test phải dựng container hoặc mock service locator.

Ưu tiên inject dependency cụ thể:

~~~java
public CheckoutService(PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Nếu thật sự cần chọn giữa nhiều implementation lúc runtime, inject `List<PaymentGateway>` hoặc `Map<String, PaymentGateway>` rồi xây một registry có business key rõ ràng.

## 8. Khi class có nhiều constructor

Một class Java có thể khai báo nhiều constructor để phục vụ các cách tạo object khác nhau. Nhưng Spring cần biết constructor nào dùng để tạo bean.

### 8.1. Một constructor duy nhất

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }
}
~~~

Spring tự chọn constructor duy nhất.

### 8.2. Nhiều constructor và đánh dấu constructor injection

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;
    private final Clock clock;

    @Autowired
    public CustomerService(
            CustomerRepository repository,
            Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    public CustomerService(CustomerRepository repository) {
        this(repository, Clock.systemUTC());
    }
}
~~~

Ở đây constructor có `@Autowired` biểu thị constructor mà Spring sử dụng. Constructor phụ có thể hữu ích cho một mục đích tạo object riêng, nhưng trong Spring bean, việc có nhiều cách tạo có thể khiến contract khó hiểu.

Trong ứng dụng thực tế, nếu constructor phụ chỉ phục vụ unit test, thường có thể tạo test bằng cách truyền mock và clock vào constructor chính thay vì giữ một constructor production có default ngầm.

### 8.3. Khi có nhiều constructor, đừng trông chờ Spring đoán theo số tham số

Quy tắc chọn constructor có thể phụ thuộc annotation, constructor mặc định và khả năng resolve tham số theo phiên bản Spring. Đối với bean cần dependency bắt buộc, hãy khai báo rõ constructor được dùng bằng `@Autowired` khi class có nhiều lựa chọn và kiểm thử context thật.

Không nên tạo nhiều constructor có tham số cùng khả năng được chọn rồi hy vọng Spring luôn chọn constructor “nhiều dependency nhất”.

## 9. Lombok và constructor injection

Lombok có thể sinh constructor từ các field cần thiết:

~~~java
@Service
@RequiredArgsConstructor
public class OrderService {

    private final OrderRepository repository;
    private final PaymentService paymentService;
}
~~~

`@RequiredArgsConstructor` tạo constructor cho các field `final` và những field được đánh dấu `@NonNull` theo quy tắc Lombok. Spring có thể dùng constructor duy nhất được sinh ra mà không cần `@Autowired`.

### 9.1. Cẩn thận với @AllArgsConstructor

~~~java
@AllArgsConstructor
@Service
public class OrderService {
    private final OrderRepository repository;
    private String lastStatus;
}
~~~

`@AllArgsConstructor` có thể đưa cả những field không phải dependency vào constructor. Điều đó làm chữ ký tạo bean phụ thuộc vào state nội bộ hoặc field không nên được Spring inject.

Với service, `@RequiredArgsConstructor` thường phù hợp hơn nếu dự án đã dùng Lombok và các dependency được khai báo final.

### 9.2. Annotation @NonNull và null checks

Lombok có thể sinh null check cho field `@NonNull` trong constructor. Nhưng đừng dùng annotation này thay thế thiết kế optionality. Nếu dependency có thể vắng mặt, biểu đạt nó bằng `Optional<T>`, `ObjectProvider<T>` hoặc một implementation mặc định phù hợp.

### 9.3. Constructor sinh tự động vẫn cần đọc được

Dù constructor không viết trực tiếp, reviewer cần nhìn thấy các dependency qua field final. Nếu một class có nhiều loại state, field không phải dependency và nhiều annotation Lombok cùng lúc, constructor thực tế có thể khó dự đoán. Khi contract quan trọng hoặc phức tạp, constructor tường minh đôi khi dễ đọc hơn.

## 10. Inject collection khi class cần nhiều implementation

Một dependency bắt buộc không nhất thiết là một object đơn. Có thể service cần tất cả handler đã đăng ký.

~~~java
public interface ExportHandler {
    boolean supports(ExportFormat format);
    void export(Report report);
}
~~~

~~~java
@Component
public class PdfExportHandler implements ExportHandler {
    // ...
}
~~~

~~~java
@Component
public class CsvExportHandler implements ExportHandler {
    // ...
}
~~~

Registry nhận tất cả:

~~~java
@Component
public class ExportHandlerRegistry {

    private final List<ExportHandler> handlers;

    public ExportHandlerRegistry(List<ExportHandler> handlers) {
        this.handlers = List.copyOf(handlers);
    }

    public ExportHandler get(ExportFormat format) {
        return handlers.stream()
                .filter(handler -> handler.supports(format))
                .findFirst()
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Unsupported format: " + format));
    }
}
~~~

Trong trường hợp này, dependency bắt buộc là **tập handler**. Nếu không có handler nào, constructor vẫn nhận một list rỗng theo cơ chế collection injection thông thường; nếu ít nhất một handler là điều kiện bắt buộc, hãy kiểm tra invariant trong constructor hoặc lúc khởi động.

Nếu thứ tự có ý nghĩa, có thể dùng `@Order` trên handler hoặc một quy tắc sắp xếp tường minh. Nếu nhiều handler cùng hỗ trợ một format, cần quyết định cách xử lý duplicate thay vì lấy phần tử đầu theo thứ tự không xác định.

## 11. Qualifier khi có nhiều bean cùng type

Nếu constructor yêu cầu một bean đơn:

~~~java
public CheckoutService(PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

nhưng context có nhiều `PaymentGateway`, Spring có thể ném `NoUniqueBeanDefinitionException`.

Hãy biểu đạt lựa chọn trong constructor:

~~~java
@Service
public class BankCheckoutService {

    private final PaymentGateway gateway;

    public BankCheckoutService(
            @Qualifier("bankPaymentGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Hoặc đánh dấu một bean mặc định bằng `@Primary` nếu phần lớn injection thực sự cần cùng default.

Constructor injection không loại bỏ ambiguity; nó làm ambiguity xuất hiện ngay ở điểm dependency được khai báo. Điều đó giúp người đọc xác định chính xác service nào cần lựa chọn nào.

### 11.1. Qualifier tùy chỉnh cho contract rõ hơn

Nếu nhiều module cần cùng loại lựa chọn, có thể tạo custom qualifier annotation:

~~~java
@Target({ElementType.FIELD, ElementType.PARAMETER, ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface Domestic {
}
~~~

~~~java
@Component
@Domestic
public class DomesticPaymentGateway implements PaymentGateway {
}
~~~

~~~java
public BankCheckoutService(@Domestic PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Custom qualifier giúp tránh lặp string và thể hiện vai trò của dependency trong API constructor.

## 12. Constructor injection giúp phát hiện circular dependency

Một circular dependency xảy ra khi các bean phụ thuộc vòng tròn vào nhau.

Ví dụ:

~~~java
@Service
public class OrderService {

    public OrderService(PaymentService paymentService) {
    }
}
~~~

~~~java
@Service
public class PaymentService {

    public PaymentService(OrderService orderService) {
    }
}
~~~

Sơ đồ:

~~~text
OrderService
     |
     v
PaymentService
     |
     v
OrderService
~~~

Spring không thể hoàn tất việc tạo bean nào trước vì mỗi constructor đều cần bean còn lại. Thường context thất bại với lỗi liên quan đến circular reference hoặc bean currently in creation.

### 12.1. Vì sao không nên đổi một constructor thành setter chỉ để né lỗi?

Setter/field injection có thể cho phép một số singleton circular references được giải quyết bằng việc tạo object trước rồi inject property sau, tùy cấu hình và lifecycle. Nhưng việc đó che giấu vòng phụ thuộc trong thiết kế.

Spring Boot từ 2.6 mặc định không cho phép circular references trong cấu hình thông thường. Có thể thay đổi hành vi qua `spring.main.allow-circular-references` ở những phiên bản hỗ trợ, nhưng đây không phải giải pháp kiến trúc ưu tiên.

Thay vì bật circular references hoặc chuyển dependency sang field, hãy phá vòng:

- Trích xuất một service thứ ba chứa logic chung.
- Đưa abstraction/event ra giữa hai service.
- Xác định lại chiều phụ thuộc giữa domain và application layer.
- Dùng một coordinator điều phối hai collaborator, thay vì để chúng gọi lẫn nhau.

### 12.2. Ví dụ tách trách nhiệm

~~~java
@Service
public class PaymentService {

    private final PaymentRepository repository;

    public PaymentService(PaymentRepository repository) {
        this.repository = repository;
    }
}
~~~

~~~java
@Service
public class OrderService {

    private final PaymentService paymentService;
    private final OrderRepository orderRepository;

    public OrderService(
            PaymentService paymentService,
            OrderRepository orderRepository) {
        this.paymentService = paymentService;
        this.orderRepository = orderRepository;
    }
}
~~~

Nếu `PaymentService` cần thông báo order đã thanh toán, có thể publish domain/application event hoặc gọi một abstraction có chiều phụ thuộc phù hợp, thay vì inject ngược `OrderService` vào nó.

## 13. Dependency có scope khác nhau và thời điểm resolve

Constructor injection resolve dependency khi bean được tạo. Điều này có ý nghĩa khi dependency có scope khác singleton.

Ví dụ một singleton inject prototype bean trực tiếp:

~~~java
@Service
public class ReportService {

    private final ReportSession session;

    public ReportService(ReportSession session) {
        this.session = session;
    }
}
~~~

Nếu `ReportService` là singleton và `ReportSession` là prototype, prototype instance thường được tạo tại thời điểm singleton được tạo và giữ trong field. Nó không tự tạo instance mới mỗi lần gọi method.

Nếu thật sự cần một prototype mới mỗi lần, có thể inject `ObjectProvider<ReportSession>`:

~~~java
@Service
public class ReportService {

    private final ObjectProvider<ReportSession> sessions;

    public ReportService(ObjectProvider<ReportSession> sessions) {
        this.sessions = sessions;
    }

    public void generate() {
        ReportSession session = sessions.getObject();
        session.generate();
    }
}
~~~

`ObjectProvider` là dependency được khai báo trong constructor; việc resolve instance cụ thể được trì hoãn đến lúc gọi `getObject()`.

Với request-scoped/session-scoped bean, cần hiểu proxy/scope semantics của Spring Web. Không nên inject một object có vòng đời ngắn vào singleton rồi giả định nó tự thay đổi theo request nếu không có scoped proxy hoặc provider phù hợp.

## 14. Constructor injection và @Configuration

Trong một configuration class, tham số của phương thức `@Bean` cũng là dependency mà Spring cần resolve:

~~~java
@Configuration(proxyBeanMethods = false)
public class BillingConfiguration {

    @Bean
    BillingService billingService(
            InvoiceRepository repository,
            TaxCalculator calculator) {
        return new BillingService(repository, calculator);
    }
}
~~~

Ở đây Spring gọi factory method với các bean tương ứng. Constructor của `BillingService` vẫn có thể thể hiện hợp đồng:

~~~java
public class BillingService {

    private final InvoiceRepository repository;
    private final TaxCalculator calculator;

    public BillingService(
            InvoiceRepository repository,
            TaxCalculator calculator) {
        this.repository = repository;
        this.calculator = calculator;
    }
}
~~~

Nếu class được đăng ký bằng `@Service` hoặc `@Component`, container dùng constructor của class. Nếu object được tạo bằng `@Bean` factory method, Spring dùng tham số của factory method để resolve dependency trước khi gọi method.

Không cần inject `ApplicationContext` vào configuration class chỉ để tự tìm các bean mà method đã có thể khai báo qua tham số.

## 15. Phân biệt constructor injection với @ConfigurationProperties constructor binding

Hai cơ chế đều sử dụng constructor, nhưng mục đích khác nhau.

### Constructor injection của Spring

~~~java
@Service
public class PaymentService {

    private final PaymentGateway gateway;

    public PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Spring tìm một bean `PaymentGateway` rồi truyền vào constructor.

### Constructor binding của Spring Boot

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        URI endpoint,
        Duration timeout) {
}
~~~

Spring Boot Binder đọc các property như `app.payment.endpoint` và `app.payment.timeout` rồi tạo object cấu hình.

Sau đó service có thể nhận properties bean bằng constructor injection:

~~~java
@Service
public class PaymentService {

    private final PaymentProperties properties;

    public PaymentService(PaymentProperties properties) {
        this.properties = properties;
    }
}
~~~

Sơ đồ:

~~~text
application.yml
      |
      v
Spring Boot Binder
      |
      v
PaymentProperties bean
      |
      v
Spring dependency injection
      |
      v
PaymentService constructor
~~~

Không nhầm constructor của properties class là nơi để inject `PaymentGateway`, `DataSource` hoặc business service. Properties class nên là dữ liệu cấu hình; service mới là nơi nhận cả cấu hình và collaborator cần thiết.

## 16. Không thực hiện công việc nặng trong constructor

Constructor nên tạo một object ở trạng thái hợp lệ, không nên khởi chạy toàn bộ nghiệp vụ.

Tránh:

~~~java
@Service
public class CatalogService {

    public CatalogService(CatalogRepository repository) {
        repository.findAll();       // I/O trong constructor
        remoteClient.warmUp();      // Gọi mạng trong constructor
        startBackgroundThread();    // Tạo thread trong constructor
    }
}
~~~

Các side effect trong constructor gây khó khăn:

- Unit test phải mock nhiều thứ chỉ để tạo object.
- Startup có thể thất bại vì một dịch vụ ngoài tạm thời không sẵn sàng.
- Bean có thể chưa được proxy/AOP xử lý đầy đủ.
- Circular dependency hoặc lifecycle phức tạp hơn.
- Khó phân biệt việc tạo object với việc khởi động tác vụ.

Constructor nên lưu dependency và kiểm tra invariant. Nếu cần initialization, hãy chọn lifecycle phù hợp như `InitializingBean`/`@PostConstruct` cho việc khởi tạo nhẹ, hoặc `ApplicationRunner`/`ApplicationReadyEvent` cho tác vụ cần ứng dụng đã refresh. Với tác vụ có thể retry hoặc chạy nền, thiết kế cơ chế riêng thay vì block constructor.

## 17. Constructor injection và proxy/AOP

Một Spring bean có thể được bọc bởi proxy để hỗ trợ transaction, caching, async hoặc security. Constructor injection giúp caller nhận bean từ container, thường là proxy nếu advisor áp dụng.

~~~java
@Service
public class CheckoutService {

    private final PaymentService paymentService;

    public CheckoutService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }
}
~~~

`CheckoutService` nhận dependency qua container, nên nó có thể gọi qua proxy của `PaymentService` nếu bean đó được proxy hóa.

Nếu tự tạo:

~~~java
this.paymentService = new PaymentService(...);
~~~

thì object đó không phải bean do Spring quản lý và không tự có transaction/cache/async proxy.

Constructor injection không tự khắc phục mọi giới hạn AOP: self-invocation, final/private method và proxy strategy vẫn cần được xét. Nhưng nó giữ cho việc lấy dependency đi qua Spring container thay vì tạo instance thủ công.

## 18. Test class dễ dàng khi dependency được truyền qua constructor

Một service dùng constructor injection có thể được unit test bằng cách truyền fake hoặc mock:

~~~java
class OrderServiceTest {

    private final OrderRepository repository =
            mock(OrderRepository.class);

    private final PaymentService paymentService =
            mock(PaymentService.class);

    private final OrderService service =
            new OrderService(repository, paymentService);

    @Test
    void placesOrder() {
        // arrange
        // act
        // assert
    }
}
~~~

Không cần khởi động Spring context nếu mục tiêu là kiểm tra logic của service. Test có thể dùng Mockito, fake implementation hoặc object thật nhẹ tùy nhu cầu.

### 18.1. Unit test không thay integration test wiring

Việc constructor được gọi thành công trong unit test không chứng minh Spring đã đăng ký đúng bean, qualifier hoặc profile.

Có thể dùng `@SpringBootTest` hoặc `ApplicationContextRunner` để kiểm tra wiring ở phạm vi cần thiết:

~~~java
@SpringBootTest
class OrderServiceWiringTest {

    @Autowired
    OrderService orderService;

    @Test
    void contextCreatesOrderService() {
        assertThat(orderService).isNotNull();
    }
}
~~~

Nếu có nhiều implementation của dependency, nên kiểm tra cụ thể bean nào được inject. Test wiring nhỏ giúp phát hiện lỗi cấu hình trước khi triển khai.

### 18.2. Test trường hợp thiếu dependency

Với dependency bắt buộc, một context không có bean phù hợp nên thất bại. Có thể dùng `ApplicationContextRunner` để xác nhận context startup failure và root cause, thay vì để service chạy rồi kiểm tra field null ở runtime.

## 19. Thiết kế API constructor dễ đọc

Một constructor tốt không chỉ có đủ tham số. Nó còn nên giúp người đọc hiểu trách nhiệm và thứ tự dependency.

### 19.1. Tránh các tham số primitive/string không có ý nghĩa

~~~java
public PaymentService(
        String url,
        String key,
        int timeout,
        boolean enabled) {
}
~~~

Một chữ ký như vậy khó biết mỗi tham số là gì, dễ truyền nhầm thứ tự và trộn configuration với service dependency.

Có thể nhóm dữ liệu cấu hình vào properties object:

~~~java
public PaymentService(
        PaymentProperties properties,
        PaymentGateway gateway) {
}
~~~

Nhưng không nên gom mọi thứ vào một `ApplicationSettings` khổng lồ chỉ để constructor ngắn hơn. Properties object nên đại diện một nhóm cấu hình có liên quan.

### 19.2. Dùng value object khi tham số có domain meaning

Ví dụ `Duration` tốt hơn một số nguyên không rõ đơn vị:

~~~java
public RetryService(Duration backoff) {
}
~~~

Nếu một kiểu dữ liệu có ý nghĩa nghiệp vụ rõ ràng, có thể tạo value object riêng để giảm nhầm lẫn giữa những tham số cùng primitive type.

### 19.3. Đừng tạo constructor overload cho mọi tổ hợp optional

Một class có 5 dependency tùy chọn có thể dẫn đến nhiều constructor overload và default ngầm. Hãy xem lại:

- Có thể tách capability thành collaborator riêng không?
- Có thể dùng một configuration object cho nhóm setting không?
- Dependency có thực sự optional hay là requirement bị bỏ sót?
- Một implementation mặc định có diễn đạt đúng chính sách không?

Constructor overload nên phản ánh các cách tạo object có ý nghĩa, không phải mọi tổ hợp boolean/nullable.

## 20. Circular dependency thường báo hiệu ranh giới trách nhiệm chưa rõ

Ví dụ A gọi B để xử lý thanh toán, còn B gọi A để cập nhật order. Vòng phụ thuộc khiến cả hai class khó tạo độc lập và khó test.

Có thể tách một abstraction sự kiện:

~~~java
public record PaymentCompleted(
        UUID orderId,
        Instant completedAt) {
}
~~~

Payment service phát event khi thanh toán thành công:

~~~java
@Service
public class PaymentService {

    private final ApplicationEventPublisher events;

    public PaymentService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void completePayment(UUID orderId) {
        // Hoàn tất xử lý payment.
        events.publishEvent(
                new PaymentCompleted(orderId, Instant.now()));
    }
}
~~~

Order service lắng nghe event:

~~~java
@Component
public class OrderPaymentListener {

    private final OrderRepository orders;

    public OrderPaymentListener(OrderRepository orders) {
        this.orders = orders;
    }

    @EventListener
    public void onPaymentCompleted(PaymentCompleted event) {
        // Cập nhật trạng thái order.
    }
}
~~~

Ví dụ này minh họa tách chiều phụ thuộc trong cùng application context. Với event cần đảm bảo transaction/outbox, retry hoặc delivery bền vững, cần chọn event mechanism phù hợp; Spring in-process event không tự cung cấp durability như message broker.

Không nên dùng event chỉ để tránh một constructor dài. Hãy dùng khi event thực sự diễn đạt một sự kiện domain/application và việc tách producer/consumer có ích.

## 21. Khi nào setter injection hợp lý?

Constructor injection là lựa chọn mặc định tốt cho dependency bắt buộc, nhưng setter injection có thể hợp lý trong một số trường hợp:

- Một dependency thật sự tùy chọn và class có behavior hợp lệ khi không có nó.
- Một thuộc tính cấu hình có thể thay đổi theo lifecycle được thiết kế rõ.
- Framework/legacy API yêu cầu no-argument constructor và property population.
- Một bean có nhiều bước cấu hình theo một contract đặc thù.

Ví dụ một callback tùy chọn:

~~~java
@Component
public class ImportCoordinator {

    private ImportListener listener = ImportListener.NOOP;

    public void setListener(ImportListener listener) {
        this.listener = listener;
    }
}
~~~

Ở đây default `NOOP` là behavior hợp lệ và listener có thể được cấu hình bổ sung. Nhưng nếu `ImportCoordinator` không thể import nếu thiếu repository, repository vẫn nên nằm trong constructor.

Không chuyển dependency bắt buộc sang setter chỉ vì có circular dependency hoặc vì constructor “trông dài”.

## 22. Tránh dependency injection qua static field

Không nên:

~~~java
@Component
public class LegacyHelper {

    @Autowired
    private static CatalogRepository repository;
}
~~~

Spring dependency injection được thiết kế cho bean instance. Static field thuộc class, không thuộc một object cụ thể và tạo state toàn cục khó quản lý.

Thay vào đó, đưa dependency vào constructor của bean sử dụng nó:

~~~java
@Service
public class CatalogService {

    private final CatalogRepository repository;

    public CatalogService(CatalogRepository repository) {
        this.repository = repository;
    }
}
~~~

Nếu code cũ dùng static utility, hãy chuyển phần cần I/O hoặc Spring service sang instance collaborator; giữ static cho hàm thuần không cần dependency.

## 23. Constructor và thứ tự khởi tạo dependency

Khi Spring tạo bean A cần bean B qua constructor, B phải được resolve trước khi constructor A có thể chạy. Vì vậy, constructor dependency thể hiện thứ tự tạo object trong graph.

~~~text
Controller
    |
    v
OrderService
    |
    +------> OrderRepository
    |
    +------> PaymentService
                 |
                 v
             PaymentClient
~~~

Container quản lý graph này, bao gồm singleton caching, scopes, proxies và lifecycle callbacks. Không nên tự sắp xếp thứ tự khởi tạo bằng cách gọi `getBean()` thủ công trong constructor.

Nếu có một initialization order thật sự cần thiết, hãy dùng dependency rõ ràng, lifecycle callback phù hợp hoặc event. Tránh dựa vào thứ tự component scan hay thứ tự file configuration.

## 24. Dependency có thể tạo bean không đồng nghĩa dependency nên được inject

Một class có thể inject quá nhiều bean vì code đang làm thay trách nhiệm của những module khác.

Ví dụ:

~~~java
@Service
public class OrderService {

    private final OrderRepository orders;
    private final CustomerRepository customers;
    private final ProductRepository products;
    private final TaxRepository taxes;
    private final CurrencyRepository currencies;
    private final EmailClient email;
    private final SmsClient sms;
    private final PdfRenderer pdf;
    private final AuditRepository audit;
}
~~~

Constructor này là dấu hiệu cần xem lại trách nhiệm. Có thể service đang vừa tính đơn hàng, render hóa đơn, gửi thông báo và ghi audit.

Không nhất thiết phải tách mọi repository thành một service wrapper. Nhưng có thể tách use case:

- `OrderPricingService` chịu trách nhiệm tính giá.
- `InvoiceService` chịu trách nhiệm tạo hóa đơn.
- `NotificationService` gửi thông báo.
- `OrderApplicationService` điều phối quy trình.

Mỗi class nhận những dependency cần thiết cho đúng nhiệm vụ. Constructor khi đó trở thành bản mô tả ngắn gọn về phạm vi trách nhiệm.

## 25. Lỗi thường gặp khi thiết kế constructor

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Bean không khởi động vì thiếu dependency | Constructor yêu cầu bean không được đăng ký | Đăng ký bean, thêm dependency phù hợp hoặc xem lại requirement |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng type | Dùng `@Qualifier`, `@Primary` hoặc inject collection |
| `BeanCurrentlyInCreationException` | Constructor dependencies tạo vòng phụ thuộc | Tách trách nhiệm, event hoặc abstraction để phá vòng |
| Unit test không tạo được service | Class phụ thuộc field injection/Spring context | Chuyển dependency bắt buộc vào constructor |
| Field dependency null trong test | Object được tạo bằng `new`, Spring chưa inject field | Truyền dependency qua constructor |
| Constructor có quá nhiều tham số | Class có nhiều trách nhiệm hoặc cấu hình chưa được nhóm hợp lý | Refactor theo trách nhiệm, không che bằng field injection |
| Optional dependency gây NPE | Dùng null nhưng không xử lý | Dùng Optional/provider/default implementation hoặc validate |
| Prototype bean không đổi mỗi lần gọi | Inject trực tiếp vào singleton nên chỉ resolve khi singleton tạo | Dùng ObjectProvider hoặc scoped proxy |
| Constructor phụ được Spring chọn ngoài ý muốn | Nhiều constructor không có quy tắc chọn rõ | Đánh dấu constructor phù hợp bằng @Autowired khi cần |
| Dependency được tạo bằng `new` không có AOP | Object nằm ngoài Spring container | Inject bean do container quản lý |
| Startup chạy query/HTTP quá sớm | Constructor chứa side effect | Chuyển công việc sang lifecycle/application service phù hợp |
| Bật circular references mới chạy | Vòng dependency bị che bằng cơ chế khởi tạo hai pha | Refactor graph để không còn cycle |

## 26. Quy trình thiết kế constructor cho một Spring bean

Khi tạo class mới hoặc refactor bean hiện có, có thể đi theo các bước:

1. Liệt kê những collaborator mà class cần để hoàn thành trách nhiệm.
2. Đánh dấu dependency nào là bắt buộc để object tồn tại hợp lệ.
3. Đưa dependency bắt buộc vào constructor.
4. Khai báo field tương ứng là `private final`.
5. Với dependency optional, chọn `Optional<T>`, `ObjectProvider<T>` hoặc default implementation theo semantics.
6. Nếu có nhiều bean cùng type, chỉ rõ qualifier/default.
7. Kiểm tra graph có circular dependency không.
8. Giữ constructor chỉ làm validation/assignment, không thực hiện I/O hoặc nghiệp vụ.
9. Unit test bằng cách truyền fake/mock trực tiếp vào constructor.
10. Integration test context để xác nhận Spring wiring và profile/condition đúng.

### Sơ đồ quyết định

~~~text
Class cần dependency X?
       |
       v
Không thể hoạt động nếu thiếu X?
       |
   +---+---+
   |       |
  Có      Không
   |       |
   v       v
Constructor  X có thể vắng mặt hợp lệ?
   |              |
   |          +---+---+
   |          |       |
   |         Có      Không
   |          |       |
   v          v       v
Inject X   Optional /  Thiết kế lại
required   Provider /  contract
           default
~~~

Nếu dependency là một trong nhiều implementation, tiếp tục chọn `@Qualifier`/`@Primary` hoặc collection theo mục đích sử dụng.

## 27. Nguyên tắc cần ghi nhớ

1. **Constructor là hợp đồng tạo object.** Những dependency bắt buộc nên xuất hiện trong constructor.
2. **Dùng field final** để giữ tham chiếu dependency ổn định sau khi tạo bean.
3. Với một constructor duy nhất, Spring thường tự inject mà không cần `@Autowired`.
4. Nếu class có nhiều constructor, hãy xác định rõ constructor Spring cần sử dụng.
5. **Optionality phải thể hiện tường minh.** Dùng `Optional`, `ObjectProvider`, `@Nullable` hoặc implementation mặc định khi vắng mặt thực sự hợp lệ.
6. Nếu dependency bắt buộc bị thiếu, để context fail sớm thay vì tạo object không hoàn chỉnh.
7. Khi có nhiều candidate, dùng qualifier/default hoặc inject collection; không để Spring đoán.
8. Constructor injection làm circular dependency lộ rõ; refactor dependency graph thay vì chuyển sang field/setter để che cycle.
9. Không dùng `ApplicationContext` như service locator trong business class.
10. Không thực hiện I/O, truy vấn DB hoặc chạy nghiệp vụ nặng trong constructor.
11. Inject bean từ Spring container để giữ đúng lifecycle, AOP proxy và configuration.
12. Unit test có thể tạo class bằng constructor với fake/mock; integration test xác nhận container wiring.
13. Constructor dài có thể là tín hiệu nhiều trách nhiệm; hãy refactor theo domain/use case, không chỉ giảm số tham số.
14. Phân biệt constructor injection của service với constructor binding của `@ConfigurationProperties`.

**Kết luận:** Thiết kế constructor tốt làm cho trạng thái hợp lệ của object trở nên rõ ràng ngay tại thời điểm tạo. Spring có thể resolve các dependency bắt buộc trước khi khởi tạo bean, còn developer có thể đọc chữ ký constructor để hiểu class cần gì. Dùng constructor cho collaborator cốt lõi, biểu đạt optional dependency bằng một kiểu rõ ràng, và giữ dependency graph không có vòng phụ thuộc sẽ giúp ứng dụng Spring Boot dễ khởi động, kiểm thử và bảo trì hơn.
