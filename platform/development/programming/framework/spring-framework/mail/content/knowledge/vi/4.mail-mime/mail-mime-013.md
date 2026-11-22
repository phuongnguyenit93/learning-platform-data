# Kiểm tra MIME tree khi chẩn đoán thư hiển thị sai

## 1. Vì sao email đúng nội dung nhưng lại hiển thị sai?

Một email có thể gửi thành công qua SMTP, được máy chủ người nhận chấp nhận, nhưng khi mở trong ứng dụng email lại xuất hiện những vấn đề như:

- Nội dung HTML bị hiển thị thành các thẻ `<p>`, `<table>` và `<img>`.
- Người dùng chỉ thấy bản text dù email được thiết kế có HTML.
- Ảnh logo trong body hiện biểu tượng ảnh hỏng hoặc bị liệt kê như tệp đính kèm.
- Một phần body xuất hiện hai lần hoặc email trông như có nhiều thư khác nhau.
- Tệp PDF không có ở danh sách đính kèm, hoặc bị nhúng vào nội dung.
- Chữ tiếng Việt thành `Ã¡`, `=?UTF-8?...?=` hoặc chuỗi ký tự khó đọc.
- Một số ứng dụng đọc mail hiển thị đúng, nhưng ứng dụng khác lại hiển thị khác.

Trong các trường hợp ấy, chỉ kiểm tra chuỗi HTML đầu vào hoặc mã phản hồi SMTP là chưa đủ. Cần xem **MIME tree**: cấu trúc phân cấp các phần (*parts*) tạo thành một thông điệp email. **MIME (Multipurpose Internet Mail Extensions)** mô tả cách thông điệp chứa nhiều định dạng nội dung, các phiên bản thay thế, ảnh nhúng và tệp đính kèm.

Với **Spring Framework Mail**, các lời gọi như `MimeMessageHelper.setText(...)`, `addInline(...)` và `addAttachment(...)` cuối cùng được biểu diễn thành một cây MIME trong `jakarta.mail.internet.MimeMessage`. Khi cây có thứ tự, quan hệ cha–con hoặc header không phù hợp, ứng dụng email của người nhận có thể lựa chọn phần hiển thị khác ý định của người gửi.

> **Nguyên tắc chẩn đoán:** Đọc MIME tree để xác định **phần nào là body chính, phần nào là phiên bản thay thế, phần nào là tài nguyên nhúng và phần nào là tệp đính kèm**. Sau đó kiểm tra header và dữ liệu thật của từng phần, rồi mới kết luận lỗi thuộc Spring Mail, SMTP server hay email client.

## 2. MIME tree là gì?

MIME tree là cách biểu diễn **đệ quy** của một email. Gốc cây thường là `MimeMessage`. Một node có thể chứa nội dung đơn (*leaf part*) hoặc nhiều node con (*multipart container*).

Ví dụ một thư vừa có plain text, HTML, ảnh logo dùng trong HTML và một tệp PDF:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/alternative
    │   ├── text/plain; charset=UTF-8
    │   └── multipart/related
    │       ├── text/html; charset=UTF-8
    │       │   (HTML tham chiếu src="cid:logo-mail")
    │       └── image/png
    │           Content-ID: <logo-mail>
    │           Content-Disposition: inline
    └── application/pdf
        Content-Disposition: attachment
        filename="report.pdf"
~~~

Cách đọc:

1. `multipart/mixed` gom các nội dung khác vai trò, ví dụ body chính và attachment.
2. `multipart/alternative` chứa **các cách thể hiện thay thế của cùng một nội dung**, ở đây là plain text và phiên bản HTML có ảnh.
3. `multipart/related` nhóm HTML với tài nguyên phụ thuộc mà HTML tham chiếu, ví dụ hình ảnh `cid:logo-mail`.
4. `text/plain` và `text/html` là hai cách biểu diễn phần thông điệp chính.
5. `image/png` với `Content-ID` là tài nguyên có thể dùng bên trong HTML; `application/pdf` với `attachment` là tệp để người dùng tải về.

Đây là **một cấu trúc hợp lý**, không phải hình dạng duy nhất của mọi thư hợp lệ. Tùy thư viện và cách tổ chức multipart, một thư khác cũng có thể chứa `multipart/mixed → multipart/related → multipart/alternative`, với inline image là node cùng cấp với `multipart/alternative` bên trong `related`. Điều cần xác định là **ngữ nghĩa của container, vị trí của các part và header tham chiếu**.

### 2.1. Những loại Content-Type cần nhận ra

