# Headers do ứng dụng tự đặt và rủi ro xung đột

Khi dùng **Spring Framework Mail**, ứng dụng có thể chủ động đặt người gửi, người nhận, tiêu đề, địa chỉ trả lời và một số **header tùy chỉnh** để phân loại hoặc theo dõi email. Tuy nhiên, email không chỉ có các header do ứng dụng tạo ra. Thư viện Jakarta Mail, máy chủ SMTP, dịch vụ gửi thư và các máy chủ chuyển tiếp cũng có thể **sinh, bổ sung, chuẩn hóa hoặc thay đổi header** trong những giai đoạn khác nhau.

Nếu ứng dụng tự ghi một header đã có chủ sở hữu, tạo nhiều bản của một trường vốn chỉ nên xuất hiện một lần, hoặc ghi dữ liệu không hợp lệ, email có thể bị đọc sai, từ chối, lọc vào spam hay mất khả năng đối chiếu trạng thái. Nguy hiểm hơn, nếu đưa dữ liệu không tin cậy thẳng vào header, ứng dụng có thể gặp rủi ro **email header injection**.

Bài học tập trung vào ba câu hỏi:

1. Ứng dụng được tự đặt **những header nào và bằng API nào**?
2. Những header nào nên để **Spring/Jakarta Mail hoặc hạ tầng email** quản lý?
3. Làm thế nào để tránh **xung đột giá trị, trùng lặp header, lộ dữ liệu và sai định dạng**?

## 1. Header của email là gì?

Một thông điệp email có **message header** ở đầu và **body** ở phía sau, ngăn cách bằng một dòng trống. Header chứa các trường như `From`, `To`, `Subject`, `Date` và `Message-ID`. Với email MIME, header còn mô tả định dạng nội dung bằng `MIME-Version`, `Content-Type` và các trường liên quan.

Ví dụ khái niệm về một email dạng thô:

```eml
From: Store <notifications@example.org>
To: customer@example.net
Reply-To: support@example.org
Subject: Order confirmed
Date: Thu, 12 Nov 2026 08:00:00 +0000
Message-ID: <sample-123@example.org>
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
X-App-Event-ID: 550e8400-e29b-41d4-a716-446655440000

Your order has been confirmed.
```

Thông điệp trên chỉ để minh họa cấu trúc. Trong thực tế, nhiều header và cách mã hóa nội dung được thư viện hoặc máy chủ gửi tạo tự động. Không cần tự ghép những dòng trên thành một chuỗi để gửi mail.

### Phân biệt message header với SMTP envelope

**Message header** là phần nội dung email có thể được truyền đến người nhận. **SMTP envelope** là các địa chỉ dùng trong phiên truyền SMTP để định tuyến thư:

```text
SMTP envelope:
    MAIL FROM:<bounces@example.org>
    RCPT TO:<customer@example.net>

Message headers:
    From: Store <notifications@example.org>
    To: customer@example.net
    Reply-To: support@example.org
    Subject: Order confirmed
```

Hai nhóm thông tin có liên quan nhưng **không đồng nhất**:

- Header `From` cho người đọc biết danh tính người gửi được trình bày trong thư.
- SMTP `MAIL FROM` là địa chỉ envelope sender, thường liên quan đến nơi nhận báo lỗi phát thư.
- Header `To`/`Cc` phục vụ cách hiển thị, còn `RCPT TO` là những địa chỉ thực sự được đưa vào phiên SMTP.
- Người nhận **Bcc** có thể có mặt trong envelope, nhưng thường không xuất hiện trong các header của bản thư giao cho người khác.

Vì vậy, thêm một header tên `Return-Path` hoặc `To` bằng cách tự nối chuỗi **không phải cách phù hợp để điều khiển envelope**. Hãy dùng API gửi thư và cấu hình SMTP tương ứng.

## 2. Ai là bên quản lý từng loại header?

Không có một “người tạo header” duy nhất trong toàn bộ hành trình email.

```text
Ứng dụng Spring
   |
   | Chọn From, To, Subject, Reply-To;
   | thêm header ứng dụng được phép
   v
JavaMailSender + MimeMessageHelper + Jakarta Mail
   |
   | Tạo cấu trúc MIME, định dạng header,
   | mã hóa Unicode, sinh các trường cần thiết
   v
SMTP submission / nhà cung cấp email
   |
   | Kiểm tra quyền gửi, có thể chuẩn hóa,
   | thêm header riêng và ký DKIM
   v
MTA trung gian / MTA phía nhận
   |
   | Thêm Received và metadata vận chuyển;
   | kiểm tra xác thực và áp dụng chính sách
   v
Mail server / mailbox phía nhận
   |
   | Ghi nhận kết quả, có thể thêm
   | Authentication-Results và dấu vết khác
   v
Mail client của người nhận
```

Một bảng phân chia trách nhiệm thực dụng:

