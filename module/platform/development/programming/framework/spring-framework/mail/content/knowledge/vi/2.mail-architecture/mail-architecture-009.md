# Reply-To, Return-Path và địa chỉ người nhận thực tế

Trong kiến trúc email, **địa chỉ người đọc nhìn thấy**, **địa chỉ để họ trả lời** và **địa chỉ máy chủ dùng để xử lý thư bị trả lại** có thể hoàn toàn khác nhau. Một thông điệp còn có danh sách người nhận ở tầng giao thức SMTP, không nhất thiết trùng với các địa chỉ hiển thị trong phần **To** hoặc **Cc**.

Khi xây dựng chức năng gửi thư bằng **Spring Framework Mail**, việc phân biệt những địa chỉ này giúp tránh nhiều lỗi khó phát hiện: người dùng trả lời vào hộp thư không được theo dõi, thông báo gửi thất bại đi sai nơi, thư gửi cho người nhận ẩn bị lộ, hoặc ứng dụng cho rằng email đã đến đúng người chỉ vì trường **To** chứa một địa chỉ hợp lệ.

Bài học tập trung vào ba khái niệm:

1. **Reply-To**: đề xuất nơi nhận thư **khi con người chọn trả lời**.
2. **Return-Path**: dấu vết của **envelope sender** dùng cho thông báo lỗi phát thư; thường do máy chủ nhận thêm vào lúc phát thư cuối cùng.
3. **Người nhận thực tế**: các đích được xử lý bởi SMTP thông qua **RCPT TO** và các lần chuyển tiếp tiếp theo, có thể khác địa chỉ trong header **To/Cc/Bcc**.

Muốn hiểu đúng chúng, trước hết cần tách **nội dung email** khỏi **phong bì SMTP**.

## 1. Một email có hai lớp địa chỉ

Khi gửi một lá thư giấy, ta phân biệt nội dung viết bên trong với địa chỉ ghi trên phong bì. Email cũng có sự phân tách tương tự:

- **Message headers** là một phần của thông điệp theo định dạng email (RFC 5322), ví dụ **From**, **To**, **Cc**, **Reply-To**, **Subject**.
- **SMTP envelope** là thông tin các bên SMTP trao đổi để chuyển thư, đặc biệt là **MAIL FROM** và một hoặc nhiều lệnh **RCPT TO** (RFC 5321).

~~~text
Ứng dụng Spring
   |
   |  Tạo MIME message
   |  From: notifications@example.test
   |  Reply-To: support@example.test
   |  To: lan@customer.test
   |
   v
SMTP client (Jakarta Mail)
   |
   |  MAIL FROM:<bounce@bounces.example.test>
   |  RCPT TO:<lan@customer.test>
   |  DATA: [headers + nội dung MIME]
   |
   v
SMTP server / nhà cung cấp email
   |
   |  Chuyển tiếp, định tuyến, mở rộng alias nếu có
   v
Máy chủ nhận và hộp thư đích
   |
   |  Có thể thêm Return-Path từ envelope sender
   v
Người đọc xem From / To và bấm Reply hoặc Reply All
~~~

**Địa chỉ trong headers không điều khiển trực tiếp việc định tuyến SMTP**. Lệnh **RCPT TO** mới xác định địa chỉ đích được đề nghị cho lần chuyển SMTP tương ứng. Ngược lại, SMTP envelope thường không được hiển thị nguyên vẹn trong giao diện đọc thư, vì nó phục vụ hạ tầng chuyển phát.

### Những trường thường gặp và vai trò

| Thành phần | Nằm ở đâu? | Công dụng chính |
| --- | --- | --- |
| **From** | Header email | Danh tính tác giả/người gửi mà người đọc nhìn thấy |
| **Sender** | Header email, khi cần | Tác nhân gửi thay mặt tác giả trong một số tình huống |
| **Reply-To** | Header email | Địa chỉ mà ứng dụng thư nên dùng khi người đọc trả lời |
| **To** | Header email | Danh sách người nhận được trình bày công khai |
| **Cc** | Header email | Danh sách nhận bản sao công khai |
| **Bcc** | Thông tin người nhận khi tạo/gửi thư | Danh sách nhận bản sao ẩn; cần được giữ kín với người nhận khác |
| **MAIL FROM** | SMTP envelope | Địa chỉ trả về (reverse-path), được dùng để báo lỗi phát thư |
| **RCPT TO** | SMTP envelope | Địa chỉ nhận do SMTP client đề nghị cho lần chuyển |
| **Return-Path** | Header thường thêm ở khâu phát thư | Bản ghi reverse-path từ envelope khi thư tới điểm phát cuối |

