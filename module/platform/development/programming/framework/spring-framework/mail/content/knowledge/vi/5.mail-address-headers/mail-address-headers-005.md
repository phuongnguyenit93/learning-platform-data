# Subject và mã hóa tiêu đề Unicode

Khi ứng dụng Spring gửi email với tiêu đề **“Xác nhận đơn hàng của Nguyễn An ✅”**, người nhận thường thấy dòng chữ có dấu tiếng Việt và biểu tượng như bình thường. Tuy nhiên, khi mở **nguồn email thô** (*raw message/source*), trường tiêu đề có thể trông giống một chuỗi ký tự ASCII khó đọc, chẳng hạn những cụm bắt đầu bằng `=?UTF-8?...?=`.

Đó không nhất thiết là lỗi. **`Subject` là một trường header của email**, và hệ thống email truyền thống cần một cách biểu diễn chữ Unicode sao cho nhiều máy chủ, chương trình xử lý và ứng dụng đọc thư có thể trao đổi tiêu đề an toàn. Cách thông dụng là dùng **MIME encoded-word theo RFC 2047**. Trong Spring Framework Mail, việc này thường do **Jakarta Mail** xử lý thông qua `MimeMessage` hoặc `MimeMessageHelper`.

Hiểu cơ chế này giúp giải thích vì sao một email có nội dung UTF-8 nhưng tiêu đề lại bị lỗi dấu, vì sao có các chuỗi `=?UTF-8?B?...?=` trong header, và vì sao **mã hóa phần thân** khác với **mã hóa header Subject**.

## 1. Subject nằm ở đâu trong một email?

Một email có **header** và **body**, phân cách bằng một dòng trống. Ví dụ:

~~~text
From: notice@example.org
To: an@example.net
Date: Thu, 12 Nov 2026 08:00:00 +0000
Subject: Order A102 confirmed
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Đơn hàng A102 đã được xác nhận.
~~~

Trong ví dụ này:

- `From` và `To` là các header mô tả người gửi/người nhận được hiển thị.
- `Subject` là **tiêu đề thư**, thường được trình đọc email hiển thị trong danh sách hộp thư, thông báo hoặc màn hình chi tiết.
- `Content-Type` mô tả loại nội dung và bộ ký tự của **body**.
- Phần sau dòng trống là **body** của email.

Một điểm thường bị nhầm: **`charset=UTF-8` trong `Content-Type` của body không tự quyết định cách mã hóa trường `Subject`**. Header có các quy tắc biểu diễn riêng. Một ứng dụng có thể gửi nội dung body UTF-8 đúng nhưng tiêu đề có dấu lại sai nếu cách dựng header không phù hợp.

Ngoài ra, `Subject` thuộc **nội dung thông điệp** được truyền trong SMTP `DATA`, không phải thông tin của SMTP envelope. Các lệnh `MAIL FROM` và `RCPT TO` phục vụ định tuyến; chúng không chứa tiêu đề Subject.

~~~mermaid
flowchart TD
    A["Thông điệp email"] --> B["Header"]
    A --> C["Body"]
    B --> D["From / To / Date"]
    B --> E["Subject: tiêu đề người đọc thấy"]
    C --> F["text/plain hoặc text/html"]
    E --> G["Mã hóa header khi cần"]
    F --> H["Charset và Content-Transfer-Encoding của body"]
~~~

## 2. Vì sao Subject có dấu tiếng Việt cần mã hóa?

Các chuẩn email truyền thống xây dựng cú pháp header chủ yếu quanh **US-ASCII**. Chữ Việt có dấu như `Đ`, `ă`, `ộ`, `ỹ` và nhiều biểu tượng emoji không thể biểu diễn trực tiếp dưới dạng byte ASCII đơn thuần.

Giả sử ứng dụng muốn đặt:

~~~text
Subject: Chào bạn – Đơn hàng đã được xác nhận ✅
~~~

Về mặt ý nghĩa đây là tiêu đề hoàn toàn hợp lệ đối với người đọc. Tuy nhiên, nếu đưa các byte UTF-8 thô vào một tuyến email chỉ hiểu dạng header ASCII truyền thống, một phần mềm trung gian có thể đọc sai, từ chối hoặc làm hỏng nội dung.

**MIME encoded-word** cho phép biểu diễn đoạn Unicode bằng các ký tự ASCII theo một khuôn dạng có khai báo bộ ký tự. Bên nhận giải mã đoạn đó để hiển thị Unicode ban đầu.

Ví dụ nhỏ với từ “Café”:

~~~text
Subject: =?UTF-8?B?Q2Fmw6k=?=
~~~

Giải mã encoded-word trên sẽ cho ra:

~~~text
Café
~~~

Trong một ví dụ khác, cùng nội dung có thể dùng cách mã hóa Q:

~~~text
Subject: =?UTF-8?Q?Caf=C3=A9?=
~~~

Cả hai đều diễn đạt chữ “Café”. Mã hóa nào được chọn phụ thuộc vào thư viện và đặc điểm dữ liệu, không phải người nhận cần biết hay chọn bằng tay.

**Lưu ý về email quốc tế hiện đại:** RFC 6532 cho phép dùng UTF-8 trực tiếp trong một số header khi môi trường truyền thư hỗ trợ SMTPUTF8 theo RFC 6531. Vì thế, không phải mọi email Unicode hiện đại đều bắt buộc có encoded-word. Tuy nhiên, RFC 2047 vẫn là cơ chế quan trọng và rất phổ biến để giữ khả năng tương thích rộng với các hệ thống xử lý header theo định dạng ASCII truyền thống.

