# Kích thước ảnh inline và ảnh từ URL

Khi thiết kế email HTML bằng Spring Framework Mail, hình ảnh có thể được đưa vào email theo hai cách phổ biến: **nhúng trực tiếp dưới dạng inline resource** và **tham chiếu tới ảnh trên một URL bên ngoài**. Cả hai cách đều có thể hiển thị logo, biểu đồ hoặc hình minh họa trong phần nội dung, nhưng khác nhau về kích thước message, cách tải ảnh, quyền riêng tư, độ tin cậy và khả năng tương thích của email client.

Một lựa chọn tốt cần xem xét cả **kích thước hiển thị** lẫn **dung lượng file**. Ví dụ, logo được hiển thị rộng 160 pixel không nhất thiết chỉ cần file ảnh 160 pixel; màn hình mật độ điểm ảnh cao có thể cần ảnh nguồn lớn hơn. Ngược lại, đặt thuộc tính width trong HTML không làm giảm số byte của ảnh được gửi. Nếu ảnh nguồn quá lớn, message vẫn phải mang hoặc tải toàn bộ dữ liệu đó.

Với inline resource, ảnh nằm trong MIME message và HTML tham chiếu nó bằng **Content-ID**:

~~~html
<img src="cid:companyLogo" alt="Logo công ty">
~~~

Với ảnh từ URL, HTML trỏ tới một địa chỉ HTTPS bên ngoài:

~~~html
<img
  src="https://assets.example.org/email/company-logo.png"
  alt="Logo công ty">
~~~

Spring Mail hỗ trợ tạo MIME part inline bằng **MimeMessageHelper.addInline(...)**. Ảnh URL bên ngoài thường chỉ là một địa chỉ trong HTML; khi người nhận mở thư, email client quyết định có tải ảnh từ máy chủ đó hay không.

## 1. Hai cách đưa ảnh vào email

### 1.1. Inline resource bằng Content-ID

Một ảnh inline được đóng gói trong chính email dưới dạng MIME part. HTML tham chiếu tới part qua URL **cid:**.

~~~java
helper.setText(
        "<html><body>"
      + "<p>Chào mừng bạn!</p>"
      + "<img src=\"cid:companyLogo\" alt=\"Logo công ty\">"
      + "</body></html>",
        true
);

helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

Trong ví dụ, file **mail/logo.png** nằm trên classpath. **companyLogo** là Content-ID logic, phải khớp với **cid:companyLogo** trong HTML. Nên gọi **setText(...) trước addInline(...)** theo khuyến nghị của Spring Mail để tăng tính tương thích khi các email client diễn giải các MIME part.

Cấu trúc MIME về mặt khái niệm:

~~~text
multipart/related
├── text/html
│   └── <img src="cid:companyLogo">
└── image/png
    ├── Content-ID: <companyLogo>
    └── Dữ liệu ảnh
~~~

Vì dữ liệu ảnh được gửi cùng message, người nhận không cần tải ảnh từ một máy chủ web bên ngoài để lấy byte ảnh đó. Tuy nhiên, client vẫn có thể ẩn hình ảnh theo cài đặt hoặc chính sách hiển thị của nó.

### 1.2. Ảnh từ URL bên ngoài

Nếu ảnh đã được lưu trên CDN hoặc web server, HTML có thể tham chiếu trực tiếp:

~~~java
String html = """
        <html>
          <body>
            <p>Chào mừng bạn!</p>
            <img
              src="https://assets.example.org/email/company-logo.png"
              alt="Logo công ty"
              width="160"
              height="48">
          </body>
        </html>
        """;

helper.setText(html, true);
~~~

Trong trường hợp này, không có MIME part ảnh tương ứng được thêm bằng **addInline**. Message chỉ chứa chuỗi HTML có URL. Khi người nhận mở email, client có thể tải ảnh qua HTTPS nếu được phép.

**Việc gửi email không đồng nghĩa máy chủ Spring tự tải URL ảnh.** Nếu ứng dụng chỉ đưa URL vào thuộc tính **src**, email client của người nhận là thành phần thường thực hiện request lấy ảnh khi hiển thị thư.

### 1.3. So sánh nhanh

| Tiêu chí | Inline resource (CID) | Ảnh URL bên ngoài |
| --- | --- | --- |
| Vị trí byte ảnh | Nằm trong MIME message | Nằm trên web server/CDN |
| HTML tham chiếu | cid:contentId | URL tuyệt đối, thường là HTTPS |
| Dung lượng email | Tăng theo ảnh được nhúng và MIME encoding | Thường nhỏ hơn vì không mang byte ảnh |
| Cần mạng khi mở thư để lấy ảnh | Không cần truy cập image host bên ngoài | Thường cần truy cập image host |
| Quyền riêng tư | Không tạo request tải ảnh tới host ngoài chỉ để lấy ảnh CID | Request tải ảnh có thể tiết lộ metadata truy cập |
| Cập nhật ảnh | Mỗi email mang bản ảnh tại thời điểm gửi | Có thể thay ảnh tại URL cho lần tải sau |
| URL hết hạn | Không phụ thuộc URL ảnh ngoài | Có thể mất ảnh nếu URL hết hạn hoặc bị đổi |
| Chặn ảnh từ xa | Không áp dụng theo cùng cách tải ảnh HTTP, nhưng client vẫn có thể ẩn nội dung | Client có thể chặn tải ảnh từ xa |
| Khả năng kiểm soát phiên bản | Nội dung ảnh gắn với message đã gửi | Nội dung có thể thay đổi theo tài nguyên ở URL |
| Phù hợp | Logo quan trọng, ảnh cần đi cùng nội dung cụ thể | Ảnh lớn, ảnh thay đổi độc lập, nội dung marketing cần cập nhật |

Không có lựa chọn nào tốt nhất cho mọi email. Hãy chọn dựa trên việc ảnh có cần đi cùng bản nội dung tại thời điểm gửi hay không, kích thước file, yêu cầu riêng tư và khả năng phục vụ ảnh từ xa.

## 2. Kích thước ảnh có hai khái niệm khác nhau

Khi nói “ảnh rộng 300 pixel”, cần xác định đó là **kích thước pixel của file nguồn** hay **kích thước hiển thị trong email**.

### 2.1. Kích thước pixel của ảnh nguồn

Đây là số pixel thực sự được lưu trong file. Ví dụ:

- 320 × 100 px.
- 640 × 200 px.
- 1200 × 400 px.

Kích thước pixel ảnh hưởng độ chi tiết có thể hiển thị và thường có quan hệ với dung lượng file, nhưng không quyết định dung lượng một cách tuyệt đối. Một ảnh chụp 640 × 200 có thể nặng hơn logo PNG 1200 × 400 nếu ảnh chụp có nhiều chi tiết và cách nén khác.

### 2.2. Kích thước hiển thị trong HTML

HTML có thể yêu cầu hiển thị ảnh ở kích thước khác với kích thước pixel nguồn:

~~~html
<img
  src="cid:companyLogo"
  alt="Logo công ty"
  width="160"
  height="50">
~~~

Nếu file nguồn là 640 × 200 px nhưng hiển thị ở 160 × 50 CSS pixel, client sẽ thu nhỏ ảnh khi render. **Dung lượng MIME của ảnh vẫn dựa trên file nguồn 640 × 200**, không tự giảm xuống theo thuộc tính width/height.

Tương tự, nếu ảnh nguồn chỉ 80 × 25 px nhưng được phóng lên 320 × 100 CSS pixel, ảnh có thể bị mờ hoặc vỡ nét. Thuộc tính HTML không tạo thêm chi tiết cho ảnh.

### 2.3. Dung lượng file là số byte

Dung lượng file được tính bằng byte, KB hoặc MB. Nó ảnh hưởng:

- Kích thước email phải truyền qua SMTP.
- Thời gian gửi và nhận.
- Bộ nhớ cần dùng khi tạo message.
- Thời gian tải ảnh URL trên mạng của người nhận.
- Khả năng vượt giới hạn message size của provider.

**Pixel và byte là hai chỉ số khác nhau.** Hai ảnh có cùng chiều rộng/cao có thể có dung lượng rất khác nhau do định dạng, mức nén, màu sắc, độ phức tạp và metadata.

## 3. Chọn kích thước hiển thị phù hợp

Kích thước hiển thị nên dựa trên bố cục email, không dựa đơn thuần vào kích thước file gốc.

Một số kích thước tham khảo:

| Loại ảnh | Kích thước hiển thị minh họa | Gợi ý |
| --- | --- | --- |
| Logo header | Rộng 120–200 px | Giữ tỷ lệ, tránh chiếm quá nhiều chiều cao |
| Icon nhỏ | 24–48 px | Có thể dùng ảnh raster nhỏ hoặc ký tự/icon được hỗ trợ |
| Ảnh minh họa trong nội dung | Rộng 280–600 px | Tùy chiều rộng cột email |
| Banner | Rộng theo vùng nội dung, thường 560–600 px trong layout email phổ biến | Kiểm tra trên mobile và desktop |
| Biểu đồ | Theo kích thước vùng đọc, thường khoảng 400–600 px | Chữ và nhãn phải đọc được khi thu nhỏ |

Đây là phạm vi thiết kế tham khảo, không phải giới hạn kỹ thuật của Spring Mail hay tiêu chuẩn bắt buộc. Email có thể có bố cục rộng/hẹp khác nhau, và client hiển thị ở nhiều viewport.

### 3.1. Giữ tỷ lệ ảnh

Nếu ảnh nguồn có tỷ lệ 4:1, hãy giữ tỷ lệ khi thu nhỏ. Ví dụ 640 × 160 hiển thị ở 160 × 40.

~~~html
<img
  src="cid:companyLogo"
  alt="Logo công ty"
  width="160"
  height="40"
  style="display:block;max-width:100%;height:auto;">
~~~

**height:auto** giúp trình duyệt/email client có hỗ trợ giữ tỷ lệ khi chiều rộng co lại. Thuộc tính width và height cung cấp kích thước dự kiến, giúp bố cục ổn định hơn trước khi ảnh tải.

Không đặt width và height không tương ứng với tỷ lệ ảnh nếu không chủ đích cắt hoặc kéo giãn. Ảnh bị kéo giãn sẽ méo logo, khuôn mặt hoặc biểu đồ.

### 3.2. Responsive cho màn hình nhỏ

Email có thể được mở trên điện thoại với vùng hiển thị hẹp. Một mẫu cơ bản:

~~~html
<img
  src="https://assets.example.org/email/banner.jpg"
  alt="Ưu đãi tháng này"
  width="600"
  style="display:block;width:100%;max-width:600px;height:auto;border:0;">
~~~

Trong nhiều email client, inline CSS và thuộc tính width có thể được hỗ trợ tốt hơn các kỹ thuật CSS web mới. Dù vậy, hỗ trợ không hoàn toàn đồng nhất. Hãy dùng layout email đơn giản, kiểm tra trên client mục tiêu và không phụ thuộc vào một thuộc tính CSS duy nhất.

Với email cần tương thích rộng, bố cục dạng bảng (table-based layout) vẫn thường được dùng cho vùng nội dung và căn chỉnh ảnh. Không nên mặc định mọi client đều hỗ trợ đầy đủ Flexbox, Grid, object-fit hoặc media query như trình duyệt hiện đại.

### 3.3. Cung cấp alt text

Luôn cân nhắc thuộc tính **alt**:

~~~html
<img
  src="cid:companyLogo"
  alt="Logo công ty ABC"
  width="160"
  height="48">
~~~

Alt text có ích khi ảnh bị ẩn, không tải được hoặc người nhận dùng công nghệ hỗ trợ. Nếu ảnh chỉ mang tính trang trí và không thêm thông tin, có thể dùng **alt=""** để tránh đọc nội dung thừa. Không đưa thông tin quan trọng duy nhất vào ảnh mà không có phần chữ tương ứng.

## 4. Ảnh nguồn cho màn hình mật độ điểm ảnh cao

Một số màn hình có mật độ pixel cao (HiDPI/Retina). Ảnh có đúng số pixel bằng kích thước CSS hiển thị đôi khi trông mềm hoặc thiếu sắc nét trên những màn hình này.

Một cách phổ biến là chuẩn bị ảnh nguồn lớn gấp khoảng **2 lần kích thước hiển thị**:

| Kích thước hiển thị | Ảnh nguồn gợi ý cho màn hình 2x |
| --- | --- |
| 160 × 40 CSS px | 320 × 80 px |
| 300 × 150 CSS px | 600 × 300 px |
| 600 × 200 CSS px | 1200 × 400 px |

