# Content sniffing

> **Chương:** Content type  
> **Bài học:** Content sniffing — cách browser nhận diện loại nội dung và phòng vệ MIME confusion  
> **Phạm vi module:** **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY** — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy (SOP), CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích MIME type và vai trò của HTTP `Content-Type`.
2. Phân biệt media type do server khai báo với content sniffing do browser thực hiện.
3. Mô tả các trường hợp browser cần nhận diện nội dung theo request destination.
4. Cấu hình `X-Content-Type-Options: nosniff` đúng mục đích và hiểu giới hạn của nó.
5. Phân biệt MIME type cho HTML, JavaScript, CSS, JSON, ảnh, font và binary.
6. Phân tích rủi ro MIME confusion, stored XSS, script execution và polyglot file.
7. Thiết kế luồng upload, download và static hosting an toàn.
8. Kết hợp MIME policy với CSP, CORS, Content-Disposition và origin isolation.
9. Kiểm tra response header và hành vi browser bằng DevTools.
10. Xây dựng checklist xử lý content type cho ứng dụng web.

## 1. Content sniffing là gì?

Khi browser nhận response HTTP, nó cần biết body là HTML, JavaScript, CSS, JSON, ảnh, font, video hay dữ liệu nhị phân. Thông tin này ảnh hưởng cách browser giải mã, hiển thị hoặc thực thi nội dung.

Server thường khai báo loại nội dung bằng header `Content-Type`. Ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8

<!doctype html>
<html lang="vi">
  <title>Trang mẫu</title>
  <p>Xin chào</p>
