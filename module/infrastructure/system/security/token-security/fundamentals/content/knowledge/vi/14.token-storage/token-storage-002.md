# Cookie HttpOnly và Secure

## Mục tiêu học tập

Trong chương **Token storage** của học phần bảo mật token, **HttpOnly** và **Secure** là hai thuộc tính quan trọng khi dùng HTTP cookie để duy trì phiên hoặc mang thông tin xác thực. Chúng giảm những rủi ro khác nhau, nhưng không thể tự bảo vệ toàn bộ quá trình xác thực, cấp quyền, lưu trữ và sử dụng access/refresh token.

Sau bài này, bạn có thể:

1. Giải thích vì sao cookie chứa session ID hoặc token là **thông tin xác thực nhạy cảm**, kể cả khi giá trị chỉ là chuỗi opaque.
2. Phân biệt chính xác **HttpOnly**, **Secure**, **SameSite**, **Domain**, **Path**, **Max-Age/Expires** và các tiền tố `__Host-`, `__Secure-`.
3. Hiểu **HttpOnly hạn chế JavaScript đọc cookie** nhưng không tự ngăn XSS thực hiện request; **Secure giới hạn gửi cookie qua HTTPS** nhưng không mã hóa giá trị cookie trên thiết bị.
4. Nhận diện và giảm thiểu **CSRF**, **XSS**, lộ cookie trong log, session fixation, token theft và replay.
5. Lựa chọn thiết kế **Backend for Frontend (BFF) + cookie session**, cookie mang access/refresh token hoặc token ở bộ nhớ phù hợp với mô hình đe dọa.
6. Cấu hình cookie và chính sách CSRF với ví dụ HTTP và Java/Spring, cũng như kiểm thử luồng đăng nhập, làm mới phiên, đăng xuất và reverse proxy.

## 1. Cookie là nơi lưu trữ và tự động gửi dữ liệu, không phải cơ chế phân quyền

HTTP cookie được server đặt qua header `Set-Cookie`; trình duyệt giữ cookie theo quy tắc phạm vi, thời hạn và chính sách bảo mật, rồi thường **tự gửi** cookie phù hợp trong header `Cookie` ở những request tiếp theo.

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=<RANDOM_SESSION_ID>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=900
Content-Type: application/json

{"message":"Đã tạo phiên"}
~~~

Sau đó, với request phù hợp:

~~~http
GET /account HTTP/1.1
Host: app.example.test
Cookie: __Host-session=<RANDOM_SESSION_ID>
~~~

Giá trị `<RANDOM_SESSION_ID>` chỉ để minh họa cấu trúc; trong hệ thống thật, **server phải tạo giá trị không đoán được bằng bộ sinh ngẫu nhiên mật mã**, quản lý phiên và kiểm tra hiệu lực phía server. Cookie do trình duyệt gửi **không tự chứng minh** người gửi là chủ tài khoản; cookie vẫn có thể bị đánh cắp hoặc sử dụng bởi một trình duyệt đã bị xâm nhập.

### Cookie có thể mang những gì?

| Nội dung cookie | Cách dùng | Điểm cần bảo vệ |
|---|---|---|
| **Opaque session ID** | Trỏ đến phiên và token được lưu phía backend/BFF. | Độ ngẫu nhiên, nơi lưu phiên, thu hồi, không log ID. |
| **JWT access token** | Browser tự gửi JWT cho server theo phạm vi cookie. | CSRF, phạm vi cookie, thời hạn, audience/scope và xác minh JWT tại API. |
| **Refresh token** | Dùng để xin access token mới ở backend/token endpoint thích hợp. | Bảo vệ đặc biệt vì tuổi thọ/quyền duy trì phiên; rotation và thu hồi. |
| **CSRF token hoặc dữ liệu không nhạy cảm** | Phục vụ cơ chế chống CSRF hoặc cài đặt giao diện. | Không được nhầm giá trị CSRF với session/access token. |

**Cookie, JWT và OAuth token là các khái niệm khác nhau.** Cookie là **phương tiện lưu và truyền** ở trình duyệt; JWT là **định dạng token**; access/refresh token có **mục đích** riêng. Một cookie `HttpOnly` mang JWT không tự làm JWT đúng issuer, audience, scope hoặc còn hiệu lực.

## 2. HttpOnly thực sự bảo vệ điều gì?

Thuộc tính **`HttpOnly`** yêu cầu trình duyệt không cho các API script thông thường như `document.cookie` đọc hoặc thay đổi cookie đó. Cookie vẫn được trình duyệt **gửi trong các HTTP request phù hợp**, bao gồm request do JavaScript tạo khi chính sách gửi cookie cho phép.

~~~http
Set-Cookie: __Host-session=<OPAQUE_ID>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Ở trang cùng host:

~~~javascript
// Không thấy cookie có HttpOnly trong document.cookie.
console.log(document.cookie);

// Tuy nhiên trình duyệt vẫn có thể gửi cookie khi gọi cùng origin.
const response = await fetch("/api/orders", {
  method: "GET",
  credentials: "same-origin"
});
~~~

### HttpOnly giúp chống loại tấn công nào?

Một kịch bản XSS điển hình là attacker chèn mã JavaScript vào origin của ứng dụng và cố đọc session ID qua `document.cookie` rồi gửi chuỗi đó ra ngoài. Nếu cookie xác thực có `HttpOnly`, việc **trích xuất trực tiếp giá trị cookie bằng API JavaScript thông thường** sẽ bị hạn chế.

Tuy nhiên, `HttpOnly` **không làm mã JavaScript độc hại trở nên vô hại**. Khi script đang chạy trong origin của ứng dụng, nó có thể:

- Tạo request tới endpoint ứng dụng; trình duyệt gửi cookie phù hợp cùng request.
- Đọc nhiều response cùng origin mà ứng dụng đang cho phép script đọc.
- Thay đổi giao diện, nội dung biểu mẫu hoặc lừa người dùng thực hiện hành động.
- Khai thác những điểm yếu nghiệp vụ khác trong phiên hiện có.

