# Khi gửi mail đồng bộ phù hợp

Trong Spring Framework Mail, lời gọi §JavaMailSender.send(...)§ thường thực hiện việc gửi SMTP ngay trên thread đang gọi. Phương thức chỉ trả về sau khi quá trình gửi qua transport hoàn tất hoặc phát sinh lỗi. Đây là cách gửi **đồng bộ** (*synchronous sending*): caller chờ kết quả từ thao tác gửi trước khi tiếp tục công việc.

Gửi đồng bộ phù hợp khi số lượng email thấp, thao tác ngắn, người gọi cần biết ngay việc chuyển message tới SMTP có thành công hay không, và thời gian chờ có thể chấp nhận được trong luồng hiện tại. Ví dụ là công cụ quản trị gửi một thông báo thủ công, ứng dụng nội bộ có ít email, hoặc một thao tác cần báo lỗi gửi ngay cho người vận hành.

Cách gửi này có một giới hạn quan trọng: **SMTP chấp nhận message không có nghĩa email đã vào inbox hoặc người nhận đã đọc thư**. Nó chỉ cho biết bước giao message tới máy chủ SMTP đã đạt kết quả mà transport báo về. Ngoài ra, caller phải giữ thread trong suốt thời gian kết nối, xác thực, truyền dữ liệu và chờ phản hồi.

Bài học này giải thích ngữ nghĩa của gửi đồng bộ, những trường hợp nên dùng, cách tích hợp với request và transaction, xử lý lỗi/timeout, giới hạn tải, idempotency và các dấu hiệu cho thấy ứng dụng cần chuyển sang hàng đợi hoặc transactional outbox.

## 1. Gửi mail đồng bộ nghĩa là gì?

Với cách gửi đồng bộ, code gọi §JavaMailSender§ và chờ lời gọi kết thúc:

§§§java
mailSender.send(message);

// Dòng tiếp theo chỉ chạy sau khi send trả về
updateNotificationStatus();
§§§

Luồng thực thi có thể hình dung:

§§§text
Caller thread
    |
    v
Build MimeMessage
    |
    v
JavaMailSender.send(...)
    |
    +--> Connect to SMTP server
    |
    +--> Authenticate (if configured)
    |
    +--> Transfer message data
    |
    +--> Receive SMTP response
    |
    v
Return or throw MailException
    |
    v
Continue caller code
§§§

Trong thời gian này, thread gọi đang chờ. Nếu đây là thread xử lý HTTP request, request đó cũng phải chờ cho tới khi gửi xong hoặc timeout.

Ví dụ service đơn giản:

§§§java
@Service
public class NotificationMailService {

    private final JavaMailSender mailSender;

    public NotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotice(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("notice@example.org");
        helper.setTo(recipient);
        helper.setSubject("Thông báo");
        helper.setText("Yêu cầu của bạn đã được xử lý.");

        mailSender.send(message);
    }
}
§§§

Khi §sendNotice§ trả về bình thường, thao tác gửi của sender đã hoàn tất theo kết quả mà transport cung cấp. Nếu SMTP server từ chối hoặc có lỗi khi tạo/gửi message, Spring có thể ném một exception thuộc hệ thống §MailException§.

### Đồng bộ không đồng nghĩa với giao thư tức thời

SMTP là giao thức chuyển tiếp thư. Một phản hồi thành công từ SMTP server thường có nghĩa máy chủ đã chấp nhận trách nhiệm xử lý message theo giao thức. Nó không xác nhận:

- Message đã được chuyển tới mailbox cuối cùng.
- Email không bị spam filter hoặc policy của nhà cung cấp chặn.
- Địa chỉ người nhận còn hoạt động.
- Người nhận đã mở hoặc đọc thư.

Muốn theo dõi delivery, bounce hoặc complaint, cần tích hợp sự kiện từ nhà cung cấp email hoặc hệ thống mail tương ứng. Kết quả trả về của §JavaMailSender.send§ chỉ là một phần trong vòng đời gửi.

## 2. Khi nào gửi đồng bộ là lựa chọn phù hợp?

Gửi đồng bộ phù hợp khi lợi ích của phản hồi ngay lớn hơn chi phí giữ thread và phụ thuộc vào SMTP.

### 2.1. Công cụ quản trị hoặc thao tác thủ công có tần suất thấp

Ví dụ:

- Nhân viên vận hành bấm nút gửi lại một thông báo.
- Quản trị viên gửi email kiểm tra cấu hình SMTP.
- Một công cụ nội bộ gửi báo cáo nhỏ theo yêu cầu.
- Hệ thống hỗ trợ gửi một email xác nhận thủ công cho từng trường hợp.

