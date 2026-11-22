# Vai trò của ứng dụng, mail client, MTA, MDA và mailbox

Khi ứng dụng Spring gửi email xác nhận đăng ký, đặt lại mật khẩu hoặc thông báo đơn hàng, câu lệnh gửi trong Java chỉ khởi đầu một quá trình gồm nhiều thành phần. Để thư xuất hiện trong hộp thư người nhận, cần phân biệt **ứng dụng**, **mail client**, **Mail Submission Agent (MSA)**, **Mail Transfer Agent (MTA)**, **Mail Delivery Agent (MDA)** và **mailbox**. Mỗi thành phần có một ranh giới trách nhiệm khác nhau.

Mục tiêu của bài là hiểu luồng gửi, chuyển tiếp, giao và đọc email; nhận biết giao thức ở từng chặng; và xác định chính xác **Spring Framework Mail** làm gì trong hệ thống.

## 1. Bức tranh tổng thể

Giả sử ứng dụng bán hàng gửi thư từ `orders@shop.example` đến `customer@example.net`:

```text
  PHÍA GỬI                                               PHÍA NHẬN

 [Ứng dụng Spring]                                      [Mail client]
 [hoặc mail client]                                   (điện thoại/webmail)
        |                                                    ^
        | 1. SMTP submission                                 | 6. IMAP/POP3
        v                                                    |
 [MSA / MTA phía gửi]                                 [Mailbox người nhận]
        |                                                    ^
        | 2. Tra cứu DNS MX, chuyển tiếp SMTP                 | 5. Lưu thư
        v                                                    |
 [MTA của miền nhận] ---- 3. Nhận, định tuyến ---> [MDA / dịch vụ giao thư]
                                                     |
                                                     +-- 4. Lọc, phân loại
```

Sơ đồ mô tả các **vai trò logic**, không khẳng định mỗi hộp là một máy chủ vật lý. Nhiều vai trò có thể cùng chạy trong một sản phẩm hoặc được phân tán giữa các dịch vụ. Một thư cũng có thể đi qua nhiều MTA trung gian.

| Thành phần | Tên khác | Trách nhiệm chính | Có lưu thư cuối cùng? |
| --- | --- | --- | --- |
| **Ứng dụng** | Application | Sinh nội dung, quyết định người nhận, thời điểm và yêu cầu gửi | Thông thường không |
| **Mail client** | Mail User Agent (MUA) | Giao diện soạn, gửi, đọc và quản lý email cho người dùng | Có thể lưu bản sao cục bộ, không nhất thiết là nguồn lưu gốc |
| **MSA** | Mail Submission Agent | Nhận thư từ ứng dụng/MUA, kiểm tra xác thực và quyền gửi | Không |
| **MTA** | Mail Transfer Agent | Định tuyến, chuyển tiếp email giữa máy chủ, quản lý hàng đợi và thử lại | Không phải mailbox người nhận |
| **MDA** | Mail Delivery Agent | Giao cuối cùng vào kho thư, có thể phối hợp lọc và phân loại | Ghi thư vào kho lưu trữ |
| **Mailbox** | Hộp thư | Kho lưu email và metadata của tài khoản hoặc đích nhận | **Có** |

Bốn hành động cần tách bạch là **nộp thư** (*submission*), **chuyển thư** (*transfer/relay*), **giao thư cuối cùng** (*delivery*) và **truy cập/đọc thư** (*retrieval/access*). Từ “gửi thành công” có thể chỉ việc hoàn tất hành động đầu tiên.

## 2. Ứng dụng: nơi phát sinh nhu cầu gửi email

Ứng dụng quyết định **vì sao**, **khi nào**, **gửi cho ai** và **gửi nội dung gì**. Ví dụ, một service Spring nhận sự kiện đơn hàng được xác nhận, xác định địa chỉ nhận, tạo tiêu đề, nội dung văn bản/HTML rồi yêu cầu gửi.

Trong Spring Framework Mail, interface `JavaMailSender` giúp ứng dụng tạo và nộp thư qua phương thức truyền gửi, thường là **SMTP**. Ứng dụng lúc này đóng vai trò một **mail client tự động**: thay vì người dùng bấm “Send”, chương trình chủ động gửi thông điệp.

Hai cách tích hợp thường gặp:

- **SMTP submission:** ứng dụng kết nối tới SMTP server của tổ chức hoặc nhà cung cấp email.
- **HTTP API của nhà cung cấp:** ứng dụng gọi API gửi thư; nhà cung cấp xử lý chuyển phát ở các tầng tiếp theo.

