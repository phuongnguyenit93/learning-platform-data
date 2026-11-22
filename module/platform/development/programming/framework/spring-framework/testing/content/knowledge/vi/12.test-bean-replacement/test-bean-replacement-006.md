# REPLACE, REPLACE_OR_CREATE và WRAP

Trong kiểm thử Spring, ta thường cần thay một bean thật bằng mock, fake hoặc một phiên bản có thể quan sát được. Việc thay bean giúp kiểm soát hệ thống bên ngoài, mô phỏng lỗi và tập trung vào hành vi của thành phần đang kiểm thử. Nhưng cách thay thế cần phản ánh đúng mục tiêu: có bài test phải xác nhận bean production thực sự tồn tại rồi mới thay nó; có bài test cần bổ sung một bean giả khi cấu hình slice không nạp bean đó; và có bài test cần giữ implementation thật nhưng bọc nó bằng spy để quan sát tương tác.

Spring TestContext Framework cung cấp ba chiến lược bean override:

- **REPLACE:** thay một bean đã tồn tại. Nếu không tìm thấy bean phù hợp, việc tạo context thất bại.
- **REPLACE_OR_CREATE:** thay bean nếu đã có; nếu chưa có, đăng ký một bean thay thế mới.
- **WRAP:** lấy một bean đã tồn tại và bọc instance đó, thường bằng Mockito spy. Nếu không tìm được đúng một bean phù hợp, việc tạo context thất bại.

Ba chiến lược này không chỉ khác nhau về cú pháp. Chúng thể hiện ba giả định khác nhau về cấu hình ứng dụng và loại bằng chứng mà test muốn có. Chọn sai chiến lược có thể làm test xanh dù cấu hình production đang thiếu bean, hoặc khiến một test vô tình chạy logic thật và gọi hệ thống bên ngoài.

## 1. Bean override trong Spring TestContext

Bean override là cơ chế thay đổi một bean trong ApplicationContext dành riêng cho kiểm thử. Spring tạo context từ cấu hình test, xác định bean cần override theo kiểu và qualifier hoặc tên, rồi áp dụng chiến lược được yêu cầu.

Trong Spring Framework 6.2, cơ chế này được cung cấp qua package:

~~~java
org.springframework.test.context.bean.override
~~~

Các annotation tích hợp phổ biến gồm:

- **@MockitoBean:** đăng ký Mockito mock làm bean trong ApplicationContext.
- **@MockitoSpyBean:** bọc bean hiện có bằng Mockito spy.
- **@TestBean:** thay hoặc cung cấp bean bằng một factory method do test khai báo.

Các annotation này sử dụng hạ tầng bean override chung. Mỗi annotation lựa chọn một chiến lược phù hợp với ý nghĩa của nó. @MockitoBean mặc định dùng REPLACE_OR_CREATE; có thể yêu cầu bean phải tồn tại bằng enforceOverride = true, tương ứng REPLACE. @MockitoSpyBean dùng WRAP vì spy cần một instance thật để bọc.

Bean override được áp dụng trong ApplicationContext của test. Nó không sửa cấu hình production, không thay đổi bean trong một ứng dụng đang chạy ở JVM khác và không phải cơ chế thay bean động cho production runtime.

### 1.1. Bean override khác @Primary và @Profile

Ba cơ chế này có mục đích khác nhau:

| Cơ chế | Mục đích |
| --- | --- |
| Bean override | Thay hoặc bọc bean trong ApplicationContext của test |
| @Primary | Ưu tiên một bean khi có nhiều candidate cho dependency đơn trị |
| @Profile | Chọn nhóm bean theo profile đang hoạt động |

Nếu test dùng @Primary để thêm một mock mới, bean production cũ vẫn có thể tồn tại trong context. Khi đó test có thể không thực sự thay thế collaborator mà SUT đang dùng. Bean override nhắm vào bean cần thay thế theo quy tắc phân giải candidate.

### 1.2. Xác định bean nào sẽ được override

Spring cần xác định một bean candidate phù hợp. Việc phân giải thường dựa trên:

- Kiểu của field hoặc kiểu được khai báo trong bean override.
- Qualifier metadata như @Qualifier hoặc custom qualifier.
- Bean name được chỉ định khi cần chọn theo tên.
- Tên field làm thông tin phân giải bổ sung trong các khai báo field-level phù hợp.

