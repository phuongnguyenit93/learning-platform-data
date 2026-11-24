# Query chứa secret: ngăn rò rỉ credential qua URL

Query string thường được dùng để truyền bộ lọc, phân trang, mã tham chiếu và trạng thái điều hướng. Nhưng nếu đặt password, access token, API key, OTP hoặc reset token vào query, giá trị đó có thể xuất hiện ở nhiều nơi ngoài request mà ứng dụng dự định gửi.

URL có thể được lưu trong browser history, bookmark, log của reverse proxy/CDN/server, hệ thống analytics, công cụ giám sát lỗi, ảnh chụp màn hình và header Referer của một request tiếp theo. HTTPS mã hóa dữ liệu trên đường truyền; nó không che URL khỏi browser, endpoint nhận request hoặc các thành phần hạ tầng kết thúc TLS.

Bài học này tập trung vào việc nhận diện secret trong query, hiểu các đường rò rỉ và thiết kế lại luồng truyền credential. Quy tắc thực tế là không đặt credential hoặc dữ liệu nhạy cảm vào URL. Hãy dùng request body hoặc header phù hợp, giới hạn thời gian và phạm vi của token, redaction log, Referrer-Policy và luồng redirect làm sạch URL.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao query string có thể bị lộ qua history, log, Referer và analytics.
- Phân biệt URL query, fragment, request body và HTTP header.
- Hiểu cách Referrer-Policy quyết định giá trị Referer được gửi đi.
- Nhận diện password, token, API key, OTP, reset code và PII không nên đặt trong URL.
- Thiết kế lại API để truyền secret trong body hoặc Authorization header.
- Xử lý magic link và password-reset token an toàn trước link scanner.
- Hiểu vì sao OAuth authorization code có thể xuất hiện trong callback URL và cách giảm rủi ro.
- Làm sạch URL sau khi exchange secret mà không dựa vào redirect như biện pháp xóa log.
- Cấu hình Cache-Control, analytics và log redaction.
- Phản ứng khi secret đã bị ghi vào URL hoặc log.
- Kiểm thử các đường rò rỉ mà không dùng credential thật.

## 1. Query string hoạt động như thế nào?

Một URL có thể gồm scheme, authority, path, query và fragment:

~~~text
https://app.example.test/reset?token=SECRET_VALUE#confirm
\_________/ \________________/ \____________________/ \_______/
  scheme          authority             query          fragment
~~~

- Path xác định tài nguyên hoặc route.
- Query chứa các cặp tham số được gửi cùng request.
- Fragment được xử lý ở phía client và không được gửi trong HTTP request target thông thường.

Ví dụ:

~~~text
https://app.example.test/search?q=browser&page=2
~~~

Query phù hợp với dữ liệu không nhạy cảm như từ khóa tìm kiếm, bộ lọc hoặc số trang. Vấn đề bắt đầu khi query chứa credential hoặc dữ liệu mà người ngoài không được biết.

### 1.1 Query được gửi đến server

Với request HTTPS:

~~~http
GET /account?email=person%40example.test&token=SECRET_VALUE HTTP/1.1
Host: app.example.test
~~~

Server nhận request target có cả query. TLS mã hóa request trên đường truyền giữa các điểm kết nối TLS, nhưng server sau khi giải mã vẫn nhìn thấy URL đầy đủ. Reverse proxy, load balancer, WAF hoặc CDN kết thúc TLS cũng có thể nhìn thấy query.

Không nhầm việc URL được mã hóa trên đường truyền với việc URL được giữ bí mật trong toàn bộ hệ thống.

### 1.2 Query khác fragment

Ví dụ:

~~~text
https://app.example.test/callback?code=AUTH_CODE#access_token=TOKEN
~~~

- `code` nằm trong query nên được gửi đến server trong request target.
- `access_token` nằm trong fragment nên không được gửi trong HTTP request target.
- Fragment vẫn có thể được đọc bởi JavaScript cùng trang và có thể xuất hiện trong browser history, clipboard, ảnh chụp hoặc công cụ phía client.

Đưa token vào fragment không biến nó thành nơi lưu trữ an toàn. Các luồng OAuth implicit cũ từng trả access token trong fragment; ứng dụng mới nên dùng Authorization Code Flow với PKCE theo hướng dẫn bảo mật hiện hành.

## 2. Những nơi query chứa secret có thể bị lộ

Một secret trong URL có thể đi qua nhiều thành phần:

~~~text
Browser address bar / history
          |
          | GET /path?token=SECRET
          v
CDN / WAF / reverse proxy
          |
          | request target có query
          v
Application server / access log
          |
          +---- analytics / tracing / error reporting
          |
          +---- response HTML
                    |
                    | request đến tài nguyên khác
                    v
                Referer policy
~~~

### 2.1 Browser history và đồng bộ thiết bị

URL đầy đủ có thể xuất hiện trong:

