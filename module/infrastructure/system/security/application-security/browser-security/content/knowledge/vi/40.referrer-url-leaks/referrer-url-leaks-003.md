# URL trong history

> **Chương:** Referrer và URL leak  
> **Chủ đề:** URL trong history  
> **Module:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly. Thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân tích URL nào được lưu trong browser history và thành phần nào được gửi tới server.
2. Phân biệt rủi ro của path, query string và fragment.
3. Nhận diện dữ liệu nhạy cảm có thể lộ qua history, autocomplete, bookmark, đồng bộ browser, log và Referer.
4. Giải thích giới hạn của `history.replaceState()` và `location.replace()`.
5. Thiết kế link xác thực, reset password và invitation không để lộ credential lâu dài trong URL.
6. Dùng Referrer-Policy, `referrerpolicy`, `rel="noreferrer"` và Cache-Control để giảm rò rỉ.
7. Làm sạch URL sau khi xử lý callback mà vẫn giữ đúng trạng thái điều hướng.
8. Kiểm tra URL/history leakage bằng lab local với dữ liệu giả.

## 1. Vì sao URL trong history là vấn đề privacy?

Browser history lưu các trang mà người dùng đã truy cập để hỗ trợ Back, Forward, khôi phục tab và gợi ý điều hướng. Một URL thường chứa path, query string và fragment. Nếu ứng dụng đặt thông tin nhạy cảm vào URL, thông tin đó có thể tồn tại lâu hơn thời gian request cần thiết.

Ví dụ URL có thể chứa:

- Từ khóa tìm kiếm hoặc nội dung người dùng vừa nhập.
- Email, số điện thoại, mã khách hàng hoặc ID hồ sơ.
- Token reset mật khẩu, magic-link token hoặc invitation code.
- Authorization code, `state` hoặc tham số xác thực trong callback.
- Session identifier, access token hoặc thông tin định danh chiến dịch.

URL có thể xuất hiện trong address bar, browser history, gợi ý autocomplete, bookmark, bản sao clipboard, screenshot, browser sync, extension và log ở nhiều lớp hạ tầng. Một số dữ liệu cũng có thể được gửi tới destination qua Referer.

Không phải mọi URL đều được đồng bộ hoặc lưu vĩnh viễn theo cùng cách. Browser, cài đặt tài khoản, private browsing, extension và chính sách thiết bị quyết định hành vi cụ thể. Thiết kế an toàn phải giả định URL có thể được lưu, sao chép hoặc quan sát bởi nhiều thành phần ngoài ứng dụng.

## 2. Path, query và fragment khác nhau thế nào?

Một URL có dạng tổng quát:

```text
https://app.example.test/account/reset?token=opaque-value&lang=vi#confirm
        scheme   host             path       query                 fragment
```

| Thành phần | Ví dụ | Gửi trong HTTP request? | Có thể xuất hiện trong history? |
|---|---|---:|---:|
| Scheme/host | https://app.example.test | Được dùng để xác định đích kết nối | Có |
| Path | /account/reset | Có | Có |
| Query | ?token=opaque-value&lang=vi | Có, trong request target | Có |
| Fragment | #confirm | Không gửi trong HTTP request | Có |

### 2.1. Query string

Query string được browser gửi cùng request target tới server. Vì vậy, query có thể xuất hiện trong access log của web server, reverse proxy, CDN, WAF, APM và hệ thống analytics nếu các lớp đó ghi URL đầy đủ.

Ví dụ:

```http
GET /account/reset?token=demo-reset-token HTTP/1.1
Host: app.example.test
```

Ngay cả khi response đặt `Cache-Control: no-store`, request URL vẫn đã được gửi và có thể được log. `no-store` điều khiển cache, không xóa request khỏi log hoặc browser history.

### 2.2. Fragment

Fragment bắt đầu bằng dấu #. Browser không gửi fragment trong HTTP request tới server. Tuy vậy, fragment vẫn được lưu trong URL history và JavaScript cùng trang có thể đọc qua `location.hash` hoặc `location.href`.

Fragment cũng có thể lộ qua:

- Script first-party hoặc third-party chạy trong trang.
- Extension có quyền đọc URL/tab.
- Browser history, bookmark, clipboard và screenshot.
- JavaScript telemetry nếu ứng dụng gửi toàn bộ `location.href`.

Một số flow cũ từng đặt access token trong fragment để tránh token xuất hiện trong HTTP request. Cách này vẫn để token trong URL phía browser và có nguy cơ bị script cùng trang đọc. Với ứng dụng mới, không dùng implicit flow để đưa access token vào fragment; ưu tiên Authorization Code Flow với PKCE và thiết kế token handling phù hợp.

