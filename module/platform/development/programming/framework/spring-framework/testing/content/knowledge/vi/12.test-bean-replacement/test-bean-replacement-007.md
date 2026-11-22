# Yêu cầu bean phải tồn tại và tránh tạo mock ngoài dự kiến

Khi thay một bean Spring bằng Mockito mock trong test, đôi khi điều quan trọng không chỉ là có một mock để inject vào đối tượng đang kiểm thử. Test còn cần xác nhận rằng **bean thật sự tồn tại trong ApplicationContext trước khi bị thay thế**. Nếu Spring tự tạo mock khi không tìm thấy bean, test có thể khởi chạy thành công dù cấu hình ứng dụng đang thiếu bean, profile không được bật hoặc component scan bỏ sót thành phần.

Spring Framework 6.2 cung cấp annotation **@MockitoBean** với thuộc tính **enforceOverride** để kiểm soát hành vi này. Mặc định, @MockitoBean có thể thay bean hiện có hoặc tạo mock mới nếu chưa có bean phù hợp. Khi đặt **enforceOverride = true**, Spring chỉ thay thế bean đã đăng ký; nếu không tìm thấy bean cần thay, quá trình chuẩn bị ApplicationContext thất bại.

Đây là lựa chọn hữu ích cho integration test cần xác nhận wiring của ứng dụng. Với test slice như @WebMvcTest, nơi service thường bị loại khỏi context có chủ đích, việc tạo mock mới có thể chính là điều test cần. Vì vậy, trước khi bật enforceOverride, cần xác định bean có thuộc phạm vi context đang được kiểm thử hay không.

## 1. Vì sao mock có thể được tạo dù bean thật không tồn tại?

Giả sử ứng dụng có một CheckoutService phụ thuộc vào PaymentGateway:

~~~java
public interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}
~~~

~~~java
@Service
class CheckoutService {

    private final PaymentGateway paymentGateway;

    CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    CheckoutResult checkout(CheckoutCommand command) {
        PaymentResult payment = paymentGateway.charge(
            new PaymentRequest(command.orderId(), command.amount())
        );
        return payment.accepted()
            ? CheckoutResult.completed(command.orderId())
            : CheckoutResult.rejected(command.orderId());
    }
}
~~~

Trong ứng dụng thật, PaymentGateway có thể được đăng ký bằng @Component hoặc một phương thức @Bean:

~~~java
@Configuration
class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new HttpPaymentGateway();
    }
}
~~~

Khi viết test, ta muốn thay PaymentGateway bằng Mockito mock để điều khiển kết quả thanh toán:

~~~java
@SpringJUnitConfig({
    PaymentConfiguration.class,
    CheckoutService.class
})
class CheckoutServiceTest {

    @Autowired
    private CheckoutService checkoutService;

    @MockitoBean
    private PaymentGateway paymentGateway;

    @Test
    void completesCheckoutWhenPaymentIsAccepted() {
        given(paymentGateway.charge(any(PaymentRequest.class)))
            .willReturn(PaymentResult.accepted());

        CheckoutResult result =
            checkoutService.checkout(validCommand());

        assertEquals(CheckoutStatus.COMPLETED, result.status());
    }
}
~~~

Với cấu hình trên, Spring tìm bean PaymentGateway trong context và thay nó bằng mock. CheckoutService vẫn được tạo bởi Spring và nhận mock thông qua constructor injection.

Tuy nhiên, nếu PaymentConfiguration vô tình bị bỏ khỏi danh sách cấu hình, hoặc bean PaymentGateway không được đăng ký vì một profile hay điều kiện cấu hình, @MockitoBean mặc định vẫn có thể tạo mock mới. Context khi đó vẫn có thể khởi tạo và CheckoutService vẫn nhận được dependency. Test có thể chạy qua dù cấu hình ứng dụng thiếu bean mà ta định kiểm tra.

Đây là khác biệt quan trọng giữa hai câu hỏi:

- “Tôi cần một mock PaymentGateway để kiểm tra CheckoutService.”
- “Tôi cần thay đúng bean PaymentGateway đã được ứng dụng đăng ký.”

