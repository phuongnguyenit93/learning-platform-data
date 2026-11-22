# Phiên SMTP từ kết nối đến đóng phiên

Khi một ứng dụng Spring gọi `JavaMailSender.send(...)`, lập trình viên thường chỉ thấy thao tác “gửi email”. Ở tầng mạng, quá trình đó gồm nhiều bước có thứ tự: mở kết nối, nhận lời chào SMTP, thỏa thuận khả năng của máy chủ, thiết lập TLS, xác thực (nếu cần), khai báo người gửi và người nhận, truyền nội dung thư, nhận kết quả rồi đóng kết nối.

Hiểu **vòng đời phiên SMTP** giúp chẩn đoán lỗi chính xác: lỗi kết nối khác lỗi đăng nhập, lỗi người nhận khác lỗi nội dung, và phản hồi “đã tiếp nhận” hoàn toàn khác thông báo “đã đến Inbox”.

## 1. SMTP hoạt động ở đâu trong Spring Framework Mail?

**SMTP (Simple Mail Transfer Protocol)** là giao thức gửi và chuyển tiếp thư điện tử. Trong một ứng dụng Spring, luồng gửi điển hình:

```text
Ứng dụng Spring
    |
    | JavaMailSender.send(...)
    v
JavaMailSenderImpl
    |
    | Jakarta Mail / SMTP Transport
    v
SMTP submission server hoặc SMTP relay
    |
    | hàng đợi và chuyển tiếp theo chính sách máy chủ
    v
Hạ tầng nhận email -> hộp thư của người nhận
```

Ứng dụng thông thường kết nối đến **SMTP host đã cấu hình**, chẳng hạn `smtp.example.com`. Nó không cần tự tra cứu bản ghi MX cho từng địa chỉ người nhận khi gửi qua một SMTP relay. Việc định tuyến tiếp theo do hạ tầng máy chủ thực hiện.

Ba khái niệm dễ bị nhầm:

| Khái niệm | Ý nghĩa |
|---|---|
| **Phiên SMTP** | Cuộc trao đổi giao thức qua một kết nối mạng giữa SMTP client và SMTP server, từ khi kết nối được thiết lập đến khi đóng. |
| **Giao dịch thư (mail transaction)** | Một đơn vị gửi gồm `MAIL FROM`, một hoặc nhiều `RCPT TO` và `DATA`. Một phiên SMTP có thể xử lý nhiều giao dịch thư. |
| **`jakarta.mail.Session`** | Đối tượng cấu hình của Jakarta Mail, chứa các properties và tài nguyên; **không phải** một socket TCP hay phiên SMTP đang mở. |

Trong Spring, `JavaMailSenderImpl` và Jakarta Mail đảm nhiệm phần lớn lệnh SMTP. Tuy nhiên, kết quả của các lệnh quyết định liệu email có được máy chủ tiếp nhận hay không.

## 2. Chọn cổng SMTP và cách thiết lập TLS

| Cổng | Trường hợp thường gặp | Thời điểm thiết lập TLS |
|---|---|---|
| **587** | Ứng dụng gửi thư đến máy chủ submission | Kết nối TCP trước, sau đó sử dụng `STARTTLS` để nâng cấp sang TLS. |
| **465** | Submission qua implicit TLS | TLS handshake xảy ra ngay sau TCP connect, trước lời chào SMTP `220`. |
| **25** | Relay giữa các máy chủ email hoặc hạ tầng nội bộ | Có thể hỗ trợ STARTTLS; không phải cổng mặc định nên chọn cho ứng dụng gửi email người dùng. |

Một số nhà cung cấp sử dụng cổng riêng. Luôn đối chiếu **host, cổng, phương thức mã hóa và cơ chế xác thực** với tài liệu của dịch vụ thực tế.

**STARTTLS (thường ở cổng 587):**

```text
TCP connect -> SMTP 220 -> EHLO -> STARTTLS
            -> TLS handshake -> EHLO lần hai -> AUTH / gửi thư
```

**Implicit TLS (thường ở cổng 465):**

```text
TCP connect -> TLS handshake -> SMTP 220
            -> EHLO -> AUTH / gửi thư
```

