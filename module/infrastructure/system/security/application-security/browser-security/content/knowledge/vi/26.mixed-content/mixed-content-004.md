# HTTP image

> **Chương:** Mixed content  
> **Chủ đề:** HTTP image  
> **Module:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly. Thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao ảnh tải qua HTTP trong một trang HTTPS là mixed content.
2. Phân biệt ảnh mixed content với các loại nội dung chủ động như script, stylesheet, iframe và Fetch/XHR.
3. Mô tả cách browser hiện đại tự nâng cấp URL ảnh từ HTTP sang HTTPS và điều gì xảy ra khi endpoint HTTPS không phục vụ ảnh.
4. Kiểm tra ảnh được khai báo qua img, srcset, picture, CSS và JavaScript.
5. Phân biệt browser auto-upgrade, CSP upgrade-insecure-requests và HSTS.
6. Chẩn đoán lỗi ảnh không hiển thị bằng DevTools và Network.
7. Thực hành kiểm tra mixed content bằng một lab local có hai hostname và TLS certificate tin cậy.

## 1. HTTP image trong trang HTTPS là gì?

Một trang web được tải qua HTTPS có kênh kết nối được mã hóa và xác thực với origin của trang. Nhưng nếu HTML của trang tham chiếu tới một ảnh qua HTTP, browser phải tải ảnh qua một kết nối không có TLS:

```html
<!doctype html>
<html lang="vi">
<body>
  <h1>Trang bảo mật</h1>
  <img src="http://images.example.test/banner.jpg" alt="Banner">
</body>
</html>
```

Giả sử trang được mở tại https://shop.example.test, còn ảnh được lấy từ http://images.example.test/banner.jpg. Đây là một request mixed content: document được bảo vệ bằng HTTPS nhưng một tài nguyên của nó được yêu cầu qua HTTP.

HTTP không bảo đảm tính bí mật hoặc toàn vẹn trên đường truyền. Một bên có khả năng can thiệp mạng có thể quan sát request, thay đổi bytes ảnh hoặc thay ảnh bằng nội dung khác trước khi browser nhận được. Việc thay hình ảnh có thể gây giả mạo thương hiệu, thay đổi chỉ dẫn hiển thị, tạo thông tin sai hoặc theo dõi người truy cập.

Ảnh thường không thực thi JavaScript trong context của trang khi được tải bằng img, nhưng vẫn có rủi ro về quyền riêng tư, tính toàn vẹn và nội dung người dùng nhìn thấy. Ngoài ra, URL ảnh không được kiểm soát có thể bị dùng để theo dõi lượt xem hoặc tiết lộ metadata của request.

## 2. Browser xử lý HTTP image như thế nào?

Trước đây, ảnh, audio và video thường được gọi là **passive/optionally blockable mixed content**, vì chúng không có khả năng điều khiển document giống script. Cách phân loại này không có nghĩa browser hiện đại luôn cho phép tải chúng qua HTTP.

Các browser hiện đại thường **tự nâng cấp** những request tài nguyên dạng ảnh từ HTTP sang HTTPS trước khi tải. Ví dụ:

```text
Trang:        https://shop.example.test
HTML khai báo: http://images.example.test/banner.jpg
Request được nâng cấp thành:
              https://images.example.test/banner.jpg
```

Nếu server ảnh hỗ trợ HTTPS và trả về tài nguyên hợp lệ, ảnh có thể hiển thị mà không cần thay đổi HTML ngay lập tức. Nếu HTTPS endpoint không tồn tại, certificate không hợp lệ, kết nối TLS lỗi hoặc đường dẫn HTTPS không phục vụ tài nguyên, browser chặn request. Browser không nên hạ cấp trở lại HTTP để tải ảnh.

Hành vi chi tiết có thể khác theo browser, phiên bản, loại request và cấu hình chính sách. Vì vậy, cần kiểm tra request thực tế trong ma trận browser của sản phẩm. Cách sửa bền vững vẫn là đổi URL nguồn sang HTTPS và bảo đảm máy chủ ảnh phục vụ TLS đúng cách.