## 3. Cú pháp MIME encoded-word của Subject

Một encoded-word có dạng:

~~~text
=?charset?encoding?encoded-text?=
~~~

Các thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `=?` | Ký hiệu bắt đầu encoded-word | `=?` |
| `charset` | Bộ ký tự dùng để chuyển văn bản thành byte | `UTF-8` |
| `encoding` | Cách chuyển những byte đó thành chuỗi ASCII | `B` hoặc `Q` |
| `encoded-text` | Nội dung sau khi mã hóa | `Q2Fmw6k=` |
| `?=` | Ký hiệu kết thúc encoded-word | `?=` |

Với chuỗi:

~~~text
=?UTF-8?B?Q2Fmw6k=?=
~~~

ta đọc lần lượt:

1. `=?` báo bắt đầu một encoded-word.
2. `UTF-8` cho biết văn bản ban đầu được chuyển thành byte theo UTF-8.
3. `B` yêu cầu giải mã phần sau theo Base64.
4. `Q2Fmw6k=` là dữ liệu đã được biểu diễn bằng Base64.
5. `?=` kết thúc encoded-word.

Sau khi giải mã Base64 thành byte, trình đọc dùng UTF-8 để khôi phục ký tự Unicode “Café”.

Tên bộ ký tự không phải là tên ngôn ngữ. `UTF-8` có thể biểu diễn tiếng Việt, tiếng Nhật, chữ Ả Rập, emoji và nhiều hệ chữ khác. Không có một “UTF-8 dành riêng cho tiếng Việt” trong cú pháp này.

### 3.1. Mã hóa B

Chữ **B** chỉ phương thức biểu diễn bằng **Base64**. Ví dụ:

~~~text
Văn bản:     Café
UTF-8 bytes: 43 61 66 C3 A9
Base64:      Q2Fmw6k=
Encoded:     =?UTF-8?B?Q2Fmw6k=?=
~~~

B thường phù hợp khi một tiêu đề chứa nhiều byte ngoài ASCII, chẳng hạn tiếng Việt có dấu dày đặc hoặc ký tự từ các hệ chữ khác. Nhưng một tiêu đề ngắn vẫn có thể dùng Q nếu thư viện chọn như vậy.

### 3.2. Mã hóa Q

Chữ **Q** sử dụng cú pháp tương tự *quoted-printable* nhưng **không giống hoàn toàn quy tắc quoted-printable cho body**. Một số byte được giữ dưới dạng ký tự ASCII đọc được, byte cần biểu diễn đặc biệt dùng `=HH` (hai chữ số hệ 16).

Ví dụ:

~~~text
Văn bản:     Café
Encoded:     =?UTF-8?Q?Caf=C3=A9?=
~~~

`=C3=A9` đại diện cho hai byte UTF-8 của chữ `é`. Với dấu cách, **Q-encoding trong encoded-word có thể dùng dấu gạch dưới `_`**:

~~~text
Subject: =?UTF-8?Q?Ch=C3=A0o_b=E1=BA=A1n?=
~~~

Sau giải mã, tiêu đề là:

~~~text
Chào bạn
~~~

Trong encoded-word mã hóa Q, dấu `_` biểu diễn một dấu cách. Nếu dữ liệu gốc thực sự có ký tự gạch dưới, nó cần được mã hóa phù hợp để tránh nhầm lẫn. Không thể tự thay mọi dấu `_` trong văn bản thông thường thành dấu cách; quy tắc này chỉ áp dụng **bên trong encoded-word Q**.

### 3.3. B và Q cùng hợp lệ

| Đặc điểm | `B` (Base64) | `Q` (Q-encoding) |
| --- | --- | --- |
| Cách biểu diễn | Mã hóa các byte thành chuỗi Base64 | Giữ một số ký tự ASCII; mã hóa byte khác thành `=HH` |
| Khả năng đọc bằng mắt trong email raw | Thường khó đọc | Có thể nhận ra một số đoạn ASCII |
| Văn bản nhiều ký tự không phải ASCII | Thường gọn hơn | Có thể dài hơn |
| Dấu cách trong encoded-word | Nằm trong dữ liệu Base64 | Thường biểu diễn bằng `_` |
| Kết quả sau giải mã đúng | Chuỗi Unicode gốc | Chuỗi Unicode gốc |

**Lựa chọn B hay Q là chi tiết biểu diễn**, không nên dùng để quyết định nội dung nghiệp vụ. Jakarta Mail có thể lựa chọn phương thức thích hợp.

## 4. Điều gì xảy ra với Subject vừa có ASCII vừa có Unicode?

Một Subject thực tế thường kết hợp nhiều loại ký tự:

~~~text
[Shop] Đơn hàng #A102 đã giao ✅
~~~

Header trên đường truyền có thể được biểu diễn bằng một hoặc nhiều encoded-word, có thể xen với những đoạn ASCII thông thường. Ví dụ mô hình khái niệm:

~~~text
Subject: [Shop] =?UTF-8?B?...?=
~~~

