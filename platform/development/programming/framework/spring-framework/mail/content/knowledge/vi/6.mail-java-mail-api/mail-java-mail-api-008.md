# Kiểm tra trạng thái message trước khi gửi

Một ứng dụng Spring có thể tạo đối tượng `MimeMessage`, đặt người nhận, tiêu đề, nội dung HTML và tệp đính kèm rồi gọi `JavaMailSender.send(...)`. Nếu thiếu người nhận, tiêu đề chưa được điền, nội dung không đúng định dạng hoặc tệp đính kèm không truy cập được, lỗi có thể xuất hiện ngay lúc gửi; đôi khi yêu cầu gửi còn phải được xử lý lại. Vì thế, việc **kiểm tra trạng thái message trước khi gửi** giúp phát hiện sớm một số lỗi ngay tại ranh giới giữa mã nghiệp vụ và hạ tầng email.

Cần hiểu chính xác chữ **trạng thái** ở đây: `MimeMessage` không có một cờ chuẩn mang nghĩa “đã sẵn sàng”, “đã gửi” hoặc “đã chuyển phát”. Đối tượng này là **mô hình dữ liệu của thông điệp MIME**. Trước khi gửi, ứng dụng có thể kiểm tra **mức độ hoàn chỉnh và hợp lệ của các trường cần thiết**, **khả năng chuẩn bị nội dung** và **quy tắc nghiệp vụ**. Sau khi gửi, ứng dụng phải quản lý trạng thái xử lý và theo dõi chuyển phát bằng cơ chế khác.

Bài này tập trung vào những gì có thể quan sát và xác nhận **trước lệnh gửi** khi sử dụng **Spring Framework Mail và API Jakarta Mail**, đồng thời giải thích ranh giới của từng phép kiểm tra.

## 1. “Trạng thái message” có thể mang ba nghĩa khác nhau

Trong một hệ thống gửi email, người ta thường dùng cùng một từ *status* cho ba câu hỏi:

| Câu hỏi | Dữ liệu liên quan | Có thể biết trước khi gửi không? |
| --- | --- | --- |
| **Message đã chuẩn bị xong chưa?** | Người gửi, người nhận, Subject, body, MIME part, tệp đính kèm và quy tắc nghiệp vụ | **Có thể kiểm tra phần lớn**, bằng dữ liệu ứng dụng và API của message |
| **Message đã được nộp cho SMTP server chưa?** | Kết quả thực hiện `JavaMailSender.send(...)`, phản hồi SMTP, lỗi kết nối/xác thực | **Chưa**, vì thao tác gửi chưa được thực hiện |
| **Message đã đến người nhận chưa?** | Bounce, sự kiện chuyển phát, trạng thái ở nhà cung cấp, hệ thống nhận | **Không**, kể cả sau khi `send(...)` trả về bình thường |

Ví dụ một message đã có người gửi và người nhận nhưng không có nội dung. Có thể xem nó là **chưa sẵn sàng theo yêu cầu sản phẩm**. Ngược lại, một message có đủ dữ liệu và serialize MIME thành công vẫn có thể bị SMTP server từ chối vì tài khoản không được phép gửi hoặc vì chính sách của người nhận.

Mô hình tư duy hữu ích:

~~~mermaid
flowchart LR
    A["Dữ liệu nghiệp vụ"] --> B["Tạo MimeMessage"]
    B --> C["Kiểm tra trước gửi"]
    C -->|"Đạt yêu cầu"| D["JavaMailSender.send"]
    C -->|"Thiếu/sai dữ liệu"| E["Từ chối tạo yêu cầu gửi"]
    D --> F["SMTP relay tiếp nhận hoặc trả lỗi"]
    F --> G["Chuyển phát và phản hồi về sau"]
~~~

Kiểm tra trước gửi nằm ở nút **C**. Nó giúp giảm lỗi có thể phát hiện sớm, chứ không thay thế bước **D**, **F** hay **G**.

## 2. Vòng đời của MimeMessage trước và sau gửi

Khi sử dụng `JavaMailSender`:

1. Gọi `createMimeMessage()` tạo thông điệp MIME mới.
2. Điền các trường bằng `MimeMessageHelper` hoặc trực tiếp qua `MimeMessage`.
3. Kiểm tra dữ liệu nghiệp vụ và những header/recipient đã đặt.
4. Có thể gọi `saveChanges()` để hoàn thiện một số header MIME khi cần quan sát/serialize thông điệp.
5. Gọi `send(message)` để kết nối tới SMTP server theo cấu hình và nộp thư.
6. Ứng dụng ghi nhận kết quả gửi, quản lý thử lại và theo dõi các sự kiện chuyển phát về sau nếu cần.

Một sơ đồ trạng thái ở **tầng ứng dụng** có thể được đặt tên như sau:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT: Tạo yêu cầu gửi
    DRAFT --> PREPARED: Dựng MIME và kiểm tra dữ liệu
    DRAFT --> INVALID: Kiểm tra thất bại
    PREPARED --> SUBMITTING: Gọi JavaMailSender.send
    SUBMITTING --> ACCEPTED: SMTP nộp thư thành công
    SUBMITTING --> FAILED: Gửi lỗi hoặc không rõ kết quả
    ACCEPTED --> DELIVERED: Có bằng chứng từ nhà cung cấp
    ACCEPTED --> BOUNCED: Có phản hồi thư bị trả lại
~~~

**`DRAFT`, `PREPARED`, `SUBMITTING`, `ACCEPTED`, `DELIVERED` và `BOUNCED` là những tên trạng thái ứng dụng tự định nghĩa**, không phải enum hay thuộc tính có sẵn trong `MimeMessage`. Một ứng dụng đơn giản chỉ gửi thư ngay có thể không cần lưu toàn bộ vòng đời này; hệ thống có hàng đợi hoặc yêu cầu kiểm toán thường cần trạng thái riêng.