### 2.1. Ảnh là nội dung có thể được nâng cấp

Ví dụ ảnh trực tiếp:

```html
<img src="http://cdn.example.test/product.jpg" alt="Sản phẩm">
```

Ví dụ ảnh responsive:

```html
<picture>
  <source
    media="(min-width: 900px)"
    srcset="http://cdn.example.test/large.webp">
  <img
    src="http://cdn.example.test/small.jpg"
    srcset="http://cdn.example.test/small-2x.jpg 2x"
    alt="Ảnh sản phẩm">
</picture>
```

Browser chọn candidate phù hợp từ src, srcset hoặc source trong picture, rồi áp dụng cơ chế mixed-content cho URL được chọn. Chỉ sửa src mà quên srcset có thể khiến một số thiết bị vẫn phát sinh request HTTP.

Ảnh CSS cũng cần kiểm tra:

```css
.hero {
  background-image: url("http://cdn.example.test/hero.jpg");
}
```

Và ảnh được tạo bằng JavaScript:

```js
const image = new Image();
image.src = 'http://cdn.example.test/avatar.png';
document.querySelector('#avatar').replaceWith(image);
```

Không chỉ rà soát các thẻ img trong HTML. URL có thể được ghép từ CSS, component framework, API response, CMS hoặc code chạy sau khi trang tải.

### 2.2. Không phải mọi request HTTP đều được xử lý giống ảnh

Script, stylesheet, iframe, font và các request Fetch/XHR thường thuộc nhóm mixed content bị chặn. Browser không thể mặc định nâng cấp và cho phép mọi request chủ động như ảnh.

| Loại tài nguyên | Ví dụ | Hành vi thường gặp trên HTTPS page |
|---|---|---|
| Ảnh | img src HTTP | Browser hiện đại thường tự nâng cấp sang HTTPS; nếu tải HTTPS thất bại thì request bị chặn |
| CSS background image | url HTTP | Được xử lý như request ảnh và thường được nâng cấp |
| Audio/video | audio, video HTTP | Có thể được browser tự nâng cấp; kiểm tra theo browser |
| JavaScript | script src HTTP | Mixed content chủ động, thường bị chặn |
| Stylesheet | link rel=stylesheet HTTP | Thường bị chặn |
| Font | font-face từ HTTP | Thường bị chặn |
| Iframe | iframe src HTTP | Thường bị chặn trong trang HTTPS |
| Fetch/XHR | fetch HTTP | Bị chặn như mixed content |

Vì vậy, không thể lấy kết quả ảnh vẫn hiển thị để kết luận các tài nguyên HTTP khác cũng an toàn hoặc được nâng cấp theo cách tương tự.

## 3. Điều gì xảy ra khi HTTPS image endpoint không hoạt động?

Browser có thể nâng URL ảnh HTTP lên HTTPS, nhưng không bảo đảm server đích có cấu hình TLS đúng.

Các tình huống thường gặp:

1. **Không lắng nghe HTTPS:** host chỉ mở cổng HTTP, không phục vụ TLS trên endpoint HTTPS.
2. **Certificate không hợp lệ:** certificate hết hạn, hostname không khớp, chain thiếu hoặc CA không được tin cậy.
3. **HTTPS path không tồn tại:** server HTTPS hoạt động nhưng đường dẫn ảnh chỉ được cấu hình ở virtual host HTTP.
4. **Redirect về HTTP:** HTTPS endpoint trả redirect tới URL HTTP; browser tiếp tục áp dụng kiểm tra mixed-content và có thể chặn request cuối.
5. **CDN hoặc reverse proxy sai cấu hình:** TLS kết thúc ở proxy nhưng origin/path hoặc cache rule làm response khác nhau.
6. **IP literal hoặc môi trường đặc biệt:** một số browser có quy tắc nâng cấp khác với hostname thông thường; không dựa vào auto-upgrade để xử lý URL IP.

Không nên cấu hình server để redirect mọi request HTTPS về HTTP chỉ nhằm làm ảnh hiển thị. Điều đó đưa tài nguyên trở lại kết nối không an toàn và không giải quyết được mixed content.

