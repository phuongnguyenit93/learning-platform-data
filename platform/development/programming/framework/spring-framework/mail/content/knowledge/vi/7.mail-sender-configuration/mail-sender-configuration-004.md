# Default FileTypeMap và xử lý kiểu nội dung

Trong Spring Framework Mail, gửi email chỉ có nội dung văn bản thường khá đơn giản. Nhưng khi thông điệp có **tệp đính kèm**, **hình ảnh hiển thị trong HTML**, hoặc dữ liệu như PDF, CSV, JSON, ZIP, ứng dụng phải cung cấp thông tin để mail client biết nó đang nhận loại dữ liệu nào. Một thành phần quan trọng của quá trình đó là **`FileTypeMap`**: cơ chế ánh xạ tên tệp sang **MIME media type**.

`JavaMailSenderImpl` có thể mang theo một **default FileTypeMap** cho những `MimeMessage` do nó tạo. `MimeMessageHelper` dùng bản đồ này để suy ra `Content-Type` của attachment/inline resource khi ứng dụng **chưa chỉ định rõ loại nội dung**. Nhờ vậy, nhiều loại file phổ biến có thể được đính kèm thuận tiện, nhưng cơ chế suy đoán theo tên file có giới hạn và không nên được coi là kiểm tra nội dung thực tế.

Bài học giải thích bản chất của `FileTypeMap`, cách default được truyền từ sender vào message, khi nào nên dùng map và khi nào nên khai báo `Content-Type` tường minh, cùng cách cấu hình/khắc phục các lỗi phổ biến trong Spring Mail.

## 1. Kiểu nội dung trong email có ý nghĩa gì?

MIME (Multipurpose Internet Mail Extensions) cho phép email chứa nhiều dạng dữ liệu. Mỗi **MIME part** có thể khai báo những header riêng:

```text
Content-Type: application/pdf; name="invoice.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice.pdf"
```

Ba header này có nhiệm vụ khác nhau:

| Header | Giải quyết vấn đề | Ví dụ |
| --- | --- | --- |
| **`Content-Type`** | Nội dung có loại dữ liệu gì? | `application/pdf`, `image/png`, `text/plain; charset=UTF-8` |
| **`Content-Transfer-Encoding`** | Byte được biểu diễn thế nào khi vận chuyển bằng email? | `base64`, `quoted-printable` |
| **`Content-Disposition`** | Gợi ý mail client xử lý phần này như inline hay attachment; có thể kèm tên file | `attachment; filename="invoice.pdf"` |

Ví dụ, một file PDF có thể được gửi với `Content-Type: application/pdf`, `Content-Disposition: attachment` và `Content-Transfer-Encoding: base64`. **`FileTypeMap` chỉ giúp tìm giá trị kiểu nội dung**, không tự chịu trách nhiệm biến byte PDF thành base64 và cũng không quyết định thay người dùng rằng file nên là attachment hay inline.

### Media type khác đuôi file

Tên `invoice.pdf` có phần mở rộng `.pdf`, còn MIME media type tương ứng thường là `application/pdf`. Hai thứ có liên hệ nhưng là hai kiểu dữ liệu khác nhau:

```text
Tên tệp:             invoice.pdf
Phần mở rộng:        .pdf
MIME media type:     application/pdf

Tên tệp:             logo.png
Phần mở rộng:        .png
MIME media type:     image/png
```

**Đuôi file là một gợi ý, không phải chứng cứ chắc chắn về byte bên trong**. Một file thực sự chứa PNG nhưng bị đổi tên thành `logo.pdf` có thể bị FileTypeMap đoán là PDF. Vì vậy, hệ thống xử lý file upload phải kiểm tra nội dung và chính sách cho phép bằng một bước phù hợp với nghiệp vụ, độc lập với FileTypeMap.

## 2. `FileTypeMap` là gì?

Trong hệ sinh thái Spring Framework hiện đại sử dụng Jakarta Mail, `FileTypeMap` thuộc package:

```java
import jakarta.activation.FileTypeMap;
```

Đây là một abstraction của Jakarta Activation để tra cứu media type dựa trên **tên file** hoặc đối tượng `File`. Những phương thức tiêu biểu là:

```java
String getContentType(String filename);
String getContentType(File file);
```

Ví dụ về ý nghĩa một phép tra cứu:

```text
FileTypeMap
  |
  +-- "report.pdf"   --> "application/pdf"
  +-- "logo.png"     --> "image/png"
  +-- "data.csv"     --> "text/csv"      (nếu có mapping)
  +-- "archive.xyzx" --> "application/octet-stream"
                           (khi không nhận diện được)
```

Các kết quả cụ thể phụ thuộc bảng ánh xạ được cấu hình. `application/octet-stream` là kiểu nhị phân tổng quát thường được dùng khi không biết định dạng. **Không nên giả định một đuôi file nhất định luôn được nhận diện ở mọi phiên bản thư viện hoặc môi trường chạy**.

### Một số media type thường dùng