Vì vậy, một XSS vẫn có thể thao tác tài khoản thông qua phiên hợp lệ, **dù script không nhìn thấy chuỗi cookie**. Cần tiếp tục chống XSS bằng escaping/encoding đầu ra, xử lý HTML an toàn, CSP phù hợp, kiểm soát dependency và giới hạn thao tác nhạy cảm.

### HttpOnly không bảo vệ các nơi nào?

| Ngữ cảnh | `HttpOnly` có tự bảo vệ không? | Giải thích |
|---|---|---|
| Script gọi `document.cookie` | **Có**, với việc đọc/chỉnh sửa cookie đó qua API script thông thường. | Giá trị HttpOnly bị ẩn khỏi JavaScript. |
| Script bị XSS gửi request cùng origin | **Không**. | Cookie vẫn được browser gửi theo quy tắc request. |
| CSRF từ website bên ngoài | **Không trực tiếp**. | Attacker không cần biết giá trị cookie để dụ browser tự gửi request. |
| Trộm cookie từ browser profile, malware hoặc backup | **Không**. | HttpOnly không mã hóa nơi lưu ở máy người dùng. |
| Server hoặc proxy log header `Cookie` | **Không**. | HttpOnly không hạn chế server nhận cookie. |
| Token bị replay sau khi lộ | **Không**. | Người giữ cookie/token có thể thử dùng lại khi còn hiệu lực. |

**Đừng coi “không đọc được bằng `document.cookie`” là bằng chứng session an toàn tuyệt đối.**

## 3. Secure thực sự bảo vệ điều gì?

Thuộc tính **`Secure`** yêu cầu browser chỉ gửi cookie qua một **kênh truyền an toàn**, thông thường là HTTPS; trình duyệt có thể có ngoại lệ phát triển liên quan `localhost`, **không nên dựa vào ngoại lệ đó để thiết kế production**.

~~~http
Set-Cookie: __Host-session=<OPAQUE_ID>; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

Trong triển khai web công khai:

- Request tới `https://app.example.test` có thể nhận cookie nếu các điều kiện khác cũng phù hợp.
- Request tới `http://app.example.test` không được dùng để truyền cookie `Secure` trong điều kiện thông thường.
- Server cần dùng TLS hợp lệ, cấu hình HTTPS và chuyển hướng/tránh phục vụ giao diện xác thực qua HTTP.

### Secure không có nghĩa là giá trị cookie được mã hóa

**`Secure` không mã hóa cookie trong browser storage**, không tự mã hóa giá trị session ID/JWT và không chứng minh người gọi vẫn là người dùng gốc. Nó giới hạn đường truyền của cookie qua kênh an toàn; việc bảo vệ dữ liệu khi truyền chủ yếu dựa vào **TLS**.

Một giá trị JWT có payload Base64URL cũng **không bí mật** chỉ vì được đặt trong cookie `Secure`. Nếu token chứa claims nhạy cảm, cân nhắc tối thiểu hóa dữ liệu, đặt token phía backend hoặc dùng cơ chế bảo vệ phù hợp.

### HTTPS, HSTS và redirect

| Cơ chế | Vai trò |
|---|---|
| **HTTPS/TLS** | Bảo mật kết nối giữa các điểm kết thúc TLS, xác thực server và bảo vệ dữ liệu trên đường truyền tương ứng. |
| **Cookie `Secure`** | Yêu cầu browser không gửi cookie qua kết nối HTTP thông thường. |
| **HSTS** | Hướng dẫn browser nâng cấp kết nối tới HTTPS cho host đã áp dụng chính sách, giảm nguy cơ truy cập HTTP; cần cấu hình đúng và xem xét yêu cầu preload riêng nếu dùng. |
| **Tắt HTTP hoặc chuyển hướng HTTPS** | Hạn chế các điểm truy cập không an toàn; chuyển hướng đơn thuần không thay mọi lợi ích của HSTS. |

Ví dụ HSTS, chỉ dùng khi toàn bộ phạm vi áp dụng thực sự hỗ trợ HTTPS:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

`includeSubDomains` chỉ phù hợp nếu **mọi subdomain bị áp dụng** đều sẵn sàng dùng HTTPS. Tránh bật đại trà mà chưa đánh giá tài sản nội bộ hoặc subdomain cũ.

### TLS kết thúc tại reverse proxy

Nếu load balancer hoặc reverse proxy kết thúc TLS, backend có thể nhìn thấy kết nối nội bộ HTTP và hiểu nhầm request bên ngoài là không an toàn. Cần cấu hình **trusted forwarded headers** và proxy trust boundary đúng để framework phát cookie `Secure` hoặc redirect HTTPS chính xác.

Không tin tùy tiện header `X-Forwarded-Proto: https` do client Internet tự gửi. Proxy phải xóa/ghi đè forwarded headers từ nguồn không tin cậy, bảo vệ đường nối proxy–backend và chỉ cho backend nhận metadata từ proxy đã xác thực.

## 4. Đọc đầy đủ các thuộc tính Set-Cookie

Một cookie auth tốt thường có **nhiều thuộc tính kết hợp**, không chỉ `HttpOnly` và `Secure`:

~~~http
Set-Cookie: __Host-session=<RANDOM_SESSION_ID>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=900
~~~

| Thuộc tính | Ý nghĩa | Lưu ý thực hành |
|---|---|---|
| **`HttpOnly`** | Chặn API script thông thường đọc/chỉnh sửa cookie. | Không chống CSRF hoặc XSS thực hiện request. |
| **`Secure`** | Chỉ gửi trên kênh an toàn, thông thường HTTPS. | Không mã hóa cookie tại chỗ. |
| **`SameSite`** | Giới hạn khi cookie được gửi trong yêu cầu **cross-site**. | Phải xét `Strict`, `Lax`, `None` theo luồng ứng dụng. |
| **`Domain`** | Chỉ định các host có thể nhận cookie trong phạm vi domain hợp lệ. | Bỏ `Domain` tạo **host-only cookie**, thường dễ giới hạn hơn. |
| **`Path`** | Giới hạn đường dẫn request mà browser gửi cookie. | **Không phải ranh giới bảo mật mạnh** giữa các endpoint trên cùng origin. |
| **`Max-Age`** | Số giây tồn tại của cookie từ khi nhận. | Khi cùng có `Expires`, `Max-Age` có ưu tiên theo chuẩn. |
| **`Expires`** | Thời điểm hết hạn theo ngày/giờ HTTP. | Bị ảnh hưởng bởi clock/time normalization của browser. |
| **`Partitioned`** | Thuộc tính hỗ trợ cookie phân vùng ở một số môi trường trình duyệt. | Không thay `HttpOnly`, CSRF hay chính sách third-party cookie; kiểm tra hỗ trợ trước khi chọn. |

