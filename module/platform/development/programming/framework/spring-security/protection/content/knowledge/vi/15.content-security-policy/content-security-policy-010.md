# img-src, font-src và tài nguyên từ dịch vụ bên ngoài

> **Chương:** Chính sách nội dung CSP  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Bài toán: ảnh và font thường không nằm cùng nơi với HTML

Một ứng dụng quản lý đơn hàng chạy ở `https://app.example.com`. HTML và JavaScript được phục vụ từ chính ứng dụng, nhưng ảnh sản phẩm nằm ở `https://images.example.net`, bộ font của thương hiệu nằm ở `https://fonts.example.net` và stylesheet của một thư viện UI được tải từ `https://styles.example.net`.

Đội phát triển bật CSP:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'
~~~

Sau triển khai, script nội bộ vẫn chạy nhưng ảnh sản phẩm không xuất hiện, icon dạng font trở thành ô vuông và một số thành phần giao diện dùng font dự phòng. Đây chưa chắc là lỗi server, URL hay mạng: trình duyệt có thể đang thực thi **Content Security Policy (CSP)** và chặn các nguồn chưa được cấp phép.

Hai directive trọng tâm là:

- **`img-src`:** giới hạn các nguồn tài nguyên ảnh trong những ngữ cảnh chịu kiểm tra ảnh của CSP, như phần tử `<img>` hoặc ảnh nền CSS.
- **`font-src`:** giới hạn nguồn tệp font được trình duyệt tải, thường thông qua `@font-face` trong CSS.

Đối với tài nguyên bên thứ ba, một trang còn cần cho phép **đúng bước tải**: stylesheet bên ngoài chịu `style-src`, font được stylesheet tham chiếu chịu `font-src` và ảnh trong CSS có thể chịu `img-src`. Chỉ cho phép domain CSS không có nghĩa mọi tệp font hoặc ảnh được kéo theo đều được phép.

**Kết quả cần đạt:** người học có thể thiết kế allowlist ảnh/font theo nguồn thực tế; lý giải fallback `default-src`; xử lý ảnh `data:`/`blob:` và font cross-origin; phân biệt CSP với CORS; cấu hình trên Spring Security Servlet/WebFlux; kiểm thử và chẩn đoán các vấn đề frontend khi dùng CDN.

## 2. Đọc một chính sách có img-src và font-src

Giả sử tài liệu nhận header sau:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self' https://styles.example.net; img-src 'self' https://images.example.net; font-src 'self' https://fonts.example.net; connect-src 'self' https://api.example.net; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
~~~

Hãy tách các nhóm:

| Directive | Phạm vi chính trong ví dụ | Nguồn được cho phép |
|---|---|---|
| `default-src 'none'` | Giá trị dự phòng cho các fetch directive khi chưa có directive chuyên biệt | Không nguồn nào |
| `script-src 'self'` | JavaScript theo phạm vi của script directive | Cùng origin |
| `style-src 'self' https://styles.example.net` | CSS/stylesheet | Cùng origin và stylesheet CDN |
| `img-src 'self' https://images.example.net` | Ảnh được tải theo phạm vi CSP | Cùng origin và image CDN |
| `font-src 'self' https://fonts.example.net` | Webfont được tải | Cùng origin và font CDN |
| `connect-src 'self' https://api.example.net` | Kết nối từ JS như fetch/XHR | Cùng origin và API |
| `object-src 'none'` | Object/embed | Không nguồn nào |
| `base-uri 'self'` | Base URL do thẻ `<base>` khai báo | Cùng origin |
| `form-action 'self'` | Đích gửi form | Cùng origin |
| `frame-ancestors 'none'` | Những origin được nhúng trang hiện tại | Không origin nào |

Nguồn `'self'` về cơ bản chỉ origin của tài liệu (scheme, host và port theo quy tắc khớp nguồn CSP), **không phải tất cả subdomain**. Ví dụ `https://images.example.net` không tự thuộc `'self'` của trang `https://app.example.com`.

Đây là chính sách minh họa: hệ thống nào có video, iframe, worker, manifest, script/style inline, analytics hoặc nguồn khác phải kiểm kê và bổ sung directive tương ứng. Không nên sao chép nguyên policy vào production khi chưa xác định nhu cầu của ứng dụng.

## 3. Fallback của img-src và font-src về default-src

Cả `img-src` và `font-src` là **fetch directive** có fallback về `default-src` nếu chúng không được khai báo. Tuy nhiên, khi đã khai báo directive riêng, nguồn của `default-src` **không tự cộng vào** danh sách đó.

### 3.1. Không khai báo img-src

~~~http
Content-Security-Policy: default-src 'self'
~~~

Trong chính sách này, ảnh cùng origin được phép theo fallback; ảnh ở `https://images.example.net` có thể bị chặn.

Nếu bạn đổi thành:

~~~http
Content-Security-Policy: default-src 'self'; img-src https://images.example.net
~~~

thì ảnh cùng origin **có thể bị chặn**, bởi `img-src` giờ chỉ liệt kê CDN ảnh. Muốn cho phép cả hai:

~~~http
Content-Security-Policy: default-src 'self'; img-src 'self' https://images.example.net
~~~

### 3.2. Không khai báo font-src

~~~http
Content-Security-Policy: default-src 'none'; style-src 'self'
~~~

Ở đây, CSS cùng origin có thể tải, nhưng các tệp font ngoài không được phép chỉ vì đã có `style-src 'self'`. `font-src` vắng mặt nên nguồn font rơi về `default-src 'none'`.

Nếu bổ sung:

~~~http
Content-Security-Policy: default-src 'none'; style-src 'self'; font-src 'self' https://fonts.example.net
~~~

thì font ở cùng origin hoặc ở CDN font được cho phép theo CSP. Tất nhiên, trình duyệt vẫn phải tải được tài nguyên thật và có thể còn áp dụng CORS cho webfont cross-origin.

