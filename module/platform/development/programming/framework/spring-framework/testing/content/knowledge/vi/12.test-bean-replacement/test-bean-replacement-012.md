# Phân biệt annotation của Spring Framework với @MockBean/@SpyBean của Spring Boot

Khi kiểm thử ứng dụng Spring, ta thường cần thay một bean bằng Mockito mock hoặc spy để cô lập phần đang được kiểm tra. Trước Spring Framework 6.2, nhiều dự án Spring Boot dùng `@MockBean` và `@SpyBean` của Spring Boot Test để thực hiện việc này. Từ Spring Framework 6.2, Spring Test cung cấp `@MockitoBean` và `@MockitoSpyBean` như một cơ chế bean override ở cấp framework. Spring Boot 3.4 đánh dấu `@MockBean` và `@SpyBean` deprecated để chuyển sang các annotation mới.

Hai nhóm annotation có mục tiêu gần nhau nhưng khác package, lịch sử phát triển và một số hành vi quan trọng. Đặc biệt, `@MockitoBean` có thể tạo mock nếu chưa có bean phù hợp hoặc thay bean hiện hữu; `@MockitoSpyBean` yêu cầu có một bean hiện hữu để bọc bằng spy. Các annotation mới cũng cung cấp lựa chọn `enforceOverride`, hỗ trợ khai báo theo kiểu ở cấp class và có khả năng giới hạn override trong context hierarchy.

Hiểu đúng sự khác nhau giúp chọn annotation theo phiên bản Spring đang dùng, tránh import nhầm package và tránh một test vô tình thêm mock mới trong khi mục tiêu thực sự là thay một bean thật.

## 1. Bối cảnh phiên bản và package

Các annotation được cung cấp bởi những module khác nhau:

| Annotation | Package | Nơi cung cấp | Ghi chú phiên bản |
|---|---|---|---|
| `@MockBean` | `org.springframework.boot.test.mock.mockito` | Spring Boot Test | Được dùng phổ biến trước Spring Boot 3.4; deprecated từ Boot 3.4 để chuyển sang annotation của Spring Framework |
| `@SpyBean` | `org.springframework.boot.test.mock.mockito` | Spring Boot Test | Được dùng phổ biến trước Spring Boot 3.4; deprecated từ Boot 3.4 để chuyển sang annotation của Spring Framework |
| `@MockitoBean` | `org.springframework.test.context.bean.override.mockito` | Spring Framework Test | Có từ Spring Framework 6.2 |
| `@MockitoSpyBean` | `org.springframework.test.context.bean.override.mockito` | Spring Framework Test | Có từ Spring Framework 6.2 |

Spring Boot 3.4 dựa trên Spring Framework 6.2, vì vậy các dự án Boot 3.4 có thể sử dụng annotation mới. Trong dòng Spring Boot 3.4, `@MockBean` và `@SpyBean` được đánh dấu deprecated để loại bỏ trong Spring Boot 4.0. Với dự án đã nâng lên Boot 4, hãy dùng annotation mới của Spring Framework thay cho import cũ.

Với Spring Framework độc lập, không dùng Spring Boot, `@MockitoBean` và `@MockitoSpyBean` vẫn có thể được sử dụng nếu phiên bản Spring Framework là 6.2 trở lên và test class có các dependency cần thiết. `@MockBean` và `@SpyBean` là API của Spring Boot Test, nên không phải lựa chọn cho một dự án chỉ có Spring Framework.

### 1.1. Import đúng package

Annotation cũ:

```java
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.mock.mockito.SpyBean;
```

