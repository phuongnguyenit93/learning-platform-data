# Nội dung thay thế phải diễn đạt cùng thông tin

Một email HTML có thể trình bày đẹp với màu sắc, bảng, nút bấm và logo. Tuy nhiên, không phải mọi ứng dụng đọc thư đều hiển thị HTML theo cùng cách; người nhận có thể dùng chế độ chỉ văn bản, thiết bị hoặc phần mềm hạn chế HTML, hoặc chính sách của mail client có thể chọn một định dạng khác. Vì vậy, email giao dịch thường cung cấp **hai cách biểu diễn cùng một nội dung**: `text/plain` và `text/html`.

Trong Spring Framework Mail, `MimeMessageHelper.setText(plainText, htmlText)` hỗ trợ tạo hai phần nội dung thay thế trong một message dạng multipart. Điều quan trọng của thiết kế này là **bản plain text và bản HTML phải truyền tải cùng thông tin nghiệp vụ**. Hai bản không cần có bố cục hay câu chữ giống hệt nhau, nhưng không được để một bản thiếu mã đơn, số tiền, thời hạn, bước tiếp theo hoặc liên kết hành động có trong bản còn lại.

Ví dụ, bản HTML có nút “Xem hóa đơn” trỏ tới một URL thì bản plain text cũng phải cung cấp URL hoặc cách tương đương để người nhận mở hóa đơn. Nếu trạng thái thanh toán, ngày đến hạn hoặc số tiền chỉ xuất hiện trong HTML, người đọc bản plain text sẽ nhận được một thông báo không đầy đủ.

Bài này giải thích ý nghĩa của `multipart/alternative`, cách thiết kế hai bản từ cùng một nguồn dữ liệu, cách gửi bằng `MimeMessageHelper` và `JavaMailSender`, những nội dung thường bị bỏ sót khi chuyển từ HTML sang plain text, cùng phương pháp kiểm thử tính tương đương thông tin.

## 1. Vì sao email cần cả plain text và HTML?

Email có thể được hiển thị trong nhiều môi trường:

- Ứng dụng đọc thư hỗ trợ HTML đầy đủ.
- Ứng dụng hoặc thiết bị chỉ hiển thị văn bản.
- Mail client tắt hoặc hạn chế hình ảnh, CSS và nội dung HTML.
- Hệ thống lưu trữ, chuyển tiếp hoặc phân tích email cần đọc phần text.
- Người dùng chủ động chọn chế độ hiển thị đơn giản.

Nếu chỉ gửi HTML, những môi trường không xử lý HTML phù hợp có thể không trình bày được nội dung như dự kiến. Nếu chỉ gửi plain text, ứng dụng không tận dụng được bố cục và hình thức trình bày phong phú.

Một email multipart/alternative cho phép message chứa hai representation:

~~~text
Email message
└── multipart/alternative
    ├── text/plain
    └── text/html
~~~

Hai phần này là **các lựa chọn thay thế cho cùng một nội dung logic**. Trình đọc thư chọn representation phù hợp với khả năng hoặc tùy chọn của nó. Theo quy ước MIME, phần có mức độ thể hiện phong phú hơn thường được đặt sau phần đơn giản hơn; với ví dụ này là plain text trước, HTML sau.

### Không phải hai email riêng biệt

Khi gọi:

~~~java
helper.setText(plainText, htmlText);
~~~

ứng dụng không gửi hai message tới người nhận. Nó tạo **một message** có hai phần body thay thế. Subject, From, To, Cc, Bcc và các header message vẫn là thông tin chung của message đó.

Điều này khác với việc gọi `mailSender.send(...)` hai lần, mỗi lần một message:

| Cách gửi | Kết quả |
| --- | --- |
| Một message có `multipart/alternative` | Một email với hai representation của cùng nội dung |
| Một message chỉ có `text/plain` | Một email chỉ có nội dung văn bản |
| Một message chỉ có `text/html` | Một email chỉ có nội dung HTML |
| Hai lần gửi, mỗi lần một message | Hai email độc lập, có thể bị nhận thành hai thư |

## 2. “Cùng thông tin” có nghĩa là gì?

Tương đương thông tin không yêu cầu hai bản có cùng số dòng, cùng từ ngữ hoặc cùng bố cục. Nó yêu cầu **mọi dữ kiện và hành động quan trọng mà người nhận cần đều có trong cả hai bản**.

Giả sử email xác nhận đơn hàng có các thông tin:

- Người nhận: Nguyễn An.
- Mã đơn hàng: `ORD-2048`.
- Trạng thái: Đã xác nhận.
- Tổng tiền: `1.250.000 ₫`.
- Thời gian giao dự kiến: ngày 18/11/2026.
- Hành động: xem chi tiết đơn hàng qua một liên kết.
- Kênh hỗ trợ khi có vấn đề.

Bản HTML có thể hiển thị chúng trong bảng và nút bấm. Bản plain text có thể trình bày thành các dòng:

~~~text
Xin chào Nguyễn An,

Đơn hàng ORD-2048 đã được xác nhận.

Trạng thái: Đã xác nhận
Tổng tiền: 1.250.000 ₫
Giao dự kiến: 18/11/2026

Xem chi tiết đơn hàng:
https://app.example.org/orders/ORD-2048

Nếu cần hỗ trợ, hãy trả lời email này hoặc liên hệ support@example.org.
~~~

Bản HTML có thể có cách trình bày khác:

~~~html
<h2>Đơn hàng đã được xác nhận</h2>
<p>Xin chào Nguyễn An,</p>
<table>
  <tr><th>Mã đơn</th><td>ORD-2048</td></tr>
  <tr><th>Trạng thái</th><td>Đã xác nhận</td></tr>
  <tr><th>Tổng tiền</th><td>1.250.000 ₫</td></tr>
  <tr><th>Giao dự kiến</th><td>18/11/2026</td></tr>
</table>
<a href="https://app.example.org/orders/ORD-2048">
  Xem chi tiết đơn hàng
