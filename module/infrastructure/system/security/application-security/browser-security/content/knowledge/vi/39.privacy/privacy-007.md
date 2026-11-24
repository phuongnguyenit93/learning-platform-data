# Referrer leakage

> **Chương:** Privacy  
> **Bài học:** Referrer leakage — nhận diện và giảm rò rỉ URL qua header Referer  
> **Phạm vi module:** **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY** — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy (SOP), CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích header HTTP `Referer`, thuộc tính `document.referrer` và cách browser gửi thông tin trang nguồn.
2. Nhận diện URL path, query string và dữ liệu có thể bị lộ khi điều hướng hoặc tải tài nguyên.
3. Phân biệt các giá trị của `Referrer-Policy` và dự đoán thông tin được gửi trong từng tình huống.
4. Cấu hình policy ở HTTP response header, HTML meta, element attribute và Fetch API.
5. Giảm rò rỉ qua link ngoài, subresource, iframe, redirect và dịch vụ analytics.
6. Thiết kế URL không chứa credential, token reset hoặc dữ liệu cá nhân.
7. Hiểu giới hạn của Referrer Policy với XSS, JavaScript bên thứ ba, browser history và server log.
8. Kiểm tra request thực tế bằng DevTools và xây dựng checklist privacy cho ứng dụng web.

## 1. Referrer leakage là gì?

Khi người dùng mở một trang web rồi điều hướng tới trang khác hoặc browser tải một tài nguyên, browser có thể gửi địa chỉ trang nguồn trong HTTP request header có tên **`Referer`**. Trang nhận request có thể dùng thông tin này để biết người dùng đến từ đâu, phục vụ analytics, chống hotlink hoặc điều hướng.

Header dùng cách viết `Referer` do một lỗi chính tả lịch sử trong tên chuẩn. Chính sách kiểm soát việc gửi thông tin này có tên đúng là **`Referrer-Policy`**.

**Referrer leakage** là việc URL hoặc thông tin về trang nguồn bị gửi tới một origin hoặc dịch vụ không cần biết thông tin đó. Nếu URL nguồn có path hoặc query string chứa dữ liệu nhạy cảm, browser có thể vô tình chuyển dữ liệu đó cho website đích, CDN, analytics hoặc nhà cung cấp tài nguyên bên thứ ba.

Ví dụ, người dùng đang ở:

```text
https://app.example/account/reset?token=reset-secret-123
```

Sau đó trang tải ảnh từ:

```text
https://images.cdn.example/banner.png
```

Nếu policy cho phép gửi toàn bộ URL khi tải tài nguyên cross-origin, request ảnh có thể chứa header:

```http
Referer: https://app.example/account/reset?token=reset-secret-123
```

CDN nhận được token reset trong URL nguồn dù nó chỉ cần phục vụ ảnh. Token có thể tiếp tục xuất hiện trong access log, hệ thống giám sát hoặc dữ liệu analytics của bên nhận.

### 1.1. Browser gửi những phần nào của URL?

URL thường có các thành phần:

```text
scheme://username:password@host:port/path?query#fragment
```

Khi browser tạo `Referer`, browser không gửi username/password trong URL và không gửi fragment sau dấu `#`. Tùy Referrer Policy, thông tin còn lại có thể là:

- **Origin:** scheme, host và port.
- **Path:** đường dẫn tài nguyên.
- **Query string:** tham số sau dấu `?`.

Query string thường là nơi vô tình chứa token, email, mã giao dịch, từ khóa tìm kiếm hoặc ID nội bộ. Path cũng có thể tiết lộ thông tin, ví dụ `/users/alice/private-report`.

Không nên dựa vào việc browser bỏ fragment để lưu bí mật trong fragment. JavaScript cùng trang có thể đọc `location.hash`, browser history có thể giữ URL đầy đủ và các script bên thứ ba có thể truy cập dữ liệu URL theo quyền thực thi của chúng.

### 1.2. Referer header và document.referrer

Có hai vị trí thường gặp:

| Cơ chế | Vai trò |
|---|---|
| HTTP request header `Referer` | Browser gửi URL nguồn tới server nhận request nếu policy cho phép |
| `document.referrer` | JavaScript trên document hiện tại đọc được referrer của lần điều hướng tới document đó, nếu có |

`document.referrer` có thể là chuỗi rỗng khi người dùng mở URL trực tiếp, dùng bookmark, policy không gửi referrer hoặc browser/privacy setting loại bỏ thông tin. Giá trị này không chứng minh danh tính người dùng và không phải bằng chứng rằng một request được phép.

Không dùng `document.referrer` làm cơ chế authentication, authorization hoặc CSRF defense. Hãy dùng session, CSRF token và kiểm tra Origin theo đúng threat model.

### 1.3. Referrer leakage ảnh hưởng confidentiality

Rò rỉ referrer thường không trực tiếp cho attacker quyền đọc response của trang nguồn. Nó làm lộ metadata về hoạt động và URL mà người dùng đã truy cập.

Thông tin bị lộ có thể giúp attacker:

- Biết người dùng đã truy cập trang nội bộ hoặc khu vực nào.
- Thu thập identifier, mã hồ sơ hoặc từ khóa tìm kiếm.
- Lấy token được đặt sai trong query string.
- Liên kết hành vi người dùng giữa nhiều website hoặc dịch vụ.
- Tăng khả năng nhắm mục tiêu phishing hoặc social engineering.