Dấu `...` ở đây chỉ là phần minh họa cấu trúc, **không phải chuỗi Base64 thực có thể giải mã**. Khi được tạo thật, từng encoded-word phải chứa dữ liệu mã hóa hợp lệ, và toàn bộ phần Subject sau giải mã phải cho ra nội dung ban đầu.

Có một số điểm quan trọng:

- Một tiêu đề Unicode không nhất thiết chỉ nằm trong một encoded-word.
- Một số đoạn ASCII có thể giữ nguyên; những đoạn Unicode có thể được mã hóa.
- Nhiều encoded-word có thể xuất hiện liên tiếp để đáp ứng giới hạn độ dài mỗi đoạn.
- Khoảng trắng giữa các encoded-word kế nhau có quy tắc giải mã riêng; không nên dùng cách nối chuỗi tùy ý để đoán tiêu đề hiển thị.
- Việc chuyển một chuỗi Unicode thành byte UTF-8 phải bảo toàn ký tự, bao gồm cả ký tự có nhiều byte và emoji.

Vì vậy, **header raw có thể dài hơn nhiều so với số ký tự người đọc nhìn thấy**. Một chữ có dấu có thể sử dụng hai hoặc ba byte UTF-8; emoji có thể cần bốn byte; việc biểu diễn Base64 hoặc Q tiếp tục làm độ dài tăng.

## 5. Giới hạn độ dài và xuống dòng của Subject

Các header email truyền thống có quy tắc giới hạn chiều dài dòng. RFC 5322 quy định giới hạn cứng ở mức **998 ký tự trên một dòng header** (không tính CRLF), đồng thời khuyến nghị mỗi dòng không dài hơn **78 ký tự** để dễ xử lý.

Đối với RFC 2047, **một encoded-word không được dài quá 75 ký tự**, tính cả phần mở `=?`, charset, encoding, phần dữ liệu và phần kết thúc `?=`.

Điều này dẫn đến hai cơ chế dễ nhầm:

1. **Tách thành nhiều encoded-word:** nếu một tiêu đề Unicode rất dài, thư viện có thể chia thành nhiều encoded-word hợp lệ.
2. **Header folding (xuống dòng header):** một header dài có thể được gấp sang dòng tiếp theo bằng `CRLF` rồi một hoặc nhiều ký tự khoảng trắng hoặc tab.

Ví dụ minh họa việc gấp header:

~~~text
Subject: =?UTF-8?B?...encoded-word-1...?=
 =?UTF-8?B?...encoded-word-2...?=
~~~

Mỗi chuỗi có `...` trên đây là **placeholder minh họa**, không phải encoded-word có thể giải mã. Trong email hợp lệ, đoạn tiếp theo bắt đầu bằng khoảng trắng hoặc tab để trình đọc hiểu đây vẫn là **cùng một trường `Subject`**, không phải một header mới.

Khi xử lý header đã gấp dòng, trình phân tích thực hiện **unfolding** theo quy tắc header trước khi diễn giải nội dung. Với những encoded-word đứng cạnh nhau, RFC 2047 còn quy định cách xử lý khoảng trắng dùng để ngăn cách chúng, tránh thêm dấu cách ngoài ý muốn vào văn bản đã giải mã.

### Vì sao không được cắt tùy tiện ở vị trí byte?

Một ký tự tiếng Việt hoặc emoji có thể có nhiều byte UTF-8. Cắt một byte sequence ngay giữa ký tự có thể tạo ra dữ liệu không còn là UTF-8 hợp lệ. Cắt một encoded-word sai vị trí có thể làm hỏng cấu trúc `=?...?=`.

Thư viện MIME phải chia tiêu đề tại ranh giới phù hợp và sinh những encoded-word hợp lệ. **Không nên tự tách một chuỗi Base64 bằng cách đếm ký tự rồi nối chúng thành các encoded-word** nếu chưa nắm rõ quy tắc mã hóa Unicode và RFC 2047.

Người dùng cuối cũng không cần nhìn thấy việc folding: mục tiêu là hiển thị một dòng tiêu đề dễ đọc trong giao diện.

## 6. Subject Unicode trong Spring Framework Mail

Ở mức ứng dụng, Spring Framework Mail cung cấp hai cách phổ biến để tạo email:

- `SimpleMailMessage` dành cho email văn bản đơn giản.
- `MimeMessage` cùng `MimeMessageHelper` dành cho thông điệp MIME, HTML, tệp đính kèm và các tùy chọn mã hóa rõ ràng hơn.

Nếu yêu cầu chú trọng đến tiêu đề Unicode, **`MimeMessageHelper` với charset `UTF-8` được chỉ định tường minh** là lựa chọn dễ hiểu và dễ bảo trì.

### 6.1. Thêm starter cho Spring Boot

Với một dự án Gradle đang dùng Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Sau đó cấu hình kết nối SMTP theo nhà cung cấp. Ví dụ:

~~~properties
spring.mail.host=smtp.provider.example
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
~~~

Địa chỉ `smtp.provider.example` chỉ là ví dụ. Các biến môi trường cần được cung cấp trong môi trường chạy, không đưa mật khẩu thật vào mã nguồn. Đây là cấu hình của **kết nối gửi thư**; nó độc lập với logic mã hóa Subject theo MIME.

