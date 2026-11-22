# Phân biệt gửi thư với đọc, đồng bộ và quản lý hộp thư

Trong một ứng dụng Spring, yêu cầu “tích hợp email” có thể chỉ là gửi thông báo đặt hàng, nhưng cũng có thể là đọc thư khách hàng gửi đến, giữ dữ liệu hộp thư nhất quán với máy chủ, hoặc chuyển thư giữa các thư mục. Bốn nhu cầu này dùng những thao tác và giao thức khác nhau. Hiểu rõ ranh giới ngay từ đầu giúp chọn đúng thành phần, tránh thiết kế một hệ thống gửi thư như thể nó cũng là hệ thống quản lý inbox.

Ở mức nhập môn, hãy phân biệt theo **hành động mà ứng dụng muốn thực hiện**:

- **Gửi thư (sending):** ứng dụng tạo một thông điệp và yêu cầu máy chủ chuyển thư đến người nhận.
- **Đọc thư (reading):** ứng dụng truy xuất thư đã nằm trong một hộp thư để xem thông tin, nội dung hoặc tệp đính kèm.
- **Đồng bộ thư (synchronization):** ứng dụng theo dõi thay đổi qua thời gian để giữ bản dữ liệu cục bộ phù hợp với hộp thư trên máy chủ.
- **Quản lý hộp thư (mailbox management):** ứng dụng thay đổi trạng thái hoặc cấu trúc của hộp thư, ví dụ đánh dấu đã đọc, gắn cờ, chuyển thư hay xóa thư.

Điểm cốt lõi: **Spring Framework Mail tập trung vào chức năng gửi email.** Việc đọc, đồng bộ và quản lý hộp thư cần những API hoặc thành phần khác, thường dựa trên IMAP, POP3 hay API riêng của nhà cung cấp dịch vụ email.

## 1. Nhìn toàn cảnh: email được gửi và được đọc ở hai đầu khác nhau

Một email không được “đẩy thẳng” từ phương thức Java đến danh sách thư trong ứng dụng của người nhận. Trong mô hình thông dụng, ứng dụng giao thư cho máy chủ gửi đi; hạ tầng email chuyển thư; sau đó người nhận truy xuất thư từ hộp thư của họ.

~~~text
Ứng dụng Spring của bên gửi
        |
        | Tạo nội dung + gửi qua SMTP (submission)
        v
Máy chủ gửi thư / dịch vụ email
        |
        | Định tuyến và chuyển phát
        v
Máy chủ nhận thư + nơi lưu hộp thư
        |
        +---- IMAP / POP3 / API nhà cung cấp ----> Ứng dụng đọc thư
        |
        +---- IMAP / API nhà cung cấp -----------> Ứng dụng đồng bộ,
                                                   gắn cờ, chuyển, xóa thư
~~~

Sơ đồ mô tả các vai trò logic. Một nhà cung cấp có thể vận hành chung nhiều vai trò trên cùng hệ thống, và ứng dụng cũng có thể vừa gửi vừa đọc, nhưng **mỗi hướng tương tác vẫn là một bài toán riêng**.

| Nghiệp vụ | Câu hỏi chính | Giao thức/API thường gặp | Trạng thái cần quan tâm | Ví dụ thực tế |
| --- | --- | --- | --- | --- |
| Gửi thư | Làm sao chuyển thông điệp ra ngoài? | SMTP submission hoặc API gửi thư qua HTTP | Yêu cầu gửi, kết quả chấp nhận, lỗi, lịch sử gửi | Gửi OTP, hóa đơn, thông báo |
| Đọc thư | Hiện có thư nào và nội dung ra sao? | IMAP, POP3, API đọc thư | Thư đang tồn tại ở thời điểm đọc | Xem email hỗ trợ khách hàng |
| Đồng bộ | Có gì mới, thay đổi hoặc bị xóa kể từ lần trước? | IMAP với cơ chế theo dõi thay đổi, polling, IDLE hoặc API delta/webhook | Checkpoint, định danh, cờ, trạng thái xóa | Đồng bộ inbox vào cơ sở dữ liệu |
| Quản lý hộp thư | Muốn sửa trạng thái hay tổ chức thư thế nào? | IMAP hoặc API quản lý thư | Quyền ghi, thư mục/nhãn, cờ, chính sách xóa | Đánh dấu đã xử lý, chuyển thư |

Một thao tác **đọc một lần** chưa phải **đồng bộ**. Một thao tác **gửi thành công ở mức SMTP** cũng chưa chứng minh người nhận đã mở thư.

