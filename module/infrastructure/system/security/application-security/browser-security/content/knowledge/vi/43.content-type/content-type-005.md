# Script MIME: định dạng nội dung và ranh giới thực thi JavaScript

**Chương:** Content type  
**Mô-đun:** `SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY` — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy (SOP), CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

MIME type của script cho trình duyệt biết response chứa loại nội dung nào. Với JavaScript, MIME type là một phần của quyết định tài nguyên có được xử lý như mã thực thi hay không. Server gửi sai Content-Type, browser có thể từ chối script, áp dụng quy tắc MIME sniffing hoặc xử lý khác nhau giữa classic script và module script.

Script MIME là một ranh giới bảo mật vì JavaScript chạy trong một origin có thể đọc DOM, gọi API bằng credential của trang và truy cập state mà script cùng origin được phép dùng. Nếu nội dung do người dùng kiểm soát bị phục vụ như JavaScript trên origin tin cậy, lỗi có thể trở thành stored/reflected XSS. Ngược lại, nếu script hợp lệ bị phục vụ với MIME sai, chức năng có thể hỏng trên một số browser hoặc khi bật strict MIME checking.

Đặt đúng MIME type không tự làm JavaScript an toàn. Một file có Content-Type là JavaScript vẫn thực thi mã độc nếu nội dung đã bị chèn. X-Content-Type-Options: nosniff ngăn một số kiểu diễn giải MIME không đúng, nhưng không thay thế output encoding, CSP, Trusted Types, kiểm soát upload hay authorization.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích MIME type, media type, essence và Content-Type response header.
2. Nhận diện JavaScript MIME types và chọn text/javascript cho script.
3. Phân biệt classic script, module script và data block trong thẻ script.
4. Giải thích strict MIME checking và vai trò của X-Content-Type-Options: nosniff.
5. Hiểu browser xử lý MIME sniffing khác nhau theo request destination và loại script.
6. Phân tích cách type="module" tải dependency và áp dụng CORS.
7. Phân biệt script MIME với MIME của JSON, import map và dữ liệu nhúng.
8. Hiểu rủi ro khi upload/user content được phục vụ từ origin ứng dụng.
9. Kết hợp CSP, SRI, CORS, CORP và nosniff để bảo vệ tài nguyên script.
10. Kiểm tra Content-Type, response headers và hành vi thực thi trong DevTools.

## 2. MIME type và Content-Type

### 2.1. MIME type là gì?

MIME type (media type) mô tả loại dữ liệu trong một representation. Trong HTTP, server thường khai báo bằng response header Content-Type.

Ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: text/javascript; charset=utf-8
X-Content-Type-Options: nosniff