- Address bar và browser history.
- Lịch sử được đồng bộ với tài khoản browser.
- Bookmark hoặc tab được khôi phục.
- Clipboard khi người dùng copy link.
- Ảnh chụp màn hình, quay màn hình hoặc bản ghi hỗ trợ.
- Extension có quyền đọc lịch sử hoặc tab URL.

Người khác dùng chung máy hoặc tài khoản browser có thể nhìn thấy URL cũ. Xóa query khỏi address bar sau khi tải trang không bảo đảm nó biến mất khỏi mọi bản sao đã được tạo.

### 2.2 Server và hạ tầng log

Nhiều hệ thống ghi request line hoặc URL đầy đủ vào:

- Web server access log.
- Reverse proxy và ingress log.
- CDN/WAF request log.
- API gateway.
- APM, distributed tracing và error reporting.
- SIEM hoặc hệ thống lưu log tập trung.

Ví dụ log nguy hiểm:

~~~text
GET /reset?token=eyJhbGciOi... HTTP/1.1 200
~~~

Một người có quyền đọc log có thể lấy token và sử dụng nó nếu token còn hiệu lực. Secret cũng có thể bị sao chép sang nhiều hệ thống lưu trữ với thời hạn retention khác nhau.

### 2.3 Referer header

Khi trang tải tài nguyên hoặc điều hướng sang trang khác, browser có thể gửi header `Referer` để cho biết URL nguồn.

Nếu URL nguồn chứa secret trong query, Referer có thể làm lộ giá trị đó tùy Referrer-Policy và quan hệ origin.

Với chính sách mặc định hiện đại `strict-origin-when-cross-origin`, hành vi thường là:

| Request tiếp theo | Referer thường được gửi |
|---|---|
| Cùng origin | URL nguồn đầy đủ, gồm path và query; không gồm fragment |
| Cross-origin cùng mức bảo mật | Chỉ origin, không gồm path/query |
| Điều hướng HTTPS xuống HTTP | Không gửi Referer |

Do đó, không nên giả định mọi request cross-origin đều nhận query. Nhưng request same-origin vẫn có thể mang URL đầy đủ, và chính sách có thể bị thay đổi bởi document, element hoặc cấu hình browser.

`unsafe-url` có thể gửi URL nguồn đầy đủ cả khi request cross-origin. Tránh dùng chính sách này trên trang có dữ liệu nhạy cảm.

### 2.4 Analytics và third-party script

Analytics có thể thu thập `location.href`, page URL, campaign parameters hoặc query string. Công cụ session replay và error reporting cũng có thể ghi URL.

Third-party script chạy trong trang thường có quyền đọc `window.location` của chính trang. Dù Referrer-Policy chỉ gửi origin cho request cross-origin, script đã được tải vẫn có thể đọc query rồi gửi dữ liệu đi qua request riêng.

Vì vậy, chỉ đặt `Referrer-Policy` không đủ nếu trang chứa secret trong URL và tải script bên thứ ba.

### 2.5 Cache và hệ thống trung gian

URL là một phần của request cache key trong nhiều hệ thống. Browser cache, CDN hoặc proxy có thể lưu metadata request/response liên quan đến URL.

Với response chứa credential hoặc trang xử lý secret, hãy cân nhắc `Cache-Control: no-store`, cấu hình cache bypass tại CDN và không đưa response đó vào Service Worker Cache Storage.

`no-store` giảm nguy cơ lưu response trong cache HTTP theo quy tắc cache, nhưng không xóa browser history, access log hoặc analytics đã thu thập URL.

## 3. Loại dữ liệu nào không nên đặt trong query?

| Dữ liệu | Ví dụ | Rủi ro |
|---|---|---|
| Password | `?password=...` | Lộ credential đăng nhập |
| Access token | `?access_token=...` | Người khác có thể gọi API bằng bearer token |
| Refresh token | `?refresh_token=...` | Có thể duy trì quyền truy cập lâu dài |
| API key | `?api_key=...` | Lộ quyền truy cập dịch vụ |
| OTP | `?otp=123456` | Có thể bị dùng trước khi hết hạn |
| Password-reset token | `?token=...` | Chiếm quyền đặt lại mật khẩu |
| Magic-link token | `?login_token=...` | Có thể đăng nhập thay người dùng |
| Session ID | `?sid=...` | Session hijacking |
| PII nhạy cảm | email, số điện thoại, mã hồ sơ | Lộ dữ liệu cá nhân qua log/history |

Không phải mọi query parameter đều là secret. `page=3`, `sort=price` hoặc bộ lọc công khai thường có thể nằm trong URL. Hãy phân loại dữ liệu theo tác động nếu người khác nhìn thấy hoặc replay được giá trị.

### 3.1 Bearer token đặc biệt nguy hiểm

Bearer token cấp quyền cho bất kỳ ai nắm giữ token. Nếu token xuất hiện trong URL, người đọc URL có thể sử dụng nó cho đến khi token hết hạn hoặc bị thu hồi.