Ví dụ logo hiển thị rộng 160 px có thể dùng file nguồn rộng 320 px:

~~~html
<img
  src="cid:companyLogo"
  alt="Logo công ty"
  width="160"
  height="40">
~~~

Nếu dùng ảnh CID, file 320 × 80 được nhúng vào MIME message. Nếu dùng URL, client tải file 320 × 80 từ server rồi hiển thị ở 160 × 40 CSS pixel.

### 4.1. Ảnh 2x không phải lúc nào cũng cần thiết

Ảnh nguồn lớn hơn có thể tăng dung lượng đáng kể. Với logo đơn giản hoặc biểu đồ có thể hiển thị rõ ở 1x, không cần tự động nhân kích thước mọi ảnh.

Hãy cân bằng:

- Độ sắc nét ở màn hình mật độ cao.
- Kích thước byte.
- Chiều rộng thực tế của vùng nội dung.
- Khả năng co giãn trên mobile.
- Hạn mức email và thời gian tải.

Không nên gửi ảnh 2400 px chỉ để hiển thị ở 120 px nếu mức chi tiết đó không có giá trị.

### 4.2. srcset không phải giải pháp đồng nhất cho email

HTML web có thể dùng **srcset** để trình duyệt chọn ảnh theo mật độ pixel hoặc kích thước viewport. Hỗ trợ srcset trong email client không đồng nhất. Nếu cần tương thích rộng, chọn một ảnh nguồn có kích thước hợp lý và khai báo kích thước hiển thị rõ ràng, thay vì phụ thuộc hoàn toàn vào cơ chế chọn ảnh nâng cao.

## 5. Dung lượng ảnh và tác động tới kích thước email

Với ảnh inline, byte ảnh được đóng gói vào MIME message. Dữ liệu nhị phân thường được mã hóa bằng **Base64** khi truyền trong email.

Base64 biến mỗi nhóm 3 byte thành 4 ký tự, nên kích thước biểu diễn thường xấp xỉ **4/3 kích thước dữ liệu gốc**, chưa tính xuống dòng, MIME header và boundary.

Ví dụ ước lượng:

| Dung lượng ảnh gốc | Phần Base64 xấp xỉ, chưa tính overhead |
| --- | --- |
| 30 KB | 40 KB |
| 75 KB | 100 KB |
| 150 KB | 200 KB |
| 300 KB | 400 KB |
| 1 MB | Khoảng 1,33 MB |

Đây chỉ là phép ước lượng để lập kế hoạch. Kích thước thực của toàn email còn gồm body, header, các attachment khác và chi tiết mã hóa của thư viện.

### 5.1. Nhiều ảnh inline cộng dồn

Nếu một email có 5 ảnh, mỗi ảnh 200 KB, tổng byte ảnh gốc khoảng 1 MB. Phần Base64 có thể vượt khoảng 1,33 MB trước khi tính phần MIME còn lại.

Với một chiến dịch gửi hàng nghìn email, việc lặp lại cùng một ảnh logo trong từng message làm tăng tổng lưu lượng gửi. Tuy nhiên, dùng URL ngoài sẽ chuyển phần tải ảnh sang thời điểm người nhận mở thư và phụ thuộc image host. Quyết định cần xét cả tải phía người gửi lẫn phía người nhận.

### 5.2. Giới hạn message size

SMTP provider thường đặt giới hạn kích thước message. Giới hạn có thể được áp dụng trên toàn bộ message sau MIME encoding, không chỉ tổng dung lượng file gốc.

Vì vậy, nếu provider cho phép tối đa một mức message cụ thể, không nên dùng toàn bộ hạn mức đó cho riêng ảnh. Cần dành chỗ cho:

- Body plain text và HTML.
- Các MIME header, boundary.
- Base64 overhead.
- PDF/CSV attachment.
- Những trường hợp người nhận hoặc hệ thống chuyển tiếp có giới hạn thấp hơn.

Hãy kiểm tra tài liệu của SMTP provider và giới hạn của hệ thống nhận. Không có một con số duy nhất áp dụng cho mọi dịch vụ email.

### 5.3. Ảnh URL không làm tăng MIME message theo kích thước ảnh

Nếu HTML chỉ chứa:

~~~html
<img src="https://assets.example.org/email/banner.jpg" alt="Banner">
~~~

thì message không mang byte ảnh banner. Nó chỉ mang chuỗi URL và các markup HTML. Dung lượng email nhỏ hơn, nhưng người nhận phải tải ảnh qua mạng nếu client cho phép.

Đổi lại, ảnh có thể không hiển thị khi client chặn remote content, người nhận offline, server ảnh lỗi hoặc URL không còn hợp lệ.

## 6. Tối ưu ảnh trước khi nhúng hoặc xuất bản lên URL

Tối ưu ảnh thường hiệu quả hơn việc chỉ giảm width/height trong HTML.

### 6.1. Resize theo kích thước thực sự cần hiển thị

Nếu banner chỉ hiển thị rộng 600 CSS pixel, hãy cân nhắc ảnh nguồn khoảng 600 px hoặc 1200 px nếu cần 2x. Không cần dùng ảnh 4000 px chỉ vì file gốc từ máy ảnh có độ phân giải lớn.

Resize giảm số pixel thật, thường giảm cả dung lượng và chi phí xử lý. Đặt width="600" trong HTML mà không resize file không làm giảm byte cần tải.

### 6.2. Chọn định dạng phù hợp

| Định dạng | Trường hợp thường phù hợp | Lưu ý email |
| --- | --- | --- |
| **PNG** | Logo, icon, biểu đồ, hình có nền trong suốt hoặc cạnh sắc | Thường được hỗ trợ rộng, nhưng ảnh chụp có thể nặng |
| **JPEG** | Ảnh chụp và hình nhiều màu liên tục | Có thể giảm dung lượng bằng chất lượng nén phù hợp; không hỗ trợ nền trong suốt |
| **GIF** | Hình đơn giản hoặc animation ngắn | Hỗ trợ animation khác nhau; một số client chỉ hiển thị frame đầu |
| **SVG** | Đồ họa vector cần sắc nét | Hỗ trợ và chính sách bảo mật khác nhau; không nên giả định mọi client hiển thị |
| **WebP** | Ảnh web cần nén hiệu quả | Hỗ trợ trong email client không đồng nhất |

