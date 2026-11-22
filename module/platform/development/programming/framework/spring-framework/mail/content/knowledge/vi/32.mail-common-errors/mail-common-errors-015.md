# Không kiểm tra message ở mail client thật

Một ứng dụng Spring Framework Mail có thể gọi `JavaMailSender.send(...)` thành công, SMTP server trả mã chấp nhận, unit test kiểm tra `MimeMessage` hoàn toàn đúng, nhưng người nhận mở thư bằng Outlook, Gmail hoặc một ứng dụng mail trên điện thoại lại thấy **bố cục vỡ, ảnh không hiện, chữ quá nhỏ, nút bấm khó dùng, bảng bị tràn hoặc nội dung quan trọng bị cắt**. Đây là lỗi phổ biến khi đội phát triển chỉ kiểm tra mã HTML hoặc preview trong trình duyệt, mà **không kiểm tra message trên mail client thực tế**.

Email HTML không vận hành giống một trang web thông thường. Mỗi mail client có cơ chế xử lý HTML, CSS, ảnh, font, dark mode, link, attachment và bảo mật riêng. Cùng một MIME message có thể được hiển thị khác nhau giữa các phiên bản Outlook trên Windows, Gmail web, Gmail mobile, Apple Mail trên iOS/macOS hoặc webmail của một tổ chức. Ngay trong cùng một ứng dụng, các tùy chọn **dark mode, chặn ảnh, cỡ chữ hệ thống, cửa sổ đọc hẹp và nội dung được chuyển tiếp** cũng có thể thay đổi kết quả.

Bài học thuộc chương **Lỗi thường gặp** của module **Spring Framework Mail**, tập trung vào nguyên nhân, cách nhận biết và quy trình phòng tránh lỗi **“Không kiểm tra message ở mail client thật”**. Chúng ta sẽ phân biệt kiểm thử SMTP/MIME với kiểm thử hiển thị, xây một ma trận mail client, thiết kế message có khả năng tương thích, kiểm tra text/plain và HTML, CID/attachment, nội dung đa ngôn ngữ, dark mode, accessibility, liên kết, tracking và bảo mật. Các ví dụ dùng `JavaMailSender` và `MimeMessageHelper`, cùng phương pháp kiểm tra trên hộp thư thử nghiệm thực thay vì gửi tới khách hàng production.

**Nguyên tắc xuyên suốt:** *SMTP đã nhận email* không đồng nghĩa *người dùng có thể đọc, hiểu và thao tác đúng trên email*. Muốn biết trải nghiệm cuối, phải quan sát thông điệp bằng những mail client đại diện cho người nhận.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích tại sao test HTML bằng browser không đủ để xác nhận email hoạt động.
2. Phân biệt **unit test**, **SMTP capture test**, **MIME structure test** và **mail client rendering test**.
3. Nhận biết các khác biệt phổ biến giữa client web, desktop, mobile và các chế độ hiển thị.
4. Thiết kế `multipart/alternative`, `multipart/related` và `multipart/mixed` phù hợp trong Spring Mail.
5. Kiểm tra plain text fallback, charset UTF-8, subject, header, inline image và attachment.
6. Dùng HTML/CSS theo hướng **progressive enhancement**, tối ưu khả năng đọc khi style hoặc ảnh bị chặn.
7. Lập ma trận thử nghiệm có ưu tiên theo người dùng thực, template, client, thiết bị và network.
8. Tổ chức việc gửi tới **test mailbox** có allowlist, không dùng dữ liệu thật hoặc làm phiền người nhận.
9. Thu thập screenshot, raw MIME và thông tin môi trường đủ để tái hiện lỗi.
10. Xử lý regression và phân biệt lỗi build MIME, lỗi delivery, lỗi rendering và lỗi thao tác.

## 2. Vì sao email không giống trang web?

Khi mở một website, trình duyệt nhận HTML/CSS/JavaScript và thực thi trong môi trường browser có thể tương đối chủ động. Mail client nhận một **MIME email** từ hệ thống thư, rồi áp dụng các quy tắc bảo mật và trình bày của nó.

```text
Ứng dụng Spring
      |
      v
MimeMessage
  - MIME headers
  - text/plain
  - text/html
  - inline image parts
  - attachment parts
      |
      v
SMTP provider / Receiving MTA
      |
      v
Receiving mail service
  - scanning
  - content filtering
  - link/image proxying (tùy hệ thống)
      |
      v
Mail client rendering engine
      |
      +-- Gmail web
      +-- Outlook desktop/web
      +-- Apple Mail desktop/mobile
      +-- Client Android/iOS khác
      |
      v
Người dùng nhìn và tương tác với email
```

Mail client có thể:

- Loại bỏ hoặc thay đổi các thẻ HTML/CSS không cho phép.
- Không hỗ trợ hoặc hỗ trợ một phần các thuộc tính CSS.
- Chặn ảnh từ xa cho đến khi người dùng đồng ý.
- Rewrite hoặc proxy URL.
- Thay đổi màu khi bật dark mode.
- Thay font theo hệ điều hành.
- Diễn giải `multipart/alternative` khác nhau nếu cấu trúc MIME sai.
- Hiển thị attachment/inline image khác với browser.
- Trích lại nội dung theo cách riêng khi Reply hoặc Forward.
- Tăng cỡ chữ hoặc thay layout theo accessibility settings.

Không nên áp một danh sách cứng “client X luôn hỗ trợ CSS Y” cho mọi phiên bản, vì sản phẩm có thể thay engine và chính sách theo thời gian. Cách kiểm tra đáng tin là **kết hợp nguyên tắc tương thích với thử nghiệm trên phiên bản client mục tiêu**.

## 3. Bốn tầng kiểm tra độc lập

| Tầng | Công cụ thường dùng | Kiểm tra được | Không chứng minh được |
| --- | --- | --- | --- |
| Unit test | JUnit, Mockito | Mapping dữ liệu, escape, routing, composer logic | Client thật sẽ render đúng |
| SMTP capture | GreenMail, Mailpit/MailHog hoặc server test | Message được submit, một số MIME headers/parts | Gmail/Outlook/Apple Mail hiển thị đúng |
| MIME inspection | Jakarta Mail parser, raw .eml | Part tree, content types, charset, CID, filenames | Dark mode/responsive layout tương thích |
| Real mail client | Hộp thư test và ứng dụng thật | Bố cục, thao tác, hình ảnh, đọc được, link | Kết quả giống mọi người dùng hoặc mọi phiên bản |

Các tầng bổ trợ nhau. Nếu một email sai `Content-Type`, MIME test sẽ phát hiện sớm hơn manual client test. Nếu MIME đúng nhưng nút CTA quá nhỏ trong Outlook desktop, cần thử trên client thật mới thấy.

### Một ví dụ dễ nhầm

```text
JUnit:        PASS
SMTP test:    PASS
HTML preview: PASS
Gmail mobile: CTA vượt mép màn hình
Outlook:      Bảng giá mất cột
Apple Mail:   Logo chìm trong dark mode
```

Ba kết quả PASS đầu tiên không bị “sai”; chúng chỉ xác minh **những thuộc tính khác**. Vấn đề là bỏ qua tầng hiển thị.

## 4. “Đã gửi thành công” nghĩa là gì?

`JavaMailSender.send(...)` không ném exception thường chỉ cho biết quá trình **SMTP submission** hoàn tất theo bằng chứng của transport. Sau đó provider hoặc remote server có thể chấp nhận, trì hoãn, bounce hoặc áp dụng filtering.

```text
Application composed message
          |
          v
SMTP SUBMITTED
          |
          v
REMOTE DELIVERED (nếu có feedback)
          |
          v
Mailbox placement
          |
          v
Mail client renders
          |
          v
Recipient can understand and act
```

Một lỗi **hiển thị trên client** không tự đồng nghĩa lỗi **SMTP submission**. Ngược lại, nếu email không xuất hiện trong mailbox test, cần điều tra delivery trước khi sửa CSS.

## 5. Dấu hiệu điển hình của việc chưa test trên client thật

Những phản hồi thường gặp từ người dùng:

- “Email có HTML tag hiện nguyên văn.”
- “Trong Outlook nút xác nhận biến thành chữ xanh không có nền.”
- “Bảng tổng tiền bị tràn khỏi màn hình điện thoại.”
- “Màu chữ trắng trên nền trắng khi bật dark mode.”
- “Logo không thấy nếu tắt tải ảnh.”
- “Attachment mở được trong một app nhưng hiện sai tên ở app khác.”
- “Tiếng Việt trong subject hoặc nội dung bị lỗi dấu.”
- “Link trong email bị xuống dòng khó bấm.”
- “Chỉ nhìn thấy ảnh, không thấy nội dung thông báo.”
- “Khi Forward email, layout mất hết hoặc tài liệu bị đính kèm lạ.”
- “Email hiển thị bản plain text dù đã gửi HTML.”
- “Mã OTP quá nhỏ để đọc trên thiết bị có tăng kích cỡ chữ.”

Một số sự cố do MIME/composer, số khác do client rendering engine, content filtering, template hoặc network. **Phải phân loại trước khi sửa.**

## 6. Một mẫu mail có thể đi qua nhiều client

Một người dùng có thể đọc cùng email trên nhiều thiết bị:

```text
Recipient mailbox
      |
      +-- Webmail trên laptop
      |
      +-- App trên Android/iOS
      |
      +-- Desktop client qua IMAP/Exchange
      |
      +-- Forward sang một tổ chức khác
```

Vì thế “test một lần bằng trình duyệt Chrome” là không đủ. Việc test nên dựa vào **tỷ lệ người nhận sử dụng client**, loại thông báo và tính quan trọng của nội dung, thay vì cố test mọi client từng tồn tại.

## 7. Browser preview không đại diện cho mail client

Khi render HTML ở một trang preview:

```html
<html>
  <head>
    <style>
      .cta {
        display: flex;
        gap: 16px;
        background: #2463eb;
      }
    </style>
  </head>
  <body>
    <div class="cta">Xác nhận đơn hàng</div>
  </body>
</html>
```

Browser có thể hỗ trợ `display:flex` và `gap` đầy đủ, nhưng một số mail client có thể loại bỏ style hoặc không có cùng mức hỗ trợ. Vì vậy preview đẹp không đảm bảo email được đọc đúng.

Với email transactional quan trọng, hãy ưu tiên:

- Nội dung theo thứ tự đọc hợp lý ngay trong HTML.
- Bố cục đơn giản, có fallback.
- Style inline hoặc kỹ thuật được xác minh cho client mục tiêu.
- Bảng trình bày khi cần tương thích client HTML hạn chế.
- Text/link vẫn hiểu được nếu nút mất style.
- Kích cỡ chữ và khoảng cách có thể sử dụng trên mobile.
- Plain text alternative để người dùng/client có lựa chọn đọc khác.

## 8. Khác biệt giữa các họ mail client

| Họ client | Điều thường cần kiểm tra | Không nên giả định |
| --- | --- | --- |
| Gmail web | Sanitized HTML/CSS, ảnh, clipping, mobile viewport | Giống browser tab bình thường |
| Gmail mobile | Chiều rộng, font sizing, dark mode, liên kết | Giống Gmail desktop |
| Outlook desktop classic | Bảng, spacing, button backgrounds, font, images | Giống Outlook web hoặc bản mới |
| Outlook web/newer clients | CSS/layout trong engine tương ứng | Giống mọi phiên bản Outlook |
| Apple Mail desktop | Retina images, typography, dark mode | Giống các mobile clients |
| Apple Mail iOS | Dynamic text, viewport, nút chạm, dark mode | Giống macOS |
| Client của tổ chức | Proxy, security policy, attachment controls | Giống tài khoản cá nhân test |
| Text-only/readers | Plain text, link và nội dung theo thứ tự | HTML luôn được hiển thị |

Bảng mô tả **những phạm vi cần quan sát**, không phải bảng “hỗ trợ CSS” chuẩn cho mọi phiên bản. Những hệ thống có compliance/DLP gateway có thể thay đổi email trước khi tới ứng dụng client.

## 9. Classic Outlook và webmail có thể render khác nhau

Trong nhiều triển khai, một số phiên bản Outlook desktop truyền thống có engine và hành vi layout khác với ứng dụng Outlook web hoặc client mới. Những lựa chọn CSS như positioning, complex background, forms hoặc một số responsive techniques có thể bị xử lý khác.

Một email cần test ít nhất:

1. Outlook phiên bản thực tế tổ chức người nhận đang dùng.
2. Outlook web nếu nhóm người nhận sử dụng.
3. Mobile Outlook nếu tỷ lệ người dùng đáng kể.
4. Dark/light mode nếu template có màu sắc quan trọng.
5. Chế độ chặn hình ảnh hoặc preview pane hẹp.

Không lấy ảnh chụp từ “Outlook” chung chung để kết luận mọi bản Outlook giống nhau. Khi ghi bug, cần **phiên bản, OS, account type và rendering setting**.

## 10. Gmail web và app có thể khác nhau

Cùng một mailbox Gmail có thể hiển thị khác khi mở trong webmail hoặc ứng dụng mobile. Ngoài CSS, các yếu tố như:

- Images được tải trực tiếp hay qua proxy.
- Tắt tải hình ảnh.
- Nội dung dài bị thu gọn hoặc cắt trong một số tình huống.
- Links được rewrite/scan.
- Dark mode của app/hệ điều hành.
- Chiều rộng màn hình và text scaling.

Do vậy, screenshot trên Gmail web desktop là **một test case**, không phải kết luận toàn bộ nền tảng Gmail.

