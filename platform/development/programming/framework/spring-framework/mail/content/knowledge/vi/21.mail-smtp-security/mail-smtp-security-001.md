# TLS trong kết nối tới mail server

Khi một ứng dụng Spring Framework Mail gửi email, dữ liệu thường đi qua kết nối từ **ứng dụng** đến **SMTP server**. Trên kết nối này có thể xuất hiện thông tin xác thực, envelope sender/recipient, header, nội dung HTML, plain text và tệp đính kèm. Nếu không có lớp bảo vệ phù hợp, dữ liệu có thể bị quan sát hoặc sửa đổi bởi một tác nhân có khả năng can thiệp trên đường truyền.

**Transport Layer Security (TLS)** là cơ chế bảo vệ kết nối mạng bằng mã hóa, xác thực danh tính phía server qua certificate và kiểm tra tính toàn vẹn của dữ liệu trao đổi. Trong SMTP, TLS thường được dùng theo hai cách: **STARTTLS** (nâng cấp một kết nối SMTP ban đầu sang TLS) hoặc **implicit TLS** (thiết lập TLS ngay khi kết nối).

Điểm cốt lõi của bài học:

- TLS bảo vệ **một chặng kết nối** giữa mail client và SMTP server, không tự mã hóa email từ đầu đến cuối.
- **STARTTLS** trên cổng submission thường dùng 587 khác với **implicit TLS** thường dùng cổng 465; không cấu hình cả hai kiểu tùy tiện cho cùng một kết nối.
- Với ứng dụng yêu cầu bảo mật, chỉ bật STARTTLS ở trạng thái tùy chọn là chưa đủ: phải **yêu cầu nâng cấp thành công** và **kiểm tra certificate/hostname**.
- **SMTP AUTH không thay thế TLS**; xác thực account và mã hóa đường truyền có vai trò khác nhau.
- Lỗi TLS thường do cổng sai, STARTTLS không được hỗ trợ, certificate không tin cậy, hostname không khớp hoặc TLS version/cipher không tương thích.
- Không chữa lỗi TLS bằng cách tắt xác thực certificate hoặc tin cậy mọi server.

Bài viết dùng ví dụ Spring Boot và **JavaMailSenderImpl**, đồng thời làm rõ ranh giới an toàn để cấu hình production và chẩn đoán sự cố.

## 1. TLS bảo vệ phần nào của luồng email?

Một email có thể đi qua nhiều hệ thống:

~~~text
Spring application
        |
        |  SMTP submission over TLS
        v
Outbound SMTP server / provider
        |
        |  SMTP relay: có thể có TLS, tùy chính sách và cấu hình
        v
Receiving mail infrastructure
        |
        v
Mailbox and recipient email client
~~~

Khi Spring kết nối tới outbound SMTP server bằng TLS, TLS bảo vệ chặng **Spring application ↔ outbound SMTP server**. Tại server, message thường được giải mã để xử lý, quét, định tuyến, ký, lưu hoặc chuyển tiếp.

Nếu server chuyển thư tới một mail server khác, đó là **kết nối riêng** với cơ chế bảo vệ riêng. Việc chặng đầu dùng TLS không chứng minh mọi chặng sau đều đã dùng TLS.

### 1.1. Các thuộc tính bảo mật của TLS

| Thuộc tính | Ý nghĩa trên kết nối SMTP |
| --- | --- |
| **Confidentiality** | Hạn chế bên thứ ba đọc nội dung kết nối |
| **Integrity** | Phát hiện dữ liệu bị thay đổi khi truyền |
| **Server authentication** | Xác minh server đang kết nối có chứng chỉ hợp lệ cho tên host mong đợi |
| **Session security** | Thiết lập khóa phiên để bảo vệ dữ liệu được truyền trong phiên TLS |

Trong cấu hình SMTP client thông thường, ứng dụng xác thực **server** qua TLS certificate. Client có thể đăng nhập SMTP bằng username/password, app password hoặc OAuth2 sau khi kết nối được bảo vệ. Đây là cơ chế **SMTP AUTH**, không đồng nghĩa với client certificate authentication.

### 1.2. TLS không phải mã hóa end-to-end

TLS chặng ứng dụng không tương đương S/MIME hoặc OpenPGP:

- **TLS:** bảo vệ dữ liệu trong quá trình truyền trên một kết nối cụ thể.
- **S/MIME/OpenPGP:** có thể mã hóa nội dung message cho người nhận cụ thể ở tầng nội dung, theo mô hình quản lý khóa riêng.

Nếu cần chỉ người nhận được phép mới đọc được nội dung, phải đánh giá giải pháp bảo vệ nội dung phù hợp. Không được mô tả SMTP STARTTLS là bảo mật end-to-end.

### 1.3. TLS không bảo đảm email vào inbox

SMTP server có thể chấp nhận message rồi sau đó message bị spam filtering, bounce hoặc không được người nhận mở. TLS không thay thế xác thực domain, kiểm soát spam hoặc theo dõi kết quả chuyển phát.

## 2. STARTTLS hoạt động như thế nào?

**STARTTLS** là một extension của SMTP cho phép client nâng cấp kết nối đang sử dụng SMTP văn bản thông thường sang kết nối được bảo vệ bằng TLS.

Luồng ở mức khái niệm:

~~~text
Spring / Jakarta Mail                     SMTP server
        |                                      |
        |------------- TCP connect ---------->|
        |<-------------- 220 ------------------|
        |------------- EHLO ------------------>|
        |<--------- 250-STARTTLS --------------|
        |------------- STARTTLS ------------->|
        |<-------------- 220 ------------------|
        |======= TLS handshake ===============|
        |     Verify certificate/hostname      |
        |------------- EHLO over TLS --------->|
        |<--------- Server capabilities -------|
        |------------- AUTH over TLS -------->|
        |------------- MAIL FROM ------------->|
        |------------- RCPT TO --------------->|
        |------------- DATA ------------------>|
        |        MIME message over TLS         |
        |<---------- SMTP response ------------|
~~~

Trước khi TLS handshake thành công, các lệnh dùng để thương lượng nâng cấp vẫn diễn ra trên kết nối ban đầu. Sau nâng cấp, client gửi lại EHLO để lấy danh sách khả năng của server trong trạng thái đã bảo mật.

### 2.1. Vì sao cần EHLO lại sau STARTTLS?

Khả năng server công bố trước và sau TLS có thể khác nhau. Chẳng hạn, server có thể không công bố SMTP AUTH trước khi kết nối được mã hóa.

Vì vậy, sau TLS handshake, client phải tiếp tục theo quy trình SMTP đúng, không mặc định mọi extension từ EHLO đầu tiên vẫn có cùng hiệu lực.