</html>
```

**Content sniffing** là quá trình browser suy luận loại nội dung từ bytes của response hoặc ngữ cảnh request khi cần. Browser có thể kiểm tra chữ ký file, cấu trúc ban đầu hoặc các đặc điểm của body để xác định cách xử lý.

Việc suy luận này hữu ích cho khả năng tương thích với server cũ hoặc response khai báo thiếu/sai MIME type. Nhưng nếu browser diễn giải nội dung khác với ý định của server, dữ liệu tưởng là văn bản hoặc ảnh có thể bị hiểu thành HTML/script. Sự không thống nhất này tạo ra **MIME confusion** và có thể dẫn tới XSS hoặc thực thi nội dung không mong muốn.

### 1.1. MIME type là gì?

MIME type (media type) mô tả loại representation bằng cấu trúc type/subtype, có thể kèm parameters:

```text
type/subtype; parameter=value
```

Ví dụ:

| Content-Type | Ý nghĩa |
|---|---|
| `text/html; charset=utf-8` | Tài liệu HTML |
| `text/plain; charset=utf-8` | Văn bản thuần |
| `text/css` | Stylesheet CSS |
| `text/javascript` | JavaScript |
| `application/json` | JSON |
| `image/png` | Ảnh PNG |
| `image/jpeg` | Ảnh JPEG |
| `image/svg+xml` | Tài liệu SVG |
| `application/pdf` | PDF |
| `application/octet-stream` | Dữ liệu nhị phân chung |

Tên MIME type không tự xác minh bytes thực sự có đúng định dạng hay không. Nếu server khai báo `image/png` nhưng body là HTML, browser và các intermediary có thể xử lý khác nhau tùy ngữ cảnh và policy. Vì vậy, server phải kiểm tra nội dung trước khi gắn nhãn response.

### 1.2. Content-Type và Content-Encoding là hai thứ khác nhau

- `Content-Type` mô tả loại representation sau khi giải mã content coding.
- `Content-Encoding` mô tả coding được áp dụng cho representation, ví dụ `gzip` hoặc `br`.

Ví dụ:

```http
Content-Type: application/json; charset=utf-8
Content-Encoding: br
```

Browser giải mã Brotli trước rồi xử lý body như JSON. Không khai báo `Content-Type: application/gzip` chỉ vì response được nén bằng gzip; MIME type vẫn phải mô tả nội dung gốc.

### 1.3. MIME type không phải extension

Đuôi file như `.png`, `.jpg`, `.html`, `.js` chỉ là một dấu hiệu tên gọi. Nó không chứng minh bytes của file thuộc định dạng đó.

Một file tên `avatar.png` có thể chứa HTML, SVG hoặc dữ liệu tùy ý. Nếu server tin extension do client gửi lên rồi phản hồi với MIME type tương ứng, attacker có thể lợi dụng để đưa nội dung chủ động vào luồng hiển thị.

Hãy phân biệt:

- Filename/extension: metadata do người dùng hoặc hệ thống đặt.
- MIME type: nhãn representation được server gửi.
- File signature/magic bytes: dấu hiệu định dạng bên trong bytes.
- Parser validation: kiểm tra cấu trúc thực sự bằng parser phù hợp.

Không có một phép kiểm tra đơn lẻ nào đủ để xác nhận mọi file upload an toàn.

## 2. Vì sao browser thực hiện content sniffing?

Web có lịch sử dài với server khai báo MIME type không chính xác hoặc không khai báo. Browser cần tương thích với các website đó, vì vậy một số loại request có quy tắc nhận diện nội dung riêng.

Tuy nhiên, cách xử lý phụ thuộc vào **request destination**: navigation tới document, tải script, stylesheet, image, font, media hay fetch data không nhất thiết áp dụng cùng một quy tắc.

### 2.1. Context ảnh hưởng cách diễn giải

Cùng một chuỗi bytes có thể được xử lý khác nhau tùy cách nó được tải:

- Navigation tới URL có thể tạo document để browser hiển thị.
- `<script src>` yêu cầu tài nguyên có MIME type JavaScript phù hợp.
- `<link rel="stylesheet">` yêu cầu stylesheet CSS.
- `<img>` yêu cầu dữ liệu ảnh được giải mã như image.
- Fetch/XHR trả bytes cho JavaScript; ứng dụng có thể tự parse theo API.

Do đó, không thể kết luận browser sẽ luôn sniff mọi response hoặc luôn tin `Content-Type`. Hành vi cần được đánh giá theo loại request và chuẩn/browser cụ thể.

### 2.2. Sniffing có thể tạo ranh giới diễn giải sai

Giả sử ứng dụng cho phép upload file text và lưu tại cùng origin với trang chính. Server trả:

```http
Content-Type: text/plain
```

Nếu một browser hoặc context diễn giải bytes đó theo cách khác với ý định của ứng dụng, nội dung có thể trở thành active content. Những tình huống như response khai báo sai MIME, thiếu `nosniff`, static hosting rule quá rộng hoặc nội dung polyglot làm tăng rủi ro.

Không thiết kế bảo mật dựa trên giả định rằng browser sẽ luôn giữ nội dung ở dạng text chỉ vì filename có `.txt` hoặc server đã đặt một header không nhất quán.

### 2.3. Content sniffing và XSS

MIME confusion có thể hỗ trợ nhiều dạng XSS:

- **Stored XSS qua upload:** attacker upload nội dung HTML/SVG rồi nạn nhân mở URL trên origin tin cậy.
- **MIME confusion:** server khai báo loại nội dung không khớp body và browser xử lý theo cách ngoài dự kiến.
- **Script/style confusion:** endpoint trả bytes không phải JavaScript/CSS nhưng được sử dụng trong script hoặc stylesheet context.
- **Content-type bypass:** ứng dụng dựa vào extension hoặc client-supplied Content-Type để quyết định nội dung có an toàn không.

MIME type chính xác và `nosniff` là các lớp phòng vệ quan trọng, nhưng không thay thế output encoding, sanitization, CSP hoặc tách origin cho nội dung do người dùng kiểm soát.

## 3. X-Content-Type-Options: nosniff

`X-Content-Type-Options` là response header giúp browser áp dụng kiểm tra MIME nghiêm ngặt cho một số loại request. Giá trị được chuẩn hóa là `nosniff`.

Ví dụ:

```http
X-Content-Type-Options: nosniff
```

### 3.1. nosniff làm gì?

Trong các browser hiện đại triển khai Fetch/MIME sniffing rules, `nosniff` đặc biệt quan trọng với request có destination là script hoặc stylesheet:

- Với script request, browser kiểm tra response có JavaScript MIME type phù hợp không. Nếu MIME type không hợp lệ, browser chặn thực thi.
- Với stylesheet request, browser yêu cầu MIME type CSS phù hợp, thường là `text/css`; nếu không đúng, stylesheet bị chặn.
- Browser phát thông báo lỗi MIME trong Console/DevTools để giúp chẩn đoán.

Ví dụ server trả JavaScript bytes nhưng khai báo:

```http
Content-Type: text/plain
X-Content-Type-Options: nosniff
```

Khi tài nguyên được dùng làm script, browser chặn việc thực thi vì MIME type không phải JavaScript MIME type được chấp nhận.

### 3.2. nosniff không phải công tắc tắt mọi sniffing

Không diễn giải `nosniff` như một bảo đảm rằng browser sẽ không bao giờ suy luận loại nội dung trong mọi context. Quy tắc cụ thể phụ thuộc request destination và browser implementation; header chủ yếu tạo strict MIME checking cho script và stylesheet.

Nó cũng không:

- Xác minh file upload có đúng định dạng được khai báo.
- Làm HTML upload trở thành text thuần trong mọi navigation.
- Ngăn JavaScript hợp lệ đã được tải và thực thi đọc DOM.
- Thay thế CSP, output encoding, sanitization hoặc origin isolation.
- Xóa nội dung đã được cache hay đã lưu trong application storage.

Với file do user upload, vẫn cần xác thực nội dung, đặt MIME type phù hợp, quyết định inline/download và cân nhắc phục vụ từ origin riêng.

### 3.3. Nên gửi nosniff ở đâu?

Có thể áp dụng trên toàn bộ response web nếu ứng dụng đã khai báo MIME type đúng. Ít nhất, hãy áp dụng nhất quán cho:

- JavaScript và CSS.
- JSON/API response.
- File upload/download.
- Static asset.
- HTML document và các route phục vụ nội dung do user kiểm soát.

Ví dụ cấu hình response:

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
X-Content-Type-Options: nosniff
Cache-Control: no-store
```

Đặt header ở application server, reverse proxy hoặc CDN theo một policy thống nhất. Sau khi triển khai, kiểm tra response thực tế vì proxy hoặc edge rule có thể ghi đè hoặc loại bỏ header.

## 4. Khai báo MIME type đúng cho từng loại nội dung

MIME type cần phản ánh bytes mà server thực sự gửi. Đừng chọn MIME type dựa riêng vào URL extension, request header do client gửi hoặc dữ liệu form.

