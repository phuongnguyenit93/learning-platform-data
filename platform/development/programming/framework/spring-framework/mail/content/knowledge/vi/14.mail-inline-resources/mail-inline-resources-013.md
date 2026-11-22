# Bảo vệ resource khỏi dữ liệu ngoài ý muốn trong Spring Framework Mail

Email HTML có thể chứa logo, ảnh minh họa, biểu tượng hoặc hình xác nhận được nhúng trực tiếp vào thông điệp. Trong Spring Framework Mail, những tài nguyên này thường được thêm bằng phương thức **MimeMessageHelper.addInline(...)** và được HTML tham chiếu qua Content-ID, ví dụ **src="cid:brand-logo@example.com"**. Cách làm này giúp người nhận xem hình mà không phải tải một URL ảnh riêng từ máy chủ bên ngoài.

Tuy nhiên, một inline resource vẫn là dữ liệu được đưa vào email MIME. Nếu ứng dụng lấy ảnh, đường dẫn, URL hoặc tên file trực tiếp từ request rồi nhúng mà không kiểm soát, email có thể mang nội dung giả mạo, tệp độc hại, tài nguyên quá lớn hoặc tham chiếu đến hệ thống nội bộ. Việc tải URL do người dùng chỉ định còn có thể tạo lỗ hổng SSRF. Email HTML cũng có thể khiến ứng dụng đọc thư của người nhận tải ảnh từ máy chủ theo dõi bên ngoài, làm lộ thời điểm mở thư hoặc địa chỉ IP.

Vì vậy, bảo vệ inline resource cần bao quát **nguồn dữ liệu, định dạng, kích thước, Content-ID, cách tạo HTML, cách mở stream và thời điểm gửi**. Spring Mail hỗ trợ đóng gói resource; chính sách tin cậy và kiểm tra dữ liệu phải do ứng dụng thực hiện trước khi gọi helper.

## 1. Inline resource là gì?

Một inline resource là một phần dữ liệu được nhúng trong MIME message và được một phần nội dung khác tham chiếu. Trường hợp phổ biến nhất là ảnh được HTML tham chiếu bằng URI có scheme **cid:**.

Ví dụ HTML:

~~~html
<html>
  <body>
    <h1>Đơn hàng đã sẵn sàng</h1>
    <img src="cid:brand-logo@example.com"
         alt="Shop Example"
         width="140">
  </body>
</html>
~~~

Phần ảnh được thêm vào message:

~~~java
helper.addInline(
        "brand-logo@example.com",
        new ClassPathResource("mail/images/brand-logo.png"),
        "image/png");
~~~

Giá trị Content-ID trong MIME tương ứng với chuỗi trong URI cid. Trong lời gọi addInline, truyền ID thuần; HTML mới dùng tiền tố cid:. Không truyền cả chuỗi cid: vào đối số Content-ID và không tự ghép dấu ngoặc nhọn vào header.

Một MIME message có thể được tổ chức như sau:

~~~text
MimeMessage
└── multipart/related
    ├── text/html
    │   └── <img src="cid:brand-logo@example.com">
    └── image/png
        └── Content-ID: <brand-logo@example.com>
~~~

Nếu email có cả plain text, HTML và attachment, MIME có thể lồng thêm multipart/alternative và multipart/mixed. Inline resource vẫn là một part trong cấu trúc liên quan đến HTML; nó không phải một URL công khai và cũng không phải attachment thông thường mà người nhận phải mở riêng.

### Phân biệt các cách đưa ảnh vào email

| Cách tham chiếu | Dữ liệu nằm ở đâu? | Hành vi và rủi ro chính |
| --- | --- | --- |
| CID inline | Bên trong MIME message | Không cần tải ảnh từ host bên ngoài; làm email lớn hơn |
| URL HTTPS | Trên máy chủ web/CDN | Email client có thể tải ảnh khi hiển thị; có thể tiết lộ thông tin truy cập |
| Data URI | Nhúng chuỗi dữ liệu vào HTML | Khả năng hỗ trợ không đồng đều, HTML phình lớn và có thể bị client loại bỏ |
| File URI hoặc đường dẫn cục bộ | Trên máy của người gửi | Không phải đường dẫn hợp lệ để người nhận truy cập; không nên đưa vào email |
| Attachment | Một part MIME độc lập | Người nhận tải/mở file riêng, không tự hiển thị như ảnh trong HTML |

Với logo và hình cần thiết cho nội dung thư, CID từ resource đã được kiểm soát thường là lựa chọn phù hợp. Với ảnh trang trí không cần thiết, có thể bỏ ảnh để giảm kích thước và bề mặt xử lý.

## 2. Những dữ liệu ngoài ý muốn có thể đi vào inline resource như thế nào?

Một số đường vào thường gặp:

1. Người dùng tải ảnh lên và yêu cầu hệ thống gửi ảnh đó trong email.
2. Request chứa URL ảnh, ứng dụng tải URL rồi nhúng vào thư.
3. Request truyền tên file hoặc resource path, service dùng nó để tạo ClassPathResource/FileSystemResource.
4. Nội dung HTML do người dùng cung cấp chứa thẻ img, style hoặc URL tùy ý.
5. Một template cho phép chèn biến chưa được kiểm soát vào thuộc tính src hoặc Content-ID.
6. File được đọc từ storage nhưng nội dung đã bị thay đổi sau khi quét.
7. Một thư viện tạo thumbnail/convert ảnh xử lý file quá lớn hoặc định dạng không an toàn.

Ví dụ nguy hiểm:

~~~java
String imageUrl = request.imageUrl();
byte[] bytes = new URL(imageUrl).openStream().readAllBytes();
helper.addInline("image", new ByteArrayResource(bytes), "image/png");
~~~

Đoạn code này tin URL do request cung cấp, không giới hạn giao thức, host, redirect, thời gian tải, kích thước hay loại nội dung thực. Nó cũng gán content type cố định mà không xác minh dữ liệu. Nếu URL trỏ tới địa chỉ nội bộ, máy chủ ứng dụng có thể bị lợi dụng để truy cập dịch vụ mà người dùng bên ngoài không được phép gọi.

Một ví dụ khác:

~~~java
String path = request.resourcePath();
Resource image = resourceLoader.getResource(path);
helper.addInline("image", image, "image/png");
~~~