### Không có phương thức chuẩn `message.isSent()`

Jakarta Mail `Message` và `MimeMessage` cung cấp các getter/setter cho nội dung và metadata. Chúng không cung cấp một getter chuẩn có thể khẳng định một thư đã được SMTP server nhận hoặc đã vào Inbox.

Một vài API dễ gây nhầm:

- `getSentDate()` đọc **ngày gửi được ghi trên header của message** nếu có; giá trị này có thể do ứng dụng tự đặt. Nó **không chứng minh** SMTP đã gửi thành công.
- `getMessageID()` đọc header `Message-ID` nếu đã có. ID này thường được tạo khi hoàn thiện message, nhưng **có ID không có nghĩa thư đã gửi**.
- `getFlags()` thuộc cơ chế cờ thư như `SEEN`, `ANSWERED` hoặc `FLAGGED` khi làm việc với message trong hộp thư; nó **không phải thước đo trạng thái gửi SMTP**.
- `getSize()` có thể trả về `-1` khi kích thước không xác định; không thể lấy một giá trị kích thước “hợp lệ” để suy ra khả năng chuyển phát.

Nên đặt tên rõ ràng cho việc kiểm tra trước gửi: **`validatePreparedMessage`**, **`checkMailRequest`** hoặc **`verifyMessageMetadata`**, thay vì gọi chung `isSent`.

## 3. Những trường nên được xem xét trước gửi

Để đánh giá một email thông báo đã sẵn sàng hay chưa, trước tiên xác định **quy tắc sản phẩm**: email phải gửi cho ai, người gửi nào được phép sử dụng, nội dung bắt buộc gồm những gì và dữ liệu nào cần bảo vệ.

Sau đó mới đọc các trường trên message.

| Nội dung cần xem | API thường dùng | Điều có thể kết luận |
| --- | --- | --- |
| Người gửi hiển thị | `getFrom()` | Đối tượng đã được gán địa chỉ người gửi chưa |
| Người nhận To | `getRecipients(Message.RecipientType.TO)` | Có địa chỉ ở trường To hay không |
| Người nhận Cc | `getRecipients(Message.RecipientType.CC)` | Có những địa chỉ sao chép nào |
| Người nhận Bcc | `getRecipients(Message.RecipientType.BCC)` | Có những địa chỉ nhận ẩn nào |
| Tổng địa chỉ nhận | `getAllRecipients()` | Có ít nhất một địa chỉ đích mà Jakarta Mail nhìn thấy |
| Tiêu đề | `getSubject()` | Giá trị Subject mà thư viện trả về |
| Địa chỉ trả lời | `getReplyTo()` | Header Reply-To đã được đặt hay chưa |
| Loại nội dung | `getContentType()`, `isMimeType(...)` | Mô tả MIME hiện có hoặc loại body mà thư viện biểu diễn |
| Ngày ghi trên thông điệp | `getSentDate()` | Header thời gian, **không phải kết quả gửi** |
| Mã định danh thông điệp | `getMessageID()` | Header ID nếu đã được tạo/đặt, **không phải biên nhận chuyển phát** |

Nhiều getter có thể trả về **`null`** khi trường chưa được đặt; các getter MIME cũng có thể ném `MessagingException` khi xử lý thông điệp. Mã kiểm tra cần xử lý cả hai tình huống.

**Không có một bộ trường “bắt buộc” dùng chung cho mọi hệ thống.** Ví dụ email thông báo tự động có thể không cần `Reply-To`; email giao dịch có thể yêu cầu To và Subject theo mẫu cụ thể; một thư nội bộ dùng Bcc có thể có quy tắc khác. Hãy định nghĩa hợp đồng kiểm tra dựa trên mục đích của email.

## 4. Kiểm tra người gửi và người nhận

### 4.1. Người gửi phải thuộc danh tính được phép

Một ứng dụng có thể gọi:

~~~java
helper.setFrom("notice@example.org");
~~~

Sau đó đọc lại:

~~~java
Address[] from = message.getFrom();
~~~

Nếu `from == null` hoặc mảng rỗng, thông điệp có thể chưa được gán người gửi hiển thị theo hợp đồng của ứng dụng. Tuy nhiên, **`From` trong MIME khác với địa chỉ envelope sender** dùng ở SMTP `MAIL FROM`. Jakarta Mail/SMTP provider có thể áp dụng các quy tắc riêng cho địa chỉ envelope sender; thậm chí nhà cung cấp có thể viết lại hoặc từ chối địa chỉ From nếu không được xác minh.

Do đó, kiểm tra cú pháp địa chỉ chỉ là một phần. Ứng dụng còn cần biết địa chỉ gửi nào được **tài khoản SMTP hoặc nhà cung cấp cho phép**. Việc được phép gửi thực tế chỉ được xác nhận ở phía dịch vụ/hạ tầng.

### 4.2. Kiểm tra có người nhận

Với message đã tạo, có thể đọc:

~~~java
Address[] recipients = message.getAllRecipients();

if (recipients == null || recipients.length == 0) {
    throw new IllegalArgumentException(
            "Email cần ít nhất một người nhận"
    );
}
~~~

`getAllRecipients()` gom các địa chỉ nhận từ các loại `TO`, `CC` và `BCC` trong message. Nếu nghiệp vụ yêu cầu phải có người nhận **To** cụ thể, cần kiểm tra chính `TO` chứ không chỉ mảng tổng hợp.

Một email có người nhận Bcc nhưng không có To có thể phù hợp với một số tình huống gửi thông báo, song nhiều ứng dụng muốn chặn kiểu này để hạn chế gửi nhầm. Đó là quy tắc ứng dụng quyết định.

