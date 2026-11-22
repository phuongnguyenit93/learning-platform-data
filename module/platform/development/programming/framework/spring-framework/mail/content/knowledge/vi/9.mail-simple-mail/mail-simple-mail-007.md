# Một message cho nhiều địa chỉ nhận

## 1. Một email có thể gửi đến nhiều người như thế nào?

Trong **Spring Framework Mail**, một đối tượng **SimpleMailMessage** có thể chứa **nhiều địa chỉ nhận**. Thay vì tạo một thông điệp riêng cho từng người, ứng dụng thiết lập danh sách người nhận vào trường **To**, **Cc** hoặc **Bcc**, sau đó gọi **MailSender.send(message)** một lần.

Ví dụ:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("notifications@example.com");
message.setTo(
        "an@example.net",
        "binh@example.net",
        "chi@example.net"
);
message.setSubject("Lịch bảo trì hệ thống");
message.setText("Hệ thống sẽ bảo trì lúc 22:00 ngày mai.");

mailSender.send(message);
~~~

Ở mức API, đây là **một đối tượng message** với **ba địa chỉ To**, được chuyển cho sender bằng **một lời gọi send()**. Hệ thống SMTP sẽ xử lý danh sách các địa chỉ nhận để giao thư. Người nhận có thể nhận các bản phân phối từ cùng nội dung thông điệp; không nên hiểu rằng chỉ có một mailbox được phát thư.

Điểm cần nhớ:

- **Một message**: một tiêu đề, một nội dung, một nhóm header gửi chung.
- **Nhiều recipient**: nhiều địa chỉ ở To/Cc/Bcc, tương ứng các đích chuyển phát.
- **Một lần gọi send()**: ứng dụng nộp yêu cầu gửi một thông điệp qua tầng Spring Mail.
- **Không đồng nghĩa tất cả đã nhận thành công**: phía SMTP có thể từ chối một số recipient, hoặc lỗi có thể xuất hiện ở các chặng sau.

Bài học này tập trung vào **simple mail**, tức thư **văn bản thuần** dùng **SimpleMailMessage**. Nếu cần HTML, file đính kèm hoặc cấu trúc MIME phức tạp, dùng **JavaMailSender** và **MimeMessageHelper**.

## 2. Các thành phần Spring Mail liên quan

| Thành phần | Vai trò |
|---|---|
| **SimpleMailMessage** | Đối tượng biểu diễn email đơn giản: người gửi, người nhận, tiêu đề, nội dung text và một số header liên quan. |
| **MailSender** | Interface Spring cung cấp phương thức gửi một hoặc nhiều SimpleMailMessage. |
| **JavaMailSender** | Interface mở rộng MailSender, đồng thời hỗ trợ các thông điệp MimeMessage. |
| **JavaMailSenderImpl** | Triển khai thông dụng, dùng Jakarta Mail để gửi thông điệp qua SMTP. |
| **To** | Những người nhận chính; danh sách thường được người nhận khác nhìn thấy. |
| **Cc** | Những người nhận bản sao công khai; địa chỉ thường cũng được hiển thị. |
| **Bcc** | Những người nhận bản sao ẩn; địa chỉ vẫn được dùng để chuyển phát nhưng thường không được công khai trong header của thư chuyển tới người khác. |

Một luồng điển hình:

~~~text
       Controller / Scheduled Job / Business Service
                           |
                           v
                     EmailService
                           |
                           v
                  SimpleMailMessage
                   /      |       \
              To: A,B   Cc: C    Bcc: D
                   \      |       /
                    \     |      /
                           v
                MailSender.send(message)
                           |
                           v
                  JavaMailSenderImpl
                           |
                           v
                Jakarta Mail / SMTP
                           |
                           v
                 SMTP server / relay
                           |
                           v
               Các hệ thống nhận thư
~~~

**Spring Mail trừu tượng hóa việc nộp thư từ ứng dụng**, còn quá trình chuyển phát đến từng mailbox phụ thuộc vào SMTP relay, mail server đích và chính sách của các bên.

## 3. API setTo(String...) nhận một hoặc nhiều địa chỉ

**SimpleMailMessage** cung cấp các phương thức setter để thiết lập người nhận. Với danh sách To, có thể truyền một địa chỉ hoặc nhiều địa chỉ:

~~~java
// Một người nhận chính.
message.setTo("an@example.net");

// Nhiều người nhận chính qua varargs.
message.setTo(
        "an@example.net",
        "binh@example.net",
        "chi@example.net"
);
~~~

Trong Java, cú pháp **String...** là *varargs*: caller có thể truyền nhiều đối số String hoặc một **String[]** đã tạo sẵn.

~~~java
String[] recipients = {
        "an@example.net",
        "binh@example.net",
        "chi@example.net"
};

message.setTo(recipients);
~~~

Đây là cách phù hợp khi danh sách nhận được tạo động từ database, cấu hình hoặc một lớp xử lý nghiệp vụ.

### setTo là thao tác thiết lập danh sách, không phải cộng dồn

Một lỗi dễ gặp:

~~~java
message.setTo("an@example.net");
message.setTo("binh@example.net");
~~~