Với email cần tương thích rộng, **PNG cho logo/đồ họa trong suốt và JPEG cho ảnh chụp** thường là lựa chọn thực dụng. Nếu sử dụng SVG, WebP hoặc GIF animation, hãy thử trên những email client mà người nhận thực sự dùng và có phương án thay thế.

### 6.3. Chọn mức nén hợp lý

JPEG cho phép điều chỉnh chất lượng nén. Nén quá mạnh có thể tạo artefact, làm chữ nhỏ hoặc logo bị nhòe. Nén quá nhẹ làm file lớn mà khác biệt hình ảnh không đáng kể.

Hãy kiểm tra ảnh ở kích thước hiển thị cuối cùng, không chỉ xem thumbnail. Chữ trong biểu đồ, mã QR và chi tiết nhỏ cần đủ rõ để đọc hoặc quét.

### 6.4. Loại metadata không cần thiết

Ảnh chụp có thể chứa metadata như EXIF, thông tin thiết bị hoặc vị trí tùy nguồn. Nếu không cần, hãy loại bỏ metadata trước khi gửi hoặc xuất bản. Điều này có thể giảm dung lượng và tránh chia sẻ thông tin không cần thiết.

Không phải mọi file đều có metadata nhạy cảm, nhưng hệ thống xử lý ảnh nên có chính sách rõ ràng cho dữ liệu tải lên.

### 6.5. Tối ưu ảnh không nên làm hỏng nội dung

Đối với logo có chữ, biểu đồ và mã QR, giảm dung lượng không được làm mất khả năng đọc. Nếu hình ảnh chứa dữ liệu nghiệp vụ, cần kiểm tra nội dung sau resize/nén trước khi gửi.

## 7. Dùng inline resource trong Spring Mail

Khi chọn CID, Spring Mail tạo MIME part từ một Resource hoặc InputStreamSource.

Ví dụ logo classpath:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);

helper.setTo("user@example.net");
helper.setSubject("Thông báo");

String html = """
        <html>
          <body>
            <h1>Chào mừng</h1>
            <img
              src="cid:companyLogo"
              alt="Logo công ty"
              width="160"
              height="48"
              style="display:block;max-width:100%;height:auto;border:0;">
          </body>
        </html>
        """;

helper.setText(html, true);

helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);

mailSender.send(message);
~~~

### 7.1. Ảnh từ byte[] bằng ByteArrayResource

Nếu ứng dụng tạo ảnh trong bộ nhớ:

~~~java
byte[] optimizedPng = imageService.createOptimizedLogo();

helper.setText(
        "<img src=\"cid:dynamicLogo\" alt=\"Logo\" width=\"160\">",
        true
);

helper.addInline(
        "dynamicLogo",
        new ByteArrayResource(optimizedPng),
        "image/png"
);
~~~

ByteArrayResource phù hợp khi ảnh đã có dưới dạng byte[]. Toàn bộ byte array nằm trong heap, nên cần giới hạn kích thước và số lượng email xử lý đồng thời.

### 7.2. Ảnh từ file trên filesystem

Nếu ảnh đã được tạo trên đĩa:

~~~java
helper.addInline(
        "reportChart",
        new FileSystemResource(chartPath),
        "image/png"
);
~~~

Nguồn file có thể được đọc lại bởi thư viện khi dựng message. Cần bảo đảm file tồn tại, đúng loại và còn truy cập được trong suốt quá trình gửi.

### 7.3. Kết hợp HTML, plain text và inline image

Nếu cần hỗ trợ client không hiển thị HTML:

~~~java
helper.setText(
        "Báo cáo đã sẵn sàng. Logo và biểu đồ nằm trong bản HTML.",
        """
        <html>
          <body>
            <h2>Báo cáo tháng</h2>
            <img src="cid:reportChart"
                 alt="Biểu đồ doanh thu"
                 width="560"
                 style="max-width:100%;height:auto;">
          </body>
        </html>
        """
);

helper.addInline(
        "reportChart",
        new ByteArrayResource(chartBytes),
        "image/png"
);
~~~

**setText(plainText, htmlText)** cung cấp hai biểu diễn của cùng nội dung. Ảnh chỉ được tham chiếu trong bản HTML; bản plain text vẫn cần nói rõ thông tin quan trọng.

## 8. Dùng ảnh URL bên ngoài trong HTML email

Khi chọn URL, ứng dụng không gọi **addInline**. Nó đưa URL tuyệt đối vào **src**.

~~~java
String html = """
        <html>
          <body>
            <h1>Thông báo mới</h1>
            <img
              src="https://cdn.example.org/email/banner-2026.jpg"
              alt="Thông báo tháng 11"
              width="600"
              style="display:block;width:100%;max-width:600px;height:auto;border:0;">
          </body>
        </html>
        """;

helper.setText(html, true);
~~~

Không cần tạo MIME part ảnh cho URL này. Email chỉ chứa địa chỉ và markup. Khi mở email, client có thể gửi HTTP request tới CDN để lấy ảnh.

### 8.1. URL phải là địa chỉ tuyệt đối

Không dùng đường dẫn tương đối:

~~~html
<img src="/images/logo.png" alt="Logo">
~~~

Email client không có một website gốc của ứng dụng Spring để giải quyết **/images/logo.png**. Dùng URL đầy đủ:

~~~html
<img
  src="https://assets.example.org/images/logo.png"
  alt="Logo">
~~~

### 8.2. Ưu tiên HTTPS

Dùng HTTPS để bảo vệ kết nối tải ảnh và tránh mixed content hoặc chính sách chặn HTTP không mã hóa. Chứng chỉ TLS của host ảnh phải hợp lệ và URL phải có thể truy cập từ mạng của người nhận.

Một URL chỉ truy cập được trong mạng nội bộ, qua VPN hoặc từ máy chủ ứng dụng có thể không truy cập được từ email client bên ngoài.

### 8.3. Không yêu cầu cookie hoặc đăng nhập của ứng dụng

Ảnh email nên được host tại địa chỉ có thể truy cập theo chính sách mà email client sử dụng. Một URL yêu cầu session cookie của website, đăng nhập qua SSO hoặc header Authorization riêng có thể không tải được trong email client.

Không đưa password, bearer token hoặc secret vào query string của URL ảnh. URL có thể xuất hiện trong HTML của email, log, proxy và hệ thống phân tích.

