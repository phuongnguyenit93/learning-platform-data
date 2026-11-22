# Phân biệt `setTo` với `addTo` trong Spring Framework Mail

Khi gửi email từ ứng dụng Spring, một thông điệp có thể cần đến một người nhận, nhiều người nhận cố định hoặc một danh sách được bổ sung dần theo nghiệp vụ. Hai tên phương thức `setTo` và `addTo` dễ khiến lập trình viên nghĩ rằng chúng luôn xuất hiện trên cùng một lớp và khác nhau rất ít. Thực tế có **hai điều cần phân biệt**:

1. **`SimpleMailMessage` có `setTo(...)` nhưng không có `addTo(...)`.** Đây là đối tượng của Spring dành cho thư văn bản đơn giản; muốn gửi cho nhiều người thì truyền tất cả địa chỉ vào `setTo(...)`.
2. **`MimeMessageHelper` có cả `setTo(...)` và `addTo(...)`.** `setTo(...)` **thiết lập/thay thế** danh sách người nhận loại `To`, còn `addTo(...)` **bổ sung** một người nhận `To` vào danh sách đang có.

Nếu gọi `setTo(...)` sau những lần `addTo(...)`, các địa chỉ `To` đã thêm trước đó có thể bị thay thế. Ngược lại, nếu dùng `addTo(...)` nhiều lần, danh sách `To` được tích lũy. Hiểu sự khác biệt này giúp tránh gửi thiếu người, gửi trùng hoặc đưa nhầm nhiều địa chỉ vào một email.

Bài học đặt hai API trong ngữ cảnh **Simple mail** của Spring Framework Mail, bao gồm cả cách gửi plain-text bằng `SimpleMailMessage` và cách tạo một MIME message chỉ chứa văn bản bằng `JavaMailSender`.

## 1. Trước hết: `To` là loại người nhận nào?

Một email thường có ba nhóm người nhận:

| Nhóm | Header thường thấy | Ý nghĩa đối với người nhận |
| --- | --- | --- |
| **To** | `To:` | Người nhận chính, thường được hiển thị trong danh sách người nhận |
| **Cc** | `Cc:` | Người được gửi bản sao, thường cũng được hiển thị |
| **Bcc** | `Bcc:` | Người nhận bản sao kín; địa chỉ Bcc thường không được tiết lộ trong bản thư gửi cho những người khác |

Ví dụ:

```text
From: notifications@example.org
To: alice@example.net, bob@example.net
Cc: manager@example.org
Subject: Thông báo bảo trì
```

Ở đây, Alice và Bob đều thuộc nhóm **To**. `setTo` và `addTo` không tự chuyển người nhận sang Cc hay Bcc. Các nhóm đó có những API riêng như `setCc`, `addCc`, `setBcc` và `addBcc` khi sử dụng `MimeMessageHelper`.

**Lưu ý về SMTP:** header `To` nằm trong nội dung email, còn SMTP sử dụng các địa chỉ envelope `RCPT TO` để chuyển thư. Spring/Jakarta Mail thường xây dựng danh sách người nhận gửi từ các nhóm To/Cc/Bcc của message. Không nên tự nối chuỗi header `To: ...` để thay thế API người nhận.

## 2. Hai lớp khác nhau: `SimpleMailMessage` và `MimeMessageHelper`

Spring Framework Mail có nhiều cách tạo thông điệp. Đối với bài này, cần nhận diện đúng kiểu đối tượng trước khi chọn phương thức.

### 2.1. `SimpleMailMessage` — thư văn bản đơn giản

`SimpleMailMessage` thuộc package:

```java
import org.springframework.mail.SimpleMailMessage;
```

Lớp này giữ các trường phổ biến: `from`, `replyTo`, `to`, `cc`, `bcc`, `sentDate`, `subject` và `text`. `To` được biểu diễn như danh sách địa chỉ chuỗi.

Các cách gọi thông dụng:

```java
SimpleMailMessage mail = new SimpleMailMessage();

mail.setTo("alice@example.net");
mail.setTo("alice@example.net", "bob@example.net");

String[] currentTo = mail.getTo();
```

**Không có phương thức `mail.addTo(...)` trên `SimpleMailMessage`.** Nếu viết:

```java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setTo("alice@example.net");
mail.addTo("bob@example.net");  // Không biên dịch: SimpleMailMessage không có addTo
```

trình biên dịch sẽ báo không tìm thấy phương thức phù hợp. Lỗi này là do **dùng nhầm API**, không phải do Spring chưa cấu hình SMTP.

### 2.2. `MimeMessageHelper` — công cụ tạo `MimeMessage`

`MimeMessageHelper` thuộc package:

```java
import org.springframework.mail.javamail.MimeMessageHelper;
```

Helper thao tác trên một `jakarta.mail.internet.MimeMessage`, hỗ trợ text thuần, HTML, multipart, attachment và nhiều phương thức tiện ích cho địa chỉ:

