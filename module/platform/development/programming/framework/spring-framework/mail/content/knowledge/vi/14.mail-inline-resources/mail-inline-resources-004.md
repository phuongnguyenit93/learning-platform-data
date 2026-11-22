# Đặt tên resource và kiểu nội dung

## 1. Resource inline là gì?

Trong **Spring Framework Mail**, email HTML có thể hiển thị một hình ảnh nằm ngay trong nội dung thư, chẳng hạn logo công ty, biểu tượng trạng thái hoặc hình minh họa của hóa đơn. Người nhận nhìn thấy hình ảnh cùng nội dung mà không cần tải ảnh từ một URL bên ngoài. Cách này thường được gọi là **inline resource** hoặc **inline image**.

Một email có ảnh inline thường sử dụng **Content-ID (CID)**. HTML tham chiếu tới ảnh bằng URL dạng `cid:...`, còn ảnh được đóng gói thành một MIME part riêng trong cùng email. Ví dụ:

~~~html
<p>Báo cáo đã sẵn sàng.</p>
<img src="cid:brand-logo" alt="Logo công ty">
~~~

Trong MIME message, part ảnh có header `Content-ID` tương ứng:

~~~text
Content-Type: image/png
Content-Disposition: inline
Content-ID: <brand-logo>
~~~

Khi email client xử lý `src="cid:brand-logo"`, nó tìm MIME part có `Content-ID: <brand-logo>` để hiển thị bytes ảnh tại vị trí đó.

Spring cung cấp `MimeMessageHelper.addInline(...)` để thêm resource inline. Ba thông tin cần phân biệt:

| Thông tin | Vai trò | Ví dụ |
| --- | --- | --- |
| **Content-ID** | Định danh MIME part để HTML tham chiếu | `brand-logo` |
| **Resource name** | Tên mô tả nguồn dữ liệu, thường giống tên file | `brand-logo.png` |
| **Content-Type** | Kiểu media của bytes trong part MIME | `image/png` |

Ba giá trị này không thay thế cho nhau. Đặt đúng tên resource và content type giúp email client hiểu **part nào được HTML tham chiếu** và **bytes bên trong phải được diễn giải như loại nội dung nào**.

## 2. Phân biệt Content-ID, tên resource và Content-Type

### 2.1. Content-ID: tên dùng trong cid URL

**Content-ID** là định danh của một MIME body part. Với `MimeMessageHelper`, truyền ID vào đối số đầu tiên của `addInline`:

~~~java
helper.addInline(
        "brand-logo",
        logoResource,
        "image/png");
~~~

HTML phải dùng cùng ID:

~~~html
<img src="cid:brand-logo" alt="Logo công ty">
~~~

Spring/Jakarta Mail sẽ tạo header MIME dạng:

~~~text
Content-ID: <brand-logo>
~~~

Trong chuỗi truyền cho `addInline` và giá trị sau `cid:`, thông thường **không viết dấu ngoặc góc**. Dấu `<` và `>` thuộc cách biểu diễn header `Content-ID` trong MIME:

| Nơi xuất hiện | Giá trị |
| --- | --- |
| Đối số `contentId` của `addInline` | `brand-logo` |
| HTML `src` | `cid:brand-logo` |
| MIME header sau khi serialize | `Content-ID: <brand-logo>` |

Nếu tự thêm dấu ngoặc góc vào ID truyền cho helper, header có thể bị tạo thành dạng không mong muốn hoặc không khớp với CID URL. Hãy truyền một định danh sạch và dùng nhất quán ở HTML.

### 2.2. Tên resource: tên mô tả nguồn dữ liệu

Tên resource có thể là tên file hoặc tên mô tả dữ liệu, ví dụ:

- `brand-logo.png`
- `invoice-stamp.jpg`
- `status-icon.gif`

Ở overload có đối số `name`, Spring dùng tên này khi tạo DataSource cho resource. Tên đó **không phải Content-ID**: HTML không tham chiếu bằng `cid:brand-logo.png` trừ khi chính Content-ID được đặt là chuỗi đó.

