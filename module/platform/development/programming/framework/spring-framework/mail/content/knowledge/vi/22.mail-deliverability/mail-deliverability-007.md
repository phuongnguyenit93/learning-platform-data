# Địa chỉ bounce và xử lý phản hồi thất bại

## 1. Bounce là gì và tại sao cần xử lý?

Trong hệ thống dùng **Spring Framework Mail**, việc gọi `JavaMailSender.send(...)` thành công không đồng nghĩa email đã tới hộp thư của người nhận. SMTP server mà ứng dụng kết nối có thể chấp nhận message, sau đó quá trình chuyển tiếp hoặc giao tới server đích thất bại. Khi đó, hệ thống thư có thể tạo một **delivery status notification (DSN)**, thường gọi là **bounce** hoặc **non-delivery report (NDR)**.

Ví dụ:

~~~text
OrderService
    |
    v
JavaMailSender
    |
    | SMTP accepted (250)
    v
SMTP relay / email provider
    |
    +--> Receiver MX accepts --> delivery process continues
    |
    +--> Recipient rejected / mailbox unavailable
                     |
                     v
                Bounce / DSN
                     |
                     v
          Bounce mailbox or provider webhook
                     |
                     v
            Application bounce processor
                     |
                     +--> Update delivery status
                     +--> Suppress invalid recipients
                     +--> Decide retry / investigation
                     +--> Update deliverability metrics
~~~

Nếu chỉ dựa vào exception của `JavaMailSender`, ứng dụng thường **không nhìn thấy các lỗi phát sinh sau khi SMTP server ban đầu đã chấp nhận thư**. Không xử lý bounce có thể dẫn đến:

- Tiếp tục gửi nhiều lần tới địa chỉ không tồn tại.
- Tăng tỷ lệ trả thư, giảm uy tín gửi của domain/IP.
- Gửi các thông báo nghiệp vụ quan trọng mà người dùng không nhận được nhưng hệ thống không biết.
- Retry không đúng cách, gửi lặp hoặc gây thêm tải cho mail provider.
- Không phân biệt lỗi tạm thời (mailbox đầy, hệ thống đích đang bận) và lỗi vĩnh viễn (địa chỉ không tồn tại).

Mục tiêu của bài học là thiết kế **địa chỉ nhận bounce**, hiểu nguồn và nội dung phản hồi thất bại, rồi đưa chúng vào hệ thống xử lý trạng thái một cách an toàn, có thể kiểm thử và phù hợp với khả năng của Spring Mail.

> **Giới hạn quan trọng:** Spring Framework Mail cung cấp API gửi email như `JavaMailSender`; nó không tự cung cấp một hệ thống hoàn chỉnh để nhận, xác minh, phân loại và xử lý mọi bounce. Phần nhận DSN qua mailbox hoặc webhook cần được xây dựng/tích hợp riêng.

## 2. Phân biệt gửi thành công và giao thư thành công

Một email đi qua nhiều giai đoạn. Chỉ khi hiểu các giai đoạn này mới đặt tên trạng thái chính xác:

| Giai đoạn | Điều ứng dụng quan sát | Có nghĩa vào inbox chưa? |
| --- | --- | --- |
| Chuẩn bị MIME | Message được tạo hợp lệ | Chưa |
| Kết nối và AUTH với SMTP | Đăng nhập mail server thành công | Chưa |
| SMTP server chấp nhận message | `send(...)` trả về bình thường sau trao đổi SMTP | Chưa |
| Provider/relay tiếp tục chuyển tiếp | Có thể có event `processed`/`queued` | Chưa |
| Server nhận chấp nhận giao thư | Có thể có event `delivered` từ provider | Không bảo đảm vào inbox |
| Bounce/DSN | Một bước giao thư thất bại hoặc bị trì hoãn | Không thành công như dự kiến |
| Mở/đọc email | Tín hiệu theo dõi riêng, nếu có | Không suy ra chỉ từ SMTP/DSN |

Thậm chí event `delivered` của email provider thường chỉ mang nghĩa đã chuyển giao tới hệ thống tiếp nhận ở mức mà provider quan sát được, **không chứng minh người dùng đã nhìn thấy thư trong inbox**. Thư có thể nằm ở spam, folder khác hoặc bị lọc sau khi nhận.

### 2.1. Lỗi đồng bộ khi gọi JavaMailSender

Một SMTP server có thể từ chối ngay trong phiên gửi, ví dụ tại lệnh `RCPT TO`:

~~~text
C: EHLO app.example.com
S: 250-mx.example.net
C: MAIL FROM:<bounces@example.com>
S: 250 2.1.0 OK
C: RCPT TO:<nobody@receiver.example>
S: 550 5.1.1 User unknown
~~~

Ví dụ phản hồi minh họa này xảy ra **trong phiên SMTP của ứng dụng**. `JavaMailSender.send(...)` có thể ném một `MailSendException` với nguyên nhân/provider exception bên trong. Đây là lỗi ứng dụng có thể quan sát ngay, không cần đợi DSN.

### 2.2. Bounce bất đồng bộ sau khi server đã chấp nhận

Trong trường hợp khác:

~~~text
App --> SMTP relay: DATA
Relay --> App: 250 2.0.0 Message accepted
App: JavaMailSender.send(...) returns successfully

Later:
Relay --> Receiver MX: attempt delivery
Receiver MX --> Relay: permanent failure
Relay --> Bounce address: DSN
~~~

App đã hoàn tất lời gọi gửi thành công nhưng sau đó vẫn nhận bounce. Do đó, **trạng thái gửi tới SMTP** và **trạng thái giao thư** cần được theo dõi riêng; không nên cập nhật outbox `SENT` thành `FAILED` một cách mơ hồ nếu không định nghĩa rõ trạng thái nào đang biểu diễn điều gì.

## 3. Bốn địa chỉ dễ bị nhầm lẫn

Khi gửi một email có thể xuất hiện nhiều địa chỉ với chức năng khác nhau:

| Thành phần | Nằm ở đâu? | Dùng để làm gì? | Có phải địa chỉ bounce? |
| --- | --- | --- | --- |
| `From:` | Header RFC 5322 trong message | Địa chỉ người gửi mà người nhận nhìn thấy | Không mặc định |
| `Reply-To:` | Header trong message | Nơi người dùng gửi thư trả lời thông thường | Không mặc định |
| `MAIL FROM` / reverse-path | SMTP **envelope** của phiên gửi | Đích nhận DSN/bounce khi có lỗi, trừ trường hợp reverse-path rỗng hoặc hệ thống xử lý khác | **Thường là có** |
| `Return-Path:` | Header do hệ thống giao thư cuối chèn | Ghi nhận reverse-path của envelope khi giao thư | Phản ánh envelope, không nên tự thêm |

Ví dụ một email:

~~~text
SMTP envelope:
  MAIL FROM:<bounces@bounce.example.com>
  RCPT TO:<lan@receiver.example>

Headers in MIME message:
  From: "Thông báo đơn hàng" <notifications@example.com>
  Reply-To: support@example.com
  To: lan@receiver.example
  Subject: Xác nhận đơn hàng
~~~

Người nhận nhìn thấy `notifications@example.com` là người gửi và có thể reply tới `support@example.com`. Nếu quá trình giao thư thất bại, thông báo DSN có thể gửi về `bounces@bounce.example.com`.

### 3.1. From không phải MAIL FROM

Trong Spring:

~~~java
helper.setFrom("notifications@example.com");
~~~

là cách đặt **header From**. API này không có nghĩa ứng dụng đã cấu hình địa chỉ envelope bounce. SMTP envelope `MAIL FROM` có thể được quyết định bởi thuộc tính transport, tài khoản SMTP hoặc chính sách của mail provider.

### 3.2. Reply-To không phải địa chỉ nhận bounce

~~~java
helper.setReplyTo("support@example.com");
~~~

cho biết người dùng nên gửi phản hồi thông thường tới bộ phận hỗ trợ. Nó **không buộc SMTP server gửi DSN tới địa chỉ đó**. Dùng `Reply-To` để thay đổi nơi nhận bounce là một nhầm lẫn phổ biến.

### 3.3. Không tự ghi đè Return-Path header

Không nên cố đặt:

~~~java
// Không dùng như cách cấu hình bounce.
message.setHeader("Return-Path", "<bounces@bounce.example.com>");
~~~

`Return-Path` thường được thêm khi thư được giao, dựa trên envelope reverse-path. Header tự đặt có thể bị loại bỏ, ghi đè hoặc khiến việc chẩn đoán khó hiểu. Hãy cấu hình **envelope sender** tại transport hoặc qua email provider thay vì coi `Return-Path` là header tùy ý.

### 3.4. DSN có thể dùng reverse-path rỗng

Theo cơ chế SMTP, một thông báo lỗi giao thư thường được gửi với envelope sender rỗng `MAIL FROM:<>` để tránh việc thông báo lỗi lại tạo một bounce mới. Đây là cơ chế ngăn **bounce loop**.

Không thiết kế worker tự động trả lời mọi bounce bằng một email mới; cách làm đó có thể sinh vòng lặp, đặc biệt khi địa chỉ nhận không tồn tại hoặc thư DSN bị gửi qua nhiều relay.

## 4. Thiết kế địa chỉ bounce

Một địa chỉ bounce phù hợp cần:

- Là địa chỉ hoặc domain được hạ tầng gửi mail/provider hỗ trợ.
- Có nơi nhận và xử lý DSN, qua mailbox hoặc webhook tương đương.
- Không trùng lẫn luồng trả lời của người dùng nếu ứng dụng cần tự động phân loại bounce.
- Dùng domain/subdomain được tổ chức sở hữu và kiểm soát DNS.
- Có quyền truy cập, retention và giám sát phù hợp vì DSN có thể chứa email người nhận hoặc phần nội dung thư gốc.

Ví dụ tách chức năng:

~~~text
notifications@example.com       -> Header From
support@example.com             -> Reply-To
bounces@bounce.example.com      -> SMTP envelope MAIL FROM
~~~

Địa chỉ `bounces@bounce.example.com` chỉ có ích nếu mailbox, route hoặc provider thật sự có thể tiếp nhận và xử lý các phản hồi tương ứng. **Tạo một chuỗi email không tự sinh mailbox hay MX record**.

### 4.1. Dùng subdomain chuyên biệt

Subdomain như `bounce.example.com` giúp phân tách hạ tầng bounce khỏi mailbox trao đổi thông thường của tổ chức. Cách này có thể giúp:

- Định tuyến DSN vào hệ thống chuyên trách.
- Thiết lập MX/CNAME/TXT theo yêu cầu của provider.
- Quản lý DNS/SPF alignment và giám sát sender reputation.
- Giới hạn quyền truy cập vào dữ liệu bounce.

Subdomain bounce phải được cấu hình theo hướng dẫn của SMTP relay/email provider. Một số nhà cung cấp **tự viết lại envelope sender** và yêu cầu custom return-path/bounce domain theo giao diện DNS của họ; khi đó đặt `mail.smtp.from` ở ứng dụng có thể không tạo đúng Return-Path cuối cùng nếu provider override.

### 4.2. Một địa chỉ chung hay một alias cho mỗi delivery?

**Địa chỉ chung:**

~~~text
bounces@bounce.example.com
~~~

Mọi DSN đến cùng một mailbox. Processor phải tìm delivery tương ứng từ thông tin message gốc, recipient, provider ID hoặc metadata liên quan.

**Alias động cho từng lần gửi (VERP-like):**

