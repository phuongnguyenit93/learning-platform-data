# SameSite attribute

## 1. SameSite là gì?

**SameSite** là thuộc tính của HTTP cookie giúp trình duyệt quyết định cookie có được gửi kèm request phát sinh trong ngữ cảnh same-site hay cross-site hay không. Mục tiêu bảo mật nổi bật của thuộc tính này là giảm nguy cơ **Cross-Site Request Forgery (CSRF)**: một website bên ngoài dụ trình duyệt của người dùng gửi request tới ứng dụng đang đăng nhập, khiến cookie phiên tự động được đính kèm.

SameSite là chính sách do **browser thực thi**. Server gửi thuộc tính trong header Set-Cookie; trình duyệt lưu cookie cùng chính sách và áp dụng khi quyết định gửi cookie. Server vẫn phải xác thực session và kiểm tra quyền trên từng request. SameSite không mã hóa cookie, không xác minh danh tính người dùng, không ngăn XSS và không thay thế các biện pháp CSRF khác.

Ba giá trị chính:

- **Strict:** chỉ gửi cookie trong ngữ cảnh same-site.
- **Lax:** gửi trong ngữ cảnh same-site và một số điều hướng cấp cao nhất từ site khác bằng phương thức an toàn, thường là GET.
- **None:** cho phép cookie được gửi trong ngữ cảnh cross-site nếu các điều kiện khác đáp ứng; cookie phải có Secure trong các trình duyệt hiện đại.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, SameSite gắn trực tiếp với bảo vệ cookie session, trust boundary của browser, đăng nhập liên kết và phòng chống CSRF. Cần hiểu chính xác khái niệm site, origin, điều hướng, fetch, iframe và callback đăng nhập để chọn chính sách mà không vô tình làm hỏng luồng xác thực.

Sau bài học, người học có thể:

- Phân biệt site với origin và hiểu schemeful same-site.
- Giải thích hành vi của Strict, Lax và None.
- Chọn SameSite phù hợp cho session cookie và cookie giao dịch.
- Phân tích tác động với form POST, fetch, iframe và OAuth/OIDC/SAML callback.
- Hiểu giới hạn của SameSite trước CSRF, XSS và third-party cookie restrictions.
- Kiểm thử hành vi cookie trên browser thực tế và thiết kế fallback an toàn.

## 2. Site và origin không phải một khái niệm

Để hiểu SameSite, trước tiên phải phân biệt **site** và **origin**.

- **Origin** được xác định bởi scheme, hostname và port. Ví dụ, https://app.example.test:443 và https://api.example.test:443 là hai origin khác nhau vì hostname khác nhau.
- **Site** trong mô hình schemeful same-site được xác định bởi scheme và registrable domain (thường là eTLD+1 theo Public Suffix List). Port không phải thành phần phân biệt site. Ví dụ, hai hostname con dưới example.test có thể cùng site nếu cùng scheme.

| URL A | URL B | Cùng origin? | Cùng site? |
| --- | --- | --- | --- |
| https://app.example.test | https://app.example.test | Có | Có |
| https://app.example.test | https://api.example.test | Không | Thường có |
| https://app.example.test | http://app.example.test | Không | Không theo schemeful same-site |
| https://app.example.test | https://other.test | Không | Không |
| https://shop.example.test | https://evil.example.test | Không | Thường có, dù hai origin khác nhau |

Các ví dụ dùng tên miền giả định để minh họa. Registrable domain phụ thuộc Public Suffix List; không phải cứ lấy hai nhãn cuối của hostname là chính xác. Ví dụ, các miền dưới một public suffix như co.uk có quy tắc registrable domain riêng.

### 2.1. Vì sao scheme cũng quan trọng?

Mô hình **schemeful same-site** phân biệt HTTP và HTTPS. Vì vậy, trang HTTPS và trang HTTP trên cùng hostname có thể được xem là cross-site trong ngữ cảnh cookie SameSite. Điều này giảm một số rủi ro khi nội dung không bảo mật có thể tương tác với trang bảo mật.

Ứng dụng nên chuyển toàn bộ luồng sang HTTPS, bật HSTS phù hợp và tránh phục vụ cùng một ứng dụng đăng nhập qua HTTP. Không thiết kế dựa trên giả định rằng HTTP và HTTPS luôn được xem là cùng site.

