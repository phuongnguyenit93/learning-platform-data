# Đường dẫn classpath và resource trong JAR trong Spring Framework Mail

Khi email cần logo, banner, ảnh minh họa hoặc tài liệu mẫu được đóng gói cùng ứng dụng, file thường nằm trong thư mục `src/main/resources`. Trong lúc chạy từ IDE, lập trình viên có thể vô tình xem những file này như file nằm trên filesystem. Nhưng khi ứng dụng được đóng gói thành JAR, tài nguyên có thể nằm **bên trong archive hoặc trong một JAR lồng**, không còn là file độc lập có đường dẫn filesystem thông thường.

Spring cung cấp abstraction `Resource` để đọc tài nguyên từ nhiều nguồn: classpath, filesystem, URL, byte array và các nguồn khác. Trong Spring Framework Mail, `MimeMessageHelper` nhận `Resource` hoặc `InputStreamSource`, vì vậy có thể đính kèm ảnh và tài liệu từ classpath ngay cả khi ứng dụng đang chạy từ JAR.

Điểm quan trọng là: **đường dẫn classpath là tên tài nguyên được class loader tìm kiếm, không phải đường dẫn thư mục trên máy**. Với resource bên trong JAR, hãy đọc qua `getInputStream()` hoặc truyền trực tiếp `Resource` cho mail helper. Không giả định tài nguyên luôn có thể chuyển thành `File` bằng `getFile()`.

## 1. Classpath là gì?

