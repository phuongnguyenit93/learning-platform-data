# Chọn bean thật, bean thử nghiệm hoặc Mockito mock

Khi kiểm thử ứng dụng Spring, một dependency có thể được cung cấp bằng bean thật của ứng dụng, một bean thay thế được viết riêng cho test hoặc một Mockito mock. Mỗi lựa chọn phục vụ một mục tiêu khác nhau. Bean thật giúp kiểm tra cách các thành phần phối hợp trong cấu hình gần với ứng dụng; bean thử nghiệm giúp kiểm soát dữ liệu và hành vi theo cách đơn giản, ổn định; Mockito mock giúp mô phỏng phản hồi của dependency và xác minh tương tác tại một ranh giới cụ thể.

Chọn sai loại bean có thể làm bài kiểm thử chậm, khó thiết lập hoặc kiểm tra nhầm hành vi. Ví dụ, mock repository trong một bài kiểm thử nhằm xác nhận mapping và truy vấn database sẽ bỏ qua chính phần cần kiểm tra. Ngược lại, dùng database thật và khởi tạo toàn bộ application context cho một quy tắc tính phí đơn giản sẽ làm unit test phụ thuộc vào nhiều thành phần không liên quan.

## 1. Ba lựa chọn và mục đích của chúng

### 1.1. Bean thật

Bean thật là implementation mà ứng dụng sử dụng khi chạy bình thường. Khi test khởi tạo Spring context và inject bean này, bài kiểm thử có thể xác nhận hành vi của nhiều thành phần cùng phối hợp: controller gọi service, service gọi repository, transaction được áp dụng và dữ liệu được lưu.

Ví dụ, `OrderService` sử dụng `OrderRepository` thật:

```java
@Service
class OrderService {

    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    Order create(String customerId) {
        return repository.save(new Order(customerId));
    }
}
```

Trong một bài kiểm thử tích hợp, có thể inject `OrderService` và repository thật để xác nhận dữ liệu thực sự được ghi. Nếu mục tiêu là kiểm tra persistence, repository thật và một database kiểm thử phù hợp là một phần quan trọng của bài test.

Bean thật phù hợp khi hành vi cần kiểm tra nằm trong chính implementation đó hoặc trong sự phối hợp giữa các thành phần. Đổi lại, test cần thiết lập các dependency mà bean thật yêu cầu, chẳng hạn database, file, message broker hoặc HTTP service. Những dependency ngoài tiến trình nên được cung cấp qua tài nguyên kiểm thử có vòng đời rõ ràng, ví dụ database container hoặc server giả lập.

### 1.2. Bean thử nghiệm (fake hoặc stub)

Bean thử nghiệm là một implementation được tạo riêng cho test và được đăng ký vào Spring context. Nó thường thực hiện một phần nhỏ của hợp đồng, lưu dữ liệu trong bộ nhớ hoặc trả về kết quả xác định trước. Fake và stub có thể là những bean thật về mặt Spring: Spring tạo chúng và inject chúng như các bean khác, nhưng logic bên trong được đơn giản hóa cho mục tiêu kiểm thử.

Ví dụ, ứng dụng dùng interface `PaymentGateway`, còn test cung cấp một implementation không gọi nhà cung cấp thanh toán thật:

```java
interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}

final class SuccessfulPaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(PaymentRequest request) {
        return new PaymentResult("TEST-PAYMENT", true);
    }
}
```

Bean này phù hợp khi nhiều test cần một hành vi ổn định, có thể đọc và tái sử dụng. Nó cũng hữu ích khi muốn giữ cấu trúc Spring context và kiểm tra luồng gọi qua interface mà không phụ thuộc dịch vụ bên ngoài.

Fake/stub thường tập trung vào kết quả trả về hoặc một mô hình đơn giản của dependency. Nó không nhất thiết ghi lại mọi lời gọi hay cung cấp khả năng verify tương tác như Mockito. Nếu test cần xác nhận chính xác method được gọi bao nhiêu lần, với đối số nào, Mockito mock thường phù hợp hơn.

### 1.3. Mockito mock

Mockito mock là đối tượng được Mockito tạo ra để thay thế dependency. Test có thể cấu hình phản hồi bằng `when(...).thenReturn(...)`, `thenThrow(...)` hoặc `doAnswer(...)`, rồi xác minh tương tác bằng `verify(...)`.