### 2.2. Same-site không có nghĩa same-origin

Giả sử ứng dụng có:

- https://app.example.test — frontend.
- https://api.example.test — API.
- https://untrusted.example.test — một ứng dụng con do nhóm khác vận hành.

Ba địa chỉ có thể cùng site nhưng là các origin khác nhau. Cookie SameSite=Lax hoặc Strict có thể được gửi trong request giữa các ngữ cảnh cùng site theo điều kiện cookie; tuy nhiên, SameSite không ngăn JavaScript ở một origin khác gọi API nếu các cơ chế browser khác cho phép.

Đây là giới hạn quan trọng: **SameSite không phải ranh giới cô lập giữa các subdomain**. Một subdomain bị chiếm quyền có thể tạo request same-site tới ứng dụng chính. Vì vậy cần cookie host-only, kiểm tra Origin/CSRF token, authorization và kiểm soát subdomain.

### 2.3. Cookie Domain và SameSite là hai thuộc tính riêng

Thuộc tính Domain quyết định hostname nào có thể nhận cookie; SameSite quyết định cookie có được gửi trong một ngữ cảnh site hay không.

- Cookie không có Domain thường là host-only, chỉ gửi tới host đã đặt cookie.
- Cookie có Domain rộng như example.test có thể được gửi tới nhiều subdomain phù hợp.
- SameSite=Lax không thu hẹp phạm vi Domain.
- SameSite=Strict cũng không thay thế việc giới hạn cookie theo host.

Đối với session cookie, thường nên dùng cookie host-only và phạm vi tối thiểu cần thiết. Tránh đặt Domain rộng chỉ để frontend và API có thể cùng đọc một cookie; thiết kế BFF hoặc endpoint cùng host có thể đơn giản hóa ranh giới.

## 3. Ba giá trị Strict, Lax và None

### 3.1. Strict

Với SameSite=Strict, browser chỉ gửi cookie trong ngữ cảnh được xem là same-site. Khi người dùng đang đăng nhập vào bank.example.test rồi nhấp một liên kết từ news.example.test tới bank.example.test, cookie Strict có thể không được gửi trong request điều hướng ban đầu vì điều hướng bắt đầu từ site khác.

Ưu điểm:

- Hạn chế mạnh việc cookie tự động đi theo request cross-site.
- Phù hợp cookie nhạy cảm khi ứng dụng không cần duy trì session qua điều hướng đến từ site ngoài.
- Giảm một lớp rủi ro CSRF với cookie phiên.

Trade-off:

- Người dùng có thể thấy trạng thái chưa đăng nhập ở lần truy cập đầu tiên từ liên kết bên ngoài.
- Luồng SSO hoặc callback từ IdP có thể cần xử lý cẩn thận.
- Không bảo vệ khỏi request same-site phát sinh từ subdomain không đáng tin.
- Không bảo vệ khỏi XSS trong chính origin của ứng dụng.

Strict thường phù hợp khi yêu cầu bảo vệ cao và UX cho phép người dùng điều hướng lại hoặc đăng nhập lại theo cách có kiểm soát.

### 3.2. Lax

SameSite=Lax cho phép cookie trong ngữ cảnh same-site và một số **top-level navigation** cross-site dùng phương thức an toàn. Trường hợp điển hình là người dùng nhấp liên kết từ một website khác để mở trang của ứng dụng bằng GET.

Ví dụ:

- Người dùng đang đăng nhập tại app.example.test.
- Họ mở một liên kết từ external.test tới https://app.example.test/account.
- Browser có thể gửi cookie Lax trong điều hướng top-level GET.
- Một form POST cross-site tới app.example.test thường không được gửi cookie Lax.

Lax là lựa chọn mặc định thực tế cho nhiều session cookie web vì giữ được trải nghiệm điều hướng từ liên kết bên ngoài trong khi chặn nhiều tình huống CSRF dựa trên form POST cross-site.

Tuy nhiên, Lax không ngăn mọi CSRF. Nếu ứng dụng thay đổi trạng thái qua GET, một trang ngoài có thể dụ browser điều hướng tới URL đó và cookie Lax vẫn có thể được gửi. Do đó, **GET phải là phương thức an toàn, không tạo side effect**.

