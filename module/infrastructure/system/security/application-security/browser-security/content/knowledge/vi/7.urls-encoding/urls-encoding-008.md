# URL leakage: dữ liệu nhạy cảm có thể rò rỉ qua địa chỉ web như thế nào?

URL thường được xem là một chuỗi dùng để định vị tài nguyên. Trong thực tế, URL còn đi qua nhiều thành phần: thanh địa chỉ, lịch sử trình duyệt, header HTTP, reverse proxy, máy chủ ứng dụng, hệ thống ghi log, công cụ phân tích và đôi khi cả website bên thứ ba. Nếu đưa mật khẩu, mã phiên, access token hoặc thông tin cá nhân vào URL, dữ liệu đó có thể xuất hiện ở những nơi mà nhà phát triển không dự định.

**URL leakage** (rò rỉ dữ liệu qua URL) là tình huống thông tin nhạy cảm bị lộ do được đặt trong URL hoặc bị tiết lộ trong quá trình điều hướng, tải tài nguyên, ghi log và chia sẻ liên kết. HTTPS bảo vệ dữ liệu trên đường truyền, nhưng không xóa URL khỏi lịch sử trình duyệt, log ở điểm cuối hay hệ thống quan sát của chính ứng dụng.

Bài học thuộc chương **URL và encoding**, trong phạm vi `SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`: phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web; hiểu SOP, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế. Trọng tâm ở đây là nhận diện nơi URL có thể bị lộ, hiểu chính xác phần nào được gửi qua HTTP, và thiết kế cách xử lý dữ liệu an toàn.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt các thành phần URL: scheme, authority, hostname, port, path, query và fragment.
2. Giải thích phần nào được gửi đến máy chủ trong request và phần nào chỉ được xử lý ở trình duyệt.
3. Nhận diện các kênh rò rỉ phổ biến: `Referer`, browser history, access log, analytics, redirect, third-party resource và copy/paste.
4. Hiểu vì sao percent-encoding hoặc Base64 không mã hóa bí mật.
5. Chọn `Referrer-Policy`, `Cache-Control`, cookie và cách ghi log phù hợp.
6. Xử lý an toàn các luồng reset password, đăng nhập OAuth/OIDC và URL có tham số nhạy cảm.
7. Kiểm chứng URL leakage bằng DevTools, header HTTP và log của môi trường thử nghiệm.

## 2. Cấu trúc URL và ranh giới dữ liệu

Một URL HTTP(S) có thể có dạng:

```text
https://user:password@app.example.com:8443/orders/42?view=full&token=demo#details
└─┬─┘   └──────┬──────┘ └──────┬──────┘ └┬─┘ └───────┬───────┘ └──┬──┘ └───┬──┘
scheme       userinfo        hostname   port        path          query  fragment
```

Trong ứng dụng hiện đại, không nên dùng `userinfo` để truyền thông tin đăng nhập. Ví dụ trên cố ý chứa `token=demo` để minh họa vị trí dữ liệu nhạy cảm có thể bị ghi lại.

| Thành phần | Ví dụ | Vai trò và khả năng lộ |
| --- | --- | --- |
| Scheme | `https` | Chỉ định giao thức. HTTPS mã hóa nội dung HTTP trên đường truyền tới điểm kết thúc TLS. |
| Userinfo | `user:password@` | Cú pháp URL cũ; không dùng để truyền username/password. Có thể bị ghi lại hoặc xử lý không nhất quán. |
| Hostname | `app.example.com` | Xác định máy chủ đích; hostname thường có thể được quan sát bởi hạ tầng mạng, DNS và điểm kết thúc kết nối. |
| Port | `8443` | Xác định cổng kết nối. |
| Path | `/orders/42` | Được gửi trong request target đến máy chủ; thường xuất hiện trong access log, tracing và analytics. |
| Query | `?view=full&token=demo` | Được gửi trong request target; thường bị ghi lại cùng URL. Đây là vị trí rủi ro cao nếu chứa bí mật. |
| Fragment | `#details` | Không được gửi trong HTTP request; được trình duyệt và JavaScript phía trang xử lý. Vẫn có thể xuất hiện trong history, clipboard và mã client. |

### Phần nào thực sự đi qua HTTP?

Khi trình duyệt tải:

```text
https://app.example.com/orders/42?view=full&token=demo#details
```

request HTTP tương ứng về cơ bản chứa path và query:

```http
GET /orders/42?view=full&token=demo HTTP/1.1
Host: app.example.com
```