</a>
<p>Hỗ trợ: support@example.org</p>
~~~

Bố cục khác nhau, nhưng các dữ kiện chính và hành động tương ứng đều có mặt.

### Tương đương không có nghĩa là HTML phải bị chuyển thành văn bản y hệt

Không nên tạo bản plain bằng cách xóa tất cả thẻ HTML khỏi chuỗi HTML. Cách đó có thể làm mất:

- Địa chỉ đích thực của một liên kết.
- Quan hệ giữa tiêu đề và nội dung.
- Tên cột trong bảng.
- Thông tin được thể hiện qua ảnh hoặc biểu tượng.
- Các đoạn hướng dẫn được nhóm theo thứ tự.

Thay vào đó, hãy xây cả hai bản từ **cùng một tập dữ liệu và cùng quy tắc nghiệp vụ**.

## 3. Xác định thông tin bắt buộc trước khi dựng hai bản

Trước khi viết HTML hoặc plain text, hãy xác định người nhận cần biết gì và phải làm gì sau khi đọc email.

Một bảng nội dung có thể giúp làm rõ yêu cầu:

| Nhóm thông tin | Ví dụ | Có cần trong cả hai bản? |
| --- | --- | --- |
| Danh tính thông báo | Xác nhận đơn hàng | Có |
| Định danh giao dịch | Mã đơn hàng | Có |
| Trạng thái | Đã xác nhận / đang chờ / thất bại | Có |
| Số liệu quan trọng | Tổng tiền, số lượng, ngày đến hạn | Có |
| Thời gian | Ngày giao, thời hạn xác nhận | Có |
| Hành động tiếp theo | Xem đơn, thanh toán, xác nhận | Có |
| Đích hành động | URL hoặc hướng dẫn truy cập | Có |
| Hỗ trợ | Email hoặc kênh liên hệ | Có nếu người nhận cần |
| Trang trí | Màu nền, đường viền, icon | Không nhất thiết |
| Hiệu ứng trình bày | Nút bo tròn, khoảng cách, banner | Không |

Thông tin trang trí có thể chỉ tồn tại trong HTML. Nhưng nếu một hình ảnh chứa mã xác nhận, số tiền hoặc hướng dẫn duy nhất, dữ liệu đó cần được diễn đạt lại bằng text trong cả hai representation.

### Dùng yêu cầu nghiệp vụ làm nguồn chuẩn

Một lỗi dễ gặp là nhóm phát triển viết HTML trước, rồi tạo plain text bằng cách rút gọn theo cảm tính. Sau vài lần chỉnh sửa, hai bản có thể lệch nhau: HTML đã cập nhật thời hạn mới nhưng plain text vẫn giữ thời hạn cũ.

Nên xác định **một danh sách dữ kiện chuẩn** và dựng cả hai bản từ danh sách đó. Khi nghiệp vụ thay đổi, dữ liệu nguồn và quy tắc render được cập nhật một lần; hai representation tiếp tục sử dụng cùng giá trị.

## 4. Dùng cùng một view model để tạo plain text và HTML

Trong ứng dụng Spring, có thể định nghĩa một đối tượng chỉ chứa thông tin email cần trình bày:

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;

public record OrderMailView(
        String customerName,
        String orderCode,
        String statusLabel,
        BigDecimal totalAmount,
        String formattedTotal,
        LocalDate expectedDeliveryDate,
        String formattedDeliveryDate,
        String detailsUrl,
        String supportEmail) {
}
~~~

View model được tạo từ dữ liệu nghiệp vụ đã xác thực:

~~~java
OrderMailView view = new OrderMailView(
        customer.getDisplayName(),
        order.getCode(),
        "Đã xác nhận",
        order.getTotalAmount(),
        moneyFormatter.format(order.getTotalAmount()),
        order.getExpectedDeliveryDate(),
        dateFormatter.format(order.getExpectedDeliveryDate()),
        orderDetailsUrl,
        "support@example.org"
);
~~~

Đây là ví dụ cấu trúc; `moneyFormatter` và `dateFormatter` là các formatter do ứng dụng cấu hình theo locale và quy tắc nghiệp vụ.

**Không nên truy vấn hoặc tính lại dữ liệu độc lập cho từng bản.** Nếu plain text và HTML gọi hai nguồn dữ liệu khác nhau, trạng thái hoặc số tiền có thể thay đổi giữa hai lần render. Hãy tạo view model một lần, sau đó truyền cùng object cho hai renderer.

### Vì sao nên định dạng dữ liệu trước?

Các giá trị như tiền tệ, ngày tháng và múi giờ cần được diễn đạt nhất quán:

- Không để HTML ghi `1.250.000 ₫` còn plain text ghi `1,250,000 VND` nếu hai định dạng có thể gây hiểu nhầm cho cùng người nhận.
- Không để ngày trong HTML theo giờ địa phương nhưng plain text theo UTC mà không ghi rõ múi giờ.
- Không tính thời gian còn lại riêng ở từng renderer, vì hai lần tính có thể lệch vài giây hoặc qua ranh giới ngày.

Có thể định dạng các giá trị một lần trong view model hoặc một lớp presentation dùng chung. Hai renderer chỉ chịu trách nhiệm sắp xếp cách trình bày.

## 5. Ví dụ plain text và HTML cùng thông tin

Giả sử dữ liệu:

~~~java
OrderMailView view = new OrderMailView(
        "Nguyễn An",
        "ORD-2048",
        "Đã xác nhận",
        new BigDecimal("1250000"),
        "1.250.000 ₫",
        LocalDate.of(2026, 11, 18),
        "18/11/2026",
        "https://app.example.org/orders/ORD-2048",
        "support@example.org"
);
~~~

### 5.1. Bản plain text

