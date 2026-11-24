# Header MIME an toàn

**MIME type** cho browser biết response chứa loại nội dung nào để chọn cách xử lý phù hợp: hiển thị HTML, giải mã ảnh, áp dụng stylesheet, thực thi JavaScript hay tải file. Nếu server khai báo sai hoặc bỏ trống Content-Type, browser có thể phải suy đoán định dạng từ byte của response. Quá trình này gọi là **MIME sniffing**. Trong một số ngữ cảnh, suy đoán sai có thể khiến dữ liệu người dùng tải lên bị diễn giải thành HTML hoặc script và dẫn tới XSS.

Header **X-Content-Type-Options: nosniff** yêu cầu browser không thực hiện MIME sniffing trong các trường hợp được chuẩn hóa cho script và stylesheet: nếu MIME type khai báo không phù hợp với loại tài nguyên được yêu cầu, browser chặn việc tải tài nguyên đó. Đây là lớp phòng vệ quan trọng, nhưng không tự sửa Content-Type sai và cũng không phải công tắc tắt mọi dạng sniffing cho mọi navigation/download.

Một ứng dụng an toàn cần chọn MIME type đúng ở server, gửi nosniff, kiểm soát file upload, tách nội dung không tin cậy khỏi origin có cookie đăng nhập và dùng Content-Disposition phù hợp khi tải file. CORS không thay thế các biện pháp này: CORS kiểm soát việc script đọc response cross-origin; nó không quyết định browser phải diễn giải một file là HTML, CSS hay JavaScript.

Bài học thuộc chương **Content type** trong module **Browser Security** (SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY). Nội dung phân tích ranh giới giữa browser, origin, response header và ứng dụng web; tập trung vào MIME type, MIME sniffing, X-Content-Type-Options, script/style strict MIME checks, upload/download, SVG, polyglot file và kiểm chứng bằng DevTools.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích MIME type và vai trò của Content-Type trong HTTP response.
2. Phân biệt Content-Type, Accept và Content-Encoding.
3. Nhận diện MIME sniffing và các tình huống browser phải suy đoán nội dung.
4. Giải thích X-Content-Type-Options: nosniff và phạm vi áp dụng của nó.
5. Chọn MIME type phù hợp cho HTML, JavaScript, CSS, JSON, SVG, ảnh và binary download.
6. Phân biệt strict MIME checking cho script/style với cách browser xử lý navigation và download.
7. Giải thích vì sao file upload và client-supplied Content-Type không đáng tin.
8. Phân tích nguy cơ XSS khi file HTML/SVG được phục vụ cùng origin với ứng dụng.
9. Kết hợp nosniff, Content-Disposition, CSP và origin riêng để phục vụ file không tin cậy.
10. Dùng Node.js lab để kiểm chứng response đúng/sai MIME và quan sát browser chặn script/stylesheet.

## 2. MIME type là gì?

MIME type (media type) mô tả định dạng của representation được truyền trong HTTP. Cấu trúc cơ bản là type/subtype, có thể kèm tham số:

~~~http
Content-Type: text/html; charset=utf-8
~~~

Trong ví dụ:

- text là type.
- html là subtype.
- charset=utf-8 là parameter mô tả encoding ký tự.

MIME type essence là cặp type/subtype sau khi chuẩn hóa, không bao gồm parameter. Browser và các API web dùng MIME type essence để so sánh loại nội dung.

### 2.1. Các MIME type thường gặp

| Nội dung | MIME type thường dùng | Ghi chú |
| --- | --- | --- |
| HTML | text/html; charset=utf-8 | Browser parse thành document HTML |
| JavaScript | text/javascript | MIME type JavaScript chuẩn hiện hành |
| CSS | text/css | Stylesheet cần MIME type CSS |
| JSON | application/json | API JSON nên trả đúng media type |
| XML | application/xml | XML tổng quát; có các subtype riêng |
| SVG | image/svg+xml | SVG là XML-based image, có thể chứa active content khi mở như document |
| PNG | image/png | Raster image |
| JPEG | image/jpeg | Raster image |
| WebP | image/webp | Raster image |
| WOFF | font/woff | Web Open Font Format |
| WOFF2 | font/woff2 | Web Open Font Format 2 |
| Plain text | text/plain; charset=utf-8 | Văn bản không được browser coi là HTML theo MIME đã khai báo |
| Binary file | application/octet-stream | Loại tổng quát cho dữ liệu nhị phân, thường dùng cùng attachment khi tải xuống |

Một số hệ thống cũ vẫn dùng application/javascript. Browser thường hỗ trợ nhiều JavaScript MIME type legacy, nhưng khi tạo response mới hãy dùng text/javascript theo đăng ký media type hiện hành.

### 2.2. Content-Type mô tả body, không mô tả cách nén

Content-Type và Content-Encoding có vai trò khác nhau:

~~~http
Content-Type: application/json
Content-Encoding: gzip
~~~

Content-Type nói representation là JSON. Content-Encoding nói byte representation đã được nén bằng gzip. Browser giải mã content coding rồi xử lý nội dung theo media type.

Không khai báo Content-Type: application/gzip chỉ vì response được nén gzip nếu nội dung sau khi giải nén là JSON. Content-Type cần mô tả định dạng representation, còn Content-Encoding mô tả phép mã hóa truyền tải.

### 2.3. Content-Type của request và response

Content-Type trong request mô tả body mà client gửi:

~~~http
POST /api/users HTTP/1.1
Content-Type: application/json

{"displayName":"An"}
~~~

Content-Type trong response mô tả body server trả:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":"u-101","displayName":"An"}
~~~

Header Accept là gợi ý về các media type client có thể nhận:

~~~http
GET /api/catalog HTTP/1.1
Accept: application/json
~~~

Accept không chứng minh body response thực tế là JSON. Server vẫn phải trả Content-Type chính xác. Nếu server tạo representation khác nhau dựa trên Accept, cache có thể cần Vary: Accept.

