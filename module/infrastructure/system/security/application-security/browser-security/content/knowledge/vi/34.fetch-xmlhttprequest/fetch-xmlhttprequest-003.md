# Credentials mode — kiểm soát credential trong Fetch và XMLHttpRequest

> **Chương:** Fetch và XMLHttpRequest  
> **Mục tiêu:** Hiểu credentials mode của Fetch, phân biệt `omit`, `same-origin` và `include`; biết credential ảnh hưởng tới request và response cookie như thế nào; cấu hình credentialed CORS và preflight; đối chiếu với `XMLHttpRequest.withCredentials`; hiểu giới hạn của SameSite và third-party cookie; phòng CSRF, rò rỉ cache và kiểm thử bằng DevTools.

## 1. Credentials mode là gì?

Khi browser gửi request, ngoài URL, method và body, request có thể mang thông tin xác thực như cookie, HTTP authentication state hoặc TLS client certificate. Những thông tin này được gọi chung là **credentials** trong Fetch model.

Credentials mode quyết định browser có gửi credentials cùng request hay không và có chấp nhận một số credential từ response hay không. Đây là một phần của mô hình Fetch, đặc biệt quan trọng khi request đi tới origin khác.

Ví dụ:

```js
const response = await fetch("https://api.example.net/profile", {
  credentials: "include",
});
```

Ở đây, ứng dụng yêu cầu Fetch sử dụng credentials kể cả khi URL khác origin. Điều đó vẫn chịu các giới hạn khác như CORS, cookie attributes, third-party cookie policy, secure context và chính sách quyền riêng tư của browser.

**Credentials mode không phải authorization.** Nó chỉ điều khiển việc browser sử dụng thông tin xác thực trong request/response. Server vẫn phải xác minh danh tính, session và quyền truy cập tài nguyên.

## 2. Credentials gồm những gì?

Trong ngữ cảnh Fetch, credentials thường bao gồm:

- **Cookies:** cookie phiên, cookie đăng nhập và cookie khác phù hợp với URL/request context.
- **HTTP authentication entries:** thông tin xác thực HTTP do browser quản lý, ví dụ trạng thái xác thực Basic/Digest theo cơ chế browser.
- **TLS client certificates:** chứng thư client nếu kết nối và môi trường sử dụng cơ chế xác thực này.

Một header do ứng dụng tự đặt như bearer token trong `Authorization` cần được quản lý rõ ràng ở tầng ứng dụng và CORS. Không giả định chỉ cần đặt `credentials: "include"` là browser tự tạo access token hoặc tự thêm header authorization của API.

Credentials cũng không đồng nghĩa với mọi header trong request. Ví dụ `Origin`, `Accept` hoặc `Content-Type` là metadata/request headers; chúng không phải cookie hay thông tin xác thực chỉ vì xuất hiện trong request.

## 3. Ba credentials mode của Fetch

Fetch hỗ trợ ba giá trị:

| Mode | Gửi credentials | Xử lý credential từ response |
| --- | --- | --- |
| `omit` | Không gửi credentials | Không sử dụng credentials từ response |
| `same-origin` | Chỉ gửi credentials cho request same-origin | Chỉ sử dụng credentials từ response same-origin |
| `include` | Cho phép gửi credentials cả với request cross-origin | Cho phép sử dụng credentials từ response, theo các policy khác của browser |

Ví dụ:

```js
// Không gửi credentials, kể cả request same-origin.
fetch("/public-data", { credentials: "omit" });

// Chỉ gửi credentials khi URL cùng origin với document.
fetch("/account", { credentials: "same-origin" });

// Cho phép credentials cả khi URL khác origin.
fetch("https://api.example.net/account", {
  credentials: "include",
});
```

Giá trị mặc định của Fetch là `same-origin`. Vì vậy, request same-origin thông thường có thể mang cookie phù hợp; request cross-origin mặc định không tự gửi cookie chỉ vì browser đang có cookie của host đích.

## 4. Mode omit

`omit` yêu cầu Fetch không sử dụng credentials cho request:

```js
const response = await fetch("https://cdn.example.net/catalog.json", {
  credentials: "omit",
});

const catalog = await response.json();
```

