# STARTTLS và nâng cấp kết nối trong phiên SMTP

Khi một ứng dụng Spring gửi email qua SMTP, dữ liệu trao đổi với máy chủ gửi thư có thể đi qua mạng nội bộ hoặc Internet. Kết nối SMTP truyền thống bắt đầu bằng các lệnh văn bản. Nếu truyền tài khoản đăng nhập hoặc nội dung thư trên một kết nối không được bảo vệ, người có khả năng quan sát lưu lượng mạng có thể đọc hoặc can thiệp vào dữ liệu.

**STARTTLS** là cơ chế cho phép hai đầu của **một kết nối SMTP đang hoạt động** chuyển từ giao tiếp SMTP thông thường sang giao tiếp được bảo vệ bằng **TLS (Transport Layer Security)**. Sau khi nâng cấp thành công, các lệnh SMTP tiếp theo và dữ liệu thư truyền qua kết nối đó sẽ được mã hóa theo phiên TLS.

Trong **Spring Framework Mail**, ứng dụng thường sử dụng `JavaMailSender` cùng thư viện Jakarta Mail để kết nối một SMTP server hoặc SMTP relay. Cấu hình STARTTLS giúp xác định cách ứng dụng bảo vệ chặng kết nối này. Cần hiểu rõ cách nâng cấp diễn ra, khi nào phải từ chối kết nối thiếu TLS và tại sao STARTTLS không đồng nghĩa với việc email được mã hóa từ đầu đến cuối.

## 1. STARTTLS giải quyết vấn đề gì?

Hãy hình dung ứng dụng cần gửi thư xác nhận tài khoản:

~~~mermaid
flowchart LR
    A["Ứng dụng Spring"] -->|"SMTP submission"| B["SMTP relay"]
    B -->|"SMTP giữa các máy chủ"| C["Máy chủ nhận"]
    C --> D["Hộp thư người nhận"]
~~~

Đây là **nhiều chặng truyền khác nhau**. Kết nối từ Spring đến SMTP relay có thể được bảo vệ bằng STARTTLS; kết nối từ relay đến máy chủ nhận là một phiên SMTP khác, có thể có hoặc không có TLS tùy cấu hình và chính sách của hai máy chủ.

Ba mục tiêu chính của TLS trên một chặng SMTP là:

- **Bảo mật nội dung trên đường truyền:** hạn chế bên quan sát mạng đọc được lệnh SMTP, nội dung email và thông tin xác thực được truyền sau khi phiên TLS được thiết lập.
- **Bảo vệ tính toàn vẹn:** giúp phát hiện việc thay đổi dữ liệu đang truyền trên kết nối TLS.
- **Xác thực máy chủ đích khi được cấu hình kiểm tra danh tính:** chứng chỉ TLS hợp lệ và kiểm tra hostname giúp giảm nguy cơ ứng dụng kết nối nhầm một máy chủ giả mạo.

STARTTLS không tự xác thực tài khoản email; đó là vai trò của cơ chế **SMTP AUTH**. Nó cũng không bảo đảm email sẽ đến Inbox, không bảo đảm mọi chặng chuyển tiếp sau đó được mã hóa và không xác thực danh tính người gửi theo SPF/DKIM/DMARC.

## 2. STARTTLS khác kết nối TLS ngay từ đầu như thế nào?

Có hai cách thiết lập kết nối SMTP được bảo vệ bằng TLS thường gặp:

| Cách kết nối | Thời điểm bắt đầu TLS | Cổng thường gặp | Đặc điểm |
| --- | --- | --- | --- |
| **STARTTLS (Explicit TLS)** | Bắt đầu bằng SMTP thông thường, gửi lệnh `STARTTLS` rồi mới thực hiện TLS handshake trên cùng kết nối TCP | **587** (submission), cũng gặp ở **25** khi các MTA chuyển thư | Cần máy chủ công bố và hỗ trợ lệnh `STARTTLS`. |
| **Implicit TLS** | TLS handshake diễn ra **ngay sau khi kết nối TCP được mở**, trước mọi lệnh SMTP | **465** (submissions) | Không cần lệnh `STARTTLS` để chuyển trạng thái trên kết nối này. |

Các cổng trên phản ánh quy ước phổ biến:

- **587:** dịch vụ **message submission**. Ứng dụng hoặc email client gửi thư cho SMTP relay, thường cần xác thực và có thể yêu cầu STARTTLS.
- **465:** dịch vụ submission qua **implicit TLS**; hai đầu bắt đầu TLS ngay khi kết nối.
- **25:** chủ yếu dành cho **SMTP giữa các máy chủ gửi/nhận**. STARTTLS trên cổng này thường được thương lượng theo chính sách của hạ tầng chuyển thư.

Không nên dựa vào số cổng để suy ra chắc chắn dịch vụ đã mã hóa. Khả năng và chính sách thực tế nằm trong cấu hình của máy chủ SMTP cùng yêu cầu bảo mật của ứng dụng.

> **Quy tắc nhớ:** STARTTLS nghĩa là “bắt đầu SMTP rồi nâng cấp sang TLS trên cùng kết nối”; implicit TLS nghĩa là “thiết lập TLS ngay từ byte đầu tiên”.

## 3. Một phiên SMTP được nâng cấp bằng STARTTLS diễn ra ra sao?

Để thấy vai trò của STARTTLS, hãy theo dõi quá trình một SMTP client kết nối tới `smtp.provider.example:587`. Đây là **phiên minh họa**; tên máy chủ, lời chào và khả năng quảng bá của máy chủ cụ thể sẽ khác nhau.

~~~text
[1] TCP connection tới smtp.provider.example:587

S: 220 smtp.provider.example ESMTP ready
C: EHLO app.example.org
S: 250-smtp.provider.example
S: 250-SIZE 26214400
S: 250-STARTTLS
S: 250 HELP

[2] Client yêu cầu nâng cấp

C: STARTTLS
S: 220 Ready to start TLS

[3] TLS handshake diễn ra trên cùng TCP connection
    (Không còn là các dòng lệnh SMTP văn bản thuần)
    - Client và server thống nhất phiên bản/cipher TLS
    - Server gửi chứng chỉ
    - Client kiểm tra chứng chỉ và danh tính máy chủ theo cấu hình
    - Hai bên thiết lập khóa phiên

[4] TLS handshake thành công; SMTP tiếp tục bên trong TLS

C: EHLO app.example.org
S: 250-smtp.provider.example
S: 250-AUTH PLAIN LOGIN
S: 250 SIZE 26214400

[5] Client xác thực và gửi thư bên trong TLS
    (Thông tin xác thực đã được lược bỏ khỏi bản minh họa)

C: AUTH ...
S: 235 2.7.0 Authentication successful
C: MAIL FROM:<notify@example.org>
S: 250 2.1.0 Sender OK
C: RCPT TO:<linh@example.net>
S: 250 2.1.5 Recipient OK
C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: From: notify@example.org
C: To: linh@example.net
C: Subject: Welcome
C:
C: Your account is ready.
C: .
S: 250 2.0.0 Message accepted
C: QUIT
S: 221 Bye
~~~

Ký hiệu `C:` là client và `S:` là server. Bản ghi trên dùng văn bản để giải thích thứ tự. Trong thực tế, sau khi TLS được thiết lập, công cụ bắt gói mạng bên ngoài kết nối chỉ thấy dữ liệu được mã hóa; muốn đọc nội dung lệnh phải có khả năng giải mã lưu lượng trong môi trường kiểm thử thích hợp.

### Giai đoạn A — Kết nối SMTP và tìm khả năng STARTTLS

Máy chủ gửi lời chào `220`. Client gửi `EHLO` để sử dụng Extended SMTP (ESMTP) và nhận danh sách khả năng của máy chủ. Nếu phản hồi có `250-STARTTLS`, máy chủ đang thông báo hỗ trợ nâng cấp.

**Quảng bá STARTTLS không phải là TLS đã được bật.** Ở thời điểm này, các lệnh và phản hồi SMTP vẫn là dữ liệu trước khi mã hóa. Các thuộc tính như địa chỉ máy chủ, phần lời chào và các khả năng công bố ban đầu có thể bị quan sát.

### Giai đoạn B — Client gửi lệnh STARTTLS

Client gửi:

~~~text
STARTTLS
~~~

