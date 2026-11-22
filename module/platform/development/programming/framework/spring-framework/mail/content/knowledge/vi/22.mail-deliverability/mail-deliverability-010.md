# Hủy đăng ký và yêu cầu không gửi tiếp

Trong hệ thống gửi email, một thông điệp có thể đúng nội dung, được ký DKIM và được SMTP server chấp nhận nhưng vẫn làm giảm khả năng phát thư nếu người nhận **không còn muốn nhận**. Việc tiếp tục gửi các email không được mong đợi làm tăng nguy cơ người dùng bấm **Report spam**, nhà cung cấp dịch vụ thư hạn chế lưu lượng hoặc địa chỉ gửi bị ảnh hưởng danh tiếng. Vì vậy, khả năng **hủy đăng ký (unsubscribe)** và xử lý **yêu cầu không gửi tiếp (opt-out / do-not-contact)** là một phần thiết yếu của *deliverability*, không phải một liên kết trang trí ở cuối email.

Trong Spring Framework Mail, **JavaMailSender** và **MimeMessageHelper** chịu trách nhiệm soạn và gửi thông điệp. Chúng **không tự quản lý** trạng thái người dùng đã hủy đăng ký, danh sách chặn, lựa chọn chủ đề email hay yêu cầu không gửi tiếp. Những quy tắc đó phải được triển khai tại lớp nghiệp vụ, dữ liệu và luồng dispatch; email composer chỉ được phép gửi sau khi hệ thống đã quyết định thông điệp có hợp lệ đối với người nhận và loại email tương ứng.

Bài học này trình bày: phân loại email và phạm vi opt-out; cách tạo **List-Unsubscribe** và **one-click unsubscribe**; thiết kế endpoint, token và cơ sở dữ liệu; kiểm tra quyền gửi ở từng lần dispatch; xử lý retry, race condition và webhook; cùng ví dụ Java/Spring, kiểm thử và vận hành. Các tiêu chuẩn kỹ thuật liên quan được giải thích theo nguyên tắc chung; yêu cầu pháp lý và yêu cầu cụ thể của từng provider phải được kiểm tra theo quốc gia, loại dịch vụ và thời điểm triển khai.

## 1. Phân biệt unsubscribe, opt-out, suppression và delivery failure

Các khái niệm thường bị dùng lẫn nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Unsubscribe** | Người nhận yêu cầu dừng một hoặc nhiều luồng email đã đăng ký | Hủy bản tin tuần |
| **Opt-out / do-not-contact** | Người nhận không đồng ý tiếp tục nhận một loại liên lạc hoặc mọi liên lạc trong phạm vi xác định | Không nhận email quảng bá nữa |
| **Preference center** | Nơi người nhận chọn chủ đề, tần suất hoặc kênh liên lạc | Chỉ nhận cập nhật sản phẩm, không nhận ưu đãi |
| **Suppression list** | Danh sách được áp ở lúc dispatch để ngăn gửi tới một recipient hoặc scope cụ thể | Chặn mọi email marketing tới địa chỉ A |
| **Complaint** | Người nhận báo một message là spam với nhà cung cấp hộp thư | Feedback loop báo complaint |
| **Hard bounce** | Lỗi chuyển phát bền vững, ví dụ mailbox không tồn tại | SMTP báo địa chỉ người nhận không hợp lệ |
| **Soft bounce** | Lỗi tạm thời hoặc chưa chắc bền vững | Mailbox đầy, máy chủ nhận tạm thời từ chối |

Một người dùng hủy đăng ký là **ý định của người nhận**; một hard bounce là **tín hiệu kỹ thuật về khả năng phát thư**. Cả hai có thể dẫn đến suppression, nhưng **reason**, phạm vi chặn, thời hạn và khả năng khôi phục khác nhau.

Ví dụ người dùng hủy newsletter không có nghĩa tài khoản của họ không còn tồn tại hoặc không thể nhận xác nhận đổi mật khẩu. Ngược lại, một địa chỉ hard bounce liên tục không nên tiếp tục được thử vô hạn chỉ vì preference center vẫn ghi “subscribed”.

### Consent và preference không chỉ là một boolean

Một cờ **subscribed = true/false** trong bảng users thường không đủ:

- Một địa chỉ có thể thuộc nhiều tenant.
- Người dùng có thể đăng ký nhiều loại bản tin.
- Cùng địa chỉ có thể dùng cho nhiều tài khoản khác nhau.
- Người dùng có thể hủy email marketing nhưng vẫn cần thông báo bảo mật.
- Một global do-not-contact có mức ưu tiên cao hơn lựa chọn nhận từng bản tin.
- Các yêu cầu đồng ý hoặc rút lại đồng ý cần lịch sử và thời điểm.

Thay vì một cờ duy nhất, nên xác định **recipient + channel + purpose/category + scope** một cách rõ ràng.

## 2. Phân loại email trước khi quyết định có cho hủy đăng ký

Một hệ thống Spring Mail thường có nhiều luồng email:

| Nhóm | Ví dụ | Cách thiết kế preference |
| --- | --- | --- |
| **Marketing/promotional** | Khuyến mãi, newsletter, quảng bá sản phẩm | Cơ chế unsubscribe rõ ràng; phải tôn trọng opt-out |
| **Product updates / non-essential** | Tin về tính năng mới, sự kiện cộng đồng | Tùy chính sách, thường cho phép hủy hoặc chọn chủ đề |
| **Transactional / service** | Xác nhận đơn hàng, biên nhận, thông báo tình trạng yêu cầu | Xử lý theo mục đích giao dịch, hạn chế nội dung quảng bá |
| **Security/critical** | Xác minh đăng nhập, thông báo thay đổi mật khẩu | Kiểm soát theo mục đích bảo mật, không dùng để lách opt-out marketing |
| **Operational notices** | Bảo trì hệ thống, thay đổi quan trọng về tài khoản | Cần phân loại cụ thể theo ngữ cảnh và nghĩa vụ sản phẩm |

**Đừng mặc định gắn nhãn transactional để bỏ qua việc hủy đăng ký.** Nếu email xác nhận đơn hàng chứa một chiến dịch quảng cáo lớn, cách phân loại theo mục đích thực tế có thể khác với tên class hoặc template. Hãy tách nội dung marketing khỏi thông điệp cần thiết và kiểm tra các quy định áp dụng.

Tương tự, không nên vô điều kiện chặn mọi email hệ thống vì người dùng đã tắt newsletter. Việc bỏ qua một email khôi phục mật khẩu có thể gây hại cho khả năng sử dụng tài khoản. Chính sách loại email cần được định nghĩa cùng bộ phận sản phẩm, quyền riêng tư và pháp chế nếu liên quan.

### Thiết kế loại thông báo có ý nghĩa

~~~java
public enum MailPurpose {
    MARKETING_NEWSLETTER,
    MARKETING_PROMOTION,
    PRODUCT_ANNOUNCEMENT,
    ORDER_RECEIPT,
    SECURITY_ALERT
}
~~~

Một hàm policy trong ứng dụng có thể phân biệt:

~~~java
public enum ConsentRequirement {
    MARKETING_OPT_IN,
    NON_ESSENTIAL_PREFERENCE,
    SERVICE_POLICY,
    SECURITY_POLICY
}
~~~

Không có enum nào trong hai ví dụ trên là API mặc định của Spring Mail; đây là các khái niệm nghiệp vụ do ứng dụng định nghĩa. Điều quan trọng là **purpose được gán bởi workflow đáng tin cậy**, không cho người gọi tùy ý chọn SECURITY_ALERT để lách suppression.

### Một email nên có một mục đích chính

Nếu trộn email khuyến mãi vào biên nhận thanh toán, hệ thống khó biết có phải tôn trọng unsubscribe marketing cho toàn bộ email đó hay không. Giải pháp thường tốt hơn:

1. Gửi biên nhận giao dịch với nội dung cần thiết.
2. Gửi quảng bá bằng luồng riêng chỉ cho người đã đủ điều kiện.
3. Ghi nhận trạng thái/định danh riêng cho từng notification.

Điều này giúp audit và xử lý opt-out chính xác hơn.

## 3. Phạm vi của yêu cầu “không gửi tiếp”

Một yêu cầu unsubscribe cần chỉ rõ **ngừng cái gì, cho ai, trong phạm vi nào**.

Ví dụ:

~~~text
Recipient:        customer-392
Channel:          EMAIL
Tenant:           shop-7
List/Purpose:     NEWSLETTER_WEEKLY
Effective state:  UNSUBSCRIBED
Updated at:       2026-11-12T09:15:00Z
Source:           ONE_CLICK_UNSUBSCRIBE
~~~

Một người nhận có thể hủy **một danh sách cụ thể**, **tất cả email marketing từ thương hiệu** hoặc **mọi liên lạc không thiết yếu**, tùy tùy chọn đã được hiển thị và thỏa thuận. Không được âm thầm biến một lựa chọn “không nhận newsletter” thành hủy cả cảnh báo bảo mật; cũng không được hiểu “ngừng mọi quảng bá” là chỉ chặn một chiến dịch.

### Thứ tự ưu tiên các quy tắc

Một cách diễn đạt policy:

~~~text
Global do-not-contact / suppression bắt buộc
                  |
                  v
   Chặn theo tenant hoặc sender brand
                  |
                  v
          Chặn theo purpose/list
                  |
                  v
       Preference cụ thể của người nhận
                  |
                  v
         Điều kiện gửi từ workflow
                  |
                  v
              ALLOW / DENY
~~~

Ví dụ logic:

- Nếu recipient đang ở global marketing suppression, không gửi bất kỳ mail marketing nào, kể cả khi một danh sách riêng còn cờ subscribed.
- Nếu recipient chỉ hủy newsletter, vẫn có thể nhận thông báo sản phẩm khác **khi chính sách và consent của thông báo đó cho phép**.
- Nếu provider thông báo complaint/hard bounce, phải áp chính sách riêng về khả năng gửi và không cố vượt suppression bằng sender khác.
- Nếu người dùng vừa hủy đăng ký, trạng thái suppression mới phải được ưu tiên trước các job marketing cũ.

Một policy engine nên trả về kết quả cùng **mã lý do** thay vì chỉ một boolean:

~~~text
DENIED_GLOBAL_OPT_OUT
DENIED_LIST_UNSUBSCRIBE
DENIED_NO_VALID_CONSENT
DENIED_HARD_BOUNCE
DENIED_COMPLAINT
ALLOWED
~~~

Lý do này hỗ trợ observability và vận hành mà không cần ghi quá nhiều thông tin cá nhân.

## 4. Vì sao deliverability phụ thuộc vào việc tôn trọng unsubscribe?

Người dùng không tìm thấy cách hủy đăng ký có thể:

- Báo thư là spam.
- Chặn sender hoặc domain.
- Xóa thư hàng loạt mà không tương tác.
- Khiếu nại qua provider, support hoặc cơ quan có thẩm quyền.