Classpath là tập hợp các thư mục và archive mà Java runtime dùng để tìm class và resource. Khi ứng dụng chạy từ IDE, classpath thường chứa thư mục output như `target/classes` hoặc `build/resources/main. Khi đóng gói, cùng những tài nguyên đó thường được đưa vào JAR.

Ví dụ cấu trúc dự án:

~~~text
my-mail-app/
├── src/
│   └── main/
│       ├── java/
│       │   └── com/example/mail/
│       │       └── NotificationService.java
│       └── resources/
│           └── mail/
│               ├── images/
│               │   ├── logo.png
│               │   └── banner.jpg
│               └── documents/
│                   └── terms.pdf
└── pom.xml
~~~

Các file trong `src/main/resources` được build tool sao chép vào classpath output. Khi chạy từ thư mục classes, tài nguyên có thể xuất hiện tại:

~~~text
target/classes/mail/images/logo.png
~~~

Khi đóng gói JAR thông thường, entry có thể là:

~~~text
mail/images/logo.png
~~~

Với executable Spring Boot JAR, application classes và resources thường nằm dưới `BOOT-INF/classes/` trong archive. Spring Boot loader thiết lập class loader có khả năng đọc resource trong cấu trúc đóng gói này.

Trong code Java, đường dẫn tài nguyên bắt đầu từ **classpath root**, vì vậy thường dùng:

~~~text
mail/images/logo.png
~~~

Không đưa phần đường dẫn source của dự án vào:

~~~text
src/main/resources/mail/images/logo.png
~~~

Đó là đường dẫn ở thời điểm phát triển, không phải tên resource trên classpath.

### Tài nguyên trong JAR không phải file thường

Một JAR là archive có cấu trúc ZIP. Một resource bên trong JAR là một entry của archive. Class loader biết cách tìm và đọc entry đó, nhưng hệ điều hành không nhất thiết cung cấp một đường dẫn file độc lập cho entry.

~~~text
Khi chạy từ IDE:
  classpath -> target/classes/
                  |
                  +--> mail/images/logo.png

Khi chạy từ JAR:
  classpath -> application.jar
                  |
                  +--> mail/images/logo.png

Khi chạy executable Spring Boot JAR:
  application.jar
      |
      +--> BOOT-INF/classes/mail/images/logo.png
      |
      +--> BOOT-INF/lib/dependency.jar
                 |
                 +--> resources của dependency
~~~

Đường dẫn logic `mail/images/logo.png` có thể giữ nguyên ở các môi trường, trong khi cách lưu trữ vật lý khác nhau.

## 2. Đặt resource trong src/main/resources

Với Maven hoặc Gradle, vị trí phổ biến cho resource dùng khi chạy ứng dụng là `src/main/resources`. Ví dụ:

~~~text
src/main/resources/
└── mail/
    ├── images/
    │   ├── logo.png
    │   └── banner.jpg
    └── documents/
        └── terms.pdf
~~~

Sau khi build, ứng dụng có thể tham chiếu `mail/images/logo.png`, `mail/images/banner.jpg` và `mail/documents/terms.pdf`.

Ví dụ:

~~~java
new ClassPathResource("mail/images/logo.png");
~~~

Không dùng:

~~~java
new ClassPathResource(
    "src/main/resources/mail/images/logo.png"
);
~~~

Bởi vì `src/main/resources` là thư mục nguồn được build tool đưa vào classpath; nó không nằm trong tên resource cuối cùng.

### Chú ý chữ hoa và chữ thường

Windows thường có filesystem không phân biệt hoa/thường theo cấu hình phổ biến, trong khi tên entry trong JAR có tính phân biệt hoa/thường. Ví dụ file thực tế là `mail/images/Logo.png` nhưng code lại yêu cầu `mail/images/logo.png`, có thể chạy được trên một máy phát triển Windows nhưng thất bại khi chạy từ JAR trên Linux. Luôn dùng đúng chính tả và casing của resource.

## 3. Dùng ClassPathResource

`ClassPathResource` là implementation của Spring `Resource` dùng để đọc tài nguyên trên classpath.

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

Resource logo =
    new ClassPathResource("mail/images/logo.png");
~~~

Có thể kiểm tra resource:

~~~java
if (!logo.exists()) {
    throw new IllegalStateException("Email logo was not found");
}

if (!logo.isReadable()) {
    throw new IllegalStateException("Email logo is not readable");
}
~~~

Các phương thức thường dùng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `exists()` | Kiểm tra resource có tồn tại theo nguồn hiện tại không |
| `isReadable()` | Kiểm tra resource có thể đọc được theo khả năng implementation |
| `getInputStream()` | Mở stream để đọc nội dung |
| `getURL()` | Lấy URL nếu resource có thể biểu diễn thành URL |
| `getURI()` | Lấy URI nếu có thể biểu diễn |
| `getFile()` | Lấy File nếu resource tương ứng với file trên filesystem |
| `contentLength()` | Lấy kích thước nội dung nếu implementation có thể xác định |

Đối với resource nằm trong JAR, `exists()` và `getInputStream()` là những thao tác phù hợp. `getFile()` có thể thất bại vì entry trong JAR không phải file độc lập.

### Đọc resource bằng InputStream

~~~java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.ClassPathResource;

ClassPathResource resource =
    new ClassPathResource("mail/images/logo.png");

try (InputStream input = resource.getInputStream()) {
    byte[] buffer = new byte[8192];

    int read;
    while ((read = input.read(buffer)) != -1) {
        // Xử lý từng phần dữ liệu.
    }
}
~~~

`getInputStream()` hoạt động thông qua class loader và không yêu cầu resource phải được giải nén thành file thường. Đừng quên đóng stream bằng try-with-resources.

### Chọn ClassLoader hoặc Class

`ClassPathResource` có thể được tạo bằng đường dẫn và class loader:

~~~java
ClassPathResource resource = new ClassPathResource(
    "mail/images/logo.png",
    Thread.currentThread().getContextClassLoader()
);
~~~

Hoặc dùng một class làm điểm tham chiếu:

~~~java
ClassPathResource resource =
    new ClassPathResource("/mail/images/logo.png", NotificationService.class);
~~~

Cách dùng class làm tham chiếu có quy tắc phân giải theo class đó; đường dẫn tương đối có thể được tính từ package của class. Nếu muốn đường dẫn từ classpath root, cần dùng dạng tuyệt đối phù hợp hoặc dùng constructor nhận class loader với tên resource không có dấu gạch chéo đầu.

Với ứng dụng Spring thông thường, `new ClassPathResource("mail/images/logo.png")` thường đủ rõ ràng. Khi ứng dụng có nhiều class loader, plugin hoặc môi trường container đặc biệt, cần xác định class loader được dùng để tìm tài nguyên.

## 4. Dùng ResourceLoader trong ứng dụng Spring

`ResourceLoader` là abstraction của Spring để lấy resource từ một location string. Nó hữu ích khi muốn chọn nguồn tài nguyên qua cấu hình thay vì tạo trực tiếp implementation.

~~~java
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class MailAssetService {

    private final ResourceLoader resourceLoader;

    public MailAssetService(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public Resource getLogo() {
        return resourceLoader.getResource(
            "classpath:mail/images/logo.png"
        );
    }
}
~~~

Prefix `classpath:` chỉ rõ rằng Spring cần tìm resource trên classpath.

Các prefix thường gặp:

| Location | Ý nghĩa |
| --- | --- |
| `classpath:mail/logo.png` | Resource trên classpath |
| `file:/opt/app/mail/logo.png` | Resource từ filesystem theo URL file |
| `https://cdn.example.com/logo.png` | Resource từ URL HTTP/HTTPS |
| `/opt/app/mail/logo.png` | Có thể được xử lý như đường dẫn theo implementation/context; nên dùng prefix rõ ràng để tránh nhập nhằng |