### 4.3. Kiểm tra cú pháp địa chỉ bằng InternetAddress

Jakarta Mail cung cấp `InternetAddress` để phân tích và kiểm tra **cú pháp** địa chỉ. Ví dụ hàm yêu cầu một địa chỉ mailbox:

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

public static InternetAddress parseOneMailbox(String raw)
        throws AddressException {

    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException(
                "Địa chỉ email không được để trống"
        );
    }

    InternetAddress[] addresses =
            InternetAddress.parse(raw, true);

    if (addresses.length != 1) {
        throw new IllegalArgumentException(
                "Chỉ cho phép một địa chỉ email"
        );
    }

    InternetAddress address = addresses[0];
    address.validate();
    return address;
}
~~~

`parse(..., true)` bật cách phân tích cú pháp nghiêm ngặt, còn `validate()` kiểm tra tính hợp lệ của cấu trúc địa chỉ theo phạm vi mà Jakarta Mail hỗ trợ.

**Kiểm tra địa chỉ không xác thực hộp thư có tồn tại.** Một địa chỉ đúng cú pháp vẫn có thể thuộc miền không nhận email, hộp thư chưa được tạo, tài khoản bị vô hiệu hóa hoặc bị nhà cung cấp từ chối. Việc thử gửi hoặc tra MX cũng không tạo ra bảo đảm tuyệt đối về khả năng chuyển phát.

Đối với email được tạo từ dữ liệu người dùng, nên xác thực địa chỉ **ngay khi tiếp nhận dữ liệu** và kiểm tra lại các điều kiện quan trọng trước gửi nếu dữ liệu có thể đã thay đổi.

## 5. Kiểm tra Subject và nội dung thư

### 5.1. Subject có được chuẩn bị đúng không?

`getSubject()` trả về chuỗi Subject trong dạng thuận tiện cho ứng dụng. Ví dụ:

~~~java
String subject = message.getSubject();

if (subject == null || subject.isBlank()) {
    throw new IllegalArgumentException(
            "Email thông báo phải có Subject"
    );
}
~~~

Jakarta Mail có thể mã hóa Subject Unicode thành MIME encoded-word khi tạo thông điệp. **Ứng dụng nên kiểm tra nội dung logic của Subject**, chẳng hạn “Xác nhận đơn hàng A102”, thay vì so sánh một chuỗi header raw cụ thể như `=?UTF-8?B?...?=`.

Cần chú ý nếu Subject ghép từ dữ liệu bên ngoài: giới hạn độ dài theo nhu cầu nghiệp vụ, tránh nhúng token nhạy cảm và không cho các ký tự điều khiển không phù hợp (đặc biệt CR/LF) đi vào header tự dựng. Dùng API `setSubject(...)` thay vì nối nguyên văn các dòng header.

### 5.2. MIME Content-Type có phù hợp không?

Với một thông điệp đơn giản:

~~~java
helper.setText("Đơn hàng đã được xác nhận.", false);
~~~

Phần nội dung thường được xây dựng dưới dạng văn bản thuần. Nếu ứng dụng đặt:

~~~java
helper.setText("<p>Đơn hàng đã được xác nhận.</p>", true);
~~~

phần thân được thiết lập như nội dung HTML. Có thể quan sát bằng:

~~~java
boolean isPlain = message.isMimeType("text/plain");
boolean isHtml = message.isMimeType("text/html");
String contentType = message.getContentType();
~~~

Tuy nhiên, email có tệp đính kèm thường có **`multipart/mixed`** ở cấp ngoài; thư HTML có ảnh nội tuyến có thể có **`multipart/related`** và các phần bên trong. Vì vậy, `message.isMimeType("text/html")` có thể trả về `false` dù **một part con** chứa HTML. Chỉ nhìn Content-Type cấp ngoài không chứng minh toàn bộ cấu trúc đã đúng hay body có nội dung.

### 5.3. Không lấy Content-Type làm bằng chứng body không rỗng

Một số API có thể cung cấp giá trị Content-Type mặc định ngay cả khi body chưa được chuẩn bị đầy đủ. Tương tự, phương thức `getContent()` có thể giải mã/đọc nội dung, khởi tạo đối tượng multipart hoặc truy cập nguồn dữ liệu.

Với nghiệp vụ chỉ cần chắc chắn chuỗi nội dung không rỗng, cách đơn giản và rõ ràng là **kiểm tra đầu vào trước khi đặt vào message**:

~~~java
static String requireBody(String text) {
    if (text == null || text.isBlank()) {
        throw new IllegalArgumentException(
                "Nội dung email không được để trống"
        );
    }
    return text;
}
~~~

Sau đó gọi:

~~~java
helper.setText(requireBody(body), false);
~~~

Với HTML có template, cần kiểm tra dữ liệu đầu vào, quá trình render và kết quả HTML trước khi thêm vào message. Header `text/html` đúng không có nghĩa HTML đã hợp lệ theo kỳ vọng giao diện, đã được thoát ký tự hoặc đã có đủ dữ liệu nghiệp vụ.

## 6. Đối với multipart và tệp đính kèm

Một message có đính kèm có thể gồm nhiều phần MIME:

~~~mermaid
flowchart TD
    A["MimeMessage"] --> B["multipart/mixed"]
    B --> C["Body: text/plain hoặc text/html"]
    B --> D["Attachment: invoice.pdf"]
    B --> E["Attachment: terms.txt"]
~~~

Khi sử dụng `MimeMessageHelper`:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setText("<p>Hóa đơn của bạn</p>", true);
helper.addAttachment("invoice.pdf", invoiceResource);
~~~

Đối tượng `MimeMessage` mô tả cấu trúc MIME, nhưng **khả năng đọc nội dung tệp** còn phụ thuộc vào `invoiceResource`. Tệp có thể bị xóa, quyền đọc bị thay đổi hoặc dữ liệu bị lỗi giữa lúc chuẩn bị và lúc serialize.