Mode này phù hợp khi tải dữ liệu công khai hoặc tài nguyên không cần gắn với session của người dùng.

Những điểm cần nhớ:

- Browser không gửi cookie phù hợp cùng request.
- Browser không sử dụng credential response như cookie được đặt từ response đó.
- Server không thể dựa vào cookie phiên để nhận diện người dùng qua request này.
- CORS vẫn áp dụng nếu request là cross-origin và JavaScript cần đọc response.
- `omit` không xóa cookie đã lưu trong browser; nó chỉ điều khiển request hiện tại.

Nếu ứng dụng tự thêm một header như `Authorization`, hãy xem đó là credential do ứng dụng chủ động cung cấp và kiểm tra quy tắc header/CORS tương ứng. Không dùng `omit` như một cách xóa hoặc thu hồi token trong storage.

## 5. Mode same-origin

`same-origin` là giá trị mặc định của Fetch:

```js
const response = await fetch("/api/me", {
  credentials: "same-origin",
});
```

Với request same-origin, browser có thể gửi cookie và credentials phù hợp. Nếu request chuyển tới origin khác, browser không gửi credentials theo mode này.

Ví dụ document tại `https://app.example.com`:

| Request URL | Quan hệ | Credentials với `same-origin` |
| --- | --- | --- |
| `https://app.example.com/api/me` | Same-origin | Có thể gửi credentials phù hợp |
| `https://app.example.com:8443/api/me` | Khác origin | Không gửi |
| `https://api.example.com/me` | Khác origin | Không gửi |
| `http://app.example.com/api/me` | Khác origin | Không gửi |

Mode này thường phù hợp với ứng dụng gọi API cùng origin bằng session cookie. Nó không có nghĩa browser sẽ gửi mọi cookie; cookie vẫn phải khớp Domain/Path, Secure, SameSite, expiry và các chính sách browser khác.

## 6. Mode include

`include` cho phép Fetch gửi credentials kể cả với URL cross-origin:

```js
const response = await fetch("https://api.example.net/profile", {
  method: "GET",
  credentials: "include",
});

const profile = await response.json();
```

Server đích phải cấu hình CORS credentialed phù hợp nếu JavaScript cần đọc response. Ngoài ra, browser chỉ gửi cookie khi cookie policy cho phép trong request context đó.

`include` không đảm bảo cookie chắc chắn được gửi. Cookie có thể bị loại vì:

- Không khớp Domain hoặc Path.
- Thiếu `Secure` khi request yêu cầu HTTPS.
- `SameSite` không cho phép cookie trong ngữ cảnh cross-site.
- Third-party cookie bị browser hoặc người dùng chặn.
- Cookie đã hết hạn hoặc bị xóa.
- Storage/cookie partitioning làm cookie thuộc partition khác.

Vì vậy, hãy kiểm tra request thực tế trong DevTools và không suy ra cookie đã được gửi chỉ từ việc code đặt `credentials: "include"`.

## 7. Credentials mode ảnh hưởng cả response

Credentials mode không chỉ quyết định dữ liệu được gửi lên server. Nó còn ảnh hưởng việc Fetch có sử dụng credentials từ response hay không.

Ví dụ server trả:

```http
Set-Cookie: session_id=opaque-value; Path=/; Secure; HttpOnly; SameSite=None
```

Nếu request dùng credentials mode phù hợp và các policy cookie cho phép, browser có thể xử lý Set-Cookie. Nếu request dùng `omit` hoặc `same-origin` cho một response cross-origin, cookie từ response đó không được xử lý như credential của Fetch.

JavaScript không thể đọc `Set-Cookie` bằng `response.headers.get("Set-Cookie")`. Đây là response header bị cấm truy cập từ frontend script; browser tự xử lý cookie theo quy tắc.

Ngay cả khi response CORS thành công, điều đó không có nghĩa JavaScript được đọc giá trị Set-Cookie.

## 8. CORS cần thiết cho credentialed cross-origin Fetch

Giả sử trang chạy tại `https://app.example.com` và gọi API tại `https://api.example.net`:

```js
const response = await fetch("https://api.example.net/profile", {
  credentials: "include",
});
```