Tên **From** dễ gây nhầm: **header From** trả lời câu hỏi “thư này xuất hiện là từ ai?”, còn **SMTP MAIL FROM** trả lời câu hỏi “nếu có thông báo không phát được thì phản hồi về địa chỉ nào?”. Chúng có thể khác nhau một cách hợp lệ.

## 2. Reply-To: nơi người đọc gửi câu trả lời

Header **Reply-To** cho biết địa chỉ mà phần mềm email nên hướng một câu trả lời thông thường tới. Ví dụ:

~~~text
From: "Nền tảng học tập" <notifications@example.test>
Reply-To: "Bộ phận hỗ trợ" <support@example.test>
To: "Lan" <lan@customer.test>
Subject: Xác nhận đăng ký khóa học
~~~

Người đọc thấy thư từ **notifications@example.test**, nhưng khi bấm **Reply**, ứng dụng thư thường đặt **support@example.test** vào ô người nhận phản hồi. Nhờ vậy hộp thư **notifications@** có thể dành cho thông báo tự động, còn **support@** nhận câu hỏi của người dùng.

Nếu không có **Reply-To**, ứng dụng thư thường sử dụng **From** làm địa chỉ trả lời mặc định. Tuy nhiên, hành vi cuối cùng do phần mềm email và thao tác của người dùng quyết định: người đọc vẫn có thể sửa địa chỉ, chọn **Reply All** hoặc chuyển tiếp.

### Reply, Reply All và Forward không giống nhau

**Reply** thường trả lời địa chỉ trong **Reply-To**, hoặc **From** nếu không có Reply-To. **Reply All** có thể bổ sung các địa chỉ trong **To** và **Cc** tùy cách client xử lý, loại bỏ địa chỉ của chính người trả lời và áp dụng những quy tắc khác. **Forward** là một thông điệp mới được người dùng chuyển tới địa chỉ họ chọn, không nhất thiết liên quan tới Reply-To.

**Reply-To không phải địa chỉ nhận thông báo lỗi phát thư (bounce)**. Một email thất bại trong quá trình chuyển phát được xử lý theo cơ chế SMTP/DSN và envelope sender, chứ không tự động gửi tới Reply-To chỉ vì header này tồn tại.

### Reply-To có thể là hộp thư, nhóm hoặc luồng hỗ trợ

Ví dụ:

- **support@example.test** cho câu hỏi khách hàng.
- **ticket-582@example.test** nếu hệ thống help desk định tuyến phản hồi theo mã ticket.
- **sales@example.test** cho báo giá, đặt lịch hoặc tư vấn.
- **replies@example.test** cho hộp thư được giám sát và phân loại tự động.

Địa chỉ Reply-To phải thật sự nhận và xử lý được email. Đặt Reply-To thành hộp thư không tồn tại sẽ khiến người dùng tin rằng có thể phản hồi trong khi thư không được xử lý. Đối với thư “không trả lời”, nên truyền đạt rõ chính sách hỗ trợ trong nội dung, thay vì chỉ đặt một địa chỉ **no-reply@** rồi mặc nhiên coi mọi phản hồi là không quan trọng.

## 3. Return-Path: dấu vết của địa chỉ nhận bounce

**Return-Path** là header dùng để ghi lại **reverse-path** của SMTP envelope tại nơi thư được phát vào hộp thư đích. Trong cách gửi thông thường, reverse-path bắt nguồn từ lệnh:

~~~text
MAIL FROM:<bounce@bounces.example.test>
~~~

Nếu thư không thể được chuyển phát, hệ thống có thể tạo một **Delivery Status Notification (DSN)**, hay **bounce**, và gửi thông báo lỗi về địa chỉ reverse-path phù hợp. Đây là cơ chế hạ tầng, tách khỏi thao tác “Reply” của con người.

Ví dụ sau khi máy chủ nhận phát thư, bản raw message mà người nhận xem có thể bắt đầu bằng:

~~~text
Return-Path: <bounce@bounces.example.test>
Received: from ... by ...
From: "Nền tảng học tập" <notifications@example.test>
Reply-To: <support@example.test>
To: <lan@customer.test>
Subject: Xác nhận đăng ký khóa học
~~~

Ở đây có **ba địa chỉ với ba mục đích**:

- **notifications@example.test**: người gửi được trình bày cho người đọc.
- **support@example.test**: nơi người đọc được hướng tới khi trả lời.
- **bounce@bounces.example.test**: nơi hạ tầng gửi thông báo không phát được khi dùng reverse-path đó.

### Return-Path không phải trường nên tự viết cứng để điều khiển SMTP

Một sai lầm thường gặp là tự thêm:

~~~text
Return-Path: <another-bounce@example.test>
~~~

