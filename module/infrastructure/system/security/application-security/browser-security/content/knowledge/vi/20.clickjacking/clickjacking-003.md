# X-Frame-Options: ngăn trang web bị nhúng trái phép

## 1. Clickjacking là gì và vì sao cần X-Frame-Options?

Clickjacking là kỹ thuật khiến người dùng tưởng rằng họ đang nhấn vào một thành phần giao diện bình thường, trong khi thao tác thực tế được chuyển tới một trang hoặc nút khác đang bị che giấu. Một cách triển khai phổ biến là attacker nhúng trang mục tiêu vào `iframe`, làm iframe trong suốt hoặc đặt nó lệch khỏi vùng nhìn thấy, rồi phủ lên bằng nội dung dụ người dùng nhấn.

Ví dụ, người dùng nghĩ rằng mình đang nhấn nút “Xem video”, nhưng vị trí đó trùng với nút “Xác nhận thay đổi” trong trang tài khoản được nhúng phía dưới. Nếu người dùng đã đăng nhập, thao tác có thể được thực hiện bằng phiên hiện tại.

**X-Frame-Options (XFO)** là HTTP response header cho phép một trang chỉ định liệu trình duyệt có được phép hiển thị trang đó bên trong frame hay không. Header này giúp giảm nguy cơ clickjacking bằng cách hạn chế website khác nhúng trang nhạy cảm.

Trong module bảo mật trình duyệt, XFO cần được hiểu cùng với iframe, origin, CSP `frame-ancestors`, SameSite cookie, CSRF, xác thực và các security headers. XFO kiểm soát việc trang có được phép bị nhúng; nó không xác minh người dùng có quyền thực hiện một hành động và cũng không thay thế các biện pháp chống CSRF.

Sau bài học, bạn có thể:

- Giải thích cách clickjacking lợi dụng iframe và giao diện bị che.
- Cấu hình `X-Frame-Options: DENY` hoặc `SAMEORIGIN`.
- Nhận diện giới hạn của giá trị cũ `ALLOW-FROM`.
- Phân biệt XFO với CSP `frame-ancestors` và `frame-src`.
- Kiểm tra header trên response thực tế bằng DevTools và curl.
- Triển khai chính sách framing nhất quán ở ứng dụng và reverse proxy.

## 2. Cơ chế clickjacking qua iframe

Giả sử người dùng đang đăng nhập vào `https://account.example.com`. Attacker tạo một trang khác và nhúng trang tài khoản:

```html
<iframe
  src="https://account.example.com/security/confirm"
  class="hidden-target">
</iframe>
```

Attacker có thể phủ nội dung giả lên iframe hoặc làm iframe trong suốt. Người dùng nhấn vào một nút nhìn thấy được, nhưng click được chuyển tới vị trí của một control trong trang mục tiêu.

Luồng khái quát:

```text
Người dùng đăng nhập account.example.com
                 │
                 ▼
Trình duyệt lưu session cookie
                 │
                 ▼
Người dùng mở trang attacker
                 │
                 ▼
Trang attacker nhúng account.example.com bằng iframe
                 │
                 ▼
Giao diện giả che vị trí nút thật
                 │
                 ▼
Người dùng nhấn vào giao diện giả
                 │
                 ▼
Click tới control trong trang mục tiêu
                 │
                 ▼
Hành động ngoài ý muốn có thể được thực hiện
```

Attacker không nhất thiết phải đọc nội dung iframe. Same-Origin Policy (SOP) thường ngăn trang attacker truy cập DOM của iframe khác origin, nhưng không tự ngăn việc hiển thị iframe hoặc chuyển thao tác nhấn tới nội dung bên trong.

### 2.1 Vì sao cookie authentication làm hậu quả nghiêm trọng hơn?

Nếu trang mục tiêu dùng cookie session, trình duyệt có thể tự gửi cookie khi người dùng tương tác với trang đã đăng nhập. Khi clickjacking khiến người dùng kích hoạt một control thật, server có thể nhận request mang phiên hợp lệ.

Điều này khác với CSRF ở cách kích hoạt:

