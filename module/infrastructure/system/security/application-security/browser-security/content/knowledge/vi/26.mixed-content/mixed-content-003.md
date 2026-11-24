# Mixed content blocking

**Mixed content** xảy ra khi một trang được tải an toàn qua **HTTPS** nhưng lại yêu cầu tài nguyên hoặc nội dung qua **HTTP** không mã hóa. Ví dụ, trang HTTPS của ứng dụng tải JavaScript từ CDN qua HTTP, tải ảnh từ HTTP hoặc gọi API bằng fetch tới endpoint HTTP. Kết nối của trang chính được bảo vệ, nhưng một phần nội dung đi qua kết nối không được mã hóa và có thể bị bên thứ ba trên đường truyền đọc hoặc sửa đổi.

Browser hiện đại chủ động **chặn mixed content có khả năng thực thi hoặc thay đổi hành vi trang**. Một số loại nội dung như ảnh, âm thanh và video có thể được tự động nâng cấp từ HTTP lên HTTPS; nếu endpoint HTTPS không hoạt động, browser sẽ chặn tải. Các cơ chế này bảo vệ tính toàn vẹn của trang HTTPS, nhưng không thể tự sửa một endpoint HTTP chưa có HTTPS.

Bài học thuộc chương **Mixed content** trong module **Browser Security** (SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY). Nội dung phân tích ranh giới giữa browser, origin, cookie và ứng dụng web; tập trung vào phân loại mixed content, cách browser block/upgrade request, CSP upgrade-insecure-requests, HSTS và cách kiểm chứng bằng DevTools.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích mixed content và rủi ro khi trang HTTPS tải nội dung HTTP.
2. Phân biệt **blockable mixed content** với nội dung có thể tự động nâng cấp (upgradable/optionally blockable).
3. Nhận diện script, stylesheet, iframe, font, fetch/XHR, WebSocket và media trong các nhóm xử lý.
4. Giải thích browser tự nâng cấp ảnh/âm thanh/video và điều gì xảy ra khi endpoint HTTPS không tồn tại.
5. Phân tích ảnh hưởng của redirect từ HTTPS sang HTTP.
6. Cấu hình CSP upgrade-insecure-requests và hiểu giới hạn của nó.
7. Phân biệt upgrade-insecure-requests, HSTS và directive cũ block-all-mixed-content.
8. Phân biệt mixed content với form submission không an toàn, insecure navigation và mixed download.
9. Dùng DevTools và Node.js lab với một trang HTTPS cùng máy chủ tài nguyên HTTP để kiểm tra hành vi browser.

## 2. Mixed content hình thành như thế nào?

HTTPS bảo vệ dữ liệu giữa browser và server bằng TLS. Browser xác minh chứng chỉ server và mã hóa dữ liệu trên đường truyền. Nhưng HTTPS của trang chính không tự động biến mọi request con thành an toàn.

Ví dụ:

~~~html
<!-- Trang được tải qua HTTPS -->
<script src="http://cdn.example.net/app.js"></script>
<img src="http://images.example.net/banner.png" alt="Banner">
<iframe src="http://legacy.example.net/widget"></iframe>
~~~

Nếu attacker có thể can thiệp vào kết nối HTTP của tài nguyên con, họ có thể thay nội dung trả về. Với JavaScript, mã bị sửa có thể chạy trong ngữ cảnh origin của trang HTTPS và có quyền tương ứng với trang đó. Với stylesheet, attacker có thể thay đổi giao diện, che nút hoặc tạo nội dung giả. Với iframe, browser có thể hiển thị một tài liệu không an toàn bên trong trang an toàn.

### 2.1. Luồng request

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant S as HTTPS app
    participant H as HTTP resource host
    U->>B: Mở trang HTTPS
    B->>S: GET / (TLS)
    S-->>B: HTML HTTPS có URL tài nguyên HTTP
    B->>B: Phân loại mixed content
    alt Blockable content
        B-->>U: Chặn request HTTP
    else Upgradable content
        B->>B: Nâng URL từ http sang https
        B->>H: GET tài nguyên qua HTTPS
        alt HTTPS endpoint hoạt động
            H-->>B: Tài nguyên qua TLS
        else HTTPS endpoint không hoạt động
            B-->>U: Tải tài nguyên thất bại
        end
    end
~~~

Trang chính vẫn có thể hiển thị dù một số tài nguyên bị chặn. Vì vậy người dùng có thể chỉ thấy ảnh trống, widget không hoạt động hoặc một phần giao diện thiếu nội dung; Console và Network panel mới cho biết nguyên nhân.

### 2.2. Attacker có thể làm gì?

