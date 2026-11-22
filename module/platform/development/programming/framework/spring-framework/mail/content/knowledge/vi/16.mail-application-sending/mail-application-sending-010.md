# Giữ quy tắc người nhận ngoài controller

Một endpoint gửi email thường nhận request từ trình duyệt hoặc ứng dụng khác. Request có thể chứa mã đơn hàng, loại thông báo và đôi khi cả địa chỉ email muốn nhận thư. Controller tiếp nhận request, chuyển dữ liệu thành command rồi gọi application service. Nhưng **quyết định ai được nhận email, địa chỉ nào được dùng và khi nào được phép gửi** là quy tắc của ứng dụng/nghiệp vụ, không nên nằm trong controller.

Nếu controller tự tìm người nhận, kiểm tra quyền sở hữu đơn hàng, xác minh email, kiểm tra trạng thái đồng ý nhận thông báo và quyết định có được gửi hay không, logic sẽ bị gắn với HTTP. Khi cùng chức năng được gọi từ scheduler, message consumer hoặc một service nội bộ, những quy tắc đó có thể bị bỏ qua hoặc phải sao chép.

Trong **Spring Framework Mail**, `JavaMailSender` thực hiện việc gửi message qua hạ tầng mail. `MimeMessageHelper` dựng người nhận và nội dung MIME. Hai thành phần này không quyết định địa chỉ nhận có hợp lệ về mặt nghiệp vụ hay người gọi có quyền gửi tới địa chỉ đó không. Hãy giữ quy tắc người nhận trong application/domain service hoặc một policy chuyên trách, rồi để controller làm nhiệm vụ tiếp nhận và chuyển yêu cầu.

Bài này trình bày ranh giới giữa controller và application layer, cách xác định người nhận từ dữ liệu có thẩm quyền, xử lý địa chỉ thay thế, xác minh, consent, suppression, tenant, danh sách người nhận, kiểm thử và tích hợp với Spring Mail.

## 1. Người nhận email là một quyết định nghiệp vụ

Một email có thể được gửi tới nhiều loại người nhận: email tài khoản đã xác minh của khách hàng; địa chỉ liên hệ đã đăng ký cho hóa đơn; người phụ trách ticket hỗ trợ; địa chỉ do người dùng nhập để chia sẻ tài liệu; danh sách thành viên của tenant; hoặc địa chỉ nhận thông báo marketing đã đăng ký nhận tin.

Các trường hợp này không có cùng quy tắc. Email xác nhận đơn hàng thường phải gửi đến địa chỉ liên hệ hợp lệ gắn với khách hàng/đơn hàng. Email chia sẻ tài liệu có thể cho phép nhập địa chỉ bên ngoài, nhưng phải kiểm tra người gọi có quyền chia sẻ tài liệu và địa chỉ đó được phép nhận. Email marketing cần áp dụng chính sách consent và unsubscribe của sản phẩm.

Vì vậy, “recipient” không đơn thuần là một chuỗi `String`. Nó gắn với các câu hỏi:

- Ai đang yêu cầu gửi?
- Email thuộc về tài khoản hoặc khách hàng nào?
- Người gọi có quyền gửi thông tin này cho người nhận đó không?
- Địa chỉ đã được xác minh theo quy trình của ứng dụng chưa?
- Loại thông báo có được phép gửi tới địa chỉ này không?
- Người nhận có bị suppression, unsubscribe hoặc tạm khóa không?
- Địa chỉ có thuộc đúng tenant và đúng tài nguyên không?
- Có giới hạn số lần gửi hoặc số người nhận không?

Những câu hỏi này là quy tắc ứng dụng. Controller có thể nhận dữ liệu đầu vào và xác thực cấu trúc cơ bản, nhưng không nên trở thành nơi thực thi toàn bộ chính sách.

## 2. Controller nên làm gì?

Controller là adapter ở ranh giới HTTP. Trách nhiệm thường gồm:

1. Nhận path, query, body và thông tin xác thực từ request.
2. Kiểm tra cấu trúc đầu vào ở mức giao thức, chẳng hạn trường bắt buộc và định dạng cơ bản.
3. Lấy danh tính người gọi từ security context đã xác thực.
4. Tạo command thể hiện use case.
5. Gọi application service/handler.
6. Chuyển kết quả hoặc lỗi ứng dụng thành HTTP response phù hợp.

Controller không nên tự thực hiện các quy tắc như tự chọn email hóa đơn từ nhiều địa chỉ liên hệ, tự kiểm tra consent/suppression, tự chọn người nhận thay thế, tự kiểm soát quota hoặc tự dựng `MimeMessage` rồi gọi SMTP.

Ví dụ controller gọn:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderMailController {

    private final SendOrderConfirmationHandler handler;

    public OrderMailController(
            SendOrderConfirmationHandler handler) {
        this.handler = handler;
    }

    @PostMapping("/{orderId}/confirmation-email")
    public ResponseEntity<Void> sendConfirmation(
            @PathVariable UUID orderId,
            @AuthenticationPrincipal AppPrincipal principal) {

        handler.handle(new SendOrderConfirmationCommand(
                orderId,
                principal.userId()
        ));

        return ResponseEntity.accepted().build();
    }
}
~~~

Controller chỉ chuyển `orderId` và danh tính người gọi đã được xác thực vào command. Nó không nhận một email bất kỳ rồi tự quyết định có được gửi xác nhận đơn hàng tới đó không.

`AppPrincipal` là kiểu principal do ứng dụng định nghĩa trong ví dụ. Không lấy `userId` từ body nếu danh tính đó phải đến từ phiên đăng nhập đã xác thực.

## 3. Vì sao không nên đặt recipient policy trong controller?

### 3.1. Logic bị gắn với HTTP

Một chức năng gửi email có thể được gọi từ nhiều nguồn:

~~~mermaid
flowchart LR
    A["HTTP controller"] --> E["Application service"]
    B["Scheduled job"] --> E
    C["Message consumer"] --> E
    D["Internal workflow"] --> E
~~~

Nếu quy tắc người nhận chỉ nằm trong controller, scheduler hoặc consumer có thể gọi service gửi mail trực tiếp mà không chạy các kiểm tra đó.

### 3.2. Dễ sao chép quy tắc và tạo hành vi không nhất quán

