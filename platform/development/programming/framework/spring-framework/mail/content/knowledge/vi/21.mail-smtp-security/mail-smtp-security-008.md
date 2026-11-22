# Xoay vòng secret và xử lý secret hết hạn trong Spring Framework Mail

Ứng dụng dùng Spring Framework Mail thường cần thông tin xác thực để đăng nhập SMTP relay: username/password, app password, credential dành riêng cho dịch vụ hoặc access token OAuth2/XOAUTH2. Những giá trị này là **secret**. Secret có thể bị lộ, bị thu hồi, hết hạn hoặc phải thay định kỳ theo chính sách bảo mật. Nếu ứng dụng chỉ cấu hình một password lúc triển khai rồi không có quy trình cập nhật, việc thay credential có thể làm toàn bộ email ngừng gửi; nếu lưu password trong mã nguồn, một lần lộ repository cũng có thể dẫn đến lạm dụng tài khoản gửi thư.

**Xoay vòng secret (secret rotation)** là quy trình tạo hoặc nhận credential mới, phân phối đến ứng dụng, chuyển lưu lượng sang credential mới, xác minh hoạt động và thu hồi credential cũ. Quá trình này cần kiểm soát đồng thời hai mục tiêu:

1. **Bảo mật:** credential cũ không còn được sử dụng sau khi thu hồi; credential mới không bị đưa vào log, repository hoặc response.
2. **Tính liên tục:** không làm mất thông báo bắt buộc, không gây bão retry khi SMTP AUTH thất bại và không gửi lại email đã được submit thành công.

Trong Spring Mail, bản thân JavaMailSender không quản lý lịch hết hạn, không tự lấy secret mới từ vault và không tự thay credential chỉ vì secret trong kho đã đổi. Các trách nhiệm đó thuộc cấu hình ứng dụng, hệ thống quản lý secret và quy trình vận hành.

## 1. Những secret nào liên quan đến SMTP?

Một hệ thống có thể có nhiều dạng thông tin xác thực. Chúng không có cùng chu kỳ sống:

| Loại | Ví dụ | Điều cần xoay vòng |
| --- | --- | --- |
| SMTP password | Username và password dành cho SMTP AUTH | Thay password, cập nhật sender, thu hồi password cũ |
| App password | Mật khẩu dành riêng cho ứng dụng, nếu provider hỗ trợ | Tạo app password mới, triển khai, hủy cái cũ |
| SMTP API credential | Token/secret do provider cấp để dùng SMTP | Tạo credential mới theo cơ chế provider |
| OAuth2 access token | Token ngắn hạn dùng với SASL XOAUTH2 | Làm mới token trước khi hết hạn, không coi như password tĩnh |
| OAuth2 refresh token | Token để lấy access token mới, nếu flow có | Bảo vệ và thay khi bị thu hồi/rotation theo provider |
| Secret-manager access | Identity hoặc credential để đọc vault | Quản lý quyền đọc, thời hạn và vòng đời riêng |
| TLS private key (nếu có) | Chứng chỉ máy khách trong kịch bản mTLS | Gia hạn key/certificate theo quy trình TLS |

Tài liệu tập trung vào secret xác thực SMTP. **TLS certificate, DKIM private key và SPF/DMARC là các chủ đề liên quan nhưng không đồng nghĩa SMTP password.** Thay password SMTP không tự thay DKIM key; thay DKIM key không tự khắc phục lỗi SMTP AUTH.

### Ai sở hữu credential?

Với hệ thống production, nên dùng identity hoặc account dành riêng cho ứng dụng, có quyền tối thiểu cần thiết. Không nên dùng mật khẩu mailbox cá nhân của một nhân viên làm credential lâu dài cho service.

Nếu có nhiều ứng dụng cùng dùng một credential, việc xoay vòng sẽ tác động đồng thời đến tất cả. Khi có thể, tách credential theo hệ thống hoặc workload giúp giới hạn phạm vi ảnh hưởng và xác định trách nhiệm sử dụng.

### Secret không chỉ là chuỗi password

Một secret record có thể gồm:

- Giá trị xác thực (không được ghi log).
- Username hoặc principal.
- Secret version/credential ID.
- Thời điểm tạo.
- Thời điểm hết hạn hoặc lịch đổi theo chính sách.
- Trạng thái: active, staged, revoked, expired.
- Phạm vi quyền và tài khoản/SMTP endpoint tương ứng.
- Metadata phục vụ audit, không chứa password.

Không phải provider nào cũng cung cấp đầy đủ metadata hết hạn; nếu không có expiresAt, hãy quản lý lịch rotation nội bộ thay vì giả định secret không bao giờ hết hạn.

## 2. Vòng đời của một SMTP secret

Một secret có thể đi qua các trạng thái:

~~~text
PROVISIONED
    |
    v
STAGED (đã tạo, chưa dùng cho production)
    |
    v
ACTIVE (đang được một hoặc nhiều sender sử dụng)
    |
    v
RETIRING (các sender đang chuyển sang bản mới)
    |
    v
REVOKED / EXPIRED (không được dùng lại)
~~~

Trạng thái thực tế phụ thuộc secret manager và provider. Một số nơi có version stage như current/previous, một số nơi cấp hai credential độc lập; không nên giả định mọi provider hỗ trợ hai password cùng hiệu lực.

### Sự khác biệt giữa rotation, refresh và revoke

| Thao tác | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Rotate | Chuyển từ credential cũ sang credential mới, có kiểm soát | Tạo SMTP password/app password mới |
| Refresh | Lấy phiên bản/giá trị hiện hành hoặc làm mới token ngắn hạn | Lấy OAuth2 access token mới |
| Revoke | Hủy hiệu lực của một credential | Vô hiệu hóa password cũ |
| Expire | Credential hết thời hạn theo provider/policy | Access token hết hạn |
| Roll back | Quay về phiên bản cấu hình/credential trước khi cutover | Chỉ khả thi nếu credential cũ vẫn hợp lệ |
| Roll forward | Khắc phục bằng phiên bản credential mới hơn | Cần làm khi credential cũ đã bị thu hồi |

Một secret đã bị revoke thường **không thể dùng để rollback**, ngay cả khi cấu hình ứng dụng vẫn giữ version cũ. Vì vậy, kế hoạch rollback phải được thiết kế trước khi thu hồi.

## 3. Điều gì xảy ra khi secret hết hạn?

Một ứng dụng có thể hoạt động bình thường nhiều tuần rồi đột nhiên nhận lỗi xác thực. Các tình huống phổ biến:

- Password bị thay ở SMTP provider nhưng cấu hình Spring vẫn dùng password cũ.
- App password bị thu hồi bởi quản trị viên.
- SMTP service account bị khóa hoặc mất quyền gửi.
- Access token OAuth2 hết hạn và không được làm mới.
- Refresh token bị revoke hoặc consent/quyền truy cập thay đổi.
- Một pod dùng secret version cũ trong khi pod khác đã cập nhật.
- Secret manager đã cấp bản mới nhưng ứng dụng vẫn giữ cấu hình cũ trong bean.

Kết quả có thể là lỗi xác thực SMTP, ví dụ phản hồi thuộc nhóm 5xx như **535 Authentication credentials invalid** ở một số provider. Một số relay dùng mã tạm thời thuộc nhóm 4xx để mô tả authentication service unavailable, rate limit hoặc chính sách khác. **Không suy luận nguyên nhân chỉ từ một mã duy nhất**: phải xem cả SMTP reply, enhanced status code, transport exception và tài liệu của provider.

### Tác động lên luồng nghiệp vụ

| Luồng | Nếu SMTP AUTH thất bại |
| --- | --- |
| OTP/reset password | Người dùng chưa thể nhận mã/link; cần phản hồi và phương án xử lý phù hợp |
| Xác nhận đơn hàng | Không được rollback đơn hàng đã commit chỉ vì email lỗi; giữ yêu cầu trong outbox |
| Hóa đơn/biên nhận | Đánh dấu chưa submit, cảnh báo và xử lý sau khi credential phục hồi |
| Newsletter/marketing | Có thể hoãn, hết hạn hoặc hủy theo chính sách |
| Worker gửi nền | Không được retry credential sai liên tục như lỗi mạng thông thường |

**Sai password là vấn đề xác thực của cả hệ thống**, không phải lỗi của từng địa chỉ người nhận. Không đánh dấu hàng nghìn email là “recipient invalid” khi nguyên nhân thực là SMTP credential hết hạn.

## 4. Mô hình luồng cấu hình của Spring Boot Mail

Khi dùng Spring Boot Mail starter và auto-configuration, cấu hình như host, port, username và password thường được bind từ cấu hình môi trường vào MailProperties, sau đó được dùng để cấu hình JavaMailSenderImpl.

~~~mermaid
flowchart TD
    A["Secret manager / deployment config"] --> B["Spring Environment / MailProperties"]
    B --> C["JavaMailSenderImpl"]
    C --> D["Jakarta Mail Session / SMTP Transport"]
    D --> E["SMTP AUTH"]
    E --> F["SMTP relay"]
~~~

Ví dụ cấu hình không chứa secret cụ thể:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: smtp-application-user
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
~~~

Trong ví dụ, **password không nằm trong file cấu hình**. Có thể cấp `SPRING_MAIL_PASSWORD` như một biến môi trường được hệ thống triển khai chèn từ secret store, hoặc dùng cơ chế secret manager/config integration đã được cấu hình. Spring Boot hỗ trợ mapping environment variable sang thuộc tính `spring.mail.password`.

### Không cam kết tự động reload

Nếu ứng dụng đã khởi động với một mật khẩu, chỉ cập nhật giá trị trong vault **không có nghĩa JavaMailSenderImpl đang chạy đã đổi password**. Trong cách cấu hình thông thường:

- Property đã được bind khi application context được tạo.
- Bean JavaMailSenderImpl có thể tiếp tục giữ username/password đã cấu hình.
- Thay biến môi trường của deployment không làm thay đổi môi trường của một process đang chạy.
- Secret file được mount và cập nhật cũng không tự động làm bean JavaMailSenderImpl bind lại.

Để nhận credential mới, cần một chiến lược rõ: **restart/rolling deployment**, **thay bean thông qua cơ chế refresh được xác minh**, hoặc **một adapter credential-aware đọc secret mới và thay sender an toàn**. Không nên dựa vào giả định framework tự phát hiện mọi rotation.

### Spring Cloud RefreshScope có giải quyết tự động không?

