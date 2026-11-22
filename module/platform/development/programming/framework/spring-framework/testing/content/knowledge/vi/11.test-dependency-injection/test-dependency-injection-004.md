# @Qualifier khi nhiều bean cùng kiểu

Trong một ứng dụng Spring, nhiều bean có thể cùng triển khai một interface hoặc cùng có một kiểu class. Ví dụ, ứng dụng gửi thông báo có EmailSender và SmsSender cùng triển khai MessageSender; ứng dụng có thể có nhiều PaymentGateway cho các nhà cung cấp khác nhau; hoặc có nhiều DataSource cho các database riêng.

Khi Spring inject một dependency theo kiểu, nếu chỉ có một bean phù hợp thì việc chọn bean thường đơn giản. Nhưng nếu có nhiều bean cùng kiểu, Spring cần thêm thông tin để xác định candidate phù hợp. **@Qualifier** cung cấp thông tin đó tại điểm injection. Nó giúp thu hẹp tập bean theo một nhãn có ý nghĩa, chẳng hạn email, sms, primary-database hoặc external-payment.

Trong kiểm thử Spring, @Qualifier có hai vai trò thường gặp:

- Chọn đúng bean khi test cần inject một trong nhiều bean cùng kiểu.
- Kiểm tra cấu hình ứng dụng thực sự nối đúng collaborator vào system under test (SUT).

Chỉ gắn @Qualifier lên field của test class chưa đủ để chứng minh service đang dùng đúng bean. Nếu mục tiêu là kiểm tra wiring, qualifier phải được áp dụng tại điểm injection của chính SUT và test cần quan sát hành vi qua SUT.

## 1. Vì sao nhiều bean cùng kiểu tạo ra sự mơ hồ?

Giả sử ứng dụng có một interface:

~~~java
public interface MessageSender {
    void send(String recipient, String message);
}
~~~

Hai implementation:

~~~java
@Component
class EmailSender implements MessageSender {
    @Override
    public void send(String recipient, String message) {
        // Gửi email qua mail provider.
    }
}

@Component
class SmsSender implements MessageSender {
    @Override
    public void send(String recipient, String message) {
        // Gửi SMS qua SMS provider.
    }
}
~~~

Một service cần gửi email:

~~~java
@Service
class AccountNotificationService {
    private final MessageSender sender;

    AccountNotificationService(MessageSender sender) {
        this.sender = sender;
    }
}
~~~

Nếu component scan phát hiện cả EmailSender và SmsSender, Spring thấy hai candidate cùng thỏa kiểu MessageSender. Constructor không cung cấp thêm thông tin để chọn một implementation cụ thể. Khi không có quy tắc ưu tiên hoặc qualifier khác, quá trình tạo bean có thể thất bại với NoUniqueBeanDefinitionException.

Đây là lỗi wiring xảy ra khi Spring tạo ApplicationContext. Nó không phải lỗi được phát hiện khi service gọi phương thức send. Vì vậy, nếu mục tiêu kiểm thử là xác minh cấu hình dependency injection, test phải khởi tạo context có các bean liên quan và để Spring thực hiện việc chọn candidate.

## 2. @Qualifier giải quyết việc chọn bean

Có thể gắn qualifier lên bean definition và điểm injection:

~~~java
@Component
@Qualifier("email")
class EmailSender implements MessageSender {
    @Override
    public void send(String recipient, String message) {
        // Gửi email.
    }
}

@Component
@Qualifier("sms")
class SmsSender implements MessageSender {
    @Override
    public void send(String recipient, String message) {
        // Gửi SMS.
    }
}
~~~

Service khai báo qualifier cần dùng:

~~~java
@Service
class AccountNotificationService {
    private final MessageSender sender;

    AccountNotificationService(
            @Qualifier("email") MessageSender sender) {
        this.sender = sender;
    }
}
~~~

Spring trước tiên tìm các bean phù hợp với kiểu dependency, sau đó dùng qualifier để thu hẹp tập candidate. Ở ví dụ này, chỉ EmailSender có qualifier email nên được inject vào constructor.

