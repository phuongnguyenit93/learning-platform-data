# Gửi một message đến nhiều người nhận

Một hệ thống Spring cần thông báo lịch bảo trì cho ba kỹ sư và sao chép thông tin cho trưởng nhóm. Nội dung gửi đi giống nhau, nên ứng dụng không nhất thiết phải tạo bốn email riêng biệt. Nó có thể dựng **một thông điệp email (message)**, thêm nhiều địa chỉ vào danh sách người nhận, rồi gọi `JavaMailSender.send(...)` một lần. Hạ tầng SMTP sẽ xử lý việc chuyển thư đến từng địa chỉ.

Trong **Spring Framework Mail**, gửi một message đến nhiều người nhận là thao tác thường gặp khi gửi thông báo nhóm, bản tin nội bộ, báo cáo chung hoặc lời mời chung. Tuy nhiên, “một message” không đồng nghĩa với “mọi người nhận đều nhìn thấy cùng một danh sách địa chỉ”, “mọi hộp thư đều nhận thành công” hay “chỉ có một bản sao được chuyển trên mạng”. Để triển khai đúng, cần hiểu cách tổ chức các trường **To, Cc, Bcc**, sự khác nhau giữa **header** và **SMTP envelope**, cũng như cách kiểm soát quyền riêng tư và lỗi gửi một phần.

## 1. Một message và nhiều địa chỉ nhận là gì?

Trong hệ sinh thái Java, `MimeMessage` biểu diễn một email với các thông tin như người gửi, người nhận, tiêu đề, nội dung và tệp đính kèm. Một `MimeMessage` có thể chứa nhiều địa chỉ nhận.

Ví dụ một thư thông báo chung:

~~~text
From: system@example.org
To: an@example.net, binh@example.net
Cc: lead@example.net
Subject: Lịch bảo trì hệ thống

Hệ thống sẽ được bảo trì vào tối thứ Bảy.
~~~

Người nhận ở trường **To** là những người được gửi trực tiếp. Người ở **Cc** nhận bản sao và thường cũng nhìn thấy các địa chỉ To/Cc trong header. Nếu ứng dụng thêm `audit@example.net` vào **Bcc**, địa chỉ đó cũng có thể được chuyển phát thư, nhưng không được công bố cho người nhận khác trong trường Bcc của thư nhận được theo luồng gửi chuẩn.

~~~mermaid
flowchart LR
    A["Ứng dụng Spring"] --> B["Một MimeMessage"]
    B --> C["JavaMailSender"]
    C --> D["SMTP relay"]
    D --> E["an@example.net"]
    D --> F["binh@example.net"]
    D --> G["lead@example.net"]
    D --> H["audit@example.net — Bcc"]
~~~

Đây là mô hình khái niệm: SMTP relay có thể thực hiện nhiều lần kết nối, xếp hàng hoặc nhân bản thư để chuyển đến các hộp thư. Ở phía ứng dụng, chỉ cần **một đối tượng message và một lần gọi phương thức gửi** cho yêu cầu này.

### Một message khác nhiều message như thế nào?

| Cách làm | Đối tượng được tạo | Trường hợp phù hợp |
| --- | --- | --- |
| Một `MimeMessage`, có nhiều To/Cc/Bcc | **Một** thông điệp mang nội dung dùng chung cho nhiều địa chỉ | Thông báo chung, cùng tiêu đề và nội dung |
| Nhiều `MimeMessage`, mỗi message có một người nhận | **Nhiều** thông điệp độc lập | Email cá nhân hóa, token riêng, trạng thái riêng từng người |
| Gọi `JavaMailSender.send(MimeMessage...)` với nhiều đối tượng | Gửi **nhiều message** qua cùng API | Gửi một nhóm các thông điệp độc lập |

Điểm cuối dễ bị hiểu nhầm: phương thức `send(MimeMessage... mimeMessages)` nhận **mảng các message**, không có nghĩa mỗi phần tử mảng là một địa chỉ nhận. Để một message đến nhiều người nhận, hãy thiết lập danh sách người nhận **bên trong message**.

## 2. To, Cc và Bcc biểu thị điều gì?

Các địa chỉ nhận không chỉ là danh sách để SMTP chuyển phát. Ba loại To/Cc/Bcc còn mang **ý nghĩa giao tiếp** và quyết định **ai nhìn thấy thông tin người nhận nào**.

| Trường | Ý nghĩa thông dụng | Địa chỉ hiển thị với người nhận khác? | API liên quan |
| --- | --- | --- | --- |
| **To** | Người nhận chính của thông báo | Thường **có**, ở header To | `setTo(...)`, `addTo(...)` |
| **Cc** (*carbon copy*) | Người nhận bản sao để theo dõi hoặc phối hợp | Thường **có**, ở header Cc | `setCc(...)`, `addCc(...)` |
| **Bcc** (*blind carbon copy*) | Người nhận bản sao ẩn khỏi danh sách hiển thị công khai | Thường **không** trong bản thư được phát tới người nhận khác qua cách gửi chuẩn | `setBcc(...)`, `addBcc(...)` |

Ví dụ một yêu cầu gửi có:

~~~text
To:  an@example.net, binh@example.net
Cc:  lead@example.net
Bcc: audit@example.net
~~~

Về mặt nghiệp vụ, cả bốn địa chỉ có thể là **đích chuyển thư**. Nhưng về mặt hiển thị, bản thư tới An/Bình/trưởng nhóm thông thường sẽ chỉ công bố **To** và **Cc**. Người nhận Bcc vẫn có thể đọc nội dung thông điệp; họ không bị hạn chế nội dung email.

**Bcc không phải cơ chế mã hóa và cũng không bảo đảm ẩn danh tuyệt đối.** Ứng dụng gửi, nhà cung cấp email, hệ thống quản trị hoặc log ở phía gửi vẫn có thể biết địa chỉ Bcc. Nếu mã ứng dụng tự xuất raw MIME, tự chuyển thư hoặc log các header Bcc, thông tin có thể bị lộ. Muốn giữ bí mật danh sách người nhận, cần quản lý toàn bộ quá trình tạo, gửi, theo dõi và ghi log.