Không đặt Bearer token trong query, kể cả khi:

- URL dùng HTTPS.
- Token có thời hạn ngắn.
- URL chỉ được gửi qua POST redirect ở một bước.
- Token được mã hóa hoặc Base64URL encode.

Encoding không phải encryption. Hãy truyền access token trong `Authorization: Bearer ...` qua TLS hoặc dùng kiến trúc BFF để giữ token phía server.

### 3.2 Không dùng GET để thay đổi trạng thái

GET URL dễ bị lưu, prefetch, crawl, cache hoặc mở lại. Không dùng GET để thực hiện hành động nhạy cảm như:

- Đổi email hoặc password.
- Xác nhận thanh toán.
- Xóa tài khoản.
- Tiêu thụ OTP.
- Hoàn tất password reset.
- Đăng xuất theo cách thay đổi trạng thái quan trọng.

Dùng POST hoặc phương thức phù hợp, có CSRF protection và xác minh quyền ở server. Chuyển sang POST không tự động chống CSRF; cookie vẫn có thể được browser gửi tự động.

## 4. Referrer-Policy giảm rò rỉ như thế nào?

`Referrer-Policy` kiểm soát thông tin được đưa vào header `Referer` của request phát sinh từ document hoặc element.

Header có thể được cấu hình ở response:

~~~http
Referrer-Policy: strict-origin-when-cross-origin
~~~

Các giá trị thường gặp:

| Policy | Same-origin | Cross-origin | HTTPS xuống HTTP |
|---|---|---|---|
| `no-referrer` | Không gửi | Không gửi | Không gửi |
| `same-origin` | URL nguồn đầy đủ | Không gửi | Không gửi |
| `origin` | Chỉ origin | Chỉ origin | Chỉ origin |
| `strict-origin` | Chỉ origin | Chỉ origin | Không gửi |
| `origin-when-cross-origin` | URL đầy đủ | Chỉ origin | Chỉ origin |
| `strict-origin-when-cross-origin` | URL đầy đủ | Chỉ origin | Không gửi |
| `no-referrer-when-downgrade` | URL đầy đủ | URL đầy đủ | Không gửi |
| `unsafe-url` | URL đầy đủ | URL đầy đủ | URL đầy đủ |

Browser hiện đại thường mặc định `strict-origin-when-cross-origin`, nhưng ứng dụng nên cấu hình rõ chính sách phù hợp thay vì dựa vào mặc định.

### 4.1 Cấu hình no-referrer

Nếu trang xử lý reset token hoặc magic link và không cần gửi Referer cho request tiếp theo:

~~~http
Referrer-Policy: no-referrer
~~~

Có thể dùng meta element:

~~~html
<meta name="referrer" content="no-referrer">
~~~

Header response thường là lựa chọn rõ ràng ở cấp trang. Meta policy cần xuất hiện sớm trong document; không chờ đến khi các tài nguyên hoặc script khác đã được tải.

### 4.2 Cấu hình theo link

Một link có thể yêu cầu không gửi Referer:

~~~html
<a href="https://external.example.test/" rel="noreferrer">
  Mở website bên ngoài
</a>
~~~

`noreferrer` ngăn gửi Referer cho navigation đó và trong browser hiện đại cũng ngụ ý hành vi tương đương `noopener` cho liên kết.

Đây là biện pháp theo từng link. Nó không thay thế chính sách toàn trang và không ngăn server nhận URL query ban đầu.

### 4.3 Referrer-Policy không xóa secret khỏi URL

Nếu trang được mở tại:

~~~text
https://app.example.test/reset?token=SECRET
~~~

`Referrer-Policy: no-referrer` chỉ kiểm soát header Referer cho request phát sinh. Nó không xóa token khỏi:

- Request đầu tiên đến `app.example.test`.
- Browser history hoặc address bar.
- CDN, proxy và server access log.
- Analytics/script đã đọc `location.href`.
- Screenshot, clipboard hoặc bản ghi hỗ trợ.

Cần loại secret khỏi URL và xử lý các nơi đã ghi nhận nó. Referrer-Policy là một lớp giảm rò rỉ, không phải giải pháp chính cho secret trong query.

## 5. Chuyển secret sang body hoặc header

Thay vì:

~~~http
GET /api/profile?access_token=SECRET HTTP/1.1
Host: api.example.test
~~~

Dùng:

~~~http
GET /api/profile HTTP/1.1
Host: api.example.test
Authorization: Bearer SECRET
~~~

Với dữ liệu nhạy cảm được gửi trong body:

~~~http
POST /api/password/reset HTTP/1.1
Host: app.example.test
Content-Type: application/json
Cache-Control: no-store
X-CSRF-Token: CSRF_VALUE

{
  "resetToken": "ONE_TIME_SECRET",
  "newPassword": "NEW_PASSWORD"
}
~~~