Một số browser có hành vi tương thích khi thuộc tính SameSite bị bỏ qua hoặc cookie vừa được tạo, thường được gọi là Lax-by-default và có thể có ngoại lệ tạm thời cho POST trong một khoảng thời gian ngắn. Không dựa vào hành vi này làm hợp đồng bảo mật; hãy đặt SameSite rõ ràng và kiểm thử browser mục tiêu.

### 3.3. None

SameSite=None cho phép cookie tham gia các ngữ cảnh cross-site nếu các điều kiện cookie và chính sách browser khác đáp ứng. Ví dụ, một dịch vụ nhúng trong iframe trên website khác hoặc một callback cross-site có thể cần cookie hoạt động theo ngữ cảnh này.

Trong các browser hiện đại, cookie SameSite=None phải có Secure:

~~~http
Set-Cookie: session_id=<opaque-value>; Path=/; Secure; HttpOnly; SameSite=None
~~~

Nếu thiếu Secure, browser hiện đại thường từ chối cookie hoặc không áp dụng nó theo cách mong đợi. Cookie vẫn cần HTTPS; không dùng None như cách sửa nhanh cho lỗi cookie.

Trade-off:

- Cho phép các flow cross-site cần thiết.
- Tăng bề mặt rủi ro CSRF nếu cookie được gửi tự động.
- Không bảo đảm cookie third-party được chấp nhận; browser có thể chặn third-party cookies theo chính sách riêng.
- Cần các biện pháp CSRF, Origin validation, Fetch Metadata và authorization phù hợp.

### 3.4. Bảng so sánh nhanh

| Ngữ cảnh request | Strict | Lax | None; Secure |
| --- | --- | --- | --- |
| Request same-site thông thường | Gửi nếu các điều kiện cookie khác đạt | Gửi nếu các điều kiện cookie khác đạt | Gửi nếu các điều kiện cookie khác đạt |
| Cross-site top-level link GET | Không gửi | Thường gửi | Có thể gửi nếu browser cho phép |
| Cross-site top-level form POST | Không gửi | Thường không gửi | Có thể gửi nếu browser cho phép |
| Cross-site fetch/XHR | Không gửi | Không gửi | Có thể gửi nếu browser cho phép và fetch credentials/CORS phù hợp |
| Cookie trong iframe cross-site | Không gửi | Không gửi | Có thể gửi nếu browser cho phép third-party context |
| Cookie không có Secure | Có thể tùy chính sách cookie khác | Có thể tùy chính sách cookie khác | Bị yêu cầu Secure trong browser hiện đại |

Bảng mô tả hành vi SameSite phổ biến; Domain/Path, Secure, expiry, credentials mode, browser privacy settings, third-party cookie blocking và các thuộc tính khác vẫn ảnh hưởng kết quả.

## 4. Browser quyết định gửi cookie như thế nào?

Khi request được tạo, browser xét nhiều điều kiện. Có thể mô hình hóa đơn giản:

~~~mermaid
flowchart TD
    A[Request được tạo] --> B{Cookie khớp host, path và thời hạn?}
    B -- Không --> X[Không gửi cookie]
    B -- Có --> C{Cookie có Secure và request dùng HTTPS?}
    C -- Không --> X
    C -- Có --> D{Ngữ cảnh same-site?}
    D -- Có --> E[Gửi nếu các điều kiện khác đạt]
    D -- Không --> F{SameSite value?}
    F -- Strict --> X
    F -- Lax --> G{Top-level navigation với safe method?}
    G -- Không --> X
    G -- Có --> E
    F -- None --> H{Browser cho phép cookie trong context này?}
    H -- Không --> X
    H -- Có --> E
~~~

Đây là mô hình học tập, không phải thuật toán đầy đủ của mọi browser. Trình duyệt còn xét cookie prefix, partitioning, third-party cookie policy, credentials mode, sandbox, privacy settings và các điều kiện khác.

Một điểm quan trọng: SameSite là **một điều kiện trong nhiều điều kiện**. Cookie có thể không được gửi vì Domain/Path không khớp, hết hạn, Secure không đáp ứng, browser chặn third-party cookie hoặc request không bật credentials.

## 5. Top-level navigation, fetch và iframe

### 5.1. Top-level navigation