### 2.3. User information và dữ liệu trong path

Không đặt mật khẩu hoặc credential trong URL userinfo như `https://user:password@example.test/`; browser có thể loại bỏ hoặc xử lý khác nhau và URL vẫn có thể bị sao chép/log.

Path cũng có thể nhạy cảm. Ví dụ `/patients/12345/diagnosis` có thể để lộ thông tin cá nhân qua log, history hoặc Referer ngay cả khi không có query string. Dùng opaque identifier khi phù hợp và không đưa dữ liệu nhạy cảm trực tiếp vào path.

## 3. Browser history lưu gì?

Browser history thường lưu URL của các navigation entry. URL có thể gồm path, query và fragment. History API cũng cho phép ứng dụng tạo hoặc thay đổi entry trong cùng document.

Các API thường gặp:

| API | Hành vi | Ảnh hưởng tới history |
|---|---|---|
| `history.pushState(state, title, url)` | Tạo history entry mới trong cùng origin, không tải document mới | Giữ URL mới thành entry hiện tại |
| `history.replaceState(state, title, url)` | Thay URL/state của entry hiện tại, không tải document mới | Thay entry hiện tại |
| `history.back()` / `history.forward()` | Điều hướng qua entry liền trước/sau | Di chuyển vị trí hiện tại trong history |
| `location.assign(url)` | Điều hướng tới URL mới | Thêm navigation entry thông thường |
| `location.replace(url)` | Điều hướng tới URL mới và thay entry hiện tại | Không giữ entry hiện tại như một bước Back riêng |

URL truyền vào `pushState()` hoặc `replaceState()` phải cùng origin với document. Các API này không gửi request mạng khi chỉ thay đổi URL trong history; chúng không phải cơ chế xóa log server.

### 3.1. History có thể tồn tại sau khi phiên ứng dụng kết thúc

Người dùng có thể:

- Mở lại trang từ history sau nhiều giờ hoặc nhiều ngày.
- Khôi phục tab sau khi browser crash hoặc restart.
- Đồng bộ history giữa các thiết bị nếu bật browser sync.
- Chia sẻ URL bằng bookmark, clipboard hoặc ứng dụng chat.
- Dùng browser autocomplete để gợi ý URL từng truy cập.

Private browsing thường không ghi history vào profile thông thường sau khi đóng phiên private, nhưng trong lúc cửa sổ private còn mở, URL vẫn hiện trong address bar và có thể được quan sát bởi website, extension được phép hoặc phần mềm trên thiết bị. Không coi private mode là biện pháp bảo vệ URL chứa secret.

### 3.2. Back/Forward Cache không phải browser history

Back/Forward Cache (bfcache) có thể giữ snapshot của document để khôi phục nhanh khi người dùng quay lại. Đây là cơ chế khác với danh sách history URL. Một trang được khôi phục từ bfcache có thể giữ trạng thái JavaScript và DOM trước đó; ứng dụng cần kiểm tra lifecycle event như `pageshow` và `event.persisted` khi xử lý dữ liệu nhạy cảm.

Không dùng `replaceState()` để giả định snapshot hoặc mọi bản sao dữ liệu đã biến mất. Nếu trang hiển thị secret trong DOM hoặc JavaScript memory, cần xử lý vòng đời trang và tránh giữ dữ liệu nhạy cảm không cần thiết.

## 4. Những nơi URL có thể bị lộ

### 4.1. Browser history, autocomplete và đồng bộ

URL có thể xuất hiện trong history list, thanh gợi ý, tab đã đóng gần đây, bookmark hoặc dữ liệu đồng bộ tài khoản browser. Người dùng khác có quyền truy cập profile hoặc thiết bị dùng chung có thể nhìn thấy các URL đó.

Biện pháp:

- Không đặt password, bearer token hoặc secret dài hạn trong URL.
- Dùng token ngẫu nhiên, one-time, thời hạn ngắn cho link cần thiết.
- Sau khi xử lý token, chuyển sang URL sạch.
- Hướng dẫn người dùng đăng xuất và khóa profile trên thiết bị dùng chung.
- Không giả định xóa URL hiện tại sẽ xóa các bản đã sync hoặc đã sao chép.

### 4.2. Server, proxy, CDN và observability

Query string thường nằm trong request target. Nhiều hạ tầng ghi method, path, query, status và request ID. Token có thể bị sao chép vào:

- Web server access log.
- Reverse proxy, load balancer và CDN log.
- WAF/security event.
- APM trace, error report và distributed tracing.
- Analytics hoặc log do middleware ứng dụng tạo.

Thiết lập log redaction theo tên tham số và route. Với callback hoặc reset route, tốt nhất không ghi query nhạy cảm ngay từ đầu; nếu hạ tầng buộc ghi URL, cấu hình redact trước khi log được lưu hoặc chuyển tiếp. Không dựa vào việc chỉ xóa URL trên browser để xử lý log đã tạo.

### 4.3. Referer

Khi trang điều hướng hoặc tải tài nguyên từ destination khác, browser có thể gửi header `Referer`. Header này có thể tiết lộ URL nguồn tùy Referrer-Policy và policy trên element.

Theo policy mặc định hiện đại thường gặp `strict-origin-when-cross-origin`, request same-origin có thể mang full URL, request cross-origin thường chỉ mang origin, còn downgrade HTTPS xuống HTTP không gửi referrer. Tuy nhiên, policy có thể bị thay đổi ở response header, thẻ HTML hoặc request cụ thể. Hãy cấu hình rõ ràng thay vì dựa vào mặc định.

Đặc biệt tránh để callback page có query chứa authorization code hoặc reset token tải analytics, pixel, font, ảnh hay script bên thứ ba trước khi xử lý xong.

### 4.4. Script, analytics và extension

JavaScript có thể đọc `location.href`, `location.search` và `location.hash`. Một analytics snippet vô tình gửi toàn bộ URL sẽ chuyển query/fragment tới vendor. Tag manager, chat widget và extension có quyền truy cập tab có thể quan sát URL.

Không gửi `location.href` nguyên vẹn vào telemetry. Tạo event theo allowlist, chỉ giữ path đã chuẩn hóa và các tham số không nhạy cảm. Trên trang xác thực, reset password hoặc callback, tránh tải third-party script.

### 4.5. Clipboard, screenshot và chia sẻ link

Người dùng có thể sao chép URL vào email, ticket, chat hoặc tài liệu. Link chứa token có thể tiếp tục tồn tại trong hệ thống đó dù token đã hết hạn. Screenshot hoặc quay màn hình cũng có thể ghi lại address bar.

Thiết kế token one-time và TTL ngắn giúp giảm thời gian khai thác, nhưng không loại bỏ việc token đã bị sao chép. Khi phát hiện link bị lộ, revoke token phía server và phát hành link mới.

## 5. Dữ liệu không nên đặt trong URL

Tránh đặt trực tiếp:

- Password, PIN, API key, access token hoặc refresh token.
- Session ID hoặc credential dùng để xác thực lâu dài.
- Email, số điện thoại, địa chỉ, mã hồ sơ y tế hoặc thông tin tài chính nếu không cần thiết.
- Nội dung tìm kiếm nhạy cảm hoặc dữ liệu người dùng nhập.
- Secret có thể dùng một lần để reset password, trừ khi đó là thiết kế link token có kiểm soát, TTL ngắn và quy trình consume phù hợp.

Một số authorization protocol buộc phải đưa authorization code hoặc state vào callback URL theo response mode. Trong trường hợp đó, giảm thời gian và bề mặt lộ: code one-time/short-lived, state được xác minh, PKCE, callback không tải third-party resource, log redaction và chuyển URL sang dạng sạch ngay sau khi xử lý.

### 5.1. URL encoding không phải mã hóa bảo mật

Percent-encoding (`%2F`, `%3D`, `%40`) chỉ biểu diễn ký tự theo cú pháp URL; Base64/Base64URL cũng chỉ là encoding. Người có URL vẫn có thể decode giá trị. Không dùng encoding để che token, password hoặc dữ liệu cá nhân.

Chuyển dữ liệu từ query sang POST body có thể tránh việc dữ liệu nằm trong address bar/history và Referer, nhưng body vẫn có thể bị ghi trong application log, APM hoặc proxy nếu cấu hình sai. POST không tự động làm dữ liệu bí mật; cần TLS, log redaction, authorization và retention phù hợp.

## 6. Làm sạch URL bằng History API

Sau khi ứng dụng đã đọc và xử lý các tham số cần thiết, có thể thay URL hiện tại để bỏ query hoặc fragment nhạy cảm. Với SPA, `history.replaceState()` thay URL của history entry hiện tại mà không tải lại document.

Ví dụ loại bỏ `code`, `state` và fragment sau khi callback đã được xử lý:

```js
function removeAuthParametersFromCurrentUrl() {
  const url = new URL(window.location.href);
  url.searchParams.delete('code');
  url.searchParams.delete('state');
  url.hash = '';

  const cleanUrl = url.pathname + url.search + url.hash;
  history.replaceState(history.state, '', cleanUrl);
}

// Chỉ gọi sau khi callback đã được xác minh và xử lý.
removeAuthParametersFromCurrentUrl();
```

Giữ lại query parameter không nhạy cảm nếu ứng dụng cần chúng. Tốt hơn là dùng allowlist các tham số được phép tồn tại thay vì chỉ xóa một vài tên đã biết khi callback có thể nhận tham số ngoài dự kiến.

### 6.1. replaceState không xóa mọi bản sao

`replaceState()` chỉ thay entry hiện tại trong session history của document. Nó không:

- Xóa request URL đã tới server hoặc access log đã ghi.
- Xóa URL khỏi history entry trước đó hoặc tab khác.
- Thu hồi link đã gửi qua email/chat hoặc đã sao chép.
- Bảo đảm browser sync chưa đồng bộ URL cũ.
- Xóa dữ liệu mà script, extension hoặc analytics đã đọc trước đó.
- Xóa token đã bị attacker lấy được.

Vì vậy, làm sạch URL là bước giảm thời gian phơi lộ, không phải biện pháp thay thế token ngắn hạn, one-time use, log redaction và revoke.

### 6.2. pushState và replaceState khác nhau

`pushState()` tạo thêm một entry. Nếu dùng nó để thêm URL chứa token, người dùng có thể quay lại entry trước đó bằng Back. `replaceState()` thay entry hiện tại nên phù hợp hơn để loại bỏ tham số nhạy cảm khỏi entry đang hiển thị.

Không tạo history entry mới chứa token chỉ để thay URL cho dễ đọc. Nếu cần lưu trạng thái giao diện, đặt dữ liệu không nhạy cảm trong history state hoặc application state, không nhét credential vào URL.

### 6.3. location.replace

Nếu cần tải một document sạch từ server, có thể dùng:

```js
window.location.replace('/account/reset/complete');
```

`location.replace()` điều hướng tới URL mới và thay entry hiện tại trong history. Tuy nhiên, request đầu tiên chứa token đã được gửi tới server và có thể đã xuất hiện trong log. Redirect sạch cũng không xóa link gốc đã nằm trong email hoặc clipboard.

Với server-side callback, cách phổ biến là xác minh state, đổi code lấy token, tạo session phía server rồi trả redirect về URL sạch bằng HTTP 303. Không trả lại HTML của callback chứa code cho analytics hoặc asset bên thứ ba.

## 7. Thiết kế link reset password, magic link và invitation

Các link này thường cần một bearer token để chứng minh người mở link được phép thực hiện thao tác. Nếu token xuất hiện trong URL, cần coi URL là dữ liệu nhạy cảm trong toàn bộ vòng đời.

### 7.1. Token link an toàn

- Sinh token bằng CSPRNG với entropy đủ lớn.
- Chỉ lưu hash token ở server nếu kiến trúc cho phép; so khớp bằng cách an toàn.
- Gắn token với đúng user, mục đích, transaction và thời điểm hết hạn.
- Giới hạn thời gian sống và chỉ cho phép sử dụng một lần.
- Không đưa PII hoặc thông tin tài khoản vào token dạng dễ đọc.
- Redact tham số token khỏi proxy, application log, analytics và tracing.
- Sau khi kiểm tra link, chuyển browser sang URL sạch.
- Revoke token khi hoàn tất, hết hạn hoặc người dùng yêu cầu link mới.

### 7.2. Không tiêu thụ token chỉ vì GET

Email security scanner, preview bot hoặc browser prefetch có thể tự mở link để kiểm tra an toàn. Nếu một GET request lập tức đổi mật khẩu, chấp nhận invitation hoặc tiêu thụ magic link, scanner có thể vô tình thực hiện thao tác thay người dùng.

Với thao tác nhạy cảm, GET nên hiển thị bước xác nhận hoặc thiết lập một transaction tạm thời; thao tác thay đổi trạng thái được thực hiện bằng POST sau tương tác rõ ràng của người dùng. Server vẫn phải xác minh token, CSRF/transaction binding và quyền trước khi commit.

Một mô hình reset password có thể là:

1. Người dùng mở link GET có token ngẫu nhiên, ngắn hạn.
2. Server kiểm tra token còn hiệu lực nhưng chưa đổi mật khẩu; tạo reset transaction tạm gắn với browser bằng cookie HttpOnly, Secure và SameSite phù hợp.
3. Server trả redirect tới URL sạch và đặt response no-store/no-referrer.
4. Trang sạch hiển thị form đặt mật khẩu; không tải analytics hoặc third-party script.
5. Browser gửi POST với reset transaction và CSRF protection.
6. Server consume token một lần, đổi mật khẩu trong transaction và revoke các phiên phù hợp.