Nếu có nhiều bean cùng kiểu, hãy khai báo qualifier hoặc tên bean rõ ràng. Đừng dựa vào thứ tự component scan hoặc thứ tự method @Bean để chọn implementation.

Ví dụ:

~~~java
@Bean
@Qualifier("stripe")
PaymentGateway stripeGateway() {
    return new StripePaymentGateway();
}

@Bean
@Qualifier("adyen")
PaymentGateway adyenGateway() {
    return new AdyenPaymentGateway();
}
~~~

Một test muốn thay Stripe gateway cần thể hiện qualifier stripe. Nếu chỉ khai báo mock theo kiểu PaymentGateway mà context có hai candidate, Spring không thể suy ra ý định của test một cách đáng tin cậy.

## 2. REPLACE: chỉ thay bean đã tồn tại

REPLACE có nghĩa là test yêu cầu Spring tìm một bean phù hợp trong cấu hình context rồi thay bean đó bằng test bean. Nếu không có candidate phù hợp, context phải thất bại.

Chiến lược này phù hợp khi sự tồn tại của bean production là một phần của điều kiện kiểm thử. Ví dụ:

- Ứng dụng bắt buộc phải có PaymentGateway.
- Một service cần một repository adapter đã được cấu hình.
- Test muốn thay một integration bean nhưng vẫn xác nhận cấu hình ứng dụng có đăng ký bean đó.
- Test cần phát hiện lỗi component scan, profile hoặc configuration class làm bean biến mất.

Với @MockitoBean trong Spring Framework 6.2, có thể dùng:

~~~java
@SpringBootTest
class CheckoutServiceTest {

    @MockitoBean(enforceOverride = true)
    @Qualifier("stripe")
    PaymentGateway stripeGateway;

    @Autowired
    CheckoutService checkoutService;
}
~~~

enforceOverride = true yêu cầu bean tương ứng phải tồn tại trước khi thay. Nếu cấu hình production không đăng ký Stripe gateway hoặc qualifier không khớp, Spring không âm thầm tạo một mock mới để làm test tiếp tục.

### 2.1. Vì sao REPLACE hữu ích?

Giả sử production có:

~~~java
@Configuration
class PaymentConfiguration {

    @Bean
    @Qualifier("stripe")
    PaymentGateway stripeGateway() {
        return new StripePaymentGateway();
    }
}
~~~

CheckoutService nhận gateway:

~~~java
@Service
class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(@Qualifier("stripe") PaymentGateway gateway) {
        this.gateway = gateway;
    }

    PaymentResult pay(PaymentRequest request) {
        return gateway.charge(request);
    }
}
~~~

Nếu test muốn thay đúng gateway production, REPLACE kiểm tra hai việc cùng lúc:

1. Cấu hình context có bean mang qualifier stripe.
2. Test thay đúng bean đó bằng mock để điều khiển phản hồi.

Test có thể xác nhận hành vi service:

~~~java
@SpringBootTest
class CheckoutServiceTest {

    @MockitoBean(enforceOverride = true)
    @Qualifier("stripe")
    PaymentGateway stripeGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void returns_approved_result_when_gateway_approves_payment() {
        PaymentRequest request = PaymentRequestFixtures.validRequest();
        PaymentResult approved = PaymentResult.approved("PAY-101");

        when(stripeGateway.charge(request)).thenReturn(approved);

        PaymentResult actual = checkoutService.pay(request);

        assertThat(actual).isEqualTo(approved);
        verify(stripeGateway).charge(request);
    }
}
~~~

Test dùng gateway mock nhưng CheckoutService thật được tạo bởi Spring. Vì bean override yêu cầu candidate tồn tại, test cũng bảo vệ cấu hình dependency của ứng dụng.

### 2.2. Khi nào REPLACE sẽ làm test thất bại?

Ví dụ, test khai báo:

~~~java
@MockitoBean(enforceOverride = true)
@Qualifier("stripe")
PaymentGateway stripeGateway;
~~~

nhưng context chỉ đăng ký bean qualifier adyen. Test sẽ không thể thay bean mong muốn. Đây là kết quả đúng nếu yêu cầu của test là production phải có Stripe gateway.