Ví dụ:

~~~java
helper.addInline(
        "brand-logo",
        logoResource,
        "image/png",
        "brand-logo.png");
~~~

Trong lời gọi này:

- `brand-logo` là Content-ID.
- `logoResource` cung cấp bytes.
- `image/png` là MIME content type.
- `brand-logo.png` là tên của nguồn dữ liệu.

Tên resource có thể được provider hoặc mail client sử dụng làm metadata tên part/filename khi biểu diễn nội dung. Cách hiển thị cụ thể phụ thuộc implementation và client; không nên dựa vào tên này để tạo một tệp tải xuống độc lập. Nếu người nhận cần một file đính kèm có tên hiển thị rõ ràng, hãy dùng `addAttachment(...)`.

### 2.3. Content-Type: kiểu MIME của dữ liệu

**Content-Type** mô tả loại dữ liệu được đóng gói trong MIME part. Với ảnh:

| Loại ảnh | MIME Content-Type |
| --- | --- |
| PNG | `image/png` |
| JPEG/JPG | `image/jpeg` |
| GIF | `image/gif` |
| WebP | `image/webp` |
| SVG | `image/svg+xml` |

Tên phần mở rộng và content type phải khớp với bytes thực tế. Ví dụ đổi tên một tệp JPEG thành `logo.png` không biến nội dung JPEG thành PNG.

Trong email, PNG, JPEG và GIF thường là lựa chọn phổ biến hơn. Hỗ trợ SVG và WebP có thể khác nhau theo client và chính sách bảo mật; nếu cần tương thích rộng, hãy kiểm tra nhóm client mục tiêu và cân nhắc chuyển ảnh sang PNG/JPEG.

Không dùng `application/octet-stream` cho ảnh nếu đã biết loại ảnh. Một số client không nhận ra part đó là hình ảnh để hiển thị inline. Content type sai cũng có thể khiến ảnh không được render hoặc bị coi như tệp đính kèm.

## 3. API addInline của MimeMessageHelper

`MimeMessageHelper` cung cấp các overload để nhận dữ liệu từ `DataSource` hoặc `InputStreamSource`. Những dạng thường dùng:

~~~java
helper.addInline(contentId, dataSource);
helper.addInline(contentId, dataSource, contentType);

helper.addInline(contentId, inputStreamSource, contentType);
helper.addInline(contentId, inputStreamSource, contentType, name);
~~~

| Đối số | Ý nghĩa |
| --- | --- |
| `contentId` | ID của MIME part, được HTML tham chiếu bằng `cid:...` |
| `dataSource` | Nguồn cung cấp bytes và metadata cho Jakarta Mail |
| `inputStreamSource` | Nguồn mở InputStream để đọc bytes của resource |
| `contentType` | MIME type như `image/png` |
| `name` | Tên mô tả DataSource, thường dùng tên file như `brand-logo.png` |

### 3.1. Dùng Resource của Spring

`org.springframework.core.io.Resource` triển khai `InputStreamSource`, nên có thể truyền trực tiếp vào overload `addInline`:

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

Resource logo = new ClassPathResource("mail/brand-logo.png");

helper.addInline("brand-logo", logo, "image/png", "brand-logo.png");
~~~

`ClassPathResource` đọc tài nguyên được đóng gói trong classpath, ví dụ:

~~~text
src/main/resources/
└── mail/
    └── brand-logo.png
~~~

Đường dẫn truyền cho `ClassPathResource` tương đối với classpath. Khi ứng dụng được đóng gói thành JAR, tài nguyên vẫn có thể được đọc từ classpath mà không cần giả định nó tồn tại dưới dạng file độc lập trên ổ đĩa.

### 3.2. Dùng FileSystemResource

Nếu ảnh nằm ở một thư mục file-system được ứng dụng quản lý:

~~~java
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;

Resource logo = new FileSystemResource(
        "/opt/mail-assets/brand-logo.png");

