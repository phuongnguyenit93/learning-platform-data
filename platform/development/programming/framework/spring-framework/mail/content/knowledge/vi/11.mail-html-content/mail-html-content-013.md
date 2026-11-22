# Đo kích thước HTML và ảnh trước khi gửi trong Spring Framework Mail

Email HTML có thể chứa markup, CSS, ảnh nội tuyến, liên kết, bản plain text dự phòng và file đính kèm. Nếu chỉ nhìn số ký tự của template, ứng dụng chưa biết email sẽ nặng bao nhiêu sau khi đóng gói thành MIME và truyền qua SMTP.

Đo kích thước trước khi gửi giúp phát hiện sớm thông điệp vượt giới hạn của nhà cung cấp, tránh tạo message quá lớn, giảm thời gian truyền và kiểm soát bộ nhớ của worker. Trong Spring Framework Mail, nên thực hiện bước này sau khi render nội dung và dựng đủ MIME parts, nhưng trước khi gọi JavaMailSender.send(...).

Cần phân biệt các phép đo:

- **Kích thước HTML**: số byte của chuỗi HTML sau khi encode, thường là UTF-8.
- **Kích thước ảnh**: số byte của file PNG/JPEG/GIF hoặc tài nguyên được nhúng.
- **Kích thước ảnh theo pixel**: chiều rộng và chiều cao; không đồng nghĩa với dung lượng file.
- **Kích thước MIME**: gồm header, body, boundary, transfer encoding, ảnh inline và attachment.
- **Kích thước trên đường SMTP**: có thể khác serialized MIME do framing, line ending, dot-stuffing và cách provider tính giới hạn.

Không có một phép đo duy nhất trả lời mọi câu hỏi. Một quy trình preflight tốt đo từng thành phần, sau đó đo toàn bộ MIME message để so với budget gửi.

## 1. Vì sao phải đo trước khi gửi?

Giả sử ứng dụng tạo email xác nhận đơn hàng gồm HTML khoảng 80 KB, logo PNG nội tuyến 120 KB, ảnh sản phẩm JPEG 900 KB, PDF đính kèm 2 MB và bản plain text khoảng 2 KB. Nếu chỉ đo HTML, ứng dụng có thể nghĩ email rất nhỏ. Nhưng ảnh inline và PDF được đóng gói vào MIME; dữ liệu nhị phân còn có thể được mã hóa Base64 làm dung lượng truyền tăng lên.

Đo trước giúp:

1. Từ chối hoặc thay thế nội dung vượt giới hạn trước khi mở SMTP connection.
2. Resize/nén ảnh trước khi đính kèm.
3. Chuyển file lớn thành link tải có quyền truy cập phù hợp, nếu nghiệp vụ cho phép.
4. Tránh worker giữ nhiều buffer lớn cùng lúc.
5. Ghi nhận template nào tạo email có kích thước bất thường.
6. Giảm nguy cơ provider từ chối do message vượt giới hạn.
7. Xây dựng ngưỡng cảnh báo và thống kê theo loại email.

Nhà cung cấp có thể giới hạn kích thước toàn message, từng attachment, số lượng recipient hoặc header. Vì vậy, đo tổng kích thước là cần thiết nhưng không thay thế việc kiểm tra các giới hạn thành phần.

## 2. Phân biệt ký tự, byte và dung lượng file

Một lỗi thường gặp là dùng String.length() để đo HTML. Phương thức này trả về số UTF-16 code units của chuỗi Java, không phải số byte mà nội dung chiếm khi encode để truyền đi. Ký tự tiếng Việt có dấu hoặc emoji có thể dùng số byte UTF-8 khác nhau.

Đo dung lượng HTML theo UTF-8:

~~~java
import java.nio.charset.StandardCharsets;

String html = "<p>Xin chào khách hàng!</p>";

int characterUnits = html.length();
int utf8Bytes = html.getBytes(StandardCharsets.UTF_8).length;

System.out.println("UTF-16 code units: " + characterUnits);
System.out.println("UTF-8 bytes: " + utf8Bytes);
~~~

Khi Spring Mail sử dụng UTF-8, số byte UTF-8 là phép đo hữu ích cho phần HTML trước khi đóng gói MIME.

Ví dụ với các chuỗi khác nhau:

~~~java
String ascii = "Order confirmed";
String vietnamese = "Đơn hàng đã xác nhận";
String emoji = "Đã giao hàng 📦";

System.out.println(ascii.length());
System.out.println(ascii.getBytes(StandardCharsets.UTF_8).length);

System.out.println(vietnamese.length());
System.out.println(vietnamese.getBytes(StandardCharsets.UTF_8).length);

System.out.println(emoji.length());
System.out.println(emoji.getBytes(StandardCharsets.UTF_8).length);
~~~

Nguyên tắc luôn giống nhau: **đo byte theo charset sử dụng**, không dùng số ký tự để so với giới hạn tính theo byte của nhà cung cấp.

Nếu HTML rất lớn, getBytes(UTF_8) tạo thêm một mảng byte trong bộ nhớ. Với template email thông thường, cách này đơn giản và dễ hiểu. Với nội dung cực lớn, có thể dùng encoder/streaming để hạn chế cấp phát, nhưng vẫn cần cân nhắc việc message cuối cùng phải được dựng và gửi.

### MB và MiB

Khi hiển thị hoặc cấu hình giới hạn, cần ghi rõ đơn vị:

| Đơn vị | Số byte |
| --- | ---: |
| 1 KB (decimal) | 1.000 |
| 1 MB (decimal) | 1.000.000 |
| 1 KiB | 1.024 |
| 1 MiB | 1.048.576 |

Provider ghi giới hạn 25 MB có thể dùng cách tính decimal theo tài liệu của họ. Ứng dụng nên giữ số liệu nội bộ dưới dạng byte (long) và chỉ định dạng thành MB/MiB khi hiển thị. Đừng lấy một ngưỡng “25” mà không biết nó đại diện cho MB hay MiB.

## 3. Đo HTML sau khi render template

HTML cần được đo **sau khi render đầy đủ dữ liệu động**. Template gốc chỉ là mẫu; tên người dùng, bảng đơn hàng, URL, nội dung thông báo và các đoạn điều kiện có thể làm kích thước cuối thay đổi đáng kể.