Ứng dụng có thể lưu nhật ký hoặc trạng thái gửi trong cơ sở dữ liệu riêng để phục vụ nghiệp vụ. Việc đó không biến cơ sở dữ liệu của ứng dụng thành mailbox của người nhận. Tương tự, ứng dụng có thể xử lý email đến nếu triển khai thêm khả năng nhận/đọc, nhưng **chức năng gửi email trong Spring Mail không tự cung cấp MTA, MDA hay mailbox**.

## 3. Mail client (MUA): công cụ người dùng soạn và đọc thư

**Mail User Agent (MUA)** là phần mềm như Outlook, Thunderbird, ứng dụng Mail trên điện thoại hoặc giao diện webmail. Nó cho phép người dùng soạn thư, quản lý thư mục, tìm kiếm, trả lời và đọc email.

Một mail client thường thực hiện hai hướng giao tiếp:

1. **Đường gửi:** nộp thông điệp tới máy chủ submission, thông dụng qua SMTP.
2. **Đường đọc:** truy cập mailbox qua IMAP, POP3 hoặc giao diện/API riêng của dịch vụ webmail.

Mail client có thể giữ bản sao email để đọc ngoại tuyến. Với IMAP, nhiều client thường đồng bộ thư, thư mục và trạng thái đọc với kho thư trên máy chủ. Vì vậy, người dùng có thể đổi từ điện thoại sang trình duyệt và vẫn thấy cùng hộp thư.

So sánh ba trường hợp:

| Trường hợp | Ai phát lệnh gửi? | Ai cho người nhận đọc thư? |
| --- | --- | --- |
| Người dùng gửi bằng Outlook | Outlook, với vai trò MUA | Outlook hoặc MUA khác |
| Website Spring gửi link xác nhận | Ứng dụng Spring, như một client tự động | Mail client của người nhận |
| Người dùng gửi/nhận bằng webmail | Giao diện webmail và các dịch vụ phía sau | Giao diện webmail |

Ứng dụng gửi email tự động **không cần** triển khai màn hình soạn thư hay IMAP chỉ để gửi thông báo.

## 4. MSA và MTA: tiếp nhận và chuyển tiếp thư

### 4.1. MSA nhận thư do client nộp

**Mail Submission Agent (MSA)** là điểm đầu vào dành cho ứng dụng hoặc mail client. Nó có thể yêu cầu xác thực SMTP, kiểm tra địa chỉ người gửi, áp dụng hạn ngạch và chính sách chống lạm dụng.

Trong hướng dẫn cấu hình, MSA thường được gọi chung là “SMTP server”. Submission dùng phổ biến **cổng 587 kết hợp STARTTLS**, hoặc **cổng 465 với TLS ngay khi thiết lập kết nối**. Nhà cung cấp thực tế quyết định cổng và cơ chế xác thực được hỗ trợ.

### 4.2. MTA vận chuyển thư qua các miền

**Mail Transfer Agent (MTA)** nhận thông điệp và quyết định chuyển tiếp đến hệ thống nào. Khi gửi cho `customer@example.net`, MTA phía gửi thường:

1. Nhận diện miền người nhận `example.net` từ địa chỉ đích.
2. Tra cứu bản ghi **MX (Mail Exchanger)** trong DNS để tìm máy chủ nhận thư cho miền.
3. Kết nối SMTP tới MTA đích, hoặc một máy chủ trung gian theo định tuyến đã thiết lập.
4. Dựa vào phản hồi SMTP để xác định thư được chấp nhận, phải chờ thử lại hay bị từ chối.

Bản ghi MX cho biết **đích nhận thư cấp miền**, không phải đường dẫn thư mục cá nhân. SMTP giữa các MTA thường dùng **cổng 25**. MSA và MTA có thể là hai dịch vụ riêng hoặc cùng nằm trong một hệ thống.

MTA thường có **queue** (hàng đợi). Khi đích lỗi tạm thời, chẳng hạn không kết nối được hoặc trả mã SMTP nhóm `4xx`, MTA có thể chờ và gửi lại theo chính sách. Lỗi vĩnh viễn, thường thuộc nhóm `5xx`, hoặc quá hạn retry có thể dẫn tới **bounce / Delivery Status Notification (DSN)**.

Ví dụ, Postfix và Exim có thể đảm nhiệm chức năng MTA; các dịch vụ SMTP được quản lý cũng thực hiện vai trò vận chuyển này dù người dùng không vận hành máy chủ.

