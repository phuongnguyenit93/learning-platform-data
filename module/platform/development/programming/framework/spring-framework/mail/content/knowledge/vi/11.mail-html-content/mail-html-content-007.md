# Liên kết, nút và nội dung có thể đọc trên màn hình nhỏ

## 1. Mục tiêu của email HTML trên thiết bị di động

Trong **Spring Framework Mail**, ứng dụng có thể gửi nội dung HTML bằng **JavaMailSender**, **MimeMessage** và **MimeMessageHelper**. Nhưng một email gửi thành công chưa chắc dễ đọc trên điện thoại. Màn hình hẹp, cỡ chữ do người dùng điều chỉnh, chế độ tối, ảnh bị chặn hoặc HTML/CSS được hỗ trợ khác nhau đều có thể ảnh hưởng đến trải nghiệm.

Một email HTML phù hợp với màn hình nhỏ cần đáp ứng ba yêu cầu:

1. **Đọc được ngay**: nội dung chính rõ ràng, không phải phóng to hay cuộn ngang.
2. **Chạm đúng hành động**: link và nút CTA có nhãn dễ hiểu, vùng chạm đủ rộng, khoảng cách hợp lý.
3. **Có phương án dự phòng**: nếu ảnh bị chặn, CSS không được áp dụng hoặc người đọc chọn chế độ plain text, thông điệp vẫn đầy đủ.

Ví dụ, email xác nhận đơn hàng có thể đẹp trên desktop nhưng khó sử dụng trên điện thoại nếu bố cục rộng cố định 900 px, font nhỏ 11 px và có ba nút đặt sát nhau. Cách khắc phục chủ yếu nằm ở **thiết kế HTML email**, không phải thay SMTP host hoặc thay kiểu JavaMailSender.

## 2. Email HTML không phải một trang web thông thường

Các email client như Gmail, Outlook và Apple Mail có cách xử lý HTML/CSS khác nhau. Một số loại bỏ script, form, CSS đặc thù hoặc sửa cấu trúc markup. Do đó, không nên sao chép nguyên một trang web vào email rồi giả định nó sẽ hiển thị như trong trình duyệt.

| Thành phần | Trên website | Trong email HTML |
|---|---|---|
| JavaScript | Thường chạy được | Thường bị chặn hoặc loại bỏ |
| Form nhập liệu | Hỗ trợ rộng rãi | Hỗ trợ không đồng nhất; nên mở website để thao tác |
| Flexbox/Grid | Thường hoạt động tốt | Có thể bị bỏ qua hoặc khác nhau theo client |
| Media query | Phổ biến | Nhiều client hỗ trợ nhưng không phải tất cả |
| CSS ngoài | Thường tải được | Không nên phụ thuộc vào stylesheet ngoài |
| Webfont | Dùng phổ biến | Cần font hệ thống dự phòng |
| Hình từ URL | Trình duyệt tải theo trang | Email client có thể chặn hoặc proxy hình |
| Button | Có thể phụ thuộc script | Nên dùng thẻ liên kết **a href** được tạo kiểu |

Chiến lược phù hợp là **progressive enhancement**: bố cục cơ bản vẫn đọc được với HTML đơn giản và CSS inline; media query chỉ giúp cải thiện khi client hỗ trợ.

## 3. Bố cục mobile-first: một cột và chiều rộng linh hoạt

Với email giao dịch như xác nhận tài khoản, đơn hàng hay đặt lại mật khẩu, **một cột** thường dễ đọc nhất:

~~~text
Desktop (nội dung giới hạn chiều rộng):

 +---------------------------------------+
 |                                       |
 |     +---------------------------+     |
 |     | Logo                      |     |
 |     |                           |     |
 |     | Tiêu đề                   |     |
 |     | Nội dung chính            |     |
 |     |                           |     |
 |     | [ Xem đơn hàng ]          |     |
 |     |                           |     |
 |     | URL dự phòng              |     |
 |     +---------------------------+     |
 |                                       |
 +---------------------------------------+

Mobile (nội dung tự co theo màn hình):

 +--------------------+
 | Logo               |
 |                    |
 | Tiêu đề            |
 |                    |
 | Nội dung ngắn      |
 | tự xuống dòng      |
 |                    |
 | [ Xem đơn hàng ]   |
 |                    |
 | Link dự phòng      |
 +--------------------+
~~~

**Gợi ý thực hành:**

- Bảng ngoài dùng **width="100%"** để tận dụng không gian sẵn có.
- Vùng nội dung chính có thể dùng **max-width khoảng 560–640 px**; trên mobile vẫn co theo chiều rộng thực tế.
- Chừa **padding ngang khoảng 16–24 px** để chữ không sát viền.
- Tránh bảng nhiều cột chứa nhiều dữ liệu dài; trên mobile có thể chuyển sang các cặp **nhãn: giá trị**.
- Không cố định chiều rộng hình lớn hơn màn hình.
- Đưa thông tin quan trọng và hành động chính lên trước các chi tiết phụ.

Các mốc kích thước là hướng dẫn thiết kế, **không phải quy định bắt buộc của Spring Mail**. Chúng cần được điều chỉnh theo nội dung và kiểm tra trên email client mục tiêu.