~~~java
private String renderPlainText(OrderMailView view) {
    return """
            Xin chào %s,

            Đơn hàng %s đã được xác nhận.

            Trạng thái: %s
            Tổng tiền: %s
            Giao dự kiến: %s

            Xem chi tiết đơn hàng:
            %s

            Nếu cần hỗ trợ, hãy liên hệ %s.
            """.formatted(
            view.customerName(),
            view.orderCode(),
            view.statusLabel(),
            view.formattedTotal(),
            view.formattedDeliveryDate(),
            view.detailsUrl(),
            view.supportEmail()
    );
}
~~~

Bản plain text không cần thẻ HTML. URL được ghi thành một dòng có thể sao chép hoặc mở từ mail client. Các dữ kiện chính vẫn đầy đủ.

### 5.2. Bản HTML

~~~java
private String renderHtml(OrderMailView view) {
    String customerName = escapeHtml(view.customerName());
    String orderCode = escapeHtml(view.orderCode());
    String status = escapeHtml(view.statusLabel());
    String total = escapeHtml(view.formattedTotal());
    String deliveryDate = escapeHtml(view.formattedDeliveryDate());
    String detailsUrl = escapeHtml(view.detailsUrl());
    String supportEmail = escapeHtml(view.supportEmail());

    return """
            <!doctype html>
            <html lang="vi">
              <body>
                <h2>Đơn hàng đã được xác nhận</h2>
                <p>Xin chào %s,</p>

                <table>
                  <tr>
                    <th>Mã đơn hàng</th>
                    <td>%s</td>
                  </tr>
                  <tr>
                    <th>Trạng thái</th>
                    <td>%s</td>
                  </tr>
                  <tr>
                    <th>Tổng tiền</th>
                    <td>%s</td>
                  </tr>
                  <tr>
                    <th>Giao dự kiến</th>
                    <td>%s</td>
                  </tr>
                </table>

                <p>
                  <a href="%s">Xem chi tiết đơn hàng</a>
                </p>

                <p>Hỗ trợ: %s</p>
              </body>
            </html>
            """.formatted(
            customerName,
            orderCode,
            status,
            total,
            deliveryDate,
            detailsUrl,
            supportEmail
    );
}
~~~

Hàm `escapeHtml` ở đây là tiện ích escape HTML text/attribute do ứng dụng cung cấp hoặc thư viện phù hợp. Trong code production, cần kiểm tra URL về scheme/host trước khi chèn vào `href`; HTML escaping không tự xác minh đích liên kết. Với template engine như Thymeleaf, có thể dùng escaped output cho các giá trị text thay vì tự nối chuỗi.

### 5.3. So sánh hai bản

| Thông tin | Plain text | HTML |
| --- | --- | --- |
| Khách hàng | `Nguyễn An` | `Nguyễn An` |
| Mã đơn | `ORD-2048` | `ORD-2048` |
| Trạng thái | `Đã xác nhận` | `Đã xác nhận` |
| Tổng tiền | `1.250.000 ₫` | `1.250.000 ₫` |
| Ngày giao | `18/11/2026` | `18/11/2026` |
| Hành động | URL được hiển thị trực tiếp | Link có nhãn “Xem chi tiết đơn hàng” |
| Hỗ trợ | Email hỗ trợ | Email hỗ trợ |

Hai bản không giống hình thức nhưng **không thiếu dữ kiện quan trọng ở một bên**.

## 6. Gửi cả hai representation bằng MimeMessageHelper

Sau khi chuẩn bị hai chuỗi, dùng overload hai tham số của `setText`:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {

    private final JavaMailSender mailSender;

    public OrderMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderConfirmation(
            String recipient,
            OrderMailView view) throws MessagingException {

        String plainText = renderPlainText(view);
        String htmlText = renderHtml(view);

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("orders@example.org");
        helper.setTo(recipient);
        helper.setSubject(
                "Đơn hàng " + view.orderCode()
                        + " đã được xác nhận"
        );

        // Cùng một message có cả text/plain và text/html.
        helper.setText(plainText, htmlText);

        mailSender.send(message);
    }

    // renderPlainText, renderHtml và escapeHtml được định nghĩa
    // trong service hoặc các component trình bày riêng.
}
~~~

Điểm quan trọng:

1. `renderPlainText(view)` và `renderHtml(view)` nhận **cùng một view model**.
2. `new MimeMessageHelper(message, true, "UTF-8")` bật multipart để hỗ trợ nhiều dạng nội dung.
3. `setText(plainText, htmlText)` đặt hai representation thay thế.
4. `JavaMailSender.send(message)` gửi một message qua SMTP.

Nếu chỉ gửi một body plain text, có thể dùng `setText(plainText)`. Nếu chỉ gửi HTML, dùng `setText(htmlText, true)`. Khi muốn có hai representation, cần dùng overload hai chuỗi và helper ở chế độ multipart phù hợp.

### Không gọi send hai lần để gửi hai định dạng

Không làm:

~~~java
helper.setText(plainText, false);
mailSender.send(message);

MimeMessage anotherMessage = mailSender.createMimeMessage();
// Dựng HTML rồi gửi lần thứ hai...
~~~

Cách này tạo hai email riêng. Người nhận có thể thấy cả hai thư, hệ thống gửi có thể tính quota hai lần và trạng thái gửi trở nên phức tạp. `multipart/alternative` được thiết kế để chứa hai dạng nội dung trong **một message**.

## 7. Những thông tin thường bị mất khi tạo bản plain text

Khi chuyển email từ HTML sang plain text, các yếu tố trình bày cần được diễn đạt lại. Đây là nơi dễ phát sinh sai lệch.

### 7.1. Nút bấm phải có URL tương ứng

HTML:

~~~html
<a href="https://app.example.org/orders/ORD-2048">
  Xem đơn hàng
</a>
~~~

Plain text không nên chỉ ghi:

~~~text
Xem đơn hàng
~~~

Vì người đọc không có nút hoặc hyperlink để bấm. Hãy ghi:

~~~text
Xem đơn hàng:
https://app.example.org/orders/ORD-2048
~~~

Nếu URL dài, có thể dùng một URL rút gọn do ứng dụng kiểm soát, nhưng đích hành động phải giống bản HTML.

### 7.2. Bảng phải giữ tên trường và giá trị