**Phân biệt cốt lõi:** MSA nhận thư *từ client để gửi đi*; MTA xử lý *việc vận chuyển giữa các hệ thống email*. Việc một máy chủ SMTP phản hồi “accepted” chỉ cho biết nó đã chấp nhận thư ở chặng đó.

## 5. MDA: giao thư cuối cùng

Sau khi MTA của miền nhận chấp nhận thư, hạ tầng nhận phải ánh xạ địa chỉ người nhận tới kho thư. Vai trò này thuộc **Mail Delivery Agent (MDA)** hoặc dịch vụ giao cuối cùng tương đương.

Tùy cấu trúc hệ thống, MDA có thể:

- Ánh xạ địa chỉ nhận, alias và quy tắc chuyển tiếp tới mailbox đích.
- Phối hợp bộ lọc spam, chính sách chặn, cách ly và phân loại.
- Ghi thông điệp cùng metadata vào kho thư, gắn vào Inbox, Spam hoặc thư mục thích hợp.
- Báo kết quả cho hệ thống chuyển phát.

MTA có thể giao thư nội bộ thông qua cơ chế local delivery hoặc **LMTP (Local Mail Transfer Protocol)**. Trong nhiều hệ thống lớn, MDA không xuất hiện như một tiến trình độc lập mang đúng tên này: chức năng delivery được triển khai bằng nhiều dịch vụ.

**MTA trả lời “chuyển tới máy chủ nào?”, MDA trả lời “giao vào hộp thư nào và lưu thế nào?”**. Hộp thư không tồn tại có thể bị phát hiện ngay ở MTA hoặc muộn hơn trong bước local delivery, tùy cách hệ thống được xây dựng.

## 6. Mailbox: kho thư của người nhận

**Mailbox** là kho lưu trữ logic của thư đã giao, thường có các thư mục Inbox, Spam, Sent, Drafts và Trash. Nó có thể lưu cả trạng thái đã đọc, cờ đánh dấu, nhãn và metadata.

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Địa chỉ email** | `customer@example.net` | Danh tính định tuyến mà bên gửi sử dụng |
| **Tài khoản người dùng** | Tài khoản đăng nhập dịch vụ mail | Quyền truy cập tài nguyên email |
| **Mailbox** | Kho thư có Inbox/Spam/… | Nơi lưu thông điệp đã giao và trạng thái của chúng |

Không nên coi địa chỉ email và mailbox là một-một. Nhiều **alias** có thể trỏ về một mailbox; địa chỉ nhóm có thể phân phối cho nhiều người; địa chỉ chuyển tiếp có thể không có mailbox riêng.

**Mailbox khác mail client:** mailbox là nơi lưu trữ; mail client là công cụ truy cập. Đổi điện thoại hoặc ứng dụng đọc thư không mặc nhiên khiến mailbox trên máy chủ biến mất.

## 7. Các giao thức nằm ở chặng nào?

| Giao thức | Kết nối phổ biến | Chức năng | Cổng thường gặp |
| --- | --- | --- | --- |
| **SMTP submission** | Ứng dụng/MUA → MSA | Nộp thư để gửi | 587 (STARTTLS), 465 (TLS từ đầu) |
| **SMTP relay** | MTA → MTA | Chuyển tiếp thư qua máy chủ | 25 |
| **LMTP** | MTA → dịch vụ delivery | Giao thư vào hệ thống lưu trữ | Tùy triển khai |
| **IMAP** | MUA → dịch vụ mailbox | Đọc và đồng bộ thư/thư mục/trạng thái | 143 (có thể STARTTLS), 993 (TLS) |
| **POP3** | MUA → dịch vụ mailbox | Tải thư theo mô hình đơn giản hơn IMAP | 110 (có thể STARTTLS), 995 (TLS) |
| **HTTP(S) API / webmail** | App → provider; trình duyệt → webmail | Nộp thư qua API hoặc sử dụng webmail | Thường 443 |

**SMTP phục vụ gửi/chuyển thư; IMAP và POP3 phục vụ truy cập thư đã lưu.** Spring Mail với `JavaMailSender` chủ yếu hỗ trợ phía gửi.

**STARTTLS** nâng cấp kết nối hiện có sang TLS; **implicit TLS** thiết lập TLS ngay từ lúc kết nối. TLS bảo vệ từng chặng truyền thông tương ứng, không tự bảo đảm mã hóa đầu cuối giữa hai người dùng.

## 8. Hành trình chi tiết của một email