- CSRF thường khiến trình duyệt gửi request ngoài ý muốn mà không cần người dùng nhấn đúng control trong trang mục tiêu.
- Clickjacking lợi dụng cách bố trí giao diện để người dùng tự thực hiện một thao tác mà họ không nhận biết đúng.

Hai loại tấn công có thể kết hợp. Vì vậy, ứng dụng cần cả chính sách chống framing, CSRF token, xác minh hành động nhạy cảm và kiểm soát quyền phía server.

## 3. Cú pháp X-Frame-Options

XFO là response header. Hai giá trị được sử dụng phổ biến là:

```http
X-Frame-Options: DENY
```

và:

```http
X-Frame-Options: SAMEORIGIN
```

| Giá trị | Hành vi |
| --- | --- |
| `DENY` | Trình duyệt không cho trang được hiển thị trong frame, iframe, embed hoặc object theo cơ chế hỗ trợ XFO. |
| `SAMEORIGIN` | Chỉ cho phép framing khi ngữ cảnh nhúng đáp ứng điều kiện same-origin theo cách triển khai của browser. |
| `ALLOW-FROM uri` | Cú pháp cũ từng nhằm cho phép một origin cụ thể; đã lỗi thời và không được browser hiện đại hỗ trợ nhất quán. |

### 3.1 DENY

`DENY` là lựa chọn chặt nhất:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
X-Frame-Options: DENY
```

Trang không được nhúng trong iframe, kể cả bởi một trang cùng origin. Đây thường là lựa chọn phù hợp cho:

- Trang đăng nhập.
- Trang quản trị.
- Trang cài đặt bảo mật.
- Trang xác nhận giao dịch.
- Khu vực tài khoản không có nhu cầu nhúng hợp lệ.

Nếu sản phẩm có chức năng nhúng trang vào portal hoặc dashboard, `DENY` có thể làm hỏng chức năng đó. Hãy xác định nhu cầu embedding trước khi áp dụng ở phạm vi toàn site.

### 3.2 SAMEORIGIN

`SAMEORIGIN` cho phép trang được nhúng bởi trang cùng origin:

```http
X-Frame-Options: SAMEORIGIN
```

Origin bao gồm scheme, host và port. Vì vậy:

| Trang mục tiêu | Trang nhúng | Same-origin? |
| --- | --- | --- |
| `https://app.example.com` | `https://app.example.com` | Có, nếu port hiệu lực giống nhau. |
| `https://app.example.com` | `http://app.example.com` | Không, scheme khác. |
| `https://app.example.com` | `https://portal.example.com` | Không, host khác. |
| `https://app.example.com` | `https://app.example.com:8443` | Không, port khác. |

`SAMEORIGIN` phù hợp khi ứng dụng có nhu cầu nhúng nội dung giữa các trang cùng origin. Nó không cho phép tất cả subdomain cùng site. Ví dụ `portal.example.com` và `app.example.com` khác origin dù có thể cùng site.

Khi có nhiều lớp iframe lồng nhau, quy tắc framing có thể phụ thuộc cách browser kiểm tra ancestor chain. Với chính sách nhúng phức tạp, nên dùng CSP `frame-ancestors`, vốn được thiết kế để biểu đạt danh sách ancestor được phép một cách rõ ràng.

### 3.3 ALLOW-FROM đã lỗi thời

Ví dụ cú pháp cũ:

```http
X-Frame-Options: ALLOW-FROM https://portal.example.com
```

Không dùng `ALLOW-FROM` cho hệ thống mới. Giá trị này đã lỗi thời, bị loại khỏi chuẩn hiện đại và không được hỗ trợ đồng nhất giữa các browser. Một số browser có thể bỏ qua header hoặc xử lý khác nhau.

Nếu cần cho phép một hoặc nhiều đối tác nhúng trang, dùng CSP `frame-ancestors`:

```http
Content-Security-Policy: frame-ancestors 'self' https://portal.example.com https://dashboard.partner.example
```

Chính sách này cho phép ancestor cùng origin và hai origin đối tác đã liệt kê. Mọi ancestor trong chuỗi framing phải đáp ứng chính sách.

## 4. XFO phải được gửi trong HTTP response header