### 2.4. MIME type và charset

Với text/html hoặc text/plain, charset giúp browser giải mã byte thành ký tự. Với HTML, khai báo UTF-8 rõ ràng:

~~~http
Content-Type: text/html; charset=utf-8
~~~

Với JSON, nội dung trao đổi giữa các hệ thống phải dùng UTF-8; media type là application/json. Không dùng charset parameter để thay thế việc encode body đúng UTF-8.

Parameter boundary trong multipart/form-data là một trường hợp khác:

~~~http
Content-Type: multipart/form-data; boundary=----BrowserBoundary123
~~~

Server cần parser multipart hiểu boundary và giới hạn kích thước/part. Không tự tách multipart bằng string split hoặc tin Content-Type do client gửi mà không kiểm tra cấu trúc body.

## 3. MIME sniffing hoạt động ra sao?

MIME sniffing là quá trình user agent kiểm tra byte của response để suy đoán loại nội dung, thường khi Content-Type thiếu, không rõ ràng hoặc khi một ngữ cảnh cụ thể yêu cầu xử lý tương thích.

Ví dụ, một endpoint upload trả:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain

<!doctype html>
<html>
  <script>document.body.dataset.executed = "yes";</script>
</html>
~~~

Nếu browser hoặc một tầng xử lý diễn giải nội dung theo cách khác với ý định của server, nội dung có thể bị parse như HTML. Hậu quả phụ thuộc loại request, browser, MIME type khai báo, header bảo vệ và cách response được mở.

### 3.1. Browser không sniff giống nhau trong mọi ngữ cảnh

Browser xử lý MIME type theo destination và các chuẩn liên quan. Cần phân biệt:

- Navigation tới URL: browser tạo document và xử lý theo response MIME type cùng quy tắc sniffing cho document.
- Script request: browser kiểm tra response có JavaScript MIME type phù hợp hay không; nosniff làm chặt việc chặn mismatch.
- Stylesheet request: browser kiểm tra MIME type CSS; nosniff chặn response không phải text/css.
- Image request: browser giải mã theo image decoder và loại nội dung được hỗ trợ.
- Fetch/XHR: JavaScript nhận response body theo API; nosniff không biến mọi fetch thành một cơ chế validate nội dung tổng quát.
- Download: Content-Disposition và browser download policy ảnh hưởng cách file được xử lý; không dựa vào nosniff như cơ chế duy nhất.

Không nên mô tả MIME sniffing như một thuật toán duy nhất áp dụng đồng đều cho mọi loại request. Khi cần bảo đảm, hãy khai báo type đúng, bật nosniff và kiểm thử đúng destination mà ứng dụng sử dụng.

### 3.2. Vì sao MIME sniffing có thể tạo XSS?

Giả sử ứng dụng lưu file người dùng tải lên và phục vụ từ cùng origin:

~~~text
https://app.example.com/
https://app.example.com/uploads/avatar-or-document
~~~

Nếu file thực tế chứa HTML nhưng server trả MIME type không phù hợp hoặc bỏ Content-Type, browser có thể diễn giải file theo cách không mong muốn trong một số ngữ cảnh. Nếu file được mở như document trên origin có session cookie, script trong file có thể chạy với origin của ứng dụng và tương tác với các endpoint mà người dùng đăng nhập được phép truy cập.

Cookie HttpOnly ngăn script đọc trực tiếp cookie value, nhưng không ngăn script cùng origin gửi request bằng cookie browser tự đính kèm. Vì vậy, phục vụ file không tin cậy trên cùng origin là một rủi ro kiến trúc.

### 3.3. MIME sniffing không chỉ liên quan HTML

Một response bị diễn giải sai có thể:

- Bị áp dụng như stylesheet hoặc script nếu MIME policy và request context cho phép.
- Bị mở dưới dạng document thay vì tải xuống.
- Làm parser xử lý byte theo định dạng khác dự kiến.
- Tạo khác biệt giữa cách CDN, proxy, antivirus và browser nhận diện file.

File polyglot có thể hợp lệ với nhiều parser hoặc chứa cấu trúc khiến các công cụ phân loại khác nhau. Chỉ kiểm tra phần mở rộng hoặc một magic number không đủ để chứng minh nội dung an toàn.

## 4. X-Content-Type-Options: nosniff

Header:

~~~http
X-Content-Type-Options: nosniff
~~~

Đây là response header yêu cầu browser không sniff MIME type trong các tình huống được chuẩn hóa và thực thi kiểm tra MIME nghiêm ngặt cho script/style. Khi destination là script, response phải có JavaScript MIME type được công nhận; khi destination là style, response phải có text/css. Nếu không phù hợp, browser chặn tài nguyên thay vì cố diễn giải nó.

### 4.1. Ví dụ JavaScript đúng

~~~http
HTTP/1.1 200 OK
Content-Type: text/javascript
X-Content-Type-Options: nosniff

export const version = "1.0";
~~~

MIME type phù hợp với JavaScript và nosniff được bật.

### 4.2. Ví dụ JavaScript sai MIME

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=utf-8
X-Content-Type-Options: nosniff

console.log("This is JavaScript bytes with a wrong media type");
~~~

Nếu response được tải làm script, browser chặn do MIME type không phải JavaScript MIME type. Header không tự sửa response thành text/javascript; nó làm lỗi cấu hình được phát hiện rõ ràng.

### 4.3. CSS cũng cần MIME type chính xác

~~~http
HTTP/1.1 200 OK
Content-Type: text/css; charset=utf-8
X-Content-Type-Options: nosniff

