# Thiết kế multipart/alternative cho plain text và HTML

## 1. Vì sao một email nên có cả plain text và HTML?

Trong **Spring Framework Mail**, một thông điệp có thể cung cấp nhiều cách biểu diễn cùng một nội dung. Ví dụ, email xác nhận đơn hàng có thể được viết dưới dạng văn bản thuần để dễ đọc ở mọi môi trường, đồng thời có một phiên bản HTML với tiêu đề, bảng thông tin và nút hành động.

Thay vì gửi hai email riêng, ứng dụng có thể đặt hai phiên bản vào cùng một cấu trúc MIME **multipart/alternative**. Email client nhận thông điệp rồi chọn cách biểu diễn phù hợp với khả năng và tùy chọn hiển thị của nó.

Một email có hai phiên bản thường có ý nghĩa như sau:

- **text/plain**: nội dung văn bản không có markup HTML, dễ đọc, tìm kiếm, sao chép và dùng trong môi trường hạn chế.
- **text/html**: nội dung có cấu trúc trình bày, liên kết, bảng, hình ảnh hoặc kiểu chữ.
- **multipart/alternative**: khai báo rằng các phần trên là những cách biểu diễn thay thế của cùng một nội dung.

Ví dụ, một thư xác nhận:

~~~text
Plain text:
Đơn hàng ORD-2026-015 đã được xác nhận.
Xem chi tiết: https://example.com/orders/ORD-2026-015

HTML:
<h1>Đơn hàng đã được xác nhận</h1>
<p>Mã đơn hàng: ORD-2026-015</p>
<a href="https://example.com/orders/ORD-2026-015">Xem đơn hàng</a>
~~~

Người dùng đọc ở chế độ text vẫn có đầy đủ thông tin và URL. Người dùng đọc HTML có thể thấy tiêu đề, bố cục và CTA. Cả hai phiên bản cùng diễn tả **một thông báo**, không phải hai thông điệp khác nhau.

**Mục tiêu của multipart/alternative là cung cấp lựa chọn biểu diễn tương đương cho cùng nội dung**, không phải tạo hai bản có dữ liệu hoặc hành động mâu thuẫn.

## 2. multipart/alternative trong MIME có nghĩa gì?

MIME cho phép một email có nhiều phần nội dung. Subtype **alternative** được dùng khi các phần là những cách thể hiện thay thế nhau. Ví dụ:

~~~text
MimeMessage
└── multipart/alternative
    ├── text/plain
    └── text/html
~~~

Một phần MIME thường có các header như:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Đơn hàng ORD-2026-015 đã được xác nhận.
Xem chi tiết: https://example.com/orders/ORD-2026-015
~~~

Phần HTML có thể có:

~~~text
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<html lang="vi">
  <body>
    <h1>Đơn hàng đã được xác nhận</h1>
    <p>Mã đơn hàng: ORD-2026-015</p>
    <a href="https://example.com/orders/ORD-2026-015">Xem đơn hàng</a>
  </body>
</html>
~~~

Ví dụ trên mô tả ý nghĩa của các phần MIME; khi gửi thật, Jakarta Mail sẽ tạo boundary, header và transfer encoding cần thiết. Ứng dụng nên dùng API Spring Mail thay vì tự nối raw MIME.

### Thứ tự các phần có ý nghĩa

Theo quy ước MIME, các phần trong multipart/alternative được sắp xếp từ biểu diễn ít được ưu tiên hơn đến biểu diễn được ưu tiên hơn. Vì vậy cách sắp xếp thường dùng là:

1. **text/plain** trước.
2. **text/html** sau.

Email client có thể chọn phần phù hợp nhất với khả năng và tùy chọn của nó. Đặt HTML sau plain text thể hiện HTML là phiên bản giàu định dạng hơn khi client hỗ trợ.

Không nên đảo thứ tự tùy tiện hoặc thêm hai phần HTML khác nhau rồi mong client tự hiểu đó là những bước nội dung nối tiếp. Nếu các phần là những nội dung độc lập, cần chọn cấu trúc MIME khác.

## 3. multipart/alternative khác multipart/mixed và multipart/related

Ba subtype này giải quyết ba nhu cầu khác nhau:

| MIME subtype | Ý nghĩa | Ví dụ |
|---|---|---|
| **multipart/alternative** | Nhiều biểu diễn thay thế của cùng nội dung | Plain text và HTML |
| **multipart/mixed** | Nhiều thành phần độc lập đi cùng một email | Body email và file PDF đính kèm |
| **multipart/related** | Các phần liên quan để tạo nên một nội dung | HTML và ảnh inline được tham chiếu bằng CID |

Ví dụ:

~~~text
Email chỉ có hai phiên bản nội dung:
multipart/alternative
  ├── text/plain
  └── text/html

Email có nội dung và file PDF:
multipart/mixed
  ├── multipart/alternative
  │   ├── text/plain
  │   └── text/html
  └── application/pdf (attachment)

Email có HTML tham chiếu ảnh inline:
multipart/related
  ├── text/html
  └── image/png (Content-ID)
~~~

Khi email vừa có plain text, HTML, ảnh inline và attachment, các phần có thể được lồng nhau:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain
    │   │   └── text/html
    │   └── image/png (Content-ID)
    └── application/pdf (attachment)
~~~

Đây là sơ đồ quan hệ logic. Cây MIME cụ thể do MimeMessageHelper và Jakarta Mail tạo có thể khác theo multipart mode. Điều quan trọng là **alternative dùng cho các phiên bản thay thế**, **mixed dùng cho các phần độc lập** và **related dùng cho các tài nguyên được phần nội dung tham chiếu**.

