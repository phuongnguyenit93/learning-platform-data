# Nội dung mixed content: vì sao trang HTTPS vẫn có thể tải tài nguyên không an toàn?

> **Chương:** HSTS và TLS  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

**Mixed content** xảy ra khi một tài liệu được tải an toàn qua HTTPS nhưng lại yêu cầu tài nguyên qua HTTP không mã hóa. Ví dụ, trang đăng nhập chạy trên HTTPS nhưng ảnh, stylesheet, script, iframe hoặc API của nó vẫn được tải bằng HTTP. Kết nối chính được mã hóa không bảo vệ được dữ liệu và hành vi của tài nguyên HTTP: kẻ đứng giữa đường truyền có thể quan sát hoặc sửa nội dung trước khi browser sử dụng nó.

Browser hiện đại thường chặn những loại mixed content có thể thực thi code hoặc thay đổi cấu trúc trang. Một số tài nguyên như ảnh, audio và video có thể được tự động nâng cấp từ HTTP sang HTTPS; nếu server không hỗ trợ HTTPS, tài nguyên sẽ không tải được. Cách xử lý bền vững là sửa URL và cấu hình mọi resource origin để dùng TLS hợp lệ, sau đó dùng HSTS và CSP như các lớp bổ sung.

Bài này giải thích cách nhận diện mixed content, phân biệt loại bị chặn với loại được tự động nâng cấp, hiểu giới hạn của HSTS và CSP, kiểm tra redirect và third-party dependency, rồi thực hành trên một trang HTTPS localhost.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Định nghĩa mixed content và giải thích vì sao HTTPS document tải HTTP resource vẫn có rủi ro.
2. Phân biệt blockable mixed content với các loại resource browser có thể tự động nâng cấp.
3. Nhận diện mixed content trong script, stylesheet, iframe, fetch/XHR, worker, WebSocket, ảnh, audio và video.
4. Phân biệt mixed content với insecure navigation và insecure download.
5. Giải thích vì sao CORS không cho phép tải tài nguyên HTTP từ trang HTTPS.
6. Dùng HSTS để buộc browser nâng cấp kết nối đến host đã có HSTS policy.
7. Dùng CSP upgrade-insecure-requests để nâng cấp URL HTTP trong tài liệu.
8. Xử lý URL hard-coded, CSS url(), redirect, CDN, API và nội dung do CMS/database lưu.
9. Kiểm tra mixed content bằng DevTools, Network, Console và một lab Node.js.

## 1. Mixed content là gì?

### 1.1 Trang HTTPS và tài nguyên HTTP

Giả sử người dùng truy cập:

~~~text
https://shop.example.com/account
~~~

Tài liệu chính được truyền qua TLS. Nhưng HTML lại chứa:

~~~html
<script src="http://cdn.example.net/app.js"></script>
<img src="http://images.example.net/logo.png" alt="Logo">
<iframe src="http://support.example.net/widget"></iframe>
~~~

Browser nhận một trang HTTPS nhưng một số request tài nguyên đi qua HTTP. HTTP không xác thực server và không bảo vệ tính toàn vẹn hay bí mật của response. Một attacker trên mạng có thể sửa script, thay ảnh, chèn nội dung hoặc quan sát dữ liệu được gửi qua request không mã hóa.

Nếu script HTTP bị sửa, attacker có thể chạy JavaScript trong origin của trang HTTPS. Khi đó script có thể thao tác DOM, đọc dữ liệu mà trang được phép đọc, thay form hoặc gửi request bằng quyền của phiên hiện tại. Vì vậy, một script HTTP trong trang HTTPS có thể phá vỡ lợi ích bảo mật của TLS đối với toàn bộ ứng dụng.

### 1.2 HTTPS của trang cha không tự biến URL HTTP thành an toàn

TLS bảo vệ từng kết nối tới từng host. Trang HTTPS chỉ được bảo vệ trên kết nối HTTPS của chính tài liệu đó. Một tài nguyên tải từ host khác qua HTTP vẫn là một kết nối không mã hóa.

Ví dụ:

~~~text
Browser
  |
  | HTTPS + TLS
  v
https://shop.example.com
  |
  | HTTP, không TLS
  v
http://cdn.example.net/app.js
~~~

Chứng chỉ TLS của shop.example.com không bảo vệ kết nối đến cdn.example.net. Mỗi origin/resource host cần có HTTPS hợp lệ và URL phải dùng HTTPS.

### 1.3 Mixed content có thể đến từ nhiều tầng

Không chỉ HTML viết trực tiếp mới tạo mixed content. URL HTTP có thể được sinh từ:

- Template server-side.
- CSS chứa url() hoặc @import.
- JavaScript tạo image, script, iframe hoặc fetch URL.
- API trả về URL ảnh hoặc link.
- CMS, rich text, bài viết hoặc cấu hình banner.
- Database lưu URL từ hệ thống cũ.
- CDN hoặc dịch vụ bên thứ ba redirect sang HTTP.
- Environment variable hoặc cấu hình build.
- Service worker/cache chứa HTML cũ.

Do đó, chỉ tìm chuỗi http:// trong một file HTML chưa đủ. Cần kiểm tra toàn bộ đường đi của resource trong browser.

## 2. Các loại mixed content

### 2.1 Blockable mixed content

Browser chặn các loại tài nguyên có thể thực thi code hoặc ảnh hưởng trực tiếp tới môi trường thực thi của trang. Những loại thường bị chặn gồm:

| Loại resource | Ví dụ | Rủi ro |
|---|---|---|
| JavaScript | script src qua HTTP, import script | Code có thể bị sửa và thực thi trong origin trang |
| Stylesheet | link rel=stylesheet qua HTTP, CSS import | CSS bị sửa, thay giao diện hoặc tạo tải tài nguyên khác |
| Iframe/frame | iframe src qua HTTP | Nhúng tài liệu không an toàn, có thể giả giao diện hoặc tương tác |
| Fetch/XHR | fetch hoặc XMLHttpRequest qua HTTP | Request/response không được TLS bảo vệ |
| Worker | Worker hoặc SharedWorker từ HTTP | Code worker có thể bị thay đổi |
| Object/embed | object hoặc embed qua HTTP | Nội dung/plugin không an toàn |
| WebSocket | ws:// từ tài liệu HTTPS | Kênh realtime không được mã hóa |
| Font và các resource thực thi/phụ thuộc | Font tải qua HTTP tùy loại request/browser | Nội dung resource có thể bị thay đổi |

Tên phân loại và hành vi cụ thể đã thay đổi theo phiên bản browser. Trong thực tế, hãy coi mọi request HTTP phát sinh từ trang HTTPS là lỗi cần sửa, kể cả khi một browser hiện tại tự động nâng cấp hoặc chặn nó.

### 2.2 Tài nguyên có thể được tự động nâng cấp

Browser hiện đại có thể tự động nâng cấp một số request ảnh, audio và video từ HTTP sang HTTPS trước khi tải. Ví dụ:

~~~html
<img src="http://images.example.net/banner.png" alt="Banner">
<audio src="http://media.example.net/intro.mp3" controls></audio>
<video src="http://media.example.net/demo.mp4" controls></video>
~~~

Browser có thể thử tải các URL tương ứng qua HTTPS. Nếu host hỗ trợ HTTPS và chứng chỉ hợp lệ, resource có thể tải thành công. Nếu host chỉ phục vụ HTTP, request HTTPS thất bại và nội dung không hiển thị.

Đây là cơ chế tương thích giúp giảm một số mixed content thụ động. Nó không phải lý do để giữ URL HTTP trong source code. Hãy sửa URL gốc sang HTTPS để tránh phụ thuộc vào hành vi tự nâng cấp của từng browser.

### 2.3 Không phải mọi resource đều được tự động nâng cấp giống nhau

Không giả định browser sẽ tự sửa mọi URL HTTP. Script, stylesheet, iframe, fetch/XHR và worker thường bị chặn thay vì tự động nâng cấp theo cơ chế mixed content mặc định. Directive CSP upgrade-insecure-requests có thể yêu cầu nâng cấp rộng hơn, nhưng cần bảo đảm đích HTTPS thực sự hoạt động.

Các browser có thể khác nhau về loại resource được nâng cấp và cách hiển thị cảnh báo. DevTools Console và Network là nơi xác nhận hành vi thực tế.

### 2.4 Insecure navigation và insecure download là trường hợp riêng

Một liên kết:

~~~html
<a href="http://legacy.example.net/">Mở trang cũ</a>
~~~

không nhất thiết là mixed content vì browser không tải tài liệu HTTP như một subresource của trang hiện tại; đó là một navigation do người dùng kích hoạt. Tuy nhiên, người dùng rời trang an toàn và truy cập một trang không được TLS bảo vệ.

Tương tự, tải file qua HTTP từ trang HTTPS có thể tạo cảnh báo insecure download. Đây là nhóm cảnh báo bảo mật liên quan nhưng không nên nhầm với quy tắc mixed subresource.

Hãy chuyển link và download sang HTTPS, đặc biệt với tài liệu, bản cập nhật, file thực thi hoặc nội dung có thể chứa thông tin nhạy cảm.

## 3. Browser xử lý mixed content như thế nào?

### 3.1 Request bị chặn trước khi ứng dụng sử dụng response

Khi browser nhận thấy một HTTPS document đang yêu cầu resource không an toàn thuộc loại bị chặn, nó có thể từ chối request. Ứng dụng không thể dùng CORS để yêu cầu browser bỏ qua quy tắc này.

