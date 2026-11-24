# CORS misconfiguration

> **Chương:** CORS  
> **Học phần:** Application Security — Browser Security (`SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`)

CORS cho phép server chỉ định origin nào được JavaScript trong browser đọc response cross-origin. Khi cấu hình sai, một website không đáng tin có thể được browser cấp quyền đọc dữ liệu từ API của ứng dụng, kể cả dữ liệu gắn với phiên đăng nhập của nạn nhân trong một số điều kiện. Đây là rủi ro **lộ dữ liệu qua browser**, thường xuất hiện khi server phản chiếu `Origin` không kiểm tra, cho phép `null`, tin mọi subdomain hoặc kết hợp sai CORS với credentials.

Đánh giá CORS cần tách biệt **quyền đọc response trong browser** với **quyền thực hiện thao tác trên server**. CORS không phải cơ chế xác thực, phân quyền hay chống CSRF. Bài này tập trung nhận diện cấu hình sai, hiểu điều kiện khai thác, kiểm thử có kiểm soát và thiết kế allowlist an toàn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nhận diện các lỗi CORS thường gặp: phản chiếu origin, wildcard với credentials, cho phép `null`, kiểm tra domain lỏng lẻo và tin toàn bộ subdomain.
2. Giải thích điều kiện để một cấu hình sai dẫn tới đọc dữ liệu nhạy cảm bằng JavaScript cross-origin.
3. Phân biệt cấu hình nguy hiểm thực sự với cấu hình chỉ rộng nhưng không làm lộ dữ liệu có bảo vệ.
4. Kiểm tra `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, preflight và `Vary: Origin`.
5. Xây dựng allowlist chính xác, kiểm soát cache và giảm phạm vi tin cậy.
6. Kiểm chứng phát hiện trong môi trường lab mà không truy cập dữ liệu của người dùng thật.

## 2. CORS misconfiguration là gì?

Một **CORS misconfiguration** xảy ra khi server công bố quyền đọc response cho origin không nên được tin cậy, hoặc khi chính sách được triển khai thiếu nhất quán làm lộ dữ liệu hay gây lỗi tích hợp. Một vài header rộng không tự động đồng nghĩa với lỗ hổng nghiêm trọng; phải xác định **response nào được đọc, dữ liệu nào có trong response, browser có gửi credentials hay không, và ai kiểm soát origin được phép**.

Ví dụ, API chỉ định cho phép frontend chính thức:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
```

Nhưng middleware lại sao chép mọi giá trị `Origin` do client gửi:

```http
Origin: https://attacker.example
```

và trả:

```http
Access-Control-Allow-Origin: https://attacker.example
Access-Control-Allow-Credentials: true
```

Nếu nạn nhân đang đăng nhập, cookie được browser gửi tới API, response chứa dữ liệu riêng tư và browser chấp nhận các điều kiện credentials/CORS, JavaScript của `attacker.example` có thể đọc response. Server đã cấp quyền đọc cho origin không đáng tin.

### 2.1 Điều kiện để lỗi trở thành lộ dữ liệu

Thông thường, cần đánh giá đồng thời các yếu tố:

- **Origin tấn công được cho phép:** cấu hình phản chiếu hoặc allowlist bao gồm một origin do kẻ tấn công kiểm soát.
- **Có dữ liệu đáng đọc:** endpoint trả dữ liệu cá nhân, hồ sơ, đơn hàng, token hoặc thông tin nội bộ mà người dùng hiện tại có quyền truy cập.
- **Có credentials hoặc cơ chế truy cập phù hợp:** ví dụ browser gửi cookie phiên theo `credentials: "include"` và cookie đủ điều kiện được gửi. Một API công khai không cần credentials có thể bị đọc bởi bất kỳ website nào nếu cấu hình cho phép `*`, nhưng mức độ ảnh hưởng phụ thuộc dữ liệu thực tế.
- **Response cho phép JavaScript đọc:** với credentialed response, origin phải cụ thể và `Access-Control-Allow-Credentials: true` phải được bật; wildcard `*` không đáp ứng điều kiện này.
- **Browser thực sự gửi credentials:** còn phụ thuộc `SameSite`, `Secure`, domain/path, ngữ cảnh top-level/frame và chính sách cookie của browser.

