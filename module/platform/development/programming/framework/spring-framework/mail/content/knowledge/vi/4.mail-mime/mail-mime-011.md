# Thứ tự các phần và khả năng tương thích mail client

Email không chỉ gồm một chuỗi HTML. Khi cần có **bản văn bản thuần**, **HTML**, **ảnh hiển thị ngay trong nội dung** và **tệp đính kèm**, thông điệp email được tổ chức thành nhiều phần theo chuẩn **MIME** (Multipurpose Internet Mail Extensions). Cách chọn loại `multipart/*`, thứ tự các phần và cách lồng chúng quyết định mail client có thể chọn nội dung phù hợp, hiển thị ảnh đúng chỗ và nhận diện attachment hay không.

Trong **Spring Framework Mail**, `JavaMailSender` gửi thông điệp, còn `MimeMessage` và `MimeMessageHelper` giúp xây dựng cấu trúc MIME. Bài học này tập trung vào **thứ tự các phần** và ảnh hưởng của chúng lên khả năng tương thích giữa các ứng dụng đọc email.

## 1. Đọc một thông điệp MIME như một cái cây

Một email có các header ở cấp thông điệp, chẳng hạn `From`, `To` và `Subject`. Phần thân có thể là một nội dung duy nhất hoặc là **cấu trúc gồm nhiều MIME part**. Mỗi part có thể có `Content-Type`, `Content-Disposition`, `Content-ID` và phần dữ liệu riêng.

Ví dụ:

```text
Email
├── Header thông điệp: From, To, Subject, ...
└── Body: multipart/mixed
    ├── Part 1: multipart/related
    │   ├── Part 1.1: multipart/alternative
    │   │   ├── Part 1.1.1: text/plain
    │   │   └── Part 1.1.2: text/html
    │   └── Part 1.2: image/png; Content-ID: <logo>
    └── Part 2: application/pdf; attachment; filename="report.pdf"
```

Ý nghĩa:

- `multipart/alternative`: các cách biểu diễn **thay thế nhau** của cùng một nội dung, thường là văn bản thuần và HTML.
- `multipart/related`: các phần **liên quan để trình bày cùng một nội dung**, ví dụ HTML có tham chiếu tới hình ảnh qua `cid:...`.
- `multipart/mixed`: ghép những thành phần tương đối độc lập, thường là **phần nội dung chính và tệp đính kèm**.

Các loại `multipart/*` mang **ngữ nghĩa khác nhau**. Không thể tùy ý thay `alternative` bằng `mixed` hoặc dàn phẳng toàn bộ part rồi mong mọi mail client tự hiểu.

## 2. `multipart/alternative`: thứ tự từ biểu diễn đơn giản đến biểu diễn giàu hơn

Một thông điệp thông báo có thể chứa cùng một thông tin ở hai dạng:

1. `text/plain`: người nhận có thể đọc khi không hỗ trợ HTML hoặc muốn đọc bản plain text.
2. `text/html`: bản thể hiện đầy đủ hơn với định dạng, đường dẫn và bố cục.

Quy ước MIME cho `multipart/alternative` là **đặt các phương án theo thứ tự tăng dần độ trung thực của biểu diễn**, thường là **plain text trước, HTML sau**. Mail client có thể chọn phương án cuối cùng mà nó hiểu và được phép hiển thị, thay vì trình bày cả hai như hai email riêng.

```text
multipart/alternative
├── 1. text/plain     ← phương án cơ bản, xuất hiện trước
└── 2. text/html      ← phương án giàu định dạng, xuất hiện sau
```

Ví dụ cấu trúc MIME minh họa (đã lược bỏ một số header và chi tiết mã hóa):

```text
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="alt-demo"

--alt-demo
Content-Type: text/plain; charset=UTF-8

Xin chào!
Xem đơn hàng tại https://example.com/orders/123

--alt-demo
Content-Type: text/html; charset=UTF-8

<html>
  <body>
    <p>Xin chào!</p>
    <p><a href="https://example.com/orders/123">Xem đơn hàng</a></p>
  </body>
</html>

--alt-demo--
```

Đoạn trên chỉ nhằm minh họa thứ tự và cách phân chia part; MIME thực tế do Jakarta Mail tạo còn có các header mã hóa truyền tải phù hợp với nội dung.

**Hai bản phải truyền đạt cùng một thông tin nghiệp vụ.** Nếu bản HTML có đường dẫn xác nhận, điều kiện giao dịch hoặc thông tin quan trọng mà bản plain text không có, người dùng chọn chế độ chỉ đọc văn bản sẽ mất thông tin.

