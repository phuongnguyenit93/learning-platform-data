# Quy tắc header của nhà cung cấp và email gateway trong Spring Framework Mail

Một email có thể được tạo hợp lệ bằng `JavaMailSender` nhưng vẫn bị nhà cung cấp SMTP từ chối, bị email gateway thay đổi hoặc đến hộp thư với một số header khác với bản ứng dụng đã tạo. Nguyên nhân là **header email đi qua nhiều hệ thống, mỗi hệ thống có quyền áp dụng các quy tắc giao thức, bảo mật và chính sách riêng**.

Trong Spring Framework Mail, lập trình viên thường quan tâm `From`, `To`, `Cc`, `Bcc`, `Reply-To` và `Subject`. Tuy nhiên, khi triển khai email thật còn có các header về định danh, MIME, xác thực, danh sách hủy đăng ký, theo dõi và thông tin vận chuyển. Bài học này giải thích cách đọc các header đó, ranh giới giữa ứng dụng và nhà cung cấp, các thay đổi gateway thường thực hiện, và cách thiết kế mã Java để tránh lỗi tương thích.

## 1. Header email đi qua những lớp nào?

Xét hệ thống gửi email thông báo đơn hàng:

```text
Ứng dụng Spring
  |
  | JavaMailSender tạo MimeMessage
  | From, To, Subject, Reply-To, MIME, custom headers
  v
SMTP submission / Email Service Provider (ESP)
  |
  | Xác thực tài khoản, kiểm tra sender, rate limit,
  | chấp nhận/chặn một số header, có thể thêm hoặc sửa
  v
Outbound email gateway
  |
  | Chính sách DLP, antivirus, disclaimer, DKIM signing,
  | routing, logging, thêm Received hoặc các header nội bộ
  v
Internet SMTP / MX phía nhận
  |
  | SPF / DKIM / DMARC, chống spam/phishing, kiểm tra MIME,
  | thêm Received, Authentication-Results theo chính sách
  v
Inbound email gateway
  |
  | Cách ly, lọc tệp, sửa URL, kiểm tra nội dung
  v
Mailbox / Email client
  |
  | Hiển thị From, Subject, Reply-To và nội dung
  v
Người nhận
```

Không phải môi trường nào cũng có mọi gateway riêng biệt. Có hệ thống sử dụng ESP làm cả SMTP relay, bộ lọc và DKIM signer. Một số hệ thống khác đi qua relay nội bộ rồi đến ESP công cộng. **Danh sách header ở mỗi chặng có thể khác nhau**, và quy định về tên header, độ dài, giá trị, quyền sửa cũng phụ thuộc cấu hình nhà cung cấp.

Một quy trình thực tế cần tách ba loại thông tin:

1. **Message headers**: nằm trong nội dung thông điệp RFC 5322/MIME, ví dụ `From`, `Subject`, `Message-ID`.
2. **SMTP envelope**: thông tin trên phiên giao thức, ví dụ `MAIL FROM` và `RCPT TO`. Chúng không phải các header hiển thị cùng tên.
3. **Provider metadata / event**: ID request, tag, campaign, message ID và sự kiện accepted/delivered/bounced; có thể nằm trong API riêng thay vì header.

Nhầm lẫn ba loại này là nguồn gốc của nhiều lỗi về địa chỉ trả lời, bounce và truy vết email.

## 2. Header theo chuẩn Internet Message Format

Một thông điệp email truyền qua SMTP có cấu trúc khái quát:

```text
From: "Cua hang" <orders@example.com>
To: "Khach hang" <customer@example.net>
Reply-To: support@example.com
Subject: Thong bao don hang
Date: Thu, 12 Nov 2026 08:30:00 +0000
Message-ID: <example-123@example.com>
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8
X-App-Correlation-ID: 3fa85f64-5717-4562-b3fc-2c963f66afa6

Xin chao,

Don hang cua ban da duoc tiep nhan.
```

Ví dụ trên dùng chữ không dấu để minh họa cú pháp raw header. Với tiếng Việt, Jakarta Mail có thể mã hóa các trường cần thiết theo MIME/SMTPUTF8 tùy trường hợp và khả năng máy chủ.

**Phần header kết thúc ở dòng trống đầu tiên.** Phần sau dòng trống là body. Header là các dòng `field-name: field-value` được ngăn cách theo chuẩn truyền email bằng CRLF (`\r\n`).

### Các ràng buộc cú pháp cần nhớ

- Tên trường header dùng ký tự ASCII hợp lệ; không được tùy tiện dùng khoảng trắng hoặc dấu hai chấm trong tên.
- Tên header về mặt giao thức **không phân biệt hoa/thường**: `Subject` và `subject` là cùng tên trường.
- Giá trị có quy tắc cú pháp riêng. `To` phải chứa địa chỉ hợp lệ; `Date` theo cú pháp ngày thư; `Message-ID` có định dạng định danh phù hợp.
- Một dòng header có giới hạn độ dài của định dạng message: tối đa **998 octet không tính CRLF**; chuẩn khuyến nghị khoảng **78 ký tự** để dễ tương thích và hiển thị. Header có thể cần **fold** sang dòng tiếp theo theo cú pháp hợp lệ.
- Không tự chèn `\r` hay `\n` lấy từ đầu vào bên ngoài vào trường header: hành vi đó có thể tạo **header injection**.
- Header dài có cách mã hóa và xuống dòng chuyên biệt. Đừng tự nối chuỗi rồi thêm CRLF theo ý mình; sử dụng API Jakarta Mail/Spring để thư viện xử lý.
- Header chuẩn và MIME có những quy tắc về trường được phép xuất hiện nhiều lần. Đặc biệt, không tự tạo hai `From` hoặc hai `Subject` cho một thông điệp rồi trông chờ gateway hiểu như ý.