Ví dụ:

~~~js
fetch('http://api.example.net/profile')
  .then(response => response.json());
~~~

Nếu code chạy trong HTTPS document, request HTTP có thể bị browser chặn như mixed content trước khi CORS có thể cho phép chia sẻ response. Server trả Access-Control-Allow-Origin cũng không biến HTTP thành TLS.

### 3.2 Redirect có thể tạo mixed content

URL ban đầu có thể là HTTPS nhưng server redirect sang HTTP:

~~~text
https://cdn.example.net/asset.js
        |
        | 302 Location: http://legacy.example.net/asset.js
        v
http://legacy.example.net/asset.js
~~~

Browser kiểm tra cả URL đích sau redirect. Nếu kết quả là tài nguyên HTTP không được phép, request sẽ bị chặn hoặc nâng cấp theo policy đang áp dụng.

Kiểm tra redirect chain trong DevTools Network và cấu hình CDN/load balancer. Sửa URL ban đầu nhưng giữ redirect HTTP ở phía server vẫn có thể khiến lỗi tồn tại.

### 3.3 HTTPS resource có chứng chỉ lỗi vẫn không an toàn

Chuyển từ http:// sang https:// chưa đủ nếu chứng chỉ:

- Hết hạn.
- Không khớp hostname.
- Không được browser tin cậy.
- Thiếu intermediate certificate cần thiết.
- Có cấu hình TLS không đáp ứng yêu cầu browser.

Không bỏ qua certificate warning trong production. Browser phải xác thực đúng server và hoàn tất TLS handshake.

### 3.4 localhost và môi trường phát triển

Browser thường coi localhost và loopback là potentially trustworthy trong nhiều API secure-context. Một số trường hợp HTTP localhost được miễn kiểm tra mixed content theo quy tắc secure origin.

Đây là ngoại lệ phục vụ phát triển. Không suy luận rằng HTTP trên một hostname nội bộ hoặc địa chỉ mạng LAN cũng an toàn. Kiểm thử production phải dùng domain HTTPS và chứng chỉ hợp lệ.

## 4. Mixed content và các cơ chế bảo mật khác

### 4.1 Mixed content và CORS

CORS trả lời câu hỏi: JavaScript từ origin A có được phép đọc response từ origin B hay không?

Mixed content trả lời câu hỏi: một HTTPS document có được phép tải resource không an toàn qua HTTP hay không?

| Tình huống | Cơ chế liên quan |
|---|---|
| HTTPS page tải HTTP script | Mixed content; browser chặn hoặc policy nâng cấp |
| HTTPS page fetch HTTPS API khác origin, cần đọc response | CORS |
| HTTPS page tải ảnh HTTPS cross-origin | SOP/canvas tainting và CORS tùy cách dùng |
| HTTP page fetch HTTPS API | CORS nếu cross-origin; request transport vẫn là HTTPS |
| HTTPS page fetch HTTP API | Mixed content trước; CORS không cứu được request |

### 4.2 Mixed content và SOP

SOP giới hạn cách script truy cập dữ liệu giữa các origin. Nhưng SOP không bảo vệ tính toàn vẹn của script HTTP được nhúng vào trang HTTPS: script đó chạy trong context của trang embedder sau khi được tải và thực thi.

Đây là lý do script HTTP nguy hiểm hơn một ảnh HTTP. Một ảnh thường không thực thi JavaScript; script có thể chạy với quyền của tài liệu.

### 4.3 Mixed content và CSP

CSP có directive:

~~~http
Content-Security-Policy: upgrade-insecure-requests
~~~

Browser được yêu cầu nâng cấp các URL tài nguyên không an toàn của tài liệu từ HTTP sang HTTPS trước khi tải. Điều này có thể giúp migration khi source còn chứa URL HTTP, nhưng chỉ hoạt động nếu host đích có HTTPS hợp lệ.

CSP cũng có thể giới hạn nguồn tải bằng các directive như default-src, script-src, img-src, connect-src và frame-src. Một policy nguồn hẹp giúp giảm số host mà trang có thể tải, nhưng không thay thế việc sửa URL HTTP.

Directive block-all-mixed-content từng được dùng để yêu cầu browser chặn mixed content, nhưng hiện không còn là lựa chọn cần thiết cho policy mới trong các browser hiện đại. Browser đã có cơ chế chặn hoặc nâng cấp mixed content; ưu tiên sửa URL và dùng upgrade-insecure-requests khi phù hợp.

### 4.4 Mixed content và HSTS

HSTS được server gửi qua HTTPS:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Browser ghi nhớ rằng host đó chỉ nên được truy cập bằng HTTPS trong thời gian max-age. Các request HTTP tới host có HSTS policy sẽ được nâng cấp sang HTTPS trước khi gửi trên mạng.

