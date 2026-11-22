# Rủi ro lưu token trong localStorage và sessionStorage

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Lưu trữ và truyền  
> **Phạm vi:** Rủi ro lưu bearer token trong trình duyệt và cách lựa chọn cơ chế lưu trữ; kiến thức bảo mật web/JWT ở mức giao thức, không phụ thuộc Java, Spring hay framework cụ thể.

Một ứng dụng web có thể lưu access token hoặc refresh token trong **localStorage** hay **sessionStorage** để dùng cho các request tiếp theo. Cách này thuận tiện vì JavaScript có thể đọc token, nhưng chính khả năng đọc đó tạo ra rủi ro lớn: bất kỳ mã JavaScript nào chạy được trong cùng origin với ứng dụng đều có thể đọc token và gửi nó ra ngoài.

JWT thường được sử dụng như **bearer token**: bên nắm giữ token có thể thử dùng token tại resource server phù hợp. Nếu token bị đánh cắp, attacker không cần biết mật khẩu người dùng hoặc private signing key của issuer. Họ có thể phát lại token cho đến khi token hết hạn, bị thu hồi hoặc bị chặn bởi một cơ chế ràng buộc người gửi.

Điều cần đánh giá không chỉ là token nằm ở API lưu trữ nào. Cần xem **ai có thể đọc nó, token sống bao lâu, quyền được cấp rộng đến đâu, token được gửi tới đâu và hệ thống xử lý thế nào khi xảy ra XSS hoặc mất thiết bị**.

## 1. localStorage và sessionStorage hoạt động ra sao?

### 1.1. localStorage

**localStorage** là vùng lưu trữ key/value phía trình duyệt, gắn với origin. JavaScript chạy trong origin đó có thể đọc và ghi dữ liệu qua Storage API.

Đặc điểm:

- Dữ liệu thường tồn tại sau khi reload trang, đóng tab và mở lại trình duyệt.
- Các trang cùng origin trong cùng browser profile có thể dùng chung vùng local storage.
- Dữ liệu không tự hết hạn theo thời gian như cookie có thuộc tính expiry; ứng dụng phải tự xóa hoặc thay thế.
- Dữ liệu được lưu ở phía client và có thể được đọc bởi script cùng origin.
- Không có thuộc tính tương đương **HttpOnly** để ngăn JavaScript đọc giá trị.

Ví dụ minh họa:

~~~javascript
localStorage.setItem("access_token", token);
const token = localStorage.getItem("access_token");
localStorage.removeItem("access_token");
~~~

Ví dụ chỉ minh họa API, không phải khuyến nghị lưu bearer token ở localStorage.

### 1.2. sessionStorage

**sessionStorage** cũng là vùng key/value phía trình duyệt, nhưng được phân vùng theo origin và **top-level browsing context** (thường là tab). Dữ liệu thường tồn tại qua reload và điều hướng trong tab, rồi bị xóa khi phiên tab kết thúc.

Đặc điểm:

- Một tab có vùng session storage riêng; tab khác thường không chia sẻ các cập nhật.
- Reload trang không xóa dữ liệu.
- Đóng tab/kết thúc browsing context thường làm dữ liệu mất đi.
- Khi mở một trang mới với **window.opener**, session storage ban đầu có thể được sao chép từ opener; hai vùng sau đó độc lập. Không nên dựa vào giả định “mở tab mới luôn bắt đầu với storage trống”.
- JavaScript cùng origin vẫn đọc được dữ liệu; sessionStorage không có thuộc tính HttpOnly.

Ví dụ minh họa:

~~~javascript
sessionStorage.setItem("access_token", token);
const token = sessionStorage.getItem("access_token");
sessionStorage.removeItem("access_token");
~~~

### 1.3. So sánh nhanh

| Thuộc tính | localStorage | sessionStorage |
|---|---|---|
| Phạm vi | Origin trong browser profile | Origin trong top-level browsing context |
| Chia sẻ giữa các tab | Thường có | Thường không; mỗi tab có vùng riêng |
| Qua reload | Có | Có |
| Qua đóng tab | Có | Thường không |
| Qua đóng/mở browser | Thường có | Không, khi browsing context kết thúc |
| JavaScript cùng origin đọc được? | Có | Có |
| Có HttpOnly? | Không | Không |
| Tự hết hạn theo claim exp của JWT? | Không | Không |
| Ngăn XSS đọc token? | Không | Không |

