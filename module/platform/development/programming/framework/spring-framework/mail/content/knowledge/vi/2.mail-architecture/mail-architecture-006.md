# SMTP envelope và phần header, body của message

Khi ứng dụng Spring gửi một email, dữ liệu đi qua SMTP không phải chỉ là chuỗi gồm người gửi, người nhận, tiêu đề và nội dung. Có **hai lớp thông tin khác nhau**:

1. **SMTP envelope (phong bì SMTP):** thông tin mà client và máy chủ SMTP trao đổi để *vận chuyển* email.
2. **Email message (thông điệp email):** dữ liệu nằm sau lệnh `DATA`, gồm **header** và **body**, để người nhận và phần mềm xử lý thư đọc được.

Sự phân biệt này giải thích được nhiều tình huống thực tế: email gửi bằng `From` khác tài khoản SMTP; địa chỉ `Bcc` vẫn nhận được email nhưng không hiển thị trong thư; nhấn **Reply** gửi đến người khác với địa chỉ nhận thông báo lỗi; hoặc một email được máy chủ SMTP chấp nhận nhưng về sau bị trả lại.

Trong Spring Framework Mail, lập trình viên chủ yếu làm việc với `JavaMailSender`, `SimpleMailMessage`, `MimeMessage` và `MimeMessageHelper`. Thư viện đảm nhiệm việc kết nối SMTP và tạo định dạng truyền phù hợp, nhưng hiểu đúng phong bì, header và body vẫn cần thiết khi cấu hình, xử lý lỗi và kiểm tra bảo mật.

## 1. Nhìn tổng thể: phong bì đứng ngoài nội dung thư

Một phiên SMTP có cấu trúc khái quát:

```text
Kết nối và xác thực SMTP (nếu cần)
    |
    +-- MAIL FROM:<bounce@example.com>     <- Envelope sender
    |
    +-- RCPT TO:<lan@example.org>          <- Envelope recipient #1
    |
    +-- RCPT TO:<archive@example.net>      <- Envelope recipient #2
    |
    +-- DATA
          |
          +-- Header: From, To, Subject, Reply-To, ...
          +-- Dòng trống ngăn cách
          +-- Body: text, HTML hoặc MIME multipart
          |
          +-- Kết thúc DATA
    |
    +-- SMTP server trả kết quả chấp nhận hoặc từ chối
```

**Envelope không nằm trong nội dung sau `DATA`.** Nếu chỉ mở file `.eml` hoặc xem “Show original” trong hộp thư, thông thường bạn đang xem các header và body đã được lưu, chứ không thấy đầy đủ các lệnh `MAIL FROM` và `RCPT TO` của phiên SMTP ban đầu.

Sự khác biệt cốt lõi:

| Khía cạnh | SMTP envelope | Message header và body |
|---|---|---|
| Mục đích | Chỉ dẫn máy chủ chuyển thư đến đâu, địa chỉ xử lý thông báo lỗi | Mô tả người gửi, người nhận, chủ đề và nội dung cho ứng dụng đọc thư |
| Vị trí trên giao thức | Lệnh `MAIL FROM`, `RCPT TO` trước `DATA` | Nội dung truyền trong `DATA` |
| Tiêu chuẩn nền tảng | SMTP / RFC 5321 | Internet Message Format / RFC 5322; MIME mở rộng cho nội dung |
| Người nhận thực tế | Các địa chỉ được chấp nhận qua `RCPT TO` | `To:`, `Cc:` là các trường hiển thị; `Bcc:` cần được xử lý kín |
| Địa chỉ gửi | Envelope sender, thường dùng khi phát sinh bounce | `From:` cho biết tác giả/địa chỉ hiển thị của thư |
| Khả năng khác nhau | Có thể khác với header | Có thể tồn tại header không tương ứng từng địa chỉ vận chuyển |

Một email có thể được chuyển qua nhiều máy chủ. Mỗi chặng SMTP dùng envelope phù hợp cho chặng đó; các máy chủ trung gian cũng có thể bổ sung header truy vết. Không nên giả định envelope giữ nguyên tuyệt đối qua toàn bộ hệ thống relay.