| `Content-Type` | Vai trò thông dụng | Cách kiểm tra khi hiển thị sai |
| --- | --- | --- |
| `text/plain` | Body dạng văn bản thuần | `charset`, nội dung thực, vị trí trong `alternative` |
| `text/html` | Body HTML | `charset`, HTML hợp lệ, quan hệ với `related` |
| `multipart/alternative` | Nhiều phiên bản tương đương của một nội dung | Thứ tự các lựa chọn; có thực sự là alternatives hay không |
| `multipart/related` | Body gốc đi cùng các tài nguyên phụ thuộc | Root part, `Content-ID`, `cid:` reference, `start`/`type` nếu có |
| `multipart/mixed` | Ghép body với các nội dung độc lập như attachment | Attachment có nằm ngoài nhóm body đúng cách không |
| `image/png`, `image/jpeg` | Ảnh, có thể là inline hoặc attachment | `Content-ID`, `Content-Disposition` và bytes/encoding |
| `application/pdf` | Tệp PDF | `Content-Disposition: attachment`, filename, kiểu và nội dung |
| `message/rfc822` | Một email khác được đính kèm hoặc lồng trong thư | Cây con phải được xử lý như một thông điệp riêng |

`multipart/*` là **container**: `Content-Type` của nó thường có tham số `boundary` để phân cách các part khi tuần tự hóa ra văn bản truyền đi. `text/*` và `application/*` thường là **leaf**. MIME có thể lồng nhiều tầng nên phải đi theo cây, không chỉ đọc `Content-Type` ở gốc.

## 3. Ba container quan trọng: alternative, related và mixed

### 3.1. multipart/alternative: chọn một phiên bản phù hợp

Ví dụ:

~~~text
multipart/alternative
├── text/plain; charset=UTF-8
│   "Báo cáo tuần đã sẵn sàng."
└── text/html; charset=UTF-8
    "<p>Báo cáo tuần đã <strong>sẵn sàng</strong>.</p>"
~~~

Hai part **không phải hai nội dung độc lập cần hiển thị nối tiếp**. Chúng là các lựa chọn khác nhau để biểu diễn cùng thông tin. Theo cách sắp xếp MIME thông thường, các part xếp **từ mức thể hiện ít phong phú đến mức được ưu tiên hơn**; bản `text/plain` thường đứng trước `text/html`. Email client chọn phiên bản cuối mà nó hỗ trợ và được phép hiển thị, đồng thời có thể áp dụng chính sách riêng.

Một lỗi dễ gặp là:

~~~text
multipart/mixed
├── text/plain
└── text/html
~~~

Nếu mục đích là cung cấp hai phiên bản thay thế, cấu trúc trên không truyền đạt đúng quan hệ *alternative*. Một số client có thể hiển thị cả hai phần, xem phần HTML như attachment hoặc dùng cách chọn riêng.

Một cấu trúc khác cần chú ý:

~~~text
multipart/alternative
├── text/html
└── text/plain
~~~

Đây là thứ tự không phù hợp với ý định ưu tiên HTML trong nhiều trường hợp: client theo quy tắc chọn phiên bản hỗ trợ ở phía sau có thể chọn `text/plain`, khiến người gửi tưởng rằng “HTML bị mất”.

### 3.2. multipart/related: HTML và ảnh inline phải liên hệ được với nhau

Giả sử HTML chứa:

~~~html
<p>Chào bạn, đây là logo:</p>
<img src="cid:logo-mail" alt="Logo">
~~~

Một cấu trúc khả dụng:

~~~text
multipart/related
├── text/html
│   <img src="cid:logo-mail">
└── image/png
    Content-ID: <logo-mail>
    Content-Disposition: inline
~~~

`cid:logo-mail` trong HTML tham chiếu tới `Content-ID: <logo-mail>` của part ảnh. Dấu ngoặc nhọn `<...>` thuộc cách biểu diễn header `Content-ID`; chuỗi trong `cid:` không chứa dấu ngoặc đó. Trên thực tế có thể có các Content-ID dài và có dạng giống địa chỉ, nhưng hai phía phải khớp chính xác theo quy tắc liên quan.

Khi kiểm tra, cần trả lời:

- Part HTML có thật sự chứa tham chiếu `cid:...` đúng như mong muốn?
- Có part ảnh tương ứng trong cùng nhóm nội dung liên quan không?
- `Content-ID` đã được gán cho đúng ảnh chưa? Có dấu ngoặc, lỗi chính tả hoặc ID bị lặp không?
- `Content-Type` của ảnh có hợp lý không, ví dụ `image/png` cho PNG?
- Part ảnh có thể giải mã được không, hay dữ liệu bị hỏng trong quá trình tạo/chuyển?
- Root của `multipart/related` là part nào? Nếu có tham số `start`, nó có trỏ đúng `Content-ID` của root không?

Trong `multipart/related`, part gốc thông thường là part đầu tiên khi không có tham số `start`; nếu có `start`, part mang Content-ID tương ứng được xác định là root. Tham số `type` nếu có nên phản ánh loại MIME của root. Không chỉ dựa vào `Content-Disposition: inline` để quyết định phần nào là body chính.

### 3.3. multipart/mixed: attachment độc lập với body

Một email có body và báo cáo PDF thường có cây:

~~~text
multipart/mixed
├── text/plain hoặc một cây multipart của body
└── application/pdf
    Content-Disposition: attachment; filename="report.pdf"
~~~

`mixed` diễn tả các phần kết hợp trong một thông điệp. Trình đọc mail thường tìm body ở phần thích hợp và cung cấp attachment như tệp tải về.

Nếu attachment bị đặt vào `multipart/alternative` như một “lựa chọn thay thế” của body:

~~~text
multipart/alternative
├── text/html
└── application/pdf
~~~

thì ý nghĩa cây đã sai: PDF được đánh dấu là một phiên bản thay thế của cùng nội dung. Tùy client, nó có thể thay thế body, làm body biến mất hoặc khiến thư hiển thị bất thường. Nếu PDF là file đính kèm độc lập, cần nhóm nó cùng body trong `multipart/mixed` ở vị trí phù hợp.

## 4. Đọc header của từng part như thế nào?

Chẩn đoán MIME tree không chỉ dựa vào tên node. Các header của **mỗi part** quyết định cách giải mã và cách ứng dụng mail xem nó.

| Header hoặc tham số | Ý nghĩa | Dấu hiệu lỗi |
| --- | --- | --- |
| `Content-Type` | Loại nội dung; có thể chứa `charset` và `boundary` | HTML bị ghi thành `text/plain`; multipart thiếu boundary hoặc sai boundary |
| `charset` | Bảng mã của nội dung dạng text | UTF-8 bị gán nhầm ISO-8859-1, chữ tiếng Việt hiển thị sai |
| `Content-Transfer-Encoding` | Cách thể hiện bytes trên đường truyền, ví dụ `base64`, `quoted-printable`, `7bit` | Part không giải mã đúng, lộ chuỗi mã hóa |
| `Content-Disposition` | Gợi ý cách trình bày `inline` hay `attachment` | Body bị xử lý như tệp tải xuống, ảnh inline bị liệt kê là attachment |
| `Content-ID` | Danh tính của một part, thường dùng với `cid:` | Ảnh không khớp ID trong HTML |
| `Content-Location` | Định danh tài nguyên theo vị trí tương đối/tuyệt đối trong một số thư | Client không nối được tham chiếu tài nguyên |
| `filename` / `name` | Tên tệp, có thể dùng trong disposition/type | Tệp xuất hiện không tên hoặc tên lỗi mã hóa |
| `boundary` | Chuỗi phân cách các thành viên của `multipart` | Trình phân tích không tách đúng các part |
| `MIME-Version` | Thông báo cấu trúc MIME, thường `1.0` ở cấp thông điệp | Thiếu hoặc bất thường có thể ảnh hưởng tương thích |

**Content-Type**, **Content-Transfer-Encoding** và **charset** là ba khái niệm khác nhau. Ví dụ:

~~~text
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

nghĩa là nội dung sau khi **giải mã quoted-printable** phải được diễn giải thành **text HTML với charset UTF-8**. Nếu áp dụng sai thứ tự hoặc gán charset không đúng với bytes ban đầu, text có thể biến thành ký tự rác. Tương tự, `base64` trong một part không có nghĩa nội dung đó tự động là attachment; text HTML cũng có thể được truyền dưới dạng base64.

`Content-Disposition` cũng là một tín hiệu trình bày, **không phải mệnh lệnh bắt buộc mọi email client phải tuân theo giống nhau**. Một số client tự quyết định cách hiển thị theo MIME type, vị trí part, filename, chính sách bảo mật và các thông tin khác.

## 5. Đọc một thông điệp MIME thô và dựng lại cây

Giả sử tải được nguyên bản thông điệp ở định dạng `.eml`. Phần header đầu có thể như sau:

~~~text
From: Reports <reports@example.com>
To: lan@example.net
Subject: Weekly report
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="mix-71"
~~~

Phần body MIME bên dưới được phân tách bằng boundary:

~~~text
--mix-71
Content-Type: multipart/alternative; boundary="alt-71"

--alt-71
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Bao cao tuan da san sang.
--alt-71
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: 7bit

<p>Weekly report is <strong>ready</strong>.</p>
--alt-71--
--mix-71
Content-Type: application/pdf; name="report.pdf"
Content-Disposition: attachment; filename="report.pdf"
Content-Transfer-Encoding: base64

[Dữ liệu base64 đã lược bỏ trong ví dụ]
--mix-71--
~~~

Đây là ví dụ minh họa cấu trúc; phần base64 giả định đã được lược bỏ để dễ đọc, nên không phải `.eml` hoàn chỉnh dùng làm mẫu gửi thật.

Quy tắc dựng cây:

1. Đọc `Content-Type` ở root, nhận ra `multipart/mixed` và `boundary="mix-71"`.
2. Mỗi dòng `--mix-71` bắt đầu một part trực tiếp dưới root; `--mix-71--` đóng container đó.
3. Part đầu là `multipart/alternative` với boundary riêng `alt-71`; phải tiếp tục đi vào trong.
4. Trong `alt-71`, hai part `text/plain` và `text/html` là các lựa chọn của cùng body.
5. Quay lại `mix-71`, part tiếp theo là PDF có `Content-Disposition: attachment`.