Nếu URL chứa bearer token có thể dùng lại, referrer leakage có thể trở thành sự cố chiếm quyền thực sự. Hãy coi mọi URL có thể được browser gửi đi hoặc lưu lại là dữ liệu có khả năng bị quan sát.

## 2. Những luồng có thể làm lộ Referer

Referer không chỉ được gửi khi người dùng bấm link. Browser cũng có thể gửi nó khi tải subresource hoặc tạo request từ document.

### 2.1. Điều hướng qua liên kết

Một liên kết từ trang A tới trang B có thể khiến browser gửi URL của A trong header `Referer` tới B. Với policy cho phép full URL, path và query của trang A có thể bị tiết lộ.

```html
<a href="https://partner.example/article">Mở trang đối tác</a>
```

Nếu trang nguồn là trang riêng tư hoặc có tham số nhạy cảm, website đối tác có thể nhận thông tin đó qua request.

### 2.2. Tải subresource từ bên thứ ba

Các request tải ảnh, script, stylesheet, iframe, font hoặc media có thể mang referrer theo policy của document hoặc policy riêng trên element.

```html
<img src="https://analytics.example/pixel.gif" alt="">
<script src="https://cdn.example/widget.js"></script>
<iframe src="https://embed.example/content"></iframe>
```

Nhà cung cấp bên thứ ba có thể nhận origin hoặc full URL nguồn. Với script bên thứ ba, rủi ro còn rộng hơn header Referer: script chạy trong context của trang có thể đọc DOM và URL mà trang cho phép JavaScript truy cập. Referrer Policy không cô lập script đã được tải và thực thi.

### 2.3. Form submission và request bằng JavaScript

Khi submit form tới origin khác, browser có thể gửi referrer theo policy áp dụng cho request. Fetch/XHR và các request được tạo từ JavaScript cũng có thể có referrer.

```js
await fetch('https://api.partner.example/collect', {
  method: 'POST',
  body: JSON.stringify({ event: 'opened' }),
});
```

Nếu request không cần URL trang hiện tại, có thể đặt `referrerPolicy` riêng cho request:

```js
await fetch('https://api.partner.example/collect', {
  method: 'POST',
  referrerPolicy: 'no-referrer',
  body: JSON.stringify({ event: 'opened' }),
});
```

Không nhầm Referrer Policy với CORS. `referrerPolicy` kiểm soát metadata referrer; CORS kiểm soát việc JavaScript có được phép đọc response cross-origin hay không. Hai cơ chế giải quyết hai vấn đề khác nhau.

### 2.4. Redirect và tracking endpoint

Link tracking thường đi qua endpoint trung gian:

```text
https://app.example/out?destination=https%3A%2F%2Fpartner.example
```

Trang nguồn có thể được gửi tới tracking endpoint trước khi server redirect browser tới website đích. Tracking service có thể ghi URL nguồn, thời điểm, IP và các thông tin request khác.

Redirect không tự loại bỏ referrer. Policy của document, element và response trong luồng điều hướng ảnh hưởng thông tin được gửi ở từng request. Hãy kiểm tra toàn bộ chuỗi redirect trong DevTools thay vì chỉ xem URL cuối cùng.

## 3. Referrer-Policy kiểm soát thông tin được gửi

`Referrer-Policy` là cơ chế chuẩn để browser quyết định có gửi referrer hay không và gửi bao nhiêu thông tin. Policy có thể được thiết lập cho document, từng request hoặc một số element tạo request.

### 3.1. Các giá trị policy

| Policy | Cùng origin | Cross-origin | HTTPS sang HTTP |
|---|---|---|---|
| `no-referrer` | Không gửi | Không gửi | Không gửi |
| `no-referrer-when-downgrade` | Full URL | Full URL | Không gửi |
| `same-origin` | Full URL | Không gửi | Không gửi |
| `origin` | Chỉ origin | Chỉ origin | Vẫn gửi origin |
| `strict-origin` | Chỉ origin | Chỉ origin | Không gửi |
| `origin-when-cross-origin` | Full URL | Chỉ origin | Vẫn gửi origin |
| `strict-origin-when-cross-origin` | Full URL | Chỉ origin nếu không downgrade | Không gửi |
| `unsafe-url` | Full URL | Full URL | Vẫn gửi full URL |

**Full URL** trong bảng không bao gồm username/password hoặc fragment. Cross-origin là khác scheme, host hoặc port. Downgrade trong bảng là điều hướng/request từ HTTPS sang HTTP.

### 3.2. Policy thường dùng: strict-origin-when-cross-origin

Các browser hiện đại thường dùng `strict-origin-when-cross-origin` làm mặc định, nhưng hành vi có thể bị thay đổi bởi browser, privacy setting, extension, enterprise policy hoặc cấu hình website. Vì vậy, ứng dụng nên chủ động gửi header thay vì phụ thuộc vào default.

Với policy này:

- Request cùng origin có thể gửi full URL để ứng dụng vẫn dùng được thông tin referrer nội bộ.
- Request cross-origin chỉ gửi origin, không gửi path và query.
- Request từ HTTPS sang HTTP không gửi referrer.

Ví dụ:

```http
Referrer-Policy: strict-origin-when-cross-origin
```

Đây là lựa chọn cân bằng thường phù hợp cho website thông thường. Với trang nhạy cảm như reset password, account recovery, trang quản trị hoặc nội dung chứa dữ liệu cá nhân trong URL, cân nhắc `no-referrer` hoặc loại bỏ dữ liệu nhạy cảm khỏi URL trước tiên.

### 3.3. Chọn policy theo nhu cầu privacy