## 2. SMTP envelope: ai gửi về mặt vận chuyển, gửi đến đâu?

### 2.1. `MAIL FROM` — envelope sender

Lệnh ví dụ:

```smtp
MAIL FROM:<bounce@example.com>
```

Đây là **reverse-path**, thường là địa chỉ mà hệ thống thư dùng để gửi báo cáo không phân phát được (non-delivery report, bounce). Địa chỉ này có thể khác hoàn toàn với `From:` trong header:

```text
SMTP envelope: MAIL FROM:<bounce@example.com>
Message header: From: "Shop Demo" <news@example.com>
```

Người dùng thấy thư “từ Shop Demo”; hạ tầng mail có thể gửi thông báo thất bại đến `bounce@example.com`.

Điều cần phân biệt:

- `MAIL FROM` không phải tài khoản dùng để đăng nhập SMTP. Tên người dùng xác thực (`AUTH`) chỉ là danh tính cấp quyền gửi; nhà cung cấp có thể yêu cầu envelope sender hoặc header `From` thuộc miền đã được cấp phép.
- `MAIL FROM` không nhất thiết trùng `Reply-To`: trả lời email và báo lỗi vận chuyển là hai tác vụ khác nhau.
- Khi hệ thống tạo thông báo lỗi gửi tự động, SMTP có thể sử dụng **null reverse-path**: `MAIL FROM:<>`. Cách này giúp tránh vòng lặp các email báo lỗi qua lại. Ứng dụng bình thường không tự chọn giá trị này cho thư thông báo.

Một số server hỗ trợ tham số SMTP mở rộng như `SIZE` hay `SMTPUTF8` trong giao dịch. Những tham số đó thuộc lớp vận chuyển, không phải các trường header thông thường.

### 2.2. `RCPT TO` — danh sách người nhận để vận chuyển

Ví dụ:

```smtp
RCPT TO:<lan@example.org>
RCPT TO:<archive@example.net>
```

Mỗi `RCPT TO` khai báo **một địa chỉ nhận trên envelope**. Các địa chỉ được chấp nhận ở bước này là cơ sở để máy chủ chuyển tiếp email.

Điều này **không đồng nghĩa** mỗi `RCPT TO` bắt buộc có một dòng tương ứng trong header `To:`. Ví dụ cùng một message:

```text
Envelope recipients:
  lan@example.org
  archive@example.net

Message headers:
  To: Lan <lan@example.org>
  Subject: Ket qua dang ky
```

`archive@example.net` có thể là người nhận ẩn (`Bcc`), hoặc một người nhận khác được chỉ định khi gửi. Tên của họ không cần xuất hiện trong `To:`.

Máy chủ có thể chấp nhận một địa chỉ và từ chối địa chỉ khác. Việc xử lý lỗi từng recipient phụ thuộc phản hồi SMTP và cách thư viện/client tiếp tục giao dịch; không nên suy luận rằng mọi người nhận đều thành công chỉ từ việc một recipient được chấp nhận.

### 2.3. `DATA` và sự tách biệt khỏi envelope

Sau khi SMTP server cho phép nhập nội dung bằng phản hồi `354`, client gửi **message header và body** rồi kết thúc dữ liệu bằng quy tắc SMTP (chuỗi `<CRLF>.<CRLF>`). Dấu chấm đầu dòng trong phần body được client xử lý bằng cơ chế *dot-stuffing* để tránh bị hiểu nhầm là dấu kết thúc.

Cơ chế này là chi tiết của SMTP transport. Khi sử dụng `JavaMailSender`, ứng dụng không phải tự chèn dấu chấm kết thúc hay tự viết lệnh `DATA`.

Máy chủ trả `250` sau khi nhận xong `DATA` nghĩa là nó đã **chấp nhận thư để xử lý tiếp**. Phản hồi này chưa xác nhận thư đã xuất hiện trong Inbox, chưa nói người nhận đã mở thư, và cũng không đảm bảo thư sẽ không bị bounce về sau.

## 3. Message header: thông tin mô tả thư

**Header** là các dòng đứng trước một dòng trống đầu tiên trong message. Mỗi trường có dạng khái quát `Tên-Trường: giá trị`. Header chuẩn định nghĩa cấu trúc của email; MIME bổ sung những header mô tả kiểu nội dung.