### 6.2. Gửi email văn bản với Subject Unicode

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderConfirmationMailService {

    private final JavaMailSender mailSender;

    public OrderConfirmationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient, String orderCode)
            throws MessagingException {

        MimeMessage mimeMessage = mailSender.createMimeMessage();

        // UTF-8 áp dụng khi helper tạo các trường MIME cần mã hóa.
        MimeMessageHelper helper =
                new MimeMessageHelper(mimeMessage, false, "UTF-8");

        helper.setFrom("notice@example.org");
        helper.setTo(recipient);
        helper.setSubject(
                "Xác nhận đơn hàng " + orderCode + " ✅"
        );
        helper.setText(
                "Đơn hàng " + orderCode + " đã được xác nhận.",
                false
        );

        mailSender.send(mimeMessage);
    }
}
~~~

Ở đây:

1. `createMimeMessage()` tạo đối tượng thư của Jakarta Mail.
2. `new MimeMessageHelper(mimeMessage, false, "UTF-8")` chỉ định charset mặc định khi helper thao tác với thông điệp. Tham số `false` cho biết ví dụ không cần cấu trúc multipart.
3. `setSubject(...)` nhận **chuỗi Java Unicode bình thường**, chẳng hạn chuỗi có dấu tiếng Việt hoặc emoji.
4. Helper/Jakarta Mail chuẩn bị biểu diễn header thích hợp khi dựng thông điệp.
5. `send(...)` gửi email qua cấu hình SMTP của ứng dụng.

Điểm cốt lõi: **mã nghiệp vụ chỉ đặt nội dung Subject**, còn phần chuyển sang biểu diễn MIME phù hợp do thư viện xử lý. Không cần tự gọi Base64 trước khi đưa tiêu đề vào `setSubject`.

Đối với `orderCode`, ví dụ giả định đây là mã đơn hàng hợp lệ đã được kiểm soát bởi nghiệp vụ. Khi dữ liệu đến từ nguồn bên ngoài, cần xác thực nội dung trước khi đưa vào tiêu đề; đặc biệt không chấp nhận ký tự xuống dòng hoặc điều khiển bất thường có thể gây hiểu nhầm cấu trúc header.

### 6.3. Dùng API Jakarta Mail trực tiếp

Nếu không muốn sử dụng helper, có thể gọi `MimeMessage.setSubject(String, String)` để khai báo charset rõ ràng:

~~~java
MimeMessage message = mailSender.createMimeMessage();
message.setFrom("notice@example.org");
message.setRecipients(
        jakarta.mail.Message.RecipientType.TO,
        "recipient@example.net"
);
message.setSubject(
        "Thông báo: Đơn hàng đã được xác nhận ✅",
        "UTF-8"
);
message.setText("Đây là nội dung email.", "UTF-8");

mailSender.send(message);
~~~

Hàm `setSubject(subject, "UTF-8")` là điểm quan trọng: thư viện có đủ thông tin để tạo header Subject từ chuỗi Unicode. Với thư phức tạp, `MimeMessageHelper` thường thuận tiện hơn để cấu hình HTML, multipart và đính kèm.

### 6.4. Với SimpleMailMessage thì sao?

Ví dụ ngắn:

~~~java
import org.springframework.mail.SimpleMailMessage;

SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("notice@example.org");
message.setTo("recipient@example.net");
message.setSubject("Đơn hàng của bạn đã được xác nhận");
message.setText("Cảm ơn bạn đã đặt hàng.");
mailSender.send(message);
~~~

`SimpleMailMessage` nhận chuỗi Java nên có thể chứa Unicode trong Subject. Tuy nhiên, đường đi từ đối tượng thư đơn giản sang MIME và charset mặc định phụ thuộc cấu hình/thực thi gửi thư. Nếu cần **quy định rõ UTF-8 để tránh phụ thuộc môi trường**, việc dựng `MimeMessage` với `MimeMessageHelper(..., "UTF-8")` hoặc dùng `setSubject(..., "UTF-8")` giúp ý định hiển thị rõ ràng.

Không cần tự mã hóa Subject bằng `MimeUtility.encodeText(...)` rồi truyền kết quả mã hóa trở lại `helper.setSubject(...)`. Làm như vậy dễ dẫn tới **mã hóa hai lần** hoặc tạo header raw không như dự định.

## 7. Subject của thư HTML có khác không?

Không. Một thư HTML có thể cần `Content-Type: text/html; charset=UTF-8` cho **body**, nhưng `Subject` vẫn tuân theo cơ chế mã hóa header tương ứng.

Ví dụ:

~~~java
MimeMessage mail = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(mail, false, "UTF-8");

helper.setTo("recipient@example.net");
helper.setFrom("notice@example.org");
helper.setSubject("Ưu đãi tháng 11 🎁");
helper.setText(
        "<h1>Xin chào!</h1><p>Đây là email HTML.</p>",
        true
);

mailSender.send(mail);
~~~

Tham số `true` của `setText(..., true)` đánh dấu body là HTML. Nó **không phải tùy chọn “bật Unicode cho Subject”**. Charset của header và nội dung MIME được thư viện xử lý theo vị trí tương ứng.

Nếu một thư gửi thành công mà **body tiếng Việt hiển thị đúng nhưng Subject sai**, cần kiểm tra cách tạo Subject/header; chỉ sửa `Content-Type` của body chưa chắc giải quyết được.

