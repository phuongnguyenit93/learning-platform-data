# ReflectionTestUtils và giới hạn phụ thuộc chi tiết riêng tư

Trong kiểm thử Spring, đôi khi ta cần chuẩn bị hoặc quan sát một trạng thái nằm trong field không public, gọi một phương thức không public của mã cũ, hoặc thiết lập một dependency được inject trực tiếp vào field. Spring Test cung cấp **ReflectionTestUtils** để thực hiện những thao tác đó thuận tiện hơn so với tự viết Java Reflection.

Tuy nhiên, khả năng truy cập thành phần private không có nghĩa đó là cách kiểm thử nên dùng thường xuyên. Khi test phụ thuộc vào tên field, tên phương thức private hoặc cấu trúc nội bộ của class, một refactor không làm thay đổi hành vi vẫn có thể khiến test thất bại. Việc ghi trực tiếp vào field cũng có thể bỏ qua constructor, setter, validation, dependency injection và lifecycle mà ứng dụng thật sử dụng.

Bài học này giải thích ReflectionTestUtils làm được gì, khi nào nó hữu ích, cách sử dụng trong unit test và Spring test, cũng như những giới hạn cần cân nhắc. Mục tiêu là chọn được cách kiểm thử tạo ra bằng chứng đáng tin cậy mà không làm bộ test phụ thuộc quá sâu vào chi tiết riêng tư.

## 1. ReflectionTestUtils là gì?

**ReflectionTestUtils** là tiện ích thuộc module Spring Test, nằm trong package:

~~~java
import org.springframework.test.util.ReflectionTestUtils;
~~~

Nó cung cấp các phương thức tĩnh để đọc hoặc ghi field, gọi một số phương thức không public và hỗ trợ một số tình huống làm việc với đối tượng do Spring quản lý. Thay vì tự tìm Field hoặc Method, gọi setAccessible và xử lý class hierarchy, test có thể dùng API có sẵn.

Những thao tác thường gặp:

| Nhu cầu | Phương thức thường dùng | Ý nghĩa |
| --- | --- | --- |
| Ghi field | setField(target, name, value) | Gán giá trị cho field, kể cả field không public |
| Đọc field | getField(target, name) | Đọc giá trị field để kiểm tra hoặc chẩn đoán |
| Gọi phương thức | invokeMethod(target, name, args...) | Gọi phương thức trên đối tượng, kể cả một số phương thức không public |
| Gọi getter | invokeGetterMethod(target, name) | Gọi getter theo tên thuộc tính |
| Gọi setter | invokeSetterMethod(target, name, value) | Gọi setter theo tên thuộc tính |

API còn có các overload nhận kiểu hoặc class khai báo để xử lý trường hợp cần xác định field hoặc method cụ thể. Hãy xem Javadoc đúng phiên bản Spring của dự án khi cần dùng overload chuyên biệt.

ReflectionTestUtils là công cụ hỗ trợ kiểm thử. Nó không thay thế Spring ApplicationContext, BeanFactory, dependency injection hoặc lifecycle của bean. Gọi setField không đồng nghĩa với việc Spring đã inject bean đó; gọi invokeMethod không chứng minh request thật sẽ đi qua controller, proxy hoặc interceptor.

## 2. Khi nào ReflectionTestUtils có ích?

ReflectionTestUtils phù hợp nhất với những trường hợp có ranh giới rõ và không dễ thiết lập bằng API công khai:

- Kiểm thử mã legacy có field được inject trực tiếp và chưa thể refactor ngay.
- Thiết lập một field private chứa cấu hình trong unit test cô lập.
- Gán một giá trị định danh hoặc trạng thái cho fixture khi không có factory phù hợp và việc gán không làm sai mục tiêu test.
- Đọc một field nội bộ trong một tình huống chẩn đoán hẹp khi không có cách quan sát phù hợp hơn.
- Hỗ trợ kiểm thử một phương thức không public trong mã cũ khi chưa thể tách logic hoặc kiểm tra qua API công khai.

Trước khi dùng, hãy xác định vì sao trạng thái đó không thể được thiết lập qua constructor, builder, factory, setter hoặc cấu hình Spring. Nếu một cách công khai đơn giản đã có, hãy ưu tiên cách đó.

### 2.1. Ví dụ: field cấu hình được inject bằng @Value

