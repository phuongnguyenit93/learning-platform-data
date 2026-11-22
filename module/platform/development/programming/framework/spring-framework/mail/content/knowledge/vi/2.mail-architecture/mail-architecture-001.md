# Message User Agent (MUA) và nơi người dùng soạn thư

## 1. MUA là gì và vì sao cần hiểu đúng vai trò?

Trong kiến trúc thư điện tử, **Message User Agent (MUA)**, cũng thường được gọi là **Mail User Agent**, là thành phần mà người dùng tương tác để **soạn, gửi yêu cầu gửi, đọc, trả lời, chuyển tiếp và quản lý email**. MUA là điểm tiếp xúc giữa con người và hệ thống email. Tên gọi “agent” diễn tả vai trò đại diện cho người dùng thực hiện các thao tác trên thư, không có nghĩa đây là một tác nhân AI.

Một số ví dụ quen thuộc:

- **Ứng dụng email trên máy tính:** Mozilla Thunderbird, Microsoft Outlook ở chế độ ứng dụng email, Apple Mail.
- **Ứng dụng email trên điện thoại:** ứng dụng Mail hoặc Gmail trên thiết bị di động.
- **Webmail:** giao diện soạn thư của Gmail, Outlook trên trình duyệt, hoặc hệ thống webmail doanh nghiệp.
- **Giao diện email tự phát triển:** màn hình “Liên hệ”, “Gửi báo cáo” hoặc “Soạn thông báo” của một ứng dụng; tùy kiến trúc, giao diện này đóng vai trò soạn thư giống MUA, còn backend thực hiện bước gửi.

Chức năng cốt lõi của MUA trong bài này là **nơi người gửi chuẩn bị một thông điệp trước khi chuyển nó vào hạ tầng vận chuyển thư**. Người dùng nhìn thấy địa chỉ nhận, tiêu đề, nội dung và tệp đính kèm; còn giao thức SMTP, máy chủ chuyển tiếp, bản ghi MX và kho lưu trữ thư thường hoạt động ở những lớp phía sau.

> **Ý chính:** Người dùng **soạn** email ở MUA; MUA hoặc backend đại diện cho MUA **nộp** email cho dịch vụ gửi; các máy chủ mail sau đó **chuyển tiếp và phân phối** thông điệp đến hộp thư người nhận. Ba hành động này là các bước khác nhau.

## 2. MUA đứng ở đâu trong kiến trúc email?

Một mô hình tổng quát:

~~~mermaid
flowchart LR
    U["Người gửi"] --> A["MUA: nơi soạn thư"]
    A -->|"Nộp thư qua SMTP hoặc API/HTTPS"| S["MSA: tiếp nhận thư gửi"]
    S --> T["MTA: chuyển tiếp thư"]
    T --> D["Hệ thống thư đích: nhận và lưu thư"]
    D --> R["MUA của người nhận"]
    R --> V["Người nhận đọc thư"]
~~~

Các tên viết tắt dễ gặp:

| Thành phần | Tên đầy đủ | Trách nhiệm chính | Liên hệ với MUA |
| --- | --- | --- | --- |
| **MUA** | Message/Mail User Agent | Giao diện và logic thao tác email của người dùng | Nơi người dùng soạn hoặc đọc thư |
| **MSA** | Mail Submission Agent | Tiếp nhận thư gửi từ ứng dụng, kiểm tra chính sách gửi và chuyển vào hệ thống mail | Đầu nhận yêu cầu gửi của MUA hoặc backend |
| **MTA** | Mail Transfer Agent | Định tuyến, chuyển tiếp thư giữa các hệ thống mail qua SMTP | Thường không trực tiếp tương tác với người dùng |
| **MDA** | Mail Delivery Agent | Phân phối thư đến hộp thư/kho lưu trữ đích | Chuẩn bị thư để người nhận có thể truy cập |
| **Mail store / mailbox** | Kho/hộp thư | Lưu thư đã nhận, thư đã gửi, thư nháp tùy hệ thống | MUA truy cập để hiển thị và quản lý thư |