Không đặt file PDF như một phiên bản alternative của HTML. PDF là tệp đính kèm riêng, không phải cách thể hiện thay thế của body.

## 4. Khi nào nên cung cấp cả hai phiên bản?

Với email nghiệp vụ, việc có plain text và HTML thường hữu ích vì:

- Một số client hoặc người dùng ưu tiên chế độ text.
- Nội dung vẫn có thể đọc khi CSS, hình ảnh hoặc một phần HTML không hiển thị.
- Plain text thường dễ sao chép và tìm kiếm.
- Trình đọc màn hình và môi trường hiển thị hạn chế có thể sử dụng nội dung text thuận tiện hơn.
- Một số gateway, công cụ lưu trữ hoặc hệ thống xử lý email có thể cần phần text đơn giản.
- Người nhận vẫn hiểu thông báo khi email client loại bỏ markup hoặc không hỗ trợ một số thành phần HTML.

### Ví dụ nội dung nên có hai phiên bản

| Loại email | Plain text cần có | HTML có thể bổ sung |
|---|---|---|
| Xác nhận đơn hàng | Mã đơn, trạng thái, URL xem đơn | Tiêu đề, bảng tóm tắt, CTA |
| Đặt lại mật khẩu | Lý do gửi, link đặt lại, thời hạn | Bố cục hướng dẫn và nút |
| Hóa đơn | Mã hóa đơn, số tiền, cách xem/tải | Bảng chi tiết và liên kết |
| Báo cáo | Kết luận chính, số liệu quan trọng | Biểu đồ, bảng và phân cấp tiêu đề |
| Thông báo lịch | Thời gian, địa điểm, hướng dẫn | Bố cục lịch và nút thêm vào ứng dụng |

Với email chỉ có một dòng text đơn giản, không nhất thiết phải tạo HTML. **SimpleMailMessage** thường đủ. Khi cần hai biểu diễn, HTML hoặc MIME phức tạp, dùng **JavaMailSender** và **MimeMessage**.

## 5. Plain text và HTML phải tương đương về ý nghĩa

Hai phiên bản không cần có cùng cách trình bày hoặc cùng số ký tự, nhưng cần cung cấp **cùng thông tin nghiệp vụ và cùng hành động chính**.

Ví dụ HTML có:

- Mã đơn hàng.
- Trạng thái đơn hàng.
- Ngày dự kiến giao.
- Nút xem đơn hàng.

Plain text cũng cần có các thông tin đó, cùng URL thực để người nhận có thể mở.

### Ví dụ chưa tốt

~~~text
Đơn hàng của bạn đã được xác nhận.
Vui lòng bật HTML để xem chi tiết.
~~~

Nếu người dùng chọn plain text, họ không có mã đơn hàng, trạng thái, ngày giao hay đường dẫn cần thiết.

### Ví dụ tốt hơn

~~~text
Đơn hàng đã được xác nhận

Mã đơn hàng: ORD-2026-015
Trạng thái: Đã xác nhận
Ngày dự kiến giao: 20/11/2026

Xem chi tiết:
https://example.com/orders/ORD-2026-015

Cần hỗ trợ:
https://example.com/support
~~~

HTML có thể trình bày các dữ liệu đó bằng bảng, tiêu đề và nút. Plain text vẫn đầy đủ để người nhận hiểu và thao tác.

### Không để hai phiên bản mâu thuẫn

Các lỗi thường gặp:

- Plain text ghi ngày giao 20/11 nhưng HTML ghi 21/11.
- Nút HTML trỏ tới một đơn hàng nhưng URL plain text trỏ sang đơn khác.
- HTML nói thanh toán đã hoàn tất nhưng plain text nói đang chờ.
- HTML hiển thị số tiền đã định dạng theo một loại tiền tệ, plain text dùng loại tiền khác.
- Một phiên bản chứa thời hạn hoặc cảnh báo quan trọng mà phiên bản kia bỏ sót.

Nên tạo hai bản từ **cùng một mô hình dữ liệu đã được xác thực**, thay vì viết hai luồng lấy dữ liệu độc lập.

## 6. Tạo multipart/alternative bằng MimeMessageHelper

Trong Spring Framework Mail, cách thông dụng là dùng **JavaMailSender** để tạo MimeMessage, sau đó sử dụng overload **MimeMessageHelper.setText(plainText, htmlText)**:

~~~java
helper.setText(plainText, htmlText);
~~~

Overload này cho Spring biết rằng ứng dụng cung cấp hai biểu diễn nội dung. Helper tạo cấu trúc alternative phù hợp trong MimeMessage.