Fragment `#details` **không được gửi đến máy chủ trong request target thông thường**. Máy chủ không nhận fragment qua request HTTP. Trình duyệt có thể dùng fragment để cuộn đến phần tử hoặc cung cấp trạng thái cho ứng dụng client-side.

Tuy nhiên, “không gửi trong HTTP request” không đồng nghĩa “bí mật an toàn”. Fragment vẫn có thể được đọc bằng `location.hash`, lưu trong browser history, được copy vào clipboard hoặc bị JavaScript bên thứ ba đang chạy trên trang đọc. Không đặt access token, session ID hoặc dữ liệu xác thực nhạy cảm vào fragment.

### HTTPS bảo vệ điều gì?

HTTPS mã hóa path, query, header và body HTTP khi truyền giữa trình duyệt với điểm kết thúc TLS. Người quan sát thụ động trên mạng thông thường không đọc được path/query như khi dùng HTTP thuần. Nhưng dữ liệu URL vẫn hiển thị hoặc được xử lý tại:

- Trình duyệt của người dùng: thanh địa chỉ, history, bookmark, đồng bộ history và extension có quyền phù hợp.
- Máy chủ đích và các điểm kết thúc TLS: reverse proxy, CDN, WAF, load balancer, service mesh hoặc gateway.
- Ứng dụng và hệ thống vận hành: access log, error log, APM, tracing, analytics và báo cáo lỗi.
- Những nơi người dùng hoặc ứng dụng chủ động chia sẻ URL: email, chat, ticket, ảnh chụp màn hình và clipboard.

Vì vậy, **HTTPS là yêu cầu bắt buộc để bảo vệ đường truyền, nhưng không phải biện pháp chống URL leakage hoàn chỉnh**. Không thể kết luận URL an toàn chỉ vì nó bắt đầu bằng `https://`.

## 3. Các kênh rò rỉ URL phổ biến

### 3.1. Header `Referer`

Khi trình duyệt điều hướng hoặc tải tài nguyên, nó có thể gửi header `Referer` để cho máy chủ đích biết trang nguồn. Ví dụ người dùng đang ở:

```text
https://app.example.com/reset/confirm?email=user%40example.com&token=RESET-DEMO
```

và trang đó tải ảnh từ:

```html
<img src="https://images.partner.example/banner.png" alt="Banner">
```

Nếu chính sách referrer cho phép gửi đầy đủ URL trong ngữ cảnh đó, máy chủ ảnh bên ngoài có thể nhận được URL trang nguồn qua header `Referer`. Như vậy, email và reset token trong query có thể bị tiết lộ dù request ảnh không chứa các giá trị đó trong URL đích.

`Referer` có cách viết lịch sử thiếu chữ “r” thứ hai; tên header chuẩn là `Referer`. Chính sách `Referrer-Policy` quy định lượng thông tin được gửi:

| Chính sách | Cùng origin | Cross-origin | HTTPS xuống HTTP |
| --- | --- | --- | --- |
| `no-referrer` | Không gửi | Không gửi | Không gửi |
| `same-origin` | Gửi URL nguồn | Không gửi | Không gửi |
| `origin` | Chỉ gửi origin | Chỉ gửi origin | Chỉ gửi origin; cần lưu ý không tự ngăn mọi downgrade |
| `strict-origin` | Chỉ gửi origin | Chỉ gửi origin | Không gửi khi hạ cấp HTTPS xuống HTTP |
| `origin-when-cross-origin` | Gửi URL đầy đủ | Chỉ gửi origin | Theo quy tắc origin; không phải lựa chọn nghiêm ngặt nhất cho downgrade |
| `strict-origin-when-cross-origin` | Gửi URL đầy đủ | Chỉ gửi origin | Không gửi |
| `unsafe-url` | Gửi URL đầy đủ | Gửi URL đầy đủ | Có thể gửi URL đầy đủ; không dùng cho trang nhạy cảm |

`strict-origin-when-cross-origin` là mặc định phổ biến của trình duyệt hiện đại, nhưng ứng dụng nên khai báo chính sách rõ ràng. Với trang chứa dữ liệu nhạy cảm, có thể dùng `no-referrer` để tránh gửi thông tin trang nguồn cho mọi đích:

```http
Referrer-Policy: no-referrer
```

Nếu trang cần referrer giới hạn để phục vụ đo lường, một lựa chọn phổ biến là:

```http
Referrer-Policy: strict-origin-when-cross-origin
```

Chính sách có thể đặt ở HTTP response header. Thuộc tính `referrerpolicy` của liên kết hoặc tài nguyên cũng có thể tinh chỉnh hành vi ở phạm vi phần tử:

```html
<a href="https://partner.example.net/help"
   referrerpolicy="no-referrer"
   rel="noopener noreferrer">
  Mở trang hỗ trợ đối tác
</a>
```

`rel="noreferrer"` trên liên kết cũng yêu cầu không gửi referrer và ngầm bao hàm hành vi `noopener` trong các trình duyệt hiện đại. Không nên dựa vào `Referer` như bằng chứng xác thực người dùng: header có thể bị lược bỏ và không thay thế cơ chế authorization.

### 3.2. Access log và hệ thống hạ tầng

Nhiều cấu hình access log ghi request line hoặc URL đầy đủ:

```text
GET /reset/confirm?email=user%40example.com&token=RESET-DEMO HTTP/1.1
```

Ngay cả khi trang không gửi referrer cho bên ngoài, URL vẫn có thể nằm trong:

- Log của CDN, reverse proxy, WAF và load balancer.
- Log của web server và framework.
- APM, distributed tracing, error reporting và hệ thống giám sát.
- Log của API gateway, hệ thống phân tích lưu lượng và công cụ replay request.

Rủi ro tăng khi log được sao chép sang nhiều workspace, được giữ quá lâu, có nhiều người truy cập hoặc được gửi tới nhà cung cấp bên ngoài.

**Biện pháp:** không đặt bí mật trong URL; cấu hình redaction ở từng lớp ghi log; loại bỏ hoặc che query parameter nhạy cảm; giới hạn quyền truy cập và thời gian lưu; không thu thập request body/URL đầy đủ nếu không có nhu cầu rõ ràng. Chỉ che ở log ứng dụng nhưng để CDN/WAF ghi nguyên URL vẫn còn rò rỉ.

### 3.3. Browser history, bookmark và đồng bộ trình duyệt

URL điều hướng cấp cao thường được lưu trong history. Người dùng có thể:

- Mở lại URL từ lịch sử hoặc autocomplete.
- Đánh dấu URL có query chứa dữ liệu nhạy cảm.
- Đồng bộ history sang thiết bị hoặc tài khoản trình duyệt khác.
- Chia sẻ URL qua clipboard, email hoặc chat.
- Chụp màn hình có thanh địa chỉ hoặc nội dung URL.

Một token có thời hạn ngắn vẫn có thể bị sử dụng trong khoảng thời gian còn hiệu lực nếu bị lộ qua history hoặc chia sẻ. Hãy thiết kế token một lần, có thời hạn ngắn và gắn với đúng người dùng/giao dịch; tốt nhất không đặt session token hay access token dài hạn trong URL.

### 3.4. Analytics, pixel và script bên thứ ba

Trang nhạy cảm có thể tải script analytics, quảng cáo, chat widget, ảnh, font hoặc pixel từ bên thứ ba. Các thành phần này thường có thể nhận:

- URL trang qua `document.location` nếu script chạy trực tiếp trong trang.
- Referrer qua request tải tài nguyên, tùy chính sách.
- Dữ liệu sự kiện mà ứng dụng chủ động truyền cho analytics.
- Thông tin người dùng hoặc giao dịch nếu mã client gửi nhầm.

Một script bên thứ ba được nhúng trực tiếp bằng `<script src="...">` thường chạy trong môi trường của tài liệu nhúng và có thể đọc URL trang, DOM và dữ liệu mà JavaScript cùng origin được phép truy cập. Việc file script đến từ hostname khác **không tự tạo sandbox**.

Biện pháp gồm hạn chế script bên thứ ba trên trang xác thực/thanh toán, kiểm kê dữ liệu gửi tới analytics, không đưa token vào event payload, dùng CSP để giới hạn nguồn script/kết nối/ảnh và cân nhắc cô lập widget không đáng tin bằng iframe sandbox. CSP giảm bề mặt gửi dữ liệu ra ngoài nhưng không sửa được bí mật đã đặt trong URL hoặc script hợp pháp đã có quyền đọc trang.

### 3.5. Redirect và chuỗi điều hướng

Một endpoint redirect có thể chuyển tiếp tham số:

```text
/continue?next=https%3A%2F%2Fpartner.example.net%2Fcallback%3Fcode%3DDEMO
```

URL ban đầu có thể bị ghi trong log trước khi redirect. URL đích trong header `Location` cũng có thể chứa thông tin nhạy cảm và xuất hiện trong log hoặc history. Sau redirect, request tiếp theo có thể tạo thêm `Referer` theo chính sách của trình duyệt.