~~~java
import java.nio.charset.StandardCharsets;

public final class HtmlSize {
    private HtmlSize() {}

    public static long utf8Bytes(String html) {
        if (html == null) {
            throw new IllegalArgumentException("HTML must not be null");
        }
        return html.getBytes(StandardCharsets.UTF_8).length;
    }
}
~~~

Sử dụng với template engine:

~~~java
Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("customerName", customerName);
context.setVariable("orderCode", orderCode);
context.setVariable("items", items);

String html = templateEngine.process("mail/order-confirmed", context);
long htmlBytes = HtmlSize.utf8Bytes(html);
~~~

Phép đo này bao gồm thẻ HTML thực tế được render, inline CSS, văn bản đã escape, URL và các phần tử ẩn nếu template vẫn tạo chúng. Nó **không bao gồm** bytes của ảnh tải từ URL HTTPS, CSS ngoài hoặc font ngoài mà email client tải sau khi nhận thư. Nó cũng chưa bao gồm MIME headers, boundary và transfer encoding.

### Đo cả plain text và HTML

Nếu gửi multipart/alternative, ghi nhận kích thước từng phiên bản:

~~~java
long plainBytes =
    plainText.getBytes(StandardCharsets.UTF_8).length;

long htmlBytes =
    htmlText.getBytes(StandardCharsets.UTF_8).length;

long bodySourceBytes = plainBytes + htmlBytes;
~~~

bodySourceBytes chỉ là tổng byte của hai chuỗi nguồn. Khi đóng gói, MIME thêm header cho từng part, boundary và có thể mã hóa transfer encoding. Không dùng tổng này thay cho kích thước MIME cuối.

### Giới hạn HTML riêng

Ứng dụng có thể đặt ngưỡng để ngăn template bất thường:

~~~java
long maxHtmlBytes = 300_000L; // Ví dụ: 300 KB decimal.

if (htmlBytes > maxHtmlBytes) {
    throw new IllegalArgumentException(
        "Rendered HTML exceeds the configured size limit");
}
~~~

Ngưỡng 300 KB chỉ là ví dụ nội bộ, không phải giới hạn chung của email. Một số email client có thể cắt nội dung HTML ở ngưỡng riêng, nhưng clipping threshold thay đổi theo client và cách tính. Hãy đặt budget dựa trên tập client mục tiêu và thử nghiệm thực tế.

## 4. Đo kích thước file ảnh

Với file ảnh trên filesystem, Files.size(...) trả về dung lượng file theo byte:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

Path imagePath = Path.of("src/main/resources/mail/banner.jpg");
long imageBytes = Files.size(imagePath);

System.out.println("Image bytes: " + imageBytes);
~~~

Nếu file nằm trên classpath và không có đường dẫn file trực tiếp, có thể đọc stream để đếm byte:

~~~java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.Resource;

public final class ResourceSize {
    private ResourceSize() {}

    public static long countBytes(Resource resource) throws IOException {
        long total = 0L;
        byte[] buffer = new byte[8192];

        try (InputStream input = resource.getInputStream()) {
            int read;
            while ((read = input.read(buffer)) != -1) {
                total += read;
            }
        }

        return total;
    }
}
~~~

Ví dụ:

~~~java
Resource logo = new ClassPathResource("mail/logo.png");
long logoBytes = ResourceSize.countBytes(logo);
~~~

Cách đếm stream không cần giữ toàn bộ file trong một mảng byte. Tuy nhiên, khi gửi sau đó, ứng dụng cần mở lại được resource. ClassPathResource hoặc FileSystemResource thường có thể tạo stream mới; một stream đã tiêu thụ hoặc một resource chỉ đọc được một lần không phù hợp với quy trình vừa đo vừa gửi.

### Vì sao không dùng contentLength() cho mọi Resource?

Resource.contentLength() hữu ích nếu resource biết kích thước. Nhưng với một số resource dựa trên stream, remote source hoặc dữ liệu động, kích thước có thể không có sẵn hoặc việc tính toán phải đọc toàn bộ stream. Khi cần con số chắc chắn, dùng Files.size cho file hoặc đọc stream có kiểm soát.

Không nên gọi getContentAsByteArray() chỉ để đo file lớn nếu ứng dụng không cần giữ toàn bộ nội dung trong bộ nhớ. Cách đó tạo một mảng byte tương ứng với toàn bộ file và có thể làm tăng memory pressure khi nhiều email được xử lý đồng thời.

## 5. Kích thước ảnh theo byte khác kích thước ảnh theo pixel

Một ảnh có hai đặc điểm cần quan tâm:

- **Dung lượng file (bytes)**: số byte của file đã nén/mã hóa, ảnh hưởng đến kích thước MIME và thời gian truyền.
- **Kích thước pixel (width × height)**: số pixel cần hiển thị/giải mã, ảnh hưởng đến độ sắc nét, khả năng co giãn và bộ nhớ khi render.

| Ảnh | Dung lượng file | Kích thước pixel | Ý nghĩa |
| --- | ---: | ---: | --- |
| Logo PNG | 90 KB | 600 × 200 | File nhỏ nhưng đủ độ phân giải cho vùng hiển thị |
| Ảnh sản phẩm JPEG | 180 KB | 1200 × 1200 | Có thể hiển thị ở 300 × 300 |
| Banner PNG | 1,8 MB | 2400 × 800 | Có thể quá lớn so với vùng hiển thị |
| GIF động | 2,5 MB | 800 × 450 | Cần xét số frame và kích thước tổng file |

Ảnh 2400 × 800 có 1.920.000 pixel. Nếu giải mã thành bitmap RGBA 4 byte/pixel, vùng pixel thô có thể cần khoảng 7,68 MB, chưa tính overhead và các bản sao trung gian. Kích thước file JPEG nén có thể chỉ vài trăm KB nhưng bộ nhớ khi giải mã lớn hơn nhiều.

Vì vậy, preflight ảnh nên kiểm tra **cả byte length lẫn dimensions**, đặc biệt khi ảnh đến từ người dùng upload hoặc hệ thống xử lý hàng loạt.

### Lấy chiều rộng và chiều cao bằng ImageIO