### Cookie không có `Max-Age` hoặc `Expires`

Đó thường là **session cookie** theo quản lý của trình duyệt. Nhưng **đừng suy rằng nó chắc chắn bị xóa khi đóng cửa sổ**: browser có thể khôi phục session khi người dùng bật session restore. Server cần **giới hạn và hết hạn phiên độc lập**, không dựa hoàn toàn vào vòng đời của cửa sổ browser.

### Cookie tồn tại lâu không có nghĩa session luôn hợp lệ

Cookie với `Max-Age=86400` có thể tồn tại 24 giờ phía browser, nhưng server cần kiểm tra **thời hạn, trạng thái thu hồi, thiết bị, quyền và tuổi phiên** theo policy. Nếu server xóa session sớm, cookie còn tồn tại cũng **không được cấp quyền**.

## 5. Domain, Path và cookie prefixes: thu hẹp phạm vi lộ

### Host-only cookie vs Domain cookie

Giả sử ứng dụng có hai host:

~~~text
app.example.test
blog.example.test
~~~

Với cookie được đặt từ `app.example.test` và **không có `Domain`**, cookie thường chỉ được gửi lại cho chính host `app.example.test` (kèm điều kiện Path/SameSite/Secure tương ứng).

Nếu đặt:

~~~http
Set-Cookie: session=<ID>; Domain=example.test; Path=/; Secure; HttpOnly
~~~

Cookie có thể được gửi tới các subdomain phù hợp như `blog.example.test`. Điều này mở rộng diện nhận cookie; nếu một subdomain yếu hoặc bị chiếm quyền kiểm soát, nguy cơ lộ/sửa cookie thuộc domain có thể tăng. Không dùng `Domain` trừ khi có nhu cầu chức năng rõ ràng và đánh giá tin cậy giữa các subdomain.

### Path không tạo lớp cách ly bảo mật chắc chắn

~~~http
Set-Cookie: refresh=<TOKEN>; Path=/auth/refresh; Secure; HttpOnly; SameSite=Strict
~~~

`Path=/auth/refresh` có thể giúp giảm những request mà browser **tự đính kèm** cookie, nhưng **không** bảo đảm các đoạn mã hoặc endpoint khác cùng origin không thể ảnh hưởng hoặc quan sát gián tiếp hoạt động của phiên. Không coi `Path` là sandbox giữa các ứng dụng dùng chung host.

### Prefix `__Secure-` và `__Host-`

Các prefix được browser hỗ trợ giúp áp đặt thêm ràng buộc khi cookie được đặt:

| Prefix | Điều kiện đáng chú ý | Lợi ích |
|---|---|---|
| **`__Secure-`** | Cookie phải có `Secure` và được đặt từ ngữ cảnh bảo mật phù hợp. | Giảm khả năng đặt cookie tên đó trong ngữ cảnh không bảo mật. |
| **`__Host-`** | Phải có `Secure`, **không có `Domain`**, và `Path=/`; đặt từ ngữ cảnh bảo mật phù hợp. | Giới hạn cookie ở host phát hành và giảm nguy cơ cookie domain-wide. |

Ví dụ cookie phiên:

~~~http
Set-Cookie: __Host-session=<RANDOM_SESSION_ID>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=900
~~~

`__Host-` **không tự yêu cầu `HttpOnly`**, do đó phải ghi rõ `HttpOnly` nếu đó là cookie xác thực. Prefix cũng **không thay thế CSRF protection, XSS protection và session validation**. Cần kiểm tra mức hỗ trợ trên các browser mục tiêu.

## 6. SameSite và CSRF: vì sao HttpOnly + Secure vẫn chưa đủ?

**CSRF (Cross-Site Request Forgery)** xảy ra khi một website không tin cậy khiến trình duyệt người dùng gửi request đã được xác thực tới một website khác, và server không xác minh đủ rằng thao tác thực sự được người dùng/ứng dụng hợp lệ khởi tạo.

### Kịch bản

1. Người dùng đang đăng nhập tại `https://bank.example.test` với cookie phiên `HttpOnly; Secure`.
2. Người dùng truy cập một website của attacker.
3. Website đó cố khiến browser gửi request chuyển tiền tới ngân hàng.
4. Nếu browser gửi cookie phiên và ngân hàng không kiểm tra CSRF/Origin/policy nghiệp vụ, thao tác có thể bị thực thi.

**Attacker không cần đọc cookie.** Vì vậy `HttpOnly` không chống CSRF; `Secure` cũng không chống CSRF vì request HTTPS của attacker vẫn là kênh an toàn.

### Ba chế độ SameSite

| Chế độ | Ý nghĩa khái quát | Đánh đổi |
|---|---|---|
| **`SameSite=Strict`** | Hạn chế gửi cookie trong các yêu cầu khởi phát cross-site. | Bảo vệ mạnh hơn ở lớp cookie nhưng có thể cản luồng đi từ website khác/OAuth redirect. |
| **`SameSite=Lax`** | Cho phép một số điều hướng top-level cross-site với phương thức an toàn, điển hình GET; hạn chế nhiều trường hợp POST cross-site. | Phù hợp nhiều ứng dụng web, **không thay CSRF defense**. |
| **`SameSite=None; Secure`** | Cho phép gửi trong ngữ cảnh cross-site khi browser/chính sách riêng cho phép. | Cần `Secure`; tăng nhu cầu kiểm soát CSRF và bị ảnh hưởng bởi chính sách third-party cookie. |