- Dùng `no-referrer` khi trang không cần chia sẻ nguồn truy cập.
- Dùng `same-origin` khi chỉ cần referrer trong nội bộ website.
- Dùng `strict-origin` khi chỉ cần biết origin và muốn tránh gửi thông tin khi downgrade.
- Dùng `strict-origin-when-cross-origin` cho chính sách cân bằng giữa analytics nội bộ và giảm rò rỉ cross-origin.
- Tránh `unsafe-url` vì nó có thể gửi path và query tới website khác, kể cả khi request đi từ HTTPS sang HTTP.
- Tránh `no-referrer-when-downgrade` làm lựa chọn mới vì nó vẫn có thể gửi full URL cho website cross-origin có cùng mức bảo mật.

Không chọn policy chỉ để giữ attribution marketing nếu URL có thể chứa thông tin nhạy cảm. Attribution có thể được thực hiện bằng campaign identifier không nhạy cảm hoặc analytics event được thiết kế riêng.

## 4. Cấu hình Referrer Policy

Nên thiết lập policy ở server bằng HTTP response header. Cách này áp dụng sớm khi browser xử lý document và ít phụ thuộc vào thứ tự HTML.

### 4.1. HTTP response header

Ví dụ cấu hình:

```http
Referrer-Policy: strict-origin-when-cross-origin
```

Server có thể chọn policy chặt hơn cho các trang nhạy cảm:

```http
Referrer-Policy: no-referrer
Cache-Control: no-store
```

Đặt header theo route hoặc response phù hợp. Trang public có thể cần analytics nội bộ, trong khi trang reset token hoặc account recovery có thể không cần gửi referrer tới bất kỳ destination nào.

### 4.2. HTML meta element

Nếu không thể cấu hình header, có thể đặt policy trong phần `<head>`:

```html
<head>
  <meta name="referrer" content="strict-origin-when-cross-origin">
</head>
```

Meta policy phải xuất hiện sớm trong document, trước các element tạo request. HTTP response header vẫn là lựa chọn ưu tiên vì browser nhận policy ngay từ response.

Không đặt nhiều meta referrer policy ở các vị trí khác nhau rồi trông chờ browser kết hợp theo cách mong muốn. Hãy dùng một policy rõ ràng cho document và override riêng khi thực sự cần.

### 4.3. Attribute referrerpolicy trên element

Một số element tạo request hỗ trợ thuộc tính `referrerpolicy`, cho phép đặt policy riêng cho request đó.

Ví dụ link ngoài không cần referrer:

```html
<a
  href="https://partner.example/article"
  referrerpolicy="no-referrer"
>
  Mở trang đối tác
</a>
```

Ví dụ tài nguyên ảnh:

```html
<img
  src="https://images.cdn.example/banner.png"
  alt="Banner"
  referrerpolicy="no-referrer"
>
```

Thuộc tính tương tự được hỗ trợ trên một số element khác như `iframe`, `script` và `link`. Kiểm tra browser support và HTML element cụ thể; không giả định mọi element đều có thuộc tính này.

### 4.4. rel=noreferrer và rel=noopener

Với liên kết mở tab mới, có thể dùng:

```html
<a
  href="https://partner.example/"
  target="_blank"
  rel="noopener noreferrer"
>
  Mở đối tác
</a>
```

`noreferrer` yêu cầu browser không gửi referrer cho navigation đó và đồng thời có hiệu lực tương đương `noopener` trên liên kết. `noopener` ngăn trang đích truy cập `window.opener`, nhưng riêng `noopener` không có nghĩa là đã tắt Referer.

Không dùng `rel="nofollow"` như biện pháp bảo vệ referrer. `nofollow` là gợi ý cho crawler tìm kiếm, không phải privacy policy của browser.

### 4.5. Fetch API referrerPolicy

Có thể đặt policy riêng trong Fetch options:

```js
const response = await fetch('/api/profile', {
  credentials: 'same-origin',
  referrerPolicy: 'same-origin',
});

const profile = await response.json();
```

Ví dụ gửi request tới dịch vụ bên ngoài mà không cần tiết lộ trang nguồn:

```js
await fetch('https://metrics.example/collect', {
  method: 'POST',
  referrerPolicy: 'no-referrer',
  body: JSON.stringify({ event: 'page_view' }),
});
```

Policy trong Fetch options điều khiển referrer cho request đó. Nó không thay đổi policy của toàn document và không ngăn script bên thứ ba đọc URL nếu script đã được thực thi trong page context.

## 5. Xác định policy nào có hiệu lực

Một trang có thể có policy toàn document và override ở request riêng. Khi debug, cần kiểm tra nguồn policy thực tế của từng request.

### 5.1. Thứ tự áp dụng ở mức thực hành

- HTTP response header đặt policy cho document.
- Meta `name="referrer"` có thể đặt policy trong HTML document; ưu tiên một cấu hình response header rõ ràng và tránh các policy xung đột.
- Thuộc tính `referrerpolicy` trên element có thể điều chỉnh request do element đó tạo.
- Fetch option `referrerPolicy` điều chỉnh request được tạo bằng Fetch API.
- `rel="noreferrer"` trên link yêu cầu bỏ referrer cho navigation đó.

Khi có nhiều lớp cấu hình, hãy kiểm tra request cuối cùng trong Network panel. Đừng suy luận chỉ từ một dòng cấu hình vì element hoặc request code có thể override policy của document.

### 5.2. Xem referrer bằng DevTools

