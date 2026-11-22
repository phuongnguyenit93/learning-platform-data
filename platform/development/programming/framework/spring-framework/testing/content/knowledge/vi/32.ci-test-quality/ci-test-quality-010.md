# Rà soát chi phí bảo trì khi tái cấu trúc mã ứng dụng

Tái cấu trúc mã ứng dụng (refactoring) là thay đổi cấu trúc bên trong để mã dễ hiểu, dễ kiểm thử và dễ thay đổi hơn, trong khi hành vi quan sát được của hệ thống vẫn được giữ nguyên. Một lần refactor có thể giảm chi phí cho những thay đổi sau này, nhưng cũng có thể tạo thêm abstraction, tăng số thành phần phải hiểu, làm phức tạp cấu hình Spring hoặc mở ra rủi ro hồi quy.

Vì vậy, khi review một đề xuất refactor, câu hỏi không chỉ là “mã mới có đẹp hơn không?”. Cần đánh giá tổng chi phí mà nhóm sẽ trả trong suốt vòng đời: chi phí thực hiện refactor, chi phí đọc và sửa mã trong các lần tiếp theo, chi phí kiểm thử, chi phí vận hành, chi phí nâng cấp dependency và chi phí xử lý lỗi nếu thay đổi làm hỏng hành vi đang chạy.

Trong ứng dụng Spring, đánh giá này còn phải xét đến dependency injection, bean lifecycle, transaction boundary, proxy/AOP, cấu hình môi trường, event và xử lý bất đồng bộ. Một thay đổi nhìn có vẻ thuần cấu trúc có thể làm thay đổi thời điểm khởi tạo bean, phạm vi transaction hoặc cách Spring áp dụng annotation. Bài review tốt cần nhìn cả mã nguồn lẫn cách ứng dụng thực sự được khởi động và kiểm thử.

## 1. Phân biệt refactoring với thay đổi hành vi

Refactoring có mục tiêu thay đổi cấu trúc mà không thay đổi hành vi bên ngoài. Ví dụ:

- Tách một phương thức dài thành các phương thức nhỏ có tên thể hiện ý định.
- Chuyển logic nghiệp vụ ra khỏi controller.
- Gom các quy tắc lặp lại vào một thành phần có trách nhiệm rõ ràng.
- Thay field injection bằng constructor injection.
- Tách adapter gọi hệ thống ngoài khỏi domain/application service.
- Giảm phụ thuộc vòng giữa các module.
- Làm rõ transaction boundary hoặc xử lý lỗi đang bị phân tán.

Nếu một thay đổi đồng thời sửa quy tắc tính giá, đổi status HTTP hoặc thay chính sách retry, đó không còn là refactor thuần túy. Có thể kết hợp refactor với thay đổi hành vi trong cùng một dự án, nhưng cần tách mục tiêu và bằng chứng kiểm thử để reviewer biết phần nào là thay đổi cấu trúc và phần nào là thay đổi sản phẩm.

Một cách hữu ích là mô tả hợp đồng trước khi sửa:

| Quan sát | Câu hỏi cần giữ nguyên trong refactor |
|---|---|
| API/HTTP | URL, method, status, header và response body có thay đổi không? |
| Nghiệp vụ | Kết quả tính toán, quy tắc validation và thứ tự xử lý có giữ nguyên không? |
| Persistence | Bản ghi nào được tạo/sửa/xóa? Transaction commit ở thời điểm nào? |
| Tích hợp | Request gửi ra ngoài, event phát đi và message được tiêu thụ có thay đổi không? |
| Lỗi | Exception, retry, fallback và cách chuyển lỗi có giữ nguyên không? |
| Bảo mật | Authentication, authorization, CSRF và dữ liệu nhạy cảm có thay đổi không? |
| Vận hành | Log, metric, trace, timeout và tài nguyên được giải phóng có giữ nguyên không? |

Hành vi quan sát được là cơ sở để đánh giá refactor an toàn. Nếu không biết hệ thống đang cam kết điều gì, nhóm khó xác định thay đổi nào là cải thiện cấu trúc và thay đổi nào vô tình làm hỏng hợp đồng.

## 2. Chi phí bảo trì gồm những gì?

Chi phí bảo trì không chỉ là số dòng code phải sửa. Một thay đổi nhỏ có thể tốn nhiều ngày nếu người thực hiện phải lần theo dependency qua nhiều module, dựng môi trường phức tạp, chờ CI lâu hoặc xác minh thủ công một luồng tích hợp khó kiểm thử.

Có thể chia chi phí thành các nhóm sau:

| Nhóm chi phí | Dấu hiệu thường gặp | Câu hỏi khi review refactor |
|---|---|---|
| Hiểu mã | Phương thức quá dài, tên mơ hồ, nhiều nhánh lồng nhau | Mã mới có làm ý định nghiệp vụ dễ đọc hơn không? |
| Thực hiện thay đổi | Một yêu cầu nhỏ phải sửa nhiều lớp/module | Refactor có giảm số nơi cần sửa cho cùng một loại thay đổi không? |
| Kiểm thử | Test khó dựng, phải khởi động nhiều dịch vụ, assertion dễ vỡ | Thay đổi có làm hành vi quan trọng dễ kiểm tra hơn không? |
| Hồi quy | Một sửa đổi làm hỏng chức năng không liên quan | Dependency và phạm vi ảnh hưởng có được thu hẹp không? |
| Vận hành | Cấu hình khó tìm, log thiếu ngữ cảnh, lỗi khó truy vết | Mã mới có làm việc chẩn đoán và rollback dễ hơn không? |
| Nâng cấp | Framework hoặc thư viện mới làm nhiều module phải sửa | Abstraction có cô lập thay đổi dependency hay tạo thêm lớp phải nâng cấp? |
| Onboarding | Người mới cần nhiều kiến thức ngầm để sửa một tính năng | Cấu trúc mới có làm ranh giới và luồng dữ liệu rõ hơn không? |
| Chuyển đổi | Phải di chuyển dữ liệu, cấu hình hoặc client đang chạy | Có kế hoạch tương thích, rollout và rollback không? |

