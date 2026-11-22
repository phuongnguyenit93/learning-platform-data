# Tránh dùng Dependency Injection như bằng chứng duy nhất rằng nghiệp vụ đúng

Dependency Injection (DI) giúp Spring cung cấp các dependency cần thiết cho một bean. Khi ApplicationContext khởi động thành công, ta có bằng chứng rằng Spring đã đọc cấu hình, tạo được các bean cần thiết và giải quyết được những quan hệ phụ thuộc trong context đó.

Tuy nhiên, **inject được dependency không có nghĩa nghiệp vụ của ứng dụng đã đúng**. Một service có thể nhận đầy đủ repository, policy và gateway nhưng vẫn tính sai tiền, áp dụng sai quy tắc, xử lý nhầm trạng thái hoặc tạo tác động không mong muốn. DI xác nhận khả năng kết nối các thành phần; kiểm thử hành vi mới xác nhận các thành phần đó làm đúng điều hệ thống yêu cầu.

Trong Spring Framework Testing, cần phân biệt rõ ba câu hỏi:

1. Spring có tạo và kết nối đúng các bean không?
2. Một service có thực hiện đúng quy tắc nghiệp vụ với đầu vào và trạng thái đã cho không?
3. Các thành phần thật có phối hợp đúng qua database, transaction, proxy hoặc giao tiếp bên ngoài không?

Mỗi câu hỏi cần bằng chứng và phạm vi kiểm thử phù hợp. Một bài kiểm thử context có thể trả lời câu hỏi thứ nhất nhưng không tự động trả lời hai câu hỏi còn lại.

## 1. DI chứng minh điều gì?

Giả sử ứng dụng có service xử lý chuyển tiền:

~~~java
@Service
public class TransferService {

    private final AccountRepository accountRepository;
    private final TransferPolicy transferPolicy;

    public TransferService(
            AccountRepository accountRepository,
            TransferPolicy transferPolicy) {
        this.accountRepository = accountRepository;
        this.transferPolicy = transferPolicy;
    }

    public TransferReceipt transfer(
            String sourceId,
            String destinationId,
            BigDecimal amount) {
        // Quy tắc chuyển tiền và phối hợp repository.
    }
}
~~~

Khi Spring tạo được TransferService, điều đó cho thấy container tìm được các dependency phù hợp để truyền vào constructor theo cấu hình đang hoạt động.

Một context test có thể xác nhận bean tồn tại:

~~~java
@SpringBootTest
class TransferServiceContextTest {

    @Autowired
    private TransferService transferService;

    @Test
    void createsTransferServiceBean() {
        assertNotNull(transferService);
    }
}
~~~

Test này có ích như một smoke test cho việc khởi tạo context. Nó có thể phát hiện các lỗi như:

- Không có bean nào phù hợp với kiểu AccountRepository.
- Có nhiều bean cùng kiểu nhưng không có lựa chọn rõ ràng.
- Một constructor dependency bị thiếu.
- Một configuration class không được nạp.
- Component scan không tìm thấy service.
- Một bean phụ thuộc vào cấu hình hoặc tài nguyên khiến ApplicationContext không thể khởi động.

Đó là bằng chứng về cấu hình và wiring. Test chưa gọi transfer(), chưa kiểm tra số dư, chưa xác nhận tài khoản nào bị ghi nợ và chưa kiểm tra giao dịch có được lưu đúng hay không.

### Những điều DI không chứng minh

Việc inject thành công không chứng minh:

- Service áp dụng đúng quy tắc nghiệp vụ.
- Giá trị trả về đúng với dữ liệu đầu vào.
- Exception được ném đúng trong tình huống không hợp lệ.
- Repository thực thi truy vấn đúng hoặc lưu dữ liệu chính xác.
- Bean được chọn là implementation phù hợp về mặt nghiệp vụ.
- Transaction rollback khi một bước thất bại.
- Event hoặc request gửi sang hệ thống khác có payload đúng.
- Một tác động không được phép đã không xảy ra.

Ví dụ, Spring có thể inject thành công một bean DiscountPolicy, nhưng policy đó có thể áp dụng mức giảm giá sai. Tương tự, OrderService có thể nhận đúng OrderRepository nhưng vẫn lưu đơn ở trạng thái PAID trong khi yêu cầu quy định trạng thái PENDING.

**Khởi động context thành công là điều kiện về cấu hình, không phải kết luận về chất lượng nghiệp vụ.**

## 2. Phân biệt ba lớp bằng chứng

Một bộ kiểm thử Spring thường cần các lớp bằng chứng khác nhau:

| Lớp bằng chứng | Câu hỏi | Cách kiểm tra thường dùng |
|---|---|---|
| Wiring/configuration | Bean nào được tạo và dependency nào được inject? | Context test, @SpringJUnitConfig, @SpringBootTest |
| Business behavior | Public method trả về gì, từ chối điều kiện nào, tạo tác động nào? | Unit test với JUnit Jupiter và test doubles |
| Integration behavior | Bean thật, proxy, database và hệ thống tích hợp phối hợp ra sao? | Integration test với Spring context và hạ tầng phù hợp |

Các lớp này bổ sung cho nhau. Unit test có thể xác nhận quy tắc tính phí mà không cần Spring. Context test có thể xác nhận service và policy được cấu hình thành bean. Integration test có thể xác nhận transaction và repository thật cùng hoạt động.

Không nên lấy kết quả của một lớp để thay thế bằng chứng của lớp khác.

### Ví dụ với chuyển tiền

Giả sử hợp đồng nghiệp vụ quy định:

- Số tiền chuyển phải lớn hơn 0.
- Tài khoản nguồn và tài khoản nhận phải tồn tại.
- Tài khoản nguồn phải có đủ số dư.
- Tài khoản nhận được cộng đúng số tiền.
- Tài khoản nguồn bị trừ đúng số tiền.
- Giao dịch được ghi nhận với trạng thái COMPLETED.
- Nếu ghi nhận giao dịch thất bại trong một transaction, các thay đổi số dư phải rollback.

Mỗi cam kết có thể có rủi ro khác nhau:

- Constructor injection có thể thất bại vì thiếu AccountRepository.
- Service có thể trừ tiền hai lần hoặc tính sai số dư.
- Repository có thể lưu sai trạng thái giao dịch.
- Transaction có thể không rollback khi bước ghi giao dịch thất bại.

Một context test chỉ xác nhận bean được tạo sẽ không phát hiện được các lỗi nghiệp vụ và persistence đó.

## 3. Vì sao contextLoads() chưa đủ?

Một test phổ biến trong dự án Spring Boot có dạng:

~~~java
@SpringBootTest
class ApplicationContextTest {

    @Test
    void contextLoads() {
    }
}
~~~

Test này yêu cầu Spring khởi động ApplicationContext. Nếu context khởi động được, test thành công. Đây là kiểm tra hữu ích cho cấu hình tổng thể, nhưng phương thức test không kích hoạt một hành vi nghiệp vụ cụ thể.

Ví dụ, test vẫn có thể thành công trong các trường hợp:

- DiscountService trả về mức giảm giá sai.
- TransferService bỏ qua kiểm tra số dư.
- Một mapper chuyển nhầm trạng thái entity.
- Một controller trả về HTTP 200 thay vì HTTP 201.
- Một repository query lọc nhầm điều kiện.
- Một event chứa sai mã khách hàng.
- Một service lưu dữ liệu trước khi kiểm tra quyền.

Các lỗi này không nhất thiết ngăn ApplicationContext khởi động. Bean có thể được tạo hoàn toàn hợp lệ nhưng logic bên trong vẫn sai.

Hãy giữ contextLoads() nếu cần smoke test cho khả năng khởi tạo ứng dụng. Đồng thời, viết các test hành vi có assertion cụ thể cho những quy tắc quan trọng.

### Context startup test và behavior test

~~~java
@SpringBootTest
class TransferServiceTest {

    @Autowired
    private TransferService transferService;

    @Test
    void contextLoads() {
        assertNotNull(transferService);
    }

    @Test
    void transfersFundsAccordingToBusinessRules() {
        // Cần chuẩn bị trạng thái tài khoản,
        // kích hoạt transfer và kiểm tra số dư/kết quả.
    }
}
~~~

Phương thức đầu tiên chỉ xác nhận bean có thể được inject. Phương thức thứ hai mới bắt đầu kiểm tra hành vi. Nếu muốn kiểm tra nghiệp vụ qua service thật trong context, phải chuẩn bị dữ liệu, gọi public method và xác nhận kết quả có ý nghĩa.

## 4. Kiểm thử quy tắc nghiệp vụ qua public method

Unit test nên gọi public API của service như một caller thực sự. Test chuẩn bị trạng thái ban đầu, gọi method và kiểm tra kết quả quan sát được.

Ví dụ dưới đây mô tả một TransferService độc lập với Spring container:

~~~java
public class TransferService {

    private final AccountRepository accountRepository;
    private final TransferPolicy transferPolicy;

    public TransferService(
            AccountRepository accountRepository,
            TransferPolicy transferPolicy) {
        this.accountRepository = accountRepository;
        this.transferPolicy = transferPolicy;
    }

    public TransferReceipt transfer(
            String sourceId,
            String destinationId,
            BigDecimal amount) {

        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Transfer amount must be positive");
        }

        Account source = accountRepository.findById(sourceId)
                .orElseThrow(() ->
                        new AccountNotFoundException(sourceId));