## 11. Apple Mail và thiết bị có Dynamic Type

Người dùng iOS/macOS có thể tăng kích cỡ chữ, bật dark mode hoặc đọc trên màn hình rất hẹp. Khi test:

- Nội dung có bị tràn khi font tăng?
- Button có target dễ chạm?
- Văn bản có bị kẹt trong cột hẹp?
- Logo hoặc icon có đủ tương phản khi nền đổi?
- Link còn dễ nhận biết khi màu sắc bị biến đổi?
- Alt text và văn bản mô tả có ý nghĩa nếu ảnh không hiển thị?

Không chỉ so screenshot pixel-perfect ở một cỡ màn hình. **Khả năng đọc và thao tác** quan trọng hơn việc một màu lệch vài đơn vị so với mockup.

## 12. Hãy định nghĩa “đúng” trước khi test

Một email không nhất thiết phải giống nhau từng pixel trên mọi client. Nên định nghĩa:

**Những điều bắt buộc**:

- Người nhận thấy thông tin chính và đúng người.
- Subject và preheader không gây hiểu lầm.
- Nội dung/giá trị/ngày giờ/mã đơn hàng đúng.
- CTA có nhãn, URL và chức năng chính xác.
- Nội dung đọc được khi bật dark mode/tắt ảnh.
- Không rò Bcc, token không cần thiết hoặc metadata nhạy cảm.
- Mobile không mất nội dung trọng yếu.
- Attachment và alt text phù hợp.

**Những khác biệt có thể chấp nhận**:

- Font fallback khác nhẹ.
- Border radius mất ở một client.
- Shadow hoặc animation không hiển thị.
- Một số spacing biến động nhưng bố cục vẫn đọc tốt.

Tiêu chuẩn này giúp kiểm thử tập trung vào **chức năng và khả năng tiếp cận**, không chạy theo pixel-perfect bất khả thi.

## 13. Template càng quan trọng, mức kiểm tra càng cao

| Loại email | Rủi ro nếu render sai | Cần ưu tiên |
| --- | --- | --- |
| OTP/đặt lại mật khẩu | Người dùng không xác thực được | Độ rõ của mã/link, expiry, copy/paste |
| Xác nhận thanh toán | Hiểu sai số tiền/giao dịch | Bảng số liệu, currency, attachment |
| Hóa đơn | Mất thông tin/tệp pháp lý | PDF/filename, bảng, encoding |
| Thông báo bảo mật | Người dùng bỏ qua cảnh báo | Nội dung và CTA nổi bật ngay khi không có ảnh |
| Email marketing | Conversion/brand, opt-out | Mobile, dark mode, unsubscribe |
| Báo cáo định kỳ | Bảng, biểu đồ, dữ liệu | Fallback cho chart images và dữ liệu quan trọng |
| Email hệ thống nội bộ | Thao tác hỗ trợ/vận hành | Text-only, link, log/tracking an toàn |

Một chiến dịch marketing có thể chấp nhận thay đổi shadow; một email OTP không thể chấp nhận mã bị che hoặc chữ có độ tương phản thấp.

## 14. Đừng gửi mail thử tới khách hàng thật

Kiểm thử mail client phải dùng **test mailbox** và dữ liệu giả. Nếu staging dùng production recipient list, một bài test có thể làm phiền người dùng hoặc tiết lộ thông tin.

Nguyên tắc:

1. Có allowlist các địa chỉ nhận thử nghiệm.
2. Tách sender domain/account/subdomain test nếu phù hợp.
3. Không dùng production token, password, hóa đơn thật, Bcc thật.
4. Đặt subject nhận diện rõ `[TEST]` khi thích hợp.
5. Dùng test customer/transaction IDs giả.
6. Không mở campaign rộng khi chỉ định test một template.
7. Giới hạn rate và quota để tránh ảnh hưởng danh tiếng domain.
8. Theo dõi thời gian lưu test mail và dọn mailbox theo policy.
9. Bảo đảm link CTA trỏ tới staging/test service an toàn.
10. Không dùng screenshot chứa PII thực trong issue tracker.

## 15. Một mail client test pass không chứng minh deliverability toàn hệ thống

Khi một hộp thư seed nhận được email:

- Nó chứng minh **tuyến gửi và client đó** đã nhận/render được fixture trong điều kiện thử.
- Nó không chứng minh toàn bộ email đến người dùng production.
- Nó không xác nhận tỷ lệ Inbox placement của mọi domain.
- Nó không xác nhận tương thích với mọi phiên bản client.
- Nó không chứng minh URL trong email an toàn nếu người khác có token.

Hãy kết hợp client tests với submission/delivery telemetry, không lấy screenshot đẹp thay cho quan sát bounce hoặc complaint.

## 16. Trước khi kiểm tra giao diện: MIME phải đúng

Một email không chỉ là chuỗi HTML. Nó có:

```text
RFC-style mail headers
  From
  To / Cc
  Subject
  Date
  Message-ID
  MIME-Version
  Content-Type
  Content-Transfer-Encoding

Message body
  text/plain
  text/html
  inline resources
  attachments
```

Nếu MIME tree không chính xác, mail client có thể:

- Chọn sai alternative.
- Hiển thị HTML như text.
- Không tìm được ảnh CID.
- Xem inline image như attachment.
- Không giải mã filename/charset mong muốn.
- Báo email có attachment dù đó là logo nội dung.

Do đó, hãy test **cấu trúc MIME**, rồi mới đánh giá kết quả render.

## 17. Một cấu trúc MIME đa định dạng

Đối với email có text, HTML, ảnh inline và PDF:

```text
multipart/mixed
  |
  +-- multipart/related
  |     |
  |     +-- multipart/alternative
  |     |     +-- text/plain; charset=UTF-8
  |     |     +-- text/html; charset=UTF-8
  |     |
  |     +-- image/png; Content-ID:<brand-logo>
  |
  +-- application/pdf; Content-Disposition: attachment
```

Đây là một **cấu trúc hợp lệ mang tính minh họa**, không phải MIME tree duy nhất được mọi thư viện sinh ra. Thứ tự nesting thực tế cần được parse/kiểm tra theo message đã tạo và contract của client.

Ý nghĩa:

- `multipart/alternative`: các cách biểu diễn cùng nội dung; thường có plain text và HTML.
- `multipart/related`: phần HTML và tài nguyên tham chiếu như ảnh CID.
- `multipart/mixed`: kết hợp phần nội dung với attachment độc lập.

Nếu lắp ghép thủ công sai, test mở trong một client có thể chưa phát hiện hết: một client tự sửa lỗi, client khác hiển thị broken.

## 18. Gửi text/plain và text/html cùng lúc

Trong Spring Mail, `MimeMessageHelper` có API:

```java
helper.setText(plainText, htmlText);
```

Điều này tạo nội dung theo hai dạng thay thế nhau để mail client chọn phần phù hợp.

Ví dụ:

```java
String plainText = """
    Xin chào,

    Đơn hàng T-454 đã được xác nhận.
    Xem chi tiết: https://portal.example.org/orders

    Trân trọng.
    """;

String htmlText = """
    <html>
      <body>
        <p>Xin chào,</p>
        <p>Đơn hàng <strong>T-454</strong>
           đã được xác nhận.</p>
        <p><a href="https://portal.example.org/orders">
           Xem chi tiết</a></p>
      </body>
    </html>
    """;

helper.setText(plainText, htmlText);
```

### Tại sao plain text không được bỏ quên?

- Một số client/user settings ưu tiên text-only.
- Các công cụ accessibility có thể lấy content dễ hơn.
- Forward/reply/copy-paste có thể chọn bản plain text.
- Nội dung chủ yếu vẫn khả dụng khi HTML bị chặn hoặc không xử lý được.
- Một số security gateways có thể dựa vào text alternative.

**Plain text phải truyền đạt cùng thông tin nghiệp vụ chính**, không chỉ là “Vui lòng bật HTML”. Với email có OTP hoặc link xác nhận, bản text cũng cần có dữ liệu và đường dẫn phù hợp.

## 19. Phải kiểm tra tương đương nội dung giữa hai alternatives

Một lỗi:

```text
text/plain:
  Đơn hàng của bạn trị giá 150.000 VND.

text/html:
  Đơn hàng của bạn trị giá 1.500.000 VND.
```

Nếu hai bản được render từ những code paths khác nhau, một thay đổi business có thể làm nội dung mâu thuẫn.

Giải pháp:

1. Tạo một **template model đã validate**.
2. Dùng cùng dữ liệu số tiền, ngày, mã đơn hàng để render plain và HTML.
3. Unit test các trường quan trọng ở cả hai representations.
4. Mở email ở ít nhất một client text-only hoặc chế độ plain text.
5. Kiểm tra link và ý nghĩa của CTA.

Khác biệt định dạng là bình thường; **khác biệt thông tin giao dịch là lỗi nghiêm trọng**.

## 20. Ví dụ Spring Boot: dựng email kiểm tra bằng MimeMessageHelper

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MailClientPreviewSender {

    private final JavaMailSender mailSender;

    public MailClientPreviewSender(
            JavaMailSender mailSender
    ) {
        this.mailSender = mailSender;
    }

    public void sendToAllowedTestRecipient(
            String testRecipient
    ) throws MessagingException {
        ensureRecipientIsAllowlisted(testRecipient);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("mail-test@example.org");
        helper.setTo(testRecipient);
        helper.setSubject("[TEST] Xác nhận đơn hàng T-454");

        String plain = """
                Đơn hàng T-454 đã xác nhận.
                Xem chi tiết: https://portal.example.org/orders
                """;

        String html = """
                <html>
                  <body style="margin:0;padding:0">
                    <table role="presentation"
                           width="100%" cellpadding="0"
                           cellspacing="0" border="0">
                      <tr>
                        <td align="center">
                          <table role="presentation"
                                 width="600"
                                 cellpadding="0"
                                 cellspacing="0" border="0">
                            <tr><td style="padding:24px">
                              <img src="cid:brand-logo"
                                   alt="Thương hiệu"
                                   width="120" height="40"
                                   style="display:block">
                              <h1 style="font-size:24px">
                                Xác nhận đơn hàng
                              </h1>
                              <p>Đơn hàng T-454
                                 đã xác nhận.</p>
                              <a href="https://portal.example.org/orders">
                                Xem chi tiết
                              </a>
                            </td></tr>
                          </table>
                        </td>
                      </tr>
                    </table>
                  </body>
                </html>
                """;

        // Nội dung chính trước khi thêm inline resources.
        helper.setText(plain, html);

        helper.addInline(
                "brand-logo",
                new ClassPathResource("mail/test-logo.png")
        );

        mailSender.send(message);
    }

    private void ensureRecipientIsAllowlisted(
            String email
    ) {
        // Ví dụ tối giản: trong hệ thống thật,
        // inject test-recipient registry đã xác thực.
        if (!email.endsWith("@mail-test.example.org")) {
            throw new IllegalArgumentException(
                    "Recipient is outside test allowlist"
            );
        }
    }
}
```

Đây là **ví dụ giảng dạy**, không phải service production hoàn chỉnh. Một kiểm tra `endsWith` đơn giản **không đủ** nếu đầu vào chưa được parse/canonicalize thành địa chỉ mailbox hợp lệ; trong hệ thống thật hãy dùng registry/allowlist chính xác theo identity và môi trường, không chấp nhận địa chỉ tùy ý. Host, URL, sender domain và resource path đều là giá trị minh họa.

### Điều cần test từ message này

- `Content-Type` có multipart phù hợp.
- Bản `text/plain` và `text/html` có nội dung chính tương đương.
- Subject tiếng Việt hiển thị đúng.
- Client tải được `cid:brand-logo` trong các tình huống hỗ trợ.
- Nếu ảnh bị chặn, text và CTA vẫn đọc được.
- HTML không bị vỡ ở màn hình mobile.
- Bố cục hợp lý khi Reply/Forward.

## 21. Vì sao phải thêm inline resource sau setText?

Trong `MimeMessageHelper`, cách compose MIME parts có thể phụ thuộc thứ tự gọi. Khi gửi inline image, cách làm được Spring Mail khuyến nghị là **đặt text trước rồi mới thêm inline resources**:

```java
helper.setText(plain, html);
helper.addInline("brand-logo", imageResource);
```

Thói quen này giúp tránh những khác biệt không mong muốn ở client khi MIME multipart structure bị sắp xếp không phù hợp.

Ngoài ra:

- `Content-ID` trong inline MIME part phải khớp với reference `cid:...`.
- Không chèn dấu ngoặc nhọn/sai ký tự vào CID một cách tùy tiện.
- Resource nên có content type xác định.
- Dữ liệu cần tồn tại khi gửi; file không được xóa trước khi MIME serialize.
- Một số client vẫn có thể hiển thị inline part như attachment khi nhận dạng MIME khác nhau.

Kiểm tra cả **MIME part metadata** lẫn **ảnh hiển thị ở client**, không chỉ nhìn code `addInline(...)`.

## 22. Inline image khác với ảnh từ xa

Hai cách dùng trong HTML:

```html
<!-- Inline Content-ID -->
<img src="cid:brand-logo"
     alt="Logo thương hiệu">

<!-- HTTPS remote image -->
<img src="https://assets.example.org/mail/logo.png"
     alt="Logo thương hiệu">