- Sửa JavaScript tải qua HTTP để thực thi mã trong trang HTTPS.
- Thay stylesheet để giả mạo nút, biểu mẫu hoặc thông tin thanh toán.
- Thay ảnh/logo bằng nội dung lừa đảo.
- Thay phản hồi API không mã hóa để làm sai dữ liệu hiển thị.
- Can thiệp nội dung iframe hoặc widget bên thứ ba.
- Quan sát dữ liệu request HTTP và response không được mã hóa.

Đối với tài nguyên chủ động như script, rủi ro đặc biệt lớn: script chạy sau khi được nạp có thể hoạt động với quyền của trang chứa nó. Không nên xem HTTP script là “chỉ một file tĩnh”.

## 3. Hai nhóm mixed content trong browser

Các tài liệu cũ thường gọi hai nhóm là **active mixed content** và **passive mixed content**. Trong cách phân loại hiện đại, các thuật ngữ thường gặp là **blockable mixed content** và **upgradable/optionally blockable content**. Browser có thể cập nhật cách xử lý theo tiêu chuẩn và mức độ rủi ro; bảng sau mô tả hành vi phổ biến của browser hiện đại.

### 3.1. Blockable mixed content

Đây là các loại tài nguyên có khả năng thực thi mã, thay đổi hành vi trang hoặc tạo ngữ cảnh tài liệu khác. Browser thường chặn khi trang HTTPS yêu cầu chúng qua HTTP.

| Loại tài nguyên | Ví dụ | Xử lý thường gặp |
| --- | --- | --- |
| JavaScript | script src qua HTTP | Chặn |
| Stylesheet | link rel=stylesheet qua HTTP | Chặn |
| Iframe/frame | iframe src qua HTTP | Chặn |
| Fetch/XHR | fetch hoặc XMLHttpRequest tới HTTP | Chặn trước khi CORS có thể cho phép đọc |
| Font | @font-face tải font qua HTTP | Chặn |
| Worker | Worker script qua HTTP | Chặn |
| Object/embed | Nội dung plugin hoặc object qua HTTP | Chặn |
| WebSocket không mã hóa | ws:// từ trang HTTPS | Browser chặn; dùng wss:// |

Không nên tìm cách “cho phép” các request này bằng cách mở rộng CORS. CORS không làm kết nối HTTP trở thành TLS và không ghi đè mixed content blocking.

### 3.2. Upgradable content

Một số loại tài nguyên ít có khả năng trực tiếp thực thi mã thường được browser tự động nâng cấp URL từ HTTP sang HTTPS trước khi tải.

| Loại tài nguyên | Ví dụ | Xử lý thường gặp |
| --- | --- | --- |
| Ảnh | img src qua HTTP | Tự nâng cấp |
| Ảnh trong CSS | background-image với URL HTTP | Thường được nâng cấp |
| Âm thanh | audio src qua HTTP | Tự nâng cấp |
| Video | video src qua HTTP | Tự nâng cấp |

Nếu tài nguyên có phiên bản HTTPS và endpoint đó hoạt động, browser tải bản HTTPS. Nếu không có HTTPS, kết nối TLS thất bại và tài nguyên không hiển thị. Browser không nên âm thầm quay lại HTTP vì điều đó sẽ tái tạo rủi ro mixed content.

Một số trường hợp đặc biệt, ví dụ URL dùng địa chỉ IP dạng literal hoặc host được browser xem là potentially trustworthy như loopback/localhost, có quy tắc riêng. Không dùng ngoại lệ của môi trường local để kết luận rằng tài nguyên HTTP trong production là an toàn.

### 3.3. Không dựa vào tên “passive” để đánh giá thấp rủi ro

Ảnh không thực thi JavaScript trong ngữ cảnh thông thường, nhưng vẫn có thể:

- Làm giả logo, QR code, thông báo hoặc số tiền.
- Theo dõi người dùng bằng request tới máy chủ bên ngoài.
- Tiết lộ metadata về trang đang truy cập.
- Gây sai lệch nội dung hoặc quy trình mà người dùng dựa vào để ra quyết định.

Vì vậy, upgradable không có nghĩa là “an toàn để tiếp tục dùng HTTP”. Đó chỉ là cách browser giảm rủi ro trong lúc ứng dụng đang chuyển đổi.

## 4. Điều gì xảy ra khi browser block hoặc upgrade?

### 4.1. Blockable request bị chặn

Ví dụ:

~~~html
<script src="http://cdn.example.net/app.js"></script>
<link rel="stylesheet" href="http://cdn.example.net/site.css">
<iframe src="http://legacy.example.net/embed"></iframe>
~~~

Trang HTTPS vẫn được render, nhưng browser chặn tài nguyên HTTP. JavaScript không chạy, CSS không được áp dụng và iframe không được hiển thị. Console thường có thông báo Mixed Content cho biết URL không an toàn đã bị chặn.