Trong DevTools → Network:

1. Mở trang nguồn có URL test chứa path và query giả lập.
2. Tạo navigation hoặc tải subresource tới origin test thứ hai.
3. Chọn request đích và xem Request Headers.
4. Tìm header `Referer`.
5. So sánh giá trị thực tế với policy đã cấu hình.
6. Lặp lại với same-origin, cross-origin và HTTPS-to-HTTP trong môi trường kiểm thử.

Nếu không thấy `Referer`, có thể policy đã loại bỏ nó, browser/privacy control đã can thiệp hoặc request được khởi tạo trong một context không có referrer. Kiểm tra cả response header và request initiator.

## 6. Thiết kế URL để không có bí mật cần bảo vệ

Referrer Policy là lớp giảm rò rỉ metadata. Cách phòng vệ bền vững hơn là không đặt secret hoặc dữ liệu cá nhân vào URL nếu không cần thiết.

### 6.1. Không đặt credential trong path hoặc query

Tránh các mẫu như:

```text
/account?email=alice@example.com
/reset?token=long-lived-bearer-token
/invoice/12345?access_token=secret
/search?q=diagnosis-or-private-query
```

URL có thể xuất hiện trong:

- Header Referer của request tiếp theo.
- Browser history, bookmark và danh sách tab gần đây.
- Web server, reverse proxy, CDN và WAF log.
- Analytics, APM, error reporting và session replay.
- Screenshot, clipboard, link được gửi qua chat/email.
- Hệ thống cache hoặc công cụ hỗ trợ debug.

HTTPS mã hóa request trên đường truyền nhưng không che URL khỏi các thành phần đầu cuối có quyền ghi log hoặc khỏi browser của người dùng.

### 6.2. Xử lý reset link và magic link

Một số luồng email verification, password reset hoặc magic link cần token trong URL để người dùng mở link. Nếu không thể tránh, token phải được thiết kế như credential nhạy cảm:

1. Sinh token ngẫu nhiên mật mã, đủ entropy và chỉ dùng một lần.
2. Gắn token với đúng account và đúng mục đích.
3. Đặt thời hạn ngắn và revoke sau khi dùng.
4. Khi nhận token, xác minh ở server rồi đổi lấy trạng thái ngắn hạn phù hợp.
5. Trả response với `Referrer-Policy: no-referrer` và `Cache-Control: no-store`.
6. Tránh tải analytics, pixel, script hoặc nội dung third-party trước khi token được xử lý.
7. Chuyển hướng sang URL sạch không còn token sau khi hoàn tất bước exchange.
8. Redact token khỏi access log, proxy, CDN, APM và error reporting.

Nếu token phải nằm trong query string, hãy bảo vệ cả request đầu tiên tới server. Policy chỉ giảm việc token bị gửi tiếp trong Referer; nó không xóa token khỏi URL ban đầu hoặc log của endpoint nhận link.

### 6.3. Làm sạch URL sau khi exchange

Sau khi server đã xác minh và đổi token thành trạng thái an toàn, ứng dụng có thể loại bỏ query string nhạy cảm khỏi thanh địa chỉ:

```js
const cleanUrl = window.location.pathname;
window.history.replaceState({}, document.title, cleanUrl);
```

Đây là bước giảm rủi ro cho các request tiếp theo và browser history. Nó không thay thế việc xử lý token ở server: URL ban đầu đã được request tới server và có thể đã xuất hiện trong log hoặc hệ thống giám sát.

Không gọi `replaceState` trước khi token được xử lý nếu điều đó làm mất dữ liệu cần xác thực. Không để third-party script chạy trước khi URL nhạy cảm được làm sạch.

### 6.4. Dùng identifier không phải credential

Nếu cần tham chiếu một tài nguyên trong URL, ưu tiên identifier không cấp quyền truy cập. Server vẫn phải kiểm tra session và authorization khi người dùng mở tài nguyên.

Một ID khó đoán không tự động là cơ chế phân quyền. Nếu ai có URL cũng có thể đọc tài nguyên, URL đó thực chất đang đóng vai trò bearer credential và phải được bảo vệ như secret.

## 7. Third-party script, iframe và analytics

Rò rỉ referrer thường xuất hiện ở ranh giới giữa website và dịch vụ bên ngoài. Hãy kiểm kê tài nguyên bên thứ ba và xác định mỗi nhà cung cấp thực sự cần biết thông tin gì.

### 7.1. Script bên thứ ba có quyền trong page context

Khi trang tải script bên thứ ba trực tiếp bằng `<script>`, script chạy trong JavaScript realm của document và thường có quyền truy cập DOM, URL và dữ liệu mà page JavaScript có thể đọc.

Ví dụ:

```html
<script src="https://analytics.example/sdk.js"></script>
```

Ngay cả khi `Referrer-Policy: no-referrer` ngăn header Referer, script đó vẫn có thể đọc `location.href` hoặc truy cập DOM rồi gửi dữ liệu bằng request khác nếu không có biện pháp giới hạn phù hợp.

Biện pháp:

- Chỉ tải script từ nhà cung cấp đã được đánh giá.
- Loại bỏ script không còn cần thiết.
- Dùng CSP `script-src` để allowlist nguồn script.
- Dùng Subresource Integrity (SRI) khi phù hợp với file tĩnh có version ổn định.
- Không tải script third-party trên trang có URL chứa token hoặc thông tin nhạy cảm.
- Cân nhắc đặt nội dung không tin cậy trong iframe ở origin riêng với sandbox phù hợp.