body { color: #123; }
~~~

Nếu stylesheet được trả về text/plain hoặc application/octet-stream, browser chặn khi nosniff được áp dụng cho style destination.

### 4.4. Phạm vi của nosniff

Không diễn giải nosniff thành “browser sẽ không bao giờ sniff bất kỳ response nào”. Quy tắc nổi bật và có thể kiểm chứng ổn định là kiểm tra MIME nghiêm ngặt đối với script và stylesheet. Cách browser xử lý navigation, download và một số loại tài nguyên khác còn phụ thuộc chuẩn, request destination và implementation.

nosniff cũng không:

- Thay thế Content-Type chính xác.
- Xác minh nội dung file upload có an toàn hay không.
- Ngăn XSS trong HTML được cố ý phục vụ với text/html.
- Thay thế Content-Disposition: attachment cho file tải xuống.
- Tách file người dùng khỏi origin có session cookie.
- Thay thế CSP, output encoding, sanitization hoặc kiểm tra quyền.
- Thay thế CORS hoặc CORP.

### 4.5. Đặt nosniff ở đâu?

Nên thêm header vào response do ứng dụng phục vụ, đặc biệt:

- HTML document.
- JavaScript và CSS.
- JSON/API response.
- File upload/download.
- Trang preview và endpoint trả nội dung do người dùng kiểm soát.

Có thể cấu hình ở application middleware, reverse proxy hoặc web server. Hãy xác minh header thực sự có mặt trên response cuối cùng từ CDN/proxy tới browser; một tầng trung gian có thể xóa hoặc ghi đè header.

## 5. Chọn Content-Type và header theo loại nội dung

### 5.1. HTML document

~~~http
Content-Type: text/html; charset=utf-8
X-Content-Type-Options: nosniff
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'
~~~

HTML được browser parse như document. Nếu HTML chứa dữ liệu do người dùng kiểm soát, phải encode theo đúng output context và sanitize HTML khi cho phép markup. nosniff không làm HTML đã khai báo text/html trở nên vô hại.

### 5.2. JavaScript

~~~http
Content-Type: text/javascript
X-Content-Type-Options: nosniff
~~~

Dùng MIME type JavaScript hiện hành. Không trả JavaScript bằng text/plain hoặc application/octet-stream rồi mong browser tự nhận ra. Với module script, browser thực hiện MIME checking nghiêm ngặt; cấu hình đúng ngay từ server.

### 5.3. CSS

~~~http
Content-Type: text/css; charset=utf-8
X-Content-Type-Options: nosniff
~~~

Không dùng text/plain cho stylesheet. CSS có thể tải từ CDN, nhưng phải bảo đảm MIME type chính xác và cache policy phù hợp.

### 5.4. JSON API

~~~http
Content-Type: application/json
X-Content-Type-Options: nosniff
Cache-Control: no-store
~~~

JSON API nên trả application/json. Nếu response chứa dữ liệu cá nhân hoặc token, cache policy cần được thiết kế riêng; nosniff không ngăn browser lưu response.

Không trả JSON nhạy cảm dưới text/html. Không dùng JSONP để né CORS cho dữ liệu riêng tư; JSONP biến response thành JavaScript có thể được nhúng qua script element.

### 5.5. SVG

~~~http
Content-Type: image/svg+xml
X-Content-Type-Options: nosniff
~~~

SVG là định dạng vector dựa trên XML và có khả năng chứa script, event handler, external reference hoặc nội dung tương tác khi được mở như document hay nhúng trong ngữ cảnh phù hợp. Một số ngữ cảnh image như img hạn chế script, nhưng không nên suy ra rằng mọi cách mở/nhúng SVG đều an toàn.

Với SVG do người dùng tải lên:

- Không phục vụ inline trên origin chứa session đăng nhập nếu chưa sanitize và đánh giá kỹ.
- Ưu tiên chuyển đổi sang raster image nếu sản phẩm chỉ cần hiển thị ảnh.
- Nếu phải giữ SVG, sanitize bằng parser/library chuyên dụng và kiểm tra external references.
- Phục vụ từ origin riêng không có cookie đăng nhập của ứng dụng.
- Với download, dùng Content-Disposition: attachment và nosniff.

### 5.6. Ảnh raster

Khai báo chính xác image/png, image/jpeg hoặc image/webp theo định dạng thực tế. Đọc file bằng decoder an toàn; cân nhắc re-encode để loại metadata hoặc cấu trúc không cần thiết. Không tin phần mở rộng .png hoặc Content-Type do browser gửi lên.

### 5.7. File không xác định

Nếu server không xác định được một định dạng được phép, có thể trả application/octet-stream cùng Content-Disposition: attachment. Không dùng octet-stream để cố phục vụ file như script/style; browser có thể chặn do strict MIME checking và việc tải xuống cần có UX rõ ràng.

### 5.8. Content-Type mẫu theo endpoint

| Endpoint | Response header gợi ý | Lưu ý |
| --- | --- | --- |
| /index.html | text/html; charset=utf-8 + nosniff | CSP và output encoding vẫn cần |
| /assets/app.js | text/javascript + nosniff | Không trả text/plain |
| /assets/site.css | text/css + nosniff | CSS MIME phải đúng |
| /api/profile | application/json + nosniff + private/no-store | Dữ liệu theo user |
| /images/logo.png | image/png + nosniff | Kiểm tra định dạng thực tế |
| /uploads/file | application/octet-stream + attachment + nosniff | Không inline nội dung không tin cậy |
| /uploads/vector.svg | image/svg+xml trên origin riêng hoặc attachment | Sanitize hoặc chuyển đổi |

## 6. File upload: không tin MIME type từ client

Browser thường gửi Content-Type cho từng part của multipart upload:

~~~http
POST /upload HTTP/1.1
Content-Type: multipart/form-data; boundary=----BrowserBoundary123

------BrowserBoundary123
Content-Disposition: form-data; name="file"; filename="photo.png"
Content-Type: image/png

...file bytes...
------BrowserBoundary123--
~~~

Tên file và Content-Type của part do client kiểm soát. Một attacker có thể đổi filename thành report.png và khai báo image/png trong khi nội dung thực tế là HTML, SVG hoặc dữ liệu khác.

### 6.1. Quy trình xử lý upload

1. Xác thực người upload và kiểm tra quyền ghi vào resource.
2. Giới hạn tổng request size, file size, số lượng part và thời gian xử lý.
3. Allowlist loại file mà chức năng thực sự cần.
4. Kiểm tra extension sau khi chuẩn hóa filename, nhưng không xem extension là bằng chứng định dạng.
5. Phân tích nội dung bằng parser/decoder phù hợp; đối chiếu magic bytes và cấu trúc file.
6. Với ảnh, cân nhắc decode rồi re-encode thành định dạng raster được hỗ trợ.
7. Với PDF/Office/media, cân nhắc antivirus hoặc sandbox scanning theo threat model.
8. Lưu file bằng tên ngẫu nhiên do server tạo; không dùng trực tiếp path do client gửi.
9. Lưu metadata MIME type đã được server xác định, không tái sử dụng giá trị client tự khai báo.
10. Phục vụ file từ origin riêng hoặc qua download endpoint có header an toàn.

~~~mermaid
flowchart TD
    A["Client gửi file và metadata không tin cậy"] --> B["Giới hạn request, file size và số part"]
    B --> C["Allowlist + parser/decoder + kiểm tra cấu trúc"]
    C --> D{"Định dạng được hỗ trợ và hợp lệ?"}
    D -->|Không| E["Từ chối upload"]
    D -->|Có| F["Re-encode hoặc scan nếu phù hợp"]
    F --> G["Lưu ngoài web root với tên do server tạo"]
    G --> H{"Cách phân phối"}
    H -->|Nội dung cần hiển thị| I["Origin riêng + Content-Type đã xác minh + nosniff"]
    H -->|Tải xuống| J["octet-stream + attachment + nosniff"]
    I --> K["Kiểm tra quyền và response policy"]
    J --> K
~~~

### 6.2. Magic bytes có ích nhưng không đủ

Magic bytes là chữ ký ở đầu file giúp nhận diện một số định dạng. Tuy nhiên:

- File có thể chứa nhiều định dạng hoặc polyglot structure.
- Parser có thể có lỗ hổng khi xử lý file lỗi.
- Một số định dạng không có signature đơn giản.
- Nội dung có thể chứa active content dù loại file hợp lệ.

Kết hợp signature check với parser/decoder, allowlist, giới hạn tài nguyên và cách phục vụ an toàn. Không dùng một hàm đoán MIME duy nhất làm ranh giới bảo mật.

### 6.3. Lưu file ngoài web root

Không để file upload tự động trở thành static file trên web root. Tạo storage riêng và chỉ phục vụ qua handler có kiểm tra quyền. Handler phải chọn Content-Type dựa trên metadata server đã xác minh và quyết định inline hay attachment theo loại file.

Nếu file chỉ thuộc về một user, endpoint tải xuống phải kiểm tra authorization mỗi lần. URL khó đoán hoặc tên file ngẫu nhiên không thay thế kiểm tra quyền.

## 7. Content-Disposition và download an toàn

Content-Disposition điều khiển cách response được trình bày, thường là inline hoặc attachment.

### 7.1. attachment

~~~http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="report.bin"
X-Content-Type-Options: nosniff
Cache-Control: private, no-store
~~~

attachment yêu cầu browser xử lý response như file tải xuống trong các browser hỗ trợ. filename gợi ý tên file; server cần loại bỏ CR/LF, path separator và ký tự nguy hiểm khỏi filename trước khi tạo header.

### 7.2. filename và filename*

Với tên file có Unicode, có thể cung cấp filename* theo RFC 8187 cùng filename fallback:

~~~http
Content-Disposition: attachment; filename="report.pdf"; filename*=UTF-8''b%C3%A1o-c%C3%A1o.pdf
~~~

Không nối trực tiếp chuỗi do client gửi vào header. Encode/validate theo chuẩn và ngăn response splitting.

### 7.3. attachment không thay thế origin isolation

Content-Disposition: attachment giảm khả năng browser mở file inline khi người dùng truy cập URL. Tuy nhiên, người dùng có thể tải file rồi mở bằng ứng dụng khác; header cũng không thay thế việc tách file khỏi origin tin cậy, kiểm tra quyền tải xuống và scan nội dung.

Với file HTML/SVG do người dùng kiểm soát, tốt nhất là phục vụ từ một origin riêng không có session cookie của ứng dụng. Nếu chức năng cần preview, dùng viewer cô lập, iframe sandbox và CSP chặt chẽ; không nhúng trực tiếp nội dung không tin cậy vào DOM của ứng dụng.

### 7.4. Origin riêng cần đi cùng cookie scope phù hợp

Một subdomain khác là origin khác, nhưng chưa chắc đã tách cookie. Nếu ứng dụng đặt cookie với Domain=.example.com, browser có thể gửi cookie đó tới nhiều subdomain trong cùng domain. Vì vậy, user-content.example.com vẫn có thể nhận cookie được cấu hình cho toàn bộ example.com.

Ưu tiên phục vụ nội dung không tin cậy trên một site/registrable domain riêng, không dùng chung cookie với ứng dụng. Với session cookie của ứng dụng, ưu tiên host-only cookie; prefix __Host- yêu cầu Secure, Path=/ và không có Domain attribute. Vẫn cần CSRF protection cho endpoint ứng dụng vì nội dung ở site khác có thể tạo request cross-site theo những điều kiện browser cho phép.

## 8. SVG, HTML và file polyglot

### 8.1. HTML upload là nội dung chủ động

Nếu user tải lên file HTML và ứng dụng mở file dưới:

~~~text
https://app.example.com/uploads/document.html
~~~

browser tạo document trên origin app.example.com. Script trong document có thể truy cập DOM, gọi endpoint cùng origin và dùng credential browser tự gửi. HttpOnly cookie không ngăn các request đó.

Đặt Content-Type: text/plain không phải biện pháp cô lập đủ mạnh nếu browser hoặc một công cụ khác xử lý nội dung theo ngữ cảnh khác. Dùng origin riêng, attachment hoặc một viewer sandbox được thiết kế rõ ràng.

### 8.2. SVG cần xử lý theo ngữ cảnh

SVG có thể được dùng làm image, document hoặc resource nhúng. Browser giới hạn một số khả năng khi SVG được tải qua img, nhưng khi mở trực tiếp hoặc nhúng bằng object/iframe, hành vi và khả năng active content khác đi.

Không cho phép SVG upload từ người dùng chạy trên origin ứng dụng chỉ vì file có MIME type image/svg+xml. MIME type đúng giúp browser chọn parser; nó không chứng minh nội dung an toàn.

### 8.3. Polyglot file

Polyglot là file được tạo để có thể được nhận diện/parse theo nhiều định dạng. Một file có thể vượt qua kiểm tra extension hoặc một bộ nhận diện đơn giản nhưng lại được browser hoặc parser khác diễn giải theo cách khác.

Phòng vệ:

- Chỉ cho phép định dạng cần thiết.
- Dùng parser/decoder chuyên dụng.
- Re-encode khi có thể.
- Không phục vụ nội dung không tin cậy inline trên app origin.
- Đặt Content-Type server-side và nosniff.
- Dùng attachment cho download.
- Kiểm thử bằng browser thật và các parser trong pipeline xử lý.

## 9. CORS, CORP và MIME type giải quyết vấn đề khác nhau

Các header này thường xuất hiện cùng nhau nhưng có mục tiêu khác:

| Cơ chế | Câu hỏi nó trả lời | Không giải quyết |
| --- | --- | --- |
| Content-Type | Body này được khai báo là định dạng gì? | Nội dung có an toàn hay user có quyền truy cập không |
| X-Content-Type-Options: nosniff | Browser có phải chặn script/style khi MIME không đúng không? | Không tắt mọi sniffing, không sanitize file |
| CORS | JavaScript origin khác có được đọc response không? | Không thay thế MIME checking hoặc authorization |
| CORP | Resource có được phép bị nhúng bởi cross-origin/cross-site context không? | Không xác định nội dung là HTML/JS/ảnh |
| CSP | Document được phép tải/thực thi resource nào và có thể giới hạn script không? | Không sửa Content-Type sai hoặc làm file upload tự an toàn |
| Content-Disposition | Browser nên hiển thị inline hay tải xuống? | Không thay thế kiểm tra file hoặc origin isolation |

Ví dụ, một file JavaScript được nhúng bằng script element có thể được tải từ origin khác mà không cần CORS trong trường hợp classic script thông thường. Vì vậy, “đã bật CORS” không đồng nghĩa browser không thể tải hoặc thực thi resource sai MIME.

## 10. Cấu hình an toàn ở application và reverse proxy

### 10.1. Middleware Node.js cơ bản

Ví dụ minh họa response HTML, JSON và JavaScript:

~~~js
import { createServer } from 'node:http';

const server = createServer((request, response) => {
  if (request.url === '/') {
    response.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'X-Content-Type-Options': 'nosniff',
      'Content-Security-Policy': "default-src 'self'; object-src 'none'; base-uri 'self'",
    });
    response.end('<!doctype html><html><body><h1>Safe MIME</h1></body></html>');
    return;
  }

  if (request.url === '/api/status') {
    response.writeHead(200, {
      'Content-Type': 'application/json',
      'X-Content-Type-Options': 'nosniff',
      'Cache-Control': 'no-store',
    });
    response.end(JSON.stringify({ status: 'ok' }));
    return;
  }

  if (request.url === '/assets/app.js') {
    response.writeHead(200, {
      'Content-Type': 'text/javascript',
      'X-Content-Type-Options': 'nosniff',
    });
    response.end('console.log("JavaScript MIME is correct");');
    return;
  }

  response.writeHead(404, {
    'Content-Type': 'text/plain; charset=utf-8',
    'X-Content-Type-Options': 'nosniff',
  });
  response.end('Not found');
});