### Cỡ chữ dễ đọc

| Nội dung | Mốc tham khảo | Lợi ích |
|---|---|---|
| Nội dung chính | Font khoảng **16 px** | Hạn chế phải phóng to trên điện thoại |
| Khoảng cách dòng | Line-height khoảng **1.4–1.6** | Dễ đọc những đoạn dài |
| Tiêu đề | Khoảng **22–28 px** | Tạo phân cấp rõ ràng |
| Chữ trên CTA | Khoảng **16 px** | Nhận biết và chạm dễ hơn |
| Padding CTA | Khoảng **12–14 px** trên/dưới | Hướng đến vùng chạm cao 44–48 px |
| Giãn cách đoạn | Khoảng **12–20 px** | Tránh nội dung quá dày |

Không nên thu nhỏ font để nhét nhiều thông tin vào một email. Hãy rút gọn nội dung, chia đoạn và ưu tiên những gì người nhận cần biết.

## 4. Liên kết trong email: rõ đích, đủ khoảng cách và dùng HTTPS

Một liên kết email phải có **href thực**:

~~~html
<a href="https://example.com/orders">Xem chi tiết đơn hàng</a>
~~~

Nhãn liên kết nên mô tả đích đến. Tránh các cụm mơ hồ:

~~~html
<a href="https://example.com/orders">Bấm vào đây</a>
~~~

Nếu người dùng sử dụng trình đọc màn hình để liệt kê các link, nhãn **“Xem chi tiết đơn hàng”** vẫn cung cấp ngữ cảnh, còn “Bấm vào đây” thì không.

Một link tốt thường có:

1. **URL HTTPS tuyệt đối**, không dùng đường dẫn tương đối như **/orders/123**.
2. **Nhãn trung thực**, không khiến người dùng nghĩ đang vào một domain khác.
3. **Gạch chân hoặc dấu hiệu nhận biết**, đặc biệt với link nằm trong đoạn văn.
4. **Khoảng trống giữa các link**, tránh nhiều vùng chạm quá sát.
5. **Đích đến hợp lệ và được kiểm soát** bởi ứng dụng, không trỏ tùy tiện theo dữ liệu người dùng.
6. **URL dự phòng đọc được** nếu thao tác rất quan trọng.

### Ký tự đặc biệt trong href

Nếu URL có hai tham số, trong HTML cần escape dấu ampersand:

~~~html
<a href="https://example.com/orders?status=ready&amp;source=email">
  Xem đơn hàng đã xác nhận
</a>
~~~

**URL encoding** và **HTML escaping** là hai thao tác khác nhau. Khi xây URL động, encode các thành phần URL theo vị trí (path, query) rồi escape toàn bộ chuỗi khi đưa vào thuộc tính HTML. Không nối dữ liệu đầu vào chưa kiểm tra trực tiếp vào thuộc tính **href**.

## 5. Nút CTA nên là thẻ a được tạo kiểu

**CTA (Call To Action)** là hành động chính: “Xác nhận địa chỉ email”, “Xem hóa đơn”, “Theo dõi đơn hàng” hoặc “Mở trang hỗ trợ”.

Trong email, nên ưu tiên **thẻ a có href** thay vì thẻ button phụ thuộc vào JavaScript hay form. Dùng CSS inline để tạo hình thức giống nút:

~~~html
<a
  href="https://example.com/orders"
  style="
    display:inline-block;
    padding:14px 24px;
    background-color:#174ea6;
    color:#ffffff;
    font:700 16px/22px Arial,sans-serif;
    text-decoration:none;
    text-align:center;
    border-radius:6px;">
  Xem đơn hàng
</a>
~~~

**Vì sao không dùng button onclick?** Phần lớn email client không cho JavaScript chạy. Khi thẻ a có href thực, hành động điều hướng vẫn có ý nghĩa ngay cả khi CSS bị giản lược.

### Vùng chạm lớn trên điện thoại

Một nút chỉ có phần chữ nhỏ, không padding, sẽ khó chạm bằng ngón tay. Trong ví dụ, line-height 22 px và padding dọc 14 px tạo vùng CTA cao khoảng 50 px trên những client áp dụng CSS đúng dự kiến. Mục tiêu thực hành thường nằm quanh **44–48 px hoặc lớn hơn**, nhưng kết quả phải được thử nghiệm vì client email có thể bỏ qua một số thuộc tính.

Với nhiều hành động, nên có **một CTA nổi bật** và link phụ ít nổi bật hơn; tránh đặt nhiều nút nhỏ ngang hàng trên màn hình hẹp.

### Nút dạng table để tăng tính tương thích

Một số email client render bố cục table ổn định hơn bố cục CSS hiện đại:

~~~html
<table role="presentation" border="0" cellpadding="0" cellspacing="0">
  <tr>
    <td
      align="center"
      bgcolor="#174ea6"
      style="background-color:#174ea6;border-radius:6px;">
      <a
        href="https://example.com/orders"
        style="
          display:inline-block;
          padding:14px 24px;
          font:700 16px/22px Arial,sans-serif;
          color:#ffffff;
          text-decoration:none;
          border-radius:6px;">
        Xem đơn hàng
      </a>
    </td>
  </tr>