Trong các luồng này, số lượng yêu cầu thấp và người thực hiện có thể chờ kết quả. Nếu SMTP lỗi, giao diện có thể báo ngay để người vận hành xử lý.

Cần phân biệt thao tác gửi thủ công với gửi chiến dịch hàng loạt. Một nút gửi một thư có thể phù hợp với sync; gửi hàng nghìn người nhận cần cơ chế hàng đợi, giới hạn tốc độ và theo dõi từng recipient.

### 2.2. Ứng dụng nội bộ có tải thấp và thời gian chờ chấp nhận được

Một ứng dụng nội bộ có vài người dùng, mỗi thao tác chỉ gửi một email nhỏ, có thể dùng gửi đồng bộ nếu:

- SMTP server ổn định và ở gần về mạng.
- Timeout được cấu hình rõ.
- Request timeout của ứng dụng lớn hơn thời gian gửi dự kiến.
- Số thread xử lý request đủ cho thời gian chờ.
- Người dùng hiểu rằng thao tác có thể mất thêm vài giây.

Đây là lựa chọn vận hành đơn giản cho hệ thống nhỏ. Khi lưu lượng tăng hoặc SMTP trở nên chậm, cần đo lại trước khi tiếp tục dùng trong request path.

### 2.3. Cần phản hồi ngay về việc SMTP chấp nhận hay từ chối message

Một số thao tác có ý nghĩa khi caller biết kết quả gửi ngay, ví dụ:

- Công cụ kiểm tra cấu hình mail server.
- Trang quản trị gửi email thử nghiệm tới một địa chỉ đã nhập.
- Công cụ hỗ trợ gửi một thông báo theo yêu cầu của nhân viên.
- Quy trình nội bộ cần hiển thị lỗi cấu hình hoặc lỗi xác thực SMTP cho người vận hành.

Ở đây, phản hồi cần được diễn đạt chính xác là “SMTP đã chấp nhận message” hoặc “không gửi được tới SMTP”, tùy kết quả. Không hiển thị “người nhận đã nhận email” chỉ vì §send§ trả về bình thường.

### 2.4. Email là một phần trực tiếp của thao tác ngắn, có thể thất bại rõ ràng

Có thể dùng sync nếu thao tác nghiệp vụ vốn đã yêu cầu caller đợi một kết quả bên ngoài và hệ thống chấp nhận việc thao tác thất bại khi SMTP không khả dụng. Ví dụ một công cụ xuất báo cáo rồi gửi một email cho chính người yêu cầu, trong đó kết quả công việc chỉ được xác nhận khi SMTP chấp nhận message.

Cần quyết định rõ điều gì xảy ra nếu báo cáo đã tạo xong nhưng gửi email thất bại. Có thể giữ file để tải xuống, đánh dấu lần gửi thất bại và cho phép retry thủ công. Không nên giả định một exception SMTP sẽ tự đảo ngược những tác động đã xảy ra trước đó.

### 2.5. Kiểm thử, command-line tool và tác vụ vận hành ngắn

Trong test hoặc một command-line utility, gửi đồng bộ thường dễ hiểu: gọi sender, chờ, rồi assert kết quả hoặc trả exit code. Không cần dựng một hệ thống queue chỉ để gửi một message trong bài kiểm tra hoặc công cụ dùng một lần.

Với integration test, nên dùng SMTP server giả lập như GreenMail hoặc Mailpit. Test xác nhận message đã được server thử nghiệm nhận, thay vì gửi thư thật tới người dùng.

## 3. Khi nào nên cân nhắc cách gửi khác?

Gửi đồng bộ trở nên bất tiện khi việc gửi không còn là thao tác ngắn hoặc caller không cần chờ kết quả SMTP.