### 3.3. Ma trận dự đoán

Giả sử trang `https://app.example.com`:

| CSP | `/images/logo.png` | `https://images.example.net/p.png` | `/fonts/site.woff2` | `https://fonts.example.net/site.woff2` |
|---|---|---|---|---|
| `default-src 'self'` | Cho phép | Chặn | Cho phép | Chặn |
| `default-src 'none'` | Chặn | Chặn | Chặn | Chặn |
| `default-src 'none'; img-src 'self' https://images.example.net` | Cho phép | Cho phép | Chặn | Chặn |
| `default-src 'none'; font-src 'self' https://fonts.example.net` | Chặn | Chặn | Cho phép | Cho phép |
| `default-src 'none'; img-src 'self' https://images.example.net; font-src 'self' https://fonts.example.net` | Cho phép | Cho phép | Cho phép | Cho phép |

“Cho phép” nghĩa là **không bị policy CSP đó từ chối**, không đồng nghĩa nguồn tồn tại, file hợp lệ hay tất cả kiểm tra của trình duyệt đã thành công. Nếu response có thêm CSP thực thi từ proxy/CDN, phải thỏa **mọi** policy liên quan.

## 4. img-src kiểm soát ảnh xuất hiện ở đâu?

Các tình huống phổ biến:

~~~html
<!-- Ảnh trong nội dung -->
<img src="/images/logo.png" alt="Logo">
<img src="https://images.example.net/products/42.webp" alt="Sản phẩm">

<!-- Responsive image: browser chọn một ứng viên -->
<picture>
  <source media="(min-width: 800px)"
          srcset="https://images.example.net/hero-large.webp">
  <img src="/images/hero-small.webp" alt="Giới thiệu">
</picture>

<!-- Một số trường hợp còn có icon trong head -->
<link rel="icon" href="/images/favicon.png">
~~~

Trong các ngữ cảnh ảnh chịu CSP, `img-src` kiểm soát nguồn ảnh mà browser định tải. Khi dùng `srcset` hoặc `<picture>`, browser có thể chọn một URL khác nhau tùy kích thước màn hình, density, định dạng được hỗ trợ. Cần kiểm thử **những ứng viên thật sự được lựa chọn**, không chỉ đọc một giá trị `src` trong HTML.

### 4.1. Ảnh nền trong CSS

~~~css
.product-card {
  background-image: url("https://images.example.net/patterns/bg.webp");
}
~~~

Nếu stylesheet chứa quy tắc này được tải thành công, browser còn thực hiện một request ảnh. Request ảnh cần được `img-src` cho phép. Do đó:

~~~http
Content-Security-Policy: default-src 'none'; style-src 'self'; img-src 'self' https://images.example.net
~~~

cho phép CSS cùng origin và ảnh nền từ CDN về mặt CSP. Nếu chỉ có `style-src 'self'` mà `img-src` không phù hợp, nền vẫn có thể không xuất hiện.

**Phân biệt:** `style-src` nói tới stylesheet và nội dung style; `img-src` nói tới các request ảnh do stylesheet hoặc HTML khởi tạo. Đừng mở rộng `style-src` để sửa lỗi bị chặn ở `img-src`.

### 4.2. SVG, icon và ảnh động

Một tệp SVG được tải qua `<img src="/icons/mark.svg">` thường nằm trong cơ chế xử lý ảnh của browser, nên nguồn của nó chịu `img-src`. Tuy nhiên, SVG còn có thể được dùng như tài liệu độc lập, nhúng qua `<object>` hoặc `<iframe>`, lúc đó các chính sách áp dụng không đồng nhất với SVG dùng làm ảnh.

Không nên tuyên bố “mọi SVG đều vô hại” chỉ vì `img-src` cho phép chúng. Cần xem xét cách phục vụ file, kiểu nội dung, policy và khả năng người dùng upload SVG. CSP không thay thế kiểm tra MIME type, xử lý upload an toàn hoặc các biện pháp chống nội dung chủ động.

Với favicon và các loại icon do browser hoặc manifest tự tải, mức áp dụng CSP có thể khác nhau giữa ngữ cảnh và trình duyệt. Hãy kiểm thử trên browser mục tiêu; đừng dựa vào `img-src` làm cơ chế bảo vệ duy nhất cho mọi đường tải icon.

## 5. data: và blob: trong img-src

Không phải ảnh nào cũng đến từ một URL `https://...`. Ứng dụng có thể tạo ảnh tại browser:

~~~html
<!-- data URL: ví dụ dùng để minh họa định dạng -->
<img alt="Chấm màu"
     src="data:image/png;base64,BASE64_PNG_PLACEHOLDER">
~~~

Hoặc dùng `Blob` và object URL:

~~~javascript
const bytes = new Uint8Array([/* dữ liệu ảnh hợp lệ */]);
const blob = new Blob([bytes], { type: "image/png" });
const url = URL.createObjectURL(blob);

const image = document.getElementById("preview");
image.src = url;

// Chỉ hủy object URL khi chắc chắn không còn cần dùng.
image.addEventListener("load", () => {
  URL.revokeObjectURL(url);
}, { once: true });
~~~

Hai lược đồ này khác nhau:

- `data:` chứa dữ liệu ngay trong URL, không phải request tới một origin HTTPS thông thường.
- `blob:` tham chiếu tài nguyên Blob thông qua object URL do browser tạo; nó có cơ chế origin và vòng đời riêng.

Với CSP:

~~~http
Content-Security-Policy: img-src 'self' https://images.example.net
~~~

những URL `data:` hoặc `blob:` không được tự cho phép chỉ vì có `'self'` trong danh sách. Nếu ứng dụng có nhu cầu thực:

~~~http
Content-Security-Policy: img-src 'self' https://images.example.net data: blob:
~~~