**Không nên kỳ vọng hai lời gọi trên tự ghép hai người nhận**. Setter thiết lập giá trị của trường To; lời gọi sau thay thế danh sách trước. Nếu cần hai người nhận, hãy truyền cả hai trong cùng một lần gọi hoặc tổng hợp mảng trước:

~~~java
message.setTo("an@example.net", "binh@example.net");
~~~

### Đừng giả định chuỗi có dấu phẩy sẽ được tách đúng ở mọi tầng

Không nên coi cách gọi sau là phương thức biểu diễn danh sách rõ ràng:

~~~java
message.setTo("an@example.net, binh@example.net");
~~~

Khi sử dụng **SimpleMailMessage**, biểu diễn nhiều người nhận bằng **các phần tử String riêng biệt** giúp phù hợp trực tiếp với hợp đồng API và tránh phụ thuộc vào việc một tầng nào đó diễn giải chuỗi chứa dấu phẩy. Nếu dữ liệu đầu vào là CSV hoặc một chuỗi danh sách, hãy parse và kiểm tra ở tầng ứng dụng trước khi gọi setTo.

## 4. Ví dụ hoàn chỉnh: một thư thông báo cho nhiều nhân sự

Giả sử ứng dụng cần thông báo lịch bảo trì chung cho ba nhân sự. Cả ba sẽ nhận **cùng tiêu đề và cùng nội dung**, nên một SimpleMailMessage có nhiều To là phương án ngắn gọn.

~~~java
package com.example.notification;

import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;

@Service
public class MaintenanceMailService {

    private final MailSender mailSender;