Controller A có thể kiểm tra email đã xác minh; controller B quên kiểm tra. Một luồng kiểm tra suppression list, luồng khác không. Khi quy tắc thay đổi, nhóm phát triển phải tìm và sửa nhiều nơi. Đặt policy tại một application/domain boundary giúp mọi entry point sử dụng cùng quy tắc.

### 3.3. Khó kiểm thử nghiệp vụ

Nếu logic nằm trong controller, unit test phải dựng HTTP request, principal và nhiều dependency chỉ để kiểm tra “người nhận có được phép nhận thông báo không”. Khi policy nằm trong service riêng, có thể kiểm thử bằng object đầu vào rõ ràng mà không cần web server.

### 3.4. Controller dễ trở thành nơi truy cập quá nhiều dữ liệu

Một controller vừa đọc order, customer, contact, tenant, consent và suppression repository vừa gửi mail có quá nhiều trách nhiệm. Application service điều phối các thành phần đó theo một use case rõ ràng hơn.

## 4. Phân biệt validation, authorization và recipient policy

Ba khái niệm thường bị gộp chung nhưng trả lời các câu hỏi khác nhau.

| Cơ chế | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Structural validation | Dữ liệu có đúng hình dạng không? | `orderId` có mặt; địa chỉ email có cú pháp phù hợp. |
| Authorization | Người gọi có quyền thực hiện hành động trên tài nguyên không? | User hiện tại có quyền xem đơn hàng này không? |
| Recipient policy | Địa chỉ nào được phép nhận loại thông báo này? | Chỉ gửi tới email liên hệ đã xác minh của khách hàng. |
| Business rule | Use case có được phép xảy ra ở trạng thái hiện tại không? | Chỉ gửi xác nhận sau khi đơn đã được tạo. |
| Delivery policy | Gửi lúc nào, giới hạn bao nhiêu lần và xử lý retry ra sao? | Không gửi quá giới hạn thông báo trong một khoảng thời gian. |

`@Email` hoặc validator cú pháp không chứng minh địa chỉ tồn tại, người gọi sở hữu nó hay có quyền gửi dữ liệu tới đó. Tương tự, authorization cho phép người dùng xem đơn hàng không tự động có nghĩa họ được gửi hóa đơn của đơn hàng tới bất kỳ địa chỉ nào.

Các lớp kiểm tra có thể được gọi trong cùng application service, nhưng nên giữ rõ mục đích để không nhầm “địa chỉ có định dạng hợp lệ” với “địa chỉ được phép nhận”.

## 5. Lấy recipient từ nguồn dữ liệu có thẩm quyền

Với email xác nhận đơn hàng, thường không cần cho client gửi địa chỉ người nhận. Command có thể chỉ chứa định danh đơn hàng và người gọi:

~~~java
public record SendOrderConfirmationCommand(
        UUID orderId,
        UUID requestedBy) {
}
~~~

Application service tải dữ liệu và quyết định người nhận:

~~~java
@Service
public class SendOrderConfirmationHandler {

    private final OrderRepository orders;
    private final CustomerRepository customers;
    private final OrderRecipientPolicy recipientPolicy;
    private final MailGateway mailGateway;

    public SendOrderConfirmationHandler(
            OrderRepository orders,
            CustomerRepository customers,
            OrderRecipientPolicy recipientPolicy,
            MailGateway mailGateway) {
        this.orders = orders;
        this.customers = customers;
        this.recipientPolicy = recipientPolicy;
        this.mailGateway = mailGateway;
    }

    public void handle(SendOrderConfirmationCommand command) {
        Order order = orders.findById(command.orderId())
                .orElseThrow(() ->
                        new OrderNotFoundException(command.orderId()));

        Customer customer = customers.findById(order.customerId())
                .orElseThrow(() ->
                        new CustomerNotFoundException(order.customerId()));

        MailRecipient recipient =
                recipientPolicy.requireOrderConfirmationRecipient(
                        command.requestedBy(),
                        order,
                        customer
                );

        // Tạo nội dung từ order/customer đã được kiểm tra.
        // Sau đó gửi qua gateway.
    }
}
~~~

Ví dụ này thể hiện vị trí gọi policy. Các repository, domain object và exception là thành phần ứng dụng giả định.

Điểm quan trọng là địa chỉ được lấy từ hồ sơ liên hệ có thẩm quyền, sau đó kiểm tra theo chính sách. Client không thể sửa `recipient` trong request để chuyển thông tin đơn hàng sang địa chỉ khác.

### Không chỉ dựa vào orderId

Nếu endpoint nhận `orderId`, ứng dụng vẫn phải kiểm tra người gọi có quyền truy cập đơn hàng. Một UUID khó đoán không phải cơ chế authorization. Trình tự thường là:

1. Tải tài nguyên trong phạm vi tenant phù hợp.
2. Kiểm tra người gọi có quyền trên tài nguyên.
3. Xác định người nhận được phép theo use case.
4. Kiểm tra trạng thái email/recipient policy.
5. Render và gửi.

Không nên chỉ kiểm tra order tồn tại rồi gửi thư cho địa chỉ lấy từ request.
## 6. Recipient policy là gì?

Recipient policy là nơi diễn đạt quy tắc chọn và cho phép người nhận theo loại thông báo. Có thể dùng một interface:

~~~java
public interface OrderRecipientPolicy {

    MailRecipient requireOrderConfirmationRecipient(
            UUID requestedBy,
            Order order,
            Customer customer);
}
~~~

Một kiểu dữ liệu recipient nội bộ:

~~~java
public record MailRecipient(
        String address,
        UUID contactId) {
}
~~~

Policy có thể kiểm tra khách hàng còn hoạt động không, email liên hệ có tồn tại và đã được xác minh không, contact có thuộc đúng customer/tenant không, địa chỉ có bị suppression không và người gọi có quyền yêu cầu gửi thông báo cho contact đó không.

Ví dụ:

~~~java
@Component
public class DefaultOrderRecipientPolicy
        implements OrderRecipientPolicy {

    private final ContactRepository contacts;
    private final SuppressionRepository suppressions;
    private final OrderAccessPolicy orderAccess;

    public DefaultOrderRecipientPolicy(
            ContactRepository contacts,
            SuppressionRepository suppressions,
            OrderAccessPolicy orderAccess) {
        this.contacts = contacts;
        this.suppressions = suppressions;
        this.orderAccess = orderAccess;
    }

    @Override
    public MailRecipient requireOrderConfirmationRecipient(
            UUID requestedBy,
            Order order,
            Customer customer) {

        orderAccess.requireCanReceiveOrderNotice(
                requestedBy,
                order
        );

        Contact contact = contacts
                .findPreferredVerifiedEmail(customer.id())
                .orElseThrow(() ->
                        new NoEligibleRecipientException(customer.id()));

        if (suppressions.isSuppressed(
                contact.email(),
                MailPurpose.ORDER_CONFIRMATION)) {
            throw new RecipientSuppressedException();
        }

        return new MailRecipient(
                contact.email(),
                contact.id()
        );
    }
}
~~~

Đây là ví dụ cấu trúc. Repository method `findPreferredVerifiedEmail` có hợp đồng chỉ trả về contact đã xác minh và thuộc customer tương ứng. Nếu repository không bảo đảm điều đó, policy cần kiểm tra các invariant này rõ ràng trước khi trả recipient.

### Policy có thể trả về kết quả thay vì ném exception

Nếu ứng dụng cần giải thích vì sao không gửi, có thể dùng kiểu kết quả:

~~~java
public sealed interface RecipientDecision {
    record Allowed(MailRecipient recipient)
            implements RecipientDecision {}

    record Rejected(RecipientRejection reason)
            implements RecipientDecision {}
}
~~~

Ví dụ reason code:

~~~java
public enum RecipientRejection {
    NO_VERIFIED_ADDRESS,
    SUPPRESSED,
    NOT_AUTHORIZED,
    WRONG_TENANT,
    CONSENT_REQUIRED
}
~~~

Chọn exception hay result object tùy quy ước dự án. Điều quan trọng là không âm thầm bỏ qua điều kiện hoặc fallback sang một địa chỉ không được phê duyệt.

## 7. Địa chỉ email người dùng nhập: khi nào được phép?

Không phải use case nào cũng chọn recipient từ hồ sơ. Một tính năng chia sẻ hóa đơn hoặc gửi bản sao tài liệu có thể cho người dùng nhập địa chỉ ngoài.

Ví dụ request DTO:

~~~java
public record ShareInvoiceRequest(
        @NotBlank
        @Email
        String recipient) {
}
~~~

Controller có thể dùng `@Valid` để kiểm tra hình dạng:

~~~java
@PostMapping("/{invoiceId}/share")
public ResponseEntity<Void> shareInvoice(
        @PathVariable UUID invoiceId,
        @Valid @RequestBody ShareInvoiceRequest request,
        @AuthenticationPrincipal AppPrincipal principal) {

    shareInvoiceHandler.handle(
            new ShareInvoiceCommand(
                    invoiceId,
                    principal.userId(),
                    request.recipient()
            )
    );

    return ResponseEntity.accepted().build();
}
~~~

Controller không quyết định địa chỉ đó có được phép nhận hóa đơn không. Handler/policy phải kiểm tra:

- Người gọi có quyền chia sẻ hóa đơn này không?
- Hóa đơn có thuộc đúng tenant/customer không?
- Tính năng có cho phép gửi ra ngoài tổ chức không?
- Địa chỉ có nằm trong danh sách chặn hoặc suppression không?
- Người gọi có được phép chia sẻ dữ liệu loại này với recipient bên ngoài không?
- Có giới hạn số lần chia sẻ và số người nhận không?

### Địa chỉ nhập vào không tự chứng minh quyền sở hữu

Người dùng có thể nhập địa chỉ của người khác. Nếu ứng dụng gửi thông tin nhạy cảm tới địa chỉ đó mà không có chính sách phù hợp, có thể gây lộ dữ liệu.

Với use case cần xác minh người nhận, có thể gửi một thông báo xác minh hoặc link có thời hạn trước khi cung cấp dữ liệu. Với hóa đơn, hợp đồng hoặc dữ liệu cá nhân, sản phẩm phải xác định rõ điều kiện chia sẻ và quyền của người yêu cầu.

### Đừng dùng một rule chung cho mọi loại email

Email xác nhận tài khoản, hóa đơn, cảnh báo bảo mật, newsletter và email chia sẻ tài liệu có thể có recipient policy khác nhau. Một địa chỉ đã unsubscribe khỏi marketing không nhất thiết phải chặn một email giao dịch bắt buộc; ngược lại, trạng thái email đã xác minh không tự động chứng minh consent marketing.

Hãy định nghĩa policy theo **purpose/type của email**, không chỉ theo chuỗi địa chỉ.

## 8. Xác minh địa chỉ và cập nhật email tài khoản

Một tài khoản có thể thay đổi địa chỉ email. Nếu ứng dụng gửi thông báo quan trọng ngay sau khi người dùng nhập địa chỉ mới, cần xác định địa chỉ đó đã được xác minh chưa.

Một mô hình contact có thể lưu:

~~~java
public record EmailContact(
        UUID id,
        String address,
        boolean verified,
        Instant verifiedAt,
        boolean primary) {
}
~~~

Đây là ví dụ DTO/domain model; trạng thái thật có thể được lưu bằng entity riêng.

Một luồng thay đổi email thường có các bước:

1. Người dùng yêu cầu đổi địa chỉ.
2. Ứng dụng lưu địa chỉ mới ở trạng thái pending.
3. Gửi link xác minh tới địa chỉ mới.
4. Người dùng chứng minh khả năng truy cập địa chỉ đó.
5. Ứng dụng đánh dấu contact đã xác minh và áp dụng chính sách primary contact.
6. Các thông báo tiếp theo dùng địa chỉ đã được chọn theo recipient policy.

Không nên đánh dấu verified chỉ vì request chứa địa chỉ hợp lệ hoặc người dùng đã đăng nhập. `@Email` chỉ kiểm tra cú pháp; xác minh cần một quy trình chứng minh quyền truy cập.

### Địa chỉ cũ và địa chỉ mới

Khi thay đổi email, ứng dụng có thể cần thông báo tới địa chỉ cũ, địa chỉ mới hoặc cả hai theo chính sách bảo mật. Quyết định đó thuộc use case đổi email, không phải controller. Đặc biệt, không để request tự chọn một địa chỉ nhận link xác minh mà không ràng buộc với trạng thái thay đổi đang chờ.