Đây là mô hình **vai trò logic**, không nhất thiết là năm chương trình hay năm máy chủ riêng. Một dịch vụ email có thể gộp MSA, MTA, lưu trữ và các API trong cùng nền tảng. Webmail cũng có thể dùng HTTPS từ trình duyệt đến backend thay vì cho trình duyệt kết nối SMTP trực tiếp.

Khi người nhận mở thư, MUA có thể lấy dữ liệu qua **IMAP**, **POP3** hoặc **API/HTTPS** của nhà cung cấp. Các giao thức đó phục vụ truy cập hộp thư, trong khi SMTP chủ yếu phục vụ khâu nộp và vận chuyển thư.

## 3. Chính xác thì người dùng soạn gì trong MUA?

Màn hình soạn thư thường gồm các trường sau:

| Trường trên màn hình | Ý nghĩa | Khi tạo thông điệp email |
| --- | --- | --- |
| **From** (Người gửi) | Danh tính người gửi được hiển thị | Thường trở thành header `From`; tài khoản/miền gửi cần được hệ thống cho phép |
| **To** (Đến) | Người nhận chính | Header `To` và địa chỉ cần được chuyển phát |
| **Cc** (Carbon copy) | Người nhận bản sao được công khai với người nhận khác | Header `Cc` và địa chỉ cần được chuyển phát |
| **Bcc** (Blind carbon copy) | Người nhận bản sao ẩn | Là người nhận chuyển phát, nhưng thông tin Bcc không được lộ trong bản thư gửi cho các người nhận khác |
| **Subject** (Tiêu đề) | Chủ đề tóm tắt nội dung | Header `Subject` |
| **Body** (Nội dung) | Văn bản thuần hoặc nội dung HTML | Một hoặc nhiều phần nội dung của thông điệp |
| **Attachments** (Đính kèm) | Tệp gửi kèm | Được đóng gói thành các phần MIME |
| **Reply-To** (Trả lời đến) | Địa chỉ ưu tiên khi người nhận chọn “Trả lời” | Header `Reply-To`, có thể khác `From` |

Ví dụ người dùng soạn một email:

~~~text
Từ:        Thông báo hệ thống <notifications@example.com>
Đến:       lan@example.net
Cc:        team@example.net
Bcc:       quan@example.org
Tiêu đề:   Báo cáo tuần đã sẵn sàng

Chào Lan,

Báo cáo tuần đã được tổng hợp. Mời bạn xem tệp đính kèm.

Trân trọng,
Nhóm vận hành

Đính kèm: bao-cao-tuan.pdf
~~~

Khi gửi, hệ thống cần chuyển thư cho Lan, nhóm nhận Cc **và** Quân. Tuy nhiên, người nhận thông thường **không nhìn thấy** địa chỉ Bcc của Quân trong các header thư mà họ nhận được. Không nên hiểu Bcc là một cơ chế ẩn danh trước chính máy chủ email: hạ tầng chuyển phát vẫn phải biết địa chỉ nào cần nhận thư.

### 3.1. Thư nháp chưa phải là thư đã gửi

Khi người dùng nhập tiêu đề và nội dung, dữ liệu có thể vẫn chỉ nằm trong bộ nhớ ứng dụng. Nếu MUA có tính năng “Lưu nháp”, ứng dụng có thể cất dữ liệu trong kho thư nháp hoặc cơ sở dữ liệu. Không có yêu cầu chuyển phát nào bắt buộc phải xảy ra ở giai đoạn này.

Tùy nền tảng, người dùng có thể:

1. Soạn và lưu nháp nhiều lần.
2. Đính kèm hoặc gỡ tệp.
3. Chọn **Gửi** hoặc lên lịch gửi.
4. Nhận thông báo ứng dụng đã tiếp nhận yêu cầu.
5. Xem kết quả gửi, hoặc nhận email báo lỗi chuyển phát sau đó.

Việc MUA hiển thị “Đã gửi” thường có nghĩa thao tác gửi đã được ứng dụng hoặc nhà cung cấp chấp nhận xử lý; nó **không tự chứng minh** email đã vào Inbox, được mở hay được đọc.

### 3.2. Email không chỉ là chuỗi nội dung hiển thị

Một thông điệp gửi đi có **header** (metadata), **body** và có thể gồm nhiều phần **MIME**. MIME (Multipurpose Internet Mail Extensions) hỗ trợ mã hóa ký tự, nội dung HTML, nhiều phiên bản nội dung và đính kèm.