Nếu path chịu ảnh hưởng trực tiếp từ request, người dùng có thể thử đường dẫn filesystem, classpath hoặc URL ngoài dự kiến. Việc dùng Spring Resource API không tự biến location không tin cậy thành an toàn.

### Ranh giới tin cậy

| Nguồn | Mức tin cậy mặc định | Cách xử lý |
| --- | --- | --- |
| Logo tĩnh được đóng gói trong ứng dụng | Có thể tin cậy nếu artifact và quy trình build được kiểm soát | Dùng resource cố định, kiểm tra khi build/deploy |
| Ảnh từ object storage nội bộ đã được phê duyệt | Tin cậy theo trạng thái và quyền truy cập | Đọc đúng object version, kiểm tra metadata và hash |
| Ảnh do người dùng upload | Không tin cậy | Giới hạn, phát hiện định dạng, kiểm tra cấu trúc và quét malware |
| URL do người dùng nhập | Không tin cậy | Không tải trực tiếp; nếu bắt buộc phải fetch, dùng proxy/fetcher có allowlist và kiểm soát mạng |
| HTML do người dùng cung cấp | Không tin cậy | Tránh render trực tiếp; nếu nghiệp vụ cần, sanitize bằng allowlist chuyên dụng |
| Tên file hoặc resource path từ request | Không tin cậy | Ánh xạ qua ID/key allowlist, không dùng làm đường dẫn tùy ý |

**Một resource chỉ được coi là đã phê duyệt khi ứng dụng biết nó đến từ đâu, nội dung nào được kiểm tra và đúng phiên bản nào sẽ được gửi.**

## 3. Ưu tiên resource tĩnh từ classpath cho nội dung thương hiệu

Logo, icon hoặc hình minh họa dùng chung thường không cần đến từ request. Đặt chúng trong thư mục resource của ứng dụng:

~~~text
src/main/resources/
└── mail/
    └── images/
        ├── brand-logo.png
        └── order-ready-banner.png
~~~

Nạp resource bằng ClassPathResource:

~~~java
Resource logo = new ClassPathResource(
        "mail/images/brand-logo.png");
~~~

Lợi ích:

- Đường dẫn do ứng dụng kiểm soát.
- Nội dung được đóng gói cùng phiên bản ứng dụng.
- Không cần fetch URL bên ngoài trong lúc gửi email.
- Dễ review thay đổi trong repository và kiểm tra artifact.
- Không phụ thuộc thư mục làm việc của process.

Không nên tạo path từ dữ liệu người dùng rồi nối vào prefix classpath. Nếu có nhiều logo theo thương hiệu hoặc tenant, dùng một key đã được xác thực và ánh xạ key sang resource cụ thể:

~~~java
enum Brand {
    SHOP_A,
    SHOP_B
}

private static final Map<Brand, String> LOGO_RESOURCES = Map.of(
        Brand.SHOP_A, "mail/images/shop-a.png",
        Brand.SHOP_B, "mail/images/shop-b.png");

Resource logoFor(Brand brand) {
    String path = LOGO_RESOURCES.get(brand);
    if (path == null) {
        throw new IllegalArgumentException("Unsupported brand");
    }
    return new ClassPathResource(path);
}
~~~

Giá trị Brand phải được xác định từ tenant/account đã được xác thực và kiểm tra quyền. Không nhận trực tiếp chuỗi như ../../application.yml hoặc file:/etc/... làm resource location.

### Resource classpath không nhất thiết là File

Khi ứng dụng chạy từ executable JAR, ảnh có thể nằm trong archive chứ không phải file độc lập. Vì vậy, không phụ thuộc vào Resource.getFile() để đọc ảnh. Spring resource có thể mở stream:

~~~java
try (InputStream input = logo.getInputStream()) {
    // Đọc hoặc chuyển dữ liệu cho thành phần cần xử lý.
}
~~~

Với MimeMessageHelper, có thể truyền Resource/InputStreamSource thích hợp để helper đọc dữ liệu khi tạo MIME. Không mở stream một lần, đọc hết rồi truyền chính stream đã đóng cho addInline.

## 4. Không tải URL tùy ý để tạo inline resource

Khi HTML trực tiếp tham chiếu một URL HTTPS, email client của người nhận thường là bên tải ảnh. Khi ứng dụng tự tải URL rồi nhúng ảnh vào MIME, **máy chủ ứng dụng trở thành HTTP client**. Hai trường hợp có rủi ro khác nhau.

### 4.1. Ứng dụng tải URL do người dùng cung cấp

Đây là một dạng SSRF (Server-Side Request Forgery). Kẻ tấn công có thể thử khiến ứng dụng truy cập:

~~~text
http://127.0.0.1/
http://localhost:8080/actuator
http://169.254.169.254/
http://10.0.0.5/internal-service
file:///etc/passwd
~~~

Các địa chỉ trên chỉ là ví dụ về đích không nên được phép. Môi trường thật có thể có địa chỉ nội bộ, dịch vụ metadata cloud, giao diện quản trị hoặc endpoint chỉ có thể truy cập từ mạng backend.

Không dùng URLConnection, URL.openStream hoặc HTTP client mặc định với URL không tin cậy rồi đính kèm kết quả. Chỉ kiểm tra chuỗi bắt đầu bằng https:// là chưa đủ: redirect có thể trỏ sang host khác, DNS có thể phân giải sang IP nội bộ, hoặc host công khai có thể thay đổi kết quả DNS.

### 4.2. Email client tải URL ảnh từ xa

Nếu HTML chứa:

~~~html
<img src="https://images.example.com/banner.png" alt="Banner">
~~~

thì email client có thể tải ảnh từ host đó khi người nhận mở thư hoặc cho phép hiển thị ảnh. Điều này có thể:

- Tiết lộ cho host bên ngoài thời điểm người nhận mở email.
- Tiết lộ IP hoặc thông tin kết nối tùy cơ chế proxy/cache của email client.
- Tạo tracking pixel hoặc theo dõi hành vi.
- Khiến nội dung hình thay đổi sau thời điểm gửi.
- Không hiển thị nếu client chặn remote image hoặc host ngừng hoạt động.

Một số client dùng proxy/cache ảnh, nên dữ liệu thực tế được chia sẻ với host có thể khác nhau. Dù vậy, remote image vẫn tạo một phụ thuộc ngoài email và có thể có hệ quả riêng tư.