Ví dụ:

```java
PaymentGateway gateway = mock(PaymentGateway.class);
when(gateway.charge(any(PaymentRequest.class)))
        .thenReturn(new PaymentResult("TEST-1", true));

OrderService service = new OrderService(gateway);
```

Mock phù hợp khi cần cô lập một lớp khỏi dependency, mô phỏng tình huống thành công/thất bại và kiểm tra dữ liệu hoặc tương tác được gửi đi. Mockito mock không tự tạo một Spring bean; để thay bean trong Spring `ApplicationContext`, cần dùng cơ chế bean override của Spring Test như `@MockitoBean` hoặc annotation tương ứng theo phiên bản.

## 2. Phân biệt fake, stub, mock và bean thật

Các thuật ngữ test double thường được dùng gần nhau, nhưng chúng nhấn mạnh các mục đích khác nhau:

| Loại | Đặc điểm | Mục tiêu thường gặp |
|---|---|---|
| Real implementation | Logic sản phẩm thực tế | Kiểm tra hành vi thật hoặc tích hợp giữa các thành phần |
| Stub | Trả về dữ liệu được định trước | Điều khiển đầu vào gián tiếp của đối tượng đang kiểm thử |
| Fake | Implementation đơn giản nhưng có hành vi chạy được, thường lưu dữ liệu trong bộ nhớ | Thay một dependency nặng bằng mô hình nhỏ, dễ kiểm soát |
| Mockito mock | Đối tượng do Mockito tạo, có thể stub và verify | Kiểm tra tương tác và phản hồi của dependency |
| Mockito spy | Theo dõi một đối tượng thật, thường vẫn gọi hành vi thật trừ khi được stub | Kiểm tra hoặc thay một phần hành vi của đối tượng có sẵn |

Trong Spring, một fake hoặc stub có thể được đăng ký thành bean bằng `@TestConfiguration`. Mockito mock có thể được đưa vào context bằng `@MockitoBean`. Cả hai đều có thể thay dependency khi Spring inject, nhưng cách tạo và cách kiểm tra hành vi khác nhau.

Không nên chọn loại test double chỉ theo thói quen. Hãy bắt đầu từ câu hỏi: bài test cần xác nhận hành vi nào? Nếu cần xác nhận database lưu đúng dữ liệu, dùng persistence thật trong test phù hợp. Nếu cần kiểm tra service gửi đúng command sang cổng thanh toán, mock cổng đó và capture đối số. Nếu nhiều test cần một cổng giả có hành vi đơn giản, một fake bean có thể dễ bảo trì hơn nhiều đoạn stubbing.

## 3. Khi nào nên giữ bean thật?

Nên giữ bean thật khi implementation nằm trong phạm vi cần kiểm tra hoặc khi hành vi phụ thuộc vào cách các thành phần Spring phối hợp.

Các trường hợp thường gặp:

- Kiểm tra repository, JPA mapping, transaction hoặc truy vấn database.
- Kiểm tra cấu hình security, serialization, validation hoặc message conversion.
- Kiểm tra nhiều service phối hợp qua Spring context.
- Kiểm tra cấu hình `@Transactional`, `@Cacheable`, `@Async` hoặc các proxy do Spring tạo.
- Kiểm tra cấu hình application thực tế được lắp ghép từ component scan, configuration class và property.

Ví dụ, nếu muốn xác nhận `OrderService` lưu đơn hàng và transaction rollback khi một thao tác thất bại, cần chạy luồng với Spring và persistence phù hợp. Mock `OrderRepository` sẽ bỏ qua hành vi database và transaction mà bài test muốn bảo vệ.

Bean thật cũng phù hợp khi test cần xác nhận wiring. Một lỗi thiếu bean, sai qualifier hoặc cấu hình điều kiện có thể chỉ xuất hiện khi Spring tạo context. Unit test thuần Java không phát hiện được những lỗi wiring này vì nó không chạy container Spring.

Tuy nhiên, giữ tất cả dependency thật trong mọi bài test có thể khiến test phụ thuộc dịch vụ ngoài, tốn thời gian và khó tái hiện. Có thể giữ phần nằm trong phạm vi kiểm tra ở dạng thật và thay các ranh giới bên ngoài bằng fake hoặc mock.