### 3.1. Không có fallback HTTP an toàn

Nếu request http://cdn.example.test/photo.jpg được nâng thành https://cdn.example.test/photo.jpg và HTTPS trả 404, browser không nên tự thử lại URL HTTP. Fallback như vậy sẽ làm mất mục tiêu bảo vệ: attacker trên mạng có thể ép browser dùng kết nối không mã hóa.

Ứng dụng cần sửa nguồn ảnh, cấu hình TLS hoặc chuyển ảnh sang CDN HTTPS khác đã được kiểm soát. Nếu một tài nguyên không có phiên bản HTTPS, hãy thay thế hoặc loại bỏ tài nguyên đó.

### 3.2. Redirect cần được kiểm tra đến URL cuối

Không chỉ kiểm tra URL đầu tiên trong HTML. Một ảnh có thể được tải từ HTTPS endpoint nhưng redirect sang HTTP:

```text
https://cdn.example.test/image
  -> 302 Location: http://legacy.example.test/image.jpg
```

Browser vẫn phải áp dụng mixed-content check cho URL đích sau redirect. Trong DevTools Network, bật Preserve log để xem chuỗi redirect và xác định response nào dẫn tới lỗi.

## 4. Browser auto-upgrade, CSP và HSTS khác nhau thế nào?

Ba cơ chế này có liên quan nhưng không đồng nhất:

| Cơ chế | Nơi áp dụng | Tác dụng |
|---|---|---|
| Browser mixed-content auto-upgrade | Browser khi xử lý một số request HTTP từ secure document | Tự chuyển một số request ảnh/audio/video sang HTTPS |
| CSP upgrade-insecure-requests | Document có CSP directive | Yêu cầu browser nâng các URL tài nguyên insecure trong document lên HTTPS trước khi gửi request |
| HSTS | Browser ghi nhớ chính sách của host từ response HSTS hoặc preload list | Nâng điều hướng và request tới host đó từ HTTP lên HTTPS theo policy HSTS |

### 4.1. CSP upgrade-insecure-requests

Server có thể gửi:

```http
Content-Security-Policy: upgrade-insecure-requests
```

Directive này yêu cầu browser nâng URL tài nguyên insecure trong document lên HTTPS. Nó hữu ích khi cần chuyển dần một website có nhiều URL HTTP cũ. Tuy nhiên:

- Nó không làm server HTTP có TLS.
- Nó không bảo đảm đường dẫn HTTPS tồn tại.
- Nó không tạo fallback an toàn về HTTP khi HTTPS thất bại.
- Nó không thay việc cập nhật URL trong database, CMS, template và source code.
- Nó không nên được xem là biện pháp sửa lỗi lâu dài cho nguồn ảnh bên thứ ba.

upgrade-insecure-requests cũng có thể tác động tới các tài nguyên khác, không chỉ ảnh. Trước khi bật trên production, cần kiểm tra mọi endpoint HTTP đang được ứng dụng sử dụng.

### 4.2. CSP img-src

img-src kiểm soát nguồn ảnh được phép tải:

```http
Content-Security-Policy: img-src 'self' https://cdn.example.test data:
```

Directive này là allowlist nguồn ảnh. Nó không tự nâng URL HTTP sang HTTPS. Ví dụ img-src https://cdn.example.test cho phép ảnh từ origin HTTPS đã nêu; một URL HTTP không tự trở thành HTTPS chỉ vì có img-src.

Nếu policy có default-src 'self' mà không khai báo img-src, ảnh sẽ dùng fallback tương ứng. Để dễ kiểm tra và giới hạn quyền, nên khai báo img-src rõ ràng theo nguồn ảnh thực tế.

### 4.3. HSTS

Server HTTPS có thể gửi:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

Browser ghi nhớ rằng host phải được truy cập bằng HTTPS trong khoảng thời gian max-age. includeSubDomains mở rộng policy tới subdomain. Chỉ bật includeSubDomains khi mọi subdomain liên quan đã sẵn sàng HTTPS.