CSP và SRI giảm một số rủi ro về nguồn và tính toàn vẹn script; chúng không biến script được phép chạy thành code bị cô lập khỏi page.

### 7.2. Iframe bên thứ ba

Iframe cross-origin có ranh giới DOM khác với trang cha theo Same-Origin Policy, nhưng request tạo iframe vẫn có thể gửi referrer theo policy áp dụng.

Ví dụ:

```html
<iframe
  src="https://embed.example/widget"
  title="Widget đối tác"
  referrerpolicy="no-referrer"
  sandbox="allow-scripts"
></iframe>
```

Chọn `sandbox` token tối thiểu cần thiết cho tính năng. Không thêm quyền chỉ để widget hoạt động mà chưa hiểu tác động. Nếu iframe cần đăng nhập hoặc storage, đánh giá thêm cookie policy, partitioning và Storage Access API.

`referrerpolicy="no-referrer"` trên iframe giới hạn referrer gửi khi browser tải iframe. Nó không kiểm soát mọi request do code bên trong iframe tự tạo; document trong iframe có policy riêng cho các request tiếp theo.

### 7.3. Analytics không cần toàn bộ URL

Nhiều hệ thống analytics mặc định thu thập page URL, referrer hoặc cả hai. Trước khi gửi event:

- Chỉ gửi route template hoặc page category nếu đủ cho báo cáo.
- Allowlist query parameter thật sự cần thiết.
- Loại bỏ email, token, search term riêng tư và identifier nhạy cảm.
- Không gửi URL đầy đủ từ trang reset password, account hoặc quản trị.
- Cấu hình redaction trong SDK và dashboard.
- Kiểm tra payload thực tế ở Network, không chỉ dựa vào cấu hình giao diện.

Nếu cần đo nguồn campaign, dùng campaign code không nhạy cảm hoặc event đã được giảm dữ liệu. Không gửi raw `document.referrer` cho analytics một cách mặc định.

### 7.4. CDN, image host và font provider

Ảnh, font, stylesheet và media từ domain khác cũng tạo request. Không coi chúng vô hại chỉ vì không thực thi JavaScript.

Dùng `no-referrer` cho tài nguyên không cần referrer, tự host tài nguyên nếu phù hợp và kiểm tra CDN/provider có ghi request URL, Referer hoặc IP hay không. Hợp đồng với nhà cung cấp nên nêu rõ mục đích, retention và quyền truy cập log.

## 8. Redirect, referrer và ranh giới bảo mật

Redirect thường được dùng để chuyển người dùng giữa trang login, trang đích, tracking endpoint và identity provider. Mỗi request trong chuỗi có thể có thông tin referrer khác nhau.

### 8.1. Không giả định redirect sẽ xóa referrer

Một redirect response không tự động bảo đảm browser bỏ thông tin nguồn. Request tới endpoint trung gian và request sau redirect có thể được tạo trong các context khác nhau; policy của nguồn, request và response ảnh hưởng kết quả.

Khi kiểm thử:

- Xem request đầu tiên và từng redirect hop trong Network.
- Kiểm tra Request Headers của từng hop nếu DevTools hiển thị.
- Xác minh policy trên trang khởi tạo navigation.
- Kiểm tra policy riêng của link hoặc script tạo request.
- Không đưa token hoặc PII vào URL của endpoint redirect.

### 8.2. Trang nguồn cần policy phù hợp

`Referrer-Policy` được đặt trên response của document nguồn để kiểm soát những request mà document khởi tạo. Nếu trang `/reset?token=...` điều hướng sang domain khác, policy cần được áp dụng cho trang reset trước khi nó tạo navigation hoặc tải tài nguyên.

Đặt policy chỉ trên website đích không thể thu hồi header Referer đã gửi trong request đến website đích. Vì vậy, cấu hình phải nằm đúng nơi phát sinh request.

### 8.3. Identity provider và callback

Trong luồng OAuth/OIDC, authorization code và các tham số callback có thể xuất hiện trong URL theo giao thức. Dùng redirect URI đăng ký chính xác, `state`, PKCE và quy trình exchange ở server/client phù hợp.

Không để trang callback tải analytics hoặc script third-party trước khi xử lý code/state. Chuyển sang URL sạch sau exchange và tránh ghi query callback vào log. Referrer Policy hỗ trợ giảm phát tán URL callback sang request tiếp theo nhưng không thay thế các kiểm tra của giao thức.

## 9. Referrer Policy không thay thế các security boundary khác

Referrer Policy là một cơ chế privacy dành cho metadata của request. Nó không thay thế các cơ chế kiểm soát truy cập, cô lập origin hoặc bảo vệ credential.

### 9.1. Quan hệ với Same-Origin Policy và CORS

- Same-Origin Policy giới hạn việc một document hoặc script đọc dữ liệu từ origin khác.
- CORS cho phép server khai báo những origin nào được JavaScript đọc response cross-origin.
- Referrer Policy kiểm soát URL nguồn browser gửi trong header Referer.

Một request có thể bị CORS chặn JavaScript đọc response nhưng vẫn được gửi tới server đích và mang header Referer. Ngược lại, `no-referrer` có thể loại bỏ Referer nhưng không cấp quyền đọc response cross-origin.

Không dùng CORS để ngăn referrer leakage và không dùng Referrer Policy để thay CORS.

### 9.2. Quan hệ với CSRF

Một số hệ thống kiểm tra Referer hoặc Origin để phát hiện request cross-site. Đây là lớp phòng vệ phía server và cần được thiết kế riêng.

