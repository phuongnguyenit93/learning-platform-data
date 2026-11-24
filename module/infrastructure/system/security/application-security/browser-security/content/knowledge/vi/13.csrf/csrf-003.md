# SameSite defense — giảm CSRF bằng chính sách gửi cookie

> **Chương:** CSRF  
> **Mục tiêu:** Hiểu cách thuộc tính cookie `SameSite` kiểm soát việc browser gửi cookie trong ngữ cảnh same-site/cross-site; phân biệt `Strict`, `Lax` và `None`; nhận diện giới hạn khi các subdomain cùng site nhưng khác origin; kết hợp SameSite với CSRF token, kiểm tra Origin và Fetch Metadata.

## 1. SameSite giải quyết vấn đề gì?

Cookie phiên thường được browser tự động đính kèm vào request phù hợp. Đây là tính năng cần thiết để người dùng đăng nhập một lần rồi tiếp tục sử dụng ứng dụng. Nhưng chính hành vi tự động gửi cookie cũng tạo điều kiện cho **Cross-Site Request Forgery (CSRF)**.

Giả sử người dùng đang đăng nhập tại `https://bank.example`. Họ mở một trang độc hại khác, trang này cố khiến browser gửi request tới ngân hàng:

```html
<form action="https://bank.example/transfer" method="POST">
  <input type="hidden" name="to" value="attacker">
  <input type="hidden" name="amount" value="1000">
</form>
<script>
  document.forms[0].submit();
</script>
```

Nếu cookie phiên được gửi cùng request và server không kiểm tra ý định hợp lệ, ngân hàng có thể xử lý thao tác mà người dùng không chủ động yêu cầu.

Thuộc tính cookie `SameSite` cho phép server yêu cầu browser **hạn chế gửi cookie trong một số ngữ cảnh cross-site**. Nhờ đó, cookie phiên có thể không được gửi khi một website khác tạo request tới ứng dụng.

SameSite là một lớp giảm thiểu CSRF ở phía browser. Nó không xác thực người dùng, không kiểm tra nội dung request và không thay thế CSRF token hoặc authorization ở server.

## 2. Same-site khác same-origin

Để hiểu SameSite, trước hết cần phân biệt **site** và **origin**.

- **Origin** của URL HTTP(S) thông thường gồm scheme, hostname và port.
- **Site** trong mô hình *schemeful same-site* thường gồm scheme và registrable domain (eTLD+1), có xét Public Suffix List.

Ví dụ lấy `https://app.example.com` làm trang đang mở:

| URL đích | Cùng origin? | Cùng site? | Lý do |
| --- | --- | --- | --- |
| `https://app.example.com/profile` | Có | Có | Cùng scheme, host và port |
| `https://api.example.com/data` | Không | Có | Khác host nhưng cùng scheme và registrable domain |
| `https://uploads.example.com/file` | Không | Có | Subdomain khác nhưng cùng site |
| `http://app.example.com/profile` | Không | Không | Scheme khác trong schemeful same-site |
| `https://other.example.net` | Không | Không | Registrable domain khác |
| `https://app.example.com:8443` | Không | Có | Port phân biệt origin, nhưng không phân biệt site |

`SameSite` cookie dựa trên **site**, không dựa trên origin. Vì vậy, request từ `uploads.example.com` tới `app.example.com` có thể được xem là same-site dù hai host khác origin.

Điều này tạo ra một giới hạn bảo mật quan trọng: nếu một subdomain cho phép người dùng đăng nội dung, bị chiếm quyền hoặc có XSS, nó có thể trở thành nguồn request cùng site tới ứng dụng chính. SameSite không tự cô lập các subdomain thuộc cùng site.

## 3. Ba giá trị Strict, Lax và None

Cookie `SameSite` có ba giá trị chính:

| Giá trị | Hành vi khái quát | Trường hợp thường dùng |
| --- | --- | --- |
| `Strict` | Cookie chỉ được gửi trong ngữ cảnh same-site | Phiên hoặc chức năng nhạy cảm không cần cookie ngay khi người dùng đi từ liên kết ngoài vào |
| `Lax` | Cookie được gửi trong same-site và một số điều hướng top-level cross-site bằng phương thức an toàn | Lựa chọn cân bằng cho cookie phiên đăng nhập thông thường |
| `None` | Cho phép cookie trong ngữ cảnh cross-site nếu các điều kiện khác thỏa | Tích hợp cross-site thật sự cần cookie, ví dụ một số luồng iframe hoặc dịch vụ bên thứ ba |