server.listen(3000, () => {
  console.log('Open http://localhost:3000');
});
~~~

Trong framework thực tế, nên cấu hình header tập trung ở middleware hoặc response policy. Tuy nhiên, endpoint download, static asset, API và upload preview có thể cần Content-Type/Content-Disposition riêng; không ghi đè tất cả response thành cùng một MIME type.

### 10.2. Reverse proxy

Ví dụ Nginx thêm nosniff:

~~~nginx
add_header X-Content-Type-Options "nosniff" always;
~~~

always giúp header được thêm trên các response status mà directive hỗ trợ, kể cả một số response lỗi/redirect. Kiểm tra scope của cấu hình để tránh thêm trùng hoặc override header do upstream đặt.

Nếu dùng Nginx static file mapping, kiểm tra mime.types và default_type. Không đặt default_type text/html cho mọi file; cấu hình sai có thể khiến file binary/script bị diễn giải như HTML.

### 10.3. Đừng tự đoán MIME từ extension rồi tin tuyệt đối

Extension có thể hỗ trợ chọn policy, nhưng phải dựa vào loại file đã xác minh ở bước upload. Ví dụ file có tên .png nhưng parser xác nhận đó là HTML thì không được phục vụ nó với image/png chỉ vì extension.

Lưu metadata do server xác định:

~~~js
const storedFile = {
  storageKey: generatedRandomName,
  verifiedMediaType: 'image/png',
  originalName: sanitizedDisplayName,
};
~~~

Khi download, lấy verifiedMediaType từ metadata server-side và kiểm tra policy inline/attachment. Không đọc lại Content-Type do client gửi để dựng response.

## 11. Thực hành: kiểm chứng MIME và nosniff trong browser

Bài lab dùng **Node.js 18 trở lên**, không cần package ngoài. Server phục vụ một trang điều khiển và một số response có MIME type đúng/sai để quan sát hành vi browser.

Lab gồm:

- JavaScript classic có MIME type text/javascript và nosniff.
- JavaScript classic có MIME type text/plain và nosniff; browser phải chặn khi dùng làm script.
- CSS có MIME type text/css và nosniff.
- CSS có MIME type text/plain và nosniff; browser phải chặn khi dùng làm stylesheet.
- Một HTML upload demo được mở inline trên cùng origin để thấy document script chạy.
- Một download demo dùng application/octet-stream, attachment và nosniff.

Chỉ dùng nội dung demo vô hại. Lab không nhận file upload thật và không dùng cookie/session.

### 11.1. Tạo file mime-lab.mjs

~~~js
import { createServer } from 'node:http';

const page = [
  '<!doctype html>',
  '<html lang="vi"><head><meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width, initial-scale=1">',
  '<title>MIME and nosniff lab</title>',
  '<style>',
  'body{font:16px system-ui,sans-serif;max-width:850px;margin:32px auto;padding:0 16px}',
  'button{padding:8px 12px;margin:4px}',
  'pre{white-space:pre-wrap;background:#f2f2f2;padding:12px}',
  '</style></head><body>',
  '<h1>MIME and nosniff lab</h1>',
  '<p>Quan sát DevTools Console và Network khi tải từng resource.</p>',
  '<p>',
  '<button id="good-script">Load correct JavaScript MIME</button>',
  '<button id="bad-script">Load wrong JavaScript MIME</button>',
  '<button id="good-style">Load correct CSS MIME</button>',
  '<button id="bad-style">Load wrong CSS MIME</button>',
  '</p>',
  '<p>',
  '<a href="/uploads/demo.html" target="_blank" rel="noopener">Open untrusted HTML inline</a>',
  '</p>',
  '<p>',
  '<a href="/downloads/demo.html">Download untrusted HTML as attachment</a>',
  '</p>',
  '<pre id="result">No resource loaded.</pre>',
  '<div id="sample">Sample element for stylesheet test.</div>',
  '<script>',
  'const result = document.querySelector("#result");',
  'function loadScript(path) {',
  '  const script = document.createElement("script");',
  '  script.async = true;',
  '  script.src = path;',
  '  script.onload = () => { result.textContent += "\\nLoaded: " + path; };',
  '  script.onerror = () => { result.textContent += "\\nBlocked or failed: " + path; };',
  '  document.head.append(script);',
  '}',
  'function loadStyle(path) {',
  '  const link = document.createElement("link");',
  '  link.rel = "stylesheet";',
  '  link.href = path;',
  '  link.onload = () => { result.textContent += "\\nLoaded: " + path; };',
  '  link.onerror = () => { result.textContent += "\\nBlocked or failed: " + path; };',
  '  document.head.append(link);',
  '}',
  'document.querySelector("#good-script").addEventListener("click", () => loadScript("/assets/good.js"));',
  'document.querySelector("#bad-script").addEventListener("click", () => loadScript("/assets/wrong.js"));',
  'document.querySelector("#good-style").addEventListener("click", () => loadStyle("/assets/good.css"));',
  'document.querySelector("#bad-style").addEventListener("click", () => loadStyle("/assets/wrong.css"));',
  '</script></body></html>',
].join('\n');