Máy chủ trả về mã `220` khi sẵn sàng bắt đầu TLS. Từ thời điểm đó, hai đầu phải chuyển sang **TLS handshake** trên **chính kết nối TCP hiện có**. Không mở một cổng mới, không phát lệnh HTTP và không dùng một kết nối SMTP độc lập để thực hiện nâng cấp.

Nếu máy chủ không công bố STARTTLS, client phải xử lý theo chính sách bảo mật đã cấu hình. Nếu lệnh nâng cấp bị từ chối, kết nối không được coi là đã bảo vệ.

### Giai đoạn C — TLS handshake

Trong TLS handshake, client và server thương lượng các tham số của phiên TLS, máy chủ đưa ra chứng chỉ và client quyết định có tin tưởng máy chủ đó hay không. Trong cấu hình bảo mật thích hợp, client kiểm tra:

1. Chuỗi chứng chỉ được ký bởi tổ chức chứng thực (CA) đáng tin cậy, hoặc bởi nguồn tin cậy riêng đã được cấu hình.
2. Chứng chỉ chưa hết hạn và có hiệu lực sử dụng phù hợp.
3. Danh tính trong chứng chỉ khớp với tên máy chủ SMTP mà client muốn kết nối.
4. Phiên bản TLS và bộ mật mã được hai bên hỗ trợ và chính sách cho phép.

**Mã hóa mà bỏ qua xác thực danh tính máy chủ là chưa đủ để chống giả mạo máy chủ.** Một kẻ tấn công có thể tìm cách đặt thiết bị đứng giữa client và server nếu client chấp nhận mọi chứng chỉ hoặc không kiểm tra hostname.

### Giai đoạn D — SMTP trở lại sau TLS

Khi bắt tay TLS thành công, hai đầu **bỏ các thông tin khả năng SMTP đã ghi nhận trước nâng cấp**. Client gửi `EHLO` **lại lần nữa** bên trong kết nối TLS để lấy danh sách khả năng mới.

Việc này cần thiết vì máy chủ có thể chỉ quảng bá cơ chế `AUTH` hoặc một số khả năng nhạy cảm **sau khi kết nối đã được bảo vệ**. Client không được giả định rằng danh sách ESMTP trước và sau STARTTLS giống nhau.

Sau `EHLO` thứ hai, client có thể thực hiện xác thực (nếu dịch vụ yêu cầu) rồi gửi `MAIL FROM`, `RCPT TO`, `DATA` theo giao thức SMTP thông thường, nhưng các byte truyền qua kết nối TCP đã nằm trong phiên TLS.

### Luồng trạng thái tổng quát

~~~mermaid
stateDiagram-v2
    [*] --> TCP
    TCP --> PlainSMTP: Nhận banner 220
    PlainSMTP --> Capabilities: EHLO
    Capabilities --> TLSRequested: Có STARTTLS, client yêu cầu
    TLSRequested --> Handshake: Server trả 220
    Handshake --> SecureSMTP: TLS thành công
    SecureSMTP --> SecureCapabilities: EHLO lại
    SecureCapabilities --> Submission: AUTH (nếu cần), MAIL/RCPT/DATA
    Submission --> [*]: QUIT
    Capabilities --> Reject: Yêu cầu TLS nhưng server không hỗ trợ
    TLSRequested --> Reject: Server từ chối
    Handshake --> Reject: TLS handshake thất bại
    Reject --> [*]
~~~

Trên kết nối bắt buộc dùng TLS, khi chưa đạt trạng thái `SecureSMTP` thì **không tiếp tục gửi tài khoản hoặc dữ liệu thư qua kết nối plaintext**.

## 4. Opportunistic TLS và Required TLS khác nhau ra sao?

Đây là sự khác biệt quan trọng nhất khi cấu hình ứng dụng.

### 4.1. Opportunistic TLS — dùng TLS nếu máy chủ hỗ trợ

Client có thể yêu cầu STARTTLS khi nhìn thấy khả năng `STARTTLS`, nhưng **vẫn có thể tiếp tục SMTP không mã hóa nếu máy chủ không hỗ trợ**. Đây là chiến lược opportunistic TLS, thường được dùng trong vận chuyển email giữa các MTA để bảo đảm khả năng tương thích rộng.