Không nên tìm toàn bộ chuỗi `Content-Type: text/html` bằng cách quét văn bản rồi kết luận “email có HTML nên phải hiển thị HTML”. Vị trí của part trong các container và cách client lựa chọn alternative mới quyết định điều đó.

### 5.1. Boundary phải khớp tuyệt đối

Với header:

~~~text
Content-Type: multipart/alternative; boundary="abc"
~~~

các part sẽ được ngăn bằng `--abc` và kết thúc container bằng `--abc--`. Nếu một hệ thống tự nối chuỗi MIME nhưng dùng sai tên boundary, thiếu dấu gạch, chèn dữ liệu sau dấu đóng không đúng mục đích, hoặc phá ranh giới CRLF, parser có thể:

- Gộp nhiều phần thành một;
- Coi header của part con như body text;
- Không tìm thấy phần HTML hoặc attachment;
- Báo lỗi phân tích hoặc bỏ qua một phần không hợp lệ.

Với Spring Mail, cách an toàn là để `MimeMessageHelper`/Jakarta Mail dựng MIME thay vì tự ghép chuỗi boundary.

## 6. Quy trình chẩn đoán có thể lặp lại

Khi nhận báo cáo “email hiển thị sai”, nên đi từ **hiện tượng** tới **thông điệp thực được nhận**, tránh bắt đầu bằng việc chỉnh HTML mù quáng.

### Bước 1 — Ghi nhận triệu chứng và client xảy ra lỗi

Thu thập đủ ngữ cảnh để tái hiện:

- Client nào gặp lỗi: Outlook desktop, Gmail web, ứng dụng mail mobile hoặc một hệ thống đọc thư riêng?
- Sai trên mọi client hay chỉ một client cụ thể?
- Chỉ một email hay mọi email gửi từ cùng template?
- Sai văn bản, HTML, ảnh CID, attachment hay font/ký tự?
- Email đã trải qua chuyển tiếp, mailing list, gateway, dịch vụ quét nội dung hoặc hệ thống bảo mật thư nào?

Chỉ khi cùng thông điệp được mở ở các client khác nhau mới có thể tách lỗi **cấu trúc MIME** khỏi giới hạn/policy của phần mềm hiển thị.

### Bước 2 — Thu bản gốc của thư thực sự được nhận

Ưu tiên xuất **Show original / View source / Download original** thành `.eml` từ mailbox hoặc công cụ nhận thư kiểm thử. Giữ nguyên header và body MIME; ảnh chụp màn hình không thể hiện boundary hay Content-ID. Nếu cần so sánh thay đổi dọc luồng, có thể lưu thêm bản `MimeMessage` ngay trước khi gọi `JavaMailSender.send(...)` trong môi trường kiểm thử.

Nội dung email có thể chứa dữ liệu cá nhân, thông tin bí mật và token trong URL. Chỉ lưu vào môi trường chẩn đoán có quyền phù hợp; che hoặc loại bỏ dữ liệu nhạy cảm trước khi chia sẻ log/tài liệu. Không nên dựa vào screenshot để suy ra tree.

### Bước 3 — Xem MIME tree, không chỉ root Content-Type

Liệt kê theo chiều sâu:

~~~text
root: multipart/mixed
  0: multipart/related
    0.0: multipart/alternative
      0.0.0: text/plain
      0.0.1: text/html
    0.1: image/png [inline] Content-ID=<logo-mail>
  1: application/pdf [attachment] filename=report.pdf
~~~

Mỗi node nên ghi tối thiểu: **đường dẫn trong cây, Content-Type, Content-Disposition, Content-ID, filename**, và khi cần, kích thước hoặc encoding. Không cần in toàn bộ body hay dữ liệu attachment ra log chỉ để xem cấu trúc.

### Bước 4 — Xác định body chính và các alternative

Trước hết, tìm `text/plain` và `text/html`. Hai phiên bản của cùng nội dung nên có quan hệ `multipart/alternative` phù hợp. Kiểm tra:

- Chúng có nằm trong cùng nhóm `alternative` không?
- Thứ tự có cho phép client ưu tiên HTML khi hỗ trợ không?
- HTML đã được đặt là `text/html` hay bị gắn `text/plain`?
- Bản plain có được tạo để đọc được khi HTML bị tắt không?
- Body chính có vô tình bị gắn `Content-Disposition: attachment` không?

### Bước 5 — Kiểm tra tham chiếu ảnh và tài nguyên liên quan

Với mỗi `src="cid:..."` trong HTML, tìm part có `Content-ID` tương ứng và xem part đó nằm dưới container `related` đúng hay không. Kiểm tra loại nội dung ảnh, encoding, dữ liệu ảnh và root/`start` nếu có. Nếu HTML dùng URL từ xa, việc client chặn tải ảnh từ Internet **không phải** lỗi MIME tree; đó là chính sách tải nội dung từ xa.

