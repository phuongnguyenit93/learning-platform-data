# Security response header — thiết lập lớp bảo vệ do browser thực thi

> **Chương:** Security headers  
> **Mục tiêu:** Hiểu response security header là gì, browser áp dụng chúng ra sao và cách chọn, triển khai, kiểm tra các header quan trọng như HSTS, nosniff, Referrer-Policy, Permissions-Policy, CSP, frame protection, COOP, COEP, CORP và Cache-Control. Biết cách tránh cấu hình xung đột giữa ứng dụng, reverse proxy và CDN.

## 1. Security response header là gì?

HTTP response header là metadata server gửi cùng response để mô tả nội dung hoặc hướng dẫn browser xử lý response. Một số header có vai trò bảo mật: chúng yêu cầu browser giới hạn cách tải tài nguyên, chia sẻ dữ liệu, mở cửa sổ, nhúng trang hoặc lưu nội dung.

Ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
X-Frame-Options: DENY
```

Browser đọc các header này và áp dụng hành vi tương ứng. Chúng là một lớp bảo vệ ở phía client, bổ sung cho kiểm soát ở server như xác thực, authorization, validation, CSRF protection và xử lý dữ liệu.

Security header không tự sửa lỗ hổng trong ứng dụng. Ví dụ:

- HSTS yêu cầu browser dùng HTTPS sau khi đã nhận policy qua HTTPS.
- CSP giới hạn nguồn và cách thực thi nội dung.
- frame protection giới hạn trang nào được phép nhúng ứng dụng.
- nosniff hạn chế browser tự đoán MIME type trong các ngữ cảnh được quy định.
- Referrer-Policy giảm lượng URL được gửi trong header Referer.

Nếu server vẫn có DOM XSS, kiểm tra quyền sai hoặc endpoint GET thay đổi trạng thái, security header đơn lẻ không loại bỏ những lỗi đó.

## 2. Response header và request header khác nhau

Header bảo mật thường được cấu hình ở response vì server muốn hướng dẫn browser cách xử lý nội dung mà server trả về.

| Loại | Hướng truyền | Ví dụ |
| --- | --- | --- |
| Request header | Browser/client → server | Origin, Referer, Sec-Fetch-Site |
| Response header | Server → browser/client | Content-Security-Policy, Strict-Transport-Security |
| Header hai chiều hoặc có vai trò theo ngữ cảnh | Có thể xuất hiện ở request/response với ý nghĩa khác nhau | Cache-Control |

Không nhầm header request do browser gửi với policy response do server cấu hình. Ví dụ, server có thể kiểm tra request `Origin` để phòng CSRF; còn response `Access-Control-Allow-Origin` là một phần của CORS policy.

Một header có thể được thêm ở nhiều tầng:

1. Ứng dụng/framework.
2. Web server như Nginx hoặc IIS.
3. Reverse proxy hoặc API gateway.
4. CDN/edge.

Browser chỉ thực thi response cuối cùng mà nó nhận được. Vì vậy, cần kiểm tra qua đúng đường truy cập production, bao gồm redirect, error response và cache.

## 3. Nhóm security header thường gặp

| Header | Mục đích chính |
| --- | --- |
| `Strict-Transport-Security` | Ghi nhớ rằng host chỉ nên được truy cập qua HTTPS |
| `X-Content-Type-Options` | Ngăn MIME sniffing trong các ngữ cảnh browser hỗ trợ |
| `Referrer-Policy` | Kiểm soát thông tin URL gửi trong Referer |
| `Permissions-Policy` | Giới hạn việc sử dụng một số browser feature |
| `Content-Security-Policy` | Hạn chế nguồn tài nguyên, script và cách trang được nhúng |
| `X-Frame-Options` | Lớp tương thích cũ để hạn chế framing |
| `Cross-Origin-Opener-Policy` | Kiểm soát quan hệ browsing context với cửa sổ cross-origin |
| `Cross-Origin-Embedder-Policy` | Đặt điều kiện khi document tải tài nguyên cross-origin |
| `Cross-Origin-Resource-Policy` | Cho phép hoặc hạn chế site/origin khác tải tài nguyên |
| `Cache-Control` | Kiểm soát cache, đặc biệt với response nhạy cảm |
| `Set-Cookie` | Thiết lập cookie và thuộc tính bảo vệ cookie phiên |

Không phải header nào cũng cần cùng một giá trị cho mọi route. Trang HTML, API JSON, file tải xuống và tài nguyên tĩnh có nhu cầu khác nhau.

## 4. Strict-Transport-Security (HSTS)

HSTS yêu cầu browser dùng HTTPS khi truy cập lại host đã khai báo. Server gửi:

```http
Strict-Transport-Security: max-age=31536000
```

`max-age` là số giây browser ghi nhớ policy. Trong ví dụ, thời hạn là một năm.

Khi browser đã ghi nhớ HSTS cho host, nó tự nâng cấp những lần truy cập HTTP tiếp theo lên HTTPS trước khi gửi request mạng. Điều này giúp giảm nguy cơ downgrade và một số tình huống SSL stripping.

### Chỉ gửi HSTS qua HTTPS

Browser chỉ chấp nhận HSTS từ response an toàn qua HTTPS (có ngoại lệ đặc biệt cho localhost trong một số triển khai). Header nhận qua HTTP không tạo policy HSTS đáng tin cậy.

HSTS không thay TLS certificate hợp lệ. Server vẫn phải cấu hình HTTPS đúng, gia hạn certificate và chuyển hướng HTTP sang HTTPS cho client chưa có policy.

### includeSubDomains

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

`includeSubDomains` áp dụng policy cho các subdomain của host. Chỉ bật khi **tất cả subdomain cần truy cập đều hỗ trợ HTTPS**. Một subdomain cũ chỉ chạy HTTP có thể không còn truy cập được sau khi browser ghi nhớ policy.

### preload

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

`preload` là tín hiệu liên quan tới chương trình HSTS preload của browser; thêm token này vào header không tự động đưa domain vào danh sách preload. Việc tham gia có điều kiện riêng và gỡ khỏi danh sách có thể mất thời gian phát hành browser. Hãy xem đây là quyết định vận hành dài hạn.

### Lộ trình bật HSTS

1. Đảm bảo mọi route và subdomain cần thiết hoạt động qua HTTPS.
2. Chuyển hướng HTTP sang HTTPS và kiểm tra tài nguyên mixed content.
3. Bắt đầu với max-age ngắn trong staging hoặc giai đoạn đầu production.
4. Theo dõi lỗi truy cập và certificate.
5. Tăng dần max-age khi đã xác nhận ổn định.
6. Chỉ thêm includeSubDomains/preload sau khi rà soát toàn bộ hệ thống tên miền.

## 5. X-Content-Type-Options: nosniff

Server nên khai báo đúng MIME type bằng `Content-Type`. Header:

```http
X-Content-Type-Options: nosniff
```

yêu cầu browser không tự suy đoán MIME type trong các ngữ cảnh được tiêu chuẩn quy định, đặc biệt với script và stylesheet. Điều này giảm nguy cơ một response dữ liệu bị browser diễn giải thành nội dung thực thi do MIME sniffing.

Ví dụ:

```http
Content-Type: application/json; charset=utf-8
X-Content-Type-Options: nosniff
```

Với JavaScript:

```http
Content-Type: text/javascript; charset=utf-8
X-Content-Type-Options: nosniff
```

Đừng trả file JavaScript với MIME type của ảnh hoặc text tùy tiện rồi trông chờ browser đoán đúng. Đảm bảo server, storage và CDN giữ đúng Content-Type của từng tài nguyên.

`nosniff` không thay validation upload, không biến file độc hại thành an toàn và không thay CSP. Nếu ứng dụng cho người dùng upload file, hãy lưu trữ/phục vụ nội dung theo kiến trúc an toàn, cân nhắc origin riêng và Content-Disposition phù hợp.

## 6. Referrer-Policy: giới hạn thông tin Referer

Khi browser điều hướng hoặc tải tài nguyên, nó có thể gửi request header `Referer` cho biết trang nguồn. URL đầy đủ đôi khi chứa query hoặc path nhạy cảm như mã mời, email, từ khóa tìm kiếm hoặc định danh giao dịch.

Response header:

```http
Referrer-Policy: strict-origin-when-cross-origin
```

Các giá trị thường gặp:

| Giá trị | Hành vi khái quát |
| --- | --- |
| `no-referrer` | Không gửi Referer |
| `same-origin` | Chỉ gửi Referer cho request cùng origin |
| `origin` | Chỉ gửi origin, không gửi path/query |
| `strict-origin` | Gửi origin; bỏ khi điều hướng từ HTTPS xuống HTTP |
| `origin-when-cross-origin` | Gửi URL đầy đủ cùng origin, chỉ origin khi cross-origin |
| `strict-origin-when-cross-origin` | URL đầy đủ cùng origin; chỉ origin khi cross-origin; bỏ khi downgrade HTTPS → HTTP |
| `no-referrer-when-downgrade` | Giá trị cũ; có thể gửi URL đầy đủ cross-origin nếu không downgrade |
| `unsafe-url` | Có thể gửi URL đầy đủ kể cả cross-origin; tránh dùng nếu không có lý do rõ ràng |

Các browser hiện đại thường mặc định `strict-origin-when-cross-origin`, nhưng ứng dụng nên đặt policy rõ ràng để tránh phụ thuộc default hoặc thay đổi theo môi trường.

Referrer-Policy không phải CSRF protection. Không dùng Referer làm bằng chứng xác thực; nếu cần kiểm tra nguồn request thay đổi trạng thái, server phải áp dụng quy tắc Origin/Referer cùng CSRF token và authorization.

### Meta và thuộc tính theo từng liên kết

Có thể khai báo policy ở cấp document bằng response header, meta element hoặc một số thuộc tính trên liên kết/tài nguyên. Response header là lựa chọn rõ ràng và dễ quản lý nhất:

```html
<meta name="referrer" content="strict-origin-when-cross-origin">
<a href="https://external.example" rel="noreferrer">Mở trang ngoài</a>
```

`rel="noreferrer"` có thể ngăn gửi referrer cho liên kết đó và thường cũng hàm ý noopener. Hãy chọn theo yêu cầu privacy và chức năng.

## 7. Permissions-Policy: giới hạn browser features

Permissions-Policy cho phép server giới hạn việc document và nội dung được nhúng sử dụng một số tính năng của browser, ví dụ camera, microphone, geolocation hoặc fullscreen.

Ví dụ khóa một số feature:

```http
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