### 4.3. Lựa chọn phù hợp

| Mục đích | Lựa chọn khuyến nghị |
| --- | --- |
| Logo thương hiệu ổn định | CID từ classpath hoặc storage đã phê duyệt |
| Ảnh sản phẩm thay đổi theo giao dịch | Lấy từ storage nội bộ bằng ID đã được authorization, kiểm tra nội dung rồi nhúng CID nếu cần |
| Ảnh do người dùng upload | Quarantine, kiểm tra loại tệp, quét malware và phê duyệt trước khi nhúng |
| Ảnh trang trí không thiết yếu | Có thể bỏ ảnh |
| Ảnh chỉ tồn tại ở URL bên ngoài | Ưu tiên không fetch tùy ý; nếu nghiệp vụ bắt buộc, dùng dịch vụ fetch riêng có allowlist và kiểm soát mạng |

Không nên tự động tải tất cả URL trong HTML để chuyển thành CID. Việc đó có thể biến quá trình render template thành một dịch vụ fetch URL tùy ý.

## 5. Nếu bắt buộc phải lấy ảnh từ nguồn bên ngoài

Một số nghiệp vụ có lý do hợp lệ để lấy ảnh từ nhà cung cấp hoặc CDN đã biết. Khi đó, không nên cho phép URL tự do. Xây một adapter/fetcher chỉ chấp nhận **host, scheme và đường dẫn đã được phê duyệt**.

Các kiểm soát tối thiểu:

1. Chỉ cho phép HTTPS và port được quy định.
2. Allowlist hostname cụ thể; không dùng kiểm tra hậu tố chuỗi đơn giản để xác thực host.
3. Tắt redirect tự động hoặc kiểm tra lại từng redirect, gồm scheme, host và IP đích.
4. Phân giải DNS và từ chối địa chỉ loopback, private, link-local, multicast, reserved và metadata endpoint.
5. Áp dụng network egress policy để service fetcher không thể truy cập mạng nội bộ không cần thiết.
6. Có connect timeout, read timeout và tổng thời gian tải.
7. Giới hạn số byte khi streaming; không tải vô hạn vào heap.
8. Kiểm tra Content-Length nếu có nhưng vẫn đếm byte thực tế.
9. Phát hiện media type từ nội dung, không chỉ tin response Content-Type.
10. Không gửi Authorization header hoặc cookie của người dùng tới host ngoài.
11. Quét/kiểm tra nội dung trước khi nhúng.
12. Lưu kết quả theo object ID/hash, không theo URL tùy ý.

**DNS validation một lần không đủ nếu client sau đó phân giải DNS lần nữa.** Một thiết kế an toàn cần kiểm soát địa chỉ IP thực được kết nối hoặc thực thi policy mạng ở tầng egress. Điều này thường phù hợp hơn khi tách việc fetch thành một service chuyên biệt.

### Pseudocode cho fetcher giới hạn

~~~text
fetchApprovedImage(imageKey):
    config = allowlist.lookup(imageKey)
    if config is absent:
        reject

    resolve destination under controlled DNS policy
    reject private, loopback, link-local and reserved addresses
    connect to approved HTTPS host
    disable automatic redirects
    enforce connect/read/total timeout

    stream bytes with a hard maximum
    detect actual media type
    require media type in image allowlist
    validate dimensions and structure
    scan content according to policy

    return immutable approved resource
~~~

Đây là mô tả kiến trúc, không phải một HTTP client hoàn chỉnh. Cách kiểm tra DNS/IP, redirect và kết nối cần được triển khai theo thư viện HTTP và môi trường mạng của ứng dụng.

### Không cho phép mọi scheme

Không chấp nhận các scheme như file:, ftp:, jar:, data: hoặc protocol nội bộ chỉ vì một API có thể mở được chúng. Với một resource ảnh từ xa, thông thường chỉ cần HTTPS đến host cụ thể. Với resource classpath, dùng ClassPathResource hoặc location do ứng dụng định nghĩa.

## 6. Kiểm tra định dạng và nội dung ảnh

Phần mở rộng hoặc Content-Type do client gửi không chứng minh file là ảnh hợp lệ. Một file có tên logo.png có thể chứa HTML, executable hoặc dữ liệu khác.

Một pipeline kiểm tra ảnh nên gồm:

- Allowlist định dạng thực sự cần dùng, thường là PNG/JPEG cho ảnh email.
- Phát hiện media type từ byte content.
- Đối chiếu phần mở rộng với định dạng phát hiện.
- Kiểm tra cấu trúc bằng parser ảnh phù hợp.
- Giới hạn dung lượng file và kích thước pixel.
- Quét malware theo chính sách của hệ thống.
- Cân nhắc decode rồi encode lại sang định dạng raster an toàn nếu nghiệp vụ cần chuẩn hóa.
- Loại metadata không cần thiết như EXIF/GPS khi có yêu cầu riêng tư.

### Vì sao không nên cho phép mọi định dạng ảnh?

SVG là một định dạng dựa trên XML, có thể chứa tham chiếu tài nguyên ngoài hoặc nội dung phức tạp. Khả năng hỗ trợ SVG trong email client cũng không đồng nhất. Nếu chỉ cần logo hoặc hình minh họa, PNG/JPEG thường dễ kiểm soát hơn.

GIF có thể chứa nhiều frame/animation. Nếu không cần chuyển động, có thể từ chối GIF hoặc chuyển đổi bằng pipeline có giới hạn. WebP và các định dạng mới cũng cần cân nhắc mức hỗ trợ của email client mục tiêu.

### Magic bytes và MIME type

Một số signature phổ biến:

| Định dạng | Byte đầu thường gặp | MIME type |
| --- | --- | --- |
| PNG | 89 50 4E 47 0D 0A 1A 0A | image/png |
| JPEG | FF D8 FF | image/jpeg |
| GIF | 47 49 46 38 | image/gif |
| SVG | Văn bản XML/SVG, không có một signature nhị phân cố định | image/svg+xml |

Magic bytes là dấu hiệu nhận dạng ban đầu, không phải parser hoàn chỉnh và không chứng minh nội dung an toàn. Một số file polyglot có thể được diễn giải theo nhiều định dạng. Dùng detector/parser đáng tin cậy, giới hạn định dạng và quét malware khi dữ liệu đến từ người dùng.