Ví dụ minh họa một thư văn bản thuần sau khi được tạo thành thông điệp:

~~~text
From: Thong bao <notifications@example.com>
To: lan@example.net
Subject: Bao cao tuan
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Chào Lan,
Báo cáo tuần đã sẵn sàng.
~~~

Đây là dạng **minh họa cấu trúc**, không phải bản chụp đầy đủ của mọi email thực tế. Ứng dụng gửi thư và máy chủ email còn có thể bổ sung các header như `Date`, `Message-ID` và những thông tin phục vụ truy vết.

Nếu thư chứa cả nội dung text và HTML, MUA có thể dùng `multipart/alternative` để cung cấp hai cách hiển thị. Nếu có tệp đính kèm, thư có thể dùng `multipart/mixed`; mỗi tệp trở thành một phần MIME với tên tệp, loại nội dung và dữ liệu được mã hóa phù hợp. Người dùng không cần tự viết những ranh giới MIME này: thư viện gửi mail thường tạo giúp.

## 4. Từ thao tác “Gửi” đến lúc thư rời MUA

Xét ví dụ người dùng gửi từ một ứng dụng email desktop:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant MUA as MUA
    participant MSA as Máy chủ submission
    participant MTA as Máy chủ chuyển tiếp
    participant Box as Hộp thư người nhận

    User->>MUA: Nhập To, Subject, Body, tệp đính kèm
    MUA->>MUA: Tạo thư nháp và cấu trúc MIME
    User->>MUA: Nhấn Gửi
    MUA->>MSA: Nộp thông điệp, xác thực nếu cần
    MSA-->>MUA: Chấp nhận hoặc từ chối yêu cầu
    MSA->>MTA: Chuyển thư đã được tiếp nhận
    MTA->>Box: Vận chuyển và phân phối
    Note over MUA,Box: Việc MSA chấp nhận không bảo đảm thư đã được đọc
~~~

### 4.1. Submission và relay khác nhau

SMTP được dùng trong cả quá trình **nộp thư** và **chuyển tiếp**, nhưng vai trò kết nối khác nhau:

- **Submission:** MUA hoặc ứng dụng gửi kết nối tới dịch vụ nhận thư đi (MSA). Cấu hình phổ biến là SMTP submission qua cổng **587** với STARTTLS; nhiều nhà cung cấp hỗ trợ cổng **465** với TLS ngay từ đầu. Kết nối thường yêu cầu xác thực theo chính sách của nhà cung cấp.
- **Relay / transfer:** các máy chủ thư chuyển tiếp đến máy chủ khác, thường qua SMTP cổng **25**. Người dùng không cần kết nối trực tiếp với máy chủ MX của mọi người nhận.
- **Đọc thư:** MUA của người nhận dùng giao thức/API truy cập hộp thư, ví dụ IMAP qua TLS cổng **993** hoặc giao diện webmail qua HTTPS.

Những số cổng trên là các giá trị thường gặp, không phải quy tắc bất biến: nhà cung cấp có thể đưa ra yêu cầu kết nối và xác thực riêng. MUA cần dùng đúng cấu hình của hệ thống thư đang sử dụng.

### 4.2. Header của thư và “phong bì” SMTP không phải một thứ

Người đọc thấy các trường như `From` và `To` trong nội dung header. Trong lúc SMTP vận chuyển, hệ thống còn dùng **SMTP envelope** để biết địa chỉ trả lỗi và các đích chuyển phát:

~~~text
MAIL FROM:<bounce@example.com>
RCPT TO:<lan@example.net>
RCPT TO:<team@example.net>
RCPT TO:<quan@example.org>
DATA
From: notifications@example.com
To: lan@example.net
Cc: team@example.net
Subject: Bao cao tuan

Noi dung thu...
.
~~~

Ví dụ cho thấy:

- `MAIL FROM` là địa chỉ envelope phục vụ quá trình gửi/báo lỗi; có thể khác header `From` mà người đọc thấy.
- Mỗi `RCPT TO` xác định một đích chuyển phát. Danh sách này có thể bao gồm người nhận Bcc.
- Header hiển thị cho Lan và nhóm không cần chứa địa chỉ Bcc của Quân.
- SMTP là giao thức truyền thông điệp; các dòng lệnh trên chỉ minh họa phiên giao tiếp, chưa bao gồm bắt tay, xác thực, TLS và nhiều chi tiết khác.

Nhầm lẫn giữa hai lớp này thường dẫn đến câu hỏi: “Tại sao đã có trường To trong email mà SMTP vẫn cần RCPT TO?”. Lý do là **header phục vụ biểu diễn thông điệp**, còn **envelope phục vụ điều phối chuyển phát**.

## 5. MUA truyền thống, webmail và giao diện ứng dụng

Không phải mọi nơi có nút “Soạn email” đều kết nối SMTP theo cùng một cách.

### Trường hợp A: Ứng dụng email trên máy tính

Ví dụ, Thunderbird hiển thị trình soạn thư, quản lý bản nháp, đóng gói MIME và kết nối tới máy chủ submission được cấu hình. Trong trường hợp này, ứng dụng desktop là một MUA khá điển hình.

~~~text
Người dùng → Thunderbird (MUA) → SMTP submission (MSA) → hệ thống mail
~~~

### Trường hợp B: Webmail trên trình duyệt

Với Gmail hoặc hệ thống webmail, trình duyệt hiển thị form soạn thư. Khi nhấn Gửi, frontend thường gọi backend của nhà cung cấp qua **HTTPS**. Backend mới thực hiện các bước cần thiết để thư được chấp nhận vào dịch vụ vận chuyển; trình duyệt không nhất thiết mở kết nối SMTP.

~~~text
Người dùng → Giao diện webmail → HTTPS → backend mail → hệ thống vận chuyển
~~~

Như vậy, **trải nghiệm MUA** có thể trải qua cả giao diện web và backend của dịch vụ. Không nên đồng nhất “MUA” với một ứng dụng cài đặt trên máy hay mặc định cho rằng mọi nút Gửi đều tự gọi SMTP từ trình duyệt.

### Trường hợp C: Form “Gửi thông báo” trong ứng dụng Spring

Một hệ thống nội bộ có form cho nhân viên nhập địa chỉ nhận, tiêu đề và nội dung. Frontend cung cấp trải nghiệm soạn thư; ứng dụng Spring nhận yêu cầu, xác định danh tính gửi hợp lệ, tạo thông điệp MIME rồi gọi dịch vụ SMTP hoặc email API.

~~~text
Người dùng
   ↓ soạn thư
Frontend: trang Soạn thông báo
   ↓ HTTPS, dữ liệu form
Backend Spring: kiểm tra và tạo thông điệp
   ↓ JavaMailSender / dịch vụ gửi mail
MSA hoặc email provider
   ↓
Người nhận
~~~

Trong trường hợp này, **Spring Mail cung cấp năng lực lập trình để tạo và gửi email ở phía server**, còn phần người dùng nhìn thấy phải do ứng dụng hoặc một sản phẩm webmail xây dựng. Bản thân Spring Framework Mail không phải một giao diện soạn thư, cũng không phải dịch vụ hosting mailbox.

## 6. Spring Framework Mail liên quan thế nào đến MUA?

Spring Framework cung cấp các API mail như `MailSender`, `JavaMailSender`, `SimpleMailMessage` và `MimeMessageHelper`.

| API / lớp | Công dụng | Liên hệ với thao tác soạn thư |
| --- | --- | --- |
| `SimpleMailMessage` | Biểu diễn email văn bản thuần đơn giản | Gán người nhận, người gửi, tiêu đề, nội dung text |
| `MailSender` | Hợp đồng gửi thư đơn giản trong Spring | Gửi các `SimpleMailMessage` |
| `JavaMailSender` | API Spring tích hợp Jakarta Mail cho thông điệp MIME | Tạo `MimeMessage` và gửi email, kể cả dạng HTML/đính kèm |
| `MimeMessage` | Thông điệp MIME của Jakarta Mail | Mang headers, body và các phần nội dung |
| `MimeMessageHelper` | Hỗ trợ thiết lập `MimeMessage` thuận tiện | Đặt To/Cc/Bcc, Subject, text/HTML, attachment... |

