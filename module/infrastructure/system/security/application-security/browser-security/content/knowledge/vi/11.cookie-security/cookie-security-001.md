# Cookie prefix: tăng cường ranh giới và tính toàn vẹn của cookie

**Chương:** Cookie security  
**Mô-đun:** `SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY` — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy (SOP), CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

**Cookie prefix** là quy ước đặt tiền tố đặc biệt trong tên cookie để yêu cầu trình duyệt áp dụng một số điều kiện khi cookie được tạo. Các tiền tố như `__Secure-` và `__Host-` giúp trình duyệt từ chối những cookie không đáp ứng ràng buộc về kết nối an toàn, phạm vi host và đường dẫn. Một số trình duyệt mới còn hỗ trợ `__Http-` và `__Host-Http-` để yêu cầu cookie được thiết lập qua HTTP response với thuộc tính `HttpOnly`.

Cookie prefix đặc biệt hữu ích cho cookie phiên đăng nhập. Nó giúp giảm nguy cơ subdomain không đáng tin tạo cookie trùng tên với cookie của ứng dụng chính, đồng thời làm rõ cấu hình mà server dự định sử dụng. Tuy nhiên, prefix không thay thế thuộc tính cookie, xác thực/phân quyền phía server, CSRF token hay phòng vệ XSS.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích cookie prefix là gì và trình duyệt kiểm tra nó ở thời điểm nào.
2. Phân biệt điều kiện của `__Secure-`, `__Host-`, `__Http-` và `__Host-Http-`.
3. Chọn prefix phù hợp cho cookie phiên, cookie tùy chọn và cookie cần chia sẻ giữa subdomain.
4. Nhận diện cookie tossing, cookie shadowing và xung đột cookie cùng tên.
5. Kết hợp prefix với `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain` và vòng đời session.
6. Kiểm tra hành vi prefix trên các trình duyệt mục tiêu và không giả định mọi browser hỗ trợ cùng một tập tiền tố.

## 2. Cookie prefix hoạt động như thế nào?

Cookie được tạo thông qua header phản hồi HTTP `Set-Cookie` hoặc JavaScript `document.cookie` (trừ cookie có `HttpOnly`). Trình duyệt phân tích tên và thuộc tính, áp dụng quy tắc cookie, rồi lưu cookie nếu hợp lệ.

Ví dụ server gửi:

```http
Set-Cookie: __Host-session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

Tên cookie bắt đầu bằng `__Host-`. Trình duyệt hỗ trợ prefix này kiểm tra những điều kiện bắt buộc trước khi chấp nhận cookie. Nếu thiếu `Secure`, `Path=/` hoặc có thuộc tính `Domain`, trình duyệt từ chối cookie thay vì lưu nó như cookie bình thường.

**Điểm quan trọng:** prefix nằm trong **tên cookie**, còn các điều kiện được kiểm tra dựa trên cả tên và thuộc tính. Server vẫn phải gửi các thuộc tính cần thiết. Chỉ đặt tên `__Host-session` mà không có `Secure`/`Path=/` không tự tạo ra cookie an toàn.

Prefix là cơ chế thực thi ở phía user agent. Trình duyệt không hỗ trợ một prefix có thể xử lý tên đó như tên cookie thông thường và không áp dụng các ràng buộc tương ứng. Vì vậy, prefix tăng cường bảo vệ trên browser hỗ trợ nhưng không phải điều kiện duy nhất để server bảo vệ phiên.

### 2.1. Bảng tổng quan các prefix

| Prefix | Yêu cầu chính trên trình duyệt hỗ trợ | Ý nghĩa |
| --- | --- | --- |
| `__Secure-` | Cookie phải được thiết lập từ secure origin và có `Secure` | Chỉ chấp nhận cookie được tạo qua ngữ cảnh kết nối an toàn |
| `__Host-` | Secure origin, `Secure`, `Path=/` và **không có `Domain`** | Cookie host-only, áp dụng toàn bộ path của host |
| `__Http-` | Secure origin, `Secure` và `HttpOnly` | Yêu cầu cookie được server thiết lập qua HTTP response, không qua JS |
| `__Host-Http-` | Secure origin, `Secure`, `HttpOnly`, `Path=/` và không có `Domain` | Kết hợp ràng buộc host-only với yêu cầu thiết lập từ HTTP response |

Các prefix mới `__Http-` và `__Host-Http-` không được hỗ trợ đồng đều trên mọi trình duyệt. Cần kiểm tra tài liệu tương thích và thử trên phiên bản browser mà ứng dụng hỗ trợ. Các prefix cũng **phân biệt chữ hoa/chữ thường**: `__Host-session` không giống `__host-session`.


## 3. Phân tích từng prefix

### 3.1. `__Secure-`: cookie phải được thiết lập an toàn

Cookie có tên bắt đầu bằng `__Secure-` phải:

- được tạo từ secure origin (thông thường là HTTPS);
- có thuộc tính `Secure`.

Ví dụ hợp lệ:

```http
Set-Cookie: __Secure-preference=compact; Secure; Path=/; SameSite=Lax
```

Ví dụ không đáp ứng yêu cầu:

```http
Set-Cookie: __Secure-preference=compact; Path=/; SameSite=Lax
```

Thiếu `Secure` nên browser hỗ trợ prefix sẽ từ chối cookie. Nếu phản hồi được gửi từ ngữ cảnh không an toàn, cookie có prefix này cũng không đáp ứng điều kiện secure origin.

**Prefix này không bắt buộc `HttpOnly` và không bắt buộc host-only.** Cookie `__Secure-preference` vẫn có thể được thiết lập với `Domain=example.com` nếu các quy tắc domain khác cho phép. Vì vậy, `__Secure-` không tự ngăn subdomain khác tạo cookie cùng tên có scope rộng.

Dùng `__Secure-` khi cần khẳng định cookie chỉ được tạo từ kênh an toàn, nhưng ứng dụng không cần ràng buộc host-only mạnh như `__Host-`.

### 3.2. `__Host-`: ràng buộc host-only

`__Host-` có các yêu cầu:

1. Phản hồi được gửi từ secure origin.
2. Cookie có `Secure`.
3. Cookie có `Path=/`.
4. Cookie **không được có thuộc tính `Domain`**.

Ví dụ:

```http
Set-Cookie: __Host-session=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

Cookie này được gắn với host đã thiết lập nó. Do không có `Domain`, nó là cookie host-only; `Path=/` khiến nó áp dụng cho mọi đường dẫn trên host đó.

Ví dụ nếu response đến từ `https://app.example.com`:

- Cookie được gửi đến các path phù hợp trên `app.example.com`.
- Cookie không được chia sẻ sang `api.example.com`.
- Subdomain `evil.example.com` không thể đặt một cookie `__Host-session` với `Domain=example.com` trên trình duyệt hỗ trợ prefix.
- Cookie không bị giới hạn theo port; cookie không phải cơ chế cách ly giữa các ứng dụng cùng host nhưng khác port.

Các cấu hình sau bị từ chối trên browser hỗ trợ `__Host-`:

```http
# Sai: thiếu Secure
Set-Cookie: __Host-session=abc; Path=/; HttpOnly

# Sai: Path không phải /
Set-Cookie: __Host-session=abc; Path=/account; Secure

# Sai: có Domain
Set-Cookie: __Host-session=abc; Domain=example.com; Path=/; Secure

# Sai: tạo từ kết nối không an toàn
# (ví dụ response HTTP thông thường)
Set-Cookie: __Host-session=abc; Path=/; Secure
```

**Vì sao `Path=/` là bắt buộc?** Prefix này định nghĩa cookie áp dụng toàn host, tránh tạo nhiều cookie cùng tên với các path khác nhau để gây nhầm lẫn trong ứng dụng. `Path` không phải ranh giới bảo mật đầy đủ giữa các ứng dụng; việc giới hạn host mới là ràng buộc quan trọng của `__Host-`.

### 3.3. `__Http-`: chỉ nhận cookie do HTTP response thiết lập

