# SameSite và quan hệ với bảo vệ bằng token

## Mục tiêu học tập

Sau bài học thuộc chương **Cơ chế CSRF**, người học có thể:

- Giải thích thuộc tính cookie **`SameSite`** điều chỉnh việc trình duyệt gửi cookie trong ngữ cảnh cross-site như thế nào, và phân biệt nó với cơ chế **CSRF token** phía ứng dụng.
- Phân biệt **site**, **origin** và **schemeful same-site**, từ đó nhận diện các request *same-site nhưng cross-origin* vốn không được SameSite ngăn chặn.
- So sánh hành vi thường gặp của `SameSite=Strict`, `SameSite=Lax` và `SameSite=None; Secure` trong điều hướng GET, form POST, iframe, tài nguyên nhúng và JavaScript `fetch`.
- Phân tích vì sao **SameSite là lớp phòng vệ bổ sung**, không thay thế hoàn toàn synchronizer token hoặc double-submit token được thiết kế đúng.
- Cấu hình cookie phiên và CSRF token trong **Spring Security Servlet** và **Reactive/WebFlux**, phân biệt nhiệm vụ của Spring Security, Spring Boot, container và trình duyệt.
- Xử lý các ngoại lệ có chủ đích như OAuth2/OIDC redirect, ứng dụng nhiều subdomain, SPA frontend/API khác origin và nhu cầu cookie cross-site.
- Kiểm thử trong **trình duyệt thật** thay vì chỉ suy luận từ HTTP client; kết hợp `MockMvc`/`WebTestClient` để xác minh lớp kiểm tra CSRF độc lập với chính sách cookie.
- Chẩn đoán các lỗi “mất đăng nhập”, `403`, CORS, cookie bị chặn và token sai phiên sau khi đổi thuộc tính SameSite.

## 1. Hai cơ chế chống CSRF ở hai lớp khác nhau

Giả sử ứng dụng quản lý tài khoản có endpoint:

~~~http
POST /profile/email HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/x-www-form-urlencoded

email=new@example.test
~~~

Browser có thể **tự gửi session cookie** khi request được tạo từ một trang khác, nếu các quy tắc cookie cho phép. Khi đó server xác định được phiên đăng nhập A nhưng **không biết chắc đây là hành động do giao diện hợp lệ của ứng dụng chủ động gửi**.

Hai lớp phòng vệ thường được phối hợp:

1. **SameSite trên cookie xác thực:** Trình duyệt quyết định **có gửi cookie cùng request hay không** dựa trên quan hệ giữa site khởi tạo/ngữ cảnh điều hướng và site đích. Nếu cookie không được gửi, request có thể không còn credential để thực hiện thao tác dưới phiên đã xác thực.
2. **CSRF token:** Ứng dụng yêu cầu request thay đổi trạng thái mang một token được client hợp lệ **chủ động đưa vào hidden form field hoặc HTTP header**. Server kiểm chứng token này theo phiên/ngữ cảnh tin cậy. Ngay cả khi browser đã gửi cookie, một POST không có token phù hợp vẫn bị từ chối.

> **Ý chính:** SameSite kiểm soát **điều kiện gửi cookie của trình duyệt**. CSRF token kiểm tra **bằng chứng trong request ở phía server**. Chúng bảo vệ từ hai góc khác nhau, nên nên được sử dụng như các lớp **defense in depth** khi ứng dụng có credential được trình duyệt tự đính kèm.

Trong module **SPRING_SECURITY_HTTP_PROTECTION**, việc phối hợp SameSite và CSRF token là nền tảng của bảo vệ HTTP và trình duyệt, bên cạnh CORS, security headers, CSP, HSTS, HTTP firewall và quản lý session. Tư duy này áp dụng cho cả ứng dụng **Servlet** và **Reactive/WebFlux**.

## 2. Trước khi cấu hình: phân biệt origin với site

### 2.1. Origin là tổ hợp scheme, host và port

Một **origin** được xác định bởi bộ ba:

~~~text
origin = scheme + host + port
~~~

Ví dụ:

| URL | Origin |
|---|---|
| `https://app.example.com:443/profile` | `https://app.example.com:443` |
| `https://api.example.com:443/orders` | `https://api.example.com:443` |
| `https://app.example.com:8443/admin` | `https://app.example.com:8443` |
| `http://app.example.com:80` | `http://app.example.com:80` |

Hai URL khác host, port hoặc scheme là **khác origin**, kể cả khi thuộc cùng doanh nghiệp và cùng tên miền đăng ký. Same-Origin Policy và CORS thường xem xét mức **origin**.

### 2.2. Site thường dựa trên scheme và registrable domain

Đối với quy tắc **schemeful same-site** trong trình duyệt hiện đại, *site* thường được xác định từ:

~~~text
site = scheme + registrable domain
~~~

*Registrable domain* được xác định trên cơ sở Public Suffix List (PSL), không chỉ bằng cách cắt lấy hai phần cuối của hostname. Vì vậy không tự viết thuật toán “hai nhãn cuối” để xác định site. Các địa chỉ IP, `localhost` và những tên miền nằm dưới public suffix có thể cần quy tắc xác định riêng.

Trong ví dụ `example.com` là registrable domain:

| Trang khởi tạo | Đích request | Quan hệ origin | Quan hệ site |
|---|---|---|---|
| `https://app.example.com` | `https://app.example.com` | Same-origin | Same-site |
| `https://blog.example.com` | `https://app.example.com` | **Cross-origin** | **Same-site** |
| `https://ui.example.com:8443` | `https://api.example.com` | **Cross-origin** | **Same-site** nếu cùng scheme và registrable domain |
| `http://app.example.com` | `https://app.example.com` | Cross-origin | **Cross-site theo schemeful same-site** |
| `https://outside.example.net` | `https://app.example.com` | Cross-origin | Cross-site |

**Quan trọng:** Port có ý nghĩa với origin nhưng không tự làm thay đổi site. Ngược lại, **scheme HTTP/HTTPS** có ý nghĩa với site trong schemeful same-site.

### 2.3. Same-site không đồng nghĩa cùng độ tin cậy

Ứng dụng chính `https://app.example.com` có thể chia site với:

- `https://blog.example.com` do đơn vị khác vận hành;
- `https://community.example.com` cho phép nội dung người dùng;
- `https://legacy.example.com` có mức bảo vệ thấp;
- một subdomain bị chiếm quyền hoặc cấu hình sai.

Request từ `blog.example.com` tới `app.example.com` là **cross-origin nhưng same-site**, nếu scheme và registrable domain trùng. SameSite **không chặn cookie chỉ vì hai hostname khác nhau**.

Đây là giới hạn đặc biệt quan trọng: **kẻ tấn công kiểm soát một subdomain cùng site có thể có điều kiện kích hoạt request mang cookie phiên của host ứng dụng**, dù không được đọc nội dung ứng dụng đích theo Same-Origin Policy. CSRF token gắn đúng phiên tiếp tục tạo một rào cản độc lập.

### 2.4. Cookie có host-only không thì sao?