Nếu hệ thống sử dụng Spring Cloud với cơ chế refresh, có thể thiết kế bean refreshable. Tuy nhiên, tính đúng đắn còn phụ thuộc property source, scope của bean, đường gọi qua proxy, tài nguyên đang được dùng và cách secret store thông báo thay đổi. RefreshScope **không phải một bảo đảm mặc định** của Spring Boot Mail. Cần kiểm thử thực tế trước khi dùng nó làm cơ chế rotation production.

## 5. Lưu secret ở đâu?

Secret nên có một nơi quản lý có quyền truy cập và audit rõ ràng, chẳng hạn vault, cloud secret manager, hoặc cơ chế secret của nền tảng triển khai. Ứng dụng chỉ cần quyền đọc đúng secret của mình.

### Nên làm

- Lưu SMTP credential ngoài repository và image/container artifact.
- Cấp quyền đọc theo service identity, môi trường và tenant nếu cần.
- Dùng secret version hoặc revision để biết ứng dụng đang dùng bản nào.
- Phân biệt secret staging với secret production.
- Mã hóa dữ liệu lưu/truyền theo cơ chế nền tảng.
- Kiểm tra audit truy cập secret và những thay đổi quyền.
- Không truyền credential trong URL query, command line hoặc HTTP response.
- Giới hạn người có thể xem/rotate/revoke credential.

### Không nên làm

~~~yaml
# KHÔNG NÊN: password thật trong repository
spring:
  mail:
    username: team-mailbox@example.com
    password: "hardcoded-real-secret"
~~~

Không đưa file chứa secret vào Git rồi chỉ thêm .gitignore sau đó. Nếu secret đã commit, việc xóa ở commit mới không xóa nó khỏi Git history. Khi credential bị lộ, cần **rotate/revoke** và xử lý lịch sử/artifact theo chính sách, không coi “xóa dòng cấu hình” là khắc phục đầy đủ.

### Biến môi trường có an toàn tuyệt đối không?

Biến môi trường có thể tiện cho cấu hình container, nhưng không phải một kho bảo mật đầy đủ. Người có quyền truy cập process/container, crash dump hoặc một số công cụ chẩn đoán có thể đọc được giá trị. Secret vẫn cần được cung cấp qua đường triển khai đáng tin cậy, với quyền hạn và audit rõ ràng.

### File mount từ secret store

Một hệ thống orchestration có thể đưa secret thành file mount. Nếu dùng cách này:

- Chỉ service account cần thiết được đọc.
- File không được web server phục vụ hoặc backup ra nơi không phù hợp.
- Thao tác update file nên tránh để ứng dụng đọc dữ liệu đang ghi dở.
- Ứng dụng cần biết khi nào file đổi và chủ động cập nhật sender.
- Secret cũ có thể vẫn nằm trong memory của process sau khi file đã thay.

Việc file mount cập nhật không đồng nghĩa SMTP sender dùng credential mới. Cần một bước **reload hoặc restart có kiểm soát**.

## 6. Rotation không gián đoạn khi provider hỗ trợ hai credential

Chiến lược ưu tiên là **overlapping credentials**: credential cũ và mới cùng hợp lệ trong một khoảng thời gian chuyển tiếp.

~~~text
Thời gian ───────────────────────────────────────────────>

Credential A:  [ ACTIVE ][ DRAINING ][ REVOKED ]
Credential B:             [ STAGED ][ ACTIVE -----------]
                         |         |
                         |         +-- Thu hồi A sau xác nhận
                         +------------ Tạo, kiểm tra B
~~~

### Quy trình chi tiết

1. **Lập inventory:** xác định tất cả workload, instance, tài khoản SMTP, môi trường và job có dùng credential A.
2. **Xác nhận provider hỗ trợ overlap:** có thể là hai app passwords, hai SMTP credentials hoặc hai service accounts có quyền gửi tương đương.
3. **Tạo credential B:** cấp đúng quyền tối thiểu, giữ secret trong secret manager.
4. **Staging:** lưu version B ở trạng thái chưa được dùng bởi production hoặc dùng cho canary.
5. **Kiểm tra B:** xác thực kết nối, TLS, quyền gửi, địa chỉ From được cho phép và canary email trên môi trường được phép.
6. **Triển khai B:** rolling restart hoặc hot-swap sender, ghi nhận instance nào đã chuyển version.
7. **Giám sát:** quan sát SMTP AUTH failures, rate, queue age và submission success.
8. **Xác nhận A không còn được dùng:** loại bỏ instance cũ và các worker/job chưa cutover; tránh bỏ sót consumer.
9. **Thu hồi A:** hủy hiệu lực credential cũ ở provider.
10. **Hậu kiểm:** xác nhận không có pod vẫn dùng A; audit rotation và trạng thái gửi.

### Vì sao cần khoảng chồng lấn?

Trong rolling deployment, một số pod vẫn chạy với A trong lúc pod khác đã dùng B. Nếu revoke A ngay sau khi tạo B, những pod chưa được rollout có thể bị lỗi SMTP AUTH. Khoảng chồng lấn cho phép dịch chuyển mà không cần dừng tất cả.

Khoảng chồng lấn phải đủ cho rollout và các kết nối đang hoạt động, nhưng không kéo dài vô hạn vì credential cũ là rủi ro tồn dư. Thời hạn cụ thể tùy hạ tầng và chính sách.

### Hạn chế cần nhớ

**Không phải SMTP provider nào cũng cho phép hai password cùng hiệu lực trên một account.** Nếu đổi password là vô hiệu hóa ngay password cũ, không được áp dụng nguyên vẹn quy trình overlap. Có thể cần tạo một service account thứ hai, một SMTP credential riêng, hoặc chuyển sang quy trình cutover có thời gian ngừng ngắn.

## 7. Rotation khi provider chỉ cho một credential

Một số hệ thống thay password hiện tại theo cách làm password cũ bị hủy ngay. Khi đó rất khó đạt zero downtime nếu có nhiều replica.

Quy trình có thể là:

1. Chọn thời gian cutover ít ảnh hưởng và thông báo cho các bên liên quan.
2. Bảo đảm outbox giữ email giao dịch bền vững.
3. Tạm dừng hoặc hạn chế dispatch trước thời điểm đổi, tránh tăng lỗi và retry.
4. Thay password ở provider và ghi vào secret manager.
5. Cập nhật tất cả instance bằng rolling restart hoặc thay sender.
6. Thử xác thực/kết nối với credential mới; chỉ mở lại dispatch khi thành công.
7. Drain backlog theo rate limiter, không gửi dồn toàn bộ.
8. Giám sát SMTP AUTH, retry và backlog sau cutover.

Nếu ứng dụng có thể duy trì hai account có quyền From hợp lệ, có thể tạo overlap ở cấp **hai account** thay vì hai password trên một account. Tuy nhiên, cần kiểm tra chính sách sender, SMTP AUTH identity, quota và quyền relay; không giả định credential mới tự động có quyền gửi mọi địa chỉ From.

### Hạn chế của rollback

Sau khi password cũ bị vô hiệu hóa, rollback image/deployment chứa password cũ sẽ tiếp tục thất bại. Một phương án khắc phục thực tế là **roll forward**: cấp credential hợp lệ, cập nhật secret store và triển khai lại. Không nên viết runbook “rollback về credential A” nếu A đã bị revoke.

## 8. Kiểm tra credential mới trước khi cutover

Một credential tồn tại trong secret manager chưa chắc đã gửi email thành công. Cần xác minh các tầng:

| Bước | Điều được xác nhận | Điều chưa được chứng minh |
| --- | --- | --- |
| Đọc secret | Workload có quyền lấy đúng version | SMTP chấp nhận credential |
| TLS connection | Kết nối bảo mật thiết lập được | Username/password đúng |
| SMTP AUTH | Server chấp nhận xác thực | Có quyền gửi từ địa chỉ From mong muốn |
| SMTP submission canary | Relay chấp nhận thư thử | Thư đã đến inbox của mọi người nhận |
| Delivery/bounce event | Provider tiếp tục xử lý/giao thư | Mọi email tương lai chắc chắn thành công |

`JavaMailSenderImpl.testConnection()` có thể hữu ích để xác nhận kết nối tới mail server, bao gồm xác thực khi cấu hình yêu cầu. Tuy nhiên, test này không tự chứng minh quota, sender permission hoặc deliverability. Nếu muốn xác minh end-to-end, gửi một **canary email** tới mailbox kiểm thử được phép và theo dõi kết quả qua provider/test environment.

### TLS cần đúng trước khi đánh giá password

Nếu SMTP yêu cầu STARTTLS, hãy bật và yêu cầu STARTTLS thay vì tự động downgrade sang kết nối không bảo mật. Ví dụ với port 587:

~~~properties
spring.mail.properties[mail.smtp.auth]=true
spring.mail.properties[mail.smtp.starttls.enable]=true
spring.mail.properties[mail.smtp.starttls.required]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true
spring.mail.properties[mail.smtp.connectiontimeout]=5000
spring.mail.properties[mail.smtp.timeout]=10000
spring.mail.properties[mail.smtp.writetimeout]=10000
~~~

Nếu provider yêu cầu implicit TLS trên port 465, cấu hình phải phù hợp cơ chế đó; không sao chép STARTTLS/port từ ví dụ 587 một cách máy móc. Secret mới không thể khắc phục sai TLS mode, certificate validation hoặc network policy.

### Chỉ canary trên hạ tầng được phép

Không gửi thư thử tới người dùng thật hàng loạt khi đang rotation. Canary có recipient và sender được quản trị cho phép, không chứa dữ liệu sản xuất nhạy cảm. Rate-limit canary và tránh lặp vô hạn nếu AUTH đang lỗi.

## 9. Chiến lược cập nhật JavaMailSender trong ứng dụng đang chạy

Có ba cách triển khai phổ biến. Không có cách nào tự động phù hợp với mọi quy mô:

| Phương án | Cách thực hiện | Điểm mạnh | Lưu ý |
| --- | --- | --- | --- |
| Rolling restart | Cập nhật secret rồi restart pod/instance theo từng đợt | Dễ quan sát và giảm trạng thái động | Cần overlap hoặc tạm dừng dispatch nếu credential cũ bị hủy ngay |
| Managed refresh | Một cơ chế refresh chính thức tái tạo bean với secret mới | Không nhất thiết restart toàn process | Phải kiểm thử bean scope, proxy, sender đang chạy và refresh failure |
| Sender hot-swap | Tạo sender mới, kiểm tra rồi đổi tham chiếu nguyên tử | Có thể chuyển nhanh trong cùng process | Cần code riêng, quản lý in-flight và không cho đường gửi bypass |