Nếu mục tiêu là câu hỏi thứ hai, hãy yêu cầu bean phải tồn tại.

## 2. Dùng enforceOverride = true

Có thể bật chế độ bắt buộc thay thế bean bằng thuộc tính enforceOverride:

~~~java
@SpringJUnitConfig({
    PaymentConfiguration.class,
    CheckoutService.class
})
class CheckoutServiceTest {

    @Autowired
    private CheckoutService checkoutService;

    @MockitoBean(enforceOverride = true)
    private PaymentGateway paymentGateway;

    @Test
    void completesCheckoutWhenPaymentIsAccepted() {
        // Arrange
        given(paymentGateway.charge(any(PaymentRequest.class)))
            .willReturn(PaymentResult.accepted());

        // Act
        CheckoutResult result =
            checkoutService.checkout(validCommand());

        // Assert
        assertEquals(CheckoutStatus.COMPLETED, result.status());
    }
}
~~~

Khi context được chuẩn bị, Spring phải tìm được bean phù hợp với PaymentGateway để thay thế. Nếu không tìm thấy bean, test context không khởi tạo thành công. Test method sẽ không chạy.

Hành vi này giúp phát hiện sớm một số lỗi:

- Cấu hình chứa bean PaymentGateway không được import hoặc scan.
- Profile cần thiết chưa được kích hoạt.
- Điều kiện @Conditional không thỏa mãn nên bean không được tạo.
- Tên bean hoặc qualifier trong test trỏ đến một bean khác.
- Kiểu bean được khai báo trong test không khớp với bean thực tế.
- Test đang dùng một context nhỏ hơn phạm vi mà người viết nghĩ rằng nó có.

Thông báo lỗi cụ thể có thể khác nhau theo phiên bản Spring và cấu hình context. Điều cần quan sát là lỗi xuất hiện trong giai đoạn tạo test ApplicationContext vì không có bean phù hợp để thay thế.

## 3. Hiểu hai chiến lược thay bean của @MockitoBean

Trong Spring Framework 6.2, cơ chế bean override của Spring Test có các chiến lược chính:

| Chiến lược | Ý nghĩa | Hành vi khi không tìm thấy bean |
|---|---|---|
| REPLACE_OR_CREATE | Thay bean phù hợp hoặc tạo bean mock mới | Tạo mock mới |
| REPLACE | Chỉ thay bean đã tồn tại | Báo lỗi khi không tìm thấy bean |
| WRAP | Bọc bean hiện có bằng spy | Báo lỗi khi không tìm thấy bean phù hợp |

@MockitoBean mặc định sử dụng chiến lược REPLACE_OR_CREATE. Thuộc tính enforceOverride chuyển hành vi sang REPLACE:

~~~java
// Mặc định: có thì thay, chưa có thì tạo mock.
@MockitoBean
PaymentGateway paymentGateway;

// Chỉ thay bean đã tồn tại; thiếu bean thì context khởi tạo thất bại.
@MockitoBean(enforceOverride = true)
PaymentGateway paymentGateway;
~~~

Điểm khác biệt nằm ở thời điểm Spring xử lý bean override, trước khi test method thực thi. enforceOverride không phải một assertion Mockito chạy sau khi gọi service. Nó là điều kiện của quá trình chuẩn bị ApplicationContext.

### 3.1. Vì sao mặc định vẫn hữu ích?

