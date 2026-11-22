# Kích thước MIME sau mã hóa khác với kích thước tệp gốc

## 1. Vì sao file nhỏ hơn giới hạn vẫn có thể gửi email thất bại?

Khi ứng dụng **Spring Framework Mail** gửi tệp đính kèm, kích thước file gốc trên ổ đĩa thường **khác** kích thước thông điệp **MIME** được gửi qua SMTP. Dữ liệu nhị phân thường được biểu diễn bằng **Base64** để đi qua hệ thống email tương thích. Base64 tăng số byte; sau đó MIME cần thêm dấu xuống dòng, header từng phần, boundary của multipart, nội dung thân thư và các header của thông điệp.

Ví dụ, một file PDF **10 MiB** (10.485.760 byte) được đóng gói dưới dạng Base64 MIME, ngắt dòng 76 ký tự và dùng CRLF giữa các dòng, có phần dữ liệu được mã hóa dài **14.348.936 byte** (khoảng **13,68 MiB**). Kích thước ấy **chưa bao gồm** header MIME, các boundary và nội dung email. Vì vậy, kiểm tra mỗi kích thước file gốc không đủ để biết SMTP server có chấp nhận thư hay không.

Những tình huống thường gặp:

- Người dùng đính kèm file nhỏ hơn 20 MiB nhưng SMTP server giới hạn **tổng thông điệp** ở 20 MiB.
- Một email có nhiều file nhỏ, tổng dung lượng gốc có vẻ hợp lệ nhưng sau Base64 vượt hạn mức.
- Email HTML có ảnh nhúng và cả phiên bản text/plain, nên tổng các phần MIME lớn hơn nội dung được hiển thị.
- Ứng dụng upload file thành công, nhưng bước gửi mail tiếp theo gặp phản hồi “message too large”.

Điểm mấu chốt là phải phân biệt **byte file gốc**, **byte phần dữ liệu sau Content-Transfer-Encoding**, và **byte toàn bộ email đã serialize**.

## 2. MIME chứa nhiều phần ngoài nội dung file

MIME (Multipurpose Internet Mail Extensions) mô tả cách email mang nội dung có charset khác nhau, nhiều body part và tệp nhị phân. File đính kèm trở thành một **MIME body part**, có header khai báo loại nội dung, tên file và cách mã hóa khi vận chuyển.

Ví dụ thông điệp rút gọn, chỉ minh họa cấu trúc:

~~~mime
From: reports@example.com
To: recipient@example.net
Subject: Monthly report
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="example-boundary"

--example-boundary
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 7bit

Your report is attached.
--example-boundary
Content-Type: application/pdf; name="report.pdf"
Content-Disposition: attachment; filename="report.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQKJUVPRgo=
--example-boundary--
~~~

Chuỗi Base64 chỉ mô tả vài byte, không phải một tài liệu PDF hoàn chỉnh. Trong email chuẩn, dòng được kết thúc bằng **CRLF**, tức hai byte 0x0D và 0x0A. Ví dụ trên còn lược bỏ các header mà máy chủ có thể thêm và các lớp multipart lồng nhau.

| Thành phần | Có trong file gốc? | Có trong thông điệp MIME? |
|---|---|---|
| Dữ liệu nhị phân ban đầu | Có | Được biểu diễn qua transfer encoding |
| Ký tự Base64 | Không | Có nếu part dùng Base64 |
| CRLF ngắt dòng Base64 | Không | Có |
| Content-Type, Content-Disposition, Content-Transfer-Encoding | Không | Có |
| Tên file được mã hóa trong MIME header | Là metadata về file | Có |
| Header From, To, Subject, Date, Message-ID... | Không | Có |
| Nội dung text/plain, text/html, ảnh nhúng | Không thuộc attachment đang xét | Có nếu được thêm vào thư |
| Multipart boundary và dòng trống | Không | Có |

Do đó, **kích thước attachment không phải kích thước message**. Ngoài tổng message, một dịch vụ còn có thể giới hạn số file, dung lượng từng file, số người nhận và tổng dung lượng nhận theo tài khoản.

## 3. Công thức Base64: từ 3 byte thành 4 ký tự

Base64 chuyển mỗi **3 byte** dữ liệu (24 bit) thành **4 ký tự ASCII**, mỗi ký tự biểu diễn 6 bit. Nếu dữ liệu cuối không đủ 3 byte thì dùng ký tự đệm **=** để hoàn tất nhóm 4 ký tự.

~~~text
3 byte gốc (24 bit)
        |
        v
4 nhóm, mỗi nhóm 6 bit
        |
        v
4 ký tự Base64 (4 byte ASCII)
~~~

Ví dụ:

~~~text
Man -> TWFu   (3 byte thành 4 ký tự)
Ma  -> TWE=   (2 byte thành 4 ký tự)
M   -> TQ==   (1 byte thành 4 ký tự)
~~~

Với **n** là số byte file gốc, số ký tự Base64 thuần là:

\[
B(n) = 4\left\lceil \frac{n}{3} \right\rceil
\]

**B(n)** cũng là số byte nếu các ký tự Base64 được biểu diễn bằng ASCII, chưa tính việc chia dòng. Khi n chia hết cho 3, tỷ lệ là **4/3**, tức khoảng **33,33% lớn hơn dữ liệu gốc**. Với file rất nhỏ, do phải đệm nhóm 4 ký tự, tỷ lệ tăng có thể cao hơn: 1 byte thành 4 byte nghĩa là tăng 300%.

**Base64 không phải thuật toán nén hay mã hóa bảo mật.** Ai có dữ liệu Base64 đều có thể khôi phục byte ban đầu. Nó được dùng vì khả năng biểu diễn dữ liệu nhị phân bằng tập ký tự ASCII an toàn cho giao thức email truyền thống.

## 4. MIME Base64 còn thêm CRLF để ngắt dòng

Khi được dùng làm **Content-Transfer-Encoding: base64** trong MIME, các dòng dữ liệu mã hóa phải **không dài hơn 76 ký tự**, không tính CRLF kết thúc dòng. CRLF là **2 byte**, vì vậy phần Base64 thực tế trên đường truyền thường lớn hơn con số B(n).

Với cách đóng gói thông dụng, mỗi dòng tối đa 76 ký tự và **không có CRLF thừa ở cuối phần dữ liệu**, ta tính:

\[
L = \left\lceil \frac{B}{76} \right\rceil
\]

Trong đó **L** là số dòng khi B > 0. Có **L − 1** khoảng ngăn giữa các dòng, nên kích thước phần dữ liệu Base64 đã gấp dòng là:

\[
E = B + 2(L-1)
\]

Nếu file rỗng (n = 0) thì B = 0, E = 0. Cách serialize cụ thể có thể thêm một CRLF cuối dữ liệu trước multipart boundary, làm thay đổi thêm 2 byte; phần này và các boundary vẫn thuộc lớp MIME bao quanh. Do đó công thức **E** là công thức cho **dữ liệu Base64 và CRLF nằm giữa các dòng**, không phải tổng kích thước email.

Hai ví dụ nhỏ:

~~~text
n = 57 byte
B = 4 * ceil(57 / 3) = 76 ký tự
L = 1 dòng
E = 76 byte

n = 58 byte
B = 4 * ceil(58 / 3) = 80 ký tự
L = 2 dòng
E = 80 + 2 = 82 byte
~~~

Tăng một byte gốc đôi khi làm phát sinh cả nhóm Base64 mới và một CRLF mới, vì thế kích thước tăng theo **bước rời rạc**.

## 5. Tính thử với file 1 MiB và 10 MiB

**MB** và **MiB** là hai đơn vị khác nhau:

- **1 MB** theo hệ thập phân là **1.000.000 byte**.
- **1 MiB** theo hệ nhị phân là **1.048.576 byte**.

Các API đọc file trong Java, như Files.size(path), trả về **số byte**, nên nên tính giới hạn bằng byte rồi mới đổi đơn vị hiển thị.

### File 1 MiB

~~~text
n = 1.048.576 byte
B = 4 * ceil(1.048.576 / 3) = 1.398.104 byte
L = ceil(1.398.104 / 76) = 18.397 dòng
CRLF giữa dòng = (18.397 - 1) * 2 = 36.792 byte
E = 1.398.104 + 36.792 = 1.434.896 byte
~~~

### File 10 MiB

~~~text
n = 10.485.760 byte
B = 4 * ceil(10.485.760 / 3) = 13.981.016 byte
L = ceil(13.981.016 / 76) = 183.961 dòng
CRLF giữa dòng = (183.961 - 1) * 2 = 367.920 byte
E = 13.981.016 + 367.920 = 14.348.936 byte
~~~

| File gốc | Base64 chưa gấp dòng | Base64 MIME gấp dòng, không có CRLF cuối | Ghi chú |
|---|---:|---:|---|
| 3 byte | 4 byte | 4 byte | Đủ một nhóm |
| 57 byte | 76 byte | 76 byte | Vừa một dòng |
| 58 byte | 80 byte | 82 byte | Cần thêm CRLF |
| 1 MiB | 1.398.104 byte | 1.434.896 byte | Chưa tính header/boundary |
| 10 MiB | 13.981.016 byte | 14.348.936 byte | Chưa tính header/boundary |