### Bước 6 — Kiểm tra attachment và charset/encoding

Nếu file bị nhầm là body, xem nó có được tổ chức đúng trong `multipart/mixed` và có disposition/filename phù hợp không. Với lỗi chữ tiếng Việt, so sánh bytes gốc, `charset` và `Content-Transfer-Encoding` của **part cụ thể** chứ không chỉ header gốc.

### Bước 7 — Đối chiếu trước/sau đường vận chuyển

Nếu bản MIME tạo ra tại ứng dụng đúng nhưng bản `.eml` người nhận có cấu trúc khác, có thể có hệ thống trung gian thêm disclaimer, quét nội dung, viết lại link/ảnh hoặc đóng gói lại MIME. Cần đối chiếu phiên bản ở các điểm có thể quan sát. Nếu hai bản giống nhau mà chỉ một client hiển thị sai, cần kiểm tra khả năng HTML/CSS, hỗ trợ ảnh CID và chính sách bảo mật của client đó.

## 7. Đọc MIME tree bằng Jakarta Mail trong Java

Trong ứng dụng dùng **Spring Framework 6 / Jakarta Mail**, có thể nạp một thông điệp `.eml` rồi duyệt đệ quy qua các container. Ví dụ dưới đây chỉ in **metadata cấu trúc**; nó không cố ý đọc nội dung text/HTML hay in bytes của các tệp đính kèm.

~~~java
package com.example.maildiagnostics;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

public final class MimeTreeInspector {

    private MimeTreeInspector() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: MimeTreeInspector <path-to-message.eml>");
        }

        Session session = Session.getInstance(new Properties());

        try (InputStream input = Files.newInputStream(Path.of(args[0]))) {
            MimeMessage message = new MimeMessage(session, input);
            walk(message, "root", 0);
        }
    }

    private static void walk(Part part, String path, int depth)
            throws MessagingException, IOException {

        String indentation = "  ".repeat(depth);
        String disposition = part.getDisposition();
        String fileName = part.getFileName();
        String contentId = first(part.getHeader("Content-ID"));
        String transferEncoding =
                first(part.getHeader("Content-Transfer-Encoding"));

        // Chỉ dùng trên email mẫu đã được phép phân tích.
        // Khi chia sẻ kết quả cần che tên file, Content-ID nhạy cảm.
        System.out.printf(
                "%s%s type=%s, disposition=%s, filename=%s, cid=%s, cte=%s%n",
                indentation,
                path,
                part.getContentType(),
                disposition,
                fileName,
                contentId,
                transferEncoding);

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (content instanceof Multipart multipart) {
                for (int i = 0; i < multipart.getCount(); i++) {
                    walk(multipart.getBodyPart(i), path + "." + i, depth + 1);
                }
            }
        } else if (part.isMimeType("message/rfc822")) {
            Object content = part.getContent();
            if (content instanceof Message nestedMessage) {
                walk(nestedMessage, path + ".message", depth + 1);
            }
        }
    }

    private static String first(String[] headers) {
        return (headers == null || headers.length == 0)
                ? "-"
                : headers[0];
    }
}
~~~

Điểm đáng chú ý:

- `MimeMessage` là thông điệp gốc và cũng là một `Part`; `Multipart` chứa các body part con.
- `getContentType()` trả về cả MIME type lẫn tham số, ví dụ `boundary` hoặc `charset`.
- `getDisposition()`, `getFileName()` và `getHeader("Content-ID")` hỗ trợ xác định vai trò của part.
- `part.isMimeType("multipart/*")` nhận biết container; sau đó `getContent()` thường trả `Multipart` có thể duyệt bằng `getBodyPart(i)`.
- `message/rfc822` là một thông điệp lồng, nên ví dụ duyệt tiếp khi nội dung giải mã là một `Message`.
- Ví dụ không gọi `getContent()` cho các leaf `text/html` hay `application/pdf`, giúp hạn chế việc đọc body hoặc attachment chỉ để kiểm tra cấu trúc.

Đoạn code giả định message có thể parse được. Với thư MIME lỗi nặng, `getContent()` vẫn có thể ném ngoại lệ hoặc parser có hành vi dung sai khác nhau; khi đó cần xem bản raw `.eml` và các boundary. Việc duyệt tree cũng có thể phát sinh đọc dữ liệu/IO để parse multipart; không nên mặc định đây là thao tác miễn phí với email lớn. Giới hạn kích thước nguồn và nơi chạy chẩn đoán phù hợp.

**Lưu ý phiên bản:** Spring Framework 6 dùng package `jakarta.mail.*`. Những ứng dụng Spring đời cũ có thể dùng `javax.mail.*`; không pha trộn hai hệ package trong cùng ví dụ.