Một refactor có thể tăng chi phí ngắn hạn nhưng giảm chi phí lặp lại trong tương lai. Ngược lại, tạo một framework nội bộ quá tổng quát có thể làm tăng chi phí đọc, debug và thay đổi dù mã có vẻ “tái sử dụng” nhiều hơn.

## 3. Xác định điểm nóng trước khi đề xuất refactor

Không nên chọn phần mã để refactor chỉ vì nó dài hoặc không tuân theo một phong cách cá nhân. Hãy tìm nơi thay đổi thường xuyên, gây lỗi hoặc tốn nhiều công sức nhất.

Các nguồn thông tin có thể dùng:

- Lịch sử Git: file hoặc module nào thường xuyên thay đổi cùng nhau?
- Pull request: loại thay đổi nào cần sửa nhiều lớp hoặc nhiều package?
- Bug và incident: lỗi nào lặp lại vì cùng một vùng logic?
- CI: test nào thường xuyên flaky, chậm hoặc cần chạy lại?
- Review: reviewer thường phải hỏi lại điều gì vì luồng xử lý không rõ?
- Vận hành: thành phần nào thường gây lỗi cấu hình, timeout hoặc khó quan sát?
- Phản hồi của nhóm: phần nào người phát triển thường tránh sửa vì sợ ảnh hưởng dây chuyền?

Một file có nhiều dòng chưa chắc là hotspot. Một lớp dài nhưng ổn định, có một trách nhiệm rõ và ít thay đổi có thể không cần refactor ngay. Ngược lại, một cấu hình Spring ngắn nhưng bị nhiều module phụ thuộc và thường xuyên gây lỗi môi trường có thể là điểm nóng quan trọng.

### Dùng change coupling để tìm ranh giới chưa rõ

Nếu hai nhóm file thường xuyên thay đổi cùng nhau trong nhiều pull request, có thể chúng thuộc cùng một trách nhiệm nhưng đang bị tách rời. Ngược lại, nếu một lớp thay đổi vì nhiều lý do không liên quan, nó có thể đang gom quá nhiều trách nhiệm.

Ví dụ, mỗi lần thêm một loại phương thức thanh toán, nhóm phải sửa `CheckoutController`, `OrderService`, `EmailService`, `ReportService` và một lớp tiện ích chung. Điều đó có thể cho thấy logic thanh toán chưa có ranh giới riêng. Tuy nhiên, change coupling chỉ là tín hiệu để điều tra; không phải bằng chứng tự động rằng cần tạo một interface hoặc module mới.

## 4. Đo chi phí hiện tại bằng tình huống thay đổi thực tế

Thay vì chỉ tranh luận về độ sạch của mã, hãy chọn một số thay đổi có khả năng xảy ra và ước lượng công sức hiện tại.

Ví dụ với hệ thống đặt hàng:

1. Thêm một phương thức thanh toán mới.
2. Thay nhà cung cấp email.
3. Thêm quy tắc miễn phí vận chuyển theo khu vực.
4. Thay cấu trúc response của dịch vụ tồn kho.
5. Thay đổi cách ghi audit log.

Với mỗi tình huống, ghi nhận:

- Bao nhiêu module và lớp phải thay đổi?
- Có cần hiểu các luồng không liên quan không?
- Có thể viết test ở mức unit hay phải khởi động cả ứng dụng?
- Test chạy trong bao lâu và có phụ thuộc dịch vụ ngoài không?
- Có phải kiểm tra thủ công trên môi trường tích hợp không?
- Khi lỗi xảy ra, có dễ xác định nguyên nhân và rollback không?

Một bảng baseline có thể như sau:

| Thay đổi dự kiến | Số vùng mã cần sửa | Kiểu test cần chạy | Khó khăn chính |
|---|---:|---|---|
| Thêm payment provider | 6 | Unit + integration | Điều kiện thanh toán phân tán trong service và controller. |
| Thay email provider | 4 | Unit + contract | SMTP client được tạo trực tiếp trong business logic. |
| Thêm shipping rule | 5 | Unit | Nhiều nhánh điều kiện lồng nhau, thiếu test biên. |

Các con số trong bảng là ví dụ minh họa. Khi áp dụng, dùng dữ liệu từ codebase và các thay đổi thực tế của nhóm. Baseline giúp so sánh trước/sau và tránh đánh giá refactor chỉ dựa vào cảm giác.

## 5. Đánh giá cấu trúc mã: cohesion, coupling và ranh giới

Hai câu hỏi cốt lõi khi review cấu trúc là:

- **Cohesion:** Các phần trong cùng một lớp/module có phục vụ một mục đích liên quan không?
- **Coupling:** Một thay đổi ở lớp/module này buộc bao nhiêu thành phần khác phải biết hoặc thay đổi theo?