Nếu ảnh phải bảo vệ theo người dùng, cân nhắc cơ chế tải có xác thực được thiết kế riêng hoặc dùng inline resource phù hợp. Signed URL có thời hạn có thể hoạt động, nhưng email được mở sau khi URL hết hạn sẽ không tải được ảnh.

### 8.4. URL phải ổn định đủ lâu

Một email có thể được mở lại nhiều ngày hoặc nhiều tháng sau khi gửi. Nếu ảnh dùng URL tạm thời, token hết hạn hoặc đường dẫn thay đổi, ảnh có thể biến mất khi người nhận mở lại.

Đối với nội dung giao dịch, hãy xác định ảnh có cần giữ nguyên theo thời điểm gửi hay không. Nếu cần tính nhất quán, CID có thể phù hợp hơn vì bản ảnh nằm trong message. Nếu dùng URL, hãy có chính sách versioning và retention.

## 9. Quyền riêng tư khi dùng ảnh URL

Khi email client tải ảnh từ máy chủ bên ngoài, server ảnh có thể nhận được metadata của request, tùy cách client và proxy hoạt động:

- Thời điểm tải.
- Địa chỉ IP của client hoặc proxy.
- User-Agent hoặc metadata tương tự, nếu được gửi.
- Đường dẫn và query string của URL.
- Một số thông tin về cách tài nguyên được yêu cầu.

Vì vậy, ảnh từ URL có thể được dùng để suy luận thời điểm mở email hoặc theo dõi tương tác. Đây là lý do một số client chặn remote images, hiển thị cảnh báo hoặc tải ảnh qua proxy/cache của chính họ.

### 9.1. Image proxy và cache

Một số email provider tải ảnh qua máy chủ proxy của họ, cache kết quả rồi phục vụ lại cho người dùng. Điều này có thể:

- Che IP thật của người nhận khỏi host ảnh.
- Làm request xảy ra ở thời điểm khác với lúc người dùng thực sự xem.
- Khiến cùng một URL được cache và không phản ánh ảnh mới nhất.
- Làm các cơ chế đo lường lượt mở dựa trên ảnh kém chính xác.

Không nên giả định mỗi lần người dùng mở email sẽ tạo một request trực tiếp tới origin server. Hành vi phụ thuộc provider, client, cài đặt và chính sách quyền riêng tư.

### 9.2. Tracking pixel và trách nhiệm sử dụng

Một ảnh 1×1 pixel từ URL có thể được dùng để ghi nhận request khi client tải ảnh. Đây là một kỹ thuật theo dõi, không phải yêu cầu kỹ thuật để hiển thị nội dung email.

Nếu hệ thống sử dụng tracking, cần xem xét thông báo minh bạch, consent và quy định quyền riêng tư áp dụng cho người nhận. Không nên coi request tải ảnh là bằng chứng chắc chắn người dùng đã đọc nội dung, vì proxy, cache và chặn ảnh có thể làm sai lệch kết quả.

### 9.3. CID không phải giải pháp đo lường mở thư

Ảnh CID được đóng gói trong email và không cần request tới image host ngoài để lấy dữ liệu. Vì vậy, nó không tạo cùng loại tín hiệu HTTP như ảnh URL. Tuy nhiên, việc dùng CID cũng không cung cấp bằng chứng người nhận đã mở hoặc đọc email.

## 10. Khả năng ảnh URL bị chặn

Nhiều email client có thể không tải ảnh từ xa cho tới khi người nhận cho phép. Một số client tải qua proxy, một số hiển thị cảnh báo hoặc tắt ảnh theo cài đặt quản trị.

Những nguyên nhân phổ biến:

- Client mặc định chặn remote images để bảo vệ quyền riêng tư.
- Người nhận chọn không tải hình ảnh bên ngoài.
- URL trả về lỗi 403, 404 hoặc 5xx.
- Host ảnh yêu cầu đăng nhập hoặc cookie.
- Chứng chỉ HTTPS không hợp lệ.
- Firewall hoặc proxy của tổ chức chặn domain.
- URL hết hạn hoặc ảnh bị xóa.
- Ảnh có định dạng mà client không hỗ trợ.

Vì vậy, ảnh URL cần có **alt text** và nội dung email không nên phụ thuộc hoàn toàn vào hình ảnh.

### 10.1. Alt text cho ảnh remote

~~~html
<img
  src="https://cdn.example.org/email/sale-banner.jpg"
  alt="Chương trình ưu đãi tháng 11: giảm giá cho đơn hàng đủ điều kiện"
  width="600">
~~~

Nếu ảnh không tải, client có thể hiển thị alt text hoặc dùng nó cho công nghệ hỗ trợ. Alt text nên truyền đạt ý nghĩa của ảnh, không chỉ ghi “image” hoặc “picture”.

### 10.2. Không đặt toàn bộ nội dung vào banner

Nếu banner chứa duy nhất thời hạn ưu đãi, mã giảm giá hoặc hướng dẫn quan trọng, người nhận có thể mất thông tin khi ảnh bị chặn. Hãy lặp lại nội dung thiết yếu ở dạng text trong body.

## 11. Chọn giữa CID và URL theo loại email

| Tình huống | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Logo thương hiệu nhỏ trong email giao dịch | CID hoặc URL ổn định | CID giữ bản ảnh trong message; URL giảm dung lượng |
| Biểu đồ được tạo riêng cho từng báo cáo | CID | Ảnh gắn với dữ liệu và thời điểm tạo báo cáo |
| Banner marketing lớn | URL/CDN | Giảm kích thước message và có thể cập nhật tài nguyên |
| Ảnh phải hiển thị ngay cả khi không truy cập host ngoài | CID | Byte ảnh nằm trong email |
| Ảnh thay đổi thường xuyên | URL có version/cache policy | Có thể cập nhật tài nguyên ở server |
| Ảnh có thông tin nhạy cảm hoặc riêng theo người nhận | Cân nhắc CID hoặc kênh tải bảo vệ | Tránh URL công khai làm lộ dữ liệu |
| Email có nhiều ảnh độ phân giải lớn | URL hoặc link tải | Hạn chế message size |
| Email cần lưu nguyên hình ảnh theo thời điểm gửi | CID hoặc URL có version bất biến | Tránh ảnh thay đổi ngoài ý muốn |

Bảng chỉ là hướng lựa chọn. Một email có thể kết hợp hai cách: logo nhỏ dùng CID, còn ảnh minh họa lớn dùng URL. Khi kết hợp, cần cân nhắc rằng một số ảnh có thể hiển thị trong khi ảnh khác bị chặn.