Ví dụ chỉ cho phép chính origin:

```http
Permissions-Policy: camera=(self), microphone=(self), geolocation=(self)
```

Một ứng dụng chỉ cần fullscreen có thể cấu hình riêng feature đó thay vì mở rộng toàn bộ quyền.

| Directive ví dụ | Tác dụng mong muốn |
| --- | --- |
| `camera=()` | Không cho document nào trong policy dùng camera |
| `microphone=()` | Không cho dùng microphone |
| `geolocation=()` | Không cho dùng geolocation |
| `fullscreen=(self)` | Giới hạn fullscreen cho cùng origin |
| `payment=()` | Tắt Payment Request API trong phạm vi policy hỗ trợ |

Permissions-Policy không tự cấp quyền cho camera hoặc microphone. Browser vẫn có permission prompt, secure context requirement và các điều kiện khác. Policy chỉ giới hạn thêm khả năng sử dụng feature.

### iframe và quyền được delegate

Trang cha có thể giới hạn feature qua header, đồng thời iframe có thể cần thuộc tính `allow`:

```html
<iframe
  src="https://video.partner.example/"
  allow="fullscreen"
  title="Video"
></iframe>
```

Quyền cuối cùng phụ thuộc policy của trang cha, policy của tài liệu con, thuộc tính allow và browser permission. Không thêm feature vào allowlist nếu widget không cần.