console.log("hello");
```

text/javascript là media type; charset=utf-8 là parameter mô tả charset. Với JavaScript hiện đại, UTF-8 là lựa chọn chuẩn. Tránh dựa vào charset khác hoặc để server tự suy đoán encoding không nhất quán.

Một MIME type có cấu trúc tổng quát type/subtype và có thể có parameters. Khi so sánh loại nội dung, browser thường xét MIME essence (type/subtype sau khi parse), không so sánh cả chuỗi header bằng cách tìm một substring tùy ý. Ví dụ text/javascript; charset=utf-8 có essence là text/javascript.

### 2.2. Content-Type được xác định ở server

Server, framework, reverse proxy hoặc object storage có thể quyết định MIME dựa trên extension, metadata hoặc cấu hình. Các lớp này có thể bất đồng:

- File .js được gửi thành application/octet-stream.
- File upload có tên .jpg nhưng nội dung là HTML/JavaScript.
- CDN ghi đè Content-Type dựa trên extension.
- Origin trả text/plain nhưng proxy đổi thành text/html.
- Một route động trả JavaScript nhưng framework mặc định application/json.

Không coi filename là bằng chứng về nội dung. Với asset do build pipeline tạo, cấu hình MIME theo loại artifact và kiểm tra header thực tế trên response đi qua CDN/proxy.

### 2.3. MIME type của JavaScript

MIME type khuyến nghị cho JavaScript là:

```http
Content-Type: text/javascript; charset=utf-8
```

Một số MIME type lịch sử cũng được browser nhận diện là JavaScript MIME type, ví dụ application/javascript, application/ecmascript, text/ecmascript và các alias legacy. Chúng tồn tại vì lịch sử web; khi triển khai mới, ưu tiên text/javascript theo chuẩn hiện hành.

Các essence thường gặp trong danh sách JavaScript MIME type gồm:

| MIME essence | Ghi chú |
| --- | --- |
| text/javascript | Khuyến nghị cho triển khai mới |
| application/javascript | Alias phổ biến, tương thích rộng |
| application/ecmascript, text/ecmascript | Alias lịch sử |
| application/x-javascript, text/x-javascript | Alias legacy |
| application/x-ecmascript, text/x-ecmascript | Alias legacy |
| text/javascript1.0 đến text/javascript1.5 | Tên lịch sử |
| text/jscript, text/livescript | Tên lịch sử |

Danh sách đầy đủ được định nghĩa trong MIME Sniffing Standard; bảng trên chỉ nêu các giá trị thường gặp. So sánh MIME essence đã parse, không tự suy ra từ extension hoặc substring.

Không tự tạo MIME type như text/js, application/x-my-javascript hoặc text/javascriptx rồi kỳ vọng browser coi đó là JavaScript MIME type. Một chuỗi trông giống tên JavaScript không đồng nghĩa là JavaScript MIME type hợp lệ.

### 2.4. Phân biệt JavaScript MIME với JSON

JSON thường được phục vụ với:

```http
Content-Type: application/json; charset=utf-8
```

JSON là dữ liệu, không phải JavaScript source. Khi dùng fetch() để lấy JSON, parse bằng response.json() hoặc JSON.parse() theo đúng contract. Không đổi Content-Type JSON thành text/javascript để làm response “dễ chạy”; việc đó mở rộng bề mặt thực thi và có thể tạo JSON hijacking hoặc script inclusion risk trong thiết kế cũ.

Một API trả JSON không nên biến thành endpoint JSONP bằng cách bọc dữ liệu vào callback tùy ý. JSONP là mô hình script execution cross-origin cũ, không phù hợp cho API mới.

## 3. Classic script và module script

### 3.1. Classic script

Classic script là script HTML truyền thống:

```html
<script src="/assets/app.js"></script>
<script type="text/javascript" src="/assets/legacy.js"></script>
```

Khi không có type hoặc type="text/javascript" (và một số alias tương thích), browser xử lý như classic JavaScript. async, defer, thứ tự tải và thời điểm thực thi ảnh hưởng cách script chạy nhưng không biến MIME type thành một loại khác.

Với classic external script, browser có lịch sử tương thích MIME lâu đời. Cách xử lý response không phải JavaScript MIME có thể phụ thuộc browser, request mode và nosniff. Vì vậy, không dựa vào MIME sniffing hoặc browser permissiveness để làm script hoạt động: server phải trả JavaScript MIME chính xác.

### 3.2. Module script

Module script được khai báo bằng:

```html
<script type="module" src="/assets/main.js"></script>
```

Module script áp dụng strict MIME type checking. Response phải có JavaScript MIME type; browser không dùng cơ chế nới lỏng của classic script để chấp nhận tùy tiện text/plain hoặc application/octet-stream. Nếu MIME sai, module bị từ chối và thường xuất hiện lỗi trong Console.

Module script mặc định được defer, chạy trong strict mode và có scope riêng. import/export tạo dependency graph; từng module dependency cũng phải được tải và kiểm tra MIME phù hợp. Một entry module có MIME đúng nhưng file dependency trả MIME sai vẫn khiến graph không tải thành công.

### 3.3. Bảng so sánh

| Thuộc tính | Classic script | Module script |
| --- | --- | --- |
| Khai báo | script src hoặc type="text/javascript" | type="module" |
| MIME | Phải trả JavaScript MIME; có lịch sử tương thích khác nhau | Strict JavaScript MIME check |
| CORS | Classic script cross-origin mặc định có thể tải ở no-CORS mode | Luôn dùng CORS mode |
| Dependency import | Không có cú pháp module import tĩnh | Có import/export và dependency graph |
| Scope | Thường chia sẻ global scope | Module scope |
| Strict mode | Phụ thuộc nội dung | Luôn strict mode |
| Thời điểm mặc định | Parser-blocking nếu không async/defer | Defer mặc định |

### 3.4. nosniff và strict MIME checking

Response header:

```http
X-Content-Type-Options: nosniff
```

Header này yêu cầu browser không MIME-sniff theo một số đường xử lý và chặn response không có MIME type phù hợp khi request destination là script hoặc stylesheet. Nó giúp ngăn một response text/plain/HTML bị browser diễn giải như script/style chỉ vì nội dung trông giống mã.

nosniff không sửa Content-Type sai; nó khiến lỗi cấu hình lộ rõ bằng cách browser chặn tài nguyên. Hãy sửa MIME ở server. Ngoài ra, nosniff không phải bộ lọc nội dung JavaScript và không ngăn script độc hại đã được phục vụ với JavaScript MIME hợp lệ.

## 4. MIME sniffing và cách browser diễn giải response

### 4.1. MIME sniffing là gì?

MIME sniffing là quá trình browser suy luận loại nội dung từ response bytes và context khi header thiếu, mơ hồ hoặc trong các trường hợp tương thích được định nghĩa. Đây là cơ chế lịch sử giúp web tiếp tục hoạt động dù server cấu hình MIME không chính xác.

Sniffing có thể gây rủi ro khi browser diễn giải nội dung theo cách server không dự định. Ví dụ, một file upload mà ứng dụng nghĩ là text/plain có thể chứa markup; nếu được mở trong context thực thi phù hợp và browser sniff thành HTML, nội dung có thể chạy script. Hành vi thực tế phụ thuộc request destination, response headers, browser và cách tài nguyên được điều hướng/tải.

### 4.2. Sniffing phụ thuộc request destination

Browser không xử lý mọi response theo một quy tắc chung. Một response được tải như script, stylesheet, image, document, font hoặc download có các thuật toán và kiểm tra khác nhau.

| Request destination | Ví dụ | Điều cần kiểm tra |
| --- | --- | --- |
| script | script src, module dependency | JavaScript MIME, nosniff, CORS nếu module/crossorigin |
| style | link rel=stylesheet | text/css và nosniff |
| document | điều hướng top-level, iframe | MIME document, sniffing, sandbox, CSP |
| image | img src | image MIME và image decoding |
| fetch/XHR | fetch API | Response MIME, parser do ứng dụng gọi, CORS |
| download | link tải file | Content-Disposition, Content-Type và nơi lưu/mở file |

Không suy ra rằng một header nosniff sẽ chặn mọi dạng MIME confusion trên mọi destination. Theo Fetch, tác dụng trực tiếp của nosniff tập trung vào request destination script và style. Điều hướng document và download cần thêm biện pháp riêng.

### 4.3. MIME essence và parameter

MIME type được parse thành type/subtype và parameters. Các parameter như charset không làm một media type không hợp lệ trở thành JavaScript MIME type. Ví dụ:

- text/javascript; charset=utf-8: JavaScript MIME hợp lệ.
- application/json; charset=utf-8: JSON data.
- text/plain; charset=utf-8: plain text, không phải JavaScript MIME.
- text/html; charset=utf-8: HTML document, không phải JavaScript MIME.
- application/octet-stream: binary generic, không phải JavaScript MIME.

Không kiểm tra header bằng cách tìm chuỗi con như "javascript" trong raw value. Hãy parse media type theo chuẩn, so sánh essence với danh sách JavaScript MIME types được công nhận và xử lý trường hợp header thiếu/lặp/malformed theo policy fail-closed.

### 4.4. nosniff không phải bộ lọc malware

Nếu response khai báo đúng text/javascript và chứa mã độc, browser vẫn có thể thực thi. nosniff không phân tích hành vi, không kiểm tra nguồn gốc nội dung và không xác thực publisher.

Các lớp bảo vệ khác nhau giải quyết vấn đề khác nhau:

- Content-Type đúng: khai báo loại representation.
- nosniff: ngăn một số đường MIME sniffing cho script/style.
- CSP: giới hạn nguồn và loại script được phép chạy.
- SRI: kiểm tra nội dung script/style khớp integrity metadata.
- CORS: kiểm soát quyền đọc response cross-origin và điều kiện fetch.
- Authorization: quyết định user có được phép lấy dữ liệu.
- Output encoding/safe DOM: ngăn input thành HTML/script trong ứng dụng.

### 4.5. Header bị thiếu hoặc bị ghi đè

Nếu origin trả đúng MIME nhưng CDN, object storage hoặc reverse proxy ghi đè header, browser chỉ thấy response cuối cùng. Vì vậy, kiểm tra qua URL production/staging sau tất cả intermediary. Không chỉ kiểm tra response từ localhost origin.

Header trùng lặp hoặc không hợp lệ có thể được proxy gộp, ghi đè hoặc từ chối khác nhau. Đặt một Content-Type rõ ràng ở nơi response được tạo; tránh gửi nhiều giá trị Content-Type và kiểm tra config gateway có sửa header.

## 5. Data block trong thẻ script

### 5.1. type không phải JavaScript MIME

Thẻ script có thể chứa data block thay vì JavaScript thực thi. Khi type attribute có giá trị không phải JavaScript MIME type và không phải loại script đặc biệt như module, browser xử lý phần tử theo data-block behavior của HTML thay vì chạy nội dung như JavaScript.

Ví dụ JSON nhúng:

```html
<script id="bootstrap-data" type="application/json">
{"theme":"light","pageSize":20}
</script>
```

JavaScript đọc text và parse:

```javascript
const node = document.querySelector("#bootstrap-data");
const config = JSON.parse(node.textContent);
console.log(config.theme);
```

type="application/json" không làm JSON thành executable script. Tuy nhiên, dữ liệu vẫn cần encode đúng khi được đưa vào HTML.

### 5.2. Rủi ro kết thúc script element

HTML parser nhận diện closing tag script ngay cả khi chuỗi đó xuất hiện bên trong nội dung text của script element. Nếu serialize dữ liệu không tin cậy thẳng vào data block, chuỗi chứa closing tag có thể kết thúc element sớm và chèn markup tiếp theo.

Ví dụ không an toàn:

```html
<script type="application/json" id="data">
{"comment":"</script><img src=x onerror=alert(1)>"}
</script>
```

Để nhúng JSON vào HTML, serialize theo quy tắc an toàn cho HTML script data: escape ký tự < thành Unicode escape \u003C (và cân nhắc escape >, &, U+2028/U+2029 tùy serializer). Tốt hơn, lấy JSON qua endpoint application/json và parse bằng fetch nếu không cần nhúng trực tiếp.

Không dùng regex tự chế để sanitize JSON. Dùng serializer có chế độ safe-for-HTML hoặc escape các ký tự có thể làm thay đổi trạng thái HTML parser.

### 5.3. Import map và speculation rules

HTML dùng một số type đặc biệt để nhúng dữ liệu điều khiển browser:

```html
<script type="importmap">
{
  "imports": {
    "app/": "/assets/app/"
  }
}
</script>