### 4.1. HTML

Dùng:

```http
Content-Type: text/html; charset=utf-8
X-Content-Type-Options: nosniff
```

HTML là active content: browser parse markup, tạo DOM và có thể chạy script theo policy. Nếu nội dung HTML đến từ user, không phục vụ nó như trang cùng origin đáng tin cậy nếu chưa sanitization và thiết kế isolation phù hợp.

### 4.2. JavaScript

Dùng MIME type JavaScript được browser công nhận, thông dụng là:

```http
Content-Type: text/javascript; charset=utf-8
X-Content-Type-Options: nosniff
```

Nếu server trả file JavaScript với `text/plain`, `application/octet-stream` hoặc một MIME không phải JavaScript, browser có thể chặn script khi strict MIME checking được áp dụng. Sửa response header tại nơi phục vụ file thay vì bỏ `nosniff` để làm script chạy.

Không dùng `application/json` hoặc `text/html` để phục vụ JavaScript chỉ vì body là text.

### 4.3. CSS

Dùng:

```http
Content-Type: text/css; charset=utf-8
X-Content-Type-Options: nosniff
```

Nếu stylesheet trả MIME type khác `text/css`, browser có thể từ chối stylesheet. Kiểm tra URL, response header, CDN metadata và Console thay vì xóa `nosniff`.

### 4.4. JSON

Dùng:

```http
Content-Type: application/json; charset=utf-8
X-Content-Type-Options: nosniff
```

JSON là data format, không phải HTML document. Client nên parse bằng `response.json()` hoặc JSON parser phù hợp; không đưa JSON string vào `innerHTML`.

Không trả API JSON dưới `text/html` chỉ để tránh lỗi client. Nếu API trả dữ liệu cá nhân, đặt thêm cache policy phù hợp như `Cache-Control: no-store` hoặc `private, no-cache` theo threat model.

### 4.5. Image và SVG

Dùng MIME type khớp định dạng:

```http
Content-Type: image/png
X-Content-Type-Options: nosniff
```

`image/svg+xml` là SVG, một định dạng dựa trên XML có khả năng chứa nội dung chủ động trong một số cách sử dụng. Không coi SVG upload là ảnh bitmap vô hại.

Nếu chỉ cần hiển thị ảnh upload, có thể decode rồi re-encode thành PNG/JPEG/WebP bằng thư viện ảnh tin cậy, bỏ metadata không cần thiết và phục vụ bản đã xử lý. Nếu phải giữ SVG, cần sanitize bằng parser/library phù hợp, giới hạn tính năng và phục vụ theo kiến trúc origin an toàn.

### 4.6. Binary và tài liệu

Với dữ liệu không có MIME type cụ thể hoặc không muốn browser render inline, `application/octet-stream` thường là lựa chọn generic. PDF có thể dùng `application/pdf`; font, audio và video cần MIME type tương ứng.

Kết hợp với `Content-Disposition: attachment` nếu mục tiêu là tải file. MIME type và disposition giải quyết hai câu hỏi khác nhau: loại dữ liệu là gì và browser được đề nghị hiển thị inline hay tải xuống.

## 5. Content sniffing trong các request destination

Một response không được xử lý giống nhau ở mọi vị trí. Hãy hiểu request destination trước khi phân tích MIME error hoặc chọn header.

### 5.1. Script destination

Ví dụ:

```html
<script src="/assets/app.js"></script>
```

Browser mong đợi JavaScript. Với `nosniff`, response có MIME type không được công nhận là JavaScript sẽ bị chặn. Với module script, browser vốn áp dụng MIME checking nghiêm ngặt theo module loading rules.

Không phục vụ upload của user từ một URL có thể được nhúng như script. Không cho phép attacker điều khiển response body hoặc MIME type của endpoint dùng làm script.

### 5.2. Style destination

Ví dụ:

```html
<link rel="stylesheet" href="/assets/site.css">
```

Browser yêu cầu CSS. Nếu response trả `text/plain` hoặc HTML error page nhưng URL kết thúc bằng `.css`, stylesheet có thể bị chặn khi strict MIME checking áp dụng.

Kiểm tra cả status code. Một số lỗi CDN/authentication trả HTML login page cho URL CSS; lỗi thực sự nằm ở routing/session hoặc deployment, không phải lý do để nới MIME policy.

### 5.3. Image destination

Ví dụ:

```html
<img src="/uploads/avatar.png" alt="Ảnh đại diện">
```

Browser giải mã nội dung như image theo quy tắc image destination. Dù vậy, upload validation vẫn cần kiểm tra định dạng thật và xử lý an toàn. Không giả định nội dung có thể nhúng bằng `<img>` sẽ an toàn nếu được mở trực tiếp như document hoặc được dùng trong context khác.

SVG đặc biệt cần xem xét vì có thể được điều hướng tới như document và có các tính năng vượt quá bitmap image.

### 5.4. Navigation/document destination

Khi người dùng mở URL trực tiếp hoặc click link, browser có thể tạo document. Cách xử lý navigation có quy tắc riêng và không nên suy luận chỉ từ hành vi của `<script>` hoặc `<img>`.

`nosniff` không thay thế việc đặt đúng `Content-Type` cho document. Nếu muốn người dùng tải nội dung do user cung cấp, hãy dùng `Content-Disposition: attachment`, MIME type phù hợp và origin tách biệt khi cần.