| Tình huống | Vì sao sync gây bất lợi | Hướng phù hợp hơn |
|---|---|---|
| Gửi email cho nhiều người | Request giữ thread lâu, dễ vượt timeout | Queue và worker |
| Email phát sinh sau mỗi đơn hàng lớn | SMTP chậm làm chậm luồng tạo đơn | Transactional outbox |
| Nhà cung cấp SMTP thường xuyên chậm/gián đoạn | Caller chịu toàn bộ độ trễ và lỗi | Queue, retry có kiểm soát, circuit breaker |
| Cần retry sau khi ứng dụng restart | Caller request đã kết thúc, không còn công việc để tiếp tục | Lưu yêu cầu bền vững trong outbox |
| Cần rate limit theo nhà cung cấp | Nhiều request đồng thời có thể vượt quota | Worker có concurrency/rate limit |
| Cần audit từng lần gửi và trạng thái | Trạng thái chỉ nằm trong request log | Delivery record và worker |
| Email không được làm thất bại nghiệp vụ chính | SMTP lỗi có thể khiến API báo lỗi dù dữ liệu đã commit | Outbox và gửi nền |
| Cần xử lý nhiều file đính kèm lớn | Thời gian serialize/truyền dữ liệu dài | Job nền và storage phù hợp |

Không phải mọi email quan trọng đều cần gửi đồng bộ. Email quan trọng thường cần **độ tin cậy và khả năng retry**, điều mà queue/outbox có thể cung cấp tốt hơn.

## 4. Đánh giá độ trễ trước khi đưa send vào request path

Một request đồng bộ có thời gian phản hồi gồm nhiều phần:

§§§text
Request duration
  = business processing
  + template rendering
  + SMTP connect/authentication
  + message transfer
  + SMTP response wait
§§§

Thời gian SMTP không cố định. Nó phụ thuộc mạng, DNS, TLS handshake, xác thực, kích thước message, nhà cung cấp và tình trạng server. Một request gửi mail có thể nhanh trong điều kiện bình thường nhưng chậm đáng kể khi SMTP gặp sự cố.

Trước khi chọn sync, hãy đo:

- Thời gian trung bình và percentile cao (p95/p99) của §send§.
- Tỷ lệ exception theo loại.
- Thời gian kết nối và thời gian ghi message.
- Kích thước message, đặc biệt khi có attachment/inline image.
- Số request gửi mail đồng thời.
- Số thread HTTP bị giữ trong lúc chờ SMTP.

Không chỉ nhìn thời gian trung bình. Nếu đa số email mất 200 ms nhưng một số ít mất 20 giây, những request chậm vẫn có thể chiếm hết thread khi tải tăng.

### Ví dụ ngân sách thời gian

Giả sử API có mục tiêu phản hồi trong 2 giây. Nếu nghiệp vụ và database đã sử dụng 1,2 giây, phần gửi mail chỉ còn khoảng 800 ms trong ngân sách đó. Nếu SMTP thường xuyên cần vài giây, gửi trong request path sẽ làm mục tiêu không ổn định.

Con số này là ví dụ lập kế hoạch, không phải giới hạn mặc định của Spring. Hãy dùng số đo từ môi trường thực tế và SLA của sản phẩm.

## 5. Gửi đồng bộ trong HTTP request

Một controller có thể gọi service gửi mail trực tiếp:

§§§java
@RestController
@RequestMapping("/admin/mail")
public class AdminMailController {

    private final NotificationMailService mailService;

    public AdminMailController(NotificationMailService mailService) {
        this.mailService = mailService;
    }

    @PostMapping("/test")
    public ResponseEntity<String> sendTest(
            @RequestParam String recipient
    ) {
        mailService.sendTestMail(recipient);
        return ResponseEntity.ok("SMTP accepted the test message");
    }
}
§§§

Ví dụ này phù hợp với một endpoint quản trị có quyền truy cập được kiểm soát, tần suất thấp và mục tiêu là kiểm tra kết nối gửi mail.

Trong hệ thống thật, cần xác thực và phân quyền người gọi, kiểm tra địa chỉ recipient theo chính sách, giới hạn tần suất, không cho phép request tùy ý đặt From hoặc SMTP header, trả thông báo phản ánh đúng ý nghĩa của kết quả, và xử lý §MailException§ thành response phù hợp mà không để lộ credential hoặc thông tin nội bộ.

### Không để request chờ vô hạn

SMTP timeout phải được cấu hình. Nếu không có giới hạn phù hợp, một kết nối bị treo có thể giữ thread lâu hơn dự kiến.

Ví dụ cấu hình Spring Boot:

§§§yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    properties:
      "mail.smtp.connectiontimeout": 5000
      "mail.smtp.timeout": 5000
      "mail.smtp.writetimeout": 5000
§§§

Các giá trị trong ví dụ tính bằng millisecond và cần điều chỉnh theo provider, môi trường mạng và SLA. Ba timeout kiểm soát các giai đoạn khác nhau:

- §connectiontimeout§: thời gian chờ thiết lập kết nối.
- §timeout§: thời gian chờ đọc phản hồi.
- §writetimeout§: thời gian chờ ghi dữ liệu.

