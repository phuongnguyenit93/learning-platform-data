# OAuth2 hoặc cơ chế xác thực hiện đại của nhà cung cấp

Khi ứng dụng **Spring Framework Mail** kết nối đến SMTP server, việc xác thực quyết định ứng dụng có được phép gửi thư dưới một danh tính nhất định hay không. Cách cấu hình truyền thống là cung cấp tên đăng nhập và mật khẩu:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
~~~

Cách này vẫn có thể phù hợp với một số SMTP server, nhưng nhiều nhà cung cấp dịch vụ email ngày càng áp dụng các chính sách hạn chế hoặc loại bỏ **Basic Authentication bằng mật khẩu tài khoản**. Họ có thể yêu cầu **OAuth 2.0**, mật khẩu ứng dụng có giới hạn, credential riêng của SMTP relay, hoặc API gửi email được bảo vệ bằng token, API key hay danh tính workload.

Trong bối cảnh đó, ứng dụng Java cần giải quyết hai vấn đề khác nhau:

1. **Lấy được một credential phù hợp với chính sách nhà cung cấp.** Với OAuth 2.0, đó thường là access token được cấp cho một mailbox hoặc ứng dụng với phạm vi quyền cụ thể.
2. **Truyền credential đúng cơ chế mà máy chủ SMTP hỗ trợ.** Ví dụ, khi SMTP server hỗ trợ `AUTH XOAUTH2`, JavaMail/Jakarta Mail có thể đưa access token vào cơ chế xác thực này thay vì gửi mật khẩu tài khoản qua `AUTH LOGIN` hoặc `AUTH PLAIN`.

**Điểm quan trọng:** OAuth 2.0 không phải là một phương thức mã hóa nội dung email và cũng không thay thế TLS. Nó giúp quản lý **ủy quyền và cấp quyền truy cập**. Ứng dụng vẫn cần kiểm tra chứng chỉ TLS, bảo vệ token, kiểm soát phạm vi quyền và xử lý lỗi SMTP.

## 1. Vì sao cần xác thực hiện đại cho SMTP?

Trong nhiều hệ thống, SMTP credential được cấu hình như một mật khẩu cố định:

~~~text
Application
    |
    | username + password
    v
SMTP server
    |
    v
Accept or reject mail submission
~~~

Cách dùng mật khẩu dài hạn có một số hạn chế:

- Nếu secret bị lộ, kẻ tấn công có thể tiếp tục dùng cho đến khi được thay đổi hoặc thu hồi.
- Khó giới hạn quyền cho đúng một ứng dụng hoặc một mục đích gửi.
- Mật khẩu dùng chung giữa nhiều service làm khó xác định nguồn phát sinh sự cố.
- Thay đổi mật khẩu có thể ảnh hưởng đồng thời nhiều process.
- Nhà cung cấp có thể cấm đăng nhập SMTP bằng mật khẩu tài khoản theo chính sách bảo mật.
- Một số môi trường yêu cầu MFA, conditional access, workload identity hoặc giới hạn ứng dụng được ủy quyền.

OAuth 2.0 giúp tách **credential dài hạn để xin quyền** khỏi **access token ngắn hạn dùng để truy cập dịch vụ**. Access token thường có thời hạn, phạm vi và đối tượng nhận (audience/resource) do hệ thống cấp token quy định.

Điều này không có nghĩa OAuth là “an toàn tự động”. Nếu ứng dụng để lộ refresh token, client secret hoặc access token, rủi ro vẫn tồn tại. Sự khác biệt là cơ chế cấp quyền, thu hồi, giới hạn và giám sát có thể được quản lý riêng thay vì phụ thuộc vào một mật khẩu mailbox dùng chung.

### 1.1. Phân biệt xác thực, ủy quyền và mã hóa

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Authentication** | Ứng dụng/đối tượng đang chứng minh danh tính nào? | SMTP xác thực qua SASL XOAUTH2 |
| **Authorization** | Danh tính đó được phép làm gì? | Token có quyền gửi thư cho mailbox được cấp |
| **Transport encryption** | Dữ liệu trên đường truyền có được bảo vệ không? | TLS, STARTTLS |
| **Message encryption** | Nội dung email có được mã hóa cho người nhận không? | S/MIME hoặc OpenPGP, nếu sản phẩm dùng |
| **Identity policy** | Ứng dụng có được phép dùng địa chỉ From này không? | Quyền Send As/alias/sender domain |

Một phiên SMTP có token đúng nhưng không dùng TLS có thể làm lộ token trên đường truyền. Một phiên dùng TLS tốt nhưng token không có quyền gửi cũng sẽ bị nhà cung cấp từ chối. Hai điều kiện phải được kiểm tra riêng.

## 2. OAuth 2.0 và SMTP AUTH XOAUTH2 không phải cùng một thứ

OAuth 2.0 là một **framework cấp quyền**: ứng dụng nhận access token từ authorization server dựa trên grant flow đã được cho phép.

SMTP là giao thức gửi mail. SMTP server dùng phần mở rộng `AUTH` để xác thực SMTP client. Một số server hỗ trợ cơ chế SASL `XOAUTH2` hoặc cơ chế bearer-token phù hợp khác.

Trong trường hợp phổ biến:

~~~text
OAuth authorization server
        |
        | OAuth 2.0 grant/token response
        v
    Access token
        |
        | Token được dùng làm credential
        v
Spring Mail / Jakarta Mail
        |
        | SMTP AUTH XOAUTH2 (qua TLS)
        v
   SMTP submission server
~~~

Ứng dụng phải biết:

- Token được cấp bởi issuer nào.
- Token dành cho SMTP resource/server nào.
- Token gắn với mailbox hoặc service principal nào.
- Token có scope/permission nào.
- Token còn hiệu lực bao lâu.
- SMTP server có hỗ trợ `AUTH XOAUTH2` hay một cơ chế khác.

Không thể lấy một access token dùng cho API bất kỳ rồi cho vào SMTP và mặc định nó sẽ hoạt động. **Audience, scope, mailbox identity và chính sách provider phải khớp**.

### 2.1. AUTH PLAIN/LOGIN khác AUTH XOAUTH2 ở đâu?

| Khía cạnh | `AUTH LOGIN` / `AUTH PLAIN` | `AUTH XOAUTH2` |
| --- | --- | --- |
| Credential thường dùng | Username + password hoặc app password | Mailbox identity + OAuth access token |
| Vòng đời credential | Có thể dài hạn | Access token thường ngắn hạn |
| Thu hồi quyền | Đổi mật khẩu, khóa tài khoản hoặc policy | Thu hồi grant/app, chặn principal, hết hạn token |
| MFA/conditional access | Tùy cơ chế/provider, basic auth thường khó đáp ứng | Flow cấp token có thể áp dụng policy hiện đại |
| TLS | Vẫn bắt buộc theo thiết kế an toàn | Vẫn bắt buộc |
| Cấu hình Jakarta Mail | Chọn `LOGIN`/`PLAIN` theo server | Chọn rõ `XOAUTH2` |
| Điều kiện hoạt động | Provider cho phép mật khẩu | Provider hỗ trợ XOAUTH2 và token đủ quyền |

Không có nghĩa mọi triển khai `AUTH PLAIN` đều gửi password ở dạng đọc được ngoài mạng: khi sử dụng TLS hợp lệ, dữ liệu AUTH được bảo vệ trong kênh TLS. Tuy vậy, TLS không giải quyết rủi ro lưu trữ và phạm vi quyền của mật khẩu dài hạn.

### 2.2. SMTP server phải quảng bá cơ chế được hỗ trợ

Sau khi thiết lập TLS và gửi lại `EHLO`, server có thể quảng bá:

~~~text
S: 250-smtp.example.com
S: 250-AUTH XOAUTH2 PLAIN LOGIN
S: 250 SIZE 35882577
~~~

Đây là ví dụ minh họa, không phải phản hồi bắt buộc của mọi nhà cung cấp.

Nếu server không hỗ trợ XOAUTH2 hoặc tài khoản không được phép dùng SMTP AUTH, chỉ thêm:

~~~properties
mail.smtp.auth.mechanisms=XOAUTH2
~~~

sẽ không làm server tự hỗ trợ tính năng này. Khi đó cần xem tài liệu của provider, chính sách tenant và khả năng dùng email sending API thay thế.

## 3. Bản chất của chuỗi xác thực XOAUTH2

Một số provider dùng payload SASL dạng:

~~~text
user=<mailbox-address>^Aauth=Bearer <access-token>^A^A
~~~

Trong đó `^A` biểu diễn ký tự điều khiển `Control-A` (`0x01`), không phải hai ký tự dấu mũ và A. Payload thường được base64-encode khi thực hiện `AUTH XOAUTH2` theo giao thức SMTP.

Ví dụ nội dung trước khi mã hóa, chỉ mang tính mô tả:

~~~text
user=notifications@example.com<0x01>auth=Bearer ACCESS_TOKEN<0x01><0x01>
~~~

**Không tự ghép chuỗi AUTH trong ứng dụng nếu thư viện SMTP đã hỗ trợ XOAUTH2.** Spring Mail dựa trên Jakarta Mail; SMTP provider tương thích có thể thực hiện định dạng và quá trình xác thực. Tự xử lý base64, control characters và giao tiếp SMTP bằng socket dễ gây lỗi giao thức và rò rỉ token.

### 3.1. Vì sao không đặt token vào header email?

Access token phục vụ **xác thực với SMTP server**. Nó không phải nội dung email và không được đưa vào:

~~~text
Authorization: Bearer <token>     # Không phải email header cần gửi
X-Access-Token: <token>           # Tuyệt đối không thêm
Subject: <token>                  # Không bao giờ
~~~

Header email có thể được chuyển qua nhiều hệ thống và lưu lâu dài. Token chỉ được truyền trong bước xác thực SMTP qua TLS hoặc tới endpoint HTTP token/API tương ứng.

## 4. Quy trình xác thực OAuth 2.0 khi gửi SMTP

Luồng phổ biến ở mức kiến trúc:

~~~mermaid
sequenceDiagram
    participant A as Spring application
    participant I as Identity provider
    participant M as SMTP server
    A->>I: Request access token
    I-->>A: Access token + expiry + scope
    A->>M: TLS / STARTTLS
    M-->>A: Secure SMTP session
    A->>M: EHLO, AUTH XOAUTH2
    M-->>A: Authentication success
    A->>M: MAIL FROM, RCPT TO, DATA
    M-->>A: Submission response
~~~

Đây là hai loại trao đổi riêng:

1. **Token acquisition:** dùng OAuth 2.0 grant để lấy token từ identity provider.
2. **SMTP submission:** dùng token như credential của `AUTH XOAUTH2` để nộp email.

Nếu việc lấy token thất bại, ứng dụng chưa cần mở phiên SMTP. Nếu token lấy được nhưng SMTP từ chối xác thực, nguyên nhân có thể là sai audience, scope, mailbox identity, policy hoặc token đã hết hạn.

### 4.1. Các grant flow hay gặp

| Flow | Ngữ cảnh | Lưu ý |
| --- | --- | --- |
| **Authorization Code** (có thể kèm PKCE) | Người dùng ủy quyền ứng dụng thay mặt họ | Token gắn với quyền người dùng; cần consent và refresh phù hợp |
| **Refresh Token** | Lấy access token mới sau lần ủy quyền ban đầu | Refresh token là secret cần bảo vệ; provider có chính sách rotation/revocation |
| **Client Credentials** | Workload/service gửi không cần người dùng tương tác | Chỉ dùng nếu provider cung cấp quyền app-only cho SMTP |
| **Service account + delegated authority** | Môi trường tổ chức được quản trị cấp quyền đại diện | Tùy provider; thường cần cấu hình quản trị và giới hạn scope |
| **Managed identity / workload identity federation** | Cloud workload xin token mà không lưu client secret dài hạn | Chỉ phù hợp nếu resource server SMTP hoặc API hỗ trợ identity/token đó |

Không tự suy luận **Client Credentials** luôn dùng được cho SMTP. Một SMTP provider có thể chỉ cho phép delegated user token, trong khi HTTP sending API lại hỗ trợ application token.

### 4.2. Access token và refresh token khác nhau

**Access token**:

- dùng để truy cập dịch vụ theo audience/scope được cấp;
- thường có thời hạn ngắn;
- được truyền vào SMTP XOAUTH2;
- không nên lưu như cấu hình cố định trong repository.

**Refresh token**:

- dùng để xin access token mới khi phù hợp với flow/provider;
- có thể sống dài hơn và chịu chính sách rotation/revocation;
- không được đưa vào SMTP `AUTH XOAUTH2` thay cho access token;
- phải nằm trong secure store có quyền hạn tối thiểu.

Nếu ứng dụng chỉ có refresh token nhưng dùng nó làm `spring.mail.password`, SMTP authentication thường thất bại vì SMTP mong đợi access token hợp lệ, không phải refresh token.

## 5. Bước chuẩn bị với nhà cung cấp email

Trước khi viết code Spring Mail, cần xác định những điều kiện phía nhà cung cấp:

1. SMTP AUTH có được bật ở cấp tổ chức/tenant và mailbox không?
2. SMTP server, port và chế độ TLS cần dùng là gì?
3. SMTP có hỗ trợ XOAUTH2 hay cơ chế khác không?
4. Cần đăng ký OAuth application/client ở đâu?
5. API permission hoặc scope dành riêng cho **SMTP sending** là gì?
6. Flow nào được hỗ trợ: delegated, app-only, service account, hay chỉ một số flow?
7. Cần admin consent, mailbox permission hoặc Send As permission không?
8. Địa chỉ `From` có bị ràng buộc với mailbox/alias được ủy quyền không?
9. Token endpoint và audience/resource cần dùng là gì?
10. Chính sách rate limit, quota, tenant restriction và audit áp dụng ra sao?

Một token có thể được cấp thành công nhưng SMTP AUTH vẫn thất bại nếu mailbox bị tắt SMTP submission hoặc service principal chưa được cấp quyền tương ứng.

### 5.1. Không nhầm “đăng nhập được” với “được quyền gửi”

Một user có thể đăng nhập thành công vào giao diện webmail hoặc lấy token cho một API khác nhưng không được phép SMTP AUTH. Tương tự, một app có thể có quyền đọc profile hoặc mailbox metadata nhưng không có quyền gửi mail.

Chẩn đoán cần kiểm tra cả:

- issuer, audience và scope/role của token;
- identity gắn với token;
- SMTP AUTH policy;
- sender/From permission;
- nhà cung cấp có chấp nhận flow đang dùng không.

### 5.2. Không chọn scope rộng hơn chỉ để lỗi biến mất

Nếu provider yêu cầu một scope có phạm vi mailbox rộng để dùng SMTP XOAUTH2, cần hiểu rủi ro và chính sách phê duyệt. Nhưng không nên mặc định cấp **mọi quyền đọc/ghi mail** cho ứng dụng nếu provider có phương thức gửi chuyên biệt với quyền hẹp hơn.

Cân nhắc sử dụng HTTP email-sending API có granular permission tốt hơn, nếu yêu cầu gửi không nhất thiết phải dùng SMTP.

## 6. Ví dụ nhà cung cấp: Google Workspace/Gmail

Gmail có hỗ trợ OAuth 2.0 cho các giao thức mail, trong đó có SMTP dùng cơ chế XOAUTH2 theo cấu hình và chính sách tương ứng.

Các điểm cần phân biệt:

- OAuth client phải được đăng ký và ủy quyền theo tài khoản/tổ chức.
- Token phải có scope được Gmail SMTP hỗ trợ. Một scope thường được nêu cho SMTP/IMAP/POP trong tài liệu Gmail OAuth là `https://mail.google.com/`; đây là scope **rộng**, nên cần đánh giá và chấp thuận phù hợp.
- Nếu dùng authorization code flow, quá trình lấy refresh token phụ thuộc consent, offline access và chính sách Google đang áp dụng.
- Trong Google Workspace, service account với **domain-wide delegation** có thể là một lựa chọn do quản trị viên cho phép; không tự động áp dụng cho tài khoản Gmail cá nhân.
- Chính sách app verification, restricted scope, tenant admin và mailbox có thể ảnh hưởng khả năng sử dụng.