### 5.5. Fetch/XHR destination

Fetch thường cung cấp response body cho JavaScript. Ứng dụng quyết định cách parse qua `response.json()`, `response.text()`, `response.blob()` hoặc `response.arrayBuffer()`.

Không dựa vào việc `fetch()` đã thành công để kết luận response đúng MIME hoặc an toàn. Kiểm tra status, Content-Type và schema; sau đó parse dữ liệu theo định dạng mong đợi. CORS chỉ quyết định script có được phép đọc response cross-origin; nó không xác minh MIME/body là an toàn.

## 6. Rủi ro từ file upload và nội dung do người dùng kiểm soát

Upload endpoint là nơi MIME confusion dễ xuất hiện vì người dùng kiểm soát filename, extension, metadata và bytes gửi lên. Header `Content-Type` trong multipart request cũng do client cung cấp và có thể giả mạo.

### 6.1. Không tin Content-Type do client gửi

Một multipart upload có thể chứa:

```http
Content-Disposition: form-data; name="file"; filename="avatar.png"
Content-Type: image/png

<bytes do client gửi>
```

Giá trị `image/png` ở đây không chứng minh file thực sự là PNG. Attacker có thể gửi HTML hoặc SVG nhưng khai báo `image/png`, hoặc đổi tên file thành `.png`.

Server phải tự xác định định dạng bằng allowlist, kiểm tra signature và parse nội dung bằng thư viện phù hợp. Client-side validation chỉ hỗ trợ trải nghiệm, không tạo ranh giới tin cậy.

### 6.2. Quy trình upload an toàn

Một pipeline thực tế có thể gồm:

1. Chỉ cho phép các định dạng nghiệp vụ thực sự cần.
2. Giới hạn kích thước, số lượng, tốc độ upload và tổng quota.
3. Chuẩn hóa filename; không dùng filename client làm đường dẫn lưu trữ.
4. Xác định loại file từ bytes bằng thư viện tin cậy.
5. Parse/decode file để xác minh cấu trúc thực tế.
6. Từ chối file không khớp allowlist hoặc có cấu trúc bất thường.
7. Với ảnh, cân nhắc decode rồi re-encode để loại bỏ payload/metadata không cần.
8. Lưu file ngoài webroot hoặc trong object storage không tự thực thi.
9. Sinh storage key ngẫu nhiên và kiểm soát authorization khi tải.
10. Khi phục vụ, tự gán Content-Type đã xác minh và security headers phù hợp.

Magic bytes là một tín hiệu, không phải bằng chứng tuyệt đối. File polyglot có thể hợp lệ với nhiều parser hoặc có bytes đầu phù hợp nhưng cấu trúc còn lại độc hại. Cần kết hợp parser validation, allowlist và cách phục vụ an toàn.

### 6.3. SVG, HTML và XML cần xử lý riêng

SVG có thể chứa markup, event handler và khả năng tham chiếu tài nguyên. HTML và XML cũng có thể kích hoạt parser hoặc tính năng chủ động khi browser mở chúng như document.

Nếu ứng dụng chỉ cần thumbnail, rasterize SVG thành bitmap ở server bằng công cụ tin cậy. Nếu phải cho phép SVG/HTML preview, dùng sanitizer chuyên dụng, loại bỏ tính năng không cần thiết và phục vụ từ origin cách ly.

Không xem việc file được hiển thị bên trong `<img>` là bằng chứng rằng cùng URL đó an toàn khi người dùng mở trực tiếp trong tab mới.

### 6.4. File upload không nên dùng chung trust boundary với ứng dụng

Nếu user upload HTML rồi file được phục vụ từ cùng origin với trang chính, document đó có thể nhận quyền của origin ứng dụng khi được mở trực tiếp. Tùy cookie scope và kiến trúc, nội dung chủ động có thể tương tác với tài nguyên hoặc session của ứng dụng.

Ưu tiên phục vụ nội dung user từ một site riêng biệt (khác registrable domain) không nhận cookie đăng nhập của ứng dụng. Không đặt cookie với `Domain` quá rộng nếu không cần; dùng host-only cookie cho ứng dụng. Kiểm soát CORS và các quyền truy cập tài nguyên trên origin upload.

Origin riêng tạo thêm ranh giới cho DOM, storage và same-origin access. Nó không thay thế kiểm tra quyền tải file hoặc xác thực nội dung.

## 7. Phục vụ file và download an toàn

Khi trả file cho browser, server cần quyết định MIME type và disposition một cách độc lập.

### 7.1. Content-Disposition: inline và attachment

- `inline`: cho browser cơ hội hiển thị nội dung theo MIME type và khả năng hỗ trợ.
- `attachment`: đề nghị browser tải file xuống thay vì hiển thị trực tiếp.

Ví dụ download:

```http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="download.bin"
X-Content-Type-Options: nosniff
```

Với PDF đã được xác minh và muốn hiển thị inline, server có thể dùng `Content-Type: application/pdf` cùng `Content-Disposition: inline`. Với file user upload không tin cậy, ưu tiên attachment hoặc preview trong sandbox/origin riêng.

`attachment` không phải bảo đảm browser sẽ không bao giờ xử lý file theo cách khác sau khi tải xuống hoặc khi người dùng mở file. Hãy thiết kế cả quy trình lưu trữ và mở file an toàn.