Các tín hiệu này có thể ảnh hưởng đến cách hệ thống nhận thư đánh giá lưu lượng. Khả năng phát thư không chỉ được quyết định bởi cấu hình DNS hay việc gọi **mailSender.send(...)** không ném exception; **mức độ người nhận muốn nhận thư** cũng có ý nghĩa lâu dài.

Một luồng unsubscribe tốt thường có các đặc tính:

1. **Dễ tìm:** người nhận nhận biết rõ cách dừng thư.
2. **Ít thao tác:** không bắt người nhận đăng nhập chỉ để hủy email marketing khi có lựa chọn one-click phù hợp.
3. **Đúng phạm vi:** giải thích danh sách/chủ đề bị hủy.
4. **Idempotent:** người nhận bấm nhiều lần không tạo tác động khác hoặc lỗi khó hiểu.
5. **Được thực thi:** trạng thái mới chặn cả các công việc gửi đang chờ.
6. **Quan sát được:** có log/audit trạng thái và nguồn yêu cầu.
7. **Không bị lách:** các luồng bulk, retry, requeue và provider API đều dùng cùng một chính sách suppression.

## 5. Hủy đăng ký qua liên kết trong nội dung email

Một email marketing có thể chứa:

~~~text
Bạn nhận thư này vì đã đăng ký bản tin sản phẩm.
Hủy đăng ký: https://mail.example.test/preferences/u/<opaque-token>
~~~

Phần HTML tương ứng:

~~~html
<p>
  Bạn nhận thư này vì đã đăng ký bản tin sản phẩm.
  <a href="https://mail.example.test/preferences/u/opaque-example">
    Hủy đăng ký
  </a>
</p>
~~~

Ở production, URL chứa token thực sự được tạo từ server, không phải một chuỗi có thể đoán từ email address. Người dùng bấm link có thể tới trang xác nhận trạng thái hoặc preference center, tùy workflow.

### Không bắt người dùng nhập lại mật khẩu để ngừng marketing

Nếu muốn dừng một newsletter, một flow yêu cầu tạo tài khoản, đăng nhập, nhập OTP rồi đi qua nhiều trang thường gây khó chịu và khiến người dùng chọn “Report spam” thay vì unsubscribe. Cơ chế hủy cần dễ dùng, đồng thời bảo vệ token và phạm vi yêu cầu.

### GET không nên gây thay đổi trạng thái

Nhiều email client và hệ thống an ninh tự mở/scan link trong email. Nếu chỉ cần **GET /unsubscribe/token** đã chuyển thành UNSUBSCRIBED, một link scanner có thể vô tình hủy đăng ký.

Hướng triển khai an toàn hơn:

- **GET** hiển thị trang xác nhận/thông tin, không thay đổi trạng thái.
- **POST** thực hiện hành động hủy theo token hợp lệ.
- Với one-click chuẩn, nhà cung cấp hộp thư dùng một **POST** được quy định riêng.

Phân biệt một link trong nội dung email để người dùng thao tác với **one-click unsubscribe header** được nói ở phần tiếp theo.

## 6. Các MIME header hỗ trợ hủy đăng ký

Bên cạnh footer HTML/plain text, email dạng danh sách có thể thêm **List-Unsubscribe** để cung cấp cho email client thông tin hủy đăng ký ở mức header.

Ví dụ:

~~~text
List-Unsubscribe: <https://mail.example.test/u/abC123opaque>, <mailto:leave-newsletter@example.test>
~~~

Header này mô tả những cơ chế mà sender hỗ trợ. Nhiều email client có thể dùng nó để cung cấp hành động **Unsubscribe** trong giao diện của họ, không yêu cầu người nhận tự tìm đường link trong footer.

### List-Unsubscribe không phải cơ chế chặn gửi

Chỉ thêm header vào message **không làm người dùng tự động bị chặn ở lần gửi sau**. Hệ thống phải triển khai endpoint/email processor, cập nhật preference hoặc suppression ở database và kiểm tra trạng thái trước các lần gửi tiếp theo.

Nếu URL trong header trả lỗi, endpoint không tồn tại hoặc chỉ chuyển người nhận đến một trang yêu cầu đăng nhập mà không xử lý, trải nghiệm unsubscribe có thể không hoạt động như mong đợi.

### Các phương thức được biểu diễn trong header

| Phương thức | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| **HTTPS URL** | Endpoint hoặc trang unsubscribe trên hệ thống sender | URL phải thuộc domain đáng tin và có token/scope hợp lệ |
| **mailto:** | Địa chỉ nhận yêu cầu hủy đăng ký qua email | Phải có bộ xử lý mailbox và gắn yêu cầu đúng recipient/list |
| **One-click POST** | Cách thực thi trực tiếp bằng POST theo RFC 8058 | Cần thêm List-Unsubscribe-Post và endpoint chuẩn |

Nếu cung cấp **mailto**, phải thực sự xử lý thư gửi tới địa chỉ đó. Chỉ để một địa chỉ mailto nhưng không có worker theo dõi không đáp ứng nhu cầu hủy đăng ký.

### Không tự nối header từ input chưa kiểm tra

URL và mailbox xuất hiện trong header nên được xác định bằng application configuration và token server sinh. Không dùng:

~~~java
message.setHeader(
        "List-Unsubscribe",
        request.unsubscribeUrl()
);
~~~

vì request có thể khiến sender giới thiệu một endpoint không đáng tin hoặc một phạm vi xử lý không đúng. Tên header là hằng số, URL được build từ base URL đáng tin và token scoped, còn mọi giá trị được đưa vào header cần được kiểm tra không có ký tự điều khiển.

## 7. One-click unsubscribe theo RFC 8058

**RFC 8058** định nghĩa cách dùng hai header:

~~~text
List-Unsubscribe: <https://mail.example.test/one-click/opaque-token>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
~~~

Ý nghĩa:

- **List-Unsubscribe** cung cấp HTTPS URI xử lý yêu cầu.
- **List-Unsubscribe-Post** cho biết sender hỗ trợ one-click POST.
- Khi người nhận thực hiện hành động hủy trong email client hỗ trợ, client/provider có thể gửi **HTTP POST** tới HTTPS URI.
- Nội dung body của yêu cầu theo cơ chế one-click bao gồm trường biểu mẫu **List-Unsubscribe=One-Click**.
- Endpoint tiếp nhận POST cần thực thi unsubscribe theo token/scope, không yêu cầu tương tác bổ sung.

Ví dụ request minh họa:

~~~http
POST /one-click/opaque-token HTTP/1.1
Host: mail.example.test
Content-Type: application/x-www-form-urlencoded

List-Unsubscribe=One-Click
~~~

Đây là sơ đồ HTTP rút gọn. Tên token là placeholder; production phải dùng giá trị khó đoán, được tạo riêng cho notification scope hoặc người nhận phù hợp.

### Vì sao dùng POST thay vì GET?

Các hệ thống an ninh thường truy cập URL trong email để phân tích link. Nếu GET gây hủy đăng ký, link scanner có thể tạo unsubscribe ngoài ý định. Cơ chế RFC 8058 dùng POST để phân biệt hành động rõ ràng với truy cập link thông thường.

Vì thế:

~~~text
GET /one-click/token
    -> Không đổi preference/suppression

POST /one-click/token
Body: List-Unsubscribe=One-Click
    -> Đánh dấu đã unsubscribe đúng scope
~~~

### One-click phải thật sự là một thao tác

Không nên biến one-click POST thành một chuỗi:

~~~text
POST -> login -> CAPTCHA -> chọn lý do -> bấm Confirm
~~~

Một endpoint được dùng cho one-click nên xác định người nhận/list từ token và **cập nhật trạng thái ngay** khi request hợp lệ; có thể cung cấp preference center như lựa chọn bổ sung trong footer, nhưng không yêu cầu bước đó để hoàn tất one-click.

### Hủy đăng ký không đồng nghĩa yêu cầu opt-in lại

Một unsubscribe token chỉ được quyền **giảm** phạm vi gửi không thiết yếu theo thiết kế, không được cấp quyền subscribe lại. Nếu người dùng muốn đăng ký lại, cần quy trình rõ ràng và đủ bằng chứng theo chính sách consent. Không triển khai một endpoint toggle, vì lặp POST hoặc bot có thể bật lại subscription đã tắt.

### DKIM và các header unsubscribe

RFC 8058 yêu cầu các header liên quan one-click được bảo vệ bằng **DKIM signature** phù hợp. Nếu sender tự tạo List-Unsubscribe nhưng nhà cung cấp SMTP/ESP thay đổi hoặc ký message theo cách không bao gồm các header liên quan, các mailbox providers có thể không hiển thị hoặc không tin cậy hành động one-click.

Trong thực tế, ký DKIM thường do **mail provider hoặc hệ thống gửi ở ranh giới outbound** thực hiện, không phải do MimeMessageHelper. Cần kiểm tra raw message phía nhận để xác nhận List-Unsubscribe và List-Unsubscribe-Post được bảo toàn và được ký đúng cách. Không coi việc gọi setHeader trước JavaMailSender.send(...) là bằng chứng DKIM đã hợp lệ.

### Vấn đề deliverability và yêu cầu từng provider

Một số provider có yêu cầu đối với lưu lượng bulk/marketing, bao gồm xác thực miền, cơ chế unsubscribe dễ dùng và one-click phù hợp. Yêu cầu, ngưỡng áp dụng và thời gian xử lý có thể thay đổi. Hãy đối chiếu tài liệu sender requirements hiện hành của provider sử dụng, chứ không dùng một con số cố định trong bài như một quy định áp dụng toàn thế giới.

## 8. Thêm List-Unsubscribe bằng Spring Mail

Với **JavaMailSender** và **MimeMessageHelper**, application có thể đặt các header bằng API của **MimeMessage**:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class NewsletterComposer {

    private final JavaMailSender mailSender;

    public NewsletterComposer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public MimeMessage compose(
            String recipient,
            String subject,
            String htmlBody,
            String oneClickUrl
    ) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("newsletter@example.test");
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(htmlBody, true);

        message.setHeader(
                "List-Unsubscribe",
                "<" + oneClickUrl + ">"
        );
        message.setHeader(
                "List-Unsubscribe-Post",
                "List-Unsubscribe=One-Click"
        );

        return message;
    }
}
~~~

Ví dụ này chỉ minh họa **cơ chế thêm header**, giả định recipient, subject, HTML và URL đã được tạo/kiểm tra bằng chính sách của application. Không truyền oneClickUrl từ request tùy ý; phải tạo từ host HTTPS đáng tin và token server sinh. Với code production, dùng một service/policy riêng để xác nhận **recipient được phép nhận newsletter** trước khi compose và trước khi submit.

### URL trong List-Unsubscribe phải được cấu trúc an toàn

Một cách tạo:

~~~java
import java.net.URI;

public final class UnsubscribeUrls {