Nhà cung cấp SMTP có thể đặt giới hạn chặt hơn chuẩn chung: số header, kích thước toàn bộ header, độ dài giá trị, tên bị cấm hoặc định dạng địa chỉ được chấp nhận. Các giới hạn này phải được xem trong tài liệu và cấu hình của provider cụ thể.

### Những header thường gặp

| Header | Vai trò | Lưu ý |
| --- | --- | --- |
| `From` | Danh tính người gửi được trình bày trong email | Thường bị yêu cầu dùng domain/địa chỉ đã xác minh |
| `Sender` | Tác nhân thực sự gửi khi khác tác giả nội dung trong `From` | Không phải lúc nào cũng cần; cú pháp và ý nghĩa riêng |
| `To` | Người nhận hiển thị | Không phản ánh đầy đủ mọi địa chỉ trong SMTP envelope |
| `Cc` | Người nhận bản sao hiển thị | Có thể làm lộ danh sách người nhận |
| `Bcc` | Người nhận bản sao kín | Cần bảo đảm không lộ trong bản giao cho người khác |
| `Reply-To` | Địa chỉ nhận phản hồi khi người dùng chọn Reply | Không tự quyết định bounce address hoặc danh tính DKIM |
| `Subject` | Tiêu đề thư | Dùng MIME encoding phù hợp cho ký tự tiếng Việt |
| `Date` | Ngày giờ phát hành thông điệp | Có thể được tạo khi thư được lưu/gửi |
| `Message-ID` | Định danh thông điệp theo chuẩn | Khác provider message ID và delivery ID |
| `MIME-Version` | Cho biết việc sử dụng MIME | Thường do Jakarta Mail thêm |
| `Content-Type` | Loại nội dung hoặc cấu trúc multipart | Do helper và quá trình đóng gói MIME thiết lập |
| `Content-Transfer-Encoding` | Mã hóa nội dung MIME khi truyền | Không nên tùy tiện sửa thủ công |
| `Received` | Dấu vết một chặng chuyển tiếp | Thường được MTA thêm vào trong quá trình vận chuyển |
| `Authentication-Results` | Kết quả kiểm tra xác thực do hệ thống nhận ghi nhận | Chỉ đáng tin khi xuất phát từ ranh giới đã tin cậy |
| `DKIM-Signature` | Chữ ký xác thực một số header và body | Cần xét vị trí ký và các phép sửa ở gateway |
| `List-Unsubscribe` | Cung cấp phương thức hủy đăng ký với email danh sách | ESP có thể tự tạo hoặc yêu cầu cú pháp nhất định |

Trong lập trình Spring, tốt nhất sử dụng các phương thức chuyên dụng của `MimeMessageHelper` cho những trường có API rõ ràng; chỉ dùng `setHeader` cho trường bổ sung thật sự cần thiết.

## 3. Phân biệt header địa chỉ với SMTP envelope

Đây là khác biệt quan trọng nhất khi làm việc với email gateway.

```text
Envelope SMTP:
MAIL FROM:<bounces@mailer.example.com>
RCPT TO:<customer@example.net>

Bên trong nội dung message:
From: "Shop Example" <orders@example.com>
To: customer@example.net
Reply-To: helpdesk@example.com
Subject: Cap nhat don hang
```

Các giá trị này có chức năng khác nhau:

- `From`: người dùng thường thấy là người gửi.
- `Reply-To`: nơi chương trình đọc thư đề xuất gửi phản hồi.
- `MAIL FROM` (envelope sender, reverse-path): địa chỉ phục vụ xử lý tình huống **không phát được/bounce** trong SMTP truyền thống; ESP có thể điều khiển hoặc thay thế nó.
- `RCPT TO`: người nhận ở tầng vận chuyển; không nhất thiết trùng tập địa chỉ hiển thị trong `To` hoặc `Cc`.

`Return-Path` là header liên quan đến đường trả lại mà hệ thống giao thư cuối thường thêm khi thực hiện giao. **Ứng dụng tự đặt `Return-Path` không đồng nghĩa thay đổi SMTP `MAIL FROM`.** Gateway/ESP có thể loại bỏ, viết lại hoặc thay giá trị theo envelope thực tế.

Ví dụ, nếu muốn nhận thư phản hồi tại `support@example.com`, ta dùng `Reply-To`. Nếu muốn nhận bounce tại `bounces@mailer.example.com`, cần cấu hình **envelope sender** bằng cơ chế provider hỗ trợ; việc chỉ viết header `Return-Path` là không đủ.

Một số cấu hình dùng SMTP transport `smtp` của Jakarta Mail có thuộc tính:

```properties
spring.mail.properties.mail.smtp.from=bounces@mailer.example.com
```

Thuộc tính này liên quan `MAIL FROM` của transport, và có thể áp dụng ở phạm vi session/transport. Nhà cung cấp SMTP vẫn có thể buộc sử dụng bounce domain của họ hoặc yêu cầu xác minh domain. Khi gửi từ nhiều domain/tenant, cần thiết kế cách cấu hình theo từng lần gửi sao cho không vô tình dùng cùng một envelope sender cho mọi tài khoản.

### Vì sao `To` không nói lên toàn bộ người nhận?

SMTP delivery có thể gửi một thông điệp đến nhiều địa chỉ `RCPT TO`, trong đó có Bcc. Một gateway cũng có thể mở rộng mailing list, chuyển tiếp người nhận hoặc đổi địa chỉ đích do chính sách nội bộ. Vì thế, để đếm số người được chấp nhận/giao thư phải dựa trên **sự kiện gửi theo recipient**, không dựa duy nhất vào header `To`.