    public MaintenanceMailService(MailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void announceMaintenance() {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("operations@example.com");
        message.setTo(
                "an@example.net",
                "binh@example.net",
                "chi@example.net"
        );
        message.setSubject("Thông báo bảo trì");
        message.setText("""
                Xin chào,

                Hệ thống sẽ bảo trì từ 22:00 đến 23:00 ngày mai.
                Vui lòng lưu công việc trước thời điểm này.

                Đội ngũ vận hành
                """);

        mailSender.send(message);
    }
}
~~~

**Các bước:**

1. **MaintenanceMailService** nhận interface MailSender bằng constructor injection.
2. **SimpleMailMessage** giữ thông tin từ địa chỉ gửi đến subject và body.
3. **setTo(...)** khai báo ba người nhận.
4. **send(message)** nộp thông điệp cho hệ thống gửi thư; lời gọi đồng bộ thông thường chờ quá trình nộp thư hoặc phát sinh exception.

Ví dụ giả định ứng dụng đã cấu hình một MailSender phù hợp, thường là **JavaMailSenderImpl** qua Spring Boot mail auto-configuration hoặc cấu hình thủ công. Các địa chỉ dùng để minh họa; trong thực tế From phải được tài khoản SMTP hoặc nhà cung cấp cho phép.

### Cấu hình tối thiểu với Spring Boot

Với ứng dụng Spring Boot có dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Một cấu hình SMTP submission điển hình:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: sender@example.com
    password: REPLACE_WITH_SECRET
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
~~~

Đây chỉ là ví dụ cấu hình. Trong ứng dụng thật, password phải được nạp từ biến môi trường hoặc hệ thống quản lý bí mật, không commit vào source code. Host, port, TLS và cơ chế xác thực phải đúng với SMTP server thực tế. Tầng SimpleMailMessage chỉ mô tả thông điệp, không tự tạo SMTP server.

## 5. Kết hợp To, Cc và Bcc trong cùng một message

Một SimpleMailMessage có thể có cả ba nhóm người nhận. Mỗi nhóm mang ý nghĩa giao tiếp khác nhau, dù tất cả đều là đích cần chuyển phát.

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("project@example.com");
message.setTo(
        "owner@example.net",
        "developer@example.net"
);
message.setCc(
        "team-lead@example.net",
        "reviewer@example.net"
);
message.setBcc("audit@example.org");
message.setSubject("Báo cáo tiến độ");
message.setText("Báo cáo tiến độ dự án đã được cập nhật.");

mailSender.send(message);
~~~

| Địa chỉ | Nhóm | Ý nghĩa |
|---|---|---|
| owner@example.net | To | Người nhận chính, chịu trách nhiệm theo dõi. |
| developer@example.net | To | Người nhận chính cùng tham gia xử lý. |
| team-lead@example.net | Cc | Được nhận bản sao để nắm thông tin. |
| reviewer@example.net | Cc | Được nhận bản sao công khai. |
| audit@example.org | Bcc | Nhận bản sao ẩn khỏi danh sách người nhận công khai trong cách xử lý thông thường. |

### Mỗi nhóm có thể chứa nhiều địa chỉ

Các setter hỗ trợ dạng mảng hoặc varargs:

~~~java
String[] to = {"first@example.net", "second@example.net"};
String[] cc = {"manager@example.net", "supervisor@example.net"};
String[] bcc = {"archive@example.org", "observer@example.org"};

message.setTo(to);
message.setCc(cc);
message.setBcc(bcc);
~~~

**Cc không phải chế độ chỉ đọc**: người nhận Cc vẫn thấy nội dung và attachment (nếu có, trong loại message khác). **Bcc không mã hóa nội dung**: người nhận Bcc vẫn đọc được thông điệp như các người nhận khác.

Không có một luồng gửi SMTP độc lập cho To, Cc và Bcc chỉ vì chúng mang tên khác nhau. Phân nhóm chủ yếu phục vụ hiển thị và quy ước giao tiếp, trong khi danh sách người nhận thực tế được sử dụng ở tầng vận chuyển.

## 6. Header của email khác danh sách SMTP recipient

Đây là điểm kỹ thuật quan trọng nhất khi nói đến **một message cho nhiều địa chỉ nhận**.

Email có **header** mô tả thông điệp cho người đọc, ví dụ:

~~~text
From: operations@example.com
To: an@example.net, binh@example.net
Cc: team-lead@example.net
Subject: Thông báo bảo trì
~~~

Nhưng máy chủ SMTP thường nhận danh sách đích thông qua **SMTP envelope**, với các lệnh tương đương:

~~~text
MAIL FROM:<bounces@example.com>
RCPT TO:<an@example.net>
RCPT TO:<binh@example.net>
RCPT TO:<team-lead@example.net>
RCPT TO:<audit@example.org>
DATA
... nội dung thông điệp, gồm header From/To/Cc ...
.
~~~

Trong ví dụ, **audit@example.org** là một người nhận Bcc. Địa chỉ này cần có trong envelope để hệ thống gửi biết đường chuyển phát, nhưng thông thường không xuất hiện trong header To/Cc của thư được người nhận khác nhìn thấy.

Ba điều phải phân biệt:

- **Header From** là địa chỉ người gửi hiển thị; nó có thể khác **envelope MAIL FROM** dùng cho chuyển phát/bounce.
- **Header To/Cc** thể hiện những người nhận công khai; chúng không phải danh sách duy nhất máy chủ có thể giao thư.
- **Bcc** là người nhận thật trong cơ chế chuyển phát, nhưng header Bcc thường được loại bỏ/điều chỉnh khi thư được gửi để tránh công khai danh sách này.

Với SimpleMailMessage, Spring/Jakarta Mail xử lý việc chuyển thông tin người nhận thành thông điệp và yêu cầu SMTP ở tầng gửi. Ứng dụng không nên tự lắp chuỗi raw SMTP hoặc tùy ý thêm các header giả để đạt kết quả tương tự.

## 7. Một message khác gì với nhiều message?

Hai cách triển khai sau có ý nghĩa khác nhau.

### Cách A: Một message, nhiều người nhận

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("notice@example.com");
message.setTo("an@example.net", "binh@example.net");
message.setSubject("Thông báo chung");
message.setText("Hệ thống sẽ bảo trì tối nay.");

mailSender.send(message);
~~~

**Đặc điểm:** cùng subject, cùng body; các địa chỉ To có thể được nhìn thấy bởi các người nhận khác. Đây là **một thông điệp** được nộp để phát tới nhiều địa chỉ.

### Cách B: Mỗi người nhận một message

~~~java
SimpleMailMessage first = new SimpleMailMessage();
first.setFrom("notice@example.com");
first.setTo("an@example.net");
first.setSubject("Thông báo chung");
first.setText("Hệ thống sẽ bảo trì tối nay.");

SimpleMailMessage second = new SimpleMailMessage();
second.setFrom("notice@example.com");
second.setTo("binh@example.net");
second.setSubject("Thông báo chung");
second.setText("Hệ thống sẽ bảo trì tối nay.");

mailSender.send(first, second);
~~~

Ở cách B, **hai SimpleMailMessage khác nhau** được truyền vào overload varargs của **MailSender.send(SimpleMailMessage...)**. Mỗi message chỉ có một người nhận chính. Đây không phải cùng một điều với một message có hai To.

| Tiêu chí | Một message có nhiều To | Nhiều message, mỗi message một To |
|---|---|---|
| Số đối tượng message | Một | Nhiều |
| Số người nhận cuối | Có thể nhiều | Tổng cộng có thể nhiều |
| Header To | Danh sách người nhận chung | Thường chỉ chứa địa chỉ của từng người |
| Subject và nội dung | Cùng một bản cho tất cả | Có thể giống nhau hoặc cá nhân hóa |
| Quyền riêng tư địa chỉ | Các To/Cc thường nhìn thấy nhau | Dễ cô lập địa chỉ giữa các người nhận |
| Ghi nhận trạng thái theo người nhận | Cần theo dõi từng recipient trong một message | Dễ gắn trạng thái riêng cho từng message |
| Thay đổi nội dung theo người nhận | Không phù hợp | Phù hợp |
| Hiệu quả vận chuyển | Có thể giảm số lần nộp thông điệp trong một số cấu hình | Tạo nhiều thông điệp; chi phí phụ thuộc transport/ESP |

**Một lời gọi Java có nhiều message không nhất thiết tương ứng một giao dịch SMTP nguyên tử.** Nếu gọi send(first, second), việc message đầu thành công không bảo đảm message sau cũng thành công.

## 8. Gửi danh sách người nhận được tạo động

Trong ứng dụng thực tế, người nhận thường lấy từ một service nghiệp vụ hoặc database. Nên **tổng hợp và kiểm tra danh sách** trước khi thiết lập SimpleMailMessage.

Ví dụ service nhận danh sách địa chỉ đã được tầng ứng dụng cho phép:

~~~java
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

@Service
public class GroupNoticeService {