Với định dạng được ImageIO hỗ trợ như PNG, JPEG và GIF, có thể dùng ImageReader để đọc metadata kích thước mà không cần giải mã toàn bộ ảnh thành BufferedImage:

~~~java
import java.awt.Dimension;
import java.io.IOException;
import java.nio.file.Path;
import java.util.Iterator;
import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.stream.ImageInputStream;

public final class ImageDimensions {
    private ImageDimensions() {}

    public static Dimension read(Path path) throws IOException {
        try (ImageInputStream input =
                 ImageIO.createImageInputStream(path.toFile())) {

            if (input == null) {
                throw new IOException("Cannot open image input");
            }

            Iterator<ImageReader> readers = ImageIO.getImageReaders(input);
            if (!readers.hasNext()) {
                throw new IOException("Unsupported image format");
            }

            ImageReader reader = readers.next();
            try {
                reader.setInput(input, true, true);
                int width = reader.getWidth(0);
                int height = reader.getHeight(0);
                return new Dimension(width, height);
            } finally {
                reader.dispose();
            }
        }
    }
}
~~~

Sau đó kiểm tra giới hạn:

~~~java
Dimension dimensions = ImageDimensions.read(imagePath);
long pixels = (long) dimensions.width * dimensions.height;

if (dimensions.width > 2400
        || dimensions.height > 2400
        || pixels > 4_000_000L) {
    throw new IllegalArgumentException(
        "Image dimensions exceed the configured limit");
}
~~~

Các con số 2400 pixel và 4 triệu pixel chỉ là ví dụ budget. Ứng dụng nên chọn theo thiết kế email, kích thước hiển thị và tài nguyên xử lý.

ImageReader.getWidth(0) và getHeight(0) thường mô tả frame đầu tiên của ảnh nhiều frame. Với GIF động, còn phải quan tâm số frame, thời lượng animation và tổng dung lượng file; không nên chỉ kiểm tra frame đầu rồi coi toàn bộ GIF nhẹ.

Đối với định dạng không có reader sẵn trong JDK, cần thư viện hỗ trợ hoặc chuyển đổi trong pipeline upload. Không giả định ImageIO luôn đọc được mọi định dạng mà trình duyệt có thể hiển thị.

## 6. Phân biệt ảnh từ xa, ảnh inline và attachment

Không phải ảnh xuất hiện trong HTML đều được tính giống nhau vào dung lượng email.

### Ảnh từ URL HTTPS

~~~html
<img src="https://static.example.com/email/logo.png"
     width="120" height="40"
     alt="Logo Example">
~~~

Email chỉ chứa URL và markup tham chiếu. Bytes của file ảnh **không nằm trong MIME message** nếu ảnh được tải từ máy chủ bên ngoài. Email client tải ảnh sau khi nhận thư, nếu chính sách của client cho phép.

- Kích thước HTML có tính độ dài URL và thuộc tính của thẻ img.
- Kích thước MIME không cộng toàn bộ bytes của file ảnh từ xa.
- Ảnh từ xa vẫn ảnh hưởng thời gian hiển thị, quyền riêng tư, caching và khả năng bị chặn.
- URL cần truy cập được từ email client/proxy; không dựa vào cookie đăng nhập của website.
- URL có query string dài vẫn làm tăng kích thước HTML.

Nếu ảnh nằm trên CDN, nên đo và tối ưu ảnh trong **pipeline build/upload asset**. Không nên tải một URL tùy ý do người dùng cung cấp ngay trước khi gửi chỉ để đo, vì có thể tạo SSRF hoặc truy cập tài nguyên nội bộ.

### Ảnh inline bằng Content-ID

Ảnh inline được đóng gói như một MIME part và HTML tham chiếu bằng cid:

~~~html
<img src="cid:brandLogo" alt="Logo Example" width="120">
~~~

Trong Spring Mail:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
    message,
    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
    "UTF-8"
);

helper.setFrom("no-reply@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Thông báo");

String plain = "Thông báo từ Example.";
String html = """
    <html><body>
      <img src="cid:brandLogo" width="120" alt="Logo Example">
      <h1>Thông báo</h1>
    </body></html>
    """;