Chi tiết cần điều chỉnh theo threat model. Nếu chỉ dùng GET để đánh dấu token đã dùng, scanner có thể làm người dùng thật mất link. Nếu token được đưa vào JavaScript hoặc DOM, XSS vẫn có thể lấy token trước khi URL được làm sạch.

### 7.3. OAuth/OIDC callback

Authorization Code Flow có thể trả `code` và `state` trong query string. Giảm rủi ro bằng cách:

- Dùng Authorization Code Flow với PKCE cho public client.
- Xác minh state gắn với browser transaction trước khi xử lý code.
- Ràng buộc redirect URI và issuer theo cấu hình đã đăng ký.
- Đổi code ngay tại backend/BFF nếu kiến trúc hỗ trợ; code phải one-time và short-lived.
- Không tải third-party resource trên callback page.
- Redact query callback khỏi log.
- Sau khi tạo session, redirect tới URL sạch hoặc dùng `replaceState()` nếu xử lý hoàn toàn ở SPA.

State không phải token xác thực và không thay PKCE hoặc ID token validation. Làm sạch URL cũng không thay thế việc kiểm tra callback.

## 8. Referrer-Policy và link an toàn

### 8.1. Referrer-Policy response header

Đối với trang có URL nhạy cảm, có thể đặt:

```http
Referrer-Policy: no-referrer
Cache-Control: no-store
```

`no-referrer` yêu cầu browser không gửi Referer từ document đó trong các request tiếp theo. `Cache-Control: no-store` yêu cầu browser và intermediary không lưu response theo HTTP cache; nó không xóa URL khỏi history hoặc request log.

Với trang thông thường, `strict-origin-when-cross-origin` thường là điểm cân bằng: full URL trong same-origin, chỉ origin cho cross-origin an toàn và không gửi khi downgrade. Trang chứa callback code, reset token hoặc dữ liệu nhạy cảm nên cân nhắc policy chặt hơn.

### 8.2. Kiểm soát theo từng element

Link có thể đặt policy riêng:

```html
<a href="https://partner.example.test/" referrerpolicy="no-referrer">
  Mở đối tác không gửi referrer
</a>

<a href="https://partner.example.test/" rel="noreferrer">
  Mở đối tác với noreferrer
</a>
```

`rel="noreferrer"` ngăn gửi Referer và trong browser hiện đại cũng ngụ ý hành vi `noopener`. Dùng `noopener` riêng khi mở tab mới bằng `target="_blank"` để ngăn trang đích truy cập `window.opener`; nếu cần cả hai, có thể ghi rõ `rel="noopener noreferrer"`.

Thuộc tính `referrerpolicy` cũng có thể dùng cho image, script, iframe và các element hỗ trợ. Với callback page, tốt nhất không tải third-party resource ngay từ đầu; referrer policy chỉ giảm thông tin được gửi, không ngăn script đã chạy đọc URL.

### 8.3. Tránh URL nhạy cảm trong analytics

Không gửi nguyên `location.href` hoặc toàn bộ query string tới analytics. Tạo URL chuẩn hóa:

```js
function analyticsPagePath() {
  const url = new URL(location.href);
  const allowed = new Set(['page', 'category']);
  const safeQuery = new URLSearchParams();

  for (const [name, value] of url.searchParams) {
    if (allowed.has(name)) {
      safeQuery.append(name, value);
    }
  }

  const query = safeQuery.toString();
  return url.pathname + (query ? '?' + query : '');
}

sendAnalytics({
  page: analyticsPagePath(),
});
```

Allowlist phải dựa trên schema thực tế; không giả định tham số nào an toàn chỉ vì tên của nó không có chữ token. Tốt nhất analytics nhận route name hoặc page ID thay vì URL tự do.

## 9. Log redaction, cache và callback page

### 9.1. Redact tại nguồn

Nếu URL có thể chứa credential, cấu hình redaction tại mọi lớp nhận request:

- Reverse proxy/CDN: bỏ hoặc che query parameter nhạy cảm theo route.
- Web server: chỉ log path đã chuẩn hóa hoặc redacted query.
- Application middleware: không log request URL nguyên vẹn ở route xác thực.
- APM/tracing: lọc URL attributes và span tags trước khi export.
- Analytics: dùng page ID/route name và allowlist parameter.