    private final MailSender mailSender;

    public GroupNoticeService(MailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotice(List<String> selectedRecipients) {
        Objects.requireNonNull(selectedRecipients, "recipients");

        Set<String> unique = new LinkedHashSet<>();
        for (String address : selectedRecipients) {
            if (address == null || address.isBlank()) {
                throw new IllegalArgumentException(
                        "Danh sách người nhận chứa địa chỉ trống"
                );
            }
            unique.add(address.trim());
        }

        if (unique.isEmpty()) {
            throw new IllegalArgumentException(
                    "Cần ít nhất một người nhận"
            );
        }

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("notifications@example.com");
        message.setTo(unique.toArray(String[]::new));
        message.setSubject("Thông báo nhóm");
        message.setText("Nội dung thông báo được gửi chung cho nhóm.");

        mailSender.send(message);
    }
}
~~~

**LinkedHashSet** ở đây giữ thứ tự và loại bỏ các chuỗi địa chỉ trùng khớp chính xác. Đây chỉ là cách lọc trùng đơn giản cho ví dụ; nó không đồng nghĩa đã chuẩn hóa đầy đủ email address theo quy tắc của từng hệ thống. Không tự ý chuyển mọi local-part thành chữ thường hoặc biến đổi địa chỉ bằng các quy tắc chưa được xác nhận.

Ứng dụng vẫn cần kiểm tra **cú pháp địa chỉ**, **quyền nhận thông tin** và **giới hạn số lượng người nhận** trước khi gọi send(). SimpleMailMessage là đối tượng dữ liệu, không phải dịch vụ xác minh mailbox tồn tại. Một địa chỉ đúng cú pháp vẫn có thể bị máy chủ đích từ chối hoặc không có người nhận thực tế.

### Nếu dữ liệu ban đầu là danh sách khách hàng

Khi danh sách gồm các khách hàng không liên quan, điều quan trọng không chỉ là chuyển từ List sang String[]. Cần xác định xem họ có được phép biết địa chỉ của nhau hoặc đọc chung nội dung không. Nếu không, **mỗi khách hàng cần một message riêng** hoặc một cơ chế phân phối phù hợp bảo vệ địa chỉ.

## 9. Dùng Bcc khi muốn ẩn địa chỉ công khai

Với một thông báo giống nhau gửi cho nhóm nhỏ, Bcc có thể giúp hạn chế việc công khai danh sách người nhận trong header:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("announcement@example.com");
message.setTo("announcement@example.com");
message.setBcc(
        "member-a@example.net",
        "member-b@example.net",
        "member-c@example.net"
);
message.setSubject("Thông báo chung");
message.setText("Nội dung áp dụng chung cho tất cả thành viên.");

mailSender.send(message);
~~~

Ví dụ đặt một địa chỉ **To** do tổ chức thực sự quản lý để thư có người nhận công khai rõ ràng; địa chỉ này cũng được nhận thư, vì vậy phải có mục đích và quyền sử dụng hợp lệ. Không dùng một địa chỉ của người khác làm To chỉ để che danh sách.

### Giới hạn của Bcc

- Địa chỉ Bcc thường không xuất hiện trong bản header của người nhận To/Cc, nhưng **SMTP server và nhà cung cấp gửi vẫn biết** vì cần chuyển thư.
- Bcc **không mã hóa** subject, nội dung hay attachment và không kiểm soát người nhận có chuyển tiếp thư hay không.
- Người nhận Bcc có thể tự tiết lộ việc nhận thư khi trả lời hoặc chuyển tiếp.
- Cách tạo bản sao Bcc có thể khác nhau theo hệ thống gửi; không nên kỳ vọng mọi client hay provider hiển thị chính xác cùng một dạng header.
- Bcc không tự giải quyết hạn mức người nhận, bộ lọc spam hoặc yêu cầu cá nhân hóa.

Nếu mỗi người có một URL xác nhận, token, mật khẩu tạm, số tiền hoặc dữ liệu riêng, **không gộp họ vào một message Bcc**: tất cả những người nhận sẽ nhận cùng nội dung, dẫn đến rủi ro lộ thông tin.

## 10. Khi nào nên gửi chung và khi nào nên tách thư?

### Gửi một message chung khi

- Nội dung gửi đến mọi người **hoàn toàn giống nhau** và không chứa dữ liệu riêng của một cá nhân.
- Danh sách người nhận nhỏ, đã được xác định và cho phép nhận thông tin.
- Việc công khai địa chỉ trong To/Cc là phù hợp với nhóm, hoặc Bcc được sử dụng có cân nhắc.
- Không cần trạng thái gửi riêng, URL riêng hay nội dung riêng cho từng người.
- Hạn mức người nhận của SMTP server/ESP cho phép.

Ví dụ phù hợp: email phối hợp nội bộ giữa những người đang cùng làm một nhiệm vụ, hoặc một thông báo nhóm nhỏ không chứa dữ liệu riêng.

### Gửi message riêng khi

- Thư chứa mã OTP, link đặt lại mật khẩu, dữ liệu tài khoản, hóa đơn, dữ liệu đơn hàng hay thông tin riêng.
- Mỗi người cần tên chào, thời hạn, ngôn ngữ, link hoặc nội dung khác nhau.
- Các người nhận không nên biết địa chỉ email của nhau.
- Ứng dụng cần ghi nhận trạng thái, bounce, retry và thống kê cho từng người.
- Danh sách lớn, cần batch, rate limit, quản lý consent hoặc unsubscribe.

Ví dụ không nên gộp:

~~~java
// Không phù hợp: mọi người sẽ thấy cùng resetLink.
SimpleMailMessage message = new SimpleMailMessage();
message.setTo("user-a@example.net", "user-b@example.net");
message.setSubject("Đặt lại mật khẩu");
message.setText("Truy cập: " + resetLink);
mailSender.send(message);
~~~

Đối với reset password, ứng dụng cần phát sinh **request/token phù hợp với từng tài khoản**, có thời hạn và được kiểm soát quyền, rồi gửi message riêng cho đúng người nhận.

## 11. Giới hạn số lượng recipient và kích thước thông điệp

**SimpleMailMessage.setTo(String...)** không định nghĩa một con số chung như “tối đa 100 địa chỉ” cho mọi môi trường. Giới hạn thực tế đến từ nhiều nơi:

- SMTP server hoặc ESP giới hạn **recipient trên một thông điệp**.
- Tài khoản gửi có giới hạn **số thư, số người nhận, tốc độ gửi** theo giờ/ngày.
- Nhà cung cấp hoặc gateway có giới hạn **kích thước email**.
- SMTP relay có thể tạm hoãn, giới hạn tốc độ hoặc từ chối khi vượt quota.
- Mail server nhận có chính sách lọc số lượng người nhận, tần suất hoặc uy tín nguồn gửi.

Vì vậy, dù API cho phép khai báo một danh sách dài, **không nên biến một message với hàng nghìn To thành mặc định cho mọi tác vụ gửi hàng loạt**.

Nếu cần gửi cho danh sách lớn, có thể chia nhóm (*batch*) để kiểm soát số recipient trong từng lần nộp thư. Tuy nhiên, việc chia thành nhiều batch tạo ra **nhiều message riêng**, làm thay đổi hành vi theo dõi và có thể ảnh hưởng đến header/message ID. Tốt hơn nữa, khi cần bảo vệ địa chỉ và thống kê từng người, hãy gửi từng message qua worker hoặc dịch vụ email hàng loạt được thiết kế cho mục đích đó.

### Batch không phải một lời gọi send() thần kỳ

Giả sử hệ thống có 500 địa chỉ và nhà cung cấp chấp nhận tối đa 50 recipient trên một thông điệp. Có thể cần 10 nhóm, mỗi nhóm là một SimpleMailMessage riêng; nhưng con số giới hạn phải lấy từ provider thật, không đoán.

Những yêu cầu nghiệp vụ khác cần cân nhắc:

1. Có cho phép gửi lại một nhóm nếu nhóm đó thất bại không?
2. Nếu một recipient bị từ chối, có được tiếp tục gửi cho những người khác?
3. Nếu gửi trùng một nhóm sau timeout, các người nhận có thể nhận hai bản?
4. Có cần theo dõi người nào đã nhận, bounce hoặc hủy đăng ký không?

Phân nhóm giúp kiểm soát tải, nhưng không tự giải quyết tất cả câu hỏi trên.

## 12. Kết quả send() có ý nghĩa gì khi có nhiều người nhận?

Với cách dùng phổ biến, Spring Mail gọi transport SMTP để nộp message. SMTP thực hiện trao đổi với địa chỉ gửi ở envelope và các địa chỉ người nhận, có thể kiểm tra từng recipient ở lệnh **RCPT TO**.

Một luồng đơn giản:

~~~text
Spring application                       SMTP submission server
        |                                           |
        | --- MAIL FROM --------------------------> |
        | <------------------------------ response |
        | --- RCPT TO: an@example.net ------------> |
        | <------------------------------ response |
        | --- RCPT TO: binh@example.net ----------> |
        | <------------------------------ response |
        | --- DATA -------------------------------> |
        | <------------------------------ response |
        |                                           |
    send() trả về hoặc ném exception                  |
~~~

Máy chủ có thể chấp nhận một người nhận nhưng từ chối người khác, tùy chính sách. Jakarta Mail và SMTP transport có hành vi liên quan đến việc tiếp tục gửi khi một số recipient không hợp lệ; cấu hình như **mail.smtp.sendpartial** cũng có thể ảnh hưởng đến cách xử lý. Do đó:

- **Không mặc định một người nhận lỗi nghĩa là tất cả người còn lại chắc chắn chưa được gửi.**
- **Không mặc định send() không ném exception nghĩa là tất cả đã vào Inbox.**
- **Không tự động retry toàn bộ danh sách khi không biết rõ nhóm nào đã được chấp nhận**, vì có thể tạo thư trùng.
- Khi cần kết quả chính xác theo từng địa chỉ, phải dùng thông tin lỗi chi tiết, log SMTP/ESP hoặc cơ chế theo dõi riêng của nhà cung cấp.

### SMTP accepted khác với delivered

SMTP server đầu tiên có thể chấp nhận thư để tiếp tục xử lý. Sau đó còn các chặng DNS/MX, relay, hệ thống lọc spam, mailbox và email client. Vì vậy một message nhiều người nhận có thể có kết quả cuối **khác nhau theo từng địa chỉ**, dù ứng dụng chỉ gọi một lần send().

~~~text
                    Một SimpleMailMessage
                              |
                     MailSender.send()
                              |
                    SMTP relay chấp nhận
                        /     |      \
                       v      v       v
                   Recipient A B       C
                       |      |       |
                   Đã nhận  Defer   Bounce
                       |
                      Inbox / Spam / thư mục khác
~~~

Những trạng thái Defer, Bounce hoặc Delivered ở các chặng sau thường không được phản hồi trực tiếp qua return value của **send()**. Hạ tầng ESP có thể cung cấp logs, webhook, delivery event hoặc báo cáo bounce.

## 13. Xử lý exception khi gửi chung một message

Spring Framework Mail sử dụng họ **MailException** để biểu diễn lỗi gửi thư. Ví dụ:

| Exception | Tình huống thường gặp | Hướng điều tra |
|---|---|---|
| **MailAuthenticationException** | SMTP AUTH thất bại | Kiểm tra credentials, quyền tài khoản, cơ chế xác thực. |
| **MailSendException** | Lỗi khi vận chuyển hoặc gửi thư | Xem nguyên nhân gốc, SMTP response và phạm vi người nhận bị ảnh hưởng. |
| **MailParseException** | Thông điệp/địa chỉ không hợp lệ trong quá trình chuyển đổi | Kiểm tra giá trị địa chỉ, header và thông tin lỗi. |

Ví dụ để tầng điều phối phân biệt một lỗi xác thực rõ ràng với các lỗi gửi chung:

~~~java
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.MailSender;

public final class GroupMailDispatcher {