    private static final String PUBLIC_BASE =
            "https://mail.example.test";

    private UnsubscribeUrls() {
    }

    public static URI oneClick(String token) {
        if (!token.matches("[A-Za-z0-9_-]{32,128}")) {
            throw new IllegalArgumentException(
                    "Token không đúng định dạng"
            );
        }

        return URI.create(
                PUBLIC_BASE + "/one-click/" + token
        );
    }
}
~~~

**PUBLIC_BASE** phải đến từ cấu hình server đáng tin, không lấy từ HTTP Host hoặc X-Forwarded-Host chưa được kiểm soát. Token base64url không chứa CR/LF nên phù hợp để đưa vào URL path segment sau khi kiểm tra chặt. Trong ứng dụng thực tế cần bảo đảm format token sinh ra và regex kiểm tra nhất quán.

### Nội dung body vẫn cần cách hủy dễ tìm

One-click header là cơ chế dành cho email client/provider; không phải mọi email client đều hiển thị nút unsubscribe. Email marketing vẫn nên có đường dẫn hủy rõ ràng trong HTML và plain text footer, được gắn đúng recipient/list.

### Khi có nhiều danh sách marketing

Một message có thể thuộc newsletter A, promotion B hoặc announcement C. URL one-click cần hủy đúng **subscription list** mà message đại diện. Nếu sender dùng một URL global cho mọi loại mail, phải chắc chắn đó là lựa chọn do sản phẩm cam kết; nếu không sẽ hủy quá rộng.

Không thể an toàn chỉ dùng recipient email trong URL mà không có thông tin tenant/list/scope và khả năng xác thực token.

## 9. Token unsubscribe phải khó đoán và có phạm vi rõ

One-click cần chạy không có bước đăng nhập người nhận, nên URL mang một dạng **bearer capability**: ai sở hữu token hợp lệ có thể thực hiện hành động được giới hạn bởi token đó. Vì vậy token phải:

- Được sinh từ bộ tạo số ngẫu nhiên mật mã an toàn.
- Có độ entropy đủ lớn để khó đoán hoặc brute force.
- Gắn với recipient, tenant, list/purpose và hành động hủy tương ứng.
- Không chứa email address, user ID tuần tự hoặc thông tin cá nhân ở dạng đọc được.
- Chỉ cho phép **unsubscribe**, không cho phép nâng quyền hay subscribe lại.
- Có chính sách lưu, thu hồi và tuổi thọ phù hợp với yêu cầu hỗ trợ email cũ.

### Sinh token ngẫu nhiên bằng Java

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class UnsubscribeTokens {

    private static final SecureRandom RANDOM = new SecureRandom();

    private UnsubscribeTokens() {
    }

    public static String generate() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }
}
~~~

32 byte ngẫu nhiên cho ra token base64url có độ dài khoảng 43 ký tự. Không dùng **UUID tuần tự**, timestamp, email address hoặc order number một mình làm token unsubscribe. Không cần nhúng mọi metadata vào URL; metadata có thể được lưu server-side theo hash token.

### Lưu hash thay vì token thô

Khi tạo token, ứng dụng có thể lưu **SHA-256 hash** của token trong database và chỉ đưa token thô vào email. Khi nhận POST:

1. Kiểm tra hình thức token.
2. Băm token nhận được theo cùng thuật toán.
3. Tìm record bằng hash.
4. Xác định recipient/list/tenant đã gắn với record.
5. Cập nhật suppression một cách idempotent.

Token ngẫu nhiên có entropy cao nên hash SHA-256 phù hợp để làm lookup key và giảm nguy cơ token bị lộ nguyên bản qua database. Với token có entropy thấp như mật khẩu do con người chọn, phải dùng một cơ chế lưu khác có chống brute force; không được suy luận rằng SHA-256 đủ cho mọi loại bí mật.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class UnsubscribeTokenHashes {

    private UnsubscribeTokenHashes() {
    }

    public static String sha256(String token) {
        try {
            byte[] digest = MessageDigest
                    .getInstance("SHA-256")
                    .digest(
                            token.getBytes(StandardCharsets.US_ASCII)
                    );
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                    "SHA-256 không được hỗ trợ",
                    ex
            );
        }
    }
}
~~~

Ở production, chỉ băm chuỗi đã qua validation base64url/ASCII. **Không log token thô**, không gắn token vào metric labels và giới hạn quyền xem access logs của proxy.

### Thời hạn token: cân bằng bảo mật và khả năng hủy

Một unsubscribe link trong email cũ vẫn có thể được người nhận mở sau nhiều tháng. Nếu token hết hạn quá sớm và không có cách hủy thay thế, người nhận có thể mất khả năng dừng thư. Ngược lại, giữ token vô thời hạn làm tăng thời gian rủi ro nếu URL bị lộ.

Chọn TTL theo chính sách sản phẩm, yêu cầu provider và khả năng phục hồi tài khoản. Có thể dùng token dài hạn có phạm vi **chỉ-unsubscribe**, cho phép tái lập liên kết hủy ở các mail mới, hoặc cung cấp một preference center dễ tiếp cận. Không tạo token ngắn hạn theo cách làm one-click vô hiệu ngay sau khi email được gửi.

## 10. Yêu cầu opt-out phải có tính idempotent

Người nhận có thể bấm unsubscribe nhiều lần; mailbox provider có thể retry POST khi timeout; hoặc nhiều request tới cùng endpoint có thể xảy ra đồng thời.

Hành vi mong đợi:

~~~text
POST lần 1 -> trạng thái UNSUBSCRIBED
POST lần 2 -> vẫn UNSUBSCRIBED
POST lần 3 -> vẫn UNSUBSCRIBED
~~~

Một lần POST lại **không** được đảo trạng thái thành SUBSCRIBED. Đây là lý do không nên dùng endpoint dạng toggle.

### Phân biệt idempotency với việc không ghi audit

State update cần idempotent, nhưng hệ thống có thể vẫn ghi nhận các lần gọi/replay phục vụ giám sát hoặc bảo mật với giới hạn phù hợp. Không phải mỗi POST đều cần tạo một event nghiệp vụ mới hoặc gửi một email xác nhận opt-out mới; điều đó có thể khiến người đã hủy đăng ký vẫn tiếp tục nhận email không mong muốn.

### Không phát sinh email marketing sau khi xác nhận hủy

Khi endpoint trả thành công, chính sách gửi ở tất cả worker/campaign cần quan sát được trạng thái mới. Một API chỉ ghi “request received” rồi tiếp tục gửi hàng giờ mà không cập nhật suppression là một thiết kế rủi ro. Nếu có xử lý bất đồng bộ, cần xác định rõ thời điểm hiệu lực và đảm bảo các job dispatch tôn trọng trạng thái này.

## 11. Thiết kế dữ liệu subscription, token và suppression

Một hệ thống có thể tách dữ liệu thành ba nhóm:

1. **Subscription/preference:** người nhận có đăng ký một danh sách hoặc loại nội dung cụ thể hay không.
2. **Suppression:** quyết định chặn gửi vì opt-out toàn cục, complaint, bounce hoặc các chính sách khác.
3. **Unsubscribe token/audit:** token ánh xạ tới recipient/list và lịch sử yêu cầu đã được xử lý.

Ví dụ schema PostgreSQL đơn giản:

~~~sql
CREATE TABLE mail_subscription (
    tenant_id VARCHAR(80) NOT NULL,
    recipient_id VARCHAR(120) NOT NULL,
    list_id VARCHAR(120) NOT NULL,
    subscribed BOOLEAN NOT NULL,
    source VARCHAR(80) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, recipient_id, list_id)
);

CREATE TABLE mail_suppression (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    recipient_id VARCHAR(120) NOT NULL,
    scope VARCHAR(80) NOT NULL,
    reason VARCHAR(80) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_mail_suppression
        UNIQUE (tenant_id, recipient_id, scope, reason)
);

CREATE TABLE mail_unsubscribe_token (
    id UUID PRIMARY KEY,
    token_hash CHAR(64) NOT NULL UNIQUE,
    tenant_id VARCHAR(80) NOT NULL,
    recipient_id VARCHAR(120) NOT NULL,
    list_id VARCHAR(120) NOT NULL,
    purpose VARCHAR(80) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    unsubscribed_at TIMESTAMPTZ
);
~~~

Schema là **minh họa**, không phải entity/JPA schema được Spring Mail tự tạo. Tên scope, reason, recipient identity và policy phải theo mô hình sản phẩm. Nếu consent được quản lý theo email address thay vì account ID, cần thiết kế quan hệ cụ thể giữa email đã được xác minh và user/tenant.

### Vì sao không dùng một bảng unsubscribed_emails duy nhất?

Với một ứng dụng đơn giản, một danh sách email bị chặn có thể đủ để khởi đầu. Nhưng khi có nhiều tenant, danh sách và loại email, cần phân biệt:

- User A đã hủy newsletter X trong tenant T.
- User A không muốn tất cả marketing của brand B.
- Địa chỉ email Z bị hard bounce, không nên gửi dù tài khoản đã đổi subscription.
- Recipient có thể đổi địa chỉ liên hệ và cần xác minh địa chỉ mới.
- Hai tài khoản có thể có cùng mailbox và cần quy tắc do-not-contact theo mailbox.

Nếu chỉ lưu **email -> unsubscribed=true**, hệ thống có thể chặn quá rộng hoặc quá hẹp.

### Trạng thái permission và suppression cần được kết hợp

Một **mail_subscription.subscribed=true** không được ghi đè **mail_suppression.active=true** ở scope áp dụng. Quy tắc kiểm tra nên xác định rõ thứ tự ưu tiên thay vì dùng giá trị ghi gần đây nhất trên hai bảng.

Ví dụ:

~~~text
SUBSCRIPTION = TRUE
SUPPRESSION  = GLOBAL_MARKETING_OPT_OUT
RESULT       = DENY
~~~

Một yêu cầu subscribe lại hợp lệ không nên tự động xóa complaint suppression hoặc bounce suppression mà không có quy trình phù hợp.

### Lưu lịch sử mà không lưu token thô

Audit tối thiểu có thể chứa:

~~~text
event_id       = ...
recipient_id   = ...
tenant_id      = ...
list_id        = NEWSLETTER_WEEKLY
action         = UNSUBSCRIBE
source         = RFC8058_ONE_CLICK
occurred_at    = ...
token_record   = ...
~~~

Không lưu raw token vào log. Có thể giữ token hash và record ID đủ để điều tra khi một request đến nhiều lần. Với yêu cầu quyền riêng tư, thiết kế thời hạn lưu và xóa dữ liệu cá nhân theo chính sách cụ thể.

## 12. Cập nhật subscription trong một transaction

Khi nhận token hợp lệ, service cần cập nhật trạng thái **UNSUBSCRIBED** trong một transaction database:

~~~sql
INSERT INTO mail_subscription (
    tenant_id, recipient_id, list_id, subscribed,
    source, updated_at
)
VALUES (
    :tenant_id, :recipient_id, :list_id,
    FALSE, 'RFC8058_ONE_CLICK', CURRENT_TIMESTAMP
)
ON CONFLICT (tenant_id, recipient_id, list_id)
DO UPDATE SET
    subscribed = FALSE,
    source = 'RFC8058_ONE_CLICK',
    updated_at = CURRENT_TIMESTAMP;
~~~

Câu lệnh là ví dụ PostgreSQL. Nó hoạt động idempotent về **trạng thái hiệu lực**: gọi lặp lại vẫn có subscribed=false. Nếu hệ thống cần giữ nguyên thời điểm hủy lần đầu, điều chỉnh logic updated_at/audit thay vì ghi đè mỗi lần replay.

### Một service Spring xử lý yêu cầu

Ví dụ thiết kế repository do ứng dụng định nghĩa:

~~~java
public record UnsubscribeIdentity(
        String tenantId,
        String recipientId,
        String listId
) {
}

public interface UnsubscribeTokenRepository {

    UnsubscribeIdentity findActiveIdentityByTokenHash(
            String tokenHash
    );

    void markUsed(String tokenHash);
}

public interface MailSubscriptionRepository {

    void markUnsubscribed(
            String tenantId,
            String recipientId,
            String listId,
            String source
    );
}
~~~

Trong ví dụ, **findActiveIdentityByTokenHash(...)** trả null nếu token không tồn tại, đã bị thu hồi hoặc quá hạn. Cách biểu diễn Optional/exception là quyết định của dự án. Để tránh race khi thu hồi token và hủy, implementation nên có transaction/locking hoặc update điều kiện phù hợp.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UnsubscribeService {

    private final UnsubscribeTokenRepository tokenRepository;
    private final MailSubscriptionRepository subscriptionRepository;

    public UnsubscribeService(
            UnsubscribeTokenRepository tokenRepository,
            MailSubscriptionRepository subscriptionRepository
    ) {
        this.tokenRepository = tokenRepository;
        this.subscriptionRepository = subscriptionRepository;
    }

    @Transactional
    public void unsubscribe(String opaqueToken) {
        if (opaqueToken == null
                || !opaqueToken.matches("[A-Za-z0-9_-]{32,128}")) {
            throw new InvalidUnsubscribeTokenException();
        }

        String tokenHash =
                UnsubscribeTokenHashes.sha256(opaqueToken);
        UnsubscribeIdentity identity =
                tokenRepository.findActiveIdentityByTokenHash(tokenHash);

        if (identity == null) {
            throw new InvalidUnsubscribeTokenException();
        }

        subscriptionRepository.markUnsubscribed(
                identity.tenantId(),
                identity.recipientId(),
                identity.listId(),
                "RFC8058_ONE_CLICK"
        );
        tokenRepository.markUsed(tokenHash);
    }
}
~~~

Ví dụ exception:

~~~java
public class InvalidUnsubscribeTokenException
        extends RuntimeException {
}
~~~

**UnsubscribeService** không gửi email xác nhận marketing sau khi hủy. Nếu cần ghi nhận một email xác nhận phục vụ yêu cầu pháp lý/nghiệp vụ, việc có gửi hay không phải được đánh giá riêng; không lợi dụng xác nhận hủy để gửi thêm nội dung quảng bá.

### Không vô hiệu hóa token sau lần đầu theo cách phá idempotency

Nếu **markUsed(...)** được implement bằng cách revoke token ngay sau POST đầu, lần POST thứ hai có thể trả lỗi mặc dù trạng thái unsubscribe đã thành công. Điều này không lý tưởng cho provider retry.

Một thiết kế tốt hơn là **đánh dấu thời điểm sử dụng đầu tiên nhưng vẫn nhận lại cùng token trong phạm vi chính sách**, rồi trả success khi người nhận đã ở trạng thái UNSUBSCRIBED. Một token có thể bị revoke do sự cố bảo mật, nhưng việc hủy thành công không nhất thiết phải làm mọi replay hợp lệ trở thành lỗi.

Khi triển khai, repository cần phân biệt token chưa tồn tại, bị revoke vì bảo mật, token đã dùng và trạng thái đã unsubscribe.

## 13. Endpoint POST one-click trong Spring MVC

Một controller nhận đúng yêu cầu theo RFC 8058:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/one-click")
public class OneClickUnsubscribeController {

    private final UnsubscribeService unsubscribeService;

    public OneClickUnsubscribeController(
            UnsubscribeService unsubscribeService
    ) {
        this.unsubscribeService = unsubscribeService;
    }

    @PostMapping(
            path = "/{token}",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<Void> oneClick(
            @PathVariable String token,
            @RequestParam("List-Unsubscribe") String requestAction
    ) {
        if (!"One-Click".equals(requestAction)) {
            return ResponseEntity.badRequest().build();
        }

        unsubscribeService.unsubscribe(token);
        return ResponseEntity.noContent().build();
    }
}
~~~

Controller sử dụng **List-Unsubscribe** từ form body và token từ URL để xác định action. Ví dụ không viết exception handler; ở production nên ánh xạ **InvalidUnsubscribeTokenException** sang HTTP response phù hợp, không lộ danh tính/email hoặc thông tin DB qua lỗi.

### GET endpoint không được thay đổi dữ liệu

Nếu muốn hỗ trợ người dùng truy cập URL trong trình duyệt, có thể cung cấp:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@GetMapping("/one-click/{token}")
public ResponseEntity<String> landing(@PathVariable String token) {
    return ResponseEntity.ok(
            "Để quản lý email nhận được, vui lòng dùng trang tùy chọn."
    );
}
~~~

Ví dụ chỉ minh họa nguyên tắc **GET không gọi unsubscribe()**. Trong ứng dụng thật, không nên hiển thị token thô trong HTML, không tải third-party assets làm lộ URL qua Referer, và cần tránh log request path có token ở mức truy cập rộng. Một preference page riêng có thể cho người dùng xem và đổi lựa chọn sau khi xác thực theo yêu cầu sản phẩm.

### Không yêu cầu login/cookie cho one-click

Mailbox provider thường gửi one-click POST từ hệ thống của họ, không có session đăng nhập của người nhận. Vì vậy endpoint phải thực thi hành động dựa trên **token có phạm vi hẹp**, không yêu cầu login/cookie hoặc CAPTCHA.

Nếu ứng dụng bật Spring Security CSRF protection cho các form có session, cần cấu hình **ngoại lệ hẹp cho đúng endpoint one-click stateless** khi thích hợp, và bù bằng token ngẫu nhiên đủ mạnh, HTTPS, rate limit và chỉ cho phép thay đổi theo hướng unsubscribe. Không vô hiệu hóa CSRF toàn bộ ứng dụng chỉ để endpoint này hoạt động.

### Phản hồi HTTP và quyền riêng tư

Khi đã hủy hoặc POST trùng hợp lệ, có thể trả HTTP **204 No Content**. Với token sai/đã thu hồi, có thể dùng 400/404/410 theo chính sách; không trả một payload chứa email, tên người dùng hoặc danh sách đăng ký.

Không để người gọi đoán một địa chỉ đang subscribed hay không thông qua response chứa chi tiết tài khoản. Rate-limit brute-force theo IP và tín hiệu khác, nhưng không cấu hình giới hạn quá gắt khiến các mailbox providers dùng shared infrastructure bị chặn hàng loạt.

## 14. Hủy ở footer và hủy one-click: hai hành trình khác nhau

Một hệ thống thường cần cả hai:

| Tiêu chí | Footer link / preference page | RFC 8058 one-click |
| --- | --- | --- |
| Người thực hiện | Người nhận click link trong nội dung | Email client/provider kích hoạt POST |
| Phương thức | GET hiển thị trang, POST sau thao tác | POST trực tiếp theo format quy định |
| Có thể hiển thị lựa chọn chủ đề | Có | Không nên bắt chọn trước khi hoàn tất |
| Có cần đăng nhập | Có thể dùng xác thực phù hợp cho thay đổi phức tạp | Không yêu cầu đăng nhập để hủy |
| Token | Scoped và bảo vệ như capability | Scoped, khó đoán, hỗ trợ retry/idempotence |
| Mục đích | Khả năng tự quản lý và giải thích | Một thao tác hủy nhanh từ email client |

Một địa chỉ one-click không nên vừa mang trách nhiệm xử lý tự động vừa dùng GET để thực hiện đổi trạng thái. Có thể dùng các path riêng:

~~~text
GET  /preferences/unsubscribe/{token}   -> hiển thị tùy chọn
POST /preferences/unsubscribe/{token}   -> xử lý thao tác của người dùng

POST /one-click/{token}                 -> xử lý RFC 8058
GET  /one-click/{token}                 -> không thay đổi trạng thái
~~~

Token ở hai flow có thể cùng ánh xạ tới subscription nhưng phạm vi, thời hạn và cơ chế sử dụng cần được thiết kế rõ ràng.

## 15. Mailbox scanning và khả năng lộ token

Unsubscribe URL có thể xuất hiện trong:

- Email raw source và nhà cung cấp hộp thư.
- Proxy access logs hoặc application logs.
- Hệ thống phân tích link an ninh.
- Trình duyệt của người dùng.
- Hệ thống redirect, analytics hoặc third-party assets nếu code thiết kế không cẩn thận.

Các biện pháp nên áp dụng:

1. Chỉ dùng HTTPS trên domain tin cậy.
2. Không đặt email address, tên hoặc ID nhạy cảm ở query/path.
3. Không ghi raw token trong log; che path/token ở reverse proxy và error reporting.
4. Không dùng third-party scripts, pixels hoặc external assets ở unsubscribe landing page.
5. Áp **Referrer-Policy: no-referrer** khi hiển thị trang liên quan token.
6. Không redirect token tới domain khác.
7. Token chỉ có khả năng hủy trong một scope, không có quyền đọc dữ liệu cá nhân hoặc subscribe lại.
8. Theo dõi request bất thường nhưng không gây khó cho provider legitimate.

### URL token không phải mã xác nhận đăng nhập

Nếu token bị lộ, người khác có thể hủy một subscription; đây vẫn là một rủi ro nhưng phải được **giới hạn ở hành động hủy**. Không dùng chung token này với password reset, login, truy vấn thông tin tài khoản hoặc API thay đổi email. Phân tách các token theo mục đích giúp giảm hậu quả khi đường link bị lộ.

## 16. Kiểm tra suppression trước mỗi lần dispatch

**Điểm quyết định cuối cùng không phải lúc tạo campaign** mà là lúc hệ thống sắp nộp mail cho provider. Danh sách người nhận có thể được chuẩn bị trước nhiều giờ, trong khi người dùng hủy đăng ký chỉ vài phút trước khi job chạy.

Một thiết kế yếu:

~~~text
08:00 Tạo campaign recipients bằng truy vấn người đã đăng ký
08:05 Người dùng A unsubscribe
09:00 Worker gửi tới danh sách đã snapshot từ 08:00
      -> A vẫn nhận một email marketing khác
~~~

Một thiết kế tốt hơn:

~~~text
Tạo campaign jobs
        |
        v
Queue / outbox
        |
        v
Worker claim job
        |
        v
Tra lại suppression/preference mới nhất
        |
        +-- DENY -> SUPPRESSED, không gửi
        |
        '-- ALLOW -> compose và submit
~~~

### Một policy interface ở tầng ứng dụng

~~~java
public record MailDeliveryContext(
        String tenantId,
        String recipientId,
        String recipientEmail,
        MailPurpose purpose,
        String listId
) {
}

public enum DeliveryDecisionType {
    ALLOW,
    DENY
}

public record DeliveryDecision(
        DeliveryDecisionType type,
        String reasonCode
) {
    public boolean allowed() {
        return type == DeliveryDecisionType.ALLOW;
    }
}

public interface MailDeliveryPolicy {