helper.addInline("brand-logo", logo, "image/png", "brand-logo.png");
~~~

Đường dẫn trong ví dụ là minh họa. Trong production, thư mục phải được cấu hình và cấp quyền rõ ràng. Không lấy đường dẫn tuyệt đối trực tiếp từ request người dùng rồi truyền vào `FileSystemResource`, vì điều đó có thể cho phép đọc file ngoài vùng dữ liệu dự kiến.

### 3.3. Dùng ByteArrayResource cho dữ liệu trong bộ nhớ

Nếu bytes ảnh đã có trong bộ nhớ, có thể dùng `ByteArrayResource`:

~~~java
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;

byte[] logoBytes = loadLogoBytesFromTrustedStorage();
Resource logo = new ByteArrayResource(logoBytes);

helper.addInline("brand-logo", logo, "image/png", "brand-logo.png");
~~~

`ByteArrayResource` mở một stream mới từ mảng byte của nó. Đây là lựa chọn phù hợp khi dữ liệu đã được đọc vào bộ nhớ và kích thước đã được kiểm soát. Không nên nạp ảnh có kích thước không giới hạn vào heap chỉ để gửi email.

## 4. Quy tắc đặt Content-ID

Content-ID cần ổn định trong phạm vi một message và phải khớp chính xác với CID URL trong HTML.

### 4.1. Dùng ID có ý nghĩa và duy nhất

Ví dụ:

~~~java
helper.addInline("company-logo", logo, "image/png", "company-logo.png");
helper.addInline("invoice-stamp", stamp, "image/png", "invoice-stamp.png");
helper.addInline("status-icon", statusIcon, "image/gif", "status-icon.gif");
~~~

HTML:

~~~html
<img src="cid:company-logo" alt="Logo">
<img src="cid:invoice-stamp" alt="Dấu hóa đơn">
<img src="cid:status-icon" alt="Trạng thái">
~~~

Mỗi ID nên mô tả mục đích của ảnh và không bị trùng trong cùng email. Nếu có nhiều ảnh cùng dùng một Content-ID, client có thể chọn nhầm part hoặc không hiển thị đúng.

### 4.2. Tránh ký tự gây khó khăn trong CID URL

Nên chọn ID đơn giản, không có khoảng trắng, dấu ngoặc góc hoặc chuỗi ký tự cần percent-encode. Ví dụ:

~~~text
company-logo
invoice-stamp
status-icon-2026
~~~

Không truyền nguyên đường dẫn file vào Content-ID:

~~~java
// Không nên: path không phải định danh CID.
helper.addInline("/opt/mail-assets/brand-logo.png", logo, "image/png");
~~~

Content-ID là định danh MIME, không phải tên file hoặc URL trên máy chủ. Nếu ID có các ký tự đặc biệt theo cú pháp Message-ID, CID URL phải được biểu diễn theo quy tắc URI tương ứng; trong ứng dụng thông thường, dùng ID ASCII ngắn và đơn giản giúp tránh lỗi.

### 4.3. Tạo ID duy nhất khi cần

Nếu một email được tạo từ nhiều thành phần độc lập và cần tránh xung đột, có thể tạo ID có hậu tố duy nhất:

~~~java
String contentId = "logo-" + java.util.UUID.randomUUID();
helper.addInline(contentId, logo, "image/png", "brand-logo.png");

String html = "<img src=\"cid:" + contentId + "\" alt=\"Logo\">";
helper.setText(plainText, html);
~~~

Ví dụ minh họa việc dùng cùng một biến cho cả helper và HTML. Với một template tĩnh chỉ có một logo, ID cố định như `company-logo` thường đơn giản hơn. UUID không làm ảnh an toàn hơn; nó chỉ giảm nguy cơ va chạm ID khi có nhiều resource được tạo động.

## 5. Đặt Content-Type chính xác

Content-Type nên mô tả **định dạng bytes thực tế**, không chỉ phần mở rộng của tên file.

### 5.1. Khai báo rõ content type