Giả sử một class legacy nhận thuế suất qua field private:

~~~java
class LegacyPricingService {

    @Value("${pricing.tax-rate}")
    private BigDecimal taxRate;

    BigDecimal calculateTax(BigDecimal amount) {
        return amount.multiply(taxRate);
    }
}
~~~

Trong unit test chỉ muốn kiểm tra phép tính, ta có thể tạo đối tượng trực tiếp rồi gán field:

~~~java
class LegacyPricingServiceTest {

    @Test
    void calculates_tax_using_configured_rate() {
        LegacyPricingService service = new LegacyPricingService();
        ReflectionTestUtils.setField(
            service,
            "taxRate",
            new BigDecimal("0.10")
        );

        BigDecimal tax = service.calculateTax(new BigDecimal("100.00"));

        assertThat(tax).isEqualByComparingTo("10.00");
    }
}
~~~

Test này có thể hữu ích khi đang kiểm tra một class cũ mà field injection là cấu trúc hiện có. Nhưng cần hiểu điều test chứng minh: phép tính sử dụng giá trị đã được gán vào field. Test không chứng minh Spring đọc đúng property pricing.tax-rate, chuyển kiểu dữ liệu chính xác, inject đúng bean hoặc chạy lifecycle đúng.

Nếu mục tiêu là xác minh cấu hình Spring, hãy tạo test context và cung cấp property:

~~~java
@SpringBootTest(properties = "pricing.tax-rate=0.10")
class PricingConfigurationTest {

    @Autowired
    LegacyPricingService pricingService;

    @Test
    void uses_tax_rate_from_application_configuration() {
        BigDecimal tax =
            pricingService.calculateTax(new BigDecimal("100.00"));

        assertThat(tax).isEqualByComparingTo("10.00");
    }
}
~~~

Ở đây Spring tạo bean, đọc property và thực hiện injection theo cơ chế thật. Tầng test được chọn theo mục tiêu: unit test cho phép tính, Spring test cho cấu hình và wiring.

### 2.2. Ví dụ: field dependency được inject trực tiếp

Một class legacy có thể dùng field injection:

~~~java
class LegacyOrderService {

    @Autowired
    private OrderRepository orderRepository;

    Order findOrder(String id) {
        return orderRepository.findById(id).orElseThrow();
    }
}
~~~

Nếu chưa thể sửa production code, unit test có thể thiết lập repository:

~~~java
@ExtendWith(MockitoExtension.class)
class LegacyOrderServiceTest {

    @Mock
    OrderRepository orderRepository;

    @Test
    void returns_order_found_by_repository() {
        LegacyOrderService service = new LegacyOrderService();
        Order expected = OrderFixtures.order("ORDER-1");

        ReflectionTestUtils.setField(
            service,
            "orderRepository",
            orderRepository
        );
        when(orderRepository.findById("ORDER-1"))
            .thenReturn(Optional.of(expected));

        Order actual = service.findOrder("ORDER-1");

        assertThat(actual).isSameAs(expected);
    }
}
~~~

Đây là một cách tương thích với mã legacy. Với code mới, constructor injection thường tốt hơn:

~~~java
class OrderService {
    private final OrderRepository orderRepository;

    OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    Order findOrder(String id) {
        return orderRepository.findById(id).orElseThrow();
    }
}
~~~

Unit test lúc này chỉ cần truyền mock vào constructor. Dependency hiện rõ, object không thể được tạo trong trạng thái thiếu repository, và test không phụ thuộc tên field riêng tư.

## 3. Ghi và đọc field

### 3.1. Ghi một field không public

Ví dụ:

~~~java
class RetryPolicy {
    private int maxAttempts;

    boolean canRetry(int attempt) {
        return attempt < maxAttempts;
    }
}
~~~

Test có thể chuẩn bị giá trị:

~~~java
RetryPolicy policy = new RetryPolicy();
ReflectionTestUtils.setField(policy, "maxAttempts", 3);

assertThat(policy.canRetry(2)).isTrue();
assertThat(policy.canRetry(3)).isFalse();
~~~

Phương thức setField giúp tránh việc test tự tìm field bằng Java Reflection. Tuy nhiên, ví dụ này cũng gợi ý một câu hỏi thiết kế: nếu maxAttempts là cấu hình cần thiết để RetryPolicy hoạt động, có thể đưa nó vào constructor hoặc một configuration object để trạng thái hợp lệ được thiết lập ngay khi tạo object.