helper.setText(plain, html);
helper.addInline(
    "brandLogo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);

mailSender.send(message);
~~~

File logo được đưa vào message như part có Content-ID. **Bytes ảnh inline làm tăng kích thước MIME**, dù thẻ HTML chỉ chứa chuỗi cid rất ngắn.

### Attachment

Attachment được thêm qua addAttachment:

~~~java
helper.addAttachment(
    "invoice.pdf",
    new FileSystemResource(invoicePath)
);
~~~

Attachment cũng làm tăng kích thước MIME. Tên file, MIME headers, transfer encoding và dữ liệu nhị phân đều góp phần vào message cuối.

| Thành phần | Nằm trong HTML? | Nằm trong MIME? | Cần đo gì? |
| --- | --- | --- | --- |
| Ảnh HTTPS từ xa | URL và thuộc tính img | Không chứa bytes ảnh | HTML bytes và asset bytes ở CDN |
| Ảnh CID inline | Chuỗi cid | Có image part | File bytes, dimensions, serialized MIME |
| Ảnh attachment | Không nhất thiết | Có attachment part | File bytes và serialized MIME |
| CSS inline | Có | Có trong HTML part | HTML UTF-8 bytes |
| CSS/ảnh từ URL ngoài | URL tham chiếu | Thường không chứa bytes ngoài | HTML bytes và asset host riêng |
| Plain text alternative | Không nằm trong HTML | Có MIME part riêng | Plain-text bytes và MIME size |

Nếu mục tiêu là giảm dung lượng message, thay ảnh CID bằng ảnh HTTPS có thể làm MIME nhẹ hơn. Nhưng cần cân nhắc ảnh ngoài có thể bị chặn, tracking/privacy và độ tin cậy của CDN. Không nên thay đổi chỉ dựa trên một con số mà bỏ qua trải nghiệm người nhận.

## 7. Base64 làm tăng kích thước ảnh và attachment

Các phần nhị phân trong MIME thường được truyền bằng Content-Transfer-Encoding: base64. Base64 biểu diễn mỗi nhóm 3 byte thành 4 ký tự, nên dung lượng cơ bản tăng khoảng một phần ba.

Công thức phần Base64 chưa tính xuống dòng:

~~~text
encodedLength = 4 × ceil(originalBytes / 3)
~~~

Ví dụ file ảnh 900.000 byte:

~~~text
Base64 characters ≈ 4 × ceil(900,000 / 3)
                  = 1,200,000 bytes (ASCII)
~~~

MIME thường xuống dòng dữ liệu Base64 theo các dòng giới hạn độ dài (thường 76 ký tự), nên còn có thêm bytes CRLF. Ngoài ra còn header, boundary và các phần MIME khác.

Có thể ước lượng Base64:

~~~java
public static long base64EncodedLength(long inputBytes) {
    if (inputBytes < 0) {
        throw new IllegalArgumentException("Negative size");
    }
    return 4L * ((inputBytes + 2L) / 3L);
}
~~~

Nếu muốn ước lượng thêm line break ở 76 ký tự:

~~~java
public static long base64WithCrlfEstimate(long inputBytes) {
    long encoded = base64EncodedLength(inputBytes);
    long lines = (encoded + 75L) / 76L;

    // Ước lượng 2 byte CRLF giữa các dòng, không cộng CRLF cuối.
    long lineBreaks = Math.max(0L, lines - 1L) * 2L;
    return encoded + lineBreaks;
}
~~~

Đây là **ước lượng cho dữ liệu Base64**, không phải kích thước MIME chính xác. Thư viện có thể chọn transfer encoding khác cho từng part; header và boundary cũng có overhead. Không dùng hàm này để khẳng định provider sẽ tính message dưới một giới hạn chính xác.

Không phải mọi phần đều Base64:

- Nội dung text có thể được truyền bằng 7bit, quoted-printable hoặc Base64 tùy charset và thư viện.
- HTML có dấu tiếng Việt có thể được encode để bảo đảm truyền đúng.
- Header Subject hoặc display name Unicode có thể được MIME-encode.
- Binary image/PDF thường cần Base64 hoặc encoding phù hợp.
- MIME boundary và header của mỗi part cũng chiếm byte.

Do đó, đo từng file giúp tìm nguồn gây phình dung lượng, còn đo serialized MIME gần với kích thước message đã đóng gói hơn.

## 8. Đo toàn bộ MIME message sau khi dựng helper

Khi đã tạo xong MimeMessage và thêm đủ text, HTML, ảnh inline, attachment, có thể serialize message ra một output stream chỉ đếm byte.

MimeMessage.writeTo(OutputStream) ghi header và các MIME part vào stream. Dùng một OutputStream chỉ đếm mà không giữ dữ liệu sẽ đo được dung lượng serialized mà không tạo thêm mảng byte lớn bằng toàn bộ message.

### CountingOutputStream

~~~java
import java.io.OutputStream;

public final class CountingOutputStream extends OutputStream {
    private long count;

    @Override
    public void write(int value) {
        count++;
    }

    @Override
    public void write(byte[] buffer, int offset, int length) {
        if (length < 0) {
            throw new IndexOutOfBoundsException();
        }
        count += length;
    }

    public long getCount() {
        return count;
    }
}
~~~

Đây là stream bỏ dữ liệu sau khi đếm; nó không lưu bytes. Hàm đo:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;

public final class MimeSize {
    private MimeSize() {}

    public static long serializedBytes(MimeMessage message)
            throws MessagingException, IOException {
        message.saveChanges();

        CountingOutputStream output = new CountingOutputStream();
        message.writeTo(output);

        return output.getCount();
    }
}
~~~

Gọi saveChanges() trước khi serialize giúp hoàn thiện header/MIME metadata mà Jakarta Mail quản lý. Sau đó writeTo ghi message theo cấu trúc MIME đã tạo.

### Giới hạn của phép đo serialized MIME

Con số này là **kích thước serialized message ở thời điểm đo**, hữu ích cho preflight, nhưng không phải lúc nào cũng bằng chính xác số byte provider tính khi nhận SMTP DATA:

- SMTP có framing, kết thúc DATA và dot-stuffing cho một số dòng bắt đầu bằng dấu chấm.
- Transport có thể bổ sung hoặc thay đổi header trong quá trình gửi.
- Provider có thể tính quota theo message size, attachment size hoặc cách riêng.
- Server có thể áp dụng giới hạn riêng cho header, recipient, attachment hoặc nội dung.
- Một số DataSource/Resource chỉ đọc được một lần.
- Nếu message bị sửa sau khi đo, kết quả không còn đại diện cho message cuối.

Vì vậy, so sánh với giới hạn provider cần **margin an toàn** và phải theo tài liệu nhà cung cấp. Nếu provider có API validation hoặc hợp đồng báo trước dung lượng, hãy dùng cơ chế chính thức của họ.

### Cẩn trọng khi đo message có attachment stream

writeTo cần đọc nội dung các MIME part để serialize. Nếu attachment dùng nguồn chỉ đọc một lần, thao tác đo có thể tiêu thụ stream và khiến lần gửi sau không đọc được nữa.

Ưu tiên nguồn có thể mở stream mới mỗi lần như FileSystemResource, ClassPathResource hoặc InputStreamSource được triển khai đúng. Tránh giữ một InputStream đã mở rồi đưa vào cả bước đo lẫn bước gửi.

## 9. Ví dụ preflight trước khi gọi send()

Ví dụ dưới đây đo HTML, logo và MIME message. Ngưỡng là cấu hình minh họa, cần thay theo chính sách ứng dụng/provider.

~~~java
package example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class CampaignMailer {

    private static final long MAX_HTML_BYTES = 300_000L;
    private static final long MAX_LOGO_BYTES = 500_000L;
    private static final long MAX_MIME_BYTES = 8_000_000L;

    private final JavaMailSender mailSender;

    public CampaignMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient, String html, String plainText)
            throws MessagingException, IOException {

        // 1. Đo chuỗi sau khi render.
        long htmlBytes =
            html.getBytes(StandardCharsets.UTF_8).length;

        if (htmlBytes > MAX_HTML_BYTES) {
            throw new IllegalArgumentException(
                "HTML content exceeds configured limit");
        }

        // 2. Đo file inline trước khi tạo message.
        ClassPathResource logo =
            new ClassPathResource("mail/logo.png");

        long logoBytes = ResourceSize.countBytes(logo);
        if (logoBytes > MAX_LOGO_BYTES) {
            throw new IllegalArgumentException(
                "Logo exceeds configured limit");
        }

        // 3. Tạo message và các MIME parts.
        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            StandardCharsets.UTF_8.name()
        );

        helper.setFrom("news@example.com");
        helper.setTo(recipient);
        helper.setSubject("Bản tin mới");
        helper.setText(plainText, html);
        helper.addInline("brandLogo", logo, "image/png");

        // 4. Đo serialized MIME sau khi đã thêm đủ parts.
        long mimeBytes = MimeSize.serializedBytes(message);

        if (mimeBytes > MAX_MIME_BYTES) {
            throw new IllegalArgumentException(
                "Email message exceeds configured size limit");
        }

        // 5. Chỉ gửi sau khi preflight đạt yêu cầu.
        mailSender.send(message);
    }
}
~~~

