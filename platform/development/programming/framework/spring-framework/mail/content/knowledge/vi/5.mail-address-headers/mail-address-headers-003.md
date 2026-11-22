# From, To, Cc và Bcc

## 1. Bốn trường địa chỉ quan trọng trong email

Khi ứng dụng **Spring Framework Mail** gửi một thông báo, không chỉ nội dung mà **ai gửi** và **ai nhận được thư** cũng là một phần của hợp đồng giao tiếp. Bốn trường quen thuộc nhất là **From**, **To**, **Cc** và **Bcc**:

- **From**: địa chỉ hiển thị của người hoặc hệ thống gửi thư.
- **To**: danh sách người nhận chính, thường là những người được thông báo trực tiếp hoặc cần hành động.
- **Cc (Carbon Copy)**: danh sách người nhận bản sao để được biết thông tin; các địa chỉ này thường hiển thị cho các người nhận khác.
- **Bcc (Blind Carbon Copy)**: danh sách người nhận bản sao ẩn; thông thường những người nhận trong To/Cc và các Bcc khác không thấy danh sách Bcc.

Những trường này có hai ý nghĩa cần phân biệt: **ý nghĩa trao đổi thông tin với con người** và **ý nghĩa kỹ thuật trong cấu trúc email**. Ở tầng Spring, ứng dụng thiết lập chúng bằng **SimpleMailMessage** hoặc **MimeMessageHelper**; ở tầng vận chuyển, máy chủ SMTP sử dụng danh sách người nhận trong **SMTP envelope** để thực hiện giao thư.

| Trường | Ý nghĩa | Người nhận khác có thấy địa chỉ không? | Có dùng để chuyển phát không? |
|---|---|---|---|
| **From** | Người gửi được hiển thị | Thường có | Là header định danh người gửi; không thay thế envelope sender. |
| **To** | Người nhận chính | Thường có | Địa chỉ nhận được đưa vào envelope để giao thư. |
| **Cc** | Người nhận bản sao công khai | Thường có | Địa chỉ nhận cũng được đưa vào envelope. |
| **Bcc** | Người nhận bản sao ẩn | Thông thường không | Địa chỉ vẫn phải nằm trong envelope để SMTP biết nơi phát thư. |

**Điểm quan trọng nhất:** Bcc là cơ chế **ẩn địa chỉ khỏi header được hiển thị cho người nhận**, không phải cơ chế giấu danh tính khỏi máy chủ gửi thư, nhà cung cấp email hoặc hệ thống vận chuyển.

## 2. Minh họa một email có đủ From, To, Cc và Bcc

Giả sử hệ thống gửi một báo cáo tiến độ dự án:

~~~text
From: Project Updates <updates@example.com>
To: an@example.net
Cc: binh@example.net, chi@example.net
Bcc: audit@example.org
Subject: Báo cáo tiến độ tuần

Xin chào,
Báo cáo tiến độ tuần này đã được cập nhật.
~~~

Có thể hiểu như sau:

1. **updates@example.com** là địa chỉ người gửi hiển thị trên thư.
2. **an@example.net** là người nhận chính.
3. **binh@example.net** và **chi@example.net** nhận bản sao công khai; người nhận khác có thể biết hai địa chỉ này được đưa vào Cc.
4. **audit@example.org** nhận bản sao ẩn; bản email chuyển đến các người nhận khác thông thường không liệt kê địa chỉ này trong trường Bcc.

Tất cả người nhận hợp lệ đều có thể nhận **cùng một thông điệp**, nhưng vai trò To/Cc/Bcc khác nhau về **khả năng hiển thị địa chỉ** và **ngữ cảnh giao tiếp**. To không mặc nhiên “ưu tiên” đường truyền hơn Cc; Cc không khiến email có ít nội dung hơn; Bcc không tạo một giao thức chuyển phát riêng.

### Khi nào nên dùng từng trường?

| Tình huống | Lựa chọn thông thường | Lý do |
|---|---|---|
| Gửi mã xác nhận cho một tài khoản | **To** | Người nhận duy nhất cần thực hiện hành động. |
| Gửi kết quả xử lý yêu cầu cho khách hàng | **To** | Khách hàng là đối tượng chính. |
| Gửi thông báo cho người phụ trách và cho quản lý theo dõi | Người phụ trách ở **To**, quản lý ở **Cc** | Vai trò trao đổi thông tin rõ ràng. |
| Gửi bản sao theo dõi nội bộ mà không hiển thị trong danh sách công khai | **Bcc**, sau khi cân nhắc chính sách dữ liệu | Ẩn địa chỉ bản sao khỏi các trường công khai. |
| Gửi thông tin cá nhân hóa cho nhiều khách hàng không liên quan | **Một email riêng cho mỗi người** | Tránh lộ địa chỉ hoặc dữ liệu riêng của người nhận. |