## 4. Khi nào nên dùng bean thử nghiệm?

Bean thử nghiệm phù hợp khi cần một dependency thay thế có hành vi nhỏ, rõ ràng và có thể dùng lại trong nhiều bài test.

Ví dụ, một ứng dụng có interface đọc tỷ giá:

```java
interface ExchangeRateProvider {
    BigDecimal rate(String currency);
}
```

Test có thể dùng fake trả về tỷ giá xác định:

```java
final class FixedExchangeRateProvider implements ExchangeRateProvider {

    @Override
    public BigDecimal rate(String currency) {
        return switch (currency) {
            case "USD" -> new BigDecimal("1.00");
            case "EUR" -> new BigDecimal("1.08");
            default -> throw new IllegalArgumentException(
                    "Unsupported currency: " + currency
            );
        };
    }
}
```

Fake này có hành vi thực thi được và có quy tắc rõ ràng. Nó có thể phục vụ nhiều test mà không cần lặp lại `when(provider.rate("USD"))...` trong từng lớp.

Một stub đơn giản hơn có thể trả về một kết quả đã định trước, không mô phỏng toàn bộ quy tắc:

```java
final class StubExchangeRateProvider implements ExchangeRateProvider {

    private final BigDecimal configuredRate;

    StubExchangeRateProvider(BigDecimal configuredRate) {
        this.configuredRate = configuredRate;
    }

    @Override
    public BigDecimal rate(String currency) {
        return configuredRate;
    }
}
```

Stub này hữu ích khi test chỉ quan tâm đến cách service xử lý một tỷ giá cụ thể. Nếu cần kiểm tra service yêu cầu đúng mã tiền tệ nào, Mockito mock cùng `verify(...)` có thể diễn đạt ý định tốt hơn.

Nên dùng fake khi cần một mô hình nhỏ nhưng có hành vi nhất quán, chẳng hạn in-memory repository hoặc gateway giả. Nên dùng stub khi chỉ cần kiểm soát kết quả trả về. Tránh xây một fake quá phức tạp mô phỏng gần như toàn bộ implementation thật; khi đó, fake có thể trở thành một hệ thống riêng cần bảo trì và có nguy cơ khác hành vi sản phẩm.

## 5. Đăng ký bean thử nghiệm bằng @TestConfiguration

Trong Spring Boot, `@TestConfiguration` dùng để khai báo bean bổ sung cho test. Nó là một dạng `@Configuration` dành cho test và không được component scan thông thường tự động chọn như một cấu hình ứng dụng. Vì vậy, một lớp `@TestConfiguration` top-level thường được import rõ ràng bằng `@Import`.

Ví dụ cấu hình fake gateway:

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
class PaymentTestConfiguration {

    @Bean
    @Primary
    PaymentGateway paymentGateway() {
        return new SuccessfulPaymentGateway();
    }
}
```

Test class import cấu hình này:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(PaymentTestConfiguration.class)
class OrderPaymentIntegrationTest {
    // Spring injects the test PaymentGateway as the primary candidate.
}
```

`@Primary` yêu cầu Spring ưu tiên bean này khi cần chọn một bean theo kiểu `PaymentGateway` và có nhiều candidate. Cấu hình trên giúp `OrderService` nhận fake gateway trong khi các bean khác của ứng dụng vẫn được tạo theo cấu hình Spring Boot.

Nếu dự án chỉ dùng Spring Framework mà không dùng Spring Boot, có thể dùng một lớp `@Configuration` test riêng và import bằng `@Import` hoặc khai báo trong `@ContextConfiguration(classes = ...)`. `@TestConfiguration` thuộc Spring Boot Test; nó không phải annotation cấu hình của Spring Framework core.

### 5.1. Cẩn thận: @Primary không xóa bean thật

`@Primary` chỉ ảnh hưởng đến việc chọn candidate khi Spring cần inject một bean đơn lẻ theo kiểu. Nếu bean thật vẫn được đăng ký, context có thể chứa cả bean thật và fake.

Điều này có thể quan trọng trong các trường hợp:

- Một bean inject `List<PaymentGateway>` hoặc `Map<String, PaymentGateway>` sẽ nhìn thấy nhiều implementation.
- Một bean sử dụng `@Qualifier` hoặc tên bean cụ thể có thể chọn bean thật.
- Một thành phần khác lấy toàn bộ bean theo kiểu có thể sử dụng cả hai implementation.
- Có side effect khi bean thật được khởi tạo, dù nó không được chọn cho injection thông thường.

Vì vậy, `@Primary` phù hợp khi mục tiêu là ưu tiên fake trong một context có nhiều candidate và việc tồn tại song song là chấp nhận được. Nếu cần thay thế bean hiện hữu một cách rõ ràng, hãy dùng cơ chế bean override thích hợp như `@MockitoBean` hoặc `@TestBean` khi phiên bản Spring hỗ trợ.

### 5.2. Dùng cấu hình nested trong test class

Có thể khai báo `@TestConfiguration` ngay trong test class:

```java
@SpringBootTest
class OrderPaymentIntegrationTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class TestConfig {

        @Bean
        @Primary
        PaymentGateway paymentGateway() {
            return new SuccessfulPaymentGateway();
        }
    }
}
```

Spring Boot hỗ trợ dùng nested `@TestConfiguration` như cấu hình bổ sung cho test. Cách này tiện khi fake chỉ phục vụ một test class. Nếu nhiều test class dùng chung fake, tách cấu hình ra một file riêng và import ở các test cần nó giúp giảm lặp lại.

## 6. Thay bean trong Spring context bằng @MockitoBean

Với Spring Framework 6.2 trở lên, `@MockitoBean` là annotation của Spring Test để đăng ký một Mockito mock làm bean override trong `ApplicationContext`. Nó giúp thay dependency mà Spring đang inject bằng mock do Mockito quản lý.

Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @MockitoBean
    private PaymentGateway paymentGateway;

    @Test
    void completesOrderWhenPaymentSucceeds() {
        when(paymentGateway.charge(any(PaymentRequest.class)))
                .thenReturn(new PaymentResult("PAY-100", true));

        OrderResult result = orderService.completeOrder("CUS-42");

        assertTrue(result.completed());
        verify(paymentGateway).charge(any(PaymentRequest.class));
    }
}
```

Spring tạo mock cho `PaymentGateway` và đưa nó vào context thay cho bean phù hợp. `OrderService` được Spring tạo như bình thường, nhưng dependency được inject là Mockito mock. Test có thể cấu hình kết quả và verify lời gọi.

### 6.1. Chọn đúng bean khi có nhiều candidate

Nếu context có nhiều bean cùng kiểu, cần xác định bean nào được thay thế. Có thể dùng qualifier trên field:

```java
@MockitoBean
@Qualifier("stripePaymentGateway")
private PaymentGateway paymentGateway;
```

Tên field cũng có thể tham gia như một qualifier fallback khi Spring cần phân biệt các candidate. Dù vậy, dùng `@Qualifier` tường minh giúp ý định dễ đọc hơn khi có nhiều gateway cùng kiểu.

Nếu muốn đảm bảo test chỉ thay một bean đã tồn tại, có thể bật `enforceOverride`:

```java
@MockitoBean(enforceOverride = true)
private PaymentGateway paymentGateway;
```

Khi không có bean phù hợp để override, context sẽ báo lỗi. Điều này giúp phát hiện cấu hình test bị thiếu hoặc sai tên, thay vì vô tình thêm một mock mới mà test vẫn chạy.

Mặc định, cơ chế bean override có thể tạo mock nếu chưa có bean phù hợp. Hành vi tạo mới có thể hữu ích trong một số test slice, nhưng nếu mục tiêu là thay bean thật cụ thể, `enforceOverride = true` làm điều kiện rõ ràng hơn.

### 6.2. @MockitoBean và @MockBean

Trong các dự án Spring Boot cũ, có thể gặp `@MockBean` thuộc `org.springframework.boot.test.mock.mockito`. Spring Framework 6.2 bổ sung `@MockitoBean` trong Spring Test; Spring Boot 3.4 đánh dấu `@MockBean` deprecated để hướng tới annotation mới.

Với dự án đã dùng Spring Framework 6.2 hoặc Spring Boot 3.4 trở lên, ưu tiên `@MockitoBean` cho test mới nếu không có ràng buộc tương thích với cấu hình cũ. Với dự án ở phiên bản cũ hơn, dùng annotation được phiên bản đang sử dụng hỗ trợ. Không import hai annotation cùng tên từ hai package khác nhau trong một test class.

## 7. Mockito mock thuần trong unit test

Không phải bài test nào cũng cần Spring context. Với unit test cho một service, có thể tạo mock bằng `@Mock` và inject vào đối tượng bằng constructor hoặc `@InjectMocks`.

Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderServiceUnitTest {

    @Mock
    private PaymentGateway paymentGateway;

    @InjectMocks
    private OrderService orderService;

    @Test
    void completesOrderWhenPaymentSucceeds() {
        when(paymentGateway.charge(any(PaymentRequest.class)))
                .thenReturn(new PaymentResult("PAY-100", true));

        OrderResult result = orderService.completeOrder("CUS-42");

        assertTrue(result.completed());
        verify(paymentGateway).charge(any(PaymentRequest.class));
    }
}
```