Một message đơn giản:

```text
From: "Demo App" <notifications@example.com>
To: "Lan" <lan@example.org>
Reply-To: support@example.com
Date: Thu, 12 Nov 2026 08:00:00 +0000
Message-ID: <welcome-123@example.com>
Subject: Welcome to Demo App
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Your account is ready.
```

Dòng trống sau `Content-Type` là ranh giới giữa **header** và **body**. Các dòng thuộc header không phải lệnh SMTP; chúng được gửi như dữ liệu thông điệp trong `DATA`.

### 3.1. Các header thường gặp

| Header | Vai trò | Điểm cần nhớ |
|---|---|---|
| `From:` | Xác định tác giả/địa chỉ gửi hiển thị | Không tự quyết định nơi nhận bounce và không tự chứng minh người gửi đã được xác thực. |
| `Sender:` | Xác định tác nhân thực hiện gửi khi cần phân biệt với tác giả | Có ý nghĩa riêng trong cấu trúc message; không phải đồng nghĩa với `MAIL FROM`. |
| `To:` | Người nhận chính hiển thị | Không phải danh sách duy nhất quyết định vận chuyển. |
| `Cc:` | Người nhận bản sao hiển thị | Thường cũng có `RCPT TO` riêng. |
| `Bcc:` | Người nhận bản sao kín | Địa chỉ vẫn phải được giao tới SMTP nhưng không được làm lộ qua bản sao thư cho người nhận khác. |
| `Reply-To:` | Địa chỉ ưu tiên khi người dùng trả lời | Không thay đổi `MAIL FROM` hoặc `RCPT TO` của email đang gửi. |
| `Subject:` | Tiêu đề | Là metadata hiển thị, không phải lệnh vận chuyển. |
| `Date:` | Thời điểm tạo/gửi message theo header | Khác với thời điểm máy chủ nhận hoặc phân phát. |
| `Message-ID:` | Định danh thông điệp | Hỗ trợ truy vết/tham chiếu; không phải mã xác nhận đã gửi thành công. |
| `MIME-Version:` | Báo rằng message dùng MIME | Thường là `1.0`. |
| `Content-Type:` | Kiểu nội dung của body hay từng MIME part | Ví dụ `text/plain`, `text/html`, `multipart/alternative`. |
| `Content-Transfer-Encoding:` | Cách biểu diễn byte của phần body | Ví dụ `quoted-printable` hoặc `base64`. |
| `Received:` | Dấu vết một chặng vận chuyển | Thường được máy chủ mail thêm vào, có thể xuất hiện nhiều lần. |
| `Return-Path:` | Dấu vết địa chỉ bounce khi thư được phân phát | Thường do hạ tầng mail đặt dựa trên reverse-path, không phải cách ứng dụng thay thế `MAIL FROM`. |

Các bộ lọc xác thực còn có thể bổ sung header như `Authentication-Results`; dịch vụ ký thư có thể chèn `DKIM-Signature`. Nguồn tạo ra từng header cần được xem xét khi phân tích thư, vì không phải mọi header đều do Spring hoặc ứng dụng ban đầu thiết lập.

### 3.2. `From`, `Sender` và `Reply-To` không thay thế nhau

Giả sử doanh nghiệp gửi thông báo thay mặt đội hỗ trợ:

```text
From: "Demo Support" <notice@example.com>
Reply-To: helpdesk@example.com
```

Khi nhấn **Reply**, phần mềm đọc thư thường ưu tiên `helpdesk@example.com`. Nhưng nếu thư không thể phân phát, hệ thống mail lại dựa vào envelope sender để xử lý bounce. Việc đặt `Reply-To` không thay đổi địa chỉ phục vụ báo lỗi.

`Sender` còn có nghĩa riêng trong email có nhiều tác giả ở `From` hoặc khi tác nhân gửi cần được biểu diễn tách biệt. Trong một hệ thống gửi thông báo đơn giản, thường chỉ cần `From` và tùy nhu cầu thêm `Reply-To`.

### 3.3. Vì sao `Bcc` là ví dụ rõ nhất của hai lớp?