### 2.2. STARTTLS là nâng cấp, không phải bật TLS ngay từ byte đầu

Với STARTTLS, kết nối bắt đầu bằng SMTP thường rồi được nâng cấp. Điều đó **không có nghĩa** nội dung và credentials được gửi không mã hóa: nếu client bắt buộc STARTTLS thành công trước AUTH/DATA, những phần nhạy cảm sẽ đi qua TLS.

Ngược lại, nếu ứng dụng cho phép fallback khi server không quảng bá STARTTLS, nó có thể tiếp tục trên kết nối không được mã hóa. Đây là điểm cấu hình cần kiểm soát.

### 2.3. STARTTLS trên cổng nào?

Cổng **587** thường được dùng cho **message submission** và STARTTLS. Đây là lựa chọn phổ biến khi ứng dụng đăng nhập provider để gửi email.

Cổng không tự quyết định TLS: cần tuân theo tài liệu của chính SMTP provider và kiểu kết nối mà endpoint cung cấp.

## 3. Implicit TLS khác STARTTLS ở đâu?

**Implicit TLS** nghĩa là client bắt đầu TLS handshake ngay sau khi mở kết nối TCP, **trước** khi trao đổi lệnh SMTP.

~~~text
Spring / Jakarta Mail                     SMTP server
        |                                      |
        |------------- TCP connect ---------->|
        |======= TLS handshake ===============|
        |     Verify certificate/hostname      |
        |<--------- SMTP greeting over TLS ----|
        |------------- EHLO over TLS --------->|
        |------------- AUTH over TLS --------->|
        |------------- MAIL FROM ------------->|
        |------------- RCPT TO --------------->|
        |------------- DATA ------------------>|
        |          MIME over TLS               |
~~~

Cổng **465** thường được dùng cho SMTP submission qua implicit TLS.

| Điểm so sánh | STARTTLS | Implicit TLS |
| --- | --- | --- |
| Thời điểm TLS handshake | Sau greeting, EHLO và lệnh STARTTLS | Ngay sau TCP connect |
| Cổng submission thường gặp | **587** | **465** |
| Thuộc tính Jakarta Mail điển hình | **mail.smtp.starttls.enable** | **mail.smtp.ssl.enable** |
| Có bước STARTTLS command | Có | Không |
| Kiểm tra certificate/hostname | Cần | Cần |
| Phù hợp | Endpoint yêu cầu STARTTLS | Endpoint dùng TLS từ đầu |

Cả hai phương pháp có thể bảo vệ kết nối tốt nếu được cấu hình đúng. Không nên khẳng định implicit TLS luôn mạnh hơn STARTTLS về mật mã: mức an toàn còn phụ thuộc phiên bản TLS, certificate verification, chính sách fail-closed và server.

### 3.1. Vì sao cùng một cấu hình không dùng được cho cả hai?

Nếu client gửi TLS ClientHello ngay tới endpoint chỉ mong chờ greeting SMTP ban đầu, hoặc gửi plaintext SMTP greeting tới endpoint mong chờ TLS trước, hai phía sẽ không hiểu nhau.

Các triệu chứng có thể là:

- Kết nối treo đến timeout.
- Connection reset.
- SSLException.
- Lỗi dạng “Unrecognized SSL message” hoặc “wrong version number”, tùy provider.
- Server đóng connection ngay sau kết nối.

Đầu tiên hãy kiểm tra **port và mode có khớp tài liệu SMTP server không**.

### 3.2. Có nên bật STARTTLS và SSL đồng thời?

Đối với cùng một endpoint submission, thông thường chọn **một** trong hai kiểu:

- **587/STARTTLS:** bật STARTTLS, không bật implicit TLS.
- **465/implicit TLS:** bật SSL/TLS từ đầu, không cần STARTTLS upgrade.

Không cấu hình cả hai chỉ vì muốn “an toàn hơn”. Nếu hai chế độ được bật cùng lúc, kết quả có thể gây nhầm lẫn hoặc không phù hợp với server; cách đúng là chọn mode của endpoint.

## 4. Cổng 25, 465 và 587 có ý nghĩa gì?

| Cổng | Vai trò thường gặp | TLS thường dùng | Ghi chú |
| --- | --- | --- | --- |
| **25** | SMTP relay giữa mail server | STARTTLS nếu được hỗ trợ/chính sách yêu cầu | Nhiều nhà mạng hoặc cloud hạn chế outbound port 25 |
| **465** | Message submission | Implicit TLS | TLS handshake từ đầu |
| **587** | Message submission | STARTTLS | Thường dùng SMTP AUTH sau nâng cấp |

Đây là **quy ước phổ biến**, không phải luật bắt buộc cho mọi máy chủ. Provider nội bộ có thể dùng cổng khác.

Ứng dụng Spring thường đóng vai trò **mail submission client**, nên cần theo hướng dẫn provider cho 465 hoặc 587, thay vì mặc định dùng port 25 của SMTP relay.

## 5. Cấu hình Spring Boot với STARTTLS trên cổng 587

Cấu hình YAML minh họa:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
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

Giá trị cần hiểu:

| Property | Mục đích |
| --- | --- |
| **spring.mail.host** | Tên SMTP host |
| **spring.mail.port** | Cổng của endpoint STARTTLS |
| **spring.mail.username/password** | Credentials SMTP, cấp qua môi trường/secret manager |
| **spring.mail.default-encoding** | Default charset cho văn bản email, không điều khiển TLS |
| **mail.smtp.auth** | Bật SMTP authentication |
| **mail.smtp.starttls.enable** | Cho phép Jakarta Mail nâng cấp qua STARTTLS nếu server hỗ trợ |
| **mail.smtp.starttls.required** | Không tiếp tục nếu STARTTLS không khả dụng hoặc không hoàn tất |
| **mail.smtp.ssl.checkserveridentity** | Bật kiểm tra danh tính tên host của TLS peer |
| **mail.smtp.connectiontimeout** | Giới hạn thời gian kết nối |
| **mail.smtp.timeout** | Giới hạn thời gian chờ đọc |
| **mail.smtp.writetimeout** | Giới hạn thời gian chờ ghi |

Ví dụ dùng host và account giả định **example.org**. Biến môi trường nên được cấp qua cơ chế quản lý secrets; không lưu password thật trong source control.

### 5.1. Điểm khác biệt giữa enable và required

Hai property thường gây nhầm:

~~~properties
spring.mail.properties[mail.smtp.starttls.enable]=true
spring.mail.properties[mail.smtp.starttls.required]=true
~~~

- **starttls.enable=true** cho phép dùng STARTTLS khi server hỗ trợ. Nếu server không quảng bá STARTTLS, hành vi mặc định có thể tiếp tục không mã hóa.
- **starttls.required=true** yêu cầu STARTTLS; nếu server không cung cấp STARTTLS hoặc nâng cấp thất bại, thao tác không được tiếp tục bình thường.