    DeliveryDecision evaluate(MailDeliveryContext context);
}
~~~

Các kiểu trên là **API do ứng dụng tự thiết kế**, không có sẵn trong Spring Mail. Implementation cần kết hợp các nguồn sự thật: preference, suppression, consent, hard bounce/complaint và các quy tắc của purpose.

### Worker phải kiểm tra trước khi gọi JavaMailSender

~~~java
import org.springframework.stereotype.Service;

@Service
public class MarketingMailDispatcher {

    private final MailDeliveryPolicy deliveryPolicy;
    private final MarketingMailComposer composer;
    private final MailJobStore jobStore;

    public MarketingMailDispatcher(
            MailDeliveryPolicy deliveryPolicy,
            MarketingMailComposer composer,
            MailJobStore jobStore
    ) {
        this.deliveryPolicy = deliveryPolicy;
        this.composer = composer;
        this.jobStore = jobStore;
    }

    public void dispatch(ClaimedMailJob job) {
        MailDeliveryContext context = job.deliveryContext();
        DeliveryDecision decision =
                deliveryPolicy.evaluate(context);

        if (!decision.allowed()) {
            jobStore.markSuppressed(
                    job.id(),
                    job.leaseToken(),
                    decision.reasonCode()
            );
            return;
        }

        composer.submit(job);
        jobStore.markSubmitted(job.id(), job.leaseToken());
    }
}
~~~

**MarketingMailComposer**, **MailJobStore** và **ClaimedMailJob** là thành phần minh họa của hệ thống. Chúng phải quản lý lỗi transport, token/lease và trạng thái job theo hợp đồng riêng. Ví dụ nhấn mạnh chỗ cần kiểm tra suppression: **gần thời điểm thực hiện external side effect**, không chỉ khi event được tạo.

### Nếu không thể đọc được suppression storage thì sao?

Với email marketing, nên cân nhắc **fail closed**: nếu không biết người nhận còn đủ điều kiện nhận hay không, chưa nộp email; đưa job về trạng thái chờ hoặc lỗi tạm thời. Không nên diễn giải lỗi database timeout thành “chưa có suppression” rồi gửi tiếp.

Quy tắc tương tự phải áp dụng cho các phương thức gửi bulk, endpoint gửi thủ công, scheduled tasks và retry worker; không tồn tại một đường phụ bỏ qua policy.

## 17. Race condition khi hủy và gửi xảy ra gần như đồng thời

Ngay cả khi worker kiểm tra suppression trước mỗi lần gửi, vẫn có cửa sổ:

~~~text
Worker A                              Unsubscribe request
    |                                        |
    v                                        |
Check suppression -> ALLOW                   |
    |                                        v
    |                                  Commit UNSUBSCRIBED
    v                                        |
JavaMailSender.send(...)                     |
    |                                        |
    v                                        v
Provider accepted                        HTTP 204
~~~

Email có thể đã được bắt đầu gửi ngay trước hoặc gần thời điểm opt-out có hiệu lực. Database và SMTP không chia sẻ một transaction nguyên tử, nên không thể coi một truy vấn trước send là bảo đảm tuyệt đối rằng **không bao giờ có email nào tới sau POST unsubscribe**.

### Những biện pháp giảm rủi ro

- Kiểm tra suppression **gần sát lúc submit**.
- Hạn chế số lượng marketing jobs đang IN_FLIGHT.
- Hủy hoặc đánh dấu SUPPRESSED các job chưa được nộp sau khi opt-out.
- Đồng bộ suppression tới ESP/provider nếu họ có danh sách chặn riêng.
- Không retry các job đã bị suppression, kể cả khi attempt trước có timeout.
- Tránh pre-submit hàng nghìn email vào provider queue trước khi kiểm tra preference.
- Quy định rõ thời điểm hiệu lực và xử lý những thư đã được provider chấp nhận trước đó.

### Không giữ transaction khóa database trong lúc gọi SMTP

Một cách cố tránh race bằng cách mở database transaction, khóa recipient row rồi chờ SMTP phản hồi thường gây vấn đề: giữ lock/connection lâu, tăng contention và dễ timeout.

Có thể thiết kế synchronization hoặc hàng rào dispatch ở mức nghiệp vụ khi yêu cầu cực kỳ nghiêm ngặt, nhưng phải cân nhắc kỹ các external side effects không thể rollback. Thực tế thông thường là **chặn các job chưa gửi, kiểm tra mới nhất trước submit và thừa nhận giới hạn với thư đang truyền**.

### Phân biệt job PENDING, IN_FLIGHT và ACCEPTED

| Trạng thái job khi unsubscribe | Hướng xử lý |
| --- | --- |
| **PENDING/SCHEDULED** | Chặn hoặc đánh dấu SUPPRESSED trước send |
| **CLAIMED nhưng chưa submit** | Worker kiểm tra lại và từ chối gửi |
| **IN_FLIGHT qua transport** | Có thể không hủy được; theo dõi và ngăn retry |
| **ACCEPTED bởi provider** | Không thể thu hồi một cách tổng quát qua SMTP |
| **RETRYABLE_FAILED/UNKNOWN** | Kiểm tra suppression trước mọi retry; nếu đã opt-out, không gửi lại marketing |

Với **UNKNOWN** do timeout, ngoài nguy cơ gửi trùng còn có điều kiện opt-out mới. Một job marketing dù có thể retry về mặt kỹ thuật vẫn không được vượt qua suppression hiện tại.

## 18. Ngăn job cũ tự gửi lại sau khi người dùng hủy

Trong hệ thống có queue/outbox, email có thể trải qua nhiều lần xử lý:

~~~text
Campaign event
    |
    v
Outbox PENDING
    |
    v
Worker attempt 1 -> SMTP temporary error
    |
    v
RETRY_SCHEDULED
    |
    +------------------- Người dùng unsubscribe
    |                             |
    |                             v
    |                        Suppression active
    v
Worker attempt 2
    |
    v
Check suppression -> DENY
    |
    v
SUPPRESSED, không gửi lại
~~~

**Retry policy không được tự động vượt qua consent/suppression policy.** Các cơ chế sau đều phải gọi lại delivery policy:

- **Spring Retry** hoặc cơ chế retry của worker.
- Job scheduler sau sự cố.
- Dead-letter redrive.
- Requeue bằng thao tác quản trị.
- Retry ở integration layer với email provider.
- Gửi lại campaign cho những người “chưa được xác nhận đã nhận”.

### Tách “retry” và “resubscribe”

Retry nghĩa là cố hoàn tất một notification cũ; nó **không phải bằng chứng đồng ý nhận thư mới**. Nếu recipient đã hủy, notification marketing cũ phải dừng.

Resubscribe nghĩa là người nhận thực hiện một hành động mới để đăng ký lại theo chính sách. Không tự bật cờ subscribed chỉ vì:

- Người dùng đăng nhập lại.
- Thay đổi mật khẩu hoặc cập nhật hồ sơ.
- Mở email cũ.
- Bấm một liên kết tracking.
- Nhân viên support gửi lại campaign.

Chỉ thay đổi consent theo một luồng có quyền, mục đích và bằng chứng phù hợp.

## 19. Đồng bộ suppression với nhà cung cấp email

Khi ứng dụng sử dụng một **Email Service Provider (ESP)**, có thể tồn tại hai nơi lưu trạng thái:

1. **Ứng dụng:** bảng preference/suppression và notification jobs.
2. **Provider:** suppression list, unsubscribe events, complaints, hard bounces và nhóm người nhận.

Hai nơi có thể không đồng bộ tức thời. Nếu ứng dụng chỉ cập nhật database nhưng dùng provider để gửi campaign với danh sách đã upload từ trước, provider có thể vẫn có job đang chờ và tiếp tục phát thư. Ngược lại, nếu provider ghi nhận unsubscribe nhưng ứng dụng không nhận event, một lần gửi qua đường khác có thể bỏ qua opt-out.

### Chiến lược đồng bộ

~~~text
                    Unsubscribe event
                           |
             +-------------+-------------+
             |                           |
             v                           v
    Application suppression      Provider suppression
             |                           |
             +-------------+-------------+
                           |
                           v
                   Reconciliation
~~~

Các nguyên tắc:

- Xác định **source of truth** cho từng loại suppression.
- Nhận webhook unsubscribe/complaint/bounce nếu provider hỗ trợ.
- Ghi nhận event idempotent, không xử lý lặp tạo thay đổi không mong muốn.
- Đồng bộ opt-out tới provider khi API hỗ trợ.
- Định kỳ đối soát số lượng và các bản ghi sai khác.
- Tránh chỉ chặn ở provider nhưng để ứng dụng tiếp tục tạo và nộp vô số job bị từ chối.

### Webhook phải được xác thực

Một HTTP request tự xưng “user đã unsubscribe” không được cập nhật trạng thái nếu nguồn chưa được xác thực. Khi dùng webhook:

- Kiểm tra chữ ký hoặc cơ chế xác thực do provider quy định.
- Kiểm tra timestamp/replay window nếu provider hỗ trợ.
- Dùng unique provider event ID hoặc dedup key.
- Ánh xạ event tới tenant/list/recipient được phép.
- Không ghi đè một suppression mạnh bằng trạng thái yếu hơn.

Không có cách ký webhook chung cho mọi provider; phải làm theo tài liệu của provider đang tích hợp.

### Provider-side suppression không thay thế policy của ứng dụng

Provider có thể từ chối gửi email tới một địa chỉ đã nằm trong suppression list, nhưng business application vẫn nên đánh dấu notification **SUPPRESSED** thay vì báo gửi thành công. Lý do từ chối của provider có thể đến sau hoặc không áp dụng với một SMTP connection khác, nên chính sách trung tâm của ứng dụng vẫn cần hoạt động.

## 20. Complaint và bounce cũng là tín hiệu “không nên gửi tiếp”

Unsubscribe không phải tín hiệu duy nhất cần dẫn tới ngừng gửi marketing. Các phản hồi của provider cũng quan trọng:

| Tín hiệu | Ý nghĩa thường gặp | Hành động gợi ý |
| --- | --- | --- |
| **Explicit unsubscribe** | Recipient không muốn loại email đã chọn | Chặn đúng phạm vi ngay |
| **Spam complaint** | Recipient báo email không mong đợi | Áp suppression theo chính sách provider/sản phẩm |
| **Hard bounce** | Mailbox/domain không nhận bền vững | Ngừng retry tới địa chỉ đó, kiểm tra lại nếu địa chỉ thay đổi |
| **Soft bounce** | Lỗi tạm thời | Retry giới hạn, monitor tần suất |
| **Repeated transient failures** | Có thể là địa chỉ/host chất lượng kém | Tạm dừng hoặc review theo policy |
| **Manual do-not-contact** | Yêu cầu từ support/pháp chế/người nhận | Áp suppression theo phạm vi và audit |

Đừng coi một soft bounce đơn lẻ như unsubscribe tự nguyện: nó không có nghĩa người nhận đã rút lại consent. Ngược lại, một spam complaint không nên bị bỏ qua vì cờ user.subscription vẫn là true.

### Không tự tìm cách “vượt suppression”

Nếu provider từ chối do complaint hoặc hard bounce, không nên đổi sender domain, đổi mail service hoặc gửi tới một alias suy đoán chỉ để tiếp tục campaign. Điều đó đi ngược ý định của suppression và có thể làm giảm deliverability.

### Phân biệt lỗi kỹ thuật và yêu cầu nghiệp vụ

Trong data model, nên lưu **reason** riêng:

~~~text
UNSUBSCRIBE
GLOBAL_OPT_OUT
COMPLAINT
HARD_BOUNCE
INVALID_RECIPIENT
MANUAL_SUPPRESSION
~~~

Chính sách phục hồi khác nhau: thay địa chỉ đã bounce, re-subscribe một newsletter và gỡ suppression do complaint không nên đi chung một endpoint “subscribe=true”.

## 21. Preference center và đăng ký lại có chủ đích

One-click có mục tiêu chính: **dừng một luồng email theo scope của token**. Preference center rộng hơn: nó cho phép người nhận điều chỉnh các chủ đề hoặc tần suất nhận thư.

Ví dụ giao diện lựa chọn:

~~~text
Quản lý email từ Shop 7

[ ] Bản tin mỗi tuần
[ ] Thông báo khuyến mãi
[x] Tin cập nhật sản phẩm

[ Hủy mọi email marketing ]

Lưu lựa chọn
~~~

Trong ví dụ, các ô được chọn hoặc bỏ chọn chỉ có ý nghĩa khi đã được ánh xạ đúng tới các mục đích và danh sách. Hệ thống cần giải thích email giao dịch/bảo mật nào vẫn có thể được gửi theo chính sách, tránh gây hiểu nhầm rằng nút “Hủy mọi email marketing” làm tài khoản ngừng nhận biên nhận thanh toán.

### Không biến preference center thành công cụ gửi mail tùy ý

Thao tác sửa preference cần xác thực hoặc token có quyền hạn phù hợp; người dùng không được sửa lựa chọn của người khác chỉ bằng cách thay recipient ID trong URL. Nếu cho phép thay đổi nhiều mục đích, phải giới hạn token/ủy quyền theo phạm vi tương ứng.

### Đăng ký lại cần hành động rõ ràng

Việc người dùng yêu cầu subscribe lại có thể cần:

- Một form thể hiện rõ loại email được đăng ký.
- Hành động chấp nhận từ người dùng, kèm bằng chứng theo chính sách.
- Xác minh quyền sở hữu mailbox khi cần.
- Double opt-in nếu quy trình/nhà cung cấp/pháp luật áp dụng yêu cầu hoặc sản phẩm chọn chính sách đó.
- Bản ghi consent source, thời điểm, policy version hoặc nội dung đã được chấp nhận.

Không suy luận việc **mở email**, đăng nhập tài khoản hoặc không bấm unsubscribe là một hành động đồng ý mới.

### Không tự xóa mọi suppression khi đăng ký lại

Ví dụ:

~~~text
Marketing preference: SUBSCRIBED
Provider hard bounce: ACTIVE
Delivery decision:    DENY
~~~

Một lần subscribe lại không tự chứng minh mailbox tồn tại trở lại. Chính sách cần xác định cách phục hồi suppression do bounce/complaint theo khả năng provider và yêu cầu xác minh. Không dùng một lệnh UPDATE xóa tất cả suppression chỉ vì user bật lại checkbox.

## 22. Email thay đổi và dữ liệu nhập từ nguồn khác

Một user có thể đổi email từ **old@example.test** sang **new@example.test**. Hệ thống cần quyết định rõ:

- Subscription có gắn với **tài khoản** hay với **địa chỉ email đã xác minh**?
- Người nhận đã opt-out khỏi một danh sách có được giữ lựa chọn khi đổi địa chỉ không?
- Nếu địa chỉ cũ được gán cho người khác, các suppression và consent có còn phù hợp không?
- Nếu import danh sách marketing từ CSV/CRM, dữ liệu đó có quyền ghi đè opt-out hiện có không?

Một mô hình đơn giản và thường an toàn hơn là **không tự ghi đè opt-out bằng dữ liệu import**. Khi nhận nguồn consent mới, cần hiểu scope, người đã đồng ý, thời điểm và bằng chứng. Nếu không xác định được, không gửi marketing chỉ vì CRM có một email address.

### Đừng loại suppression khi xóa và tạo lại account

Nếu người dùng xóa tài khoản rồi tạo lại bằng cùng địa chỉ, hệ thống có thể mất cờ opt-out lưu trong bảng users cũ. Với yêu cầu không gửi tiếp, có thể cần duy trì một record suppression tối thiểu và phù hợp pháp luật để tránh vô tình re-import và gửi lại.

Phải cân bằng điều đó với quyền xóa dữ liệu và data minimization: không giữ toàn bộ hồ sơ cá nhân chỉ để chặn email. Có thể sử dụng recipient reference hoặc digest được thiết kế an toàn theo yêu cầu và chính sách retention; cần đánh giá khả năng tái nhận diện và tính phù hợp pháp lý.

### Không tự chuẩn hóa mailbox quá mức

Ví dụ không nên xóa dấu chấm hoặc plus-tag trên mọi email theo một quy tắc chung. Cách xử lý alias phụ thuộc nhà cung cấp mailbox và không phải chuẩn chung cho tất cả domain. Nếu suppression theo email address, cần một canonicalization policy nhất quán, được xác định theo nguồn tin cậy, đồng thời tránh gộp nhầm hai mailbox khác nhau.

## 23. Kiểm thử one-click và suppression

Một bộ test cần xác minh **giao thức**, **thay đổi trạng thái**, **ủy quyền theo scope** và **đường đi trước khi gửi**, không chỉ kiểm tra controller trả 204.

### Test POST one-click có body hợp lệ

Ví dụ dùng Spring MockMvc với standalone controller và mock service:

~~~java
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class OneClickUnsubscribeControllerTest {

    @Test
    void postOneClickDelegatesToService() throws Exception {
        UnsubscribeService service = mock(UnsubscribeService.class);
        MockMvc mvc = MockMvcBuilders.standaloneSetup(
                new OneClickUnsubscribeController(service)
        ).build();

        String token = "A".repeat(43);

        mvc.perform(post("/one-click/{token}", token)
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED
                        )
                        .param("List-Unsubscribe", "One-Click"))
                .andExpect(status().isNoContent());

        verify(service).unsubscribe(token);
    }