Không dựa vào `document.referrer` phía client để chống CSRF. Không chỉ kiểm tra Referer rồi bỏ qua CSRF token nếu ứng dụng cần token. Với cookie-authenticated state-changing request, dùng CSRF token, kiểm tra Origin phù hợp và cookie `SameSite` theo threat model.

Referrer Policy có thể làm Referer vắng mặt hoặc rút gọn. Server phải xử lý trường hợp header thiếu theo chính sách đã xác định, không coi thiếu Referer là request hợp lệ.

### 9.3. Quan hệ với CSP

CSP giới hạn nguồn tài nguyên và kết nối mà document được phép sử dụng. Ví dụ `script-src` kiểm soát nguồn script, `connect-src` kiểm soát fetch/XHR/WebSocket và `frame-src` kiểm soát nguồn iframe.

CSP có thể giảm số destination mà page gửi dữ liệu tới, nhưng không tự xóa Referer. Referrer Policy có thể giảm metadata gửi kèm request, nhưng không ngăn script đã được phép chạy đọc URL và gửi dữ liệu bằng một request khác.

Dùng cả hai theo mục đích riêng. Với script bên thứ ba, hãy đánh giá quyền thực thi và dữ liệu mà script có thể truy cập, không chỉ kiểm tra header Referer.

### 9.4. Quan hệ với cookie và session

Referrer Policy không quyết định cookie có được gửi hay không. Cookie flags như `Secure`, `HttpOnly`, `SameSite`, `Path` và `Domain` có quy tắc riêng.

Không đặt session ID, access token hoặc refresh token vào URL rồi trông chờ `no-referrer` bảo vệ chúng. Cookie `HttpOnly` cũng không ngăn URL có token bị ghi vào browser history hoặc server log.

### 9.5. Quan hệ với TLS và HSTS

HTTPS bảo vệ request khỏi bị đọc hoặc sửa trên đường truyền giữa các điểm kết thúc TLS. Nó không ngăn destination server hoặc proxy được ủy quyền đọc header Referer.

HSTS giúp browser ưu tiên HTTPS cho host đã áp dụng policy. Referrer Policy `strict-origin-when-cross-origin` hoặc `strict-origin` giúp không gửi referrer khi downgrade từ HTTPS sang HTTP. Các cơ chế này bổ trợ nhau.

## 10. Bảo vệ log và hệ thống quan sát

Ngay cả khi browser không gửi full URL trong Referer, URL ban đầu vẫn có thể được ghi tại server nhận request. Privacy review cần xem cả browser và hạ tầng.

### 10.1. Redact tại nhiều lớp

Kiểm tra nơi có thể ghi URL và Referer:

- Web server và reverse proxy.
- CDN, WAF và load balancer.
- APM, distributed tracing và error reporting.
- Analytics SDK và session replay.
- Log của dịch vụ redirect/tracking.
- Công cụ hỗ trợ khách hàng và debug.

Redact trước khi dữ liệu được lưu hoặc gửi tới bên thứ ba. Chỉ ẩn field trong dashboard sau khi dữ liệu đã được lưu không loại bỏ rủi ro.

### 10.2. Chỉ ghi thông tin cần thiết

Thay vì lưu toàn bộ Referer, cân nhắc ghi:

- Scheme/host hoặc site category nếu cần attribution.
- Route template thay cho path có identifier.
- Campaign code không nhạy cảm.
- Event name và timestamp.
- Correlation ID không mang quyền truy cập.

Không ghi query string nguyên vẹn theo mặc định. Nếu cần giữ một số tham số, dùng allowlist rõ ràng và loại bỏ token, email, search term riêng tư, session ID và identifier nhạy cảm.

### 10.3. Quản lý retention và quyền truy cập

Log referrer có thể tiết lộ lịch sử truy cập hoặc quan hệ giữa các trang. Giới hạn thời gian lưu, quyền truy cập theo vai trò và khả năng export. Dùng audit log khi nhân sự truy cập dữ liệu nhạy cảm.

Đưa referrer và URL vào quy trình phân loại dữ liệu của ứng dụng. Đừng mặc định rằng một header kỹ thuật không thể chứa thông tin cá nhân.

## 11. Các lỗi triển khai thường gặp

### 11.1. Chỉ cấu hình policy trên trang đích

Trang đích không thể thu hồi Referer đã gửi trong request tới nó. Hãy cấu hình policy trên document nguồn trước khi document tạo request.

### 11.2. Chọn unsafe-url để giữ analytics

Policy này có thể gửi full URL, gồm path và query, tới destination cross-origin và cả khi downgrade. Nếu cần attribution, hãy thiết kế campaign identifier không nhạy cảm.

### 11.3. Chỉ dùng rel=noopener

`noopener` ngăn trang mới điều khiển tab nguồn qua `window.opener`; nó không tự ngăn gửi Referer. Nếu không muốn gửi referrer, dùng `noreferrer` hoặc policy phù hợp.

### 11.4. Cho rằng no-referrer ngăn script đọc URL

Policy chỉ điều khiển metadata referrer của request. Script chạy trong page context vẫn có thể đọc URL và DOM mà page cho phép. Hạn chế third-party script, dùng CSP và tách nội dung không tin cậy vào origin riêng.

### 11.5. Cho rằng fragment là nơi lưu secret an toàn

Fragment không được gửi trong HTTP Referer, nhưng JavaScript trên page đọc được, browser history lưu URL và script third-party cùng context có thể truy cập. Không dùng fragment làm nơi cất credential.