Không phải mọi lỗi CORS đều cho phép đánh cắp dữ liệu đăng nhập. Ngược lại, nếu response công khai vốn không nhạy cảm thì `Access-Control-Allow-Origin: *` có thể là thiết kế có chủ đích. Cần chứng minh tác động theo endpoint và dữ liệu, không chỉ đếm số header.

## 3. Lỗi 1 — Phản chiếu mọi Origin (arbitrary origin reflection)

Đây là lỗi cấu hình nguy hiểm và dễ gặp khi code muốn “cho frontend nào cũng gọi được”.

**Mẫu không an toàn:**

```js
function cors(req, res, next) {
  const origin = req.headers.origin;
  if (origin) {
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Access-Control-Allow-Credentials", "true");
  }
  next();
}
```

Server không kiểm tra `Origin` có thuộc danh sách được tin cậy hay không. Vì vậy một website bất kỳ có thể gửi request cross-origin và nhận quyền đọc response theo header mà server tự phản chiếu.

### 3.1 Vì sao `credentials: include` làm rủi ro tăng?

Trên một trang do kẻ tấn công kiểm soát, JavaScript có thể yêu cầu browser gửi credentials:

```js
fetch("https://api.example.test/account", {
  credentials: "include",
})
  .then((response) => response.json())
  .then((data) => console.log("Lab response:", data));
```

Đoạn code chỉ dùng để kiểm chứng trong lab: nó ghi response ra Console, không gửi dữ liệu đi nơi khác. Nếu API phản chiếu origin hiện tại và trả `Access-Control-Allow-Credentials: true`, browser có thể cho script đọc response khi cookie/session cũng được gửi hợp lệ. Với người dùng thật, đây có thể trở thành lộ dữ liệu xuyên origin.

**Lưu ý:** `credentials: "include"` không cưỡng ép browser gửi mọi cookie. Cookie vẫn chịu các quy tắc `SameSite`, `Secure`, domain/path, thời hạn và chính sách chặn/partition cookie bên thứ ba. Tuy nhiên, một subdomain cùng site nhưng khác origin có thể là nguồn request same-site; không được dựa vào SameSite để tin mọi subdomain.

### 3.2 Cách khắc phục

- Dùng **allowlist origin chính xác** được cấu hình từ môi trường triển khai.
- Chỉ trả `Access-Control-Allow-Credentials: true` cho endpoint thật sự cần credentials và những origin đã được phê duyệt.
- Không sao chép giá trị `Origin` vào response chỉ vì request có header đó.
- Kiểm thử cả response thành công và lỗi, cả preflight lẫn request thực tế.

## 4. Lỗi 2 — Wildcard `*` và credentials

Header:

```http
Access-Control-Allow-Origin: *
```

cho phép JavaScript ở bất kỳ origin nào đọc response **không dùng credentials**. Nó có thể phù hợp với dữ liệu công khai, ví dụ catalog sản phẩm công khai hoặc metadata không nhạy cảm.

Nhưng cấu hình sau không cấp quyền đọc credentialed response:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Khi Fetch request dùng credentials mode `include`, browser yêu cầu `Access-Control-Allow-Origin` phải là origin cụ thể phù hợp; `*` không hợp lệ. `Access-Control-Allow-Credentials` phải có giá trị chính xác `true`.

| Cấu hình | Kết quả CORS điển hình |
| --- | --- |
| `ACAO: *`, không credentials | Có thể cho mọi origin đọc response công khai |
| `ACAO: https://app.example.com`, không credentials | Chỉ origin đó được đọc response |
| `ACAO: https://app.example.com` + `ACAC: true`, request `include` | Có thể cho origin cụ thể đọc credentialed response |
| `ACAO: *` + `ACAC: true`, request `include` | Browser không chia sẻ response cho JavaScript |