### Giới hạn pixel, không chỉ byte

Một ảnh có kích thước file nhỏ vẫn có thể khai báo chiều rộng/chiều cao rất lớn, khiến quá trình decode tiêu tốn nhiều bộ nhớ. Khi xử lý ảnh, giới hạn:

- Kích thước upload tính bằng byte.
- Chiều rộng và chiều cao tối đa.
- Tổng số pixel.
- Số frame nếu định dạng hỗ trợ animation.
- Thời gian decode/convert.
- Dung lượng sau khi encode lại.

Không gọi ImageIO.read trên dữ liệu không giới hạn trong một request thread. Dùng worker/processor có timeout, quota và giới hạn bộ nhớ phù hợp.

## 7. Không cho dữ liệu người dùng điều khiển resource path

Một số ứng dụng chọn ảnh theo tên:

~~~java
String path = request.getParameter("logo");
Resource resource = new ClassPathResource("mail/images/" + path);
~~~

Nếu không giới hạn giá trị logo, request có thể thử traversal, tên resource nội bộ hoặc file ngoài dự kiến. Cách an toàn hơn là ánh xạ một mã lựa chọn đã được kiểm tra:

~~~java
enum LogoVariant {
    DEFAULT,
    PREMIUM
}

private static final Map<LogoVariant, String> LOGOS = Map.of(
        LogoVariant.DEFAULT, "mail/images/brand-default.png",
        LogoVariant.PREMIUM, "mail/images/brand-premium.png");

Resource loadLogo(LogoVariant variant) {
    String path = LOGOS.get(variant);
    if (path == null) {
        throw new IllegalArgumentException("Unsupported logo variant");
    }
    return new ClassPathResource(path);
}
~~~

Nếu biến thể logo đến từ tenant, lấy nó từ bản ghi tenant đã được xác thực và kiểm tra quyền. Không tin một chuỗi do người dùng gửi chỉ vì nó trùng với tên file hợp lệ.

### Resource từ storage

Với ảnh do người dùng tải lên, API nên nhận một attachment ID hoặc asset ID. Service kiểm tra:

1. Asset có thuộc user/tenant hiện tại không?
2. Asset có được phê duyệt và chưa bị thu hồi không?
3. Scan result có gắn với đúng object version/hash không?
4. Content type và kích thước có trong allowlist không?
5. Người nhận email có quyền nhận nội dung đó không?

Sau đó mới mở object đã phê duyệt. Không nhận trực tiếp bucket name, object key hoặc filesystem path từ request.

## 8. Bảo vệ HTML template và thuộc tính src

Ngay cả khi resource image đã an toàn, cách template tham chiếu đến nó cũng có thể bị thao túng. Đặc biệt, không nối chuỗi không tin cậy vào thuộc tính HTML.

Ví dụ không an toàn:

~~~java
String html = "<img src=\\"" + request.imageUrl() + "\\">";
~~~

Dữ liệu có thể chứa dấu ngoặc kép, markup hoặc URL scheme ngoài dự kiến. Nếu template engine hỗ trợ, dùng template expression được escape và cung cấp một CID đã được tạo từ ứng dụng:

~~~html
<img src="cid:brand-logo@example.com"
     alt="Shop Example"
     width="140">
~~~

Ở đây CID phải do ứng dụng tạo từ một giá trị hợp lệ, không lấy từ request. Khi dùng Thymeleaf, không dùng th:utext để chèn HTML không tin cậy. Với template khác, bật chế độ auto-escape và dùng API escape theo đúng context.

### Escape HTML không thay thế kiểm tra URI

Escape chuỗi để đưa vào HTML attribute chỉ ngăn ký tự phá cấu trúc markup. Nó không biến một URL nguy hiểm thành URL hợp lệ. Nếu thuộc tính là href hoặc src, cần kiểm tra scheme, host và chính sách resource riêng.

Đối với src của ảnh inline, chỉ cho phép CID được tạo từ danh sách resource đã duyệt. Không cho phép request tự đưa vào file:, javascript:, data:, http://127.0.0.1 hoặc URL tùy ý.

### Nếu người dùng được phép viết HTML?

Nếu sản phẩm có chức năng cho người dùng soạn email HTML, không thể chỉ escape toàn bộ vì họ có thể cần định dạng. Khi đó cần HTML sanitizer có allowlist phần tử/attribute, loại bỏ script, event handler, form, iframe, object, embed và URL scheme không được phép. Quy tắc phải bao gồm cả src, href, CSS url(...) và các tham chiếu tài nguyên khác.

Không nên tự viết sanitizer bằng regex. Dùng thư viện được duy trì và cấu hình policy tối thiểu cho email; sau đó vẫn render/preview trong môi trường cô lập.

## 9. Content-ID: tạo và sử dụng an toàn

Content-ID là định danh MIME cho một body part. HTML dùng dạng URI:

~~~html
<img src="cid:brand-logo@example.com" alt="Brand">
~~~

Trong Spring:

~~~java
helper.addInline(
        "brand-logo@example.com",
        logoResource,
        "image/png");
~~~

Một số quy tắc:

- Content-ID phải được ứng dụng tạo, không lấy nguyên từ người dùng.
- Dùng chuỗi ngắn, ký tự an toàn và ổn định theo quy ước.
- Mỗi Content-ID phải duy nhất trong phạm vi một MIME message.
- Mỗi CID được tham chiếu trong HTML phải có đúng một inline part tương ứng.
- Không dùng CID để nhúng đường dẫn filesystem hoặc URL.
- Không tự ghép raw MIME header; để MimeMessageHelper tạo header đúng định dạng.
- Không đưa CR/LF vào Content-ID.

### CID cố định hay ngẫu nhiên?

Với logo tĩnh, một CID cố định như brand-logo@example.com trong mỗi message thường đủ vì phạm vi định danh là từng MIME message. Nếu cùng một message có nhiều ảnh động hoặc nhiều resource cùng loại, tạo ID riêng cho từng part.

Ví dụ:

~~~java
String contentId = "asset-" + UUID.randomUUID()
        + "@mail.example.com";
String imageReference = "cid:" + contentId;
~~~