Điều này cho phép thêm hai dạng nguồn ảnh theo CSP, nhưng **không nên thêm mặc định nếu không dùng**. Đặc biệt, không vì cần `data:` cho một biểu tượng nhỏ mà nới `script-src` bằng `data:` hoặc `'unsafe-inline'`. Các nhóm tài nguyên được cấu hình độc lập và có rủi ro khác nhau.

### Khi nào cân nhắc data:/blob:?

| Nhu cầu | Hướng xử lý ưu tiên |
|---|---|
| Logo, avatar, icon tĩnh | Dùng file cùng origin hoặc CDN ảnh đã kiểm soát |
| Ảnh preview vừa được người dùng chọn | Có thể dùng `blob:`, quản lý object URL và kiểm tra loại file |
| Ảnh nhỏ được nhúng trong HTML/CSS do build tool tạo | Có thể cần `data:` trong `img-src` sau khi kiểm kê |
| Dữ liệu ảnh được nhập từ URL bất kỳ của người dùng | Không tự động thêm mọi host vào CSP; xử lý URL/nguồn ảnh với quy tắc riêng |

Một ví dụ minh họa `Blob` rỗng hoặc không chứa dữ liệu PNG hợp lệ sẽ **không** hiển thị ảnh dù CSP có cho phép `blob:`. CSP chỉ là một bước kiểm tra, không biến dữ liệu tùy ý thành file ảnh hợp lệ.

## 6. font-src và @font-face: CSS được tải nhưng font có thể bị chặn

Webfont được khai báo trong CSS:

~~~css
@font-face {
  font-family: "Company Sans";
  src: url("https://fonts.example.net/company-sans.woff2") format("woff2");
  font-style: normal;
  font-weight: 400;
  font-display: swap;
}

body {
  font-family: "Company Sans", system-ui, sans-serif;
}
~~~

Để browser sử dụng webfont:

1. Tài liệu phải tải hoặc nhận được CSS theo `style-src`/directive style phù hợp.
2. Browser phân tích `@font-face` và phát request tới URL font.
3. Request font phải thỏa `font-src` hoặc fallback `default-src`.
4. Với font tải **cross-origin**, browser thường áp dụng yêu cầu CORS; server font cần trả response CORS hợp lệ.
5. File font phải tồn tại, đúng định dạng và có nội dung sử dụng được.

Một chính sách đáp ứng hai nhóm:

~~~http
Content-Security-Policy: default-src 'none'; style-src 'self' https://styles.example.net; font-src 'self' https://fonts.example.net
~~~

Nếu bạn chỉ thêm CDN vào `style-src` mà bỏ `font-src`, browser vẫn có thể từ chối tệp `.woff2`. Nếu stylesheet nằm ở `styles.example.net` còn font nằm ở `fonts.example.net`, đó là **hai source expression khác nhau**, không được suy ra lẫn nhau.

### 6.1. Ví dụ HTML dùng stylesheet CDN

~~~html
<head>
  <link rel="stylesheet"
        href="https://styles.example.net/brand.css">
</head>
<body>
  <h1>Quản lý đơn hàng</h1>
</body>
~~~

Giả sử `brand.css` chứa `@font-face` trỏ tới `fonts.example.net`. Browser cần cho phép cả:

~~~http
style-src 'self' https://styles.example.net
font-src 'self' https://fonts.example.net
~~~

Hai dòng này là **các đoạn directive minh họa**, không phải hai HTTP header riêng. Trong cấu hình thực tế, ghép chúng vào một giá trị CSP với dấu `;` phù hợp.

### 6.2. Font cục bộ và fallback font

Tệp ở `/fonts/company.woff2` thuộc cùng origin nếu ứng dụng thực sự phục vụ tệp đó:

~~~css
@font-face {
  font-family: "Company Sans";
  src: url("/fonts/company.woff2") format("woff2");
  font-display: swap;
}
~~~

Với `font-src 'self'`, nguồn font cùng origin được cho phép về mặt CSP. Nhưng font không tải được vẫn có thể khiến browser dùng font dự phòng. Người học cần phân biệt **bị CSP từ chối** với **bị CORS chặn**, HTTP 404, MIME không phù hợp, file lỗi hoặc font không có glyph cần dùng.

`font-display: swap` là lựa chọn hiển thị trong CSS để tránh văn bản bị ẩn quá lâu, **không phải directive CSP** và không cấp thêm quyền mạng.

## 7. CDN font và CORS: hai phép kiểm tra độc lập

Một nhầm lẫn phổ biến: thêm domain font vào `font-src` rồi kết luận lỗi webfont cross-origin chắc chắn hết.

Ví dụ:

~~~http
Content-Security-Policy: font-src 'self' https://fonts.example.net
~~~

Header này chỉ nói **tài liệu cho phép nguồn font** theo CSP. Khi font ở `https://fonts.example.net` được tải từ tài liệu `https://app.example.com`, browser còn xử lý chính sách **CORS** dành cho font cross-origin. Server font cần đáp ứng cơ chế CORS; ví dụ đơn giản nếu chỉ cho frontend cụ thể:

~~~http
Access-Control-Allow-Origin: https://app.example.com
~~~

Tùy việc request có credentials hay không và cách CDN cấu hình, phản hồi CORS cần phù hợp với loại request. Với những font công khai không dùng credentials, nhà cung cấp có thể dùng `Access-Control-Allow-Origin: *`; điều này là cấu hình CORS của **font server**, không có nghĩa CSP của trang nên mở `font-src *`.

| Trạng thái | `font-src` của trang | CORS của font server | Kết quả có thể xảy ra |
|---|---|---|---|
| Không cho phép CDN | Chặn | Bất kỳ | Font bị CSP từ chối |
| Cho phép CDN, CORS không phù hợp | Cho phép | Chặn | Browser không dùng được font cross-origin |
| Cho phép CDN, CORS phù hợp | Cho phép | Cho phép | Font có thể tải và dùng nếu file hợp lệ |
| Cho phép CDN, CDN trả 404 | Cho phép | Có thể phù hợp | Font vẫn không tồn tại |