## 2. Gửi thư: tạo thông điệp và chuyển cho máy chủ gửi

### 2.1. SMTP đảm nhiệm vai trò gì?

**SMTP (Simple Mail Transfer Protocol)** là giao thức nền tảng để gửi và chuyển email. Ứng dụng thường kết nối tới điểm tiếp nhận thư gửi (message submission) của nhà cung cấp qua SMTP có xác thực, chẳng hạn cổng 587 với STARTTLS hoặc cổng 465 với TLS ngay từ đầu, tùy cấu hình dịch vụ.

Quy trình tối giản:

1. Ứng dụng tạo thông điệp có người nhận, tiêu đề và nội dung.
2. Ứng dụng kết nối tới SMTP server bằng cấu hình phù hợp và thực hiện xác thực nếu dịch vụ yêu cầu.
3. SMTP server chấp nhận hoặc từ chối yêu cầu gửi.
4. Hạ tầng email tiếp tục định tuyến và thử chuyển phát đến máy chủ nhận; thư có thể bị trì hoãn, trả về (bounce) hoặc bị lọc.

SMTP còn phân biệt **phong bì vận chuyển** (envelope sender/recipients dùng trong phiên giao thức) với các **header của email** như From, To, Subject. Hai lớp dữ liệu thường tương ứng nhau nhưng không đồng nhất tuyệt đối. Khi chẩn đoán gửi thư, cần biết đang nói về địa chỉ trong phong bì hay địa chỉ hiển thị trong thông điệp.

**Giới hạn quan trọng:** lời gọi gửi không phát sinh một API để liệt kê inbox, đọc lại thư, đánh dấu thư đã đọc hoặc chuyển thư sang thư mục. Đó là các chức năng ở phía lưu trữ hộp thư.

### 2.2. Spring Framework Mail hỗ trợ gửi thư như thế nào?

Trong Spring Framework, các khái niệm cơ bản gồm:

- **MailSender:** giao diện gửi thông điệp văn bản đơn giản thông qua **SimpleMailMessage**.
- **JavaMailSender:** giao diện mở rộng hỗ trợ gửi email dạng MIME, tức nội dung HTML, nhiều phần (multipart), tệp đính kèm và các đặc điểm cần thiết khác.
- **JavaMailSenderImpl:** triển khai gửi thư phổ biến dựa trên thư viện Jakarta Mail.
- **MimeMessageHelper:** tiện ích giúp dựng thông điệp MIME thuận tiện hơn.
- **MailException** cùng các loại ngoại lệ liên quan: phản ánh lỗi mà Spring phát hiện trong lúc gửi.

Spring Boot có thể tự cấu hình một **JavaMailSender** khi ứng dụng khai báo starter mail và cung cấp các thuộc tính phù hợp. Đây là cách tích hợp thông thường trong ứng dụng Spring Boot; nó vẫn phục vụ hướng **gửi**.

Ví dụ dependency Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Ví dụ cấu hình SMTP trong **application.yml** (địa chỉ chỉ mang tính minh họa):

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 5000
      mail.smtp.writetimeout: 5000
~~~

Tên đăng nhập và thông tin xác thực có thể được nạp qua biến môi trường **SPRING_MAIL_USERNAME** và **SPRING_MAIL_PASSWORD** hoặc hệ thống quản lý bí mật. Không đưa mật khẩu thực vào mã nguồn hay tài liệu. Cấu hình xác thực, TLS và cổng phải tuân theo hướng dẫn của dịch vụ SMTP đang dùng.

Một dịch vụ gửi thư văn bản đơn giản:

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

    public void sendWelcome(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("noreply@example.org");
        message.setTo(recipient);
        message.setSubject("Chào mừng");
        message.setText("Cảm ơn bạn đã đăng ký tài khoản.");

        mailSender.send(message);
    }
}
~~~

**Điều xảy ra:** phương thức tạo thông điệp rồi dùng **JavaMailSender** gửi tới SMTP server đã cấu hình. **Điều không xảy ra:** phương thức không kết nối inbox của người nhận để kiểm tra thư có nằm ở đó hay đã được đọc chưa.

Khi cần HTML hoặc tệp đính kèm, ứng dụng tạo **MimeMessage** và dùng **MimeMessageHelper**. Dù biểu diễn phức tạp hơn, đây vẫn là nghiệp vụ gửi.

### 2.3. “Gửi thành công” có nghĩa chính xác là gì?

Cần phân biệt các mốc:

| Mốc | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| Tạo được đối tượng email | Dữ liệu thông điệp đã được dựng | SMTP server đã chấp nhận |
| Lời gọi gửi hoàn tất không lỗi | Thành phần gửi đã hoàn tất trao đổi cần thiết theo phản hồi nhận được | Thư chắc chắn đã vào inbox người nhận |
| Dịch vụ gửi xác nhận đã tiếp nhận | Hệ thống gửi đã nhận trách nhiệm xử lý theo hợp đồng dịch vụ | Người nhận đã nhìn thấy hoặc đọc thư |
| Hệ thống báo phát thành công | Dịch vụ ghi nhận chuyển phát theo ngữ nghĩa của nó | Thư không bị lọc, người nhận đã đọc |
| Có sự kiện mở/đọc | Có một tín hiệu theo dõi hoặc biên nhận | Luôn xác thực được người thực sự đã đọc |

Thư có thể bị giữ trong hàng đợi, bounce, lọc spam hoặc chặn vì cấu hình miền gửi. SPF, DKIM và DMARC giúp xác thực miền và chính sách email; chúng không thay thế cơ chế đọc hộp thư. Các tín hiệu “opened” trong công cụ email marketing cũng không phải bằng chứng tuyệt đối vì client có thể chặn hoặc tự tải nội dung từ xa.

Một điểm dễ nhầm khác: **gửi qua SMTP không mặc nhiên tạo một bản sao trong thư mục Sent của bất kỳ tài khoản nào**. Việc lưu vào Sent phụ thuộc dịch vụ, client hoặc một thao tác lưu thư riêng.

## 3. Đọc thư: truy xuất email đã nằm trong hộp thư

Đọc thư chuyển bài toán từ “đẩy thông điệp ra ngoài” thành “truy cập kho thư đã được máy chủ lưu giữ”. Thông thường, ứng dụng cần quyền truy cập một tài khoản/hộp thư và cơ chế liệt kê, lấy header, lấy nội dung.

### 3.1. Ba hướng truy cập thường gặp

| Cách truy cập | Đặc điểm | Phù hợp khi |
| --- | --- | --- |
| **IMAP** | Làm việc với thư nằm trên server; hỗ trợ thư mục và nhiều cờ trạng thái; có khả năng truy vấn/cập nhật thư | Cần đọc và duy trì góc nhìn nhất quán giữa nhiều client |
| **POP3** | Tập trung lấy thư từ hộp nhận, chức năng đồng bộ trạng thái và thư mục hạn chế hơn IMAP | Trường hợp đơn giản hoặc hệ thống cũ chỉ cần tải thư |
| **API nhà cung cấp** | API HTTP có mô hình thư, nhãn, sự kiện và quyền riêng của nhà cung cấp | Tích hợp chặt với Gmail, Microsoft 365 hoặc nền tảng có API chuyên dụng |

Cổng thường gặp của IMAP là 143 (có thể nâng cấp TLS) hoặc 993 (TLS ngay từ đầu); POP3 thường dùng 110 hoặc 995. Đây là thông tin định hướng, không thay cho cấu hình chính thức của máy chủ.

**IMAP không phải SMTP chạy theo chiều ngược lại.** SMTP chuyển thông điệp giữa các bên gửi/nhận; IMAP cho phép truy cập và thao tác trên một mailbox.

### 3.2. Đọc thư bằng Jakarta Mail trong ứng dụng Spring

Thư viện Jakarta Mail có các khái niệm **Session**, **Store**, **Folder** và **Message**:

- **Session:** cấu hình môi trường làm việc với giao thức email.
- **Store:** kết nối tới kho thư của tài khoản.
- **Folder:** hộp/thư mục trên server, ví dụ INBOX.
- **Message:** một thư đang được truy cập qua thư mục đó.

Ví dụ Java thuần dùng Jakarta Mail, minh họa việc đọc tối đa 10 tiêu đề thư cuối cùng bằng IMAPS:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.Session;
import jakarta.mail.Store;

import java.util.Properties;

public class InboxReader {