Ở đây MockitoExtension khởi tạo `@Mock` và xử lý `@InjectMocks`; Spring không tạo `ApplicationContext`. Cách này nhanh và phù hợp để kiểm tra logic của `OrderService` khi các dependency có thể được thay bằng mock.

Nếu constructor có nhiều dependency, cách viết tường minh bằng constructor trong test cũng là lựa chọn tốt:

```java
@Test
void calculatesDiscount() {
    PaymentGateway gateway = mock(PaymentGateway.class);
    OrderService service = new OrderService(gateway);

    // Arrange, act and assert
}
```

Constructor injection giúp nhìn rõ dependency nào được thay thế và tránh phụ thuộc vào cơ chế inject theo field của test framework.

## 8. Chọn bean theo loại test của Spring

Các annotation test slice và test context thường gợi ý loại bean nên giữ thật và loại nên thay.

| Loại test | Bean nên giữ thật | Bean thường được thay |
|---|---|---|
| Unit test service thuần Java | Đối tượng đang kiểm thử và các value object | Repository, gateway, clock hoặc client bên ngoài bằng Mockito mock/fake |
| `@WebMvcTest` | Controller, MVC infrastructure liên quan | Service/application facade bằng `@MockitoBean` hoặc mock bean tương ứng |
| `@DataJpaTest` | Repository, entity mapping, JPA và database test | HTTP client hoặc dependency ngoài persistence nếu được đưa vào slice |
| `@JsonTest` | Jackson configuration và serializer/deserializer trong phạm vi test | Dependency ứng dụng không liên quan nếu có |
| `@SpringBootTest` | Những thành phần ứng dụng nằm trong luồng tích hợp cần xác nhận | Dịch vụ ngoài hoặc ranh giới không thuộc mục tiêu test |

Ví dụ, trong `@WebMvcTest(OrderController.class)`, controller thật được tạo để kiểm tra routing, binding, validation và response. Application service thường được mock vì bài test không nhằm kiểm tra logic service hay database. Trong `@DataJpaTest`, repository và persistence layer nên chạy thật trong test slice; mock repository sẽ bỏ qua hành vi mà test cần xác nhận.

Với `@SpringBootTest`, hãy chọn một luồng cụ thể để kiểm tra. Nếu mục tiêu là xác nhận controller, service và repository phối hợp, giữ chúng thật và thay hệ thống thanh toán ngoài. Nếu mục tiêu là kiểm tra service tích hợp với database, có thể giữ service và repository thật, nhưng mock cổng gửi email không thuộc phạm vi.

## 9. Chọn bean bằng @Profile hoặc @ConditionalOnProperty

Một ứng dụng có thể cung cấp nhiều implementation và chọn bằng profile hoặc property. Ví dụ:

```java
@Component
@Profile("!test")
class HttpPaymentGateway implements PaymentGateway {
    // Calls the real payment provider.
}

@Component
@Profile("test")
class TestPaymentGateway implements PaymentGateway {
    // Returns deterministic test results.
}
```

Test kích hoạt profile:

```java
@SpringBootTest
@ActiveProfiles("test")
class OrderPaymentIntegrationTest {
}
```