Với file đủ lớn, phép xấp xỉ nhanh là:

\[
\frac{4}{3} \times \frac{78}{76}
= \frac{26}{19}
\approx 1{,}36842
\]

Nghĩa là **dữ liệu Base64 MIME** có thể lớn hơn file gốc khoảng **36,84%** khi dùng dòng 76 ký tự ngăn nhau bằng CRLF. Hệ số này là **ước lượng**: file ngắn chịu ảnh hưởng của padding, vị trí xuống dòng; toàn email còn có nhiều phần khác.

## 6. Khi email có nhiều part, kích thước sẽ cộng dồn

Một email có thể có **multipart/mixed** chứa nội dung văn bản và nhiều attachment, trong khi một phần thân thư khác dùng **multipart/alternative** để chứa cả text/plain và text/html.

~~~text
multipart/mixed
|
+-- multipart/alternative
|   +-- text/plain
|   +-- text/html
|
+-- application/pdf  (attachment, base64)
|
+-- image/jpeg       (attachment, base64)
|
+-- image/png        (inline image, base64 nếu được dùng)
~~~

Các part text/plain và text/html đều có thể nằm trong thư, dù client chỉ hiển thị một phiên bản. Một ảnh nhúng trong HTML vẫn tiêu tốn dung lượng nếu nội dung ảnh được đóng gói thành MIME part.

Nếu ba file nhị phân lần lượt có kích thước **4 MiB**, **3 MiB** và **2 MiB**, tổng file gốc là **9 MiB**. Dùng hệ số gần đúng cho Base64 MIME, tổng dữ liệu các part đính kèm đã vào khoảng **12,32 MiB**, chưa tính header, boundary và body text. Vì vậy phải **cộng kích thước tất cả part** thay vì chỉ kiểm tra file lớn nhất.

Tên file có Unicode, ví dụ **Báo cáo quý.pdf**, có thể cần biểu diễn bằng tham số MIME được mã hóa và gấp dòng header. Điều này khiến header trên đường truyền dài hơn số ký tự hiển thị. Chi phí ấy thường nhỏ hơn Base64 của file lớn nhưng vẫn quan trọng khi email ở sát ngưỡng cho phép.
## 7. Không phải mọi nội dung MIME đều dùng Base64

MIME cho phép mỗi part khai báo **Content-Transfer-Encoding** khác nhau. Cơ chế thực tế tùy kiểu nội dung, byte bên trong và thư viện/hạ tầng SMTP hỗ trợ.

| Encoding | Cách biểu diễn | Ảnh hưởng đến kích thước |
|---|---|---|
| **7bit** | Nội dung tuân thủ yêu cầu byte 7-bit và độ dài dòng của thư | Không tăng theo Base64, nhưng vẫn có CRLF/header |
| **8bit** | Body có thể chứa byte 8-bit khi transport hỗ trợ phù hợp | Không có hệ số Base64; vẫn phải tuân thủ quy tắc liên quan |
| **quoted-printable** | Giữ nhiều ký tự ASCII dễ đọc, byte cần mã hóa được biểu diễn dạng =HH | Thay đổi theo dữ liệu; có thể tăng mạnh với nhiều byte không phải ASCII |
| **base64** | Mã hóa dữ liệu thành ký tự ASCII | Khoảng 33,33% trước gấp dòng, gần 36,84% với file lớn và dòng 76 ký tự |
| **binary** | Giữ dữ liệu nhị phân theo transport được hỗ trợ | Không thể mặc định dùng qua đường SMTP 7-bit truyền thống |

Không nên lấy hệ số **1,36842** nhân cho **toàn bộ email**. Một đoạn text/plain ASCII ngắn có thể dùng 7bit và tăng rất ít; text/html tiếng Việt có thể được mã hóa theo quoted-printable hoặc Base64; file PDF hoặc ảnh đính kèm thường được đóng gói Base64.

Ví dụ quoted-printable:

~~~text
Một byte dữ liệu cần escape: E1
Biểu diễn quoted-printable: =E1

1 byte được biểu diễn bằng 3 ký tự ASCII.
~~~

Quoted-printable còn có **soft line break** để xuống dòng theo giới hạn định dạng; chi phí này phụ thuộc nội dung. Với văn bản chứa nhiều byte UTF-8 cần escape, quoted-printable có thể lớn hơn Base64. Nhưng khi văn bản phần lớn là ASCII, nó có thể tiết kiệm hơn Base64 và vẫn dễ đọc bằng mắt.

### MIME không phải là nén