Ví dụ logic:

~~~text
Google OAuth authorization/token flow
  -> access token cho mailbox được ủy quyền
  -> JavaMailSender SMTP AUTH XOAUTH2
  -> smtp.gmail.com (TLS theo cấu hình provider)
~~~

**Không giả định** một Google service account bình thường có thể gửi SMTP thay mặt bất kỳ người dùng nào mà không được quản trị viên Workspace cấp quyền đúng cách. Thông tin scope và chính sách có thể thay đổi; khi triển khai thật cần đối chiếu tài liệu chính thức của Google tại thời điểm cấu hình.

### 6.1. App password có phải OAuth2 không?

Không. **App password** (nếu tài khoản và chính sách provider cho phép) vẫn là một loại credential giống mật khẩu, không phải OAuth access token. Một số hệ thống dùng app password khi bật xác thực đa yếu tố, nhưng:

- không có cùng flow grant/refresh như OAuth;
- cách giới hạn quyền và thu hồi phụ thuộc provider;
- có thể bị quản trị viên hoặc loại tài khoản cấm;
- không nên coi app password là giải pháp lâu dài nếu chính sách đã yêu cầu OAuth.

Chỉ dùng app password nếu nhà cung cấp hiện hỗ trợ, tổ chức cho phép và cơ chế đó phù hợp yêu cầu bảo mật.

## 7. Ví dụ nhà cung cấp: Microsoft Exchange Online/Outlook

Exchange Online có các khả năng xác thực OAuth cho SMTP AUTH phụ thuộc loại tài khoản, quyền được cấp và cấu hình tenant/mailbox.

Những khái niệm thường gặp:

- **Delegated permissions:** ứng dụng hoạt động thay mặt một user đã ủy quyền. Tài liệu Microsoft có ví dụ scope SMTP delegated như `https://outlook.office.com/SMTP.Send`.
- **Application permissions:** ứng dụng gửi theo workload/app identity trong các cấu hình được Exchange Online hỗ trợ; có thể liên quan permission `SMTP.SendAsApp` và việc quản trị viên thiết lập quyền cho service principal/mailbox.
- **Token audience/resource:** ứng dụng phải lấy token dành cho dịch vụ Exchange/Outlook tương ứng. Với một số luồng app-only, tài liệu Microsoft sử dụng token request theo resource `https://outlook.office365.com/.default`; không thay thế bằng scope của Microsoft Graph nếu định xác thực SMTP.
- **SMTP AUTH policy:** dù token đúng, tổ chức hoặc mailbox vẫn có thể chặn SMTP AUTH.
- **Send As:** việc dùng địa chỉ From khác user/service principal được cấp quyền đòi hỏi chính sách thích hợp.

Điểm dễ sai là lấy **Microsoft Graph token** rồi truyền thẳng vào SMTP XOAUTH2. Token dùng cho Graph `Mail.Send` và token dành cho Exchange SMTP có thể khác audience và quyền. Không nên coi chúng hoán đổi được.

Khi công việc chỉ cần gửi email, HTTP API như Microsoft Graph `sendMail` có thể là một hướng khác; hãy so sánh giới hạn, yêu cầu quyền và hành vi trả kết quả trước khi chọn.

### 7.1. Mô hình delegated và app-only khác nhau

~~~text
Delegated:
  User consent / organization policy
      -> delegated SMTP token
      -> mailbox được ủy quyền

App-only (khi provider hỗ trợ và cấp quyền):
  Service principal / application identity
      -> application token
      -> SMTP permission + mailbox policy
~~~

Không có một cấu hình JavaMail nào tự cấp quyền app-only. Phần lớn công việc nằm ở identity provider, admin consent và cấu hình Exchange/tenant. Chỉ sau đó mới đặt token vào SMTP XOAUTH2.

**Lưu ý về phiên bản/chính sách:** Endpoint, permission, khả năng SMTP AUTH và hướng dẫn của Microsoft thay đổi theo thời gian, tenant và sản phẩm. Ví dụ scope ở đây phục vụ nhận diện khái niệm; phải xác minh bằng tài liệu chính thức cho môi trường đang triển khai.

## 8. Kiến trúc Spring Mail khi token thay đổi theo thời gian

Một cấu hình Spring Boot thông thường tạo một `JavaMailSender` singleton dùng các thuộc tính từ `spring.mail.*`. Điều này tiện khi username/password là credential ổn định.

Nhưng OAuth access token có thời hạn. Nếu chỉ khởi động ứng dụng một lần và đặt:

~~~yaml
spring:
  mail:
    password: ${OAUTH_ACCESS_TOKEN}
~~~

token sẽ có thể hết hạn sau khi ứng dụng đã chạy một thời gian. Việc cấp token mới phải được đưa vào vòng đời của **mỗi lần thực hiện SMTP authentication**, hoặc một lớp cache token biết tự làm mới.

Luồng mong muốn:

~~~text
MailService.send(mail)
     |
     v
AccessTokenProvider.getValidToken(mailbox)
     |
     +-- token còn hạn, trả cache
     |
     +-- token sắp hết hạn, refresh/acquire
     |
     v
SMTP sender với access token hiện tại
     |
     v
AUTH XOAUTH2 + send message
~~~

### 8.1. Tách token provider khỏi mail service

Một interface ở cấp ứng dụng:

~~~java
public interface SmtpAccessTokenProvider {
    /**
     * Trả về access token hợp lệ dành cho SMTP của mailbox.
     * Có thể lấy từ cache hoặc thực hiện OAuth token exchange.
     *
     * Ném exception theo contract ứng dụng nếu không lấy được token.
     */
    String getValidAccessToken(String mailboxAddress);
}
~~~

Mail service chỉ biết nó cần access token để xác thực SMTP; không cần biết flow là authorization code, client credentials hay workload identity.

Tầng implementation của provider sẽ biết:

- client registration nào dùng cho mailbox;
- access token lưu ở đâu và hết hạn lúc nào;
- refresh token/identity credential được bảo vệ thế nào;
- scope và audience do provider yêu cầu;
- khi refresh thất bại phải báo lỗi ra sao.

## 9. Ví dụ gửi email bằng JavaMailSenderImpl và XOAUTH2

Một cách đơn giản, dễ xác định vòng đời là tạo **sender ngắn hạn cho mỗi thao tác gửi**, lấy access token hợp lệ ngay trước khi tạo kết nối. Cách này tránh thay đổi `password` trên một bean `JavaMailSenderImpl` singleton trong lúc nhiều thread đang gửi.

### 9.1. Cấu hình ứng dụng

Ví dụ `application.yml`:

~~~yaml
app:
  smtp:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    mailbox: ${SMTP_MAILBOX}
    from: ${SMTP_FROM:notifications@example.com}
~~~

Đây là các thuộc tính do ứng dụng định nghĩa, không phải thuộc tính built-in bắt buộc của Spring Boot. Token không nằm trong YAML; nó được cấp qua `SmtpAccessTokenProvider`.

### 9.2. Mail service minh họa

~~~java
package com.example.mail.infrastructure;