**Phân chia trách nhiệm cần giữ rõ:**

1. **Frontend hoặc MUA** thu thập ý định soạn thư của người dùng.
2. **Backend nghiệp vụ** quyết định người gửi hợp lệ, người nhận được phép, nội dung và thời điểm gửi.
3. **Spring Mail/Jakarta Mail** dựng thông điệp và kết nối tới hạ tầng gửi thư theo cấu hình.
4. **Mail server/provider** tiếp nhận, định tuyến và thực hiện chuyển phát.

Đôi khi ứng dụng Spring **không có người soạn thư trực tiếp**, chẳng hạn gửi email xác thực tài khoản hoặc email báo lỗi khi một tác vụ chạy. Đây là email được ứng dụng tạo tự động. Về mặt kiến trúc, code Spring đóng vai trò **thành phần phát sinh và nộp thông điệp**, không biến toàn bộ backend thành một giao diện MUA cho con người.

### 6.1. Ví dụ Spring: backend nhận nội dung đã soạn và gửi email text

Ví dụ sau dùng Spring Framework 6 / Jakarta Mail, với một service được cấp `JavaMailSender`. Địa chỉ `From` do hệ thống định sẵn; các giá trị do người dùng cung cấp chỉ nên được xử lý sau bước xác thực, phân quyền và kiểm tra dữ liệu ở lớp gọi.

~~~java
package com.example.mail;

import java.nio.charset.StandardCharsets;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {

    private final JavaMailSender mailSender;

    public NotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendComposedMessage(
            String recipient,
            String subject,
            String body) {

        MimeMessage message = mailSender.createMimeMessage();

        try {
            MimeMessageHelper helper = new MimeMessageHelper(
                    message,
                    false,
                    StandardCharsets.UTF_8.name());

            helper.setFrom("notifications@example.com");
            helper.setTo(recipient);
            helper.setSubject(subject);
            helper.setText(body, false); // false = plain text, không phải HTML

            mailSender.send(message);
        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Không thể chuẩn bị thông điệp email", ex);
        }
    }
}
~~~

Trong ví dụ:

- Người dùng **soạn** `recipient`, `subject`, `body` trong giao diện do ứng dụng cung cấp.
- Service tạo `MimeMessage` và ánh xạ dữ liệu đã được phép gửi sang cấu trúc email.
- `MimeMessageHelper` xử lý các thao tác tạo header và nội dung, bao gồm thiết lập UTF-8.
- `JavaMailSender.send(...)` yêu cầu hạ tầng mail gửi thông điệp; lỗi gửi từ Spring thường được biểu diễn bằng các ngoại lệ thuộc nhóm `MailException` (runtime), ngoài lỗi `MessagingException` khi chuẩn bị thông điệp.
- Ví dụ không tự tạo màn hình soạn thư, tài khoản email hay hộp thư nhận. Muốn chạy thực tế phải cấu hình `JavaMailSender` và dịch vụ SMTP hợp lệ.

Trong ứng dụng **Spring Boot**, một cấu hình mẫu cho SMTP submission có thể là:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: username-from-secure-config
    password: password-from-secure-config
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
~~~

Đây là ví dụ cấu hình cấu trúc, không phải tài khoản SMTP dùng được. Khi triển khai thật, lấy thông tin xác thực từ biến môi trường hoặc hệ thống quản lý bí mật, sử dụng phương thức xác thực mà nhà cung cấp hỗ trợ và bảo đảm địa chỉ `From` được phép gửi. `spring.mail.*` là cơ chế cấu hình tiện lợi của **Spring Boot**; trong ứng dụng chỉ dùng Spring Framework thuần, lập trình viên có thể cần khai báo bean `JavaMailSenderImpl` và cấu hình tương đương.

### 6.2. Khi cần HTML và tệp đính kèm

Với nội dung HTML, có thể dùng `helper.setText(html, true)`; với cả bản text và HTML, dùng phương thức hỗ trợ hai phiên bản nội dung. Với tệp đính kèm, tạo `MimeMessageHelper` ở chế độ multipart và thêm attachment từ một nguồn dữ liệu phù hợp. Ví dụ khái niệm:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, StandardCharsets.UTF_8.name());

