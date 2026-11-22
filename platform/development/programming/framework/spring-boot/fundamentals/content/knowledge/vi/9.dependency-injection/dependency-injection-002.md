# Tiêm qua setter cho phụ thuộc tùy chọn hoặc cần cấu hình lại

Trong Spring, **constructor injection** thường là lựa chọn đầu tiên cho những dependency bắt buộc: một service cần repository, một controller cần service, hoặc một bộ xử lý cần chính sách nghiệp vụ. Nhưng có những dependency không phải lúc nào cũng tồn tại, chỉ được sử dụng trong một số môi trường, hoặc cần một điểm cấu hình riêng sau khi object được tạo. Trong các trường hợp đó, **setter injection** có thể là lựa chọn phù hợp.

Setter injection là cách truyền dependency vào một object thông qua phương thức setter sau khi constructor đã tạo object. Spring gọi phương thức đó khi khởi tạo bean và resolve dependency theo cấu hình. Cách này làm dependency có thể được bỏ qua hoặc thay đổi qua một API setter, nhưng cũng khiến object có trạng thái có thể thay đổi sau khi tạo.

Điều quan trọng là phân biệt hai ý:

- **Phụ thuộc tùy chọn:** ứng dụng vẫn hoạt động khi một bean hỗ trợ không có mặt, ví dụ metrics, thông báo phụ hoặc tích hợp tùy môi trường.
- **Phụ thuộc cần cấu hình lại:** object có một điểm nhận giá trị hoặc implementation khác khi cấu hình được thay đổi có chủ đích.

Setter injection hỗ trợ việc cung cấp dependency theo cách linh hoạt. Tuy nhiên, setter injection tự nó **không tạo ra cơ chế tự reload cấu hình hay tự thay dependency khi ứng dụng đang chạy**. Việc thay đổi runtime cần một thiết kế và cơ chế riêng.

## 1. Setter injection hoạt động như thế nào?

Ví dụ một class Java có setter:

~~~java
public class ReportService {

    private ReportExporter exporter;

    public void setExporter(ReportExporter exporter) {
        this.exporter = exporter;
    }
}
~~~

Nếu object được tạo thủ công, bên gọi có thể làm:

~~~java
ReportService service = new ReportService();
service.setExporter(new PdfReportExporter());
~~~

Với Spring, có thể đánh dấu setter bằng **@Autowired**:

~~~java
@Service
public class ReportService {

    private ReportExporter exporter;

    @Autowired
    public void setExporter(ReportExporter exporter) {
        this.exporter = exporter;
    }
}
~~~

Khi tạo bean **ReportService**, Spring tạo object trước, sau đó gọi setter và truyền bean **ReportExporter** phù hợp vào. Trình tự khái quát:

~~~text
Spring ApplicationContext
        │
        ▼
Gọi constructor ReportService()
        │
        ▼
Object ReportService được tạo
        │
        ▼
Resolve bean ReportExporter
        │
        ▼
Gọi setExporter(exporter)
        │
        ▼
Các bước khởi tạo bean tiếp theo
        │
        ▼
ReportService sẵn sàng sử dụng
~~~

Spring quản lý việc tìm bean và gọi setter; **ReportService** vẫn định nghĩa cách sử dụng exporter trong nghiệp vụ. Annotation không tự quyết định định dạng báo cáo hay nội dung file.

### Setter injection khác constructor injection ở đâu?

| Tiêu chí | Constructor injection | Setter injection |
|---|---|---|
| Thời điểm nhận dependency | Trong lúc tạo object | Sau khi constructor hoàn tất |
| Phù hợp nhất | Dependency bắt buộc | Dependency tùy chọn hoặc có điểm cấu hình riêng |
| Trạng thái object | Có thể hoàn chỉnh ngay sau constructor | Có thể chưa đủ dependency cho tới khi setter được gọi |
| Tính bất biến | Dễ dùng final cho dependency | Dependency thường nằm trong field có thể thay đổi |
| Kiểm thử Java thuần | Truyền dependency ngay khi tạo | Tạo object rồi gọi setter |
| Rủi ro chính | Constructor có quá nhiều tham số nếu class ôm quá nhiều trách nhiệm | Object có trạng thái chưa hoàn chỉnh hoặc bị thay đổi ngoài dự kiến |

