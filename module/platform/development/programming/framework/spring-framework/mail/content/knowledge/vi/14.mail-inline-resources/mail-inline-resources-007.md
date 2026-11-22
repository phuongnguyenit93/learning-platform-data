# Mail client không hỗ trợ inline và phương án dự phòng

Một ứng dụng Spring Boot gửi email HTML có logo công ty, hình minh họa trạng thái đơn hàng và một liên kết “Xem chi tiết”. Nhóm phát triển dùng **inline resource** với Content-ID (CID), nên HTML tham chiếu hình bằng `src="cid:company-logo"`. Trên một số email client, logo hiển thị đúng; trên một số client khác, hình bị ẩn, xuất hiện thành attachment riêng hoặc không được trình bày như mong muốn.

Đây là một đặc điểm quan trọng của email: **ứng dụng gửi có thể tạo MIME message hợp lệ, nhưng không thể ép mọi mail client hiển thị nội dung giống nhau**. Mỗi client có chính sách tải hình, cách xử lý MIME, bộ máy HTML/CSS và giao diện riêng. Inline resource giúp đính kèm tài nguyên vào email và tham chiếu nó từ HTML; nó không bảo đảm hình sẽ luôn hiện ở đúng vị trí trên mọi thiết bị.

Trong **Spring Framework Mail**, `MimeMessageHelper.addInline(...)` được dùng để thêm resource inline. Để nội dung vẫn hữu ích khi inline không được hiển thị, cần thiết kế **graceful fallback**: văn bản phải tự truyền đạt thông tin, ảnh có `alt`, CTA là liên kết thật, có bản `text/plain` và chỉ chuyển ảnh thành attachment hoặc remote resource khi điều đó có giá trị với người nhận.

## 1. Inline resource hoạt động như thế nào?

Một inline image thường được đưa vào MIME message dưới dạng một body part có `Content-ID`. HTML tham chiếu part đó bằng URL có scheme `cid:`.

Ví dụ HTML:

```html
<p>Chào mừng bạn đến với dịch vụ.</p>
<img src="cid:company-logo" alt="Logo công ty">
```

Phần MIME tương ứng có thể được biểu diễn khái niệm như sau:

```text
Content-Type: multipart/related

--related-boundary
Content-Type: text/html; charset=UTF-8

<p>Chào mừng bạn đến với dịch vụ.</p>
<img src="cid:company-logo" alt="Logo công ty">

--related-boundary
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <company-logo>
Content-Disposition: inline

[byte ảnh được biểu diễn bằng base64]
--related-boundary--
```

Đây là sơ đồ minh họa; Jakarta Mail tạo boundary và header cụ thể. Khi email client xử lý MIME, nó tìm body part có Content-ID tương ứng và có thể hiển thị byte ảnh tại vị trí `cid:company-logo` trong HTML.

Các thành phần:

| Thành phần | Vai trò |
|---|---|
| `src="cid:company-logo"` | Tham chiếu tài nguyên từ HTML. |
| `Content-ID: <company-logo>` | Định danh MIME part để client tìm tài nguyên. |
| `Content-Type: image/png` | Mô tả định dạng byte của ảnh. |
| `Content-Transfer-Encoding: base64` | Cách biểu diễn byte trong MIME message. |
| `Content-Disposition: inline` | Gợi ý nội dung được dùng trong thân thư. |
| `alt="Logo công ty"` | Văn bản thay thế nếu ảnh không hiển thị hoặc cho công nghệ hỗ trợ. |

**CID là cơ chế liên kết các MIME part trong cùng email**, không phải URL công khai trên Internet. Người nhận không cần tải logo từ website để xem hình inline; dữ liệu ảnh đã nằm trong message.

## 2. Vì sao mail client có thể không hiển thị inline?

Một email client có thể nhận đúng MIME message nhưng cách trình bày vẫn khác nhau. Một số nguyên nhân thường gặp:

| Hiện tượng | Nguyên nhân có thể |
|---|---|
| Hình không xuất hiện | Client không tìm thấy CID khớp, MIME structure không như mong đợi, part bị lọc hoặc lỗi xử lý. |
| Hiện biểu tượng ảnh lỗi | Resource thiếu, Content-ID không khớp hoặc dữ liệu ảnh không đọc/giải mã được. |
| Hình xuất hiện ở cuối email như attachment | Client chọn cách trình bày part inline như một tệp đính kèm. |
| Hình remote bị ẩn | Client chặn tải ảnh ngoài vì quyền riêng tư hoặc chính sách bảo mật. |
| Hình bị co giãn/cắt | CSS, thuộc tính kích thước hoặc layout không được hỗ trợ giống nhau. |
| Chỉ có chữ thay thế | Client không tải hoặc không render ảnh; `alt` có thể được hiển thị. |
| HTML không hiển thị đúng | Client làm sạch markup, giới hạn CSS hoặc chọn bản text/plain. |

Những vấn đề này có thể đến từ client, gateway, proxy ảnh, bộ lọc bảo mật hoặc cấu trúc MIME do ứng dụng tạo. Vì vậy, khi debug cần phân biệt **message có part inline đúng** với **client có hiển thị part đó đúng hay không**.

### 2.1. Inline không đồng nghĩa ảnh luôn được tải

CID image đã nằm trong email, nên không phụ thuộc một HTTP request ra ngoài như ảnh remote. Tuy nhiên, client vẫn có thể:

- Không hỗ trợ hoặc không xử lý đúng cấu trúc MIME cụ thể.
- Ẩn hình theo tùy chọn người dùng.
- Hiển thị hình như attachment thay vì đặt trong HTML.
- Làm sạch HTML hoặc bỏ tham chiếu không nhận diện được.

Vì thế, CID thường là cách tốt để đính kèm logo/tài nguyên nhỏ mà không cần tải từ domain ngoài, nhưng **không phải bảo đảm tuyệt đối về hiển thị**.

### 2.2. Ảnh remote cũng có thể bị chặn

HTML có thể tham chiếu:

```html
<img src="https://static.example.com/mail/logo.png"
     alt="Logo công ty">
```

Ảnh remote phụ thuộc khả năng tải URL và chính sách của client. Client có thể hỏi người dùng trước khi tải, chặn hoàn toàn hoặc tải qua proxy. Một số hệ thống còn cache/proxy ảnh khiến ứng dụng không quan sát được hành vi truy cập gốc.

Do đó, thay CID bằng ảnh remote **không phải phương án dự phòng chắc chắn hơn**. Với thông tin bắt buộc, hãy thể hiện bằng văn bản; ảnh chỉ nên hỗ trợ trải nghiệm.

## 3. Tạo inline resource bằng Spring MimeMessageHelper

### 3.1. Ví dụ cơ bản

```java
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendWelcomeMail(JavaMailSender mailSender)
        throws Exception {

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_RELATED,
            "UTF-8");

    helper.setFrom("notifications@example.com");
    helper.setTo("customer@example.net");
    helper.setSubject("Chào mừng bạn");

    String html = """
            <html>
              <body>
                <p>Chào mừng bạn đến với dịch vụ.</p>
                <img src="cid:company-logo" alt="Logo công ty"
                     width="160">
              </body>
            </html>
            """;

    // Đặt nội dung trước khi thêm inline resource.
    helper.setText("Chào mừng bạn đến với dịch vụ.", html);
    helper.addInline(
            "company-logo",
            new ClassPathResource("mail/images/company-logo.png"),
            "image/png");

    mailSender.send(message);
}
```

Trong ví dụ:

- `MULTIPART_MODE_RELATED` phù hợp với message có nội dung HTML liên quan tới inline resource.
- `setText(plain, html)` tạo hai cách biểu diễn nội dung.
- `src="cid:company-logo"` phải khớp với ID truyền cho `addInline("company-logo", ...)`.
- `ClassPathResource` dùng cho ảnh logo được đóng gói cùng ứng dụng.
- `image/png` mô tả đúng định dạng ảnh nguồn.

**Nên gọi `setText(...)` trước `addInline(...)`.** Tài liệu Spring khuyến nghị thứ tự này để bảo đảm cấu trúc message được xây dựng phù hợp với inline resource.

### 3.2. Dùng chế độ multipart khi có cả attachment

Nếu email có text/plain, HTML, inline logo và thêm một PDF để tải, có thể dùng:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");
```

Sau đó:

```java
helper.setText(plainText, html);
helper.addInline(
        "company-logo",
        new ClassPathResource("mail/images/company-logo.png"),
        "image/png");
helper.addAttachment(
        "invoice-DH1024.pdf",
        new FileSystemResource(invoicePath),
        "application/pdf");
```

Chế độ `MIXED_RELATED` giúp biểu diễn phần nội dung liên quan (HTML và inline resource) cùng các attachment thông thường. Cấu trúc MIME lồng nhau do helper/provider tạo; không nên tự giả định part nằm ở index cố định khi kiểm thử.

### 3.3. Content-ID phải khớp chính xác

Nếu HTML dùng:

```html
<img src="cid:brand-logo" alt="Logo">
```

thì helper phải thêm:

```java
helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");
```

Nếu HTML tham chiếu `cid:brand-logo` nhưng code thêm ID `company-logo`, client không thể ánh xạ đúng tài nguyên.

Không tự thêm dấu ngoặc nhọn vào ID khi truyền cho helper nếu API nhận content ID dạng chuỗi logic. Spring/Jakarta Mail xử lý cách biểu diễn header `Content-ID`. Trong raw MIME, ID thường xuất hiện trong dấu ngoặc nhọn, ví dụ `<brand-logo>`.

### 3.4. ID nên duy nhất trong message

Khi email có nhiều inline resource, mỗi CID cần phân biệt:

```java
helper.addInline(
        "company-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");

helper.addInline(
        "status-icon",
        new ClassPathResource("mail/images/status.png"),
        "image/png");
```

HTML:

```html
<img src="cid:company-logo" alt="Logo công ty">
<img src="cid:status-icon" alt="Trạng thái đã xác nhận">
```

Không dùng cùng một Content-ID cho hai tài nguyên khác nhau trong một message. Để tránh xung đột khi template được tái sử dụng hoặc có nhiều module tạo resource, có thể quy ước namespace ID theo message/template.

## 4. Thiết kế nội dung vẫn dùng được khi ảnh không hiển thị

Phương án dự phòng đầu tiên không phải thêm một cơ chế tải ảnh khác. Đó là **đảm bảo email vẫn truyền đạt đầy đủ ý nghĩa khi bỏ toàn bộ hình ảnh**.

### 4.1. Dùng alt text có ý nghĩa

Không nên:

```html
<img src="cid:status-icon" alt="">
```

nếu hình ảnh mang thông tin quan trọng.

Nên:

```html
<img src="cid:status-icon"
     alt="Đơn hàng đã được xác nhận"
     width="24" height="24">