## 4. Nhà cung cấp SMTP và gateway áp dụng những quy tắc nào?

Các bộ lọc có thể hoạt động ở ba thời điểm: trước khi nhận thư, khi xử lý trong relay, và khi giao tới hệ thống phía nhận.

| Nhóm quy tắc | Điều có thể xảy ra | Tác động đối với Spring Mail |
| --- | --- | --- |
| Kiểm tra sender | Yêu cầu `From` thuộc domain hoặc địa chỉ đã xác minh | Thư bị từ chối hoặc `From` bị rewrite |
| Xác thực SMTP/account | Account bị giới hạn gửi bằng sender khác | Cần đồng bộ tài khoản, domain và `From` |
| Kiểm tra cú pháp | Header thiếu colon, địa chỉ sai, newline bất hợp lệ | Phát sinh lỗi trước gửi hoặc SMTP rejection |
| Giới hạn dữ liệu | Quá nhiều recipient, header quá dài, thông điệp quá lớn | Bị chặn hoặc bị chia/xử lý lại theo provider |
| Chính sách chống spoofing | Domain alignment hoặc xác thực không đạt | Bị reject, quarantine, gắn cảnh báo hay spam |
| Chính sách tổ chức | Chèn disclaimer, lọc nội dung, sửa `Subject` | Nội dung/headers sau gateway khác bản gốc |
| Bảo vệ đường dẫn | Rewrite URL, quét link, thêm tracking | Đích link hiển thị và telemetry thay đổi |
| Metadata | Chặn reserved headers, thêm tracking ID, bỏ custom headers | Không thể dựa vào mọi header tự đặt được bảo toàn |
| DKIM signing | Chữ ký được thêm sau khi thông điệp được dựng | Việc sửa sau khi ký có thể làm xác thực thất bại |
| Quy tắc danh sách | Thêm/kiểm tra `List-Unsubscribe` với email tiếp thị | Phải phối hợp API, loại email và chính sách của ESP |

Không nên mặc định mọi nhà cung cấp đều thực hiện cùng một thao tác. Ví dụ, có ESP tự động thay sender không được xác minh bằng sender được phép; ESP khác từ chối request. Một email gateway doanh nghiệp có thể chèn chú thích “external email” vào subject trong khi gateway khác chỉ thêm banner vào body.

### Các kết cục phải phân biệt

1. **Client-side validation**: ứng dụng/Jakarta Mail từ chối giá trị không hợp lệ trước khi gửi.
2. **SMTP/API rejection**: provider trả lỗi, thường có mã SMTP/HTTP và thông điệp chi tiết.
3. **Accepted then filtered**: relay nhận thư nhưng sau đó chặn hoặc drop theo chính sách.
4. **Accepted and rewritten**: thư tiếp tục đi, nhưng header/nội dung sau gateway khác ban đầu.
5. **Delivered to receiving MTA**: hệ thống đích chấp nhận thư; chưa đồng nghĩa vào inbox hoặc được đọc.

Mỗi kiểu kết cục dẫn đến cách xử lý lỗi và quan sát vận hành khác nhau. Không nên xem lệnh `JavaMailSender.send(...)` thành công là bằng chứng header đã được giữ nguyên đến mailbox.

## 5. Header nào nên do ứng dụng tạo, header nào nên để thư viện/provider tạo?

Cách phân chia trách nhiệm giúp giảm xung đột:

| Trường | Chủ thể thiết lập phù hợp | Vì sao |
| --- | --- | --- |
| `From`, `To`, `Cc`, `Reply-To`, `Subject` | Ứng dụng, qua helper | Gắn trực tiếp ý nghĩa nghiệp vụ |
| `MIME-Version`, `Content-Type`, encoding MIME | Jakarta Mail/`MimeMessageHelper` | Phụ thuộc cấu trúc body và attachment |
| `Date`, `Message-ID` | Thư viện mail hoặc chiến lược Message-ID có kiểm soát | Cần định dạng đúng, có thể được sinh khi save/send |
| `Received` | SMTP relay/MTA trên từng chặng | Mô tả đường vận chuyển thực |
| `Authentication-Results` | Hệ thống kiểm tra xác thực phía nhận | Chỉ có ý nghĩa trong trust boundary thích hợp |
| `DKIM-Signature` | Hệ thống signing đã cấu hình | Ký sau khi nội dung cuối được xác định |
| `Return-Path` | Hệ thống giao cuối từ SMTP envelope | Ứng dụng không điều khiển bằng việc tự đặt header |
| `List-Unsubscribe` | Ứng dụng/ESP tùy luồng gửi và chính sách | Cần URL/cơ chế unsubscribe hợp lệ |
| Custom correlation header | Ứng dụng nếu provider cho phép | Gắn định danh kỹ thuật để truy vết |

Không nên tự thêm các header mô phỏng dấu vết vận chuyển như `Received` hoặc `Authentication-Results` để “làm email đáng tin hơn”. Chúng không thay thế việc kiểm tra SPF/DKIM/DMARC và có thể bị loại bỏ, làm sai lệch hoặc bị đối xử như dữ liệu không đáng tin.

## 6. Tạo header đúng cách với JavaMailSender và MimeMessageHelper

Spring Framework Mail cung cấp `JavaMailSender` để tạo `MimeMessage` và `MimeMessageHelper` để thiết lập các header phổ biến.

Ví dụ Spring Boot 3+/Spring Framework 6+ với Jakarta Mail:

```java
package example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {

    private final JavaMailSender mailSender;

    public OrderMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderNotification(
            String recipient,
            UUID deliveryId,
            String orderCode) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
            message, StandardCharsets.UTF_8.name()
        );

        helper.setFrom("orders@example.com", "Cửa hàng Example");
        helper.setTo(recipient);
        helper.setReplyTo("support@example.com");
        helper.setSubject("Xác nhận đơn hàng");
        helper.setText(
            "Đơn hàng " + orderCode + " đã được tiếp nhận.",
            false
        );

        // ID do server tạo, không chứa thông tin bí mật.
        message.setHeader(
            "X-App-Delivery-ID",
            deliveryId.toString()
        );
        message.setHeader(
            "X-App-Message-Category",
            "transactional"
        );

        mailSender.send(message);
    }
}
```

Điểm chính của ví dụ:

- `helper.setFrom(address, personalName)` cho phép display name tiếng Việt; helper dùng encoding để mã hóa đúng.
- `helper.setTo(...)` và `setReplyTo(...)` đặt địa chỉ theo API của thư viện, có quy tắc parse riêng.
- `helper.setSubject(...)` để thư viện mã hóa tiếng Việt thay vì tự ghép một raw header.
- `message.setHeader(...)` chỉ dùng cho header bổ sung với dữ liệu **an toàn, định dạng cố định**.
- `setHeader` thay các giá trị hiện có của trường cùng tên; `addHeader` thêm giá trị khác. Không tùy tiện tạo nhiều bản cho các header vốn chỉ có một giá trị.
- Giá trị `deliveryId` là UUID sinh bởi ứng dụng, không chứa token truy cập hoặc dữ liệu nhạy cảm.

`mailSender.send(...)` sẽ chuyển thông điệp qua SMTP transport; những thay đổi sau đó tại provider/gateway nằm ngoài phạm vi điều khiển trực tiếp của `MimeMessageHelper`.

### Cấu hình tối thiểu trong Spring Boot

```properties
spring.mail.host=smtp.example.com
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.default-encoding=UTF-8

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

Cấu hình này chỉ là ví dụ. SMTP host, port, tài khoản, TLS mode và sender domain phải đúng yêu cầu của provider thực tế. Một provider có thể chỉ cho gửi từ domain đã xác minh và sử dụng bounce domain riêng dù ứng dụng đã cấu hình `From`.

## 7. Xác thực header địa chỉ và ngăn header injection

Một rủi ro nguy hiểm là tạo raw header từ dữ liệu người dùng, đặc biệt khi dữ liệu có ký tự xuống dòng.

Ví dụ **không an toàn**:

```java
String unsafeName = request.getParameter("displayName");

// Không làm như sau:
message.setHeader("From", unsafeName + " <orders@example.com>");
```

Nếu `unsafeName` chứa chuỗi xuống dòng và một tên header mới, thao tác xây raw header bằng chuỗi có thể bị lợi dụng hoặc bị các lớp thư viện/provider từ chối. Tùy thư viện và cách gửi, rủi ro có thể là header injection, lỗi cú pháp hoặc nội dung hiển thị không mong muốn.

### Nguyên tắc xử lý

1. **Địa chỉ email**: dùng các API nhận địa chỉ, như `MimeMessageHelper#setTo` hoặc `InternetAddress`. Áp dụng kiểm tra nghiệp vụ về độ dài, số recipient và địa chỉ/domain được phép.
2. **Display name**: dùng `setFrom(address, personalName)` hoặc API có hỗ trợ mã hóa tên người, không tự nối thành header raw.
3. **Subject**: dùng `helper.setSubject(...)`; giới hạn độ dài và chuẩn hóa văn bản theo mục đích nghiệp vụ.
4. **Custom header**: chỉ cho giá trị có cấu trúc chặt chẽ, ví dụ UUID, enum, short opaque ID. Từ chối CR/LF và các ký tự điều khiển không phù hợp.
5. **Thông tin nhạy cảm**: không nhúng mật khẩu, JWT, OTP, access token, chi tiết giao dịch riêng tư hoặc dữ liệu cá nhân không cần thiết vào header.

Ví dụ helper kiểm tra giá trị dùng cho một custom header nội bộ:

```java
package example.mail;

import java.util.regex.Pattern;

public final class MailHeaderValues {
    private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private MailHeaderValues() {}

    public static String requireSafeId(String value) {
        if (value == null || !SAFE_ID.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid mail header ID");
        }
        return value;
    }
}
```

Sau đó:

```java
message.setHeader(
    "X-App-Trace-ID",
    MailHeaderValues.requireSafeId(traceId)
);
```

Quy tắc này được thiết kế cho **opaque identifier ASCII ngắn**, không phải bộ kiểm tra hợp lệ phổ quát cho mọi header. Subject, địa chỉ email, MIME parameter và các trường chuẩn khác đều có cú pháp riêng; không thể áp cùng regex này lên tất cả.

### Trường Bcc và thông tin riêng tư

`Bcc` phục vụ gửi bản sao kín. Trong thư giao tới người nhận thông thường, danh sách Bcc không được để lộ như một header chứa toàn bộ địa chỉ ẩn. Hãy sử dụng `helper.setBcc(...)`/cơ chế thư viện; không tự chèn raw `Bcc` rồi tự xây SMTP request.

Khi gửi email hàng loạt tới những người không nên thấy địa chỉ của nhau, thường nên tạo delivery riêng theo recipient hoặc dùng chức năng bulk email có recipient isolation của ESP. Ngoài header, URL theo dõi, nội dung template và attachment cũng phải tránh làm lộ dữ liệu của người nhận khác.