Lựa chọn To, Cc hay Bcc không thay thế việc xác định **ai được phép nhận dữ liệu đó**. Một người nhận được đặt trong Bcc vẫn có thể đọc toàn bộ nội dung và tệp đính kèm của thư.

## 3. Header email và SMTP envelope: hai lớp địa chỉ khác nhau

Đây là nền tảng để hiểu chính xác From, To, Cc và Bcc trong kiến trúc email.

**Message headers** là các trường trong thông điệp email, chẳng hạn From, To, Cc, Subject, Reply-To và Message-ID. Email client thường dựa vào chúng để hiển thị nội dung, danh sách người tham gia và chức năng trả lời.

**SMTP envelope** là thông tin vận chuyển được trao đổi giữa SMTP client và server qua các lệnh như **MAIL FROM** và **RCPT TO**. Nó xác định địa chỉ trả lỗi và những đích cần giao thư. SMTP dùng envelope để chuyển phát, thay vì chỉ đọc nội dung header To/Cc.

Ví dụ khái niệm:

~~~text
SMTP envelope:
  MAIL FROM:<bounces@example.com>
  RCPT TO:<an@example.net>
  RCPT TO:<binh@example.net>
  RCPT TO:<audit@example.org>

Header trong nội dung email:
  From: Project Updates <updates@example.com>
  To: an@example.net
  Cc: binh@example.net
  Subject: Báo cáo tiến độ tuần
~~~

Trong ví dụ, SMTP server vẫn biết **audit@example.org** là người nhận cần giao thư vì có **RCPT TO**, mặc dù địa chỉ này không hiện trong những header được trình bày. Đồng thời, header **From: updates@example.com** khác envelope sender **bounces@example.com**.

~~~text
                       ỨNG DỤNG SPRING
                              |
                    Xây dựng MimeMessage
                   /                    \
                  v                      v
           Header của thư           SMTP envelope
           From, To, Cc             MAIL FROM
           Subject, Reply-To        RCPT TO (To/Cc/Bcc)
                  |                      |
                  +-----------+----------+
                              |
                              v
                       SMTP submission
                              |
                              v
                         Mail server đích
~~~

**Bcc được xử lý đặc biệt:** trong cách gửi phổ biến, thư viện hoặc hệ thống gửi sử dụng địa chỉ Bcc để tạo danh sách người nhận ở envelope nhưng loại bỏ header Bcc khỏi bản thư chuyển đến người nhận. Theo quy tắc email, việc xử lý bản sao Bcc có một số biến thể; vì vậy không nên khẳng định mọi hệ thống luôn tạo bản sao có header giống hệt nhau. Điều cần ghi nhớ là địa chỉ Bcc **không được tiết lộ cho các người nhận công khai chỉ vì họ nằm trong To hoặc Cc**.

### Vì sao không thể chỉ dựa vào header To?

Nếu thông điệp có:

~~~text
To: account-owner@example.net
Bcc: archive@example.org
~~~

thì SMTP phải có cách chuyển thư đến **archive@example.org**. Nếu chỉ nhìn header To, ta sẽ bỏ sót người nhận bản sao ẩn. Tương tự, thư gửi cho danh sách phân phối hoặc hệ thống chuyển tiếp có thể được phát tới địa chỉ không xuất hiện trực tiếp ở header To của bản cuối.

## 4. From: định danh người gửi hiển thị

**From** trả lời câu hỏi: *Ai chịu trách nhiệm hoặc là nguồn của thông điệp này theo thông tin hiển thị của email?*

Một giá trị From có thể chỉ là địa chỉ:

~~~text
From: no-reply@example.com
~~~

hoặc có cả **display name**:

~~~text
From: Thông báo hệ thống <no-reply@example.com>
~~~

Trong các thư tự động, From thường sử dụng hộp thư hoặc alias ổn định đã được nhà cung cấp gửi xác thực, ví dụ **notifications@example.com** hoặc **billing@example.com**.

### From không nhất thiết là tài khoản đăng nhập SMTP

Ứng dụng có thể dùng một tài khoản gửi được cấp quyền và đặt From theo alias hợp lệ. Nhưng **đặt một địa chỉ bất kỳ vào From không có nghĩa máy chủ SMTP sẽ cho phép gửi**. Nhà cung cấp có thể từ chối nếu địa chỉ không được xác minh hoặc không thuộc miền đã cấp quyền.

Hơn nữa, **header From** khác **SMTP envelope sender** (được dùng cho đường trả lỗi/bounce). Nhiều hệ thống email còn dùng SPF, DKIM và DMARC để đánh giá tính xác thực và quan hệ giữa miền From với thông tin xác thực vận chuyển. Vì vậy, không nên dùng một địa chỉ From tùy tiện để “giả làm” một tổ chức khác.