```

Nếu client không hiển thị hình, `alt` có thể giúp người nhận hiểu nội dung. Nhưng không phải client nào cũng hiển thị alt theo cùng một cách; một số chỉ hiện biểu tượng ảnh lỗi hoặc không hiển thị phần thay thế.

Vì thế, **không để thông tin quan trọng chỉ nằm trong alt**. Hãy có một câu văn độc lập:

```html
<p><strong>Trạng thái: Đơn hàng đã được xác nhận.</strong></p>
<img src="cid:status-icon"
     alt="Biểu tượng xác nhận"
     width="24" height="24">
```

Nếu ảnh biến mất, câu trạng thái vẫn còn.

### 4.2. Logo cần có tên thương hiệu dạng chữ

Nếu logo không hiển thị, người nhận vẫn cần biết email đến từ thương hiệu nào. Có thể dùng:

```html
<p style="font-size:20px; font-weight:bold;">
  Công ty Example
</p>
<img src="cid:company-logo" alt="Logo Công ty Example"
     width="160">
```

Không đặt toàn bộ tên thương hiệu, tiêu đề hoặc thông tin liên hệ trong một hình ảnh duy nhất.

### 4.3. CTA phải là liên kết thật

Không dùng một ảnh nút làm cách duy nhất để mở trang:

```html
<!-- Không nên chỉ có hình ảnh làm CTA -->
<img src="cid:confirm-button.png" alt="">
```

Thay bằng anchor có nội dung:

```html
<p>
  <a href="https://accounts.example.com/verify">
    Xác minh tài khoản
  </a>
</p>
```

Nếu có hình trang trí cho nút, hãy xem nó là phần bổ trợ. Liên kết văn bản phải có thể dùng được khi ảnh bị ẩn hoặc CSS không hoạt động.

## 5. Phương án dự phòng cho từng loại nội dung

Không phải mọi inline resource đều cần cùng một fallback. Hãy xác định **mục đích của từng hình**:

| Loại resource | Khi inline không hiển thị | Phương án phù hợp |
|---|---|---|
| Logo thương hiệu | Không còn hình nhận diện | Hiển thị tên thương hiệu bằng text và alt có nghĩa. |
| Icon trang trí | Mất chi tiết trang trí | Bỏ qua ảnh; giữ nội dung chữ và trạng thái. |
| Icon thể hiện trạng thái | Người nhận có thể không hiểu trạng thái | Ghi trạng thái thành câu văn, không chỉ dùng màu/icon. |
| Biểu đồ hoặc sơ đồ quan trọng | Mất dữ liệu hình ảnh | Tóm tắt số liệu bằng text/bảng; đính kèm PDF hoặc link xem chi tiết khi phù hợp. |
| Ảnh sản phẩm | Người nhận không thấy sản phẩm | Có tên sản phẩm, mô tả và link xem sản phẩm. |
| Nút CTA dạng hình | Không thể thao tác | Dùng anchor text/HTML button-style có liên kết thật. |
| Chữ ký hoặc con dấu | Có thể mất thông tin xác nhận | Thể hiện thông tin xác thực bằng văn bản và liên kết kiểm tra hợp lệ; không chỉ dựa vào ảnh. |

**Fallback nên giữ nguyên ý nghĩa nghiệp vụ**, không nhất thiết giữ nguyên cách trình bày. Một icon có thể biến mất mà không ảnh hưởng nếu câu chữ đã truyền đạt trạng thái; một biểu đồ quan trọng cần có bản tóm tắt hoặc tài liệu thay thế.

## 6. Bản text/plain là lớp dự phòng quan trọng

Khi email có HTML, nên cân nhắc gửi thêm `text/plain` qua `multipart/alternative`. Bản text không chứa inline image và không phụ thuộc HTML/CSS.

Ví dụ:

```text
CÔNG TY EXAMPLE

Đơn hàng DH1024 đã được xác nhận.

Trạng thái: ĐÃ XÁC NHẬN
Tổng tiền: 1.250.000 VND

Xem chi tiết:
https://accounts.example.com/orders/DH1024

Nếu bạn không thực hiện yêu cầu này, vui lòng liên hệ bộ phận hỗ trợ.
```

Bản text phải giữ các thông tin cốt lõi:

- Ai gửi thông báo.
- Sự kiện/trạng thái nào đã xảy ra.
- Mã tham chiếu cần thiết.
- Thông tin số tiền/ngày giờ nếu có.
- Liên kết hoặc hướng dẫn hành động.
- Cách liên hệ hỗ trợ khi có vấn đề.

Đừng chỉ gửi `"Email của bạn không hỗ trợ HTML"`. Bản text là một biểu diễn đầy đủ của thông điệp, không phải một trang báo lỗi.

### 6.1. Cách tạo text và HTML bằng Spring

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8");

helper.setFrom("notifications@example.com");
helper.setTo(recipient);
helper.setSubject("Đơn hàng DH1024 đã được xác nhận");

String plain = """
        CÔNG TY EXAMPLE

        Đơn hàng DH1024 đã được xác nhận.
        Trạng thái: ĐÃ XÁC NHẬN
        Tổng tiền: 1.250.000 VND

        Xem chi tiết:
        https://accounts.example.com/orders/DH1024
        """;

String html = """
        <html>
          <body>
            <p><strong>CÔNG TY EXAMPLE</strong></p>
            <p>Đơn hàng <strong>DH1024</strong> đã được xác nhận.</p>
            <p>Trạng thái: ĐÃ XÁC NHẬN</p>
            <p>Tổng tiền: 1.250.000 VND</p>
            <p>
              <a href="https://accounts.example.com/orders/DH1024">
                Xem chi tiết đơn hàng
              </a>
            </p>
            <img src="cid:company-logo"
                 alt="Logo Công ty Example" width="160">
          </body>
        </html>
        """;

helper.setText(plain, html);
helper.addInline(
        "company-logo",
        new ClassPathResource("mail/images/company-logo.png"),
        "image/png");

mailSender.send(message);
```