Tên property thuộc cấu hình JavaMail SMTP; nếu dùng transport hoặc provider khác, cần kiểm tra property tương ứng. Cũng cần đồng bộ timeout với reverse proxy, load balancer và HTTP client để request không bị cắt trước khi ứng dụng xử lý xong.

## 6. Xử lý lỗi khi gửi đồng bộ

§JavaMailSender§ ném các exception thuộc hệ thống §MailException§ khi gửi thất bại. Các lỗi có thể xuất hiện ở nhiều giai đoạn:

- Cấu hình host/port không đúng.
- DNS hoặc kết nối mạng thất bại.
- TLS handshake không thành công.
- Xác thực SMTP bị từ chối.
- Địa chỉ người nhận hoặc message bị server từ chối.
- Lỗi khi serialize MIME part hoặc đọc attachment.
- SMTP server không phản hồi trong timeout.

Một service có thể xử lý lỗi ở ranh giới phù hợp:

§§§java
import org.springframework.mail.MailException;
import org.springframework.stereotype.Service;

@Service
public class SynchronousNotificationService {

    private final JavaMailSender mailSender;

    public SynchronousNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public SendResult send(MimeMessage message) {
        try {
            mailSender.send(message);
            return SendResult.smtpAccepted();
        } catch (MailException exception) {
            // Ghi log mã message và loại lỗi; tránh log credential/payload.
            return SendResult.smtpFailed(classify(exception));
        }
    }

    private String classify(MailException exception) {
        return exception.getClass().getSimpleName();
    }
}
§§§

§SendResult§ là kiểu dữ liệu minh họa của ứng dụng. Trong thực tế, có thể giữ cause để chẩn đoán nội bộ, nhưng response gửi ra client chỉ nên chứa thông báo an toàn và mã lỗi ổn định.

### Không nuốt exception rồi báo thành công

Mẫu nguy hiểm:

§§§java
try {
    mailSender.send(message);
} catch (MailException exception) {
    log.warn("Mail failed", exception);
}

return "Email sent successfully";
§§§

Code trên biến lỗi SMTP thành thành công giả. Nếu nghiệp vụ cần biết thao tác gửi có thành công hay không, hãy trả trạng thái rõ ràng hoặc ném exception để tầng gọi xử lý.

### Phân biệt lỗi tạm thời và lỗi lâu dài

Một số lỗi có thể thử lại sau, ví dụ timeout tạm thời hoặc SMTP server không khả dụng. Một số lỗi cần sửa dữ liệu/cấu hình, ví dụ recipient không hợp lệ hoặc xác thực bị từ chối.

Không nên retry mọi §MailException§ theo cùng một cách. Nếu gửi đồng bộ, có thể trả lỗi cho caller và cho phép thao tác gửi lại sau khi xác định nguyên nhân. Với hệ thống có retry tự động, cần phân loại lỗi, đặt giới hạn số lần, backoff và idempotency.

### Chú ý trường hợp kết quả không chắc chắn

Có thể xảy ra tình huống ứng dụng đã truyền message và SMTP server đã nhận, nhưng kết nối bị đứt trước khi ứng dụng nhận phản hồi cuối cùng. Caller thấy timeout hoặc exception và không biết chắc server đã nhận hay chưa.

Nếu lập tức gửi lại, người nhận có thể nhận email trùng. Đây là một dạng kết quả không xác định (*ambiguous outcome*) của giao tiếp mạng. Với thông báo có thể gửi trùng gây tác động đáng kể, cần message ID nghiệp vụ, delivery record và cơ chế idempotency hoặc deduplication phù hợp.

## 7. Không gửi SMTP bên trong database transaction dài

Gửi email là một tác động tới hệ thống bên ngoài. Database transaction không thể rollback một message mà SMTP server đã chấp nhận.

Ví dụ không nên làm:

§§§java
@Transactional
public Order createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(create(command));

    mailService.sendConfirmation(order);

    return order;
}
§§§

Có hai tình huống rủi ro:

1. SMTP chấp nhận email, sau đó transaction database rollback. Người nhận đã nhận một thông báo về đơn hàng không được commit.
2. Database đã thực hiện nhiều thao tác và đang giữ lock, nhưng SMTP chậm hoặc lỗi. Transaction bị kéo dài, làm tăng contention và thời gian chờ của request khác.

### Nếu vẫn cần gửi đồng bộ, gửi sau khi transaction commit

Có thể tách thao tác lưu dữ liệu và gửi mail:

§§§java
public Order createOrder(CreateOrderCommand command) {
    Order order = transactionTemplate.execute(status ->
            orderRepository.save(create(command))
    );

    mailService.sendConfirmation(order);
    return order;
}
§§§

Trong ví dụ này, transaction lưu đơn hàng hoàn tất trước khi gửi mail. Nếu SMTP lỗi, đơn hàng vẫn đã tồn tại. Tầng gọi cần quyết định response và cách người vận hành gửi lại.

Một lựa chọn khác là §@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)§ để chạy listener sau commit:

§§§java
@Component
public class OrderMailListener {

    private final NotificationMailService mailService;

    public OrderMailListener(NotificationMailService mailService) {
        this.mailService = mailService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreated event) {
        mailService.sendConfirmation(event.orderId());
    }
}
§§§

Listener mặc định chạy đồng bộ trong luồng phát event sau commit, trừ khi được cấu hình bất đồng bộ. Cách này tránh gửi trước khi transaction commit nhưng **không tạo bảo đảm bền vững** nếu process dừng sau commit và trước khi listener gửi xong. Nếu email phải được gửi đáng tin cậy, dùng outbox hoặc cơ chế lưu công việc bền vững.

## 8. Đừng nhầm gửi đồng bộ với @Async

§@Async§ cho phép Spring thực thi phương thức trên executor thread khác khi được gọi qua proxy Spring phù hợp. Đây là gửi bất đồng bộ ở cấp thread:

§§§java
@Async
public void sendLater(MimeMessage message) {
    mailSender.send(message);
}
§§§

Caller có thể tiếp tục trước khi việc gửi hoàn tất. Nhưng điều này khác với queue bền vững:

| Đặc điểm | Gửi đồng bộ | §@Async§ trong process | Queue/outbox bền vững |
|---|---|---|---|
| Caller chờ SMTP | Có | Thường không | Không |
| Công việc tồn tại sau khi process dừng | Không có hàng đợi riêng | Thường không, tùy executor | Có nếu được lưu bền vững |
| Retry sau restart | Caller phải thực hiện lại | Cần cơ chế riêng | Worker có thể tiếp tục từ record |
| Quan sát trạng thái | Kết quả ngay trong call | Cần Future/callback/status | Có delivery/job record |
| Phù hợp | Tác vụ ngắn, ít tải, cần kết quả ngay | Tác vụ nền đơn giản trong process | Email nghiệp vụ cần độ tin cậy và khả năng retry |

§@Async§ cũng có giới hạn:

- Gọi phương thức async từ một phương thức khác trong cùng object có thể không đi qua proxy, nên không được chạy async như mong đợi.
- Executor cần có giới hạn thread và queue capacity.
- Exception trong phương thức trả về §void§ không tự được ném về caller.
- Process restart có thể làm mất công việc đang chờ hoặc đang chạy.
- Không có bảo đảm exactly-once khi gửi SMTP.

Vì vậy, nếu chỉ muốn caller không chờ, §@Async§ có thể phù hợp cho thông báo ít quan trọng và chấp nhận mất công việc khi process gặp sự cố. Nếu cần bảo đảm yêu cầu gửi được lưu và tiếp tục sau restart, hãy dùng queue hoặc outbox.

## 9. Gửi đồng bộ có thể làm cạn thread như thế nào?

Trong server web, mỗi request thường sử dụng một thread trong một khoảng thời gian. Nếu request gọi SMTP đồng bộ, thread đó bị giữ trong khi chờ mạng.

Giả sử ứng dụng có 100 thread xử lý request và nhiều request đồng thời đều chờ SMTP. Khi đủ 100 thread bị giữ, request mới có thể phải chờ trong hàng đợi của server hoặc bị từ chối theo cấu hình.

§§§mermaid
flowchart TD
    A["HTTP requests"] --> B["Request thread pool"]
    B --> C["Request 1 waits for SMTP"]
    B --> D["Request 2 waits for SMTP"]
    B --> E["Request 3 waits for SMTP"]
    B --> F["Other request threads"]
    C --> G["SMTP provider"]
    D --> G
    E --> G
    G --> H["SMTP response"]
    H --> I["Threads become available"]
§§§

Điều này có thể tạo hiệu ứng dây chuyền:

1. SMTP chậm làm request giữ thread lâu hơn.
2. Thread pool dần đầy.
3. Request không liên quan đến email cũng chậm vì thiếu thread.
4. Retry từ client làm tăng tải.
5. Hệ thống càng khó phục hồi khi SMTP chưa ổn định.