Không nên dựa vào **mặc định** SameSite của từng browser. Hãy đặt một giá trị **tường minh** phù hợp với luồng thật và kiểm thử trên browser mục tiêu.

### Site khác origin

Browser phân biệt **origin** (scheme + host + port) và **site** (một khái niệm bao gồm scheme cùng miền đăng ký có thể dùng để xác định same-site theo quy tắc browser). Ví dụ:

~~~text
https://app.example.test
https://api.example.test
~~~

Hai URL trên **khác origin** nhưng thường **cùng site**. `SameSite` chủ yếu dựa vào **site**, không phải origin; do đó một subdomain bị xâm nhập **có thể** khiến browser gửi cookie tới subdomain khác trong các request same-site. Đây là lý do không dùng `SameSite` như biện pháp CSRF duy nhất trong kiến trúc nhiều subdomain.

### Phòng chống CSRF ở server

Các biện pháp thường phối hợp:

1. **CSRF token** (synchronizer token hoặc signed double-submit cookie được ràng buộc với phiên theo thiết kế), kiểm tra trên thao tác thay đổi trạng thái.
2. **Kiểm tra `Origin`/`Referer`** theo chính sách và xử lý trường hợp thiếu hợp lệ, không dùng so khớp chuỗi con domain.
3. **Fetch Metadata headers** như `Sec-Fetch-Site` làm tín hiệu từ chối request cross-site nguy hiểm; không thay hoàn toàn token ở hệ thống cần CSRF token.
4. **`SameSite` phù hợp** và **không dùng GET để thay đổi trạng thái**.
5. **Xác nhận bổ sung** cho giao dịch rủi ro cao; bảo vệ XSS vì XSS cùng origin có thể vượt nhiều cơ chế chống CSRF.

Ví dụ yêu cầu thay đổi dữ liệu với CSRF token được cấp và quản lý đúng:

~~~http
POST /account/change-email HTTP/1.1
Host: app.example.test
Cookie: __Host-session=<SESSION_ID>
Content-Type: application/json
X-CSRF-Token: <CSRF_TOKEN_BOUND_TO_SESSION>

{"email":"new-address@example.test"}
~~~

**Đừng nhầm CSRF token với bearer access token**: CSRF token cần bảo vệ chống request giả mạo theo chính sách; bearer token là thông tin ủy quyền. Một CSRF token có thể được đưa cho JavaScript của ứng dụng hợp lệ theo thiết kế, trong khi **cookie phiên xác thực vẫn cần `HttpOnly`**.

## 7. Nên đặt access token, refresh token hay session ID trong cookie?

Không có một vị trí lưu token duy nhất đúng cho mọi kiến trúc. Điều cần cân nhắc là **ai thực sự cần đọc token**, **token được trình tới đâu**, **khả năng JS bị XSS** và **CSRF khi browser tự gửi cookie**.

### Phương án A — BFF + opaque session cookie

Một kiến trúc thường phù hợp cho ứng dụng web là **Backend for Frontend (BFF)**:

1. Browser đăng nhập qua luồng Authorization Code + PKCE phù hợp.
2. **BFF** giữ access token/refresh token và thông tin grant ở **backend** trong kho bảo vệ phù hợp.
3. Browser chỉ giữ **opaque session ID** trong cookie `HttpOnly; Secure; SameSite`.
4. Browser gọi BFF; BFF kiểm tra phiên, CSRF, policy và dùng access token để gọi Resource Server.
5. BFF quản lý refresh, rotation, logout và thu hồi phiên phía server.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant F as BFF / Session Backend
    participant AS as Authorization Server
    participant RS as Resource Server
    U->>B: Đăng nhập
    B->>F: Khởi tạo luồng OAuth
    F->>AS: Authorization Code + PKCE theo thiết kế
    AS-->>F: Token response sau khi đổi code
    F->>F: Lưu token phía server và tạo session
    F-->>B: Set-Cookie HttpOnly; Secure; SameSite
    B->>F: Request kèm session cookie và CSRF khi cần
    F->>F: Kiểm tra phiên, CSRF và quyền
    F->>RS: Gọi API với access token phù hợp
    RS-->>F: Phản hồi được phép
    F-->>B: Dữ liệu phù hợp
~~~

**Ưu điểm:** token OAuth không cần xuất hiện trong JavaScript của trang; backend kiểm soát nơi lưu refresh token và thời điểm thu hồi. **Giới hạn:** BFF vẫn phải chống CSRF, XSS điều khiển trình duyệt, session hijacking, lộ session cookie và các lỗi phân quyền ở RS. Session store và hệ thống token backend cần được bảo vệ.

### Phương án B — Access token trong HttpOnly cookie

Một API có thể dùng cookie chứa access token. Browser tự gửi cookie, nhưng JavaScript không đọc được nếu `HttpOnly`. Kiến trúc phải bảo đảm:

- Cookie chỉ đi đến **host/path cần thiết**, không lan sang dịch vụ không cùng ranh giới tin cậy.
- API hiểu cookie chính là **thông tin xác thực** và **phải chống CSRF** vì browser tự gửi nó.
- API xác minh JWT/opaque token, issuer, audience, thời hạn, scope và quyền trên bản ghi.
- Token không bị ghi log, không xuất ra HTML và có chiến lược thu hồi.

Đừng coi câu “token không ở localStorage nên hoàn toàn an toàn trước XSS” là đúng. XSS có thể gửi request khi cookie tự đi kèm; đồng thời **token lưu trong cookie không phải một tính năng mặc định của mọi OAuth Resource Server**, cần chủ động thiết kế cơ chế tiếp nhận.

### Phương án C — Refresh token trong HttpOnly cookie

Refresh token có khả năng duy trì phiên lâu hơn và chỉ nên được sử dụng đúng **token endpoint/đường refresh được thiết kế**. Khi hệ thống dùng cookie cho nó, cần:

- `HttpOnly; Secure` và phạm vi cookie hẹp phù hợp.
- Kiểm tra CSRF/Origin cho luồng refresh nếu cookie được browser tự gửi.
- Rotation và phát hiện refresh token reuse hoặc sender-constraining theo chính sách/loại client.
- Thu hồi ở server, bảo vệ session và không cấp scope vượt grant gốc.

Cookie có `Path=/auth/refresh` có thể giảm đường truyền cookie không cần thiết, nhưng **Path không phải ranh giới bảo mật**. Nếu đã chọn BFF, có thể giữ refresh token **chỉ phía backend** thay vì phát nó vào cookie của browser.

### Phương án D — Access token trong bộ nhớ JavaScript

Token được giữ trong **bộ nhớ ứng dụng** có thể tránh browser tự gửi token như cookie, nhưng JavaScript bị xâm nhập trong cùng origin có thể đọc hoặc sử dụng token. Lưu trong `localStorage` hoặc `sessionStorage` khiến token dễ tiếp cận qua XSS hơn so với cookie HttpOnly; các nơi lưu đó cũng không được bảo vệ chỉ bằng cấu hình `Secure`/`HttpOnly` (hai thuộc tính này thuộc cookie).

Không có phương án nào loại bỏ nhu cầu bảo vệ code frontend, giới hạn quyền, token lifetime và quản lý phiên. BFF thường giúp giảm độ phơi lộ token OAuth với JavaScript khi phù hợp kiến trúc, nhưng cũng làm tăng trách nhiệm bảo vệ backend session.

### Ma trận lựa chọn

| Nhu cầu | Cách cân nhắc | Rủi ro vẫn phải xử lý |
|---|---|---|
| Web app có backend đáng tin, nhiều API OAuth | **BFF + HttpOnly session cookie**, token OAuth ở backend. | CSRF, session hijacking, refresh/thu hồi, backend access control. |
| Same-origin web app xác thực bằng session | **Cookie session HttpOnly + Secure + SameSite**. | CSRF, session fixation, XSS thao tác, server-side session expiry. |
| Browser trực tiếp gọi API khác origin | Cần thiết kế CORS/credentials, cookie domain/site hoặc token transport rõ ràng. | XSS, CSRF nếu dùng cookie, third-party cookie restrictions. |
| Backend-to-backend | Thường không cần browser cookie; giữ credential trong kho secret/keystore phía service. | Quyền secret, rotation, scope/audience, replay. |
| Mobile native | Dùng OS secure storage/keystore phù hợp thay vì giả định cookie HttpOnly giải quyết lưu trữ native. | Backup, malware, khóa thiết bị, refresh/thu hồi. |

## 8. Cross-origin request, CORS và cookie

Một browser có thể cần gọi:

~~~text
Frontend: https://app.example.test
API:      https://api.example.test
~~~

Hai endpoint **khác origin**. Nếu API dựa vào cookie, fetch phía frontend thường cần cấu hình gửi credential cho cross-origin request:

~~~javascript
const response = await fetch("https://api.example.test/orders", {
  method: "GET",
  credentials: "include"
});
~~~

Tuy nhiên, `credentials: "include"` **không buộc browser phải gửi mọi cookie**. Cookie vẫn bị chi phối bởi `Domain`, `Path`, `Secure`, `SameSite` và chính sách cookie/browser.

Nếu server cho phép frontend đọc response của credentialed CORS request, server cần trả chính sách CORS **cụ thể**, ví dụ:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Không sử dụng `Access-Control-Allow-Origin: *` cùng credentialed CORS response để kỳ vọng browser cho ứng dụng đọc response. Cũng **không phản chiếu mọi Origin bất kỳ** thành origin được phép khi dùng credentials.

### CORS không phải cơ chế chống CSRF đủ dùng

CORS chủ yếu kiểm soát **quyền JavaScript đọc response cross-origin**, cùng quy tắc về một số loại request/preflight. Một số request trình duyệt vẫn có thể được **gửi** dù attacker không đọc được response. Nếu request làm thay đổi trạng thái, **CSRF vẫn cần được xử lý**.

### Cookie cross-site thực sự

Nếu frontend và API nằm ở hai **site khác nhau**, một số trường hợp cần `SameSite=None; Secure` để cookie có thể được gửi cross-site. Nhưng trình duyệt có thể chặn/giới hạn **third-party cookies**, nên việc đặt `SameSite=None` **không đảm bảo** tất cả browser sẽ gửi cookie. Cần kiểm thử thực tế; cân nhắc same-site BFF hoặc kiến trúc khác thay vì dựa hoàn toàn vào third-party cookie.

## 9. Cấu hình minh họa với Java và Spring

### Cách 1 — Spring Boot session cookie

Với ứng dụng dùng phiên của server, có thể cấu hình ở Spring Boot (đối chiếu tên property theo phiên bản đang sử dụng):

~~~yaml
server:
  servlet:
    session:
      cookie:
        name: __Host-session
        http-only: true
        secure: true
        same-site: lax
        path: /
~~~

**Cảnh báo triển khai:** prefix `__Host-` yêu cầu **không có `Domain`** và `Path=/`. Cần kiểm tra header `Set-Cookie` thực tế để bảo đảm container/proxy không bổ sung `Domain` hoặc bỏ `Secure`. Session timeout, invalidation và session store được cấu hình riêng; cookie lifetime không thay thời hạn phiên ở server.

### Cách 2 — Phát cookie một cách tường minh

Ví dụ Java với Spring `ResponseCookie`:

~~~java
import java.time.Duration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import jakarta.servlet.http.HttpServletResponse;

final class SessionCookieWriter {
    static void setSessionCookie(
            HttpServletResponse response, String randomOpaqueSessionId) {
        ResponseCookie cookie = ResponseCookie
                .from("__Host-session", randomOpaqueSessionId)
                .httpOnly(true)
                .secure(true)
                .path("/")
                .sameSite("Lax")
                .maxAge(Duration.ofMinutes(15))
                .build();

        response.addHeader(HttpHeaders.SET_COOKIE, cookie.toString());
    }
}
~~~