Tương tự, `Content-Transfer-Encoding: base64` hoặc `quoted-printable` trên body/part không có nghĩa toàn bộ các header đã được mã hóa bằng cùng quy tắc. **`B`/`Q` của encoded-word trong header** và **Content-Transfer-Encoding của body** là những cơ chế có phạm vi khác nhau.

## 8. Đọc Subject đã mã hóa trong email raw

Một chương trình thư có thể lưu Subject trên đường truyền dưới dạng:

~~~text
Subject: =?UTF-8?Q?Ch=C3=A0o_b=E1=BA=A1n?=
~~~

Khi người nhận xem email trong ứng dụng đọc thư, trình đọc giải mã và hiển thị:

~~~text
Chào bạn
~~~

Có ba góc nhìn khác nhau đối với cùng một tiêu đề:

| Góc nhìn | Dữ liệu quan sát |
| --- | --- |
| Mã ứng dụng | `"Chào bạn"` dưới dạng chuỗi Java |
| Raw MIME header | `=?UTF-8?Q?Ch=C3=A0o_b=E1=BA=A1n?=` |
| Giao diện hộp thư | `Chào bạn` |

Khi đọc thư bằng API Jakarta Mail, `MimeMessage.getSubject()` thường trả về **giá trị đã được giải mã** (hoặc biểu diễn được diễn giải từ header). Nếu cần quan sát giá trị raw của header để chẩn đoán, có thể đọc `getHeader("Subject", null)`.

Ví dụ dành cho môi trường phát triển với thư **được tạo cho mục đích kiểm tra**, không sử dụng nội dung email nhạy cảm:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setFrom("notice@example.org");
helper.setTo("recipient@example.net");
helper.setSubject("Chào bạn");
helper.setText("Ví dụ nội dung thư.", false);

// Chuẩn bị các header của đối tượng MIME trước khi quan sát.
message.saveChanges();

String rawSubject = message.getHeader("Subject", null);
String decodedSubject = message.getSubject();

System.out.println("Raw Subject: " + rawSubject);
System.out.println("Decoded Subject: " + decodedSubject);
~~~

`rawSubject` có thể chứa encoded-word và có thể gồm các dòng header đã được gấp. `decodedSubject` là tiêu đề ở dạng thuận tiện cho ứng dụng. **Không nên phụ thuộc vào một chuỗi raw cụ thể**, vì Jakarta Mail có thể chọn B hay Q và cách chia encoded-word khác nhau giữa phiên bản hoặc điều kiện mã hóa.

### Vì sao source có thể chứa nhiều encoded-word?

Một Subject dài có thể được trải thành nhiều đoạn:

~~~text
Subject: =?UTF-8?Q?Ch=C3=A0o_b=E1=BA=A1n?=
 =?UTF-8?Q?_Caf=C3=A9?=
~~~

Đây là **ví dụ minh họa cấu trúc encoded-word liên tiếp**. Trình đọc email cần diễn giải toàn bộ trường header theo RFC 2047, bao gồm cách xử lý khoảng trắng giữa các encoded-word. Không nên dùng một hàm chuỗi tự viết kiểu “tách ở dấu cách rồi giải mã từng từ” vì có thể cho kết quả sai.

Nếu làm việc với một MIME message đã có sẵn ở dạng raw, có thể dùng chức năng giải mã của Jakarta Mail thay cho cách tự viết:

~~~java
import jakarta.mail.internet.MimeUtility;

String decoded = MimeUtility.decodeText(rawSubject);
~~~

Khi tiêu đề raw bao gồm cả phần header name như `Subject:` hoặc có folding, cần lấy đúng **giá trị trường header** trước khi truyền vào hàm. Với một `MimeMessage` hợp lệ, cách đơn giản là dùng `getSubject()`.

## 9. Subject, tên người gửi và địa chỉ email là ba vấn đề khác nhau

Các header hiển thị không chỉ có Subject. Ví dụ:

~~~text
From: Nguyễn An <nguyen.an@example.org>
To: Minh <minh@example.net>
Subject: Xác nhận lịch hẹn 📅
~~~

Ở đây có ít nhất ba loại dữ liệu:

- **Subject:** một trường văn bản tự do có thể cần encoded-word.
- **Tên hiển thị (display name)** như `Nguyễn An`: cũng có thể cần mã hóa header theo quy tắc phù hợp.
- **Địa chỉ thực** như `nguyen.an@example.org`: tuân theo cú pháp địa chỉ email; việc đưa Unicode vào phần tên hộp thư hay tên miền liên quan đến chuẩn email quốc tế và khả năng hỗ trợ của hạ tầng.

Khi dùng API Jakarta Mail để thiết lập tên hiển thị có dấu, có thể cung cấp charset riêng:

~~~java
import jakarta.mail.internet.InternetAddress;

InternetAddress sender = new InternetAddress(
        "notice@example.org",
        "Nhóm hỗ trợ khách hàng",
        "UTF-8"
);

helper.setFrom(sender);
helper.setSubject("Xác nhận lịch hẹn 📅");
~~~

`InternetAddress` xử lý dữ liệu địa chỉ và tên hiển thị. `setSubject` xử lý tiêu đề thư. Không nên nhét cả chuỗi `Subject: ...` hoặc `From: ...` vào `setSubject`; nó chỉ nhận **giá trị Subject**, không nhận một khối header hoàn chỉnh.