Cookie **host-only** của `app.example.com` (không có thuộc tính `Domain`) chỉ được gửi tới **host app.example.com**, chứ không được gửi tới `blog.example.com`. Nhưng nếu một trang đang mở tại `blog.example.com` kích hoạt request **đến chính `app.example.com`**, cookie host-only của `app.example.com` **vẫn có thể được gửi tới đích**.

Nói cách khác:

- **`Domain`/host-only:** quyết định **cookie có thuộc phạm vi hostname đích** hay không.
- **`SameSite`:** bổ sung kiểm tra **ngữ cảnh site khởi tạo so với site đích**.
- **CSRF token:** do server xác minh request có mang bằng chứng phù hợp hay không.

Không nên nhầm “cookie không chia sẻ với subdomain” với “subdomain không thể kích hoạt request được trình duyệt gửi tới host chính”.

## 3. Ba chế độ SameSite và hành vi thực tế

Cookie có thể được phát hành qua `Set-Cookie`:

~~~http
Set-Cookie: JSESSIONID=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

`SameSite` không phải HTTP response header độc lập; nó là **thuộc tính của từng cookie**. Browser lưu và áp dụng thuộc tính này theo ngữ cảnh request.

### 3.1. SameSite=Strict

~~~http
Set-Cookie: SESSION=opaque; Path=/; Secure; HttpOnly; SameSite=Strict
~~~

`Strict` hạn chế gửi cookie trong request được xem là **cross-site**, kể cả nhiều điều hướng cấp cao từ website khác đến ứng dụng.

**Lợi ích:** Thu hẹp các request cross-site có thể mang cookie xác thực.

**Đánh đổi UX:** Người dùng bấm một link từ email, ứng dụng chat hoặc một website khác để mở trang riêng tư trên `app.example.com` có thể thấy mình **chưa đăng nhập trong request điều hướng đầu tiên**, dù cookie vẫn tồn tại trong browser. Khi đã ở trong site đích, những request same-site tiếp theo có thể mang cookie như bình thường. Hành vi chi tiết phụ thuộc browser và luồng điều hướng.

`Strict` không chặn POST bắt nguồn từ một subdomain **same-site** ít tin cậy. Nó cũng không thay thế xác minh CSRF token và không ngăn một request có thể thay đổi trạng thái được thực thi khi cookie được gửi trong cùng site.

### 3.2. SameSite=Lax

~~~http
Set-Cookie: SESSION=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

`Lax` là lựa chọn phổ biến cân bằng giữa hạn chế cookie cross-site và trải nghiệm điều hướng:

- Thường **không gửi cookie** với cross-site form POST hoặc các request tài nguyên nhúng/call subresource cross-site.
- Thường **cho phép cookie** trong điều hướng cấp cao (*top-level navigation*) cross-site sử dụng phương thức an toàn như **GET**.
- Với request **same-site**, `Lax` không chặn cookie chỉ vì nó dùng POST.

Hệ quả nổi bật: **GET không được thay đổi trạng thái nghiệp vụ**. Nếu `GET /logout` thực hiện đăng xuất ngay hoặc `GET /orders/42/approve` duyệt đơn, một link từ site ngoài có thể dẫn đến tác động khi cookie Lax được gửi trong điều hướng GET.

Lưu ý quan trọng về browser: một số implementation có chế độ tương thích như **Lax-allowing-unsafe** áp dụng tạm thời cho cookie **không khai báo SameSite** mới được tạo, ví dụ một khoảng thời gian ngắn sau khi phát hành. Cơ chế này **không tương đương** `SameSite=Lax` được khai báo rõ và không phải cam kết đồng nhất cho mọi browser. Do đó không được dựa vào việc mặc định thiếu thuộc tính hoặc một thử nghiệm POST đơn lẻ để kết luận an toàn.

### 3.3. SameSite=None; Secure

~~~http
Set-Cookie: SESSION=opaque; Path=/; Secure; HttpOnly; SameSite=None
~~~

`None` thể hiện ứng dụng muốn browser **có thể gửi cookie cả trong ngữ cảnh cross-site**, miễn đáp ứng phạm vi cookie và các chính sách khác. Trong trình duyệt hiện đại, `SameSite=None` phải đi kèm **`Secure`**.

Dùng trong những kiến trúc thực sự cần cookie trong iframe, một số luồng tích hợp cross-site hoặc frontend/backend nằm trên hai site khác nhau. Nhưng:

- `None` **không bảo đảm** cookie luôn được gửi: browser có thể hạn chế cookie bên thứ ba, áp dụng chính sách riêng hoặc người dùng chặn cookie.
- `Secure` yêu cầu kết nối an toàn thích hợp, thường là HTTPS; nó **không** tạo CSRF token.
- Nếu cookie đó là **credential xác thực**, việc cho phép cross-site có thể làm tăng diện tấn công CSRF. Cần kiểm tra token và các biện pháp bổ sung phù hợp.

### 3.4. Không khai báo SameSite không phải một thiết kế bảo mật

Một số browser áp dụng mặc định gần với `Lax` khi cookie không khai báo SameSite; các browser khác, phiên bản khác hoặc công cụ HTTP có thể cư xử khác. Những khác biệt và ngoại lệ tương thích càng khiến hành vi khó dự đoán.

Trong production nên **khai báo thuộc tính có chủ đích** cho từng cookie, kiểm thử với những browser mà sản phẩm hỗ trợ, và không xem một mặc định browser như lớp phòng vệ duy nhất.

## 4. Ma trận trực quan: trường hợp nào gửi session cookie?

Giả định cookie thuộc `https://app.example.com`, có `Secure` và các quy tắc hostname/path phù hợp; không có chặn cookie bên thứ ba hoặc chính sách bất thường khác. Bảng mô tả **hành vi thường gặp**, không phải lời hứa cho mọi browser.

| Ngữ cảnh request | `Strict` | `Lax` | `None; Secure` |
|---|---|---|---|
| Từ chính `https://app.example.com` gửi POST | Có | Có | Có |
| Từ `https://blog.example.com` gửi POST đến `https://app.example.com` (same-site, cross-origin) | Có | Có | Có |
| Từ `https://other.test` mở **top-level navigation GET** đến `app.example.com` | Thường **không** | Thường **có** | Có nếu browser cho phép |
| Từ `https://other.test` gửi **top-level form POST** đến `app.example.com` | Không | Thường **không** | Có nếu browser cho phép |
| Từ `https://other.test` tải ảnh/iframe GET từ `app.example.com` | Không | Thường **không** | Có nếu browser cho phép |
| Từ `https://other.test` dùng `fetch` cross-origin đến `app.example.com` | Không | Không | Chỉ khi credentials/CORS/cookie policy cho phép |
| Từ `http://app.example.com` đến `https://app.example.com` (khác scheme, schemeful cross-site) | Theo quy tắc cross-site | Theo quy tắc cross-site | Theo quy tắc cross-site và `Secure` |