| Loại dữ liệu | Media type thông dụng | Ghi chú |
| --- | --- | --- |
| Text thuần | `text/plain` | Với body văn bản có thể kèm `charset=UTF-8` |
| HTML | `text/html` | Body HTML và charset phải phù hợp |
| PDF | `application/pdf` | Dùng nhiều cho hóa đơn và báo cáo |
| PNG | `image/png` | Có thể là ảnh inline hoặc attachment |
| JPEG | `image/jpeg` | Có thể là ảnh inline hoặc attachment |
| GIF | `image/gif` | Phụ thuộc khả năng hiển thị của mail client |
| CSV | `text/csv` | Cần cân nhắc charset, dấu phân cách và phần mềm mở |
| JSON | `application/json` | Có thể gửi như attachment dữ liệu |
| XML | `application/xml` | Dữ liệu XML |
| ZIP | `application/zip` | Dữ liệu nén nhị phân |
| Word dạng DOCX | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | Media type dài, cần ánh xạ đúng |
| Excel dạng XLSX | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | Không dùng `application/vnd.ms-excel` cho XLSX |
| Không xác định | `application/octet-stream` | Lựa chọn tổng quát khi không biết loại file |

Bảng chỉ nêu **tên media type phù hợp với loại file**, không khẳng định tất cả các mapping đều đã tồn tại trong FileTypeMap mặc định của mọi ứng dụng.

### `MimetypesFileTypeMap` và `ConfigurableMimeFileTypeMap`

Một implementation thường gặp của Jakarta Activation là `MimetypesFileTypeMap`:

```java
import jakarta.activation.MimetypesFileTypeMap;

MimetypesFileTypeMap fileTypeMap = new MimetypesFileTypeMap();
String type = fileTypeMap.getContentType("report.pdf");
```

Spring Framework Mail có `org.springframework.mail.javamail.ConfigurableMimeFileTypeMap`, một implementation có thể cấu hình nguồn mapping. Nó được dùng trong cơ chế FileTypeMap mặc định của Spring Mail. Điều này giúp Spring hỗ trợ các kiểu nội dung thông dụng mà không buộc mỗi ứng dụng phải tự khai báo từng đuôi tệp.

Điều quan trọng là **mapping theo phần mở rộng**: FileTypeMap không mở file ra để phân tích chữ ký định dạng, cấu trúc PDF, nội dung ZIP hay dữ liệu nhúng.

## 3. Default FileTypeMap đi từ sender vào message như thế nào?

`JavaMailSenderImpl` là implementation thường gặp của `JavaMailSender` trong Spring. Nó có khả năng cấu hình **default encoding** và **default FileTypeMap** dùng khi tạo `MimeMessage`.

Luồng khái niệm:

```text
JavaMailSenderImpl
  |
  | defaultEncoding
  | defaultFileTypeMap
  v
createMimeMessage()
  |
  | MimeMessage mang thông tin mặc định
  v
MimeMessageHelper
  |
  | Khi addAttachment/addInline:
  |   Có contentType chỉ định rõ?
  |      | Có  -> dùng contentType đã chỉ định
  |      | Không
  |      v
  |   dùng FileTypeMap để tra tên file/resource
  v
MIME part có Content-Type
  |
  v
Jakarta Mail serialize message để gửi qua SMTP
```