### Điều gì xảy ra nếu đảo ngược thứ tự?

Giả sử phần `text/html` đứng trước phần `text/plain`. Một client tuân theo thứ tự ưu tiên của `multipart/alternative` có thể chọn bản text sau cùng, dù nó hỗ trợ HTML. Một số client khác có cách xử lý riêng. Vì vậy, thứ tự sai có thể gây khác biệt giữa các client.

**Không có quy tắc “HTML luôn được chọn”.** MIME mô tả các phương án và thứ tự ưu tiên; quyết định cuối cùng còn tùy khả năng, cài đặt, chính sách bảo mật và cơ chế render của mail client.

## 3. `multipart/related`: HTML và tài nguyên hiển thị cùng nhau

Một email HTML có thể tham chiếu tới ảnh nằm ngay trong cùng thông điệp:

```html
<p>Xin chào!</p>
<img src="cid:brandLogo" alt="Logo thương hiệu">
```

`cid:brandLogo` là tham chiếu đến MIME part có header `Content-ID` tương ứng:

```text
Content-Type: image/png
Content-ID: <brandLogo>
Content-Disposition: inline
```

Mail client có thể tìm part ảnh theo Content-ID và dùng nó để dựng HTML. Thông thường cấu trúc này được đặt trong `multipart/related`:

```text
multipart/related
├── text/html                ← phần gốc (root), tham chiếu cid:brandLogo
└── image/png                ← Content-ID: <brandLogo>
```

Ở đây thứ tự có ý nghĩa về khả năng tương thích. Theo cấu trúc MIME related, **phần gốc** có thể được xác định bằng tham số `start`; nếu không có tham số này, **part đầu tiên** thường được xem là root. Vì vậy, với cấu trúc đơn giản, nên để **phần nội dung HTML chính trước**, sau đó mới thêm các inline resource được nó tham chiếu.

Lưu ý:

- HTML dùng `cid:brandLogo`, còn MIME header chứa `Content-ID: <brandLogo>`; dấu ngoặc nhọn ở header là cú pháp của Content-ID.
- `Content-ID` phải khớp với tham chiếu `cid:`; lỗi chính tả khiến ảnh không hiển thị.
- `Content-Disposition: inline` thể hiện ý định hiển thị trong nội dung, nhưng **không bảo đảm** mail client sẽ dựng ảnh tại vị trí mong muốn.
- Ảnh inline có thể bị mail client hiển thị thêm trong danh sách attachment, nhất là khi cấu trúc MIME không phù hợp hoặc client có quy tắc riêng.
- Ảnh tải từ URL ngoài (`https://...`) không phải inline MIME resource; chính sách chặn ảnh ngoài, proxy ảnh và quyền riêng tư của mail client có thể ảnh hưởng đến ảnh đó.

Với Spring, một lưu ý thực tế là **gọi `setText(...)` trước `addInline(...)`**. `MimeMessageHelper` cũng khuyến nghị thứ tự này để tránh một số mail reader xử lý tham chiếu tới ảnh inline không đúng.

## 4. `multipart/mixed`: tệp đính kèm là phần tách biệt

Khi gửi kèm PDF hoặc tài liệu tải về, cấu trúc phổ biến là `multipart/mixed` ở ngoài cùng:

```text
multipart/mixed
├── Nội dung email chính
└── application/pdf
    ├── Content-Disposition: attachment
    └── filename="report.pdf"
```

Part đính kèm thường có `Content-Disposition: attachment` và tên file. Phần thân chính được đặt trước để các client dễ xác định đâu là nội dung cần hiển thị và đâu là tệp đính kèm.

Đừng xem mọi part trong `multipart/mixed` là những phương án thay thế nhau: chúng là **các thành phần cùng tồn tại**. Nếu đặt `text/plain` và `text/html` thành hai phần ngang hàng trực tiếp của `multipart/mixed`, có mail client có thể hiển thị cả hai hoặc coi một phần là attachment. Muốn chọn **một trong hai**, phải lồng chúng trong `multipart/alternative`.

### Trường hợp có cả plain, HTML, ảnh inline và PDF

Đây là cấu trúc thường gặp và phù hợp với cách xây dựng của `MimeMessageHelper` khi chọn `MULTIPART_MODE_MIXED_RELATED`:

```text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html (có <img src="cid:brandLogo">)
│   └── image/png; Content-ID: <brandLogo>; inline
└── application/pdf; attachment; filename="report.pdf"
```