```java
helper.setTo("alice@example.net");
helper.addTo("bob@example.net");
```

Ở đây, cả hai lời gọi đều hợp lệ:

- `setTo("alice@example.net")`: đặt danh sách người nhận `To` thành Alice.
- `addTo("bob@example.net")`: bổ sung Bob vào danh sách `To` hiện có.

**Không cần có HTML hoặc file đính kèm mới được dùng `MimeMessageHelper`.** Một MIME message vẫn có thể chỉ chứa plain-text. Khi muốn thêm người nhận từng bước, helper là lựa chọn thuận tiện.

### 2.3. Bảng đối chiếu API

| Khả năng | `SimpleMailMessage` | `MimeMessageHelper` |
| --- | --- | --- |
| Gán một địa chỉ `To` | `setTo(String)` | `setTo(String)` |
| Gán nhiều địa chỉ `To` cùng lúc | `setTo(String...)` | `setTo(String...)` |
| Thêm từng địa chỉ `To` bằng `addTo` | **Không hỗ trợ** | **Hỗ trợ** |
| Đọc danh sách `To` | `getTo()` | Có thể đọc qua `MimeMessage` được helper quản lý |
| Tạo plain-text | `setText(String)` | `setText(String, false)` |
| Tạo HTML | Không phải mục đích của lớp | `setText(String, true)` |
| Tệp đính kèm và multipart | Không hỗ trợ trực tiếp | `addAttachment(...)`, các constructor multipart |
| Gửi qua `JavaMailSender` | `mailSender.send(simpleMail)` | `mailSender.send(mimeMessage)` |

Sự khác nhau nằm ở **kiểu đối tượng**, không phải ở loại cổng SMTP hoặc danh tính đăng nhập.

## 3. `setTo` có nghĩa là “thiết lập danh sách”

Với cả `SimpleMailMessage` và `MimeMessageHelper`, `setTo` đặt tập hợp các địa chỉ `To` theo giá trị truyền vào. Mỗi lần gọi lại `setTo` cho cùng message, danh sách `To` trước đó **bị thay thế** bằng danh sách mới.

Ví dụ trên `SimpleMailMessage`:

```java
SimpleMailMessage mail = new SimpleMailMessage();

mail.setTo("alice@example.net");
mail.setTo("bob@example.net");

mail.setFrom("notifications@example.org");
mail.setSubject("Thông báo");
mail.setText("Nội dung văn bản thuần.");
```

Sau hai lần `setTo`, danh sách `To` cuối cùng chỉ có:

```text
bob@example.net
```

**Alice không còn là người nhận `To` của message này.** Điều đó khác với cách hiểu “mỗi lần `setTo` là thêm một người”.

### 3.1. Muốn có nhiều người nhận, hãy truyền nhiều địa chỉ trong một lần

```java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setTo(
        "alice@example.net",
        "bob@example.net",
        "carol@example.net"
);
```

Kết quả logic:

```text
To:
  alice@example.net
  bob@example.net
  carol@example.net
```

`setTo(String...)` nhận một **varargs**. Vì vậy, các cách sau đều thể hiện danh sách `To`:

```java
mail.setTo("alice@example.net");

mail.setTo("alice@example.net", "bob@example.net");

String[] recipients = {
        "alice@example.net",
        "bob@example.net"
};
mail.setTo(recipients);
```

Trong Java, `String...` cho phép truyền nhiều đối số `String` hoặc một mảng `String[]`. Không cần tự ghép một chuỗi gồm nhiều email cách nhau bằng dấu phẩy chỉ để sử dụng overload mảng.

### 3.2. `setTo` không thay thế `Cc` hoặc `Bcc`

Ví dụ:

```java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setTo("alice@example.net");
mail.setCc("manager@example.org");
mail.setBcc("audit@example.org");

mail.setTo("bob@example.net");
```

Danh sách sau cùng:

```text
To:  bob@example.net
Cc:  manager@example.org
Bcc: audit@example.org
```

`setTo` chỉ cập nhật **nhóm To**, không tự xóa Cc/Bcc. Tương tự, `setCc` đặt danh sách Cc và `setBcc` đặt danh sách Bcc.

## 4. `addTo` có nghĩa là “thêm vào danh sách hiện có”

`MimeMessageHelper.addTo(...)` bổ sung một địa chỉ `To` vào những địa chỉ đang có trên `MimeMessage`. Đây là thao tác **tích lũy**, hữu ích khi mỗi bước nghiệp vụ xác định thêm một người nhận.

Ví dụ:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

helper.setFrom("notifications@example.org");
helper.setTo("alice@example.net");
helper.addTo("bob@example.net");
helper.addTo("carol@example.net");
helper.setSubject("Thông báo");
helper.setText("Nội dung văn bản thuần.", false);

mailSender.send(message);
```

Danh sách `To` lúc gửi gồm Alice, Bob và Carol.

### 4.1. Có cần gọi `setTo` trước `addTo` không?

Không bắt buộc nếu message chưa có `To`:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

helper.addTo("alice@example.net");
helper.addTo("bob@example.net");
```