Xét email “Đơn hàng đã xác nhận” từ `orders@shop.example` tới `customer@example.net`.

**Bước 1 – Tạo thư.** Ứng dụng quyết định người nhận, chủ đề, nội dung và có thể thêm HTML/tệp đính kèm. **MIME** hỗ trợ biểu diễn thông điệp đa phần và đính kèm; MIME mô tả định dạng nội dung, không chịu trách nhiệm chuyển phát.

**Bước 2 – Nộp cho MSA.** `JavaMailSender` kết nối máy chủ submission được cấu hình, xác thực nếu được yêu cầu và nộp thư qua SMTP. Nếu submission thành công, máy chủ đó nhận trách nhiệm xử lý tiếp; chưa có bằng chứng email đã tới người nhận.

**Bước 3 – MTA chuyển tiếp.** MTA định tuyến theo địa chỉ nhận, thường dựa trên DNS MX. Thư có thể đi qua nhiều chặng hoặc hàng đợi khi gặp lỗi tạm thời.

**Bước 4 – Hệ thống nhận xử lý.** MTA đích kiểm tra chính sách nhận, địa chỉ, bộ lọc chống spam và các điều kiện khác. Thư có thể được chấp nhận hoặc từ chối.

**Bước 5 – MDA giao thư.** Dịch vụ giao cuối cùng ánh xạ địa chỉ tới mailbox và lưu thư, có thể đưa vào Inbox hay Spam. Nếu không giao được, hệ thống có thể phát sinh phản hồi lỗi hoặc bounce tùy thời điểm phát hiện.

**Bước 6 – Mail client đọc.** Người nhận mở điện thoại, desktop hoặc webmail. Truy cập này có thể qua IMAP/POP3 hoặc API nội bộ và là một quy trình khác với phiên SMTP mà ứng dụng đã thực hiện.

```text
Ứng dụng tạo thông điệp
         |
         v
Nộp tới SMTP server ---- lỗi kết nối/xác thực ---> ứng dụng xử lý lỗi gửi
         |
         v
Máy chủ gửi chấp nhận
         |
         +---- lỗi chuyển tiếp tạm thời ---> queue / retry của MTA
         |
         +---- lỗi vĩnh viễn --------------> bounce / DSN (nếu có)
         |
         v
Hệ thống nhận giao vào mailbox
         |
         v
Người nhận xem qua mail client
```

Do các bước nằm ở nhiều hệ thống, không thể suy ra **đã giao**, **đã vào Inbox**, **đã mở** hoặc **đã đọc** chỉ từ việc một hàm gửi trả về bình thường. Nếu cần theo dõi giao thư, hãy sử dụng trạng thái và sự kiện delivery/bounce do hạ tầng cung cấp.

## 9. SMTP envelope khác header của thông điệp

Trong SMTP có thông tin **envelope** phục vụ định tuyến, còn nội dung email có **message headers** và **body** phục vụ người đọc.

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| SMTP `MAIL FROM` | `bounce@shop.example` | Địa chỉ hoàn trả khi không phát được thư |
| SMTP `RCPT TO` | `customer@example.net` | Địa chỉ người nhận mà SMTP cần giao |
| Header `From:` | `Shop <orders@shop.example>` | Người gửi hiển thị trong email |
| Header `To:` | `customer@example.net` | Người nhận hiển thị trong email |
| Header `Subject:` | `Đơn hàng đã xác nhận` | Tiêu đề |
| Body / MIME parts | Text, HTML, attachment | Nội dung của thư |

Hai nhóm địa chỉ này có liên quan nhưng không phải lúc nào giống nhau. Người nhận **Bcc** có thể nằm trong SMTP envelope mà không xuất hiện trong các header người nhận được hiển thị. Header `Return-Path` thường phản ánh envelope sender sau khi thư được giao.

Ví dụ rút gọn:

```text
SMTP envelope:
  MAIL FROM:<bounce@shop.example>
  RCPT TO:<customer@example.net>

Message:
  From: Shop <orders@shop.example>
  To: customer@example.net
  Subject: Đơn hàng đã xác nhận
  MIME-Version: 1.0
  Content-Type: text/plain; charset=UTF-8

  Đơn hàng của bạn đã được xác nhận.
```

Từ sự khác biệt này, có thể hiểu sơ bộ các cơ chế kiểm tra miền gửi: **SPF** xem máy chủ gửi có được ủy quyền cho danh tính SMTP phù hợp; **DKIM** xác thực chữ ký trên phần thông điệp đã ký; **DMARC** dựa vào kết quả xác thực và sự liên kết miền với header `From` để áp dụng chính sách. Chúng giúp giảm giả mạo nhưng không bảo đảm mọi thư hợp lệ sẽ vào Inbox.