~~~text
bounces+e7f4a2@bounce.example.com
bounces+9d103c@bounce.example.com
~~~

Phần token giúp tìm đúng delivery mà không cần dựa duy nhất vào subject/recipient. Mô hình này gần với **Variable Envelope Return Path (VERP)** và rất hữu ích khi hệ thống gửi số lượng lớn.

Tuy nhiên:

- Hạ tầng phải hỗ trợ plus-addressing hoặc catch-all/route nhận alias tương ứng.
- Token nên là định danh opaque ngẫu nhiên, không nhúng địa chỉ email hoặc PII trực tiếp.
- Cần validate token và liên kết nó tới delivery ID trong database.
- Không tin mọi DSN mang token: attacker có thể tự tạo email gửi tới địa chỉ bounce, vì vậy cần kiểm tra nguồn/độ tin cậy và policy trước khi suppression.
- Giữ token trong giới hạn độ dài/charset hợp lệ của SMTP local-part.

Với provider hỗ trợ custom return-path và webhook chính thức, provider event ID hoặc message ID có thể đóng vai trò correlation thay vì tự triển khai toàn bộ VERP.

## 5. Cấu hình envelope sender trong Spring Framework Mail

Khi dùng Spring Boot với Jakarta Mail SMTP transport, thuộc tính `mail.smtp.from` có thể xác định envelope sender được transport dùng cho `MAIL FROM`, khác với header `From` do `MimeMessageHelper` thiết lập.

Ví dụ cấu hình cho một địa chỉ bounce dùng chung:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.from]": bounces@bounce.example.com
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
~~~

Cú pháp ngoặc vuông trong map property giúp giữ nguyên key có dấu chấm khi Spring Boot bind `spring.mail.properties`. Địa chỉ và miền ở ví dụ là dữ liệu giả; production phải sử dụng miền đã được cấu hình/ủy quyền thật sự ở SMTP provider.

Trong code gửi:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class OrderMailer {

    private final JavaMailSender mailSender;

    public OrderMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(
            String recipient, String subject, String plainText,
            String htmlText) throws MessagingException {

        MimeMessage mimeMessage = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(mimeMessage, true, "UTF-8");

        helper.setFrom("notifications@example.com");
        helper.setReplyTo("support@example.com");
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(plainText, htmlText);

        mailSender.send(mimeMessage);
    }
}
~~~

Đây là ví dụ cấu hình **một envelope sender cố định cho toàn ứng dụng**. `helper.setFrom` và `helper.setReplyTo` chỉ đặt header tương ứng; `mail.smtp.from` được SMTP transport dùng khi gửi.

### 5.1. Không sửa Session properties dùng chung theo từng request

Nếu muốn dùng alias bounce riêng cho từng delivery, không nên làm như sau với một bean singleton:

~~~java
// Không an toàn trong ứng dụng gửi đồng thời.
javaMailSenderImpl.getJavaMailProperties().put(
        "mail.smtp.from", "bounces+tokenA@bounce.example.com");
mailSender.send(messageA);
~~~

Nếu hai request thay cùng property, message A có thể bị gửi với envelope sender của message B. Cần dùng giải pháp **per-message** do SMTP provider/API hỗ trợ, hoặc thiết kế transport/factory riêng không chia sẻ mutable state. Một số implementation Jakarta Mail có lớp `SMTPMessage` hỗ trợ thiết lập envelope sender riêng cho message, nhưng package và cách tích hợp phụ thuộc implementation/version (ví dụ Eclipse Angus Mail) và cần kiểm tra tài liệu tương ứng.

Nếu SMTP relay quản lý return-path và webhook, thường nên dùng cơ chế **custom bounce domain + event correlation** mà provider hỗ trợ thay vì tự can thiệp vào shared `JavaMailSenderImpl`.

### 5.2. Kiểm tra envelope sender thực tế

Không chỉ nhìn source code hoặc header `From`. Để xác định đường bounce:

1. Gửi một thư kiểm thử tới mail server/provider được phép.
2. Xác nhận SMTP transport sử dụng reverse-path mà hạ tầng cho phép.
3. Kiểm tra Return-Path khi email được giao, nếu môi trường kiểm thử cung cấp.
4. Tạo tình huống thất bại giả lập và xác nhận bounce được chuyển về kênh thu thập phù hợp.
5. Nếu provider override envelope sender, cấu hình custom return-path/bounce domain trong chính provider.

Không dùng địa chỉ thật của người khác để tạo bounce thử nghiệm. Dùng mailbox hoặc SMTP sink/test environment có quyền kiểm soát.

## 6. Delivery Status Notification (DSN) hoạt động như thế nào?

DSN là cơ chế thông báo tình trạng giao thư của hệ thống mail. Khi một MTA không thể giao message, nó có thể gửi một thông báo lỗi tới **reverse-path của envelope** của message gốc.

Luồng điển hình:

~~~text
SMTP message gốc
  MAIL FROM: bounces@bounce.example.com
  RCPT TO: invalid@receiver.example
          |
          v
Relay accepts message
          |
          v
Later delivery fails
          |
          v
MTA generates DSN
  MAIL FROM: <>      (null reverse-path)
  RCPT TO: bounces@bounce.example.com
          |
          v
Bounce mailbox / inbound handler
~~~

DSN có thể mô tả:

- **Failed:** Giao thư thất bại cuối cùng.
- **Delayed:** Giao thư đang bị trì hoãn, MTA có thể tiếp tục thử.
- **Delivered:** Có thông tin về giao thư thành công theo phạm vi DSN hỗ trợ.
- **Relayed/Expanded:** MTA đã chuyển tiếp hoặc mở rộng danh sách người nhận.

Không phải mọi nhà cung cấp đều gửi một DSN theo cùng hình thức. Có provider thông báo qua webhook; có provider cung cấp dashboard và API event; có hệ thống nhận không tạo phản hồi đầy đủ. Vì vậy, xử lý bounce phải hỗ trợ **thiếu thông tin, dữ liệu không chuẩn và kết quả chưa chắc chắn**.

### 6.1. DSN định dạng machine-readable

Theo các quy ước MIME/DSN, một thông báo chuẩn thường là `multipart/report`, có một phần thông tin cho người đọc và một phần `message/delivery-status` cho máy xử lý.

Ví dụ giản lược:

~~~text
Content-Type: multipart/report;
    report-type=delivery-status; boundary="dsn-boundary"

--dsn-boundary
Content-Type: text/plain; charset=UTF-8

Delivery failed for one or more recipients.

--dsn-boundary
Content-Type: message/delivery-status

Reporting-MTA: dns; mx.sender.example
Arrival-Date: Thu, 12 Nov 2026 08:30:00 +0000

Final-Recipient: rfc822; invalid@receiver.example
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown

--dsn-boundary--
~~~

Đây là **đoạn minh họa rút gọn**: boundary, header và nội dung gốc có thể khác. Một DSN thực tế có thể chứa nhiều recipient block và một phần message gốc/headers, hoặc provider có thể gửi phản hồi dạng khác.

### 6.2. Những trường DSN quan trọng

| Trường | Ý nghĩa |
| --- | --- |
| `Reporting-MTA` | Mail transfer agent tạo thông báo |
| `Original-Envelope-Id` | Mã envelope nếu hệ thống SMTP/DSN hỗ trợ và giữ lại |
| `Original-Recipient` | Người nhận ban đầu, nếu có |
| `Final-Recipient` | Địa chỉ người nhận mà trạng thái áp dụng |
| `Action` | `failed`, `delayed`, `delivered`, `relayed` hoặc `expanded` |
| `Status` | Enhanced mail status code, ví dụ `5.1.1` |
| `Diagnostic-Code` | Chi tiết từ transport/provider, ví dụ SMTP `550` |
| `Last-Attempt-Date` | Thời điểm MTA thử giao thư gần nhất, nếu có |
| `Will-Retry-Until` | Thời điểm cuối MTA dự kiến thử lại, nếu có |

`Final-Recipient` và `Action` đặc biệt quan trọng khi một message có nhiều recipient: **một DSN có thể chỉ báo lỗi một số người nhận**, trong khi người khác không có lỗi hoặc đã được giao.

Không nên dùng `Subject` hoặc `From` của DSN làm khóa duy nhất để xác định message gốc; những trường đó không có tính duy nhất và có thể bị giả mạo.

### 6.3. Request DSN trên SMTP không bảo đảm sẽ nhận DSN

Một số Jakarta Mail SMTP implementation hỗ trợ các property để yêu cầu DSN khi server công bố extension liên quan:

~~~yaml
spring:
  mail:
    properties:
      "[mail.smtp.dsn.notify]": FAILURE,DELAY
      "[mail.smtp.dsn.ret]": HDRS
~~~

Trong các implementation hỗ trợ, `mail.smtp.dsn.notify` yêu cầu thông báo cho các kết quả nhất định, còn `mail.smtp.dsn.ret` chọn mức nội dung message gốc được trả lại, chẳng hạn `HDRS` hoặc `FULL`. Giá trị thực tế và cách áp dụng cần đối chiếu implementation SMTP đang dùng.

Giới hạn quan trọng:

1. Mail server phải hỗ trợ extension DSN tương ứng.
2. Relay/provider có thể bỏ qua, sửa hoặc giới hạn yêu cầu.
3. Không phải failure nào cũng sinh một thông báo có thể phân tích.
4. `notify=FAILURE,DELAY` không buộc server phải gửi webhook cho ứng dụng.
5. Trả lại `FULL` có thể đưa nguyên nội dung email chứa dữ liệu nhạy cảm vào DSN; thường nên tránh nếu không thật sự cần.

Tham số DSN chỉ là một **yêu cầu giao thức**, không phải cam kết deliverability. Nếu cần theo dõi đáng tin cậy theo event, ưu tiên tích hợp API/webhook chính thức của provider khi khả dụng.

## 7. Enhanced status code và cách phân loại bounce

DSN và phản hồi SMTP có thể chứa mã trạng thái:

- SMTP basic reply code: ví dụ `421`, `450`, `550`.
- Enhanced status code: ví dụ `4.2.2`, `5.1.1` hoặc `5.7.1`.

Enhanced status code có dạng `class.subject.detail`. Chữ số đầu thường mô tả nhóm:

| Nhóm | Ý nghĩa chung | Gợi ý xử lý |
| --- | --- | --- |
| `2.x.x` | Thành công | Ghi nhận event tương ứng nếu được xác minh |
| `4.x.x` | Lỗi tạm thời | Xem provider retry và chính sách soft bounce |
| `5.x.x` | Lỗi vĩnh viễn | Cân nhắc hard bounce/suppression hoặc yêu cầu sửa dữ liệu |

Một số mã thường gặp:

| Ví dụ | Diễn giải thường gặp | Phân loại ban đầu |
| --- | --- | --- |
| `5.1.1` | Địa chỉ mailbox đích không tồn tại hoặc sai | Hard bounce |
| `5.1.2` | Hệ thống/domain đích không hợp lệ trong bối cảnh giao thư | Permanent; cần kiểm tra địa chỉ |
| `4.2.2` | Mailbox đầy hoặc vượt giới hạn tạm thời | Soft bounce |
| `5.2.2` | Mailbox đầy nhưng được báo là lỗi vĩnh viễn | Cần policy riêng; không coi mọi “mailbox full” đều transient |
| `4.4.1` | Không nhận được câu trả lời từ host đích | Transient network/delivery |
| `5.4.4` | Không tìm được đường định tuyến tới đích | Permanent routing issue |
| `5.7.1` | Giao thư không được phép hoặc bị từ chối theo policy | Có thể cần điều tra authentication/reputation |