Nếu API muốn cho JavaScript của app đọc response có credentials, server cần trả origin cụ thể và cho phép credentials:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Các điều kiện quan trọng:

- `Access-Control-Allow-Origin` phải là origin cụ thể được phép, không phải `*`.
- `Access-Control-Allow-Credentials` phải có giá trị `true`.
- Nếu response thay đổi theo request Origin, dùng `Vary: Origin` và cấu hình cache/CDN tương ứng.
- Server phải kiểm tra Origin bằng allowlist; không phản chiếu mọi giá trị client gửi.
- Cookie vẫn chịu SameSite, Secure và third-party cookie restrictions.

Nếu CORS check thất bại, JavaScript không được đọc response. Request có thể đã được gửi và server có thể đã thực hiện hành động; CORS không phải authorization hay CSRF defense.

## 9. Vì sao wildcard không hợp lệ với credentials?

Response sau không hợp lệ cho credentialed CORS:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Khi credentials mode là `include`, browser yêu cầu `Access-Control-Allow-Origin` khớp chính xác origin của caller. Wildcard không thể biểu thị rằng server đã tin cậy một origin cụ thể khi chia sẻ response có credentials.

Ví dụ đúng cho một ứng dụng:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Nếu hỗ trợ nhiều ứng dụng, server có thể:

1. Đọc request Origin.
2. So sánh với allowlist cấu hình phía server.
3. Nếu được phép, trả đúng một origin đã xác minh trong ACAO.
4. Trả `Vary: Origin` để cache biết response phụ thuộc Origin.
5. Từ chối hoặc không cấp CORS permission cho origin không được phép.

Không làm:

```js
// Không an toàn: phản chiếu Origin mà không xác minh.
res.setHeader("Access-Control-Allow-Origin", req.headers.origin);
res.setHeader("Access-Control-Allow-Credentials", "true");
```

Phản chiếu tùy tiện có thể biến mọi website thành origin được phép đọc response credentialed.

## 10. Preflight và credentials

Một request CORS có method hoặc header không thuộc nhóm đơn giản có thể cần preflight OPTIONS trước actual request.

Ví dụ:

```js
fetch("https://api.example.net/orders", {
  method: "PUT",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-Request-Id": "req-123",
  },
  body: JSON.stringify({ status: "confirmed" }),
});
```

Browser có thể gửi preflight:

```http
OPTIONS /orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: content-type,x-request-id
```

Preflight request không mang credentials của actual request. Tuy nhiên, response preflight phải cho phép origin, method và header cần thiết; với actual request dùng credentials, response CORS phải đáp ứng điều kiện credentialed CORS, bao gồm `Access-Control-Allow-Credentials: true` và origin cụ thể.

Ví dụ response preflight:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: PUT
Access-Control-Allow-Headers: Content-Type, X-Request-Id
Access-Control-Max-Age: 600
Vary: Origin
```

Sau khi preflight thành công, browser mới gửi actual request theo CORS protocol. Nếu preflight thất bại, actual request không được gửi trong flow đó.

Không yêu cầu preflight endpoint xác thực bằng cookie của actual request; preflight vốn không mang credentials. Hãy cấu hình OPTIONS để trả policy CORS đúng và bảo vệ actual endpoint bằng authentication/authorization.

## 11. Preflight không phải biện pháp CSRF đầy đủ

Không phải mọi cross-origin request đều cần preflight. Một số request đơn giản, form submission hoặc navigation có thể được gửi mà không cần preflight.

Do đó:

- CORS chủ yếu kiểm soát việc JavaScript đọc response.
- Preflight giới hạn một số request không đơn giản trước khi actual request được gửi.
- CORS không đảm bảo server không nhận request cross-site.
- CORS không thay CSRF token, SameSite cookie hoặc kiểm tra Origin.

Endpoint thay đổi trạng thái dựa trên cookie phiên cần CSRF protection phù hợp. Không dựa vào việc response không đọc được để kết luận thao tác không xảy ra.

## 12. SameSite cookie có thể ngăn cookie dù dùng include

Cookie có thuộc tính SameSite:

```http
Set-Cookie: session=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
```

Các giá trị phổ biến:

| Giá trị | Hành vi khái quát |
| --- | --- |
| `Strict` | Hạn chế gửi cookie trong các ngữ cảnh cross-site |
| `Lax` | Cho phép một số điều hướng top-level an toàn; hạn chế nhiều request cross-site khác |
| `None` | Cho phép cookie trong ngữ cảnh cross-site theo SameSite, thường phải kèm `Secure` |

Nếu cookie là `SameSite=Lax` hoặc `Strict`, Fetch cross-site dùng `credentials: "include"` vẫn không ép browser gửi cookie trái với SameSite policy.

Đối với cookie cần dùng cross-site:

```http
Set-Cookie: session=opaque; Path=/; Secure; HttpOnly; SameSite=None
```

Nhưng `SameSite=None; Secure` chỉ đáp ứng điều kiện SameSite; browser vẫn có thể chặn third-party cookie theo privacy settings hoặc chính sách nền tảng.

## 13. Third-party cookie blocking và storage partitioning

Một request có thể là cross-origin và cũng là third-party trong ngữ cảnh trang nhúng. Browser hiện đại có thể chặn hoặc phân vùng cookie/storage bên thứ ba để giảm tracking.

Ví dụ:

- Top-level site: `https://news.example`.
- Iframe/API: `https://accounts.partner.example`.
- Iframe gọi API với `credentials: "include"`.

