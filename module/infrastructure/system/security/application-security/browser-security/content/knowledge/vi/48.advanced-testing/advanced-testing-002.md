# Redirect test: kiểm thử an toàn cho luồng chuyển hướng

## 1. Redirect test là gì?

**Redirect test** là kiểm thử cách ứng dụng chuyển browser hoặc HTTP client từ một URL sang URL khác. Redirect giúp hoàn tất đăng nhập, đưa người dùng về trang trước đó, chuyển sang URL chuẩn hoặc điều hướng sau khi lưu dữ liệu. Redirect không được kiểm soát có thể đưa người dùng tới website giả mạo, làm lộ authorization code, token hoặc dữ liệu trong URL, tạo vòng lặp điều hướng hay khiến backend truy cập tài nguyên ngoài dự kiến.

Ứng dụng web thường redirect bằng response HTTP 3xx cùng header `Location`, bằng JavaScript như `window.location.assign()`, hoặc qua router phía client. Mỗi cách có ranh giới và hành vi khác nhau. Kiểm thử cần xác định ai chọn đích đến, giá trị đó được parse/normalize thế nào, browser có gửi credential hoặc referrer nào trong các bước tiếp theo và server có kiểm tra quyền ở từng request hay không.

Ví dụ endpoint nhận tham số `next`:

```text
https://app.example.test/login?next=https%3A%2F%2Fattacker.example
```

Nếu server đưa giá trị `next` trực tiếp vào header `Location`, người dùng có thể đăng nhập trên website thật rồi bị chuyển sang website do attacker kiểm soát. Đây là một dạng **open redirect**. Endpoint chuyển hướng cũng có thể bị dùng trong phishing vì link ban đầu mang domain đáng tin cậy.

**Nguyên tắc:** ứng dụng nên chọn đích đến từ route key hoặc allowlist do server quản lý. Nếu phải nhận URL, parse bằng URL parser chuẩn, kiểm tra scheme và origin chính xác, giới hạn path/query, rồi chỉ tạo `Location` từ giá trị đã xác minh. Kiểm thử phải quan sát response đầu tiên và cả chuỗi điều hướng cuối cùng.

Bài viết thuộc chương **Kiểm thử nâng cao** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Nội dung kết nối redirect với origin, URL parsing, authentication, OAuth/OIDC, cookie, Referrer-Policy, HTTP status, SSRF và kiểm thử bảo mật ứng dụng web.

Sau bài học, bạn có thể:

- Phân biệt redirect HTTP và điều hướng phía client.
- Đọc các status code 301, 302, 303, 307 và 308.
- Nhận diện open redirect qua `next`, `returnUrl`, `continue`, `redirect` và callback.
- Phân tích URL bằng parser chuẩn và kiểm tra origin chính xác.
- Nhận diện protocol-relative URL, scheme nguy hiểm, userinfo, backslash và CRLF.
- Thiết kế redirect bằng route key hoặc allowlist.
- Kiểm thử redirect chain, loop và method preservation.
- Bảo vệ login, logout, OAuth/OIDC callback và return URL.
- Phân biệt browser redirect với redirect trong server-side fetch.
- Đánh giá tác động tới cookie, referrer và dữ liệu nhạy cảm.
- Viết unit test, integration test và browser test cho redirect.
- Thực hành kiểm thử redirect bằng Node.js local.

## 2. Các loại redirect trong ứng dụng web

### 2.1. HTTP redirect

Server trả response 3xx và header `Location`:

```http
HTTP/1.1 302 Found
Location: /dashboard
Cache-Control: no-store
```

Browser nhận response và gửi request mới tới URL đích. `Location` có thể là URI tuyệt đối hoặc URI tương đối. Với URI tương đối, browser giải quyết dựa trên URL của response hiện tại.

Ví dụ:

- `/dashboard`: đường dẫn trên cùng origin.
- `https://portal.example.test/dashboard`: URL tuyệt đối.
- `../account`: đường dẫn tương đối theo URL hiện tại.
- `//other.example.test/path`: protocol-relative URL, kế thừa scheme hiện tại nhưng chuyển sang host khác.

Đừng xem `Location` là chuỗi hiển thị vô hại. Nó quyết định browser sẽ gửi request tiếp theo tới đâu.

### 2.2. Client-side redirect

JavaScript có thể điều hướng bằng:

```js
window.location.assign("/dashboard");
window.location.replace("/dashboard");
```

`assign()` thêm entry vào browser history; `replace()` thay entry hiện tại. Cả hai đều điều hướng browser, nhưng không tạo response 3xx từ server cho bước gọi ban đầu.

Nếu giá trị đích đến đến từ query string, DOM, message hoặc API, client-side redirect cũng cần validation. Không cho dữ liệu không tin cậy trở thành URL điều hướng chỉ vì code chạy trong browser.

### 2.3. SPA router redirect

SPA có thể điều hướng nội bộ qua router mà không tải document mới. Router có thể nhận `returnTo` từ query hoặc state sau login. Dù không phát sinh HTTP 3xx, việc chuyển tới external URL vẫn có thể tạo open redirect hoặc phishing.

Phân biệt route nội bộ với URL tuyệt đối. Nếu router có API `navigate()` chỉ dành cho route nội bộ, không truyền URL do người dùng kiểm soát vào API mở external link.

### 2.4. Redirect trong server-side fetch

Backend có thể fetch URL do người dùng cung cấp, sau đó HTTP client tự follow redirect. Đây là tình huống khác với browser navigation. Nếu server fetch URL và theo redirect tới `127.0.0.1`, private network hoặc metadata endpoint, rủi ro có thể trở thành **SSRF**.

Ví dụ tính năng import ảnh từ URL, kiểm tra webhook hoặc tạo preview có thể vô tình truy cập địa chỉ nội bộ sau một redirect. Backend cần kiểm tra đích ở mỗi hop, giới hạn redirect count, kiểm tra DNS/IP theo policy và chặn loopback/private/link-local/metadata destinations theo threat model.

Không dùng kết quả kiểm thử browser redirect để kết luận server-side fetch an toàn.

## 3. HTTP status code và hành vi method