XFO là HTTP response header. Đặt nó trong HTML meta element không có tác dụng:

```html
<!-- Không có tác dụng như X-Frame-Options response header -->
<meta http-equiv="X-Frame-Options" content="DENY">
```

Hãy cấu hình tại server, framework hoặc reverse proxy để header xuất hiện trong response HTML thực tế:

```http
HTTP/1.1 200 OK
Content-Type: text/html
X-Frame-Options: DENY
```

Header cần được áp dụng cho mọi response có nội dung có thể bị nhúng, không chỉ trang chủ. Cần kiểm tra:

- Trang đăng nhập và đăng xuất.
- Trang tài khoản và quản trị.
- Endpoint trả HTML qua route phụ.
- Trang lỗi do ứng dụng tạo.
- Redirect và response được tạo ở tầng proxy.
- Các phiên bản HTTP/HTTPS và hostname được sản phẩm hỗ trợ.

Không phải mọi response cần cùng một chính sách. Ví dụ một widget có nhu cầu nhúng có thể có chính sách riêng, nhưng cần giới hạn rõ endpoint và origin đối tác.

## 5. CSP frame-ancestors là lựa chọn hiện đại

XFO là cơ chế cũ, có hai lựa chọn chính hữu ích và không biểu đạt được allowlist nhiều origin một cách linh hoạt. CSP cung cấp directive `frame-ancestors` để kiểm soát những origin nào được phép nhúng tài liệu.

Các ví dụ:

```http
Content-Security-Policy: frame-ancestors 'none'
```

Không cho phép bất kỳ ancestor nào nhúng trang.

```http
Content-Security-Policy: frame-ancestors 'self'
```

Chỉ cho phép ancestor cùng origin.

```http
Content-Security-Policy: frame-ancestors 'self' https://portal.example.com
```

Cho phép trang cùng origin và portal đối tác cụ thể nhúng trang.

### 5.1 frame-ancestors không có fallback từ default-src

Khác nhiều fetch directives, `frame-ancestors` không dùng `default-src` làm fallback. Nếu muốn kiểm soát ai được nhúng trang, phải khai báo trực tiếp:

```http
Content-Security-Policy: default-src 'self'; frame-ancestors 'none'
```

Chỉ khai báo `default-src 'self'` không thay thế được `frame-ancestors 'self'`.

### 5.2 frame-ancestors phải đặt trong response header

Không triển khai `frame-ancestors` bằng meta element:

```html
<!-- Không được browser thực thi như frame-ancestors policy -->
<meta http-equiv="Content-Security-Policy" content="frame-ancestors 'none'">
```

Directive này cần được gửi qua HTTP response header. Meta-delivered CSP không hỗ trợ `frame-ancestors`.

### 5.3 frame-ancestors và XFO cùng tồn tại

Trong browser hiện đại hỗ trợ CSP, nếu policy có `frame-ancestors`, directive này được ưu tiên cho quyết định framing và XFO bị bỏ qua. Tuy nhiên, có thể giữ XFO như lớp tương thích cho browser cũ:

```http
Content-Security-Policy: frame-ancestors 'self' https://portal.example.com
X-Frame-Options: SAMEORIGIN
```

Ví dụ trên có thể gây khác biệt giữa browser hiện đại và browser cũ: browser hiện đại áp dụng allowlist từ `frame-ancestors`, còn browser cũ chỉ hiểu `SAMEORIGIN` có thể không cho portal khác origin nhúng. Nếu cần hỗ trợ embedding cross-origin, hãy đánh giá tập browser mục tiêu và không giả định XFO có thể biểu đạt cùng allowlist.

Với ứng dụng chỉ cho phép cùng origin hoặc cấm hoàn toàn framing, XFO và `frame-ancestors` có thể được cấu hình nhất quán:

```http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
```

## 6. Phân biệt frame-ancestors với frame-src

Hai directive có tên gần nhau nhưng kiểm soát hai hướng khác nhau:

| Directive | Ai kiểm soát? | Ý nghĩa |
| --- | --- | --- |
| `frame-ancestors` | Trang đang được tải | Ai được phép nhúng trang này? |
| `frame-src` | Trang đang chạy | Trang này được phép tải iframe từ đâu? |