### Nên dùng loại nào?

- Gửi một nhiệm vụ cần An và Bình xử lý, trưởng nhóm theo dõi: dùng **To** cho An/Bình và **Cc** cho trưởng nhóm.
- Gửi một thông báo chung cho một danh sách mà các thành viên **không nên biết địa chỉ của nhau**: cân nhắc **Bcc** hoặc, tốt hơn cho các trường hợp có yêu cầu cá nhân hóa/quyền riêng tư, **mỗi người một message**.
- Gửi mã OTP, liên kết đặt lại mật khẩu, báo cáo cá nhân hoặc dữ liệu riêng: **mỗi người nhận một message riêng**, không đưa toàn bộ danh sách vào To/Cc.
- Gửi bản sao về hộp thư phục vụ kiểm toán: chỉ dùng Bcc nếu chính sách bảo mật và quy trình lưu giữ cho phép; nhiều hệ thống chọn lưu bản ghi sự kiện thay cho tự động gửi thêm bản sao.

**Một người thuộc Bcc vẫn có thể tự tiết lộ việc họ nhận được thư** bằng cách chuyển tiếp hoặc trả lời. Bcc chỉ kiểm soát việc trường địa chỉ này được công bố trong bản message chuyển phát bình thường, không kiểm soát hành vi người dùng sau đó.

## 3. SMTP thực sự chuyển thư đến nhiều người bằng cách nào?

Email có hai lớp thông tin liên quan đến người nhận:

1. **Header của message**: các trường `To`, `Cc`, đôi khi `Bcc` khi đối tượng đang được dựng trong ứng dụng; chúng mô tả người nhận của thông điệp.
2. **SMTP envelope**: địa chỉ được SMTP relay dùng trong các lệnh `RCPT TO` để xác định những đích cần chuyển phát.

Một phiên SMTP minh họa có thể trông như sau:

~~~text
C: EHLO application.example.org
S: 250 smtp-relay.example.org
C: MAIL FROM:<system@example.org>
S: 250 Sender accepted
C: RCPT TO:<an@example.net>
S: 250 Recipient accepted
C: RCPT TO:<binh@example.net>
S: 250 Recipient accepted
C: RCPT TO:<lead@example.net>
S: 250 Recipient accepted
C: RCPT TO:<audit@example.net>
S: 250 Recipient accepted
C: DATA
S: 354 Send message content
C: From: system@example.org
C: To: an@example.net, binh@example.net
C: Cc: lead@example.net
C: Subject: Lịch bảo trì
C:
C: Hệ thống sẽ được bảo trì vào tối thứ Bảy.
C: .
S: 250 Message accepted for delivery
~~~

Đây chỉ là ví dụ về thứ tự lệnh; trong thực tế một phiên có thể sử dụng STARTTLS và AUTH trước `MAIL FROM`, các phản hồi khác nhau giữa các nhà cung cấp, và địa chỉ người gửi envelope có thể khác `From` trong header.

Trong ví dụ có **bốn lệnh `RCPT TO`**, tương ứng bốn đích gửi, kể cả địa chỉ Bcc. Nhưng khối `DATA` được truyền trong phiên minh họa **một lần**. Địa chỉ Bcc không xuất hiện trong header `To` hoặc `Cc` được gửi đến người nhận khác.

Điều này giải thích ba điều quan trọng:

- **Một message có thể có nhiều đích SMTP.** Đích SMTP không chỉ được suy ra bằng cách đọc dòng `To` khi message đã được chuyển phát.
- **Bcc có thể nhận thư dù không hiển thị trong header thư được gửi đi.** Hệ thống gửi dùng thông tin người nhận envelope để chuyển thư.
- **Một lần gọi gửi không đồng nghĩa với chuyển phát thành công đến mọi người.** SMTP server có thể chấp nhận hoặc từ chối từng địa chỉ ở thời điểm xử lý, hoặc một email đã được chấp nhận vẫn có thể bị trả lại về sau.

Với Jakarta Mail, transport SMTP thông thường lấy tập địa chỉ nhận từ message để xử lý chuyển phát. Khi muốn kiểm soát envelope ở mức thấp hơn hoặc tích hợp một relay đặc biệt, cần hiểu thêm API `Transport.sendMessage(...)` và chính sách transport; đó là phạm vi rộng hơn trường hợp ứng dụng Spring chỉ gọi `JavaMailSender.send(...)`.

## 4. Gửi nhiều người nhận bằng SimpleMailMessage

Nếu chỉ cần gửi nội dung **văn bản thuần** mà không có tệp đính kèm, `SimpleMailMessage` là lựa chọn gọn.

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class MaintenanceNoticeService {

    private final JavaMailSender mailSender;

    public MaintenanceNoticeService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendCommonNotice() {
        SimpleMailMessage message = new SimpleMailMessage();

        message.setFrom("system@example.org");
        message.setTo(
                "an@example.net",
                "binh@example.net"
        );
        message.setCc("lead@example.net");
        message.setBcc("audit@example.net");
        message.setSubject("Thông báo lịch bảo trì");
        message.setText(
                "Hệ thống sẽ được bảo trì vào tối thứ Bảy."
        );

        mailSender.send(message);
    }
}
~~~

Các phương thức `setTo(String...)`, `setCc(String...)` và `setBcc(String...)` của `SimpleMailMessage` nhận nhiều địa chỉ thông qua tham số dạng biến đối hoặc mảng chuỗi. Spring Mail gửi đối tượng này bằng thành phần `MailSender`/`JavaMailSender` đã được cấu hình.

Ví dụ sử dụng địa chỉ giả định nhằm diễn đạt cách gọi API. Trong ứng dụng thật, `From` phải là địa chỉ được SMTP provider cho phép, còn danh sách nhận phải được kiểm tra theo yêu cầu nghiệp vụ.

### Khi nào nên chuyển sang MimeMessage?