~~~java
helper.addInline("brand-logo", logoPng, "image/png", "brand-logo.png");
helper.addInline("avatar", avatarJpeg, "image/jpeg", "avatar.jpg");
helper.addInline("animated-status", statusGif, "image/gif", "status.gif");
~~~

Khi dùng overload ba đối số, tên resource không được truyền tường minh:

~~~java
helper.addInline("brand-logo", logoPng, "image/png");
~~~

Trong trường hợp này, nguồn dữ liệu vẫn phải đọc được; helper có content type để tạo part MIME, còn tên nguồn được lấy từ DataSource được tạo cho resource theo overload/implementation.

### 5.2. Không đoán content type chỉ từ tên file

Một file có tên `image.png` chưa chắc chứa PNG hợp lệ. Nếu tệp đến từ upload hoặc nguồn bên ngoài:

1. Kiểm tra kích thước tối đa trước khi đọc toàn bộ bytes.
2. Kiểm tra chữ ký định dạng (magic bytes) hoặc dùng thư viện xử lý ảnh để nhận diện loại thật.
3. Chỉ cho phép tập định dạng cần thiết như PNG/JPEG/GIF.
4. Giải mã thử ảnh nếu nghiệp vụ cần bảo đảm dữ liệu có cấu trúc hợp lệ.
5. Chọn Content-Type từ kết quả xác định, không tin trực tiếp header MIME do client gửi.

Mục tiêu là tránh trường hợp bytes không phải ảnh nhưng được gắn nhãn `image/png`, hoặc nội dung độc hại/không hợp lệ được đưa vào email.

### 5.3. SVG và định dạng ít tương thích

SVG là XML-based vector image với khả năng biểu diễn phong phú. Một số mail client có thể chặn hoặc không render SVG inline vì chính sách bảo mật và khả năng tương thích. Nếu cần hiển thị logo trên nhiều client, PNG hoặc JPEG thường là lựa chọn dễ dự đoán hơn.

WebP cũng có thể không được hỗ trợ đồng đều trong các client/phiên bản. Nếu dùng SVG/WebP, phải kiểm tra email thực trên tập ứng dụng đích và có fallback phù hợp. Không coi `image/svg+xml` hoặc `image/webp` là bảo đảm client sẽ hiển thị.

## 6. Ví dụ hoàn chỉnh: thêm logo inline vào HTML email

Ví dụ dưới đây dùng `ClassPathResource` và `MimeMessageHelper`:

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ReportMailer {

    private final JavaMailSender mailSender;

    public ReportMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReportReady(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8");

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Báo cáo đã sẵn sàng");

        Resource logo = new ClassPathResource("mail/brand-logo.png");

        String plainText = "Báo cáo đã sẵn sàng.";
        String html = """
                <html lang="vi">
                  <body>
                    <p>Báo cáo đã sẵn sàng.</p>
                    <img src="cid:brand-logo"
                         alt="Logo công ty"
                         width="160"
                         style="display:block;width:160px;height:auto;">
                  </body>
                </html>
                """;

        // Đặt body trước khi thêm inline resource.
        helper.setText(plainText, html);

        helper.addInline(
                "brand-logo",
                logo,
                "image/png",
                "brand-logo.png");

        mailSender.send(message);
    }
}
~~~

Tệp ảnh nằm trong:

~~~text
src/main/resources/mail/brand-logo.png
~~~

Các giá trị trong ví dụ có vai trò:

| Giá trị | Vai trò |
| --- | --- |
| `"brand-logo"` ở `addInline` | Content-ID của part ảnh |
| `cid:brand-logo` trong HTML | Tham chiếu tới part có Content-ID đó |
| `logo` | Resource cung cấp bytes PNG |
| `"image/png"` | MIME Content-Type |
| `"brand-logo.png"` | Tên mô tả nguồn dữ liệu |
| `MULTIPART_MODE_MIXED_RELATED` | Cấu trúc phù hợp cho body có inline resource và có thể kèm attachment |