Kết quả logic vẫn là hai người nhận `To`. Tuy nhiên, khi có một danh sách đầu vào rõ ràng, gọi `setTo(recipients)` một lần thường dễ hiểu hơn.

### 4.2. `addTo` sau `setTo`

```java
helper.setTo(
        "alice@example.net",
        "bob@example.net"
);
helper.addTo("carol@example.net");
```

Kết quả:

```text
To: alice@example.net, bob@example.net, carol@example.net
```

### 4.3. `setTo` sau `addTo`

```java
helper.addTo("alice@example.net");
helper.addTo("bob@example.net");
helper.setTo("carol@example.net");
```

Kết quả:

```text
To: carol@example.net
```

Hai địa chỉ đã thêm trước đó **không còn trong nhóm To** vì lời gọi `setTo` mới thiết lập lại danh sách.

**Thứ tự gọi ảnh hưởng trực tiếp đến danh sách gửi cuối cùng.** Đây là khác biệt quan trọng nhất khi hai phương thức cùng được dùng.

## 5. Bảng trạng thái: gọi nhiều lần thì chuyện gì xảy ra?

Giả sử sử dụng một đối tượng `MimeMessageHelper` mới, chưa có người nhận:

| Thứ tự | Phương thức gọi | Danh sách `To` sau thao tác |
| --- | --- | --- |
| 1 | `setTo("alice@example.net")` | Alice |
| 2 | `addTo("bob@example.net")` | Alice, Bob |
| 3 | `addTo("carol@example.net")` | Alice, Bob, Carol |
| 4 | `setTo("david@example.net")` | David |
| 5 | `addTo("erin@example.net")` | David, Erin |

Có thể hình dung:

```text
To = []
 |
 | setTo(Alice)
 v
To = [Alice]
 |
 | addTo(Bob)
 v
To = [Alice, Bob]
 |
 | addTo(Carol)
 v
To = [Alice, Bob, Carol]
 |
 | setTo(David)
 v
To = [David]
 |
 | addTo(Erin)
 v
To = [David, Erin]
```

Tại thời điểm `send(...)` được gọi, thư viện sử dụng trạng thái message **sau những thao tác tạo nội dung và người nhận đã hoàn thành**. Do đó, một lần `setTo` vô tình ở cuối quá trình chuẩn bị có thể làm mất các địa chỉ đã được thêm bằng `addTo` trước đó.

## 6. API bên dưới: Jakarta Mail đặt và bổ sung người nhận

`MimeMessageHelper` là lớp tiện ích của Spring xây dựng trên `MimeMessage` của Jakarta Mail. Ở tầng Jakarta Mail cũng có sự phân biệt tương đương giữa **set** và **add** cho người nhận:

```java
import jakarta.mail.Message;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

MimeMessage message = mailSender.createMimeMessage();

message.setRecipients(
        Message.RecipientType.TO,
        InternetAddress.parse("alice@example.net,bob@example.net")
);

message.addRecipient(
        Message.RecipientType.TO,
        new InternetAddress("carol@example.net")
);
```

Ý tưởng chung:

- `setRecipients(RecipientType.TO, ...)` đặt danh sách cho một nhóm recipient.
- `addRecipient(RecipientType.TO, ...)` thêm một địa chỉ cho nhóm đó.
- `addRecipients(RecipientType.TO, ...)` thêm một nhóm địa chỉ.
- `Message.RecipientType.TO` khác `Message.RecipientType.CC` và `Message.RecipientType.BCC`.

Với code ứng dụng Spring thông thường, `MimeMessageHelper.setTo` và `addTo` giúp thao tác dễ đọc hơn và hỗ trợ các overload dùng chuỗi/tên hiển thị, đồng thời sử dụng cơ chế xử lý địa chỉ của thư viện.

**Không cần can thiệp trực tiếp vào `MimeMessage.setRecipients` chỉ để thêm một người nhận thông thường** nếu helper đã đáp ứng yêu cầu. Việc trộn cả helper và code Jakarta Mail mức thấp trong cùng một đường gửi có thể khiến trạng thái cuối khó theo dõi.

## 7. Ví dụ hoàn chỉnh: gửi Simple mail bằng `SimpleMailMessage`

Trường hợp phổ biến là gửi thông báo text thuần tới danh sách cố định hoặc được tính xong trước khi tạo email.

### 7.1. Cấu hình gửi qua SMTP trong Spring Boot

Với Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