## 8. Custom headers và metadata của nhà cung cấp

Đôi khi ứng dụng cần truyền một giá trị phục vụ đối soát: loại thông báo, mã delivery, mã campaign hoặc correlation ID.

Ví dụ:

```text
X-App-Delivery-ID: a6741f5e-3b53-4f99-9d27-3f6ab58310e6
X-App-Message-Category: transactional
X-App-Environment: production
```

Các trường dạng `X-*` xuất hiện nhiều trong hệ thống email hiện có. Về thiết kế chuẩn mới, quy ước luôn bắt đầu bằng `X-` không còn được khuyến khích như một cơ chế tiêu chuẩn hóa; nhưng các nhà cung cấp vẫn có thể yêu cầu hoặc hỗ trợ chính những trường có tiền tố đó. **Tên header phải theo hợp đồng thực tế với provider.**

### Vì sao không nên phụ thuộc tuyệt đối vào custom header?

- Một số provider có danh sách header **reserved** do họ quản lý và không cho ứng dụng ghi đè.
- Header tùy chỉnh có thể bị strip để giảm dữ liệu cá nhân hoặc phục vụ chính sách gateway.
- Một số ESP lấy metadata qua API/SMTP headers riêng rồi **xóa các header đó khỏi email cuối**.
- Gateway có thể đổi tên hoặc chuẩn hóa header; quy tắc tên không phân biệt chữ hoa/chữ thường.
- Khả năng quan sát custom header ở SMTP submission không bảo đảm nó xuất hiện khi người nhận xem raw message.

Nếu provider hỗ trợ **tags, categories, custom arguments, metadata hoặc correlation ID** qua API chính thức, ưu tiên dùng kênh được thiết kế cho mục đích này, rồi lưu mapping với `deliveryId` nội bộ. Nếu provider yêu cầu một header riêng để truyền metadata, theo đúng định dạng được công bố; không tự suy ra cú pháp từ provider khác.

### Các trường cần tránh xung đột

Không tự ghi đè một cách tùy tiện các trường mà Jakarta Mail hoặc provider có quyền quản lý, đặc biệt:

- `Message-ID`, `Date`, `MIME-Version` và các `Content-*` liên quan trực tiếp đến cấu trúc MIME.
- `DKIM-Signature`: chữ ký phải phản ánh nội dung/headers cuối được ký.
- `Authentication-Results`, `Received`: dùng cho dấu vết vận chuyển và kết quả xác thực của MTA.
- `Return-Path`: phải khớp với logic SMTP envelope/giao thư.
- Những tên `X-...` riêng của ESP đã được nhà cung cấp coi là reserved.

Trước khi thêm custom header, cần biết nó có được provider cho phép hay không, có được gửi ra mailbox hay chỉ dùng trong API, giới hạn kích thước/kiểu dữ liệu là gì, và có bị ký DKIM hay không.

## 9. From, Reply-To và chính sách xác minh sender

Một tình huống phổ biến: ứng dụng đăng nhập SMTP bằng `smtp-account@example.net` nhưng muốn hiển thị:

```text
From: "Dich vu A" <orders@shop.example.com>
Reply-To: support@shop.example.com
```

Điều này **không tự động được phép** chỉ vì ứng dụng có thể tạo header. Provider có thể yêu cầu:

- Xác minh `shop.example.com` hoặc địa chỉ `orders@shop.example.com`.
- Cấu hình DNS/định danh sender phù hợp chính sách.
- Quyền gửi thay mặt địa chỉ hoặc domain đó trong tài khoản SMTP.
- Tuân thủ một miền `MAIL FROM`/bounce address do họ quy định.
- Không dùng display name mạo danh tổ chức khác.

Khi không đáp ứng, provider có thể từ chối tại SMTP/API, thay `From` bằng địa chỉ được phép hoặc yêu cầu dùng `Sender` theo chính sách. Không nên dùng cách “đặt Reply-To bằng địa chỉ mong muốn, From bằng địa chỉ provider” mà không xem nó có phù hợp trải nghiệm và chính sách xác thực hay không.

**Reply-To không quyết định SPF, DKIM hay DMARC alignment.** Nó chỉ định địa chỉ trả lời. Một `Reply-To` trỏ tới domain khác không tự làm cho `From` được xác thực.

## 10. SPF, DKIM, DMARC và ảnh hưởng của email gateway

Quy tắc header thường gắn chặt với xác thực danh tính người gửi. Ba cơ chế quan trọng:

| Cơ chế | Dựa vào | Điều kiểm tra |
| --- | --- | --- |
| SPF | IP gửi và danh tính SMTP envelope/HELO theo quy tắc SPF | Máy chủ gửi có được miền liên quan ủy quyền không |
| DKIM | Chữ ký trong `DKIM-Signature`, một tập header và body | Nội dung/phần header đã ký còn khớp với chữ ký không |
| DMARC | Domain ở header `From` và kết quả SPF/DKIM có alignment | Có ít nhất một cơ chế xác thực phù hợp và aligned hay không, theo chính sách domain |

Ví dụ:

```text
From: orders@shop.example.com
MAIL FROM: bounces@mailer.example.net
DKIM-Signature: v=1; d=shop.example.com; ...
```

Trong tình huống này, SPF có thể thành công với domain `mailer.example.net` nhưng **không aligned** với domain trong `From`. DKIM nếu xác minh thành công và `d=shop.example.com` đáp ứng alignment với `From` thì có thể góp phần giúp DMARC pass. Kết quả phụ thuộc chính sách strict/relaxed và cấu hình thực tế.

Đây là lý do một thông điệp gửi được qua SMTP chưa chắc vượt qua kiểm tra danh tính của mailbox đích.