Dù code yêu cầu include, cookie bên thứ ba có thể không được gửi nếu browser hoặc người dùng chặn third-party cookies. Một số browser có cơ chế partitioned cookies/storage; dữ liệu có thể được phân vùng theo top-level site thay vì chia sẻ toàn cục.

Điều đó có nghĩa cùng một embedded origin có thể có trạng thái khác nhau khi được nhúng trong hai top-level site khác nhau.

Không xây dựng đăng nhập hoặc nhận diện người dùng dựa trên giả định third-party cookie luôn khả dụng. Ưu tiên kiến trúc first-party, redirect/login flow phù hợp hoặc cơ chế storage access có điều kiện khi sản phẩm thực sự cần.

## 14. Partitioned cookie và CHIPS

Cookie có thuộc tính `Partitioned` (CHIPS) được thiết kế để lưu trạng thái cookie theo partition key, thường gắn với top-level site:

```http
Set-Cookie: widget_session=opaque; Secure; HttpOnly; SameSite=None; Partitioned; Path=/
```

Cookie partitioned cho phép một số tích hợp nhúng duy trì trạng thái riêng cho từng top-level site mà không chia sẻ cùng một cookie bên thứ ba trên mọi website.

Điều cần nhớ:

- Hỗ trợ và chi tiết hành vi phụ thuộc browser.
- `Partitioned` không thay CORS.
- Cookie vẫn cần thuộc tính và điều kiện phù hợp, thường gồm `Secure` và `SameSite=None`.
- Partitioning không biến iframe thành same-origin với parent.
- Không dùng cookie partitioned làm cơ chế authorization duy nhất; server vẫn xác minh session và quyền.

Khi debug, xác định top-level site, embedded origin, cookie attributes và browser support. Không kết luận cookie bị mất chỉ từ việc không thấy nó trong một partition khác.

## 15. Fetch credentials và cookie attributes

Ngay cả khi Fetch dùng `include`, cookie chỉ được gửi nếu mọi điều kiện liên quan đều thỏa:

| Điều kiện | Câu hỏi |
| --- | --- |
| Domain | Host request có khớp cookie host/domain không? |
| Path | Request path có khớp cookie Path không? |
| Secure | Cookie Secure có được gửi qua HTTPS không? |
| SameSite | Ngữ cảnh request có cho phép cookie không? |
| Expiry | Cookie còn hiệu lực không? |
| Third-party policy | Browser/người dùng có chặn cookie bên thứ ba không? |
| Partition key | Cookie thuộc partition của top-level site hiện tại không? |

Vì vậy, credentials mode là một điều kiện trong nhiều điều kiện. Nó không ghi đè cookie matching hoặc privacy policy.

## 16. Đối chiếu XMLHttpRequest.withCredentials

XMLHttpRequest dùng thuộc tính `withCredentials` để điều khiển credentialed CORS request:

```js
const xhr = new XMLHttpRequest();
xhr.open("GET", "https://api.example.net/profile");
xhr.withCredentials = true;
xhr.onload = () => {
  console.log(xhr.status, xhr.responseText);
};
xhr.onerror = () => {
  console.error("Request hoặc CORS thất bại");
};
xhr.send();
```

Khác biệt quan trọng:

| API | Cấu hình credentials | Mặc định |
| --- | --- | --- |
| Fetch | `credentials: "omit" / "same-origin" / "include"` | `same-origin` |
| XMLHttpRequest | `xhr.withCredentials = true/false` | `false` cho cross-origin credential sharing |

Với XHR, `withCredentials` chủ yếu điều khiển việc gửi credentials trong request cross-origin và việc chấp nhận cookie từ response cross-origin. Đối với same-origin request, thuộc tính này không làm thay đổi cách browser gửi credentials same-origin.

Vì vậy, không diễn giải `withCredentials = false` thành “XHR không bao giờ gửi cookie”. Same-origin XHR vẫn có thể gửi cookie phù hợp theo quy tắc browser.

## 17. XHR: đặt withCredentials trước send

Hãy đặt thuộc tính trước khi gửi request:

```js
const xhr = new XMLHttpRequest();
xhr.open("GET", "https://api.example.net/profile");
xhr.withCredentials = true;
xhr.responseType = "json";

xhr.onload = () => {
  if (xhr.status >= 200 && xhr.status < 300) {
    renderProfile(xhr.response);
  } else {
    showError("Không tải được profile.");
  }
};

xhr.onerror = () => showError("Network hoặc CORS error.");
xhr.send();
```

Nếu đặt `withCredentials` sau `send()`, quá muộn để thay đổi request đã gửi. Đặt thuộc tính sau `open()` và trước `send()` để code dễ đọc.

Với cross-origin XHR có `withCredentials = true`, server vẫn phải trả:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Nếu response không đáp ứng CORS, JavaScript không được phép đọc response dù server có thể đã nhận request.

## 18. So sánh Fetch và XHR theo tình huống

| Tình huống | Fetch | XHR |
| --- | --- | --- |
| Same-origin API dùng session cookie | Mặc định `same-origin` thường đủ | Same-origin credentials được gửi theo quy tắc browser; withCredentials không cần bật chỉ vì cùng origin |
| Cross-origin API không cần cookie | `credentials: "omit"` hoặc mặc định same-origin | `withCredentials = false` |
| Cross-origin API cần cookie | `credentials: "include"` | `withCredentials = true` |
| Cross-origin response cần đọc | CORS response phải hợp lệ | CORS response phải hợp lệ |
| Credentialed CORS | ACAO cụ thể + ACAC true | ACAO cụ thể + ACAC true |
| Third-party cookie bị browser chặn | Include không vượt qua policy | withCredentials không vượt qua policy |

Fetch và XHR đều chịu CORS, cookie policy và server authorization. Chọn API theo nhu cầu ứng dụng; không chọn XHR chỉ để né CORS hoặc cookie restrictions.

## 19. Explicit Authorization header khác credentials mode

Ứng dụng có thể tự thêm bearer token:

```js
fetch("https://api.example.net/data", {
  headers: {
    Authorization: "Bearer " + accessToken,
  },
});
```

Đây là header do ứng dụng cung cấp. Nó không được browser tự tạo chỉ vì đặt credentials mode là `include`.

Header `Authorization` thường khiến request cross-origin cần preflight và server phải cho phép header đó:

```http
Access-Control-Allow-Headers: Authorization, Content-Type
```

Không đưa token vào URL query string. URL có thể xuất hiện trong history, logs, analytics hoặc Referer tùy ngữ cảnh. Giữ token trong cơ chế quản lý credential phù hợp và gửi qua kênh HTTPS.

Nếu dùng cookie session, vẫn cần CSRF protection. Nếu dùng bearer token, vẫn cần bảo vệ token khỏi XSS, logging và storage không an toàn.

## 20. Credentials, CSRF và authorization

Credentialed request làm browser tự đính kèm thông tin phiên trong một số ngữ cảnh. Đây là lý do cookie-based session cần CSRF protection.