| Trường | Vai trò chính | Cách sử dụng ưu tiên trong ứng dụng Spring |
| --- | --- | --- |
| `From` | Danh tính tác giả/người gửi hiển thị | `MimeMessageHelper.setFrom(...)` với địa chỉ được phép |
| `To`, `Cc`, `Bcc` | Người nhận ở từng nhóm | `setTo(...)`, `setCc(...)`, `setBcc(...)` |
| `Reply-To` | Địa chỉ gợi ý nhận phản hồi | `setReplyTo(...)` |
| `Subject` | Chủ đề thông điệp | `setSubject(...)` |
| `Sender` | Danh tính tác nhân gửi khi khác tác giả trong trường hợp thích hợp | Chỉ đặt nếu hiểu chính xác ngữ nghĩa và chính sách provider |
| `Date` | Ngày tạo/gửi của thông điệp | Thường để thư viện thiết lập; chỉ tùy chỉnh khi có yêu cầu đặc biệt |
| `Message-ID` | Định danh thông điệp theo chuẩn email | Thường để thư viện/hạ tầng sinh; không dùng làm ID nghiệp vụ duy nhất |
| `MIME-Version` | Báo thông điệp dùng MIME | Để Jakarta Mail quản lý |
| `Content-Type`, `Content-Transfer-Encoding`, `Content-Disposition` | Kiểu dữ liệu, transfer encoding và cách xử lý MIME part | Dùng `MimeMessageHelper`, `setText(...)`, `addAttachment(...)` |
| `Received` | Dấu vết vận chuyển qua các máy chủ | Do các MTA thêm; ứng dụng không tự giả lập |
| `Return-Path` | Thường được thêm ở bước giao cuối cùng từ envelope sender | Điều khiển envelope qua cấu hình gửi phù hợp, không tự gắn header |
| `DKIM-Signature` | Chữ ký xác thực miền | Thường để bộ ký của dịch vụ gửi/MTA thêm sau khi nội dung ổn định |
| `Authentication-Results` | Kết quả kiểm tra xác thực tại hệ thống nhận | Do hệ thống kiểm tra có thẩm quyền thêm |
| Header ứng dụng như `X-App-Event-ID` | Metadata phục vụ tương quan, phân loại riêng | Có thể dùng `MimeMessage.setHeader(...)` với giá trị đã kiểm soát |

Đây là **hướng dẫn phân quyền theo vai trò**, không phải quy định rằng ứng dụng tuyệt đối không bao giờ được can thiệp vào các trường chuẩn. Có những nghiệp vụ chuyên biệt phải đặt một số trường đó; khi ấy cần hiểu rõ quy tắc RFC, hành vi thư viện và chính sách SMTP provider.

## 3. Những header ứng dụng có thể chủ động đặt

### 3.1. Dùng API chuyên dụng cho các trường chuẩn

Trong Spring Mail, ứng dụng nên sử dụng `MimeMessageHelper` cho các trường có ngữ nghĩa rõ ràng:

```java
helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setReplyTo("support@example.org");
helper.setSubject("Xác nhận đơn hàng");
helper.setText("Đơn hàng của bạn đã được xác nhận.", false);
```

Các API này giúp thư viện xử lý địa chỉ, ký tự quốc tế, định dạng header và cấu trúc MIME phù hợp. Khi địa chỉ hoặc nội dung đến từ người dùng, ứng dụng vẫn phải kiểm tra dữ liệu nghiệp vụ và quyền gửi; API tiện ích không thay thế việc kiểm soát đầu vào.

Với `Bcc`, hãy dùng `helper.setBcc(...)`. Việc tự thêm dòng `Bcc: ...` vào chuỗi raw message có thể tạo ra header hiển thị ngoài ý muốn hoặc gây sai lệch so với danh sách người nhận envelope.

### 3.2. Custom headers để gắn metadata

Các hệ thống gửi email giao dịch có thể cần liên kết một thông điệp với sự kiện tạo ra nó. Ví dụ:

```text
X-App-Event-ID: 550e8400-e29b-41d4-a716-446655440000
X-App-Notification-Type: order-confirmation
X-App-Environment: production
```

Những trường này có thể giúp:

- Đối chiếu bản email đã gửi với yêu cầu nghiệp vụ trong hệ thống.
- Nhận diện loại thông báo khi xem raw message hoặc bản sao trong môi trường kiểm thử.
- Gắn một khóa liên hệ giữa log ứng dụng và log của dịch vụ gửi, khi dịch vụ đó lưu và trả lại custom headers.
- Hỗ trợ luồng xử lý nội bộ có thỏa thuận rõ về tên và ý nghĩa header.

**Không phải mọi SMTP provider đều giữ nguyên hoặc trả custom header trong webhook.** Có nhà cung cấp sử dụng metadata/tagging API riêng đáng tin cậy hơn. Nếu workflow phụ thuộc việc đọc lại một header, cần xem hợp đồng và tài liệu của provider.

#### Có bắt buộc đặt tiền tố `X-` không?

Không. Tiền tố `X-` là một **tập quán lâu đời** với header tự định nghĩa. Nhưng không có quy tắc rằng mọi trường tùy chỉnh đều phải bắt đầu bằng `X-`; hướng dẫn hiện đại về extensibility cũng không khuyến khích mặc định dùng tiền tố này cho mọi trường mới.

Có thể chọn tên rõ phạm vi, ví dụ `App-Event-ID` hoặc `X-App-Event-ID`, tùy quy ước của hệ thống và khả năng provider. Quan trọng hơn tiền tố là:

1. Tên không đụng trường chuẩn đã có ý nghĩa riêng hoặc trường do provider dành riêng.
2. Mọi bên sử dụng hiểu thống nhất định dạng và ý nghĩa.
3. Giá trị không chứa bí mật hoặc dữ liệu không nên tiết lộ cho người nhận.
4. Đặt header bằng API có kiểm soát thay vì tự ghép raw email.

### 3.3. Một số header chuẩn có thể cần đặt theo nghiệp vụ

Không phải header chuẩn nào cũng luôn được sinh tự động. Một vài trường có thể do ứng dụng chỉ định **khi có yêu cầu rõ**:

| Header | Tình huống phù hợp | Lưu ý |
| --- | --- | --- |
| `Reply-To` | Người gửi muốn thư trả lời đi tới bộ phận hỗ trợ | Khác với `From`; dùng helper |
| `Auto-Submitted: auto-generated` | Đánh dấu thông điệp tự động theo ngữ nghĩa phù hợp | Không bảo đảm mọi mail client bỏ qua auto-reply hay chống spam |
| `List-ID` | Phân biệt một mailing list thực sự | Không dùng bừa cho email giao dịch |
| `List-Unsubscribe` | Cung cấp địa chỉ hoặc URL hủy đăng ký cho luồng thư phù hợp | Chỉ đặt khi có cơ chế hủy đăng ký hoạt động |
| `List-Unsubscribe-Post` | Cung cấp cơ chế one-click theo quy ước tương ứng | Phải triển khai endpoint/luồng đúng; chỉ header là chưa đủ |
| `In-Reply-To`, `References` | Email là phần tiếp nối một chuỗi trao đổi | Dựa vào Message-ID hợp lệ của thông điệp liên quan |

Ví dụ, một header `List-Unsubscribe` trỏ tới URL chết sẽ tạo trải nghiệm sai và có thể vi phạm kỳ vọng của hệ thống nhận. Còn việc yêu cầu xác nhận đã đọc qua một header không biến sự kiện “đã mở thư” thành bằng chứng chắc chắn.

## 4. Rủi ro xung đột header là gì?

**Xung đột header** xảy ra khi hai thành phần dùng cùng một trường nhưng có giá trị hoặc kỳ vọng khác nhau, hoặc khi một trường bị đặt sai vị trí, sai số lần xuất hiện, sai định dạng.

Ví dụ một ứng dụng tự đặt:

```text
Content-Type: text/plain; charset=UTF-8
```

rồi sau đó dùng `helper.setText(html, true)` để tạo HTML. Nếu code hoặc thư viện thay đổi `Content-Type` thành `text/html`, kỳ vọng của hai bên mâu thuẫn. Nếu header bị nhân đôi thành hai giá trị khác nhau, mail client có thể giải thích không thống nhất.

Một số dạng xung đột tiêu biểu:

- **Hai nguồn cùng thiết lập:** ứng dụng đặt `Date` hoặc `Message-ID`, sau đó thư viện/provider sinh lại.
- **Trùng một trường:** dùng `addHeader` nhiều lần cho trường vốn chỉ nên có một giá trị.
- **Giá trị không khớp body:** khai báo `charset`, `Content-Type` hoặc `Content-Transfer-Encoding` không tương ứng dữ liệu thật.
- **Xung đột với chính sách sender:** ứng dụng đặt `From` ngoài danh tính đã xác minh của SMTP account.
- **Xung đột với bộ ký xác thực:** sửa nội dung/header đã ký làm DKIM không còn kiểm tra đúng.
- **Metadata bị hiểu sai:** tự đặt `Received` hoặc `Authentication-Results` như thể do máy chủ tin cậy tạo ra.
- **Provider xử lý lại:** nhà cung cấp đổi `Message-ID`, thêm tag hoặc loại bỏ một custom header.
- **Dữ liệu đầu vào phá cấu trúc:** chuỗi có CR/LF được đưa vào tên hoặc giá trị header.

Không phải mọi xung đột đều gây ngoại lệ ở phía ứng dụng. Một số chỉ biểu hiện khi email đến máy chủ nhận hoặc mail client, khiến lỗi khó tìm hơn.

## 5. `setHeader` và `addHeader` khác nhau

Trong Jakarta Mail, `MimeMessage` có các phương thức thao tác trực tiếp với header:

```java
mimeMessage.setHeader("X-App-Event-ID", eventId);
mimeMessage.addHeader("X-App-Tag", "notification");
mimeMessage.addHeader("X-App-Tag", "order");
```

Ý nghĩa cơ bản:

| API | Tác động | Khi nào dùng |
| --- | --- | --- |
| `setHeader(name, value)` | Đặt giá trị cho header; thay các giá trị hiện có với tên tương ứng | Một header ứng dụng cần **một giá trị xác định** |
| `addHeader(name, value)` | Thêm một giá trị/occurrence của header | Chỉ khi định dạng và ngữ nghĩa trường đó cho phép nhiều giá trị |
| `getHeader(name)` | Truy xuất giá trị header hiện có | Khi cần đọc dữ liệu trong môi trường có kiểm soát |
| `removeHeader(name)` | Xóa header theo tên | Chỉ khi thực sự quản lý trường đó và hiểu tác động |

**Tên header không phân biệt chữ hoa/chữ thường theo ngữ nghĩa email**. `X-App-Event-ID` và `x-app-event-id` không phải hai trường độc lập.

### 5.1. Khi nào lặp header là nguy hiểm?

Giả sử đoạn code:

```java
mimeMessage.addHeader("Subject", "Order received");
mimeMessage.addHeader("Subject", "Reset your password");
```

Điều này tạo nguy cơ có nhiều trường `Subject` trái ngữ nghĩa. Một mail client có thể chọn giá trị đầu, giá trị sau, từ chối hoặc hiển thị khác dự kiến. Với `Subject`, hãy dùng `helper.setSubject(...)` **một lần cho kết quả cuối cùng**.

Tương tự, `From` và `Message-ID` có quy tắc cú pháp riêng và không nên dùng `addHeader` như một danh sách nhãn. Nếu cần nhiều người nhận, hãy dùng API đặt danh sách địa chỉ, thay vì lặp `To` tùy tiện.

Tuy nhiên, **không phải mọi header lặp đều sai**. Chẳng hạn, mỗi máy chủ trên đường vận chuyển có thể thêm một dòng `Received` mới. Đó là phần của cơ chế trace hợp lệ, nhưng ứng dụng không nên tự giả lập các dòng này.

### 5.2. Nếu một metadata có nhiều giá trị?

Với metadata ứng dụng, thay vì tùy tiện tạo nhiều header trùng tên:

```text
X-App-Tag: invoice
X-App-Tag: priority
```

có thể định nghĩa một định dạng duy nhất:

```text
X-App-Tags: invoice, priority
```

hoặc dùng hai tên tách biệt có ngữ nghĩa rõ:

```text
X-App-Notification-Type: invoice
X-App-Processing-Class: priority
```

Chọn một phương án và định nghĩa cách parse ở cả nơi ghi lẫn nơi đọc. Danh sách phân tách dấu phẩy **không mặc nhiên đúng với mọi header**; đó phải là quy ước của chính custom field được ứng dụng định nghĩa.

## 6. Vì sao không nên tự sửa các MIME headers?

Với thư chỉ chứa text, phần body có thể được mô tả bằng:

```text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
```

Nhưng với thư gồm HTML và một PDF, cấu trúc có thể là:

```text
Top-level message:
    Content-Type: multipart/mixed; boundary=...
        |
        +-- multipart/alternative; boundary=...
        |       |
        |       +-- text/plain; charset=UTF-8
        |       |
        |       +-- text/html; charset=UTF-8
        |
        +-- application/pdf
            Content-Transfer-Encoding: base64
            Content-Disposition: attachment; filename=...
```

Mỗi MIME part có thể có `Content-Type` và `Content-Transfer-Encoding` riêng. Nếu chỉ thay header `Content-Type` **ngoài cùng** thành `text/html` vì muốn “email hỗ trợ HTML”, toàn bộ multipart structure có thể bị hiểu sai hoặc không đọc được attachment.

**Cách đúng trong Spring:** sử dụng `MimeMessageHelper` để tạo nội dung:

```java
helper.setText(
    "Nội dung văn bản thuần.",
    "<p>Nội dung <strong>HTML</strong>.</p>"
);
helper.addAttachment(
    "invoice.pdf",
    new ByteArrayResource(pdfBytes),
    "application/pdf"
);
```

Để dùng cả text/HTML và attachment, helper cần được tạo ở chế độ multipart phù hợp. Thư viện sẽ quản lý `boundary` và các header MIME của từng phần.

Tránh kiểu code sau:

```java
// Sai hướng tiếp cận: tùy ý ghi đè Content-Type
mimeMessage.setHeader("Content-Type", "text/html");

// Sau đó lại dùng helper để tạo multipart/attachment
helper.addAttachment("invoice.pdf", resource);
```

Phương thức cuối có thể khiến thư viện tổ chức lại MIME tree, làm header tự đặt không còn phù hợp với body. Việc sửa raw message bằng string replacement sau khi thư viện đóng gói còn nguy hiểm hơn.

### Charset và transfer encoding cũng phải đồng bộ

Nếu part có nội dung UTF-8 chứa tiếng Việt nhưng ứng dụng khai báo `charset=US-ASCII`, người nhận có thể thấy ký tự sai. Nếu byte được base64-encode nhưng header lại ghi `quoted-printable`, mail client sẽ giải mã bằng thuật toán sai.

Không nên tự base64 `String`, gán nó làm text rồi ép thêm header `Content-Transfer-Encoding: base64`; dễ tạo **mã hóa hai lần**. Hãy đưa nội dung gốc cho Jakarta Mail và để thư viện quyết định transfer encoding phù hợp.

## 7. Xung đột với `Date`, `Message-ID` và các header do hạ tầng sinh

### 7.1. `Message-ID` không phải ID sự kiện nghiệp vụ

`Message-ID` là định danh của thông điệp email theo định dạng được quy định. Thư viện hoặc máy chủ có thể tạo giá trị này trong quá trình hoàn tất/gửi message. Một số nhà cung cấp còn có **provider message ID** riêng trong hệ thống theo dõi giao thư.

Ví dụ ứng dụng xử lý đơn hàng `ORD-2026-105`, tạo hai email độc lập:

```text
Business event: ORD-2026-105
   |
   +-- email xác nhận đơn hàng ----> Message-ID A
   |
   +-- email hóa đơn --------------> Message-ID B
```

Nếu email được thử gửi lại, hệ thống có thể tạo message mới với `Message-ID` khác. Vì vậy:

- Dùng **business event ID** hoặc **notification ID** trong database để theo dõi trạng thái và chống gửi trùng theo chính sách ứng dụng.
- Có thể thêm custom header `X-App-Event-ID` để hỗ trợ liên hệ giữa email và event.
- Lưu provider ID hoặc SMTP queue ID riêng khi được cung cấp.
- Không giả định `Message-ID` luôn bất biến qua mọi lớp provider hoặc luôn là định danh mà webhook trả về.

Nếu tự đặt `Message-ID` thủ công rồi thư viện chạy `saveChanges()` hoặc nhà cung cấp xử lý lại, giá trị cuối có thể khác kỳ vọng. Hãy để thư viện/hạ tầng đảm nhiệm trừ khi có yêu cầu giao thức rõ ràng và hiểu cách chúng xử lý.

### 7.2. `Date` và múi giờ

`Date` là một header chuẩn chứa thời điểm được biểu diễn theo cú pháp ngày giờ của email. `MimeMessage` và hạ tầng có thể điền hoặc sửa trường này.

Một bản ghi thời gian nghiệp vụ như `createdAt`, `orderConfirmedAt` hay `processedAt` cần được lưu riêng trong hệ thống. Không dùng `Date` như nguồn duy nhất để chứng minh thời điểm tạo đơn hàng, vì nó gắn với thông điệp email và có thể khác thời điểm phát sinh nghiệp vụ.

### 7.3. `Received` và `Authentication-Results` thuộc miền tin cậy khác

MTA thường **thêm** `Received` khi thư đi qua nó; các hệ thống nhận có thể thêm `Authentication-Results` mô tả kết quả SPF, DKIM, DMARC. Một ví dụ khái niệm:

```text
Received: from relay.example.org by mx.example.net ...
Authentication-Results: mx.example.net; dkim=pass ...
```