vào MIME message rồi nghĩ rằng máy chủ sẽ gửi bounce tới địa chỉ đó. **Header Return-Path và SMTP MAIL FROM không tương đương về cách cấu hình**: việc đặt header thủ công không bảo đảm thay đổi envelope sender. Máy chủ nhận có thể xóa, ghi đè hoặc tự thêm Return-Path theo đường chuyển phát thực tế.

Muốn điều khiển địa chỉ nhận bounce, cần cấu hình **envelope sender** theo cơ chế SMTP client hoặc dịch vụ email hỗ trợ. Với một số dịch vụ, đây là cấu hình **custom MAIL FROM domain**, **bounce domain** hoặc **return-path domain**; nhà cung cấp cũng có thể viết lại envelope sender để quản lý bounce.

### Điều gì xảy ra nếu reverse-path rỗng?

Đối với các thông báo lỗi phát thư do hệ thống tự tạo, SMTP thường sử dụng **null reverse-path**:

~~~text
MAIL FROM:<>
~~~

Để đường trả về rỗng giúp ngăn một thông báo bounce tiếp tục tạo thêm bounce mới nếu không phát được, tránh vòng lặp thư lỗi. Khi thư như vậy được phát vào hộp thư, có thể thấy **Return-Path: <>**. Đây là cơ chế bình thường của giao thức, không đồng nghĩa lập trình viên quên đặt địa chỉ.

## 4. Địa chỉ người nhận thực tế: RCPT TO và định tuyến

Header **To** chủ yếu nói về **người nhận được hiển thị**. Nhưng SMTP quyết định giao thư cho ai bằng từng lệnh **RCPT TO**. Ví dụ:

~~~text
MAIL FROM:<bounce@bounces.example.test>
RCPT TO:<lan@customer.test>
RCPT TO:<archive@internal.test>
DATA
From: "Nền tảng học tập" <notifications@example.test>
Reply-To: <support@example.test>
To: "Lan" <lan@customer.test>
Subject: Xác nhận đăng ký khóa học

Xin chào Lan, ...
.
~~~

Đây là phiên SMTP được giản lược để minh họa. Các phản hồi của máy chủ, TLS, xác thực, mã MIME và những lệnh điều khiển khác đã được lược bỏ.

Thông điệp có thể được gửi tới **hai envelope recipients**, dù header **To** chỉ chứa **lan@customer.test**. Địa chỉ **archive@internal.test** có thể đến từ cấu hình **Bcc** trong ứng dụng và không xuất hiện trong header mà Lan nhận được. Không thấy một địa chỉ trong trường To không chứng minh địa chỉ đó không hề nhận thư.

### To, Cc và Bcc liên quan đến envelope như thế nào?

Khi ứng dụng dùng Jakarta Mail hoặc Spring Mail để gửi MIME message tới các địa chỉ **To**, **Cc** và **Bcc**, tầng gửi thường tổng hợp danh sách recipient để thực hiện lệnh **RCPT TO** tương ứng. Phần **To/Cc** được lưu làm headers hiển thị. **Bcc** là thông tin người nhận ẩn cần được xử lý sao cho không tiết lộ danh sách này cho những người nhận khác.

| Trường hợp | Người đọc thấy gì? | Địa chỉ SMTP có thể xử lý |
| --- | --- | --- |
| **To: lan@customer.test** | Lan xuất hiện trong To | lan@customer.test |
| Thêm **Cc: minh@customer.test** | Lan và Minh thấy các địa chỉ To/Cc | Lan và Minh |
| Thêm **Bcc: audit@internal.test** | Lan và Minh không được thấy audit trong bản thư của họ | Lan, Minh và audit |
| Gửi tới một **mailing list** | To có thể chỉ hiện địa chỉ nhóm | Máy chủ danh sách có thể mở rộng tới nhiều thành viên |
| Gửi tới một **alias** | To vẫn có thể hiện alias ban đầu | Máy chủ có thể ánh xạ tới hộp thư khác |
| Thư được **forward** tự động | To gốc có thể không đổi | Thư đi tiếp tới một đích mới |

**Bcc là tính năng ẩn người nhận của định dạng và quá trình gửi thư, không phải giải pháp bảo mật tuyệt đối.** Cần dùng đúng API và kiểm tra cách hệ thống gửi tạo bản sao cho Bcc. Nếu một công việc yêu cầu mỗi người nhận hoàn toàn không biết đến người khác, gửi **thông điệp riêng cho từng người** thường dễ kiểm soát hơn.

### “RCPT TO thành công” có phải thư đã nằm trong Inbox?

Không. Mỗi máy chủ SMTP có thể chấp nhận, từ chối hoặc tạm hoãn một recipient, sau đó tiếp tục định tuyến theo alias, forwarding rule hoặc chính sách nội bộ. Kể cả khi có phản hồi thành công lúc nộp thư, bước lọc spam, kiểm tra địa chỉ cuối cùng và phát vào mailbox vẫn có thể diễn ra ở phía sau.