Các mô tả trên là **gợi ý theo mã**, không bảo đảm mọi provider dùng cùng mức chi tiết hoặc cùng từ ngữ. Một số bounce chứa message tự do hoặc mã không chuẩn; cần giữ raw evidence ở nơi an toàn khi điều tra nhưng chỉ lưu error code đã chuẩn hóa trong delivery state.

### 7.1. Hard bounce

**Hard bounce** thường là thất bại được đánh giá là vĩnh viễn đối với địa chỉ hoặc điều kiện giao thư hiện tại, ví dụ:

- Mailbox không tồn tại.
- Domain đích không hợp lệ.
- Người nhận bị từ chối vĩnh viễn.
- Một chính sách provider ngăn giao thư và cần thay đổi điều kiện trước khi thử lại.

Với địa chỉ chắc chắn không tồn tại, tiếp tục gửi cùng nội dung nhiều lần thường làm tăng tỷ lệ bounce, ảnh hưởng uy tín gửi và gây lãng phí tài nguyên. Một hệ thống deliverability thường **suppress** địa chỉ này cho các lượt gửi tiếp theo cho tới khi được sửa hoặc xác minh lại.

Không phải mọi `5xx` đều đồng nghĩa “địa chỉ hỏng vĩnh viễn”. Ví dụ `5.7.1` có thể là vấn đề domain authentication hoặc policy của sender; cần phân tích nguyên nhân và phạm vi ảnh hưởng trước khi vô hiệu hóa hàng loạt người nhận.

### 7.2. Soft bounce

**Soft bounce** thường chỉ một điều kiện tạm thời:

- Hộp thư đầy.
- Server đích tạm thời không phản hồi.
- Tạm giới hạn tốc độ hoặc áp dụng greylisting.
- Sự cố định tuyến hoặc mạng có thể tự phục hồi.

Đôi khi provider tiếp tục retry sau khi báo `delayed` mà không cần ứng dụng gửi lại. Nếu ứng dụng cũng tạo một mail mới ngay khi nhận thông báo tạm thời, người nhận có thể nhận trùng khi provider giao thành công thư ban đầu.

Vì vậy, cần phân biệt:

- **Delay event:** message vẫn đang được relay/provider giữ để retry.
- **Final soft bounce:** provider đã ngừng cố giao message sau các lần thử và báo không giao được.
- **Temporary SMTP rejection trước acceptance:** ứng dụng chưa nộp được message, có thể retry từ outbox nếu kết quả chắc chắn.

Không tự động biến mọi `4.x.x` thành lệnh gửi lại ngay từ ứng dụng.

### 7.3. Complaint không giống bounce

**Spam complaint** là tín hiệu người nhận hoặc mailbox provider đánh dấu message là spam. Một số provider chuyển complaint qua feedback loop (FBL) hoặc webhook. Đây không nhất thiết là lỗi giao thư; message có thể đã tới hệ thống nhận.

Complaint cần có chính sách suppression/consent riêng, thường chặt chẽ hơn soft bounce. Không nhét complaint vào cùng một mã `SMTP_550` hoặc coi nó là email chưa gửi.

### 7.4. Unknown và phản hồi không đầy đủ

Một DSN không có `Status` rõ ràng, một thông báo đã bị chuyển tiếp nhiều lớp hoặc một event provider không map được tới delivery nên được đưa vào trạng thái **UNKNOWN/NEEDS_REVIEW** thay vì tự động xóa recipient.

Phân loại sai hard bounce có thể khiến hệ thống ngừng gửi các thông báo quan trọng tới một địa chỉ vẫn hợp lệ. Chính sách an toàn phải ưu tiên tính xác thực nguồn dữ liệu và khả năng đối soát.

## 8. Deliverability và sự liên hệ với SPF, DKIM, DMARC

Địa chỉ bounce không chỉ để nhận DSN. Domain của SMTP envelope sender còn ảnh hưởng đến SPF và kết quả xác thực domain:

| Thành phần | Domain liên quan | Vai trò |
| --- | --- | --- |
| SPF | Domain của envelope `MAIL FROM` (hoặc HELO khi reverse-path rỗng) | Cho biết IP/server nào được phép gửi thay domain đó |
| DKIM | Domain trong chữ ký `d=` | Chữ ký xác thực message headers/body |
| DMARC | Domain hiển thị trong header `From` | Yêu cầu alignment của SPF và/hoặc DKIM, cùng policy domain |
| Reply-To | Domain của địa chỉ trả lời | Không thay thế SPF/DKIM/DMARC alignment |
| Return-Path | Phản ánh envelope sender khi giao | Không nên tự ghi như header tùy ý |

Ví dụ:

~~~text
Header From: notifications@example.com
Envelope MAIL FROM: bounces@bounce.example.com
DKIM d=example.com
~~~

Với DMARC relaxed alignment, subdomain `bounce.example.com` có thể được xem là aligned với domain tổ chức `example.com` nếu SPF pass và các điều kiện alignment được đáp ứng. Chữ ký DKIM có domain aligned với header From cũng có thể giúp DMARC pass. Kết quả thực tế phụ thuộc DNS, domain organizational boundary, chế độ alignment và việc provider thực sự ký/gửi.

**Không chỉ đặt tên subdomain giống nhau rồi giả định SPF pass.** Domain bounce phải có bản ghi SPF/DNS phù hợp với hạ tầng gửi và provider; DKIM phải được cấu hình/ủy quyền đúng. Với custom return-path, hãy làm theo hướng dẫn DNS của provider và kiểm tra kết quả xác thực thực tế.

### 8.1. Đừng thay đổi domain bounce tùy tiện

Nếu thay envelope sender sang một domain chưa được cấu hình SPF/MX/catch-all hoặc provider chưa xác minh quyền sở hữu, ứng dụng có thể:

- Bị SMTP relay từ chối `MAIL FROM`.
- Không nhận được DSN vì bounce domain không định tuyến đúng.
- Tạo SPF/DMARC alignment không mong đợi.
- Khiến báo cáo deliverability khó đối soát do domain thay đổi.

Thay đổi bounce domain nên được quản lý như một thay đổi hạ tầng mail: cấu hình DNS, kiểm tra route, xác thực SPF/DKIM/DMARC và thực hiện rollout có giám sát.

## 9. Hai hướng thu thập bounce: webhook và mailbox

Sau khi địa chỉ bounce đã được cấu hình, ứng dụng cần một **đường nhận phản hồi**. Có hai mô hình thường dùng:

| Tiêu chí | Webhook/API của email provider | Mailbox nhận DSN qua IMAP |
| --- | --- | --- |
| Đường nhận | Provider POST event HTTP(S) | Ứng dụng poll hoặc receive mailbox |
| Định dạng | JSON/event schema riêng provider | Email/MIME, thường `multipart/report` |
| Correlation | Provider message ID, event ID, recipient, metadata | VERP token, original envelope ID, DSN recipient/header |
| Bảo mật nguồn | Chữ ký webhook/token/identity được provider quy định | Mailbox credential; DSN payload vẫn có thể bị giả mạo |
| Độ ổn định định dạng | Theo hợp đồng provider | DSN chuẩn và nhiều biến thể thực tế |
| Vận hành | Endpoint, retry event, kiểm tra signature | Lưu trữ mailbox, UID, polling, MIME parsing |
| Khi nên dùng | Provider hỗ trợ event delivery đáng tin cậy | SMTP relay truyền thống hoặc cần nhận NDR qua mailbox |

Nếu đang dùng một email service có webhook chính thức, tích hợp webhook thường giúp tránh phải tự xử lý hàng loạt biến thể MIME/DSN. Nếu dùng SMTP server tự quản lý và không có webhook, mailbox DSN qua IMAP hoặc một inbound mail gateway có thể phù hợp hơn.

Hai cách đều cần **xác minh nguồn**, correlation, lưu lịch sử, deduplication và xử lý idempotent.

### 9.1. Quy trình webhook của provider

~~~text
Provider detects delivery failure
                |
                v
HTTPS POST to /webhooks/mail-provider
                |
                v
Verify signature / timestamp / replay
                |
                v
Parse provider-specific schema
                |
                v
Normalize to internal delivery event
                |
                v
Persist event idempotently
                |
                v
Update delivery state + suppression policy
                |
                v
Return 2xx after durable receipt
~~~

Webhook có thể được gửi lại nếu provider không nhận được HTTP 2xx hoặc timeout. Do đó **duplicate event là bình thường**. Đừng tự động tăng bounce count hay suppress lại nhiều lần chỉ vì cùng một event được redeliver.

### 9.2. Quy trình mailbox nhận DSN

~~~text
SMTP reverse-path -> bounce mailbox
                         |
                         v
                 IMAPS / inbound gateway
                         |
                         v
                  Read MIME message
                         |
                         v
          Locate message/delivery-status part
                         |
                         v
           Extract recipient/action/status
                         |
                         v
            Match delivery by trusted token
                         |
                         v
             Persist normalized event
                         |
                         v
              Mark processing checkpoint
~~~

Với IMAP, **trạng thái SEEN không nên là checkpoint bền vững duy nhất**: process có thể dừng sau khi mark SEEN nhưng trước khi commit event, hoặc ngược lại. Hãy lưu UID/UIDVALIDITY và trạng thái xử lý trong database, với cơ chế xử lý lại idempotent nếu cần.

## 10. Nhận webhook trong Spring

Spring MVC có thể cung cấp một endpoint để nhận event delivery/bounce từ provider. Khác với các API của `JavaMailSender`, cấu trúc webhook **không chuẩn hóa giữa các nhà cung cấp**, do đó nên viết adapter riêng.

Một interface định nghĩa việc xác thực và chuẩn hóa:

~~~java
package com.example.mail.feedback;

import org.springframework.http.HttpHeaders;
import java.util.List;

public interface ProviderWebhookVerifier {
    boolean verify(byte[] rawBody, HttpHeaders headers);
}

public interface ProviderBounceDecoder {
    List<NormalizedDeliveryEvent> decode(byte[] verifiedBody);
}
~~~

`verify` là nơi thực hiện thuật toán xác minh do provider công bố (ví dụ HMAC hoặc chữ ký bất đối xứng), sử dụng **body nguyên bản**, signature header và timestamp/anti-replay khi có. Không nên tự giả định mọi provider sử dụng cùng một header hoặc cùng công thức ký.

Controller minh họa:

~~~java
package com.example.mail.feedback;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/webhooks/mail-provider")
public class MailProviderWebhookController {

    private final ProviderWebhookVerifier verifier;
    private final ProviderBounceDecoder decoder;
    private final BounceEventIngestService ingestService;

