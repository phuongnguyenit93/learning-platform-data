# X-Frame-Options, CSP frame-ancestors và phòng chống clickjacking

## Mục tiêu học tập

Bài học thuộc **Header và HTTPS** của **Spring Security reactive (Spring WebFlux)**. Sau bài học, bạn có thể:

- Giải thích **clickjacking/UI redressing** và vai trò của việc nhúng trang nhạy cảm qua `<iframe>`, ngay cả khi attacker không đọc được DOM của iframe.
- Phân biệt rõ `X-Frame-Options: DENY`, `X-Frame-Options: SAMEORIGIN` và directive `Content-Security-Policy: frame-ancestors ...`.
- Biết `frame-ancestors` kiểm soát **ai được nhúng trang của mình**, khác `frame-src` (trang của mình được tải những frame nào); hiểu nested iframes, origin và thứ tự ưu tiên khi cùng có hai header.
- Cấu hình an toàn `ServerHttpSecurity.headers(...)` trong Spring Security WebFlux, giữ mặc định `DENY` cho trang nhạy cảm và tạo ngoại lệ có kiểm soát cho một trang thật sự cần nhúng.
- Hiểu `frame-ancestors` không được thiết lập qua HTML `meta` và `default-src` không tự tạo fallback; phân biệt chính sách CSP **enforcing** với **Report-Only**.
- Viết ví dụ **Java 17 + Spring Boot WebFlux**, dùng nhiều `SecurityWebFilterChain` để tách trang có thể nhúng và trang không cho nhúng; chạy phép thử `curl`, `WebTestClient` và **trình duyệt**.
- Nêu được giới hạn của XFO/CSP trước XSS, CSRF, CORS, cookie third-party, reverse proxy và browser cũ; tránh “sửa lỗi iframe” bằng cách bỏ toàn bộ security headers.

> **Chỉ dùng API reactive.** WebFlux dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và `XFrameOptionsServerHttpHeadersWriter.Mode`. Đừng sao chép cách gọi `HttpSecurity.headers().frameOptions().sameOrigin()` của Servlet vì khác DSL/API.

## 1. Clickjacking: người dùng click nhầm một giao diện thật

**Clickjacking** xảy ra khi attacker đặt một **trang thật** của ứng dụng nạn nhân vào `iframe` hoặc một container có thể nhúng, rồi dùng CSS/lớp phủ để khiến người dùng click vào vị trí mà họ tưởng thuộc giao diện attacker nhưng thực tế là nút trong trang nạn nhân.

Ví dụ khái niệm:

~~~text
Trình duyệt của người dùng
  |
  +-- Trang của attacker: https://untrusted.example.test
         |
         +-- Hiển thị trò chơi/nút "Nhận quà"
         |
         +-- Iframe trong suốt/được căn vị trí:
               https://bank.example.test/settings
                    |
                    +-- Nút thật "Bật quyền chuyển tiền"
                        ^
                        |
              Người dùng click nhầm tại tọa độ này
~~~

Trang ngân hàng vẫn là **origin khác** với attacker. Same-Origin Policy (SOP) thường ngăn JavaScript của attacker đọc DOM trong iframe, nhưng SOP **không tự cấm việc nhúng** trang và **không ngăn người dùng click** vào nội dung đã nhúng. Nếu browser tự gửi cookie phiên cho iframe theo cookie policy, trang thật có thể hiển thị dưới danh tính người dùng đã đăng nhập.

Đó là lý do phải kiểm soát **khả năng được nhúng** của những trang có thao tác nhạy cảm. Tấn công có nhiều biến thể như nút phủ/ẩn, điều hướng lừa dối, thao tác chạm trên mobile hoặc kéo–thả; không chỉ giới hạn ở một `iframe` có `opacity:0`.

### 1.1. Các điều kiện tạo rủi ro

Một tình huống clickjacking thường cần nhiều yếu tố:

1. Trang đích có thể render bên trong frame của origin không tin cậy.
2. Người dùng có thể thao tác trên UI đích, đôi khi với phiên/cookie hiện hữu.
3. Attacker dụ người dùng tương tác theo một hướng khiến thao tác rơi vào vùng frame.
4. Hành động có hậu quả và không có lớp xác nhận bổ sung thích hợp.

Không phải iframe nào cũng nguy hiểm: trang công khai, thẻ preview hoặc widget partner được thiết kế để nhúng có thể là use case hợp lệ. Nhưng với trang admin, thanh toán, đổi thông tin liên hệ, cấp quyền hoặc xác nhận giao dịch, mặc định **không cho nhúng** là lựa chọn an toàn.

### 1.2. XFO và CSP xử lý ở đâu?

Cả `X-Frame-Options` và `CSP frame-ancestors` đều là **HTTP response headers của chính trang sẽ bị nhúng**, không phải header của trang mẹ. Browser kiểm tra response của iframe để quyết định có render tài liệu đó dưới cây frame hiện tại hay không.

~~~text
GET https://app.example.test/account/settings
        |
        v
HTTP response của app.example.test:
  X-Frame-Options: DENY
  Content-Security-Policy: frame-ancestors 'none'
        |
        v
Browser từ chối render trang trong iframe
mà attacker dựng ở origin khác
~~~

Sơ đồ trên là behavior mong muốn trong browser hỗ trợ; `curl` chỉ cho thấy header có được phát, không tự áp dụng quy tắc frame. Một kiểm thử đầy đủ cần xem behavior trong browser được hỗ trợ.

## 2. X-Frame-Options: chỉ vài lựa chọn nhưng quan trọng

`X-Frame-Options` (XFO) là HTTP response header chuyên dùng cho việc chống embedding/clickjacking. Các giá trị nên dùng:

~~~http
X-Frame-Options: DENY
~~~

hoặc:

~~~http
X-Frame-Options: SAMEORIGIN
~~~

| Giá trị | Ý nghĩa | Khi nên dùng |
|---|---|---|
| `DENY` | Không được nhúng trang, **kể cả frame cùng origin**. | Admin, giao dịch, settings, API/web UI không cần iframe. |
| `SAMEORIGIN` | Cho phép nhúng khi các ancestor frames thỏa điều kiện **cùng origin** theo cách trình duyệt hiện đại áp dụng. | App thực sự có iframe nội bộ cùng origin. |
| `ALLOW-FROM uri` | **Lỗi thời**, không được nhiều trình duyệt hiện đại hỗ trợ; browser có thể bỏ qua XFO hoàn toàn. | **Không sử dụng.** Chọn CSP `frame-ancestors` cho partner origin. |