Đối với submission dùng account và thông tin nhạy cảm, **nên cấu hình cả enable và required bằng true** khi endpoint đã được xác định là STARTTLS.

### 5.2. Vì sao required cần thiết?

Nếu chỉ bật enable:

~~~text
SMTP server không quảng bá STARTTLS
        |
        v
Client vẫn có thể tiếp tục phiên không mã hóa
        |
        v
Nguy cơ truyền AUTH/MIME qua plaintext
~~~

Khi required:

~~~text
SMTP server không quảng bá STARTTLS
        |
        v
Client báo lỗi, không gửi message
~~~

Đây là nguyên tắc **fail closed**: ưu tiên dừng gửi khi điều kiện bảo mật bắt buộc chưa được đáp ứng.

### 5.3. Tại sao default-encoding không bảo vệ kết nối?

**UTF-8** là charset của nội dung văn bản. Nó không mã hóa dữ liệu để chống đọc trộm. **Base64** trong MIME cũng không phải encryption bảo mật.

TLS hoạt động ở tầng truyền tải; charset và Content-Transfer-Encoding hoạt động ở tầng biểu diễn nội dung.

## 6. Cấu hình Spring Boot với implicit TLS trên cổng 465

Khi provider yêu cầu TLS ngay từ đầu:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.ssl.enable]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
~~~

Ở đây **mail.smtp.ssl.enable=true** làm cho kết nối SMTP sử dụng TLS từ đầu. Không cần bật STARTTLS required cho một endpoint implicit TLS đúng nghĩa.

### 6.1. Property name vẫn bắt đầu bằng mail.smtp

Trong cách dùng phổ biến với **JavaMailSenderImpl** và protocol **smtp**, cấu hình implicit TLS có thể dùng **mail.smtp.ssl.enable=true**. Không nhất thiết phải tự đổi protocol thành **smtps**.

Nếu ứng dụng dùng transport protocol **smtps** riêng, tên thuộc tính và cách khởi tạo transport có thể khác; hãy kiểm tra tài liệu provider Jakarta Mail cho mode đó. Không trộn ngẫu nhiên các tiền tố **mail.smtp** và **mail.smtps**.

### 6.2. Khi nào chọn cổng 465?

Chọn nếu SMTP provider cung cấp submission endpoint explicit cho implicit TLS, hoặc chính sách triển khai quy định như vậy. Không chỉ đổi port từ 587 sang 465 mà giữ nguyên toàn bộ STARTTLS settings.

## 7. Cấu hình tương đương bằng application.properties

Dạng properties với STARTTLS:

~~~properties
spring.mail.host=smtp.example.org
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.default-encoding=UTF-8

spring.mail.properties[mail.smtp.auth]=true
spring.mail.properties[mail.smtp.starttls.enable]=true
spring.mail.properties[mail.smtp.starttls.required]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true

spring.mail.properties[mail.smtp.connectiontimeout]=5000
spring.mail.properties[mail.smtp.timeout]=10000
spring.mail.properties[mail.smtp.writetimeout]=10000
~~~

Dạng properties với implicit TLS:

~~~properties
spring.mail.host=smtp.example.org
spring.mail.port=465
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties[mail.smtp.auth]=true
spring.mail.properties[mail.smtp.ssl.enable]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true
~~~

Dấu ngoặc vuông giúp biểu diễn chính xác key trong map JavaMail properties. Trong YAML, key có dấu chấm nên được đặt trong dấu ngoặc kép như các ví dụ ở trên.

## 8. Cấu hình trực tiếp JavaMailSenderImpl không dùng Boot

Trong ứng dụng Spring Framework thuần, có thể khởi tạo **JavaMailSenderImpl**:

~~~java
import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public class MailSenderFactory {

    public JavaMailSenderImpl create(
            String host,
            int port,
            String username,
            String password
    ) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();

        sender.setHost(host);
        sender.setPort(port);
        sender.setProtocol("smtp");
        sender.setUsername(username);
        sender.setPassword(password);
        sender.setDefaultEncoding("UTF-8");

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

Method nhận host/account/secret từ cấu hình bên ngoài. Không hard-code mật khẩu trong source.

### 8.1. Đối với implicit TLS

Thay cấu hình mode:

~~~java
sender.setPort(465);

Properties properties = new Properties();
properties.put("mail.smtp.auth", "true");
properties.put("mail.smtp.ssl.enable", "true");
properties.put("mail.smtp.ssl.checkserveridentity", "true");

sender.setJavaMailProperties(properties);
~~~

Đừng đồng thời giữ các property STARTTLS từ factory trước nếu endpoint thật sự yêu cầu implicit TLS.

### 8.2. Không tạo JavaMailSender mới cho mỗi message

Thông thường Spring Boot đã auto-configure **JavaMailSender** nếu điều kiện dependency và cấu hình phù hợp. Hãy inject bean vào service.

Nếu có nhiều SMTP account/tenant, cần thiết kế cơ chế chọn sender và quản lý tài nguyên có kiểm soát, tránh tạo cấu hình kết nối tùy tiện từ dữ liệu người dùng.

## 9. Ví dụ service gửi mail qua kết nối TLS

TLS được cấu hình cho **transport**, không phải từng MimeMessage. Một service gửi thư dùng JavaMailSender như bình thường:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class SecureNotificationMailService {

    private final JavaMailSender mailSender;

    public SecureNotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotification(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                false,
                "UTF-8"
        );

        helper.setFrom("notifications@example.org");
        helper.setTo(recipient);
        helper.setSubject("Thông báo tài khoản");
        helper.setText(
                "Một thay đổi trong tài khoản đã được ghi nhận.",
                false
        );

        mailSender.send(message);
    }
}
~~~

Tầng business không cần gọi STARTTLS trực tiếp. Jakarta Mail transport xử lý handshake theo **mail.smtp.\*** properties.

### 9.1. Những điều service không tự bảo đảm

Chỉ thấy **mailSender.send(message)** chạy thành công không chứng minh:

- Tất cả các relay tiếp theo đều dùng TLS.
- Message được mã hóa end-to-end.
- Message đã tới inbox.
- Người nhận đã đọc email.
- Nội dung email an toàn nếu mailbox bị chiếm quyền.

Đó là những yêu cầu riêng với các cơ chế giám sát và bảo vệ khác nhau.

## 10. SMTP AUTH nên diễn ra sau khi TLS được thiết lập

Một lỗi thiết kế nguy hiểm là cho phép username/password được gửi qua kết nối không mã hóa.

Với server hỗ trợ STARTTLS, trình tự phù hợp là:

~~~text
TCP connect
    |
    v
EHLO
    |
    v