Tên directive và mức hỗ trợ có thể thay đổi theo browser. Hãy kiểm tra danh sách feature mà sản phẩm thực sự dùng và thử trên browser mục tiêu; không sao chép một danh sách quyền rộng cho mọi route.

## 8. Content-Security-Policy: kiểm soát tài nguyên và hành vi trang

CSP là một trong những security response header quan trọng nhất. Nó cho browser biết nguồn nào được phép tải và thực thi script, style, ảnh, font, frame, kết nối mạng và nhiều loại tài nguyên khác.

Ví dụ khởi đầu:

```http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
```

Một số directive quan trọng:

| Directive | Phạm vi |
| --- | --- |
| `default-src` | Fallback cho nhiều loại tài nguyên |
| `script-src` | Script và nguồn thực thi JavaScript |
| `style-src` | Stylesheet và một số inline style context |
| `img-src` | Hình ảnh |
| `connect-src` | Fetch, XHR, WebSocket và kết nối tương ứng |
| `font-src` | Font |
| `frame-src` | Frame mà trang hiện tại được phép tải |
| `frame-ancestors` | Origin được phép nhúng trang hiện tại |
| `object-src` | Plugin/object; thường đặt `'none'` |
| `base-uri` | URL base element được phép |
| `form-action` | Đích submit form |

Policy thực tế phải được xây dựng theo tài nguyên của ứng dụng. Tránh thêm `'unsafe-inline'`, `'unsafe-eval'` hoặc wildcard chỉ để loại bỏ lỗi console. Với script, ưu tiên nonce/hash và cân nhắc `strict-dynamic` khi loader đã được kiểm soát.

### frame-ancestors và clickjacking

Nếu trang không cần được nhúng:

```http
Content-Security-Policy: frame-ancestors 'none'
```

Nếu chỉ cho phép cùng origin:

```http
Content-Security-Policy: frame-ancestors 'self'
```

`frame-ancestors` kiểm soát toàn bộ chuỗi ancestor và phải được gửi bằng HTTP response header; nó không fallback từ `default-src` và không có hiệu lực qua meta CSP. Đây là directive quan trọng để phòng clickjacking.

## 9. X-Frame-Options: tương thích framing cũ

`X-Frame-Options` (XFO) là header cũ dùng để hạn chế việc trang được nhúng:

```http
X-Frame-Options: DENY
```

Các giá trị thường gặp:

- `DENY`: không cho hiển thị trang trong frame.
- `SAMEORIGIN`: chỉ cho phép frame cùng origin.

`ALLOW-FROM` đã lỗi thời và không được browser hiện đại hỗ trợ nhất quán. Nếu cần allowlist đối tác khác origin, dùng CSP `frame-ancestors`.

