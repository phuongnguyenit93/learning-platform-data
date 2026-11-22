# HTML email khác HTML của trình duyệt như thế nào?

Một trang HTML chạy tốt trên Chrome hoặc Firefox chưa chắc hiển thị đúng khi được gửi qua email. Chẳng hạn, cùng một đoạn mã dùng `display: flex`, font tải từ web và nút có hiệu ứng hover có thể đẹp trong trình duyệt, nhưng trở thành một cột văn bản lệch hàng, mất font hoặc mất nút trên một số ứng dụng đọc thư.

Nguyên nhân là **HTML email không được xử lý như một trang web thông thường**. Email đi qua máy chủ SMTP, bộ lọc bảo mật, hệ thống lưu trữ và nhiều email client có cách hiển thị khác nhau. Các client có thể loại bỏ JavaScript, hạn chế CSS, chặn ảnh ngoài, điều chỉnh liên kết hoặc tự biến đổi màu trong dark mode. Một số phiên bản Outlook trên Windows còn dùng engine hiển thị khác với trình duyệt hiện đại.

Trong Spring Framework Mail, `MimeMessageHelper#setText(html, true)` giúp đánh dấu nội dung thư là HTML, nhưng **không làm HTML đó tương thích tự động với mọi email client**. Ứng dụng vẫn phải thiết kế markup, CSS, tài nguyên và phần plain text phù hợp với môi trường email.

## 1. Trang web và email HTML có mục tiêu khác nhau

Trang web là ứng dụng được trình duyệt chủ động tải, có thể liên tục gọi API, chạy JavaScript, thay đổi DOM và tương tác với người dùng. Email là **thông điệp đã được đóng gói và chuyển đến một ứng dụng đọc thư**, nơi người nhận có thể chỉ xem nội dung tĩnh.

| Khía cạnh | Trang HTML trong trình duyệt | HTML trong email |
| --- | --- | --- |
| Nơi hiển thị | Trình duyệt do người dùng mở trang | Gmail, Outlook, Apple Mail, ứng dụng di động, webmail, gateway preview... |
| Công cụ render | Engine trình duyệt tương đối hiện đại | Rất khác nhau giữa client và phiên bản |
| JavaScript | Thường có thể chạy theo chính sách web | Hầu hết email client chặn hoặc loại bỏ |
| CSS | Hỗ trợ rộng, cập nhật theo chuẩn web | Hỗ trợ không đồng đều, có thể bị lọc hoặc viết lại |
| Layout | Flexbox, Grid, positioning, responsive CSS | Bảng HTML và CSS inline thường an toàn hơn |
| Hình ảnh | Có thể tải cùng trang hoặc theo request | Thường có chính sách chặn/proxy/cache ảnh từ xa |
| Font | Web fonts và font hệ thống | Web fonts không nhất quán; cần fallback |
| Form và tương tác | Form, event handlers, API, SPA | Không nên dựa vào form/script bên trong email |
| Nội dung thay đổi | Có thể render lại khi dữ liệu cập nhật | Bản email đã gửi thường không cập nhật theo ứng dụng |
| Bảo mật | Web sandbox, CSP, origin... | Sanitization, link scanning, chống phishing, chặn nội dung chủ động |
| Môi trường test | Browser + thiết bị chính | Phải thử trên các email client mục tiêu |

Một chiến lược đúng với email là ưu tiên **truyền tải nội dung rõ ràng và ổn định**: tiêu đề dễ đọc, nút hành động hoạt động như liên kết, bố cục không vỡ khi thiếu ảnh và bản plain text dự phòng. Khả năng tương tác phức tạp nên nằm trên website hoặc ứng dụng sau khi người nhận bấm liên kết.

## 2. Email client có thể sửa hoặc loại bỏ HTML

Khi trình duyệt tải một trang, nhà phát triển thường kiểm soát phần lớn HTML/CSS gửi đến. Với email, markup có thể đi qua nhiều lớp:

```text
Spring Service
    |
    | render template -> HTML string
    v
MimeMessage / MimeMessageHelper
    |
    | Content-Type: text/html; charset=UTF-8
    | hoặc multipart/alternative
    v
SMTP relay / Email Service Provider
    |
    | tracking URL, anti-abuse, DKIM, chính sách nhà cung cấp
    v
Receiving MTA / security gateway
    |
    | anti-phishing, content filtering, URL rewrite
    v
Email client
    |
    | sanitize HTML, xử lý CSS, chặn/proxy ảnh,
    | điều chỉnh light/dark mode, quyết định hiển thị
    v
Nội dung người dùng nhìn thấy
```

Không phải client nào cũng thực hiện mọi bước theo cách giống nhau. Một email có thể hiển thị khác giữa bản webmail trên trình duyệt và ứng dụng desktop cùng thương hiệu. Tên sản phẩm cũng không đủ để khẳng định engine: các phiên bản Outlook trên Windows có hành vi render khác nhau, đặc biệt giữa các phiên bản cổ điển và mới.

### Vì sao không dùng JavaScript?

Đoạn HTML sau hoạt động như một trang web nhưng **không phải email đáng tin cậy**:

```html
<button onclick="confirmOrder()">Xác nhận đơn</button>
<script>
  async function confirmOrder() {
    await fetch("/api/orders/123/confirm", { method: "POST" });
  }
</script>
```

Trong email, các thẻ `script`, thuộc tính sự kiện như `onclick` hoặc API trình duyệt thường bị loại bỏ/vô hiệu hóa. URL `/api/orders/...` còn là đường dẫn tương đối, không có ngữ cảnh origin ổn định trong thư.

Thay bằng liên kết HTTPS tuyệt đối dẫn đến một trang do ứng dụng quản lý:

```html
<a href="https://example.com/orders/123">
  Xem và xác nhận đơn hàng
</a>
```