Một service có cohesion tốt thường có một lý do thay đổi tương đối rõ. Nó có thể phối hợp nhiều collaborator, nhưng không nên tự chịu trách nhiệm cho mọi chi tiết của persistence, HTTP, email, format file và quy tắc nghiệp vụ không liên quan.

Coupling thấp không có nghĩa là tạo interface cho mọi class. Abstraction có ích khi nó thể hiện một ranh giới có khả năng thay đổi độc lập, ví dụ cổng thanh toán, kho lưu trữ hoặc hệ thống thông báo. Nếu interface chỉ lặp lại đúng một implementation và không tạo seam kiểm thử hay ranh giới kiến trúc, nó có thể làm tăng số file và số khái niệm phải hiểu.

### Ví dụ: service có quá nhiều trách nhiệm

Trước refactor, một service có thể vừa tính tổng đơn hàng, lưu dữ liệu, gọi dịch vụ thanh toán và gửi email:

```java
@Service
class CheckoutService {

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private RestTemplate restTemplate;

    @Autowired
    private JavaMailSender mailSender;

    public Order checkout(CheckoutRequest request) {
        BigDecimal total = request.items().stream()
                .map(item -> item.price().multiply(BigDecimal.valueOf(item.quantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        if (total.signum() <= 0) {
            throw new IllegalArgumentException("Order total must be positive");
        }

        Order order = orderRepository.save(new Order(request.customerId(), total));

        PaymentResponse payment = restTemplate.postForObject(
                "https://payments.example.test/charge",
                new PaymentRequest(order.getId(), total),
                PaymentResponse.class);

        SimpleMailMessage message = new SimpleMailMessage();
        message.setTo(request.email());
        message.setSubject("Order created");
        message.setText("Order " + order.getId() + " created");
        mailSender.send(message);

        return order;
    }
}
```

Lớp này có nhiều lý do thay đổi: quy tắc tính tiền, persistence, giao thức payment và nội dung email. Test unit cũng khó vì dependency được field-inject và logic gọi hệ thống ngoài trực tiếp.

### Sau refactor: tách ranh giới có ý nghĩa

Có thể đưa quy tắc tính tiền và tích hợp thanh toán/thông báo vào các collaborator riêng:

```java
public interface PaymentGateway {
    PaymentResult charge(long orderId, BigDecimal amount);
}

public interface OrderNotifier {
    void orderCreated(Order order, String recipient);
}
```

Service điều phối nghiệp vụ bằng constructor injection:

```java
@Service
class CheckoutService {

    private final OrderRepository orderRepository;
    private final PricingPolicy pricingPolicy;
    private final PaymentGateway paymentGateway;
    private final OrderNotifier orderNotifier;

    CheckoutService(
            OrderRepository orderRepository,
            PricingPolicy pricingPolicy,
            PaymentGateway paymentGateway,
            OrderNotifier orderNotifier) {
        this.orderRepository = orderRepository;
        this.pricingPolicy = pricingPolicy;
        this.paymentGateway = paymentGateway;
        this.orderNotifier = orderNotifier;
    }

    @Transactional
    public Order checkout(CheckoutRequest request) {
        BigDecimal total = pricingPolicy.calculate(request.items());
        Order order = orderRepository.save(
                new Order(request.customerId(), total));

        PaymentResult payment = paymentGateway.charge(order.getId(), total);
        if (!payment.approved()) {
            throw new PaymentRejectedException(order.getId());
        }

        orderNotifier.orderCreated(order, request.email());
        return order;
    }
}
```

Ví dụ này minh họa các ranh giới, không phải một thiết kế bắt buộc cho mọi ứng dụng. Việc đặt `@Transactional` trên toàn bộ phương thức chỉ phù hợp nếu payment và notification có thể được gọi trong transaction đó và semantics lỗi đã được xác định. Nếu payment là hệ thống ngoài, giữ transaction database mở trong khi chờ HTTP có thể làm tăng thời gian giữ connection/lock. Một thiết kế production có thể cần transaction ngắn hơn, outbox hoặc quy trình saga. Reviewer phải xác nhận transaction boundary trước khi chấp nhận refactor.

Refactor có lợi khi các collaborator phản ánh những lý do thay đổi độc lập và có thể kiểm thử riêng. Nó không có lợi nếu chỉ chuyển code sang nhiều class nhỏ nhưng mọi class vẫn phụ thuộc trực tiếp vào cùng một implementation cụ thể và thay đổi vẫn lan rộng như trước.

## 6. Đánh giá testability và chi phí hồi quy

Testability là một phần lớn của chi phí bảo trì. Mã khó kiểm thử thường khiến nhóm phải dựa vào test tích hợp nặng hoặc kiểm tra thủ công. Khi refactor, hãy xem xét liệu thay đổi có tạo ra seam kiểm thử tốt hơn mà không làm test phụ thuộc vào chi tiết nội bộ.

Các tín hiệu tích cực:

- Dependency được truyền qua constructor và có thể thay thế trong unit test.
- Quy tắc nghiệp vụ thuần được tách khỏi HTTP, database và framework.
- Các adapter có contract rõ ràng.
- Transaction và event boundary có thể kiểm tra bằng integration test.
- Test xác nhận kết quả và side effect quan trọng, không phụ thuộc thứ tự gọi nội bộ không phải hợp đồng.

Các tín hiệu tiêu cực:

- Test phải mock quá nhiều collaborator để dựng một trường hợp đơn giản.
- Mỗi thay đổi implementation làm nhiều test thất bại dù hành vi không đổi.
- Test chỉ xác nhận mock được gọi mà không kiểm tra kết quả nghiệp vụ.
- Tách lớp làm phát sinh nhiều context hoặc nhiều server test không cần thiết.
- Unit test pass nhưng không có integration test cho transaction, mapping hoặc cấu hình Spring đã thay đổi.

### Dùng characterization test trước khi refactor

Khi mã cũ khó hiểu hoặc thiếu test, hãy ghi lại hành vi hiện tại bằng characterization test. Test này mô tả input, output và side effect đang tồn tại, kể cả những hành vi không lý tưởng nhưng đã trở thành hợp đồng thực tế.

Ví dụ:

```java
@Test
void checkoutStoresOrderAndChargesTheCalculatedAmount() {
    CheckoutRequest request = requestWithItem("BOOK-42", 2, new BigDecimal("10.00"));

    Order order = checkoutService.checkout(request);

    assertThat(order.getTotal()).isEqualByComparingTo("20.00");
    verify(orderRepository).save(argThat(saved ->
            saved.getTotal().compareTo(new BigDecimal("20.00")) == 0));
    verify(paymentGateway).charge(order.getId(), new BigDecimal("20.00"));
}
```

Sau refactor, giữ cùng test hoặc chuyển nó sang test phù hợp với ranh giới mới. Nếu kết quả thay đổi có chủ ý, đó là thay đổi hành vi và cần được ghi rõ, không được che dưới nhãn refactor.

### Phân bổ test theo ranh giới

| Loại test | Điều nên xác nhận |
|---|---|
| Unit test | Quy tắc tính toán, validation và quyết định nghiệp vụ. |
| Spring slice test | Wiring MVC, serialization, validation hoặc repository theo slice cần thiết. |
| Integration test | Transaction, persistence, event dispatch, adapter và cấu hình thực. |
| Contract test | Request/response giữa ứng dụng và dịch vụ ngoài. |
| End-to-end/smoke test | Một luồng quan trọng qua các thành phần triển khai. |

Không cần biến mọi unit test thành `@SpringBootTest`. Test nhỏ và có mục tiêu rõ giúp phản hồi nhanh hơn; integration test chỉ nên bao phủ những hành vi phụ thuộc vào framework hoặc hạ tầng thật.

## 7. Những rủi ro đặc thù trong ứng dụng Spring

Refactor trong Spring có thể làm thay đổi hành vi dù code nghiệp vụ nhìn gần như giống nhau. Reviewer cần xem xét những cơ chế framework đứng sau annotation và bean.

### Dependency injection và bean lifecycle

Chuyển field injection sang constructor injection thường làm dependency rõ ràng hơn và giúp tạo unit test dễ hơn. Tuy nhiên, cần kiểm tra:

- Bean có còn được component scan hoặc import đúng không?
- Có nhiều implementation cho một interface khiến injection trở nên mơ hồ không?
- `@Qualifier`, `@Primary` hoặc profile có bị bỏ sót không?
- Bean có scope đặc biệt như request/session không?
- Có circular dependency bị che bởi field injection hoặc lazy proxy không?

Tạo thêm abstraction không tự động giảm coupling. Nếu Spring phải dùng nhiều `@Qualifier` hoặc cấu hình điều kiện phức tạp để chọn implementation, chi phí hiểu cấu hình có thể tăng.

### Transaction boundary và proxy

`@Transactional` thường được áp dụng qua proxy. Di chuyển phương thức sang một bean khác, đổi visibility, thay cách gọi hoặc tạo self-invocation có thể làm transaction không còn được áp dụng như dự kiến.

Ví dụ, một phương thức gọi một phương thức `@Transactional` khác trong cùng instance thường không đi qua Spring proxy. Refactor method thành một bean riêng có thể thay đổi việc proxy được gọi và do đó thay đổi transaction behavior. Cần xác nhận propagation, isolation, rollback rule và thời điểm commit.

Không chỉ kiểm tra annotation có còn trên code. Hãy kiểm tra transaction thực sự được mở, rollback khi lỗi và commit đúng thời điểm bằng integration test với transaction manager thật.

### AOP, security và method interception

Các annotation như `@PreAuthorize`, `@Cacheable`, `@Retryable`, `@Async` hoặc custom aspect có thể dựa vào proxy/interceptor. Chuyển phương thức giữa class, đổi kiểu bean hoặc gọi nội bộ có thể làm advice không chạy.

Review refactor cần kiểm tra:

- Bean có còn được Spring quản lý không?
- Lời gọi có đi qua proxy không?
- Method có đáp ứng điều kiện interception của framework không?
- Thứ tự các advice có thay đổi không?
- Test có xác nhận hành vi bảo mật/cache/retry/async thay vì chỉ kiểm tra code compile không?

### Event và transaction event

Chuyển một lời gọi trực tiếp thành event có thể giảm coupling nhưng cũng thay đổi timing và semantics. `@EventListener` mặc định có thể xử lý đồng bộ trong quá trình publish; `@Async` hoặc `@TransactionalEventListener` làm thay đổi thời điểm và thread xử lý. Nếu listener chỉ chạy sau commit, test cần xác nhận event được phát trong transaction và listener chạy ở phase mong đợi.

