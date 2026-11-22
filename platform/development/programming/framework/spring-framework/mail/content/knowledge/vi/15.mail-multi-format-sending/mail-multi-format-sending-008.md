# Kiểm tra trên mail client khác nhau

Email HTML có thể được tạo đúng trong ứng dụng Spring nhưng vẫn hiển thị khác nhau khi người nhận mở bằng Gmail, Outlook, Apple Mail hoặc ứng dụng mail trên điện thoại. Một trình duyệt web thường hỗ trợ HTML/CSS rộng hơn môi trường email; vì vậy, việc mở file HTML trong Chrome rồi thấy đẹp **không chứng minh email sẽ hiển thị giống như vậy trong inbox**.

Trong **Spring Framework Mail**, ứng dụng thường dùng template engine tạo HTML, `MimeMessageHelper` xây dựng MIME message và `JavaMailSender` gửi thư qua SMTP. Các bước này quyết định nội dung và cấu trúc thư được gửi đi. Còn cách mail client diễn giải HTML, CSS, ảnh, font và chế độ tối phụ thuộc vào từng client, phiên bản, nền tảng và thiết lập của người nhận.

Kiểm tra trên nhiều mail client là một phần của quá trình phát triển email, giúp phát hiện lỗi bố cục, mất ảnh, link khó bấm, nội dung thiếu trong bản text, lỗi tiếng Việt và khác biệt giữa desktop với mobile trước khi gửi cho người dùng thật.

## 1. Vì sao cùng một email có thể hiển thị khác nhau?

Một email HTML đi qua nhiều lớp:

```text
Ứng dụng Spring
   |
   | Template engine render HTML và text
   v
MimeMessageHelper
   |
   | MIME parts, charset, inline resource, attachment
   v
JavaMailSender / Jakarta Mail
   |
   | SMTP submission
   v
Mail server / mailbox
   |
   | Mail client nhận và diễn giải message
   v
Gmail / Outlook / Apple Mail / mobile app
   |
   v
Người dùng nhìn thấy email
```

HTML email không được trình bày trong một môi trường duy nhất. Những yếu tố có thể làm kết quả khác nhau:

- **HTML/CSS support:** client có thể bỏ qua hoặc thay đổi cách xử lý một số tag, attribute, selector hoặc thuộc tính CSS.
- **Rendering engine:** các ứng dụng có thể dùng engine khác nhau; những phiên bản Outlook trên Windows cũng không nhất thiết hoạt động giống Outlook trên web hoặc ứng dụng mới.
- **MIME structure:** client chọn phần text/HTML trong `multipart/alternative`, xử lý inline resource và attachment theo cách của nó.
- **Image policy:** ảnh từ URL bên ngoài có thể bị chặn, tải qua proxy hoặc chỉ hiện sau khi người dùng cho phép.
- **Dark mode:** client hoặc hệ điều hành có thể đổi màu nền, chữ và hình ảnh để phù hợp chế độ tối.
- **Viewport và font:** màn hình nhỏ, độ phóng đại, font hệ thống và font fallback ảnh hưởng đến chiều rộng, xuống dòng và chiều cao.
- **User settings:** chế độ đọc text, chặn ảnh, accessibility, zoom hoặc preference của người dùng làm kết quả khác.

Do đó, mục tiêu kiểm thử là bảo đảm **nội dung quan trọng vẫn đọc được và hành động chính vẫn thực hiện được** trong các client mà sản phẩm hỗ trợ. Không nên giả định mọi pixel sẽ giống hệt nhau trên tất cả môi trường.

## 2. Những mail client nên đưa vào ma trận kiểm thử

Không có danh sách cố định phù hợp cho mọi sản phẩm. Hãy chọn client theo nhóm người nhận thực tế, thiết bị và mức độ quan trọng của email.

Một ma trận khởi đầu thường bao gồm:

| Nhóm client | Ví dụ môi trường | Điều cần chú ý |
| --- | --- | --- |
| Gmail web | Gmail trong trình duyệt desktop | CSS bị giới hạn/biến đổi, ảnh ngoài, link, cấu trúc MIME |
| Gmail mobile | Ứng dụng Gmail trên Android/iOS | Chiều rộng, cỡ chữ, nút bấm, nội dung dài |
| Outlook classic trên Windows | Phiên bản Outlook desktop truyền thống | Khác biệt rendering HTML/CSS, khoảng cách và bảng |
| Outlook mới / Outlook web | New Outlook hoặc Outlook trên web | Không mặc định giống Outlook classic; cần kiểm tra riêng |
| Apple Mail trên macOS | Mail trên máy Mac | Font, dark mode, ảnh inline và layout |
| Apple Mail trên iPhone/iPad | Mail trên iOS/iPadOS | Responsive layout, vùng chạm, font và ảnh |
| Yahoo Mail | Web hoặc mobile nếu nhóm người nhận sử dụng | CSS, hình ảnh và link |
| Client doanh nghiệp khác | Ví dụ client được tổ chức triển khai | Policy bảo mật, proxy ảnh và quy tắc hiển thị riêng |

### Chọn ưu tiên theo người nhận

Ví dụ, nếu phần lớn khách hàng mở mail bằng điện thoại, hãy ưu tiên Gmail mobile và Apple Mail iOS trong vòng kiểm thử chính. Nếu email phục vụ nhân viên doanh nghiệp, Outlook trên Windows và Outlook web có thể quan trọng hơn.

Một cách phân loại:

- **Tier 1:** các client chiếm phần lớn lượt mở hoặc ảnh hưởng đến nghiệp vụ cốt lõi.
- **Tier 2:** client được một nhóm người nhận đáng kể sử dụng.
- **Tier 3:** client hiếm gặp hoặc chỉ cần kiểm tra khi có thay đổi lớn.

Không cần chạy mọi tổ hợp client/OS/browser trong mọi lần sửa. Tuy nhiên, khi thay đổi template chung, CSS layout, MIME structure hoặc inline image, cần chạy lại những môi trường chịu ảnh hưởng.

## 3. Phân biệt kiểm tra HTML, MIME và hiển thị thực tế

Một email có thể qua kiểm tra HTML nhưng vẫn lỗi khi gửi. Nên tách các lớp kiểm thử:

| Lớp | Câu hỏi | Công cụ/cách kiểm tra |
| --- | --- | --- |
| Template rendering | Biến có được thay đúng, HTML có cấu trúc hợp lệ không? | Unit test renderer, kiểm tra HTML output |
| MIME composition | Có đúng text/HTML part, charset, CID và attachment không? | Jakarta Mail inspection, SMTP capture |
| SMTP submission | Ứng dụng có gửi được đến SMTP server không? | Integration test, log và SMTP response |
| Delivery | Mail server có chấp nhận/giao thư không? | Provider event, bounce, delivery log |
| Client rendering | Người nhận nhìn thấy email ra sao? | Inbox thật trên các client/thiết bị mục tiêu |
| User interaction | Link, nút, ảnh và attachment có dùng được không? | Click test, download test, kiểm tra flow |

**SMTP gửi thành công không đồng nghĩa email hiển thị đúng.** Tương tự, một screenshot đẹp không chứng minh recipient, link hoặc attachment hoạt động.

### Không dùng browser preview làm bằng chứng duy nhất

Mở template trong Chrome có ích để kiểm tra cấu trúc cơ bản và nội dung. Nhưng trình duyệt không mô phỏng đầy đủ:

- Cách client phân tích MIME.
- Việc chọn bản `text/plain` hoặc `text/html`.
- Cách client lọc CSS/HTML.
- Policy chặn ảnh bên ngoài.
- Chế độ dark mode của ứng dụng mail.
- Khác biệt của rendering engine Outlook.
- Việc proxy hoặc cache hình ảnh.

Browser preview là một bước kiểm tra sớm; cần gửi email qua SMTP vào mailbox thử nghiệm và mở bằng client thật.

## 4. Chuẩn bị message có nhiều định dạng trong Spring Mail

Để kiểm tra nhiều client, email nên có nội dung HTML và bản text thuần tương ứng. `MimeMessageHelper.setText(plainText, htmlText)` tạo nội dung thay thế trong MIME.

### 4.1. Ví dụ dùng `MimeMessageHelper`

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class PreviewMailService {

    private final JavaMailSender mailSender;

    public PreviewMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendPreview(String recipient)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("preview@example.org");
        helper.setTo(recipient);
        helper.setSubject("Kiểm tra email trên nhiều mail client");

        String plain = """
                Xin chào,

                Đây là email dùng để kiểm tra nội dung trên nhiều mail client.
                Mã tham chiếu: PREVIEW-2026-001
                Xem chi tiết: https://app.example.org/preview/PREVIEW-2026-001
                """;

        String html = """
                <!doctype html>
                <html lang="vi">
                <head>
                  <meta charset="UTF-8">
                  <meta name="viewport"
                        content="width=device-width, initial-scale=1.0">
                  <title>Kiểm tra email</title>
                </head>
                <body style="margin:0;padding:24px;font-family:Arial,sans-serif;">
                  <table role="presentation" width="100%"
                         cellspacing="0" cellpadding="0" border="0">
                    <tr>
                      <td align="center">
                        <table role="presentation" width="600"
                               cellspacing="0" cellpadding="0" border="0"
                               style="width:100%;max-width:600px;">
                          <tr>
                            <td style="padding:24px;background:#ffffff;">
                              <h1 style="font-size:24px;line-height:1.3;">
                                Xin chào
                              </h1>
                              <p>
                                Đây là email dùng để kiểm tra trên nhiều
                                mail client.
                              </p>
                              <p>
                                Mã tham chiếu:
                                <strong>PREVIEW-2026-001</strong>
                              </p>
                              <p>
                                <a href="https://app.example.org/preview/PREVIEW-2026-001"
                                   style="display:inline-block;padding:12px 18px;
                                          background:#175cd3;color:#ffffff;
                                          text-decoration:none;">
                                  Xem chi tiết
                                </a>
                              </p>
                            </td>
                          </tr>
                        </table>
                      </td>
                    </tr>
                  </table>
                </body>
                </html>
                """;

        helper.setText(plain, html);
        mailSender.send(message);
    }
}
```

Đây là ví dụ cấu trúc để kiểm tra. Trong ứng dụng thật, nội dung nên được render từ template engine và các URL phải do backend tạo từ domain đáng tin cậy. Địa chỉ sender phải thuộc miền được SMTP provider cấp quyền.

### 4.2. Vì sao cần bản text?

`multipart/alternative` cho phép message mang nhiều cách biểu diễn cùng một nội dung:

```text
MimeMessage
└── multipart/alternative
    ├── text/plain; charset=UTF-8
    │     Xin chào...
    │     Xem chi tiết: https://...
    │
    └── text/html; charset=UTF-8
          <h1>Xin chào</h1>
          <a href="https://...">Xem chi tiết</a>
```

Mail client có thể chọn phần phù hợp với khả năng hoặc preference. Bản text không nên chỉ là một dòng “hãy xem email HTML”; nó cần truyền tải thông tin và đường dẫn quan trọng để người nhận vẫn hoàn thành được tác vụ.

Nếu chỉ gọi `helper.setText(html, true)`, message có HTML body nhưng không có bản text thay thế do ứng dụng cung cấp. Với email giao dịch, thường nên chuẩn bị cả hai.

### 4.3. Inline image và attachment

Nếu template tham chiếu ảnh bằng `cid:`, cần thêm MIME part tương ứng:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name()
);

String logoCid = "logo-" + UUID.randomUUID()
        + "@mail.example.org";
String html = renderTemplate(logoCid);

helper.setFrom("preview@example.org");
helper.setTo(recipient);
helper.setSubject("Email có inline image và attachment");
helper.setText(
        "Email có logo và một file PDF đính kèm.",
        html
);
helper.addInline(
        logoCid,
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
helper.addAttachment(
        "guide.pdf",
        new ClassPathResource("mail/guide.pdf"),
        "application/pdf"
);

mailSender.send(message);
```

Đoạn code giả định `renderTemplate(logoCid)` là hàm render HTML có tham chiếu đúng `cid:` và `recipient` đã được kiểm tra. Gọi `setText` trước `addInline` theo cách sử dụng thông thường của `MimeMessageHelper`.

Khi test, cần kiểm tra riêng:

- Inline image có hiển thị hay chỉ xuất hiện như attachment.
- CID trong HTML có khớp `Content-ID` của MIME part không.
- PDF có thể mở và byte không bị hỏng không.
- Client có hiển thị filename và media type hợp lý không.