### 7.1. Preload font và crossorigin

Ứng dụng có thể preload tệp font để cải thiện hiệu năng:

~~~html
<link rel="preload"
      href="https://fonts.example.net/company-sans.woff2"
      as="font"
      type="font/woff2"
      crossorigin>
~~~

Đối với preload font cross-origin, `crossorigin` giúp đặt chế độ yêu cầu phù hợp; thiếu hoặc đặt sai có thể gây tải lại, lỗi CORS hoặc không tái sử dụng được preload như dự kiến. Dù preload, browser vẫn kiểm tra CSP `font-src` và các điều kiện khác. Chỉ preload font thực sự được dùng; không preload toàn bộ bộ font nếu không cần.

### 7.2. Không sửa lỗi CORS bằng cách tắt CSP

Nếu Console cho biết `Refused to load the font ... because it violates ... font-src`, hãy sửa chính sách CSP của **trang HTML** sau khi xác minh nguồn font.

Nếu Console cho biết font bị **CORS policy** chặn, kiểm tra header CORS trên response font của CDN, request origin, credentials và cache. Thêm `font-src *` không thể tự làm server font trả header CORS đúng.

## 8. Ảnh cross-origin, CORS và canvas: hiển thị được chưa chắc đọc pixel được

Một ảnh từ CDN có thể hiển thị:

~~~html
<img id="productImage"
     src="https://images.example.net/products/42.png"
     alt="Sản phẩm">
~~~

Nếu `img-src` cho phép CDN, browser có thể hiển thị ảnh mà **không cần cơ chế CORS để chỉ hiển thị ảnh đơn thuần**. Tuy nhiên, nếu JavaScript muốn vẽ ảnh ấy vào canvas rồi đọc pixel:

~~~javascript
const image = document.getElementById("productImage");
const canvas = document.createElement("canvas");
const context = canvas.getContext("2d");

context.drawImage(image, 0, 0);
const pixels = context.getImageData(0, 0, 1, 1);
console.log(pixels.data);
~~~

canvas có thể bị coi là *tainted* vì ảnh cross-origin không được tải theo cơ chế CORS thích hợp. Khi đó `getImageData(...)`, `toDataURL()` hoặc việc xuất pixel có thể gặp `SecurityError`, **dù ảnh đã hiển thị**. Đây là giới hạn nguồn gốc của canvas, không phải lỗi `img-src`.

Nếu thực sự cần xử lý pixel từ CDN khác origin, có thể tải ảnh bằng CORS:

~~~javascript
const image = new Image();
image.crossOrigin = "anonymous"; // Đặt TRƯỚC khi bắt đầu tải src.
image.src = "https://images.example.net/products/42.png";

image.addEventListener("load", () => {
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const context = canvas.getContext("2d");
  context.drawImage(image, 0, 0);

  // Chỉ đọc được pixel nếu CORS và các điều kiện khác cho phép.
  console.log(context.getImageData(0, 0, 1, 1).data);
});
~~~

CDN ảnh cần trả header `Access-Control-Allow-Origin` phù hợp với trang. Việc đặt `crossOrigin` trên client mà server không cho CORS có thể làm **việc tải ảnh theo CORS thất bại** thay vì giải quyết vấn đề. CSP `img-src` vẫn phải cho phép nguồn ảnh.

**Không nhầm `connect-src` với `img-src`:** ảnh được tạo bằng `new Image()` hoặc `<img>` vẫn nằm trong nhóm ảnh; còn nếu ứng dụng lấy ảnh bằng `fetch(...)` rồi chuyển thành Blob, chính request `fetch` chịu `connect-src`, và việc gắn Blob URL vào ảnh có thể cần `blob:` trong `img-src`.

## 9. Tài nguyên từ dịch vụ bên ngoài: kiểm kê theo chuỗi tải

Một CDN có thể phục vụ nhiều nhóm tài nguyên, nhưng CSP phân biệt theo **loại request**, không đơn giản theo tên nhà cung cấp. Ví dụ giả định:

| Yêu cầu giao diện | Endpoint thực tế | Directive cần xem xét |
|---|---|---|
| CSS thư viện UI | `https://styles.example.net/ui.css` | `style-src` |
| Webfont mà CSS UI dùng | `https://fonts.example.net/ui.woff2` | `font-src` |
| Ảnh sản phẩm | `https://images.example.net/p/42.webp` | `img-src` |
| Ảnh nền trong CSS | `https://images.example.net/bg.webp` | `img-src` |
| JavaScript widget | `https://scripts.example.net/widget.js` | `script-src` |
| API dữ liệu sản phẩm | `https://api.example.net/products` | `connect-src` |
| Iframe hỗ trợ | `https://help.example.net/embed` | `frame-src` |
| Dữ liệu gửi qua HTML form | `https://pay.example.net/checkout` | `form-action` |

Để thiết kế chính sách đúng, cần **đi theo chuỗi tải tài nguyên thực tế**: HTML → CSS → `@font-face`/`url(...)`; HTML → JS → fetch/WebSocket; HTML → picture/srcset. Việc một tài nguyên gốc đã được tải không tự cấp quyền cho những request con mà nó tạo ra.

### 9.1. Không cho phép toàn bộ CDN theo thói quen

Ví dụ một cấu hình quá rộng:

~~~http
Content-Security-Policy: default-src https:; img-src https: data:; font-src https:
~~~

Trong nhiều hệ thống, `https:` mở quyền tải từ phần lớn host HTTPS, làm giảm khả năng hạn chế các nguồn không được tin cậy. Nếu nội dung bị chèn tạo URL ảnh tới host bên ngoài, `img-src https:` có thể không ngăn được request ấy. Vì thế nên dùng **host chính xác** và chỉ thêm `data:`/`blob:` khi thực sự cần.