Body và header không xuất hiện trong browser address bar hoặc Referer URL. Tuy nhiên, proxy/APM có thể log body hoặc Authorization header nếu được cấu hình. Vẫn cần:

- TLS.
- Log redaction.
- Không cache response nhạy cảm.
- Giới hạn quyền truy cập log.
- Retention ngắn.
- Không gửi credential đến third-party telemetry.

### 5.1 Khi nào dùng header?

- `Authorization`: credential dùng để xác thực request.
- CSRF header: bằng chứng anti-CSRF theo thiết kế ứng dụng.
- Header riêng cho API key trong hệ thống server-to-server nếu giao thức cho phép.

Không đưa secret vào custom header nếu browser API không cho phép đặt header đó, ví dụ WebSocket constructor. Với browser application, hãy chọn giao thức hỗ trợ hoặc dùng BFF.

### 5.2 Khi nào dùng body?

Body phù hợp cho POST/PUT/PATCH khi gửi dữ liệu nhạy cảm hoặc thao tác thay đổi trạng thái.

Không dùng GET body như một cách thay query: hỗ trợ và ngữ nghĩa của GET body không nhất quán, proxy có thể xử lý khác nhau. Dùng method có contract rõ ràng.

### 5.3 Body cũng cần được bảo vệ

POST body không tự động an toàn. Nếu log middleware ghi request body, secret vẫn có thể bị lộ. Nếu endpoint không có CSRF protection, website khác vẫn có thể tạo request cookie-authenticated trong một số ngữ cảnh.

Hãy redact trường nhạy cảm trước khi ghi log và xác minh quyền ở server.

## 6. Password-reset và magic-link token

Password-reset và magic-link thường cần một liên kết mà người dùng có thể mở từ email. Điều này tạo áp lực phải đặt một token vào URL, nhưng token cần được thiết kế như credential dùng một lần, thời hạn ngắn và phạm vi hẹp.

### 6.1 Rủi ro của reset link

Một reset link có thể bị lộ qua:

- Email forwarding hoặc mailbox compromise.
- Link preview và security scanner.
- Browser history.
- Proxy/CDN/server logs.
- Referer nếu trang tải tài nguyên hoặc điều hướng không an toàn.
- Analytics hoặc third-party script.
- Screenshot và clipboard.

### 6.2 Dùng token ngẫu nhiên, một lần và giới hạn mục đích

Reset token nên:

- Được sinh từ cryptographically secure random generator.
- Có entropy đủ cao.
- Chỉ dùng cho một user và một hành động cụ thể.
- Có expiration ngắn theo risk policy.
- Được lưu dạng hash phía server nếu kiến trúc cho phép.
- Chỉ được tiêu thụ một lần.
- Bị vô hiệu hóa sau khi password được đổi hoặc token bị revoke.

Không dùng access token hoặc session token thông thường làm reset token.

### 6.3 GET hiển thị trang, POST mới tiêu thụ token

Email security scanner có thể tự động mở link để kiểm tra phishing hoặc malware. Nếu GET request lập tức đổi password, xác nhận giao dịch hoặc đăng nhập người dùng, scanner có thể vô tình tiêu thụ token.

Một luồng phù hợp hơn:

~~~text
Người dùng mở email link
        |
        v
GET /reset?token=ONE_TIME_CODE
        |
        v
Server kiểm tra token và hiển thị trang tối giản
        |
        v
Người dùng nhập password mới
        |
        v
POST /reset/complete
Body: token + new password + CSRF proof
        |
        v
Server xác minh lại và tiêu thụ token nguyên tử
        |
        v
Đổi password, revoke phiên phù hợp
        |
        v
Redirect đến URL sạch
~~~

GET chỉ hiển thị trang xác nhận và không thay đổi trạng thái. POST mới thực hiện hành động sau khi người dùng chủ động xác nhận.

### 6.4 Làm sạch URL sớm

Sau khi server xác minh token và tạo một flow ngắn hạn an toàn, có thể chuyển browser đến URL sạch bằng redirect:

~~~http
HTTP/1.1 303 See Other
Location: /reset/confirm
Cache-Control: no-store
Referrer-Policy: no-referrer
~~~

Nếu SPA phải xử lý ở client, có thể dùng `history.replaceState()` sau khi đã exchange token. Tuy nhiên, redirect phía server thường tốt hơn vì secret được loại khỏi URL trước khi tải trang chính và third-party resource.

Không coi redirect là xóa log. Request URL ban đầu vẫn có thể đã được ghi tại CDN, proxy hoặc server.

## 7. OAuth authorization code trong query

OAuth Authorization Code Flow thường trả authorization code về redirect URI qua query parameter:

~~~text
https://client.example.test/callback?code=AUTH_CODE&state=RANDOM_STATE
~~~