</table>
~~~

**role="presentation"** cho biết đây là bảng bố cục, không phải bảng dữ liệu. Thuộc tính **bgcolor** hỗ trợ một số client cũ, trong khi style inline giữ cách thể hiện rõ hơn. Tuy nhiên, có những phiên bản Outlook desktop không xử lý toàn bộ padding hoặc border-radius trên anchor như trình duyệt; nếu cần hỗ trợ nghiêm ngặt, hãy thử nghiệm riêng và cân nhắc kỹ thuật button đặc thù.

**Không có nút HTML nào bảo đảm hiển thị giống hệt trên mọi email client**. Điều quan trọng là nhãn và href vẫn rõ, bấm được và có link dự phòng.

## 6. Nút chính và link dự phòng

Một thông điệp giao dịch nên đặt hành động chính ngay sau đoạn mô tả ngắn:

~~~text
Đơn hàng đã được xác nhận

Chúng tôi đã nhận thông tin đơn hàng.

        [ Xem đơn hàng ]

Nếu nút không hoạt động, mở liên kết:
https://example.com/orders

Cần hỗ trợ? https://example.com/support
~~~

Link dự phòng có ích khi một client hiển thị nút không như dự kiến hoặc người dùng muốn sao chép URL. Tuy vậy, một URL quá dài có token nhạy cảm có thể khó đọc và dễ lộ qua việc chuyển tiếp; thiết kế đường dẫn cần cân nhắc bảo mật.

Đối với email chứa thao tác quan trọng, nên đảm bảo **nội dung thư tự giải thích điều gì đã xảy ra và người dùng cần làm gì**, không chỉ có một ảnh hoặc một nút không rõ đích.

## 7. Mẫu HTML responsive một cột đầy đủ

Mẫu sau có tiêu đề, đoạn mô tả, CTA, link dự phòng và footer. Bố cục cơ sở là bảng rộng 100%; media query chỉ nâng cao giao diện trên các client hỗ trợ.

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Đơn hàng đã được xác nhận</title>
  <style>
    @media screen and (max-width:480px) {
      .mobile-pad { padding:20px 16px !important; }
      .mobile-title { font-size:23px !important; }
      .mobile-cta { display:block !important; text-align:center !important; }
    }
  </style>
</head>
<body style="margin:0;padding:0;background-color:#f3f5f8;">
  <div
    style="
      display:none;
      font-size:1px;
      line-height:1px;
      max-height:0;
      max-width:0;
      opacity:0;
      overflow:hidden;">
    Đơn hàng của bạn đã được ghi nhận. Xem thông tin ngay.
  </div>

  <table
    role="presentation"
    width="100%"
    cellpadding="0"
    cellspacing="0"
    border="0"
    style="width:100%;border-collapse:collapse;background:#f3f5f8;">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table
          role="presentation"
          width="100%"
          cellpadding="0"
          cellspacing="0"
          border="0"
          style="width:100%;max-width:600px;background:#ffffff;">
          <tr>
            <td class="mobile-pad" style="padding:32px 28px 24px;">
              <p
                style="
                  margin:0 0 12px;
                  font:700 14px/1.5 Arial,sans-serif;
                  color:#174ea6;">
                THÔNG BÁO ĐƠN HÀNG
              </p>

              <h1
                class="mobile-title"
                style="
                  margin:0 0 18px;
                  font:700 26px/1.3 Arial,sans-serif;
                  color:#18212f;">
                Đơn hàng đã được xác nhận
              </h1>

              <p
                style="
                  margin:0 0 22px;
                  font:16px/1.55 Arial,sans-serif;
                  color:#27364a;">
                Xin chào! Chúng tôi đã ghi nhận đơn hàng.
                Bạn có thể xem trạng thái và thông tin giao hàng
                trên trang tài khoản.
              </p>

              <table
                role="presentation"
                border="0"
                cellpadding="0"
                cellspacing="0">
                <tr>
                  <td
                    align="center"
                    bgcolor="#174ea6"
                    style="background:#174ea6;border-radius:6px;">
                    <a
                      class="mobile-cta"
                      href="https://example.com/orders"
                      style="
                        display:inline-block;
                        padding:14px 24px;
                        font:700 16px/22px Arial,sans-serif;
                        color:#ffffff;
                        text-decoration:none;
                        border-radius:6px;">
                      Xem đơn hàng
                    </a>
                  </td>
                </tr>
              </table>

              <p
                style="
                  margin:24px 0 6px;
                  font:14px/1.5 Arial,sans-serif;
                  color:#42546a;">
                Nếu nút không hoạt động, hãy mở liên kết:
              </p>
              <p
                style="
                  margin:0;
                  font:14px/1.5 Arial,sans-serif;
                  overflow-wrap:anywhere;">
                <a
                  href="https://example.com/orders"
                  style="color:#174ea6;text-decoration:underline;">
                  https://example.com/orders
                </a>
              </p>
            </td>
          </tr>
          <tr>
            <td
              style="
                padding:20px 28px;
                background:#f8fafc;
                border-top:1px solid #e5eaf0;">
              <p
                style="
                  margin:0;
                  font:14px/1.5 Arial,sans-serif;
                  color:#42546a;">
                Cần hỗ trợ?
                <a
                  href="https://example.com/support"
                  style="color:#174ea6;text-decoration:underline;">
                  Liên hệ bộ phận hỗ trợ
                </a>.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