Spring sử dụng một dạng `MimeMessage` có thể mang theo các thiết lập mặc định của sender, nhờ đó `MimeMessageHelper` có thể nhận được default từ `JavaMailSenderImpl`. Khi ứng dụng chỉ dùng các API thông thường:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, true, "UTF-8");
```

helper có thể dùng default FileTypeMap đã được sender cấu hình.

Điều này khác với việc tự tạo một đối tượng `MimeMessage` bằng `new MimeMessage(session)` từ một session bất kỳ: thông tin mặc định riêng do `JavaMailSenderImpl` truyền vào có thể không còn giống nhau. Khi dùng Spring Mail, nên lấy message qua `mailSender.createMimeMessage()`.

### Hai thiết lập mặc định hoàn toàn khác nhau

| Thiết lập | Tác động | Không có tác động |
| --- | --- | --- |
| **Default encoding** | Mã hóa ký tự của các nội dung văn bản liên quan; ví dụ `UTF-8` | Không xác định dữ liệu là PDF hay PNG |
| **Default FileTypeMap** | Suy đoán media type từ tên file cho những MIME part cần tra cứu | Không chuyển byte thành UTF-8 hoặc mã hóa base64 |

Ví dụ một PDF tên `invoice.pdf`:

- Default FileTypeMap có thể cho ra `application/pdf`.
- MIME helper/Jakarta Mail xử lý transfer encoding cho byte dữ liệu.
- Charset `UTF-8` trên helper chủ yếu phục vụ những phần văn bản và giá trị header cần thiết, **không biến byte của PDF thành chuỗi ký tự**.

## 4. Khi nào `MimeMessageHelper` dùng FileTypeMap?

`MimeMessageHelper` có các phương thức tiện ích để gắn file hoặc tài nguyên vào email. Trong những overload **không nhận media type**, helper phải lựa chọn một `Content-Type`. Nó có thể dựa vào `FileTypeMap`.

Ví dụ:

```java
helper.addAttachment("invoice.pdf", new ByteArrayResource(pdfBytes));
```

Helper nhận được tên `invoice.pdf` và có thể tra FileTypeMap để chọn media type. Nếu map không có mapping chính xác, kết quả có thể là một loại tổng quát như `application/octet-stream`.

Nếu ứng dụng đã biết loại dữ liệu, có thể **chỉ định content type rõ ràng**:

```java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
```

Ở đây ứng dụng cung cấp `application/pdf` trực tiếp cho MIME part của attachment. Đây là lựa chọn phù hợp khi file được hệ thống tạo ra và định dạng đã biết chắc, ví dụ service vừa sinh một PDF hợp lệ.

### Các cách thêm attachment

| Cách tạo attachment | Có media type tường minh? | Nguồn suy ra `Content-Type` |
| --- | --- | --- |
| `addAttachment(filename, File)` | Không | Thường theo tên file qua FileTypeMap |
| `addAttachment(filename, InputStreamSource)` | Không | Thường theo tên attachment qua FileTypeMap |
| `addAttachment(filename, InputStreamSource, contentType)` | Có | Giá trị `contentType` do ứng dụng truyền |
| `addAttachment(filename, DataSource)` | Theo DataSource | `DataSource.getContentType()` và cơ chế của thư viện |

Tên phương thức rút gọn để dễ đọc; chi tiết chữ ký phụ thuộc overload được dùng. Với tài nguyên do ứng dụng đã biết media type, overload có `contentType` thường rõ ràng hơn việc dựa vào đuôi file.

### Có khác biệt giữa attachment và inline resource?

Có. **Attachment** thường được hiển thị như file đính kèm; **inline resource** thường được tham chiếu từ HTML, chẳng hạn:

```html
<img src="cid:logo" alt="Company logo"/>
```

Hình ảnh inline vẫn là một MIME part và cũng cần `Content-Type` phù hợp, ví dụ `image/png`. Có thể dùng:

```java
helper.addInline(
        "logo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
```

Khi dùng overload không khai báo content type, việc suy đoán có thể dựa trên tên resource hoặc `contentId` tùy overload. `contentId` như `logo` thường **không có phần mở rộng**, nên khai báo `image/png` rõ ràng giúp tránh phụ thuộc vào kết quả suy đoán.

**Một nguyên tắc đáng nhớ:** MIME media type mô tả nội dung của *MIME part*, không phải chỉ mô tả “toàn bộ email”. Thư HTML có inline image và PDF sẽ chứa nhiều part với media type khác nhau.

## 5. Cách xác định Content-Type: chọn rõ ràng hay suy đoán?

Nếu hệ thống tạo ra nội dung hoặc có metadata đáng tin cậy, nên chọn loại nội dung dựa trên thông tin đó. FileTypeMap rất hữu ích như một cơ chế **fallback** hoặc một phần cấu hình cho các loại file do ứng dụng kiểm soát.

Một hướng quyết định:

```text
Ứng dụng cần thêm một file vào email
                |
                v
     Đã biết chắc media type?
           /            \
         Có             Chưa
          |               |
          v               v
  Truyền contentType   Xác định nguồn file
  tường minh           và mức độ tin cậy
          |               |
          |      +--------+--------+
          |      |                 |
          |  File do hệ thống  File do người dùng
          |  kiểm soát tên     tải lên
          |      |                 |
          |  FileTypeMap      Kiểm tra loại file
          |  có thể hữu ích   theo chính sách
          |      |                 |
          +------+-----------------+
                 |
                 v
     Tạo MIME part với type phù hợp
                 |
                 v
      Nếu thực sự chưa biết định dạng:
      application/octet-stream
```

Không nên gán `application/pdf` chỉ vì người dùng sửa tên file thành `contract.pdf`. Kiểu nội dung không xác thực file.

### Tại sao `application/octet-stream` không luôn là lỗi?

`application/octet-stream` cho biết đây là dữ liệu nhị phân tổng quát. Nhiều mail client vẫn cho phép tải tệp về và đặt tên như bình thường. Trong trường hợp phần mềm không biết chắc kiểu dữ liệu, giá trị này **tốt hơn việc tuyên bố sai một định dạng**.

Tuy nhiên, một số client có thể giảm khả năng preview, áp dụng bộ lọc khác hoặc yêu cầu người nhận chọn ứng dụng để mở. Nếu hệ thống thật sự tạo PDF/PNG/CSV, khai báo chính xác thường làm trải nghiệm tốt hơn.

### Tên file có ý nghĩa gì?

Tên file giúp hệ điều hành/mail client gợi ý cách mở và cho người nhận nhận diện tài liệu. Cần:

- Chọn tên có phần mở rộng phù hợp với định dạng thực.
- Không tin tuyệt đối vào filename từ upload hoặc request.
- Giữ tên hiển thị **không chứa đường dẫn** và ký tự không phù hợp cho header.
- Giới hạn độ dài; xử lý ký tự Unicode qua thư viện MIME.
- Không đưa secrets, token hoặc dữ liệu nhạy cảm vào filename nếu không cần thiết.

Tên file và media type cần nhất quán, nhưng **mức độ an toàn của file vẫn phải được kiểm soát ngoài bước tạo email**.

## 6. Ví dụ Spring Boot: attachment có Content-Type tường minh

Với Spring Boot, thêm starter mail:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

Cấu hình `application.yml` minh họa gửi qua SMTP submission bằng STARTTLS:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    sender: ${MAIL_SENDER_ADDRESS}
```

Cấu hình chỉ minh họa endpoint SMTP hỗ trợ xác thực và STARTTLS trên cổng 587. Thông tin xác thực phải được cấp qua môi trường hoặc secret manager; không ghi credential thật vào source. `spring.mail.default-encoding` hỗ trợ phần **ký tự văn bản**, khác hoàn toàn với cấu hình FileTypeMap.

Service gửi một PDF đã được hệ thống sinh ra:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class InvoiceMailService {

    private final JavaMailSender mailSender;
    private final String senderAddress;

    public InvoiceMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.sender}") String senderAddress
    ) {
        this.mailSender = mailSender;
        this.senderAddress = senderAddress;
    }

    public void sendInvoice(String recipient, byte[] pdfBytes)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom(senderAddress);
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn của bạn");
        helper.setText("Hóa đơn được đính kèm trong email.", false);

        helper.addAttachment(
                "invoice.pdf",
                new ByteArrayResource(pdfBytes),
                "application/pdf"
        );

        mailSender.send(message);
    }
}
```

Ở ví dụ này:

1. `true` trong constructor helper bật chế độ multipart cần thiết để có attachment.
2. `UTF-8` phục vụ xử lý văn bản và các giá trị liên quan.
3. `pdfBytes` là dữ liệu PDF **đã có sẵn**; ví dụ không bao gồm bước sinh PDF.
4. `ByteArrayResource` cung cấp lại byte từ bộ nhớ theo yêu cầu của thư viện.
5. `"application/pdf"` là media type tường minh; không cần suy đoán theo `invoice.pdf`.
6. Helper/Jakarta Mail đóng gói attachment theo MIME, thường dùng transfer encoding như base64 cho dữ liệu nhị phân.

Không nên biến `pdfBytes` thành `String` rồi đưa vào `setText(...)`; PDF không phải chuỗi văn bản UTF-8. Nếu gửi file lớn, cân nhắc sử dụng `FileSystemResource` hoặc một nguồn có thể mở stream nhiều lần, tránh giữ nhiều bản sao dữ liệu trong RAM.

### Khi muốn dùng default FileTypeMap

Nếu filename do ứng dụng kiểm soát và map có mapping tương ứng, có thể dùng overload:

```java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes)
);
```

Khi đó helper dựa vào FileTypeMap để suy ra `Content-Type`. Cách này tiện khi ứng dụng gửi nhiều tệp thông thường có tên chính xác. Nó cũng khiến kết quả phụ thuộc vào mapping ở môi trường chạy, nên cần hiểu default và các trường hợp fallback.

## 7. Cấu hình FileTypeMap theo từng thông điệp

`MimeMessageHelper` có phương thức `setFileTypeMap(FileTypeMap)`. Nó cho phép thay bản đồ nhận diện kiểu file **ở helper hiện tại**, hữu ích nếu một luồng gửi mail cần dùng mapping khác với mặc định.

Ví dụ sử dụng `MimetypesFileTypeMap`:

```java
import jakarta.activation.MimetypesFileTypeMap;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, true, "UTF-8");