const harmlessScript = [
  'window.mimeLabScriptLoaded = true;',
  'document.documentElement.dataset.mimeLabScript = "loaded";',
  'console.info("Correct JavaScript MIME loaded.");',
].join('\n');

const wrongMimeScript = [
  'window.mimeLabWrongScriptLoaded = true;',
  'console.warn("This script should be blocked by nosniff.");',
].join('\n');

const goodCss = '#sample { color: green; font-weight: 700; }';
const wrongCss = '#sample { color: red; font-weight: 700; }';

const untrustedHtml = [
  '<!doctype html>',
  '<html lang="vi"><head><meta charset="utf-8"><title>Uploaded demo</title></head>',
  '<body><h1>Demo upload document</h1>',
  '<p>Nội dung này được phục vụ inline trên cùng origin.</p>',
  '<script>',
  'document.body.dataset.inlineScript = "executed";',
  'document.body.insertAdjacentHTML("beforeend", "<p id=\\"execution\\">Inline script executed.</p>");',
  '</script></body></html>',
].join('\n');

const server = createServer((request, response) => {
  const url = new URL(request.url, 'http://localhost:3000');

  if (url.pathname === '/') {
    response.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'X-Content-Type-Options': 'nosniff',
      'Cache-Control': 'no-store',
    });
    response.end(page);
    return;
  }

  if (url.pathname === '/assets/good.js') {
    response.writeHead(200, {
      'Content-Type': 'text/javascript',
      'X-Content-Type-Options': 'nosniff',
      'Cache-Control': 'no-store',
    });
    response.end(harmlessScript);
    return;
  }

  if (url.pathname === '/assets/wrong.js') {
    response.writeHead(200, {
      'Content-Type': 'text/plain; charset=utf-8',
      'X-Content-Type-Options': 'nosniff',
      'Cache-Control': 'no-store',
    });
    response.end(wrongMimeScript);
    return;
  }

  if (url.pathname === '/assets/good.css') {
    response.writeHead(200, {
      'Content-Type': 'text/css; charset=utf-8',
      'X-Content-Type-Options': 'nosniff',
      'Cache-Control': 'no-store',
    });
    response.end(goodCss);
    return;
  }

  if (url.pathname === '/assets/wrong.css') {
    response.writeHead(200, {
      'Content-Type': 'text/plain; charset=utf-8',
      'X-Content-Type-Options': 'nosniff',
      'Cache-Control': 'no-store',
    });
    response.end(wrongCss);
    return;
  }

  if (url.pathname === '/uploads/demo.html') {
    response.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'X-Content-Type-Options': 'nosniff',
      'Cache-Control': 'no-store',
    });
    response.end(untrustedHtml);
    return;
  }

  if (url.pathname === '/downloads/demo.html') {
    response.writeHead(200, {
      'Content-Type': 'application/octet-stream',
      'X-Content-Type-Options': 'nosniff',
      'Content-Disposition': 'attachment; filename="demo.html"',
      'Cache-Control': 'private, no-store',
    });
    response.end(untrustedHtml);
    return;
  }

  response.writeHead(404, {
    'Content-Type': 'text/plain; charset=utf-8',
    'X-Content-Type-Options': 'nosniff',
  });
  response.end('Not found');
});