    public MailProviderWebhookController(
            ProviderWebhookVerifier verifier,
            ProviderBounceDecoder decoder,
            BounceEventIngestService ingestService) {
        this.verifier = verifier;
        this.decoder = decoder;
        this.ingestService = ingestService;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Void> receive(
            @RequestBody byte[] rawBody,
            @RequestHeader HttpHeaders headers) {

        if (!verifier.verify(rawBody, headers)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }

        ingestService.persistVerifiedEvents(decoder.decode(rawBody));
        return ResponseEntity.accepted().build();
    }
}
~~~

`BounceEventIngestService` là service ứng dụng được định nghĩa ở các phần dưới, có trách nhiệm **lưu bền vững** event hoặc enqueue vào hàng đợi bền vững trước khi HTTP handler trả mã thành công. Nếu ghi thất bại, hãy trả response lỗi để provider có thể retry theo hợp đồng của họ; không trả 2xx trước khi dữ liệu đã được nhận an toàn.

### 10.1. Các điều kiện bắt buộc của webhook

- Dùng HTTPS; không tiếp nhận event nhạy cảm qua HTTP công khai.
- Xác minh signature/token đúng **hướng dẫn của provider**, không dùng tên miền gọi tới làm bằng chứng đủ.
- Nếu provider ký kèm timestamp, kiểm tra khoảng thời gian và lưu/chặn replay theo cơ chế họ hỗ trợ.
- Không parse rồi serialize lại JSON **trước khi** kiểm tra HMAC trên raw body nếu provider yêu cầu ký theo bytes gốc.
- Giới hạn kích thước request ở gateway/web server trước khi đọc vào memory.
- Giới hạn tốc độ, timeout và số event trong mỗi batch.
- Chỉ dùng danh sách IP như một lớp bổ sung khi provider cung cấp; IP allowlist không thay signature verification.
- Chỉ nhận event type được hỗ trợ; với type không biết, ghi nhận/đưa vào luồng xử lý an toàn.
- Tránh log raw payload vì có thể chứa recipient, subject, message ID hoặc dữ liệu cá nhân.

**Không lấy một webhook bất kỳ có trường `recipient` rồi lập tức cấm gửi đến địa chỉ đó.** Chỉ áp dụng policy sau khi xác minh nguồn, event, correlation và phạm vi tenant/delivery hợp lệ.

### 10.2. Vì sao phải trả 2xx sau khi lưu event?

Nhiều provider gửi lại webhook nếu request timeout hoặc nhận non-2xx. Nếu ứng dụng trả 2xx rồi mới xử lý trong một thread không bền vững, crash có thể làm mất bounce event vĩnh viễn. Vì vậy, một trong hai cách:

1. Lưu event vào database trong transaction rồi trả 2xx.
2. Đưa event đã xác minh vào một durable queue có cơ chế ack trước khi trả 2xx.

Nếu dùng queue có tính chất at-least-once, consumer vẫn phải idempotent. Webhook redelivery và queue redelivery có thể cùng tạo duplicate; deduplication phải được áp dụng ở bước cập nhật trạng thái.

## 11. Nhận DSN từ mailbox bằng Jakarta Mail

Nếu hạ tầng gửi trả bounce vào mailbox, ứng dụng có thể dùng **Jakarta Mail** để kết nối IMAPS hoặc tích hợp với một inbound mail service khác. Spring Framework Mail chủ yếu hỗ trợ gửi; ứng dụng phải tự quản lý việc đọc mail, phân tích MIME và checkpoint.

Ví dụ khung poll mailbox:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.Store;
import java.util.Properties;

public class BounceMailboxPoller {