Ví dụ:

```http
Content-Security-Policy: frame-src https://video.example.com; frame-ancestors 'none'
```

Trang được phép nhúng video từ `video.example.com`, nhưng bản thân trang không được website khác nhúng vào frame.

Ngược lại:

```http
Content-Security-Policy: frame-src 'none'; frame-ancestors 'self'
```

Trang không được tải iframe con, nhưng có thể được nhúng bởi trang cùng origin.

Đừng dùng `frame-src` để thay thế XFO hoặc `frame-ancestors`; nó không trả lời câu hỏi ai được phép nhúng trang hiện tại.

## 7. Chọn chính sách framing cho từng loại trang

Chính sách nên phản ánh nhu cầu sản phẩm và rủi ro của từng nhóm route.

| Loại trang | Chính sách thường phù hợp | Lý do |
| --- | --- | --- |
| Đăng nhập | `DENY` hoặc `frame-ancestors 'none'` | Tránh trang đăng nhập bị nhúng và giả giao diện. |
| Quản trị | `DENY` hoặc `frame-ancestors 'none'` | Ngăn clickjacking trên hành động có quyền cao. |
| Trang tài khoản | `DENY` hoặc `SAMEORIGIN` | Chỉ cho phép nhúng nội bộ nếu có nhu cầu rõ ràng. |
| Widget dành cho đối tác | `frame-ancestors` allowlist | Cho phép đúng portal/partner đã xác định. |
| Trang tài liệu công khai | Tùy nhu cầu; có thể `SAMEORIGIN` hoặc allowlist | Nội dung công khai vẫn có thể có nút hoặc trạng thái người dùng. |

Không quyết định chỉ dựa trên việc trang có chứa dữ liệu bí mật hay không. Một trang công khai vẫn có thể chứa nút đăng ký, mua hàng, xác nhận hoặc thao tác tài khoản có thể bị clickjacking.

### 7.1 Tách route nếu nhu cầu nhúng khác nhau

Nếu chỉ một widget cần được nhúng cross-origin, tránh nới lỏng chính sách cho toàn bộ ứng dụng. Có thể tách widget thành route hoặc subdomain riêng, với dữ liệu và quyền tối thiểu:

```text
app.example.com
  /login       -> DENY
  /account     -> DENY
  /admin       -> DENY

embed.example.com
  /status-card -> frame-ancestors 'self' https://portal.partner.example
```

Tách biệt host giúp giảm phạm vi cookie và quyền truy cập. Widget nên nhận dữ liệu tối thiểu, không chia sẻ session cookie quản trị nếu không cần, và vẫn xác thực mọi thao tác ở backend.

## 8. Cấu hình XFO tại server và reverse proxy

XFO cần được phát nhất quán. Có thể cấu hình ở ứng dụng hoặc reverse proxy; cần tránh cả hai tầng phát ra các giá trị xung đột.

### 8.1 Nginx

Ví dụ cấm framing:

```nginx
add_header X-Frame-Options "DENY" always;
```

Từ khóa `always` yêu cầu Nginx thêm header cho cả các response có status lỗi phù hợp, không chỉ một số response thành công. Hãy kiểm tra phạm vi `http`, `server` và `location` để biết directive được kế thừa như thế nào; cấu hình ở location có thể ảnh hưởng việc kế thừa header từ cấp trên.

Nếu dùng CSP:

```nginx
add_header Content-Security-Policy "frame-ancestors 'none'" always;
add_header X-Frame-Options "DENY" always;
```

Không thêm một CSP hoàn chỉnh bằng chuỗi mới nếu ứng dụng đã phát CSP khác mà chưa hiểu cách các policy được kết hợp. Nhiều enforcement policies cùng tồn tại có thể làm chính sách chặt hơn dự kiến.

### 8.2 Apache HTTP Server

Ví dụ:

```apache
Header always set X-Frame-Options "DENY"
```

Với CSP:

```apache
Header always set Content-Security-Policy "frame-ancestors 'none'"
```

Cần bảo đảm module headers đã được bật và directive được đặt trong virtual host hoặc directory phù hợp. Kiểm tra response thực tế vì ứng dụng hoặc proxy phía trước có thể thay đổi header.