    public void printRecentSubjects(
            String host, String username, String credential
    ) throws MessagingException {
        Properties properties = new Properties();
        properties.put("mail.store.protocol", "imaps");
        properties.put("mail.imaps.connectiontimeout", "5000");
        properties.put("mail.imaps.timeout", "5000");

        Session session = Session.getInstance(properties);
        Store store = session.getStore("imaps");
        Folder inbox = null;

        try {
            store.connect(host, 993, username, credential);
            inbox = store.getFolder("INBOX");
            inbox.open(Folder.READ_ONLY);

            int count = inbox.getMessageCount();
            if (count > 0) {
                int first = Math.max(1, count - 9);
                Message[] messages = inbox.getMessages(first, count);

                for (Message message : messages) {
                    System.out.println(message.getSubject());
                }
            }
        } finally {
            if (inbox != null && inbox.isOpen()) {
                inbox.close(false);
            }
            if (store.isConnected()) {
                store.close();
            }
        }
    }
}
~~~

Ví dụ chủ ý đọc ở chế độ **READ_ONLY** và chỉ lấy tiêu đề. Nó cần nhà cung cấp có hỗ trợ IMAPS, cấu hình bảo mật phù hợp và một phương thức xác thực được server chấp nhận. Trong ứng dụng thực tế, không in tiêu đề/nội dung email nhạy cảm ra log; chuyển dữ liệu vào lớp xử lý có kiểm soát truy cập. Một số dịch vụ đòi hỏi OAuth 2.0 hoặc cơ chế xác thực khác thay cho mật khẩu tài khoản.

Trong ví dụ, **getMessages(first, count)** dùng số thứ tự của thư trong thư mục ở thời điểm đó. Số thứ tự này có thể thay đổi khi hộp thư thay đổi, nên **không dùng nó làm checkpoint đồng bộ dài hạn**.

Nếu đọc thân thư, **Message.getContent()** có thể trả về văn bản, đối tượng nhiều phần (multipart) hoặc cấu trúc lồng nhau. Một email HTML có thể đi kèm phiên bản plain text, ảnh nhúng và attachment. Cần xử lý đúng MIME, giới hạn kích thước, cách mã hóa ký tự và loại tệp; không giả định mọi email chỉ là một chuỗi văn bản.

### 3.3. Một lần đọc có nhất thiết đánh dấu thư đã đọc không?

Không thể trả lời “có” cho mọi tình huống. Trạng thái đã đọc thường được lưu thành cờ của hộp thư, nhưng tác động của việc truy xuất nội dung còn phụ thuộc giao thức, chế độ mở folder và hành vi client/provider.

Khi ứng dụng chỉ muốn phân tích thư mà không thay đổi hộp thư, nên dùng cơ chế đọc không ghi và xác định rõ chính sách đối với cờ **Seen**. Khi ứng dụng muốn đánh dấu đã đọc, hãy coi đó là **một thao tác quản lý trạng thái riêng**.

## 4. Đồng bộ thư: duy trì trạng thái theo thời gian

Giả sử hệ thống chăm sóc khách hàng đọc inbox lúc 09:00 và lưu 20 thư vào database. Đến 09:05, có hai thư mới, một thư bị chuyển thư mục và một thư được đánh dấu đã đọc. Nếu ứng dụng chỉ chạy lại lệnh “lấy 20 thư cuối” rồi chèn toàn bộ, dữ liệu sẽ trùng lặp và không phản ánh thay đổi trạng thái.

**Đồng bộ** là quá trình phát hiện và áp dụng sự thay đổi giữa hai hệ thống, thường giữa mailbox trên server và bản dữ liệu của ứng dụng. Nó đòi hỏi **trạng thái qua nhiều lần chạy**, chứ không chỉ một lệnh đọc.

### 4.1. Những dữ kiện phải theo dõi

Một bộ đồng bộ có thể cần lưu:

- Định danh tài khoản và thư mục nguồn.
- Định danh ổn định của từng thư trong phạm vi được nhà cung cấp bảo đảm.
- Checkpoint lần xử lý gần nhất hoặc token delta của API.
- Trạng thái thư: cờ đã đọc/chưa đọc, trả lời, gắn sao, đã xóa; thư mục hoặc nhãn.
- Thời điểm và kết quả xử lý để chạy lại an toàn sau lỗi.

Với **IMAP**, mỗi thư có thể được tham chiếu bằng **UID**, là định danh theo từng thư mục. Khi dùng UID để làm checkpoint cần đi cùng **UIDVALIDITY** của thư mục. Nếu UIDVALIDITY thay đổi, các UID đã lưu trước đó không còn được hiểu theo cùng một phạm vi; bộ đồng bộ phải xây dựng lại ánh xạ phù hợp. UID không phải mã định danh duy nhất toàn cục giữa mọi tài khoản và thư mục.