Nếu vẫn dùng sync, cần giới hạn số thao tác gửi đồng thời, cấu hình timeout, theo dõi thread pool và đặt rate limit cho endpoint có thể kích hoạt gửi mail.

## 10. Giới hạn tốc độ và số lượng email đồng bộ

Một vòng lặp gửi hàng loạt:

§§§java
for (String recipient : recipients) {
    mailSender.send(buildMessage(recipient));
}
§§§

thực hiện tuần tự. Thời gian tổng có thể gần bằng tổng thời gian của từng lần gửi. Nếu gửi song song bằng nhiều thread, thời gian có thể giảm nhưng tạo thêm kết nối và tải lên SMTP provider.

Với gửi đồng bộ, nên đặt các giới hạn:

- Số recipient tối đa cho một request.
- Số message gửi trong một khoảng thời gian.
- Số lần gửi đồng thời.
- Kích thước message và attachment tối đa.
- Timeout của connect/read/write.
- Ngưỡng cảnh báo khi latency hoặc lỗi tăng.

Không nên dùng request đồng bộ để gửi newsletter hoặc campaign lớn. Những công việc đó cần queue, batch, suppression list, unsubscribe policy, rate limit và delivery tracking.

### Một request gửi nhiều recipient có thể tạo rủi ro riêng tư

Nếu nhiều người nhận được đặt vào cùng một trường §To§ hoặc §Cc§, địa chỉ có thể hiển thị cho những người khác. Khi cần gửi riêng từng người, tạo message phù hợp cho từng recipient hoặc dùng cơ chế gửi hàng loạt có quản lý personalization. Việc gom nhiều địa chỉ vào một message cũng làm khó xác định recipient nào bị từ chối.

## 11. Idempotency và nguy cơ gửi trùng

Gửi đồng bộ không bảo đảm một yêu cầu HTTP chỉ tạo đúng một email. Người dùng có thể double-click, trình duyệt retry, gateway retry request hoặc client gửi lại sau timeout.

Ví dụ:

1. API nhận request gửi email.
2. SMTP đã chấp nhận message.
3. Ứng dụng bị timeout trước khi trả response.
4. Client không biết kết quả và gửi lại request.
5. Email thứ hai được tạo và gửi.

Để giảm trùng lặp, có thể dùng idempotency key:

§§§java
public SendResult sendOnce(
        String idempotencyKey,
        MailCommand command
) {
    SendRecord existing = sendRecordRepository
            .findByIdempotencyKey(idempotencyKey)
            .orElse(null);

    if (existing != null) {
        return existing.toResult();
    }

    // Cần unique constraint và cơ chế claim/locking phù hợp
    // để xử lý hai request đồng thời dùng cùng key.
    return performAndRecordSend(idempotencyKey, command);
}
§§§

Đây là phác thảo; chỉ truy vấn rồi insert không đủ chống race khi hai request đồng thời cùng dùng key. Cần unique constraint, transaction và cách xử lý conflict/claim rõ ràng.

Idempotency trong ứng dụng cũng không biến SMTP thành exactly-once. Nếu server đã nhận email nhưng ứng dụng chưa ghi được kết quả, record có thể vẫn ở trạng thái không chắc chắn. Hãy định nghĩa trạng thái như §PENDING§, §SUBMITTING§, §ACCEPTED_BY_SMTP§, §FAILED§ và §UNKNOWN§ nếu nghiệp vụ cần phân biệt kết quả không xác định.

## 12. Theo dõi trạng thái và log khi gửi đồng bộ

Ngay cả khi gửi trực tiếp, vẫn nên có một message ID nội bộ để liên kết log và yêu cầu.

Ví dụ log cấu trúc:

§§§text
messageId=mail-2026-001
notificationType=ADMIN_TEST
recipientDomain=example.net
durationMs=842
smtpOutcome=ACCEPTED
errorType=none
§§§

Nếu lỗi:

§§§text
messageId=mail-2026-002
notificationType=ADMIN_TEST
durationMs=5000
smtpOutcome=FAILED
errorType=MailSendException
§§§

Các trường nên cân nhắc:

- Message ID nội bộ.
- Notification type.
- Thời gian bắt đầu/kết thúc và duration.
- Kết quả SMTP theo ngữ nghĩa chính xác.
- Loại exception và mã lỗi đã phân loại.
- Recipient đã được che/mã hóa hoặc chỉ log domain khi phù hợp.
- Template version và locale nếu cần truy xuất.