Với hệ thống đơn giản, **rolling restart có orchestration và outbox** thường dễ vận hành hơn một cơ chế reload tự viết. Hot-swap hữu ích khi tần suất rotation lớn hoặc thời gian restart không phù hợp, nhưng phải thiết kế chặt.

### Không mutate một JavaMailSenderImpl chia sẻ giữa các thread

Giả sử hàng chục worker cùng dùng một bean JavaMailSenderImpl. Nếu một thread gọi setUsername hoặc setPassword trong lúc thread khác đang send(), có thể phát sinh thời điểm quan sát cấu hình không nhất quán. Ví dụ username mới nhưng password cũ, hoặc ngược lại.

Không nên làm:

~~~java
// Không nên sửa credential của một sender đang được nhiều thread dùng.
sharedSender.setUsername(newUsername);
sharedSender.setPassword(newPassword);
~~~

Hai lệnh này không tạo một phép cập nhật nguyên tử username/password. Thay vào đó, tạo **một sender hoàn chỉnh** cho credential mới, xác minh kết nối và thay tham chiếu của adapter.

### Một adapter hot-swap minh họa

Ví dụ dưới đây thể hiện cách snapshot sender theo mỗi lần gửi. SmtpSecret là dữ liệu do secret provider nội bộ trả về; code không dùng constructor Spring Boot auto-config:

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import java.util.Properties;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessagePreparator;

public final class RotatingSmtpGateway {

    private final AtomicReference<JavaMailSenderImpl> active;
    private final String host;
    private final int port;

    public RotatingSmtpGateway(
            String host, int port, SmtpSecret initialSecret)
            throws MessagingException {

        this.host = Objects.requireNonNull(host);
        this.port = port;
        JavaMailSenderImpl initial = createSender(initialSecret);
        initial.testConnection();
        active = new AtomicReference<>(initial);
    }

    public void send(MimeMessagePreparator preparator) {
        JavaMailSenderImpl snapshot = active.get();
        snapshot.send(preparator);
    }

    public void rotateTo(SmtpSecret next) throws MessagingException {
        JavaMailSenderImpl candidate = createSender(next);

        // Nếu auth/TLS không thành công, giữ nguyên sender cũ.
        candidate.testConnection();

        // Mọi lần gửi bắt đầu sau thao tác này nhận sender mới.
        active.set(candidate);
    }

    private JavaMailSenderImpl createSender(SmtpSecret secret) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(host);
        sender.setPort(port);
        sender.setProtocol("smtp");
        sender.setDefaultEncoding("UTF-8");
        sender.setUsername(secret.username());
        sender.setPassword(secret.password());

        Properties properties = new Properties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.ssl.checkserveridentity", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "10000");
        properties.put("mail.smtp.writetimeout", "10000");
        sender.setJavaMailProperties(properties);
        return sender;
    }
}
~~~

Một loại dữ liệu secret không nên có toString in password:

~~~java
public final class SmtpSecret {

    private final String username;
    private final String password;
    private final String version;

    public SmtpSecret(
            String username, String password, String version) {
        this.username = Objects.requireNonNull(username);
        this.password = Objects.requireNonNull(password);
        this.version = Objects.requireNonNull(version);
    }

    public String username() { return username; }
    public String password() { return password; }
    public String version() { return version; }

    // Không tự tạo toString() chứa các trường nhạy cảm.
}
~~~

**Lưu ý quan trọng:** Đây là ví dụ kiến trúc, không phải một hệ thống secret hot-reload production hoàn chỉnh. Nó chưa bao gồm listener nhận version từ vault, quyền gọi rotateTo, rollback/canary theo nhiều replica, metrics hoặc quản lý các sender in-flight. Các string secret vẫn có thể tồn tại trong heap cho tới khi được garbage-collected; không tuyên bố việc thay AtomicReference sẽ xóa ngay credential cũ khỏi memory.

### Vì sao snapshot sender có lợi?

Mỗi lời gọi send giữ một local reference duy nhất. Sau khi thay active bằng sender mới, những lần gửi bắt đầu sau đó dùng candidate. Những lần gửi đã snapshot sender cũ vẫn có thể tiếp tục chạy với credential cũ. Nếu credential cũ bị revoke trước khi chúng hoàn tất AUTH, các lần gửi đó có thể thất bại.

Vì vậy, cần khoảng chồng lấn hoặc drain/quiesce traffic khi cutover. **AtomicReference bảo vệ việc chuyển tham chiếu, không bảo đảm SMTP rotation zero downtime** trong mọi tình huống.

### Không để hai đường gửi khác nhau

Nếu các service khác vẫn inject JavaMailSender mặc định trong khi một service dùng RotatingSmtpGateway, hệ thống có thể tiếp tục gửi với credential cũ. Trong thiết kế hot-swap, phải:

- Quy định một SMTP submission gateway duy nhất.
- Bảo đảm mọi notification đi qua gateway đã cập nhật.
- Kiểm tra bean wiring và không để route bypass ngoài ý muốn.
- Phân biệt sender staging/canary và sender production.
- Ghi metrics theo secret version không nhạy cảm, nếu chính sách cho phép.

Nếu không thể kiểm soát tất cả đường gửi, lựa chọn rolling restart/đổi cấu hình tập trung có thể đáng tin cậy hơn.

## 10. Nạp secret mới từ secret manager

Một service có thể đọc secret theo version, xác minh rồi cập nhật sender:

~~~java
public interface SmtpSecretProvider {

    SmtpSecret getCurrent();

    SmtpSecret getVersion(String version);
}
~~~

Đây là contract nội bộ; interface này không phải API của Spring Mail. Một triển khai có thể sử dụng vault, cloud secret manager hoặc file mount đã được bảo vệ.

### Các bước reload an toàn

~~~text
Secret store publishes a new version
        |
        v
Application receives change event / scheduled refresh
        |
        v
Read version B with workload identity
        |
        v
Validate metadata and configuration
        |
        v
Construct a complete candidate sender
        |
        v
Test TLS + SMTP AUTH (controlled)
        |
        +-- FAILED --> Keep current sender, alert
        |
        +-- PASSED --> Swap active sender reference
                         |
                         v
                Drain old in-flight sends
                         |
                         v
                Revoke old credential per runbook
~~~

Không đặt username/password mới vào log khi reload thất bại. Nếu cần debug, ghi version ID, provider key, giai đoạn (read, construct, auth, swap), error code đã chuẩn hóa và correlation ID.

### Phân biệt “secret đã đổi” với “ứng dụng đã dùng bản mới”

Một secret manager có thể thông báo current version là B, nhưng pod vẫn dùng A. Cần quan sát riêng:

- Secret store current version.
- Version của sender mà mỗi pod đang sử dụng.
- Thời điểm pod xác nhận version mới.
- Số pod chưa cutover.
- Số lần SMTP AUTH thất bại theo pod/provider.

Không ghi raw credential hoặc fingerprint dễ suy đoán từ password. Một version ID không nhạy cảm là đủ trong nhiều hệ thống; nếu version ID do provider tạo có thể làm lộ thông tin nội bộ, chỉ xuất qua telemetry có phân quyền.

### Bộ nhớ cache và TTL

Nếu secret provider client cache credential, phải định nghĩa TTL và cách invalidation. Trong rotation bình thường, cache quá lâu khiến pod tiếp tục dùng A sau khi B active; trong incident credential bị lộ, cache có thể khiến ứng dụng không chuyển sang B kịp.

Tùy cách triển khai, có thể:

- Chủ động invalidate cache khi nhận event rotation.
- Dùng periodic refresh với jitter.
- Kiểm tra version metadata khi sắp hết hạn.
- Reload khi nhận AUTH failure có dấu hiệu credential đã bị thay, nhưng phải **rate-limit refresh** để tránh tất cả worker cùng gọi vault.

Không đọc secret manager cho từng email nếu không cần: một đợt hàng chục nghìn email có thể làm quá tải secret manager. Một cơ chế refresh tập trung với TTL, single-flight và giới hạn retry thường phù hợp hơn.

## 11. Xử lý race condition trong rotation

Một hệ thống nhiều instance có thể gặp các cuộc đua:

1. Pod A đã đọc B; pod B còn dùng A.
2. Operator revoke A trước khi pod B cập nhật.
3. Worker A đang gửi với sender cũ đúng lúc ref được swap.
4. Hai sự kiện refresh đến lệch thứ tự: B rồi A, gây downgrade.
5. Secret manager có eventual consistency hoặc version staging thay đổi giữa các lần đọc.

### Nguyên tắc dùng version đơn điệu

Gán một rotation generation do hệ thống quản lý, ví dụ 41 → 42. Mỗi instance chỉ chấp nhận promotion theo thứ tự đã phê duyệt. Không để callback cũ đến muộn ghi đè sender mới:

~~~text
Current generation: 42
Incoming event:     41
Action:             Ignore stale update
~~~

Nếu version ID của provider không có thứ tự (ví dụ UUID ngẫu nhiên), không so sánh lexical. Dùng metadata stage/current hoặc một generation/epoch được quản lý riêng.

### Refresh single-flight

Nếu 500 worker cùng gặp AUTH error, không để tất cả gọi vault và canary 500 lần. Dùng một cơ chế duy nhất cho mỗi instance/cluster để thực hiện refresh, còn các worker khác chuyển job về trạng thái tạm dừng:

- Chỉ một refresh task chạy tại một thời điểm.
- Những sự kiện trùng được gộp.
- Có backoff nếu vault/SMTP không sẵn sàng.
- Không phá sender đang hoạt động khi candidate không hợp lệ.
- Có timeout và alert nếu refresh chờ quá lâu.

## 12. OAuth2/XOAUTH2: token hết hạn khác password hết hạn

Một số provider SMTP hỗ trợ OAuth2 thông qua SASL XOAUTH2 thay vì password tĩnh. Lúc này secret thực tế trong lần SMTP AUTH là **access token ngắn hạn**. Việc token hết hạn là một phần vòng đời bình thường, không phải lúc nào cũng là sự cố.

### Các thành phần cần phân biệt

| Thành phần | Vòng đời | Lưu ý |
| --- | --- | --- |
| OAuth2 access token | Ngắn hạn | Phải có token còn hạn khi bắt đầu SMTP AUTH |
| Refresh token (nếu có) | Dài hơn, nhưng có thể bị revoke | Bảo vệ nghiêm ngặt và luân chuyển theo provider |
| Client secret/private key | Dùng để xác thực client theo flow | Quản lý riêng, cũng có thể phải rotate |
| Workload identity | Identity của ứng dụng tới token provider | Giảm nhu cầu giữ password dài hạn khi hỗ trợ |
| SMTP account/principal | Danh tính gửi email | Cần đủ quyền/scope cho SMTP |