MimetypesFileTypeMap map = new MimetypesFileTypeMap();
map.addMimeTypes("application/vnd.example.export exportx");
helper.setFileTypeMap(map);

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Dữ liệu xuất");
helper.setText("Tệp dữ liệu được đính kèm.");
helper.addAttachment(
        "data.exportx",
        new ByteArrayResource(exportBytes)
);

mailSender.send(message);
```

Trong ví dụ:

- `exportx` là phần mở rộng **giả định** của một định dạng nội bộ.
- `application/vnd.example.export` là media type **minh họa**, không phải một media type công cộng đã được đăng ký.
- `addMimeTypes(...)` thêm quy tắc nhận diện vào `MimetypesFileTypeMap`.
- `helper.setFileTypeMap(map)` yêu cầu helper sử dụng map này khi cần suy ra media type.
- Nếu chỉ có một loại file cụ thể, gọi `addAttachment(..., "application/vnd.example.export")` có thể đơn giản hơn việc cấu hình map.

### Phạm vi của `setFileTypeMap`

Một `MimeMessageHelper` gắn với một đối tượng `MimeMessage`; map được thiết lập trên helper chủ yếu ảnh hưởng các thao tác thêm part qua helper đó. **Không nên coi đây là thay đổi default toàn cục** cho mọi `JavaMailSender` hoặc mọi thư gửi sau này.

Khi gửi nhiều email với một quy tắc mapping chung, cấu hình ở sender sẽ hợp lý hơn. Khi gửi một tệp đặc biệt, chỉ định media type trực tiếp thường dễ đọc và ít tác động hơn.

## 8. Cấu hình default FileTypeMap trên `JavaMailSenderImpl`

`JavaMailSenderImpl` cho phép cấu hình `defaultFileTypeMap`. Đây là lựa chọn khi ứng dụng cần **một bộ mapping dùng chung** cho các `MimeMessage` do cùng sender tạo ra.

Phương thức liên quan:

```java
import jakarta.activation.FileTypeMap;
import org.springframework.mail.javamail.JavaMailSenderImpl;

JavaMailSenderImpl sender = new JavaMailSenderImpl();
FileTypeMap customMap = /* instance đã được cấu hình */;
sender.setDefaultFileTypeMap(customMap);
```

Phần trên chỉ minh họa API, chưa phải bean SMTP hoàn chỉnh.

### 8.1. Dùng `ConfigurableMimeFileTypeMap` của Spring

Spring có `ConfigurableMimeFileTypeMap`, cho phép nạp một tệp mapping định dạng `mime.types`.

Ví dụ tài nguyên ứng dụng tại `src/main/resources/mail/mime.types`:

```text
# Custom MIME mappings for application attachments
application/pdf pdf
text/csv csv
application/json json
application/vnd.openxmlformats-officedocument.spreadsheetml.sheet xlsx
application/vnd.example.export exportx
```

Đây là định dạng mapping theo kiểu MIME type và phần mở rộng, **không phải YAML hay Spring properties**. Các media type/extension cụ thể cần được lựa chọn theo dữ liệu mà ứng dụng thật sự tạo.

Bean cấu hình map:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.ConfigurableMimeFileTypeMap;

@Configuration
public class MailTypeMapConfiguration {

    @Bean
    public ConfigurableMimeFileTypeMap mailFileTypeMap() {
        ConfigurableMimeFileTypeMap map = new ConfigurableMimeFileTypeMap();
        map.setMappingLocation(
                new ClassPathResource("mail/mime.types")
        );
        return map;
    }
}
```