### 2.1. Đặt @Qualifier ở đâu?

Qualifier có thể xuất hiện tại nhiều vị trí tùy cách đăng ký bean:

| Vị trí | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Class component | @Component kết hợp @Qualifier | Gắn metadata qualifier lên bean được phát hiện qua component scan |
| Phương thức @Bean | @Bean kết hợp @Qualifier | Gắn metadata qualifier lên bean được tạo từ Java configuration |
| Constructor parameter | @Qualifier trên tham số | Chỉ rõ candidate cần inject vào tham số |
| Field injection point | @Autowired và @Qualifier | Chọn bean cho field |
| Setter hoặc method parameter | @Qualifier trên tham số | Chọn bean cho điểm injection tương ứng |
| Test field | @Autowired và @Qualifier | Chọn bean mà test class muốn nhận |

Với code mới, constructor injection thường dễ đọc và dễ kiểm thử hơn field injection. Đặt qualifier trên tham số constructor giúp dependency bắt buộc và lựa chọn implementation được thể hiện ngay khi tạo object.

### 2.2. Dùng Java configuration với @Bean

Không cần dùng component scan để đăng ký nhiều implementation. Có thể khai báo tường minh:

~~~java
@Configuration
class MessageSenderConfiguration {

    @Bean
    @Qualifier("email")
    MessageSender emailSender() {
        return new EmailSender();
    }

    @Bean
    @Qualifier("sms")
    MessageSender smsSender() {
        return new SmsSender();
    }
}
~~~

Qualifier ở phương thức @Bean được gắn với bean definition tương ứng. Điểm injection có thể chọn bean theo qualifier đó:

~~~java
@Bean
AccountNotificationService accountNotificationService(
        @Qualifier("email") MessageSender sender) {
    return new AccountNotificationService(sender);
}
~~~

Khi cấu hình bằng Java, tên phương thức @Bean mặc định cũng là bean name nếu không khai báo tên khác. Ví dụ emailSender là tên bean; email là qualifier metadata. Hai khái niệm có thể có cùng giá trị nhưng không đồng nghĩa.

## 3. @Qualifier khác @Primary như thế nào?

@Primary đánh dấu một bean được ưu tiên khi Spring cần chọn một candidate cho dependency dạng đơn trị và có nhiều bean cùng kiểu. @Qualifier thu hẹp tập candidate dựa trên metadata tại điểm injection.

Ví dụ:

~~~java
@Configuration
class SenderConfiguration {

    @Bean
    @Primary
    MessageSender emailSender() {
        return new EmailSender();
    }

    @Bean
    MessageSender smsSender() {
        return new SmsSender();
    }
}
~~~

Với injection không có qualifier:

~~~java
AccountNotificationService(MessageSender sender) {
    this.sender = sender;
}
~~~

EmailSender được ưu tiên vì có @Primary.

Nếu điểm injection chỉ định:

~~~java
AccountNotificationService(
        @Qualifier("sms") MessageSender sender) {
    this.sender = sender;
}
~~~

Spring chọn bean thỏa qualifier sms. @Primary trên EmailSender không làm EmailSender thắng một qualifier không phù hợp.

| Tiêu chí | @Qualifier | @Primary |
| --- | --- | --- |
| Mục đích | Thu hẹp candidate theo nhãn | Đánh dấu candidate mặc định được ưu tiên |
| Phạm vi lựa chọn | Gắn với điểm injection và metadata bean | Gắn với bean definition |
| Khi có nhiều candidate | Chọn nhóm bean phù hợp qualifier | Ưu tiên bean primary khi cần một bean |
| Có thể dùng cùng nhau? | Có | Có |
| Collection injection | Có thể lọc collection theo qualifier | Không loại các bean không primary khỏi collection |

Không nên dùng @Primary để che giấu một dependency thực ra cần phân biệt rõ theo nghiệp vụ. Nếu service cần email, khai báo qualifier email giúp ý định rõ hơn một lựa chọn mặc định toàn cục.

## 4. Qualifier không chỉ là bean name