### 8.3 Java Servlet

Ứng dụng Java có thể đặt response header trước khi gửi nội dung:

```java
protected void doGet(HttpServletRequest request,
                     HttpServletResponse response) throws IOException {
    response.setHeader("X-Frame-Options", "DENY");
    response.setContentType("text/html;charset=UTF-8");
    response.getWriter().write("<!doctype html><title>Account</title>");
}
```

Trong ứng dụng thật, nên đặt header ở security filter hoặc cơ chế cấu hình bảo mật dùng chung để không bỏ sót route. Nếu một route cần embedding khác biệt, tạo ngoại lệ có chủ đích và kiểm tra quyền truy cập.

### 8.4 Tránh header trùng hoặc xung đột

Kiểm tra xem ứng dụng, framework, CDN và reverse proxy có cùng phát XFO hay không. Không dựa vào việc browser sẽ chọn một giá trị “đúng” khi nhận nhiều giá trị mâu thuẫn. Chọn một nơi làm nguồn cấu hình chính hoặc bảo đảm mọi tầng phát cùng một chính sách.

## 9. XFO không thay thế các biện pháp bảo vệ khác

XFO giảm nguy cơ trang bị nhúng trái phép, nhưng có phạm vi bảo vệ giới hạn.

| Biện pháp | Bảo vệ chính | XFO có thay thế được không? |
| --- | --- | --- |
| CSP `frame-ancestors` | Kiểm soát ancestor được phép nhúng trang. | Không; đây là cơ chế hiện đại và linh hoạt hơn. |
| CSRF token | Xác minh request thay đổi trạng thái đến từ luồng ứng dụng hợp lệ. | Không. |
| SameSite cookie | Hạn chế gửi cookie trong một số ngữ cảnh cross-site. | Không. |
| Authentication | Xác định phiên/người dùng. | Không. |
| Authorization | Kiểm tra quyền trên tài nguyên/hành động. | Không. |
| XSS prevention | Ngăn script độc hại chạy trong origin. | Không. |
| `frame-src` | Kiểm soát iframe mà trang được phép tải. | Không; hướng kiểm soát khác. |

XFO cũng không bảo vệ khỏi một trang độc hại đã chạy được script cùng origin, một extension có quyền mạnh hoặc người dùng bị lừa thực hiện hành động qua giao diện hợp lệ mà không cần framing. Hãy dùng xác nhận lại cho giao dịch nhạy cảm, CSRF protection và kiểm tra quyền ở server.

### 9.1 Frame-busting JavaScript không phải giải pháp chính

Một số ứng dụng cũ dùng script kiểm tra `window.top !== window.self` rồi điều hướng ra khỏi frame. Kỹ thuật frame-busting này có thể bị vô hiệu hóa bởi sandbox, race condition, trình duyệt hoặc cách attacker bố trí trang.

HTTP response headers được browser thực thi trước khi nội dung trang hoạt động là cách kiểm soát framing đáng tin cậy hơn. Không dựa vào JavaScript frame-busting để thay XFO hoặc `frame-ancestors`.

## 10. Kiểm thử X-Frame-Options bằng DevTools

Thực hiện trên ứng dụng thử nghiệm do bạn kiểm soát.

### 10.1 Kiểm tra response header

1. Mở trang mục tiêu bằng browser.
2. Mở DevTools → Network.
3. Chọn document request chính.
4. Trong Response Headers, tìm `X-Frame-Options`.
5. Kiểm tra `DENY` hoặc `SAMEORIGIN` đúng với thiết kế.
6. Kiểm tra cả response lỗi, redirect và route phụ.

Header cần xuất hiện trong response HTML thực tế. Việc thấy cấu hình trong file Nginx hoặc Java code không chứng minh request production đã nhận header.

### 10.2 Tạo trang kiểm thử iframe cùng origin

Trong lab cùng origin, tạo trang:

```html
<!doctype html>
<html lang="vi">
  <body>
    <h1>Trang kiểm thử cùng origin</h1>
    <iframe src="/account" title="Account page"></iframe>
  </body>
</html>
```

Kết quả mong đợi:

- Với `DENY`, trang `/account` không được hiển thị trong iframe.
- Với `SAMEORIGIN`, trang cùng origin có thể được hiển thị trong iframe.

### 10.3 Tạo trang kiểm thử cross-origin

Chạy trang nhúng trên một origin khác, ví dụ `https://attacker-lab.example.net`, rồi nhúng:

```html
<!doctype html>
<html lang="vi">
  <body>
    <h1>Trang kiểm thử cross-origin</h1>
    <iframe
      src="https://app.example.com/account"
      title="Cross-origin framing test">
    </iframe>
  </body>
</html>
```

Kết quả mong đợi:

- `DENY`: browser chặn trang mục tiêu bị nhúng.
- `SAMEORIGIN`: browser chặn vì origin trang nhúng khác origin mục tiêu.
- `ALLOW-FROM`: không dựa vào giá trị này; browser hiện đại có thể bỏ qua.

Browser thường hiển thị thông báo framing bị từ chối trong Console. Trang ngoài có thể chỉ thấy iframe trống hoặc thông báo lỗi; điều đó không có nghĩa iframe đã tải nội dung thành công.

### 10.4 Kiểm tra bằng curl

Có thể xem response header:

```bash
curl -I https://app.example.com/account
```

Kết quả mong đợi có dạng:

```http
HTTP/2 200
content-type: text/html; charset=utf-8
x-frame-options: DENY
```

curl chỉ đọc response header; nó không mô phỏng hành vi framing của browser. Cần kết hợp curl với thử nghiệm iframe và Console.

## 11. Chẩn đoán lỗi và sự cố triển khai

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Portal nội bộ không nhúng được trang | Trang mục tiêu phát `DENY` hoặc `SAMEORIGIN`. | Kiểm tra XFO và CSP `frame-ancestors` trên response. |
| `ALLOW-FROM` không có tác dụng | Browser không hỗ trợ cú pháp cũ. | Thay bằng CSP `frame-ancestors`. |
| Header có trong trang chủ nhưng thiếu ở trang con | Cấu hình chỉ áp dụng một route hoặc response được tạo ở tầng khác. | Kiểm tra từng document response, lỗi và redirect. |
| Browser vẫn chặn dù đã thêm portal vào frame-ancestors | XFO `SAMEORIGIN` hoặc CSP enforcement khác vẫn áp dụng ở browser tương ứng. | Kiểm tra tất cả CSP headers và XFO thực tế. |
| CSP meta không ngăn framing | `frame-ancestors` không được hỗ trợ qua meta delivery. | Phát directive qua HTTP response header. |
| Cùng origin vẫn không nhúng được | Có `DENY`, CSP `frame-ancestors 'none'` hoặc ancestor khác origin trong chuỗi. | Kiểm tra toàn bộ ancestor chain và response policy. |
| curl cho thấy header nhưng browser không hành xử như mong đợi | Có cache, redirect, response khác hoặc policy bổ sung. | Kiểm tra request document thực tế trong Network và Console. |
| Header bị lặp | App, proxy và CDN cùng thêm header. | Chọn một nguồn cấu hình hoặc đồng bộ các tầng. |

### 11.1 Nhiều CSP headers

Nếu response có nhiều CSP enforcement headers, browser áp dụng đồng thời tất cả policy. Policy thứ hai không thể nới lỏng policy thứ nhất. Ví dụ một header cho phép portal đối tác nhưng header khác có `frame-ancestors 'self'` thì portal đối tác vẫn có thể bị chặn.

Kiểm tra toàn bộ response headers ở điểm cuối mà browser nhận, không chỉ file cấu hình của ứng dụng.

### 11.2 Cache và CDN

Nếu chính sách framing thay đổi theo route hoặc tenant, cần kiểm tra CDN cache có phục vụ nhầm response/header hay không. Header bảo mật nên được gắn nhất quán với nội dung response tương ứng. Không để cache trả nội dung widget với policy của trang tài khoản hoặc ngược lại.

## 12. Quy trình triển khai