Trong ví dụ:

- MAX_HTML_BYTES kiểm soát phần HTML nguồn.
- MAX_LOGO_BYTES kiểm soát asset inline độc lập.
- MAX_MIME_BYTES kiểm soát serialized message sau khi dựng MIME.
- Logo được dùng lại bằng resource có thể mở stream mới; phép đếm và bước gửi đọc resource riêng biệt.
- Nếu có attachment, thêm helper.addAttachment(...) trước khi gọi MimeSize.serializedBytes(message) để phép đo bao gồm attachment.

Trong production, nên đưa các ngưỡng vào ConfigurationProperties, ném exception domain phù hợp và ghi nhận metrics/correlation ID thay vì hard-code trong service.

## 10. Đo nhiều ảnh và cộng budget tài nguyên

Một template có thể tham chiếu nhiều ảnh inline. Nên quản lý một danh sách asset gồm tên, MIME type, kích thước file và dimensions.

Ví dụ cấu trúc dữ liệu:

~~~java
public record EmailImageAsset(
    String contentId,
    String resourcePath,
    String contentType,
    long maxBytes,
    int maxWidth,
    int maxHeight
) {}
~~~

Khai báo asset theo template:

~~~java
List<EmailImageAsset> assets = List.of(
    new EmailImageAsset(
        "brandLogo",
        "mail/logo.png",
        "image/png",
        500_000L,
        1200,
        400
    ),
    new EmailImageAsset(
        "productImage",
        "mail/product.jpg",
        "image/jpeg",
        800_000L,
        1600,
        1600
    )
);
~~~

Khi xử lý mỗi asset:

1. Mở resource và đo bytes.
2. Kiểm tra giới hạn dung lượng file.
3. Đọc width/height bằng image metadata reader.
4. Kiểm tra kích thước pixel và loại file được phép.
5. Thêm inline part với Content-ID duy nhất.
6. Ghi nhận bytes theo từng asset để giải thích email nào nặng.

Ví dụ cộng dung lượng file gốc:

~~~java
long totalInlineImageBytes = 0L;

for (EmailImageAsset asset : assets) {
    ClassPathResource resource =
        new ClassPathResource(asset.resourcePath());

    long bytes = ResourceSize.countBytes(resource);

    if (bytes > asset.maxBytes()) {
        throw new IllegalArgumentException(
            "Image exceeds limit: " + asset.resourcePath());
    }

    totalInlineImageBytes += bytes;
}
~~~

totalInlineImageBytes là tổng bytes **file gốc**, chưa phải lượng MIME tăng thêm sau Base64. Nếu cần kiểm soát dung lượng cuối, vẫn phải đo toàn bộ message đã serialize.

### Budget theo từng template

| Nhóm email | HTML budget | Tổng ảnh inline budget | MIME budget |
| --- | ---: | ---: | ---: |
| OTP / thông báo ngắn | 50 KB | 0 | 200 KB |
| Xác nhận đơn hàng | 150 KB | 300 KB | 2 MB |
| Newsletter có banner | 300 KB | 1 MB | 4 MB |
| Hóa đơn có PDF | 150 KB | 300 KB | 8 MB |

Đây chỉ là **budget nội bộ minh họa**, không phải giới hạn chính thức của Gmail, Outlook hay SMTP provider. Mỗi loại email có nhu cầu khác nhau; email OTP thường không cần ảnh, còn newsletter có thể cần banner. Ngưỡng cuối phải thấp hơn giới hạn thực tế của provider đủ để dành chỗ cho encoding và các phần MIME khác.

## 11. Kích thước ảnh hiển thị và cách tối ưu

Một ảnh 2400 × 800 pixel có thể được hiển thị ở 600 × 200 CSS pixel để giữ độ nét trên màn hình mật độ điểm ảnh cao. Tuy nhiên, ảnh 2x cũng có dung lượng và bộ nhớ giải mã lớn hơn. Không nên tải ảnh quá lớn rồi chỉ đặt width="300" trong HTML và nghĩ rằng dung lượng đã giảm.

Các cách giảm dung lượng:

- **Resize thật sự** ảnh về kích thước phù hợp trước khi gửi hoặc đưa lên CDN.
- Chọn định dạng phù hợp: JPEG thường hiệu quả cho ảnh chụp; PNG phù hợp với đồ họa cần transparency hoặc cạnh sắc; GIF chỉ dùng khi cần animation và đã kiểm soát số frame.
- Nén ảnh với chất lượng phù hợp, cân bằng độ nét và bytes.
- Loại bỏ metadata không cần thiết như EXIF khi xử lý asset.
- Dùng biến thể ảnh nhỏ cho email thay vì file gốc từ hệ thống upload.
- Hạn chế ảnh nền lớn và tránh đưa nội dung quan trọng chỉ vào ảnh.
- Với ảnh remote, tối ưu asset trên CDN và đặt kích thước hiển thị trong HTML.

| Định dạng | Thích hợp | Lưu ý |
| --- | --- | --- |
| JPEG | Ảnh chụp, ảnh sản phẩm nhiều màu | Không có transparency; chất lượng nén ảnh hưởng dung lượng |
| PNG | Logo, icon, đồ họa cần trong suốt | File có thể lớn với ảnh chụp |
| GIF | Animation đơn giản, hình ít màu | Dung lượng tăng theo số frame; một số client chỉ hiện frame đầu |
| SVG | Logo/vector sắc nét | Hỗ trợ nhúng/hiển thị không đồng nhất; cần fallback raster |
| WebP/AVIF | Asset web hiện đại | Email client hỗ trợ không đồng đều; cần kiểm tra client mục tiêu |