~~~

Các URL **example.com** trong mẫu là ví dụ, không phải điểm đến thật. Màu sắc, font và độ tương phản cần điều chỉnh theo thiết kế của ứng dụng.

### Vì sao mẫu có thể đọc ở màn hình nhỏ?

Ngay cả khi media query bị bỏ qua, vùng ngoài và vùng trong đều dùng **width=100%**, nội dung được tổ chức một cột, font không quá nhỏ và CTA là link có href thật. Khi media query được áp dụng, padding và tiêu đề có thể điều chỉnh để bớt chiếm diện tích.

Trong một số phiên bản Outlook desktop, **max-width** có thể không hoạt động như mong đợi. Có thể bổ sung kỹ thuật hybrid/fluid table hoặc conditional markup riêng cho Outlook nếu đối tượng người dùng yêu cầu. Tuy nhiên, tránh đánh đổi nội dung dễ đọc trên mobile chỉ để duy trì một bố cục desktop quá phức tạp.

## 8. Tạo email HTML bằng Spring Framework Mail

Với Spring Boot, dependency thông dụng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Ví dụ cấu hình SMTP submission qua STARTTLS:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: account@example.com
    password: REPLACE_WITH_SECRET
    default-encoding: UTF-8
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

SMTP host và tài khoản phải được thay bằng cấu hình thật. Trong production, **password cần lấy từ biến môi trường hoặc secret manager**, không đưa bí mật vào repository hay log. Cổng SMTP và chế độ TLS cần tuân theo hướng dẫn của nhà cung cấp.

**Spring Boot** có thể tạo bean JavaMailSender khi có classpath và cấu hình phù hợp. **Spring Framework Mail** cung cấp API tạo và gửi MIME. Còn việc email có dễ đọc trên điện thoại không phụ thuộc vào chính **HTML/template**.

### SimpleMailMessage hay MimeMessage?

| Nhu cầu | API thông dụng |
|---|---|
| Email chỉ có văn bản thuần | **MailSender** + **SimpleMailMessage** |
| Email HTML | **JavaMailSender** + **MimeMessageHelper** |
| Có cả plain text và HTML | **MimeMessageHelper.setText(plainText, htmlText)** |
| Hình inline qua CID | **MimeMessageHelper.addInline(...)** |
| File đính kèm | **MimeMessageHelper.addAttachment(...)** |

Vì email trong bài có HTML và CTA được tạo kiểu, sử dụng **MimeMessage** là lựa chọn phù hợp.

## 9. Ví dụ Java hoàn chỉnh: HTML + plain text có URL hành động