Điểm khác nhau chính là TLS được bắt đầu **trước** hay **sau** lời chào SMTP. Với STARTTLS, sau khi thương lượng TLS thành công, client phải gửi lại `EHLO` để khám phá các extension khả dụng trên kết nối đã mã hóa. Nếu chính sách yêu cầu TLS mà việc nâng cấp không thành công, client phải dừng gửi.

## 3. Tổng quan trình tự một phiên SMTP

```text
SMTP client (Spring/Jakarta Mail)             SMTP server
              |                                   |
              |---------- TCP connect ----------->|
              |<---------- 220 greeting ----------|
              |-------------- EHLO -------------->|
              |<--------- 250 extensions ---------|
              |                                   |
              |----------- STARTTLS ------------->|  (nếu dùng)
              |<------------- 220 ----------------|
              |<========== TLS handshake ========>|
              |-------------- EHLO -------------->|
              |<--------- 250 extensions ---------|
              |                                   |
              |------------- AUTH --------------->|  (nếu cần)
              |<------------- 235 ----------------|
              |----------- MAIL FROM ------------>|
              |<------------- 250 ----------------|
              |------------ RCPT TO ------------->|
              |<-------- 250 hoặc lỗi ------------|
              |-------------- DATA -------------->|
              |<------------- 354 ----------------|
              |------ Headers + dòng trống ------>|
              |------------ Body ---------------->|
              |------- <CRLF>.<CRLF> ------------>|
              |<----- 250 đã tiếp nhận / lỗi ------|
              |                                   |
              |-------------- QUIT -------------->|
              |<------------- 221 ----------------|
              |--------- TCP/TLS close ---------->|
```

Đây là luồng gửi thành công có STARTTLS và AUTH. Hai bước đó phụ thuộc cấu hình. Nếu kết nối lỗi hoặc máy chủ đóng phiên giữa chừng, có thể không có `QUIT` và `221`.

## 4. Từng giai đoạn từ kết nối tới đóng phiên

### 4.1. Mở kết nối TCP và nhận lời chào `220`

Client mở socket tới SMTP host/cổng. Với implicit TLS, TLS handshake diễn ra ngay lúc này. Khi máy chủ SMTP sẵn sàng, nó gửi một dòng lời chào:

```text
S: 220 smtp.example.com ESMTP service ready
```

Trong các bản ghi minh họa, `C:` là client, `S:` là server. Các tiền tố này giúp đọc hội thoại và **không được gửi thật** trên kết nối.

Mã **220** báo SMTP server sẵn sàng. Nếu thất bại ở giai đoạn này, kiểm tra DNS của host, cổng, tường lửa, mạng, timeout kết nối và thiết lập TLS của cổng. TCP kết nối được không đồng nghĩa tài khoản đã có quyền gửi thư.

### 4.2. `EHLO` và khả năng của máy chủ

Client gửi `EHLO` để tự giới thiệu và yêu cầu danh sách extension SMTP:

```text
C: EHLO app.example.com
S: 250-smtp.example.com
S: 250-STARTTLS
S: 250-SIZE 10485760
S: 250 AUTH PLAIN LOGIN
```

`EHLO` thuộc Extended SMTP (ESMTP). Trong phản hồi nhiều dòng, `250-` nghĩa là còn dòng tiếp theo, `250 ` (dấu cách) đánh dấu dòng cuối.

| Extension | Ý nghĩa thực tiễn |
|---|---|
| `STARTTLS` | Máy chủ hỗ trợ nâng cấp từ phiên SMTP hiện tại sang TLS. |
| `AUTH PLAIN LOGIN` | Công bố các cơ chế xác thực mà máy chủ hỗ trợ tại thời điểm đó. |
| `SIZE 10485760` | Máy chủ công bố giới hạn kích thước thông điệp, tính bằng byte. |
| `8BITMIME` | Hỗ trợ truyền nội dung 8-bit theo extension tương ứng. |
| `SMTPUTF8` | Hỗ trợ địa chỉ/header quốc tế hóa theo quy tắc SMTPUTF8. |
| `PIPELINING` | Cho phép tối ưu việc phát một số lệnh mà không chờ từng phản hồi, nếu client tuân thủ extension. |