Một batch gửi tới nhiều recipient có thể có kết quả **từng phần** tùy phản hồi và chính sách SMTP client/provider. Không nên suy ra trạng thái của từng người chỉ từ một nhãn “email đã gửi” chung.

## 5. Theo dấu một email từ Spring tới hộp thư

Giả sử hệ thống thông báo đặt lịch tư vấn:

~~~text
From:        notifications@study.example.test
Reply-To:    consultant@study.example.test
To:          customer@recipient.test
Bcc:         audit@study.example.test
Envelope:    bounce+booking-782@bounces.study.example.test
~~~

Ứng dụng tạo MIME message có **From**, **Reply-To**, **To** và **Bcc**. SMTP client gửi một phiên với **MAIL FROM** là địa chỉ bounce và các lệnh **RCPT TO** tới customer cùng audit. Máy chủ tiếp nhận xử lý từng địa chỉ, có thể đưa customer qua nhiều bước trung gian trước khi đến mailbox.

Sau khi được phát:

1. **Khách hàng mở thư** nhìn thấy người gửi **notifications@...**, không nhất thiết thấy địa chỉ envelope.
2. **Khách hàng chọn Reply**: phần mềm thư thường đặt **consultant@...** làm đích phản hồi theo Reply-To.
3. **Thư không phát được tới khách hàng**: hạ tầng có thể gửi DSN về **bounce+booking-782@...** nếu chính sách tạo bounce cho phép.
4. **Bộ phận audit** cũng nhận thư vì địa chỉ của họ được dùng làm một **envelope recipient**, dù không được liệt kê công khai trong To/Cc của bản gửi khách hàng.
5. **Nếu customer@... là alias**, hộp thư thực tế nhận có thể mang địa chỉ khác; email gốc vẫn có thể giữ **To: customer@recipient.test**.

Điểm quan trọng là **cùng một thông điệp có nhiều danh tính địa chỉ, mỗi danh tính trả lời một câu hỏi khác nhau**. Khi có sự cố, cần xác định mình đang truy tìm phản hồi của người dùng, thông báo bounce hay hành trình chuyển phát.

## 6. Tạo From, Reply-To và người nhận trong Spring Framework Mail

Spring cung cấp giao diện **JavaMailSender** và lớp **MimeMessageHelper** để thiết lập những header phổ biến:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class BookingMailService {

    private final JavaMailSender mailSender;

    public BookingMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                false,
                "UTF-8"
        );

        helper.setFrom("notifications@example.test");
        helper.setReplyTo("support@example.test");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đặt lịch");
        helper.setText("Lịch tư vấn của bạn đã được ghi nhận.", false);

        mailSender.send(message);
    }
}
~~~

Trong ví dụ:

- **setFrom(...)** điều chỉnh header **From**.
- **setReplyTo(...)** điều chỉnh header **Reply-To**.
- **setTo(...)** khai báo người nhận **To**.
- **setCc(...)** và **setBcc(...)** có thể dùng khi cần bản sao công khai hoặc bản sao ẩn.
- **send(...)** yêu cầu tầng mail thực hiện thao tác gửi; nó không chứng minh người nhận cuối đã nhìn thấy email trong Inbox.

Mã dùng các lớp **jakarta.mail** phù hợp với dòng Spring hiện đại sử dụng Jakarta Mail. Trường hợp dùng Spring phiên bản cũ dựa trên **javax.mail** cần lưu ý namespace tương ứng.

### Đặt Reply-To với SimpleMailMessage

Nếu chỉ cần email văn bản thuần, **SimpleMailMessage** cũng hỗ trợ thiết lập các địa chỉ thông thường:

~~~java
import org.springframework.mail.SimpleMailMessage;

SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("notifications@example.test");
mail.setReplyTo("support@example.test");
mail.setTo("customer@recipient.test");
mail.setSubject("Xác nhận");
mail.setText("Yêu cầu của bạn đã được ghi nhận.");

mailSender.send(mail);
~~~

Sự khác biệt giữa các đối tượng tạo thư không thay đổi ý nghĩa giao thức: Reply-To vẫn là header phục vụ trả lời; phần envelope được quyết định bởi SMTP client/transport và cấu hình liên quan.

## 7. Cấu hình MAIL FROM trong SMTP transport

Với SMTP transport dựa trên Jakarta Mail, thuộc tính **mail.smtp.from** thường được dùng để đặt **envelope sender**. Trong Spring Boot, có thể truyền thuộc tính này qua **spring.mail.properties**:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: "smtp-user"
    password: "<load-secret-from-environment>"
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.from]": "bounces@bounces.example.test"
      "[mail.smtp.connectiontimeout]": 3000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