Base64 làm dữ liệu lớn hơn vì mục đích tương thích khi truyền, không phải để thu nhỏ file. Nén ZIP có thể giảm kích thước **trước khi đính kèm**, nếu dữ liệu có khả năng nén; sau đó file ZIP vẫn có thể được biểu diễn dưới dạng Base64 MIME.

~~~text
File nguồn
    |
    +-- Đính kèm trực tiếp --> MIME encoding --> dữ liệu gửi
    |
    +-- Nén thành ZIP ------> MIME encoding --> dữ liệu gửi
~~~

File CSV hoặc log nhiều dòng lặp có thể nén tốt. File JPEG, PNG, MP4, ZIP hay nội dung đã nén thường ít lợi ích khi nén lại; đôi khi file ZIP mới còn lớn hơn. Việc có nén hay không nên phụ thuộc loại file, yêu cầu nghiệp vụ và khả năng người nhận mở nội dung.

## 8. SMTP server tính giới hạn kích thước ở đâu?

Có nhiều giới hạn độc lập trong luồng gửi thư:

| Lớp | Dữ liệu thường bị giới hạn | Ví dụ hệ quả |
|---|---|---|
| **HTTP upload** | Byte của HTTP request/multipart upload gửi vào ứng dụng | File không upload được, mặc dù chưa hề tạo email |
| **Ứng dụng Spring** | File gốc, số attachment, tổng kích thước dự kiến của email | Ứng dụng trả lỗi trước khi gọi JavaMailSender |
| **SMTP submission server** | Kích thước toàn bộ thông điệp SMTP, cùng quota và chính sách gửi | SMTP từ chối thư khi vượt ngưỡng |
| **SMTP relay/MX phía nhận** | Kích thước thư đích sẵn sàng nhận, chính sách theo miền/người nhận | Thư đã được submission chấp nhận nhưng có thể không phát được về sau |
| **Mailbox/message store** | Quota hoặc quy tắc lưu trữ | Giao thư có thể thất bại khi lưu vào mailbox |

SMTP có phần mở rộng **SIZE**, cho phép server quảng bá kích thước message tối đa mà nó sẵn sàng nhận, và cho phép client khai báo kích thước dự kiến.

Ví dụ phiên SMTP rút gọn:

~~~smtp
C: EHLO app.example.com
S: 250-mail.example.net
S: 250-SIZE 20971520
S: 250-STARTTLS
S: 250 AUTH PLAIN LOGIN
~~~

Giá trị **20.971.520 byte = 20 MiB** là ví dụ về khả năng/chính sách tại **máy chủ SMTP đang kết nối**. Máy chủ có thể áp dụng ngưỡng thấp hơn theo tài khoản, địa chỉ gửi hoặc người nhận; khả năng nhận ở một hop không bảo đảm các hop sau có cùng ngưỡng. Đối với SMTP gửi đi, kích thước liên quan là thông điệp đã mã hóa/gắn header mà SMTP server cần tiếp nhận, không đơn giản là Files.size của attachment.

Một phản hồi lỗi kích thước có thể có dạng:

~~~text
552 5.3.4 Message size exceeds fixed maximum message size
~~~

Mã và câu chữ thực tế khác nhau giữa các hệ thống. Khi sử dụng **email API qua HTTP**, lỗi có thể là **413 Payload Too Large** nếu request HTTP quá lớn. Provider có thể đo giới hạn trên HTTP JSON, trên tổng byte tệp được giải mã hoặc trên email MIME sau khi dựng; không được giả định ba đại lượng này bằng nhau.

### Giới hạn 20 MiB không cho phép đính kèm file 20 MiB

Nếu một provider giới hạn **toàn email 20 MiB** thì một attachment gốc 20 MiB được gửi bằng Base64 MIME sẽ có phần dữ liệu khoảng **27,37 MiB**, trước cả header/body. Nó vượt giới hạn.

Ước lượng ngân sách ngược cho **một attachment lớn**:

\[
\text{Raw budget} \approx
\frac{\text{Message budget}}{1{,}36842}
\]

Với hạn mức 20 MiB, số byte gốc lý thuyết dành cho riêng một part Base64 khoảng **14,6 MiB**, trước khi trừ chỗ cho toàn bộ header, nội dung thư và những part khác. Đây là **mức ước lượng để lập kế hoạch**, không phải cam kết provider chấp nhận một file đúng bằng ngưỡng đó.

Khi đặt giới hạn ứng dụng, nên dùng **headroom** vì multipart thực tế, charset, filename, chữ ký và những header có thể tăng kích thước thông điệp. Với dịch vụ có nhiều provider, giới hạn cần dựa vào chính sách từng provider hoặc mức thấp nhất của các đích cần phục vụ.