Không được giả định server nào cũng có các extension giống nhau. Chỉ dùng tính năng phù hợp với danh sách được công bố và chính sách ứng dụng.

### 4.3. `STARTTLS`: nâng cấp bảo mật

Trên cổng 587, khi server công bố `STARTTLS`, client có thể yêu cầu nâng cấp:

```text
C: STARTTLS
S: 220 Ready to start TLS
[TLS handshake thành công]
C: EHLO app.example.com
S: 250-smtp.example.com
S: 250-AUTH PLAIN LOGIN
S: 250 SIZE 10485760
```

Các lệnh sau khi handshake thành công sẽ đi qua kết nối được mã hóa. **Phải gửi lại `EHLO`** vì tập extension có thể thay đổi, ví dụ `AUTH` chỉ được công bố sau khi bật TLS.

Thiết lập STARTTLS theo chế độ “nếu có thì dùng” khác với chế độ “bắt buộc phải dùng”. Với ứng dụng cần bảo mật credential, nên yêu cầu TLS thay vì cho phép gửi xuống kết nối không mã hóa khi server không hỗ trợ.

Trên cổng 465, không có lệnh `STARTTLS` trong hội thoại; TLS đã được thiết lập trước `220`.

### 4.4. `AUTH`: xác thực tài khoản gửi

Nhiều SMTP submission server yêu cầu client xác thực:

```text
C: AUTH PLAIN <credentials-redacted>
S: 235 2.7.0 Authentication successful
```

Chuỗi trong ngoặc là placeholder, không phải lệnh xác thực hợp lệ. Trong cơ chế `PLAIN`, dữ liệu xác thực được biểu diễn bằng Base64; **Base64 không phải cơ chế mã hóa bảo mật**. Cần sử dụng TLS và bảo quản credential như bí mật.

Các mã phản hồi thường thấy:

- **235**: xác thực thành công.
- **535**: xác thực bị từ chối; kiểm tra tài khoản, mật khẩu/token và chính sách xác thực.
- **454**: lỗi xác thực tạm thời; xử lý theo chính sách retry có giới hạn.

SMTP relay nội bộ đôi khi cấp quyền theo mạng hoặc IP và không yêu cầu `AUTH`. Client cần tuân thủ cơ chế được máy chủ cho phép, không mặc định mọi SMTP server đều dùng tên đăng nhập và mật khẩu.

### 4.5. `MAIL FROM`: bắt đầu giao dịch và khai báo người gửi

Sau khi sẵn sàng gửi, client bắt đầu một giao dịch thư bằng lệnh:

```text
C: MAIL FROM:<bounce@example.com>
S: 250 2.1.0 Sender OK
```

`MAIL FROM` là địa chỉ người gửi trong **phong bì SMTP (envelope sender/reverse-path)**, dùng để xử lý đường trả lỗi (bounce). Nó có thể khác với header `From:` mà người nhận nhìn thấy. Máy chủ có thể từ chối ở bước này vì sender không hợp lệ, tài khoản không có quyền dùng địa chỉ hoặc chính sách chống lạm dụng.

Một số thông điệp đặc biệt như thông báo lỗi giao hàng có thể dùng reverse-path rỗng (`MAIL FROM:<>`) để tránh vòng lặp bounce. Ứng dụng gửi email giao dịch thông thường không cần tự thay đổi giá trị này nếu không có yêu cầu rõ ràng.

### 4.6. `RCPT TO`: khai báo từng người nhận

Mỗi người nhận trong phong bì có một lệnh riêng:

```text
C: RCPT TO:<alice@example.net>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<bob@example.org>
S: 250 2.1.5 Recipient OK
```

Máy chủ phản hồi **cho từng địa chỉ**. Một người có thể được chấp nhận và người khác bị từ chối:

```text
C: RCPT TO:<alice@example.net>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<unknown@example.org>
S: 550 5.1.1 User unknown
```