~~~

Đây là cấu hình **minh họa**; máy chủ, cổng, TLS, xác thực và chính sách gửi phải tuân theo nhà cung cấp. Trong ứng dụng thật, username/password cần lấy từ biến môi trường hoặc cơ chế quản lý bí mật; chuỗi placeholder ở trên không phải mật khẩu có thể sử dụng.

Đặc biệt:

- Thuộc tính **mail.smtp.from** hướng SMTP client sử dụng địa chỉ envelope sender được chỉ định đối với transport tương ứng.
- Nó **không thay thế** header **From** đã thiết lập bằng **helper.setFrom(...)**.
- Nó **không thay thế** **Reply-To**.
- Nó **không đồng nghĩa** ta đã trực tiếp tạo hoặc kiểm soát header **Return-Path** cuối cùng.

Nếu không cấu hình envelope sender, giá trị mặc định phụ thuộc cách SMTP transport suy ra địa chỉ gửi và cấu hình môi trường. Không nên dựa vào suy đoán khi cần một địa chỉ nhận bounce cố định.

Thuộc tính trên là cấu hình dùng chung cho SMTP transport được cấu hình. Nếu mỗi luồng cần envelope sender riêng hoặc cần mã định danh bounce theo từng thông điệp, hãy kiểm tra cơ chế **per-message envelope sender** mà implementation/provider hỗ trợ, hoặc dùng API nhà cung cấp có tính năng tương ứng. **Không tự sửa header Return-Path để thay thế việc cấu hình MAIL FROM.**

### Nhà cung cấp có thể viết lại MAIL FROM

Một số dịch vụ chỉ cho phép địa chỉ/domain bounce mà họ quản lý, hoặc yêu cầu xác minh miền gửi. Chúng có thể nhận thông điệp với envelope sender do ứng dụng đề xuất rồi dùng một địa chỉ khác trong chặng SMTP tiếp theo để thu thập bounce.

Vì vậy, khi cần xác nhận Return-Path ngoài thực tế, nên kết hợp cấu hình SMTP phía ứng dụng, log hoặc dữ liệu gửi của provider, và bản raw message ở hộp thư nhận. Mỗi nguồn quan sát **những giai đoạn khác nhau**; một giá trị trong cấu hình Spring không nhất thiết xuất hiện nguyên vẹn ở mọi chặng.

## 8. SPF, DKIM và DMARC: vì sao From khác Return-Path lại quan trọng?

Các địa chỉ email không chỉ phục vụ hiển thị và định tuyến; tên miền của chúng còn liên quan đến xác thực nguồn gửi.

### SPF thường xét domain của SMTP MAIL FROM

**SPF (Sender Policy Framework)** giúp máy chủ nhận kiểm tra xem IP máy chủ gửi có được domain tương ứng ủy quyền hay không. Trong trường hợp thông thường, domain dùng để kiểm tra SPF lấy từ **RFC 5321 MAIL FROM** (envelope sender). Với null reverse-path, cơ chế kiểm tra có thể dựa trên danh tính **HELO/EHLO** theo quy tắc SPF.

Ví dụ:

~~~text
From: notifications@company.example
MAIL FROM:<bounce@bounces.provider.example>
~~~

SPF có thể pass cho **bounces.provider.example**, nhưng kết quả đó **không tự động chứng minh** thư được gửi thay mặt **company.example** ở header From.

### DKIM dùng chữ ký của domain ký thư

**DKIM** đặt chữ ký trong header để bên nhận kiểm tra tính toàn vẹn của các phần được ký và domain ký (tham số **d=**). Domain ký không nhất thiết giống địa chỉ Reply-To hoặc envelope sender.

### DMARC liên hệ với header From

**DMARC** dùng domain trong header **From** làm mốc căn chỉnh (**alignment**) với danh tính SPF hoặc DKIM. Tùy chính sách căn chỉnh relaxed/strict, DMARC có thể pass khi ít nhất một cơ chế được xác thực và căn chỉnh phù hợp với header From.

Nói cách khác:

- Thay **Reply-To** không làm SPF/DKIM/DMARC tự nhiên pass.
- Thay **Return-Path** hoặc **MAIL FROM** có thể ảnh hưởng domain được SPF kiểm tra và khả năng căn chỉnh SPF với From.
- Header **From** là danh tính quan trọng đối với DMARC; Return-Path không phải giá trị thay thế From.
- Một nhà cung cấp dùng bounce domain riêng và DKIM domain được căn chỉnh với From vẫn có thể đạt DMARC qua DKIM, dù SPF của envelope domain không căn chỉnh.

