# Giới hạn quyền của tài khoản gửi

## 1. Vì sao tài khoản SMTP phải có quyền tối thiểu?

Trong **Spring Framework Mail**, ứng dụng thường dùng `JavaMailSender` để gửi email thông báo, xác nhận đơn hàng, hóa đơn hoặc liên kết kích hoạt tài khoản. Muốn gửi thư qua một SMTP submission server có xác thực, ứng dụng cần một định danh gửi, có thể là tài khoản dịch vụ kèm mật khẩu chuyên dụng, thông tin OAuth2 hoặc một cơ chế xác thực mà nhà cung cấp hỗ trợ.

Điểm quan trọng của bảo mật không chỉ là **mật khẩu có đủ mạnh** hoặc **kết nối SMTP có dùng TLS hay không**. Cần xác định: nếu thông tin xác thực bị lộ hoặc chức năng gửi thư bị lạm dụng, kẻ tấn công có thể làm được những gì với danh tính đó?

Nguyên tắc **least privilege — đặc quyền tối thiểu** yêu cầu tài khoản gửi chỉ có những quyền và phạm vi cần thiết để hoàn thành đúng nhiệm vụ nghiệp vụ:

- Chỉ có khả năng **gửi** những loại email mà ứng dụng được phép phát hành.
- Chỉ được dùng những địa chỉ người gửi (`From`/`Sender`) đã được tổ chức phê duyệt.
- Chỉ có thể gửi tới nhóm recipient, domain hoặc luồng nghiệp vụ được cho phép, nếu provider và kiến trúc hỗ trợ giới hạn này.
- Không có quyền đọc toàn bộ hộp thư, xóa thư, thay đổi cấu hình tenant hoặc quản trị người dùng nếu những quyền đó không cần thiết.
- Không được dùng làm tài khoản tương tác cho nhân viên, đăng nhập vào hệ thống nội bộ khác hoặc phục vụ nhiều ứng dụng không liên quan.
- Được giới hạn quota, tốc độ gửi, IP nguồn và phạm vi sử dụng khóa/token nếu nhà cung cấp hỗ trợ.

~~~text
Ứng dụng Spring
      |
      | SMTP AUTH / OAuth2
      v
Danh tính gửi chuyên dụng
      |
      +-- Được: gửi thông báo từ địa chỉ đã cấp
      |
      +-- Không: đọc mailbox của nhân viên
      +-- Không: quản trị tenant
      +-- Không: gửi với mọi From address
      +-- Không: dùng cho ứng dụng khác
      |
      v
SMTP submission service
      |
      v
Mail transfer và mailbox đích
~~~

**Giới hạn quyền không phải một cấu hình duy nhất của Spring Mail.** Nó là tập hợp chính sách ở nhiều lớp: identity provider, mail provider/SMTP relay, tài khoản gửi, hệ thống secrets, network, và kiểm tra nghiệp vụ trong ứng dụng.

## 2. Phân biệt ba lớp quyền khi gửi email

Khi người dùng nói “tài khoản gửi có quá nhiều quyền”, cần xác định đang nói đến lớp nào.

### 2.1. Quyền của định danh (identity permissions)

Đây là các quyền mà credential/token có thể dùng để truy cập dịch vụ:

- SMTP submission: gửi message qua một SMTP endpoint được phép.
- Mailbox access: đọc, xem, chuyển hoặc xóa email qua các giao thức/API khác.
- Delegated send: gửi thay hoặc gửi với tư cách một mailbox khác khi được cấp quyền.
- Quản trị tổ chức: tạo tài khoản, thay đổi mail flow/rule hoặc cấp quyền cho danh tính khác.

Một tài khoản có thể có khả năng SMTP submission nhưng không cần quyền đọc mailbox. Tuy nhiên, không thể suy luận từ việc ứng dụng **chỉ gọi SMTP** rằng credential **chỉ có quyền gửi**. Nếu cùng password còn dùng được cho IMAP, POP3, webmail hoặc API khác, phạm vi thực tế vẫn lớn hơn nhu cầu.

### 2.2. Quyền của sender identity và mail flow

Một SMTP account được xác thực thành công chưa chắc được phép:

- Đặt bất kỳ địa chỉ nào trong header `From:`.
- Dùng mọi sender alias.
- Gửi thay hộp thư của người khác.
- Relay tới mọi domain bên ngoài.
- Vượt quota hoặc chính sách gửi marketing/bulk.

Các giới hạn như **verified sender**, **Send As**, **Send on Behalf**, domain restriction, permitted recipient và sender rewriting là chính sách do hệ thống mail/provider kiểm soát. Tên quyền cụ thể thay đổi theo nhà cung cấp.

### 2.3. Quyền thực hiện nghiệp vụ trong ứng dụng

Ngay cả khi nhà cung cấp cho phép gửi đến mọi email hợp lệ, ứng dụng không nên biến nó thành một API “gửi bất kỳ nội dung đến bất kỳ người nhận”.

Ví dụ, endpoint dành cho xác nhận đơn hàng chỉ nên:

1. Xác thực người thực hiện hoặc sự kiện nghiệp vụ.
2. Xác định đơn hàng mà họ được phép thao tác.
3. Lấy recipient từ nguồn dữ liệu đáng tin cậy.
4. Chọn template đã được phê duyệt.
5. Tạo job gửi có mục đích và giới hạn rõ ràng.

**Sender account permissions** và **application authorization** bổ sung cho nhau. Provider khóa những gì credential có thể làm; ứng dụng khóa *ai được yêu cầu gửi email nào, tới ai, khi nào*.

## 3. Mô hình đe dọa: điều gì xảy ra nếu tài khoản gửi bị lộ?

Một số rủi ro thực tế:

| Rủi ro | Nếu dùng tài khoản quá quyền | Nếu áp dụng least privilege |
|---|---|---|
| Credential bị lộ trong log/CI | Có thể gửi thư, đọc mailbox hoặc truy cập dịch vụ khác | Chỉ có phạm vi gửi hẹp, dễ thu hồi |
| Kẻ tấn công lạm dụng API gửi | Gửi spam/phishing số lượng lớn | Rate limit, template policy, recipient restrictions và quota hạn chế tác động |
| Giả mạo người gửi | Có thể gửi như nhiều cá nhân/phòng ban | Chỉ được gửi từ sender identity được cấp |
| Ứng dụng staging dùng nhầm secret production | Có thể gửi thư thật tới khách hàng | Tách credential/environment, sandbox hoặc recipient restriction |
| Một ứng dụng bị xâm nhập | Tất cả hệ thống cùng dùng chung credential bị ảnh hưởng | Mỗi ứng dụng/dịch vụ có credential riêng |
| Token còn hiệu lực sau khi nhân sự rời công ty | Định danh cá nhân gây phụ thuộc và khó thu hồi | Service identity được quản lý theo vòng đời workload |
| Admin credential được dùng để gửi | Xâm nhập mail sender có thể leo thang quyền quản trị | Không cấp quyền quản trị cho gửi SMTP |

Ví dụ chống chỉ định:

~~~text
Production Spring Boot app
       |
       +-- dùng tài khoản email của admin hệ thống
                  |
                  +-- gửi email
                  +-- đọc mailbox
                  +-- quản trị tài khoản
                  +-- đổi chính sách mail
                  +-- đăng nhập hệ thống khác
~~~

Một lỗi cấu hình hay lộ secret nhỏ trong ứng dụng có thể trở thành sự cố lớn hơn nếu định danh bị gắn nhiều đặc quyền.

Thiết kế nên hướng đến:

~~~text
Production Spring Boot app
       |
       +-- production-notifier identity
                  |
                  +-- chỉ gửi mail theo phạm vi được cấp
                  +-- không có mailbox admin
                  +-- không có quyền cấp quyền mới
                  +-- không dùng cho staging/dev
~~~

## 4. Tạo danh tính gửi riêng cho từng ứng dụng và môi trường

Đừng dùng tài khoản email cá nhân của developer, nhân viên hỗ trợ hoặc administrator làm SMTP sender cho production. Một định danh gửi chuyên dụng giúp:

- Chặn hoặc thu hồi credential của ứng dụng mà không ảnh hưởng đăng nhập của nhân viên.
- Phân biệt lưu lượng gửi của ứng dụng A và B.
- Áp quota theo ứng dụng hoặc luồng nghiệp vụ.
- Theo dõi audit: message nào đến từ service nào.
- Áp sender policy và rotate secret độc lập.
- Ngăn staging/dev vô tình gửi đến khách hàng thật.

Một mô hình phân tách:

| Môi trường/ứng dụng | Định danh gửi | Sender được phép | Recipient |
|---|---|---|---|
| Production — transactional mail | `prod-order-mailer` | `orders@example.com` | Khách hàng theo nghiệp vụ |
| Production — security notification | `prod-security-mailer` | `security@example.com` | Chủ tài khoản hợp lệ |
| Staging | `staging-mailer` | `staging@example.test` | Mailbox test hoặc sandbox |
| Development | `dev-mailer` hoặc SMTP sink | Địa chỉ giả | Không relay ra Internet |

Các tên ở bảng là ví dụ. Tài khoản thật và alias phải được cấp đúng theo cơ chế nhà cung cấp, không tự phát minh quyền gửi bằng cách đặt chuỗi `spring.mail.username`.

### Đừng dùng chung credential giữa các ứng dụng

Nếu ứng dụng quản lý đơn hàng và ứng dụng marketing dùng cùng SMTP username/password, một sự cố ở ứng dụng marketing có thể ảnh hưởng uy tín sender, quota và cả hoạt động gửi email đơn hàng.

Nên tách theo **độ nhạy cảm của nội dung, mức ưu tiên, chính sách và blast radius**, nhưng không nhất thiết tạo một account cho mọi template. Việc tạo quá nhiều account làm tăng chi phí quản lý; hãy lựa chọn mức phân tách theo rủi ro.

### Định danh không nhất thiết phải là mailbox đầy đủ