### 2.1. DENY không chỉ chặn website lạ

Giả sử trang `https://app.example.test/internal/report` trả:

~~~http
X-Frame-Options: DENY
~~~

Thì cả trang mẹ `https://evil.example.test` **và** trang mẹ `https://app.example.test` đều không được nhúng document này bằng iframe (ở browser áp dụng XFO đúng).

Đừng chọn `DENY` nếu hệ thống thực sự dùng iframe cùng origin cho một màn hình cần hoạt động; hãy xác định nhu cầu trước. Ngược lại, đừng hạ toàn bộ ứng dụng xuống SAMEORIGIN khi chỉ một route cần iframe.

### 2.2. SAMEORIGIN là origin, không phải site

Origin bao gồm **scheme + hostname + port**:

| Trang con | Trang mẹ | Same-origin? |
|---|---|---|
| `https://app.example.test/page` | `https://app.example.test/dashboard` | Có |
| `https://app.example.test/page` | `https://admin.example.test` | Không (subdomain khác) |
| `http://localhost:8080/page` | `http://localhost:3000` | Không (port khác) |
| `https://app.example.test/page` | `http://app.example.test` | Không (scheme khác) |

Đừng nhầm **same-site** của cookie `SameSite` với **same-origin** của XFO/CSP. Hai subdomain cùng một registrable domain có thể là same-site mà vẫn bị `SAMEORIGIN` từ chối.

### 2.3. ALLOW-FROM không phải giải pháp cho partner

Đoạn sau là **phản ví dụ**:

~~~http
X-Frame-Options: ALLOW-FROM https://partner.example.test
~~~

Nhiều browser hiện đại **không hiểu** directive `ALLOW-FROM`; một số bỏ qua XFO, khiến trang có thể bị nhúng rộng hơn dự tính. Không dùng XFO như một allowlist partner. Dùng CSP:

~~~http
Content-Security-Policy: frame-ancestors 'self' https://partner.example.test
~~~

Khi cần tương thích browser cũ không hỗ trợ CSP, xem xét chính sách **fail closed** (để XFO DENY/SAMEORIGIN và chấp nhận browser cũ không nhúng được) hoặc một thiết kế tách widget public riêng. Đừng bỏ kiểm soát chỉ để iframe hoạt động ở mọi browser.

### 2.4. XFO phải là HTTP response header

Sai:

~~~html
<meta http-equiv="X-Frame-Options" content="DENY">
~~~

Browser **không thực thi XFO từ thẻ meta**. Header phải được gửi bởi ứng dụng, gateway hoặc web server trong response thực. Nếu một route trả redirect rồi HTML page khác, hãy kiểm tra header của **HTML response cuối cùng** cùng các route nhạy cảm, không chỉ redirect ban đầu.

## 3. CSP frame-ancestors: chính sách embedding linh hoạt hơn

CSP (Content Security Policy) hỗ trợ directive `frame-ancestors` để quy định những **ancestor origins nào được quyền nhúng tài liệu hiện tại** trong `frame`/`iframe`/`object`/`embed`.

Ba cấu hình quan trọng:

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

~~~http
Content-Security-Policy: frame-ancestors 'self'
~~~

~~~http
Content-Security-Policy: frame-ancestors 'self' https://portal.example.test
~~~

| Directive | Ý nghĩa |
|---|---|
| `frame-ancestors 'none'` | Cấm iframe embedding từ tất cả origin, kể cả chính mình. |
| `frame-ancestors 'self'` | Chỉ cho ancestor cùng origin. |
| `frame-ancestors 'self' https://portal.example.test` | Cho ancestor cùng origin **hoặc** portal được liệt kê. |
| `frame-ancestors https://widget-host.example.test:8443` | Cho một origin rõ scheme/host/port, không áp dụng cho origin khác. |
| Không có `frame-ancestors` | Không có restriction embedding **từ directive này**; XFO hoặc chính sách khác có thể vẫn chặn. |

### 3.1. 'none' và 'self' cần dấu nháy đơn

Hai keyword quan trọng được ghi đúng cú pháp:

- `'none'`: không có ancestor nào được phép.
- `'self'`: ancestor cùng origin với tài liệu.

Ví dụ `frame-ancestors none` hoặc `frame-ancestors self` **không phải cách viết nên dùng** cho keyword; nếu trình duyệt không nhận đúng source expression, policy có thể không vận hành như mong đợi. Dùng cú pháp CSP chuẩn và viết test cho response string thực.

### 3.2. default-src không tự thay frame-ancestors

Đây là lỗi đặc biệt nguy hiểm:

~~~http
Content-Security-Policy: default-src 'none'
~~~

`default-src 'none'` giới hạn **nhiều loại subresource**, nhưng **không tạo fallback cho frame-ancestors**. Một response không có `frame-ancestors` có thể vẫn bị nhúng bởi website khác nếu không có XFO/chính sách embedding khác.

Muốn cấm nhúng phải viết rõ:

~~~http
Content-Security-Policy: default-src 'self'; frame-ancestors 'none'
~~~

Tương tự `script-src 'none'`, `object-src 'none'`, `base-uri 'none'` không thay cho `frame-ancestors`, dù chúng đều là những phần của một CSP tổng thể.

### 3.3. frame-ancestors khác frame-src và child-src

Hai chiều kiểm soát:

~~~text
Document A (parent)
  |
  +-- <iframe src="https://B.example.test/page">

Response của A:
  frame-src https://B.example.test
  -> A có được tải B như child frame không?

Response của B:
  frame-ancestors https://A.example.test
  -> B có cho A nhúng mình không?
~~~

| Directive | Được đặt ở đâu? | Câu hỏi trả lời |
|---|---|---|
| `frame-src` | Response của **trang mẹ** | Trang mẹ được tải iframe từ nguồn nào? |
| `child-src` | Response của **trang mẹ** (fallback theo CSP) | Nguồn child browsing contexts/workers theo quy tắc CSP liên quan. |
| `frame-ancestors` | Response của **trang con** sẽ bị nhúng | Những ancestor nào được phép nhúng trang con? |

Đặt `frame-src 'self'` trên trang con **không chặn** website khác nhúng trang con. Nếu trang mẹ và con cùng có policy, **cả hai phía** phải cho phép để iframe render.

### 3.4. Nested iframe: kiểm tra mọi ancestor

Giả sử:

~~~text
Top-level: https://partner.example.test
  |
  +-- iframe: https://shell.example.test
          |
          +-- iframe: https://app.example.test/embed/card