## 9. Phân biệt transactional email và marketing email

Các loại email có thể có quy tắc người nhận khác nhau.

| Loại | Ví dụ | Quy tắc recipient cần xem xét |
| --- | --- | --- |
| Transactional | Xác nhận đơn hàng, hóa đơn, reset password | Người nhận gắn với tài khoản/giao dịch; authorization và tính đúng đắn dữ liệu |
| Security alert | Đăng nhập mới, thay đổi email | Địa chỉ đã xác minh hoặc kênh liên hệ bảo mật theo chính sách |
| Operational notice | Bảo trì dịch vụ, sự cố tenant | Thành viên/đầu mối thuộc đúng tenant và vai trò |
| Marketing | Newsletter, khuyến mãi | Consent, unsubscribe, suppression và quy định áp dụng |
| User-initiated share | Gửi tài liệu tới địa chỉ do user nhập | Quyền chia sẻ tài nguyên, kiểm soát recipient ngoài và audit |

Không nên áp dụng cùng một điều kiện “đã đăng ký nhận tin” cho mọi email mà không phân loại mục đích. Cũng không nên lấy nhãn “transactional” để bỏ qua mọi kiểm tra. Ứng dụng vẫn cần đúng người nhận, đúng mục đích, quyền truy cập và các yêu cầu pháp lý/chính sách liên quan.

### Consent và unsubscribe

Với email marketing, recipient policy thường cần xem trạng thái đăng ký, thời điểm consent, phạm vi nội dung, nguồn consent và trạng thái unsubscribe/suppression. Việc kiểm tra nên diễn ra tại application boundary ngay trước khi tạo job gửi hoặc trước khi worker gửi, tùy kiến trúc và yêu cầu cập nhật trạng thái.

Nếu người nhận đã unsubscribe, không nên gửi lại marketing chỉ vì một controller khác không đọc trạng thái đó. Dùng một policy tập trung để các entry point áp dụng cùng quy tắc.

## 10. Suppression list và địa chỉ không được gửi

Suppression list có thể chứa các địa chỉ:

- Người nhận đã yêu cầu unsubscribe.
- Địa chỉ hard bounce hoặc không còn khả dụng.
- Địa chỉ bị complaint/spam report.
- Địa chỉ bị khóa theo yêu cầu bảo mật hoặc quản trị.
- Địa chỉ không được phép nhận một loại thông báo cụ thể.

Suppression có thể áp dụng toàn hệ thống hoặc theo từng purpose/provider. Vì vậy, policy nên nhận biết **loại thông báo** và phạm vi suppression.

Ví dụ:

~~~java
public enum MailPurpose {
    ORDER_CONFIRMATION,
    PASSWORD_RESET,
    SECURITY_ALERT,
    MARKETING
}
~~~

~~~java
public interface RecipientSuppressionPolicy {
    void requireNotSuppressed(
            EmailAddress recipient,
            MailPurpose purpose);
}
~~~

Một suppression marketing không nhất thiết có cùng tác động với cảnh báo bảo mật. Quyết định phải được xác định bởi chính sách sản phẩm và quy định áp dụng; không tự động dùng một boolean chung `blocked` cho mọi loại mail nếu hệ thống có các trường hợp ngoại lệ hợp lệ.

### Kiểm tra suppression ở thời điểm phù hợp

Nếu gửi email ngay lập tức, kiểm tra recipient policy trước khi gửi. Nếu tạo job bất đồng bộ, trạng thái suppression có thể thay đổi giữa lúc tạo job và lúc worker xử lý. Với các loại mail cần trạng thái mới nhất, worker nên kiểm tra lại policy trước khi giao message cho gateway.

Cần xác định hành vi nếu policy từ chối: đánh dấu job là suppressed, lưu reason code phù hợp và không retry như lỗi SMTP. Một địa chỉ bị chặn theo policy không phải lỗi kết nối có thể giải quyết bằng retry.

## 11. Tenant và ranh giới tổ chức

Trong ứng dụng multi-tenant, cùng một email address có thể xuất hiện trong nhiều tenant hoặc người dùng có vai trò khác nhau theo từng tenant. Không nên tìm contact chỉ theo email rồi gửi dữ liệu tenant A cho người có liên quan tenant B.

Command có thể mang tenant context được xác định từ security/session:

~~~java
public record SendTenantNoticeCommand(
        UUID tenantId,
        UUID requestedBy,
        String noticeCode) {
}
~~~

Application service cần xác minh người gọi thuộc tenant đó và có quyền gửi thông báo. Recipient resolver chỉ truy vấn contact trong tenant tương ứng:

~~~java
Optional<TenantContact> findEligibleRecipient(
        UUID tenantId,
        NoticePurpose purpose);
~~~

Không tin `tenantId` từ body nếu tenant thực tế phải lấy từ authenticated context hoặc membership đã được xác minh. Nếu request có tenant ID, application layer vẫn phải kiểm tra nó phù hợp với phạm vi quyền của principal.

### Không để recipient trở thành đường vòng qua tenant

Một user thuộc tenant A không nên gửi email chứa dữ liệu tenant A tới địa chỉ được lấy từ hồ sơ tenant B chỉ vì địa chỉ đó tồn tại. Cần kiểm tra tài nguyên thuộc tenant nào, người gọi có quyền trên tài nguyên, contact được chọn thuộc cùng tenant hay được phép chia sẻ liên tenant, và có policy cho external recipient hay không.

Các kiểm tra này thuộc use case/policy, không nên dựa vào controller route hoặc UI để bảo đảm.

## 12. Cc, Bcc và danh sách người nhận

Một request có thể muốn gửi cho nhiều người. Khi đó, recipient policy cần xử lý cả danh sách, không chỉ từng địa chỉ riêng lẻ.

Các điểm cần quyết định:

- Số lượng recipient tối đa.
- Có cho phép To/Cc/Bcc hay chỉ To?
- Có loại bỏ địa chỉ trùng không?
- Người nhận có được nhìn thấy địa chỉ của nhau không?
- Mỗi người có quyền nhận cùng nội dung không?
- Có cần gửi message riêng cho từng người để cá nhân hóa không?
- Nếu một địa chỉ không hợp lệ, toàn bộ batch thất bại hay chỉ bỏ địa chỉ đó?

