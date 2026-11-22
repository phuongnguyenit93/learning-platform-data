# Tham chiếu ảnh bằng đường dẫn file cục bộ

## 1. Hiện tượng: email gửi thành công nhưng ảnh không hiển thị

Khi tạo email HTML bằng **Spring Framework Mail**, một lỗi rất phổ biến là đặt trực tiếp **đường dẫn file trên máy chạy ứng dụng** vào thuộc tính `src` của thẻ `<img>`. Ví dụ:

~~~html
<html>
  <body>
    <h1>Chào mừng bạn!</h1>
    <img src="C:\work\mail-assets\logo.png" alt="Company logo">
  </body>
</html>
~~~

Hoặc:

~~~html
<img src="/opt/app/assets/logo.png" alt="Logo">
<img src="file:///opt/app/assets/logo.png" alt="Logo">
<img src="./images/banner.jpg" alt="Banner">
~~~

Khi xem HTML trên máy phát triển, developer đôi khi vẫn nhìn thấy ảnh trong một trình duyệt hoặc công cụ preview có quyền đọc file. Nhưng sau khi email được gửi đến Gmail, Outlook, Apple Mail hoặc một mail client khác, ảnh có thể:

- Hiển thị biểu tượng ảnh bị hỏng hoặc một khoảng trống.
- Chỉ hiển thị thuộc tính `alt`.
- Không xuất hiện trong email dù file vẫn tồn tại trên server.
- Hiện trên một mail client nhưng không hiện trên client khác.
- Gửi thành công qua SMTP, không có exception, nhưng người nhận không xem được ảnh.

Nguyên nhân không nhất thiết là `JavaMailSender` bị lỗi. **Máy của người nhận không có quyền truy cập filesystem của server gửi email**, và email client thường chặn hoặc không hỗ trợ đọc đường dẫn `file:` vì lý do an toàn.

> **Quy tắc nền tảng:** Một email là một tài liệu được gửi tới thiết bị khác. Đường dẫn như `C:\work\logo.png` hoặc `/opt/app/logo.png` chỉ có ý nghĩa trong một môi trường filesystem cụ thể; nó không tự biến thành dữ liệu ảnh được đính kèm trong thông điệp MIME.

Để hiển thị ảnh trong email HTML, thường có ba lựa chọn:

1. **Ảnh inline qua Content-ID (CID):** đưa dữ liệu ảnh vào MIME message và tham chiếu `cid:...` trong HTML.
2. **Ảnh trên HTTPS:** đưa ảnh lên một URL có thể truy cập qua Internet theo chính sách và tham chiếu URL đó; mail client có thể chặn tải ảnh từ xa.
3. **Data URI/Base64:** nhúng ảnh trực tiếp trong HTML dưới dạng `data:image/...;base64,...`, nhưng khả năng tương thích giữa email clients không đồng nhất; thường không phải lựa chọn mặc định.

Bài này tập trung vào việc **nhận diện và sửa lỗi tham chiếu đường dẫn file cục bộ** trong Spring Framework Mail, đặc biệt với `JavaMailSender`, `MimeMessageHelper` và cấu trúc MIME.

## 2. Vì sao đường dẫn file trên server không thể dùng làm URL trong email?

Xem hành trình thực tế:

~~~text
Spring Boot application
  Filesystem:
    /opt/app/assets/logo.png
               |
               v
  HTML generated:
    <img src="/opt/app/assets/logo.png">
               |
               v
       JavaMailSender.send(...)
               |
               v
         SMTP server
               |
               v
     Recipient mail server
               |
               v
     Gmail / Outlook / Mail app
               |
               v
    Tries to interpret image src
               |
               v
       NOT a portable URL
       NOT an embedded MIME part
       -> broken or blocked image
~~~

Khi gửi HTML qua SMTP, nội dung HTML chỉ là **một MIME body part**. Dòng:

~~~html
<img src="/opt/app/assets/logo.png">
~~~

không ra lệnh cho SMTP server tự tìm file `/opt/app/assets/logo.png` rồi nhúng nó vào email. SMTP transport truyền dữ liệu message đã được tạo. Nếu muốn file trở thành một MIME part, code phải chủ động tạo part đó qua `MimeMessageHelper.addInline(...)` hoặc một API tương đương.

### 2.1. Đường dẫn tuyệt đối không có ý nghĩa toàn cầu

| Giá trị `src` | Nó thực sự chỉ tới đâu? | Vấn đề |
| --- | --- | --- |
| `C:\app\images\logo.png` | File trên Windows nơi đường dẫn tồn tại | Người nhận không có ổ `C:` giống server |
| `/var/app/logo.png` | File trên Unix/Linux hoặc đường dẫn tương đối tới origin trong một số ngữ cảnh web | Email không biết origin HTTP của server |
| `file:///opt/app/logo.png` | File URI của máy diễn giải URI | Mail client chặn hoặc không có file |
| `./logo.png` | Đường dẫn tương đối vào ngữ cảnh tài liệu | Email thường không có base URL phù hợp |
| `classpath:mail/logo.png` | Cú pháp Spring Resource dùng trong backend | Không phải URL ảnh mà mail client hiểu |
| `https://cdn.example.com/logo.png` | Một URL web công khai/được truy cập hợp lệ | Có thể tải từ xa, nhưng client có thể chặn |
| `cid:brandLogo` | Content-ID của một MIME part trong chính email | Hoạt động khi đúng MIME part và client hỗ trợ |

Sự khác biệt quan trọng: **đường dẫn backend để đọc file** và **URL để mail client hiển thị ảnh** không phải một loại dữ liệu.

### 2.2. Gửi file như attachment cũng chưa đủ

Ví dụ:

~~~java
helper.addAttachment(
        "logo.png",
        new FileSystemResource("/opt/app/assets/logo.png"));
~~~

Lệnh này tạo **file đính kèm**. Nó không tự thay đổi HTML:

~~~html
<img src="file:///opt/app/assets/logo.png">
~~~

thành một ảnh inline. Một số mail client có thể hiển thị attachment dưới dạng thumbnail, nhưng đó không phải vị trí của thẻ `<img>` trong email.

Muốn HTML hiển thị đúng vị trí, hãy dùng **CID reference** kết hợp **inline MIME part**, không chỉ thêm attachment thông thường.

### 2.3. “Trình duyệt xem được” không chứng minh email xem được

Trang HTML được mở từ file hoặc web server có thể có quyền truy cập tương ứng:

~~~text
Browser preview on developer machine:
  file:///C:/work/logo.png
  -> Browser may display

Email opened on recipient phone:
  file:///C:/work/logo.png
  -> File does not exist or is blocked
~~~

Một template preview trong IDE hoặc email preview service cũng có thể tự map asset path sang filesystem. Khi kiểm tra email thật, cần xem **MIME được gửi** và **render trên các mail client mục tiêu**, không chỉ xem preview HTML trước khi gửi.

## 3. Phân biệt URL ảnh, CID và tệp nguồn

Một file ảnh có thể có ba “địa chỉ” khác nhau trong hệ thống:

~~~text
SOURCE PATH / RESOURCE
  /opt/app/assets/logo.png
  (where Spring reads bytes)
             |
             v
MIME INLINE CONTENT-ID
  Content-ID: <brandLogo>
  Content-Type: image/png
  (part stored inside the message)
             |
             v
HTML REFERENCE
  <img src="cid:brandLogo">
  (what the recipient client resolves)
~~~

Với HTTPS:

~~~text
SOURCE IMAGE -> uploaded to a web-accessible object/CDN
                      |
                      v
URL: https://cdn.example.com/mail/logo.png
                      |
                      v
HTML: <img src="https://cdn.example.com/mail/logo.png">
                      |
                      v
Recipient's client requests URL
  (possibly proxied, cached, blocked or delayed)
~~~

**Đổi `file:///...` thành `cid:...` trong HTML là chưa đủ** nếu ứng dụng không đưa dữ liệu ảnh vào email dưới một MIME part có Content-ID tương ứng.

## 4. Giải pháp khuyến nghị cho logo/banner cố định: inline CID

Với ảnh nhỏ có vai trò thiết yếu trong email (ví dụ logo nội bộ của template), thường dùng:

1. Tạo `MimeMessage` từ `JavaMailSender`.
2. Tạo `MimeMessageHelper` ở chế độ multipart phù hợp.
3. Gọi `setText(plainText, htmlText)` với HTML chứa `cid:logo`.
4. Gọi `addInline("logo", resource, "image/png")` để đưa bytes ảnh vào MIME.
5. Gửi message bằng cùng `JavaMailSender`.

### 4.1. Ví dụ đầy đủ với file trên disk

~~~java
package com.example.mail;

import java.nio.file.Files;
import java.nio.file.Path;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(
            String recipient,
            Path logoPath) throws MessagingException {

        if (!Files.isRegularFile(logoPath)
                || !Files.isReadable(logoPath)) {
            throw new IllegalArgumentException(
                    "Configured mail logo is unavailable");
        }

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8");

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Chào mừng bạn");

        String plainText = """
                Chào mừng bạn!
                Cảm ơn bạn đã đăng ký.
                """;

        String htmlText = """
                <html>
                  <body>
                    <img src="cid:brandLogo"
                         alt="Company"
                         width="140">
                    <h1>Chào mừng bạn!</h1>
                    <p>Cảm ơn bạn đã đăng ký.</p>
                  </body>
                </html>
                """;

        // Set HTML trước rồi mới addInline.
        helper.setText(plainText, htmlText);

        FileSystemResource logoResource =
                new FileSystemResource(logoPath);
        helper.addInline(
                "brandLogo",
                logoResource,
                "image/png");

        mailSender.send(message);
    }
}
~~~

**Điểm cốt lõi:**

- `logoPath` chỉ dùng **trên server** để Spring đọc bytes.
- `cid:brandLogo` là thứ được đặt vào **HTML gửi cho người nhận**.
- `helper.addInline("brandLogo", ...)` tạo MIME part với Content-ID tương ứng.
- `MULTIPART_MODE_MIXED_RELATED` được dùng để tạo cấu trúc phù hợp với HTML, ảnh inline và khả năng bổ sung attachment độc lập.
- `setText(plainText, htmlText)` tạo cả bản text/plain và text/html cho các client không hiển thị HTML.
- `image/png` là loại MIME đúng cho file PNG; không đặt tùy tiện một content type khác với dữ liệu thật.

Lưu ý import `java.nio.file.Path` và dùng Java phù hợp phiên bản project. Ví dụ text block cần Java 15+, thích hợp với Java 17 thường dùng trong Spring Boot 3. Nếu code dùng Java cũ, thay text blocks bằng string thông thường.

### 4.2. Tại sao Content-ID phải khớp chính xác?

HTML:

~~~html
<img src="cid:brandLogo" alt="Company">
~~~

MIME:

~~~text
Content-ID: <brandLogo>
Content-Type: image/png
Content-Disposition: inline
Content-Transfer-Encoding: base64
~~~

`MimeMessageHelper.addInline("brandLogo", ...)` quản lý cách ghi Content-ID; code HTML tham chiếu giá trị `brandLogo` mà **không** chèn cặp ngoặc nhọn `<...>` vào `cid:`.

Nếu viết:

~~~html
<img src="cid:logo">
~~~

nhưng gọi:

~~~java
helper.addInline("brandLogo", logoResource, "image/png");
~~~

thì client không tìm thấy MIME part có ID `logo`. Kết quả có thể là ảnh hỏng dù file PNG đã được đính kèm trong email.

### 4.3. Vì sao addInline nên thực hiện sau setText?

Spring `MimeMessageHelper` khuyến nghị thêm inline resources **sau khi đặt text** để tránh một số mail client có thể không phân giải đúng cấu trúc MIME nếu các part được tạo theo thứ tự không tương thích.

Thứ tự đơn giản:

~~~java
helper.setText(plainText, htmlText);
helper.addInline("brandLogo", resource, "image/png");
mailSender.send(message);
~~~

Không phải mọi MIME parser đều nhạy thứ tự giống nhau, nhưng giữ cấu trúc và thứ tự rõ ràng làm giảm sự cố giữa Gmail, Outlook, Apple Mail hoặc những client cũ.

### 4.4. File tồn tại tại lúc kiểm tra nhưng mất trước khi send

Đoạn:

~~~java
Files.isReadable(logoPath)
~~~

chỉ kiểm tra ở **một thời điểm**. Nếu job chạy bất đồng bộ và file bị xóa giữa kiểm tra và `send`, thư có thể lỗi khi serialization MIME đọc resource:

~~~text
T1: request uploads logo -> /tmp/logo-123.png
T2: queue background mail job
T3: request ends -> temp file deleted
T4: mail worker invokes addInline + send
T5: resource cannot be read
~~~

Với job async/retry, hãy sử dụng tài nguyên bền vững đủ lâu (classpath, asset cố định, object storage versioned, durable staged file) và chỉ cleanup khi hoàn tất/được phép theo lifecycle.

## 5. Ảnh nằm trong resources của Spring Boot: dùng ClassPathResource

Nhiều dự án đặt logo trong cấu trúc:

~~~text
src/
  main/
    java/
      com/example/mail/...
    resources/
      mail/
        images/
          brand-logo.png
          welcome-banner.jpg
~~~

Trong trường hợp này, ảnh thường được **đóng gói vào JAR** khi build. Không nên cố tìm nó như một file vật lý:

~~~java
// Dễ lỗi sau khi đóng gói executable JAR:
Path path = Paths.get(
        "src/main/resources/mail/images/brand-logo.png");