Ở dòng `fetch`: trình duyệt có chế độ `credentials` riêng. Với `fetch` cross-origin, mặc định `credentials: "same-origin"` **không gửi cookie** dù SameSite cho phép. Để yêu cầu browser cân nhắc gửi cookie, thường cần `credentials: "include"`, nhưng nó **không vượt qua** SameSite, `Secure` hoặc chính sách chặn cookie.

### 4.1. Sơ đồ ra quyết định

~~~mermaid
flowchart TD
    A[Browser chuẩn bị gửi request] --> B{Cookie khớp domain/path và các quy tắc khác?}
    B -- Không --> X[Không gửi cookie]
    B -- Có --> C{Request same-site?}
    C -- Có --> G[SameSite không ngăn cookie]
    C -- Không --> D{Cookie SameSite?}
    D -- Strict --> X
    D -- Lax --> E{Điều hướng cấp cao với safe method?}
    E -- Có --> G
    E -- Không --> X
    D -- None --> F{Secure và chính sách browser cho phép?}
    F -- Có --> G
    F -- Không --> X
    G --> H[Tiếp tục xét credentials mode, cookie policy và gửi request]
~~~

Sơ đồ giản lược để học quy tắc. Browser còn có quy định về cookie partitioning, policy và các đặc tính ngữ cảnh như nested navigation; biểu đồ không thay việc kiểm thử thật.

## 5. Vì sao SameSite không thể thay thế hoàn toàn CSRF token?

### 5.1. Rủi ro same-site nhưng cross-origin

Kịch bản:

- Ứng dụng ngân hàng ở `https://bank.example.com`, dùng session cookie `SameSite=Strict`.
- Một subdomain `https://promo.example.com` bị chiếm quyền.
- Attacker tạo form POST từ `promo.example.com` đến `bank.example.com`.

Cả hai hostname có cùng scheme và registrable domain `example.com`, nên browser có thể coi request là **same-site**. Cookie Strict/Lax của `bank.example.com` có thể được gửi **đến bank.example.com** nếu khớp các quy tắc cookie khác.

~~~html
<!-- Minh họa request giả mạo từ một origin khác nhưng cùng site. -->
<form method="post" action="https://bank.example.com/profile/email">
  <input type="hidden" name="email" value="attacker@example.test">
</form>
<script>
  document.forms[0].submit();
</script>
~~~

Attacker không vì thế mà được đọc DOM/form hợp lệ do `bank.example.com` phát hành. Nếu ứng dụng **yêu cầu CSRF token gắn với phiên**, POST do attacker tạo thường thiếu token hợp lệ và bị từ chối.

**Bài học:** SameSite kiểm tra site, **không** kiểm tra origin chính xác. Một site có subdomain ít tin cậy không nên dựa duy nhất vào SameSite để bảo vệ request có tác động.

### 5.2. Rủi ro GET làm thay đổi trạng thái

`SameSite=Lax` thường cho phép cookie trong top-level GET cross-site. Nếu server dùng GET để xóa, đổi email, chuyển tiền, duyệt đơn hoặc logout, một link ngoài site có thể kích hoạt thao tác.

Spring Security mặc định thường **không yêu cầu CSRF token đối với GET** vì HTTP định nghĩa GET là phương thức an toàn. Cách sửa đúng là **đưa hành động sang POST/PUT/PATCH/DELETE phù hợp**, không chỉ cấu hình SameSite hoặc nhét token vào query string.

### 5.3. Login CSRF trước khi có phiên xác thực

Một trang bên ngoài có thể thử gửi form `POST /login` chứa **credential của tài khoản attacker** để khiến nạn nhân đăng nhập vào tài khoản đó.

Ở đây POST login có thể **tạo ra session mới**, nên việc cookie phiên hiện tại không được gửi vì SameSite chưa đủ để khẳng định login CSRF không xảy ra. Server cần bảo vệ request login theo luồng của mình; với form login Spring Security, POST login thường được yêu cầu **CSRF token từ trang login hợp lệ**, kể cả khi người dùng chưa xác thực.

Kết quả có thể là nạn nhân vô tình dùng tài khoản attacker và lưu dữ liệu vào nơi attacker xem được. Đây không phải trường hợp attacker tự động chiếm tài khoản nạn nhân; cơ chế đe dọa khác.

### 5.4. Có thể cần SameSite=None cho chức năng hợp lệ

Một tích hợp cross-site có thể buộc ứng dụng dùng `SameSite=None; Secure`. Khi đó browser có thể gửi cookie xác thực trong các ngữ cảnh attacker cũng có thể tạo request, nếu các chính sách khác cho phép.

CSRF token cung cấp một ranh giới **kiểm chứng phía server** không phụ thuộc hoàn toàn vào việc browser loại cookie. Khi cần `None`, lớp CSRF token càng quan trọng.

### 5.5. Browser không thống nhất tuyệt đối

Cùng một ứng dụng có thể chạy trên Chrome, Firefox, Safari, browser nhúng, môi trường enterprise hoặc hệ thống tự động. Chính sách cookie, chặn third-party cookies, hành vi SameSite mặc định và ngoại lệ tương thích có thể khác nhau.

CSRF token là kiểm tra **do ứng dụng thực thi** trên những request đã đến server, giúp giảm phụ thuộc vào một hành vi cookie browser cụ thể. Tuy nhiên token vẫn cần được cấp và kiểm tra đúng, tránh rò rỉ qua XSS và không phải biện pháp độc lập trước mọi tấn công.

## 6. Hai lớp tương tác với nhau như thế nào?

### 6.1. Synchronizer Token Pattern

Với ứng dụng dùng `HttpSession` hoặc `WebSession`:

1. Server phát CSRF token đủ khó đoán và lưu theo phiên.
2. Trang hợp lệ nhận token qua HTML/form hoặc API phù hợp.
3. Browser gửi session cookie theo SameSite/cookie policy.
4. Form hoặc JavaScript **chủ động gửi** CSRF token qua trường `_csrf` hoặc header.
5. Server tra expected token **theo phiên hiện tại** và so với token đã gửi.

Ví dụ POST hợp lệ:

~~~http
POST /profile/email HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/x-www-form-urlencoded

email=alice@example.test&_csrf=TOKEN_CUA_PHIEN_A
~~~

Nếu browser không gửi cookie session vì SameSite, ứng dụng có thể xem request là anonymous và từ chối/đưa về login. Nếu browser **có gửi** cookie nhưng POST **thiếu/sai token**, `CsrfFilter`/`CsrfWebFilter` vẫn từ chối theo cấu hình.

### 6.2. Double-submit cookie

Một số SPA nhận một cookie CSRF riêng, ví dụ:

~~~http
Set-Cookie: XSRF-TOKEN=random-csrf-token; Path=/; Secure; SameSite=Lax
~~~

Client hợp lệ đọc token qua một kênh cho phép, rồi gửi lại:

~~~http
POST /api/preferences HTTP/1.1
Host: app.example.com
Cookie: SESSION=authenticated-session; XSRF-TOKEN=random-csrf-token
X-XSRF-TOKEN: random-csrf-token
Content-Type: application/json

{"theme":"dark"}
~~~

Có **hai cookie với hai nhiệm vụ**:

- `SESSION` hoặc cookie chứa access token: **credential xác thực** mà browser có thể tự gửi.
- `XSRF-TOKEN`: cookie chuyên dùng để cung cấp/đối chiếu token CSRF theo mô hình repository.

Trình duyệt cũng áp dụng SameSite cho **cookie CSRF**, độc lập với SameSite của cookie phiên. Vì vậy một request có thể nhận cookie session nhưng không nhận cookie CSRF, hoặc ngược lại, nếu thuộc tính và ngữ cảnh khác nhau.

**Lưu ý bảo mật:** Một double-submit cookie **naive** chỉ so cookie với header/form có thể yếu trước **cookie injection** (ví dụ từ subdomain có khả năng đặt cookie với `Domain=example.com`). Biến thể mạnh dùng **token có chữ ký HMAC gắn với phiên** và chính sách cookie host-only phù hợp. `SameSite` và `CookieCsrfTokenRepository` thông thường **không tự biến** double-submit thành signed session-bound token.

### 6.3. Không nhầm SameSite với token masking

Spring Security hiện đại có thể sử dụng XOR masking khi render CSRF token để giảm nguy cơ BREACH. Việc chuỗi token trong form **thay đổi qua mỗi lần render** không đồng nghĩa session cookie SameSite đã thay đổi hoặc raw CSRF token trong repository đã được luân phiên.

Cần phân biệt ba lớp:

| Cơ chế | Giải quyết vấn đề gì? |
|---|---|
| `SameSite` | Browser có gửi cookie trong ngữ cảnh site hiện tại hay không |
| Token repository + CSRF filter | Server có chấp nhận request thay đổi trạng thái dựa trên token hợp lệ hay không |
| XOR masking/token request handler | Cách biểu diễn/giải mã CSRF token khi đưa ra response và nhận lại request |

## 7. Các thuộc tính cookie khác cần đi kèm SameSite

| Thuộc tính | Vai trò | Quan hệ với CSRF |
|---|---|---|
| `Secure` | Hạn chế cookie qua kết nối an toàn thích hợp | Cần cho `SameSite=None` và môi trường HTTPS; không tự kiểm chứng CSRF |
| `HttpOnly` | Ngăn JavaScript thông thường đọc cookie bằng `document.cookie` | Phù hợp với **cookie phiên xác thực**; không ngăn browser tự gửi cookie |
| `Domain` | Xác định phạm vi hostname; có thể mở rộng sang subdomain | Mở quá rộng có thể tăng nguy cơ cookie injection/trộn ranh giới tin cậy |
| `Path` | Giới hạn đường dẫn nhận cookie | Không phải ranh giới bảo mật đủ mạnh giữa các ứng dụng cùng host |
| `SameSite` | Giới hạn cookie theo site của request | Lớp phòng vệ hỗ trợ, không thay token |
| `Max-Age`/`Expires` | Vòng đời cookie trong browser | Không thay chính sách hủy phiên/token phía server |
| Tiền tố `__Host-` | Cookie phải có `Secure`, `Path=/`, không có `Domain` trong browser hỗ trợ | Hạn chế subdomain đặt cookie tiền tố đó cho host cha; hữu ích cho phạm vi cookie |
| Tiền tố `__Secure-` | Cookie phải có `Secure` trong browser hỗ trợ | Không ép host-only; yếu hơn `__Host-` về cookie scope |

Một cấu hình cookie phiên điển hình có thể là:

~~~http
Set-Cookie: __Host-SESSION=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Không khai báo `Domain` giúp cookie host-only. Nếu dùng tiền tố `__Host-`, phải đáp ứng đúng các điều kiện của browser. Cần kiểm tra tên cookie mà **session resolver/container** thực sự sử dụng thay vì đổi tên trên tài liệu mà không đổi cấu hình.

**Không nên** áp `HttpOnly` cho cookie CSRF mà SPA **bắt buộc** phải đọc qua `document.cookie`, nếu không có kênh cấp token khác. Cookie xác thực và cookie CSRF cần được cấu hình **riêng theo chức năng**.

## 8. Cấu hình trên Spring Security Servlet

### 8.1. SameSite thường là cấu hình cookie/session, không phải `CsrfFilter`

Spring Security Servlet phụ trách **CSRF request verification** qua `CsrfFilter` và token repository; thuộc tính `SameSite` của session cookie có thể được cấu hình tại Spring Boot, container hoặc Spring Session.

Nếu ứng dụng dùng Spring Boot với Servlet container và phiên bản hỗ trợ các thuộc tính sau, có thể cấu hình:

~~~yaml
# application.yml — ví dụ Spring Boot Servlet chạy HTTPS
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Cần quan sát `Set-Cookie` thực tế:

~~~http
Set-Cookie: JSESSIONID=...; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

**Quan trọng:**

- `same-site: lax` định cấu hình cookie, **không kích hoạt hoặc thay thế kiểm tra CSRF token**.
- `secure: true` phù hợp khi client dùng HTTPS; nếu thử nghiệm qua HTTP thông thường, cookie có thể không được gửi như mong đợi. Ở hệ thống có reverse proxy TLS termination, phải kiểm tra forward headers và cấu hình container để browser nhận đúng cookie.
- Nếu sử dụng **Spring Session** hoặc custom cookie serializer, cơ chế phát cookie của Spring Session có thể cần cấu hình riêng và có thể khác cơ chế `server.servlet.session.cookie`.
- Tên cookie, `Domain` và `Path` cần kiểm chứng từ response thực, không suy đoán chỉ từ file cấu hình.

### 8.2. CSRF token theo session vẫn được kiểm chứng độc lập

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(new HttpSessionCsrfTokenRepository()))
            .build();
    }
}
~~~

Ở đây:

- **Cookie SameSite** được áp dụng bởi **browser** khi gửi session ID.
- `HttpSessionCsrfTokenRepository` lưu expected CSRF token theo phiên.
- `CsrfFilter` kiểm tra submitted CSRF token ở các request cần bảo vệ, không giả định browser luôn áp dụng một chính sách SameSite nhất định.

Spring Security thường bật CSRF theo mặc định cho cấu hình web session thông dụng; repository tường minh được ghi ra để giải thích mô hình.

### 8.3. Form POST với CSRF token

Với Spring MVC + Thymeleaf:

~~~html
<!-- GET /profile/edit chỉ trả trang đọc/form -->
<form action="/profile/email" method="post">
  <label for="email">Email mới</label>
  <input id="email" name="email" type="email" required>

  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">

  <button type="submit">Cập nhật email</button>
</form>
~~~

Dùng token thực từ request attribute `_csrf`, **không** tự gắn session ID vào form, cũng không hardcode token. Với `th:action` và một số tích hợp form, framework có thể tự thêm hidden CSRF field; hãy kiểm tra HTML cuối cùng để không sinh trường trùng.

Controller POST thực hiện nghiệp vụ sau khi security filter kiểm chứng:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;

@Controller
class ProfileController {

    @GetMapping("/profile/edit")
    String showForm() {
        return "profile/edit";
    }