### Gateway sửa header làm hỏng DKIM khi nào?

Một DKIM signature chỉ rõ các header đã ký và có hash của body. Nếu gateway **sửa nội dung đã được ký** hoặc thay đổi những phần mà canonicalization không bỏ qua, chữ ký có thể thất bại.

Ví dụ:

```text
Ứng dụng Spring tạo thông điệp
    |
    v
Gateway A ký DKIM
    |
    v
Gateway B thêm tiền tố "[EXTERNAL]" vào Subject
    |
    v
Máy chủ nhận kiểm tra DKIM
    |
    +--> DKIM có thể fail nếu Subject đã được ký và thay đổi
```

Tương tự, chèn disclaimer vào cuối body sau khi ký có thể làm hash body không khớp. Việc đổi MIME boundary, mã hóa lại nội dung hoặc sửa HTML có thể ảnh hưởng chữ ký. Một số thay đổi whitespace có thể được DKIM canonicalization chấp nhận; vì vậy không phải *mọi* thay đổi kỹ thuật đều làm fail.

Các cách kiến trúc thường hợp lý:

1. Cho các bước biến đổi nội dung dự kiến (template, tracking link, disclaimer, MIME packing) diễn ra **trước khi ký DKIM**.
2. Đặt DKIM signing tại chặng outbound cuối có thể kiểm soát được.
3. Nếu có relay/gateway sau signer, cấu hình để hạn chế sửa các phần đã ký, hoặc sử dụng signing lại theo chính sách phù hợp.
4. Theo dõi header `Authentication-Results` từ hệ thống nhận đáng tin, thay vì chỉ dựa vào việc ứng dụng thấy `DKIM-Signature` đã được thêm.

### Forwarding và ARC

Khi email được forward qua mailing list hoặc gateway, SPF có thể không pass ở IP chuyển tiếp; DKIM cũng có thể bị ảnh hưởng nếu nội dung bị sửa. Cơ chế **ARC (Authenticated Received Chain)** cho phép một số bên trung gian ghi lại thông tin xác thực qua các chặng. Tuy nhiên, ARC không bảo đảm thư sẽ được chấp nhận và không thay thế chính sách của receiving server.

Không tự thêm header ARC trong Spring chỉ để tăng điểm tin cậy; chuỗi ARC có giá trị khi được các tác nhân trung gian ký và đánh giá đúng cách.

## 11. MIME headers và ảnh hưởng của gateway lên HTML/attachment

Không chỉ `From` và `Subject`, các header MIME cũng có thể bị gateway xử lý.

Ví dụ thư có hai bản nội dung và PDF:

```text
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="outer"

--outer
Content-Type: multipart/alternative; boundary="inner"

--inner
Content-Type: text/plain; charset=UTF-8

Thong bao: vui long xem tai lieu.
--inner
Content-Type: text/html; charset=UTF-8

<p>Thong bao: vui long xem tai lieu.</p>
--inner--

--outer
Content-Type: application/pdf; name="guide.pdf"
Content-Disposition: attachment; filename="guide.pdf"
Content-Transfer-Encoding: base64

[base64 data]
--outer--
```

Cấu trúc trên chỉ là mẫu khái niệm, không phải MIME message đầy đủ để gửi nguyên xi. Trong ứng dụng, nên để `MimeMessageHelper` tạo cấu trúc và `DataSource`/`Resource` cung cấp nội dung.

Email gateway có thể:

- Quét attachment và chặn định dạng file nguy hiểm.
- Đổi tên tệp hoặc xóa attachment theo chính sách DLP.
- Thêm banner cảnh báo vào HTML hoặc text body.
- Rewrite liên kết trong HTML để chống phishing.
- Chuyển đổi encoding hoặc cấu trúc MIME khi cần xử lý nội dung.

Do đó, nếu đang debug “tệp đính kèm mất” hoặc “HTML bị vỡ”, phải kiểm tra thông điệp **trước và sau gateway**, không chỉ xem code Spring. Nếu có DKIM ở giữa, cũng cần kiểm tra thứ tự signing/biến đổi như phần trên.

## 12. Header List-Unsubscribe và email gửi hàng loạt

Email quảng bá, newsletter hoặc luồng gửi theo danh sách thường cần cơ chế hủy đăng ký rõ ràng. Các header thường gặp:

```text
List-Unsubscribe: <https://example.com/unsubscribe/opaque-token>,
 <mailto:unsubscribe@example.com>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

`List-Unsubscribe` liệt kê cách hủy đăng ký; `List-Unsubscribe-Post` với giá trị trên liên quan cơ chế one-click theo RFC 8058 khi được triển khai đúng. Cú pháp, yêu cầu xác thực, chính sách cho từng loại sender và cách provider hỗ trợ cần xem tài liệu của ESP và mailbox provider cụ thể.

Những điểm quan trọng:

- **Transactional** và **marketing/bulk** có thể chịu quy tắc khác nhau. Đừng áp dụng cùng quy trình hủy đăng ký cho mọi email mà không xác định mục đích gửi.
- Một số ESP tự thêm hoặc quản lý `List-Unsubscribe` thông qua tính năng unsubscribe của họ; tự thêm trùng có thể tạo hành vi không mong muốn.
- Endpoint one-click cần thực hiện theo phương thức và hợp đồng quy định; không nhầm với URL mở trang web tùy ý.
- Token hủy đăng ký nên có phạm vi và hiệu lực phù hợp, không chứa dữ liệu nhạy cảm thô.
- Một lần mailbox client gửi POST one-click cần được xử lý idempotent, không yêu cầu người dùng đăng nhập lại nếu giao thức/thiết kế one-click đã cho phép hủy bằng token hợp lệ.
- Không xây cách hủy đăng ký mà về bản chất lại khiến người dùng bị đăng ký thêm khi link scanner truy cập.

Spring Mail chỉ hỗ trợ xây dựng và gửi thông điệp; phần quản lý subscription, suppression list và logic unsubscribe phải được xây trong ứng dụng hoặc dịch vụ gửi email.

## 13. Message-ID, provider message ID và correlation ID

Một vấn đề khi truy vết qua gateway là các hệ thống dùng nhiều loại định danh có tên giống nhau.

```text
Ứng dụng:
  deliveryId = "f62a4acd-7f44-41ae-9c3f-2460feac42c9"