Khác biệt chính là vòng đời và phạm vi chia sẻ. **sessionStorage không trở thành nơi lưu bí mật an toàn trước XSS** chỉ vì dữ liệu thường mất khi đóng tab.

## 2. Mô hình đe dọa: vì sao JavaScript cùng origin đọc được token?

### 2.1. Same-origin policy không bảo vệ khỏi script đã chạy trong origin

Trình duyệt dùng origin (scheme, host và port) để phân tách nhiều tài nguyên web. Same-origin policy hạn chế một trang ở origin khác đọc dữ liệu của ứng dụng.

Tuy nhiên, nếu mã độc đã chạy bên trong origin của ứng dụng, nó được thực thi trong ngữ cảnh có quyền tương tự các script hợp lệ của ứng dụng. Vì vậy, nó có thể gọi **localStorage.getItem()** hoặc **sessionStorage.getItem()** để lấy token.

Các nguồn có thể đưa mã không mong muốn vào origin:

- Stored XSS: nội dung do người dùng gửi được lưu lại rồi render không an toàn.
- Reflected hoặc DOM-based XSS: dữ liệu đầu vào được đưa vào DOM theo cách cho phép thực thi script.
- Thư viện hoặc dependency phía client bị xâm phạm.
- Script bên thứ ba bị chiếm quyền hoặc thay đổi nội dung.
- Tag manager, widget, analytics hoặc đoạn script nhúng có quyền chạy trong trang.
- Tài khoản triển khai, CDN hoặc pipeline phát hành frontend bị chiếm quyền.

Không cần attacker kiểm soát server API nếu họ đã thực thi JavaScript trong origin có token.

### 2.2. Luồng đánh cắp token

~~~mermaid
flowchart TD
    A[Người dùng đăng nhập] --> B[Ứng dụng nhận bearer token]
    B --> C[Lưu token trong localStorage/sessionStorage]
    D[XSS hoặc script cùng origin bị xâm phạm] --> E[Đọc Storage API]
    C --> E
    E --> F[Gửi token tới hạ tầng attacker]
    F --> G[Attacker phát lại token]
    G --> H[Resource server nhận bearer token]
    H --> I{Token còn hợp lệ và chưa bị chặn?}
    I -->|Có| J[Request có thể được chấp nhận]
    I -->|Không| K[Từ chối]
~~~

Sơ đồ minh họa việc đánh cắp và phát lại. Một token có thể bị sử dụng từ thiết bị khác nếu nó là bearer token và không có sender constraint được kiểm tra.

### 2.3. XSS có thể hành động ngay cả khi không lấy token ra ngoài

Đánh cắp token và lạm dụng phiên là hai rủi ro liên quan nhưng khác nhau:

- Script độc hại có thể đọc token rồi gửi sang máy chủ attacker để dùng về sau.
- Script độc hại cũng có thể gọi API ngay trong trang, dùng token từ bộ nhớ hoặc để trình duyệt tự gửi request.
- Vì vậy, ngăn exfiltration token không tự động ngăn attacker thực hiện hành động khi XSS còn chạy.

Một biện pháp chỉ làm token khó đọc hơn nhưng không ngăn script thực thi có thể giảm một dạng đánh cắp, nhưng không loại bỏ hoàn toàn tác động của XSS.

## 3. Rủi ro cụ thể khi lưu JWT trong localStorage

### 3.1. Token tồn tại lâu và dễ bị bỏ quên

localStorage tồn tại qua nhiều lần mở trang và thường qua cả lần khởi động lại trình duyệt. Nếu ứng dụng không xóa token đúng lúc, token có thể còn lại sau khi:

- Người dùng nghĩ rằng đã đăng xuất nhưng logic logout chỉ chuyển trang.
- Một tài khoản khác đăng nhập trên cùng browser profile.
- Máy tính được dùng chung hoặc cho mượn.
- Một thiết bị bị mất, bán lại hoặc không còn được quản lý.
- Một ứng dụng đổi domain nhưng vẫn còn dữ liệu ở origin cũ.

Nếu refresh token hoặc access token dài hạn nằm ở localStorage, khoảng thời gian attacker có thể khai thác sau khi đánh cắp thường lớn hơn.

### 3.2. Mọi script cùng origin có thể truy cập

localStorage không phân biệt script của ứng dụng với script bên thứ ba đã được phép chạy trong trang. Một analytics script hoặc dependency bị xâm phạm có thể có quyền đọc cùng vùng storage.