Khi muốn đọc một resource cố định được đóng gói cùng ứng dụng, `classpath:` là lựa chọn dễ hiểu. Khi muốn đọc file được quản trị bên ngoài JAR và có thể thay đổi mà không build lại ứng dụng, dùng cấu hình filesystem hoặc storage riêng.

### ResourceLoader không đồng nghĩa với mọi pattern classpath

`ResourceLoader#getResource(...)` phù hợp với một location cụ thể. Nếu cần tìm nhiều resource theo wildcard như `classpath*:mail/**/*.png`, dùng `ResourcePatternResolver`. Prefix `classpath*:` có ý nghĩa tìm kiếm nhiều vị trí trên classpath và trong dependency JAR; không nên giả định mọi implementation `ResourceLoader` đều xử lý pattern này như mong muốn.

## 5. Dùng ResourcePatternResolver để tìm nhiều resource

Một số email có thể cần đính kèm nhiều tài liệu mẫu hoặc chọn ảnh theo một thư mục. `PathMatchingResourcePatternResolver` hỗ trợ pattern matching:

~~~java
import java.io.IOException;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;

ResourcePatternResolver resolver =
    new PathMatchingResourcePatternResolver();

Resource[] templates = resolver.getResources(
    "classpath*:mail/templates/**/*.html"
);

for (Resource template : templates) {
    System.out.println(template.getDescription());
}
~~~

Phân biệt:

- `classpath:...` thường tìm resource theo một location trên classpath.
- `classpath*:...` tìm tất cả resource phù hợp trên classpath, có thể gồm nhiều thư mục và dependency JAR.
- `**` và `*` là pattern được resolver xử lý, không phải cú pháp của file path thông thường.

Nếu chỉ cần logo có tên cố định, không cần pattern resolver. Nếu cần quét nhiều plugin hoặc tài nguyên do nhiều module cung cấp, `classpath*:` có thể hữu ích.

### Lưu ý khi quét resource trong JAR

Pattern matching trên JAR có thể phụ thuộc cách resolver và class loader cung cấp URL. Với pattern đơn giản, Spring xử lý nhiều trường hợp phổ biến; nhưng không nên thiết kế ứng dụng dựa trên giả định rằng mọi archive hoặc custom class loader đều hỗ trợ mọi kiểu wildcard giống filesystem.

Khi danh sách resource là một phần cấu hình quan trọng, nên dùng manifest/catalog rõ ràng hoặc kiểm thử trên artifact đóng gói thực tế.

## 6. Vì sao getFile() thường thất bại khi resource nằm trong JAR?

Một lỗi phổ biến:

~~~java
ClassPathResource resource =
    new ClassPathResource("mail/images/logo.png");

File file = resource.getFile();
~~~

Khi chạy từ IDE, resource có thể nằm trong `target/classes`, vì vậy `getFile()` có thể trả về file thật. Khi chạy từ JAR, resource có thể là một entry trong archive, không có đường dẫn file độc lập. Khi đó, Spring không thể biểu diễn nó thành `java.io.File` và có thể ném `FileNotFoundException`.

Đoạn code có vẻ chạy tốt ở môi trường phát triển nhưng hỏng khi deploy:

~~~text
IDE:
  target/classes/mail/images/logo.png
  -> có thể ánh xạ thành File

Executable JAR:
  app.jar!/BOOT-INF/classes/mail/images/logo.png
  -> entry trong archive, không phải File thông thường
~~~

### Không chuyển URL JAR thành File bằng cách cắt chuỗi

Một số code cố làm:

~~~java
String path = resource.getURL().getPath();
File file = new File(path);
~~~

Cách này không đáng tin cậy. URL có thể dùng protocol hoặc dạng archive khác nhau, chứa ký tự đã encode, có dấu phân tách archive, hoặc được cung cấp bởi class loader đặc biệt. Chuyển một URL archive thành File bằng cách tự cắt chuỗi sẽ làm code phụ thuộc vào cách đóng gói.

**Nếu API nhận Resource hoặc InputStreamSource, hãy truyền resource trực tiếp.** Nếu thật sự cần file hệ thống, hãy sao chép stream sang file tạm có quản lý vòng đời.

### getURL() vẫn hữu ích, nhưng không phải File