~~~

Đường dẫn `src/main/resources` chỉ đúng với layout source code lúc phát triển. Sau khi build và chạy từ JAR/container, thư mục đó có thể không còn tồn tại.

### 5.1. Đọc resource đúng qua classpath

~~~java
import org.springframework.core.io.ClassPathResource;

ClassPathResource logo =
        new ClassPathResource("mail/images/brand-logo.png");

helper.setText(
        "Chào mừng bạn!",
        """
        <html>
          <body>
            <h1>Chào mừng bạn!</h1>
            <img src="cid:companyLogo" alt="Company logo">
          </body>
        </html>
        """);

helper.addInline("companyLogo", logo, "image/png");
~~~

`ClassPathResource` cung cấp `InputStream` vào dữ liệu trong classpath, kể cả khi nằm trong JAR. Không cần biết file thực đang nằm trong thư mục build, trong JAR hay location cụ thể trên hệ điều hành.

**Không đưa chuỗi `classpath:mail/images/brand-logo.png` vào HTML.** Đây là cách backend tìm resource, không phải địa chỉ mà mail client có thể đọc.

### 5.2. Tránh ép classpath resource thành File

Một lỗi:

~~~java
File logoFile = new ClassPathResource(
        "mail/images/brand-logo.png").getFile();
~~~

Khi resource nằm trong JAR, `getFile()` có thể thất bại vì resource **không tồn tại như một file riêng trên filesystem**. Đối với `MimeMessageHelper.addInline`, có thể truyền trực tiếp `ClassPathResource`:

~~~java
helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/images/brand-logo.png"),
        "image/png");
~~~

Spring sẽ mở stream khi cần. Điều kiện là resource còn tồn tại và có thể đọc lại trong vòng đời tạo/gửi message.

### 5.3. Đóng gói asset trong JAR có phù hợp không?

**Phù hợp** khi:

- Logo/ảnh nhỏ, không thay đổi theo từng user.
- Ảnh là một phần của phiên bản template được deploy.
- Không cần thay asset mà không triển khai lại ứng dụng.
- Ứng dụng có thể mở resource từ classpath ở mỗi worker instance.

**Không phù hợp** khi:

- Mỗi tenant upload logo riêng và thường xuyên cập nhật.
- Ảnh có kích thước lớn hoặc có nội dung cá nhân.
- File cần được xóa theo retention riêng.
- Cần sửa banner theo campaign mà không redeploy.

Trong những trường hợp này, nên dùng object storage hoặc hệ quản lý asset có quyền truy cập rõ ràng.

## 6. FileSystemResource, PathResource, ByteArrayResource và InputStreamSource

Các nguồn ảnh đều có thể được Spring chuyển thành bytes MIME, nhưng **vòng đời và khả năng đọc lại** khác nhau.

| Nguồn | Dùng khi | Ưu điểm | Điểm cần lưu ý |
| --- | --- | --- | --- |
| `ClassPathResource` | Asset đóng gói trong app/JAR | Portable qua môi trường deploy | Asset thay đổi cần redeploy |
| `FileSystemResource` | File tồn tại trên disk lúc gửi | Không cần đọc toàn bộ file trước vào heap | File phải tồn tại, readable và giữ nguyên |
| `PathResource` | File trên `java.nio.file.Path` | Thuận tiện với NIO | Có cùng vấn đề lifecycle/path |
| `ByteArrayResource` | Ảnh đã có dưới dạng `byte[]` nhỏ | Read-repeatable, không lệ thuộc file sau đó | Bytes nằm trong heap |
| Custom `InputStreamSource` | Asset từ object storage/database | Có thể stream từ backend | Mỗi lần gọi cần trả stream **mới**, ổn định |
| `InputStreamResource` | Một `InputStream` đang mở | Dùng cho một số pipeline single-use | Thường **không nên** dùng cho MIME inline cần đọc nhiều lần |

### 6.1. ByteArrayResource cho logo nhỏ

Nếu ảnh đã được tạo hoặc tải về thành bytes:

~~~java
import org.springframework.core.io.ByteArrayResource;

byte[] logoBytes = imageService.loadSmallBrandLogo(tenantId);

helper.setText(
        "Xin chào",
        "<html><body><img src=\"cid:brandLogo\"></body></html>");

helper.addInline(
        "brandLogo",
        new ByteArrayResource(logoBytes),
        "image/png");
~~~

`imageService` là service ứng dụng minh họa. Với logo nhỏ, cách này rõ ràng và dễ kiểm thử. Tuy nhiên, nhiều email đồng thời với ảnh lớn có thể tạo áp lực bộ nhớ:

~~~text
200 concurrent messages
x 8 MiB image bytes each
= ~1.6 GiB image buffers
(chưa tính MIME, object và thread overhead)
~~~

Không dùng `ByteArrayResource` chỉ vì code dễ viết nếu dữ liệu ảnh lớn hoặc số lượng worker đồng thời cao.

### 6.2. Custom InputStreamSource mở stream mới

Một số thư viện gửi mail có thể đọc resource nhiều lần, ví dụ để xác định metadata rồi khi serialize nội dung. Với object storage, adapter có thể tạo nguồn repeatable:

~~~java
import java.io.IOException;
import java.io.InputStream;

import org.springframework.core.io.InputStreamSource;

public final class VersionedImageSource
        implements InputStreamSource {

    private final ImageObjectStore store;
    private final String objectKey;
    private final String versionId;

    public VersionedImageSource(
            ImageObjectStore store,
            String objectKey,
            String versionId) {
        this.store = store;
        this.objectKey = objectKey;
        this.versionId = versionId;
    }

    @Override
    public InputStream getInputStream() throws IOException {
        // Every invocation must open a NEW stream.
        return store.openVersion(objectKey, versionId);
    }
}
~~~

Sau đó:

~~~java
helper.addInline(
        "brandLogo",
        new VersionedImageSource(store, objectKey, versionId),
        "image/png");
~~~

`ImageObjectStore` là abstraction do ứng dụng triển khai, không phải class Spring Mail. Object key/version phải được **authorize theo tenant và message**, có size/timeout/retention phù hợp. Nếu stream chỉ mở được một lần hoặc object thay đổi giữa hai lượt đọc, MIME có thể hỏng hoặc chứa ảnh không nhất quán.

### 6.3. Vì sao InputStreamResource thường không phù hợp?

~~~java
InputStream oneShot = Files.newInputStream(path);

helper.addInline(
        "brandLogo",
        new InputStreamResource(oneShot),
        "image/png");
~~~

`InputStreamResource` bọc một stream đã mở. Nếu phía gửi cần gọi `getInputStream()` nhiều lần, lần sau có thể thất bại hoặc stream đã ở cuối. Lời khuyên thực tế là:

- File trên disk: dùng `FileSystemResource` hoặc `PathResource`.
- Ảnh trong classpath: `ClassPathResource`.
- Bytes nhỏ có sẵn: `ByteArrayResource`.
- Remote storage: custom `InputStreamSource` tạo stream mới mỗi lần, cùng version.

### 6.4. Loại MIME phải đúng

Các ví dụ:

| File | Content-Type nên dùng |
| --- | --- |
| PNG | `image/png` |
| JPEG | `image/jpeg` |
| GIF | `image/gif` |
| SVG | `image/svg+xml`, nhưng khả năng hiển thị/bảo mật tùy mail client |
| WebP | `image/webp`, mức hỗ trợ tùy mail client |

Đối với email gửi cho nhiều mail client, PNG/JPEG thường là lựa chọn đơn giản và ổn định hơn các định dạng hiện đại hoặc SVG. Không tin đuôi file do người dùng cung cấp là bằng chứng nội dung thực sự là PNG; với nội dung được upload, nên kiểm tra format và kích thước ở backend.

## 7. MIME multipart/related mới liên kết HTML với ảnh

Để hiểu tại sao `addInline` giải quyết được lỗi, cần biết email HTML/inline image được đóng gói như thế nào.

Một message có cả plain text, HTML và ảnh inline thường dùng **MIME multipart**, với một phần HTML tham chiếu Content-ID của part ảnh.

### 7.1. Cấu trúc đơn giản

~~~text
multipart/related
  |
  +-- multipart/alternative
  |     |
  |     +-- text/plain; charset=UTF-8
  |     |
  |     +-- text/html; charset=UTF-8
  |           <img src="cid:brandLogo">
  |
  +-- image/png
        Content-ID: <brandLogo>
        Content-Disposition: inline
        Content-Transfer-Encoding: base64
        [image bytes]
~~~

Tùy `MimeMessageHelper` multipart mode và thư viện, MIME tree thực tế có thể gồm thêm lớp `multipart/mixed` để chứa attachment. Điều quan trọng không phải chỉ nhìn tên root, mà là **HTML và tài nguyên inline nằm trong quan hệ MIME mà mail client hiểu**.

### 7.2. Khi có cả attachment

~~~text
multipart/mixed
  |
  +-- multipart/related
  |     |
  |     +-- multipart/alternative
  |     |     +-- text/plain
  |     |     +-- text/html
  |     |           <img src="cid:brandLogo">
  |     |
  |     +-- image/png
  |           Content-ID: <brandLogo>
  |           Content-Disposition: inline
  |
  +-- application/pdf
        Content-Disposition: attachment
        filename="invoice.pdf"
~~~

Nếu dùng `MULTIPART_MODE_MIXED_RELATED`, Spring tạo cấu trúc mixed/related để hỗ trợ cả inline resource và attachment; tên, thứ tự và cấp của các body part có thể thay đổi theo triển khai/version.

### 7.3. Phân biệt addInline và addAttachment

~~~java
// Ảnh được tham chiếu ngay trong HTML:
helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");

// File người nhận cần tải hoặc mở như attachment:
helper.addAttachment(
        "invoice.pdf",
        invoiceResource,
        "application/pdf");
~~~

| `addInline` | `addAttachment` |
| --- | --- |
| Gắn Content-ID cho tham chiếu `cid:...` | Đặt content disposition attachment |
| Hướng tới hiển thị trong HTML | Hướng tới tệp đính kèm độc lập |
| Nên có reference từ HTML tới CID | Không cần HTML reference |
| Một số client vẫn có thể liệt kê như attachment | Một số client có thể preview ảnh nhưng không là inline CID |

Không nên cố biến file đính kèm thành ảnh HTML bằng cách đặt filename của attachment vào `src`:

~~~html
<!-- Sai về cơ chế tham chiếu -->
<img src="logo.png">
~~~

`logo.png` không tự map tới MIME attachment cùng tên. Cần `cid:<content-id>` hoặc URL web hợp lệ.

### 7.4. Vì sao chỉ setText(html, true) chưa đủ?

Đoạn code:

~~~java
helper.setText(
        "<img src=\"file:///opt/app/logo.png\">",
        true);
mailSender.send(message);
~~~

chỉ đánh dấu body là HTML, không bổ sung part ảnh. `HTML email` và `MIME inline resources` là hai khả năng liên quan nhưng khác nhau.

### 7.5. Lỗi multipart=false

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        false,
        "UTF-8");

helper.setText(html, true);
helper.addInline("brandLogo", resource, "image/png");
~~~

Ở chế độ không multipart, việc thêm inline resource không phù hợp và có thể phát sinh `IllegalStateException` hoặc lỗi khi build MIME. Để có inline images, sử dụng multipart helper:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");
~~~

**Không sửa lỗi bằng cách đổi `false` thành `true` một cách mù quáng ở phương thức khác.** `setText(html, true)` nói “nội dung này là HTML”; `MimeMessageHelper(message, true, "UTF-8")` nói “helper hỗ trợ multipart”. Hai boolean ở hai API có ý nghĩa khác nhau.

## 8. Nhiều ảnh inline trong cùng một email

Nếu template có logo, banner và biểu tượng liên hệ:

~~~html
<table role="presentation">
  <tr>
    <td>
      <img src="cid:companyLogo"
           alt="Company"
           width="140">
    </td>
  </tr>
  <tr>
    <td>
      <img src="cid:welcomeBanner"
           alt="Welcome"
           width="600">
    </td>
  </tr>
  <tr>
    <td>
      <p>Liên hệ với chúng tôi:</p>
      <img src="cid:supportIcon"
           alt=""
           width="20">
    </td>
  </tr>
</table>
~~~

Phần Java:

~~~java
helper.setText(plainText, htmlText);

helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");

helper.addInline(
        "welcomeBanner",
        new ClassPathResource("mail/images/banner.jpg"),
        "image/jpeg");

helper.addInline(
        "supportIcon",
        new ClassPathResource("mail/images/support.png"),
        "image/png");
~~~

**Mỗi ảnh có Content-ID riêng**, và chuỗi CID trong HTML khớp với tham số ID của `addInline`. Không dùng cùng ID cho những ảnh có bytes khác nhau. Với tài nguyên xuất hiện nhiều nơi trong cùng template, có thể tái sử dụng một CID để tránh nhúng lặp nhiều bản ảnh, tùy khả năng tương thích client và cách build MIME.

### 8.1. Tạo mapping CID rõ ràng

Ví dụ:

| Vai trò | CID | Backend resource |
| --- | --- | --- |
| Logo | `companyLogo` | `mail/images/logo.png` |
| Banner | `welcomeBanner` | `mail/images/banner.jpg` |
| Icon | `supportIcon` | `mail/images/support.png` |