**Không** tự tạo `randomOpaqueSessionId` bằng `Random`, timestamp, email hoặc user ID; phải dùng CSPRNG và quản lý session/token ở server. Đoạn code chỉ cấu hình **cookie**, chưa triển khai session creation, CSRF, authorization, rate limiting hay token revocation.

### Cách 3 — Không vô hiệu hóa CSRF khi dùng cookie authentication

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/health").permitAll()
            .anyRequest().authenticated());

    // Ví dụ ứng dụng web xác thực bằng session cookie.
    // Dùng CSRF protection theo thiết kế, không tắt chỉ vì cookie là HttpOnly.
    http.csrf(Customizer.withDefaults());

    return http.build();
}
~~~

Với request HTML form truyền thống, Spring có thể tích hợp CSRF token vào form. Với SPA gọi API, cần thiết kế cách đưa CSRF token đến JavaScript hợp lệ (ví dụ token trả qua endpoint/HTML được bảo vệ hoặc repository phù hợp) và gửi lại qua header theo cơ chế đã chọn.

Một số cấu hình sử dụng **CSRF token cookie có thể đọc bởi JavaScript**, nhưng đó là **cookie CSRF token**, khác với **cookie xác thực**. **Không** vì cần JavaScript đọc CSRF token mà bật `HttpOnly=false` cho session hoặc refresh token.

### Đăng xuất phải làm hơn việc xóa cookie

~~~java
static void clearSessionCookie(HttpServletResponse response) {
    ResponseCookie expiredCookie = ResponseCookie
            .from("__Host-session", "")
            .httpOnly(true)
            .secure(true)
            .path("/")
            .sameSite("Lax")
            .maxAge(Duration.ZERO)
            .build();
    response.addHeader(HttpHeaders.SET_COOKIE, expiredCookie.toString());
}
~~~

Để xóa cookie đúng, cần khớp **tên, Path và Domain** tương ứng với cookie đã đặt; ví dụ `__Host-session` ở đây không có `Domain`. **Quan trọng hơn**, backend phải **vô hiệu hóa session server-side**, thu hồi/điều chỉnh refresh grant khi thích hợp; chỉ yêu cầu browser xóa cookie không bảo đảm một bản sao ID bị đánh cắp không còn dùng được.

## 10. Vòng đời cookie, session và token

### Khi đăng nhập thành công

1. Server xác thực/hoàn thành OAuth/OIDC theo luồng phù hợp, kiểm tra `state`/PKCE và những yêu cầu liên quan.
2. Tạo **session ID mới** có độ ngẫu nhiên cao; không tái sử dụng session ID trước xác thực.
3. Gắn session với principal, quyền và grant phù hợp trong session store tin cậy.
4. Phát cookie `HttpOnly; Secure; SameSite` cùng `Domain`/`Path`/thời hạn được giới hạn.
5. Tại mỗi request, xác minh session còn hiệu lực và thực thi authorization.

### Khi nâng quyền hoặc xác thực lại

Khi user hoàn tất đăng nhập, nâng mức xác thực, đổi vai trò hoặc thay đổi trạng thái bảo mật quan trọng, nên **xoay session ID** hoặc áp dụng cơ chế session fixation protection phù hợp với framework. Đừng biến một ID khách truy cập chưa xác thực thành session quản trị mà không đổi ID.

### Khi refresh token được sử dụng

Nếu BFF giữ refresh token phía server, cookie browser chỉ xác định phiên BFF. Backend sử dụng refresh token theo grant/policy để xin access token mới, thực hiện rotation/ràng buộc người gửi nếu yêu cầu và xử lý lỗi thu hồi. Refresh token **không được trình trực tiếp đến Resource Server** như access token.

### Khi đăng xuất, thu hồi hoặc hết hạn

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser
    participant App as Session Backend / BFF
    participant AS as Authorization Server
    User->>Browser: Đăng xuất
    Browser->>App: Logout request + CSRF protection
    App->>App: Vô hiệu hóa session tại server
    App->>AS: Thu hồi token/grant khi chính sách yêu cầu
    App-->>Browser: Set-Cookie session Max-Age=0
    Browser->>App: Request cũ với bản sao cookie (nếu còn)
    App-->>Browser: Từ chối vì session đã vô hiệu hóa
~~~

**Xóa cookie** là một hành động ở browser; **vô hiệu hóa session** là hành động ở server; **thu hồi access/refresh token** là hành động của cơ chế token/AS. Cần xác định rõ ba kết quả này trong yêu cầu nghiệp vụ.

Nếu access token là JWT ký và RS chỉ xác minh chữ ký/`exp`, việc logout khỏi BFF không tự bảo đảm **bản sao JWT đã lộ ngoài BFF** hết hiệu lực ngay. Cần TTL, revocation, introspection/denylist hoặc policy phù hợp nếu yêu cầu thu hồi tức thời hơn.

## 11. Các tấn công mà HttpOnly và Secure không tự ngăn

| Tình huống | Vì sao chỉ HttpOnly/Secure chưa đủ? | Kiểm soát bổ sung |
|---|---|---|
| **XSS thực hiện hành động** | Script không cần đọc cookie để gọi endpoint cùng origin. | Chống XSS, quyền tối thiểu, xác nhận thao tác nhạy cảm. |
| **CSRF** | Browser tự đính cookie trong request phù hợp. | SameSite, CSRF token, Origin/Fetch Metadata, GET không đổi trạng thái. |
| **Session fixation** | Attacker cố khiến client dùng ID phiên định trước. | Session ID mới khi đăng nhập/nâng quyền, chỉ nhận ID do server cấp. |
| **Session hijacking qua thiết bị/log** | Cookie có thể bị trộm ngoài API JavaScript. | Không log, bảo vệ thiết bị/session store, TTL, thu hồi và giám sát. |
| **Cross-subdomain cookie scope** | Cookie `Domain` quá rộng có thể tới host không đáng tin. | Host-only cookie, prefix `__Host-`, tách host nhạy cảm. |
| **Bearer replay** | Người giữ ID/token có thể trình lại khi còn hiệu lực. | TTL, thu hồi, scope/audience hẹp, DPoP/mTLS cho access token khi cần. |
| **Sai audience/scope/tenant** | Cookie attributes không xác minh nội dung token hoặc quyền nghiệp vụ. | JWT/introspection validation và resource-level authorization. |
| **Proxy spoofing** | Backend tin forwarded headers do người ngoài tự đặt. | Trusted proxy configuration, sanitize headers, TLS đúng ranh giới. |
| **Cookie tồn tại sau thu hồi** | Browser lưu cookie không đồng nghĩa server vẫn nên cấp quyền. | Server-side invalidation, refresh grant revocation. |
| **Third-party cookie bị chặn** | `SameSite=None; Secure` không buộc browser chấp nhận. | Kiểm thử browser, BFF hoặc kiến trúc không phụ thuộc third-party cookie. |