HTML cần dùng đúng giá trị đã tạo. Không tái sử dụng cùng CID cho hai ảnh khác nhau trong cùng message, vì email client có thể tham chiếu nhầm part.

### Không dùng CID như một bí mật hoặc quyền truy cập

Content-ID là định danh trong MIME, không phải token bảo mật. Người nhận có thể đọc source email và thấy CID. Không nhúng credential, session ID hoặc access token vào CID.

## 10. Tên file và header MIME

Inline resource thường không cần tên file hiển thị như attachment, nhưng nếu có metadata filename hoặc resource được thêm như attachment thì tên vẫn cần chuẩn hóa. Tên do người dùng gửi có thể chứa:

~~~text
../../secret.png
..\..\Windows\system.ini
image.png CRLF Bcc: victim@example.com
~~~

Không dùng chuỗi tên file thô làm path hoặc tự ghép Content-Disposition header. Dùng API của Spring/Jakarta Mail và tên hiển thị đã được chuẩn hóa. Loại bỏ separator, ký tự điều khiển và giới hạn độ dài theo chính sách.

Với inline image, ưu tiên dùng resource cố định hoặc object ID đã phê duyệt; filename không cần tham gia vào Content-ID. Không lấy filename làm CID.

## 11. Kích thước, số lượng và tài nguyên MIME

Mỗi inline image làm tăng kích thước email. Base64 encoding thường khiến dữ liệu nhị phân tăng khoảng một phần ba, chưa kể MIME header và boundary. Một template có thể chứa logo, banner, icon và nhiều ảnh sản phẩm; tổng dung lượng có thể nhanh chóng vượt giới hạn của SMTP provider hoặc mailbox.

Đặt giới hạn:

| Giới hạn | Mục đích |
| --- | --- |
| Kích thước một ảnh | Theo nhu cầu thực tế của template |
| Tổng byte inline resource | Có giới hạn cho một email |
| Số lượng inline parts | Chỉ cho các ảnh thật sự cần |
| Kích thước pixel | Giới hạn chiều rộng, chiều cao và tổng pixel |
| Tổng MIME message | Chừa khoảng trống cho Base64 và body |
| Thời gian xử lý | Giới hạn decode, resize, scan và MIME construction |

Không đặt các con số tùy ý rồi dùng cho mọi hệ thống. Chọn ngưỡng theo provider, loại email, thiết bị người nhận và tải vận hành. Kiểm tra kích thước sau khi xử lý ảnh, vì ảnh chuyển đổi có thể lớn hơn hoặc nhỏ hơn bản gốc.

### Không dùng tracking pixel

Một ảnh 1x1 được host từ xa có thể dùng để ghi nhận việc mở email. Đây là một hình thức theo dõi hành vi và có thể có hệ quả về quyền riêng tư hoặc yêu cầu đồng ý. Không thêm tracking pixel mặc định chỉ vì template marketing có ví dụ sẵn. Nếu sản phẩm có analytics email, cần có cơ sở pháp lý/chính sách, thông báo minh bạch và lựa chọn phù hợp cho người nhận.

CID image được nhúng trong email không tạo HTTP request tới máy chủ tracking khi hiển thị, nhưng việc nhúng ảnh vẫn làm lộ nội dung email cho bất kỳ ai có quyền truy cập thư. Không coi CID là biện pháp bảo vệ dữ liệu nhạy cảm.

## 12. Quét và phê duyệt ảnh do người dùng upload

Nếu ảnh được tải lên từ người dùng và sau đó nhúng inline, cần pipeline tương tự attachment:

~~~text
Upload
  |
  v
Size + filename validation
  |
  v
Quarantine storage
  |
  v
Detected image type + structural validation
  |
  v
Malware scan / safe image processing
  |
  v
Approved immutable object + hash
  |
  v
Mail service reads exact approved version
  |
  v
MimeMessageHelper.addInline(...)
~~~

Không gửi ảnh trong trạng thái PENDING, SCANNING, ERROR hoặc UNKNOWN. Scanner không khả dụng không đồng nghĩa file sạch. Chỉ sử dụng nội dung đã được phê duyệt theo đúng hash/object version.

### Xử lý lại ảnh

Một số hệ thống giải mã ảnh rồi encode lại thành PNG/JPEG để loại bỏ metadata hoặc chuẩn hóa nội dung. Việc này có thể giảm một số rủi ro và làm định dạng nhất quán hơn, nhưng không phải bảo đảm an toàn tuyệt đối:

- Parser/decoder cũng có thể có lỗ hổng.
- Ảnh đầu vào vẫn phải bị giới hạn trước khi decode.
- Output sau chuyển đổi là byte content mới, cần kiểm tra và scan theo policy.
- Cần giữ đúng kích thước và định dạng MIME của output.
- Nếu metadata GPS không cần thiết, xác nhận pipeline thực sự loại bỏ nó.

Không tự chỉnh byte của file ảnh bằng thao tác chuỗi hoặc regex.

## 13. Đọc resource an toàn và vòng đời InputStreamSource

Spring Mail có overload nhận InputStreamSource:

~~~java
helper.addInline(
        contentId,
        inputStreamSource,
        contentType);
~~~

InputStreamSource cần cung cấp stream có thể mở khi framework cần đọc nội dung. Đừng đưa một InputStream đã đọc hết hoặc đã đóng vào resource source có thể bị gọi lại.

Ví dụ với classpath resource:

~~~java
Resource logo = new ClassPathResource(
        "mail/images/brand-logo.png");

helper.addInline(
        "brand-logo@example.com",
        logo,
        "image/png");
~~~

Ví dụ với byte array đã được phê duyệt:

~~~java
ByteArrayResource logo = new ByteArrayResource(approvedImageBytes);

helper.addInline(
        "customer-logo@example.com",
        logo,
        "image/png");
~~~

Với object storage, tạo InputStreamSource mở một stream mới cho đúng object version:

~~~java
InputStreamSource source = () ->
        approvedStorage.openStream(
                approvedAsset.objectKey(),
                approvedAsset.version());

helper.addInline(
        contentId,
        source,
        approvedAsset.contentType());
~~~

Đoạn code giả định approvedStorage là API nội bộ. Không mở file theo đường dẫn hoặc key lấy trực tiếp từ request. Storage cần bảo đảm object version bất biến sau khi scan.