Top-level navigation là điều hướng khiến browser thay đổi trang chính đang hiển thị, ví dụ người dùng nhấp liên kết hoặc submit form làm tải trang mới. Lax cho phép cookie trong một số top-level navigation cross-site dùng safe method, thường là GET.

Không nhầm top-level navigation với mọi request do trang tạo ra. Một trang ngoài gọi fetch tới API không phải top-level navigation, ngay cả khi URL đích thuộc ứng dụng đã đăng nhập.

### 5.2. Fetch và XMLHttpRequest

Với fetch cross-origin, JavaScript có thể cần đặt credentials mode là include để browser gửi credential phù hợp. Tuy nhiên:

- credentials: include không vượt qua SameSite.
- SameSite=None không tự vượt qua CORS.
- CORS quyết định script có thể đọc response cross-origin theo policy; nó không thay thế authentication hoặc authorization.
- Browser privacy policy có thể vẫn chặn cookie third-party.

Ví dụ:

~~~js
fetch("https://api.example.test/profile", {
  method: "GET",
  credentials: "include"
});
~~~

Nếu cookie có SameSite=Lax và request là cross-site fetch, cookie thường không được gửi. Nếu cookie là SameSite=None; Secure, browser có thể gửi nếu third-party cookie policy và CORS/credentials cho phép.

Khi dùng credentialed CORS, server cần chỉ định origin cụ thể, cho phép credentials theo đúng cấu hình và tránh wildcard origin với credentials. Nhưng ngay cả khi CORS được cấu hình đúng, API vẫn phải xác minh session và quyền.

### 5.3. Iframe và embedded application

Cookie dùng trong iframe cross-site thường cần SameSite=None; Secure để có thể được gửi. Tuy nhiên, browser có thể chặn third-party cookies hoàn toàn hoặc áp dụng partitioned storage. Do đó, thêm SameSite=None không bảo đảm ứng dụng nhúng hoạt động trên mọi browser.

Các lựa chọn kiến trúc:

- Ưu tiên điều hướng top-level hoặc popup đăng nhập khi phù hợp.
- Dùng Authorization Code + PKCE và callback top-level thay vì dựa vào session cookie third-party lâu dài.
- Đánh giá Storage Access API hoặc partitioned cookies khi sản phẩm thực sự cần embedded context.
- Hạn chế quyền và thời gian của phiên nhúng.
- Kiểm thử các browser privacy modes và thiết lập chặn tracking.

## 6. SameSite và CSRF

CSRF xảy ra khi browser của người dùng gửi request tới một website mà người dùng đã đăng nhập, tự đính kèm cookie phiên, trong khi request được kích hoạt từ một site khác. Server có thể nhầm request đó là hành động do người dùng chủ động thực hiện.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant E as Website ngoài
    participant B as Browser
    participant A as Ứng dụng đang đăng nhập
    U->>B: Đăng nhập ứng dụng A
    B->>A: Set-Cookie session
    U->>E: Mở website ngoài
    E->>B: Dụ submit form tới A
    B->>A: POST request + cookie nếu policy cho phép
    A->>A: Kiểm tra CSRF và authorization
    A-->>B: Từ chối hoặc xử lý theo policy
~~~

SameSite giúp browser không gửi cookie trong nhiều ngữ cảnh cross-site, đặc biệt với Lax/Strict. Nhưng cần xem nó là **defense in depth**, kết hợp:

1. Cookie session có SameSite phù hợp (thường Lax hoặc Strict tùy flow).
2. CSRF token gắn với session hoặc cơ chế tương đương cho request thay đổi trạng thái.
3. Kiểm tra Origin và/hoặc Referer theo chính sách.
4. Fetch Metadata như Sec-Fetch-Site để hỗ trợ phân biệt cross-site, same-site và same-origin.
5. Không thực hiện thay đổi trạng thái bằng GET.
6. Authorization và kiểm tra nghiệp vụ phía server.

### 6.1. Khi nào SameSite chưa đủ?

- **Same-site subdomain:** một subdomain bị chiếm có thể tạo request cùng site tới ứng dụng chính.
- **XSS:** script chạy trong origin ứng dụng có thể gửi request hợp lệ và có thể lấy CSRF token tùy cách lưu.
- **Cookie Domain rộng:** cookie có thể được chia sẻ với subdomain ngoài dự kiến.
- **Unsafe GET:** cookie Lax có thể được gửi trong top-level GET từ site ngoài.
- **Legacy/unsupported browsers:** hành vi có thể khác với browser hiện đại.
- **Cross-site workflow hợp lệ:** callback từ IdP, payment provider hoặc embedded service có thể yêu cầu chính sách đặc biệt.