```

| Đặc điểm | CID inline | HTTPS remote |
| --- | --- | --- |
| Nguồn ảnh | MIME part trong cùng email | Server/CDN bên ngoài |
| Kích thước MIME | Tăng theo kích thước ảnh + encoding | Nhỏ hơn nhưng phải tải mạng |
| Bị chặn ảnh | Có thể vẫn bị xử lý khác tùy client | Có thể bị chặn/proxy |
| Khả năng đổi ảnh sau gửi | Nội dung MIME đã cố định | URL có thể trả tài nguyên mới |
| Cache/proxy | Tùy client | Tùy client/provider |
| Rủi ro privacy | Payload tới recipient/provider | Server ảnh có thể nhận request/metadata |

Không khẳng định CID **luôn hiển thị** hoặc remote image **luôn tải được**. Một số client có thể có các quy tắc riêng. Vì vậy phải thử cả **ảnh hiện** và **ảnh bị chặn**.

## 23. Alt text là nội dung dự phòng, không phải trang trí

Một email chỉ chứa ảnh có chữ “Đơn hàng đã được giao” sẽ không truyền đạt thông tin nếu ảnh bị chặn.

Ví dụ kém:

```html
<img src="cid:important-news"
     alt="image">
```

Ví dụ tốt hơn:

```html
<h1>Đơn hàng đã được giao</h1>
<p>Bạn có thể xem biên nhận tại tài khoản của mình.</p>
<img src="cid:delivery-illustration"
     alt="Minh họa kiện hàng đã giao">
```

**Thông tin quan trọng nên có dưới dạng text thực**, không chỉ nằm trong bitmap. Alt text mô tả ảnh phù hợp, nhưng không thay thế toàn bộ nội dung nghiệp vụ.

Khi test tắt ảnh:

- Nội dung còn hiểu được?
- CTA có nhãn?
- Bố cục có chỗ trống quá lớn?
- Alt text có hiện theo client không?
- Logo không hiển thị có làm người dùng mất nhận diện không?

## 24. Attachment cần test như một phần của trải nghiệm

Một message có PDF:

```java
helper.addAttachment(
        "hoa-don-T-454.pdf",
        new FileSystemResource(invoicePath.toFile())
);
```

Không chỉ assert `attachment != null`. Kiểm tra trong mailbox/client:

- Attachment có xuất hiện đúng là một tệp đính kèm không?
- Filename tiếng Việt/dấu cách có hiển thị đúng không?
- Client có preview được PDF không?
- File mở được và nội dung không bị hỏng bytes?
- Download từ mobile có thao tác hợp lý?
- Mở/forward email có còn attachment không?
- Logo inline có bị hiểu nhầm là một attachment bổ sung không?
- File quá lớn có bị provider/client chặn hoặc hiển thị cảnh báo không?

**Tên tệp và khả năng mở tệp** là một phần của chất lượng email, không chỉ là MIME-level correctness.

## 25. Filename quốc tế và charset

Filename như `"Hóa đơn tháng 11.pdf"` có thể đi qua encoding MIME parameter khác nhau giữa thư viện và client.

Khi test:

- Đọc decoded filename bằng Jakarta Mail parser.
- Mở trên ít nhất hai client đại diện.
- Kiểm tra copy/download tên có dấu trên Windows/macOS/mobile.
- Kiểm tra phần mở rộng đúng và MIME type hợp lý.
- Không đặt dữ liệu nhạy cảm trong filename.

Đối với hệ thống mail client quá cũ hoặc đặc thù, có thể cần một tên file ASCII an toàn làm fallback. Nhưng không cần biến mọi tên file thành ASCII nếu nhóm client mục tiêu hiển thị Unicode tốt.

## 26. Multipart/alternative bị sai sẽ tạo triệu chứng khó đoán

Ví dụ MIME tree sai:

```text
multipart/mixed
  +-- text/plain
  +-- text/html
  +-- image/png
```

Không có nghĩa client luôn chọn đúng HTML khi plain và HTML được đặt là các siblings trong mixed thay vì được nhóm thành alternatives. Một số client có thể hiển thị cả hai hoặc chọn sai representation.

Giải pháp:

- Dùng `MimeMessageHelper` đúng constructor/multipart mode.
- Khi cần MIME phức tạp hơn, dùng Jakarta Mail APIs một cách có chủ đích.
- Parse MIME tree trong integration test.
- Gửi thử raw message tương ứng đến test mailboxes.
- Không dùng client rendering như công cụ duy nhất để phát hiện MIME tree sai.

## 27. Content-Type phải phản ánh nội dung thật

Những trường hợp cần phân biệt:

```text
text/plain; charset=UTF-8
text/html; charset=UTF-8
image/png
application/pdf
multipart/alternative
multipart/related
multipart/mixed
```

Nếu một `String` HTML được gửi bằng `SimpleMailMessage`, mail client có thể hiển thị nguyên các thẻ HTML vì message là plain text. Không thể sửa lỗi này bằng CSS; phải gửi một `MimeMessage` có `text/html` part đúng.

Đối với một tệp nhị phân, việc đặt sai `Content-Type` hoặc `Content-Disposition` có thể làm client preview, tải xuống hoặc xử lý attachment không đúng.

## 28. Content-Transfer-Encoding không đồng nghĩa nội dung bị mã hóa bảo mật

Email có thể dùng:

```text
Content-Transfer-Encoding: quoted-printable
Content-Transfer-Encoding: base64
Content-Transfer-Encoding: 7bit
```

Các encoding này phục vụ **truyền dữ liệu qua MIME/SMTP**, không cung cấp bảo mật. Một email text/html được mã hóa quoted-printable hoặc base64 vẫn có thể được client giải mã và hiển thị nội dung.

Khi test:

- Parse/đọc **decoded content**, không so sánh thô chuỗi raw SMTP bytes với UTF-8 source.
- Đừng nhầm base64 attachment với encryption.
- Kiểm tra client không hiện dấu `=C3=...` hoặc ký tự rác do charset/encoding sai.

## 29. UTF-8 với tiếng Việt cần kiểm tra ở nhiều nơi

Một email có thể có:

- Subject: “Xác nhận thanh toán thành công”.
- Body: “Số tiền: 1.250.000 ₫”.
- Recipient display name: “Nguyễn Minh”.
- Attachment filename: “Hóa đơn tháng 11.pdf”.
- Link path/query có ký tự Unicode nếu ứng dụng tạo URL chưa encode.

**Đặt `"UTF-8"` trong `MimeMessageHelper` là bước quan trọng**, nhưng phải kiểm tra:

1. Dữ liệu nguồn và template file được lưu đúng encoding.
2. Servlet/JSON/database không đã làm hỏng chuỗi trước khi render.
3. MIME Subject và headers được encode/decoded đúng.
4. Text/plain và text/html có charset phù hợp.
5. Filename được hiện đúng trên clients mục tiêu.
6. URL đã được percent-encode theo tiêu chuẩn tương ứng.

Đừng chỉ test bằng toàn ASCII `"Hello world"` rồi suy ra email tiếng Việt an toàn.

## 30. Thời gian và số tiền cần test ở mail client

Một email có:

```text
Lịch hẹn: 09:00 ngày 12/11/2026
Thanh toán: 1.250.000 ₫
```

Nếu ứng dụng render ở timezone không đúng hoặc cột giá tiền bị tràn, người đọc có thể hiểu sai nội dung. Cần:

- Chỉ rõ timezone khi thời gian liên quan người nhận.
- Dùng định dạng số tiền/locale nhất quán giữa plain và HTML.
- Kiểm tra text wrapping với số dài.
- Tránh style `white-space: nowrap` cho mọi số nếu nó khiến mobile overflow.
- Xác nhận dấu phẩy/dấu chấm và ký hiệu tiền tệ không bị đảo.

**Sai thông tin nghiệp vụ do formatting** là lỗi nghiêm trọng hơn việc một bóng đổ không hiển thị.

## 31. CSS trong email: chọn tính ổn định trước hiệu ứng

Email HTML có các ràng buộc khác web. Một số client xử lý tốt `<style>` và media queries; một số loại bỏ, thay đổi hoặc chỉ hỗ trợ một phần. Vì vậy:

- Không phụ thuộc JavaScript.
- Không thiết kế email mà chỉ hoạt động khi `display:grid`/`flex` có hỗ trợ.
- Ưu tiên các bố cục đơn giản và có fallback.
- Sử dụng CSS inline cho những thuộc tính quan trọng khi phù hợp với clients mục tiêu.
- Kiểm tra bảng, border, padding, font, background trong các ứng dụng phổ biến.
- Dùng email-specific CSS inlining/build tools nếu pipeline có hỗ trợ.

Một ví dụ đơn giản:

```html
<td
  style="
    font-family:Arial,Helvetica,sans-serif;
    font-size:16px;
    line-height:24px;
    color:#1f2937;
    padding:24px;
  ">
  Nội dung cần đọc trên nhiều mail client.
</td>
```

Không có một danh sách CSS được hỗ trợ giống nhau ở mọi client/phiên bản. Sử dụng bảng hỗ trợ CSS đã được kiểm chứng cho client mục tiêu và **test trực tiếp** trước khi chốt template.

## 32. Inline CSS không có nghĩa mọi thuộc tính đều hoạt động

Ví dụ:

```html
<div style="
  display:flex;
  position:sticky;
  gap:24px;
  backdrop-filter:blur(8px);
">
  ...
</div>
```

Style được inline, nhưng những thuộc tính hiện đại này vẫn có thể không được mail client hỗ trợ. CSS inlining chỉ đưa declaration gần element; nó không thay đổi rendering engine.

Để tăng tương thích:

1. Xác định critical layout.
2. Chọn HTML structure có thể đọc khi CSS bị bỏ.
3. Đặt inline styles cho typography, spacing và màu quan trọng.
4. Dùng fallback cho những tính năng mới.
5. Test trên các client quyết định SLA.

## 33. Bố cục bằng table trong email

Một pattern thường dùng cho email HTML cần tương thích:

```html
<table role="presentation"
       width="100%"
       cellpadding="0"
       cellspacing="0"
       border="0"
       style="border-collapse:collapse;">
  <tr>
    <td align="center">
      <table role="presentation"
             width="600"
             cellpadding="0"
             cellspacing="0"
             border="0"
             style="width:100%;max-width:600px;">
        <tr>
          <td style="padding:24px;">
            <h1 style="font-size:24px;line-height:30px;">
              Xác nhận đơn hàng
            </h1>
            <p style="font-size:16px;line-height:24px;">
              Đơn hàng T-454 đã xác nhận.
            </p>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
```

`role="presentation"` giúp các công cụ hỗ trợ không coi bảng layout là bảng dữ liệu nếu client hỗ trợ semantics đó. Một số clients có cách áp dụng `max-width` khác; vì vậy vẫn cần thử trên mobile và Outlook.

### Đừng dùng table layout cho mọi thứ

Bảng **dữ liệu thật** (danh sách hóa đơn, giao dịch) cần headings, thứ tự đọc và khả năng cuộn/xếp cột phù hợp. `role="presentation"` chỉ nên đặt lên bảng **để bố cục**, không dùng để vô hiệu hóa semantics của một bảng dữ liệu cần accessible.

## 34. Responsive email khác responsive website

Trên web, bạn có thể dựa nhiều vào media queries. Trong email, khả năng hỗ trợ media queries có thể khác nhau.

Chiến lược:

- Một cột cho nội dung trọng tâm.
- Container có width tương đối và max-width.
- Ảnh có kích thước linh hoạt trong cell.
- Nút có đủ vùng chạm.
- Tránh nhiều cột dữ liệu chật trên mobile.
- Nội dung đọc có thứ tự hợp lý nếu không có responsive CSS.
- Không đặt CTA chỉ trong sidebar/column có nguy cơ bị ẩn.

Ví dụ:

```html
<img
  src="cid:product-photo"
  alt="Ảnh sản phẩm"
  width="280"
  style="
    display:block;
    width:100%;
    max-width:280px;
    height:auto;
    border:0;
  ">
```

Đây là một pattern fallback, không cam kết mọi client tuân thủ chính xác. Test trên các widths đại diện sẽ phát hiện overflow, ảnh bị phóng và table cell ép chữ.

## 35. Chiều rộng 600 px không phải một luật cứng

Nhiều template email dùng container quanh 600 px, nhưng không có một kích thước áp dụng đúng cho mọi thiết bị hoặc client.

Một template rộng cố định:

```html
<table width="900">
  ...
</table>
```

có thể gây horizontal scroll trên điện thoại. Một template hẹp quá lại làm bảng số liệu khó đọc trên desktop.

Thiết kế:

1. Chọn container width theo loại nội dung.
2. Dùng responsive/stacking nơi clients mục tiêu hỗ trợ.
3. Xác định cách trình bày bảng dữ liệu trên mobile.
4. Kiểm tra màn hình rất hẹp, zoom và text scaling.
5. Không phụ thuộc chỉ vào viewport meta tag để sửa layout.

## 36. Long text và link dài có thể phá layout

Dữ liệu thật có thể dài hơn mockup:

```text
Tên khách hàng dài
Mã đơn hàng có nhiều ký tự
URL có query string dài
Email recipient display name dài
Địa chỉ chứa nhiều dòng
```

Khi CSS/word wrapping khác nhau giữa clients:

- Link dài có thể đẩy table ra khỏi màn hình.
- Một mã không có dấu cách làm cột quá rộng.
- Tên tiếng Việt có dấu có thể xuống dòng bất ngờ.
- Các ký tự Unicode đặc biệt có thể tạo vấn đề directionality.

Nên kiểm thử với **boundary fixtures**, không chỉ chuỗi ngắn đẹp. Nếu URL chứa token, không log/screenshot nó ở môi trường chia sẻ; dùng link synthetic với domain staging.

## 37. Button bằng CSS và fallback link

Một CTA được thiết kế như nút:

```html
<table role="presentation" border="0"
       cellpadding="0" cellspacing="0">
  <tr>
    <td bgcolor="#2058c9"
        style="border-radius:6px;
               background-color:#2058c9;">
      <a href="https://portal.example.org/orders"
         style="display:inline-block;
                padding:14px 24px;
                font-size:16px;
                font-family:Arial,sans-serif;
                color:#ffffff;
                text-decoration:none;">
        Xem đơn hàng
      </a>
    </td>
  </tr>