### Không đóng stream quá sớm

Không viết:

~~~java
InputStream input = logo.getInputStream();
try (input) {
    helper.addInline("logo@example.com",
            new InputStreamResource(input),
            "image/png");
}
// Stream đã đóng trước khi message được serialize.
~~~

Trong một số đường xử lý, helper/Jakarta Mail chỉ đọc nội dung khi message được ghi hoặc gửi. Nếu stream bị đóng trước thời điểm đó, việc tạo MIME có thể thất bại hoặc resource rỗng. Dùng Resource có thể mở stream mới, ByteArrayResource cho file nhỏ, hoặc InputStreamSource tạo stream mới mỗi lần được gọi.

### Gọi setText trước addInline

Khi dùng MimeMessageHelper cho HTML có CID, nên đặt body trước rồi thêm inline resource:

~~~java
helper.setText(plainText, htmlText);
helper.addInline(
        "brand-logo@example.com",
        logoResource,
        "image/png");
~~~

Thứ tự này giúp helper xây dựng cấu trúc multipart liên quan phù hợp với nhiều email client. Không tự thao tác MIME tree cấp thấp nếu API helper đã đáp ứng nhu cầu.

## 14. Ví dụ service dùng resource inline đã kiểm soát

Ví dụ dưới đây sử dụng logo tĩnh trong classpath. Không có URL ảnh do request cung cấp và không đọc resource path từ client.

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.springframework.web.util.HtmlUtils;

@Service
public class OrderReadyMailService {

    private static final String LOGO_CID =
            "brand-logo@example.com";

    private final JavaMailSender mailSender;

    public OrderReadyMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(
            String recipient,
            String customerName,
            String orderId) throws MessagingException {

        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException("Recipient is required");
        }
        if (customerName == null || customerName.isBlank()) {
            customerName = "bạn";
        }
        if (orderId == null || !orderId.matches("[A-Za-z0-9-]{1,40}")) {
            throw new IllegalArgumentException("Invalid order ID");
        }

        String safeName = HtmlUtils.htmlEscape(customerName);
        String safeOrderId = HtmlUtils.htmlEscape(orderId);

        String plainText = """
                Xin chào %s,

                Đơn hàng %s đã sẵn sàng.
                Cảm ơn bạn đã mua hàng.
                """.formatted(customerName, orderId);

        String htmlText = """
                <!doctype html>
                <html lang="vi">
                  <body>
                    <img src="cid:brand-logo@example.com"
                         alt="Shop Example"
                         width="140">
                    <h1>Đơn hàng đã sẵn sàng</h1>
                    <p>Xin chào <strong>%s</strong>,</p>
                    <p>Mã đơn hàng: <strong>%s</strong></p>
                    <p>Cảm ơn bạn đã mua hàng.</p>
                  </body>
                </html>
                """.formatted(safeName, safeOrderId);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8");

        helper.setFrom("notifications@example.com");
        helper.setTo(recipient);
        helper.setSubject("Đơn hàng " + orderId + " đã sẵn sàng");
        helper.setText(plainText, htmlText);

        ClassPathResource logo = new ClassPathResource(
                "mail/images/brand-logo.png");
        helper.addInline(LOGO_CID, logo, "image/png");

        mailSender.send(message);
    }
}
~~~

Đây là ví dụ minh họa cho resource tĩnh đã được kiểm soát trong artifact. Trong ứng dụng thật, địa chỉ người nhận và From phải được xác thực theo nghiệp vụ và cấu hình SMTP; subject cần kiểm soát ký tự điều khiển; tên và dữ liệu động cần giới hạn độ dài. HTML escaping chỉ áp dụng cho nội dung HTML, không thay thế validation recipient hoặc subject.

Một logo tĩnh không cần antivirus scan ở mỗi lần gửi nếu artifact và quy trình build đã kiểm soát nguồn của nó. Tuy nhiên, cần kiểm tra resource khi build/release và giới hạn kích thước. Với ảnh upload hoặc ảnh từ storage thay đổi được, áp dụng pipeline phê duyệt trước khi dùng.

## 15. Bảo vệ URL trong các liên kết HTML

Inline resource thường đi cùng link. Dù link không phải ảnh CID, nó vẫn là dữ liệu ngoài có thể ảnh hưởng người nhận.

Không nối URL tùy ý:

~~~java
String html = "<a href=\\"" + userProvidedUrl + "\\">Mở tài liệu</a>";
~~~

Thay vào đó:

- Tạo URL từ base URL được cấu hình tin cậy.
- Encode path segment/query parameter bằng API URI phù hợp.
- Chỉ cho phép scheme HTTPS khi link đi ra ngoài.
- Allowlist host hoặc domain theo nghiệp vụ.
- Escape HTML attribute sau khi URL đã được tạo/kiểm tra.
- Không đưa token, password hoặc dữ liệu nhạy cảm vào URL nếu có thể tránh.

Trong Thymeleaf, dùng th:href với giá trị URL đã được ứng dụng chuẩn hóa. Không coi HTML escaping là URL validation.

Nếu một template có cả CID và hyperlink, kiểm tra hai loại URI riêng: CID chỉ tham chiếu inline part trong cùng message; HTTPS dẫn đến tài nguyên web. Không dùng cùng một trường input tùy ý cho cả hai.

## 16. Quan sát và ghi log

Khi inline resource bị thiếu hoặc không hiển thị, log cần giúp xác định:

- Template key và phiên bản.
- Content-ID đã được tạo.
- Resource key nội bộ hoặc asset ID.
- Detected media type và kích thước.
- Scan status/hash/version nếu resource đến từ upload.
- Giai đoạn lỗi: resolve, read, MIME composition hoặc SMTP.

Không log byte content, URL có token, nội dung tài liệu cá nhân hoặc credential. Với URL bên ngoài, hạn chế log query string vì có thể chứa định danh hoặc bí mật.

Ví dụ log có cấu trúc:

~~~json
{
  "event": "mail_inline_resource_rejected",
  "notificationId": "order-ready-184",
  "resourceKey": "customer-logo",
  "contentType": "image/png",
  "sizeBytes": 48210,
  "reason": "SCAN_NOT_CLEAN",
  "scanStatus": "UNKNOWN"
}
~~~