### 4.2. Upgradable request được nâng cấp

Ví dụ:

~~~html
<img src="http://images.example.net/logo.png" alt="Logo">
~~~

Browser có thể chuyển request thành:

~~~text
https://images.example.net/logo.png
~~~

Nếu endpoint HTTPS trả ảnh hợp lệ, hình ảnh hiển thị. Nếu endpoint chỉ phục vụ HTTP, browser báo lỗi tải ảnh sau khi nâng cấp. Hãy sửa URL nguồn hoặc cấu hình endpoint HTTPS thực sự.

### 4.3. Redirect từ HTTPS sang HTTP

Một URL ban đầu có thể trông an toàn:

~~~text
https://cdn.example.net/library.js
~~~

nhưng server trả redirect tới:

~~~http
Location: http://legacy.example.net/library.js
~~~

Browser đánh giá đích cuối cùng và loại request. Nếu chuỗi redirect đưa tài nguyên về HTTP, request có thể bị chặn như mixed content. Vì vậy khi debug, cần kiểm tra toàn bộ redirect chain trong Network panel, không chỉ URL ban đầu được ghi trong HTML.

Không dùng redirect HTTP làm cách “tương thích” cho URL HTTPS. Hãy sửa cấu hình CDN, proxy hoặc endpoint để chuỗi tải luôn kết thúc bằng HTTPS.

## 5. Mixed content không giống mọi loại điều hướng HTTP

Mixed content chủ yếu nói về request từ tài liệu secure context tới tài nguyên không an toàn. Một số trường hợp liên quan đến HTTP nhưng có cơ chế xử lý riêng.

| Trường hợp | Có phải mixed subresource điển hình? | Cách xử lý |
| --- | --- | --- |
| HTTPS page tải HTTP script | Có | Block |
| HTTPS page tải HTTP image | Có | Thường auto-upgrade; lỗi HTTPS thì block |
| HTTPS page gọi HTTP fetch/XHR | Có | Block |
| Người dùng click link từ HTTPS sang HTTP | Không phải subresource mixed content thông thường | Insecure navigation/downgrade; chuyển link sang HTTPS |
| HTTPS form gửi dữ liệu tới HTTP action | Luồng form downgrade, có rủi ro riêng | Không gửi dữ liệu nhạy cảm; browser có thể cảnh báo, không dựa vào cảnh báo làm kiểm soát |
| HTTPS page tải file download qua HTTP | Insecure/mixed download, được xử lý riêng | Browser có thể cảnh báo hoặc chặn theo loại file và phiên bản |
| HTTPS page kết nối ws:// | Kết nối WebSocket không an toàn | Dùng wss:// |

### 5.1. Form submission tới HTTP

Ví dụ:

~~~html
<form action="http://legacy.example.net/submit" method="post">
  <input name="email">
  <button type="submit">Gửi</button>
</form>
~~~

Trang được tải qua HTTPS nhưng dữ liệu form được gửi tới HTTP. Đây là một **downgrade nguy hiểm**: dữ liệu có thể bị đọc hoặc sửa trên đường truyền. Hành vi cảnh báo/chặn phụ thuộc browser và ngữ cảnh; không nên dựa vào browser để bảo vệ dữ liệu.

Đặt action tới endpoint HTTPS, kiểm tra redirect phía server và không gửi mật khẩu, token hoặc dữ liệu cá nhân qua HTTP.

### 5.2. Insecure downloads

Một trang HTTPS có thể liên kết tới file tải qua HTTP. Đây là rủi ro tải xuống không an toàn, không nên gộp với phân loại script/image mixed subresource. Browser hiện đại có thể cảnh báo hoặc chặn một số loại file, đặc biệt file có thể thực thi. Hãy phục vụ file qua HTTPS và cấu hình Content-Disposition/Content-Type phù hợp.

### 5.3. Top-level navigation

Người dùng click một liên kết HTTP không có nghĩa browser đang tải một subresource HTTP vào document HTTPS. Đây là navigation tới một trang không an toàn. Dù không cùng cơ chế block mixed content, ứng dụng vẫn nên dùng HTTPS cho mọi liên kết, redirect và callback.

## 6. CSP upgrade-insecure-requests

**upgrade-insecure-requests** là CSP directive yêu cầu browser nâng các URL không an toàn do tài liệu khởi tạo từ HTTP sang HTTPS trước khi thực hiện request.

Ví dụ response header:

~~~http
Content-Security-Policy: upgrade-insecure-requests
~~~

Nếu HTML có:

~~~html
<script src="http://cdn.example.net/app.js"></script>
<img src="http://images.example.net/logo.png" alt="Logo">
~~~