### 7.2. Filename trong Content-Disposition

Không nối trực tiếp filename do client gửi vào response header. Loại bỏ CR/LF, path separator và ký tự điều khiển; dùng thư viện chuẩn để encode filename và hỗ trợ `filename*` khi cần Unicode.

Ví dụ:

```http
Content-Disposition: attachment; filename="report.pdf"; filename*=UTF-8''bao-cao.pdf
```

Filename chỉ là nhãn hiển thị. Không dùng nó làm storage path, authorization key hoặc bằng chứng định dạng.

### 7.3. Header cho nội dung user upload

Một response download có thể dùng:

```http
Content-Type: application/octet-stream
Content-Disposition: attachment
X-Content-Type-Options: nosniff
Cache-Control: private, no-store
```

Chọn MIME type đã xác minh nếu browser cần preview định dạng cụ thể. Nếu response nhạy cảm hoặc có kiểm soát truy cập, cache policy phải phù hợp với session và authorization.

### 7.4. Preview nội dung không tin cậy

Nếu sản phẩm cần preview HTML/SVG/PDF hoặc tài liệu do user cung cấp:

- Phục vụ preview từ origin/site riêng.
- Dùng iframe `sandbox` với quyền tối thiểu.
- Thêm CSP phù hợp, có thể dùng `sandbox` và `default-src 'none'` cho nội dung không cần tài nguyên ngoài.
- Không cấp `allow-same-origin` hoặc `allow-scripts` nếu chức năng không cần.
- Không truyền session cookie của ứng dụng vào preview origin.
- Giới hạn network access và nguồn tài nguyên.
- Cung cấp đường download riêng nếu người dùng muốn lấy file gốc.

Ví dụ policy chặt cho một trang preview đơn giản:

```http
Content-Security-Policy: sandbox; default-src 'none'; img-src data: blob:
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
```

CSP sandbox là lớp bổ sung. Cần thử nội dung thực tế vì preview có thể cần các directive cụ thể hơn.

## 8. Kết hợp MIME policy với security headers

MIME type chính xác là nền tảng; các security headers bổ sung ranh giới xử lý cho browser.

### 8.1. Header nền tảng

Ví dụ cho response web thông thường:

```http
Content-Type: text/html; charset=utf-8
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
```

`Content-Type` mô tả document; `nosniff` yêu cầu strict MIME handling cho các request destination được áp dụng; `Referrer-Policy` giảm thông tin URL nguồn được gửi đi.

### 8.2. CSP giảm khả năng thực thi ngoài dự kiến

CSP có thể giới hạn nguồn script, style, frame và kết nối:

```http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
```

CSP không sửa MIME type sai. `nosniff` không thay thế CSP. Nếu script được phép tải và MIME hợp lệ, CSP vẫn cần quyết định script đó có được phép chạy hay không.

### 8.3. CORS không xác minh nội dung

CORS điều khiển JavaScript có thể đọc response cross-origin hay không. Nó không chứng minh response là JSON, ảnh hoặc script an toàn; cũng không ngăn mọi request được gửi tới server.

Nếu API trả JSON, khai báo `application/json`, kiểm tra authorization và chỉ bật CORS cho origin được phép. Không dùng `Access-Control-Allow-Origin: *` như cách xử lý MIME confusion.

### 8.4. CORP và cross-origin resource loading

`Cross-Origin-Resource-Policy` (CORP) có thể giới hạn context nào được phép tải response như một resource. Nó hữu ích khi bảo vệ tài nguyên nhạy cảm khỏi việc bị nhúng cross-origin trong một số context.

Ví dụ:

```http
Cross-Origin-Resource-Policy: same-origin
```

CORP không thay MIME type hoặc `nosniff`, và không phải biện pháp chống XSS trong cùng origin. Chỉ bật policy phù hợp với cách ứng dụng thực sự chia sẻ ảnh, font hoặc API resource.

## 9. Thiết kế static hosting và file service

Static hosting thường ánh xạ URL extension sang MIME type. Cấu hình sai có thể làm browser nhận response với MIME không phù hợp hoặc biến route động thành nơi phục vụ nội dung do user kiểm soát.

### 9.1. Dùng MIME map do hệ thống quản lý

- Dùng MIME map được duy trì bởi framework, web server hoặc object storage.
- Giữ map nhất quán giữa development, staging, production và CDN.
- Không để client gửi MIME type tùy ý rồi ghi thẳng vào object metadata.
- Không dùng extension làm nguồn xác thực duy nhất.
- Với định dạng không được hỗ trợ, từ chối hoặc phục vụ dưới dạng download generic.

### 9.2. Kiểm tra lỗi static hosting

Một file JavaScript có thể trả về HTML error page vì route rewrite, login redirect hoặc CDN fallback. Browser sau đó báo MIME mismatch khi script được tải.

Khi gặp lỗi, kiểm tra:

1. Request URL có đúng không?
2. Status code là 200, 301/302 hay lỗi 4xx/5xx?
3. Response body thực tế là JavaScript hay HTML error page?
4. Header Content-Type có đúng MIME không?
5. CDN có trả cache cũ hoặc rewrite sang index.html không?
6. `nosniff` có chặn đúng response sai MIME không?

Đừng xóa `nosniff` để che lỗi deployment. Sửa route, response body hoặc MIME mapping tại nguồn.