Trang đích sẽ xử lý đăng nhập, kiểm tra quyền và thao tác xác nhận. Không thực hiện hành động nhạy cảm ngay trên GET của URL vì link scanner của hệ thống bảo mật có thể truy cập liên kết trước người nhận.

## 3. CSS trong email: hỗ trợ không đồng đều

Ở trang web, lập trình viên thường viết:

```html
<link rel="stylesheet" href="/styles/app.css">
<section class="layout">
  <aside>Thông tin</aside>
  <main>Nội dung</main>
</section>
```

```css
.layout {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 24px;
}
```

Trong email, link CSS ngoài có thể bị chặn hoặc bị client bỏ qua. Các thuộc tính Grid, Flexbox, pseudo-class, selector phức tạp hay CSS variable có mức hỗ trợ không đồng đều. Một số email client giữ và áp dụng `<style>` trong `<head>`; số khác có thể lọc toàn bộ hoặc một phần. Vì vậy **không nên xem email như một ứng dụng CSS hiện đại thu nhỏ**.

### Inline CSS là lựa chọn nền tảng

Ví dụ:

```html
<p style="font-family: Arial, Helvetica, sans-serif;
          font-size: 16px;
          line-height: 24px;
          color: #222222;
          margin: 0 0 16px 0;">
  Đơn hàng của bạn đã được tiếp nhận.
</p>
```

Đặt những style quan trọng trực tiếp trên element giúp tăng khả năng tương thích với các client không giữ stylesheet như mong muốn.

Tuy nhiên, **inline CSS không bảo đảm mọi thuộc tính đều được hỗ trợ**. Một client có thể bỏ qua `box-shadow`, `position: fixed` hoặc một số giá trị CSS ngay cả khi chúng xuất hiện trong `style` của phần tử.

Một email nên được thiết kế để **mất một số hiệu ứng vẫn đọc được**.

### Bảng hỗ trợ tương đối

| CSS/kỹ thuật | Khả năng tương thích | Cách tiếp cận |
| --- | --- | --- |
| `font-family`, `font-size`, `color` | Tương đối phổ biến | Inline vào `td`, `p` hoặc `a` |
| `padding` trên ô bảng | Thường ổn định | Ưu tiên cho khoảng cách chính |
| `background-color` | Khá phổ biến nhưng có client biến đổi dark mode | Đặt trên container và cell cần thiết |
| `border` trên bảng/nút | Thường dùng được | Có fallback văn bản/link |
| `border-radius` | Không đồng nhất, đặc biệt ở một số Outlook | Chấp nhận góc vuông khi không hỗ trợ |
| `max-width` | Không đồng đều ở vài engine | Kết hợp `width` và cấu trúc bảng |
| `display: flex`, `display: grid` | Không nên làm nền tảng của layout email | Dùng table layout |
| `position: absolute/fixed` | Khả năng hỗ trợ hạn chế | Tránh dùng cho nội dung chính |
| `:hover`, `::before`, `::after` | Không đồng đều | Không phụ thuộc để truyền thông tin |
| `@media` responsive | Nhiều client hỗ trợ một phần, nhưng không phải tất cả | Thiết kế fallback không cần media query |
| `@font-face` | Hỗ trợ không ổn định | Dùng font stack hệ thống |

Bảng nói về lựa chọn thiết kế **bảo thủ để tăng khả năng tương thích**, không phải lời khẳng định mọi client luôn hỗ trợ hoặc không hỗ trợ một tính năng. Khi cần kỹ thuật cụ thể, phải thử trên client và phiên bản mà người nhận thực sự sử dụng.

## 4. Vì sao email vẫn dùng bảng HTML để bố cục?

Trên website hiện đại, dùng `<table>` chỉ để bố cục thường không được khuyến khích. Nhưng trong HTML email, **bảng vẫn là công cụ layout phổ biến** do các engine đọc thư hỗ trợ cấu trúc bảng tương đối ổn định.

Ví dụ thay vì dùng Flexbox:

```html
<div style="display: flex; gap: 24px;">
  <div style="width: 50%;">Thông tin đơn hàng</div>
  <div style="width: 50%;">Thông tin giao hàng</div>
</div>
```

Có thể dùng hai cột dựa trên bảng:

```html
<table role="presentation"
       cellpadding="0" cellspacing="0" border="0"
       width="100%" style="border-collapse: collapse;">
  <tr>
    <td width="50%" valign="top"
        style="padding: 12px; font-family: Arial, sans-serif;">
      Thông tin đơn hàng
    </td>
    <td width="50%" valign="top"
        style="padding: 12px; font-family: Arial, sans-serif;">
      Thông tin giao hàng
    </td>
  </tr>
</table>
```

`role="presentation"` giúp công nghệ hỗ trợ tiếp cận không coi một bảng dùng để bố cục như bảng dữ liệu cần đọc theo hàng/cột, khi client giữ lại thuộc tính này. Nếu là **bảng dữ liệu thật** như bảng chi tiết hóa đơn, không nên gắn `role="presentation"`: hãy dùng ngữ nghĩa bảng dữ liệu phù hợp.

### Một container email với độ rộng ổn định

Nhiều template email lựa chọn một khối nội dung ở giữa, độ rộng tối đa khoảng 600–640px (giá trị thiết kế tham khảo, không phải chuẩn bắt buộc):

```html
<table role="presentation" width="100%"
       cellpadding="0" cellspacing="0" border="0"
       style="width:100%; border-collapse:collapse;
              background-color:#f3f4f6;">
  <tr>
    <td align="center" style="padding:24px 12px;">
      <table role="presentation" width="600"
             cellpadding="0" cellspacing="0" border="0"
             style="width:100%; max-width:600px;
                    background-color:#ffffff;
                    border-collapse:collapse;">
        <tr>
          <td style="padding:32px 24px;
                     font-family:Arial,Helvetica,sans-serif;
                     font-size:16px;line-height:24px;color:#222222;">
            <h1 style="font-size:26px;line-height:32px;margin:0 0 16px 0;">
              Đơn hàng đã được xác nhận
            </h1>
            <p style="margin:0;">
              Cảm ơn bạn đã mua hàng.
            </p>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
```