Ví dụ constructor injection cho dependency bắt buộc:

~~~java
@Service
public class InvoiceService {

    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }
}
~~~

Nếu không có **InvoiceRepository**, Spring nên báo lỗi khởi tạo context. Đây là hành vi tốt: service không thể thực hiện chức năng chính nếu thiếu repository.

Ngược lại, một **MetricsRecorder** chỉ dùng để ghi số liệu phụ có thể là tùy chọn. Nếu bean này không được cấu hình ở một môi trường, service vẫn có thể tạo hóa đơn bình thường. Setter injection có thể diễn đạt trường hợp đó.

## 2. Tiêm setter cho dependency tùy chọn bằng @Autowired(required = false)

Spring cho phép đánh dấu một phương thức injection với **@Autowired(required = false)**. Nếu dependency không thể được resolve, phương thức injection đó sẽ không được gọi.

~~~java
public interface MetricsRecorder {
    void recordInvoiceCreated();
}
~~~

Service sử dụng dependency này như một tính năng hỗ trợ:

~~~java
@Service
public class InvoiceService {

    private final InvoiceRepository repository;
    private MetricsRecorder metricsRecorder;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Autowired(required = false)
    public void setMetricsRecorder(MetricsRecorder metricsRecorder) {
        this.metricsRecorder = metricsRecorder;
    }

    public Invoice create(CreateInvoiceCommand command) {
        Invoice invoice = repository.save(Invoice.from(command));

        if (metricsRecorder != null) {
            metricsRecorder.recordInvoiceCreated();
        }

        return invoice;
    }
}
~~~

Trong ví dụ:

- **InvoiceRepository** là dependency bắt buộc, được nhận qua constructor.
- **MetricsRecorder** là dependency tùy chọn, được nhận qua setter.
- Nếu không có bean **MetricsRecorder**, Spring bỏ qua setter và field vẫn là **null**.
- Khi tạo hóa đơn, service kiểm tra sự tồn tại của recorder trước khi gọi.

Điều kiện quan trọng: dependency tùy chọn phải thực sự là **tùy chọn đối với tính đúng đắn của nghiệp vụ**. Nếu thiếu nó khiến dữ liệu bị mất hoặc đơn hàng không thể hoàn tất, không nên âm thầm coi đó là tùy chọn.

### @Autowired(required = false) có ý nghĩa gì?

Giá trị **required = false** áp dụng cho điểm injection được đánh dấu. Với setter một tham số như ví dụ, nếu không có bean phù hợp, Spring không gọi phương thức đó. Với phương thức injection có nhiều tham số, Spring chỉ gọi phương thức khi có thể resolve các dependency cần thiết theo quy tắc của điểm injection đó.

Nếu có **nhiều bean MetricsRecorder** mà Spring không biết chọn bean nào, **required = false** không có nghĩa là “bỏ qua mọi lỗi”. Sự mơ hồ trong việc chọn bean vẫn cần được giải quyết bằng **@Qualifier**, **@Primary** hoặc cấu hình rõ ràng.

### Cần tránh NullPointerException

Sau khi dùng setter optional, field có thể không được gán. Vì vậy, mọi nơi sử dụng nó phải xử lý trạng thái vắng mặt:

~~~java
if (metricsRecorder != null) {
    metricsRecorder.recordInvoiceCreated();
}
~~~

Không nên gọi trực tiếp **metricsRecorder.recordInvoiceCreated()** nếu bean thật sự có thể không tồn tại.

Ngoài ra, nếu object được tạo thủ công bên ngoài Spring, Spring sẽ không tự gọi setter. Khi đó field cũng có thể là null. Đây là một lý do khác để API của class làm rõ dependency nào bắt buộc và dependency nào tùy chọn.

## 3. Dùng Optional<T> để biểu diễn sự vắng mặt

Một cách khác là khai báo dependency bằng **Optional<T>**. Spring hỗ trợ resolve một dependency kiểu Optional: nếu có bean phù hợp thì Optional chứa bean; nếu không thì nhận **Optional.empty()**.

~~~java
@Service
public class InvoiceService {

    private final InvoiceRepository repository;
    private Optional<MetricsRecorder> metricsRecorder = Optional.empty();

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Autowired
    public void setMetricsRecorder(
            Optional<MetricsRecorder> metricsRecorder) {
        this.metricsRecorder = metricsRecorder;
    }