Một số provider hỗ trợ sender identity/API key/SMTP credential chỉ phục vụ submission, không có mailbox đọc thư. Nếu có lựa chọn này, nó thường phù hợp hơn cho các thông báo một chiều. Một số nền tảng doanh nghiệp yêu cầu mailbox hoặc service principal có quyền gửi; cần xem xét chính sách cụ thể trước khi cấp quyền.

Không nên tự động cấp mailbox access hoặc license/quyền quản trị ngoài mức cần thiết chỉ vì muốn gửi email.

## 5. Lập ma trận quyền tối thiểu trước khi cấp tài khoản

Trước khi cấu hình SMTP, có thể thống nhất một ma trận quyền:

| Hành động | Tài khoản mail ứng dụng |
|---|---|
| Xác thực tới SMTP endpoint được chọn | Cho phép |
| Gửi từ sender/alias đã được duyệt | Cho phép |
| Gửi từ mọi mailbox của tổ chức | Không cho phép |
| Đọc Inbox/IMAP/POP3 | Không cho phép trừ khi có nhu cầu riêng được phê duyệt |
| Truy cập webmail tương tác | Không cho phép nếu không cần |
| Thay đổi mailbox permission | Không cho phép |
| Tạo hoặc xóa account mail | Không cho phép |
| Quản lý domain/DNS | Không cho phép |
| Thay đổi mail-flow rule/connector | Không cho phép |
| Xem secret của ứng dụng khác | Không cho phép |
| Gửi từ môi trường staging tới khách hàng thật | Không cho phép |
| Gửi với tốc độ vô hạn | Không cho phép |

**Deny by default**: chỉ cấp quyền được nêu rõ là cần thiết. Nếu một vai trò mặc định của provider rộng hơn mục tiêu, hãy dùng custom role, scoped grant, policy hoặc sender identity khác **nếu nền tảng hỗ trợ**; không mặc định mọi provider có đúng cùng một tính năng phân quyền.

### Tách quyền kỹ thuật và quyền nghiệp vụ

Ví dụ provider chỉ hỗ trợ SMTP credential có thể gửi tới mọi recipient, không có recipient allowlist. Khi đó ứng dụng cần tự áp recipient restrictions, quota và audit. Nhưng quy tắc trong ứng dụng **không ngăn được người đã đánh cắp credential** dùng SMTP trực tiếp ngoài ứng dụng. Vì vậy chính sách provider/network hoặc một relay trung gian thực thi recipient restriction vẫn là lớp bảo vệ mạnh hơn khi khả thi.

## 6. Những giới hạn nào do SMTP và những giới hạn nào do provider quyết định?

SMTP là giao thức chuyển thư; bản thân nó không định nghĩa một mô hình RBAC chung cho mọi nhà cung cấp. Mô tả quyền trong UI của provider, IAM, service principal, verified sender, SMTP relay connector và mailbox ACL có thể rất khác nhau.

| Giới hạn | Spring Framework Mail | SMTP server/provider |
|---|---|---|
| Đặt username/password hoặc cơ chế AUTH | Cấu hình client | Xác thực credential và quyết định có chấp nhận |
| Chọn host/port/TLS | Cấu hình client | Yêu cầu TLS/chính sách kết nối |
| Chọn From/Sender/Reply-To | Dựng header | Cho phép, từ chối hoặc rewrite theo sender policy |
| Giới hạn người nhận theo nghiệp vụ | Ứng dụng kiểm tra | Có thể hỗ trợ recipient/domain policy |
| Chỉ cho phép tài khoản gửi, không đọc mail | Không kiểm soát từ Spring | Identity/mailbox/API permissions |
| Giới hạn IP nguồn hoặc network | Triển khai network | Firewall/relay allowlist/conditional access |
| Quota/throttling | Có thể giới hạn phía ứng dụng | Provider thực thi hạn mức cuối cùng |
| Quyền quản trị account/domain | Không liên quan JavaMailSender | Admin/RBAC/IAM của nền tảng |
| Audit của việc gửi | Log/metrics của ứng dụng | Submission/message trace của provider |

**Thay đổi `JavaMailSender` thành một API client khác không tự giải quyết least privilege.** Bất kể SMTP hay HTTP email API, credential/token vẫn cần phạm vi tối thiểu và chính sách chống lạm dụng.

## 7. Giới hạn sender: xác thực SMTP không đồng nghĩa được gửi với mọi From

Trong một thư MIME thường có nhiều giá trị liên quan tới người gửi:

- **SMTP AUTH identity:** danh tính được dùng để xác thực với submission server.
- **SMTP envelope sender (MAIL FROM):** địa chỉ sử dụng trong giao dịch SMTP, liên quan đường trả thư/bounce.
- **RFC 5322 From:** địa chỉ mà người nhận thường thấy trong giao diện email.
- **Sender:** một header có thể được dùng khi người thực tế gửi khác người được nêu ở From.
- **Reply-To:** địa chỉ nhận câu trả lời, không phải bằng chứng về quyền gửi.

Các giá trị này có liên quan nhưng **không bắt buộc trùng nhau ở mức giao thức**. Chính sách provider có thể yêu cầu chúng khớp, phải được xác minh hoặc được cấp delegated permission. Một server có thể từ chối, viết lại địa chỉ hoặc chấp nhận theo quy tắc riêng.

Ví dụ:

~~~text
Authenticated identity: order-mailer@example.com
Header From:            invoices@example.com
SMTP MAIL FROM:         bounces@example.com
Reply-To:               support@example.com
~~~

Mô hình này chỉ hợp lệ nếu nhà cung cấp cho phép sender identity tương ứng và doanh nghiệp có quyền sử dụng các domain/địa chỉ đó. **Đừng cho rằng đặt được `From` trong Java có nghĩa được quyền gửi với danh tính ấy.**

### Thiết lập From trong Spring Mail

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void composeReceipt(
        JavaMailSender sender,
        String recipient,
        String html) throws MessagingException {

    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(message, false, "UTF-8");

    helper.setFrom("orders@example.com");
    helper.setTo(recipient);
    helper.setReplyTo("support@example.com");
    helper.setSubject("Xác nhận đơn hàng");
    helper.setText(html, true);

    sender.send(message);
}
~~~

Ví dụ giả định `orders@example.com` đã được provider cho phép gửi. `Reply-To` không thay thế permission của `From`; ứng dụng cần xác thực địa chỉ trả lời và không lấy tùy ý từ request chưa được tin cậy.

### Send As và Send on Behalf

Một số nền tảng mailbox phân biệt:

| Khái niệm | Ý nghĩa thường gặp |
|---|---|
| `Send As` | Danh tính có thể gửi như mailbox/địa chỉ được cấp |
| `Send on Behalf` | Gửi thay mặt, có thể hiển thị thông tin đại diện trong client |
| Sender alias | Địa chỉ phụ có thể dùng trong những điều kiện cụ thể |
| Verified sender identity | Địa chỉ hoặc domain được provider xác minh và chấp nhận |

Không cấp quyền `Send As` trên toàn bộ mailbox của tổ chức nếu ứng dụng chỉ cần gửi từ một mailbox thông báo. Nếu bắt buộc phải cấp quyền delegated, giới hạn vào đúng mailbox mục tiêu, đúng service principal/account, đúng thời hạn và ghi audit.

### Tránh spoofing qua đầu vào ứng dụng

API gửi mail không nên nhận một giá trị `from` từ bất kỳ client rồi gán thẳng:

~~~java
// Không nên nếu request đến từ người dùng chưa được ủy quyền.
helper.setFrom(request.getFrom());
~~~

Thay vào đó, chọn sender từ cấu hình server theo loại thông báo:

~~~java
public enum NotificationKind {
    ORDER_RECEIPT,
    SECURITY_ALERT
}

public String senderFor(NotificationKind kind) {
    return switch (kind) {
        case ORDER_RECEIPT -> "orders@example.com";
        case SECURITY_ALERT -> "security@example.com";
    };
}
~~~

Cho phép một ứng dụng chọn giữa hai sender không có nghĩa một credential được phép gửi cả hai. Trong hệ thống phân quyền nghiêm ngặt, mỗi sender có thể tương ứng **một credential/client/adapter riêng**.

## 8. SMTP AUTH: bật đúng nơi, tắt nơi không cần

SMTP AUTH cho phép client xác thực khi nộp thư tới submission server. Nhưng nhiều tổ chức không muốn mọi tài khoản mail đều được phép SMTP AUTH vì thông tin xác thực có thể bị lạm dụng qua các client ngoài chính sách.

Nguyên tắc:

1. Chỉ bật khả năng SMTP submission cho danh tính hoặc connector thật sự cần.
2. Không bật SMTP AUTH trên toàn tenant nếu chỉ một ứng dụng cần và có cách giới hạn hẹp hơn.
3. Ưu tiên cơ chế xác thực mạnh, token có phạm vi phù hợp và vòng đời ngắn khi nền tảng hỗ trợ.
4. Nếu phải dùng password/app password, tạo credential riêng, lưu trong secret manager và rotate theo quy trình.
5. Không bật lại các giao thức legacy như IMAP/POP chỉ vì ứng dụng cần gửi SMTP.
6. Loại bỏ quyền/credential khi ứng dụng bị ngừng hoặc chuyển provider.

Một số mail provider không hỗ trợ SMTP AUTH bằng password cho tài khoản hoặc tenant trong các chế độ cấu hình nhất định; một số yêu cầu OAuth2 hoặc một relay connector khác. Hãy kiểm tra chính sách của nền tảng đang sử dụng, không giả định cặp username/password luôn được phép.

### Không đồng nhất MFA và app password

MFA bảo vệ đăng nhập tương tác, nhưng một số SMTP integration cũ dùng app password có thể không đi qua bước MFA cho từng lần gửi. App password, nếu nhà cung cấp còn cho phép, là **một secret có giá trị lâu dài** và phải được quản lý như mật khẩu mạnh:

- Tạo riêng cho service, không chia sẻ giữa người dùng/ứng dụng.
- Lưu ở secret store, không trong source.
- Giới hạn service/account và thu hồi ngay khi không còn cần.
- Theo dõi lần sử dụng bất thường.
- Ưu tiên OAuth2 hoặc mechanism bảo mật hiện đại khi khả dụng và phù hợp.

Không nói “có MFA rồi nên mật khẩu SMTP không đáng lo”; khả năng lạm dụng phụ thuộc phương thức SMTP AUTH thực tế.

## 9. OAuth2 scope và service principal cần được giới hạn

Khi nhà cung cấp hỗ trợ OAuth2 cho SMTP submission, việc thay password bằng access token giúp cải thiện khả năng quản lý vòng đời credential nhưng **không tự làm quyền nhỏ đi**.

Cần xác định:

- Token là **delegated** thay cho người dùng hay **application/service principal**?
- Quyền/scope nào thực sự cần cho SMTP submission?
- Token có thể dùng cho API đọc mail hoặc quản trị tenant không?
- Quyền ứng dụng được giới hạn vào mailbox/sender nào?
- Có consent/role assignment quá rộng không?
- Token hết hạn và được refresh bằng cơ chế gì?
- Secret hoặc private key dùng để lấy token được lưu, rotate và audit ra sao?

Một dịch vụ email API có thể hỗ trợ role `send-only` hoặc quyền riêng cho gửi; một nền tảng khác có thể yêu cầu cấp thêm mailbox-level access policy. **Không dùng một tên scope giả định chung cho mọi provider.** Phải sử dụng chính xác scope/audience, grant type và quyền mà tài liệu chính thức của provider cho biết.

### Principle of minimum token scope

Ví dụ về tư duy cấp quyền:

~~~text
Service principal: production-order-notifier
  |
  +-- Token audience: mail submission service
  +-- Allowed operation: submit/send transaction email
  +-- Sender/mailbox scope: orders@example.com
  +-- Lifetime: ngắn, làm mới có kiểm soát
  +-- No: read/list mailbox
  +-- No: user administration
  +-- No: tenant-wide delegated send
~~~

Sơ đồ là mục tiêu bảo mật, không phải cấu hình IAM có thể copy nguyên cho mọi hệ thống. Nếu provider **không thể giới hạn quyền tới một sender/mailbox**, cần ghi nhận rủi ro còn lại và cân nhắc identity khác, relay trung gian hoặc provider có cơ chế send-only hẹp hơn.

### Cẩn trọng khi dùng XOAUTH2 với Spring Mail

`JavaMailSenderImpl` dùng Jakarta Mail và có thể cấu hình các SMTP authentication mechanisms mà implementation hỗ trợ. Việc dùng XOAUTH2 đúng cách cần **token acquisition, refresh, scope, audience, expiry và cấu hình Jakarta Mail phù hợp**; chỉ đổi `spring.mail.password` thành một access token tĩnh không đủ cho hệ thống vận hành lâu dài.

Nếu token hết hạn sau một thời gian, ứng dụng phải có cơ chế cung cấp token mới cho từng lần xác thực/kết nối. Không nên ghi access token vào log, mail header hoặc exception message.

Một ví dụ khái quát về tính chất cấu hình SMTP AUTH:

~~~properties
# Mang tính minh họa: cấu hình cụ thể theo provider và Jakarta Mail.
mail.smtp.auth=true
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
mail.smtp.auth.mechanisms=XOAUTH2
~~~

Các thuộc tính trên **không tự cấp OAuth scope và không tự refresh token**. Phải dùng token provider integration phù hợp với implementation, và kiểm tra chính sách provider; không sao chép ví dụ để dùng production khi chưa thiết kế vòng đời token.

## 10. Secret management: không để credential trong source code

Ví dụ không nên:

~~~java
sender.setUsername("prod-mailer@example.com");
sender.setPassword("hard-coded-password");
~~~

Hoặc:

~~~yaml
spring:
  mail:
    username: prod-mailer@example.com
    password: plaintext-secret-committed-to-git
~~~

Các giá trị này có thể bị lộ qua git history, pull request, artifact build, container image, CI output hoặc bản sao môi trường phát triển.

### Spring Boot đọc credential từ secret injection

Ví dụ cấu hình ứng dụng (không chứa secret):

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Trong môi trường thực tế, các placeholder được thay từ environment, configuration integration hoặc secret manager được triển khai an toàn. **Environment variable không tự động bảo mật tuyệt đối**: những người/process có quyền đọc môi trường hoặc debug process vẫn có thể thấy nó. Nếu nền tảng có secret volume hoặc runtime secret injection với cơ chế rotate tốt hơn, nên đánh giá lựa chọn đó.

### Chính sách lưu trữ credential

| Kiểm soát | Lý do |
|---|---|
| Secret manager / protected secret store | Tránh nhúng password trong git/build artifact |
| Quyền đọc secret theo workload identity | Chỉ pod/service đúng được lấy secret |
| Không log password/token | Giảm khả năng lộ qua log pipeline |
| Masking trong CI/CD | Ngăn in giá trị secret trong build/deploy |
| Rotate có quy trình | Giới hạn vòng đời credential bị lộ |
| Thu hồi credential cũ | Ngăn ứng dụng cũ hoặc kẻ tấn công tiếp tục sử dụng |
| Tách dev/staging/prod secrets | Giảm blast radius và gửi nhầm |
| Audit khi ai đọc/cấp/thu hồi secret | Phát hiện bất thường và phục vụ điều tra |

### Rotation không chỉ là đổi password

Khi rotate credential cho Spring Mail:

1. Cấp credential mới có **cùng phạm vi quyền tối thiểu**.
2. Cập nhật secret store và deploy/reload cấu hình theo khả năng runtime.
3. Kiểm tra submission từ ứng dụng mới.
4. Thu hồi credential cũ sau khi đã bảo đảm cutover, theo chính sách bảo mật.
5. Kiểm tra các instance cũ không còn sử dụng secret bị thu hồi.
6. Xác nhận log/audit không hiển thị password/token.

Nếu provider cho phép có hai credential hoạt động song song trong khoảng chuyển tiếp, có thể dùng rotation không downtime. Nếu provider chỉ cho một password, cần lập kế hoạch phối hợp deployment/rolling restart và nhận diện lỗi xác thực sau rotate.

## 11. Kênh truyền TLS là bắt buộc nhưng không phải quyền hạn

Một credential có đặc quyền thấp vẫn có thể bị lộ nếu truyền qua kênh không được bảo vệ. Với SMTP submission hiện đại, nên dùng TLS theo chính sách nhà cung cấp.

Thông thường:

- **Port 587**: kết nối SMTP rồi nâng cấp sang TLS bằng STARTTLS.
- **Port 465**: kết nối TLS ngay từ đầu (implicit TLS) nếu provider hỗ trợ.
- **Port 25**: thường dùng trong mail transfer/relay; không nên mặc định dùng để submission của ứng dụng.

Đây là quy ước phổ biến, không phải điều kiện cứng cho mọi provider.

Ví dụ STARTTLS bắt buộc:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

`mail.smtp.starttls.required=true` yêu cầu quá trình nâng cấp lên TLS thành công, thay vì tiếp tục gửi nếu server không hỗ trợ. `mail.smtp.ssl.checkserveridentity=true` bật kiểm tra định danh hostname theo khả năng của Jakarta Mail provider, giảm nguy cơ kết nối sai endpoint.

Nếu provider yêu cầu implicit TLS, có thể phải cấu hình `mail.smtp.ssl.enable=true` với port tương ứng thay vì chỉ dựa vào STARTTLS.

**TLS bảo vệ đường truyền; nó không hạn chế mailbox nào tài khoản được đọc hay địa chỉ From nào được gửi.** Vẫn phải áp least privilege ở identity/provider.

### Không nới lỏng kiểm tra chứng chỉ để “sửa” lỗi gửi

Không nên:

~~~properties
# Không dùng cấu hình bỏ qua xác minh chứng chỉ trong production.
mail.smtp.ssl.trust=*
~~~

Tin mọi chứng chỉ có thể che lỗi DNS/PKI hoặc cho phép kết nối tới endpoint không đúng. Hãy cấu hình trust store/CA và hostname phù hợp; nếu server nội bộ dùng CA riêng, cấp trust chain đúng thay vì bỏ toàn bộ bước xác minh.

## 12. Hạn chế địa chỉ đích và domain người nhận

Một tài khoản chỉ có quyền SMTP submission vẫn có thể bị lạm dụng để gửi spam hoặc phishing tới rất nhiều người nếu provider không giới hạn recipient. Do đó cần xác định **ai có thể kích hoạt việc gửi** và **được gửi tới nhóm người nhận nào**.

Một số nhóm chính sách:

| Chính sách | Ví dụ | Lớp thực thi phù hợp |
|---|---|---|
| Allowlist domain trong staging | Chỉ gửi tới `example.test` hoặc domain mailbox test | Ứng dụng + SMTP relay nếu hỗ trợ |
| Chỉ gửi tới tài khoản đã xác minh | Email trong hồ sơ có trạng thái verified | Application authorization/data layer |
| Chặn địa chỉ ngoài tổ chức với email nội bộ | Chỉ `@example.com` | Provider/relay/ứng dụng |
| BCC recipient bị kiểm soát | Không cho client tùy ý thêm BCC | Application model/template |
| Giới hạn tổng số recipient | Tối đa N recipient theo một message/job | App + provider quota |
| Danh sách suppression/opt-out | Không gửi thông báo tùy chọn tới người đã unsubscribe | Business policy |
| Chặn domain có rủi ro | Theo abuse policy | Mail provider/gateway |

### Cần phân biệt thông báo giao dịch và marketing

Thông báo bảo mật hoặc xác nhận giao dịch có chính sách người nhận khác bản tin marketing. Không nên cho một endpoint gửi email marketing sử dụng cùng tài khoản/credential và quota của email bảo mật nếu việc quá tải có thể làm chậm các thông báo quan trọng.