Các status code redirect phổ biến:

| Status | Ý nghĩa | Method khi follow |
|---|---|---|
| 301 Moved Permanently | Tài nguyên được chuyển vĩnh viễn | Với POST, user agent có thể đổi thành GET theo hành vi lịch sử |
| 302 Found | Chuyển hướng tạm thời | Với POST, user agent có thể đổi thành GET theo hành vi lịch sử |
| 303 See Other | Xem tài nguyên khác | Thường follow bằng GET, ngoại trừ HEAD |
| 307 Temporary Redirect | Chuyển hướng tạm thời | Giữ nguyên method và body |
| 308 Permanent Redirect | Chuyển hướng vĩnh viễn | Giữ nguyên method và body |

### 3.1. 301 và 308

Dùng redirect vĩnh viễn khi địa chỉ cũ thực sự được thay thế. Browser, proxy hoặc cache có thể lưu kết quả redirect theo quy tắc caching. Nếu cấu hình sai, thay đổi đích sau đó có thể khó kiểm soát vì client vẫn dùng redirect đã cache.

Kiểm thử cần xem `Cache-Control`, thời gian cache, hành vi sau khi đổi route và việc browser có tiếp tục dùng URL cũ hay không.

### 3.2. 302 và 307

Dùng redirect tạm thời khi đích đến có thể thay đổi hoặc chỉ áp dụng cho một phiên/tình huống. Nếu cần giữ nguyên method và body của request, dùng 307 hoặc 308 theo yêu cầu.

Không chọn 302 cho POST chỉ theo thói quen. Browser và client có thể chuyển POST thành GET khi follow 301/302; điều này có thể làm thay đổi ý nghĩa nghiệp vụ.

### 3.3. 303 sau POST

Mẫu Post/Redirect/Get (PRG) thường dùng 303 sau khi server xử lý POST thành công:

```http
HTTP/1.1 303 See Other
Location: /orders/confirmation
Cache-Control: no-store
```

Browser tiếp tục bằng GET tới trang xác nhận. Cách này giúp refresh trang kết quả không gửi lại POST tạo đơn hàng. Kiểm thử cần xác nhận request tiếp theo là GET và thao tác ghi không bị lặp.

### 3.4. 307 và 308 giữ body

307/308 yêu cầu client giữ method và body khi follow redirect. Điều này quan trọng với POST/PUT có payload. Nếu đích đến là origin khác, body có thể được gửi tới server khác theo redirect policy của client; do đó chỉ redirect tới origin được tin cậy và hiểu rõ dữ liệu sẽ được chuyển tiếp.

Không redirect request có credential hoặc body nhạy cảm sang host do user kiểm soát.

### 3.5. Không nhầm 304 với redirect

304 Not Modified là response phục vụ cache validation, không phải lệnh điều hướng thông thường. Đừng viết test gom mọi status 3xx thành một loại redirect có cùng ý nghĩa.

## 4. Open redirect

### 4.1. Open redirect là gì?

Open redirect xảy ra khi ứng dụng chấp nhận URL đích từ input không tin cậy và chuyển hướng tới đó mà không kiểm tra đúng policy.

Ví dụ dễ mắc:

```js
const next = new URLSearchParams(location.search).get("next");
window.location.assign(next);
```

Hoặc phía server:

```js
res.writeHead(302, {
  Location: req.query.next
});
res.end();
```

Nếu attacker gửi link có `next=https://attacker.example`, ứng dụng trở thành bước trung gian để đưa người dùng sang domain khác. Domain đáng tin trong link ban đầu có thể khiến nạn nhân ít nghi ngờ hơn.

### 4.2. Các tham số cần tìm

Khi review route và API, tìm các tên thường dùng:

- `next`
- `return`
- `returnUrl`
- `return_to`
- `redirect`
- `redirect_uri`
- `continue`
- `callback`
- `target`
- `destination`
- `url`
- `goto`
- `post_logout_redirect_uri`

Không chỉ tìm query string. Giá trị đích có thể đến từ form body, JSON, cookie, session, database, OAuth state hoặc SPA router state.

### 4.3. Tác động bảo mật

Open redirect có thể hỗ trợ:

- Phishing qua link mang domain hợp pháp ở bước đầu.
- Rò rỉ authorization code hoặc dữ liệu trong query qua redirect chain.
- Bypass một số kiểm tra callback yếu dựa trên domain trung gian.
- Chuyển người dùng tới trang giả sau khi đăng nhập hoặc đăng xuất.
- Tạo link đáng tin để phát tán malware hoặc trang thu thập credential.
- Làm tăng tác động của lỗi trong OAuth/OIDC hoặc luồng reset password.

Open redirect không tự động cho attacker quyền đọc cookie của origin ban đầu. Cookie vẫn tuân theo domain/path/SameSite/Secure và browser policy. Tuy nhiên, redirect có thể khiến người dùng gửi dữ liệu hoặc credential tới destination khác qua thao tác tiếp theo.

### 4.4. Redirect sau login

Luồng thường gặp:

1. Người dùng mở trang cần đăng nhập.
2. Ứng dụng lưu đường dẫn cần quay lại.
3. Người dùng đăng nhập.
4. Server chuyển tới đường dẫn đã lưu.

Nếu bước 2 lưu URL tùy ý và bước 4 phát `Location` trực tiếp, login endpoint có thể thành open redirect. Lưu route key hoặc path nội bộ đã kiểm tra, không lưu full URL do client cung cấp.

### 4.5. Redirect sau logout

Một số ứng dụng nhận `returnUrl` sau logout. Nếu không allowlist, attacker có thể tạo link đăng xuất rồi đưa người dùng sang website giả. Nếu logout được dùng trong Single Logout hoặc OIDC RP-Initiated Logout, cần áp dụng allowlist callback theo cấu hình provider/client.

## 5. URL parsing và validation

### 5.1. Dùng URL parser chuẩn

Không kiểm tra URL bằng các phép so sánh chuỗi như:

```js
if (target.startsWith("https://app.example.com")) {
  // Sai: có thể chấp nhận app.example.com.attacker.test
}
```