### Không làm lộ danh sách người nhận

Nếu gửi cùng một email cho nhiều người không quen biết, đặt tất cả vào To hoặc Cc có thể tiết lộ địa chỉ email của họ cho nhau. Bcc có thể phù hợp trong một số trường hợp, nhưng vẫn phải tuân theo chính sách quyền riêng tư và mục đích gửi.

Với email cá nhân hóa hoặc có dữ liệu nhạy cảm, thường nên tạo message riêng cho từng recipient. Không đưa danh sách người nhận từ tenant khác hoặc nhóm không liên quan vào cùng một message.

### Kiểm soát số lượng và trùng lặp

Ví dụ request DTO:

~~~java
public record BulkNoticeRequest(
        @NotEmpty
        @Size(max = 50)
        List<@NotBlank @Email String> recipients,
        @NotBlank
        String noticeCode) {
}
~~~

Con số 50 chỉ là giới hạn minh họa. Ứng dụng cần đặt giới hạn theo quota provider, kích thước message, chính sách sản phẩm và khả năng chống lạm dụng.

Deduplicate cũng cần có chính sách chuẩn hóa địa chỉ rõ ràng. Domain email không phân biệt hoa thường theo DNS, nhưng local-part về mặt tiêu chuẩn có thể phân biệt; không nên tùy tiện lowercase toàn bộ địa chỉ rồi giả định mọi provider xử lý giống nhau. Có thể trim khoảng trắng và áp dụng quy tắc canonicalization đã được sản phẩm chấp thuận, nhưng phải giữ nguyên semantics của địa chỉ.

## 13. Địa chỉ email: cú pháp, chuẩn hóa và quyền sử dụng

Một địa chỉ có dạng gần đúng:

~~~text
local-part@domain
~~~

Nhưng việc kiểm tra cú pháp email không thể chứng minh domain đang hoạt động, mailbox tồn tại, người nhận kiểm soát mailbox, người nhận muốn nhận loại email này hoặc người gọi có quyền gửi dữ liệu tới đó.

`@Email` của Bean Validation hữu ích để kiểm tra cấu trúc đầu vào ở mức cơ bản, nhưng không phải quy trình xác minh mailbox. Một số địa chỉ hợp lệ theo chuẩn có thể không được provider hoặc hệ thống nội bộ chấp nhận; ngược lại, regex quá chặt có thể từ chối địa chỉ hợp lệ.

Ví dụ DTO:

~~~java
public record ExternalShareRequest(
        @NotBlank
        @Email
        @Size(max = 254)
        String recipient) {
}
~~~

Giới hạn 254 là giá trị thường dùng trong ứng dụng nhưng cần đối chiếu với quy tắc địa chỉ/provider mà hệ thống hỗ trợ. Không nên xem một con số giới hạn là bằng chứng về tính hợp lệ cuối cùng.

### Chuẩn hóa cẩn trọng

Một số bước có thể phù hợp:

- Loại bỏ khoảng trắng vô tình ở đầu/cuối nếu hợp đồng API cho phép.
- Từ chối ký tự điều khiển hoặc newline.
- Dùng parser địa chỉ email phù hợp khi cần hỗ trợ cú pháp hiển thị tên.
- Chuẩn hóa domain theo quy tắc IDN nếu hệ thống hỗ trợ.
- Giữ nguyên local-part theo chính sách đã chọn; không tự ý xóa dấu chấm hoặc dấu cộng vì các provider có semantics khác nhau.

Đừng tự viết regex lớn để giải quyết mọi dạng địa chỉ. Hãy xác định tập định dạng hệ thống hỗ trợ và dùng parser/validator phù hợp.

### Không ghép raw header từ input

Đặt người nhận qua API như `helper.setTo(...)` hoặc overload nhận `InternetAddress`, không tự ghép chuỗi header `To:` từ dữ liệu. Từ chối ký tự CR/LF không mong muốn và dùng thư viện MIME để encode header. Đây là một phần của bảo vệ ranh giới mail, ngoài recipient policy nghiệp vụ.

## 14. Recipient policy và Reply-To/From không giống nhau

Một email có nhiều địa chỉ với vai trò khác nhau:

| Trường | Vai trò |
| --- | --- |
| To | Người nhận chính |
| Cc | Người nhận bản sao được hiển thị |
| Bcc | Người nhận bản sao ẩn |
| `From` | Địa chỉ người gửi hiển thị |
| `Reply-To` | Địa chỉ gợi ý để người nhận trả lời |
| SMTP account | Credential dùng xác thực với SMTP relay |

Recipient policy tập trung vào **ai nhận message**. `From`, `Reply-To` và SMTP account là các khía cạnh khác. Ví dụ, đặt `Reply-To` thành địa chỉ support không có nghĩa email được gửi tới support; người nhận chính vẫn là To.

+## 15. Gửi email sau khi policy đã cho phép

Sau khi application service đã xác định recipient hợp lệ, tầng gửi mail có thể nhận một object nội bộ:

~~~java
public record OutboundMail(
        MailRecipient recipient,
        String subject,
        String plainText,
        String html) {
}
~~~

Gateway sử dụng Spring Mail:

~~~java
@Component
public class SpringMailGateway {

    private final JavaMailSender mailSender;

    public SpringMailGateway(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(OutboundMail mail) {
        try {
            MimeMessage message = mailSender.createMimeMessage();

            MimeMessageHelper helper =
                    new MimeMessageHelper(message, true, "UTF-8");

            helper.setFrom("notice@example.org");
            helper.setTo(mail.recipient().address());
            helper.setSubject(mail.subject());
            helper.setText(mail.plainText(), mail.html());

            mailSender.send(message);
        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Không thể chuẩn bị email", ex
            );
        } catch (MailException ex) {
            throw new MailDeliveryException(
                    "Không thể gửi email qua SMTP", ex
            );
        }
    }
}
~~~

`MailPreparationException` và `MailDeliveryException` là exception riêng của ứng dụng trong ví dụ. Gateway không tự quyết định ai được nhận; nó nhận một recipient đã được application layer xác định.