Với email marketing, còn có yêu cầu về consent, unsubscribe và quy định pháp luật tùy địa bàn; đây là các chính sách bổ sung, không phải quyền tự động của SMTP account.

### Bảo vệ staging và development

Một lỗi phổ biến là chạy lệnh kiểm thử bằng dữ liệu production và gửi email thật:

~~~text
Staging application
     |
     +-- SMTP credential production
     |
     +-- Customer data copy
     |
     v
Gửi email cho khách hàng không chủ đích
~~~

Nên dùng **SMTP sink**, sandbox provider hoặc credential có recipient restrictions riêng cho staging/dev. Một điều kiện `if (profile == "test")` trong code không phải hàng rào vững chắc duy nhất; cấu hình provider/relay không cho gửi ra domain ngoài là lớp bảo vệ tốt khi có thể.

## 13. Thực thi recipient allowlist ở lớp Spring

Khi policy nghiệp vụ chỉ cho gửi trong một tập domain, có thể áp kiểm tra trước khi tạo `MimeMessage`.

Ví dụ service validation (Java 17+):

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public final class RecipientPolicy {
    private final Set<String> allowedDomains;

    public RecipientPolicy(Set<String> allowedDomains) {
        this.allowedDomains = Set.copyOf(
                Objects.requireNonNull(allowedDomains));
    }

    public InternetAddress requireAllowed(String raw)
            throws AddressException {
        if (raw == null || raw.isBlank()) {
            throw new AddressException("Recipient is required");
        }

        InternetAddress address = new InternetAddress(raw, true);
        address.validate();

        String mailbox = address.getAddress();
        if (mailbox == null) {
            throw new AddressException("Recipient has no mailbox");
        }
        int atIndex = mailbox.lastIndexOf('@');
        if (atIndex < 1 || atIndex == mailbox.length() - 1) {
            throw new AddressException("Invalid mailbox");
        }

        String domain = mailbox.substring(atIndex + 1)
                .toLowerCase(Locale.ROOT);
        if (!allowedDomains.contains(domain)) {
            throw new SecurityException(
                    "Recipient domain is not permitted");
        }
        return address;
    }
}
~~~

Sử dụng:

~~~java
RecipientPolicy policy = new RecipientPolicy(
        Set.of("example.test", "qa.example.test"));

InternetAddress recipient =
        policy.requireAllowed(request.recipient());

helper.setTo(recipient);
~~~

Ví dụ này thực hiện **so khớp domain chính xác**, không cho phép subdomain tự động và không cố phân tích toàn bộ các biến thể địa chỉ quốc tế. Nếu chính sách hỗ trợ IDN, cần chuẩn hóa domain bằng IDNA và kiểm tra canonical form theo quy tắc của tổ chức. Với hệ thống có yêu cầu bảo mật cao, nên dùng một address-validation library/policy được kiểm thử kỹ càng.

**Không nên kiểm tra bằng `endsWith("example.com")`** vì có thể chấp nhận nhầm `notexample.com`. Cũng không nên dùng `raw.contains("@example.com")` vì input có thể có display name hoặc định dạng phức tạp. Hãy parse mailbox và áp chính sách trên domain đã được chuẩn hóa.

### Không tin recipient do trình duyệt tự chọn

Trong API gửi xác nhận đơn hàng:

~~~java
// Không nên lấy thẳng recipient từ request công khai.
mailService.sendOrderConfirmation(request.getEmail(), orderId);
~~~

Thay vào đó:

~~~java
Order order = orderService.getAuthorizedOrder(
        authenticatedUserId, orderId);

String recipient = order.getVerifiedContactEmail();
mailService.sendOrderConfirmation(recipient, orderId);
~~~

Ở ví dụ này, `getAuthorizedOrder` và `getVerifiedContactEmail` là API nghiệp vụ minh họa. Nếu đơn hàng có thể được gửi cho người nhận khác, phải có quy trình ủy quyền rõ ràng thay vì cho phép ghi bất kỳ địa chỉ nào vào request.

### Đừng coi allowlist trong ứng dụng là đủ khi credential bị lộ

Một kẻ đánh cắp SMTP username/password có thể không đi qua `RecipientPolicy` trong Java. Nếu yêu cầu kiểm soát bắt buộc phải tồn tại ngay cả khi application host bị xâm nhập, áp cùng giới hạn ở **provider/relay/network** hoặc thay đổi mô hình cấp credential.

## 14. Giới hạn số lượng email, connection và quota gửi

Least privilege không chỉ là một danh sách hành động; còn là **giới hạn năng lực lạm dụng**.

Ví dụ một tài khoản gửi email giao dịch có thể cần:

- Tối đa một số lượng message/phút theo tải bình thường.
- Giới hạn message/day hoặc recipient/day tùy provider.
- Giới hạn số kết nối SMTP đồng thời.
- Giới hạn số recipient cho mỗi message.
- Giới hạn kích thước body và attachment.
- Giới hạn số lần gửi cùng loại email cho một account trong một khoảng thời gian.
- Cảnh báo khi tốc độ gửi tăng bất thường.

Giới hạn cần được chọn theo năng lực thực tế và SLA, không lấy một con số cố định cho mọi ứng dụng.

### Concurrency không phải rate

Nếu executor mail có 8 worker, điều đó chỉ giới hạn **số task đồng thời**. Nếu mỗi task gửi rất nhanh, 8 worker vẫn có thể gửi nhiều email trong một giây và vượt quota.

~~~text
Application / Outbox
        |
        v
Recipient + template policy
        |
        v
Rate limiter (message/giây, quota theo account)
        |
        v
Mail executor (concurrency)
        |
        v
SMTP server/provider
~~~

Trong ứng dụng có nhiều replica, 8 worker mỗi replica nhân với 5 replica có thể tạo 40 SMTP calls đồng thời. Nếu provider quota áp cho toàn bộ sender account, cần một giới hạn **toàn cụm** hoặc dùng một dispatcher tập trung; giới hạn cục bộ mỗi JVM không tự bảo đảm quota chung.

### Quota ở provider là lớp bảo vệ cuối

Nếu credential bị lộ và kẻ tấn công gửi SMTP trực tiếp, rate limiter trong Spring không có hiệu lực. Khi có thể, hãy giới hạn quota và concurrency **trên account/connector ở provider**, đồng thời thêm rate limiter trong ứng dụng để xử lý tốt trước khi bị provider trả `4xx` hoặc throttling.

### Tránh biến restriction thành tình trạng mất email

Với email giao dịch cần được gửi, khi vượt rate limit:

1. Lưu ý định gửi vào hàng đợi bền vững.
2. Giữ trạng thái chờ/available_at thích hợp.
3. Gửi lại theo backoff hoặc lịch dispatch.
4. Theo dõi backlog age để không chậm thông báo quá SLA.

Không nên bỏ email âm thầm khi token bucket cạn. Cũng không nên retry dồn dập khiến quota provider bị khóa lâu hơn.

## 15. Chỉ cho phép SMTP relay từ nguồn tin cậy

Một số hệ thống dùng **SMTP relay theo IP/connector** thay vì username/password thông thường. Khi đó, quyền gửi có thể được quyết định theo nguồn mạng, chứng chỉ hoặc policy relay.

Rủi ro lớn là vô tình tạo **open relay**: server chấp nhận chuyển thư từ nguồn không tin cậy đến đích tùy ý. Open relay có thể bị lạm dụng để gửi spam, dẫn đến blocklist và thiệt hại uy tín domain.

Các kiểm soát:

- Chỉ allowlist dải IP egress thật sự của ứng dụng hoặc mạng nội bộ cần gửi.
- Nếu triển khai trên cloud, tránh allowlist một dải NAT/shared egress quá rộng nếu có thể tách.
- Áp TLS/mTLS hoặc cơ chế định danh bổ sung khi relay hỗ trợ.
- Giới hạn sender address/domain mà connector được phép sử dụng.
- Giới hạn destination domain/recipient, message rate và size nếu có.
- Không cho anonymous relay từ Internet.
- Audit các thay đổi connector và thường xuyên rà lại source IP.

Ví dụ kiến trúc:

~~~text
Application pod
      |
      | egress policy: chỉ smtp-relay.internal:587
      v
Internal SMTP relay
      |
      +-- Verify client/network identity
      +-- Enforce allowed sender domains
      +-- Apply rate limits / quotas
      +-- Record audit
      |
      v
External mail provider
~~~

**IP allowlist một mình có hạn chế**: IP có thể dùng chung qua NAT, workload khác trong cùng mạng có thể mượn đường đi, và egress IP có thể thay đổi khi deploy. Tài khoản/credential hoặc mTLS riêng cho service giúp thu hẹp identity hơn nếu nền tảng hỗ trợ.

### Network egress policy

Tại tầng Kubernetes/firewall/security group, có thể giới hạn ứng dụng chỉ được kết nối đến SMTP host/port đã duyệt. Điều này giúp giảm nguy cơ credential bị dùng để liên hệ server lạ hoặc ứng dụng gửi trực tiếp qua port khác.

Nhưng network egress policy cũng không tự cấp quyền theo sender mailbox. Cần kết hợp với provider permissions và giám sát.

## 16. Giới hạn những account mà service có thể đại diện

Nếu ứng dụng phải gửi từ nhiều thương hiệu, tenant hoặc phòng ban, một credential có khả năng gửi thay toàn bộ organization là rủi ro đáng kể. Hãy cân nhắc:

1. Một sender identity/SMTP credential cho từng tenant hoặc từng nhóm thương hiệu có yêu cầu cách ly.
2. Một policy xác định tenant nào được phép dùng sender nào.
3. Không lấy sender mailbox tùy ý từ HTTP request.
4. Chỉ load credential tương ứng sau khi kiểm tra tenant authorization.
5. Audit `tenantId`, `senderId` và `notificationType` mà không log secret.
6. Cách ly quota để một tenant không làm cạn năng lực gửi của tenant khác.

Một abstraction:

~~~java
public record SenderProfile(
        String profileId,
        String fromAddress,
        String replyToAddress) {
}