Không nên dùng event chỉ để tránh truyền một dependency qua constructor. Event hữu ích khi producer không cần biết consumer và có ranh giới nghiệp vụ rõ. Nếu chỉ có một consumer đồng bộ và lời gọi trực tiếp dễ hiểu hơn, event có thể làm luồng xử lý khó truy vết.

### Cấu hình và auto-configuration

Refactor package, class configuration hoặc property prefix có thể làm component scan và auto-configuration thay đổi. Cần kiểm tra active profile, conditional bean, `@ConfigurationProperties`, property precedence và default value ở các môi trường.

Một unit test tạo thủ công service không thể chứng minh application context production vẫn khởi động đúng. Khi refactor cấu hình, cần có context test hoặc smoke test khởi động application với các profile/property quan trọng.

### Request scope và thread context

Di chuyển xử lý sang executor hoặc reactive pipeline có thể làm mất request context, security context hoặc MDC nếu code đang dựa vào thread-local. Refactor cần xác định dữ liệu nào phải truyền tường minh, cơ chế context propagation nào được dùng và nơi cleanup diễn ra.

Đừng để một service nghiệp vụ đọc `RequestContextHolder` hoặc `SecurityContextHolder` ở nhiều nơi nếu có thể truyền tenant/user identity rõ ràng qua application boundary. Cách truyền tường minh làm dependency dễ kiểm thử và tránh phụ thuộc ngầm vào thread.

## 8. Đánh giá abstraction: giảm chi phí hay tạo thêm tầng?

Một refactor thường tạo thêm interface, factory, strategy, adapter hoặc module. Những abstraction này chỉ có giá trị khi giảm một loại thay đổi cụ thể hoặc làm rõ ranh giới.

Trước khi thêm abstraction, hỏi:

1. Có ít nhất hai implementation thực sự khác nhau hoặc một ranh giới bên ngoài cần cô lập không?
2. Có lý do hợp lý để implementation thay đổi độc lập với caller không?
3. Abstraction có làm test đơn giản hơn hoặc cho phép contract test rõ hơn không?
4. Tên interface có thể diễn đạt khái niệm nghiệp vụ thay vì chỉ lặp lại tên class không?
5. Có làm tăng số bước điều hướng để hiểu một luồng đơn giản không?

Ví dụ, `PaymentGateway` có ý nghĩa nếu ứng dụng có nhiều provider hoặc cần cô lập giao thức của dịch vụ ngoài. Nhưng một interface `OrderServiceInterface` chỉ có một implementation, không có ranh giới module và không có nhu cầu thay thế, có thể chỉ tăng số file và số bean phải cấu hình.

### Tránh abstraction tổng quát quá sớm

Một framework nội bộ cho mọi loại integration có thể cần nhiều generic type, factory, registry, annotation và cấu hình. Ban đầu nó có vẻ giảm duplication; sau đó mỗi trường hợp đặc biệt lại cần hook hoặc override. Chi phí hiểu framework nội bộ có thể cao hơn phần code lặp ban đầu.

Hãy trừu tượng hóa khi có bằng chứng về mẫu lặp ổn định hoặc khi ranh giới thay đổi đã rõ. Hai đoạn code giống nhau về cú pháp nhưng khác nhau về quy tắc nghiệp vụ không nhất thiết nên dùng chung abstraction.

## 9. Đánh giá complexity và khả năng đọc

Các metric tĩnh có thể giúp xác định vùng đáng xem xét:

- Cyclomatic complexity: số đường đi độc lập qua logic điều khiển.
- Cognitive complexity: mức khó theo dõi logic do lồng nhau và nhảy ngữ cảnh.
- Coupling: số dependency hoặc module liên quan.
- Cohesion: mức độ các phần trong module phục vụ cùng một trách nhiệm.
- Duplication: logic hoặc quy tắc bị lặp ở nhiều nơi.
- Method/class size: tín hiệu cần xem xét, không phải ngưỡng chất lượng tuyệt đối.

Không có một ngưỡng số dòng hoặc complexity áp dụng đúng cho mọi class. Một phương thức dài xử lý một thuật toán có thể dễ đọc hơn nhiều phương thức một dòng có tên chung chung. Một interface có ít method vẫn có thể tạo abstraction sai nếu caller phải hiểu nhiều implementation detail.

Metric nên giúp đặt câu hỏi, không thay thế review. Hãy kiểm tra liệu người phát triển có thể trả lời nhanh:

- Dữ liệu vào từ đâu?
- Quy tắc nghiệp vụ nằm ở đâu?
- Side effect xảy ra khi nào?
- Lỗi được chuyển đổi ở lớp nào?
- Transaction bắt đầu và kết thúc ở đâu?
- Muốn thêm một trường hợp mới thì cần sửa những thành phần nào?

Nếu cấu trúc mới giúp trả lời những câu hỏi đó nhanh hơn, đó là bằng chứng có ích về khả năng bảo trì.

## 10. Dùng dữ liệu thay đổi và lỗi để đánh giá kết quả

Sau refactor, không nên chỉ so sánh số dòng code. Hãy quan sát những chỉ số liên quan đến chi phí thay đổi trong một khoảng thời gian đủ đại diện.

Một số tín hiệu:

| Chỉ số | Có thể cho biết điều gì | Cách diễn giải cẩn trọng |
|---|---|---|
| Lead time for change | Thời gian từ lúc bắt đầu đến khi thay đổi sẵn sàng | Cần so sánh các thay đổi có độ phức tạp tương đương. |
| Change failure rate | Tỷ lệ thay đổi gây incident, rollback hoặc hotfix | Một thay đổi đơn lẻ không đủ kết luận; xem xu hướng. |
| Rework/reopen rate | PR hoặc ticket phải sửa lại nhiều lần | Có thể phản ánh thiết kế khó hiểu hoặc yêu cầu chưa rõ. |
| Flaky test rate | Tỷ lệ test thất bại không ổn định | Tách nguyên nhân hạ tầng khỏi nguyên nhân code. |
| CI feedback time | Thời gian nhận kết quả kiểm thử | Refactor có thể giảm hoặc tăng số context/test phải chạy. |
| Files changed per feature | Số file phải sửa cho một loại tính năng | Không phải mục tiêu tối ưu độc lập; một thay đổi đúng ranh giới có thể sửa nhiều file. |
| Defect recurrence | Lỗi cùng loại có lặp lại không | Kiểm tra refactor đã xử lý nguyên nhân gốc chưa. |

Các chỉ số DORA như lead time, deployment frequency, change failure rate và time to restore service có thể giúp nhìn chất lượng phân phối ở cấp nhóm/sản phẩm. Không nên dùng chúng để chấm điểm một PR refactor đơn lẻ. Cần xem bối cảnh release, quy mô thay đổi và các yếu tố ngoài code.

### Không dùng coverage làm đại diện duy nhất cho khả năng bảo trì

Code coverage cho biết phần code được thực thi trong test, không cho biết assertion có kiểm tra hành vi quan trọng hay không. Một refactor có thể tăng coverage nhưng test lại phụ thuộc quá nhiều vào implementation. Ngược lại, một thay đổi làm test contract rõ hơn có thể có coverage tương đương nhưng giảm rủi ro hồi quy.

Khi review, xem test có kiểm tra các trường hợp biên, lỗi, side effect và hợp đồng tích hợp hay không. Coverage hữu ích như tín hiệu vùng chưa được thực thi, không phải bằng chứng duy nhất về chất lượng.

## 11. Ước lượng chi phí và lợi ích dài hạn

Một mô hình đơn giản để cân nhắc là so sánh chi phí refactor ban đầu với phần công sức có thể tiết kiệm trong các thay đổi tương lai.

```text
Tổng chi phí refactor =
    công sức thiết kế và triển khai
  + công sức viết/cập nhật test
  + chi phí migration và rollout
  + rủi ro hồi quy và thời gian xử lý sự cố
  + chi phí vận hành abstraction mới

Lợi ích kỳ vọng =
    số lần thay đổi tương lai
  x công sức tiết kiệm trung bình mỗi lần
  + chi phí lỗi/rework có thể tránh được
```

Ví dụ minh họa:

| Thành phần | Ước lượng |
|---|---:|
| Refactor và viết test | 5 ngày công |
| Migration/rollout và tài liệu | 1 ngày công |
| Tiết kiệm cho mỗi lần thay đổi payment | 0,5 ngày công |
| Số thay đổi tương tự dự kiến trong năm | 16 lần |
| Tiết kiệm công sức trực tiếp | 8 ngày công |

Trong ví dụ này, lợi ích trực tiếp dự kiến lớn hơn chi phí ban đầu, chưa tính giảm rework và giảm rủi ro. Đây không phải phép tính chính xác tuyệt đối; nó buộc nhóm nêu rõ giả định. Nếu chỉ có một thay đổi tương tự trong vài năm, refactor lớn có thể chưa đáng làm. Nếu vùng mã gây incident lặp lại, lợi ích giảm rủi ro có thể quan trọng hơn số ngày công tiết kiệm.

Không nên đưa ra dự báo quá chính xác khi dữ liệu không đủ. Dùng khoảng ước lượng, ghi giả định và xem lại sau một số thay đổi thực tế.

## 12. Đánh giá chi phí kiểm thử và CI sau refactor

Một refactor có thể làm code dễ unit test hơn nhưng lại tăng chi phí suite nếu tạo nhiều Spring context khác nhau hoặc thêm test container không cần thiết. Hãy đánh giá tổng thời gian phản hồi.

Các câu hỏi nên đặt ra:

- Unit test có chạy mà không cần khởi động Spring context không?
- Test slice có dùng đúng phạm vi bean cần thiết không?
- Có làm phát sinh nhiều context cache key do property/profile khác nhau không?
- Test tích hợp có khởi động cùng một container nhiều lần không?
- Test có phụ thuộc thời gian cố định hoặc thứ tự chạy không?
- Có thể chạy test module độc lập và song song an toàn không?
- CI có chạy lint/static analysis và test phù hợp với vùng thay đổi không?

Một cấu trúc tốt thường cho phép kiểm tra nhanh quy tắc nghiệp vụ bằng unit test, kiểm tra wiring bằng slice/integration test và dành end-to-end test cho các luồng quan trọng. Không nên dùng `@SpringBootTest` cho mọi trường hợp nếu test không cần full application context.

Nếu refactor tạo abstraction chỉ để mock mọi dependency, hãy kiểm tra xem số lượng mock và setup có tăng đáng kể không. Test cần mô tả hành vi; nếu phải dựng một đồ thị mock phức tạp để kiểm tra một quy tắc đơn giản, ranh giới mới có thể chưa hợp lý.

## 13. Migration, rollout và khả năng rollback

Refactor nội bộ có thể được triển khai một lần nếu thay đổi không ảnh hưởng schema, API hoặc trạng thái đang chạy. Nhưng nếu refactor đổi database schema, event schema, message format, configuration key hoặc endpoint tích hợp, cần kế hoạch chuyển đổi.