server.listen(3000, () => {
  console.log('Open http://localhost:3000');
});
~~~

### 11.2. Chạy lab

~~~bash
node mime-lab.mjs
~~~

Mở http://localhost:3000 trong browser hiện đại.

### 11.3. Kiểm tra JavaScript MIME

1. Nhấn Load correct JavaScript MIME.
2. Mở Console và kiểm tra thông báo Correct JavaScript MIME loaded.
3. Trong Network, chọn /assets/good.js và xem Content-Type: text/javascript cùng X-Content-Type-Options: nosniff.
4. Nhấn Load wrong JavaScript MIME.
5. Browser phải chặn module script do response khai báo text/plain; Console thường hiển thị lỗi strict MIME type checking.

### 11.4. Kiểm tra CSS MIME

1. Nhấn Load correct CSS MIME; phần tử sample đổi màu xanh.
2. Nhấn Load wrong CSS MIME; browser chặn stylesheet khai báo text/plain khi nosniff được áp dụng.
3. Xem Console và response header trong Network.

### 11.5. So sánh inline HTML và attachment

1. Mở Open untrusted HTML inline.
2. Trang demo hiển thị Inline script executed; kiểm tra DOM attribute data-mime-lab-script trong DevTools.
3. Quay lại trang lab và chọn Download untrusted HTML as attachment.
4. Browser tải file thay vì hiển thị nó inline theo hành vi Content-Disposition.
5. Mở file tải xuống bằng trình soạn thảo để kiểm tra nội dung.

Thử nghiệm minh họa rằng MIME đúng cho HTML không làm nội dung HTML do người dùng cung cấp trở nên an toàn. Trong ứng dụng thật, file upload cần origin riêng, quyền tải xuống và pipeline xác minh/sanitization phù hợp.

### 11.6. Kiểm tra bằng curl

~~~bash
curl -i http://localhost:3000/assets/good.js
curl -i http://localhost:3000/assets/wrong.js
curl -I http://localhost:3000/downloads/demo.html
~~~

So sánh Content-Type, X-Content-Type-Options và Content-Disposition giữa các route.

### 11.7. Giới hạn lab

- Lab dùng classic script cùng nosniff để kiểm tra MIME type; browser chặn response script khai báo text/plain. Kết quả cụ thể của Console có thể khác giữa browser.
- HTML upload là nội dung demo vô hại, nhưng được cố ý mở trên cùng origin để minh họa ranh giới bảo mật.
- Download behavior có thể khác theo browser, cài đặt và người dùng; Content-Disposition: attachment là chỉ thị xử lý download, không bảo đảm file an toàn khi mở sau đó.
- Lab không nhận upload thật, không scan malware, không sanitize SVG và không mô phỏng CDN/proxy.
- Không dùng lab để thử credential hoặc dữ liệu production.

## 12. Kiểm tra và xử lý lỗi MIME

### 12.1. DevTools Network

Trong DevTools → Network:

1. Chọn request script, stylesheet, document hoặc file download.
2. Xem Response Headers và ghi lại Content-Type.
3. Xác minh X-Content-Type-Options có giá trị nosniff.
4. Kiểm tra Request URL và loại destination.
5. Xem Console để tìm lỗi strict MIME type checking.
6. Nếu qua CDN, so sánh response header từ origin với response cuối cùng browser nhận.

Đừng chỉ nhìn extension trong URL. Một file có đuôi .js nhưng server trả text/plain vẫn là response sai MIME.

### 12.2. curl

Kiểm tra response headers:

~~~bash
curl -I https://app.example.com/assets/app.js
curl -I https://app.example.com/api/profile
curl -I https://app.example.com/uploads/document
~~~

Lấy cả body và header khi cần kiểm tra byte/định dạng:

~~~bash
curl -i https://app.example.com/api/data
~~~

curl không thực thi JavaScript hoặc áp dụng browser MIME policy. Dùng nó để kiểm tra response server; dùng browser thật để kiểm chứng cách tài nguyên được xử lý.

### 12.3. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Console báo strict MIME type checking | Script/module trả MIME type không phải JavaScript | Trả text/javascript và kiểm tra proxy/CDN |
| Stylesheet bị chặn | CSS trả text/plain hoặc application/octet-stream | Trả text/css |
| API JSON bị hiểu thành HTML | Server khai báo text/html hoặc route fallback trả HTML | Trả application/json; kiểm tra Accept và routing |
| File upload chạy script khi mở | File được phục vụ inline trên app origin | Tách origin, attachment, sanitize hoặc chuyển đổi |
| nosniff không xuất hiện | Middleware/proxy không thêm hoặc CDN xóa header | Kiểm tra response cuối cùng và cấu hình mọi tầng |
| Download mở trong browser | Content-Disposition thiếu/sai hoặc user agent policy | Dùng attachment, kiểm tra filename và browser thực tế |
| Font tải lỗi | MIME type hoặc CORS/font policy sai | Dùng font/woff2 hoặc MIME phù hợp; kiểm tra CORS khi font cross-origin |
| SVG chạy nội dung ngoài dự kiến | SVG mở như document hoặc object/iframe | Sanitize, rasterize, tách origin hoặc attachment |

## 13. Checklist triển khai MIME an toàn