Nếu gateway được gọi từ nhiều use case, có thể thiết kế để nhận một kiểu `ApprovedRecipient` chỉ được tạo qua policy hoặc application boundary. Đây là cách biểu đạt ý định trong code, không phải cơ chế bảo mật tuyệt đối: Java visibility và module boundary vẫn cần được thiết kế phù hợp.

### Không cho gateway trở thành public endpoint gửi tùy ý

Một gateway nội bộ có thể có phương thức tổng quát `send(OutboundMail)`. Không nên expose phương thức này trực tiếp ra HTTP mà không qua policy. Nếu bất kỳ caller nào cũng có thể tự tạo `OutboundMail` với người nhận bất kỳ và HTML tùy ý, các quy tắc use case có thể bị bỏ qua.

## 16. Đưa recipient policy vào luồng bất đồng bộ

Với gửi mail bất đồng bộ, application service có thể tạo job rồi worker gửi sau:

~~~mermaid
flowchart TD
    A["Controller / Event / Scheduler"] --> B["Application command handler"]
    B --> C["Authorization + recipient policy"]
    C --> D["Lưu mail job / outbox"]
    D --> E["Mail worker"]
    E --> F["Kiểm tra policy hiện hành nếu cần"]
    F --> G["Render message"]
    G --> H["JavaMailSender"]
    H --> I["Cập nhật trạng thái"]
~~~

Có hai thời điểm có thể kiểm tra policy:

- **Khi tạo job:** xác nhận use case hợp lệ và người nhận ban đầu được phép.
- **Ngay trước khi gửi:** kiểm tra những điều kiện có thể thay đổi, như suppression, unsubscribe hoặc trạng thái contact.

Việc kiểm tra lại phụ thuộc yêu cầu nghiệp vụ. Với email xác nhận đơn hàng, snapshot người nhận tại thời điểm tạo sự kiện có thể là điều cần thiết để bảo đảm lịch sử. Với marketing, trạng thái unsubscribe mới nhất thường cần được tôn trọng khi worker thực hiện gửi.

### Lưu recipient snapshot hay resolve lại?

| Cách | Ý nghĩa | Cần cân nhắc |
| --- | --- | --- |
| Lưu snapshot recipient | Job gửi tới địa chỉ đã được xác định tại thời điểm tạo | Địa chỉ có thể đã thay đổi hoặc bị suppression trước lúc worker chạy |
| Resolve recipient khi gửi | Worker lấy contact hiện tại từ hệ thống | Người nhận có thể khác người được dự kiến lúc tạo job |
| Snapshot + policy recheck | Lưu recipient/purpose và kiểm tra điều kiện có thể thay đổi trước gửi | Cần định nghĩa rõ điều kiện nào được phép làm job bị hủy |

Không có một cách đúng cho mọi use case. Với thông báo bảo mật hoặc giao dịch, quyết định có thể ảnh hưởng đến audit và quyền truy cập. Hãy ghi nhận recipient identity, purpose, thời điểm lựa chọn và kết quả policy ở mức metadata phù hợp.

## 17. Chống lạm dụng và giới hạn gửi

Một endpoint cho phép nhập recipient ngoài có thể bị dùng để gửi spam hoặc quấy rối nếu không giới hạn. Recipient policy và delivery policy có thể phối hợp kiểm tra:

- Số email tối đa theo user/tenant trong một khoảng thời gian.
- Số recipient tối đa trong một command.
- Tần suất gửi tới cùng một địa chỉ.
- Các loại thông báo được phép gửi từ endpoint.
- Quyền sử dụng tài nguyên được chia sẻ.
- Trạng thái tài khoản, tenant và API key.
- Hành vi gửi bất thường hoặc lặp lại.

Ví dụ interface:

~~~java
public interface MailRateLimitPolicy {
    void requireWithinLimit(
            UUID actorId,
            UUID tenantId,
            MailPurpose purpose);
}
~~~

Policy này nên được gọi ở application layer hoặc một thành phần chuyên trách, không chỉ dựa vào rate limit ở API gateway. Rate limit HTTP có thể bảo vệ endpoint, nhưng job từ scheduler hoặc event consumer cũng cần những giới hạn phù hợp.

### Không tiết lộ quá nhiều qua lỗi recipient

Với các use case nhạy cảm như password reset, thông báo lỗi có thể giúp kẻ tấn công dò xem email nào đã đăng ký. Public response có thể cần giữ thông điệp trung tính, trong khi log nội bộ lưu reason code phù hợp và bảo vệ dữ liệu.

Ví dụ response bên ngoài có thể nói “Nếu tài khoản phù hợp tồn tại, hướng dẫn sẽ được gửi” thay vì tiết lộ trực tiếp tài khoản có hay không. Quy tắc cụ thể phụ thuộc threat model của ứng dụng.

## 18. Audit và log recipient policy

Khi không gửi được do policy, đó là kết quả nghiệp vụ khác với lỗi SMTP. Có thể lưu metadata:

~~~text
mail_request_id: req-7f2...
purpose: ORDER_CONFIRMATION
tenant_id: tenant-42
recipient_contact_id: contact-19
decision: REJECTED
reason: SUPPRESSED
requested_at: 2026-11-12T09:00:00Z
~~~

Đây là bản ghi minh họa. Không nên log địa chỉ email đầy đủ, nội dung message, token hoặc SMTP credential nếu không có nhu cầu và biện pháp bảo vệ phù hợp. Có thể dùng contact ID, hash có quản lý khóa hoặc dữ liệu đã che một phần theo chính sách logging.

Audit nên giúp trả lời use case nào yêu cầu gửi, ai hoặc thành phần nào khởi tạo, recipient được resolve từ đâu, policy nào được áp dụng, kết quả allow/reject và reason code, message có được đưa tới gateway không, SMTP provider phản hồi thế nào.

Cần phân biệt **policy rejected**, **message prepared**, **SMTP accepted** và **delivery confirmed**. SMTP chấp nhận không chứng minh email đã vào inbox.

## 19. Kiểm thử recipient policy ngoài controller