## 5. Thiết kế HTML email để dễ tương thích

HTML email cần được thiết kế theo khả năng thực tế của các mail client. Một số kỹ thuật web hiện đại có thể không được hỗ trợ đồng đều hoặc có thể bị client loại bỏ.

### 5.1. Dùng layout đơn giản và có fallback

Đối với email cần hỗ trợ nhiều client, cấu trúc bảng HTML (`table`) thường được sử dụng cho layout chính vì tính tương thích rộng:

```html
<table role="presentation"
       width="100%"
       cellpadding="0"
       cellspacing="0"
       border="0">
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
            Nội dung email
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
```

`role="presentation"` giúp công nghệ hỗ trợ hiểu rằng bảng đang dùng cho bố cục, không phải dữ liệu dạng bảng. Khi nội dung thực sự là dữ liệu bảng, hãy dùng semantics phù hợp thay vì gắn role presentation.

Không có nghĩa phải dùng table cho mọi thành phần. Hãy dùng cấu trúc đơn giản, ít phụ thuộc vào CSS phức tạp và kiểm tra trên client mục tiêu.

### 5.2. Inline CSS cho các style quan trọng

Một số client có thể xử lý `<style>` block hoặc CSS selector khác nhau. Với những style cốt lõi như màu nền, cỡ chữ, padding và căn chỉnh, inline CSS thường là lựa chọn thực tế:

```html
<p style="margin:0 0 16px 0;
          font-family:Arial,sans-serif;
          font-size:16px;
          line-height:24px;
          color:#344054;">
  Nội dung thông báo
</p>
```

Không nên phụ thuộc vào một stylesheet bên ngoài hoặc selector phức tạp cho những thông tin thiết yếu. Nếu dùng media query để điều chỉnh mobile, hãy coi đó là cải thiện bổ sung và kiểm tra client có hỗ trợ hay không.

### 5.3. Chiều rộng và responsive

Một mẫu email thường có container giới hạn chiều rộng, ví dụ khoảng 600px, đồng thời co lại theo viewport:

```html
<table role="presentation"
       width="100%"
       cellpadding="0"
       cellspacing="0"
       border="0">
  <tr>
    <td align="center">
      <table role="presentation"
             width="600"
             cellpadding="0"
             cellspacing="0"
             border="0"
             style="width:100%;max-width:600px;">
        ...
      </table>
    </td>
  </tr>
</table>
```

Kích thước 600px chỉ là điểm khởi đầu phổ biến, không phải giới hạn bắt buộc. Hãy kiểm tra:

- Không xuất hiện thanh cuộn ngang ở màn hình điện thoại.
- Văn bản không bị thu nhỏ quá mức.
- Bảng dữ liệu dài có cách cuộn/hiển thị hợp lý.
- Nút hành động đủ lớn để chạm.
- Ảnh không vượt quá chiều rộng container.
- Nội dung vẫn đọc được khi zoom.

### 5.4. Font fallback

Không phải mail client nào cũng tải được web font hoặc cho phép font ngoài. Hãy khai báo font stack có fallback:

```html
<p style="font-family:Arial,Helvetica,sans-serif;">
  Nội dung email
</p>
```

Nếu font thương hiệu không tải được, chữ vẫn có thể hiển thị bằng font hệ thống. Không dùng một font duy nhất cho thông tin thiết yếu.

### 5.5. Button nên là liên kết thực

Nút hành động trong email thường là một thẻ anchor được tạo kiểu:

```html
<a href="https://app.example.org/orders/123"
   style="display:inline-block;
          padding:12px 18px;
          background-color:#175cd3;
          color:#ffffff;
          text-decoration:none;
          border-radius:4px;">
  Xem đơn hàng
</a>
```

Đừng dùng JavaScript, form submit hoặc event handler để thực hiện hành động trong email. Mail client thường hạn chế script và form. Một anchor HTTPS rõ ràng có thể được mở trong browser hoặc ứng dụng.

Nếu sản phẩm yêu cầu nút có hình dạng chính xác trong một số phiên bản Outlook desktop, có thể cần kỹ thuật tương thích riêng (ví dụ VML cho một số trường hợp). Chỉ thêm khi ma trận client thực tế yêu cầu và cần kiểm tra lại trên những client còn lại.

## 6. Kiểm tra nội dung khi ảnh bị chặn

Nhiều mail client có thể không tải ảnh ngoài ngay khi mở email. Người dùng cũng có thể chủ động tắt tải ảnh.

Một email không nên mất toàn bộ ý nghĩa khi ảnh không xuất hiện:

```html
<img src="https://cdn.example.org/mail/banner.png"
     alt="Ưu đãi dành cho đơn hàng của bạn"
     width="560"
     style="display:block;width:100%;max-width:560px;height:auto;"/>
```

Kiểm tra:

- `alt` mô tả ảnh có ý nghĩa khi ảnh không hiển thị.
- Không đặt mã xác nhận, giá tiền hoặc nội dung pháp lý chỉ trong ảnh.
- Link/nút không phụ thuộc vào ảnh để người nhận hiểu hành động.
- Ảnh có kích thước phù hợp, tránh file quá lớn.
- Nếu dùng CID inline, MIME part và Content-ID phải khớp.
- Nếu dùng URL ngoài, kiểm tra HTTPS và khả năng truy cập từ môi trường người nhận.

### Ảnh CID và ảnh URL ngoài

| Tiêu chí | CID inline | URL HTTPS |
| --- | --- | --- |
| Dữ liệu ảnh | Được nhúng trong MIME message | Lưu trên server/CDN |
| Cần request tải ảnh riêng | Không cần request web để lấy ảnh CID | Thường cần tải URL, có thể qua proxy/cache |
| Dung lượng email | Tăng theo kích thước ảnh và MIME encoding | Email nhẹ hơn, nhưng phụ thuộc ảnh ngoài |
| Quyền riêng tư | Không tạo request tới image server khi mở ảnh CID | Có thể phát sinh request hoặc log khi client tải ảnh |
| Khả năng chặn | Client có thể không hiển thị inline resource | Client có thể chặn ảnh ngoài |
| Cập nhật ảnh | Ảnh trong email đã gửi không thay đổi | Nội dung tại URL có thể thay đổi sau khi gửi |