        Account destination = accountRepository
                .findById(destinationId)
                .orElseThrow(() ->
                        new AccountNotFoundException(destinationId));

        transferPolicy.checkAllowed(source, destination, amount);

        source.debit(amount);
        destination.credit(amount);

        accountRepository.save(source);
        accountRepository.save(destination);

        return new TransferReceipt(
                sourceId,
                destinationId,
                amount,
                TransferStatus.COMPLETED);
    }
}
~~~

Các interface và kiểu miền nghiệp vụ được minh họa như sau:

~~~java
public interface AccountRepository {
    Optional<Account> findById(String accountId);

    Account save(Account account);
}

public interface TransferPolicy {
    void checkAllowed(
            Account source,
            Account destination,
            BigDecimal amount);
}

public record TransferReceipt(
        String sourceId,
        String destinationId,
        BigDecimal amount,
        TransferStatus status) {
}

public enum TransferStatus {
    COMPLETED
}
~~~

Ví dụ giả định Account có các phương thức debit và credit để bảo vệ quy tắc số dư. Nó cũng giả định TransferPolicy ném exception miền nghiệp vụ khi giao dịch không được phép.

Để kiểm tra quy tắc service, có thể tạo TransferService trực tiếp bằng constructor. Không cần khởi động Spring chỉ để xác nhận amount phải dương hoặc số tiền chuyển được tính đúng.

## 5. Dùng unit test để chứng minh hành vi, không chỉ chứng minh bean tồn tại

Mockito cho phép điều khiển kết quả dependency để đưa service vào từng nhánh nghiệp vụ. Test có thể xác nhận receipt, số dư được yêu cầu cập nhật và các tác động bị ngăn chặn.

Ví dụ kiểm tra chuyển tiền thành công:

~~~java
@ExtendWith(MockitoExtension.class)
class TransferServiceUnitTest {

    @Mock
    private AccountRepository accountRepository;

    @Mock
    private TransferPolicy transferPolicy;

    @InjectMocks
    private TransferService transferService;

    @Test
    void transfersRequestedAmountBetweenExistingAccounts() {
        Account source = new Account(
                "A-1", new BigDecimal("100.00"));
        Account destination = new Account(
                "B-2", new BigDecimal("40.00"));

        when(accountRepository.findById("A-1"))
                .thenReturn(Optional.of(source));
        when(accountRepository.findById("B-2"))
                .thenReturn(Optional.of(destination));

        TransferReceipt receipt = transferService.transfer(
                "A-1", "B-2", new BigDecimal("25.00"));

        assertAll(
                () -> assertEquals(
                        TransferStatus.COMPLETED, receipt.status()),
                () -> assertEquals(
                        new BigDecimal("25.00"), receipt.amount()),
                () -> assertEquals(
                        new BigDecimal("75.00"), source.balance()),
                () -> assertEquals(
                        new BigDecimal("65.00"), destination.balance())
        );

        verify(accountRepository).save(source);
        verify(accountRepository).save(destination);
    }
}
~~~

Test này kiểm tra hành vi qua public method transfer(). Nó xác nhận số dư sau thao tác và receipt mà caller nhận được. Việc constructor injection của service hoạt động chỉ là cách test tạo object; bằng chứng chính là kết quả nghiệp vụ.

Trong test thực tế, cần bảo đảm Account có equality hoặc accessor tương ứng với cách assertion đang dùng. Ví dụ này dùng mock repository để cô lập logic service, vì vậy nó không chứng minh dữ liệu đã được lưu vào database.

### Kiểm tra đầu vào không hợp lệ

~~~java
@Test
void rejectsNonPositiveAmountWithoutChangingAccounts() {
    assertThrows(
            IllegalArgumentException.class,
            () -> transferService.transfer(
                    "A-1", "B-2", BigDecimal.ZERO)
    );

    verify(accountRepository, never()).save(any(Account.class));
}
~~~

Assertion này xác nhận service từ chối số tiền bằng 0 và không yêu cầu lưu tài khoản. Nếu hợp đồng cũng quy định không được tra cứu account khi amount không hợp lệ, có thể xác nhận repository không bị gọi; chỉ nên thêm điều kiện đó khi thứ tự kiểm tra là cam kết cần giữ.

### Kiểm tra tài khoản không tồn tại

~~~java
@Test
void rejectsTransferWhenSourceAccountDoesNotExist() {
    when(accountRepository.findById("missing"))
            .thenReturn(Optional.empty());

    assertThrows(
            AccountNotFoundException.class,
            () -> transferService.transfer(
                    "missing", "B-2", new BigDecimal("10.00"))
    );

    verify(accountRepository, never()).save(any(Account.class));
}
~~~

Test này xác nhận loại lỗi mà caller nhận được và việc service không tạo thao tác ghi nhận khi tài khoản nguồn không tồn tại.