Các nguyên nhân thường gặp:

- Bean bị thiếu do component scan không bao phủ package.
- Configuration class chưa được import.
- Profile đang hoạt động không đăng ký bean.
- Qualifier trên bean hoặc injection point bị sai.
- Test nạp nhầm application context.
- Bean name hoặc kiểu khai báo không khớp.

Đừng bỏ enforceOverride chỉ để test xanh nếu bean production bắt buộc phải tồn tại. Trước tiên hãy xác định test có đang dùng đúng cấu hình cần kiểm tra không.

## 3. REPLACE_OR_CREATE: thay nếu có, tạo mới nếu chưa có

REPLACE_OR_CREATE có nghĩa là:

- Nếu tìm thấy bean phù hợp, Spring thay bean đó.
- Nếu không tìm thấy bean phù hợp, Spring đăng ký bean test mới.

Đây là chiến lược mặc định của @MockitoBean trong Spring Framework 6.2:

~~~java
@SpringBootTest
class CheckoutServiceTest {

    @MockitoBean
    @Qualifier("stripe")
    PaymentGateway stripeGateway;
}
~~~

Nếu context đã có bean stripe, bean đó được thay bằng mock. Nếu không có bean phù hợp, một mock bean mới có thể được đăng ký theo khai báo override.

### 3.1. Khi nào REPLACE_OR_CREATE phù hợp?

Chiến lược này hữu ích khi test cần một collaborator giả nhưng không đặt mục tiêu xác nhận bean production đã được đăng ký:

- Test slice chỉ nạp controller nhưng không nạp service thật.
- Test context nhỏ chỉ cần một dependency để tạo SUT.
- Một integration point là tùy chọn trong cấu hình hiện tại.
- Test đang kiểm tra thành phần tiêu thụ một interface, không kiểm tra adapter cụ thể có được cấu hình hay không.
- Test muốn cung cấp mock cho một dependency chưa có trong context tối giản.

Ví dụ, một controller test có thể dùng mock service để kiểm tra HTTP contract:

~~~java
@WebMvcTest(CheckoutController.class)
class CheckoutControllerTest {

    @MockitoBean
    CheckoutService checkoutService;

    @Autowired
    MockMvc mockMvc;
}
~~~

Trong một web slice, CheckoutService thường không được tạo như trong application context đầy đủ. Test cần một mock để controller được inject và có thể điều khiển response. REPLACE_OR_CREATE phù hợp với ý định đó.

### 3.2. Rủi ro: che giấu bean production bị thiếu

Giả sử một service bắt buộc phải dùng Stripe gateway, nhưng production configuration vô tình không đăng ký bean này. Nếu test dùng REPLACE_OR_CREATE, Spring có thể tạo mock mới và ApplicationContext vẫn khởi động.

Test có thể xanh dù ứng dụng thật sẽ không khởi động được khi dùng cùng cấu hình.

Đây là lý do quan trọng để chọn REPLACE khi sự tồn tại của bean production là điều cần bảo vệ. REPLACE_OR_CREATE phù hợp khi việc tạo một bean test mới là một phần có chủ đích của test.

### 3.3. Dùng enforceOverride để chuyển sang REPLACE

Với @MockitoBean:

~~~java
@MockitoBean(enforceOverride = true)
PaymentGateway paymentGateway;
~~~

enforceOverride = true yêu cầu bean phải có sẵn. Đây là lựa chọn phù hợp khi test cần thay một integration bean production đã được cấu hình.

Không dùng enforceOverride chỉ vì muốn test nghiêm ngặt hơn. Nếu test đang dùng @WebMvcTest và service không thuộc slice được nạp, việc bắt buộc bean production tồn tại sẽ đi ngược mục tiêu của slice test. Trong trường hợp đó, REPLACE_OR_CREATE thường đúng hơn.

## 4. WRAP: bọc một bean thật bằng spy

WRAP không tạo một implementation thay thế hoàn toàn. Spring tìm bean hiện có, lấy instance của bean đó và bọc bằng Mockito spy. Spy giữ hành vi thật theo mặc định nhưng cho phép test quan sát lời gọi hoặc stub một số phương thức.

Trong Spring Framework 6.2, @MockitoSpyBean sử dụng chiến lược WRAP:

~~~java
@SpringBootTest
class CheckoutServiceTest {

    @MockitoSpyBean
    @Qualifier("stripe")
    PaymentGateway stripeGateway;

    @Autowired
    CheckoutService checkoutService;
}
~~~

Chiến lược này yêu cầu có đúng một bean phù hợp để bọc. Nếu không có bean, hoặc có nhiều candidate mà không thể phân giải rõ ràng, Spring không thể thực hiện WRAP.

### 4.1. Khi nào WRAP hữu ích?

Spy phù hợp khi test muốn giữ implementation thật và quan sát tương tác:

- Xác nhận service gọi một adapter thật với command đúng.
- Kiểm tra một collaborator thật có được gọi hay không.
- Giữ phần lớn logic của bean nhưng thay một phương thức cụ thể để mô phỏng tình huống khó.
- Kiểm tra một lớp tích hợp trong khi kiểm soát một nhánh phản hồi.

Ví dụ:

~~~java
@SpringBootTest
class CheckoutServiceSpyTest {

    @MockitoSpyBean
    @Qualifier("stripe")
    PaymentGateway stripeGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void delegates_payment_to_real_gateway() {
        PaymentRequest request = PaymentRequestFixtures.validRequest();

        checkoutService.pay(request);

        verify(stripeGateway).charge(request);
    }
}
~~~

Trong ví dụ này, phương thức charge của bean thật được thực thi. Điều đó có thể gọi HTTP client hoặc hệ thống thanh toán thật nếu adapter được cấu hình như production. Vì vậy, spy không tự động làm cho test an toàn khỏi side effect bên ngoài.

Nếu mục tiêu chỉ là xác nhận CheckoutService xử lý kết quả thanh toán, dùng mock với REPLACE thường phù hợp hơn. Nếu mục tiêu là kiểm tra adapter gọi HTTP đúng, hãy dùng server giả lập hoặc môi trường sandbox để điều khiển phía đối tác.

### 4.2. Stub một phần spy

Spy gọi implementation thật theo mặc định. Nếu một phương thức có thể gây side effect hoặc cần một phản hồi cố định, hãy stub phương thức đó:

~~~java
doReturn(PaymentResult.approved("PAY-TEST"))
    .when(stripeGateway)
    .charge(any(PaymentRequest.class));
~~~

Với spy, doReturn(...).when(spy)... thường an toàn hơn when(spy.method()).thenReturn(...) vì cách viết thứ hai có thể gọi phương thức thật ngay trong lúc thiết lập stubbing.

Chỉ stub phần cần kiểm soát. Những phương thức không bị stub vẫn chạy logic thật. Hãy xác định rõ test đang chứng minh điều gì khi kết hợp code thật và hành vi thay thế.

### 4.3. WRAP cần bean singleton hiện có

Bean override trong Spring TestContext tập trung vào singleton bean. WRAP cần một instance hiện có để bọc. Nếu candidate không tồn tại, có nhiều candidate không phân giải được hoặc bean có scope không phù hợp, context có thể thất bại.

Nếu cần quan sát một collaborator được tạo theo request scope hoặc prototype, hãy xem lại ranh giới test. Có thể kiểm tra factory/scope ở một test riêng hoặc dùng một adapter có vòng đời phù hợp, thay vì cố bọc bean không đáp ứng yêu cầu của WRAP.

## 5. So sánh ba chiến lược

| Đặc điểm | REPLACE | REPLACE_OR_CREATE | WRAP |
| --- | --- | --- | --- |
| Bean phù hợp đã tồn tại | Thay bean đó | Thay bean đó | Bọc instance đó |
| Không có bean phù hợp | Lỗi khi tạo context | Tạo bean test mới | Lỗi khi tạo context |
| Nhiều candidate | Cần phân giải đúng một candidate | Cần phân giải đúng candidate để thay; nếu không thể phân giải thì lỗi | Cần xác định đúng một instance để bọc |
| Hành vi mặc định của bean production | Bị thay thế | Bị thay thế nếu có | Vẫn chạy qua spy |
| API Spring thường dùng | @MockitoBean(enforceOverride = true) | @MockitoBean mặc định | @MockitoSpyBean |
| Mục tiêu điển hình | Bảo vệ cấu hình bean hiện có, thay collaborator | Cung cấp mock cho context, kể cả khi bean chưa được đăng ký | Quan sát hoặc stub một bean thật |