## 9. Spring Framework Mail tạo attachment MIME như thế nào?

Trong Spring, **JavaMailSender** sử dụng **Jakarta Mail** để tạo và gửi **MimeMessage**. **MimeMessageHelper** hỗ trợ tạo email multipart, HTML và attachment mà không phải tự viết các dòng boundary hay header MIME.

Ví dụ gửi một PDF qua SMTP:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ReportMailService {
    private final JavaMailSender mailSender;

    public ReportMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReport(String recipient, Path file)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, StandardCharsets.UTF_8.name());

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Monthly report");
        helper.setText("Your report is attached.", false);
        helper.addAttachment(
                file.getFileName().toString(),
                new FileSystemResource(file.toFile()));

        mailSender.send(message);
    }
}
~~~

**FileSystemResource** cho phép Jakarta Mail đọc file khi cần đóng gói và gửi dữ liệu. Nó **không có nghĩa** SMTP sẽ truyền attachment dưới dạng byte gốc. Thư viện lựa chọn Content-Transfer-Encoding phù hợp với body part, thường là Base64 đối với dữ liệu nhị phân.

Một số điểm triển khai cần nhớ:

1. **MimeMessageHelper(message, true, ...)** tạo hỗ trợ multipart.
2. **addAttachment(...)** thêm nội dung file cùng filename và metadata MIME.
3. **MimeMessage** được serialize thành header, boundary, body part và dữ liệu đã mã hóa.
4. **JavaMailSender.send()** thành công nghĩa là quá trình gửi ở mức submission đã hoàn tất tương ứng; không khẳng định người nhận đã mở thư.
5. Nếu gửi bất đồng bộ, file phải còn tồn tại và giữ nguyên nội dung trong thời gian worker đọc; khi retry có thể phải mở stream lại.

Với file lớn, không nên tự tạo **byte[]** chứa toàn bộ file chỉ để tính kích thước rồi mới đính kèm nếu có thể dùng resource phù hợp. Đọc file lớn vào RAM cùng với việc tạo toàn bộ MIME trong bộ nhớ có thể tăng rủi ro thiếu heap. Đo/ước lượng kích thước bằng byte và stream sẽ phù hợp hơn với tài nguyên hạn chế.

## 10. Viết hàm Java ước lượng Base64 MIME bằng số nguyên

Khi biết một attachment sẽ dùng Base64 và dòng dài tối đa 76 ký tự, có thể tính chính xác **B** và **E** theo công thức ở trên mà không phải tạo file mã hóa.

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public final class MimeBase64Size {
    private MimeBase64Size() {
    }

    public static long estimateBodyBytes(long rawBytes) {
        if (rawBytes < 0) {
            throw new IllegalArgumentException("Negative file size");
        }
        if (rawBytes == 0) {
            return 0;
        }

        // ceil(rawBytes / 3), avoiding rawBytes + 2 overflow.
        long groups = rawBytes / 3;
        if (rawBytes % 3 != 0) {
            groups = Math.addExact(groups, 1);
        }

        long base64Chars = Math.multiplyExact(groups, 4);

        // CRLF only between Base64 lines, not a trailing CRLF.
        long lineSeparators = (base64Chars - 1) / 76;
        long crlfBytes = Math.multiplyExact(lineSeparators, 2);

        return Math.addExact(base64Chars, crlfBytes);
    }

    public static void main(String[] args) throws Exception {
        Path path = Path.of("report.pdf");
        long rawBytes = Files.size(path);
        long encodedBodyBytes = estimateBodyBytes(rawBytes);

        System.out.println("File bytes: " + rawBytes);
        System.out.println("Estimated Base64 MIME bytes: "
                + encodedBodyBytes);
    }
}
~~~

**Math.multiplyExact** và **Math.addExact** phát hiện tràn số long thay vì âm thầm tạo kết quả sai. Hàm trên chỉ tính **dữ liệu Base64 và CRLF giữa các dòng**. Nó chưa tính header, phần CRLF cuối body, boundary, HTML, text/plain hay file đính kèm khác; đồng thời giả định thư viện dùng Base64 và cách xuống dòng tương ứng.

Với nhiều file, có thể cộng số byte ước lượng:

~~~java
long totalBase64BodyBytes = 0;
for (Path attachment : attachments) {
    long size = Files.size(attachment);
    totalBase64BodyBytes = Math.addExact(
            totalBase64BodyBytes,
            MimeBase64Size.estimateBodyBytes(size));
}
~~~

**totalBase64BodyBytes** là tổng chi phí của những phần attachment Base64, **không phải kích thước của MimeMessage đầy đủ**. Việc lấy tổng này so với giới hạn SMTP cần cộng thêm phần dự phòng cho các thành phần khác.