Raw email header:
  Message-ID: <98765.abc@example.com>

ESP:
  providerMessageId = "esp-msg-100245"

Webhook:
  providerEventId = "evt-20091"
  eventType = "delivered"
```

Các ID không nhất thiết trùng nhau:

- **Delivery ID**: định danh do ứng dụng sinh cho một email cần giao tới một người nhận.
- **Message-ID**: header có cú pháp Internet message ID, có thể do Jakarta Mail tạo khi lưu/gửi hoặc bị hệ thống khác thay đổi.
- **Provider message ID**: mã riêng mà ESP dùng để tìm thông điệp trong hệ thống của họ.
- **Event ID**: mã của một sự kiện như accepted, delivered, bounced, opened, clicked; dùng để chống xử lý webhook trùng.

Một email có nhiều người nhận có thể có chung Message-ID nhưng các kết quả giao thư khác nhau theo recipient. Vì vậy, hệ thống không nên dùng `Message-ID` làm khóa duy nhất cho mọi record delivery/recipient.

### Gắn ID theo cách bền vững

Nếu ESP cho phép custom metadata, lưu `deliveryId` ở đó; nếu chỉ hỗ trợ header riêng, dùng header an toàn như:

```text
X-App-Delivery-ID: f62a4acd-7f44-41ae-9c3f-2460feac42c9
```

Trong database nên lưu thêm mapping giữa delivery ID, provider ID và attempt ID. Không nên phụ thuộc vào việc custom header này sẽ nguyên vẹn đi qua mọi gateway.

Để xem thư đã trải qua những chặng nào, các header `Received` của mailbox có thể hữu ích, nhưng **không thể mặc định tin mọi dòng Received** vì các header bên dưới ranh giới do hệ thống tin cậy thêm vào có thể chứa dữ liệu do bên gửi cung cấp. Khi điều tra, cần xác định chặng tin cậy bắt đầu từ đâu.

## 14. Cách provider có thể xử lý header lỗi hoặc bị cấm

Một số ví dụ thường gặp:

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| SMTP từ chối sender | `From` không thuộc địa chỉ/domain đã xác minh hoặc thiếu quyền | Xác minh sender và cấu hình tài khoản |
| Mail gửi được nhưng `From` bị thay | ESP có quy tắc rewrite sender | Kiểm tra chính sách gửi thay mặt domain |
| Người dùng trả lời sai mailbox | Thiếu/sai `Reply-To` | Dùng helper để đặt địa chỉ đúng |
| Bounce không về nơi mong muốn | Nhầm `Return-Path` header với SMTP `MAIL FROM` | Dùng bounce/envelope sender được provider hỗ trợ |
| Provider báo invalid header | Ký tự điều khiển, tên trường sai, giá trị không hợp lệ | Validate đầu vào, dùng API chuyên dụng |
| Subject tiếng Việt bị lỗi | Mã hóa/charset header không đúng | Dùng UTF-8 và `helper.setSubject` |
| Custom header mất ở mailbox | ESP/gateway strip hoặc dùng nó làm metadata | Xem chính sách provider, lưu mapping riêng |
| DKIM fail sau gateway | Header/body đã ký bị biến đổi | Sắp xếp signing sau transformation |
| Thư vào spam dù đã accepted | Sender reputation, nội dung, SPF/DKIM/DMARC, chính sách nhận | Kiểm tra xác thực và kết quả phía nhận |
| Email hàng loạt thiếu tùy chọn hủy | Chưa phối hợp cơ chế List-Unsubscribe/suppression | Cấu hình theo loại email và provider |
| Bcc bị lộ | Tự tạo raw header hoặc ghép danh sách người nhận sai | Dùng API Bcc/recipient isolation |

Một provider có thể trả mã SMTP `550`, `553`, `554` hoặc một mã lỗi khác tùy trường hợp; **không gán cứng một mã SMTP cho mọi lỗi header**. Đọc cả mã phản hồi mở rộng, thông điệp lỗi và tài liệu của provider. Trên API email, mã HTTP `400`/`422` có thể dùng cho dữ liệu không hợp lệ, nhưng hợp đồng thực tế vẫn khác nhau giữa nhà cung cấp.

## 15. Quan sát header trước và sau khi gửi

Trong quá trình phát triển, có thể kiểm tra một `MimeMessage` mà Spring tạo. Ví dụ, một số thông tin có thể được đọc bằng API:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
    new MimeMessageHelper(message, "UTF-8");

helper.setFrom("orders@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Thông báo");
helper.setText("Nội dung", false);
message.setHeader("X-App-Delivery-ID", "delivery-123");

// Lưu cập nhật để các header do Jakarta Mail sinh ra được cập nhật.
message.saveChanges();

// Ví dụ đọc header cụ thể ở giai đoạn local:
String[] values = message.getHeader("X-App-Delivery-ID");
```