Trong cấu trúc này:

- `mixed` bên ngoài phân biệt nội dung chính với tệp đính kèm.
- `related` gom nội dung hiển thị và ảnh đi kèm.
- `alternative` nhóm bản văn bản và bản HTML theo thứ tự ưu tiên.
- PDF là part attachment độc lập ở cấp `mixed`.

Một biến thể MIME khác là:

```text
multipart/mixed
├── multipart/alternative
│   ├── text/plain
│   └── multipart/related
│       ├── text/html
│       └── image/png; Content-ID: <brandLogo>
└── application/pdf; attachment
```

Biến thể này gom toàn bộ phiên bản HTML và tài nguyên của nó vào một alternative. Khi xây dựng email bằng Spring Mail, không cần tự tay sắp xếp các boundary hoặc ép mọi cấu trúc phải trùng một hình vẽ. Điều quan trọng là giữ đúng **ngữ nghĩa của từng nhóm MIME**, rồi kiểm tra kết quả trên các mail client mục tiêu.

## 5. Spring Framework Mail tạo cấu trúc MIME thế nào?

Spring Mail thường dùng:

- `JavaMailSender`: tạo và gửi `MimeMessage`.
- `MimeMessageHelper`: đặt người nhận, tiêu đề, body văn bản/HTML, tài nguyên inline và attachment.
- `MimeMessageHelper.MULTIPART_MODE_*`: chọn cách tổ chức multipart bên trong thư.

### 5.1. Chọn chế độ multipart phù hợp

`MimeMessageHelper` cung cấp các chế độ chính:

| Chế độ | Cấu trúc tổng quát | Khi cân nhắc |
|---|---|---|
| `MULTIPART_MODE_NO` | Không khởi tạo multipart | Email chỉ có một body đơn giản, không inline resource hay attachment. |
| `MULTIPART_MODE_MIXED` | Một `multipart/mixed` ở cấp gốc | Dùng khi muốn gom nhiều thành phần nhưng cần thận trọng với các client có thể hiểu inline resource thành attachment. |
| `MULTIPART_MODE_RELATED` | Một `multipart/related` ở cấp gốc | Phù hợp với nhóm nội dung có tài nguyên liên quan; cách thể hiện attachment độc lập có thể thay đổi tùy client. |
| `MULTIPART_MODE_MIXED_RELATED` | `multipart/mixed` bên ngoài, `multipart/related` bên trong | Lựa chọn thực dụng khi vừa có nội dung/ảnh inline vừa có attachment; đây là cấu trúc được Spring khuyến nghị cho nhiều tình huống. |

Ví dụ:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
    message,
    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
    "UTF-8"
);
```

Constructor `new MimeMessageHelper(message, true, "UTF-8")` dùng chế độ multipart mặc định của helper (thường là `MIXED_RELATED` trong các phiên bản Spring Framework hiện đại), nhưng chỉ rõ constant trong ví dụ học tập sẽ giúp nhìn ra chủ đích cấu trúc.

Không có cấu trúc MIME nào bảo đảm hiển thị hoàn toàn giống nhau trên tất cả mail client. Chọn chế độ là bước **thiết kế thông điệp**; kiểm tra trên các client và môi trường nhận thực tế vẫn là bước cần thiết trước khi triển khai email quan trọng.

### 5.2. Ví dụ hoàn chỉnh: plain text + HTML + logo inline + PDF

Giả sử ứng dụng Spring Boot đã cấu hình `JavaMailSender` qua `spring-boot-starter-mail` và thông tin máy chủ SMTP. Hai tài nguyên nằm trong classpath:

```text
src/main/resources/
└── mail/
    ├── brand-logo.png
    └── report.pdf
```

Dịch vụ gửi mail:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ReportEmailService {

    private final JavaMailSender mailSender;

    public ReportEmailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReport(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Báo cáo tháng");

        String plainText = """
                Báo cáo tháng của bạn đã sẵn sàng.
                Xem tệp report.pdf đính kèm.
                """;

        String htmlText = """
                <html>
                  <body>
                    <img src="cid:brandLogo" alt="Logo" width="120">
                    <h1>Báo cáo tháng</h1>
                    <p>Báo cáo tháng của bạn đã sẵn sàng.</p>
                    <p>Xem tệp <strong>report.pdf</strong> đính kèm.</p>
                  </body>
                </html>
                """;

        // Đặt body trước để helper tạo alternative đúng vị trí.
        helper.setText(plainText, htmlText);

        // cid:brandLogo phải khớp với Content-ID của ảnh inline.
        helper.addInline(
                "brandLogo",
                new ClassPathResource("mail/brand-logo.png"),
                "image/png"
        );

        // Attachment thuộc nhóm mixed, tách khỏi nội dung hiển thị.
        helper.addAttachment(
                "report.pdf",
                new ClassPathResource("mail/report.pdf"),
                "application/pdf"
        );

        mailSender.send(message);
    }
}
```