Annotation mới:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
```

Tên annotation gần giống nhau nhưng không thể thay import một cách máy móc mà bỏ qua phiên bản và semantics. Khi migration, hãy xóa import cũ và thêm import mới từ `org.springframework.test.context.bean.override.mockito`.

## 2. Cơ chế bean override của Spring Framework 6.2

Spring Framework 6.2 đưa bean overriding vào Spring TestContext Framework thông qua một cơ chế chung. `@MockitoBean` và `@MockitoSpyBean` là hai annotation tích hợp Mockito với cơ chế đó.

Ý tưởng cơ bản là test khai báo một bean override trên field hoặc trên test class. Spring xử lý metadata trước khi tạo `ApplicationContext`, tìm bean phù hợp và áp dụng strategy tương ứng:

- **Replace hoặc create:** tạo Mockito mock và thay bean phù hợp; nếu không có bean thì có thể đăng ký mock mới. Đây là strategy mặc định của `@MockitoBean`.
- **Replace:** chỉ thay bean phù hợp đã tồn tại. `@MockitoBean(enforceOverride = true)` yêu cầu hành vi này.
- **Wrap:** tìm một bean hiện hữu và bọc bean đó bằng Mockito spy. Đây là strategy của `@MockitoSpyBean`.

Các annotation mới không chỉ là alias cho annotation Boot cũ. Chúng thuộc Spring Test và dùng bean override infrastructure của Spring Framework, nên có thể dùng trong dự án Spring Framework không có Spring Boot.

## 3. So sánh @MockBean và @MockitoBean

### 3.1. Cách khai báo cơ bản

Với Spring Boot cũ, một dependency có thể được thay bằng `@MockBean`:

```java
import org.springframework.boot.test.mock.mockito.MockBean;

@SpringBootTest
class OrderServiceTests {

    @Autowired
    private OrderService orderService;

    @MockBean
    private PaymentGateway paymentGateway;
}
```

Với Spring Framework 6.2 hoặc Spring Boot 3.4 trở lên, dùng `@MockitoBean`:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class OrderServiceTests {

    @Autowired
    private OrderService orderService;

    @MockitoBean
    private PaymentGateway paymentGateway;
}
```

Trong cả hai trường hợp, test nhận một Mockito mock cho `PaymentGateway`, còn `OrderService` vẫn là bean được Spring tạo và inject. Test có thể stub phản hồi của gateway và xác minh tương tác.

### 3.2. Thay bean hiện hữu hoặc tạo mock mới

`@MockitoBean` dùng strategy replace-or-create theo mặc định:

- Nếu context có một bean phù hợp, bean đó được thay bằng mock.
- Nếu context chưa có bean phù hợp, mock có thể được đăng ký thành bean mới.

Điều này hữu ích trong test slice, nơi một dependency có thể không nằm trong context ban đầu nhưng controller hoặc component vẫn cần nó để được tạo.

Nếu muốn bảo đảm test đang thay một bean thật đã được cấu hình, bật `enforceOverride`:

```java
@MockitoBean(enforceOverride = true)
private PaymentGateway paymentGateway;
```

Khi không tìm thấy bean phù hợp để thay, Spring báo lỗi trong quá trình tạo context. Đây là lựa chọn tốt khi test đang kiểm tra wiring của một ứng dụng mà `PaymentGateway` bắt buộc phải được đăng ký.

`@MockBean` của Spring Boot cũng có thể thay bean hiện hữu hoặc thêm mock nếu chưa có bean phù hợp, nhưng không có thuộc tính `enforceOverride` tương đương trong API cũ. Vì vậy, khi chuyển từ `@MockBean` sang `@MockitoBean`, hãy cân nhắc có cần bật `enforceOverride = true` để làm rõ ý định hay không.

### 3.3. Khai báo ở field hoặc cấp class

Annotation mới hỗ trợ khai báo mock tại field:

```java
@MockitoBean
private PaymentGateway paymentGateway;
```

Và khai báo theo kiểu ở cấp class:

```java
@MockitoBean(types = {
        PaymentGateway.class,
        InventoryClient.class
})
@SpringBootTest
class OrderServiceTests {
}
```

Khai báo cấp class phù hợp khi test chỉ cần thay bean và không cần inject mock vào field để stub hoặc verify trực tiếp. Nếu cần thao tác với mock trong test method, field-level declaration thường dễ đọc hơn.