Đừng chọn định dạng chỉ vì trình duyệt hỗ trợ tốt. Email client có chính sách lọc và khả năng hiển thị khác nhau; PNG/JPEG thường là lựa chọn dễ tương thích hơn cho hình quan trọng.

## 12. Ảnh từ URL ngoài vẫn cần được đo

Ảnh remote không làm tăng trực tiếp kích thước MIME, nhưng vẫn cần budget riêng. Nếu một email tham chiếu 12 ảnh CDN, người nhận có thể phải tải nhiều MB tài nguyên sau khi mở thư.

Nên đo ảnh remote trong pipeline asset để kiểm soát tốc độ hiển thị, chi phí CDN, kích thước pixel, định dạng và khả năng tương thích. Một manifest asset có thể ghi:

~~~json
{
  "name": "newsletter-banner",
  "url": "https://static.example.com/email/banner.jpg",
  "contentType": "image/jpeg",
  "bytes": 182400,
  "width": 1200,
  "height": 400,
  "displayWidth": 600,
  "displayHeight": 200
}
~~~

Đây là dữ liệu do pipeline upload/build asset cung cấp. Ứng dụng gửi mail không cần tự tải lại URL do người dùng đưa vào để lấy kích thước. Nếu bắt buộc kiểm tra remote URL, chỉ cho phép domain tin cậy, giới hạn redirect, thời gian tải, dung lượng response và chặn truy cập IP/private network để tránh SSRF.

URL ảnh cũng có thể làm HTML lớn hơn:

~~~html
<img src="https://cdn.example.com/image?id=123&signature=..."
     alt="Banner">
~~~

Bytes ảnh không nằm trong MIME, nhưng URL dài vẫn làm tăng HTML. Không nhúng token truy cập dài hạn hoặc bí mật vào URL; nếu link ảnh cần ký, giới hạn phạm vi và thời hạn, đồng thời cân nhắc ảnh có thể được proxy/cache bởi email client.

## 13. Tránh đọc toàn bộ ảnh vào bộ nhớ chỉ để đo

Cách viết ngắn sau có thể gây vấn đề:

~~~java
byte[] bytes = resource.getInputStream().readAllBytes();
long size = bytes.length;
~~~

Đoạn này còn thiếu quản lý đóng stream. Quan trọng hơn, nó giữ toàn bộ file trong một mảng byte. Khi gửi hàng trăm email đồng thời với ảnh lớn, nhiều bản sao có thể gây áp lực heap hoặc OutOfMemoryError.

Để đo, đọc stream theo buffer:

~~~java
long count = 0L;
byte[] buffer = new byte[8192];

try (InputStream input = resource.getInputStream()) {
    int read;
    while ((read = input.read(buffer)) != -1) {
        count += read;
    }
}
~~~

Nếu asset là file cục bộ, Files.size(path) thường hiệu quả hơn vì hệ thống file cung cấp metadata.

### Resource phải đọc lại được

Một quy trình đo rồi gửi thường đọc resource ít nhất hai lần:

~~~text
Lần 1: đo kích thước
    Resource -> InputStream -> count bytes -> close

Lần 2: serialize MIME hoặc gửi
    Resource -> InputStream mới -> đọc dữ liệu -> close
~~~

Vì vậy, nguồn attachment nên mở được stream mới mỗi lần. Tránh đưa một stream đã mở vào lambda rồi trả lại chính stream đó nhiều lần:

~~~java
// Không nên: stream này chỉ có thể tiêu thụ một lần.
InputStream input = Files.newInputStream(path);
InputStreamSource source = () -> input;
~~~

Thay vào đó:

~~~java
InputStreamSource source = () -> Files.newInputStream(path);
~~~

Cần bảo đảm file không bị thay đổi giữa lúc đo và lúc gửi. Nếu file có thể thay đổi, lưu một bản snapshot/version hoặc kiểm tra lại size/hash trước khi gửi để tránh preflight đo một file nhưng MIME chứa nội dung khác.

## 14. Đo MIME không có nghĩa đo mọi tài nguyên client tải

Một email có thể chứa:

~~~html
<link rel="stylesheet" href="https://static.example.com/email.css">
<img src="https://static.example.com/logo.png">
<img src="cid:productPhoto">
<a href="https://example.com/order">Xem đơn hàng</a>
~~~

Khi đóng gói:

- Chuỗi HTML và URL được lưu trong HTML part.
- productPhoto được đưa vào MIME như inline part.
- logo.png từ HTTPS không nằm trong MIME.
- CSS ngoài không được đính kèm nếu chỉ tham chiếu URL.
- Liên kết đích không được tải khi gửi, nhưng URL vẫn chiếm byte trong HTML.
- Gateway có thể rewrite URL, làm kích thước message sau xử lý thay đổi.

Serialized MIME là phép đo tốt cho **thông điệp do ứng dụng dựng**, nhưng không phải tổng bytes người nhận tải khi mở email. Muốn tối ưu trải nghiệm, phải quản lý cả asset remote riêng.

### Mô hình budget

~~~text
HTML UTF-8 bytes
+ Plain text UTF-8 bytes
+ Inline image bytes
+ Attachment bytes
+ MIME headers / boundaries / encoding overhead
-----------------------------------------------
= Estimated serialized MIME bytes

Remote images / CSS / fonts:
  = Asset delivery budget riêng, không cộng trực tiếp vào MIME
~~~

Không cộng file ảnh remote vào MIME budget, nhưng cũng không bỏ qua nó trong asset budget.

## 15. Giới hạn của SMTP provider và email client

Nhà cung cấp có thể giới hạn kích thước toàn message, từng attachment, số lượng attachment, số recipient, kích thước header, tốc độ gửi hoặc tổng dung lượng theo ngày/tháng. Các giới hạn khác nhau giữa ESP, SMTP relay và mailbox provider. Có nơi trả lỗi SMTP khi message vượt giới hạn, có nơi API trả lỗi validation.