Ví dụ service dưới đây tập trung vào bước tạo email. Nội dung HTML ngắn hơn mẫu ở mục 7 nhưng vẫn giữ bố cục một cột, CSS inline và vùng CTA rộng.

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderEmailService {

    private final JavaMailSender mailSender;

    public OrderEmailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderAccepted(String recipient)
            throws MessagingException {
        String plainText = """
                Đơn hàng đã được xác nhận.

                Chúng tôi đã ghi nhận đơn hàng của bạn.
                Xem thông tin: https://example.com/orders
                Hỗ trợ: https://example.com/support
                """;

        String htmlText = """
                <!doctype html>
                <html lang="vi">
                  <head>
                    <meta charset="UTF-8">
                    <meta name="viewport"
                          content="width=device-width,initial-scale=1">
                  </head>
                  <body style="margin:0;padding:0;background:#f3f5f8;">
                    <table role="presentation" width="100%"
                           cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td align="center" style="padding:20px 12px;">
                          <table role="presentation" width="100%"
                                 cellpadding="0" cellspacing="0" border="0"
                                 style="max-width:600px;background:#ffffff;">
                            <tr>
                              <td style="padding:24px 20px;">
                                <h1 style="margin:0 0 16px;
                                           font:700 24px/1.3 Arial,sans-serif;">
                                  Đơn hàng đã được xác nhận
                                </h1>
                                <p style="margin:0 0 22px;
                                          font:16px/1.5 Arial,sans-serif;">
                                  Chúng tôi đã ghi nhận đơn hàng của bạn.
                                </p>
                                <table role="presentation" border="0"
                                       cellpadding="0" cellspacing="0">
                                  <tr>
                                    <td bgcolor="#174ea6"
                                        style="background:#174ea6;">
                                      <a href="https://example.com/orders"
                                         style="display:inline-block;
                                                padding:14px 24px;
                                                font:700 16px/24px Arial,sans-serif;
                                                color:#fff;text-decoration:none;">
                                        Xem đơn hàng
                                      </a>
                                    </td>
                                  </tr>
                                </table>
                                <p style="margin:22px 0 0;
                                          font:14px/1.5 Arial,sans-serif;">
                                  Hoặc mở:
                                  <a href="https://example.com/orders">
                                    https://example.com/orders
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

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("orders@example.com");
        helper.setTo(recipient);
        helper.setSubject("Đơn hàng đã được xác nhận");
        helper.setText(plainText, htmlText);

        mailSender.send(message);
    }
}
~~~

Đây là mã minh họa; nhà cung cấp phải cho phép địa chỉ From và hệ thống cần có SMTP sender được cấu hình. Link được cố định để bài học tập trung vào bố cục; với ứng dụng thật, nên tạo **một URL nghiệp vụ từ cấu hình đáng tin cậy** rồi render cùng URL vào cả hai phiên bản HTML và plain text.

### Các bước cần hiểu

1. **JavaMailSender** được inject vào service, thường từ cấu hình Spring Boot.
2. **plainText** mô tả đầy đủ nội dung và URL người nhận cần mở.
3. **htmlText** có tiêu đề, đoạn văn, CTA và link dự phòng.
4. **createMimeMessage()** tạo đối tượng MIME.
5. **MimeMessageHelper(..., true, UTF-8)** bật multipart và encoding thích hợp.
6. **setText(plainText, htmlText)** xây hai biểu diễn nội dung thay thế nhau.
7. **send(message)** nộp thông điệp cho SMTP transport.

**Send thành công không bảo đảm email đã vào Inbox hoặc được email client hiển thị hoàn hảo**. Phải phân biệt kết quả gửi thư với chất lượng HTML ở phía người nhận.

## 10. Bản plain text là fallback thực sự

Khi tạo email HTML có nút CTA, đừng để bản plain text chỉ có câu “Hãy bật HTML để xem”. Người đọc plain text vẫn cần biết nội dung và có URL có thể sao chép.

Ví dụ:

~~~text
Đơn hàng đã được xác nhận

Xin chào!
Chúng tôi đã ghi nhận đơn hàng của bạn.

Xem chi tiết:
https://example.com/orders

Liên hệ hỗ trợ:
https://example.com/support
~~~

Trong Spring Mail:

~~~java
helper.setText(plainText, htmlText);
~~~

Phương thức này khác với:

~~~java
helper.setText(htmlText, true);
~~~

Overload thứ hai đánh dấu một body là HTML, **không tự tạo bản plain text hoàn chỉnh**. Khi có cả hai bản, thư thường chứa **multipart/alternative**:

~~~text
MimeMessage
└── multipart/alternative
    ├── text/plain
    │    └── Nội dung và URL đầy đủ
    └── text/html
         └── Nội dung và CTA <a href="...">
~~~

Nếu có thêm ảnh inline hoặc attachment, cấu trúc có thể lồng thêm **multipart/related** và **multipart/mixed**. Hai bản plain text/HTML là **hai cách thể hiện thay thế của cùng thông điệp**, không phải hai email riêng.

## 11. Template engine và dữ liệu động

Khi thư chứa tên người dùng, mã đơn hàng, thời gian hoặc liên kết riêng, không nên copy HTML dài trong từng Java service. Có thể dùng **Thymeleaf**, **FreeMarker** hoặc công cụ render email template tương đương.

~~~text
Business event
      |
      v
Tạo dữ liệu thông báo đã được kiểm tra
      |
      +--> Plain text template --> plainText
      |
      +--> HTML template -------> htmlText
      |
      v
MimeMessageHelper.setText(plainText, htmlText)
      |
      v
JavaMailSender.send(message)
~~~

Một mẫu HTML có thể chứa placeholder mà template engine xử lý:

~~~html
<h1>Đơn hàng đã được xác nhận</h1>
<p>Xin chào, [TÊN NGƯỜI NHẬN]!</p>
<a
  href="[URL ĐÃ KIỂM TRA]"
  style="
    display:inline-block;
    padding:14px 24px;
    background-color:#174ea6;
    color:#fff;
    font:700 16px/24px Arial,sans-serif;
    text-decoration:none;">
  Xem đơn hàng
</a>
~~~

Các chuỗi trong ngoặc vuông chỉ là placeholder để minh họa, không phải API Thymeleaf. Trong code thực, engine sẽ thay chúng bằng dữ liệu từ model và escape theo ngữ cảnh.

**Tách bạch hai việc:**

- **Escape HTML** cho text và các thuộc tính để dữ liệu chứa dấu ngoặc hoặc dấu nháy không làm hỏng markup.
- **Kiểm soát URL** trước khi render: chỉ dùng domain/scheme được phép, encode đúng path/query, không chấp nhận link độc hại do người dùng truyền vào.

Template engine có thể hỗ trợ escaping, nhưng không tự biến một URL không đáng tin cậy thành đích an toàn. Cần xác minh dữ liệu nghiệp vụ và bảo vệ token trong liên kết.

### Giữ URL nhất quán giữa hai bản

Nếu HTML dùng nút “Xem đơn hàng” trỏ đến một URL, bản plain text phải dùng **cùng URL nghiệp vụ**. Nên tính URL ở service hoặc builder một lần rồi render vào cả hai template để tránh sai lệch khi thay đổi cấu hình.

## 12. Liên kết nhạy cảm và bảo mật

Email chứa link xác minh tài khoản, đặt lại mật khẩu hoặc xem tài liệu có quyền truy cập cần được xem như một thành phần của quy trình bảo mật.

Những nguyên tắc cơ bản:

- Dùng **HTTPS** và domain đáng tin cậy của ứng dụng.
- Xác minh quyền truy cập tại server, không chỉ dựa vào việc người dùng có URL.
- Với token xác minh/đặt lại mật khẩu, áp dụng thời hạn sử dụng, phạm vi tác dụng và khả năng thu hồi hoặc vô hiệu hóa khi phù hợp.
- Không đưa token vào log hoặc công cụ phân tích không được bảo vệ.
- Tránh tạo liên kết theo host không tin cậy lấy trực tiếp từ request để hạn chế phishing hoặc open redirect.
- Nhãn link phải thể hiện đúng hành động; không giả mạo tên dịch vụ khác.

### Email scanner có thể mở link trước người dùng

Một số cổng bảo mật email tự truy cập URL để kiểm tra malware/phishing. Vì vậy, **không thiết kế thao tác có hậu quả nghiêm trọng chỉ bằng một GET khi mở link**.

Ví dụ thiết kế rủi ro:

~~~text
GET /delete-account?token=...
    -> Xóa ngay tài khoản mà không có bước xác nhận.
~~~

Tốt hơn là mở một trang giải thích rồi yêu cầu người dùng xác nhận hoặc xác thực phù hợp với hành động. Với unsubscribe một lần nhấp, có chuẩn và yêu cầu riêng; không đánh đồng với việc xóa tài khoản hoặc chuyển tiền.

Nếu email có click tracking, cần hiểu cách nhà cung cấp viết lại URL, các bước redirect và nghĩa của số lượt nhấp. Một lượt truy cập có thể do scanner tạo ra, không nhất thiết là người dùng chủ động thao tác.

## 13. Khả năng truy cập và trình đọc màn hình

Email đọc tốt trên mobile cũng cần phù hợp với người dùng tăng cỡ chữ hoặc sử dụng công nghệ hỗ trợ.

**Những lựa chọn nên ưu tiên:**

- Dùng heading có ý nghĩa, ví dụ một **h1** rõ ràng cho nội dung chính.
- Khai báo **lang="vi"** trong HTML khi phù hợp.
- Nút/đường link có nhãn mô tả chính xác.
- Đảm bảo **tương phản chữ và nền**; không truyền thông tin chỉ bằng màu.
- Hình minh họa quan trọng có **alt text**; hình trang trí có thể dùng alt rỗng tùy mục đích.
- Bảng dùng cho bố cục có **role="presentation"**; bảng chứa dữ liệu thực vẫn cần cấu trúc có nghĩa.
- Giữ thứ tự đọc hợp lý ngay cả khi CSS bị bỏ qua.
- Cung cấp bản **text/plain** hoàn chỉnh.

Ví dụ link có nhãn rõ:

~~~html
<a href="https://example.com/invoices">Xem hóa đơn của bạn</a>
~~~

Tránh nút chỉ chứa icon hoặc chữ “Go” mà không có ngữ cảnh. Nếu một hành động quan trọng chỉ được trình bày trong ảnh, người không tải được ảnh sẽ không biết cần làm gì.

## 14. Dark mode và hình ảnh co giãn

Nhiều ứng dụng mail hỗ trợ chế độ tối hoặc tự điều chỉnh màu. Có thể xảy ra tình huống màu chữ của nút bị thay đổi nhưng màu nền thì không, khiến độ tương phản giảm.

Hướng xử lý:

- Chọn các cặp màu dễ đọc ngay từ giao diện sáng.
- Kiểm tra cả giao diện sáng và tối ở các client quan trọng.
- Không đặt logo có chữ tối trên nền tối mà không có giải pháp hiển thị.
- Không dựa hoàn toàn vào media query dark mode vì mức hỗ trợ không đồng nhất.

### Ảnh không nên làm email bị tràn màn hình

Ví dụ hình logo inline:

~~~html
<img
  src="cid:brandLogo"
  alt="Logo thương hiệu"
  width="160"
  style="
    display:block;
    width:160px;
    max-width:100%;
    height:auto;
    border:0;">
~~~

Ví dụ banner:

~~~html
<img
  src="https://static.example.com/email/banner.png"
  alt="Thông báo chương trình"
  width="560"
  style="
    display:block;
    width:100%;
    max-width:560px;
    height:auto;
    border:0;">
~~~

Ảnh có **max-width:100%** và **height:auto** được thiết kế để co theo vùng chứa trong các client hỗ trợ. Cần tránh ảnh có width cứng lớn hơn màn hình, đồng thời giữ nội dung chính ở dạng text vì email client có thể chặn hiển thị ảnh.

Trong Spring Mail, để dùng ảnh CID cần xây MimeMessage multipart phù hợp và gọi **MimeMessageHelper.addInline(...)** với Content-ID khớp giá trị sau **cid:**. Nếu dùng hình remote, URL cần truy cập được theo chính sách email client. Cả hai phương pháp đều cần phương án fallback.

## 15. Subject, preheader và nội dung phía trên

Trong danh sách thư trên điện thoại, người nhận thường chỉ thấy một phần tên người gửi, **Subject** và vài ký tự đầu của nội dung (preheader). Vì vậy thông điệp cần rõ ngay từ đoạn mở đầu:

~~~text
Subject: Đơn hàng đã được xác nhận
Preheader: Xem trạng thái và thông tin giao hàng trong tài khoản.
~~~

Preheader thường là một đoạn nội dung ẩn ở phần đầu HTML. Ví dụ:

~~~html
<div
  style="
    display:none;
    max-height:0;
    max-width:0;
    opacity:0;
    overflow:hidden;">
  Xem trạng thái và thông tin giao hàng trong tài khoản.
</div>
~~~

Một số client có thể không tuân thủ cách ẩn này hoặc chọn đoạn khác làm preview. Preheader là **kỹ thuật thiết kế nội dung**, không phải tính năng được Spring Mail bảo đảm. Subject cũng không nên cố tạo cảm giác khẩn cấp giả; cần diễn tả đúng sự kiện.

Nút CTA chính nên nằm sau lời giải thích ngắn. Không bắt người nhận cuộn qua nhiều banner rồi mới biết email muốn họ thực hiện hành động gì.

## 16. Nội dung dài và bảng dữ liệu trên màn hình nhỏ

Nếu email chứa nhiều bước hoặc nhiều chi tiết, nên chia theo thứ tự:

~~~text
1. Chuyện gì đã xảy ra?
2. Người nhận cần làm gì?
3. CTA/link hành động
4. Thông tin chi tiết
5. Liên hệ hỗ trợ
~~~

Với thông tin đơn hàng, dạng nhãn–giá trị thường dễ đọc hơn bảng nhiều cột:

~~~text
Đơn hàng: ORD-123
Trạng thái: Đã xác nhận
Ngày dự kiến: 20/11/2026

[ Xem đơn hàng ]
~~~

Tránh dùng bảng có 6–8 cột, nhiều URL dài hoặc hình rộng cố định. Những chuỗi không có khoảng trắng có thể làm vỡ layout; CSS **overflow-wrap:anywhere** có thể hỗ trợ một số client nhưng không phải tất cả. Nếu URL hiển thị quá dài, cần thiết kế cách trình bày phù hợp và không biến nó thành một liên kết rút gọn không rõ nguồn.

## 17. Các lỗi thường gặp khi tạo email HTML mobile-friendly

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Phải cuộn ngang trên mobile | Bảng/hình có width cứng quá lớn | Dùng bố cục một cột, width 100%, max-width khi phù hợp |
| Chữ quá nhỏ | Font 10–12 px, nội dung dày | Ưu tiên body khoảng 16 px, chia đoạn |
| Nút khó chạm | Thiếu padding, các nút sát nhau | Tăng vùng chạm, tách các CTA |
| Nút không hoạt động | Dùng button/form/onclick | Dùng anchor href HTTPS thực |
| Link mở nhầm trang | URL tương đối, sai domain hoặc redirect sai | Kiểm tra URL tuyệt đối và đích đến |
| Bản plain text thiếu URL | Chỉ gửi HTML hoặc text là câu yêu cầu bật HTML | Dùng setText(plainText, htmlText) và thêm URL thật |
| Outlook hiển thị khác Gmail | Hỗ trợ CSS/engine render khác nhau | Table layout, CSS inline, kiểm tra client mục tiêu |
| Dark mode khó đọc | Màu chữ/nền đổi không đồng nhất | Kiểm tra tương phản và giao diện tối |
| Ảnh tràn màn hình | Width cố định, thiếu max-width | Dùng hình co giãn và alt text |
| Logo không hiện | Ảnh remote bị chặn, CID sai, client không hỗ trợ | Fallback văn bản và kiểm tra URL/Content-ID |
| URL dài phá layout | Chuỗi không có khoảng trắng | CSS xuống dòng nơi được hỗ trợ, thiết kế link đọc được |
| Tiếng Việt bị sai ký tự | Charset hoặc MIME encoding không phù hợp | Sử dụng UTF-8 qua MimeMessageHelper |
| Email vào Spam | Chính sách gửi/nhận, uy tín miền/IP, SPF/DKIM/DMARC | Điều tra SMTP và hệ thống nhận, không chỉ sửa CSS |

### Lỗi HTML và lỗi gửi thư không giống nhau

**JavaMailSender.send(...)** có thể thất bại vì SMTP AUTH, TLS, DNS, timeout, policy hoặc recipient bị từ chối. Đó không phải lỗi responsive HTML. Ngược lại, nếu SMTP đã chấp nhận thư nhưng client hiển thị font nhỏ hoặc nút xấu, cần kiểm tra template và email client.

Một số exception ở tầng Spring Mail gồm **MailAuthenticationException**, **MailSendException** và **MailPreparationException**. Đối với MIME, **MessagingException** có thể phát sinh khi tạo thông điệp. Xem nguyên nhân cụ thể trước khi áp dụng retry; gửi lại không sửa được một template HTML hiển thị sai.

## 18. Quy trình thử nghiệm trên nhiều email client

Trước khi dùng một template HTML trong production, nên gửi thử vào SMTP sandbox hoặc test inbox và mở trên các client mục tiêu.

1. Xác nhận **Subject**, preheader và nội dung mở đầu dễ hiểu.
2. Thử đọc trên màn hình hẹp khoảng **320–400 px**, trên desktop và khi tăng cỡ chữ.
3. Thử trên các client người dùng thực sự dùng, ví dụ Gmail, Outlook hoặc Apple Mail khi phù hợp.
4. Tắt ảnh để kiểm tra alt text và nội dung fallback.
5. Xem giao diện sáng và tối.
6. Chạm tất cả CTA/link: kiểm tra vùng chạm, domain, URL cuối, quyền truy cập và redirect.
7. Đọc bản plain text: phải đủ nội dung và có URL hành động.
8. Dùng tên người dùng dài, mã đơn hàng dài, ký tự tiếng Việt và URL dài để kiểm tra xuống dòng.
9. Nếu cần, xem raw MIME để xác nhận Content-Type, charset và các phần alternative.

Một trình duyệt hiển thị HTML đẹp không đủ chứng minh email sẽ hiển thị đúng trong mọi ứng dụng mail. Việc thử trên **email client thật hoặc công cụ preview chuyên dụng** mới phát hiện được các khác biệt đáng kể.

Không gửi email thử tới khách hàng production. Nếu raw message chứa token, email người nhận hoặc dữ liệu riêng, cần lưu giữ và chia sẻ trong phạm vi được phép.

## 19. Thiết kế template có thể tái sử dụng

Khi ứng dụng có nhiều mẫu email, có thể tách thành các khối dùng chung:

~~~text
Business event
     |
     v
Notification model
     |
     v
Template renderer
     +--> Header / Logo
     +--> Nội dung chính
     +--> CTA dạng liên kết
     +--> Link dự phòng
     +--> Footer
     |
     +--> Plain text alternative
     |
     v
MimeMessageHelper
     |
     v
JavaMailSender.send(...)
~~~

Mỗi khối CTA nên nhận **URL đã được kiểm tra** và **nhãn rõ ràng**; không nhận markup tùy ý từ request người dùng. Template engine giúp giữ font, khoảng cách, màu và hành vi mobile nhất quán giữa email giao dịch và email thông báo khác.

Với email tiếp thị, ngoài thiết kế còn cần quản lý việc người nhận đồng ý đăng ký, cơ chế hủy nhận và chính sách vận hành liên quan. **MimeMessageHelper không tự giải quyết các quy tắc về danh sách người đăng ký**.

## 20. Bảng kiểm thiết kế trước khi gửi

| Nhóm | Câu hỏi cần trả lời |
|---|---|
| Nội dung | Người đọc có hiểu sự kiện ngay trong vài dòng đầu? |
| Responsive | Có đọc trên màn hình nhỏ mà không phải cuộn ngang? |
| Font | Chữ đủ lớn và line-height dễ đọc? |
| CTA | Vùng chạm rộng, nhãn rõ, một hành động chính nổi bật? |
| Liên kết | URL HTTPS tuyệt đối, đúng đích, đúng quyền và không gây hiểu nhầm? |
| Fallback | Có link dạng văn bản và bản plain text đầy đủ? |
| Ảnh | Nếu ảnh không tải, thông điệp vẫn hiểu được? |
| Khả năng truy cập | Heading, alt text, độ tương phản và thứ tự đọc hợp lý? |
| Dark mode | Chữ, nút và logo còn nhìn rõ? |
| Dữ liệu động | Text/attribute được escape; URL/token được kiểm soát? |
| MIME | Có UTF-8, text/plain và text/html phù hợp? |
| Tương thích | Đã thử với các email client trọng yếu chưa? |

Đây là các tiêu chí **thiết kế và vận hành email HTML**, không phải một cơ chế kiểm tra tự động có sẵn trong Spring Framework Mail.

## 21. Tổng kết

Trong **Spring Framework Mail**, việc gửi email HTML với link và CTA được thực hiện bằng **JavaMailSender** và **MimeMessageHelper**. Nhưng để người nhận có thể đọc và thao tác trên màn hình nhỏ, nội dung cần có **bố cục một cột linh hoạt, chữ dễ đọc, link mô tả rõ đích đến, nút CTA là thẻ a có href thực với vùng chạm đủ lớn**, và phương án dự phòng khi CSS hoặc ảnh không hiển thị.

Nên dùng bảng bố cục đơn giản và CSS inline làm nền tảng, bổ sung media query khi cần, rồi kiểm tra trên các email client trọng yếu. Khi gửi từ Java, sử dụng **MimeMessageHelper.setText(plainText, htmlText)** để cung cấp hai biểu diễn nội dung tương đương; kiểm soát URL và dữ liệu động, không phụ thuộc JavaScript hoặc form trong email.

**Email đẹp trên desktop chưa đủ: một thông điệp chỉ thực sự hữu ích khi người nhận có thể hiểu, tìm đúng hành động và thực hiện thao tác một cách tin cậy trên điện thoại.**