### Kiểm tra chính sách từ chối giao dịch

~~~java
@Test
void doesNotSaveAccountsWhenTransferPolicyRejectsRequest() {
    Account source = new Account(
            "A-1", new BigDecimal("100.00"));
    Account destination = new Account(
            "B-2", new BigDecimal("40.00"));

    when(accountRepository.findById("A-1"))
            .thenReturn(Optional.of(source));
    when(accountRepository.findById("B-2"))
            .thenReturn(Optional.of(destination));

    doThrow(new TransferNotAllowedException())
            .when(transferPolicy)
            .checkAllowed(source, destination, new BigDecimal("25.00"));

    assertThrows(
            TransferNotAllowedException.class,
            () -> transferService.transfer(
                    "A-1", "B-2", new BigDecimal("25.00"))
    );

    verify(accountRepository, never()).save(any(Account.class));
}
~~~

Test xác nhận policy được dùng để quyết định giao dịch có được phép hay không và service không lưu account khi policy từ chối. Nó vẫn chưa xác nhận implementation thật của TransferPolicy áp dụng đúng mọi quy tắc. Policy đó cần unit test riêng hoặc được đưa vào một test tích hợp phù hợp.

## 6. Dùng context test riêng để kiểm tra DI/wiring

Sau khi đã có unit test cho nghiệp vụ, có thể viết một test nhỏ xác nhận Spring tạo và kết nối các bean như dự kiến.

Ví dụ cấu hình test dùng repository giả trong bộ nhớ và policy thật:

~~~java
@Configuration
class TransferTestConfiguration {

    @Bean
    AccountRepository accountRepository() {
        return new InMemoryAccountRepository();
    }

    @Bean
    TransferPolicy transferPolicy() {
        return new StandardTransferPolicy();
    }

    @Bean
    TransferService transferService(
            AccountRepository accountRepository,
            TransferPolicy transferPolicy) {
        return new TransferService(
                accountRepository, transferPolicy);
    }
}
~~~

Test sử dụng cấu hình đó:

~~~java
@SpringJUnitConfig(TransferTestConfiguration.class)
class TransferServiceWiringTest {

    @Autowired
    private TransferService transferService;

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void createsServiceWithConfiguredCollaborators() {
        assertNotNull(transferService);
        assertNotNull(accountRepository);
    }
}
~~~

Test này xác nhận context nhỏ có thể tạo service và repository. Nếu mục tiêu chỉ là wiring, đó là bằng chứng phù hợp.

Có thể mở rộng test để gọi transfer với dữ liệu được chuẩn bị trong InMemoryAccountRepository rồi kiểm tra kết quả. Khi làm vậy, test đồng thời kiểm tra service hoạt động với cấu hình và fake repository đã chọn. Nó vẫn không chứng minh implementation repository production hoặc database thật hoạt động.

### Không để mock thay thế chính bean đang cần kiểm chứng

Giả sử rủi ro là Spring chọn sai TransferPolicy do @Primary hoặc @Qualifier. Nếu test dùng @MockitoBean để thay TransferPolicy, nó đã loại bỏ implementation thật khỏi context. Test có thể xanh dù cấu hình production vẫn chọn sai policy.

Khi kiểm tra wiring hoặc lựa chọn bean:

- Giữ bean thật đang là đối tượng rủi ro.
- Nạp profile và property tương ứng với tình huống.
- Kiểm tra implementation được inject hoặc kích hoạt hành vi đặc trưng của implementation.
- Chỉ mock những dependency nằm ngoài phạm vi rủi ro.

Khi kiểm tra controller mapping và service không phải mục tiêu, mock service là hợp lý. Khi kiểm tra chính service được inject cùng policy thật, thay policy bằng mock sẽ làm mất bằng chứng cần có.

## 7. Phân biệt @InjectMocks với Spring Dependency Injection

Mockito và Spring đều có thể tạo object với dependency, nhưng chúng hoạt động theo hai cơ chế khác nhau.

### @InjectMocks của Mockito

~~~java
@ExtendWith(MockitoExtension.class)
class InvoiceServiceTest {

    @Mock
    private InvoiceRepository invoiceRepository;

    @InjectMocks
    private InvoiceService invoiceService;
}
~~~

Mockito cố gắng tạo InvoiceService và đưa các mock phù hợp vào constructor, setter hoặc field theo quy tắc của Mockito. Nó không khởi động ApplicationContext, không chạy component scan, không áp dụng Spring AOP proxy và không xác nhận cấu hình bean production.

Đây là cơ chế thuận tiện để unit test.

### @Autowired của Spring

~~~java
@SpringJUnitConfig(InvoiceTestConfiguration.class)
class InvoiceServiceContextTest {