Không đưa bí mật vào tham số `next`, `returnUrl`, `redirect`, `continue` hoặc URL callback. Kiểm tra đích redirect ở server bằng allowlist chính xác; không phản chiếu URL tùy ý. Với dữ liệu cần chuyển giữa hai dịch vụ, dùng mã giao dịch ngẫu nhiên, dùng một lần và trao đổi qua kênh backend đã xác thực khi kiến trúc cho phép.

## 4. Query, path và fragment: không có vị trí URL nào là kho bí mật

| Vị trí | Có gửi tới máy chủ khi tải trang? | Có thể xuất hiện ở đâu? | Khuyến nghị |
| --- | --- | --- | --- |
| Path | Có | Request, access log, tracing, history, referrer | Không nhúng PII hoặc token; dùng mã tài nguyên không tiết lộ danh tính nếu phù hợp. |
| Query | Có | Request, log, analytics, history, referrer, redirect | Không chứa password, session ID, access token hoặc reset token có quyền dài hạn. |
| Fragment | Không gửi trong request HTTP thông thường | Browser history, clipboard, JavaScript, client analytics | Không dùng để cất bí mật; tránh token trong fragment. |
| Userinfo | Không nên sử dụng | URL hiển thị, parser, log và công cụ xử lý URL | Không nhúng username/password vào URL. |

Đường dẫn cũng có thể làm lộ dữ liệu. Ví dụ `/users/lan.nguyen/private-records` có thể tiết lộ tên người dùng hoặc loại hồ sơ ngay trong log. Dù nội dung response được bảo vệ bằng authorization, metadata của path vẫn có thể tiết lộ thông tin.

### Fragment không đi qua HTTP nhưng vẫn có rủi ro

Ví dụ:

```text
https://app.example.com/callback#access_token=DEMO-TOKEN
```

Trình duyệt không gửi `#access_token=...` trong request tải callback, và fragment thường không được đưa vào `Referer`. Tuy nhiên, JavaScript trên trang có thể đọc:

```js
const fragment = new URLSearchParams(location.hash.slice(1));
const token = fragment.get('access_token');
```

Nếu trang callback có XSS hoặc tải script bên thứ ba không đáng tin, token có thể bị lấy. Token trong fragment cũng có thể tồn tại trong browser history và bị sao chép. Đây là một lý do quan trọng để tránh OAuth Implicit Flow trong ứng dụng mới và ưu tiên Authorization Code Flow với PKCE theo hướng dẫn giao thức hiện hành.

## 5. URL encoding không phải mã hóa bí mật

Percent-encoding biểu diễn byte của một giá trị bằng dạng `%HH` để dữ liệu có thể xuất hiện an toàn trong thành phần URL. Ví dụ:

```text
email=user+demo%40example.com
search=red%20shoes
```

`%40` biểu diễn ký tự `@`, còn `%20` biểu diễn dấu cách theo dạng percent-encoding. Cách biểu diễn này **không có khóa bí mật**, không làm dữ liệu khó khôi phục và không cung cấp tính bảo mật.

Base64 cũng không phải encryption:

```js
const original = 'reset-token-demo';
const encoded = btoa(original);

console.log(encoded);        // Có thể giải mã ngay.
console.log(atob(encoded));  // reset-token-demo
```

Không dùng percent-encoding, Base64, URL-safe Base64 hoặc một phép thay thế ký tự để “che giấu” token/password. Nếu người nhận URL có quyền đọc URL, họ có thể giải mã hoặc chuyển đổi dữ liệu.

### Dùng URL API thay cho ghép chuỗi

Khi tạo URL từ dữ liệu đầu vào, dùng parser và API chuẩn:

```js
const url = new URL('https://app.example.com/search');
url.searchParams.set('q', 'áo sơ mi xanh');
url.searchParams.set('page', '2');

console.log(url.href);
// https://app.example.com/search?q=%C3%A1o+s%C6%A1+mi+xanh&page=2
```

`URLSearchParams` xử lý việc encode giá trị query theo quy tắc phù hợp. Điều này giúp tránh lỗi dấu phân cách, nhưng **không làm query bí mật** và không thay thế xác thực URL đích. Khi nhận URL do người dùng kiểm soát, hãy phân tích bằng `new URL()`, kiểm tra protocol, hostname, port và các thành phần được phép.

Không tự decode một giá trị nhiều lần. Double decoding có thể làm thay đổi ý nghĩa của dấu phân cách hoặc chuỗi đã được lọc ở lớp trước. Một quy trình đúng cần thống nhất số lần parse/decode giữa proxy, framework và ứng dụng; validation phải thực hiện trên giá trị đã được chuẩn hóa theo đúng ngữ cảnh.