Không phải lúc nào bean chưa tồn tại cũng là lỗi. Trong test slice, Spring cố ý chỉ nạp một phần ứng dụng. Ví dụ, @WebMvcTest thường tạo controller và các thành phần MVC cần thiết, còn service nghiệp vụ có thể nằm ngoài slice. Test cần mock service để controller được inject và có thể xử lý request.

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @Test
    void returnsOrderWhenServiceFindsIt() throws Exception {
        given(orderService.findById("order-42"))
            .willReturn(new OrderResponse("order-42"));

        mockMvc.perform(get("/orders/order-42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("order-42"));
    }
}
~~~

Trong ví dụ này, OrderService không nhất thiết phải là bean trong MVC slice. Việc tạo mock mới là chủ đích để cô lập controller. Nếu đặt enforceOverride = true, context có thể thất bại vì service không nằm trong phạm vi slice.

Vì vậy, chỉ bật enforceOverride khi test thực sự yêu cầu bean gốc phải có mặt trong context. Không dùng thuộc tính này theo kiểu áp dụng đồng loạt cho mọi mock.

## 4. Chọn đúng bean khi có nhiều ứng viên

Spring có thể có nhiều bean cùng implement một interface. Ví dụ, ứng dụng đăng ký gateway cho nhiều nhà cung cấp:

~~~java
@Configuration
class PaymentConfiguration {

    @Bean
    @Qualifier("cardGateway")
    PaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    @Qualifier("walletGateway")
    PaymentGateway walletGateway() {
        return new WalletPaymentGateway();
    }
}
~~~

Nếu test chỉ khai báo một field PaymentGateway mà không chỉ rõ ứng viên, Spring có thể không xác định được bean cần thay. Dùng @Qualifier để chỉ định chính xác:

~~~java
@SpringJUnitConfig({
    PaymentConfiguration.class,
    CheckoutService.class
})
class CardCheckoutServiceTest {

    @MockitoBean(enforceOverride = true)
    @Qualifier("cardGateway")
    private PaymentGateway paymentGateway;

    // ...
}
~~~

Có thể dùng thuộc tính name để chỉ định tên bean:

~~~java
@MockitoBean(
    name = "cardGateway",
    enforceOverride = true
)
private PaymentGateway paymentGateway;
~~~

Khi chọn bean, Spring dùng kiểu dữ liệu và qualifier metadata. Với field-level @MockitoBean, tên field cũng có thể được dùng làm qualifier dự phòng khi cần phân biệt nhiều ứng viên. Tuy vậy, @Qualifier hoặc name thể hiện ý định rõ hơn và ít phụ thuộc vào việc đổi tên field.

Nếu có nhiều bean cùng kiểu, hãy kiểm tra:

- Bean nào được đánh dấu @Primary?
- Có @Qualifier tương ứng với bean mong muốn không?
- Tên field có vô tình được dùng làm qualifier dự phòng không?
- Test có đang nạp đúng cấu hình đăng ký các bean đó không?

Không nên đổi tên field chỉ để thử làm context khởi tạo thành công mà không hiểu bean nào đang được chọn. Một test thay nhầm gateway có thể chạy qua nhưng không còn bảo vệ đúng wiring.

## 5. Ví dụ phát hiện bean bị thiếu do cấu hình

Giả sử bean gateway chỉ được đăng ký trong profile production:

~~~java
@Configuration
@Profile("production")
class ProductionPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new HttpPaymentGateway();
    }
}
~~~

Test kích hoạt profile test:

~~~java
@SpringJUnitConfig({
    ProductionPaymentConfiguration.class,
    CheckoutService.class
})
@ActiveProfiles("test")
class CheckoutServiceTest {

    @MockitoBean(enforceOverride = true)
    private PaymentGateway paymentGateway;

    // ...
}
~~~

Trong trường hợp này, profile production không hoạt động nên PaymentGateway không được đăng ký. Với enforceOverride = true, Spring không thể thay bean và context khởi tạo thất bại. Điều này làm lộ ra sự khác biệt giữa cấu hình test đang dùng và cấu hình bean mà test mong đợi.

Nếu mục tiêu của test là kiểm tra CheckoutService với một gateway giả lập trong profile test, hãy đăng ký một bean phù hợp cho profile test hoặc dùng một test configuration rõ ràng:

~~~java
@TestConfiguration
class TestPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new SandboxPaymentGateway();
    }
}
~~~

Khi test import TestPaymentConfiguration, bean tồn tại và có thể được thay bằng Mockito mock với enforceOverride = true. Cách này giữ rõ hai việc: cấu hình test cung cấp bean nền, còn @MockitoBean thay bean đó để điều khiển tương tác.

Nếu test chỉ cần mock làm dependency cho service và không nhằm xác nhận cấu hình bean thật, có thể dùng @MockitoBean mặc định. Điều quan trọng là phải xác định rõ phạm vi điều test đang bảo vệ.