helper.setFrom("notifications@example.com");
helper.setTo("lan@example.net");
helper.setSubject("Báo cáo tuần");
helper.setText(
        "Báo cáo tuần đã sẵn sàng.",
        "<p>Báo cáo tuần đã <strong>sẵn sàng</strong>.</p>");
helper.addAttachment("bao-cao-tuan.pdf", pdfResource);

mailSender.send(message);
~~~

Đoạn minh họa giả định `pdfResource` là một `InputStreamSource`/`Resource` hợp lệ được tạo từ tệp báo cáo mà ứng dụng sở hữu. Với attachment sử dụng luồng, nguồn dữ liệu phải đáp ứng yêu cầu có thể đọc lại của Jakarta Mail khi cần. Ứng dụng cũng phải giới hạn kích thước, kiểm tra nội dung/tên tệp và không tự động gửi tệp tùy ý theo một đường dẫn do client đưa vào.

**Chú ý:** Dùng HTML để hiển thị đẹp không có nghĩa MUA hoặc trình nhận sẽ chạy JavaScript từ email. Nhiều ứng dụng email lọc chặt HTML, CSS, ảnh từ xa và nội dung chủ động. Với email giao dịch, nên cung cấp bản text và tránh phụ thuộc vào những tính năng web không được hỗ trợ đồng nhất.

## 7. Ranh giới giữa nội dung người dùng nhập và danh tính gửi

MUA có thể cho phép người dùng chọn tài khoản gửi hoặc bí danh (alias), nhưng backend và máy chủ mail vẫn phải áp dụng chính sách. Chẳng hạn, một form công khai không nên để bất kỳ khách truy cập nào gán tùy ý:

~~~text
From: ceo@company.example
~~~

nếu họ không có quyền sử dụng danh tính đó. Header `From` chỉ là một phần của thông điệp; việc xác thực tài khoản SMTP, quyền gửi từ miền, chính sách nhà cung cấp và các cơ chế bảo vệ miền gửi (SPF, DKIM, DMARC) mới cùng tham gia xác định tính hợp lệ và độ tin cậy của thư.

Với form “Liên hệ chúng tôi”, thiết kế phổ biến là:

- `From`: địa chỉ đã được xác thực hoặc được hệ thống quản lý, ví dụ `contact-form@example.com`.
- `Reply-To`: địa chỉ của người liên hệ, sau khi kiểm tra định dạng và chính sách sử dụng.
- `To`: hộp thư hỗ trợ nội bộ do server cấu hình.
- `Subject` và `Body`: nội dung được xử lý/kiểm tra trước khi tạo email.

Cách này giúp người nhận có thể bấm “Trả lời” để phản hồi đúng người liên hệ, đồng thời giữ danh tính gửi trong phạm vi được cấp quyền.

### Những điểm cần chú ý khi thiết kế giao diện soạn thư

| Vấn đề | Cách xử lý |
| --- | --- |
| **Dữ liệu nhập** | Giới hạn độ dài, số địa chỉ, dung lượng attachment; từ chối giá trị không hợp lệ trước khi tạo thông điệp |
| **Quyền gửi** | Xác định người dùng/tác vụ nào được gửi cho nhóm người nhận nào; không tin vào quyền do frontend tự khai báo |
| **Header và danh tính** | Tạo những trường nhạy cảm như `From` từ cấu hình hoặc danh tính đã xác minh; dùng API thư viện thay vì tự nối chuỗi header |
| **HTML** | Escape dữ liệu khi xây dựng HTML và kiểm soát template; không đưa HTML tùy ý của người dùng vào email với quyền tin cậy |
| **Tệp đính kèm** | Kiểm tra loại tệp, kích thước, nội dung và quyền truy cập; không hiển thị hay ghi log dữ liệu nhạy cảm |
| **Thông tin xác thực SMTP** | Lưu ở phía backend và nguồn bí mật phù hợp; dùng TLS và cơ chế xác thực được provider chấp nhận |
| **Gửi nhiều / gửi lại** | Áp dụng giới hạn tần suất và cơ chế chống gửi trùng theo nghiệp vụ, nhất là khi retry sau timeout |
| **Trạng thái gửi** | Phân biệt “đã tiếp nhận yêu cầu”, “SMTP chấp nhận”, “đã chuyển phát” và “người nhận đã đọc” |