1. **Lập danh sách route:** phân loại trang đăng nhập, tài khoản, quản trị, widget và nội dung công khai.
2. **Xác định nhu cầu nhúng:** hỏi route nào thật sự cần được iframe, bởi origin nào và vì mục đích gì.
3. **Chọn chính sách:** dùng `DENY` cho trang không cần nhúng; `SAMEORIGIN` nếu chỉ cần nhúng nội bộ; dùng `frame-ancestors` allowlist nếu cần partner.
4. **Cấu hình ở response:** đặt header tại framework hoặc reverse proxy, bảo đảm áp dụng cho các route cần bảo vệ.
5. **Kiểm tra header trùng:** xem response thực tế từ CDN/proxy và loại bỏ giá trị xung đột.
6. **Thử iframe:** kiểm tra same-origin, cross-origin và chuỗi frame lồng nhau trên browser mục tiêu.
7. **Kiểm tra luồng nghiệp vụ:** xác nhận widget hợp lệ vẫn hoạt động và trang nhạy cảm không bị nhúng.
8. **Theo dõi sau triển khai:** kiểm tra Console, báo cáo CSP và phản hồi từ các portal tích hợp.

## 13. Checklist bảo vệ chống clickjacking

- [ ] Trang đăng nhập và trang nhạy cảm có XFO hoặc CSP `frame-ancestors`.
- [ ] `DENY` được dùng ở route không có nhu cầu nhúng.
- [ ] `SAMEORIGIN` chỉ được dùng khi embedding cùng origin thực sự cần thiết.
- [ ] Không dùng `ALLOW-FROM` cho triển khai mới.
- [ ] `frame-ancestors` được phát qua HTTP response header, không qua meta.
- [ ] Không nhầm `frame-ancestors` với `frame-src`.
- [ ] Mọi origin đối tác được cho phép đều có lý do nghiệp vụ và được xác minh.
- [ ] Header có trên route, error response và các host cần thiết.
- [ ] Không có XFO/CSP headers xung đột từ ứng dụng, proxy hoặc CDN.
- [ ] Đã thử framing cùng origin và cross-origin trên browser mục tiêu.
- [ ] CSRF token, authorization và xác nhận giao dịch vẫn được áp dụng.
- [ ] Widget được nhúng có dữ liệu và quyền tối thiểu.

## 14. Câu hỏi tự kiểm tra

1. Clickjacking lợi dụng iframe và thao tác người dùng như thế nào?
2. `X-Frame-Options: DENY` khác `SAMEORIGIN` ở điểm nào?
3. Vì sao origin khác subdomain vẫn không đáp ứng `SAMEORIGIN`?
4. Vì sao không nên dùng `ALLOW-FROM`?
5. XFO được gửi ở đâu và vì sao meta element không có tác dụng?
6. `frame-ancestors` khác `frame-src` như thế nào?
7. Nếu có cả XFO và CSP `frame-ancestors`, browser hiện đại xử lý framing theo cơ chế nào?
8. Vì sao curl thành công không chứng minh browser cho phép iframe?
9. XFO có thay thế CSRF token hoặc authorization không?
10. Làm thế nào cho phép một portal đối tác nhúng widget mà vẫn cấm nhúng trang quản trị?

## 15. Tổng kết

`X-Frame-Options` là response header giúp kiểm soát việc trang có được hiển thị trong frame hay không. `DENY` cấm framing; `SAMEORIGIN` chỉ cho phép framing cùng origin; `ALLOW-FROM` đã lỗi thời và không được browser hiện đại hỗ trợ nhất quán. Header phải được gửi trong HTTP response, không thể thay bằng meta element.

Với ứng dụng hiện đại, CSP `frame-ancestors` là lựa chọn linh hoạt hơn: có thể cấm mọi ancestor, chỉ cho phép same-origin hoặc chỉ định các portal đối tác cụ thể. Directive này không có fallback từ `default-src`, phải được phát qua response header và kiểm tra toàn bộ chuỗi ancestor. XFO/`frame-ancestors` giảm nguy cơ clickjacking nhưng không thay thế CSRF protection, XSS prevention, authentication hay authorization. Hãy chọn chính sách theo từng route, kiểm tra response thực tế và thử iframe trên browser mục tiêu trước khi triển khai rộng.
