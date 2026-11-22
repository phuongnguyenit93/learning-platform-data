# Tách mail service khỏi controller hoặc domain service

## 1. Vì sao việc gửi email cần một ranh giới riêng?

Trong **Spring Framework Mail**, cách gửi email đơn giản nhất là tạo **SimpleMailMessage** rồi gọi **JavaMailSender.send(...)**. API ngắn gọn khiến developer dễ viết mã SMTP trực tiếp trong controller hoặc domain service. Cách đó có thể hoạt động khi ứng dụng nhỏ, nhưng khi cần kiểm thử, thay đổi SMTP provider, gửi nhiều loại thông báo hoặc xử lý lỗi mạng, mã nghiệp vụ sẽ phụ thuộc chặt vào hạ tầng email.

Ví dụ một thao tác đăng ký tài khoản gồm những trách nhiệm khác nhau:

1. **HTTP controller** nhận request, xác thực dữ liệu đầu vào và gọi use case.
2. **Application service** điều phối đăng ký tài khoản, repository và yêu cầu thông báo.
3. **Domain model/domain service** thực thi quy tắc đăng ký, trạng thái và invariant.
4. **Mail service/adapter** dựng email rồi tương tác với JavaMailSender và SMTP server.

**Tách mail service** nghĩa là chuyển phần dựng/gửi email sang một thành phần chuyên trách, để controller không phải biết SMTP và domain không phải biết MimeMessage, host, port, username, retry hoặc thư viện Jakarta Mail.

~~~mermaid
flowchart LR
    C[REST Controller] --> A[Application Service / Use Case]
    A --> D[Domain Model / Domain Service]
    A --> P[Mail Port / Notification Interface]
    P --> M[Spring Mail Adapter]
    M --> J[JavaMailSender]
    J --> S[SMTP Server]
~~~

Ranh giới này giữ **hướng phụ thuộc** rõ ràng: controller phụ thuộc use case; domain chứa quy tắc nghiệp vụ; application layer quyết định có cần yêu cầu gửi hay không; mail adapter quyết định giao tiếp SMTP như thế nào.

Đây là cách tổ chức trách nhiệm, không phải yêu cầu bắt buộc mọi ứng dụng Spring phải dùng Clean Architecture nhiều module. Với ứng dụng nhỏ, một Spring service chuyên gửi mail vẫn là bước cải thiện hữu ích.

## 2. Phản ví dụ: gửi trực tiếp từ controller

Một controller có thể viết:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/accounts")
public class AccountController {
    private final JavaMailSender mailSender;

    public AccountController(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @PostMapping("/welcome")
    public void welcome(@RequestParam String email) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("noreply@example.com");
        message.setTo(email);
        message.setSubject("Welcome!");
        message.setText("Thanks for joining.");
        mailSender.send(message);
    }
}
~~~

Đoạn code này **có thể gửi được email**, nhưng controller đang xử lý quá nhiều việc:

- Vừa diễn giải HTTP request vừa trực tiếp điều khiển SMTP.
- Tự chứa nội dung mail (From, Subject, Text), khó tái sử dụng khi đăng ký từ CLI, batch job hoặc message consumer.
- Phụ thuộc SimpleMailMessage và JavaMailSender; test controller khó tập trung vào HTTP behavior.
- Thời gian phản hồi HTTP phụ thuộc network, TLS, SMTP AUTH và tốc độ SMTP server.
- Lỗi SMTP dễ bị biến thành HTTP 500 dù thao tác nghiệp vụ có thể đã thành công.
- Khi thêm HTML, locale, template, unsubscribe hoặc provider khác, controller phình to.

Một rủi ro khác: nếu controller ghi database xong rồi gửi mail, lời gọi send ném exception có thể khiến client tưởng toàn bộ request thất bại dù bản ghi đã được lưu. Nếu gửi mail trước khi database commit, người dùng có thể nhận thông báo về dữ liệu vừa rollback.

**Giải pháp:** controller chỉ gọi application service. Việc gửi mail qua ranh giới riêng và thời điểm gửi phải được xác định theo hợp đồng nghiệp vụ.

## 3. Phản ví dụ: domain service phụ thuộc SMTP

Một domain service nên trả lời câu hỏi **quy tắc nghiệp vụ có hợp lệ không**, không phải **SMTP đang sử dụng cổng nào**. Ví dụ chưa hợp lý:

~~~java
@Service
public class OrderDomainService {
    private final JavaMailSender mailSender;

    public OrderDomainService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void confirm(Order order) {
        order.confirm();
        SimpleMailMessage message = new SimpleMailMessage();
        message.setTo(order.customerEmail());
        message.setSubject("Order confirmed");
        message.setText("Your order was confirmed.");
        mailSender.send(message);
    }
}
~~~

Đây là **coupling không mong muốn**: xác nhận đơn hàng phụ thuộc vào đường truyền và cấu hình SMTP. Domain test có thể thất bại vì email, không phải vì quy tắc Order. Khi đổi phương thức thông báo, domain phải thay đổi dù logic xác nhận đơn hàng vẫn như cũ.

Trong thiết kế DDD, domain có thể phát sinh **domain event** như OrderConfirmed để biểu diễn sự kiện nghiệp vụ đã xảy ra; một handler ở lớp ứng dụng hoặc infrastructure sẽ quyết định gửi email. Không nhất thiết phải dùng DDD đầy đủ để áp dụng nguyên tắc: **không để quy tắc nghiệp vụ thuần phụ thuộc adapter hạ tầng**.

## 4. Ranh giới trách nhiệm của các lớp

| Thành phần | Việc nên làm | Việc không nên làm |
|---|---|---|
| **Controller/HTTP adapter** | Parse request, validation, gọi use case, trả HTTP status | Tạo SimpleMailMessage, giữ SMTP secret, retry transport |
| **Application service** | Điều phối ca sử dụng, transaction, repository và chính sách thông báo | Tự mã hóa MIME/Base64, quản lý socket SMTP |
| **Domain model/service** | Invariant, trạng thái và quy tắc nghiệp vụ | Import Spring Mail/Jakarta Mail, đọc HTTP header |
| **Mail port** | Mô tả yêu cầu gửi bằng ngôn ngữ ứng dụng | Tiết lộ transport cụ thể khi không cần thiết |
| **Mail adapter** | Dựng nội dung, set header, gọi JavaMailSender, ánh xạ lỗi hạ tầng | Quyết định lại quy tắc đăng ký/đặt hàng |
| **Queue/outbox worker** | Lưu và chạy yêu cầu gửi, retry có kiểm soát, ghi trạng thái | Giả định SMTP có thể rollback theo DB transaction |