`ConfigurableMimeFileTypeMap` hỗ trợ lifecycle initialization của Spring. Khi được khai báo là bean theo cách này, Spring gọi bước khởi tạo cần thiết để nạp mapping. Nếu tạo map bằng `new` ngoài container và sử dụng trực tiếp, phải bảo đảm nó đã được khởi tạo theo hợp đồng của class.

**Lưu ý:** thay mapping location có thể thay đổi những quy tắc sẵn có. Nên coi file `mail/mime.types` là nguồn cấu hình do ứng dụng quản lý và bao gồm đầy đủ những mapping đặc thù cần dùng, thay vì giả định mọi mapping trong cấu hình mặc định sẽ được cộng thêm tự động.

### 8.2. Gắn map vào sender khi tự cấu hình bean

Trong **Spring Framework thuần**, hoặc khi ứng dụng **chủ động tự tạo** bean `JavaMailSenderImpl`, có thể dùng:

```java
import jakarta.activation.FileTypeMap;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSenderImpl;

import java.nio.charset.StandardCharsets;
import java.util.Properties;

@Configuration
public class ManualMailSenderConfiguration {

    @Bean
    public JavaMailSenderImpl javaMailSender(
            FileTypeMap mailFileTypeMap,
            @Value("${SMTP_HOST}") String host,
            @Value("${SMTP_PORT:587}") int port,
            @Value("${SMTP_USERNAME}") String username,
            @Value("${SMTP_PASSWORD}") String password
    ) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(host);
        sender.setPort(port);
        sender.setUsername(username);
        sender.setPassword(password);
        sender.setDefaultEncoding(StandardCharsets.UTF_8.name());
        sender.setDefaultFileTypeMap(mailFileTypeMap);

        Properties properties = sender.getJavaMailProperties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "5000");
        properties.put("mail.smtp.writetimeout", "5000");
        return sender;
    }
}
```

Đoạn này biểu diễn **một cách tự cấu hình sender**, giả sử có bean `FileTypeMap` và biến môi trường SMTP tương ứng. Cổng 587/STARTTLS chỉ là một chế độ submission phổ biến; phải dùng cấu hình của nhà cung cấp thật.

Trong **Spring Boot**, auto-configuration thông thường đã tạo `JavaMailSender` từ `spring.mail.*` khi đáp ứng điều kiện. Nếu tự khai báo bean `JavaMailSenderImpl`, bạn có thể khiến auto-configuration của Boot **không còn tạo sender mặc định**; các thiết lập như `spring.mail.host`, `spring.mail.properties.*` cũng không tự động được sao chép vào bean bạn tự tạo. Vì vậy:

- Nếu chỉ cần gửi một vài tệp có định dạng riêng, ưu tiên **overload truyền media type tường minh**.
- Nếu muốn một map riêng cho một số thư, cấu hình trên **`MimeMessageHelper`**.
- Nếu tất cả email cần mapping chung và ứng dụng đã tự sở hữu cấu hình sender, có thể dùng **`setDefaultFileTypeMap(...)`**.
- Nếu đang dùng Boot auto-config, cân nhắc cách mở rộng phù hợp với cấu trúc ứng dụng thay vì tạo một bean sender thứ hai không cần thiết.

### 8.3. Có thể chỉ cấu hình một property `spring.mail.default-file-type-map` không?

Spring Boot có những property quen thuộc như `spring.mail.host`, `spring.mail.port` và `spring.mail.default-encoding`. Nhưng **default FileTypeMap** là một đối tượng Java của Jakarta Activation, không phải loại dữ liệu mà ứng dụng thông thường gán trực tiếp bằng một dòng cấu hình tương tự `spring.mail.default-encoding`.

Vì vậy, với yêu cầu mapping đặc thù, hãy cấu hình **bean/map hoặc content type tại chỗ** theo API Spring/Jakarta Mail thay vì tự suy diễn rằng có một property chuẩn tên `spring.mail.default-file-type-map`.

## 9. MIME part và kiểu nội dung ở những vị trí khác nhau

Một message có nhiều part có thể có cấu trúc:

```text
MIME message
Content-Type: multipart/mixed; boundary="outer"
  |
  +-- Part 1:
  |     Content-Type: multipart/alternative; boundary="alt"
  |        |
  |        +-- text/plain; charset=UTF-8
  |        |
  |        +-- text/html; charset=UTF-8
  |
  +-- Part 2:
  |     Content-Type: application/pdf
  |     Content-Disposition: attachment; filename="invoice.pdf"
  |
  +-- Part 3:
        Content-Type: text/csv; charset=UTF-8
        Content-Disposition: attachment; filename="data.csv"
```

Ở đây:

- Header ngoài cùng `multipart/mixed` mô tả **container** có nhiều phần.
- `multipart/alternative` chứa những phiên bản trình bày khác nhau của cùng một nội dung.
- `text/plain` và `text/html` là các phần văn bản, cần charset phù hợp.
- `application/pdf` mô tả attachment PDF.
- `text/csv` mô tả attachment CSV; ứng dụng có thể cần xử lý charset và quy ước CSV cụ thể.