Việc chỉ tải script từ CDN hoặc nhà cung cấp nổi tiếng không đảm bảo script luôn an toàn. Hợp đồng với nhà cung cấp, pin version, Subresource Integrity khi phù hợp, kiểm soát dependency và hạn chế script đều quan trọng.

### 3.3. Dễ tạo nhiều bản sao token

Ứng dụng có thể vô tình sao chép token sang:

- Log debug hoặc telemetry.
- State persistence hoặc cache của frontend.
- Công cụ theo dõi lỗi có thu thập object/request.
- Dữ liệu export/import hoặc backup trình duyệt.
- URL, query string hoặc fragment khi xử lý callback.
- Clipboard hoặc thông báo debug.

Khi token đã bị sao chép sang nhiều nơi, xóa một key trong localStorage không thu hồi được các bản sao đó.

### 3.4. localStorage không tự đồng bộ với thời hạn JWT

Claim **exp** chỉ được resource server hoặc client có logic kiểm tra diễn giải theo chính sách. Trình duyệt không tự xóa một key localStorage khi exp đến. Ứng dụng phải quản lý trạng thái token và xóa dữ liệu khi logout, hết hạn hoặc đổi tài khoản.

Không dựa vào việc xóa token phía client như cơ chế thu hồi duy nhất. Attacker có thể đã sao chép token; resource server vẫn cần xác minh thời hạn và trạng thái theo hợp đồng.

## 4. Rủi ro cụ thể khi lưu JWT trong sessionStorage

### 4.1. Vòng đời ngắn hơn không có nghĩa chống XSS

sessionStorage thường kết thúc khi tab đóng, nên có thể giảm thời gian tồn tại của token trên thiết bị so với localStorage. Nhưng trong lúc tab còn mở, script cùng origin vẫn đọc được token.

Nếu XSS xảy ra khi người dùng đang đăng nhập, attacker có thể:

- Đọc và exfiltrate token.
- Gọi API ngay trong phiên.
- Thay đổi giao diện để lừa người dùng thực hiện thao tác.
- Đánh cắp dữ liệu hiển thị trong trang.

Đóng tab sau đó không xóa bản token mà attacker đã lấy đi.

### 4.2. sessionStorage vẫn tồn tại qua reload

Một số nhóm cho rằng sessionStorage chỉ tồn tại trong bộ nhớ tạm và mất khi refresh. Điều này không chính xác: reload trang không kết thúc tab session. Token vẫn có thể được đọc lại sau khi trang tải lại.

### 4.3. Tab mới và opener

Khi mở một browsing context mới có opener, session storage ban đầu có thể được khởi tạo bằng bản sao từ opener. Sau đó hai vùng tách biệt, nhưng token đã có thể xuất hiện trong tab mới.

Nếu ứng dụng mở cửa sổ/tab ngoài, nên xem xét **noopener** để tránh quan hệ opener không cần thiết. Đây là biện pháp giảm một số rủi ro liên quan cửa sổ, không phải biện pháp bảo vệ token trước XSS cùng origin.

### 4.4. Không dùng sessionStorage như “phiên đăng nhập an toàn”

sessionStorage không:

- Ngăn script cùng origin đọc token.
- Ngăn malware hoặc extension có quyền truy cập trình duyệt.
- Thu hồi token đã bị sao chép.
- Thay thế kiểm tra exp, issuer, audience hoặc scope.
- Bảo vệ refresh token khỏi replay nếu attacker đã lấy được token.

Nó chỉ thay đổi phạm vi chia sẻ và vòng đời lưu trữ phía trình duyệt.

## 5. Hậu quả khi bearer token bị đánh cắp

### 5.1. Replay token

Attacker có thể gửi lại token trong header Authorization tới resource server phù hợp. Nếu token còn hạn và server không có cơ chế thu hồi/ràng buộc sender, request có thể được chấp nhận.

Rủi ro phụ thuộc:

- Token là access token hay refresh token.
- Audience và scope được cấp.
- Lifetime và freshness.
- Có sender constraint như mTLS hoặc DPoP không.
- Resource server kiểm tra revocation/introspection hay chỉ xác minh offline.
- Hành động có cần xác nhận bổ sung hoặc chống replay theo giao dịch không.

### 5.2. Phạm vi tác động theo loại token