### From và Reply-To khác nhau

**Reply-To** là một header riêng: khi người nhận chọn **Reply**, email client thường gửi câu trả lời tới Reply-To nếu được cung cấp, thay vì gửi tới From.

~~~text
From: Notifications <no-reply@example.com>
Reply-To: support@example.com
To: customer@example.net
Subject: Thông tin yêu cầu hỗ trợ
~~~

Trong ví dụ, email được gửi bởi hệ thống thông báo nhưng câu trả lời được hướng tới **support@example.com**. Reply-To không tự biến support@example.com thành người nhận thông điệp ban đầu.

**From**, **Reply-To** và **envelope MAIL FROM** giải quyết ba nhu cầu khác nhau: nguồn hiển thị, nơi nhận phản hồi và đường xử lý thư không thể phát. Chúng có thể trùng hoặc khác nhau tùy kiến trúc email.

## 5. To: người nhận chính

**To** thường là những người được trực tiếp gửi thông tin hoặc được mong đợi hành động. Một email có thể có một hoặc nhiều địa chỉ To:

~~~text
To: customer@example.net
~~~

hoặc:

~~~text
To: an@example.net, binh@example.net
~~~

Khi có nhiều người trong To, họ thường thấy danh sách người nhận công khai. Do đó, trước khi gửi thư cho nhiều khách hàng, cần xét xem việc tiết lộ danh sách địa chỉ giữa các khách hàng có phù hợp hay không.

Trong ứng dụng nghiệp vụ, các tác vụ như gửi xác nhận tài khoản, đặt lại mật khẩu, hóa đơn cá nhân hoặc chi tiết đơn hàng thường nên **tạo một thông điệp riêng cho từng người nhận**. Không gộp nhiều khách hàng vào To khi mỗi người có dữ liệu hoặc đường dẫn riêng.

### To không quyết định ai thực sự nhận được

Trong thư thông thường, địa chỉ trong To được đưa vào danh sách người nhận SMTP. Tuy nhiên, To là **header mô tả vai trò người nhận**, không phải cơ chế định tuyến độc lập. Khi thư được forward, gửi qua mailing list hoặc qua một dịch vụ chuyển tiếp, tập người nhận thực tế có thể không trùng hoàn toàn với địa chỉ To hiển thị.

## 6. Cc: bản sao công khai

**Cc** viết tắt của *Carbon Copy*. Đây là quy ước giao tiếp, không phải một loại định dạng nội dung MIME khác với To. Người trong Cc thường:

- Được cập nhật để theo dõi một trao đổi.
- Không phải người xử lý chính, trừ khi nội dung thư nói rõ trách nhiệm khác.
- Có thể nhìn thấy các địa chỉ To và Cc được hiển thị trong bản thư.
- Có thể nhận các câu trả lời nếu người tham gia dùng **Reply All**, tùy cách email client xử lý.

Ví dụ:

~~~text
From: workflow@example.com
To: engineer@example.net
Cc: team-lead@example.net
Subject: Yêu cầu kiểm tra bản phát hành
~~~

Về kỹ thuật, Cc **không bảo đảm người nhận sẽ chỉ đọc** và cũng không giới hạn quyền truy cập attachment. Cc chỉ biểu thị vai trò trong cuộc trao đổi. Quyền dữ liệu phải được kiểm soát trước khi gửi.

### Reply và Reply All không giống nhau

Một thao tác **Reply** thường trả lời về From hoặc Reply-To. **Reply All** có thể thêm những người khác trong To và Cc vào câu trả lời, theo hành vi của email client. Vì vậy khi Cc một nhóm lớn, người nhận dễ tạo chuỗi phản hồi tới nhiều người.

Nếu ứng dụng cần nhận phản hồi có kiểm soát, hãy dùng Reply-To rõ ràng hoặc gửi các thông báo riêng khi hợp lý. Không nên trông chờ quy ước “Cc chỉ để biết” như một biện pháp kỹ thuật ngăn người nhận trả lời.

## 7. Bcc: bản sao ẩn và giới hạn quyền riêng tư

**Bcc** là *Blind Carbon Copy*: dùng khi cần gửi cùng một thông điệp cho một người nhưng không muốn công khai địa chỉ đó trong danh sách người nhận khác.

Ví dụ:

~~~text
From: announcements@example.com
To: coordinator@example.net
Bcc: observer@example.org
Subject: Thông báo cuộc họp
~~~

Người nhận ở **observer@example.org** vẫn phải được chuyển thư bằng SMTP envelope. Tuy nhiên, những người trong To/Cc thông thường sẽ không thấy observer trong header Bcc của bản thư họ nhận.

### Bcc ẩn điều gì, và không ẩn điều gì?