Ví dụ `application.yml` dùng SMTP submission trên cổng 587:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    from: ${MAIL_FROM_ADDRESS}
```

Đây là ví dụ cho máy chủ hỗ trợ SMTP AUTH và STARTTLS trên cổng 587. Cổng, TLS và phương thức xác thực phải theo nhà cung cấp thật. Không đặt mật khẩu thật trong mã nguồn; các giá trị biến môi trường do hệ thống triển khai cung cấp.

### 7.2. Service với một lần `setTo`

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class SimpleNotificationService {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public SimpleNotificationService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress
    ) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendAnnouncement(List<String> recipients) {
        if (recipients == null || recipients.isEmpty()) {
            throw new IllegalArgumentException("Recipients are required");
        }

        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom(fromAddress);
        mail.setTo(recipients.toArray(new String[0]));
        mail.setSubject("Thông báo hệ thống");
        mail.setText("Hệ thống sẽ bảo trì vào cuối tuần.");

        mailSender.send(mail);
    }
}
```

Điểm quan trọng nằm ở:

```java
mail.setTo(recipients.toArray(new String[0]));
```

Ứng dụng gom danh sách người nhận trước, chuyển sang `String[]` và gọi `setTo` **một lần**. Không cần `addTo`. Với hệ thống thực tế, `recipients` nên là các địa chỉ đã được kiểm tra theo quy tắc nghiệp vụ; chỉ kiểm tra danh sách không rỗng chưa đủ để bảo đảm mọi địa chỉ đều hợp lệ hoặc được phép gửi.

### 7.3. Nếu danh sách được bổ sung từ nhiều nguồn

Giả sử cần gửi cho người tạo yêu cầu và những người phụ trách:

```java
import java.util.ArrayList;
import java.util.List;

List<String> recipients = new ArrayList<>();
recipients.add("requester@example.net");
recipients.add("owner@example.net");

if (notifyBackupOwner) {
    recipients.add("backup@example.net");
}

SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("notifications@example.org");
mail.setTo(recipients.toArray(new String[0]));
mail.setSubject("Yêu cầu đã cập nhật");
mail.setText("Có một thay đổi mới cần bạn theo dõi.");

mailSender.send(mail);
```

Trong đoạn minh họa này, biến `notifyBackupOwner` đã được nghiệp vụ xác định. Mấu chốt là **tích lũy danh sách trong collection**, rồi gọi `setTo` một lần sau cùng.

### 7.4. Có nên “thêm” người nhận bằng cách đọc `getTo` rồi gọi lại `setTo`?

Kỹ thuật này có thể thực hiện:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

SimpleMailMessage mail = new SimpleMailMessage();
mail.setTo("alice@example.net");

List<String> current = new ArrayList<>();
if (mail.getTo() != null) {
    current.addAll(Arrays.asList(mail.getTo()));
}
current.add("bob@example.net");

mail.setTo(current.toArray(new String[0]));
```

Nhưng đây là thao tác **tự dựng lại cả danh sách**, không phải một phương thức `addTo` chính thức của `SimpleMailMessage`. Nếu nhiều tầng code cùng đọc/sửa message theo thứ tự khó kiểm soát, cách này dễ bị ghi đè. Trong thiết kế thông thường, nên giữ một collection danh sách người nhận ở tầng nghiệp vụ và gọi `setTo` khi đã có quyết định cuối cùng.

## 8. Ví dụ hoàn chỉnh: plain-text với `MimeMessageHelper.addTo`

Khi luồng nghiệp vụ cần thêm người nhận theo từng bước hoặc muốn tận dụng các khả năng của MIME, có thể dùng `MimeMessageHelper` dù body chỉ là text:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MimeNotificationService {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public MimeNotificationService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress
    ) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendUpdate(
            String requester,
            String owner,
            String backupOwner
    ) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                "UTF-8"
        );

        helper.setFrom(fromAddress);
        helper.setTo(requester);
        helper.addTo(owner);

        if (backupOwner != null && !backupOwner.isBlank()) {
            helper.addTo(backupOwner);
        }

        helper.setSubject("Cập nhật yêu cầu");
        helper.setText(
                "Có một cập nhật mới dành cho nhóm xử lý yêu cầu.",
                false
        );

        mailSender.send(message);
    }
}
```

Ở đây:

- `helper.setTo(requester)` xác định người nhận chính ban đầu.
- `helper.addTo(owner)` bổ sung người phụ trách.
- `helper.addTo(backupOwner)` chỉ thực hiện khi có người phụ trách dự phòng.
- `setText(..., false)` tạo nội dung plain-text.
- `JavaMailSender.send(message)` gửi thông điệp có danh sách To cuối cùng.

Với ứng dụng thật, cần có chính sách xử lý `requester`/`owner`/`backupOwner` bị trùng hoặc không hợp lệ. `addTo` chỉ giúp **bổ sung địa chỉ**, không đồng nghĩa tự lọc trùng hay kiểm tra người nhận có quyền xem nội dung email.

### 8.1. Dùng `addTo` để thêm tên hiển thị

`MimeMessageHelper` có các overload hỗ trợ địa chỉ và **personal name**:

```java
helper.setTo("alice@example.net");
helper.addTo("bob@example.net", "Bộ phận hỗ trợ");
```