    private final MailSender sender;

    public GroupMailDispatcher(MailSender sender) {
        this.sender = sender;
    }

    public void dispatch(SimpleMailMessage message) {
        try {
            sender.send(message);
        } catch (MailAuthenticationException ex) {
            // Cần sửa credential hoặc quyền gửi SMTP.
            throw ex;
        } catch (MailException ex) {
            // Tầng ngoài ghi nhận loại lỗi, message/attempt ID
            // và quyết định điều tra hay retry có điều kiện.
            throw ex;
        }
    }
}
~~~

Đoạn mã chỉ minh họa **ranh giới xử lý lỗi**, chưa triển khai một chính sách retry hoàn chỉnh. Với một thư nhiều recipient, cần tìm hiểu **phạm vi đã được SMTP server chấp nhận** trước khi thử lại toàn bộ. **MailSendException** có thể giữ các thông tin thất bại ở mức message; điều đó không thay thế log recipient/delivery của SMTP provider.

### Lỗi tạm thời, vĩnh viễn và chưa rõ kết quả

**Tạm thời:** server quá tải, kết nối không ổn định, phản hồi SMTP 4xx. Có thể retry với backoff, giới hạn lần thử và theo dõi kết quả.

**Vĩnh viễn:** địa chỉ không hợp lệ, tài khoản gửi bị từ chối, policy không cho relay, nội dung bị chặn theo quy tắc. Sửa dữ liệu hoặc cấu hình trước khi gửi lại.

**Chưa rõ:** kết nối đứt sau khi client đã nộp DATA nhưng chưa đọc được phản hồi chấp nhận. Có khả năng server đã nhận email; gửi lại có thể làm các người nhận nhận bản thứ hai. Nên ghi nhận trạng thái **UNKNOWN** và đối soát khi provider hỗ trợ.

## 14. Quyền riêng tư, bảo mật và trách nhiệm với người nhận

**Gửi một message đến nhiều To có thể tiết lộ danh sách email** cho các thành viên trong cùng email, vì header To và Cc thông thường được người nhận thấy. Đây có thể là hành vi hoàn toàn hợp lý trong nhóm dự án, nhưng không phù hợp khi gửi dữ liệu cho khách hàng không liên quan.

Những điểm cần kiểm soát:

1. **Quyền nhận thông tin:** người trong nhóm có được phép xem toàn bộ nội dung chung không?
2. **Quyền biết địa chỉ:** có được phép công khai địa chỉ To/Cc giữa các người nhận không?
3. **Tính cá nhân hóa:** có token, số đơn hàng, số tiền, link riêng hoặc dữ liệu người dùng trong nội dung không?
4. **Người nhận bổ sung:** Cc và Bcc có cùng quyền đọc nội dung không, và đã được xét chính sách truy cập chưa?
5. **Dữ liệu log:** không ghi toàn bộ danh sách địa chỉ, OTP hoặc nội dung nhạy cảm vào log nếu không cần thiết.
6. **Consent và unsubscribe:** nếu là thư tiếp thị, phải tôn trọng việc đăng ký/hủy nhận và chính sách liên quan.

### Bcc là giới hạn về hiển thị, không phải bảo mật đầu cuối

Bcc giúp tránh hiển thị địa chỉ trong header ở cách xử lý thông thường. Tuy nhiên, các hệ thống SMTP vẫn phải biết đích, người được Bcc vẫn nhận nội dung, và họ có thể forward hoặc Reply All làm lộ sự tham gia. Nếu cần bảo vệ dữ liệu riêng cho từng người, **gửi từng message riêng** là thiết kế phù hợp hơn.

### Tên người nhận hoặc dữ liệu từ request

Đừng nhận tùy ý danh sách email từ một API rồi gửi thư cho mọi địa chỉ mà không xác minh quyền thao tác. Có thể cần xác thực người gọi, kiểm tra từng recipient thuộc nhóm được phép, giới hạn số lượng và chống lạm dụng endpoint gửi mail.

SimpleMailMessage quản lý nội dung text đơn giản; nó không tự làm những bước kiểm soát nghiệp vụ này.

## 15. Một message cho nhiều người không đồng nghĩa gửi không đồng bộ

Theo cách dùng thông thường, **mailSender.send(message)** thực hiện việc gửi đồng bộ trên thread gọi. Việc có năm hay mười người nhận không biến lời gọi thành một job nền tự động.

Đối với một request web cần phản hồi nhanh hoặc hệ thống phải gửi lượng lớn, có thể tách gửi thư thành một worker:

~~~text
Business event / HTTP request
             |
             v
     Ghi ý định gửi thông báo
             |
             v
      Queue / Outbox record
             |
             v
          Mail worker
             |
             v
    Build SimpleMailMessage
             |
             v
       MailSender.send()
             |
             v
           SMTP/ESP
~~~

Nếu quyết định gửi **một message cho nhiều người**, bản ghi công việc phải giữ được danh sách recipient và dữ liệu chung tại thời điểm hợp lệ. Nếu quyết định gửi **một message riêng cho từng người**, có thể tạo công việc hoặc trạng thái gửi theo recipient để retry và giám sát chính xác hơn.

**Queue hoặc transactional outbox không tự bảo đảm exactly-once delivery.** Nếu worker gửi xong nhưng chết trước khi cập nhật trạng thái, việc retry có thể gây trùng. Khi một message có nhiều recipient, rủi ro lặp lại liên quan đến cả nhóm, nên càng cần quản lý attempt và khả năng đối soát.

## 16. Quan sát và kiểm tra hành vi ở tầng ứng dụng

Khi kiểm tra một service gửi chung, có thể dùng mock **MailSender** để quan sát một lần gọi send() và danh sách To/Cc/Bcc được thiết lập. Đây là kiểm tra ở tầng ứng dụng, không cần kết nối SMTP thật.

Ví dụ minh họa với JUnit 5 và Mockito:

~~~java
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.mockito.Mockito.*;

class MaintenanceMailServiceTest {