Có thể nhớ ý nghĩa bằng ba câu:

- **REPLACE:** “Bean này phải có; hãy thay nó.”
- **REPLACE_OR_CREATE:** “Nếu bean có thì thay; nếu chưa có thì tạo bean test.”
- **WRAP:** “Bean này phải có; hãy giữ instance thật và bọc nó.”

## 6. Chọn chiến lược theo mục tiêu kiểm thử

### 6.1. Kiểm tra service trong application context đầy đủ

Nếu service production bắt buộc có một adapter, dùng REPLACE để test vừa thay adapter vừa bảo vệ cấu hình.

Ví dụ:

~~~java
@SpringBootTest
class InvoiceServiceTest {

    @MockitoBean(enforceOverride = true)
    @Qualifier("invoiceRepository")
    InvoiceRepository invoiceRepository;

    @Autowired
    InvoiceService invoiceService;
}
~~~

Test xác nhận application context có bean repository cần thiết trước khi thay nó. Nếu test chỉ cần điều khiển repository response và không quan tâm production configuration có bean hay không, REPLACE_OR_CREATE có thể phù hợp hơn.

### 6.2. Kiểm tra controller bằng web slice

Trong @WebMvcTest, các service thường không được nạp như trong full application context. Test cần tạo mock để controller có thể được inject:

~~~java
@WebMvcTest(InvoiceController.class)
class InvoiceControllerTest {

    @MockitoBean
    InvoiceService invoiceService;

    @Autowired
    MockMvc mockMvc;
}
~~~

REPLACE_OR_CREATE là lựa chọn tự nhiên cho tình huống này. Test đang kiểm tra MVC contract và cần một collaborator giả. Nó không tuyên bố rằng InvoiceService production đã được cấu hình trong slice.

### 6.3. Quan sát một bean thật

Nếu cần xác nhận một adapter hoặc collaborator thật được gọi, dùng WRAP:

~~~java
@SpringBootTest
class AuditServiceIntegrationTest {

    @MockitoSpyBean
    @Qualifier("auditWriter")
    AuditWriter auditWriter;

    @Autowired
    UserService userService;
}
~~~

Hãy bảo đảm implementation thật không ghi dữ liệu vào hệ thống dùng chung hoặc phát side effect ngoài ý muốn. Nếu có, hãy dùng môi trường test riêng hoặc stub phương thức gây tác động.

### 6.4. Kiểm tra cấu hình thiếu bean

Nếu test cần chứng minh cấu hình bắt buộc có một bean, dùng REPLACE. Nếu dùng REPLACE_OR_CREATE, bean mock mới có thể khiến context khởi động dù production configuration bị thiếu.

Đây là một ví dụ điển hình cho thấy chiến lược override ảnh hưởng đến ý nghĩa của test, không chỉ ảnh hưởng đến cách viết annotation.

## 7. Phân giải khi có nhiều bean cùng kiểu

Giả sử context có:

~~~java
@Bean
@Qualifier("primary")
PaymentGateway primaryGateway() {
    return new PrimaryPaymentGateway();
}

@Bean
@Qualifier("backup")
PaymentGateway backupGateway() {
    return new BackupPaymentGateway();
}
~~~

Để thay đúng bean primary:

~~~java
@MockitoBean(enforceOverride = true)
@Qualifier("primary")
PaymentGateway primaryGateway;
~~~

Để bọc đúng bean backup:

~~~java
@MockitoSpyBean
@Qualifier("backup")
PaymentGateway backupGateway;
~~~

Nếu không khai báo qualifier, Spring có thể dùng các thông tin phân giải khác như tên field hoặc bean name trong trường hợp phù hợp. Tuy nhiên, với nhiều bean cùng kiểu, qualifier tường minh giúp ý định của test dễ hiểu và tránh thay nhầm candidate.

### 7.1. Qualifier không thay đổi tất cả bean cùng kiểu

Một bean override thường nhắm tới candidate được xác định, không có nghĩa mọi bean cùng interface đều bị thay. Nếu test muốn thay nhiều bean, hãy khai báo từng override rõ ràng hoặc dùng cơ chế cấu hình test phù hợp.