Ở ví dụ, `MULTIPART_MODE_RELATED` dùng cho HTML và inline resource. Helper xây dựng phần alternative và related theo chế độ multipart. Nếu còn attachment thông thường, dùng chế độ `MULTIPART_MODE_MIXED_RELATED` để kết hợp.

## 7. Có nên chuyển inline image thành attachment?

Có thể, nhưng cần hiểu **attachment thông thường và inline resource có mục đích khác nhau**.

### 7.1. Inline resource

```java
helper.addInline(
        "chart-image",
        new FileSystemResource(chartPath),
        "image/png");
```

HTML:

```html
<img src="cid:chart-image" alt="Biểu đồ doanh thu theo tháng">
```

Mục tiêu là hiển thị hình ngay trong phần HTML của message.

### 7.2. Attachment thông thường

```java
helper.addAttachment(
        "bao-cao-doanh-thu.png",
        new FileSystemResource(chartPath),
        "image/png");
```

Mục tiêu là cung cấp một file để người nhận mở hoặc tải về. Client có thể hiển thị file ở vùng attachment, thường có biểu tượng kẹp giấy hoặc danh sách tệp.

### 7.3. Khi nào nên dùng cả hai?

Với một biểu đồ quan trọng, sản phẩm có thể:

- Đưa hình inline để người nhận xem nhanh.
- Cung cấp file đính kèm để tải về khi cần lưu trữ.
- Có bản text tóm tắt số liệu.

Nhưng gửi cùng một ảnh hai lần có thể làm email lớn hơn và client hiển thị một attachment dư thừa. Chỉ nên làm khi người nhận thực sự cần tải file. Nếu nội dung có nhiều dữ liệu, PDF hoặc trang báo cáo có quyền truy cập có thể phù hợp hơn.

**Không nên tự động chuyển mọi inline image thành attachment khi nghĩ rằng client không hỗ trợ CID.** Nhiều client vẫn xử lý inline; việc chuyển thành attachment làm thay đổi trải nghiệm và không bảo đảm người nhận sẽ mở file.

## 8. Dùng ảnh remote làm phương án thay thế?

Ảnh remote có thể thích hợp với logo hoặc hình trang trí công khai, nhưng không nên coi là fallback tuyệt đối.

Ví dụ:

```html
<img src="https://static.example.com/email/logo.png"
     alt="Logo Công ty Example"
     width="160">
```

### 8.1. Ưu điểm

- Không làm tăng kích thước MIME message bằng byte ảnh.
- Có thể cập nhật ảnh ở server mà không phải thay template email.
- Nhiều client hỗ trợ ảnh HTTPS khi người dùng cho phép tải.
- Có thể dùng CDN để phân phối tài nguyên công khai.

### 8.2. Giới hạn và rủi ro

- Client có thể chặn ảnh ngoài hoặc yêu cầu người nhận bật tải ảnh.
- URL cần truy cập được từ mạng của người nhận, không yêu cầu cookie/session nội bộ.
- Tài nguyên remote có thể bị proxy hoặc cache, nên không kiểm soát được thời điểm tải.
- Một URL riêng cho từng người nhận có thể tạo tracking và ảnh hưởng quyền riêng tư.
- Tài nguyên có thể bị thay đổi sau khi email đã gửi, làm nội dung cũ hiển thị khác.
- Nếu URL hết hạn hoặc domain ngừng hoạt động, ảnh biến mất.

### 8.3. Khi nào dùng remote image?

Có thể cân nhắc cho logo công khai hoặc ảnh trang trí ít quan trọng, nếu:

- URL dùng HTTPS.
- Domain được quản lý bởi tổ chức.
- Không cần cookie hoặc quyền truy cập nội bộ.
- Nội dung có alt và thông tin text thay thế.
- Chính sách riêng tư cho phép tải ảnh ngoài.
- Có phương án hiển thị khi client chặn ảnh.

Không đặt OTP, token, dữ liệu riêng tư hoặc thông tin hóa đơn trong query string của URL ảnh. Không dùng remote image làm nơi duy nhất chứa nội dung quan trọng.

## 9. Vì sao không dùng data URI/base64 trong src để thay CID?

Một ý tưởng thường gặp là nhúng ảnh trực tiếp:

```html
<img src="data:image/png;base64,iVBORw0KGgo...">
```

Đây là **data URI**, không phải CID. Hỗ trợ trong email client không đồng nhất; nhiều client lọc hoặc không hiển thị kiểu nguồn này. Nó cũng làm HTML dài, tăng dung lượng và gây khó khăn cho việc quản lý nội dung.