Khi policy nằm trong service riêng, có thể test trực tiếp với các trường hợp:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Contact chính đã xác minh, không suppression | Cho phép |
| Không có địa chỉ đã xác minh | Từ chối |
| Contact thuộc tenant khác | Từ chối |
| Người gọi không có quyền trên order | Từ chối |
| Địa chỉ bị suppression cho purpose tương ứng | Từ chối |
| Marketing consent không tồn tại | Từ chối theo policy marketing |
| User nhập địa chỉ ngoài nhưng use case không cho phép | Từ chối |
| Recipient hợp lệ nhưng vượt rate limit | Từ chối hoặc trì hoãn theo delivery policy |

Ví dụ test dạng khung:

~~~java
@Test
void rejectsOrderRecipientWhenContactIsNotVerified() {
    // Arrange:
    // - order và customer hợp lệ
    // - contact chưa xác minh
    // - actor có quyền trên order

    assertThrows(
            NoEligibleRecipientException.class,
            () -> policy.requireOrderConfirmationRecipient(
                    actorId,
                    order,
                    customer
            )
    );
}
~~~

Test này không cần dựng HTTP request hoặc gọi SMTP. Nó kiểm tra quy tắc chọn người nhận ở đúng lớp.

### Kiểm thử controller riêng

Controller test tập trung vào việc request hợp lệ được ánh xạ thành command đúng, actor ID lấy từ authenticated principal, request sai cấu trúc trả HTTP error phù hợp và application exception được chuyển thành response qua exception handler.

Không cần lặp lại toàn bộ policy test trong từng controller test. Có thể mock application handler để xác nhận controller gọi đúng command.

### Kiểm thử tích hợp

Integration test có thể dùng repository test database, fake mail gateway hoặc SMTP test server để xác nhận toàn luồng. Tách test policy, controller, renderer và SMTP giúp xác định lỗi ở đúng ranh giới.

## 20. Ví dụ endpoint cho địa chỉ ngoài nhưng policy vẫn ở application layer

Có trường hợp sản phẩm cho phép người dùng nhập địa chỉ để gửi bản sao tài liệu. Controller chỉ nhận request và chuyển command:

~~~java
public record ShareDocumentRequest(
        @NotBlank
        @Email
        @Size(max = 254)
        String recipient) {
}
~~~

~~~java
public record ShareDocumentCommand(
        UUID documentId,
        UUID requestedBy,
        String recipient) {
}
~~~

Controller:

~~~java
@PostMapping("/{documentId}/share")
public ResponseEntity<Void> share(
        @PathVariable UUID documentId,
        @Valid @RequestBody ShareDocumentRequest request,
        @AuthenticationPrincipal AppPrincipal principal) {

    shareDocumentHandler.handle(
            new ShareDocumentCommand(
                    documentId,
                    principal.userId(),
                    request.recipient()
            )
    );

    return ResponseEntity.accepted().build();
}
~~~

Handler:

~~~java
@Service
public class ShareDocumentHandler {

    private final DocumentRepository documents;
    private final DocumentSharePolicy sharePolicy;
    private final MailGateway mailGateway;

    public ShareDocumentHandler(
            DocumentRepository documents,
            DocumentSharePolicy sharePolicy,
            MailGateway mailGateway) {
        this.documents = documents;
        this.sharePolicy = sharePolicy;
        this.mailGateway = mailGateway;
    }

    public void handle(ShareDocumentCommand command) {
        Document document = documents.findById(command.documentId())
                .orElseThrow(() ->
                        new DocumentNotFoundException(command.documentId()));

        sharePolicy.requireCanShare(
                command.requestedBy(),
                document,
                command.recipient()
        );

        // Tạo link chia sẻ có quyền và thời hạn phù hợp.
        // Render email rồi gửi qua gateway.
    }
}
~~~

`DocumentSharePolicy` có thể kiểm tra quyền chia sẻ, loại tài liệu, tenant, recipient ngoài, suppression và rate limit. Controller không cần biết chi tiết những quy tắc đó.

+## 21. Những lỗi thường gặp

### 21.1. Controller tự chọn email từ request

**Vấn đề:** client có thể thay địa chỉ để nhận dữ liệu không thuộc về mình.

**Cách xử lý:** với thông báo gắn tài khoản/giao dịch, resolve recipient từ nguồn dữ liệu có thẩm quyền trong application service.

### 21.2. Chỉ kiểm tra @Email rồi gửi

**Vấn đề:** cú pháp đúng không chứng minh địa chỉ tồn tại, được xác minh hoặc có quyền nhận.

**Cách xử lý:** tách structural validation khỏi authorization và recipient policy.

### 21.3. Đặt policy trong một controller duy nhất

**Vấn đề:** scheduler hoặc consumer có thể gọi service mà bỏ qua policy.

**Cách xử lý:** đặt quy tắc ở application/domain service mà mọi entry point sử dụng.

### 21.4. Dùng một recipient rule cho mọi loại email

**Vấn đề:** transactional, security, marketing và sharing có điều kiện khác nhau.

**Cách xử lý:** truyền purpose rõ ràng và áp dụng policy phù hợp.

### 21.5. Tin recipient do client gửi trong use case nhạy cảm

**Vấn đề:** người gọi có thể chuyển hóa đơn, reset link hoặc thông tin cá nhân tới địa chỉ ngoài.

**Cách xử lý:** resolve từ contact đã xác minh hoặc yêu cầu quy trình chia sẻ/ủy quyền riêng.

### 21.6. Không kiểm tra tenant

**Vấn đề:** contact hoặc tài nguyên có thể thuộc tenant khác.

**Cách xử lý:** scope repository query và policy theo tenant đã xác thực; không tin tenant ID do client tự khai báo.

### 21.7. Bỏ qua suppression khi worker gửi job cũ

**Vấn đề:** người nhận có thể unsubscribe hoặc bị suppression sau khi job được tạo.

**Cách xử lý:** xác định thời điểm policy phải được kiểm tra lại, đặc biệt với marketing.

### 21.8. Dùng Bcc để gửi dữ liệu không được phép

**Vấn đề:** Bcc ẩn địa chỉ khỏi người nhận khác, nhưng không tạo quyền gửi hoặc quyền chia sẻ dữ liệu.

**Cách xử lý:** kiểm tra mọi To/Cc/Bcc theo cùng nguyên tắc quyền và purpose.

### 21.9. Log toàn bộ email address và nội dung

**Vấn đề:** log trở thành nơi lưu dữ liệu cá nhân, token và nội dung riêng tư.