    @PostMapping("/profile/email")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void updateEmail(@RequestParam String email) {
        // Service thật phải xác định user hiện tại,
        // kiểm tra quyền, validate và ghi dữ liệu.
    }
}
~~~

Ngay cả khi cookie `SameSite=Lax` chặn phần lớn cross-site POST, server vẫn **đòi token**. Nếu attacker có đường gửi request *same-site* từ subdomain bị chiếm quyền, việc kiểm tra token vẫn có giá trị.

### 8.4. Khi dùng CookieCsrfTokenRepository cho SPA

Spring Security Servlet cũng có `CookieCsrfTokenRepository`:

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

CookieCsrfTokenRepository repository =
        CookieCsrfTokenRepository.withHttpOnlyFalse();
~~~

Repository này phục vụ luồng client đọc token từ cookie rồi gửi token bằng header (thường `X-XSRF-TOKEN`). Cấu hình `withHttpOnlyFalse()` dùng cho cookie CSRF cần đọc bằng JavaScript, **không áp cho session cookie xác thực**.

Cookie `XSRF-TOKEN` có thể có `SameSite` riêng. Cần kiểm tra phạm vi `Domain`/`Path` và nguy cơ cookie injection. Ở các phiên bản Spring Security Servlet có XOR masking mặc định, SPA gửi token raw từ cookie qua header có thể cần `CsrfTokenRequestHandler` phù hợp; không giải quyết bằng cách tắt CSRF trên API có cookie xác thực.

## 9. Cấu hình trên Spring Security Reactive/WebFlux

### 9.1. Giữ kiểm tra CSRF với WebSession

WebFlux sử dụng `CsrfWebFilter`, `ServerHttpSecurity` và các `ServerCsrfTokenRepository`, ví dụ `WebSessionServerCsrfTokenRepository`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(authorize -> authorize
                .pathMatchers("/assets/**").permitAll()
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(new WebSessionServerCsrfTokenRepository()))
            .build();
    }
}
~~~

Nếu request có cookie `SESSION` hợp lệ và gửi POST, server vẫn yêu cầu submitted token từ form/header theo chính sách CSRF. Nếu cookie bị SameSite chặn, request có thể không còn ngữ cảnh đăng nhập, nhưng **đó là kết quả ở lớp cookie**, không phải bằng chứng đã kiểm tra CSRF token.

### 9.2. Cấu hình SameSite cho cookie WebSession

Với Spring WebFlux có `CookieWebSessionIdResolver` và API `addCookieInitializer`, có thể tùy chỉnh cookie được phát hành:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration
class WebSessionCookieConfig {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
                new CookieWebSessionIdResolver();

        resolver.setCookieName("SESSION");
        resolver.addCookieInitializer(cookie -> cookie
                .path("/")
                .httpOnly(true)
                .secure(true)
                .sameSite("Lax"));

        return resolver;
    }
}
~~~

Đây là minh họa cho ứng dụng WebFlux chạy **HTTPS** và phiên bản Spring Framework hỗ trợ API tương ứng. Cần kiểm tra xem Spring Boot, Spring Session hoặc một custom resolver có đang quản lý cookie thay cho bean này hay không; không mặc định mọi ứng dụng Reactive đều dùng cùng một resolver.

Trong production cần kiểm tra response:

~~~http
Set-Cookie: SESSION=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

`SameSite=Lax` được gửi như **cookie attribute**; nó không phải một lựa chọn trực tiếp của `CsrfWebFilter`. Nếu ứng dụng nhận WebSession từ browser, CSRF token gắn WebSession vẫn là lớp bảo vệ cần thiết cho unsafe request.

### 9.3. Template và Reactive CSRF token

WebFlux có thể cung cấp `Mono<CsrfToken>` trong `ServerWebExchange` để view lấy token:

~~~java
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.reactive.result.view.Rendering;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Controller
class ReactiveProfilePage {

    @GetMapping("/profile/edit")
    Mono<Rendering> edit(ServerWebExchange exchange) {
        Mono<CsrfToken> csrf =
                exchange.getAttribute(CsrfToken.class.getName());

        return csrf.map(token ->
            Rendering.view("profile/edit")
                .modelAttribute("_csrf", token)
                .build());
    }
}
~~~

Đoạn trên giả định request đã đi qua `CsrfWebFilter` và exchange attribute có token publisher. View render token vào form tương ứng. Trong hệ thống thật, cơ chế template/request handler có thể tự cấp token; không tự sinh token ngẫu nhiên trong controller để thay thế repository.

### 9.4. Cookie CSRF trên Reactive

`CookieServerCsrfTokenRepository` hỗ trợ token CSRF dựa trên cookie trong WebFlux. Cũng như phía Servlet, điều đó **không tự thay** việc cần phân tích SameSite của cookie **xác thực**, phạm vi cookie CSRF, CORS của SPA hoặc nguy cơ cookie injection.

Nếu frontend cùng site nhưng khác origin, cần kiểm tra thật cách SPA lấy token và gửi header. Token raw đọc từ cookie có thể đòi request handler tương thích với repository và Spring Security version đang dùng.

## 10. SPA, CORS và luồng khác origin

### 10.1. Same-site nhưng cross-origin

Ví dụ frontend ở `https://ui.example.com`, API ở `https://api.example.com`:

- Hai origin **khác nhau** nhưng có thể **cùng site**.
- `SameSite=Lax` của cookie API **không chặn** chỉ vì origin khác.
- Tuy nhiên, `fetch` cross-origin **không tự gửi credential theo mặc định**; cần `credentials: "include"` nếu muốn browser cân nhắc gửi cookie.
- API phải cấu hình CORS cho origin thực sự tin cậy, phương thức, header và credentials khi cần.
- Cookie host-only của `api.example.com` vẫn được gửi **đến API**, nhưng JavaScript chạy ở `ui.example.com` không đọc được cookie host-only của API qua `document.cookie`.

Ví dụ request từ một frontend đã có CSRF token hợp lệ bằng kênh ứng dụng thiết kế:

~~~javascript
const token = getCsrfTokenFromApplication(); // Ví dụ: từ HTML/endpoint được phép.

const response = await fetch("https://api.example.com/profile/email", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": token
  },
  body: JSON.stringify({ email: "alice@example.test" })
});

if (!response.ok) {
  throw new Error("Không cập nhật được: HTTP " + response.status);
}
~~~

Hàm `getCsrfTokenFromApplication()` ở đây là **placeholder mô tả kênh cấp token cần được thiết kế**, không phải API có sẵn của JavaScript/Spring Security. Không sao chép ví dụ rồi cho rằng frontend khác origin tự đọc được cookie API.

### 10.2. Cross-site thật sự

Frontend `https://portal.other.test` và API `https://api.example.com` là cross-site. Nếu API dựa vào cookie xác thực, `SameSite=Strict` và `Lax` thường làm cookie không đi cùng cross-site POST từ JavaScript.

Nếu nghiệp vụ thật sự cần request có credential:

- Có thể phải dùng `SameSite=None; Secure` trên cookie thích hợp.
- Cần `credentials: "include"` ở client và CORS response tương ứng.
- Browser vẫn có thể chặn cookie bên thứ ba dù SameSite=None.
- Server **vẫn cần CSRF token** khi credential có thể được browser tự gửi.
- Không cấu hình `Access-Control-Allow-Origin: *` kết hợp credentialed CORS response; chỉ cho phép những origin được kiểm soát theo chính sách.

Không biến `SameSite=None` thành một “cách sửa mọi lỗi CORS”. Nó chỉ điều chỉnh một điều kiện cookie; CORS là chính sách khác và CSRF là bước kiểm chứng request ở server.

### 10.3. Tại sao CORS không thay SameSite hoặc CSRF?

| Cơ chế | Câu hỏi được trả lời |
|---|---|
| SameSite | Browser có gửi cookie trong ngữ cảnh site này không? |
| CORS | JavaScript ở origin A có được gọi/đọc phản hồi từ origin B theo chính sách trình duyệt không? |
| CSRF token | Request thay đổi trạng thái có mang token mà server chấp nhận theo ngữ cảnh phù hợp không? |
| Authentication/authorization | Người dùng/client là ai, và có quyền thực hiện thao tác không? |
| CSP | Trang được phép chạy/tải script và tài nguyên từ đâu? |

CORS có thể yêu cầu **preflight** với những request JavaScript cross-origin có header `X-CSRF-TOKEN`. Tuy nhiên một HTML form đơn giản có thể gửi POST cross-site **không cần preflight**. Nếu server đã nhận POST có cookie mà không bảo vệ CSRF, việc JavaScript trang ngoài không được đọc response **không ngăn thay đổi trạng thái**.

## 11. OAuth2/OIDC, login và các ngoại lệ SameSite

### 11.1. Điều hướng từ Identity Provider về ứng dụng

Một ứng dụng đăng nhập bằng OAuth2/OIDC thường đưa người dùng từ `app.example.com` sang Identity Provider rồi điều hướng về callback của ứng dụng.

Nếu cookie ứng dụng dùng `SameSite=Strict`, điều hướng từ Identity Provider **cross-site** về ứng dụng có thể không mang cookie cần cho phiên đăng nhập chưa hoàn tất. Điều này có thể làm sai cơ chế đối chiếu `state`/authentication request hoặc khiến người dùng có cảm giác bị mất phiên, tùy cách ứng dụng lưu trạng thái.

`SameSite=Lax` thường phù hợp hơn với các luồng **top-level GET redirect** cross-site. Nhưng khi sử dụng **response_mode=form_post** hoặc các callback POST cross-site, `Lax` thường không gửi cookie tương ứng; có thể phải dùng một cơ chế cookie/phiên hoặc cấu hình khác cho luồng đó.

### 11.2. OAuth state/PKCE không phải CSRF token cho mọi nghiệp vụ

Trong OAuth2/OIDC, `state` giúp liên kết authorization request/response và chống những kiểu CSRF/tráo luồng tại callback; PKCE giúp ràng buộc authorization code với client khởi tạo. Các cơ chế này bảo vệ **giao thức đăng nhập/ủy quyền**.

Sau khi người dùng đăng nhập, request `POST /profile/email` dựa trên cookie phiên **vẫn cần bảo vệ CSRF riêng phù hợp**. Không kết luận “đã có OAuth state nên mọi POST nghiệp vụ không cần CSRF token”.

### 11.3. Login CSRF và logout CSRF

Ngay cả khi browser không gửi cookie phiên trong cross-site POST do SameSite, **POST login** vẫn có thể là thao tác tạo session mới. Login CSRF có thể khiến người dùng đăng nhập vào tài khoản attacker nếu ứng dụng không bảo vệ request login đúng cách.

Với **logout**, một GET thực hiện đăng xuất ngay là thiết kế yếu, đặc biệt vì `SameSite=Lax` có thể gửi cookie trong top-level GET. Spring Security khi bật CSRF thường yêu cầu **POST /logout có token**, còn GET `/logout` trong các luồng mặc định có thể chỉ là trang xác nhận.

Không “khắc phục” logout bị chặn bằng cách cho phép GET logout trực tiếp hoặc tắt CSRF toàn cục.

## 12. Kiểm thử: chia rõ hai nhóm câu hỏi

Một bộ test tốt phải tách bạch:

1. **Cookie/browser layer:** Browser có hay không gửi cookie theo `SameSite`, ngữ cảnh site và loại request?
2. **Server CSRF layer:** Nếu request đến server, token thiếu/sai/của phiên khác có bị từ chối không?

Một test `MockMvc` hoặc `WebTestClient` có thể chứng minh filter CSRF đang hoạt động, nhưng **không tự mô phỏng đầy đủ browser áp dụng SameSite**. Ngược lại, một test trên browser thấy cookie không được gửi không chứng minh rằng server vẫn an toàn khi cookie được gửi từ ngữ cảnh khác.

### 12.1. Ma trận E2E cho browser

Đặt ứng dụng test trên HTTPS có ít nhất ba origin:

~~~text
https://app.example.test        # Ứng dụng đích
https://blog.example.test       # Khác origin, same-site (nếu cùng scheme)
https://attacker.other.test     # Cross-site
~~~

Các tên trên là **mô hình cấu hình cho môi trường thử nghiệm**, phải có DNS/hosts, certificate và mapping phù hợp; không giả định những hostname đó tự hoạt động trên Internet.

| Ca thử | Nguồn → đích | Method/ngữ cảnh | Cookie `Strict` | Cookie `Lax` | Điều cần xác minh thêm |
|---|---|---|---|---|---|
| A | app → app | Form POST cùng origin | Có | Có | Token đúng vượt CSRF; thiếu token bị từ chối |
| B | blog → app | Form POST same-site cross-origin | Thường có | Thường có | **Thiếu token vẫn phải bị chặn** |
| C | attacker → app | Top-level GET navigation | Thường không | Thường có | GET không được thay trạng thái |
| D | attacker → app | Cross-site form POST | Không | Thường không | Cookie vắng mặt không thay cho test token |
| E | attacker → app | Cross-site iframe/ảnh GET | Không | Thường không | `None` có thể cho cookie nếu browser cho phép |
| F | app → app | POST sau login/logout đổi phiên | Có | Có | Token cũ bị từ chối nếu đã vô hiệu hóa |
| G | portal site khác → app | Cross-site fetch POST | Không | Không | `None`, credentials, CORS và CSRF đều cần đúng |

Đối với `SameSite=None; Secure`, nhiều browser có thể gửi cookie ở các trường hợp cross-site **nếu** third-party cookie policy và các điều kiện khác cho phép. Kết quả của test phải bao gồm **request Cookie header thực tế**, không chỉ quan sát status response.

### 12.2. Quy trình kiểm tra bằng DevTools

Trong một ứng dụng thử nghiệm được phép:

1. **Quan sát response login:** Kiểm tra `Set-Cookie` của cookie xác thực, nhất là `SameSite`, `Secure`, `HttpOnly`, `Domain`, `Path`.
2. **Mở request từ same-site subdomain:** Trên `blog.example.test`, gửi POST đến app test. Xác nhận browser có gửi cookie phiên hay không, đồng thời server từ chối request không có CSRF token.
3. **Mở link GET từ website khác site:** Kiểm tra `Lax` có gửi cookie trong top-level navigation hay không; quan trọng hơn, GET không gây thay đổi nghiệp vụ.
4. **Gửi cross-site POST:** Quan sát cookie bị loại với Strict/Lax; không kết luận cơ chế CSRF server an toàn chỉ vì cookie bị loại.
5. **Thử token thiếu và sai:** Trong một request **đã chắc chắn mang credential phiên**, xóa header/form CSRF hoặc sửa token; phải bị từ chối nếu request thuộc phạm vi CSRF.
6. **Thử OAuth/SSO:** Quan sát cookie trong redirect callback GET hoặc POST; kiểm tra `state`/PKCE và việc giữ đúng phiên đăng nhập.
7. **Thử SPA khác origin:** Phân biệt preflight CORS, lỗi cookie không gửi, và POST có cookie nhưng bị `403` do token.
8. **Thử browser khác nhau:** Ít nhất các browser mục tiêu của sản phẩm và chế độ chặn third-party cookie, nếu nghiệp vụ sử dụng cross-site cookie.

Ở production, không gửi credential hoặc CSRF token thật vào công cụ telemetry hay chia sẻ bản ghi HAR công khai. Cần che token/cookie khi lưu phục vụ chẩn đoán.

### 12.3. Kiểm thử lớp CSRF Servlet bằng MockMvc

Giả định ứng dụng Spring MVC có `POST /profile/email` và sau khi xử lý thành công trả `204 No Content`. Với `spring-security-test`, ta có thể kiểm tra bước CSRF:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SameSiteAndCsrfServletTests {

    @Autowired MockMvc mvc;

    @Test
    void unsafeRequestWithoutTokenIsRejected() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .param("email", "alice@example.test"))
            .andExpect(status().isForbidden());
    }

    @Test
    void unsafeRequestWithInvalidTokenIsRejected() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .with(csrf().useInvalidToken())
                .param("email", "alice@example.test"))
            .andExpect(status().isForbidden());
    }

    @Test
    void unsafeRequestWithTokenCanPassCsrf() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .with(csrf())
                .param("email", "alice@example.test"))
            .andExpect(status().isNoContent());
    }
}
~~~

`with(user("alice"))` là mock authentication; nó **không nhất thiết tạo cookie như browser thật**. Các test này xác minh **server-side token check**, không chứng minh `SameSite=Lax` hay `Strict` được browser áp dụng. Muốn chứng minh ràng buộc phiên, cần test tích hợp với hai session A/B và thử dùng token A trong session B.

### 12.4. Kiểm thử lớp CSRF Reactive bằng WebTestClient