Hãy parse bằng API `URL`:

```js
const target = new URL(input, "https://app.example.com");

if (target.origin !== "https://app.example.com") {
  throw new Error("Redirect origin is not allowed");
}
```

So sánh `origin` chính xác bao gồm scheme, host và port. `https://app.example.com` khác `http://app.example.com`, khác port và khác subdomain.

### 5.2. Protocol-relative URL

Giá trị bắt đầu bằng `//` kế thừa scheme hiện tại nhưng chuyển host:

```text
//attacker.example/path
```

Nếu chỉ kiểm tra rằng chuỗi không bắt đầu bằng `http`, giá trị này vẫn có thể redirect cross-origin. Dùng URL parser và so sánh origin cuối cùng.

### 5.3. Userinfo trong URL

URL có thể chứa userinfo trước hostname:

```text
https://app.example.com@attacker.example/path
```

Người đọc có thể chú ý phần `app.example.com` và hiểu nhầm host thực tế. Trong URL parser, hostname là `attacker.example`. Khi validate redirect, từ chối username/password nếu ứng dụng không có use case rõ ràng.

### 5.4. Domain suffix và lookalike

Không dùng kiểm tra suffix thiếu ranh giới:

```js
target.hostname.endsWith("example.com")
```

Chuỗi `notexample.com` hoặc `example.com.attacker.test` có thể bị xử lý sai nếu code không kiểm tra đúng boundary. Tốt nhất dùng allowlist hostname/origin chính xác. Nếu cho phép subdomain, kiểm tra hostname bằng quy tắc suffix có dấu chấm phân cách và có policy rõ ràng về subdomain do ai quản lý.

### 5.5. Scheme nguy hiểm

Redirect chỉ nên dùng scheme được ứng dụng chủ đích hỗ trợ, thường là HTTPS cho external destination và relative path cho nội bộ. Từ chối các scheme như `javascript:`, `data:`, `file:`, `blob:` hoặc custom protocol nếu không có use case được review.

Đừng nghĩ rằng `new URL()` thành công nghĩa là URL an toàn. Parser chỉ phân tích cú pháp; ứng dụng vẫn phải kiểm tra scheme, origin, credentials và route.

### 5.6. Backslash và parser khác biệt

Một số parser chuẩn hóa backslash trong URL có authority như dấu slash. Nếu một tầng kiểm tra `\` theo quy tắc riêng còn browser diễn giải theo WHATWG URL, các tầng có thể hiểu cùng input khác nhau.

Reject backslash và control characters trước khi parse khi chúng không được phép trong redirect input. Không tự decode nhiều lần. Dùng cùng một parser/validation rule ở nơi nhận input và nơi phát header.

### 5.7. CRLF và header injection

Không nối giá trị người dùng vào header `Location` hoặc tự tạo HTTP response bằng string. CR/LF có thể làm hỏng cấu trúc header nếu framework hoặc server cho phép.

Framework hiện đại thường từ chối một số ký tự điều khiển trong header, nhưng đó là lớp bảo vệ cuối. Validate input trước khi tạo response và dùng API header chuẩn.

## 6. Chọn đích đến an toàn

### 6.1. Ưu tiên route key

Thiết kế tốt nhất là client gửi một mã route đã định nghĩa, server ánh xạ sang path cố định:

```js
const destinations = new Map([
  ["home", "/"],
  ["dashboard", "/dashboard"],
  ["settings", "/settings"],
  ["complete", "/orders/confirmation"]
]);

function resolveDestination(key) {
  return destinations.get(key) || "/";
}

const locationHeader = resolveDestination(request.query.destination);
res.redirect(303, locationHeader);
```

Client không thể yêu cầu server chuyển tới host tùy ý. Nếu cần giữ một số filter, chỉ nhận các query parameter đã allowlist và validate kiểu/độ dài.

### 6.2. Allowlist origin chính xác

Nếu sản phẩm cần redirect tới nhiều website, khai báo origin chính xác ở server-side configuration:

```js
const allowedOrigins = new Set([
  "https://portal.example.com",
  "https://docs.example.com"
]);

function validateExternalRedirect(input) {
  let url;

  try {
    url = new URL(input);
  } catch {
    return null;
  }

  if (url.protocol !== "https:") return null;
  if (url.username || url.password) return null;
  if (!allowedOrigins.has(url.origin)) return null;

  return url.href;
}
```

Allowlist phải do hệ thống tin cậy quản lý. Không cho người dùng tự thêm origin vào allowlist qua profile hoặc query parameter nếu không có quy trình xác minh.

### 6.3. Chỉ cho phép relative path nội bộ

Nếu redirect chỉ cần quay lại trang trong cùng ứng dụng, chấp nhận path nội bộ đã kiểm tra và từ chối absolute/protocol-relative URL. Có thể giới hạn path bằng route allowlist hoặc router name.

Không chỉ kiểm tra `startsWith("/")`: giá trị `//attacker.example` cũng bắt đầu bằng slash. Hãy parse và kiểm tra origin, đồng thời từ chối `//`, backslash và control characters.

### 6.4. Kiểm tra query và fragment

Query/fragment có thể mang token, email, search term hoặc state. Nếu ứng dụng không cần giữ chúng, bỏ chúng khỏi redirect target. Nếu cần, chỉ giữ key đã allowlist, kiểm tra kiểu/độ dài và không chuyển tiếp credential.

Fragment không gửi trong HTTP request ban đầu tới server, nhưng JavaScript ở trang đích có thể đọc nó. Không dùng fragment làm nơi chuyển secret qua redirect.

### 6.5. Fallback an toàn

Khi target không hợp lệ, chuyển về một trang mặc định cùng origin như `/` hoặc trang báo lỗi. Không echo input sai vào `Location`, HTML hay thông báo lỗi. Ghi một event bảo mật đã lọc nếu cần theo dõi số lần bị từ chối.

## 7. Redirect chain và redirect loop

### 7.1. Redirect chain

Một redirect chain có nhiều bước:

```text
/login
  -> /auth/continue
      -> https://id.example.com/authorize
          -> /auth/callback
              -> /dashboard
```