Ở đây:

- Bảng ngoài chiếm toàn chiều rộng, tạo nền và padding.
- Bảng trong tạo vùng đọc có độ rộng giới hạn.
- `cellpadding="0"`, `cellspacing="0"`, `border="0"` giúp giảm khác biệt mặc định ở một số client.
- `width` HTML attribute kết hợp với CSS `width`/`max-width` tăng khả năng tương thích.
- Khoảng cách chính đặt ở `td` để ít phụ thuộc hành vi margin mặc định của `div` và `p`.

Kỹ thuật này vẫn cần thử với màn hình nhỏ. Một bảng cố định 600px có thể tràn trên client không tôn trọng `max-width`; các mẫu responsive email thường kết hợp container linh hoạt, các cột có thể xếp chồng và media query như lớp cải tiến bổ sung.

### Có phải mọi email đều cần bảng?

Không. Email chỉ có một đoạn text hoặc nội dung cực ngắn có thể dùng HTML tối giản. Bảng hữu ích khi cần **layout có kiểm soát** và hỗ trợ nhiều client, không phải một yêu cầu bắt buộc của MIME.

## 5. Thiết kế responsive cho điện thoại khác responsive web

Một trang web có thể thay đổi layout bằng media queries và Flex/Grid. Email có thêm khó khăn:

- Nhiều email client hiển thị nội dung trong một vùng nhỏ hơn toàn màn hình.
- Một số client không áp dụng đủ `@media` hoặc loại bỏ stylesheet.
- Font scaling, auto-fit, dark mode và xử lý viewport khác nhau giữa ứng dụng.
- Người nhận có thể phóng to chữ hoặc bật tùy chọn accessibility.

Với email, hãy **thiết kế bản một cột đọc được trước**, sau đó thêm hai cột hoặc bố cục nâng cao nếu nội dung thực sự cần.

Một đoạn CSS responsive nâng cao có thể dùng:

```html
<style>
  @media screen and (max-width: 600px) {
    .mobile-full-width {
      width: 100% !important;
      display: block !important;
    }
    .mobile-padding {
      padding: 20px 16px !important;
    }
  }
</style>
```

Nhưng các lớp trên chỉ có tác dụng ở client cho phép `<style>` và media query tương ứng. Nội dung vẫn phải đọc được nếu các luật này bị bỏ qua.

### Độ rộng, nút bấm và vùng chạm

- Đặt nội dung chính trong một cột; tránh văn bản dài sát mép màn hình.
- Chọn font và line-height dễ đọc, ví dụ body 16px/24px làm điểm xuất phát.
- CTA đủ lớn để người dùng điện thoại chạm dễ dàng.
- Không đặt hai liên kết quan trọng quá sát nhau.
- Tránh ảnh rộng cố định mà không có cách co lại.
- Đưa thông tin quan trọng thành văn bản; không đặt toàn bộ thông tin trong một ảnh.

Đây là nguyên tắc thiết kế trải nghiệm, không phải thông số bắt buộc của mọi email client.

## 6. Nút bấm trong email thực chất thường là liên kết

Nút HTML `<button>` có thể không phù hợp vì form/event handling bị hạn chế. CTA trong email thường là `<a>` được tạo kiểu để trông như nút:

```html
<table role="presentation" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td align="center" bgcolor="#1457a4"
        style="background-color:#1457a4; border-radius:6px;">
      <a href="https://example.com/orders"
         style="display:inline-block; padding:14px 22px;
                font-family:Arial,Helvetica,sans-serif;
                font-size:16px;line-height:20px;
                font-weight:bold;color:#ffffff;
                text-decoration:none;">
        Xem đơn hàng
      </a>
    </td>
  </tr>
</table>
```

Ngay cả khi một client bỏ qua `border-radius`, CTA vẫn là link có thể bấm. Ở những engine hạn chế `display:inline-block` hay padding trên `<a>`, có thể cần biến thể nút dành cho Outlook hoặc cấu trúc table/conditional comments. Điều quan trọng là **liên kết vẫn hiển thị và có ý nghĩa khi phần trang trí mất đi**.

Thường nên thêm link dưới dạng văn bản đầy đủ ở phần plain text:

```text
Xem đơn hàng: https://example.com/orders
```

Không phụ thuộc vào hiệu ứng hover hoặc JavaScript để hiển thị URL.

## 7. Hình ảnh: từ xa, nội tuyến và hình nhúng là những cách khác nhau

Trong website, hình ảnh thường dùng `<img src="/assets/logo.png">`. Email không có cùng origin như trang web, do đó đường dẫn tương đối có thể không hoạt động.

### 7.1. Ảnh từ URL HTTPS

```html
<img src="https://static.example.com/email/logo.png"
     width="120" height="40"
     alt="Logo Example"
     style="display:block; width:120px; height:40px; border:0;">
```

Ưu điểm: email không cần chứa bytes ảnh, dễ phân phối qua CDN. Hạn chế: client có thể **chặn, tải qua proxy, cache hoặc trì hoãn** ảnh từ xa; URL phải truy cập được công khai hoặc theo cơ chế phù hợp với email, không thể dựa vào cookie đăng nhập của website.

Một số client xử lý URL hình ảnh qua proxy hoặc chặn hoàn toàn để bảo vệ riêng tư; vì vậy IP request ảnh không đáng tin để xác định vị trí hay người mở email.

### 7.2. Ảnh nội tuyến bằng Content-ID (CID)

Ảnh cũng có thể là một MIME part với `Content-ID` và được tham chiếu qua `cid:...`:

```html
<img src="cid:brandLogo" width="120" height="40"
     alt="Logo Example">
```

Trong Spring Mail:

```java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
    message,
    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
    "UTF-8"
);

helper.setFrom("no-reply@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Chào mừng");

String plainText = "Xin chào! Tài khoản của bạn đã sẵn sàng.";
String htmlText = """
    <html><body>
      <img src="cid:brandLogo" width="120" height="40"
           alt="Logo Example">
      <h1>Chào mừng bạn!</h1>
      <p>Tài khoản của bạn đã sẵn sàng.</p>
    </body></html>
    """;

// Thiết lập phần thân trước khi thêm tài nguyên nội tuyến.
helper.setText(plainText, htmlText);
helper.addInline(
    "brandLogo",
    new ClassPathResource("mail/brand-logo.png"),
    "image/png"
);

mailSender.send(message);
```

Ví dụ giả định đã import `org.springframework.core.io.ClassPathResource`, `org.springframework.mail.javamail.MimeMessageHelper` và các kiểu cần thiết; file `mail/brand-logo.png` phải nằm trong classpath, chẳng hạn `src/main/resources/mail/brand-logo.png`.

`cid:brandLogo` trong HTML phải trùng với ID truyền vào `addInline("brandLogo", ...)`. Một số client vẫn có thể chặn hoặc không hiển thị đúng ảnh CID; vì vậy vẫn cần `alt` và nội dung văn bản.

### 7.3. Base64 data URI trong src

Một trang web có thể dùng:

```html
<img src="data:image/png;base64,iVBORw0KGgo...">
```

Nhưng nhiều email client không hỗ trợ nhất quán hoặc có thể lọc data URI do chính sách bảo mật. Không nên dựa vào cách này để hiển thị logo/CTA quan trọng.

### So sánh ảnh

| Cách nhúng ảnh | Ưu điểm | Giới hạn |
| --- | --- | --- |
| HTTPS URL | MIME nhỏ hơn, CDN dễ quản lý | Ảnh có thể bị chặn/proxy/cache; URL phải truy cập được |
| CID inline | Ảnh đi cùng MIME message | Tăng kích thước thư; hỗ trợ hiển thị tùy client |
| Data URI | Không cần URL ngoài | Email client có thể loại bỏ/không hiển thị |
| Ảnh đính kèm thông thường | Người dùng có thể tải file | Không tự trở thành ảnh trong body |

**Không để thông điệp quan trọng nằm duy nhất trong ảnh.** Ví dụ, nếu nút “Thanh toán” chỉ là hình PNG, khi ảnh bị chặn người nhận có thể không biết cần làm gì. Dùng văn bản và link thật để bảo đảm nội dung hoạt động khi thiếu ảnh.

## 8. Font chữ và tiếng Việt

Trong trình duyệt, dùng web font qua `@font-face` hoặc Google Fonts là chuyện phổ biến. Trong email, web font có thể không tải hoặc bị client bỏ qua. Nên đặt font stack có fallback:

```html
<p style="font-family: Arial, Helvetica, sans-serif;
          font-size:16px;line-height:24px;color:#222222;">
  Đơn hàng của bạn đã được xác nhận.
</p>
```

Nếu dùng font thương hiệu:

```css
font-family: 'Brand Font', Arial, Helvetica, sans-serif;
```

thì cần bảo đảm chữ vẫn dễ đọc khi client chọn Arial hoặc một font hệ thống khác. Bố cục không nên phụ thuộc cứng vào chiều rộng chính xác của một font duy nhất.

### Encoding UTF-8 trong Spring Mail

HTML có dấu tiếng Việt nên đi cùng encoding đúng:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Xác nhận đơn hàng");
helper.setText(
    "Đơn hàng của bạn đã được tiếp nhận.",
    "<html><body><h1>Đơn hàng đã được tiếp nhận</h1></body></html>"
);

mailSender.send(message);
```

Với multipart và charset UTF-8, helper tạo các phần MIME đúng mục đích, còn Jakarta Mail xử lý encoding truyền thông điệp. Có thể cấu hình thêm `spring.mail.default-encoding=UTF-8` trong Spring Boot. Không sửa thủ công MIME headers hay tự encode tiếng Việt thành những byte tùy ý nếu đã sử dụng helper.

## 9. Dark mode có thể thay đổi màu email

Nhiều email client có chế độ tối. Tuy nhiên, cách họ xử lý HTML không giống trình duyệt: có client giữ nguyên màu đã khai báo, có client chuyển đổi nền/chữ hoặc chỉ đổi một phần, và có client hỗ trợ meta/CSS dark-mode ở những mức khác nhau.

Ví dụ một email khai báo nền trắng và chữ đen:

```html
<td style="background-color:#ffffff; color:#111111;">
  Nội dung thông báo