Các OAuth2 flow, scope và quyền SMTP phụ thuộc provider. Không giả định mọi SMTP relay đều chấp nhận XOAUTH2; cần đọc khả năng và cấu hình xác thực được nhà cung cấp hỗ trợ.

### Ví dụ thuộc tính Jakarta Mail

~~~properties
mail.smtp.auth=true
mail.smtp.auth.mechanisms=XOAUTH2
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
mail.smtp.ssl.checkserveridentity=true
~~~

Với một số cách tích hợp Jakarta Mail, access token được dùng như phần password trong lời gọi SMTP AUTH XOAUTH2. Cần xác minh theo phiên bản thư viện và provider đang dùng. Không ghi access token dưới dạng password cố định vào application.yml rồi kỳ vọng hệ thống tự refresh.

### Refresh trước expiry với khoảng đệm

Giả sử access token có expiresAt. Không đợi chính xác thời điểm hết hạn mới lấy token mới, vì:

- Đồng hồ giữa hệ thống có thể lệch.
- SMTP handshake mất thời gian.
- Token server có độ trễ.
- Token có thể hết hạn trong lúc connection được thiết lập.

Một policy có thể lấy token mới khi thời gian còn lại nhỏ hơn một **safety margin** phù hợp. Khoảng đệm phải theo quy định provider, thời gian xử lý và độ lệch đồng hồ thực tế; không có giá trị cố định áp dụng cho mọi hệ thống.

### Token refresh failure

Nếu token endpoint trả lỗi tạm thời, application nên:

1. Giữ access token cũ **chỉ khi nó còn hợp lệ**.
2. Refresh có backoff và single-flight, không gọi token endpoint cho mỗi email.
3. Nếu token đã hết hạn, dừng SMTP submission và giữ outbox.
4. Phân biệt token service unavailable với refresh token bị revoke/invalid grant.
5. Alert khi không thể khôi phục trong ngưỡng SLA.

Không fallback sang SMTP AUTH không bảo mật hoặc anonymous relay chỉ vì token không lấy được.

## 13. Vì sao xoay vòng secret cần outbox và retry đúng loại lỗi?

Khi credential hết hạn, nhiều job đang chờ có thể đồng thời thất bại. Nếu mỗi job retry ngay với cùng password cũ, SMTP relay tiếp tục bị gọi hàng nghìn lần vô ích. Một outbox bền vững giúp tách việc **giữ yêu cầu gửi** khỏi việc **gọi SMTP ngay lúc này**.

~~~mermaid
flowchart LR
    A["Email outbox"] --> B["Dispatch gate"]
    B --> C{"Credential usable?"}
    C -- "No" --> D["Pause provider lane / alert"]
    D --> A
    C -- "Yes" --> E["Rate limiter"]
    E --> F["JavaMailSender"]
    F --> G["SMTP relay"]
~~~

Hành vi an toàn khi một credential bị từ chối diện rộng:

- Ghi nhận lỗi xác thực ở cấp provider/account.
- Đánh dấu provider lane đang bị chặn hoặc đưa circuit breaker vào OPEN khi có tín hiệu phù hợp.
- Không tăng tốc retry theo từng notification.
- Thực hiện refresh/rotation qua một quy trình riêng.
- Giữ bản ghi email trong PENDING/RETRY_PENDING hoặc trạng thái chờ credential.
- Chỉ mở lại gửi khi candidate đã được xác minh.
- Drain backlog qua rate limiter và giới hạn concurrency, tránh burst.

### AUTH failure có phải lỗi vĩnh viễn của email không?

Đối với một lần đăng nhập với credential sai, SMTP có thể trả lỗi 5xx. Nhưng điều này **không chứng minh nội dung email hoặc recipient là sai vĩnh viễn**. Đây thường là lỗi cấu hình/credential mang tính hệ thống; không nên đánh dấu toàn bộ notification là FAILED_PERMANENT rồi xóa yêu cầu gửi.

Một state bổ sung có thể là:

~~~text
PENDING
  |
  +-- CREDENTIAL_UNAVAILABLE --> WAITING_FOR_CREDENTIAL
                                    |
                                    v
                          ROTATION_VERIFIED
                                    |
                                    v
                                  PENDING
~~~

State này là model ứng dụng, không phải trạng thái sẵn có của JavaMailSender. Cần giới hạn thời gian chờ và cảnh báo cho email có SLA hoặc token hết hạn, chẳng hạn OTP.

### Không retry mọi lỗi SMTP vô hạn

| Lỗi | Hành động |
| --- | --- |
| AUTH bị từ chối trên nhiều job | Stop provider lane, refresh/rotate, alert |
| AUTH tạm không sẵn sàng do provider | Backoff và đánh giá tình trạng provider |
| Kết nối timeout | Retry có backoff qua rate limiter |
| Recipient bị từ chối vĩnh viễn | Xử lý theo recipient, không kích hoạt rotation |
| Template/MIME sai | Sửa template/dữ liệu, không phụ thuộc secret |
| SMTP outcome unknown sau DATA | Không tự retry mù vì nguy cơ duplicate |
| Quota/rate-limit | Điều tiết tốc độ và retry theo policy |

Lưu ý: khi AUTH lỗi chắc chắn xảy ra **trước khi gửi DATA**, thường biết lần thử đó chưa submit message. Nhưng một ngoại lệ kết nối sau DATA có thể không cho biết relay đã nhận hay chưa. Adapter phải phân biệt các giai đoạn lỗi nếu thông tin transport cho phép.

## 14. Giới hạn retry và circuit breaker trong sự cố secret

Thay vì mỗi job liên tục kiểm tra password cũ, dùng circuit breaker hoặc provider health state:

~~~text
ACTIVE
  |
  +-- AUTH rejected repeatedly --> CREDENTIAL_SUSPECT
                                      |
                                      v
                                DISPATCH_PAUSED
                                      |
                            load/verify new secret
                                      |
                    +-----------------+-----------------+
                    |                                   |
                FAILED                              VERIFIED
                    |                                   |
                stay paused                         RATE_LIMITED_DRAIN
~~~

Đây là sơ đồ trạng thái khái niệm. Ngưỡng chuyển trạng thái cần dựa trên bằng chứng lỗi xác thực có độ tin cậy cao, không tự mở breaker vì một recipient 550 hoặc một lỗi DNS đơn lẻ.

### Tránh credential refresh storm

Một lỗi có thể kích hoạt cùng lúc:

- 200 worker gọi SMTP và nhận AUTH failure.
- Mỗi worker gọi secret manager.
- Mỗi worker gọi testConnection với credential mới.
- Secret manager và SMTP tiếp tục bị quá tải.

Để tránh điều đó:

1. Có một coordinator hoặc single-flight refresh.
2. Thêm jitter vào periodic refresh ở nhiều instance.
3. Giới hạn canary/testConnection cho mỗi rotation version.
4. Cache secret theo version có TTL và invalidation rõ ràng.
5. Khi refresh thất bại, retry ở cấp rotation coordinator, không ở từng email.
6. Worker chỉ giữ job trong outbox, không lặp SMTP liên tục.

### Retry vẫn cần idempotency

Sau khi credential mới được kích hoạt, việc gửi lại hàng đợi có thể gặp tình huống một số email trước đó đã được SMTP chấp nhận nhưng ứng dụng chưa kịp ghi SUBMITTED. Dùng notification ID, trạng thái, lease, attempt history và đối soát khi kết quả SMTP không chắc chắn; không tự reset mọi record thành PENDING chỉ vì credential đã được thay.

## 15. Theo dõi thời điểm hết hạn trước khi sự cố xảy ra

Không nên chờ đến khi SMTP trả AUTH failure mới biết secret đã hết hạn. Một cơ chế quản lý vòng đời cần cảnh báo **trước** expiry và xác nhận rotation được hoàn tất.

Các metadata nên theo dõi:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| credentialVersion | Version đang được ứng dụng sử dụng |
| createdAt | Thời điểm credential được tạo |
| activatedAt | Thời điểm bắt đầu dùng |
| expiresAt | Thời điểm hết hạn nếu provider cung cấp |
| rotationDueAt | Hạn đổi theo chính sách nội bộ |
| lastSuccessfulAuthAt | Lần xác thực SMTP thành công gần nhất |
| lastValidatedAt | Lần kiểm tra candidate gần nhất |
| rotationState | STAGED, ACTIVE, RETIRING, REVOKED... |
| owner/contact | Nhóm chịu trách nhiệm rotation và incident |

**Không dùng “lastSuccessfulAuthAt” làm bằng chứng secret còn hiệu lực tới một ngày cụ thể**: một lần AUTH hôm nay không bảo đảm credential không bị revoke ngày mai. Metadata expiry cũng cần được xác nhận với provider, không chỉ dựa vào timestamp do ứng dụng tự đoán.

### Cảnh báo nhiều mốc

Có thể đặt một loạt mốc cảnh báo theo mức độ rủi ro, chẳng hạn:

- Nhắc rotation theo lịch chính sách trước hạn đáng kể.
- Cảnh báo sớm khi còn ít thời gian để staging/canary.
- Cảnh báo khẩn cấp nếu gần hết hạn mà chưa có phiên bản mới active.
- Incident khi đã quá hạn hoặc AUTH failure diễn ra diện rộng.

Thời gian cụ thể tùy tổ chức, hệ thống và độ ngắn của secret. Access token OAuth2 có thể sống trong khoảng phút/giờ, nên refresh tự động trước expiry; SMTP password có thể được thay theo lịch ngày/tháng. Không dùng cùng một ngưỡng 7 ngày cho mọi loại.

### Hàm xác định đã đến ngưỡng refresh

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class SecretExpiryPolicy {

    public static boolean refreshDue(
            Instant now,
            Instant expiresAt,
            Duration safetyMargin) {

        Objects.requireNonNull(now);
        Objects.requireNonNull(expiresAt);
        Objects.requireNonNull(safetyMargin);
        if (safetyMargin.isNegative()) {
            throw new IllegalArgumentException("Negative margin");
        }

        return !now.isBefore(expiresAt.minus(safetyMargin));
    }
}
~~~

Hàm này chỉ trả lời **đã đến ngưỡng refresh hay chưa**, không tự refresh token hay rotate SMTP credential. Với secret không có expiresAt, dùng rotationDueAt hoặc policy riêng. Trong ứng dụng thật, inject Clock để test biên thời gian và tránh phụ thuộc vào đồng hồ hệ thống ở nhiều nơi.