<script type="speculationrules">
{
  "prefetch": [
    { "source": "list", "urls": ["/next-page"] }
  ]
}
</script>
```

Các block này không phải JavaScript source thông thường. Import map định tuyến module specifier; speculation rules cung cấp gợi ý prefetch/prerender. Chúng vẫn là dữ liệu có ảnh hưởng hành vi browser, vì vậy không đưa nội dung do user kiểm soát vào mà không validate và serialize an toàn.

Khi dùng import map hoặc script data block, đừng gắn type="text/javascript" chỉ để browser đọc nội dung. Hãy dùng đúng loại script/data block theo HTML Standard và đúng MIME của file ngoài nếu loại đó được tải từ URL.

### 5.4. Không dùng JSONP cho API mới

JSONP tải response bằng classic script và thực thi callback trong trang gọi. Vì script inclusion có thể cross-origin và không dùng CORS response-read model như fetch, JSONP dễ tạo bề mặt thực thi và rủi ro callback injection.

Dùng fetch với CORS khi thật sự cần đọc API cross-origin. Xác thực/ủy quyền ở server; không xem CORS là xác thực. Không trả dữ liệu riêng tư dưới dạng JavaScript callback cho bất kỳ origin nào có thể nhúng script.

## 6. Cross-origin script, CORS và SRI

### 6.1. Classic script cross-origin

Classic script từ origin khác có thể được nhúng bằng script src mà không cần CORS response header trong chế độ no-CORS thông thường:

```html
<script src="https://cdn.example.test/library.js"></script>
```

Đây là khả năng web lâu đời để tải thư viện từ CDN. Tuy nhiên, việc browser cho phép tải và thực thi không có nghĩa trang gọi được quyền đọc response body qua fetch hoặc truy cập DOM của origin cung cấp script. Script sau khi chạy thực thi trong environment của trang nhúng, nên nếu CDN bị compromise hoặc nội dung script bị thay đổi, tác động có thể xảy ra trong origin của ứng dụng.

Cross-origin classic script cũng thường có error details hạn chế nếu không bật CORS. Thuộc tính crossorigin có thể yêu cầu CORS mode để browser nhận lỗi chi tiết hơn và hỗ trợ SRI cho tài nguyên cross-origin.

### 6.2. Module script luôn dùng CORS

Module script fetch dùng CORS mode, kể cả khi module ở cùng origin. Với module cross-origin, server cần trả Access-Control-Allow-Origin phù hợp:

```http
Access-Control-Allow-Origin: https://app.example.test
Content-Type: text/javascript; charset=utf-8
```

Nếu module server không cho phép origin gọi, browser chặn tải module. Mọi module dependency cross-origin trong graph cũng cần thỏa CORS. Cấu hình đúng ở entry module nhưng sai ở một dependency vẫn làm module graph thất bại.

Không dùng Access-Control-Allow-Origin: * với credentials. Nếu cần credentials, server phải trả origin cụ thể và Access-Control-Allow-Credentials: true; request cũng phải dùng credentials mode phù hợp.

### 6.3. crossorigin attribute

Ví dụ tải classic script cross-origin ở anonymous CORS mode:

```html
<script
  src="https://cdn.example.test/app-v4.js"
  crossorigin="anonymous">
</script>
```

Các giá trị thường dùng:

- anonymous: CORS request không gửi cross-origin credentials; same-origin credentials vẫn có thể được gửi theo quy tắc fetch.
- use-credentials: request dùng credentials mode include; server cần CORS response cho origin cụ thể và cho phép credentials.

Không thêm crossorigin tùy tiện nếu chưa hiểu ảnh hưởng tới cookie, CORS và CDN. Với script module, CORS mode đã là mặc định; thuộc tính crossorigin điều chỉnh credentials mode.

### 6.4. Subresource Integrity

SRI dùng integrity attribute để browser kiểm tra resource bytes khớp hash đã khai báo:

```html
<script
  src="https://cdn.example.test/library.min.js"
  integrity="sha384-BASE64_HASH_FROM_BUILD"
  crossorigin="anonymous">