`SimpleMailMessage` chỉ thể hiện những trường thư đơn giản. Nếu cần HTML, hai phiên bản plain text/HTML, ảnh nội tuyến, Unicode với charset xác định rõ ràng hoặc tệp đính kèm, nên dùng `MimeMessage` và `MimeMessageHelper`.

Điều quan trọng là **cách khai báo nhiều người nhận tương tự nhau**, dù nội dung email được dựng bằng API đơn giản hay MIME phức tạp.

## 5. Gửi một MimeMessage đến nhiều người nhận bằng MimeMessageHelper

`MimeMessageHelper` cung cấp các phương thức nhận địa chỉ chuỗi hoặc `InternetAddress`, thuận tiện khi dựng thông điệp MIME. Với thư dùng tiếng Việt có dấu, có thể chọn `UTF-8` rõ ràng.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class TeamAnnouncementService {

    private final JavaMailSender mailSender;

    public TeamAnnouncementService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendAnnouncement() throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("system@example.org");
        helper.setTo(new String[] {
                "an@example.net",
                "binh@example.net"
        });
        helper.setCc(new String[] {
                "lead@example.net"
        });
        helper.setBcc(new String[] {
                "audit@example.net"
        });

        helper.setSubject("Lịch bảo trì hệ thống tuần này");
        helper.setText(
                "Hệ thống sẽ được bảo trì vào tối thứ Bảy.",
                false
        );

        mailSender.send(message);
    }
}
~~~

`helper.setTo(String[])`, `setCc(String[])` và `setBcc(String[])` thiết lập **toàn bộ nhóm địa chỉ tương ứng**. Các biến thể `addTo(...)`, `addCc(...)`, `addBcc(...)` thêm từng địa chỉ, phù hợp khi danh sách nhận được xây dựng dần.

Ví dụ:

~~~java
helper.setTo("an@example.net");
helper.addTo("binh@example.net");
helper.addCc("lead@example.net");
helper.addBcc("audit@example.net");
~~~

Nếu danh sách đã có sẵn, thường dễ đọc và quản lý hơn khi chuyển thành mảng đúng loại rồi gọi một lần cho từng trường. Nếu muốn thêm người nhận vào danh sách đã thiết lập, dùng `addTo` thay vì gọi `setTo` lần thứ hai để tránh vô tình thay thế nội dung trước đó.

### setTo và addTo khác nhau thế nào?

| Cách gọi | Ý nghĩa |
| --- | --- |
| `helper.setTo("an@example.net")` | Đặt danh sách To của message thành một địa chỉ. |
| `helper.setTo(new String[]{"an@example.net", "binh@example.net"})` | Đặt danh sách To thành hai địa chỉ. |
| `helper.addTo("binh@example.net")` | Thêm một địa chỉ vào To hiện có. |
| `helper.setCc(new String[]{"lead@example.net"})` | Đặt danh sách người nhận Cc. |
| `helper.addBcc("audit@example.net")` | Thêm người nhận Bcc. |

Không nên đưa nguyên một chuỗi dạng `"an@example.net,binh@example.net"` vào phương thức chỉ nhận **một địa chỉ** và trông chờ thư viện luôn phân tách như mong muốn. Khi đầu vào là nhiều địa chỉ, hãy dùng **mảng, danh sách có kiểm tra hoặc API phân tích địa chỉ** phù hợp.

## 6. Cấu hình Spring Boot để gửi qua SMTP relay

Nếu sử dụng Spring Boot với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Cấu hình ví dụ trong `application.properties`:

~~~properties
spring.mail.host=smtp.provider.example
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000

app.mail.from=${APP_MAIL_FROM}
~~~

`smtp.provider.example` là hostname giả định. Để gửi thật, cần sử dụng host, cổng, cơ chế xác thực và thông tin TLS đúng với dịch vụ email. Tài khoản và mật khẩu nên được cấp qua biến môi trường hoặc hệ thống quản lý bí mật thay vì lưu trong mã nguồn.

Cấu hình SMTP **không phải nơi khai báo To/Cc/Bcc** cho từng email. Danh sách nhận được đặt trong `SimpleMailMessage` hoặc `MimeMessage` khi xây dựng thông điệp.

Gửi đến nhiều người nhận qua một relay cũng không đồng nghĩa ứng dụng phải tự truy vấn bản ghi DNS MX của từng miền. Nhà cung cấp SMTP thường chịu trách nhiệm phân giải miền nhận và định tuyến email tiếp theo.

## 7. Lấy danh sách người nhận từ dữ liệu nghiệp vụ

Trong thực tế, danh sách người nhận có thể đến từ cơ sở dữ liệu, danh sách thành viên nhóm hoặc kết quả xử lý một sự kiện. Ứng dụng cần kiểm tra dữ liệu trước khi tạo message:

1. Xác định các địa chỉ được phép nhận thông báo.
2. Chọn từng địa chỉ thuộc To, Cc hay Bcc theo mục đích.
3. Loại dữ liệu rỗng hoặc sai định dạng.
4. Xử lý địa chỉ trùng theo chính sách rõ ràng.
5. Kiểm tra giới hạn số người nhận và loại nội dung.
6. Sau đó dựng `MimeMessage` và gọi `send(...)`.

### Ví dụ dịch vụ nhận danh sách động