</table>
```

Một số client không render button background/border radius/padding giống web. Cần xem:

- Text label vẫn đọc được nếu background biến mất?
- Link còn click/tap được?
- Button có bị chia nhiều dòng?
- Màu chữ đủ tương phản trong dark mode?
- URL có đúng staging/production domain?
- Tương tác bằng bàn phím/screen reader có thuận tiện?

Nếu email rất quan trọng, có thể cung cấp thêm **đường dẫn văn bản rõ nghĩa** sau nút, nhưng tránh in trực tiếp một bearer token nhạy cảm trong screenshot hoặc email được forward.

## 38. Đừng tạo CTA chỉ bằng background image

Ví dụ kém:

```html
<a href="https://portal.example.org/confirm">
  <img src="cid:confirm-button"
       alt="">
</a>
```

Nếu ảnh bị chặn, người dùng không biết mục tiêu của link. Ví dụ tốt hơn:

```html
<a href="https://portal.example.org/confirm">
  Xác nhận yêu cầu
</a>
```

hoặc dùng button bằng HTML text như phần trước. Chức năng chính nên tồn tại độc lập với ảnh trang trí.

## 39. Dark mode không chỉ đổi một màu nền

Mail client có thể:

- Giữ nguyên màu theo inline CSS.
- Tự đảo màu background và text.
- Chỉ thay đổi một số thành phần.
- Áp dụng màu/theme theo cài đặt người dùng.
- Không dùng CSS media query về color scheme như browser.

Hậu quả:

```text
Light mode: chữ đen trên nền trắng -> rõ
Dark mode:  nền biến thành đen,
            nhưng một phần chữ vẫn đen -> khó đọc
```

Với ảnh logo màu tối, dark mode có thể khiến logo chìm vào background. Cần thử:

1. Light mode trên desktop.
2. Dark mode trên desktop nếu hỗ trợ.
3. Dark mode trên mobile clients phổ biến.
4. Ảnh bị chặn kết hợp dark mode.
5. Logo, CTA, bảng giá, warning và footer.

Không chỉ test một screenshot dark mode từ một client rồi suy ra mọi client sử dụng cùng quy tắc đảo màu.

## 40. Tương phản màu và accessibility

Một email tốt cần:

- Nội dung chính dễ đọc với độ tương phản đủ theo mục tiêu accessibility của tổ chức.
- Không chỉ dùng màu đỏ/xanh để truyền đạt trạng thái.
- Có text label cho icon quan trọng.
- Link có tên mô tả.
- Font cơ bản đủ lớn và line-height hợp lý.
- Nội dung có thứ tự đọc logic.
- Không nhấp nháy/animation gây khó chịu hoặc phụ thuộc animation để hiểu.

Ví dụ:

```html
<!-- Tránh chỉ có biểu tượng màu đỏ -->
<p>🔴</p>

<!-- Nên có nhãn văn bản -->
<p><strong>Thanh toán thất bại.</strong>
   Vui lòng cập nhật phương thức thanh toán.</p>
```

Trong dark mode, một màu đúng chuẩn trên nền sáng vẫn có thể trở nên khó đọc nếu client đổi nền. Kiểm tra **tương phản sau khi render**, không chỉ kiểm mã màu trong HTML source.

## 41. Font fallback và line height

Không phải mail client nào cũng tải web font hoặc dùng font custom như browser. Nên chọn font stack:

```html
<p style="
  font-family:Arial,Helvetica,sans-serif;
  font-size:16px;
  line-height:24px;
">
  Nội dung tiếng Việt có dấu: Hóa đơn đã thanh toán.
</p>
```

Khi một font không tồn tại:

- Dòng có thể dài/ngắn hơn.
- CTA có thể xuống dòng.
- Bảng có thể nở rộng.
- Dấu tiếng Việt cần hiển thị đầy đủ.
- Kích cỡ chữ do user tăng có thể làm container cao hơn.

Tránh đặt fixed height cho block chứa text dài. Test bằng font fallback và cỡ chữ lớn.

## 42. Preheader và preview text

Nhiều mail clients hiển thị một đoạn xem trước cạnh subject. Đoạn này có thể được suy từ nội dung đầu message hoặc từ một đoạn HTML preheader được xây chủ đích.

Ví dụ:

```html
<div style="
  display:none;
  font-size:1px;
  line-height:1px;
  color:transparent;
  max-height:0;
  max-width:0;
  opacity:0;
  overflow:hidden;
">
  Đơn hàng T-454 đã được xác nhận.
</div>
```

**Đây chỉ là một technique thường gặp, không được mọi client thực hiện giống nhau.** Nếu preheader bị render thành nội dung đầu body hoặc bị bỏ qua, user experience có thể khác.

Khi test:

- Preview text có đúng nội dung?
- Có lộ token/OTP/PII trên notification ngoài màn hình khóa?
- Có bị lấy từ CSS, alt text hoặc footer?
- Text có bị cắt giữa một từ nhạy cảm?
- Subject/preheader có khác nhau giữa web và mobile?

Preheader là một phần của trải nghiệm và quyền riêng tư, không chỉ là chi tiết marketing.

## 43. Subject và From là UI quan trọng

Một email có layout đẹp nhưng subject mơ hồ:

```text
Subject: Thông báo
```

người nhận khó xác định mức độ quan trọng. Một subject cụ thể hơn:

```text
Subject: [TEST] Đơn hàng T-454 đã xác nhận
```

có thể giúp phân biệt email test và production.

Khi test mail client:

- Tên hiển thị From và địa chỉ có hợp lý?
- Subject có chứa Unicode đúng?
- Subject có bị cắt trên mobile mà mất thông tin chính?
- Reply-To có dẫn đến đúng kênh hỗ trợ?
- Có vô tình thêm `[TEST]` vào mail production?
- Header From có nhất quán với domain authentication của route?

Test rendering không chỉ là body HTML; **mailbox list UI** cũng quan trọng.

## 44. Các email quá dài có thể bị thu gọn

Một số mail clients có thể thu gọn hoặc cắt nội dung email dài theo cơ chế của sản phẩm/phiên bản. Nếu phần:

- CTA.
- Mã xác nhận.
- Thông tin thanh toán.
- Link hỗ trợ.
- Unsubscribe bắt buộc cho luồng phù hợp.

nằm quá sâu cuối một email rất dài, người dùng có thể không nhìn thấy ngay.

Phương án:

- Đưa thông tin quan trọng gần đầu.
- Rút gọn markup không cần thiết.
- Không nhúng cùng một block CSS/HTML lặp nhiều lần.
- Không đưa attachment dạng base64 vào HTML body.
- Kiểm tra email dài thực tế trên các clients mục tiêu.
- Giữ footer và thông tin hỗ trợ dễ truy cập.

Không dựa vào một con số clipping threshold cố định cho mọi phiên bản Gmail/client; hãy test với payload thực của sản phẩm.

## 45. HTML email không nên phụ thuộc JavaScript

Một trang web có thể có:

```html
<button onclick="confirmOrder()">
  Xác nhận
</button>
```

Nhưng email clients thường chặn hoặc loại bỏ script và event handlers vì bảo mật. CTA nên là một link HTTPS đến ứng dụng:

```html
<a href="https://portal.example.org/orders/confirm">
  Xác nhận trong ứng dụng
</a>
```

Điểm đến phải có authentication/authorization/CSRF hoặc one-time token theo thiết kế; không biến việc nhấn link trong email thành một hành động nhạy cảm không có bảo vệ.

### Không dùng form HTML email làm thao tác bắt buộc

Input/form bên trong email có hỗ trợ rất khác nhau. Một số client vô hiệu hóa hoặc chuyển cách hiển thị. Nếu người dùng phải nhập mã, cập nhật thẻ thanh toán hoặc xác nhận giao dịch, dẫn họ đến một trang HTTPS có bảo vệ sẽ dễ kiểm thử và an toàn hơn.

## 46. Link tracking và redirect có thể ảnh hưởng trải nghiệm

Provider hoặc gateway có thể rewrite:

```text
https://portal.example.org/orders/123
        |
        v
https://tracking-or-security-gateway/... 
        |
        v
Destination URL
```

Điều này có thể ảnh hưởng:

- Link redirect trong mobile app.
- Deep links và universal links.
- Thời gian tải.
- URL encoding.
- One-time token/expiry.
- Security scanner/prefetch.
- Điều kiện xác thực/cookie.

Khi test, **nhấn link trong mail client thật** và xác minh đích cuối, không chỉ đọc `href` trong source. Không dùng dữ liệu thật hoặc token production trong screenshot/test link.

## 47. Click scanner có thể kích hoạt link trước người dùng

Một số hệ thống security scan URL trong email. Nếu một link GET vừa mở đã thực thi hành động phá hủy hoặc thay đổi trạng thái (hủy đơn, xác thực token, đổi mật khẩu), scanner có thể gây side effect không mong muốn.

Thiết kế an toàn hơn:

1. Link GET mở trang xác nhận, không tự hoàn tất hành động nguy hiểm.
2. Hành động thực hiện sau bước người dùng chủ động với bảo vệ phù hợp.
3. One-time tokens được kiểm tra theo đúng lifecycle và không lộ vào logs.
4. Có protection chống replay/CSRF theo loại thao tác.
5. Test với mailbox/gateway có scanning nếu doanh nghiệp dùng.

Đây là một lỗi **hành vi người dùng sau khi mở mail**, không thể phát hiện bằng snapshot HTML thuần túy.

## 48. Tắt ảnh từ xa: một test case bắt buộc

Một client có thể không tải external images theo mặc định hoặc theo policy tổ chức. Hãy thử:

```text
Image loading:
  [ ] Enabled
  [ ] Disabled / Ask before loading
```

Với ảnh bị tắt, kiểm tra:

- Nội dung chính vẫn xuất hiện.
- CTA có text không phụ thuộc image.
- Logo/illustration có alt text phù hợp.
- Không còn khoảng trống quá lớn gây hiểu lầm.
- Giá tiền, hạn thanh toán, OTP không nằm trong ảnh.
- Background image biến mất có ảnh hưởng độ tương phản không.

### Vì sao không chỉ test ảnh online?

Inline CID có thể có behavior khác external image. Một client cũng có thể proxy, cache hoặc thay URI. Hãy test **loại ảnh thực tế template đang dùng**.

## 49. Chặn ảnh không phải lỗi của Spring Mail

Nếu MIME part có `Content-ID` đúng, raw HTML tham chiếu đúng, nhưng user setting chặn image, đó có thể là behavior bảo mật của client. Giải pháp không nhất thiết là sửa backend SMTP; nên làm email **đọc được khi không có hình**.

Trái lại, nếu CID part thiếu hoặc sai MIME nesting, đó là lỗi compose. Phân loại đúng sẽ giảm việc sửa nhầm code.

## 50. HTML sanitization và những thẻ không phù hợp

Mail clients có thể loại bỏ:

- `<script>` và script/event handlers.
- Form components.
- Embedded media.
- External CSS hoặc một số style rules.
- Iframes.
- Một số SVG và dynamic content.
- Tài nguyên không được phép bởi security policy.

Đừng dùng các thành phần đó để truyền tải thông tin bắt buộc.

Một email nên có semantic core:

```html
<h1>Thanh toán hoàn tất</h1>
<p>Số tiền: 1.250.000 ₫</p>
<p>Mã tham chiếu: T-454</p>
<p>
  <a href="https://portal.example.org/receipts">
    Xem biên nhận trong tài khoản
  </a>
</p>
```

Trang trí có thể nâng cấp trải nghiệm, nhưng nội dung phải sống được sau khi HTML bị xử lý hạn chế.

## 51. CSS reset của web có thể gây tác dụng phụ trong email

Framework CSS web thường giả định:

- Global `box-sizing`.
- Flex/grid support.
- Pseudo selectors.
- Custom properties.
- Modern layout features.
- Một số styles trên `html`, `body` hoặc selectors bị client hạn chế.

Nếu copy nguyên CSS của SPA vào email:

```text
Browser preview: đẹp
Mail client: nhiều style bị bỏ hoặc khác default
```

Nên xây **email design system** riêng hoặc dùng email template tool có hỗ trợ output tương thích, sau đó vẫn phải test trên clients thật. Không nhúng một bundle CSS web lớn và nghĩ rằng minify sẽ giải quyết compatibility.

## 52. Dark mode nên có thiết kế chịu lỗi

Để tránh logo không nhìn thấy:

- Ưu tiên logo có vùng nền/viền phù hợp khi cần.
- Kiểm tra biến thể light/dark nhưng không phụ thuộc tuyệt đối vào media query.
- Không dùng ảnh transparent màu tối đặt trên nền có thể thành đen.
- Dùng nhãn text thương hiệu nếu logo là thông tin bắt buộc.
- Giữ CTA label có contrast ngay khi client tự đổi màu.

Ví dụ:

```html
<img
  src="cid:brand-logo"
  width="120"
  height="40"
  alt="Phòng hỗ trợ"
  style="
    display:block;
    background-color:#ffffff;
    padding:8px;
  ">