Trong trường hợp này, tên hiển thị có thể được mã hóa đúng charset bởi thư viện và xuất hiện trên mail client ở dạng gần như:

```text
To: alice@example.net, Bộ phận hỗ trợ <bob@example.net>
```

Đây là phần **trình bày danh tính người nhận**, không làm thay đổi địa chỉ định tuyến `bob@example.net`. Các overload nhận `jakarta.mail.internet.InternetAddress` cũng có thể được dùng khi cần kiểm soát đối tượng địa chỉ ở mức thấp hơn.

## 9. Chọn `setTo` hay `addTo` trong những tình huống nào?

| Tình huống | API khuyến nghị | Vì sao |
| --- | --- | --- |
| Gửi SimpleMailMessage tới một người | `mail.setTo(address)` | API đơn giản, đủ nhu cầu |
| Gửi SimpleMailMessage tới nhiều người đã biết | `mail.setTo(addresses)` | Không có `addTo`; đặt toàn bộ danh sách |
| Bổ sung người nhận từ nhiều nguồn trước khi tạo email | Gom `List<String>` rồi `setTo(list.toArray(...))` | Một nơi quyết định danh sách cuối cùng |
| Tạo MIME message với danh sách To đã biết | `helper.setTo(addresses)` | Đặt rõ tập người nhận ban đầu |
| Tạo MIME message, sau đó cần thêm một người | `helper.addTo(address)` | Không ghi đè những người đã có |
| Cần thay thế hoàn toàn danh sách To của MIME message | `helper.setTo(newAddresses)` | Chủ động thay dữ liệu cũ |
| Cần thêm Cc/Bcc, không phải To | `addCc`/`addBcc` hoặc `setCc`/`setBcc` | Giữ đúng ý nghĩa nhóm người nhận |
| Cần gửi riêng cho từng người | Tạo **message riêng** cho mỗi người | Mỗi thư có recipient, nội dung và quyền truy cập riêng |

**Một quy tắc thiết kế dễ nhớ:** khi bạn biết **danh sách cuối cùng**, dùng `setTo`; khi bạn cần **nối thêm** vào danh sách `To` đang có trên một `MimeMessageHelper`, dùng `addTo`.

## 10. Cẩn thận với thứ tự gọi trong các tầng code

Lỗi dễ xảy ra khi message được xây dựng qua nhiều service hoặc helper function.

Ví dụ:

```java
void fillCommonRecipients(MimeMessageHelper helper)
        throws MessagingException {
    helper.setTo("primary@example.net");
    helper.addTo("observer@example.net");
}

void fillSpecificRecipient(MimeMessageHelper helper)
        throws MessagingException {
    helper.setTo("case-owner@example.net");
}
```

Nếu chương trình gọi:

```java
fillCommonRecipients(helper);
fillSpecificRecipient(helper);
```

`case-owner@example.net` sẽ thay thế nhóm To đã được thiết lập ở bước đầu. Ý định “thêm người phụ trách case” đã không được thực hiện.

Nếu `fillSpecificRecipient` chỉ cần bổ sung người nhận, nó phải dùng:

```java
void addSpecificRecipient(MimeMessageHelper helper)
        throws MessagingException {
    helper.addTo("case-owner@example.net");
}
```

Một thiết kế khác rõ ràng hơn là **tập hợp mọi người nhận trước**, chuẩn hóa theo chính sách nghiệp vụ và gọi `setTo` đúng một lần ở lớp dựng email.

### Vì sao nhiều tầng cùng sửa recipient dễ gây lỗi?

Vì thứ tự thao tác trở thành một phần của ngữ nghĩa:

```text
commonRecipients()   -> setTo(Alice), addTo(Bob)
caseRecipients()     -> setTo(Carol)
auditRecipients()    -> addTo(David)

Danh sách cuối cùng: Carol, David
```

Nếu nhà phát triển chỉ đọc nội dung của `commonRecipients()` rồi mặc định Alice và Bob vẫn có mặt, email sẽ bị gửi thiếu. Nên quy định rõ lớp nào **sở hữu danh sách To cuối cùng** và tránh việc nhiều decorator cùng tự ý `setTo`.

## 11. `addTo` có tự chống trùng địa chỉ không?

Không nên giả định như vậy. `addTo` là thao tác **thêm recipient**, không phải API quản lý tập hợp duy nhất theo quy tắc email. Nếu thêm cùng một địa chỉ nhiều lần:

```java
helper.setTo("alice@example.net");
helper.addTo("alice@example.net");
```

message có thể mang các mục To trùng nhau. Cách server hoặc transport xử lý danh sách trùng có thể thay đổi theo triển khai; không nên dựa vào nó để chống gửi lặp.

Nếu nghiệp vụ yêu cầu mỗi địa chỉ chỉ xuất hiện một lần trong cùng danh sách, có thể **lọc trùng trước khi tạo message**:

```java
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.Set;

Set<String> recipients = new LinkedHashSet<>(
        Arrays.asList(
                "alice@example.net",
                "bob@example.net",
                "alice@example.net"
        )
);

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");
helper.setTo(recipients.toArray(new String[0]));
```

`LinkedHashSet` giữ thứ tự thêm và loại bỏ những chuỗi bằng nhau theo quy tắc `String.equals`. Nó **không phải** bộ chuẩn hóa địa chỉ email hoàn chỉnh: những chuỗi khác nhau ở chữ hoa/chữ thường, tên hiển thị hoặc cú pháp địa chỉ có thể cần quy tắc bổ sung.

Nếu ứng dụng đưa cùng một địa chỉ vào To, Cc và Bcc, việc khử trùng trong riêng To không tự xử lý sự chồng lấn giữa ba nhóm. Nên xác định rõ chính sách ưu tiên recipient khi tổng hợp các nhóm.

### Gửi một message đến nhiều người khác gửi nhiều message riêng

```text
Một message:
  To: Alice, Bob, Carol
  Subject: Common update

Ba message độc lập:
  Message 1 -> To: Alice
  Message 2 -> To: Bob
  Message 3 -> To: Carol
```

Hai cách có khác biệt:

- Một message nhiều `To` thường để lộ danh sách `To` cho những người được nhận thư.
- Các thông điệp riêng cho phép tùy biến tên, liên kết hoặc trạng thái gửi theo từng người.
- Việc retry/ghi nhận lỗi giao thư theo từng người nhận có thể khác giữa hai mô hình.

Đừng dùng `addTo` với hàng trăm người nhận nếu nghiệp vụ cần **từng email riêng tư, cá nhân hóa**. Khi đó nên tạo một message riêng cho từng người hoặc sử dụng cơ chế bulk gửi riêng có chính sách phù hợp.

## 12. Dùng `Cc` và `Bcc` khi cần đúng mục đích

Khi muốn một người “được biết thêm” thay vì trở thành người nhận chính, sử dụng Cc:

```java
helper.setTo("customer@example.net");
helper.addCc("account-manager@example.org");
```

Khi cần gửi bản sao kín, sử dụng Bcc:

```java
helper.setTo("customer@example.net");
helper.addBcc("audit@example.org");
```

Với `SimpleMailMessage`, tương đương việc **đặt danh sách**:

```java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setTo("customer@example.net");
mail.setCc("account-manager@example.org");
mail.setBcc("audit@example.org");
```

Trong mail gửi cho khách hàng, `audit@example.org` không nên xuất hiện trong các bản header `To`/`Cc` được phân phối cho những người nhận khác; đây là mục đích của Bcc. Tuy nhiên, riêng tính năng Bcc không phải một cơ chế bảo vệ dữ liệu hoàn chỉnh và cũng không thay thế kiểm soát người nhận tại tầng nghiệp vụ.

**Không gọi `addTo` chỉ vì muốn “thêm một người theo dõi kín”**: việc thêm vào To có thể làm địa chỉ của họ hiển thị. Hãy chọn To/Cc/Bcc theo đúng mục đích thông tin và quyền riêng tư.

## 13. Kiểm tra địa chỉ và quyền nhận trước khi gửi

Cả `setTo` và `addTo` đều nhận các địa chỉ để tạo message. Chúng **không phải** API xác nhận rằng mailbox thực sự tồn tại hoặc người đó có quyền nhận thông tin nghiệp vụ.

Những tình huống cần quản lý:

- **Địa chỉ sai cú pháp:** `alice@@example.net` có thể gây lỗi khi phân tích/chuẩn bị message.
- **Địa chỉ trống hoặc `null`:** cần xử lý từ tầng nhập liệu và chính sách bắt buộc recipient.
- **Tài khoản đã hủy nhận thông báo:** cần được loại khỏi tập recipient nếu nghiệp vụ yêu cầu.
- **Người nhận không có quyền xem dữ liệu:** phải được kiểm tra trước khi đặt vào To/Cc/Bcc.
- **Danh sách quá lớn:** SMTP provider có thể hạn chế số `RCPT TO`, kích thước thư hoặc tốc độ gửi.
- **Trùng địa chỉ:** cần xử lý theo chính sách ứng dụng trước khi tạo message.
- **Địa chỉ do người dùng cung cấp:** tránh đưa dữ liệu không tin cậy vào raw header; dùng API địa chỉ của Spring/Jakarta Mail.

Với `MimeMessageHelper`, lỗi phân tích địa chỉ có thể biểu hiện dưới dạng `MessagingException` hoặc exception cụ thể của Jakarta Mail tùy cách gọi. Với `SimpleMailMessage`, một số vấn đề chỉ được phát hiện khi sender chuyển message sang định dạng gửi. Ngoại lệ có thể xảy ra **trước khi SMTP chấp nhận thư**, nhưng việc không có ngoại lệ cũng chưa chứng minh người nhận đã mở email.

### Có cần tự ghép chuỗi các địa chỉ cách nhau bằng dấu phẩy?