Ứng dụng gửi mail **không nên tự đặt các trường này để tuyên bố** thư đã đi qua máy chủ nào hoặc đã qua kiểm tra xác thực. Các hệ thống nhận phải áp dụng ranh giới tin cậy riêng cho thông tin trace/authentication, vì header do bên gửi tự cung cấp có thể bị giả mạo.

### 7.4. `Return-Path` là hệ quả của envelope sender

`Return-Path` trong thư đã giao thường phản ánh **SMTP envelope sender** tại thời điểm giao cuối cùng. Tự gọi:

```java
mimeMessage.setHeader("Return-Path", "bounces@example.org");
```

không đảm bảo bounce sẽ được chuyển tới địa chỉ đó. Envelope sender được xác định ở tầng giao tiếp SMTP và có thể do nhà cung cấp kiểm soát.

Với Jakarta Mail SMTP transport, có những thuộc tính điều khiển envelope sender như `mail.smtp.from` khi endpoint hỗ trợ, nhưng chúng có phạm vi và quy tắc riêng; không dùng raw header như một cách thay thế. Nếu dùng nhà cung cấp mail qua API hoặc relay được quản lý, nên cấu hình return-path/bounce domain theo cơ chế chính thức của nhà cung cấp.

### 7.5. `DKIM-Signature` và thứ tự sửa thông điệp

DKIM ký một số header và body theo cơ chế xác thực miền. Nếu thông điệp bị sửa **sau khi ký**, chữ ký có thể không còn hợp lệ tùy nội dung được ký và cách canonicalization.

```text
Ứng dụng tạo MIME message
        |
        v
Thư viện hoàn thiện headers/body
        |
        v
Provider / MTA ký DKIM
        |
        v
SMTP relay -> hệ thống nhận kiểm tra DKIM
```

Do đó, không nên tự gắn `DKIM-Signature` như một nhãn tùy chỉnh; cũng không nên tự ý sửa các header/body đã ký ở một relay trung gian. Cấu hình ký DKIM thường thuộc phần hạ tầng gửi, nơi có domain, khóa và chính sách phù hợp.

## 8. Header injection: rủi ro khi nhận dữ liệu không tin cậy

Header email là các dòng dạng `Field-Name: value`. Nếu ứng dụng ghép trực tiếp dữ liệu bên ngoài vào raw header mà không kiểm soát ký tự xuống dòng, kẻ tấn công có thể cố gắng làm xuất hiện **header mới** hoặc thay đổi cấu trúc thông điệp.

Ví dụ nguy hiểm về mặt ý tưởng:

```text
X-App-Customer-Name: Alice
Bcc: unknown-recipient@example.net
```

Nếu `Alice` thực chất là dữ liệu người dùng được nối kèm ký tự xuống dòng rồi `Bcc: ...`, hệ thống ghép raw header thiếu an toàn có thể hiểu thành hai trường. Tương tự, chèn dòng trống có thể đẩy phần sau vào body. Mức độ khai thác thực tế phụ thuộc thư viện và cách serialize; **không được coi bộ lọc của mail client là cơ chế bảo vệ ứng dụng**.

### Quy tắc phòng tránh

1. **Không tự xây raw headers bằng string concatenation** từ input bên ngoài.
2. **Không để người dùng tùy ý chọn tên header**; đặt danh sách tên cố định trong code.
3. **Giới hạn giá trị** theo cấu trúc mong đợi: UUID, mã sự kiện, enum hoặc mã tracking ngắn.
4. **Từ chối CR, LF và ký tự điều khiển không phù hợp** trong giá trị đưa vào custom header.
5. Dùng API địa chỉ, chủ đề, nội dung chuyên dụng của Jakarta Mail/Spring; không chèn giá trị vào chuỗi gồm nhiều dòng `Header: value`.
6. Giới hạn độ dài để tránh log quá lớn hoặc hành vi không nhất quán giữa provider.
7. Chỉ gắn metadata thực sự cần thiết; không đưa secret hoặc PII nhạy cảm vào header.

Đây cũng là lý do nên dùng **giá trị có kiểu** thay vì một chuỗi tự do. Ví dụ, `UUID#toString()` cho ra tập ký tự đơn giản, xác định; một `NotificationType` enum có danh sách giá trị hữu hạn và dễ kiểm soát.

## 9. Ví dụ Spring Boot: đặt custom header an toàn

Phần này dùng **Spring Boot và Spring Framework Mail** với `JavaMailSender`. Mục tiêu là gửi một email giao dịch có `From`, `To`, `Reply-To`, `Subject` và hai custom headers phục vụ đối chiếu. Các header kỹ thuật còn lại do Jakarta Mail/provider xử lý.

### 9.1. Dependency và cấu hình

Với Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

Cấu hình `application.yml` minh họa SMTP submission qua cổng 587:

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
    from: ${MAIL_FROM_ADDRESS}
    reply-to: ${MAIL_REPLY_TO_ADDRESS}
```

Đây là cấu hình giả định SMTP server hỗ trợ STARTTLS và xác thực trên 587. Những endpoint dùng implicit TLS trên 465 sẽ có cấu hình khác. Các credential cần được truyền từ biến môi trường hoặc secret của môi trường chạy, không lưu trực tiếp trong source.

### 9.2. Đặt header theo đúng nguồn sở hữu

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

@Service
public class OrderNotificationMailService {

    private static final String HEADER_EVENT_ID = "X-App-Event-ID";
    private static final String HEADER_TYPE = "X-App-Notification-Type";

    private final JavaMailSender mailSender;
    private final String fromAddress;
    private final String replyToAddress;

    public OrderNotificationMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress,
            @Value("${app.mail.reply-to}") String replyToAddress
    ) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
        this.replyToAddress = replyToAddress;
    }

    public void sendOrderConfirmed(
            String recipientAddress,
            UUID notificationId
    ) {
        mailSender.send(message -> {
            MimeMessageHelper helper = new MimeMessageHelper(
                    message,
                    StandardCharsets.UTF_8.name()
            );

            // Các message headers chuẩn: dùng API chuyên dụng.
            helper.setFrom(fromAddress);
            helper.setTo(recipientAddress);
            helper.setReplyTo(replyToAddress);
            helper.setSubject("Đơn hàng của bạn đã được xác nhận");
            helper.setText(
                    "Xin chào. Đơn hàng của bạn đã được xác nhận.",
                    false
            );

            // Metadata ứng dụng: tên cố định, giá trị có kiểu.
            message.setHeader(HEADER_EVENT_ID, notificationId.toString());
            message.setHeader(HEADER_TYPE, "order-confirmation");
        });
    }
}
```