HSTS hữu ích để ngăn kết nối HTTP tới host đã có policy, nhưng có giới hạn:

- Trình duyệt cần nhận policy từ một kết nối HTTPS hợp lệ trước, trừ khi host nằm trong preload list.
- HSTS không sửa URL hardcode trong nội dung và không thay thế kiểm thử mixed content.
- HSTS của một host không tự bảo vệ một host ảnh khác không có HSTS.
- HSTS không cứu được endpoint HTTPS có certificate sai hoặc không phục vụ tài nguyên.

### 4.4. Không dùng block-all-mixed-content như giải pháp chính

Directive CSP block-all-mixed-content từng được dùng để yêu cầu browser chặn mixed content. Trong các browser hiện đại, cơ chế này đã lỗi thời/không còn cần thiết vì mixed-content handling và auto-upgrade đã được tích hợp. Không dựa vào directive này để thay thế việc sửa URL, cấu hình HTTPS và dùng CSP hiện hành.

## 5. Rủi ro bảo mật của HTTP image

Ảnh không giống script, nhưng tải ảnh qua HTTP vẫn có các tác động đáng kể:

- **Mất toàn vẹn nội dung:** bên can thiệp mạng có thể thay ảnh bằng thông tin giả, hình ảnh lừa đảo hoặc nội dung gây hiểu nhầm.
- **Mất quyền riêng tư:** server ảnh có thể nhận IP, thời điểm truy cập, user-agent và các header phù hợp với chính sách referrer/browser.
- **Theo dõi người dùng:** URL ảnh duy nhất hoặc query parameter có thể dùng để liên kết lượt xem với một người hoặc một phiên.
- **Giảm độ tin cậy giao diện:** logo, giá, QR code, hướng dẫn hoặc ảnh sản phẩm có thể bị thay đổi.
- **Khác biệt giữa browser:** một client cũ hoặc môi trường nhúng có thể xử lý mixed content khác browser desktop mới.
- **Khó chẩn đoán:** ảnh có thể biến mất chỉ ở một browser, một thiết bị hoặc một biến thể srcset.

HTTPS bảo vệ kênh tới server đã xác thực, không chứng minh bản thân ảnh là nội dung đúng về mặt nghiệp vụ. Ứng dụng vẫn cần kiểm soát nguồn ảnh, quyền upload và nội dung được phép hiển thị.

## 6. Cách tìm HTTP image trong ứng dụng

Kiểm tra toàn bộ nơi URL ảnh có thể được định nghĩa:

### 6.1. HTML và template

- img[src]
- img[srcset]
- source[srcset] trong picture
- video[poster]
- link rel=preload as=image
- HTML được server render và HTML được tạo sau hydration

### 6.2. CSS

- background-image
- border-image
- list-style-image
- content: url(...)
- image-set(...)
- CSS từ thư viện hoặc theme bên ngoài

### 6.3. JavaScript và dữ liệu

- new Image().src
- setAttribute('src', ...)
- Component nhận URL từ API
- CMS lưu URL ảnh cũ
- Cấu hình theme, email preview hoặc trang quản trị
- URL được ghép động từ hostname và path

Tìm chuỗi http:// trong repository là bước đầu hữu ích, nhưng không đủ. URL có thể được ghép từ nhiều biến, nhận từ backend hoặc được tạo bởi dependency. Cần kết hợp static search với Network trace khi chạy ứng dụng.

### 6.4. Cẩn thận với protocol-relative URL

URL dạng:

```html
<img src="//cdn.example.test/photo.jpg" alt="Ảnh">
```

thừa hưởng scheme của document. Trên trang HTTPS, browser sẽ yêu cầu HTTPS; trên trang HTTP, nó có thể yêu cầu HTTP. Vì vậy, protocol-relative URL không cố định ở HTTPS. Với ứng dụng yêu cầu HTTPS, nên dùng URL https:// rõ ràng.

## 7. Quy trình khắc phục HTTP image

Khi phát hiện ảnh HTTP trên trang HTTPS:

1. Xác định URL ảnh cuối cùng trong Network, gồm mọi redirect.
2. Mở trực tiếp URL HTTPS tương ứng và kiểm tra certificate, status code, content type và response body.
3. Cập nhật src, mọi candidate trong srcset, CSS URL và dữ liệu CMS sang HTTPS.
4. Nếu server ảnh chưa hỗ trợ HTTPS, cấu hình TLS ở CDN/reverse proxy hoặc chuyển sang nhà cung cấp ảnh hỗ trợ HTTPS.
5. Kiểm tra redirect không quay về HTTP và không đổi sang hostname ngoài dự kiến.
6. Cập nhật CSP img-src để chỉ cho phép origin ảnh cần thiết.
7. Cân nhắc CSP upgrade-insecure-requests trong giai đoạn chuyển đổi, sau khi kiểm tra tác động tới mọi tài nguyên.
8. Kiểm thử lại trên browser/thiết bị được hỗ trợ và theo dõi mixed-content violation.

Không thay URL HTTP bằng HTTPS theo kiểu find-and-replace mà không xác minh host/path. Một số dịch vụ dùng host HTTP riêng, cổng riêng hoặc endpoint không hỗ trợ TLS; việc thay scheme mù quáng có thể làm mất ảnh hoặc trỏ tới một dịch vụ khác.

### 7.1. Tiêu chí xác minh ảnh đã an toàn

- URL trong HTML/CSS/API data dùng HTTPS rõ ràng.
- Request cuối cùng trong Network dùng HTTPS.
- Certificate hợp lệ cho hostname ảnh và chain được browser tin cậy.
- Response trả đúng image content type và status thành công.
- Không có redirect cuối về HTTP.
- Các biến thể srcset, breakpoint, theme và lazy-load đều được kiểm tra.
- CSP img-src cho phép đúng nguồn và không cần wildcard rộng.
- Không còn mixed-content error trên các workflow quan trọng.

## 8. Thực hành: lab HTTP image với Node.js

Lab tạo một trang HTTPS và một host ảnh có cả HTTP lẫn HTTPS. Browser được yêu cầu tải hai ảnh qua HTTP:

- auto-ok.svg: có mặt trên cả HTTP và HTTPS. Browser hiện đại sẽ nâng request ảnh lên HTTPS và hiển thị ảnh.
- http-only.svg: chỉ có ở HTTP; endpoint HTTPS trả 404. Browser nâng request lên HTTPS rồi thất bại, không quay lại HTTP.

Để lab kiểm tra đúng mixed content, không dùng localhost làm hostname của ảnh. Browser xem loopback/localhost là nguồn có thể tin cậy trong một số secure-context check; dùng hai hostname .test riêng giúp mô phỏng hai origin rõ ràng.

### Bước 1 — Tạo hostname local

Trên Windows, mở Notepad bằng quyền Administrator và thêm hai dòng vào file:

```text
C:\Windows\System32\drivers\etc\hosts

127.0.0.1 secure-content.test
127.0.0.1 mixed-image.test
```

Lưu file hosts. Hai hostname sẽ trỏ về máy local nhưng vẫn là hostname riêng trong browser.

### Bước 2 — Tạo certificate local

Cài và dùng mkcert để tạo CA local được browser tin cậy:

```sh
mkcert -install
mkcert -cert-file local.pem -key-file local-key.pem secure-content.test mixed-image.test
```

Hai file certificate/key cần nằm cùng thư mục với file lab. Không dùng certificate này cho production.

### Bước 3 — Tạo file mixed-content-image-lab.cjs