HTML có thể dùng bảng hai cột. Plain text nên diễn đạt rõ cặp nhãn/giá trị:

~~~text
Mã đơn hàng: ORD-2048
Trạng thái: Đã xác nhận
Tổng tiền: 1.250.000 ₫
Ngày giao dự kiến: 18/11/2026
~~~

Không chỉ nối các giá trị theo thứ tự mà bỏ tên trường. Khi không còn đường viền và cột, người đọc có thể không biết số nào là số tiền, số nào là mã đơn.

### 7.3. Hình ảnh mang thông tin cần có phần text tương ứng

Nếu HTML hiển thị banner:

~~~html
<img src="cid:payment-status" alt="Thanh toán thành công">
~~~

thì bản plain text nên có dòng:

~~~text
Trạng thái thanh toán: Thành công.
~~~

Không để trạng thái, mã xác nhận, ngày đến hạn hoặc hướng dẫn quan trọng chỉ nằm trong ảnh. `alt` hữu ích cho HTML nhưng không thay thế representation plain text riêng.

### 7.4. Danh sách phải giữ đủ mục

HTML:

~~~html
<ul>
  <li>Kiểm tra địa chỉ nhận hàng.</li>
  <li>Đảm bảo có người nhận.</li>
  <li>Chuẩn bị mã đơn khi liên hệ hỗ trợ.</li>
</ul>
~~~

Plain text:

~~~text
Các bước cần chuẩn bị:
- Kiểm tra địa chỉ nhận hàng.
- Đảm bảo có người nhận.
- Chuẩn bị mã đơn khi liên hệ hỗ trợ.
~~~

Không rút gọn plain text đến mức bỏ mất một bước quan trọng.

### 7.5. Nội dung được ẩn/hiện theo điều kiện phải nhất quán

Nếu HTML dùng điều kiện để hiển thị một cảnh báo, bản plain text cũng cần áp dụng cùng điều kiện và cùng dữ liệu. Ví dụ trạng thái thanh toán `PENDING` phải hiển thị thông tin chờ thanh toán ở cả hai bản; không để plain text luôn ghi “Đã thanh toán”.

**Đừng tự tính điều kiện riêng trong từng renderer.** Hãy quyết định trạng thái nghiệp vụ trước, đưa vào view model và để cả hai renderer trình bày giá trị đó.

## 8. Hành động và liên kết phải tương đương

Email thường yêu cầu người nhận thực hiện một bước:

- Xác nhận địa chỉ email.
- Thanh toán hóa đơn.
- Đặt lại mật khẩu.
- Xem trạng thái đơn hàng.
- Xác nhận lịch hẹn.
- Tải tài liệu.

Bản HTML có thể có nút lớn, nhưng bản plain text phải cung cấp **cùng đích đến và cùng ý nghĩa hành động**.

| HTML | Plain text tương ứng |
| --- | --- |
| Nút “Xác nhận email” | “Xác nhận email: URL” |
| Nút “Thanh toán ngay” | “Thanh toán tại: URL” |
| Link “Xem hóa đơn” | “Xem hóa đơn: URL” |
| Link “Đổi mật khẩu” | “Đổi mật khẩu: URL” |
| QR code mở trang xác nhận | URL hoặc hướng dẫn thay thế |

### Tránh để URL chỉ nằm trong href

Một lỗi phổ biến:

~~~html
<a href="https://app.example.org/pay/INV-12">Thanh toán ngay</a>
~~~

Plain text:

~~~text
Thanh toán ngay.
~~~

Người đọc plain text biết phải thanh toán nhưng không biết truy cập đâu. Cần cung cấp URL hoặc hướng dẫn rõ ràng.

### Token và đường dẫn nhạy cảm

Với liên kết đặt lại mật khẩu hoặc xác nhận tài khoản, URL có thể chứa token. Nếu cùng URL xuất hiện trong cả hai representation, người nhận vẫn có cùng khả năng thực hiện hành động, nhưng ứng dụng cần bảo vệ token theo chính sách: thời hạn, phạm vi sử dụng, một lần dùng, không ghi vào log và tránh gửi cho sai người nhận.

Tính tương đương nội dung **không có nghĩa** phải tiết lộ thêm dữ liệu nhạy cảm. Nếu URL không được phép hiển thị trong plain text theo yêu cầu bảo mật của sản phẩm, hãy cung cấp một hướng dẫn thay thế thực hiện cùng mục đích, ví dụ đăng nhập website chính thức rồi mở mục xác nhận.

## 9. Subject và header là thông tin chung, không phải hai body alternative

Trong một message multipart/alternative, Subject chỉ được đặt một lần:

~~~java
helper.setSubject("Hóa đơn INV-12 đã sẵn sàng");
helper.setText(plainText, htmlText);
~~~

Không có một Subject riêng cho `text/plain` và một Subject riêng cho `text/html`. Cả hai representation cùng thuộc một message và dùng chung header.

Nếu muốn nội dung tiêu đề xuất hiện trong body, chẳng hạn “Hóa đơn đã sẵn sàng”, hãy bảo đảm cả plain text và HTML có phần mở đầu phù hợp. Nhưng không nhất thiết phải lặp Subject nguyên văn nếu thông điệp đã rõ.

Tương tự, From, To, Cc, Bcc, Reply-To và các header khác không phải các alternative body. Chúng áp dụng ở cấp message.

## 10. Plain text cần dễ đọc, không chỉ đủ dữ liệu

Một bản plain text có đầy đủ thông tin nhưng trình bày thành một chuỗi dài vẫn gây khó đọc. Nên tổ chức nội dung bằng:

- Đoạn văn ngắn.
- Dòng trống giữa các nhóm.
- Nhãn rõ cho dữ liệu quan trọng.
- Danh sách có dấu đầu dòng.
- URL trên dòng riêng.
- Hướng dẫn theo thứ tự.
- Chữ ký hoặc thông tin hỗ trợ ở cuối.

Ví dụ khó đọc:

~~~text
Xin chào An đơn ORD-2048 đã xác nhận tổng tiền 1250000 giao 18/11 xem https://app.example.org/orders/ORD-2048 cần hỗ trợ support@example.org.
~~~

Ví dụ dễ đọc:

~~~text
Xin chào An,

Đơn hàng ORD-2048 đã được xác nhận.

Tổng tiền: 1.250.000 ₫
Giao dự kiến: 18/11/2026

Xem chi tiết:
https://app.example.org/orders/ORD-2048

Cần hỗ trợ? Liên hệ support@example.org.
~~~

Không nên cố tạo bảng ASCII quá phức tạp nếu nội dung có thể hiển thị trên màn hình hẹp. Định dạng plain text nên ưu tiên tính đọc được và khả năng sao chép.

## 11. HTML có thể phong phú hơn nhưng không được chứa dữ kiện độc quyền

HTML có thể thêm:

- Màu sắc để nhấn trạng thái.
- Logo và hình ảnh trang trí.
- Bảng để nhóm dữ liệu.
- Nút hành động có kiểu dáng.
- Khoảng cách và phân cấp tiêu đề.
- Biểu tượng hỗ trợ điều hướng.

Những thành phần này cải thiện cách trình bày. Tuy nhiên, HTML không nên là nơi duy nhất chứa thông tin cần thiết.

Ví dụ, nếu HTML dùng màu xanh để biểu thị “Đã thanh toán”, không chỉ dùng màu mà cần có chữ `Đã thanh toán`. Người đọc có thể không thấy màu do client bỏ CSS hoặc người dùng không phân biệt màu tốt.

Tương tự, nếu HTML có biểu tượng cảnh báo, hãy kèm nội dung “Cần thanh toán trước ngày...” để ý nghĩa không phụ thuộc vào hình ảnh.

### Accessibility hỗ trợ cả hai representation

Bản HTML nên dùng cấu trúc có ý nghĩa:

- Heading theo thứ tự.
- Text label rõ ràng.
- Bảng có tiêu đề trường phù hợp.
- Link có tên mô tả hành động.
- Ảnh có alt text phù hợp.
- Không chỉ truyền trạng thái qua màu sắc.

Bản plain text cũng nên giữ thứ tự đọc và nhãn dữ liệu. Cả hai cùng hướng tới một mục tiêu: người nhận hiểu thông báo và biết phải làm gì tiếp theo.

## 12. Nội dung đa ngôn ngữ cũng phải tương đương

Nếu email hỗ trợ tiếng Việt và tiếng Anh, cần đảm bảo **hai định dạng trong cùng một message dùng cùng locale**.

Ví dụ tiếng Việt:

~~~text
Đơn hàng ORD-2048 đã được xác nhận.
Tổng tiền: 1.250.000 ₫
Giao dự kiến: 18/11/2026
~~~

Bản HTML tiếng Việt cũng phải có các dữ kiện tương ứng. Không để plain text mặc định tiếng Anh trong khi HTML được render tiếng Việt chỉ vì hai renderer dùng hai nguồn message bundle khác nhau.

Nên chọn locale một lần, tạo view model theo locale đó và truyền cùng dữ liệu đã định dạng cho cả hai renderer.

### Ngày giờ và múi giờ

Nếu email nói lịch hẹn lúc 09:00 ngày 20/11 theo giờ Việt Nam, cả plain và HTML cần thể hiện cùng thời điểm và múi giờ. Tránh một bản dùng giờ địa phương, bản kia dùng UTC mà không ghi rõ.

Có thể lưu thời điểm chuẩn dưới dạng instant, rồi định dạng một lần theo timezone của người nhận:

~~~java
ZonedDateTime localTime =
        appointmentInstant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

String formattedTime =
        DateTimeFormatter.ofPattern(
                "HH:mm dd/MM/yyyy z",
                Locale.forLanguageTag("vi-VN")
        ).format(localTime);
~~~

Cả hai representation dùng `formattedTime`. Nếu sản phẩm hỗ trợ nhiều múi giờ, timezone phải được xác định theo chính sách người nhận và ghi rõ trong email.

### Tiền tệ và số thập phân

Dùng cùng một formatter để tránh HTML và plain text có dấu phân cách hoặc ký hiệu tiền khác nhau ngoài ý muốn. Nếu cần hiển thị quy đổi nhiều loại tiền, các giá trị và tỷ giá áp dụng phải đến từ cùng một snapshot nghiệp vụ.

## 13. Xử lý dữ liệu động: plain text và HTML có cách khác nhau

Dữ liệu động cần được đưa vào cả hai bản, nhưng cách encode phụ thuộc định dạng:

- **Plain text:** dùng giá trị văn bản đã kiểm tra nghiệp vụ; chuẩn hóa newline và ký tự điều khiển theo chính sách.
- **HTML:** escape dữ liệu ở đúng ngữ cảnh text node hoặc attribute; xác thực URL trước khi đưa vào href.
- **Subject:** đặt qua API header, không dùng HTML entity để xử lý Unicode.
- **URL:** xây từ nguồn tin cậy, encode thành phần path/query, rồi biểu diễn an toàn khi đặt vào HTML attribute.

Ví dụ tên người nhận là:

~~~text
An <Bảo> & Co.
~~~

Plain text:

~~~text
Xin chào An <Bảo> & Co.
~~~

HTML source:

~~~html
<p>Xin chào An &lt;Bảo&gt; &amp; Co.</p>
~~~

Người đọc HTML cũng nhìn thấy `An <Bảo> & Co.`. Không đưa chuỗi HTML-escaped vào bản plain text, vì người nhận có thể thấy `&lt;` và `&amp;`.

### Không escape cùng một chuỗi hai lần

Nếu backend escape tên thành `An &lt;Bảo&gt;` rồi template engine lại escape, người nhận có thể thấy entity literal. Chọn một nơi chịu trách nhiệm HTML escaping; bản plain text luôn dùng giá trị logic, không dùng chuỗi đã escape cho HTML.