Ý nghĩa thiết kế:

- `MimeMessageHelper` nhận trách nhiệm gán những header chuẩn và nội dung text.
- Hai custom header có **tên cố định**, không lấy từ query parameter hoặc form tùy ý.
- `notificationId` là UUID; dạng chuỗi của nó không chứa xuống dòng để chèn header.
- Giá trị `order-confirmation` là hằng số đã biết.
- Code **không tự đặt** `Message-ID`, `Date`, `Received`, `Return-Path`, `DKIM-Signature` hay các MIME encoding headers.
- Những giá trị như `recipientAddress`, `fromAddress` và `replyToAddress` vẫn cần được xác minh trong quy trình nghiệp vụ và cấu hình hệ thống.

`JavaMailSender.send(MimeMessagePreparator)` cho phép chuẩn bị `MimeMessage` qua callback. Bên trong callback, có thể dùng `MimeMessageHelper` để thiết lập các trường thông dụng, rồi gọi `message.setHeader(...)` cho metadata tùy chỉnh. Khi gửi, thư viện/provider sẽ hoàn tất những chi tiết giao thức còn lại.

Trong Spring Framework thuần, có thể cấu hình một implementation `JavaMailSender` và Jakarta Mail tương ứng; phần thao tác `MimeMessage` vẫn theo cùng nguyên tắc.

### 9.3. Nếu cần kiểm tra một giá trị custom header tự do

Giả sử hệ thống cho phép một mã chiến dịch ngắn từ upstream. Đây là metadata cần giữ, nhưng đầu vào **không phải** một UUID có kiểu. Có thể áp dụng allowlist ký tự:

```java
import java.util.regex.Pattern;

private static final Pattern SAFE_CAMPAIGN_KEY =
        Pattern.compile("[A-Za-z0-9_-]{1,64}");

private static String requireSafeCampaignKey(String value) {
    if (value == null || !SAFE_CAMPAIGN_KEY.matcher(value).matches()) {
        throw new IllegalArgumentException("Invalid campaign key");
    }
    return value;
}
```

Và chỉ đặt trường do ứng dụng quy định:

```java
message.setHeader(
        "X-App-Campaign-Key",
        requireSafeCampaignKey(campaignKey)
);
```

Regex này là một **ví dụ chính sách cho mã ứng dụng**, không phải cú pháp bắt buộc cho mọi header email. Một trường có định dạng khác có thể cần validation khác, nhưng vẫn phải loại trừ ký tự điều khiển và cú pháp không mong muốn.

### 9.4. Cùng email nhưng có HTML và attachment

Nếu cần thêm HTML và PDF, không tự cập nhật `Content-Type` sau ví dụ trên. Thay vào đó, tạo helper ở chế độ multipart:

```java
import org.springframework.core.io.ByteArrayResource;

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name()
);

helper.setFrom(fromAddress);
helper.setTo(recipientAddress);
helper.setSubject("Hóa đơn của bạn");
helper.setText(
        "Hóa đơn được đính kèm trong email.",
        "<p><strong>Hóa đơn</strong> được đính kèm trong email.</p>"
);
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);

message.setHeader("X-App-Event-ID", notificationId.toString());
```

Những đoạn code này là phần thân logic chuẩn bị message, giả sử biến `message`, `fromAddress`, `recipientAddress`, `pdfBytes` và `notificationId` đã có trong phạm vi method. Việc tạo `multipart`, `boundary`, transfer encoding và header của attachment do thư viện xử lý.

**Không nên gọi `message.setHeader("Content-Type", "text/html")` để “sửa” email sau khi thêm attachment.** `Content-Type` của message ngoài cùng sẽ cần phản ánh cấu trúc multipart, chứ không chỉ phần HTML bên trong.

## 10. Đọc kết quả: header nào có thể thay đổi sau khi gửi?

Hãy phân biệt ba góc nhìn khi quan sát email:

1. **Trước gửi:** đối tượng `MimeMessage` trong ứng dụng có các trường do code đặt; một số header tự động chưa được hoàn thiện.
2. **Sau SMTP submission:** máy chủ gửi có thể thêm trace, queue ID, sửa một số trường theo chính sách hoặc ký DKIM.
3. **Khi nằm trong mailbox:** thư có thể đã đi qua nhiều MTA và được thêm `Received`, `Authentication-Results` hoặc metadata riêng của dịch vụ.

Ví dụ, cùng một email có thể xuất hiện như sau:

```text
Ứng dụng tạo:
  From: notifications@example.org
  X-App-Event-ID: 550e8400-e29b-41d4-a716-446655440000

Thư viện/provider hoàn tất:
  Date: ...
  Message-ID: ...
  MIME-Version: ...
  Content-Type: ...

Máy chủ gửi/nhận bổ sung:
  Received: ...
  DKIM-Signature: ...
  Authentication-Results: ...
```

Không suy ra rằng mọi trường đều sẽ được thêm ở đúng chặng này trong tất cả hệ thống. Ví dụ, một dịch vụ gửi có thể ký DKIM tại điểm khác trong hạ tầng của mình.