Cách này phù hợp khi ứng dụng thật sự có một cấu hình theo môi trường rõ ràng, chẳng hạn implementation local, sandbox và production. Cần bảo đảm profile test không vô tình được kích hoạt trong môi trường production và implementation test không chứa logic hoặc dữ liệu có thể gây tác động ngoài dự kiến.

Nếu chỉ một hoặc vài test class cần thay bean, `@TestConfiguration` hoặc `@MockitoBean` thường thể hiện phạm vi rõ hơn. Profile là cấu hình cấp context; bật profile có thể thay đổi nhiều bean cùng lúc và ảnh hưởng tới toàn bộ test dùng profile đó.

## 10. Thay bean bằng @TestBean khi cần implementation tùy chỉnh

Spring Framework 6.2 bổ sung `@TestBean` để thay bean trong context bằng một instance do phương thức factory của test cung cấp. Cơ chế này phù hợp khi cần một implementation test cụ thể mà không muốn dùng Mockito.

Ví dụ minh họa:

```java
import org.springframework.test.context.bean.override.convention.TestBean;

@SpringBootTest
class OrderServiceTest {

    @TestBean
    PaymentGateway paymentGateway;

    static PaymentGateway paymentGateway() {
        return new SuccessfulPaymentGateway();
    }
}
```

Phương thức factory `static` cung cấp instance để Spring đăng ký làm bean override. Hãy kiểm tra bean được chọn theo kiểu hoặc tên khi context có nhiều implementation. `@TestBean` có thể dùng để đưa fake vào vị trí bean hiện hữu, trong khi `@TestConfiguration` thường bổ sung cấu hình và bean cho context.

Nếu dự án đang dùng Spring Framework trước 6.2, annotation này chưa có; dùng `@TestConfiguration` và cấu hình bean theo phiên bản tương ứng. Không cần đưa `@TestBean` vào chỉ để thay một dependency đơn giản nếu `@MockitoBean` hoặc test configuration đã diễn đạt đầy đủ ý định.

## 11. Những điều cần cân nhắc khi thay bean

### 11.1. Bean override có thể ảnh hưởng context cache

Spring Test cache `ApplicationContext` dựa trên metadata cấu hình. Các test class có cùng cấu hình và cùng bean override có thể tái sử dụng context. Nếu mock hoặc cấu hình test khác nhau, context customizer và metadata override có thể làm cache key khác nhau.

Không nên thay đổi hành vi global của bean dùng chung giữa các test mà không reset hoặc cấu hình lại rõ ràng. `@MockitoBean` có cơ chế reset mock theo lifecycle test; với MockitoExtension trong unit test, extension cũng quản lý trạng thái mock. Nếu dùng fake bean có mutable state, cần reset state giữa các test hoặc tạo context riêng phù hợp.

### 11.2. Không mock đối tượng đang được kiểm thử

Nếu `OrderService` là đối tượng cần xác nhận hành vi, không nên thay chính `OrderService` bằng mock rồi verify method của nó. Khi đó, bài test chỉ xác nhận Mockito hoạt động, không kiểm tra logic sản phẩm. Hãy giữ đối tượng mục tiêu thật và thay các dependency của nó.

### 11.3. Không mock quá sâu

Nếu một service gọi ba dependency và test mock tất cả các lớp bên dưới, bài kiểm thử có thể chỉ xác nhận một chuỗi tương tác đã được định sẵn. Khi refactor nội bộ, test dễ hỏng dù hành vi công khai không đổi.

Chỉ thay những ranh giới cần kiểm soát, ví dụ cổng thanh toán, email gateway hoặc hệ thống bên ngoài. Giữ các thành phần thuộc phạm vi hành vi cần kiểm tra ở dạng thật.

### 11.4. Cẩn thận với @Primary và nhiều bean cùng kiểu

Thêm fake bean với `@Primary` không bảo đảm mọi nơi đều sử dụng fake. `@Qualifier`, bean name, collection injection và các điều kiện cấu hình có thể làm kết quả khác đi. Nếu mục tiêu là thay đúng bean, dùng bean override có định danh rõ ràng hoặc kiểm tra wiring qua context test.

### 11.5. Reset trạng thái fake giữa các test