    @Autowired
    private InvoiceService invoiceService;
}
~~~

Spring tạo ApplicationContext, đăng ký bean theo cấu hình, giải quyết dependency và quản lý vòng đời bean. Nếu cấu hình có transaction hoặc AOP, Spring có thể cung cấp proxy tương ứng.

Đây là cơ chế phù hợp để kiểm tra wiring và các hành vi phụ thuộc container.

### So sánh

| Đặc điểm | Mockito @InjectMocks | Spring @Autowired |
|---|---|---|
| Tạo object bằng cơ chế | Mockito | Spring container |
| Cần ApplicationContext | Không | Có |
| Component scan/configuration | Không | Có theo cấu hình |
| Áp dụng Spring AOP proxy | Không | Có nếu cấu hình yêu cầu |
| Kiểm tra bean selection/profile | Không | Có thể |
| Mục đích chính | Unit test logic | Context/wiring/integration test |

Không dùng kết quả unit test với @InjectMocks để kết luận Spring DI đã cấu hình đúng. Cũng không dùng việc @Autowired thành công để kết luận nghiệp vụ đúng.

## 8. Kiểm tra bean selection: @Primary, @Qualifier và profile

Một lỗi wiring có thể xảy ra dù context vẫn khởi động: Spring chọn một implementation hợp lệ về kiểu dữ liệu nhưng không đúng mục đích của môi trường hoặc nghiệp vụ.

Ví dụ có hai policy:

~~~java
@Component
@Primary
class StandardTransferPolicy implements TransferPolicy {
    // Quy tắc chuyển tiền thông thường.
}

@Component
class RestrictedTransferPolicy implements TransferPolicy {
    // Quy tắc cho tài khoản bị giới hạn.
}
~~~

Nếu service chỉ inject TransferPolicy, Spring dùng bean được đánh dấu @Primary. Context khởi động thành công, nhưng điều đó không chứng minh implementation được chọn phù hợp với yêu cầu của từng luồng.

Có thể dùng @Qualifier để chỉ rõ dependency:

~~~java
public TransferService(
        AccountRepository accountRepository,
        @Qualifier("standardTransferPolicy")
        TransferPolicy transferPolicy) {
    this.accountRepository = accountRepository;
    this.transferPolicy = transferPolicy;
}
~~~

Nếu implementation được chọn theo profile:

~~~java
@Configuration
@Profile("test")
class TestTransferConfiguration {

    @Bean
    TransferPolicy transferPolicy() {
        return new PermissiveTransferPolicy();
    }
}
~~~

Một context test nên kích hoạt profile cần kiểm tra và xác nhận bean đúng được tạo. Nhưng nếu policy có quy tắc nghiệp vụ, vẫn cần test hành vi của policy đó.

Có hai loại assertion khác nhau:

- **Bean selection assertion:** implementation nào được Spring inject?
- **Behavior assertion:** implementation đó xử lý tình huống nghiệp vụ như thế nào?

Cả hai có thể cần thiết nếu rủi ro bao gồm cấu hình và logic của policy.

## 9. Constructor injection giúp rõ ràng dependency, nhưng không chứng minh logic đúng

Constructor injection thường được khuyến nghị vì:

- Dependency bắt buộc được thể hiện ngay trong constructor.
- Có thể dùng final field.
- Object khó được tạo ở trạng thái thiếu dependency.
- Unit test có thể tạo object trực tiếp.
- Dependency graph dễ đọc và dễ kiểm tra.

Ví dụ:

~~~java
@Service
public class PaymentService {

    private final PaymentGateway paymentGateway;
    private final PaymentRepository paymentRepository;

    public PaymentService(
            PaymentGateway paymentGateway,
            PaymentRepository paymentRepository) {
        this.paymentGateway = paymentGateway;
        this.paymentRepository = paymentRepository;
    }
}
~~~

Tuy nhiên, constructor injection chỉ bảo đảm object nhận các reference cần thiết khi được tạo. Nó không bảo đảm:

- Gateway trừ tiền đúng số tiền.
- Service gửi đúng currency.
- Service xử lý timeout đúng.
- Repository lưu đúng trạng thái.
- Service không gọi gateway khi request không hợp lệ.

Những điều này cần test hành vi qua public method.

### Field injection cũng không làm test nghiệp vụ tự động đúng

~~~java
@Service
public class PaymentService {

    @Autowired
    private PaymentGateway paymentGateway;
}
~~~

Field injection khiến unit test thuần khó tạo object hơn vì dependency không được truyền qua constructor. Nhưng ngay cả khi Spring inject thành công field, logic payment vẫn cần được kiểm tra bằng test có đầu vào và kết quả rõ ràng.

Chất lượng kiểm thử đến từ bằng chứng mà test thu thập, không đến từ annotation DI được dùng trong class.