Phân biệt **“khi nào cần thông báo?”** và **“gửi qua SMTP như thế nào?”** giúp tránh lớp xử lý vừa làm nghiệp vụ vừa điều khiển transport.

## 5. Cách đơn giản: một MailService riêng

Với dự án Spring Boot nhỏ, có thể chuyển toàn bộ code tạo SimpleMailMessage sang service chuyên trách:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {
    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient, String displayName) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("welcome@example.com");
        message.setTo(recipient);
        message.setSubject("Welcome to our service");
        message.setText("Hello " + displayName + ", welcome!");
        mailSender.send(message);
    }
}
~~~

Application service chỉ gọi hàm có ý nghĩa nghiệp vụ:

~~~java
import org.springframework.stereotype.Service;

@Service
public class RegistrationApplicationService {
    private final AccountRepository accounts;
    private final WelcomeMailService welcomeMail;

    public RegistrationApplicationService(
            AccountRepository accounts,
            WelcomeMailService welcomeMail) {
        this.accounts = accounts;
        this.welcomeMail = welcomeMail;
    }

    public void register(String email, String displayName) {
        accounts.create(email, displayName);
        welcomeMail.sendWelcome(email, displayName);
    }
}
~~~

**AccountRepository** ở ví dụ là contract do ứng dụng tự định nghĩa. Code minh họa việc tách trách nhiệm, **chưa giải quyết ranh giới giao dịch DB–SMTP**: nếu DB đã commit nhưng mail lỗi, đăng ký có thể thành công một phần. Những phần sau trình bày cách xử lý tốt hơn khi thông báo quan trọng.

Controller gọn lại:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/registrations")
public class RegistrationController {
    private final RegistrationApplicationService registrations;

    public RegistrationController(
            RegistrationApplicationService registrations) {
        this.registrations = registrations;
    }

    @PostMapping
    public ResponseEntity<Void> register(
            @RequestBody RegistrationRequest request) {
        registrations.register(request.email(), request.displayName());
        return ResponseEntity.noContent().build();
    }

    public record RegistrationRequest(String email, String displayName) {
    }
}
~~~

Ví dụ trả **204 No Content** sau use case đồng bộ; HTTP status cụ thể phải theo hợp đồng API. Với API tạo tài khoản thực tế có thể trả **201 Created**. Nếu chỉ xếp job gửi thư và xử lý sau, **202 Accepted** có thể phản ánh việc yêu cầu đã được tiếp nhận. Không mã HTTP nào tự chứng minh người nhận đã đọc email.

Lợi ích trước mắt là có một nơi cập nhật From/subject/content, tái sử dụng từ nhiều use case, mock service khi test và đổi nội dung mail mà không sửa controller. Chưa cần tạo interface chỉ vì muốn “đúng kiến trúc”; chọn độ phức tạp vừa đủ.

## 6. Dùng interface: MailPort và SMTP adapter

Khi application layer cần tránh import Spring Mail, định nghĩa **mail port** với kiểu dữ liệu đơn giản:

~~~java
public record OutgoingMail(
        String recipient,
        String subject,
        String body) {
}

public interface MailPort {
    void send(OutgoingMail mail);
}
~~~

Adapter sử dụng JavaMailSender:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
public class SmtpMailAdapter implements MailPort {
    private final JavaMailSender sender;

    public SmtpMailAdapter(JavaMailSender sender) {
        this.sender = sender;
    }

    @Override
    public void send(OutgoingMail mail) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("notifications@example.com");
        message.setTo(mail.recipient());
        message.setSubject(mail.subject());
        message.setText(mail.body());
        sender.send(message);
    }
}
~~~

Application service phụ thuộc contract:

~~~java
public class PasswordResetApplicationService {
    private final ResetTokenService tokens;
    private final MailPort mailPort;

    public PasswordResetApplicationService(
            ResetTokenService tokens,
            MailPort mailPort) {
        this.tokens = tokens;
        this.mailPort = mailPort;
    }

    public void requestReset(String email) {
        String link = tokens.createResetLink(email);
        mailPort.send(new OutgoingMail(
                email,
                "Reset your password",
                "Use this link to reset your password: " + link));
    }
}
~~~

**ResetTokenService** là contract minh họa. Hệ thống thực cần bảo vệ token, giới hạn thời hạn, chống lạm dụng/rate limit và không trả lời theo cách tiết lộ tài khoản có tồn tại hay không. Mục đích đoạn code là cho thấy application service chỉ yêu cầu **gửi email**, không cần hiểu SMTP.

~~~mermaid
flowchart TD
    REST[REST Controller] --> APP[Application Service]
    APP --> DOMAIN[Domain Rules]
    APP --> PORT[MailPort]
    SMTP[Spring SMTP Adapter] -.implements.-> PORT
    SMTP --> JMS[JavaMailSender]
    JMS --> PROVIDER[SMTP Provider]
~~~

Đổi transport có thể tạo adapter HTTP email API hoặc in-memory fake khi test mà không thay domain. Tuy nhiên contract vẫn cần biểu diễn đủ thông tin quan trọng: locale, template ID, attachment, header nghiệp vụ hoặc metadata nếu ứng dụng thật sự có nhu cầu.

## 7. Chọn contract ở đúng cấp độ

Không phải use case nào cũng nên tự ghép subject và body. Với email dùng template, locale hoặc branding riêng, contract nghiệp vụ dễ duy trì hơn:

~~~java
public interface AccountNotificationService {
    void welcomeAccount(String accountId, String recipient);
    void passwordChanged(String accountId, String recipient);
}
~~~

Implementation chọn template/ngôn ngữ rồi gọi MailPort chung:

~~~text
AccountApplicationService
          |
          v
AccountNotificationService
          |
          v
Template Renderer + MailPort
          |
          v
Spring SMTP Adapter
          |
          v
JavaMailSender
~~~

Trong cấu trúc này, application service yêu cầu **welcomeAccount**, notification service chọn nội dung/template, SMTP adapter chỉ thực hiện transport. Nếu ứng dụng chỉ có hai email text, một WelcomeMailService đơn giản có thể phù hợp hơn nhiều lớp trung gian. Mục tiêu là **giảm coupling có ý nghĩa**.