HSTS hữu ích khi:

- Ứng dụng có link hoặc request HTTP trỏ tới chính host đã bật HSTS.
- Host đã được browser ghi nhớ policy từ lần truy cập HTTPS trước.
- Domain nằm trong HSTS preload list, nếu đã đăng ký và đáp ứng yêu cầu.

Nhưng HSTS không thay thế kiểm kê mixed content:

- HSTS policy áp dụng theo host/domain đã khai báo, không tự bao phủ mọi third-party host.
- Trước lần đầu browser nhận HSTS, host chưa preload có thể chưa được bảo vệ khỏi lần truy cập HTTP đầu tiên.
- Một CDN hoặc API domain khác cần tự triển khai HSTS cho domain của nó.
- HSTS không sửa URL trong source, database hoặc CMS.
- Nếu host không phục vụ HTTPS hợp lệ, request được nâng cấp vẫn thất bại.

### 4.5 Upgrade-insecure-requests và HSTS khác nhau

| Thuộc tính | upgrade-insecure-requests | HSTS |
|---|---|---|
| Nơi khai báo | CSP response header của tài liệu | Strict-Transport-Security response header của host |
| Phạm vi | URL HTTP được tài liệu yêu cầu, kể cả nhiều host tài nguyên | Host đã gửi HSTS và subdomain nếu includeSubDomains |
| Thời gian | Áp dụng cho tài liệu nhận policy | Browser ghi nhớ theo max-age; có thể preload |
| Mục đích | Nâng cấp request insecure trong tài liệu | Buộc browser truy cập host qua HTTPS |
| Giới hạn | Không sửa link navigation nói chung; HTTPS endpoint phải tồn tại | Không bao phủ host bên thứ ba chưa có HSTS và không sửa source |

Hai cơ chế có thể cùng tồn tại. CSP nâng cấp request của tài liệu; HSTS củng cố việc truy cập HTTPS tới host đã tuyên bố chính sách.

## 5. Các nguồn tạo mixed content thường bị bỏ sót

### 5.1 HTML và template

Tìm các thuộc tính URL:

~~~html
<script src="http://..."></script>
<link rel="stylesheet" href="http://...">
<img src="http://...">
<iframe src="http://..."></iframe>
<video poster="http://..."></video>
<form action="http://..."></form>
~~~

Một số URL là navigation hoặc form submission thay vì mixed subresource, nhưng vẫn cần kiểm tra và chuyển sang HTTPS.

### 5.2 CSS

CSS có thể tải tài nguyên phụ:

~~~css
.hero {
  background-image: url("http://images.example.net/hero.jpg");
}

@import url("http://cdn.example.net/theme.css");
~~~

Một stylesheet HTTPS có thể tham chiếu ảnh hoặc stylesheet HTTP. Kiểm tra cả CSS bundle, CSS-in-JS, theme và style được CMS tạo.

### 5.3 JavaScript

Code có thể tạo URL khi chạy:

~~~js
const image = new Image();
image.src = 'http://images.example.net/avatar.png';

fetch('http://api.example.net/data');

const socket = new WebSocket('ws://stream.example.net/events');
~~~

Sửa source/config để dùng HTTPS và WSS. Đừng chỉ sửa markup vì request có thể phát sinh sau khi người dùng tương tác.

### 5.4 API và nội dung trong database

API HTTPS có thể trả JSON chứa URL HTTP. Browser sau đó tải URL đó như ảnh hoặc media. Vì vậy, server API đã chạy HTTPS chưa bảo đảm mọi URL trong response đều an toàn.

Rà soát:

- URL ảnh avatar và banner.
- URL video/audio trong bài viết.
- Link được biên tập viên nhập trong CMS.
- URL callback hoặc endpoint do tenant cấu hình.
- Link được import từ hệ thống legacy.
- Dữ liệu cache cũ và HTML đã render trước khi migration.

Chuẩn hóa URL khi ghi dữ liệu và kiểm tra lại tại output boundary. Không tự động thay scheme cho URL của mọi host nếu chưa xác nhận host đó hỗ trợ HTTPS.

### 5.5 Third-party dependency

Analytics, tag manager, CAPTCHA, chat widget, payment SDK, CDN, font provider và video embed có thể tải thêm resource từ host phụ. Một script chính tải qua HTTPS vẫn có thể tạo request HTTP ở runtime.

Kiểm tra request tree trong Network và yêu cầu nhà cung cấp sửa toàn bộ redirect/resource chain. Nếu không thể dùng HTTPS, đánh giá thay thế hoặc bỏ tích hợp khỏi trang nhạy cảm.

## 6. Cách sửa mixed content

### 6.1 Sửa URL gốc sang HTTPS