**Không được kết luận API an toàn chỉ vì wildcard kết hợp credentials bị browser từ chối.** API có thể vẫn công khai dữ liệu nhạy cảm không cần đăng nhập, có endpoint khác trả response theo cách không credential, hoặc cấu hình ở một endpoint khác có lỗi. Hãy kiểm tra từng endpoint và dữ liệu.

### 4.1 Wildcard ở các header khác

Các wildcard trong `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` và `Access-Control-Expose-Headers` có ngữ nghĩa riêng theo Fetch. Với request credentials mode `include`, giá trị `*` ở những header này không hoạt động như wildcard tổng quát; trong nhiều trường hợp nó được hiểu như tên literal. Cấu hình rõ method, request header và response header cần thiết giúp tránh phụ thuộc vào khác biệt ngữ nghĩa này.

## 5. Lỗi 3 — Cho phép Origin `null`

Một số ngữ cảnh browser có **opaque origin** được biểu diễn trong header `Origin` thành chuỗi `null`. Các ví dụ có thể gồm tài liệu sandbox iframe không có `allow-same-origin`, một số URL `data:` và ngữ cảnh `file:`.

Nếu server trả:

```http
Access-Control-Allow-Origin: null
Access-Control-Allow-Credentials: true
```

cho response nhạy cảm, các tài liệu có origin opaque có thể được cấp quyền đọc response trong những điều kiện credentials phù hợp. Không nên coi `null` là một origin nội bộ đáng tin chỉ vì nó không hiển thị tên miền.

**Mẫu kiểm tra không an toàn:**

```js
if (origin === "null" || allowedOrigins.has(origin)) {
  res.setHeader("Access-Control-Allow-Origin", origin);
}
```

**Cách xử lý:** mặc định từ chối `Origin: null`. Chỉ cân nhắc cho phép khi có yêu cầu nghiệp vụ đặc biệt, đã xác định chính xác ngữ cảnh phát sinh và đã đánh giá rủi ro. Đối với trang cần truy cập API, hãy dùng một origin HTTP(S) ổn định và được quản lý.

## 6. Lỗi 4 — Kiểm tra origin bằng chuỗi hoặc regex lỏng lẻo

Một số ứng dụng muốn cho phép mọi subdomain của `example.com`, rồi viết kiểm tra:

```js
// Không an toàn
if (origin.endsWith("example.com")) {
  allow(origin);
}
```

Điều kiện này cũng có thể chấp nhận `https://evil-example.com`, vì chuỗi hostname đó kết thúc bằng `example.com`. Regex không neo đầu/cuối hoặc kiểm tra chuỗi con cũng dễ tạo lỗi tương tự.

Ví dụ khác:

```js
// Không an toàn: chỉ cần chuỗi "example.com" xuất hiện
if (origin.includes("example.com")) {
  allow(origin);
}
```

Nó có thể chấp nhận `https://example.com.attacker.test`.

### 6.1 Nếu thật sự cần cho phép subdomain

Tốt nhất vẫn là liệt kê origin cụ thể. Nếu nghiệp vụ bắt buộc cho phép subdomain động, hãy parse URL bằng parser chuẩn và kiểm tra ranh giới hostname chính xác, đồng thời ràng buộc scheme và port:

```js
function isAllowedCompanyOrigin(origin) {
  if (!origin || origin === "null") return false;

  let url;
  try {
    url = new URL(origin);
  } catch {
    return false;
  }

  // Origin header phải biểu diễn đúng một origin, không có path/query.
  if (url.origin !== origin) return false;
  if (url.protocol !== "https:") return false;
  if (url.port !== "") return false; // Chỉ cho phép cổng HTTPS mặc định

  const host = url.hostname.toLowerCase();
  return host === "example.com" || host.endsWith(".example.com");
}
```

Đây vẫn là chính sách rộng: nó tin **mọi subdomain** của `example.com`, bao gồm subdomain do nhóm khác quản lý, dịch vụ cũ, tenant, nội dung do người dùng tải lên hoặc host có thể bị takeover. Chỉ dùng khi toàn bộ namespace subdomain được quản trị cùng một mức tin cậy và đã có quy trình kiểm soát. Nếu không, hãy dùng allowlist origin chính xác.