Với `@MockitoBean`, thuộc tính `types` được dùng khi khai báo trên class; khi khai báo trên field, kiểu mock được suy ra từ kiểu field. Có thể chỉ định tên bean khi context có nhiều bean cùng kiểu:

```java
@MockitoBean(name = "stripePaymentGateway")
private PaymentGateway paymentGateway;
```

Trong API `@MockBean` cũ, người viết thường dùng `value` hoặc `classes` cho khai báo cấp class và `name` để xác định bean. Khi migration sang `@MockitoBean`, thay cách khai báo theo API mới, đặc biệt là `types` cho danh sách kiểu ở cấp class.

## 4. So sánh @SpyBean và @MockitoSpyBean

### 4.1. Spy giữ hành vi thật

Mockito spy bọc một đối tượng thật. Nếu không stub method, lời gọi thường chạy implementation thật. Test có thể dùng spy để quan sát lời gọi hoặc thay hành vi của một method cụ thể trong khi giữ các method còn lại.

Annotation Boot cũ:

```java
import org.springframework.boot.test.mock.mockito.SpyBean;

@SpringBootTest
class PricingServiceTests {

    @SpyBean
    private PricingService pricingService;
}
```

Annotation Spring Framework mới:

```java
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

@SpringBootTest
class PricingServiceTests {

    @MockitoSpyBean
    private PricingService pricingService;
}
```

Spring tìm bean `PricingService` trong context, tạo spy bọc bean đó và sử dụng spy làm bean được inject. Test có thể gọi method thật, stub một method hoặc verify method đã được gọi.

### 4.2. Khác biệt quan trọng: spy cần bean hiện hữu

`@MockitoSpyBean` dùng strategy wrap: nó yêu cầu một bean hiện hữu phù hợp để bọc. Nếu không có bean phù hợp, Spring không thể tạo spy từ khoảng trống và context sẽ thất bại.

Đây là điểm cần chú ý khi thay `@SpyBean` cũ. API `@SpyBean` của Spring Boot có thể đăng ký một spy bean mới khi không tìm thấy bean tương ứng, trong khi `@MockitoSpyBean` của Spring Framework được thiết kế để wrap một bean hiện hữu. Nếu test cần một implementation mới, hãy đăng ký fake bằng `@TestConfiguration` hoặc `@TestBean`, rồi dùng spy trên bean đã được tạo nếu thực sự cần quan sát hành vi.

Ví dụ:

```java
@SpringBootTest
@Import(PricingTestConfiguration.class)
class PricingServiceTests {

    @MockitoSpyBean
    private PricingService pricingService;
}
```

`PricingTestConfiguration` cần đăng ký `PricingService` trước khi Spring áp dụng spy. Nếu `PricingService` đã được component scan hoặc tạo từ cấu hình ứng dụng, không cần thêm một bean thứ hai.

### 4.3. Spy theo kiểu hoặc theo tên

Nếu có nhiều bean cùng kiểu, hãy xác định bean cần wrap bằng qualifier hoặc tên:

```java
@MockitoSpyBean(name = "standardPricingService")
private PricingService pricingService;
```

Hoặc:

```java
@MockitoSpyBean
@Qualifier("standardPricingService")
private PricingService pricingService;
```

`@MockitoSpyBean` cũng hỗ trợ khai báo theo kiểu ở cấp class thông qua `types`:

```java
@MockitoSpyBean(types = PricingService.class)
@SpringBootTest
class PricingServiceTests {
}
```

Khi chỉ có một bean cùng kiểu, Spring có thể xác định candidate theo kiểu. Nếu có nhiều bean, cần qualifier hoặc bean name để lựa chọn duy nhất.

## 5. Bảng so sánh hành vi