</script>
```

Nếu bytes không khớp, browser không thực thi tài nguyên. Hash phải được tạo từ đúng artifact đã review và cập nhật cùng release. Placeholder hash không hoạt động; ví dụ trên chỉ minh họa cấu trúc.

Với cross-origin resource, SRI yêu cầu CORS check thành công; vì vậy thường cần crossorigin="anonymous" và server cho phép origin của ứng dụng. SRI bảo vệ khỏi thay đổi ngoài dự kiến của resource, nhưng không giúp nếu attacker có thể sửa cả file lẫn integrity hash trong HTML/build pipeline.

### 6.5. CORS không phải quyền thực thi hoặc authorization

CORS là cơ chế browser kiểm soát việc JavaScript đọc response cross-origin trong các request áp dụng CORS. Nó không xác thực người dùng, không quyết định script có được thực thi khi nhúng theo classic script no-CORS hay không, và không ngăn mọi request gửi tới server.

Với API riêng tư, luôn xác thực session/token và authorization ở server. Không dựa vào CORS để bảo vệ dữ liệu nếu endpoint vẫn trả nội dung cho request không có quyền. CORS allowlist cần so sánh origin chính xác, không dùng suffix matching dễ bị giả mạo.

## 7. Script MIME và các đường dẫn dẫn tới XSS

### 7.1. User upload được phục vụ như JavaScript

Nếu ứng dụng cho upload file rồi phục vụ file đó từ origin ứng dụng với JavaScript MIME type, file có thể được nhúng như script và thực thi trong context của trang. Việc kiểm tra extension hoặc client-supplied Content-Type là không đủ.

Các lỗi thường gặp:

- Tin filename .js hoặc MIME type do browser upload gửi lên.
- Dùng extension để gán text/javascript mà không kiểm tra loại asset được phép.
- Cho user upload file HTML/JS vào cùng origin với ứng dụng đăng nhập.
- Phản chiếu nội dung upload trong trang mà không encode.
- Dùng URL công khai có thể được nhúng bằng script src.
- Cho phép sửa asset đã được SRI/CSP tin cậy mà không cập nhật release integrity.

### 7.2. Tách origin cho nội dung không tin cậy

Phục vụ user content từ một origin/site riêng không chia sẻ session cookie với ứng dụng chính. Ví dụ ứng dụng chính ở app.example.test và file user ở user-content.example-cdn.test hoặc một domain độc lập do tổ chức kiểm soát.

Domain nội dung nên:

- Không nhận cookie session của app chính; không đặt Domain cookie rộng.
- Không có CORS allowlist rộng tới API riêng tư.
- Trả Content-Type đúng hoặc application/octet-stream cho file tải xuống.
- Dùng Content-Disposition: attachment khi nội dung cần tải về thay vì render.
- Dùng X-Content-Type-Options: nosniff cho tài nguyên phù hợp.
- Có CSP sandbox hoặc trang viewer cô lập nếu cần preview.
- Giới hạn loại file, dung lượng, scan malware và xử lý archive an toàn.

Tách origin giảm tác động của nội dung thực thi; vẫn cần kiểm soát link, redirect, preview, CORS và cách người dùng mở file.

### 7.3. Content-Disposition và MIME

Content-Disposition: attachment yêu cầu browser xử lý response như file tải xuống trong các trường hợp phù hợp:

```http
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="download.bin"
X-Content-Type-Options: nosniff
```

Đây là cấu hình thường dùng cho file không cần render inline. Nó không phải một bảo đảm tuyệt đối rằng file không bao giờ được mở bằng ứng dụng khác sau khi tải. Không phục vụ file không tin cậy dưới cùng origin với ứng dụng nhạy cảm chỉ vì đã thêm attachment.

Nếu sản phẩm cần preview, dùng viewer origin riêng, sandbox iframe chặt và chỉ bật capability cần thiết. Với HTML/SVG, xem chúng như nội dung có thể thực thi; không nhúng trực tiếp bằng innerHTML hoặc iframe cùng origin.

### 7.4. MIME đúng vẫn có thể là XSS

Attacker không cần MIME sniffing nếu có thể chèn mã vào file được phục vụ hợp lệ như text/javascript. Ví dụ một endpoint script tạo nội dung từ query parameter rồi trả JavaScript MIME có thể bị lợi dụng dù đã bật nosniff.

Do đó, cần kiểm soát cả nguồn nội dung và response type. Không tạo JavaScript bằng string concatenation từ input; không dùng eval/new Function; encode theo đúng output context; dùng safe DOM APIs; hạn chế script-src bằng CSP và áp dụng Trusted Types cho DOM sink khi phù hợp.

### 7.5. JSON không phải script nhưng có thể bị nhúng sai cách

API JSON nên trả application/json và yêu cầu authorization phù hợp. Không biến JSON thành script bằng cách đặt text/javascript. Nếu dữ liệu JSON được đặt trong script data block, cần serialize safe-for-HTML để chuỗi closing script không thoát khỏi block.

Các hệ thống legacy từng dùng JSON array hoặc JSONP để hỗ trợ script inclusion cross-origin. Không coi các kỹ thuật đó là ranh giới bảo mật; dùng CORS fetch, CSRF defense và authorization server-side.

## 8. Cấu hình server và security headers

### 8.1. Trả MIME chính xác từ origin

Node.js có thể đặt response header rõ ràng:

```javascript
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";

const server = createServer(async (request, response) => {
  if (request.url === "/assets/app.js") {
    const body = await readFile("./public/app.js");
    response.writeHead(200, {
      "Content-Type": "text/javascript; charset=utf-8",
      "X-Content-Type-Options": "nosniff",
      "Cache-Control": "public, max-age=31536000, immutable"
    });
    response.end(body);
    return;
  }

  response.writeHead(404);
  response.end("Not found");
});