### Rotation là quy trình, không chỉ là timestamp

Một thông báo “secret sẽ hết hạn sau 24 giờ” không đủ nếu ứng dụng chưa triển khai version mới. Dashboard nên hiển thị:

- Đã có candidate hợp lệ chưa?
- Canary đã qua chưa?
- Bao nhiêu instance đang dùng version mới?
- Còn traffic dùng version cũ không?
- Credential cũ đã bị revoke chưa?
- Có backlog AUTH failure cần xử lý không?

Chỉ khi các điều kiện liên quan đến chính sách hoàn thành, rotation mới được coi là kết thúc.

## 16. Readiness, health check và startup behavior

Spring Boot hỗ trợ tùy chọn kiểm tra kết nối SMTP lúc startup, ví dụ:

~~~yaml
spring:
  mail:
    test-connection: true
~~~

Với môi trường và phiên bản Spring Boot phù hợp, thiết lập này có thể khiến ứng dụng kiểm tra khả năng kết nối mail server khi khởi động. Tuy nhiên, cần cân nhắc:

- Nếu SMTP tạm unavailable, tất cả pod mới có thể không sẵn sàng trong một rolling deploy.
- Một sự cố provider có thể vô tình ngăn cả chức năng ứng dụng không liên quan email khởi động.
- Kiểm tra connect/auth chưa chứng minh email được relay chấp nhận theo sender policy.
- Mỗi pod khởi động đồng thời có thể tạo nhiều lần testConnection tới SMTP.

### Có nên gọi testConnection trong readiness probe liên tục?

Không nên mặc định thực hiện SMTP AUTH trên **mọi** HTTP readiness check. Kết quả có thể là:

- Tăng số kết nối và chiếm quota xác thực.
- Khi SMTP outage, load balancer rút tất cả web pod khỏi service dù chức năng chính vẫn hoạt động.
- Tạo thêm Auth/connection storm trong lúc provider đang yếu.

Thay vào đó, tách các thành phần:

- **Web/application readiness:** ứng dụng có thể xử lý các request nghiệp vụ theo cam kết không?
- **Mail dispatch health:** worker có thể submit email không?
- **Credential freshness:** secret đang dùng có đúng version và còn hạn không?
- **Backlog health:** mail outbox có vượt SLA không?

Một dịch vụ chỉ làm mail sender có thể coi SMTP readiness là quan trọng; một web app đa chức năng có thể chấp nhận SMTP down trong lúc vẫn nhận đơn hàng và lưu outbox. Quyết định phụ thuộc kiến trúc.

### Cân bằng fail-fast với khả năng phục hồi

Với một hệ thống chuyên gửi SMTP, fail-fast khi không thể authenticate có thể phù hợp, vì nó không có chức năng khác. Với producer web app sử dụng outbox, chấp nhận khởi động mà chưa có SMTP nhưng đánh dấu mail lane unhealthy có thể tốt hơn. Đừng biến lựa chọn của một ví dụ thành quy tắc chung.

## 17. Xử lý khi secret manager không khả dụng

Kho secret cũng có thể gặp sự cố. Đây là tình huống khác với SMTP provider từ chối credential.

### Nếu đang có credential còn hợp lệ

Khi vault tạm unavailable nhưng sender đang dùng credential A chưa hết hạn và chưa bị revoke, một ứng dụng có thể tiếp tục dùng A theo policy, đồng thời:

- Không cố đọc secret mỗi email.
- Refresh trong nền có backoff/jitter.
- Alert khi không thể đọc metadata hoặc version mới.
- Dừng triển khai rotation nếu chưa xác minh B.
- Giới hạn thời gian cho phép tiếp tục dùng bản cache.

Điều này giúp hệ thống không phụ thuộc thời gian thực vào vault cho mọi lệnh SMTP. Tuy nhiên, nếu chính sách bảo mật yêu cầu revoke ngay hoặc có bằng chứng A bị lộ, không được cố giữ A chỉ để bảo đảm uptime.

### Nếu credential đã hết hạn/bị thu hồi

Không được dùng credential đã biết vô hiệu hoặc fallback tới anonymous relay để “cứ gửi đi”. Giữ outbox, báo lỗi và đợi secret hợp lệ. Với OTP và thông điệp có thời hạn, trạng thái có thể hết hạn trước khi hạ tầng phục hồi; cần phản hồi phù hợp cho người dùng.

### Backoff cho vault khác backoff cho SMTP

Lỗi vault nên được xử lý bởi **secret refresh coordinator**. Lỗi SMTP nên được xử lý bởi **mail dispatch worker**. Nếu một incident làm cả hai cùng lỗi, cần tránh hai vòng retry nhân số request:

~~~text
Vault unavailable
    |
    v
One bounded secret refresh retry loop
    |
    v
Mail lane temporarily paused
    |
    v
Outbox preserved; no per-email vault fetch loop
~~~

## 18. Quy trình xử lý khi SMTP secret đã hết hạn

Khi nhiều notification liên tiếp gặp SMTP AUTH failure, cần xử lý theo thứ tự giảm tác động.

### Bước 1 — Xác nhận phạm vi

Kiểm tra:

- Lỗi xảy ra với một pod hay toàn bộ instance?
- Một SMTP account hay tất cả tài khoản?
- Lỗi xuất hiện sau rotation/deployment nào?
- Provider báo password invalid, account locked, token expired hay lỗi dịch vụ tạm thời?
- Có thay đổi TLS mode, hostname, sender permission hoặc IP allowlist không?
- Bản ghi đang dùng secret version nào?

Không tự kết luận secret hết hạn khi chỉ thấy một connection timeout. Đây có thể là network, DNS, certificate hoặc provider outage.

### Bước 2 — Ngăn khuếch đại lỗi

- Tạm dừng lane gửi qua credential đang lỗi.
- Giữ outbox PENDING/RETRY_PENDING, tránh retry storm.
- Có thể tạm ngừng marketing và ưu tiên phục hồi email giao dịch.
- Không xóa failed record, không tăng attempts vô hạn.
- Cảnh báo nhóm trực hệ thống và nhóm quản lý credential.

### Bước 3 — Tạo/nhận credential hợp lệ

- Tra cứu secret current version trong nguồn có thẩm quyền.
- Nếu credential bị revoke, cấp credential mới theo policy.
- Kiểm tra account permissions và From address.
- Đọc secret qua workload identity có quyền, không copy password vào chat hoặc ticket.
- Không thử lại password nhiều lần dẫn đến khóa tài khoản.

### Bước 4 — Kiểm tra candidate

- Kiểm tra TLS/connect/auth ở một canary worker.
- Gửi một thư canary tới mailbox kiểm thử được phép nếu cần kiểm tra quyền submit.
- Xác nhận cấu hình host, port, STARTTLS/implicit TLS phù hợp.
- Ghi version ID và kết quả xác minh, không ghi giá trị password.

### Bước 5 — Triển khai và chuyển lưu lượng

- Thay sender hoặc rolling restart theo kế hoạch.
- Xác nhận mỗi pod dùng đúng version mới.
- Nếu credential cũ không còn hợp lệ, không để pod cũ tiếp tục dispatch.
- Dọn các kết nối/sender in-flight theo cách an toàn.

### Bước 6 — Khôi phục backlog

- Mở lane gửi trở lại **thông qua rate limiter**.
- Ưu tiên thông báo còn hạn và quan trọng.
- Không phát lại bản ghi SUBMITTED hoặc SUBMISSION_UNKNOWN một cách mù quáng.
- Kiểm tra suppression/expiry trước các lần retry.
- Theo dõi SMTP success, failure, oldest pending age và dead-letter.

### Bước 7 — Hậu kiểm

- Phân tích vì sao cảnh báo expiry không hoạt động hoặc rollout chậm.
- Cập nhật lịch rotation, threshold, runbook và owner.
- Ghi audit hoạt động rotation, phiên bản và thời điểm revoke.
- Nếu có người nhận bị ảnh hưởng, xử lý truyền thông theo chính sách tổ chức.

### Sơ đồ xử lý sự cố

~~~mermaid
flowchart TD
    A["AUTH failures spike"] --> B{"Credential actually invalid?"}
    B -- "No / unclear" --> C["Investigate TLS, provider, network"]
    B -- "Yes" --> D["Pause affected mail lane"]
    D --> E["Get/create valid secret"]
    E --> F["Test TLS + AUTH + canary"]
    F --> G{"Candidate valid?"}
    G -- "No" --> H["Keep outbox, alert, investigate"]
    G -- "Yes" --> I["Deploy or swap sender"]
    I --> J["Verify fleet version"]
    J --> K["Drain backlog with limiter"]
    K --> L["Audit and post-incident review"]
~~~

## 19. Ứng phó khi phát hiện secret bị lộ

Rotation định kỳ và ứng phó **credential compromise** không hoàn toàn giống nhau. Nếu password bị lộ trong repository, log, ticket, screenshot hoặc máy bị xâm nhập, tiếp tục giữ credential cũ active trong overlap dài có thể làm tăng rủi ro lạm dụng.

Một quy trình sự cố có thể gồm:

1. Khoanh vùng SMTP account/secret liên quan.
2. Hạn chế hoặc thu hồi credential bị lộ theo mức độ khẩn cấp và kế hoạch duy trì dịch vụ.
3. Cấp credential mới, cập nhật đúng ứng dụng/service account.
4. Kiểm tra hoạt động gửi bất thường qua provider audit/log.
5. Rà soát quyền truy cập vault, CI/CD, repository và log nơi có thể còn secret.
6. Xử lý bản sao trong history, artifact hoặc backup theo chính sách; không tuyên bố có thể xóa mọi bản sao đã phát tán.
7. Cân nhắc nghĩa vụ báo cáo sự cố và hỗ trợ người nhận theo yêu cầu tổ chức/pháp luật.
8. Tăng cường guardrail để tránh lộ lại, chẳng hạn secret scanning và kiểm soát debug log.

Nếu secret đang bị khai thác, ưu tiên thu hồi có thể cao hơn zero-downtime. Outbox giúp duy trì yêu cầu gửi trong lúc luồng SMTP được khôi phục bằng credential mới.

### Không đưa secret vào log và exception

Cần thận trọng với:

- `application.yml` hoặc `application.properties` được in ra khi debug.
- Startup dumps liệt kê toàn bộ Spring Environment.
- HTTP actuator endpoints phơi bày thông tin cấu hình nếu bảo vệ không đúng.
- Mail protocol debug và SMTP trace.
- Exception chứa URL/parameter có credential.
- Custom toString của object credential.
- CI pipeline in biến môi trường.
- Tracing baggage, APM breadcrumbs hoặc support bundle.