Ví dụ:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class NotificationMailService {

    private final JavaMailSender mailSender;

    public NotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderAccepted(String recipient)
            throws MessagingException {
        String plainText = """
                Đơn hàng đã được xác nhận

                Mã đơn hàng: ORD-2026-015
                Trạng thái: Đã xác nhận

                Xem chi tiết:
                https://example.com/orders/ORD-2026-015
                """;

        String htmlText = """
                <!doctype html>
                <html lang="vi">
                  <head>
                    <meta charset="UTF-8">
                  </head>
                  <body>
                    <h1>Đơn hàng đã được xác nhận</h1>
                    <p><strong>Mã đơn hàng:</strong> ORD-2026-015</p>
                    <p><strong>Trạng thái:</strong> Đã xác nhận</p>
                    <p>
                      <a href="https://example.com/orders/ORD-2026-015">
                        Xem chi tiết đơn hàng
                      </a>
                    </p>
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

Ví dụ giả định ứng dụng đã có **JavaMailSender** được cấu hình hợp lệ, SMTP server cho phép địa chỉ From và URL minh họa được thay bằng domain thật của ứng dụng.

### Giải thích

1. **createMimeMessage()** tạo một thông điệp MIME mới.
2. **MimeMessageHelper(..., true, UTF-8)** bật chế độ multipart và thiết lập encoding.
3. **setFrom**, **setTo**, **setSubject** đặt các header cơ bản.
4. **setText(plainText, htmlText)** thiết lập hai biểu diễn thay thế.
5. **send(message)** chuyển message cho mail transport.

Trong ví dụ, plain text được đặt trước trong lời gọi và HTML ở tham số thứ hai. Không đảo hai tham số vì chữ ký phương thức xác định thứ tự là **plainText, htmlText**.

## 7. Khác biệt giữa setText(plainText, htmlText) và setText(htmlText, true)

Đây là điểm quan trọng khi thiết kế nhiều định dạng.

### Cung cấp cả plain text và HTML

~~~java
helper.setText(plainText, htmlText);
~~~

Phương thức này tạo hai biểu diễn:

- Một phần **text/plain**.
- Một phần **text/html**.

Đây là lựa chọn phù hợp khi ứng dụng muốn dùng **multipart/alternative**.

### Chỉ cung cấp HTML

~~~java
helper.setText(htmlText, true);
~~~

Tham số boolean cho biết nội dung là HTML. Cách này đặt một body HTML; nó **không tự sinh một bản plain text tương đương**.

| API | Kết quả | Trường hợp |
|---|---|---|
| **setText(text)** | Body text/plain | Email chỉ có văn bản |
| **setText(html, true)** | Body HTML | Email chỉ cung cấp HTML |
| **setText(plain, html)** | Hai biểu diễn thay thế | Email muốn hỗ trợ cả text và HTML |

Nếu gọi nhiều setter liên tiếp trên cùng helper, lần gọi sau có thể thay thế hoặc thay đổi nội dung đã thiết lập. Không nên gọi **setText(html, true)** rồi gọi **setText(plain, html)** với kỳ vọng hai lần gọi sẽ tự cộng thêm các body part. Hãy chọn overload đúng với mục tiêu ngay từ đầu.

## 8. Cấu hình charset và encoding

Email có nội dung tiếng Việt cần được xử lý đúng charset. Ví dụ:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        true,
        StandardCharsets.UTF_8.name()
);
~~~

UTF-8 giúp biểu diễn các ký tự như **ă, â, ê, ô, ơ, ư, đ** và dấu thanh. Nếu cấu hình charset không phù hợp, người nhận có thể thấy ký tự lỗi hoặc dấu hỏi.

### Charset và Content-Transfer-Encoding là hai khái niệm khác nhau

- **charset** cho biết cách giải mã các byte thành ký tự, ví dụ UTF-8.
- **Content-Transfer-Encoding** mô tả cách biểu diễn dữ liệu để truyền qua MIME, ví dụ quoted-printable hoặc base64.

Ví dụ một phần:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

Jakarta Mail lựa chọn cách transfer encoding phù hợp trong quá trình tạo thông điệp. Ứng dụng nên dùng API Spring Mail để đặt encoding thay vì tự mã hóa body thành base64 hoặc quoted-printable rồi đưa vào setText.

### Subject và tên người gửi

Subject có dấu tiếng Việt cũng cần được MIME xử lý đúng. Khi sử dụng **MimeMessageHelper** với encoding UTF-8, helper/Jakarta Mail có thể mã hóa header theo cơ chế phù hợp. Không tự nối chuỗi base64 vào subject.

## 9. Tổ chức dữ liệu dùng chung cho hai phiên bản

Một lỗi thiết kế phổ biến là viết hai template độc lập rồi truy vấn database riêng cho từng template. Điều này có thể làm hai bản nội dung khác nhau nếu dữ liệu thay đổi giữa hai lần truy vấn.

Nên tạo một mô hình thông báo thống nhất:

~~~text
Order / Business event
          |
          v
Notification data
  - customerName
  - orderCode
  - orderStatus
  - deliveryDate
  - orderUrl
          |
          +-------------------+
          |                   |
          v                   v
   Plain text renderer    HTML renderer
          |                   |
          v                   v
      plainText             htmlText
          |                   |
          +---------+---------+
                    |
                    v
       MimeMessageHelper.setText(...)
                    |
                    v
          JavaMailSender.send(...)
~~~

Ví dụ record dữ liệu:

~~~java
import java.time.LocalDate;

public record OrderEmailData(
        String customerName,
        String orderCode,
        String orderStatus,
        LocalDate deliveryDate,
        String orderUrl
) {
}
~~~

Từ cùng object **OrderEmailData**, hai renderer tạo nội dung khác cách trình bày nhưng dùng cùng mã đơn, trạng thái, ngày giao và URL.

### Tại sao không lấy dữ liệu hai lần?

Giả sử trạng thái đơn hàng thay đổi từ **Đang xử lý** sang **Đã xác nhận** giữa hai lần truy vấn. Nếu plain text được render trước và HTML được render sau, người nhận có thể nhận một email mà hai phiên bản mâu thuẫn. Snapshot dữ liệu trước khi render giúp tránh tình huống đó.

Nếu việc gửi email được trì hoãn trong queue, hãy lưu dữ liệu hoặc định danh snapshot cần thiết để cả hai phiên bản được render từ cùng một trạng thái nghiệp vụ. Đừng giữ một object mutable có thể bị luồng khác thay đổi trong khi callback/template đang chạy.

## 10. Render HTML và plain text bằng template engine

Với email đơn giản, có thể dùng text block như ví dụ trước. Với hệ thống có nhiều loại email, template engine như **Thymeleaf** hoặc **FreeMarker** giúp quản lý nội dung riêng cho từng định dạng.

Luồng điển hình:

~~~text
Notification model
        |
        +--> templates/order-accepted.txt
        |          |
        |          v
        |       plainText
        |
        +--> templates/order-accepted.html
                   |
                   v
                htmlText
        |
        v
MimeMessageHelper.setText(plainText, htmlText)
~~~

Có thể dùng một renderer cho mỗi loại:

~~~java
String plainText = plainTextRenderer.render("order-accepted", data);
String htmlText = htmlRenderer.render("order-accepted", data);

helper.setText(plainText, htmlText);
~~~

**plainTextRenderer** và **htmlRenderer** là các thành phần do ứng dụng xây dựng; đây không phải API mặc định của Spring Mail.

### Template plain text

~~~text
Xin chào, ${customerName}!

Đơn hàng ${orderCode} đã được xác nhận.
Trạng thái: ${orderStatus}
Ngày dự kiến giao: ${deliveryDate}

Xem chi tiết:
${orderUrl}
~~~

### Template HTML

~~~html
<h1>Đơn hàng đã được xác nhận</h1>
<p>Xin chào, <strong>${customerName}</strong>!</p>
<p>Mã đơn hàng: ${orderCode}</p>
<p>Trạng thái: ${orderStatus}</p>
<p>Ngày dự kiến giao: ${deliveryDate}</p>
<p><a href="${orderUrl}">Xem chi tiết đơn hàng</a></p>
~~~

Các placeholder **${...}** trong ví dụ là ký hiệu minh họa, không khẳng định template engine nào tự hiểu chúng theo đúng cú pháp. Cần cấu hình template engine và model tương ứng.

### Escape dữ liệu đúng ngữ cảnh

Tên người dùng và các chuỗi từ dữ liệu nghiệp vụ có thể chứa ký tự đặc biệt. Trong HTML, text và thuộc tính href phải được escape đúng ngữ cảnh. URL cần được kiểm tra domain/scheme, encode path/query rồi HTML-escape khi đưa vào thuộc tính.

Không nối trực tiếp dữ liệu không tin cậy vào HTML. Template engine thường hỗ trợ escaping, nhưng cần dùng đúng chế độ; không bật chế độ chèn HTML thô cho nội dung người dùng nếu chưa được làm sạch.

Plain text không cần HTML escaping, nhưng vẫn cần loại bỏ hoặc xử lý ký tự điều khiển không mong muốn và trình bày URL hợp lý.

## 11. Thiết kế bản plain text dễ đọc

Plain text không nên là một chuỗi HTML bị xóa thẻ một cách máy móc. Nó cần được biên tập để đọc tự nhiên:

- Dùng tiêu đề ngắn ở đầu thư.
- Chia đoạn bằng dòng trống.
- Dùng nhãn cho các giá trị như mã đơn, trạng thái, thời gian.
- Giữ URL thực cho hành động chính.
- Dùng dấu gạch đầu dòng cho danh sách.
- Không nhồi toàn bộ dữ liệu vào một dòng dài.
- Nếu có bảng HTML, chuyển sang dạng nhãn–giá trị hoặc danh sách phù hợp.

Ví dụ:

~~~text
BÁO CÁO THÁNG 10

Doanh thu: 125.000.000 VND
Số đơn hàng: 340
Tăng trưởng so với tháng trước: 8%

Điểm cần chú ý:
- Nhóm A tăng trưởng tốt.
- Nhóm B cần xem lại tỷ lệ hoàn hàng.

Mở báo cáo đầy đủ:
https://example.com/reports/2026-10
~~~

HTML có thể dùng bảng và biểu đồ, nhưng plain text vẫn cần giữ kết luận và đường dẫn.

## 12. HTML nên có cấu trúc rõ ràng và có fallback

Phiên bản HTML có thể dùng tiêu đề, đoạn, bảng và liên kết:

~~~html
<!doctype html>
<html lang="vi">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
  </head>
  <body>
    <h1>Báo cáo tháng 10</h1>
    <p>Doanh thu: <strong>125.000.000 VND</strong></p>
    <p>Số đơn hàng: <strong>340</strong></p>
    <p>Tăng trưởng: <strong>8%</strong></p>
    <h2>Điểm cần chú ý</h2>
    <ul>
      <li>Nhóm A tăng trưởng tốt.</li>
      <li>Nhóm B cần xem lại tỷ lệ hoàn hàng.</li>
    </ul>
    <p>
      <a href="https://example.com/reports/2026-10">
        Mở báo cáo đầy đủ
      </a>
    </p>
  </body>
</html>
~~~

Không nên để thông tin quan trọng chỉ xuất hiện trong hình hoặc màu sắc. Nếu ảnh bị chặn, HTML vẫn cần truyền tải được ý chính; plain text cũng cần có kết luận và URL.

Với email hiển thị trên điện thoại, nên dùng bố cục một cột linh hoạt, chữ đủ lớn, link có nhãn rõ và CTA có vùng chạm phù hợp. Không phụ thuộc JavaScript, form hoặc CSS hiện đại mà email client có thể loại bỏ.

## 13. Ví dụ với HTML có nút CTA và plain text có URL

Một nút HTML nên là thẻ **a** có href thật, được tạo kiểu như nút:

~~~html
<a
  href="https://example.com/orders/ORD-2026-015"
  style="
    display:inline-block;
    padding:14px 24px;
    background-color:#174ea6;
    color:#ffffff;
    font:700 16px/22px Arial,sans-serif;
    text-decoration:none;">
  Xem đơn hàng
</a>
~~~

Plain text cần có URL tương ứng:

~~~text
Xem chi tiết đơn hàng:
https://example.com/orders/ORD-2026-015
~~~

Không chỉ ghi:

~~~text
Nhấn vào nút bên dưới để xem đơn hàng.
~~~

vì trong plain text không có nút để người đọc nhấn.

Với liên kết nhạy cảm như đặt lại mật khẩu hoặc xác nhận giao dịch, URL phải dùng HTTPS, domain được kiểm soát, token có phạm vi và thời hạn phù hợp. Không log token và không dùng GET để thực hiện ngay thao tác có hậu quả không thể đảo ngược chỉ vì email scanner có thể tự truy cập URL.

## 14. Kết hợp multipart/alternative với attachment

Nếu email có plain text, HTML và PDF attachment, cấu trúc MIME thường dùng **multipart/mixed** ở lớp ngoài, với phần body là **multipart/alternative**:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/alternative
    │   ├── text/plain
    │   └── text/html
    └── application/pdf
        └── Content-Disposition: attachment
~~~

Ví dụ:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        true,
        StandardCharsets.UTF_8.name()
);

helper.setFrom("billing@example.com");
helper.setTo(recipient);
helper.setSubject("Hóa đơn của bạn");
helper.setText(
        "Hóa đơn được đính kèm trong email này.",
        "<html lang=\"vi\"><body>"
                + "<h1>Hóa đơn của bạn</h1>"
                + "<p>Hóa đơn PDF được đính kèm.</p>"
                + "</body></html>"
);
helper.addAttachment(
        "invoice.pdf",
        new ClassPathResource("mail/invoice.pdf"),
        "application/pdf"
);

mailSender.send(message);
~~~

Ví dụ giả định **recipient**, **mailSender** và tài nguyên PDF đã được chuẩn bị hợp lệ. **setText(plain, html)** tạo hai biểu diễn nội dung; **addAttachment** thêm một phần độc lập.

### Vì sao attachment không nằm trong alternative?

Nếu đặt PDF như một alternative của HTML, client có thể hiểu PDF là một cách biểu diễn khác của body và chọn một phần thay thế, thay vì coi nó là tệp cần đi cùng thư. **Attachment có mục đích độc lập**, nên thường nằm trong multipart/mixed.

## 15. Kết hợp multipart/alternative với inline resource

Khi HTML tham chiếu ảnh qua CID, phần HTML và ảnh cần có quan hệ **multipart/related**. Nếu đồng thời có plain text, một cấu trúc logic có thể là:

~~~text
MimeMessage
└── multipart/related
    ├── multipart/alternative
    │   ├── text/plain
    │   └── text/html
    │       └── <img src="cid:brandLogo">
    └── image/png
        └── Content-ID: <brandLogo>
~~~

Khi có thêm attachment, có thể có multipart/mixed bao ngoài. Cây chính xác phụ thuộc multipart mode của MimeMessageHelper và cách Jakarta Mail tổ chức body.

Ví dụ:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name()
);

helper.setFrom("news@example.com");
helper.setTo(recipient);
helper.setSubject("Bản tin mới");
helper.setText(
        "Bản tin mới đã sẵn sàng. Xem tại https://example.com/news",
        """
        <html lang="vi">
          <body>
            <img src="cid:brandLogo" alt="Logo thương hiệu">
            <h1>Bản tin mới</h1>
            <p>Bản tin tháng này đã sẵn sàng.</p>
            <a href="https://example.com/news">Đọc bản tin</a>
          </body>
        </html>
        """
);
helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);

mailSender.send(message);
~~~

Thứ tự nên dùng là **setText trước addInline**. Bản plain text phải giữ nội dung và link; ảnh logo chỉ là thành phần hỗ trợ cho HTML.

## 16. Multipart mode trong MimeMessageHelper

MimeMessageHelper cung cấp các chế độ multipart:

| Mode | Mục đích tổng quát | Trường hợp |
|---|---|---|
| **MULTIPART_MODE_NO** | Không dùng multipart | Nội dung đơn giản, không cần MIME part bổ sung |
| **MULTIPART_MODE_MIXED** | multipart/mixed | Body cùng attachment |
| **MULTIPART_MODE_RELATED** | multipart/related | HTML có inline resource |
| **MULTIPART_MODE_MIXED_RELATED** | Kết hợp mixed và related | Email có inline resource và attachment |

Với **setText(plainText, htmlText)**, helper tạo nội dung alternative. Khi cần thêm attachment hoặc inline resource, bật multipart và chọn mode phù hợp để các phần được lồng đúng mục đích.

Ví dụ constructor phổ biến:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        true,
        StandardCharsets.UTF_8.name()
);
~~~

Tham số **true** bật multipart. Khi có nhiều loại part, chọn mode tường minh giúp code thể hiện ý định rõ hơn:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name()
);
~~~

Không nên suy luận rằng một constructor multipart luôn tạo cùng một cây MIME trong mọi tình huống. Cấu trúc cuối phụ thuộc việc ứng dụng gọi setText, addInline, addAttachment và multipart mode nào.

## 17. Cấu hình Spring Boot cho JavaMailSender

Trong ứng dụng Spring Boot, dependency thường dùng:

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
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
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

**smtp.example.com** chỉ là host minh họa. Trong môi trường thật, thay bằng SMTP server của tổ chức và nạp username/password từ biến môi trường hoặc secret manager. Không commit credential thật vào repository.

Spring Boot có thể tự cấu hình bean **JavaMailSender** khi dependency và cấu hình phù hợp. Service chỉ cần inject interface; việc tạo nội dung plain text và HTML vẫn thuộc ứng dụng.

Nếu ứng dụng tự khai báo nhiều bean JavaMailSender, cần chọn rõ bằng **@Qualifier** hoặc một router. Auto-configuration không tự quyết định email nào nên đi qua sender nào.

## 18. Tạo nội dung động từ một model

Ví dụ service nhận model:

~~~java
public record OrderEmailData(
        String customerName,
        String orderCode,
        String status,
        String orderUrl
) {
}
~~~

Một renderer có thể tạo hai phiên bản:

~~~java
public record RenderedMail(String plainText, String htmlText) {
}

public RenderedMail render(OrderEmailData data) {
    String plainText = """
            Xin chào %s,

            Đơn hàng %s có trạng thái: %s.
            Xem chi tiết: %s
            """.formatted(
            data.customerName(),
            data.orderCode(),
            data.status(),
            data.orderUrl()
    );

    String htmlText = """
            <html lang="vi">
              <body>
                <h1>Thông tin đơn hàng</h1>
                <p>Xin chào %s!</p>
                <p>Mã đơn: %s</p>
                <p>Trạng thái: %s</p>
                <p><a href="%s">Xem chi tiết đơn hàng</a></p>
              </body>
            </html>
            """.formatted(
            escapeHtml(data.customerName()),
            escapeHtml(data.orderCode()),
            escapeHtml(data.status()),
            escapeHtmlAttribute(data.orderUrl())
    );

    return new RenderedMail(plainText, htmlText);
}
~~~

Trong ví dụ, **escapeHtml** và **escapeHtmlAttribute** là các hàm minh họa cần được triển khai bằng thư viện phù hợp hoặc thay bằng template engine có escaping theo ngữ cảnh. Không dùng cùng một hàm escape cho mọi vị trí nếu ngữ cảnh HTML khác nhau. URL cũng phải được kiểm tra scheme/domain trước khi đưa vào href.

Sau khi render:

~~~java
RenderedMail rendered = renderer.render(data);
helper.setText(rendered.plainText(), rendered.htmlText());
~~~

Tách render khỏi gửi giúp dễ kiểm tra từng phiên bản và bảo đảm chúng cùng xuất phát từ một snapshot dữ liệu.

## 19. Kiểm tra tính tương đương của hai bản

Không có một phép so sánh chuỗi đơn giản nào chứng minh plain text và HTML tương đương về ý nghĩa. Tuy vậy, ứng dụng có thể kiểm tra những dữ liệu bắt buộc từ model xuất hiện trong cả hai phiên bản.

Ví dụ các trường bắt buộc:

| Dữ liệu | Plain text | HTML |
|---|---|---|
| Mã đơn hàng | Có | Có |
| Trạng thái | Có | Có |
| Ngày giao | Có | Có |
| URL hành động | URL đầy đủ | href đúng URL |
| Thông tin hỗ trợ | Có nếu cần | Có nếu cần |

### Ví dụ cách kiểm tra ở tầng renderer

~~~java
RenderedMail rendered = renderer.render(data);

if (!rendered.plainText().contains(data.orderCode())) {
    throw new IllegalStateException("Plain text thiếu mã đơn hàng");
}

if (!rendered.htmlText().contains(escapeHtml(data.orderCode()))) {
    throw new IllegalStateException("HTML thiếu mã đơn hàng");
}
~~~

Đây là ví dụ kiểm tra đơn giản. Với HTML có template, dữ liệu có thể được escape hoặc đặt trong thuộc tính nên cần kiểm tra theo DOM hoặc kiểm tra template/rendered output phù hợp. Không dùng một phép contains đơn giản làm bằng chứng toàn diện cho an toàn hay tính đúng đắn.

Ngoài ra, cần kiểm tra URL trong bản text và href của HTML cùng trỏ tới một đích nghiệp vụ. Nếu link có token, không đưa token thật vào log kiểm thử hoặc báo cáo.

## 20. Kiểm tra MIME structure sau khi tạo message

Trong quá trình phát triển, có thể tạo MimeMessage mà chưa gửi SMTP, sau đó đọc Content-Type hoặc các body part để xác nhận có alternative. Ví dụ với Jakarta Mail:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        true,
        StandardCharsets.UTF_8.name()
);
helper.setText(plainText, htmlText);

message.saveChanges();
String contentType = message.getContentType();
~~~

Khi cần kiểm tra sâu, đọc **Multipart** và duyệt từng BodyPart để xác nhận:

- Có một phần **text/plain**.
- Có một phần **text/html**.
- Phần plain text được đặt trước phần HTML trong alternative.
- Charset phù hợp.
- Nếu có attachment, part đó được đặt ở cấu trúc mixed phù hợp.
- Nếu có ảnh inline, Content-ID khớp tham chiếu cid.

Không nên chỉ kiểm tra chuỗi Content-Type của root rồi kết luận toàn bộ cây MIME đúng; với message lồng nhau, cần duyệt các part.

### Dùng SMTP test server

Unit test có thể kiểm tra renderer và MIME message mà không gửi thư thật. Integration test có thể dùng SMTP server thử nghiệm hoặc sandbox để quan sát raw message. Tránh gửi nội dung thử tới khách hàng production.

## 21. Hành vi của email client khi nhận multipart/alternative

Email client thường chọn một phần phù hợp với chế độ đọc và khả năng hỗ trợ. Một số người dùng có thể chọn hiển thị plain text, trong khi phần lớn client hiện đại có thể hiển thị HTML.

Các tình huống:

- Client hiển thị HTML: người nhận thấy bố cục, link, bảng và kiểu chữ.
- Client hoặc cấu hình ưu tiên text: người nhận đọc phần text/plain.
- HTML bị lọc một phần: nội dung text hoặc phần HTML còn lại vẫn cần đủ ý nghĩa.
- Hình ảnh bị chặn: nội dung text và alt text giúp người đọc hiểu thông điệp.
- Gateway lưu trữ hoặc phân tích: có thể trích xuất phần text đơn giản.

**multipart/alternative không yêu cầu client phải hiển thị cả hai phiên bản cùng lúc.** Nó cho phép chọn một biểu diễn. Nếu muốn người dùng nhìn thấy cả bản text và HTML trong cùng phần hiển thị, đó là một thiết kế nội dung khác và không phải mục đích chuẩn của alternative.

## 22. Những lỗi thường gặp khi tạo multipart/alternative

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Chỉ thấy HTML, không có plain text | Dùng **setText(html, true)** | Dùng **setText(plainText, htmlText)** |
| Plain text hiện nguyên thẻ HTML | Gán chuỗi HTML vào setText(text) | Tạo nội dung text riêng, không dùng HTML làm plain text |
| Hai bản có thông tin khác nhau | Render từ nguồn dữ liệu hoặc truy vấn khác nhau | Tạo một snapshot/model dùng chung |
| Link chỉ có trong HTML | Plain text không có URL đầy đủ | Đưa URL vào bản text |
| Tiếng Việt bị lỗi ký tự | Charset không được thiết lập nhất quán | Dùng UTF-8 trong MimeMessageHelper |
| Attachment thay thế body | Đặt attachment trong alternative | Dùng multipart/mixed bao ngoài alternative |
| Ảnh CID không hiện | Thiếu related part hoặc Content-ID sai | Kiểm tra multipart/related và addInline |
| Body part bị ghi đè | Gọi nhiều setter setText không đúng mục đích | Chọn một overload và thiết lập một lần |
| Email quá lớn | Nhúng quá nhiều ảnh hoặc attachment | Tối ưu ảnh, dùng link tải an toàn khi phù hợp |
| HTML khó đọc trên mobile | Bố cục cố định, font nhỏ, nhiều cột | Thiết kế một cột, CSS inline và test client |
| SMTP gửi lỗi | Host, credential, TLS hoặc recipient sai | Điều tra MailException và phản hồi SMTP |
| send() thành công nhưng email không vào Inbox | SMTP acceptance không đồng nghĩa delivery cuối | Xem bounce, logs và event của provider |

## 23. Các vấn đề bảo mật khi có hai phiên bản nội dung

Việc có plain text và HTML làm tăng khả năng tiếp cận, nhưng cũng tạo thêm nơi dữ liệu nhạy cảm có thể xuất hiện. Cần kiểm soát:

- **Cùng người nhận, cùng quyền:** hai bản phải chứa dữ liệu mà recipient được phép xem.
- **URL và token:** kiểm tra domain, scheme, quyền, thời hạn; không log token.
- **HTML escaping:** tránh chèn nội dung người dùng không tin cậy trực tiếp vào markup.
- **Header:** không để subject, From, Reply-To hoặc recipient lấy từ input không được xác thực.
- **Ảnh và attachment:** không nhúng dữ liệu riêng của người khác hoặc tài nguyên không được phép.
- **Log và lưu trữ:** raw MIME có thể chứa toàn bộ cả hai phiên bản, link và attachment.
- **Nội dung giống nhau:** tránh để HTML hiển thị thêm dữ liệu nhạy cảm mà plain text không có hoặc ngược lại.

### Không biến URL thành hành động tự động

Email scanner có thể tự mở URL để kiểm tra an toàn. Với thao tác nhạy cảm như thay đổi mật khẩu, xóa tài khoản hoặc xác nhận giao dịch, không nên hoàn tất hành động chỉ vì một request GET được thực hiện. Hãy dùng trang đích có bước xác nhận hoặc xác thực phù hợp.

## 24. Hiệu năng và dung lượng

Hai phần text/plain và text/html làm message lớn hơn so với chỉ có một phần, nhưng với email giao dịch thông thường, phần tăng này thường nhỏ hơn nhiều so với ảnh và attachment.

Những yếu tố làm email phình to:

- HTML chứa nhiều markup hoặc CSS inline lặp lại.
- Hình ảnh inline mã hóa base64.
- Nhiều attachment.
- Các URL tracking dài.
- Nội dung template lặp lại quá nhiều.

Nên giữ HTML gọn, dùng CSS cần thiết và không nhúng ảnh lớn nếu không có lý do. Nếu một biểu đồ có kích thước lớn, có thể cung cấp link tới dashboard được bảo vệ thay vì gửi toàn bộ dữ liệu hình ảnh.

### Đừng hy sinh plain text để giảm vài byte

Plain text thường nhỏ và có ích khi HTML không được hiển thị. Bỏ phần text chỉ để giảm dung lượng rất nhỏ có thể làm email kém sử dụng ở nhiều môi trường. Nếu message lớn, hãy xem xét ảnh/attachment trước và áp dụng giới hạn kích thước hợp lý.

## 25. Tách biệt lỗi chuẩn bị nội dung và lỗi gửi SMTP

Khi sử dụng **JavaMailSender.send(message)**, lỗi có thể xuất hiện ở những tầng khác nhau:

| Tầng | Ví dụ lỗi | Cách điều tra |
|---|---|---|
| Render text | Dữ liệu thiếu, template lỗi | Kiểm tra model và renderer |
| Render HTML | Template lỗi, escape sai | Kiểm tra HTML output và template engine |
| Tạo MIME | MessagingException, charset hoặc part không hợp lệ | Kiểm tra MimeMessageHelper và body parts |
| SMTP authentication | Sai username/password hoặc quyền | Kiểm tra credentials và provider |
| SMTP transport | Timeout, TLS, relay từ chối | Kiểm tra host, port, mạng và SMTP response |
| Chuyển phát sau SMTP | Bounce, spam, quarantine | Xem log/event của provider và hệ thống nhận |

Spring Mail có thể ném các exception thuộc họ **MailException**, ví dụ **MailAuthenticationException**, **MailSendException** hoặc **MailPreparationException**. Khi dựng MimeMessage, Jakarta Mail cũng có thể phát sinh **MessagingException**.

Không nên retry một lỗi render HTML hoặc lỗi charset như thể đó là lỗi mạng. Ngược lại, sửa template không giải quyết được credential SMTP sai.

Nếu timeout xảy ra sau khi dữ liệu đã được gửi tới SMTP server nhưng trước khi client nhận phản hồi, kết quả có thể chưa rõ. Retry ngay có nguy cơ tạo email trùng. Hệ thống quan trọng nên ghi notification ID, attempt ID và đối soát với provider khi có thể.

## 26. Gửi đồng bộ hay qua queue?

Lời gọi:

~~~java
mailSender.send(message);
~~~

thông thường thực hiện gửi đồng bộ trên thread gọi. **multipart/alternative không tự tạo background job, queue hoặc retry**.

Nếu email là kết quả của giao dịch nghiệp vụ và cần độ tin cậy cao, có thể lưu ý định gửi trong outbox rồi để worker tạo nội dung:

~~~text
Business transaction
        |
        v
Ghi dữ liệu + notification outbox
        |
      COMMIT
        |
        v
Background worker
        |
        v
Tạo snapshot dữ liệu email
        |
        +--> Render plain text
        |
        +--> Render HTML
        |
        v
MimeMessageHelper.setText(plain, html)
        |
        v
JavaMailSender.send()
        |
        v
Ghi nhận attempt và kết quả
~~~

Worker cần render hai phiên bản từ cùng snapshot dữ liệu để tránh mâu thuẫn. Outbox giúp lưu ý định gửi nhất quán với transaction database, nhưng không tự bảo đảm exactly-once delivery; cần quản lý retry và trạng thái chưa rõ.

## 27. Bảng kiểm khi thiết kế hai phiên bản

| Hạng mục | Câu hỏi |
|---|---|
| Ý nghĩa | Plain text và HTML có cùng nội dung nghiệp vụ không? |
| Thứ tự | text/plain có đứng trước text/html trong alternative không? |
| URL | Link trong hai bản có cùng đích đến không? |
| Dữ liệu | Cả hai có được render từ cùng snapshot không? |
| Charset | Nội dung tiếng Việt có dùng UTF-8 phù hợp không? |
| HTML | Markup có được escape đúng ngữ cảnh không? |
| Khả năng truy cập | Nội dung có đọc được khi ảnh hoặc CSS bị chặn không? |
| Attachment | Có dùng mixed cho file đính kèm thay vì alternative không? |
| Inline resource | Có dùng related và Content-ID khi HTML cần ảnh CID không? |
| Kiểm thử | Đã xem raw MIME và mở thư trên client mục tiêu chưa? |
| Vận hành | Đã phân biệt lỗi render, lỗi gửi và bounce sau SMTP chưa? |

Đây là các điểm thiết kế để hướng dẫn triển khai; không phải một cơ chế QA tự động của Spring Mail.

## 28. Ghi nhớ

**multipart/alternative** là cấu trúc MIME dùng để cung cấp nhiều biểu diễn thay thế của cùng nội dung email. Với Spring Framework Mail, ứng dụng thường tạo MimeMessage và dùng **MimeMessageHelper.setText(plainText, htmlText)** để cung cấp phần **text/plain** và **text/html**. Plain text nên được đặt trước, HTML sau; email client chọn biểu diễn phù hợp.

Hai phiên bản cần nhất quán về thông tin và hành động, được render từ cùng một mô hình dữ liệu. Plain text phải có nội dung và URL thật, còn HTML có thể bổ sung tiêu đề, bảng, nút CTA và hình ảnh. Dùng **multipart/mixed** cho attachment và **multipart/related** cho tài nguyên inline; không nhầm các quan hệ MIME này với alternative.

Khi triển khai, đặt charset phù hợp như UTF-8, escape dữ liệu HTML đúng ngữ cảnh, kiểm tra URL và MIME structure, rồi thử nghiệm trên email client mục tiêu. **Thiết kế multipart/alternative tốt giúp email giữ được ý nghĩa và khả năng sử dụng dù người nhận xem ở dạng văn bản hay HTML.**