Đừng dùng **Message-ID** trong header email làm khóa duy nhất tuyệt đối: header đó có thể thiếu hoặc bị trùng. Đừng dùng chỉ số thứ tự thư (message sequence number) làm khóa lâu dài, vì thứ tự có thể đổi sau xóa hoặc cập nhật mailbox.

### 4.2. Polling, IMAP IDLE và webhook khác nhau ra sao?

| Cơ chế | Cách hoạt động | Điểm cần lưu ý |
| --- | --- | --- |
| **Polling** | Định kỳ hỏi server về thư và thay đổi mới | Dễ triển khai; có độ trễ và chi phí truy vấn; cần checkpoint |
| **IMAP IDLE** | Giữ kết nối để nhận tín hiệu server cho biết mailbox thay đổi | Vẫn phải truy vấn để xác định thay đổi; cần xử lý kết nối đứt và kết nối lại |
| **Webhook/push nhà cung cấp** | Nhà cung cấp gửi sự kiện hoặc thông báo có thay đổi | Cần xác thực thông báo, chống nhận trùng, bù sự kiện bị bỏ lỡ |
| **Delta/change tracking API** | Truy vấn các thay đổi từ một token/trạng thái trước đó | Token có thể hết hạn; phải có đường tái đồng bộ |

**Có thông báo mới không đồng nghĩa đã nhận đủ dữ liệu mới.** IDLE hoặc webhook thường là tín hiệu “hãy kiểm tra thay đổi”; hệ thống vẫn cần truy xuất dữ liệu và giải quyết tình huống bị mất kết nối, nhận lặp hoặc sự kiện đến không đúng thứ tự.

IMAP có những phần mở rộng như CONDSTORE/QRESYNC trên một số máy chủ để theo dõi thay đổi trạng thái hiệu quả hơn. Không được giả định mọi máy chủ đều hỗ trợ các phần mở rộng này; thiết kế phải kiểm tra capability thực tế và có cơ chế dự phòng.

### 4.3. Luồng đồng bộ tối thiểu

~~~text
Lần đầu:
  Kết nối và xác định mailbox
    -> đọc các thư cần nhập
    -> ghi dữ liệu + định danh nguồn
    -> lưu checkpoint sau khi xử lý thành công

Những lần sau:
  Nạp checkpoint
    -> hỏi thay đổi từ server
    -> thêm thư mới / cập nhật cờ / xử lý thư mất hoặc chuyển chỗ
    -> ghi kết quả theo cách có thể chạy lại
    -> cập nhật checkpoint khi dữ liệu đã được lưu an toàn

Khi mất checkpoint hoặc định danh nguồn hết hiệu lực:
  Tái quét hoặc tái đối chiếu theo quy tắc hệ thống
~~~

Ví dụ: với một thư mục IMAP, bộ đồng bộ có thể đọc UIDVALIDITY, lấy các UID sau UID đã xử lý, lấy nội dung cần thiết, rồi lưu bản ghi và checkpoint. Nhưng **chỉ quét UID lớn hơn lần trước chưa đủ để phát hiện cờ thay đổi hoặc thư bị xóa**; cần cơ chế đối chiếu/truy vấn thay đổi tương ứng. Nếu thư được chuyển thư mục, nó có thể xuất hiện với định danh mới trong thư mục đích.

Một bản ghi có thể dùng khóa logic dạng:

~~~text
(accountId, folderId, uidValidity, uid)
~~~

Đây là minh họa cho trường hợp IMAP, không phải khóa chung cho tất cả nhà cung cấp. Một provider API có thể cung cấp ID thư hoặc ID hội thoại theo phạm vi ổn định khác.

### 4.4. Đồng bộ an toàn cần xử lý điều gì?

**Chạy lặp và mất kết nối.** Nếu lưu thư thành công nhưng chưa kịp cập nhật checkpoint, lần chạy sau có thể gặp lại cùng thư. Hãy dùng upsert hoặc ràng buộc duy nhất theo khóa nguồn và đảm bảo cập nhật checkpoint nhất quán với dữ liệu đã xử lý.

**Nhiều tiến trình cùng chạy.** Hai worker có thể cùng nhập một thư hoặc cập nhật checkpoint sai thứ tự. Cần khóa, phân vùng theo tài khoản/thư mục hoặc cơ chế phối hợp thích hợp.

**Trạng thái hai chiều.** Nếu người dùng trong ứng dụng đánh dấu “đã đọc” rồi thao tác đó được gửi ngược lên server, hệ thống phải quyết định phía nào là nguồn sự thật, cách giải quyết xung đột và phản hồi khi server từ chối.