Chọn cách phù hợp với mục đích và kiểm tra trên client mục tiêu. Dù dùng loại nào, thông tin quan trọng cần có dạng text.

## 7. Kiểm tra dark mode

Dark mode là nguồn khác biệt đáng kể. Một mail client có thể:

- Giữ màu gốc.
- Đổi nền sáng thành nền tối.
- Đảo hoặc điều chỉnh màu chữ.
- Thay đổi màu link.
- Xử lý ảnh nền hoặc logo khác với màu chữ.

Một thiết kế đẹp ở light mode có thể bị mất tương phản khi client tự đổi màu. Ví dụ, logo có chữ màu trắng trên nền trong suốt có thể biến mất nếu client thay nền sang trắng hoặc nền sáng.

### Những điểm cần kiểm tra

| Thành phần | Rủi ro trong dark mode | Cách thiết kế/kiểm tra |
| --- | --- | --- |
| Body background | Client thay nền, làm mất vùng phân tách | Kiểm tra cả nền gốc và nền bị chuyển |
| Text | Chữ bị đổi màu hoặc thiếu tương phản | Dùng màu dễ đọc, không truyền tải ý nghĩa chỉ bằng màu |
| Logo | Logo trong suốt hoặc đơn sắc biến mất | Chuẩn bị biến thể phù hợp hoặc nền tương phản |
| Button | Nền và chữ bị điều chỉnh độc lập | Kiểm tra chữ/nền vẫn phân biệt rõ |
| Border/divider | Đường phân cách quá mờ | Không dùng màu quá nhạt cho cấu trúc quan trọng |
| Link | Màu link bị đổi hoặc khó nhận biết | Có underline hoặc dấu hiệu khác ngoài màu |
| Ảnh nền | Có thể bị bỏ qua hoặc thay đổi | Có màu nền và nội dung fallback |

### CSS dark mode

Một số client hỗ trợ media query như `prefers-color-scheme`, nhưng mức hỗ trợ và cách áp dụng khác nhau. Ví dụ:

```html
<style>
  @media (prefers-color-scheme: dark) {
    .email-card {
      background-color: #1f2937 !important;
      color: #f9fafb !important;
    }
  }
</style>
```

Đây là enhancement cho client có hỗ trợ; không phải mọi client đều tôn trọng quy tắc này hoặc giữ nguyên màu khai báo. Style nền/chữ cơ bản vẫn cần được kiểm tra khi media query không được áp dụng.

Không nên giả định có thể ép mọi mail client giữ nguyên light mode bằng một meta tag hoặc CSS rule. Hãy kiểm tra hành vi thực tế và bảo đảm nội dung vẫn đọc được sau khi client điều chỉnh màu.

## 8. Kiểm tra bản text thuần

Với email `multipart/alternative`, kiểm tra riêng bản `text/plain`, không chỉ HTML.

Checklist nội dung:

- Subject và thông tin nhận diện email rõ ràng.
- Tên người nhận, mã tham chiếu và thông tin chính không bị thiếu.
- Các đường dẫn quan trọng xuất hiện đầy đủ, có thể sao chép.
- Không để lại HTML tag như `<p>`, `<table>`, `<a>`.
- Không để link bị cắt hoặc dính với dấu câu làm người dùng khó mở.
- Thứ tự thông tin hợp lý khi không có bố cục.
- Có cách liên hệ/hỗ trợ khi nghiệp vụ yêu cầu.
- Nội dung không phụ thuộc vào màu, icon hoặc ảnh.

Ví dụ bản text nên đọc tự nhiên:

```text
Xin chào Nguyễn An,

Đơn hàng ORD-2026-001 đã được xác nhận.
Tổng tiền: 1.250.000 ₫

Xem đơn hàng:
https://app.example.org/orders/ORD-2026-001

Trân trọng,
Bộ phận hỗ trợ
```

Tránh tạo bản text bằng cách loại bỏ tag HTML một cách máy móc nếu điều đó làm mất thứ tự hoặc URL. Tốt hơn là tạo plain-text template riêng hoặc xây text content có chủ đích.

## 9. Kiểm tra tiếng Việt, Unicode và localization

Email cần được kiểm tra với nội dung thực tế thay vì chỉ dùng chuỗi ASCII đơn giản.

Ví dụ dữ liệu thử:

```text
Tên: Nguyễn Thị Ánh
Địa chỉ: 12 Đường số 8, Phường An Khánh
Mã: DH-2026-001
Tiền: 1.250.000 ₫
Ghi chú: Giao hàng buổi chiều – gọi trước khi đến.
```

Kiểm tra:

- Body HTML có `charset=UTF-8` phù hợp.
- Bản text có charset phù hợp.
- Subject và tên hiển thị From/To có dấu được mã hóa đúng.
- Ký tự tiền tệ, dấu gạch dài, dấu nháy cong và emoji được hiển thị hợp lý.
- Không có ký tự thay thế như `�` hoặc dấu hỏi ngoài ý muốn.
- Ngày, giờ, số tiền và currency đúng locale.
- Nội dung dài hoặc tên có nhiều từ không làm vỡ layout.

`spring.mail.default-encoding=UTF-8` giúp cấu hình charset mặc định cho sender được Spring Boot tạo. Nhưng nó không sửa được chuỗi đã bị đọc sai encoding từ database, file hoặc API trước khi template render.

### Nội dung dài và bản dịch

Một template có thể trông ổn với tiếng Anh nhưng vỡ khi chuyển sang tiếng Việt, tiếng Đức hoặc ngôn ngữ có chuỗi dài. Test với:

- Tên người nhận dài.
- Mã đơn có nhiều ký tự.
- Địa chỉ dài.
- Tiêu đề email dài.
- Link có query string.
- Văn bản bản dịch dài hơn bản gốc.
- Giá trị rỗng/null và dữ liệu optional.

Không cố định chiều cao của vùng chứa văn bản nếu nội dung có thể dài. Cho phép xuống dòng và kiểm tra các từ/URL dài không làm tràn container.

## 10. Kiểm tra link và hành động của người nhận

Một email đẹp vẫn thất bại nếu nút hành động dẫn sai URL hoặc link bị cắt.

Kiểm tra từng link:

1. Scheme có phải HTTPS khi phù hợp không?
2. Host/domain có thuộc ứng dụng hoặc nhà cung cấp được tin cậy không?
3. Path và query có được encode đúng không?
4. Link có hoạt động khi mở trên desktop và mobile không?
5. Người nhận có quyền truy cập sau khi đăng nhập không?
6. Token có thời hạn và không bị lộ trong log không?
7. Link có hoạt động khi mail client thêm redirect/tracking theo cấu hình không?
8. Nội dung hiển thị của link có mô tả đúng đích đến không?

Không chỉ kiểm tra nút chính. Email có thể chứa link logo, link hỗ trợ, unsubscribe hoặc link điều khoản. Mỗi link cần được kiểm tra theo mục đích.

### Tránh URL bị cắt hoặc khó sao chép

Với bản text, đặt URL trên một dòng riêng và không ghép dấu câu ngay sau phần token nếu có thể gây nhầm. Với HTML, dùng anchor có text rõ ràng. Nếu link rất dài, hãy dùng URL do backend tạo với định dạng ổn định thay vì tự ghép một chuỗi query phức tạp trong template.

### Không dựa vào JavaScript trong email

Nút hành động nên là liên kết thực. Email không phải trang web chạy trong browser; script, form và event handler có thể bị loại bỏ hoặc vô hiệu hóa. Các hành động cần xác thực/ủy quyền nên thực hiện trên website hoặc ứng dụng sau khi người dùng mở link.

## 11. Kiểm tra attachment và inline resource

Nếu email có nhiều định dạng, cần kiểm tra không chỉ phần HTML mà cả các MIME part khác.

| Thành phần | Kiểm tra |
| --- | --- |
| `text/plain` | Nội dung đầy đủ, không có HTML markup, link đọc được |
| `text/html` | Render đúng, cấu trúc và CSS không gây lỗi |
| Inline image | CID khớp, ảnh hiển thị, alt text có ý nghĩa |
| Attachment PDF | Mở được, tên file đúng, nội dung không hỏng |
| Attachment CSV | Encoding, dấu phân cách, dòng tiêu đề và dữ liệu |
| Filename Unicode | Tên file có dấu hiển thị hợp lý trên client mục tiêu |
| Content-Type | Phù hợp với byte dữ liệu |
| Content-Disposition | Inline/attachment đúng mục đích |

### Kiểm tra MIME source

Khi client không hiển thị ảnh hoặc attachment, mở raw source của email và tìm:

```text
Content-Type: multipart/mixed
...
Content-Type: multipart/related
...
Content-Type: text/html; charset=UTF-8
...
Content-Type: image/png
Content-ID: <logo-...@mail.example.org>
Content-Disposition: inline
...
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice.pdf"
```

Đây là cấu trúc minh họa; nesting và boundary thực tế phụ thuộc MIME message. Cần xác nhận:

- HTML part có đúng `Content-Type` và charset.
- Inline CID trong HTML khớp Content-ID của part.
- Attachment có đúng filename, media type và byte.
- `Content-Transfer-Encoding` được tạo phù hợp.
- Không có hai part khác nhau dùng cùng CID.

Không chỉnh raw MIME bằng cách thay chuỗi header sau khi helper đã tạo message. Hãy sửa cách dựng message hoặc nguồn resource.

## 12. Công cụ và môi trường kiểm thử

Không có một công cụ duy nhất thay thế được mọi lớp kiểm tra. Có thể kết hợp:

| Công cụ/loại công cụ | Mục đích | Giới hạn cần hiểu |
| --- | --- | --- |
| Unit test template renderer | Kiểm tra dữ liệu được render đúng và không thiếu biến | Không mô phỏng mail client |
| Jakarta Mail inspection | Kiểm tra MIME parts, charset, CID, attachment | Không kiểm tra hình thức hiển thị |
| GreenMail | SMTP test server và kiểm tra message trong integration test | Không render như Gmail/Outlook |
| Mailpit hoặc MailHog | Bắt email trong môi trường local/staging và xem message | Preview không thay thế client thật |
| Real mailbox test accounts | Gửi vào Gmail/Outlook/Apple Mail thật | Cần quản lý tài khoản và dữ liệu thử |
| Email rendering preview service | Xem trước trên nhiều client/version | Phụ thuộc dịch vụ, gói và môi trường mô phỏng |
| HTML validator/linter | Phát hiện lỗi markup cơ bản | HTML hợp lệ chưa chắc được mọi client hiển thị giống nhau |
| Link checker | Kiểm tra URL và response | Cần test cả quyền truy cập và flow nghiệp vụ |

### 12.1. Local SMTP capture

Trong lúc phát triển, không nên gửi email thử tới khách hàng thật. Có thể cấu hình ứng dụng gửi đến SMTP server cục bộ như Mailpit hoặc MailHog. Công cụ này nhận message để xem:

- Subject, From, To.
- Bản HTML và text.
- Raw MIME.
- Inline image và attachment.

Điều này giúp phát hiện lỗi cấu trúc trước khi gửi ra mailbox thật. Tuy nhiên, giao diện preview của công cụ bắt thư không đại diện cho tất cả mail client.

### 12.2. Integration test với GreenMail

GreenMail có thể dùng như SMTP server trong test để nhận message do `JavaMailSender` gửi. Sau đó test có thể kiểm tra recipient, subject, MIME multipart và nội dung.

Ví dụ ở mức ý tưởng:

```java
@Test
void sendsHtmlAndPlainTextAlternatives() throws Exception {
    // Arrange:
    // - Khởi động SMTP test server.
    // - Cấu hình JavaMailSender trỏ tới server đó.
    // - Gọi service gửi email.

    // Assert:
    // - Có đúng một message được nhận.
    // - Có text/plain và text/html parts.
    // - Plain text có URL hành động.
    // - HTML có nội dung đã render.
    // - Inline CID trỏ tới part có Content-ID tương ứng.
}
```

Đây là khung kiểm thử, không phải một test class hoàn chỉnh vì cấu hình GreenMail phụ thuộc phiên bản và cách khởi tạo của dự án. Điểm cần giữ là kiểm tra **MIME structure** một cách tự động, không chỉ xác nhận method gửi không ném exception.

### 12.3. Gửi vào mailbox thật

Để kiểm tra rendering, cần gửi email vào các mailbox thử nghiệm được đăng nhập trên client mục tiêu. Có thể tạo địa chỉ test riêng cho:

- Gmail web.
- Gmail mobile.
- Outlook classic trên Windows.
- Outlook web hoặc ứng dụng mới.
- Apple Mail trên macOS/iOS.
- Yahoo hoặc client khác theo đối tượng người nhận.

Mỗi lần gửi nên có một mã preview duy nhất để tìm đúng email và đối chiếu phiên bản template.

## 13. Xây dựng ma trận test có thể lặp lại

Một ma trận tốt ghi rõ client, thiết bị, chế độ và các tình huống cần kiểm tra. Không chỉ ghi “đã test Gmail”.

Ví dụ:

| Test ID | Client | Thiết bị/chế độ | Nội dung cần kiểm tra |
| --- | --- | --- | --- |
| C01 | Gmail | Web, desktop, light | Layout, font, link, ảnh |
| C02 | Gmail | Android, light | Responsive, vùng chạm, xuống dòng |
| C03 | Gmail | iOS, dark | Màu sắc, button, ảnh |
| C04 | Outlook classic | Windows, light | Bảng, padding, button, font |
| C05 | Outlook web | Browser, dark | CSS, ảnh, link |
| C06 | Outlook mới | Desktop, light | Khác biệt với classic/web |
| C07 | Apple Mail | macOS, light | Layout, CID, font |
| C08 | Apple Mail | iPhone, dark | Responsive, dark mode, text |
| C09 | Yahoo Mail | Web/mobile nếu thuộc audience | CSS và ảnh |
| C10 | Text-only view | Client hỗ trợ chế độ text | Bản text và URL |

Đây là ví dụ ma trận; thay các client bằng nhóm người nhận thật của sản phẩm.

### Các trường hợp nội dung cần có trong mỗi vòng test

- Dữ liệu bình thường.
- Tên và địa chỉ dài.
- Giá trị optional bị thiếu.
- Ký tự tiếng Việt, ký hiệu tiền tệ và ký tự đặc biệt.
- Nội dung dài nhiều đoạn.
- Ảnh bị chặn.
- Dark mode.
- Màn hình hẹp.
- Link chính và link phụ.
- Attachment có tên file dài hoặc Unicode.
- Email chỉ có text nếu ứng dụng có đường gửi text-only.

### Ghi kết quả rõ ràng

Mỗi kết quả nên ghi:

| Trường | Ví dụ |
| --- | --- |
| Template version | `order-confirmation/v4` |
| Test data ID | `preview-case-long-name-02` |
| Client | Gmail mobile |
| Platform/version | Android, phiên bản app được ghi tại thời điểm test |
| Mode | Dark |
| Result | Pass / Fail / Needs review |
| Finding | Button tràn chiều rộng ở màn hình nhỏ |
| Screenshot/reference | Đường dẫn artifact nội bộ hoặc ID |
| Retest | Ngày/commit/template version đã sửa |

Ghi version client và template giúp kết quả có thể diễn giải được. Ảnh chụp màn hình không có metadata thường khó biết đã được tạo từ template nào.

## 14. Quy trình kiểm thử từ local tới production

Một pipeline thực tế có thể chia thành các bước:

```text
1. Build mail model và render template
          |
          v
2. Unit test HTML + plain text
          |
          v
3. Kiểm tra MIME structure
          |
          v
4. Gửi tới local SMTP capture
          |
          v
5. Gửi staging tới mailbox test
          |
          v
6. Mở trên client/thiết bị mục tiêu
          |
          v
7. Click link, tải attachment, kiểm tra nội dung
          |
          v
8. Ghi kết quả, sửa và retest
          |
          v
9. Phát hành template
```

### Bước 1 — Chuẩn bị dữ liệu đại diện

Không chỉ dùng một người tên `John`. Tạo fixture có:

- Tên tiếng Việt có dấu.
- Tên rất dài.
- Mã đơn và số tiền.
- Giá trị null/optional.
- Nội dung có dấu `&`, `<`, `>` trong dữ liệu text.
- URL hợp lệ với query parameter.
- Ngày giờ theo timezone và locale cần hỗ trợ.

### Bước 2 — Render template

Kiểm tra template engine thay biến đúng, điều kiện hiển thị đúng và không để sót expression như `th:text` trong output cuối. Kiểm tra escaping cho dữ liệu người dùng và URL được tạo từ nguồn tin cậy.

### Bước 3 — Kiểm tra MIME

Đảm bảo message có `text/plain` và `text/html` nếu yêu cầu. Kiểm tra charset, Content-ID, attachment filename, media type và cấu trúc multipart.

### Bước 4 — SMTP capture

Gửi vào Mailpit/MailHog/GreenMail hoặc môi trường tương đương để kiểm tra message đã được ứng dụng tạo. Không gửi dữ liệu nhạy cảm thật vào môi trường local.

### Bước 5 — Mailbox thật

Gửi staging message tới các account test. Dùng subject hoặc preview ID riêng để tránh nhầm với email khác.

### Bước 6 — Kiểm tra hình ảnh và tương tác

Mở email trên từng client. Kiểm tra link chính, link hỗ trợ, ảnh, attachment, text-only view và dark mode.

### Bước 7 — Ghi nhận và retest

Chụp ảnh lỗi, ghi client/version/template version, sửa template hoặc model, rồi gửi lại cùng fixture để xác nhận.