| Token bị lộ | Tác động tiềm tàng |
|---|---|
| Access token ngắn hạn | Gọi API trong scope/audience và thời gian còn hiệu lực |
| Access token quyền rộng hoặc lifetime dài | Tác động lớn hơn, nhiều tài nguyên hoặc thời gian khai thác dài |
| Refresh token | Có thể xin access token mới; phạm vi phụ thuộc grant, rotation và reuse detection |
| ID token | Lộ thông tin định danh/xác thực; không mặc nhiên cấp quyền gọi resource API |
| Password reset token | Có thể hoàn tất yêu cầu khôi phục nếu còn hiệu lực và chưa dùng |
| Email verification token | Có thể xác minh địa chỉ nếu token còn hợp lệ và đúng yêu cầu |

Không coi tất cả JWT là access token. Phải đánh giá theo đúng profile và mục đích.

### 5.3. Xóa token khỏi storage không thu hồi token đã bị đánh cắp

Logout phía client có thể xóa token trong browser, nhưng attacker có thể đã sao chép token ra ngoài. Cần cơ chế phía server phù hợp với rủi ro:

- Access token có lifetime ngắn.
- Thu hồi token/grant/session hoặc introspection.
- Denylist theo jti khi phù hợp.
- Refresh token rotation và reuse detection.
- Sender-constrained token nếu có thể triển khai.
- Yêu cầu xác thực lại hoặc xác nhận bổ sung cho hành động nhạy cảm.

## 6. So sánh với các lựa chọn lưu trữ khác

Không có một lựa chọn lưu trữ hoàn hảo cho mọi kiến trúc. Hãy so sánh dựa trên khả năng đọc từ JavaScript, CSRF, XSS, vòng đời và nơi token được giữ.

| Cơ chế | JavaScript đọc token? | Tự động gửi theo request? | Rủi ro chính |
|---|---|---|---|
| localStorage | Có | Không; ứng dụng thường gắn vào Authorization header | XSS có thể đọc và exfiltrate; tồn tại lâu |
| sessionStorage | Có | Không; ứng dụng thường gắn vào Authorization header | XSS có thể đọc và exfiltrate trong tab |
| In-memory JavaScript | Có, nếu script truy cập được biến/runtime | Không tự động | XSS vẫn có thể đọc hoặc sử dụng token trong phiên; mất khi context kết thúc |
| Cookie không HttpOnly | Có | Trình duyệt tự gửi theo cookie rules | XSS có thể đọc cookie; còn có CSRF |
| Cookie HttpOnly, Secure | JavaScript không đọc được qua API thông thường | Có, theo domain/path/SameSite/secure rules | Giảm exfiltration qua JS nhưng cần chống CSRF; XSS vẫn có thể tạo request trong phiên |
| BFF giữ token phía server | Browser không giữ OAuth token; thường chỉ giữ session cookie | Browser gửi cookie session tới BFF | Cần bảo vệ session cookie và endpoint BFF; CSRF vẫn cần xử lý |

### 6.1. In-memory token

Ứng dụng có thể giữ access token trong bộ nhớ runtime thay vì lưu bền vững. Khi reload hoặc đóng tab, token thường mất và ứng dụng cần lấy lại theo flow đã thiết kế.

Ưu điểm:

- Giảm tồn tại lâu dài trong browser storage.
- Không để token nằm sẵn trong localStorage sau khi người dùng đóng trình duyệt.
- Có thể giới hạn vòng đời theo runtime/phiên trang.

Giới hạn:

- XSS đang chạy vẫn có thể đọc token hoặc gọi API thay người dùng.
- Token có thể bị lộ qua log, telemetry hoặc state debug nếu ứng dụng xử lý sai.
- Reload có thể yêu cầu xác thực hoặc lấy token lại.
- Không tự giải quyết refresh token; refresh credential vẫn cần nơi lưu trữ và cơ chế bảo vệ riêng.

In-memory là biện pháp giảm persistence, không phải ranh giới bảo mật chống XSS.

### 6.2. HttpOnly cookie

Cookie có thuộc tính **HttpOnly** không được JavaScript đọc qua **document.cookie**. Cookie **Secure** chỉ được gửi qua kênh bảo mật HTTPS; **SameSite** kiểm soát một số ngữ cảnh gửi cookie cross-site.

Ví dụ cookie session:

~~~http
Set-Cookie: __Host-session=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Ví dụ minh họa một cấu hình cookie host-only. Prefix **__Host-** yêu cầu cookie được đặt với Secure, Path=/ và không có Domain attribute. Giá trị nên là session identifier opaque, không phải mặc định nhét toàn bộ JWT hoặc dữ liệu nhạy cảm vào cookie.