Ở đây, thứ tự gọi API thể hiện ý định:

1. Khởi tạo `MimeMessage` và helper ở chế độ có hai tầng `mixed/related`.
2. Đặt header và **hai biến thể nội dung** bằng `setText(plainText, htmlText)`; helper tạo `multipart/alternative` với plain trước, HTML sau.
3. Gọi `addInline(...)` sau `setText(...)` để đưa logo vào nhóm related và liên kết nó qua `cid:brandLogo`.
4. Gọi `addAttachment(...)` để thêm PDF như tệp đính kèm, độc lập với ảnh inline.
5. Gửi qua `JavaMailSender`, để Jakarta Mail lo việc chuẩn hóa MIME, mã hóa nội dung và trao đổi SMTP.

Ví dụ dùng tài nguyên tĩnh để dễ quan sát. Trong ứng dụng thực tế, tệp báo cáo có thể được tạo động bằng `ByteArrayResource` hoặc nguồn dữ liệu phù hợp. Cần bảo đảm tài nguyên có thể được đọc khi thư viện gửi thư thực sự ghi nội dung MIME ra kết nối.

### 5.3. Chỉ có plain text và HTML, không cần inline hay attachment

Khi chỉ có hai bản nội dung, `multipart/alternative` vẫn hữu ích:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("notifications@example.com");
helper.setTo("user@example.org");
helper.setSubject("Xác nhận đăng ký");

helper.setText(
        "Đăng ký thành công. Truy cập https://example.com/account",
        "<p>Đăng ký thành công. " +
        "<a href=\"https://example.com/account\">Mở tài khoản</a></p>"
);