Nếu template engine đổi tên placeholder, cần cập nhật mapping cùng lúc. Không suy đoán CID từ filename nếu filename chưa được xác thực hoặc có ký tự đặc biệt.

### 8.2. Đặt alt text và kích thước

Một số mail client chặn ảnh hoặc chế độ tiết kiệm dữ liệu không tải ảnh. Nên có:

~~~html
<img src="cid:companyLogo"
     alt="Company"
     width="140"
     height="48"
     style="display:block;border:0;max-width:100%;">
~~~

`alt` giúp người đọc hiểu nội dung ngay cả khi ảnh không hiển thị. Với icon chỉ trang trí, có thể dùng `alt=""`; với banner chứa thông điệp quan trọng, không nên chỉ truyền thông tin qua pixels, cần text HTML tương ứng.

Không mặc định rằng mọi CSS hiện đại hay SVG hoạt động đồng nhất trên mọi email client. Template email cần được kiểm tra bằng các client mục tiêu.

## 9. Lỗi chỉ xuất hiện sau khi triển khai Docker hoặc Kubernetes

Một kịch bản:

~~~text
Development laptop:
  C:\projects\my-app\logo.png -> exists

Container image:
  /app/application.jar
  /app/logo.png              -> may not exist

Mail recipient:
  has neither file
~~~

Có **hai tầng lỗi khác nhau**:

1. **Backend không đọc được nguồn ảnh:** đường dẫn file được cấu hình sai sau deploy; `addInline`/`send` không tìm thấy tài nguyên.
2. **Backend đọc được ảnh nhưng HTML vẫn tham chiếu file path:** MIME thiếu Content-ID tương ứng, ảnh bị hỏng trên mail client dù gửi thành công.

Phân biệt hai tầng này giúp tránh sửa sai hướng.

### 9.1. Đường dẫn tương đối phụ thuộc working directory

Ví dụ:

~~~java
Path imagePath = Paths.get("assets/mail/logo.png");
~~~

Đây là đường dẫn tương đối được resolve từ **current working directory** của tiến trình Java, không tự động từ project root hoặc `src/main/resources`.

Chạy từ IDE:

~~~text
working directory = C:\dev\project
assets/mail/logo.png may exist
~~~

Chạy trên Docker:

~~~text
working directory = /app
assets/mail/logo.png may not exist
~~~

Giải pháp:

- Asset đóng gói: `ClassPathResource`.
- Asset bên ngoài được mount: cấu hình một **absolute path** do operator quản lý, tạo `FileSystemResource`.
- Asset tải lên: lưu object storage/durable file và chỉ truyền resource reference đã kiểm tra.

Đừng ghép filesystem path trực tiếp vào HTML.

### 9.2. Mount volume đúng cũng chưa đủ cho HTML

Ví dụ Docker có mount:

~~~yaml
services:
  mail-worker:
    image: example/mail-worker:latest
    volumes:
      - /srv/mail-assets:/app/mail-assets:ro
~~~

Ứng dụng có thể đọc:

~~~text
/app/mail-assets/logo.png
~~~

nhưng người nhận vẫn **không** thể đọc:

~~~html
<img src="/app/mail-assets/logo.png">
~~~

Docker volume chỉ giải quyết quyền đọc file của ứng dụng. Vẫn phải dùng `addInline(..., resource, ...)` hoặc public HTTPS URL.

### 9.3. File nguồn không tồn tại trên mọi replica

Trong Kubernetes:

~~~text
Pod A handles upload
  /tmp/logo-100.png
       |
       v
Mail task enqueued
       |
       v
Pod B consumes task
  /tmp/logo-100.png -> missing
~~~

Một `Path` chỉ tồn tại trên local filesystem của Pod A không phải durable job payload. Với hệ thống nhiều worker, cần:

- Classpath assets giống nhau ở các replica cho tài nguyên cố định.
- Object storage/bucket có phân quyền và versioning cho upload.
- Shared filesystem đáng tin cậy nếu kiến trúc yêu cầu.
- Durable staging và cleanup có kiểm soát.

Nếu cùng một message được retry sau restart, nội dung ảnh phải còn **truy xuất được và nhất quán**, không phụ thuộc vào thư mục temp của một container đã bị hủy.

### 9.4. Quyền đọc file khác nhau theo user chạy JVM

Developer có thể chạy ứng dụng bằng tài khoản quản trị, còn container chạy user không đặc quyền:

~~~text
File exists: true
File readable by application user: false
~~~

Cần kiểm tra ownership/ACL, volume read permissions và SELinux/AppArmor policy khi có. Không chạy toàn bộ app dưới quyền root chỉ để đọc một logo; cấp quyền tối thiểu cho thư mục asset đúng nơi.

### 9.5. Windows path separator không phải URL separator

Đường dẫn Windows:

~~~text
C:\assets\logo.png
~~~

không phải một web URL hợp lệ cho mail client. Ngay cả khi tạo:

~~~java
path.toUri().toString()
~~~

kết quả có thể là:

~~~text
file:///C:/assets/logo.png
~~~

và vẫn không giải quyết được quyền truy cập của người nhận. Chuyển `Path` thành `URI` không tự động upload file lên server công khai hoặc nhúng bytes vào MIME.

## 10. Phương án dùng HTTPS URL cho ảnh email

Không phải mọi hình ảnh đều cần inline CID. Với banner thường xuyên thay đổi hoặc chiến dịch marketing, có thể dùng ảnh đặt trên một HTTPS CDN/asset server.

~~~html
<img
  src="https://cdn.example.com/email/assets/welcome-banner.png"
  alt="Chào mừng bạn"
  width="600">
~~~

Mail client của người nhận có thể yêu cầu URL thông qua chính client hoặc proxy tải ảnh; một số client mặc định chặn hoặc hỏi người dùng trước khi hiển thị ảnh.

### 10.1. Ưu điểm của HTTPS

- Không cần nhúng bytes ảnh vào từng email MIME.
- Email có thể nhỏ hơn, đặc biệt với banner lớn.
- CDN có thể cache và phục vụ ảnh tối ưu.
- Nội dung hình có thể được cập nhật ngoài quy trình build ứng dụng.
- Ít áp lực cho `JavaMailSender` khi gửi hàng loạt email.

### 10.2. Nhược điểm của HTTPS

- Ảnh phụ thuộc vào hạ tầng ngoài email: DNS, TLS, CDN và URL availability.
- Một số mail client chặn remote images vì bảo vệ quyền riêng tư.
- Người nhận offline có thể không xem được ảnh chưa cache.
- URL có thể hết hạn; email lưu nhiều tháng có thể hiển thị ảnh bị hỏng.
- URL có thông tin nhận dạng cá nhân có thể tạo privacy/tracking concerns.
- Không phải mọi web auth mechanism hoạt động trong email client.

### 10.3. Không dùng localhost hoặc địa chỉ IP nội bộ

Các ví dụ **không phù hợp cho email gửi ra Internet**:

~~~html
<img src="http://localhost:8080/logo.png">
<img src="http://127.0.0.1:8080/logo.png">
<img src="http://192.168.1.10/assets/logo.png">
<img src="http://internal-service:8080/logo.png">
~~~

`localhost` ở phía người nhận **là thiết bị của người nhận**, không phải server gửi. Các IP mạng nội bộ hoặc hostname trong Kubernetes thường không phân giải được từ Internet và việc nhúng địa chỉ nội bộ vào email cũng có thể tiết lộ thông tin hạ tầng.

### 10.4. Dùng URL có thời hạn ngắn sẽ làm email hỏng về sau

Ví dụ:

~~~html
<img src="https://storage.example.com/private/logo.png?expires=3600&signature=...">
~~~

Nếu signed URL hết hạn sau một giờ, người nhận mở lại email sau vài ngày có thể không thấy ảnh. Ngoài ra, signed URL có thể là bearer credential: nếu email bị forward hoặc được cache, người khác có thể truy cập dữ liệu trong thời gian URL còn hợp lệ.

Nếu hình ảnh là nội dung nhạy cảm, cân nhắc:

- Không đặt dữ liệu nhạy cảm vào email/remote image.
- Gửi một link tới portal có authentication thay vì cố hiển thị thumbnail.
- Nếu nghiệp vụ yêu cầu inline, chỉ nhúng dữ liệu được phép gửi cho chính người nhận trong email.
- Thiết kế retention và revoke policy tương ứng.

### 10.5. HTTP 200 không đủ nếu Content-Type sai

Một URL có thể trả:

~~~text
HTTP/1.1 200 OK
Content-Type: text/html

<html>login required</html>
~~~

Mail client kỳ vọng PNG nhưng nhận trang login, nên ảnh bị hỏng. Khi debug URL ảnh, cần xác nhận nó có thể truy cập **không cần cookie/session** của developer (nếu ảnh được thiết kế public), trả đúng content type và body ảnh thật.

Một URL dùng cookie đăng nhập của trình duyệt admin không chứng minh người nhận có quyền truy cập. Mặt khác, không tự công khai ảnh nhạy cảm chỉ để “email hiển thị được”.

### 10.6. Caching của mail proxy

Một số dịch vụ email tải ảnh qua proxy và cache, nên:

- Thời điểm request không nhất thiết trùng thời điểm người dùng mở email.
- Địa chỉ IP của request có thể thuộc proxy.
- Cache có thể khiến người dùng không thấy bản thay đổi ngay.
- Các tham số tracking cá nhân có thể bị xử lý khác nhau giữa clients.

Không thiết kế logic nghiệp vụ quan trọng dựa trên “ảnh được tải” để chứng minh email đã được đọc. Open tracking không đồng nghĩa người dùng đã xem hoặc hiểu nội dung.

## 11. Data URI/Base64 trong HTML: có thể dùng nhưng không nên mặc định

Một số developer thử thay file path bằng:

~~~html
<img
  src="data:image/png;base64,iVBORw0KGgoAAA..."
  alt="Company">
~~~

Data URI mô tả bytes ảnh trực tiếp trong thuộc tính HTML, **khác hoàn toàn với Content-ID**:

~~~text
cid:brandLogo
  -> refers to a separate MIME body part

data:image/png;base64,...
  -> embeds image bytes inside HTML attribute
~~~

### 11.1. Các hạn chế

- Hỗ trợ data URI giữa các email clients không đồng nhất, có client loại bỏ/không hiển thị.
- HTML body tăng kích thước đáng kể vì Base64 overhead.
- Một ảnh được dùng nhiều lần có thể làm HTML lặp nhiều bytes.
- HTML sanitizers hoặc security filters có thể chặn URI scheme `data:`.
- Tạo Base64 từ ảnh lớn làm tăng heap usage.

Vì vậy, với email HTML cần tương thích rộng, **CID hoặc HTTPS** thường dễ kiểm soát hơn data URI.

### 11.2. Base64 trong MIME không giống data URI

Khi `addInline` tạo một MIME part `image/png`, thư viện có thể chọn:

~~~text
Content-Transfer-Encoding: base64
~~~

để truyền ảnh qua SMTP. Nhưng HTML vẫn dùng:

~~~html
<img src="cid:brandLogo">
~~~

Không vì nhìn thấy Base64 trong raw MIME mà kết luận HTML phải chứa `data:image/png;base64,...`. Hai cơ chế khác nhau.

## 12. So sánh CID, HTTPS và Data URI

| Tiêu chí | CID inline | HTTPS URL | Data URI |
| --- | --- | --- | --- |
| Dữ liệu ảnh nằm trong email | Có, MIME part riêng | Không | Có, trong HTML |
| Phụ thuộc mạng khi mở thư | Không cần tải ảnh từ URL sau khi mail được nhận | Thường có, trừ khi đã cache | Không nếu client hỗ trợ |
| Tương thích mail client | Tốt cho nhiều client, vẫn có khác biệt | Rộng nhưng remote image có thể bị chặn | Không đồng nhất |
| Kích thước email | Tăng theo bytes/Base64 | Nhẹ hơn | Tăng mạnh trong HTML |
| Thay ảnh sau khi gửi | Không | Có thể, nhưng cache/proxy ảnh hưởng | Không |
| Quản lý vòng đời | Resource phải tồn tại khi gửi | URL phải hoạt động khi mở | Bytes đã nằm trong HTML |
| Thông tin quyền riêng tư | Không cần request tới CDN để hiện ảnh | Có thể phát sinh request/tracking | Không cần remote request |
| Khả năng offline | Có sau khi email tải về | Phụ thuộc cache | Có nếu client hỗ trợ |
| Bảo mật dữ liệu nhạy cảm | Nội dung nằm trong email, người nhận có thể forward | Cần cân nhắc access control/token | Nội dung nằm trong HTML email |

**Gợi ý lựa chọn:**

- Logo cố định nhỏ và quan trọng: ưu tiên **CID**.
- Banner marketing lớn, không nhạy cảm và cần quản lý độc lập: **HTTPS CDN** có thể phù hợp.
- Ảnh nhạy cảm hoặc cần authentication mỗi lần xem: thường nên **dùng link portal**, không cố biến nó thành inline image.
- Data URI: chỉ dùng khi đã kiểm tra danh sách email clients mục tiêu chấp nhận.

Đừng coi một phương án là hoàn hảo trên mọi client. Quyết định dựa trên **khả năng tương thích, nội dung dữ liệu, kích thước, quyền riêng tư và vòng đời tài nguyên**.

## 13. HTML template engine và vấn đề nội suy đường dẫn file

Một template có thể được render bằng Thymeleaf, FreeMarker, Mustache hoặc một renderer riêng:

~~~html
<!-- Template ban đầu -->
<img src="{{logoUrl}}" alt="Company">
~~~

Nếu code truyền:

~~~text
logoUrl = /opt/app/assets/logo.png
~~~

thì renderer chỉ thay chuỗi; nó **không tự đọc file, tạo MIME part hoặc biến đường dẫn thành HTTPS URL**.

### 13.1. Tách “nguồn ảnh” khỏi “tham chiếu HTML”

Không nên đưa nguyên `Path` vào model để template ghép thành URL:

~~~java
model.put("logoUrl", logoPath.toString());
~~~

Thay vào đó:

~~~java
model.put("logoSrc", "cid:brandLogo");
~~~

Và service gửi mail đảm bảo:

~~~java
helper.setText(plainText, renderedHtml);
helper.addInline("brandLogo", logoResource, "image/png");
~~~

Ở đây:

- Template model biết **CID hoặc HTTPS URL**.
- Mail builder biết **resource source/bytes và MIME type**.
- Provider adapter gửi message đã được chuẩn bị.

### 13.2. Không tự động chuyển mọi img src

Một helper “tự động tìm tất cả `<img src=...>` rồi tải ảnh” có thể rủi ro:

- Tải URL tùy ý do user đưa vào → **SSRF** vào mạng nội bộ.
- Đọc file path tùy ý → **path traversal/đọc file bí mật**.
- Xử lý HTML bằng regex dễ sai với quoting, entity, inline CSS, responsive markup.
- Gắn CID khác nhau không nhất quán.
- Tải ảnh lớn/redirect vô hạn hoặc file không phải ảnh.

Với email template đáng tin, tốt hơn là **khai báo danh sách inline assets rõ ràng**. Nếu phải chuyển đổi HTML động, dùng HTML parser và allowlist source/host, giới hạn byte, redirects, content type, thời gian tải, số ảnh, quyền tenant và lưu snapshot.

### 13.3. Ví dụ template asset registry

~~~java
public record InlineAsset(
        String contentId,
        String contentType,
        org.springframework.core.io.InputStreamSource source) {
}
~~~

Mail builder:

~~~java
helper.setText(plainText, renderedHtml);

for (InlineAsset asset : inlineAssets) {
    helper.addInline(
            asset.contentId(),
            asset.source(),
            asset.contentType());
}
~~~

`inlineAssets` phải được tạo từ một registry do ứng dụng kiểm soát, không từ một danh sách file/URL bất kỳ của người dùng. CID phải unique trong cùng message, content type đúng, và source phải repeatable.

## 14. Chẩn đoán ảnh hỏng bằng cách kiểm tra MIME thực tế

Để xử lý lỗi ảnh không hiển thị, cần biết **HTML đã gửi** và **MIME part của ảnh có tồn tại hay không**. Chỉ xem một log “SMTP sent successfully” chưa trả lời được.

### 14.1. Ba câu hỏi đầu tiên

1. HTML của email thực sự chứa `src` là gì? `file:`, đường dẫn tương đối, `cid:` hay HTTPS?
2. Nếu HTML dùng `cid:foo`, raw MIME có part với `Content-ID: <foo>` không?
3. MIME part đó có bytes ảnh hợp lệ, `Content-Type` đúng và nằm trong multipart relationship phù hợp không?

~~~text
Inspect HTML <img src>
         |
         +-- src is local file path
         |       |
         |       v
         |   Root cause found:
         |   not a portable email resource
         |
         +-- src is cid:logo
         |       |
         |       v
         |   Check MIME Content-ID <logo>
         |       |
         |       +-- missing -> call addInline
         |       +-- mismatch -> align CID strings
         |       +-- exists -> inspect MIME type/structure/data
         |
         +-- src is https://...
                 |
                 v
             Check URL availability,
             Content-Type, TLS, client blocking
~~~

### 14.2. Đọc raw message

Với một email test được gửi tới mailbox kiểm thử, có thể xem nguồn raw MIME:

~~~text
MIME-Version: 1.0
From: no-reply@example.com
To: test@example.net
Subject: Test logo
Content-Type: multipart/related; boundary="related-1"

--related-1
Content-Type: text/html; charset=UTF-8

<html><body>
  <img src="cid:brandLogo" alt="Brand">
</body></html>

--related-1
Content-Type: image/png
Content-ID: <brandLogo>
Content-Disposition: inline
Content-Transfer-Encoding: base64

iVBORw0KGgo...

--related-1--
~~~

Đây là **sơ đồ MIME rút gọn**. Khi có cả text/plain và HTML, hoặc attachment, cấu trúc thực tế sẽ có thêm boundaries/multipart levels. Raw MIME phải được parse theo MIME rules, không chỉ dựa vào chuỗi `Content-ID` xuất hiện ở đâu đó.

### 14.3. Các dấu hiệu tìm lỗi

| Dấu hiệu trong raw MIME | Khả năng xảy ra | Hướng sửa |
| --- | --- | --- |
| HTML chứa `file:///...` | Chưa chuyển local path thành CID/HTTPS | Dùng `cid:...` + `addInline` |
| HTML chứa `C:\...` | Template dùng đường dẫn Windows | Tách backend path khỏi HTML |
| HTML có `cid:logo` nhưng không có Content-ID | Không gọi `addInline`/lỗi build | Bổ sung inline part |
| Content-ID là `brandLogo` nhưng HTML là `cid:logo` | Hai ID không khớp | Dùng cùng chuỗi ID |
| HTML dùng `cid:<logo>` | Sai cú pháp tham chiếu thông thường | Dùng `cid:logo` |
| Content-Type `application/octet-stream` | Mail client không nhận diện ảnh | Dùng content type chính xác |
| Part có Content-Disposition attachment | Được gửi như file đính kèm | Dùng `addInline` |
| MIME base64 rỗng/không hợp lệ | Resource không đọc được hoặc bytes sai | Kiểm tra nguồn/lifecycle |
| `multipart/related` không gắn với HTML | MIME tree không phù hợp | Dùng multipart mode và helper đúng |
| HTML và MIME khớp nhưng client vẫn ẩn ảnh | Chính sách/client compatibility | Test client, xem remote/inline settings |
| Ảnh test cực lớn | Giới hạn provider/client, HTML layout | Giảm size, chọn phương án khác |

### 14.4. Content-Type đúng vẫn chưa đủ

Một MIME part có:

~~~text
Content-Type: image/png
Content-ID: <logo>
~~~

nhưng dữ liệu body là HTML hoặc một file hỏng thì ảnh vẫn không hiển thị. Nếu source là upload, cần kiểm tra **magic bytes/format thực** và giới hạn kích thước, không tin extension hoặc `Content-Type` do client upload tự khai.

### 14.5. Tài nguyên inline xuất hiện dưới dạng attachment

Một số email clients có thể liệt kê ảnh inline trong khu vực attachments dù HTML vẫn hiển thị đúng, vì chúng là các MIME parts thực sự. Điều này **không nhất thiết nghĩa build MIME sai**.

Ngược lại, nếu ảnh chỉ xuất hiện như attachment mà thẻ `<img>` vẫn hỏng, cần kiểm tra CID mapping và MIME tree. Cần phân biệt *cách client trình bày* với *cấu trúc dữ liệu*.

### 14.6. Vì sao preview HTML tại backend dễ đánh lừa?

Nếu preview service tự inject file path hoặc data URLs, nó có thể dựng một HTML khác với HTML thực tế được gửi:

~~~text
Preview path:
  template -> preview asset resolver -> browser

Email path:
  template -> MimeMessageHelper -> SMTP -> mail client
~~~

Để tránh khác biệt, nên dùng cùng renderer và cùng asset mapping CID cho cả gửi thật và preview MIME test. Preview HTML trong browser chỉ kiểm tra layout cơ bản; kiểm tra Content-ID cần nhìn message MIME.

## 15. Viết test kiểm tra ảnh inline không cần SMTP thật

Một unit test có thể tạo `MimeMessage` với `JavaMailSenderImpl` mà **không gọi `send`**, rồi kiểm tra HTML và MIME parts đã được build.

### 15.1. Ví dụ tạo MimeMessage

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

JavaMailSenderImpl mailSender = new JavaMailSenderImpl();
mailSender.setDefaultEncoding("UTF-8");

var message = mailSender.createMimeMessage();
var helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("test@example.net");
helper.setSubject("Test inline logo");
helper.setText(
        "Company logo",
        "<html><body><img src=\"cid:brandLogo\"></body></html>");

byte[] samplePng = testResources.loadPngBytes("mail/logo.png");
helper.addInline(
        "brandLogo",
        new ByteArrayResource(samplePng),
        "image/png");

message.saveChanges();

ByteArrayOutputStream output = new ByteArrayOutputStream();
message.writeTo(output);
byte[] mimeBytes = output.toByteArray();
~~~

`testResources` là helper của test suite do ứng dụng định nghĩa. Đoạn test giả lập tạo MIME không cần cấu hình host SMTP vì chưa gọi `send`.

Đối với test nhỏ có thể xem dữ liệu raw, nhưng **không nên dùng `new String(mimeBytes, UTF_8).contains(...)` làm bằng chứng duy nhất** rằng part ảnh hợp lệ. MIME có thể có encoding/boundary phức tạp, header folding, base64; nên parse MIME bằng Jakarta Mail hoặc utility chuyên dụng.

### 15.2. Parse MIME để tìm Content-ID

Ví dụ một helper đệ quy qua multipart:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public static Part findPartByContentId(
        Part node,
        String wantedContentId)
        throws Exception {

    String[] headers = node.getHeader("Content-ID");
    if (headers != null) {
        for (String value : headers) {
            String normalized = value == null
                    ? ""
                    : value.trim();
            if (normalized.startsWith("<")
                    && normalized.endsWith(">")) {
                normalized = normalized.substring(
                        1, normalized.length() - 1);
            }
            if (wantedContentId.equals(normalized)) {
                return node;
            }
        }
    }

    Object content = node.getContent();
    if (content instanceof Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            BodyPart child = multipart.getBodyPart(i);
            Part match = findPartByContentId(
                    child, wantedContentId);
            if (match != null) {
                return match;
            }
        }
    }
    return null;
}
~~~

Đây là một **test helper minh họa**, dành cho MIME fixtures nhỏ đã kiểm soát. Với email không tin cậy, parser cần giới hạn độ sâu, số part, tổng byte và xử lý message/rfc822 nested content an toàn.

### 15.3. Assert content type và bytes

~~~java
Part imagePart = findPartByContentId(
        message, "brandLogo");

assertThat(imagePart).isNotNull();
assertThat(imagePart.isMimeType("image/png")).isTrue();

byte[] actualImage;
try (var in = imagePart.getInputStream()) {
    actualImage = in.readAllBytes();
}
assertThat(actualImage).containsExactly(samplePng);
~~~

Điểm quan trọng: kiểm tra bytes đã được nhúng vào MIME part, không chỉ kiểm tra code có gọi `helper.addInline(...)` bằng Mockito. Unit test này còn giúp phát hiện resource không có dữ liệu.

### 15.4. Kiểm tra HTML chứa CID, không chứa path

Một test có thể parse `text/html` part rồi assert:

~~~text
Expected:
  <img src="cid:brandLogo">

Forbidden local-path patterns:
  file:///
  C:\
  /opt/app/assets/
  src/main/resources/
~~~

Không nên thực hiện blacklist vài chuỗi rồi coi đã đủ an toàn nếu template HTML có thể do người dùng sửa. Với template đã quản lý, có thể dùng HTML parser lấy mọi `img[src]` và chỉ cho phép `cid:` được map trong inline registry hoặc `https:` thuộc allowlist của ứng dụng.

### 15.5. Test nhiều ảnh

Với HTML có:

~~~html
<img src="cid:logo">
<img src="cid:banner">
~~~

Test:

1. Có part với Content-ID `logo` và bytes đúng PNG.
2. Có part với Content-ID `banner` và bytes đúng JPEG.
3. Hai Content-ID không trùng khi bytes khác nhau.
4. HTML không có đường dẫn local bị lộ.
5. Plain text alternative có nội dung hữu ích.
6. Attachment (nếu có) vẫn là attachment độc lập, không làm hỏng inline CID.

### 15.6. Test attachment và inline cùng lúc

~~~java
helper.setText(
        "Hóa đơn đính kèm",
        "<html><body>"
                + "<img src=\"cid:companyLogo\" alt=\"Company\">"
                + "<p>Hóa đơn đính kèm.</p>"
                + "</body></html>");

helper.addInline(
        "companyLogo",
        logoResource,
        "image/png");

helper.addAttachment(
        "invoice.pdf",
        invoiceResource,
        "application/pdf");
~~~

Sau khi build, test nên kiểm tra:

- CID image part tồn tại, content disposition phù hợp.
- PDF attachment có filename/content type chính xác.
- HTML part còn tham chiếu CID.
- Text/plain part vẫn còn nội dung.

Nếu `logoResource` hay `invoiceResource` chỉ đọc được một lần, việc serialize nhiều lần trong test có thể phát hiện vấn đề repeatability.

## 16. Integration test với SMTP server giả lập

Unit test MIME là cần thiết nhưng chưa chứng minh message được gửi trọn vẹn qua transport. Với integration test, sử dụng Mailpit, GreenMail hoặc một SMTP server test phù hợp để nhận email trong môi trường kiểm thử.

~~~text
Spring Boot test
       |
       v
WelcomeMailService
       |
       v
JavaMailSender
       |
       v