Nên kiểm tra nguồn đính kèm trước khi đưa vào thư:

~~~java
import org.springframework.core.io.Resource;
import java.io.IOException;

static void requireAttachment(Resource resource)
        throws IOException {

    if (resource == null
            || !resource.exists()
            || !resource.isReadable()) {
        throw new IllegalArgumentException(
                "Không đọc được tệp đính kèm"
        );
    }

    long size = resource.contentLength();
    long maxBytes = 10L * 1024 * 1024;

    if (size <= 0 || size > maxBytes) {
        throw new IllegalArgumentException(
                "Kích thước tệp không hợp lệ"
        );
    }
}
~~~

Đây chỉ là **một quy tắc minh họa** cho một tài nguyên được kỳ vọng là file thường. Có nguồn dữ liệu dạng stream không biết trước độ dài, hoặc nguồn không hỗ trợ truy cập lại nhiều lần. Trong ứng dụng thực, chọn loại `Resource`/`InputStreamSource` phù hợp với Jakarta Mail và giới hạn của nhà cung cấp; đặc biệt nguồn dữ liệu dùng để đính kèm nên đọc lại được khi thư viện thực hiện serialization.

Các điểm cần xét thêm tùy sản phẩm:

- Kích thước tổng email sau MIME encoding có thể **lớn hơn** kích thước tệp gốc, nhất là khi Base64.
- Tên tệp đính kèm phải được chuẩn hóa, tránh đường dẫn hoặc nội dung điều khiển không mong muốn.
- Loại MIME do người dùng cung cấp chưa chắc trùng với nội dung thực của tệp.
- Kiểm tra phần mềm độc hại và loại tệp được phép là trách nhiệm bảo mật của ứng dụng/dịch vụ chuyên dụng.
- Với tài nguyên có thể biến đổi, kiểm tra `exists()` trước gửi **không đảm bảo** nó vẫn tồn tại khi chương trình đọc dữ liệu thực tế.

Vì vậy, kiểm tra metadata của message và kiểm tra tài nguyên đính kèm là hai việc bổ sung cho nhau.

## 7. Vai trò của saveChanges() trước khi gửi

`MimeMessage.saveChanges()` là phương thức quan trọng của Jakarta Mail. Với message do ứng dụng mới xây dựng, nó có thể cập nhật các header MIME cần thiết, chẳng hạn những thông tin liên quan đến cấu trúc nội dung hoặc `Message-ID`. Nó cũng cho phép quá trình dựng/serialize phát hiện một số lỗi mà trước đó chưa lộ ra.

Ví dụ:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setTo("an@example.net");
helper.setFrom("notice@example.org");
helper.setSubject("Thông báo mới");
helper.setText("Xin chào!", false);

// Hoàn thiện thay đổi MIME để có thể quan sát header.
message.saveChanges();

String messageId = message.getMessageID();
String contentType = message.getContentType();
~~~

### saveChanges() không gửi thư

Lời gọi này:

- **Không kết nối đến SMTP relay chỉ vì nó được gọi.**
- **Không thực hiện xác thực SMTP hoặc truyền thư qua mạng.**
- **Không bảo đảm mọi tệp đính kèm có thể đọc ở thời điểm gửi sau đó.**
- **Không chứng minh người nhận tồn tại hay email sẽ chuyển phát được.**

Nó là một thao tác **chuẩn bị/cập nhật thông điệp MIME**, không phải hành động gửi.

### Có bắt buộc tự gọi saveChanges() không?

Thông thường **không cần** nếu mục tiêu chỉ là gửi một `MimeMessage` bình thường thông qua `JavaMailSender.send(...)`. Lớp triển khai gửi thư có trách nhiệm chuẩn bị thông điệp phù hợp trước khi truyền.

Việc gọi `saveChanges()` hữu ích khi muốn **quan sát header đã hoàn thiện, xuất MIME ra môi trường kiểm thử hoặc chuẩn bị thông điệp ở một giai đoạn riêng**. Nhưng nó có thể thay đổi metadata; không nên coi việc gọi nhiều lần là phép kiểm tra hoàn toàn không tác động.

Một `Message-ID` có thể được tạo hoặc thay đổi trong quá trình chuẩn bị. Vì vậy, nếu hệ thống cần một khóa idempotency hay mã yêu cầu gửi ổn định, hãy tạo **ID ở tầng ứng dụng** (ví dụ ID bản ghi outbox), thay vì coi `Message-ID` là khóa nghiệp vụ duy nhất.

## 8. Ví dụ hoàn chỉnh: kiểm tra trước khi gọi JavaMailSender.send()

Ví dụ dưới đây gửi một email văn bản trong ứng dụng Spring Boot. Quy trình tách thành **kiểm tra đầu vào**, **tạo message**, **kiểm tra metadata trước gửi** và **thực hiện gửi**.

### 8.1. Cấu hình Spring Boot

Với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Cấu hình minh họa:

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

app.mail.from=${APP_MAIL_FROM}
~~~

`smtp.provider.example` chỉ là hostname dùng để giải thích cấu hình; cần thay bằng máy chủ thực tế do dịch vụ email cung cấp. Biến môi trường dùng để tránh đưa mật khẩu SMTP vào mã nguồn. TLS và thông số xác thực phải theo đúng yêu cầu của nhà cung cấp.

### 8.2. Dịch vụ gửi thư