Trên trình duyệt hỗ trợ prefix này, cookie bắt đầu bằng `__Http-` phải có:

- secure origin;
- thuộc tính `Secure`;
- thuộc tính `HttpOnly`.

Ví dụ:

```http
Set-Cookie: __Http-session-proof=server-value; Secure; HttpOnly; Path=/; SameSite=Lax
```

JavaScript không thể thiết lập thuộc tính `HttpOnly` bằng `document.cookie`. Do đó, prefix `__Http-` yêu cầu cookie phải được tạo qua HTTP response có header `Set-Cookie`, không phải bởi script trên trang.

Prefix này không tự yêu cầu `Path=/` và cũng không cấm `Domain`. Nếu muốn cookie host-only và toàn path, cần dùng `__Host-Http-` khi browser hỗ trợ hoặc dùng `__Host-` cùng `HttpOnly` theo cách tương thích rộng hơn.

### 3.4. `__Host-Http-`: kết hợp host-only và HTTP-only

Prefix này kết hợp yêu cầu của `__Host-` và `__Http-`:

- secure origin;
- `Secure`;
- `HttpOnly`;
- `Path=/`;
- không có `Domain`.

Ví dụ:

```http
Set-Cookie: __Host-Http-session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

Đây là cấu hình có nhiều ràng buộc cho cookie phiên nhạy cảm trên trình duyệt hỗ trợ đầy đủ prefix. Tuy nhiên, do hỗ trợ browser không đồng đều, ứng dụng cần có chiến lược tương thích: vẫn gửi đầy đủ thuộc tính cookie an toàn, kiểm tra behavior trên browser mục tiêu và không xem prefix là thay thế cho server-side session security.


## 4. So sánh các prefix qua ví dụ

Giả sử ứng dụng ở `https://app.example.com` và có subdomain `https://uploads.example.com` do một nhóm khác quản lý.

| Tình huống | `__Secure-session` | `__Host-session` |
| --- | --- | --- |
| Bắt buộc `Secure` | Có | Có |
| Bắt buộc HTTPS/secure origin khi tạo | Có | Có |
| Bắt buộc `Path=/` | Không | Có |
| Cấm thuộc tính `Domain` | Không | Có |
| Host-only bắt buộc | Không | Có |
| Bắt buộc `HttpOnly` | Không | Không |
| Có thể dùng để giảm cookie tossing từ subdomain | Hạn chế | Tốt hơn nhờ cấm Domain |
| Phù hợp làm session cookie | Có thể, nếu cấu hình đủ thuộc tính | Thường là lựa chọn mạnh hơn cho session host-only |

Nếu chọn `__Secure-session` nhưng vẫn đặt `Domain=example.com`, subdomain có khả năng phát response HTTPS có thể cố đặt cookie cùng tên với scope cha (nếu thỏa quy tắc domain). Điều này tạo nguy cơ cookie trùng tên và parsing không rõ ràng. `__Host-session` ngăn cấu hình domain rộng đó trên browser hỗ trợ.

Một ứng dụng không nên chia sẻ session cookie giữa nhiều subdomain chỉ vì chúng cùng registrable domain. Nếu thật sự cần SSO, hãy thiết kế cơ chế đăng nhập liên miền/subdomain có kiểm soát, token trao đổi ngắn hạn và callback allowlist rõ ràng; không mở rộng cookie phiên chính một cách tùy tiện.

## 5. Cookie tossing và cookie shadowing

### 5.1. Cookie tossing là gì?

**Cookie tossing** là tình huống một host hoặc subdomain có thể tạo cookie cùng tên với cookie ứng dụng chính, thường bằng cách đặt thuộc tính `Domain` rộng hơn. Nếu server nhận nhiều cookie cùng tên, cách framework phân tích header có thể tạo ra kết quả không mong muốn.

Ví dụ ứng dụng chính thiết lập:

```http
Set-Cookie: session=trusted-session; Domain=example.com; Path=/; Secure; HttpOnly
```

Một subdomain khác có thể cố tạo cookie trùng tên:

```http
Set-Cookie: session=attacker-value; Domain=example.com; Path=/; Secure
```

Tùy cách trình duyệt lưu và gửi cookie, request có thể mang nhiều cặp `session`. Header `Cookie` không gửi lại thuộc tính `Domain`, `Path` hay cờ host-only; server nhận tên và giá trị, nên việc phân biệt cookie dựa vào scope gốc không đơn giản. Các framework có thể chọn giá trị đầu tiên, cuối cùng hoặc biểu diễn thành nhiều giá trị.

### 5.2. `__Host-` giảm rủi ro như thế nào?

Nếu ứng dụng chính dùng:

```http
Set-Cookie: __Host-session=trusted-session; Path=/; Secure; HttpOnly; SameSite=Lax
```

thì browser hỗ trợ `__Host-` từ chối nỗ lực tạo cookie cùng tên với `Domain=example.com`. Subdomain không thể đặt cookie host-only cho host cha; nó chỉ có thể tạo cookie host-only cho chính nó, không gửi cookie đó tới host ứng dụng chính.

Đây là một ràng buộc hữu ích để bảo vệ tính toàn vẹn của cookie phiên. Tuy nhiên, prefix không bảo vệ nếu attacker kiểm soát chính origin `app.example.com`, có khả năng sửa response của host đó, hoặc khai thác server/application để thay cookie. Hãy kết hợp với bảo vệ DNS, TLS, cấu hình reverse proxy và kiểm soát quyền deploy.

### 5.3. Cookie shadowing và trùng tên theo Path

Cookie có cùng tên nhưng khác `Path` có thể cùng được gửi trong một request nếu path của request khớp cả hai. `Path` không phải ranh giới bảo mật; đừng dùng cookie cùng tên ở `/` và `/admin` để biểu diễn hai cấp quyền. Prefix `__Host-` bắt buộc `Path=/`, giúp loại bỏ biến thể path hẹp cho tên cookie đó trên browser hỗ trợ.

Server nên dùng tên cookie duy nhất cho từng mục đích, từ chối request có định dạng cookie mơ hồ nếu framework hỗ trợ phát hiện, và không dựa vào thứ tự cookie trong header để quyết định phiên nào được tin cậy.

## 6. Prefix không thay thế thuộc tính cookie

Prefix chỉ bổ sung một tập điều kiện. Cookie thực tế vẫn cần các thuộc tính phù hợp:

| Thuộc tính | Chức năng | Lưu ý bảo mật |
| --- | --- | --- |
| `Secure` | Chỉ gửi cookie qua kênh bảo mật theo quy tắc trình duyệt | Bắt buộc với các prefix trên; triển khai HTTPS toàn bộ |
| `HttpOnly` | Ngăn JavaScript đọc cookie qua `document.cookie` | Giảm nguy cơ đánh cắp cookie qua XSS; XSS vẫn có thể gửi request bằng phiên của nạn nhân |
| `SameSite` | Hạn chế gửi cookie trong một số ngữ cảnh cross-site | `Strict`, `Lax`, `None` có hành vi khác nhau; `None` yêu cầu `Secure` |
| `Path` | Giới hạn URL path mà cookie được gửi đến | Không phải ranh giới bảo mật giữa ứng dụng |
| `Domain` | Mở rộng cookie tới domain và subdomain phù hợp | Tránh dùng nếu không cần; `__Host-` cấm thuộc tính này |
| `Max-Age` / `Expires` | Kiểm soát thời hạn cookie | Session timeout vẫn phải được kiểm tra phía server |

Ví dụ cookie phiên host-only:

```http
Set-Cookie: __Host-session=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1800
```

Ví dụ cookie cần gửi trong ngữ cảnh cross-site (chỉ khi kiến trúc thực sự cần):

```http
Set-Cookie: __Secure-embed-session=opaque-id; Secure; HttpOnly; SameSite=None; Path=/
```

Cookie thứ hai vẫn có thể cần thêm chính sách phù hợp với browser về third-party cookies và partitioning. `SameSite=None` không đảm bảo mọi trình duyệt sẽ chấp nhận cookie bên thứ ba trong mọi bối cảnh.