Ví dụ:

```http
Set-Cookie: session_strict=opaque; Path=/; Secure; HttpOnly; SameSite=Strict
Set-Cookie: session_lax=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
Set-Cookie: widget_session=opaque; Path=/; Secure; HttpOnly; SameSite=None
```

Với `SameSite=None`, cookie cần `Secure` trong các browser hiện đại. Browser còn có thể chặn hoặc phân vùng cookie bên thứ ba theo chính sách riêng tư, nên `None` không bảo đảm cookie luôn được gửi.

Nếu không khai báo `SameSite`, nhiều browser hiện đại áp dụng mặc định tương đương Lax. Một số browser từng có cơ chế tương thích tạm thời cho cookie mới không khai báo SameSite trong một số POST top-level; không dựa vào hành vi tương thích này. Hãy khai báo rõ giá trị mong muốn và kiểm tra browser mục tiêu.

## 4. Strict: giới hạn cookie trong điều hướng cùng site

`SameSite=Strict` là lựa chọn nghiêm ngặt nhất trong ba giá trị. Khi người dùng đang ở một site khác và nhấn liên kết tới ứng dụng, browser thường không gửi cookie Strict trong request điều hướng cross-site đầu tiên.

Ví dụ:

```text
Người dùng đang ở https://mail.example.net
    |
    | Click liên kết tới https://bank.example
    v
Browser điều hướng cross-site
    |
    | Cookie SameSite=Strict không được gửi trong request này
    v
Trang ngân hàng được tải
```

Sau khi người dùng đã ở site ngân hàng, những request same-site tiếp theo có thể mang cookie Strict theo phạm vi cookie.

**Ưu điểm:** giảm các request cross-site mang cookie phiên.

**Đánh đổi:** một số luồng đi từ email, trang tìm kiếm, liên kết bên ngoài hoặc nhà cung cấp đăng nhập có thể không có phiên ngay trong lần điều hướng đầu. Ứng dụng cần thiết kế lại trải nghiệm hoặc dùng một luồng callback/nonce an toàn thay vì nới cookie một cách tùy tiện.

Strict không bảo vệ khỏi request cùng site do subdomain kém tin cậy tạo ra. Nó cũng không ngăn mã XSS chạy trong chính origin ứng dụng.

## 5. Lax: cho phép điều hướng top-level an toàn

`SameSite=Lax` thường được chọn cho cookie phiên đăng nhập vì nó hạn chế cookie trong phần lớn ngữ cảnh cross-site, đồng thời cho phép cookie trong một số điều hướng top-level bằng phương thức an toàn, thường là GET.

Ví dụ:

```text
Trang ngoài → click liên kết GET → https://app.example.com
                         |
                         └─ Cookie Lax có thể được gửi

Trang ngoài → form POST  → https://app.example.com/transfer
                         |
                         └─ Cookie Lax thường không được gửi

Trang ngoài → iframe/fetch/image → https://app.example.com
                         |
                         └─ Cookie Lax thường không được gửi
```

“Top-level navigation” nghĩa là request điều hướng trang chính, không phải request tải tài nguyên phụ như iframe, ảnh hoặc fetch. “Safe method” là phương thức không được thiết kế để thay đổi trạng thái, điển hình là GET.

**Không dùng GET cho thao tác thay đổi trạng thái.** Nếu GET chuyển tiền, xóa tài khoản hoặc đổi email, một điều hướng cross-site có thể kích hoạt hành động dù cookie Lax vẫn được gửi.

Lax là lớp giảm thiểu, không phải bảo đảm mọi request CSRF đều bị chặn. Request cùng site vẫn có thể gửi cookie; server vẫn cần kiểm tra ý định đối với thao tác nhạy cảm.

## 6. None: cho phép cookie trong ngữ cảnh cross-site

`SameSite=None` cho phép browser gửi cookie trong ngữ cảnh cross-site nếu cookie và môi trường đáp ứng các điều kiện khác:

```http
Set-Cookie: embedded_session=opaque; Path=/; Secure; HttpOnly; SameSite=None
```