Ưu điểm là có thể chuyển thư cho các máy chủ cũ chưa hỗ trợ TLS; nhược điểm là lưu lượng có thể đi dưới dạng không mã hóa. Nếu kẻ tấn công có khả năng can thiệp vào kết nối trước khi bật TLS, họ có thể tìm cách xóa khả năng `STARTTLS` khỏi phản hồi `EHLO` (một dạng **downgrade attack**).

Không nên mặc định opportunistic TLS đủ cho chặng **ứng dụng Spring → SMTP submission relay có sử dụng tài khoản**.

### 4.2. Required TLS — bắt buộc nâng cấp thành công

Với chính sách required TLS, client từ chối gửi tiếp nếu:

- SMTP server không quảng bá `STARTTLS`;
- máy chủ không chấp nhận lệnh `STARTTLS`;
- quá trình TLS handshake không thành công;
- chứng chỉ hoặc danh tính server không đạt yêu cầu xác thực đã cấu hình.

Cách này giúp tránh tình huống ứng dụng im lặng rơi về SMTP plaintext. Với một SMTP relay thuộc nhà cung cấp đáng tin cậy, yêu cầu TLS là lựa chọn thích hợp khi gửi email giao dịch có xác thực.

Cần phân biệt **“bắt buộc có TLS”** và **“kiểm tra danh tính server”**. Hai yêu cầu phải được cấu hình thích hợp để tránh trường hợp kết nối đã mã hóa nhưng vẫn tin một chứng chỉ hoặc hostname không hợp lệ.

| Chính sách | Khi server hỗ trợ TLS hợp lệ | Khi server không hỗ trợ STARTTLS | Khi handshake lỗi |
| --- | --- | --- | --- |
| Opportunistic STARTTLS | Nâng cấp rồi gửi | Có thể tiếp tục plaintext | Thường báo lỗi kết nối/nâng cấp; không mặc định coi đó là fallback an toàn |
| Required STARTTLS | Nâng cấp rồi gửi | Dừng với lỗi | Dừng với lỗi |
| Implicit TLS | Bắt tay TLS ngay khi kết nối | Không áp dụng lệnh STARTTLS | Dừng với lỗi |

**Không được hiểu “opportunistic” là mọi thất bại TLS đều được phép bỏ qua.** Hành vi cụ thể phụ thuộc SMTP client và loại lỗi; cần kiểm tra cấu hình thực tế. Chính sách an toàn cho ứng dụng có xác thực là làm cho yêu cầu TLS trở nên rõ ràng.

## 5. Cấu hình STARTTLS trong Spring Boot và JavaMailSender

Spring Framework Mail cung cấp `JavaMailSender` để gửi thư. Với Spring Boot và `spring-boot-starter-mail`, thư viện Jakarta Mail xử lý kết nối SMTP và lệnh STARTTLS theo các thuộc tính được cấu hình.

### 5.1. Phụ thuộc Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Nếu dự án Spring không sử dụng Spring Boot, có thể tự tạo bean `JavaMailSenderImpl`, khai báo Jakarta Mail và các thuộc tính SMTP tương đương.

### 5.2. Ví dụ ứng dụng dùng STARTTLS trên cổng 587

~~~properties
# SMTP submission relay thực tế do nhà cung cấp cấp
spring.mail.host=smtp.provider.example
spring.mail.port=587
spring.mail.protocol=smtp

# Lấy bí mật từ môi trường chạy, không lưu mật khẩu trong Git
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

# Xác thực và STARTTLS
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true

# Kiểm tra danh tính hostname trong chứng chỉ TLS
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true

# Thời gian chờ kết nối / đọc / ghi (mili giây)
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
~~~

Tên `smtp.provider.example` chỉ mang tính minh họa. Cần thay bằng máy chủ và cổng chính thức của nhà cung cấp SMTP, kiểm tra xem dịch vụ hỗ trợ STARTTLS và cơ chế xác thực nào.

Ý nghĩa các thuộc tính liên quan trực tiếp đến STARTTLS:

| Thuộc tính Jakarta Mail | Tác dụng |
| --- | --- |
| `mail.smtp.starttls.enable=true` | Cho phép client sử dụng lệnh STARTTLS khi server công bố hỗ trợ. Riêng thuộc tính này **không buộc mọi kết nối đều phải được mã hóa**. |
| `mail.smtp.starttls.required=true` | Yêu cầu STARTTLS khả dụng và nâng cấp thành công; nếu không, thao tác gửi phải thất bại. |
| `mail.smtp.ssl.checkserveridentity=true` | Bật kiểm tra danh tính hostname của máy chủ đối với TLS; tránh chỉ dựa vào việc chứng chỉ có chuỗi tin cậy. |
| `mail.smtp.auth=true` | Yêu cầu sử dụng SMTP AUTH. Nó không thay thế STARTTLS. |
| `mail.smtp.connectiontimeout` | Giới hạn thời gian thiết lập kết nối TCP. |
| `mail.smtp.timeout` | Giới hạn thời gian chờ đọc từ socket. |
| `mail.smtp.writetimeout` | Giới hạn thời gian ghi dữ liệu ra socket. |

Spring Boot đưa những giá trị sau `spring.mail.properties.` vào cấu hình Jakarta Mail. Vì vậy, tên thuộc tính bắt đầu bằng `mail.smtp.` cần được viết chính xác theo thư viện Jakarta Mail mà dự án sử dụng.

Thông thường, ứng dụng nên dùng kho chứng chỉ tin cậy của JVM hoặc truststore được quản lý đúng cách. **Tránh cấu hình `mail.smtp.ssl.trust=*` trong môi trường thật** vì điều đó có thể khiến client chấp nhận máy chủ mà không kiểm tra chuỗi tin cậy như mong muốn.

### 5.3. Ví dụ gửi email

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {
    private final JavaMailSender mailSender;

    public NotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotice(String from, String to) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(to);
        message.setSubject("Thông báo hệ thống");
        message.setText("Yêu cầu của bạn đã được tiếp nhận.");
        mailSender.send(message);
    }
}
~~~

Lớp `NotificationMailService` không tự phát lệnh `EHLO`, `STARTTLS` hay thực hiện TLS handshake. **Jakarta Mail xử lý giao thức dựa trên cấu hình**, còn mã nghiệp vụ gọi `JavaMailSender.send(...)`.

Nếu STARTTLS là bắt buộc và quá trình nâng cấp không thành công, lời gọi gửi có thể ném ngoại lệ thuộc nhóm `MailException` của Spring (nguyên nhân gốc có thể là lỗi từ Jakarta Mail hoặc SSL/TLS). Ứng dụng cần ghi nhận lỗi thích hợp và quyết định có thử gửi lại hay thông báo sự cố, thay vì coi đây là gửi thành công.

## 6. Khi nhà cung cấp yêu cầu implicit TLS cổng 465

Nếu SMTP relay yêu cầu TLS ngay từ lúc kết nối, cấu hình thường khác:

~~~properties
spring.mail.host=smtp.provider.example
spring.mail.port=465
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.ssl.enable=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
~~~

Trong trường hợp implicit TLS, `mail.smtp.ssl.enable=true` yêu cầu tạo kết nối SMTP bảo vệ bằng SSL/TLS **ngay từ đầu**. Không cần bật STARTTLS để “nâng cấp” một kết nối vốn đã nằm trong TLS.

Một lỗi cấu hình thường gặp là:

- Kết nối cổng **587** nhưng bật `mail.smtp.ssl.enable=true` như thể đó là cổng implicit TLS.
- Kết nối cổng **465** nhưng chỉ bật `mail.smtp.starttls.enable=true` như thể máy chủ đợi phiên SMTP plaintext ban đầu.

Hai kiểu này có thể làm hai bên chờ các dữ liệu giao thức khác nhau, dẫn đến timeout hoặc handshake lỗi. Hãy dùng cấu hình đúng với tài liệu của SMTP provider. Cổng tùy chỉnh vẫn có thể hoạt động nếu hai đầu được thiết lập tương ứng.

## 7. Mã lệnh EHLO và thay đổi khả năng sau STARTTLS

SMTP mở rộng sử dụng `EHLO` để server công bố các khả năng đang được hỗ trợ. Danh sách khả năng **có thể thay đổi sau TLS**.

Ví dụ:

~~~text
# Trước STARTTLS
250-smtp.provider.example
250-STARTTLS
250 SIZE 26214400

# Sau TLS và EHLO lại
250-smtp.provider.example
250-AUTH PLAIN LOGIN
250 SIZE 26214400
~~~