### 9.2. Đường dẫn, biến thể ảnh và CDN redirect

Nhiều dịch vụ ảnh sử dụng:

~~~text
https://images.example.net/products/42.webp?w=400
https://images.example.net/products/42.webp?w=800
https://images.example.net/avatars/u123.png
~~~

Một host allowlist có thể đáp ứng nhiều biến thể kích thước nếu cùng host. Tuy vậy, nếu CDN trả redirect sang một hostname khác, hoặc môi trường staging dùng subdomain riêng, việc khớp nguồn có thể khác và browser có thể từ chối. CSP có quy tắc riêng khi khớp URL qua redirect; không nên suy rằng mọi URL chuyển hướng được phép chỉ vì đích ban đầu hợp lệ.

Khi nhà cung cấp thường xuyên đổi host, tránh việc tự động mở `*`. Có thể cân nhắc proxy ảnh/font qua một origin do ứng dụng kiểm soát hoặc ký hợp đồng ổn định endpoint, nhưng proxy cần bảo vệ chống SSRF, giới hạn domain đích, kích thước, loại file, cache và dữ liệu nhạy cảm.

### 9.3. Quyền riêng tư khi tải tài nguyên ngoài

Một request ảnh hoặc font có thể tiết lộ thông tin như địa chỉ IP, thời điểm truy cập và một số metadata HTTP cho nhà cung cấp. URL ảnh có query string chứa dữ liệu định danh cũng có thể gây lộ thông tin. CSP cho phép host **không có nghĩa** doanh nghiệp đã phê duyệt mọi dữ liệu gửi đến host đó.

Với ảnh bên thứ ba, hãy cân nhắc chính sách `Referrer-Policy`, thiết kế URL không lộ bí mật và nhu cầu thật sự trước khi cho phép một dịch vụ. Với font, đôi khi tự phục vụ tệp đã được cấp phép hợp lệ từ origin ứng dụng giúp giảm phụ thuộc và rủi ro quyền riêng tư; cần tuân thủ điều kiện bản quyền/phân phối font.

## 10. Chiến lược chính sách CSP cho ứng dụng Spring

Một policy minh họa cho dashboard:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self' https://styles.example.net; img-src 'self' https://images.example.net; font-src 'self' https://fonts.example.net; connect-src 'self' https://api.example.net; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
~~~

**Quy trình chọn nguồn:**

1. Xác định **origin phục vụ HTML** và tài nguyên nào được phục vụ cùng origin.
2. Kiểm kê tất cả nguồn ảnh, bao gồm `srcset`, CSS background, nội dung người dùng upload, preview `blob:`, data URL và ảnh của thư viện UI.
3. Kiểm kê nguồn CSS và nguồn font **riêng biệt**, bao gồm các URL bên trong `@font-face`, biến thể font weight và font icons.
4. Kiểm tra CORS của font CDN, CORS cho ảnh nếu ứng dụng đọc pixel trên canvas, và TLS/redirect.
5. Cấp phép host cụ thể theo từng directive; tránh nới `default-src` hoặc các directive không liên quan.
6. Thử với Report-Only trên trang đang vận hành trước khi bật thực thi nếu có nguy cơ làm hỏng frontend.
7. Kiểm tra response HTML thực tế qua reverse proxy/CDN; duy trì test cho các tài nguyên quan trọng.

### Bảo vệ lớp khác không được bỏ qua

`img-src` và `font-src` không thay thế chống XSS bằng mã hóa đầu ra/sanitize HTML. Chúng không tạo CSRF token, không thiết lập CORS của API, không ép TLS như HSTS và không bảo vệ cookie/session. Mô-đun `SPRING_SECURITY_HTTP_PROTECTION` sử dụng các cơ chế HTTP và browser này như **nhiều lớp độc lập bổ sung nhau**.

## 11. Cấu hình trong Spring Security Servlet

Với Spring MVC/Servlet, sử dụng `SecurityFilterChain` và API cấu hình CSP của `HttpSecurity`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    private static final String CSP_POLICY =
        "default-src 'none'; " +
        "script-src 'self'; " +
        "style-src 'self' https://styles.example.net; " +
        "img-src 'self' https://images.example.net; " +
        "font-src 'self' https://fonts.example.net; " +
        "connect-src 'self' https://api.example.net; " +
        "object-src 'none'; " +
        "base-uri 'self'; " +
        "form-action 'self'; " +
        "frame-ancestors 'none'";

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(CSP_POLICY)
            )
        );
        return http.build();
    }
}
~~~

Spring Security phát header theo chuỗi do ứng dụng cung cấp; nó **không tự quét template, CSS hoặc CDN** để nhận biết `img-src`/`font-src`. Chỉ những response đi qua chain này mới nhận header từ cấu hình đó. Cần xem trang đăng nhập, dashboard, trang lỗi và các nguồn HTML nếu ứng dụng dùng nhiều `SecurityFilterChain`.

### 11.1. HeaderWriter trực tiếp

Nếu Servlet stack đã dùng custom header writers:

~~~java
import org.springframework.security.web.header.writers.ContentSecurityPolicyHeaderWriter;

ContentSecurityPolicyHeaderWriter writer =
    new ContentSecurityPolicyHeaderWriter(
        "default-src 'none'; " +
        "style-src 'self' https://styles.example.net; " +
        "img-src 'self' https://images.example.net; " +
        "font-src 'self' https://fonts.example.net; " +
        "object-src 'none'"
    );

http.headers(headers -> headers.addHeaderWriter(writer));
~~~

Đây là **cách khác** để phát CSP trong Servlet, không phải thao tác bắt buộc thực hiện thêm sau DSL ở trên. Nếu có nhiều CSP thực thi, browser áp dụng tất cả; chính sách thứ hai có thể chặn ảnh/font mà chính sách thứ nhất đã cho phép.