Mỗi bước có thể được xử lý bởi hệ thống khác nhau. Kiểm thử chỉ endpoint đầu tiên có thể bỏ sót một bước trung gian chuyển tới host ngoài dự kiến.

Ghi lại từng status, `Location`, origin và method trong môi trường test. Với production, dùng trace/request ID để liên kết các bước mà không log token hoặc full query.

### 7.2. Redirect loop

Loop xảy ra khi A chuyển tới B và B lại chuyển về A, hoặc khi middleware luôn redirect vì điều kiện sai:

```text
/login -> /login
```

Nguyên nhân thường gặp:

- Cookie session không được gửi hoặc không được đọc.
- Reverse proxy báo sai scheme HTTP/HTTPS.
- Middleware HTTPS redirect không nhận biết TLS termination.
- Route locale hoặc canonical URL lặp lại.
- Điều kiện authentication sai.
- Slash/case normalization không nhất quán.

Kiểm thử cần có giới hạn số hop và xác nhận cuối cùng đạt trang mong đợi hoặc trả lỗi có kiểm soát.

### 7.3. Giới hạn redirect count

HTTP client và browser có giới hạn riêng cho số lần redirect, nhưng ứng dụng không nên dựa vào giới hạn đó để xử lý loop. Server-side fetch nên đặt max redirects rõ ràng. Với browser flow, test tự theo dõi từng response hoặc quan sát navigation để phát hiện vòng lặp.

### 7.4. Cache và redirect cũ

Redirect 301/308 có thể được cache. Khi đổi đích, người dùng có thể tiếp tục đi theo redirect cũ. Dùng status phù hợp và cache policy phù hợp với tính chất route. Không dùng redirect permanent cho target thay đổi theo user/session.

## 8. Authentication và OAuth/OIDC redirect

### 8.1. redirect_uri phải khớp chính xác

OAuth/OIDC authorization request dùng `redirect_uri` để chỉ định callback. Authorization server cần so khớp URI với callback đã đăng ký theo yêu cầu của profile/provider. Không dùng wildcard rộng hoặc kiểm tra domain bằng chuỗi lỏng lẻo.

Một redirect endpoint trong ứng dụng không được phép biến callback đã xác thực thành URL tùy ý do query cung cấp.

### 8.2. state và PKCE

`state` giúp liên kết response với request ban đầu và chống request forgery trong OAuth client flow. PKCE bảo vệ authorization code bằng verifier/challenge. Hai cơ chế giải quyết mục tiêu khác nhau và cần được triển khai theo flow phù hợp.

Không bỏ qua state chỉ vì redirect_uri đã allowlist. Không dùng state như URL đích chưa xác minh. Nếu state chứa reference tới return route, lưu mapping ở server/session hoặc ký và xác thực payload theo thiết kế.

### 8.3. Authorization code và token trong redirect chain

Authorization code có thể xuất hiện trên callback URL trong một thời gian ngắn. Không để callback chuyển tiếp nguyên query sang external destination, analytics, third-party script hoặc log.

Sau khi xác minh state và exchange code theo flow, làm sạch URL/history nếu phù hợp. Redirect tiếp theo nên tới path sạch, không chứa code hoặc token.

Không đặt access token hoặc refresh token trong query string. Kiểm soát Referrer-Policy và script bên thứ ba trên callback page.

### 8.4. Logout callback

OIDC logout có thể có `post_logout_redirect_uri`. Chỉ chấp nhận URI đã đăng ký cho client và kiểm tra state/flow theo provider. Không dùng `returnUrl` tự do làm callback sau logout.

## 9. Redirect và browser security context

### 9.1. Cookie theo từng request

Redirect không chuyển nguyên cookie từ origin cũ sang origin mới. Browser quyết định cookie nào được gửi cho từng request dựa trên domain, path, Secure, SameSite, partitioning và context điều hướng.

Khi test cross-site redirect, kiểm tra request thực tế trong Network tab. Không suy luận rằng cookie của `app.example.com` sẽ được gửi tới `attacker.example` chỉ vì ứng dụng đã redirect tới đó.

### 9.2. SameSite và top-level navigation

SameSite ảnh hưởng việc cookie được gửi trong cross-site context. Hành vi còn phụ thuộc method và loại navigation. Redirect chain có thể thay đổi site context giữa các request.

Kiểm thử login/logout và callback nên dùng browser thật hoặc automation browser để quan sát cookie request headers, không chỉ dùng unit test URL validator.

### 9.3. Referrer-Policy

Khi browser điều hướng qua origin khác, header `Referer` có thể tiết lộ origin hoặc URL nguồn tùy Referrer-Policy. Dữ liệu query nhạy cảm trong URL nguồn có thể bị lộ nếu policy cho phép gửi full URL.

Dùng policy phù hợp, thường ít nhất là `strict-origin-when-cross-origin` cho website chung và cân nhắc `no-referrer` cho callback hoặc trang xử lý secret. Policy không ngăn JavaScript tự gửi `location.href` tới analytics.

### 9.4. HTTPS và HSTS

Không redirect người dùng qua HTTP nếu có thể phục vụ trực tiếp HTTPS. Dùng HTTPS mặc định, cấu hình HSTS phù hợp và tránh tạo một bước HTTP trung gian có thể bị can thiệp. Kiểm thử cả URL HTTP cũ, proxy/load balancer TLS termination và canonical host.

### 9.5. window.opener và link external

Nếu mở external destination bằng tab mới qua link, cân nhắc `rel="noopener"` và policy phù hợp để trang đích không thao tác được window mở nó. Đây là vấn đề liên quan navigation/tab relationship, không thay thế việc validate redirect target.

## 10. Redirect test matrix

Một bộ kiểm thử tốt cần bao phủ nhiều nhóm input:

| Nhóm | Input mẫu | Kết quả mong đợi |
|---|---|---|
| Relative path hợp lệ | `/dashboard` | Chỉ redirect nội bộ |
| Same-origin absolute URL | `https://app.example.test/dashboard` | Chấp nhận nếu route được phép |
| External origin | `https://attacker.example/` | Từ chối nếu không nằm allowlist |
| Protocol-relative | `//attacker.example/` | Từ chối |
| Userinfo | `https://app.example.test@attacker.example/` | Từ chối |
| Scheme nguy hiểm | `javascript:alert(1)` | Từ chối |
| Data/file scheme | `data:text/html,...`, `file:///...` | Từ chối |
| Backslash | `\\attacker.example\path` | Từ chối |
| CR/LF | `%0d%0aX-Test:yes` | Từ chối |
| Encoded separator | `%2f%2fattacker.example` | Parse rồi kiểm tra origin; không tin raw string |
| Double encoding | `%252f%252fattacker.example` | Không decode lặp; reject nếu không hợp lệ |
| Lookalike host | `app.example.test.attacker.example` | Từ chối |
| Host suffix sai | `notapp.example.test` | Từ chối |
| Port khác | `https://app.example.test:8443/` | Từ chối nếu port không allowlist |
| Query nhạy cảm | `/done?token=...` | Bỏ hoặc từ chối query không được phép |
| Fragment | `/done#access_token=...` | Không chuyển secret |
| Redirect chain | A → B → C | Mọi hop đúng allowlist và kết thúc dự kiến |
| Redirect loop | A → B → A | Phát hiện loop, không retry vô hạn |
| POST + 303 | POST → /done | Request tiếp theo là GET |
| POST + 307 | POST → /target | Giữ method/body |
| POST + 308 | POST → /target | Giữ method/body |
| Cached permanent redirect | 301/308 cũ | Cache behavior đúng policy |

Bổ sung các trường hợp hợp lệ theo nghiệp vụ như locale path, query filter được allowlist, callback nội bộ và route fallback. Không chỉ kiểm tra danh sách payload xấu; cần bảo đảm luồng hợp lệ vẫn hoạt động.

## 11. Kiểm thử tự động

### 11.1. Unit test URL validator

Kiểm thử hàm validation độc lập với HTTP server:

```js
import assert from "node:assert/strict";

const BASE = "https://app.example.test";
const ALLOWED_PATHS = new Set([
  "/",
  "/dashboard",
  "/settings",
  "/done"
]);

function validateInternalRedirect(input) {
  if (
    typeof input !== "string" ||
    input.length === 0 ||
    input.length > 512 ||
    /[\u0000-\u001F\u007F\\]/.test(input)
  ) {
    return "/";
  }

  let target;

  try {
    target = new URL(input, BASE);
  } catch {
    return "/";
  }

  if (target.origin !== BASE) return "/";
  if (target.protocol !== "https:") return "/";
  if (target.username || target.password) return "/";
  if (!ALLOWED_PATHS.has(target.pathname)) return "/";
  if (target.search || target.hash) return "/";

  return target.pathname;
}

assert.equal(validateInternalRedirect("/dashboard"), "/dashboard");
assert.equal(
  validateInternalRedirect("https://app.example.test/settings"),
  "/settings"
);
assert.equal(validateInternalRedirect("//attacker.example"), "/");
assert.equal(validateInternalRedirect("https://attacker.example"), "/");
assert.equal(validateInternalRedirect("javascript:alert(1)"), "/");
assert.equal(
  validateInternalRedirect("https://app.example.test@attacker.example/"),
  "/"
);
assert.equal(validateInternalRedirect("/done?token=FAKE"), "/");
assert.equal(validateInternalRedirect("/done#secret"), "/");
assert.equal(validateInternalRedirect("/unknown"), "/");
assert.equal(validateInternalRedirect("/done\r\nX-Test: yes"), "/");

console.log("Redirect validator tests passed");
```

Unit test chứng minh logic validator với các input cụ thể. Nó không kiểm tra framework có ghi header đúng hay browser có follow chain như dự kiến.

### 11.2. Integration test: không tự follow redirect

Khi kiểm thử response đầu tiên, tắt tự động follow redirect để quan sát status và `Location`. Nếu client tự follow, test có thể chỉ thấy response cuối và bỏ qua endpoint trung gian độc hại.

Ví dụ Node.js:

```js
import assert from "node:assert/strict";

const base = "http://127.0.0.1:8080";

const response = await fetch(
  base + "/safe?next=%2Fdone",
  { redirect: "manual" }
);

assert.equal(response.status, 302);
assert.equal(response.headers.get("location"), "/done");

console.log("First redirect response is valid");
```

Trong browser Fetch API, manual redirect có thể trả response dạng opaque redirect và không cho đọc status/Location. Dùng Node.js integration test, browser automation navigation hoặc HTTP test client phù hợp để kiểm tra từng response.

### 11.3. Browser end-to-end test

Browser test cần xác nhận:

- URL bắt đầu.
- URL sau mỗi navigation.
- Origin cuối cùng.
- Trang hiển thị đúng sau login/logout.
- Không có vòng lặp.
- Method/body được xử lý đúng.
- Cookie chỉ gửi tới destination phù hợp.
- Referrer không chứa dữ liệu nhạy cảm.
- Back/forward history có hành vi mong đợi.

Với Playwright hoặc công cụ tương tự, có thể quan sát navigation request/response và kiểm tra URL cuối. Không chỉ assert text của trang; một trang giả có thể hiển thị nội dung giống trang thật.

### 11.4. Test server-side HTTP client

Nếu backend fetch URL và follow redirect, test riêng client đó:

- Tắt auto-follow để inspect từng hop.
- Giới hạn số hop.
- Resolve hostname và kiểm tra IP theo policy.
- Revalidate mỗi `Location`.
- Chặn loopback, private, link-local và metadata IP.
- Kiểm tra redirect từ HTTPS sang HTTP.
- Không forward Authorization/Cookie sang origin khác.
- Giới hạn response size và timeout.

DNS rebinding và thay đổi DNS giữa validation và connect cần được xem xét trong threat model SSRF. Chỉ kiểm tra hostname string không đủ để bảo vệ server-side fetch.

## 12. Lab local: kiểm tra open redirect

Lab tạo một HTTP server chỉ bind vào `127.0.0.1`. Endpoint `/unsafe` minh họa open redirect; `/safe` chỉ chấp nhận path đã allowlist; `/by-key` dùng route key. Không đưa endpoint lab lên internet hoặc dùng với token thật.