### 3.2. Đọc một field

ReflectionTestUtils.getField trả về giá trị dưới dạng Object, do đó test cần chuyển về kiểu phù hợp:

~~~java
Object value = ReflectionTestUtils.getField(policy, "maxAttempts");
assertThat(value).isEqualTo(3);
~~~

Đọc field thường ít cần thiết hơn đọc kết quả qua API công khai. Nếu test phải đọc nhiều field private để xác nhận một nghiệp vụ, có thể class đang thiếu một hành vi quan sát được hoặc test đang kiểm tra quá sâu vào cấu trúc nội bộ.

### 3.3. Field nằm trong lớp cha

Một field có thể được khai báo ở lớp cha thay vì lớp cụ thể đang kiểm thử. ReflectionTestUtils có overload nhận class khai báo để chỉ rõ field cần truy cập:

~~~java
class BaseJob {
    private Duration timeout;
}

class ScheduledJob extends BaseJob {
    private Duration timeout;
}
~~~

Khi có field trùng tên trong hierarchy, việc chỉ truyền tên có thể không thể hiện rõ ý định. Có thể chỉ định class khai báo:

~~~java
ReflectionTestUtils.setField(
    scheduledJob,
    BaseJob.class,
    "timeout",
    Duration.ofSeconds(5)
);
~~~

Hãy dùng overload này khi thực sự cần phân biệt field ở lớp cha và lớp con. Nếu test thường xuyên phải truy cập field kế thừa hoặc field bị che khuất, nên xem lại thiết kế fixture và hierarchy.

### 3.4. Không dùng field access để kiểm tra mọi trạng thái

Ví dụ, thay vì đọc field private status để kiểm tra đơn hàng đã hoàn tất, hãy ưu tiên phương thức nghiệp vụ hoặc repository trả về trạng thái mà caller có thể quan sát:

~~~java
Order order = service.completeOrder("ORDER-1");

assertThat(order.status()).isEqualTo(OrderStatus.COMPLETED);
~~~

Nếu class không trả kết quả nhưng có API công khai để truy vấn, hãy dùng API đó. Nếu cần xác minh trạng thái được lưu, hãy đọc qua repository hoặc giao diện persistence tương ứng. Chỉ đọc trực tiếp field private khi trạng thái nội bộ là chi tiết cần chẩn đoán và không có cách quan sát hợp lý hơn.

## 4. Gọi phương thức không public

ReflectionTestUtils.invokeMethod có thể gọi phương thức theo tên trên đối tượng, kể cả một số phương thức private hoặc protected. Điều này có thể hỗ trợ mã cũ, nhưng cần phân biệt khả năng kỹ thuật với mục tiêu kiểm thử tốt.

Ví dụ class có helper private:

~~~java
class LegacyNameFormatter {

    String format(String rawName) {
        return normalize(rawName);
    }

    private String normalize(String value) {
        return value == null ? "" : value.trim().replaceAll("\\s+", " ");
    }
}
~~~

Một test theo hành vi công khai nên gọi format:

~~~java
@Test
void format_trims_and_collapses_whitespace() {
    LegacyNameFormatter formatter = new LegacyNameFormatter();

    assertThat(formatter.format("  Spring   Framework  "))
        .isEqualTo("Spring Framework");
}
~~~

Nếu cần chẩn đoán riêng một nhánh legacy trong thời gian ngắn, có thể gọi helper:

~~~java
String normalized = ReflectionTestUtils.invokeMethod(
    formatter,
    "normalize",
    "  Spring   Framework  "
);
~~~

Không nên biến test gọi normalize thành test chính thức dài hạn nếu normalize chỉ là chi tiết triển khai. Nếu helper đổi tên, gộp vào phương thức khác hoặc thay thuật toán nhưng format vẫn giữ đúng hợp đồng, test gọi private method sẽ thất bại dù người dùng không nhận thấy thay đổi nào.

### 4.1. Vì sao kiểm thử private method thường tạo coupling?

Một phương thức private không phải hợp đồng công khai của class. Nó có thể được:

- Đổi tên.
- Chia thành nhiều helper nhỏ.
- Gộp vào phương thức khác.
- Thay bằng một collaborator.
- Thay thuật toán nhưng giữ nguyên kết quả bên ngoài.

Test gọi trực tiếp private method phải biết tên, tham số và cách tổ chức nội bộ. Điều đó làm tăng chi phí refactor. Một test tốt thường xác nhận hành vi qua public API hoặc qua ranh giới domain/application đã được thiết kế rõ.

Nếu private method chứa một thuật toán đủ phức tạp để cần nhiều test riêng, hãy cân nhắc trích xuất thuật toán thành một class hoặc collaborator có trách nhiệm riêng. Khi đó, test có thể gọi API công khai của collaborator mới mà không phải mở private implementation của class ban đầu.

### 4.2. Khi nào gọi private method có thể chấp nhận được?

Một số tình huống legacy có thể chưa thể refactor vì rủi ro, phạm vi hoặc giới hạn thời gian. Trong trường hợp đó, ReflectionTestUtils có thể giúp:

- Khoanh vùng lỗi trong một helper cụ thể.
- Kiểm tra một trường hợp khó tạo qua public API.
- Tạo bằng chứng tạm thời trong quá trình thay thế dần mã cũ.

Hãy ghi nhận vì sao test cần đi qua private method, giới hạn của nó và điều kiện để loại bỏ. Tránh tạo một bộ test lớn khóa chặt mọi helper private.

## 5. Gọi getter và setter qua ReflectionTestUtils

ReflectionTestUtils cũng cung cấp invokeGetterMethod và invokeSetterMethod. Các phương thức này có thể hữu ích khi làm việc với object cũ hoặc property accessor không public.

Ví dụ:

~~~java
class LegacySettings {
    private int threshold;

    private void setThreshold(int threshold) {
        if (threshold < 0) {
            throw new IllegalArgumentException("threshold must be non-negative");
        }
        this.threshold = threshold;
    }

    private int getThreshold() {
        return threshold;
    }
}
~~~

Test có thể gọi accessor:

~~~java
LegacySettings settings = new LegacySettings();
ReflectionTestUtils.invokeSetterMethod(settings, "threshold", 5);

Object threshold =
    ReflectionTestUtils.invokeGetterMethod(settings, "threshold");

assertThat(threshold).isEqualTo(5);
~~~

Nếu setter có validation hoặc side effect, gọi setter giữ lại logic đó tốt hơn việc setField trực tiếp. Nhưng nếu setter private, đây vẫn là một truy cập vào chi tiết không public. Với code mới, hãy cân nhắc constructor hoặc API phù hợp để thiết lập trạng thái hợp lệ.

Không nên dùng ReflectionTestUtils để ép gọi setter nhằm né thiết kế không rõ ràng. Nếu một property là một phần hợp đồng của class, cân nhắc biểu diễn nó bằng constructor, method công khai hoặc configuration object.

## 6. ReflectionTestUtils và Java Reflection thuần

Java Reflection cho phép khám phá class, field, method và annotation lúc chạy. ReflectionTestUtils cung cấp các thao tác kiểm thử thường dùng dựa trên cơ chế reflection của Java và tiện ích nội bộ của Spring.

| Khía cạnh | Java Reflection trực tiếp | ReflectionTestUtils |
| --- | --- | --- |
| Tìm field/method | Tự dùng Class, Field, Method | Có API theo tên field/method |
| Truy cập thành phần không public | Tự xử lý accessibility | Hỗ trợ các thao tác kiểm thử phổ biến |
| Class hierarchy | Tự duyệt lớp cha/lớp con | Có overload hỗ trợ chỉ định class |
| Proxy Spring | Tự xử lý proxy và target | Có hỗ trợ cho một số trường hợp proxy của Spring |
| Mục đích | Cơ chế runtime tổng quát | Tiện ích dành cho test |
| Thiết kế kiểm thử | Không quyết định test có tốt hay không | Cũng không quyết định test có tốt hay không |

ReflectionTestUtils giúp giảm mã phụ trợ, nhưng không loại bỏ giới hạn của reflection. Nó không làm private field trở thành API ổn định, không bảo đảm một object có trạng thái hợp lệ, và không tái tạo các bước mà Spring thực hiện khi tạo bean.

## 7. Những giới hạn quan trọng

### 7.1. Test phụ thuộc tên field và tên method