    public Invoice create(CreateInvoiceCommand command) {
        Invoice invoice = repository.save(Invoice.from(command));

        metricsRecorder.ifPresent(
                MetricsRecorder::recordInvoiceCreated);

        return invoice;
    }
}
~~~

So với field có thể null, **Optional** làm trạng thái vắng mặt được thể hiện rõ hơn trong kiểu dữ liệu:

~~~text
Optional<MetricsRecorder>
        │
        ├── Optional.of(recorder)  → có recorder
        │
        └── Optional.empty()       → không có recorder
~~~

Ở ví dụ này, setter được đánh dấu **@Autowired** mặc định là required, nhưng dependency kiểu **Optional<MetricsRecorder>** vẫn có thể được resolve thành **Optional.empty()** khi không có bean. Không cần kết hợp **required = false** chỉ để làm cho Optional trở thành optional.

**Chọn một cách diễn đạt thống nhất.** Với dependency tùy chọn, bạn có thể dùng setter **@Autowired(required = false)** cùng field nullable, hoặc setter nhận **Optional<T>**. Không nên trộn nhiều cơ chế mà không có lý do.

## 4. Setter injection với @Nullable

Spring cũng hỗ trợ đánh dấu tham số injection là có thể null bằng annotation **@Nullable**:

~~~java
@Autowired
public void setMetricsRecorder(
        @Nullable MetricsRecorder metricsRecorder) {
    this.metricsRecorder = metricsRecorder;
}
~~~

Trong Spring Framework, có thể dùng **org.springframework.lang.Nullable** ở những phiên bản phù hợp. Annotation nullability khác nhau có thể được sử dụng tùy hệ sinh thái và phiên bản; cần chọn một loại nhất quán với project.

Khi bean không có, tham số có thể nhận null. Cách này ngắn nhưng field và mọi nơi sử dụng vẫn phải tuân thủ quy ước null. Nếu muốn thể hiện trạng thái vắng mặt ngay ở kiểu tham số, **Optional<T>** thường dễ đọc hơn.

Không nên đánh dấu một dependency quan trọng là nullable chỉ để ứng dụng khởi động được. Nếu service không thể làm đúng nhiệm vụ khi thiếu dependency, hãy để Spring báo lỗi rõ ràng ở startup.

## 5. So sánh các cách biểu diễn dependency tùy chọn

| Cách | Khi dependency vắng mặt | Điểm cần chú ý |
|---|---|---|
| **@Autowired(required = false)** trên setter | Setter không được gọi | Field phải có giá trị mặc định hoặc xử lý null |
| Setter nhận **Optional<T>** | Nhận Optional.empty() | Thể hiện optional ngay trong kiểu |
| Tham số **@Nullable T** | Có thể nhận null | Cần null-check nhất quán |
| **ObjectProvider<T>** | Có thể kiểm tra hoặc lấy bean khi cần | Phù hợp khi muốn trì hoãn lookup hoặc có nhiều candidate |
| **No-op implementation** | Luôn có một bean, nhưng hành động không làm gì | Giảm nhánh null; cần tên và hành vi rõ ràng |

### No-op implementation: một lựa chọn thường đơn giản hơn

Thay vì để bean metrics có thể vắng mặt, có thể cung cấp implementation mặc định không làm gì:

~~~java
@Component
public class NoOpMetricsRecorder implements MetricsRecorder {

    @Override
    public void recordInvoiceCreated() {
        // Cố ý không ghi metrics.
    }
}
~~~

Khi đó service luôn nhận được **MetricsRecorder** qua constructor:

~~~java
@Service
public class InvoiceService {

    private final InvoiceRepository repository;
    private final MetricsRecorder metricsRecorder;

    public InvoiceService(
            InvoiceRepository repository,
            MetricsRecorder metricsRecorder) {
        this.repository = repository;
        this.metricsRecorder = metricsRecorder;
    }
}
~~~

Nếu chỉ có **NoOpMetricsRecorder**, dependency không còn optional ở cấp container; service luôn gọi được interface. Ở môi trường cần metrics thật, có thể chọn implementation khác bằng profile/conditional configuration hoặc cấu hình bean phù hợp.