### 11.6. Chỉ redact analytics nhưng quên proxy

URL có thể đã được ghi ở CDN, reverse proxy hoặc APM trước khi analytics SDK xử lý. Kiểm tra đường đi của request và redaction tại từng lớp.

## 12. Thực hành A — Quan sát Referer giữa hai origin

Dùng hai website test do bạn kiểm soát, ví dụ `https://source.dev.example` và `https://destination.dev.example`. Không dùng URL chứa token thật hoặc dữ liệu người dùng.

1. Tạo trang nguồn với một path và query giả lập, chẳng hạn `/private/demo?case=sample`.
2. Đặt `Referrer-Policy: unsafe-url` trên response của trang nguồn.
3. Tạo link tới origin đích và click link.
4. Mở DevTools → Network trên origin đích và xem Request Headers.
5. Xác minh Referer có thể chứa path/query của trang nguồn.
6. Đổi policy thành `strict-origin-when-cross-origin` và lặp lại.
7. Xác minh request cross-origin chỉ gửi origin khi không có downgrade.
8. Đổi policy thành `no-referrer` và xác minh header không được gửi.

Kết quả mong đợi: quan sát được sự khác nhau giữa full URL, origin-only và không gửi referrer.

## 13. Thực hành B — So sánh navigation, subresource và Fetch

1. Trên trang nguồn, thêm link tới destination, một ảnh cross-origin và một iframe test.
2. Tải trang với policy document `strict-origin-when-cross-origin`.
3. Kiểm tra Referer ở từng request trong Network.
4. Đặt `referrerpolicy="no-referrer"` trên riêng ảnh và iframe.
5. Tạo một Fetch request với `referrerPolicy: "no-referrer"`.
6. So sánh các request đã override với request dùng policy document.
7. Thử link `rel="noopener"` và `rel="noreferrer"` để thấy khác biệt về referrer và opener.

Kết quả mong đợi: policy toàn document có thể được override theo request/element; `noopener` và `noreferrer` giải quyết hai mục tiêu khác nhau.

## 14. Thực hành C — Bảo vệ URL reset token

Dùng ứng dụng staging và token giả, ngắn hạn, một lần.

1. Tạo route reset có token test trong query string.
2. Cấu hình response trang này với `Referrer-Policy: no-referrer` và `Cache-Control: no-store`.
3. Không tải analytics, pixel hoặc script third-party trên route này.
4. Xác minh token ở server và đổi lấy trạng thái reset ngắn hạn.
5. Chuyển hướng hoặc dùng `history.replaceState` để làm sạch URL sau exchange.
6. Kiểm tra request tiếp theo không gửi URL token trong Referer.
7. Kiểm tra server/proxy/APM log đã redact token.
8. Thử dùng lại token và xác minh server từ chối.

Kết quả mong đợi: token không bị phát tán sang request tiếp theo, được bảo vệ tại request đầu tiên và không thể replay sau khi dùng.

## 15. Thực hành D — Kiểm tra script và analytics bên thứ ba

1. Dùng trang test có query giả lập không nhạy cảm.
2. Thêm analytics script hoặc iframe test từ origin thứ hai do bạn kiểm soát.
3. Đặt `Referrer-Policy: no-referrer` và kiểm tra header Referer trong Network.
4. Với script test, kiểm tra trong môi trường local rằng code cùng page context vẫn đọc được `location.href`.
5. Tắt script đó bằng CSP `script-src` và xác minh browser chặn tải/thực thi.
6. Kiểm tra analytics payload không chứa URL/query ngoài allowlist.
7. Kiểm tra log CDN/proxy không lưu query nhạy cảm.

Kết quả mong đợi: phân biệt được việc bỏ header Referer với việc cô lập quyền của script bên thứ ba.

## 16. Troubleshooting referrer leakage

### 16.1. Không thấy header Referer

Kiểm tra:

- Trang nguồn có policy `no-referrer` hoặc `same-origin` không?
- Request có phải điều hướng trực tiếp, bookmark hoặc context không có referrer không?
- Element có `referrerpolicy` riêng không?
- Fetch request có `referrerPolicy` riêng không?
- Browser, extension hoặc privacy setting có loại bỏ referrer không?
- Request có đi qua redirect hoặc service worker làm thay đổi luồng không?

Không kết luận rằng browser luôn gửi Referer chỉ vì trang được mở từ một trang khác.

### 16.2. Đã đặt header nhưng vẫn thấy full URL

Xác minh header được gửi trên response của đúng document nguồn. Sau đó kiểm tra:

- Header có bị proxy/CDN ghi đè hoặc loại bỏ không?
- Meta policy có xuất hiện và thay đổi document policy không?
- Element hoặc Fetch request có override policy không?
- Bạn đang xem request cùng origin hay cross-origin?
- Trang nguồn có được phục vụ từ cache với header cũ không?

Dùng hard reload và kiểm tra response headers thực tế thay vì chỉ xem cấu hình ở source code.

### 16.3. Analytics vẫn nhận URL sau khi đặt no-referrer

Kiểm tra payload analytics. SDK có thể đọc `location.href` hoặc `document.referrer` rồi đưa chúng vào body của request. Referrer Policy chỉ kiểm soát header Referer, không tự động lọc payload do JavaScript tạo.

Cấu hình redaction trong SDK, bỏ field không cần thiết và kiểm tra request body. Nếu script không đáng tin hoặc không cần thiết, loại bỏ nó hoặc cô lập trong iframe riêng.