`getURL()` có thể trả về URL biểu diễn resource, chẳng hạn URL kiểu JAR hoặc URL đặc thù của launcher. Có thể mở stream từ URL nếu cần, nhưng không nên giả định protocol luôn là `file:`, URL có thể chuyển thẳng thành `Path` hoặc chuỗi URL có một định dạng cố định. Hãy dùng API của `Resource` thay vì tự phân tích chuỗi URL.

## 7. Đính kèm ảnh classpath trong email bằng MimeMessageHelper

Với ảnh logo được đóng gói cùng ứng dụng, không cần chuyển resource thành File. `MimeMessageHelper` nhận trực tiếp `Resource`:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailer {

    private final JavaMailSender mailSender;

    public WelcomeMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient)
            throws MessagingException {

        Resource logo =
            new ClassPathResource("mail/images/logo.png");

        if (!logo.exists() || !logo.isReadable()) {
            throw new IllegalStateException(
                "Classpath email logo is missing or unreadable");
        }

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            "UTF-8"
        );

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Chào mừng bạn");

        String html = """
            <html lang="vi">
              <body>
                <img src="cid:brandLogo"
                     width="120"
                     alt="Example">
                <h1>Chào mừng bạn!</h1>
                <p>Tài khoản của bạn đã sẵn sàng.</p>
              </body>
            </html>
            """;

        helper.setText(html, true);

        // Nên thêm inline resource sau khi đã đặt phần text/HTML.
        helper.addInline("brandLogo", logo, "image/png");

        mailSender.send(message);
    }
}
~~~

Các điểm cần chú ý:

- Đường dẫn `mail/images/logo.png` tính từ classpath root.
- `Resource` có thể đọc resource ngay cả khi resource nằm trong JAR.
- `addInline` nhận Content-ID là `brandLogo`.
- HTML tham chiếu bằng `cid:brandLogo`.
- Content type được khai báo là `image/png`; hãy dùng MIME type đúng với file thực tế.
- `setText(html, true)` đánh dấu nội dung là HTML.
- Gọi `addInline` sau khi thiết lập body theo khuyến nghị của Spring để đảm bảo cấu trúc MIME được dựng đúng.

Content-ID là định danh trong message, không phải đường dẫn classpath. Có thể đặt tên như `brandLogo`, `headerBanner` hoặc `productImage-123`, miễn là duy nhất trong phạm vi email và trùng với chuỗi `cid:...` trong HTML.

### Gửi cả plain text và HTML

Nếu email cần bản text dự phòng, có thể dùng overload `setText(plainText, htmlText)`:

~~~java
String plainText = """
    Xin chào!

    Tài khoản của bạn đã được tạo.
    """;

String htmlText = """
    <html>
      <body>
        <img src="cid:brandLogo" alt="Example">
        <h1>Xin chào!</h1>
        <p>Tài khoản của bạn đã được tạo.</p>
      </body>
    </html>
    """;

helper.setText(plainText, htmlText);
helper.addInline("brandLogo", logo, "image/png");
~~~

Constructor multipart mode ở ví dụ trên hỗ trợ cấu trúc MIME cần thiết cho nội dung và resource liên quan. Hai phiên bản text/HTML là cùng một thông điệp ở hai dạng hiển thị.

## 8. Đính kèm tài liệu nằm trong JAR

Resource trong JAR cũng có thể được dùng làm attachment, ví dụ điều khoản sử dụng hoặc tài liệu PDF được phát hành cùng ứng dụng:

~~~java
Resource terms =
    new ClassPathResource("mail/documents/terms.pdf");

if (!terms.exists() || !terms.isReadable()) {
    throw new IllegalStateException(
        "Terms document is not available");
}

helper.addAttachment("terms-and-conditions.pdf", terms);
~~~

Không cần gọi `terms.getFile()`. Helper có thể đọc resource thông qua abstraction stream.

Ví dụ đầy đủ:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("support@example.com");
helper.setTo(recipient);
helper.setSubject("Tài liệu hướng dẫn");
helper.setText("Vui lòng xem tài liệu đính kèm.", false);

Resource guide =
    new ClassPathResource("mail/documents/guide.pdf");

helper.addAttachment("guide.pdf", guide);

mailSender.send(message);
~~~

Khi tài liệu được đóng gói trong JAR, nội dung sẽ được đọc từ archive và đóng gói thành MIME part. Người nhận nhận một attachment bình thường, không biết file ban đầu đến từ classpath hay filesystem.

### Tên attachment khác đường dẫn resource

`mail/documents/guide.pdf` là vị trí nội bộ trong ứng dụng. `guide.pdf` là tên hiển thị cho người nhận. Hai giá trị có thể khác nhau:

~~~java
helper.addAttachment(
    "user-guide-v2.pdf",
    new ClassPathResource("mail/documents/guide.pdf")
);
~~~