**No-op pattern** hữu ích khi muốn tránh nhiều nhánh null trong service. Nhưng chỉ dùng nó nếu hành vi “không làm gì” thật sự hợp lệ. Không nên cung cấp no-op cho một dependency bắt buộc như kiểm tra quyền thanh toán, vì nó có thể biến lỗi cấu hình nghiêm trọng thành hành vi có vẻ thành công.

## 6. ObjectProvider<T> khi muốn tra cứu dependency linh hoạt

**ObjectProvider<T>** là abstraction của Spring cho phép lấy bean theo nhu cầu thay vì buộc phải có ngay một instance cụ thể ở constructor hoặc setter.

~~~java
@Service
public class InvoiceService {

    private final InvoiceRepository repository;
    private final ObjectProvider<MetricsRecorder> metricsProvider;

    public InvoiceService(
            InvoiceRepository repository,
            ObjectProvider<MetricsRecorder> metricsProvider) {
        this.repository = repository;
        this.metricsProvider = metricsProvider;
    }

    public Invoice create(CreateInvoiceCommand command) {
        Invoice invoice = repository.save(Invoice.from(command));

        metricsProvider.ifAvailable(
                MetricsRecorder::recordInvoiceCreated);

        return invoice;
    }
}
~~~

Container có thể inject **ObjectProvider<MetricsRecorder>** như một đối tượng truy cập bean. Khi service gọi **ifAvailable**, provider mới tìm bean phù hợp; nếu không có thì callback không chạy.

Provider hữu ích khi:

- Dependency có thể không tồn tại.
- Muốn trì hoãn thời điểm resolve bean.
- Có nhiều bean và muốn sử dụng API như **orderedStream()** hoặc lựa chọn theo quy tắc phù hợp.
- Muốn lấy instance theo scope tại thời điểm gọi thay vì giữ trực tiếp một instance được inject từ đầu.

Tuy nhiên, **ObjectProvider** là API Spring. Nếu mục tiêu là giữ application service độc lập với container, có thể đặt một interface/factory của ứng dụng ở ranh giới phù hợp rồi inject implementation tương ứng. Không nên dùng provider chỉ để né việc khai báo dependency rõ ràng.

## 7. Setter injection cho cấu hình

Setter cũng có thể nhận một giá trị cấu hình:

~~~java
@Component
public class MessageFormatter {

    private String prefix = "[APP]";

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }

    public String format(String message) {
        return prefix + " " + message;
    }
}
~~~

Spring có thể gọi setter để gán property khi bean được cấu hình. Với một thuộc tính đơn, có thể dùng **@Value** trên setter để bind một property placeholder từ Environment, kèm giá trị mặc định nếu cần. Nếu không có cơ chế bind hoặc không có bên gọi setter, giá trị mặc định trong class vẫn được giữ.

Đây là **property injection qua setter**. Nó vẫn là quá trình bind cấu hình khi bean được tạo. Việc có setter công khai không đồng nghĩa Spring sẽ tự động theo dõi file cấu hình và gọi lại setter mỗi khi file thay đổi.

### Khi có nhiều thuộc tính, nên dùng @ConfigurationProperties

Nếu một component có nhiều giá trị cấu hình liên quan, gom chúng thành một đối tượng có kiểu rõ ràng:

~~~yaml
app:
  notification:
    enabled: true
    sender-name: Learning Platform
    retry-limit: 3
~~~

Dùng JavaBean setter:

~~~java
@ConfigurationProperties(prefix = "app.notification")
public class NotificationProperties {

    private boolean enabled;
    private String senderName;
    private int retryLimit;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getSenderName() {
        return senderName;
    }

    public void setSenderName(String senderName) {
        this.senderName = senderName;
    }

    public int getRetryLimit() {
        return retryLimit;
    }

    public void setRetryLimit(int retryLimit) {
        this.retryLimit = retryLimit;
    }
}
~~~

Đăng ký properties:

~~~java
@Configuration
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationConfiguration {
}
~~~

Sau đó service có thể inject **NotificationProperties** qua constructor. Spring Boot binder gọi các setter tương ứng khi bind thuộc tính.

~~~java
@Service
public class NotificationService {

    private final NotificationProperties properties;

    public NotificationService(NotificationProperties properties) {
        this.properties = properties;
    }
}
~~~