Không log SMTP password, authentication token, toàn bộ MIME source hoặc payload nhạy cảm. Log đủ để điều tra mà không sao chép dữ liệu riêng tư vào hệ thống logging.

### Metric hữu ích

Theo dõi:

- mail_send_total theo kết quả và loại thông báo.
- mail_send_duration histogram/percentile.
- mail_send_failure_total theo loại exception.
- Số request hiện đang chờ SMTP.
- Tỷ lệ timeout.
- Số lần retry thủ công hoặc gửi lại.
- Tỷ lệ gửi trùng nếu hệ thống có phát hiện.

Nếu gửi đồng bộ trong web request, liên hệ metric gửi mail với HTTP latency và thread pool utilization để biết tác động lên toàn ứng dụng.

## 13. Cách trả kết quả cho caller

Không nên trả một boolean mơ hồ nếu caller cần xử lý nhiều trạng thái. Có thể định nghĩa kết quả:

§§§java
public record SendResult(
        String messageId,
        Status status,
        String errorCode
) {
    public enum Status {
        SMTP_ACCEPTED,
        FAILED,
        UNKNOWN
    }

    public static SendResult accepted(String messageId) {
        return new SendResult(messageId, Status.SMTP_ACCEPTED, null);
    }

    public static SendResult failed(String messageId, String errorCode) {
        return new SendResult(messageId, Status.FAILED, errorCode);
    }
}
§§§

Đây là model minh họa. Nếu §send§ trả về bình thường, có thể trả §SMTP_ACCEPTED§. Nếu lỗi rõ ràng trước khi server nhận message, trả §FAILED§. Nếu timeout xảy ra ở thời điểm kết quả không xác định, cân nhắc §UNKNOWN§ để không khuyến khích retry mù.

Ở tầng HTTP, ánh xạ kết quả theo hợp đồng API. Ví dụ endpoint test SMTP có thể trả §200§ khi SMTP chấp nhận, §502§ hoặc §503§ khi dịch vụ gửi không khả dụng, tùy thiết kế. Không nên biến lỗi SMTP thành §500§ không có mã lỗi hữu ích hoặc để lộ chi tiết credential.

## 14. Kết hợp gửi đồng bộ với nghiệp vụ quan trọng

Hãy xác định email có vai trò gì đối với kết quả nghiệp vụ.

### Email chỉ là thông báo phụ

Ví dụ người dùng tạo đơn hàng và email chỉ để xác nhận. Nếu SMTP lỗi, đơn hàng vẫn hợp lệ. Trong trường hợp này, gửi đồng bộ rồi ném exception có thể khiến API báo lỗi dù đơn hàng đã được lưu. Người dùng có thể thử tạo đơn lần nữa và tạo đơn trùng.

Một thiết kế tốt hơn là:

- Commit đơn hàng.
- Ghi yêu cầu email trong outbox cùng transaction.
- Worker gửi sau.
- Nếu gửi lỗi, retry theo chính sách.
- API trả kết quả tạo đơn độc lập với trạng thái SMTP.

### Email là kết quả chính của thao tác

Ví dụ công cụ quản trị “Gửi email thử nghiệm” chỉ hoàn tất khi SMTP chấp nhận message. Gửi đồng bộ phù hợp vì chính việc gửi là mục tiêu của thao tác. Nếu lỗi, người dùng cần biết ngay để sửa cấu hình hoặc thử lại.

### Email có tác động bảo mật hoặc thời hạn

Email đặt lại mật khẩu, mã xác minh hoặc thông báo bảo mật có thể cần độ trễ thấp, nhưng cũng cần khả năng chống spam, rate limit, idempotency và bảo vệ token. Không nên chọn sync chỉ vì email “quan trọng”. Hãy đánh giá yêu cầu về latency, độ tin cậy, retry và tác động khi SMTP tạm thời không khả dụng.

## 15. Một ví dụ gửi đồng bộ có giới hạn và xử lý lỗi

Ví dụ dưới đây dành cho một endpoint quản trị gửi email thử nghiệm. Nó tạo message, gửi ngay và trả kết quả ở cấp SMTP:

§§§java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MailTestService {

    private final JavaMailSender mailSender;

    public MailTestService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public TestMailResult sendTest(String recipient) {
        String messageId = "test-" + java.util.UUID.randomUUID();

        try {
            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper =
                    new MimeMessageHelper(message, false, "UTF-8");

            helper.setFrom("admin@example.org");
            helper.setTo(recipient);
            helper.setSubject("SMTP configuration test");
            helper.setText(
                    "The application successfully submitted a test message."
            );

            mailSender.send(message);

            return new TestMailResult(
                    messageId,
                    TestMailResult.Status.SMTP_ACCEPTED,
                    null
            );
        } catch (MessagingException | MailException exception) {
            // Ghi nhận exception nội bộ; response không chứa secret.
            return new TestMailResult(
                    messageId,
                    TestMailResult.Status.FAILED,
                    "MAIL_SUBMISSION_FAILED"
            );
        }
    }
}
§§§

Kiểu kết quả:

§§§java
public record TestMailResult(
        String messageId,
        Status status,
        String errorCode
) {
    public enum Status {
        SMTP_ACCEPTED,
        FAILED
    }
}
§§§

Ví dụ minh họa cấu trúc xử lý. Trong ứng dụng thật, cần validate recipient, phân quyền endpoint, áp dụng rate limit, ghi duration và phân loại timeout/unknown outcome. Nếu muốn caller nhận exception để tầng trên xử lý, có thể để service ném lỗi đã được phân loại thay vì chuyển mọi lỗi thành một kết quả chung.

## 16. Checklist quyết định dùng gửi đồng bộ

Trước khi gọi §JavaMailSender.send§ trong luồng nghiệp vụ hoặc HTTP request, hãy trả lời:

| Câu hỏi | Nếu câu trả lời là “Có” |
|---|---|
| Số email mỗi thao tác thấp và bị giới hạn? | Sync có thể phù hợp. |
| Người gọi cần biết ngay SMTP chấp nhận hay từ chối? | Sync có lợi thế rõ. |
| Thời gian gửi nằm trong ngân sách latency đo được? | Có thể tiếp tục đánh giá sync. |
| Timeout SMTP và HTTP đã được cấu hình? | Có thể kiểm soát thời gian chờ. |
| SMTP lỗi có thể được biểu diễn rõ mà không làm sai trạng thái nghiệp vụ? | Sync dễ tích hợp hơn. |
| Không cần retry sau khi process restart? | Có thể không cần queue bền vững. |
| Số request đồng thời được giới hạn? | Giảm nguy cơ cạn thread. |
| Không gửi trong transaction database dài? | Tránh giữ lock khi chờ mạng. |

Nếu phần lớn câu trả lời là “Không”, hãy cân nhắc queue/outbox. Đặc biệt, nếu email là side effect của giao dịch quan trọng và phải được gửi lại sau sự cố, outbox thường là lựa chọn phù hợp hơn.

## 17. Ghi nhớ

- Gửi đồng bộ nghĩa là caller chờ §JavaMailSender.send(...)§ hoàn tất hoặc ném lỗi.
- Kết quả thành công thường chỉ xác nhận SMTP đã chấp nhận message; nó không chứng minh email đã tới inbox hoặc được đọc.
- Sync phù hợp với email ít, ngắn, thao tác thủ công/quản trị, ứng dụng nội bộ tải thấp và trường hợp caller cần phản hồi SMTP ngay.
- Không dùng request đồng bộ cho campaign, gửi hàng loạt hoặc thông báo phát sinh với lưu lượng cao.
- Đo p95/p99 latency, timeout, số request đồng thời và mức sử dụng thread trước khi đưa SMTP vào request path.
- Cấu hình connection/read/write timeout; xử lý §MailException§ rõ ràng và không báo thành công giả.
- Tránh gửi SMTP bên trong database transaction dài. Nếu gửi sau commit, nhớ rằng listener đồng bộ vẫn không có bảo đảm bền vững khi process dừng.
- §@Async§ chỉ chuyển công việc sang executor thread; nó không thay thế queue/outbox bền vững.
- Xử lý timeout có kết quả không chắc chắn và nguy cơ gửi trùng bằng message ID, idempotency và delivery record phù hợp.
- Với email là side effect của nghiệp vụ quan trọng, transactional outbox giúp lưu yêu cầu gửi cùng transaction và cho worker retry sau.
- Theo dõi thời gian gửi, kết quả SMTP, loại lỗi và ảnh hưởng tới HTTP latency; không log credential hoặc payload nhạy cảm.

Hãy chọn gửi đồng bộ khi việc chờ SMTP là một phần chấp nhận được của thao tác và caller cần biết kết quả submit ngay. Khi email cần được gửi bền vững, retry sau sự cố hoặc không được làm chậm luồng nghiệp vụ chính, hãy lưu yêu cầu gửi và xử lý bằng worker.