STARTTLS
    |
    v
TLS handshake + server certificate verification
    |
    v
EHLO again
    |
    v
SMTP AUTH
    |
    v
MAIL FROM / RCPT TO / DATA
~~~

Nếu dùng implicit TLS, handshake đã hoàn tất trước khi server greeting và AUTH.

### 10.1. SMTP AUTH không phải encryption

**mail.smtp.auth=true** chỉ yêu cầu SMTP authentication theo khả năng server. Nó **không tự bật TLS**.

Một cấu hình gồm username/password và AUTH nhưng không bật TLS theo policy có thể khiến credential bị truyền trong một phiên không được bảo vệ, tùy server và mechanism. Để tránh sai sót, yêu cầu TLS tại client và dùng server submission hỗ trợ bảo mật.

### 10.2. AUTH mechanism có ảnh hưởng không?

SMTP có nhiều mechanism xác thực, có thể gồm PLAIN, LOGIN hoặc OAuth-based mechanisms. Một số mechanism đưa dữ liệu xác thực theo một dạng mã hóa biểu diễn chứ không phải encryption mạnh; vì vậy vẫn cần TLS cho kết nối.

**Không coi Base64 của AUTH PLAIN/LOGIN là một lớp mã hóa bảo mật.**

### 10.3. TLS và OAuth2 là hai lớp khác nhau

OAuth2 access token hạn chế cách client chứng minh quyền truy cập, còn TLS bảo vệ token trên đường truyền. Token hết hạn hoặc sai scope cần được xử lý ở tầng xác thực; tắt TLS không sửa được lỗi đó.

## 11. Certificate và trust chain: server có đáng tin không?

Trong TLS handshake, server gửi certificate chain để client xác minh. JVM thường dùng Java TLS stack và trust material phù hợp với môi trường triển khai.

Kiểm tra thường bao gồm:

- Certificate còn hạn.
- Chain đi tới một certificate authority được tin cậy.
- Signature và chain hợp lệ.
- Tên host mà ứng dụng kết nối khớp với danh tính trong certificate.
- TLS protocol/cipher được cả hai phía hỗ trợ.
- Những kiểm tra bổ sung theo cấu hình runtime hoặc chính sách triển khai.

### 11.1. Trust chain không đồng nghĩa hostname đúng

Giả sử certificate được cấp bởi CA hợp lệ nhưng tên host là:

~~~text
mail-other.example.org
~~~

trong khi ứng dụng kết nối tới:

~~~text
smtp.example.org
~~~

Nếu không kiểm tra hostname, ứng dụng có thể chấp nhận kết nối tới endpoint có certificate thuộc tên khác. Vì vậy, cần bật kiểm tra danh tính server.

### 11.2. Bật hostname verification trong Jakarta Mail

Property:

~~~properties
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true
~~~

Trong Java:

~~~java
properties.put(
        "mail.smtp.ssl.checkserveridentity",
        "true"
);
~~~

Không nên dựa vào một mặc định mà chưa xác nhận ở phiên bản mail provider/JDK đang triển khai. Bật nó rõ ràng giúp thể hiện yêu cầu hostname verification.

### 11.3. Certificate SAN và tên host

Certificate hiện đại thường chỉ định tên DNS hợp lệ trong **Subject Alternative Name (SAN)**. Endpoint SMTP mà ứng dụng kết nối phải có tên phù hợp với certificate.

Nếu ứng dụng dùng alias riêng hoặc load balancer, cần bảo đảm alias đó được certificate hỗ trợ. Không sửa lỗi mismatch bằng cách vô hiệu hóa hostname verification.

### 11.4. Private CA trong môi trường doanh nghiệp

Một SMTP server nội bộ có thể dùng certificate do CA nội bộ cấp. Nếu JVM chưa tin CA đó, handshake có thể báo lỗi PKIX hoặc certificate path validation.

Cách xử lý đúng:

1. Xác nhận certificate và tên host do tổ chức quản lý.
2. Bổ sung CA nội bộ vào truststore phù hợp theo chính sách.
3. Cấu hình JVM hoặc SSL context đáng tin cậy.
4. Giữ hostname verification.
5. Tái kiểm tra bằng endpoint thực tế.

Tránh cập nhật truststore toàn JVM không kiểm soát nếu ứng dụng còn kết nối nhiều hệ thống khác; giới hạn phạm vi tin cậy khi kiến trúc cho phép.

## 12. Những cấu hình TLS nguy hiểm cần tránh

### 12.1. Tin cậy mọi server

Một cấu hình không an toàn:

~~~properties
spring.mail.properties[mail.smtp.ssl.trust]=*
~~~

Thuộc tính đặc thù của provider có thể khiến client tin cậy rộng các host thay vì kiểm tra trust chain theo cơ chế bình thường. Điều này làm giảm khả năng chống giả mạo server.

Không dùng thiết lập **trust=*** như cách sửa nhanh lỗi PKIX trong production.

### 12.2. Tắt hostname verification

Cấu hình không phù hợp cho môi trường cần bảo mật:

~~~properties
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=false
~~~

Ngay cả khi certificate chain được chấp nhận, server identity có thể không được kiểm tra theo tên host mong đợi.

### 12.3. Tắt STARTTLS required để “gửi cho được”

~~~properties
spring.mail.properties[mail.smtp.starttls.required]=false
~~~

Nếu yêu cầu nghiệp vụ là chỉ gửi qua TLS, việc tắt required có thể làm hệ thống fallback sang kết nối không mã hóa khi server không hỗ trợ STARTTLS.

Khi server gặp sự cố TLS, hãy điều tra endpoint, certificate, cấu hình và mạng, không âm thầm bỏ yêu cầu bảo mật.

### 12.4. Tắt kiểm tra certificate ở custom SSLSocketFactory

Một custom TrustManager chấp nhận mọi certificate có thể khiến kết nối TLS mã hóa nhưng không chứng minh được danh tính server. Kẻ tấn công có thể trình bày certificate tùy ý để giả mạo endpoint.

Nếu có yêu cầu custom truststore hoặc TLS policy, hãy cấu hình lớp tin cậy đúng, không viết TrustManager “always true”.

### 12.5. Bật debug chứa secrets

Protocol debug có thể làm lộ metadata hoặc thông tin xác thực, tùy implementation và cấu hình. Không dùng debug chi tiết không kiểm soát ở production.

## 13. STARTTLS downgrade attack và fail-closed

Vì STARTTLS được công bố qua EHLO trước khi TLS bắt đầu, một tác nhân có khả năng sửa đổi kết nối có thể cố tình can thiệp vào phần thương lượng.

Ví dụ khái niệm:

~~~text
Client                    Attacker                 Server
  |                         |                       |
  |------ EHLO ------------>|------ EHLO ---------->|
  |                         |<--- 250-STARTTLS -----|
  |<--- 250 (đã bỏ TLS) ----|                       |
  |                         |                       |
  | Client tưởng server không hỗ trợ STARTTLS       |
~~~

Nếu ứng dụng chỉ bật **starttls.enable**, client có thể tiếp tục trong plaintext khi không thấy extension.

Nếu ứng dụng bật **starttls.required=true**, nó phải dừng thay vì fallback theo kiểu không mã hóa.

### 13.1. Khi nào bắt buộc fail-closed?

Với ứng dụng gửi qua account SMTP submission, đặc biệt có thông tin xác thực hoặc nội dung nhạy cảm, chính sách thường nên yêu cầu:

- STARTTLS hoặc implicit TLS theo endpoint.
- Certificate validation.
- Hostname verification.
- Không gửi AUTH/DATA nếu bảo mật bắt buộc chưa được thiết lập.

### 13.2. Fail-closed có đánh đổi gì?

Có. Khi TLS server lỗi, email có thể tạm ngừng gửi. Đây là sự đánh đổi có chủ đích giữa **tính sẵn sàng** và **yêu cầu bảo mật tối thiểu**.

Ứng dụng nên chuyển tác vụ sang retry/backoff hoặc trạng thái cần hỗ trợ, thay vì bí mật hạ cấp kết nối.

## 14. TLS phiên bản và cipher suites

TLS có nhiều phiên bản. Trong hệ thống hiện đại, **TLS 1.2 và TLS 1.3** thường là mục tiêu triển khai phù hợp, tùy JVM, SMTP server và chính sách tổ chức.

Các phiên bản cũ như TLS 1.0/1.1 không nên được chủ động bật cho kết nối mới nếu không có yêu cầu legacy đặc biệt đã được đánh giá rủi ro.

### 14.1. JVM và Jakarta Mail chia trách nhiệm thế nào?

- **JDK/JSSE:** triển khai TLS protocol, cryptography, certificate processing và truststore.
- **Jakarta Mail provider:** tạo SMTP connection, dùng TLS stack và đọc các property.
- **Spring Mail:** cung cấp JavaMailSender/JavaMailSenderImpl và cấu hình.
- **SMTP server:** công bố và hỗ trợ các protocol/cipher thực tế.

Không thể ép server hỗ trợ TLS 1.3 chỉ bằng một property phía client.

### 14.2. Chỉ định protocol khi thực sự cần

Một số provider hỗ trợ property:

~~~properties
spring.mail.properties[mail.smtp.ssl.protocols]=TLSv1.3 TLSv1.2
~~~

Property này thường nhận danh sách protocol được phân tách bằng khoảng trắng. Chỉ dùng khi cần chính sách cụ thể và đã kiểm tra hỗ trợ ở JDK/provider/server. Cấu hình không phù hợp có thể khiến handshake thất bại ngay cả khi server có một cấu hình TLS an toàn khác.

Nếu tổ chức có baseline security cho TLS, ưu tiên áp dụng đồng bộ trong JVM/runtime và kiểm thử tương thích theo môi trường.

### 14.3. Cipher suite

Các cipher được hỗ trợ phụ thuộc JDK và server. Nếu cần giới hạn cipher suite, sử dụng những cấu hình được provider/JDK hỗ trợ và được đội bảo mật phê duyệt.

Không sao chép danh sách cipher của một hệ thống khác mà chưa kiểm tra phiên bản Java, thuật toán bị vô hiệu hóa và khả năng của SMTP server.

## 15. Sự khác nhau giữa TLS handshake failure và SMTP AUTH failure

Hai loại lỗi này thường bị trộn với nhau.

### 15.1. TLS handshake failure

Ví dụ chuỗi nguyên nhân:

~~~text
MailSendException
    |
    v
MessagingException / SSLException
    |
    v
SSLHandshakeException
    |
    +-- PKIX path building failed
    +-- Certificate expired
    +-- Hostname verification failed
    +-- No appropriate protocol
~~~

Đây là lỗi ở bước thiết lập kết nối bảo mật. Chưa nên thử đổi password chỉ vì SMTP send thất bại.

### 15.2. SMTP AUTH failure

Ví dụ:

~~~text
MailAuthenticationException
    |
    v
AuthenticationFailedException
    |
    v
535 5.7.8 Authentication credentials invalid
~~~

TLS có thể đã thành công nhưng credentials vẫn sai hoặc account không được cấp quyền.

### 15.3. Bảng phân biệt nhanh

| Hiện tượng | Nghi vấn chính | Kiểm tra |
| --- | --- | --- |
| PKIX path building failed | Trust chain/CA | Certificate chain, truststore |
| No subject alternative name matching | Hostname mismatch | SAN, host đang kết nối |
| Handshake failure | TLS protocol/cipher/certificate | JDK, server capability, TLS baseline |
| 535 authentication failed | Credentials/quyền AUTH | Username, token, SMTP AUTH policy |
| STARTTLS is required but host does not support it | Mode/endpoint/advertisement | Port, EHLO capabilities, provider |
| Connection reset trên port 465 | Có thể sai mode/port hoặc mạng | Implicit TLS endpoint, firewall |
| Timeout ở connect | Network/route/firewall/provider | Host, port, DNS, timeout |
| Timeout sau DATA | Kết quả gửi chưa chắc chắn | SMTP phase, retry/idempotency |

## 16. Lỗi thường gặp khi cấu hình cổng và TLS mode

### 16.1. Port 587 nhưng bật implicit TLS

Ví dụ không khớp với endpoint STARTTLS phổ biến:

~~~properties
spring.mail.port=587
spring.mail.properties[mail.smtp.ssl.enable]=true
~~~

Client cố thực hiện TLS ngay từ đầu trong khi server đang chuẩn bị trả SMTP greeting ở plaintext. Kết quả có thể là timeout hoặc SSLException.

Khắc phục bằng cách dùng STARTTLS trên endpoint đó, nếu provider xác nhận.

### 16.2. Port 465 nhưng chỉ bật STARTTLS

Nếu server mong TLS ngay từ đầu mà client đợi SMTP greeting plaintext, kết nối có thể treo hoặc bị đóng.

Cấu hình implicit TLS thay vì STARTTLS cho endpoint 465.

### 16.3. Chỉ bật mail.smtp.auth

~~~properties
spring.mail.properties[mail.smtp.auth]=true
~~~

Dòng này không yêu cầu TLS. Với provider bắt buộc STARTTLS, việc thiếu starttls properties có thể gây lỗi AUTH hoặc dẫn tới kết nối không thỏa chính sách.

### 16.4. Chỉ bật starttls.enable

~~~properties
spring.mail.properties[mail.smtp.starttls.enable]=true
~~~