Đây là cách tốt nhất khi server đích hỗ trợ TLS:

~~~html
<!-- Trước -->
<img src="http://images.example.net/logo.png" alt="Logo">

<!-- Sau -->
<img src="https://images.example.net/logo.png" alt="Logo">
~~~

Sửa ở source/template/CMS/config để request ngay từ đầu dùng HTTPS. Không phụ thuộc vào browser tự nâng cấp.

### 6.2 Dùng URL tương đối khi phù hợp

Nếu resource cùng host với tài liệu, URL path tương đối tránh hard-code scheme:

~~~html
<script src="/assets/app.js"></script>
<img src="/assets/logo.svg" alt="Logo">
~~~

URL này dùng scheme và host của document hiện tại. Cách này phù hợp cho resource cùng origin. Không dùng protocol-relative URL dạng //cdn.example.net nếu mục tiêu là ép HTTPS rõ ràng; URL đó vẫn phụ thuộc scheme của tài liệu và khó audit hơn.

### 6.3 Sửa API và WebSocket

~~~js
// HTTPS API
const response = await fetch('https://api.example.net/profile');

// Secure WebSocket
const socket = new WebSocket('wss://stream.example.net/events');
~~~

Đảm bảo API và WebSocket endpoint có chứng chỉ TLS hợp lệ, proxy hỗ trợ TLS và CORS được cấu hình nếu request cross-origin cần đọc response.

### 6.4 Dùng CSP upgrade-insecure-requests trong migration

Có thể triển khai:

~~~http
Content-Security-Policy: upgrade-insecure-requests
~~~

Browser nâng cấp request HTTP của tài liệu sang HTTPS trước khi tải. Directive này hữu ích khi chưa thể sửa ngay tất cả URL được sinh ra từ template hoặc dữ liệu cũ.

Giới hạn cần nhớ:

- Host đích phải phục vụ HTTPS với chứng chỉ hợp lệ.
- URL HTTP trong navigation do người dùng bấm không được biến thành một navigation HTTPS chung theo cách có thể thay thế việc sửa link.
- Resource có port tùy chỉnh vẫn cần TLS tại port tương ứng sau khi nâng scheme.
- Redirect cuối cùng sang HTTP vẫn phải xử lý.
- Không coi directive này là thay thế cho sửa source và dữ liệu.

Khi dùng directive này, hãy kiểm thử staging, xem Console/Network và theo dõi resource nào thất bại sau nâng cấp.

### 6.5 Bật HSTS sau khi HTTPS đã sẵn sàng

Ví dụ:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Chỉ bật includeSubDomains khi mọi subdomain thuộc phạm vi đều hỗ trợ HTTPS ổn định. HSTS chỉ được browser chấp nhận từ response HTTPS hợp lệ; gửi header này qua HTTP không có tác dụng.

Preload là cam kết triển khai dài hạn và có quy trình/điều kiện riêng. Không thêm preload chỉ để xử lý một vài mixed content URL. Đảm bảo redirect HTTP→HTTPS, chứng chỉ và mọi subdomain đã sẵn sàng trước khi đăng ký.

## 7. Kiểm tra mixed content trong DevTools

### 7.1 Console

Mở trang HTTPS và DevTools → Console. Tìm thông báo:

- Mixed Content: The page was loaded over HTTPS, but requested an insecure resource.
- Mixed Content: The request has been blocked.
- Automatically upgraded insecure request.
- Failed to load resource sau khi browser nâng cấp sang HTTPS.
- WebSocket connection to ws://... failed.

Console thường nêu URL resource và loại xử lý. Dùng URL này để tìm nguồn trong HTML, CSS, JavaScript hoặc response API.

### 7.2 Network

Trong DevTools → Network:

1. Reload trang với cache disabled.
2. Lọc theo Img, JS, CSS, Fetch/XHR, Media, WS và Doc.
3. Kiểm tra Request URL và redirect chain.
4. Xác định scheme HTTP hay HTTPS.
5. Kiểm tra status, blocked reason và response headers.
6. Với resource auto-upgrade, xem browser đã đổi request sang HTTPS chưa.
7. Với WebSocket, kiểm tra URL ws/wss và handshake.

Không chỉ xem document chính có status 200 và HTTPS. Một trang có thể tải thành công nhưng một số resource quan trọng đã bị chặn.

### 7.3 Kiểm tra source

Có thể tìm dấu hiệu URL insecure trong repository:

~~~bash
rg -n -i 'http://|ws://' src public templates styles
~~~

Kết quả cần được phân loại thủ công:

- URL test/example không được deploy.
- URL navigation mà người dùng chủ động mở.
- URL resource thực sự được tải.
- URL nằm trong dữ liệu fixture hoặc migration.
- URL do API/CMS trả về.
- URL đã được browser nâng cấp nhưng source vẫn cần sửa.