```js
const http = require('node:http');
const https = require('node:https');
const fs = require('node:fs');

const PAGE_HOST = 'secure-content.test';
const IMAGE_HOST = 'mixed-image.test';

const page = [
  '<!doctype html>',
  '<html lang="vi"><head><meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width, initial-scale=1">',
  '<title>Mixed content image lab</title></head><body>',
  '<h1>HTTP image trong HTTPS page</h1>',
  '<p>Ảnh đầu có HTTPS endpoint; ảnh thứ hai chỉ có HTTP endpoint.</p>',
  '<figure>',
  '  <img id="auto-ok" width="240" height="100"',
  '    src="http://mixed-image.test/auto-ok.svg" alt="HTTPS endpoint available">',
  '  <figcaption>HTTP URL được nâng cấp; HTTPS trả ảnh.</figcaption>',
  '</figure>',
  '<figure>',
  '  <img id="http-only" width="240" height="100"',
  '    src="http://mixed-image.test/http-only.svg" alt="HTTPS endpoint missing">',
  '  <figcaption>HTTP có ảnh nhưng HTTPS trả 404.</figcaption>',
  '</figure>',
  '</body></html>',
].join('\n');

function sendSvg(res, label) {
  const svg = [
    '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="100">',
    '<rect width="100%" height="100%" fill="#d9f3e4"/>',
    '<text x="12" y="55" font-size="18">' + label + '</text>',
    '</svg>',
  ].join('');
  res.writeHead(200, {
    'Content-Type': 'image/svg+xml; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  res.end(svg);
}

function pathname(req, scheme) {
  return new URL(req.url, scheme + '://' + req.headers.host).pathname;
}

const httpServer = http.createServer((req, res) => {
  const host = (req.headers.host || '').split(':')[0].toLowerCase();
  const path = pathname(req, 'http');
  console.log('HTTP request:', host, path);

  if (host === IMAGE_HOST &&
      (path === '/auto-ok.svg' || path === '/http-only.svg')) {
    return sendSvg(res, 'HTTP origin response');
  }

  res.writeHead(404);
  res.end('Not found');
});

const tls = {
  key: fs.readFileSync('./local-key.pem'),
  cert: fs.readFileSync('./local.pem'),
};

const httpsServer = https.createServer(tls, (req, res) => {
  const host = (req.headers.host || '').split(':')[0].toLowerCase();
  const path = pathname(req, 'https');
  console.log('HTTPS request:', host, path);

  if (host === PAGE_HOST && path === '/') {
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
      'Content-Security-Policy':
        "default-src 'self'; img-src 'self' https://" + IMAGE_HOST +
        "; object-src 'none'; base-uri 'none'",
      'X-Content-Type-Options': 'nosniff',
    });
    return res.end(page);
  }

  if (host === IMAGE_HOST && path === '/auto-ok.svg') {
    return sendSvg(res, 'HTTPS upgraded image');
  }

  if (host === IMAGE_HOST && path === '/http-only.svg') {
    res.writeHead(404, { 'Cache-Control': 'no-store' });
    return res.end('No HTTPS version for this image');
  }

  res.writeHead(404);
  res.end('Not found');
});

httpServer.listen(80, '0.0.0.0', () => {
  console.log('HTTP image host listening on port 80');
});

httpsServer.listen(443, '0.0.0.0', () => {
  console.log('HTTPS page/image hosts listening on port 443');
  console.log('Open https://' + PAGE_HOST + '/');
});
```

### Bước 4 — Chạy lab

Mở terminal có quyền phù hợp để bind cổng 80 và 443, chuyển tới thư mục chứa certificate và file JavaScript, sau đó chạy:

```sh
node mixed-content-image-lab.cjs
```

Mở browser tại https://secure-content.test/. Certificate phải được browser tin cậy; nếu xuất hiện cảnh báo certificate, dừng và xử lý CA/hostname trước khi kiểm thử.

### Bước 5 — Quan sát kết quả

Mở DevTools → Network, bật Preserve log và tải lại trang:

1. auto-ok.svg được khai báo bằng HTTP nhưng request thực tế phải chuyển sang https://mixed-image.test/auto-ok.svg; ảnh hiển thị dòng “HTTPS upgraded image”.
2. http-only.svg cũng được nâng sang HTTPS, nhưng HTTPS endpoint trả 404 nên ảnh không hiển thị.
3. Browser không nên gửi request HTTP để fallback cho ảnh thứ hai. Terminal thường ghi request ở HTTPS server; nếu thấy request HTTP, kiểm tra browser/version và URL thực tế.
4. Console có thể hiển thị thông báo auto-upgrade hoặc lỗi tải ảnh; nội dung thông báo khác nhau theo browser.