## 15. Những lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| HTML đẹp trong browser nhưng vỡ trong Outlook | CSS/layout không được client hỗ trợ như browser | Dùng cấu trúc email tương thích và test Outlook thật |
| Nội dung bị tràn ngang trên điện thoại | Container hoặc bảng có chiều rộng cố định | Dùng layout co giãn, kiểm tra viewport hẹp |
| Button mất nền hoặc padding | Client xử lý style trên anchor khác nhau | Dùng link thật, style đơn giản; cân nhắc fallback riêng nếu cần |
| Ảnh không hiện | Ảnh ngoài bị chặn hoặc CID không khớp | Kiểm tra policy ảnh, MIME part, Content-ID và alt text |
| Logo biến mất trong dark mode | Ảnh trong suốt/đơn sắc thiếu tương phản | Chuẩn bị biến thể logo hoặc nền phù hợp |
| Chữ tối trên nền tối | Client tự điều chỉnh màu | Kiểm tra dark mode, đảm bảo tương phản |
| Font khác thiết kế | Font web không được tải hoặc không hỗ trợ | Dùng font stack có fallback |
| Khoảng cách giữa các đoạn khác nhau | Margin/CSS bị diễn giải khác | Kiểm tra spacing trên client mục tiêu, dùng cấu trúc đơn giản |
| Bản text không có URL | Plain text được tạo sơ sài hoặc chỉ strip HTML | Tạo text template có chủ đích |
| Tiếng Việt bị lỗi dấu | Charset đầu vào hoặc MIME không nhất quán | Kiểm tra UTF-8 từ nguồn đến MIME |
| Attachment không mở được | Byte sai, media type/encoding sai | Kiểm tra byte nguồn và MIME part |
| CID xuất hiện như link hoặc chữ | HTML dùng sai scheme hoặc part không tồn tại | Dùng `src="cid:..."` và `addInline` tương ứng |
| Email đến nhưng link không hoạt động | URL sai, token hết hạn hoặc quyền không hợp lệ | Kiểm tra flow backend và URL thực tế |
| Một client hiển thị ảnh, client khác không | Khác biệt hỗ trợ CID/remote images | Xem raw MIME và policy client; giữ nội dung text |
| Email có hai bản nội dung lặp | MIME alternative/HTML được dựng sai | Kiểm tra cấu trúc `multipart/alternative` |

### 15.1. Lỗi layout do CSS

Không nên giải quyết mọi khác biệt bằng cách thêm nhiều CSS override. Trước tiên, xác định thành phần nào gây lỗi:

- Container width.
- Table cell padding.
- Margin của heading/paragraph.
- Line-height.
- Image width/height.
- Font fallback.
- CSS selector bị client bỏ qua.

Ưu tiên sửa cấu trúc hoặc style đơn giản nhất có thể, sau đó retest trên các client bị ảnh hưởng.

### 15.2. Lỗi ảnh

Phân biệt:

- Ảnh URL ngoài không tải do policy hoặc URL.
- Ảnh CID không có part tương ứng.
- CID đúng nhưng MIME part có byte hoặc media type sai.
- Client hiển thị ảnh nhưng CSS kích thước làm ảnh biến mất/tràn.

Raw MIME giúp xác định part có tồn tại không; client thật giúp xác định cách hiển thị.

### 15.3. Lỗi giao thư không phải lỗi rendering

Nếu SMTP server từ chối, recipient sai hoặc thư bị bounce, vấn đề nằm ở submission/delivery. Không sửa CSS để xử lý lỗi SMTP. Theo dõi response, bounce và provider event riêng với kết quả visual test.

## 16. Accessibility và khả năng đọc

Kiểm thử trên nhiều client cũng nên xem xét khả năng tiếp cận:

- Dùng heading theo thứ tự hợp lý.
- Dùng `alt` có ý nghĩa cho ảnh thông tin.
- Dùng `alt=""` cho ảnh trang trí nếu phù hợp.
- Không truyền tải trạng thái chỉ bằng màu.
- Link có tên mô tả hành động, tránh nhiều link đều ghi “Click here”.
- Độ tương phản chữ/nền đủ rõ.
- Cỡ chữ và line-height đọc được trên màn hình nhỏ.
- Bảng dữ liệu có cấu trúc phù hợp, không dùng layout table như bảng nội dung.
- Bản text thuần vẫn truyền tải nội dung cốt lõi.

Ví dụ link có ý nghĩa:

```html
<a href="https://app.example.org/orders/123">
  Xem chi tiết đơn hàng ORD-2026-001
</a>
```

Nội dung link rõ ràng hơn so với:

```html
<a href="https://app.example.org/orders/123">Click here</a>
```

Nếu ảnh là logo, `alt` nên mô tả thương hiệu/tên tổ chức khi đó là thông tin có ích. Nếu logo chỉ lặp lại tên công ty đã có ngay cạnh, có thể chọn alt phù hợp để tránh đọc lặp.

## 17. Deliverability khác với rendering

Một email có thể hiển thị hoàn hảo nhưng vẫn vào spam hoặc không được giao. Ngược lại, email được giao thành công có thể bị lỗi layout.

| Vấn đề | Lớp xử lý |
| --- | --- |
| SPF, DKIM, DMARC | Xác thực domain và chính sách gửi |
| SMTP AUTH/TLS | Kết nối và xác thực với mail server |
| Bounce, quota, rate limit | Delivery/provider |
| Spam filtering/reputation | Deliverability |
| HTML/CSS, dark mode, responsive | Client rendering |
| MIME alternative/CID/attachment | Message composition và client parsing |

Không dùng kết quả “đã nhận được trong inbox test” để kết luận mọi người nhận sẽ nhận được thư. Môi trường test có thể khác reputation, domain, nội dung và chính sách lọc của production.

Khi kiểm thử staging, nên dùng domain/subdomain và mailbox được kiểm soát, tuân thủ chính sách gửi của nhà cung cấp. Tách test deliverability khỏi test visual để biết lỗi thuộc tầng nào.

## 18. Lưu screenshot và quản lý regression

Sau mỗi lần test, lưu ảnh chụp theo một quy ước:

```text
email-preview/
  order-confirmation/
    template-v4/
      gmail-web-light.png
      gmail-android-light.png
      outlook-classic-windows.png
      outlook-web-dark.png
      apple-mail-iphone-dark.png
```

Khi template thay đổi:

1. Render cùng bộ dữ liệu fixture.
2. Gửi lại cùng các mailbox test.
3. So sánh ảnh mới với ảnh đã duyệt.
4. Ghi nhận khác biệt có chủ đích và regression.
5. Lưu kết quả cùng commit/template version.

Screenshot comparison có thể hỗ trợ phát hiện thay đổi bố cục, nhưng khác biệt do font, anti-aliasing, thời gian, ảnh động hoặc phiên bản client có thể tạo ra nhiễu. Không nên chỉ dựa vào pixel diff tự động để quyết định pass/fail; cần xem xét bằng mắt và kiểm tra hành vi.

## 19. Checklist kiểm tra trước khi phát hành

### Nội dung và định dạng

- [ ] Subject, From, To và nội dung chính đúng.
- [ ] Có bản `text/plain` nếu email cần hỗ trợ nhiều định dạng.
- [ ] Bản text chứa link và thông tin quan trọng.
- [ ] HTML không để sót biến template hoặc placeholder.
- [ ] Dữ liệu động được escape đúng ngữ cảnh.
- [ ] Tiếng Việt, currency, ngày giờ và locale hiển thị đúng.