Regex không thay thế kiểm tra Network; URL có thể được ghép từ nhiều phần hoặc lấy từ runtime data.

### 7.4 Kiểm tra response và redirect

Dùng Network hoặc công cụ HTTP để xem:

- Redirect từ HTTPS sang HTTP.
- Location header của CDN.
- HSTS header trên từng host.
- TLS certificate và hostname.
- CSP header của document.
- Cache/service worker có trả HTML cũ không.

Sau khi sửa, xóa cache phù hợp, cập nhật service worker và kiểm tra lại trong browser sạch để tránh kết quả cũ.

## 8. Thực hành: quan sát mixed content bằng Node.js

Lab tạo một trang HTTPS ở localhost và resource server HTTP riêng. Một ảnh trỏ đến cổng HTTPS khác để quan sát browser tự nâng cấp ảnh; script, stylesheet, iframe và fetch trỏ đến HTTP server để quan sát hành vi block. Dùng chứng chỉ localhost được browser tin cậy; không dùng chứng chỉ tự ký chưa được tin cậy để kết luận hành vi production.

### 8.1 Chuẩn bị chứng chỉ localhost

Nếu đã cài mkcert:

~~~bash
mkcert -install
mkcert -key-file localhost-key.pem -cert-file localhost-cert.pem localhost 127.0.0.1 ::1
~~~

Lệnh tạo hai file:

- localhost-key.pem
- localhost-cert.pem

Chạy các lệnh trong thư mục lab. Nếu không dùng mkcert, có thể dùng chứng chỉ phát triển do hệ điều hành/browser tin cậy; chứng chỉ self-signed chưa trust có thể gây lỗi TLS riêng, làm sai kết quả mixed content.

### 8.2 Tạo file mixed-content-lab.mjs

~~~js
import { createServer as createHttpServer } from 'node:http';
import { createServer as createHttpsServer } from 'node:https';
import { readFileSync } from 'node:fs';

const key = readFileSync('./localhost-key.pem');
const cert = readFileSync('./localhost-cert.pem');

const page = [
  '<!doctype html>',
  '<html lang="vi">',
  '<head>',
  '<meta charset="utf-8">',
  '<title>Mixed content lab</title>',
  '<link rel="stylesheet" href="http://localhost:3001/style.css">',
  '</head>',
  '<body>',
  '<h1>HTTPS page with HTTP resources</h1>',
  '<p>Ảnh này dùng HTTP URL ở port 3444; browser có thể tự nâng cấp sang HTTPS.</p>',
  '<img src="http://localhost:3444/pixel.svg" alt="Auto-upgrade image">',
  '<p>Script, stylesheet, iframe và fetch bên dưới trỏ tới HTTP port 3001.</p>',
  '<script src="http://localhost:3001/app.js"></script>',
  '<iframe src="http://localhost:3001/frame" title="HTTP frame"></iframe>',
  '<button id="fetch" type="button">Thử fetch HTTP</button>',
  '<pre id="result">Chưa thử fetch.</pre>',
  '<script>',
  'document.querySelector("#fetch").addEventListener("click", async () => {',
  '  try {',
  '    await fetch("http://localhost:3001/api");',
  '    document.querySelector("#result").textContent = "Fetch hoàn tất.";',
  '  } catch (error) {',
  '    document.querySelector("#result").textContent = error.name + ": " + error.message;',
  '  }',
  '});',
  '</script>',
  '<a href="http://localhost:3001/landing">Navigation HTTP (chỉ tải khi bấm)</a>',
  '</body></html>'
].join('\n');

const httpResources = createHttpServer((req, res) => {
  if (req.url === '/style.css') {
    res.writeHead(200, { 'Content-Type': 'text/css' });
    return res.end('body { background: #f5f5f5; }');
  }

  if (req.url === '/app.js') {
    res.writeHead(200, { 'Content-Type': 'text/javascript' });
    return res.end('console.log("HTTP script executed");');
  }

  if (req.url === '/frame') {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    return res.end('<p>HTTP iframe content</p>');
  }

  if (req.url === '/api') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end('{"ok":true}');
  }

  res.writeHead(200, { 'Content-Type': 'text/html' });
  res.end('<h1>HTTP navigation destination</h1>');
});

const httpsResources = createHttpsServer({ key, cert }, (req, res) => {
  if (req.url === '/pixel.svg') {
    res.writeHead(200, {
      'Content-Type': 'image/svg+xml',
      'Cache-Control': 'no-store'
    });
    return res.end(
      '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="60">' +
      '<rect width="120" height="60" fill="green"/>' +
      '<text x="8" y="35" fill="white">HTTPS image</text>' +
      '</svg>'
    );
  }

  res.writeHead(404);
  res.end('Not found');
});