Điều này có thể chưa đáp ứng yêu cầu “không gửi khi TLS không khả dụng”. Khi cần fail closed, bật required.

### 16.5. Dùng SMTP host nội bộ không khớp certificate

Ví dụ kết nối bằng IP hoặc alias ngắn trong khi certificate chỉ có tên DNS đầy đủ có thể gây lỗi hostname verification.

Giải pháp là dùng hostname được certificate hỗ trợ hoặc cấp certificate đúng, không tắt checkserveridentity.

## 17. Timeouts, giới hạn retry và độ tin cậy

Một kết nối TLS/SMTP có thể bị chậm hoặc treo ở các bước khác nhau. Đặt timeout hữu hạn là quan trọng trong production:

~~~properties
spring.mail.properties[mail.smtp.connectiontimeout]=5000
spring.mail.properties[mail.smtp.timeout]=10000
spring.mail.properties[mail.smtp.writetimeout]=10000
~~~

Các con số chỉ là ví dụ. Cần chỉnh theo thời gian phản hồi provider, kích thước MIME, chất lượng mạng và SLA.

### 17.1. Vì sao có ba timeout?

- **connectiontimeout:** chờ tạo kết nối tới server.
- **timeout:** chờ đọc dữ liệu/phản hồi từ server.
- **writetimeout:** chờ ghi byte ra kết nối.

Một timeout ở giai đoạn đọc sau DATA có thể xảy ra sau khi SMTP server đã nhận message. Vì vậy, không thể mặc định mọi timeout đều là một thất bại chắc chắn chưa gửi.

### 17.2. Retry không nên hạ cấp TLS

Nếu lỗi xảy ra do certificate không hợp lệ hoặc STARTTLS không hỗ trợ, retry bằng cách tắt TLS có thể vi phạm yêu cầu bảo mật.

Nên phân loại:

| Lỗi | Hành động phù hợp |
| --- | --- |
| Network timeout tạm thời trước DATA | Retry có backoff, giới hạn |
| Server tạm thời quá tải | Chờ và thử lại theo policy |
| Certificate expired hoặc hostname mismatch | Dừng, sửa cấu hình/certificate |
| Không có STARTTLS khi required | Dừng và kiểm tra endpoint/chính sách |
| AUTH credentials invalid | Dừng retry mù, sửa credentials |
| Kết quả không rõ sau DATA | Đối soát hoặc retry thận trọng vì có nguy cơ trùng |

### 17.3. Không gửi SMTP trong transaction database kéo dài

SMTP I/O có thể mất nhiều giây. Nếu gọi mailSender.send() trong method @Transactional, database connection/lock có thể bị giữ trong khi đang thương lượng TLS hoặc chờ SMTP.

Với thông báo sau commit, dùng service gọi sau transaction, TransactionalEventListener(AFTER_COMMIT) hoặc transactional outbox khi yêu cầu phục hồi cao. Cách này giảm coupling giữa độ trễ SMTP/TLS và transaction nghiệp vụ.

## 18. Debug TLS an toàn

Khi điều tra lỗi, các lớp logging khác nhau cung cấp thông tin khác nhau:

1. **Application log:** event ID, account reference, host/port/mode, loại exception.
2. **Jakarta Mail protocol debug:** lệnh SMTP và phản hồi, khi được bật có kiểm soát.
3. **JVM SSL debug:** thông tin TLS handshake, certificate và protocol, cần hạn chế trong môi trường chẩn đoán.

### 18.1. Jakarta Mail debug

Ví dụ môi trường phát triển:

~~~yaml
spring:
  mail:
    properties:
      "[mail.debug]": "true"
~~~

Dùng debug trong thời gian giới hạn; phải xem chính sách ghi log vì transcript có thể lộ metadata như sender, recipient, server capabilities hoặc thông tin khác.

### 18.2. JSSE debug

JVM có thể hỗ trợ system property:

~~~text
-Djavax.net.debug=ssl,handshake
~~~

Tùy JDK, nó giúp nhìn thông tin handshake, certificate và protocol negotiation.

**Không bật debug handshake và protocol log chi tiết như một mặc định của production.** Log cần có quyền truy cập hạn chế và thời hạn lưu phù hợp.

### 18.3. Không ghi password hoặc AUTH payload

Không log:

- SMTP password.
- OAuth access/refresh token.
- Raw SMTP AUTH data.
- Nội dung email hoặc attachment chỉ để chứng minh TLS.
- Toàn bộ địa chỉ người nhận khi không cần thiết.

Trong nhiều trường hợp, mã lỗi, tên host, port, TLS mode và correlation ID đã đủ để xác định hướng điều tra.

## 19. Ví dụ chẩn đoán STARTTLS bằng công cụ mạng

Khi có quyền kiểm thử endpoint, có thể dùng công cụ TLS để xác minh server công bố STARTTLS và trình bày certificate nào.

Ví dụ minh họa với OpenSSL:

~~~bash
openssl s_client \
  -starttls smtp \
  -connect smtp.example.org:587 \
  -servername smtp.example.org \
  -verify_hostname smtp.example.org
~~~

Đối với implicit TLS:

~~~bash
openssl s_client \
  -connect smtp.example.org:465 \
  -servername smtp.example.org \
  -verify_hostname smtp.example.org
~~~

Cần đọc toàn bộ kết quả verify và chain, không chỉ thấy TLS handshake thành công. Các tùy chọn hỗ trợ có thể phụ thuộc phiên bản OpenSSL.

Các lệnh này dùng để **chẩn đoán TLS endpoint**, không có nghĩa JavaMailSender sẽ tự dùng OpenSSL. Ứng dụng Java sử dụng TLS stack và truststore của runtime Java.

### 19.1. Điều gì cần quan sát?

- Có kết nối tới đúng host/port không?
- STARTTLS có được quảng bá ở endpoint 587 không?
- TLS handshake hoàn tất không?
- Certificate chain có hợp lệ không?
- SAN có tên host mong đợi không?
- TLS version/cipher được thương lượng có phù hợp policy không?
- Endpoint có yêu cầu authentication sau TLS không?

### 19.2. Vì sao OpenSSL thành công nhưng Java vẫn báo PKIX?

OpenSSL và JVM có thể dùng các trust store khác nhau. Một CA được OpenSSL tin cậy chưa chắc đã có trong Java truststore của ứng dụng.

Cần xác minh JDK, container image, runtime options và truststore thực tế mà ứng dụng dùng.

## 20. Kiểm thử cấu hình TLS trong môi trường Spring

Không nên chỉ dựa vào việc ứng dụng khởi động thành công. Một số cấu hình mail được kiểm tra khi thật sự mở connection.

### 20.1. Test bằng SMTP server dành riêng cho môi trường kiểm thử