Vì vậy, khi gửi từ domain doanh nghiệp qua bên thứ ba, cần xem **cấu hình SPF, DKIM, DMARC và bounce domain** như một hệ thống nhất quán, thay vì chỉ sửa các địa chỉ trong mã Java.

## 9. Bounce, thư trả lời và thông báo tự động là các luồng riêng

Giả sử khách hàng không tồn tại hoặc hộp thư bị chặn, hệ thống có thể nhận một thông báo không phát được. Thông báo đó khác thư trả lời do người nhận chủ động soạn:

| Tình huống | Tín hiệu hoặc địa chỉ liên quan | Điều ứng dụng cần xử lý |
| --- | --- | --- |
| Người dùng bấm **Reply** | Reply-To hoặc From | Đọc, hỗ trợ hoặc đưa câu trả lời về đúng hội thoại |
| SMTP không phát được thư | MAIL FROM / Return-Path, DSN hoặc event provider | Ghi nhận lỗi phát, tránh tiếp tục gửi bừa tới địa chỉ hỏng |
| Provider báo deferred | SMTP response hoặc sự kiện chuyển phát | Chờ/retry theo chính sách; chưa kết luận thất bại vĩnh viễn |
| Người dùng bật tự động trả lời | Quy tắc mail client/server | Không giả định luôn đi theo Reply-To |
| Provider gửi webhook bounce | Dữ liệu sự kiện provider | Xác thực webhook, gắn về đúng thông điệp/công việc |
| Người dùng chuyển tiếp thư | Địa chỉ do người dùng hoặc quy tắc forward chọn | Không suy ra người nhận cuối chỉ từ To gốc |

Một **bounce mailbox** cần có cách thu thập và phân tích DSN, hoặc dịch vụ email có thể cung cấp các sự kiện tương đương. Chỉ đặt địa chỉ **bounces@...** mà không có hệ thống theo dõi thì ứng dụng vẫn không biết những thư nào đã không phát được.

### Địa chỉ bounce theo từng công việc gửi

Nếu dùng địa chỉ theo từng thông điệp như:

~~~text
bounce+booking-782@bounces.example.test
bounce+booking-783@bounces.example.test
~~~

thì có thể gắn thông báo lỗi về từng công việc gửi, với điều kiện miền và hạ tầng email hỗ trợ định tuyến địa chỉ đó. Cách tạo envelope sender khác nhau để đối chiếu từng người nhận hoặc từng thông điệp được gọi là **Variable Envelope Return Path (VERP)**. Cần bảo đảm cú pháp, tên miền và cơ chế nhận bounce phù hợp provider; không nên coi đây là tính năng mặc định mà mọi SMTP server đều tự thực hiện.

Khi bounce đến, một ứng dụng có thể dựa trên mã công việc để phân loại: địa chỉ không tồn tại, hộp thư đầy, bị chính sách chặn hoặc lỗi tạm thời. Không phải DSN nào cũng chứa mọi thông tin cần thiết, và provider có thể cung cấp trạng thái qua webhook thay vì gửi một thông điệp trở lại mailbox riêng.

## 10. Đọc raw email để điều tra: thấy gì và không thấy gì?

Khi khắc phục sự cố, tùy phần mềm email, ta có thể xem **Show original**, **View source** hoặc **View message headers**. Bản raw message thường chứa:

~~~text
Return-Path: <bounce@bounces.example.test>
Received: from outbound.example.test by mx.recipient.test ...
From: "Course Updates" <notifications@example.test>
Reply-To: <helpdesk@example.test>
To: "Lan" <lan@customer.test>
Subject: Thông báo khóa học
Message-ID: <some-id@example.test>
Date: ...
~~~

Cách đọc:

- **From**: danh tính xuất hiện trong email.
- **Reply-To**: đích được đề nghị để trả lời.
- **Return-Path**: reverse-path được ghi nhận ở lúc phát thư, nếu có và còn được giữ trong bản sao.
- **Received**: dấu vết xử lý qua các mail server; cần đọc trong bối cảnh và đánh giá độ tin cậy của từng hop.
- **Message-ID**: định danh thông điệp ở tầng header, hữu ích khi tương quan log nhưng không đồng nghĩa một lần phát thư hay một người nhận duy nhất.

Một số hệ thống thêm các header như **Delivered-To** hoặc **X-Original-To** để ghi nhận người nhận hoặc địa chỉ trước khi định tuyến. Các trường này **không xuất hiện thống nhất ở mọi nhà cung cấp** và không thể dùng làm nguồn sự thật phổ quát về mọi RCPT TO đã đi qua.

### Có thể suy ra đầy đủ envelope từ raw message không?