**Thứ tự gọi quan trọng:** đặt body bằng `setText(...)` trước khi gọi `addInline(...)`. Điều này giúp helper xây dựng cấu trúc MIME liên quan đúng cách và tránh lỗi do tạo part inline trước khi phần HTML tham chiếu nó tồn tại.

Ví dụ này chỉ gửi logo inline. Nếu cần đính kèm PDF độc lập, có thể tiếp tục gọi `helper.addAttachment("report.pdf", reportResource)` trên cùng helper multipart.

## 7. Cây MIME của email có inline resource

Một email HTML có bản text dự phòng và một logo inline thường có cấu trúc khái quát:

~~~text
MimeMessage
└── multipart/related
    ├── multipart/alternative
    │   ├── text/plain; charset=UTF-8
    │   └── text/html; charset=UTF-8
    │       <img src="cid:brand-logo">
    └── image/png
        Content-ID: <brand-logo>
        Content-Disposition: inline
~~~

Nếu thư có cả inline resource và attachment độc lập, cây thường có một `multipart/mixed` bên ngoài:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain
    │   │   └── text/html
    │   │       <img src="cid:brand-logo">
    │   └── image/png
    │       Content-ID: <brand-logo>
    │       Content-Disposition: inline
    └── application/pdf
        Content-Disposition: attachment
        filename="report.pdf"
~~~

Đây là cấu trúc điển hình để giải thích mối quan hệ giữa các phần; cây chính xác phụ thuộc multipart mode và cách message được dựng. `multipart/related` nhóm body với resource được body tham chiếu; `multipart/alternative` chứa các phiên bản nội dung thay thế; `multipart/mixed` nhóm các phần độc lập như attachment.

## 8. Phân biệt addInline và addAttachment

Hai phương thức đều thêm MIME part, nhưng mục đích khác nhau:

| API | Ý nghĩa | Cách người nhận thường thấy |
| --- | --- | --- |
| `addInline(contentId, ...)` | Resource được tham chiếu từ body bằng `cid:...` | Ảnh xuất hiện ngay trong nội dung HTML nếu client hỗ trợ |
| `addAttachment(name, ...)` | Tệp độc lập đính kèm message | Hiển thị trong danh sách attachment để người nhận tải/mở |

Ví dụ:

~~~java
helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png",
        "brand-logo.png");

helper.addAttachment(
        "report.pdf",
        new ClassPathResource("reports/report.pdf"));
~~~

HTML chỉ tham chiếu logo:

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

PDF không cần CID vì nó là attachment độc lập. Đặt `report.pdf` bằng `addInline` mà không có `cid:...` tham chiếu có thể khiến part không được sử dụng như mong đợi. Ngược lại, dùng `addAttachment` cho logo thường khiến ảnh xuất hiện như tệp tải xuống thay vì ở đúng vị trí trong body.

## 9. Nguồn InputStreamSource phải đọc được khi gửi

`MimeMessageHelper.addInline` nhận `InputStreamSource`. Hợp đồng của nguồn này cần được lưu ý: quá trình dựng/serialize MIME có thể yêu cầu mở stream nhiều lần. Vì vậy, **mỗi lần gọi `getInputStream()` nên cung cấp một stream mới có thể đọc từ đầu**.

Các nguồn thường phù hợp:

| Nguồn | Đặc điểm |
| --- | --- |
| `ClassPathResource` | Mở lại resource từ classpath |
| `FileSystemResource` | Mở lại file theo đường dẫn được phép |
| `ByteArrayResource` | Cung cấp stream mới từ bytes trong bộ nhớ |
| Nguồn tùy chỉnh triển khai `InputStreamSource` | Phải bảo đảm stream có thể mở lại theo hợp đồng |
| `InputStreamResource` dựa trên stream đã mở | Thường chỉ đọc được một lần; không phù hợp nếu quá trình MIME cần mở lại |