Đây là trường hợp đặc biệt được giao thức thiết kế. Authorization code không phải access token và cần được bảo vệ bằng nhiều lớp.

### 7.1 Vì sao authorization code có thể xuất hiện trong URL?

Browser được redirect về callback URL. Client hoặc backend dùng code để đổi lấy token tại token endpoint.

Code cần:

- Có lifetime ngắn.
- Chỉ dùng một lần.
- Gắn với client và redirect URI.
- Không thể đổi bởi một client không hợp lệ.
- Được bảo vệ bằng PKCE cho public clients.
- Được ràng buộc với `state` để chống CSRF trong luồng redirect theo thiết kế OAuth/OIDC.

### 7.2 PKCE không làm URL code trở thành dữ liệu công khai an toàn

PKCE làm cho kẻ chỉ lấy được authorization code nhưng không có `code_verifier` khó đổi code thành token. Nhưng code vẫn là dữ liệu nhạy cảm cần bảo vệ.

Không ghi code vào log, không gửi code sang analytics và không tải third-party script trên callback trước khi xử lý.

### 7.3 Callback page tối giản

Một callback page nên:

1. Đọc code và state.
2. Xác minh state và luồng đăng nhập.
3. Exchange code qua token endpoint, tốt nhất qua backend/BFF nếu kiến trúc dùng BFF.
4. Không tải analytics, quảng cáo hoặc script bên thứ ba trước khi xử lý code.
5. Redirect đến URL sạch.
6. Dùng `Cache-Control: no-store` và Referrer-Policy chặt chẽ.

Không đưa access token hoặc refresh token vào query. Tránh implicit flow trả access token trong fragment; dùng Authorization Code Flow với PKCE.

### 7.4 Không log callback URL

Đặt quy tắc redaction cho query parameter `code`, `state`, `error_description` và các giá trị nhạy cảm khác. `state` không phải access token nhưng vẫn là dữ liệu của transaction đăng nhập và không nên xuất hiện trong log không cần thiết.

## 8. URL sạch và redirect an toàn

Sau khi exchange một secret, ứng dụng nên chuyển người dùng đến URL không còn credential.

Ví dụ:

~~~js
// Chỉ là ví dụ client-side sau khi code đã được xử lý thành công.
history.replaceState(null, "", "/account");
~~~

`replaceState()` thay URL hiện tại trong history entry của trang. Nó không xóa request log, Referer đã gửi, extension đã đọc URL hoặc bản sao trong hệ thống quan sát.

### 8.1 Redirect không được tạo open redirect

Nếu redirect target lấy từ query như `?next=...`, server phải kiểm tra đích:

- Chỉ cho phép relative path nội bộ hoặc allowlist origin cụ thể.
- Từ chối scheme nguy hiểm hoặc URL bên ngoài không được phép.
- Không ghép chuỗi URL tùy tiện.
- Không chuyển secret sang một URL đích khác.

Một open redirect có thể khiến người dùng tin domain ban đầu rồi bị chuyển sang website độc hại, đồng thời làm phức tạp việc rò rỉ query.

### 8.2 Không đưa secret vào Location header

Header `Location` có thể chứa URL đích và được proxy/server log. Nếu redirect cần mang state, hãy dùng một mã tham chiếu ngắn hạn, dùng một lần và không có quyền độc lập, rồi exchange ở server.

Không chuyển nguyên query chứa token sang trang tiếp theo.

## 9. Cache, logging và analytics

### 9.1 Cache-Control cho trang xử lý secret

Với reset page, callback hoặc response chứa thông tin xác thực:

~~~http
Cache-Control: no-store
Pragma: no-cache
Referrer-Policy: no-referrer
X-Content-Type-Options: nosniff
~~~

`no-store` hướng dẫn cache không lưu response. Nó không xóa request URL khỏi access log và không bảo vệ khỏi script đã chạy trong trang.

### 9.2 Redact ở mọi tầng

Cấu hình redaction cho các trường hoặc query key như:

- `token`
- `access_token`
- `refresh_token`
- `code`
- `password`
- `otp`
- `api_key`
- `reset_token`
- `login_token`
- `session`

Không chỉ redact ở application log. Kiểm tra CDN, WAF, ingress, reverse proxy, API gateway, APM, tracing, analytics và crash reporting.

Ưu tiên allowlist các trường được phép log thay vì ghi toàn bộ URL rồi cố gắng xóa mọi secret đã biết.

### 9.3 Analytics chỉ nhận URL đã làm sạch

Không gửi `location.href` nguyên bản lên analytics nếu URL có thể chứa secret hoặc PII. Tạo page identifier sạch:

~~~js
const safePage = window.location.origin + window.location.pathname;

analytics.track("page_view", {
  page: safePage
});
~~~

Nếu query chứa bộ lọc không nhạy cảm và sản phẩm cần phân tích, chỉ cho phép các key đã được duyệt và loại bỏ giá trị không cần thiết. Không dùng một regex chung để cố phát hiện tất cả secret.