Ví dụ trang khác có thể cố tạo request tới endpoint thay đổi trạng thái. Ngay cả khi script của trang đó không đọc được response do CORS, request đơn giản vẫn có thể được gửi.

Các lớp phòng vệ:

- CSRF token gắn với session và được xác minh ở server.
- Cookie SameSite phù hợp.
- Kiểm tra Origin/Referer theo chính sách server khi phù hợp.
- Fetch Metadata như `Sec-Fetch-Site` như một tín hiệu bổ sung.
- Không dùng GET để thay đổi trạng thái.
- Xác minh authentication, authorization và resource ownership ở server.
- CORS allowlist chính xác cho các client cần đọc response.

Không coi `credentials: "omit"` ở một frontend là CSRF defense cho endpoint. Attacker có thể tạo request từ một client khác hoặc dùng form/navigation không phụ thuộc code Fetch của ứng dụng.

## 21. Redirect và credentials

Fetch có thể gặp redirect từ URL ban đầu sang URL khác origin. Browser áp dụng quy tắc Fetch/CORS/credentials cho request trong chuỗi redirect; không nên giả định credentials sẽ được chuyển tới mọi host trong redirect chain.

Các nguyên tắc triển khai:

- Tránh redirect API credentialed sang host không thuộc allowlist.
- Không đặt session token trong query string để chuyển qua redirect.
- Kiểm tra origin cuối cùng và response CORS của endpoint đích.
- Không cho endpoint redirect do người dùng kiểm soát dẫn tới host tùy ý.
- Với redirect cross-origin, xem Network để biết request nào thực sự được gửi và cookie nào được browser chọn.

Redirect không biến hai origin thành một. Server đích vẫn phải xác thực request và CORS policy của nó.

## 22. Cache và response chứa dữ liệu theo credential

Response khác nhau theo session hoặc người dùng không nên bị cache dùng chung ngoài ý muốn.

Ví dụ response profile:

```http
Cache-Control: private, no-store
Vary: Origin
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
```

`private` hạn chế shared cache lưu response; `no-store` yêu cầu cache không lưu response. Chọn policy theo dữ liệu và kiến trúc cache.

Nếu ACAO thay đổi theo request Origin, `Vary: Origin` giúp cache phân biệt biến thể. Tuy nhiên, CDN có thể có cache key riêng; phải cấu hình và kiểm thử cache thực tế.

Không cache response credentialed dưới một key chỉ dựa vào URL nếu nội dung thay đổi theo cookie/session. Nếu cache sai, dữ liệu của một user có thể bị phục vụ cho user khác.

## 23. Ví dụ hoàn chỉnh: Fetch credentialed CORS

Frontend:

```js
async function loadAccount() {
  const response = await fetch("https://api.example.net/account", {
    method: "GET",
    credentials: "include",
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error("Account request failed: " + response.status);
  }

  return response.json();
}
```

Server response:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
Cache-Control: private, no-store
```

Cookie được thiết lập trước đó trên API host có thể được gửi nếu Domain/Path, Secure, SameSite, expiry, partitioning và third-party policy đều cho phép.

Nếu frontend và API khác site, cookie cross-site thường cần cấu hình phù hợp như `SameSite=None; Secure`, nhưng browser vẫn có thể chặn third-party cookies. Hãy kiểm thử trên browser mục tiêu.

## 24. Ví dụ XHR credentialed CORS

Frontend:

```js
function loadAccountWithXHR() {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("GET", "https://api.example.net/account");
    xhr.withCredentials = true;
    xhr.responseType = "json";

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.response);
      } else {
        reject(new Error("HTTP " + xhr.status));
      }
    };

    xhr.onerror = () => reject(new Error("Network hoặc CORS error"));
    xhr.send();
  });
}
```

Server cần cùng nguyên tắc CORS credentialed như Fetch: origin cụ thể, ACAC true và cache variation phù hợp.

Same-origin XHR không cần bật `withCredentials` chỉ để gửi cookie same-origin. Thuộc tính này có ý nghĩa chủ yếu khi request cross-origin.

## 25. Kiểm thử credentials mode bằng DevTools

Thực hành trong staging hoặc lab với hai origin do bạn kiểm soát, ví dụ `https://app.example.test` và `https://api.example.test`. Dùng cookie giả lập, không dùng session thật hoặc dữ liệu tài khoản thật.