**Không chắc chắn.** Bản raw message ở hộp thư người nhận đã đi qua nhiều mail server; nó thường không lưu toàn bộ các lệnh SMTP **RCPT TO** trong lịch sử. Header **To** là nội dung hiển thị, không phải bản ghi các lần máy chủ chấp nhận recipient. Nhiều người có thể nhận bản sao của một MIME message nhưng chỉ nhìn thấy cùng trường To ban đầu.

Để biết tại chặng do ứng dụng kiểm soát đã gửi tới địa chỉ nào, cần dữ liệu từ quá trình tạo recipient, log SMTP hoặc log provider. Để biết một recipient sau forwarding thực sự phát đến mailbox nào, có thể cần log hoặc sự hỗ trợ từ hạ tầng mail nhận.

Khi ghi log, nên lưu định danh công việc gửi, mã thông điệp, trạng thái và thông tin cần thiết theo chính sách dữ liệu; tránh ghi toàn bộ nội dung thư, mật khẩu SMTP, token hoặc địa chỉ cá nhân quá mức cần thiết.

## 11. Các nhầm lẫn thường gặp khi tích hợp Spring Mail

### Nhầm 1: “Tôi đặt Reply-To để nhận bounce”

**Sai cơ chế.** Reply-To dành cho phản hồi theo thao tác của người đọc. Bounce do chuỗi chuyển phát SMTP xử lý, thường dựa trên envelope reverse-path hoặc sự kiện provider.

**Cách nghĩ đúng:** cấu hình địa chỉ nhận phản hồi và địa chỉ/bộ xử lý bounce như hai luồng trách nhiệm độc lập.

### Nhầm 2: “Đặt Return-Path bằng một header là đủ”

**Không bảo đảm.** Return-Path ở thư cuối có quan hệ với SMTP MAIL FROM; việc tự viết header không chắc ảnh hưởng envelope và có thể bị máy chủ thay thế.

**Cách nghĩ đúng:** dùng khả năng cấu hình envelope sender của transport/provider và quan sát kết quả thực tế.

### Nhầm 3: “Trong To có một địa chỉ thì thư chỉ gửi tới người đó”

**Không đủ căn cứ.** Cc, Bcc, alias, mailing list, forwarding và những bước định tuyến tiếp theo có thể làm số người thực nhận khác danh sách To.

**Cách nghĩ đúng:** phân biệt **display recipients** với **envelope recipients** và từng bước phát thư sau đó.

### Nhầm 4: “Bcc chỉ là cách ẩn trên giao diện”

**Thiếu.** Đúng cách, Bcc phải được xử lý ở quá trình tạo các bản sao và gửi để không tiết lộ người nhận ẩn trong dữ liệu hiển thị. Nếu tự lắp MIME message hoặc chuyển qua gateway không tương thích, có nguy cơ để lộ header không mong muốn.

**Cách nghĩ đúng:** sử dụng đúng API, kiểm tra bản thư được nhận ở các địa chỉ khác nhau, và gửi thư riêng khi yêu cầu quyền riêng tư cao.

### Nhầm 5: “Return-Path giống From nên cứ dùng chung”

Chúng **có thể** dùng cùng địa chỉ trong hệ thống rất đơn giản, nhưng có mục đích khác nhau. Khi sản lượng email lớn hoặc cần quản lý bounce, domain riêng cho envelope sender có thể hợp lý. Cấu hình phải tuân theo chính sách xác thực và tên miền được cấp quyền gửi.

### Nhầm 6: “Gọi JavaMailSender.send() xong nghĩa là người nhận đã nhận”

**Không suy ra được.** Thành công ở phía Spring thường chỉ cho biết thao tác submit sang mail transport/server hoàn tất tại giai đoạn đó. Thư có thể bị trì hoãn, trả lại, phân loại Spam hoặc chuyển tiếp.

**Cách nghĩ đúng:** định nghĩa trạng thái **SUBMITTED**, **DELIVERED**, **BOUNCED** theo dữ liệu thực có; dùng sự kiện provider nếu cần giám sát sau bước submit.

## 12. Thiết kế địa chỉ cho một ứng dụng thực tế

Giả sử hệ thống gửi email xác nhận, thông báo khóa học và hỗ trợ khách hàng. Có thể phân chia:

| Mục đích | Ví dụ | Lý do |
| --- | --- | --- |
| Header From | **notifications@example.test** | Danh tính thông báo hiển thị rõ cho người đọc |
| Reply-To | **support@example.test** | Phản hồi của người dùng được đọc và xử lý |
| SMTP MAIL FROM | **bounce@bounces.example.test** | Tách thông báo lỗi phát thư khỏi hộp thư hỗ trợ |
| To/Cc/Bcc | Địa chỉ theo từng công việc gửi | Đối tượng nhận được xác định bởi nghiệp vụ |
| Định danh công việc | **MAIL-JOB-782** | Tương quan log gửi, retry và provider events |