| Tiêu chí | `@MockBean` (Boot) | `@MockitoBean` (Framework) | `@SpyBean` (Boot) | `@MockitoSpyBean` (Framework) |
|---|---|---|---|---|
| Loại test double | Mockito mock | Mockito mock | Mockito spy | Mockito spy |
| Vai trò | Thay dependency bằng mock | Thay hoặc tạo mock bean | Spy bean trong context | Bọc bean hiện hữu bằng spy |
| Khi không có bean phù hợp | Có thể thêm mock bean | Có thể tạo mock theo mặc định | Có thể đăng ký spy bean mới theo API Boot | Không có bean để wrap nên context thất bại |
| Chỉ thay bean đã tồn tại | Không có thuộc tính enforce tương đương | `enforceOverride = true` | Spy trên bean được tìm thấy; API Boot có hành vi thêm bean nếu không có | Bắt buộc tìm bean phù hợp để wrap |
| Field-level | Có | Có | Có | Có |
| Type-level | Có, qua `classes`/`value` | Có, qua `types` | Có, qua `classes`/`value` | Có, qua `types` |
| Chọn candidate | Bean name, qualifier và kiểu | `name`, qualifier và kiểu | Bean name, qualifier và kiểu | `name`, qualifier và kiểu |
| Reset mock mặc định | Sau mỗi test method theo cấu hình mặc định | `MockReset.AFTER` | Sau mỗi test method theo cấu hình mặc định | `MockReset.AFTER` |
| Module cung cấp | Spring Boot Test | Spring Framework Test | Spring Boot Test | Spring Framework Test |

Điểm khác biệt quan trọng nhất khi migration là semantics của spy và khả năng yêu cầu override bean đã tồn tại đối với mock. Không nên chỉ thay tên annotation mà bỏ qua việc test đang dựa vào hành vi tạo bean mới hay wrap bean cũ.

## 6. Chọn đúng bean khi có nhiều implementation

Giả sử ứng dụng có hai implementation:

```java
@Component("stripePaymentGateway")
class StripePaymentGateway implements PaymentGateway {
    // Calls Stripe.
}

@Component("bankPaymentGateway")
class BankPaymentGateway implements PaymentGateway {
    // Calls a bank provider.
}
```

Nếu test chỉ khai báo:

```java
@MockitoBean
private PaymentGateway paymentGateway;
```

Spring có thể không xác định được một candidate duy nhất. Có thể chỉ định qualifier:

```java
@MockitoBean
@Qualifier("stripePaymentGateway")
private PaymentGateway paymentGateway;
```

Hoặc chỉ định tên bean trực tiếp:

```java
@MockitoBean(name = "stripePaymentGateway")
private PaymentGateway paymentGateway;
```

Khi dùng field-level annotation, tên field cũng có thể được dùng làm fallback qualifier nếu không có qualifier khác. Ví dụ field tên `stripePaymentGateway` có thể giúp Spring chọn bean cùng tên. Dù vậy, nếu có nhiều candidate, `@Qualifier` hoặc `name` tường minh giúp ý định rõ hơn và giảm phụ thuộc vào cách đặt tên field.

Quy tắc tương tự cần được áp dụng cho `@MockitoSpyBean`. Spy phải wrap đúng một bean hiện hữu; nếu có nhiều candidate, Spring cần qualifier để biết instance nào sẽ được bọc.

## 7. Spy và cách stub method an toàn

Vì spy gọi implementation thật theo mặc định, cú pháp stubbing có thể tạo side effect ngay trong lúc thiết lập test.

Với mock, cách viết phổ biến là:

```java
when(paymentGateway.charge(any(PaymentRequest.class)))
        .thenReturn(new PaymentResult("PAY-1", true));
```

Với spy, biểu thức `when(spy.method())` có thể gọi method thật ngay khi thiết lập stubbing. Nếu method thật kết nối database, gọi HTTP hoặc ném exception khi chưa có dữ liệu, test có thể thất bại trước khi chạy phần hành động chính.

Với spy, thường nên dùng `doReturn(...).when(spy).method(...)`:

```java
doReturn(new BigDecimal("90.00"))
        .when(pricingService)
        .calculateDiscount(any(Order.class));
```

Cách này cấu hình kết quả mà không gọi method thật trong lúc stubbing. Các method khác của spy vẫn có thể chạy implementation thật.