public interface SenderProfileResolver {
    SenderProfile forTenantAndType(
            String tenantId,
            NotificationKind type);
}
~~~

`SenderProfileResolver` phải lấy từ cấu hình đáng tin cậy và áp authorization; nó không tự kiểm chứng quyền SMTP. Khi cần nhiều account, adapter gửi phải chọn **JavaMailSender** tương ứng với profile và tránh chia sẻ token/password giữa tenants không cùng quyền.

### Không truyền credential vào đối tượng nhận request

Không dùng API như:

~~~java
public void sendEmail(
        String smtpUsername,
        String smtpPassword,
        String from,
        String to,
        String body) {
    // Rủi ro: client tự chọn identity và quyền gửi.
}
~~~

Credential thuộc hạ tầng phía server. Request chỉ nên chứa hành động nghiệp vụ, ID đối tượng và dữ liệu được cho phép; không được quyết định SMTP identity một cách tùy tiện.

## 17. SPF, DKIM và DMARC có thay thế quyền tài khoản không?

**Không.** SPF, DKIM và DMARC là các cơ chế xác thực email/domain ở tầng mail ecosystem, không phải một bộ phân quyền RBAC cho SMTP account.

| Cơ chế | Mục tiêu chính | Không làm thay |
|---|---|---|
| SPF | Xác định nguồn gửi được domain cho phép ở lớp envelope | Cấp/chặn quyền SMTP của một user cụ thể |
| DKIM | Gắn chữ ký mật mã giúp xác minh domain ký và tính toàn vẹn phần được ký | Giới hạn credential có thể gửi tới recipient nào |
| DMARC | Chính sách alignment và xử lý thư thất bại xác thực theo domain From | Chặn credential đã hợp lệ nhưng bị lạm dụng |

Nếu tổ chức cấu hình SPF/DKIM/DMARC tốt nhưng dùng credential admin quá quyền, nguy cơ lạm dụng vẫn còn. Một attacker sử dụng **credential gửi hợp lệ** có thể tạo email vượt qua authentication của domain, tùy cơ chế/provider. Do đó cần giới hạn quyền gửi, quota, monitoring và response.

### Sender identity cần được phép ở cả hai phía

Một message có thể bị provider chặn do sender chưa được xác minh, hoặc được provider nhận nhưng có vấn đề deliverability do cấu hình SPF/DKIM/DMARC chưa đúng. Chúng là các lớp khác nhau:

~~~text
Ứng dụng được phép gửi?
          |
          v
Provider chấp nhận authenticated sender?
          |
          v
Domain authentication và routing đúng?
          |
          v
Recipient system đánh giá và phân phối?
~~~

Không dùng cách “sửa DKIM” để khắc phục lỗi “Send As denied” khi credential không có quyền đặt From. Ngược lại, cấp rộng quyền Send As cũng không chữa cấu hình DNS/email authentication sai.

## 18. Thiết kế lớp gửi mail chỉ chấp nhận yêu cầu nghiệp vụ

Một cách để bảo vệ tài khoản SMTP là **không để mọi thành phần trong ứng dụng có thể gọi trực tiếp `JavaMailSender` với header và recipient tùy ý**.

Thay vì:

~~~java
// API gửi mail tổng quát này dễ bị lạm dụng nếu exposed sai ranh giới.
public void sendAny(
        String from,
        String to,
        String subject,
        String html) {
    // ...
}
~~~

Hãy tạo các phương thức thể hiện hành động nghiệp vụ được phép:

~~~java
public interface TransactionalMailPort {
    void sendOrderReceipt(OrderReceiptCommand command);
    void sendSecurityAlert(SecurityAlertCommand command);
}
~~~

Ví dụ DTO:

~~~java
public record OrderReceiptCommand(
        String orderId,
        String customerId,
        String locale) {
}

public record SecurityAlertCommand(
        String accountId,
        String eventId,
        String locale) {
}
~~~

**Đừng đưa SMTP username, password, From, BCC hoặc arbitrary HTML vào command từ client.** Application service kiểm tra authorization, lấy recipient đã xác minh, chọn template và sender profile theo cấu hình.

Luồng:

~~~mermaid
flowchart TD
    A[Authenticated request / committed event] --> B[Business authorization]
    B --> C[Load trusted recipient + domain data]
    C --> D[Select approved template and sender]
    D --> E[Recipient/rate/size policy]
    E --> F[Mail outbox / queue]
    F --> G[Dedicated mail adapter]
    G --> H[SMTP identity with least privilege]
    H --> I[Provider policy and quota]
    I --> J[SMTP submission]
~~~

Lợi ích:

- Controller không thể tự quyết định sender identity.
- Template được giới hạn theo trường hợp sử dụng.
- Business authorization diễn ra trước khi có hành động gửi.
- Policy được áp một cách tập trung, tránh mỗi service viết một kiểu.
- Có một chỗ để audit và phân loại việc từ chối.

### Validation không bằng authorization

Một địa chỉ email hợp lệ về cú pháp không đồng nghĩa người dùng được phép gửi tới địa chỉ đó. Ví dụ endpoint đặt lại mật khẩu có thể được thiết kế để gửi tới email trong hồ sơ tài khoản; dù request chứa `other@example.com` hợp lệ, nó có thể không được phép nhận thông báo có nội dung nhạy cảm.

Ngược lại, chính sách security không nên vô tình tiết lộ liệu một tài khoản tồn tại khi endpoint công khai trả kết quả khác nhau theo recipient. Hãy áp biện pháp chống enumeration và rate limit tùy nghiệp vụ.

## 19. Cô lập tài khoản gửi theo mức độ nhạy cảm

Không phải mọi email cần chung chính sách:

| Loại email | Đặc tính | Cách phân quyền nên cân nhắc |
|---|---|---|
| OTP/khôi phục tài khoản | Nhạy cảm, thời hạn ngắn, dễ bị lạm dụng | Sender riêng, quota riêng, template cố định, không gửi BCC tùy ý |
| Hóa đơn/xác nhận thanh toán | Quan trọng, cần audit | Identity giới hạn, outbox, sender đã duyệt |
| Đơn hàng/vận chuyển | Lưu lượng tương đối cao | Quota đủ lớn và có giám sát |
| Marketing/newsletter | Có thể có spike lớn và suppression policy | Account/provider lane riêng, opt-out, rate policy riêng |
| Thông báo nội bộ | Có thể chỉ dành cho domain nội bộ | Internal recipient restriction |

Nếu marketing gửi quá quota dùng chung với OTP, khách hàng có thể không nhận được mã đăng nhập. Tách sender identity/credential và giới hạn quota theo lane giúp giữ ưu tiên cho luồng quan trọng.

Đối với nội dung nhạy cảm, còn cần:

- Không gửi secret/token qua danh sách email phân phối không được phép.
- Không cho phép thay `Reply-To` để chuyển câu trả lời tới một địa chỉ lạ.
- Không để backend tự thêm nhiều BCC ngoài nhu cầu kiểm soát/audit.
- Khi có attachment, kiểm tra tài liệu đúng thuộc về recipient và quyền truy cập.
- Hạn chế thông tin đưa vào subject (subject dễ bị hiển thị ngoài ý muốn).

## 20. Dùng nhiều JavaMailSender khi có nhiều account

Khi mỗi loại email dùng một account hoặc provider khác nhau, có thể cấu hình **hai JavaMailSender bean riêng** với identity được đặt theo mục đích:

~~~java
import java.util.Properties;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class DedicatedSenderConfiguration {

    private JavaMailSenderImpl newSender(
            String host,
            int port,
            String username,
            String password) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(host);
        sender.setPort(port);
        sender.setUsername(username);
        sender.setPassword(password);
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");
        return sender;
    }

    @Bean("ordersMailSender")
    JavaMailSender ordersMailSender(OrderMailCredential credentials) {
        return newSender(
                credentials.host(),
                credentials.port(),
                credentials.username(),
                credentials.password());
    }

    @Bean("securityMailSender")
    JavaMailSender securityMailSender(
            SecurityMailCredential credentials) {
        return newSender(
                credentials.host(),
                credentials.port(),
                credentials.username(),
                credentials.password());
    }
}
~~~

Hai kiểu `OrderMailCredential` và `SecurityMailCredential` là các abstraction cấu hình an toàn do ứng dụng tự xây dựng, ví dụ được bind từ secret store. **Không viết giá trị password trong Java source.**

Chọn bean theo qualifier:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class OrderReceiptSender {
    private final JavaMailSender sender;

    public OrderReceiptSender(
            @Qualifier("ordersMailSender")
            JavaMailSender sender) {
        this.sender = sender;
    }
}
~~~

Với nhiều `JavaMailSender` bean, những service không đặt `@Qualifier` có thể gặp ambiguity khi Spring injection. Trong hệ thống bảo mật, việc lựa chọn explicit sender theo nghiệp vụ thường dễ kiểm soát hơn một bean mặc định có toàn quyền.

**Phân tách JavaMailSender bean chỉ là một phần.** Nếu cả hai bean dùng chung một credential có thể gửi từ mọi address, blast radius vẫn chưa được thu hẹp thực sự. Provider phải cấp hai identity/quyền riêng tương ứng.

### Cẩn trọng với pool và session sharing

Mỗi `JavaMailSenderImpl` giữ cấu hình server/authentication tương ứng; không nên thay `username` hoặc `password` của cùng một singleton bean ngay trước mỗi lần gửi theo tenant. Việc mutate shared configuration trong các request concurrent có thể dẫn đến gửi nhầm danh tính, khó audit và rò quyền.

Nếu cần chọn theo tenant, dùng registry các sender/config bất biến theo profile, có kiểm soát lifecycle và cache/secret rotation rõ ràng. Không nhận SMTP credential từ request client để tạo sender động không giới hạn.

## 21. Bảo vệ cấu hình From/Reply-To/Return-Path

Với email có reply hoặc bounce, người phát triển dễ nhầm:

- Header `From` cho biết tác giả/người gửi hiển thị.
- Header `Reply-To` gợi ý nơi nhận phản hồi.
- Envelope sender/return-path liên quan đến bounce và mail routing.

Một tài khoản có quyền gửi email không nhất thiết có quyền đổi tùy ý cả ba. Provider có thể áp rewriting hoặc yêu cầu xác thực domain/sender. Đặc biệt, attacker có thể lạm dụng `Reply-To` để dẫn phản hồi tới địa chỉ do họ kiểm soát dù phần `From` trông hợp lệ.

Ví dụ policy:

~~~java
public record ApprovedMailIdentity(
        String fromAddress,
        String replyToAddress) {
}

public ApprovedMailIdentity identityFor(
        NotificationKind kind) {
    return switch (kind) {
        case ORDER_RECEIPT -> new ApprovedMailIdentity(
                "orders@example.com", "support@example.com");
        case SECURITY_ALERT -> new ApprovedMailIdentity(
                "security@example.com", "security@example.com");
    };
}
~~~

Mail composer chỉ nhận profile được server lựa chọn. Không nhận tham số `replyTo` tùy ý từ endpoint công khai. Nếu cần reply-to động theo một nhân viên hoặc địa chỉ đối tác, phải kiểm tra quyền sử dụng và domain theo chính sách.

### Header tùy chỉnh không phải cơ chế cấp quyền

Thêm một header như `X-Application-Name` hoặc `X-Tenant-Id` có thể hỗ trợ trace nội bộ, nhưng SMTP provider không tự nhiên coi nó là bằng chứng authorization. Nếu mail gateway dựa vào custom header để áp policy, phải kiểm soát ai có thể chèn/sửa header và xác thực nguồn theo một cơ chế đáng tin cậy.

## 22. Outbox và authorization: giữ quyết định gửi qua transaction

Với email được phát sinh bởi thao tác nghiệp vụ, nên tách **ý định gửi được phê duyệt** khỏi hành động SMTP:

~~~text
Business transaction
    |
    +-- Xác thực event + quyền user
    +-- Xác định recipient đáng tin cậy
    +-- Chọn template + sender profile ID
    +-- Ghi outbox record
    |
    v
COMMIT
    |
    v
Mail worker
    |
    +-- Load sender profile được cấp
    +-- Re-validate policy cần thiết
    +-- Áp quota/rate limit
    +-- JavaMailSender.send
~~~

Record outbox nên giữ **sender profile ID** hoặc loại notification đã được phê duyệt thay vì lưu username/password. Worker tra cứu credential từ secret store hoặc hạ tầng bảo mật phía server.

Ví dụ payload:

~~~json
{
  "eventId": "mail-job-2810",
  "notificationType": "ORDER_RECEIPT",
  "senderProfileId": "production-orders",
  "orderId": "ORD-001",
  "recipientId": "CUSTOMER-900",
  "payloadVersion": 1
}
~~~

Nếu business policy cho phép lưu snapshot recipient, có thể dùng email address đã xác minh tại thời điểm commit. Nếu worker tra cứu recipient mới nhất, cần xác định việc thay đổi email sau khi tạo event có làm thay đổi đối tượng được nhận hay không. **Đừng để outbox consumer tự gửi với quyền rộng chỉ vì nó chạy nền.**

### Khi policy thay đổi giữa lúc tạo job và lúc gửi

Giả sử tài khoản bị khóa sau khi một password-reset email đã được thêm vào outbox nhưng trước khi worker gửi. Nghiệp vụ có thể yêu cầu hủy thông báo hoặc thay đổi nội dung. Vì vậy cần xác định:

- Những kiểm tra nào được chốt tại thời điểm commit?
- Những kiểm tra nào phải đánh giá lại ở dispatch time?
- Job nào cần hủy nếu tài khoản/consent/tenant bị vô hiệu hóa?
- Job có chứa token đã hết hạn không?

Quyết định tùy loại thông báo; outbox không tự giải quyết các vấn đề authorization và hiệu lực dữ liệu theo thời gian.

## 23. Kiểm thử quyền tối thiểu từ ứng dụng đến mail provider

Test bảo mật SMTP nên có ít nhất **hai lớp**:

1. **Application policy tests:** kiểm tra controller/service không cho gửi vượt quyền, chọn đúng sender, recipient và template.
2. **Provider/relay authorization tests:** với tài khoản test và môi trường được kiểm soát, xác nhận provider thực sự từ chối những hành động vượt phạm vi.

### Test domain allowlist

Với `RecipientPolicy` đã minh họa:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import jakarta.mail.internet.AddressException;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class RecipientPolicyTest {
    private RecipientPolicy policy;

    @BeforeEach
    void init() {
        policy = new RecipientPolicy(
                Set.of("example.test", "qa.example.test"));
    }

    @Test
    void permitsExplicitlyAllowedDomain() throws Exception {
        assertThat(
                policy.requireAllowed("user@example.test").getAddress())
                .isEqualTo("user@example.test");
    }

    @Test
    void rejectsUnapprovedDomain() {
        assertThatThrownBy(
                () -> policy.requireAllowed("user@external.example"))
                .isInstanceOf(SecurityException.class);
    }

    @Test
    void rejectsLookalikeDomain() {
        assertThatThrownBy(
                () -> policy.requireAllowed("user@notexample.test"))
                .isInstanceOf(SecurityException.class);
    }

    @Test
    void rejectsMissingRecipient() {
        assertThatThrownBy(
                () -> policy.requireAllowed("  "))
                .isInstanceOf(AddressException.class);
    }
}
~~~

Test này kiểm tra chính sách ở lớp Java, không xác minh account SMTP thật được provider giới hạn tương ứng.

### Test không gửi khi policy từ chối

Ví dụ mock `JavaMailSender` cho một lớp adapter dùng policy:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;

class PolicyGuardTest {
    @Test
    void doesNotReachMailSenderForBlockedRecipient() {
        JavaMailSender sender =
                org.mockito.Mockito.mock(JavaMailSender.class);
        RecipientPolicy policy =
                new RecipientPolicy(Set.of("example.test"));

        assertThatThrownBy(() ->
                policy.requireAllowed("outside@other.test"))
                .isInstanceOf(SecurityException.class);

        verifyNoInteractions(sender);
    }
}
~~~

Đoạn test mô tả nguyên tắc fail-before-send bằng cách kiểm tra policy ở bước tiền xử lý; trong ứng dụng thật, hãy gọi **service kết hợp validation và mailSender** rồi assert `verifyNoInteractions(sender)` để chứng minh đường gửi không thể bị gọi khi policy từ chối. Không nên chỉ kiểm tra helper hay policy riêng rồi coi như toàn bộ hệ thống đã được bảo vệ.

### Provider authorization test

Trong môi trường thử nghiệm có permission được cấp hẹp, xác minh:

- Credential gửi đúng sender được chấp nhận.
- Cố dùng `From` không được cấp bị từ chối hoặc bị rewrite đúng chính sách.
- Nếu có recipient restriction, gửi ngoài allowlist bị chặn.
- Nếu có IP restriction, request từ nguồn không hợp lệ bị từ chối.
- Nếu có quota, vượt giới hạn được kiểm soát (không cần cố tình spam tới người dùng thật).
- Credential không có quyền đọc mailbox/API không được cấp.
- Secret cũ đã thu hồi không còn hoạt động sau rotation.

**Không tiến hành thử brute force, tạo spam hoặc thử vượt quota trên production để “kiểm tra” bảo mật.** Dùng tài khoản sandbox, mailbox được kiểm soát và kiểm thử quyền qua API quản trị/provider hoặc quy trình được cấp phép.

### Negative test quan trọng hơn happy path

Việc email gửi thành công từ `orders@example.com` chỉ chứng minh account có quyền đủ để làm việc đó. **Không chứng minh rằng account không có quyền gửi với `ceo@example.com` hoặc đọc mailbox.** Kiểm thử quyền tối thiểu cần các negative tests có kiểm soát tương ứng với grant bị cấm.

## 24. Rà soát quyền định kỳ và phát hiện drift

Ban đầu tài khoản có thể được cấp quyền hẹp, nhưng theo thời gian:

- Một admin cấp thêm Send As để sửa lỗi khẩn cấp.
- Account được đưa vào nhóm có quyền rộng.
- Connector được mở rộng IP allowlist.
- SMTP AUTH được bật cho nhiều tài khoản hơn dự kiến.
- Staging vô tình dùng chung secret với production.
- API key được dùng cho cả marketing và thông báo bảo mật.
- Quyền đọc mailbox được thêm rồi không thu hồi.

Đó là **privilege drift**: đặc quyền thực tế lớn hơn thiết kế ban đầu.

Một kỳ rà soát quyền có thể so sánh:

| Nội dung rà soát | Desired state | Cần hành động nếu |
|---|---|---|
| Service principal/account | Chỉ danh tính đã phê duyệt | Xuất hiện user cá nhân hoặc account lạ |
| Authentication method | Cơ chế được chính sách chấp nhận | Legacy method được bật ngoài nhu cầu |
| Send As grants | Chỉ mailbox/alias được duyệt | Có mailbox khác hoặc wildcard scope |
| Mailbox read permission | Không có nếu chỉ cần gửi | Xuất hiện IMAP/POP/API read |
| Admin/IAM roles | Không có | Có role quản trị tenant hoặc org |
| IP/source restriction | Egress đã duyệt | Allowlist quá rộng hoặc nguồn lạ |
| Sender domains | Đúng danh sách verified | Có domain không thuộc ứng dụng |
| Recipient/relay limits | Đúng phạm vi nghiệp vụ | Cho relay ra ngoài ngoài dự kiến |
| Quota/alerts | Ngưỡng rõ ràng | Không cảnh báo khi spike |
| Secrets | Tách môi trường, rotate | Credential cũ còn dùng được |

Nếu nền tảng hỗ trợ infrastructure as code, lưu **chính sách quyền và connector** dưới dạng cấu hình có review/approval. Secret không nằm trong repository IaC. Với thay đổi khẩn cấp, cần ghi lý do, người phê duyệt và thời điểm thu hồi quyền tạm.