Đừng cho rằng thay PaymentGateway bằng mock sẽ tự động thay mọi implementation PaymentGateway trong context. Điều đó có thể làm router, registry hoặc collection injection hoạt động khác với cấu hình thật.

### 7.2. Field name có thể ảnh hưởng lựa chọn

Khi khai báo override trên field, tên field có thể được dùng làm qualifier fallback nếu không có qualifier hoặc tên bean rõ hơn. Điều này tiện cho trường hợp đơn giản nhưng dễ tạo coupling ngầm.

Nếu context có nhiều bean cùng kiểu, hãy khai báo @Qualifier hoặc bean name thay vì đổi tên field để điều khiển lựa chọn một cách khó nhận ra.

## 8. Bean override và vòng đời ApplicationContext

Các khai báo bean override là một phần của cấu hình test context. Chúng có thể ảnh hưởng đến context customizer và cache key của TestContext Framework.

Điều đó có nghĩa:

- Hai test class có cùng cấu hình và cùng override declarations có thể dùng chung ApplicationContext.
- Hai test class có override khác nhau có thể cần context riêng.
- Thêm hoặc bỏ một mock bean có thể làm thay đổi context cần nạp.
- @MockitoBean và @MockitoSpyBean không chỉ là biến Java trong test class; chúng tham gia cấu hình container.

Khi nhiều test dùng chung context có mock bean, Spring quản lý việc reset mock theo cấu hình reset của annotation. Mặc định, mock thường được reset sau mỗi test method để tránh interaction và stubbing rò rỉ sang test khác. Nếu thay đổi reset mode, cần hiểu rõ trạng thái mock có thể được chia sẻ.

Không nên dùng một mock bean có state tích lũy qua nhiều test nếu test không chủ đích kiểm tra state đó. Hãy thiết lập stubbing trong từng test và để lifecycle reset mặc định làm sạch tương tác.

### 8.1. Khác biệt override có thể làm giảm cache reuse

Ví dụ, nhiều test class cùng dùng @SpringBootTest nhưng mỗi class khai báo một tập mock bean khác nhau. Vì context customization khác nhau, Spring có thể phải tạo nhiều context thay vì tái sử dụng một context chung.

Hãy nhóm test theo nhu cầu override tương tự khi phù hợp. Tuy nhiên, không gộp các test vào cùng cấu hình chỉ để tăng cache hit nếu điều đó làm thay đổi phạm vi kiểm thử hoặc tạo state dùng chung khó kiểm soát.

## 9. Các giới hạn và lưu ý

### 9.1. Chỉ override bean phù hợp với cơ chế singleton

Bean override trong Spring TestContext được thiết kế cho singleton bean. Những bean có scope khác như prototype hoặc request scope có thể không được override theo cách mong muốn và có thể làm context thất bại.

Nếu cần kiểm tra scope, hãy kiểm thử scope/lifecycle ở một test riêng. Đừng giả định một mock singleton thay thế được toàn bộ semantics của request-scoped bean.

### 9.2. WRAP có thể thực thi logic thật

Spy không phải mock thuần. Phương thức thật được gọi trừ khi test stub nó. Một spy trên HTTP client, mail sender hoặc payment adapter có thể tạo request thật.

Trước khi dùng WRAP, hãy xác định side effect của bean. Nếu không thể kiểm soát tác động, dùng REPLACE với mock hoặc fake thường an toàn và rõ mục tiêu hơn.

### 9.3. REPLACE_OR_CREATE có thể che giấu lỗi cấu hình

Nếu bean phải có trong production nhưng test dùng REPLACE_OR_CREATE, mock mới có thể làm context khởi động dù cấu hình thật thiếu bean. Hãy dùng REPLACE khi sự tồn tại của bean là một phần cần kiểm tra.

### 9.4. REPLACE không có nghĩa thay mọi candidate

Nếu có nhiều bean cùng kiểu, test vẫn cần xác định đúng bean. Nếu qualifier hoặc tên không đủ rõ, Spring có thể báo lỗi do không phân giải được candidate. Hãy khai báo qualifier tường minh.

### 9.5. Không phải mọi dependency đều cần mock