### Không để dữ liệu người dùng trở thành markup

Nếu người dùng nhập `<strong>Ưu tiên</strong>` trong trường ghi chú, hãy xác định nghiệp vụ:

- Nếu ghi chú là văn bản, plain text giữ nguyên chuỗi và HTML escape để thẻ hiển thị như chữ.
- Nếu cho phép rich text, phải sanitize HTML theo allowlist trước khi đưa vào HTML body; bản plain text cần một representation có ý nghĩa tương đương, ví dụ “Ưu tiên”.

Không dùng `setText(html, true)` như một cơ chế sanitize. Helper chỉ đóng gói body MIME.

## 14. Kết hợp inline image và multipart/alternative

Một message có thể chứa plain text, HTML và ảnh inline được HTML tham chiếu bằng CID. Cấu trúc MIME thường có các lớp lồng nhau, ví dụ:

~~~text
multipart/related
├── multipart/alternative
│   ├── text/plain
│   └── text/html
│       └── <img src="cid:brand-logo">
└── image/png
    └── Content-ID: <brand-logo>
~~~

Plain text không cần chứa `cid:brand-logo` vì nó không hiển thị ảnh bằng HTML. Nhưng **nội dung mà ảnh mang ý nghĩa phải được diễn đạt bằng text**.

Ví dụ logo chỉ mang tính thương hiệu có thể không cần mô tả dài trong plain text. Nhưng nếu ảnh là mã QR để thanh toán, plain text cần có URL hoặc hướng dẫn thanh toán tương đương. Không để QR là con đường duy nhất thực hiện hành động.

Khi sử dụng `MimeMessageHelper`, hãy tạo helper ở chế độ multipart phù hợp, gọi `setText(plainText, htmlText)` trước, rồi thêm inline resource bằng `addInline(...)`. Tên CID trong HTML phải khớp Content-ID mà helper thêm vào message.

## 15. Attachment không phải một representation thay thế

Tệp đính kèm như PDF hóa đơn hoặc bảng tính không phải bản thứ ba của body thay thế. Nó là một MIME part riêng có thể nằm trong cấu trúc multipart/mixed bao ngoài phần body.

Ví dụ khái quát:

~~~text
multipart/mixed
├── multipart/alternative
│   ├── text/plain
│   └── text/html
└── application/pdf
    └── invoice.pdf
~~~

Nếu email nói “Hóa đơn được đính kèm”, cả plain và HTML đều nên nói điều đó. Nếu HTML có link tải hóa đơn trực tuyến còn plain text không có, người dùng plain text sẽ mất hành động đó; cần cung cấp URL hoặc hướng dẫn tương đương.

Việc có PDF không miễn trách nhiệm cung cấp các thông tin chính như mã hóa đơn, số tiền và ngày đến hạn trong body. Tệp đính kèm có thể không mở được hoặc bị hệ thống nhận chặn.

## 16. Các lỗi thiết kế thường gặp

### 16.1. Plain text chỉ là câu rút gọn, thiếu dữ kiện

HTML có mã đơn, tổng tiền, hạn thanh toán; plain text chỉ ghi “Bạn có đơn hàng mới”. Người đọc plain text không có đủ thông tin.

**Cách xử lý:** lập danh sách dữ kiện bắt buộc và dùng chung view model cho hai renderer.

### 16.2. HTML có nút nhưng plain text không có URL

Người đọc plain text biết phải bấm “Thanh toán” nhưng không có đích đến.

**Cách xử lý:** đưa URL hoặc hướng dẫn truy cập tương đương vào bản plain text.

### 16.3. Plain text được tạo bằng cách xóa tag HTML

Regex xóa tag có thể làm mất URL, nhãn, cấu trúc bảng và thông tin trong thuộc tính.

**Cách xử lý:** xây plain text riêng từ dữ liệu nghiệp vụ hoặc dùng một bộ chuyển đổi HTML-to-text được kiểm soát, sau đó vẫn kiểm tra nội dung.

### 16.4. Hai renderer truy vấn dữ liệu riêng

Trạng thái đơn hàng hoặc số tiền có thể thay đổi giữa hai lần đọc, khiến representation khác nhau.

**Cách xử lý:** tạo snapshot/view model một lần và truyền cho cả hai renderer.

### 16.5. Định dạng ngày giờ hoặc tiền tệ khác nhau

HTML và plain text có thể hiển thị các giá trị có vẻ khác nhau do locale hoặc timezone.

**Cách xử lý:** định dạng một lần từ cùng giá trị và timezone/locale.

### 16.6. HTML có thông tin chỉ nằm trong ảnh

Một banner ghi “Thanh toán trước ngày 20/11” nhưng plain text không có thời hạn.

**Cách xử lý:** đưa thông tin đó thành text trong cả hai bản; ảnh chỉ bổ sung trình bày.

### 16.7. HTML link và plain URL trỏ tới hai đích khác nhau

Một lỗi copy/paste có thể khiến nút HTML mở đơn hàng A nhưng URL plain text mở đơn hàng B.

**Cách xử lý:** tạo URL một lần trong view model và dùng cùng giá trị cho cả hai representation.

### 16.8. Subject khác body alternative

Subject là header chung, nhưng nội dung trong body có thể bỏ sót thông tin khiến người đọc hiểu sai. Đảm bảo Subject và hai body cùng phản ánh một sự kiện nghiệp vụ, không hiển thị trạng thái mâu thuẫn.

### 16.9. Dùng dữ liệu HTML-escaped trong plain text

Plain text xuất hiện `&lt;` hoặc `&amp;` vì ứng dụng tái sử dụng chuỗi đã escape cho HTML.

**Cách xử lý:** giữ dữ liệu logic gốc và encode riêng theo từng representation.

### 16.10. Dùng hai message thay cho multipart/alternative

Người nhận có thể nhận hai email giống nhau, gây nhầm lẫn và tăng lượng gửi.

**Cách xử lý:** dùng `setText(plainText, htmlText)` để tạo một message với hai body part thay thế.