## 6. Phân biệt @MockitoBean với @MockitoSpyBean

@MockitoBean thay bean bằng Mockito mock. Mock không chạy logic thật trừ khi được stub hoặc cấu hình answer tương ứng.

@MockitoSpyBean tạo spy trên một bean đã tồn tại, giữ hành vi thật của bean và cho phép theo dõi hoặc stub một số method. Spy sử dụng chiến lược WRAP, vì vậy Spring cần tìm được bean gốc để bọc.

~~~java
@SpringJUnitConfig(InventoryConfiguration.class)
class InventoryServiceTest {

    @MockitoSpyBean
    private InventoryService inventoryService;

    @Test
    void tracksInvocationWhileUsingRealBehavior() {
        inventoryService.recalculate("SKU-10");

        then(inventoryService).should()
            .recalculate("SKU-10");
    }
}
~~~

Ví dụ giả định InventoryConfiguration đăng ký một bean InventoryService. Nếu bean không tồn tại, @MockitoSpyBean không tự tạo một instance thay thế. Nếu có nhiều bean phù hợp, cần chỉ rõ bean bằng qualifier hoặc tên.

Với spy, lời gọi method thật có thể thực thi ngay cả trong lúc stub nếu dùng cú pháp when(spy.method()).thenReturn(...). Để tránh gọi method thật khi cấu hình stub, Mockito thường khuyến nghị cú pháp doReturn(...).when(spy).method().

~~~java
doReturn(10).when(inventoryService).availableQuantity("SKU-10");
~~~

Điểm khác biệt:

| Annotation | Hành vi | Có thể tạo bean khi chưa có? | Mục tiêu |
|---|---|---|---|
| @MockitoBean | Thay bằng mock | Có, mặc định | Cô lập dependency và điều khiển kết quả |
| @MockitoBean(enforceOverride = true) | Chỉ thay bean có sẵn | Không | Bảo đảm bean được đăng ký trước khi thay |
| @MockitoSpyBean | Bọc bean thật bằng spy | Không | Giữ logic thật và theo dõi/stub có chọn lọc |

## 7. Dùng enforceOverride với cấu hình test và test slice

Việc chọn chế độ phụ thuộc vào phạm vi context:

| Kiểu test | Bean được mock có thuộc context không? | Cách chọn thường phù hợp |
|---|---|---|
| @SpringBootTest kiểm tra cấu hình ứng dụng đầy đủ | Thường có, nếu ứng dụng phải đăng ký bean đó | enforceOverride = true khi muốn bảo vệ wiring |
| @SpringJUnitConfig với cấu hình bean tường minh | Có nếu cấu hình khai báo bean | enforceOverride = true |
| @WebMvcTest controller | Service thường bị loại khỏi slice | @MockitoBean mặc định để tạo mock cộng tác |
| @DataJpaTest repository | Service nghiệp vụ thường không thuộc slice | Không yêu cầu override service ngoài slice |
| Test slice tùy chỉnh | Phụ thuộc component được import | Chỉ bật strict override với bean thuộc slice |

### 7.1. Full application context

Khi kiểm tra cấu hình ứng dụng, mục tiêu thường bao gồm việc xác nhận các bean cần thiết được đăng ký. Ví dụ:

~~~java
@SpringBootTest
class CheckoutApplicationTest {

    @Autowired
    private CheckoutService checkoutService;

    @MockitoBean(enforceOverride = true)
    private PaymentGateway paymentGateway;

    @Test
    void wiresCheckoutServiceWithConfiguredGateway() {
        given(paymentGateway.charge(any(PaymentRequest.class)))
            .willReturn(PaymentResult.accepted());

        CheckoutResult result =
            checkoutService.checkout(validCommand());

        assertEquals(CheckoutStatus.COMPLETED, result.status());
    }
}
~~~

Nếu cấu hình ứng dụng không tạo PaymentGateway, test thất bại khi chuẩn bị context. Nhờ vậy, test xác nhận được bean mà service cần thực sự thuộc cấu hình ứng dụng.

### 7.2. Test slice