import java.util.Properties;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OAuth2SmtpMailService {
    private final SmtpAccessTokenProvider accessTokens;
    private final String smtpHost;
    private final int smtpPort;
    private final String mailbox;
    private final String from;

    public OAuth2SmtpMailService(
            SmtpAccessTokenProvider accessTokens,
            @Value("${app.smtp.host}") String smtpHost,
            @Value("${app.smtp.port:587}") int smtpPort,
            @Value("${app.smtp.mailbox}") String mailbox,
            @Value("${app.smtp.from}") String from) {
        this.accessTokens = accessTokens;
        this.smtpHost = smtpHost;
        this.smtpPort = smtpPort;
        this.mailbox = mailbox;
        this.from = from;
    }

    public void sendText(
            String recipient,
            String subject,
            String body) {

        // Token phải dành cho SMTP resource/mailbox được phép sử dụng.
        String token = accessTokens.getValidAccessToken(mailbox);

        // Không sửa password/token trên singleton shared giữa các thread.
        JavaMailSenderImpl sender = createSender(token);
        MimeMessage message = sender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                    new MimeMessageHelper(message, false, "UTF-8");
            helper.setFrom(from);
            helper.setTo(recipient);
            helper.setSubject(subject);
            helper.setText(body);
        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Cannot prepare SMTP message", ex);
        }

        // MailException được truyền lên tầng điều phối để phân loại.
        // Trả về không lỗi chỉ nói lên SMTP submission, không phải Inbox delivery.
        sender.send(message);
    }

    private JavaMailSenderImpl createSender(String accessToken) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(smtpHost);
        sender.setPort(smtpPort);
        sender.setProtocol("smtp");
        sender.setUsername(mailbox);
        sender.setPassword(accessToken);
        sender.setDefaultEncoding("UTF-8");

        Properties props = new Properties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.auth.mechanisms", "XOAUTH2");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");

        sender.setJavaMailProperties(props);
        return sender;
    }
}
~~~

Các điểm chính:

1. `mailbox` được truyền làm SMTP username.
2. `accessToken` được truyền vào vị trí credential mà JavaMail dùng để xác thực; với `auth.mechanisms=XOAUTH2`, đó là OAuth bearer token, **không phải mật khẩu tài khoản**.
3. `mail.smtp.auth.mechanisms=XOAUTH2` chỉ cho phép cơ chế được yêu cầu theo cấu hình này, tránh fallback vô tình sang LOGIN/PLAIN.
4. `mail.smtp.starttls.required=true` yêu cầu nâng cấp kênh bảo mật qua STARTTLS trên cổng SMTP submission phù hợp.
5. `mail.smtp.ssl.checkserveridentity=true` yêu cầu kiểm tra tên máy chủ trong chứng chỉ TLS ở provider hỗ trợ.
6. Sender mới được tạo cho lần gửi, tránh race condition do gọi `setPassword(...)` trên một singleton shared.
7. Token cần còn đủ hạn để hoàn tất kết nối và SMTP authentication.

**Giới hạn của ví dụ:** không bao gồm implementation lấy token, retry, queue, template rendering, validation đầy đủ hoặc logic multi-tenant. Khi triển khai production, những phần đó cần policy rõ và kiểm thử với provider thực tế. Đặc biệt, `mail.smtp.auth.mechanisms` là thuộc tính SMTP provider; phiên bản Jakarta Mail/Angus Mail phải hỗ trợ `XOAUTH2`.

### 9.3. Vì sao không dùng một singleton rồi gọi setPassword cho từng email?

Cách dễ mắc lỗi:

~~~java
@Autowired
JavaMailSenderImpl sharedSender;

void sendWithToken(String token, MimeMessage mime) {
    sharedSender.setPassword(token);
    sharedSender.send(mime);
}
~~~

Nếu hai thread hoạt động:

~~~text
Thread A: setPassword(token-for-A)
Thread B: setPassword(token-for-B)
Thread A: sender.send(message-for-A)
~~~

Thread A có thể sử dụng credential của B. Đây là lỗi đặc biệt nguy hiểm trong hệ thống multi-account/multi-tenant. Nếu cần một sender singleton có performance tốt, hãy thiết kế một adapter thực hiện token resolution per connection, cô lập account identity và kiểm tra đồng thời thật kỹ; không chỉ thay đổi mutable password trước mỗi `send`.

### 9.4. Tạo sender mới có làm mất lợi ích connection pooling?

Ví dụ tạo sender mới ưu tiên tính minh bạch và an toàn về concurrency. Chi phí tạo object thường nhỏ so với chi phí mở SMTP connection/TLS. Nhưng với throughput cao, nhiều kết nối có thể làm tăng latency hoặc chạm giới hạn provider.

Trong production, cần cân nhắc:

- giới hạn số worker SMTP đồng thời;
- connection lifecycle và token expiry;
- quota theo mailbox/tenant;
- connection reuse nếu provider hỗ trợ và được kiểm soát riêng theo identity;
- retry/backoff và monitoring;
- lựa chọn HTTP sending API nếu cần scale lớn.

Không tự chia sẻ transport đã xác thực giữa các mailbox hoặc tenant khác nhau nếu không có thiết kế cô lập rõ ràng.

## 10. Token provider sử dụng Spring Security OAuth2 Client

Spring Security OAuth2 Client có thể hỗ trợ lấy và làm mới access token qua `OAuth2AuthorizedClientManager`, tùy grant flow và cấu hình. Tuy nhiên, thư viện này **không tự biến `JavaMailSender` thành SMTP XOAUTH2 sender**. Nó giúp giải quyết phần token acquisition; code mail sender vẫn phải truyền token vào SMTP mechanism thích hợp.

### 10.1. Ví dụ token provider cho workload app-only

Trong trường hợp nhà cung cấp **thực sự cho phép client credentials đối với SMTP resource**, một service có thể lấy token qua manager:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.stereotype.Component;