Giả sử nghiệp vụ có ba danh sách được cấp từ nguồn đã kiểm soát. Dịch vụ sau yêu cầu ít nhất một địa chỉ, xác thực cú pháp và giữ nguyên nhóm người nhận.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class GroupMailService {

    private final JavaMailSender mailSender;
    private final String from;

    public GroupMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String from) {

        this.mailSender = mailSender;
        this.from = from;
    }

    public void sendToGroup(
            List<String> to,
            List<String> cc,
            List<String> bcc,
            String subject,
            String body) throws MessagingException {

        String[] toAddresses = parseMailboxes(to);
        String[] ccAddresses = parseMailboxes(cc);
        String[] bccAddresses = parseMailboxes(bcc);

        if (toAddresses.length + ccAddresses.length
                + bccAddresses.length == 0) {
            throw new IllegalArgumentException(
                    "Cần ít nhất một người nhận"
            );
        }

        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException(
                    "Subject không được để trống"
            );
        }

        if (body == null || body.isBlank()) {
            throw new IllegalArgumentException(
                    "Nội dung không được để trống"
            );
        }

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom(from);

        if (toAddresses.length > 0) {
            helper.setTo(toAddresses);
        }
        if (ccAddresses.length > 0) {
            helper.setCc(ccAddresses);
        }
        if (bccAddresses.length > 0) {
            helper.setBcc(bccAddresses);
        }

        helper.setSubject(subject);
        helper.setText(body, false);

        mailSender.send(message);
    }

    private static String[] parseMailboxes(List<String> input)
            throws AddressException {

        if (input == null || input.isEmpty()) {
            return new String[0];
        }

        String[] addresses = new String[input.size()];

        for (int i = 0; i < input.size(); i++) {
            String raw = input.get(i);

            if (raw == null || raw.isBlank()) {
                throw new IllegalArgumentException(
                        "Danh sách chứa địa chỉ trống"
                );
            }

            if (raw.indexOf('\r') >= 0
                    || raw.indexOf('\n') >= 0) {
                throw new IllegalArgumentException(
                        "Địa chỉ chứa ký tự xuống dòng"
                );
            }

            // Mỗi phần tử phải là một mailbox.
            InternetAddress[] parsed =
                    InternetAddress.parse(raw.trim(), true);

            if (parsed.length != 1 || parsed[0].isGroup()) {
                throw new IllegalArgumentException(
                        "Mỗi phần tử phải là một địa chỉ"
                );
            }

            parsed[0].validate();
            addresses[i] = parsed[0].getAddress();
        }

        return addresses;
    }
}
~~~

Ví dụ chỉ mô tả **kiểm tra địa chỉ đầu vào**, chưa giải quyết trùng địa chỉ giữa To/Cc/Bcc, quyền nhận thông báo, kiểm soát tổng số người nhận hoặc chính sách gửi riêng từng người. Chúng cần được bổ sung ở tầng nghiệp vụ theo yêu cầu thực tế.

`InternetAddress.parse(..., true)` và `validate()` chủ yếu kiểm tra cú pháp địa chỉ. Chúng **không xác nhận hộp thư đang tồn tại**, không kiểm tra người nhận đồng ý nhận thông báo và không bảo đảm mail server đích chấp nhận thư.

### Có nên loại địa chỉ trùng?

Ví dụ An có trong cả To và Cc. Việc để trùng có thể gây ra thông điệp khó hiểu hoặc ảnh hưởng cách SMTP provider xử lý người nhận. Vì thế, ứng dụng nên có chính sách rõ ràng, thường là **không cho một địa chỉ xuất hiện đồng thời ở nhiều nhóm**.

Tuy vậy, không nên tự động gọi `toLowerCase()` cho **toàn bộ địa chỉ** rồi coi đó là quy tắc chuẩn tuyệt đối: **miền** của email không phân biệt chữ hoa/thường, nhưng tính tương đương của phần trước dấu `@` có thể phụ thuộc hệ thống nhận. Ngoài ra, các địa chỉ có dấu cộng (`+`), alias hay địa chỉ có nhiều kiểu biểu diễn không phải lúc nào cũng cùng một mailbox.

Nên chuẩn hóa theo chính sách tổ chức và nhà cung cấp, giữ được địa chỉ gốc để giải thích quyết định loại trùng, đồng thời tránh vô tình đổi đích nhận.

## 8. Kiểm tra người nhận đã gắn vào MimeMessage

Sau khi dùng helper đặt địa chỉ, có thể đọc lại các trường qua API Jakarta Mail:

~~~java
import jakarta.mail.Address;
import jakarta.mail.Message;
import jakarta.mail.internet.MimeMessage;

Address[] to = message.getRecipients(
        Message.RecipientType.TO
);
Address[] cc = message.getRecipients(
        Message.RecipientType.CC
);
Address[] bcc = message.getRecipients(
        Message.RecipientType.BCC
);
Address[] all = message.getAllRecipients();
~~~

Một getter có thể trả về `null` khi trường tương ứng chưa tồn tại. `getAllRecipients()` cung cấp danh sách các địa chỉ nhận theo nội dung message, phù hợp để **xác nhận có ít nhất một địa chỉ** trước gửi:

~~~java
Address[] recipients = message.getAllRecipients();

if (recipients == null || recipients.length == 0) {
    throw new IllegalStateException(
            "Message chưa có người nhận"
    );
}
~~~

Phép kiểm tra này chỉ xác nhận **các địa chỉ đã được gán vào đối tượng**. Nó không xác nhận các hộp thư tồn tại, không bảo đảm nhà cung cấp có thể gửi tới tất cả và không chứng minh quyền nhận thông báo.

Khi message chứa Bcc, `getRecipients(BCC)` trong đối tượng đang dựng có thể trả về danh sách Bcc. **Đừng đưa kết quả này vào log hoặc API trả về cho người dùng** nếu danh sách có thông tin riêng tư. Việc message giữ địa chỉ để phục vụ gửi không có nghĩa danh sách đó phù hợp để hiển thị công khai.

### Địa chỉ người nhận trong MIME khác địa chỉ SMTP envelope

Ở tầng thấp của Jakarta Mail, có thể gọi:

~~~java
Transport.send(message);
~~~

Khi sử dụng đường gửi phổ biến, transport lấy các địa chỉ từ message để nộp SMTP. Với những trường hợp đặc biệt, API:

~~~java
transport.sendMessage(message, recipients);
~~~

cho phép người gọi truyền tập đích `recipients` cụ thể của thao tác gửi. Tập này có thể khác những gì hiển thị trong các trường To/Cc của header; muốn sử dụng trực tiếp phải chịu trách nhiệm xác định đúng địa chỉ và xử lý kết quả transport. Trong ứng dụng Spring thông thường, `JavaMailSender.send(message)` đơn giản và nhất quán hơn.