~~~java
import jakarta.mail.Address;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NoticeMailService {

    private final JavaMailSender mailSender;
    private final String configuredFrom;

    public NoticeMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String configuredFrom) {

        this.mailSender = mailSender;
        this.configuredFrom = configuredFrom;
    }

    public void sendNotice(
            String recipient,
            String subject,
            String body) throws MessagingException {

        // 1. Kiểm tra yêu cầu nghiệp vụ trước khi tạo MIME.
        InternetAddress toAddress = requireOneAddress(recipient);
        InternetAddress fromAddress =
                requireOneAddress(configuredFrom);

        String safeSubject = requireText(subject, "Subject");
        String safeBody = requireText(body, "Body");

        // 2. Tạo một MimeMessage cho yêu cầu gửi này.
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom(fromAddress);
        helper.setTo(toAddress);
        helper.setSubject(safeSubject);
        helper.setText(safeBody, false);

        // 3. Xem lại metadata đã gán trước khi gửi.
        verifyPreparedMessage(message);

        // 4. Nộp thư cho SMTP transport.
        mailSender.send(message);
    }

    private static String requireText(String value, String label) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    label + " không được để trống"
            );
        }
        return value;
    }

    private static InternetAddress requireOneAddress(String value)
            throws AddressException {

        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Địa chỉ email không được để trống"
            );
        }

        InternetAddress[] parsed =
                InternetAddress.parse(value, true);

        if (parsed.length != 1) {
            throw new IllegalArgumentException(
                    "Chỉ được phép một địa chỉ email"
            );
        }

        parsed[0].validate();
        return parsed[0];
    }

    private static void verifyPreparedMessage(
            MimeMessage message) throws MessagingException {

        Address[] from = message.getFrom();
        if (from == null || from.length == 0) {
            throw new IllegalStateException(
                    "Thiếu trường From"
            );
        }

        Address[] recipients = message.getAllRecipients();
        if (recipients == null || recipients.length == 0) {
            throw new IllegalStateException(
                    "Không có người nhận"
            );
        }

        String subject = message.getSubject();
        if (subject == null || subject.isBlank()) {
            throw new IllegalStateException(
                    "Thiếu Subject"
            );
        }
    }
}
~~~

**Ý nghĩa của cách tổ chức:**

- Mã trước `createMimeMessage()` xác định **dữ liệu đầu vào** phù hợp với yêu cầu gửi thư.
- `MimeMessageHelper` chuyển những giá trị đó thành cấu trúc MIME, trong đó Subject có thể chứa tiếng Việt hoặc Unicode.
- `verifyPreparedMessage(...)` kiểm tra một số **trường đã được gán**. Hàm này không kiểm tra toàn bộ cấu trúc MIME hay kết quả SMTP.
- `mailSender.send(message)` mới thực hiện việc gửi. Nó có thể ném các ngoại lệ gửi thư của Spring; lỗi dựng/đọc MIME có thể xuất hiện dưới dạng nguyên nhân bên trong.

Ví dụ chưa có hàng đợi và cơ chế gửi lại. Trong hệ thống cần độ tin cậy cao, dịch vụ có thể ghi nhận yêu cầu gửi và giao cho một tiến trình gửi nền. Điều đó không làm thay đổi nguyên tắc kiểm tra dữ liệu ngay trước khi gửi.

### Vì sao không chỉ kiểm tra MimeMessage sau khi đã dựng?

Nếu chỉ đọc `getAllRecipients()`, `getSubject()` và `getFrom()`, ứng dụng sẽ **không biết** body rỗng hay tệp đính kèm hỏng trong mọi trường hợp. Bởi vậy ví dụ còn kiểm tra `body` và dữ liệu nghiệp vụ **trước khi gọi setter**.

Một bộ kiểm tra tốt thường có **hai lớp**:

1. **Lớp dữ liệu nghiệp vụ:** giá trị nguồn, nội dung bắt buộc, danh sách người nhận cho phép, giới hạn kích thước và loại nội dung.
2. **Lớp đối tượng email:** các trường đã gán vào `MimeMessage`, cấu trúc MIME và khả năng serialize khi có yêu cầu đặc biệt.

Hai lớp kiểm tra trả lời những câu hỏi khác nhau và cùng góp phần giảm lỗi.

## 9. Có thể kiểm tra khả năng serialize thông điệp không?

Đôi khi muốn biết liệu một đối tượng MIME vừa tạo có thể xuất ra dữ liệu MIME thô hay không, chẳng hạn khi đang phát triển chức năng gửi HTML kèm nhiều tệp.

Jakarta Mail cung cấp `writeTo(OutputStream)`. Trong **môi trường kiểm thử với dữ liệu giả**, có thể thử:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

static byte[] serializeForTest(MimeMessage message)
        throws MessagingException, IOException {

    message.saveChanges();

    ByteArrayOutputStream out =
            new ByteArrayOutputStream();

    message.writeTo(out);
    return out.toByteArray();
}
~~~

Nếu thành công, byte trả về là biểu diễn MIME của thông điệp ở thời điểm kiểm tra. Điều đó có thể giúp quan sát:

- Các trường header đã được chuẩn bị.
- `Content-Type` và boundary của những vùng `multipart`.
- Những phần `text/plain`, `text/html`, ảnh và tệp đính kèm được serialize.
- Một số lỗi khi thư viện truy cập dữ liệu nguồn.

Tuy nhiên, **đây là thao tác có chi phí và tác dụng phụ cần cân nhắc**:

- `saveChanges()` có thể cập nhật metadata.
- `writeTo(...)` có thể phải đọc toàn bộ tệp đính kèm.
- `ByteArrayOutputStream` giữ toàn bộ email trong RAM, không thích hợp cho thư lớn hoặc dùng làm kiểm tra bắt buộc cho mọi email production.
- Thông điệp raw có thể chứa thông tin cá nhân, token hoặc dữ liệu tệp. Không ghi toàn bộ byte này vào log.
- Nguồn dữ liệu thay đổi sau lần thử serialize vẫn có thể gây lỗi khi gửi thật.