### 12.1. Tạo file server.mjs

```js
import { createServer } from "node:http";

const ORIGIN = "http://127.0.0.1:8080";

const ALLOWED_PATHS = new Set([
  "/",
  "/done",
  "/settings"
]);

const DESTINATIONS = new Map([
  ["home", "/"],
  ["done", "/done"],
  ["settings", "/settings"]
]);

function validateInternalRedirect(input) {
  if (
    typeof input !== "string" ||
    input.length === 0 ||
    input.length > 512 ||
    /[\u0000-\u001F\u007F\\]/.test(input)
  ) {
    return "/";
  }

  let target;

  try {
    target = new URL(input, ORIGIN);
  } catch {
    return "/";
  }

  if (target.origin !== ORIGIN) return "/";
  if (target.protocol !== "http:") return "/";
  if (target.username || target.password) return "/";
  if (!ALLOWED_PATHS.has(target.pathname)) return "/";
  if (target.search || target.hash) return "/";

  return target.pathname;
}

function sendRedirect(res, status, location) {
  res.writeHead(status, {
    Location: location,
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer"
  });
  res.end();
}

const server = createServer((req, res) => {
  const requestUrl = new URL(req.url, ORIGIN);

  if (requestUrl.pathname === "/unsafe") {
    const next = requestUrl.searchParams.get("next") || "/";
    // Chỉ minh họa lỗi open redirect trên loopback.
    sendRedirect(res, 302, next);
    return;
  }

  if (requestUrl.pathname === "/safe") {
    const next = requestUrl.searchParams.get("next");
    sendRedirect(res, 302, validateInternalRedirect(next));
    return;
  }

  if (requestUrl.pathname === "/by-key") {
    const key = requestUrl.searchParams.get("to");
    const destination = DESTINATIONS.get(key) || "/";
    sendRedirect(res, 302, destination);
    return;
  }

  if (requestUrl.pathname === "/post-303" && req.method === "POST") {
    sendRedirect(res, 303, "/done");
    return;
  }

  if (requestUrl.pathname === "/post-307" && req.method === "POST") {
    sendRedirect(res, 307, "/done");
    return;
  }

  if (requestUrl.pathname === "/post-308" && req.method === "POST") {
    sendRedirect(res, 308, "/done");
    return;
  }

  if (
    requestUrl.pathname === "/" ||
    requestUrl.pathname === "/done" ||
    requestUrl.pathname === "/settings"
  ) {
    res.writeHead(200, {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store"
    });
    res.end("Local redirect test page: " + requestUrl.pathname + " method=" + req.method);
    return;
  }

  res.writeHead(404, {
    "Content-Type": "text/plain; charset=utf-8"
  });
  res.end("Not found");
});

server.listen(8080, "127.0.0.1", () => {
  console.log("Redirect lab listening at " + ORIGIN);
});
```

### 12.2. Tạo file test-redirect.mjs

```js
import assert from "node:assert/strict";

const base = "http://127.0.0.1:8080";

async function checkRedirect(path, expectedStatus, expectedLocation, method = "GET") {
  const response = await fetch(base + path, {
    method,
    body: method === "POST" ? "sample=1" : undefined,
    redirect: "manual"
  });

  assert.equal(response.status, expectedStatus);
  assert.equal(
    response.headers.get("location"),
    expectedLocation
  );
}

await checkRedirect("/safe?next=%2Fdone", 302, "/done");
await checkRedirect("/safe?next=%2Fsettings", 302, "/settings");
await checkRedirect("/safe?next=https%3A%2F%2Fevil.example", 302, "/");
await checkRedirect("/safe?next=%2F%2Fevil.example", 302, "/");
await checkRedirect("/safe?next=javascript%3Aalert%281%29", 302, "/");
await checkRedirect("/safe?next=%2Fdone%3Ftoken%3DFAKE", 302, "/");
await checkRedirect("/safe?next=%2Fdone%0d%0aX-Test%3Ayes", 302, "/");
await checkRedirect("/safe?next=%5C%5Cevil.example", 302, "/");

await checkRedirect(
  "/by-key?to=done",
  302,
  "/done"
);
await checkRedirect(
  "/by-key?to=unknown",
  302,
  "/"
);

// Endpoint unsafe chỉ minh họa open redirect trong lab local.
await checkRedirect(
  "/unsafe?next=https%3A%2F%2Fevil.example",
  302,
  "https://evil.example"
);

// Kiểm tra status và Location đầu tiên của POST redirect.
await checkRedirect("/post-303", 303, "/done", "POST");
await checkRedirect("/post-307", 307, "/done", "POST");
await checkRedirect("/post-308", 308, "/done", "POST");

async function checkFollowedPost(path, expectedMethod) {
  const response = await fetch(base + path, {
    method: "POST",
    body: "sample=1",
    redirect: "follow"
  });

  assert.equal(response.status, 200);
  assert.equal(
    await response.text(),
    "Local redirect test page: /done method=" + expectedMethod
  );
}

await checkFollowedPost("/post-303", "GET");
await checkFollowedPost("/post-307", "POST");
await checkFollowedPost("/post-308", "POST");

console.log("All redirect integration checks passed");
```

### 12.3. Chạy lab

Mở terminal thứ nhất trong thư mục chứa `server.mjs`:

```bash
node server.mjs
```

Mở terminal thứ hai trong cùng thư mục:

```bash
node test-redirect.mjs
```

Mở browser và thử các URL:

```text
http://127.0.0.1:8080/safe?next=%2Fdone
http://127.0.0.1:8080/safe?next=https%3A%2F%2Fevil.example
http://127.0.0.1:8080/unsafe?next=https%3A%2F%2Fevil.example
http://127.0.0.1:8080/by-key?to=done
```

Ở endpoint `/unsafe`, browser rời khỏi loopback và chuyển sang hostname external trong `Location`; không cần mở website đó để test. Nếu browser chặn hoặc không có kết nối, vẫn có thể kiểm tra header bằng integration test.