## 9. Gửi cùng một nội dung HTML hoặc tệp đính kèm cho nhiều người

Nguyên tắc danh sách người nhận không thay đổi khi message trở thành multipart. Ví dụ gửi cùng một tệp PDF:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("report@example.org");
helper.setTo(new String[] {
        "an@example.net",
        "binh@example.net"
});
helper.setSubject("Báo cáo tuần");

helper.setText(
        "<p>Báo cáo tuần đã được đính kèm.</p>",
        true
);

helper.addAttachment(
        "weekly-report.pdf",
        new ClassPathResource("mail/weekly-report.pdf"),
        "application/pdf"
);

mailSender.send(message);
~~~

Ứng dụng cần có tệp `src/main/resources/mail/weekly-report.pdf` trên classpath, người gửi được nhà cung cấp chấp nhận, và SMTP relay được cấu hình phù hợp. `MimeMessageHelper` tổ chức các phần MIME và để Jakarta Mail xử lý mã hóa/boundary.

**Tất cả người nhận của message sẽ nhận được cùng nội dung và cùng tệp**, trừ khi một thành phần chuyển tiếp hoặc chính sách phía nhà cung cấp thay đổi cách phát thư. Không nên dùng một message chung nếu PDF chỉ được phép xem bởi một người nhận nhất định.

### HTML có tên riêng từng người thì sao?

Giả sử bạn muốn:

~~~text
Chào An, hóa đơn của bạn là INV-101.
Chào Bình, hóa đơn của bạn là INV-102.
~~~

Một `MimeMessage` chỉ có **một bộ Subject/body/attachment**. Nếu đưa cả An và Bình vào cùng To, họ sẽ nhận cùng một phần thân email, nên không thể cá nhân hóa riêng nội dung cho từng người bằng cách thay một biến trong một message chung.

Cách đúng là tạo **một message cho mỗi người nhận**, với nội dung được dựng theo thông tin của chính người đó:

~~~java
for (InvoiceNotice notice : notices) {
    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(message, false, "UTF-8");

    helper.setFrom("billing@example.org");
    helper.setTo(notice.email());
    helper.setSubject("Hóa đơn " + notice.invoiceCode());
    helper.setText(
            "Hóa đơn " + notice.invoiceCode()
                    + " của bạn đã sẵn sàng.",
            false
    );

    mailSender.send(message);
}
~~~

Đây là ví dụ ý tưởng, giả định `InvoiceNotice` là kiểu dữ liệu ứng dụng định nghĩa với phương thức `email()` và `invoiceCode()`. Trong hệ thống thật, cần kiểm soát nội dung riêng tư, kết quả gửi và quy trình thử lại cho từng thông báo.

Việc gửi nhiều message có thể được tối ưu bằng hàng đợi, batch hoặc API hỗ trợ gửi nhiều thư, nhưng **không nên đánh đổi cách ly dữ liệu cá nhân** lấy việc giảm số lần gọi hàm.

## 10. Một lần send() có bảo đảm tất cả người nhận thành công không?

**Không.** Đây là một trong những khác biệt quan trọng nhất giữa thao tác API và kết quả nghiệp vụ.

Trong SMTP, máy chủ có thể phản hồi khác nhau cho từng lệnh `RCPT TO`. Ví dụ:

~~~text
C: RCPT TO:<an@example.net>
S: 250 2.1.5 Recipient OK

C: RCPT TO:<binh@example.net>
S: 550 5.1.1 User unknown

C: RCPT TO:<lead@example.net>
S: 250 2.1.5 Recipient OK
~~~

Ở đây, một địa chỉ bị từ chối còn hai địa chỉ được chấp nhận tại bước kiểm tra người nhận. **Hành vi tiếp theo phụ thuộc SMTP client, cấu hình transport và phản hồi server**. Một cấu hình có thể hủy gửi thông điệp khi phát hiện đích lỗi; một cấu hình cho phép chuyển đến người nhận hợp lệ trong khi trả thông tin lỗi cho địa chỉ không hợp lệ.

### Partial delivery trong Jakarta Mail

Jakarta Mail SMTP có tùy chọn transport như `mail.smtp.sendpartial` để điều khiển trường hợp **một số địa chỉ hợp lệ, một số bị từ chối**.

- Với chính sách không cho phép gửi một phần, transport có thể dừng nộp message khi phát hiện địa chỉ không hợp lệ.
- Khi cấu hình cho phép gửi một phần, transport có thể gửi đến các địa chỉ hợp lệ và đồng thời thông báo lỗi đối với địa chỉ không hợp lệ.
- Một server có thể chấp nhận nhiều địa chỉ lúc nộp thư nhưng sau đó vẫn trả lại email vì lỗi tại điểm nhận cuối. Kết quả này không thể xác định chỉ bằng phản hồi ban đầu.

Các ngoại lệ Jakarta Mail liên quan có thể chứa `SendFailedException` và thông tin về các tập địa chỉ như `validSentAddresses`, `validUnsentAddresses`, `invalidAddresses`, tùy ngữ cảnh và cách transport báo lỗi. Trong Spring Mail, ngoại lệ khi gửi thường được bọc vào lớp như `MailSendException` hoặc các ngoại lệ `MailException` tương ứng.

**Không nên tự suy ra rằng một lỗi là “không ai nhận” hoặc một lần gửi không ném ngoại lệ là “mọi người đã nhận thư trong Inbox”.** Muốn theo dõi trạng thái từng người, cần cơ chế ghi nhận phản hồi hoặc sự kiện từ hạ tầng email, trong đó có khả năng thư bị trả lại (*bounce*).

### Tránh khẳng định tính nguyên tử

Thao tác gửi SMTP tới nhiều người nhận **không phải giao dịch nguyên tử** giống một transaction cơ sở dữ liệu. Có thể tồn tại tình huống một số địa chỉ đã được hạ tầng chấp nhận trong khi các địa chỉ khác bị từ chối, hoặc thư được nhận nhưng phản hồi cuối cùng thất lạc làm ứng dụng không biết chắc kết quả.