Không chỉ kiểm tra hostname. Origin còn bao gồm scheme và port; `http://app.example.com`, `https://app.example.com:8443` và `https://app.example.com` là ba origin khác nhau. Việc chuẩn hóa URL, IDN/punycode, dấu chấm cuối hostname và port phải nhất quán với quy tắc triển khai; tránh tự viết parser bằng regex.

## 7. Lỗi 5 — Tin tất cả subdomain

Cho phép `https://*.example.com` có vẻ hợp lý nếu frontend nằm trên nhiều subdomain. Nhưng một subdomain bị XSS, takeover, cấu hình sai DNS hoặc được giao cho nhà cung cấp bên thứ ba có thể trở thành origin tấn công được tin cậy.

Ví dụ cùng site:

```text
https://accounts.example.com  → API tài khoản
https://blog.example.com      → CMS nội dung
https://legacy.example.com    → ứng dụng cũ
https://tenant.example.com    → nội dung do khách hàng quản lý
```

Các host này có thể **same-site nhưng cross-origin**. SOP/CORS phân biệt origin; cookie `SameSite` thường phân loại chúng là same-site. Vì vậy, nếu `blog.example.com` bị chiếm quyền, việc API cho phép mọi subdomain đọc response credentialed có thể mở đường lộ dữ liệu. SameSite không phải ranh giới tin cậy giữa các subdomain.

**Khuyến nghị:**

- Chỉ allowlist những subdomain thật sự cần truy cập API.
- Không dùng wildcard cho namespace có nội dung người dùng, tenant hoặc dịch vụ bên thứ ba.
- Kiểm kê DNS, CNAME, hosting và quy trình thu hồi subdomain không còn sử dụng.
- Giới hạn cookie phiên theo host nếu có thể; tránh chia sẻ `Domain=example.com` nếu không cần.
- Kết hợp CSRF token/Origin validation và phân quyền ở server; không dựa vào cùng site.

## 8. Lỗi 6 — Dùng `Origin` như bằng chứng xác thực

`Origin` là một tín hiệu browser gửi trong nhiều request cross-origin. Server dùng nó để thực thi chính sách CORS, nhưng nó **không phải danh tính người dùng** và không phải credential. Client HTTP không phải browser có thể tự tạo header `Origin`; vì vậy `curl` hoặc script tùy chỉnh có thể gửi bất kỳ giá trị nào.

Mẫu sai:

```text
Nếu Origin thuộc app.example.com
    → cho phép đọc dữ liệu tài khoản
```

Mẫu đúng:

```text
Xác thực session / token
    → kiểm tra quyền user với tài nguyên và hành động
    → xử lý nghiệp vụ
    → thêm CORS header nếu origin được phép đọc response
```

Không được bỏ xác thực hoặc phân quyền chỉ vì request có `Origin` được allowlist. Với các request thay đổi trạng thái, `Origin`/`Referer` có thể là một tín hiệu trong CSRF defense, nhưng phải thiết kế đúng cho endpoint và các trường hợp header bị thiếu; nó không thay thế CSRF token trong mọi kiến trúc.

## 9. Lỗi 7 — Quên `Vary: Origin` và cache dùng chung

Nếu server phản hồi origin động, response có thể thay đổi theo request header `Origin`. Ví dụ:

```http
Origin: https://app.example.com
```

được phản hồi:

```http
Access-Control-Allow-Origin: https://app.example.com
```

Một request từ origin khác có thể nhận giá trị `Access-Control-Allow-Origin` khác. Khi response thay đổi theo `Origin`, cần:

```http
Vary: Origin
```

Nếu thiếu `Vary: Origin`, reverse proxy hoặc CDN có thể dùng lại response đã cache cho origin khác. Điều này có thể làm response bị browser từ chối ngoài dự kiến, hoặc tạo điều kiện chia sẻ response sai ngữ cảnh nếu kết hợp với cache key và dữ liệu nhạy cảm không an toàn.