</td>
```

Trên một số client, màu có thể được điều chỉnh; nếu logo chỉ có màu đen trên nền trong suốt, nó có thể mất tương phản khi nền trở nên tối.

Cách thiết kế:

- Giữ tương phản giữa chữ và nền đủ rõ trong cả light và dark mode.
- Dùng logo có khoảng nền hoặc biến thể phù hợp khi cần.
- Tránh đặt chữ quan trọng trực tiếp lên ảnh nền.
- Kiểm tra viền, CTA và liên kết khi màu bị client thay đổi.
- Không giả định `prefers-color-scheme` luôn hoạt động trong email.

Một số client hỗ trợ khai báo như:

```html
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
```

và CSS:

```css
@media (prefers-color-scheme: dark) {
  .email-card {
    background-color: #161616 !important;
    color: #ffffff !important;
  }
}
```

Nhưng đây là **enhancement theo client**, không phải bảo đảm đồng nhất. Mọi nội dung vẫn cần dễ đọc nếu client bỏ meta, không chạy media query hoặc tự sửa màu theo cách riêng.

## 10. Form, video, animation và nội dung tương tác

Các trang web có thể chứa form, iframe, video player, animation phức tạp và mã JavaScript. Email cần xử lý thận trọng:

| Tính năng website | Trong HTML email | Hướng thay thế |
| --- | --- | --- |
| `<script>` và event handler | Thường bị chặn hoặc loại bỏ | Đưa hành động sang trang HTTPS |
| `<form>` với input | Không ổn định, nhiều client hạn chế | CTA dẫn đến form trên website |
| `<iframe>` | Thường bị chặn | Link tới trang/video |
| `<video>` | Hỗ trợ khác nhau tùy client | Poster image + link đến trang xem video |
| Animated GIF | Có client chỉ hiện frame đầu, có client hiển thị animation | Frame đầu phải có nội dung có nghĩa |
| CSS animation | Không ổn định | Nội dung tĩnh vẫn phải đủ thông tin |
| SVG | Hỗ trợ hiển thị/nhúng không đồng nhất | PNG/JPEG phù hợp, kèm alt |
| Background image CSS | Hỗ trợ khác nhau | Nền màu và nội dung không phụ thuộc ảnh |

Ví dụ thay video player bằng hình có lời mời rõ ràng:

```html
<a href="https://example.com/tutorials/getting-started">
  <img src="https://static.example.com/email/tutorial-poster.jpg"
       alt="Xem video hướng dẫn bắt đầu"
       width="560"
       style="display:block;max-width:100%;height:auto;border:0;">