Không gửi đường dẫn nội bộ như `BOOT-INF/classes/mail/documents/guide.pdf` cho người nhận. Hãy chọn tên file có ý nghĩa và không chứa đường dẫn máy chủ.

## 9. Resource phải có thể mở stream mới

Spring `Resource` kế thừa `InputStreamSource`. Đặc điểm quan trọng là một resource thông thường như `ClassPathResource` có thể mở một stream mới mỗi lần gọi `getInputStream()`.

~~~java
Resource logo =
    new ClassPathResource("mail/images/logo.png");

try (InputStream first = logo.getInputStream()) {
    // Đọc lần đầu.
}

try (InputStream second = logo.getInputStream()) {
    // Mở stream mới cho lần đọc tiếp theo.
}
~~~

Điều này hữu ích khi thư viện MIME cần đọc nội dung trong lúc serialize message hoặc khi ứng dụng đo resource trước khi gửi.

### Tránh InputStreamResource cho stream đã dùng một lần

Không nên mở stream sớm rồi bọc nó:

~~~java
InputStream input = resource.getInputStream();
InputStreamResource oneShot = new InputStreamResource(input);
helper.addInline("logo", oneShot, "image/png");
~~~

`InputStreamResource` đại diện cho một stream đã có sẵn và thường chỉ đọc được một lần. Nếu bước khác đã đọc stream hoặc thư viện cần mở lại, có thể gặp lỗi stream đã đóng hoặc đã tiêu thụ.

Đối với classpath resource, truyền trực tiếp `ClassPathResource`:

~~~java
Resource logo =
    new ClassPathResource("mail/images/logo.png");

helper.addInline("logo", logo, "image/png");
~~~

Nếu có dữ liệu byte đã được nạp trong bộ nhớ, `ByteArrayResource` có thể mở stream mới từ byte array, nhưng giữ file lớn trong RAM có thể tốn bộ nhớ. Với tài nguyên tĩnh đóng gói trong JAR, `ClassPathResource` thường phù hợp hơn.

### Custom InputStreamSource

Khi nguồn dữ liệu không có implementation Resource sẵn, có thể cung cấp một `InputStreamSource` tạo stream mới mỗi lần:

~~~java
InputStreamSource source = () -> Files.newInputStream(path);

helper.addAttachment("report.pdf", source, "application/pdf");
~~~

Lambda này mở file mới mỗi lần được gọi. Không viết lambda trả về cùng một stream đã mở trước đó.

## 10. Dùng resource từ cấu hình

Nếu đường dẫn asset thay đổi theo môi trường, có thể đưa location vào cấu hình:

~~~yaml
app:
  mail:
    logo: classpath:mail/images/logo.png
    terms: classpath:mail/documents/terms.pdf
~~~

Bind cấu hình:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailResourceProperties(
    String logo,
    String terms
) {}
~~~

Dùng `ResourceLoader` để resolve:

~~~java
@Service
public class ConfiguredMailAssets {

    private final ResourceLoader resourceLoader;
    private final MailResourceProperties properties;

    public ConfiguredMailAssets(
            ResourceLoader resourceLoader,
            MailResourceProperties properties) {
        this.resourceLoader = resourceLoader;
        this.properties = properties;
    }

    public Resource logo() {
        return resourceLoader.getResource(properties.logo());
    }

    public Resource terms() {
        return resourceLoader.getResource(properties.terms());
    }
}
~~~

Cấu hình mặc định có thể trỏ đến classpath, trong khi production có thể trỏ tới filesystem hoặc storage phù hợp nếu cần cập nhật tài nguyên mà không build lại ứng dụng.

Location trong cấu hình là dữ liệu đầu vào của resource loader. Nếu người có quyền chỉnh cấu hình có thể chỉ định URL hoặc file path, cần kiểm soát scheme, thư mục được phép và quyền truy cập. Không nhận một location tùy ý từ HTTP request rồi chuyển thẳng cho `ResourceLoader`; điều đó có thể tạo đường truy cập tới file hoặc URL không mong muốn.

## 11. Classpath resource và filesystem resource khác nhau thế nào?

Spring có nhiều implementation `Resource`. Chọn đúng loại theo nơi lưu file:

| Implementation | Nguồn dữ liệu | Dùng khi |
| --- | --- | --- |
| `ClassPathResource` | Classpath, gồm resource trong JAR | Logo, template, PDF mẫu được đóng gói cùng ứng dụng |
| `FileSystemResource` | Filesystem | File do ứng dụng tạo hoặc quản lý bên ngoài JAR |
| `PathResource` | Java NIO Path | Làm việc với path filesystem đã được xác định |
| `UrlResource` | URL | Resource ở HTTP/HTTPS hoặc URL protocol khác |
| `ByteArrayResource` | Byte array trong bộ nhớ | Nội dung nhỏ đã có sẵn trong RAM |
| `InputStreamResource` | InputStream có sẵn | Nguồn stream một lần, cần quản lý vòng đời cẩn thận |

Ví dụ:

~~~java
Resource classpathLogo =
    new ClassPathResource("mail/images/logo.png");

Resource externalLogo =
    new FileSystemResource("/opt/app/assets/logo.png");

Resource remoteDocument =
    new UrlResource("https://cdn.example.com/docs/guide.pdf");
~~~

Trong email service, nếu logo được phát hành cùng phiên bản ứng dụng, dùng `ClassPathResource`. Nếu người quản trị thay logo mà không deploy lại, có thể dùng filesystem hoặc object storage. Nếu URL remote là dữ liệu không tin cậy, cần kiểm soát SSRF, redirect, timeout và kích thước trước khi tải.

### Khi nào nên dùng file bên ngoài JAR?

Dùng resource ngoài JAR khi:

- Quản trị viên cần thay hình/logo mà không build lại ứng dụng.
- Tenant có bộ ảnh hoặc tài liệu riêng.
- File do người dùng upload và được lưu trong object storage.
- Tài liệu có dung lượng lớn hoặc cập nhật thường xuyên.
- Nội dung được quản lý qua CMS.

Resource bên trong JAR phù hợp với asset tĩnh đi cùng phiên bản code, ví dụ logo hệ thống, template mặc định, PDF hướng dẫn cố định. Khi asset cần thay đổi độc lập với release, nên tách khỏi JAR.

## 12. Kiểm tra resource trong lúc khởi động và lúc gửi

Có hai cách kiểm tra:

**Kiểm tra khi khởi động** phù hợp với asset bắt buộc luôn phải có, ví dụ logo thương hiệu. Ứng dụng có thể fail fast nếu resource không tồn tại, tránh tới lúc gửi mới phát hiện.

~~~java
@Component
public class MailAssetVerifier implements InitializingBean {

    private final Resource logo;

    public MailAssetVerifier() {
        this.logo = new ClassPathResource("mail/images/logo.png");
    }

    @Override
    public void afterPropertiesSet() throws IOException {
        if (!logo.exists() || !logo.isReadable()) {
            throw new IllegalStateException(
                "Required mail resource is missing");
        }
    }
}
~~~

**Kiểm tra lúc gửi** phù hợp khi resource được chọn động theo tenant, template hoặc loại thông báo. Kiểm tra trước khi tạo message giúp trả lỗi có ngữ cảnh rõ ràng.

Không nên mở stream rồi giữ suốt vòng đời singleton chỉ để chứng minh file tồn tại. Hãy kiểm tra resource, sau đó mở stream theo nhu cầu của từng message.

### Kiểm tra nội dung thực tế

`exists()` chỉ cho biết resource được tìm thấy. Nó không chứng minh nội dung là PNG hợp lệ, file PDF không hỏng hoặc MIME type đúng. Với asset tĩnh do dự án kiểm soát, có thể kiểm tra thêm trong build/test. Với file upload hoặc resource bên ngoài, cần xác minh định dạng và trạng thái file theo policy.

## 13. Kiểm thử classpath resource trong môi trường test

Unit test có thể kiểm tra resource được đưa vào test/runtime classpath:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;

class MailClasspathResourceTest {

    @Test
    void logoIsAvailableOnClasspath() throws Exception {
        ClassPathResource logo =
            new ClassPathResource("mail/images/logo.png");

        assertTrue(logo.exists());
        assertTrue(logo.isReadable());

        try (InputStream input = logo.getInputStream()) {
            assertTrue(input.read() >= 0);
        }
    }
}
~~~

Test này xác nhận resource có thể được tìm thấy và đọc trong classpath của test. Nó chưa chứng minh resource chắc chắn được đưa vào executable JAR cuối cùng.

### Kiểm tra artifact đã đóng gói

Một lỗi thường gặp là test trong IDE chạy thành công nhưng build artifact thiếu file do cấu hình resource filtering/exclude hoặc packaging tùy chỉnh.

Với JAR, có thể kiểm tra danh sách entry bằng công cụ `jar`:

~~~powershell
jar tf target/my-mail-app.jar | Select-String "mail/images/logo.png"
~~~

Với executable Spring Boot JAR, entry thường có dạng:

~~~text
BOOT-INF/classes/mail/images/logo.png
~~~

Với JAR Java thông thường, entry có thể là:

~~~text
mail/images/logo.png
~~~

Sau đó chạy ứng dụng từ chính JAR và thực hiện smoke test đọc resource. Đây là cách kiểm tra môi trường đóng gói gần với production hơn việc chỉ chạy test từ IDE.

Không hard-code vị trí vật lý trong JAR vào code ứng dụng. Danh sách entry hữu ích cho việc kiểm tra artifact, còn runtime nên tiếp tục dùng `Resource` và class loader.

## 14. Đường dẫn resource trong executable Spring Boot JAR

Spring Boot executable JAR có cấu trúc đóng gói riêng. Resource ứng dụng thường nằm trong `BOOT-INF/classes`, còn dependency JAR nằm trong `BOOT-INF/lib`. Boot loader tạo class loader có khả năng tìm class và resource trong cấu trúc này.

~~~text
my-mail-app.jar
├── META-INF/
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── application.yml
    │   └── mail/
    │       └── images/
    │           └── logo.png
    └── lib/
        ├── spring-boot-*.jar
        └── jakarta-mail-*.jar
~~~

Trong code, vẫn dùng:

~~~java
Resource logo =
    new ClassPathResource("mail/images/logo.png");
~~~

Không dùng:

~~~java
new ClassPathResource(
    "BOOT-INF/classes/mail/images/logo.png"
);
~~~

`BOOT-INF/classes` là chi tiết cấu trúc archive, không phải prefix của tên resource classpath.

### Không giả định protocol URL của JAR

Tùy Java, Spring Boot loader và cách đóng gói, URL của resource có thể có dạng đặc thù. Không nên so sánh chuỗi URL với `jar:file:...` hoặc giả định luôn có một ký tự phân tách archive ở vị trí cố định. Nếu cần đọc nội dung, dùng `Resource#getInputStream()`; nếu cần URL để truyền cho API khác, xác định rõ API đó có hỗ trợ protocol đang được runtime cung cấp hay không.

## 15. Lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Resource tồn tại khi chạy IDE nhưng mất khi chạy JAR | File không được đóng gói hoặc đường dẫn sai | Đặt trong `src/main/resources` và kiểm tra entry JAR |
| `FileNotFoundException` khi gọi `getFile()` | Resource nằm trong JAR, không phải file thường | Dùng `getInputStream()` hoặc truyền `Resource` cho helper |
| `getResourceAsStream()` trả về null | Sai path, sai chữ hoa/thường hoặc resource không được đóng gói | Kiểm tra path từ classpath root và artifact |
| Đường dẫn có `src/main/resources` không tìm thấy | Dùng đường dẫn source thay cho classpath path | Bỏ prefix source, chỉ dùng `mail/...` |
| Windows chạy được, Linux/JAR thất bại | Sai casing của resource | Khớp chính xác tên file và thư mục |
| Ảnh inline không hiện | Content-ID không khớp, MIME type sai hoặc thứ tự thêm part không phù hợp | So khớp `cid` và `addInline`, thêm sau `setText` |
| Attachment lỗi hoặc rỗng | Stream chỉ đọc một lần hoặc resource đã bị đóng | Dùng resource mở stream mới |
| Resource pattern không tìm thấy trong dependency JAR | Dùng `ResourceLoader` thay vì resolver phù hợp hoặc pattern không khớp | Dùng `PathMatchingResourcePatternResolver` với `classpath*:` |
| Tài nguyên đổi sau khi deploy nhưng ứng dụng vẫn dùng bản cũ | Asset đã đóng gói trong JAR | Chuyển asset ra storage ngoài nếu cần cập nhật độc lập |
| Dùng URL JAR như filesystem path bị lỗi | URL archive không phải File/Path | Dùng stream hoặc sao chép sang temp file khi thật sự cần |

### Phân biệt lỗi đường dẫn và lỗi đọc file

Khi debug, kiểm tra theo thứ tự:

1. Resource path có đúng từ classpath root không?
2. File có được build tool đưa vào output không?
3. Entry có nằm trong JAR cuối cùng không?
4. Runtime class loader có tìm được resource không?
5. `getInputStream()` có đọc được bytes không?
6. `MimeMessageHelper` có nhận đúng resource, content type và Content-ID không?

Không sửa lỗi bằng cách chuyển sang đường dẫn tương đối theo working directory nếu mục tiêu là resource đóng gói trong JAR. Cách đó có thể làm ứng dụng phụ thuộc vị trí khởi chạy và thất bại khi service chạy dưới container hoặc systemd.