## 12. Kết hợp ảnh CID và ảnh URL trong cùng HTML

Không bắt buộc một email chỉ dùng một phương pháp. Ví dụ:

- Logo công ty là tài nguyên nhỏ, cần gắn với bản email đã gửi: dùng CID.
- Banner chiến dịch lớn được quản lý trên CDN: dùng URL HTTPS.

~~~java
String html = """
        <html>
          <body>
            <img
              src="cid:companyLogo"
              alt="Logo công ty"
              width="150">
            <h1>Thông báo tháng 11</h1>
            <img
              src="https://cdn.example.org/campaign/november-banner.jpg"
              alt="Banner chương trình tháng 11"
              width="600"
              style="max-width:100%;height:auto;">
            <p>Chi tiết chương trình được trình bày bên dưới.</p>
          </body>
        </html>
        """;

helper.setText(html, true);

helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

Trong message, logo được đóng gói thành MIME part. Banner chỉ có URL trong HTML. Khi client mở thư, nó có thể hiển thị logo CID nhưng chặn banner bên ngoài.

Vì vậy, nội dung text phải vẫn đầy đủ và không phụ thuộc vào việc cả hai ảnh đều được tải.

## 13. Nếu muốn chuyển ảnh URL thành inline resource

Đôi khi hệ thống lưu ảnh ở object storage hoặc CDN, nhưng email cần mang theo bản ảnh tại thời điểm gửi. Khi đó ứng dụng có thể **tải byte ảnh từ nguồn được phép**, rồi thêm bằng addInline hoặc addAttachment.

Luồng khái niệm:

~~~text
Image URL đã được kiểm soát
       |
       v
HTTP client / storage SDK
       |
       v
byte[] ảnh
       |
       v
ByteArrayResource
       |
       v
MimeMessageHelper.addInline(...)
       |
       v
CID part trong email
~~~

Ví dụ phần MIME sau khi tải:

~~~java
byte[] imageBytes = imageClient.download(approvedImageUri);

helper.setText(
        "<img src=\"cid:productImage\" alt=\"Sản phẩm\">",
        true
);

helper.addInline(
        "productImage",
        new ByteArrayResource(imageBytes),
        "image/jpeg"
);
~~~

**imageClient.download(...)** là API minh họa do ứng dụng định nghĩa. Nó phải trả byte ảnh hợp lệ, có timeout và giới hạn kích thước. **approvedImageUri** phải đến từ nguồn đã được kiểm soát, không phải một URL tùy ý do người dùng gửi mà chưa kiểm tra.

### 13.1. Kiểm tra URL để tránh SSRF

Nếu server Spring chủ động tải một URL do người dùng cung cấp, đây không còn là việc email client tải remote image. Backend đang thực hiện HTTP request thay người dùng. Cần phòng ngừa **Server-Side Request Forgery (SSRF)**:

- Chỉ cho phép domain hoặc storage bucket đã được cấu hình.
- Kiểm tra scheme, host, port và địa chỉ IP sau phân giải DNS.
- Chặn loopback, link-local, private network và endpoint metadata không được phép.
- Kiểm soát redirect; không cho redirect sang host bị cấm.
- Đặt connect/read timeout.
- Giới hạn kích thước response trước khi materialize vào byte[].
- Kiểm tra MIME type và định dạng file thực tế.
- Không gửi cookie, token hoặc header nội bộ tới host không tin cậy.

Nếu mục tiêu chỉ là để email client tải ảnh từ URL công khai, thường không cần server Spring tải ảnh đó về trước.

### 13.2. Xác minh Content-Type và dữ liệu thực

Không chỉ tin header Content-Type do server ngoài trả về. Một endpoint có thể trả HTML lỗi với status hoặc media type bất thường, nhưng ứng dụng lại gắn dữ liệu đó thành image/jpeg.

Hãy kiểm tra HTTP status, giới hạn kích thước và loại dữ liệu thực tế trước khi nhúng. Nếu tải thất bại, cần quyết định render email không có ảnh, dùng ảnh dự phòng hoặc đánh dấu tác vụ lỗi tùy yêu cầu nghiệp vụ.

## 14. Tránh nhúng ảnh bằng data URL Base64 trong HTML

Một số HTML cho phép biểu diễn ảnh như:

~~~html
<img src="data:image/png;base64,iVBORw0KGgo...">
~~~

Đây là **data URL**. Nó khác với CID:

- Data URL chứa dữ liệu ảnh trực tiếp trong thuộc tính HTML.
- CID tham chiếu một MIME part riêng trong message.
- URL HTTPS tham chiếu một tài nguyên bên ngoài.

Email client không hỗ trợ data URL đồng nhất; nhiều client có thể loại bỏ hoặc chặn kiểu nhúng này. Nó cũng làm phần HTML dài và tăng dung lượng message.

Với Spring Framework Mail, nếu muốn nhúng ảnh theo cách có cấu trúc MIME, nên dùng **MimeMessageHelper.addInline(...)** thay vì nhét Base64 vào HTML. Nếu muốn ảnh bên ngoài, dùng URL HTTPS.

## 15. Caching và versioning ảnh URL

Ảnh URL có thể được cache bởi browser proxy, email provider hoặc CDN. Điều này giúp giảm tải và tăng tốc, nhưng có nghĩa ảnh mới không nhất thiết xuất hiện ngay khi bạn thay file tại cùng URL.

### 15.1. Dùng URL versioned

Ví dụ:

~~~text
https://cdn.example.org/email/logo-v3.png
~~~

Khi logo thay đổi, xuất bản một URL version mới thay vì thay nội dung dưới cùng URL nếu muốn tránh cache cũ. Cách này giúp message mới tham chiếu tài nguyên mới, còn message cũ vẫn có thể tham chiếu bản cũ nếu server tiếp tục giữ URL đó.

### 15.2. Cache-Control

CDN có thể cấu hình header cache theo vòng đời tài nguyên. Với ảnh chiến dịch thay đổi thường xuyên, cache cần được cân bằng giữa tốc độ và thời gian cập nhật. Với logo ổn định, cache dài có thể phù hợp.

Email client có thể có proxy/cache riêng và không nhất thiết tuân theo toàn bộ header như browser thông thường. Hãy thử nghiệm trên các provider mục tiêu.