**`Vary: Origin` không thay thế cache policy.** Với response cá nhân hóa theo session, cần đặt chính sách như `Cache-Control: private` hoặc `no-store` tùy yêu cầu. Không để CDN cache dữ liệu tài khoản theo một cache key không phân biệt người dùng. Kiểm tra cả cache ở gateway/CDN, không chỉ header tại ứng dụng.

## 10. Lỗi 8 — Preflight và response thực tế không nhất quán

Một cấu hình có thể trả lời `OPTIONS` đúng nhưng response `GET`/`POST` thật lại thiếu CORS header. Khi đó browser có thể gửi request thực tế nhưng JavaScript vẫn không đọc được response. Ngược lại, server có thể chặn `OPTIONS` ở reverse proxy hoặc router khiến request cần preflight không bao giờ được gửi.

Các lỗi thường gặp:

- Chỉ gắn CORS middleware cho response `200`, bỏ qua `401`, `403`, `404` hoặc `500`.
- Reverse proxy xử lý `OPTIONS` trước ứng dụng và không trả đủ header.
- Server trả redirect cho preflight hoặc endpoint chuyển hướng sang host khác mà không có chính sách CORS phù hợp.
- `Access-Control-Allow-Methods` không bao gồm method được yêu cầu.
- `Access-Control-Allow-Headers` thiếu một request header tùy chỉnh.
- Preflight cho phép origin/method/header nhưng response thực tế lại không có `Access-Control-Allow-Origin` tương ứng.

Preflight là cơ chế kiểm tra khả năng gửi một số request cross-origin; nó không phải nơi xác thực session. Server thường phải xử lý preflight `OPTIONS` mà không yêu cầu cookie phiên. Khi request thực tế đến, server vẫn xác thực và phân quyền bình thường.

### 10.1 Cache preflight không phải cache dữ liệu

`Access-Control-Max-Age` cho browser lưu kết quả preflight trong CORS-preflight cache. Browser có thể áp giới hạn tối đa riêng. Khi thu hẹp policy, kết quả preflight cũ có thể còn hiệu lực tới khi cache hết hạn, nên request thực tế vẫn có thể được gửi trong khoảng đó; response thực tế vẫn cần vượt qua kiểm tra CORS. Không dùng TTL dài để thay cho quy trình thu hồi quyền hoặc authorization ở server.

## 11. Các cấu hình sai khác cần nhận diện

| Cấu hình hoặc cách làm | Vấn đề | Hướng khắc phục |
| --- | --- | --- |
| `Access-Control-Allow-Origin` phản chiếu mọi request | Cấp quyền đọc cho origin không tin cậy | Allowlist chính xác |
| Cho phép `Origin: null` vô điều kiện | Tin các opaque origin không rõ nguồn | Từ chối mặc định; chỉ ngoại lệ khi có yêu cầu đã đánh giá |
| `endsWith("example.com")` | Chấp nhận hostname giả mạo như `evil-example.com` | Parse origin và so sánh hostname có ranh giới; ưu tiên exact allowlist |
| Cho phép mọi `*.example.com` | Tin cả subdomain bị takeover hoặc do bên khác quản lý | Chỉ cho phép host cần thiết |
| ACAO `*` trên API trả dữ liệu nhạy cảm | Mọi website có thể đọc dữ liệu công khai qua browser | Yêu cầu xác thực/phân quyền và giới hạn origin khi dữ liệu cần bảo vệ |
| ACAO `*` cùng ACAC `true` | Không hợp lệ cho credentialed response; gây hiểu nhầm | Trả origin cụ thể cho credentials |
| Tin `Origin` để xác định user | Header không chứng minh danh tính | Xác thực và phân quyền độc lập |
| Thiếu `Vary: Origin` khi phản hồi động | Cache có thể tái sử dụng response sai origin | Thêm `Vary` và cấu hình cache key đúng |
| Chỉ thêm CORS cho response thành công | Frontend khó đọc lỗi, tạo chẩn đoán sai | Cấu hình nhất quán cho response cần chia sẻ |
| Mở mọi method/header | Tăng bề mặt tích hợp và gây hiểu nhầm về quyền API | Chỉ mở đúng nhu cầu; server vẫn kiểm soát method và quyền |
| Cho phép credentials trên mọi API | Tăng khả năng lộ dữ liệu phiên nếu origin policy sai | Chỉ bật trên endpoint cần và origin được duyệt |