Khi gửi:

```text
To: lan@example.org
Bcc: auditor@example.net
```

Danh sách recipient chuyển cho SMTP bao gồm cả `lan@example.org` và `auditor@example.net`. Tuy nhiên, **thông điệp đến Lan không được tiết lộ danh sách người nhận kín**. Theo cách gửi phổ biến, header `Bcc` bị loại khỏi bản sao phát cho các người nhận khác; các cách gửi hợp lệ khác có thể tạo bản sao riêng cho người nhận Bcc.

Vì vậy, không thể suy ra đầy đủ người nhận thực tế chỉ từ `To:` và `Cc:` trong bản raw message đã được phát. Khi tự tạo raw MIME hoặc proxy mail, phải bảo đảm cơ chế giấu Bcc được xử lý đúng; đừng chỉ giả định viết thêm một dòng header `Bcc:` sẽ tự bảo mật.

### 3.4. Header không phải dữ liệu nhập tự do

Tên hiển thị có tiếng Việt, tiêu đề Unicode hoặc những dòng header dài cần được mã hóa và gấp dòng theo chuẩn mail. Thư viện Jakarta Mail xử lý phần lớn công việc này khi tạo `MimeMessage`.

Không ghép trực tiếp các header bằng chuỗi từ dữ liệu người dùng. Đặc biệt, ký tự CR/LF trong giá trị không được kiểm soát có thể dẫn đến *header injection* trong các triển khai tự viết sai. Nên dùng API `setFrom`, `setRecipients`, `setSubject`, `MimeMessageHelper` và kiểm tra định dạng địa chỉ phù hợp.

## 4. Message body: văn bản, HTML và MIME

**Body** là phần nội dung sau dòng trống phân cách header. Body có thể là văn bản đơn giản, HTML, hoặc tập hợp nhiều phần MIME (Multipurpose Internet Mail Extensions).

### 4.1. Body văn bản thuần

```text
From: no-reply@example.com
To: lan@example.org
Subject: Account notification
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Hello Lan,
Your account has been created.
```

Ở đây body là đoạn văn bản sau dòng trống. Header `Content-Type` cho biết cách phần mềm đọc mail diễn giải nội dung và bộ ký tự.

### 4.2. Body HTML

```text
From: no-reply@example.com
To: lan@example.org
Subject: Account notification
MIME-Version: 1.0
Content-Type: text/html; charset=UTF-8

<h1>Welcome</h1>
<p>Your account has been created.</p>
```

Dù là HTML, nội dung vẫn chỉ là **body của message**, không có ảnh hưởng trực tiếp lên `MAIL FROM` hoặc danh sách `RCPT TO`. Các email HTML phức tạp thường đi kèm phiên bản văn bản thuần để các trình đọc thư và công cụ hỗ trợ tiếp cận có lựa chọn thay thế.

### 4.3. Body nhiều phần với `multipart/alternative`

Khi gửi cả plain text lẫn HTML, body là một cấu trúc MIME gồm các phần có boundary. Ví dụ rút gọn:

```eml
From: no-reply@example.com
To: lan@example.org
Subject: Account notification
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="demo-boundary"

--demo-boundary
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 7bit

Hello Lan. Your account has been created.
--demo-boundary
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: 7bit

<html><body><p>Hello <strong>Lan</strong>.</p></body></html>
--demo-boundary--
```

Phần mềm đọc thư thường chọn một bản thể hiện phù hợp. `boundary` chỉ dùng để phân tách các MIME part trong **body**, không phải phong bì SMTP hay ranh giới kết thúc lệnh `DATA`.

Các tổ hợp phổ biến:

| MIME content type | Dùng khi |
|---|---|
| `text/plain` | Nội dung văn bản. |
| `text/html` | Nội dung HTML. |
| `multipart/alternative` | Nhiều cách thể hiện của cùng một nội dung, thường là plain text và HTML. |
| `multipart/mixed` | Gồm nội dung thư và các thành phần độc lập như tệp đính kèm. |
| `multipart/related` | Các thành phần liên quan để dựng một nội dung, ví dụ HTML và hình ảnh nhúng tham chiếu bằng CID. |