### Header ứng dụng có phải bằng chứng đáng tin cậy?

Một `X-App-Event-ID` do chính ứng dụng gửi tạo hữu ích cho **correlation**. Nhưng nếu ứng dụng nhận email từ Internet rồi dựa vào header đó để cấp quyền truy cập, giải ngân hoặc xác nhận tác vụ, kẻ gửi bên ngoài có thể **tự giả mạo giá trị header**.

Header đi qua email là dữ liệu do bên gửi có thể kiểm soát. Để xác thực một thông điệp hoặc chấp nhận hành động nhạy cảm, phải dùng các bằng chứng phù hợp như danh tính đã xác thực, chữ ký, token một lần, quyền trong backend hoặc cơ chế kiểm chứng khác. Custom header tự thân **không phải authentication token**.

## 11. Bảo mật và riêng tư: đừng đưa bí mật vào header

Header thường dễ được xem qua chức năng “Show original”, “View source” hoặc qua log của máy chủ. Khi thư được chuyển tiếp, nhiều header có thể tiếp tục đi cùng message. Một số provider có thể lưu metadata và xuất nó vào dashboard.

Vì vậy **không đưa vào header**:

- Mật khẩu SMTP, API key, access token, refresh token hoặc cookie.
- Thông tin xác thực phiên làm việc.
- Dữ liệu cá nhân không cần thiết như số giấy tờ, thông tin thanh toán, chẩn đoán y tế hoặc nội dung bí mật.
- Chuỗi query chứa mã reset mật khẩu hoặc link truy cập riêng tư nếu chỉ để phục vụ tracking.
- Dữ liệu nội bộ dài, dễ khiến hệ thống log hoặc provider lưu nhiều hơn dự kiến.

Nên ưu tiên **opaque ID** như UUID ngẫu nhiên và lưu ánh xạ sang thông tin chi tiết trong database có kiểm soát quyền truy cập. Tuy nhiên, ngay cả opaque ID cũng có thể bị xem bởi người nhận, nên chỉ sử dụng khi thực sự hữu ích.

### Header có thể bị thay đổi hoặc loại bỏ

Một số hệ thống nhận và gửi có thể gỡ bỏ custom headers, chuẩn hóa chữ hoa/thường, gộp nội dung hoặc ghi thêm giá trị. Nếu tích hợp một luồng máy chủ dựa vào header, cần:

1. Có định nghĩa rõ người tạo và người đọc.
2. Không phụ thuộc vào thứ tự các header không được quy định.
3. Xử lý trường hợp thiếu hoặc bị thêm nhiều giá trị.
4. Không giả định provider sẽ trả lại raw MIME giống hệt lúc ứng dụng khởi tạo.
5. Có khóa correlation trong backend và provider event khi cần theo dõi chắc chắn hơn.

## 12. Các tình huống lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Email hiển thị hai Subject khác nhau | `addHeader("Subject", ...)` nhiều lần | Dùng `MimeMessageHelper.setSubject(...)` |
| Reply đi sai địa chỉ | `Reply-To` bị đặt nhầm, mâu thuẫn với cấu hình | Dùng `setReplyTo(...)` và kiểm tra địa chỉ |
| Tệp đính kèm không mở | Tự ghi đè `Content-Type` hoặc `Content-Transfer-Encoding` | Để Jakarta Mail tạo MIME; dùng `addAttachment(...)` |
| HTML hiện nguyên tag | Header/part bị đặt `text/plain` trong khi body là HTML | Dùng `setText(html, true)` hoặc text/HTML alternative |
| Gửi bị từ chối dù có SMTP AUTH | `From` không nằm trong sender/miền được cấp quyền | Dùng địa chỉ đã xác minh, rà soát policy provider |
| Chữ tiếng Việt sai | Charset khai báo không khớp byte văn bản | Dùng UTF-8 nhất quán, kiểm tra nguồn dữ liệu |
| Custom header không xuất hiện ở mailbox | Provider hoặc relay đã chuẩn hóa/loại bỏ | Kiểm tra raw message và tài liệu provider |
| `Message-ID` khác ID trong ứng dụng | Thư viện hoặc provider sinh/đổi message ID | Lưu ID nghiệp vụ riêng và mapping với provider ID |
| DKIM fail sau bước chỉnh sửa mail | Header/body bị biến đổi sau khi ký | Hoàn thiện message trước bước ký; rà soát relay |
| Header làm lộ dữ liệu nội bộ | Đưa payload/secret vào metadata | Dùng ID không nhạy cảm, giới hạn thông tin |
| Thư bị phát sinh Bcc ngoài ý muốn | Dữ liệu ngoài được nối vào raw header bằng CR/LF | Dùng API chuyên dụng, whitelist tên và validate giá trị |
| Thư đến nhưng không hiển thị đúng nhiều phần | Boundary hoặc MIME part header bị chỉnh thủ công | Để `MimeMessageHelper` dựng cấu trúc multipart |

### Tình huống 1: một service và một library cùng đặt `Subject`

```java
helper.setSubject("Thông báo đơn hàng");
mimeMessage.addHeader("Subject", "Thông báo chung");
```

Đoạn code tạo hai nguồn cùng can thiệp vào một trường. Trong thiết kế tốt, **một tầng quyết định giá trị cuối cùng**; các tầng khác truyền tham số hoặc trả nội dung để tầng đó đặt header. Tránh để thư viện đóng vai trò decorator ngầm thêm `Subject`.

### Tình huống 2: ứng dụng tự đặt `Message-ID` để chống gửi trùng

Code tạo `Message-ID` từ mã đơn hàng rồi gửi cùng một message nhiều lần. Cách này không đảm bảo chống lặp: MTA/provider có thể xử lý mỗi submission như một lần gửi mới, và ID có thể bị thay đổi.