1. **Khai báo Content-Type chính xác:** dựa trên định dạng server xác minh, không dựa riêng vào filename.
2. **Thêm nosniff:** gửi X-Content-Type-Options: nosniff trên response cần bảo vệ.
3. **JavaScript:** dùng text/javascript.
4. **CSS:** dùng text/css.
5. **HTML:** dùng text/html; charset=utf-8 và áp CSP/output encoding phù hợp.
6. **JSON:** dùng application/json; không trả JSON nhạy cảm dưới text/html.
7. **Ảnh/font:** dùng MIME type đúng với định dạng đã xác minh.
8. **Binary download:** dùng application/octet-stream và Content-Disposition: attachment khi phù hợp.
9. **Upload validation:** allowlist, parser/decoder, giới hạn tài nguyên và server-generated filename.
10. **Không tin client MIME:** multipart Content-Type và extension đều do client kiểm soát.
11. **Tách untrusted content:** phục vụ file người dùng từ origin riêng không có session cookie ứng dụng.
12. **Xử lý SVG:** sanitize hoặc rasterize; tránh mở inline trên app origin.
13. **Không cache nội dung nhạy cảm:** chọn Cache-Control private/no-store theo dữ liệu.
14. **Cấu hình CDN/proxy:** giữ nguyên Content-Type và nosniff; tránh default type sai.
15. **Kiểm thử destination:** kiểm tra navigation, script, stylesheet, image và download riêng.
16. **Quan sát browser thật:** kiểm tra Console, Network và các browser mục tiêu.

## 14. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “nosniff tắt mọi MIME sniffing trên browser.” | Nó thực thi MIME checking nghiêm ngặt cho script/style trong các trường hợp được chuẩn hóa; không phải công tắc chung cho mọi navigation/download. |
| “Có nosniff thì Content-Type có thể sai.” | MIME sai có thể khiến browser chặn resource; server vẫn phải khai báo đúng. |
| “CORS ngăn browser thực thi file sai MIME.” | CORS kiểm soát quyền đọc cross-origin; MIME checking là cơ chế khác. |
| “File có đuôi .png thì là ảnh.” | Extension do client kiểm soát; phải kiểm tra nội dung bằng parser/decoder. |
| “Client gửi image/png thì có thể lưu metadata đó.” | Multipart Content-Type là dữ liệu không tin cậy; server phải tự xác định loại file. |
| “SVG là ảnh nên không có script.” | SVG có active content trong một số ngữ cảnh; mở trực tiếp/object/iframe khác với img. |
| “Content-Disposition attachment làm file an toàn.” | Nó yêu cầu download; file vẫn có thể nguy hiểm khi người dùng mở bằng browser hoặc ứng dụng khác. |
| “text/plain luôn bảo đảm nội dung không thể chạy.” | Phải xét browser, destination, sniffing behavior và nơi file được mở; dùng origin isolation cho nội dung không tin cậy. |
| “no-store thay thế nosniff.” | Cache policy và MIME handling giải quyết hai vấn đề khác nhau. |
| “Magic bytes đủ xác minh file.” | File polyglot, parser bug và active content cần thêm validation, transformation và isolation. |

## 15. Câu hỏi tự đánh giá

**Câu 1.** Content-Type khác Accept thế nào?

**Gợi ý trả lời:** Content-Type mô tả body thực tế của request/response; Accept là danh sách media type client muốn nhận.

**Câu 2.** MIME sniffing là gì?

**Gợi ý trả lời:** Browser suy đoán loại nội dung từ byte response khi metadata thiếu, mơ hồ hoặc trong một ngữ cảnh cần sniff theo quy tắc user agent.

**Câu 3.** X-Content-Type-Options: nosniff bảo vệ điều gì?

**Gợi ý trả lời:** Nó làm chặt MIME checking cho script và stylesheet; browser chặn tài nguyên nếu MIME type không phù hợp với destination.

**Câu 4.** Vì sao nosniff không làm file HTML upload an toàn?

**Gợi ý trả lời:** HTML được khai báo text/html vẫn được parse thành document; nosniff không sanitize nội dung hoặc tách file khỏi origin.

**Câu 5.** Vì sao không tin Content-Type trong multipart upload?

**Gợi ý trả lời:** Client có thể tự chọn filename và Content-Type; server phải xác minh nội dung bằng allowlist và parser/decoder.

**Câu 6.** Vì sao HTML upload trên cùng origin nguy hiểm?

**Gợi ý trả lời:** Khi mở như document, script có thể chạy trong origin ứng dụng và dùng browser session để gọi endpoint cùng origin.

**Câu 7.** Content-Disposition attachment có vai trò gì?

**Gợi ý trả lời:** Yêu cầu browser tải response thay vì hiển thị inline theo hành vi user agent; nó không thay thế scan, authorization hoặc origin isolation.

**Câu 8.** Vì sao SVG cần xử lý riêng?

**Gợi ý trả lời:** SVG có thể chứa active content; hành vi phụ thuộc cách nó được mở hoặc nhúng.

**Câu 9.** CORS có thay thế nosniff không?

**Gợi ý trả lời:** Không. CORS kiểm soát việc JavaScript cross-origin đọc response; nosniff kiểm tra MIME cho một số destination tài nguyên.

**Câu 10.** Cần kiểm tra gì khi browser báo strict MIME type checking?

**Gợi ý trả lời:** Xem destination, Content-Type response, nosniff, route static server và header cuối cùng sau CDN/proxy.

## Tài liệu tham khảo

- WHATWG — [MIME Sniffing Standard](https://mimesniff.spec.whatwg.org/).
- WHATWG — [Fetch Standard: X-Content-Type-Options nosniff check](https://fetch.spec.whatwg.org/).
- IETF — [RFC 9239: Updates to ECMAScript Media Types](https://www.rfc-editor.org/rfc/rfc9239.html).
- IETF — [RFC 9110: HTTP Semantics, Content-Type and Content-Disposition](https://www.rfc-editor.org/rfc/rfc9110.html).
- IETF — [RFC 8187: Character Set and Language Encoding for HTTP Header Field Parameters](https://www.rfc-editor.org/rfc/rfc8187.html).
- MDN — [X-Content-Type-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Content-Type-Options).
- MDN — [MIME types](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/MIME_types).
- MDN — [Content-Type](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Type).
- OWASP — [File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).
- OWASP — [Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html).