Có thể dùng một SMTP test server hỗ trợ TLS với certificate và policy rõ ràng để kiểm tra:

- STARTTLS required và server có STARTTLS → kết nối được.
- STARTTLS required nhưng server không hỗ trợ → gửi thất bại.
- Certificate không tin cậy → handshake phải thất bại.
- Hostname mismatch → kết nối phải thất bại khi checkserveridentity được bật.
- Implicit TLS endpoint trên 465 → kết nối đúng mode.
- Sai port/mode → báo lỗi phù hợp, không tự fallback plaintext.
- Credentials sai → AUTH thất bại dù TLS thành công.

Không cố tình cấu hình certificate giả hoặc đăng nhập sai hàng loạt trên SMTP production.

### 20.2. Test fail-closed

Một test quan trọng là cho server không công bố STARTTLS và xác nhận client đã cấu hình **required=true** không gửi nội dung qua plaintext.

Kiểm tra này phản ánh yêu cầu bảo mật tốt hơn test chỉ xác nhận “gửi được”.

### 20.3. Test hostname verification

Thử một certificate có chain hợp lệ nhưng SAN không khớp hostname. Client phải từ chối nếu chính sách yêu cầu xác minh hostname.

Không xem kết nối đó thành công chỉ vì certificate do một CA hợp lệ cấp.

### 20.4. Test timeout và retry

Nếu test làm server ngừng phản hồi, cần kiểm tra worker không giữ tài nguyên vô hạn, trạng thái tác vụ được ghi nhận và retry có giới hạn. Nếu lỗi xảy ra sau DATA, kết quả có thể không xác định và có nguy cơ gửi trùng.

## 21. Các biện pháp bảo mật bổ sung ngoài TLS client

TLS là nền tảng bảo vệ kết nối, nhưng hệ thống gửi email còn cần các lớp bảo vệ khác.

### 21.1. SPF, DKIM và DMARC

Các cơ chế này liên quan xác thực nguồn gửi và chống giả mạo domain, không phải encryption của SMTP session.

| Cơ chế | Vai trò chính |
| --- | --- |
| **SPF** | Xác định những host được phép gửi thay domain trong ngữ cảnh SMTP |
| **DKIM** | Gắn chữ ký vào message để xác thực domain ký và tính toàn vẹn các thành phần được ký |
| **DMARC** | Chính sách/đánh giá alignment của SPF/DKIM với From domain |
| **TLS** | Bảo vệ một kết nối truyền tải |

Một email có DKIM hợp lệ không chứng minh chặng gửi dùng TLS. Một SMTP session được TLS bảo vệ cũng không chứng minh From domain có DKIM/SPF/DMARC hợp lệ.

### 21.2. MTA-STS và DANE

Trong môi trường trao đổi email giữa mail transfer agents, **MTA-STS** và **DANE** là những cơ chế có thể hỗ trợ chính sách bảo vệ/kiểm tra TLS của các chặng chuyển phát phù hợp.

Chúng không thay thế cấu hình JavaMailSender của ứng dụng khi gửi tới submission server qua 587 hoặc 465. Phạm vi và yêu cầu triển khai nằm ở hạ tầng mail transport/server nhận, không đơn thuần ở dòng code Spring Mail.

### 21.3. Bảo vệ credentials

Nên sử dụng:

- Secret manager hoặc biến môi trường được kiểm soát.
- Phân quyền tối thiểu cho SMTP account.
- Xoay vòng credential theo chính sách.
- Giới hạn domain/From identity được phép.
- Theo dõi lỗi AUTH bất thường.
- Không đưa secret vào repository, ticket hoặc log.

### 21.4. Bảo vệ nội dung nhạy cảm

TLS không ngăn người nhận chuyển tiếp email, mailbox bị chiếm quyền hoặc provider lưu nội dung. Với tài liệu đặc biệt nhạy cảm, có thể cần gửi link tải được xác thực có thời hạn hoặc giải pháp mã hóa nội dung riêng.

## 22. Những lỗi cấu hình và hướng khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Hướng khắc phục |
| --- | --- | --- |
| Không kết nối được smtp.example.org:587 | DNS, firewall, host hoặc port sai | Kiểm tra endpoint và network route |
| SSLException khi dùng 587 | Bật implicit TLS vào cổng STARTTLS | Chọn STARTTLS mode |
| Timeout khi dùng 465 | Client chờ greeting plaintext nhưng server đợi TLS | Bật implicit TLS |
| STARTTLS required nhưng server không hỗ trợ | Sai endpoint hoặc server thiếu STARTTLS | Chọn endpoint đúng, giữ fail-closed |
| PKIX path building failed | CA/chain không tin cậy | Sửa chain/truststore |
| Hostname verification failed | Host không khớp SAN | Dùng đúng DNS/certificate |
| Certificate expired | Certificate server hết hạn | Gia hạn/thay certificate |
| No appropriate TLS protocol | Version/cipher không giao nhau | Kiểm tra JDK và server policy |
| AUTH 535 sau TLS | Credentials hoặc SMTP AUTH policy sai | Sửa account, không tắt TLS |
| AUTH not available before STARTTLS | Chưa nâng cấp TLS | Bật STARTTLS required |
| Mail gửi được ở dev, lỗi ở container | Truststore/JDK/network khác | Kiểm tra runtime thực tế |
| SMTP send timeout | Server/mạng chậm hoặc phase lỗi | Phân loại timeout và retry có kiểm soát |
| Email bị bounce sau gửi thành công | Delivery downstream thất bại | Theo dõi bounce riêng, không quy cho TLS |
| Gửi được nhưng compliance yêu cầu TLS bắt buộc | Chỉ bật starttls.enable | Bật required và xác minh hostname |

## 23. Câu hỏi thường gặp

**1. TLS trong SMTP dùng để làm gì?**

Nó mã hóa và bảo vệ tính toàn vẹn của dữ liệu trên kết nối giữa SMTP client và server, đồng thời hỗ trợ xác minh danh tính server bằng certificate.

**2. STARTTLS khác SSL/TLS trên cổng 465 ở đâu?**

STARTTLS nâng cấp một phiên SMTP ban đầu sang TLS. Implicit TLS bắt đầu TLS handshake ngay sau TCP connection. Hai endpoint có quy trình khác nhau.

**3. Port 587 có luôn là STARTTLS không?**

Thường dùng 587 cho submission với STARTTLS, nhưng phải theo cấu hình provider. Cổng không thay cho việc xác minh mode thực tế.

**4. Dùng 465 có nhất thiết phải cấu hình mail.smtp.ssl.enable=true không?**

Nếu JavaMailSender dùng protocol smtp và endpoint yêu cầu implicit TLS, đây là cấu hình điển hình để bắt đầu TLS từ đầu. Cần theo dõi phiên bản/provider và tài liệu endpoint.