Vì thế, **serialize trước gửi là công cụ chẩn đoán/kiểm thử**, không phải phép bảo đảm chuyển phát và không cần thực hiện ở mọi request. Đối với production, nên kiểm soát tài nguyên đầu vào, cấu hình SMTP và xử lý lỗi khi gửi.

## 10. Những API thường bị hiểu nhầm là trạng thái gửi

### 10.1. getSentDate()

~~~java
Date sentDate = message.getSentDate();
~~~

Ngày gửi ở header có thể được lập trình viên đặt thủ công hoặc được thư viện thêm trong quá trình chuẩn bị/gửi. Nếu `sentDate != null`, điều đó **chỉ nói thông điệp có một giá trị Date phù hợp**, chứ không xác nhận SMTP relay đã nhận thư.

Một message tạo từ hôm qua có thể mang `Date` hôm qua nhưng chưa từng được gửi. Một message gửi thành công cũng có thể cần các bước xử lý sau đó trước khi đến người nhận.

### 10.2. getMessageID()

~~~java
String messageId = message.getMessageID();
~~~

`Message-ID` là định danh của thông điệp trong hệ sinh thái email, thường có dạng tương tự:

~~~text
<some-id@example.org>
~~~

Lưu ý: chuỗi trên chỉ minh họa dạng cấu trúc. Nó không phải số thứ tự nghiệp vụ hay biên nhận từ máy chủ SMTP. Khi thư viện tạo/cập nhật message, header này có thể xuất hiện trước khi gửi, và đôi khi nhà cung cấp có thể xử lý lại metadata. **Có Message-ID không đồng nghĩa với DELIVERED**.

### 10.3. getFlags()

~~~java
jakarta.mail.Flags flags = message.getFlags();
~~~

Các cờ như `SEEN`, `ANSWERED` và `FLAGGED` chủ yếu dùng khi thao tác với thư được lưu trong một mail folder. Chúng không đại diện cho tiến trình nộp thư qua SMTP từ một ứng dụng Spring.

Không được dùng `SEEN` để kết luận “người nhận đã đọc email” trong một đối tượng `MimeMessage` mới xây dựng. Dữ liệu cờ có ý nghĩa trong ngữ cảnh mail store và hỗ trợ của server, không phải biên nhận đọc của email gửi đi.

### 10.4. getSize()

~~~java
int size = message.getSize();
~~~

Kết quả có thể là `-1` nếu kích thước không được biết. Với mail có multipart và attachment, kích thước thực sau mã hóa MIME có thể khác tổng byte của các tệp gốc. Không nên dùng `getSize()` làm tiêu chí duy nhất để xác nhận message hợp lệ hoặc phù hợp giới hạn SMTP provider.

Nếu hệ thống yêu cầu giới hạn dung lượng, hãy kết hợp giới hạn đầu vào, ước tính phần mở rộng do encoding và chính sách của nhà cung cấp; hệ thống gửi vẫn phải xử lý trường hợp server từ chối vì quá lớn.

## 11. Kiểm tra Message-ID, Date và header có nên là điều kiện bắt buộc không?

Không nên bắt buộc mọi message phải có `Message-ID` hoặc `Date` **trước khi gọi `send(...)`** nếu ứng dụng đang dùng đường gửi chuẩn của `JavaMailSender`. Những trường này có thể được thư viện thêm hoặc cập nhật trong bước chuẩn bị cuối.

Một **danh sách kiểm tra hợp đồng** hữu ích hơn thường gồm:

- Địa chỉ gửi và người nhận đã được xác định theo quy tắc nghiệp vụ.
- Subject và nội dung đã được tạo, không chứa dữ liệu nhạy cảm không cần thiết.
- Loại nội dung và các phần MIME phù hợp với thông điệp định gửi.
- Nguồn file đính kèm có thể truy cập, có giới hạn dung lượng và chính sách an toàn.
- Các giá trị tạo email từ dữ liệu ngoài đã được kiểm soát.
- Ứng dụng có cách ghi nhận lỗi, chống gửi trùng và thử lại nếu luồng nghiệp vụ yêu cầu.

Nếu cần lưu `Message-ID` để đối chiếu log, hãy quyết định lúc nào thu thập ID và xử lý tình huống header được thay đổi. Tách nó khỏi ID nghiệp vụ của yêu cầu gửi, chẳng hạn `notificationId` hoặc `outboxId`, để quản lý gửi lại nhất quán.

## 12. Kiểm tra sẵn sàng gửi khác với kiểm tra kết nối SMTP

Một `MimeMessage` hoàn chỉnh không chứng minh rằng SMTP relay đang hoạt động. Những vấn đề khác có thể xuất hiện:

| Giai đoạn | Ví dụ lỗi | Nơi phát hiện |
| --- | --- | --- |
| Chuẩn bị dữ liệu | To trống, Subject rỗng, nội dung thiếu, attachment không tồn tại | Kiểm tra đầu vào/metadata |
| Xây dựng MIME | Header hoặc nguồn dữ liệu không thể tạo/serialize đúng | API Jakarta Mail khi chuẩn bị/serialize |
| Kết nối SMTP | Sai host/port, DNS lỗi, kết nối bị chặn, timeout | Lúc kết nối tới SMTP server |
| Bảo mật SMTP | STARTTLS thất bại, chứng chỉ không tin cậy, sai cơ chế xác thực | Trong phiên SMTP |
| Nộp thư | SMTP server từ chối người gửi/người nhận hoặc thông điệp | Khi thực hiện `send(...)` |
| Chuyển phát sau nộp | Địa chỉ nhận không tồn tại, thư bị trả lại, chặn spam | Nhà cung cấp và hệ thống nhận |

Nếu dùng `JavaMailSenderImpl`, có phương thức `testConnection()` cho phép **kiểm tra thử kết nối tới server** theo cấu hình tại thời điểm gọi. Nhưng cần hiểu:

- Đây là thao tác **có kết nối mạng**, khác với xem trạng thái của message.
- Kết nối được không chứng minh một người gửi/nhận cụ thể hoặc nội dung cụ thể sẽ được SMTP chấp nhận.
- Kiểm tra thành công tại thời điểm A không bảo đảm phiên gửi tại thời điểm B sẽ thành công.
- Đừng gọi kiểm tra kết nối cho từng email chỉ để thay cho xử lý lỗi thật của `send(...)`; việc này tạo thêm kết nối và không loại bỏ được các tình huống lỗi bất ngờ.

Vì thế, đánh giá **message readiness** và đánh giá **SMTP availability** là hai trách nhiệm khác nhau.

## 13. Trạng thái do ứng dụng quản lý khi có hàng đợi hoặc outbox

Một hệ thống bán hàng có thể cần bảo đảm rằng yêu cầu gửi hóa đơn không bị mất khi máy chủ email tạm thời ngừng hoạt động. Khi đó, ứng dụng thường lưu một yêu cầu gửi vào cơ sở dữ liệu hoặc hàng đợi rồi để worker xử lý nền.

Ví dụ mô hình dữ liệu **do ứng dụng tự định nghĩa**:

~~~text
notification_id: 7fb2...
recipient: buyer@example.net
template: invoice-ready
template_data: ...
status: PENDING
attempt_count: 0
created_at: ...
~~~

Worker lấy yêu cầu, tạo `MimeMessage`, kiểm tra và thử gửi:

~~~mermaid
flowchart TD
    A["PENDING"] --> B["Dựng và kiểm tra MimeMessage"]
    B -->|"Dữ liệu không hợp lệ"| C["INVALID"]
    B -->|"Hợp lệ"| D["Gọi JavaMailSender.send"]
    D -->|"Server nhận yêu cầu"| E["SUBMITTED"]
    D -->|"Lỗi có thể thử lại"| F["RETRY_WAITING"]
    D -->|"Lỗi cấu hình/cố định"| G["FAILED"]
    F --> B
    E -->|"Có delivery event"| H["DELIVERED"]
    E -->|"Có bounce event"| I["BOUNCED"]
~~~

`PENDING`, `INVALID`, `SUBMITTED`, `RETRY_WAITING`, `FAILED`, `DELIVERED` và `BOUNCED` ở đây là **giá trị ứng dụng thiết kế**, không nằm trong `MimeMessage`.

Cách đặt tên `SUBMITTED` hoặc `ACCEPTED_BY_RELAY` có thể chính xác hơn `SENT` khi hệ thống mới chỉ biết SMTP relay đã chấp nhận yêu cầu. Để có `DELIVERED`, thường cần thông tin đáng tin cậy từ dịch vụ email hoặc hạ tầng người nhận, không thể suy ra từ kết quả kiểm tra message trước gửi.

### Thử lại và nguy cơ gửi trùng

Một tình huống khó: ứng dụng đã truyền thông điệp và SMTP relay có thể đã chấp nhận, nhưng kết nối bị ngắt trước khi client đọc được phản hồi cuối cùng. Ứng dụng không biết chắc thư đã được nhận hay chưa. Khi thử lại, thư có thể được gửi lần thứ hai.

Do vậy, trạng thái `UNKNOWN` hoặc cơ chế đối soát có thể cần thiết trong những hệ thống quan trọng. Khóa nghiệp vụ ổn định, giới hạn thử lại và quản lý giao dịch/outbox giúp giảm lỗi vận hành, nhưng **bản thân SMTP không cung cấp cam kết exactly-once cho ứng dụng chỉ nhờ gọi `send(...)`**.

## 14. Lỗi và ngoại lệ khi kiểm tra trước gửi

Nên phân biệt lỗi dữ liệu với lỗi kỹ thuật:

**Lỗi dữ liệu:**

~~~java
throw new IllegalArgumentException(
        "Subject không được để trống"
);
~~~

Hoặc lỗi trạng thái nội bộ:

~~~java
throw new IllegalStateException(
        "MimeMessage chưa có người nhận"
);
~~~

Đây là những lỗi do ứng dụng chủ động tạo khi không đáp ứng hợp đồng đã định.

**Lỗi API MIME:** Các phương thức của Jakarta Mail có thể ném `MessagingException` hoặc `AddressException`, chẳng hạn trong lúc dựng header, phân tích địa chỉ hoặc thao tác dữ liệu MIME. Chúng thường cần được quy về kết quả “không thể chuẩn bị thông điệp” phù hợp với quy trình ứng dụng.

**Lỗi gửi thư:** `JavaMailSender.send(...)` sử dụng hệ thống ngoại lệ của Spring Mail như `MailException`, trong đó có `MailAuthenticationException` và `MailSendException` tùy tình huống. Những lỗi này xảy ra trong quy trình gửi và có thể bọc ngoại lệ từ Jakarta Mail hoặc hạ tầng mạng.

Không nên gom toàn bộ ngoại lệ thành một kết quả “message chưa sẵn sàng”, vì **địa chỉ thiếu** khác với **SMTP server quá tải**. Phân loại chính xác sẽ giúp hệ thống quyết định khi nào cần sửa dữ liệu, sửa cấu hình hoặc thử lại.

### Tránh log tràn dữ liệu nhạy cảm

Khi báo lỗi trước gửi, có thể ghi nhận ID yêu cầu, loại thông điệp, mã lỗi và bước xảy ra lỗi. Không nên ghi toàn bộ `MimeMessage` hoặc biểu diễn raw MIME vào log production: phần body, header và tệp đính kèm có thể chứa dữ liệu cá nhân, token và tài liệu của người dùng.

## 15. Một số tình huống dễ hiểu nhầm