Một quy trình an toàn có thể gồm:

1. **Characterize:** ghi nhận hành vi hiện tại bằng test và quan sát.
2. **Introduce:** thêm cấu trúc mới trong khi giữ tương thích với caller hiện tại.
3. **Migrate:** chuyển caller hoặc dữ liệu theo từng bước.
4. **Verify:** xác nhận metric, log, contract và test ở từng giai đoạn.
5. **Remove:** chỉ xóa đường cũ khi không còn caller và đã có bằng chứng sử dụng.

Với database, mô hình expand-and-contract thường an toàn hơn thay đổi schema không tương thích trong một lần deploy:

- Thêm cột hoặc cấu trúc mới có thể chạy song song.
- Deploy code đọc/ghi tương thích với cả cấu trúc cũ và mới trong giai đoạn chuyển tiếp.
- Backfill dữ liệu nếu cần.
- Chuyển toàn bộ caller sang cấu trúc mới.
- Xác nhận không còn sử dụng cấu trúc cũ rồi mới xóa.

Nếu refactor chỉ thay đổi class nội bộ và không đổi schema/API, không cần tạo migration phức tạp. Hãy giữ quy trình tương xứng với rủi ro thực tế.

### Feature flag có cần thiết không?

Feature flag có thể hữu ích khi cần chuyển traffic giữa hai implementation hoặc rollout theo nhóm người dùng. Nhưng flag cũng tạo thêm nhánh, cấu hình và nghĩa vụ xóa sau migration. Không thêm flag cho một refactor nhỏ, không có rủi ro rollout đáng kể. Nếu dùng, cần xác định owner, điều kiện bật/tắt, metric quan sát và thời điểm gỡ flag.

## 14. Review log, metric và khả năng vận hành

Mã mới có thể sạch hơn nhưng làm việc điều tra lỗi khó hơn nếu bỏ mất thông tin vận hành.

Khi refactor integration hoặc async flow, cần xác nhận:

- Log vẫn có correlation/request id và business identifier cần thiết.
- Không log token, password hoặc dữ liệu cá nhân nhạy cảm.
- Metric giữ được ý nghĩa và tag không tạo cardinality quá cao.
- Trace vẫn nối được các bước qua HTTP, message và worker.
- Timeout, retry và circuit breaker không bị thay đổi ngoài ý muốn.
- Exception được giữ nguyên cause hoặc chuyển đổi có chủ đích.
- Tác vụ nền có cleanup và shutdown rõ ràng.

Nếu đổi tên metric hoặc log field, dashboard và alert có thể cần migration. Đây là chi phí bảo trì thực tế cần đưa vào PR, đặc biệt với hệ thống đã có dashboard, SLO hoặc runbook phụ thuộc vào tên cũ.

## 15. Những dấu hiệu refactor làm tăng chi phí bảo trì

Một số dấu hiệu nên được thảo luận trong review:

- Số lớp tăng nhiều nhưng trách nhiệm không rõ hơn.
- Một thao tác đơn giản phải đi qua nhiều factory, mapper và adapter.
- Interface chỉ có một implementation và không tạo ranh giới có giá trị.
- Logic nghiệp vụ bị phân tán vào annotation, expression hoặc cấu hình khó tìm.
- Test phải mock nhiều collaborator hơn trước.
- Cần thêm profile/property đặc biệt chỉ để dựng test.
- Transaction hoặc async behavior phụ thuộc vào self-invocation/proxy khó nhận biết.
- Một abstraction tổng quát cần nhiều hook và exception case.
- Xóa duplication nhưng làm hai quy tắc nghiệp vụ khác nhau bị ghép chung.
- Refactor làm mất log/metric hoặc thay đổi error semantics.
- PR quá lớn, trộn rename, move, behavior change và dependency upgrade khiến review khó xác định nguyên nhân.

Một số dấu hiệu tích cực:

- Trách nhiệm và dependency direction rõ hơn.
- Thay đổi một quy tắc chỉ cần sửa đúng một nơi có chủ sở hữu.
- Unit test nhanh hơn và ít phụ thuộc framework hơn.
- Integration test tập trung vào ranh giới thực sự cần xác nhận.
- Cấu hình và lifecycle bean dễ hiểu hơn.
- Lỗi có nguyên nhân và context rõ hơn.
- Các module có thể phát triển độc lập mà không cần biết implementation nội bộ của nhau.

## 16. Tổ chức pull request refactor để review được

Một PR refactor dễ review nên nêu rõ vấn đề và kết quả mong đợi:

**Vấn đề hiện tại:** ví dụ mỗi lần thêm payment provider phải sửa nhiều nhánh trong `CheckoutService`, đồng thời unit test cần dựng HTTP client và email sender thật.

**Thay đổi cấu trúc:** tách payment integration thành adapter sau `PaymentGateway`, chuyển dependency sang constructor và giữ quy tắc checkout trong application service.

**Hành vi được giữ:** status đơn hàng, số tiền charge, thứ tự lưu dữ liệu và lỗi khi payment bị từ chối.

**Bằng chứng:** characterization test, unit test cho service/policy, integration test cho transaction và contract test cho adapter.

**Rủi ro:** transaction boundary, retry semantics, bean selection và cấu hình provider.

**Rollout:** có cần migration/configuration flag hay chỉ thay implementation nội bộ?