Mỗi MIME part có thể có **header riêng**, như `Content-Type`, `Content-Disposition`, `Content-ID`, `Content-Transfer-Encoding`. Không nên nhầm chúng với nhóm header cấp message nằm ở đầu thư.

### 4.4. Mã hóa body khác mã hóa đường truyền

`Content-Transfer-Encoding: base64` hoặc `quoted-printable` là **cách biểu diễn dữ liệu** để có thể truyền qua hạ tầng email. Đây không phải mã hóa bảo mật.

- **UTF-8 / charset:** quy định cách ánh xạ ký tự thành byte.
- **Quoted-printable / base64:** quy định cách biểu diễn byte trong nội dung MIME.
- **TLS khi kết nối SMTP:** bảo vệ kết nối mạng của một chặng.
- **Mã hóa đầu cuối:** là bài toán riêng, thường cần công nghệ như S/MIME hoặc OpenPGP.

Địa chỉ người gửi và người nhận vẫn thuộc envelope/header tương ứng, cho dù body dùng HTML, base64 hay có đính kèm.

## 5. Ví dụ một giao dịch SMTP đầy đủ

Ví dụ: ứng dụng gửi thông báo cho Lan, đồng thời gửi một bản sao kín tới hệ thống lưu trữ. Địa chỉ báo lỗi được đặt riêng.

```text
S: 220 smtp.example.com ESMTP
C: EHLO app.example.com
S: 250-smtp.example.com
S: 250-STARTTLS
S: 250 AUTH PLAIN LOGIN
C: STARTTLS
S: 220 Ready to start TLS
   [Hai phía thiết lập kết nối TLS]
   [EHLO lại và xác thực SMTP nếu máy chủ yêu cầu]
C: MAIL FROM:<bounce@example.com>
S: 250 2.1.0 Sender OK
C: RCPT TO:<lan@example.org>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<archive@example.net>
S: 250 2.1.5 Recipient OK
C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: From: "Demo App" <notice@example.com>
C: To: Lan <lan@example.org>
C: Reply-To: support@example.com
C: Subject: Account notification
C: MIME-Version: 1.0
C: Content-Type: text/plain; charset=UTF-8
C:
C: Hello Lan,
C: Your account is ready.
C: .
S: 250 2.0.0 Accepted for delivery
C: QUIT
S: 221 Bye
```

Đây là transcript minh họa: phản hồi server, khả năng và bước AUTH thực tế phụ thuộc nhà cung cấp. Chú ý ba địa chỉ có **ba vai trò khác nhau**:

- `bounce@example.com` là **envelope sender**, nơi có thể nhận thông báo không phân phát được.
- `notice@example.com` là **header From**, địa chỉ người nhận nhìn thấy là bên gửi thư.
- `support@example.com` là **Reply-To**, địa chỉ được ưu tiên khi người nhận bấm trả lời.

`archive@example.net` có trong `RCPT TO` để được chuyển thư nhưng **không xuất hiện trong header `To:`** của thông điệp phát cho Lan. Phần body chỉ bắt đầu sau dòng trống, không bao gồm các dòng khai báo envelope.

## 6. Ánh xạ các khái niệm vào Spring Framework Mail

### 6.1. Chọn API phù hợp

| API Spring/Jakarta Mail | Phần nó giúp ứng dụng kiểm soát |
|---|---|
| `SimpleMailMessage` | Các trường thư thường gặp và body dạng text thuần; phù hợp thông báo đơn giản. |
| `JavaMailSender` | Tạo/gửi `MimeMessage` hoặc gửi `SimpleMailMessage` tới máy chủ SMTP. |
| `MimeMessage` | Nội dung message gồm header và body MIME. |
| `MimeMessageHelper` | Đặt `From`, `To`, `Cc`, `Bcc`, `Reply-To`, `Subject`, body text/HTML và attachment. |
| `JavaMailSenderImpl` | Triển khai gửi qua Jakarta Mail; dùng thuộc tính SMTP để thiết lập kết nối và một số đặc tính envelope. |