Ở đây, `AUTH` chỉ xuất hiện sau khi client hoàn thành handshake. Máy chủ làm vậy để tránh khuyến khích client gửi thông tin xác thực qua một kênh chưa mã hóa.

Các điểm cần hiểu:

1. `EHLO` đầu tiên xác định có thể yêu cầu STARTTLS hay không.
2. Phản hồi `220` cho `STARTTLS` bắt đầu **TLS handshake**.
3. Sau khi TLS thành công, **không dùng lại danh sách ESMTP capability cũ**.
4. `EHLO` thứ hai cung cấp khả năng hiện hành cho phiên SMTP đã bảo vệ.
5. Sau đó mới đến `AUTH` và các lệnh nộp thư theo chính sách server.

Một số server có thể công bố `AUTH` cả trước TLS nhưng từ chối thực hiện cho tới khi TLS được bật. Client vẫn cần tuân thủ chính sách không gửi thông tin đăng nhập qua plaintext.

## 8. Các lỗi thường gặp khi nâng cấp STARTTLS

Các lỗi quan sát được có thể xuất hiện ở nhiều bước. Cách xác định nguyên nhân nên dựa trên **thời điểm thất bại trong phiên SMTP**, không chỉ dựa vào thông điệp “gửi mail thất bại” ở lớp nghiệp vụ.

| Hiện tượng | Khả năng nguyên nhân | Hướng kiểm tra |
| --- | --- | --- |
| `STARTTLS is required but host does not support STARTTLS` hoặc thông báo tương tự | Server không công bố STARTTLS; ứng dụng kết nối nhầm cổng, nhầm dịch vụ hoặc server cấu hình thiếu | Xác nhận hostname/cổng, kiểm tra khả năng `EHLO`, đối chiếu tài liệu provider |
| `454 TLS not available due to temporary reason` | Server tạm thời không cung cấp được TLS; cấu hình hoặc tài nguyên server có vấn đề | Kiểm tra trạng thái SMTP server, chứng chỉ và log server |
| `SSLHandshakeException` | Không thống nhất được phiên TLS, chứng chỉ không tin cậy hoặc bị lỗi handshake | Xem nguyên nhân trong stack trace, TLS version/cipher, truststore |
| Chứng chỉ không khớp tên máy chủ | Kết nối qua hostname khác với Subject Alternative Name (SAN) của chứng chỉ; thiết bị trung gian thay thế chứng chỉ | Dùng đúng SMTP hostname; kiểm tra chuỗi chứng chỉ và cấu hình hostname verification |
| Kết nối tới 465/587 bị timeout | Sai kiểu TLS so với cổng, bị chặn bởi firewall, hoặc server không phản hồi | Đối chiếu implicit TLS và STARTTLS, kiểm tra mạng và cổng |
| Đã bắt tay TLS nhưng `AUTH` bị từ chối | Sai tài khoản, sai cơ chế xác thực hoặc chính sách provider | Kiểm tra credential, phương thức AUTH và quyền gửi |
| `530 Must issue a STARTTLS command first` hoặc thông báo tương tự | Máy chủ yêu cầu nâng cấp trước khi xác thực hoặc gửi thư | Cấu hình STARTTLS thích hợp và bắt buộc TLS |

Các mã SMTP chỉ mang tính ví dụ: phản hồi cụ thể và thông điệp lỗi khác nhau giữa các máy chủ. Sau lỗi mạng hoặc lỗi TLS, **không mặc định thử gửi lại bằng kết nối plaintext** để “chạy cho được”, đặc biệt khi nội dung hoặc tài khoản có tính nhạy cảm.

### Khi nào nên thử lại?

- Nếu gặp lỗi tạm thời từ hạ tầng, hàng đợi gửi có thể thử lại sau với giới hạn thời gian và số lần hợp lý.
- Nếu gặp sai hostname, chứng chỉ không tin cậy hoặc cấu hình sai cổng, thử lại liên tục thường không khắc phục được; cần sửa cấu hình hoặc hạ tầng.
- Nếu lỗi xảy ra sau khi máy chủ nhận đã chấp nhận `DATA` nhưng phản hồi cuối không đến ứng dụng, client có thể **không biết thư đã được nhận hay chưa**. Cơ chế thử lại cần tính đến khả năng gửi trùng.