Redaction cần được thực hiện trước khi dữ liệu đi vào hệ thống log tập trung. Việc xóa log sau này có thể không xóa bản sao, export hoặc backup đã tạo.

### 9.2. Callback page tối giản

Trang xử lý token hoặc authorization code nên:

- Trả `Cache-Control: no-store`.
- Trả `Referrer-Policy: no-referrer`.
- Dùng CSP chặt, không tải script bên thứ ba.
- Không nhúng analytics, tag manager, chat widget hoặc pixel.
- Không render token/code vào DOM hoặc thông báo lỗi.
- Sau khi xử lý, redirect hoặc replace URL sang route sạch.
- Không đưa query string vào error reporting.

Ví dụ response header:

```http
Cache-Control: no-store
Referrer-Policy: no-referrer
Content-Security-Policy: default-src 'none'; script-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'
X-Content-Type-Options: nosniff
```

Điều chỉnh CSP theo tài nguyên thực tế. Nếu callback không cần script, có thể bỏ hẳn script-src và xử lý ở server rồi redirect ngay.

## 10. Thực hành: URL history và Referer bằng Node.js

Lab chạy hoàn toàn trên localhost và chỉ dùng token giả `DEMO-RESET-TOKEN-NOT-REAL`. Mục tiêu là quan sát:

- Query string được gửi tới server và có thể xuất hiện trong log.
- Query/fragment xuất hiện trong address bar và history entry.
- `pushState()` tạo entry mới còn `replaceState()` thay entry hiện tại.
- Link same-origin có thể gửi Referer chứa URL nguồn.
- `referrerpolicy="no-referrer"` ngăn gửi Referer cho link cụ thể.
- `location.replace()` chuyển tới URL sạch và thay entry hiện tại.

Lab không gọi third-party site, không dùng token thật và không gửi dữ liệu ra ngoài máy local.

### Bước 1 — Tạo file `url-history-lab.cjs`