## 12. Thiết kế allowlist an toàn

Với phần lớn ứng dụng, **allowlist origin chính xác** là lựa chọn dễ kiểm tra nhất. Ví dụ:

```js
const allowedOrigins = new Set([
  "https://app.example.com",
  "https://admin.example.com",
]);

function isAllowedOrigin(value) {
  if (!value || value === "null") return false;

  try {
    const parsed = new URL(value);
    // Chỉ chấp nhận giá trị Origin đã chuẩn hóa, không có path/query.
    if (parsed.origin !== value) return false;
    return allowedOrigins.has(parsed.origin);
  } catch {
    return false;
  }
}

function applyCors(req, res, next) {
  const origin = req.headers.origin;
  const allowed = isAllowedOrigin(origin);

  // Response được tạo khác nhau theo Origin.
  res.vary("Origin");

  if (allowed) {
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Access-Control-Allow-Credentials", "true");
  }

  if (req.method === "OPTIONS" &&
      req.headers["access-control-request-method"]) {
    if (!allowed) return res.sendStatus(403);

    res.setHeader("Access-Control-Allow-Methods", "GET, POST, PATCH");
    res.setHeader(
      "Access-Control-Allow-Headers",
      "Content-Type, Authorization, X-CSRF-Token"
    );
    res.setHeader("Access-Control-Max-Age", "300");
    return res.sendStatus(204);
  }

  next();
}
```

Đây là ví dụ minh họa, cần điều chỉnh cho framework, router, gateway và endpoint thật. Không bật credentials mặc định nếu API không cần cookie/HTTP credentials. Nếu endpoint công khai và không có dữ liệu riêng tư, có thể cân nhắc `Access-Control-Allow-Origin: *` mà không bật credentials. Nếu API có dữ liệu cá nhân, allowlist chỉ là quyền đọc từ browser; server vẫn phải xác thực và phân quyền.

### 12.1 Những điều cần kiểm tra trong triển khai

- Cấu hình origin theo môi trường; không đưa localhost, staging hoặc preview deployment vào production allowlist nếu không có lý do.
- So sánh scheme, host và port đầy đủ; không chỉ so domain gốc.
- Không chấp nhận origin `null` theo mặc định.
- Không dùng regex/substring thay cho parser URL và ranh giới hostname.
- Không trả nhiều origin phân tách bằng dấu phẩy trong `Access-Control-Allow-Origin`; response phải chứa một origin cụ thể hoặc `*` khi phù hợp.
- Tránh gửi nhiều `Access-Control-Allow-Origin` do cả ứng dụng và proxy cùng thêm; header trùng có thể bị browser coi là không hợp lệ.
- Thêm `Vary: Origin` khi response phụ thuộc origin; kiểm tra CDN có tôn trọng `Vary` không.
- Dùng `Cache-Control` phù hợp với dữ liệu cá nhân và session.
- Chỉ cho phép method/header cần thiết; không nhầm CORS method allowlist với quyền nghiệp vụ.
- Kiểm thử response lỗi, preflight, redirect và các endpoint qua gateway.

## 13. Quy trình đánh giá một CORS finding

Khi phát hiện ACAO wildcard hoặc phản chiếu origin, cần thu thập bằng chứng để xác định tác động:

1. **Xác định endpoint:** response có chứa dữ liệu gì, có yêu cầu đăng nhập không, có dữ liệu cá nhân hoặc bí mật không?
2. **Xác định origin nguồn:** gửi request với origin kiểm thử do bạn kiểm soát; quan sát server có phản chiếu hoặc chấp nhận nó không.
3. **Kiểm tra credentials:** request có dùng `credentials: "include"` không? Browser có gửi cookie thực tế không? Cookie có bị SameSite/third-party policy chặn không?
4. **Kiểm tra response:** có đúng một `Access-Control-Allow-Origin` khớp origin thử nghiệm không? Có `Access-Control-Allow-Credentials: true` khi cần không?
5. **Kiểm tra khả năng đọc:** JavaScript trong trang thử nghiệm có thực sự đọc được status/body không? Network panel một mình không chứng minh JavaScript được cấp quyền đọc.
6. **Kiểm tra phân quyền:** gọi endpoint bằng session không có quyền hoặc user lab khác; server có trả dữ liệu ngoài phạm vi không?
7. **Kiểm tra cache:** thử các origin khác nhau và xác nhận `Vary: Origin`, cache key, `Cache-Control`.
8. **Đánh giá phạm vi:** tìm các endpoint liên quan có cùng middleware, đặc biệt API tài khoản, profile, billing, export, admin và multi-tenant.

Một finding tốt cần ghi rõ **điều kiện tiên quyết, dữ liệu có thể đọc, vai trò người dùng, yêu cầu cookie/browser, endpoint bị ảnh hưởng và bằng chứng tái hiện trong lab**. Chỉ có `Access-Control-Allow-Origin: *` không đủ để kết luận có thể chiếm session hay đọc dữ liệu tài khoản.

## 14. Thực hành kiểm chứng trong môi trường lab

Chỉ thực hiện trên ứng dụng và tài khoản thử nghiệm do bạn quản lý. Dùng dữ liệu giả, không chạy proof of concept trên website bên ngoài hoặc phiên đăng nhập của người khác.

### Bài thử A — Phản chiếu Origin

Tạo API lab trả dữ liệu giả:

```json
{"user":"demo-user","plan":"test"}
```

Cho API phản chiếu `Origin` và trả `Access-Control-Allow-Credentials: true`. Mở frontend lab trên một origin khác và gọi:

```js
fetch("https://api.lab.example.test/profile", {
  credentials: "include",
})
  .then((response) => response.text())
  .then((body) => console.log("Đọc được response trong lab:", body));
```

Thử một origin lab được cho phép và một origin lab không được cho phép. Sau đó thay middleware phản chiếu bằng exact allowlist.

**Kỳ vọng:** Với phản chiếu không kiểm tra, browser có thể cho trang thử nghiệm đọc response credentialed nếu cookie được gửi. Sau khi áp dụng allowlist, origin ngoài danh sách không đọc được response. Ghi lại request/response header và trạng thái cookie để chứng minh điều kiện.

### Bài thử B — Wildcard và credentials

Thử lần lượt:

```http
Access-Control-Allow-Origin: *
```

và:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Gọi API với `credentials: "omit"`, sau đó `credentials: "include"`.

**Kỳ vọng:** Wildcard có thể cho phép đọc response không credential. Với credentials mode `include`, browser từ chối chia sẻ response khi ACAO là `*`. Thay bằng origin cụ thể để kiểm tra luồng credentialed response.

### Bài thử C — Kiểm tra `null` và suffix matching

Trong unit test của middleware, đưa vào các giá trị:

```text
https://app.example.com
https://evil-example.com
https://example.com.attacker.test
null
http://app.example.com
https://app.example.com:8443
```

Xác minh chỉ origin thực sự được phê duyệt mới được trả lại trong ACAO. Thêm các case hostname có dấu chấm cuối hoặc IDN nếu hệ thống có hỗ trợ tên miền quốc tế.

**Kỳ vọng:** Kiểm tra chuỗi lỏng lẻo bị phát hiện; `null`, sai scheme và sai port bị từ chối nếu không có yêu cầu ngoại lệ được duyệt.

### Bài thử D — Cache theo Origin

Gửi hai request tới cùng endpoint, lần lượt với hai origin khác nhau được allowlist. Kiểm tra:

- `Access-Control-Allow-Origin` có thay đổi đúng theo origin không?
- Response có `Vary: Origin` không?
- CDN/proxy có giữ `Vary` và cache key tương ứng không?
- Dữ liệu cá nhân có bị cache public không?

**Kỳ vọng:** Response động được phân biệt theo Origin; dữ liệu cá nhân có cache policy riêng tư phù hợp.

### Bài thử E — Preflight và response lỗi

Gọi API bằng `PATCH` cùng header tùy chỉnh để tạo preflight. Kiểm tra `OPTIONS`, sau đó thử cho endpoint trả `401`, `403` và `500`.

**Kỳ vọng:** Preflight được xử lý theo policy; response thực tế có CORS header nhất quán để frontend có thể đọc trạng thái lỗi khi origin hợp lệ. Server vẫn từ chối request không có quyền dù preflight thành công.

## 15. Checklist review CORS trước khi phát hành

- [ ] Mỗi API đã xác định origin frontend cần được phép đọc.
- [ ] Không phản chiếu `Origin` tùy ý.
- [ ] Không cho phép `null` nếu chưa có yêu cầu và đánh giá rủi ro cụ thể.
- [ ] Không dùng wildcard credentials; origin credentialed được allowlist chính xác.
- [ ] Quy tắc subdomain không tin mọi host do bên thứ ba/tenant quản lý.
- [ ] Không kiểm tra hostname bằng substring hoặc `endsWith` thiếu ranh giới.
- [ ] Method và request header chỉ mở theo nhu cầu.
- [ ] `Vary: Origin` và cache key đúng khi response thay đổi theo origin.
- [ ] Response lỗi và preflight được kiểm thử qua proxy/CDN.
- [ ] Cookie và CSRF được đánh giá độc lập với CORS.
- [ ] API xác thực và phân quyền từng request/tài nguyên, kể cả khi request đến từ origin được allowlist.
- [ ] Bằng chứng kiểm thử xác nhận JavaScript thực sự đọc được dữ liệu, không chỉ dựa trên header hoặc thông báo Console.

## 16. Câu hỏi tự kiểm tra

1. Vì sao phản chiếu mọi giá trị `Origin` kết hợp `Access-Control-Allow-Credentials: true` có thể làm lộ dữ liệu phiên?
2. Vì sao `Access-Control-Allow-Origin: *` không cho JavaScript đọc credentialed response?
3. Những ngữ cảnh nào có thể tạo `Origin: null`, và vì sao không nên allowlist nó tùy tiện?
4. `origin.endsWith("example.com")` có thể chấp nhận hostname nào ngoài ý muốn?
5. Vì sao tin mọi subdomain có thể nguy hiểm dù chúng cùng site?
6. `Vary: Origin` giải quyết vấn đề gì? Vì sao nó không thay thế `Cache-Control: private` hoặc `no-store` cho dữ liệu cá nhân?
7. CORS preflight thành công có chứng minh người dùng có quyền truy cập API không?
8. Khi đánh giá lỗ hổng CORS, cần bằng chứng nào để chứng minh response nhạy cảm thực sự đọc được bằng JavaScript?

## 17. Ghi nhớ

CORS misconfiguration nguy hiểm nhất khi server cấp quyền đọc response cho **origin không đáng tin**, đặc biệt với response chứa dữ liệu riêng tư và credentials của người dùng. Các lỗi cần ưu tiên kiểm tra là phản chiếu origin tùy ý, allowlist chuỗi lỏng lẻo, cho phép `null`, tin mọi subdomain, cấu hình credentials sai và cache không phân biệt `Origin`.

Hãy dùng allowlist chính xác, chỉ bật credentials khi cần, kiểm soát cache, kiểm thử preflight và response thực tế. Dù CORS được cấu hình đúng, **server vẫn phải xác thực, phân quyền, kiểm tra CSRF và bảo vệ dữ liệu**. CORS quyết định JavaScript nào được đọc response trong browser; nó không quyết định ai có quyền gọi API.