Việc phân biệt lỗi tạm thời và lỗi cấu hình là trách nhiệm của hệ thống gửi/hàng đợi, không phải tính năng mà STARTTLS tự cung cấp.

## 9. Dùng công cụ để quan sát quá trình nâng cấp

Khi cần tìm nguyên nhân kết nối STARTTLS thất bại, có thể dùng `openssl s_client` trên máy có OpenSSL. Ví dụ cú pháp:

~~~bash
openssl s_client -starttls smtp \
  -connect smtp.provider.example:587 \
  -servername smtp.provider.example \
  -verify_hostname smtp.provider.example
~~~

Lệnh yêu cầu nâng cấp SMTP bằng STARTTLS và hiển thị thông tin TLS/chứng chỉ sau khi kết nối. Tên máy chủ minh họa phải được thay bằng SMTP hostname thật. Tùy phiên bản OpenSSL, các tùy chọn xác thực chuỗi và cách trả mã lỗi có thể khác nhau; cần xem **kết quả xác minh chứng chỉ và exit status**, không chỉ quan sát việc socket đã kết nối.

Có thể dùng `swaks` (nếu cài trong môi trường thử nghiệm) để kiểm tra SMTP ở mức giao thức:

~~~bash
swaks --server smtp.provider.example --port 587 \
  --tls --to test-recipient@example.net \
  --from test-sender@example.org
~~~

Lệnh này minh họa cách yêu cầu STARTTLS; muốn gửi thật có thể cần khai báo xác thực SMTP và chính sách gửi phù hợp. Không nhập mật khẩu vào lệnh nếu nó có nguy cơ bị lưu trong lịch sử shell hoặc lộ qua danh sách tiến trình.

### Quan sát thông tin debug từ Jakarta Mail

Ở môi trường phát triển có kiểm soát, Jakarta Mail hỗ trợ debug phiên SMTP bằng thuộc tính:

~~~properties
spring.mail.properties.mail.debug=true
~~~

Debug có thể hỗ trợ quan sát `EHLO`, việc hỗ trợ `STARTTLS`, quá trình kết nối và các lỗi giao thức. **Không bật debug tràn lan trên Production**, vì log phiên SMTP có thể chứa địa chỉ email, metadata hoặc thông tin nhạy cảm. Khi cần xử lý sự cố, phải có quy định giới hạn thời gian bật log và lọc dữ liệu phù hợp. Đừng cố chép thông tin xác thực hoặc nội dung thư thật vào báo cáo debug.

## 10. TLS trên một chặng không phải mã hóa email đầu cuối

Giả sử ứng dụng Spring dùng STARTTLS với SMTP relay và TLS handshake thành công:

~~~mermaid
flowchart LR
    A["Ứng dụng Spring"] -->|"TLS #1"| B["SMTP relay"]
    B -->|"TLS #2 nếu được thương lượng"| C["Máy chủ nhận"]
    C -->|"Lưu trữ/chuyển tiếp nội bộ"| D["Hộp thư"]
~~~

Những điều có thể khẳng định là **chặng A → B** đã được TLS bảo vệ trong phiên SMTP đó, với mức tin cậy phụ thuộc kiểm tra chứng chỉ/danh tính máy chủ. Không thể từ kết quả này suy ra:

- Chặng B → C chắc chắn có TLS; đó là phiên và chính sách kết nối riêng.
- Email được mã hóa khi nằm trong hàng đợi, cơ sở dữ liệu hoặc hộp thư của các nhà cung cấp.
- Người trung gian có quyền truy cập hệ thống mail server không thể xem nội dung email.
- Email không thể bị giả mạo người gửi, bị spam filter từ chối hoặc bị chuyển vào thư mục Junk.

Nếu cần **mã hóa nội dung từ người gửi đến người nhận sao cho máy chủ trung gian không đọc được**, cần xem các cơ chế khác như S/MIME hoặc OpenPGP, cùng quy trình quản lý khóa tương ứng. STARTTLS bảo vệ **kênh truyền giữa hai điểm kết nối SMTP**, không tạo bảo mật nội dung đầu cuối.

### STARTTLS của MTA và phòng ngừa downgrade