**Không sửa `Content-Type` của toàn bộ message thành `application/pdf` chỉ vì email đính kèm PDF**. FileTypeMap cần được dùng khi tạo **part của attachment**, không phải để đặt media type của top-level multipart.

### Khi thêm CSV

Nếu hệ thống tạo CSV UTF-8, media type có thể chứa parameter charset:

```java
helper.addAttachment(
        "report.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
```

Điều này hữu ích khi ứng dụng thật sự biết các byte `csvBytes` được tạo bằng UTF-8. Tuy nhiên, **`text/csv` và `charset=UTF-8` không giải quyết vấn đề dialect CSV** (ký tự phân cách, quoting, BOM hoặc cách ứng dụng spreadsheet nhập dữ liệu). Các vấn đề đó cần xử lý khi tạo CSV.

## 10. HTML email và inline image: chọn Content-Type đúng

Ví dụ email chào mừng có HTML và logo:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.nio.charset.StandardCharsets;

public void sendWelcomeWithLogo(
        JavaMailSender mailSender,
        String recipient
) throws MessagingException {

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_RELATED,
            StandardCharsets.UTF_8.name()
    );

    helper.setFrom("notifications@example.org");
    helper.setTo(recipient);
    helper.setSubject("Chào mừng!");
    helper.setText(
            "<p>Chào mừng đến với hệ thống.</p>"
                    + "<img src=\"cid:logo\" alt=\"Logo\"/>",
            true
    );

    helper.addInline(
            "logo",
            new ClassPathResource("mail/logo.png"),
            "image/png"
    );

    mailSender.send(message);
}
```

Giải thích:

- `helper.setText(..., true)` tạo nội dung **`text/html`**, không phải `text/plain`.
- `cid:logo` tham chiếu một inline MIME part có Content-ID `logo`.
- `addInline("logo", ..., "image/png")` khai báo media type cho ảnh. Vì `logo` không có phần mở rộng, **khai báo tường minh** giúp tránh phụ thuộc vào suy đoán tên.
- `MULTIPART_MODE_RELATED` phù hợp với mối quan hệ giữa HTML và inline resource trong ví dụ; nếu cần thêm attachment hoặc text/HTML alternative, cấu trúc MIME có thể phức tạp hơn.
- HTML được thiết lập **trước khi** thêm inline resource, phù hợp với cách nhiều mail client xử lý tham chiếu CID.

**Không phải mail client nào cũng hiển thị inline image giống nhau.** `image/png` giúp mô tả đúng nội dung nhưng không ép client tải hình hoặc render theo một cách cố định.

## 11. Tự kiểm soát filename và nguồn dữ liệu

Khi ứng dụng xử lý file do người dùng tải lên, có ba mẩu thông tin cần quản lý **riêng biệt**:

| Thông tin | Nguồn có thể có | Có đáng tin tuyệt đối không? |
| --- | --- | --- |
| **Original filename** | Tên do trình duyệt/client gửi | Không |
| **Client-reported content type** | HTTP `Content-Type` của request upload | Không |
| **File bytes** | Nội dung thật của file upload | Cần kiểm tra theo chính sách và định dạng được hỗ trợ |

Không nên chọn `Content-Type` email bằng cách mù quáng tin vào extension hoặc header upload do người dùng kiểm soát.

Một quy trình nghiệp vụ phổ biến:

1. Kiểm tra quyền upload của người dùng và giới hạn kích thước file.
2. Chỉ cho phép các định dạng mà ứng dụng thực sự hỗ trợ.
3. Xác định định dạng bằng cơ chế kiểm tra thích hợp (ví dụ signature/format parser khi cần) thay vì chỉ đọc extension.
4. Gán **tên file an toàn** cho email, không chứa path hoặc các ký tự điều khiển không phù hợp.
5. Chọn media type theo định dạng đã được xác nhận.
6. Đính kèm byte nguyên vẹn bằng `ByteArrayResource`, `FileSystemResource` hoặc một `InputStreamSource` thích hợp.

FileTypeMap có thể tham gia **bước ánh xạ tên file đã tin cậy** sang media type; nó không thay thế các bước kiểm tra bảo mật và nội dung.

### Vì sao `InputStreamSource` phải cung cấp dữ liệu đọc được?

`MimeMessageHelper.addAttachment(...)` có thể yêu cầu mở lại input stream khi JavaMail chuẩn bị/serialize message. Do đó, tài nguyên đầu vào nên là một nguồn có khả năng cung cấp **stream mới mỗi lần đọc**. `ByteArrayResource` và `FileSystemResource` thường phù hợp; một `InputStreamResource` bọc sẵn stream chỉ dùng được một lần có thể gây lỗi trong một số luồng xử lý.

Nếu gửi tệp dung lượng lớn, nên cân nhắc giới hạn bộ nhớ, kích thước email sau base64 và quota của SMTP server. Chọn đúng FileTypeMap **không giảm kích thước file hay vượt qua giới hạn SMTP**.

## 12. Khi Content-Type sai, mail client sẽ gặp chuyện gì?

| Hiện tượng | Nguyên nhân có thể | Cần xem |
| --- | --- | --- |
| File PDF được nhận dưới tên đúng nhưng hiện là dữ liệu nhị phân chung | Mapping không nhận diện `.pdf` hoặc dùng tên không có phần mở rộng | FileTypeMap/overload `addAttachment` và header của part |
| Mail client không preview hình inline | Inline part bị gắn `application/octet-stream` hoặc CID/MIME structure sai | `Content-Type`, `Content-ID` và cấu trúc `multipart/related` |
| HTML bị hiện nguyên tag | Body bị khai báo `text/plain` thay vì `text/html` | `helper.setText(..., true)` |
| PDF bị báo hỏng khi mở | File byte gốc sai, bị chuyển thành String hoặc transfer encoding hỏng | Byte đầu vào, MIME part và quá trình nhận |
| File có phần mở rộng `.csv` nhưng bị xử lý như attachment nhị phân | FileTypeMap không có mapping CSV phù hợp | Media type tường minh `text/csv` hoặc custom map |
| Tên file có dấu bị hiển thị sai | Quy tắc mã hóa parameter filename hoặc khả năng client | `Content-Disposition`, thư viện MIME và mail client |
| Kích thước email vượt giới hạn dù file gốc chưa quá lớn | Base64 và overhead MIME làm tăng kích thước | Giới hạn SMTP/provider; cân nhắc link download |
| Gửi email có tệp đính kèm nhưng body bị trống/mất | MIME multipart tạo chưa đúng | Cách tạo `MimeMessageHelper` và thứ tự đặt các part |
| Một số môi trường nhận diện `.exportx`, môi trường khác trả octet-stream | Map được nạp khác nhau giữa các môi trường | Cấu hình default map / custom `mime.types` |
| Attachment bị hệ thống nhận từ chối | Provider/recipient chặn loại file hoặc chính sách chống lạm dụng | Quy tắc SMTP/provider; loại file; log phản hồi |

**Khác biệt quan trọng:** loại file sai không nhất thiết làm hỏng byte tệp. Có thể mail client vẫn cho tải và mở file bằng chương trình phù hợp. Ngược lại, khai báo `application/pdf` đúng cũng không sửa được một PDF có byte đã hỏng.

### Cách đọc raw MIME khi nghi ngờ sai kiểu nội dung

Ví dụ message có attachment:

```eml
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="mixed-123"