Đây là ví dụ schema log do ứng dụng định nghĩa, không phải log tự sinh của Spring. Không đưa địa chỉ email đầy đủ hoặc tên khách hàng vào nếu notification ID đã đủ để tra cứu trong hệ thống có phân quyền.

### Các metric hữu ích

| Metric | Mục đích |
| --- | --- |
| Số inline resource bị từ chối theo lý do | Nhận biết loại dữ liệu không hợp lệ |
| Tỷ lệ scan CLEAN/INFECTED/ERROR | Theo dõi scanner và chất lượng upload |
| Tổng byte inline theo email | Phát hiện email quá lớn |
| Lỗi mở Resource/InputStream | Phát hiện thiếu file hoặc lỗi storage |
| Lỗi CID không có part tương ứng | Phát hiện template và MIME không đồng bộ |
| Thời gian fetch/scan/transform | Phát hiện phụ thuộc chậm hoặc xử lý quá tốn tài nguyên |

## 17. Kiểm thử resource trước khi gửi

Không cần SMTP thật để kiểm tra phần lớn quy tắc resource. Có thể kiểm tra:

1. Resource key được chọn từ allowlist.
2. Classpath resource tồn tại và đọc được.
3. Detected media type khớp policy.
4. Kích thước và kích thước pixel nằm trong giới hạn.
5. Scanner trả CLEAN cho đúng hash/object version.
6. CID được tạo và chỉ xuất hiện một lần cho mỗi inline part trong message.
7. HTML có src cid tương ứng.
8. Stream được mở đúng lúc và không bị dùng lại sau khi đóng.
9. Không có URL ngoài không được phép trong template.
10. MIME tree có inline part với Content-ID và Content-Type mong đợi.

### Test resource classpath

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;

class MailInlineResourceTest {

    @Test
    void brandLogoIsPackaged() {
        ClassPathResource logo = new ClassPathResource(
                "mail/images/brand-logo.png");

        assertTrue(logo.exists());
        assertTrue(logo.isReadable());
    }
}
~~~

Test này xác nhận resource có trên test classpath. Nếu build artifact có cấu hình resource filtering hoặc packaging đặc biệt, cần kiểm tra executable JAR được tạo ra để chắc chắn file thực sự nằm trong artifact.

### Test quyết định allowlist

~~~java
@Test
void rejectsUnsupportedMediaType() {
    assertThrows(
            IllegalArgumentException.class,
            () -> attachmentPolicy.requireAllowed(
                    "image.svg",
                    "image/svg+xml"));
}
~~~

Đây là ví dụ kiểm tra policy do ứng dụng định nghĩa. Nó không kiểm tra khả năng phát hiện của antivirus thật.

### Test scanner fail-closed

~~~java
when(malwareScanner.scan(any(InputStream.class)))
        .thenReturn(new ScanResult(ScanStatus.ERROR, "test", "v1", null));

assertThrows(
        IllegalStateException.class,
        () -> attachmentService.approve(upload));

verifyNoInteractions(mailSender);
~~~

Test này minh họa rằng scanner ERROR không được chuyển thành CLEAN và mail sender không được gọi. Cần điều chỉnh kiểu exception, service và mock theo code thật của dự án.

### Test MIME message

Có thể tạo MimeMessage trong bộ nhớ, gọi setText và addInline, rồi duyệt MIME parts để xác nhận:

- Có text/html part.
- Có inline image part.
- Content-ID khớp CID trong HTML.
- Content-Type là loại đã được phê duyệt.
- Nội dung part trùng với resource đã kiểm tra.

Nếu cần kiểm tra rendering thực tế, gửi tới SMTP capture/test server và xem raw MIME trong môi trường kiểm soát. SMTP submission thành công không chứng minh email client sẽ tải hoặc hiển thị mọi ảnh như nhau.

## 18. Những sai lầm thường gặp

### 18.1. Nhúng URL do người dùng gửi thẳng vào HTML

URL có thể trỏ tới host độc hại, endpoint nội bộ hoặc tracking server. Không cho request điều khiển src tùy ý. Dùng CID từ resource đã duyệt hoặc một host allowlist với chính sách rõ.

### 18.2. Tải URL bằng URL.openStream()

API này không tự cung cấp chính sách SSRF, redirect, timeout và giới hạn byte phù hợp. Không dùng với URL không tin cậy. Nếu cần fetch, dùng service có egress control, allowlist và giới hạn nghiêm ngặt.

### 18.3. Tin Content-Type do client khai báo

Client có thể gửi image/png cho nội dung không phải ảnh. Phát hiện định dạng từ byte content, xác minh cấu trúc và quét malware theo policy.

### 18.4. Tin phần mở rộng .png hoặc .jpg

Tên file không chứng minh nội dung. Đối chiếu extension với detected media type và allowlist.

### 18.5. Dùng SVG tùy ý làm logo inline

SVG có cấu trúc XML và khả năng tham chiếu nội dung phức tạp; hỗ trợ trong email client không đồng đều. Nếu không cần, dùng PNG/JPEG đã được kiểm tra.

### 18.6. Đưa resource path từ request vào ResourceLoader

Có thể tạo path traversal hoặc truy cập file/URL ngoài ý muốn. Dùng resource key trong allowlist, không nhận location tùy ý.

### 18.7. Tái sử dụng InputStream đã bị đóng

MimeMessage có thể đọc resource khi serialize/send. Dùng Resource hoặc InputStreamSource có thể mở stream mới; không truyền stream đã tiêu thụ.

### 18.8. Gọi addInline trước setText

Với MimeMessageHelper, đặt body trước rồi thêm inline resource theo thứ tự được khuyến nghị để helper xây dựng MIME structure phù hợp.

### 18.9. Dùng Content-ID do client cung cấp

CID là một phần của MIME header. Tạo CID từ ứng dụng, giới hạn ký tự và bảo đảm duy nhất trong message.

### 18.10. Cho rằng CID là cơ chế bảo mật

CID chỉ là định danh part MIME, không mã hóa nội dung và không kiểm soát quyền đọc. Người nhận có thể đọc source của email.

### 18.11. Không giới hạn kích thước ảnh

Ảnh lớn làm email phình lên sau Base64, tăng thời gian xử lý và có thể vượt giới hạn provider. Giới hạn byte, pixel, số lượng và tổng dung lượng.