Một trường hợp sử dụng có thể là widget đăng nhập hoặc dịch vụ được nhúng trong iframe trên nhiều site. Tuy nhiên, cookie bên thứ ba có thể bị browser chặn, phân vùng hoặc yêu cầu cơ chế cấp quyền riêng. Cần kiểm tra chính sách của browser và kiến trúc lưu trữ/đăng nhập hiện tại.

`SameSite=None` làm giảm lớp bảo vệ CSRF do SameSite mang lại. Nếu cookie được gửi cross-site, ứng dụng cần CSRF token, kiểm tra Origin/Referer, Fetch Metadata và authorization ở server phù hợp với mức rủi ro.

Không chọn None chỉ để sửa lỗi “cookie không gửi được” trước khi xác định request là same-site hay cross-site và cookie đang bị chặn vì lý do nào.

## 7. Ma trận hành vi thường gặp

Bảng sau giả định cookie khớp Domain/Path, chưa hết hạn, HTTPS khi cần, browser hỗ trợ SameSite hiện đại và không có chính sách third-party cookie bổ sung chặn cookie:

| Ngữ cảnh request tới site đích | Strict | Lax | None; Secure |
| --- | --- | --- | --- |
| Request cùng site | Gửi | Gửi | Gửi |
| Điều hướng top-level cross-site bằng GET | Không gửi | Gửi | Có thể gửi |
| Điều hướng top-level cross-site bằng POST | Không gửi | Không gửi theo quy tắc Lax thông thường | Có thể gửi |
| Fetch cross-site | Không gửi | Không gửi | Có thể gửi |
| Iframe cross-site | Không gửi | Không gửi | Có thể gửi |
| Ảnh/subresource cross-site | Không gửi | Không gửi | Có thể gửi |

“Có thể gửi” vẫn phụ thuộc cookie policy, credentials mode của Fetch, third-party cookie restrictions, partitioning, quyền và điều kiện browser. Đặc biệt, Fetch mặc định dùng `credentials: "same-origin"`; request cross-origin cần `credentials: "include"` nếu muốn browser-managed credentials được gửi.

## 8. SameSite không thay thế CSRF token

SameSite có thể chặn nhiều request cross-site mang cookie, nhưng có các giới hạn:

1. **Same-site sibling:** subdomain không đáng tin có thể tạo request same-site tới ứng dụng.
2. **Lax top-level navigation:** một số request GET cross-site vẫn mang cookie.
3. **Cookie None:** cho phép cookie cross-site khi các chính sách khác thỏa.
4. **Browser và compatibility behavior:** chính sách có thể khác theo phiên bản hoặc thiết lập.
5. **XSS:** script độc hại chạy cùng origin có thể gửi request với cookie hiện có.
6. **Ứng dụng sai thiết kế:** endpoint GET thay đổi trạng thái vẫn có thể bị kích hoạt bởi điều hướng.

Với thao tác thay đổi trạng thái, server nên yêu cầu **CSRF token** được gắn với session hoặc request hợp lệ. Ví dụ:

```html
<form method="POST" action="/profile/email">
  <input type="hidden" name="csrf_token" value="SERVER_ISSUED_TOKEN">
  <input type="email" name="email" required>
  <button type="submit">Cập nhật email</button>
</form>
```

Server phải xác minh token với session hiện tại trước khi thực hiện thay đổi. Token không được chỉ kiểm tra theo việc trường có tồn tại; cần so sánh giá trị đúng cách và gắn token với đúng phiên hoặc cơ chế đã thiết kế.

Nếu dùng AJAX, token có thể được gửi qua custom request header. CORS preflight có thể khiến request cross-origin bị chặn nếu server không cho phép header đó, nhưng **CORS không phải lớp CSRF duy nhất** vì form HTML và các request đơn giản vẫn có thể gửi.

## 9. SameSite và kiểm tra Origin/Referer

Đối với endpoint thay đổi trạng thái, server có thể kiểm tra header `Origin` và/hoặc `Referer`:

```http
Origin: https://app.example.com
Referer: https://app.example.com/settings
```

Server so sánh origin với allowlist đã cấu hình. Không dùng kiểm tra chuỗi hậu tố lỏng như `endsWith("example.com")` vì có thể chấp nhận `attackerexample.com`.