### Cookie `Secure` và mạng nội bộ

Không coi HTTP nội bộ giữa proxy và backend là an toàn mặc nhiên. Nếu proxy truyền session/token qua hạ tầng nội bộ, phải bảo vệ kênh và quyền truy cập phù hợp; dùng TLS/mTLS giữa các service khi mô hình đe dọa yêu cầu. Browser cookie `Secure` **chỉ điều chỉnh hành vi browser**, không mã hóa các kết nối nội bộ phía server.

### Session ID có cần JWT không?

Không. Opaque session ID ngẫu nhiên với state được bảo vệ ở backend thường phù hợp cho session cookie. JWT trong cookie **không tự tốt hơn**: nếu token còn hạn nhưng quyền bị thu hồi, có thể cần kiểm tra trạng thái; kích thước lớn và claims lộ cũng tạo rủi ro. Chọn biểu diễn dựa trên ràng buộc hệ thống, không dựa vào mong muốn “mọi nơi đều JWT”.

## 12. Ma trận kiểm thử bảo mật

Giả sử ứng dụng tại `https://app.example.test` dùng cookie `__Host-session` có `Secure; HttpOnly; SameSite=Lax; Path=/`, không có `Domain` và backend có session store:

| Kiểm thử | Kết quả mong đợi | Điều chứng minh |
|---|---|---|
| Server đăng nhập trả `Set-Cookie` | Đủ `HttpOnly; Secure; SameSite=Lax; Path=/`, không có `Domain`. | Cookie đúng hợp đồng. |
| JavaScript đọc `document.cookie` | Không thấy `__Host-session`. | HttpOnly hoạt động ở browser. |
| JavaScript same-origin gọi `fetch("/account")` | Browser có thể gửi cookie hợp lệ; server vẫn kiểm tra session. | HttpOnly không cản request đúng. |
| Truy cập HTTP không an toàn tới host | Browser không gửi cookie Secure trong điều kiện production. | Không lộ cookie qua HTTP thường. |
| Truy cập `blog.example.test` | Không nhận cookie host-only của `app.example.test`. | Phạm vi host. |
| Request GET top-level đi từ site khác | Với Lax có thể gửi cookie; GET **không** đổi trạng thái. | Không hiểu sai SameSite=Lax. |
| POST cross-site có khả năng kèm cookie do policy/browser | Endpoint từ chối nếu CSRF/Origin không hợp lệ. | Phòng chống CSRF độc lập với cookie attributes. |
| Tạo cookie có `__Host-` nhưng đặt `Domain` | Browser hỗ trợ prefix phải từ chối cookie sai cấu trúc. | Điều kiện prefix. |
| XSS gọi request same-origin khi user đang đăng nhập | Không được cho phép thao tác ngoài quyền; vẫn cần chặn XSS. | HttpOnly không xóa rủi ro XSS. |
| Server session đã hết hạn, cookie vẫn còn | Request bị từ chối. | Thời hạn server độc lập với cookie. |
| Logout và thử lại bằng bản sao ID cũ | Request bị từ chối. | Server-side session invalidation. |
| Nâng quyền mà ID session không đổi | Kiểm thử phải phát hiện và yêu cầu bảo vệ session fixation theo kiến trúc. | Session rotation. |
| Cookie được ghi vào access log/reverse proxy log | Test/audit xác nhận giá trị bị loại hoặc làm sạch. | Không rò rỉ credential qua logging. |
| AS thu hồi refresh token | Backend không được tiếp tục refresh grant đó. | Thu hồi đúng vòng đời. |
| API nhận JWT từ cookie sai `aud`/`scope` | Từ chối dù cookie attributes đúng. | Cookie không thay token validation. |
| Proxy nhận `X-Forwarded-Proto` giả từ Internet | Backend không tin header giả hoặc phát sinh downgrade. | Trusted proxy boundary. |
| Browser chặn third-party cookie | Ứng dụng thông báo/điều chỉnh luồng, không giả định cookie luôn gửi. | Tương thích chính sách browser. |

Test cần chạy trên **trình duyệt thật** hoặc môi trường browser có hành vi tương đương khi xác minh `HttpOnly`, `Secure`, `SameSite` và prefix. Unit test controller chỉ xem cấu hình Java **không đủ** để chứng minh browser xử lý cookie đúng, đặc biệt khi đi qua CDN, proxy, load balancer hoặc cross-origin request.

## 13. Tình huống suy luận

**Tình huống A — HttpOnly có chống XSS không?** Cookie session có `HttpOnly`, nhưng attacker inject script gọi `POST /transfer` ở cùng origin. Có thể gây hại không?

**Giải thích:** Có thể. Script không cần đọc cookie nếu browser tự gửi cookie cùng request. HttpOnly giảm khả năng **đánh cắp trực tiếp chuỗi cookie bằng JavaScript**, không thay chống XSS và authorization nghiệp vụ.

**Tình huống B — Secure có mã hóa JWT không?** API đặt JWT trong `Set-Cookie` với `Secure; HttpOnly`. Người có được chuỗi JWT từ log có thể đọc payload của JWT ký thông thường không?

**Giải thích:** Có thể. `Secure` bảo vệ cách browser truyền cookie, `HttpOnly` giới hạn JavaScript đọc cookie. Cả hai **không mã hóa payload JWS** hoặc dữ liệu đã bị lộ ở server log.