`mail.debug` hoặc protocol logging có thể giúp chẩn đoán, nhưng không nên bật tràn lan ở production. Khi cần, sử dụng môi trường kiểm soát, masking, thời gian bật ngắn và rà soát dữ liệu được ghi. Không giả định mọi thư viện sẽ luôn che toàn bộ chuỗi AUTH hoặc token trong mọi cấu hình.

### Secret trong bộ nhớ

Java String bất biến và có thể còn trong heap sau khi thay password. Không khẳng định có thể xóa hoàn toàn mọi bản sao secret đang được JavaMailSenderImpl/Jakarta Mail giữ. Giảm thời gian sống bằng cách thay sender, loại bỏ reference cũ, không cache vô hạn và quản lý quyền đọc heap dump. Nếu yêu cầu bảo mật rất cao, cân nhắc quá trình/worker riêng có vòng đời ngắn hơn và identity ngắn hạn theo nền tảng.

## 20. Rollback và roll-forward cho SMTP rotation

Một bảng quyết định giúp tránh rollback mù quáng:

| Tình huống | Lựa chọn |
| --- | --- |
| Candidate B lỗi, A vẫn hợp lệ | Giữ A, không promote B; sửa rồi thử lại |
| B đã active, A chưa revoke, B phát sinh lỗi | Có thể rollback có kiểm soát về A nếu an toàn và được phép |
| B active, A đã revoke | Không rollback về A; roll forward bằng B đã sửa hoặc credential C |
| A bị lộ | Không cố giữ A chỉ để phục hồi dịch vụ; ưu tiên revoke theo incident policy |
| Provider chỉ cho một password | Lập cutover/rollback theo khả năng cấp lại password |
| Token OAuth2 hết hạn | Refresh token/access token mới; không “rollback” về token hết hạn |

### Không làm mất dữ liệu khi rollback

Với outbox, các message chưa submit vẫn được giữ. Nhưng phải phân biệt:

- SUBMITTED: đã được SMTP relay chấp nhận, không retry tùy tiện.
- RETRY_PENDING: đã có lỗi tạm thời và có lịch retry.
- WAITING_FOR_CREDENTIAL: chưa được gửi do mail lane dừng.
- SUBMISSION_UNKNOWN: không biết chắc relay đã nhận hay chưa.
- EXPIRED/SUPPRESSED: không còn được phép gửi theo policy.

Không reset toàn bộ trạng thái về PENDING chỉ vì chuyển credential. Điều này vừa tạo duplicate vừa có thể gửi email marketing đã hết hạn hoặc OTP không còn hiệu lực.

### Khi nào thu hồi credential cũ?

Trong rotation thông thường có overlap, chỉ revoke sau khi:

1. Candidate mới xác thực/gửi canary thành công.
2. Mọi instance/consumer đã cutover.
3. Không còn request in-flight cần A theo chính sách.
4. Metrics không còn ghi nhận traffic dùng A.
5. Phương án roll-forward nếu B lỗi đã sẵn sàng.

Trong incident compromise, có thể phải revoke sớm hơn. Quy trình phải nêu rõ khác biệt giữa **rotation theo lịch** và **thu hồi khẩn cấp**.

## 21. Kiểm thử secret rotation trước khi triển khai

Không nên chỉ test đường gửi thành công với một password cố định. Một hệ thống có khả năng rotation cần các phép thử **trước, trong và sau** thời điểm đổi secret.

| ID | Tình huống | Kết quả cần chứng minh |
| --- | --- | --- |
| R01 | Credential A hợp lệ | Gửi qua A theo cấu hình ban đầu |
| R02 | Tạo credential B hợp lệ | B có thể AUTH/canary trước khi promote |
| R03 | Candidate B sai password | Không thay active sender; A tiếp tục hoạt động nếu còn hợp lệ |
| R04 | Swap A → B thành công | Những lần gửi mới dùng B |
| R05 | A vẫn có in-flight send lúc swap | Không có cấu hình username mới/password cũ bị trộn; xử lý lỗi in-flight theo policy |
| R06 | Revoke A sau khi B active | Không pod nào còn bắt đầu SMTP AUTH bằng A |
| R07 | Một replica không nhận event | Phát hiện version drift và không revoke A khi chưa giải quyết |
| R08 | Refresh event B đến trước event A cũ | Không downgrade từ B về A |
| R09 | Secret manager tạm unavailable | Không tạo vòng lặp fetch mỗi email; outbox còn nguyên |
| R10 | Secret hết hạn trong lúc backlog lớn | Mail lane tạm dừng; không retry storm |
| R11 | Credential được khôi phục | Backlog drain qua rate/concurrency limiter |
| R12 | App restart sau đổi secret | Lấy đúng version hiện hành, không dùng cache version cũ vô hạn |
| R13 | OAuth2 access token sắp hết hạn | Token được refresh trước margin |
| R14 | Refresh token bị revoke | Không retry login liên tục, ghi lỗi cần can thiệp |
| R15 | SMTP provider không hỗ trợ overlap | Cutover có dừng/lập lịch, không giả định hai password cùng sống |
| R16 | Credential bị lộ | Nhánh incident revoke/roll-forward được thực hiện |
| R17 | SMTP chấp nhận thư nhưng update outbox lỗi | Không tự retry mù những record có kết quả không chắc chắn |
| R18 | Logging bật trong test | Không lộ raw password/access token vào log/trace |

### Tạo SMTP relay giả có hai phiên bản credential

Với integration test, một SMTP fake có thể kiểm soát:

~~~text
Phase 1: accept credential A, reject B
Phase 2: accept A and B
Phase 3: accept B, reject A
Phase 4: temporarily reject all AUTH
Phase 5: recover and accept B
~~~

Ứng dụng chạy rotation A → B ở phase 2, xác nhận tất cả sender mới dùng B, rồi chuyển fake sang phase 3. Kịch bản này kiểm tra quy trình có khoảng overlap và khả năng phát hiện pod cũ.

Nếu ứng dụng có nhiều replica, chạy ít nhất hai worker và một coordinator/secret-store fake. Không kết luận hệ thống phân tán an toàn từ unit test chỉ có một bean trong một JVM.

### Test credential mới lỗi

Một tiêu chí quan trọng: nếu candidate B không authenticate được, gateway **không được thay active sender A**.

Pseudocode:

~~~text
activeSecretVersion = "A"
candidate = "B"  // B invalid

rotateTo(B) -> authentication failure
assert activeSecretVersion == "A"
assert no raw secret appeared in logs

if A is still valid:
    next send uses A
else:
    keep pending; alert for recovery
~~~

Với adapter có AtomicReference, có thể inject một SenderFactory và CredentialProbe vào phiên bản production để unit test việc swap mà không cần mở socket. Test thực tế với SMTP fake vẫn cần để xác nhận AUTH và transport configuration.

### Test cập nhật đồng thời

Cho nhiều thread liên tục gọi send trong lúc rotation:

- Mỗi lần gửi dùng một snapshot sender hoàn chỉnh.
- Không quan sát trường hợp username B kết hợp password A.
- Những lần gửi đang chạy với A có kết quả phù hợp với chính sách overlap.
- Những lần gửi bắt đầu sau khi B được promote dùng B.
- Candidate không hợp lệ không thay thế reference đang hoạt động.

Test concurrency cần latch/barrier và số lượt đủ lớn để có tranh chấp; không chỉ gọi hai method tuần tự rồi kết luận an toàn.

## 22. Unit test chính sách hết hạn bằng đồng hồ cố định

Tài liệu nên đưa rotation/expiry logic ra khỏi scheduler để có thể kiểm thử mà không phải đợi thật.

Với hàm SecretExpiryPolicy.refreshDue đã trình bày, có thể kiểm thử:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class SecretExpiryPolicyTest {

    @Test
    void refreshBeginsAtSafetyMargin() {
        Instant expiry = Instant.parse(
                "2030-06-01T12:00:00Z");
        Duration margin = Duration.ofMinutes(5);

        assertFalse(SecretExpiryPolicy.refreshDue(
                expiry.minus(Duration.ofMinutes(6)),
                expiry,
                margin));

        assertTrue(SecretExpiryPolicy.refreshDue(
                expiry.minus(Duration.ofMinutes(5)),
                expiry,
                margin));

        assertTrue(SecretExpiryPolicy.refreshDue(
                expiry.plusSeconds(1),
                expiry,
                margin));
    }
}
~~~

Đây là test logic chính sách, không phải test token service. Với access token OAuth2, cần thêm test: refresh token endpoint tạm lỗi; refresh token bị revoke; access token còn hạn; access token đã hết hạn; các worker cùng nhận 401/SMTP AUTH failure; và refresh single-flight.

### Không dùng Thread.sleep để đợi secret hết hạn

Nếu test thật sự ngủ năm phút, CI sẽ chậm và dễ không ổn định. Thay vào đó, inject Clock hoặc tạo secret metadata có expiresAt cố định; kiểm thử bằng các thời điểm giả lập. Dùng SMTP fake cho integration test yêu cầu xác thực, không dùng production credential.

## 23. Kiểm thử rolling restart và nhiều instance

Rotation trên một service instance có thể thành công nhưng cả cụm vẫn dùng credential A ở những pod khác. Một bài thử staging nên mô phỏng:

1. Có ba instance A1, A2, A3 dùng secret version A.
2. Tạo credential version B và xác nhận có overlap.
3. Cập nhật A1, sau đó A2, rồi A3.
4. Sau mỗi bước, gửi một canary hoặc kiểm tra xác thực được phân tán hợp lý.
5. Quan sát version gauge của từng instance và lỗi SMTP.
6. Xác nhận không instance nào còn dùng A.
7. Revoke A.
8. Gửi thử tiếp từ tất cả instance bằng B.

### Nếu một instance bị mắc kẹt

Không revoke A trong quy trình rotation bình thường khi còn pod sử dụng A mà chưa có kế hoạch xử lý. Có thể:

- Khởi động lại instance mắc kẹt.
- Dừng mail dispatch ở instance đó.
- Chuyển traffic khỏi pod cũ.
- Kiểm tra listener/refresh event hoặc cache TTL.

Trong incident compromise, có thể phải revoke A bất kể rollout đã hoàn tất hay chưa, nhưng cần sẵn sàng cho gián đoạn gửi và khả năng khôi phục outbox.

### Cẩn trọng với connection/session đang sống