**Chọn `SameSite` theo luồng nghiệp vụ.** `Lax` thường là mặc định thực dụng cho cookie phiên web; `Strict` có thể ảnh hưởng link đến từ website ngoài và luồng đăng nhập; `None` dành cho use case cross-site rõ ràng và phải có `Secure`. Không dùng prefix để suy ra cookie đang same-site hay cross-site.

## 7. Chọn prefix nào cho từng loại cookie?

| Nhu cầu | Cấu hình khuyến nghị | Lý do |
| --- | --- | --- |
| Session đăng nhập trên một host | `__Host-session` + `Secure; HttpOnly; SameSite=Lax; Path=/` | Host-only, không cho subdomain mở rộng Domain |
| Session nhạy cảm trên browser hỗ trợ prefix mới | `__Host-Http-session` với đầy đủ thuộc tính | Thêm yêu cầu HttpOnly và server-set |
| Cookie cần xác nhận server-set nhưng không cần host-only | `__Http-name` + `Secure; HttpOnly` | Ngăn script tạo cookie cùng prefix trên browser hỗ trợ |
| Cookie cấu hình cần Secure nhưng có thể chia sẻ domain | `__Secure-name` + `Secure` | Đảm bảo secure origin và Secure |
| Cookie phải chia sẻ cho nhiều subdomain | Cân nhắc cookie Domain thông thường, tên riêng, scope nhỏ nhất | `__Host-` không phù hợp vì cấm Domain |

**Khuyến nghị mặc định cho session:** nếu không cần chia sẻ cookie qua subdomain, ưu tiên `__Host-session` với `Secure`, `HttpOnly`, `SameSite` tường minh và `Path=/`. Nếu muốn dùng `__Host-Http-`, phải xác minh browser hỗ trợ và vẫn giữ cấu hình thuộc tính đầy đủ.


## 8. Cookie prefix và các lớp phòng vệ ứng dụng

### 8.1. XSS

`HttpOnly` ngăn JavaScript đọc trực tiếp giá trị cookie phiên, nhưng XSS chạy trong origin ứng dụng vẫn có thể thực hiện request đến server bằng cookie tự động được đính kèm. Prefix không loại bỏ XSS.

Phòng vệ XSS gồm output encoding theo ngữ cảnh, dùng `textContent` khi hiển thị text, tránh sink HTML nguy hiểm, sanitizer được duy trì, CSP chặt và Trusted Types ở các DOM sink được hỗ trợ.

### 8.2. CSRF

Cookie prefix không phải CSRF token. `SameSite` giúp giảm một số request cross-site mang cookie, nhưng không ngăn mọi request cùng site từ subdomain không đáng tin. Với hành động thay đổi trạng thái, dùng CSRF token hoặc cơ chế tương đương, kiểm tra `Origin`/`Referer` theo chính sách, Fetch Metadata khi phù hợp và xác thực/phân quyền ở server.

### 8.3. Clickjacking

Prefix không ngăn trang bị nhúng trong iframe. Dùng CSP `frame-ancestors` hoặc `X-Frame-Options` trên response của trang cần bảo vệ. Kiểm tra luồng đăng nhập và xác nhận thao tác nhạy cảm nếu trang có thể được nhúng hợp lệ.

### 8.4. Quản lý session phía server

Cookie chỉ mang một định danh phiên opaque. Server phải:

- sinh session ID đủ ngẫu nhiên và không đoán được;
- tái tạo session ID sau đăng nhập hoặc thay đổi quyền để chống session fixation;
- thu hồi session khi logout, hết hạn hoặc phát hiện rủi ro;
- kiểm tra session và quyền trên mỗi request nhạy cảm;
- áp dụng timeout idle/absolute theo yêu cầu nghiệp vụ;
- không tin dữ liệu quyền hạn do client gửi;
- không ghi giá trị cookie phiên vào log hoặc analytics.