~~~

Trang `app.example.test/embed/card` có:

~~~http
Content-Security-Policy: frame-ancestors https://partner.example.test
~~~

**Chưa đủ** nếu `shell.example.test` cũng là ancestor và không có trong allowlist. `frame-ancestors` kiểm tra **tất cả ancestor frames**; nếu bất kỳ ancestor nào không match, browser hủy việc render trang con.

Nếu chuỗi lồng nhau là nhu cầu thật, liệt kê rõ các origins có quyền:

~~~http
Content-Security-Policy: frame-ancestors https://partner.example.test https://shell.example.test
~~~

Đây vẫn không đảm bảo frame render nếu trang mẹ có `frame-src` chặn, browser chặn mixed content hay cookie/session không khả dụng. Review **toàn bộ chuỗi ancestor** chứ không chỉ top-level.

### 3.5. frame-ancestors không dùng được trong meta

Sai:

~~~html
<meta http-equiv="Content-Security-Policy"
      content="frame-ancestors 'none'">
~~~

Directive `frame-ancestors` **không được hỗ trợ** qua CSP meta; browser cần chính sách này sớm khi quyết định liệu có tạo/render frame. Hãy phát qua **HTTP response header** của tài liệu cần bảo vệ.

Tương tự XFO, không thể đặt header trong nội dung HTML sau khi frame đã được chọn để kỳ vọng nó chặn rendering.

### 3.6. CSP enforcement và Report-Only

CSP có hai header:

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

và:

~~~http
Content-Security-Policy-Report-Only: script-src 'self'; report-uri /csp-report
~~~

- `Content-Security-Policy` là chính sách **enforced**.
- `Content-Security-Policy-Report-Only` hỗ trợ **thu thập báo cáo** cho những policy tương thích, **không chặn** các vi phạm thay cho enforced policy.

Riêng `frame-ancestors` là navigation control và có những hạn chế đối với report-only ở browser/spec; **không trông chờ report-only frame-ancestors sẽ ngăn clickjacking**. Để có bảo vệ phải bật header enforcing, sau đó test bằng trình duyệt thật. Nếu thử nghiệm CSP script/style chính sách mới ở Report-Only, không được vô tình chuyển **điều kiện chống iframe** sang chỉ Report-Only.

## 4. Khi cả X-Frame-Options và frame-ancestors cùng tồn tại

Spring Security WebFlux **mặc định gửi `X-Frame-Options: DENY`**. Framework **không tự thêm CSP**, vì CSP phải dựa vào nhu cầu từng ứng dụng. Khi bạn tự cấu hình `frame-ancestors`, response có thể có **cả hai**:

~~~http
X-Frame-Options: DENY
Content-Security-Policy: frame-ancestors 'self' https://portal.example.test
~~~

Theo chuẩn CSP và behavior **trình duyệt hiện đại** hỗ trợ `frame-ancestors` enforcing, directive CSP này **được ưu tiên**, XFO sẽ bị bỏ qua cho quyết định frame của response đó. Do vậy portal được liệt kê có thể nhúng được ở browser hiện đại **dù XFO vẫn là DENY**.

Nhưng **trình duyệt cũ** không hiểu `frame-ancestors` có thể chỉ dùng XFO, dẫn tới **cấm nhúng**. Đây là cơ chế *fail closed*: partner có thể không dùng widget trên browser cũ, nhưng không mở website cho toàn bộ origin.

### 4.1. Các phối hợp thường gặp

| X-Frame-Options | CSP frame-ancestors (enforcing) | Trình duyệt hiện đại | Browser cũ chỉ hiểu XFO |
|---|---|---|---|
| `DENY` | Không có | Chặn mọi frame | Chặn mọi frame |
| `SAMEORIGIN` | Không có | Chỉ same-origin | Chỉ same-origin theo implementation |
| `DENY` | `'none'` | Chặn mọi frame | Chặn mọi frame |
| `DENY` | `'self'` | Cho same-origin | Chặn mọi frame |
| `DENY` | `'self' https://portal.example.test` | Cho các ancestor được liệt kê | Chặn mọi frame |
| Không có XFO | `'self' https://portal.example.test` | Cho các ancestor được liệt kê | Có thể **không có bảo vệ** |
| `ALLOW-FROM https://...` | Không có | Không đáng tin cậy | Khác nhau giữa browser |

**Khuyến nghị theo rủi ro:** Với trang bảo mật quan trọng, dùng `DENY` và `frame-ancestors 'none'`. Với widget thật sự cần nhúng bên ngoài, cân nhắc CSP allowlist **cụ thể và hạn chế quyền**, giữ XFO như fallback chặn browser cũ hoặc cung cấp một giải pháp thay thế nếu legacy compatibility bắt buộc.

### 4.2. Có nên tắt XFO khi dùng CSP?

Không có quy tắc “thêm CSP là phải tắt XFO”. Việc tắt XFO:

~~~java
// Chỉ là mảnh cấu hình của một chain cần xem xét kỹ:
http.headers(headers -> headers
    .frameOptions(frame -> frame.disable())
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "frame-ancestors 'self' https://portal.example.test")));
~~~

có thể khiến browser cũ không hỗ trợ CSP **không có lớp bảo vệ framing nào**. Chỉ chọn nếu đã đánh giá browser support, scope endpoint, dữ liệu trong frame và business requirement. Không tắt `headers(...)` toàn bộ chỉ để một iframe partner chạy.

### 4.3. Nhiều Content-Security-Policy headers

Nếu CDN/gateway và Spring Security đều gửi `Content-Security-Policy`, trình duyệt hiện đại thường **enforce nhiều policy đồng thời**; policy được kết hợp theo hướng **không mở rộng hơn**. Ví dụ:

~~~http
Content-Security-Policy: frame-ancestors 'none'
Content-Security-Policy: frame-ancestors https://portal.example.test
~~~

Không thể hiểu header thứ hai “ghi đè” header đầu để cho portal; policy đầu vẫn chặn. Cần phối hợp một nguồn cấu hình/chiến lược rõ ràng ở gateway và ứng dụng, tránh các response CSP trùng nhau mâu thuẫn. Tương tự, nhiều XFO headers không nhất quán có thể gây kết quả không đoán được theo browser.

### 4.4. Không dựa vào response của parent để che rủi ro

Một parent đặt `frame-src 'self'` không ngăn attacker ở origin khác nhúng trang con của bạn. Muốn chống clickjacking phải đặt **frame-ancestors trên response của trang con**. Nếu chỉ quản lý trang mẹ, bạn không thể đảm bảo một trang con bên ngoài sẽ chống nhúng đúng cách.