**5. starttls.enable=true có đủ cho production không?**

Chưa đủ nếu policy bắt buộc TLS. Nên dùng **starttls.required=true** và **ssl.checkserveridentity=true** khi kết nối tới endpoint STARTTLS.

**6. Vì sao cần checkserveridentity?**

Để xác minh server TLS có certificate phù hợp với hostname ứng dụng định kết nối. Chỉ tin chain CA mà không kiểm tra tên có thể không đủ chống giả mạo endpoint.

**7. Có thể dùng mail.smtp.ssl.trust=* để sửa PKIX không?**

Không nên trong production. Cần xác minh chain và cấu hình CA/truststore thích hợp, không tin cậy mọi server.

**8. TLS có làm email được mã hóa end-to-end không?**

Không. TLS bảo vệ một kết nối. Các mail server trung gian có thể giải mã và xử lý message. End-to-end encryption là yêu cầu riêng.

**9. TLS có thay thế SMTP AUTH không?**

Không. TLS bảo vệ kết nối; AUTH xác thực tài khoản gửi. Cần cả hai khi provider yêu cầu authenticated submission.

**10. BASE64 có bảo vệ password SMTP hoặc body không?**

Không. Base64 là encoding, không phải encryption. STARTTLS/implicit TLS bảo vệ kết nối khi được cấu hình và xác minh đúng.

**11. Tại sao server trả 535 dù TLS thành công?**

535 thường liên quan credentials/quyền AUTH. TLS handshake và SMTP AUTH là hai bước độc lập.

**12. Vì sao OpenSSL verify thành công nhưng Java báo lỗi?**

Hai môi trường có thể dùng truststore và policy TLS khác nhau. Kiểm tra JDK, container, CA và hostname mà Java thực sự sử dụng.

**13. Có thể ép chỉ TLS 1.3 không?**

Có thể nếu provider/JDK hỗ trợ cấu hình đó, nhưng server cũng phải hỗ trợ. Không ép tùy tiện gây gián đoạn gửi; hãy áp dụng baseline và kiểm thử.

**14. Có nên retry khi handshake thất bại không?**

Tùy nguyên nhân. Lỗi mạng tạm thời có thể retry. Certificate hết hạn, hostname mismatch hoặc mode sai cần sửa, không retry mù.

**15. Timeout khi gửi SMTP có chắc chắn email chưa được gửi?**

Không. Nếu timeout sau DATA, server có thể đã chấp nhận message. Retry cần tính tới khả năng email bị gửi trùng.

**16. Spring Mail có API sendTls() riêng không?**

Thông thường không cần. Cấu hình TLS nằm trong JavaMail properties của transport. Service vẫn gọi JavaMailSender.send(...).

**17. SSL và TLS có phải luôn là hai tùy chọn bảo mật khác nhau trong cấu hình không?**

Tên property **ssl** là cách đặt tên lịch sử của thư viện. Trong triển khai hiện đại, nó thường cấu hình TLS qua Java SSL/TLS stack, không khuyến nghị sử dụng giao thức SSL cũ.

**18. DKIM/SPF/DMARC có chứng minh email đã được gửi qua TLS không?**

Không. Chúng giải quyết xác thực nguồn gửi và alignment của domain, không bảo đảm mã hóa toàn bộ đường truyền.

## 24. Quy trình triển khai TLS cho Spring Mail

Một quy trình thực tế:

1. **Chọn SMTP provider và endpoint**: xác định host, port và mode TLS từ tài liệu provider.
2. **Quyết định STARTTLS hay implicit TLS**: thường là 587/STARTTLS hoặc 465/implicit TLS.
3. **Yêu cầu kết nối bảo mật**: STARTTLS nên dùng enable + required nếu policy bắt buộc TLS; implicit TLS dùng ssl.enable.
4. **Bật hostname verification**: cấu hình ssl.checkserveridentity=true.
5. **Bảo đảm certificate hợp lệ**: kiểm tra SAN, trust chain, ngày hết hạn và truststore của JVM.
6. **Cấu hình AUTH an toàn**: secrets lấy từ kênh quản lý bí mật; không gửi credentials trên kết nối không đáp ứng policy.
7. **Đặt timeout hữu hạn**: connection/read/write timeout.
8. **Kiểm tra fail-closed**: server thiếu STARTTLS hoặc certificate sai phải bị từ chối.
9. **Kiểm tra lỗi AUTH riêng**: xác thực thất bại không được xử lý bằng cách tắt TLS.
10. **Theo dõi vận hành**: log có cấu trúc, cảnh báo, retry có điều kiện và xử lý kết quả không xác định.
11. **Bảo vệ các lớp ngoài TLS**: SPF/DKIM/DMARC, secret rotation, kiểm soát dữ liệu và authorization.
12. **Thử ở runtime thật**: JDK, container, host, port và truststore production có thể khác môi trường phát triển.

## 25. Ghi nhớ về TLS trong kết nối tới mail server

**TLS là nền tảng bảo vệ kết nối SMTP, không phải bảo mật email end-to-end.** Trong Spring Framework Mail, ứng dụng thường dùng **STARTTLS trên cổng 587** hoặc **implicit TLS trên cổng 465** theo tài liệu của provider. STARTTLS nâng cấp kết nối sau EHLO; implicit TLS thương lượng bảo mật ngay từ đầu. Cả hai cần xác minh certificate và hostname đúng để chống giả mạo server.

Với STARTTLS, **mail.smtp.starttls.enable=true** chỉ cho phép nâng cấp. Nếu policy bắt buộc mã hóa, hãy thêm **mail.smtp.starttls.required=true** để tránh fallback plaintext; đồng thời bật **mail.smtp.ssl.checkserveridentity=true**. Với implicit TLS, dùng **mail.smtp.ssl.enable=true** và hostname verification trên endpoint tương ứng. Không cấu hình chồng hai mode cho một server chỉ vì muốn tăng bảo mật.

Không dùng **mail.smtp.ssl.trust=***, tắt hostname verification hoặc bỏ TLS để che lỗi certificate hay AUTH. Phân biệt lỗi kết nối, handshake và credentials; đặt timeout, lưu trạng thái gửi, retry có điều kiện và thận trọng với timeout sau DATA vì kết quả SMTP có thể chưa xác định.

Cuối cùng, hãy phân biệt **kết nối SMTP được TLS bảo vệ**, **provider chấp nhận message**, **email được chuyển phát**, và **người nhận đã đọc thư**. Đây là các mốc độc lập. Cấu hình TLS đúng giúp bảo vệ đường truyền mà không đánh đồng nó với mọi yêu cầu an toàn và độ tin cậy của hệ thống email.