### 7.1. Dùng chính MimeMessage vừa tạo trước khi gửi

Trong Spring Mail, có thể xây dựng `MimeMessage`, sau đó xem cấu trúc trong môi trường thử nghiệm trước khi gọi `send(...)`:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("reports@example.com");
helper.setTo("lan@example.net");
helper.setSubject("Báo cáo tuần");
helper.setText(
        "Báo cáo tuần đã sẵn sàng.",
        "<p>Báo cáo tuần đã <strong>sẵn sàng</strong>.</p>");

// Sau khi cấu hình xong message, có thể serialize để
// quan sát cấu trúc MIME tại môi trường kiểm thử:
message.saveChanges();
try (OutputStream output = Files.newOutputStream(Path.of("sample.eml"))) {
    message.writeTo(output);
}

mailSender.send(message);
~~~

Đây là đoạn minh họa đặt trong nơi đã có biến `mailSender` và các import phù hợp; khi muốn dùng trong một method Java cần import `java.io.OutputStream`, `java.nio.file.Files` và `java.nio.file.Path`, cũng như xử lý các ngoại lệ được khai báo. Hãy chọn nơi lưu file kiểm thử có kiểm soát và bảo đảm không vô tình ghi nội dung email nhạy cảm vào thư mục công khai.

Thông điệp serialize **trước khi gửi** giúp biết Spring/Jakarta Mail dựng những part nào. Bản **người nhận thực sự nhận được** vẫn cần đối chiếu riêng vì hạ tầng mail có thể bổ sung hoặc thay đổi header/body trong quá trình xử lý.

## 8. Tạo cây MIME đúng bằng MimeMessageHelper

Giả sử cần gửi thông báo chứa hai phiên bản body, một logo inline và file báo cáo PDF. Với Spring Framework Mail, thay vì tự tạo boundary, có thể sử dụng `MimeMessageHelper`:

~~~java
package com.example.mail;

import java.nio.charset.StandardCharsets;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.Resource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WeeklyReportMailer {

    private final JavaMailSender mailSender;

    public WeeklyReportMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient, Resource logoPng, Resource reportPdf)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name());

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Báo cáo tuần");

        // Cung cấp hai phiên bản thay thế của cùng body.
        helper.setText(
                "Báo cáo tuần đã sẵn sàng. Xem tệp PDF đính kèm.",
                "<p>Báo cáo tuần đã sẵn sàng.</p>"
                        + "<img src=\"cid:weekly-logo\" alt=\"Logo\">"
                        + "<p>Xem tệp PDF đính kèm.</p>");

        // Khai báo inline sau setText để phần HTML đã tồn tại.
        helper.addInline("weekly-logo", logoPng, "image/png");

        // Tệp PDF là attachment độc lập với body.
        helper.addAttachment("report.pdf", reportPdf);

        mailSender.send(message);
    }
}
~~~

Ở đây `Resource` cho logo và PDF phải trỏ tới nội dung có thể đọc được (và đáp ứng yêu cầu đọc lại của thư viện khi cần); code gọi phải xác minh quyền truy cập, loại file, kích thước và nguồn dữ liệu. Phần `addInline` dùng Content-ID `weekly-logo`; trong HTML phải viết `src="cid:weekly-logo"`. **Thứ tự `setText(...)` trước `addInline(...)`** quan trọng với cách `MimeMessageHelper` tổ chức body part.

Khi chọn `MULTIPART_MODE_MIXED_RELATED`, Spring thường tổ chức body/ảnh/attachment theo dạng:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain; charset=UTF-8
    │   │   └── text/html; charset=UTF-8
    │   └── image/png
    │       Content-ID: <weekly-logo>
    │       Content-Disposition: inline
    └── application/pdf
        Content-Disposition: attachment
        filename="report.pdf"
~~~

Đây là **dạng điển hình** của mode được chọn, giúp phân biệt body và attachment. Tree chính xác phụ thuộc các thao tác helper, phiên bản và cách serialize; muốn biết mail thật được tạo ra ra sao vẫn cần inspect `MimeMessage`.

Các mode multipart khác có thể tạo cấu trúc khác:

| Mode của `MimeMessageHelper` | Ý tưởng cấu trúc | Khi cần chú ý |
| --- | --- | --- |
| `MULTIPART_MODE_NO` | Không dựng cấu trúc multipart để thêm inline/attachment | Dùng cho thông điệp đơn giản không cần multipart |
| `MULTIPART_MODE_MIXED` | Một container `multipart/mixed` | Một số client có thể khác biệt khi hiển thị inline resource |
| `MULTIPART_MODE_RELATED` | Một container `multipart/related` | Cách client diễn giải attachment có thể khác nhau |
| `MULTIPART_MODE_MIXED_RELATED` | `mixed` ở ngoài và `related` cho body/tài nguyên bên trong | Thường phù hợp khi vừa có inline image vừa có attachment |