Ưu điểm:

- JavaScript không thể đọc giá trị cookie HttpOnly qua API thông thường.
- Trình duyệt tự quản lý gửi cookie theo domain, path, secure và SameSite.
- Có thể dùng session phía server để giữ access/refresh token ở backend.

Giới hạn:

- Cookie tự động được trình duyệt gửi, vì vậy cần đánh giá CSRF.
- XSS vẫn có thể gửi request same-origin trong phiên dù không đọc được cookie.
- Cookie cần cấu hình domain/path/SameSite đúng và bảo vệ session fixation.
- Không nên nhầm HttpOnly với khả năng chống mọi tác động của XSS.

### 6.3. Backend-for-Frontend (BFF)

Với kiến trúc BFF, browser giữ một session cookie; backend giữ OAuth access token/refresh token và gọi resource server thay mặt browser.

~~~mermaid
flowchart LR
    B[Browser] -->|Session cookie HttpOnly| F[BFF]
    F -->|Access token trong backend| R[Resource API]
    F -->|Refresh token được bảo vệ| A[Authorization Server]
    A -->|Token mới| F
    R -->|Kết quả| F
    F -->|Dữ liệu cần thiết| B
~~~

Lợi ích:

- Browser không cần lưu OAuth bearer token trong localStorage/sessionStorage.
- Refresh token được giữ ở backend với kiểm soát truy cập và lưu trữ phù hợp.
- BFF có thể giới hạn API mà browser được gọi và áp dụng policy tập trung.

Chi phí và rủi ro:

- BFF phải bảo vệ session cookie, CSRF, session lifecycle và backend token store.
- BFF trở thành một thành phần cần sẵn sàng, giám sát và mở rộng.
- XSS vẫn có thể gọi các endpoint BFF mà người dùng có quyền gọi.
- Cần kiểm soát CORS, origin, request validation và quyền theo từng thao tác.

BFF giảm việc đưa bearer token tới JavaScript; nó không làm ứng dụng miễn nhiễm với XSS hoặc lỗi authorization.

## 7. Cookie và CSRF: đánh đổi cần hiểu đúng

### 7.1. Vì sao cookie có rủi ro CSRF?

Trình duyệt có thể tự động đính kèm cookie phù hợp vào request. Nếu attacker khiến trình duyệt gửi request tới ứng dụng, cookie session có thể được gửi cùng request dù attacker không đọc được cookie.

Đây là khác biệt quan trọng:

- localStorage token thường được JavaScript chủ động gắn vào header Authorization; trang cross-site không thể đọc localStorage của origin khác theo same-origin policy.
- Cookie được trình duyệt tự động gửi theo quy tắc cookie, nên cần kiểm soát CSRF.

Không vì localStorage ít tự động gửi hơn mà kết luận nó an toàn hơn tổng thể; XSS có thể đọc token trực tiếp.

### 7.2. Biện pháp chống CSRF

Tùy kiến trúc và mức độ rủi ro, kết hợp:

- Cookie **SameSite=Lax** hoặc **Strict** khi flow ứng dụng cho phép.
- CSRF token được kiểm tra phía server cho request thay đổi trạng thái.
- Kiểm tra **Origin** và/hoặc **Referer** theo policy.
- Không dùng GET cho hành động thay đổi trạng thái.
- Kiểm tra content type và cấu trúc request phù hợp.
- Giới hạn CORS; không phản chiếu Origin tùy ý và không cho credentials với origin không tin cậy.
- Dùng cookie host-only, Secure, HttpOnly và Path phù hợp.

SameSite là một lớp phòng vệ, không nên xem là giải pháp CSRF duy nhất cho mọi flow. Cần kiểm tra hành vi trên browser, subdomain và luồng điều hướng thực tế.

### 7.3. HttpOnly không ngăn XSS hành động

Nếu XSS chạy trong trang, script có thể không đọc được cookie HttpOnly, nhưng vẫn có thể gọi endpoint same-origin; trình duyệt sẽ tự gửi cookie. Vì vậy:

- HttpOnly giúp giảm nguy cơ attacker lấy cookie/session secret ra ngoài.
- Nó không ngăn attacker thao tác trong phiên hiện tại.
- Cần kết hợp XSS prevention, CSRF protection, authorization và xác nhận bổ sung cho hành động nhạy cảm.

## 8. Các biện pháp giảm XSS và token exposure

### 8.1. Ngăn XSS tại nguồn