SameSite không chứng minh request xuất phát từ thao tác người dùng thật. Nó chỉ tác động tới việc browser gửi cookie theo ngữ cảnh site.

### 6.2. CSRF token vẫn có vai trò

Một synchronizer token có thể được lưu phía server và gắn với session; client gửi token trong form hoặc custom header. Server kiểm tra token trước khi thực hiện side effect. Token không nên được đặt trong cookie mà server chỉ kiểm tra sự hiện diện giống như cookie session, vì kẻ tấn công có thể không cần biết giá trị để kích hoạt browser gửi cookie.

Double-submit cookie là một mô hình khác; cần ràng buộc token với session hoặc chữ ký phù hợp để tránh biến cookie do attacker có thể đặt thành bypass. Chọn pattern theo threat model và framework được duy trì.

## 7. SameSite trong OAuth, OIDC và SAML

Đăng nhập liên kết thường chuyển browser qua nhiều site: ứng dụng → Identity Provider (IdP) → ứng dụng. Cookie của ứng dụng có thể không được gửi trong callback tùy phương thức trả kết quả.

### 7.1. Authorization Code callback bằng GET

Một flow OIDC Authorization Code thường trả authorization code qua redirect top-level GET tới redirect URI. Cookie SameSite=Lax của ứng dụng thường có thể được gửi trong top-level safe navigation, giúp ứng dụng tìm trạng thái đăng nhập/giao dịch cần thiết.

Dù cookie được gửi, ứng dụng vẫn phải kiểm tra:

- state gắn với giao dịch đăng nhập và chống CSRF.
- PKCE code_verifier khi áp dụng.
- issuer, audience, signature, expiry và nonce theo OIDC.
- redirect URI đã đăng ký.
- callback thuộc đúng browser transaction/session.

Không coi việc cookie được gửi là bằng chứng callback hợp lệ.

### 7.2. POST callback và form_post

Một số giao thức hoặc cấu hình trả kết quả bằng cross-site form POST, ví dụ OIDC response mode form_post hoặc SAML HTTP-POST binding. Cookie Lax thường không được gửi trong cross-site top-level POST. Cookie Strict cũng không được gửi.

Nếu callback cần một cookie giao dịch, thiết kế có thể cần cookie riêng SameSite=None; Secure với TTL ngắn và scope tối thiểu. Cần cân nhắc:

- Cookie chỉ dùng để ràng buộc transaction, không cấp quyền session đầy đủ trước khi response được xác minh.
- state/nonce và kiểm tra chữ ký/assertion vẫn bắt buộc.
- Cookie None làm tăng yêu cầu CSRF protection.
- Browser third-party cookie restrictions có thể ảnh hưởng các flow khác, đặc biệt khi dùng iframe.
- Có thể chọn callback top-level GET nếu giao thức và threat model cho phép.

Không hạ toàn bộ session cookie chính xuống SameSite=None chỉ để sửa một callback POST mà không đánh giá tác động.

### 7.3. SameSite và SSO

SSO có thể dựa vào cookie của IdP trong các ngữ cảnh top-level hoặc embedded. Cookie Strict có thể làm mất trạng thái đăng nhập IdP khi người dùng đến từ ứng dụng bên ngoài. Cookie Lax thường phù hợp hơn cho điều hướng top-level; cookie None có thể cần cho một số embedded flows nhưng phụ thuộc third-party cookie policy.

Thiết kế SSO hiện đại nên ưu tiên redirect top-level, state/nonce/PKCE và session riêng của từng relying party. Không dựa vào iframe ẩn và third-party cookie như cơ chế duy nhất để duy trì SSO.

## 8. Cấu hình cookie an toàn

Một session cookie phổ biến cho ứng dụng web first-party:

~~~http
Set-Cookie: __Host-session=<opaque-random-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Ý nghĩa:

- **__Host-** yêu cầu browser hỗ trợ prefix này phải đặt Secure, Path=/ và không có Domain.
- **Secure** giới hạn việc gửi cookie qua HTTPS.
- **HttpOnly** ngăn JavaScript đọc trực tiếp cookie.
- **SameSite=Lax** giảm nhiều request cross-site tự động gửi cookie nhưng vẫn hỗ trợ top-level GET navigation.
- **Path=/** làm cookie áp dụng cho toàn host; prefix __Host- yêu cầu giá trị này.
- Không có Domain nên cookie host-only.

Đối với ứng dụng cần session Strict, có thể dùng cookie:

~~~http
Set-Cookie: __Host-session=<opaque-random-id>; Path=/; Secure; HttpOnly; SameSite=Strict
~~~

Đối với cookie cần cross-site:

~~~http
Set-Cookie: __Host-cross-site-tx=<short-lived-random-id>; Path=/; Secure; HttpOnly; SameSite=None
~~~

Cookie giao dịch cross-site nên có TTL ngắn, dữ liệu tối thiểu và không tự cấp quyền. Tên prefix và các thuộc tính phải phù hợp yêu cầu browser; không thêm Domain vào cookie __Host-.

### 8.1. Đặt SameSite rõ ràng

Nếu bỏ thuộc tính SameSite, browser hiện đại thường áp dụng mặc định Lax hoặc hành vi tương đương. Nhưng không nên phụ thuộc mặc định vì browser, phiên bản và compatibility behavior có thể khác nhau.

Đặt rõ Strict, Lax hoặc None cho từng cookie theo chức năng. Một ứng dụng có thể có nhiều cookie với chính sách khác nhau: session chính, transaction callback, preference và analytics. Không áp dụng None cho tất cả chỉ vì một luồng cần cross-site.

### 8.2. SameSite không thay thế Secure và HttpOnly

- SameSite kiểm soát ngữ cảnh gửi cookie.
- Secure kiểm soát cookie chỉ được truyền qua kênh HTTPS.
- HttpOnly hạn chế JavaScript đọc cookie.
- Domain/Path giới hạn phạm vi gửi.
- Expires/Max-Age giới hạn vòng đời.

Mỗi thuộc tính giải quyết một vấn đề khác nhau. Cookie session thường cần kết hợp các thuộc tính phù hợp thay vì chọn một thuộc tính rồi coi là đủ.

## 9. Third-party cookie blocking và Partitioned cookies

**Third-party cookie** là cookie được sử dụng trong ngữ cảnh nhúng hoặc request mà site hiện tại khác site của cookie. SameSite=None cho phép cookie được gửi cross-site theo thuộc tính cookie, nhưng browser có thể có chính sách riêng chặn hoặc phân vùng third-party storage để bảo vệ quyền riêng tư.

Do đó:

- SameSite=None không có nghĩa browser bắt buộc phải gửi cookie third-party.
- Browser privacy setting, tracking prevention và chế độ riêng tư có thể chặn cookie.
- Các API như Storage Access API có thể cho phép một số embedded context xin quyền truy cập storage theo chính sách browser.
- **Partitioned cookies** (CHIPS) có thể phân vùng cookie theo top-level site, giúp một số dịch vụ nhúng giữ trạng thái riêng cho từng site nhúng mà không chia sẻ cookie toàn cục.

Ví dụ cookie partitioned:

~~~http
Set-Cookie: widget_session=<opaque-id>; Path=/; Secure; HttpOnly; SameSite=None; Partitioned
~~~

Partitioned không phải cách thay thế mọi session cookie. Cần kiểm tra browser hỗ trợ, yêu cầu Secure, semantics của partition key và nguy cơ khi ứng dụng cần chia sẻ trạng thái giữa nhiều top-level sites. Không lưu dữ liệu có thể dùng để theo dõi người dùng xuyên site nếu không có cơ sở và chính sách phù hợp.

## 10. Các lỗi triển khai phổ biến

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đặt SameSite=None nhưng thiếu Secure | Browser từ chối hoặc không gửi cookie như mong đợi | Dùng HTTPS và Secure |
| Dùng None cho mọi cookie | Tăng bề mặt CSRF không cần thiết | Chọn policy riêng theo từng cookie |
| Dùng Strict cho callback SSO mà không kiểm thử | Cookie transaction không được gửi khi callback từ site khác | Thiết kế callback phù hợp, state/nonce và cookie giao dịch riêng |
| Cho rằng Lax chặn mọi CSRF | Unsafe GET hoặc same-site subdomain vẫn có thể tạo request | Không side effect qua GET; CSRF token và Origin validation |
| Cho rằng SameSite = same-origin | Bỏ qua rủi ro subdomain | Host-only cookie, kiểm soát subdomain, CSRF và authorization |
| Dùng cookie Domain quá rộng | Subdomain không tin cậy có thể nhận hoặc tác động cookie theo điều kiện | Ưu tiên host-only và prefix __Host- |
| Tin CORS thay CSRF | API vẫn có thể nhận request được browser gửi | CSRF controls và server-side auth |
| Dựa vào third-party cookie cho SSO | Login hỏng khi browser chặn cookie | Redirect top-level, PKCE, state/nonce |
| GET làm thay đổi dữ liệu | Lax có thể gửi cookie trong cross-site top-level GET | GET chỉ đọc; dùng POST/PUT/DELETE và CSRF defense |
| Không test callback POST | Cookie Lax không được gửi, login thất bại | Kiểm thử response mode và cookie transaction |
| Chỉ kiểm tra trên một browser | Khác biệt privacy/browser behavior gây lỗi production | Test matrix browser, version và privacy settings |
| Dùng None để chữa lỗi CORS | Lẫn lộn hai chính sách khác nhau | Phân tích credentials mode, CORS, SameSite và browser privacy riêng |

## 11. Kiểm thử SameSite trong browser

Không nên chỉ đọc header Set-Cookie rồi kết luận cookie sẽ được gửi. Hãy kiểm tra cả **request thực tế** trong Developer Tools và server log an toàn.

Một bộ kiểm thử tối thiểu:

1. Đăng nhập ứng dụng, xác nhận session cookie có thuộc tính mong đợi.
2. Từ site khác mở liên kết top-level GET tới ứng dụng; quan sát Strict/Lax/None.
3. Từ site khác submit form POST tới endpoint test; quan sát cookie và xác nhận không có side effect trái phép.
4. Từ site khác gọi fetch cross-origin với credentials include; kiểm tra SameSite, CORS và browser privacy.
5. Nhúng ứng dụng trong iframe cross-site; kiểm tra third-party cookie blocking và partitioning.
6. Thử callback OAuth/OIDC GET và form_post; kiểm tra transaction binding.
7. Thử subdomain cùng site nhưng khác origin; xác minh Origin/CSRF và authorization.
8. Thử HTTP và HTTPS để kiểm tra schemeful same-site và Secure.
9. Thử cookie hết hạn, Domain/Path không khớp và browser chặn third-party cookie.
10. Thử XSS trong môi trường test để xác nhận SameSite không được xem là biện pháp chống XSS.

### 11.1. Quan sát trong Developer Tools

Trong tab Application/Storage, xem cookie và thuộc tính Domain, Path, Secure, HttpOnly, SameSite, expiry. Trong tab Network, mở request cụ thể và kiểm tra Request Headers có Cookie hay không. Browser có thể hiển thị lý do cookie bị chặn, chẳng hạn SameSite, Secure, third-party cookie policy hoặc partitioning.

Khi chẩn đoán, kiểm tra cả:

- URL trang khởi tạo request.
- URL đích và scheme.
- Request là top-level navigation, form submission, fetch hay iframe resource.
- HTTP method.
- Cookie Domain/Path/Secure/SameSite.
- Fetch credentials mode và CORS response.
- Browser privacy settings và phiên bản browser.

Không ghi giá trị session cookie vào ticket, screenshot hoặc log chia sẻ. Chỉ cần ghi tên cookie và thuộc tính; che hoặc bỏ giá trị bí mật.

## 12. Ma trận chọn SameSite theo use case

| Use case | Hướng cân nhắc | Lưu ý |
| --- | --- | --- |
| Session web first-party thông thường | Lax | Phù hợp nhiều ứng dụng; vẫn cần CSRF defense |
| Ứng dụng nhạy cảm không cần điều hướng cross-site giữ phiên | Strict | Kiểm thử link ngoài và SSO callback |
| Cookie giao dịch cho cross-site POST callback | None; Secure có scope và TTL hẹp | Dùng state/nonce, xác minh callback và không cấp session sớm |
| Cookie trong iframe cross-site | None; Secure hoặc partitioned theo kiến trúc | Browser có thể chặn third-party cookies |
| Cookie preference không nhạy cảm | Lax hoặc Strict tùy UX | Không cần None nếu không có nhu cầu cross-site |
| Cookie analytics/embedded widget | Cân nhắc partitioning và privacy policy | Không coi None là bảo đảm cookie hoạt động |
| API cùng site trên subdomain | Lax/Strict tùy flow và kiến trúc | Same-site không phải same-origin; cần CORS/CSRF/authorization |

Đây là hướng thiết kế ban đầu, không phải quy tắc tuyệt đối. Cần kiểm tra toàn bộ flow, browser hỗ trợ, yêu cầu UX và rủi ro của endpoint.

## 13. Checklist review

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Đã xác định site và origin? | Có sơ đồ scheme, registrable domain, host và port |
| Cookie nào cần cross-site? | Có lý do cụ thể cho từng cookie |
| Strict/Lax/None đã được chọn theo flow? | Không phụ thuộc mặc định hoặc đặt None hàng loạt |
| None có Secure? | Có HTTPS và Secure |
| Cookie session có host-only? | Không dùng Domain rộng nếu không cần |
| GET có side effect không? | Không; thay đổi trạng thái dùng method thích hợp và CSRF defense |
| Có CSRF token/Origin validation? | Có lớp server-side phù hợp với kiến trúc |
| Có subdomain không tin cậy? | Đã xem xét same-site nhưng cross-origin |
| OAuth/OIDC callback là GET hay POST? | Cookie transaction và state/nonce/PKCE phù hợp |
| Iframe/third-party context có cần không? | Có phương án cho browser privacy và partitioning |
| CORS có bị nhầm với CSRF? | Hai chính sách được kiểm tra riêng |
| Có test nhiều browser? | Có matrix browser, version và privacy settings |
| Cookie value có được bảo vệ? | Không log hoặc chia sẻ session ID |

### Tình huống tự kiểm tra

**Tình huống 1:** Cookie SameSite=Lax có được gửi khi người dùng nhấp liên kết từ một site khác tới ứng dụng bằng GET top-level không?

**Trả lời:** Thường có, nếu các điều kiện cookie khác đạt. Đây là lý do Lax giữ được trải nghiệm điều hướng từ liên kết ngoài.

**Tình huống 2:** Cookie Lax có được gửi trong cross-site form POST thông thường không?

**Trả lời:** Thường không. Nếu callback hợp lệ cần POST, phải thiết kế cookie transaction và kiểm soát callback phù hợp; không hạ toàn bộ session cookie một cách thiếu cân nhắc.

**Tình huống 3:** app.example.test gọi api.example.test. Hai URL khác origin; chúng có thể same-site không?

**Trả lời:** Có, nếu cùng scheme và registrable domain theo mô hình schemeful same-site. SameSite không thay thế CORS hoặc kiểm soát subdomain.

**Tình huống 4:** Cookie SameSite=None; Secure có luôn hoạt động trong iframe third-party không?

**Trả lời:** Không. Browser có thể chặn third-party cookie hoặc yêu cầu partitioning/permission riêng.

**Tình huống 5:** Ứng dụng chỉ dùng SameSite=Lax và có endpoint GET /transfer?to=...&amount=... thực hiện chuyển tiền. Đã an toàn CSRF chưa?

**Trả lời:** Chưa. Top-level cross-site GET có thể gửi cookie Lax. GET không được tạo side effect; thao tác chuyển tiền cần method phù hợp, CSRF defense, authorization và xác nhận giao dịch theo policy.

## 14. Ghi nhớ

**SameSite điều khiển việc browser gửi cookie theo ngữ cảnh site, không xác minh người dùng và không thay thế authorization.** Strict hạn chế cookie trong ngữ cảnh cross-site; Lax cho phép thêm một số top-level navigation an toàn; None cho phép cross-site khi có Secure và browser policy cho phép.

Để chọn đúng, hãy phân biệt site với origin, xem xét method và loại request, kiểm tra callback SSO, iframe và third-party cookie policy. Dùng SameSite cùng Secure, HttpOnly, cookie host-only, CSRF token, Origin/Fetch Metadata validation và authorization phía server. Quan trọng nhất, không tạo side effect qua GET và không coi SameSite là lớp bảo vệ duy nhất cho session.