### 9.4 Error reporting và session replay

Trước khi gửi telemetry:

- Loại Authorization header, cookie và request body nhạy cảm.
- Redact URL query theo allowlist.
- Che form field chứa password/OTP.
- Không capture reset/magic-link page nếu không cần.
- Giới hạn người có quyền truy cập bản ghi replay.
- Đặt retention phù hợp.

## 10. Xử lý khi secret đã bị lộ trong URL

Nếu phát hiện access token, reset token hoặc API key đã xuất hiện trong URL/log:

1. Xác định loại secret, phạm vi quyền và thời điểm bị lộ.
2. Thu hồi hoặc rotate secret nếu có thể.
3. Invalidate session/token family liên quan theo policy.
4. Xác định các hệ thống đã nhận URL: CDN, proxy, application log, APM, analytics, browser history.
5. Hạn chế quyền truy cập log và xóa/expire bản sao theo quy trình retention.
6. Kiểm tra access log để tìm request sử dụng lại token bất thường.
7. Sửa luồng để secret không còn nằm trong URL.
8. Thêm redaction và test hồi quy.
9. Thông báo incident theo quy trình tổ chức nếu có dữ liệu người dùng bị ảnh hưởng.

Không chỉ xóa URL khỏi browser history rồi coi incident đã được xử lý. Nếu token còn hiệu lực, cần ưu tiên revoke/rotate.

## 11. Ví dụ thiết kế trước và sau

### 11.1 API tìm kiếm

Trước:

~~~text
GET /search?query=browser&api_key=SECRET
~~~

Sau:

~~~http
GET /search?query=browser HTTP/1.1
Authorization: Bearer SECRET
~~~

API key dài hạn không nên được nhúng vào browser client. Nếu browser cần truy cập API, cân nhắc BFF hoặc credential giới hạn quyền.

### 11.2 Password reset

Trước:

~~~text
GET /reset?token=LONG_LIVED_TOKEN&new_password=...
~~~

Sau:

~~~text
GET /reset?token=SHORT_LIVED_ONE_TIME_CODE
  -> trang xác nhận tối giản, không consume token

POST /reset/complete
  body: one-time code + new password + CSRF proof
  -> server consume token nguyên tử, đổi password, revoke session
  -> redirect URL sạch
~~~

GET không làm thay đổi trạng thái. POST yêu cầu người dùng chủ động xác nhận và có CSRF protection.

### 11.3 OAuth callback

Callback query có thể chứa authorization code theo giao thức:

~~~text
GET /oauth/callback?code=SHORT_LIVED_CODE&state=TRANSACTION_STATE
~~~

Backend/BFF xác minh state, đổi code bằng PKCE-bound transaction và redirect đến URL sạch. Không để callback page tải analytics hoặc third-party script trước khi exchange.

## 12. Kiểm thử Query chứa secret

Chỉ dùng token giả lập trên môi trường lab. Không copy secret thật vào URL test hoặc screenshot.

### 12.1 Kiểm tra Referer

Tạo trang lab:

~~~text
https://app.example.test/demo?token=FAKE_SECRET_123
~~~

Từ trang đó tải một tài nguyên same-origin và một tài nguyên cross-origin. Quan sát header Referer ở server lab.

So sánh các policy:

- `strict-origin-when-cross-origin`
- `no-referrer`
- `same-origin`
- `unsafe-url`

Xác nhận query có thể xuất hiện trong Referer same-origin nhưng không xuất hiện trong cross-origin theo policy mặc định hiện đại.

### 12.2 Kiểm tra server/proxy logs

Gửi request có fake token trong query. Kiểm tra:

- CDN/WAF log.
- Reverse proxy access log.
- Application access log.
- APM/tracing.
- Analytics event.

Xác định tầng nào đang ghi full URL và bật redaction.

### 12.3 Kiểm tra redirect làm sạch

Mở reset link lab có fake token. Xác nhận:

- Trang xử lý không tải third-party script.
- Token không được gửi sang analytics.
- Server không consume token chỉ vì GET.
- Sau khi exchange/submit thành công, browser đến URL sạch.
- Log vẫn được redact cho request ban đầu.

### 12.4 Kiểm tra cache

Xác nhận reset/callback response có `Cache-Control: no-store`. Kiểm tra Service Worker fetch handler không đưa response chứa secret vào Cache Storage.

### 12.5 Kiểm tra OAuth callback

Dùng authorization code giả lập và transaction PKCE lab. Xác nhận code chỉ dùng một lần, state được kiểm tra, callback không tải third-party resource và URL được làm sạch sau exchange.

## 13. Lỗi triển khai thường gặp

### 13.1 Nghĩ HTTPS làm query bí mật

TLS bảo vệ đường truyền, không che URL khỏi browser, server, proxy kết thúc TLS hoặc log.