### Bước 1 — Tạo endpoint và cookie thử nghiệm

API lab đặt cookie không nhạy cảm với các biến thể:

- SameSite=Lax.
- SameSite=None; Secure.
- Partitioned nếu browser hỗ trợ.

Ghi lại host, Path, Domain, expiry và thuộc tính Secure/HttpOnly.

### Bước 2 — So sánh Fetch modes

Từ app origin, gửi ba request tới API:

```js
fetch(API_URL, { credentials: "omit" });
fetch(API_URL, { credentials: "same-origin" });
fetch(API_URL, { credentials: "include" });
```

Trong Network, kiểm tra cookie request có được gửi hay không và so sánh response.

### Bước 3 — Kiểm tra CORS

Thử:

- ACAO khớp origin cụ thể + ACAC true.
- ACAO wildcard + ACAC true.
- Thiếu ACAC.
- Origin không nằm trong allowlist.

Quan sát CORS error và xác định request đã tới server hay chưa.

### Bước 4 — Kiểm tra preflight

Gửi PUT hoặc custom header để kích hoạt OPTIONS. Xác minh preflight không mang cookie credentials, response cho phép method/header và actual request chỉ được gửi khi preflight thành công.

### Bước 5 — So sánh XHR

Gửi XHR cross-origin với `withCredentials=false` rồi `true`. Sau đó thử same-origin XHR với cả hai giá trị để quan sát việc thuộc tính không làm thay đổi gửi credentials same-origin.

### Bước 6 — Thử SameSite và third-party policy

Nhúng API/widget trong top-level site khác. Thử cookie Lax, Strict, None; Secure và kiểm tra browser có chặn third-party cookie hay partition cookie không.

### Bước 7 — Kiểm tra response Set-Cookie

Quan sát Application/Storage và cookie jar. Thử đọc `response.headers.get("Set-Cookie")` trong JavaScript; xác minh script không được phép đọc header này. Kiểm tra cookie thực tế được browser lưu hay bị từ chối.

## 26. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Fetch cross-origin không gửi cookie | Mode mặc định same-origin hoặc cookie policy chặn | Dùng include khi cần và kiểm tra cookie attributes/browser policy |
| Đặt include nhưng cookie vẫn không xuất hiện | SameSite, Secure, Domain, Path, expiry hoặc third-party blocking | Kiểm tra cookie jar và request context |
| CORS báo lỗi khi credentials include | ACAO wildcard, thiếu ACAC true hoặc origin không khớp | Trả origin cụ thể và ACAC true |
| Preflight thất bại | OPTIONS thiếu allow-method/header hoặc CORS response | Cấu hình preflight; không yêu cầu cookie trên OPTIONS |
| Actual request không được gửi | Preflight không thành công | Xem OPTIONS trong Network và sửa policy |
| Server xử lý request nhưng JavaScript báo CORS | Response không vượt CORS check | Kiểm tra server response; đánh giá CSRF/side effect riêng |
| XHR không gửi cookie cross-origin | withCredentials chưa bật hoặc cookie bị chặn | Đặt true trước send và kiểm tra server CORS |
| XHR same-origin không có cookie | Cookie attributes/session không hợp lệ hoặc bị xóa | Kiểm tra cookie host/path/Secure/expiry |
| Không đọc được Set-Cookie từ Fetch | Header bị cấm truy cập từ frontend script | Kiểm tra cookie trong browser storage; không đọc header bằng JS |
| Third-party cookie hoạt động ở browser này nhưng không ở browser khác | Privacy policy và partitioning khác nhau | Thiết kế không phụ thuộc third-party cookie toàn cục |
| CDN trả ACAO sai origin | Cache không vary theo Origin hoặc cache key sai | Dùng Vary: Origin và cấu hình cache key/purge |