Một số request không có `Origin` hoặc `Referer` do phương thức, chính sách riêng tư hoặc ngữ cảnh đặc biệt. Cần quy định rõ cách xử lý thiếu header theo loại endpoint; với hành động nhạy cảm, không nên âm thầm bỏ qua mọi kiểm tra khi thiếu.

Kiểm tra Origin là lớp bổ sung. Nó không thay xác thực, phân quyền hoặc CSRF token, và không giúp nếu ứng dụng có XSS cho phép script chạy ngay trong origin hợp lệ.

## 10. Fetch Metadata: nhận diện ngữ cảnh request

Browser hiện đại có thể gửi các header Fetch Metadata như:

```http
Sec-Fetch-Site: cross-site
Sec-Fetch-Mode: navigate
Sec-Fetch-Dest: document
```

`Sec-Fetch-Site` có thể mang các giá trị như:

| Giá trị | Ý nghĩa |
| --- | --- |
| `same-origin` | Cùng origin |
| `same-site` | Cùng site nhưng có thể khác origin |
| `cross-site` | Khác site |
| `none` | Request không có site khởi tạo thông thường, ví dụ một số thao tác người dùng trực tiếp |

Server có thể dùng Fetch Metadata để từ chối những request cross-site không cần thiết tới endpoint nhạy cảm. Ví dụ, một endpoint JSON chỉ dành cho same-origin có thể từ chối `Sec-Fetch-Site: cross-site`, sau khi đánh giá các luồng hợp lệ.

Không chặn mọi request cross-site một cách máy móc. Website có thể cần nhận callback từ nhà cung cấp thanh toán, webhook hoặc điều hướng từ luồng đăng nhập liên kết. Phải phân biệt endpoint browser-facing với endpoint server-to-server; webhook server-to-server thường không mang các header Fetch Metadata.

Fetch Metadata là lớp bổ sung, không thay thế CSRF token. Với browser cũ hoặc client không gửi header, ứng dụng cần fallback được thiết kế rõ ràng.

## 11. Subdomain cùng site nhưng không cùng mức tin cậy

Giả sử doanh nghiệp có:

```text
https://app.example.com       — ứng dụng tài khoản
https://uploads.example.com   — nội dung do người dùng tải lên
https://legacy.example.com    — ứng dụng cũ
```

Ba host có thể cùng site theo schemeful same-site. Nếu `uploads` cho phép người dùng xuất bản HTML hoặc `legacy` có lỗ hổng, request từ các host đó tới `app` vẫn có thể được phân loại same-site và cookie Lax/Strict có thể được gửi theo các điều kiện tương ứng.

Do đó:

- Không dùng SameSite làm ranh giới tin cậy giữa các subdomain.
- Ưu tiên cookie host-only; tránh `Domain=example.com` nếu không cần chia sẻ phiên.
- Tách nội dung người dùng tải lên sang site/registrable domain riêng khi kiến trúc và rủi ro yêu cầu.
- Dùng CSRF token và kiểm tra Origin/Fetch Metadata trên endpoint thay đổi trạng thái.
- Cấu hình CORS theo origin cụ thể, không tin mọi subdomain cùng site.
- Phòng vệ XSS ở từng ứng dụng; XSS trong sibling origin vẫn có thể tạo request cùng site.

Đây là một trong những lý do SameSite nên được xem là **phòng vệ theo ngữ cảnh gửi cookie**, không phải mô hình phân quyền giữa các ứng dụng.

## 12. Luồng đăng nhập liên kết, OAuth và điều hướng ngoài

Cookie Strict có thể không được gửi trong request đầu tiên khi người dùng quay lại từ một site khác. Điều này ảnh hưởng một số luồng:

1. Người dùng rời ứng dụng để đăng nhập tại Identity Provider.
2. Identity Provider chuyển hướng browser trở lại ứng dụng bằng top-level navigation.
3. Ứng dụng cần nhận biết giao dịch đăng nhập đang chờ và hoàn tất callback.

Với OAuth/OIDC, không nên dựa vào việc nới cookie phiên chính sang None để bảo vệ callback. Dùng các biện pháp của giao thức như `state` được ràng buộc với giao dịch, PKCE cho authorization code flow và kiểm tra issuer/redirect URI. Nếu kiến trúc cần cookie tạm cho callback, thiết kế riêng cookie đó với phạm vi và thời hạn tối thiểu, rồi kiểm tra hành vi trên browser mục tiêu.