Nếu PR lớn, chia thành các bước có thể review độc lập: rename/move không đổi logic, trích xuất collaborator, thay wiring, sau đó mới xóa đường cũ. Các bước này giúp phát hiện thay đổi hành vi ngoài ý muốn dễ hơn.

## 17. Khung review thực tế

Khi review một đề xuất, có thể dùng các câu hỏi sau để dẫn dắt trao đổi:

| Khía cạnh | Câu hỏi review |
|---|---|
| Lý do | Vấn đề bảo trì cụ thể nào đang được giải quyết? Có ví dụ từ thay đổi/bug thực tế không? |
| Phạm vi | Thay đổi có đúng vùng gây chi phí không? Có kéo theo module không liên quan không? |
| Hành vi | Hợp đồng API, nghiệp vụ, transaction và lỗi có được giữ nguyên hoặc thay đổi có chủ đích không? |
| Cohesion | Mỗi lớp/module có trách nhiệm dễ mô tả không? |
| Coupling | Caller có phụ thuộc vào implementation detail không? Thay đổi tương lai có ít lan rộng hơn không? |
| Abstraction | Interface/factory/event có ranh giới thay đổi thực tế không? |
| Testability | Có thể test quy tắc độc lập không? Test mới có ít brittle hơn không? |
| Spring semantics | Bean scope, proxy, transaction, async, event và configuration có thay đổi không? |
| CI | Test nào cần chạy? Thời gian và độ ổn định của pipeline có bị ảnh hưởng không? |
| Operations | Log, metric, trace, timeout và shutdown có còn đúng không? |
| Migration | Có thay đổi schema, event, property hoặc external contract không? Rollback ra sao? |
| Lợi ích | Có thể nêu cách đo xem chi phí bảo trì đã giảm sau khi triển khai không? |

Không cần mọi PR refactor trả lời mọi câu hỏi với cùng độ sâu. Một refactor nhỏ trong một phương thức có thể chỉ cần test và mô tả ngắn. Thay đổi module, transaction hoặc tích hợp ngoài cần bằng chứng rộng hơn.

## 18. Ví dụ: chọn giữa refactor nhỏ và tái thiết kế lớn

Giả sử một `OrderService` có ba nhánh điều kiện tính phí vận chuyển và nhóm muốn đưa toàn bộ quy trình checkout sang một workflow engine tổng quát.

Trước khi chọn giải pháp lớn, hãy xem dữ liệu:

- Có bao nhiêu loại shipping rule đang tồn tại?
- Quy tắc có thay đổi thường xuyên không?
- Các rule có chung cấu trúc hay khác nhau về bản chất?
- Lỗi hiện tại đến từ duplication, thứ tự điều kiện hay thiếu test?
- Có yêu cầu vận hành như retry, compensation hoặc audit workflow không?

Nếu chỉ có ba quy tắc ổn định và vấn đề chính là logic lồng nhau, tách `ShippingPolicy` cùng test cho các boundary có thể đủ. Workflow engine sẽ tạo chi phí dependency, cấu hình, monitoring, migration và onboarding mà nhóm chưa cần.

Nếu quy trình có nhiều bước dài hạn, cần compensation, retry qua nhiều ngày và theo dõi trạng thái, workflow engine có thể giảm chi phí vận hành và bảo trì. Khi đó chi phí triển khai ban đầu có cơ sở từ yêu cầu thực tế.

Điểm quan trọng là chọn mức cấu trúc vừa đủ để giải quyết vấn đề đã quan sát, và có thể giải thích chi phí nào sẽ giảm nhờ thay đổi đó.

## 19. Checklist trước khi chấp nhận refactor

- [ ] Vấn đề bảo trì được mô tả bằng ví dụ hoặc dữ liệu từ codebase.
- [ ] Phạm vi refactor nhắm đúng hotspot và không mở rộng tùy tiện.
- [ ] Hành vi hiện tại được ghi nhận bằng test hoặc contract phù hợp.
- [ ] Thay đổi nghiệp vụ được tách rõ khỏi thay đổi cấu trúc.
- [ ] Cohesion, coupling và dependency direction rõ hơn sau refactor.
- [ ] Abstraction mới có lý do tồn tại và không tạo thêm tầng không cần thiết.
- [ ] Constructor injection và Spring bean wiring vẫn rõ ràng.
- [ ] Transaction, AOP/proxy, security, cache, retry và async semantics đã được xem xét.
- [ ] Unit/integration/contract test được phân bổ đúng ranh giới.
- [ ] CI time, test flakiness và context startup không tăng ngoài dự kiến.
- [ ] Log, metric, trace và error handling giữ được khả năng vận hành.
- [ ] Migration, rollout và rollback được xác định nếu có thay đổi ngoài code nội bộ.
- [ ] Có cách quan sát lợi ích bảo trì sau khi refactor được triển khai.

Rà soát chi phí bảo trì giúp nhóm quyết định refactor nào đáng thực hiện và mức thay đổi nào phù hợp. Một refactor có giá trị khi giảm công sức hiểu, sửa, kiểm thử hoặc vận hành trong những tình huống thực tế mà nhóm thường gặp, trong khi giữ được hành vi và ranh giới hệ thống có chủ đích. Với ứng dụng Spring, cần xem cả cơ chế proxy, transaction, lifecycle, configuration và async processing; nếu chỉ nhìn code mới ngắn hơn hoặc có nhiều interface hơn, nhóm có thể bỏ sót chính những chi phí mà refactor tạo ra.