## 11. Đo số byte của MimeMessage thực sự được serialize

Khi email gần sát ngưỡng, ước lượng theo hệ số là chưa đủ. Có thể dựng **MimeMessage**, gọi **saveChanges()** để hoàn tất một số header, rồi ghi ra **OutputStream chỉ đếm byte**. Cách này không cần giữ toàn bộ message trong một ByteArrayOutputStream.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;
import java.io.OutputStream;

public final class MimeMessageBytes {
    private MimeMessageBytes() {
    }

    public static long count(MimeMessage message)
            throws MessagingException, IOException {
        message.saveChanges();
        CountingOutputStream counter = new CountingOutputStream();
        message.writeTo(counter);
        return counter.getCount();
    }

    private static class CountingOutputStream extends OutputStream {
        private long count;

        @Override
        public void write(int value) {
            count = Math.addExact(count, 1);
        }

        @Override
        public void write(byte[] bytes, int offset, int length) {
            if (bytes == null) {
                throw new NullPointerException("bytes");
            }
            if (offset < 0 || length < 0
                    || offset > bytes.length - length) {
                throw new IndexOutOfBoundsException();
            }
            count = Math.addExact(count, length);
        }

        long getCount() {
            return count;
        }
    }
}
~~~

Sau khi thêm toàn bộ body và attachment vào MimeMessage, có thể gọi:

~~~java
long serializedBytes = MimeMessageBytes.count(message);
long providerLimit = 20L * 1024 * 1024;

if (serializedBytes > providerLimit) {
    throw new IllegalArgumentException(
            "Email MIME exceeds configured size limit");
}

mailSender.send(message);
~~~

Đây là **đo byte MIME được serialize ở thời điểm hiện tại**. Nó có giá trị cao hơn việc chỉ dựa trên file gốc, nhưng vẫn có giới hạn:

- Quá trình gửi hoặc một MTA có thể thêm/thay đổi header; provider cũng có thể áp dụng quy tắc tính khác.
- Những byte thuộc cơ chế SMTP trên đường truyền (ví dụ xử lý transparency/dot-stuffing) không nên đánh đồng với kích thước nội dung MIME.
- Phép đếm phải **đọc lại file** để serialize, tốn I/O và thời gian; cần bảo đảm attachment ổn định trong suốt thời gian đếm và gửi.
- Nếu MimeMessage bị sửa sau phép đếm, số byte vừa đo không còn đại diện cho thông điệp mới.

Vì vậy, nên **ước lượng nhanh bằng kích thước file gốc** để lọc trước các trường hợp chắc chắn quá lớn, chỉ **serialize để đếm** khi cần gần giới hạn, đồng thời dành headroom cho hạ tầng SMTP thực tế.
## 12. Kiểm soát giới hạn email theo từng bước trong ứng dụng

Quy trình có upload file và gửi email nên được tách thành các điểm quyết định:

~~~mermaid
flowchart TD
    A[Người dùng chọn attachment] --> B[Đọc byte file gốc]
    B --> C{Đủ điều kiện upload?}
    C -- Không --> X[Trả lỗi về giới hạn upload]
    C -- Có --> D[Ước lượng Base64 và các part dự kiến]
    D --> E{Trong ngưỡng message có dự phòng?}
    E -- Không --> Y[Đề nghị giảm kích thước hoặc dùng link tải]
    E -- Có --> F[Tạo MimeMessage và các MIME part]
    F --> G{Cần đo byte serialize?}
    G -- Có --> H[Đếm byte MIME hoàn chỉnh]
    G -- Không --> I[Gửi bằng JavaMailSender]
    H --> J{Trong ngưỡng được phép?}
    J -- Không --> Y
    J -- Có --> I
    I --> K[SMTP server chấp nhận hoặc trả lỗi]
~~~

### Giới hạn lúc upload

Một HTTP endpoint có thể chặn file dựa trên kích thước request hoặc cấu hình multipart của ứng dụng. Đây là giới hạn phục vụ **tiếp nhận dữ liệu**, không phải giới hạn email. File upload thành công vẫn có thể vượt giới hạn SMTP sau khi được mã hóa. Ngược lại, việc có SMTP provider cho phép thư 25 MiB không đồng nghĩa HTTP server nên nhận file vô hạn.

### Giới hạn khi xây dựng MIME

Đối với một email có nhiều attachment, cần cộng từng body đã mã hóa cùng text/plain, text/html, inline image, boundary và header. Có thể đặt ngưỡng gốc nội bộ thấp hơn giới hạn của provider để dành khoảng dự phòng. Nếu một provider đổi chính sách kích thước hoặc ứng dụng thêm chữ ký HTML, ảnh logo và attachment mới, ngân sách MIME cũng phải được cập nhật.