Không nên spy toàn bộ service chỉ để stub một dependency. Nếu `PricingService` đang gọi một gateway bên ngoài, thay gateway bằng mock thường tạo ranh giới test rõ hơn. Spy phù hợp khi chính bean cần kiểm tra có một phần hành vi thật cần giữ và một method cụ thể cần quan sát hoặc thay thế.

## 8. Reset mock và spy sau mỗi test

Các annotation tích hợp Mockito của Spring hỗ trợ reset mock sau test method. Mặc định, `@MockitoBean` và `@MockitoSpyBean` dùng chế độ reset `MockReset.AFTER`. Annotation Boot cũ cũng hỗ trợ cấu hình reset và thường dùng reset sau mỗi test theo mặc định.

Điều này giúp tránh stubbing hoặc invocation history từ test trước ảnh hưởng test sau khi cùng một context được cache và bean mock được tái sử dụng.

Ví dụ:

```java
@MockitoBean(reset = MockReset.AFTER)
private PaymentGateway paymentGateway;
```

Trong đa số trường hợp, không cần ghi thuộc tính `reset` vì mặc định đã reset sau mỗi test. Chỉ thay đổi chế độ reset khi có lý do cụ thể và hiểu rõ tác động của việc giữ lại stubbing hoặc invocation history.

Reset mock không đồng nghĩa reset mọi trạng thái của ứng dụng. Nếu một fake bean tự lưu dữ liệu trong map, list hoặc field mutable, Mockito không quản lý trạng thái đó. Test cần reset fake riêng hoặc tạo context mới khi cần.

## 9. Context hierarchy và contextName

Spring Test hỗ trợ context hierarchy, trong đó một test có thể có context cha và context con. Ví dụ, context cha chứa service dùng chung, còn context con chứa web configuration.

Các annotation bean override mới có thuộc tính `contextName` để giới hạn override ở một level được đặt tên trong hierarchy. Điều này hữu ích khi cùng một kiểu bean xuất hiện ở nhiều level và test chỉ muốn thay bean ở một context cụ thể.

Ví dụ minh họa:

```java
@ContextHierarchy({
        @ContextConfiguration(name = "root", classes = RootConfig.class),
        @ContextConfiguration(name = "web", classes = WebConfig.class)
})
class WebIntegrationTests {

    @MockitoBean(contextName = "root")
    private UserDirectory userDirectory;
}
```

`contextName` phải khớp với tên level được khai báo trong `@ContextConfiguration`. Nếu bỏ qua thuộc tính này trong một hierarchy, override có thể được áp dụng ở nhiều level theo quy tắc của bean override infrastructure. Hãy chỉ định tên level khi muốn kiểm soát chính xác vị trí thay bean.

Đây là khả năng của annotation Spring Framework mới, giúp test diễn đạt phạm vi override rõ ràng trong cấu hình nhiều context. Khi migration một test hierarchy từ annotation Boot cũ, hãy xem xét lại bean nào thực sự cần được thay ở từng level.

## 10. Dùng trong Spring Boot test slice

`@MockitoBean` có thể dùng với các test slice như `@WebMvcTest` hoặc `@DataJpaTest` để cung cấp dependency mà slice không tự tạo.