    @Test
    void rejectsWrongAction() throws Exception {
        UnsubscribeService service = mock(UnsubscribeService.class);
        MockMvc mvc = MockMvcBuilders.standaloneSetup(
                new OneClickUnsubscribeController(service)
        ).build();

        mvc.perform(post("/one-click/{token}", "A".repeat(43))
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED
                        )
                        .param("List-Unsubscribe", "Other-Action"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }
}
~~~

Test trên chỉ kiểm tra hợp đồng controller khi service là mock. Nó **không chứng minh** Spring Security cho phép POST không session trong môi trường thật hoặc DB update đã commit. Cần test integration cho security chain, token repository và suppression storage.

### Test GET không làm thay đổi preference

Một test cần gửi GET tới URL one-click và xác nhận:

~~~text
Given: recipient vẫn subscribed
When: GET /one-click/token
Then: không ghi UNSUBSCRIBED
And: không tạo suppression event
~~~

Trường hợp này mô phỏng link scanner. Đừng chỉ kiểm tra status 200; phải xác nhận state trong storage không đổi.

### Test POST lặp lại

~~~text
Given: token hợp lệ cho newsletter A
When: POST lần 1, sau đó POST lại cùng token
Then: newsletter A vẫn UNSUBSCRIBED
And: không có thao tác nào bật subscribed lại
And: không tạo hai notification email xác nhận hủy
~~~

Nếu repository lưu timestamp hủy lần đầu, test cần xác nhận lần POST thứ hai không làm mất audit của lần đầu.

### Test đúng phạm vi token

~~~text
Given: token của recipient R / tenant T / list A
When: POST one-click
Then: list A của R trong T bị hủy
And: list B không bị thay đổi
And: recipient S không bị thay đổi
And: tenant U không bị thay đổi
~~~

Đây là test quan trọng khi hệ thống đa tenant hoặc dùng nhiều marketing list. Không để token nhận được quyền truy vấn/sửa mọi preference của recipient.

### Test job được tạo trước unsubscribe

~~~text
T1: tạo PENDING newsletter job cho R
T2: R unsubscribe
T3: dispatcher claim job
Expected: dispatcher mark SUPPRESSED, JavaMailSender không được gọi
~~~

Đây là kiểm thử end-to-end của quy tắc **đừng gửi tiếp**. Việc endpoint cập nhật subscribed=false trong database vẫn chưa đủ nếu mail dispatcher dùng danh sách người nhận cũ.

### Test retry sau unsubscribe

~~~text
T1: attempt gửi marketing gặp lỗi tạm thời
T2: user unsubscribe
T3: retry worker chạy
Expected: không retry SMTP; job chuyển SUPPRESSED
~~~

Với retry, không nên chỉ test maximum attempts/backoff. Phải test việc thay đổi preference trong lúc job chờ.

### Test nhiều request đồng thời

Cho hai POST cùng token chạy gần như cùng lúc. Kết quả cần là một trạng thái UNSUBSCRIBED nhất quán. Nếu hệ thống ghi audit event duy nhất cho lần hủy đầu, dùng constraint/upsert thích hợp để tránh ghi trùng ngoài ý định.

### Test DKIM/header thực tế

Một test tại tầng composer có thể xác nhận:

~~~java
MimeMessage message = composer.compose(
        recipient,
        subject,
        html,
        oneClickUrl
);

assertNotNull(message.getHeader("List-Unsubscribe"));
assertNotNull(message.getHeader("List-Unsubscribe-Post"));
~~~

Nhưng muốn xác nhận **DKIM signature** và cách email client hiển thị nút unsubscribe, cần quan sát bản thư thật phía nhận hoặc provider test environment. Unit test header không chứng minh provider đã ký đúng các header theo RFC 8058.

### Test với token trong log

Khi endpoint bị gọi với token sai và ném exception, kiểm tra application logging và reverse proxy access logs có vô tình in toàn bộ URL path không. Mục tiêu là tránh raw token xuất hiện ở hệ thống log có quyền xem rộng, không phải chỉ tránh logging trong Java method.

## 24. Metrics, alert và đánh giá hiệu quả

Các metric hữu ích cho vận hành unsubscribe:

| Metric minh họa | Ý nghĩa |
| --- | --- |
| **mail_unsubscribe_requests_total{source,result}** | Yêu cầu từ one-click/footer/provider webhook và kết quả |
| **mail_unsubscribe_processing_duration_seconds** | Thời gian cập nhật preference/suppression |
| **mail_suppressed_jobs_total{reason}** | Số notification bị chặn trước send |
| **mail_eligible_recipients_total{purpose}** | Số recipient đủ điều kiện theo purpose |
| **mail_complaints_total{provider}** | Số spam complaint |
| **mail_hard_bounces_total{provider}** | Số hard bounce |
| **mail_delivery_policy_failures_total** | Lỗi khi quyết định có cho gửi không |
| **mail_provider_suppression_sync_failures_total** | Lỗi đồng bộ suppression lên provider |

Đây là **metric ứng dụng tự định nghĩa**, không phải tên mặc định của Spring Mail. Không đưa recipient email, raw token hoặc notification ID thành metric label vì vừa tăng cardinality vừa có rủi ro quyền riêng tư.

### Những alert cần cân nhắc

- Tỷ lệ HTTP 5xx của one-click tăng bất thường.
- Subscription được cập nhật nhưng mail dispatcher vẫn gửi marketing cho scope bị hủy.
- Provider webhook unsubscribe/complaint bị lỗi xác thực hoặc ngừng đến.
- Có chênh lệch lớn giữa suppression của ứng dụng và provider.
- Số email marketing bị báo spam tăng.
- Tỷ lệ retry marketing sau opt-out lớn hơn mức chấp nhận được.

Mục tiêu không phải giảm số lượt unsubscribe bằng cách làm nút hủy khó tìm. Số unsubscribe cao có thể chỉ ra nội dung, tần suất hoặc targeting chưa phù hợp. Tăng cường quyền lựa chọn của người nhận thường tốt hơn việc che hoặc trì hoãn opt-out.

## 25. Xử lý yêu cầu unsubscribe qua mailto hoặc hỗ trợ khách hàng

Không phải mọi người nhận đều có email client hỗ trợ one-click hoặc muốn dùng đường link. Yêu cầu **“Xin đừng gửi thư quảng bá nữa”** có thể đến qua:

- Một email trả lời địa chỉ hỗ trợ.
- Header List-Unsubscribe có **mailto:**.
- Ticket hỗ trợ khách hàng.
- Form privacy hoặc yêu cầu không liên hệ.
- Provider feedback loop.

Nếu hệ thống quảng bá mailto trong header, phải có một bộ xử lý tương ứng:

~~~text
mailto:leave-newsletter@example.test
               |
               v
         Mailbox receiver
               |
               v
    Parse và liên kết yêu cầu
               |
               v
      Xác định recipient/list
               |
               v
      Apply suppression
               |
               v
      Ghi audit kết quả
~~~

### Không tin hoàn toàn From của email gửi tới mailbox hủy

Header From trong một thư đến có thể bị giả mạo hoặc forward. Một email đến địa chỉ unsubscribe không tự chứng minh người viết kiểm soát mailbox được nêu trong header. Cần một cơ chế liên kết yêu cầu và scope phù hợp:

- Địa chỉ **mailto:** hoặc subject có thể chứa mã opaque do server tạo.
- Hệ thống có thể dùng identifier đã liên kết với notification.
- Yêu cầu đến từ support có thể cần xác minh người yêu cầu theo chính sách.
- Trường hợp không xác minh được có thể cần xử lý thủ công hoặc quy trình giảm rủi ro spam.

Không tạo một endpoint mailto mà bất kỳ người nào cũng gửi tên user khác rồi tùy ý thay đổi mọi preference. Tuy nhiên, cũng không nên đặt gánh nặng xác minh quá mức khiến người nhận không thể thực hiện quyền opt-out.

### Không dùng auto-reply để ép người nhận đăng ký lại

Nếu một yêu cầu unsubscribe đã được xử lý, không gửi thêm newsletter dưới dạng “Xác nhận bạn vẫn muốn nhận thư” nhằm lách lựa chọn đã hủy. Nếu có xác nhận vận hành, nó phải phù hợp chính sách, không chứa nội dung quảng bá và không tạo chuỗi email lặp vô hạn.

## 26. Khía cạnh pháp lý và chính sách gửi

Quyền hủy đăng ký và yêu cầu ngừng liên lạc có thể chịu tác động của:

- Pháp luật chống spam và thương mại điện tử tại quốc gia liên quan.
- Quy định về quyền riêng tư và cơ sở xử lý dữ liệu.
- Hợp đồng với email provider.
- Chính sách nội bộ về marketing, transactional notifications và data retention.
- Lựa chọn mà người nhận đã được trình bày khi đăng ký.

Không thể áp một mốc xử lý hoặc một cách phân loại email duy nhất cho mọi thị trường. Ví dụ, cách quản lý email quảng bá và email xác thực bảo mật có thể khác nhau; một thông điệp chứa cả quảng bá và giao dịch có thể bị đánh giá theo nội dung thực tế.

### Các câu hỏi nên được xác định trong yêu cầu sản phẩm

1. Loại email nào yêu cầu opt-in trước khi gửi?
2. Người nhận có quyền hủy ở mức list, brand hay toàn bộ marketing?
3. Mốc thời gian nào phải áp dụng cho yêu cầu hủy theo thị trường/provider?
4. Cơ chế one-click có phải yêu cầu đối với nhóm lưu lượng đang sử dụng?
5. Có cần giữ bằng chứng consent và withdrawal không; giữ bao lâu?
6. Khi người dùng đổi email hoặc xóa tài khoản, lưu suppression tối thiểu thế nào?
7. Ai có quyền xử lý manual override và theo quy trình nào?
8. Những thông báo dịch vụ/bảo mật nào vẫn được phép hoặc cần gửi?

Những điều trên cần được kiểm tra theo chính sách hiện hành; đây là bài học kỹ thuật, **không thay thế tư vấn pháp lý**.

### Tôn trọng lựa chọn phải xảy ra trong hệ thống, không chỉ trên giấy

Ghi trong email “bạn có thể hủy bất kỳ lúc nào” nhưng endpoint hủy lỗi, job queue không kiểm tra lại suppression hoặc provider vẫn tiếp tục gửi campaign sẽ làm chính sách không có giá trị trong thực tế.

Một yêu cầu “không gửi tiếp” phải xuất hiện ở **quyết định được phép gửi** tại mail dispatcher, không chỉ ở biểu mẫu preference.

## 27. Những sai lầm thường gặp

### Sai lầm 1 — Có link unsubscribe nhưng không lưu trạng thái

Footer mở một trang “Cảm ơn” nhưng không thay đổi subscription.

**Cách xử lý:** áp suppression idempotent và xác nhận database đã commit.

### Sai lầm 2 — GET link đã tự hủy

Link scanner truy cập URL có thể kích hoạt unsubscribe không mong muốn.

**Cách xử lý:** GET chỉ hiển thị; POST mới xử lý. One-click dùng đúng POST theo RFC 8058.

### Sai lầm 3 — One-click yêu cầu đăng nhập hoặc CAPTCHA

Mailbox provider không có phiên đăng nhập của người nhận để hoàn tất tự động.

**Cách xử lý:** token có phạm vi hẹp, HTTPS và POST trực tiếp không yêu cầu bước xác nhận thêm.

### Sai lầm 4 — Thêm List-Unsubscribe nhưng không có handler

Email client hiển thị nút hủy nhưng request trả 404/500.

**Cách xử lý:** triển khai endpoint/mailbox processor, quan sát lỗi và kiểm tra từ môi trường nhận thư thật.

### Sai lầm 5 — Chỉ kiểm tra subscribed khi enqueue

Job đã xếp hàng nhiều giờ vẫn gửi sau khi người dùng hủy.

**Cách xử lý:** kiểm tra lại suppression tại dispatch và trước retry.

### Sai lầm 6 — Hủy một list nhưng gửi lại bằng campaign khác thuộc cùng scope

Hệ thống định nghĩa nhầm scope hoặc không áp global opt-out.

**Cách xử lý:** định nghĩa precedence rõ ràng và dùng chung MailDeliveryPolicy cho mọi đường gửi.

### Sai lầm 7 — Hủy rồi POST lần hai lại đăng ký

Endpoint dùng logic toggle boolean.

**Cách xử lý:** action chỉ là unsubscribe, thực thi idempotent.

### Sai lầm 8 — Token là email hoặc user ID dễ đoán

Người khác có thể đoán URL hủy đăng ký của recipient khác.

**Cách xử lý:** opaque random token có entropy cao, gắn scope và chỉ có quyền hủy.

### Sai lầm 9 — Đăng ký lại xóa cả complaint và hard bounce

Một lệnh UPDATE toàn cục xóa mọi suppression.

**Cách xử lý:** quản lý reason và cách phục hồi độc lập cho từng suppression type.

### Sai lầm 10 — Coi hard bounce là người dùng tự hủy

Nguyên nhân kỹ thuật và ý định người nhận bị trộn lẫn.

**Cách xử lý:** lưu reason rõ; policy có thể chặn cả hai nhưng audit/khôi phục khác nhau.

### Sai lầm 11 — Provider đã biết opt-out nhưng ứng dụng chưa biết

Ứng dụng tiếp tục tạo/gửi qua một transport khác, bỏ qua trạng thái provider.

**Cách xử lý:** xác thực webhook, đồng bộ và reconciliation suppression.

### Sai lầm 12 — URL token bị ghi vào log truy cập

Raw token nằm ở proxy/error monitoring, có thể bị sử dụng ngoài ý muốn.

**Cách xử lý:** token chỉ-unsubscribe, che log, không dùng external assets ở landing page.

### Sai lầm 13 — Gửi marketing như security notification

Ứng dụng gắn cờ transactional/security để vượt qua unsubscribe marketing.

**Cách xử lý:** phân loại theo mục đích thật, tách nội dung quảng bá khỏi thông điệp thiết yếu.

### Sai lầm 14 — Hard-code chính sách thời hạn dựa trên một provider

Một mốc xử lý có thể không phù hợp với quy định khác hoặc cập nhật mới.

**Cách xử lý:** xác nhận yêu cầu pháp lý/provider tại thị trường và thời điểm thực tế, lưu policy trong cấu hình/đặc tả vận hành.

### Sai lầm 15 — Chỉ dựa vào SMTP success

JavaMailSender.send(...) không ném lỗi, nhưng người nhận vẫn complaint hoặc unsubscribe.

**Cách xử lý:** theo dõi provider events, delivery outcomes, complaint và preference; không coi SMTP accept là sự đồng ý tiếp tục nhận.

## 28. Tình huống luyện tập

### Tình huống A — Người dùng hủy newsletter, sau đó đặt hàng

Người dùng đã opt-out newsletter nhưng thực hiện giao dịch mới.

**Hỏi:** có được gửi biên nhận đơn hàng không?

**Đáp:** cần áp chính sách theo mục đích. Một opt-out chỉ cho newsletter thường không có cùng ý nghĩa với việc ngừng mọi thông điệp giao dịch; biên nhận phải được xử lý theo service policy và quy định áp dụng, đồng thời không lồng quảng bá để lách opt-out.

### Tình huống B — One-click URL được link scanner GET

Server thấy GET đến URL one-click trước khi người dùng mở thư.

**Hỏi:** có nên đổi trạng thái subscription?

**Đáp:** không. GET không gây side effect; one-click chuẩn xử lý POST với trường List-Unsubscribe.

### Tình huống C — Provider gửi POST hai lần

Lần đầu thành công nhưng mất HTTP response; provider retry.

**Hỏi:** lần hai có được đổi lại SUBSCRIBED?

**Đáp:** không. Handler unsubscribe phải idempotent và giữ trạng thái đã hủy.

### Tình huống D — Người nhận có ba newsletters

Token trong email newsletter A được dùng để hủy.

**Hỏi:** có tự hủy cả B và C không?

**Đáp:** chỉ khi scope của lựa chọn đã được định nghĩa rõ là hủy toàn bộ marketing. Nếu token đại diện list A, chỉ hủy A; không đoán scope từ địa chỉ email.

### Tình huống E — Token unsubscribe có email trong URL

URL chứa query parameter email đầy đủ và list ID.

**Hỏi:** rủi ro?

**Đáp:** lộ dữ liệu trong logs/truy vết, dễ bị đoán hoặc thay đổi thông tin. Dùng opaque token liên kết server-side với recipient/list.

### Tình huống F — Job đã enqueue lúc người dùng còn subscribed

Đến giờ gửi, recipient đã unsubscribed.

**Hỏi:** gửi hay không?

**Đáp:** không gửi marketing; dispatcher phải kiểm tra lại suppression và đánh dấu SUPPRESSED thay vì dùng snapshot eligibility cũ.

### Tình huống G — Mail đang IN_FLIGHT khi người dùng opt-out

Worker đã bắt đầu SMTP transaction trước khi unsubscribe được commit.

**Hỏi:** có bảo đảm email không tới không?

**Đáp:** không thể thu hồi chắc chắn một submission đã được provider chấp nhận. Hạn chế cửa sổ race, chặn các job chưa submit và không retry sau opt-out.

### Tình huống H — Provider báo spam complaint

Preference database vẫn subscribed=true.

**Hỏi:** có nên tiếp tục newsletter?

**Đáp:** không chỉ dựa vào preference. Complaint suppression có thể yêu cầu chặn gửi theo policy/provider; cần đồng bộ tín hiệu về ứng dụng.

### Tình huống I — Marketing operator import lại CSV cũ

CSV ghi user vẫn đồng ý nhận, nhưng họ đã unsubscribe trong tuần vừa rồi.

**Hỏi:** dữ liệu CSV có được bật lại subscription không?

**Đáp:** không tự động. Cần xác định bằng chứng consent mới hợp lệ; opt-out gần nhất không được ghi đè bằng snapshot cũ một cách im lặng.

### Tình huống J — Địa chỉ gửi bị đổi sang brand khác

Một campaign thay From để tiếp tục gửi tới địa chỉ đã opt-out.

**Hỏi:** có phù hợp không?

**Đáp:** không nếu đây là cách lách phạm vi suppression mà người nhận đã yêu cầu. Policy phải theo brand/tenant/purpose thực tế, không chỉ theo string From.

### Tình huống K — Người dùng muốn đăng ký lại sau khi hủy

**Hỏi:** có thể dùng lại one-click token cũ để subscribe không?

**Đáp:** không. Token chỉ cho phép unsubscribe. Resubscribe cần một thao tác riêng có quyền và bằng chứng phù hợp.

### Tình huống L — Email client không hiển thị nút Unsubscribe

Raw message có List-Unsubscribe.

**Hỏi:** có chắc message sai không?

**Đáp:** chưa. Cần xem khả năng của client/provider, DKIM signature, List-Unsubscribe-Post, loại email và sender requirements. Header có mặt không bảo đảm client sẽ hiển thị nút.

### Tình huống M — Một provider có suppression, provider khác không

Hệ thống failover SMTP sau sự cố.

**Hỏi:** làm thế nào không gửi lại cho người đã hủy?

**Đáp:** dùng suppression ở ứng dụng làm hàng rào chung và đồng bộ theo provider; không phụ thuộc hoàn toàn một danh sách chặn của một vendor.

### Tình huống N — Người nhận yêu cầu “đừng gửi email nữa” qua support

**Hỏi:** có được chỉ đánh dấu unsubscribe newsletter A không?

**Đáp:** cần xác minh phạm vi yêu cầu và chính sách; nếu ý định là dừng mọi marketing, phải áp scope phù hợp thay vì chỉ một list. Audit nguồn và lý do xử lý.

### Tình huống O — Không đọc được database suppression khi worker gửi

**Hỏi:** có nên mặc định ALLOW để không mất chiến dịch?

**Đáp:** với marketing, nên ưu tiên fail closed và dừng/hoãn dispatch khi không biết eligibility. Gửi tiếp khi mất kiểm soát opt-out có thể gây hại nghiêm trọng hơn việc gửi chậm.

## 29. Quy trình triển khai từ đầu đến cuối

~~~text
XÁC ĐỊNH CHÍNH SÁCH
    |
    +-- Loại email: marketing / product / service / security
    +-- Phạm vi: tenant / brand / list / purpose
    +-- Consent, do-not-contact và suppression precedence
    |
    v
THIẾT KẾ DỮ LIỆU
    |
    +-- Subscription/preference record
    +-- Suppression record + reason
    +-- Token hash -> recipient/list/scope
    +-- Audit trail
    |
    v
TẠO EMAIL
    |
    +-- Kiểm tra recipient có đủ điều kiện
    +-- Render footer unsubscribe
    +-- Thêm List-Unsubscribe
    +-- Thêm List-Unsubscribe-Post
    +-- Provider outbound ký DKIM phù hợp
    |
    v
XỬ LÝ OPT-OUT
    |
    +-- HTTPS one-click POST
    +-- GET không thay đổi trạng thái
    +-- Xác thực opaque token/scope
    +-- Commit UNSUBSCRIBED idempotent
    |
    v
THỰC THI SUPPRESSION
    |
    +-- Dispatcher kiểm tra lại ngay trước gửi
    +-- Retry/dead-letter redrive cũng kiểm tra
    +-- Chặn job PENDING đã hết điều kiện
    |
    v
ĐỒNG BỘ VÀ VẬN HÀNH
    |
    +-- Provider webhook + suppression sync
    +-- Complaint/bounce handling
    +-- Metrics, alert, reconciliation
    |
    v
KIỂM THỬ
    |
    +-- RFC 8058 POST/form body
    +-- GET link scanner
    +-- Idempotent replay
    +-- Cross-tenant/list isolation
    +-- Queued and retried jobs after opt-out
    +-- DKIM/header ở message thực tế
~~~

### Một checklist triển khai thực tế

- **Policy:** có định nghĩa rõ marketing, transactional và security notification chưa?
- **Scope:** token và trạng thái subscription gắn đúng tenant, list và recipient chưa?
- **Consent:** có nguồn dữ liệu/ủy quyền phù hợp để cho phép gửi marketing không?
- **Header:** List-Unsubscribe và List-Unsubscribe-Post có đúng cú pháp, URL HTTPS và được ký DKIM thích hợp không?
- **Endpoint:** POST form xử lý trực tiếp, GET không thay đổi trạng thái, không bắt login/CAPTCHA không?
- **Token:** token khó đoán, có hash lookup, không lộ PII hoặc quyền ngoài unsubscribe không?
- **Database:** unsubscribe idempotent và update có ranh giới transaction rõ không?
- **Dispatcher:** mọi đường gửi marketing đều kiểm tra suppression mới nhất trước submit không?
- **Retry:** job đang chờ/retry có bị chặn sau opt-out không?
- **Provider:** unsubscribe, complaint và bounce có được đồng bộ/đối soát không?
- **Privacy:** có giới hạn logging URL token và quyền truy cập audit không?
- **Tests:** đã mô phỏng provider POST, link scanner GET, replay, race và queued email chưa?
- **Operations:** có alert khi endpoint lỗi hoặc suppression bị bỏ qua không?

## 30. Tóm tắt nguyên tắc cốt lõi

~~~text
Unsubscribe link chỉ là giao diện,
suppression ở lúc gửi mới là cơ chế thực thi.

GET unsubscribe URL -> không đổi trạng thái
RFC 8058 one-click POST -> hủy đúng scope, idempotent

Một token khó đoán -> một khả năng hủy có giới hạn
Không dùng token để truy vấn dữ liệu hay subscribe lại

Không tin snapshot người nhận từ lúc enqueue
Mọi attempt marketing phải kiểm tra suppression hiện tại

Newsletter opt-out != tự động chặn mọi email bảo mật
Subscribed=true != được gửi khi global suppression đang active

Provider suppression != thay thế hoàn toàn application policy
SMTP accepted != người nhận mong muốn nhận tiếp
~~~

**Hủy đăng ký và yêu cầu không gửi tiếp** là một vòng đời nghiệp vụ trải từ consent/preference tới soạn MIME, nhận HTTP POST, cập nhật database, chặn job và đồng bộ email provider. Với Spring Framework Mail, **JavaMailSender** có thể thêm các header **List-Unsubscribe** và **List-Unsubscribe-Post**, nhưng **không tự thực hiện suppression**. Cần triển khai endpoint one-click đúng giao thức, token có phạm vi chặt, cập nhật idempotent và kiểm tra eligibility ngay trước mỗi lần gửi — kể cả khi job đã được enqueue từ trước hoặc đang retry. Khi người nhận có thể dừng email nhanh chóng và quyết định đó được thực thi thực sự trên mọi đường gửi, hệ thống vừa tôn trọng lựa chọn của họ vừa xây dựng nền tảng deliverability bền vững hơn.