Với chặng **MTA → MTA trên cổng 25**, việc chỉ dựa vào danh sách `STARTTLS` công bố ở kết nối ban đầu có thể gặp nguy cơ downgrade nếu không có chính sách bảo vệ bổ sung. Những cơ chế như **MTA-STS** hoặc **DANE for SMTP** (gắn với DNSSEC) có thể giúp tăng độ tin cậy của việc yêu cầu TLS và xác thực máy chủ chuyển thư, tùy mức triển khai của các miền.

Đây là mảng quản trị hạ tầng email khác với cấu hình gửi thư từ Spring tới relay cố định. Ứng dụng Spring nên bắt đầu bằng chính sách rõ ràng cho **SMTP submission của mình**: yêu cầu STARTTLS hoặc implicit TLS đúng cách, kiểm tra danh tính server và quản lý thông tin xác thực an toàn.

## 11. Một số câu hỏi thực tế để tự suy luận

**Tình huống 1:** Ứng dụng đã bật `mail.smtp.starttls.enable=true`. SMTP server không quảng bá STARTTLS. Có chắc client sẽ từ chối gửi plaintext không?

**Không.** Chỉ `enable=true` cho phép sử dụng STARTTLS khi server có khả năng. Nếu ứng dụng muốn chắc chắn phải có TLS, hãy cấu hình `mail.smtp.starttls.required=true` và kiểm tra xác thực server thích hợp.

**Tình huống 2:** SMTP client gửi `EHLO`, sau đó `STARTTLS`, handshake TLS thành công. Có thể dùng lại danh sách capability trước TLS để gửi `AUTH` không?

**Không.** Sau khi nâng cấp, cần gửi `EHLO` lại và sử dụng danh sách khả năng mới.

**Tình huống 3:** Nhà cung cấp yêu cầu cổng 465 implicit TLS. Có nên dùng `spring.mail.port=465` cùng `mail.smtp.starttls.enable=true` mà không bật `mail.smtp.ssl.enable=true` không?

**Không.** Cần dùng chế độ TLS ngay từ đầu tương ứng với máy chủ 465; STARTTLS là một cơ chế nâng cấp trên kết nối SMTP ban đầu.

**Tình huống 4:** Spring gửi thành công qua relay và có TLS. Có thể kết luận máy chủ của người nhận đã nhận được thư qua TLS không?

**Không.** Kết quả chỉ liên quan đến bước gửi của ứng dụng đến relay. Mỗi lần chuyển tiếp tiếp theo có chính sách TLS, kết nối và trạng thái riêng.

**Tình huống 5:** TLS handshake thành công nhưng chứng chỉ không khớp SMTP hostname. Có thể bỏ qua kiểm tra hostname để gửi thư cho nhanh không?

**Không nên.** Cần dùng đúng hostname, xác minh chứng chỉ hoặc sửa cấu hình truststore/server. Bỏ qua xác thực danh tính làm suy giảm bảo vệ trước máy chủ giả mạo.

## 12. Mô hình ghi nhớ

Trong quy trình gửi thư qua Spring, hãy tách ba việc:

1. **Spring Framework Mail và Jakarta Mail:** tạo thông điệp, kết nối SMTP theo cấu hình, yêu cầu STARTTLS và xử lý lỗi kết nối.
2. **SMTP và STARTTLS:** máy chủ công bố khả năng qua `EHLO`, client gửi `STARTTLS`, hai bên thực hiện TLS handshake, rồi tiếp tục SMTP sau `EHLO` mới.
3. **Chính sách và hạ tầng email:** quyết định có bắt buộc TLS hay không, kiểm tra chứng chỉ, xác thực tài khoản, chuyển tiếp nhiều chặng, xử lý thư lỗi và theo dõi trạng thái chuyển phát.

Cốt lõi của STARTTLS là **nâng cấp bảo mật cho một kết nối SMTP đang tồn tại**. Với ứng dụng Spring gửi thư qua SMTP submission, hãy xác định rõ **TLS là bắt buộc hay tùy chọn**, cấu hình đúng kiểu kết nối của nhà cung cấp và kiểm tra danh tính máy chủ. Khi đã hiểu các trạng thái trước/sau `STARTTLS`, bạn sẽ dễ giải thích vì sao một email gửi được, thất bại khi handshake, hoặc bị từ chối xác thực ngay cả khi TCP đã kết nối thành công.