## 10. Khi nào cần kiểm tra @Transactional và proxy?

Một service có thể được đánh dấu:

~~~java
@Service
public class TransferService {

    @Transactional
    public TransferReceipt transfer(...) {
        // Cập nhật nhiều bản ghi.
    }
}
~~~

Khi Spring quản lý bean và transaction infrastructure được cấu hình, lời gọi qua proxy có thể mở transaction. Nếu test tạo object trực tiếp:

~~~java
TransferService service =
        new TransferService(accountRepository, transferPolicy);
~~~

thì annotation @Transactional không tự được thực thi. Unit test vẫn có thể kiểm tra logic tính toán và các lời gọi collaborator, nhưng không thể chứng minh transaction rollback.

Để kiểm tra transaction:

- Nạp Spring context có transaction manager.
- Dùng repository và database test phù hợp.
- Gọi service bean được inject từ context, qua proxy.
- Tạo tình huống một bước ghi thành công rồi bước sau thất bại.
- Quan sát dữ liệu sau transaction để xác nhận rollback hoặc commit theo hợp đồng.

Ví dụ khung test:

~~~java
@SpringBootTest
class TransferTransactionTest {

    @Autowired
    private TransferService transferService;

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void rollsBackBalanceChangesWhenTransferRecordCannotBeSaved() {
        // Chuẩn bị tài khoản trong database test.
        // Kích hoạt tình huống lỗi ở bước ghi transfer record.
        // Gọi transferService qua bean được Spring inject.
        // Đọc lại tài khoản sau transaction và xác nhận số dư cũ.
    }
}
~~~

Đây là một mục tiêu khác với việc xác nhận TransferService bean tồn tại. Chỉ nạp context không kích hoạt transaction. Gọi method qua proxy và kiểm tra trạng thái database mới tạo bằng chứng cho hành vi transaction.

Lưu ý rằng test method tự mang @Transactional có thể khiến transaction của test bao quanh lời gọi service. Cần hiểu propagation, commit/rollback và transaction boundary của bài test để không vô tình che khuất hành vi đang muốn kiểm chứng. Với test cần xác nhận dữ liệu sau khi service commit hoặc rollback, có thể cần điều khiển transaction của test và đọc dữ liệu ở transaction khác hoặc sau khi kết thúc transaction phù hợp.

## 11. Kiểm tra cấu hình Spring và nghiệp vụ bằng hai test riêng

Giả sử PaymentService phụ thuộc vào PaymentGateway được chọn theo property payment.provider.

Có thể tách hai mục tiêu:

### Test cấu hình chọn gateway

~~~java
@SpringBootTest(properties = "payment.provider=stub")
class PaymentGatewayConfigurationTest {

    @Autowired
    private PaymentGateway paymentGateway;

    @Test
    void selectsStubGatewayForTestProvider() {
        assertInstanceOf(
                StubPaymentGateway.class,
                paymentGateway);
    }
}
~~~

Test này xác nhận cấu hình chọn implementation StubPaymentGateway trong điều kiện property cụ thể.

### Test nghiệp vụ của PaymentService

~~~java
@ExtendWith(MockitoExtension.class)
class PaymentServiceTest {

    @Mock
    private PaymentGateway paymentGateway;

    @Mock
    private PaymentRepository paymentRepository;

    @InjectMocks
    private PaymentService paymentService;

    @Test
    void recordsSuccessfulPayment() {
        when(paymentGateway.charge(any(PaymentRequest.class)))
                .thenReturn(new GatewayResult(true, "txn-42"));

        PaymentResult result = paymentService.pay(
                new PaymentRequest("order-7", new BigDecimal("50.00")));

        assertEquals(PaymentStatus.PAID, result.status());
        assertEquals("txn-42", result.transactionId());
    }
}
~~~

Test thứ nhất kiểm tra lựa chọn bean. Test thứ hai kiểm tra cách service phản ứng với kết quả gateway. Nếu cần xác nhận gateway thật giao tiếp đúng với provider, viết test adapter/integration riêng.

Tách như vậy giúp mỗi test có một kết luận rõ ràng và tránh một test context lớn chứa quá nhiều mock làm mờ đối tượng đang kiểm tra.

## 12. Kiểm tra bean tồn tại không giống kiểm tra bean được dùng đúng

Một test có thể xác nhận service và repository đều tồn tại:

~~~java
assertNotNull(transferService);
assertNotNull(accountRepository);
~~~

Nhưng nếu TransferService vô tình dùng một repository khác hoặc policy không phù hợp, hai assertion này vẫn có thể xanh.

Khi wiring cụ thể là rủi ro, hãy kiểm tra kết quả lựa chọn dependency theo một trong các cách:

- Nạp context chỉ với các bean được định danh rõ ràng và xác nhận implementation được inject.
- Dùng qualifier và kiểm tra bean có tên/loại mong đợi.
- Gọi hành vi phân biệt của implementation thật.
- Kiểm tra cấu hình profile/property chọn đúng bean.
- Kiểm tra proxy nếu hành vi phụ thuộc AOP.

Không cần truy cập private field của service bằng reflection chỉ để xác nhận mọi dependency. Ưu tiên kiểm tra bean graph qua cấu hình và hành vi quan sát được. Nếu dependency selection không thể quan sát qua public behavior và thực sự là một cam kết cấu hình, có thể xác nhận implementation bean được Spring quản lý bằng cách inject trực tiếp bean đó trong context test.

## 13. Đừng để mock che khuất lỗi DI

Mock là công cụ cô lập, nhưng cũng có thể loại bỏ chính dependency cần kiểm tra.

Ví dụ:

~~~java
@SpringBootTest
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @MockitoBean
    private OrderRepository orderRepository;
}
~~~

Trong test này, Spring vẫn tạo OrderService nhưng repository được thay bằng mock. Điều đó hữu ích nếu mục tiêu là kiểm tra service trong context với repository được kiểm soát. Tuy nhiên, test không xác nhận OrderRepository production được cấu hình, kết nối database hoặc thực thi truy vấn đúng.

Hãy tự hỏi:

- Bean bị mock có nằm trong phạm vi rủi ro không?
- Nếu bean đó sai cấu hình, test có phát hiện được không?
- Mock đang thay một dependency ngoài mục tiêu hay thay chính thành phần cần kiểm chứng?
- Có test khác bao phủ adapter thật hoặc bean selection không?

Một test slice thường mock service vì logic service không thuộc mục tiêu controller. Một repository test không nên mock repository nếu mục tiêu là query. Một wiring test không nên thay bean đang cần xác nhận bằng mock.

## 14. Chọn phạm vi kiểm thử theo câu hỏi cần trả lời

| Mục tiêu | Test phù hợp | Nên quan sát |
|---|---|---|
| Kiểm tra service tính toán đúng | Unit test tạo service trực tiếp | Giá trị trả về, exception |
| Kiểm tra service từ chối đầu vào sai | Unit test với JUnit | Exception và tác động bị ngăn |
| Kiểm tra mock dependency nhận đúng yêu cầu | Unit test với Mockito | ArgumentCaptor hoặc verify có ý nghĩa |
| Kiểm tra Spring tạo bean và inject dependency | @SpringJUnitConfig hoặc context test nhỏ | Bean được tạo và cấu hình phù hợp |
| Kiểm tra lựa chọn bean theo profile/property | Spring context test | Implementation thực tế được chọn |
| Kiểm tra MVC mapping | @WebMvcTest | HTTP status, header, body, model |
| Kiểm tra JPA mapping/query | @DataJpaTest | Dữ liệu trong database test |
| Kiểm tra transaction proxy | Spring integration test | Commit/rollback qua transaction manager |
| Kiểm tra toàn bộ luồng ứng dụng | @SpringBootTest | Kết quả qua nhiều bean và hạ tầng thật |

Nếu mục tiêu là logic nghiệp vụ, unit test thường cung cấp bằng chứng trực tiếp và nhanh nhất. Nếu mục tiêu là wiring, cần context. Nếu mục tiêu là tương tác giữa wiring và hạ tầng, cần integration test.

## 15. Một ví dụ hoàn chỉnh về ba lớp test

Giả sử hệ thống có DiscountService sử dụng DiscountPolicy và OrderRepository.

### Business rule

Hợp đồng:

> Khách hàng VIP được giảm 10% trên giá trị đơn hàng đủ điều kiện. Tổng tiền sau giảm không được âm. Đơn hàng được lưu với tổng tiền cuối cùng.

Unit test kiểm tra kết quả:

~~~java
@ExtendWith(MockitoExtension.class)
class DiscountServiceUnitTest {

    @Mock
    private DiscountPolicy discountPolicy;

    @Mock
    private OrderRepository orderRepository;

    @InjectMocks
    private DiscountService discountService;