```

Ngay cả `background-color:#ffffff` có thể bị thay đổi ở một số clients. Do vậy chỉ là một mitigation; cần nhìn kết quả render.

## 53. Email ảnh-heavy có thể kém accessible

Một design chỉ gồm một ảnh dài:

```html
<img src="https://assets.example.org/promo-all-in-one.png">
```

có những vấn đề:

- Bị chặn ảnh sẽ gần như trắng.
- Screen reader thiếu nội dung semantic.
- Text trong ảnh không scale theo user settings.
- Hình ảnh lớn tải chậm.
- Link trong ảnh không dễ biểu thị nhiều hành động.
- Không thể copy nội dung văn bản.

Nên dùng HTML text cho thông tin, ảnh cho minh họa. Nếu thực sự cần infographic, tóm tắt ý nghĩa và cung cấp link đến trang nội dung accessible.

## 54. Thử screen reader và keyboard navigation

Một test rendering hiện đại không chỉ là screenshot:

1. Mở email trong client có screen reader hoặc accessibility tools được hỗ trợ.
2. Kiểm tra thứ tự đọc.
3. Kiểm tra headings có logic.
4. Kiểm tra link có tên mô tả (không chỉ “Click here”).
5. Kiểm tra ảnh trang trí không gây tiếng ồn quá mức.
6. Kiểm tra bảng dữ liệu có thể hiểu.
7. Kiểm tra các thao tác chính không chỉ dựa vào màu hoặc vị trí.
8. Nếu client hỗ trợ, dùng bàn phím để chuyển đến links.

**Không chỉ dùng một điểm accessibility checker tự động** để tuyên bố email accessible. Kết quả thực tế còn phụ thuộc mail client và công nghệ hỗ trợ.

## 55. Plain text là fallback về nội dung, không phải bản sao HTML

Trong HTML:

```html
<a href="https://portal.example.org/orders">
  Xem đơn hàng
</a>
```

Trong plain text:

```text
Xem đơn hàng:
https://portal.example.org/orders
```

Đường link cần đầy đủ để người dùng text-only có thể sử dụng. Nếu link là magic-link token, chú ý bảo vệ trong quá trình test/forward/log.

Khi HTML có bảng:

```text
Mặt hàng: Sách
Số lượng: 2
Đơn giá: 120.000 VND
Tổng: 240.000 VND
```

Một bản plain text dạng key-value có thể dễ đọc hơn cố tái tạo bảng ASCII rộng.

## 56. Reply và Forward có thể làm nội dung thay đổi

Người dùng không chỉ đọc lần đầu; họ có thể Reply/Forward email:

- Một client có thể chuyển HTML thành format khác.
- CID image có thể bị bỏ hoặc đổi reference.
- CSS styles bị strip.
- Attachment có thể bị tách/đổi cách thể hiện.
- Quote history lặp nhiều lần làm email dài.
- Link tracking có thể giữ URL rewritten.
- Nơi nhận forward có mail client khác.

Nếu email cần được forward trong nghiệp vụ (vé, xác nhận đặt chỗ, báo cáo), hãy test **forward qua ít nhất một cặp client đại diện**.

### Không dựa vào forward để chia sẻ credential

OTP, reset token, thông tin định danh hoặc attachment nhạy cảm không nên được thiết kế với giả định ai forward cũng được quyền sử dụng. Business authorization ở trang đích vẫn cần thực thi.

## 57. Thử email được trả lời (Reply-To)

Ví dụ:

```java
helper.setReplyTo("support@example.org");
```

Kiểm tra trong client:

- Nhấn Reply sẽ gửi về đúng mailbox hỗ trợ?
- Có trường hợp reply đi vào `no-reply`?
- Người dùng thấy tên hiển thị From và Reply-To như thế nào?
- Có lộ địa chỉ nội bộ không mong muốn?
- Với thread email, có bị nhóm sai vào một conversation?

Đừng chỉ assert header có mặt mà không thử một lần reply trong mailbox test.

## 58. Threading và conversation view

Một số client nhóm nhiều email thành conversation/thread dựa trên subject, Message-ID hoặc các headers như In-Reply-To/References tùy logic của nó.

Đôi khi các email khác nhau lại có Subject giống nhau:

```text
Subject: Thông báo
Subject: Thông báo
Subject: Thông báo
```

Client có thể gom chúng gây khó tìm. Ngược lại, nếu ứng dụng cố đặt cùng một `Message-ID` cho nhiều emails riêng, có thể tạo hành vi bất thường.

Khi test một flow nhiều email:

- Subject có đủ thông tin phân biệt không?
- Threading có phản ánh mục đích thực tế?
- Message IDs có được tạo theo contract?
- Email reply có vào đúng conversation nếu đó là yêu cầu?

Không dùng cố định `Message-ID` làm thủ thuật “tránh gửi trùng”; nó không bảo đảm dedup SMTP và có thể làm hành vi client khó đoán.

## 59. Mail client cũng tác động đến URL detection

Một số client có thể tự biến chuỗi điện thoại, địa chỉ, ngày tháng hoặc URL thành link:

```text
Điện thoại: 0900 000 000
Ngày hẹn: 12/11/2026
Mã đơn hàng: 123456
```

Trên mobile, số điện thoại và ngày tháng có thể được nhận diện thành hành động. Việc đó có thể thay màu/underline hoặc tạo khả năng tap không chủ định.

Hãy test khi:

- Số đơn hàng trông giống số điện thoại.
- Địa chỉ chứa dấu và xuống dòng.
- Ngày tháng có locale mơ hồ.
- Chuỗi tài khoản dài cần copy chính xác.

Nếu tính năng auto-link gây hiểu lầm, điều chỉnh cách trình bày nội dung một cách tương thích; không dùng thủ thuật chèn ký tự vô hình tùy tiện khiến copy/paste sai.

## 60. Định dạng địa chỉ và ký tự hai chiều

Email có thể chứa tên người nhận, địa chỉ hoặc nội dung dùng ngôn ngữ viết phải sang trái (RTL) xen với số/URL. Khi test:

- Thứ tự số tiền và ký hiệu tiền tệ.
- Thứ tự ký tự trong đường link.
- Chiều của câu và bảng.
- Copy/paste mã xác thực.
- Screen reader pronunciation.

Đừng chỉ test tiếng Anh với tên ngắn. Với sản phẩm đa ngôn ngữ, xây fixtures tương ứng locale khách hàng và kiểm thử ở clients đại diện.

## 61. Tắt tải ảnh và dark mode phải được test cùng nhau

Test độc lập:

```text
Dark mode OFF, images ON  -> PASS
Dark mode ON,  images ON  -> PASS
Dark mode OFF, images OFF -> PASS
```

chưa bao phủ kết hợp:

```text
Dark mode ON, images OFF  -> logo absent,
                            white text invisible?
```

Không cần mọi phép kết hợp trên mọi thiết bị, nhưng với template nhạy cảm/quan trọng, nên có một số **pairwise test cases** đại diện thay vì chỉ một biến mỗi lần.

## 62. Font size lớn kết hợp viewport hẹp

Một người dùng bật cỡ chữ hệ thống lớn có thể làm:

- Nút bị tăng chiều cao.
- Bảng hai cột trở nên quá chật.
- Line breaks khác.
- Footer bị đẩy xuống sâu.
- Một fixed-height container cắt mất text.

Khi test mobile:

1. Mở ở viewport thông thường.
2. Thử tăng text size nếu client hỗ trợ.
3. Xoay ngang/dọc.
4. Kiểm tra CTA và nội dung trọng tâm.
5. Kiểm tra không cần zoom/horizontal scroll để đọc thông điệp chính.

## 63. Bảng giá và dữ liệu nhiều cột cần cách xử lý riêng

Một bảng dữ liệu:

```text
Item | Qty | Unit price | Tax | Discount | Total
```

có thể phù hợp desktop nhưng quá rộng trên mobile.

Giải pháp theo độ quan trọng:

- Hiển thị tóm tắt và tổng tiền trước.
- Trình bày mỗi item dưới dạng stacked card/text khi màn hình hẹp.
- Cung cấp PDF hoặc portal cho bảng chi tiết nếu được phép.
- Không hy sinh dữ liệu cần thiết hoặc tính chính xác.
- Dùng table markup có semantics cho dữ liệu thực.

Nếu chỉ có bảng HTML, test trên ít nhất một mobile client để phát hiện horizontal overflow và cột bị che.

## 64. Ma trận test mail client: bắt đầu từ đối tượng người dùng

Không nên chọn ma trận chỉ theo sở thích developer. Cần hỏi:

- Bao nhiêu người nhận dùng Gmail/Outlook/Apple Mail hoặc hệ thống doanh nghiệp?
- Tỷ lệ mobile so với desktop?
- Có nhóm dùng Outlook classic/thiết bị cũ không?
- Có môi trường nghiêm ngặt về attachment/link?
- Email loại nào có tác động lớn nếu lỗi?
- Những bản OS/app nào đang được hỗ trợ?

Một ma trận mẫu **để minh họa**, không phải tiêu chuẩn bắt buộc:

| Client | Môi trường | Chế độ | Ưu tiên |
| --- | --- | --- | --- |
| Gmail web | Desktop browser | Light, images on/off | Cao |
| Gmail mobile | Android hoặc iOS | Light/dark, narrow screen | Cao |
| Outlook desktop (bản đang dùng) | Windows | Reading pane, images blocked | Cao nếu người dùng doanh nghiệp |
| Outlook web | Desktop browser | Light/dark | Trung bình/cao |
| Apple Mail | iPhone | Light/dark, larger text | Cao nếu nhiều người dùng iOS |
| Apple Mail | macOS | Light/dark | Trung bình |
| Mail client tổ chức | Desktop/mobile | Security gateway, attachment restrictions | Theo doanh nghiệp |
| Text-only mail reader | Test mode | text/plain | Cao với email transactional |

Hãy **thay đổi** ma trận này bằng usage data và client support policy của sản phẩm.

## 65. Mỗi chiều test có nhiều điều kiện

Một test case có thể được định danh bằng:

```text
Template: payment-receipt v7
Fixture: multiple-items-vnd
Client: Outlook desktop
OS: Windows
App version: recorded
Theme: dark
Images: disabled
Viewport: narrow reading pane
Locale: vi-VN
```

Nếu kết hợp tất cả biến, số test cases sẽ rất lớn. Dùng **risk-based selection**, pairwise coverage và mức độ quan trọng của template để chọn hợp lý.

## 66. Test theo tầng rủi ro thay vì mọi tổ hợp

Một cách phân tầng:

**Smoke tests** cho mỗi lần thay đổi template:

- Plain text và HTML MIME.
- Client web phổ biến.
- Một mobile client.
- CTA, nội dung chính và link.

**Regression tests** khi release:

- Các clients thuộc nhóm được hỗ trợ.
- Light/dark.
- Images on/off.
- Attachment.
- Long-text/locale fixtures.

**Extended tests** khi có thay đổi lớn:

- New mail client version/OS version.
- Template layout mới.
- Nhiều cột hoặc dynamic content.
- Thay đổi provider SMTP hoặc security gateway.
- Hệ thống accessibility đặc thù.

Không nên tuyên bố “đã test 100% clients”; hãy công bố **đã test những điều kiện nào và giới hạn nào còn lại**.

## 67. Dùng tài khoản seed thử nghiệm

Một seed mailbox là hộp thư được quản lý để nhận email thử theo template và client. Nó khác với một chiến dịch gửi mail tới khách hàng thật.

Quy trình:

1. Tạo các test mailboxes thuộc những dịch vụ/tenant đại diện được phép.
2. Ghi cách đăng nhập/quản trị mà không chia sẻ credential trong tài liệu công khai.
3. Đăng ký allowlist recipient.
4. Kết nối SMTP test/staging provider theo cấu hình phê duyệt.
5. Dùng synthetic fixtures và link staging.
6. Gắn run ID/template version vào metadata phù hợp.
7. Gửi một bản cho mỗi mailbox được chọn.
8. Mở message bằng những ứng dụng thật theo test matrix.
9. Ghi evidence/screenshot và trạng thái test.
10. Dọn mailbox/evidence theo retention policy.

Nếu việc dùng tài khoản thử nghiệm trên một dịch vụ có yêu cầu điều khoản hoặc quyền tổ chức, hãy tuân thủ chúng. Không dùng account cá nhân của nhân viên nếu có thể dùng account do dự án quản lý.

## 68. Test inbox placement khác test rendering

Seed account có thể nhận mail trong:

```text
Inbox
Spam/Junk
Promotions/Other
Quarantine
Không thấy trong tài khoản
```

Nếu email bị đưa vào Spam, đó có thể liên quan deliverability/reputation hoặc content filtering. Khi đã mở được message, bạn vẫn có thể test HTML rendering, nhưng cần ghi:

- Message nằm ở thư mục nào?
- Client có chặn ảnh/link/attachment do folder/risk policy không?
- Nếu chuyển từ Spam về Inbox, behavior có đổi không?
- Giao diện có gắn warning làm user experience khác không?

Không dùng “không vào Inbox” làm bằng chứng CSS sai. Đồng thời không lấy một seed account làm kết luận về placement của tất cả người nhận.

## 69. Phân biệt provider submission test và client rendering test

Một pipeline nên tách:

```text
Test template model
      |
      v
Generate MIME in test context
      |
      v
Parse/check MIME structure
      |
      v
Submit via approved test route
      |
      v
Seed mailboxes
      |
      v
Open with supported clients
      |
      v
Record screenshots + interactions
```

Nếu ở bước submit có SMTP authentication error, chưa thể kết luận gì về client rendering. Nếu MIME parse lỗi, cần sửa composer trước khi thử dark mode.

## 70. Đặt tên test run và template version

Để có thể tái hiện một screenshot bug, cần biết **chính xác mail được render từ phiên bản nào**.

Ví dụ:

```text
testRunId = mail-render-454-20261112
templateKey = order-confirmation
templateVersion = 7
fixtureId = long-vietnamese-name
buildCommit = abc1234
senderRoute = staging-smtp
```

Không đặt commit hash, run ID hoặc fixture key vào header SMTP public nếu không cần. Có thể giữ ở test harness/evidence store và dùng subject `[TEST]` kèm opaque ID ngắn để tìm mail, với điều kiện không lộ bí mật.

## 71. Thu thập evidence có cấu trúc

Một bản ghi test:

```yaml
runId: mail-render-454-demo
template: order-confirmation
templateVersion: 7
fixture: multiple-items-vnd
clientFamily: Outlook
clientVersion: recorded-in-test
osVersion: recorded-in-test
theme: dark
images: blocked
viewport: narrow-reading-pane
result: FAIL
symptom: CTA label has insufficient contrast
rawMimeRef: restricted-artifact-reference
screenshotRef: restricted-artifact-reference
```

Đây là **schema ví dụ**, không phải file metadata STEP 4. Những artifact pointers phải trỏ tới hệ thống có quyền truy cập và retention, đặc biệt nếu screenshot có email address hoặc token.

## 72. Screenshot test: ích lợi và giới hạn

Screenshot giúp so sánh layout, spacing, color và visibility. Nhưng:

- Font rendering khác nhau theo OS/scale.
- Anti-aliasing và subpixel có thể gây pixel diffs giả.
- Dynamic content thay đổi số dòng.
- Client UI/warnings/promo banners có thể thay đổi.
- Một screenshot không kiểm tra link click-through.
- Ảnh không thể đánh giá screen reader.
- Một ảnh chụp với images enabled không bao phủ disabled.

Nên dùng screenshot regression như **tín hiệu hỗ trợ**, không là nguồn quyết định duy nhất. Với lỗi trọng yếu, phải kiểm tra tương tác và nội dung thật.

## 73. Test automation nào hữu ích?

Automation có thể:

1. Render plain và HTML từ cùng fixture.
2. Tạo `MimeMessage` và parse headers/parts.
3. Gửi đến SMTP capture server.
4. Tự gửi đến seed mailboxes theo allowlist.
5. Thu nhận test IDs và trạng thái provider.
6. Chụp/so sánh screenshots nếu có dịch vụ công cụ phù hợp và được cấp quyền.
7. Kiểm tra URLs đã được xây dựng theo expected origin.
8. Xuất report theo template/version/client.

Những công việc **không nên tự cho là đã tự động kiểm tra đủ**:

- Mọi khác biệt layout trong mail client ngoài test matrix.
- Screen reader experience thực tế.
- Một email vào Inbox của tất cả người dùng.
- Link có được người dùng hiểu đúng.
- External security gateways có can thiệp không.
- Cảm giác dễ đọc với cỡ chữ lớn.

## 74. Dùng SMTP capture server cho kiểm thử cấu trúc

Một SMTP test server như GreenMail hoặc mail capture server giúp nhận message mà **không cần gửi tới hộp thư thật**. Dùng để kiểm tra:

- Subject và From/To.
- `multipart/alternative`.
- HTML/plain text content.
- CID và attachment MIME parts.
- Encoding.
- Bytes của file.

Tuy nhiên, giao diện xem mail của capture server **không phải cùng rendering engine** với Gmail, Outlook hay Apple Mail. Một preview đẹp ở đó không chứng minh các clients thật tương thích.

## 75. Ví dụ integration test với GreenMail

Đây là ví dụ **chỉ gửi tới SMTP test server cục bộ**, không gửi mail ra Internet:

```java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

import static org.junit.jupiter.api.Assertions.*;

class MailComposerSmtpTest {

    @Test
    void receivesHtmlAndPlainTextMessage() throws Exception {
        GreenMail server = new GreenMail(
                new ServerSetup(0, "127.0.0.1", "smtp")
        );
        server.start();

        try {
            JavaMailSenderImpl sender = new JavaMailSenderImpl();
            sender.setHost("127.0.0.1");
            sender.setPort(server.getSmtp().getPort());

            MimeMessage message = sender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(
                    message, true, "UTF-8"
            );
            helper.setTo("recipient@example.net");
            helper.setFrom("mail-test@example.org");
            helper.setSubject("Xác nhận đơn hàng T-454");
            helper.setText(
                    "Đơn hàng T-454 đã xác nhận.",
                    "<p>Đơn hàng <b>T-454</b> đã xác nhận.</p>"
            );

            sender.send(message);

            assertTrue(server.waitForIncomingEmail(5000, 1));

            MimeMessage received = server.getReceivedMessages()[0];
            assertEquals(
                    "Xác nhận đơn hàng T-454",
                    received.getSubject()
            );
            assertTrue(received.isMimeType("multipart/*"));
        } finally {
            server.stop();
        }
    }
}
```

Test cần dependency GreenMail tương thích với Jakarta Mail của dự án. Assertion `multipart/*` là kiểm tra ở mức cao; test production nên **walk MIME tree** để xác minh text/plain, text/html và content đúng. Không chạy SMTP real trong CI nếu môi trường không được phép.

## 76. Tại sao không so raw MIME text bằng chuỗi?

Một raw email có thể encode tiếng Việt bằng quoted-printable hoặc base64. Nếu test tìm nguyên văn:

```text
"Đơn hàng đã xác nhận"
```

trong raw bytes, nó có thể không xuất hiện dù mail client decode đúng.

Nên dùng Jakarta Mail parser để lấy **decoded content**, content type, filename và Content-ID, sau đó assert các trường business. Raw MIME vẫn hữu ích để điều tra ranh giới RFC headers/parts, nhưng không nên là cách duy nhất để đọc message.

## 77. Walk MIME tree để tìm nội dung

Ví dụ hàm hỗ trợ test đơn giản:

```java
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.IOException;

static void visitMimeParts(Part part) throws Exception {
    if (part.isMimeType("multipart/*")) {
        Multipart multi = (Multipart) part.getContent();
        for (int i = 0; i < multi.getCount(); i++) {
            visitMimeParts(multi.getBodyPart(i));
        }
        return;
    }

    if (part.isMimeType("text/plain")) {
        String text = (String) part.getContent();
        assertTrue(text.contains("T-454"));
    }

    if (part.isMimeType("text/html")) {
        String html = (String) part.getContent();
        assertTrue(html.contains("T-454"));
    }
}
```

Đoạn code minh họa recursion. Trong test thực tế, nên thu thập danh sách parts rồi assert **mỗi loại đúng số lượng** và content/relationship; nếu không thấy text part nào, đoạn `assertTrue` bên trong sẽ không được gọi và test có thể pass giả. Với MIME lạ, nested `message/rfc822` hoặc attachment `text/plain` cần phân biệt đúng theo disposition và context.

## 78. Kiểm tra attachment bằng bytes, không chỉ filename

Đối với PDF:

1. Tìm body part có `Content-Disposition: attachment`.
2. Giải mã filename theo API.
3. Đọc decoded bytes theo stream.
4. So với SHA-256 hoặc fixture bytes dự kiến.
5. Kiểm tra content type và kích thước hợp lý.
6. Mở thử file đã download trong client thật.

Đừng lưu hoặc log PDF chứa dữ liệu khách hàng thật trong kết quả test. Dùng fixture synthetic và giới hạn kích thước để test không làm đầy disk/heap.

## 79. Dùng hộp thư thử nghiệm có nhiều phiên bản message

Một chuỗi test trên cùng mailbox:

```text
[TEST] order-confirmation v7 runA
[TEST] order-confirmation v8 runB
[TEST] order-confirmation v8 dark-mode-case
```

giúp người kiểm tra so sánh trực tiếp giữa các bản. Tuy nhiên, conversation grouping có thể gom các subject giống nhau làm khó tìm; nên có run ID phù hợp hoặc cách lưu evidence riêng, không lạm dụng spoof Message-ID.

## 80. Kiểm tra URL bằng tương tác thật

Một test email đặt lại mật khẩu:

1. Gửi tới mailbox test.
2. Mở bằng client mục tiêu.
3. Nhấn link từ UI thật.
4. Xác nhận chuyển đến domain staging hợp lệ.
5. Kiểm tra redirect, consent, token expiry.
6. Đảm bảo link không tự hoàn tất hành động nhạy cảm qua GET scanner.
7. Kiểm tra khi link đã hết hạn, UI hiển thị lỗi có ích.
8. Không capture token ở screenshot/shared logs.

Nếu chỉ assert `href` trong raw HTML, bạn chưa kiểm tra quá trình link được client và security gateway xử lý.

## 81. Phân loại lỗi theo giai đoạn để tránh sửa nhầm

Một bug report “mail không hiện đúng” có thể thuộc nhiều tầng:

| Triệu chứng | Giai đoạn cần kiểm tra đầu tiên | Bằng chứng |
| --- | --- | --- |
| Không thấy email trong test mailbox | SMTP/delivery/spam placement | Provider logs, bounce, mailbox folders |
| HTML tag hiện như văn bản | MIME `Content-Type`/composer | Raw headers và decoded parts |
| Chỉ thấy plain text | `multipart/alternative`/client setting | MIME tree + client mode |
| CID image hỏng | Part mapping/CID/related tree | Content-ID, src, client screenshot |
| Remote image không tải | Client image policy/CDN/network | URL, proxy logs, settings |
| CSS table vỡ trong một client | Rendering compatibility | Template version + screenshot |
| Vietnamese subject lỗi | Charset/header encoding | Decoded subject + client |
| PDF sai filename | MIME filename encoding/Content-Disposition | Parsed filename + client |
| CTA mở URL sai | Link generation/rewriting/deep link | Destination, redirects, test click |
| Dark mode chữ chìm | Theme/style handling | Screenshot light/dark |
| Nội dung thiếu sau Forward | Client behavior/MIME resource references | Original vs forwarded message |
| OTP hết hạn khi mở link | Business token lifetime/timing | IssuedAt/expiry, client behavior |

Không thay SMTP host chỉ vì border radius bị mất, và không sửa CSS để chữa một message không có HTML part.

## 82. Quy trình triage một lỗi hiển thị

```text
User reports rendering issue
           |
           v
Identify notification + template version
           |
           v
Confirm SMTP/delivery and mailbox received
           |
           v
Inspect decoded MIME structure
           |
           +-- Invalid MIME -> fix composer/encoding
           |
           v
Reproduce on same client/version/settings
           |
           +-- Client-specific -> improve fallback
           |
           v
Compare baseline and new screenshot
           |
           v
Test representative other clients
           |
           v
Release/regression checks
```

Nếu message chứa dữ liệu cá nhân, triage qua **fixture synthetic** có cùng template/boundary values thay vì gửi lại raw MIME production cho một nhóm developer.

## 83. Bug report phải có thông tin tái hiện

Một ticket đủ hữu ích:

```text
Template: order-confirmation
Template version: 7
Fixture: long-customer-name
Client: Outlook desktop
Client version: recorded
OS: Windows
Theme: dark
Images: disabled
Viewport: narrow reading pane
Symptom: CTA label appears dark on dark background
Expected: readable CTA text with working URL
Actual: label has insufficient contrast
Evidence: restricted screenshot + sanitized MIME reference
```

Không nên tạo ticket kiểu:

> Email bị lỗi ở Outlook.

vì thiếu phiên bản và điều kiện để tái hiện.

## 84. Tái hiện từ cùng input, không đoán bằng screenshot

Ảnh chụp từ production có thể có dữ liệu động khác với staging. Để tái hiện:

1. Lấy template version và code commit.
2. Xây synthetic fixture cùng cấu trúc (tên dài, số tiền, nhiều items).
3. Render bằng cùng composer/MIME mode.
4. Gửi qua tuyến test tương tự về content processing.
5. Mở ở client đúng phiên bản và settings.
6. So sánh MIME và screenshot.

**Không cần sao chép toàn bộ email khách hàng thật để tái hiện một lỗi padding.** Chỉ giữ những đặc điểm dữ liệu liên quan.

## 85. Một client thay đổi sau update có thể tạo regression

Không chỉ thay đổi code mới gây lỗi. Mail clients có thể cập nhật rendering behavior hoặc security policy, và những email trước đó đã pass có thể bị ảnh hưởng.

Vì vậy:

- Giữ các baseline fixtures.
- Có lịch retest các clients quan trọng sau cập nhật lớn.
- Ghi client version trong kết quả.
- Đừng kết luận code template vừa deploy chắc chắn là nguyên nhân nếu lỗi xuất hiện sau client update.
- Khi bug do client behavior không thể kiểm soát, nâng fallback/giảm phụ thuộc feature đó.

## 86. Email provider có thể rewrite message

Giữa Spring Mail và mailbox:

```text
Spring-generated MIME
        |
        v
SMTP provider
        |
        +-- DKIM signing
        +-- Headers additions
        +-- Link tracking, if enabled
        +-- Security or policy processing
        |
        v
Received MIME
```