- Encode output theo đúng ngữ cảnh HTML, attribute, JavaScript, CSS hoặc URL.
- Ưu tiên API DOM an toàn; tránh đưa dữ liệu không tin cậy vào HTML parser.
- Sanitize HTML nếu sản phẩm thực sự cần hiển thị HTML do người dùng cung cấp.
- Tránh **eval**, **Function**, inline script và các sink nguy hiểm khi không cần.
- Validate input ở server; lưu ý validation không thay thế output encoding.
- Cập nhật dependency và kiểm soát nguồn script bên thứ ba.

### 8.2. Content Security Policy

CSP có thể giới hạn nguồn script và giảm tác động của một số dạng XSS:

- Dùng nonce hoặc hash cho script hợp lệ thay vì allowlist rộng.
- Tránh **unsafe-inline** và **unsafe-eval** nếu có thể.
- Hạn chế **script-src**, **object-src**, **base-uri** và các directive liên quan.
- Dùng **frame-ancestors** để kiểm soát embedding khi phù hợp.
- Bắt đầu bằng report-only khi cần quan sát tác động, sau đó triển khai enforcement.

CSP là defense-in-depth. CSP cấu hình sai hoặc allowlist quá rộng vẫn có thể cho phép script độc hại.

### 8.3. Trusted Types và kiểm soát DOM

Trusted Types có thể giúp hạn chế việc đưa chuỗi không tin cậy vào một số DOM injection sinks trên trình duyệt hỗ trợ. Kết hợp với API DOM an toàn và code review để giảm DOM-based XSS.

### 8.4. Giảm quyền và thời gian sử dụng token

- Cấp scope tối thiểu cần thiết cho từng API.
- Dùng audience hẹp, không dùng một access token cho mọi resource nếu không cần.
- Giữ access token có lifetime ngắn phù hợp rủi ro.
- Không lưu refresh token dài hạn trong localStorage/sessionStorage nếu kiến trúc có lựa chọn an toàn hơn.
- Áp dụng refresh token rotation và reuse detection theo RFC 9700 khi dùng refresh token cho public client.
- Cân nhắc sender-constrained token như DPoP hoặc mTLS khi mô hình client và resource server hỗ trợ.
- Yêu cầu xác nhận lại hoặc step-up authentication cho hành động nhạy cảm.

Token ngắn hạn giảm cửa sổ replay, nhưng không ngăn attacker sử dụng token trong thời gian nó còn hiệu lực.

## 9. Quy tắc lưu trữ và truyền token

### 9.1. Không đưa token vào URL

Tránh đặt bearer token trong query string hoặc URL fragment nếu không có flow chuẩn yêu cầu. URL có thể xuất hiện trong:

- Browser history.
- Access log, proxy log và analytics.
- Referrer header trong một số điều kiện.
- Screenshot, clipboard hoặc hệ thống hỗ trợ người dùng.

Ưu tiên truyền access token trong header Authorization theo giao thức hoặc dùng cookie session được cấu hình đúng. Với OAuth authorization response, tuân thủ flow và quy tắc chống rò rỉ code/state/nonce tương ứng.

### 9.2. Không log token

Không ghi toàn bộ access token, refresh token, cookie session hoặc authorization header vào:

- Console log và debug trace.
- Error monitoring.
- Analytics.
- Request/response capture.
- Support ticket hoặc chat.

Nếu cần tương quan sự kiện, dùng request ID, contract ID hoặc fingerprint đã được thiết kế để không làm lộ credential. Không log raw token rồi kỳ vọng xóa sau.

### 9.3. Xóa và thay token đúng vòng đời

Ứng dụng cần:

- Xóa token khỏi storage khi logout và khi đổi tài khoản.
- Không tái sử dụng token của user trước cho user sau trên cùng browser profile.
- Xử lý token hết hạn theo thời gian phía server và policy client.
- Xóa bản sao trong memory/state/cache khi không còn cần.
- Không coi thao tác xóa localStorage/sessionStorage là thu hồi phía server.
- Xử lý refresh token rotation đồng bộ để tránh dùng lại token cũ.

Nếu logout cần vô hiệu hóa session ngay, phải gọi cơ chế logout/revocation phía server phù hợp; xóa dữ liệu phía browser chỉ là một phần.

### 9.4. Mã hóa token trước khi lưu có giải quyết được không?

Thông thường, tự mã hóa token bằng JavaScript trước khi lưu localStorage không tạo ra ranh giới bảo vệ đáng tin cậy trước XSS:

- Nếu khóa giải mã nằm trong cùng JavaScript bundle hoặc storage, script độc hại có thể lấy khóa.
- Nếu ứng dụng cung cấp API giải mã, script độc hại có thể gọi API đó.
- Nếu token được giải mã trong runtime để gắn vào request, XSS có thể sử dụng chính runtime đó.

Web Crypto và non-extractable key có thể hữu ích cho một số thiết kế khóa, nhưng không tự bảo vệ phiên khỏi script độc hại có thể gọi các thao tác mật mã được ứng dụng cho phép. Không nên xem “encrypt rồi lưu localStorage” là giải pháp thay thế HttpOnly/BFF hoặc XSS prevention.

## 10. Lựa chọn kiến trúc theo loại ứng dụng

| Kiến trúc | Hướng thiết kế thường cân nhắc | Điểm phải bảo vệ |
|---|---|---|
| SPA gọi API trực tiếp | Access token ngắn hạn trong memory; Authorization Code + PKCE; tránh lưu refresh token dài hạn trong browser storage | XSS, token replay, refresh rotation, scope/audience |
| Web app có backend/BFF | Backend giữ access/refresh token; browser giữ session cookie HttpOnly/Secure/SameSite | CSRF, session fixation, session theft, BFF authorization |
| Ứng dụng nhiều tab | Tránh chia sẻ token dài hạn qua localStorage nếu không cần; thiết kế session/token coordination có chủ đích | Đồng bộ logout, race condition, token rotation |
| Thiết bị dùng chung | Ưu tiên session ngắn, logout server-side và không lưu credential bền vững | Dữ liệu còn lại sau logout, browser profile, cache |
| Ứng dụng nhạy cảm | Token lifetime ngắn, audience/scope hẹp, sender constraint và step-up cho hành động quan trọng | Replay, XSS, revocation và audit |

Đây là hướng thiết kế, không phải công thức bắt buộc. Quyết định cần dựa trên threat model, khả năng của authorization server/resource server và trải nghiệm sản phẩm.

### 10.1. SPA dùng Authorization Code + PKCE

Với ứng dụng trình duyệt là public client:

- Dùng Authorization Code Flow với PKCE theo OAuth security best practice.
- Không nhúng client secret vào JavaScript; secret trong bundle không còn là secret.
- Xác minh redirect URI chính xác và bảo vệ state/nonce theo flow.
- Lưu access token ngắn hạn trong memory nếu ứng dụng cần gọi API trực tiếp.
- Có kế hoạch cho refresh token: sender-constrained hoặc rotation/reuse detection theo RFC 9700.
- Đánh giá BFF nếu muốn giữ OAuth token ngoài browser.

PKCE bảo vệ authorization code khỏi một số dạng interception/injection; nó không ngăn XSS đọc token sau khi token đã được cấp cho JavaScript.

### 10.2. BFF và session cookie

Với BFF:

- Backend thực hiện OAuth flow và giữ token phía server.
- Browser nhận session identifier opaque qua cookie HttpOnly, Secure.
- BFF chỉ cung cấp các endpoint cần thiết cho frontend.
- Mỗi endpoint BFF kiểm tra authorization theo user, client, resource và action.
- Áp dụng CSRF protection và kiểm tra Origin.
- Rotate session ID sau đăng nhập hoặc thay đổi mức xác thực.
- Hủy session phía server khi logout hoặc khi có sự cố.

Không chuyển toàn bộ API quyền rộng thành proxy tổng quát mà không có authorization. BFF không được trở thành một “confused deputy” cho mọi request từ browser.

## 11. Checklist đánh giá localStorage/sessionStorage

**Lưu trữ**

- [ ] Xác định rõ loại token đang lưu: access, refresh, ID hay token nghiệp vụ.
- [ ] Ghi nhận thời hạn và quyền của từng token.
- [ ] Đánh giá token có thật sự cần tồn tại sau reload hoặc qua nhiều tab không.
- [ ] Không coi sessionStorage là an toàn trước XSS.
- [ ] Tránh lưu refresh token dài hạn trong localStorage/sessionStorage nếu có phương án phù hợp hơn.
- [ ] Có xóa token khi logout, hết hạn và đổi tài khoản.

**XSS và script**