Đối với email có phần địa chỉ quốc tế hóa, việc hỗ trợ `SMTPUTF8` là chủ đề khác, cần xem cả SMTP server và đường chuyển tiếp. **Subject Unicode không có nghĩa địa chỉ người nhận cũng có thể dùng Unicode tùy ý ở phần trước dấu `@`.**

## 10. Khả năng dùng UTF-8 trực tiếp trong header hiện đại

RFC 6532 mở rộng cú pháp header để có thể chứa UTF-8 trực tiếp khi giao thức và đường chuyển thư hỗ trợ quốc tế hóa, thường gắn với **SMTPUTF8** theo RFC 6531.

Về mặt ý tưởng có thể gặp header dạng:

~~~text
Subject: Xác nhận đơn hàng ✅
~~~

với các byte UTF-8 trong header, thay vì toàn bộ Unicode được chuyển thành encoded-word ASCII.

Tuy nhiên, khi xây dựng ứng dụng Spring gửi email thông thường, cần phân biệt:

| Cách biểu diễn | Đặc điểm |
| --- | --- |
| RFC 2047 encoded-word | Biểu diễn các đoạn Unicode bằng chuỗi ASCII dạng `=?UTF-8?B?...?=` hoặc `=?UTF-8?Q?...?=`, tương thích rộng với hệ thống MIME truyền thống. |
| RFC 6532 UTF-8 trực tiếp | Cho phép Unicode trong header với điều kiện môi trường SMTP quốc tế hóa hỗ trợ việc truyền và xử lý dạng đó. |

Đây là **hai cách biểu diễn header**, không phải hai loại Subject mà người dùng cần chọn trong giao diện.

Một ứng dụng không nên giả định rằng bật UTF-8 trong một cấu hình Java đồng nghĩa toàn bộ SMTP relay và mọi chặng chuyển thư đều hỗ trợ SMTPUTF8. Nếu có yêu cầu đặc biệt dùng địa chỉ email quốc tế, cần đánh giá trọn đường truyền và khả năng hỗ trợ của nhà cung cấp.

Đối với tiêu đề Unicode thông thường qua `JavaMailSender`, cách dễ duy trì là **truyền chuỗi Unicode vào API MimeMessage/MimeMessageHelper với charset rõ ràng** và để thư viện quyết định cách biểu diễn header phù hợp.

## 11. Các lỗi thường gặp khi mã hóa Subject Unicode

### 11.1. Hiện dấu hỏi, ký tự thay thế hoặc chữ bị hỏng

Ví dụ người nhận thấy:

~~~text
Ch?o b?n
~~~

hoặc:

~~~text
ChÃ o báº¡n
~~~

Nguyên nhân có thể là văn bản bị chuyển qua bộ ký tự không phù hợp tại một khâu trước hoặc trong khi tạo email. Một trường hợp là **mojibake**: byte UTF-8 bị diễn giải bằng một bảng mã khác, tạo ra ký tự sai.

Nếu chuỗi Java **đã bị hỏng trước khi gọi** `setSubject`, thư viện MIME mã hóa chính chuỗi sai đó; chỉ chỉ định `UTF-8` sau cùng sẽ không khôi phục được dữ liệu gốc.

Cần xem đường đi của dữ liệu: nguồn từ cơ sở dữ liệu/API, chuỗi Java được dựng ra, charset trong API tạo MIME và giá trị header trên đường truyền.

### 11.2. Header chứa hai lớp encoded-word

Nếu một đoạn raw đã được mã hóa bằng `MimeUtility.encodeText(...)` rồi lại đưa qua một API tự mã hóa, thư nhận có thể hiển thị nguyên chuỗi `=?UTF-8?...?=` hoặc nhận kết quả không như mong muốn.

Thay vì:

~~~java
// Tránh tự mã hóa trước khi gọi helper.setSubject(...).
// String preEncoded = MimeUtility.encodeText(subject, "UTF-8", "B");
// helper.setSubject(preEncoded);
~~~

hãy dùng:

~~~java
helper.setSubject("Thông báo: Đơn hàng đã xác nhận ✅");
~~~

API của helper nhận chuỗi văn bản cần hiển thị. Nếu bạn đang trực tiếp xây dựng thư dạng byte/raw ở một tầng thấp hơn, phải tuân theo quy tắc mã hóa của tầng đó; không trộn lẫn hai cách làm.

### 11.3. Subject quá dài hoặc bị xuống dòng lạ

Một số hệ thống hiển thị giới hạn số ký tự ở danh sách hộp thư; đây là **giới hạn của giao diện**. Mặt khác, MIME header có giới hạn kỹ thuật riêng nên thư viện có thể gấp header thành nhiều dòng khi serialize.

Khi thấy nhiều dòng Subject trong email raw, cần xem chúng có đúng dạng continuation line bắt đầu bằng khoảng trắng hoặc tab không. Không nên cố xóa toàn bộ CRLF thô mà chưa hiểu quy tắc folding.

Nếu Subject được tạo từ dữ liệu của người dùng, cần tránh ký tự CR/LF chủ động nằm trong dữ liệu đầu vào. Nếu dữ liệu có thể dài tùy ý, nên xác định độ dài hiển thị hợp lý tại tầng nghiệp vụ và rút gọn bằng thao tác **an toàn cho Unicode**, tránh cắt vào giữa cặp surrogate hoặc cụm ký tự kết hợp.