Cookie prefix làm tăng độ chặt của cách trình duyệt chấp nhận cookie; nó không biến giá trị cookie thành token an toàn nếu server tạo, lưu hoặc xác minh session sai.

## 9. Lab: kiểm tra prefix qua HTTP response

Lab này dùng Node.js để tạo một server HTTPS local. Trình duyệt thường chỉ chấp nhận cookie `Secure` từ secure context; localhost có một số ngoại lệ được xem là potentially trustworthy tùy browser. Để kiểm chứng nhất quán, nên dùng HTTPS local với chứng chỉ dev được trình duyệt tin cậy. Không dùng chứng chỉ production hay cookie thật.

### 9.1. Tạo server thử nghiệm

Tạo chứng chỉ local bằng công cụ dev phù hợp (ví dụ mkcert) và đặt hai file `localhost-key.pem`, `localhost-cert.pem` trong thư mục lab. Tạo file `cookie-prefix-lab.mjs`:

```javascript
import https from "node:https";
import fs from "node:fs";

const key = fs.readFileSync("./localhost-key.pem");
const cert = fs.readFileSync("./localhost-cert.pem");

const page = `<!doctype html>
<html lang="vi">
<meta charset="utf-8">
<title>Cookie prefix lab</title>
<h1>Cookie prefix lab</h1>
<p>Trang thử nghiệm HTTPS localhost.</p>
<button id="show">Đọc cookie không HttpOnly</button>
<pre id="result"></pre>
<script>
  document.querySelector("#show").onclick = () => {
    // Cookie HttpOnly không xuất hiện trong document.cookie.
    document.querySelector("#result").textContent = document.cookie;
  };
</script>
</html>`;

https.createServer({ key, cert }, (req, res) => {
  if (req.url === "/set-valid-host") {
    res.writeHead(200, {
      "Set-Cookie": "__Host-session=host-ok; Path=/; Secure; HttpOnly; SameSite=Lax",
      "Content-Type": "text/html; charset=utf-8"
    });
    return res.end(page);
  }

  if (req.url === "/set-invalid-domain") {
    res.writeHead(200, {
      "Set-Cookie": "__Host-session=domain-bad; Domain=localhost; Path=/; Secure; HttpOnly",
      "Content-Type": "text/html; charset=utf-8"
    });
    return res.end(page);
  }

  if (req.url === "/set-invalid-path") {
    res.writeHead(200, {
      "Set-Cookie": "__Host-session=path-bad; Path=/app; Secure; HttpOnly",
      "Content-Type": "text/html; charset=utf-8"
    });
    return res.end(page);
  }

  if (req.url === "/set-secure") {
    res.writeHead(200, {
      "Set-Cookie": "__Secure-preference=compact; Secure; Path=/; SameSite=Lax",
      "Content-Type": "text/html; charset=utf-8"
    });
    return res.end(page);
  }

  if (req.url === "/echo") {
    res.writeHead(200, {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store"
    });
    return res.end("Cookie header: " + (req.headers.cookie ?? "(none)"));
  }

  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
  res.end(page);
}).listen(3443, () => {
  console.log("Open https://localhost:3443");
});
```

Chạy `node cookie-prefix-lab.mjs` rồi mở `https://localhost:3443`. Nếu browser cảnh báo chứng chỉ, cấu hình chứng chỉ local tin cậy trước khi thử. Không bỏ qua cảnh báo chứng chỉ cho hệ thống thật.

### 9.2. Quan sát từng trường hợp

1. Mở `/set-valid-host`. Response có `__Host-session` với `Secure`, `HttpOnly`, `Path=/` và không có `Domain`. Trên browser hỗ trợ prefix, cookie được lưu.
2. Mở `/set-invalid-domain`. Header có `Domain=localhost` nên vi phạm quy tắc `__Host-`; browser hỗ trợ phải từ chối.
3. Mở `/set-invalid-path`. `Path=/app` không hợp lệ cho `__Host-`; browser hỗ trợ phải từ chối.
4. Mở `/set-secure`. Cookie `__Secure-preference` được chấp nhận từ HTTPS với `Secure`.
5. Trong DevTools → Application/Storage → Cookies, xem tên, Domain, Path, Secure, HttpOnly, SameSite. Cookie HttpOnly không xuất hiện trong `document.cookie`.
6. Trong Network, mở từng response và kiểm tra `Set-Cookie` cùng thông tin blocked reason nếu trình duyệt cung cấp.