### Audit ai đã thay đổi quyền

Không chỉ theo dõi số email gửi; hãy theo dõi:

- Ai đã tạo/reset credential?
- Ai bật/tắt SMTP AUTH?
- Ai cấp hoặc thu hồi Send As/Send on Behalf?
- Ai thêm IP vào allowlist?
- Ai thay quota hoặc recipient policy?
- App nào dùng token mới/cũ?

Những audit event này nằm chủ yếu ở identity provider/mail provider, không phải `JavaMailSender` tự ghi. App log có thể bổ sung event ID, sender profile và mục đích gửi.

## 25. Monitoring hành vi bất thường của tài khoản gửi

Một service identity có quyền tối thiểu vẫn có thể bị lạm dụng trong phạm vi được cấp. Cần giám sát dấu hiệu bất thường:

| Tín hiệu | Ý nghĩa có thể có |
|---|---|
| Số mail gửi/phút tăng đột biến | Bug vòng lặp, spam hoặc credential bị lộ |
| Tăng recipient mới/lạ | Luồng nghiệp vụ bị lạm dụng |
| Gửi vào giờ bất thường | Event bất thường hoặc lạm dụng |
| Nhiều lỗi SMTP AUTH | Secret hết hạn, cấu hình lỗi hoặc brute-force attempt |
| Nhiều lỗi Send As denied | App đang chọn sai From hoặc ai đó thử giả mạo |
| Nhiều lỗi relay prohibited | Recipient/domain restriction hoạt động hoặc bị bypass |
| Nhiều message bị provider từ chối | Quota, reputational issue hoặc policy violation |
| Nguồn IP/auth location thay đổi | Deployment egress thay đổi hoặc credential compromise |
| Bounce/complaint rate tăng | Recipient list có vấn đề hoặc abuse |

### Log tại ứng dụng

Nên ghi metadata ở mức đủ dùng:

~~~text
event=mail_submission
notificationType=ORDER_RECEIPT
senderProfile=production-orders
jobId=mail-job-2810
tenantId=tenant-42
recipientDomain=example.test
result=SMTP_ACCEPTED
durationMs=731
~~~

Đây là ví dụ dữ liệu giả. Nếu recipient domain hoặc tenant ID cũng nhạy cảm trong hệ thống, hãy điều chỉnh/redact. Không log password, OAuth token, nội dung body, attachment, OTP, magic link hoặc dữ liệu khách hàng không cần thiết.

Khi gửi qua SMTP, có thể ghi mã lỗi/nhóm lỗi và số lần thử. **Không dùng nguyên exception message hoặc recipient address làm metric label** vì cardinality cao và có thể làm lộ dữ liệu.

### Cảnh báo cần gắn với hành động vận hành

Một alert tốt nên có:

- Sender profile bị ảnh hưởng.
- Khung thời gian và mức tăng gửi/thất bại.
- Nguồn dữ liệu: app metrics hay provider submission audit.
- Hướng kiểm tra ban đầu: credential, quota, quyền Send As, network hoặc template.
- Quy trình tạm dừng lane gửi và thu hồi secret nếu nghi compromise.

Không nhất thiết cảnh báo từng lần `SMTP 4xx` do rate limit tạm thời. Hãy dựa vào tỷ lệ, độ kéo dài, hậu quả với backlog và loại thông báo.

## 26. Ứng phó khi phát hiện SMTP credential bị lộ

Nếu có dấu hiệu credential lộ qua commit, log, CI artifact, container image hoặc hành vi gửi bất thường, cần xử lý như một sự cố bảo mật:

1. **Khoanh vùng:** xác định app, account, sender profiles, environments và các nguồn có credential.
2. **Giới hạn lạm dụng:** tạm dừng submission của identity hoặc áp chặn/quota tại provider theo kế hoạch ứng phó.
3. **Thu hồi/rotate credential:** vô hiệu hóa secret/token cũ; kiểm tra tất cả replica và các job còn dùng secret.
4. **Kiểm tra phạm vi:** rà quyền Send As, mailbox access, admin role, relay connector và token grants.
5. **Đối soát logs:** so sánh app outbox với provider submission audit; tìm các message không đến từ luồng nghiệp vụ được phê duyệt.
6. **Khôi phục an toàn:** cấp credential mới với quyền tối thiểu; triển khai lại bằng secret store.
7. **Đánh giá ảnh hưởng:** xem người nhận, domain, reputation, complaint/bounce và thông báo sự cố khi cần.
8. **Loại bỏ nguyên nhân:** xóa secret khỏi nơi lưu không phù hợp, cập nhật CI masking, review code/config và điều chỉnh policy.

### Một nguy cơ khi chỉ rotate mật khẩu

Nếu token hoặc credential cũ còn có thể sử dụng, đổi một password ở UI nhưng không thu hồi session/token có liên quan có thể chưa đủ. Quy trình cần phù hợp với provider: thu hồi refresh token, API key, app password, SMTP credential hoặc quyền service principal tương ứng.

Nếu một tài khoản có quyền quản trị tenant, phạm vi điều tra phải lớn hơn rất nhiều. Đây là một trong những lý do quan trọng nhất để **không dùng admin credential cho Spring Mail**.

### Hệ thống outbox giúp phục hồi nhưng phải kiểm soát replay

Nếu tạm dừng gửi để ứng phó, outbox có thể giữ các job chưa submit. Sau khi cấp credential mới:

- Kiểm tra job thuộc loại được phép gửi.
- Chặn những job đã hết giá trị (ví dụ OTP đã hết hạn).
- Áp quota khi phát lại backlog.
- Đối soát những job có trạng thái UNKNOWN để tránh gửi trùng không cần thiết.
- Theo dõi audit để xác định thời điểm khôi phục.

Không tự phát lại mọi job cũ vô điều kiện. Một tài khoản đã bị lộ có thể đồng thời phát sinh những job trái phép; chỉ replay các yêu cầu có nguồn gốc và authorization rõ ràng.

## 27. Triệu chứng cấu hình và hướng chẩn đoán

Một số lỗi thường gặp khi tài khoản gửi được giới hạn quyền đúng cách:

| Triệu chứng | Khả năng nguyên nhân | Cách kiểm tra |
|---|---|---|
| SMTP AUTH bị từ chối | Credential/token sai, expired, SMTP AUTH bị chặn, scope sai | Kiểm tra auth method, token audience/scope, policy account |
| Authenticate được nhưng From bị từ chối | Thiếu Send As/verified sender grant | So sánh authenticated identity với sender profile và policy provider |
| Chỉ staging bị lỗi | Sandbox credential/recipient allowlist | Kiểm tra environment, profile, egress và domain test |
| Có thể gửi nội bộ nhưng không gửi Internet | Relay policy giới hạn external recipients | Kiểm tra connector, recipient rule và domain policy |
| Một vài tenant không gửi được | Tenant-to-sender authorization hoặc quota | Kiểm tra profile resolver, quyền per tenant |
| Truy cập mailbox bị từ chối | Quyền đọc mail đã bị tắt theo thiết kế | Xác nhận ứng dụng có thực sự cần read access không |
| SMTP 4xx khi lưu lượng tăng | Provider throttling hoặc quota | Kiểm tra rate, concurrency, backlog và response code |
| SMTP 5xx trên một số người nhận | Recipient/sender policy, domain validation | Xem mã phản hồi SMTP, chính sách và dữ liệu recipient |
| TLS handshake hoặc hostname lỗi | Trust chain, host, TLS version/cert | Sửa trust và endpoint, không bật trust all |
| Bị từ chối từ instance mới | IP egress không nằm trong allowlist | Kiểm tra NAT egress/connector và deployment |
| Email gửi thành công nhưng vào spam | Deliverability, reputation, authentication | Kiểm tra SPF/DKIM/DMARC và nội dung; không tự mở rộng quyền |

**Không khắc phục lỗi “Send As denied” bằng cách cấp admin role cho service account.** Hãy cấp đúng permission trên sender identity mà ứng dụng thực sự cần. Tương tự, khi bị throttling không nên chuyển sang dùng credential của nhân viên để “gửi cho nhanh”.

### Chẩn đoán theo lớp

~~~mermaid
flowchart TD
    A[Spring Mail submission failed] --> B{Kết nối và TLS thành công?}
    B -- Không --> C[DNS, port, TLS, certificate, network]
    B -- Có --> D{SMTP AUTH thành công?}
    D -- Không --> E[Credential, token, auth policy/scope]
    D -- Có --> F{Sender được phép?}
    F -- Không --> G[Verified sender, Send As, mailbox scope]
    F -- Có --> H{Recipient/rate/relay được phép?}
    H -- Không --> I[Quota, recipient allowlist, IP policy]
    H -- Có --> J[Submission accepted]
    J --> K[Delivery/DMARC/spam filtering kiểm tra riêng]
~~~

Đây là đường đi khái quát; SMTP provider có thể thực hiện kiểm tra ở những giai đoạn khác nhau và có mã lỗi không hoàn toàn tương ứng từng nhánh. Hãy xem nested exception, SMTP response và log provider trước khi kết luận.

## 28. Những anti-pattern nên tránh

### 28.1. Dùng credential mailbox quản trị cho SMTP

Một lỗi của ứng dụng hoặc lộ secret có thể dẫn đến xâm nhập vượt phạm vi gửi. Dùng service identity chỉ có quyền cần thiết.

### 28.2. Đưa cùng secret vào development, staging và production

Lộ secret từ laptop developer có thể ảnh hưởng toàn bộ người nhận production. Tách môi trường và giới hạn staging recipient ở provider/relay nếu có thể.

### 28.3. Chỉ kiểm soát quyền trong Java mà không kiểm tra provider

Một đoạn Java chặn recipient không còn tác dụng khi kẻ tấn công lấy credential và kết nối SMTP trực tiếp. Áp provider policies, egress restriction và audit.