## 16. Khi API khác bắt buộc phải có File hoặc Path

Một số thư viện xử lý file chỉ nhận `File` hoặc `Path` thay vì `Resource`. Nếu resource nằm trong JAR, có thể sao chép stream sang file tạm:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import org.springframework.core.io.ClassPathResource;

ClassPathResource resource =
    new ClassPathResource("mail/documents/guide.pdf");

Path temporaryFile =
    Files.createTempFile("mail-guide-", ".pdf");

try (InputStream input = resource.getInputStream()) {
    Files.copy(
        input,
        temporaryFile,
        StandardCopyOption.REPLACE_EXISTING
    );
}

// Gọi thư viện cần Path tại đây.

Files.deleteIfExists(temporaryFile);
~~~

Trong production, nên dùng try/finally hoặc một abstraction quản lý temp file để bảo đảm xóa file ngay cả khi xử lý thất bại. Với luồng gửi email thông thường, bước sao chép này không cần thiết vì `MimeMessageHelper` đã nhận `Resource`.

Không giải nén toàn bộ JAR chỉ để đọc một logo hoặc PDF nhỏ. Chỉ tạo file tạm khi API bên ngoài thật sự yêu cầu filesystem path.

## 17. Quản lý asset classpath và resource ngoài JAR theo môi trường

Một ứng dụng có thể dùng asset mặc định trong JAR nhưng cho phép thay thế bằng file ngoài khi triển khai:

~~~yaml
app:
  mail:
    logo-location: classpath:mail/images/logo.png
~~~

Trong production, cấu hình có thể được override:

~~~yaml
app:
  mail:
    logo-location: file:/opt/my-app/assets/company-logo.png
~~~

Service chỉ biết abstraction:

~~~java
Resource logo = resourceLoader.getResource(
    mailProperties.logoLocation()
);

if (!logo.exists() || !logo.isReadable()) {
    throw new IllegalStateException("Mail logo is unavailable");
}
~~~

Cách này giúp tách logic tạo email khỏi nơi lưu asset. Tuy nhiên, cần có policy rõ ràng:

- Location mặc định nào được phép?
- Ai có quyền thay đổi cấu hình?
- Có cho phép URL remote không?
- File ngoài JAR có được kiểm tra quyền và nội dung không?
- Khi asset bị thay, ứng dụng có cần reload hay tạo resource mới mỗi lần gửi?
- Nếu có nhiều tenant, asset nào thuộc tenant nào?

Không nên để request HTTP tự gửi một location tùy ý. Location nên đến từ cấu hình được kiểm soát hoặc ID asset đã được phân quyền.

## 18. Ghi nhớ khi dùng classpath resource cho email

- Resource trong `src/main/resources` được tham chiếu từ classpath root; bỏ phần `src/main/resources` khỏi tên resource.
- Dùng `ClassPathResource` hoặc `ResourceLoader` để lấy tài nguyên.
- Với resource nằm trong JAR, dùng `getInputStream()` hoặc truyền trực tiếp `Resource` cho `MimeMessageHelper`.
- Không giả định `getFile()` hoạt động; entry trong JAR không phải file filesystem thông thường.
- Với nhiều resource theo pattern, dùng `ResourcePatternResolver` và cân nhắc `classpath*:`.
- Dùng đúng chữ hoa/thường của đường dẫn để tránh lỗi khi deploy trên Linux.
- Resource cần đọc lại được khi thư viện MIME có thể mở stream nhiều lần; `ClassPathResource` phù hợp hơn một stream đã mở và tiêu thụ.
- Khi dùng ảnh inline, Content-ID trong `addInline` phải khớp `cid:...` trong HTML; content type phải đúng.
- Với attachment, tên hiển thị không phải đường dẫn classpath.
- Kiểm tra cả classpath test và executable JAR thực tế để phát hiện resource bị loại khỏi artifact.
- Nếu API bắt buộc nhận `Path`, sao chép stream sang file tạm và quản lý cleanup; không giải nén JAR chỉ để đọc resource.
- Dùng asset trong JAR cho nội dung tĩnh đi cùng release; dùng filesystem/object storage cho asset cần cập nhật độc lập.

Trong Spring Framework Mail, classpath resource giúp email service sử dụng logo, hình ảnh và tài liệu mẫu mà không phụ thuộc vào working directory của tiến trình. Khi giữ resource ở dạng `Resource` từ lúc tìm kiếm đến lúc đưa vào `MimeMessageHelper`, cùng một code có thể chạy trong IDE, thư mục classes và executable JAR mà không cần giả định tài nguyên luôn là một file trên filesystem.