Không nên diễn giải một `250` cho Alice thành tất cả người nhận đều hợp lệ. Việc client tiếp tục gửi tới những địa chỉ đã được chấp nhận hay hủy cả lần gửi phụ thuộc thư viện, cấu hình và tình trạng giao dịch. Nếu tất cả địa chỉ đều bị từ chối, client không có người nhận hợp lệ để chuyển sang truyền dữ liệu.

### 4.7. `DATA`: truyền header và nội dung

Sau khi máy chủ chấp nhận ít nhất một người nhận, client gửi `DATA`:

```text
C: DATA
S: 354 End data with <CRLF>.<CRLF>
```

Mã **354** nghĩa là máy chủ sẵn sàng nhận dữ liệu. Client truyền **headers**, một **dòng trống**, rồi **body**. Ví dụ chỉ mang tính minh họa:

```text
C: From: "He thong" <no-reply@example.com>
C: To: alice@example.net
C: Subject: Xac nhan dang ky
C: MIME-Version: 1.0
C: Content-Type: text/plain; charset=UTF-8
C:
C: Xin chao Alice,
C: Tai khoan da duoc tao.
C: .
```

Trên đường truyền, dấu kết thúc dữ liệu là **`<CRLF>.<CRLF>`**. Nếu một dòng của nội dung bắt đầu bằng dấu chấm, client phải dùng cơ chế **dot-stuffing**: thêm dấu chấm để không bị hiểu nhầm là kết thúc `DATA`. Jakarta Mail xử lý phần giao thức này.

Sau khi nhận toàn bộ nội dung, máy chủ có thể trả:

```text
S: 250 2.0.0 Queued as ABC123
```

Điều này thường có nghĩa **SMTP server đã nhận trách nhiệm xử lý thông điệp** hoặc đưa thông điệp vào hàng đợi. Nó **không bảo đảm** thư đã đến mailbox cuối cùng, vào Inbox hoặc được người nhận đọc.

Email HTML, tệp đính kèm và nội dung có nhiều phần (MIME multipart) thay đổi cấu trúc thông điệp sau `DATA`; các lệnh điều khiển `MAIL FROM` → `RCPT TO` → `DATA` vẫn giữ nguyên về nguyên tắc.

### 4.8. Giao dịch khác hoặc `QUIT` để kết thúc

Sau một giao dịch thư hoàn tất, client có thể bắt đầu **giao dịch mới trên cùng kết nối** bằng `MAIL FROM` nếu cần và server vẫn duy trì phiên. Khi không còn công việc:

```text
C: QUIT
S: 221 2.0.0 Bye
[Đóng kết nối TCP/TLS]
```

`QUIT` kết thúc phiên một cách có trật tự; `221` xác nhận phía máy chủ chuẩn bị đóng. Với lỗi mạng, timeout hoặc server ngắt kết nối, client có thể không gửi được `QUIT` hoặc không nhận được `221`.

## 5. Ví dụ hội thoại SMTP hoàn chỉnh trên cổng 587

Hội thoại bên dưới dùng địa chỉ giả và đã ẩn dữ liệu AUTH. Chú thích trong dấu ngoặc vuông không phải lệnh SMTP thực:

```text
[TCP connect smtp.example.com:587]
S: 220 smtp.example.com ESMTP ready

C: EHLO app.example.com
S: 250-smtp.example.com
S: 250-STARTTLS
S: 250 SIZE 10485760

C: STARTTLS
S: 220 Ready to start TLS
[TLS handshake successful]

C: EHLO app.example.com
S: 250-smtp.example.com
S: 250-AUTH PLAIN LOGIN
S: 250 SIZE 10485760

C: AUTH PLAIN <redacted>
S: 235 2.7.0 Authentication successful

C: MAIL FROM:<no-reply@example.com>
S: 250 2.1.0 OK

C: RCPT TO:<alice@example.net>
S: 250 2.1.5 OK

C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: From: no-reply@example.com
C: To: alice@example.net
C: Subject: Welcome
C:
C: Hello, Alice!
C: .
S: 250 2.0.0 Message queued as ABC123

C: QUIT
S: 221 2.0.0 Closing connection
[TCP/TLS close]
```