Fake SMTP server
       |
       v
Captured MIME
       |
       v
Assert:
  HTML cid
  Content-ID
  image bytes
  content type
  multipart layout
~~~

### 16.1. Test cấu hình SMTP

Ví dụ cấu hình test:

~~~yaml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    properties:
      mail:
        smtp:
          auth: false
          starttls:
            enable: false
~~~

Đây chỉ là cấu hình cho **SMTP sink nội bộ không yêu cầu authentication/TLS**. Không sử dụng nó cho SMTP production hoặc môi trường qua Internet.

Nếu chạy SMTP fake bằng Testcontainers, host/port thường là **mapped port** do container runtime cấp, không mặc định luôn là 1025 trên máy host. Cần lấy host và mapped port từ fixture/container.

### 16.2. Kiểm tra bằng SMTP test UI

Sau khi gửi, nhiều SMTP test tools cho xem:

- HTML preview.
- Text/plain.
- Raw MIME.
- Danh sách inline attachments.
- Attachment filenames.

Hãy kiểm tra **raw MIME** trước khi kết luận lỗi render thuộc mail client. Nếu không có `Content-ID`, vấn đề nằm ở cách build message. Nếu MIME đúng nhưng chỉ một client bị lỗi, nguyên nhân có thể nằm ở compatibility hoặc chính sách client đó.

### 16.3. Test không phụ thuộc provider thật

Không dùng email production, tài khoản công cộng hoặc một nhà cung cấp email thực để liên tục gửi trong test tự động:

- Có thể làm tăng spam complaint.
- Có thể tiêu hao quota hoặc chi phí.
- Có thể khiến test không ổn định do network/anti-spam.
- Có nguy cơ lộ nội dung mẫu, attachment hoặc thông tin nội bộ.

Giữ test local/isolated; sau đó có thể có một staging smoke test được ủy quyền để xác minh client compatibility với các mailbox kiểm thử hợp lệ.

### 16.4. Vì sao test SMTP vẫn không bảo đảm Gmail/Outlook hiển thị giống nhau?

MIME structure là phần có thể kiểm tra bằng giao thức, nhưng email clients có các engine HTML/security policy khác nhau. Một test SMTP sink khẳng định message đã được gửi đúng dữ liệu, **không chứng minh mọi recipient client render giống nhau**. Với template quan trọng, cần kiểm tra trên danh sách client/version cụ thể mà sản phẩm hỗ trợ.

## 17. Khác biệt giữa mail clients và cách hiển thị ảnh

Ngay cả khi MIME đã đúng, hành vi hiển thị hình ảnh vẫn phụ thuộc vào ứng dụng đọc thư, cấu hình người dùng và chính sách tổ chức.

### 17.1. Ảnh remote có thể bị chặn

Với HTML:

~~~html
<img src="https://cdn.example.com/email/logo.png" alt="Logo">
~~~

Một số client có thể:

- Chặn tải ảnh từ xa theo mặc định.
- Chỉ tải khi người dùng chọn “display images”.
- Sử dụng proxy/caching để hạn chế lộ IP và hành vi người dùng.
- Không tải tài nguyên từ domain hoặc scheme không được phép.
- Chặn mixed content hoặc HTTP không bảo mật.

Do đó, ảnh không hiện **không tự động chứng minh** URL ảnh sai hoặc Spring Mail có lỗi.

### 17.2. CID inline cũng có khác biệt

CID thường là phương án phù hợp với nhiều mail clients, nhưng vẫn có trường hợp:

- Client không hỗ trợ hoặc sanitize một phần HTML.
- MIME tree không phù hợp với parser của client.
- Cùng Content-ID bị trùng khiến parser chọn nhầm part.
- Email được forward/rewrite làm thay đổi MIME structure.
- Client liệt kê inline images trong attachments.
- Nội dung HTML bị mail security gateway sửa hoặc thay thế.

Vì vậy, trong môi trường cần hiển thị chính xác, kiểm tra các client thực tế và xem MIME **sau khi message đi qua gateway** khi có thể.

### 17.3. Một số client loại bỏ CSS/background image

Không nên nhầm:

~~~html
<img src="cid:banner">
~~~

với:

~~~html
<div style="background-image:url('cid:banner')">
  ...
</div>
~~~

Mức hỗ trợ CSS background image trong email clients khác mức hỗ trợ thẻ `img`; một số engine render email hạn chế CSS hoặc yêu cầu markup riêng. Nếu hình ảnh mang thông tin quan trọng, dùng `<img>` với alt text và HTML text fallback thường dễ kiểm soát hơn.

### 17.4. SVG, WebP và animated GIF

Các định dạng có mức hỗ trợ và security policy khác nhau:

| Định dạng | Đặc điểm | Lưu ý cho email |
| --- | --- | --- |
| PNG | Hỗ trợ alpha/transparency, phù hợp logo | Kích thước có thể lớn nếu ảnh chụp |
| JPEG | Phù hợp ảnh chụp/banner | Không hỗ trợ transparency |
| GIF | Có thể có animation | Một số client chỉ hiển thị frame đầu |
| SVG | Vector, kích thước nhỏ | Có client lọc hoặc không render vì bảo mật |
| WebP | Nén hiệu quả | Client cũ có thể không hỗ trợ |

Nếu asset quan trọng phải hiển thị rộng, cân nhắc xuất PNG/JPEG theo kích thước phù hợp. Không đưa SVG do người dùng upload trực tiếp vào email mà không có kiểm tra bảo mật.

### 17.5. Dark mode và kích thước ảnh

Trong dark mode, logo nền trong suốt có thể trở nên khó nhìn nếu chữ/logo có màu tối. Một số client tự đổi màu nền, trong khi ảnh không đổi:

~~~html
<img src="cid:companyLogo"
     alt="Company"
     width="160"
     style="display:block;border:0;">
~~~

Đặt kích thước ảnh cụ thể hoặc dùng bảng layout thường giúp hạn chế ảnh quá lớn trên mobile. Có thể cần phiên bản logo phù hợp dark mode hoặc nền trung tính theo template đã kiểm thử, nhưng không nên dựa hoàn toàn vào CSS media queries vì độ hỗ trợ khác nhau.

### 17.6. Khi mail được forward

Forwarding có thể:

- Giữ nguyên MIME và CID parts.
- Chuyển email thành attachment `message/rfc822`.
- Chỉ trích một phần HTML và làm mất inline resource.
- Thay đổi Content-ID hoặc tài nguyên theo chính sách gateway.

Ứng dụng gửi không thể kiểm soát mọi hành vi forward của mọi client. Để nội dung vẫn có ý nghĩa, không đặt thông tin cốt lõi chỉ trong ảnh; cần text HTML/plain text tương ứng.

## 18. Bảo mật khi xử lý đường dẫn ảnh cục bộ

Lỗi file path không chỉ là vấn đề hiển thị; việc lấy file theo đường dẫn không đáng tin có thể khiến ứng dụng đọc dữ liệu nhạy cảm hoặc lộ thông tin hệ thống.

### 18.1. Không dùng trực tiếp file path do người dùng cung cấp

Ví dụ API nguy hiểm:

~~~json
{
  "recipient": "customer@example.net",
  "logoPath": "../../secrets/app-config.yml"
}
~~~

Nếu backend:

~~~java
Path path = Paths.get(request.logoPath());
helper.addInline("logo", new FileSystemResource(path), "image/png");
~~~

thì attacker có thể cố chọn file nằm ngoài thư mục asset dự kiến. Content-Type `image/png` chỉ là nhãn; nó **không ngăn thư viện đọc bytes** của một file khác và gửi theo email.

Giải pháp tốt hơn: API chỉ nhận **asset ID** trong danh mục đã được authorize:

~~~json
{
  "templateId": "welcome-v3",
  "brandAssetId": "tenant-asset-opaque-id"
}
~~~

Backend ánh xạ ID tới object/file thuộc tenant, kiểm tra quyền, version, content type và kích thước trước khi gửi.

### 18.2. Canonical path và symlink

Nếu bắt buộc lưu file trên disk dưới một thư mục chung, cần bảo vệ khỏi path traversal và symlink:

~~~text
allowedRoot = /srv/mail-assets/tenants/T1
candidate   = /srv/mail-assets/tenants/T1/../../secrets
~~~

Chỉ dùng `candidate.normalize().startsWith(allowedRoot)` có thể chưa xử lý hết **symlink** và các thay đổi filesystem cạnh tranh. Với nội dung nhạy cảm, nên:

1. Sử dụng resource ID/object key được tạo bởi hệ thống, không phải user-supplied path.
2. Giới hạn root và quyền OS.
3. Khi dùng filesystem, resolve/canonicalize phù hợp, cân nhắc symlink, kiểm tra regular file.
4. Mở stream theo quyền tối thiểu.
5. Cố định nội dung hoặc version để tránh file thay đổi sau validation.

Không cho worker đọc bất kỳ đường dẫn nào trên host chỉ vì caller có quyền gửi email.

### 18.3. SSRF khi tự động tải ảnh từ URL

Nếu một chức năng nhận `imageUrl` từ user rồi tải và nhúng ảnh:

~~~text
User provides imageUrl = http://127.0.0.1:8080/admin
                       = http://169.254.169.254/...
                       = http://internal-service/secret
~~~

đó có thể là **Server-Side Request Forgery**. Không dùng một HTTP client tùy ý tải mọi URL và đưa nội dung vào email.

Một thiết kế an toàn hơn:

- Chỉ cho phép asset server/host thuộc allowlist.
- Không chấp nhận IP riêng, loopback, link-local, metadata endpoint.
- Kiểm tra DNS và kết nối thực, không chỉ chuỗi host ban đầu.
- Kiểm soát redirects, timeouts, total byte limits và content type.
- Không forward nội bộ Authorization/Cookie/secret vào request tải ảnh.
- Ưu tiên tải asset qua trusted object storage SDK bằng key đã được authorize.

Mọi công cụ tự động “convert remote image to inline” đều cần boundary bảo mật tương ứng.

### 18.4. Dùng file URI có thể lộ cấu trúc nội bộ

Một email HTML chứa:

~~~html
<img src="file:///home/service-account/private/logo.png">
~~~

có thể tiết lộ tên thư mục, tên user nội bộ, OS hoặc cách triển khai ứng dụng cho người nhận. Đây thường không phải bí mật đủ để tấn công trực tiếp, nhưng không cần thiết và không nên xuất hiện trong HTML public.

Ngoài ra, một số mail clients/security filters có thể gắn cờ hoặc loại bỏ `file:` vì rủi ro local file access.

### 18.5. Ảnh có thể chứa dữ liệu nhạy cảm

Ngay cả khi sửa bằng CID, nếu ảnh là hóa đơn, thẻ căn cước, mã QR đăng nhập hoặc nội dung cá nhân, nó trở thành **dữ liệu đính kèm trong email**. Người nhận có thể:

- Forward.
- Lưu raw MIME.
- Tải hình ra disk.
- Đồng bộ email tới dịch vụ/thiết bị khác.

Không nên dùng CID để “che” dữ liệu nhạy cảm: inline image cũng là một MIME part có bytes thực. Nếu cần kiểm soát quyền truy cập hoặc revoke, một link tới portal có xác thực, thời hạn và audit có thể phù hợp hơn.

### 18.6. Không biến một đường dẫn ngoài thành quyền truy cập

Ví dụ một `brandAssetId` nên được resolve dựa trên tenant:

~~~java
InlineAsset asset = assetService.resolveAuthorized(
        authenticatedTenantId,
        brandAssetId);
~~~

`resolveAuthorized` là API do ứng dụng định nghĩa, phải kiểm tra tenant ownership, trạng thái asset, loại file, size và version. Một file nằm trong cùng bucket không có nghĩa mọi tenant đều có quyền dùng nó.

### 18.7. Logging và quan sát

Không log nguyên:

~~~text
email HTML
image bytes
signed storage URL
local secret path
raw MimeMessage
~~~

trong production chỉ để debug ảnh. Nên log các thông tin ít nhạy cảm:

~~~json
{
  "event": "mail.inline_asset_added",
  "deliveryId": "opaque-id",
  "assetType": "BRAND_LOGO",
  "contentId": "brandLogo",
  "mimeType": "image/png",
  "sizeBytes": 4821
}
~~~

Nếu `contentId` có nguồn không tin cậy hoặc cardinality lớn, không dùng làm metric label. Với lỗi file path, dùng mã như `INLINE_ASSET_NOT_FOUND`, `INLINE_ASSET_UNREADABLE`, `MIME_INLINE_CID_MISMATCH`; không đưa path/tên khách hàng vào tag.

## 19. Gửi bất đồng bộ: khi nguồn ảnh tồn tại lúc enqueue nhưng biến mất lúc send

Đây là biến thể rất phổ biến của lỗi file path trong production.

### 19.1. Ví dụ sai: tạo task giữ local Path của request

~~~java
public void submitWelcome(
        String recipient,
        MultipartFile uploadedLogo) throws IOException {

    Path temp = Files.createTempFile("logo-", ".png");
    uploadedLogo.transferTo(temp);

    asyncMailQueue.submit(
            new WelcomeMailJob(recipient, temp.toString()));

    Files.deleteIfExists(temp);
}
~~~

Worker có thể chạy sau khi file đã bị xóa. Với hệ thống có queue bền vững, task còn có thể được tiêu thụ bởi **replica khác** không có file đó.

### 19.2. Giải pháp: lưu asset bền vững trước enqueue