### Encoding theo ngữ cảnh vẫn cần thiết

URL encoding không thay thế HTML escaping hoặc JavaScript escaping. Ví dụ, nếu đưa một URL vào thuộc tính HTML:

```js
const link = document.createElement('a');
link.textContent = 'Mở tài liệu';
link.href = validatedUrl.href;
document.querySelector('#links').append(link);
```

Hãy xác thực protocol và origin nếu URL có thể đến từ người dùng. Không chèn URL tùy ý bằng `innerHTML`, và không cho phép scheme thực thi như `javascript:`. Trusted Types/CSP có thể bổ sung bảo vệ cho các DOM sink, nhưng không biến một URL nguy hiểm thành URL hợp lệ.

## 6. GET, POST và vị trí lưu dữ liệu

Form dùng GET thường đưa các trường vào query string:

```html
<form action="/search" method="get">
  <input name="q" value="browser security">
  <button type="submit">Tìm kiếm</button>
</form>
```

Đây là lựa chọn phù hợp cho truy vấn có thể bookmark hoặc chia sẻ, miễn là dữ liệu không nhạy cảm. Không dùng GET để gửi password, reset token hoặc thực hiện thay đổi trạng thái.

Form POST gửi trường trong request body:

```html
<form action="/account/email" method="post">
  <input type="email" name="email">
  <input type="hidden" name="csrf_token" value="DEMO-CSRF-TOKEN">
  <button type="submit">Cập nhật email</button>
</form>
```

POST giúp dữ liệu không nằm trong URL, browser address bar, query-based history và `Referer` theo cách GET thường gặp. Tuy nhiên, **POST không tự mã hóa dữ liệu và không đảm bảo body không bị ghi log**. HTTPS vẫn bắt buộc; hệ thống proxy/APM có thể cấu hình thu thập body; ứng dụng phải bảo vệ log và chống CSRF. Không dùng POST như lý do để ghi password hoặc token vào log.

Đối với API, dữ liệu nhạy cảm thường được truyền trong body qua HTTPS và được xác thực bằng cookie phiên an toàn hoặc token trong header theo kiến trúc phù hợp. Không nhúng bearer token vào query để tiện gọi API hoặc tạo liên kết.

## 7. Các luồng đặc biệt: reset password và OAuth/OIDC

### 7.1. Password reset

Một liên kết reset thường có dạng:

```text
https://app.example.com/reset?token=ONE-TIME-RESET-TOKEN
```

Đây là bearer secret: bất kỳ ai có token còn hiệu lực có thể có khả năng thực hiện hành động reset. Nếu token xuất hiện trong history, referrer, analytics hoặc log, tài khoản có thể bị chiếm quyền.

Thiết kế an toàn hơn:

1. Token ngẫu nhiên đủ mạnh, chỉ dùng một lần, có thời hạn ngắn và gắn với đúng tài khoản/mục đích.
2. Lưu bản băm token ở server nếu kiến trúc cho phép; không lưu token dạng rõ trong log.
3. Response trang reset đặt `Referrer-Policy: no-referrer`, `Cache-Control: no-store` và tránh tải analytics/script bên thứ ba.
4. Sau khi xác minh token ở server, tạo một quy trình tiếp tục bằng session/nonce ngắn hạn; dùng `history.replaceState()` để loại tham số khỏi URL hiển thị sau khi đã xử lý nếu phù hợp.
5. Sau khi hoàn tất hoặc hết hạn, vô hiệu hóa token; ghi log sự kiện bằng mã tương quan không nhạy cảm.

`history.replaceState()` chỉ thay URL hiển thị trong history hiện tại. Nó **không thể xóa** request đã tới server, log ở proxy/CDN, history đã đồng bộ trước đó hoặc dữ liệu mà analytics đã thu thập. Vì vậy, phải ngăn rò rỉ ngay từ thiết kế token và log.

### 7.2. OAuth 2.0 và OpenID Connect

Luồng đăng nhập hiện đại thường dùng Authorization Code Flow với PKCE. Trình duyệt được điều hướng tới authorization endpoint, sau đó quay về `redirect_uri` với một authorization code ngắn hạn và `state`. Code cần được đổi ở backend theo giao thức và không phải access token dài hạn.

Các nguyên tắc quan trọng:

- Đăng ký và so khớp chính xác `redirect_uri`; tránh open redirect trên callback.
- Dùng `state` gắn với giao dịch và kiểm tra khi callback trở về.
- Dùng PKCE để ràng buộc authorization code với client đã khởi tạo giao dịch.
- Với OpenID Connect, kiểm tra `nonce` và chữ ký/issuer/audience/expiry của ID token theo đúng flow.
- Authorization code là dữ liệu nhạy cảm: không ghi nguyên callback URL vào log/analytics; đổi code ngay tại backend và tránh tải tài nguyên bên thứ ba trước khi xử lý callback.
- Sau khi xử lý, chuyển người dùng tới URL sạch; xóa code/state khỏi thanh địa chỉ bằng redirect phía server hoặc `history.replaceState()` khi phù hợp.

Không dùng access token lâu dài trong query hoặc fragment. Việc URL callback có code là một đặc tính của Authorization Code Flow, nên phải giảm thời gian tồn tại và mọi bề mặt ghi nhận code thay vì giả định HTTPS tự bảo vệ khỏi rò rỉ tại endpoint.

## 8. Biện pháp phòng vệ theo từng lớp

### 8.1. Giảm dữ liệu nhạy cảm trong URL

Đây là biện pháp ưu tiên:

- Không đặt password, session ID, API key, access token, reset token dài hạn hoặc dữ liệu cá nhân không cần thiết trong query/path/fragment.
- Dùng mã tham chiếu ngẫu nhiên, có thời hạn và phạm vi hẹp thay vì nhúng thông tin thật.
- Ưu tiên cookie phiên với `Secure`, `HttpOnly`, `SameSite` phù hợp hoặc header xác thực cho API.
- Với form tìm kiếm và bộ lọc không nhạy cảm, GET/query vẫn phù hợp vì URL có thể bookmark và chia sẻ.
- Không xem mã hóa URL là cách bảo vệ bí mật.

### 8.2. Giới hạn referrer

Chính sách cấp site:

```http
Referrer-Policy: strict-origin-when-cross-origin
```

Trang xử lý dữ liệu nhạy cảm:

```http
Referrer-Policy: no-referrer
```

Chính sách per-link:

```html
<a href="https://external.example.net/"
   rel="noopener noreferrer">
  Mở trang ngoài
</a>
```

Chọn chính sách theo dữ liệu của trang nguồn và nhu cầu tích hợp. `no-referrer` giảm rò rỉ URL nguồn nhưng không ngăn người dùng copy URL, browser history, server log hoặc script cùng origin đọc `location.href`.

### 8.3. Kiểm soát cache

Response chứa dữ liệu cá nhân hoặc kết quả xác thực nhạy cảm thường nên dùng:

```http
Cache-Control: no-store
```

`no-store` yêu cầu cache tuân thủ không lưu response; nó không xóa browser history, log hay bản sao mà ứng dụng tự tạo. `no-cache` có ý nghĩa khác: response có thể được lưu nhưng phải revalidate trước khi dùng. Đừng nhầm hai chỉ thị.

Đặt cache policy cho đúng endpoint và kiểm thử cả browser cache lẫn CDN/reverse proxy. Với URL có query nhạy cảm, cần cấu hình cache key và log redaction để tránh lưu/copy query vào hệ thống chia sẻ.

### 8.4. Bảo vệ log và telemetry

- Redact các tham số như `token`, `code`, `secret`, `password`, `email` ở gateway, web server, app log, APM và analytics.
- Tốt hơn là không ghi toàn bộ query string khi không cần; ghi route template và mã tương quan thay thế.
- Không capture request body chứa mật khẩu, token hoặc thông tin xác thực trong hệ thống replay/tracing.
- Giới hạn quyền truy cập log, retention, export và chia sẻ với nhà cung cấp.
- Có kiểm thử tự động bảo đảm token giả trong URL không xuất hiện trong log ở bất kỳ lớp nào.

Không chỉ lọc theo tên tham số đã biết. Bí mật có thể nằm trong path, nested URL, redirect target hoặc tham số được encode. Nên có chính sách dữ liệu và cơ chế redaction ở các điểm ghi nhận trung tâm.

### 8.5. Hạn chế script và kết nối bên thứ ba

CSP có thể giới hạn nguồn script, ảnh, form và kết nối mạng:

```http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{RANDOM_PER_RESPONSE}'; img-src 'self'; connect-src 'self'; form-action 'self'; object-src 'none'; base-uri 'none'
Referrer-Policy: no-referrer
Cache-Control: no-store
```