Trong browser hiện đại hỗ trợ `frame-ancestors`, CSP directive này được ưu tiên hơn XFO. XFO có thể giữ lại để hỗ trợ browser cũ; hãy chọn giá trị tương thích với yêu cầu nhúng thực tế.

Không nhầm `frame-ancestors` với `frame-src`: một cái kiểm soát ai được nhúng trang của bạn, cái kia kiểm soát trang của bạn được tải frame từ đâu.

## 10. COOP: Cross-Origin-Opener-Policy

COOP kiểm soát việc một document có chia sẻ browsing context group với cửa sổ mở nó hoặc cửa sổ nó mở hay không. Nó giúp cô lập quan hệ opener giữa các site và giảm một số rủi ro liên quan tới cross-origin window references.

Ví dụ:

```http
Cross-Origin-Opener-Policy: same-origin
```

Các giá trị thường gặp:

| Giá trị | Ý nghĩa khái quát |
| --- | --- |
| `unsafe-none` | Hành vi mặc định tương thích rộng |
| `same-origin` | Chỉ giữ browsing context group với document cùng origin theo quy tắc COOP |
| `same-origin-allow-popups` | Cho phép một số popup có COOP mặc định cùng nhóm trong khi cô lập các quan hệ khác |
| `noopener-allow-popups` | Cô lập opener nhưng vẫn cho phép một số popup được giữ quan hệ theo quy tắc riêng |

COOP có thể làm `window.opener` ở một phía trở thành null hoặc làm các cửa sổ nằm trong browsing context group khác nhau. Điều này có thể ảnh hưởng luồng đăng nhập popup, thanh toán, OAuth/OIDC và tích hợp legacy dựa trên opener.

Không bật `same-origin` trên toàn bộ ứng dụng mà chưa thử các luồng popup. Chọn policy theo kiến trúc và xác minh browser hỗ trợ.

## 11. COEP: Cross-Origin-Embedder-Policy

COEP kiểm soát điều kiện khi document tải tài nguyên cross-origin. Một giá trị thường gặp:

```http
Cross-Origin-Embedder-Policy: require-corp
```

Với `require-corp`, tài nguyên cross-origin được tải theo các mode liên quan cần có CORS hoặc CORP phù hợp. Điều này giúp ứng dụng đạt trạng thái cross-origin isolated khi kết hợp đúng với COOP và các điều kiện khác.

Một giá trị khác:

```http
Cross-Origin-Embedder-Policy: credentialless
```

`credentialless` cho phép một số request no-CORS cross-origin được tải mà không gửi credentials, theo quy tắc browser hỗ trợ. Đây không phải cách bỏ qua kiểm soát nguồn; tài nguyên và browser compatibility vẫn cần được kiểm thử.

COEP có thể làm hỏng tài nguyên bên thứ ba nếu CDN/image/font/script không trả CORS hoặc CORP phù hợp. Trước khi bật enforcement, kiểm kê toàn bộ tài nguyên cross-origin.

## 12. CORP: Cross-Origin-Resource-Policy

CORP được server của **tài nguyên** dùng để giới hạn site/origin nào có thể tải tài nguyên trong một số ngữ cảnh cross-origin no-CORS:

```http
Cross-Origin-Resource-Policy: same-origin
```

Các giá trị:

| Giá trị | Ý nghĩa |
| --- | --- |
| `same-origin` | Chỉ cho phép cùng origin tải trong phạm vi CORP |
| `same-site` | Cho phép cùng site |
| `cross-origin` | Cho phép cross-origin |

Ví dụ, một endpoint trả dữ liệu riêng tư hoặc tài nguyên nội bộ có thể dùng CORP same-origin nếu không cần được nhúng/tải từ site khác.

CORP không phải CORS:

- CORS cho phép JavaScript cross-origin đọc response khi server cho phép.
- CORP chủ yếu kiểm soát việc tài nguyên được nhúng/tải trong các ngữ cảnh no-CORS.
- CORP không cấp quyền đọc response cho JavaScript cross-origin.

Đặt CORP quá chặt có thể làm ảnh, font hoặc tài nguyên hợp lệ bị chặn. Chọn policy theo mục đích của từng loại tài nguyên.

## 13. COOP, COEP và cross-origin isolation

Một số API nhạy cảm về hiệu năng hoặc timing, ví dụ SharedArrayBuffer trong browser hiện đại, yêu cầu document ở trạng thái cross-origin isolated. Thông thường, cần kết hợp:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

Khi cấu hình đúng và browser hỗ trợ, document có thể thỏa điều kiện cross-origin isolation. Kiểm tra trạng thái trong browser:

```js
console.log(window.crossOriginIsolated);
```

Giá trị `true` cho biết document đang ở trạng thái cross-origin isolated theo browser; `false` nghĩa là điều kiện chưa thỏa hoặc browser không hỗ trợ trong ngữ cảnh đó.