Đối với email HTML, nên ưu tiên:

1. CID inline resource cho ảnh nhỏ cần gắn với message.
2. HTTPS remote image cho tài nguyên công khai khi chấp nhận việc client có thể chặn.
3. Attachment thông thường khi người nhận cần tải file.
4. Văn bản/bảng/link thay thế cho thông tin quan trọng.

Không tự base64 ảnh rồi chèn vào HTML với kỳ vọng tương thích cao hơn CID.

## 10. Tránh phụ thuộc vào CSS background image

Một số email template sử dụng:

```html
<td style="background-image: url('https://static.example.com/banner.png');">
  <h1>Chương trình ưu đãi</h1>
</td>
```

CSS background image có thể không hiển thị trên một số client hoặc bị thay đổi trong chế độ đọc. Nếu banner chứa nội dung quan trọng như ngày hết hạn hoặc mức giảm giá, người nhận có thể mất thông tin khi ảnh bị chặn.

Thiết kế tốt hơn:

- Đưa tiêu đề và thông tin ưu đãi thành text thật.
- Dùng ảnh nền như trang trí.
- Có màu nền và bố cục dự phòng.
- Không đặt điều kiện/giá trị nghiệp vụ duy nhất trong ảnh.
- Kiểm thử trên client mục tiêu.

Với email, table layout và CSS inline đơn giản thường dễ tương thích hơn layout web hiện đại dùng nhiều selector phức tạp. Tuy nhiên, vẫn cần kiểm thử thực tế.

## 11. Không nên dò email client để gửi các phiên bản nội dung khác nhau

Ứng dụng có thể muốn phát hiện Gmail, Outlook hay Apple Mail từ user agent hoặc header rồi chọn cách nhúng ảnh. Với email, cách này thường không đáng tin:

- Email có thể được chuyển tiếp hoặc xem qua nhiều client.
- Gateway/proxy có thể thay đổi request và metadata.
- Một người có thể dùng nhiều thiết bị/client.
- Ứng dụng gửi thường không nhận được một tín hiệu đáng tin cậy cho biết cách render của từng người nhận.
- Việc phân nhánh theo client dễ tạo nhiều template và trường hợp lỗi cần duy trì.

**Thiết kế theo khả năng suy giảm an toàn** thường bền vững hơn: nội dung text đầy đủ, ảnh bổ trợ, link thật và MIME đúng. Nếu sản phẩm có yêu cầu đặc thù cho một nền tảng email nhất định, kiểm thử và công bố hỗ trợ theo client đó, thay vì suy đoán client từ dữ liệu không đáng tin.

## 12. Kiểm tra MIME message trước khi kết luận client không hỗ trợ inline

Trước khi đổi giải pháp, cần xác định message có được tạo đúng không.

### 12.1. Kiểm tra Content-ID và MIME type

Đối chiếu:

```html
<img src="cid:company-logo" alt="Logo công ty">
```

với:

```java
helper.addInline(
        "company-logo",
        new ClassPathResource("mail/images/company-logo.png"),
        "image/png");
```

Kiểm tra:

- CID trong HTML khớp với ID được truyền vào helper.
- Resource tồn tại và đọc được.
- MIME type đúng với byte thực tế.
- Ảnh có định dạng được email client mục tiêu hỗ trợ phổ biến như PNG/JPEG.
- Không có hai resource dùng cùng CID trong một message.
- Helper được tạo ở chế độ multipart phù hợp.
- `setText` được gọi trước `addInline`.

### 12.2. Kiểm tra raw MIME trong môi trường test

Một email có inline resource thường có cấu trúc multipart liên quan. Có thể kiểm tra message sau khi tạo bằng Jakarta Mail:

```java
Object content = message.getContent();
if (!(content instanceof Multipart multipart)) {
    throw new IllegalStateException("Expected multipart message");
}

System.out.println("Part count: " + multipart.getCount());
```

Với cấu trúc mixed/related/alternative, multipart có thể lồng nhiều cấp. Test nên duyệt đệ quy các `BodyPart` và kiểm tra:

- Có part `text/plain`.
- Có part `text/html`.
- Có inline part với `Content-ID` phù hợp.
- `Content-Type` và `Content-Disposition` hợp lý.
- Byte ảnh được đọc đầy đủ.

Không giả định inline image luôn ở part index 1 hoặc attachment luôn ở index cuối.

### 12.3. Dùng SMTP catcher

SMTP catcher như GreenMail, Mailpit hoặc MailHog có thể giúp:

- Nhận message mà không gửi ra ngoài.
- Xem header và MIME structure.
- Tải part ảnh để kiểm tra byte.
- Xác nhận Content-ID và HTML reference khớp nhau.
- Kiểm tra nội dung text/plain và text/html.

SMTP catcher **không mô phỏng chính xác mọi email client**. Nếu MIME hợp lệ nhưng Outlook/Gmail/Apple Mail vẫn hiển thị khác nhau, cần kiểm thử trên client đó hoặc dịch vụ xem trước email chuyên dụng.

### 12.4. Kiểm tra dữ liệu ảnh độc lập

Trước khi điều tra client, xác nhận file ảnh:

- Có tồn tại và đọc được.
- Không phải file rỗng.
- Định dạng đúng.
- Kích thước pixel hợp lý.
- Dung lượng không quá lớn.
- Không bị hỏng trong quá trình tạo/copy.