**Tình huống C — Cookie có SameSite=Lax thì khỏi CSRF?** Website dùng GET `/delete-account` để xóa tài khoản. Có thể dựa vào SameSite=Lax không?

**Giải thích:** Không. Lax thường cho phép cookie trên một số **điều hướng top-level GET cross-site**. GET không nên có side effect; cần dùng phương thức đúng, kiểm tra CSRF/Origin và xác nhận bổ sung cho hành động nguy hiểm.

**Tình huống D — Dùng Domain rộng.** `app.example.test` đặt cookie auth với `Domain=example.test`; `blog.example.test` do nhóm khác quản lý. Rủi ro nào xuất hiện?

**Giải thích:** Cookie có thể được gửi tới blog subdomain, mở rộng diện lộ. Nên dùng host-only cookie, có thể thêm `__Host-` và tách ranh giới trust giữa các host.

**Tình huống E — OAuth redirect không còn session.** Ứng dụng dùng `SameSite=Strict` cho cookie duy trì login transaction, rồi redirect từ AS ở site khác về callback. Vì sao có thể lỗi?

**Giải thích:** Cookie Strict thường không được gửi trong **điều hướng khởi phát cross-site** tới callback. Cần thiết kế luồng OAuth tương thích, thường xem xét Lax cho top-level GET callback và bảo vệ `state`/PKCE. Nếu callback dùng `form_post`, cần đánh giá quy tắc SameSite/CSRF và chính sách browser riêng.

**Tình huống F — Logout chỉ xóa cookie.** Backend vẫn giữ session ID cũ hợp lệ; attacker có bản sao cookie trước khi người dùng logout. Attacker tiếp tục dùng được không?

**Giải thích:** Có thể. Xóa cookie trên thiết bị không thu hồi bản sao. Server phải vô hiệu hóa session và xử lý token/grant liên quan khi cần.

**Tình huống G — BFF có đủ an toàn tuyệt đối?** Token OAuth nằm ở backend; browser chỉ có cookie HttpOnly. Attacker inject script same-origin có thể thao tác gì?

**Giải thích:** Script có thể gọi BFF bằng session cookie hợp lệ và tương tác với API trong phạm vi session, nên vẫn cần chống XSS, giới hạn nghiệp vụ, CSRF và kiểm tra quyền ở BFF/RS. BFF giảm việc **đưa token OAuth trực tiếp vào JavaScript**, không xóa mọi rủi ro.

**Tình huống H — Cookie cross-site không được gửi.** App đặt `SameSite=None; Secure` và bật `credentials: "include"` nhưng một browser vẫn chặn cookie của API. Có phải backend sai `HttpOnly`?

**Giải thích:** Không nhất thiết. Browser có thể chặn/giới hạn **third-party cookie** theo privacy policy. Cần kiểm tra Domain/Path/SameSite/CORS và chính sách browser; cân nhắc kiến trúc same-site/BFF.

## Checklist triển khai

1. **Nhận diện credential:** session ID, access token hay refresh token? Ai phải đọc, ai cần giữ bí mật và ai có quyền sử dụng?
2. **Bật `HttpOnly` cho cookie xác thực** để giảm khả năng JavaScript trích xuất giá trị; không coi là biện pháp chống XSS toàn diện.
3. **Bật `Secure` cùng HTTPS/TLS**, cân nhắc HSTS và cấu hình proxy tin cậy; không phụ thuộc HTTP/localhost exceptions.
4. **Chọn `SameSite` có chủ đích** theo OAuth redirect, frontend/API origin và nhu cầu cross-site; không dựa vào mặc định browser.
5. **Áp dụng phòng chống CSRF** ở endpoint thay đổi trạng thái: CSRF token, Origin/Fetch Metadata và phương thức HTTP an toàn.
6. **Giới hạn host/path:** ưu tiên host-only cookie, cân nhắc `__Host-`, không khai báo `Domain` rộng khi không cần; nhớ Path không phải security boundary.
7. **Giới hạn thời gian và phía server:** cookie `Max-Age`, session TTL, timeout, session rotation và server-side invalidation.
8. **Giữ OAuth token phía backend nếu phù hợp:** BFF + session cookie giúp giảm token lộ cho JavaScript; vẫn phải bảo vệ BFF session.
9. **Bảo vệ refresh token:** lưu trữ phù hợp, rotation/reuse detection hoặc sender-constraining theo chính sách, thu hồi sau logout/consent changes khi cần.
10. **Không ghi credential vào log:** lọc `Cookie`, `Set-Cookie`, `Authorization`, exception, analytics, trace và URL.
11. **Xác minh token và quyền tại RS:** issuer, signature/introspection, audience, exp/nbf, scope và owner/tenant/permission; cookie flags không thay điều đó.
12. **Kiểm thử browser và hạ tầng:** cross-origin/CORS, TLS termination, prefixes, SameSite, CSRF, session fixation, logout và sử dụng lại bản sao cookie.

## Ghi nhớ

**`HttpOnly`** giới hạn JavaScript đọc/chỉnh sửa **cookie xác thực**, còn **`Secure`** hạn chế browser gửi cookie qua kết nối không an toàn. **Cả hai là điều kiện cần hữu ích, không phải cơ chế xác thực hay phân quyền đầy đủ**: browser vẫn có thể tự gửi cookie, do đó phải bảo vệ **CSRF**; JavaScript bị XSS vẫn có thể thao tác trong phiên; credential bị lộ ngoài JavaScript vẫn có thể bị phát lại. Kết hợp **`SameSite`, phạm vi host, HTTPS, quản lý session, bảo vệ token và chính sách quyền tại Resource Server**. Với web app có backend phù hợp, **BFF giữ OAuth token ở server và đặt opaque session ID trong cookie HttpOnly/Secure** là một thiết kế đáng cân nhắc, nhưng vẫn cần chống XSS, CSRF, session hijacking và thu hồi.

### Tài liệu tham khảo

- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265)
- [MDN — Set-Cookie HTTP response header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie)
- [MDN — Secure cookie configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