Giả định WebFlux có endpoint tương ứng trả `204` và request đi qua Spring Security:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class SameSiteAndCsrfReactiveTests {

    @Autowired ApplicationContext context;

    private WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void csrfTokenStillRequiredForPost() {
        client().mutateWith(mockUser("alice"))
            .post().uri("/profile/email")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void validTokenPassesCsrfLayer() {
        client().mutateWith(mockUser("alice"))
            .mutateWith(csrf())
            .post().uri("/profile/email")
            .exchange()
            .expectStatus().isNoContent();
    }
}
~~~

Test cuối yêu cầu endpoint và request body phù hợp với ví dụ; nếu handler bắt buộc body hoặc có kiểm tra nghiệp vụ khác, điều chỉnh request/expectation. Nó chứng minh CSRF WebFilter hoạt động, **không kiểm chứng trực tiếp cookie SameSite**.

### 12.5. Vì sao cURL/Postman không đủ để kiểm tra SameSite?

Công cụ HTTP có thể chủ động viết:

~~~http
Cookie: JSESSIONID=SESSION_A
~~~

bất kể request xuất phát từ origin nào. Nó không nhất thiết tái hiện việc browser **tự quyết định gửi hay bỏ cookie** theo `SameSite`.

Vì vậy:

- Dùng cURL/Postman để **kiểm tra logic server**: CSRF token, xác thực, quyền, mã lỗi.
- Dùng browser automation hoặc DevTools để **kiểm tra chính sách cookie** trong ngữ cảnh cross-site/same-site thật.
- Kết hợp hai lớp kiểm thử thay vì chỉ chọn một.

## 13. Chẩn đoán lỗi khi triển khai SameSite cùng CSRF

| Hiện tượng | Giải thích có thể | Hướng điều tra/khắc phục |
|---|---|---|
| Bấm link từ email vào app thì như chưa đăng nhập | Cookie `Strict` không được gửi trong điều hướng cross-site đầu tiên | Kiểm tra top-level GET và cân nhắc `Lax` nếu UX cần |
| SPA khác origin POST trả `401` | `fetch` không gửi cookie do `credentials`, cookie scope hoặc SameSite | Kiểm tra Cookie header thật, host, scheme và credentials |
| SPA POST có cookie nhưng trả `403` | Token CSRF thiếu/sai/hết hạn hoặc không đúng phiên | Kiểm tra form/header, repository và handler; đừng tắt CSRF |
| Browser báo lỗi preflight | CORS policy không cho origin/method/header/credentials | Xử lý CORS riêng, không coi là lỗi SameSite hoặc CSRF |
| Cookie `SameSite=None` không được lưu/gửi | Thiếu `Secure`, không HTTPS hoặc third-party cookie policy | Kiểm tra cảnh báo cookie trong browser; dùng HTTPS và thiết kế fallback |
| Redirect OAuth trả về mất state/phiên | Cookie Strict hoặc callback POST không tương thích Lax | Xem lại redirect mode, site context và cách lưu authorization request |
| `Lax` vẫn gửi cookie từ subdomain lạ | Request là **same-site** dù cross-origin | Giữ CSRF token và phân vùng subdomain tin cậy |
| GET từ site khác gây logout | Endpoint GET thực hiện hành động ghi, Lax có thể gửi cookie | Đổi logout sang POST có token; GET chỉ hiển thị xác nhận |
| Cookie CSRF xuất hiện nhưng SPA không đọc được | `HttpOnly` trên cookie CSRF, host-only khác host, hoặc deferred token chưa cấp | Thiết kế kênh cấp token/handler đúng; không sửa cookie session thành đọc được |
| Token raw từ cookie bị từ chối | Handler đang kỳ vọng token masked/XOR | Cấu hình handler phù hợp với SPA và phiên bản Spring Security |
| Hệ thống có hai cookie cùng tên | Cookie phạm vi Domain/Path khác nhau hoặc bị injection | Đánh giá parse duplicate cookie, host-only, `__Host-` và cơ chế token |
| Chỉ có một browser không đăng nhập được | Khác biệt third-party cookie policy hoặc SameSite implementation | Tái hiện có hệ thống trên browser mục tiêu, không bỏ CSRF để “khớp browser” |
| Set-Cookie không có SameSite như YAML | Cookie do Spring Session/custom serializer/container phát | Xác định tầng thực sự tạo cookie; kiểm tra response qua proxy |

### 13.1. Checklist kiểm tra trước khi sửa cấu hình

- Session cookie có đúng `SameSite`, `Secure`, `HttpOnly`, `Domain`, `Path`?
- Request thực sự là **same-site** hay **cross-site**, có khác scheme không?
- Có phải **top-level navigation GET** thay vì POST/fetch/iframe?
- Browser có thực sự gửi cookie xác thực không?
- Token CSRF đang lấy từ `HttpSession`/`WebSession` hay từ cookie repository?
- Client gửi token qua đúng hidden field/header, đúng raw/masked format chưa?
- Request có đi qua đúng security chain và matcher CSRF không?
- Nếu đang có OAuth redirect hoặc frontend/API khác origin, CORS và session context có đúng không?
- Lỗi HTTP đến từ authentication, authorization, CSRF filter hay tầng mạng/browser?
- Thao tác GET có side effect nghiệp vụ ngoài ý muốn không?

Không dùng giải pháp “thử tắt CSRF rồi thấy hoạt động” như cấu hình cuối cùng cho web dựa vào cookie. Nó chỉ chứng minh có vấn đề ở luồng token hoặc policy, chứ không chứng minh CSRF không còn đáng quan tâm.

## 14. Bài tập tự đánh giá

**Tình huống 1 — same-site cross-origin.** `https://blog.example.com` bị attacker kiểm soát, `https://app.example.com` dùng session cookie `SameSite=Strict`. Attacker gửi POST từ blog đến app. Có chắc session cookie sẽ bị chặn?

**Đáp án:** **Không.** Hai origin khác nhau nhưng có thể cùng site theo schemeful same-site. Cookie của app vẫn có thể đi cùng request đến app; server cần kiểm tra CSRF token đối với thao tác thay đổi trạng thái.

**Tình huống 2 — link GET từ site khác.** Cookie là `SameSite=Lax`; người dùng bấm link `GET /logout` từ website ngoài. Ứng dụng thực hiện logout ngay. Vì sao có rủi ro?

**Đáp án:** Lax thường gửi cookie trong top-level navigation GET cross-site. GET bị sử dụng để thay đổi trạng thái. Cần thực hiện logout bằng POST có CSRF token; GET nếu có chỉ hiển thị trang xác nhận.

**Tình huống 3 — SPA khác origin cùng site.** Frontend `https://ui.example.com` gọi API `https://api.example.com` với `SameSite=Lax`, nhưng `fetch` không gửi cookie. Có phải Lax chặn vì khác hostname?

**Đáp án:** Không nhất thiết. Hai host có thể cùng site; vấn đề có thể là `fetch` mặc định `credentials: "same-origin"`, host cookie hoặc CORS. Cần kiểm tra `credentials: "include"` và các policy liên quan, đồng thời giữ CSRF token đúng.

**Tình huống 4 — None nhưng không có Secure.** Server phát `Set-Cookie: SESSION=...; SameSite=None` qua HTTP. Vì sao cookie không được browser chấp nhận như mong đợi?

**Đáp án:** Trong browser hiện đại `SameSite=None` yêu cầu `Secure` và kết nối an toàn phù hợp. Dùng HTTPS đúng cách, kiểm tra response thực và lưu ý chính sách cookie bên thứ ba.

**Tình huống 5 — “SameSite đủ rồi”.** Nhóm bỏ CSRF token khỏi POST nghiệp vụ vì đã bật `SameSite=Lax`. Điểm thiếu trong mô hình đe dọa là gì?

**Đáp án:** Request same-site từ subdomain ít tin cậy vẫn có thể mang cookie; Lax còn cho phép một số điều hướng GET; login CSRF và các luồng cross-site hợp lệ có ngoại lệ; browser policy có thể khác nhau. CSRF token tiếp tục kiểm chứng ở server ngay cả khi cookie được gửi.

**Tình huống 6 — OAuth callback POST.** Ứng dụng dùng `SameSite=Lax` và OAuth response mode `form_post`. Sau khi Identity Provider POST về callback, phiên trước login không còn được nhận diện. Vì sao?

**Đáp án:** Cross-site POST thường không mang cookie Lax. Cần xem lại cách lưu trạng thái OAuth request, response mode và cookie cần thiết theo kiến trúc; không tắt kiểm tra `state` hoặc toàn bộ CSRF để xử lý.

**Tình huống 7 — test giả.** `MockMvc` POST với `with(csrf())` thành công. Có thể kết luận SameSite đã chặn mọi cross-site POST không?

**Đáp án:** Không. MockMvc helper kiểm tra logic CSRF filter phía server, không tự chạy thuật toán cookie SameSite của browser. Cần kiểm thử browser qua các site/ngữ cảnh thật.

## Kết luận

**SameSite là thuộc tính cookie do trình duyệt thực thi**, giúp hạn chế credential được tự gửi trong những request cross-site. `Strict` hạn chế mạnh nhất nhưng có thể ảnh hưởng luồng điều hướng; `Lax` cân bằng UX và chặn nhiều cross-site POST nhưng thường vẫn cho cookie trong top-level GET; `None; Secure` hỗ trợ một số tích hợp cross-site song mở rộng phạm vi cookie có thể được gửi và vẫn chịu giới hạn browser.

**CSRF token là lớp kiểm tra do server thực thi** trên request thay đổi trạng thái, có giá trị đặc biệt khi cookie vẫn được gửi: chẳng hạn request **same-site nhưng cross-origin**, hoặc một hệ thống buộc phải dùng `SameSite=None`. Không một lớp nào thay thế lớp còn lại. Ngoài token, endpoint GET phải giữ ngữ nghĩa chỉ đọc, login/logout phải được thiết kế phù hợp, và cookie cần `Secure`, `HttpOnly`, phạm vi host/path chặt chẽ.

Trên **Spring Security Servlet** và **Reactive/WebFlux**, hãy cấu hình SameSite ở nơi thực sự phát cookie phiên, giữ `CsrfFilter`/`CsrfWebFilter` và repository/handler token phù hợp, rồi kiểm thử cả **hành vi cookie trong trình duyệt** lẫn **kiểm chứng token trên server**. Cách kết hợp này là một phần của hệ thống phòng vệ nhiều lớp cùng CORS, CSP, HSTS, security headers, HTTP firewall và bảo vệ session trong **SPRING_SECURITY_HTTP_PROTECTION**.

## Tài liệu tham khảo

- [MDN — Set-Cookie và thuộc tính SameSite](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): `Strict`, `Lax`, `None`, `Secure`, cookie prefixes và các lưu ý tương thích.
- [web.dev — SameSite cookies explained](https://web.dev/articles/samesite-cookies-explained): site, same-site, cross-site và các kịch bản browser.
- [Spring Security — CSRF Protection (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF token, repository, request handler và ứng dụng SPA.
- [Spring Security — CSRF Protection (WebFlux)](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): cơ chế CSRF cho Reactive applications.
- [Spring Framework — CookieWebSessionIdResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/CookieWebSessionIdResolver.html): cấu hình cookie của WebSession.