Không nên tạo một `InputStream`, đọc hết nó rồi bọc thành nguồn chỉ trả lại cùng stream đã tiêu thụ. Nếu dữ liệu đến từ stream một lần, có thể đọc vào buffer có giới hạn để tạo `ByteArrayResource`, hoặc dùng một nguồn lưu trữ có khả năng mở lại.

Ví dụ nguồn tùy chỉnh đơn giản:

~~~java
byte[] bytes = loadAndValidateImage();
InputStreamSource source = () -> new ByteArrayInputStream(bytes);
~~~

Mỗi lần `getInputStream()` được gọi, lambda tạo `ByteArrayInputStream` mới từ đầu mảng bytes. Hãy giới hạn kích thước trước khi giữ bytes trong bộ nhớ.

## 10. Những lỗi thường gặp khi đặt tên và content type

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| HTML có `cid:brand-logo` nhưng ảnh không hiện | Content-ID truyền vào helper không khớp | Đọc header `Content-ID` trong raw MIME |
| Ảnh hiển thị thành attachment | Dùng nhầm `addAttachment` hoặc client xử lý inline part theo cách riêng | Xem `Content-Disposition` và MIME tree |
| Part ảnh có tên nhưng HTML không tìm thấy | Nhầm resource name với Content-ID | So sánh `cid:...` với `Content-ID`, không so với filename |
| Ảnh không giải mã được | Content-Type không khớp bytes | Xác định định dạng ảnh thực, kiểm tra MIME header |
| Ảnh bị tải như file không rõ loại | Dùng `application/octet-stream` hoặc thiếu media type phù hợp | Đặt `image/png`, `image/jpeg`... theo bytes |
| Chỉ một trong nhiều ảnh hiện | CID trùng hoặc có một CID sai | Mỗi part có ID duy nhất; kiểm tra từng reference |
| Ảnh không có dữ liệu | Resource rỗng, sai path hoặc không có quyền đọc | Kiểm tra nguồn dữ liệu và kích thước |
| Lỗi stream khi send | Nguồn chỉ mở được một lần hoặc đã bị đóng | Dùng Resource có thể mở lại hoặc buffer bytes |
| Ảnh SVG không hiển thị ở một số client | Client không hỗ trợ hoặc chặn SVG | Chọn PNG/JPEG fallback và kiểm tra client |
| Ảnh hiển thị trong một client nhưng mất ở client khác | Khác biệt MIME/HTML support hoặc policy ảnh | Kiểm tra raw MIME và thử trên client mục tiêu |

### 10.1. Content-ID không khớp

Ví dụ lỗi:

~~~java
helper.addInline("company-logo", logo, "image/png");
~~~

nhưng HTML lại viết:

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

Hai chuỗi khác nhau nên client không tìm thấy part. Hãy dùng một hằng số hoặc biến duy nhất:

~~~java
String logoId = "company-logo";
helper.addInline(logoId, logo, "image/png");
String html = "<img src=\"cid:" + logoId + "\" alt=\"Logo\">";
~~~

### 10.2. Đặt sai content type

Nếu bytes là JPEG nhưng khai báo `image/png`, client có thể không giải mã đúng. Hãy lấy content type từ quá trình xác định định dạng thực, không chỉ dựa vào tên file hoặc MIME header từ request.

### 10.3. Resource name bị nhầm với filename của attachment

Đối số `name` của overload `addInline` giúp mô tả DataSource; nó không biến inline resource thành một attachment tải xuống độc lập. Nếu yêu cầu là người nhận tải file với tên cụ thể, dùng:

~~~java
helper.addAttachment("invoice.pdf", invoiceResource);
~~~

và để helper quản lý `Content-Disposition: attachment` cho phần đó.

### 10.4. Gọi addInline trước setText

Nên theo thứ tự:

~~~java
helper.setText(plainText, html);
helper.addInline("brand-logo", logo, "image/png", "brand-logo.png");
~~~

Body được đặt trước để helper có thể tổ chức inline part liên quan đến HTML. Nếu thêm inline part quá sớm, một số cấu trúc MIME hoặc client có thể xử lý không như dự kiến.