### 12.4. Quan sát kết quả

- `/safe?next=%2Fdone` trả 302 với `Location: /done`.
- `/safe?next=https...` trả về `/` vì origin không được phép.
- Protocol-relative URL bị từ chối.
- `javascript:` và backslash bị từ chối.
- Query chứa token giả bị từ chối thay vì chuyển tiếp.
- `/by-key?to=done` chỉ chọn route đã khai báo.
- `/unsafe` cho thấy một input external được đưa thẳng vào `Location`.
- POST endpoint trả đúng status 303/307/308 để kiểm tra method semantics.

### 12.5. Giới hạn của lab

Lab minh họa URL validation và response đầu tiên. Nó không mô phỏng đầy đủ OAuth provider, cookie SameSite, CDN cache, browser history, proxy TLS termination hoặc SSRF. Không dùng code lab như một redirect library production mà chưa review theo framework, routing và policy của ứng dụng.

## 13. Kiểm tra redirect trong môi trường thực tế

Khi review một ứng dụng, lập danh sách mọi endpoint có khả năng redirect và truy vết nguồn dữ liệu đi vào `Location` hoặc client navigation.

### 13.1. Kiểm tra response đầu tiên

Dùng DevTools Network với Preserve log hoặc HTTP client tắt auto-follow. Ghi lại:

- Request method và URL.
- Response status.
- `Location`.
- `Set-Cookie` và cookie gửi ở request kế tiếp.
- `Cache-Control`.
- `Referrer-Policy`.
- Origin của từng hop.
- Request method/body sau redirect.

Không chỉ xem trang cuối cùng. Một redirect trung gian tới domain lạ vẫn là lỗi dù cuối cùng browser quay về app.

### 13.2. Kiểm tra browser history

Xác nhận `assign`, `replace`, HTTP redirect và SPA router tạo history như yêu cầu. Kiểm tra Back/Forward không gây vòng lặp hoặc gửi lại form. Với PRG, refresh trang kết quả không lặp thao tác ghi.

### 13.3. Kiểm tra nhiều tầng proxy

Reverse proxy, load balancer và application server có thể tạo redirect khác nhau. Kiểm tra scheme/host mà backend nhận, các header forwarded được tin cậy từ proxy nào và canonical host policy.

Không tin `X-Forwarded-Host` hoặc `Forwarded` từ client trực tiếp nếu request không đến từ proxy được cấu hình tin cậy. Giá trị host sai có thể làm ứng dụng tạo absolute redirect tới attacker domain.

### 13.4. Kiểm tra redirect do framework tạo

Framework có thể tự redirect khi:

- Thiếu trailing slash hoặc có slash thừa.
- Route không đúng case.
- HTTP được chuyển sang HTTPS.
- User chưa đăng nhập.
- Locale hoặc tenant thay đổi.
- Session hết hạn.
- Route không còn tồn tại.

Xác định redirect đến từ middleware, reverse proxy hay controller. Nếu chỉ kiểm thử controller, có thể bỏ sót redirect do tầng khác tạo.

### 13.5. Kiểm tra log mà không lộ dữ liệu

Có thể log status, route category, destination origin đã phân loại và request ID. Không log full query, authorization code, access token hoặc session identifier. Dùng structured logging và giới hạn quyền xem log.

## 14. Checklist review Redirect test

Trước khi phát hành:

1. **Inventory:** Đã tìm các tham số `next`, `returnUrl`, `redirect`, `continue`, `callback` chưa?
2. **Ownership:** Ai quyết định destination: server, client, router hay third-party provider?
3. **Validation:** URL có được parse bằng URL parser chuẩn không?
4. **Origin:** Có so sánh origin chính xác gồm scheme/host/port không?
5. **Scheme:** Có từ chối `javascript:`, `data:`, `file:` và scheme không cần thiết không?
6. **Userinfo:** Có xử lý username/password trong URL không?
7. **Protocol-relative:** Có test `//host/path` không?
8. **Backslash/control:** Có reject backslash, CR, LF, NUL và control character không?
9. **Path/query:** Có allowlist route và query key cần thiết không?
10. **Fallback:** Input không hợp lệ có về destination nội bộ an toàn không?
11. **OAuth:** redirect_uri có khớp callback đã đăng ký; state và PKCE có được xác minh không?
12. **Token:** Code/token có bị chuyển tiếp, log hoặc đưa vào analytics không?
13. **Status:** 301/302/303/307/308 có đúng semantics không?
14. **Method:** POST/PUT có bị đổi method hoặc forward body ngoài ý muốn không?
15. **Chain:** Có kiểm tra mọi hop và redirect loop không?
16. **Cache:** Redirect permanent có cache policy phù hợp không?
17. **Cookies:** Cookie có chỉ được gửi tới domain/path phù hợp không?
18. **Referrer:** Destination cross-origin có nhận URL nguồn nhạy cảm không?
19. **Proxy:** Host/scheme forwarded có chỉ được tin từ proxy hợp lệ không?
20. **SSRF:** Server-side fetch có revalidate mỗi redirect hop và giới hạn private IP không?
21. **Automation:** Integration test có tắt auto-follow để kiểm tra Location đầu tiên không?
22. **Browser:** E2E test có xác minh origin cuối, history và method không?
23. **Logging:** Log có tránh full URL, token và PII không?

## 15. Những hiểu lầm phổ biến