Các câu chữ và enhanced status code (`2.0.0`, `2.1.5`, v.v.) khác nhau tùy nhà cung cấp. Phản hồi SMTP là kết quả của **từng bước**, vì vậy cùng một mã `250` xuất hiện tại nhiều vị trí nhưng có ý nghĩa cụ thể theo lệnh vừa gửi.

## 6. Envelope và message header là hai phần khác nhau

Phong bì SMTP được truyền qua các lệnh:

```text
MAIL FROM:<bounce@example.com>
RCPT TO:<alice@example.net>
RCPT TO:<audit@example.org>
```

Header của email lại nằm **bên trong `DATA`**:

```text
From: "Shop" <sales@example.com>
To: alice@example.net
Subject: Your order

...noi dung...
```

Vì vậy:

- `MAIL FROM` có thể khác `From:`. Điều này thường liên quan đến địa chỉ nhận bounce, cấu hình sender và chính sách của dịch vụ gửi.
- `RCPT TO` mô tả người nhận thực sự ở lớp vận chuyển; header `To:` và `Cc:` mô tả người nhận hiển thị.
- Người nhận **Bcc** có thể có trong phong bì nhưng không xuất hiện trong header `To:` hay `Cc:` của thư được gửi.

Khi phân tích log SMTP hoặc lỗi “sender address rejected”, cần biết lỗi thuộc **phong bì** hay nội dung/header. Việc sửa `From:` hiển thị không phải lúc nào cũng làm thay đổi `MAIL FROM` thực tế.

## 7. Spring Mail thực hiện các bước trên như thế nào?

Với Spring Boot, dependency `spring-boot-starter-mail` và cấu hình `spring.mail.*` thường đủ để Boot tạo `JavaMailSender` dùng Jakarta Mail:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

Trong ứng dụng Spring Framework không dùng Boot, cần tự tạo và cấu hình `JavaMailSenderImpl` cùng thư viện mail phù hợp.

### 7.1. Cấu hình SMTP 587 với STARTTLS

`application.yml`:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

| Property Jakarta Mail | Tác dụng |
|---|---|
| `mail.smtp.auth=true` | Bật cơ chế xác thực SMTP. |
| `mail.smtp.starttls.enable=true` | Cho phép dùng STARTTLS nếu server hỗ trợ. |
| `mail.smtp.starttls.required=true` | Yêu cầu STARTTLS phải thực hiện thành công. |
| `mail.smtp.connectiontimeout` | Thời gian tối đa chờ tạo kết nối. |
| `mail.smtp.timeout` | Thời gian tối đa chờ đọc dữ liệu/phản hồi từ socket. |
| `mail.smtp.writetimeout` | Thời gian tối đa cho thao tác ghi socket. |

Ba timeout trong ví dụ dùng đơn vị **mili giây**. Cấu hình timeout giúp thao tác gửi không chờ vô hạn khi mạng hoặc server bị treo. Giá trị phù hợp phụ thuộc môi trường triển khai.

`SMTP_USERNAME` và `SMTP_PASSWORD` được cấp từ biến môi trường, secret store hoặc cấu hình triển khai an toàn; không ghi giá trị thật vào Git.

### 7.2. Cấu hình implicit TLS ở cổng 465

Nếu nhà cung cấp yêu cầu TLS ngay từ khi mở kết nối:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

`mail.smtp.ssl.enable=true` sử dụng TLS từ đầu kết nối SMTP, thay vì khởi đầu plaintext rồi gửi `STARTTLS`. Cổng và phương thức bảo mật phải khớp với thiết lập phía server.

### 7.3. Gửi thư bằng JavaMailSender

```java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class RegistrationMailService {
    private final JavaMailSender mailSender;

    public RegistrationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient, String link) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("no-reply@example.com");
        message.setTo(recipient);
        message.setSubject("Xac nhan dang ky");
        message.setText("Mo lien ket de xac nhan tai khoan: " + link);

        mailSender.send(message);
    }
}
```