Mock quá nhiều bean có thể khiến test chỉ xác nhận chuỗi tương tác giữa mock mà không kiểm tra hành vi phối hợp thật. Hãy giữ các bean thuộc phạm vi cần chứng minh và thay những collaborator nằm ngoài ranh giới.

### 9.6. FactoryBean và bean proxy

Một số bean được tạo thông qua FactoryBean hoặc được bọc bởi proxy của Spring. Bean override có quy tắc xử lý riêng cho các trường hợp này và có thể ảnh hưởng loại object được thay hoặc bọc. Khi test nhắm vào FactoryBean, AOP proxy, transaction hoặc security advice, hãy xác định rõ test cần quan sát factory, product bean hay bean proxy và tham khảo tài liệu của phiên bản Spring đang dùng.

Không dùng spy trên target object để kết luận rằng lời gọi đã đi qua proxy và interceptor. Nếu mục tiêu là kiểm tra transaction hoặc security advice, hãy gọi bean từ ApplicationContext qua đúng proxy và xác minh hiệu ứng.

## 10. Phiên bản Spring Boot và annotation tương ứng

Ba chiến lược trên thuộc bean override infrastructure của Spring Framework 6.2. Các annotation @MockitoBean và @MockitoSpyBean được giới thiệu trong phiên bản này.

Spring Boot 3.3.x dựa trên Spring Framework 6.1.x, vì vậy dự án dùng baseline này thường sử dụng annotation cũ của Spring Boot:

~~~java
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.mock.mockito.SpyBean;
~~~

@MockBean và @SpyBean là các API Spring Boot có từ trước cơ chế bean override của Framework 6.2. Chúng có mục tiêu tương tự ở mức sử dụng, nhưng không nên giả định mọi thuộc tính hoặc semantics của chúng giống hoàn toàn với @MockitoBean(enforceOverride = true) và @MockitoSpyBean.

Trong Spring Boot 3.4 trở lên, các annotation @MockBean và @SpyBean được đánh dấu deprecated để chuyển dần sang annotation mới của Spring Framework. Khi viết test, hãy kiểm tra phiên bản Spring Boot và Spring Framework thực tế do dependency management chọn.

| Nền tảng | Annotation thường dùng |
| --- | --- |
| Spring Boot 3.3 / Spring Framework 6.1 | @MockBean, @SpyBean |
| Spring Framework 6.2 trở lên | @MockitoBean, @MockitoSpyBean |
| Spring Boot 3.4 trở lên | Có thể dùng annotation Framework 6.2; annotation Boot cũ được đánh dấu deprecated |

Không nâng riêng spring-test hoặc trộn phiên bản Spring để có annotation mới mà bỏ qua dependency alignment của Spring Boot. Hãy để BOM hoặc dependency management của dự án kiểm soát các module Spring tương thích.

## 11. Ví dụ tổng hợp: chọn đúng strategy cho PaymentGateway

Giả sử CheckoutService nhận PaymentGateway có qualifier stripe. Ta muốn kiểm tra ba mục tiêu khác nhau.

### 11.1. Mục tiêu A: thay bean production đã được cấu hình

Chọn REPLACE:

~~~java
@SpringBootTest
class CheckoutReplaceTest {

    @MockitoBean(enforceOverride = true)
    @Qualifier("stripe")
    PaymentGateway stripeGateway;

    @Autowired
    CheckoutService checkoutService;
}
~~~

Ý nghĩa: test yêu cầu bean stripe phải tồn tại trong context. Nếu thiếu, context fail. Khi tồn tại, mock thay thế bean thật để test điều khiển kết quả thanh toán.

### 11.2. Mục tiêu B: web slice cần một mock service

Chọn REPLACE_OR_CREATE:

~~~java
@WebMvcTest(CheckoutController.class)
class CheckoutControllerTest {

    @MockitoBean
    CheckoutService checkoutService;

    @Autowired
    MockMvc mockMvc;
}
~~~

Ý nghĩa: web slice cần một collaborator để controller được inject. Nếu service không nằm trong slice, mock mới được tạo. Test chỉ kiểm tra HTTP contract và mapping của controller.

### 11.3. Mục tiêu C: quan sát implementation thật

Chọn WRAP:

~~~java
@SpringBootTest
class CheckoutSpyTest {

    @MockitoSpyBean
    @Qualifier("stripe")
    PaymentGateway stripeGateway;