@Component
public class ClientCredentialsSmtpTokenProvider
        implements SmtpAccessTokenProvider {

    private final OAuth2AuthorizedClientManager manager;

    public ClientCredentialsSmtpTokenProvider(
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    @Override
    public String getValidAccessToken(String mailboxAddress) {
        OAuth2AuthorizeRequest request =
                OAuth2AuthorizeRequest
                        .withClientRegistrationId("smtp-workload")
                        .principal("mail-sender-service")
                        .build();

        OAuth2AuthorizedClient client = manager.authorize(request);
        if (client == null || client.getAccessToken() == null) {
            throw new IllegalStateException(
                    "Cannot authorize SMTP OAuth client");
        }

        OAuth2AccessToken token = client.getAccessToken();
        return token.getTokenValue();
    }
}
~~~

Giải thích:

- `smtp-workload` là registration ID do ứng dụng định nghĩa.
- Principal `mail-sender-service` là identity dùng để liên kết authorized client ở ví dụ workload.
- Manager phải được cấu hình với `OAuth2AuthorizedClientProvider` hỗ trợ client credentials và kho authorized client phù hợp.
- Manager có thể dùng lại hoặc xin token mới theo chính sách expiry; không nên tự tạo token mới cho mọi email nếu token còn hợp lệ.
- Tham số `mailboxAddress` được interface nhận nhưng **không tự cấp quyền thay mặt mailbox đó**. Provider thực tế phải bảo đảm app principal được phép gửi cho mailbox chỉ định.

Đây là ví dụ cho **flow app-only có điều kiện**. Nếu provider chỉ hỗ trợ delegated SMTP OAuth, cần dùng authorized client tương ứng người dùng và bảo vệ refresh token; không thể thay thế bằng đoạn client-credentials này.

### 10.2. Cấu hình client registration

Một cấu hình khái niệm:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          smtp-workload:
            provider: smtp-idp
            client-id: ${OAUTH_CLIENT_ID}
            client-secret: ${OAUTH_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - ${SMTP_OAUTH_SCOPE}
        provider:
          smtp-idp:
            token-uri: ${OAUTH_TOKEN_URI}
~~~

Giá trị `SMTP_OAUTH_SCOPE`, `OAUTH_TOKEN_URI` và client registration phải xuất phát từ tài liệu nhà cung cấp. Không sao chép ví dụ của một provider sang provider khác.

Đây cũng không có nghĩa mọi ứng dụng phải sử dụng client secret. Có thể dùng certificate-based credential, workload identity federation hoặc managed identity tùy platform và thư viện, nếu provider cho phép.

### 10.3. Dùng AuthorizedClientManager đúng ngữ cảnh

Spring Security có nhiều cách tổ chức OAuth authorized client. Với service nền không gắn với HTTP request hoặc authenticated end user, một implementation manager dựa trên `OAuth2AuthorizedClientService` thường phù hợp hơn biến thể dựa trên servlet request.

Với delegated flow, ứng dụng phải quản lý:

- người dùng đã ủy quyền;
- storage của authorized client và refresh token;
- refresh/revocation logic;
- tình huống user bị vô hiệu hóa hoặc consent bị thu hồi;
- mailbox identity được phép gửi;
- lỗi cần người dùng hoặc quản trị viên ủy quyền lại.

Không dùng một authorized client của người quản trị rồi mặc định gửi thay mặt tất cả mailbox.

## 11. Cache token và làm mới trước khi hết hạn

Access token thường có thời hạn nên cần có lifecycle rõ ràng:

~~~mermaid
flowchart TD
    A["Mail job chuẩn bị gửi"] --> B{"Có token cho resource/identity?"}
    B -->|Không| C["Acquire token"]
    B -->|Có| D{"Token còn đủ hạn?"}
    D -->|Có| E["Dùng token"]
    D -->|Sắp hết| C
    C --> F{"Acquire thành công?"}
    F -->|Có| E
    F -->|Không| G["Fail trước SMTP / lên lịch retry phù hợp"]
    E --> H["SMTP AUTH XOAUTH2"]
~~~

Một cache key có thể cần bao gồm:

~~~text
provider / tenant / client registration / mailbox identity / scopes
~~~

Không chỉ cache theo username nếu cùng username có thể dùng nhiều tenant, scope hoặc OAuth client khác nhau.

### 11.1. Safety margin

Ví dụ token hết hạn lúc 14:00:00. Ứng dụng không nên chỉ kiểm tra lúc 13:59:59 rằng token “chưa hết hạn” rồi bắt đầu quá trình gửi có thể kéo dài nhiều giây.

Một policy minh họa:

~~~java
boolean shouldRefresh(
        Instant expiresAt,
        Instant now,
        Duration safetyWindow) {
    return expiresAt == null
            || !expiresAt.isAfter(now.plus(safetyWindow));
}
~~~

Safety window có thể dựa trên timeout SMTP, clock skew và policy của provider. Không có một con số chung cho mọi ứng dụng.

### 11.2. Tránh refresh stampede

Nếu hàng trăm worker thấy token gần hết hạn cùng lúc và đều request token mới, identity provider có thể bị quá tải hoặc rate-limit.

Một token provider có thể sử dụng:

- cache theo identity/resource/scope;
- lock hoặc single-flight refresh cho cùng cache key;
- kiểm soát số request token đồng thời;
- backoff khi token endpoint lỗi tạm thời;
- xử lý refresh-token rotation theo contract provider;
- không lưu access token raw trong log/metric.

Khi refresh thất bại, không nên tiếp tục dùng token đã hết hạn với hy vọng SMTP sẽ chấp nhận.

### 11.3. Phân biệt token bị từ chối với SMTP bị chậm

**Lỗi lấy token** xảy ra trước khi gửi message; retry token acquisition theo chính sách thường chưa có nguy cơ email đã được gửi.

**Lỗi SMTP sau khi gửi dữ liệu** có thể xảy ra dù provider đã nhận email. Nếu ứng dụng tự “làm mới token rồi gửi lại nguyên message” sau mọi `MailException`, nó có thể gửi trùng.

Phải xác định lỗi xảy ra ở giai đoạn nào trước khi retry.

## 12. TLS vẫn là điều kiện cần

OAuth bearer token phải được bảo vệ trên đường truyền. SMTP thường có hai cách thiết lập TLS:

| Chế độ | Cổng thường gặp | Cách hoạt động |
| --- | --- | --- |
| **SMTP submission + STARTTLS** | 587 | Kết nối SMTP, yêu cầu STARTTLS rồi xác thực/gửi qua kênh TLS |
| **Implicit TLS / SMTPS** | 465 | Thiết lập TLS ngay khi mở kết nối, sau đó chạy SMTP |

Cổng cụ thể và chế độ được nhà cung cấp quy định; không nên suy ra chỉ từ số cổng.

### 12.1. STARTTLS bắt buộc

~~~properties
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
mail.smtp.ssl.checkserveridentity=true
~~~

`starttls.enable=true` yêu cầu dùng STARTTLS khi được hỗ trợ; `starttls.required=true` giúp tránh việc âm thầm tiếp tục một kết nối không được nâng cấp TLS nếu server không hỗ trợ STARTTLS. Cơ chế kiểm tra danh tính server giúp hạn chế kết nối tới host có chứng chỉ không đúng.

Không đặt `starttls.enable=false` hoặc bỏ `starttls.required` chỉ để “xử lý lỗi kết nối” nếu chính sách của ứng dụng yêu cầu bảo vệ credential qua TLS.

### 12.2. Implicit TLS trên cổng 465

Nếu provider yêu cầu TLS ngay khi kết nối:

~~~properties
mail.smtp.ssl.enable=true
mail.smtp.ssl.checkserveridentity=true
mail.smtp.auth=true
mail.smtp.auth.mechanisms=XOAUTH2
~~~

Kết hợp host và port phù hợp, ví dụ cổng 465 **nếu** tài liệu provider sử dụng cổng này. Không cấu hình vừa implicit TLS vừa STARTTLS theo cách không phù hợp với endpoint đã chọn.

### 12.3. Không vô hiệu hóa certificate verification

Để “fix” lỗi chứng chỉ, một số dự án dùng trust-all socket factory. Điều này có thể khiến access token bị gửi tới một server giả mạo.

Đúng hơn là:

- xác minh host;
- cấu hình truststore hợp lệ;
- cập nhật CA/certificate chain;
- kiểm tra proxy hoặc TLS inspection policy;
- đối chiếu endpoint nhà cung cấp.

Không gửi bearer token qua kênh TLS không đáng tin cậy.

## 13. Chính sách sender identity và From

Token được cấp cho một account hay application identity không đồng nghĩa được gửi dưới bất kỳ địa chỉ `From` nào.

Ví dụ:

~~~text
SMTP authentication identity:
  notifications@example.com

From header:
  billing@example.com
~~~

Nếu provider chưa cấp quyền Send As/alias cho `billing@example.com`, server có thể từ chối message hoặc chỉnh sửa sender theo chính sách.

Ứng dụng nên:

- quản lý `From` bằng cấu hình hoặc sender profile allowlist;
- không cho caller tùy ý chọn địa chỉ;
- xác minh mailbox/alias/domain đã được provider cho phép;
- phân biệt SMTP envelope sender, From và Reply-To;
- xem xét SPF, DKIM và DMARC để tăng khả năng xác thực domain khi nhận thư;
- không trông chờ OAuth thay thế chính sách chống giả mạo email.

### 13.1. Token cho một mailbox không tự có quyền với mailbox khác

Trong hệ thống multi-tenant:

~~~text
Tenant A -> mailbox A -> OAuth identity A
Tenant B -> mailbox B -> OAuth identity B
~~~

Cần cô lập token store, client configuration, recipient data, logs và rate limit theo tenant. Không dùng nhầm token A để xác thực mailbox B, kể cả khi cùng SMTP host.

## 14. Các lỗi thường gặp và cách chẩn đoán

Một SMTP server có thể trả lỗi xác thực như:

~~~text
535 5.7.x Authentication unsuccessful
530 5.7.x Authentication required
454 4.7.x Temporary authentication failure
~~~

Đây là ví dụ, không phải bộ mã chi tiết giống nhau ở mọi nhà cung cấp.

### 14.1. Bảng chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Điều cần kiểm tra |
| --- | --- | --- |
| `535 Authentication unsuccessful` | Token sai audience, hết hạn, không có scope, mailbox hoặc policy sai | Issuer, scope, token expiry, identity, SMTP AUTH policy |
| Server không quảng bá XOAUTH2 | Endpoint hoặc provider không hỗ trợ | `EHLO` sau TLS, tài liệu provider |
| `530 Must issue STARTTLS first` | Chưa thiết lập TLS | Port, STARTTLS required, truststore |
| Token endpoint trả unauthorized/invalid client | Client credential hoặc registration sai | Client ID/secret/cert, token endpoint |
| `invalid_grant` khi refresh | Refresh token hết hiệu lực, consent/revocation, clock policy | Flow ủy quyền, token store, yêu cầu ủy quyền lại |
| Authentication thành công nhưng `MAIL FROM` / `DATA` bị từ chối | Sender permission, domain policy, quota | From/Send As/alias, SMTP policy |
| Thời gian đầu gửi được rồi sau đó lỗi | Access token hết hạn | Refresh/cache/expiry safety window |
| Một tenant gửi được, tenant khác lỗi | Tenant/mailbox policy hoặc permission khác | Scope, tenant ID, SMTP AUTH state |
| SMTP timeout | Network, firewall, provider latency | DNS, port, timeout, TLS handshake |
| Mail được nhận nhưng không vào Inbox | Delivery/spam/bounce là giai đoạn sau | Provider events, SPF/DKIM/DMARC |

Không nên bắt mọi `MailException` rồi trả về thông báo “OAuth token hết hạn”. Một SMTP send failure có thể liên quan recipient, message size, quota, network hoặc provider policy không liên quan access token.

### 14.2. Lỗi Spring Mail

Với Spring Mail, những ngoại lệ thường cần phân biệt:

- `MailAuthenticationException`: vấn đề authentication do Spring Mail biểu diễn.
- `MailSendException`: lỗi nộp message/transport, có thể có lỗi theo message.
- `MailPreparationException`: lỗi chuẩn bị message theo tầng Spring.
- `MailException`: base class.

Ở tầng Jakarta Mail/provider, exception có thể bị bọc trong `getCause()` hoặc chuỗi `MessagingException.getNextException()`. Khi cần chẩn đoán, đọc cả giai đoạn lỗi và mã provider thay vì chỉ dựa vào text.

### 14.3. Token hết hạn giữa quá trình gửi

Một token có thể đủ hạn lúc lấy nhưng không còn hợp lệ khi bắt đầu SMTP authentication. Phương án phù hợp là:

1. Dùng cache có safety margin.
2. Phân biệt lỗi xác thực chắc chắn xảy ra **trước khi message được chấp nhận**.
3. Nếu chắc là authentication failure, có thể invalidate token và lấy lại token theo chính sách.
4. Tránh retry toàn bộ email một cách mù quáng nếu lỗi xảy ra **sau `DATA`** và kết quả chưa xác định.

Đây là điểm nối giữa bảo mật SMTP, idempotency và retry. **Token refresh có thể lặp lại**, nhưng **SMTP submission không mặc nhiên idempotent**.

## 15. Không bật debug làm lộ bearer token

SMTP debug rất hữu ích khi điều tra kết nối, nhưng có thể tiết lộ:

- AUTH command và base64 credential;
- access token;
- địa chỉ email và header;
- dữ liệu message tùy mức debug;
- server response với thông tin tenant/account.

Không dùng:

~~~properties
mail.debug=true
~~~

trên production mà không kiểm soát redaction, access và retention. Khi cần, bật log tối thiểu trong môi trường kiểm thử hoặc một phiên chẩn đoán có kiểm soát, đồng thời xác nhận provider/library có che nội dung AUTH thật sự.

Ví dụ log an toàn ở cấp ứng dụng:

~~~text
event=smtp_auth_attempt
provider=exchange-online
mailboxProfile=billing
tokenSource=oauth2
tokenExpiresSoon=false
result=FAILED
errorClass=MailAuthenticationException
correlationId=mail-job-752
~~~

Không log:

~~~text
accessToken=eyJ...
refreshToken=...
clientSecret=...
Authorization: Bearer ...
AUTH XOAUTH2 <base64-payload>
~~~

**Base64 không phải mã hóa bảo mật.** Chuỗi AUTH được base64-encode vẫn có thể giải mã để lấy bearer token.

## 16. Quản lý secret và quyền truy cập

Một hệ thống OAuth SMTP có thể cần bảo vệ:

- client secret hoặc private key dùng để xin token;
- refresh token của user;
- access token hiện tại;
- service account credentials hoặc federation configuration;
- danh sách mailbox/application permissions.

Các thực hành hữu ích:

1. Dùng secret manager hoặc cơ chế danh tính workload thay vì hard-code credential trong repository.
2. Chỉ cấp permission cần thiết cho một app/tenant/mailbox.
3. Giới hạn quyền đọc token store và môi trường runtime.
4. Không xuất token qua API response, error message hoặc log.
5. Thiết lập rotation, revocation và quy trình xử lý khi token bị lộ.
6. Theo dõi app consent, quyền Send As và các thay đổi chính sách SMTP.
7. Phân tách tài khoản gửi production với tài khoản test.
8. Dùng TLS bắt buộc và kiểm tra chứng chỉ.
9. Xóa/giới hạn dữ liệu token đã hết hạn theo retention phù hợp.
10. Rate-limit email để giảm thiệt hại nếu ứng dụng hoặc danh tính gửi bị lạm dụng.

Nếu access token bị lộ, thời hạn ngắn giúp giới hạn một phần cửa sổ lạm dụng. Nhưng refresh token hay private key bị lộ có thể cho phép xin token mới; các credential này cần được bảo vệ chặt chẽ hơn.

## 17. Khi nào nên dùng API gửi email thay vì SMTP?

Không phải nhà cung cấp nào cũng cung cấp cùng tính năng SMTP OAuth. Một số dịch vụ email giao dịch ưu tiên **HTTP API**:

~~~text
Spring application
   |
   | HTTPS request
   | OAuth bearer / API key / request signing
   v
Email provider API
   |
   +--> Tracking / provider ID
   +--> Webhook delivery / bounce
   +--> Rate limiting / templates
~~~

### 17.1. So sánh SMTP và HTTP API

| Tiêu chí | SMTP + OAuth XOAUTH2 | HTTP email API |
| --- | --- | --- |
| Giao thức | SMTP submission | HTTPS/REST hoặc giao thức provider |
| Credential | OAuth access token trong SMTP AUTH | OAuth token, API key, IAM signing hoặc cơ chế riêng |
| Spring integration | `JavaMailSender` / Jakarta Mail | HTTP client hoặc SDK của provider |
| Định dạng | MIME message | JSON payload hoặc MIME raw tùy API |
| Tracking | Thường cần provider-specific integration | Nhiều provider cung cấp message ID, status/webhook |
| Idempotency | SMTP thuần không có bảo đảm chung | Có thể có idempotency key tùy provider |
| Port/network | SMTP ports như 587/465 | Thường HTTPS 443 |
| Quyền gửi | SMTP AUTH policy/mailbox permissions | API permission/provider-specific policy |
| Khả năng thay provider | MIME/SMTP có tính chuẩn hóa cao | API riêng có thể cần adapter mới |

HTTP API không luôn dùng OAuth. Ví dụ:

- Một số transactional email service dùng API key riêng.
- Một số cloud service dùng ký request bằng IAM/workload credentials.
- Một số API dùng OAuth delegated/application permissions.

**Không gán nhãn mọi API key là OAuth token.** Các cơ chế này khác nhau về cấp quyền, rotation và bảo mật.

### 17.2. Kiến trúc để đổi transport

Nếu muốn có thể chuyển giữa SMTP và HTTP API:

~~~text
Business service
     |
     v
MailService interface
     |
     +-- SmtpOAuthMailAdapter
     |
     +-- ProviderHttpMailAdapter
     |
     +-- FakeMailAdapter for tests
~~~

Contract có thể là:

~~~java
public interface MailService {
    MailSubmissionResult submit(OutgoingMail request);
}

public record MailSubmissionResult(
        String localJobId,
        String providerMessageId,
        SubmissionStatus status) {
}

public enum SubmissionStatus {
    SUBMITTED,
    ACCEPTED_FOR_PROCESSING
}
~~~

Các trạng thái cần được định nghĩa theo provider thực tế. Một HTTP API trả `202 Accepted` có thể chỉ xác nhận job đã được tiếp nhận, **không** khẳng định thư đã tới Inbox. Tương tự, SMTP `250` sau `DATA` là submission acceptance, không phải final delivery.

### 17.3. Tại sao managed identity có thể phù hợp API hơn?

Một cloud sending API có thể hỗ trợ workload identity hoặc request signing trực tiếp. Điều đó giúp tránh lưu refresh token/user password trong ứng dụng. Nhưng không nên mặc định cùng managed identity ấy có thể xác thực SMTP XOAUTH2: SMTP server phải chấp nhận token đúng resource và flow.

Chọn kênh dựa trên yêu cầu nghiệp vụ, mức độ hỗ trợ provider, mô hình quyền và năng lực vận hành, thay vì cố ép một token API vào SMTP.

## 18. Kế hoạch chuyển từ password sang OAuth2

Khi một hệ thống đang dùng `spring.mail.username/password` và nhà cung cấp yêu cầu xác thực hiện đại, có thể chuyển theo từng bước:

1. **Kiểm kê:** xác định tất cả service, batch worker, scheduler và tài khoản SMTP đang dùng.
2. **Kiểm tra chính sách provider:** SMTP AUTH, XOAUTH2, grant flow, scope, sender permissions.
3. **Đăng ký ứng dụng:** OAuth client/service principal hoặc phương thức identity do provider yêu cầu.
4. **Cấp quyền tối thiểu:** chỉ những mailbox/tenant/domain cần thiết.
5. **Triển khai token provider:** acquisition, cache, refresh và lỗi token endpoint.
6. **Chuyển SMTP mechanism:** chọn `XOAUTH2`, cấu hình TLS và hostname verification.
7. **Kiểm thử có kiểm soát:** dùng mailbox test, không dùng người nhận production.
8. **Quan sát:** tách tỷ lệ lỗi token acquisition, SMTP authentication và email submission.
9. **Triển khai từng nhóm:** canary hoặc cấu hình theo mailbox/tenant, có rollback plan.
10. **Thu hồi credential cũ:** sau khi xác nhận đường gửi mới hoạt động và không còn consumer cũ.

### 18.1. Tránh rollout kiểu “đổi password thành token tĩnh”

Không nên:

~~~yaml
spring:
  mail:
    password: eyJ... # Access token được chép thủ công
~~~

Đây không phải migration hoàn chỉnh. Token có thể hết hạn và xuất hiện trong source/config backup. Cần có token lifecycle tự động và secure store.

### 18.2. Đảm bảo rollback không hạ cấp bảo mật

Khi chuyển đổi gặp lỗi, một cách rollback không phù hợp là:

- tắt TLS;
- bật trust-all certificate;
- mở lại Basic Authentication cho toàn tenant;
- ghi token trong log;
- dùng một tài khoản quản trị có quyền gửi rộng cho mọi ứng dụng.

Rollback cần trở về phương án được tổ chức cho phép và có kiểm soát; nếu provider đã cấm basic auth, cần sửa cấu hình token/provider hoặc tạm dừng gửi an toàn thay vì lách chính sách.

## 19. Kiểm thử OAuth2 SMTP

Cần test riêng việc **lấy token**, **chọn SMTP mechanism** và **nộp email**.

### 19.1. Unit test cho token provider

Các tình huống:

- token còn hạn: dùng cache;
- token sắp hết hạn: xin token mới;
- token endpoint bị timeout: không trả token đã hết hạn;
- client bị revoke: báo lỗi theo contract;
- hai thread cùng cần token: không tạo refresh storm;
- hai mailbox khác tenant: không dùng chung token sai scope;
- refresh token rotation: lưu credential mới theo cơ chế provider.

Với Spring Security manager, có thể mock `OAuth2AuthorizedClientManager` để trả authorized client giả. Không cần gọi identity provider thật trong unit test.

### 19.2. Unit test cho mail adapter

Với `OAuth2SmtpMailService`, nên tách factory tạo sender hoặc một SMTP adapter để test:

- `auth.mechanisms` chỉ gồm `XOAUTH2` khi được yêu cầu;
- host, port và TLS mode đúng;
- token được lấy sát thời điểm kết nối;
- sender không đổi password giữa các mailbox;
- lỗi token acquisition không bị ghi nhận thành delivery failure;
- adapter tạo message có From/To/Subject hợp lệ;
- không log access token.

Các test này kiểm tra cấu hình và hợp đồng, **không chứng minh provider thực sự chấp nhận token**.

### 19.3. Integration test

Một SMTP test server có thể kiểm tra MIME, TLS và việc gọi AUTH. Tuy nhiên, không phải SMTP mock nào cũng hỗ trợ XOAUTH2 hoặc xác minh token thực tế.

Nên phân tách:

1. Test SMTP giả lập để kiểm tra message format, retry, exception mapping.
2. Test identity/token mock để kiểm tra grant/refresh.
3. Integration test có kiểm soát với sandbox/tenant thử nghiệm của provider để kiểm tra OAuth + SMTP end-to-end.

### 19.4. Các case chẩn đoán cần có

| Case | Kỳ vọng |
| --- | --- |
| Token hợp lệ, đúng quyền | SMTP AUTH thành công, có thể submit |
| Token hết hạn | Provider từ chối auth; token source biết refresh |
| Token đúng chữ ký nhưng sai audience | Không dùng token này để SMTP AUTH |
| Thiếu SMTP send permission | Báo lỗi quyền; không retry vô hạn như lỗi mạng |
| SMTP AUTH bị tắt ở mailbox | Chẩn đoán chính sách, không tự sửa TLS |
| Host certificate không hợp lệ | Từ chối kết nối |
| Server không hỗ trợ STARTTLS nhưng client yêu cầu | Từ chối kết nối an toàn |
| Server không hỗ trợ XOAUTH2 | Không fallback im lặng sang password |
| Client credentials không được provider hỗ trợ | Báo lỗi flow, chọn delegated hoặc API phù hợp |
| Token endpoint 429/5xx | Retry token acquisition theo giới hạn |
| SMTP timeout sau DATA | Giữ trạng thái UNKNOWN nếu kết quả nộp thư chưa rõ |
| Tải cao nhiều thread/mailbox | Không trộn token, kiểm soát rate limit |

Không chạy những test cố tình làm lộ credential hoặc gửi thư thật tới người nhận ngoài phạm vi thử nghiệm.

## 20. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đặt access token tĩnh vào `spring.mail.password` | Hết hạn, gửi lỗi sau một thời gian | Token provider có refresh/cache |
| Dùng refresh token làm SMTP password | Authentication thất bại | Đổi refresh token thành access token đúng resource |
| Dùng Graph/API token để gửi SMTP | Sai audience/scope | Xin token dành cho SMTP resource |
| Chọn `LOGIN`/`PLAIN` nhưng truyền OAuth token | Server hiểu token như mật khẩu thường | Bật `XOAUTH2` theo provider |
| Bật XOAUTH2 khi SMTP server không hỗ trợ | Authentication không hoạt động | Kiểm tra EHLO/docs/provider |
| Giả định client credentials luôn hỗ trợ SMTP | Không xin được token đúng quyền | Xác nhận grant flow được provider hỗ trợ |
| Dùng mailbox A nhưng token được cấp cho B | Sai identity/quyền | Ràng buộc mailbox, token, From |
| Dùng một singleton sender và `setPassword` mỗi thread | Race/trộn token giữa account | Sender per call hoặc adapter cô lập token per connection |
| Tắt STARTTLS hoặc hostname verification để “fix” lỗi | Có thể lộ bearer token | TLS bắt buộc, sửa truststore/cert đúng |
| Log AUTH XOAUTH2 base64 | Token bị lộ | Redact và hạn chế protocol debug |
| Refresh token trong repository | Rủi ro credential dài hạn | Secret manager/secure authorized client store |
| Retry email ngay sau mọi auth/transport exception | Có thể gửi trùng sau DATA timeout | Phân loại giai đoạn, dùng idempotency |
| Bật From tùy ý từ API | Có thể giả danh sender | Allowlist sender profile/Send As |
| Coi OAuth thay thế SPF/DKIM/DMARC | Delivery/reputation không được bảo đảm | Thiết lập xác thực domain riêng |
| Coi SMTP accepted là Delivered | Báo sai Inbox delivery | Provider event/DSN/webhook |
| Coi mọi HTTP sending API là OAuth | Thiết kế secret/permission sai | Phân biệt API key, IAM, OAuth |

## 21. Ví dụ tổng hợp: dịch vụ gửi hóa đơn

Giả sử một ứng dụng gửi PDF hóa đơn từ mailbox `billing@example.com`. Do nhà cung cấp yêu cầu OAuth2 SMTP, hệ thống gồm:

~~~text
OrderApplicationService
  |
  +-- commit invoice
  |
  +-- store mail outbox job
            |
            v
      MailWorker
            |
            v
  OAuth2SmtpMailService
            |
            +-- SmtpAccessTokenProvider
            |       |
            |       +-- token cache / expiry check
            |       +-- identity provider
            |
            +-- JavaMailSenderImpl
                    |
                    +-- TLS
                    +-- AUTH XOAUTH2
                    +-- MAIL FROM / RCPT TO / DATA
                    |
                    v
                 SMTP server
~~~

Trình tự:

1. Nghiệp vụ tạo hóa đơn và outbox job có message key ổn định.
2. Worker nhận job và chuẩn bị MIME message (plain text/HTML, PDF).
3. Token provider lấy access token hợp lệ cho identity được phép gửi từ mailbox billing.
4. Mail adapter mở TLS, xác minh chứng chỉ và xác thực bằng XOAUTH2.
5. SMTP server chấp nhận message hoặc trả lỗi.
6. Nếu submission không lỗi, worker đánh dấu `SUBMITTED`; không đánh dấu `DELIVERED`.
7. Nếu token acquisition hoặc auth bị từ chối, worker phân loại lỗi trước khi quyết định retry.
8. Nếu SMTP timeout khi kết quả không rõ, worker áp dụng chính sách idempotency và trạng thái UNKNOWN.
9. Khi provider có bounce/delivery events, hệ thống cập nhật trạng thái giao thư riêng.

Điểm quan trọng là **xác thực OAuth** và **độ tin cậy của luồng gửi email** là hai mối quan tâm độc lập nhưng liên quan. OAuth đảm bảo ứng dụng dùng đúng credential/permission; outbox, retry và tracking đảm bảo yêu cầu gửi được quản lý bền vững.

### 21.1. Trường hợp không cần SMTP

Nếu provider cung cấp API gửi hóa đơn qua HTTPS với quyền gửi phù hợp, workflow có thể thay `OAuth2SmtpMailService` bằng `ProviderHttpMailAdapter`. Phần tạo outbox job, message key, rendering và trạng thái nghiệp vụ có thể giữ nguyên. Việc tách contract khỏi transport giúp ứng dụng chuyển đổi mà không phải thay đổi nghiệp vụ hóa đơn.

## 22. Checklist trước khi triển khai production

1. **Provider support:** SMTP AUTH và XOAUTH2 có hỗ trợ cho loại tài khoản/tenant này không?
2. **Grant flow:** delegated, app-only hay service account có được cho phép không?
3. **Scope/audience:** access token thực sự dành cho SMTP resource nào?
4. **Mailbox authorization:** identity/token có quyền gửi từ mailbox/alias không?
5. **TLS:** STARTTLS required hoặc implicit TLS đúng endpoint, xác minh chứng chỉ.
6. **Client config:** `mail.smtp.auth.mechanisms=XOAUTH2` và không fallback im lặng sang password.
7. **Token lifecycle:** cache, refresh, safety window, revoke và xử lý refresh failure.
8. **Concurrency:** không sửa credential trên sender dùng chung giữa nhiều thread/tenant.
9. **Secret storage:** không hard-code token, client secret hoặc refresh token.
10. **Logging:** không log access token, AUTH payload, raw SMTP authentication trace.
11. **Error mapping:** phân biệt token endpoint, SMTP AUTH, sender policy và submission failure.
12. **Retry:** không tự gửi lại nguyên email sau timeout với kết quả không xác định.
13. **Observability:** theo dõi auth failure, token refresh, SMTP latency và submission status.
14. **Tests:** kiểm thử token lifecycle và SMTP XOAUTH2 trên tenant/sandbox được kiểm soát.
15. **Provider lifecycle:** kiểm tra thay đổi policy/API và chuẩn bị phương án chuyển sang HTTP API.

## 23. Những điều cần nhớ

- **OAuth 2.0** cấp access token theo danh tính và quyền; **SMTP XOAUTH2** là cách SMTP dùng token để xác thực.
- Access token dùng trong `AUTH XOAUTH2` không phải mật khẩu mailbox và không phải refresh token.
- SMTP provider phải hỗ trợ XOAUTH2 và token phải có đúng audience, scope, mailbox permission.
- Trong Spring Mail, có thể cấu hình `mail.smtp.auth.mechanisms=XOAUTH2` và truyền access token vào vị trí credential của `JavaMailSenderImpl`.
- Access token hết hạn nên phải có token provider làm mới theo vòng đời thực tế; không đặt token tĩnh trong cấu hình.
- Không sửa password/token trên sender singleton dùng chung giữa nhiều thread hoặc tenant.
- TLS và xác minh chứng chỉ vẫn cần thiết để bảo vệ bearer token.
- Các nhà cung cấp có flow và permission khác nhau; không sao chép token hoặc scope giữa Gmail, Exchange Online và API khác.
- HTTP API dùng OAuth, API key hoặc IAM signing có thể là lựa chọn tốt hơn SMTP tùy nhu cầu.
- Gửi thành công qua SMTP chỉ xác nhận kết quả submission; không bảo đảm email đã tới Inbox.

Trong Spring Framework Mail, triển khai “OAuth2 SMTP” đúng nghĩa không chỉ là thay chuỗi password bằng một token. Ứng dụng cần **lấy token đúng quyền, làm mới token an toàn, chọn cơ chế SMTP AUTH phù hợp, bảo vệ kết nối bằng TLS và xử lý kết quả gửi độc lập với lỗi xác thực**. Khi chia rõ những trách nhiệm này, hệ thống vừa thích ứng với chính sách bảo mật hiện đại của nhà cung cấp, vừa giữ được luồng gửi email có thể vận hành và kiểm soát.

### Tài liệu tham khảo

- **Spring Framework Reference — Email:** `JavaMailSender`, `JavaMailSenderImpl` và `MimeMessageHelper`.
- **Spring Boot Reference — Sending Email:** `spring.mail.*` và custom mail configuration.
- **Jakarta Mail / Angus Mail SMTP provider documentation:** `mail.smtp.auth.mechanisms`, `XOAUTH2`, TLS, STARTTLS và SMTP properties.
- **Spring Security Reference — OAuth 2.0 Client:** `OAuth2AuthorizedClientManager`, client registration và authorized client lifecycle.
- **RFC 6749 — OAuth 2.0 Authorization Framework:** authorization grants và access token.
- **RFC 6750 — Bearer Token Usage:** bearer token và yêu cầu bảo vệ credential.
- **RFC 7628 — A Set of Simple Authentication and Security Layer (SASL) Mechanisms for OAuth:** cơ chế SASL OAuth và quan hệ với protocol client.
- **RFC 3207 — SMTP Service Extension for Secure SMTP over TLS:** STARTTLS.
- **RFC 4954 — SMTP Service Extension for Authentication:** SMTP AUTH.
- **Google Workspace/Gmail official documentation — OAuth 2.0 for mail protocols:** XOAUTH2, scope và chính sách cấp quyền.
- **Microsoft Learn — Authenticate an IMAP, POP or SMTP connection using OAuth:** permissions, SMTP AUTH policies và delegated/app-only scenarios.