Ở đây, ứng dụng chỉ gọi `send(...)`. Spring Mail và Jakarta Mail tạo thông điệp, quản lý SMTP transport và thực hiện các lệnh cần thiết. Để gửi HTML hoặc tệp đính kèm, có thể tạo `MimeMessage` với `MimeMessageHelper`; vòng đời điều khiển của SMTP về cơ bản không thay đổi.

**Đừng nhầm bean `JavaMailSender` được tái sử dụng với socket SMTP luôn mở.** Thời điểm mở/đóng transport phụ thuộc implementation và cách gọi. Một lần gửi nhiều thông điệp có thể tận dụng một kết nối đang mở; không nên mặc định mỗi email luôn tạo một kết nối riêng hoặc luôn dùng lại một kết nối lâu dài.

## 8. Phân tích lỗi theo giai đoạn

Ý nghĩa tổng quát của mã SMTP:

- **2xx**: lệnh tương ứng thành công, ví dụ `220`, `235`, `250` và `221`.
- **3xx**: phản hồi trung gian cần thao tác tiếp, thường gặp `354`.
- **4xx**: thất bại tạm thời; có thể thử lại theo chính sách được kiểm soát.
- **5xx**: thất bại vĩnh viễn trong ngữ cảnh yêu cầu hiện tại; không nên lặp lại vô điều kiện.

| Giai đoạn | Ví dụ lỗi | Hướng xử lý |
|---|---|---|
| Kết nối TCP/DNS | Unknown host, connection refused, connection timeout | Kiểm tra SMTP host, cổng, DNS, firewall, mạng và tình trạng dịch vụ. |
| TLS | STARTTLS không được hỗ trợ, handshake thất bại, chứng chỉ không hợp lệ | So khớp cổng/cơ chế TLS, hostname và certificate trust; không tắt xác minh chứng chỉ để né lỗi. |
| `EHLO` | Không có extension yêu cầu | Xác nhận tính năng server và cấu hình client. |
| `AUTH` | `535` hoặc `454` | Kiểm tra credential/policy với 535; cân nhắc retry có giới hạn với lỗi tạm 454. |
| `MAIL FROM` | Người gửi bị từ chối | Kiểm tra địa chỉ sender, quyền relay và chính sách tên miền. |
| `RCPT TO` | `450`, `550 5.1.1` | Phân biệt mailbox tạm không sẵn sàng và địa chỉ không tồn tại. |
| `DATA` | `552`, `554` | Kiểm tra kích thước, nội dung, định dạng và chính sách máy chủ. |
| Sau kết thúc `DATA` | Timeout trước khi nhận phản hồi `250` | Trạng thái gửi **có thể chưa xác định**; tránh retry gây thư trùng. |
| `QUIT` | Mất kết nối trước `221` | Xem phản hồi sau `DATA` đã nhận được hay chưa trước khi quyết định trạng thái. |

### 8.1. Tình huống khó: đã gửi nội dung nhưng chưa nhận `250`

Ví dụ client đã gửi dấu chấm kết thúc nhưng bị ngắt kết nối trước khi đọc phản hồi cuối:

```text
C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: [headers + body + dấu kết thúc]
[Timeout hoặc mất kết nối trước phản hồi cuối]
```

Client không thể khẳng định server đã chấp nhận hay chưa. Server **có thể** đã xếp hàng thông điệp nhưng phản hồi không đến được client. Retry ngay có nguy cơ gửi trùng; hệ thống quan trọng nên lưu mã sự kiện nghiệp vụ, số lần thử, thời gian và trạng thái đối soát để xử lý trường hợp này.

Tương tự, một phản hồi **250 sau `DATA`** chỉ xác nhận SMTP server ở chặng hiện tại đã tiếp nhận thông điệp. Nếu cần biết email đã được giao, bị bounce, từ chối về sau hoặc có người mở, cần dữ liệu từ hạ tầng giao hàng hoặc nhà cung cấp email phù hợp.

### 8.2. Nhiều người nhận và thành công một phần

SMTP trả phản hồi cho từng `RCPT TO`. Thư viện gửi có thể từ chối cả lời gọi khi có địa chỉ không hợp lệ, hoặc có thể tiếp tục với người nhận hợp lệ tùy implementation và cấu hình. Khi cần theo dõi trạng thái chính xác từng người, nên quản lý việc gửi ở cấp người nhận, lưu kết quả chi tiết hoặc sử dụng event/provider API.