Khi test viết:

~~~java
ReflectionTestUtils.setField(service, "paymentGateway", gateway);
~~~

test phụ thuộc vào tên field paymentGateway. Nếu field được đổi tên nhưng constructor và hành vi không đổi, test có thể thất bại. Tương tự, invokeMethod phụ thuộc tên và chữ ký phương thức.

Đây là một dạng coupling vào implementation. Hãy dùng reflection ở phạm vi hẹp, tránh lặp tên private field ở nhiều test và ưu tiên constructor injection hoặc fixture factory.

### 7.2. Bỏ qua constructor và bất biến của object

Constructor có thể kiểm tra tham số, chuẩn hóa dữ liệu hoặc bảo đảm các dependency bắt buộc tồn tại. Gán field sau khi object đã được tạo có thể bỏ qua những điều kiện đó.

Ví dụ, một đối tượng có thể yêu cầu limit phải lớn hơn 0. Nếu test setField trực tiếp giá trị -1, test đang tạo một trạng thái mà production code không cho phép tạo qua constructor hoặc API công khai.

Hãy dùng constructor, builder hoặc factory để tạo trạng thái hợp lệ. Chỉ dùng reflection nếu test thực sự cần tạo một trạng thái legacy hoặc trạng thái lỗi mà không thể tạo bằng đường đi công khai và mục tiêu kiểm thử đòi hỏi điều đó.

### 7.3. Bỏ qua dependency injection và chuyển đổi cấu hình

Gán một field có annotation @Autowired hoặc @Value không kiểm tra:

- Spring có tìm đúng bean hay không.
- Qualifier có được áp dụng không.
- Property có được đọc từ đúng nguồn không.
- String có được chuyển thành kiểu cần thiết không.
- Bean post-processor có can thiệp không.
- Profile hoặc condition có chọn đúng cấu hình không.

Nếu mục tiêu là kiểm tra các hành vi này, hãy để Spring tạo bean trong ApplicationContext và cung cấp cấu hình test. ReflectionTestUtils chỉ nên hỗ trợ unit test cô lập cho phần logic, không thay thế test wiring.

### 7.4. Bỏ qua lifecycle của Spring

Một bean Spring có thể trải qua constructor, dependency injection, BeanPostProcessor, initialization callback, @PostConstruct và các bước khác trước khi sẵn sàng sử dụng.

Nếu test tự tạo object bằng new rồi setField, những bước này không tự chạy. Một object có thể thiếu trạng thái mà bean thật được thiết lập trong lifecycle.

Khi lifecycle là điều cần kiểm tra, hãy dùng Spring test context. Nếu chỉ kiểm tra logic thuần của object, hãy tạo fixture rõ ràng và không giả định object đã trải qua Spring lifecycle.

### 7.5. Bỏ qua setter validation và side effect

setField ghi trực tiếp vào field. Nó không gọi setter, không thực hiện logic chuẩn hóa trong setter và không kích hoạt side effect mà setter có thể chứa.

Ví dụ, setter có thể từ chối số âm hoặc cập nhật một field dẫn xuất. Nếu setField trực tiếp, object có thể rơi vào trạng thái không nhất quán.

Khi setter là API hợp lệ để cấu hình object, hãy gọi setter hoặc constructor. Khi muốn kiểm tra setter, hãy gọi nó qua API phù hợp và xác nhận kết quả.

### 7.6. Không chứng minh proxy và AOP behavior

Spring có thể bọc bean bằng proxy để áp dụng transaction, security, caching, retry hoặc advice khác. Một thao tác reflection trên target object không chứng minh lời gọi đã đi qua proxy và các advice đã được áp dụng.

Nếu mục tiêu là xác minh @Transactional, @PreAuthorize, @Cacheable hoặc một advice, hãy lấy bean từ ApplicationContext và gọi phương thức qua bean mà Spring cung cấp. Sau đó kiểm tra hiệu ứng bên ngoài, chẳng hạn rollback, access denied hoặc cache behavior.

Một số thao tác của Spring test có thể xử lý đối tượng proxy để truy cập target. Điều đó hữu ích cho việc thiết lập fixture trong trường hợp cụ thể, nhưng cũng có nghĩa test cần cẩn thận: truy cập target không tương đương với gọi qua proxy. Đừng dùng ReflectionTestUtils để kết luận interceptor hoạt động đúng.