Việc bật COEP thường yêu cầu kiểm tra mọi script, worker, font, ảnh, iframe và tài nguyên bên thứ ba. Đừng chỉ thêm hai header rồi giả định ứng dụng đã được cô lập; hãy kiểm tra response của từng tài nguyên và lỗi Console.

## 14. Cache-Control: tránh lưu nội dung nhạy cảm ngoài ý muốn

Cache-Control điều khiển cách browser và shared cache lưu response. Với nội dung tài khoản, dữ liệu cá nhân hoặc response chứa thông tin nhạy cảm, thường cần policy rõ ràng:

```http
Cache-Control: no-store
```

Phân biệt:

| Directive | Ý nghĩa |
| --- | --- |
| `no-store` | Cache không được lưu response |
| `no-cache` | Có thể lưu nhưng phải revalidate trước khi dùng lại |
| `private` | Chỉ private cache của user agent được lưu; shared cache không được lưu |
| `public` | Cho phép shared cache lưu nếu các điều kiện khác thỏa |
| `max-age=N` | Freshness lifetime tính bằng giây |
| `s-maxage=N` | Freshness lifetime dành cho shared cache |

Ví dụ response có dữ liệu tài khoản:

```http
Cache-Control: private, no-store
```

`no-store` thường phù hợp khi không muốn browser hoặc shared cache lưu response. `no-cache` không có nghĩa “không lưu”; nó yêu cầu kiểm tra lại trước khi dùng bản lưu. Không dùng các directive này thay authorization hoặc xóa dữ liệu đã được ứng dụng lưu ở nơi khác.

Với nội dung tĩnh có version/hash trong filename, cache dài hạn có thể phù hợp:

```http
Cache-Control: public, max-age=31536000, immutable
```

Chỉ dùng khi URL thay đổi khi nội dung thay đổi. Không cache dài hạn HTML động hoặc dữ liệu riêng tư như tài nguyên công khai bất biến.

## 15. Set-Cookie và thuộc tính bảo vệ phiên

`Set-Cookie` là response header quan trọng với ứng dụng dùng session cookie:

```http
Set-Cookie: __Host-session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

| Thuộc tính | Vai trò |
| --- | --- |
| `Secure` | Browser chỉ gửi cookie qua kết nối an toàn |
| `HttpOnly` | JavaScript không đọc cookie qua document.cookie |
| `SameSite` | Hạn chế gửi cookie trong một số ngữ cảnh cross-site |
| `Path` | Giới hạn path mà browser gửi cookie |
| `Domain` | Mở rộng cookie tới domain/subdomain được chỉ định; tránh nếu không cần |
| `Max-Age` / `Expires` | Điều khiển thời hạn cookie |
| `__Host-` prefix | Yêu cầu Secure, Path=/ và không có Domain trong browser hỗ trợ |

Không đặt nhiều cookie trong một header bằng cách nối dấu phẩy tùy tiện. Mỗi cookie nên được phát bằng một Set-Cookie header riêng; dấu phẩy còn có ý nghĩa bên trong thuộc tính Expires.

Cookie flags không thay thế session rotation, server-side revocation, CSRF token hoặc authorization.

## 16. CORS không phải một response security header đơn lẻ

CORS được cấu hình bằng một nhóm response header, ví dụ:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Những header này điều khiển browser có cho JavaScript từ origin khác đọc response hay không. CORS không thay thế CSP, SOP, CSRF protection hoặc postMessage origin validation.

Tránh cấu hình:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Browser không cho phép wildcard origin kết hợp với credentials trong CORS response theo cách này. Với credentialed request, server cần trả origin cụ thể đã được xác minh và thường cần `Vary: Origin` nếu response thay đổi theo Origin.

Không phản chiếu tùy tiện mọi request Origin vào Access-Control-Allow-Origin. Hãy dùng allowlist chính xác và kiểm tra cả preflight request.

## 17. Header cũ và header không còn nên dựa vào

Một số header từng được dùng nhưng đã lỗi thời, bị thay thế hoặc không nên xem là biện pháp bảo vệ chính:

| Header | Tình trạng và hướng xử lý |
| --- | --- |
| `X-XSS-Protection` | Bộ lọc XSS cũ của browser; không đáng tin cậy và đã bị loại bỏ/không còn được khuyến nghị. Không dùng thay CSP và output encoding. |
| `Public-Key-Pins` (HPKP) | Đã bị loại bỏ do rủi ro khóa nhầm domain; không triển khai mới. |
| `Expect-CT` | Không còn cần cho các browser hiện đại; không dùng làm kiểm soát Certificate Transparency chính. |
| `X-Frame-Options: ALLOW-FROM` | Lỗi thời và hỗ trợ không nhất quán; dùng CSP frame-ancestors. |
| `X-Permitted-Cross-Domain-Policies` | Header legacy cho Flash/PDF plugin; chỉ đánh giá nếu hệ thống thật sự còn phụ thuộc client legacy. |
| `X-Download-Options` | Header legacy chủ yếu cho Internet Explorer; không thay Content-Disposition và xử lý download hiện đại. |

`Server` hoặc `X-Powered-By` có thể tiết lộ thông tin công nghệ. Ẩn chúng giảm một phần fingerprinting nhưng không thay patching, cấu hình an toàn và quản lý dependency.

## 18. Thiết kế header theo loại response

Không nên áp một bộ header giống hệt nhau cho mọi loại response. Hãy phân loại:

| Response | Các kiểm soát thường cần xem xét |
| --- | --- |
| Trang đăng nhập/tài khoản | HSTS, CSP, frame-ancestors, Referrer-Policy, nosniff, Cache-Control, cookie flags |
| Trang HTML công khai | HSTS, CSP, frame policy theo nhu cầu, Referrer-Policy, nosniff |
| API JSON | Content-Type đúng, nosniff, CORS nếu cần, Cache-Control theo độ nhạy, CORP nếu phù hợp |
| JavaScript/CSS tĩnh | MIME type đúng, nosniff, cache theo version, CORS/SRI nếu cross-origin |
| Ảnh/font/video | Content-Type đúng, cache policy, CORP/CORS theo cách nhúng |
| File download | Content-Disposition phù hợp, MIME type đúng, nosniff và cache policy |
| Trang widget cần nhúng | frame-ancestors allowlist cụ thể, CSP và giao thức postMessage rõ ràng |

Ví dụ, `frame-ancestors` chỉ có ý nghĩa với tài liệu có thể được nhúng; áp vào JSON API không tạo ra chính sách clickjacking cho trang HTML khác. Ngược lại, CORS trên API không thay framing protection của trang đăng nhập.

## 19. Triển khai qua ứng dụng, reverse proxy và CDN

Một response có thể đi qua nhiều tầng. Nếu ứng dụng gửi CSP nhưng CDN thêm một CSP khác, browser áp dụng nhiều policy enforcement đồng thời. Nếu reverse proxy ghi đè header, policy cuối có thể khác cấu hình trong source code.

Nguyên tắc:

- Chọn một nơi làm nguồn cấu hình chuẩn cho từng nhóm header.
- Nếu cần chia trách nhiệm, quy định rõ tầng nào được thêm, sửa hoặc xóa header.
- Không phát hai giá trị xung đột cho HSTS, Referrer-Policy, Permissions-Policy hoặc các header đơn trị nếu không hiểu hành vi browser.
- Với nhiều CSP enforcement policy, hiểu rằng chúng cùng được áp dụng; policy rộng hơn không mở lại quyền đã bị policy khác chặn.
- Kiểm tra response 200, redirect, 401/403, 404/500 và response từ CDN/cache.
- Đảm bảo header có mặt trên mọi route nhạy cảm, không chỉ trang chủ.
- Kiểm tra header trên HTTP và HTTPS; HSTS chỉ được chấp nhận từ response an toàn.

### Ví dụ Express

Ví dụ minh họa cách thêm một số header ở middleware:

```js
app.use((req, res, next) => {
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.setHeader("Referrer-Policy", "strict-origin-when-cross-origin");
  res.setHeader("X-Frame-Options", "DENY");
  res.setHeader(
    "Content-Security-Policy",
    "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
  );

  // Chỉ bật HSTS khi request thực sự được phục vụ qua HTTPS
  // hoặc proxy HTTPS được cấu hình trust đúng cách.
  if (req.secure) {
    res.setHeader(
      "Strict-Transport-Security",
      "max-age=31536000"
    );
  }
  next();
});
```

Đây là ví dụ tối giản, không thay thế cấu hình theo route và phiên bản framework. Khi chạy sau reverse proxy, `req.secure` chỉ đáng tin nếu trust proxy được cấu hình đúng; nếu không, HSTS có thể không được thêm hoặc có thể được thêm sai. Ứng dụng thực nên dùng thư viện middleware được duy trì và cấu hình CSP tập trung.

### Ví dụ Nginx

```nginx
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header X-Frame-Options "DENY" always;
add_header Strict-Transport-Security "max-age=31536000" always;
```

Chỉ đặt HSTS ở server block HTTPS. Với Nginx, quy tắc kế thừa `add_header` phụ thuộc context và có thể thay đổi khi location con tự khai báo add_header; kiểm tra cấu hình thực tế để tránh mất header ở một số route. Nếu CSP được quản lý ở upstream, không thêm một policy khác ngoài dự kiến.

## 20. Rollout an toàn: quan sát, kiểm thử, enforcement

Không bật mọi header với giá trị nghiêm ngặt nhất trong production mà chưa hiểu luồng ứng dụng. Một số header có thể làm hỏng đăng nhập popup, tài nguyên CDN, widget đối tác hoặc subdomain cũ.

Lộ trình:

1. **Kiểm kê:** xác định loại response, nguồn tài nguyên, subdomain, popup, iframe và dữ liệu nhạy cảm.
2. **Định nghĩa policy:** chọn giá trị tối thiểu cần thiết cho từng route/response.
3. **Staging:** bật header trong môi trường gần production và kiểm tra luồng chính.
4. **Report-Only:** dùng CSP Report-Only khi đánh giá CSP; ghi nhận vi phạm và phân loại.
5. **Canary:** triển khai theo nhóm nhỏ hoặc route ít rủi ro trước.
6. **Theo dõi:** quan sát lỗi browser, đăng nhập, payment, analytics, widget và cache.
7. **Enforcement:** chuyển policy sang chế độ thực thi sau khi xử lý dependency hợp lệ.
8. **Duy trì:** rà soát khi thêm subdomain, CDN, script, iframe, feature browser hoặc nhà cung cấp mới.

Đối với HSTS, tăng max-age theo giai đoạn và chỉ bật includeSubDomains/preload sau khi kiểm kê đầy đủ. Với COEP/COOP, kiểm tra popup và mọi tài nguyên cross-origin. Với Permissions-Policy, xác minh tính năng mà iframe thực sự cần.

## 21. Kiểm tra security header bằng DevTools

Thực hiện trên ứng dụng lab hoặc staging mà bạn có quyền kiểm tra.

### Bước 1 — Xem response cuối

1. Mở DevTools → Network.
2. Tải lại trang với cache được kiểm soát.
3. Chọn document response chính.
4. Xem mục Response Headers.
5. Ghi nhận header, giá trị, số lần xuất hiện và nguồn response nếu browser hiển thị.

Kiểm tra cả redirect và response cuối; header của redirect không tự động thay thế policy trên document cuối.

### Bước 2 — Kiểm tra theo chức năng

- **HSTS:** truy cập HTTPS, xác minh header và thử điều hướng HTTP trong profile lab sau khi browser đã ghi policy.
- **nosniff:** kiểm tra Content-Type của script, stylesheet và API response.
- **Referrer-Policy:** điều hướng từ trang lab sang origin lab khác và quan sát request Referer.
- **Permissions-Policy:** thử feature đã bị tắt và kiểm tra Console/permission behavior.
- **CSP/frame-ancestors:** thử nhúng trang từ origin không được phép.
- **COOP/COEP/CORP:** xem Console và lỗi tải tài nguyên cross-origin; kiểm tra `window.crossOriginIsolated` khi cần.
- **Cache-Control:** kiểm tra response có dữ liệu nhạy cảm và hành vi cache/revalidation.
- **Set-Cookie:** kiểm tra Secure, HttpOnly, SameSite, Domain và Path trong Application/Storage.

### Bước 3 — Kiểm tra nhiều route và tầng mạng

Lặp lại cho:

- Trang login và account.
- Trang settings và thao tác nhạy cảm.
- API JSON.
- File tĩnh và upload/download.
- Trang lỗi 401/403/404/500.
- Response qua CDN/reverse proxy và cache hit.

Một header đúng ở trang chủ không chứng minh mọi response của ứng dụng đều được bảo vệ.

## 22. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Browser vẫn tải HTTP sau khi bật HSTS | Header chỉ được gửi qua HTTP, chưa có HTTPS policy hoặc max-age bằng 0 | Xác minh HTTPS response và thời hạn HSTS |
| Subdomain không truy cập được sau HSTS | includeSubDomains bật khi subdomain chưa có HTTPS | Khôi phục HTTPS cho subdomain; rà soát trước khi bật includeSubDomains |
| Script/stylesheet bị chặn do nosniff | Content-Type sai hoặc server trả MIME không phù hợp | Sửa MIME type tại app/storage/CDN |
| Referer không như mong đợi | Referrer-Policy ở document, link hoặc browser context khác | Kiểm tra response header và policy theo element |
| Camera/microphone không hoạt động trong iframe | Permissions-Policy hoặc iframe allow không cấp feature | Xác định feature cần thiết và delegate đúng phạm vi |
| Trang bị chặn trong iframe | frame-ancestors hoặc XFO không cho origin nhúng | Kiểm tra toàn bộ ancestor và allowlist |
| Popup OAuth mất opener | COOP/noopener làm tách browsing context | Thiết kế lại callback theo giao thức chuẩn, không hạ policy tùy tiện |
| Ảnh/font/script cross-origin bị chặn | COEP/CORP/CORS không tương thích | Kiểm tra response của từng tài nguyên và chọn policy phù hợp |
| API bị cache sai người dùng | Cache-Control chưa phù hợp hoặc CDN bỏ qua variation | Đặt private/no-store phù hợp và kiểm tra cache key |
| Header biến mất ở một số route | Middleware không chạy hoặc proxy/location ghi đè | Kiểm tra response thực tế từng route |
| Hai CSP header gây chặn bất ngờ | Nhiều enforcement policy cùng được áp dụng | Hợp nhất cấu hình và kiểm tra mọi CSP header |

## 23. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Có security header là ứng dụng không còn XSS.” | Header giảm một số tác động; source-to-sink, output encoding và safe DOM vẫn cần thiết. |
| “HSTS thay certificate TLS.” | HSTS chỉ hướng browser dùng HTTPS; certificate và TLS server vẫn phải hợp lệ. |
| “nosniff làm mọi file upload an toàn.” | Nó hạn chế MIME sniffing; upload vẫn cần validation, isolation và Content-Disposition phù hợp. |
| “Referrer-Policy là CSRF protection.” | Nó điều khiển Referer; CSRF cần token, origin checks và authorization. |
| “Permissions-Policy cấp quyền camera.” | Nó giới hạn feature; browser permission và secure context vẫn áp dụng. |
| “frame-src chặn website khác nhúng trang mình.” | frame-src kiểm soát frame trang mình tải; frame-ancestors kiểm soát ai nhúng mình. |
| “CORS cho phép server truy cập dữ liệu browser.” | CORS kiểm soát việc script cross-origin đọc response; không thay SOP/CSRF hoặc server authorization. |
| “COEP chỉ cần bật một header.” | Tài nguyên cross-origin phải đáp ứng CORS/CORP và browser support. |
| “no-cache nghĩa là không lưu.” | no-cache cho phép lưu nhưng yêu cầu revalidate; no-store mới cấm lưu response. |
| “Thêm header ở một tầng là browser chắc chắn nhận được.” | CDN/proxy/framework có thể ghi đè, bỏ hoặc nhân đôi header. |

## 24. Checklist security response header

- Xác định response nào là HTML, API, static asset, upload/download và dữ liệu riêng tư.
- Gửi HSTS qua HTTPS; chỉ bật includeSubDomains/preload sau khi rà soát toàn bộ subdomain.
- Đặt Content-Type chính xác và X-Content-Type-Options: nosniff.
- Chọn Referrer-Policy phù hợp; tránh unsafe-url nếu không có lý do.
- Giới hạn Permissions-Policy theo feature thực sự cần.
- Xây dựng CSP theo tài nguyên thực tế; ưu tiên nonce/hash cho script và dùng frame-ancestors chống clickjacking.
- Dùng X-Frame-Options như lớp tương thích legacy khi phù hợp.
- Đánh giá COOP/COEP/CORP cùng popup, iframe và tài nguyên cross-origin.
- Đặt Cache-Control phù hợp cho response nhạy cảm và tài nguyên versioned.
- Bảo vệ session cookie bằng Secure, HttpOnly, SameSite và scope phù hợp.
- Cấu hình CORS bằng allowlist origin; không phản chiếu Origin tùy tiện.
- Loại bỏ phụ thuộc vào header lỗi thời như X-XSS-Protection, HPKP và XFO ALLOW-FROM.
- Xác định một nguồn cấu hình header chuẩn; tránh header trùng/xung đột.
- Kiểm tra response cuối trên mọi route, status code, redirect, CDN và cache.
- Rollout qua staging/Report-Only/canary, theo dõi lỗi và duy trì khi kiến trúc thay đổi.

## 25. Câu hỏi tự kiểm tra

1. Security response header khác request header ở điểm nào?
2. Vì sao HSTS chỉ được browser chấp nhận từ HTTPS response?
3. includeSubDomains có thể gây sự cố gì nếu còn subdomain chỉ hỗ trợ HTTP?
4. X-Content-Type-Options: nosniff giảm rủi ro nào và không giải quyết rủi ro nào?
5. strict-origin-when-cross-origin gửi thông tin Referer ra sao?
6. Permissions-Policy khác browser permission prompt như thế nào?
7. frame-ancestors khác frame-src ở hướng kiểm soát nào?
8. COOP, COEP và CORP giải quyết các ranh giới cross-origin khác nhau ra sao?
9. no-store khác no-cache như thế nào?
10. Vì sao phải kiểm tra header ở response cuối sau CDN/reverse proxy?
11. CORS response header có thay thế CSRF protection không?
12. Vì sao cần rollout và kiểm thử theo từng loại response?

**Ghi nhớ:** Security response header là chỉ thị server gửi để browser thực thi các lớp bảo vệ cho document, tài nguyên, cookie và cache. Hãy chọn header theo loại response và threat model: HSTS cho HTTPS, nosniff cho MIME, Referrer-Policy cho privacy, Permissions-Policy cho browser features, CSP/frame protection cho nội dung và framing, COOP/COEP/CORP cho ranh giới cross-origin, Cache-Control cho dữ liệu nhạy cảm. Kiểm tra response cuối qua mọi tầng mạng và kết hợp các header với kiểm soát bảo mật ở server.