    @Autowired
    CheckoutService checkoutService;
}
~~~

Ý nghĩa: bean stripe phải tồn tại. Spy bọc instance thật để test có thể verify tương tác hoặc stub một số phương thức. Những phương thức không stub vẫn có thể chạy logic thật và gây side effect.

Ba test có thể cùng kiểm tra một luồng nghiệp vụ ở các ranh giới khác nhau. Chúng không nên bị gộp thành một test chỉ để giảm số class, vì mỗi test có một giả định khác nhau về bean và mức độ thực thi code thật.

## 12. Quy trình chọn REPLACE, REPLACE_OR_CREATE hoặc WRAP

Trước khi khai báo bean override, hãy trả lời:

**Bước 1 – Xác định SUT và mục tiêu.** Test đang kiểm tra service, controller, adapter hay cấu hình context?

**Bước 2 – Xác định bean cần can thiệp.** Ghi rõ kiểu, qualifier hoặc bean name. Nếu có nhiều candidate, không để lựa chọn phụ thuộc vào thứ tự đăng ký.

**Bước 3 – Xác định bean production có bắt buộc phải tồn tại không.** Nếu có, chọn REPLACE. Nếu test cố ý tạo một collaborator trong context tối giản, chọn REPLACE_OR_CREATE.

**Bước 4 – Xác định có cần chạy implementation thật không.** Nếu cần giữ hành vi thật và chỉ quan sát hoặc stub một phần, chọn WRAP. Nếu không cần logic thật, dùng mock thay thế.

**Bước 5 – Đánh giá side effect.** WRAP có thể gọi HTTP, database, broker hoặc filesystem thật. Hãy chuẩn bị môi trường cô lập hoặc chọn REPLACE.

**Bước 6 – Kiểm tra context.** Bảo đảm bean candidate được phân giải đúng và strategy phản ánh giả định của test.

**Bước 7 – Viết assertion theo hành vi.** Kiểm tra output, state và interaction có ý nghĩa. Không chỉ kiểm tra mock đã được inject.

**Bước 8 – Xem xét cache và lifecycle.** Những override declarations khác nhau có thể tạo context cache entry khác nhau; mock được reset theo cấu hình lifecycle.

## 13. Bảng quyết định nhanh

| Câu hỏi | Strategy phù hợp |
| --- | --- |
| Bean production bắt buộc phải tồn tại và tôi muốn thay nó bằng mock? | REPLACE |
| Test slice không nạp bean và tôi cần tạo mock để inject vào SUT? | REPLACE_OR_CREATE |
| Tôi muốn giữ bean thật nhưng quan sát lời gọi hoặc stub một phần? | WRAP |
| Tôi muốn test phát hiện bean production bị thiếu? | REPLACE |
| Tôi không quan tâm bean production có được đăng ký trong context tối giản không? | REPLACE_OR_CREATE |
| Bean có side effect bên ngoài và tôi không muốn gọi implementation thật? | REPLACE hoặc REPLACE_OR_CREATE |
| Tôi cần xác nhận một adapter thật được gọi nhưng có thể kiểm soát side effect? | WRAP, kết hợp môi trường giả lập phù hợp |
| Có nhiều bean cùng kiểu? | Bất kỳ strategy nào cũng cần qualifier hoặc tên để chọn đúng candidate |

## Kết luận

REPLACE, REPLACE_OR_CREATE và WRAP biểu đạt ba ý định khác nhau khi thay bean trong Spring test. REPLACE yêu cầu bean production phải tồn tại rồi thay nó; REPLACE_OR_CREATE thay bean nếu có hoặc tạo bean test nếu chưa có; WRAP yêu cầu một bean hiện có và bọc instance thật, thường bằng Mockito spy.

Với Spring Framework 6.2, @MockitoBean mặc định dùng REPLACE_OR_CREATE và có thể bật enforceOverride để yêu cầu REPLACE; @MockitoSpyBean dùng WRAP. Hãy chọn strategy theo điều test cần chứng minh, khai báo qualifier rõ khi có nhiều bean cùng kiểu và chú ý side effect khi dùng spy. Đặc biệt, nếu sự tồn tại của bean production là một phần của hợp đồng cấu hình, hãy dùng REPLACE để test không vô tình che giấu bean bị thiếu.