### 7.7. Field final, static và giới hạn của JVM

Reflection không phải lúc nào cũng có thể thay đổi mọi field. Field final, field thuộc class của JDK hoặc module bị đóng có thể chịu giới hạn truy cập của JVM. Khả năng truy cập phụ thuộc phiên bản Java, module system và cách class được đóng gói.

Không nên dựa vào việc sửa static final field hoặc trạng thái static toàn cục để tạo test. Cách đó có thể không hoạt động trên JDK hiện đại, ảnh hưởng các test chạy song song và làm trạng thái rò rỉ giữa các test.

Nếu cần thay một giá trị có thể thay đổi, hãy đưa nó thành dependency có thể inject như Clock, configuration object hoặc interface. Không dùng reflection để mở khóa nội bộ của JDK.

### 7.8. Overload và kiểu tham số có thể gây mơ hồ

Khi một class có nhiều method cùng tên, việc tìm method theo tên và các đối số có thể cần phân biệt kiểu tham số. Đối số null hoặc các kiểu tham số kế thừa có thể khiến việc chọn overload không rõ ràng.

Hãy tránh thiết kế test phụ thuộc vào một lời gọi reflection mơ hồ. Nếu cần overload cụ thể, xem Javadoc của phiên bản Spring đang dùng để chọn overload nhận kiểu tham số hoặc class khai báo. Với mã mới, gọi API công khai có kiểu tĩnh thường an toàn và dễ đọc hơn.

### 7.9. Truy cập private không đảm bảo test có ý nghĩa

Một test có thể truy cập được field private nhưng vẫn không chứng minh điều gì quan trọng với người dùng. Ví dụ, kiểm tra một biến boolean nội bộ đã đổi thành true không chứng minh API trả đúng kết quả hoặc transaction đã commit.

Hãy xác định bằng chứng cần có trước khi chọn công cụ. Nếu hành vi quan sát được đã đủ, không cần đọc field private.

## 8. Những cách thay thế nên cân nhắc

ReflectionTestUtils không phải lựa chọn đầu tiên cho mọi tình huống. Có một số cách khác giúp test ít phụ thuộc implementation hơn.

### 8.1. Constructor injection

Với dependency bắt buộc, constructor injection giúp object không thể được tạo thiếu collaborator:

~~~java
class InvoiceService {
    private final InvoiceRepository repository;
    private final Clock clock;

    InvoiceService(InvoiceRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }
}
~~~

Unit test có thể truyền mock, fake và fixed Clock trực tiếp. Không cần truy cập field private và không phụ thuộc tên field.

### 8.2. Builder hoặc fixture factory

Với domain object có nhiều thuộc tính, builder hoặc factory giúp tạo trạng thái hợp lệ và thể hiện rõ dữ liệu quan trọng:

~~~java
Invoice invoice = InvoiceFixtures.validInvoice()
    .withStatus(InvoiceStatus.PENDING)
    .withTotal(new BigDecimal("250.00"));
~~~

Factory nên giữ mặc định đơn giản và cho phép test ghi đè các thuộc tính quyết định tình huống. Tránh factory quá thông minh đến mức che giấu dữ liệu mà test đang kiểm tra.

### 8.3. Configuration properties

Nếu một class có nhiều giá trị cấu hình, gom chúng vào một đối tượng @ConfigurationProperties thường rõ ràng hơn nhiều field @Value riêng lẻ:

~~~java
@ConfigurationProperties(prefix = "pricing")
public record PricingProperties(BigDecimal taxRate, int maxItems) {}
~~~

Test logic có thể tạo PricingProperties trực tiếp. Test cấu hình có thể dùng Spring context và property values để xác nhận binding. Cách này tách logic khỏi cơ chế đọc property.

### 8.4. Package-private collaborator hoặc domain service

Nếu private helper chứa logic đáng kể, có thể trích xuất thành class riêng với API phù hợp trong package. Class mới có thể được kiểm thử qua public API của chính nó mà không mở private method của class cũ.

Không nên tăng visibility chỉ để test gọi được một helper. Hãy trích xuất khi logic có trách nhiệm riêng, có tên miền rõ và được tái sử dụng hoặc cần được kiểm thử độc lập.

### 8.5. Spring test context