### 15.3. Không xóa ảnh ngay sau chiến dịch nếu email còn được mở lại

Email cũ có thể được người nhận mở sau khi chiến dịch kết thúc. Nếu URL ảnh bị xóa, banner có thể không còn hiển thị. Cần xác định thời gian giữ tài nguyên ít nhất tương ứng với thời gian email cần được xem lại.

Nếu cần nội dung bất biến, dùng CID hoặc URL versioned được lưu giữ theo chính sách.

## 16. Ảnh URL và signed URL có thời hạn

Một signed URL thường chứa token hoặc chữ ký trong query string và chỉ có hiệu lực trong một khoảng thời gian. Điều này hữu ích để giới hạn quyền tải, nhưng có một vấn đề với email:

~~~text
Ngày gửi: URL còn hiệu lực
Ngày người nhận mở lại thư: URL đã hết hạn
Kết quả: ảnh không tải được
~~~

Nếu dùng signed URL trong email, thời hạn phải phù hợp với vòng đời sử dụng thư. Không đặt token có quyền truy cập rộng hoặc thời hạn quá dài nếu không cần thiết. URL có chữ ký cũng có thể được ghi trong log hoặc chia sẻ cùng email; hãy coi nó là một thông tin truy cập cần bảo vệ.

Với tài liệu nhạy cảm, thay vì dùng ảnh URL công khai, cân nhắc kênh tải có xác thực, liên kết có thời hạn được kiểm soát hoặc nhúng dữ liệu nếu chính sách cho phép. Đừng đưa thông tin bí mật vào URL ảnh chỉ để tránh attachment.

## 17. Ảnh từ URL có thể thay đổi sau khi email đã gửi

Một khác biệt quan trọng giữa CID và URL:

- CID gắn byte ảnh cụ thể vào email đã gửi.
- URL gắn email với một địa chỉ; nội dung ở địa chỉ đó có thể được thay đổi về sau.

Ví dụ một email chiến dịch được gửi hôm nay với:

~~~html
<img src="https://cdn.example.org/promo/current-banner.jpg">
~~~

Nếu tuần sau CDN thay file tại cùng URL, người nhận mở lại email cũ có thể thấy banner mới, tùy cache. Điều đó có thể không phù hợp nếu email chứa giá, thời hạn hoặc điều kiện khuyến mãi tại thời điểm gửi.

Nếu nội dung phải phản ánh đúng thời điểm phát hành, dùng **CID** hoặc URL versioned bất biến. Nếu ảnh cần cập nhật liên tục như logo hệ thống, URL có thể phù hợp hơn.

## 18. Accessibility và nội dung thay thế

Dù dùng CID hay URL, email nên có nội dung văn bản hữu ích khi ảnh không hiển thị.

~~~html
<img
  src="cid:paymentStatus"
  alt="Thanh toán đã hoàn tất"
  width="240"
  height="80">
<p>Thanh toán cho đơn hàng ORD-1001 đã hoàn tất.</p>
~~~

Nếu ảnh bị chặn, người nhận vẫn đọc được trạng thái ở dạng text.

Với ảnh trang trí:

~~~html
<img src="cid:decorativeDivider" alt="" width="600">
~~~

Alt rỗng có thể phù hợp khi ảnh không truyền đạt thông tin và không cần được đọc bởi screen reader.

Các nguyên tắc:

- Alt text mô tả ý nghĩa, không nhất thiết lặp tên file.
- Không nhúng văn bản quan trọng duy nhất vào banner.
- Dùng màu sắc và hình ảnh như hỗ trợ, không phải kênh thông tin duy nhất.
- Kiểm tra email ở chế độ ảnh bị tắt.
- Đảm bảo body plain text vẫn truyền đạt nội dung chính nếu có.

## 19. Kiểm tra ảnh inline và URL trong môi trường phát triển

Có thể dùng SMTP capture server để xem raw message và kiểm tra MIME structure trước khi gửi tới hộp thư thật.

### 19.1. Với CID

Kiểm tra:

- HTML có src="cid:...".
- Message có MIME part ảnh.
- Content-ID của part khớp với giá trị trong HTML.
- Content-Type phù hợp byte ảnh.
- Multipart mode đúng.
- setText được gọi trước addInline.
- File/resource có thể đọc tại thời điểm gửi.

### 19.2. Với URL

Kiểm tra:

- src là URL tuyệt đối.
- Dùng HTTPS.
- URL truy cập được từ mạng bên ngoài phù hợp với người nhận.
- Không yêu cầu cookie/session riêng của website.
- URL không hết hạn trước khi email được mở.
- Ảnh trả về đúng media type và status.
- Host có TLS hợp lệ và đủ khả năng phục vụ lưu lượng.

Một request kiểm tra thành công từ máy phát triển không chứng minh mọi email client đều tải được. Mạng doanh nghiệp, proxy, chính sách người nhận và image proxy có thể tạo kết quả khác.

### 19.3. Kiểm tra nhiều kích thước màn hình

Xem email trên ít nhất một màn hình desktop và một viewport mobile. Kiểm tra:

- Ảnh không tràn khỏi vùng nội dung.
- Tỷ lệ ảnh được giữ.
- Chữ trong biểu đồ còn đọc được.
- Banner không quá cao.
- Alt text có ý nghĩa khi ảnh bị tắt.
- Bố cục không phụ thuộc vào CSS chỉ được một số client hỗ trợ.

### 19.4. Đừng chỉ kiểm tra bằng trình duyệt

HTML email có thể hiển thị tốt trong browser nhưng khác trong Gmail, Outlook, Apple Mail hoặc client doanh nghiệp. Trình duyệt web không đại diện cho mọi engine và chính sách hiển thị email.