Đặc biệt, nếu thử lại **cả message** sau khi gặp lỗi không rõ trạng thái, một vài người có thể nhận email trùng. Hãy thiết kế việc gửi lại theo chính sách rõ ràng, không mặc định “gửi lại nguyên danh sách là an toàn”.

## 11. Theo dõi kết quả gửi cho từng người nhận

Nếu sản phẩm yêu cầu biết chính xác ai đã được nộp thư, ai bị từ chối và ai được chuyển phát, nên tách hai khái niệm:

- **Yêu cầu gửi chung:** mã thông báo, tiêu đề, mẫu nội dung, thời điểm phát sinh.
- **Trạng thái từng người nhận:** địa chỉ, vai trò To/Cc/Bcc, số lần thử, kết quả nộp thư và sự kiện chuyển phát.

Một mô hình dữ liệu ở tầng ứng dụng có thể là:

~~~text
mail_request:
  request_id: notif-2026-001
  template: maintenance-notice
  status: SUBMITTING

mail_recipient:
  - address: an@example.net
    role: TO
    delivery_status: SUBMITTED
  - address: binh@example.net
    role: TO
    delivery_status: FAILED
  - address: lead@example.net
    role: CC
    delivery_status: SUBMITTED
~~~

Đây là **mô hình ứng dụng tự định nghĩa**, không phải schema có sẵn của Spring Mail. Tên `SUBMITTED` chỉ nên biểu thị đã nộp thư hoặc được relay chấp nhận theo bằng chứng hiện có; `DELIVERED` chỉ dùng khi hệ thống có nguồn dữ liệu đủ đáng tin cậy về chuyển phát.

Nếu không có thông tin chi tiết cho từng người nhận từ SMTP transport hoặc provider, trạng thái nên phản ánh **mức độ biết được thực tế**, chẳng hạn `UNKNOWN` hoặc `PENDING_CONFIRMATION`. Không nên bịa ra trạng thái riêng chỉ vì một lần gọi gửi đã hoàn tất.

### Thử lại và chống gửi trùng

Một số biện pháp phù hợp với ứng dụng có yêu cầu tin cậy:

1. Gắn `requestId` riêng cho mỗi ý định gửi và theo dõi từng người nhận.
2. Lưu mẫu nội dung hoặc dữ liệu đủ để dựng lại message khi thử lại.
3. Phân loại lỗi cấu hình, lỗi tạm thời và lỗi do địa chỉ không hợp lệ.
4. Xác định số lần thử và thời gian chờ giữa các lần, không thử lại vô hạn.
5. Khi có phản hồi từng địa chỉ, cân nhắc thử lại **chỉ những đích chưa được xác nhận**; vẫn phải chấp nhận khả năng kết quả chưa rõ ràng.
6. Dùng outbox hoặc hàng đợi nếu cần tách gửi thư khỏi giao dịch nghiệp vụ.

Nếu bắt buộc **trạng thái cá nhân hóa và kiểm soát gửi lại riêng cho từng người**, mô hình **một message trên mỗi người nhận** thường dễ quản lý hơn một message chung có hàng trăm đích.

## 12. Những giới hạn vận hành khi gửi tới danh sách lớn

Một email gửi cho ba người và một email gửi cho ba nghìn người khác nhau về vận hành. Nhà cung cấp SMTP có thể đặt các giới hạn:

| Giới hạn có thể có | Tác động |
| --- | --- |
| Số người nhận tối đa trên một message | Server có thể từ chối một phần hoặc toàn bộ danh sách quá lớn |
| Số message/tốc độ gửi theo tài khoản | Thư bị trì hoãn, giới hạn hoặc tạm từ chối |
| Dung lượng message | Tệp đính kèm và mã hóa MIME có thể vượt giới hạn |
| Chính sách bảo mật/phát tán | Có thể bị đánh dấu là gửi hàng loạt, spam hoặc vi phạm điều kiện dịch vụ |
| Quy tắc xác minh địa chỉ gửi | `From` hoặc envelope sender không được chấp nhận |
| Quota và uy tín miền gửi | Tác động đến khả năng chấp nhận và chuyển phát |

Các mức giới hạn là **chính sách riêng của provider**, không được Spring Framework Mail quy định thống nhất. Vì vậy, không nên đặt một con số cố định kiểu “mỗi message luôn gửi được tối đa 100 người” mà chưa biết nhà cung cấp đang sử dụng.

### Có nên chia danh sách thành nhiều nhóm?

Khi có nhiều người nhận dùng chung nội dung, ứng dụng có thể chia thành các nhóm có số lượng phù hợp giới hạn provider. Nhưng mỗi nhóm thường cần **một message riêng**, được quản lý như một lần gửi độc lập; không phải chỉ chia danh sách trên bộ nhớ rồi truyền tất cả vào một `MimeMessage`.

Ví dụ ở mức mô hình:

~~~mermaid
flowchart TD
    A["Danh sách người nhận đã được cho phép"] --> B["Áp dụng chính sách bảo mật / giới hạn"]
    B --> C["Chia thành các nhóm"]
    C --> D["Message nhóm 1"]
    C --> E["Message nhóm 2"]
    C --> F["Message nhóm N"]
    D --> G["SMTP relay"]
    E --> G
    F --> G
~~~

Khi chia nhóm, cần tính đến việc một người có thể xuất hiện ở nhiều nhóm, tránh gửi trùng và xác định ai được phép thấy danh sách To/Cc. Nếu nhóm đông người cần giữ kín địa chỉ, sử dụng Bcc có thể hạn chế việc lộ header nhưng vẫn phải tuân thủ yêu cầu về đồng ý nhận thư, lựa chọn hủy nhận và hạn mức gửi.

## 13. Quyền riêng tư và kiểm soát nội dung

### 13.1. Không đưa danh sách khách hàng vào To/Cc của email hàng loạt