### Giới hạn khi gửi đến SMTP server

Khi SMTP server báo giới hạn kích thước, ứng dụng nên ghi nhận lỗi rõ nghĩa và **không retry vô hạn** cùng một message không thay đổi. Một lỗi quá lớn mang tính cố định thường sẽ không tự biến mất sau vài giây. Nhưng nếu lỗi là tạm thời và server dùng mã phản hồi tương ứng, chính sách retry phải dựa trên **mã phản hồi và ngữ nghĩa thực tế**, không chỉ từ chuỗi thông báo lỗi.

### Giới hạn ở máy chủ người nhận

Ngay cả sau khi **JavaMailSender.send()** thành công ở SMTP submission, server phía nhận có thể từ chối ở hop tiếp theo do thông điệp quá lớn hoặc vi phạm chính sách. Vì vậy, việc ứng dụng tự đo byte là một phần của kiểm soát lỗi **trước khi gửi**, không thay thế trạng thái phát thư, bounce, DSN hoặc webhook từ dịch vụ email.

## 13. Ví dụ trình bày kích thước cho người dùng

Giả sử dịch vụ SMTP cho phép tối đa **20 MiB cho tổng email**. Người dùng chọn một PDF 10 MiB:

~~~text
Tên file:                        report.pdf
Kích thước file gốc:            10,00 MiB
Phần Base64 MIME dự kiến:        13,68 MiB
Nội dung thư + header:           Chưa cộng
Giới hạn tổng email:             20,00 MiB

Kết quả: Có thể tiếp tục xây dựng MIME để kiểm tra giới hạn.
~~~

Sau đó người dùng chọn thêm một ảnh gốc 7 MiB:

~~~text
File PDF gốc:                   10 MiB
File ảnh gốc:                    7 MiB
Tổng file nguồn:                17 MiB

Base64 MIME PDF xấp xỉ:        13,68 MiB
Base64 MIME ảnh xấp xỉ:         9,58 MiB
                                ---------
Tổng hai phần đính kèm:        23,26 MiB

Chưa cộng header/body.
Giới hạn tổng email:           20,00 MiB

Kết quả: Không gửi dưới dạng một email đính kèm như hiện tại.
~~~

Ứng dụng có thể đề xuất giảm kích thước file, nén một loại file phù hợp hoặc gửi **liên kết tải tệp** thay vì attachment. Khi dùng link, cần bảo đảm chỉ đúng người được cấp quyền xem file, link có hạn sử dụng phù hợp, có cơ chế thu hồi và thỏa mãn chính sách bảo mật dữ liệu. Việc chia một email thành nhiều email cũng có thể gây bất tiện cho người nhận và cần được quyết định theo yêu cầu nghiệp vụ.

Một thông báo tốt không nên chỉ nói “file quá lớn” nếu file gốc thực tế vẫn nằm dưới giới hạn upload. Có thể ghi:

> Tổng dung lượng email sau khi đóng gói tệp đính kèm dự kiến vượt giới hạn 20 MiB của dịch vụ gửi mail. Hãy giảm kích thước tệp hoặc sử dụng liên kết chia sẻ.

## 14. Những nhầm lẫn thường gặp

**“Base64 luôn làm tăng đúng 33%.”** Không hoàn toàn. Tỷ lệ 4/3 là tỷ lệ cơ bản của Base64 khi số byte chia hết cho 3. MIME còn ngắt dòng bằng CRLF và phần cuối có thể cần padding, nên body dữ liệu của file lớn thường tăng gần 36,84% với cách gấp dòng 76 ký tự.

**“Tên file dài hơn sẽ làm dữ liệu file Base64 lớn hơn.”** Tên file không ảnh hưởng số byte Base64 tính từ nội dung file; nó ảnh hưởng độ dài **MIME header** chứa filename. Header có Unicode hoặc cần gấp dòng có thể dài hơn.

**“Chọn UTF-8 là giảm được kích thước attachment.”** Charset UTF-8 dùng để biểu diễn văn bản. Nó không làm cho PDF, ảnh, file ZIP hay dữ liệu nhị phân khác tự nhỏ đi. MIME Content-Transfer-Encoding giải quyết vấn đề khác với charset.

**“Chỉ cần dùng Java String.length() để biết dung lượng.”** Java String.length() đếm đơn vị UTF-16, không phải số byte của email. Nếu nội dung text phải chuyển thành UTF-8, quoted-printable hoặc Base64 thì độ dài byte còn thay đổi. Với toàn message nên dựa vào dữ liệu serialize thành byte.