~~~text
HTTP upload / asset lookup
           |
           v
Validate tenant / content / size
           |
           v
Persist image to authorized object storage
  - immutable object key
  - version / checksum
  - retention sufficient for retries
           |
           v
Commit mail outbox job with asset reference
           |
           v
Async worker resolves image source
           |
           v
Build MIME with cid + addInline
           |
           v
JavaMailSender.send
           |
           v
Mark job outcome + cleanup by policy
~~~

Nếu file đã nằm trong classpath cố định, không cần upload lại cho mỗi email. Chỉ cần đảm bảo **mọi worker** chạy phiên bản ứng dụng có asset đúng.

### 19.3. Khi phải stage ra file tạm

Một số API gửi mail hoặc thư viện xử lý ảnh thuận tiện hơn khi có local file. Worker có thể:

1. Tải object version chính xác xuống một thư mục staging riêng.
2. Giới hạn tổng bytes và dung lượng filesystem.
3. Kiểm tra checksum/content type khi yêu cầu.
4. Gắn `FileSystemResource` vào `addInline`.
5. Gọi `mailSender.send` khi file còn tồn tại.
6. Cleanup trong `finally` **sau khi transport kết thúc**.

~~~java
Path staged = stageAuthorizedImage(assetRef);

try {
    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            "UTF-8");

    helper.setFrom("no-reply@example.com");
    helper.setTo(recipient);
    helper.setSubject("Notification");
    helper.setText(
            "Your notification",
            "<html><body>"
                    + "<img src=\"cid:brandLogo\">"
                    + "</body></html>");

    helper.addInline(
            "brandLogo",
            new FileSystemResource(staged),
            "image/png");

    mailSender.send(message);
} finally {
    Files.deleteIfExists(staged);
}
~~~

`stageAuthorizedImage(...)` là abstraction ứng dụng, phải giới hạn size, storage, quyền tenant và timeout. Nếu `Files.deleteIfExists` thất bại trong `finally`, code production cần lưu lỗi cleanup để sweeper xử lý mà không che mất lỗi gửi SMTP chính. Không dùng `finally` để xóa object durable gốc còn cần cho retry.

### 19.4. Crash trước cleanup

`finally` không chạy nếu process bị kill đột ngột hoặc node mất nguồn. Với staging trong production, nên có **sweeper** theo thời hạn và job ownership, quota/monitoring cho disk usage và quyền OS hạn chế.

Không xóa file đang được worker khác sử dụng dựa chỉ vào tuổi file nếu share staging directory. Gắn lifecycle metadata/lease hoặc đặt staging riêng theo attempt để cleanup an toàn.

### 19.5. Retry cần cùng nội dung, không chỉ cùng filename

Giả sử banner tại `/assets/current-banner.png` được thay giữa attempt 1 và 2:

~~~text
Attempt 1 -> logo version V1
Attempt 2 -> logo version V2
~~~

Hai email cùng một business delivery có thể có nội dung khác nhau. Với notification cần audit/reproducibility, lưu **immutable asset version** hoặc checksum để retry cùng nội dung. Nếu nghiệp vụ chủ ý dùng asset mới khi retry, đó phải là một policy rõ, không phải do file bị ghi đè vô tình.

### 19.6. SMTP accepted chưa phải lý do xóa mọi dữ liệu nguồn

Khi `send` trả thành công, SMTP relay thường đã chấp nhận submission theo quan sát client. Nhưng nếu database mark `SENT` thất bại, application có thể cần đối soát/retry policy. Asset retention nên gắn với toàn bộ vòng đời delivery/outbox, không chỉ việc `send` return. Tránh xóa logo/banner snapshot ngay khi chưa có durable record về outcome.

## 20. Kích thước email, Base64 và chi phí của inline image

CID inline giải quyết vấn đề ảnh không thể truy cập qua local file path, nhưng không miễn phí về băng thông và kích thước email.

### 20.1. Base64 làm dữ liệu truyền lớn hơn

Một ảnh PNG kích thước 300 KiB khi được encode Base64 có thể tăng khoảng một phần ba số byte trước khi cộng header, CRLF và MIME boundaries.

~~~text
Raw PNG bytes
     |
     v
MIME Base64 encoding (~4/3)
     |
     v
SMTP message bytes
     |
     v
Provider message SIZE limit
~~~

Đây là lý do nhà cung cấp có thể từ chối email có nhiều ảnh inline/attachment dù mỗi file trên disk trông không quá lớn. Giới hạn áp dụng cho **message MIME cuối cùng**, không chỉ tổng kích thước file gốc.

### 20.2. Dùng một logo trong 100.000 email

Nếu nhúng một logo 100 KiB vào mỗi email, đó là 100.000 lần truyền dữ liệu ảnh trong các message riêng biệt, chưa tính overhead:

~~~text
100 KiB x 100,000 messages
= ~9.5 GiB raw image bytes
~~~

Sau MIME/Base64 và overhead, số bytes qua SMTP còn cao hơn. Với campaign rất lớn, một ảnh public HTTPS trên CDN có thể giảm kích thước mỗi message, nhưng phải chấp nhận khả năng client chặn ảnh từ xa.

### 20.3. Tối ưu ảnh trước khi nhúng

Một số nguyên tắc:

- Resize về kích thước thực sử dụng trong email; không nhúng ảnh 4000px để hiển thị 150px.
- Chọn PNG cho logo/biểu tượng cần sắc nét, JPEG cho ảnh chụp/banner.
- Nén trước ở asset pipeline, không encode lại/resize mọi ảnh cho mỗi mail attempt nếu không cần.
- Giới hạn tổng bytes của inline assets và attachments theo loại email.
- Giới hạn số lượng ảnh inline và MIME parts.
- Dùng một CID cho nhiều vị trí hiển thị cùng ảnh khi tương thích client và yêu cầu template cho phép.
- Ước lượng kích thước MIME cuối trước khi chọn SMTP provider có quota/SIZE thấp.

### 20.4. Không thực hiện xử lý ảnh nặng trong SMTP thread

Nếu mỗi email tự tải logo, resize, tính checksum và convert format trong thread gửi SMTP, throughput có thể giảm và timeout khó phân tích:

~~~text
Mail worker:
  remote download
  -> resize
  -> format convert
  -> MIME build
  -> SMTP send
~~~

Với asset cố định, có thể chuẩn bị các phiên bản ảnh trước và cache kết quả phù hợp. Với asset theo tenant, cache cần có tenant scoping, versioning và memory bounds; không cache bytes không giới hạn từ tất cả uploads.

### 20.5. Resource repeatability vs memory

Hai lỗi hiệu năng phổ biến:

**Lỗi 1:** chuyển mọi ảnh thành `byte[]` lớn vì sợ `FileSystemResource` không hoạt động.

~~~java
byte[] all = Files.readAllBytes(bigImagePath);
helper.addInline(
        "hero",
        new ByteArrayResource(all),
        "image/jpeg");
~~~

Điều này có thể tạo peak heap lớn khi gửi nhiều message đồng thời.

**Lỗi 2:** tạo stream chỉ dùng một lần để “tiết kiệm bộ nhớ”:

~~~java
InputStream once = remoteStore.open(objectKey);
helper.addInline(
        "hero",
        new InputStreamResource(once),
        "image/jpeg");
~~~

Nó có thể hỏng khi thư viện đọc lại stream. Thiết kế đúng là **repeatable source với vòng đời và byte limits rõ**, không nhất thiết giữ tất cả bytes trong RAM.

### 20.6. Tách thời gian chuẩn bị asset khỏi thời gian SMTP

Một bảng metric:

| Giai đoạn | Metric gợi ý |
| --- | --- |
| Resolve asset metadata | `mail_asset_resolve_duration` |
| Load/stage image | `mail_asset_load_duration` |
| Build MIME | `mail_mime_build_duration` |
| SMTP submission | `mail_smtp_submit_duration` |
| Inline asset bytes | `mail_inline_asset_bytes` |
| Asset source failures | `mail_inline_asset_failures_total` |
| Staging disk usage | `mail_staging_bytes` |

Trong Micrometer, giữ tag hữu hạn (`asset_kind`, `source_type`, `error_code`) thay vì dùng raw filesystem path, URL có token hoặc email recipient làm labels.

## 21. Bảng chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Chỉ thấy alt text | `src` dùng local path/file URI hoặc ảnh bị chặn | Xem raw HTML, chuyển CID/HTTPS |
| Ảnh hiện trong IDE nhưng mất trong email | Preview có quyền đọc file local | Kiểm tra MIME thực tế |
| Gửi thành công nhưng ảnh hỏng ở mọi client | HTML thiếu CID part hoặc URL không truy cập | Kiểm tra `Content-ID`, raw MIME |
| HTML có `cid:logo`, part là `<brandLogo>` | ID không khớp | Sửa mapping |
| Inline image xuất hiện như attachment | Client hiển thị part inline như tệp | Kiểm tra HTML có render được; có thể là client behavior |
| Có attachment `logo.png` nhưng HTML hỏng | Dùng `addAttachment` thay `addInline` | Dùng `addInline` và `cid:` |
| `IllegalStateException` khi addInline | Helper không ở multipart mode | Tạo helper multipart trước |
| Ảnh chỉ hỏng sau đóng gói JAR | Dùng `src/main/resources` hoặc `getFile()` | Dùng `ClassPathResource` |
| Ảnh chỉ hỏng trong container | Path khác hoặc volume không mount/readable | Kiểm tra runtime asset; vẫn phải dùng CID |
| Pod khác không đọc được ảnh | Job lưu local temp path của Pod cũ | Dùng durable object/version reference |
| Email lúc hiện lúc không khi chạy async | File đã bị cleanup hoặc đổi trước `send` | Giữ snapshot tới khi gửi xong |
| Image resource stream error | `InputStreamResource` single-use | Dùng repeatable source |
| `FileNotFoundException` khi gửi | File không tồn tại ở send time | Sửa source/lifecycle |
| `AccessDeniedException` | OS user/ACL không có quyền đọc | Chỉnh quyền tối thiểu phù hợp |
| Ảnh hiển thị sai định dạng | Content-Type hoặc bytes không phù hợp | Validate format, đúng MIME type |
| PNG quá lớn làm SMTP reject | Tổng MIME/Base64 vượt limit | Resize/nén/chọn HTTPS/link |
| Ảnh HTTPS hiện trên browser nhưng không trên mail | URL cần cookie/auth hoặc client block remote images | Thử request public không cookie, xem privacy settings |
| `http://localhost:8080/logo.png` không hiện | URL trỏ máy người nhận | Dùng HTTPS public/CID |
| Signed URL chỉ hiện trong ngày đầu | Link hết hạn | Dùng asset public ổn định hoặc CID |
| Data URI không hiện ở Outlook/client nào đó | Client không hỗ trợ hoặc strip `data:` | Dùng CID/HTTPS phù hợp |
| CSS background image không hiện | Client không hỗ trợ CSS | Dùng thẻ `img` và HTML text fallback |
| SVG bị chặn | Mail client/security sanitizer | Dùng PNG/JPEG đã kiểm tra |
| Có CID part nhưng vẫn ảnh hỏng | MIME tree, bytes, content type hoặc CID parser | Inspect raw MIME/decoded image |
| Logo màu tối biến mất trong dark mode | Client đổi nền nhưng không đổi ảnh | Chọn asset/template có contrast tốt |
| Hình hiện nhưng mail bị đánh spam | Không nhất thiết do CID; nội dung, domain, size, reputation | Xem authentication/deliverability |
| Log lộ local path | Template mang filesystem path vào HTML/log | Tách asset ID, sanitize logs |
| Retry tạo email khác ảnh | File nguồn bị overwrite giữa attempts | Pin version/checksum của asset |
| Đọc URL ảnh do user truyền gây truy cập nội bộ | SSRF | Dùng allowlist/trusted object storage |

### 21.1. Ưu tiên chẩn đoán theo thứ tự

Đừng bắt đầu bằng cách thay SMTP provider hoặc tăng timeout khi duy nhất ảnh bị hỏng nhưng email đã nhận:

~~~text
1. Inspect HTML src
2. Inspect MIME Content-ID + Content-Type
3. Inspect actual image bytes
4. Check multipart layout
5. Check backend resource lifecycle
6. Check recipient client rendering behavior
7. Check URL/provider/security gateways if relevant
~~~

Nếu local file path còn nằm trong HTML, đó là lỗi ở **bước chuẩn bị nội dung**, không phải chứng cứ rằng mạng SMTP có vấn đề.

## 22. Runbook: ảnh hỏng sau khi deploy

### Tình huống

Trên máy developer, email welcome có logo; sau khi deploy lên container, người nhận chỉ thấy ảnh hỏng.

### Bước 1 — Kiểm tra `src` của email thực

Nếu thấy:

~~~html
<img src="src/main/resources/mail/logo.png">
~~~

thì cần sửa ngay sang `cid:companyLogo` hoặc URL HTTPS phù hợp. Việc image nằm trong source tree chỉ có ý nghĩa đối với build process.

Nếu đã thấy:

~~~html
<img src="cid:companyLogo">
~~~

thì chuyển sang bước MIME.

### Bước 2 — Kiểm tra Content-ID part

Trong raw MIME, tìm part:

~~~text
Content-ID: <companyLogo>
Content-Type: image/png
~~~

Nếu không có, kiểm tra code `helper.addInline` có chạy hay không, MIME helper có multipart không, và có đang gửi **đúng MimeMessage được build** không.