## 5. Spring Security reactive: cấu hình headers nào?

Trong Spring Security WebFlux, cấu hình liên quan nằm ở:

~~~java
ServerHttpSecurity http = ...; // builder được Spring cung cấp
http.headers(headers -> headers
    .frameOptions(frameOptions -> frameOptions
        .mode(XFrameOptionsServerHttpHeadersWriter.Mode.SAMEORIGIN))
    .contentSecurityPolicy(csp -> csp
        .policyDirectives("frame-ancestors 'self'")));
~~~

Đây là **mảnh code minh họa DSL**. Import enum:

~~~java
import org.springframework.security.web.server.header
    .XFrameOptionsServerHttpHeadersWriter;
~~~

Ở Java, câu `import` phải là **một dòng liên tục** khi chép vào file:

~~~java
import org.springframework.security.web.server.header.XFrameOptionsServerHttpHeadersWriter;
~~~

### 5.1. Giữ mặc định DENY khi không có yêu cầu nhúng

Spring Security WebFlux mặc định phát XFO `DENY`. Nếu ứng dụng không cần iframe, nhiều khi **không cần chỉnh XFO**; có thể bổ sung CSP để defense in depth:

~~~java
.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives("default-src 'self'; frame-ancestors 'none'")))
~~~

Ở đây `default-src 'self'` là policy tối giản về tài nguyên con; `frame-ancestors 'none'` mới là phần chống embedding. Trong ứng dụng thực tế, cần thiết kế **toàn bộ CSP** cho script, style, image, connect, font v.v. Không copy `default-src 'self'` rồi nghĩ mọi ứng dụng SPA sẽ hoạt động mà không có ngoại lệ.

### 5.2. Khi cần iframe **cùng origin**

Có thể đặt:

~~~java
.headers(headers -> headers
    .frameOptions(frame ->
        frame.mode(XFrameOptionsServerHttpHeadersWriter.Mode.SAMEORIGIN))
    .contentSecurityPolicy(csp -> csp
        .policyDirectives("frame-ancestors 'self'")))
~~~

Trong WebFlux, method là `mode(...)`; không dùng `sameOrigin()` của cấu hình Servlet. Phải test cả trang mẹ lẫn trang con: nếu trang mẹ có `frame-src 'none'` thì vẫn không nhúng được dù response con cho phép.

### 5.3. Khi một trang riêng cần nhúng từ partner

Thay vì nới toàn website, tạo policy riêng cho `/embed/**`:

~~~java
.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; " +
            "frame-ancestors 'self' https://portal.example.test")))
~~~

Đây là mảnh code, không phải toàn bộ security chain. XFO `DENY` mặc định có thể vẫn được gửi; browser hiện đại tuân theo CSP allowlist, browser cũ thường fail closed. Cần **review trang embed không chứa các hành động nhạy cảm**, ngay cả khi partner là bên tin cậy.

### 5.4. Vì sao nhiều SecurityWebFilterChain hữu ích?

Một bean `SecurityWebFilterChain` được chọn theo matcher trước tiên; nếu không chia chain mà đặt CSP rộng ở mọi route, rất dễ vô tình cho iframe truy cập trang login, admin hoặc payment. Khi muốn **các response headers khác nhau theo path**, nhiều chain với `securityMatcher(...)` và `@Order` là cách dễ đọc.

Cấu trúc:

~~~text
GET /embed/card
    -> chain @Order(1), matcher /embed/**
    -> CSP frame-ancestors 'self' http://localhost:3000
    -> public demo widget

GET /public/page hoặc /api/me
    -> chain @Order(2), catch-all
    -> CSP frame-ancestors 'none'
    -> X-Frame-Options DENY mặc định
~~~

**Cảnh báo:** Mỗi request chỉ dùng chain đầu tiên match. Chain `/embed/**` phải có authorization phù hợp riêng, không được `permitAll()` toàn bộ dữ liệu bí mật chỉ vì muốn cho phép iframe. Trong demo, endpoint `/embed/card` là tài nguyên công khai không có state và không có thao tác nhạy cảm.

## 6. Demo Java 17 chạy được: frame bị chặn và frame được phép từ partner

Ví dụ dùng **Java 17**, **Spring Boot 3.5.16**, Spring WebFlux và Spring Security do Boot quản lý. Spring Boot 3.5.16 là bản cuối được phát hành theo OSS cho dòng 3.5; demo dùng bản ổn định này để sinh viên dựng bài nhất quán. **Ứng dụng production cần theo dòng được hỗ trợ và nhận bản vá bảo mật** (ví dụ Spring Boot 4.x với thay đổi API tương ứng) thay vì giữ mãi phiên bản demo.

Mục tiêu:

- `GET /public/page` trả HTML công khai nhưng **không cho iframe từ đâu cả**.
- `GET /embed/card` trả HTML widget **không chứa thông tin nhạy cảm**, được phép nhúng bởi **chính origin backend** và origin frontend demo `http://localhost:3000`.
- `GET /api/me` yêu cầu login HTTP Basic, trả username (để kiểm chứng security chain vẫn bảo vệ).
- Response có **XFO DENY mặc định trên cả hai chain**; CSP của từng chain khác nhau. Browser hỗ trợ CSP ưu tiên `frame-ancestors`; browser cũ có thể chặn cả widget — đó là fail closed.
- Trang `ui/index.html` chạy trên port 3000 để quan sát iframe nào render. Có thể thử port 3001 để mô phỏng origin không được cho phép.

### 6.1. Cấu trúc project

~~~text
webflux-frame-security-demo/
├── settings.gradle
├── build.gradle
├── src/
│   ├── main/java/example/FrameSecurityDemo.java
│   └── test/java/example/FrameSecurityIntegrationTest.java
└── ui/
    └── index.html
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'webflux-frame-security-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Cần JDK 17+ và Gradle/Wrapper tương thích Spring Boot 3.5. Đừng thêm `spring-boot-starter-web` Servlet vào demo vì bài dùng reactive security. Trong IDE, giữ `package example` đúng đường dẫn.

### 6.2. Ứng dụng WebFlux hoàn chỉnh

Tệp `src/main/java/example/FrameSecurityDemo.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class FrameSecurityDemo {

    public static void main(String[] args) {
        SpringApplication.run(FrameSecurityDemo.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // Local demo only; không dùng password {noop} ở production.
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo-pass")
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(learner);
    }

    // Chỉ /embed/** có policy cho partner iframe.
    @Bean
    @Order(1)
    SecurityWebFilterChain embedChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/embed/**"))
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().permitAll())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; " +
                    "frame-ancestors 'self' http://localhost:3000")))
            .build();
    }

    // Catch-all vẫn yêu cầu login cho URL không public.
    @Bean
    @Order(2)
    SecurityWebFilterChain defaultChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; frame-ancestors 'none'")))
            .build();
    }

    @RestController
    static class Pages {

        @GetMapping(value = "/public/page",
                    produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> blockedPage() {
            return Mono.just(
                "<!doctype html><html lang=\"vi\">" +
                "<head><meta charset=\"UTF-8\">" +
                "<title>Trang không cho nhúng</title></head>" +
                "<body><h1>Không thể nhúng trang này</h1></body>" +
                "</html>");
        }

        @GetMapping(value = "/embed/card",
                    produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> embedCard() {
            return Mono.just(
                "<!doctype html><html lang=\"vi\">" +
                "<head><meta charset=\"UTF-8\">" +
                "<title>Public card</title></head>" +
                "<body><h2>Thẻ demo được phép nhúng</h2>" +
                "<p>Không có hành động nhạy cảm.</p></body></html>");
        }

        @GetMapping("/api/me")
        Mono<Map<String, String>> me(ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "username", principal.getName()));
        }
    }
}
~~~

**Phân tích những dòng quyết định:**

1. `@EnableWebFluxSecurity` và hai bean `SecurityWebFilterChain` cho Spring Security chọn chain theo URL.
2. `@Order(1)` với `PathPatternParserServerWebExchangeMatcher("/embed/**")` là matcher **cụ thể**; nó chỉ áp dụng cho widget. Bean `@Order(2)` không có matcher riêng nên là **catch-all**.
3. `embedChain` dùng `anyExchange().permitAll()` **chỉ vì tất cả nội dung /embed/** của demo được thiết kế công khai và không có side effect**. Nếu /embed/** có dữ liệu người dùng, không copy policy này.
4. `defaultChain` chỉ công khai `/public/**`; `/api/me` bắt buộc authenticated qua HTTP Basic.
5. `.headers(...contentSecurityPolicy(...))` đặt **enforcing CSP**, không dùng `reportOnly()`. Một chain cho `frame-ancestors 'none'`, một chain cho `'self' http://localhost:3000`.
6. Spring Security reactive **vẫn phát XFO DENY mặc định** vì không disable `frameOptions`. Browser hiện đại áp dụng CSP frame-ancestors thay cho XFO; browser cũ chỉ đọc XFO có thể chặn cả widget.
7. `default-src 'self'` bảo vệ một số nguồn subresource của demo; chính `frame-ancestors` mới quyết định trang có thể được nhúng không.
8. Hai trang HTML không dùng inline JS/CSS hoặc tài nguyên từ bên thứ ba nên hoạt động với `default-src 'self'`. Ứng dụng thật phải xây CSP đầy đủ, không dán nguyên mà bỏ qua script/style dependencies.
9. `/api/me` dùng principal Spring Security, không tin header user tự khai. Basic account `learner:demo-pass` chỉ để test local qua HTTP không dùng TLS.
10. Response quan trọng là các **HTTP headers thực sự**; code không tự render một trang “bị chặn” khi embedding thất bại, vì quyết định đó thuộc browser.

### 6.3. Trang thử iframe ở origin http://localhost:3000

Tệp `ui/index.html`:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport"
        content="width=device-width, initial-scale=1">
  <title>Thử frame-ancestors</title>
</head>
<body>
  <h1>Kiểm tra chống clickjacking</h1>
  <p>Parent: xem origin hiện tại trên thanh địa chỉ.</p>

  <h2>Widget được cho phép từ localhost:3000</h2>
  <iframe
    title="Widget được phép"
    src="http://localhost:8080/embed/card"
    width="520" height="140"></iframe>

  <h2>Trang không được nhúng từ bất kỳ origin nào</h2>
  <iframe
    title="Trang bị chặn"
    src="http://localhost:8080/public/page"
    width="520" height="140"></iframe>

  <p>Kiểm tra DevTools Console/Network để thấy
     lỗi frame-ancestors trên trang bị chặn.
     Iframe lỗi có thể hiển thị trống hoặc thông báo browser.</p>
</body>
</html>
~~~

Trang parent **không có CSP frame-src riêng** để demo tập trung kiểm tra policy do backend ở port 8080 phát. Trong ứng dụng production, parent nên có CSP `frame-src` hạn chế các child frame mong muốn.

### 6.4. Chạy ứng dụng

Terminal 1, trong thư mục project:

~~~bash
gradle bootRun
~~~

Nếu có Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows.

Terminal 2, trong thư mục `ui/`, với Python 3:

~~~bash
python -m http.server 3000
~~~

Mở:

~~~text
http://localhost:3000/
~~~

**Kỳ vọng trên browser hiện đại:**

- Frame thứ nhất tải `/embed/card` và hiển thị “Thẻ demo được phép nhúng”.
- Frame thứ hai tải `/public/page` nhưng **không render tài liệu** do CSP `frame-ancestors 'none'` (và XFO DENY mặc định).
- Browser Console có thể ghi thông báo từ chối frame theo CSP/XFO; wording khác nhau giữa các browser.
- Không kỳ vọng Chrome/Firefox/Safari cùng một trang error UI, vì điều quan trọng là **không render trang được bảo vệ**.

Để thử origin **không được phép**, dừng Python server ở terminal UI, sau đó chạy:

~~~bash
python -m http.server 3001
~~~

Mở `http://localhost:3001/`: lúc này parent origin là **localhost:3001**, không nằm trong `frame-ancestors 'self' http://localhost:3000` của `/embed/card`. Kỳ vọng **cả hai iframe đều bị chặn** ở browser hỗ trợ CSP. Không cần sửa backend để chạy phép thử này; origin khác do **port khác**.

### 6.5. Kiểm tra headers bằng curl

Khi backend chạy ở `localhost:8080`:

~~~bash
# Trang mặc định không cho nhúng.
curl -i http://localhost:8080/public/page

# Widget có ngoại lệ cho origin localhost:3000.
curl -i http://localhost:8080/embed/card

# API vẫn yêu cầu authentication, không bị permitAll của embedChain.
curl -i http://localhost:8080/api/me

# Basic credential đúng cho /api/me.
curl -i -u learner:demo-pass http://localhost:8080/api/me
~~~

Dùng `curl.exe` trên Windows PowerShell nếu `curl` là alias khác. Tham số `-u` chỉ chứa account demo; đừng đặt password thật trong command-line/shell history hoặc gửi Basic qua HTTP mạng thật.

**Trích đoạn header mong đợi từ `/public/page`:**

~~~http
HTTP/1.1 200 OK
Content-Type: text/html
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'; frame-ancestors 'none'
~~~

**Trích đoạn header mong đợi từ `/embed/card`:**

~~~http
HTTP/1.1 200 OK
Content-Type: text/html
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'; frame-ancestors 'self' http://localhost:3000
~~~

Hai đoạn trên là các dòng liên quan, không phải toàn bộ HTTP response. `Content-Type` có thể kèm charset, HTTP protocol version/Date/Cache-Control/hệ thống header khác thay đổi theo runtime. XFO `DENY` của widget **không mâu thuẫn với ý đồ CSP** trên browser hiện đại: CSP enforced được ưu tiên; trên browser cũ, widget có thể không render.

**Không thể kết luận browser đã chặn clickjacking chỉ từ curl.** Curl không render iframe hoặc áp dụng CSP/XFO; nó chỉ xác nhận backend xuất header.

## 7. Kiểm thử Spring WebFlux với WebTestClient

Tệp `src/test/java/example/FrameSecurityIntegrationTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FrameSecurityIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicPageBlocksAllEmbedding() {
        client.get().uri("/public/page")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.TEXT_HTML)
            .expectHeader().valueEquals(
                "X-Frame-Options", "DENY")
            .expectHeader().valueContains(
                "Content-Security-Policy",
                "frame-ancestors 'none'");
    }

    @Test
    void embedCardAllowsOnlyNamedAncestorsInCsp() {
        client.get().uri("/embed/card")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.TEXT_HTML)
            .expectHeader().valueEquals(
                "X-Frame-Options", "DENY")
            .expectHeader().valueContains(
                "Content-Security-Policy",
                "frame-ancestors 'self' http://localhost:3000");
    }

    @Test
    void privateApiStillChallengesAnonymous() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(
                HttpHeaders.WWW_AUTHENTICATE)
            .expectHeader().valueContains(
                "Content-Security-Policy",
                "frame-ancestors 'none'");
    }

    @Test
    void authenticatedApiIsStillFrameProtected() {
        client.get().uri("/api/me")
            .headers(headers ->
                headers.setBasicAuth("learner", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "X-Frame-Options", "DENY")
            .expectHeader().valueContains(
                "Content-Security-Policy",
                "frame-ancestors 'none'")
            .expectBody()
            .jsonPath("$.username").isEqualTo("learner");
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Nếu dự án có wrapper, dùng `./gradlew test` hoặc `gradlew.bat test`. Với cấu hình đã đưa, bốn test **kỳ vọng pass**. Đây là integration tests xác nhận **response headers và HTTP authorization**, không phải browser rendering tests; kết quả iframe thực sự phải kiểm chứng bằng phần 6.4 trên những browser người dùng hỗ trợ.

### 7.1. Vì sao test XFO ở trang được phép nhúng?

Nó giúp phát hiện một hành vi dễ gây hiểu nhầm: mặc dù CSP của `/embed/card` cho phép `http://localhost:3000`, Spring Security vẫn phát XFO DENY do mặc định. Test khẳng định đây là chính sách **fail closed cho legacy browser** có chủ đích, không phải do quên xử lý XFO. Nếu requirement bắt buộc support browser cũ, phải viết acceptance tests/bảng compatibility và thiết kế một giải pháp khác, không tùy tiện bỏ header.

### 7.2. Những test tiếp theo cần có trong dự án thật

- Browser automation với parent origin **được phép** và **không được phép** để xác minh frame rendering.
- Test `SAMEORIGIN` khi route có iframe nội bộ.
- Test `frame-src` của parent nếu app có CSP chặn child frames.
- Test nested iframe: một ancestor trung gian không nằm trong allowlist phải gây chặn.
- Test response của login, admin, thanh toán, error page, static HTML, redirect cuối cùng và trang do gateway phục vụ.
- Test nhiều CSP headers do reverse proxy/CDN có thể gửi; không để `frame-ancestors 'none'` thứ hai vô tình chặn widget.
- Test browser với third-party cookies bị chặn: iframe có thể render nhưng hiện logged-out UI.
- Test chính sách khi upgrade Spring Security/Boot hoặc thêm `SecurityWebFilterChain` mới.

## 8. HTTPS, HSTS, cookie và clickjacking

### 8.1. frame-ancestors có ràng buộc scheme

`https://portal.example.test` **khác** `http://portal.example.test` về origin. Một allowlist CSP cho HTTPS portal không tự cho bản HTTP không mã hóa nhúng page. Trong production, dùng HTTPS để bảo vệ cả parent và embedded page, tránh mixed-content blocking và rò rỉ cookie.

Nếu parent là HTTPS còn iframe URL là HTTP, browser có thể chặn iframe do **mixed content** dù frame-ancestors đã cho phép. Đây là lỗi khác với “Refused to frame because it violates frame-ancestors”. Đừng sửa bằng cách mở rộng policy sang HTTP; sửa URL/TLS.

### 8.2. HSTS có vai trò khác

HSTS `Strict-Transport-Security` giúp browser nhớ dùng HTTPS cho domain đã công bố, còn XFO/CSP quy định embedding. Spring Security có cấu hình HSTS mặc định cho HTTPS response. Không coi việc có `Strict-Transport-Security` là đã chống clickjacking, cũng không coi `frame-ancestors` là đã bảo đảm mã hóa giao thông.

Trong demo HTTP local, không nhất thiết thấy HSTS như trên HTTPS production. Muốn kiểm thử HSTS, chạy HTTPS đúng và quan sát header ở HTTPS response.

### 8.3. Iframe được phép render chưa chắc có session

Nếu `https://partner.example.test` nhúng `https://app.example.test/embed/card`, browser có thể xem cookie của app là **third-party/cross-site**. `SameSite=Lax` hoặc `Strict` thường không gửi cookie cho cross-site iframe. Cookie `SameSite=None; Secure` có thể cần cho một thiết kế nhúng có đăng nhập, nhưng nhiều trình duyệt cũng giới hạn third-party cookies. Chính sách browser có thể thay đổi; không sửa bằng cách làm session cookie thiếu Secure/HttpOnly.

**Về bảo mật:** Một iframe được phép trong CSP vẫn cần Authentication và Authorization đúng. Đừng chuyển màn hình giao dịch thành public chỉ vì partner cần nhúng. Hãy cân nhắc widget read-only, token có scope tối thiểu, UI confirmation ngoài iframe hoặc kiến trúc redirect thay cho việc nhúng thao tác nhạy cảm.

### 8.4. CORS không kiểm soát quyền nhúng iframe

CORS `Access-Control-Allow-Origin` quyết định JavaScript từ origin khác được **đọc response qua Fetch/XHR** trong những trường hợp phù hợp. Iframe navigation/embedding là cơ chế khác. Không thể “fix iframe bị CSP chặn” bằng cách chỉ thêm:

~~~http
Access-Control-Allow-Origin: https://partner.example.test
~~~

Tương tự, `frame-ancestors` cho partner nhúng **không cấp** cho JavaScript partner quyền đọc DOM iframe do SOP. Nếu hai bên cần trao đổi thông điệp, có thể thiết kế `window.postMessage` với kiểm tra `event.origin` và `targetOrigin` chính xác; không gửi secret cho origin bất kỳ.

## 9. Các sai lầm thực tế dễ xảy ra

**Lỗi 1 — Tin rằng chỉ cần CORS đã chống clickjacking.**

CORS không quyết định website khác có thể nhúng trang HTML của bạn hay không. Cần XFO hoặc CSP frame-ancestors trên response của trang bị nhúng.

**Lỗi 2 — Ghi `frame-src 'none'` để cấm website khác nhúng mình.**

`frame-src` là policy của **parent**, không phải danh sách parent được phép. Dùng `frame-ancestors 'none'`.

**Lỗi 3 — Chỉ đặt `default-src 'none'`.**

`frame-ancestors` **không có fallback** sang `default-src`. Phải khai báo directive embedding tường minh.

**Lỗi 4 — Đặt XFO hoặc frame-ancestors trong HTML meta.**

`X-Frame-Options` không có hiệu lực từ meta. `frame-ancestors` không được hỗ trợ ở CSP meta. Chỉ dùng HTTP response headers.

**Lỗi 5 — Dùng XFO ALLOW-FROM cho partner.**

Directive lỗi thời, browser hiện đại có thể bỏ qua XFO. Dùng enforcing CSP allowlist, kiểm tra browser support.

**Lỗi 6 — Bỏ tất cả security headers để iframe hoạt động.**

`headers(headers -> headers.disable())` có thể làm mất HSTS, nosniff, cache control, referrer policy và các default headers khác. Thay đổi đúng directive/route cần thiết, không tắt cả bộ bảo vệ.

**Lỗi 7 — Gắn policy nới lỏng vào mọi trang.**

Nếu chỉ một widget cần partner nhúng, đừng cho iframe của partner nhúng login, settings, payment và admin. Dùng chain/matcher hoặc policy per-path rõ ràng.

**Lỗi 8 — Nhầm SAMEORIGIN với cùng domain gốc.**

Subdomain, scheme, port khác tạo origin khác. SameSite cookie và same-origin framing không tương đương.

**Lỗi 9 — Quên ancestor trung gian.**

Nested iframes: `frame-ancestors` kiểm tra **mọi ancestor**; chỉ allow top-level parent có thể chưa đủ. Kiểm tra toàn cây frame.

**Lỗi 10 — Dùng `Content-Security-Policy-Report-Only` mà tưởng đã chặn.**

Report-Only không phải policy enforcing. Cần `Content-Security-Policy` được browser thực thi; với frame-ancestors phải test iframe thật.

**Lỗi 11 — Bật CSP nhưng policy thiếu frame-ancestors.**

Spring Security không thêm CSP mặc định; chỉ có `script-src`/`style-src` không có nghĩa đã chặn embedding.

**Lỗi 12 — Tắt XFO khi thêm CSP mà không review browser cũ.**

Modern browser tuân theo CSP; browser cũ có thể không. Tắt XFO làm legacy client thiếu fallback, có thể cho nhúng rộng hơn dự kiến.

**Lỗi 13 — Gửi nhiều CSP headers mâu thuẫn từ app và CDN.**

Các enforcing policies cùng áp dụng theo hướng hạn chế; một `frame-ancestors 'none'` ở proxy có thể khiến allowlist app không bao giờ hoạt động. Phải kiểm tra headers thực trên đường deploy.

**Lỗi 14 — Đặt allowlist quá rộng.**

`frame-ancestors *` hoặc mở mọi subdomain có thể khiến attacker kiểm soát một subdomain làm parent, tăng rủi ro clickjacking. Dùng origin cụ thể, audit ownership.

**Lỗi 15 — Cho iframe hiển thị màn hình giao dịch nhạy cảm.**

Dù partner trusted, ứng dụng vẫn có rủi ro UI redressing từ partner hoặc origin bị compromise. Thiết kế widget read-only, step-up confirmation hoặc redirect sang top-level site cho hành động nguy hiểm.

**Lỗi 16 — Test header bằng curl rồi tuyên bố browser đã an toàn.**

Curl không enforce CSP/XFO. Cần browser smoke test trên origin được phép/bị cấm, kể cả mobile/embedded webview theo sản phẩm.

**Lỗi 17 — Đặt header ở parent thay vì trang con.**

`frame-ancestors` phải nằm trên response của **document sẽ bị nhúng**. Parent cần `frame-src` nếu muốn hạn chế child nó tải.

**Lỗi 18 — Không xét HTTPS/mixed content.**

CSP allowlist HTTPS không cho HTTP; một parent HTTPS có thể bị chặn khi nhúng child HTTP trước cả frame-ancestors. Dùng TLS đúng.

**Lỗi 19 — Nghĩ clickjacking protection thay CSRF/XSS protection.**

XFO/CSP giảm khả năng iframe embedding, không xác minh ý định của mọi POST hoặc chặn script injection. Cần CSRF protection, output encoding, CSP cho scripts và authorization phù hợp.

**Lỗi 20 — Login iframe lỗi liền tắt SameSite/Secure trên cookie.**

Browser có thể hạn chế third-party cookies. Hãy xác định auth model/cookie policy; không bỏ Secure/HttpOnly hoặc mở rộng CORS để chữa nhầm nguyên nhân.

## 10. Checklist trước khi triển khai

1. **Liệt kê trang nhạy cảm:** admin, payment, settings, token/consent và giao dịch; mặc định deny embedding.
2. **Chọn policy:** Không cần iframe → `X-Frame-Options: DENY` + `frame-ancestors 'none'`.
3. **Iframe nội bộ:** Cần cùng origin → cân nhắc `SAMEORIGIN` + `frame-ancestors 'self'`.
4. **Partner embed:** Chỉ route widget cụ thể; `frame-ancestors` với origin partner tin cậy, không dùng XFO ALLOW-FROM.
5. **Tất cả ancestors:** Nếu nested frame, cả middle/top-level origins đều phải được phép.
6. **Response thực:** Header phải xuất hiện trong response của HTML document đích; không dùng meta.
7. **CSP enforcing:** Chống iframe dùng `Content-Security-Policy` thực thi, không chỉ Report-Only.
8. **Default headers:** Không vô hiệu hóa toàn bộ `ServerHttpSecurity.headers(...)` chỉ để sửa một iframe.
9. **Chọn chain:** `@Order`/`securityMatcher` bao phủ đúng route, catch-all bảo vệ những phần còn lại.
10. **AuthZ:** `permitAll` chỉ cho tài nguyên public; widget nhạy cảm vẫn phải kiểm tra quyền thật.
11. **Không chồng policy:** Kiểm tra gateway/CDN/app cùng xuất XFO/CSP gây xung đột.
12. **Browser compatibility:** Có kế hoạch fail closed cho browser cũ không hỗ trợ `frame-ancestors`.
13. **Parent CSP:** Nếu mình sở hữu parent, `frame-src` cũng phải cho child frame hợp lệ.
14. **Cookie:** Iframe cross-site có thể không mang session; giữ Secure/HttpOnly và đánh giá SameSite/third-party policy.
15. **HTTPS:** Parent/child dùng HTTPS ở production; xem HSTS và mixed-content.
16. **CSRF/XSS:** Frame protection không thay thế các lớp đó; không tạo endpoint write bằng GET.
17. **CORS:** Không dựa vào CORS để quyết định quyền iframe hay để sửa frame-ancestors.
18. **Privacy:** Iframe partner không nên lộ thông tin nhạy cảm, credential hoặc UI admin.
19. **Testing:** Test headers với WebTestClient, test render bằng browser ở allowed và untrusted origin.
20. **Regression:** Test trên từng security chain sau khi nâng cấp Spring Security, thay proxy hoặc CSP.
21. **Logging:** CSP violation/logs hữu ích nhưng tránh log cookies, Authorization headers, user data không cần thiết.
22. **Policy review:** Nếu thêm một partner origin, kiểm chứng ownership, HTTPS, phạm vi quyền và cơ chế thu hồi quyền nhúng.

## 11. Câu hỏi tự đánh giá

**1.** Trang có `X-Frame-Options: DENY` có được iframe của chính domain nhúng không?

**Đáp án:** Không. DENY cấm mọi ancestor kể cả same-origin.

**2.** `X-Frame-Options: SAMEORIGIN` có cho `https://admin.example.test` nhúng `https://app.example.test` không?

**Đáp án:** Không; host khác nên origin khác, dù hai subdomain có thể same-site theo cookie.

**3.** XFO `ALLOW-FROM https://partner.example.test` có được khuyến nghị không?

**Đáp án:** Không. Nó là directive lỗi thời và hiện không được browser hiện đại hỗ trợ đáng tin cậy; dùng CSP `frame-ancestors`.

**4.** `Content-Security-Policy: default-src 'none'` có chặn mọi website nhúng trang không?

**Đáp án:** Không tự động. `frame-ancestors` không fallback sang default-src; cần khai báo riêng hoặc dùng XFO.

**5.** `frame-src 'self'` và `frame-ancestors 'self'` khác nhau?

**Đáp án:** frame-src giới hạn nguồn iframe mà document hiện tại được tải; frame-ancestors giới hạn nguồn của các parent được phép nhúng document hiện tại.

**6.** CSP `frame-ancestors 'self' https://partner.example.test` có kiểm tra ancestor ở giữa không?

**Đáp án:** Có. Tất cả ancestors phải match; một ancestor trung gian ngoài allowlist khiến browser hủy rendering.

**7.** Nếu response có XFO DENY và CSP frame-ancestors cho partner, browser hiện đại làm gì?

**Đáp án:** Theo chuẩn, browser hỗ trợ enforced frame-ancestors ưu tiên directive CSP và bỏ qua XFO cho quyết định đó; browser cũ chỉ hiểu XFO có thể chặn partner.

**8.** Chỉ đặt frame-ancestors qua `<meta http-equiv="Content-Security-Policy">` có đủ không?

**Đáp án:** Không. Directive không được hỗ trợ qua meta; dùng HTTP response header.

**9.** Có thể lấy kết quả `curl -i` làm bằng chứng rằng iframe bị chặn không?

**Đáp án:** Không. Curl chỉ đọc HTTP headers, không render iframe. Cần thử trong browser.

**10.** Vì sao CSP frame-ancestors không thay thế CSRF token và authorization?

**Đáp án:** Nó chỉ kiểm soát khả năng nhúng tài liệu, không kiểm tra danh tính, quyền làm nghiệp vụ hay tính chủ động của request thay đổi state.

**11.** Chỉ một route widget cần iframe partner. Có nên thay cả app thành `SAMEORIGIN`/allowlist rộng không?

**Đáp án:** Không. Cấu hình policy theo route/chain; những trang không liên quan vẫn deny.

**12.** Trang được phép nhúng nhưng iframe không có session. Có phải frame-ancestors lỗi?

**Đáp án:** Chưa chắc. Cookie SameSite/Secure/third-party blocking và login flow có thể làm iframe anonymous dù framing đã được cho phép.

## Tài liệu chính thức

- Spring Security 6.5 — Security HTTP Response Headers for WebFlux (X-Frame-Options default/mode, CSP): https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html
- Spring Security — `ServerHttpSecurity.HeaderSpec.FrameOptionsSpec` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HeaderSpec.FrameOptionsSpec.html
- Spring Security — `XFrameOptionsServerHttpHeadersWriter.Mode` (DENY, SAMEORIGIN): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/header/XFrameOptionsServerHttpHeadersWriter.Mode.html
- Spring Security — Configuring Multiple SecurityWebFilterChain: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- MDN — X-Frame-Options (DENY/SAMEORIGIN/ALLOW-FROM): https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Frame-Options
- MDN — CSP frame-ancestors (nested ancestors, meta limitation, no default-src fallback): https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/frame-ancestors
- MDN — CSP Guide, enforcement and Report-Only: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP
- OWASP — Clickjacking Defense Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html
- Spring Boot 3.5.16 release (last OSS 3.5.x): https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