## 11. Kiểm tra MIME message đã tạo

Trong môi trường thử nghiệm, có thể serialize `MimeMessage` thành tệp `.eml` để kiểm tra tên, CID và Content-Type:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");

String logoId = "brand-logo";
Resource logo = new ClassPathResource("mail/brand-logo.png");
String html = "<p>Báo cáo đã sẵn sàng.</p>"
        + "<img src=\"cid:" + logoId + "\" alt=\"Logo\">";

helper.setFrom("reports@example.com");
helper.setTo("test@example.net");
helper.setSubject("Kiểm tra inline resource");
helper.setText("Báo cáo đã sẵn sàng.", html);
helper.addInline(logoId, logo, "image/png", "brand-logo.png");

message.saveChanges();
try (OutputStream output =
             Files.newOutputStream(Path.of("inline-preview.eml"))) {
    message.writeTo(output);
}
~~~

Ví dụ giả định có các import tương ứng `java.io.OutputStream`, `java.nio.file.Files`, `java.nio.file.Path` và xử lý `IOException`/`MessagingException`. Đoạn này chỉ ghi message ra file; **không gửi email** vì không gọi `mailSender.send(message)`.

Trong raw MIME, kiểm tra:

~~~text
Content-Type: image/png
Content-Disposition: inline
Content-ID: <brand-logo>
~~~

Các header có thể được viết khác về thứ tự hoặc thêm tham số, nhưng ý nghĩa cần khớp:

- `Content-ID` phải khớp CID URL trong HTML.
- `Content-Type` phải mô tả bytes ảnh.
- `Content-Disposition` cho biết part được dự định sử dụng inline.
- Bytes part không được rỗng và phải là ảnh hợp lệ.

Đối với email thật, raw MIME có thể chứa dữ liệu nhạy cảm hoặc nội dung riêng tư. Chỉ xuất và lưu file thử nghiệm trong nơi được phép, dùng người nhận/ảnh mẫu và xóa dữ liệu theo chính sách lưu trữ.

## 12. Kiểm thử qua SMTP sink và mail client

Kiểm tra raw MIME chưa đủ để bảo đảm mọi mail client hiển thị giống nhau. Một quy trình kiểm thử hữu ích:

1. Dùng một ảnh mẫu PNG nhỏ trong classpath.
2. Tạo message với Content-ID cố định, content type chính xác và tên resource rõ ràng.
3. Gửi tới SMTP sink cục bộ như Mailpit/MailHog thay vì hộp thư khách hàng.
4. Xem message được nhận, kiểm tra MIME part và HTML CID reference.
5. Mở email trên Gmail, Outlook và Apple Mail thuộc nhóm client sản phẩm cần hỗ trợ.
6. Kiểm tra khi ảnh ngoài bị chặn, nhưng vẫn xác nhận ảnh CID có được hiển thị theo client hay không.
7. Thử nhiều ảnh trong cùng message để phát hiện CID trùng hoặc reference sai.

SMTP sink xác nhận email đã được ứng dụng gửi tới môi trường thử nghiệm và cho phép kiểm tra MIME. Nó không chứng minh provider production hay mọi client sẽ hiển thị ảnh giống nhau.

## 13. Bảo mật và quản lý resource inline

Ảnh inline vẫn là dữ liệu được nhúng trong email. Cần quản lý nguồn và kích thước:

- Chỉ dùng resource từ classpath, thư mục được kiểm soát hoặc kho lưu trữ mà ứng dụng có quyền truy cập.
- Nếu người dùng tải ảnh lên, kiểm tra định dạng bytes, giới hạn kích thước và xử lý ảnh trước khi gửi.
- Không tin tên file hoặc Content-Type do client cung cấp.
- Không đọc đường dẫn tùy ý từ request.
- Không nhúng ảnh chứa thông tin nhạy cảm vào email nếu người nhận không được phép xem.
- Dùng ID không chứa dữ liệu cá nhân hoặc token.
- Cân nhắc tổng dung lượng MIME sau khi encode; attachment/inline images làm email lớn hơn dữ liệu gốc.
- Tránh dùng ảnh để truyền đạt thông tin duy nhất; luôn có text hoặc alt text có nghĩa.