### Bước 3 — Kiểm tra source resource khi worker chạy

Với classpath:

~~~java
ClassPathResource resource =
        new ClassPathResource("mail/logo.png");
~~~

Nếu classpath asset không tồn tại trong build artifact, cần điều chỉnh packaging. Không dùng `resource.getFile()` khi ảnh có thể nằm trong JAR.

Với filesystem:

~~~text
Configured path: /app/assets/logo.png
Does it exist in container?
Is it readable by JVM user?
Is it the correct PNG file?
~~~

Không hardcode đường dẫn máy phát triển vào bản production.

### Bước 4 — Kiểm tra MIME bytes

Nếu part có Content-ID nhưng bytes rỗng/sai:

- Kiểm tra file zero bytes/corrupt.
- Xem resource read exceptions.
- Kiểm tra file bị thay/cleanup trong quá trình gửi.
- Kiểm tra content type đúng format.
- Kiểm tra custom `InputStreamSource` có trả stream mới.

### Bước 5 — Chẩn đoán theo client

Nếu MIME hợp lệ ở SMTP test server nhưng một client không hiển thị:

- Xem mail client có chặn remote image không.
- Xem content type/format và MIME tree.
- Kiểm tra CSS/background image.
- Kiểm tra chính sách gateway hoặc image proxy.
- Đảm bảo logo có alt text và không chứa thông tin cốt lõi chỉ trong pixels.

### Bước 6 — Khắc phục và quan sát

Sau khi triển khai cách tham chiếu đúng:

1. Gửi tới mailbox test, không tới một danh sách người nhận production để thử nghiệm hàng loạt.
2. Kiểm tra raw MIME và các clients được hỗ trợ.
3. Quan sát `INLINE_ASSET_NOT_FOUND`/`MIME_PREPARATION_FAILED`.
4. Nếu có async queue, kiểm tra retry vẫn dùng đúng asset version.
5. Giữ log/correlation ID tối thiểu cho incident audit.

## 23. Ví dụ thực tế: sửa một email welcome có ảnh logo bị hỏng

Giả sử ứng dụng có một template welcome cho người dùng mới. Ban đầu, code sinh HTML bằng cách đưa trực tiếp local path vào `src`.

### 23.1. Cách viết sai

~~~java
@Service
public class WrongWelcomeMailService {

    private final JavaMailSender mailSender;

    public WrongWelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient) throws MessagingException {
        Path logo = Path.of(
                "/opt/app/assets/brand-logo.png");

        String html = """
                <html>
                  <body>
                    <img src="%s" alt="Brand">
                    <h1>Welcome!</h1>
                  </body>
                </html>
                """.formatted(logo);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, "UTF-8");

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Welcome!");
        helper.setText(html, true);
        mailSender.send(message);
    }
}
~~~

**Lý do sai:**

- `formatted(logo)` chỉ chuyển `Path` thành chuỗi, không đọc file.
- HTML chứa `<img src="/opt/app/assets/brand-logo.png">`.
- Helper không tạo part `image/png`.
- Mail recipient không có origin/đường dẫn filesystem của server.
- `MimeMessageHelper(message, "UTF-8")` ở đây không được cấu hình multipart, nên không có đường để thêm inline asset.

SMTP có thể gửi hoàn toàn thành công vì HTML chỉ là text. Đây là ví dụ điển hình của **email gửi được nhưng giao diện không đúng**.

### 23.2. Cách sửa với logo trong classpath

Nếu logo cố định nằm trong:

~~~text
src/main/resources/mail/images/brand-logo.png
~~~

thì sửa thành:

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient) throws MessagingException {
        String plainText = """
                Welcome!
                Thank you for joining us.
                """;

        String htmlText = """
                <html>
                  <body>
                    <img src="cid:brandLogo"
                         alt="Brand"
                         width="160"
                         style="display:block;border:0;">
                    <h1>Welcome!</h1>
                    <p>Thank you for joining us.</p>
                  </body>
                </html>
                """;

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8");

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Welcome!");

        helper.setText(plainText, htmlText);

        helper.addInline(
                "brandLogo",
                new ClassPathResource(
                        "mail/images/brand-logo.png"),
                "image/png");

        mailSender.send(message);
    }
}
~~~

Phần HTML **không chứa đường dẫn filesystem**. Nó chỉ nhắc tới CID mà MIME part cùng message cung cấp. Khi logo nằm trong JAR, `ClassPathResource` vẫn có thể mở stream của asset.

### 23.3. Nếu logo thay đổi theo tenant

Không nên tạo nhiều folder tùy ý dựa trên input:

~~~java
Path logo = Paths.get(
        "/assets/", request.getTenantId(), request.getLogoName());
~~~

Thay vào đó, service đáng tin cậy resolve một asset reference:

~~~java
BrandAssetRef asset = brandAssets.requireAuthorizedLogo(
        authenticatedTenantId);

InlineAsset logo = brandAssets.openVersionedAsset(
        asset.objectKey(), asset.versionId());
~~~

Sau đó:

~~~java
helper.setText(plainText, renderedHtmlWithCidBrandLogo);
helper.addInline(
        "brandLogo",
        logo.source(),
        logo.contentType());
~~~

`BrandAssetRef` và `brandAssets` là abstraction ứng dụng. Cần enforce tenant ownership, immutable version, size/format và source read-repeatability. Đường lưu trữ thực có thể là object storage hoặc filesystem; người nhận không cần biết.

### 23.4. Nếu dùng HTTPS thay vì CID

Khi marketing banner không nhạy cảm nằm trên CDN:

~~~java
String approvedBannerUrl =
        assetCatalog.requirePublicMailImageUrl("welcome-banner");

String html = """
        <html>
          <body>
            <img src="%s"
                 alt="Welcome"
                 width="600">
          </body>
        </html>
        """.formatted(escapeHtmlAttribute(approvedBannerUrl));
~~~

`assetCatalog` và `escapeHtmlAttribute` là ví dụ API ứng dụng; method escape phải bảo đảm encoding đúng ngữ cảnh HTML attribute. URL cần được chọn từ catalog/allowlist đáng tin, dùng HTTPS, tồn tại lâu đủ cho email và không đòi browser session của developer.

Với ảnh HTTPS, **không gọi `addInline`** trừ khi muốn gửi thêm một part ảnh độc lập. Mail client sẽ tải qua mạng khi chính sách cho phép.

### 23.5. Kết quả cần kiểm chứng

| Trước khi sửa | Sau khi sửa bằng CID |
| --- | --- |
| HTML có `src="/opt/app/assets/logo.png"` | HTML có `src="cid:brandLogo"` |
| MIME chỉ có text/html | MIME có text/html và image/png inline |
| Không có `Content-ID` | Có `Content-ID: <brandLogo>` |
| Mail recipient cần file trên server | Bytes ảnh nằm trong MIME message |
| Dễ hỏng khi đổi IDE/Docker/K8s | Dùng source classpath/asset đúng runtime |
| Code không quản lý vòng đời asset | Source phải tồn tại khi build/gửi, có policy cleanup |

## 24. Các câu hỏi thường gặp

**“Tại sao ảnh hiển thị trong trang web nhưng không trong email?”**  
Trang web có origin và có thể truy cập ảnh theo URL/path của web server. Email được đọc trên thiết bị/app khác, thường không có base URL hoặc quyền truy cập filesystem của server gửi. Dùng CID inline hoặc HTTPS URL phù hợp.

**“Spring Mail có tự tải file khi thấy `<img src="/path">` không?”**  
Không. HTML là nội dung text. Bạn phải chủ động gọi `MimeMessageHelper.addInline` hoặc dùng URL web có thể truy cập.

**“Nếu đường dẫn tuyệt đối đúng trên server thì sao ảnh vẫn hỏng?”**  
Đường dẫn đúng chỉ giúp **backend** tìm file. Người nhận vẫn không biết/không được phép đọc file đó. Phải biến bytes thành MIME part hoặc public HTTPS asset.

**“Đổi `C:\logo.png` thành `file:///C:/logo.png` có đủ không?”**  
Không. `file:` vẫn là scheme chỉ filesystem của máy đang diễn giải URL, mail client thường không được phép đọc. Đổi cú pháp không upload/nhúng ảnh.

**“Có thể để `src="./logo.png"` không?”**  
Không nên dựa vào đường dẫn tương đối trong email. MIME HTML thường không có HTTP base URL tương ứng, và attachment filename không tự resolve thành URL.

**“Nếu thêm file bằng addAttachment thì img sẽ hiện không?”**  
Không tự động. `addAttachment` tạo attachment; `<img>` cần `cid:<id>` tham chiếu part inline được thêm bằng `addInline` hoặc URL HTTPS.

**“Content-ID và tên file có phải giống nhau không?”**  
Không. CID là identifier của MIME part; filename chỉ là metadata của file. Bạn có thể dùng CID `brandLogo` cho ảnh lưu dưới tên `logo-v3.png`. HTML phải khớp CID, không phải filename.

**“Vì sao addInline có hai tham số giống nhau?”**  
Phương thức nhận content ID và source của ảnh. `addInline("logo", resource, "image/png")` tạo part có ID `logo`, còn HTML dùng `cid:logo` để trỏ tới part đó.

**“Có cần viết dấu ngoặc nhọn trong HTML CID không?”**  
Không. Với Content-ID header `<brandLogo>`, HTML thường dùng `cid:brandLogo`, không phải `cid:<brandLogo>`.

**“Có cần multipart=true để dùng CID không?”**  
Có. Inline image cần một MIME part riêng, nên helper phải được cấu hình multipart. `MULTIPART_MODE_MIXED_RELATED` là một lựa chọn phù hợp khi muốn hỗ trợ inline và attachment.

**“`setText(html, true)` đã đủ chưa?”**  
Chưa. Nó chỉ đánh dấu HTML content, không tạo inline image part. Cần multipart helper và `addInline`.

**“Nên gọi setText hay addInline trước?”**  
Nên đặt text/HTML bằng `setText` rồi thêm `addInline`, theo khuyến nghị của `MimeMessageHelper` để giảm vấn đề tương thích với một số mail clients.

**“File nằm trong src/main/resources thì dùng FileSystemResource được không?”**  
Trong IDE có thể tìm thấy file, nhưng sau đóng gói JAR đường source đó thường không còn. Với asset đóng gói, dùng `ClassPathResource` để đọc qua classpath.

**“Vì sao ClassPathResource.getFile() bị lỗi sau deploy?”**  
Resource nằm bên trong JAR không nhất thiết có một file riêng trên disk. Truyền `ClassPathResource` trực tiếp vào `addInline` hoặc mở stream, không ép thành `File`.

**“Ảnh đặt trong static của Spring Boot có tự thành URL email không?”**  
Không tự động. Nếu ứng dụng phục vụ ảnh qua HTTP, có thể tạo URL HTTPS public phù hợp, nhưng `/static/logo.png` hoặc local classpath path trong HTML email không tự biến thành URL Internet.

**“Có nên dùng localhost URL khi ứng dụng và SMTP server cùng máy?”**  
Không cho email người nhận bên ngoài. `localhost` khi mail client tải ảnh trỏ về **máy người nhận** hoặc proxy, không phải backend của bạn.

**“Ứng dụng chạy Docker có đọc file từ host được không?”**  
Chỉ khi file được đóng gói/mount và quyền đọc phù hợp. Nhưng kể cả backend đọc được, HTML vẫn phải dùng CID/HTTPS, không dùng container path.

**“Nếu file ở /tmp và gửi @Async thì sao?”**  
File có thể bị xóa trước khi worker gửi hoặc nằm trên replica khác. Dùng durable asset reference/snapshot, giữ file đến khi gửi hoàn tất, có cleanup và retry policy.

**“Có thể dùng InputStreamResource cho ảnh inline không?”**  
Không nên mặc định, vì nó bọc stream single-use. Nếu MIME encoder đọc nhiều lần, có thể lỗi. Dùng `FileSystemResource`, `ClassPathResource`, `ByteArrayResource` hoặc custom repeatable `InputStreamSource`.

**“Nếu chỉ có byte[] ảnh thì dùng gì?”**  
`ByteArrayResource` phù hợp với ảnh nhỏ đã có trong RAM. Với ảnh lớn và concurrency cao, cân nhắc stream repeatable từ file/object storage để tránh heap tăng mạnh.

**“Content-Type image/png có nghĩa mail client chắc chắn hiện PNG?”**  
Không. Bytes ảnh phải thực sự hợp lệ, MIME tree và CID khớp, mail client hỗ trợ hiển thị, không bị gateway/client chặn. Content-Type chỉ là một điều kiện.

**“JPEG/WebP/SVG có dùng addInline được không?”**  
Về MIME có thể gắn resource với content type tương ứng, nhưng khả năng hiển thị tùy client. PNG/JPEG thường dễ tương thích hơn; SVG có thể bị chặn vì bảo mật.

**“Tại sao ảnh inline lại xuất hiện trong phần attachments?”**  
Vì ảnh vẫn là một MIME body part. Một số clients liệt kê nó như file đính kèm dù HTML vẫn render đúng. Nếu HTML không hiện, kiểm tra Content-ID và MIME structure.

**“Có nên chuyển mọi ảnh sang data:image/png;base64 không?”**  
Không nên mặc định vì email clients hỗ trợ khác nhau, HTML tăng kích thước và có thể bị sanitizer loại bỏ. CID hoặc HTTPS thường có trade-off dễ kiểm soát hơn.