Lựa chọn mode phải dựa vào nội dung cần gửi và khả năng tương thích của các client mục tiêu; không nên thay mode chỉ để cây nhìn “ngắn hơn”.

## 9. Bảng chẩn đoán: triệu chứng → điểm cần xem trong tree

| Triệu chứng | Dấu hiệu MIME cần kiểm tra | Hướng xử lý có thể phù hợp |
| --- | --- | --- |
| Thấy nguyên thẻ `<html>`, `<p>` | Body HTML bị ghi là `text/plain`; part HTML không thuộc nhánh được chọn | Tạo đúng `text/html`, dùng `setText(html, true)` hoặc plain+HTML overload |
| Chỉ thấy bản plain | `multipart/alternative` thiếu HTML hoặc HTML đứng sai thứ tự; client không chọn HTML | Tạo alternative đúng, kiểm tra chính sách và khả năng HTML của client |
| Body bị lặp hai lần | Plain và HTML là hai sibling trong `multipart/mixed` thay vì `alternative` | Đưa hai phiên bản cùng nội dung vào `multipart/alternative` |
| HTML bị xem như attachment | `Content-Disposition: attachment` trên HTML; body nằm sai chỗ | Xem lại disposition và nhóm body |
| Logo hiện ảnh hỏng | `cid:` không khớp `Content-ID`, thiếu part inline, sai content type hoặc bytes | Sửa tham chiếu và part ảnh; inspect `related` |
| Ảnh inline bị hiện ở danh sách tệp | Ảnh không nằm trong nhóm related phù hợp, header disposition/filename gây nhầm lẫn | Dùng mode multipart phù hợp; đối chiếu client đích |
| PDF biến mất | Attachment nằm trong `alternative`, thiếu disposition, multipart/boundary lỗi | Đặt PDF vào nhóm `mixed`, kiểm tra header và bytes |
| Tên attachment bị lỗi ký tự | Header filename/name encoding không phù hợp hoặc client không giải mã đúng | Dùng API thư viện và kiểm tra cách tên tệp được mã hóa |
| Tiếng Việt thành ký tự rác | `charset` sai, CTE sai hoặc dữ liệu bị mã hóa hai lần | So sánh bytes và charset của part chứa text |
| Chỉ hỏng ở một client | MIME hợp lệ nhưng client giới hạn CSS/HTML, ảnh từ xa hoặc cách xử lý related | Kiểm thử trên client mục tiêu; đơn giản hóa HTML, không suy ra MIME hỏng |

Bảng này dùng để **khoanh vùng**, không khẳng định một triệu chứng chỉ có một nguyên nhân. Cùng một hình ảnh lỗi có thể đến từ HTML/CSS không được hỗ trợ, email gateway thay đổi nội dung, thư MIME chưa chuẩn hoặc chính sách bảo mật của client.

## 10. Phân tích các tình huống cụ thể

### 10.1. Body hiện hai lần sau khi thêm HTML

**Cây sai theo mục đích gửi hai phiên bản thay thế:**

~~~text
multipart/mixed
├── text/plain: "Xin chào"
└── text/html: "<p>Xin chào</p>"
~~~

Hai part độc lập thuộc `mixed` có thể đều được hiển thị. Nếu là hai phiên bản của một body, cây nên là:

~~~text
multipart/alternative
├── text/plain: "Xin chào"
└── text/html: "<p>Xin chào</p>"
~~~

Trong Spring, dùng `helper.setText(plainText, htmlText)` để tạo hai lựa chọn, thay vì tự thêm hai body part cùng cấp vào `mixed`.

### 10.2. Ảnh CID có trong email nhưng không hiện

Giả sử HTML có `<img src="cid:logo-2026">`. Khi inspect tree thấy:

~~~text
multipart/related
├── text/html
└── image/png
    Content-ID: <logo-2025>
~~~

ID không khớp; client không tìm thấy part ảnh được tham chiếu. Cần sửa content ID/HTML để cùng chỉ về một tài nguyên. Nếu hai ID khớp nhưng vẫn hỏng, kiểm tra liệu bytes ảnh có giải mã và mở được không, đúng `Content-Type` không, client có chặn loại tài nguyên đó không.

Đừng nhầm ảnh có URL `https://...` với ảnh `cid:...`: hình ảnh từ xa có thể bị client chặn tự động cho đến khi người dùng cho phép tải ảnh, dù email MIME hợp lệ.

### 10.3. Plain text đúng nhưng HTML lỗi ký tự tiếng Việt

Giả sử `text/plain; charset=UTF-8` đọc đúng, nhưng nhánh HTML khai báo `charset=ISO-8859-1` trong khi bytes của nó thực tế là UTF-8. Vấn đề nằm tại **part HTML**, không phải root multipart. Cần tạo nội dung bằng charset đúng và để thư viện mã hóa content transfer tương ứng.