## 10. Spring Framework Mail nằm ở đâu?

```text
Service nghiệp vụ
       |
       | Tạo nội dung, chọn người nhận
       v
JavaMailSender (Spring Framework)
       |
       | Jakarta Mail + cấu hình SMTP
       v
SMTP submission (MSA)
       |
       v
MTA  -->  MDA  -->  Mailbox  -->  Mail client người nhận
```

`JavaMailSender` là API gửi thư của Spring. `SimpleMailMessage` dùng cho thư văn bản đơn giản; `MimeMessage` cùng `MimeMessageHelper` hỗ trợ HTML, nội dung multipart và tệp đính kèm.

### Ví dụ gửi email văn bản bằng Spring Boot

Thêm dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

Trong `application.yml`, với SMTP server hỗ trợ STARTTLS qua 587:

```yaml
spring:
  mail:
    host: ${MAIL_HOST}
    port: ${MAIL_PORT:587}
    username: ${MAIL_USERNAME}
    password: ${MAIL_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    from: ${MAIL_FROM_ADDRESS}
```

Các biến môi trường là thông tin do người triển khai cung cấp. Cấu hình cổng, TLS và xác thực cần phù hợp với nhà cung cấp thực tế; không ghi mật khẩu thật trong source code.

Service sử dụng `JavaMailSender`:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {
    private final JavaMailSender mailSender;
    private final String fromAddress;

    public OrderMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress
    ) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendOrderConfirmed(String recipient, String orderId) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom(fromAddress);
        mail.setTo(recipient);
        mail.setSubject("Đơn hàng đã xác nhận");
        mail.setText("Đơn hàng " + orderId + " đã được xác nhận.");

        mailSender.send(mail);
    }
}
```

Khi `mailSender.send(mail)` hoàn thành không có ngoại lệ, ứng dụng biết việc tương tác với cơ chế gửi được cấu hình đã hoàn tất. Nó **không xác nhận** MDA đã ghi vào Inbox hoặc người dùng đã đọc thư.

Đoạn trên dùng **Spring Boot**, nơi `spring-boot-starter-mail` và cấu hình `spring.mail.*` giúp tạo bean theo cơ chế auto-configuration. Nếu dùng **Spring Framework thuần**, cần khai báo implementation `JavaMailSender` cùng dependency Jakarta Mail và cấu hình bean tương ứng.

### Khi cần HTML và attachment

`SimpleMailMessage` thích hợp cho nội dung text. Với HTML, tạo `MimeMessage`:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendHtml(JavaMailSender sender, String from, String to)
        throws MessagingException {
    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");
    helper.setFrom(from);
    helper.setTo(to);
    helper.setSubject("Chào mừng");
    helper.setText("<h1>Chào mừng!</h1><p>Tài khoản đã tạo.</p>", true);
    sender.send(message);
}
```

Để thêm tệp đính kèm, có thể dùng constructor `MimeMessageHelper` bật chế độ multipart rồi gọi `addAttachment(...)`. Dù nội dung phức tạp hơn, **đường vận chuyển SMTP/MTA/MDA/mailbox không thay đổi**.

## 11. Khi xảy ra lỗi, xem thành phần nào?

| Hiện tượng | Nơi nên kiểm tra | Ý nghĩa |
| --- | --- | --- |
| Không kết nối được SMTP | Ứng dụng ↔ MSA | Host, cổng, mạng, TLS hoặc máy chủ |
| SMTP từ chối xác thực | MSA | Tài khoản, quyền gửi hoặc phương thức xác thực |
| Lệnh gửi thành công nhưng thư chưa thấy | MTA, bộ lọc, MDA và mailbox | Queue, retry, bounce, Spam hoặc chặn phía nhận |
| Báo địa chỉ người nhận không hợp lệ | MTA/MDA phía nhận | Hộp thư không có, sai địa chỉ hoặc bị chính sách chặn |
| Webmail có thư nhưng điện thoại không hiện | Mail client/IMAP/đồng bộ | Sự cố truy cập thư đã lưu |
| Một thông báo được gửi nhiều lần | Ứng dụng và cơ chế retry | Có thể gửi lặp khi thử lại mà thiếu kiểm soát trạng thái |