Ngoài provider, email client còn có giới hạn render/clipping HTML riêng. Một email MIME nhỏ không nhất thiết được hiển thị đầy đủ nếu HTML quá dài hoặc client áp dụng clipping. Ngược lại, HTML khá dài nhưng không có attachment có thể vẫn nằm trong giới hạn message của SMTP.

### Đặt ngưỡng nội bộ thấp hơn giới hạn provider

Nếu provider công bố giới hạn message tối đa, ứng dụng nên dùng **ngưỡng an toàn thấp hơn** để dành chỗ cho MIME encoding, headers, biến đổi gateway và khác biệt trong cách tính.

Ví dụ giả định provider có giới hạn 10 MB decimal, ứng dụng có thể đặt MIME budget 8 MB để dành margin. Con số cụ thể phải dựa vào tài liệu provider và đo thực tế; không lấy ví dụ này làm mặc định.

Nếu nhận lỗi vượt giới hạn, không retry cùng một message không thay đổi. Hãy giảm kích thước ảnh/attachment, chuyển file thành link tải an toàn hoặc chia nội dung theo nghiệp vụ nếu phù hợp.

## 16. Ghi nhận số đo để chẩn đoán email quá lớn

Log preflight nên chứa số đo và ID liên kết, không cần lưu toàn bộ HTML hoặc file:

~~~json
{
  "deliveryId": "d-123",
  "template": "order-confirmed",
  "htmlUtf8Bytes": 84210,
  "plainUtf8Bytes": 1840,
  "inlineImageBytes": 122880,
  "attachmentBytes": 1048576,
  "serializedMimeBytes": 1684200,
  "imageCount": 1,
  "attachmentCount": 1,
  "preflightResult": "accepted"
}
~~~

Các trường này giúp trả lời email nào tăng kích thước bất thường, template nào chứa quá nhiều markup, ảnh nào chiếm phần lớn dung lượng và attachment có làm message vượt budget không.

Không ghi raw HTML, ảnh Base64, dữ liệu cá nhân hoặc nội dung hóa đơn nhạy cảm vào log chỉ để theo dõi kích thước. Có thể ghi bytes, số lượng asset, template version, loại MIME và hash nếu cần đối chiếu mà không lưu nội dung.

Metrics hữu ích:

- email_html_bytes histogram theo template.
- email_inline_asset_bytes theo asset type.
- email_attachment_bytes theo loại file.
- email_serialized_mime_bytes theo loại email/provider.
- email_preflight_rejected_total theo lý do.
- email_send_duration và tỷ lệ provider reject do size.

Dùng percentile (p50/p95/p99) để phát hiện những message lớn bất thường thay vì chỉ nhìn trung bình.

## 17. Một lớp preflight có thể tái sử dụng

Khi nhiều service gửi email, không nên lặp lại logic đo trong từng service. Có thể xây một thành phần hạ tầng chịu trách nhiệm tính budget.

~~~java
public record MailSizeReport(
    long htmlBytes,
    long plainTextBytes,
    long inlineAssetBytes,
    long attachmentBytes,
    long serializedMimeBytes
) {}
~~~

Một policy:

~~~java
public record MailSizeLimits(
    long maxHtmlBytes,
    long maxInlineAssetBytes,
    long maxAttachmentBytes,
    long maxSerializedMimeBytes
) {}
~~~

Một lớp kiểm tra:

~~~java
public class MailSizePolicy {

    private final MailSizeLimits limits;

    public MailSizePolicy(MailSizeLimits limits) {
        this.limits = limits;
    }

    public void validate(MailSizeReport report) {
        if (report.htmlBytes() > limits.maxHtmlBytes()) {
            throw new MailSizeLimitException("HTML is too large");
        }

        if (report.inlineAssetBytes() > limits.maxInlineAssetBytes()) {
            throw new MailSizeLimitException(
                "Inline assets exceed the configured limit");
        }

        if (report.attachmentBytes() > limits.maxAttachmentBytes()) {
            throw new MailSizeLimitException(
                "Attachments exceed the configured limit");
        }

        if (report.serializedMimeBytes()
                > limits.maxSerializedMimeBytes()) {
            throw new MailSizeLimitException(
                "Serialized email exceeds the configured limit");
        }
    }
}
~~~

MailSizeLimitException là exception domain do ứng dụng định nghĩa. Có thể dùng ConfigurationProperties để bind limits từ cấu hình:

~~~yaml
app:
  mail:
    size:
      max-html-bytes: 300000
      max-inline-asset-bytes: 1000000
      max-attachment-bytes: 5000000
      max-serialized-mime-bytes: 8000000
~~~

Các giá trị là ví dụ. Cần xác định chúng dựa trên giới hạn provider và mục tiêu vận hành.

Kiến trúc:

~~~text
Template renderer
      |
      v
Rendered HTML + plain text
      |
      v
Asset resolver / image metadata
      |
      v
MimeMessage builder
      |
      v
Size estimator + policy
      |
      +---- vượt budget ----> từ chối / tối ưu / link tải
      |
      v
JavaMailSender.send(message)
~~~

Lớp policy không cần biết SMTP host hay credential. Nó chỉ nhận báo cáo kích thước và quyết định message có nằm trong budget nội bộ hay không.

## 18. Tối ưu khi email vượt budget

Khi email vượt ngưỡng, có nhiều cách xử lý tùy nội dung:

### 18.1. Resize hoặc nén ảnh

Nếu banner có kích thước 3000 × 1000 nhưng hiển thị ở 600 × 200, tạo asset 1200 × 400 hoặc kích thước hợp lý khác trước khi nhúng. Chọn định dạng và mức nén phù hợp.

### 18.2. Dùng ảnh từ CDN thay vì CID

Nếu hình không bắt buộc phải đi cùng email, có thể tham chiếu URL HTTPS. Điều này giảm MIME size, nhưng ảnh có thể bị chặn hoặc không tải được. Giữ alt và không đặt thông tin cốt lõi chỉ trong ảnh.

### 18.3. Chuyển attachment lớn thành link tải

Thay vì đính kèm PDF lớn, ứng dụng có thể gửi URL tới trang tải tài liệu. Link cần HTTPS, kiểm tra quyền truy cập, thời hạn hoặc token có phạm vi phù hợp. Không đặt URL công khai dài hạn nếu tài liệu chứa dữ liệu riêng tư.