browser sẽ thử tải các URL tương ứng qua HTTPS. Directive này hữu ích khi ứng dụng có nhiều URL legacy và cần một bước chuyển tiếp trong lúc sửa template, CMS hoặc dữ liệu lưu trong database.

### 6.1. Điều directive này làm

- Viết lại request URL không an toàn sang HTTPS trước khi tải.
- Giúp giảm mixed content từ URL HTTP còn sót trong HTML/CSS.
- Áp dụng cho các request do tài liệu khởi tạo theo phạm vi CSP.
- Có thể hỗ trợ migration khi chưa thể sửa toàn bộ nội dung ngay lập tức.

### 6.2. Điều directive này không làm

- Không tạo chứng chỉ TLS cho server HTTP.
- Không bảo đảm host/port đã nâng cấp thực sự phục vụ HTTPS.
- Không sửa redirect sai ở CDN hoặc server.
- Không làm endpoint HTTP bên thứ ba trở nên đáng tin.
- Không thay việc sửa URL trong code, template, database và cấu hình.
- Không phải biện pháp thay thế HTTPS cho mọi navigation do người dùng chủ động click hoặc form submission.

Nếu HTTPS endpoint không tồn tại, request nâng cấp thất bại. Browser không nên quay lại HTTP. Vì vậy, chỉ bật directive sau khi kiểm tra các host và port liên quan.

### 6.3. Ví dụ chính sách kết hợp

~~~http
Content-Security-Policy: default-src 'self'; upgrade-insecure-requests; object-src 'none'; base-uri 'self'
~~~

Các directive khác vẫn cần được thiết kế theo ứng dụng. upgrade-insecure-requests không phải allowlist nguồn tài nguyên và không thay script-src, img-src, connect-src hoặc các directive CSP khác.

### 6.4. Thẻ meta

CSP có thể được khai báo bằng meta cho một số directive, nhưng cấu hình response header được ưu tiên để áp dụng sớm và nhất quán. Nếu dùng meta:

~~~html
<meta http-equiv="Content-Security-Policy" content="upgrade-insecure-requests">
~~~

Meta phải xuất hiện trước các phần tử khởi tạo request. Với ứng dụng production, hãy cấu hình HTTP response header ở server, reverse proxy hoặc CDN.

## 7. block-all-mixed-content đã lỗi thời

Trước đây, một số website dùng:

~~~http
Content-Security-Policy: block-all-mixed-content
~~~

Directive này yêu cầu browser chặn mọi mixed content, kể cả các loại trước kia có thể được tải. Tuy nhiên, browser hiện đại đã tự động chặn các loại nguy hiểm và nâng cấp các loại có thể nâng cấp theo cơ chế mặc định. block-all-mixed-content đã lỗi thời và không còn là biện pháp cần thêm vào CSP hiện đại.

Không nên dùng nó như một cách “bật bảo vệ” thay cho việc:

- Sửa toàn bộ URL HTTP sang HTTPS.
- Cấu hình upgrade-insecure-requests khi cần migration.
- Kiểm tra tài nguyên bên thứ ba và redirect chain.
- Theo dõi Mixed Content trong DevTools.

## 8. HSTS khác upgrade-insecure-requests như thế nào?

**HTTP Strict Transport Security (HSTS)** là response header yêu cầu browser chỉ truy cập host đó qua HTTPS trong thời hạn được khai báo.

Ví dụ:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

| Tiêu chí | CSP upgrade-insecure-requests | HSTS |
| --- | --- | --- |
| Phạm vi | Các request không an toàn do document áp dụng CSP khởi tạo | Host đã gửi HSTS và phạm vi subdomain nếu có includeSubDomains |
| Mục tiêu | Nâng URL HTTP trong nội dung/request của trang sang HTTPS | Buộc browser truy cập host qua HTTPS |
| Cách cấu hình | CSP directive trong response của document | HTTP response header Strict-Transport-Security từ host qua HTTPS |
| Subdomain | Phụ thuộc URL được nâng và tài nguyên trang yêu cầu | Có thể áp dụng cho subdomain bằng includeSubDomains |
| Endpoint HTTPS không hoạt động | Request nâng cấp thất bại | Browser không quay lại HTTP trong thời gian HSTS có hiệu lực |
| Thay thế nhau? | Không | Không |

HSTS nên được triển khai khi host và các subdomain thuộc phạm vi đã sẵn sàng HTTPS. includeSubDomains có thể ảnh hưởng dịch vụ legacy; kiểm kê trước khi bật. Preload là cơ chế riêng với điều kiện và quy trình đăng ký riêng, không chỉ là thêm một directive vào header.

upgrade-insecure-requests xử lý URL HTTP được trang yêu cầu; HSTS ghi nhớ chính sách HTTPS cho host. Có thể dùng cả hai nhưng cần hiểu phạm vi và tác động của từng cơ chế.