Đây là cấu hình minh họa cho một trang nhạy cảm. Nonce phải ngẫu nhiên, khó đoán và mới cho mỗi response; các nguồn cần thiết phải được bổ sung có kiểm soát. `img-src` và `connect-src` hạn chế một số kênh truyền dữ liệu ra ngoài, nhưng không ngăn script hợp pháp cùng origin đọc URL rồi gửi dữ liệu qua một endpoint được phép. CSP là lớp giảm thiểu, không thay thế việc loại bí mật khỏi URL.

Trusted Types có thể giảm rủi ro khi dữ liệu URL được đưa vào DOM sink như `innerHTML`. Tuy nhiên, nó không che query string khỏi history hoặc log. XSS phòng vệ và URL leakage có liên hệ với nhau nhưng là hai vấn đề cần các kiểm soát riêng.

### 8.6. Loại tham số khỏi URL sau khi xử lý

Nếu ứng dụng buộc phải nhận một mã dùng một lần trong URL, sau khi server/client đã xử lý đúng, có thể thay URL hiển thị:

```js
const cleanUrl = new URL(location.href);
cleanUrl.searchParams.delete('code');
cleanUrl.searchParams.delete('state');
history.replaceState(null, '', cleanUrl.pathname + cleanUrl.search + cleanUrl.hash);
```

Chỉ làm điều này **sau khi** đã kiểm tra và hoàn tất bước cần dùng tham số. Không xóa `state` trước khi xác thực callback. Phương pháp này giúp giảm khả năng người dùng copy lại URL và giảm lộ trong các thao tác tiếp theo của trang, nhưng server đã nhận request đầu tiên và các log trước đó vẫn có thể lưu URL cũ.

## 9. Thực hành: quan sát URL và referrer trong DevTools

Thí nghiệm dưới đây dùng dữ liệu giả, không dùng tài khoản hoặc token thật. Có thể thực hiện trên hai origin do người học kiểm soát, ví dụ:

```text
Trang nguồn: https://app.example.test/
Trang đích:  https://partner.example.test/observe
```

Hai hostname cần được trỏ tới môi trường thử nghiệm của người học và có chứng chỉ phù hợp. Nếu không có môi trường đó, dùng hai site thử nghiệm riêng mà mình được phép kiểm soát; không gửi dữ liệu nhạy cảm tới website công cộng.

### 9.1. Kiểm tra request target và fragment

Mở Console trên trang nguồn và chạy:

```js
const sample = new URL(
  'https://app.example.test/report?id=42&token=DEMO#section-2'
);

console.log(sample.pathname);
console.log(sample.search);
console.log(sample.hash);
console.log(sample.origin);
```

Mở tab Network, tải URL tương tự và chọn request document. Quan sát **Request URL** và request headers. Path/query xuất hiện trong request URL; fragment không được gửi trong HTTP request. Trong Console của chính trang nguồn, `location.hash` vẫn có thể đọc fragment.

### 9.2. So sánh chính sách referrer

Trên trang nguồn, tạo ba liên kết thử:

```html
<a href="https://partner.example.test/observe">Default policy</a>
<a href="https://partner.example.test/observe"
   referrerpolicy="strict-origin-when-cross-origin">
  Strict origin when cross-origin
</a>
<a href="https://partner.example.test/observe"
   referrerpolicy="no-referrer">
  No referrer
</a>
```

Mở từng liên kết và kiểm tra header `Referer` tại request document ở Network phía đích (hoặc log server thử nghiệm). Kỳ vọng với một trang HTTPS nguồn:

- Chính sách `strict-origin-when-cross-origin`: request cross-origin chỉ gửi origin nguồn.
- Chính sách `no-referrer`: không có header `Referer`.
- Chính sách mặc định có thể khác theo trình duyệt hoặc cấu hình; không lấy một lần quan sát làm giả định cho mọi trình duyệt.

Thử lại bằng tài nguyên ảnh hoặc `fetch` cross-origin để quan sát referrer policy ở những loại request khác nhau. Dùng dữ liệu giả trong path/query để dễ xác định có bị lộ hay không.

### 9.3. Kiểm tra log và redirect

Nếu có quyền với server thử nghiệm, gửi một URL có tham số `token=DEMO-ONLY` và kiểm tra:

1. Access log ở CDN/proxy/web server có ghi query không?
2. APM/tracing có capture URL đầy đủ không?
3. Redirect `Location` có mang token sang đích mới không?
4. Analytics hoặc script bên thứ ba có nhận URL đầy đủ không?
5. Sau khi `history.replaceState()`, URL hiển thị có sạch không và log request ban đầu có còn giá trị giả không?