    public void poll(
            String imapHost,
            String username,
            String password) throws Exception {

        Properties props = new Properties();
        props.put("mail.store.protocol", "imaps");
        props.put("mail.imaps.ssl.checkserveridentity", "true");

        Session session = Session.getInstance(props);
        Store store = null;
        Folder folder = null;

        try {
            store = session.getStore("imaps");
            store.connect(imapHost, username, password);
            folder = store.getFolder("INBOX");
            folder.open(Folder.READ_ONLY);

            for (Message dsn : folder.getMessages()) {
                // Production: dùng IMAP UID/UIDVALIDITY checkpoint,
                // lọc bản ghi chưa xử lý và giới hạn batch.
                // Parse multipart/report + message/delivery-status.
                // Normalize / correlate / persist idempotently.
            }
        } finally {
            if (folder != null && folder.isOpen()) {
                folder.close(false);
            }
            if (store != null && store.isConnected()) {
                store.close();
            }
        }
    }
}
~~~

Đây là **skeleton minh họa**, không phải một poller production hoàn chỉnh: nó không có batching, checkpoint, giới hạn kích thước, phân tích DSN hay rate limit. Password IMAP phải được cấp qua secret manager/config runtime, không hard-code hoặc ghi log. Với mailbox có nhiều thư, không quét lại toàn bộ `getMessages()` trong mỗi chu kỳ; dùng UID và bộ lọc phù hợp.

### 11.1. Parser DSN phải hiểu MIME tree

Một bounce chuẩn có thể chứa:

~~~text
multipart/report
├── text/plain                      human-readable notice
├── message/delivery-status         machine-readable recipient status
└── message/rfc822 or text/rfc822-headers (optional)
~~~

Không nên lấy vài dòng trong body bằng regex tự do rồi coi đó là kết quả đáng tin cậy. Một quy trình parser cần:

1. Xác định `multipart/report` và `report-type=delivery-status` khi có.
2. Tìm phần `message/delivery-status`, kể cả MIME lồng nhiều cấp hợp lệ.
3. Đọc per-message fields và các per-recipient blocks.
4. Chuẩn hóa `Action`, `Status`, `Final-Recipient` và `Diagnostic-Code`.
5. Correlate tới delivery có thật trong hệ thống.
6. Lưu evidence có kiểm soát và trạng thái đã chuẩn hóa.

Nếu cần thư viện parser chuyên dụng theo Jakarta Mail implementation, phải kiểm tra version/package của các phần mở rộng DSN (các package DSN của những implementation có thể khác nhau). Không giả định mọi `message/delivery-status` sẽ được JavaMail tự chuyển thành cùng một object Java ở mọi phiên bản.

### 11.2. Một DSN có thể có nhiều người nhận

Ví dụ:

~~~text
Final-Recipient: rfc822; a@receiver.example
Action: failed
Status: 5.1.1

Final-Recipient: rfc822; b@receiver.example
Action: delayed
Status: 4.2.2
~~~

Không biến cả hai recipient thành một kết quả duy nhất. A có thể cần hard suppression, còn B vẫn đang được MTA thử giao. Điều này là lý do hữu ích để ứng dụng quản lý **một delivery record cho mỗi recipient** thay vì một status cho cả danh sách To/Cc/Bcc.

### 11.3. Tính xác thực của DSN qua mailbox

Nhận được một email có `From: MAILER-DAEMON` hoặc có MIME type `message/delivery-status` **không tự chứng minh sự kiện là thật**. Kẻ tấn công có thể gửi email giả tới bounce mailbox nếu địa chỉ đoán được.

Giảm rủi ro bằng cách:

- Đặt bounce mailbox trên domain/hạ tầng được kiểm soát.
- Ưu tiên provider event có cơ chế xác minh khi có.
- Dùng token correlation opaque trong envelope hoặc ID provider có thể đối soát.
- Đối chiếu delivery ID, recipient, domain và trạng thái đã ghi trong hệ thống.
- Không xử lý event không khớp hoặc nguồn không đủ tin cậy theo đường tự động suppress.
- Giới hạn MIME recursion depth, kích thước message và số recipient blocks để tránh DoS.
- Không mở/ghi đính kèm tùy ý từ DSN xuống filesystem khi không cần thiết.

Nếu không thể xác minh nguồn đủ chắc chắn, đưa event vào hàng chờ điều tra thay vì tự động áp dụng hành động làm gián đoạn liên lạc với người nhận.

## 12. Mô hình dữ liệu: tách outbox gửi và delivery feedback

Trong ứng dụng giao dịch, có thể đã có bảng outbox để theo dõi worker gửi email. Bảng đó thường có trạng thái như `PENDING`, `PROCESSING`, `RETRY`, `SENT` hoặc `FAILED`.

Sau khi lời gọi SMTP thành công, **bounce có thể xuất hiện vài phút hoặc nhiều giờ sau**. Do đó, nếu dùng một cột `status` duy nhất cho cả outbox và deliverability sẽ dễ gây hiểu nhầm:

~~~text
Outbox lifecycle:
PENDING -> PROCESSING -> SENT

Delivery feedback (after SMTP acceptance):
SUBMITTED -> DEFERRED -> RECEIVER_ACCEPTED
                     \-> HARD_BOUNCED / SOFT_BOUNCED
                     \-> UNKNOWN
~~~

Không tự động chuyển outbox từ `SENT` sang `FAILED` khi nhận bounce nếu `SENT` đã được định nghĩa là “SMTP submission hoàn tất”. Thay vào đó, lưu một **delivery status** riêng hoặc một event history, thể hiện các bước sau SMTP.

### 12.1. Một bản ghi delivery cho một người nhận

Ví dụ bảng PostgreSQL:

~~~sql
CREATE TABLE mail_delivery (
    id UUID PRIMARY KEY,
    outbox_id UUID,
    tenant_id UUID NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    template_name VARCHAR(120) NOT NULL,
    envelope_sender VARCHAR(320),
    provider VARCHAR(80),
    provider_message_id VARCHAR(250),
    submit_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    feedback_status VARCHAR(40) NOT NULL DEFAULT 'AWAITING_FEEDBACK',
    smtp_accepted_at TIMESTAMPTZ,
    receiver_accepted_at TIMESTAMPTZ,
    last_feedback_at TIMESTAMPTZ,
    last_bounce_code VARCHAR(30),
    last_bounce_category VARCHAR(40),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_mail_delivery_provider_message
    ON mail_delivery(provider, provider_message_id);

CREATE INDEX ix_mail_delivery_recipient
    ON mail_delivery(tenant_id, recipient);
~~~

`outbox_id` liên kết tác vụ gửi nội bộ, còn `provider_message_id` dùng correlate tới event của nhà cung cấp. Nếu một provider ID đại diện cho message có nhiều người nhận, ID đó **không duy nhất theo delivery**; phải kết hợp recipient hoặc delivery metadata.

Trường `feedback_status` có thể dùng:

| Giá trị | Ý nghĩa |
| --- | --- |
| `AWAITING_FEEDBACK` | Đã nộp cho transport, chưa nhận event sau gửi |
| `DEFERRED` | Provider/MTA đang trì hoãn hoặc tiếp tục retry |
| `RECEIVER_ACCEPTED` | Provider báo phía nhận đã chấp nhận giao thư |
| `HARD_BOUNCED` | Đã xác nhận thất bại vĩnh viễn theo policy |
| `SOFT_BOUNCED` | Đã xác nhận thất bại tạm thời/cuối cùng theo policy |
| `COMPLAINED` | Có phản hồi spam complaint |
| `UNKNOWN` | Không đủ thông tin để quyết định |

Không nhận được event **không chứng minh** giao thư thất bại. Nhiều hệ thống không có delivery receipt đầy đủ, vì vậy `AWAITING_FEEDBACK` có thể tồn tại lâu; cần retention và cách trình bày rõ ràng thay vì tự suy ra `DELIVERED` sau một thời gian.

### 12.2. Event history để đối soát

Lưu các event đến từ provider/mailbox theo kiểu append-only:

~~~sql
CREATE TABLE mail_delivery_feedback_event (
    id UUID PRIMARY KEY,
    delivery_id UUID NOT NULL REFERENCES mail_delivery(id),
    source VARCHAR(80) NOT NULL,
    source_event_id VARCHAR(250) NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    feedback_type VARCHAR(40) NOT NULL,
    enhanced_status VARCHAR(20),
    smtp_reply_code VARCHAR(10),
    safe_reason VARCHAR(300),
    occurred_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ux_mail_feedback_event UNIQUE (
        source, source_event_id, recipient
    )
);

CREATE INDEX ix_mail_feedback_delivery_time
    ON mail_delivery_feedback_event(delivery_id, received_at);
~~~

Schema giả định adapter cung cấp một `source_event_id` có tính ổn định trong phạm vi source. Nếu provider không có event ID, ứng dụng phải định nghĩa cách fingerprint/deduplicate thận trọng; không tự tạo UUID mới cho cùng một event ở mỗi lần webhook retry rồi nghĩ unique constraint sẽ chặn trùng.

Giữ event history cho phép phân tích một chuỗi như:

~~~text
09:00 submitted_to_provider
09:01 deferred (4.2.2 mailbox full)
09:11 deferred (4.2.2 mailbox full)
10:15 receiver_accepted
~~~

Một event `DEFERRED` không đồng nghĩa thất bại cuối. Nếu nhận event thành công sau đó, bản ghi tổng hợp cần cập nhật theo quy tắc thứ tự và độ tin cậy của từng provider.

## 13. Chuẩn hóa event từ nhiều nguồn

Provider A có thể gọi sự kiện `bounce`, provider B phân biệt `temporary_failure` và `permanent_failure`, còn DSN sử dụng `Action: failed` cùng `Status`. Ứng dụng nên chuyển chúng thành một **model chung**, còn giữ raw/provider-specific metadata trong adapter hoặc vùng audit được bảo vệ nếu cần.

~~~java
package com.example.mail.feedback;

import java.time.Instant;
import java.util.UUID;

public enum DeliveryFeedbackType {
    RECEIVER_ACCEPTED,
    DELAYED,
    HARD_BOUNCE,
    SOFT_BOUNCE_FINAL,
    COMPLAINT,
    UNKNOWN
}

public record NormalizedDeliveryEvent(
        String source,
        String sourceEventId,
        UUID deliveryId,
        String recipient,
        DeliveryFeedbackType type,
        String enhancedStatus,
        String smtpReplyCode,
        String safeReason,
        Instant occurredAt) {
}
~~~

Các ví dụ này mô tả **hợp đồng nội bộ**; trong Java, `public enum` và `public record` phải nằm ở file tương ứng theo quy tắc ngôn ngữ.

Nguyên tắc normalization:

1. Xác định event type thực sự theo schema/provider, không chỉ tìm chữ “bounce” trong text.
2. Nếu có action `delayed`, không chuyển ngay thành hard bounce.
3. Nếu event là permanent failure `5.1.1`, có thể phân loại hard bounce sau khi validate source và recipient.
4. Nếu là policy block `5.7.1`, không mặc định người nhận không tồn tại; xem phạm vi lỗi sender/domain.
5. Giữ mã enhanced status và basic SMTP code nếu dữ liệu nguồn có.
6. Ghi timestamp của provider khi có, cùng timestamp nhận event do hệ thống ghi.
7. Không lưu raw diagnostic message vào cột hiển thị công khai; chuyển sang `safeReason` đã được chuẩn hóa.
8. Nếu không correlate được delivery hoặc recipient, đưa vào hàng `UNMATCHED/NEEDS_REVIEW` thay vì cập nhật nhầm người nhận.

### 13.1. Correlation là điều kiện bắt buộc

Các khóa có thể dùng:

- Delivery ID opaque đã nhúng trong VERP token.
- Provider message ID kèm đúng recipient.
- Original envelope ID khi provider/MTA hỗ trợ.
- Metadata/custom arguments của provider nếu API hỗ trợ và bảo đảm round-trip.

`Message-ID` trong MIME header có thể hữu ích cho truy vết nhưng không phải lúc nào cũng duy nhất theo recipient và có thể xuất hiện trong DSN đã chuyển tiếp. Đừng coi một giá trị header đơn lẻ là bằng chứng đủ để xóa địa chỉ khỏi danh sách gửi.

### 13.2. Không tin email nhận trong DSN nếu không map được delivery

Giả sử một DSN tự khai:

~~~text
Final-Recipient: rfc822; customer@example.net
Status: 5.1.1
~~~

Nếu ứng dụng chưa từng gửi message tương ứng cho `customer@example.net` hoặc không xác minh được nguồn DSN, không được lập tức chặn địa chỉ này. Một attacker có thể gửi DSN giả nhằm làm gián đoạn thông báo của người khác.

Ngay cả khi recipient tồn tại trong database, phải đối chiếu **delivery cụ thể, tenant, thời gian và kênh thu thập được tin cậy**.

## 14. Xử lý idempotent và transaction khi nhận event

Webhook và consumer đều có thể redeliver. Một bounce được gửi hai lần không được làm tăng counter hoặc áp dụng suppression hai lần.

Luồng cập nhật an toàn:

~~~text
Verify + normalize event
          |
          v
Start database transaction
          |
          +--> Validate delivery + recipient + tenant
          |
          +--> Insert event with unique event key
          |      |
          |      +--> Duplicate? stop, no side effect
          |
          +--> Update delivery feedback projection
          |
          +--> Update suppression if policy says so
          |
          v
Commit transaction
          |
          v
Ack provider / mailbox checkpoint
~~~

Ví dụ service dùng repository abstraction:

~~~java
package com.example.mail.feedback;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BounceEventIngestService {

    private final DeliveryRepository deliveries;
    private final FeedbackEventRepository events;
    private final SuppressionPolicyService suppressions;

    public BounceEventIngestService(
            DeliveryRepository deliveries,
            FeedbackEventRepository events,
            SuppressionPolicyService suppressions) {
        this.deliveries = deliveries;
        this.events = events;
        this.suppressions = suppressions;
    }

    @Transactional
    public void persistVerifiedEvents(
            java.util.List<NormalizedDeliveryEvent> input) {

        for (NormalizedDeliveryEvent event : input) {
            DeliveryRecord delivery =
                    deliveries.lockById(event.deliveryId())
                            .orElseThrow(
                                    () -> new UnknownDeliveryException(
                                            event.deliveryId()));

            if (!delivery.recipient()
                    .equalsIgnoreCase(event.recipient())) {
                throw new InvalidDeliveryFeedbackException(
                        "Event recipient does not match delivery");
            }

            // DB unique constraint ngăn cùng một event
            // tạo side effect lặp lại.
            if (!events.insertIfAbsent(event)) {
                continue;
            }

            deliveries.applyFeedback(delivery, event);

            if (event.type() == DeliveryFeedbackType.HARD_BOUNCE) {
                suppressions.applyVerifiedHardBounce(
                        delivery.tenantId(),
                        delivery.recipient(),
                        event);
            }
        }
    }
}
~~~

Các interface `DeliveryRepository`, `FeedbackEventRepository`, `SuppressionPolicyService` và exception ứng dụng là **abstraction minh họa**, không phải API có sẵn của Spring Mail. `insertIfAbsent` cần được thực hiện atomically ở database; không chỉ `existsById` rồi `save` vì hai request song song có thể qua được cùng lúc.

Một implementation production cần định nghĩa thêm policy khi event không khớp, khi nhận batch có cả event hợp lệ và không hợp lệ, cùng quy tắc cập nhật trạng thái nếu event tới trễ hoặc ngược thứ tự. Nếu dùng một transaction cho toàn batch, một event lỗi có thể rollback cả batch; có thể xử lý từng event trong transaction riêng hoặc đưa event bất thường vào dead-letter để không chặn các event khác.

### 14.1. Chống out-of-order event

Provider có thể gửi lại hoặc giao event không đúng thứ tự phát sinh:

~~~text
Provider emits: DEFERRED -> RECEIVER_ACCEPTED
Application receives: RECEIVER_ACCEPTED -> DEFERRED
~~~

Nếu worker cập nhật `feedback_status` theo thứ tự HTTP request đến, trạng thái cuối có thể bị lùi về `DEFERRED` dù đã nhận bằng chứng phía nhận chấp nhận.

Hãy định nghĩa **state transition policy**:

- `DEFERRED` không ghi đè `RECEIVER_ACCEPTED` chỉ vì đến sau.
- `HARD_BOUNCED` và `COMPLAINED` là event quan trọng, cần giữ trong history kể cả khi projection hiện tại khác.
- Nếu provider gửi các event mâu thuẫn, giữ toàn bộ timeline và đánh dấu để đối soát, không tùy tiện bỏ một event.
- Sử dụng provider event timestamp khi có, nhưng không tin timestamp từ nguồn chưa xác minh và không giả định đồng hồ các hệ thống luôn đồng bộ.

Chính sách sắp thứ tự cần gắn với **định nghĩa của provider** và từng delivery. Một priority cố định áp dụng cho mọi provider có thể không đúng với các trường hợp delayed, bounce cuối và delivered.

### 14.2. Không xử lý bounce của một recipient thành lỗi của cả batch

Nếu message được gửi tới nhiều người nhận, SMTP response hoặc DSN có thể chỉ ra:

~~~text
a@receiver.example -> delivered
b@receiver.example -> hard bounced
c@receiver.example -> delayed
~~~

Chỉ cập nhật từng `mail_delivery` tương ứng; không set toàn bộ sự kiện giao dịch thành `FAILED` vì một địa chỉ bị trả thư. Với email giao dịch quan trọng, **một delivery row cho một recipient** là kiến trúc thường dễ audit và retry nhất.

## 15. Chính sách suppression: khi nào ngừng gửi?

**Suppression list** là danh sách những địa chỉ hoặc identity mà hệ thống không nên tiếp tục gửi theo một phạm vi chính sách nhất định. Nguồn tạo suppression có thể là:

- Hard bounce đã được xác minh.
- Spam complaint.
- Unsubscribe của email marketing.
- Một chuỗi soft bounce vượt ngưỡng trong một khoảng thời gian.
- Quyết định của người dùng, administrator hoặc hệ thống chống lạm dụng.

Không nên đặt mọi lý do vào một cờ `isBlocked` duy nhất. Hãy lưu **nguồn, loại và phạm vi** để hệ thống biết vì sao một recipient bị suppress và khi nào được khôi phục.

Ví dụ:

~~~sql
CREATE TABLE mail_suppression (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    reason VARCHAR(40) NOT NULL,
    source_delivery_id UUID,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    CONSTRAINT ux_mail_suppression UNIQUE (
        tenant_id, recipient, reason
    )
);
~~~

Schema chỉ mang tính minh họa. Nếu sản phẩm phân biệt marketing và transactional email, cần thêm kênh/phạm vi hoặc một policy layer khác. Một hard bounce do mailbox không tồn tại có thể ảnh hưởng mọi loại email gửi tới địa chỉ đó, còn unsubscribe marketing không nhất thiết được phép chặn một thông báo bảo mật bắt buộc.

### 15.1. Hard bounce: chặn địa chỉ không hợp lệ

Với bằng chứng có độ tin cậy cao rằng mailbox không tồn tại (ví dụ enhanced status `5.1.1`, event verified và map đúng delivery), có thể:

1. Ghi event `HARD_BOUNCE`.
2. Cập nhật `mail_delivery.feedback_status = HARD_BOUNCED`.
3. Tạo hoặc cập nhật suppression record theo phạm vi.
4. Ghi timestamp và nguồn sự kiện để audit.
5. Với tài khoản người dùng quan trọng, yêu cầu xác minh hoặc cung cấp địa chỉ email mới qua một kênh đáng tin cậy.

Không gửi lại ngay tới địa chỉ đã xác nhận sai chỉ để “test xem đã hoạt động chưa”. Nếu người dùng sửa email hoặc xác minh quyền sở hữu mailbox, có thể gỡ suppression theo quy trình đã định nghĩa.

### 15.2. Soft bounce: theo dõi ngưỡng và thời gian

Một soft bounce đơn lẻ không phải bằng chứng recipient không còn tồn tại. Có thể dùng chính sách:

~~~text
Nếu nhận DELAYED event:
  -> Chờ provider tiếp tục retry; không gửi mới ngay.

Nếu nhận FINAL SOFT BOUNCE:
  -> Ghi failure cho delivery hiện tại.
  -> Tăng điểm/đếm soft bounce theo recipient trong time window.
  -> Chỉ tạm suppress nếu vượt ngưỡng đã định.
  -> Cho phép re-evaluate khi đã hết thời gian chờ.
~~~

Ví dụ chính sách giả định: ba final soft bounce trong bảy ngày sẽ tạm ngừng gửi marketing tới địa chỉ đó trong 48 giờ. Đây chỉ là **ví dụ cấu hình nghiệp vụ**, không phải chuẩn chung. Ngưỡng phải được cân nhắc theo volume, provider, loại email và rủi ro giao thư.

Đừng đếm mỗi webhook `delayed` hoặc mỗi attempt nội bộ như một final soft bounce; một provider có thể phát hàng chục event trì hoãn cho cùng một message đang được retry.

### 15.3. Complaint và consent

Spam complaint và unsubscribe thường liên quan tới sự đồng ý nhận email. Một complaint đã được xác minh có thể yêu cầu ngừng email marketing ngay, theo policy và nghĩa vụ pháp lý áp dụng.

Không dùng chức năng `Reply-To` hay địa chỉ bounce để thay thế cơ chế unsubscribe. Bounce phản ánh **lỗi giao thư**; unsubscribe phản ánh **ý muốn của người nhận**. Chúng có thể cùng ảnh hưởng suppression nhưng là hai loại tín hiệu khác nhau.

### 15.4. Cân bằng suppression với email giao dịch quan trọng

Với email xác thực tài khoản, hóa đơn hoặc thông báo bảo mật, không nên đơn giản bỏ qua việc gửi và coi tác vụ thành công khi recipient đang bị suppress.

Có thể:

- Đánh dấu delivery là `SUPPRESSED` hoặc `NOT_ATTEMPTED` với reason rõ ràng.
- Thông báo trong tài khoản rằng địa chỉ email cần xác minh/sửa.
- Yêu cầu cập nhật địa chỉ qua luồng bảo mật phù hợp.
- Sử dụng kênh thay thế được người dùng cho phép khi cần.
- Giữ audit rằng hệ thống **không thử gửi** vì suppression, thay vì báo SMTP accepted.

Đối với địa chỉ cần nhận thông báo theo nghĩa vụ vận hành/pháp lý, policy phải được thảo luận với chủ sở hữu sản phẩm và bộ phận tuân thủ; không mặc định bật một rule chặn toàn bộ loại email.

## 16. Retry và bounce: tránh hai hệ thống retry chồng nhau

Ở thời điểm gọi SMTP, ứng dụng có thể cần retry các lỗi tạm thời **trước khi message được chấp nhận**. Nhưng sau khi message được provider chấp nhận, provider có thể tự retry việc giao tới mailbox đích.

Hai vòng retry có ranh giới khác nhau:

~~~text
Application -> SMTP provider
    |
    +--> Connection refused / reject before acceptance
    |       |
    |       v
    |   Application outbox retry
    |
    +--> 250 message accepted
            |
            v
       Provider attempts delivery
            |
            +--> temporary deferral
            |       |
            |       v
            |   Provider retries internally
            |
            +--> final failure
                    |
                    v
                Bounce / DSN
~~~

**Không tạo một message mới chỉ vì provider phát event `DEFERRED`.** Làm vậy sẽ khiến cùng một thông báo tồn tại ở cả hàng đợi của provider lẫn hàng đợi ứng dụng.

### 16.1. Retry lỗi đồng bộ

Khi `JavaMailSender.send(...)` ném `MailException`, có thể phân loại:

| Tình huống | Quyết định thường phù hợp |
| --- | --- |
| Không mở được kết nối tới SMTP | Retry có backoff và giới hạn |
| SMTP từ chối AUTH | Cảnh báo cấu hình; dừng retry nhanh |
| Địa chỉ recipient sai và bị từ chối rõ ràng | Sửa dữ liệu hoặc suppression, không retry nguyên trạng |
| SMTP provider tạm bận/throttle | Retry theo provider guidance/rate limit |
| Timeout sau khi DATA đã được gửi | Kết quả có thể không rõ; policy duplicate/UNKNOWN |

Một timeout không phải lúc nào cũng chứng minh provider chưa chấp nhận message; cần xem giai đoạn SMTP và nested exception.

### 16.2. Retry sau final bounce

Khi provider thông báo một **final soft bounce**, việc gửi lại một message mới có thể được phép sau một thời gian chờ tùy nghiệp vụ. Nhưng:

- Phải chắc rằng đây là event final, không chỉ tạm hoãn.
- Không retry nếu email chứa token đã hết hạn.
- Không vượt quá giới hạn số lần gửi hay quota provider.
- Kiểm tra suppression list trước khi tạo delivery mới.
- Giữ một delivery ID/event key riêng cho lần phát lại hợp lệ và audit liên hệ tới message cũ.

Với hard bounce đã xác minh, gửi lại cùng địa chỉ ngay thường không có ích. Với complaint, retry marketing có thể trái với mong muốn người nhận và chính sách gửi.

### 16.3. Cửa sổ gửi trùng của transactional outbox

Ngay cả trước bounce, một hệ thống outbox cũng có cửa sổ lỗi:

~~~text
Worker sends to SMTP -> SMTP accepts message
          |
          v
Worker crashes before marking outbox SENT
          |
          v
Another worker retries -> duplicate submission possible
~~~

Outbox thông thường có ngữ nghĩa **at-least-once**, không bảo đảm exactly-once SMTP delivery. Correlation ID/`Message-ID` có thể giúp truy vết nhưng không buộc mọi SMTP server loại bỏ message trùng. Nếu provider có API idempotency key, dùng theo hợp đồng của provider; với SMTP thuần, cần chấp nhận/kiểm soát rủi ro duplicate.

## 17. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Nghĩ `helper.setFrom` đặt bounce address | DSN đi tới nơi khác hoặc bị provider viết lại | Cấu hình envelope `MAIL FROM`/custom return-path |
| Dùng `Reply-To` làm địa chỉ bounce | Người dùng reply đúng nhưng bounce không đến | Tách Reply-To và envelope sender |
| Tự thêm `Return-Path` header | Không thay đổi envelope thật, có thể bị ghi đè | Dùng SMTP transport/provider config |
| Tạo bounce mailbox nhưng không có route/MX | DSN không đến processor | Cấu hình DNS/inbound route đúng |
| Sửa `mail.smtp.from` trên Session singleton mỗi request | Race condition khi gửi song song | Per-message mechanism/provider correlation |
| Chỉ bắt `MailSendException` | Bỏ sót bounce xuất hiện sau `send` thành công | Thêm webhook/IMAP feedback pipeline |
| Coi mọi `4xx` là retry ngay | Provider cũng đang retry, gây duplicate | Phân biệt deferral và final soft bounce |
| Coi mọi `5xx` là địa chỉ không tồn tại | Suppress nhầm khi sender bị policy block | Phân loại theo stage/subject/status/provider |
| Dựa vào `From: MAILER-DAEMON` để xác minh | DSN giả có thể làm suppress recipient | Source verification + correlation |
| Bỏ qua duplicate webhook | Đếm bounce nhiều lần, suppression sai | Unique event key + transaction idempotent |
| Dựa riêng vào `Message-ID` cho mọi recipient | Partial bounce gán sai delivery | Provider ID + recipient/delivery token |
| Chỉ có một status cho outbox và feedback | Mất nghĩa `SMTP_ACCEPTED` so với `BOUNCED` | Tách submission và delivery status |
| Update feedback theo thứ tự arrival | Event cũ ghi đè event mới | State transition + timeline policy |
| Log raw DSN hoặc toàn bộ original email | Rò rỉ dữ liệu cá nhân/token | Safe diagnostics + retention |
| Retry khi `DELAYED` | Gửi lặp khi provider vẫn đang thử | Đợi final outcome hoặc policy rõ |
| Treat complaint như soft bounce | Vẫn gửi marketing ngoài ý muốn | Complaint suppression riêng |

## 18. Bảo mật và quyền riêng tư của kênh bounce

DSN không chỉ chứa status code. Nó có thể bao gồm địa chỉ nhận, subject, message headers hoặc một phần/toàn bộ email gốc tùy cấu hình transport. Với email xác minh tài khoản, bản gốc có thể chứa URL mang token.

Những biện pháp quan trọng:

1. **Giới hạn dữ liệu thu thập:** Ưu tiên `HDRS` thay vì yêu cầu hoàn trả full message nếu ứng dụng không cần body.
2. **Xác minh nguồn:** Webhook cần chữ ký/xác thực provider; mailbox DSN cần correlation và đánh giá độ tin cậy.
3. **Tách quyền:** Worker xử lý bounce chỉ cần quyền đọc mailbox/event và cập nhật delivery/suppression theo phạm vi.
4. **Bảo vệ credential:** IMAP password, webhook signing secret, API token và SMTP credential phải đến từ nguồn runtime an toàn.
5. **Chống replay:** Event source ID uniqueness, timestamp, provider signature và logic idempotent.
6. **Giới hạn tải:** HTTP request size, MIME size, recursion depth và số lượng recipient/event.
7. **Không log raw:** Tránh log nguyên webhook payload, DSN, recipient list hoặc MIME gốc.
8. **Retention:** Xóa/anonymize dữ liệu nhạy cảm sau thời hạn cần thiết cho deliverability và audit.
9. **Không dùng event chưa xác thực để suppress:** Giữ hàng chờ điều tra nếu không thể kết luận.
10. **Phân quyền dashboard:** Hỗ trợ viên không cần đọc toàn bộ email gốc để biết lý do bounce.

### 18.1. Tránh mail loop và backscatter

Không triển khai cơ chế tự động gửi “thư không giao được” tới địa chỉ `From` của một message không tin cậy. Hành động này có thể tạo **backscatter**: phản hồi lỗi được gửi tới nạn nhân bị giả mạo địa chỉ.

Nếu ứng dụng là mail transfer agent thực thụ và phải tạo DSN, cần tuân thủ quy tắc SMTP về null reverse-path và giới hạn thông báo; tuy nhiên ứng dụng Spring Mail gửi thông báo nghiệp vụ thông thường **không nên tự viết lại MTA**. Hãy để provider/SMTP server tạo DSN, còn ứng dụng chỉ tiếp nhận và xử lý event.

## 19. Metrics và quan sát deliverability

Một hệ thống đã lưu bounce nên cung cấp các metric để người vận hành phát hiện vấn đề sớm:

| Metric | Diễn giải |
| --- | --- |
| `mail_submission_accepted_total` | Số delivery được SMTP transport/provider chấp nhận |
| `mail_submission_failed_total` | Số delivery bị lỗi trước khi submission thành công |
| `mail_delivery_feedback_total` | Số feedback event theo loại/status code |
| `mail_hard_bounce_total` | Số delivery có hard bounce đã xác minh |
| `mail_soft_bounce_final_total` | Số delivery có soft bounce cuối cùng |
| `mail_delivery_deferred_total` | Số event trì hoãn giao thư |
| `mail_feedback_unmatched_total` | Số event không map được tới delivery |
| `mail_feedback_duplicate_total` | Số webhook/DSN lặp được bỏ qua |
| `mail_suppression_active_count` | Số recipient đang bị suppress theo phạm vi |
| `mail_complaint_total` | Số complaint được xác minh |
| `mail_feedback_processing_duration_seconds` | Thời gian xử lý event |
| `mail_delivery_event_lag_seconds` | Độ trễ từ provider event time tới lúc ingest |

Không dùng recipient email, Message-ID, delivery UUID hoặc raw diagnostic message làm **metric label**: vừa tăng cardinality, vừa có thể lộ PII. Có thể dùng các dimension có số lượng hữu hạn như provider, template category, tenant tier, bounce category, error code và môi trường.

### 19.1. Bounce rate được tính như thế nào?

Một chỉ số cơ bản có thể tính:

\[
\text{Bounce rate} =
\frac{\text{Số delivery bị bounce cuối cùng trong cohort}}
{\text{Số delivery đã được chấp nhận gửi trong cohort}}
\times 100\%
\]

Cần định nghĩa rõ:

- Cohort theo thời điểm gửi hay thời điểm nhận bounce?
- Đơn vị là **message** hay **recipient delivery**?
- Chỉ tính final hard/soft bounce hay có gồm deferral?
- Provider có đầy đủ event hay chỉ một phần?
- Có loại bỏ duplicate webhook và test email?

Một tỷ lệ bounce đo theo event đến trong ngày chia cho email gửi trong ngày có thể sai lệch khi bounce đến trễ nhiều ngày. Với dashboard ổn định, có thể dùng cohort theo ngày SMTP accepted và cập nhật kết quả theo một cửa sổ quan sát xác định.

### 19.2. Cảnh báo theo nguyên nhân

Ví dụ các cảnh báo hữu ích:

- Hard bounce `5.1.1` tăng bất thường: kiểm tra chất lượng địa chỉ và onboarding.
- `5.7.1` tăng đồng loạt trên nhiều domain: kiểm tra SPF/DKIM/DMARC và sender reputation, không suppress hàng loạt mailbox.
- `4.2.2` tăng cho một miền: có thể có giới hạn tạm thời hoặc mailbox full, xem policy provider.
- Webhook processing lag tăng: kiểm tra endpoint/queue và database.
- Unmatched feedback tăng: kiểm tra correlation key, provider message ID hoặc thay đổi schema event.
- Bounce mailbox không có thư nhưng delivery thất bại: kiểm tra reverse-path, MX, relay rewriting và quyền truy cập IMAP.
- Event duplicate tăng mạnh: kiểm tra thời gian xử lý/ACK và chính sách retry webhook của provider.

Nên phân biệt **lỗi SMTP submission**, **bounces sau submission** và **complaints** thành ba nhóm quan sát khác nhau.

## 20. Kiểm thử địa chỉ bounce và xử lý phản hồi

Kiểm thử nên đi qua nhiều tầng; một lần gọi `JavaMailSender.send(...)` không đủ chứng minh kênh bounce đã hoạt động.

### 20.1. Unit test phân loại enhanced status

Ví dụ một bộ phân loại do ứng dụng xây dựng:

~~~java
public enum BounceCategory {
    HARD,
    SOFT,
    UNKNOWN
}

public class BounceClassifier {

    public BounceCategory classify(
            String action,
            String statusCode) {

        if ("delayed".equalsIgnoreCase(action)) {
            return BounceCategory.SOFT;
        }
        if (!"failed".equalsIgnoreCase(action)
                || statusCode == null) {
            return BounceCategory.UNKNOWN;
        }
        if (statusCode.startsWith("5.1.1")) {
            return BounceCategory.HARD;
        }
        if (statusCode.startsWith("4.")) {
            return BounceCategory.SOFT;
        }
        return BounceCategory.UNKNOWN;
    }
}
~~~

Đây là **classifier tối giản, có chủ ý bảo thủ**. Nó chỉ xem `5.1.1` là hard bounce chắc chắn trong ví dụ, chưa phân loại nhiều mã khác và chưa xét provider policy; không thể dùng thay một bộ phân loại production đầy đủ. Đặc biệt, action `delayed` được biểu diễn ở nhóm soft chỉ cho mục đích phân tích, **không có nghĩa là final soft bounce hay được phép retry ngay**.

Test với JUnit:

~~~java
@Test
void classifiesInvalidMailboxAsHardBounce() {
    BounceClassifier classifier = new BounceClassifier();
    assertEquals(
            BounceCategory.HARD,
            classifier.classify("failed", "5.1.1"));
}

@Test
void doesNotTreatUnknownFailureAsHardBounce() {
    BounceClassifier classifier = new BounceClassifier();
    assertEquals(
            BounceCategory.UNKNOWN,
            classifier.classify("failed", "5.7.1"));
}
~~~

Những test này kiểm tra classifier nhỏ, không kiểm chứng SMTP server thực tế. Có thể bổ sung fixture DSN/provider cho `4.2.2`, `5.2.2`, lỗi thiếu `Status`, recipient không hợp lệ và response không chuẩn.

### 20.2. Test webhook authentication và idempotency

Kịch bản nên bao phủ:

1. Signature hợp lệ, payload đúng → event được lưu.
2. Signature sai → 401, không ghi delivery/suppression.
3. Replay payload cùng event ID → không tạo side effect lần hai.
4. Event delivery ID không tồn tại → không cập nhật recipient khác.
5. Recipient không khớp delivery → từ chối hoặc đưa vào hàng điều tra.
6. Event đến không đúng thứ tự → feedback projection không bị ghi đè sai.
7. Provider gửi batch có event trùng → chỉ giữ một bản theo key.
8. Database lỗi trước commit → endpoint không ack thành công để provider có thể retry.

Với cơ chế ký bằng raw body, test phải dùng bytes nguyên bản thay vì giả định JSON serialize lại cho cùng một signature. Thuật toán/chữ ký thật phải theo tài liệu của provider.

### 20.3. Test parser DSN

Dùng các fixture email `.eml` được tạo trong môi trường thử nghiệm:

- `multipart/report` với một recipient `failed 5.1.1`.
- Một DSN chứa hai recipient có kết quả khác nhau.
- Event `delayed 4.2.2`.
- DSN có phần `message/rfc822` kèm bản gốc.
- DSN không có `Status` hoặc thiếu `Final-Recipient`.
- DSN MIME lồng sâu/hỏng boundary.
- DSN giả mạo hoặc không map được tới delivery.
- DSN rất lớn phải bị chặn theo giới hạn tài nguyên.

Không gửi email lỗi đến địa chỉ thật không thuộc quyền kiểm soát để tạo test. Có thể dùng một inbound mailbox hoặc test SMTP relay có cấu hình tạo DSN được kiểm soát.

### 20.4. Test SMTP sink và giới hạn của nó

SMTP sink như Mailpit/MailHog hữu ích để xác nhận:

- Spring Mail tạo đúng `From`, `Reply-To`, subject và MIME.
- SMTP sender có thể submit message tới môi trường thử nghiệm.
- Các thay đổi message không làm hỏng phần plain text/HTML.

Nhưng SMTP sink **không tự chứng minh** bounce trên Internet hay SPF/DKIM/DMARC của production hoạt động. Một sink đơn giản thường chấp nhận và hiển thị email thay vì giao tới mail server đích; muốn test DSN cần mô phỏng event hoặc dùng mail relay được cấu hình tạo bounce.

### 20.5. Test domain/Return-Path trong staging

Trong môi trường staging được phép:

1. Cấu hình bounce domain riêng cho staging, không dùng production credential.
2. Kiểm tra DNS và route inbound tương ứng.
3. Submit một message tới recipient kiểm thử hợp lệ.
4. Quan sát Return-Path và provider metadata thực tế.
5. Tạo một failure giả lập trên mail server/test provider do nhóm kiểm soát.
6. Xác nhận DSN/webhook đến hệ thống, được xác minh và map đúng delivery.
7. Kiểm tra trạng thái và suppression áp dụng đúng phạm vi.
8. Gửi lại cùng webhook/DSN để xác nhận idempotency.

Không dùng một “địa chỉ có vẻ không tồn tại” của người thật để thử hard bounce trên production; việc đó có thể gây tổn hại sender reputation và ảnh hưởng recipient không liên quan.

## 21. Tình huống thực tế: hóa đơn gửi thành công nhưng bounce muộn

Giả sử hệ thống cần gửi hóa đơn sau khi đơn hàng đã hoàn tất.

### Bước 1 — Tạo delivery

~~~text
delivery_id: 73f...
recipient: customer@receiver.example
header_from: billing@example.com
envelope_from: bounces+73f@bounce.example.com
submit_status: PENDING
feedback_status: AWAITING_FEEDBACK
~~~

Ứng dụng ghi outbox/delivery record cùng transaction nghiệp vụ, sau đó worker lấy tác vụ gửi.

### Bước 2 — JavaMailSender nộp thư

~~~text
SMTP relay -> 250 2.0.0 accepted
~~~

Worker ghi:

~~~text
submit_status: SMTP_ACCEPTED
smtp_accepted_at: [timestamp]
feedback_status: AWAITING_FEEDBACK
~~~

Tại thời điểm này, email **chưa được bảo đảm giao tới hộp thư**.

### Bước 3 — Provider thử giao và nhận lỗi

Vài phút sau, provider nhận phản hồi:

~~~text
Final-Recipient: rfc822; customer@receiver.example
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 Mailbox does not exist
~~~

Provider webhook hoặc mailbox DSN đưa sự kiện đến ứng dụng. Processor xác minh nguồn, correlate `delivery_id = 73f...` và chuẩn hóa `HARD_BOUNCE`.

### Bước 4 — Lưu feedback và suppression

Trong transaction:

~~~text
mail_delivery:
  submit_status: SMTP_ACCEPTED
  feedback_status: HARD_BOUNCED
  last_bounce_code: 5.1.1

mail_delivery_feedback_event:
  delivery_id: 73f...
  feedback_type: HARD_BOUNCE
  enhanced_status: 5.1.1

mail_suppression:
  recipient: customer@receiver.example
  reason: HARD_BOUNCE
  status: ACTIVE
~~~

`submit_status` vẫn phản ánh đúng việc SMTP relay đã chấp nhận message; `feedback_status` phản ánh **giao thư thất bại về sau**. Hai trạng thái không mâu thuẫn.

### Bước 5 — Khi người dùng sửa địa chỉ

Người dùng cập nhật địa chỉ email trong ứng dụng. Hệ thống cần xác minh địa chỉ mới theo chính sách của sản phẩm, rồi tạo delivery mới nếu email hóa đơn vẫn cần được gửi.

Không tự gửi lại vô hạn đến địa chỉ cũ. Nếu người dùng xác minh lại chính địa chỉ cũ, việc gỡ suppression phải thông qua luồng có bằng chứng và audit.

### Bước 6 — Nếu webhook trùng

Provider gửi cùng một event lần thứ hai do lần đầu HTTP response bị timeout. Unique event key khiến processor không tạo suppression thứ hai và không tăng hard bounce count thêm một lần.

Điều này cho phép hệ thống chịu được redelivery mà vẫn phản ánh đúng một bounce đã được xác nhận.

## 22. Hỏi đáp thường gặp

**“Tại sao `JavaMailSender.send()` không ném exception nhưng người nhận vẫn không có email?”**  
Phương thức gửi chỉ biết kết quả của phiên SMTP mà ứng dụng tham gia. Server relay có thể chấp nhận message rồi gặp lỗi sau đó ở bước chuyển tiếp hoặc giao tới server đích. Cần webhook/DSN hoặc API provider để theo dõi feedback sau submission.

**“Dùng `helper.setFrom("bounces@...")` đã cấu hình được bounce chưa?”**  
Chưa chắc. `setFrom` đặt header From; địa chỉ nhận DSN thường được quyết định bởi SMTP envelope `MAIL FROM` và provider. Hãy cấu hình `mail.smtp.from` hoặc custom return-path theo hạ tầng gửi.

**“Dùng `helper.setReplyTo(...)` làm bounce address được không?”**  
Không. Reply-To dành cho phản hồi của người đọc email, không phải nơi SMTP server bắt buộc gửi delivery failure notice.

**“Có nên tự đặt header `Return-Path` không?”**  
Không nên. Return-Path được hệ thống giao thư chèn dựa trên envelope reverse-path; chỉnh header không thay thế cấu hình SMTP envelope.

**“Tại sao tôi cấu hình `mail.smtp.from` rồi Return-Path vẫn khác?”**  
SMTP relay hoặc email provider có thể ghi đè envelope sender theo policy, đặc biệt khi dùng dịch vụ gửi email có custom bounce domain riêng. Kiểm tra cấu hình của provider và trạng thái domain verification.

**“Có nên dùng một bounce mailbox cho mọi email?”**  
Có thể nếu mailbox/processor có đủ khả năng correlation theo delivery/recipient. Với khối lượng lớn, VERP-like alias hoặc provider metadata thường giúp đối soát chính xác hơn.

**“VERP có bảo đảm DSN là thật không?”**  
Không. Token opaque trong địa chỉ bounce hỗ trợ correlation, nhưng một người biết địa chỉ vẫn có thể gửi email giả. Cần bảo vệ nguồn nhận và chỉ hành động khi đã xác minh event/delivery hợp lệ.

**“Bounce mailbox cần MX record không?”**  
Nếu muốn nhận mail qua SMTP trực tiếp, domain nhận phải có định tuyến mail hợp lệ theo hạ tầng. Một số provider dùng CNAME, custom return-path hoặc route riêng; cần làm theo cơ chế provider thay vì tự đặt DNS tùy ý.

**“Bounce có luôn là email từ MAILER-DAEMON không?”**  
Không. Có provider gửi webhook hoặc event API, có DSN từ một MTA với header khác nhau. Tên người gửi không đủ để xác minh nguồn.

**“Một DSN có thể báo cho nhiều recipient không?”**  
Có. Một message gửi nhiều địa chỉ có thể phát sinh phản hồi khác nhau theo từng recipient. Phải đọc per-recipient fields và cập nhật đúng từng delivery.

**“Mã `5.1.1` có nghĩa gì?”**  
Thường là bad destination mailbox address, chẳng hạn mailbox không tồn tại. Sau khi xác minh nguồn và correlation, đây là tín hiệu điển hình để hard suppress địa chỉ.

**“Mã `4.2.2` có nên retry ngay không?”**  
Không nhất thiết. Nó thường liên quan mailbox full/tạm thời. Nếu provider vẫn đang thử giao, application không nên nộp một message mới chỉ vì nhận event trì hoãn. Chờ final outcome hoặc làm theo policy provider.

**“Mọi mã 5xx có phải hard bounce vì recipient không tồn tại?”**  
Không. `5.7.1` có thể do policy, authentication hoặc sender reputation. Cần phân loại theo phản hồi, giai đoạn và provider trước khi quyết định suppression.

**“Nên xử lý spam complaint như hard bounce?”**  
Không hoàn toàn. Complaint thể hiện phản hồi không mong muốn của người nhận, thường dẫn tới suppression vì consent. Hard bounce thể hiện lỗi giao thư. Hai loại cần chính sách và thống kê riêng.

**“Nếu không có bounce thì có nghĩa email đã tới inbox?”**  
Không. Provider có thể không cung cấp feedback đầy đủ, email bị lọc hoặc bounce có thể tới muộn/mất. Không có event không phải bằng chứng delivery.

**“Provider báo `delivered` thì người nhận đã đọc email chưa?”**  
Không. Delivered thường phản ánh mức chuyển giao mà provider quan sát được, không chứng minh thư đã được người dùng mở hoặc thấy trong inbox.

**“Có nên dùng một trường `sent` cho cả gửi và bounce?”**  
Không nên. Nên tách SMTP submission status khỏi delivery feedback status để không mất lịch sử “server đã nhận, nhưng giao thư thất bại sau đó”.

**“Khi webhook tới hai lần thì xử lý sao?”**  
Dùng provider event ID/recipient làm khóa idempotency theo hợp đồng provider, insert atomically vào event history rồi chỉ cập nhật trạng thái/suppression một lần.

**“Nếu webhook đến sai thứ tự thì sao?”**  
Giữ toàn bộ event history và áp dụng state transition policy. Không cho event `DEFERRED` cũ ghi đè một kết quả nhận/giao thư mới hơn chỉ vì HTTP request tới sau.

**“Có nên tin DSN bất kỳ để xóa địa chỉ khỏi danh sách gửi?”**  
Không. Email DSN có thể bị giả mạo; cần correlation và xác minh nguồn ở mức khả thi. Sự kiện không tin cậy nên được lưu để điều tra, không tự động gây suppression.

**“Có cần tự viết parser MIME của DSN không?”**  
Nếu dùng provider webhook chính thức, thường có thể tránh tự xử lý nhiều biến thể DSN. Với mailbox, nên dùng Jakarta Mail và/hoặc parser DSN phù hợp implementation, giới hạn tài nguyên và kiểm thử bằng fixture.

**“Bật `mail.smtp.dsn.notify` có bảo đảm provider sẽ gửi bounce không?”**  
Không. Nó là yêu cầu extension của SMTP transport khi server hỗ trợ. Provider có thể có chính sách riêng và không phải mọi lỗi đều sinh DSN đầy đủ.

**“Địa chỉ bounce ảnh hưởng SPF/DMARC thế nào?”**  
SPF kiểm tra domain của envelope sender, còn DMARC đánh giá alignment với header From thông qua SPF và/hoặc DKIM. Custom bounce domain phải được cấu hình DNS, xác thực và kiểm tra thực tế theo provider.

**“Có nên retry một email đã hard bounced?”**  
Thường không với địa chỉ đã được xác minh là không tồn tại. Nếu người dùng sửa/xác minh địa chỉ hoặc nguyên nhân thực ra là policy sender, hệ thống có thể tạo delivery hợp lệ mới theo quy trình.

**“Có thể dùng Message-ID để bảo đảm chỉ gửi một lần?”**  
Không. Message-ID giúp truy vết nhưng không bắt buộc các SMTP server loại bỏ message trùng. Outbox+SMTP thường có duplicate window; provider API có idempotency nếu được hỗ trợ chính thức.

## 23. Checklist triển khai hệ thống bounce

### Hạ tầng gửi và địa chỉ

1. Xác định rõ header From, Reply-To và envelope MAIL FROM.
2. Có địa chỉ/subdomain bounce thuộc quyền kiểm soát của tổ chức.
3. Provider cho phép sử dụng và định tuyến địa chỉ bounce đó.
4. DNS, MX/custom return-path và SPF/DKIM/DMARC được cấu hình theo provider.
5. Nếu dùng VERP, token đủ an toàn, không chứa PII và có route inbound hỗ trợ.

### Tiếp nhận feedback

6. Chọn webhook đã được provider hỗ trợ hoặc mailbox DSN có checkpoint.
7. Xác minh webhook signature/raw body và replay theo hợp đồng provider.
8. Với DSN mailbox, phân tích MIME có giới hạn kích thước/độ sâu và xử lý per-recipient.
9. Không tin một email tự xưng MAILER-DAEMON khi chưa có kiểm tra nguồn/correlation.
10. Có dead-letter/needs-review cho event không match hoặc không phân loại được.

### Dữ liệu và nghiệp vụ

11. Tách trạng thái SMTP submission và delivery feedback.
12. Một recipient có một delivery record nếu cần retry/audit riêng.
13. Lưu feedback event append-only, có khóa deduplication.
14. Correlate theo delivery ID/provider ID/recipient thay vì chỉ subject.
15. Có state transition policy khi provider event tới muộn hoặc ngược thứ tự.
16. Phân biệt hard bounce, final soft bounce, delayed, delivered và complaint.
17. Hard bounce đã xác minh có chính sách suppression phù hợp.
18. Không retry tự động một message mới khi provider còn đang retry message cũ.
19. Với email giao dịch quan trọng, suppression phải có đường xử lý thay thế/khôi phục rõ ràng.

### Vận hành và kiểm thử

20. Log/metrics chỉ dùng error category/correlation ID an toàn, không log nguyên DSN có dữ liệu nhạy cảm.
21. Có dashboard cho bounce rate, unmatched event, webhook lag và suppression.
22. Test signature không hợp lệ, duplicate webhook, multi-recipient DSN và out-of-order event.
23. Test bounce address/Return-Path bằng hạ tầng staging được phép.
24. Có quy trình sửa địa chỉ, re-verification, redrive và retention.

## 24. Tổng kết luồng xử lý

Một hệ thống deliverability dùng Spring Framework Mail có thể triển khai theo chuỗi trách nhiệm:

~~~text
Business event / Outbox
          |
          v
Build MIME message
  From: notifications@example.com
  Reply-To: support@example.com
          |
          v
SMTP envelope
  MAIL FROM: bounces+deliveryToken@bounce.example.com
  RCPT TO: customer@receiver.example
          |
          v
JavaMailSender.send(...)
          |
      +---+------------------------+
      |                            |
      v                            v
Sync SMTP failure             SMTP accepted
      |                            |
      v                            v
Classify/retry outbox        Later delivery attempt
                                   |
                                   v
                       DSN mailbox or provider webhook
                                   |
                                   v
                      Verify source + normalize event
                                   |
                                   v
                     Match delivery ID + recipient
                                   |
                                   v
                       Idempotent database update
                                   |
                        +----------+----------+
                        |          |          |
                        v          v          v
                    Hard bounce  Soft bounce  Complaint
                        |          |          |
                        v          v          v
                    Suppression  Wait/policy  Consent policy
                        |          |          |
                        +----------+----------+
                                   |
                                   v
                         Metrics / audit / alerts
~~~

### Nguyên tắc ghi nhớ

- `JavaMailSender.send` trả về thành công **không bảo đảm inbox delivery**.
- Bounce thường quay về **SMTP envelope sender**, không phải Header From hay Reply-To.
- `Return-Path` là dấu vết envelope khi giao thư, không phải header để ứng dụng tự sửa.
- DSN có thể tới muộn, không đầy đủ, báo cho nhiều recipient và thậm chí bị giả mạo.
- Webhook cần xác minh và xử lý idempotent; IMAP DSN cần MIME parser và checkpoint.
- `DELAYED` khác `FAILED`; đừng tạo lần gửi mới khi provider vẫn retry.
- Hard bounce, soft bounce và spam complaint cần chính sách suppression riêng.
- Submission state, delivery feedback và audit event nên được lưu tách bạch.

**Kết luận:** Trong Spring Framework Mail, thiết kế địa chỉ bounce đúng nghĩa là thiết kế **đường nhận phản hồi thất bại của SMTP envelope**, không chỉ điền một email vào header. Một giải pháp hoàn chỉnh cần cấu hình bounce domain/return-path được provider chấp nhận, thu thập DSN hoặc webhook có xác minh, phân loại phản hồi theo từng recipient và cập nhật trạng thái idempotent. Khi làm đúng, ứng dụng biết được thư nào chưa được giao, ngừng gửi tới địa chỉ chắc chắn không hợp lệ, tránh retry gây trùng và có dữ liệu đáng tin cậy để cải thiện deliverability.