**“Kích thước HTTP multipart/form-data bằng kích thước email MIME.”** Không. Chúng là hai lớp đóng gói khác nhau. HTTP upload còn có boundary/header của request; email dùng MIME và có thể mã hóa nội dung qua Base64. Với email API JSON nhúng Base64, kích thước request JSON cũng khác kích thước MIME cuối cùng của email.

**“File ZIP được Base64 sẽ nhỏ hơn.”** ZIP có thể đã nén được dữ liệu nguồn trước đó, nhưng **Base64 của file ZIP** vẫn dài hơn số byte ZIP gốc. Base64 không phải phép nén.

**“Cộng dung lượng từng file bằng phép nhân 1,37 luôn đủ.”** Phép nhân chỉ là ước lượng gần đúng cho phần Base64 của file lớn. Email còn có text, HTML, inline images, MIME header, filename, boundary và các encoding khác. Khi gần giới hạn phải có dự phòng hoặc đo MIME serialize.

**“SMTP chấp nhận rồi thì server đích chắc chắn nhận được.”** Chấp nhận tại SMTP submission chỉ là mốc máy chủ gửi đã nhận trách nhiệm xử lý thư. Việc phát đi qua những máy chủ khác có thể gặp giới hạn kích thước hoặc quota khác.

## 15. Từ file upload đến MIME: mô hình số liệu cần giữ tách biệt

Khi quan sát log hoặc theo dõi job gửi mail, nên dùng tên đại lượng rõ ràng:

| Đại lượng | Ý nghĩa | Dùng để làm gì? |
|---|---|---|
| **rawAttachmentBytes** | Kích thước file gốc trên đĩa | Hạn chế upload, lưu trữ, kiểm tra file nguồn |
| **estimatedEncodedBodyBytes** | Ước lượng Base64 hoặc transfer encoding của một part | Cảnh báo trước khi tạo MIME |
| **estimatedMessageBytes** | Tổng ước lượng của các part và overhead | Lập ngân sách gửi và đặt headroom |
| **serializedMimeBytes** | Byte của MimeMessage tại một lần serialize xác định | Kiểm tra gần giới hạn cho message cụ thể |
| **providerReportedSize** | Kích thước theo định nghĩa của nhà cung cấp | Đối chiếu phản hồi/hạn mức provider |

Không nên đặt tất cả các đại lượng dưới một tên chung như **fileSize**. Khi file upload 10 MiB và email bị từ chối ở hạn mức 12 MiB, log chỉ ghi “fileSize=10” sẽ không giải thích được tại sao bị từ chối.

Ví dụ log nghiệp vụ đã loại bỏ nội dung nhạy cảm:

~~~text
mailRequestId=mail-2048
attachmentCount=2
rawAttachmentBytes=17825792
estimatedEncodedBodyBytes=24400000
serializedMimeBytes=24402620
configuredMessageLimitBytes=20971520
result=REJECTED_BY_APPLICATION_SIZE_POLICY
~~~

Các giá trị encoded và serialized trong ví dụ mang tính minh họa. Thực tế cần tính và ghi đúng số đo, giữ các identifier để tương quan với kết quả SMTP, đồng thời hạn chế log filename, địa chỉ hoặc nội dung nhạy cảm nếu không cần thiết.

## 16. Công thức và cách áp dụng trong Spring Mail

Nếu một attachment **n byte** chắc chắn được mã hóa **Base64 MIME** với tối đa **76 ký tự mỗi dòng**, không có CRLF thừa ở cuối phần dữ liệu:

~~~text
B = 4 * ceil(n / 3)         // Số byte Base64 trước gấp dòng
L = ceil(B / 76)            // Số dòng Base64 khi B > 0
E = B + 2 * (L - 1)         // Base64 + CRLF giữa dòng

Đối với n = 0: E = 0
Đối với file lớn: E xấp xỉ n * 1,36842
~~~

Với toàn thông điệp:

~~~text
MIME message bytes =
    Message headers
  + MIME part headers
  + Encoded body of each MIME part
  + Multipart boundary and CRLF
  + Other included body parts
~~~

**Trong Spring Framework Mail, hãy kiểm tra dung lượng file gốc bằng byte, dự trù chi phí mã hóa và phần overhead của MIME, rồi đối chiếu với giới hạn tổng email của SMTP provider.** Khi dữ liệu sát hạn mức, có thể đo số byte **MimeMessage** sau khi serialize. Lỗi phát sinh tại SMTP vẫn cần được xử lý riêng theo mã phản hồi và trạng thái phát thư, vì “kích thước phù hợp trước khi gửi” không phải bảo đảm email đã đến mailbox đích.