const httpsPage = createHttpsServer({ key, cert }, (req, res) => {
  if (req.url !== '/') {
    res.writeHead(404);
    return res.end('Not found');
  }

  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store'
  });
  res.end(page);
});

httpResources.listen(3001, 'localhost', () => {
  console.log('HTTP resources: http://localhost:3001');
});

httpsPage.listen(3443, 'localhost', () => {
  console.log('HTTPS page: https://localhost:3443');
});

httpsResources.listen(3444, 'localhost', () => {
  console.log('HTTPS image: https://localhost:3444/pixel.svg');
});
~~~

### 8.3 Chạy lab

~~~bash
node mixed-content-lab.mjs
~~~

Mở:

~~~text
https://localhost:3443
~~~

Quan sát:

- Trang chính tải qua HTTPS.
- Ảnh HTTP ở port 3444 có thể được browser nâng cấp sang HTTPS và tải thành công vì HTTPS image server chạy ở cùng port.
- Stylesheet, script, iframe và fetch trỏ tới HTTP port 3001 thường bị browser chặn như mixed content.
- Link navigation HTTP không tải cho đến khi người dùng bấm; đó là navigation, không phải mixed subresource.
- Console và Network cho biết resource nào bị chặn hoặc nâng cấp.

Nếu browser không tin chứng chỉ localhost, sửa trust trước khi đánh giá kết quả. Không tắt bảo vệ mixed content để làm lab.

### 8.4 Thử upgrade-insecure-requests

Có thể thêm header vào response HTTPS page:

~~~http
Content-Security-Policy: upgrade-insecure-requests
~~~

Sau khi thêm, browser sẽ thử nâng cấp nhiều request HTTP của tài liệu sang HTTPS. Trong lab, các URL ở port 3001 sẽ được đổi sang HTTPS port 3001 nhưng server đó chỉ chạy HTTP, nên request sẽ thất bại vì không có TLS listener. Đây là minh họa rằng directive chỉ nâng scheme; nó không tự cài TLS cho server.

Để kiểm tra thành công, resource host và port đích phải thực sự phục vụ HTTPS với certificate hợp lệ. Sau thử nghiệm, bỏ header nếu cần so sánh hành vi mặc định.

## 9. Chẩn đoán lỗi

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Script HTTP bị chặn | Active mixed content | Host script qua HTTPS và sửa URL nguồn |
| Ảnh biến mất dù browser tự nâng cấp | Host ảnh không phục vụ HTTPS hoặc certificate lỗi | Cấu hình TLS cho image host, cập nhật URL |
| HTTPS page gọi API HTTP thất bại | Mixed content trước khi CORS xử lý | Dùng HTTPS API; sau đó cấu hình CORS nếu cross-origin |
| WebSocket không kết nối | Code dùng ws:// từ HTTPS page | Chuyển sang wss:// và cấu hình TLS reverse proxy |
| URL bắt đầu bằng HTTPS nhưng vẫn bị chặn | Redirect chain kết thúc ở HTTP hoặc TLS lỗi | Kiểm tra toàn bộ redirect và certificate |
| Một số ảnh tự tải được, một số bị chặn | Browser auto-upgrade nhưng host không hỗ trợ HTTPS | Sửa URL và triển khai TLS đồng bộ |
| CSS HTTPS vẫn tạo mixed content | CSS chứa url() hoặc @import HTTP | Kiểm tra dependency CSS và sửa URL |
| CMS tiếp tục sinh URL HTTP | Database/template cũ hoặc editor lưu URL tuyệt đối | Migration dữ liệu và chuẩn hóa khi ghi |
| HSTS không sửa được resource bên thứ ba | Host đó chưa có HSTS hoặc chưa preload | Yêu cầu provider bật HTTPS/HSTS hoặc thay resource |
| CSP upgrade-insecure-requests làm resource lỗi | URL được nâng scheme nhưng endpoint không có TLS | Cấu hình HTTPS tại đúng host/port |
| Console không báo nhưng source còn http:// | Browser có thể auto-upgrade hoặc URL chưa được thực thi trong luồng thử | Audit source và test các luồng đầy đủ |
| Localhost hoạt động nhưng production lỗi | Localhost có ngoại lệ potentially trustworthy | Kiểm tra bằng hostname production và TLS thật |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Mixed content xảy ra khi nào?

**Đáp án:** Khi một tài liệu được tải qua HTTPS yêu cầu tài nguyên qua HTTP không mã hóa, ví dụ script, ảnh, stylesheet hoặc API.

**Câu 2.** Vì sao HTTP script trong trang HTTPS nguy hiểm?

**Đáp án:** Script có thể bị sửa trên đường truyền rồi thực thi trong origin của trang HTTPS, cho phép attacker thao tác DOM và request bằng quyền của trang.