Hành vi cụ thể khác nhau theo provider/config. Nếu raw MIME do Spring tạo đúng nhưng bản nhận có link/headers đổi, kiểm tra **bản nhận thực tế** và provider configuration.

Một SMTP capture server nội bộ bypass provider có thể không tái hiện lỗi đó. Vì vậy real-client test qua **tuyến test tương ứng** rất có ích.

## 87. Tại sao preview screenshot dịch vụ bên thứ ba cũng chưa đủ?

Một rendering preview service có thể cung cấp nhiều client screenshots nhanh, hữu ích cho regression. Tuy nhiên:

- Nó có thể dùng một tập phiên bản khác môi trường người dùng.
- Một số security policies/enterprise gateways không giống test account.
- Link clicks/forward/reply không được kiểm tra đầy đủ.
- Content có thể đi qua provider khác với tuyến production.
- Upload raw email fixture có thể gây rủi ro dữ liệu nếu không được phép.

Dùng những công cụ ấy để **bổ sung** test matrix, không mặc định thay thế 100% test với mail client/device được hỗ trợ.

## 88. Đừng upload email thật lên dịch vụ preview công khai

Raw email có thể chứa:

- To/Cc/Bcc.
- OTP/reset link.
- Hóa đơn/tài liệu nhạy cảm.
- Tracking identifiers.
- Account IDs.
- Attachment bytes.

Khi sử dụng tool preview:

1. Chỉ dùng fixture synthetic.
2. Xác minh quyền và chính sách lưu trữ của tool.
3. Không dùng link một lần còn hiệu lực của người thật.
4. Không chia sẻ .eml chưa redact trong ticket public.
5. Giới hạn ai có quyền xem screenshot và test artifact.
6. Xóa artifacts theo retention policy.

An toàn dữ liệu test là một phần của chất lượng release, không phải một bước tùy chọn sau khi phát hiện leak.

## 89. Quy trình phát hành template

Một pipeline có thể:

```text
PR changes HTML/template
        |
        v
Render approved synthetic fixtures
        |
        v
Unit tests on business fields
        |
        v
MIME structure/encoding tests
        |
        v
SMTP capture test
        |
        v
Seed mailbox dispatch (approved)
        |
        v
Real client matrix
        |
        v
Review screenshots + interactions
        |
        v
Versioned release + rollback plan
```

Không phải mọi chỉnh sửa dấu câu đều cần chụp lại toàn bộ ma trận, nhưng thay đổi layout/CSS/MIME/CTA nên kích hoạt ít nhất các test có nguy cơ bị ảnh hưởng.

## 90. Cách ưu tiên các bug rendering

| Mức độ | Ví dụ | Xử lý |
| --- | --- | --- |
| Critical | Gửi nhầm dữ liệu, link đến sai tenant, OTP không đọc được | Block release, kiểm tra bảo mật/nghiệp vụ |
| High | CTA không dùng được trên client phổ biến; số tiền bị cắt | Block/review theo release criteria |
| Medium | Logo không hiện nhưng nội dung chính đầy đủ | Fix theo ưu tiên và phạm vi clients |
| Low | Radius/shadow khác mockup | Chấp nhận nếu visual policy cho phép |

Không quyết định severity chỉ bằng số pixel khác. Đánh giá **tác động người dùng và tỷ lệ client bị ảnh hưởng**.

## 91. Đặt chỗ cho fallback, không chỉ tối ưu “best case”

Một email robust:

```text
Images ON, CSS full:    Đẹp và dễ đọc
Images OFF:             Vẫn hiểu nội dung
CSS limited:            Bố cục đơn giản nhưng dùng được
Mobile narrow:          Không mất CTA và số liệu
Dark mode:              Tương phản đủ
Plain text:             Có thông tin và link tương đương
Forward:                Không mất thông tin quan trọng
```

Đây là mục tiêu thực tế hơn “mọi pixel giống thiết kế”.

## 92. Test template động: dữ liệu xấu hơn dữ liệu mẫu đẹp

Hãy tạo fixtures:

| Fixture | Kiểm tra |
| --- | --- |
| Name 1 ký tự | Khoảng trắng, salutation |
| Name rất dài | Wrapping/overflow |
| Tên tiếng Việt có dấu | UTF-8, font fallback |
| Tên đa ngôn ngữ | Unicode/RTL |
| Không có sản phẩm | Empty state |
| 1 sản phẩm | Layout ngắn |
| 50 sản phẩm | Email length/clipping |
| Giá rất lớn | Cột số, line wrap |
| Tệp tên dài có dấu | Attachment filename |
| Link dài | Wrapping/tap |
| Missing optional field | Placeholder/fallback |
| Images disabled | Nội dung không phụ thuộc ảnh |

Không dùng một fixture “John Doe / 1 item / $10” làm đại diện cho mọi email.

## 93. Email có biến dữ liệu cần escaping đúng

Ví dụ một người dùng nhập tên:

```text
An <script>alert(1)</script>
```

Không ghép trực tiếp vào HTML:

```java
String html = "<p>Xin chào " + userName + "</p>";
```

Trong mail client, script thường bị chặn, nhưng HTML injection vẫn có thể làm vỡ markup, chèn link giả hoặc gây hiển thị sai. Dùng template engine có HTML escaping đúng ngữ cảnh, validation của dữ liệu và allowlist với URL/HTML nếu cần.

**Kiểm thử HTML escaping** thuộc unit/integration layer, nhưng cũng nên mở một fixture chứa ký tự đặc biệt trong mail client để xác nhận chuỗi được hiển thị như dữ liệu, không trở thành markup ngoài ý muốn.

## 94. Link HTML cần được kiểm tra scheme và host

Nếu URL do user input tạo:

```java
helper.setText(
    "<a href='" + userUrl + "'>Xem chi tiết</a>",
    true
);
```

template có thể bị chèn URL không mong muốn hoặc bị escape sai dấu quote.

Nên:

- Xây URL từ base URL đã phê duyệt.
- Validate HTTPS scheme/host/path theo use case.
- Encode query parameters đúng.
- Dùng template engine escape attribute values.
- Không cho phép `javascript:` hoặc scheme không phù hợp.
- Test click-through trên client thật.

Không dựa vào mail client sanitization để thay thế kiểm tra đầu vào và quyền truy cập trong ứng dụng.

## 95. Unsubscribe và footer phải hoạt động trên client

Với những email cần cơ chế unsubscribe theo policy:

- Link phải nhìn thấy và dễ thao tác.
- URL không bị render hỏng.
- Không yêu cầu copy một token quá dài bằng tay.
- Quy tắc opt-out ở backend phải được thực thi, kể cả khi email được gửi qua provider khác.
- Không rò dữ liệu người nhận qua link không cần thiết.

Khi test, nhấn unsubscribe bằng seed account và xác nhận thay đổi chỉ ở test data. Không thực hiện thao tác với người dùng thật.

## 96. Một ứng dụng có thể dùng nhiều SMTP providers

Cùng template có thể đi qua:

```text
Template T-454
    |
    +-- Provider A -> recipient client
    |
    +-- Provider B -> recipient client
```

Provider có thể thêm headers, rewrite links hoặc áp policy khác nhau. Nếu production dùng hai route thực tế, nên có **một số test cases đi qua từng route**, không chỉ test trực tiếp từ local SMTP server.

Điều đó không có nghĩa gửi một bản email đến cùng khách hàng qua cả hai providers chỉ để so sánh. Dùng **test mailboxes** và test IDs riêng, tránh gửi trùng đến người dùng thật.

## 97. Regression có thể do template engine hoặc thư viện mail đổi

Khi nâng cấp Spring Framework, Jakarta Mail implementation hoặc template engine:

- Content-Type/multipart nesting có thể thay đổi khi code compose khác.
- Charset/filename behavior cần đối chiếu.
- Header encoding/line folding có thể khác.
- Resource lifecycle hoặc serialization có thể thay đổi.
- Template auto-escaping/rendering có thể đổi.

Do đó, sau upgrade có tác động tới mail layer, nên chạy lại MIME tests và một số real-client fixtures. Không suy ra “không sửa file HTML thì render chắc chắn y hệt”.

## 98. Một checklist tối thiểu cho mỗi template release

### Nội dung và quyền riêng tư

- [ ] Subject, From, Reply-To chính xác.
- [ ] Thông tin nghiệp vụ đúng ở plain text và HTML.
- [ ] Không dùng dữ liệu production trong test.
- [ ] Không lộ OTP/token/PII trong preheader hoặc screenshots.
- [ ] Các liên kết tới domain hợp lệ.
- [ ] Không gửi nhầm người nhận/Bcc.

### MIME

- [ ] HTML part có `text/html` và charset đúng.
- [ ] Plain text part có nội dung đầy đủ.
- [ ] `multipart/alternative` và các parts hợp lý.
- [ ] Inline CID khớp và ảnh có alt text.
- [ ] Attachment filename/type/bytes chính xác.
- [ ] Không dùng file temp đã bị xóa trước serialization.

### Client rendering

- [ ] Ít nhất một webmail và một mobile client quan trọng.
- [ ] Outlook/enterprise client nếu thuộc nhóm dùng.
- [ ] Dark mode và images blocked được xem xét.
- [ ] Long-text/UTF-8/boundary fixtures.
- [ ] CTA vẫn hoạt động khi CSS bị hạn chế.
- [ ] Không có nội dung chính bị cắt/tràn.
- [ ] Reply/Forward nếu use case cần.
- [ ] Accessibility cơ bản được quan sát.

### Vận hành

- [ ] Test run có template version và client metadata.
- [ ] Screenshot/evidence được lưu ở nơi được cấp quyền.
- [ ] Có phân loại mức độ lỗi và rollback plan.
- [ ] Không log raw MIME hoặc tokens.
- [ ] Không gửi hàng loạt tới người dùng thật.

## 99. Runbook: “HTML tag hiện nguyên văn trong Gmail”

Một người dùng báo:

```text
<h1>Xin chào</h1><p>Đơn hàng xác nhận</p>
```

thay vì thấy tiêu đề và đoạn văn.

**Các bước:**

1. Xác nhận client/phiên bản và email đã nhận.
2. Đọc `Content-Type` của body part bằng MIME parser.
3. Kiểm tra có phải `SimpleMailMessage` đã gửi HTML như text/plain.
4. Nếu dùng `MimeMessageHelper`, kiểm tra `setText(html, true)` hoặc `setText(plain, html)`.
5. Kiểm tra raw multipart structure.
6. Gửi lại synthetic fixture qua SMTP test và seed mailbox.
7. Xem kết quả trên ít nhất một client khác.

**Không xử lý bằng cách đổi CSS** nếu vấn đề nằm ở MIME content type.

## 100. Runbook: “Ảnh inline hiện như attachment”

Triệu chứng: logo là một attachment riêng hoặc không thấy tại chỗ trong HTML.

Kiểm tra:

- HTML có `src="cid:brand-logo"`?
- MIME part có `Content-ID: <brand-logo>` tương ứng?
- Content type là `image/png`/`image/jpeg` phù hợp?
- Part có nằm trong cấu trúc `multipart/related` hợp lý?
- `helper.setText(...)` được gọi trước `addInline(...)`?
- Image resource tồn tại đến lúc serialize/send?
- Client có chính sách hiển thị inline image khác không?

Nếu MIME hợp lệ nhưng client vẫn hiện attachment, cân nhắc fallback text/remote image theo policy và client matrix; không cố “ẩn mọi attachment” bằng metadata sai chuẩn.

## 101. Runbook: “Button mất nền trong Outlook”

1. Ghi chính xác Outlook version/OS/reading pane.
2. Kiểm tra HTML và computed-like behavior qua screenshot thực.
3. Xem button có dựa vào background CSS/property client không hỗ trợ.
4. Đảm bảo text label và `href` vẫn dùng được.
5. Thử một pattern nút dựa trên cấu trúc email-compatible, có fallback.
6. Kiểm tra lại các clients khác để không tạo regression.
7. Không bắt buộc mọi client phải có cùng border radius/shadow nếu UX vẫn đúng.

Một fix chỉ đẹp trên Outlook nhưng phá Gmail mobile chưa phải fix hoàn chỉnh.

## 102. Runbook: “Chữ biến mất trong dark mode”

Triệu chứng:

```text
Light: white button text on blue background
Dark:  white button text on lightened/white background
```

Quy trình:

- Tái hiện cùng template và client/theme.
- Kiểm tra vùng text/background bị client biến đổi.
- Đặt fallback text/background hợp lý và tránh màu quá phụ thuộc.
- Kiểm tra logo/ảnh transparent.
- Test images enabled và disabled.
- Đọc CTA dưới cỡ chữ lớn và với contrast tool khi có thể.

Không thiết kế fix chỉ dựa vào một media query dark mode nếu client mục tiêu không hỗ trợ hoặc dùng thuật toán đổi màu riêng.

## 103. Runbook: “Email đọc tốt trên desktop, tràn trên mobile”

Các nguyên nhân thường thấy:

- Container/table width cố định lớn.
- Long unbroken URL.
- Hàng dữ liệu quá nhiều cột.
- Image width/height cố định.
- Text `white-space: nowrap`.
- Button có padding/width lớn.
- Font tăng nhưng container fixed-height.

Khắc phục:

1. Tìm element gây overflow bằng fixture tối giản.
2. Dùng layout một cột hoặc stacking.
3. Cho hình co giãn trong container.
4. Rút gọn link hiển thị nhưng giữ href đúng.
5. Tóm tắt bảng dài và link tới portal khi phù hợp.
6. Test narrow viewport và large text.