## 20. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Ảnh inline làm email quá lớn | Ảnh nguồn độ phân giải hoặc dung lượng cao | Resize và nén file trước khi addInline |
| Ảnh hiển thị mờ | File nguồn nhỏ nhưng bị phóng lớn | Tạo ảnh nguồn có đủ pixel cho kích thước hiển thị |
| Đặt width nhỏ nhưng message vẫn lớn | HTML chỉ thay kích thước hiển thị, không thay byte ảnh | Tối ưu chính file ảnh |
| Ảnh URL không hiện | Client chặn remote images hoặc URL lỗi | Có alt text, kiểm tra URL và cung cấp nội dung text |
| URL hoạt động ở local nhưng không ở email client | URL nội bộ, cần VPN/cookie hoặc bị firewall chặn | Dùng host truy cập phù hợp với người nhận |
| Ảnh cũ vẫn hiện sau khi cập nhật | CDN hoặc client cache URL | Version URL và cấu hình cache phù hợp |
| Email cũ mất banner | URL hết hạn hoặc ảnh bị xóa | Giữ tài nguyên theo vòng đời email hoặc dùng CID |
| Ảnh từ URL bị theo dõi ngoài dự kiến | Host ghi nhận request hoặc tracking pixel | Xem xét quyền riêng tư, proxy và consent |
| Inline image không hiển thị | CID không khớp hoặc thiếu MIME part | Kiểm tra addInline và HTML |
| SVG/WebP không hiển thị | Client không hỗ trợ hoặc chặn định dạng | Cung cấp PNG/JPEG thay thế |
| Mobile làm ảnh tràn | Kích thước cố định hoặc CSS không phù hợp | Dùng width hợp lý, max-width và height:auto |
| Tải ảnh server-side gây lỗi bảo mật | URL do người dùng điều khiển, thiếu kiểm tra SSRF | Allowlist host, kiểm tra redirect/IP, timeout và size |

## 21. Câu hỏi thường gặp

**1. Ảnh rộng 600 px có nghĩa file phải nặng 600 KB không?**

Không. Pixel mô tả kích thước hình ảnh, còn KB/MB mô tả dung lượng dữ liệu. Hai ảnh cùng kích thước pixel có thể có dung lượng khác nhau rất lớn.

**2. Đặt width="160" có làm ảnh inline nhỏ hơn trong email không?**

Nó yêu cầu client hiển thị ảnh ở chiều rộng 160 pixel theo cách client hỗ trợ. Nó không giảm số byte của file đã nhúng. Muốn giảm dung lượng, cần resize hoặc nén file nguồn trước.

**3. Nên dùng ảnh nguồn 1x hay 2x?**

Nếu cần sắc nét trên màn hình mật độ cao, ảnh nguồn 2x so với kích thước hiển thị có thể hữu ích. Nhưng nó làm tăng dữ liệu. Hãy chọn theo mức chi tiết thực tế và giới hạn message.

**4. Ảnh URL có làm email nhỏ hơn không?**

Thông thường có, vì message chỉ chứa URL thay vì byte ảnh. Người nhận phải tải ảnh từ host bên ngoài khi client cho phép.

**5. Vì sao ảnh URL không hiển thị dù mở được trên browser?**

Email client có thể chặn ảnh từ xa, không có cookie/session cần thiết, dùng proxy khác, hoặc URL không truy cập được từ mạng người nhận.

**6. CID có chắc chắn hiển thị hơn URL không?**

CID không cần tải byte ảnh từ host ngoài, nhưng client vẫn có thể ẩn hình ảnh hoặc không xử lý message như mong đợi. Cần thử trên client mục tiêu.

**7. Có thể dùng CID cho banner lớn không?**

Có về mặt kỹ thuật, nhưng ảnh sẽ làm message lớn. Với banner lớn, URL/CDN thường giảm dung lượng email; CID phù hợp khi ảnh cần gắn với bản message tại thời điểm gửi.

**8. Có thể kết hợp CID và URL trong cùng email không?**

Có. Ví dụ logo dùng CID, banner lớn dùng URL HTTPS. Hãy bảo đảm nội dung vẫn đầy đủ khi remote image bị chặn.

**9. Ảnh URL có thể bị thay đổi sau khi email gửi không?**

Có. Nếu server thay nội dung tại cùng URL, người mở lại thư có thể nhận ảnh mới, tùy cache. Dùng URL versioned hoặc CID nếu cần nội dung bất biến.

**10. Có nên dùng data:image/png;base64 trong HTML email?**

Không nên dựa vào cách này cho email cần tương thích rộng. Nhiều client xử lý data URL không đồng nhất. Dùng CID cho ảnh nhúng hoặc HTTPS cho ảnh bên ngoài.

**11. Có thể dùng SVG hoặc WebP không?**

Có thể ở một số client, nhưng hỗ trợ không đồng nhất. PNG/JPEG thường là lựa chọn thực dụng hơn khi cần tương thích rộng.

**12. Khi server Spring tải ảnh URL để nhúng CID, cần lưu ý gì?**

Chỉ tải từ nguồn được kiểm soát; xác minh host và redirect, chặn địa chỉ nội bộ không được phép, đặt timeout và giới hạn byte, kiểm tra media type và định dạng thực. Đây là request từ backend nên cần phòng ngừa SSRF.

**13. Ảnh remote có thể dùng để biết người dùng mở email không?**

Request tải ảnh có thể tạo tín hiệu truy cập, nhưng proxy, cache và chặn ảnh làm dữ liệu không chính xác. Nếu sử dụng tracking, cần xem xét quyền riêng tư và yêu cầu pháp lý.

## 22. Ghi nhớ khi chọn kích thước ảnh inline và ảnh từ URL

**Kích thước hiển thị**, **kích thước pixel nguồn** và **dung lượng file** là ba khái niệm khác nhau. Thuộc tính width/height trong HTML điều khiển cách hiển thị, không tự giảm số byte của ảnh. Muốn email nhẹ hơn, hãy resize và nén file nguồn, chọn định dạng phù hợp, giới hạn số lượng ảnh và tính đến phần tăng dung lượng do MIME/Base64.

**Inline resource bằng CID** mang byte ảnh trong message, thích hợp khi hình ảnh cần gắn với nội dung tại thời điểm gửi hoặc không muốn phụ thuộc image host bên ngoài. **Ảnh URL HTTPS** giúp message nhỏ hơn và cho phép quản lý ảnh độc lập, nhưng phụ thuộc mạng, chính sách chặn remote image, cache, vòng đời URL và quyền riêng tư.

Trong Spring Framework Mail, dùng **addInline(...)** cho ảnh được HTML tham chiếu bằng **cid:**; nếu chỉ dùng ảnh bên ngoài, đặt URL tuyệt đối trong **src** và không cần tạo MIME part ảnh. Dù chọn cách nào, hãy giữ tỷ lệ, khai báo kích thước hiển thị hợp lý, cung cấp alt text, không đặt thông tin thiết yếu duy nhất trong ảnh và kiểm tra trên các email client mục tiêu.