### Không truyền entity persistence trực tiếp vào mail adapter

Tránh thiết kế **sendWelcome(UserEntity user)** rồi cho mail adapter phụ thuộc entity JPA. Điều đó khiến mail layer phải biết cấu trúc database, dễ vướng lazy loading và dữ liệu thay đổi khi gửi bất đồng bộ.

Thay bằng snapshot DTO:

~~~java
public record WelcomeNotice(
        String accountId,
        String recipientEmail,
        String displayName,
        String localeTag) {
}
~~~

DTO nên chứa **chỉ những dữ liệu cần gửi**. Với password reset token hoặc thông tin nhạy cảm khác, phải áp dụng thời hạn, bảo vệ nơi lưu/queue và không ghi token vào log.
## 8. Gửi email lúc nào so với transaction?

Tách class gửi mail **chưa đủ** nếu application service gọi SMTP vào thời điểm không phù hợp. Ví dụ đơn hàng được lưu trong transaction, sau đó Spring Mail gửi thông báo. Database có thể rollback, trong khi SMTP server không thể “rollback” thông điệp đã chấp nhận.

Một lời gọi SMTP là **tác dụng phụ bên ngoài**. Nó không cùng tham gia giao dịch ACID của database nếu không có cơ chế đặc biệt; JavaMailSender không cung cấp two-phase commit với database.

### Tình huống 1: gửi khi database transaction chưa commit

~~~mermaid
sequenceDiagram
    participant A as Application service
    participant D as Database
    participant M as SMTP server
    A->>D: BEGIN; lưu đơn hàng
    A->>M: JavaMailSender.send()
    M-->>A: 250 accepted
    A->>D: COMMIT
    D-->>A: Commit thất bại, rollback
    Note over M: Email có thể đã vào SMTP queue
    Note over D: Đơn hàng không tồn tại
~~~

Khách hàng có thể nhận email “đơn hàng đã xác nhận” cho một đơn hàng không được commit. Kể cả khi **MailService** nằm ở class riêng, application service vẫn cần chọn **thời điểm** gửi.

### Tình huống 2: commit thành công nhưng SMTP lỗi

~~~mermaid
sequenceDiagram
    participant A as Application service
    participant D as Database
    participant M as SMTP server
    A->>D: Lưu đơn hàng
    D-->>A: COMMIT thành công
    A->>M: JavaMailSender.send()
    M-->>A: Lỗi kết nối / từ chối
    Note over D: Đơn hàng đã được lưu
    Note over A: Không thể rollback commit chỉ vì email lỗi
~~~

Nếu HTTP controller chuyển mọi exception thành lỗi “đặt hàng thất bại”, client có thể gửi lại yêu cầu và tạo đơn trùng. Cần định nghĩa rõ **thành công nghiệp vụ** (đơn hàng đã ghi) tách khỏi **trạng thái gửi thông báo**.

### Ba cách thường gặp

| Cách điều phối | Độ phức tạp | Ưu điểm | Rủi ro và giới hạn |
|---|---|---|---|
| **Gửi đồng bộ sau thao tác DB** | Thấp | Đơn giản, kết quả gửi được trả trong cùng luồng | Có khoảng trống crash; SMTP ảnh hưởng latency và response |
| **Spring event với AFTER_COMMIT** | Trung bình | Tránh gửi trước commit, giảm coupling giữa use case và listener | Event in-memory không bền vững; crash sau commit vẫn mất yêu cầu |
| **Transactional outbox + worker** | Cao hơn | Lưu ý định gửi cùng transaction; retry có trạng thái | Cần bảng/job store, worker, claim, retry, đối soát và chống trùng |

Không có một lựa chọn bắt buộc cho mọi ứng dụng. Email thử nghiệm hoặc thông báo không quan trọng có thể chấp nhận cách đơn giản. Email liên quan thanh toán, đơn hàng, quyền truy cập hoặc yêu cầu kiểm toán thường cần cơ chế bền vững hơn.

## 9. Dùng event sau commit để không gửi trước khi transaction hoàn tất

Đối với những email có thể chấp nhận mất khi process crash giữa commit và listener, **@TransactionalEventListener** là một cách tách ứng dụng và adapter gọn gàng.

Use case có thể phát một event sau khi thực thi quy tắc nghiệp vụ:

~~~java
public record AccountRegisteredEvent(
        String accountId,
        String email) {
}
~~~

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RegisterAccountUseCase {
    private final AccountRepository repository;
    private final ApplicationEventPublisher events;

    public RegisterAccountUseCase(
            AccountRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public String register(String email, String displayName) {
        Account account = repository.create(email, displayName);

        events.publishEvent(new AccountRegisteredEvent(
                account.id(),
                account.email()));

        return account.id();
    }
}
~~~

**AccountRepository** và **Account** là các contract/model minh họa của hệ thống nghiệp vụ. Trong thực tế cần validate email và áp dụng quy tắc đăng ký trước khi lưu.

Listener xử lý yêu cầu gửi sau commit:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class WelcomeEmailListener {
    private final AccountNotificationService notifications;

    public WelcomeEmailListener(AccountNotificationService notifications) {
        this.notifications = notifications;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterAccountRegistered(AccountRegisteredEvent event) {
        notifications.welcomeAccount(
                event.accountId(), event.email());
    }
}
~~~

**Điểm quan trọng:** listener được gọi khi transaction liên quan đã commit thành công. Theo mặc định, nếu không có transaction tương ứng, sự kiện của @TransactionalEventListener thường **không được xử lý**, trừ khi cấu hình **fallbackExecution**. Phải xác định event được publish trong phạm vi transaction thật, ví dụ lời gọi đi qua Spring transactional proxy chứ không phải gọi nội bộ tự bỏ qua proxy.

Sự kiện Spring kiểu này thường nằm trong bộ nhớ tiến trình. Nó **không phải hàng đợi bền vững**. Ứng dụng có thể crash sau database commit nhưng trước khi gửi mail; yêu cầu thông báo bị mất. Ngoài ra, nếu listener đồng bộ ném lỗi sau commit, phía gọi có thể nhận exception mặc dù dữ liệu nghiệp vụ đã được commit; không được coi exception đó là bằng chứng database rollback.

**AFTER_COMMIT giải quyết vấn đề thời điểm gửi, không tự giải quyết độ bền, retry hoặc exactly-once.**

### Domain event có cần biết MailService không?

Không. Sự kiện nên mô tả **điều đã xảy ra trong nghiệp vụ**, ví dụ AccountRegisteredEvent, OrderConfirmedEvent. Sự kiện không nên chứa JavaMailSender hoặc dữ liệu SMTP transport.

~~~text
Domain/Application:
  AccountRegisteredEvent(accountId, email)
                         |
                         v
  Notification listener / application handler
                         |
                         v
  AccountNotificationService
                         |
                         v
  MailPort -> SMTP adapter
~~~

Đôi khi event chỉ chứa **accountId**, còn handler truy vấn dữ liệu mới nhất; đôi khi event mang snapshot email cần thiết. Chọn dựa trên tính nhất quán dữ liệu và khả năng xử lý bất đồng bộ. Nếu email người dùng có thể thay đổi giữa lúc phát event và lúc gửi, dùng snapshot hoặc rõ ràng chấp nhận đọc địa chỉ mới theo chính sách.

## 10. Transactional outbox cho yêu cầu gửi đáng tin cậy

Với thông báo quan trọng, cần tránh khoảng trống **“database đã commit nhưng chưa kịp phát hành job email”**. Mô hình **transactional outbox** giải quyết bằng cách ghi cả dữ liệu nghiệp vụ và yêu cầu gửi trong cùng một transaction database.

~~~mermaid
sequenceDiagram
    participant U as Client
    participant A as Application Service
    participant D as Database + Outbox
    participant W as Mail Worker
    participant S as SMTP Server
    U->>A: Đăng ký / đặt hàng
    A->>D: BEGIN, lưu dữ liệu nghiệp vụ
    A->>D: Thêm outbox mail job
    D-->>A: COMMIT
    A-->>U: Trả kết quả nghiệp vụ
    W->>D: Claim job đang PENDING
    W->>W: Dựng nội dung mail
    W->>S: JavaMailSender.send()
    S-->>W: SMTP accepted hoặc lỗi
    W->>D: Lưu trạng thái / retry metadata
~~~

Application service ghi **ý định thông báo** thay vì gửi SMTP trong transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderUseCase {
    private final OrderRepository orders;
    private final MailOutboxRepository outbox;

    public PlaceOrderUseCase(
            OrderRepository orders,
            MailOutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public String placeOrder(PlaceOrderCommand command) {
        Order order = orders.place(command);

        outbox.enqueueOrderConfirmation(
                order.id(),
                order.customerEmail());

        return order.id();
    }
}
~~~

**OrderRepository**, **MailOutboxRepository**, **PlaceOrderCommand** và **Order** là các abstraction minh họa, không phải Spring Mail API có sẵn. Điều kiện cần là cả thao tác lưu order và thao tác ghi outbox tham gia **cùng transaction database**. Nếu outbox thuộc một DB khác, chỉ đặt hai lời gọi trong phương thức @Transactional không mặc nhiên khiến chúng atomic.

Worker về sau đọc outbox, dựng SimpleMailMessage hoặc MimeMessage rồi gọi mail adapter:

~~~text
mail_outbox (mô hình minh họa)
  id
  business_key
  message_type
  recipient
  payload_ref / serialized_payload
  status             PENDING / CLAIMED / SMTP_ACCEPTED / FAILED / UNKNOWN
  attempt_count
  next_attempt_at
  last_error_code
  created_at
  updated_at
~~~

Không phải lưu tất cả nội dung email dưới dạng plaintext. Có thể lưu reference đến dữ liệu được bảo vệ hoặc một payload đã giới hạn thông tin theo chính sách. Hệ thống cần kiểm soát quyền đọc queue, thời hạn giữ dữ liệu và loại bỏ token nhạy cảm khi hết hiệu lực.

### Outbox không đảm bảo exactly-once

~~~text
Worker nhận job
      |
      v
Gửi SMTP thành công, server trả 250
      |
      v
Worker crash trước khi cập nhật outbox
      |
      v
Job lại xuất hiện sau khi lease hết hạn
      |
      v
Worker có thể gửi lại cùng một email
~~~

Do đó, outbox thường giúp tiến gần đến mô hình **at-least-once xử lý yêu cầu gửi**, chứ không cam kết email được giao chính xác một lần. Có thể giảm trùng bằng business key, trạng thái per-recipient, kiểm soát retry, tra cứu event provider và idempotency key nếu provider hỗ trợ. **SMTP chuẩn không có idempotency key phổ quát** để bên nhận luôn loại bỏ bản sao trùng.

Nếu worker mất kết nối sau khi đã truyền toàn bộ dữ liệu nhưng trước khi đọc phản hồi, cần có trạng thái **SUBMISSION_UNKNOWN** hoặc tương đương. Việc retry lúc này có rủi ro gửi trùng; xử lý phụ thuộc độ quan trọng của email và khả năng đối soát với provider.

## 11. Gửi đồng bộ và bất đồng bộ: chọn theo yêu cầu nghiệp vụ

Một MailService tách riêng có thể được gọi **đồng bộ** hoặc thông qua **worker**. Tách class không tự khiến gửi mail chạy nền.

### Đồng bộ

~~~text
HTTP Request
  -> Controller
  -> Application Service
  -> MailPort / MailService
  -> JavaMailSender
  -> SMTP Server
  <- SMTP response
  <- HTTP response
~~~

Ưu điểm là đơn giản và có thể báo lỗi submission ngay trong request. Nhược điểm là SMTP latency làm request chậm, timeout có thể kéo dài và không dễ đảm bảo gửi lại khi process dừng. Phù hợp với tác vụ nhỏ có hợp đồng chấp nhận phụ thuộc vào việc gọi SMTP thành công.

### Bất đồng bộ qua @Async

Spring có thể chạy một phương thức qua task executor:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncNotificationDispatcher {
    private final MailPort mailPort;

    public AsyncNotificationDispatcher(MailPort mailPort) {
        this.mailPort = mailPort;
    }

    @Async("mailTaskExecutor")
    public void sendLater(OutgoingMail mail) {
        mailPort.send(mail);
    }
}
~~~

Để dùng @Async, ứng dụng phải cấu hình **@EnableAsync** và một executor phù hợp với tên **mailTaskExecutor** hoặc cơ chế cấu hình task execution tương ứng. Lời gọi phải đi qua **Spring proxy**; gọi nội bộ từ một phương thức khác của cùng bean thường không kích hoạt proxy-based async. Với phương thức @Async trả về void, lỗi trên worker thread không tự trở thành exception ở HTTP caller, nên phải có chiến lược ghi lỗi và quan sát; có thể dùng kiểu trả về phù hợp hoặc lưu trạng thái ở job store.

**@Async không phải hàng đợi bền vững.** Khi process restart/crash, tác vụ chỉ nằm trong bộ nhớ/executor có thể bị mất. Với thông báo cần bảo đảm không mất yêu cầu gửi, nên dùng queue/outbox bền vững và để worker xử lý, thay vì xem @Async là đủ.

### Bất đồng bộ qua database/broker

Với outbox hoặc message broker, HTTP request kết thúc sau khi **yêu cầu gửi đã được ghi bền vững**. Worker nhận và gửi mail sau. Khi trả **202 Accepted**, response nên nói rõ **yêu cầu đã được tiếp nhận để xử lý**; nó không khẳng định SMTP server hoặc mailbox đã nhận thư.

| Yêu cầu | Đồng bộ trực tiếp | @Async đơn giản | Outbox/queue bền vững |
|---|---|---|---|
| HTTP phải chờ SMTP | Có | Không, nếu task được dispatch thành công | Không |
| Lưu job qua process restart | Không tự có | Không tự có | Có, nếu được triển khai đúng |
| Cần worker/rate limit riêng | Không bắt buộc | Có thể cấu hình executor | Thiết kế rõ ràng hơn |
| Có thể retry có trạng thái | Cần tự làm | Cần tự làm | Thuận lợi hơn với job metadata |
| Ngăn mất yêu cầu giữa commit và gửi | Không tự bảo đảm | Không tự bảo đảm | Có thể bảo đảm ở ranh giới DB/outbox |
| Gửi exactly-once qua SMTP | Không | Không | Vẫn không tự đảm bảo |

Tách MailService khỏi controller giúp **đổi chiến lược dispatch** mà không phải thay HTTP contract và domain logic, miễn là contract ứng dụng mô tả đúng cam kết.
## 12. Kiểm thử từng lớp mà không phụ thuộc SMTP thật

Một lợi ích lớn của việc tách mail layer là **kiểm thử ở đúng ranh giới**. Mỗi loại test chỉ cần kiểm tra điều mà lớp tương ứng cam kết, thay vì mỗi bài test nghiệp vụ đều mở socket SMTP.

### Test application service bằng mock MailPort

Với **PasswordResetApplicationService** ở ví dụ trước, có thể dùng JUnit Jupiter và Mockito:

~~~java
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class PasswordResetApplicationServiceTest {
    @Mock
    ResetTokenService tokens;

    @Mock
    MailPort mailPort;

    private PasswordResetApplicationService service;

    @BeforeEach
    void setUp() {
        service = new PasswordResetApplicationService(tokens, mailPort);
    }

    @Test
    void sendsResetMessageThroughPort() {
        when(tokens.createResetLink("alice@example.test"))
                .thenReturn("https://example.test/reset/token-example");

        service.requestReset("alice@example.test");

        verify(mailPort).send(new OutgoingMail(
                "alice@example.test",
                "Reset your password",
                "Use this link to reset your password: "
                        + "https://example.test/reset/token-example"));
    }
}
~~~

Test này không phụ thuộc Spring ApplicationContext, JavaMailSender, SMTP credential hoặc network. Nó chứng minh **use case đã yêu cầu gửi thông báo đúng dữ liệu** qua port. Nó không chứng minh MIME đúng hoặc SMTP nhận thư, vì đó không phải trách nhiệm lớp đang test.

### Test SMTP adapter bằng mock JavaMailSender

Có thể kiểm tra adapter tạo đúng SimpleMailMessage:

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

@ExtendWith(MockitoExtension.class)
class SmtpMailAdapterTest {
    @Mock
    JavaMailSender sender;

    @InjectMocks
    SmtpMailAdapter adapter;

    @Test
    void createsExpectedSimpleMessage() {
        adapter.send(new OutgoingMail(
                "alice@example.test",
                "Status",
                "Your status has changed."));

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);

        verify(sender).send(captor.capture());

        SimpleMailMessage message = captor.getValue();
        assertArrayEquals(
                new String[] {"alice@example.test"},
                message.getTo());
        assertEquals("notifications@example.com", message.getFrom());
        assertEquals("Status", message.getSubject());
        assertEquals("Your status has changed.", message.getText());
    }
}
~~~

Test này chỉ kiểm tra **mapping DTO → SimpleMailMessage**. Không mở kết nối SMTP vì JavaMailSender là mock. Nếu adapter hỗ trợ HTML, attachment hoặc MIME alternative, có thể test **MimeMessage** với một mail sender/factory phù hợp và kiểm tra các part, hoặc dùng SMTP test server để capture thông điệp thật.

### Test HTTP controller riêng

Với **@WebMvcTest**, controller test nên giả lập application service hoặc một use-case interface. Mục tiêu là kiểm tra validation, JSON binding, HTTP code, exception mapping, authentication/authorization và hợp đồng response. Không nên bắt một test controller phải nạp SMTP transport chỉ vì controller trực tiếp inject JavaMailSender.

Với Spring Boot 3.3, có thể dùng **@MockBean** cho application service trong test MVC. Các phiên bản Spring/Boot mới hơn có thể dùng cơ chế mock bean khác; lựa chọn theo dependency thật của dự án.

### Test tích hợp SMTP khi nào?

Khi cần kiểm tra **giao thức SMTP và MIME thực**, dùng SMTP sink/test server trong test environment, không dùng provider production. Có thể quan sát:

- Sender/recipient envelope và header.
- Nội dung plain text, charset UTF-8, HTML và attachment.
- Tác động của cấu hình host, cổng, timeout, TLS/AUTH nếu test server hỗ trợ.
- Cách adapter phản ứng với phản hồi SMTP lỗi.

| Lớp cần kiểm chứng | Loại test phù hợp | Có cần SMTP server thật? |
|---|---|---|
| Domain invariant | Plain JUnit test | Không |
| Application service orchestration | Mock MailPort | Không |
| SMTP adapter mapping | Mock JavaMailSender/MimeMessage test | Không bắt buộc |
| Controller HTTP contract | MVC slice + mock use case | Không |
| SMTP protocol/transport integration | SMTP sink/test server | Cần test server, không cần provider production |
| Production delivery | Metrics/DSN/provider events | Cần hạ tầng production và chính sách quan sát |

Chỉ mock JavaMailSender không thể chứng minh SMTP AUTH, STARTTLS hoặc deliverability. Ngược lại, không cần SMTP integration test cho mọi biến thể quy tắc nghiệp vụ.

## 13. Thống nhất cách xử lý lỗi ở ranh giới mail

Spring Mail có thể phát sinh các ngoại lệ thuộc họ **MailException**, ví dụ **MailAuthenticationException** khi xác thực SMTP thất bại, **MailSendException** khi một hoặc nhiều thông điệp không gửi thành công, hoặc **MailPreparationException** khi chuẩn bị MIME lỗi.

Không phải mọi lỗi đều mang cùng ý nghĩa:

| Tình huống | Phạm vi quan sát | Hướng xử lý |
|---|---|---|
| Sai credential hoặc SMTP AUTH bị từ chối | Không có phiên gửi hợp lệ theo cấu hình | Cảnh báo cấu hình, không retry dồn dập bằng cùng secret |
| Kết nối không mở được | Chưa có bằng chứng submission thành công | Retry có giới hạn, backoff, quan sát provider |
| Server trả lỗi vĩnh viễn cho recipient | Phần giao thư tương ứng bị từ chối | Ghi lỗi theo recipient, xử lý địa chỉ hoặc chính sách |
| SMTP chấp nhận message | Submission thành công ở hop hiện tại | Theo dõi delivery riêng, không đánh dấu đã đọc |
| Timeout sau khi client truyền DATA | Có thể server đã nhận nhưng phản hồi bị mất | Lưu trạng thái không chắc chắn, cân nhắc rủi ro trùng khi retry |
| Template dữ liệu thiếu | Lỗi chuẩn bị thông điệp ở ứng dụng | Sửa dữ liệu hoặc template, tránh retry SMTP vô ích |

Ứng dụng có thể muốn che đi chi tiết framework bằng một lỗi ở application boundary:

~~~java
public class NotificationSubmissionException
        extends RuntimeException {

    public NotificationSubmissionException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Ví dụ adapter chuyển lỗi:

~~~java
import org.springframework.mail.MailException;

public void sendSafely(OutgoingMail mail) {
    try {
        send(mail);
    } catch (MailException ex) {
        throw new NotificationSubmissionException(
                "SMTP submission failed for mail request", ex);
    }
}
~~~

Ví dụ **sendSafely** chỉ minh họa ranh giới lỗi, không phải phương thức được Spring tạo tự động. Khi hệ thống cần phân biệt lỗi tạm thời/vĩnh viễn, nên giữ **loại lỗi nguyên nhân, mã SMTP và trạng thái theo người nhận** trong cấu trúc kết quả/exception có thể xử lý. Nếu gói tất cả thành một RuntimeException rồi bỏ nguyên nhân, khả năng retry chính xác sẽ suy giảm.

### Best-effort khác với bắt buộc gửi được

Một email marketing hoặc thông báo không thiết yếu có thể là **best effort**: application service hoàn tất nghiệp vụ, ghi nhận yêu cầu/lỗi email để xử lý sau. Một email xác nhận dùng để cấp quyền truy cập có thể đòi hỏi một hợp đồng mạnh hơn, nhưng SMTP vẫn không thể được đưa vào cùng transaction với database như thao tác nội bộ đơn giản.

Không nên catch mọi MailException rồi bỏ qua, trả lời rằng “đã gửi thành công” khi không có bằng chứng. Nếu cố ý không để email lỗi ảnh hưởng kết quả nghiệp vụ, hãy thể hiện rõ trạng thái trong job/event/metrics và quy trình xử lý. Nếu nghiệp vụ cần chờ SMTP accepted thì cần nói rõ HTTP response chỉ xác nhận **SMTP submission**, không có nghĩa inbox đã nhận thư.

## 14. Cấu hình mail không được rò sang controller hoặc domain

Những thuộc tính như SMTP host, cổng, username, password, STARTTLS, timeout và From address nên thuộc **infrastructure configuration** hoặc mail adapter, không phải controller/domain service.

Ví dụ cấu hình Spring Boot với placeholder:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: SMTP_USER_FROM_ENVIRONMENT
    password: SMTP_SECRET_FROM_SECRET_STORE
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

**Hai giá trị username/password trên chỉ là placeholder minh họa**, không phải credential thật. Trong deployment thực tế phải inject từ biến môi trường hoặc secret store được quản lý. Các timeout là ví dụ tính bằng mili giây.

Tại local/test, có thể thay sender bằng mock, fake hoặc trỏ SMTP host vào **Mailpit**, **MailHog** hay SMTP sink tương đương. Staging dùng sandbox, credential riêng và allowlist recipient; production dùng SMTP provider thật với TLS, secret và monitoring. Controller vẫn gọi cùng use case, không được chứa các nhánh kiểu “nếu profile dev thì gửi đi địa chỉ A”.

### Dùng @ConfigurationProperties cho sender identity

Địa chỉ From, reply-to hoặc tên hiển thị có thể được gom vào cấu hình riêng:

~~~yaml
app:
  notification:
    from-address: notifications@example.com
    reply-to-address: support@example.com
~~~

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notification")
public record NotificationMailProperties(
        String fromAddress,
        String replyToAddress) {
}
~~~

Spring Boot cần **đăng ký configuration properties** bằng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties, tùy kiến trúc ứng dụng. Mail adapter inject properties này, thay vì hard-code From và Reply-To ở nhiều controller.

From address phải nằm trong phạm vi **tài khoản/SMTP provider được phép gửi**. Việc JavaMailSender được xác thực thành công không tự bảo đảm mọi địa chỉ From đều được chấp nhận.

## 15. Tách trách nhiệm không có nghĩa bỏ qua bảo mật và quyền riêng tư

Mail adapter là một **ranh giới hạ tầng nhạy cảm** vì nó có khả năng gửi dữ liệu ra ngoài. Cần quy định rõ dữ liệu nào có thể được đưa vào email:

- **Validation recipient:** địa chỉ hợp lệ về cú pháp, người nhận có quyền nhận loại thông báo đó; không tin toàn bộ input từ HTTP request.
- **Authorization:** controller/use case chỉ cho phép người dùng kích hoạt email phù hợp quyền và trạng thái nghiệp vụ.
- **Không lộ người nhận:** không gom danh sách riêng tư vào To/Cc nếu từng người cần nhận một email độc lập; Bcc có ý nghĩa khác với cá nhân hóa.
- **Template encoding:** với email HTML, escape dữ liệu do người dùng nhập ở đúng ngữ cảnh, không nối HTML tùy tiện rồi tin rằng Spring Mail tự chống mọi injection nội dung.
- **Dữ liệu nhạy cảm:** hạn chế email chứa secret, token hoặc hồ sơ cá nhân. Nếu bắt buộc gửi token, áp dụng thời hạn ngắn và chính sách truy cập phù hợp.
- **Quản lý log:** dùng request ID, message ID, trạng thái và lỗi đã làm sạch. Không in SMTP password, OAuth bearer token hoặc toàn bộ MIME body.
- **Gửi qua kênh được bảo vệ:** SMTP submission có TLS đúng cấu hình và xác minh danh tính server theo yêu cầu provider.
- **Rate limit:** hạn chế API có thể kích hoạt mail để tránh spam, lạm dụng hệ thống hoặc làm provider khóa tài khoản.

Tách mail service giúp tập trung các quy tắc liên quan đến gửi email vào một nơi, nhưng **không thay thế** kiểm tra quyền ở application layer. Ví dụ, mail adapter không có đủ ngữ cảnh để quyết định một người dùng có được phép yêu cầu reset mật khẩu của tài khoản khác hay không; đó là trách nhiệm use case.

## 16. Tổ chức package trong một ứng dụng Spring Boot

Một cấu trúc dễ đọc, không cần nhiều module Gradle:

~~~text
com.example.account
├── web
│   ├── RegistrationController.java
│   └── RegistrationRequest.java
├── application
│   ├── RegisterAccountUseCase.java
│   ├── AccountNotificationService.java
│   └── AccountRegisteredEvent.java
├── domain
│   ├── Account.java
│   └── AccountRules.java
├── persistence
│   └── JpaAccountRepository.java
└── infrastructure
    └── mail
        ├── SmtpMailAdapter.java
        ├── MailTemplateRenderer.java
        └── NotificationMailProperties.java
~~~

Hoặc trong ứng dụng nhỏ:

~~~text
com.example.app
├── controller/RegistrationController.java
├── service/RegistrationService.java
├── service/WelcomeMailService.java
└── repository/AccountRepository.java
~~~

Không có một cách đặt tên package bắt buộc. Điều cần giữ là **đường đi rõ ràng từ nghiệp vụ đến hạ tầng**, và tránh vòng phụ thuộc giữa controller, domain, persistence và mail. Càng nhiều loại thông báo, template hoặc SMTP transport, việc tách interface/adapter càng có lợi.

### Khi nào chưa cần MailPort?

Nếu ứng dụng chỉ gửi một loại email text bằng một SMTP provider, mail service chuyên trách inject JavaMailSender có thể là đủ. Đặt MailPort chỉ để che hai dòng gọi send mà không có nhu cầu kiểm thử/phân tầng thêm có thể tăng số file và indirection. Khi application module cần độc lập infrastructure, muốn dùng fake mà không khởi động Spring, hoặc dự kiến nhiều transport, **MailPort** có lợi rõ rệt.
## 17. Lộ trình refactor từ controller gửi trực tiếp

Giả sử dự án đã có controller gọi JavaMailSender. Không nhất thiết phải chuyển sang kiến trúc nhiều module ngay lập tức. Có thể refactor theo những bước nhỏ, vẫn giữ behavior bên ngoài ổn định.

### Bước 1: xác định điểm gửi thư hiện tại

Tìm các nơi đang gọi JavaMailSender, MailSender, tạo SimpleMailMessage hoặc MimeMessage; cả controller, scheduled job, listener và domain service đều có thể đang gửi. Xác định **loại email**, **trigger**, **thông tin người nhận**, **nội dung**, **điều kiện gửi** và **thời điểm so với transaction**.

Ví dụ bảng phân loại trước refactor:

| Trigger | Email | Vị trí hiện tại | Vị trí dự kiến |
|---|---|---|---|
| Đăng ký tài khoản thành công | Welcome | RegistrationController | RegisterAccountUseCase → WelcomeMailService |
| Đổi mật khẩu | Security alert | AccountService | AccountNotificationService → MailPort |
| Đơn hàng commit | Order confirmation | OrderDomainService | Domain event/outbox → mail worker |
| Báo cáo định kỳ | Report with attachment | Scheduled job | ReportApplicationService → mail adapter |

### Bước 2: trích xuất MailService nhưng chưa đổi dispatch

Di chuyển logic **setFrom, setTo, setSubject, setText, send** vào MailService. Controller chuyển sang gọi application service. Bước này giúp tách transport khỏi HTTP mà chưa làm thay đổi đồng bộ hay bất đồng bộ, nên phạm vi thay đổi dễ kiểm soát hơn.

### Bước 3: tách contract nếu cần

Khi nhiều use case cần gửi cùng một loại email, chọn API có ý nghĩa:

~~~java
public interface OrderNotificationPort {
    void sendOrderConfirmation(
            String orderId,
            String recipientEmail);
}
~~~

Với nhiều loại email đa dạng, có thể dùng DTO chung kèm template/locale; với ứng dụng nhỏ, phương thức chuyên biệt thường dễ hiểu hơn generic API chứa rất nhiều tham số tùy chọn.

### Bước 4: quyết định ranh giới transaction

Nếu một email thể hiện sự kiện đã commit, không gửi khi dữ liệu còn có thể rollback. Có thể dùng event AFTER_COMMIT cho best effort hoặc outbox nếu cần bền vững. **Không vô tình thay đổi hợp đồng HTTP** chỉ vì di chuyển dòng send sang file khác: cần xác định khi nào ứng dụng coi use case thành công.

### Bước 5: bổ sung kiểm thử đúng lớp

Kiểm tra controller gọi application service, application service yêu cầu gửi qua mail port, adapter tạo message đúng định dạng. Chỉ dùng SMTP test server ở những test thật sự cần kiểm tra giao thức. Đối với nghiệp vụ quan trọng, kiểm tra thêm trường hợp database rollback, commit thành công nhưng mail lỗi, timeout và retry gây trùng.

### Bước 6: thêm quan sát và chính sách vận hành

Lưu request ID/job ID, email type, recipient theo chính sách bảo mật, kết quả submission và thời điểm. Đặt timeout, giới hạn tốc độ, batch size và retry theo khả năng provider. Tránh dùng log “Email sent successfully” làm bằng chứng email đã được phát đến Inbox.

## 18. Sai lầm thường gặp khi tách mail service

**1. Chỉ đổi tên class nhưng business vẫn phụ thuộc SMTP API.** Nếu một controller không còn gọi send nhưng application service phải dựng MimeMessage, hiểu MIME boundary và chẩn đoán mã SMTP, thì trách nhiệm hạ tầng vẫn chưa được tách đúng. Chuyển chi tiết dựng email vào adapter.

**2. Cho domain service gọi trực tiếp MailPort để gửi trong transaction.** Dù import interface thay vì JavaMailSender, vẫn có thể gửi trước khi transaction commit. Contract giúp đảo phụ thuộc, nhưng **không tự giải quyết timing và độ bền** của side effect.

**3. Tự động swallow exception ở MailService.** Bắt tất cả exception rồi bỏ qua có thể khiến use case hoặc hệ thống giám sát tưởng email đã được gửi. Nếu là best effort, cần có trạng thái và metric rõ ràng; nếu bắt buộc submission, phải truyền trạng thái phù hợp cho caller.

**4. Gọi @Async rồi nghĩ job chắc chắn không mất.** Task executor in-memory có thể bị mất khi process crash; một outbox/queue bền vững cần cơ chế lưu job và khôi phục. @Async cũng không tự giữ đúng transaction context hoặc đảm bảo thứ tự gửi.

**5. Chia sẻ một SimpleMailMessage mutable giữa nhiều request.** Spring bean MailService thường là singleton, nhưng mỗi lần gửi phải tạo đối tượng message riêng. Nếu đặt SimpleMailMessage làm field rồi sửa To/Subject ở từng request, các thread có thể ghi đè dữ liệu của nhau.

Ví dụ không nên làm:

~~~java
@Service
public class UnsafeMailService {
    private final JavaMailSender sender;
    private final SimpleMailMessage shared = new SimpleMailMessage();

    public UnsafeMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void send(String recipient) {
        shared.setTo(recipient); // Mutable state dùng chung.
        shared.setSubject("Hello");
        sender.send(shared);
    }
}
~~~

Một implementation đúng tạo **new SimpleMailMessage()** bên trong mỗi lần gửi; chỉ tái sử dụng bean JavaMailSender đã được cấu hình ổn định.

**6. Cố dùng one-size-fits-all DTO chứa mọi chi tiết.** Một class có hàng chục field nullable (recipient, cc, html, attachment, passwordResetToken, providerSpecificId...) khiến contract khó dùng đúng. Tách yêu cầu nghiệp vụ và yêu cầu transport khi cần, tránh lộ đặc thù nhà cung cấp vào domain.

**7. Mock JavaMailSender trong mọi test.** Nếu use case chỉ cần biết có yêu cầu gửi welcome email, mock MailPort/AccountNotificationService là đủ; không nên để test nghiệp vụ phụ thuộc nội dung MIME. Kiểm tra mapping MIME ở test adapter riêng.

**8. Tin rằng SMTP accepted là mailbox delivered.** JavaMailSender.send() thành công thường tương ứng submission server đã chấp nhận message; quá trình relay, mailbox delivery, spam filtering và người nhận đọc là các bước khác nhau. Nếu hệ thống cần biết kết quả phát, phải tích hợp nguồn sự kiện đáng tin ở hạ tầng mail.

**9. Chuyển mọi logic gửi mail sang controller helper tĩnh.** Static helper vẫn kéo HTTP và business layer phụ thuộc vào transport, khó inject, khó mock và khó thay cấu hình theo profile. Spring service hoặc một port/adapter có trách nhiệm rõ sẽ dễ kiểm soát hơn.

## 19. Chọn mức tách phù hợp

| Quy mô/bối cảnh | Thiết kế phù hợp | Điều cần ưu tiên |
|---|---|---|
| Ứng dụng nhỏ, vài email text | Một WelcomeMailService/NotificationMailService inject JavaMailSender | Không gọi SMTP từ controller hoặc domain model |
| Nhiều use case, cần test độc lập | MailPort interface + SmtpMailAdapter | Application layer phụ thuộc contract, test mock port |
| Email HTML, đa ngôn ngữ, template | Notification service + template renderer + adapter | Tách quyết định thông báo khỏi định dạng và transport |
| Email sau transaction DB | AFTER_COMMIT listener, nếu chấp nhận giới hạn in-memory | Không gửi khi DB còn có thể rollback |
| Email quan trọng, cần phục hồi qua restart | Transactional outbox + worker + mail adapter | Lưu yêu cầu gửi bền vững và retry có trạng thái |
| Nhiều provider/kênh notification | Port/gateway định tuyến theo chính sách | Giữ domain độc lập provider và hạn chế lộ secret |

Trong **Spring Framework Mail**, **SimpleMailMessage** và **JavaMailSender** là công cụ phù hợp để xây dựng adapter gửi email đơn giản. Chúng không nên trở thành dependency bắt buộc của HTTP controller hoặc domain service. Application layer nên quyết định **khi nào cần thông báo**, mail service quyết định **nội dung và cách gửi**, còn queue/outbox nếu có chịu trách nhiệm **duy trì công việc gửi và trạng thái thực thi**.

**Kết luận:** Bắt đầu bằng việc đưa lệnh gửi mail ra khỏi controller/domain service, tạo message độc lập trong mail service và dùng dependency injection. Khi nhu cầu tăng, thêm MailPort, notification abstraction, sự kiện sau commit hoặc transactional outbox theo mức độ tin cậy yêu cầu. Dù chọn cách nào, luôn giữ rõ sự khác nhau giữa **nghiệp vụ đã hoàn thành**, **SMTP đã chấp nhận thư** và **người nhận thật sự nhận/đọc email**.