### 13.2 Chỉ đặt Referrer-Policy rồi giữ token trong URL

Referrer-Policy không xóa history, access log, analytics hoặc URL request đầu tiên. Hãy loại secret khỏi URL.

### 13.3 Cho rằng cross-origin luôn nhận full Referer

Default hiện đại thường chỉ gửi origin cho cross-origin request cùng mức bảo mật. Nhưng same-origin request có thể nhận URL đầy đủ và policy khác có thể nới lỏng. Hãy kiểm tra chính sách thực tế.

### 13.4 Dùng fragment để giấu token

Fragment không gửi đến server trong request thông thường, nhưng vẫn có thể bị JavaScript, history, extension hoặc telemetry đọc. Không dùng fragment làm kho credential.

### 13.5 Dùng GET để tiêu thụ reset link

Link scanner có thể tự động mở URL. GET không nên thực hiện hành động thay đổi trạng thái hoặc tiêu thụ token.

### 13.6 Redirect rồi nghĩ log đã sạch

Request ban đầu vẫn có thể đã được log. Redact tại mọi tầng và revoke secret nếu đã lộ.

### 13.7 Đưa secret vào analytics để debug

Không gửi raw URL hoặc token vào analytics, tracing, replay hay crash report. Dùng ID tham chiếu không có quyền truy cập và dữ liệu đã redact.

### 13.8 Chuyển secret sang POST nhưng log body

Body cũng có thể bị log. Cấu hình redaction và giới hạn quyền đọc log.

### 13.9 Dùng wildcard cho Referrer-Policy

`unsafe-url` có thể gửi full URL cross-origin. Chọn policy tối thiểu cần thiết, thường là `no-referrer` cho trang xử lý secret.

### 13.10 Cho phép redirect tùy ý

`next` hoặc `returnUrl` có thể bị lợi dụng làm open redirect. Validate đích và không mang secret sang URL mới.

## 14. Quy trình review URL chứa secret

Trước khi đưa luồng lên production:

1. Liệt kê mọi query parameter và phân loại dữ liệu.
2. Xác định secret nào đang được gửi qua URL.
3. Chuyển credential sang Authorization header hoặc POST body phù hợp.
4. Dùng token ngẫu nhiên, ngắn hạn, một lần và gắn đúng mục đích khi cần link-based flow.
5. Không tiêu thụ reset/magic token chỉ bằng GET.
6. Dùng Authorization Code Flow với PKCE; không đưa access/refresh token vào query.
7. Đặt Referrer-Policy chặt chẽ cho callback/reset page.
8. Không tải third-party script trước khi xử lý secret và làm sạch URL.
9. Dùng redirect server-side đến URL sạch sau exchange.
10. Đặt Cache-Control: no-store cho response nhạy cảm.
11. Redact query, header và body ở CDN/proxy/server/APM/analytics.
12. Không ghi raw URL vào telemetry hoặc session replay.
13. Xác thực CSRF cho cookie-authenticated POST.
14. Kiểm tra open redirect và redirect chain.
15. Có quy trình revoke/rotate khi secret bị lộ.
16. Kiểm thử Referer, history, logs, cache và multi-hop navigation.

## 15. Checklist review Query chứa secret

- [ ] Không có password, access token, refresh token, API key hoặc session ID trong query.
- [ ] OTP, reset token và magic-link token có lifetime ngắn và chỉ dùng một lần.
- [ ] Secret được truyền qua body hoặc header phù hợp.
- [ ] Không dùng GET để thay đổi trạng thái hoặc tiêu thụ token.
- [ ] Reset/magic link không bị tiêu thụ bởi GET/link scanner.
- [ ] OAuth callback dùng authorization code ngắn hạn và PKCE.
- [ ] Không dùng implicit flow để trả access token trong fragment.
- [ ] Referrer-Policy được cấu hình rõ ràng.
- [ ] Trang xử lý secret dùng `no-referrer` nếu phù hợp.
- [ ] Không tải third-party script trước khi exchange và làm sạch URL.
- [ ] Redirect đến URL sạch không chuyển secret sang đích khác.
- [ ] Redirect target được allowlist để tránh open redirect.
- [ ] Response nhạy cảm dùng `Cache-Control: no-store`.
- [ ] Service Worker không cache token/callback response.
- [ ] CDN, WAF, proxy, app server và APM đều redact query nhạy cảm.
- [ ] Analytics và session replay không thu thập raw URL hoặc token.
- [ ] Request body và Authorization header cũng được redact trong log.
- [ ] Có CSRF protection cho endpoint dùng cookie.
- [ ] Có quy trình revoke/rotate nếu secret đã bị lộ.
- [ ] Đã kiểm thử same-origin và cross-origin Referer behavior.
- [ ] Đã kiểm tra browser history, redirect và log trong môi trường lab.

## 16. Bài thực hành

Thực hiện trong ứng dụng lab do bạn kiểm soát. Chỉ dùng fake token, không đưa credential thật vào URL.