| Nhận định sai | Cách hiểu đúng |
|---|---|
| Redirect chỉ là điều hướng giao diện. | HTTP redirect có thể chuyển request, method, dữ liệu và browser context sang đích mới. |
| URL bắt đầu bằng domain tin cậy thì an toàn. | Userinfo, suffix và protocol-relative URL có thể làm host thực tế khác dự kiến. |
| startsWith() đủ để kiểm tra origin. | Phải parse URL và so sánh origin chính xác. |
| Chỉ cần chặn http:// là hết open redirect. | //host, backslash và scheme khác vẫn cần kiểm tra. |
| Location luôn là absolute URL. | URI tương đối cũng hợp lệ và được giải quyết theo URL hiện tại. |
| Mọi 3xx đều có cùng hành vi. | 301/302/303/307/308 có semantics khác nhau, đặc biệt với method/body. |
| 307 giống 302. | 307 giữ method/body; 302 có hành vi lịch sử có thể đổi POST thành GET. |
| 301 chỉ ảnh hưởng một request. | Redirect permanent có thể được cache và ảnh hưởng các lần truy cập sau. |
| Open redirect tự động làm lộ cookie của app. | Cookie không tự chuyển sang origin khác; rủi ro thường qua phishing, token/URL hoặc thao tác tiếp theo. |
| OAuth redirect_uri chỉ cần cùng domain. | Cần callback URI khớp chính xác theo cấu hình và policy provider. |
| Có state thì không cần allowlist redirect. | State không thay thế kiểm tra destination/callback. |
| Browser test chứng minh backend fetch an toàn. | Server-side fetch có rủi ro SSRF và cần kiểm tra từng hop/IP. |
| Kiểm tra URL đầu tiên là đủ. | Redirect chain có thể chứa một hop độc hại ở giữa. |
| Browser tự dừng loop nên không cần test. | Ứng dụng cần phát hiện loop và giới hạn hop theo policy. |
| Redirect nội bộ không thể lộ dữ liệu. | Query, fragment, referrer, logs và third-party scripts vẫn có thể làm lộ dữ liệu. |

## 16. Câu hỏi ôn tập

1. Redirect test kiểm tra những hành vi nào?
2. HTTP redirect khác client-side redirect ở điểm nào?
3. Open redirect là gì và có thể bị lợi dụng ra sao?
4. Vì sao route key an toàn hơn nhận URL tự do?
5. 301, 302, 303, 307 và 308 khác nhau thế nào?
6. Khi nào dùng 303 cho Post/Redirect/Get?
7. Vì sao 307/308 cần thận trọng với POST body?
8. Protocol-relative URL có dạng nào?
9. Userinfo có thể làm người đọc nhầm hostname ra sao?
10. Vì sao startsWith() không đủ để kiểm tra domain?
11. URL parser chuẩn giúp xử lý điều gì và không giải quyết điều gì?
12. Vì sao cần reject backslash và control characters trước khi tạo Location?
13. Redirect chain và redirect loop khác nhau thế nào?
14. Redirect permanent có tác động cache nào?
15. OAuth redirect_uri, state và PKCE bảo vệ các mục tiêu nào?
16. Vì sao không chuyển tiếp authorization code hoặc token qua redirect không cần thiết?
17. Cookie và Referer được xử lý thế nào khi chuyển origin?
18. Server-side fetch theo redirect có thể tạo SSRF ra sao?
19. Vì sao integration test cần tắt auto-follow?
20. Browser E2E test cần xác minh những điều gì?

**Đáp án định hướng:** (1) Status, Location, method/body, destination, chain, loop và browser context. (2) HTTP redirect là response 3xx; client-side redirect do JavaScript/router điều khiển. (3) Server/client chuyển tới URL attacker chọn mà không kiểm tra. (4) Server ánh xạ key sang path cố định. (5) 301/308 permanent, 302/307 temporary, 303 chuyển sang GET/HEAD; 307/308 giữ method/body. (6) Sau POST ghi dữ liệu để điều hướng GET tới trang kết quả. (7) Body có thể được gửi tiếp tới destination. (8) //host/path. (9) Host thật nằm sau dấu @. (10) Prefix có thể khớp domain giả hoặc suffix độc hại. (11) Parser chuẩn hóa cú pháp; ứng dụng vẫn phải kiểm tra scheme/origin/path. (12) Tránh parser mismatch và header injection. (13) Chain là nhiều hop; loop là quay lại route đã đi qua. (14) Client/proxy có thể lưu 301/308. (15) redirect_uri giới hạn callback; state liên kết request/response; PKCE bảo vệ authorization code. (16) Tránh lộ qua URL, referrer, logs và analytics. (17) Cookie được chọn theo domain/path/SameSite/Secure; Referer theo policy. (18) Server follow tới private/metadata address sau redirect. (19) Để nhìn thấy status và Location của response đầu tiên. (20) Origin cuối, từng hop, history, cookie, method/body và loop.

## 17. Tài liệu tham khảo

- [RFC 9110 — HTTP Semantics, Redirection 3xx](https://www.rfc-editor.org/rfc/rfc9110#section-15.4): Ý nghĩa các status code redirect và header Location.
- [WHATWG URL Standard](https://url.spec.whatwg.org/): Parsing, serialization và URL normalization trong browser.
- [MDN — Redirections in HTTP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Redirections): Tổng quan redirect HTTP và status code.
- [MDN — Location](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Location): Header đích cho response redirect.
- [MDN — URL API](https://developer.mozilla.org/en-US/docs/Web/API/URL): Parse URL và đọc origin/protocol/hostname.
- [OWASP — Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): Phòng open redirect và unvalidated forward.
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): Bảo vệ server-side request và redirect.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): Bảo vệ OAuth redirect, authorization code và client flow.
- [OpenID Connect RP-Initiated Logout](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): Quy tắc logout và post_logout_redirect_uri.
- [MDN — SameSite cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie#samesitesamesite-value): Cookie behavior trong same-site/cross-site context.
- [MDN — Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Referrer-Policy): Giới hạn referrer khi điều hướng.
- [Node.js — URL](https://nodejs.org/api/url.html): URL parser chuẩn trong Node.js.
- [Node.js — HTTP](https://nodejs.org/api/http.html): Tạo response và header HTTP cho lab.

**Kết nối với mô hình bảo mật web:** Redirect làm browser tạo request mới tới đích được chỉ định bởi server hoặc client. Vì vậy, kiểm thử phải xác minh status, Location, origin, method/body và mọi hop trong chain. Open redirect được giảm thiểu bằng route key hoặc allowlist chính xác; OAuth callback cần URI đã đăng ký cùng state/PKCE; server-side fetch phải kiểm tra redirect từng bước để tránh SSRF. Cookie và referrer tiếp tục tuân theo policy của browser, nên không chuyển secret qua URL và không ghi full destination vào log.