</a>
```

Nếu ảnh bị chặn, nên có một link văn bản riêng trong đoạn bên dưới để người nhận vẫn mở được video.

## 11. Kích thước email và giới hạn xử lý

Một website có thể tải nhiều asset theo nhu cầu. Email HTML được đóng gói thành nội dung message, và phần HTML quá dài có thể làm tăng thời gian tải hoặc bị một số client cắt/truncate phần hiển thị.

Các yếu tố làm email nặng hơn:

- HTML chứa markup lặp lại và nhiều bảng lồng nhau.
- CSS inline trên từng element.
- Data URI hoặc ảnh nội tuyến kích thước lớn.
- Quá nhiều nội dung ẩn để điều chỉnh responsive.
- Attachment lớn.
- Nội dung HTML gồm nhiều biến thể nhưng chưa được rút gọn.

Các ngưỡng cắt nội dung hay giới hạn dung lượng phụ thuộc email client và nhà cung cấp, có thể thay đổi theo thời gian. Không nên hard-code một con số clipping cố định làm chuẩn cho mọi khách hàng.

Thực hành phù hợp:

1. Đưa thông điệp quan trọng và CTA chính lên gần đầu thư.
2. Tránh tạo một HTML email như một bản sao đầy đủ của trang website dài.
3. Nén ảnh, giới hạn kích thước MIME và cân nhắc link tải tài liệu khi file lớn.
4. Loại bỏ CSS/markup không sử dụng khi build template nếu việc này không phá fallback.
5. Dùng một số đoạn ngắn, liên kết đến trang chi tiết nếu nội dung quá nhiều.

Gửi nội dung vừa đủ cũng giảm nguy cơ thư bị bộ lọc đánh giá bất thường và giúp người dùng di động đọc nhanh hơn.

## 12. Không nên chỉ gửi HTML: dùng multipart/alternative

Một trang web bình thường không cần phiên bản plain text của chính nó. Email thì khác: một số người dùng xem thư ở chế độ text, có client hạn chế HTML, có công nghệ hỗ trợ tiếp cận hoặc hệ thống xử lý tự động chỉ quan tâm phần plain text.

Với Spring Mail, có thể gửi **cùng một email chứa hai phiên bản**:

```text
multipart/alternative
├── text/plain; charset=UTF-8
└── text/html; charset=UTF-8
```

Ví dụ Java:

```java
package example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class AccountNoticeMailer {

    private final JavaMailSender sender;

    public AccountNoticeMailer(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendNotice(String recipient) throws MessagingException {
        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Tài khoản đã được kích hoạt");

        String plain = """
            Xin chào,

            Tài khoản của bạn đã được kích hoạt.
            Đăng nhập: https://example.com/login
            """;

        String html = """
            <!doctype html>
            <html lang="vi">
              <body>
                <h1>Tài khoản đã được kích hoạt</h1>
                <p>Bạn có thể đăng nhập tại
                  <a href="https://example.com/login">trang đăng nhập</a>.
                </p>
              </body>
            </html>
            """;

        helper.setText(plain, html);
        sender.send(message);
    }
}
```

Overload `setText(plainText, htmlText)` cần helper ở chế độ multipart. Hai chuỗi là **hai cách trình bày cùng thông điệp**, không phải hai email khác nhau. Client có thể chọn phiên bản phù hợp.

Phân biệt các overload:

| Phương thức | Ý nghĩa |
| --- | --- |
| `helper.setText(text, false)` | Một thân thư plain text |
| `helper.setText(html, true)` | Một thân thư HTML; không tự tạo plain text |
| `helper.setText(plainText, htmlText)` | Hai phiên bản alternative; yêu cầu multipart |

### Nội dung plain text phải được viết có chủ đích

Không nên chỉ xóa tất cả thẻ HTML rồi coi đó là plain text hoàn chỉnh. Nếu HTML dùng một nút “Xác nhận” với URL ẩn trong `href`, việc chỉ bỏ thẻ có thể làm **mất URL**.

Ví dụ:

```html
<a href="https://example.com/confirm">Xác nhận tài khoản</a>
```

Bản text phải chứa:

```text
Xác nhận tài khoản:
https://example.com/confirm
```

Hai phiên bản nên chứa cùng thông tin nghiệp vụ quan trọng: người nhận, hành động, thời hạn, điều kiện, liên kết và nội dung cảnh báo. Không để bản HTML và plain text mâu thuẫn.

## 13. HTML template: đừng ghép dữ liệu người dùng vào markup thô

Với website, dữ liệu động thường được framework escape theo ngữ cảnh. Khi tạo HTML email bằng Java, nếu trực tiếp nối tên khách hàng vào chuỗi HTML, ứng dụng có thể phát sinh lỗi hiển thị hoặc rủi ro injection:

```java
// Tránh ghép dữ liệu không tin cậy trực tiếp vào HTML:
String html = "<p>Xin chào " + displayName + "!</p>";
```

Nếu `displayName` chứa ký tự `<`, `>`, `&` hay đoạn HTML, kết quả có thể khác nội dung mong muốn. Trong email client, nhiều script có thể bị chặn, nhưng điều đó **không thay thế việc escape và kiểm soát dữ liệu ở server**.

### Dùng Thymeleaf cho HTML email

Có thể sử dụng Thymeleaf để render nội dung riêng cho email, ví dụ thêm dependency Spring Boot:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-thymeleaf</artifactId>
</dependency>
```

Template `src/main/resources/templates/mail/order-confirmed.html`:

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body style="margin:0;padding:0;background-color:#f3f4f6;">
  <table role="presentation" width="100%" cellpadding="0"
         cellspacing="0" border="0">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" width="600" cellpadding="0"
               cellspacing="0" border="0"
               style="width:100%;max-width:600px;background:#ffffff;">
          <tr>
            <td style="padding:28px;font-family:Arial,sans-serif;
                       font-size:16px;line-height:24px;color:#222222;">
              <h1 style="font-size:24px;margin:0 0 16px 0;">
                Đơn hàng đã được xác nhận
              </h1>
              <p>Xin chào <strong th:text="${customerName}">Khách hàng</strong>,</p>
              <p>Đơn hàng
                <strong th:text="${orderCode}">ORD-000</strong>
                đã được tiếp nhận.
              </p>
              <p><a th:href="${orderUrl}">Xem đơn hàng</a></p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
```

Java render template:

```java
import java.util.Locale;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("customerName", customerName);
context.setVariable("orderCode", orderCode);
context.setVariable("orderUrl", "https://example.com/orders");

String html = templateEngine.process("mail/order-confirmed", context);
```

`th:text` escape ký tự trong nội dung text, tránh hiểu dữ liệu như markup. Với `th:href`, cần **kiểm soát URL đích**: escape HTML attribute không tự bảo đảm URL an toàn. Trong nghiệp vụ giao dịch, nên xây link từ base URL đã được cấu hình, giới hạn domain/scheme và chỉ cho phép path/token hợp lệ.

Tiếp theo, tạo `MimeMessageHelper` với multipart rồi gọi `setText(plain, html)`. Template engine giúp tách việc trình bày email khỏi logic nghiệp vụ, đồng thời dễ quản lý nhiều ngôn ngữ và style.

### CSS inlining có thể là một bước build

Một nhóm phát triển có thể viết template với CSS trong `<style>` để dễ bảo trì, rồi dùng công cụ **CSS inliner** chuyển các luật quan trọng thành thuộc tính `style` trên từng element trước khi gửi.

Ví dụ trước khi inline:

```html
<style>
  .body-copy { font-size:16px; line-height:24px; color:#222222; }
</style>
<p class="body-copy">Nội dung xác nhận.</p>
```

Sau khi inline:

```html
<p style="font-size:16px;line-height:24px;color:#222222;">
  Nội dung xác nhận.
</p>
```

Inlining không tự sửa những CSS feature mà client không hỗ trợ. Các media query responsive cũng có thể cần giữ trong `<style>` cho những client hỗ trợ. Nếu dùng inliner, cần xác định thứ tự xử lý template, inline, sanitize và đóng gói MIME để không biến đổi sai nội dung.

## 14. Một email HTML thực tế: cấu trúc an toàn hơn

Ví dụ sau là một thân thư HTML có container bảng, phần nội dung chính, nút dạng liên kết, fallback URL và footer. Nó chỉ dùng những kỹ thuật tương đối quen thuộc với HTML email:

```html
<!doctype html>
<html lang="vi">
  <body style="margin:0;padding:0;background-color:#f3f4f6;">
    <table role="presentation" width="100%" border="0"
           cellpadding="0" cellspacing="0"
           style="width:100%;border-collapse:collapse;background-color:#f3f4f6;">
      <tr>
        <td align="center" style="padding:24px 12px;">
          <table role="presentation" width="600" border="0"
                 cellpadding="0" cellspacing="0"
                 style="width:100%;max-width:600px;border-collapse:collapse;
                        background-color:#ffffff;">
            <tr>
              <td style="padding:32px 24px 16px 24px;
                         font-family:Arial,Helvetica,sans-serif;">
                <h1 style="margin:0;font-size:24px;line-height:30px;
                           color:#1f2937;">
                  Đơn hàng đã được xác nhận
                </h1>
              </td>
            </tr>
            <tr>
              <td style="padding:0 24px;
                         font-family:Arial,Helvetica,sans-serif;
                         font-size:16px;line-height:24px;color:#374151;">
                <p style="margin:0 0 16px 0;">
                  Cảm ơn bạn. Chúng tôi đã tiếp nhận đơn hàng của bạn.
                </p>
                <p style="margin:0 0 20px 0;">
                  Mọi cập nhật sẽ được hiển thị trong tài khoản.
                </p>
                <table role="presentation" border="0"
                       cellpadding="0" cellspacing="0">
                  <tr>
                    <td bgcolor="#1457a4" align="center"
                        style="background-color:#1457a4;border-radius:6px;">
                      <a href="https://example.com/orders"
                         style="display:inline-block;padding:14px 22px;
                                font-family:Arial,Helvetica,sans-serif;
                                font-size:16px;font-weight:bold;
                                color:#ffffff;text-decoration:none;">
                        Xem đơn hàng
                      </a>
                    </td>
                  </tr>
                </table>
                <p style="margin:20px 0 0 0;font-size:13px;line-height:20px;">
                  Nếu nút không hoạt động, mở liên kết:
                  <a href="https://example.com/orders"
                     style="color:#1457a4;text-decoration:underline;">
                    https://example.com/orders
                  </a>
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:28px 24px;
                         font-family:Arial,Helvetica,sans-serif;
                         color:#6b7280;font-size:12px;line-height:18px;">
                Đây là email thông báo từ Example.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
```

Bố cục này được thiết kế để khi bỏ hình ảnh, CSS nâng cao hoặc JavaScript thì nội dung vẫn còn. Vẫn cần kiểm tra thực tế trên các client mục tiêu, đặc biệt độ rộng container, màu nút trong dark mode, khoảng cách và khả năng xuống dòng ở màn hình nhỏ.

Với production, dữ liệu người dùng và URL cá nhân hóa cần được đưa qua template đã escape, không nên nối trực tiếp vào đoạn HTML tĩnh này.

## 15. Các vấn đề về bảo mật và riêng tư riêng của HTML email

### Link tracking và hệ thống quét URL

Một ESP có thể viết lại:

```text
https://example.com/orders/123
```

thành một URL redirect để đo lượt click. Gateway phía nhận có thể tiếp tục thay URL đó bằng link của hệ thống chống phishing. Người dùng hoặc hệ thống tự động có thể truy cập liên kết trước khi người nhận thực sự bấm.

Vì vậy:

- Không coi event `clicked` là bằng chứng chắc chắn người dùng đã hành động.
- Không kích hoạt thao tác bảo mật nhạy cảm chỉ từ một GET request tới link email.
- Trang đích cần xác thực và yêu cầu hành động xác nhận phù hợp.
- Nếu dùng link có token, giới hạn mục đích, thời hạn và tránh lộ thông tin nhạy cảm trong URL.
- Không phụ thuộc vào chuỗi URL hiển thị giống hoàn toàn URL gốc, vì một số gateway có thể rewrite.

### Tracking pixel và open event

HTML email có thể chứa ảnh 1×1 để đo lượt tải:

```html
<img src="https://track.example.com/o/opaque-id"
     width="1" height="1" alt="">
```

Nhưng client có thể không tải ảnh, hoặc một proxy/privacy feature có thể tải trước. Vì vậy event “opened” là **tín hiệu tải tài nguyên**, không phải chứng minh người nhận đã đọc. Spring `MimeMessageHelper` không tự sinh tracking pixel; nếu bật tracking ở ESP cần hiểu chính sách dữ liệu và giới hạn đo lường của dịch vụ.

### Dữ liệu bí mật và HTML

Đừng đưa access token dài hạn, thông tin thanh toán nhạy cảm, bí mật SMTP hoặc nội dung nội bộ không cần thiết vào HTML hoặc custom tracking URL. Một email có thể được chuyển tiếp, lưu trong nhiều hộp thư hoặc được quét bởi hệ thống bảo mật trung gian.

HTML email không phải một vùng tin cậy để thực thi chương trình, lưu token an toàn hay quyết định quyền truy cập. Các quyết định xác thực và phân quyền phải nằm trên server.

## 16. Khả năng tiếp cận (accessibility) trong HTML email

Email có thể được đọc bằng screen reader, phóng to font, hiển thị ở chế độ tương phản cao hoặc dưới dạng plain text. Nếu chỉ tập trung vào giao diện trong một client, người nhận khác có thể gặp khó khăn.

Một số nguyên tắc:

- Viết **subject và heading rõ ràng**, không dùng toàn chữ hoa hay nhiều biểu tượng thay cho nội dung.
- Dùng heading có thứ tự hợp lý, không dùng một thẻ chỉ vì kích thước chữ.
- Gắn `alt` có nghĩa cho ảnh truyền đạt thông tin; nếu ảnh chỉ trang trí, có thể dùng `alt=""`.
- Dùng văn bản liên kết có nghĩa như “Xem đơn hàng” thay vì nhiều link đều ghi “Bấm vào đây”.
- Giữ tương phản đủ tốt; đừng dựa duy nhất vào màu sắc để biểu thị lỗi/thành công.
- Dùng bảng layout với `role="presentation"` khi thích hợp, và bảng dữ liệu với cấu trúc header khi thực sự có dữ liệu bảng.
- Tránh văn bản nằm trong ảnh; người dùng tắt ảnh hoặc dùng screen reader có thể mất thông tin.
- Cung cấp plain text thay thế cho nội dung HTML.
- Không yêu cầu hover hoặc thao tác chỉ có chuột để xem nội dung.

Ví dụ ảnh chức năng:

```html
<img src="https://static.example.com/email/status-success.png"
     width="28" height="28"
     alt="Trạng thái: thành công">
```

Nếu đoạn văn bên cạnh đã ghi “Đơn hàng thành công”, ảnh có thể chỉ mang tính trang trí với `alt=""` để tránh screen reader đọc lặp. Quyết định alt phụ thuộc vai trò thực sự của hình.

## 17. Render, thử nghiệm và khả năng tương thích

Có ba mức kiểm thử khác nhau:

| Mức | Kiểm tra | Chưa chứng minh |
| --- | --- | --- |
| Kiểm tra template HTML tại server | Dữ liệu được render và escape, URL đúng | Email client hiển thị giống trình duyệt |
| Kiểm tra MIME/SMTP | Email có `text/html`, `multipart/alternative`, ảnh inline/attachment đúng | Inbox hiển thị hoàn toàn như mong muốn |
| Kiểm tra email client thực tế | Bố cục, màu, ảnh, link, responsive, dark mode | Tất cả phiên bản tương lai cũng giống nhau |

Một chiến lược làm việc thực tế:

1. **Xác định client mục tiêu** theo người nhận, ví dụ Gmail web/mobile, Outlook desktop/web hoặc Apple Mail.
2. **Thiết kế bản text và layout một cột** để đảm bảo nội dung chính không phụ thuộc vào CSS phức tạp.
3. **Render template trên server** bằng dữ liệu giả và kiểm tra escaping, link, Unicode.
4. **Gửi email thử vào SMTP test server** để quan sát MIME, header và các phần text/HTML; không gửi nhầm email tới người thật.
5. **Gửi tới các hộp thư thử nghiệm** ở những client mục tiêu và kiểm tra thực tế ảnh bật/tắt, màn hình nhỏ, dark mode.
6. **Kiểm tra link** sau khi gateway/ESP rewrite, xác thực trang đích và hành vi của link scanner.
7. **Quan sát kết quả sau triển khai**: phản hồi từ người nhận, lỗi hiển thị, tỷ lệ bounce và tracking với những giới hạn riêng tư đã nêu.

Đừng chỉ mở `.html` trên Chrome rồi kết luận email tương thích. Chrome không đi qua pipeline SMTP/MIME/email gateway và thường hỗ trợ CSS/JS rộng hơn nhiều email client.

### Một số công cụ và cách tiếp cận

- SMTP test server trong môi trường phát triển giúp nhận email, xem MIME và tránh gửi ra Internet.
- Dùng các dịch vụ kiểm tra HTML email trên nhiều client nếu dự án cần độ tương thích cao.
- Chụp ảnh email trong các client mục tiêu sau khi thực sự giao thư để đánh giá cả ảnh, dark mode và fallback.
- Nếu có hệ thống thiết kế email, có thể dùng template/framework chuyên email để tạo table layout và CSS inline; vẫn cần kiểm tra output và khả năng bảo trì.

Không có công cụ nào bảo đảm 100% client hiện tại và tương lai giống nhau. Tiêu chí quan trọng nhất là **nội dung và hành động chính không bị mất** khi client bỏ một số style hoặc tài nguyên.

## 18. Những lỗi thường gặp khi chuyển HTML web sang email

| Biểu hiện | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Email hiện nguyên `<h1>`, `<p>` | Gửi HTML dưới dạng text/plain | `helper.setText(html, true)` hoặc `setText(plain, html)` |
| Flex/Grid bị lệch | Client không hỗ trợ layout CSS như trình duyệt | Chuyển vùng layout chính sang bảng |
| CSS không có tác dụng | Stylesheet ngoài, `<style>` hoặc selector bị lọc | Inline CSS quan trọng, dùng thuộc tính đơn giản |
| Nút không bấm được | Dùng `<button>` và JavaScript | Dùng `<a href="https://...">` thật |
| Logo biến mất | Ảnh từ xa bị chặn, URL tương đối hoặc CID sai | Dùng URL tuyệt đối/CID đúng và thêm alt |
| Ảnh trở thành attachment | Đóng gói MIME/`addInline` không đúng | Dùng `multipart/related` thích hợp, `cid` khớp |
| Tiếng Việt lỗi dấu | Charset/encoding không nhất quán | UTF-8 ở helper, template và mail config |
| Hình có chữ mất ý nghĩa khi ảnh bị chặn | Nội dung chỉ nằm trong ảnh | Đưa thông tin chính vào văn bản |
| Email rất rộng trên di động | Bảng cố định, ảnh lớn, text không xuống dòng | Container linh hoạt, thử responsive/fallback |
| Chữ/nút mất tương phản ở dark mode | Client tự chuyển đổi màu | Kiểm tra cả hai mode, thêm nền/viền hợp lý |
| Một số Outlook hiển thị khác | Engine hoặc tính năng CSS khác với browser | Dùng kỹ thuật email tương thích, thử theo phiên bản |
| Template có nội dung người dùng làm hỏng layout | Dữ liệu HTML chưa escape | Dùng template engine với escaping |
| Link click mà không có người thao tác | Security gateway tự quét URL | Không kích hoạt tác vụ nhạy cảm trên GET |
| Chỉ có HTML, không có bản text | Dùng `setText(html, true)` | Thêm plain text và dùng multipart/alternative |
| Email bị cắt phần cuối | HTML dài hoặc policy client | Rút gọn markup, đặt thông tin quan trọng lên đầu |
| Gửi thành công nhưng không thấy mail | SMTP accepted không bằng delivered/inbox | Kiểm tra provider events, policy, SPF/DKIM/DMARC |

## 19. Quy trình ra quyết định khi viết email HTML trong Spring

Trước khi tạo một template, có thể tự hỏi:

```text
Email có cần HTML không?
   |
   +-- Không --> Plain text với SimpleMailMessage
   |
   +-- Có
       |
       v
Cần bố cục ổn định trong nhiều client?
       |
       +--> Table layout + inline CSS quan trọng
       |
       v
Có hình ảnh?
       |
       +--> URL HTTPS tuyệt đối hoặc CID inline
       +--> alt + fallback khi chặn ảnh
       |
       v
Có hành động?
       |
       +--> Link <a href="https://...">
       +--> Xác nhận/ủy quyền tại website
       |
       v
Có bản plain text tương đương?
       |
       +--> multipart/alternative
       |
       v
Render bằng template có escaping
       |
       v
MimeMessageHelper + JavaMailSender
       |
       v
Thử ở SMTP test server và email clients mục tiêu
```

Chọn `MimeMessageHelper` giải quyết việc **đóng gói HTML email thành thông điệp MIME**. Thiết kế HTML email còn đòi hỏi quan tâm engine của client, CSS bị giới hạn, table layout, ảnh bị chặn, dark mode, accessibility và tính nhất quán giữa HTML với plain text.

Nếu cần giữ một nguyên tắc chính: **email HTML là tài liệu để đọc trong một môi trường nhiều hạn chế, không phải trang web có thể chạy như ứng dụng**. Hãy xây nội dung có nghĩa ngay cả khi ảnh không tải, CSS nâng cao bị bỏ và JavaScript hoàn toàn không tồn tại; sau đó bổ sung phần trình bày đẹp hơn ở những client hỗ trợ.