Đối với cấu hình bất biến, có thể dùng constructor binding/record tùy phiên bản và cách đăng ký. Setter-based JavaBean properties là một lựa chọn khi cần kiểu mutable và binder hỗ trợ setter.

**Không nên tạo một setter cho mỗi property rải rác trong các service** nếu chúng thuộc cùng một nhóm cấu hình. Một lớp properties tập trung giúp dễ đọc, kiểm tra và quản lý cấu hình theo môi trường.

## 8. Setter injection có phải là runtime reconfiguration?

Đây là điểm cần phân biệt kỹ nhất của bài.

Khi Spring khởi tạo singleton bean, container gọi setter injection để cung cấp dependency. Sau khi hoàn tất, setter **không tự được gọi lại** chỉ vì:

- Một file application.yml được sửa trên ổ đĩa.
- Một biến môi trường của tiến trình thay đổi.
- Một service bên ngoài có phiên bản mới.
- Một giá trị trong database thay đổi.

Setter injection cung cấp một **điểm nhận giá trị**. Nó không phải cơ chế quan sát thay đổi, đồng bộ trạng thái, refresh bean hay điều phối việc thay thế dependency.

### Trường hợp 1: chỉ cần cấu hình tại startup

Nếu URL dịch vụ, timeout hay sender name chỉ cần xác định lúc ứng dụng khởi động, hãy dùng **@ConfigurationProperties** hoặc cấu hình bean. Setter injection có thể là cách binder gán thuộc tính, nhưng không cần mở API setter công khai để mọi nơi tùy ý thay đổi sau đó.

### Trường hợp 2: thực sự cần thay đổi dependency lúc runtime

Giả sử ứng dụng cần chuyển giữa hai implementation của một dịch vụ định tuyến trong khi tiến trình vẫn chạy. Có thể thiết kế một abstraction có khả năng thay thế rõ ràng:

~~~java
public interface RouteProvider {
    String routeFor(String destination);
}
~~~

Một registry quản lý implementation hiện hành:

~~~java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Component;

@Component
public class RouteProviderRegistry {

    private final AtomicReference<RouteProvider> current;

    public RouteProviderRegistry(RouteProvider initialProvider) {
        this.current = new AtomicReference<>(initialProvider);
    }

    public String routeFor(String destination) {
        return current.get().routeFor(destination);
    }

    public void replace(RouteProvider newProvider) {
        Objects.requireNonNull(newProvider, "newProvider");
        current.set(newProvider);
    }
}
~~~

Đây là ví dụ minh họa một API runtime reconfiguration do ứng dụng sở hữu, **không phải setter injection của Spring**. Việc thay reference có tính nguyên tử, nhưng hệ thống thật còn phải xác định ai được phép gọi **replace**, cách tạo và xác thực provider mới, cách thu hồi tài nguyên của provider cũ, và cách xử lý những lời gọi đang chạy.

Nếu dùng setter công khai trên singleton service để thay dependency tùy ý:

~~~java
public void setRouteProvider(RouteProvider provider) {
    this.routeProvider = provider;
}
~~~

thì phải xem xét:

- Thread khác có thể đang đọc field trong khi setter thay đổi nó.
- Giá trị null có được chấp nhận không?
- Ai có quyền thay đổi và khi nào?
- Dependency mới đã được khởi tạo, kiểm tra kết nối và sẵn sàng chưa?
- Dependency cũ có cần đóng connection, thread hoặc tài nguyên không?
- Một request đang xử lý dở sẽ tiếp tục với provider cũ hay provider mới?

Một setter bình thường không tự giải quyết các câu hỏi này. Nếu có nhu cầu thay đổi runtime, cần thiết kế API và vòng đời thay thế có chủ đích.

## 9. Thay đổi cấu hình động: setter, refresh và cập nhật trạng thái

Có một số cách tiếp cận khi hệ thống cần nhận cấu hình mới:

| Cách | Ý nghĩa | Hành vi |
|---|---|---|
| **Setter injection** | Gán dependency/property trong quá trình bean được tạo | Không tự reload khi nguồn cấu hình đổi |
| **ConfigurationProperties binding** | Bind cấu hình thành object có kiểu | Thường diễn ra trong quá trình khởi tạo context hoặc khi binder được gọi |
| **Refresh mechanism** | Yêu cầu một hạ tầng cụ thể refresh bean/configuration | Chỉ có khi ứng dụng triển khai và cấu hình cơ chế refresh tương ứng |
| **Application-managed registry** | Ứng dụng chủ động thay implementation/configuration qua API | Cần quản lý đồng thời, xác thực và vòng đời |
| **Recreate ApplicationContext** | Tạo context mới với cấu hình mới | Có chi phí, cần chiến lược chuyển traffic và đóng context cũ |