Một nhầm lẫn phổ biến là xem @Qualifier("emailSender") như một cách khác để tham chiếu bean name. Spring có thể dùng bean name làm fallback khi so khớp qualifier, nhưng ý nghĩa chính của qualifier là nhãn ngữ nghĩa dùng để lọc candidate.

Ví dụ, có thể khai báo bean name khác qualifier:

~~~java
@Bean("smtpClient")
@Qualifier("email")
MessageSender outboundEmailSender() {
    return new EmailSender();
}
~~~

Điểm injection:

~~~java
NotificationService(@Qualifier("email") MessageSender sender) {
    // ...
}
~~~

Ở đây:

- Bean name là smtpClient.
- Qualifier value là email.
- Dependency yêu cầu một MessageSender mang qualifier email.

Đặt qualifier theo vai trò hoặc mục đích thường giúp cấu hình dễ hiểu hơn. Ví dụ, một hệ thống có thể có nhiều bean gửi email nhưng khác loại: transactional, marketing hoặc audit. Dùng qualifier transactional mô tả vai trò của bean tốt hơn tên class implementation.

### 4.1. Khi nào dùng @Resource?

@Resource thường được dùng khi muốn inject một resource theo tên cụ thể. @Qualifier kết hợp với @Autowired vẫn bắt đầu từ kiểu dependency rồi dùng qualifier để lọc candidate.

| Tình huống | Lựa chọn thường phù hợp |
| --- | --- |
| Chọn một implementation theo vai trò/ngữ nghĩa | @Autowired kết hợp @Qualifier |
| Chọn đúng một resource theo tên | @Resource(name = "...") |
| Chọn bean mặc định trong nhiều implementation | @Primary |
| Inject tất cả implementation phù hợp | List, Set, array hoặc Map theo kiểu |

Không nên chọn annotation chỉ theo thói quen. Hãy diễn đạt rõ dependency cần một bean theo vai trò, theo tên hay theo quy tắc mặc định.

## 5. Nhiều qualifier và custom qualifier

Một dependency đôi khi cần nhiều thuộc tính để phân biệt. Ví dụ hệ thống có nhiều PaymentGateway và cần chọn gateway có vai trò external ở khu vực eu.

Có thể đặt nhiều qualifier metadata:

~~~java
@Bean
@Qualifier("external")
@Region("eu")
PaymentGateway europeanExternalGateway() {
    return new EuropeanPaymentGateway();
}
~~~

Điểm injection yêu cầu các metadata tương ứng:

~~~java
PaymentService(
        @Qualifier("external") @Region("eu")
        PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Các qualifier được kết hợp để thu hẹp candidate. Bean phải thỏa các điều kiện qualifier mà điểm injection yêu cầu.

### 5.1. Tạo custom qualifier annotation

Nếu một nhãn được dùng nhiều nơi, có thể tạo annotation riêng được meta-annotate bằng @Qualifier.

~~~java
@Target({
    ElementType.FIELD,
    ElementType.PARAMETER,
    ElementType.METHOD,
    ElementType.TYPE,
    ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface Region {
    String value();
}
~~~

Đăng ký bean:

~~~java
@Bean
@Region("eu")
PaymentGateway europeanGateway() {
    return new EuropeanPaymentGateway();
}

@Bean
@Region("us")
PaymentGateway americanGateway() {
    return new AmericanPaymentGateway();
}
~~~

Inject bean:

~~~java
PaymentService(@Region("eu") PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Custom qualifier giúp code thể hiện domain language và tránh rải các chuỗi tùy ý ở nhiều nơi. Nếu annotation có nhiều thuộc tính, Spring có thể dùng các thuộc tính đó trong quá trình so khớp qualifier.

Không nên tạo custom qualifier cho mọi bean. Một annotation mới chỉ hữu ích khi nó biểu diễn một phân loại ổn định và có ý nghĩa trong cấu hình.

## 6. @Qualifier với collection injection

Khi inject một List hoặc Set của một kiểu, Spring thường cung cấp tất cả bean phù hợp kiểu đó. @Qualifier tại điểm injection có thể lọc collection theo qualifier.

Ví dụ:

~~~java
@Component
@Qualifier("internal")
class InternalPaymentGateway implements PaymentGateway {
    // ...
}

@Component
@Qualifier("external")
class StripePaymentGateway implements PaymentGateway {
    // ...
}

@Component
@Qualifier("external")
class AdyenPaymentGateway implements PaymentGateway {
    // ...
}
~~~

Một service nhận tất cả gateway bên ngoài:

~~~java
class ExternalPaymentRouter {
    private final List<PaymentGateway> gateways;

    ExternalPaymentRouter(
            @Qualifier("external") List<PaymentGateway> gateways) {
        this.gateways = List.copyOf(gateways);
    }
}
~~~

Danh sách chỉ chứa các bean mang qualifier external. Đây là điểm khác biệt quan trọng so với @Primary: @Primary không có nghĩa các bean không primary bị loại khỏi collection injection.

Spring cũng hỗ trợ inject Map với key là bean name và value là bean instance:

~~~java
class PaymentGatewayRegistry {
    private final Map<String, PaymentGateway> gateways;

    PaymentGatewayRegistry(Map<String, PaymentGateway> gateways) {
        this.gateways = Map.copyOf(gateways);
    }
}
~~~

Trong trường hợp này, Map thể hiện các bean theo tên. Nếu cần lọc theo một nhóm qualifier, có thể dùng qualifier ở điểm injection collection phù hợp.

## 7. Qualifier và generic type

Kiểu generic cũng có thể giúp Spring phân biệt một số dependency. Ví dụ:

~~~java
interface Store<T> {
    void save(T value);
}

class StringStore implements Store<String> {
    public void save(String value) {
    }
}

class IntegerStore implements Store<Integer> {
    public void save(Integer value) {
    }
}
~~~

Điểm injection Store<String> có thể được phân biệt với Store<Integer> nhờ generic type metadata. Nếu có nhiều Store<String> cùng tồn tại, qualifier vẫn có thể cần thiết để chỉ rõ vai trò hoặc implementation mong muốn.

Không nên dựa vào tên class hoặc thứ tự đăng ký bean để chọn implementation. Hãy khai báo kiểu và qualifier đủ rõ để cấu hình không phụ thuộc thứ tự scan hoặc thứ tự file.

## 8. Kiểm thử @Qualifier với Spring TestContext

Kiểm thử qualifier nên xác nhận Spring thật sự tạo các bean và chọn đúng candidate. Có thể dùng @SpringJUnitConfig để nạp một context nhỏ mà không cần khởi động toàn bộ ứng dụng.

### 8.1. Tạo cấu hình test với hai bean cùng kiểu

Giả sử có service:

~~~java
class NotificationService {
    private final MessageSender sender;

    NotificationService(
            @Qualifier("email") MessageSender sender) {
        this.sender = sender;
    }

    void notify(String recipient, String message) {
        sender.send(recipient, message);
    }
}
~~~

Test configuration:

~~~java
@Configuration
class NotificationTestConfiguration {

    @Bean
    @Qualifier("email")
    MessageSender emailSender() {
        return Mockito.mock(MessageSender.class);
    }

    @Bean
    @Qualifier("sms")
    MessageSender smsSender() {
        return Mockito.mock(MessageSender.class);
    }

    @Bean
    NotificationService notificationService(
            @Qualifier("email") MessageSender sender) {
        return new NotificationService(sender);
    }
}
~~~

Ở đây, hai bean cùng kiểu MessageSender được đăng ký trong cùng ApplicationContext. Constructor của NotificationService yêu cầu qualifier email. Spring phải chọn đúng bean khi tạo NotificationService.

### 8.2. Kiểm tra bean được inject vào SUT

~~~java
@SpringJUnitConfig(NotificationTestConfiguration.class)
class NotificationQualifierTest {

    @Autowired
    NotificationService notificationService;

    @Autowired
    @Qualifier("email")
    MessageSender emailSender;

    @Autowired
    @Qualifier("sms")
    MessageSender smsSender;

    @Test
    void injects_email_sender_into_notification_service() {
        notificationService.notify("user@example.com", "Welcome");

        Mockito.verify(emailSender)
            .send("user@example.com", "Welcome");
        Mockito.verifyNoInteractions(smsSender);
    }
}
~~~

Test này kiểm tra cả hai lớp:

1. @Qualifier trên field test giúp inject riêng emailSender và smsSender để test quan sát.
2. @Qualifier trên constructor của NotificationService quyết định bean được inject vào SUT.

Nếu chỉ viết:

~~~java
@Autowired
@Qualifier("email")
MessageSender emailSender;
~~~

thì test chỉ chứng minh test class nhận được bean email. Nó không chứng minh một service khác cũng được nối với email bean. Muốn kiểm tra wiring của service, cần inject service thật và gọi hành vi của service như ví dụ trên.

### 8.3. Kiểm tra ambiguity khi thiếu qualifier

Có thể tạo một test cấu hình tối giản để xác nhận hai bean cùng kiểu gây lỗi nếu một dependency đơn trị không có qualifier và không có @Primary. Tuy nhiên, việc kiểm tra exception khởi tạo context nên được thực hiện có chủ đích vì context failure thường xuất hiện trước khi test method chạy.

Trong phần lớn suite, test cấu hình thành công với qualifier đúng đã chứng minh wiring cần thiết. Nếu muốn bảo vệ hành vi fail-fast của cấu hình, hãy dùng một context riêng hoặc một ApplicationContextRunner trong hệ sinh thái Spring Boot để xác nhận context không khởi động khi candidate mơ hồ.

Không làm cho test suite chính thất bại bằng cách cố tình đăng ký một context lỗi trong cùng cấu hình dùng chung.

## 9. Kiểm thử @Qualifier trong Spring Boot

Với ứng dụng Spring Boot, có thể dùng @SpringBootTest khi muốn kiểm tra bean wiring trong application context đầy đủ:

~~~java
@SpringBootTest
class NotificationServiceIntegrationTest {

    @Autowired
    NotificationService notificationService;

    @Autowired
    @Qualifier("email")
    MessageSender emailSender;

    @Test
    void uses_email_sender_for_account_notifications() {
        notificationService.notify("user@example.com", "Welcome");

        // Assertion phù hợp với implementation hoặc test adapter.
    }
}
~~~

Nếu email sender gọi hệ thống ngoài, không nên gửi email thật chỉ để kiểm tra qualifier. Hãy thay adapter ngoài bằng mock, fake hoặc server giả lập, nhưng vẫn giữ bean wiring của NotificationService và điểm injection cần kiểm tra.

Trong Spring Boot Test, @MockBean có thể thay một bean trong ApplicationContext bằng Mockito mock. Khi có nhiều bean cùng kiểu, hãy xác định rõ bean cần thay theo tên hoặc qualifier phù hợp với phiên bản đang dùng. Điều quan trọng là bean bị thay phải đúng collaborator mà SUT nhận; nếu thay nhầm một implementation khác, test có thể không điều khiển được hành vi mong muốn.

### 9.1. Không để @Primary che mất lỗi qualifier

Giả sử production service có constructor yêu cầu @Qualifier("email"). Nếu test configuration chỉ đăng ký một bean @Primary mà không đăng ký qualifier email, test không còn kiểm tra đúng hợp đồng lựa chọn bean ban đầu.

Khi mục tiêu là kiểm tra @Qualifier, test nên giữ các qualifier metadata giống cấu hình ứng dụng hoặc tạo test bean với qualifier tương ứng. Không thêm @Primary chỉ để làm context khởi động được nếu nó che giấu một cấu hình qualifier sai.

### 9.2. Dùng @TestConfiguration để bổ sung bean kiểm thử

Spring Boot cho phép khai báo cấu hình riêng cho test bằng @TestConfiguration. Có thể dùng nó để cung cấp một adapter giả hoặc một bean có qualifier rõ ràng:

~~~java
@TestConfiguration
class NotificationAdapterTestConfiguration {

    @Bean
    @Primary
    @Qualifier("email")
    MessageSender testEmailSender() {
        return new RecordingMessageSender();
    }
}
~~~

Ví dụ trên minh họa cách khai báo test bean. Nếu context đã có bean cùng tên hoặc cùng qualifier, cần chọn chiến lược thay thế phù hợp với cấu hình ứng dụng và cơ chế bean overriding đang bật. Không dựa vào @Primary để bỏ qua sự mơ hồ nếu mục tiêu là kiểm tra chính qualifier.

## 10. Xử lý các lỗi thường gặp

### NoUniqueBeanDefinitionException

Lỗi xuất hiện khi Spring tìm thấy nhiều bean phù hợp cho một dependency đơn trị nhưng không có qualifier, @Primary hoặc quy tắc phân giải khác để chọn một candidate.

Cách xử lý:

- Xác định các bean cùng kiểu trong context.
- Kiểm tra điểm injection của SUT.
- Thêm qualifier có ý nghĩa lên bean definition và injection point nếu nghiệp vụ cần một implementation cụ thể.
- Dùng @Primary nếu thật sự có một implementation mặc định hợp lý.
- Nếu cần tất cả implementation, inject collection thay vì một bean đơn.

### NoSuchBeanDefinitionException

Lỗi có thể xuất hiện khi không có bean nào phù hợp kiểu hoặc qualifier yêu cầu. Hãy kiểm tra:

- Bean đã được đăng ký chưa?
- Qualifier value có khớp metadata không?
- Bean có bị loại bởi profile hoặc condition không?
- Test context có nạp đúng configuration class không?
- Bean override trong test có thay đúng bean không?

### Qualifier đặt sai phía

Gắn @Qualifier chỉ trên field của test class không thay đổi cách Spring inject dependency vào service. Qualifier phải xuất hiện tại constructor, field hoặc method parameter của SUT nếu mục tiêu là chọn collaborator cho SUT.

### Nhầm qualifier với bean name

Một bean có thể có bean name smtpClient và qualifier email. Hãy kiểm tra metadata và điểm injection thay vì chỉ nhìn tên phương thức @Bean.

### Dùng @Primary khi cần nhiều bean

@Primary chỉ ưu tiên candidate cho dependency đơn trị. Nếu service cần một danh sách implementation, hãy inject List hoặc Map và dùng qualifier để lọc khi phù hợp.

### Test dùng mock nhưng SUT vẫn gọi implementation thật

Có thể test đã mock bean cùng kiểu nhưng không phải bean được qualifier chọn. Hãy xác định bean name và qualifier của collaborator, sau đó verify mock thực sự nhận lời gọi từ SUT.

### Component scan tạo thêm bean ngoài dự kiến

Test context có thể quét cả implementation không cần thiết. Hãy thu hẹp component scan, import cấu hình rõ ràng hoặc dùng profile phù hợp. Không xóa một bean chỉ để test qua nếu bean đó cần tồn tại trong môi trường thực tế.

## 11. Các lưu ý về thiết kế

### 11.1. Dùng qualifier theo vai trò

Tên qualifier nên biểu diễn vai trò, mục đích hoặc nhóm cấu hình:

- email, sms.
- primary-database, audit-database.
- external-payment, internal-payment.
- eu, us.
- transactional, marketing.

Tránh tên quá gắn với class hoặc vendor nếu vai trò mới là điều ứng dụng cần. Khi implementation thay đổi, qualifier theo vai trò có thể giữ ổn định.

### 11.2. Không tạo qualifier trùng lặp vô nghĩa

Nếu trong toàn bộ context chỉ có một bean của kiểu đó và không có nhu cầu chọn theo vai trò, qualifier có thể không cần thiết. Thêm annotation cho mọi dependency làm cấu hình dài và tăng chi phí bảo trì.

### 11.3. Không dựa vào thứ tự đăng ký bean

Không dùng thứ tự component scan, thứ tự method @Bean hoặc thứ tự classpath để quyết định implementation nào được inject. Hãy dùng qualifier, @Primary hoặc collection với quy tắc sắp xếp rõ ràng nếu thứ tự có ý nghĩa.

### 11.4. Tách nhiều trách nhiệm thay vì thêm quá nhiều qualifier

Nếu một interface có hàng chục implementation và mỗi service phải chọn bằng tổ hợp qualifier phức tạp, có thể abstraction đang quá rộng. Hãy cân nhắc tách interface theo khả năng hoặc dùng một registry/router có trách nhiệm rõ ràng.

Qualifier là công cụ lựa chọn bean, không phải cơ chế thay thế thiết kế domain.

## 12. Quy trình kiểm thử wiring với @Qualifier

Có thể áp dụng quy trình sau:

**Bước 1 – Liệt kê các bean cùng kiểu.** Xác định interface hoặc class có nhiều implementation trong context.

**Bước 2 – Xác định vai trò của SUT.** Làm rõ SUT cần implementation nào và vì sao.

**Bước 3 – Gắn metadata qualifier.** Đặt qualifier lên bean definition hoặc custom qualifier annotation theo vai trò.

**Bước 4 – Đặt qualifier ở điểm injection của SUT.** Ưu tiên constructor parameter để dependency rõ ràng.

**Bước 5 – Tạo test context.** Dùng @SpringJUnitConfig cho context nhỏ hoặc @SpringBootTest khi cần application context đầy đủ.

**Bước 6 – Inject các candidate vào test khi cần quan sát.** Dùng @Autowired kết hợp @Qualifier để nhận đúng bean test cần verify.

**Bước 7 – Gọi hành vi qua SUT.** Không chỉ kiểm tra test class có inject được bean.

**Bước 8 – Xác nhận đúng collaborator được dùng.** Dùng recording fake, output có thể quan sát hoặc Mockito verify ở ranh giới thích hợp.

**Bước 9 – Kiểm tra cấu hình lỗi nếu cần.** Xác nhận ambiguity hoặc qualifier không khớp làm context fail theo cách mong muốn trong một context test riêng.

**Bước 10 – Đảm bảo test không gọi hệ thống ngoài.** Thay adapter bên ngoài bằng mock/fake hoặc server giả lập, đồng thời giữ bean wiring đang được kiểm tra.

## 13. Bảng quyết định nhanh

| Nhu cầu | Cách chọn |
| --- | --- |
| Có một bean cùng kiểu | Injection theo kiểu thường là đủ |
| Có nhiều bean, cần một implementation cụ thể | @Qualifier tại điểm injection |
| Có một implementation mặc định cho dependency đơn trị | @Primary |
| Cần tất cả implementation | Inject List, Set hoặc Map |
| Cần lọc một nhóm bean trong collection | @Qualifier trên điểm injection collection |
| Cần phân biệt theo nhiều thuộc tính ổn định | Nhiều qualifier hoặc custom qualifier |
| Test muốn inject riêng từng bean để quan sát | @Autowired kết hợp @Qualifier trên test field/parameter |
| Test muốn chứng minh SUT nhận đúng bean | Qualifier trên injection point của SUT và gọi qua SUT |
| Test muốn thay một collaborator bên ngoài | Mock/fake đúng bean được qualifier chọn |

## Kết luận

@Qualifier giúp Spring chọn đúng bean khi có nhiều candidate cùng kiểu bằng cách thu hẹp tập bean theo metadata có ý nghĩa. Nó có thể được khai báo trên component, phương thức @Bean và điểm injection; custom qualifier giúp biểu diễn các thuộc tính phân loại ổn định. @Primary phù hợp để chọn một bean mặc định cho dependency đơn trị, còn @Qualifier diễn đạt rõ dependency cần vai trò nào. Khi inject collection, qualifier có thể lọc nhóm bean cần dùng.

Trong Spring Testing, cần phân biệt việc test class nhận được bean nào với việc SUT thực sự được inject bean nào. Hãy tạo context có các candidate thật, đặt qualifier tại constructor hoặc điểm injection của SUT, gọi hành vi qua SUT và quan sát collaborator được sử dụng. Cách kiểm tra này bảo vệ cấu hình dependency injection mà không phải dựa vào tên class, thứ tự đăng ký bean hoặc một mock được đặt nhầm vị trí.