| Khả năng | Bcc có làm được không? |
|---|---|
| Ẩn địa chỉ Bcc khỏi danh sách người nhận To/Cc hiển thị | **Thông thường có**. |
| Giao được email cho Bcc | **Có**, vì địa chỉ này vẫn được nộp ở tầng vận chuyển. |
| Ẩn địa chỉ Bcc khỏi SMTP server hoặc nhà cung cấp gửi | **Không**. |
| Ẩn nội dung, subject và attachment khỏi người nằm trong Bcc | **Không**; họ cũng nhận được thư. |
| Mã hóa đầu cuối hoặc bảo đảm bí mật nội dung | **Không**. |
| Chắc chắn ngăn người nhận Bcc tiết lộ việc mình nhận thư | **Không**; họ có thể forward, chụp màn hình hoặc chủ động trả lời. |
| Bảo đảm tất cả nhà cung cấp xử lý header Bcc cùng một cách | **Không**; có khác biệt về cách tạo bản sao Bcc. |

**Một lưu ý với Reply All:** địa chỉ Bcc thông thường không xuất hiện trong header To/Cc của các bản thư công khai, nên email client không tự thêm người Bcc chỉ từ những header ấy. Tuy nhiên, nếu người nhận Bcc chủ động trả lời tất cả hoặc chuyển tiếp thư, sự tham gia của họ có thể bị lộ. Bcc là **ẩn địa chỉ theo cơ chế phân phối thư**, không phải cam kết bảo mật danh tính lâu dài.

### Bcc không phải giải pháp mặc định cho gửi thư hàng loạt

Một thông báo chung cho nhiều người có thể dùng Bcc để tránh công khai danh sách To/Cc. Tuy nhiên, gửi tới một danh sách khách hàng lớn bằng Bcc có nhiều nhược điểm:

- Hạn mức người nhận trên một email hoặc giới hạn tốc độ của SMTP/ESP.
- Thư gửi hàng loạt dễ bị bộ lọc đánh giá theo chính sách chống spam.
- Khó cá nhân hóa tên, nội dung, ngôn ngữ hoặc đường dẫn cho từng người.
- Khó thống kê trạng thái phát thư chính xác theo từng người.
- Rủi ro gửi nhầm toàn bộ danh sách trong To/Cc chỉ vì một lỗi lập trình.

Với thông báo có dữ liệu riêng hoặc quy mô lớn, nên dùng **một email riêng cho từng người nhận**, gửi qua hàng đợi/worker hoặc dịch vụ email thích hợp. Đối với thư tiếp thị, cũng cần tôn trọng sự đồng ý của người nhận và cơ chế ngừng nhận theo yêu cầu liên quan.

## 8. Dùng From, To, Cc và Bcc với SimpleMailMessage

Đối với thư văn bản thuần, Spring cung cấp **SimpleMailMessage**. Đây là đối tượng dữ liệu đơn giản có các setter tương ứng:

- **setFrom(String)** cho địa chỉ gửi.
- **setTo(String...)** cho một hoặc nhiều người nhận chính.
- **setCc(String...)** cho danh sách bản sao công khai.
- **setBcc(String...)** cho danh sách bản sao ẩn.
- **setReplyTo(String)** cho địa chỉ nhận phản hồi.
- **setSubject(String)** và **setText(String)** cho tiêu đề và nội dung.

**MailSender** cung cấp thao tác gửi **SimpleMailMessage**. **JavaMailSender** kế thừa **MailSender**, nên một bean JavaMailSender thông dụng cũng có thể gửi SimpleMailMessage.

### Ví dụ hoàn chỉnh: thư plain text có đủ bốn trường

~~~java
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;

@Service
public class ProjectUpdateMailService {

    private final MailSender mailSender;