Một số hệ sinh thái Spring có cơ chế refresh context/bean, nhưng không phải mọi Spring Boot application đều tự có khả năng reload cấu hình. Cần xác định rõ thư viện, phiên bản và loại bean nào hỗ trợ refresh.

**Đừng đánh đồng setter injection với refresh scope.** Setter chỉ là một điểm nhận dependency hoặc giá trị. Refresh scope, nếu được cung cấp bởi hạ tầng cụ thể, là cơ chế quản lý việc làm mới target/proxy theo hợp đồng riêng.

## 10. Khi nào nên dùng setter injection?

| Tình huống | Setter injection có phù hợp? | Lý do |
|---|---|---|
| Repository bắt buộc của service | Thường không | Thiếu dependency phải làm startup thất bại; constructor thể hiện rõ hơn |
| Metrics recorder không bắt buộc | Có thể | Bean hỗ trợ có thể vắng mặt mà nghiệp vụ chính vẫn hoạt động |
| Notification bổ sung tùy môi trường | Có thể | Có thể bỏ qua hoặc dùng implementation mặc định |
| Một nhóm cấu hình cần bind qua JavaBean setter | Có | Binder có thể gán các thuộc tính mutable |
| Dependency phải thay đổi runtime theo một quy trình được kiểm soát | Setter đơn giản chưa đủ | Cần API reconfiguration, đồng bộ và quản lý lifecycle |
| Class có nhiều dependency bắt buộc | Không nên chuyển tất cả sang setter để né constructor dài | Nên xem lại class có quá nhiều trách nhiệm không |
| Cần dependency cho một số lần gọi hiếm hoi | Có thể cân nhắc ObjectProvider/factory | Tránh giữ hoặc tạo dependency không cần thiết |

Nguyên tắc chung:

1. **Constructor injection cho dependency bắt buộc.**
2. **Setter injection cho dependency thực sự tùy chọn hoặc cần điểm cấu hình mutable có lý do.**
3. **Optional<T>, @Nullable hoặc ObjectProvider<T> để biểu diễn sự vắng mặt theo cách rõ ràng.**
4. **No-op implementation** nếu hành vi mặc định không làm gì là hợp lệ và giúp loại bỏ nhánh null.
5. **Cơ chế runtime reconfiguration riêng** khi phải thay đổi trong lúc ứng dụng đang chạy.

## 11. Thứ tự khởi tạo và những điều không nên giả định

Với một bean Spring thông thường, constructor được gọi trước. Sau đó container thực hiện các bước inject dependency qua field/method và những bước xử lý bean khác trước khi callback khởi tạo và bean được đưa vào sử dụng theo vòng đời.

Do đó, trong constructor không nên giả định setter injection đã chạy:

~~~java
@Component
public class ExportService {

    private Exporter exporter;

    public ExportService() {
        // Không nên dùng exporter ở đây nếu nó chỉ được inject qua setter.
    }

    @Autowired
    public void setExporter(Exporter exporter) {
        this.exporter = exporter;
    }
}
~~~

Nếu một dependency bắt buộc để object có trạng thái hợp lệ ngay khi tạo, đưa nó vào constructor sẽ diễn đạt đúng hơn. Với setter optional, có thể dùng fallback hợp lệ hoặc chỉ truy cập sau khi đã xác định dependency có mặt.

Không nên gọi setter injection thủ công từ một bean khác để điều khiển thứ tự khởi tạo. Hãy để container quản lý việc resolve dependency. Nếu có quan hệ khởi tạo đặc biệt, cần xem xét cấu hình bean/factory hoặc lifecycle callback phù hợp, đồng thời tránh tạo phụ thuộc vòng.

### Setter nhiều tham số

Spring có thể inject một phương thức có nhiều tham số:

~~~java
@Autowired
public void configure(
        Clock clock,
        MetricsRecorder metricsRecorder) {
    // Nhận cả hai dependency.
}
~~~