`SameSite=Lax` thường tương thích hơn với top-level GET callback; callback dùng POST hoặc response mode khác có thể cần thiết kế khác. Đừng thay đổi SameSite trên toàn bộ cookie phiên chỉ để xử lý một endpoint callback mà chưa đánh giá CSRF.

## 13. Cấu hình cookie và ví dụ triển khai

### Cookie phiên thông thường

Một cấu hình khởi đầu thường gặp:

```http
Set-Cookie: __Host-session=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

`__Host-` yêu cầu `Secure`, `Path=/` và không có `Domain` ở browser hỗ trợ. Đây là cách giới hạn cookie vào đúng host, hữu ích khi ứng dụng không cần chia sẻ session giữa subdomain.

### Cookie cross-site thật sự cần thiết

```http
Set-Cookie: embedded-session=opaque-id; Path=/; Secure; HttpOnly; SameSite=None
```

Chỉ sử dụng khi tích hợp cần cookie trong ngữ cảnh cross-site. Browser có thể vẫn chặn third-party cookie hoặc phân vùng dữ liệu; cần kiểm thử trong môi trường người dùng mục tiêu.

### Không đặt cookie SameSite dựa trên input request

Không cho client tự gửi một giá trị tùy ý rồi server dùng trực tiếp làm thuộc tính SameSite. Chọn chính sách từ cấu hình ứng dụng và mục đích cookie. Nếu có nhiều loại cookie, phân tách tên và policy rõ ràng thay vì dùng một cookie domain rộng cho tất cả chức năng.

## 14. Thực hành: kiểm tra SameSite trong DevTools

Thực hành trên hai site thử nghiệm do bạn kiểm soát, ví dụ `https://app.example.test` và `https://attacker.example.net`. Dùng tài khoản và dữ liệu giả lập.

### Bước 1 — Tạo ba cookie

Server thử nghiệm trả:

```http
Set-Cookie: strict_demo=1; Path=/; Secure; HttpOnly; SameSite=Strict
Set-Cookie: lax_demo=1; Path=/; Secure; HttpOnly; SameSite=Lax
Set-Cookie: none_demo=1; Path=/; Secure; HttpOnly; SameSite=None
```

Kiểm tra trong DevTools → Application/Storage → Cookies. Xác nhận browser đã lưu từng cookie; cookie None cần Secure.

### Bước 2 — Gửi request từ site khác

Từ trang thử nghiệm cross-site, tạo:

- Một form POST tới endpoint test.
- Một liên kết top-level GET tới endpoint test.
- Một fetch cross-site có credentials include.
- Một iframe trỏ tới endpoint test.

Trong Network, xem Request Cookies hoặc blocked reason của từng cookie. Kết quả dự kiến theo bảng hành vi ở phần 7; cookie None vẫn có thể bị third-party cookie policy chặn.

### Bước 3 — So sánh same-site sibling

Nếu có thể, tạo hai subdomain thử nghiệm cùng registrable domain, ví dụ `app.example.test` và `uploads.example.test`. Gửi request từ uploads tới app. Quan sát `Sec-Fetch-Site` và cookie:

- Hai origin khác nhau.
- Hai host có thể được browser phân loại same-site.
- Cookie SameSite có thể được gửi nếu Domain/Path phù hợp.

### Bước 4 — Thêm CSRF token

Thêm token hợp lệ vào form/request POST và xác minh server từ chối request thiếu hoặc token sai. Kiểm tra rằng request GET không thay đổi trạng thái.

### Bước 5 — Kiểm tra Origin và Fetch Metadata

Ghi nhận `Origin`, `Referer` và `Sec-Fetch-Site` trên request. Thử policy server chỉ cho phép các ngữ cảnh cần thiết; kiểm tra các luồng đăng nhập/callback hợp lệ để tránh chặn nhầm.

Kết quả và cách browser hiển thị blocked reason có thể khác theo phiên bản và cài đặt riêng tư. Không dùng tài khoản production hoặc cookie thật trong bài thực hành.