### Layout và hình ảnh

- [ ] Không tràn ngang trên mobile.
- [ ] Heading, paragraph và bảng đọc được.
- [ ] Button và link có thể chạm/click.
- [ ] Ảnh có kích thước hợp lý và alt text.
- [ ] Email vẫn hiểu được khi ảnh bị chặn.
- [ ] Dark mode không làm mất chữ hoặc logo.
- [ ] Font fallback hoạt động.

### MIME và attachment

- [ ] MIME alternative có đúng text/HTML part.
- [ ] Charset phù hợp với byte nội dung.
- [ ] CID trong HTML khớp Content-ID.
- [ ] Attachment có tên và media type đúng.
- [ ] File mở được và không hỏng.
- [ ] Không có MIME part trùng/lỗi không cần thiết.

### Client và tương tác

- [ ] Đã mở trên các client Tier 1.
- [ ] Đã kiểm tra desktop và mobile theo audience.
- [ ] Đã kiểm tra light và dark mode nếu được hỗ trợ.
- [ ] Link chính và link phụ hoạt động.
- [ ] Recipient có quyền truy cập sau khi mở link.
- [ ] Screenshot và kết quả được lưu cùng template version.

### Delivery

- [ ] SMTP submission staging thành công.
- [ ] Không có lỗi bounce/recipient không hợp lệ trong test.
- [ ] Domain và cấu hình xác thực gửi được kiểm tra theo môi trường.
- [ ] Log ghi nhận notification/template version mà không lộ dữ liệu nhạy cảm.

Checklist này dùng cho quy trình phát hành; không thay thế kiểm thử chuyên sâu cho email có yêu cầu pháp lý, bảo mật hoặc nghiệp vụ đặc biệt.

## 20. Một quy trình thực tế cho nhóm phát triển

Để việc kiểm tra lặp lại được, nhóm có thể thống nhất các đầu vào và đầu ra:

**Đầu vào:**

- Template key và version.
- Data schema version.
- Fixture đại diện.
- Locale.
- Danh sách client Tier 1/Tier 2.
- Cấu hình MIME (text, HTML, inline, attachment).

**Đầu ra:**

- HTML và plain text đã render.
- Raw MIME của message staging.
- Screenshot theo client/thiết bị.
- Kết quả link/attachment test.
- Findings và trạng thái retest.
- Version/commit đã được duyệt.

Một thay đổi chỉ ảnh hưởng subject hoặc plain text có thể không cần chụp lại toàn bộ ma trận visual. Thay đổi layout, CSS, inline image, MIME structure hoặc font cần chạy lại các client liên quan. Khi thay đổi shared template, cần đánh giá phạm vi ảnh hưởng tới mọi email dùng chung thành phần đó.

## 21. Tình huống tự luyện

### Tình huống A: email đẹp trong Gmail web nhưng lỗi trong Outlook classic

**Hướng xử lý:** xác định vùng bị lỗi (width, table, padding, font hay button), xem raw MIME để chắc chắn message không bị lỗi cấu trúc, sửa HTML/CSS theo tập tính năng tương thích và retest Outlook classic cùng một client khác để tránh regression.

### Tình huống B: ảnh banner không hiện trên mobile

**Hướng xử lý:** xác định ảnh là CID hay URL ngoài. Với URL, kiểm tra policy tải ảnh và URL HTTPS; với CID, đối chiếu `src` và `Content-ID`. Kiểm tra kích thước ảnh, `width`, `height`, `max-width` và alt text.

### Tình huống C: email hiển thị tốt ở light mode nhưng chữ biến mất ở dark mode

**Hướng xử lý:** xem client có tự đổi màu hay áp dụng media query không; điều chỉnh màu nền/chữ và kiểm tra button, logo, border. Không giả định CSS dark-mode được mọi client hỗ trợ.

### Tình huống D: người nhận bật chế độ chỉ đọc text

**Hướng xử lý:** kiểm tra `text/plain` có đủ thông tin và URL hay không. Không dựa vào HTML để truyền tải mã xác nhận hoặc hành động quan trọng.

### Tình huống E: SMTP test thành công nhưng khách hàng báo email không có attachment

**Hướng xử lý:** kiểm tra raw MIME xem part có tồn tại không, đúng `Content-Disposition`, filename, media type và byte không. Sau đó thử client mục tiêu. Nếu part không có trong raw message, lỗi ở bước tạo message; nếu có nhưng client không trình bày đúng, tiếp tục kiểm tra cách client xử lý.

### Tình huống F: template mới làm bản dịch tiếng Việt bị tràn

**Hướng xử lý:** dùng fixture có chuỗi dài, cho phép text xuống dòng, tránh chiều cao cố định và kiểm tra trên mobile. Không chỉ test bản tiếng Anh ngắn.

### Tình huống G: email được giao nhưng nút dẫn tới trang báo không có quyền

**Hướng xử lý:** xác minh URL được tạo từ domain/path đúng, recipient đúng, token hoặc session hợp lệ và backend kiểm tra quyền. Đây là lỗi nghiệp vụ/link flow, không phải lỗi rendering.

## 22. Kết luận

Kiểm tra email trên các mail client khác nhau là bước xác nhận rằng nội dung do Spring tạo ra vẫn hữu ích khi được diễn giải trong môi trường thật của người nhận. Cần kiểm tra riêng template HTML, bản text, MIME structure, SMTP submission, delivery và hiển thị trên client. Một browser preview hoặc một lần gửi thành công không thể thay thế toàn bộ các bước đó.

Với Spring Framework Mail, hãy tạo `text/plain` và `text/html` phù hợp bằng `MimeMessageHelper`, kiểm tra CID/attachment trong raw MIME và gửi staging tới mailbox trên các client thuộc nhóm người nhận. Dùng HTML/CSS đơn giản, fallback font, alt text, link HTTPS rõ ràng và nội dung không phụ thuộc vào ảnh. Ma trận kiểm thử nên bao gồm desktop/mobile, light/dark mode, dữ liệu tiếng Việt và trường hợp ảnh bị chặn. Lưu screenshot cùng template version và retest các client bị ảnh hưởng sau mỗi thay đổi. Như vậy, nhóm có thể phát hiện regression sớm và phát hành email nhất quán hơn cho người dùng.