Một fake lưu dữ liệu trong map hoặc list có thể giữ trạng thái từ test trước nếu context được cache. Có thể cung cấp phương thức `clear()` và gọi ở `@BeforeEach`, hoặc thiết kế fake bất biến với dữ liệu được truyền qua constructor. Trạng thái dùng chung cần được quản lý rõ để test không phụ thuộc thứ tự thực thi.

## 12. Ví dụ quyết định cho một luồng đặt hàng

Giả sử luồng đặt hàng có các thành phần:

```text
OrderController
      |
      v
OrderService
   /       \
  v         v
OrderRepository   PaymentGateway
```

Mục tiêu test quyết định cách thay bean:

| Mục tiêu | Controller | Service | Repository | PaymentGateway |
|---|---|---|---|---|
| Unit test quy tắc service | Không cần Spring | Thật | Mock/fake | Mock |
| Kiểm thử HTTP controller | Thật | Mock bean | Không tham gia | Không tham gia |
| Kiểm thử persistence đơn hàng | Không cần controller | Có thể thật | Thật | Fake/mock nếu luồng gọi tới nó |
| Tích hợp luồng đặt hàng | Thật | Thật | Thật | Fake hoặc mock tùy phạm vi |

Ví dụ unit test service tập trung vào việc thanh toán thành công:

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    OrderRepository repository;

    @Mock
    PaymentGateway paymentGateway;

    @InjectMocks
    OrderService service;

    @Test
    void savesOrderAfterSuccessfulPayment() {
        when(paymentGateway.charge(any(PaymentRequest.class)))
                .thenReturn(new PaymentResult("PAY-1", true));

        service.createOrder("CUS-1");

        verify(repository).save(any(Order.class));
    }
}
```

Ví dụ kiểm thử controller dùng Spring MVC slice:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void returnsAcceptedWhenOrderIsCreated() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""{"customerId":"CUS-1"}"""))
                .andExpect(status().isAccepted());

        verify(orderService).createOrder("CUS-1");
    }
}
```

Ví dụ tích hợp với repository thật và payment fake có thể dùng `@SpringBootTest` cùng `@TestConfiguration`. Test cần xác nhận đơn hàng thực sự được lưu và trạng thái thanh toán được ghi đúng, trong khi fake gateway trả kết quả xác định để không gọi nhà cung cấp thanh toán bên ngoài.

## 13. Quy trình chọn và thay bean

Khi bắt đầu viết một bài kiểm thử Spring, có thể đưa ra quyết định theo các bước:

1. **Xác định đối tượng và hành vi cần bảo vệ.** Đối tượng này nên được giữ thật trong test.
2. **Xác định ranh giới dependency.** Thành phần nào thuộc phạm vi test, thành phần nào là dịch vụ ngoài hoặc chỉ cần cung cấp kết quả?
3. **Chọn implementation cho từng dependency.** Giữ bean thật khi cần kiểm tra tích hợp; dùng fake/stub khi cần hành vi đơn giản, tái sử dụng; dùng Mockito mock khi cần điều khiển kết quả hoặc verify tương tác.
4. **Chọn cách đưa dependency vào test.** Unit test thuần Java dùng `@Mock` hoặc `mock(...)`; Spring context dùng `@MockitoBean`, `@TestConfiguration`, `@TestBean` hoặc profile phù hợp.
5. **Xác định đúng bean cần thay.** Nếu có nhiều bean cùng kiểu, dùng qualifier hoặc tên bean. Nếu cần bảo đảm bean đã tồn tại, bật chế độ enforce override khi annotation hỗ trợ.
6. **Quản lý trạng thái và vòng đời.** Reset mock/fake khi cần, bảo đảm container/server còn chạy trong thời gian context sử dụng và tránh chia sẻ mutable state ngoài ý muốn.
7. **Kiểm tra ở đúng tầng.** Unit test cho logic, test slice cho một phần Spring, integration test cho sự phối hợp giữa nhiều thành phần.

Một bài kiểm thử dễ bảo trì thường giữ đối tượng mục tiêu thật, thay các dependency nằm ngoài phạm vi bằng test double phù hợp và chỉ khởi tạo Spring context khi cần xác nhận hành vi do Spring cung cấp. Bean thật, fake/stub và Mockito mock đều có chỗ đứng trong bộ kiểm thử; điều quan trọng là mỗi lựa chọn phải phục vụ một hành vi cụ thể mà test cần chứng minh.