## 15. Chẩn đoán lỗi cookie không được gửi

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Cookie không có trong request cross-site POST | SameSite Strict/Lax | Xem cookie attributes và request context trong Network |
| Cookie Lax có trong top-level GET nhưng không có trong iframe | Khác biệt top-level navigation và subresource | Kiểm tra Sec-Fetch-Dest/Mode và loại điều hướng |
| Cookie None không được gửi | Thiếu Secure, third-party cookie bị chặn hoặc partitioning | Xem blocked reason, browser settings và HTTPS |
| Cookie không gửi dù cùng site | Fetch credentials mặc định same-origin khi khác origin; Domain/Path không khớp | Kiểm tra credentials mode và cookie scope |
| Cookie gửi từ subdomain ngoài dự kiến | Cookie Domain quá rộng hoặc host cùng site | Ưu tiên host-only, rà soát subdomain và session boundary |
| Login callback không thấy session | Strict cookie bị bỏ trong điều hướng cross-site đầu tiên hoặc callback method khác | Kiểm tra luồng OAuth/OIDC, SameSite và state/PKCE |
| CSRF vẫn xảy ra dù cookie Lax | Request cùng site, GET đổi trạng thái hoặc lỗi logic server | Kiểm tra CSRF token, method, Origin và Fetch Metadata |

Không giải quyết mọi lỗi bằng cách đặt cookie thành `SameSite=None`. Trước hết hãy xác định request context, mục đích cookie, cookie scope và chính sách browser.

## 16. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “SameSite nghĩa là cùng origin.” | SameSite dựa trên site; subdomain có thể khác origin nhưng cùng site. |
| “Lax chặn mọi request cross-site.” | Một số top-level navigation bằng phương thức an toàn vẫn gửi cookie. |
| “Strict bảo vệ cả request từ subdomain.” | Subdomain cùng site có thể vẫn được phân loại same-site. |
| “None luôn gửi cookie bên thứ ba.” | Third-party cookie policy và partitioning có thể chặn hoặc thay đổi hành vi. |
| “SameSite thay thế CSRF token.” | Nó chỉ giảm một số ngữ cảnh gửi cookie; server vẫn cần CSRF protection. |
| “CORS chặn CSRF.” | CORS chủ yếu giới hạn đọc response; form và request đơn giản vẫn có thể gửi. |
| “HttpOnly ngăn XSS.” | HttpOnly ngăn đọc cookie bằng JS; XSS vẫn có thể gọi API trong phiên hiện tại. |
| “GET có thể thay đổi trạng thái vì Lax không gửi cookie trong POST.” | Lax vẫn có thể gửi cookie trong top-level GET; GET phải an toàn và không đổi trạng thái. |

## 17. Câu hỏi tự kiểm tra

1. Site khác origin ở điểm nào? Vì sao hai subdomain có thể cùng site?
2. Cookie Strict khác Lax trong điều hướng top-level từ site ngoài như thế nào?
3. Vì sao Lax thường cho phép một số GET top-level nhưng không cho POST cross-site?
4. Khi nào cookie None có thể cần thiết và điều kiện Secure là gì?
5. Vì sao SameSite không ngăn request từ sibling subdomain cùng site?
6. Vì sao không dùng GET cho thao tác thay đổi trạng thái?
7. CSRF token bổ sung lớp bảo vệ nào mà SameSite không cung cấp?
8. Fetch Metadata `Sec-Fetch-Site` giúp server nhận diện điều gì?
9. Vì sao OAuth callback cần được thiết kế theo giao thức thay vì nới toàn bộ cookie phiên?
10. Nếu cookie không xuất hiện trong request, cần kiểm tra những thuộc tính và ngữ cảnh nào trước khi đổi sang None?

**Ghi nhớ:** SameSite điều khiển việc browser gửi cookie theo quan hệ site: `Strict` hạn chế nhất, `Lax` cho phép thêm một số top-level navigation an toàn, còn `None` cho phép cross-site khi điều kiện cookie và browser thỏa. Vì site rộng hơn origin, SameSite không cô lập các sibling subdomain và không thay CSRF token. Bảo vệ thao tác nhạy cảm cần kết hợp cookie flags, token gắn với session, kiểm tra Origin/Referer, Fetch Metadata, phương thức HTTP đúng và authorization phía server.