**Xóa và chuyển thư.** Không xuất hiện trong danh sách hiện tại chưa chắc nghĩa là thư đã bị xóa vĩnh viễn: có thể bị chuyển thư mục, ẩn bởi bộ lọc hoặc mất quyền truy cập. Chính sách lưu trữ và xóa dữ liệu cục bộ cần được định nghĩa rõ.

**Giới hạn tài nguyên.** Hộp thư lớn cần truy vấn theo lô, phân trang hợp lý, giới hạn kích thước attachment, retry có giới hạn và giám sát khả năng bị nhà cung cấp hạn chế tốc độ.

Vì các yếu tố trên, một tác vụ “đọc inbox mỗi phút” chỉ trở thành đồng bộ đúng nghĩa khi nó xử lý được **thay đổi, checkpoint và tình huống chạy lại**.

## 5. Quản lý hộp thư: thay đổi trạng thái trên máy chủ

Đọc và quản lý có thể cùng dùng kết nối IMAP, nhưng **quyền và hậu quả khác nhau**. Quản lý bao gồm các thao tác ghi lên mailbox.

Một số ví dụ:

| Thao tác | Ý nghĩa đối với mailbox | Lưu ý |
| --- | --- | --- |
| Đánh dấu đã đọc | Thiết lập cờ Seen hoặc trạng thái tương đương | Ảnh hưởng cách client khác hiển thị thư |
| Gắn cờ/đánh sao | Ghi trạng thái Flagged hoặc nhãn tương ứng | Provider có thể dùng nhãn riêng |
| Đánh dấu đã trả lời | Ghi trạng thái Answered nếu hệ thống dùng cờ này | Không tự chứng minh email trả lời thực sự đã được gửi |
| Chuyển hoặc sao chép thư | Đưa thư sang folder/nhãn khác hoặc sao chép | UID trong folder đích có thể khác |
| Xóa thư | Đánh dấu xóa, chuyển Trash hoặc xóa trực tiếp tùy API và hệ thống | Có thể cần bước expunge/xóa vĩnh viễn |
| Tạo/đổi tên thư mục | Thay đổi cách tổ chức mailbox | Không phải provider nào cũng mô hình hóa folder giống nhau |

Với Jakarta Mail, việc sửa trạng thái cần mở **Folder.READ_WRITE** và có quyền phù hợp. Ví dụ một API có thể thay đổi **Flags.Flag.SEEN**; các thao tác xóa thư cần xử lý rất cẩn thận vì có thể ảnh hưởng nhiều client và khả năng khôi phục thư.

IMAP truyền thống dùng folder và flags, trong khi một số dịch vụ lớn dùng mô hình **label**, có thể làm một thư xuất hiện trong nhiều “nhóm” mà không phải là các bản sao độc lập. Không nên ép mọi nhà cung cấp vào một mô hình folder giống hệt nhau khi thiết kế tính năng quản lý.

### Ranh giới giữa đồng bộ và quản lý

Hai nghiệp vụ thường đi cạnh nhau nhưng không đồng nhất:

- Khi **đồng bộ**, ứng dụng quan sát thư đã được người dùng đánh dấu đọc ở nơi khác và cập nhật database.
- Khi **quản lý**, ứng dụng chủ động đánh dấu thư đã đọc trên server theo thao tác của người dùng.
- Khi **đồng bộ hai chiều**, ứng dụng vừa quan sát thay đổi từ server vừa gửi thay đổi cục bộ lên server, nên cần quy tắc xử lý xung đột.

Ví dụ: nhân viên bấm “Đã xử lý” trong phần mềm chăm sóc khách hàng. Nếu chỉ thay đổi trường **status** của ticket trong database, đó là quản lý dữ liệu nghiệp vụ của ứng dụng. Nếu hệ thống còn gắn nhãn hoặc chuyển chính email sang folder “Processed” trên máy chủ, đó là **quản lý hộp thư**. Nếu ứng dụng sau đó phản ánh chính xác thay đổi này trên mọi màn hình và thiết bị, phần duy trì nhất quán là **đồng bộ**.

## 6. Spring Mail nằm ở đâu trong kiến trúc?

Một ứng dụng hoàn chỉnh có thể kết hợp nhiều thành phần:

~~~text
                         ỨNG DỤNG SPRING
                               |
         +---------------------+-----------------------+
         |                     |                       |
   Outbound Mail         Inbound Reader          Mailbox Sync /
   Service               Service                 Management Service
         |                     |                       |
  JavaMailSender         Jakarta Mail Store       IMAP / API provider
         |               hoặc API provider        + checkpoint trong DB
    SMTP / API send            |                       |
         v                     v                       v
    Hạ tầng gửi         Hộp thư trên server <----> Database ứng dụng