- [ ] Có output encoding và DOM API an toàn.
- [ ] Kiểm soát dependency, script bên thứ ba và tag manager.
- [ ] Có CSP phù hợp, hạn chế inline/eval.
- [ ] Cân nhắc Trusted Types và kiểm thử DOM-based XSS.
- [ ] Không ghi token vào console, analytics, telemetry hoặc error report.

**Truyền và xác minh**

- [ ] Không đưa bearer token vào URL.
- [ ] Chỉ gửi token tới đúng audience/resource.
- [ ] Dùng HTTPS và bảo vệ header/cookie trong toàn tuyến.
- [ ] Access token có lifetime và scope tối thiểu.
- [ ] Có xử lý revocation, replay và refresh token rotation phù hợp.

**Kiến trúc thay thế**

- [ ] Đã đánh giá in-memory token và giới hạn của nó trước XSS.
- [ ] Đã đánh giá BFF/server-side token storage khi phù hợp.
- [ ] Nếu dùng cookie, có HttpOnly, Secure, SameSite và CSRF protection.
- [ ] Có kiểm thử logout, nhiều tab, reload, tab mới và browser restart.
- [ ] Có quy trình ứng phó khi token bị đánh cắp.

## 12. Bộ kiểm thử bảo mật thực tế

| ID | Kiểm thử | Kết quả mong đợi |
|---|---|---|
| S01 | Chèn XSS thử nghiệm trong môi trường cô lập và kiểm tra localStorage | Xác nhận script cùng origin có thể đọc giá trị; test chứng minh rủi ro |
| S02 | Lặp lại với sessionStorage | Xác nhận script cùng origin vẫn đọc được token |
| S03 | Reload tab có sessionStorage | Token vẫn tồn tại trong cùng tab session |
| S04 | Mở tab mới có opener | Kiểm tra hành vi sao chép session storage theo browser |
| S05 | Đóng tab và mở tab mới | Xác nhận vòng đời session storage theo browser |
| S06 | Đóng/mở browser với localStorage | Xác nhận dữ liệu còn tồn tại theo browser policy |
| S07 | Logout rồi đăng nhập user khác | Không còn token hoặc state của user trước |
| S08 | Kiểm tra cookie HttpOnly | JavaScript không đọc được cookie qua document.cookie |
| S09 | Kiểm tra XSS với BFF cookie | Script có thể gọi endpoint trong phiên; authorization vẫn phải giới hạn |
| S10 | Gửi request cross-site tới endpoint thay đổi trạng thái | CSRF protection chặn request không hợp lệ |
| S11 | Tìm token trong URL, log và telemetry | Không tìm thấy credential dạng raw |
| S12 | Replay access token đã đánh cắp trong môi trường thử nghiệm | Server chặn theo exp/revocation/sender constraint đúng policy |
| S13 | Refresh token rotation và gửi lại token cũ | Reuse detection xử lý theo policy |
| S14 | CSP report/enforcement | Script ngoài policy bị chặn hoặc báo cáo theo cấu hình |

Chỉ thực hiện thử nghiệm XSS trong môi trường được phép, với token giả và tài khoản thử nghiệm. Không đưa token production vào test harness hoặc gửi token thật tới endpoint kiểm thử.

**Điều cần nhớ:** localStorage và sessionStorage đều cho JavaScript cùng origin đọc dữ liệu. sessionStorage có phạm vi tab và vòng đời ngắn hơn, nhưng không chống XSS. Với bearer token, rủi ro chính là token bị sao chép rồi phát lại. Hãy giảm token tồn tại lâu trong browser, ngăn XSS, giới hạn quyền và thời hạn, cân nhắc BFF với HttpOnly cookie, đồng thời xử lý CSRF và revocation đúng cách.

## Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token và rủi ro lộ/phát lại token.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): OAuth access token và refresh token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): Bảo vệ public client, refresh token rotation và sender-constrained token.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636): PKCE.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): Sender-constrained access token bằng mTLS.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): Ràng buộc token với proof-of-possession.
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265): Cookie và thuộc tính quản lý trạng thái HTTP.
- [OWASP HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): Rủi ro và khuyến nghị với browser storage.
- [OWASP Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): Ngăn XSS.
- [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): Phòng chống CSRF.
- [OWASP Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html): CSP và giảm thiểu XSS.
- [MDN — Window.localStorage](https://developer.mozilla.org/docs/Web/API/Window/localStorage): Phạm vi và vòng đời localStorage.
- [MDN — Window.sessionStorage](https://developer.mozilla.org/docs/Web/API/Window/sessionStorage): Phạm vi browsing context và vòng đời sessionStorage.