```js
const http = require('node:http');

const page = [
  '<!doctype html>',
  '<html lang="vi"><head><meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width, initial-scale=1">',
  '<title>URL history lab</title></head><body>',
  '<h1>URL history lab</h1>',
  '<p>Chỉ dùng dữ liệu giả. Không nhập token thật hoặc thông tin cá nhân.</p>',
  '<p><a href="/history-lab?reset_token=DEMO-RESET-TOKEN-NOT-REAL">',
  'Mở URL demo có query token giả</a></p>',
  '</body></html>',
].join('\n');

const historyPage = [
  '<!doctype html>',
  '<html lang="vi"><head><meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width, initial-scale=1">',
  '<title>History entry demo</title></head><body>',
  '<h1>History entry demo</h1>',
  '<p id="current-url"></p>',
  '<p id="fragment"></p>',
  '<button id="inspect" type="button">Inspect current URL</button>',
  '<button id="push" type="button">Push demo token and fragment</button>',
  '<button id="clean" type="button">Replace current entry with clean URL</button>',
  '<button id="navigate-clean" type="button">location.replace to clean page</button>',
  '<button id="back" type="button">History back</button>',
  '<h2>Referer test (same origin)</h2>',
  '<p><a href="/destination">Navigate and send normal Referer policy</a></p>',
  '<p><a href="/destination" referrerpolicy="no-referrer">',
  'Navigate without Referer</a></p>',
  '<p><a href="/destination" rel="noreferrer">Navigate with rel=noreferrer</a></p>',
  '<pre id="output"></pre>',
  '<script src="/app.js" defer></script>',
  '</body></html>',
].join('\n');

const appJs = [
  "const output = document.querySelector('#output');",
  "const currentUrl = document.querySelector('#current-url');",
  "const fragment = document.querySelector('#fragment');",
  'function inspect() {',
  '  currentUrl.textContent = "Current URL: " + location.href;',
  '  fragment.textContent = "Fragment: " + (location.hash || "(none)");',
  '  output.textContent = "document.referrer: " + (document.referrer || "(empty)");',
  '}',
  "document.querySelector('#inspect').addEventListener('click', inspect);",
  "document.querySelector('#push').addEventListener('click', () => {",
  '  const url = new URL(location.href);',
  '  url.searchParams.set("demo_token", "DEMO-ONLY-NOT-A-CREDENTIAL");',
  '  url.hash = "demo-fragment";',
  '  history.pushState({ demo: true }, "", url.pathname + url.search + url.hash);',
  '  inspect();',
  '});',
  "document.querySelector('#clean').addEventListener('click', () => {",
  '  const url = new URL(location.href);',
  '  url.searchParams.delete("reset_token");',
  '  url.searchParams.delete("demo_token");',
  '  url.hash = "";',
  '  history.replaceState(history.state, "", url.pathname + url.search + url.hash);',
  '  inspect();',
  '  output.textContent += "\\nreplaceState changed only the current history entry; earlier entries may remain.";',
  '});',
  "document.querySelector('#navigate-clean').addEventListener('click', () => {",
  '  location.replace("/clean");',
  '});',
  "document.querySelector('#back').addEventListener('click', () => history.back());",
  'inspect();',
].join('\n');

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character]);
}

function sendHtml(res, status, html) {
  res.writeHead(status, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
    'X-Content-Type-Options': 'nosniff',
  });
  res.end(html);
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost:3000');

  if (req.method !== 'GET') {
    res.writeHead(405, { 'Content-Type': 'text/plain; charset=utf-8' });
    return res.end('Method not allowed');
  }

  if (url.pathname === '/history-lab') {
    // Synthetic-only log to demonstrate that query reaches the server.
    console.log('[LAB] request target:', req.url);
    return sendHtml(res, 200, historyPage);
  }

  if (url.pathname === '/destination') {
    const referer = req.headers.referer || '(no Referer header)';
    console.log('[LAB] destination Referer:', referer);
    return sendHtml(res, 200, [
      '<!doctype html><html lang="vi"><meta charset="utf-8">',
      '<meta name="viewport" content="width=device-width, initial-scale=1">',
      '<title>Destination</title><body><h1>Destination</h1>',
      '<p>Referer nhận được:</p><pre>',
      escapeHtml(referer),
      '</pre><p><a href="/">Return to lab</a></p></body></html>',
    ].join(''));
  }

  if (url.pathname === '/app.js') {
    res.writeHead(200, {
      'Content-Type': 'text/javascript; charset=utf-8',
      'Cache-Control': 'no-store',
      'Referrer-Policy': 'strict-origin-when-cross-origin',
      'X-Content-Type-Options': 'nosniff',
    });
    return res.end(appJs);
  }

  if (url.pathname === '/clean') {
    return sendHtml(res, 200, [
      '<!doctype html><html lang="vi"><meta charset="utf-8">',
      '<title>Clean URL</title><body><h1>Clean URL</h1>',
      '<p>Đã điều hướng tới URL không có query token demo.</p>',
      '<a href="/">Return to lab</a></body></html>',
    ].join(''));
  }

  if (url.pathname === '/') {
    return sendHtml(res, 200, page);
  }

  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
  res.end('Not found');
});

server.listen(3000, 'localhost', () => {
  console.log('Open http://localhost:3000');
});
```

### Bước 2 — Chạy lab

```sh
node url-history-lab.cjs
```

Mở http://localhost:3000. Nếu cổng 3000 đang được sử dụng, đổi cổng trong `server.listen()` và URL base dùng để tạo đối tượng URL.

### Bước 3 — Quan sát query trong request và history

1. Chọn **Mở URL demo có query token giả**.
2. Quan sát address bar có tham số `reset_token`.
3. Xem terminal: server ghi request target có query string. Đây là ví dụ vì sao URL nhạy cảm có thể xuất hiện trong access log.
4. Nhấn **Inspect current URL** để xem URL hiện tại.
5. Nhấn **Push demo token and fragment**; URL có query và fragment mới, nhưng không có request document mới do `pushState()`.
6. Mở browser history hoặc dùng Back để quan sát các entry đã tạo.

### Bước 4 — So sánh replaceState và location.replace

1. Trên entry có query token demo, nhấn **Replace current entry with clean URL**.
2. URL hiện tại mất `reset_token`, `demo_token` và fragment.
3. Nhấn Back để thấy entry trước đó có thể vẫn tồn tại.
4. Mở lại URL demo và nhấn **location.replace to clean page**.
5. Trang được tải tại `/clean` và entry hiện tại được thay; request URL ban đầu vẫn đã tới server.

### Bước 5 — Quan sát Referer

1. Mở lại URL demo có query.
2. Chọn **Navigate and send normal Referer policy**.
3. Destination cùng origin hiển thị Referer; terminal cũng ghi header nhận được.
4. Quay lại và chọn **Navigate without Referer** hoặc link `rel=noreferrer`.
5. Destination phải hiển thị `(no Referer header)`.

Lab chỉ điều hướng giữa các route localhost. Không dùng dữ liệu thật và không thử link này trên website bên ngoài.

## 11. Checklist bảo vệ URL và browser history