    @Test
    void sendsOneMessageToThreeRecipients() {
        MailSender sender = mock(MailSender.class);
        MaintenanceMailService service = new MaintenanceMailService(sender);

        service.announceMaintenance();

        ArgumentCaptor<SimpleMailMessage> captured =
                ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(sender).send(captured.capture());

        SimpleMailMessage actual = captured.getValue();
        assertArrayEquals(
                new String[] {
                        "an@example.net",
                        "binh@example.net",
                        "chi@example.net"
                },
                actual.getTo()
        );
    }
}
~~~

Ví dụ giả định project có JUnit 5 và Mockito. Nó minh họa cách xác định **một SimpleMailMessage** chứa **ba địa chỉ nhận** và được giao cho MailSender. Để thử nghiệm việc SMTP server nhận thông điệp, có thể dùng SMTP test server hoặc sandbox của nhà cung cấp; những phép thử đó thuộc phạm vi tích hợp khác.

Khi vận hành thực tế, nên theo dõi:

| Thông tin | Tác dụng |
|---|---|
| **Notification ID** | Định danh ý định gửi thông báo. |
| **Attempt ID** | Phân biệt các lần nộp lại thông điệp. |
| **Recipient count** | Biết số đích gửi trong một message, phát hiện vượt giới hạn. |
| **SMTP response / exception type** | Chẩn đoán lỗi tại chặng nộp thư. |
| **Provider message ID** | Tra cứu trạng thái ở ESP/MTA. |
| **Bounce, deferred, delivered events** | Quan sát kết quả ở các chặng sau nếu nhà cung cấp hỗ trợ. |

Không giả định chỉ có một trạng thái cuối chung cho mọi recipient. Trên thực tế, một số người có thể nhận thành công còn số khác bị trì hoãn, từ chối hoặc đưa vào Spam.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân điển hình | Cách xử lý |
|---|---|---|
| Chỉ người cuối nhận thư | Gọi setTo nhiều lần và ghi đè danh sách | Gom địa chỉ vào một lần setTo hoặc một String[]. |
| Chuỗi nhiều địa chỉ bị xử lý sai | Truyền một String chứa dấu phẩy và kỳ vọng nó tự tách | Parse thành từng địa chỉ và truyền bằng varargs/String[]. |
| Không có người nhận | Mảng/list rỗng hoặc dữ liệu bị lọc hết | Kiểm tra danh sách trước khi tạo message. |
| Email bị từ chối ở SMTP | Một hoặc nhiều recipient không hợp lệ, bị cấm relay hoặc vượt giới hạn | Xem SMTP response và chính sách của provider. |
| Người dùng nhìn thấy email của người khác | Đặt danh sách khách hàng vào To/Cc | Gửi riêng cho từng người hoặc cân nhắc Bcc với nội dung chung. |
| Người nhận Bcc bị lộ khi trả lời | Người nhận chủ động Reply All hoặc forward | Hiểu giới hạn Bcc; chọn luồng gửi khác nếu cần bảo mật cao. |
| Mọi người nhận chung một link/token | Dùng một message cho nội dung cần cá nhân hóa | Tạo token và message riêng cho từng tài khoản. |
| Gửi trùng nhiều người sau retry | Kết quả gửi trước không rõ nhưng toàn bộ danh sách được gửi lại | Theo dõi attempt, đối soát trạng thái rồi retry có điều kiện. |
| Gửi chung bị giới hạn | Vượt quota recipient/message hoặc rate limit | Giảm nhóm, dùng worker và chiến lược gửi phù hợp với provider. |
| send() thành công nhưng người nhận không thấy thư | Thư còn ở queue, bị bounce muộn hoặc vào Spam | Tra log ESP, DNS/policy nhận và mailbox. |

### Lỗi do danh sách bị trùng ở các trường

Nếu cùng một địa chỉ xuất hiện ở cả To và Cc, hoặc xuất hiện lặp trong một mảng, hành vi gửi thực tế phụ thuộc tầng xử lý và mail server. Không nên dựa vào hệ thống gửi để tự khử trùng tuyệt đối. Tầng nghiệp vụ nên có quy tắc rõ ràng: địa chỉ nào là To, địa chỉ nào là Cc, và có cần loại bỏ trùng giữa các nhóm hay không.

Nếu một người cần được ẩn ở Bcc, đừng đồng thời đưa họ vào To/Cc; nếu không, địa chỉ có thể lộ qua trường công khai.

## 18. Quy tắc chọn thiết kế phù hợp

Khi đứng trước yêu cầu “gửi cho nhiều địa chỉ”, có thể quyết định theo thứ tự:

1. **Nội dung có giống nhau hoàn toàn không?** Nếu mỗi người có nội dung riêng, dùng nhiều message.
2. **Người nhận có được biết email của nhau không?** Nếu có và cùng trao đổi công việc, To/Cc có thể hợp lý; nếu không, gửi riêng hoặc dùng Bcc cho thông báo chung nhỏ.
3. **Có cần theo dõi kết quả riêng của từng người không?** Nếu có, gửi riêng giúp hệ thống trạng thái dễ thiết kế hơn.
4. **Nhà cung cấp cho phép bao nhiêu người nhận trên một message?** Tôn trọng giới hạn thực tế, không dựa vào khả năng lưu trữ của String[].
5. **Nếu một người bị từ chối hoặc trạng thái gửi không rõ, retry sẽ ra sao?** Xác định chính sách trước khi triển khai.

Với một nhóm nhỏ cùng làm việc và nhận cùng một thông báo, **một SimpleMailMessage với nhiều địa chỉ To/Cc** là cách đơn giản, đúng mục đích. Với người dùng độc lập và dữ liệu cá nhân, **nhiều SimpleMailMessage, mỗi message có một người nhận**, thường là lựa chọn dễ bảo vệ dữ liệu và theo dõi.

## 19. Ghi nhớ

**SimpleMailMessage.setTo(String...)** cho phép đưa nhiều địa chỉ người nhận vào **một message**. Có thể thiết lập tương tự với **setCc(String...)** và **setBcc(String...)**, rồi gọi **MailSender.send(message)** để nộp thông điệp cho hệ thống SMTP. Một message chứa một subject và một body chung; các địa chỉ là nhiều đích chuyển phát của cùng thông điệp đó.

Đừng nhầm **một message có nhiều recipient** với **nhiều message gửi qua một lần gọi send(...)**. Cách đầu phù hợp với thông báo chung và nhóm nhận được phép biết nhau; cách sau phù hợp hơn với nội dung cá nhân hóa, quyền riêng tư và trạng thái gửi theo từng người. Khi thiết kế, luôn xét giới hạn SMTP, khả năng thất bại một phần, rủi ro gửi trùng và nghĩa chính xác của kết quả **send()**.