Kết quả mong đợi:

| Ảnh | Có ở HTTP | Có ở HTTPS | Kết quả |
|---|---:|---:|---|
| auto-ok.svg | Có | Có | Browser nâng cấp và ảnh hiển thị |
| http-only.svg | Có | Không | Browser nâng cấp, HTTPS trả 404 và ảnh thất bại |

Lab minh họa rằng browser có thể tự nâng cấp HTTP image và không tự hạ cấp lại khi HTTPS endpoint không phục vụ tài nguyên.

### Bước 6 — Thử CSP upgrade-insecure-requests

Thêm directive sau vào header CSP của HTTPS page:

```http
Content-Security-Policy: upgrade-insecure-requests; default-src 'self'; img-src 'self' https://mixed-image.test
```

Tải lại trang và quan sát Network. Các URL tài nguyên HTTP trong document được yêu cầu nâng lên HTTPS theo CSP. Ảnh http-only.svg vẫn thất bại vì HTTPS endpoint trả 404; directive không tạo bản sao ảnh hoặc fallback HTTP.

Sau khi thử nghiệm, bỏ directive nếu không cần cho lab và giữ policy theo cấu hình mong muốn.

## 9. Chẩn đoán lỗi HTTP image

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Ảnh không hiển thị trên HTTPS page | HTTPS endpoint không có ảnh hoặc TLS lỗi | Mở URL HTTPS trực tiếp, kiểm tra Network status và certificate |
| Một số ảnh hiển thị, một số ảnh mất | srcset, CSS hoặc CMS dùng host khác | Kiểm tra request URL cuối và từng candidate |
| Ảnh tải được trên HTTP page nhưng không tải trên HTTPS page | Mixed content auto-upgrade thất bại hoặc request bị chặn | Đọc Console và xem scheme thực tế trong Network |
| Ảnh chuyển sang URL HTTPS rồi 404 | Server chỉ cấu hình route trên HTTP | Cấu hình route HTTPS hoặc thay nguồn ảnh |
| Ảnh chuyển hướng sang HTTP | CDN/legacy host redirect sai | Bật Preserve log, kiểm tra redirect chain |
| Chỉ browser cũ gặp lỗi | Hành vi mixed-content khác phiên bản | Kiểm thử browser matrix, cập nhật URL nguồn sang HTTPS |
| CSP báo vi phạm img-src | Host ảnh không nằm trong allowlist | Xác minh host cần thiết rồi thêm origin chính xác |
| Ảnh vẫn tải qua HTTP trong môi trường cũ | Browser không auto-upgrade hoặc môi trường có ngoại lệ | Cập nhật nguồn ảnh và cân nhắc CSP upgrade-insecure-requests |

### 9.1. Dùng Network thay vì chỉ xem HTML

HTML source có thể vẫn chứa URL HTTP ngay cả khi browser đã nâng cấp request. Để xác định trạng thái thật:

- Xem Request URL trong Network.
- Kiểm tra redirect chain và response cuối.
- Xem Initiator để biết request đến từ img, CSS, script hay framework.
- Bật Disable cache khi thử nghiệm.
- Xem Console để biết request bị mixed-content block, CSP block hay lỗi TLS/HTTP.
- Lặp lại trên viewport khác để kích hoạt candidate srcset khác.

Đừng nhầm lỗi mixed content với lỗi CORS. Ảnh hiển thị qua img thường không cần CORS nếu chỉ render; CORS chỉ liên quan khi ứng dụng cần truy cập pixel qua canvas hoặc dùng các tính năng cross-origin khác. Một request có thể bị chặn vì mixed content trước khi vấn đề CORS có ý nghĩa.

## 10. Checklist bảo vệ ảnh trên HTTPS