Với hệ thống gửi số lượng lớn, thao tác Gửi trong MUA hoặc frontend có thể chỉ tạo một công việc trong hàng đợi. Worker xử lý ở backend sau đó mới gọi provider. Cách này không làm thay đổi vị trí MUA trong mô hình: **nơi soạn thư vẫn ở đầu luồng**, còn chuyển phát là quy trình phía sau.

## 8. Các nhầm lẫn thường gặp

**“MUA chính là SMTP server?”**  
Không. MUA phục vụ người dùng và chuẩn bị/yêu cầu gửi thư; SMTP server ở vai trò MSA/MTA tiếp nhận, kiểm tra và chuyển thư. Một sản phẩm có thể tích hợp nhiều vai trò, nhưng đó vẫn là các trách nhiệm khác nhau.

**“Soạn xong email là thư đã được gửi?”**  
Không. Văn bản có thể chỉ nằm trong form hoặc thư nháp. Gửi là bước riêng, có thể thành công, bị từ chối hoặc cần xử lý sau.

**“Email web không có MUA vì trình duyệt không nói chuyện bằng SMTP?”**  
Không. Webmail vẫn cung cấp các chức năng của MUA. Kết nối browser–backend có thể dùng HTTPS; SMTP được xử lý tại dịch vụ phía sau.

**“Spring Framework Mail tự tạo giao diện Compose giống Gmail?”**  
Không. Spring Mail là API cho lập trình viên xây dựng và gửi thông điệp. Muốn người dùng nhập và quản lý bản nháp, ứng dụng phải có giao diện và logic nghiệp vụ tương ứng.

**“Địa chỉ trong To là đủ cho máy chủ chuyển thư?”**  
Không. SMTP còn sử dụng envelope recipients (`RCPT TO`). Danh sách chuyển phát có thể bao gồm địa chỉ Cc/Bcc, còn header quyết định phần lớn thông tin người đọc nhìn thấy.

**“Gửi thành công nghĩa là người nhận đã đọc?”**  
Không. Phản hồi chấp nhận của máy chủ submission, báo cáo chuyển phát và trạng thái đọc là các tín hiệu khác nhau; trạng thái đọc thường không thể suy ra chắc chắn từ SMTP.

## 9. Lần theo một tình huống từ đầu đến cuối

Giả sử hệ thống quản lý dự án có nút “Gửi báo cáo tuần cho nhóm”.

1. **Người dùng chọn người nhận và soạn lời nhắn.** Đây là phần trải nghiệm tương tự MUA; frontend có thể lưu nháp.
2. **Người dùng nhấn Gửi.** Frontend chuyển dữ liệu form qua HTTPS đến backend Spring.
3. **Backend kiểm tra yêu cầu.** Hệ thống xác định người gọi có quyền gửi báo cáo, chọn địa chỉ `From` đã được cấp phép và lấy bản PDF phù hợp.
4. **Spring Mail tạo thông điệp.** `JavaMailSender` cùng `MimeMessageHelper` thiết lập To/Cc/Bcc, Subject, body, MIME và attachment.
5. **Hệ thống nộp thư.** SMTP submission hoặc dịch vụ email API tiếp nhận yêu cầu, xác thực và áp dụng chính sách gửi.
6. **Hạ tầng mail chuyển thư.** Máy chủ vận chuyển định tuyến đến hệ thống của người nhận; thư có thể được nhận, tạm hoãn, từ chối hoặc bị lọc.
7. **Người nhận mở hộp thư.** MUA của họ truy cập mailbox rồi hiển thị tiêu đề, nội dung và tệp đính kèm.

Ở đây, **một MUA hoặc giao diện soạn thư xuất hiện ở phía người gửi**; **một MUA khác xuất hiện ở phía người nhận**. Spring Framework Mail nằm tại bước backend tạo và nộp thông điệp, nối trải nghiệm người dùng với hạ tầng email. Nắm được ranh giới này giúp thiết kế đúng giao diện, API, cấu hình SMTP, xử lý lỗi và cách diễn giải trạng thái gửi thư.