mailSender.send(message);
```

`setText(plain, html)` là overload được thiết kế để tạo **các nội dung thay thế**. Trái lại, `setText(html, true)` chỉ đặt nội dung HTML và không tự sinh bản plain text có chất lượng tương đương. Nếu muốn hỗ trợ tốt các trình đọc text-only, hãy cung cấp bản plain text thực sự.

## 6. Các header MIME khác cũng ảnh hưởng khả năng hiển thị

Thứ tự là một phần của cấu trúc; **Content-Type**, charset và disposition giúp client hiểu từng part.

| Header / thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| `Content-Type` | Loại nội dung hoặc cấu trúc multipart | `text/plain`, `text/html`, `image/png`, `multipart/alternative` |
| `charset` | Bộ mã ký tự của phần văn bản | `charset=UTF-8` |
| `boundary` | Chuỗi phân tách các phần của một multipart | `boundary="mix-123"` |
| `Content-Disposition` | Gợi ý hiển thị inline hoặc dưới dạng attachment | `inline`, `attachment; filename="report.pdf"` |
| `Content-ID` | Định danh MIME part để tham chiếu từ HTML | `<brandLogo>` |
| `Content-Transfer-Encoding` | Cách mã hóa payload để truyền tải qua hệ thống thư | `quoted-printable`, `base64`, `7bit` |

Với nội dung tiếng Việt, hãy chọn UTF-8 ngay khi tạo helper. Thư viện mail thường quyết định `quoted-printable` hoặc `base64` phù hợp; không nên tự nối boundary hoặc tự mã hóa chuỗi nếu không thật sự cần can thiệp cấp MIME thấp.

`Content-Disposition` và tên file giúp client nhận ra attachment, nhưng nhiều client còn suy luận dựa trên `Content-Type`, vị trí trong cây, Content-ID và chính sách tải tệp của chúng. Vì vậy, một tệp ảnh có `inline` vẫn có thể xuất hiện trong danh sách đính kèm của vài client; đây không phải lúc nào cũng là lỗi của `JavaMailSender`.

## 7. Khả năng tương thích giữa các mail client

Các mail client có engine render HTML, chính sách bảo mật và cách trình bày attachment khác nhau. Ngoài ứng dụng cụ thể, **phiên bản, hệ điều hành, cấu hình doanh nghiệp và đường đi qua gateway** cũng có thể làm thay đổi kết quả.

| Tình huống | Biểu hiện có thể gặp | Cách thiết kế để tương thích hơn |
|---|---|---|
| Client ưu tiên plain text hoặc tắt HTML | Chỉ thấy văn bản, không có bố cục HTML | Luôn tạo bản `text/plain` mang đủ thông tin và đường dẫn cần thiết. |
| HTML đứng trước plain trong `alternative` | Một số client chọn bản text thay vì HTML | Đặt `text/plain` trước `text/html`. |
| HTML và plain là hai part trực tiếp trong `mixed` | Client hiển thị lặp nội dung hoặc coi một part như tệp đính kèm | Lồng hai bản vào `multipart/alternative`. |
| Ảnh CID được đưa sai nhóm hoặc Content-ID không khớp | Ảnh bị vỡ, chỉ thấy alt text, hoặc hiện như attachment | Dùng `multipart/related`, `cid:...` khớp ID và thêm inline sau khi đặt body. |
| Email dùng ảnh tải từ Internet | Ảnh chưa hiển thị đến khi người nhận cho phép tải | Không đặt thông tin quan trọng chỉ trong ảnh; dùng alt text và body văn bản. |
| HTML dùng CSS phức tạp hoặc script | Giao diện khác nhau hoặc bị lược bỏ | Viết HTML email đơn giản, CSS tương thích, tránh phụ thuộc JavaScript. |
| Có nhiều file hoặc tên file chứa ký tự quốc tế | Tên file/biểu tượng attachment khác nhau theo client | Dùng API helper và encoding phù hợp, thử nghiệm với các tên file mục tiêu. |
| Thư có dung lượng lớn | Bị nhà cung cấp từ chối, cắt ngắn hoặc xử lý chậm | Giới hạn attachment, cân nhắc đưa liên kết tải file có kiểm soát. |

### Ví dụ với các họ client

- **Gmail (web/app):** có thể lọc HTML, xử lý ảnh qua proxy và áp dụng chính sách bảo vệ người đọc; ảnh inline/attachment cần được xem trong điều kiện nhận thực tế.
- **Outlook:** khả năng hiển thị khác nhau giữa phiên bản desktop truyền thống, phiên bản mới và web; bố cục HTML/CSS phức tạp và ảnh inline cần được thử riêng.
- **Apple Mail và các client trên thiết bị di động:** có thể tự điều chỉnh kích thước nội dung, chế độ tối và hiển thị attachment; thiết kế responsive và plain fallback có ích.
- **Client chỉ đọc văn bản, hệ thống cảnh báo và bộ xử lý tự động:** có thể bỏ qua HTML hoàn toàn, nên bản `text/plain` không được là một câu vô nghĩa như “Vui lòng xem bản HTML”.

Các ví dụ trên là **những hướng cần quan sát**, không phải cam kết tuyệt đối về từng phiên bản. Cấu trúc MIME tốt giúp giảm lỗi nhưng không kiểm soát được tất cả chính sách render của phía nhận.

## 8. Hai loại “thứ tự” cần phân biệt

Khi nói “thứ tự MIME”, cần tách:

**Thứ tự ưu tiên ngữ nghĩa trong `multipart/alternative`**

- Phần sau là phương án biểu diễn ưu tiên hơn nếu client hỗ trợ.
- Với plain và HTML, thông thường **plain trước → HTML sau**.
- Thứ tự sai có thể khiến client lựa chọn sai phiên bản.

**Thứ tự xây dựng và sắp đặt resource trong `multipart/related` / `mixed`**

- Part gốc của related cần được chỉ định rõ hoặc đặt đầu nếu không có `start`.
- Attachment thường nằm sau phần nội dung chính trong mixed.
- Khi dùng Spring Mail, gọi `setText(...)` rồi `addInline(...)` để tương thích tốt hơn với một số mail reader.

Ngoài hai loại đó, **thứ tự hiển thị** do mail client quyết định. Ví dụ, một client có thể đặt các file đính kèm thành thanh biểu tượng phía trên dù trong MIME chúng nằm sau body. Đừng dùng vị trí hiển thị trên UI để suy luận chính xác thứ tự các part; khi cần hãy xem **raw message source**.

## 9. Cách kiểm tra cấu trúc MIME trên hệ thống nhận

Khi email không giống mong đợi, chỉ nhìn bản render có thể che mất nguyên nhân. Hãy quan sát cây MIME:

1. Gửi email tới một **SMTP server thử nghiệm** hoặc hộp thư kiểm thử. Các công cụ như Mailpit và GreenMail có thể hỗ trợ quan sát nội dung, header và attachment.
2. Xem **nguồn email gốc** (*show original*, *view source* hoặc tương đương). Tìm `MIME-Version` và `Content-Type: multipart/...` của thông điệp.
3. Xác định các boundary và cây lồng nhau; với `alternative`, đọc thứ tự `text/plain` và `text/html`.
4. Với HTML có ảnh inline, kiểm tra `src="cid:brandLogo"` có part `Content-ID: <brandLogo>` tương ứng và part ảnh nằm trong nhóm liên quan thích hợp.
5. Với attachment, xem `Content-Disposition: attachment`, tên file, loại dữ liệu và nhóm `mixed`.
6. Mở thư bằng **những client mà người nhận thực tế sử dụng**, gồm web/mobile/desktop nếu liên quan. Quan sát body, các link, alt text, ảnh inline, tên tệp và cách xuống dòng.

Nếu ứng dụng Spring gửi thư qua SMTP mà máy chủ trả `250` sau `DATA`, nghĩa là server đã **chấp nhận thư để xử lý**, chưa có bảo đảm tất cả client sẽ hiển thị nội dung theo cách giống nhau. Đường đi qua gateway, hệ thống chống spam, bộ lọc bảo mật hoặc dịch vụ newsletter có thể thêm header và thậm chí viết lại một số phần.

### Dấu hiệu lỗi và vị trí cần xem trước

| Dấu hiệu | Khả năng liên quan | Nơi kiểm tra |
|---|---|---|
| Người đọc thấy hai lần cùng một nội dung | Hai bản plain/HTML không được nhóm trong `alternative` | Cây `multipart/*` và vị trí part |
| Chỉ thấy plain text dù có HTML | `alternative` sai thứ tự hoặc client không hiển thị HTML | Thứ tự `text/plain`/`text/html` và cài đặt client |
| Logo là biểu tượng attachment | Inline part không thuộc related phù hợp, hoặc client có cách hiển thị riêng | `Content-ID`, `Content-Disposition`, `multipart/related` |
| Logo trống hoặc dấu X | `cid:` không khớp, part không được đính kèm, ảnh không được client hỗ trợ hoặc đã bị chặn | HTML, part ảnh, MIME type, chính sách client |
| Tiếng Việt lỗi dấu | Charset/transfer encoding không nhất quán hoặc xử lý sai ở khâu tạo body | `charset=UTF-8` và dữ liệu nguồn |
| PDF không xuất hiện | Đính kèm sai nhóm, bị lọc hoặc kích thước vượt giới hạn | `multipart/mixed`, provider log, thông điệp nhận |
| HTML méo bố cục | CSS/HTML không được client hỗ trợ | HTML thực nhận, CSS và renderer mục tiêu |

## 10. Nguyên tắc soạn email MIME đáng tin cậy

Để tránh phụ thuộc quá mức vào một mail client cụ thể, hãy thiết kế từ **các tầng ý nghĩa**:

1. **Nội dung:** bản `text/plain` đầy đủ; nếu có HTML thì đặt sau trong `alternative`.
2. **Tài nguyên hiển thị:** HTML và các ảnh CID thuộc một nhóm `related` thích hợp; quản lý chính xác Content-ID.
3. **Tệp đính kèm:** giữ tách khỏi tài nguyên inline bằng `mixed` bên ngoài khi cần.
4. **Mã hóa:** đặt charset phù hợp, thường là UTF-8; giao định dạng MIME và transfer encoding cho thư viện mail.
5. **Khả năng đọc:** email phải hữu ích khi ảnh không tải hoặc HTML bị vô hiệu hóa; alt text chỉ hỗ trợ phần hình, không thay thế nội dung văn bản cần thiết.
6. **Thiết bị và client:** thử các mail client chính của người nhận, tránh những tính năng HTML/CSS chỉ hoạt động trên một engine.
7. **Mã Spring:** dùng `MimeMessageHelper` thay cho việc tự ghép MIME raw; chọn multipart mode rõ ràng khi có inline resource hoặc attachment và thực hiện `setText(...)` trước `addInline(...)`.

Khi nhìn một email có HTML, logo và PDF, hãy tự hỏi ba câu: **Các bản plain/HTML có được đánh dấu là alternative không? Ảnh thuộc về nội dung HTML theo related hay đang bị coi như attachment? PDF có tách khỏi nội dung chính trong mixed không?** Trả lời được ba câu đó giúp định vị phần lớn vấn đề liên quan đến thứ tự MIME và khả năng tương thích giữa các mail client.