Ví dụ controller test:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderControllerTests {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @Test
    void delegatesOrderCreationToService() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""{"customerId":"CUS-1"}"""))
                .andExpect(status().isAccepted());

        verify(orderService).createOrder("CUS-1");
    }
}
```

Controller và MVC infrastructure là thành phần thật trong slice; `OrderService` là mock bean để test xác nhận controller chuyển request sang service. Cách này giữ test tập trung vào routing, binding, validation và response HTTP.

Với Spring Boot 3.3 trở xuống, dùng `@MockBean` nếu phiên bản Spring Framework đi kèm chưa có `@MockitoBean`. Với Boot 3.4 trở lên, dùng annotation mới để tránh API đã deprecated.

## 11. Dùng trong dự án Spring Framework không có Boot

Một dự án chỉ dùng Spring Framework 6.2+ có thể sử dụng `@MockitoBean` và `@MockitoSpyBean` với Spring TestContext Framework. Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.Mockito.verify;

@SpringJUnitConfig(classes = OrderTestConfig.class)
class OrderApplicationServiceTests {

    @Autowired
    private OrderApplicationService orderService;

    @MockitoBean
    private PaymentGateway paymentGateway;

    @Test
    void delegatesPaymentToGateway() {
        orderService.complete("CUS-1");

        verify(paymentGateway).charge(org.mockito.ArgumentMatchers.any());
    }
}

@Configuration
class OrderTestConfig {
    // Declares OrderApplicationService and its other test dependencies.
}
```

`@SpringJUnitConfig` kết hợp JUnit Jupiter với Spring TestContext Framework. Không cần Spring Boot để sử dụng bean override annotation của Spring Framework. Dự án vẫn cần Mockito trên test classpath và cần cung cấp cấu hình Spring cho những bean còn lại.

Với Spring Framework trước 6.2, các annotation `@MockitoBean` và `@MockitoSpyBean` chưa có. Nếu không dùng Spring Boot, có thể khai báo fake bằng `@Configuration` test, tự tạo Mockito mock rồi đăng ký bean qua cấu hình test hoặc sử dụng một cơ chế thay bean phù hợp với phiên bản đang chạy.

## 12. Migration từ @MockBean/@SpyBean sang annotation mới

### 12.1. Thay @MockBean bằng @MockitoBean

Trước:

```java
import org.springframework.boot.test.mock.mockito.MockBean;

@MockBean
private PaymentGateway paymentGateway;
```

Sau:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@MockitoBean
private PaymentGateway paymentGateway;
```

Nếu test yêu cầu bean phải tồn tại trong context, dùng:

```java
@MockitoBean(enforceOverride = true)
private PaymentGateway paymentGateway;
```

Nếu test cũ dùng `@MockBean(name = "stripePaymentGateway")`, chuyển sang:

```java
@MockitoBean(name = "stripePaymentGateway")
private PaymentGateway paymentGateway;
```

Nếu khai báo ở class level, chuyển danh sách `classes`/`value` sang thuộc tính `types` của `@MockitoBean`.

### 12.2. Thay @SpyBean bằng @MockitoSpyBean

Trước:

```java
import org.springframework.boot.test.mock.mockito.SpyBean;

@SpyBean
private PricingService pricingService;
```

Sau:

```java
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

@MockitoSpyBean
private PricingService pricingService;
```

Trước khi chuyển, xác nhận bean `PricingService` thật sự được đăng ký trong context. `@MockitoSpyBean` cần một bean hiện hữu để wrap. Nếu test cũ dựa vào việc `@SpyBean` thêm một bean khi không tìm thấy implementation, hãy đăng ký implementation bằng test configuration trước rồi mới dùng spy.

### 12.3. Kiểm tra các thuộc tính cũ

Không phải mọi thuộc tính của annotation Boot cũ đều có tên hoặc semantics giống annotation mới. Khi migration, kiểm tra:

- `classes` hoặc `value` ở khai báo cấp class có cần chuyển thành `types` không.
- `name` có còn xác định đúng bean trong context không.
- Có nhiều bean cùng kiểu và cần `@Qualifier` không.
- Test có cần `enforceOverride = true` để xác nhận bean thật tồn tại không.
- Spy có bean hiện hữu để wrap hay đang dựa vào hành vi tạo mới của annotation cũ.
- Test có context hierarchy và cần chỉ định `contextName` không.
- Cấu hình reset mock/spy có được giữ theo mong muốn không.

Sau khi đổi annotation, chạy test class tương ứng và các test dùng chung context để xác nhận wiring và hành vi vẫn đúng. Đặc biệt, nếu test trước đây vô tình tạo thêm mock hoặc spy, annotation mới có thể làm rõ lỗi cấu hình mà trước đó bị che khuất.

## 13. Khi nào dùng annotation Spring, khi nào dùng Mockito thuần?

`@MockitoBean` và `@MockitoSpyBean` là annotation bean override dành cho test có Spring `ApplicationContext`. Chúng không thay thế mọi annotation Mockito.

| Cách khai báo | Có tạo Spring bean override không? | Phạm vi phù hợp |
|---|---|---|
| Mockito `@Mock` | Không | Unit test thuần Java với `MockitoExtension` |
| Mockito `@Spy` | Không | Unit test cần spy một đối tượng do test tạo |
| Spring `@MockitoBean` | Có | Thay hoặc thêm mock bean trong Spring context |
| Spring `@MockitoSpyBean` | Có | Wrap bean hiện hữu trong Spring context bằng spy |
| Spring Boot `@MockBean` cũ | Có | Test Spring Boot ở các phiên bản trước khi chuyển sang annotation Framework |
| Spring Boot `@SpyBean` cũ | Có | Test Spring Boot ở các phiên bản trước khi chuyển sang annotation Framework |

Ví dụ unit test không cần context:

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceUnitTests {

    @Mock
    private PaymentGateway paymentGateway;

    private OrderService orderService;

    @BeforeEach
    void setUp() {
        orderService = new OrderService(paymentGateway);
    }
}
```

Ví dụ này không cần `@MockitoBean`, vì Spring không tạo `ApplicationContext`. Dùng `@Mock` hoặc `mock(...)` là đủ.

Nếu test dùng `@SpringBootTest`, `@WebMvcTest` hoặc `@SpringJUnitConfig` và cần thay một dependency do Spring quản lý, dùng `@MockitoBean` hoặc `@MockitoSpyBean`. Đừng nhầm `@Mock` của Mockito với bean override annotation: mock ở field không tự động thay bean mà Spring inject vào service.

## 14. Những lỗi thường gặp

### 14.1. Import nhầm annotation từ package Boot

Một test mới dùng Spring Framework 6.2 có thể vô tình import `org.springframework.boot.test.mock.mockito.MockBean` thay vì `org.springframework.test.context.bean.override.mockito.MockitoBean`. Nếu dự án đã nâng Boot, IDE có thể cảnh báo deprecated hoặc không tìm thấy annotation cũ sau khi nâng major version. Hãy kiểm tra package import.

### 14.2. Dùng @MockitoSpyBean khi không có bean thật

Spy phải bọc một instance hiện hữu. Nếu context không có bean phù hợp, tạo bean bằng `@TestConfiguration` hoặc `@TestBean` trước, hoặc dùng mock nếu không cần hành vi thật.

### 14.3. Có nhiều bean cùng kiểu

Nếu Spring báo không xác định được candidate, dùng `@Qualifier` hoặc `name` để chỉ rõ bean cần thay. Kiểm tra cả tên field vì nó có thể tham gia làm fallback qualifier.

### 14.4. Mong đợi @MockitoBean luôn thất bại khi bean không tồn tại

Mặc định `@MockitoBean` có thể tạo mock bean mới. Nếu test cần kiểm tra một bean production đã được cấu hình, bật `enforceOverride = true`.

### 14.5. Stub spy bằng when(...) gây gọi method thật

Với spy, `when(spy.method())` có thể thực thi method thật ngay khi thiết lập. Dùng `doReturn(...).when(spy).method(...)` nếu cần tránh side effect trong giai đoạn stubbing.

### 14.6. Mong đợi Mockito @Mock thay bean Spring

`@Mock` chỉ tạo mock cho test instance qua Mockito. Nó không đăng ký mock vào `ApplicationContext`. Dùng `@MockitoBean` nếu service do Spring tạo phải nhận mock đó.

### 14.7. Dùng annotation mới với Spring Framework cũ

`@MockitoBean` và `@MockitoSpyBean` có từ Spring Framework 6.2. Nếu dự án dùng Framework 6.1 hoặc cũ hơn, import sẽ không tồn tại. Với Spring Boot, kiểm tra phiên bản Boot quản lý Spring Framework trước khi đổi annotation.

### 14.8. Context có bean override khác nhau ngoài dự kiến

Các annotation override là một phần metadata cấu hình test và có thể ảnh hưởng context cache. Nếu nhiều test class khai báo mock khác nhau, Spring có thể tạo nhiều context riêng. Hãy dùng cấu hình test có chủ đích và tránh thêm các override không cần thiết.

## 15. Quy trình chọn annotation

Khi cần thay dependency trong một bài kiểm thử Spring, có thể quyết định theo trình tự:

1. **Xác định phiên bản Spring Framework.** Nếu là 6.2 trở lên, có thể dùng `@MockitoBean` và `@MockitoSpyBean`; nếu cũ hơn, dùng API được phiên bản hiện tại hỗ trợ.
2. **Xác định có cần Spring context không.** Nếu chỉ kiểm tra một lớp Java, dùng Mockito `@Mock`/`@Spy`; nếu cần thay bean Spring, dùng bean override annotation.
3. **Chọn mock hay spy.** Mock thay toàn bộ hành vi dependency; spy giữ implementation thật và cho phép stub/verify một phần.
4. **Kiểm tra bean có tồn tại không.** `@MockitoBean` mặc định có thể tạo mới; bật `enforceOverride` nếu bắt buộc phải thay bean hiện hữu. `@MockitoSpyBean` cần bean hiện hữu để wrap.
5. **Chọn đúng candidate.** Dùng kiểu, `name` hoặc `@Qualifier` khi context có nhiều bean cùng kiểu.
6. **Kiểm tra phạm vi context.** Với context hierarchy, dùng `contextName` nếu override chỉ thuộc một level.
7. **Migration theo semantics.** Khi chuyển từ `@MockBean` hoặc `@SpyBean`, kiểm tra class-level declaration, thuộc tính cũ, hành vi tạo bean mới và vòng đời reset.

## 16. Ví dụ migration hoàn chỉnh

Một test Boot cũ có thể viết:

```java
@SpringBootTest
class PaymentServiceTests {

    @Autowired
    private PaymentService paymentService;

    @MockBean(name = "stripePaymentGateway")
    private PaymentGateway paymentGateway;

    @SpyBean
    private ReceiptFormatter receiptFormatter;
}
```

Khi chuyển sang Spring Framework 6.2/Spring Boot 3.4 trở lên:

```java
@SpringBootTest
class PaymentServiceTests {

    @Autowired
    private PaymentService paymentService;

    @MockitoBean(name = "stripePaymentGateway", enforceOverride = true)
    private PaymentGateway paymentGateway;

    @MockitoSpyBean
    private ReceiptFormatter receiptFormatter;
}
```

Trong ví dụ migration, `enforceOverride = true` được thêm để thể hiện rằng `stripePaymentGateway` phải là bean thật có sẵn trong cấu hình. `ReceiptFormatter` cũng phải tồn tại để spy có thể wrap. Nếu trước đó test cần tạo một mock mới vì context không có gateway, hãy bỏ `enforceOverride` hoặc bổ sung cấu hình phù hợp theo mục tiêu test.

Khi migration, hãy giữ lại các assertion và stubbing đang kiểm tra hành vi công khai. Thay đổi annotation chỉ nên điều chỉnh cách Spring đưa test double vào context; nó không nên làm thay đổi đối tượng đang được kiểm thử hoặc mục tiêu của bài test.

`@MockBean` và `@SpyBean` là API Spring Boot Test được sử dụng rộng rãi trong các dự án cũ. Từ Spring Framework 6.2, `@MockitoBean` và `@MockitoSpyBean` cung cấp bean override trực tiếp trong Spring Test, dùng được cả khi không có Spring Boot. `@MockitoBean` có thể thay bean hoặc tạo mock mới theo mặc định, còn `enforceOverride` buộc phải thay bean hiện hữu; `@MockitoSpyBean` cần một bean hiện hữu để wrap. Khi chuyển annotation, hãy kiểm tra package import, phiên bản, cách chọn candidate, class-level declaration, context hierarchy và đặc biệt là khác biệt giữa tạo mock mới với spy trên bean đã tồn tại.