- [ ] Trang chính được phục vụ qua HTTPS với certificate hợp lệ.
- [ ] Mọi img[src] và candidate trong srcset dùng HTTPS.
- [ ] Các URL trong picture/source, CSS background, image-set và JavaScript đã được rà soát.
- [ ] Ảnh từ CMS/API không trả URL HTTP cũ.
- [ ] HTTPS endpoint của CDN/host ảnh trả đúng nội dung và status.
- [ ] Không có redirect cuối về HTTP.
- [ ] Không dùng wildcard rộng trong CSP img-src nếu chỉ cần một vài host.
- [ ] upgrade-insecure-requests chỉ được bật sau khi đánh giá toàn bộ tài nguyên.
- [ ] HSTS chỉ được bật khi host và subdomain đã sẵn sàng HTTPS.
- [ ] Network không còn request ảnh HTTP trên các workflow quan trọng.
- [ ] Đã kiểm tra browser, thiết bị, breakpoint và lazy-loaded image.
- [ ] Có quy trình rà soát URL ảnh mới khi nhập nội dung hoặc triển khai CDN.

## 11. Câu hỏi tự kiểm tra

**1.** Vì sao HTTP image trong HTTPS page là mixed content?  
**Trả lời:** Document được tải qua HTTPS nhưng một tài nguyên của document được yêu cầu qua kết nối HTTP không có TLS.

**2.** Browser hiện đại thường xử lý HTTP image như thế nào?  
**Trả lời:** Thường tự nâng request sang HTTPS; nếu HTTPS endpoint không hoạt động hoặc không có tài nguyên, browser chặn request thay vì fallback về HTTP.

**3.** Vì sao không thể kết luận HTTP image luôn an toàn vì nó không chạy JavaScript?  
**Trả lời:** Nội dung ảnh vẫn có thể bị sửa, dùng để theo dõi hoặc làm sai lệch thông tin người dùng nhìn thấy.

**4.** srcset và picture tạo thêm yêu cầu kiểm thử nào?  
**Trả lời:** Browser có thể chọn URL khác theo viewport/density; cần kiểm tra mọi candidate chứ không chỉ img.src.

**5.** CSP img-src có tự nâng URL HTTP sang HTTPS không?  
**Trả lời:** Không. img-src giới hạn nguồn ảnh; upgrade-insecure-requests mới yêu cầu nâng URL tài nguyên insecure.

**6.** Nếu HTTP image được nâng lên HTTPS nhưng HTTPS trả 404, browser có nên thử HTTP lại không?  
**Trả lời:** Không. Fallback HTTP sẽ làm mất bảo vệ toàn vẹn và bí mật của kết nối.

**7.** HSTS khác browser mixed-content auto-upgrade ở đâu?  
**Trả lời:** HSTS ghi nhớ yêu cầu dùng HTTPS cho một host; mixed-content auto-upgrade xử lý một số request HTTP phát sinh từ secure document.

**8.** Vì sao cần kiểm tra redirect chain?  
**Trả lời:** URL ban đầu có thể là HTTPS nhưng server redirect tới HTTP, khiến request cuối vẫn không an toàn và có thể bị browser chặn.

**9.** Vì sao không nên chỉ tìm chuỗi http:// trong HTML source?  
**Trả lời:** URL có thể nằm trong CSS, JavaScript, CMS/API hoặc được tạo động; Network trace mới cho biết request cuối thực tế.

**10.** Có nên bật block-all-mixed-content để giải quyết vấn đề không?  
**Trả lời:** Không nên dựa vào directive đã lỗi thời này; hãy cập nhật URL sang HTTPS, cấu hình TLS và dùng CSP hiện hành.

## Tổng kết

HTTP image trong trang HTTPS là một dạng mixed content. Browser hiện đại thường tự nâng request ảnh lên HTTPS; nếu endpoint HTTPS không phục vụ ảnh hoặc TLS lỗi, request thất bại và không được hạ cấp về HTTP. Hãy rà soát img src, srcset, picture, CSS và URL tạo động; kiểm tra request cuối trong Network; cấu hình CDN/TLS đúng và khai báo CSP img-src theo nguồn cần thiết. upgrade-insecure-requests và HSTS có thể hỗ trợ quá trình chuyển đổi, nhưng cách xử lý bền vững là phục vụ mọi ảnh qua HTTPS ngay từ nguồn dữ liệu.