### 11.2. Dự án dùng Spring chỉ làm API

Khi HTML/JavaScript của frontend được trả từ CDN ở `https://app.example.com` còn Spring MVC chỉ trả JSON ở `https://api.example.net`, đặt CSP trên JSON response **không áp dụng** chính sách đó cho tài liệu HTML của frontend. Phải cấu hình CSP ở **server phục vụ HTML**. Nếu ứng dụng đồng thời trả HTML cho màn quản trị, CSP có thể cần triển khai tại cả hai origin theo nhu cầu.

## 12. Cấu hình Spring Security Reactive/WebFlux

Với WebFlux, dùng `ServerHttpSecurity` và `SecurityWebFilterChain`; ý nghĩa của CSP với browser không đổi:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        String policy =
            "default-src 'none'; " +
            "script-src 'self'; " +
            "style-src 'self' https://styles.example.net; " +
            "img-src 'self' https://images.example.net; " +
            "font-src 'self' https://fonts.example.net; " +
            "connect-src 'self' https://api.example.net; " +
            "object-src 'none'; " +
            "base-uri 'self'; " +
            "form-action 'self'; " +
            "frame-ancestors 'none'";

        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(policy)
            )
        );
        return http.build();
    }
}
~~~

Đối với WebFlux serving HTML hoặc SSR templates, chính sách nên nằm trên response HTML thực sự. Đối với WebFlux chỉ cung cấp API, cần phối hợp hệ thống frontend để cấu hình CSP đúng nơi.

### 12.1. Không dùng CSP để sửa lỗi phát font ở backend

Nếu server font (Spring MVC static resources, WebFlux static resources hoặc CDN) trả 404, MIME sai hoặc CORS thiếu, việc nới `font-src` chưa chắc giúp. Phải kiểm tra từng lớp: **CSP của trang → request font → HTTP status/MIME → CORS của font server → font hợp lệ**.

Tương tự, nếu ảnh nằm sau authorization hoặc URL có chữ ký hết hạn, `img-src` có thể cho phép request nhưng response vẫn là 401/403 hoặc lỗi file. Hãy phân biệt những trường hợp đó khi debug.

## 13. Report-Only khi siết nguồn ảnh và font

Một ứng dụng đang có nhiều ảnh/font từ các CDN khác nhau có thể triển khai thử policy mới:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; img-src 'self' https://images.example.net; font-src 'self' https://fonts.example.net; report-uri /_csp/report
~~~

Đây là **candidate policy**, dùng để quan sát nguồn ảnh/font ngoài allowlist. Report-Only **không chặn chỉ vì chính sách thử nghiệm đó**. Nếu response đồng thời có CSP thực thi, CSP thực thi vẫn có quyền chặn tài nguyên.

Một vi phạm `img-src` hoặc `font-src` có thể xuất hiện trên DevTools Console/Issues và, nếu trình duyệt hỗ trợ reporting và đã cấu hình endpoint, được gửi về collector. Không phải mọi violation đều là tấn công: có thể do ảnh của thư viện UI, font variant ít sử dụng, extension hoặc CDN chuyển host.

### Quy trình triển khai an toàn

| Bước | Việc cần làm | Bằng chứng cần thu thập |
|---|---|---|
| 1. Kiểm kê | Ghi nguồn ảnh/font và chuỗi tải CSS → font, HTML/CSS → ảnh | Danh sách origin và tính năng sử dụng |
| 2. Candidate CSP | Bật Report-Only trên HTML ở môi trường phù hợp | Các vi phạm `img-src`/`font-src` theo route/browser |
| 3. Phân loại | Xác nhận nguồn hợp lệ, bỏ CDN cũ hoặc sửa đường dẫn | Origin được chủ sản phẩm phê duyệt |
| 4. Kiểm tra CORS | Với font cross-origin và ảnh cần đọc pixel | Response CORS và test browser |
| 5. Enforcement | Chuyển candidate sang `Content-Security-Policy` có kiểm soát | Ảnh/font hợp lệ hiển thị, nguồn ngoài vẫn bị chặn |
| 6. Theo dõi | Đọc Console/report sau triển khai, kiểm tra proxy/CDN | Không có hồi quy quan trọng, policy còn chặt |

**Không cần loại bỏ mọi report**: extension, nguồn không đáng tin và các request bị chặn có thể tiếp tục tạo violation. Quan trọng là **tính năng hợp lệ không bị chặn** và những nguồn được mở đều có lý do rõ ràng.

Collector nhận report phải kiểm soát kích thước body, rate limit và dữ liệu nhạy cảm; không tin trường URL hoặc policy mà client gửi. CSP reporting giúp quan sát nhưng không thay thế giám sát lỗi tải tài nguyên thông thường.

## 14. Kiểm thử bằng MockMvc và WebTestClient

Các test phía server kiểm tra **header CSP được phát đúng**, không mô phỏng đầy đủ hoạt động tải ảnh/font của trình duyệt.

### 14.1. Servlet với MockMvc

Giả sử có route HTML `/dashboard` trong ứng dụng và security filters được bật trong test:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

mockMvc.perform(get("/dashboard"))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("img-src 'self' https://images.example.net")
    ))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("font-src 'self' https://fonts.example.net")
    ))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("style-src 'self' https://styles.example.net")
    ));
~~~

Nếu route yêu cầu đăng nhập, phải chuẩn bị authentication trong test để kiểm tra đúng response HTML mục tiêu. Tránh kết luận CSP sai khi request chỉ nhận redirect 302 hoặc response 401/403.

### 14.2. Reactive với WebTestClient