Với test slice, một số bean bị loại có chủ đích để giới hạn phạm vi. Ví dụ:

~~~java
@WebMvcTest(CheckoutController.class)
class CheckoutControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private CheckoutService checkoutService;

    // ...
}
~~~

CheckoutService nằm ngoài MVC slice, nên mock mới được tạo là hợp lý. Nếu mục tiêu là kiểm tra CheckoutService được cấu hình trong toàn ứng dụng, hãy dùng test có phạm vi context phù hợp.

## 8. Những trường hợp enforceOverride giúp phát hiện lỗi

### 8.1. Thiếu bean do component scan

Một package bị loại khỏi component scan hoặc cấu hình scan bị đổi có thể khiến bean không được đăng ký. Mock mặc định có thể che mất vấn đề này. enforceOverride làm context thất bại ngay khi không tìm thấy bean.

### 8.2. Thiếu cấu hình do profile

Bean được đánh dấu @Profile nhưng test kích hoạt profile khác. Nếu bean phải có trong profile đang kiểm tra, strict override giúp phát hiện việc profile không cung cấp bean.

### 8.3. Điều kiện @Conditional không thỏa mãn

Bean có thể chỉ được tạo khi một property bật hoặc một class có mặt. Nếu điều kiện không thỏa, @MockitoBean mặc định có thể thêm mock mới. enforceOverride xác nhận bean thực sự đã được tạo theo điều kiện đó.

### 8.4. Chọn sai qualifier

Nếu qualifier trỏ đến bean không tồn tại, strict override khiến test không thể khởi tạo. Điều này giúp phát hiện lỗi tên hoặc qualifier thay vì tạo một mock không gắn với bean mà người viết dự định.

### 8.5. Test nạp context thiếu cấu hình

Test có thể chỉ import service class nhưng quên import configuration chứa dependency. Nếu mục tiêu là kiểm tra wiring, strict override giúp phát hiện context chưa đầy đủ.

## 9. Giới hạn và quy tắc lựa chọn bean

Bean override của Spring Test có một số giới hạn cần biết:

- Cơ chế mock/spy được thiết kế cho bean singleton. Bean có scope khác có thể không được override theo cách này.
- Nếu có nhiều bean cùng kiểu, cần xác định rõ bean mục tiêu bằng qualifier, tên hoặc metadata chọn bean.
- @MockitoSpyBean cần một bean hiện có để bọc; nó không tạo bean khi thiếu.
- @MockitoBean mặc định có thể tạo bean mới; điều này có thể thay đổi thành phần trong test context so với cấu hình ứng dụng gốc.
- Việc override diễn ra khi context được chuẩn bị, nên lỗi thiếu bean thường xuất hiện trước khi test method chạy.

Khi test một bean có scope request hoặc session, cần xem xét cách tạo và quản lý scope của test. Không nên giả định @MockitoBean sẽ thay được mọi bean bất kể scope.

Nếu ứng dụng có FactoryBean, proxy hoặc nhiều tầng proxy, cần xác định test đang thay product bean nào và kiểu được expose trong context. Khi chọn bean phức tạp, hãy kiểm tra bean definition và context thực tế trong test configuration thay vì chỉ dựa vào tên class triển khai.

## 10. Quan hệ với @MockBean của Spring Boot

Trước Spring Framework 6.2, nhiều dự án Spring Boot dùng @MockBean của spring-boot-test để đăng ký hoặc thay Mockito mock trong ApplicationContext.

Spring Framework 6.2 bổ sung @MockitoBean và @MockitoSpyBean trong module spring-test. Từ Spring Boot 3.4, @MockBean và @SpyBean của Spring Boot được đánh dấu deprecated để chuyển sang các annotation bean override thuộc Spring Framework.

Điểm cần lưu ý khi chuyển đổi:

- @MockitoBean là annotation của Spring Framework, import từ org.springframework.test.context.bean.override.mockito.MockitoBean.
- @MockBean cũ thuộc Spring Boot test và không có thuộc tính enforceOverride tương đương trong API cũ.
- Khi dùng Spring Framework 6.2 trở lên, có thể dùng enforceOverride để yêu cầu bean tồn tại trước khi thay.
- Với dự án Spring cũ chưa có @MockitoBean, cần tiếp tục dùng cơ chế mock tương thích với phiên bản hiện tại hoặc nâng cấp framework theo kế hoạch dự án.