Để kiểm tra prefix mới, thêm response:

```http
Set-Cookie: __Http-server-only=ok; Secure; HttpOnly; Path=/; SameSite=Lax
Set-Cookie: __Host-Http-session=ok; Secure; HttpOnly; Path=/; SameSite=Lax
```

Sau đó thử tạo tên tương ứng bằng `document.cookie` trên browser hỗ trợ prefix:

```javascript
document.cookie = "__Http-script=bad; Secure; Path=/";
document.cookie = "__Host-Http-script=bad; Secure; Path=/";
```

Vì script không thể đặt `HttpOnly`, các cookie vi phạm điều kiện prefix mới phải bị từ chối ở browser hỗ trợ chúng. Nếu browser không hỗ trợ `__Http-` hoặc `__Host-Http-`, kết quả có thể khác; ghi rõ phiên bản browser và đối chiếu tài liệu tương thích.

### 9.3. Kiểm tra cookie header và server

Mở `https://localhost:3443/echo` để xem cookie được gửi trong request. Header `Cookie` chỉ chứa tên và giá trị; nó không gửi lại thuộc tính `Secure`, `HttpOnly`, `SameSite`, `Path` hoặc `Domain`. Vì vậy server không thể dựa vào header này để suy ra browser đã thực thi prefix nào; việc kiểm tra prefix là trách nhiệm user agent khi lưu cookie.

Dừng server bằng Ctrl+C. Lab không xác thực người dùng và không được triển khai công khai.


## 10. Những ngộ nhận thường gặp

**“Chỉ cần tên cookie bắt đầu bằng `__Host-` là đủ.”** Sai. Phải có secure origin, `Secure`, `Path=/` và không có `Domain`.

**“`__Secure-` cũng tự động là host-only.”** Sai. Prefix này không cấm `Domain` và không bắt buộc `Path=/`.

**“`__Host-` đồng nghĩa HttpOnly.”** Sai. `__Host-` không yêu cầu `HttpOnly`; phải thêm thuộc tính này nếu cookie phiên không cần JavaScript đọc.

**“JavaScript có thể tự tạo cookie HttpOnly nếu tên có `__Http-`.”** Sai. `HttpOnly` chỉ được đặt qua HTTP response; browser hỗ trợ prefix sẽ từ chối cookie script-set không thỏa yêu cầu.

**“Mọi trình duyệt đều hỗ trợ bốn prefix.”** Sai. Hỗ trợ `__Secure-`/`__Host-` rộng hơn; `__Http-`/`__Host-Http-` mới hơn và có thể khác theo browser/version.

**“Cookie prefix thay thế SameSite và CSRF token.”** Sai. Prefix kiểm soát điều kiện chấp nhận cookie; SameSite và CSRF bảo vệ các khía cạnh khác.

**“HttpOnly ngăn XSS thực hiện hành động bằng phiên.”** Sai. Nó ngăn đọc cookie trực tiếp, nhưng script XSS vẫn có thể gửi request từ origin bị xâm nhập.

**“Cookie header cho server biết cookie đã được thiết lập với Domain/Path nào.”** Sai. Header chỉ mang các cặp tên/giá trị.

**“Cookie prefix bảo vệ được nếu chính ứng dụng bị xâm nhập.”** Sai. Mã hoặc server bị chiếm quyền trên chính host vẫn có thể tác động đến cookie và phiên theo các khả năng được cấp.

## 11. Checklist triển khai cookie prefix

Trước khi phát hành cookie phiên, kiểm tra:

1. **Chọn prefix:** ưu tiên `__Host-` khi session chỉ cần trên một host; cân nhắc `__Host-Http-` sau khi xác minh hỗ trợ browser.
2. **Secure origin:** phát cookie từ HTTPS và bật `Secure`.
3. **Host-only:** với `__Host-`, đặt `Path=/` và bỏ hoàn toàn thuộc tính `Domain`.
4. **HttpOnly:** thêm `HttpOnly` cho cookie phiên nếu JavaScript không cần đọc.
5. **SameSite:** chọn `Strict`/`Lax`/`None` theo luồng thực tế; `None` cần `Secure`.
6. **Cookie naming:** tên prefix đúng chữ hoa/chữ thường; không tạo cookie trùng tên ở path/domain khác.
7. **Session lifecycle:** rotate session ID sau login/đổi quyền, thu hồi khi logout và hết hạn phía server.
8. **CSRF:** có token hoặc cơ chế tương đương, kiểm tra nguồn request và quyền trên server.
9. **XSS:** output encoding, DOM API an toàn, CSP và Trusted Types phù hợp; nhớ HttpOnly không chặn request do XSS tạo.
10. **Subdomain:** kiểm kê host/tenant và nguy cơ takeover; tránh cookie Domain rộng nếu không bắt buộc.
11. **Browser support:** kiểm tra phiên bản mục tiêu; không giả định prefix mới được mọi browser thực thi.
12. **DevTools:** xác nhận cookie được lưu, thuộc tính đúng, cookie bị từ chối có lý do và request chỉ gửi cookie đúng host/path.

### Câu hỏi tự kiểm tra

**Câu 1.** Cookie `__Host-session` được gửi với `Secure` và `Path=/` nhưng có `Domain=example.com`. Có hợp lệ không?  
**Đáp án:** Không. `__Host-` cấm thuộc tính `Domain`.

**Câu 2.** `__Secure-session` có bắt buộc host-only không?  
**Đáp án:** Không. Prefix yêu cầu secure origin và `Secure`, nhưng không cấm `Domain`.

**Câu 3.** Vì sao cookie session nên có `HttpOnly`?  
**Đáp án:** Để JavaScript không đọc trực tiếp giá trị cookie qua `document.cookie`; điều này giảm nguy cơ đánh cắp cookie nhưng không loại bỏ XSS.

**Câu 4.** `__Host-` có ngăn CSRF không?  
**Đáp án:** Không. Nó ràng buộc host/path và Secure; CSRF cần SameSite cùng token/kiểm tra nguồn và xác thực phía server.

**Câu 5.** Có thể biết cookie có `HttpOnly` chỉ từ header request `Cookie` không?  
**Đáp án:** Không. Request header không chứa thuộc tính cookie.

**Câu 6.** Nếu browser không hỗ trợ `__Host-Http-`, có nên bỏ `Secure`/`HttpOnly` để tương thích không?  
**Đáp án:** Không. Vẫn gửi đầy đủ thuộc tính bảo vệ cookie; prefix là lớp tăng cường trên browser hỗ trợ, không phải lý do hạ thấp cấu hình.

## 12. Ghi nhớ cốt lõi

Cookie prefix là một lớp ràng buộc do trình duyệt thực thi khi chấp nhận cookie. `__Secure-` yêu cầu cookie được thiết lập từ secure origin và có `Secure`. `__Host-` bổ sung `Path=/` và cấm `Domain`, tạo cookie host-only. `__Http-` bổ sung yêu cầu `HttpOnly` để cookie được thiết lập qua HTTP response; `__Host-Http-` kết hợp cả hai nhóm ràng buộc trên những browser hỗ trợ.

Đối với session cookie trên một host, `__Host-session` cùng `Secure`, `HttpOnly` và `SameSite` tường minh là lựa chọn mạnh, tương thích rộng. Prefix giúp giảm cookie tossing từ subdomain và làm cấu hình rõ ràng hơn, nhưng **không thay thế** phòng vệ XSS, CSRF, kiểm soát quyền phía server, quản lý session hay kiểm thử browser.

### Tài liệu tham khảo

- [MDN — Set-Cookie header and cookie prefixes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).
- [MDN — HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies).
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265).
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