server.listen(8080, "127.0.0.1");
```

Ví dụ này giả định file app.js là asset build bất biến có filename/version phù hợp. Nếu nội dung file có thể thay đổi tại cùng URL, không đặt immutable với TTL dài; dùng versioned filename hoặc freshness policy phù hợp.

### 8.2. Nginx

Ví dụ cấu hình:

```nginx
http {
    include       mime.types;
    default_type  application/octet-stream;

    types {
        text/javascript  js mjs;
    }

    server {
        listen 443 ssl;
        server_name app.example.test;

        add_header X-Content-Type-Options "nosniff" always;

        location /assets/ {
            try_files $uri =404;
            # A location-level add_header can stop inheriting server-level add_header directives.
            add_header X-Content-Type-Options "nosniff" always;
            add_header Cache-Control "public, max-age=31536000, immutable";
        }
    }
}
```

Kiểm tra file mime.types và thứ tự cấu hình trong hệ thống thực tế để tránh khai báo trùng hoặc bị location/server khác ghi đè. Đảm bảo MIME map cho .js và .mjs phù hợp với browser mục tiêu. Không dùng application/octet-stream cho mọi file script nếu browser cần JavaScript MIME.

### 8.3. Apache HTTP Server

Ví dụ cấu hình MIME mapping:

```apache
AddType text/javascript .js .mjs
Header always set X-Content-Type-Options "nosniff"
```

Cần bật module headers nếu dùng Header directive và kiểm tra VirtualHost/Directory/.htaccess có rule ghi đè. Kiểm tra response cuối bằng curl hoặc DevTools; cấu hình trong file chưa chứng minh header thực tế.

### 8.4. CSP giới hạn nguồn script

CSP có thể giới hạn nguồn script và yêu cầu nonce/hash:

```http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-RANDOM_PER_RESPONSE'; object-src 'none'; base-uri 'self'
X-Content-Type-Options: nosniff
```

Nonce phải được sinh ngẫu nhiên cho từng response, gắn đúng vào script được phép và không tái sử dụng giữa trang/session. Với ứng dụng phức tạp, cân nhắc strict-dynamic và hash theo threat model; tránh thêm unsafe-inline hoặc unsafe-eval chỉ để làm code cũ chạy mà chưa đánh giá.

CSP không sửa MIME sai và không kiểm tra nội dung file. Một script độc hại từ nguồn được CSP tin cậy vẫn có thể chạy; SRI, dependency pinning và bảo vệ build pipeline vẫn quan trọng.

### 8.5. Trusted Types và DOM sink

Trusted Types có thể yêu cầu dữ liệu đi qua policy được kiểm soát trước khi tới các DOM sink nguy hiểm như innerHTML. Ví dụ CSP:

```http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html
```

Trusted Types giảm một số đường DOM XSS nhưng không thay MIME validation, output encoding ở server hoặc CSP script-src. Không tạo policy trả nguyên input không tin cậy mà không sanitize; policy yếu có thể vô hiệu hóa lợi ích.

### 8.6. CORP và resource isolation

Cross-Origin-Resource-Policy (CORP) cho phép server khai báo resource có thể được nhúng bởi context nào trong các request no-CORS phù hợp:

- same-origin: chỉ context cùng origin được phép dùng resource theo CORP.
- same-site: cho phép cùng site theo policy của browser.
- cross-origin: cho phép nhúng cross-origin.

Ví dụ resource riêng tư không nên bị nhúng ngoài origin có thể trả:

```http
Cross-Origin-Resource-Policy: same-origin
X-Content-Type-Options: nosniff
```

Nếu ứng dụng cần tải script classic từ CDN trong no-CORS mode, CORP same-origin ở CDN có thể chặn tài nguyên. Chọn policy phù hợp với kiến trúc; module script và CORS resource có yêu cầu riêng. COEP: require-corp ở document còn yêu cầu tài nguyên cross-origin phải được tải qua CORS hoặc được cho phép bằng CORP.

### 8.7. Cache và deployment của script

Script public versioned có thể cache lâu:

```http
Content-Type: text/javascript; charset=utf-8
X-Content-Type-Options: nosniff
Cache-Control: public, max-age=31536000, immutable
```

Đặt filename có content hash hoặc version release. Khi deploy, HTML tham chiếu asset mới; không ghi đè nội dung tại URL immutable cũ. Nếu CDN/proxy thay đổi Content-Type, kiểm tra cả cache hit và miss; purge khi metadata bị cache sai.

## 9. Lab localhost: quan sát Script MIME trong browser

Lab chạy hai HTTP server trên loopback:

- Trang test: http://127.0.0.1:8080
- Script cross-origin: http://127.0.0.1:8081

Hai URL khác origin. Server thứ hai cho phép CORS với origin của trang test để so sánh classic script và module script. Lab không dùng domain Internet hoặc dữ liệu thật.

### 9.1. Tạo file script-mime-lab.mjs

```javascript
import { createServer } from "node:http";

function send(response, status, headers, body) {
  response.writeHead(status, headers);
  response.end(body);
}

const page = [
  "<!doctype html>",
  "<html lang='vi'>",
  "<head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>Script MIME lab</title></head>",
  "<body>",
  "<h1>Script MIME lab</h1>",
  "<p>Open DevTools Console and compare which scripts execute.</p>",
  "<pre id='results'>Waiting for scripts...</pre>",
  "<script>",
  "window.labResults = [];",
  "window.record = (name, result) => {",
  "  window.labResults.push({ name, result });",
  "  document.querySelector('#results').textContent = JSON.stringify(window.labResults, null, 2);",
  "};",
  "</script>",
  "<script src='/good.js'></script>",
  "<script src='/wrong.js'></script>",
  "<script src='/wrong-nosniff.js'></script>",
  "<script src='/html-nosniff.js'></script>",
  "<script type='module' src='/module-good.js'></script>",
  "<script type='module' src='/module-wrong.js'></script>",
  "<script src='http://127.0.0.1:8081/classic-cors.js' crossorigin='anonymous'></script>",
  "<script src='http://127.0.0.1:8081/classic-no-cors.js'></script>",
  "<script type='module' src='http://127.0.0.1:8081/module-cors.js'></script>",
  "<script type='module' src='http://127.0.0.1:8081/module-no-cors.js'></script>",
  "<script id='json-data' type='application/json'>",
  '{"message":"This is data, not executable JavaScript","count":3}',
  "</script>",
  "<script>",
  "const data = JSON.parse(document.querySelector('#json-data').textContent);",
  "record('json-data-block', data.message);",
  "window.addEventListener('load', () => record('page-load', 'Inspect Console and Network for blocked resources'));",
  "</script>",
  "</body>",
  "</html>"
].join("\n");

const sameOriginRoutes = {
  "/good.js": {
    type: "text/javascript; charset=utf-8",
    nosniff: true,
    body: 'record("classic-good", "executed");'
  },
  "/wrong.js": {
    type: "text/plain; charset=utf-8",
    nosniff: false,
    body: 'record("classic-wrong-mime", "executed despite text/plain");'
  },
  "/wrong-nosniff.js": {
    type: "text/plain; charset=utf-8",
    nosniff: true,
    body: 'record("classic-wrong-nosniff", "should be blocked");'
  },
  "/html-nosniff.js": {
    type: "text/html; charset=utf-8",
    nosniff: true,
    body: '<script>record("html-response", "must not execute as script");</script>'
  },
  "/module-good.js": {
    type: "text/javascript; charset=utf-8",
    nosniff: true,
    body: 'record("module-good", "executed"); export const version = 1;'
  },
  "/module-wrong.js": {
    type: "text/plain; charset=utf-8",
    nosniff: false,
    body: 'record("module-wrong", "must be rejected by strict module MIME check");'
  }
};

const appServer = createServer((request, response) => {
  const url = new URL(request.url, "http://127.0.0.1:8080");

  if (request.method !== "GET") {
    send(response, 405, { "Content-Type": "text/plain; charset=utf-8" }, "Method not allowed");
    return;
  }

  if (url.pathname === "/") {
    send(response, 200, {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff"
    }, page);
    return;
  }

  if (url.pathname === "/data.json") {
    send(response, 200, {
      "Content-Type": "application/json; charset=utf-8",
      "X-Content-Type-Options": "nosniff"
    }, JSON.stringify({ message: "JSON data" }));
    return;
  }

  const route = sameOriginRoutes[url.pathname];
  if (route) {
    const headers = { "Content-Type": route.type };
    if (route.nosniff) headers["X-Content-Type-Options"] = "nosniff";
    send(response, 200, headers, route.body);
    return;
  }

  send(response, 404, { "Content-Type": "text/plain; charset=utf-8" }, "Not found");
});

const crossOriginRoutes = {
  "/classic-cors.js": 'record("classic-cross-cors", "executed");',
  "/classic-no-cors.js": 'record("classic-cross-no-cors", "executed in no-CORS mode");',
  "/module-cors.js": 'record("module-cross-cors", "executed"); export const cross = true;',
  "/module-no-cors.js": 'record("module-cross-no-cors", "must be blocked without ACAO");'
};