Không trộn hai annotation cho cùng một bean trong một test context. Chọn một cơ chế bean override nhất quán để tránh hai công cụ cùng cố đăng ký hoặc thay một bean.

## 11. Cấu hình reset mock và vòng đời context

@MockitoBean thường reset mock sau mỗi test method theo chính sách mặc định của Spring Test. Việc reset xóa trạng thái stubbing và invocation của mock để các method không dùng lại tương tác từ test trước.

Reset mock và đóng ApplicationContext là hai hành động khác nhau:

- Reset mock giữ nguyên context và bean mock, chỉ làm sạch trạng thái Mockito.
- @DirtiesContext loại context khỏi cache và đóng context, sau đó Spring có thể tạo lại toàn bộ bean.

Nếu một test chỉ cần mock không còn invocation hoặc stubbing từ method trước, cơ chế reset mặc định thường đã đủ. Không cần đánh dấu context dirty chỉ vì mock đã được gọi.

Ngược lại, nếu test làm thay đổi bean khác trong context hoặc thay đổi cấu trúc context, reset mock không giải quyết được vấn đề đó. Hãy chọn cơ chế phù hợp với loại trạng thái bị thay đổi.

## 12. Các lỗi thường gặp và cách xử lý

### 12.1. Bật enforceOverride trong test slice

Context slice có thể không chứa service mà test muốn mock. Khi bật enforceOverride, Spring báo không tìm thấy bean. Hãy xác định service có được import vào slice hay cố ý nằm ngoài phạm vi. Nếu nó là dependency cần giả lập của controller, dùng @MockitoBean mặc định.

### 12.2. Quên đăng ký cấu hình chứa bean

Trong test dùng @SpringJUnitConfig hoặc @ContextConfiguration, hãy bảo đảm class cấu hình tạo bean được nạp. Nếu cấu hình bị thiếu, strict override sẽ làm context thất bại. Kiểm tra danh sách classes, component scan và @Import.

### 12.3. Sai qualifier hoặc tên bean

Nếu có nhiều implementation, dùng @Qualifier hoặc name để chọn đúng bean. Kiểm tra chính tả, tên bean do @Bean method tạo ra và qualifier được khai báo trên bean.

### 12.4. Bean bị tắt bởi profile

Kiểm tra @ActiveProfiles và điều kiện @Profile trên cấu hình. Nếu bean chỉ tồn tại ở profile khác, hãy xác định test đang muốn kiểm tra profile nào và nạp cấu hình tương ứng.

### 12.5. Bean bị tắt bởi property

Với @ConditionalOnProperty hoặc điều kiện tương tự, kiểm tra giá trị trong Environment. Nếu bean phải tồn tại trong tình huống test, cung cấp property phù hợp bằng cấu hình test và bật enforceOverride.

### 12.6. Nhầm mock mới với bean bị thay thế

Test context khởi tạo thành công không tự chứng minh bean gốc đã tồn tại. Nếu mục tiêu là xác nhận thay thế một bean đã đăng ký, dùng enforceOverride = true. Nếu mục tiêu chỉ là tạo dependency giả cho slice, mặc định là phù hợp.

### 12.7. Thay nhầm một trong nhiều bean

Khi nhiều bean cùng kiểu, đừng dựa vào lựa chọn ngầm. Chỉ định qualifier hoặc tên và dùng strict override nếu bean phải tồn tại.

### 12.8. Mong test method bắt được lỗi khởi tạo context

Lỗi không tìm thấy bean xuất hiện khi Spring chuẩn bị ApplicationContext, trước khi test method bắt đầu. Không thể dùng assertThrows bên trong method để bắt lỗi bootstrap này. Hãy đọc nguyên nhân gốc trong lỗi context loading và kiểm tra cấu hình bean.

## 13. Mẫu thực hành: kiểm tra bean được đăng ký rồi mới mock