    @Test
    void appliesVipDiscountAndReturnsFinalTotal() {
        when(discountPolicy.rateFor("VIP"))
                .thenReturn(new BigDecimal("0.10"));

        when(orderRepository.save(any(Order.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        OrderResult result = discountService.checkout(
                new OrderRequest("VIP", new BigDecimal("100.00")));

        assertEquals(
                new BigDecimal("90.00"), result.finalTotal());
    }
}
~~~

Test này xác nhận service áp dụng kết quả policy và trả về tổng tiền đúng với dependency behavior đã cấu hình. Nếu muốn xác nhận DiscountPolicy thật tính đúng 10%, cần test policy riêng.

### DI/configuration

Context test xác nhận policy được chọn đúng:

~~~java
@SpringBootTest(properties = "discount.policy=standard")
class DiscountPolicyWiringTest {

    @Autowired
    private DiscountPolicy discountPolicy;

    @Test
    void wiresStandardDiscountPolicy() {
        assertInstanceOf(StandardDiscountPolicy.class, discountPolicy);
    }
}
~~~

Test này không kiểm tra mức giảm giá. Nó chỉ kiểm tra bean implementation được chọn.

### Integration behavior

Một integration test có thể nạp service, policy và repository thật, chuẩn bị order trong database test, gọi checkout và truy vấn lại tổng tiền được lưu. Test này tạo bằng chứng rằng các bean phối hợp và persistence hoạt động như yêu cầu.

Ba test không trùng vai trò. Mỗi test xử lý một rủi ro khác nhau.

## 16. Các dấu hiệu cho thấy test đang nhầm DI với nghiệp vụ

Hãy xem lại thiết kế nếu test chỉ có các assertion sau:

- assertNotNull(service).
- assertNotNull(repository).
- assertTrue(applicationContext.containsBean("someService")).
- assertDoesNotThrow(() -> context.getBean(Service.class)).
- contextLoads() không có hành động nghiệp vụ nào.

Các assertion này hữu ích trong kiểm tra cấu hình, nhưng không thể thay thế test có đầu vào, hành động và kết quả.

Một test hành vi nên có ít nhất:

1. Trạng thái hoặc dữ liệu ban đầu.
2. Lời gọi public method hoặc request thực tế.
3. Assertion về kết quả mà caller hoặc hệ thống có thể quan sát.
4. Assertion về tác động bị ngăn chặn nếu đó là một phần của hợp đồng.

Không phải mọi test đều cần kiểm tra database hoặc nhiều mock. Hãy chọn bằng chứng tương ứng với rủi ro.

## 17. Quy trình thực hành khi viết test cho bean có DI

1. **Xác định rủi ro:** đang kiểm tra wiring, logic nghiệp vụ hay tích hợp?
2. **Xác định bean trong phạm vi:** service, repository, policy, controller hoặc adapter nào cần tham gia?
3. **Giữ đúng thành phần đang kiểm chứng:** không mock bean mà test cần xác nhận.
4. **Cô lập phần ngoài mục tiêu:** dùng mock hoặc fake cho dependency không thuộc rủi ro.
5. **Chọn phạm vi:** unit test nếu chỉ cần logic; context test nếu cần DI; integration test nếu cần proxy, database hoặc hạ tầng thật.
6. **Kích hoạt hành vi:** gọi public method hoặc gửi request qua ranh giới phù hợp.
7. **Xác nhận kết quả:** kiểm tra giá trị trả về, exception, trạng thái dữ liệu hoặc tác động.
8. **Đánh giá kết luận:** test đã chứng minh điều gì và còn điều gì nằm ngoài phạm vi?

### Mẫu mô tả mục tiêu test

~~~text
Rủi ro:
[Điều có thể sai và hậu quả]

Thành phần cần kiểm chứng:
[Bean hoặc quy tắc nghiệp vụ]

Dependency cần có thật:
[Bean, proxy, repository hoặc adapter thuộc phạm vi]

Dependency có thể thay:
[Mock/fake nằm ngoài phạm vi]

Hành động:
[Public method hoặc request]

Bằng chứng:
[Return value, exception, state, HTTP response, database state]
~~~

Ví dụ:

~~~text
Rủi ro:
Spring chọn nhầm TransferPolicy cho profile test.

Thành phần cần kiểm chứng:
TransferPolicy bean được inject.

Dependency cần có thật:
StandardTransferPolicy và cấu hình profile.

Dependency có thể thay:
Các dịch vụ ngoài không liên quan đến policy.

Hành động:
Khởi động context với profile test và gọi policy qua public API.

Bằng chứng:
Bean được chọn là implementation dự kiến và một tình huống nghiệp vụ mẫu
cho kết quả theo quy tắc đã công bố.
~~~

Mẫu này buộc người viết test phân biệt rõ bằng chứng về lựa chọn bean và bằng chứng về hành vi của bean.

## Kết luận

Dependency Injection chứng minh Spring có thể cung cấp và kết nối các dependency theo cấu hình hiện tại. Nó không chứng minh service áp dụng đúng quy tắc nghiệp vụ, repository lưu đúng dữ liệu hay transaction xử lý đúng khi có lỗi. Hãy dùng context test để xác nhận wiring, unit test để xác nhận hành vi qua public API và integration test để xác nhận proxy cùng hạ tầng thật. Một bộ test đáng tin cậy cần bằng chứng cho từng rủi ro, thay vì dựa vào việc ApplicationContext khởi động thành công.