### 9.3. Không phục vụ user content từ asset path đáng tin

Tránh để upload user có thể ghi vào thư mục hoặc URL prefix vốn được dùng cho script, stylesheet hoặc HTML của ứng dụng. Static asset cần có nguồn build/deploy đáng tin cậy và quyền ghi tách biệt với upload service.

Dùng object storage/bucket riêng, storage key do server sinh và route phục vụ file có authorization rõ ràng.

## 10. MIME confusion và polyglot file

Polyglot là file được tạo sao cho nhiều parser có thể nhận diện hoặc xử lý cùng một tập bytes theo những định dạng khác nhau. Ví dụ một file có thể chứa cấu trúc hợp lệ đối với image parser và đồng thời có phần bytes được HTML parser diễn giải.

### 10.1. Vì sao extension và magic bytes chưa đủ?

- Extension có thể đổi tên.
- Multipart Content-Type do client khai báo.
- Magic bytes có thể bị giả mạo hoặc chỉ xác nhận phần đầu file.
- Một số định dạng có container/metadata linh hoạt.
- Parser khác nhau có thể chấp nhận những cấu trúc khác nhau.

Hãy parse bằng thư viện chuyên dụng và xử lý theo định dạng mà sản phẩm thực sự cần. Với ảnh, decode rồi re-encode thường giảm nhiều loại payload và metadata không cần thiết, nhưng cần thư viện được cập nhật và giới hạn tài nguyên.

### 10.2. Content-type confusion trong route download

Nếu một route trả nội dung user-controlled và server tự chọn MIME type theo extension, attacker có thể khiến browser mở nội dung dưới dạng active document.

Ví dụ logic nguy hiểm:

```text
mimeType = lookupMimeType(filenameFromUser)
return response(bodyFromUser, Content-Type = mimeType)
```

Logic này tin filename do client kiểm soát. Hãy xác định MIME type từ nội dung đã kiểm tra và dùng route download riêng với `Content-Disposition: attachment` khi không cần inline rendering.

### 10.3. Không dùng file upload để chạy script ứng dụng

Không cho upload ghi vào thư mục chứa JavaScript/CSS được app import hoặc route có thể tải bằng `<script>`. Nếu có nhu cầu user tạo theme/template, xử lý chúng bằng pipeline kiểm duyệt/sanitization và sandbox riêng.

Không cho phép người dùng đặt `Content-Type: text/javascript` hoặc `text/html` vào object metadata để quyết định cách browser thực thi. Metadata phục vụ phải do server quản lý.

## 11. JSON, API và content-type confusion

API thường trả JSON nhưng có thể bị cấu hình sai thành `text/html`, `text/plain` hoặc `application/octet-stream`.

### 11.1. Trả đúng application/json

Ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
X-Content-Type-Options: nosniff
Cache-Control: no-store

{"ok":true,"count":3}
```

Client có thể kiểm tra media type trước khi parse:

```js
const response = await fetch('/api/items');

if (!response.ok) {
  throw new Error('API request failed');
}

const contentType = response.headers.get('content-type') || '';
const mediaType = contentType.split(';', 1)[0].trim().toLowerCase();

const isJsonMediaType =
  mediaType === 'application/json' ||
  (mediaType.startsWith('application/') && mediaType.endsWith('+json'));

if (!isJsonMediaType) {
  throw new TypeError('Unexpected response media type');
}