Một SMTP connection đã authenticate với credential cũ có thể tiếp tục được dùng tùy hành vi transport/server. Điều này không chứng minh mọi kết nối mới sẽ authenticate được sau revoke. Khi kiểm tra rotation, nên phân biệt:

- Lệnh gửi dùng một transport/connection đã có.
- Lệnh gửi mở kết nối và AUTH mới.
- Sender bean đã cập nhật credential nhưng worker vẫn giữ reference cũ.

Nếu ứng dụng sử dụng connection pooling hoặc wrapper transport riêng, phải xác minh chính sách đóng/rotate connection; ví dụ demo JavaMailSenderImpl tạo mới không tự giải quyết mọi pooling behavior trong hệ thống.

## 24. Metrics và alert cho SMTP secret

Metrics nên giúp trả lời “secret đã được cập nhật trên toàn bộ workload chưa?” và “rotation có làm gián đoạn email không?” mà không lộ giá trị secret.

| Metric gợi ý | Mục đích |
| --- | --- |
| smtp_auth_failures_total | Phát hiện tỷ lệ AUTH bị từ chối |
| smtp_secret_rotation_attempts_total | Số lần cố gắng rotation |
| smtp_secret_rotation_success_total | Số lần promote thành công |
| smtp_secret_rotation_failure_total | Số lần candidate không hợp lệ |
| smtp_secret_seconds_until_expiry | Thời gian còn hạn nếu metadata có |
| smtp_secret_age_seconds | Tuổi của credential đang active |
| smtp_secret_active_generation | Generation đang dùng trên mỗi instance |
| smtp_secret_version_drift_instances | Số instance chưa ở version kỳ vọng |
| smtp_dispatch_paused | Lane SMTP đang bị tạm dừng |
| smtp_outbox_pending | Số thông điệp chờ |
| smtp_outbox_oldest_age_seconds | Tuổi thông điệp chờ lâu nhất |
| smtp_submission_success_total | Số lần relay chấp nhận submit |
| smtp_submission_unknown_total | Số lần kết quả không xác định |
| smtp_secret_refresh_latency_seconds | Độ trễ lấy và kiểm tra secret mới |

Các tên trên là ví dụ telemetry do ứng dụng định nghĩa; Spring Mail không tự xuất toàn bộ metrics này. Có thể dùng Micrometer, Actuator hoặc hệ thống observability hiện có để thu thập.

### Alert theo mức độ

| Tình huống | Phản ứng |
| --- | --- |
| Secret gần expiry nhưng chưa có candidate | Cảnh báo nhóm phụ trách rotation |
| Candidate AUTH thất bại | Giữ version cũ nếu an toàn; điều tra |
| Nhiều instance version drift | Dừng revoke theo lịch, xử lý instance cũ |
| AUTH failure tăng đột biến | Cô lập lane, kiểm tra credential/provider |
| Mail queue vượt SLA | Nâng mức cảnh báo theo category |
| Refresh token bị revoke | Cảnh báo quyền/token grant cần cấp lại |
| Secret manager không khả dụng kéo dài | Alert hạ tầng; kiểm tra thời gian còn hạn của credential hiện tại |

Metric label không được chứa password, access token, OTP, địa chỉ email đầy đủ hoặc tên người dùng. Tránh đưa notification ID vào label vì cardinality cao. Version/generation nên là metadata không nhạy cảm, chỉ công khai cho người có quyền xem hệ thống.

### Sự khác nhau giữa version gauge và audit

Gauge giúp biết trạng thái hiện tại; audit cần biết ai đã rotate, từ version nào sang version nào, tại thời điểm nào, có thu hồi thành công hay không. Không dùng một metric gauge thay thế hệ thống audit.

## 25. Audit, quyền hạn và thay đổi có kiểm soát

Một quá trình rotation nên được ghi nhận:

- Service/account/provider bị tác động.
- Rotation request ID hoặc change ticket.
- Operator hoặc automation identity.
- Version/generation trước và sau.
- Thời điểm tạo/stage/promote/revoke.
- Canary/testConnection outcome, không chứa credential.
- Số instance đã cập nhật.
- Backlog và lỗi sau cutover.
- Lý do rotation: định kỳ, expiry, credential bị lộ, quyền thay đổi.

### Quyền tối thiểu

| Vai trò | Quyền phù hợp |
| --- | --- |
| Application runtime | Đọc đúng secret version cần dùng |
| Rotation automation | Tạo/stage/promote secret theo policy |
| Security operator | Revoke/incident rotation với audit |
| Mail operator | Tạm dừng/khôi phục queue, xem trạng thái không nhạy cảm |
| Developer | Xem cấu hình không chứa secret, chạy test trên secret staging |
| Auditor | Xem lịch sử thay đổi, không cần xem password |

Không mặc định cho mọi application pod quyền **rotate hoặc revoke** secret. Quyền đọc secret và quyền thay đổi secret nên tách để giảm nguy cơ một workload bị xâm nhập có thể phá cả hệ thống.

### Không coi secret manager là nguồn log ứng dụng

Audit của secret manager có thể cho biết một workload đọc version B, nhưng không bảo đảm nó đã tạo JavaMailSender mới, authenticate thành công hoặc ngừng dùng A. Cần cả audit điều phối và telemetry tại ứng dụng.

## 26. Các lỗi triển khai thường gặp

### 26.1. Hardcode SMTP password trong Git

Credential có thể lưu trong history, artifact và CI logs. Cần chuyển ra secret store; nếu từng bị lộ, rotate/revoke thay vì chỉ xóa dòng.

### 26.2. Đổi secret trong vault nhưng không refresh JavaMailSender

Bean đã bind trước đó có thể tiếp tục dùng password cũ. Cần restart, verified refresh hoặc hot-swap.

### 26.3. Revoke credential cũ ngay khi tạo credential mới

Những pod chưa cutover sẽ AUTH thất bại. Chỉ áp dụng overlap khi provider hỗ trợ và chỉ revoke sau khi đã xác nhận fleet; incident compromise có thể cần xử lý nhanh hơn.

### 26.4. Tự động rollback về credential đã bị thu hồi

Rollback image không làm password cũ hợp lệ trở lại. Phải roll forward bằng credential được cấp lại.

### 26.5. Gọi setUsername và setPassword trực tiếp trên shared sender

Không phải phép cập nhật credential nguyên tử. Tạo sender mới và swap reference có kiểm soát hoặc restart.

### 26.6. Test connection thành công rồi cho rằng deliverability đã ổn

AUTH thành công không chứng minh From được phép, quota còn hay email đến inbox. Cần canary và provider event khi cần.

### 26.7. Refresh credential trong mọi lần gửi

Tạo áp lực lên secret manager và có thể phát sinh refresh storm. Dùng refresh coordinator, cache/TTL và single-flight.

### 26.8. Retry AUTH failure cho từng notification

Một credential sai gây lỗi cho toàn bộ account, nên retry từng email liên tục chỉ tạo tải. Tạm dừng lane và phục hồi credential trước.

### 26.9. Bật mail.debug liên tục ở production

Có thể làm lộ thông tin protocol hoặc dữ liệu nhạy cảm. Chỉ dùng trong môi trường kiểm soát và có masking.

### 26.10. Không kiểm soát secret hết hạn của OAuth2 token

Access token ngắn hạn cần refresh tự động trước expiry; không thể lưu như password tĩnh.

### 26.11. Cho phép anonymous SMTP fallback

Hạ thấp bảo mật khi AUTH lỗi có thể dẫn tới relay trái phép hoặc rò rỉ dữ liệu. Không tự downgrade AUTH/TLS khi không có chính sách rõ và được phê duyệt.

### 26.12. Gộp lỗi AUTH với lỗi recipient

Credential sai là lỗi hệ thống, recipient 550 là lỗi địa chỉ/đích. Hai loại có retry và cảnh báo khác nhau.

### 26.13. Gửi bù toàn bộ backlog ngay sau rotation

Có thể gây SMTP throttling ngay sau khi credential phục hồi. Drain qua rate limiter và concurrency gate.

### 26.14. Không kiểm tra tất cả replica và worker

Pod cũ hoặc scheduled job không nằm trong rollout vẫn dùng version A. Theo dõi fleet version trước revoke.

### 26.15. Dùng thông tin credential trong metric label

Raw secret, token hoặc account key nhạy cảm không thuộc về telemetry. Chỉ sử dụng metadata an toàn, phân quyền truy cập.

### 26.16. Coi secret cache hết hạn là bằng chứng SMTP secret đã bị revoke

TTL cache chỉ là chính sách nạp lại ở ứng dụng. Nó không phản ánh chính xác vòng đời credential tại provider. Cần phân biệt cache expiry với credential expiry.

### 26.17. Xóa toàn bộ bản ghi gửi lỗi sau khi credential mới hoạt động

Có thể mất lịch sử và không biết email nào chưa được submit. Giữ outbox/attempt history, xử lý từng trạng thái đúng policy.

## 27. Checklist trước, trong và sau rotation

### Trước khi rotation

1. Có inventory đủ mọi SMTP consumer/service account.
2. Có owner, lịch và hạn mức credential rõ ràng.
3. Xác nhận provider hỗ trợ overlap hay không.
4. Secret B được tạo trong kho bảo mật đúng môi trường.
5. Có canary kiểm tra TLS, AUTH và quyền From.
6. Có metric secret version, AUTH failure và queue age.
7. Có khả năng tạm dừng mail dispatch mà không mất outbox.
8. Có kế hoạch rollback hoặc roll-forward thực tế.
9. Có runbook revoke khẩn cấp nếu credential bị lộ.

### Trong rotation

1. Ghi audit change/rotation ID.
2. Xác nhận B hợp lệ trước khi promote.
3. Rollout theo batch hoặc hot-swap an toàn.
4. Kiểm tra pod nào vẫn dùng A.
5. Không để retry storm nếu AUTH lỗi.
6. Canh backlog của OTP/giao dịch và quota provider.
7. Không log password/token trong quá trình chẩn đoán.

### Sau rotation

1. Toàn bộ instance dùng version B theo policy.
2. Auth/canary gửi thành công.
3. Không còn sender in-flight cần A.
4. A được revoke theo thời điểm thích hợp.
5. Outbox đã được drain có kiểm soát.
6. Không còn AUTH failure diện rộng.
7. Không có bản ghi SUBMISSION_UNKNOWN bị replay mù.
8. Audit và dashboard phản ánh version mới.
9. Lịch rotation tiếp theo đã được cập nhật.

## 28. Ví dụ tình huống thực tế

### Tình huống A — Xoay vòng SMTP password định kỳ với hai credential