**Cách xử lý:** dùng ID, reason code và metadata tối thiểu; bảo vệ log theo chính sách.

### 21.10. Retry lỗi policy như lỗi SMTP

**Vấn đề:** địa chỉ bị suppression hoặc không có quyền nhận không được giải quyết bằng retry.

**Cách xử lý:** phân loại rejected/suppressed khác với transient delivery failure.

### 21.11. Controller gọi JavaMailSender trực tiếp

**Vấn đề:** HTTP layer phụ thuộc MIME, SMTP và quy tắc gửi; các luồng khác dễ bỏ qua policy.

**Cách xử lý:** controller gọi use case, application service áp dụng policy, gateway mới gọi Spring Mail.

### 21.12. Tự động fallback sang email phụ

**Vấn đề:** địa chỉ phụ có thể chưa xác minh, thuộc người khác hoặc không được phép nhận loại dữ liệu đó.

**Cách xử lý:** fallback phải là một quy tắc nghiệp vụ rõ ràng, có xác minh và audit; không tự chọn địa chỉ đầu tiên còn lại.

## 22. Bài tập suy luận

**Câu 1.** Endpoint xác nhận đơn hàng nhận `orderId` và `recipient` từ client. Có nên gửi tới `recipient` mà không kiểm tra?

Không. Application service phải xác minh quyền trên order và chọn/cho phép recipient theo policy. Với use case thông thường, địa chỉ liên hệ có thẩm quyền có thể được resolve từ customer/order.

**Câu 2.** `@Email` trả về hợp lệ có chứng minh người nhận đã xác minh địa chỉ không?

Không. Nó chỉ kiểm tra định dạng ở mức validator; xác minh cần quy trình chứng minh quyền truy cập mailbox.

**Câu 3.** Vì sao recipient policy không nên chỉ nằm trong controller?

Vì scheduler, consumer và internal workflow có thể gọi use case mà không đi qua controller. Policy ở application/domain layer được dùng chung cho mọi entry point.

**Câu 4.** Người dùng unsubscribe marketing. Có nên chặn mọi email transactional không?

Không thể kết luận như vậy. Policy phải phân biệt purpose và tuân theo quy tắc sản phẩm/pháp lý áp dụng. Unsubscribe marketing không tự động đồng nghĩa với việc chặn mọi thông báo giao dịch hoặc bảo mật.

**Câu 5.** User thuộc tenant A nhập email của contact tenant B để nhận hóa đơn tenant A. Chỉ cần email đúng cú pháp có đủ không?

Không. Phải kiểm tra quyền chia sẻ tài nguyên, tenant boundary và recipient policy.

**Câu 6.** Job marketing được tạo hôm qua, người nhận unsubscribe hôm nay, worker gửi ngày mai. Nên làm gì?

Nếu chính sách yêu cầu tôn trọng trạng thái mới nhất, worker cần kiểm tra suppression/consent ngay trước khi gửi và đánh dấu job bị suppressed thay vì retry SMTP.

**Câu 7.** Bcc có làm cho việc gửi tới một địa chỉ bất kỳ trở nên hợp lệ không?

Không. Bcc chỉ ẩn header recipient khỏi những người nhận khác; nó không thay thế authorization hoặc recipient policy.

**Câu 8.** Controller test đã xác nhận endpoint trả HTTP 202. Điều đó chứng minh policy đúng chưa?

Chưa. Policy cần unit/integration test riêng ở application layer. Controller test chủ yếu kiểm tra mapping request và response.

**Câu 9.** Có nên lowercase toàn bộ email address để deduplicate?

Không nên tự động giả định local-part luôn không phân biệt hoa thường. Hãy dùng quy tắc canonicalization có chủ đích, tôn trọng semantics của hệ thống/provider.

**Câu 10.** Gateway có thể nhận một `OutboundMail` tổng quát không?

Có thể ở tầng nội bộ sau khi application layer đã quyết định recipient và nội dung. Không nên expose gateway như endpoint công khai cho phép caller bỏ qua policy.

## 23. Mô hình ghi nhớ

Luồng gửi email nên giữ recipient policy ở application/domain boundary:

~~~mermaid
flowchart TD
    A["Controller / Scheduler / Event"] --> B["Command"]
    B --> C["Application service"]
    C --> D["Authorization + business checks"]
    D --> E["Recipient resolver / policy"]
    E --> F{"Recipient được phép?"}
    F -->|"Không"| G["Reject / Suppressed / Audit"]
    F -->|"Có"| H["Render nội dung email"]
    H --> I["Mail gateway"]
    I --> J["MimeMessageHelper"]
    J --> K["JavaMailSender"]
    K --> L["SMTP relay"]
~~~

Các nguyên tắc chính:

1. **Controller tiếp nhận request và tạo command**, không tự quyết định người nhận theo nghiệp vụ.
2. **Resolve recipient từ nguồn dữ liệu có thẩm quyền** khi email gắn với tài khoản, đơn hàng hoặc tài liệu.
3. **Tách validation, authorization và recipient policy**: cú pháp email đúng không chứng minh quyền nhận.
4. **Phân loại theo purpose**: transactional, security, marketing và sharing có thể có quy tắc khác nhau.
5. **Kiểm tra verification, consent, suppression và tenant** ở application/domain layer phù hợp.
6. **Địa chỉ do người dùng nhập vẫn phải qua policy**; request DTO và `@Email` chỉ là lớp kiểm tra cấu trúc.
7. **Kiểm soát To, Cc và Bcc** như các recipient thực sự; Bcc không tạo quyền gửi.
8. **Xác định thời điểm kiểm tra lại policy** đối với job bất đồng bộ và retry.
9. **Phân biệt policy rejection với lỗi SMTP**, lưu reason code và audit metadata phù hợp.
10. **Giữ JavaMailSender trong gateway**; application service quyết định gửi cho ai, gateway thực hiện việc gửi.

Với thiết kế này, controller có thể mỏng và dễ thay đổi, còn quy tắc người nhận được thực thi nhất quán dù yêu cầu đến từ HTTP, scheduler hay event consumer. `MimeMessageHelper` và `JavaMailSender` chỉ xử lý việc dựng và gửi message sau khi ứng dụng đã xác định người nhận hợp lệ theo đúng use case.