Trong môi trường có nhiều loại email, có thể tạo địa chỉ Reply-To theo nhóm hoặc ticket, còn envelope sender theo domain và cơ chế xử lý bounce của nhà cung cấp. Các địa chỉ ví dụ chỉ nhằm minh họa; địa chỉ thực tế phải thuộc miền tổ chức được phép sử dụng và đã cấu hình hạ tầng.

Một thiết kế vận hành được cần xác định:

1. **Ai được phép xuất hiện ở From?** Domain, tên hiển thị và chính sách xác thực có hợp lệ không?
2. **Ai xử lý Reply-To?** Có mailbox thật, quy trình hỗ trợ hoặc định tuyến ticket không?
3. **Ai nhận và phân tích bounce?** Có webhook/API/provider event hay mailbox được xử lý không?
4. **Ai là envelope recipient?** Danh sách được lấy từ đâu, có Bcc, danh sách nhóm hoặc alias nào không?
5. **Trạng thái nào ứng dụng có thể chứng minh?** Chỉ submit thành công hay có bằng chứng phát thư và bounce?

Việc tách các câu hỏi này giúp giảm phụ thuộc vào giả định sai rằng một trường địa chỉ có thể làm cùng lúc vai trò hiển thị, trả lời, xử lý lỗi và định tuyến.

## 13. Bài tập suy luận

Xem thông điệp minh họa:

~~~text
SMTP MAIL FROM:<bounce+order-15@bounces.shop.test>
SMTP RCPT TO:<accounting@shop.test>
SMTP RCPT TO:<client@customer.test>

From: "Shop" <orders@shop.test>
Reply-To: <help@shop.test>
To: <client@customer.test>
Subject: Xác nhận đơn hàng
~~~

**1. Khi client@customer.test bấm Reply, địa chỉ nào thường được chọn?**

**help@shop.test**, vì nằm trong **Reply-To**. Người dùng hoặc phần mềm thư vẫn có thể thay đổi lựa chọn đó.

**2. Nếu mail server không phát được tới client@customer.test, nên kỳ vọng thông báo lỗi đi đâu?**

Theo cơ chế reverse-path, thông báo lỗi có thể được gửi về **bounce+order-15@bounces.shop.test**, hoặc được nhà cung cấp báo qua hệ thống event tương ứng. Không mặc định nó sẽ đến **help@shop.test**.

**3. Tại sao accounting@shop.test có thể nhận thư dù không xuất hiện trong To?**

Vì SMTP transaction có **RCPT TO** cho địa chỉ này. Đây có thể là recipient được thêm theo Bcc hoặc chính sách gửi; header hiển thị không phản ánh toàn bộ danh sách envelope.

**4. Có thể khẳng định thư đã tới Inbox của client chỉ vì RCPT TO thành công không?**

**Không.** SMTP chấp nhận một recipient ở một bước không khẳng định quá trình phát cuối cùng đã hoàn tất hoặc được xếp vào Inbox.

**5. Nếu đọc raw message tại client, có chắc tìm thấy lệnh RCPT TO của accounting không?**

**Không.** Raw message thường chứa MIME headers và dấu vết do các server thêm vào, không phải toàn bộ transcript SMTP. Danh sách recipient ẩn không nên xuất hiện công khai trong bản thư gửi cho client.

## 14. Ghi nhớ đúng ranh giới

Khi viết mã Spring Mail, hãy đặt câu hỏi theo đúng lớp kỹ thuật:

~~~text
Người đọc nhìn thấy thư từ ai?
    -> From

Người đọc bấm Reply sẽ được hướng tới ai?
    -> Reply-To (hoặc From khi không có Reply-To)

Nếu hạ tầng không phát được thư, lỗi hướng về đâu?
    -> SMTP MAIL FROM / reverse-path, phản ánh bởi Return-Path

SMTP server được yêu cầu chuyển thư tới những ai?
    -> RCPT TO (có thể có nhiều địa chỉ)

Ai cuối cùng nhận được bản sao trong mailbox?
    -> Kết quả định tuyến, alias, forwarding và chính sách phát thư
~~~

**Reply-To, Return-Path và địa chỉ người nhận thực tế giải quyết ba vấn đề khác nhau**: phản hồi của người dùng, xử lý lỗi vận chuyển và định tuyến thông điệp. Phân biệt rõ chúng từ đầu giúp cấu hình Spring Framework Mail chính xác hơn, giải thích log đúng hơn và xây dựng hệ thống gửi email có khả năng hỗ trợ, theo dõi và phục hồi sự cố.