Một ứng dụng gửi xác nhận đơn hàng có hai worker replica, dùng SMTP credential A. Provider hỗ trợ tạo credential B độc lập với quyền gửi tương đương.

**Cách triển khai:**

1. Tạo B trong secret manager, không để password xuất hiện trong deployment manifest.
2. Chạy một canary bằng B, xác nhận STARTTLS, AUTH và quyền gửi từ địa chỉ đã cho phép.
3. Rollout replica thứ nhất sang B, kiểm tra auth failure và gửi thử.
4. Rollout replica thứ hai sang B.
5. Xác nhận không còn luồng gửi sử dụng A, kể cả job scheduled và worker cũ.
6. Revoke A.
7. Giữ metrics/audit và theo dõi queue sau rollout.

**Kết quả mong muốn:** không làm mất outbox, không có giai đoạn toàn hệ thống không thể AUTH và không lưu secret ở repository.

### Tình huống B — Password hết hạn khi đang xử lý backlog

Một đợt marketing tạo nhiều job, đồng thời các email hóa đơn đang chờ. Credential A bị hết hạn và mọi lần AUTH mới thất bại.

**Không nên:** để từng notification tự retry 10 lần liên tục; cùng lúc 20 pod gọi secret manager và SMTP. Điều này tạo bão xác thực mà không làm email thành công.

**Nên:**

1. Phân loại lỗi AUTH trên account chung.
2. Tạm dừng lane SMTP bị ảnh hưởng và alert.
3. Giữ outbox; dừng email marketing có thể hoãn.
4. Cấp/đọc B, test AUTH và canary.
5. Rollout B, xác minh version toàn cụm.
6. Mở dispatch có giới hạn tốc độ; ưu tiên hóa đơn/OTP còn hợp lệ.
7. Đánh dấu EXPIRED cho marketing/OTP đã hết hạn theo chính sách.

### Tình huống C — OAuth2 token hết hạn giữa đêm

Ứng dụng dùng XOAUTH2 với access token ngắn hạn. Sau một thời gian, token hết hạn và SMTP bắt đầu từ chối.

**Khắc phục đúng hướng:** xác nhận token flow và scope, làm mới token bằng token provider theo policy, kiểm tra đồng hồ và safety margin, tránh đồng loạt refresh tại từng worker. Nếu refresh token đã bị revoke, cần xử lý lại grant/identity theo cơ chế provider; retry cùng access token đã hết hạn không giúp ích.

**Điểm cần đo:** số lần token refresh, độ trễ, tỷ lệ lỗi, thời gian còn hạn, số pod sử dụng token generation hợp lệ, và trạng thái outbox trong thời gian lỗi.

### Tình huống D — Secret mới không có quyền gửi địa chỉ From

Candidate B xác thực thành công bằng SMTP AUTH, nhưng provider không cho gửi từ một địa chỉ From của ứng dụng.

**Vấn đề:** testConnection có thể qua, nhưng send canary có From tương ứng lại bị từ chối.

**Xử lý:** kiểm tra quyền sender/account/verified identity, điều chỉnh cấu hình quyền trên provider, test lại bằng canary hợp lệ và chỉ promote B khi đáp ứng yêu cầu gửi thật. Đừng tự kết luận password sai chỉ vì server từ chối lệnh MAIL FROM.

### Tình huống E — Credential bị lộ trong log

Một developer vô tình log đối tượng SmtpSecret chứa password trong quá trình troubleshooting.

**Xử lý:** coi đây là sự cố credential exposure. Xác định phạm vi log và người có quyền đọc, rotate/revoke credential theo mức độ rủi ro, kiểm tra provider audit về hoạt động gửi trái phép, xóa/giới hạn truy cập log theo chính sách và sửa code để không serialize secret. Chỉ xóa một log line mới phát sinh không đủ để chắc chắn mọi bản sao đã biến mất.

## 29. Câu hỏi tự kiểm tra

**1. Vì sao thay secret trong secret manager không đồng nghĩa JavaMailSender đã thay password?**

Vì JavaMailSenderImpl trong cấu hình thông thường nhận username/password khi bean được tạo. Ứng dụng cần rolling restart, cơ chế refresh đã kiểm chứng hoặc hot-swap sender; secret store không tự sửa object đang chạy.

**2. Rotation khác refresh token thế nào?**

Rotation là chuyển sang credential/version mới và thu hồi credential cũ theo policy. Refresh token ngắn hạn là lấy access token mới cho các lần AUTH tiếp theo; refresh token hoặc client secret cũng có vòng đời riêng có thể phải rotate.

**3. Có nên dùng SMTP password của mailbox cá nhân làm credential production không?**

Không nên. Ưu tiên service identity/credential chuyên dụng, quyền tối thiểu, owner và rotation/audit rõ ràng.

**4. Vì sao không nên cập nhật setUsername và setPassword ngay trên bean đang được nhiều thread dùng?**

Hai lời gọi không tạo một phép thay đổi nguyên tử; thread khác có thể quan sát cấu hình không nhất quán. Tạo sender hoàn chỉnh và swap reference hoặc restart.

**5. Khi nào có thể revoke credential cũ?**

Trong rotation có overlap, sau khi candidate hợp lệ, các instance đã cutover và không còn luồng gửi cần credential cũ theo policy. Trong sự cố credential bị lộ, có thể cần revoke khẩn cấp trước thời điểm đó.

**6. Provider chỉ cho một password thì có thể zero downtime tuyệt đối không?**

Không nên cam kết như vậy. Cần kế hoạch cutover, có thể tạm dừng dispatch, cập nhật tất cả instance và khôi phục backlog. Nếu có hai account/credential riêng được hỗ trợ và quyền phù hợp, có thể thiết kế overlap.

**7. TestConnection thành công có chứng minh email đã được giao tới inbox không?**

Không. Nó chủ yếu kiểm tra kết nối và xác thực theo cấu hình. Cần canary gửi thật để kiểm tra quyền submit; delivery/bounce là giai đoạn khác.

**8. SMTP trả 535 có chắc chắn secret hết hạn không?**

Không. Có thể là credential sai, bị revoke, account bị khóa, cơ chế AUTH không tương thích hoặc lỗi theo policy provider. Cần xem ngữ cảnh, enhanced status và lịch thay đổi.

**9. Lỗi SMTP AUTH có nên retry cho mỗi email không?**

Không nên retry liên tục. Nếu credential chung không hợp lệ, tạm dừng lane và thực hiện refresh/rotation có kiểm soát; outbox giữ job.

**10. Nếu secret manager unavailable nhưng credential đang dùng còn hợp lệ thì sao?**

Có thể tiếp tục dùng credential đã cache theo chính sách khi không có bằng chứng bị revoke/lộ, đồng thời retry refresh có backoff và cảnh báo. Không tiếp tục dùng secret đã biết hết hạn hoặc bị thu hồi.

**11. Access token OAuth2 phải refresh vào lúc nào?**

Trước expiresAt một khoảng đệm phù hợp, xét thêm thời gian kết nối, độ trễ token service và clock skew; không chờ đến lúc AUTH chắc chắn lỗi.

**12. Có cần kiểm tra tất cả pod trong rolling rotation không?**

Có. Một pod hoặc job cũ vẫn dùng credential A có thể thất bại ngay sau khi A bị revoke. Theo dõi version active của toàn bộ workload liên quan.

**13. Có nên bật mail.debug trên production suốt thời gian rotation không?**

Không nên mặc định. Debug protocol có thể làm lộ thông tin nhạy cảm. Chỉ bật có giới hạn, masking, phân quyền và kế hoạch tắt.

**14. Có thể rollback về password cũ sau khi provider đã revoke nó không?**

Không. Khi credential cũ không còn hợp lệ, cần roll forward hoặc cấp credential mới; rollback image không làm password cũ hoạt động.

**15. Secret đã cập nhật thì có nên replay toàn bộ FAILED email không?**

Không. Phải phân biệt trạng thái, lỗi, expiry, suppression và SUBMISSION_UNKNOWN. Chỉ replay các record đủ điều kiện; mọi lần gửi lại qua limiter.

**16. Vì sao expiry monitoring phải có cả status rollout?**

Vì biết secret sắp hết hạn chưa đủ; phải biết candidate đã được kiểm tra chưa và tất cả instance đã chuyển sang version mới hay chưa.

**17. Có thể log username SMTP không?**

Username có thể là định danh nội bộ hoặc địa chỉ email nhạy cảm. Chỉ log khi cần, có masking/quyền truy cập phù hợp; không bao giờ log password hoặc access token.

**18. Vì sao thay password SMTP không đồng nghĩa thay TLS certificate hoặc DKIM key?**

Đó là các credential/chức năng khác nhau: SMTP AUTH kiểm soát đăng nhập relay, TLS bảo vệ kênh kết nối và DKIM ký thông điệp. Mỗi loại có vòng đời và cách rotate riêng.

**19. Làm gì nếu credential B AUTH được nhưng MAIL FROM bị từ chối?**

Kiểm tra sender authorization, verified identities và chính sách provider. Không chuyển toàn bộ traffic trước khi canary gửi với From thực tế thành công.

**20. Làm sao biết rotation thật sự hoàn tất?**

Candidate mới đã được xác minh, mọi workload dùng đúng version, credential cũ đã được revoke theo policy, không còn AUTH failures diện rộng, backlog được xử lý an toàn và audit ghi nhận kết quả.

## Kết luận

**Xoay vòng secret SMTP là một quy trình bảo mật và vận hành liên tục, không chỉ là thay password trong cấu hình.** Với Spring Framework Mail, cần xác định nơi quản lý credential, vòng đời version/expiry, cơ chế nạp lại vào JavaMailSender, quyền SMTP AUTH và cách chuyển các instance mà không làm mất yêu cầu gửi. Khi provider hỗ trợ hai credential, tạo overlap, xác minh candidate rồi mới revoke bản cũ; khi không hỗ trợ, chuẩn bị cutover có kiểm soát và outbox bền vững. Với OAuth2/XOAUTH2, làm mới access token trước expiry và tránh refresh storm. Nếu credential bị từ chối diện rộng, tạm dừng lane gửi, phân loại lỗi, alert và khôi phục bằng secret hợp lệ thay vì retry từng email vô hạn. Cuối cùng, kiểm thử rotation, theo dõi expiry/version drift, bảo vệ log, drain backlog qua rate limiter và ghi audit. **Một hệ thống được thiết kế đúng có thể thay credential an toàn, phát hiện hết hạn trước khi gây sự cố và phục hồi gửi email mà không đánh đổi tính bảo mật hoặc tạo thêm lỗi dây chuyền.**