### 16.11. Chỉ kiểm thử HTML

Template HTML có thể đúng nhưng plain text đã lỗi thời hoặc thiếu URL.

**Cách xử lý:** kiểm thử cả hai renderer và các dữ kiện chung.

### 16.12. Cho rằng HTML đẹp hơn đồng nghĩa đầy đủ hơn

Bố cục tốt không bù được dữ liệu thiếu. Representation nào cũng phải cho người nhận biết sự kiện gì xảy ra và cần làm gì tiếp theo.

## 17. Kiểm thử tính tương đương thông tin

Không cần kiểm tra hai chuỗi phải giống hệt nhau. Cần kiểm tra **các dữ kiện quan trọng xuất hiện ở cả hai bản**.

Giả sử view model có:

~~~java
OrderMailView view = ...;
String plain = renderPlainText(view);
String html = renderHtml(view);
~~~

Một số assertion đơn giản:

~~~java
assertTrue(plain.contains(view.orderCode()));
assertTrue(html.contains(view.orderCode()));

assertTrue(plain.contains(view.formattedTotal()));
assertTrue(html.contains(view.formattedTotal()));

assertTrue(plain.contains(view.formattedDeliveryDate()));
assertTrue(html.contains(view.formattedDeliveryDate()));

assertTrue(plain.contains(view.detailsUrl()));
assertTrue(html.contains(view.detailsUrl()));
~~~

Với HTML, URL có thể được escape trong thuộc tính, vì vậy kiểm thử nâng cao nên parse HTML hoặc kiểm tra giá trị thuộc tính sau khi giải mã theo quy tắc HTML, thay vì luôn so sánh chuỗi thô.

### 17.1. Kiểm tra semantic checklist

Một bảng dữ kiện giúp nhóm phát triển xác định yêu cầu:

| Assertion | Plain text | HTML |
| --- | --- | --- |
| Có mã đơn | Có | Có |
| Có trạng thái | Có | Có |
| Có tổng tiền và đơn vị tiền tệ | Có | Có |
| Có ngày đến hạn/giao hàng | Có | Có |
| Có hành động tiếp theo | Có | Có |
| Có đích liên kết tương ứng | URL/hướng dẫn | href |
| Có kênh hỗ trợ | Có | Có |
| Không lộ dữ liệu không được phép | Có | Có |

Các kiểm tra này nên được cập nhật khi nghiệp vụ thay đổi. Chúng xác nhận nội dung người nhận cần, không phải cách HTML được serialize thành byte.

### 17.2. Kiểm tra cấu trúc MIME

Có thể dùng SMTP test server hoặc đọc lại `MimeMessage` trong unit/integration test để xác nhận message có:

- Một phần `text/plain`.
- Một phần `text/html`.
- Cả hai nằm trong cấu trúc multipart/alternative phù hợp.
- Attachment hoặc inline resource nằm trong container phù hợp nếu có.

Không nên giả định HTML luôn ở chỉ số part cố định trong một multipart ngoài cùng, vì cấu trúc có thể lồng `multipart/related` hoặc `multipart/mixed`. Hãy duyệt cây MIME theo Content-Type.

### 17.3. Kiểm tra trải nghiệm trên mail client

Sau khi kiểm tra MIME, gửi tới môi trường test và mở trên những client mục tiêu. Xác nhận:

- HTML hiển thị đúng.
- Plain text có thể đọc độc lập.
- URL có thể mở và trỏ tới cùng đích.
- Ảnh không chứa dữ kiện duy nhất.
- Thông tin quan trọng không phụ thuộc vào màu sắc hoặc CSS.
- Không có dòng hoặc bảng bị mất khi hiển thị trên màn hình hẹp.

## 18. Ví dụ dùng template engine

Nếu ứng dụng sử dụng Thymeleaf, có thể giữ hai template riêng:

~~~text
templates/mail/order-confirmed.html
templates/mail/order-confirmed.txt
~~~

Template HTML có thể dùng markup:

~~~html
<h2>Đơn hàng đã được xác nhận</h2>
<p>Xin chào, <span th:text="¤{mail.customerName}">Khách hàng</span>.</p>
<p>Mã đơn: <span th:text="¤{mail.orderCode}">ORD-2048</span></p>
<p>Tổng tiền: <span th:text="¤{mail.formattedTotal}">1.250.000 ₫</span></p>
<a th:href="¤{mail.detailsUrl}">Xem chi tiết</a>
~~~

Template text có thể dùng cú pháp text mode hoặc một cơ chế template phù hợp với plain text:

~~~text
Xin chào, [customerName].

Đơn hàng [orderCode] đã được xác nhận.
Tổng tiền: [formattedTotal]

Xem chi tiết:
[detailsUrl]
~~~

Placeholder trong ví dụ plain chỉ minh họa; cú pháp cụ thể phụ thuộc cách ứng dụng cấu hình template engine cho text mode. Điều quan trọng là **cả hai template nhận cùng view model** và được render theo cùng locale.

Ví dụ Java:

~~~java
Context context = new Context(locale);
context.setVariable("mail", view);

String html = templateEngine.process(
        "mail/order-confirmed",
        context
);

String plain = plainTextRenderer.render(view, locale);

helper.setText(plain, html);
~~~

Không dùng một template HTML làm nguồn rồi xóa tag bằng regex để tạo text nếu nội dung có bảng, liên kết hoặc điều kiện phức tạp. Một renderer plain text rõ ràng thường dễ kiểm soát tính đầy đủ hơn.

## 19. Khi nào hai bản có thể khác nhau?

Hai representation có thể khác về **cách trình bày**, nhưng cần giữ nguyên ý nghĩa nghiệp vụ.

Những khác biệt chấp nhận được:

- HTML có nút bấm, plain text hiển thị URL.
- HTML có bảng, plain text có nhãn và dòng dữ liệu.
- HTML có logo trang trí, plain text không có logo.
- HTML dùng màu để nhấn mạnh, plain text dùng từ ngữ như “Cảnh báo”.
- HTML có khoảng cách và kiểu chữ, plain text dùng dòng trống và dấu đầu dòng.