Không khi bạn đã có danh sách địa chỉ `String[]` hoặc `List<String>`. Ví dụ:

```java
String[] addresses = {
        "alice@example.net",
        "bob@example.net"
};

helper.setTo(addresses);
```

Đây là cách thể hiện rõ **hai địa chỉ riêng biệt**. Với địa chỉ có tên hiển thị hoặc cú pháp phức tạp, việc tự nối chuỗi rồi tự tách theo dấu phẩy dễ gây lỗi. Sử dụng đúng overload hoặc `InternetAddress` thích hợp.

## 14. Những lỗi hiểu nhầm thường gặp

| Hiện tượng / suy nghĩ | Vấn đề | Cách xử lý |
| --- | --- | --- |
| “`SimpleMailMessage` có `addTo`” | Lớp này chỉ có `setTo` cho nhóm To | Gom danh sách rồi gọi `setTo` |
| “Gọi `setTo` hai lần là có hai người nhận” | Lần sau ghi đè danh sách To | Gọi một lần với nhiều địa chỉ hoặc dùng `addTo` trên helper |
| “`addTo` và `setTo` dùng thay nhau được” | Một bên thêm, một bên thay | Chọn theo trạng thái recipient muốn có |
| “`addTo` tự loại trùng” | Không phải chức năng quản lý danh sách duy nhất | Lọc/chuẩn hóa theo quy tắc nghiệp vụ |
| “`addTo` cũng thêm Cc” | `addTo` chỉ xử lý `To` | Dùng `addCc` hoặc `setCc` |
| “Muốn Bcc thì dùng `addTo` và ẩn trong HTML” | To có thể hiển thị cho người nhận khác | Dùng API Bcc thích hợp |
| “Chỉ HTML mới dùng `MimeMessageHelper`” | Helper cũng gửi plain-text được | `helper.setText(text, false)` |
| “Muốn nhiều người thì gửi một message là tương đương gửi riêng” | Danh sách To được chia sẻ, khó cá nhân hóa | Tạo message riêng khi cần riêng tư |
| “`setTo` đã xác nhận địa chỉ nhận thư có tồn tại” | API chỉ đặt recipient vào message | Xử lý bounce/delivery ở hệ thống email |
| “SMTP xác nhận thành công nghĩa là tất cả đã đọc thư” | Trạng thái nộp thư khác delivery/read | Theo dõi trạng thái độc lập nếu nghiệp vụ cần |

### 14.1. Sai vì gọi `setTo` trong vòng lặp

```java
for (String recipient : recipients) {
    helper.setTo(recipient); // Sai nếu muốn gửi cùng một thư cho tất cả
}
```

Sau vòng lặp, `To` thường chỉ còn **phần tử cuối cùng**, vì mỗi vòng gọi `setTo` thay thế danh sách.

Sửa theo một trong hai cách:

```java
// Cách 1: Gán toàn bộ danh sách một lần.
helper.setTo(recipients.toArray(new String[0]));
```

```java
// Cách 2: Bổ sung từng địa chỉ trên MimeMessageHelper.
for (String recipient : recipients) {
    helper.addTo(recipient);
}
```

Nếu `recipients` có thể rỗng hoặc chứa giá trị không hợp lệ, cần xử lý trước vòng lặp. Đối với `SimpleMailMessage`, **chỉ có cách đầu tiên**, tức gom danh sách rồi gọi `setTo`.

### 14.2. Sai vì đặt lại `To` sau khi đã bổ sung

```java
helper.setTo("alice@example.net");
helper.addTo("bob@example.net");

// Một đoạn code dùng chung chạy ở cuối:
helper.setTo("system@example.org");
```

Kết quả cuối không còn Alice và Bob trong nhóm To. Nếu `system@example.org` chỉ cần nhận bản sao, hãy thêm vào Cc/Bcc theo đúng mục đích hoặc sử dụng `addTo` nếu thực sự cần thêm một người nhận To. Tốt hơn, xác định toàn bộ recipient trước khi dựng message.

### 14.3. Sai vì gửi riêng nhiều thư nhưng vẫn thêm dồn vào cùng message

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message);

for (String recipient : recipients) {
    helper.addTo(recipient);
    mailSender.send(message);
}
```

Luồng này không tạo “một thư độc lập cho từng người”. Danh sách `To` được tăng dần trên **cùng một message**, làm các lần gửi sau có nhiều người nhận hơn các lần trước.

Nếu yêu cầu là **mỗi người một email**, hãy tạo message mới trong mỗi vòng:

```java
for (String recipient : recipients) {
    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

    helper.setFrom("notifications@example.org");
    helper.setTo(recipient);
    helper.setSubject("Thông báo cá nhân");
    helper.setText("Nội dung dành riêng cho bạn.", false);

    mailSender.send(message);
}
```

Thiết kế gửi thực tế còn cần giới hạn lưu lượng, xử lý lỗi và lưu trạng thái nghiệp vụ. Ví dụ này chỉ làm rõ phạm vi sống của đối tượng message.

## 15. Một mô hình thiết kế dễ bảo trì

Thay vì để nhiều thành phần lần lượt sửa người nhận trên một message chung, có thể phân chia thành hai công đoạn:

```text
Sự kiện nghiệp vụ
       |
       v