### 18.12. Coi scanner timeout là CLEAN

Timeout, unsupported hoặc encrypted phải là ERROR/UNKNOWN. Không gửi resource chưa được xác nhận sạch.

### 18.13. Chỉ xóa metadata mà không kiểm tra output

Sau khi resize/re-encode, nội dung đã thay đổi. Kiểm tra và scan lại phiên bản cuối cùng trước khi nhúng.

### 18.14. Dùng remote tracking pixel mà không có chính sách

Ảnh từ xa có thể theo dõi việc mở email. Không thêm pixel theo dõi mặc định; phải tuân theo chính sách quyền riêng tư và lựa chọn của người nhận.

## 19. Quy trình xử lý inline resource an toàn

Một quy trình thực tế có thể được tổ chức như sau:

1. Xác định resource theo template key/asset ID đã được ứng dụng cho phép.
2. Xác thực quyền của user/tenant đối với asset.
3. Mở resource từ classpath hoặc storage nội bộ có kiểm soát.
4. Kiểm tra kích thước, định dạng thực và cấu trúc.
5. Nếu dữ liệu đến từ người dùng, quét malware và giữ quarantine đến khi có kết quả.
6. Nếu có biến đổi ảnh, kiểm tra lại output và gắn hash mới.
7. Tạo Content-ID do ứng dụng kiểm soát, duy nhất trong message.
8. Render HTML bằng template tin cậy; escape dữ liệu động theo đúng context.
9. Đặt body bằng setText trước khi addInline.
10. Gắn resource đúng byte content, MIME type và Content-ID đã duyệt.
11. Kiểm tra tổng kích thước message và gửi bằng JavaMailSender.
12. Ghi log trạng thái an toàn, xóa dữ liệu tạm theo retention.

### Quyết định nhanh theo nguồn

| Nguồn resource | Có thể dùng ngay? | Điều kiện |
| --- | --- | --- |
| Classpath logo đã review | Có, theo policy | Resource có trong artifact, định dạng/kích thước được kiểm soát |
| Object storage nội bộ | Không mặc định | Authorization, immutable version, type/size và scan state |
| User upload | Không | Quarantine, detection, validation, malware scan và approval |
| URL do request cung cấp | Không | Chỉ qua fetcher chuyên biệt với allowlist và network controls nếu thật sự cần |
| HTML có src tùy ý | Không | Sanitize/allowlist; tốt hơn là tạo CID từ resource được phê duyệt |

## 20. Câu hỏi tự kiểm tra

**1. Inline resource trong Spring Mail thường được HTML tham chiếu bằng cách nào?**

Bằng URI có scheme cid:, khớp với Content-ID của MIME part được thêm bằng MimeMessageHelper.addInline(...).

**2. Resource path do request gửi lên có thể đưa thẳng vào ResourceLoader không?**

Không. Location có thể trỏ tới file hoặc URL ngoài dự kiến. Dùng key allowlist rồi ánh xạ sang resource do ứng dụng kiểm soát.

**3. CID có phải token bảo mật không?**

Không. Nó chỉ là định danh của một MIME part trong email và có thể được người nhận đọc từ source.

**4. Tại sao không tải URL ảnh tùy ý để nhúng vào email?**

Vì ứng dụng có thể bị SSRF, tải nội dung quá lớn hoặc dữ liệu độc hại. Nếu email client tự tải URL từ xa, host đó cũng có thể nhận dữ liệu truy cập và theo dõi thời điểm mở thư.

**5. Magic bytes có chứng minh ảnh an toàn không?**

Không. Chúng giúp nhận dạng định dạng sơ bộ; vẫn cần parser/validation, giới hạn tài nguyên và malware scan khi nguồn không tin cậy.

**6. Vì sao nên ưu tiên PNG/JPEG thay cho SVG tùy ý?**

PNG/JPEG thường dễ kiểm soát hơn cho logo và hình raster; SVG có cấu trúc XML, tham chiếu phức tạp và mức hỗ trợ email client không đồng đều.

**7. Scanner không khả dụng thì có thể gửi ảnh không?**

Không nếu policy yêu cầu scan. Giữ file ở trạng thái pending/error hoặc từ chối; không coi timeout là CLEAN.

**8. Vì sao phải gắn kết quả scan với hash/version?**

Để bảo đảm byte content được gửi chính là byte content đã được kiểm tra. Nếu file thay đổi, phải scan lại.

**9. Có nên tái sử dụng InputStream đã đọc để gọi addInline không?**

Không. Stream có thể đã ở cuối hoặc đã đóng. Dùng Resource/ByteArrayResource hoặc InputStreamSource mở stream mới.

**10. Nên gọi setText hay addInline trước?**

Với MimeMessageHelper, nên đặt nội dung bằng setText trước rồi thêm inline resource.

**11. Vì sao cần giới hạn pixel của ảnh ngoài giới hạn byte?**

File nhỏ vẫn có thể khai báo chiều rộng/chiều cao rất lớn, khiến decode tốn bộ nhớ hoặc CPU.

**12. CID inline có ngăn mọi vấn đề quyền riêng tư không?**

Không. Nó tránh request tải ảnh từ xa khi hiển thị, nhưng nội dung email vẫn có thể bị đọc, chuyển tiếp hoặc lưu trữ; dữ liệu nhạy cảm vẫn phải được bảo vệ.

## Kết luận

**Bảo vệ inline resource bắt đầu từ việc kiểm soát nguồn và nội dung trước khi đưa chúng vào MIME message.** Với resource tĩnh, ưu tiên ClassPathResource có đường dẫn cố định trong artifact. Với ảnh do người dùng cung cấp, áp dụng allowlist định dạng, content detection, giới hạn kích thước/pixel, kiểm tra cấu trúc, malware scan, quarantine và phê duyệt theo hash/object version. Không tải URL hoặc resource path tùy ý; việc fetch URL có thể tạo SSRF, còn remote image trong HTML có thể làm lộ thông tin truy cập của người nhận. Tạo Content-ID từ ứng dụng, escape HTML động, dùng Resource/InputStreamSource có thể mở stream đúng lúc và gọi setText trước addInline. **MimeMessageHelper chỉ đóng gói resource; ứng dụng phải bảo đảm dữ liệu được nhúng là đúng nguồn, đúng nội dung và được phép gửi.**