Nên phân biệt ít nhất hai mốc quan sát: **máy chủ submission đã chấp nhận thư** và **hệ thống phía nhận xác nhận giao hoặc từ chối**. Nếu nhà cung cấp hỗ trợ message ID, delivery event hoặc bounce event, có thể đối chiếu chúng với từng yêu cầu nghiệp vụ.

Khi vận hành thực tế, cần chú ý:

- Giữ thông tin xác thực trong secret hoặc biến môi trường; dùng TLS theo cấu hình do SMTP server hỗ trợ.
- Chỉ dùng địa chỉ gửi đã được cấp quyền; thiết lập SPF/DKIM/DMARC theo hướng dẫn nhà cung cấp.
- Thiết kế retry có giới hạn, chống gửi trùng và theo dõi trạng thái nếu nghiệp vụ đòi hỏi độ tin cậy.
- Cân nhắc hàng đợi nghiệp vụ để request HTTP không bị kéo dài vì SMTP chậm hoặc gián đoạn.
- Tôn trọng giới hạn lưu lượng gửi và chính sách chống spam của dịch vụ email.

## 12. Những nhầm lẫn phổ biến

**“Spring gửi mail tức là Spring là mail server.”** Spring Mail cung cấp API tạo và nộp thư. Hạ tầng MSA/MTA/MDA/mailbox vẫn cần có ở đâu đó.

**“MTA và MDA là một.”** Chúng có thể cùng nằm trong một sản phẩm, nhưng MTA chuyển tiếp giữa hệ thống; MDA giao cuối cùng vào kho thư.

**“Địa chỉ email chính là mailbox.”** Địa chỉ dùng để định tuyến. Alias, nhóm và forwarding có thể khiến nhiều địa chỉ trỏ cùng mailbox hoặc một địa chỉ phân phối tới nhiều đích.

**“SMTP dùng để xem Inbox.”** SMTP phục vụ đường gửi/chuyển thư; đường đọc thường là IMAP/POP3 hoặc dịch vụ webmail.

**“SMTP trả thành công là người nhận đã đọc.”** Phản hồi thành công chỉ xác nhận mức chấp nhận của chặng SMTP tương ứng. Việc nhận, phân loại, hiển thị và đọc là các bước khác.

**“Ứng dụng cần tự kết nối cổng 25 tới mọi máy chủ đích.”** Ứng dụng thông thường nộp thư tới một endpoint submission được ủy quyền; hạ tầng gửi đảm nhiệm việc định tuyến và relay tiếp theo.

## 13. Tình huống tự kiểm tra hiểu bài

**Tình huống A:** Người dùng bấm “Quên mật khẩu”. Spring gọi `send()` thành công nhưng chưa thấy email. Kết luận được gì?

> Ứng dụng đã hoàn tất submission qua cơ chế được cấu hình. Cần kiểm tra tiếp trạng thái chuyển thư của MTA, bounce, bộ lọc phía nhận, Spam và việc đồng bộ mail client. Chưa thể khẳng định mail đã vào Inbox.

**Tình huống B:** Người dùng đổi từ Outlook sang webmail mà vẫn thấy thư. Vì sao?

> Mail client là phương tiện truy cập, còn mailbox thường được lưu ở hệ thống máy chủ. Nhiều client có thể truy cập cùng mailbox.

**Tình huống C:** Miền nhận có MTA hoạt động nhưng địa chỉ người nhận không tồn tại. Ai phát hiện?

> MTA có thể từ chối từ phiên SMTP nếu đã kiểm tra địa chỉ. Ở hệ thống khác, dịch vụ giao cuối cùng/MDA phát hiện sau khi MTA nhận thư, dẫn đến trạng thái lỗi hoặc bounce tùy cơ chế.

## 14. Ghi nhớ theo ranh giới trách nhiệm

Khi phân tích bất kỳ tính năng email nào của Spring, hãy lần lượt hỏi:

1. **Ứng dụng/mail client** tạo email gì, cho ai và nộp ở đâu?
2. **MSA** có chấp nhận yêu cầu gửi và xác thực bên gửi không?
3. **MTA** định tuyến, chuyển tiếp và thử lại bằng cách nào?
4. **MDA** giao thư tới mailbox nào và áp dụng chính sách lưu gì?
5. **Mailbox/mail client** lưu và hiển thị thư cho người nhận thế nào?

Tách được năm ranh giới trên sẽ giúp dùng `JavaMailSender` đúng vai trò và giải thích chính xác sự khác nhau giữa “đã nộp thư”, “đã giao vào mailbox” và “người nhận đã đọc”.