**Câu 3.** Browser thường xử lý active mixed content như thế nào?

**Đáp án:** Thường chặn các resource có thể thực thi code hoặc tạo browsing context như script, stylesheet, iframe, fetch/XHR và worker; hành vi cụ thể phụ thuộc browser/version.

**Câu 4.** Vì sao ảnh HTTP đôi khi vẫn hiển thị trên trang HTTPS?

**Đáp án:** Browser hiện đại có thể tự động nâng cấp một số ảnh/audio/video sang HTTPS. Nếu host không có HTTPS hợp lệ, resource sẽ thất bại.

**Câu 5.** CORS có thể cho phép HTTPS page tải HTTP script không?

**Đáp án:** Không. Mixed content là giới hạn về transport/security của browser; CORS không biến HTTP thành HTTPS.

**Câu 6.** HSTS bảo vệ host nào?

**Đáp án:** Host đã gửi HSTS policy qua HTTPS; includeSubDomains mở rộng tới subdomain. Host bên thứ ba cần policy riêng hoặc preload phù hợp.

**Câu 7.** upgrade-insecure-requests khác HSTS thế nào?

**Đáp án:** CSP nâng cấp request HTTP của tài liệu; HSTS ghi nhớ yêu cầu truy cập HTTPS cho host/domain đã khai báo.

**Câu 8.** Một HTTPS URL redirect sang HTTP có thể gây mixed content không?

**Đáp án:** Có. Browser đánh giá đích cuối cùng; redirect HTTP có thể bị chặn hoặc xử lý theo policy.

**Câu 9.** Link anchor HTTP có luôn là mixed content không?

**Đáp án:** Không. Navigation do người dùng kích hoạt không phải subresource mixed content, nhưng vẫn đưa người dùng tới kết nối không an toàn.

**Câu 10.** Vì sao không nên dựa vào localhost để kết luận production không có mixed content?

**Đáp án:** Browser có thể coi localhost/loopback là potentially trustworthy cho phát triển. Cần kiểm tra trên hostname production với HTTPS và chứng chỉ hợp lệ.

## 11. Checklist loại bỏ mixed content

Trước khi phát hành trang HTTPS, hãy kiểm tra:

1. **Document:** mọi trang HTML quan trọng được phục vụ qua HTTPS.
2. **HTML:** script, stylesheet, image, iframe, media, form và các URL động đã được rà soát.
3. **CSS:** kiểm tra url(), @import, CSS-in-JS và stylesheet từ CMS.
4. **JavaScript:** kiểm tra fetch, XHR, Worker, WebSocket, dynamic script/image và endpoint cấu hình.
5. **Runtime data:** kiểm tra URL từ API, database, CMS, cache và dữ liệu import.
6. **Redirect:** không có resource HTTPS redirect xuống HTTP.
7. **TLS:** mọi resource host dùng HTTPS có certificate hợp lệ và hostname khớp.
8. **Third party:** CDN, analytics, CAPTCHA, payment, chat và font provider đã hỗ trợ HTTPS.
9. **CSP:** dùng upgrade-insecure-requests như biện pháp migration khi phù hợp; giữ source policy hẹp.
10. **HSTS:** bật sau khi toàn bộ host/subdomain trong phạm vi đã sẵn sàng HTTPS.
11. **Navigation/download:** chuyển link và file download nhạy cảm sang HTTPS.
12. **DevTools:** Console không còn mixed content warning; Network không còn request HTTP không chủ ý.
13. **Automation:** quét source và kiểm thử browser trên staging/production-like hostname.
14. **Regression:** kiểm tra lại sau khi thêm SDK, CDN, nội dung CMS hoặc route mới.

**Ghi nhớ:** Một trang HTTPS chỉ bảo vệ đầy đủ khi tài nguyên mà nó sử dụng cũng được tải an toàn. Browser có thể chặn active mixed content hoặc tự nâng cấp một số resource thụ động, nhưng đó là cơ chế giảm rủi ro trong quá trình tương thích. Hãy sửa URL tại nguồn, bảo đảm TLS cho từng host, dùng CSP để hỗ trợ migration và HSTS để buộc browser tiếp tục dùng HTTPS.

## Tài liệu tham khảo

- [MDN — Mixed content](https://developer.mozilla.org/en-US/docs/Web/Security/Mixed_content)
- [W3C — Mixed Content](https://www.w3.org/TR/mixed-content/)
- [MDN — upgrade-insecure-requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy/upgrade-insecure-requests)
- [MDN — Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security)
- [OWASP — Transport Layer Protection Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Protection_Cheat_Sheet.html)
- [Chrome for Developers — Mixed content](https://developer.chrome.com/blog/mixed-content-autoupgrade)