- [ ] Không đặt password, session ID, access token hoặc refresh token trong URL.
- [ ] Query/fragment được rà soát trước khi đưa vào path, analytics, error report hoặc telemetry.
- [ ] Token link là opaque, có entropy cao, đúng mục đích, TTL ngắn và one-time use.
- [ ] Reset/magic-link GET không tự thực hiện side effect trước tương tác xác nhận phù hợp.
- [ ] Callback xác thực kiểm tra state, PKCE và issuer trước khi xử lý authorization code.
- [ ] Callback/reset page không tải third-party script, pixel, analytics hoặc tag manager.
- [ ] URL hiện tại được làm sạch sau khi xử lý tham số nhạy cảm.
- [ ] Hiểu rằng replaceState/location.replace không xóa server log, history entry khác hoặc link đã sao chép.
- [ ] Referrer-Policy được cấu hình tường minh; route nhạy cảm dùng no-referrer khi phù hợp.
- [ ] Link tới site khác dùng referrerpolicy/no-referrer hoặc rel=noreferrer nếu không cần Referer.
- [ ] Query nhạy cảm được redact tại CDN, proxy, web server, middleware, APM và analytics.
- [ ] Response callback/reset dùng Cache-Control: no-store.
- [ ] Redirect destination được allowlist; không tin return URL tùy ý từ query hoặc fragment.
- [ ] Không giả định URL fragment an toàn chỉ vì browser không gửi nó trong HTTP request.
- [ ] Browser history, autocomplete, sync, bookmark và thiết bị dùng chung nằm trong threat model.
- [ ] Token bị lộ có quy trình revoke và phát hành token thay thế.
- [ ] Lab chỉ dùng dữ liệu giả và không điều hướng ra third-party domain.

## 12. Câu hỏi tự kiểm tra

**1.** Browser gửi những phần nào của URL trong HTTP request?  
**Trả lời:** Request chứa path và query string; fragment không được gửi trong HTTP request.

**2.** Nếu fragment không gửi tới server, vì sao vẫn có rủi ro?  
**Trả lời:** Fragment vẫn xuất hiện trong address bar/history và JavaScript cùng trang, extension hoặc telemetry có thể đọc được.

**3.** Query string có thể xuất hiện ở đâu ngoài browser history?  
**Trả lời:** Web server, reverse proxy, CDN, WAF, APM, analytics và Referer tùy policy.

**4.** `history.pushState()` khác `history.replaceState()` thế nào?  
**Trả lời:** pushState tạo entry mới; replaceState thay entry hiện tại mà không tải document mới.

**5.** `location.replace()` có xóa request URL khỏi server log không?  
**Trả lời:** Không. Request ban đầu đã tới server trước khi browser điều hướng tới URL sạch.

**6.** `Cache-Control: no-store` có xóa URL khỏi history không?  
**Trả lời:** Không. Header này điều khiển HTTP cache, không xóa browser history hoặc log.

**7.** Vì sao callback page không nên tải analytics?  
**Trả lời:** Script/analytics có thể đọc location.href hoặc query và gửi authorization code/state tới vendor.

**8.** `Referrer-Policy: no-referrer` làm gì?  
**Trả lời:** Yêu cầu browser không gửi Referer từ document đó trong các request tiếp theo.

**9.** Vì sao reset token không nên bị consume ngay ở GET?  
**Trả lời:** Email scanner hoặc prefetch có thể tự mở link; GET side effect có thể làm token mất hiệu lực trước khi người dùng thật thao tác.

**10.** Khi phát hiện token trong URL bị lộ, chỉ replaceState có đủ không?  
**Trả lời:** Không. Cần revoke token/session phía server, xử lý log/bản sao theo chính sách và phát hành credential mới khi cần.

## Tổng kết

URL trong browser history là một phần của bề mặt rò rỉ dữ liệu. Query được gửi tới server và có thể đi vào log; fragment không gửi trong HTTP request nhưng vẫn nằm trong URL phía browser và có thể bị JavaScript hoặc extension đọc. URL cũng có thể tồn tại trong history, autocomplete, sync, bookmark, clipboard, screenshot và Referer. Không đặt credential lâu dài hoặc dữ liệu cá nhân không cần thiết trong URL. Với link reset và callback, dùng token ngắn hạn/one-time, ràng buộc transaction, log redaction, Referrer-Policy, Cache-Control và callback page tối giản. Sau khi xử lý, dùng replaceState hoặc location.replace để giảm thời gian URL nhạy cảm xuất hiện, đồng thời nhớ rằng các API này không xóa request log hay những bản sao đã được tạo.