Nếu ảnh không giải mã được, đổi MIME mode hoặc client không giải quyết được nguồn ảnh hỏng.

## 13. Ví dụ hoàn chỉnh: HTML có inline logo và fallback bằng text

Ví dụ sau dùng Spring Mail với nội dung HTML, plain text và CID logo. Nội dung quan trọng vẫn hiển thị ngay cả khi logo không xuất hiện.

```java
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderNotificationMailer {

    private final JavaMailSender mailSender;

    public OrderNotificationMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmed(String recipient, String orderCode)
            throws Exception {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_RELATED,
                "UTF-8");

        helper.setFrom("orders@example.com");
        helper.setTo(recipient);
        helper.setSubject("Đơn hàng " + orderCode + " đã được xác nhận");

        String plain = """
                CÔNG TY EXAMPLE

                Đơn hàng %s đã được xác nhận.

                Xem chi tiết đơn hàng:
                https://accounts.example.com/orders/%s

                Nếu bạn không thực hiện yêu cầu này, hãy liên hệ bộ phận hỗ trợ.
                """.formatted(orderCode, orderCode);

        String html = """
                <html>
                  <body>
                    <p><strong>CÔNG TY EXAMPLE</strong></p>
                    <img src="cid:company-logo"
                         alt="Logo Công ty Example"
                         width="160">
                    <h1>Đơn hàng đã được xác nhận</h1>
                    <p>Mã đơn hàng: <strong>%s</strong></p>
                    <p>
                      <a href="https://accounts.example.com/orders/%s">
                        Xem chi tiết đơn hàng
                      </a>
                    </p>
                    <p>Nếu bạn không thực hiện yêu cầu này,
                       hãy liên hệ bộ phận hỗ trợ.</p>
                  </body>
                </html>
                """.formatted(orderCode, orderCode);

        helper.setText(plain, html);
        helper.addInline(
                "company-logo",
                new ClassPathResource("mail/images/company-logo.png"),
                "image/png");

        mailSender.send(message);
    }
}
```

Đây là ví dụ minh họa thứ tự và cấu trúc MIME. Trong ứng dụng thật:

- `orderCode` phải được kiểm tra ký tự và độ dài trước khi dùng trong URL/HTML.
- URL nên được tạo bằng trusted URL builder từ base URL cấu hình, không ghép từ dữ liệu không tin cậy.
- Dữ liệu động trong HTML nên được render qua template engine có escaping thay vì nối chuỗi trực tiếp.
- Logo phải là tài nguyên do ứng dụng kiểm soát.
- Recipient và quyền gửi phải được xác thực theo nghiệp vụ.

### 13.1. Nếu có thêm attachment PDF

Đổi multipart mode:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");
```

Sau khi `setText` và `addInline`:

```java
helper.addAttachment(
        "hoa-don-" + orderCode + ".pdf",
        new FileSystemResource(invoicePath),
        "application/pdf");
```

Logo inline và PDF attachment có mục đích khác nhau: logo giúp nhận diện trong nội dung, PDF cung cấp tài liệu tải về. Nếu logo không hiển thị, phần chữ và liên kết vẫn hữu ích; nếu PDF bắt buộc mà file không đọc được, phải xử lý lỗi attachment theo chính sách nghiệp vụ.

## 14. Kiểm thử khả năng suy giảm khi inline không hiển thị

Không thể chỉ kiểm tra “ảnh có xuất hiện trên một client hay không”. Cần kiểm tra cả trường hợp ảnh bị loại bỏ.

### 14.1. Test phiên bản HTML khi bỏ ảnh

Một cách kiểm thử đơn giản là render template rồi loại bỏ các thẻ `img` trong bản HTML test để xác nhận nội dung còn lại vẫn đầy đủ:

```java
String htmlWithoutImages = Jsoup.parse(html)
        .select("img")
        .remove()
        .toString();

assertThat(htmlWithoutImages)
        .contains("Đơn hàng đã được xác nhận")
        .contains("DH1024")
        .contains("Xem chi tiết đơn hàng");
```

Ví dụ cần dependency jsoup trong test. Đây là kiểm tra nội dung sau khi bỏ ảnh, không mô phỏng đầy đủ mọi cách client xử lý MIME hoặc alt text.

### 14.2. Test plain text

```java
assertThat(plainText)
        .contains("Đơn hàng DH1024 đã được xác nhận")
        .contains("https://accounts.example.com/orders/DH1024");