Không nên dùng một cờ boolean “send thành công” để đại diện cho tất cả người nhận nếu bài toán đòi hỏi tính chính xác ở cấp từng email.

## 9. Giám sát và vận hành phiên SMTP

Một log hữu ích nên cho thấy **đã đi đến giai đoạn nào**: connect, TLS, AUTH, MAIL FROM, RCPT TO, DATA hay QUIT. Ví dụ:

```text
220 smtp.example.com ESMTP
250-STARTTLS
250 SIZE 10485760
220 Ready to start TLS
[TLS established]
235 2.7.0 Authentication successful
250 2.1.0 Sender OK
550 5.1.1 User unknown
```

Nếu lần gửi kết thúc ở `550 5.1.1` khi khai báo người nhận, kết nối và AUTH đã qua, nên ưu tiên kiểm tra địa chỉ người nhận. Thay mật khẩu SMTP sẽ không giải quyết đúng lỗi.

Thực hành vận hành nên gồm:

- Ghi thời gian, SMTP host, giai đoạn lỗi, mã phản hồi, mã job hoặc message ID nội bộ.
- Tránh ghi mật khẩu, dữ liệu AUTH, token trong nội dung thư và dữ liệu người nhận không cần thiết.
- Chỉ bật debug giao thức ở môi trường kiểm soát; log SMTP có thể chứa nội dung thư hoặc metadata nhạy cảm.
- Áp dụng timeout, retry/backoff và giới hạn tốc độ gửi theo chính sách nhà cung cấp.
- Phân biệt xác nhận từ SMTP relay với event giao hàng thực tế ở bước sau.

## 10. Câu hỏi tự kiểm tra

1. Trên cổng 587, hãy sắp xếp `220`, `EHLO`, `STARTTLS`, TLS handshake, `EHLO` lần hai và `AUTH`.
2. Vì sao `MAIL FROM` có thể khác header `From:`?
3. Server trả `250` cho `RCPT TO` nhưng trả `554` sau `DATA`. Có thể coi email đã được nhận để chuyển tiếp không?
4. Khi server trả `354`, client phải gửi gì và kết thúc dữ liệu bằng chuỗi nào?
5. Client bị timeout ngay sau khi gửi dấu chấm kết thúc mà chưa nhận `250`. Vì sao retry có thể làm người nhận nhận hai thư?
6. Khác biệt giữa `mail.smtp.starttls.enable=true` và `mail.smtp.starttls.required=true`?
7. Với cổng 465, TLS handshake diễn ra trước hay sau lời chào SMTP `220`?

**Gợi ý:** (1) `220` → `EHLO` → `STARTTLS` → TLS handshake → `EHLO` lại → `AUTH`; (2) một địa chỉ thuộc phong bì chuyển phát, một địa chỉ thuộc header thông điệp; (3) không, giao dịch bị từ chối sau DATA; (4) headers, dòng trống, body, kết thúc `<CRLF>.<CRLF>`; (5) server có thể đã nhận nhưng phản hồi thất lạc; (6) cho phép dùng STARTTLS so với bắt buộc phải nâng cấp thành công; (7) trước `220`.

## 11. Kết luận

Một phiên SMTP từ kết nối đến đóng phiên thông thường đi theo thứ tự **TCP/TLS → `220` → `EHLO` → TLS bổ sung nếu cần → `AUTH` → `MAIL FROM` → `RCPT TO` → `DATA` → phản hồi cuối → `QUIT`/đóng kết nối**. Spring Mail và Jakarta Mail giúp ứng dụng không phải tự viết các lệnh đó, nhưng mỗi bước vẫn có thể thất bại với ý nghĩa riêng.

Khi chẩn đoán, hãy dựa vào **lệnh đang thực hiện, mã SMTP phản hồi và trạng thái kết nối**. Luôn phân biệt “máy chủ SMTP đã tiếp nhận thư” với “người nhận đã nhận được thư”; hai trạng thái này nằm ở những chặng khác nhau của hệ thống email.