Không chỉ giảm toàn bộ font xuống 10 px để “vừa màn hình”; điều đó tạo lỗi accessibility mới.

## 104. Runbook: “Tiếng Việt trong subject hoặc filename bị lỗi”

1. Xác nhận chuỗi gốc trước khi template render có đúng không.
2. Kiểm tra encoding của source/template/database.
3. Kiểm tra `MimeMessageHelper` charset.
4. Đọc decoded Subject và filename bằng Jakarta Mail APIs.
5. Kiểm tra MIME headers `Content-Type` và filename parameters.
6. Gửi synthetic fixture có ký tự có dấu qua tuyến test.
7. Mở bằng ít nhất hai mail clients đại diện.

Không “sửa” lỗi bằng cách loại bỏ toàn bộ dấu tiếng Việt nếu sản phẩm yêu cầu nội dung tiếng Việt. Tìm lỗi encoding thực sự.

## 105. Runbook: “Link từ mail mở sai trang”

1. Kiểm tra link nguồn do template render.
2. Kiểm tra HTML attribute escaping và URL encoding.
3. Kiểm tra redirect/tracking/security rewrites của provider.
4. Nhấn link trong client thật.
5. Xác minh scheme, hostname, destination và tenant access.
6. Kiểm tra deep-link behavior trên mobile nếu use case có.
7. Kiểm tra token timeout và security scanner prefetch.
8. Ghi error category, không log raw token/URL nhạy cảm.

Đừng kết luận client lỗi nếu source `href` đã bị build sai từ ứng dụng.

## 106. Runbook: “Attachment thiếu trên một số clients”

1. Kiểm tra raw MIME có attachment part không.
2. Parse `Content-Disposition`, `Content-Type` và filename.
3. So decoded file bytes với fixture.
4. Kiểm tra resource lifecycle và giới hạn kích thước.
5. Kiểm tra provider/gateway có chặn loại file không.
6. Kiểm tra ứng dụng client/OS có chính sách security block không.
7. Thử mở từ mailbox test trên client khác.
8. Nếu cần, chuyển sang một portal download có quyền.

Một attachment bị security gateway chặn **khác** với một lỗi `helper.addAttachment(...)` ở Spring.

## 107. Runbook: “Email không xuất hiện trong Inbox”

Một bug report có thể ghi “layout email không thấy”, nhưng thực ra test mailbox chưa nhận thư.

Thứ tự điều tra:

1. Producer/outbox có tạo notification không?
2. `JavaMailSender.send(...)` có được gọi và outcome ra sao?
3. SMTP/provider accepted hay rejected?
4. Có deferred/bounce/suppression feedback không?
5. Test mailbox có thư trong Spam/Other/Quarantine không?
6. From domain/SPF/DKIM/DMARC và account route có đúng không?
7. Khi đã có message, mới tiếp tục đánh giá rendering.

Không dùng một lỗi “email không thấy” để tự động sửa HTML/CSS mà không có bằng chứng.

## 108. Test với email bảo mật: OTP

Các trường bắt buộc quan sát:

```text
Subject: Mã xác minh
Preheader: Không tiết lộ quá nhiều trên lock screen
Body: Mã có cỡ chữ đủ lớn, dễ copy
Plain: Mã và thời hạn có mặt
CTA: Link đúng domain, không auto-activate
Dark: Mã vẫn tương phản
Images off: Mã vẫn hiện
Mobile: Mã không bị cắt
```

Một checklist thực hành:

- [ ] Mã không nằm trong ảnh.
- [ ] Mã không bị gộp với dấu cách/ký tự vô hình làm copy sai.
- [ ] Plain text và HTML cùng mã.
- [ ] Thời hạn được thể hiện rõ.
- [ ] OTP hết hạn thì không resend nội dung cũ một cách vô ý.
- [ ] Không log token trong screenshot hoặc test artifact public.
- [ ] Security scanner không tự hoàn tất thao tác xác thực.

## 109. Test với email hóa đơn

Kiểm tra:

- Subject và order ID đúng.
- Giá trị tiền tệ/thuế/giảm giá chính xác.
- Bảng đọc được trên mobile.
- Nội dung plain text không mâu thuẫn.
- PDF attachment đúng bytes, filename, charset.
- Link tải lại có phân quyền đúng.
- Không lộ thông tin tài chính không cần thiết trong Subject.
- Bản forward vẫn có đủ thông tin nếu use case yêu cầu.

Một email hóa đơn có bảng vỡ và tổng tiền bị che là lỗi nghiệp vụ, ngay cả khi hình ảnh trang trí vẫn đẹp.

## 110. Test với email marketing

Kiểm tra:

- Preheader có ý nghĩa.
- Logo, headline, CTA hiển thị ở dark mode/images blocked.
- Mobile single-column readable.
- Unsubscribe dễ truy cập và hoạt động theo policy.
- Không chỉ dùng ảnh để chứa nội dung khuyến mãi quan trọng.
- Không tạo tracking links sai/đứt.
- Nội dung không bị clipping khiến điều kiện áp dụng biến mất.
- Có plain text alternative phù hợp.

Không cần dùng mailing list thật để test; seed accounts và synthetic campaign fixtures đủ để phát hiện phần lớn lỗi template/interaction.

## 111. Bài tập 1 — Browser preview xanh, Outlook nút trắng

Bạn có HTML dùng `border-radius` và background CSS cho CTA. Browser preview đẹp, Outlook desktop hiện nút trắng với text trắng.

**Yêu cầu:** Xác định tầng lỗi và kế hoạch kiểm thử.

**Gợi ý:** kiểm tra client rendering, dùng nút có fallback text và background tương thích hơn, tái hiện Outlook phiên bản cụ thể, thử dark mode/Gmail/mobile để tránh regression.

## 112. Bài tập 2 — HTML và plain text khác số tiền

HTML hiển thị 120.000 VND, text/plain hiển thị 12.000 VND.

**Gợi ý:** cả hai representations phải render từ cùng validated template model. Thêm unit assertions và mở một client text-only, không chỉ xem HTML.

## 113. Bài tập 3 — CID ảnh không hiện ở mobile

Raw HTML có `cid:logo`, nhưng helper tạo Content-ID khác. Trong một client ảnh hiện, client khác không.

**Gợi ý:** parse MIME tree, kiểm tra Content-ID/reference và nesting; gửi fixture tới seed mailboxes, test images on/off. Không xem một client tự khắc phục lỗi là contract phổ quát.

## 114. Bài tập 4 — Email bị cắt cuối nội dung

Template dài, footer và link hỗ trợ ở cuối không hiện rõ trong client.

**Gợi ý:** giảm markup lặp, ưu tiên nội dung đầu, test long-content fixture và kiểm tra client clipping behavior. Không dựa vào một threshold HTML length chung cho mọi client.

## 115. Bài tập 5 — File hóa đơn tải về sai tên

`MimeMessageHelper.addAttachment("Hóa đơn 2026.pdf", ...)` được gọi, nhưng một client hiển thị filename bị lỗi encoding.

**Gợi ý:** kiểm tra nguồn UTF-8, MIME encoded filename, decoded parser và client-specific behavior; cân nhắc filename ASCII fallback nếu nhóm client cũ bắt buộc.

## 116. Bài tập 6 — Link bị mở tự động bởi scanner

Email có link GET để xác nhận giao dịch ngay, security gateway mở link trước người dùng.

**Gợi ý:** link chỉ điều hướng đến trang có bước xác nhận được bảo vệ; không thực thi side effect nhạy cảm chỉ qua GET. Test end-to-end với môi trường gateway đại diện.

## 117. Bài tập 7 — Ảnh bị chặn, email trắng

Toàn bộ thông báo là một infographic. Gmail mobile chặn ảnh nên người nhận không hiểu gì.

**Gợi ý:** chuyển nội dung chính thành HTML text + plain text, dùng ảnh minh họa/alt text, test images disabled.

## 118. Bài tập 8 — Test staging gửi tới khách hàng thật

Developer thay `To` bằng địa chỉ lấy từ database production để xem email thực tế có đúng không.

**Gợi ý:** rủi ro gửi nhầm và lộ PII. Dùng allowlist seed recipients, synthetic fixtures, test sender domain và staging URLs; đảm bảo policy chặn mọi recipient ngoài allowlist ngay trước SMTP.

## 119. Bài tập 9 — Test screenshot pass nhưng link sai

Ảnh chụp của email trùng mockup, nhưng nút “Xem đơn hàng” điều hướng sang tài khoản khác.

**Gợi ý:** screenshot không kiểm tra hành vi click/authorization. Test URL, recipient binding, tenant scope và browser destination; phân loại đây là lỗi security/logic nghiêm trọng.

## 120. Bài tập 10 — Chỉ kiểm tra một phiên bản Outlook

Team test Outlook web và kết luận Outlook desktop classic hiển thị giống nhau.

**Gợi ý:** không thể suy ra. Dùng client usage matrix, ghi phiên bản/OS và kiểm tra ít nhất bản thuộc nhóm người dùng được hỗ trợ.

## 121. Bài tập 11 — Forward làm mất logo

Email nhận ban đầu có CID image, nhưng khi user forward qua một client khác, ảnh không còn.

**Gợi ý:** test forward workflow với cùng fixture, xem MIME structure của forwarded message, đánh giá liệu logo là nội dung bắt buộc hay trang trí. Đảm bảo text chính không bị phụ thuộc hình.

## 122. Bài tập 12 — Email với tên rất dài tràn màn hình

Template test bằng “An”, production gặp tên dài nhiều từ; table/CTA bị đẩy rộng.

**Gợi ý:** boundary fixtures, responsive text wrapping, tránh fixed width/no-wrap không phù hợp, test narrow mobile và text scaling.

## 123. Những nguyên tắc cốt lõi cần ghi nhớ

1. **SMTP submission không chứng minh email render đúng.**
2. **Browser preview không phải mail client test.**
3. **MIME structure và client rendering là hai lớp kiểm tra khác nhau**.
4. **Plain text và HTML phải cùng nội dung nghiệp vụ quan trọng**.
5. **CID/attachment cần đúng Content-ID, disposition, charset và lifecycle**.
6. **Email HTML nên ưu tiên progressive enhancement và fallback**, không phụ thuộc script/modern CSS.
7. **Dark mode, images disabled và mobile width phải là test conditions có chủ đích**.
8. **Accessibility quan trọng hơn pixel-perfect** khi hai yêu cầu xung đột.
9. **CTA phải click được và dẫn tới destination đúng**, không chỉ có màu nền đẹp.
10. **Ma trận test phải dựa vào người dùng, client versions và mức độ quan trọng của template**.
11. **Seed mailbox và synthetic fixtures giúp test an toàn** mà không gửi tới khách hàng.
12. **SMTP capture kiểm tra transport/MIME**, không thay thế real-client rendering.
13. **Screenshot chỉ là một loại evidence**, cần thêm tương tác và raw MIME khi cần.
14. **Lỗi có thể do provider/security gateway rewrite**, không nhất thiết do Spring.
15. **Release template cần version, regression tests và triage có khả năng tái hiện**.

## 124. Tài liệu tham khảo để mở rộng

- Spring Framework — Email Integration: https://docs.spring.io/spring-framework/reference/integration/email.html
- Spring Boot — Sending Email: https://docs.spring.io/spring-boot/reference/io/email.html
- Jakarta Mail API: https://jakarta.ee/specifications/mail/
- W3C — Web Content Accessibility Guidelines: https://www.w3.org/WAI/standards-guidelines/wcag/

Các tài liệu về Spring/Jakarta Mail hỗ trợ kiểm tra cách tạo MIME. Chúng **không thể thay thế** việc mở email bằng các client thực mà sản phẩm đang hỗ trợ. Khả năng HTML/CSS của Gmail, Outlook, Apple Mail và các clients khác cần được đối chiếu theo phiên bản/tính năng thực tế, không coi một bảng hỗ trợ cũ là nguồn duy nhất.

## 125. Kết luận

**Không kiểm tra message ở mail client thật** là một lỗi quy trình có thể khiến một email hợp lệ về SMTP và MIME vẫn thất bại ở trải nghiệm người dùng: không đọc được, không thấy CTA, hiển thị sai số tiền, mất hình, đứt link hoặc không mở được attachment. Spring Framework Mail giúp dựng và gửi email, nhưng **không thể mô phỏng toàn bộ rendering engines, security policies và thiết bị của người nhận**.

Để tránh lỗi này, hãy xây email với **plain text fallback, HTML/MIME đúng cấu trúc, CSS có phương án dự phòng, dữ liệu UTF-8 chuẩn, text/CTA không phụ thuộc ảnh, hỗ trợ mobile và dark mode**. Sau unit tests và SMTP/MIME inspection, hãy gửi **synthetic message qua tuyến test được phép** đến các seed mailboxes, mở trên một ma trận client/OS/theme đại diện, kiểm tra nội dung, link, attachment, khả năng đọc, và ghi bằng chứng/version để tái hiện regression.

Đích đến không phải một email giống hệt từng pixel trên mọi thiết bị, mà là một email **đúng nội dung, an toàn, dễ đọc và có thể thao tác** trong những điều kiện thực tế người nhận sử dụng. Khi kiểm tra mail client trở thành một phần của quy trình phát hành template, đội ngũ có thể phát hiện lỗi trước khi khách hàng báo, và phân biệt chính xác lỗi xây MIME, lỗi gửi, lỗi client rendering hay lỗi nghiệp vụ.