**“Base64 trong raw MIME và data URI có giống nhau không?”**  
Không. MIME Base64 là transfer encoding cho một part ảnh riêng; data URI nhúng bytes trực tiếp trong HTML attribute. CID dùng `Content-ID` để nối HTML tới part MIME.

**“CID có hoạt động khi người nhận offline?”**  
Nếu email và MIME parts đã được tải về máy, ảnh inline có thể hiển thị mà không cần tải từ CDN. Hành vi cụ thể vẫn phụ thuộc mail client và cách đồng bộ message.

**“HTTPS có luôn tốt hơn CID không?”**  
Không. HTTPS giảm size email và phù hợp asset public/CDN, nhưng client có thể chặn remote images, URL có thể hết hạn và có privacy concerns. CID tăng MIME size nhưng không cần request ảnh tới một server bên ngoài khi render.

**“Có nên dùng signed URL làm img src?”**  
Thận trọng. URL có thể hết hạn khiến email hỏng sau này; token trong URL có thể bị forward/cache. Với ảnh nhạy cảm, nên dùng link tới portal xác thực hoặc gửi thông tin theo chính sách cho phép.

**“Ảnh có thể bị chặn vì mail client không?”**  
Có. Một số clients chặn remote images hoặc hạn chế định dạng, CSS và MIME handling. Cần xem raw MIME và thử với client mục tiêu để phân biệt lỗi build message với chính sách render.

**“Logo không hiện trong dark mode có phải lỗi CID?”**  
Không nhất thiết. Ảnh có thể tồn tại nhưng thiếu tương phản với nền tối. Chọn asset/template phù hợp hoặc nền bao quanh có contrast đã kiểm tra.

**“Có nên chứa nội dung OTP hoặc điều kiện giao dịch chỉ trong ảnh?”**  
Không. Nếu ảnh bị chặn, người dùng sẽ không thấy thông tin quan trọng. Đặt nội dung cốt lõi trong HTML text và plain text, ảnh chỉ bổ trợ.

**“Nếu thay ảnh trên server sau khi gửi thì người nhận có thấy ảnh mới không?”**  
Với CID, bytes đã nằm trong email nên không đổi. Với HTTPS, URL có thể trả ảnh mới nhưng cache/proxy có thể giữ bản cũ. Cần chọn hành vi theo nghiệp vụ.

**“Dùng Content-ID có chống người nhận forward ảnh không?”**  
Không. Inline image là dữ liệu nằm trong email và có thể được lưu/forward. CID không phải cơ chế bảo vệ DRM hay quyền truy cập.

**“Nếu HTML template lấy logoPath từ user có nguy hiểm không?”**  
Có. File path tùy ý có thể dẫn đến path traversal/đọc file ngoài ý muốn. Dùng asset ID được kiểm tra tenant và một registry nguồn được phép.

**“Nếu auto-download mọi URL để convert sang CID thì sao?”**  
Cần chống SSRF, private IP/DNS rebinding, redirect, oversized download và MIME spoofing. Tốt hơn là dùng trusted object storage/catalog, không lấy ảnh từ URL tùy ý.

**“Làm sao biết Spring Mail đã nhúng ảnh thật?”**  
Kiểm tra raw MIME có Content-ID tương ứng, đúng Content-Type và bytes ảnh hợp lệ. Unit/integration test có thể parse message và kiểm tra part.

**“SMTP send trả success nhưng ảnh vẫn lỗi là bình thường?”**  
Có thể. SMTP chỉ chuyển message đã tạo; transport không đánh giá HTML `img[src]` có trỏ resource có thể xem được trên client hay không.

**“Cần test trên Gmail/Outlook hay chỉ SMTP sink?”**  
SMTP sink giúp kiểm tra MIME được tạo/gửi đúng. Để bảo đảm cách render trên clients mục tiêu, cần thêm thử nghiệm với mail clients thực tế hoặc dịch vụ render test được ủy quyền.

**“Có thể retry gửi khi hình không hiện ở client không?”**  
Không tự động. Nếu SMTP đã accepted, gửi lại có thể gây duplicate. Sửa template/asset mapping cho các delivery mới, còn xử lý email đã gửi theo nghiệp vụ và truyền thông cần thiết.

## 25. Checklist triển khai ảnh trong email HTML với Spring Mail

### Kiểm tra HTML template

1. Không có `src="C:\..."`, `src="/opt/app/..."`, `src="file:///..."` hoặc `src="./logo.png"` trong email gửi ra.
2. Với CID, mỗi `<img src="cid:...">` có một inline asset tương ứng.
3. Chuỗi CID trong HTML khớp với ID truyền vào `addInline`.
4. Không đặt dấu `<...>` vào giá trị `cid:` trong HTML.
5. Không nhầm filename của attachment với Content-ID.
6. Nếu dùng HTTPS, URL có scheme/domain đúng và được phép public theo policy.
7. Nếu ảnh có thể bị chặn, có `alt` và nội dung text quan trọng không phụ thuộc ảnh.
8. HTML có kích thước/markup phù hợp cho các mail clients mục tiêu.

### Kiểm tra MimeMessageHelper

9. Message được tạo từ `JavaMailSender.createMimeMessage()`.
10. Helper được tạo ở chế độ multipart khi có inline images.
11. `setText(plainText, htmlText)` được gọi để cung cấp plain-text fallback khi phù hợp.
12. `addInline` được gọi **sau** `setText`.
13. Dùng đúng content type như `image/png` hoặc `image/jpeg`.
14. Không chỉ gọi `addAttachment` rồi hy vọng HTML tham chiếu file bằng filename.
15. Gửi đúng `MimeMessage` đã được thêm inline parts, không tạo một message khác rồi send nhầm.
16. Khi có cả attachment và inline image, kiểm tra MIME tree mixed/related hợp lệ.

### Kiểm tra nguồn ảnh

17. Asset đóng gói trong JAR được đọc bằng `ClassPathResource`.
18. Không phụ thuộc `src/main/resources` tồn tại ở runtime.
19. Không gọi `ClassPathResource.getFile()` khi resource có thể nằm trong JAR.
20. Với file ngoài app, dùng đường dẫn được cấu hình rõ và `FileSystemResource`/`PathResource`.
21. File được phép đọc bởi user chạy JVM/container.
22. Ảnh có format thực đúng, không chỉ có extension `.png`.
23. Resource phải đọc lại được trong lúc MIME serialization.
24. Không dùng `InputStreamResource` single-use cho ảnh cần đọc nhiều lần.
25. Asset không bị xóa hoặc ghi đè trước khi gửi kết thúc.
26. Với nhiều replica, không đưa path trong một Pod vào job của Pod khác.

### Kiểm tra bảo mật và vòng đời

27. Không cho caller tự cung cấp filesystem path tùy ý.
28. Asset lookup được scope theo tenant/permission.
29. Nếu fetch ảnh từ URL, dùng trusted source/allowlist và chống SSRF.
30. Có max image bytes, tổng MIME bytes, MIME part count và concurrency limit.
31. Asset theo tenant/campaign có immutable version hoặc checksum khi cần retry.
32. Không log raw MIME, file bytes, signed URLs hoặc local secret path.
33. Thư mục staging có ACL, quota, cleanup và crash sweeper.
34. Có retention phù hợp cho asset khi outbox/retry chưa kết thúc.
35. Nội dung ảnh nhạy cảm chỉ được gửi nếu phù hợp policy; CID không thay authorization.

### Kiểm tra hành vi gửi và hiển thị

36. Raw HTML gửi đi chứa CID/HTTPS đúng, không còn local paths.
37. Raw MIME có `Content-ID`, `Content-Type` và bytes ảnh hợp lệ.
38. Plain-text alternative vẫn có thông tin cần thiết.
39. Thử với SMTP fake/sink, không gửi hàng loạt vào SMTP production để debug.
40. Test ít nhất một mail client thực tế của nhóm người dùng mục tiêu khi template quan trọng.
41. Chấp nhận rằng một số clients có thể chặn remote images hoặc giới hạn định dạng.
42. Nếu gửi đã accepted, không tự retry chỉ vì một client không hiển thị ảnh.
43. Có metric/alert cho asset not found, MIME preparation failures và staging quota.
44. Có runbook phân biệt lỗi local file path, MIME mismatch, backend resource và client rendering.

## 26. Sơ đồ quyết định: chọn cách đưa ảnh vào email

~~~text
                     Need image in an email?
                               |
                               v
                  Is image essential to content?
                     |                   |
                    Yes                 No
                     |                   |
                     v                   v
              Keep HTML/plain text   Consider whether
              meaning without image  image is necessary
                     |
                     v
               Is image sensitive?
                 |          |
                Yes         No
                 |          |
                 v          v
         Should it require    Is it a small,
         authenticated view?  stable brand asset?
           |          |           |           |
          Yes         No          Yes         No
           |          |           |           |
           v          v           v           v
        Secure     Consider CID  Use CID    Consider HTTPS
        portal     if sending    inline     for public/CDN
        link       bytes is      from a     images
                   authorized    resource      |
                      |           |            v
                      v           v       URL still reachable?
               Prepare durable   cid +      No auth cookie?
               resource snapshot addInline  Size/privacy OK?
                      |           |            |
                      +-----------+------------+
                                  |
                                  v
                       Build MIME + validate
                                  |
                                  v
                         Fake SMTP/MIME test
                                  |
                                  v
                          Send to recipient
~~~

### Tình huống lựa chọn thường gặp

| Nội dung | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| Logo công ty cố định trong welcome email | CID + `ClassPathResource` | Không phụ thuộc URL ngoài, đóng gói cùng app |
| Logo của tenant có trong object storage | CID + source repeatable/versioned | Lấy đúng asset được cấp quyền |
| Banner marketing kích thước lớn, public | HTTPS CDN | Giảm dung lượng từng message |
| File ảnh người dùng upload để gửi cho một recipient | CID hoặc attachment theo nhu cầu | Có payload durable, kiểm tra định dạng và quyền |
| Hình chứa thông tin cá nhân cần revoke | Secure portal link | Giữ quyền truy cập sau khi gửi |
| Ảnh chỉ tồn tại ở `/tmp` của request | Không dùng path trực tiếp | Stage durable hoặc xây MIME khi file còn sống |
| `<img src="file:///...">` trong template | Không dùng | Không thể hiện portable trên recipient |
| Logo trong `src/main/resources` sau đóng gói | `ClassPathResource` + CID | Đọc được bên trong JAR |

## 27. Tóm tắt luồng đúng và sai

### Cách sai

~~~text
Local file path
    |
    v
Path.toString()
    |
    v
HTML <img src="/opt/app/logo.png">
    |
    v
JavaMailSender.send
    |
    v
Recipient client cannot read server filesystem
    |
    v
Broken image
~~~

### Cách đúng với CID

~~~text
Local/classpath/authorized remote image
                 |
                 v
        Spring Resource / repeatable source
                 |
                 v
      MimeMessageHelper multipart mode
                 |
          +------+-------+
          |              |
          v              v
  HTML <img src=      addInline(
   "cid:brandLogo">      "brandLogo",
                        resource,
                        "image/png")
          |              |
          +------+-------+
                 |
                 v
         MimeMessage content
            - HTML part
            - image/png inline part
              Content-ID: <brandLogo>
                 |
                 v
        JavaMailSender.send
                 |
                 v
          Recipient client
            resolves cid
                 |
                 v
          Image can render
~~~

### Cách đúng với URL HTTPS

~~~text
Authorized public image asset
                 |
                 v
          HTTPS CDN endpoint
                 |
                 v
 HTML <img src="https://cdn.example.com/logo.png">
                 |
                 v
          JavaMailSender.send
                 |
                 v
 Mail client may request image via HTTPS
       (can be blocked/cached)
~~~

## 28. Kết luận

**Tham chiếu ảnh bằng đường dẫn file cục bộ** là lỗi xuất hiện khi ứng dụng đưa đường dẫn của **máy gửi email** vào HTML mà không cung cấp dữ liệu ảnh theo cơ chế mail client có thể hiểu. `C:\...`, `/opt/app/...`, `file:///...`, `classpath:...` hoặc đường dẫn tương đối chỉ có giá trị trong bối cảnh nhất định; chúng **không tự tạo một tài nguyên ảnh có thể truy cập cho người nhận**.

Trong Spring Framework Mail, cách sửa thông dụng cho logo/ảnh nhỏ là sử dụng `MimeMessageHelper` ở chế độ multipart, đặt HTML `<img src="cid:brandLogo">` và gọi `addInline("brandLogo", resource, "image/png")`. Với asset trong JAR, dùng `ClassPathResource`; với file trên disk, dùng `FileSystemResource`; với object storage, dùng nguồn có thể mở stream mới và version ổn định. Nếu chọn ảnh từ HTTPS, URL phải thực sự phù hợp cho mail client và chấp nhận khả năng ảnh từ xa bị chặn.

Trong production, đừng chỉ kiểm tra file “tồn tại” hay SMTP “send thành công”. Hãy phân biệt **đường dẫn backend**, **tham chiếu HTML**, **MIME Content-ID**, **vòng đời asset**, **quyền truy cập**, **khả năng tương thích mail client** và **giới hạn kích thước email**. Khi những ranh giới này rõ ràng, email có thể nhúng ảnh đúng cách mà không phụ thuộc filesystem máy gửi, không lộ đường dẫn nội bộ và vẫn có thể vận hành ổn định trong môi trường JAR, Docker, Kubernetes hoặc worker bất đồng bộ.