Để chống gửi trùng, cần lưu trạng thái yêu cầu trong backend theo **notification ID/idempotency key** và xây chiến lược retry phù hợp. Header chỉ hỗ trợ theo dõi chứ không thay thế trạng thái nghiệp vụ.

### Tình huống 3: muốn thay `Return-Path` để nhận bounce

Ứng dụng gọi `setHeader("Return-Path", ...)` nhưng bounce vẫn không tới địa chỉ mong muốn.

Lý do là đường gửi dùng **SMTP envelope sender** hoặc cấu hình bounce/return-path của provider. Cần sửa cấu hình nơi sở hữu envelope thay vì thêm một header nhìn giống tên trường.

### Tình huống 4: dùng custom header để thông báo loại email

Ứng dụng đặt:

```text
X-App-Notification-Type: account-verification
X-App-Event-ID: 550e8400-e29b-41d4-a716-446655440000
```

Cách này hợp lý nếu tên header được kiểm soát và giá trị không chứa thông tin nhạy cảm. Nó không làm thay đổi ý nghĩa chuẩn của `From`, `To`, `Subject` hay MIME. Nếu provider có hệ thống tagging riêng phục vụ analytics, cần đối chiếu xem nên sử dụng API metadata thay vì phụ thuộc hoàn toàn vào custom headers.

### Tình huống 5: bộ ký DKIM và một relay cùng sửa footer

Provider ký DKIM rồi một relay nội bộ tự chèn footer quảng bá vào body sau khi ký. Khi máy chủ nhận xác thực, chữ ký body có thể thất bại do nội dung đã khác.

Giải pháp về mặt kiến trúc là hoàn thiện nội dung và footer **trước khi ký**, hoặc tổ chức ký lại ở chặng phù hợp và được ủy quyền. Không nên “khắc phục” bằng cách tự chèn một dòng `DKIM-Signature` giả.

## 13. Quy ước thiết kế headers cho dự án Spring

Khi nhiều service cùng gửi email, có thể thống nhất một hợp đồng đơn giản:

| Nhóm header | Bên chịu trách nhiệm | Quy ước |
| --- | --- | --- |
| `From`, `To`, `Cc`, `Bcc`, `Reply-To`, `Subject` | Service gửi mail hoặc lớp builder duy nhất | Thiết lập bằng `MimeMessageHelper` |
| `Content-Type`, `Content-Transfer-Encoding`, `boundary` và attachment headers | Jakarta Mail/MIME helper | Chọn bằng API nội dung; không tự ghi đè |
| `Date`, `Message-ID`, `MIME-Version` | Thư viện/hạ tầng gửi theo cấu hình | Không dùng làm mã nghiệp vụ |
| `Received`, `Return-Path`, `Authentication-Results`, `DKIM-Signature` | Hạ tầng vận chuyển, nhận và xác thực | Không tự giả lập trong application |
| `X-App-Event-ID` | Service nghiệp vụ cấp notification ID | UUID; tối đa một giá trị rõ ràng |
| `X-App-Notification-Type` | Service nghiệp vụ chọn loại thông báo | Enum/giá trị cố định |
| Những header chuẩn đặc thù khác | Đầu mối hiểu nghiệp vụ và yêu cầu provider | Chỉ đặt khi có cơ chế tương ứng hoạt động |

Một mô hình code dễ bảo trì:

```text
Business event
     |
     v
Mail request:
   recipients, sender, replyTo,
   subject, body, notificationId, type
     |
     v
Mail composer (một nơi tạo MimeMessage)
   |
   +-- MimeMessageHelper: headers chuẩn + MIME body
   |
   +-- MimeMessage.setHeader: metadata đã kiểm soát
     |
     v
JavaMailSender
     |
     v
SMTP server / provider / các MTA
```

Cách này giúp tránh việc một interceptor, một template renderer và một service nghiệp vụ cùng sửa `From`, `Subject` hoặc `Content-Type` theo thứ tự khó đoán.

Nếu có yêu cầu mở rộng, hãy xác định rõ **header đó có do ứng dụng sở hữu không**, **giá trị có cần được đặt trên top-level message hay MIME part**, và **một thành phần khác có thể ghi đè nó không**. Cũng cần biết giá trị cuối có phải thứ mà người nhận hoặc provider webhook thực sự nhìn thấy.

## 14. Ghi nhớ qua ba câu hỏi

**Ứng dụng có thể tự thêm header không?** Có. Ví dụ một `X-App-Event-ID` dạng UUID có thể được thêm qua `MimeMessage.setHeader(...)`. Tuy nhiên, custom header là dữ liệu nhìn thấy được trong email và có thể bị hệ thống trung gian thay đổi; không coi nó là thông tin xác thực đáng tin cậy.

**Vì sao không tự đặt `Content-Type`, `Message-ID` hoặc `Return-Path` theo ý muốn?** Vì chúng có vai trò giao thức cụ thể, thường đã được thư viện hoặc hạ tầng email quản lý. Việc đặt lại có thể xung đột với cấu trúc MIME, cách sinh định danh hoặc SMTP envelope.

**Cần làm gì để tránh xung đột?** Dùng `MimeMessageHelper` cho các trường chuẩn và nội dung, chỉ dùng `setHeader` cho metadata do ứng dụng thực sự sở hữu, kiểm soát tên và giá trị header, hiểu sự khác nhau giữa email header với envelope, và tránh sửa thông điệp sau khi hạ tầng ký hoặc chuẩn hóa nó.

Trong Spring Framework Mail, thiết kế an toàn nhất là **chỉ chủ động sở hữu những header ứng dụng thực sự cần**, còn việc mã hóa, đóng gói MIME, tạo thông tin vận chuyển và xác thực thư nên được giao cho thành phần có trách nhiệm tương ứng.