### 16.4. URL sạch trên thanh địa chỉ nhưng log vẫn có token

`history.replaceState` chỉ cập nhật URL hiển thị và history của document hiện tại. Request ban đầu đã tới server với token. Kiểm tra log ở CDN, reverse proxy, application, WAF và APM; áp dụng redaction tại nơi nhận request đầu tiên.

## 17. Checklist review Referrer leakage

| Hạng mục | Câu hỏi cần trả lời |
|---|---|
| Policy | Website có gửi Referrer-Policy rõ ràng thay vì phụ thuộc default? |
| Default | Policy có phù hợp với nhu cầu privacy và analytics? |
| Sensitive routes | Trang reset, recovery, account và admin có policy chặt hơn? |
| URL design | Path/query có chứa token, email, PII hoặc secret không? |
| Reset links | Token ngắn hạn, one-time, exchange an toàn và URL được làm sạch? |
| Third-party | Có kiểm kê script, iframe, image, font và analytics provider? |
| Script access | Script bên thứ ba có thực sự cần quyền chạy trong page context? |
| Element | Link/subresource nhạy cảm có referrerpolicy hoặc noreferrer phù hợp? |
| Fetch | Request ngoài có đặt referrerPolicy theo nhu cầu tối thiểu? |
| Redirect | Từng hop được kiểm tra và endpoint redirect không ghi token? |
| Analytics | Chỉ gửi route/campaign data cần thiết, query đã allowlist/redact? |
| Logging | CDN, proxy, WAF, server, APM và session replay có redaction? |
| Retention | Log referrer có retention và quyền truy cập phù hợp? |
| CSRF | Server không dùng document.referrer làm CSRF defense? |
| CORS/SOP | Team hiểu Referrer Policy không thay thế CORS hoặc SOP? |
| CSP | script-src/connect-src/frame-src giới hạn nguồn theo nhu cầu? |
| Iframe | Iframe không tin cậy có sandbox và policy phù hợp? |
| Testing | Đã kiểm tra same-origin, cross-origin, downgrade và request override? |
| Monitoring | Có quy trình phát hiện token/PII trong URL và log? |

## 18. Câu hỏi tự kiểm tra

**1.** Header nào mang URL trang nguồn trong HTTP request?  
**Đáp án:** `Referer`. Chính sách điều khiển nó có tên `Referrer-Policy`.

**2.** Referer có gửi fragment sau dấu `#` không?  
**Đáp án:** Không. Browser không đưa fragment vào Referer, nhưng JavaScript và browser history vẫn có thể truy cập URL đó.

**3.** `document.referrer` có thể dùng làm authentication không?  
**Đáp án:** Không. Giá trị có thể rỗng hoặc bị policy/browser thay đổi và không xác định danh tính người dùng.

**4.** `strict-origin-when-cross-origin` gửi gì khi cùng origin?  
**Đáp án:** Gửi full URL, không gồm userinfo và fragment.

**5.** Policy nào chỉ gửi origin cross-origin và bỏ referrer khi HTTPS chuyển sang HTTP?  
**Đáp án:** `strict-origin-when-cross-origin`.

**6.** `no-referrer` có ngăn script bên thứ ba đọc `location.href` không?  
**Đáp án:** Không. Nó chỉ ngăn gửi header Referer; script chạy trong page context vẫn có thể đọc URL.

**7.** `noopener` có tự tắt Referer không?  
**Đáp án:** Không. Dùng `noreferrer` nếu cần vừa bỏ referrer vừa ngăn trang đích truy cập opener.

**8.** Vì sao không nên đặt reset token trong URL?  
**Đáp án:** URL có thể xuất hiện trong Referer, browser history, server/proxy log và analytics.

**9.** Vì sao đặt Referrer Policy trên trang đích là quá muộn?  
**Đáp án:** Request tới trang đích đã được tạo; policy cần đặt trên document nguồn trước khi request phát sinh.

**10.** CORS có ngăn request gửi Referer không?  
**Đáp án:** Không. CORS kiểm soát việc JavaScript đọc response cross-origin; Referrer Policy kiểm soát metadata nguồn.

**11.** `history.replaceState` có xóa token khỏi server log của request đầu tiên không?  
**Đáp án:** Không. Nó chỉ làm sạch URL trong document hiện tại và history sau khi request ban đầu đã xảy ra.

**12.** Cần kiểm tra những nơi nào ngoài analytics khi điều tra rò rỉ URL?  
**Đáp án:** Web server, reverse proxy, CDN, WAF, APM, error reporting, session replay và dịch vụ redirect/tracking.

## Ghi nhớ

**Referrer leakage xảy ra khi browser gửi URL trang nguồn tới destination không cần biết thông tin đó.** Header `Referer` có thể chứa origin, path và query tùy `Referrer-Policy`; fragment và userinfo không được gửi trong header này. Policy `strict-origin-when-cross-origin` thường là lựa chọn cân bằng, còn `no-referrer` phù hợp với trang nhạy cảm không cần chia sẻ nguồn truy cập.

Hãy đặt policy trên document nguồn, dùng override cho link/subresource/Fetch khi cần và kiểm tra request thực tế trong DevTools. Quan trọng hơn, không đặt secret trong URL; bảo vệ reset link bằng token one-time, exchange và URL sạch; giới hạn script bên thứ ba; redact URL tại CDN/proxy/server/APM/analytics. Referrer Policy không thay thế SOP, CORS, CSRF token, CSP hoặc authorization.