## 9. Cách sửa mixed content trong ứng dụng

### 9.1. Sửa URL nguồn thành HTTPS

Trước:

~~~html
<script src="http://cdn.example.net/app.js"></script>
<img src="http://images.example.net/logo.png" alt="Logo">
~~~

Sau:

~~~html
<script src="https://cdn.example.net/app.js"></script>
<img src="https://images.example.net/logo.png" alt="Logo">
~~~

Chỉ đổi scheme khi endpoint thực sự hỗ trợ HTTPS và chứng chỉ hợp lệ. Không thay chuỗi http thành https một cách mù quáng nếu host hoặc port không phục vụ TLS.

### 9.2. Dùng URL tương đối khi tài nguyên cùng origin

Nếu tài nguyên được phục vụ từ chính ứng dụng:

~~~html
<script src="/assets/app.js"></script>
<link rel="stylesheet" href="/assets/site.css">
~~~

URL tương đối kế thừa scheme của trang hiện tại. Khi trang chạy HTTPS, browser yêu cầu tài nguyên qua HTTPS.

Tránh URL protocol-relative như //cdn.example.net/app.js nếu không rõ chính sách và endpoint. Nó kế thừa scheme hiện tại, nhưng vẫn phụ thuộc host bên ngoài và có thể che giấu nguồn tài nguyên trong code review.

### 9.3. Sửa CSS và JavaScript tạo URL động

Tìm cả URL trong:

- CSS url(http://...), @import.
- JavaScript gán img.src, script.src, iframe.src.
- Fetch/XHR/WebSocket.
- Cấu hình runtime, CMS, database và feature flag.
- URL được tạo từ API response hoặc biến môi trường.

Không chỉ tìm http:// trong HTML template. Một URL có thể được tạo ở runtime hoặc được trả về qua API.

### 9.4. Sửa endpoint và redirect

Nếu một host chỉ hỗ trợ HTTP:

1. Cấu hình TLS certificate hợp lệ cho host.
2. Bật HTTPS listener trên đúng host/port.
3. Chuyển CDN, reverse proxy và origin routing sang HTTPS.
4. Sửa redirect để không quay lại HTTP.
5. Cập nhật URL trong ứng dụng và dữ liệu lưu trữ.
6. Kiểm tra cache và service worker để loại bỏ URL cũ.

Nếu bên thứ ba chưa hỗ trợ HTTPS, không nhúng tài nguyên HTTP đó vào trang HTTPS. Hãy yêu cầu endpoint HTTPS, thay nhà cung cấp hoặc thiết kế proxy server-side có kiểm soát và đánh giá rủi ro riêng.

## 10. Kiểm tra mixed content bằng DevTools

### 10.1. Console

Mở DevTools → Console và tải lại trang. Browser thường hiển thị thông báo có:

- URL trang HTTPS.
- URL tài nguyên HTTP được yêu cầu.
- Loại nội dung bị block hoặc được auto-upgrade.
- Lý do tải thất bại nếu HTTPS endpoint không phản hồi đúng.

Không chỉ nhìn dòng lỗi đầu tiên. Một tài nguyên có thể redirect qua nhiều host hoặc được tạo bởi script khác.

### 10.2. Network

Trong DevTools → Network:

1. Bật Preserve log nếu trang có redirect.
2. Tải lại trang.
3. Lọc theo blocked, mixed, http hoặc loại resource.
4. Kiểm tra Request URL, Status, Initiator và redirect chain.
5. Với ảnh được nâng cấp, xem URL cuối cùng có phải HTTPS không.
6. Với request bị chặn, xác định source trong Initiator hoặc call stack.

Một request có thể hiện blocked:mixed-content hoặc thông báo tương đương tùy browser. Request được auto-upgrade có thể xuất hiện dưới HTTPS và sau đó thất bại do TLS/connection; cần phân biệt lỗi mixed content với lỗi chứng chỉ hoặc endpoint.

### 10.3. Security panel và header

Kiểm tra:

- Trang chính có được tải qua HTTPS không?
- Chứng chỉ TLS có hợp lệ không?
- Response có CSP upgrade-insecure-requests không?
- Host có HSTS không?
- Tài nguyên con có redirect về HTTP không?
- Có endpoint nào dùng port HTTP tùy chỉnh không?

## 11. Thực hành: tái hiện mixed content với Node.js

Bài lab dùng **Node.js 18 trở lên** và mkcert để tạo chứng chỉ tin cậy cho môi trường local. Dùng hai hostname .test để browser không xem chúng như loopback/localhost; nhờ đó tránh ngoại lệ secure-context dành cho localhost làm sai kết quả.

Lab tạo:

- https://app.test:8443: trang chính HTTPS.
- http://assets.test:8080: tài nguyên HTTP không an toàn.
- https://assets.test:8443: endpoint HTTPS hợp lệ để so sánh cách sửa.

Trang thử nghiệm có ba chế độ:

| Route | Hành vi |
| --- | --- |
| /default | Trang HTTPS yêu cầu script, ảnh và fetch qua HTTP |
| /upgrade | Cùng nội dung nhưng có CSP upgrade-insecure-requests |
| /fixed | Dùng URL HTTPS thực sự của máy chủ tài nguyên |

### 11.1. Chuẩn bị hostname và chứng chỉ

Thêm dòng sau vào file hosts của hệ điều hành (cần quyền quản trị):

~~~text
127.0.0.1 app.test assets.test
~~~

Cài mkcert theo hướng dẫn của hệ điều hành, sau đó chạy trong thư mục lab:

~~~bash
mkcert -install
mkcert -cert-file cert.pem -key-file key.pem app.test assets.test
~~~

mkcert -install thêm CA local vào trust store của máy. Chỉ dùng chứng chỉ này cho môi trường thử nghiệm. Không dùng hoặc phân phối private key của lab cho production.

### 11.2. Tạo file mixed-content-lab.mjs

~~~js
import { createServer as createHttpServer } from 'node:http';
import { createServer as createHttpsServer } from 'node:https';
import { readFileSync } from 'node:fs';

const tls = {
  cert: readFileSync('./cert.pem'),
  key: readFileSync('./key.pem'),
};

function page(assetBase) {
  return [
    '<!doctype html>',
    '<html lang="vi"><head><meta charset="utf-8">',
    '<title>Mixed content lab</title></head><body>',
    '<h1>Mixed content blocking</h1>',
    '<p>Ảnh: <img id="probe-image" alt="Tài nguyên ảnh thử nghiệm"></p>',
    '<p id="script-status">Script chưa chạy.</p>',
    '<p id="fetch-status">Fetch chưa hoàn tất.</p>',
    '<p><a href="/default">Default</a> | ',
    '<a href="/upgrade">upgrade-insecure-requests</a> | ',
    '<a href="/fixed">HTTPS URLs</a></p>',
    '<script src="' + assetBase + '/blocked.js"></script>',
    '<script>',
    "document.querySelector('#probe-image').src = " +
      "JSON_ASSET_IMAGE_PLACEHOLDER;",
    'fetch(JSON_ASSET_DATA_PLACEHOLDER)',
    "  .then((response) => response.json())",
    "  .then((data) => { document.querySelector('#fetch-status').textContent = data.message; })",
    "  .catch(() => { document.querySelector('#fetch-status').textContent = 'Fetch thất bại hoặc bị browser chặn.'; });",
    '</script>',
    '</body></html>',
  ].join('\n')
    .replace('JSON_ASSET_IMAGE_PLACEHOLDER', JSON.stringify(assetBase + '/image.svg'))
    .replace('JSON_ASSET_DATA_PLACEHOLDER', JSON.stringify(assetBase + '/data.json'));
}

function assetResponse(req, res) {
  const path = new URL(req.url, 'https://assets.test:8443').pathname;
  const headers = {
    'Cache-Control': 'no-store',
    'Access-Control-Allow-Origin': 'https://app.test:8443',
  };

  if (path === '/image.svg') {
    res.writeHead(200, {
      ...headers,
      'Content-Type': 'image/svg+xml; charset=utf-8',
    });
    res.end(
      '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="80">' +
      '<rect width="100%" height="100%" fill="#d9f0dc"/>' +
      '<text x="12" y="48" font-size="22">HTTPS image loaded</text></svg>'
    );
    return;
  }

  if (path === '/blocked.js') {
    res.writeHead(200, {
      ...headers,
      'Content-Type': 'text/javascript; charset=utf-8',
    });
    res.end(
      "document.querySelector('#script-status').textContent =" +
      "'External script loaded over HTTPS';"
    );
    return;
  }

  if (path === '/data.json') {
    res.writeHead(200, {
      ...headers,
      'Content-Type': 'application/json; charset=utf-8',
    });
    res.end(JSON.stringify({ message: 'HTTPS fetch thành công.' }));
    return;
  }

  res.writeHead(404);
  res.end('Not found');
}

createHttpServer((req, res) => {
  assetResponse(req, res);
}).listen(8080, () => {
  console.log('HTTP assets: http://assets.test:8080');
});

createHttpsServer(tls, (req, res) => {
  const url = new URL(req.url, 'https://app.test:8443');

  if (url.pathname === '/image.svg' ||
      url.pathname === '/blocked.js' ||
      url.pathname === '/data.json') {
    assetResponse(req, res);
    return;
  }

  const route = ['/', '/default'].includes(url.pathname)
    ? 'default'
    : url.pathname.slice(1);

  if (!['default', 'upgrade', 'fixed'].includes(route)) {
    res.writeHead(404);
    res.end('Not found');
    return;
  }

  const assetBase = route === 'fixed'
    ? 'https://assets.test:8443'
    : 'http://assets.test:8080';

  const headers = {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
  };

  if (route === 'upgrade') {
    headers['Content-Security-Policy'] = 'upgrade-insecure-requests';
  }

  res.writeHead(200, headers);
  res.end(page(assetBase));
}).listen(8443, () => {
  console.log('HTTPS app: https://app.test:8443');
  console.log('HTTPS assets: https://assets.test:8443');
});
~~~

Máy chủ HTTPS phục vụ cả trang app và tài nguyên HTTPS theo hostname/port. Máy chủ HTTP chỉ phục vụ tài nguyên ở port 8080. Khi browser nâng URL có port 8080 sang HTTPS, không có TLS listener ở port đó nên request sẽ thất bại; đây là cách lab minh họa rằng auto-upgrade không tạo HTTPS endpoint thay cho server.

### 11.3. Chạy lab

~~~bash
node mixed-content-lab.mjs
~~~

Mở https://app.test:8443/default:

1. Browser tải trang chính qua HTTPS.
2. Script từ http://assets.test:8080/blocked.js bị chặn vì là blockable mixed content.
3. Ảnh HTTP có thể được tự động nâng thành https://assets.test:8080/image.svg; do port 8080 không có TLS listener, ảnh không tải được.
4. Fetch tới HTTP bị chặn như mixed content trước khi CORS có thể cho phép JavaScript đọc response.
5. Mở DevTools → Console và Network để xem từng request.

### 11.4. Thử upgrade-insecure-requests

Mở https://app.test:8443/upgrade.

Response có:

~~~http
Content-Security-Policy: upgrade-insecure-requests
~~~

Các URL HTTP do trang khởi tạo được nâng cấp trước khi tải. Trong lab, chúng vẫn thất bại vì TLS không được phục vụ trên port 8080. Đây là kết quả mong đợi: directive nâng URL, không sửa cấu hình máy chủ.

### 11.5. Thử URL HTTPS đã sửa

Mở https://app.test:8443/fixed.

Trang dùng https://assets.test:8443:

- Ảnh HTTPS được tải.
- Script HTTPS chạy và cập nhật trạng thái.
- Fetch HTTPS thành công vì máy chủ tài nguyên trả Access-Control-Allow-Origin phù hợp.

Điều này cho thấy cách sửa bền vững là cung cấp endpoint HTTPS thực sự và cập nhật URL trong ứng dụng. CSP upgrade có thể hỗ trợ migration nhưng không thay việc sửa endpoint.

### 11.6. Giới hạn lab

- Lab cần mkcert và thay đổi file hosts; chứng chỉ chỉ dùng cho local development.
- Lab dùng port tùy chỉnh để minh họa URL nâng cấp có thể thất bại khi HTTPS listener không có ở port tương ứng.
- Kết quả auto-upgrade và thông báo Console có thể khác giữa browser/version.
- Không dùng localhost hoặc địa chỉ loopback cho URL tài nguyên HTTP trong bài kiểm tra chính vì browser có thể xem chúng là potentially trustworthy.
- Không đưa tài khoản, cookie hoặc dữ liệu thật vào lab.

## 12. Checklist xử lý mixed content trong dự án

1. **Xác định trang nguồn:** kiểm tra mọi route HTTPS và response header liên quan.
2. **Tìm URL HTTP:** tìm trong HTML, CSS, JavaScript, database, CMS, config, API response và redirect.
3. **Phân loại resource:** script/style/iframe/fetch/font/worker/WebSocket hay image/audio/video.
4. **Kiểm tra redirect:** theo dõi URL cuối cùng và port thực tế.
5. **Sửa endpoint:** bảo đảm host và port phục vụ HTTPS với chứng chỉ hợp lệ.
6. **Cập nhật URL:** dùng HTTPS hoặc URL tương đối cho tài nguyên cùng origin.
7. **Dùng CSP migration có chủ đích:** cân nhắc upgrade-insecure-requests sau khi kiểm kê endpoint.
8. **Không dựa vào directive lỗi thời:** không dùng block-all-mixed-content như biện pháp chính.
9. **Phân biệt rủi ro khác:** form HTTP, insecure navigation và mixed download cần được kiểm tra riêng.
10. **Kiểm tra CORS:** chỉ sau khi request đã qua mixed content/TLS; CORS không làm HTTP an toàn.
11. **Kiểm tra HSTS:** triển khai theo phạm vi host/subdomain đã sẵn sàng HTTPS.
12. **Kiểm thử browser:** xem Console, Network, Initiator, redirect chain và lỗi TLS.
13. **Theo dõi sau deploy:** kiểm tra trang lỗi, cache cũ, service worker và tài nguyên do bên thứ ba cung cấp.

## 13. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Trang chính HTTPS nên mọi tài nguyên đều an toàn.” | Tài nguyên HTTP vẫn có thể bị đọc hoặc sửa trên đường truyền. |
| “Browser chặn mọi mixed content giống nhau.” | Script/style/iframe/fetch thường bị chặn; ảnh/audio/video có thể được nâng cấp tự động. |
| “Ảnh được auto-upgrade thì HTTP endpoint đã an toàn.” | Browser thử HTTPS; nếu endpoint HTTPS không tồn tại, ảnh sẽ lỗi. |
| “CORS cho phép thì mixed content được tải.” | Mixed content blocking xảy ra độc lập; CORS không biến HTTP thành HTTPS. |
| “upgrade-insecure-requests tạo TLS cho server.” | Directive chỉ viết lại URL; server phải thực sự phục vụ HTTPS. |
| “block-all-mixed-content là cách bảo vệ hiện đại.” | Directive đã lỗi thời; browser hiện đại tự block/upgrades theo phân loại. |
| “URL bắt đầu bằng HTTPS thì chắc chắn không có mixed content.” | Server có thể redirect sang HTTP; cần kiểm tra redirect chain. |
| “Link HTTP được click là cùng loại với script HTTP.” | Top-level navigation, form downgrade và insecure download có cơ chế riêng. |
| “localhost hoạt động qua HTTP nên production cũng được.” | Loopback có thể được xem là potentially trustworthy; không suy rộng ngoại lệ này. |
| “Chỉ cần tìm http:// trong HTML.” | URL có thể nằm trong CSS, JavaScript, API response, database, CMS hoặc redirect. |
| “HSTS và upgrade-insecure-requests thay nhau được.” | HSTS áp dụng theo host; CSP directive nâng request do document khởi tạo. |

## 14. Câu hỏi tự đánh giá

**Câu 1.** Mixed content là gì?

**Gợi ý trả lời:** Là khi tài liệu HTTPS tải tài nguyên hoặc nội dung không an toàn qua HTTP, làm một phần trang không được bảo vệ bởi TLS.

**Câu 2.** Vì sao script HTTP thường bị chặn còn ảnh HTTP có thể được nâng cấp?

**Gợi ý trả lời:** Script có thể thực thi mã trong origin của trang nên rủi ro cao; ảnh là loại nội dung có thể được browser tự nâng URL sang HTTPS theo chính sách upgradable content.

**Câu 3.** Điều gì xảy ra nếu ảnh HTTP được nâng lên HTTPS nhưng server không hỗ trợ TLS?

**Gợi ý trả lời:** Request HTTPS thất bại và ảnh không tải; browser không quay lại HTTP để tránh mixed content.

**Câu 4.** upgrade-insecure-requests giải quyết vấn đề gì và giới hạn ra sao?

**Gợi ý trả lời:** Nó viết lại URL HTTP trong request do document khởi tạo thành HTTPS; không tạo chứng chỉ hoặc sửa endpoint chưa hỗ trợ TLS.

**Câu 5.** Vì sao CORS không thay thế mixed content blocking?

**Gợi ý trả lời:** CORS quyết định JavaScript có được đọc response cross-origin hay không; mixed content kiểm soát việc tài liệu secure tải tài nguyên không an toàn.

**Câu 6.** HSTS khác CSP upgrade-insecure-requests thế nào?

**Gợi ý trả lời:** HSTS ghi nhớ yêu cầu HTTPS cho một host; CSP directive nâng URL không an toàn trong các request do tài liệu áp dụng policy khởi tạo.

**Câu 7.** Vì sao cần kiểm tra redirect chain khi debug mixed content?

**Gợi ý trả lời:** URL ban đầu có thể là HTTPS nhưng server redirect tới HTTP; browser đánh giá đích cuối và có thể chặn request.

## Tài liệu tham khảo

- W3C — [Mixed Content](https://www.w3.org/TR/mixed-content/).
- MDN — [Mixed content](https://developer.mozilla.org/en-US/docs/Web/Security/Mixed_content).
- MDN — [Content-Security-Policy: upgrade-insecure-requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/upgrade-insecure-requests).
- MDN — [Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security).
- OWASP — [Transport Layer Protection Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Protection_Cheat_Sheet.html).
- Chrome for Developers — [Mixed content](https://developer.chrome.com/blog/mixed-content/).