Đây là **quan sát nội dung local trước khi đi qua provider**. Sau `send`, các thành phần khác có thể thêm, bỏ hoặc đổi header. Muốn đối chiếu đúng đường vận chuyển, nên sử dụng hộp thư thử nghiệm hoặc công cụ nhận SMTP cho môi trường phát triển, đồng thời quan sát raw message thực tế ở phía nhận khi được phép.

Với nội dung thật, tránh in toàn bộ headers vào log production: `To`, `Cc`, `Message-ID`, tracking token và dữ liệu tùy chỉnh có thể chứa thông tin nhạy cảm.

### Những lớp dữ liệu nên ghi nhận

| Nguồn | Thông tin phù hợp | Giới hạn |
| --- | --- | --- |
| Spring service | Delivery ID, loại thông báo, sender domain, thời điểm gửi | Không biết chắc thông điệp sau gateway |
| SMTP submission | Thành công/thất bại khi truyền đến relay | Chưa chứng minh delivered tới mailbox |
| ESP API/webhook | Provider ID, rejected, delivered, bounce, suppression | Theo định nghĩa event của nhà cung cấp |
| Mailbox raw headers | `Received`, `Authentication-Results`, `From` cuối | Chỉ phản ánh một bản thư đã nhận, cần xét trust boundary |
| Gateway logs | Header bị thay, rule ID, policy decision | Chỉ có nếu tổ chức có quyền truy cập gateway |

Khi điều tra một sự cố, dùng cùng delivery ID và provider message ID để nối dữ liệu các tầng. Ví dụ nếu `From` được ứng dụng tạo đúng nhưng mailbox nhận địa chỉ khác, logs của SMTP relay/ESP và raw headers phía nhận sẽ giúp xác định nơi rewrite.

## 16. Tình huống thực tế: Spring gửi thư qua gateway doanh nghiệp

Giả sử hệ thống thương mại điện tử cần gửi email xác nhận với các yêu cầu:

- Hiển thị `From: orders@shop.example.com`.
- Người dùng trả lời tới `help@shop.example.com`.
- Bounce được xử lý qua ESP.
- Mỗi email có delivery ID để đối soát.
- Gateway doanh nghiệp thêm disclaimer và ký DKIM.
- Người nhận có thể sử dụng Gmail, Outlook hoặc máy chủ doanh nghiệp khác.

Luồng triển khai hợp lý:

**Bước 1 — Xác minh danh tính gửi.** Cấu hình và xác minh `shop.example.com`/địa chỉ gửi tại ESP; thực hiện SPF/DKIM/DMARC và bounce domain theo khả năng/khuyến nghị của provider.

**Bước 2 — Tạo email trong Spring.** Dùng `MimeMessageHelper` để đặt `From`, `To`, `Reply-To`, `Subject` và body. Đặt correlation ID an toàn trong metadata/provider API hoặc custom header được hỗ trợ.

**Bước 3 — Kiểm soát nội dung trước ký.** Nếu gateway cần thêm disclaimer, banner hoặc rewrite link, cố gắng thực hiện những biến đổi này trước khi DKIM signer tạo chữ ký cuối.

**Bước 4 — Gửi qua SMTP.** `JavaMailSender.send(...)` giao thông điệp cho relay. Chỉ ghi nhận kết quả submission, không mặc định đã delivered.

**Bước 5 — Xử lý chính sách provider.** Theo dõi lỗi vì sender không hợp lệ, reserved header, kích thước header, chính sách DLP hoặc attachment. Nếu bị reject, sửa cấu hình/nội dung theo nguyên nhân, tránh retry mãi không đổi.

**Bước 6 — Đối chiếu phía nhận.** Khi có vấn đề, kiểm tra raw headers và kết quả SPF/DKIM/DMARC, đặc biệt `From`, `Return-Path`, `Message-ID`, `Received` và `Authentication-Results` ở ranh giới tin cậy.

**Bước 7 — Gắn dữ liệu vào dashboard.** Lưu accepted/delivered/bounce từ ESP theo provider message ID và recipient; giữ correlation ID nội bộ. Không yêu cầu một custom header phải xuất hiện nguyên vẹn trong email cuối để hệ thống vận hành.

### Một số nguyên tắc cốt lõi cho kiến trúc

- **Message header khác SMTP envelope.** `Reply-To` không thay bounce address và `Return-Path` không phải cách cấu hình `MAIL FROM`.
- **Provider/gateway là một phần của pipeline tạo email cuối.** Họ có thể kiểm tra, từ chối, thêm, bỏ hoặc viết lại header theo chính sách.
- **Spring giúp đặt header đúng cú pháp, nhưng không vượt qua quy tắc của nhà cung cấp.** `setFrom` và `setHeader` không cấp quyền gửi bằng domain chưa xác minh.
- **DKIM phụ thuộc vào thời điểm ký.** Thêm disclaimer hay sửa subject sau khi ký có thể làm xác thực không đạt.
- **Custom header phục vụ truy vết phải được coi là dữ liệu bổ sung.** Hệ thống nên giữ mapping ở database/ESP API thay vì phụ thuộc tuyệt đối vào header có thể bị strip.
- **Chỉ tin dấu vết được tạo bên trong ranh giới tin cậy.** Header `Received` hoặc `Authentication-Results` do bên gửi tùy ý thêm không chứng minh đường gửi hay kết quả xác thực.

Hiểu đúng các quy tắc này giúp ứng dụng Spring Framework Mail gửi thư với danh tính nhất quán, giảm lỗi bị gateway từ chối, bảo toàn xác thực khi thông điệp bị biến đổi và xây dựng hệ thống truy vết đáng tin cậy từ ứng dụng đến hệ thống thư phía nhận.