const crossServer = createServer((request, response) => {
  const url = new URL(request.url, "http://127.0.0.1:8081");
  const body = crossOriginRoutes[url.pathname];

  if (request.method !== "GET" || !body) {
    send(response, 404, { "Content-Type": "text/plain; charset=utf-8" }, "Not found");
    return;
  }

  const headers = {
    "Content-Type": "text/javascript; charset=utf-8",
    "X-Content-Type-Options": "nosniff"
  };

  if (url.pathname !== "/classic-no-cors.js" &&
      url.pathname !== "/module-no-cors.js") {
    headers["Access-Control-Allow-Origin"] = "http://127.0.0.1:8080";
  }

  send(response, 200, headers, body);
});

appServer.listen(8080, "127.0.0.1", () => {
  console.log("Test page: http://127.0.0.1:8080");
});

crossServer.listen(8081, "127.0.0.1", () => {
  console.log("Cross-origin scripts: http://127.0.0.1:8081");
});
```

### 9.2. Chạy lab

Trong thư mục chứa file:

```bash
node script-mime-lab.mjs
```

Mở http://127.0.0.1:8080 trong browser. Mở DevTools → Console và Network. Reload trang sau khi mở DevTools để quan sát toàn bộ request.

### 9.3. Kết quả cần quan sát

| Script | Content-Type | nosniff | CORS | Kết quả cần kiểm tra |
| --- | --- | --- | --- | --- |
| good.js | text/javascript | Có | Same-origin | Classic script chạy |
| wrong.js | text/plain | Không | Same-origin | Quan sát browser có từ chối MIME hay không |
| wrong-nosniff.js | text/plain | Có | Same-origin | Bị chặn theo nosniff |
| html-nosniff.js | text/html | Có | Same-origin | Không thực thi như script |
| module-good.js | text/javascript | Có | Same-origin | Module chạy |
| module-wrong.js | text/plain | Không | Same-origin | Module bị strict MIME check từ chối |
| classic-cors.js | text/javascript | Có | ACAO cho localhost | Classic script chạy |
| classic-no-cors.js | text/javascript | Có | Không có ACAO | Classic script có thể chạy ở no-CORS mode |
| module-cors.js | text/javascript | Có | ACAO cho localhost | Module chạy |
| module-no-cors.js | text/javascript | Có | Không có ACAO | Module bị CORS check chặn |

Classic script sai MIME không có nosniff có lịch sử tương thích khác nhau giữa browser; ghi lại kết quả của browser/version đang kiểm thử. Không lấy trường hợp permissive làm cấu hình production. Module script luôn yêu cầu JavaScript MIME type và CORS cho cross-origin module fetch.

### 9.4. Kiểm tra JSON data block

Trong Console, kiểm tra kết quả json-data-block xuất hiện nhưng không có script nào chạy từ nội dung JSON. Mở endpoint /data.json trực tiếp hoặc dùng fetch để xem response Content-Type là application/json.

Thử thay JSON trong trang bằng dữ liệu chứa chuỗi closing script; quan sát vì sao serialize JSON an toàn cho HTML là cần thiết. Không dùng payload thực thi trên site bên ngoài; lab chỉ chạy loopback.

### 9.5. Dọn lab

Dừng Node process bằng Ctrl+C. Đóng tab và xóa file lab khi không còn cần. Server chỉ bind vào loopback; không expose cổng 8080/8081 ra mạng LAN hoặc Internet khi chạy thử.

## 10. Kiểm tra MIME trong pipeline và môi trường triển khai

### 10.1. Kiểm tra bằng curl

Dùng HEAD nếu server hỗ trợ đúng method, hoặc GET với response headers:

```bash
curl -I https://app.example.test/assets/app.js
curl -sS -D - -o /dev/null https://app.example.test/assets/app.js
```

Xác nhận tối thiểu:

- Status code đúng, không bị redirect sang trang login/HTML.
- Content-Type là JavaScript MIME type, thường text/javascript; charset=utf-8.
- X-Content-Type-Options là nosniff.
- Cache-Control phù hợp với asset versioned hay response động.
- CORS header đúng nếu module/SRI cross-origin cần.
- CORP không vô tình chặn cách nhúng được thiết kế.
- Content-Length/Content-Encoding phù hợp với response body.

HEAD và GET có thể đi qua middleware hoặc cache rule khác nhau. Khi điều tra lỗi, kiểm tra cả GET thực tế của browser, redirect chain và response cuối cùng.

### 10.2. Kiểm tra response qua CDN và reverse proxy

So sánh response trực tiếp từ origin với response public qua CDN/proxy. Nếu origin trả text/javascript nhưng edge trả application/octet-stream, lỗi nằm ở mapping/metadata hoặc transformation trung gian. Nếu response HIT khác MISS, kiểm tra cache metadata và purge sau khi sửa.

Đối với module graph, kiểm tra từng dependency URL. Một module có thể tải thành công nhưng import bên trong trả HTML 404/login page hoặc MIME sai. DevTools Network sẽ hiển thị URL lỗi và response Content-Type.

### 10.3. Build artifact và filename

Dùng asset pipeline tạo file .js/.mjs từ source và xuất ra thư mục static. Không cho upload tùy ý vào cùng namespace /assets/. Dùng filename có hash để cache dài hạn; đảm bảo mapping MIME cho cả .js và .mjs sau khi build/deploy.

Nếu server chỉ map .js mà quên .mjs, module có thể trả application/octet-stream. Kiểm tra MIME map của object storage/CDN và test trên đúng deployment target.

### 10.4. Phân biệt MIME error với lỗi JavaScript khác

Console có thể báo nhiều loại lỗi:

| Dấu hiệu | Nguyên nhân có thể |
| --- | --- |
| Refused to execute script because MIME type is not executable | Content-Type sai hoặc nosniff/strict check chặn |
| Failed to load module script | MIME sai, CORS lỗi, network/404 hoặc redirect |
| CORS policy blocked | ACAO/credentials không phù hợp |
| Integrity check failed | SRI hash không khớp resource bytes |
| Refused to load script due to CSP | script-src/nonce/hash không cho phép |
| SyntaxError | Response được tải nhưng source không hợp lệ |
| 404 trả HTML | URL sai hoặc auth redirect; browser nhận document thay script |

Không sửa lỗi MIME bằng cách nới CSP hoặc tắt nosniff. Xác định lớp nào từ chối và sửa header/route ở đúng nơi.

## 11. Ma trận kiểm thử Script MIME

Chạy trên các browser/version trong support matrix. Với mỗi test, lưu URL, request destination, status, Content-Type, nosniff, CORS, CSP/SRI nếu có và kết quả thực thi. Không lưu token hoặc response riêng tư trong test report.

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| SM-01 | Classic script có text/javascript | Thực thi thành công |
| SM-02 | Classic script có application/javascript | Tương thích theo browser; vẫn ưu tiên text/javascript |
| SM-03 | Classic script text/plain và nosniff | Browser chặn thực thi |
| SM-04 | Classic script text/plain không nosniff | Ghi nhận behavior từng browser; không dựa vào permissive behavior |
| SM-05 | Classic script application/octet-stream và nosniff | Browser chặn như script |
| SM-06 | Classic script response text/html và nosniff | Browser chặn như script |
| SM-07 | Module script text/javascript | Thực thi thành công |
| SM-08 | Module script text/plain | Strict MIME check từ chối |
| SM-09 | Module dependency có MIME sai | Module graph thất bại |
| SM-10 | Module cross-origin có ACAO hợp lệ | Tải thành công nếu các điều kiện khác đúng |
| SM-11 | Module cross-origin thiếu ACAO | CORS check chặn |
| SM-12 | Classic cross-origin no-CORS | Có thể tải/thực thi; không suy ra quyền đọc response |
| SM-13 | Classic cross-origin với crossorigin=anonymous | CORS response phải hợp lệ |
| SM-14 | SRI hash khớp | Resource được chấp nhận |
| SM-15 | SRI hash không khớp | Browser từ chối thực thi |
| SM-16 | SRI cross-origin thiếu CORS | Integrity fetch thất bại |
| SM-17 | Script bị CSP script-src chặn | Browser không thực thi |
| SM-18 | Script nonce đúng response | Chỉ script có nonce hợp lệ được phép theo policy |
| SM-19 | JSON data block application/json | Không thực thi như JavaScript |
| SM-20 | JSON data block chứa closing script không escape | Test xác nhận serializer không tạo parser breakout |
| SM-21 | Import map có type phù hợp | Browser parse map theo HTML rules |
| SM-22 | Response header Content-Type thiếu | Behavior được ghi nhận; server sửa để khai báo rõ |
| SM-23 | Content-Type có parameter charset UTF-8 | Essence vẫn được nhận diện đúng |
| SM-24 | MIME type tùy biến chứa substring javascript | Không được coi là JavaScript MIME hợp lệ |
| SM-25 | File .mjs qua CDN | Response có JavaScript MIME đúng |
| SM-26 | User upload HTML/SVG trên app origin | Không được phục vụ inline cùng origin tin cậy |
| SM-27 | User upload có Content-Type giả | Server dùng policy nội dung riêng, không tin client header |
| SM-28 | File tải về có attachment/octet-stream/nosniff | Browser xử lý theo download policy |
| SM-29 | 404/login redirect cho script URL | Pipeline phát hiện HTML/redirect thay vì JS |
| SM-30 | CDN cache HIT và MISS | Cả hai response giữ đúng MIME/security headers |

### 11.1. Kiểm thử hồi quy khi đổi MIME mapping

Khi thay đổi web server, CDN, object storage hoặc build pipeline, chạy lại ít nhất classic script, module script, module dependency, cross-origin module, SRI và file upload. Kiểm tra cả staging và production canary nếu quy trình phát hành cho phép.

## 12. Kiểm tra bằng DevTools

### 12.1. Network panel

1. Mở DevTools → Network.
2. Bật Preserve log và Disable cache trong lúc kiểm thử.
3. Reload trang để tải lại script.
4. Lọc theo JS hoặc nhập URL script.
5. Chọn request và xem Request Headers, Response Headers, status, initiator và timing.
6. Xác nhận Content-Type, X-Content-Type-Options, Access-Control-Allow-Origin, Cross-Origin-Resource-Policy và Cache-Control.
7. Mở Response để kiểm tra body thực tế; chú ý response HTML login/404 bị trả nhầm dưới URL .js.
8. Kiểm tra từng module dependency, không chỉ entry module.

### 12.2. Console

Console giúp phân biệt lỗi MIME, CORS, CSP, SRI, network và syntax. Đọc URL đầy đủ của resource bị từ chối; cùng một thông báo chung có thể đến từ response khác nhau. Nếu script bị block, xem Network để biết response status và headers.

### 12.3. Kiểm tra trực tiếp response

Có thể dùng Console để fetch cùng-origin script URL và xem header:

```javascript
const response = await fetch("/assets/app.js", { cache: "no-store" });
console.log({
  status: response.status,
  contentType: response.headers.get("content-type"),
  nosniff: response.headers.get("x-content-type-options")
});
```

Fetch chỉ đọc được response nếu same-origin hoặc CORS cho phép. Request này không thay thế kiểm tra request destination script: browser có thể áp dụng MIME check khác khi resource được nạp bằng script element/module loader.

### 12.4. Kiểm tra server response bằng curl

Nếu DevTools cho thấy response bị cache, dùng query cache-buster chỉ trong staging hoặc purge URL theo runbook để so sánh. Đừng thêm query tùy tiện vào production nếu query có thể thay đổi routing/cache key. Kiểm tra redirect bằng curl với và không theo redirect để biết server trả gì ở từng hop.

## 13. Những ngộ nhận thường gặp

**“File có đuôi .js thì browser sẽ chạy.”** Sai. Browser xét response, request destination, script kind và MIME policy; extension không quyết định thay cho Content-Type.

**“Content-Type application/json có thể dùng cho JavaScript vì JSON là subset của JavaScript.”** Sai. JSON là data representation; API nên trả application/json và được parse như dữ liệu.

**“nosniff làm mọi nội dung độc hại không thể chạy.”** Sai. Script độc hại có JavaScript MIME hợp lệ vẫn có thể chạy nếu các policy khác cho phép.

**“Module script và classic script có cùng MIME behavior.”** Sai. Module script áp dụng strict MIME checking và CORS mode; classic script có lịch sử tương thích khác.

**“CORS ngăn mọi cross-origin script execution.”** Sai. Classic script có thể được nhúng cross-origin ở no-CORS mode; CORS chủ yếu kiểm soát response access và module fetch.

**“Nếu script tải được từ CDN thì origin của CDN đáng tin.”** Sai. Script chạy trong context trang nhúng; CDN compromise hoặc supply-chain attack có thể ảnh hưởng ứng dụng.

**“SRI thay thế CSP.”** Sai. SRI xác minh bytes của resource cụ thể; CSP giới hạn nguồn/script execution policy. Hai cơ chế bổ sung nhau.

**“Content-Disposition attachment là đủ để cách ly upload.”** Sai. File vẫn có thể được mở bằng ứng dụng ngoài browser; cần origin riêng, MIME đúng, nosniff và policy preview/download.

**“nosniff chặn MIME confusion cho document và download.”** Sai. Tác dụng trực tiếp của nosniff tập trung vào script/style request; document/download cần biện pháp riêng.

**“JSON trong script type=application/json không có rủi ro.”** Sai. Parser HTML vẫn nhận diện closing script; serialize dữ liệu an toàn để ngăn thoát khỏi data block.

**“MIME đúng đồng nghĩa nội dung an toàn.”** Sai. Content-Type phân loại representation, không xác minh nội dung hoặc publisher.

## 14. Checklist triển khai Script MIME

Trước khi phát hành, xác nhận:

1. **JavaScript MIME:** script response dùng text/javascript; charset=utf-8.
2. **MIME map:** .js và .mjs được map đúng ở origin, proxy, CDN và object storage.
3. **nosniff:** trả X-Content-Type-Options: nosniff trên response phù hợp.
4. **Module graph:** entry và mọi dependency module có MIME hợp lệ.
5. **CORS:** module cross-origin được allowlist; credentials chỉ bật khi thực sự cần.
6. **Classic script:** hiểu rõ no-CORS behavior và không dựa vào MIME sniffing.
7. **SRI:** pin hash cho script CDN quan trọng và cập nhật cùng release.
8. **CSP:** script-src dùng nonce/hash/source allowlist; không nới unsafe-inline/unsafe-eval tùy tiện.
9. **Trusted Types:** bảo vệ DOM sink phù hợp và không tạo policy passthrough cho input không tin cậy.
10. **JSON:** API trả application/json; không dùng JSONP cho API mới.
11. **Data block:** serialize JSON safe-for-HTML, escape closing script breakout.
12. **Upload:** không tin extension/MIME do client gửi; tách user content khỏi app origin.
13. **Download:** dùng Content-Disposition attachment và MIME download phù hợp.
14. **Preview:** HTML/SVG không tin cậy chạy trong origin riêng hoặc sandbox chặt.
15. **CORS authorization:** server xác thực user và kiểm tra quyền; không coi CORS là auth.
16. **CORP/COEP:** chọn policy tương thích với kiến trúc nhúng tài nguyên.
17. **Headers:** không để CDN/proxy ghi đè Content-Type hoặc security headers ngoài ý muốn.
18. **Cache:** asset immutable có filename hash; response MIME/security header ổn định qua HIT/MISS.
19. **Monitoring:** log MIME mismatch, module load failure và CSP/SRI reports theo cách không chứa dữ liệu nhạy cảm.
20. **Testing:** chạy matrix trên browser/version mục tiêu, bao gồm upload và cross-origin.
21. **Release:** kiểm tra build artifact và response sau deploy, không chỉ config file.
22. **Incident response:** có thể rollback asset, purge cache, revoke publisher/dependency và điều tra script đã được tải.

## 15. Câu hỏi tự kiểm tra và ghi nhớ

**Câu 1.** MIME type khuyến nghị cho JavaScript là gì?  
**Đáp án:** text/javascript; charset=utf-8.

**Câu 2.** Content-Type có quyết định nội dung có an toàn không?  
**Đáp án:** Không. Nó khai báo loại representation, không xác minh publisher hoặc mã nguồn.

**Câu 3.** nosniff làm gì với script/style?  
**Đáp án:** Ngăn một số đường MIME sniffing và chặn response có MIME không phù hợp với request destination script/style.

**Câu 4.** Module script có strict MIME check không?  
**Đáp án:** Có. Response phải có JavaScript MIME type.

**Câu 5.** Module script cross-origin cần gì?  
**Đáp án:** CORS response hợp lệ cho origin gọi; mọi dependency cross-origin cũng cần thỏa.

**Câu 6.** Classic script cross-origin mặc định có cần ACAO không?  
**Đáp án:** Không trong no-CORS mode thông thường; nhưng response access, crossorigin mode và SRI có yêu cầu CORS riêng.

**Câu 7.** SRI xác minh điều gì?  
**Đáp án:** Bytes tải về khớp hash integrity đã khai báo.

**Câu 8.** JSON có nên trả text/javascript không?  
**Đáp án:** Không. JSON nên trả application/json và được parse như dữ liệu.

**Câu 9.** Vì sao JSON trong script data block vẫn cần escape?  
**Đáp án:** HTML parser vẫn nhận diện closing script và có thể kết thúc element sớm.

**Câu 10.** nosniff có ngăn XSS nếu script độc hại trả text/javascript không?  
**Đáp án:** Không. MIME hợp lệ vẫn có thể thực thi; cần phòng vệ injection, CSP, Trusted Types và kiểm soát nguồn script.

**Câu 11.** Vì sao user upload cần origin riêng?  
**Đáp án:** Để nội dung không tin cậy không chạy trong security principal/session của ứng dụng chính.

**Câu 12.** Content-Disposition attachment có thay thế origin isolation không?  
**Đáp án:** Không. Nó hỗ trợ download behavior nhưng không phải ranh giới bảo mật đầy đủ.

**Câu 13.** CORP same-origin ảnh hưởng gì tới script CDN?  
**Đáp án:** Có thể chặn resource được nhúng cross-origin trong no-CORS mode; policy phải phù hợp kiến trúc.

**Câu 14.** Vì sao cần kiểm tra module dependency?  
**Đáp án:** Mỗi module được fetch riêng và một dependency có MIME/CORS sai có thể làm cả module graph thất bại.

**Câu 15.** Khi Console báo MIME mismatch, nên sửa ở đâu?  
**Đáp án:** Kiểm tra response cuối cùng và sửa mapping/header ở origin, proxy, CDN hoặc object storage; không tắt nosniff để che lỗi.

Script MIME là một phần của contract giữa server và browser. Server phải khai báo đúng representation, browser kiểm tra theo loại script và request destination, còn ứng dụng phải bảo vệ nội dung trước khi nó trở thành mã thực thi. text/javascript và nosniff là baseline cần có; module script còn yêu cầu strict MIME và CORS khi cross-origin.

MIME đúng không làm mã an toàn. Hãy kết hợp CSP, SRI, Trusted Types, output encoding, authorization và origin isolation cho user content. Kiểm tra response thực tế sau CDN/proxy và mọi dependency của module graph.

**Browser chỉ nên thực thi resource khi loại nội dung, nguồn tải và nội dung thực tế đều phù hợp với chính sách của ứng dụng.**

### Tài liệu tham khảo

- [WHATWG — MIME Sniffing Standard](https://mimesniff.spec.whatwg.org/).
- [WHATWG — HTML Standard: The script element](https://html.spec.whatwg.org/multipage/scripting.html#the-script-element).
- [WHATWG — Fetch Standard](https://fetch.spec.whatwg.org/).
- [IETF RFC 9239 — Updates to ECMAScript Media Types](https://www.rfc-editor.org/rfc/rfc9239).
- [MDN — MIME types](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/MIME_types).
- [MDN — X-Content-Type-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Content-Type-Options).
- [MDN — JavaScript modules](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Modules).
- [MDN — Subresource Integrity](https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity).
- [MDN — Cross-Origin Resource Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cross-Origin-Resource-Policy).
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html).
- [OWASP — Unrestricted File Upload](https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload).