Những khác biệt không nên có:

- HTML ghi đã thanh toán, plain text ghi đang chờ.
- HTML có thời hạn, plain text bỏ thời hạn.
- HTML có nút xác nhận, plain text không có URL/hướng dẫn thay thế.
- HTML hiển thị tổng tiền đã gồm thuế, plain text hiển thị tổng trước thuế mà không giải thích.
- HTML dùng ngày theo một timezone, plain text dùng ngày theo timezone khác.
- HTML hiển thị một mã giao dịch, plain text hiển thị mã khác.

### Có thể cung cấp chi tiết khác nhau không?

Nếu HTML có thêm nội dung trang trí hoặc hướng dẫn bổ sung không thiết yếu, bản plain text không nhất thiết phải tái tạo từng chi tiết. Nhưng nếu nội dung đó có thể ảnh hưởng đến quyết định, quyền lợi, nghĩa vụ hoặc hành động của người nhận, nó phải được diễn đạt trong bản plain text.

## 20. Câu hỏi thực hành

**Câu 1.** Vì sao nên gửi cả `text/plain` và `text/html` trong một email?

Để mail client có thể chọn representation phù hợp. Người nhận vẫn có nội dung đọc được khi HTML không được hỗ trợ hoặc bị hạn chế.

**Câu 2.** `setText(plainText, htmlText)` tạo hai email riêng biệt không?

Không. Nó tạo hai phần body thay thế trong cùng một MIME message multipart/alternative.

**Câu 3.** HTML có nút “Xem hóa đơn” nhưng plain text chỉ có chữ “Xem hóa đơn”. Đã tương đương chưa?

Chưa. Plain text cần URL hoặc hướng dẫn tương đương để người nhận thực hiện hành động.

**Câu 4.** Có nên tạo plain text bằng cách xóa tất cả thẻ HTML bằng regex?

Không nên dựa vào cách đó cho template phức tạp. Nó có thể làm mất URL, nhãn bảng, nội dung ảnh và cấu trúc. Hãy tạo plain text từ cùng dữ liệu nghiệp vụ.

**Câu 5.** Plain text và HTML có thể dùng hai lần truy vấn database riêng không?

Không nên. Hai lần truy vấn có thể trả về trạng thái hoặc giá trị khác nhau. Tạo view model/snapshot một lần rồi truyền cho cả hai renderer.

**Câu 6.** Dữ liệu tên người nhận có ký tự `<`. Plain text và HTML có cách biểu diễn giống nhau không?

Không nhất thiết. Plain text dùng chuỗi gốc; HTML source phải escape ký tự cho đúng ngữ cảnh. Khi hiển thị, cả hai vẫn truyền tải cùng tên.

**Câu 7.** Một QR code chứa URL thanh toán xuất hiện trong HTML. Plain text cần gì?

Cần URL hoặc hướng dẫn thanh toán tương đương. Không để QR code là cách duy nhất thực hiện hành động.

**Câu 8.** Có thể dùng Subject khác nhau cho hai alternative body không?

Không. Subject là header chung của message. Hai alternative chỉ là các representation của body.

**Câu 9.** HTML có logo CID, plain text không có ảnh. Có vi phạm tương đương không?

Không nhất thiết. Nếu logo chỉ mang tính thương hiệu, plain text không cần tái tạo ảnh. Nếu ảnh chứa thông tin nghiệp vụ hoặc hành động, nội dung đó phải có representation bằng text.

**Câu 10.** Kiểm thử hai body có cần yêu cầu chuỗi HTML và plain text giống nhau không?

Không. Cần kiểm tra các dữ kiện và hành động quan trọng có mặt, nhất quán ở cả hai bản; bố cục và cách trình bày được phép khác nhau.

## 21. Mô hình ghi nhớ

Một email nhiều định dạng nên được xây theo quy trình:

~~~mermaid
flowchart TD
    A["Dữ liệu nghiệp vụ đã xác thực"] --> B["View model dùng chung"]
    B --> C["Renderer text/plain"]
    B --> D["Renderer text/html"]
    C --> E["MimeMessageHelper.setText(plain, html)"]
    D --> E
    E --> F["Một MIME message multipart/alternative"]
    F --> G["JavaMailSender.send"]
    G --> H["Mail client chọn representation phù hợp"]
~~~

Hãy ghi nhớ:

1. **Plain text và HTML là hai cách biểu diễn thay thế của cùng một nội dung**, không phải hai email riêng.
2. **Mọi thông tin và hành động quan trọng phải có ở cả hai bản**: mã, trạng thái, tiền, thời gian, hướng dẫn, URL và kênh hỗ trợ.
3. **Dùng cùng view model hoặc snapshot dữ liệu** để tránh trạng thái, số tiền, ngày giờ và URL bị lệch.
4. **HTML được phép phong phú hơn về trình bày**, nhưng không được chứa dữ kiện độc quyền mà plain text không thể tiếp cận.
5. **Link HTML phải có URL/hướng dẫn tương ứng trong plain text**; bảng và hình ảnh mang thông tin cần được diễn đạt thành text.
6. **Encode theo từng định dạng**: plain text dùng văn bản logic, HTML escape theo ngữ cảnh, URL được kiểm soát riêng.
7. **Dùng `MimeMessageHelper.setText(plainText, htmlText)`** với helper multipart để tạo một message có hai representation.
8. **Kiểm thử semantic parity**, không yêu cầu hai chuỗi phải giống hệt; xác nhận dữ kiện và hành động quan trọng đều hiện diện và nhất quán.

Khi ứng dụng xây cả plain text và HTML từ cùng một nguồn dữ liệu, người nhận sẽ nhận được thông điệp đầy đủ dù mail client chọn cách hiển thị nào. `MimeMessageHelper` đóng gói hai representation vào MIME message, còn `JavaMailSender` gửi một message duy nhất qua SMTP đã cấu hình.