### 18.4. Rút gọn markup và CSS

Loại bỏ HTML không sử dụng, CSS lặp, comment build không cần thiết và nội dung ẩn không có mục đích. Giữ fallback và markup dễ đọc; không minify tới mức khó bảo trì nếu không có pipeline kiểm soát.

### 18.5. Tách nội dung dài sang website

Email có thể tóm tắt thông tin quan trọng và dẫn tới trang chi tiết. Không cần gửi toàn bộ báo cáo nhiều trang trong HTML nếu người nhận chỉ cần biết kết quả và nơi xem thêm.

### 18.6. Chia message theo nghiệp vụ

Nếu cần gửi nhiều tài liệu riêng, có thể gửi các email độc lập hoặc tạo một trang tải nhiều file. Không chia email tùy tiện nếu người nhận cần một thông điệp thống nhất; mỗi message cần ID, subject và ngữ cảnh rõ ràng.

## 19. Những sai lầm thường gặp khi đo kích thước

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Dùng String.length() để so với giới hạn byte | Đếm UTF-16 code units, không phải UTF-8 bytes | getBytes(UTF_8).length |
| Chỉ đo HTML và bỏ qua ảnh CID | Ảnh inline nằm trong MIME message | Đo asset riêng và serialized MIME |
| Cộng ảnh remote vào MIME size | Bytes ảnh ngoài không nằm trong message | Theo dõi remote asset budget riêng |
| Cộng file gốc và coi đó là MIME size | Base64, header, boundary làm tăng kích thước | Serialize MimeMessage để ước lượng |
| Chỉ đo pixel, không đo bytes | Ảnh có thể nhiều pixel nhưng nén nhỏ hoặc ngược lại | Theo dõi cả bytes và dimensions |
| Chỉ đo bytes, không đo dimensions | Ảnh nhỏ file nhưng giải mã rất lớn | Giới hạn width, height và pixel count |
| Đọc toàn bộ file vào byte[] để đếm | Tăng memory, dễ gây áp lực heap | Files.size hoặc stream counting |
| Đo stream rồi dùng lại stream đã tiêu thụ | Lần gửi không đọc được resource | Resource phải mở được stream mới |
| Đo MIME trước khi thêm attachment | Con số thiếu các part quan trọng | Đo sau khi dựng đầy đủ MIME |
| Thay message sau khi đo | Số đo không còn đại diện message cuối | Đo sau bước build cuối cùng |
| Cho rằng serialized MIME bằng chính xác SMTP wire size | Transport còn framing/dot-stuffing và provider policy | Dùng làm preflight estimate với margin |
| Dùng một ngưỡng size cho mọi loại email | Newsletter, OTP và PDF có nhu cầu khác nhau | Budget theo template/use case |
| Gửi lại ngay khi provider từ chối vì quá lớn | Message không thay đổi vẫn sẽ bị từ chối | Tối ưu nội dung trước khi gửi lại |

## 20. Quy trình preflight trước khi gửi email

Một quy trình triển khai có thể diễn ra như sau:

1. **Render template** với dữ liệu thực tế của người nhận.
2. **Đo HTML và plain text** theo UTF-8 bytes.
3. **Kiểm tra từng ảnh**: byte length, MIME type, width, height, pixel count; với GIF cần xét cả animation.
4. **Kiểm tra attachment**: dung lượng, định dạng được phép và giới hạn nghiệp vụ.
5. **Tạo MimeMessage** và thêm tất cả parts bằng MimeMessageHelper.
6. **Serialize message để đo** tổng MIME bytes bằng counting stream.
7. **So với budget nội bộ** và giới hạn provider có margin.
8. Nếu vượt, **tối ưu hoặc từ chối có lý do rõ ràng**, không gửi message chưa đạt policy.
9. Nếu đạt, gọi JavaMailSender.send(message).
10. **Ghi metrics và delivery ID** để đối soát lỗi provider.

~~~text
Render template
     |
     v
Measure HTML / plain text bytes
     |
     v
Inspect image and attachment assets
     |
     v
Build complete MimeMessage
     |
     v
Serialize and count MIME bytes
     |
     v
Within application/provider budget?
     |
   +--+--+
   |     |
  No    Yes
   |     |
   v     v
Optimize, reject,   JavaMailSender.send()
or create link             |
                           v
                   Record submission result
~~~

Preflight là kiểm tra trước gửi; nó không thay thế phản hồi SMTP thực tế. Provider vẫn có thể từ chối vì quota, policy, sender authentication, recipient hoặc các giới hạn không chỉ dựa trên size.

## 21. Ghi nhớ

Khi đo kích thước HTML và ảnh trước khi gửi, hãy dùng đúng đơn vị và đo đúng lớp dữ liệu:

- **HTML**: dùng số byte UTF-8 sau khi render, không dùng String.length().
- **Ảnh**: đo bytes của file và kích thước pixel; hai chỉ số phục vụ hai mục tiêu khác nhau.
- **Ảnh remote**: URL nằm trong HTML nhưng bytes ảnh không được tính vào MIME message; quản lý asset budget riêng.
- **Ảnh CID và attachment**: được đóng gói vào MIME, thường tăng dung lượng khi Base64 encode.
- **Toàn bộ message**: dựng đủ MIME parts rồi serialize MimeMessage vào counting stream để có số đo preflight gần với message được gửi.
- **Resource**: phải đọc lại được nếu quy trình đo và gửi cùng truy cập một asset; tránh giữ toàn bộ file lớn trong heap chỉ để đếm.
- **Giới hạn**: dùng budget riêng cho HTML, ảnh, attachment và MIME tổng; đặt margin so với provider và kiểm tra client mục tiêu.
- **Vận hành**: ghi kích thước và template/delivery ID để tìm nguyên nhân message lớn mà không lưu nội dung nhạy cảm.

Trong Spring Framework Mail, MimeMessageHelper giúp xây nội dung và tài nguyên email, còn việc đo kích thước nên được tổ chức thành bước preflight trước JavaMailSender.send(...). Khi biết rõ phần nào chiếm dung lượng, ứng dụng có thể tối ưu ảnh, rút gọn HTML hoặc chuyển tài liệu sang link tải trước khi SMTP provider từ chối thông điệp.