--mixed-123
Content-Type: text/plain; charset=UTF-8

Hóa đơn đính kèm.

--mixed-123
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQKLi4u

--mixed-123--
```

Đây là ví dụ minh họa cấu trúc; chuỗi base64 là đoạn ngắn giả lập, không chứa đủ dữ liệu PDF.

Nếu đọc header ngoài cùng `multipart/mixed` và cho rằng “email không phải PDF nên thiếu type”, đó là nhầm lẫn: **PDF nằm trong một part con**. Cần kiểm tra `Content-Type` trên chính part có `Content-Disposition: attachment`.

Trình tự quan sát:

1. Xác định top-level `Content-Type` và `boundary` nếu có multipart.
2. Tìm đúng MIME part chứa tệp hoặc hình đang gặp vấn đề.
3. Kiểm tra `Content-Type`, `Content-Disposition`, `Content-ID` (nếu inline) của part.
4. Phân biệt lỗi type với lỗi transfer encoding hoặc byte nguồn.
5. So sánh định dạng thật của file với media type mà ứng dụng khai báo.

Việc kiểm tra raw MIME giúp phân biệt lỗi cấu hình FileTypeMap với lỗi tệp nguồn và lỗi hiển thị riêng của mail client.

## 13. Một vài sai lầm thường gặp

### Sai lầm 1: “Chỉ cần đổi `Content-Type` của email ngoài cùng là đủ”

Một ứng dụng tạo message multipart để gửi text và PDF rồi gọi:

```java
message.setHeader("Content-Type", "application/pdf");
```

Lệnh này có thể làm header của **container ngoài cùng** mâu thuẫn với cấu trúc nhiều phần. Đừng thay MIME header bằng thao tác thủ công để “sửa” kiểu attachment. Dùng overload `addAttachment(..., "application/pdf")` hoặc FileTypeMap ở đúng helper.

### Sai lầm 2: “FileTypeMap đọc byte và biết nội dung thực”

Một tệp tên `photo.jpg` có thể chứa nội dung khác. FileTypeMap chỉ suy đoán theo tên, không phải công cụ kiểm tra chữ ký file, phát hiện malware hay xác thực nội dung upload.

### Sai lầm 3: “Đặt `defaultEncoding=UTF-8` thì PDF sẽ tự nhận đúng loại”

Encoding dùng cho **văn bản**. PDF vẫn cần `Content-Type: application/pdf`, có thể được suy ra qua FileTypeMap hoặc truyền tường minh.

### Sai lầm 4: “Base64 là MIME type”

`base64` là một giá trị của **`Content-Transfer-Encoding`**. Nó không phải `Content-Type`. PDF có thể có `Content-Type: application/pdf` và `Content-Transfer-Encoding: base64` cùng lúc.

### Sai lầm 5: “Đổi đuôi file là chuyển đổi định dạng”

Đổi `report.txt` thành `report.pdf` không biến văn bản thành PDF. Media type được suy đoán có thể đổi, nhưng byte gốc vẫn là text. Muốn chuyển đổi định dạng cần chương trình tạo file mới đúng định dạng.

### Sai lầm 6: “Sender có FileTypeMap mặc định nghĩa là mọi helper sẽ dùng đúng map đó”

Default map được truyền khi tạo message qua những đường code thích hợp. Nếu ứng dụng tự tạo message, tự override `helper.setFileTypeMap(...)` hoặc truyền `contentType` tường minh, nguồn quyết định có thể khác. Cần biết **đường tạo message và overload đang dùng**.

### Sai lầm 7: “Thêm mapping vào Spring Boot property là xong”

`FileTypeMap` là đối tượng của Jakarta Activation. Với mapping đặc thù, có thể dùng `ConfigurableMimeFileTypeMap`, `MimeMessageHelper.setFileTypeMap(...)` hoặc `JavaMailSenderImpl.setDefaultFileTypeMap(...)` theo phạm vi cần thiết. Không suy đoán tên property không có trong cấu hình ứng dụng.

## 14. Tình huống vận dụng

### Tình huống A: hệ thống gửi XLSX nhưng mail client không nhận diện đúng

Ứng dụng tạo byte XLSX hợp lệ, gọi:

```java
helper.addAttachment("report.xlsx", new ByteArrayResource(xlsxBytes));
```

Một môi trường gắn đúng media type, môi trường khác gắn octet-stream.

**Giải thích:** hai môi trường có thể có mapping khác nhau. Vì ứng dụng biết chắc đó là XLSX, có thể dùng:

```java
helper.addAttachment(
        "report.xlsx",
        new ByteArrayResource(xlsxBytes),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
);
```

Nếu nhiều tệp XLSX cần cùng quy ước, thêm mapping phù hợp vào FileTypeMap chung cũng là lựa chọn.

### Tình huống B: ảnh inline bị gửi thành `application/octet-stream`

Ứng dụng dùng content ID `logo` và một overload không chỉ rõ content type.

**Giải thích:** `logo` không chứa phần mở rộng giúp map suy đoán. Dùng `addInline("logo", resource, "image/png")` khi biết tệp là PNG. Đồng thời bảo đảm HTML chứa `cid:logo` và MIME part được tạo ở cấu trúc phù hợp.

### Tình huống C: PDF đính kèm “đúng kiểu” nhưng file lỗi

Ứng dụng gọi `addAttachment("invoice.pdf", resource, "application/pdf")` nhưng người nhận không mở được.

**Giải thích:** header media type đã được khai báo, song có thể dữ liệu của `resource` sai hoặc stream không được cung cấp đầy đủ. Cần xác định nguồn byte và cơ chế đọc lại stream; đổi FileTypeMap không sửa được byte PDF.

### Tình huống D: muốn gửi định dạng nội bộ `.exportx`

Nhiều luồng gửi loại file này và cần một media type nhất quán trong cùng một ứng dụng.

**Giải thích:** có thể định nghĩa mapping trong `mime.types`, dùng `ConfigurableMimeFileTypeMap`, rồi đặt map ở sender nếu đang chủ động cấu hình sender. Nếu chỉ có một email đặc biệt, truyền media type tường minh tại `addAttachment` sẽ đơn giản hơn.

### Tình huống E: ứng dụng Spring Boot bị mất cấu hình SMTP sau khi thêm bean sender riêng

Nhóm phát triển tạo `@Bean JavaMailSenderImpl` chỉ để gọi `setDefaultFileTypeMap(...)`, nhưng quên đặt host, tài khoản và TLS.

**Giải thích:** bean tự khai báo có thể thay thế đường auto-configuration. Khi sở hữu sender, phải cấu hình đầy đủ thông số SMTP; nếu chỉ cần chỉnh một attachment, nên tránh thay sender và dùng overload với content type trực tiếp.

## 15. Quy tắc thực hành cho Spring Mail

| Nhu cầu | Cách làm phù hợp | Lý do |
| --- | --- | --- |
| Gửi một PDF do hệ thống tạo | `addAttachment(..., "application/pdf")` | Loại dữ liệu đã rõ, ít phụ thuộc môi trường |
| Gửi một PNG inline | `addInline(..., "image/png")` | Content ID có thể không có phần mở rộng |
| Gửi nhiều loại file phổ biến có tên đúng | Dùng default FileTypeMap | Thuận tiện, tránh lặp media type |
| Thêm một extension riêng cho một luồng gửi | `helper.setFileTypeMap(...)` hoặc content type tường minh | Phạm vi thay đổi hẹp |
| Đồng bộ mapping cho toàn bộ sender do mình cấu hình | `JavaMailSenderImpl.setDefaultFileTypeMap(...)` | Cùng một mặc định cho các message liên quan |
| Nạp mapping từ tài nguyên ứng dụng | `ConfigurableMimeFileTypeMap` + `mime.types` | Tách bảng ánh xạ khỏi business code |
| Đính kèm file do người dùng upload | Kiểm tra định dạng thật và chọn type sau khi kiểm tra | Phần mở rộng và upload MIME type có thể giả |
| Không biết định dạng | `application/octet-stream` | Không tuyên bố sai kiểu nội dung |
| Cần hỗ trợ tiếng Việt trong body | `charset=UTF-8` / default encoding phù hợp | Giải quyết ký tự văn bản, khác FileTypeMap |

**Default FileTypeMap là một cơ chế suy đoán media type dựa trên tên file**, được sender và MIME helper sử dụng khi cần. Nó làm việc gửi attachment tiện hơn, nhưng không xác minh byte dữ liệu, không xác định tính an toàn, không mã hóa transfer encoding và không thay thế chính sách nội dung của ứng dụng. Khi biết chính xác định dạng, hãy **chỉ định `Content-Type` tường minh**; khi cần quy tắc chung cho nhiều phần mở rộng, hãy cấu hình map ở đúng phạm vi của `MimeMessageHelper` hoặc `JavaMailSenderImpl`.