```

Bản text cần có thông tin và link tương đương. Nếu bản HTML dùng một nút ảnh còn plain text không có URL, người dùng client text-only sẽ không hoàn tất được tác vụ.

### 14.3. Test CID mapping

Kiểm tra:

```java
assertThat(html).contains("cid:company-logo");
assertThat(inlineContentIds).contains("company-logo");
```

`inlineContentIds` là tập CID được trích xuất từ các MIME part trong helper test; cần duyệt multipart lồng nhau để lấy đủ. Không chỉ kiểm tra chuỗi HTML mà bỏ qua việc resource có thật sự được thêm vào message hay không.

### 14.4. Test trên client thật

Với email quan trọng, kiểm tra tối thiểu trên các client mà sản phẩm hỗ trợ. Cần xem:

- Logo CID có hiển thị không.
- Ảnh bị ẩn có làm mất thông tin không.
- Alt text có ích không.
- Nút/anchor còn sử dụng được khi CSS bị bỏ.
- Bản plain text có đầy đủ nội dung không.
- Inline image có bị trình bày như attachment ngoài ý muốn không.
- Dark mode và mobile có làm chữ khó đọc không.

Một bản MIME hợp lệ là điều kiện cần; kiểm tra client là cách xác nhận trải nghiệm thực tế.

## 15. Lựa chọn fallback theo mức độ quan trọng của hình

Có thể phân nhóm:

### 15.1. Hình trang trí

Ví dụ đường kẻ, nền màu, icon trang trí. Phương án tốt nhất thường là **không cần fallback phức tạp**. Nếu hình mất, nội dung vẫn nguyên vẹn. Có thể bỏ ảnh hoàn toàn trên client không hỗ trợ.

### 15.2. Hình nhận diện

Ví dụ logo công ty. Dùng CID nếu muốn tránh request ảnh ngoài; kèm tên thương hiệu dạng chữ và alt có nghĩa. Remote HTTPS là lựa chọn khác khi tổ chức muốn quản lý ảnh tập trung và chấp nhận việc client có thể chặn tải.

### 15.3. Hình truyền tải dữ liệu

Ví dụ biểu đồ, sơ đồ quy trình hoặc ảnh chụp bằng chứng. **Không chỉ dựa vào ảnh**:

- Tóm tắt kết quả bằng text.
- Có bảng số liệu HTML/text nếu phù hợp.
- Đính kèm PDF/CSV khi người nhận cần lưu hoặc phân tích.
- Cung cấp link tới trang báo cáo được phân quyền.

### 15.4. Hình là một phần của hành động

Ví dụ nút “Thanh toán”, “Xác nhận”, “Đặt lại mật khẩu”. Dùng anchor thật có nội dung văn bản và URL HTTPS; hình chỉ trang trí. Không dùng image map hoặc một ảnh làm vùng click duy nhất.

## 16. Quyền riêng tư và bảo mật của các phương án ảnh

### 16.1. CID không yêu cầu tải ảnh từ domain ngoài

Vì byte ảnh được đính kèm trong email, CID thường tránh được một HTTP request tới máy chủ ảnh khi client hiển thị. Điều này có thể giảm một số kiểu theo dõi qua ảnh remote. Tuy nhiên, nó **không làm toàn bộ email riêng tư tuyệt đối**: nhà cung cấp mail, gateway và người nhận vẫn có thể truy cập message.

### 16.2. Remote image có thể để lộ metadata

Một request tải ảnh có thể làm máy chủ hoặc proxy quan sát thời điểm, URL và một số metadata tùy client. Không dùng ảnh remote làm tracking pixel nếu chưa đánh giá yêu cầu riêng tư, consent và chính sách áp dụng.

### 16.3. Không chứa bí mật trong URL ảnh hoặc CID

CID không phải nơi lưu token xác thực. URL ảnh remote cũng không nên mang:

- OTP hoặc password reset token.
- Dữ liệu cá nhân không cần thiết.
- Số hóa đơn hoặc mã bí mật có thể đoán được.
- Thông tin định danh có thể được dùng để truy cập tài liệu.

Nếu cần hiển thị tài liệu riêng tư, dùng cơ chế truy cập được bảo vệ và kiểm tra quyền ở server.

### 16.4. Chỉ dùng định dạng ảnh phù hợp

Đối với email, PNG và JPEG thường là lựa chọn tương thích phổ biến. Tránh phụ thuộc SVG inline hoặc định dạng ảnh ít được hỗ trợ nếu chưa kiểm thử trên client mục tiêu. Ảnh phải được kiểm tra kích thước và nguồn; không nhúng file không tin cậy mà chưa qua quy trình kiểm soát.

## 17. Các lỗi thường gặp khi dùng inline resource

### 17.1. CID trong HTML không khớp với addInline

HTML dùng `cid:logo` nhưng Java thêm `company-logo`. Cần dùng cùng một ID.

### 17.2. Gọi addInline trước setText

Thứ tự này có thể khiến cấu trúc multipart không được helper xây dựng như mong muốn. Gọi `setText` trước rồi mới `addInline`.

### 17.3. Dùng multipart mode không phù hợp

Inline resource cần cấu trúc related. Nếu email có cả attachment thông thường, chọn `MULTIPART_MODE_MIXED_RELATED`.

### 17.4. Tưởng Content-Disposition inline ép client hiển thị trong HTML

`inline` là metadata MIME; cách hiển thị cuối vẫn phụ thuộc client. CID mapping và MIME structure cũng phải đúng.

### 17.5. Chỉ có ảnh, không có text

Khi client chặn hình, người nhận không biết nội dung. Thêm văn bản, alt và bản plain text.

### 17.6. Dùng remote image như fallback chắc chắn

Remote image cũng có thể bị chặn. Hãy dùng text làm fallback cốt lõi.

### 17.7. Dùng data URI để tránh CID

Data URI không có mức hỗ trợ nhất quán trong email client. Ưu tiên CID, remote HTTPS có kiểm soát hoặc attachment theo mục đích.

### 17.8. Chuyển mọi inline image thành attachment

Attachment có thể gây rối, tăng dung lượng và không bảo đảm người nhận sẽ mở. Chỉ dùng khi file có giá trị tải về.

### 17.9. Dùng CSS background cho thông tin bắt buộc

Background image có thể không hiển thị. Đưa nội dung quan trọng thành text thật.

### 17.10. Dùng ảnh làm CTA duy nhất

Ảnh có thể mất hoặc không click được như mong đợi. Dùng anchor text có ý nghĩa và URL thật.

### 17.11. Nghĩ SMTP catcher chứng minh hiển thị đúng

SMTP catcher xác nhận MIME được gửi tới test server, không mô phỏng mọi email client. Cần test trên client mục tiêu.

### 17.12. Dùng một CID cho nhiều resource

CID cần duy nhất trong message để tránh ánh xạ nhầm.

## 18. Bài tập thực hành

### Bài 1 — Kiểm tra CID

HTML có `src="cid:brand-logo"` nhưng code gọi `addInline("logo", ...)`. Hãy giải thích tại sao ảnh không hiển thị và sửa lại ID.

### Bài 2 — MIME multipart

Một email có plain text, HTML, logo inline và PDF attachment. Hãy chọn multipart mode phù hợp và giải thích sự khác nhau giữa `MULTIPART_MODE_RELATED` và `MULTIPART_MODE_MIXED_RELATED`.

### Bài 3 — Fallback khi ảnh bị ẩn

Thiết kế email xác nhận đơn hàng có logo, icon trạng thái và nút “Xem chi tiết”. Viết HTML sao cho nếu toàn bộ ảnh bị loại bỏ, người nhận vẫn biết trạng thái và có thể mở trang đơn hàng.

### Bài 4 — Remote image hay CID?

Một logo công khai cần được cập nhật thường xuyên. So sánh CID và ảnh remote HTTPS về kích thước message, khả năng cập nhật, quyền riêng tư và khả năng bị chặn. Đề xuất lựa chọn theo yêu cầu sản phẩm.

### Bài 5 — Biểu đồ quan trọng

Email báo cáo có biểu đồ doanh thu là nội dung chính. Hãy đề xuất fallback bằng text/bảng số liệu, attachment PDF hoặc link báo cáo; giải thích khi nào dùng từng phương án.

### Bài 6 — Text-only

Viết bản `text/plain` cho email có HTML button và logo inline. Đảm bảo người nhận vẫn có đủ URL và thông tin để thực hiện hành động.

### Bài 7 — Kiểm thử

Thiết kế test kiểm tra MIME có CID khớp HTML, ảnh có đúng MIME type và plain text có đủ nội dung. Sau đó mô tả cách kiểm thử thực tế trên email client.

### Bài 8 — Quyền riêng tư

Một nhóm muốn dùng remote tracking pixel để biết ai mở email. Hãy phân tích giới hạn độ tin cậy của tín hiệu, metadata có thể bị thu thập và các yếu tố riêng tư cần cân nhắc.

## 19. Ghi nhớ và tài liệu tham khảo

Khi **mail client không hỗ trợ inline hoặc không hiển thị inline resource đúng cách**, hãy:

1. Dùng `MimeMessageHelper.addInline` với CID khớp chính xác giữa HTML và MIME part.
2. Chọn multipart mode phù hợp; có attachment thông thường thì cân nhắc `MULTIPART_MODE_MIXED_RELATED`.
3. Gọi `setText` trước `addInline` để helper xây dựng MIME structure đúng.
4. Kiểm tra byte ảnh, MIME type, Content-ID và cấu trúc multipart trước khi kết luận lỗi thuộc client.
5. Giữ thông tin quan trọng trong text thật; không đặt trạng thái, số tiền hay CTA chỉ trong ảnh.
6. Cung cấp alt text có ý nghĩa và bản `text/plain` đầy đủ.
7. Dùng attachment khi người nhận cần tải tài liệu; dùng remote HTTPS khi chấp nhận việc client có thể chặn ảnh; không coi data URI là fallback phổ quát.
8. Kiểm thử trên email client mục tiêu; SMTP catcher chỉ kiểm tra MIME, không xác nhận giao diện cuối.
9. Cân nhắc quyền riêng tư khi tải ảnh remote và không đưa bí mật vào URL ảnh.

Tài liệu kỹ thuật nên tham khảo:

- **Spring Framework API — `MimeMessageHelper`:** `addInline`, multipart modes, `setText` và cách gắn resource.
- **Spring Framework Reference — Email:** tạo MIME message, inline resource và attachment.
- **Jakarta Mail API — `MimeMessage`, `MimeMultipart`, `MimeBodyPart`:** cấu trúc multipart và xử lý body part.
- **RFC 2387 — The MIME Multipart/Related Content-type:** quan hệ giữa phần nội dung chính và tài nguyên liên quan.
- **RFC 2392 — Content-ID and Message-ID Uniform Resource Locators:** tham chiếu tài nguyên bằng `cid:` trong nội dung MIME.
- **RFC 2045–2049 — MIME:** content type, transfer encoding và cấu trúc email đa phương tiện.

**Inline resource là một cách đóng gói tài nguyên trong email, không phải cam kết về giao diện của client.** Một email đáng tin cậy vẫn phải truyền đạt đầy đủ thông tin khi hình ảnh bị ẩn: dùng văn bản, liên kết thật, alt có ý nghĩa và bản plain text. Khi thiết kế theo nguyên tắc đó, email vẫn hữu ích dù client xử lý CID, CSS hoặc ảnh remote khác nhau.