Không sửa bằng cách đoán ký tự thay thế trong HTML; trước tiên kiểm tra bytes trước/ sau transfer decoding và header của part tương ứng. Nếu nội dung đã sai ngay trước khi đưa vào `MimeMessageHelper` thì sửa nguồn/template thay vì thay MIME header để che lỗi.

### 10.4. PDF nằm trong nhánh alternative và làm mất body

~~~text
multipart/alternative
├── text/html
└── application/pdf
~~~

Điều này nói rằng PDF là một **lựa chọn thay thế** cho HTML, khác ý định gửi PDF như một tệp độc lập. Phân tách đúng:

~~~text
multipart/mixed
├── text/html
└── application/pdf
    Content-Disposition: attachment
~~~

Nếu còn cần plain text và inline image, body ở nhánh thứ nhất có thể tiếp tục là một cây `alternative`/`related` riêng.

### 10.5. Email đúng khi tạo ở Spring nhưng sai ở hộp thư đích

Nếu cây tại thời điểm `message.writeTo(...)` khác cây trong `.eml` người nhận xuất ra, khả năng cần điều tra gồm dịch vụ gửi mail, bộ lọc quét tệp, relay, mail gateway, mailing list hoặc hệ thống thêm chữ ký/disclaimer. Không nên sửa `setText(...)` trước khi có căn cứ khác biệt đó. Ngược lại, nếu cây trước/sau giống nhau và chỉ một phần mềm mail hiển thị sai, trọng tâm chuyển sang hành vi client và nội dung HTML/CSS.

## 11. Những tình huống MIME đặc biệt

**Message đính kèm (`message/rfc822`).** Một part có thể chứa nguyên một email khác. Khi đó phải duyệt thành cây con riêng; không tự động coi toàn bộ các `text/html` tìm được trong thư lồng là body chính của email ngoài.

**Email ký số hoặc mã hóa (S/MIME).** Có thể gặp `multipart/signed`, `application/pkcs7-mime` hoặc các dạng nội dung bảo vệ khác. Thư mã hóa không thể inspect plaintext tree bên trong nếu chưa giải mã hợp lệ. Với thư ký số, việc sửa part/boundary có thể làm chữ ký không còn kiểm chứng được. Chỉ phân tích và biến đổi trong phạm vi cho phép.

**Cấu trúc MIME hợp lệ nhưng HTML không tương thích.** Email client có thể loại bỏ JavaScript, CSS phức tạp, form và ảnh tải từ xa. Tree đúng không bảo đảm mọi thuộc tính HTML được hiển thị giống trình duyệt. Cần thiết kế email HTML đơn giản, có plain text và thử trên client mục tiêu.

**MIME parser chấp nhận thư lỗi ở các mức khác nhau.** Một client có thể dung sai với boundary sai hoặc header không chuẩn, client khác thì không. Khi gặp khác biệt, luôn giữ bản raw `.eml` và xem cả cách thư viện parse lẫn nội dung gốc.

**Tên tệp và Content-ID không phải dữ liệu vô hại.** Chúng có thể chứa thông tin dự án, địa chỉ email hoặc chuỗi định danh. Khi chia sẻ tree debug, che dữ liệu nhạy cảm nhưng vẫn giữ những phần cấu trúc cần đối chiếu, ví dụ sử dụng cặp ID nhất quán đã được thay tên.

## 12. Cách kết luận nguyên nhân sau khi đã xem tree

Một kết luận hữu ích nên mô tả **hiện tượng, bằng chứng từ MIME tree và thay đổi cần thiết**, thay vì chỉ nói “HTML lỗi”.

Ví dụ:

> Ở bản `.eml` nhận được, root `multipart/mixed` chứa hai part `text/plain` và `text/html` cùng cấp. Chúng là hai phiên bản của một nội dung nhưng chưa được bọc trong `multipart/alternative`. Một client đang hiển thị cả hai. Cần tạo body qua `MimeMessageHelper.setText(plain, html)` để biểu diễn đúng quan hệ alternative, rồi kiểm tra lại tree ở bản thư gửi thử.

Ví dụ khác:

> Part HTML tham chiếu `cid:logo-a` nhưng part ảnh có `Content-ID: <logo-b>`. Ảnh không hiển thị vì tham chiếu không tìm thấy tài nguyên tương ứng. Cần dùng cùng một Content-ID trong HTML và `addInline(...)`, bảo đảm ảnh nằm trong nhóm MIME liên quan và kiểm tra lại trên client đích.

Qua hai ví dụ, có thể thấy **cây MIME là chứng cứ cấu trúc** kết nối code Spring Mail với cách email client hiển thị thông điệp. Quy trình chẩn đoán hiệu quả là đọc bản email thực, duyệt từ root đến từng part, xác định quan hệ `mixed`/`alternative`/`related`, kiểm tra header và tham chiếu, rồi so sánh với ý định tạo message trong Spring. Nhờ đó có thể phân biệt lỗi từ cấu trúc MIME, dữ liệu phần nội dung, đường vận chuyển và giới hạn của ứng dụng đọc mail.