    public ProjectUpdateMailService(MailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWeeklyUpdate() {
        SimpleMailMessage message = new SimpleMailMessage();

        message.setFrom("updates@example.com");
        message.setTo("an@example.net");
        message.setCc(
                "binh@example.net",
                "chi@example.net"
        );
        message.setBcc("audit@example.org");
        message.setReplyTo("project-help@example.com");
        message.setSubject("Cập nhật tiến độ tuần");
        message.setText("""
                Xin chào,

                Báo cáo tiến độ tuần đã được cập nhật.
                Vui lòng phản hồi khi cần bổ sung thông tin.
                """);

        mailSender.send(message);
    }
}
~~~

**Cách đọc ví dụ:**

1. Spring service chỉ phụ thuộc vào interface **MailSender**.
2. **setTo**, **setCc** và **setBcc** tạo ba nhóm vai trò người nhận.
3. **setReplyTo** hướng phản hồi về địa chỉ hỗ trợ dự án.
4. **send(message)** yêu cầu tầng gửi thư chuyển thông điệp tới hệ thống mail.

Đây là ví dụ minh họa; địa chỉ **example.com**, **example.net** và **example.org** không được dùng như một cấu hình gửi mail thật. Ứng dụng cần bean gửi thư và SMTP server hợp lệ. Bcc trong đối tượng SimpleMailMessage vẫn phải được tầng gửi dùng làm người nhận vận chuyển, ngay cả khi trường này không xuất hiện ở bản thư được hiển thị.

### Truyền nhiều địa chỉ

Có thể dùng mảng chuỗi khi danh sách người nhận có sẵn:

~~~java
String[] primaryRecipients = {
        "first@example.net",
        "second@example.net"
};

String[] copiedRecipients = {
        "team-lead@example.net"
};

message.setTo(primaryRecipients);
message.setCc(copiedRecipients);
~~~

**Một lời gọi setTo với mảng là cách thiết lập toàn bộ danh sách To.** Nếu cần tổng hợp người nhận từ nhiều nguồn, hãy xây dựng và kiểm tra danh sách cuối cùng trước khi gọi setter; không phụ thuộc vào việc gọi setter nhiều lần sẽ tự cộng dồn danh sách.

## 9. Dùng From, To, Cc và Bcc với MimeMessageHelper

Khi muốn gửi HTML, tài nguyên inline, attachment hoặc sử dụng cấu trúc email phức tạp, Spring thường dùng **JavaMailSender**, **MimeMessage** và **MimeMessageHelper**. Helper cung cấp các phương thức tương tự SimpleMailMessage, đồng thời làm việc với những địa chỉ MIME của Jakarta Mail.

### Ví dụ hoàn chỉnh: email HTML và bản text thay thế

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class ReleaseAnnouncementMailService {

    private final JavaMailSender mailSender;

    public ReleaseAnnouncementMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendAnnouncement() throws MessagingException {
        MimeMessage mimeMessage = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                mimeMessage,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("releases@example.com");
        helper.setTo(new String[] {
                "owner@example.net",
                "developer@example.net"
        });
        helper.setCc(new String[] {
                "manager@example.net"
        });
        helper.setBcc(new String[] {
                "release-audit@example.org"
        });
        helper.setReplyTo("release-support@example.com");
        helper.setSubject("Thông báo phiên bản mới");

        String plainText = """
                Phiên bản mới đã sẵn sàng.
                Xem chi tiết tại https://example.com/releases.
                """;
        String htmlText = """
                <html lang="vi">
                  <body>
                    <h2>Phiên bản mới đã sẵn sàng</h2>
                    <p>
                      Xem chi tiết tại
                      <a href="https://example.com/releases">trang phát hành</a>.
                    </p>
                  </body>
                </html>
                """;

        helper.setText(plainText, htmlText);
        mailSender.send(mimeMessage);
    }
}
~~~

Trong ví dụ này:

- **new MimeMessageHelper(..., true, UTF-8)** kích hoạt chế độ multipart, thích hợp cho hai biểu diễn plain text và HTML.
- **setTo(String[])**, **setCc(String[])** và **setBcc(String[])** thiết lập nhiều địa chỉ theo vai trò.
- **setText(plainText, htmlText)** tạo hai bản nội dung thay thế nhau theo MIME.
- **send(mimeMessage)** nộp email đã dựng cho hạ tầng gửi thư.

Nếu chỉ muốn một phần HTML, có thể dùng **helper.setText(htmlText, true)**. Nếu chỉ muốn plain text, có thể dùng **helper.setText(plainText)**. Trường địa chỉ From/To/Cc/Bcc **không phụ thuộc** vào việc body là HTML hay text.

### Tên hiển thị (display name) và ký tự tiếng Việt

Một địa chỉ có thể gồm **tên người hoặc tổ chức** cộng địa chỉ email. Với MimeMessageHelper, có thể khai báo From bằng dạng có tên hiển thị:

~~~java
helper.setFrom("no-reply@example.com", "Thông báo hệ thống");
~~~

Overload này có thể ném **java.io.UnsupportedEncodingException** khi encoding tên hiển thị, ngoài các vấn đề liên quan đến địa chỉ. Trong mã ứng dụng, hãy sử dụng charset UTF-8 phù hợp; nếu muốn xử lý tường minh, có thể tạo **jakarta.mail.internet.InternetAddress** với tên hiển thị được mã hóa đúng.

Khi sử dụng tên hiển thị có tiếng Việt, hãy để Jakarta Mail/MimeMessageHelper xử lý mã hóa header. Không tự nối chuỗi thô vào các header From, To, Cc, Bcc bằng cách ghép dữ liệu đầu vào.

## 10. Định dạng địa chỉ email và kiểm soát dữ liệu đầu vào

Một mailbox email thường được trình bày như:

~~~text
address@example.com
~~~

hoặc:

~~~text
Display Name <address@example.com>
~~~

Phần địa chỉ gồm **local-part** phía trước ký tự **@** và **domain** phía sau. Định dạng mailbox trong header còn có thể chứa tên hiển thị, dấu nháy và các quy tắc cú pháp khác. Vì vậy, không nên kiểm tra địa chỉ email bằng một regex quá đơn giản rồi mặc định mọi giá trị được chấp nhận đều có thể giao thư.

Ví dụ các trạng thái cần phân biệt:

| Tình huống | Ý nghĩa |
|---|---|
| Thiếu ký tự @ hoặc domain | Dữ liệu có thể sai cú pháp. |
| Chuỗi có xuống dòng hoặc dấu điều khiển | Có nguy cơ làm sai cách dựng header nếu thao tác raw không an toàn. |
| Địa chỉ đúng cú pháp nhưng domain không tồn tại | Có thể không gửi được dù ứng dụng chấp nhận định dạng. |
| Địa chỉ đúng cú pháp và domain tồn tại | Chưa chứng minh mailbox đó thật sự có người nhận. |
| Địa chỉ quốc tế hóa có ký tự Unicode | Cần hỗ trợ định dạng và khả năng SMTPUTF8 tương ứng của hệ thống gửi/nhận. |

**Các nguyên tắc khi nhận email từ HTTP request, database hoặc import file:**

1. Kiểm tra độ dài, định dạng và tính bắt buộc của từng trường theo nhu cầu nghiệp vụ.
2. Dùng API địa chỉ của Spring/Jakarta Mail để xây dựng header, thay vì tự thêm dòng From/To/Cc/Bcc vào một chuỗi MIME.
3. Loại bỏ hoặc từ chối input không mong muốn có thể làm sai định dạng header, đặc biệt là CR/LF không hợp lệ.
4. Xác định người dùng có **quyền gửi** tới tập người nhận này hay không; địa chỉ đúng cú pháp vẫn có thể là địa chỉ ngoài phạm vi được phép.
5. Xem xét dữ liệu trùng lặp giữa To, Cc và Bcc trước khi gửi, để không tạo nhiều vai trò không rõ ràng cho cùng địa chỉ.
6. Với các thông báo nhạy cảm hoặc cá nhân hóa, tạo thư riêng thay vì ghép tất cả người nhận vào cùng một email.

**Kiểm tra cú pháp không đồng nghĩa kiểm tra khả năng giao thư.** SMTP có thể từ chối địa chỉ ở nhiều chặng do policy, mailbox không tồn tại, quota hoặc lỗi mạng.

## 11. Bcc và địa chỉ người nhận khi gửi theo lô

Một kỹ thuật phổ biến nhưng dễ gây rủi ro là gom nhiều người dùng vào cùng một email và dùng Bcc. Nó có thể phù hợp với một số thông báo chung, nhưng không thích hợp cho dữ liệu cá nhân hóa.

### Mẫu dễ lộ thông tin

~~~java
// Không phù hợp khi các khách hàng không được phép biết địa chỉ của nhau.
message.setTo(customerEmails);
~~~

Các địa chỉ khách hàng nằm trong To có thể được hiển thị cho những người nhận khác. Nếu customerEmails chứa danh sách lớn hoặc thông tin khách hàng không liên quan, thao tác này có nguy cơ làm lộ dữ liệu.

### Mẫu Bcc cho thông báo chung

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("announcements@example.com");
message.setTo("announcements@example.com");
message.setBcc(
        "member-a@example.net",
        "member-b@example.net"
);
message.setSubject("Thông báo chung");
message.setText("Nội dung chung cho tất cả người nhận.");
mailSender.send(message);
~~~

Đây là minh họa cho danh sách nhỏ và nội dung không chứa dữ liệu riêng của từng người. **Địa chỉ To phải là địa chỉ thực sự hợp lệ, được kiểm soát và phù hợp chính sách của hệ thống gửi**; không dùng một địa chỉ ngẫu nhiên chỉ để làm đẹp header.

### Mẫu tách từng email cho dữ liệu cá nhân hóa

~~~java
public void sendPersonalNotice(
        MailSender sender,
        String recipient,
        String displayName
) {
    SimpleMailMessage message = new SimpleMailMessage();
    message.setFrom("notifications@example.com");
    message.setTo(recipient);
    message.setSubject("Thông báo tài khoản");
    message.setText("Xin chào " + displayName + ", tài khoản của bạn đã cập nhật.");
    sender.send(message);
}
~~~

Gọi phương thức này cho từng người (thông qua một worker/hàng đợi phù hợp khi số lượng lớn) giúp tách biệt danh sách nhận và nội dung. Tuy nhiên, ứng dụng vẫn cần kiểm soát tốc độ gửi, thời gian chờ, retry, trùng lặp và hạn mức của SMTP/ESP. Không chạy vòng lặp gửi hàng nghìn thư trong cùng request HTTP khi yêu cầu độ trễ và độ tin cậy cao.

## 12. From, Cc, Bcc và việc trả lời email

Hành vi **Reply** và **Reply All** liên quan trực tiếp đến các header:

| Thao tác ở email client | Kết quả thường gặp |
|---|---|
| **Reply** | Trả lời tới Reply-To, nếu có; nếu không, thường tới From. |
| **Reply All** | Trả lời tới người gửi/Reply-To và các người nhận trong To/Cc có thể xác định từ thư, tùy client. |
| **Forward** | Tạo thư gửi tiếp và có thể tiết lộ nội dung/header cho người nhận mới. |
| Người nằm trong **Bcc** chọn Reply All | Có khả năng tiết lộ rằng họ đã nhận thư. |

Không thể dùng Bcc để bảo đảm một cá nhân sẽ mãi không bị các bên khác biết đến. Người nhận Bcc cũng có thể gửi lại, chụp màn hình hoặc chia sẻ nội dung. Nếu có yêu cầu bảo mật mạnh hơn, hãy xác định đúng **quyền truy cập và kênh trao đổi**, không dựa hoàn toàn vào trường địa chỉ.

Tương tự, Cc không phải cơ chế phân quyền chỉ đọc. Người được Cc có cùng quyền đọc nội dung thư và tệp đính kèm như người trong To, trừ khi hệ thống cung cấp bảo vệ dữ liệu ở lớp khác.

## 13. Những lỗi liên quan đến địa chỉ và header trong Spring Mail

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Thư bị từ chối do sender | From không được nhà cung cấp cho phép hoặc miền gửi chưa cấu hình | Xác minh địa chỉ/miền gửi, tài khoản SMTP, SPF/DKIM/DMARC và policy của ESP. |
| SMTP báo không có người nhận hoặc người nhận sai | Danh sách To/Cc/Bcc trống, địa chỉ sai hoặc từ chối ở RCPT TO | Kiểm tra dữ liệu người nhận và phản hồi SMTP cụ thể. |
| Khách hàng nhìn thấy địa chỉ của nhau | Danh sách khách hàng bị đặt ở To/Cc | Chuyển sang gửi riêng hoặc dùng Bcc khi phù hợp với thông báo chung. |
| Người nhận Bcc không nhận được thư | Bcc chưa được đưa vào thông điệp/envelope, hoặc mail bị từ chối ở chặng sau | Kiểm tra quá trình dựng thư, recipient envelope và log ESP. |
| Reply đến nhầm địa chỉ | Không đặt Reply-To hoặc đặt sai | Thiết kế rõ địa chỉ nhận phản hồi. |
| Header xuất hiện ký tự lạ với tiếng Việt | Mã hóa tên hiển thị hoặc subject sai | Dùng API Jakarta Mail/Helper và UTF-8. |
| Một số người nhận thành công, một số thất bại | Server có thể chấp nhận một tập recipient và từ chối tập khác theo policy | Kiểm tra báo cáo theo từng người nhận; không mặc định mọi người đều nhận hoặc đều thất bại. |
| Bcc lộ sau khi người nhận phản hồi | Người trong Bcc đã trả lời tất cả hoặc forward | Giải thích giới hạn của Bcc và điều chỉnh luồng giao tiếp. |
| Email chỉ gửi vào Spam | Vấn đề uy tín miền/IP, nội dung hoặc xác thực gửi | Điều tra hạ tầng mail; To/Cc/Bcc không tự giải quyết deliverability. |

### Một lần send() có thể có kết quả khác nhau theo người nhận

Khi gửi thư có nhiều To/Cc/Bcc, các SMTP server có thể chấp nhận người nhận này nhưng từ chối người nhận khác. Hành vi trả lỗi và khả năng tiếp tục gửi tới recipient hợp lệ phụ thuộc cấu hình transport và server. **Không suy luận rằng toàn bộ danh sách chắc chắn thành công hay thất bại chỉ từ một kết quả tổng hợp**.

Spring Mail có họ exception **MailException**, trong đó **MailSendException** có thể mang thông tin lỗi gửi chi tiết. Ở tầng vận hành, cần đối chiếu thông báo SMTP, log ESP và trạng thái theo từng người nhận nếu nhà cung cấp hỗ trợ. Lỗi tạo địa chỉ, sai cú pháp hoặc cấu hình gửi thường phải được sửa trước khi retry; lỗi tạm thời mới thích hợp với retry có giới hạn.

## 14. Thiết kế dịch vụ gửi email dễ kiểm soát

Trong một ứng dụng lớn, không nên để mọi controller tự ghép danh sách From/To/Cc/Bcc tùy ý. Một service gửi thư có thể nhận đối tượng yêu cầu đã được kiểm tra trước:

~~~java
import java.util.List;

public record EmailRecipients(
        List<String> to,
        List<String> cc,
        List<String> bcc
) {
}
~~~

Một quy trình hợp lý là:

1. Nghiệp vụ chọn người nhận theo quyền và mục đích thông báo.
2. Lớp validation chuẩn hóa và kiểm tra danh sách To/Cc/Bcc, đồng thời loại bỏ những địa chỉ trùng khi chính sách yêu cầu.
3. Tầng gửi thư xây dựng SimpleMailMessage hoặc MimeMessage bằng API của Spring.
4. Tầng transport nộp thư cho SMTP/ESP và lưu kết quả có thể quan sát được.
5. Nếu cần theo dõi hoặc retry, ứng dụng lưu **notification ID**, trạng thái và số lần gửi; không ghi lộ địa chỉ hay nội dung nhạy cảm vào log.

### Ví dụ chuyển danh sách vào MimeMessageHelper

~~~java
import jakarta.mail.MessagingException;
import org.springframework.mail.javamail.MimeMessageHelper;

public void applyRecipients(
        MimeMessageHelper helper,
        EmailRecipients recipients
) throws MessagingException {
    helper.setTo(recipients.to().toArray(String[]::new));
    helper.setCc(recipients.cc().toArray(String[]::new));
    helper.setBcc(recipients.bcc().toArray(String[]::new));
}
~~~

Ví dụ giả định các danh sách không null và đã được validation theo quy tắc của ứng dụng. Nếu chỉ có Bcc, cần xác định cách hệ thống gửi và email client biểu diễn thư không có To công khai; không được tự điền To bằng một địa chỉ người dùng khác khi chưa có lý do nghiệp vụ.

Trong hệ thống gửi email quan trọng, việc lưu yêu cầu gửi trong queue hoặc transactional outbox có thể tách nghiệp vụ khỏi thời gian giao tiếp SMTP. Tuy vậy, gửi không đồng bộ và retry không tự bảo đảm “đúng một lần”; cần quản lý trùng lặp, trạng thái chưa xác định và chính sách nhà cung cấp.

## 15. Những hiểu nhầm thường gặp

**“Người nằm trong Cc không phải người nhận thật?”** Không. Cc là một vai trò giao tiếp; địa chỉ Cc vẫn phải được SMTP giao thư như những người nhận khác.

**“Bcc được ẩn khỏi mọi hệ thống?”** Không. SMTP server và dịch vụ gửi cần biết địa chỉ để thực hiện chuyển phát.

**“Đặt Bcc là đủ để bảo vệ thông tin cá nhân?”** Không. Người nhận Bcc vẫn thấy nội dung. Bcc không mã hóa email và không ngăn người nhận chuyển tiếp hoặc tiết lộ việc đã nhận.

**“From luôn phải giống tài khoản SMTP và MAIL FROM?”** Không nhất thiết. Tuy nhiên, địa chỉ From vẫn phải tuân thủ chính sách ủy quyền, xác thực miền và điều kiện của nhà cung cấp.

**“Reply luôn gửi về From?”** Không nếu header Reply-To đã được đặt và email client tuân theo header đó.

**“Gửi một email tới nhiều địa chỉ đồng nghĩa mọi người đã nhận thành công?”** Không. Các SMTP server hoặc ESP có thể từ chối một số recipient, trì hoãn hoặc trả bounce ở các chặng sau.

**“To, Cc, Bcc là các cách encode nội dung khác nhau?”** Không. Chúng là các trường địa chỉ/nhóm người nhận; việc dùng plain text, HTML, MIME attachment là một vấn đề riêng.

## 16. Ghi nhớ

**From** xác định người gửi hiển thị; **To** là người nhận chính; **Cc** là người nhận bản sao công khai; **Bcc** là người nhận bản sao thường bị ẩn khỏi header hiển thị cho các người nhận khác. Spring Framework Mail hỗ trợ thiết lập các trường này bằng **SimpleMailMessage** và **MimeMessageHelper**.

Ở tầng kỹ thuật, luôn tách **message headers** khỏi **SMTP envelope**: header diễn đạt cách thư xuất hiện với người đọc, còn envelope chứa các địa chỉ dùng để chuyển phát, kể cả Bcc. Hãy chọn người nhận theo quyền truy cập và nhu cầu nghiệp vụ, dùng **Reply-To** khi cần điều khiển nơi nhận phản hồi, kiểm tra địa chỉ bằng API thích hợp và gửi từng thư riêng nếu dữ liệu cần được cá nhân hóa hoặc giữ kín.