const data = await response.json();
```

`application/problem+json` và các media type dạng `application/*+json` có thể là JSON-based format. Sau khi parse, vẫn cần validate schema và kiểm tra dữ liệu trước khi dùng.

### 11.2. Không đưa JSON vào HTML sink

Không đưa JSON string vào `innerHTML`, `outerHTML` hoặc các DOM sink tương tự. Dùng `textContent` để hiển thị text hoặc tạo DOM node theo cấu trúc đã kiểm soát.

Nếu API trả nội dung do user nhập, encode theo context khi render. MIME type `application/json` không tự làm các string bên trong trở nên an toàn khi đưa vào HTML.

### 11.3. Không nhầm CORS với MIME validation

Fetch cross-origin có thể bị CORS chặn JavaScript đọc response, nhưng server vẫn nhận request. Khi CORS cho phép đọc response, ứng dụng vẫn phải kiểm tra status, Content-Type, schema và dữ liệu.

CORS không xác minh response body là JSON thật và không thay `nosniff`.

## 12. Content sniffing, CSP và các cơ chế phòng vệ liên quan

Mỗi lớp giải quyết một phần khác nhau của vấn đề:

| Cơ chế | Vai trò |
|---|---|
| Content-Type | Khai báo loại representation |
| X-Content-Type-Options: nosniff | Strict MIME checking cho các request destination được áp dụng |
| CSP | Giới hạn nguồn và hành vi tài nguyên/document |
| CORS | Kiểm soát JavaScript đọc response cross-origin |
| CORP | Giới hạn việc resource được tải từ context cross-origin |
| Content-Disposition | Đề nghị browser hiển thị inline hoặc tải xuống |
| Origin isolation | Tách quyền DOM, storage và cookie theo site/origin |
| Upload validation | Kiểm tra định dạng và cấu trúc file trước khi lưu/phục vụ |

Không một header đơn lẻ nào giải quyết toàn bộ MIME confusion. Ví dụ, `nosniff` không làm sạch HTML upload; CSP không xác minh file là PNG; `Content-Disposition: attachment` không thay thế authorization hoặc kiểm tra file.

## 13. Troubleshooting MIME mismatch

Lỗi MIME thường là dấu hiệu server trả sai response, route rewrite nhầm hoặc static asset được cấu hình không nhất quán.

### 13.1. Script bị chặn vì MIME type

Thông báo Console có thể cho biết browser từ chối thực thi script vì MIME type không hợp lệ khi `nosniff` được bật.

Kiểm tra:

- Response có đúng JavaScript bytes không?
- Content-Type có phải JavaScript MIME type không?
- Có bị redirect tới trang login hoặc HTML error page không?
- CDN có trả response cache cũ không?
- Static host có ánh xạ extension `.js` đúng không?

Sửa MIME mapping hoặc route. Không bỏ `nosniff` để browser chấp nhận response sai MIME.

### 13.2. Stylesheet bị từ chối

Browser có thể báo stylesheet không phải MIME type CSS. Kiểm tra response header có `text/css`, status code có thành công và body có phải CSS hay HTML error page.

Nếu CSS được build thành file hash, kiểm tra manifest và đường dẫn deploy có khớp không. Nếu CDN trả index.html cho mọi URL không tồn tại, sửa fallback rule để asset missing trả 404 thay vì HTML 200.

### 13.3. JSON parser báo lỗi

Nếu `response.json()` thất bại:

1. Xem status code.
2. Xem Content-Type.
3. Xem response body có phải JSON hay HTML login/error page.
4. Kiểm tra charset và encoding.
5. Kiểm tra server có thêm text/debug output trước JSON không.

Không sửa bằng cách parse mọi response dưới dạng text rồi dùng `eval`. JSON phải được parse bằng JSON parser và schema cần được kiểm tra.

### 13.4. Upload hiển thị như HTML

Nếu file upload được mở thành document:

- Kiểm tra Content-Type và Content-Disposition.
- Kiểm tra file có được phục vụ từ cùng origin với app không.
- Kiểm tra user-controlled metadata có quyết định MIME type không.
- Kiểm tra CDN/object storage có override header không.
- Chuyển sang download attachment hoặc preview ở origin cách ly.
- Nếu là ảnh, cân nhắc rasterize/re-encode.

Không dựa vào filename extension hoặc việc upload được chấp nhận để kết luận nội dung an toàn.

## 14. Thực hành A — Quan sát MIME type và nosniff

Dùng local server hoặc staging do bạn kiểm soát. Tạo một file JavaScript test có nội dung vô hại:

```js
console.log('MIME test loaded');
```

1. Phục vụ file với `Content-Type: text/javascript`.
2. Thêm `X-Content-Type-Options: nosniff`.
3. Nhúng file vào trang test bằng `<script src>`.
4. Mở DevTools → Network và xác minh response headers.
5. Xác minh script chạy và log xuất hiện.
6. Đổi Content-Type thành `text/plain`, giữ `nosniff`.
7. Tải lại trang và xem Console; browser phải từ chối script vì MIME không phù hợp.
8. Đổi lại MIME type chính xác và xác minh lỗi biến mất.

Kết quả mong đợi: thấy `nosniff` thực thi strict MIME check cho script destination.

## 15. Thực hành B — Kiểm tra stylesheet MIME

1. Tạo stylesheet đơn giản đổi màu nền một vùng test.
2. Phục vụ file với `Content-Type: text/css` và `nosniff`.
3. Dùng `<link rel="stylesheet">` để tải file.
4. Xác minh stylesheet được áp dụng.
5. Đổi response thành `text/plain` hoặc trả HTML error page.
6. Tải lại và quan sát browser từ chối stylesheet.
7. Sửa MIME mapping và xác minh CSS hoạt động trở lại.

Không xóa `nosniff` để làm stylesheet chạy. Hãy sửa response type tại server/CDN.

## 16. Thực hành C — Upload và download file an toàn

Dùng một ứng dụng staging với file giả lập, không có dữ liệu thật.

1. Upload một ảnh PNG hợp lệ.
2. Upload một file text đã đổi tên thành `.png` và khai báo multipart Content-Type giả.
3. Xác minh server không tin MIME type hoặc extension do client gửi.
4. Kiểm tra parser/signature validation và giới hạn kích thước.
5. Xác minh server gán Content-Type từ kết quả kiểm tra.
6. Tải file không tin cậy và kiểm tra `Content-Disposition`, `nosniff` và cache policy.
7. Xác minh filename được encode an toàn và không thể chèn CR/LF vào header.
8. Kiểm tra URL file được phục vụ từ origin/site upload riêng nếu sản phẩm hỗ trợ.

Kết quả mong đợi: file không khớp định dạng bị từ chối hoặc được phục vụ như download generic; nội dung user không được thực thi như document tin cậy.

## 17. Thực hành D — Kiểm tra static hosting và API

1. Mở một JavaScript asset và một CSS asset từ staging.
2. Xác minh status, body, Content-Type và `X-Content-Type-Options`.
3. Tạo URL asset không tồn tại và kiểm tra server trả 404 thay vì fallback HTML 200.
4. Gọi API JSON và kiểm tra `application/json; charset=utf-8`.
5. Thử response HTML login/error tại URL API và xác minh client không parse nhầm thành JSON.
6. Kiểm tra CDN không override MIME type hoặc xóa `nosniff`.
7. Thử request cross-origin trong môi trường được kiểm soát và phân biệt lỗi CORS với lỗi MIME.
8. Ghi lại kết quả theo browser/version.

Không thử upload HTML/SVG độc hại vào hệ thống production. Dùng file test vô hại và staging.

## 18. Checklist review Content sniffing

| Hạng mục | Câu hỏi cần trả lời |
|---|---|
| Content-Type | Mỗi response có khai báo MIME type đúng với bytes? |
| Charset | Text/HTML/JSON có charset rõ ràng và thống nhất UTF-8? |
| Content-Encoding | Compression có tách biệt với MIME type? |
| nosniff | Response có X-Content-Type-Options: nosniff? |
| Script | JavaScript asset có MIME type được browser công nhận? |
| Stylesheet | CSS asset có trả text/css? |
| JSON | API có trả application/json hoặc media type +json phù hợp? |
| Upload | Server có bỏ qua client-supplied MIME type và extension khi xác thực? |
| File parser | Có kiểm tra signature và parse/decode file bằng thư viện phù hợp? |
| Polyglot | Có xử lý file đa định dạng hoặc cấu trúc bất thường? |
| SVG/HTML | Nội dung chủ động có được sanitize/rasterize và cô lập? |
| Storage | Upload có nằm ngoài webroot và không ghi vào asset path? |
| Origin | User content có được phục vụ từ site riêng không nhận app session cookie? |
| Download | Content-Disposition có phù hợp với inline/attachment? |
| Filename | Filename có được encode và loại bỏ CR/LF/path traversal? |
| Cache | File nhạy cảm có cache policy phù hợp? |
| CSP | Preview có sandbox/CSP tối thiểu? |
| CORS/CORP | Cross-origin access và resource loading có allowlist phù hợp? |
| CDN | Edge có giữ nguyên Content-Type và security headers? |
| Testing | Đã kiểm tra script, stylesheet, image, navigation và fetch destination? |
| Monitoring | Có log MIME mismatch và phát hiện upload bất thường? |

## 19. Câu hỏi tự kiểm tra

**1.** Content sniffing là gì?  
**Đáp án:** Browser suy luận loại nội dung từ bytes hoặc ngữ cảnh request khi cần xác định cách xử lý response.

**2.** Header nào khai báo MIME type của response?  
**Đáp án:** `Content-Type`.

**3.** Content-Type khác Content-Encoding thế nào?  
**Đáp án:** Content-Type mô tả representation; Content-Encoding mô tả coding như gzip hoặc Brotli được áp dụng lên representation.

**4.** Vì sao không tin Content-Type trong multipart upload?  
**Đáp án:** Client kiểm soát giá trị đó và có thể khai báo sai so với bytes thực tế.

**5.** X-Content-Type-Options: nosniff có tác dụng chính gì?  
**Đáp án:** Yêu cầu browser strict MIME checking, đặc biệt chặn script/stylesheet request có MIME type không phù hợp.

**6.** nosniff có tắt mọi content sniffing trong mọi navigation không?  
**Đáp án:** Không. Quy tắc phụ thuộc request destination; header chủ yếu có tác dụng strict MIME checking cho script và stylesheet.

**7.** MIME type thường dùng cho CSS là gì?  
**Đáp án:** `text/css`.

**8.** MIME type thông dụng cho JavaScript là gì?  
**Đáp án:** `text/javascript`.

**9.** Vì sao SVG upload cần được xử lý cẩn thận?  
**Đáp án:** SVG là định dạng dựa trên XML và có thể chứa nội dung chủ động khi được mở như document.

**10.** Content-Disposition: attachment giải quyết điều gì?  
**Đáp án:** Đề nghị browser tải file xuống thay vì hiển thị inline; nó không thay thế xác thực file hoặc authorization.

**11.** Vì sao nên phục vụ user upload từ origin riêng?  
**Đáp án:** Để nội dung chủ động do user kiểm soát không cùng trust boundary với ứng dụng và session của ứng dụng.

**12.** CORS có xác minh response body là JSON thật không?  
**Đáp án:** Không. CORS kiểm soát việc đọc response cross-origin; ứng dụng vẫn phải kiểm tra Content-Type, parse và validate schema.

## Ghi nhớ

**Content sniffing là việc browser suy luận loại nội dung khi xử lý response; MIME confusion xuất hiện khi cách browser diễn giải khác với ý định của server.** Luôn khai báo `Content-Type` chính xác, tách biệt nó với `Content-Encoding` và gửi `X-Content-Type-Options: nosniff` để browser strict MIME checking cho script/stylesheet.

Không tin extension hoặc multipart Content-Type do client gửi. Xác minh file bằng allowlist, signature và parser phù hợp; cân nhắc rasterize ảnh, sanitize SVG và phục vụ nội dung user từ origin/site riêng. Dùng `Content-Disposition: attachment` cho download không cần inline, CSP sandbox cho preview và kiểm tra static hosting/CDN để tránh trả HTML error page dưới URL script/CSS. `nosniff`, CSP, CORS, CORP và origin isolation bổ trợ nhau; không cơ chế nào thay thế xác thực nội dung, authorization và kiểm thử browser thực tế.