**`MimeMessageHelper.setFrom(...)` đặt header `From`; không nên hiểu đó là API độc lập để cấu hình envelope sender.** `setTo`, `setCc`, `setBcc` tạo các recipient header/metadata mà tầng gửi mail dùng để lập danh sách người nhận SMTP theo cơ chế của Jakarta Mail.

### 6.2. Cấu hình Spring Boot

Spring Framework Mail có thể dùng trong ứng dụng Spring thuần. Ví dụ dưới đây sử dụng tính năng cấu hình tự động của **Spring Boot** với dependency `spring-boot-starter-mail`, vì đây là trường hợp tích hợp thường gặp:

```yaml
# application.yml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
      "[mail.smtp.from]": bounce@example.com

app:
  mail:
    from: notice@example.com
    reply-to: support@example.com
```

Giải thích:

- `spring.mail.host` và `port` chọn máy chủ SMTP để ứng dụng kết nối.
- `mail.smtp.auth` và các thuộc tính STARTTLS quy định xác thực và bảo vệ kết nối theo yêu cầu server.
- `mail.smtp.from` là một **thuộc tính Jakarta Mail SMTP** thường dùng để chỉ định địa chỉ envelope `MAIL FROM` khi gửi qua SMTP transport tương ứng.
- `app.mail.from` và `app.mail.reply-to` là **cấu hình do ứng dụng tự đặt tên**, được dùng để xây dựng header `From` và `Reply-To` trong code bên dưới.

Cấu hình `mail.smtp.from` ở cấp mail sender thường áp dụng cho các lần gửi qua cấu hình đó. Nếu mỗi loại thư cần envelope sender khác nhau, phải thiết kế cơ chế chọn theo từng message/transport phù hợp; không nên thay đổi thuộc tính dùng chung trên một bean trong lúc nhiều luồng gửi đồng thời.

Địa chỉ envelope/header phải được nhà cung cấp SMTP cho phép. Thông tin đăng nhập thực nên lấy từ biến môi trường hoặc secret manager.

### 6.3. Tạo message bằng `MimeMessageHelper`

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class AccountNotificationMailService {
    private final JavaMailSender mailSender;
    private final String from;
    private final String replyTo;

    public AccountNotificationMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String from,
            @Value("${app.mail.reply-to}") String replyTo) {
        this.mailSender = mailSender;
        this.from = from;
        this.replyTo = replyTo;
    }

    public void sendAccountReady(String recipient) throws MessagingException {
        MimeMessage mimeMessage = mailSender.createMimeMessage();

        // multipart=true cho phép tạo cả text/plain và text/html.
        MimeMessageHelper helper =
                new MimeMessageHelper(mimeMessage, true, "UTF-8");

        // Header của message:
        helper.setFrom(from, "Demo App");
        helper.setTo(recipient);
        helper.setBcc("archive@example.net");
        helper.setReplyTo(replyTo);
        helper.setSubject("Tài khoản đã sẵn sàng");

        // Hai phần thể hiện cùng một nội dung.
        helper.setText(
                "Xin chào! Tài khoản của bạn đã sẵn sàng.",
                "<p>Xin chào! <strong>Tài khoản của bạn đã sẵn sàng.</strong></p>"
        );

        mailSender.send(mimeMessage);
    }
}
```

Với cấu hình ví dụ:

1. `helper.setFrom(...)` tạo header `From: "Demo App" <notice@example.com>`.
2. `helper.setTo(...)` thiết lập người nhận hiển thị. `helper.setBcc(...)` thêm người nhận kín; tầng gửi mail xử lý việc giao email tới các recipient này.
3. `helper.setReplyTo(...)` đặt địa chỉ phục vụ thao tác trả lời, không thay đổi phong bì SMTP.
4. `helper.setText(plain, html)` thiết lập body theo cấu trúc MIME có cả plain text và HTML.
5. `mailSender.send(mimeMessage)` giao cho Jakarta Mail SMTP transport thực hiện truyền thư; trong ví dụ, `mail.smtp.from` chỉ định envelope sender là `bounce@example.com`.

Chương trình chỉ đặt một số header cần thiết. Các header khác như `Date`, `Message-ID` hoặc trường MIME có thể do thư viện bổ sung/hoàn thiện trước khi gửi.

Khi `send(...)` kết thúc thành công, điều đó thông thường chỉ xác nhận lần gửi tới SMTP đã hoàn tất theo phản hồi server. Kết quả chuyển tiếp đến hộp thư đích nằm ngoài phạm vi xác nhận trực tiếp của API này.

### 6.4. Khi nào dùng `SimpleMailMessage`?

Nếu chỉ gửi văn bản thuần, có thể giảm độ phức tạp:

```java
import org.springframework.mail.SimpleMailMessage;

SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("notice@example.com");
message.setTo("lan@example.org");
message.setReplyTo("support@example.com");
message.setSubject("Account notification");
message.setText("Your account is ready.");

mailSender.send(message);
```

`SimpleMailMessage` tiện cho nội dung đơn giản, nhưng không hỗ trợ trực tiếp cấu trúc HTML/attachment phức tạp như `MimeMessage`. Việc thiết lập envelope sender vẫn cần xem cấu hình của SMTP transport; `setFrom(...)` là địa chỉ trong header message.

## 7. Các vấn đề thực tế thường bị nhầm lẫn

### 7.1. Đặt `From` thành công chưa chắc đã được phép gửi

Header `From` có thể được gán trong code, nhưng nhà cung cấp SMTP có thể giới hạn những miền hoặc địa chỉ được phép dùng. Việc xác thực tài khoản SMTP không mặc nhiên cho phép thay mặt mọi domain. Phần mềm nhận mail cũng có cơ chế đánh giá tính xác thực của địa chỉ hiển thị.

Ba cơ chế liên quan cần biết:

| Cơ chế | Dữ liệu được sử dụng | Điều nó giúp xác minh |
|---|---|---|
| **SPF** | IP máy chủ gửi và danh tính thuộc lớp SMTP như envelope sender domain | Máy chủ gửi có được domain liên quan cho phép hay không. |
| **DKIM** | Chữ ký mật mã trên những phần header và body của message | Nội dung được ký có còn nguyên và chữ ký khớp với domain ký hay không. |
| **DMARC** | `From` domain trong header và kết quả SPF/DKIM với quy tắc alignment | Kết quả xác thực có phù hợp với domain `From` hiển thị theo chính sách hay không. |

Vì vậy, `MAIL FROM` và `From:` khác nhau là điều có thể hợp lệ. Tuy nhiên, nếu domain không được cấu hình đúng, email có thể bị đánh giá là giả mạo hoặc bị từ chối. SPF/DKIM/DMARC thuộc phần cấu hình domain và dịch vụ mail, không phải chỉ cần thêm một trường header tùy ý trong Spring.

### 7.2. Đổi `Reply-To` không đổi nơi nhận bounce

Nếu thư có:

```text
MAIL FROM:<bounce@example.com>
From: billing@example.com
Reply-To: support@example.com
```

- Người dùng thấy thư từ `billing@example.com`.
- Khi người dùng trả lời, thư mới thường được gửi tới `support@example.com`.
- Nếu mail server gửi báo lỗi tự động về phiên vận chuyển ban đầu, địa chỉ thường là `bounce@example.com`.

Đây là ba quy trình khác nhau; chỉ có địa chỉ trong header không đủ để dựng lại toàn bộ hành vi.

### 7.3. `Return-Path` không phải cách thiết lập envelope

Khi đọc thư đã nhận, có thể thấy:

```text
Return-Path: <bounce@example.com>
Received: from relay.example.com ...
From: "Demo App" <notice@example.com>
```

`Return-Path` thường được đưa vào message khi mail được phân phát dựa trên reverse-path đang có ở SMTP. Nó là một **dấu vết trong message đã nhận**. Nếu muốn điều khiển phong bì gửi bằng Jakarta Mail SMTP transport, cần dùng cơ chế envelope tương ứng, như `mail.smtp.from`, thay vì tự gán `Return-Path` và hy vọng server sẽ dùng trường đó.

### 7.4. File `.eml` không hiển thị đầy đủ envelope

Một file email có thể lưu đủ header và body, kể cả dấu `Received` hay `Return-Path` nếu hệ thống đã thêm chúng. Nhưng nó thường **không lưu từng lệnh `RCPT TO`** đã dùng khi gửi. Với thư Bcc, chỉ đọc `.eml` có thể không xác định được tất cả người nhận thực tế. Cần truy vết SMTP log hoặc metadata từ nhà cung cấp để biết chắc.

### 7.5. Header và body đều có thể rất lớn

Tệp đính kèm thuộc MIME body và thường bị mã hóa base64, dẫn tới kích thước truyền có thể lớn hơn tệp gốc. SMTP server có giới hạn dung lượng, số người nhận và tốc độ gửi. Các giới hạn này áp dụng cho giao dịch truyền, không đơn thuần cho độ dài tiêu đề.

### 7.6. Bảo mật khi quan sát raw email

Log SMTP và raw message có thể chứa địa chỉ cá nhân, nội dung nhạy cảm, mã xác nhận, attachment và thậm chí dấu vết xác thực nếu debug cấu hình sai. Chỉ bật trace/debug cần thiết trong môi trường phù hợp, ẩn bí mật và kiểm soát quyền truy cập log.

## 8. Bảng đối chiếu nhanh khi xử lý sự cố

| Quan sát | Kiểm tra phần nào trước? | Lý do |
|---|---|---|
| Thư hiện tên người gửi không đúng | Header `From` / display name | Đây là thông tin hiển thị. |
| Reply đi sai địa chỉ | Header `Reply-To`, sau đó `From` | Phần mềm đọc thư quyết định đích trả lời từ header. |
| Bounce về sai mailbox | SMTP `MAIL FROM`, thông tin `Return-Path` và cấu hình relay | Báo lỗi vận chuyển liên quan envelope sender. |
| Bcc không nhận thư | Danh sách recipient của message và `RCPT TO`/SMTP log | Recipient ẩn vẫn phải được chuyển cho SMTP. |
| Người nhận khác nhìn thấy Bcc | Cách tạo/ghi/relay message và loại bỏ header Bcc | Đó là lỗi tiết lộ người nhận, cần xử lý tại tầng tạo/gửi. |
| HTML hiện dưới dạng mã thô | MIME `Content-Type`, cách xây dựng body | Client chưa diễn giải body là HTML đúng cách. |
| Chữ tiếng Việt lỗi font/ký tự | Charset, `Content-Transfer-Encoding` và mã hóa header | Thường là vấn đề định dạng MIME, không phải envelope. |
| Server báo recipient không hợp lệ | `RCPT TO` và phản hồi SMTP | Lỗi xảy ra khi chuyển địa chỉ nhận qua transport. |
| `send(...)` thành công nhưng không có thư trong Inbox | SMTP acceptance, log chuyển tiếp, bounce, Spam | Chấp nhận ở SMTP chưa phải giao thư đến hộp thư. |

## 9. Tổng kết qua một phép đối chiếu

Giả sử hệ thống phát một email với những giá trị sau:

```text
AUTH username: service-account
MAIL FROM:     bounce@example.com
RCPT TO:       lan@example.org
RCPT TO:       archive@example.net

From:          Demo App <notice@example.com>
To:            Lan <lan@example.org>
Reply-To:      support@example.com
Subject:       Account notification
Content-Type:  multipart/alternative; ...
Body:          text/plain + text/html
```

Hãy đọc nó theo đúng thứ tự:

- **AUTH** là danh tính dùng để được phép gửi qua SMTP.
- **MAIL FROM** là envelope sender phục vụ vận chuyển và xử lý lỗi.
- **RCPT TO** là các địa chỉ mà server được yêu cầu chuyển thư tới, kể cả người nhận kín.
- **From, To, Reply-To, Subject** là header mô tả thông điệp và hành vi của phần mềm đọc thư.
- **Content-Type** giải thích cách diễn giải body; body chứa phần nội dung và các MIME part.

Trong Spring Framework Mail, các API tạo message giúp lập trình viên biểu diễn **header và body** rõ ràng, còn `JavaMailSender` cùng SMTP transport chuyển email với **envelope** được xác định bởi danh sách recipient và cấu hình gửi. Phân biệt đúng hai lớp này giúp hiểu hành vi Bcc, truy vết bounce, thiết lập bảo mật domain và chẩn đoán các sự cố chuyển thư.