Khi mục tiêu là injection, configuration, lifecycle hoặc AOP, hãy dùng Spring test context. Ví dụ:

~~~java
@SpringBootTest(properties = {
    "pricing.tax-rate=0.10",
    "pricing.max-items=5"
})
class PricingServiceContextTest {
    @Autowired
    PricingService pricingService;
}
~~~

Test này tốn thời gian hơn unit test nhưng cung cấp bằng chứng về bean wiring và property binding thật. Chỉ dùng context đầy đủ khi cần; với một slice nhỏ, các test annotation chuyên biệt có thể phù hợp hơn.

## 9. Chọn phương án theo mục tiêu kiểm thử

| Mục tiêu | Cách ưu tiên | Vai trò của ReflectionTestUtils |
| --- | --- | --- |
| Kiểm tra kết quả nghiệp vụ qua public API | Gọi API công khai, assert output/state | Thường không cần |
| Thiết lập dependency cho unit test | Constructor injection, fake hoặc mock | Có thể dùng tạm cho mã field injection legacy |
| Kiểm tra property binding | Spring test context và test properties | Không thay thế context |
| Kiểm tra JPA mapping hoặc query | @DataJpaTest và database test | Không thay repository bằng reflection |
| Kiểm tra transaction/AOP/security | Gọi bean qua Spring proxy và kiểm tra hiệu ứng | Tránh truy cập target để kết luận advice |
| Tạo fixture có ID hoặc trạng thái legacy | Factory/builder nếu có | Có thể dùng trong trường hợp hẹp |
| Kiểm tra private helper | Kiểm tra qua public API hoặc trích xuất collaborator | Chỉ cân nhắc cho legacy/diagnostic |
| Chẩn đoán trạng thái nội bộ khó quan sát | Thêm API quan sát phù hợp hoặc debug | Có thể đọc field tạm thời |

### 9.1. Ví dụ: kiểm tra @Transactional

Giả sử một service có phương thức ghi hai bản ghi trong cùng transaction và phát sinh lỗi sau thao tác thứ nhất. Nếu mục tiêu là kiểm tra rollback, việc tự tạo service rồi dùng ReflectionTestUtils setField vào repository không đủ.

Test cần:

1. Khởi động Spring context có transaction manager thật.
2. Lấy service bean từ ApplicationContext.
3. Gọi phương thức qua bean Spring.
4. Đọc lại dữ liệu qua repository hoặc một transaction phù hợp.
5. Xác nhận cả hai thao tác ghi được rollback theo hợp đồng.

Nếu test gọi trực tiếp target object, bỏ qua proxy hoặc transaction interceptor, nó không kiểm tra được hành vi mà @Transactional cung cấp.

### 9.2. Ví dụ: kiểm tra validation của cấu hình

Nếu một configuration property phải nằm trong khoảng hợp lệ, không nên set field private rồi chỉ kiểm tra logic sử dụng nó. Hãy kiểm tra cơ chế binding và validation trong Spring context, hoặc tạo configuration object trực tiếp để kiểm tra validator tương ứng.

Hai bài test có thể bổ sung cho nhau:

- Unit test xác nhận logic nghiệp vụ phản ứng đúng với configuration object hợp lệ.
- Context test xác nhận property bên ngoài được bind và từ chối khi sai theo hợp đồng.

## 10. Những lỗi thường gặp khi dùng ReflectionTestUtils

### Dùng reflection để né constructor

Nếu test phải set nhiều field private sau khi tạo object, class có thể đang có quá nhiều dependency hoặc thiếu constructor phù hợp. Hãy xem lại thiết kế trước khi thêm nhiều thao tác setField.

### Dùng reflection để kiểm tra private method thay vì hành vi

Test gọi private helper thường thất bại khi refactor dù behavior không đổi. Hãy gọi public API hoặc trích xuất logic có trách nhiệm riêng.

### Set field nhưng quên lifecycle

Object được tạo bằng new không tự chạy @Autowired, @Value, @PostConstruct hoặc BeanPostProcessor. Nếu test phụ thuộc lifecycle, hãy dùng Spring context.

### Set field bỏ qua validation

Gán trực tiếp có thể tạo trạng thái không thể xuất hiện qua API thật. Hãy tạo dữ liệu hợp lệ bằng constructor, factory hoặc setter có quy tắc.