~~~java
// Trong lớp test WebFlux đã có WebTestClient và route HTML /dashboard.
webTestClient.get()
    .uri("/dashboard")
    .exchange()
    .expectHeader()
    .valueMatches(
        "Content-Security-Policy",
        ".*img-src 'self' https://images.example.net.*"
    );
~~~

Nếu muốn kiểm tra font, có thể thêm assertion riêng cho `font-src`. Nếu hệ thống áp dụng nhiều policy hoặc proxy chỉnh sửa header, cần test ở tầng trả HTML cuối cùng cho browser.

## 15. Ma trận kiểm thử trực tiếp trên trình duyệt

Với ứng dụng demo ở `https://app.example.com`, cho CSP:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self' https://styles.example.net; img-src 'self' https://images.example.net; font-src 'self' https://fonts.example.net; object-src 'none'; base-uri 'self'
~~~

Hãy thử trong môi trường mà bạn kiểm soát:

| Hành vi | Kỳ vọng theo CSP | Kiểm tra thêm |
|---|---|---|
| `<img src="/images/logo.png">` | Cho phép | 200 và đúng MIME/file |
| `<img src="https://images.example.net/p.png">` | Cho phép | CDN tồn tại, CORS nếu cần canvas |
| `<img src="https://untrusted.example/p.png">` | Chặn | Console/Network báo `img-src` |
| CSS nền từ `images.example.net` | Cho phép | CSS phải tải được theo `style-src` |
| CSS `@font-face` trỏ `fonts.example.net` | Cho phép về CSP | CORS font, font file, glyph |
| CSS font ở `https://other-fonts.example.net` | Chặn | Console chỉ ra `font-src` |
| `data:image/png;base64,...` | Chặn nếu không có `data:` | Phân biệt file dữ liệu sai với CSP |
| Ảnh preview bằng `blob:` | Chặn nếu chưa mở `blob:` | Kiểm tra object URL và revoke |
| CSS ở `styles.example.net`, font ở `fonts.example.net` | Cần cả `style-src` và `font-src` phù hợp | Xem hai request khác nhau |
| `fetch("https://images.example.net/p.png")` từ JS | Không do `img-src` quyết định ở bước fetch | `connect-src`/CORS của fetch |

### Quy trình kiểm thử có thể lặp lại

1. Mở DevTools → Network; chọn request **document HTML** để xem giá trị CSP. Không nhầm CSP trên response ảnh hoặc font với CSP của tài liệu.
2. Ở Network, lọc theo **Img**, **Font** và **CSS**; kiểm tra URL, status, redirect và response headers của từng request.
3. Mở Console/Issues, tìm thông báo `Refused to load the image` hoặc `Refused to load the font` và directive gây chặn.
4. Kiểm tra `srcset`/`picture` ở kích thước màn hình khác nhau; browser có thể tải ứng viên ảnh khác.
5. Với font CDN, mở request font để xem CORS header. Với ảnh dùng canvas, kiểm tra `crossOrigin` được đặt trước `src` và việc đọc pixel có hoạt động.
6. Tạo một ảnh ngoài allowlist để xác nhận chính sách thực thi vẫn từ chối nguồn không được phép.
7. Lặp lại trên browser mục tiêu và qua reverse proxy/CDN của staging/production, bởi nguồn và cách browser xử lý asset có thể thay đổi.

Chú ý: một ảnh không hiển thị có thể do đường dẫn sai, phản hồi 403/404, MIME hoặc nội dung file hỏng. Không phải mọi ô ảnh trống đều có nghĩa `img-src` đang chặn.

## 16. Chẩn đoán các xung đột phổ biến

| Triệu chứng | Cách xác định | Hướng xử lý |
|---|---|---|
| Ảnh từ CDN bị chặn, ảnh nội bộ vẫn hiện | CSP có `img-src 'self'` nhưng thiếu CDN | Thêm **đúng origin ảnh** nếu được phê duyệt |
| Ảnh nội bộ bị chặn sau khi thêm CDN | `img-src https://images.example.net` đã thay thế fallback `default-src 'self'` | Thêm `'self'` trực tiếp vào `img-src` |
| Font chữ trở thành font hệ thống | Font bị CSP/CORS/404 hoặc file không dùng được | Kiểm tra Network Font, Console, `font-src` và CORS |
| Stylesheet tải được nhưng font không tải | CSS và font dùng hai origin, hai directive khác nhau | Khai báo `font-src` phù hợp; kiểm tra CORS font |
| CSS nền không hiện dù stylesheet có mặt | Ảnh nền chịu `img-src` | Kiểm tra URL ảnh, `img-src`/fallback |
| `srcset` có lúc hiện lúc không | Browser chọn ảnh từ host khác theo màn hình | Kiểm kê mọi ứng viên, test responsive |
| Preview người dùng tải lên không hiện | Blob URL cần `blob:` hoặc dữ liệu không hợp lệ | Đánh giá `img-src blob:` và vòng đời object URL |
| Icon base64 không hiện | CSP không cho `data:` hoặc data URL sai | Chỉ thêm `data:` vào `img-src` nếu cần và kiểm tra payload |
| Ảnh hiển thị nhưng canvas không đọc pixel | Canvas bị taint do ảnh cross-origin không tải theo CORS | Dùng `crossOrigin` và CORS đúng từ CDN ảnh |
| Font cross-origin báo CORS dù CSP cho phép | CDN font thiếu `Access-Control-Allow-Origin` phù hợp | Sửa CORS ở **font server/CDN** |
| CDN trả redirect sang host lạ | CSP URL matching hoặc nguồn đích không khớp | Xác minh chuỗi redirect và host được phê duyệt |
| Local đúng, production sai | Origin, port, path, TLS hoặc CDN khác | Đọc response HTML production và các asset URL thực tế |
| Chỉ thấy lỗi khi login/error page | Trang đó do security chain/container/proxy khác phục vụ | Xác định nơi trả HTML và policy tương ứng |
| Một CSP cho phép nhưng browser vẫn chặn | Có thêm CSP thực thi khác | Kiểm tra tất cả `Content-Security-Policy` header |
| Report-Only báo vi phạm nhưng ảnh vẫn hiện | Report-Only không chặn | Chuyển sang enforced CSP sau kiểm thử |
| API JSON có CSP nhưng HTML thiếu | CSP đặt tại backend API không phục vụ HTML | Cấu hình tại HTML server/CDN |