### Tình huống A — Có Message-ID nghĩa là đã gửi?

Không. Một `MimeMessage` chưa gửi vẫn có thể có `Message-ID` sau khi `saveChanges()`. Header này mô tả thông điệp, không phải biên nhận SMTP hay trạng thái chuyển phát.

### Tình huống B — getSentDate() có giá trị nghĩa là email đã tới?

Không. Đây là thông tin ngày giờ trên header. Nó có thể được đặt từ trước khi gửi. Trạng thái chuyển phát cần bằng chứng khác.

### Tình huống C — getAllRecipients() có phần tử nghĩa là địa chỉ tồn tại?

Không. API chỉ cung cấp địa chỉ đã được gắn vào message. `InternetAddress.validate()` cũng chủ yếu kiểm tra **cú pháp**, không kiểm chứng sự tồn tại của hộp thư từ xa.

### Tình huống D — isMimeType("text/html") trả về false nghĩa là email không có HTML?

Không nhất thiết. Thông điệp có thể là `multipart/mixed` hoặc `multipart/related` ở cấp ngoài và chứa một part `text/html` bên trong.

### Tình huống E — saveChanges() hoàn tất nghĩa là SMTP không còn lỗi?

Không. `saveChanges()` chỉ chuẩn bị thông điệp MIME, không kết nối và không xác thực tới SMTP relay.

### Tình huống F — Chỉ cần một hàm validatePreparedMessage() là đủ?

Không với những thông điệp phức tạp. Hàm kiểm tra metadata có thể bỏ sót dữ liệu template, kích thước và khả năng đọc tệp, ràng buộc người nhận hoặc lỗi mạng sau đó. Hãy kiểm tra dữ liệu nguồn và điều kiện nghiệp vụ bên cạnh trạng thái các trường trên message.

### Tình huống G — Một message được tái sử dụng nhiều lần có tiện hơn không?

Thông thường, nên tạo **`MimeMessage` mới cho từng yêu cầu gửi** để hạn chế rò rỉ người nhận, Subject, nội dung hoặc attachment giữa những email khác nhau. `MimeMessage` có trạng thái thay đổi được (mutable); việc chia sẻ cùng một đối tượng giữa các luồng gửi độc lập dễ dẫn đến lỗi và khó xác định kết quả. Nếu cần gửi tới nhiều người, hãy chọn chiến lược tạo message và danh sách người nhận phù hợp theo nghiệp vụ.

## 16. Bài tập thực hành

**Bài 1.** Một `MimeMessage` có `From`, `Subject` và body HTML, nhưng `getAllRecipients()` trả về `null`. Có nên gọi `send(...)` không?

**Không nên** nếu hợp đồng ứng dụng yêu cầu ít nhất một người nhận. Cần điền địa chỉ To/Cc/Bcc phù hợp trước khi gửi.

**Bài 2.** Sau khi gọi `saveChanges()`, `getMessageID()` có giá trị. Có thể cập nhật trạng thái DB sang `DELIVERED` chưa?

**Chưa.** Message-ID chỉ là định danh header. Cần thực hiện gửi và có bằng chứng chuyển phát thích hợp.

**Bài 3.** `MimeMessage` có `Content-Type: multipart/mixed`. Có thể kết luận không có HTML không?

**Không.** Một part con có thể là `text/html`, hoặc có nhiều lớp multipart lồng nhau.

**Bài 4.** Địa chỉ `someone@example.org` qua kiểm tra cú pháp. Điều đó bảo đảm email sẽ không bounce?

**Không.** Cú pháp hợp lệ không chứng minh hộp thư tồn tại, miền nhận thư đã cấu hình hoặc người nhận chấp nhận email.

**Bài 5.** Một tệp đính kèm tồn tại khi kiểm tra nhưng bị xóa trước lúc gửi. Lỗi xảy ra ở đâu?

Có thể xảy ra khi Jakarta Mail đọc nội dung để serialize và gửi. Kiểm tra `exists()` trước đó chỉ là quan sát tại một thời điểm. Cần quản lý vòng đời tài nguyên và xử lý lỗi đọc tệp.

**Bài 6.** `mailSender.send(message)` trả về bình thường. Có thể kết luận người dùng đã đọc email?

**Không.** Đó là kết quả bước gửi/nộp thư đến hạ tầng SMTP. Trạng thái hộp thư và việc người dùng mở thư là những thông tin khác.

## 17. Mô hình ghi nhớ

**Kiểm tra trạng thái message trước khi gửi** là kiểm tra **dữ liệu và cấu trúc thông điệp ở phía ứng dụng**: địa chỉ, Subject, body, MIME và các tệp đính kèm theo hợp đồng nghiệp vụ. Spring Framework Mail cho phép ta truy cập một số trường qua `MimeMessage` và `MimeMessageHelper`; Jakarta Mail còn có `saveChanges()` khi cần chuẩn bị header hoặc serialize thông điệp.

Nên nhớ ba ranh giới:

1. **Message đã sẵn sàng**: ứng dụng đã kiểm tra các điều kiện cần thiết theo mục đích gửi email.
2. **SMTP đã nhận yêu cầu gửi**: kết quả sau khi thực hiện `JavaMailSender.send(...)` và xử lý các lỗi có thể xảy ra.
3. **Email đã được chuyển phát/đọc**: cần tín hiệu hoặc bằng chứng riêng từ hạ tầng chuyển phát và người nhận.

Không có một phương thức `MimeMessage.isSent()` đủ sức thay thế ba tầng này. Việc xây dựng bước kiểm tra trước gửi rõ ràng giúp phát hiện lỗi sớm và làm luồng gửi dễ theo dõi, trong khi trạng thái gửi và chuyển phát phải được quản lý ở tầng ứng dụng và hạ tầng email.