## 27. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “include bảo đảm browser gửi cookie.” | Cookie còn chịu SameSite, Secure, Domain/Path, expiry, third-party blocking và partitioning. |
| “same-origin là mode gửi mọi cookie.” | Chỉ credentials phù hợp với URL và cookie policy mới được gửi. |
| “omit xóa cookie khỏi browser.” | Omit chỉ ảnh hưởng request/response hiện tại, không xóa cookie đã lưu. |
| “CORS wildcard dùng được với credentials.” | Credentialed CORS cần ACAO origin cụ thể và ACAC true. |
| “Preflight gửi cookie giống actual request.” | CORS preflight không mang credentials của actual request. |
| “CORS chặn request cross-site.” | CORS chủ yếu kiểm soát chia sẻ response; request đơn giản vẫn có thể tới server. |
| “withCredentials=false nghĩa XHR không gửi cookie cùng origin.” | Same-origin XHR vẫn gửi credentials phù hợp; thuộc tính chủ yếu ảnh hưởng cross-origin. |
| “Fetch include tự thêm bearer token.” | Ứng dụng phải quản lý Authorization header riêng. |
| “Set-Cookie đọc được qua response.headers.” | Set-Cookie là forbidden response header đối với frontend JavaScript. |
| “SameSite=None bỏ qua mọi third-party cookie policy.” | Browser vẫn có thể chặn hoặc partition third-party cookies. |

## 28. Checklist sử dụng credentials mode

- Chọn `omit` cho request không cần credentials; `same-origin` cho request cùng origin; `include` chỉ khi cần credentialed cross-origin.
- Nhớ Fetch mặc định dùng `same-origin`.
- Phân biệt credentials do browser quản lý với Authorization header do ứng dụng tự đặt.
- Với credentialed CORS, dùng ACAO origin cụ thể và ACAC true.
- Không phản chiếu Origin tùy tiện; dùng allowlist và `Vary: Origin`.
- Cấu hình OPTIONS/preflight không phụ thuộc cookie của actual request.
- Không xem CORS là CSRF protection hoặc authorization.
- Kiểm tra SameSite, Secure, Domain, Path, expiry và third-party cookie restrictions.
- Đánh giá storage/cookie partitioning trong embedded context.
- Với XHR cross-origin cần credentials, đặt `withCredentials = true` trước `send()`.
- Không bật withCredentials chỉ để gửi cookie same-origin.
- Không cố đọc Set-Cookie từ JavaScript; kiểm tra browser cookie storage.
- Đặt Cache-Control phù hợp cho response chứa dữ liệu theo session.
- Không cache credentialed response dùng chung nếu cache key không phân biệt user/Origin.
- Kiểm thử redirect, preflight, nhiều browser và top-level site khác nhau.
- Xác minh authentication, authorization và CSRF ở server cho mọi thao tác nhạy cảm.

## 29. Câu hỏi tự kiểm tra

1. Credentials mode điều khiển hai chiều nào của request/response?
2. Ba giá trị omit, same-origin và include khác nhau ra sao?
3. Vì sao same-origin là default của Fetch?
4. Include có đảm bảo cookie cross-site được gửi không?
5. CORS credentialed response cần những header nào?
6. Vì sao ACAO wildcard không hợp lệ khi credentials mode là include?
7. Preflight có mang cookie credentials không?
8. Vì sao CORS không thay CSRF protection?
9. SameSite=None; Secure giải quyết điều gì và không giải quyết điều gì?
10. Third-party cookie blocking và partitioning ảnh hưởng include như thế nào?
11. Fetch credentials mode khác XMLHttpRequest.withCredentials ở default nào?
12. Vì sao XHR withCredentials=false vẫn có thể gửi cookie same-origin?
13. Vì sao JavaScript không đọc được Set-Cookie?
14. Cần cấu hình cache thế nào cho response thay đổi theo Origin hoặc session?

**Ghi nhớ:** Fetch credentials mode quyết định browser gửi và xử lý credentials ở mức nào: omit không dùng credentials, same-origin chỉ dùng cho cùng origin và là mặc định, include cho phép dùng cả cross-origin. Include không vượt qua SameSite, Secure, third-party cookie blocking hoặc partitioning. Credentialed CORS cần origin cụ thể và ACAC true; preflight không mang credentials. Với XHR, withCredentials chủ yếu bật credential sharing cross-origin, còn same-origin credentials vẫn tuân theo quy tắc browser. CORS không thay CSRF, authentication hay authorization phía server.