### 11.4. Body UTF-8 đúng nhưng Subject lại sai

Có thể do:

- Dùng `setText(..., "UTF-8")` nhưng không thiết lập Subject với charset phù hợp.
- Dữ liệu Subject đã bị lỗi bảng mã trước khi tạo email.
- Một middleware hoặc hệ thống khác ghi đè header.
- Phần mềm đọc thư xử lý header không đúng chuẩn.

Phân biệt bằng cách xem **giá trị Subject trước khi gửi**, **raw Subject được serialize** và **giá trị Subject được giải mã ở đầu nhận**. Mỗi tầng cho biết lỗi phát sinh ở đâu.

### 11.5. Email thô hiện =?UTF-8?...?= và tưởng là lỗi

Những chuỗi encoded-word là biểu diễn bình thường trong raw MIME. Cần phân biệt:

- **Raw source** hiển thị encoded-word: thường hoàn toàn bình thường.
- **Ứng dụng đọc thư** hiển thị tiêu đề Unicode đúng: kết quả mong đợi.
- **Ứng dụng đọc thư** hiển thị nguyên encoded-word trong danh sách Inbox: có thể bộ giải mã header bị lỗi hoặc header không được tạo đúng cú pháp.

Việc chỉ thấy Base64 trong phần nguồn **chưa phải bằng chứng** email bị lỗi.

### 11.6. Chủ đề Subject chứa ký tự xuống dòng do dữ liệu không tin cậy

Dữ liệu như tên khách hàng hoặc tên sản phẩm có thể được ghép vào Subject. Nếu cho phép các ký tự điều khiển như `CR` hoặc `LF` đi vào quá trình dựng header thô, ứng dụng có thể gây ra sự cố **header injection** hoặc email bị từ chối.

Nên xác thực dữ liệu đầu vào, giới hạn độ dài và sử dụng API header có cấu trúc của Jakarta Mail. Tránh dựng toàn bộ thư bằng cách nối chuỗi `"Subject: " + userInput + "\r\n"`. Dù thư viện có cơ chế bảo vệ, nghiệp vụ vẫn cần quyết định Subject được phép chứa những gì.

## 12. Subject và quyền riêng tư

Tiêu đề email thường hiển thị ở nhiều nơi ngoài phần nội dung thư: danh sách Inbox, thông báo đẩy trên điện thoại, bản xem trước hoặc hệ thống lưu nhật ký của dịch vụ email.

Vì vậy, tiêu đề rõ ràng không nên chứa dữ liệu bí mật không cần thiết, chẳng hạn:

- Mật khẩu, mã OTP hoặc liên kết khôi phục có token nhạy cảm.
- Thông tin tài chính hoặc thông tin cá nhân chi tiết khi không cần cho việc nhận diện email.
- Nội dung mà người nhận không mong muốn bị lộ trên màn hình khóa.

**RFC 2047 Base64 không phải mã hóa bảo mật.** Bất kỳ hệ thống nào đọc được header cũng có thể giải mã encoded-word; nó chỉ là một **cách biểu diễn ký tự**. STARTTLS cũng chỉ bảo vệ kết nối SMTP tương ứng, không biến Subject thành dữ liệu bí mật ở mọi máy chủ trung gian.

Khi cần gửi thông tin riêng tư, Subject nên nêu mục đích chung, chẳng hạn **“Bạn có thông báo mới”**, còn phần dữ liệu nhạy cảm được đặt trong luồng đã có chính sách truy cập phù hợp.

## 13. Gợi ý đặt Subject dễ đọc bằng tiếng Việt

Mã hóa đúng giúp chữ hiển thị; **nội dung Subject rõ ràng** giúp người nhận hiểu email. Một số nguyên tắc:

1. Đặt thông tin quan trọng ở đầu: `Xác nhận đơn hàng A102` thường rõ hơn một câu mở đầu dài.
2. Viết có dấu tiếng Việt bình thường; tránh bỏ dấu chỉ vì lo ngại SMTP. Thư viện MIME có cơ chế hỗ trợ Unicode.
3. Dùng emoji có chọn lọc; không phụ thuộc hoàn toàn vào một emoji để diễn đạt ý nghĩa vì thiết bị hiển thị có thể khác nhau.
4. Hạn chế viết hoa toàn bộ, lặp nhiều ký tự cảm thán hoặc nhồi quá nhiều từ khóa.
5. Có thể thêm mã tham chiếu không nhạy cảm khi người nhận cần đối chiếu: `Lịch hẹn #A102 đã được xác nhận`.
6. Với nội dung đa ngôn ngữ, dịch Subject từ template theo locale rồi truyền chuỗi Unicode cuối cùng vào `setSubject`; không tạo các bản mã hóa thủ công cho từng ngôn ngữ.

Ví dụ một dịch vụ có thể chuẩn bị Subject từ mẫu đã kiểm soát:

~~~java
String subject = switch (locale.getLanguage()) {
    case "vi" -> "Đơn hàng " + orderCode + " đã được xác nhận";
    case "en" -> "Order " + orderCode + " has been confirmed";
    default -> "Order confirmation: " + orderCode;
};

helper.setSubject(subject);
~~~

Mẫu này giả định biến `locale` kiểu `java.util.Locale` và `orderCode` đã được ứng dụng xác thực. **Template cho văn bản** và **mã hóa MIME** là hai bước: trước hết chuẩn bị đúng câu cần hiển thị, sau đó để thư viện biểu diễn câu ấy trong header.