~~~

**Spring Framework Mail** xử lý phần gửi. Nếu cần nhận thư trong hệ sinh thái Spring, có thể xem xét **Spring Integration Mail**, với các thành phần nhận thư theo lịch hoặc IMAP IDLE, tùy phiên bản và khả năng của server. Spring Integration cung cấp các khối tích hợp, nhưng ứng dụng vẫn phải quyết định lưu dữ liệu, checkpoint, xử lý trùng, quyền truy cập và nghiệp vụ quản lý.

Ngoài ra, có thể sử dụng trực tiếp **Jakarta Mail** để truy cập IMAP/POP3 hoặc dùng client SDK/API của nhà cung cấp. Lựa chọn phụ thuộc đặc thù nhu cầu:

- Chỉ gửi mã xác minh hoặc thông báo: thường chỉ cần **JavaMailSender** hoặc dịch vụ gửi thư HTTP.
- Thỉnh thoảng lấy nội dung email từ một tài khoản: cần **bộ đọc IMAP/POP3/API**.
- Nhận nhiều email và xử lý liên tục: cần **bộ nhận + cơ chế đồng bộ + lưu trạng thái**.
- Phát triển giao diện inbox để người dùng đánh dấu, phân loại, chuyển hoặc xóa: cần **API quản lý mailbox** cùng phân quyền và đồng bộ trạng thái.

Không nên tạo một dịch vụ duy nhất có tên chung chung như “EmailService” rồi mặc định rằng mọi thao tác đều có thể gọi qua **JavaMailSender**. Tên và ranh giới lớp nên thể hiện vai trò của từng hướng trao đổi.

## 7. Ba tình huống thường gây nhầm lẫn

### Tình huống A: “Tôi đã gửi email xác nhận, giờ cần biết khách hàng đã đọc chưa”

Đây là hai yêu cầu khác nhau. **Gửi** qua JavaMailSender chỉ giúp ứng dụng yêu cầu chuyển thư. Nếu muốn xác minh đã đọc, cần giải pháp theo dõi/biên nhận với sự đồng ý và giới hạn riêng; nhiều client không cung cấp tín hiệu đáng tin cậy. **Đọc inbox của chính ứng dụng** cũng không trả lời được việc khách hàng có mở thư trong hộp thư của họ hay không.

Giải pháp đáng tin cậy hơn cho xác nhận nghiệp vụ là cung cấp một hành động rõ ràng như nút **Xác nhận email** hoặc liên kết có token. Khi người dùng bấm và máy chủ xác nhận token, ứng dụng biết họ đã hoàn thành bước xác minh; điều này vẫn khác với đo “đã đọc email”.

### Tình huống B: “Hệ thống cần đọc email phản hồi của khách hàng”

Đây là nghiệp vụ **nhận/đọc thư từ mailbox của doanh nghiệp**, ví dụ support@example.org. JavaMailSender không có thao tác liệt kê các thư đến. Hệ thống cần quyền truy cập inbox thông qua IMAP hoặc API nhà cung cấp, giải mã nội dung cần dùng và liên kết thư với yêu cầu hỗ trợ thích hợp.

Nếu chỉ lấy mẫu thư thủ công, một lần truy xuất có thể đủ. Nếu cần hoạt động liên tục, phải bổ sung cơ chế đồng bộ để không xử lý trùng hoặc bỏ sót thư.

### Tình huống C: “Tự động chuyển email đã xử lý sang thư mục Archive”

Hệ thống vừa **đọc** để nhận diện thư, vừa **quản lý hộp thư** để chuyển trạng thái, và thường cần **đồng bộ** để ghi nhớ rằng thư đã được xử lý. Nếu thư được chuyển sang thư mục khác, bộ đồng bộ phải hiểu ngữ nghĩa định danh mới trong thư mục đích và tránh coi đó là một yêu cầu hỗ trợ hoàn toàn mới.

Đây không phải phần mở rộng tự nhiên của lệnh gửi SMTP; nó yêu cầu kết nối mailbox có quyền ghi hoặc API provider tương ứng.

## 8. Các ràng buộc nên xác định trước khi chọn giải pháp

Khi đặc tả một chức năng email, hãy trả lời rõ những câu hỏi sau:

1. **Ứng dụng là bên gửi hay bên truy cập một hộp thư?** Tài khoản và quyền gửi có thể khác tài khoản và quyền đọc.
2. **Cần kết quả tại một thời điểm hay theo dõi liên tục?** “Lấy 10 thư mới nhất” khác hẳn “không bỏ sót thư nào trong nhiều tháng”.
3. **Chỉ quan sát hay được thay đổi thư trên server?** Quyền đọc và quyền ghi phải được phân tách theo nhu cầu.
4. **Nhà cung cấp hỗ trợ giao thức nào?** Không phải hộp thư nào cũng cho phép IMAP/POP3; provider API có thể yêu cầu scope, OAuth và hạn mức riêng.
5. **Dữ liệu nào là nguồn sự thật?** Nếu có database cục bộ, phải quy định cách xử lý thư mới, cờ thay đổi, thư bị xóa, lỗi và đồng bộ hai chiều.
6. **Bảo mật và vận hành được xử lý ra sao?** Cần bảo vệ credential/token, dùng TLS, kiểm soát quyền truy cập dữ liệu email, giới hạn attachment, tránh log nội dung riêng tư, quản lý retry/rate limit và giám sát lỗi.

Một số sai lầm dễ gặp:

- Dùng SMTP để “đọc thư gửi đến” hoặc dùng JavaMailSender để tìm các thư trong inbox.
- Coi **không phát sinh ngoại lệ khi send()** là bằng chứng người nhận đã nhận hoặc mở thư.
- Dùng chỉ số thứ tự của IMAP làm ID lâu dài; bỏ qua UIDVALIDITY hoặc sự thay đổi cờ/xóa.
- Đọc lại toàn bộ inbox rồi chèn mới mọi thư trong mỗi chu kỳ chạy.
- Tự động sửa/xóa thư khi bài toán ban đầu chỉ yêu cầu đọc, chưa có quyền và chính sách rõ ràng.
- Đồng nhất folder IMAP với label hoặc định danh thư của mọi nhà cung cấp.

## 9. Chọn đúng giải pháp theo yêu cầu

| Nếu yêu cầu là… | Nghiệp vụ chính | Hướng triển khai |
| --- | --- | --- |
| “Gửi OTP khi đăng nhập” | Gửi | Spring Mail / JavaMailSender hoặc API gửi |
| “Gửi hóa đơn có PDF đính kèm” | Gửi | JavaMailSender với MIME và attachment |
| “Hiển thị 10 thư mới nhất từ inbox chung” | Đọc | IMAP hoặc API đọc thư |
| “Tạo ticket mỗi khi có email mới, không trùng khi chạy lại” | Đọc + đồng bộ | Bộ nhận có checkpoint, định danh nguồn và lưu trữ bền vững |
| “Hiển thị thay đổi đã đọc/chưa đọc trên nhiều thiết bị” | Đồng bộ | Theo dõi cờ/nhãn, cập nhật dữ liệu theo thay đổi của server |
| “Đánh dấu đã xử lý và chuyển thư vào Archive” | Quản lý + đồng bộ | API mailbox có quyền ghi, sau đó đối chiếu trạng thái |
| “Biết người nhận có xác minh địa chỉ email hay chưa” | Xác nhận nghiệp vụ | Liên kết/token xác nhận trên ứng dụng; gửi thư chỉ là bước phân phối |

## 10. Ghi nhớ khi học Spring Framework Mail

**Gửi** là yêu cầu máy chủ chuyển một thông điệp ra ngoài; **đọc** là truy xuất thư đã lưu; **đồng bộ** là duy trì tính nhất quán khi hộp thư thay đổi qua thời gian; **quản lý** là chủ động thay đổi trạng thái hoặc cấu trúc hộp thư. Cùng dùng khái niệm “email”, nhưng chúng khác nhau về giao thức, quyền truy cập, dữ liệu trạng thái và điều kiện thành công.

Khi làm việc với **Spring Framework Mail**, hãy đặt **MailSender/JavaMailSender** đúng vai trò gửi thư. Nếu bài toán phát triển sang đọc inbox, xử lý thư liên tục, gắn cờ, chuyển thư hoặc xóa thư, hãy thiết kế thêm các thành phần truy cập mailbox và đồng bộ tương ứng. Việc chọn đúng ranh giới từ đầu sẽ làm rõ điều ứng dụng thật sự bảo đảm, đặc biệt trong những tình huống có lỗi mạng, thư trùng hoặc trạng thái khác nhau giữa nhiều client.