**Kết quả đúng** không chỉ là token biến mất khỏi thanh địa chỉ. Giá trị thử nghiệm cần không xuất hiện ở bất kỳ log/telemetry nào không có nhu cầu hợp lệ, và không được gửi cho origin bên thứ ba qua `Referer` hoặc payload analytics.

### 9.4. Kiểm tra POST và GET

Thử hai form với dữ liệu giả:

```html
<form action="/search" method="get">
  <input name="q" value="demo-search">
  <button type="submit">GET search</button>
</form>

<form action="/submit-demo" method="post">
  <input name="value" value="demo-only">
  <button type="submit">POST demo</button>
</form>
```

Quan sát URL sau GET và request body sau POST trong Network. GET đưa giá trị vào query; POST đưa giá trị vào body. Sau đó kiểm tra log máy chủ: body cũng có thể bị ghi nếu cấu hình capture request. Không thử gửi mật khẩu hoặc dữ liệu thật vào endpoint không được phép.

## 10. Checklist rà soát URL leakage trước phát hành

| Bề mặt | Câu hỏi kiểm tra | Biện pháp mong đợi |
| --- | --- | --- |
| URL được tạo | Có token, password, session ID, email hoặc PII trong path/query/fragment không? | Loại bỏ bí mật; dùng mã tham chiếu giới hạn nếu cần. |
| Navigation | Đích redirect có được allowlist và xác minh scheme/origin không? | Chặn open redirect và scheme nguy hiểm. |
| Referrer | Trang nhạy cảm gửi URL đầy đủ cho origin khác không? | `no-referrer` hoặc policy phù hợp, kiểm thử header thực tế. |
| Third-party | Trang reset/login/payment tải script, pixel, ảnh hoặc widget ngoài không? | Giảm bên thứ ba, CSP, cô lập widget và kiểm soát analytics. |
| History/clipboard | Token có thể tồn tại trong history hoặc URL được chia sẻ không? | Token dùng một lần, thời hạn ngắn; làm sạch URL sau xử lý. |
| Access log | CDN, proxy, app, APM có ghi query/body nhạy cảm không? | Redaction tập trung, hạn chế log và retention. |
| Cache | Response nhạy cảm có bị lưu ở browser/CDN không? | `Cache-Control: no-store` khi phù hợp, kiểm tra cache key. |
| Encoding | Có nhầm percent-encoding/Base64 với mã hóa không? | Xem encoding là biểu diễn dữ liệu; không dùng để che bí mật. |
| Authentication | Token callback có được đổi/xác minh ở server và vô hiệu hóa đúng lúc không? | Dùng flow giao thức chuẩn, token ngắn hạn một lần, PKCE/state. |
| Kiểm thử | Có dấu hiệu dữ liệu giả trong history, Referer, log và analytics không? | Kiểm tra từng lớp bằng Network, Console và log thử nghiệm. |

## 11. Câu hỏi tự kiểm tra

1. Vì sao query string được gửi tới server và thường xuất hiện trong access log, trong khi fragment không được gửi trong request HTTP thông thường?
2. HTTPS bảo vệ URL khỏi người quan sát trên đường truyền ở mức nào? Vì sao nó không ngăn URL xuất hiện trong log máy chủ hoặc browser history?
3. Khi trang reset password tải ảnh từ một origin bên thứ ba, dữ liệu nào có thể bị gửi qua `Referer`? `Referrer-Policy: no-referrer` thay đổi điều gì?
4. Percent-encoding và Base64 khác encryption như thế nào? Vì sao không thể dùng chúng để bảo vệ access token?
5. POST giúp giảm loại rò rỉ nào so với GET? Những hệ thống nào vẫn có thể ghi lại request body?
6. `history.replaceState()` có thể xóa những dấu vết nào và không thể xóa những dấu vết nào?
7. Vì sao script analytics bên thứ ba được nhúng trực tiếp có thể đọc `location.href`, dù script được tải từ hostname khác?
8. Trong OAuth Authorization Code Flow với PKCE, vì sao authorization code vẫn cần được bảo vệ khỏi log và analytics?
9. `Cache-Control: no-store` và `Referrer-Policy: no-referrer` bảo vệ hai bề mặt nào khác nhau?
10. Hãy đề xuất một quy trình kiểm thử để chứng minh token giả không rò rỉ qua Network, Referer, access log và analytics.

**Tiêu chí hoàn thành:** người học có thể giải thích đường đi của từng thành phần URL, xác định đúng các kênh rò rỉ, chọn biện pháp giảm thiểu ở trình duyệt và máy chủ, đồng thời chứng minh bằng header, Network và log rằng dữ liệu thử nghiệm không bị tiết lộ ngoài ý muốn.