## 14. Quy trình suy luận khi Subject Unicode hiển thị sai

Có thể lần lượt xác định vấn đề theo luồng:

~~~mermaid
flowchart TD
    A["Chuỗi Subject trong ứng dụng"] --> B{"Unicode trước gửi có đúng?"}
    B -->|"Không"| C["Kiểm tra nguồn dữ liệu / charset trước khi gửi"]
    B -->|"Có"| D["Tạo MIME với UTF-8 rõ ràng"]
    D --> E["Quan sát raw Subject"]
    E --> F{"Encoded-word / UTF-8 header hợp lệ?"}
    F -->|"Không"| G["Kiểm tra API dựng header và cấu hình MIME"]
    F -->|"Có"| H["Kiểm tra cách đọc/giải mã ở đầu nhận"]
    H --> I["Đối chiếu Subject hiển thị"]
~~~

Từng tầng có trách nhiệm riêng:

| Tầng | Câu hỏi cần trả lời |
| --- | --- |
| Nguồn dữ liệu | Chuỗi Java gốc có đúng dấu, ký tự và emoji không? |
| Mã dựng email | Đang dùng `MimeMessageHelper` hoặc `MimeMessage.setSubject` với charset phù hợp chứ? |
| Serialize MIME | Raw header có đúng cú pháp encoded-word, folding hoặc UTF-8 header được hỗ trợ không? |
| SMTP/relay | Hạ tầng có sửa đổi hoặc không hỗ trợ định dạng header đã chọn không? |
| Ứng dụng đọc thư | Bộ giải mã header có khôi phục đúng Unicode không? |

Không nên mặc định mọi ký tự sai xuất phát từ DNS, SMTP AUTH, STARTTLS hoặc nội dung HTML. Những phần đó giải quyết **chặng truyền**, **xác thực kết nối** hoặc **body**, còn lỗi Unicode Subject thường cần xem **chuỗi nguồn và biểu diễn header**.

## 15. Câu hỏi thực hành

**Câu 1.** Một email có header:

~~~text
Content-Type: text/html; charset=UTF-8
Subject: =?UTF-8?Q?Ch=C3=A0o_b=E1=BA=A1n?=
~~~

Subject hiển thị là gì? **“Chào bạn”**. `Content-Type` mô tả body HTML; encoded-word ở `Subject` có quy tắc giải mã riêng.

**Câu 2.** Hai chuỗi sau có thể biểu diễn cùng nội dung không?

~~~text
=?UTF-8?B?Q2Fmw6k=?=
=?UTF-8?Q?Caf=C3=A9?=
~~~

**Có.** Cả hai đều biểu diễn **“Café”**; một bên dùng Base64 và bên còn lại dùng Q.

**Câu 3.** Đoạn `=?UTF-8?B?...?=` trong nguồn email có nghĩa thư đã được mã hóa bí mật chưa? **Chưa.** Đây là mã hóa ký tự có thể giải mã công khai.

**Câu 4.** Trong Spring, có cần tự gọi Base64 trước khi `helper.setSubject("Xin chào")` không? **Không.** Truyền chuỗi Unicode nguyên bản vào helper và dùng charset phù hợp.

**Câu 5.** Tại sao Subject được tạo thành hai encoded-word trên hai dòng? Có phải hai Subject? **Không.** Đó có thể là một header duy nhất được gấp dòng hoặc chia encoded-word để tuân theo giới hạn của chuẩn.

**Câu 6.** Nếu Subject chứa emoji nhưng địa chỉ nhận hoàn toàn ASCII, có bắt buộc dùng địa chỉ SMTPUTF8 không? **Không phải chỉ vì Subject.** Header Unicode có thể được biểu diễn bằng RFC 2047. Địa chỉ email Unicode và SMTPUTF8 là một yêu cầu riêng.

## 16. Mô hình ghi nhớ

Trong Spring Framework Mail, `Subject` đi từ **chuỗi Unicode của ứng dụng** đến **header MIME của email** rồi được **ứng dụng đọc thư giải mã để hiển thị**.

~~~mermaid
flowchart LR
    A["String Java: Chào bạn"] --> B["MimeMessageHelper / Jakarta Mail"]
    B --> C["Subject: encoded-word RFC 2047"]
    C --> D["SMTP relay và máy chủ nhận"]
    D --> E["Trình đọc email giải mã"]
    E --> F["Hiển thị: Chào bạn"]
~~~

Hãy phân biệt bốn ý:

- **`Subject` là header**, có quy tắc biểu diễn Unicode riêng với body.
- **`=?UTF-8?B?...?=` hoặc `=?UTF-8?Q?...?=` là encoded-word**, có thể giải mã để lấy văn bản gốc.
- **`MimeMessageHelper.setSubject(...)` nhận chuỗi cần hiển thị**, còn thư viện lo mã hóa và cách gấp header.
- **Encoding khác encryption**: chuyển Unicode thành Base64 hoặc Q không làm tiêu đề trở nên bí mật.

Khi hiểu ranh giới đó, lập trình viên có thể xây dựng Subject tiếng Việt có dấu và emoji mà không phải tự thao tác với byte, đồng thời biết cách đọc raw header để xác định vì sao một tiêu đề hiển thị không đúng mong đợi.