Tính danh sách To/Cc/Bcc
  - kiểm tra quyền nhận
  - loại trùng theo chính sách
  - phân biệt To, Cc, Bcc
       |
       v
Tạo message
  - SimpleMailMessage.setTo(allTo)
        hoặc
  - MimeMessageHelper.setTo(allTo)
       |
       v
Tạo nội dung, Subject, From
       |
       v
JavaMailSender.send(...)
       |
       v
SMTP submission / mail server
```

Nếu một quá trình thực sự cần thêm recipient **trong lúc xây dựng MIME message**, `addTo` thể hiện rõ ý định bổ sung. Còn khi toàn bộ danh sách đã xác định, `setTo` một lần giúp người đọc code dễ kiểm tra kết quả.

### Gợi ý quy ước đặt tên phương thức

Một service dùng các hàm:

```java
List<String> determinePrimaryRecipients(...);
List<String> determineCopyRecipients(...);
List<String> determineBlindCopyRecipients(...);
```

có thể xác định danh sách ở tầng nghiệp vụ; lớp dựng mail chỉ nhận kết quả và gọi:

```java
helper.setTo(primary.toArray(new String[0]));
helper.setCc(copy.toArray(new String[0]));
helper.setBcc(blindCopy.toArray(new String[0]));
```

Các biến `primary`, `copy` và `blindCopy` trong ví dụ biểu diễn danh sách đã được chuẩn bị. Cách tổ chức này tránh nhầm lẫn khi một helper method tưởng mình đang thêm người nhận nhưng lại gọi `setTo` và xóa mất danh sách cũ.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Với `SimpleMailMessage`, làm sao gửi đến Alice và Bob?

> Gọi `mail.setTo("alice@example.net", "bob@example.net")` hoặc truyền một `String[]` gồm hai địa chỉ. `SimpleMailMessage` không có `addTo`.

**Câu 2.** Trên `MimeMessageHelper`, đoạn sau gửi cho ai?

```java
helper.setTo("alice@example.net");
helper.addTo("bob@example.net");
```

> Hai người thuộc To: Alice và Bob.

**Câu 3.** Còn đoạn sau?

```java
helper.addTo("alice@example.net");
helper.setTo("bob@example.net");
```

> Chỉ Bob còn thuộc To; `setTo` đã thay thế danh sách cũ.

**Câu 4.** Nếu chỉ muốn bổ sung người nhận để nhận bản sao hiển thị, phải dùng phương thức nào?

> Với `MimeMessageHelper`, dùng `addCc(...)`; với `SimpleMailMessage`, dùng `setCc(...)` để đặt danh sách Cc.

**Câu 5.** Có thể dùng `MimeMessageHelper.addTo` khi thư chỉ là text, không có HTML và attachment không?

> Có. `MimeMessageHelper` hỗ trợ plain-text thông qua `setText(text, false)`. Việc chọn helper phụ thuộc nhu cầu thao tác message, không đòi hỏi phải có HTML.

**Câu 6.** Vì sao gọi `addTo` nhiều lần không phải là cách đảm bảo “mỗi người một email”?

> Vì `addTo` thêm vào **cùng một MIME message**. Muốn gửi thư độc lập cho từng người, cần tạo message mới cho từng người hoặc sử dụng cơ chế gửi hàng loạt có hợp đồng xử lý tương đương.

## 17. Ghi nhớ trọng tâm

| Điều cần nhớ | `setTo` | `addTo` |
| --- | --- | --- |
| Ý nghĩa | Đặt/thay thế danh sách `To` | Thêm địa chỉ vào danh sách `To` |
| Có trong `SimpleMailMessage`? | **Có** | **Không** |
| Có trong `MimeMessageHelper`? | **Có** | **Có** |
| Gọi nhiều lần | Lần sau thay danh sách trước | Các lần gọi bổ sung người nhận |
| Có thay đổi Cc/Bcc không? | Không, chỉ nhóm To | Không, chỉ nhóm To |
| Dùng khi nào? | Biết danh sách người nhận cuối cùng | Cần bổ sung từng người vào MIME message |

Với **Simple mail** thông thường, cách trực tiếp nhất là chuẩn bị `String[]`/`List<String>` và gọi `SimpleMailMessage.setTo(...)` một lần. Khi sử dụng `MimeMessageHelper`, hãy nhớ: **`setTo` = thiết lập lại; `addTo` = bổ sung**. Chọn đúng phương thức, đúng lớp và đúng nhóm To/Cc/Bcc giúp email đến đúng người, tránh ghi đè danh sách và giảm rủi ro lộ người nhận ngoài ý muốn.