### 28.4. Dùng wildcard Send As hoặc quyền tenant-wide không cần thiết

Một ứng dụng chỉ gửi từ `orders@example.com` không cần quyền gửi thay mọi mailbox. Cấp quyền hẹp theo sender identity.

### 28.5. Để endpoint nhận From, Reply-To và nội dung HTML tùy ý

Điều này có thể biến backend thành spam/phishing relay hợp lệ. Chỉ cho gửi theo template và quy tắc nghiệp vụ được phê duyệt; validation và authorization phải đứng trước SMTP.

### 28.6. Dùng password thật trong application.yml được commit vào git

Git history và artifacts vẫn giữ secret kể cả khi xóa khỏi file ở commit mới. Dùng secret manager và rotate secret đã lộ.

### 28.7. Coi OAuth2 tự động đồng nghĩa send-only

Token có thể chứa application permission rộng nếu grant rộng. Cần rà scope, audience, application role, mailbox scope và consent.

### 28.8. Tin rằng SPF/DKIM/DMARC ngăn credential bị lạm dụng

Các cơ chế này giải quyết xác thực domain/deliverability, không kiểm soát user/application quyền SMTP.

### 28.9. Tăng concurrency để vượt rate limit

Provider có thể khóa hoặc throttling mạnh hơn; tăng pool còn làm backlog và retry phức tạp. Cần tôn trọng quota và điều phối rate.

### 28.10. Bỏ qua lỗi authorization rồi dùng sender khác

Nếu `orders@example.com` bị từ chối vì thiếu quyền, không tự fallback sang `admin@example.com` hoặc shared global account. Đây có thể là một vi phạm policy. Hãy chặn submission, log error code và sửa cấp quyền.

### 28.11. Không kiểm tra quyền sau khi thay đổi provider

Nhà cung cấp mới có thể cho credential quyền gửi rộng hơn hoặc yêu cầu cơ chế authentication khác. Cần rà lại ma trận quyền, sender alias, quota, TLS và webhook/bounce scope trước cutover.

### 28.12. Dùng open relay không có nguồn tin cậy

Một relay cho phép nguồn ngoài gửi tới đích tùy ý tạo cửa ngõ spam. Cần giới hạn network identity, sender domain, rate và logging.

## 29. Quy trình triển khai quyền tối thiểu cho Spring Mail

Một quy trình thực tế theo trình tự:

1. **Liệt kê nhu cầu:** ứng dụng gửi loại email nào, từ địa chỉ nào, tới nhóm người nhận nào và lưu lượng dự kiến?
2. **Chọn mô hình xác thực:** SMTP AUTH password, OAuth2 hoặc relay identity theo khả năng provider và chính sách bảo mật.
3. **Tạo danh tính chuyên dụng:** không dùng admin hoặc tài khoản nhân viên cá nhân.
4. **Cấp quyền tối thiểu:** chỉ được submission, chỉ sender/mailbox đã duyệt; không cấp mailbox read hoặc tenant admin nếu không cần.
5. **Cấu hình provider policies:** verified sender, Send As, allowed recipients/domains, quota/IP restriction khi hỗ trợ.
6. **Tách môi trường:** credential, sender và recipient policy độc lập cho dev/staging/prod.
7. **Lưu secret an toàn:** dùng secret manager, hạn chế workload được đọc và có kế hoạch rotate.
8. **Cấu hình Spring:** đúng host/port/TLS/auth/timeout; không log credential.
9. **Xây application authorization:** endpoint chỉ phát yêu cầu nghiệp vụ; mail adapter chọn sender và template từ cấu hình.
10. **Giới hạn tải:** rate limiting, concurrency, batch size và quota theo account/toàn cụm.
11. **Kiểm thử positive và negative:** được gửi đúng identity; bị chặn nếu sender/recipient/IP vượt quyền.
12. **Theo dõi và audit:** submission rate, auth failures, Send As denied, quota, IP lạ và privilege changes.
13. **Vận hành vòng đời:** rotate, revoke, rà soát drift và xử lý credential compromise.

### Ma trận quyết định tối thiểu

| Câu hỏi | Nếu câu trả lời là “Có” | Hành động |
|---|---|---|
| Ứng dụng chỉ cần gửi mà không đọc inbox? | Có | Không cấp quyền mailbox read |
| Chỉ cần gửi từ một sender? | Có | Chỉ verified/allow sender đó |
| Có nhiều ứng dụng không liên quan? | Có | Tách credential theo blast radius |
| Có staging/dev? | Có | Credential và recipient sandbox riêng |
| Provider hỗ trợ giới hạn recipient? | Có | Áp policy ngay tại provider/relay |
| Provider không giới hạn recipient? | Có | Bổ sung application policy, network và monitoring; ghi nhận rủi ro credential theft |
| Cần gửi qua nhiều account? | Có | Dùng sender profiles/JavaMailSender riêng và grant tương ứng |
| Account có admin permission? | Có | Rà soát, thu hồi quyền không cần |
| Có quota toàn cụm? | Có | Điều phối rate/concurrency ở cấp toàn cụm |
| Mail không được mất sau restart? | Có | Transactional outbox/broker, không chỉ @Async |

## 30. Câu hỏi thường gặp

**Tài khoản SMTP có cần được cấp quyền quản trị mail server không?** Không. Một mail sender thông thường chỉ cần quyền submission và sender identity tương ứng. Admin rights làm tăng đáng kể blast radius.

**Cứ tạo account chỉ để gửi là account đó không đọc được mailbox?** Không nhất thiết. Quyền thực tế phụ thuộc provider và các giao thức/API còn được bật. Phải kiểm tra grants/protocol access, không chỉ dựa vào mục đích đặt tên account.

**Đặt `spring.mail.username` và `spring.mail.password` có tự giới hạn quyền không?** Không. Những thuộc tính này cấu hình cách client xác thực. Quyền được quyết định bởi provider/account và các chính sách bên ngoài.

**Có thể dùng một account cho mọi địa chỉ From?** Chỉ khi provider cấp quyền tương ứng, nhưng đó thường là scope quá rộng nếu ứng dụng chỉ cần vài sender. Hãy giới hạn theo địa chỉ/alias hoặc tách identity.

**Có nên cho ứng dụng tự đổi From tùy yêu cầu?** Không với request chưa được tin cậy. Chọn sender profile từ server theo loại nghiệp vụ và tenant đã xác thực.

**SMTP AUTH với OAuth2 có bảo mật hơn mọi trường hợp password?** Token có thời hạn và scope phù hợp giúp giảm rủi ro, nhưng OAuth2 vẫn có thể bị cấp quyền quá rộng hoặc lộ refresh token/client secret. Cần rà grants và vòng đời token.

**Bật MFA cho account SMTP có đủ không?** Không. Một số cách SMTP AUTH, app password hoặc service-to-service grant không yêu cầu prompt MFA mỗi lần gửi. Phải kiểm tra authentication mechanism và cấp quyền tối thiểu.

**TLS có giới hạn người nhận hoặc địa chỉ gửi không?** Không. TLS bảo vệ đường truyền; authorization và sender/recipient restrictions nằm ở provider, relay và ứng dụng.

**IP allowlist có thay thế password/OAuth2 không?** Không hoàn toàn. Nó chỉ ràng buộc nguồn mạng và có thể bị ảnh hưởng NAT/shared egress. Nếu có thể, kết hợp xác thực dịch vụ, TLS và policy sender.

**SPF, DKIM, DMARC có chặn tài khoản bị lộ gửi thư không?** Không. Các cơ chế xác thực domain không thay thế quản lý credential và quyền gửi.

**Quyền Send As và Reply-To giống nhau không?** Không. Send As liên quan quyền gửi như một mailbox/identity; Reply-To chỉ là header chỉ nơi nhận phản hồi, cần chính sách chống lạm dụng riêng.

**Tách hai JavaMailSender bean đã là cách ly bảo mật chưa?** Chỉ khi mỗi bean thực sự dùng credential/quyền khác nhau và cấu hình/provider policy được tách. Hai bean dùng cùng global credential không tạo least privilege.

**Có thể chỉ dùng recipient allowlist trong Spring?** Có thể là một lớp phòng vệ, nhưng credential bị lộ có thể bị dùng ngoài ứng dụng. Cần provider/relay/network restrictions nếu bảo đảm này là bắt buộc.

**Tài khoản gửi có cần outbox?** Outbox không phải cơ chế cấp quyền. Nó lưu ý định gửi bền vững; sender permissions vẫn phải được giới hạn. Hai cơ chế giải quyết vấn đề khác nhau và có thể kết hợp.

## 31. Tổng kết

Trong Spring Framework Mail, **giới hạn quyền của tài khoản gửi** có nghĩa là tạo danh tính chuyên dụng với phạm vi nhỏ nhất: chỉ được gửi các thông báo cần thiết, bằng sender identity đã được phê duyệt, qua endpoint/chính sách SMTP phù hợp và với quota có kiểm soát.

Để làm được điều đó cần phối hợp nhiều lớp:

- **Identity/provider:** xác thực, scope/grant, Send As và các quyền mailbox thực sự được cấp.
- **Network/SMTP relay:** TLS, source restriction, chống open relay, giới hạn recipient/traffic.
- **Spring application:** không chấp nhận arbitrary From/recipient/HTML, dùng sender profile cố định, validation và authorization.
- **Secret management:** lưu trữ, rotation, thu hồi và tách môi trường.
- **Operations:** audit, metric, cảnh báo bất thường, rà soát privilege drift và ứng phó sự cố.

Nguyên tắc cần nhớ là: **`JavaMailSender` chỉ là client gửi thư; quyền thực tế của credential nằm ngoài Spring.** Bảo vệ ứng dụng không dừng ở việc mã hóa đường truyền hoặc dùng mật khẩu mạnh. Hãy giảm những gì credential được phép làm, giảm lượng thư có thể bị lạm dụng và bảo đảm một ứng dụng bị xâm nhập không kéo theo quyền đọc mailbox hay quản trị toàn hệ thống email.