### Những điều không nên làm

- Không mở `img-src *` hoặc `font-src https:` chỉ để xóa thông báo Console.
- Không cho phép mọi domain hình ảnh do người dùng nhập tự động trở thành source expression. Nếu ứng dụng hiển thị ảnh bên ngoài, cần chiến lược kiểm soát URL, proxy hoặc cơ chế ảnh phù hợp.
- Không nới `script-src`/`default-src` chỉ vì một font hoặc ảnh bị chặn.
- Không tắt CORS/CSRF/session protection để sửa lỗi CSP: chúng là những cơ chế khác.
- Không coi `img-src` là biện pháp chống thất thoát dữ liệu tuyệt đối nếu `connect-src`, `form-action` hay các đường tải khác đang mở quá rộng.
- Không coi font/ảnh được CSP cho phép là nội dung đáng tin tuyệt đối; phải kiểm soát nguồn, dữ liệu và những tác động về quyền riêng tư.

## 17. Bài thực hành tổng hợp

**Bối cảnh:** Trang dashboard Spring Boot sử dụng HTML và JavaScript cùng origin, ảnh sản phẩm từ `images.example.net`, CSS từ `styles.example.net` và font từ `fonts.example.net`. Giao diện còn có chức năng preview ảnh local trước khi upload.

1. Cấu hình `default-src 'none'`; thêm `script-src 'self'`, `style-src 'self' https://styles.example.net`, `img-src 'self' https://images.example.net` và `font-src 'self' https://fonts.example.net`.
2. Dùng MockMvc hoặc WebTestClient kiểm tra đúng CSP header trên route HTML.
3. Tạo trang hiển thị ảnh cùng origin, ảnh CDN và ảnh từ host không được phép. Dùng Console/Network ghi lại kết quả.
4. Đặt một ảnh nền trong stylesheet CDN. Giải thích vì sao ngoài `style-src` vẫn cần `img-src`.
5. Thêm CSS `@font-face` trỏ font CDN. Nếu font bị chặn, phân biệt lỗi `font-src`, CORS và HTTP status.
6. Với ảnh CDN dùng trong canvas, thử đọc pixel không cấu hình CORS, sau đó kiểm tra phương án `crossOrigin="anonymous"` và header CORS của CDN.
7. Tạo preview bằng `URL.createObjectURL(file)` từ file người dùng chọn hợp lệ; trước tiên quan sát CSP với `img-src` không có `blob:`, sau đó mở `blob:` cho chính nhóm ảnh nếu cần.
8. Đổi policy thành `default-src 'self'; img-src https://images.example.net` để kiểm tra ảnh cùng origin có bị chặn không; khôi phục bằng cách thêm `'self'` trực tiếp.
9. Thử trong kích thước màn hình khác nhau với `srcset`/`picture` để phát hiện URL ảnh ngoài allowlist.
10. Bật Report-Only trong một môi trường thử nghiệm; phân loại violation hợp lệ rồi mới bật `Content-Security-Policy` thực thi.
11. So sánh cấu hình Servlet và Reactive/WebFlux, giải thích vì sao CSP cần nằm trên response HTML khi frontend và API tách origin.

**Câu hỏi tự đánh giá:**

1. Khi không khai báo `img-src`/`font-src`, điều gì xảy ra nếu có `default-src 'none'`?
2. Vì sao `default-src 'self'; img-src https://images.example.net` có thể chặn ảnh cùng origin?
3. Một stylesheet được phép bởi `style-src` có tự động cho phép font và ảnh được CSS tham chiếu không?
4. Tại sao font cross-origin có thể bị từ chối dù `font-src` đã cho CDN?
5. Vì sao ảnh từ CDN có thể hiển thị nhưng canvas vẫn không đọc được pixel?
6. Khi nào nên thêm `data:`/`blob:` vào `img-src`, và tại sao không nên tự thêm vào `script-src`?
7. `srcset` hoặc CSS background ảnh hưởng như thế nào đến việc kiểm kê nguồn ảnh?
8. Khi một CDN trả redirect đến hostname khác, bạn cần kiểm tra những gì?
9. Điều gì khác nhau giữa CSP trên API JSON và CSP trên tài liệu HTML?
10. Vì sao mở quá rộng `img-src` có thể làm tăng rủi ro theo dõi hoặc truyền dữ liệu qua URL ảnh?

## 18. Ghi nhớ

**`img-src` kiểm soát các nguồn ảnh; `font-src` kiểm soát nguồn webfont.** Cả hai có fallback từ `default-src` khi không được khai báo, nhưng khi đã xuất hiện, danh sách nguồn của chúng **không tự được cộng thêm** từ `default-src`. Trong hệ thống có tài nguyên bên ngoài, CSS, ảnh và font có thể nằm ở những origin riêng, nên phải cấp phép theo **loại request thực tế**.

Với font CDN, cần kiểm tra thêm CORS từ server font; với ảnh cross-origin sử dụng trong canvas, hiển thị ảnh và quyền đọc pixel là hai vấn đề khác nhau. Chỉ thêm `data:`/`blob:` khi sản phẩm thật sự cần. Trong Spring Security Servlet/WebFlux, ứng dụng đặt CSP trên response HTML được browser sử dụng, kiểm thử trên cả server và trình duyệt, đồng thời phối hợp CSP với xử lý HTML an toàn, CORS, CSRF, HSTS, HTTP firewall và bảo vệ session.