Với một injection method được đánh dấu required mặc định, các dependency của method phải được resolve. Nếu một dependency không tồn tại, Spring không thể gọi method như mong đợi và có thể làm bean creation thất bại. Nếu toàn bộ method được đánh dấu **required = false**, Spring bỏ qua method khi không thể resolve các dependency cần thiết.

Nếu các dependency có tính bắt buộc khác nhau, nên tách thành các constructor/setter riêng hoặc biểu diễn phần tùy chọn bằng **Optional<T>**. Không nên gom nhiều dependency vào một setter optional rồi vô tình làm những dependency bắt buộc trở nên không rõ ràng.

## 12. Những rủi ro khi lạm dụng setter injection

### Object có thể tồn tại trong trạng thái chưa hoàn chỉnh

Constructor đã chạy nhưng setter chưa được gọi. Nếu một phương thức nghiệp vụ bị gọi quá sớm hoặc object được tạo thủ công ngoài Spring, field có thể chưa có giá trị.

### Dependency có thể bị thay đổi ngoài dự kiến

Setter công khai làm tăng số điểm có thể thay đổi trạng thái object. Một bean singleton được nhiều thành phần dùng chung có thể bị ảnh hưởng nếu setter bị gọi sau khi bean đã hoạt động.

### Khó đảm bảo thread safety

Thay một dependency trong lúc nhiều thread đang sử dụng nó cần cơ chế đồng bộ và quy tắc chuyển đổi rõ ràng. Chỉ đổi field từ null sang object không giải quyết vòng đời của dependency cũ hoặc trạng thái của request đang chạy.

### Dependency bắt buộc bị che thành tùy chọn

Đánh dấu **required = false** cho repository hoặc policy cốt lõi có thể khiến ứng dụng khởi động nhưng lỗi chỉ xuất hiện khi người dùng gọi chức năng. Lỗi cấu hình nên được phát hiện càng sớm càng tốt.

### Test phải thiết lập nhiều bước

Với setter injection, test cần tạo object rồi gọi setter trước khi kiểm tra. Nếu quên bước đó, test có thể gặp null hoặc chạy với fallback ngoài ý muốn. Constructor injection thường làm trạng thái bắt buộc rõ ngay tại thời điểm tạo.

~~~java
InvoiceService service = new InvoiceService(repository);
service.setMetricsRecorder(metricsRecorder);
~~~

Đoạn test trên thể hiện hai bước thiết lập. Nếu **metricsRecorder** là bắt buộc, nên đưa nó vào constructor để API thể hiện yêu cầu ngay từ đầu.

## 13. Kiểm thử hành vi khi dependency tùy chọn vắng mặt

Giả sử **InvoiceService** chỉ yêu cầu **InvoiceRepository**; **MetricsRecorder** có thể vắng mặt. Một unit test có thể tạo service không cần Spring:

~~~java
class InvoiceServiceTest {

    @Test
    void createsInvoiceWhenMetricsRecorderIsAbsent() {
        InvoiceRepository repository =
                command -> Invoice.from(command);

        InvoiceService service = new InvoiceService(repository);

        Invoice invoice = service.create(
                new CreateInvoiceCommand("INV-001"));

        assertNotNull(invoice);
    }
}
~~~

Đây là mã minh họa, giả định các kiểu **InvoiceRepository**, **Invoice**, **CreateInvoiceCommand** và phương thức **create(...)** đã được định nghĩa tương ứng. Mục tiêu là chứng minh **tính năng hỗ trợ metrics không phải điều kiện để tạo invoice**.

Nếu cần kiểm tra chính xác Spring bỏ qua setter khi bean không tồn tại, có thể viết một context test nhỏ chỉ đăng ký **InvoiceService** và repository giả, không đăng ký **MetricsRecorder**. Khi đó test kiểm tra hành vi wiring của container; unit test kiểm tra hành vi nghiệp vụ độc lập.

Hai phạm vi kiểm thử khác nhau:

- **Unit test:** service có hoạt động đúng khi không có optional collaborator không?
- **Spring context test:** cấu hình bean có khiến Spring khởi tạo service thành công khi collaborator không có không?

## 14. Các lựa chọn thay thế cần cân nhắc

### Constructor với Optional

Nếu muốn dependency tùy chọn vẫn được thể hiện ngay lúc object được tạo:

~~~java
@Service
public class InvoiceService {

    private final InvoiceRepository repository;
    private final Optional<MetricsRecorder> metrics;

    public InvoiceService(
            InvoiceRepository repository,
            Optional<MetricsRecorder> metrics) {
        this.repository = repository;
        this.metrics = metrics;
    }
}
~~~

Cách này giữ object được thiết lập đầy đủ sau constructor và thể hiện rõ optional dependency. Đây là lựa chọn tốt nếu không cần setter mutable.

### Factory hoặc ObjectProvider

Nếu cần lấy một bean theo yêu cầu hoặc phụ thuộc vào scope, có thể dùng **ObjectProvider<T>** hoặc một factory interface do ứng dụng định nghĩa. Điều này phù hợp hơn việc giữ một field có thể bị setter thay đổi không kiểm soát.

### Conditional bean hoặc profile

Nếu muốn chọn implementation dựa trên môi trường, có thể định nghĩa các bean có điều kiện hoặc dùng **@Profile**:

~~~java
@Configuration
public class MetricsConfiguration {

    @Bean
    @Profile("production")
    MetricsRecorder productionMetricsRecorder() {
        return new ProductionMetricsRecorder();
    }

    @Bean
    @Profile("test")
    MetricsRecorder testMetricsRecorder() {
        return new NoOpMetricsRecorder();
    }
}
~~~

Đây là ví dụ minh họa lựa chọn implementation theo profile; trong ứng dụng cụ thể, cần bảo đảm chỉ có implementation phù hợp được đăng ký cho mỗi profile. **Profile chọn bean lúc xây dựng ApplicationContext**, không phải cơ chế thay bean tự động mỗi khi profile hay môi trường thay đổi.

## 15. Tư duy trước khi chọn setter injection

Trước khi chuyển một dependency từ constructor sang setter, hãy tự hỏi:

1. Dependency này có thật sự **không bắt buộc** để chức năng chính hoạt động không?
2. Nếu không có bean, hành vi của service có được xác định rõ và an toàn không?
3. Có thể dùng **No-op implementation** để tránh null branch không?
4. Nếu dùng **Optional<T>**, code có thể biểu diễn sự vắng mặt rõ hơn không?
5. Setter được gọi khi khởi tạo hay có ai được phép gọi lại sau khi ứng dụng chạy?
6. Nếu thay dependency runtime, có cần đồng bộ thread, xác thực provider mới và đóng tài nguyên cũ không?
7. Dependency này có thể là cấu hình kiểu **@ConfigurationProperties** thay vì một object được thay thế không?
8. Có phải class đang có quá nhiều dependency vì nó gánh quá nhiều trách nhiệm không?

Nếu dependency là bắt buộc và object không có trạng thái hợp lệ khi thiếu nó, constructor injection thường là câu trả lời. Nếu dependency thực sự là tính năng bổ sung, setter/Optional/No-op có thể phù hợp. Nếu cần thay đổi runtime, hãy thiết kế rõ cơ chế reconfiguration thay vì dựa vào một setter công khai.

## Kết luận

**Setter injection** cho phép Spring truyền dependency sau khi constructor đã tạo object. Nó hữu ích khi một collaborator thực sự tùy chọn, hoặc khi một đối tượng cần API setter để nhận cấu hình mutable theo một quy trình xác định. Với Spring, có thể biểu diễn optional dependency bằng **@Autowired(required = false)**, **Optional<T>**, **@Nullable**, **ObjectProvider<T>** hoặc một implementation mặc định kiểu **No-op**.

Hãy dùng **constructor injection cho dependency bắt buộc**, vì nó làm rõ điều kiện để object tồn tại hợp lệ. Chỉ dùng setter khi lợi ích của tính tùy chọn hoặc khả năng thay đổi thực sự cần thiết và trạng thái vắng mặt đã được xử lý.

Cuối cùng, **setter injection không đồng nghĩa với runtime reconfiguration**. Spring gọi setter trong quá trình wiring bean; muốn thay đổi dependency khi ứng dụng đang chạy phải có cơ chế riêng để kiểm soát quyền thay đổi, tính đồng thời, tính hợp lệ và vòng đời của implementation mới. Giữ rõ ranh giới này giúp ứng dụng Spring Boot linh hoạt mà vẫn dễ dự đoán và bảo trì.