Một ví dụ đầy đủ có thể dùng cấu hình nhỏ để thể hiện rõ bean gốc:

~~~java
@Configuration
class CheckoutTestConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new HttpPaymentGateway();
    }

    @Bean
    CheckoutService checkoutService(PaymentGateway paymentGateway) {
        return new CheckoutService(paymentGateway);
    }
}
~~~

Test thay đúng bean đã đăng ký:

~~~java
@SpringJUnitConfig(CheckoutTestConfiguration.class)
class CheckoutServiceTest {

    @Autowired
    private CheckoutService checkoutService;

    @MockitoBean(enforceOverride = true)
    private PaymentGateway paymentGateway;

    @Test
    void completesCheckoutWhenGatewayAcceptsPayment() {
        // Arrange
        given(paymentGateway.charge(any(PaymentRequest.class)))
            .willReturn(PaymentResult.accepted());

        // Act
        CheckoutResult result =
            checkoutService.checkout(validCommand());

        // Assert
        assertEquals(CheckoutStatus.COMPLETED, result.status());
        then(paymentGateway).should()
            .charge(any(PaymentRequest.class));
    }
}
~~~

Trong ví dụ này, cấu hình khai báo PaymentGateway và CheckoutService. Spring tạo context, tìm bean PaymentGateway rồi thay bằng mock. CheckoutService nhận mock khi được tạo. Nếu xóa phương thức @Bean paymentGateway khỏi cấu hình, context sẽ không thể khởi tạo do enforceOverride yêu cầu bean đó phải tồn tại.

Để so sánh, nếu test chỉ cần một mock cho dependency mà context không đăng ký:

~~~java
@SpringJUnitConfig(CheckoutService.class)
class CheckoutServiceUnitContextTest {

    @MockitoBean
    private PaymentGateway paymentGateway;

    // Mock được tạo nếu context chưa có PaymentGateway.
}
~~~

Ví dụ thứ hai minh họa create-or-replace. Nó phù hợp khi test chủ động tạo một mock để đáp ứng dependency của service. Cấu hình cụ thể phải bảo đảm CheckoutService được đăng ký và có thể được tạo với dependency đó.

## 14. Quy trình quyết định có bật enforceOverride hay không

Trước khi thêm @MockitoBean, hãy trả lời các câu hỏi sau:

1. Bean đang mock có phải được ứng dụng đăng ký trong context này không?
2. Test đang kiểm tra wiring của ứng dụng hay chỉ cô lập một thành phần?
3. Context là full application context hay test slice?
4. Có nhiều bean cùng kiểu cần chọn bằng qualifier hoặc tên không?
5. Bean có bị điều kiện bởi profile hoặc property không?
6. Nếu bean không tồn tại, đó là lỗi cần phát hiện hay là trạng thái bình thường của slice?

Có thể áp dụng quy tắc:

| Mục tiêu | Cách khai báo |
|---|---|
| Thay bean ứng dụng và yêu cầu bean phải có sẵn | @MockitoBean(enforceOverride = true) |
| Tạo mock mới cho dependency không nằm trong slice | @MockitoBean |
| Thay một implementation cụ thể trong số nhiều bean | @MockitoBean(enforceOverride = true) kết hợp @Qualifier hoặc name |
| Theo dõi hành vi thật của bean đã đăng ký | @MockitoSpyBean |
| Kiểm tra bean có được tạo theo profile/conditional config không | Dùng context chứa cấu hình đó và strict override khi thay bean |

## Kết luận

@MockitoBean mặc định có thể thay một bean hiện có hoặc tạo mock mới nếu không tìm thấy bean phù hợp. Đặt enforceOverride = true để yêu cầu Spring chỉ thay bean đã được đăng ký và báo lỗi ngay khi chuẩn bị context nếu bean bị thiếu. Điều này giúp test phát hiện lỗi component scan, profile, conditional configuration và qualifier. Với test slice cố ý loại service khỏi context, mock mới thường là một phần của thiết kế test; hãy dùng strict override khi sự tồn tại của bean trong chính context đó là điều cần được bảo vệ.