### Bài 1: Quan sát query leakage

Tạo URL có `token=FAKE_SECRET`. Gửi request qua CDN/proxy lab và kiểm tra tầng nào ghi full URL. Ghi nhận các điểm cần redaction.

### Bài 2: So sánh Referrer-Policy

Tạo trang có query giả lập và tải tài nguyên same-origin/cross-origin. Thử `no-referrer`, `same-origin`, `strict-origin-when-cross-origin` và `unsafe-url`. So sánh header Referer.

### Bài 3: Chuyển API key khỏi query

Sửa endpoint lab từ `?api_key=...` sang Authorization header hoặc BFF. Xác nhận API log không còn credential trong request target.

### Bài 4: Reset token và link scanner

Tạo reset token một lần. Mô phỏng scanner gửi GET nhiều lần. Xác nhận token chỉ được tiêu thụ sau POST xác nhận của người dùng.

### Bài 5: Làm sạch URL

Sau khi exchange token lab, redirect server-side đến URL sạch. Xác nhận trang đích không nhận secret qua Referer và log đã redact request ban đầu.

### Bài 6: OAuth callback

Tạo callback lab có code/state giả lập. Kiểm tra state, PKCE exchange, one-time code và redirect sạch. Xác nhận callback không tải third-party analytics trước khi xử lý.

### Bài 7: Cache và Service Worker

Cấu hình response nhạy cảm `Cache-Control: no-store`. Kiểm tra browser cache và Service Worker Cache Storage không lưu response token.

### Bài 8: Incident response

Giả lập fake token bị ghi vào access log. Thực hiện revoke token, tìm bản sao log, xác nhận redaction và viết quy trình xử lý cho lần sau.

## 17. Câu hỏi tự kiểm tra

**1. Vì sao secret trong query có thể bị lộ dù URL dùng HTTPS?**

HTTPS chỉ mã hóa dữ liệu trên đường truyền. Browser, server nhận request, proxy kết thúc TLS và hệ thống log vẫn có thể nhìn thấy URL.

**2. Query khác fragment như thế nào?**

Query được gửi trong HTTP request target; fragment không được gửi trong request thông thường nhưng vẫn có thể được JavaScript và browser history đọc.

**3. Default `strict-origin-when-cross-origin` gửi gì?**

Thường gửi URL đầy đủ cho same-origin request, chỉ gửi origin cho cross-origin request cùng mức bảo mật và không gửi khi downgrade HTTPS xuống HTTP.

**4. Referrer-Policy có xóa query khỏi browser history không?**

Không. Nó chỉ kiểm soát thông tin trong Referer header của request phát sinh.

**5. Nên truyền access token qua đâu?**

Qua Authorization header trên TLS hoặc giữ token phía server bằng BFF; không đặt token trong URL.

**6. Vì sao reset token không nên bị tiêu thụ bằng GET?**

Email security scanner hoặc link preview có thể tự động mở link. GET nên chỉ hiển thị trang; POST sau xác nhận mới tiêu thụ token.

**7. OAuth authorization code có thể nằm trong query không?**

Có, theo Authorization Code Flow. Code phải ngắn hạn, dùng một lần, gắn với redirect URI/client và được bảo vệ bằng PKCE/state.

**8. `history.replaceState()` có xóa secret khỏi server log không?**

Không. Nó chỉ thay URL trong history entry hiện tại của browser.

**9. Chuyển secret sang POST body có đủ an toàn không?**

Không. Cần TLS, CSRF protection khi dùng cookie, log redaction, cache policy và kiểm soát quyền truy cập telemetry.

**10. Khi phát hiện token trong URL log, cần làm gì trước?**

Đánh giá phạm vi, revoke/rotate token nếu còn hiệu lực, hạn chế truy cập và xử lý bản sao log, sau đó sửa luồng và thêm redaction.

## Ghi nhớ

Query string phù hợp với tham số điều hướng không nhạy cảm, không phải nơi lưu credential. Secret trong URL có thể xuất hiện ở history, request logs, analytics và Referer; HTTPS hay redirect không xóa các bản sao đó. Hãy chuyển secret sang body/header hoặc BFF, dùng token ngắn hạn một lần cho link-based flow, cấu hình Referrer-Policy và no-store, redaction ở mọi tầng, rồi kiểm thử các đường rò rỉ thực tế.

## Tài liệu tham khảo

- [RFC 9110: HTTP Semantics — Referer](https://www.rfc-editor.org/rfc/rfc9110.html)
- [W3C: Referrer Policy](https://www.w3.org/TR/referrer-policy/)
- [MDN: Referrer-Policy header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy)
- [MDN: Referer header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referer)
- [RFC 6749: OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html)
- [RFC 7636: Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636.html)
- [RFC 9700: Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html)
- [OWASP: Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [OWASP: REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [OWASP: Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