### Đọc field private để assertion mọi thứ

Assertion nên tập trung vào output và trạng thái mà hợp đồng cho phép quan sát. Đọc quá nhiều field private làm test phụ thuộc cấu trúc dữ liệu nội bộ.

### Dùng reflection trên bean proxy để kiểm tra advice

Truy cập target không chứng minh lời gọi đi qua proxy. Hãy gọi bean được Spring quản lý và xác minh tác động như rollback, quyền truy cập hoặc cache.

### Dùng reflection để thay static state dùng chung

Static state có thể rò rỉ giữa test và gây lỗi khi chạy song song. Hãy inject dependency có thể thay thế và tạo mới cho từng test.

## 11. Quy trình thực hành

Trước khi dùng ReflectionTestUtils, hãy đi qua quy trình sau:

**Bước 1 – Xác định hành vi cần kiểm chứng.** Viết rõ điều kiện ban đầu, hành động và kết quả cần quan sát.

**Bước 2 – Xác định SUT và ranh giới.** Nêu rõ class hoặc luồng nào đang được kiểm tra, collaborator nào thuộc phạm vi và hệ thống ngoài nào cần kiểm soát.

**Bước 3 – Tìm cách thiết lập công khai.** Kiểm tra constructor, builder, factory, setter, configuration object hoặc API tạo fixture.

**Bước 4 – Chọn tầng test.** Dùng unit test cho logic cô lập; dùng Spring context khi cần xác minh injection, lifecycle, configuration hoặc AOP.

**Bước 5 – Nếu vẫn cần reflection, giới hạn phạm vi.** Chỉ truy cập field hoặc method cần thiết, dùng tên rõ ràng và tránh tạo helper reflection dùng chung quá rộng.

**Bước 6 – Ghi rõ điều test không chứng minh.** Ví dụ, setField vào @Value field không chứng minh property binding; gọi private helper không chứng minh public contract; đọc target không chứng minh proxy advice.

**Bước 7 – Ưu tiên assertion hành vi.** Kiểm tra kết quả trả về, dữ liệu lưu và side effect có ý nghĩa. Chỉ đọc private state khi không có bằng chứng phù hợp hơn.

**Bước 8 – Xem xét khả năng loại bỏ reflection.** Nếu test thường xuyên cần truy cập nội bộ, cân nhắc constructor injection, configuration properties, collaborator hoặc fixture factory.

## 12. Mẫu quyết định ngắn

Có thể dùng các câu hỏi sau khi review một test:

| Câu hỏi | Hướng xử lý |
| --- | --- |
| Test có thể thiết lập trạng thái qua constructor hoặc factory không? | Ưu tiên cách đó |
| Mục tiêu có phải là kiểm tra Spring injection hoặc lifecycle không? | Dùng Spring test context |
| Mục tiêu có phải là kiểm tra AOP, transaction hoặc security proxy không? | Gọi bean qua proxy |
| Test đang gọi private method vì helper quá phức tạp? | Cân nhắc trích xuất collaborator |
| Reflection chỉ dùng để chuẩn bị fixture legacy? | Có thể chấp nhận trong phạm vi hẹp |
| Test đọc nhiều field private để xác nhận nghiệp vụ? | Tìm cách kiểm tra qua API hoặc trạng thái được lưu |
| Refactor đổi tên field có làm test hỏng dù behavior không đổi? | Test đang coupling vào implementation |

## Kết luận

ReflectionTestUtils là công cụ hữu ích để đọc, ghi field hoặc gọi phương thức không public trong những tình huống kiểm thử cần thiết, đặc biệt khi xử lý mã legacy. Nó giúp giảm mã Java Reflection thủ công, nhưng không biến chi tiết private thành hợp đồng ổn định và không tái tạo dependency injection, lifecycle, validation hoặc AOP của Spring.

Hãy ưu tiên kiểm thử qua API công khai, constructor injection, fixture factory và Spring test context đúng mục tiêu. Chỉ dùng ReflectionTestUtils khi có lý do cụ thể, giới hạn số điểm truy cập và hiểu rõ phần hành vi mà test không kiểm chứng được. Một bài kiểm thử tốt phải bảo vệ hành vi có ý nghĩa, đồng thời cho phép cấu trúc nội bộ được refactor mà không làm mất giá trị của bộ test.