Content-ID chỉ là **định danh trong MIME**, không phải cơ chế xác thực hay mã truy cập. Không đưa secret, access token hoặc thông tin cá nhân vào CID với suy nghĩ rằng ID đó sẽ được bảo vệ.

## 14. Câu hỏi thường gặp

**“Content-ID có phải tên file ảnh không?”**  
Không. Content-ID là định danh mà HTML tham chiếu bằng `cid:...`. Tên file/resource là metadata riêng.

**“Tại sao helper nhận `brand-logo` nhưng header có dấu ngoặc góc?”**  
Đó là cách biểu diễn header MIME `Content-ID: <brand-logo>`. Trong HTML dùng `cid:brand-logo`, không thêm dấu ngoặc góc.

**“Content-Type có thể suy ra từ đuôi file không?”**  
Đuôi file là gợi ý, không phải bằng chứng. Với dữ liệu upload, cần xác định định dạng thực của bytes và chỉ cho phép các loại được hỗ trợ.

**“Resource name có thể khác Content-ID không?”**  
Có. Ví dụ Content-ID là `company-logo`, resource name là `brand-logo.png`. HTML phải dùng CID, không dùng resource name trừ khi hai giá trị được chủ động đặt giống nhau.

**“Dùng `image/png` cho file JPEG có được không?”**  
Không nên. Content-Type phải mô tả định dạng thực. Khai báo sai có thể khiến client không giải mã hoặc hiển thị đúng.

**“Có thể dùng cùng một CID cho hai ảnh?”**  
Không nên. Mỗi part inline trong một message cần một định danh riêng để HTML tham chiếu không mơ hồ.

**“Dùng `addInline` có tự thêm ảnh vào HTML không?”**  
Không. Helper thêm MIME part; HTML vẫn phải chứa `<img src="cid:...">` tham chiếu tới Content-ID tương ứng.

**“Có thể dùng URL https thay cho CID không?”**  
Có thể nhúng ảnh từ URL ngoài, nhưng client có thể chặn tải hoặc dùng proxy. CID đóng gói ảnh trong message; hai cách có đặc tính và giới hạn khác nhau.

**“Resource chỉ có thể đọc một lần có dùng được không?”**  
Không nên dùng trực tiếp nếu quá trình gửi/serialize cần mở stream nhiều lần. Hãy dùng Resource có thể mở lại hoặc buffer bytes có giới hạn thành `ByteArrayResource`.

**“Ảnh SVG có phù hợp với mọi mail client không?”**  
Không. Một số client có thể chặn hoặc không render SVG. Nếu cần tương thích rộng, cân nhắc PNG/JPEG và thử nghiệm trên client mục tiêu.

## 15. Ghi nhớ khi đặt tên resource và kiểu nội dung

Một inline resource đúng cần ba giá trị nhất quán:

~~~text
HTML:
  <img src="cid:brand-logo">
                 |
                 | cùng Content-ID
                 v
MIME part:
  Content-ID: <brand-logo>
  Content-Type: image/png
  Content-Disposition: inline
  DataSource name: brand-logo.png
  Body: bytes PNG hợp lệ
~~~

Trong Spring Framework Mail, hãy dùng `MimeMessageHelper.addInline(contentId, resource, contentType, name)` khi muốn chỉ định rõ cả ID, nguồn bytes, MIME type và tên resource. Giữ **Content-ID** trùng với CID URL trong HTML, chọn **Content-Type** theo định dạng bytes thật và dùng **resource name** như metadata mô tả. Kết hợp đúng ba thành phần này với multipart structure và nguồn stream có thể đọc lại giúp ảnh inline được đóng gói rõ ràng, dễ kiểm tra và tương thích tốt hơn với các ứng dụng email.