Ví dụ một website muốn gửi thông báo chung cho 500 khách hàng. Nếu tạo:

~~~text
To: customer1@example.net, customer2@example.net, ...
~~~

thì người nhận có thể nhìn thấy email của hàng trăm người khác. Đây là rủi ro quyền riêng tư ngay cả khi body không chứa dữ liệu nhạy cảm. **Không sử dụng To/Cc công khai cho danh sách nhận mà các thành viên không có quyền biết nhau.**

Có thể cân nhắc gửi từng người một hoặc dùng nền tảng gửi email hàng loạt chuyên dụng. Khi dùng Bcc, vẫn cần kiểm soát ai có thể xem danh sách trong hệ thống nội bộ, trong log và trong dashboard của nhà cung cấp.

### 13.2. Không gửi nội dung cá nhân hóa trong message chung

Email có mã OTP, liên kết xác nhận tài khoản, mã đặt lại mật khẩu, hóa đơn, số dư hoặc dữ liệu cá nhân phải được dựng theo đúng người nhận. Nếu có một token trong body rồi thêm nhiều địa chỉ vào Bcc, **mọi người nhận sẽ thấy cùng token đó**, gây lỗi bảo mật nghiệp vụ.

Mỗi người nên có nội dung/token riêng và một message riêng, hoặc dùng cơ chế cá nhân hóa có khả năng bảo đảm cách ly người nhận từ provider.

### 13.3. Địa chỉ Bcc vẫn có thể xuất hiện ở nơi khác

Ngay cả khi header Bcc không có trong thông điệp tới người nhận khác, địa chỉ Bcc có thể xuất hiện trong cơ sở dữ liệu yêu cầu gửi, log của ứng dụng, log SMTP, bản sao “Sent” hoặc hệ thống quản trị. Không xem Bcc là biện pháp thay thế quản lý truy cập.

Khi ghi log, nên dùng mã yêu cầu, số lượng người nhận và loại lỗi, tránh ghi toàn bộ mảng To/Cc/Bcc hay raw MIME. Nếu cần lưu địa chỉ để xử lý lỗi, nên có chính sách giới hạn quyền xem và thời gian lưu giữ.

## 14. Các lỗi thường gặp khi gửi một message đến nhiều người

### 14.1. Gọi setTo nhiều lần và làm mất danh sách cũ

~~~java
helper.setTo("an@example.net");
helper.setTo("binh@example.net");
~~~

Phương thức `setTo` là thao tác **đặt lại** trường To. Kết quả không tương đương với thêm cả hai địa chỉ. Đúng hơn là:

~~~java
helper.setTo(new String[] {
        "an@example.net",
        "binh@example.net"
});
~~~

Hoặc:

~~~java
helper.setTo("an@example.net");
helper.addTo("binh@example.net");
~~~

### 14.2. Nhầm Bcc với To ẩn

Nếu đưa người nhận vào To rồi ẩn ô hiển thị ở giao diện quản trị của ứng dụng, điều đó **không thay đổi header To của email**. Người nhận vẫn có thể nhìn thấy địa chỉ To. Muốn gửi bản sao ẩn theo luồng thư chuẩn, cần thực sự dùng `Bcc` hoặc tạo message riêng.

### 14.3. Tưởng gửi một message tạo nội dung riêng cho từng người

Một `MimeMessage` có một Subject và một body được serialize. Để thay tên, hóa đơn, token hoặc ngôn ngữ theo người nhận, cần dựng message tương ứng với từng người.

### 14.4. Chỉ có người nhận Bcc rồi cho rằng message không có địa chỉ nhận

Nếu kiểm tra duy nhất `getRecipients(TO)`, phương thức có thể trả `null` dù email vẫn có địa chỉ Bcc hợp lệ. Nếu chính sách nghiệp vụ cho phép Bcc-only, dùng `getAllRecipients()` để xét tổng số đích; còn nếu yêu cầu To bắt buộc, kiểm tra To riêng.

Một số chương trình đọc thư có cách hiển thị đặc biệt cho thư không có To công khai. Ứng dụng có thể đặt một header To mang tính mô tả theo cú pháp email phù hợp hoặc chọn gửi từng người riêng, tùy yêu cầu.

### 14.5. Cho rằng send() trả về nghĩa là tất cả đã vào Inbox

`JavaMailSender.send(...)` không tạo biên nhận cuối cùng từ từng mailbox. SMTP server có thể chấp nhận thư rồi hệ thống đích trả lại sau; thư cũng có thể đi vào spam. Cần theo dõi trạng thái riêng từ provider nếu sản phẩm cần biết kết quả chuyển phát.

### 14.6. Retry cả message sau lỗi gửi một phần

Một số địa chỉ có thể đã được chấp nhận, trong khi một số khác bị từ chối hoặc trạng thái chưa rõ. Gửi lại cả danh sách có thể gây email trùng. Với yêu cầu quan trọng, ghi nhận kết quả theo recipient hoặc chọn gửi từng người để đơn giản hóa việc quản lý.

### 14.7. Tin rằng InternetAddress.validate() xác thực mailbox từ xa

`InternetAddress.validate()` kiểm tra cấu trúc địa chỉ trong phạm vi Jakarta Mail hỗ trợ, chứ không gửi email thử hay xác định hộp thư tồn tại. Cần xử lý lỗi SMTP và bounce theo nghiệp vụ.

### 14.8. Sử dụng lại một MimeMessage đang bị thay đổi

`MimeMessage` là đối tượng **có thể thay đổi (mutable)**. Không nên cho nhiều luồng đồng thời sửa cùng một đối tượng để thêm người nhận rồi gửi. Điều này có thể làm lẫn To/Cc/Bcc, Subject, body và attachment giữa các yêu cầu khác nhau. Tạo message riêng cho mỗi yêu cầu gửi độc lập sẽ rõ ràng hơn.

## 15. Cách quan sát khi phát triển và kiểm thử

Trong môi trường thử nghiệm, có thể sử dụng một SMTP server phục vụ kiểm thử để nhận message mà không chuyển thư ra Internet. Khi đó quan sát được:

- Một lời gọi gửi đã tạo bao nhiêu thông điệp.
- Những địa chỉ nào được nộp qua SMTP envelope.
- Header To/Cc trong bản thư nhận có đúng danh sách dự kiến không.
- Bcc có được chuyển thành đích gửi mà không công bố trong header hiển thị không.
- Nội dung HTML, Unicode và tệp đính kèm có được dựng đúng không.

Với đơn vị kiểm thử của ứng dụng, có thể thay `JavaMailSender` bằng một mock hoặc fake để thu lại đối tượng `MimeMessage` ngay khi gọi `send(...)`. Chẳng hạn, kiểm tra những giá trị trả về bởi:

~~~java
message.getRecipients(Message.RecipientType.TO);
message.getRecipients(Message.RecipientType.CC);
message.getRecipients(Message.RecipientType.BCC);
message.getAllRecipients();
message.getSubject();
~~~

Khi quan sát đối tượng **trước khi gửi**, header Bcc có thể vẫn nằm trong message nội bộ; đây là điều bình thường để transport biết đích. Để xác minh **không lộ Bcc khi chuyển phát**, cần quan sát bản email thực được relay tạo ra và các header mà hộp thư nhận thấy, thay vì chỉ kiểm tra đối tượng MIME trước gửi.

Những phép kiểm tra này hỗ trợ phát triển tính năng, nhưng không thay thế việc vận hành một dịch vụ SMTP đúng cấu hình hoặc giám sát email bị trả lại ở môi trường thật.

## 16. Câu hỏi thực hành

**Câu 1.** Muốn gửi một thông báo chung tới An và Bình, đồng thời cho trưởng nhóm theo dõi, cần tạo bao nhiêu `MimeMessage`?

Có thể tạo **một `MimeMessage`** với To gồm An/Bình, Cc gồm trưởng nhóm, nếu cả ba được phép thấy danh sách người nhận và nhận **cùng nội dung**.

**Câu 2.** Muốn trưởng nhóm nhận bản sao mà An và Bình không thấy địa chỉ trưởng nhóm trong header, nên dùng gì?

Dùng **Bcc** hoặc gửi bản sao riêng theo quy trình thích hợp. Bcc che địa chỉ trong bản thư được chuyển phát thông thường, nhưng không mã hóa hay xóa dấu vết địa chỉ trong hệ thống gửi.

**Câu 3.** Tại sao một message có thể cần nhiều lệnh `RCPT TO` nhưng chỉ một `DATA`?

Bởi vì `RCPT TO` xác định những người nhận trong **SMTP envelope**, còn `DATA` mang nội dung **một thông điệp**. Mail server sẽ xử lý chuyển phát tới từng đích theo chính sách của nó.

**Câu 4.** Hai lần gọi `helper.setTo("an@example.net")` rồi `helper.setTo("binh@example.net")` có giữ cả hai địa chỉ không?

Không. `setTo` thay giá trị của trường To. Dùng một mảng hai địa chỉ hoặc gọi `addTo` cho địa chỉ thứ hai.

**Câu 5.** Nếu muốn mỗi người nhận có mã OTP khác nhau, có nên thêm tất cả vào Bcc của một email không?

Không. Bcc chỉ ẩn danh sách người nhận trong header; **body vẫn giống nhau**. Cần gửi message riêng với token của đúng người nhận.

**Câu 6.** Một email gửi cho ba địa chỉ và phương thức `send(...)` trả về mà không báo lỗi. Điều gì đã được xác nhận?

Thao tác nộp thông điệp tới hạ tầng gửi đã hoàn tất theo phản hồi mà client có được. Chưa thể kết luận mọi hộp thư nhận đã chuyển phát thành công hoặc người dùng đã đọc email.

**Câu 7.** Khi gặp lỗi từ một recipient, có nên tự động gửi lại nguyên message cho tất cả không?

Không nên coi đó là cách thử lại luôn an toàn. Cần hiểu lỗi và khả năng đã gửi một phần; khi không chắc kết quả, việc gửi lại có thể tạo bản sao trùng.

## 17. Mô hình ghi nhớ

Gửi một message đến nhiều người nhận trong Spring Framework Mail gồm ba lớp:

~~~mermaid
flowchart TD
    A["Nghiệp vụ: ai được nhận cùng nội dung?"] --> B["MimeMessage: To / Cc / Bcc"]
    B --> C["JavaMailSender.send(message)"]
    C --> D["SMTP envelope: nhiều RCPT TO"]
    D --> E["SMTP relay tiếp nhận và chuyển thư"]
    E --> F["Theo dõi trạng thái từng người nếu cần"]
~~~

Hãy ghi nhớ bốn nguyên tắc chính:

1. **Một `MimeMessage` có thể gửi đến nhiều địa chỉ.** Dùng `setTo`/`addTo`, `setCc`/`addCc` và `setBcc`/`addBcc` để tạo danh sách đúng vai trò.
2. **To/Cc/Bcc có ý nghĩa về khả năng hiển thị.** To và Cc thường công khai; Bcc cần được xử lý đúng luồng và không thay thế chính sách bảo mật dữ liệu người nhận.
3. **Mọi người của cùng một message dùng chung nội dung.** Nếu cần nội dung riêng, bảo mật riêng hoặc quản lý trạng thái độc lập, hãy tạo từng message riêng.
4. **Một lần gửi không bảo đảm chuyển phát thành công cho toàn danh sách.** SMTP có thể từ chối từng người, gặp lỗi sau khi chấp nhận hoặc trả lại thư về sau; hệ thống cần ghi nhận và xử lý theo mức độ tin cậy thực tế.

Khi hiểu rõ quan hệ giữa **message – recipient headers – SMTP envelope – trạng thái chuyển phát**, bạn sẽ biết lúc nào có thể tận dụng một message gửi chung và lúc nào phải thiết kế luồng gửi riêng cho từng người nhận để bảo đảm tính đúng đắn của nghiệp vụ.

