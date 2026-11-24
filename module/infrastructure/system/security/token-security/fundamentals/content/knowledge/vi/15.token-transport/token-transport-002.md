# Cookie transport

## Mục tiêu học tập

Trong chương **Token transport** của học phần bảo mật token, **cookie transport** là cách trình duyệt nhận credential từ server qua `Set-Cookie`, lưu theo chính sách cookie và tự gửi lại bằng `Cookie` khi thực hiện request phù hợp. Đây là **cơ chế truyền tải**; nó khác với định dạng JWT/opaque, mục đích access/refresh token và quyết định phân quyền ở API.

Sau bài này, bạn có thể:

1. Mô tả trọn đường đi của cookie từ response `Set-Cookie` đến request `Cookie`, phân biệt với `Authorization: Bearer`.
2. Giải thích chính xác phạm vi gửi cookie qua **host, Domain, Path, scheme, SameSite, Secure**, cũng như chính sách trình duyệt.
3. Phân biệt **same-origin**, **same-site** và **cross-site** khi frontend gọi API; biết khi nào cần `fetch(..., { credentials: "include" })` và CORS.
4. Chứng minh vì sao cookie transport dễ gặp **CSRF**, kể cả khi có `HttpOnly` và `Secure`; áp dụng biện pháp chống CSRF phù hợp.
5. Lựa chọn **cookie session ở Backend for Frontend (BFF)** hoặc mô hình API nhận token trực tiếp qua cookie; giữ access token, refresh token và ID token đúng mục đích.
6. Xử lý cấp cookie, refresh, logout, rotation, proxy/CDN, logging và kiểm thử các luồng trình duyệt thật.

## 1. Cookie transport là gì?

Cookie transport diễn ra trên **hai chiều HTTP**:

- **Server → browser:** response có header `Set-Cookie` chỉ định tên, giá trị, phạm vi và thuộc tính cookie.
- **Browser → server:** các request sau được browser tự động đính kèm header `Cookie` khi thỏa điều kiện host, path, thời hạn, scheme, SameSite và quy tắc riêng của browser.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant App as Web App / BFF
    participant RS as Resource Server
    U->>B: Đăng nhập
    B->>App: POST /login (theo cơ chế xác thực)
    App->>App: Tạo hoặc xoay session ID
    App-->>B: Set-Cookie: __Host-session=...; Secure; HttpOnly
    B->>B: Lưu cookie theo chính sách browser
    B->>App: GET /orders + Cookie: __Host-session=...
    App->>App: Xác minh phiên và chính sách truy cập
    App->>RS: Authorization: Bearer access token (nếu dùng BFF)
    RS-->>App: Dữ liệu đã được phân quyền
    App-->>B: Phản hồi phù hợp
~~~

Trong sơ đồ, **browser không cần biết access token OAuth** khi BFF giữ token ở backend. Giá trị cookie có thể chỉ là **opaque session ID** trỏ tới phiên server. Đây là một kiến trúc phổ biến, **không phải yêu cầu bắt buộc của OAuth 2.0**.

### Một trao đổi HTTP rút gọn

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=<RANDOM_OPAQUE_ID>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=900
Cache-Control: no-store
Content-Type: application/json

{"authenticated":true}
~~~

Sau khi browser nhận và lưu:

~~~http
GET /account HTTP/1.1
Host: app.example.test
Cookie: __Host-session=<RANDOM_OPAQUE_ID>
~~~

`<RANDOM_OPAQUE_ID>` chỉ là placeholder, **không dùng chuỗi mẫu trong production**. Session ID phải được tạo bằng nguồn ngẫu nhiên mật mã, khó đoán, có thời hạn và trạng thái thu hồi phía server.

**Điểm quan trọng:** response **không gửi lại các thuộc tính** `Secure`, `HttpOnly`, `SameSite` hay `Path` trong request `Cookie`. Những thuộc tính ấy được browser áp dụng khi quản lý và lựa chọn cookie; server nhận header `Cookie` chỉ gồm tên–giá trị (và có thể nhiều cookie).

## 2. Cookie transport khác Authorization header ra sao?

OAuth 2.0 Bearer Token Usage (RFC 6750) chuẩn hóa việc gửi bearer access token, với cách dùng `Authorization` header được khuyến nghị:

~~~http
GET /orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

Trong khi đó, cookie transport dùng:

~~~http
GET /orders HTTP/1.1
Host: api.example.test
Cookie: __Host-session=<SESSION_ID>
~~~

Hai cách **khác nhau về ai quyết định gửi credential**:

| Tiêu chí | `Authorization` header | Cookie transport |
|---|---|---|
| Ai gắn credential vào request? | Code client hoặc HTTP client chủ động thêm header. | Browser tự gắn cookie phù hợp theo cookie policy. |
| Credential thường gặp | Bearer/DPoP-bound access token. | Session ID, đôi khi access/refresh token theo thiết kế. |
| Rủi ro CSRF do ambient credential | Không tự xuất hiện như cookie khi attacker chỉ khiến browser gửi form; vẫn tùy kiến trúc thực tế. | **Có**, nếu browser tự gắn cookie và server thiếu bảo vệ CSRF. |
| Rủi ro XSS | Script có quyền truy cập token có thể đọc/lạm dụng; script trong origin còn có thể gửi request. | `HttpOnly` cản việc script đọc cookie, **nhưng script vẫn có thể gửi request**. |
| Tương thích với OAuth Resource Server | Cách bearer token tiêu chuẩn khi API hỗ trợ RFC 6750. | Cần API/BFF chủ động hỗ trợ giải nghĩa cookie; không mặc định mọi RS đọc cookie. |
| Browser cross-origin | CORS khi dùng JavaScript fetch; header `Authorization` thường gây preflight. | CORS/credentials **và** chính sách cookie, SameSite, CSRF. |
| Non-browser clients | Dễ chủ động đính bearer token. | HTTP client phải có cookie jar/quản lý cookie nếu muốn dùng. |

### Đừng dùng cookie như một tên gọi khác của JWT

Một JWT có thể:

- Nằm trong `Authorization: Bearer <JWT>`.
- Được giữ ở backend rồi ánh xạ qua một session cookie.
- Được đặt trực tiếp làm giá trị một cookie **nếu kiến trúc định nghĩa cách nhận và xác minh đó**.

Ngược lại, một cookie `__Host-session` có thể chỉ chứa ID ngẫu nhiên; nó **không phải JWT** và không cần decode. **Transport ≠ token format ≠ token purpose.**

### Nếu một request mang cả Cookie và Authorization?

Đây là trường hợp cần **chính sách rõ ràng**. Nếu backend khi thì tin cookie phiên, khi thì tin bearer header tùy thứ tự ngẫu nhiên, có thể phát sinh **credential confusion**, chọn nhầm principal hoặc dùng quyền sai ngữ cảnh.

Ví dụ:

~~~http
GET /orders/42 HTTP/1.1
Host: api.example.test
Cookie: __Host-session=<SESSION_A>
Authorization: Bearer <TOKEN_FOR_USER_B>
~~~

Thiết kế cần quy định endpoint nào nhận cookie, endpoint nào nhận bearer token; nếu hai cơ chế cùng được phép, phải xác định cách xử lý credential trùng/sai principal, thường **từ chối yêu cầu mâu thuẫn** thay vì lặng lẽ chọn quyền rộng hơn.

## 3. Browser quyết định khi nào gửi cookie?

Browser không gửi tất cả cookie trong mọi request. Những thuộc tính sau cùng quyết định **phạm vi và thời điểm vận chuyển**:

| Thuộc tính | Ý nghĩa khi vận chuyển | Lưu ý |
|---|---|---|
| **Host và `Domain`** | Cookie được gửi tới host/domain phù hợp. | Bỏ `Domain` tạo **host-only cookie**, hạn chế lan sang subdomain. |
| **`Path`** | Browser chỉ gắn cookie vào request có path phù hợp. | Giảm phạm vi gửi, **không phải ranh giới bảo mật chắc chắn** giữa ứng dụng cùng origin. |
| **`Secure`** | Chỉ gửi qua kênh an toàn, thông thường HTTPS. | Không mã hóa giá trị cookie tại nơi lưu. |
| **`HttpOnly`** | Hạn chế API script đọc/sửa cookie. | Không cản browser tự gửi cookie khi script gọi request phù hợp. |
| **`SameSite`** | Điều chỉnh gửi cookie trong các ngữ cảnh same-site/cross-site. | Không thay CSRF protection và không đồng nghĩa CORS. |
| **`Max-Age` / `Expires`** | Quy định vòng đời cookie tại browser. | Session server hoặc token có thể hết hạn **sớm hơn** cookie. |
| **Browser policy** | Chính sách third-party cookie, privacy, partitioning và hạn mức. | `SameSite=None; Secure` không đảm bảo browser luôn gửi cookie. |

### Host-only cookie và Domain cookie

Với host:

~~~text
https://app.example.test
https://api.example.test
https://blog.example.test
~~~

Nếu `app.example.test` đặt cookie **không có `Domain`**, cookie thuộc **host app**, không mặc nhiên gửi tới `api.example.test` hoặc `blog.example.test`.

Nếu cookie được đặt:

~~~http
Set-Cookie: shared_session=<ID>; Domain=example.test; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Thì cookie có thể được gửi tới các subdomain phù hợp. Điều này **mở rộng ranh giới nhận credential**; không dùng `Domain` rộng để “sửa lỗi CORS” hoặc “giúp app gọi API” nếu không thực sự cần.

Một frontend `app.example.test` hoàn toàn có thể gọi API `api.example.test` khi cookie **host-only do chính `api.example.test` cấp**: cookie ấy được gửi tới API, dù **không** được gửi tới frontend host. Đây là cách giới hạn phạm vi tốt hơn khi API thực sự nhận cookie.

### Path không thay quyền truy cập

~~~http
Set-Cookie: refresh=<TOKEN>; Path=/auth/refresh; Secure; HttpOnly; SameSite=Strict
~~~

Cookie có thể chỉ tự gửi tới `/auth/refresh` hoặc các path phù hợp. Nhưng `Path` không cách ly bảo mật tuyệt đối giữa những đoạn mã, ứng dụng hoặc endpoint dùng chung origin. Nếu refresh token cần bảo vệ cao, còn phải kiểm soát token endpoint, CSRF, session, thu hồi, rotation và nguồn quyền.

### Prefix `__Host-` giúp giảm nhầm cookie giữa các host

~~~http
Set-Cookie: __Host-session=<OPAQUE_ID>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Browser hỗ trợ prefix `__Host-` yêu cầu cookie được đặt từ ngữ cảnh bảo mật phù hợp, **có `Secure`, có `Path=/` và không có `Domain`**. `__Secure-` yêu cầu `Secure` và ngữ cảnh bảo mật nhưng **không** áp đặt đầy đủ các hạn chế host-only như `__Host-`.

Prefix không tự yêu cầu `HttpOnly` và không thay bảo vệ CSRF, XSS, phân quyền hoặc thu hồi. Trong production, cần xem **header `Set-Cookie` thực tế** sau gateway/proxy để kiểm tra toàn bộ thuộc tính.

## 4. Same-origin, same-site và cross-site là ba ngữ cảnh quan trọng

### Origin là gì?

**Origin** thường được xác định bằng **scheme + host + port**. Ví dụ:

~~~text
A = https://app.example.test
B = https://api.example.test
C = https://app.example.test:8443
~~~

- A → B: **cross-origin** (khác host).
- A → C: **cross-origin** (khác port).

JavaScript fetch giữa hai origin chịu **Same-Origin Policy/CORS** về khả năng đọc response và một số quy tắc gửi request.

### Site là gì?

Theo mô hình cookie hiện đại, same-site thường xét **scheme** và **registrable domain** (khái niệm schemeful same-site). Với các host minh họa:

~~~text
https://app.example.test
https://api.example.test
~~~

Hai URL thường được coi là **same-site**, dù **cross-origin**. Còn:

~~~text
https://app.example.test
https://another.example.org
~~~

Là **cross-site**. Việc chuyển từ `https` sang `http` cũng có thể khiến request khác site theo quy tắc **schemeful SameSite**, kể cả cùng host/domain.

### Tại sao phân biệt này quan trọng?

`SameSite` là thuộc tính cookie dựa trên khái niệm **site**, trong khi **CORS dựa trên origin**. Một cookie `SameSite=Lax` có thể được gửi trong request same-site giữa `app.example.test` và `api.example.test` nếu Domain/host, Path, Secure và các điều kiện khác phù hợp; nhưng frontend vẫn cần **CORS** nếu muốn đọc response API khác origin.

**Đừng suy rằng same-site đồng nghĩa cùng mức độ tin cậy.** Một subdomain yếu bị attacker chiếm có thể tạo request **same-site** tới subdomain chứa API. `SameSite` vì thế **không phải biện pháp chống CSRF duy nhất** cho ứng dụng nhiều subdomain.

## 5. SameSite quyết định điều gì khi cookie được vận chuyển?

| Giá trị | Hành vi khái quát | Tác động thiết kế |
|---|---|---|
| **`Strict`** | Không gửi cookie trong request khởi phát cross-site theo quy tắc SameSite. | Hạn chế nhiều request từ site khác, nhưng có thể làm hỏng một số luồng đăng nhập/OAuth callback. |
| **`Lax`** | Có thể gửi cookie trong **top-level navigation** cross-site dùng phương thức an toàn, thường là GET; hạn chế nhiều trường hợp POST cross-site. | Thường phù hợp ứng dụng web có callback GET, nhưng không chống CSRF toàn diện. |
| **`None; Secure`** | Cho phép cookie dùng trong ngữ cảnh cross-site khi browser policy cho phép. | `Secure` bắt buộc trong browser hiện đại; cần CSRF defense và tính đến third-party cookie blocking. |

Hãy **đặt SameSite tường minh**, đừng phụ thuộc vào mặc định của từng browser. Một số mặc định thực tế có ngoại lệ ngắn hạn cho POST đối với cookie mới đặt, vì vậy không nên suy rằng cookie **không khai báo SameSite** tương đương tuyệt đối với `SameSite=Lax` tường minh.

### OAuth/OIDC callback là bài kiểm tra thực tế

Ví dụ browser đang ở `https://auth.example.test` (Authorization Server) rồi được redirect về `https://app.example.test/oauth/callback`.

~~~text
1. Browser -> app.example.test/login       : khởi tạo OAuth, lưu state/PKCE
2. Browser -> auth.example.test/authorize  : user đăng nhập/consent
3. AS -> Browser redirect                  : top-level GET về app callback
4. Browser -> app.example.test/callback    : cookie tương quan phiên có thể cần gửi
5. Backend kiểm tra state, PKCE, issuer và hoàn tất luồng
~~~

Nếu cookie giữ thông tin tương quan login transaction là `SameSite=Strict`, nó **có thể không được gửi** khi browser trở về app từ site khác; luồng dễ thất bại. `SameSite=Lax` thường thuận lợi với **top-level GET redirect**.

Nếu hệ thống dùng **OIDC `response_mode=form_post`** hoặc callback bằng POST cross-site, phải thiết kế cookie/correlation và CSRF phù hợp với request đó; **không** mặc định rằng Lax sẽ gửi cookie. Nếu thực sự cần `SameSite=None; Secure`, còn phải xét chính sách third-party cookie và bảo vệ khác.

`SameSite` **không thay thế** `state`, `nonce` khi profile cần, **PKCE** và việc kiểm tra authorization response. Đây là các lớp bảo vệ những rủi ro khác nhau.

## 6. Vì sao cookie transport cần chống CSRF?

**CSRF (Cross-Site Request Forgery)** xuất hiện khi attacker khiến browser của người dùng gửi request tới server đang nhận cookie xác thực, và server không kiểm tra đủ ý định/nguồn request.

~~~mermaid
sequenceDiagram
    actor U as Người dùng đang đăng nhập
    participant Evil as Website attacker
    participant B as Browser
    participant App as App có cookie session
    U->>Evil: Mở trang không tin cậy
    Evil->>B: Khiến browser gửi request thay đổi trạng thái
    B->>App: Request có thể kèm cookie phiên theo browser policy
    Note over App: Nếu thiếu CSRF/origin check, request có thể được thực thi
    App-->>B: Phản hồi
~~~

Attacker **không cần đọc cookie** để thử CSRF. `HttpOnly` làm script khó lấy giá trị cookie, `Secure` yêu cầu kết nối an toàn, nhưng **không chứng minh người dùng muốn thực hiện giao dịch**.

### Các lớp bảo vệ CSRF nên kết hợp

1. **Không dùng GET/HEAD cho hành động thay đổi trạng thái.** Một top-level GET cross-site có thể mang cookie `SameSite=Lax`.
2. **CSRF token** trên form và request thay đổi trạng thái, được ràng buộc với session hoặc thiết kế signed double-submit phù hợp.
3. **Kiểm tra `Origin`/`Referer`** so khớp nguồn đáng tin; có quy tắc khi header không hiện diện.
4. **Fetch Metadata** như `Sec-Fetch-Site`, `Sec-Fetch-Mode` làm tín hiệu chặn request cross-site nguy hiểm; không xem chúng là thay thế bắt buộc cho token trong mọi ứng dụng.
5. **`SameSite` phù hợp**, hạn chế subdomain không tin cậy và quyền của các endpoint.
6. **Kiểm tra authorization/step-up** cho chuyển tiền, hoàn tiền, thay đổi MFA hoặc hành động rủi ro cao.

Request minh họa khi ứng dụng dùng CSRF token:

~~~http
POST /account/change-email HTTP/1.1
Host: app.example.test
Cookie: __Host-session=<OPAQUE_SESSION_ID>
Content-Type: application/json
X-CSRF-Token: <TOKEN_BOUND_TO_SESSION>

{"email":"new-address@example.test"}
~~~

CSRF token có thể cần được **JavaScript hợp lệ** đọc qua HTML, endpoint được bảo vệ hoặc một kênh thiết kế riêng. **Đừng vì cần JS đọc CSRF token mà bỏ `HttpOnly` khỏi session/refresh token.**

### CORS không phải giải pháp CSRF đầy đủ

Một browser có thể **gửi** một số request cross-origin dù JavaScript attacker không thể đọc response do CORS. Vì vậy “API không bật CORS” hoặc “CORS chỉ cho app origin” **không đủ** thay cho CSRF defense khi server dùng cookie làm credential.

## 7. Cross-origin fetch với cookie: cả browser policy và CORS

Giả sử:

~~~text
Frontend: https://app.example.test
API:      https://api.example.test
~~~

Frontend gọi API:

~~~javascript
const response = await fetch("https://api.example.test/orders", {
  method: "GET",
  credentials: "include"
});

if (!response.ok) {
  throw new Error("Request failed");
}
const orders = await response.json();
~~~

`credentials: "include"` cho phép browser sử dụng credentials trong request cross-origin theo quy tắc tương ứng. Nhưng **nó không ép browser gửi cookie không khớp domain/path, bị SameSite chặn hoặc bị chính sách cookie chặn**.

### Phản hồi CORS đúng cho credentialed request

Nếu API đã cho phép origin frontend gọi bằng credentials, phản hồi có thể gồm:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

- `Access-Control-Allow-Origin` phải là **origin được phép cụ thể**, không dùng `*` với credentialed CORS response để mong browser cho phép script đọc.
- `Access-Control-Allow-Credentials: true` là điều kiện của credentialed CORS response; nó **không tự giải quyết** CSRF hoặc cookie restrictions.
- Nếu phản chiếu `Origin` theo yêu cầu, server **phải validate bằng allowlist đáng tin**, không phản chiếu mọi origin bất kỳ.
- Với method/header cần preflight, cấu hình `OPTIONS` và các header được phép đúng giao thức, không dựa vào cookie login của preflight như cơ chế bảo mật.

### Phát cookie từ response cross-origin

Nếu frontend gọi API bằng `fetch` và API phản hồi `Set-Cookie`, browser chỉ lưu cookie trong điều kiện chính sách credentials/CORS/cookie cho phép. Ví dụ:

~~~javascript
await fetch("https://api.example.test/session", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-Token": csrfToken
  },
  body: JSON.stringify({ action: "establish" })
});
~~~

Ứng dụng không thể lấy `Set-Cookie` bằng `response.headers.get("Set-Cookie")` trong trình duyệt: header này bị lọc khỏi JavaScript vì lý do bảo mật. Việc không đọc được header bằng JavaScript **không chứng minh** cookie không được browser lưu; cần xem browser cookie storage/network diagnostics.

Một cookie được cấp từ `api.example.test` mà **không có `Domain`** có thể là host-only và **chỉ gửi đến API host**, dù frontend ở `app.example.test`. Không cần cố đặt `Domain=example.test` trừ khi nghiệp vụ thật sự yêu cầu chia sẻ.

### Cross-site và third-party cookie blocking

Nếu frontend `https://shop.example.test` gọi API tại `https://api.other.test`, đây là **cross-site**. Dù cookie có `SameSite=None; Secure` và JS dùng `credentials: "include"`, browser vẫn có thể **chặn third-party cookie** theo chính sách quyền riêng tư hoặc môi trường người dùng.

Không coi đây luôn là lỗi backend thiếu `HttpOnly`. Cần kiểm tra cấu hình browser và cân nhắc **same-site BFF**, điều hướng đăng nhập phù hợp hoặc kiến trúc không phụ thuộc vào third-party cookie.

## 8. Mô hình được khuyến nghị cân nhắc: BFF và session cookie

Trong ứng dụng web có backend đáng tin, **Backend for Frontend** thường giúp tránh đưa access/refresh token OAuth trực tiếp cho JavaScript.

### Phân công trách nhiệm

| Thành phần | Giữ hoặc gửi credential nào? | Kiểm soát quan trọng |
|---|---|---|
| **Browser** | Opaque session ID trong cookie `HttpOnly; Secure; SameSite`. | Chống XSS/CSRF, cookie policy, không lộ session. |
| **BFF** | Session store, access token và refresh token nếu có. | Session fixation protection, token lifecycle, refresh rotation/revocation, quyền truy cập kho token. |
| **Authorization Server** | Grant và token đã cấp theo client/user/resource/scope. | Issuance policy, client, PKCE/consent, audience, TTL. |
| **Resource Server** | Nhận access token do BFF trình qua `Authorization` hoặc cơ chế đã định nghĩa. | Xác minh issuer/audience/scope/trạng thái và object-level authorization. |

~~~mermaid
sequenceDiagram
    actor U as User
    participant B as Browser
    participant F as BFF
    participant AS as Authorization Server
    participant API as Orders API
    B->>F: GET /login
    F->>AS: Authorization request (redirect qua browser)
    AS-->>F: Authorization code (qua browser callback)
    F->>AS: Token request (PKCE, client auth nếu áp dụng)
    AS-->>F: Access token, có thể refresh token
    F->>F: Lưu token an toàn; phát session ID
    F-->>B: Set-Cookie: __Host-session=...; Secure; HttpOnly
    B->>F: GET /orders + session Cookie
    F->>F: Validate session, CSRF/Origin khi cần
    F->>API: Authorization: Bearer <ACCESS_TOKEN>
    API->>API: Check iss/aud/scope/ownership/tenant
    API-->>F: Dữ liệu được phép
    F-->>B: Phản hồi
~~~

Đây là mô tả kiến trúc; các lần **redirect qua browser** được đơn giản hóa trong sơ đồ, không phải kết nối trực tiếp user-agent với AS bằng backend call ở mọi bước. BFF cần quản lý `state`, PKCE, kiểm tra authorization response, refresh token và session theo giao thức thực tế.

### BFF giảm rủi ro gì?

BFF giữ token OAuth trong backend nên giảm khả năng JavaScript của frontend **đọc và đem access/refresh token ra ngoài**. Browser chỉ có session cookie host-only. Khi token OAuth hết hạn, BFF xử lý refresh theo chính sách; browser không phải tự gửi refresh token tới token endpoint.

**Giới hạn:** XSS trong trang vẫn có thể gửi request tới BFF khi session còn hiệu lực; CSRF vẫn là rủi ro nếu browser tự đính cookie; session ID vẫn có thể bị đánh cắp từ thiết bị hoặc log. BFF **không thay** xác minh quyền ở API.

## 9. Nếu API nhận access token trực tiếp qua cookie

Một số hệ thống chủ động đặt access token JWT/opaque trong cookie rồi để API đọc giá trị từ `Cookie`. Mô hình này cần ghi rõ là **quy ước của ứng dụng**, không phải giả định mặc định rằng mọi OAuth Resource Server đều hiểu token trong cookie.

Ví dụ minh họa:

~~~http
GET /orders HTTP/1.1
Host: api.example.test
Cookie: __Host-access=<ACCESS_TOKEN_PLACEHOLDER>
~~~

API phải:

1. **Trích cookie chính xác** theo tên đã quy định, xử lý cookie thiếu/trùng/sai cấu trúc.
2. Xác minh token như bình thường: JWT signature/`iss`/`aud`/`exp`/`nbf`/loại token, hoặc introspection opaque token.
3. Kiểm tra `scope`, trạng thái thu hồi và quyền trên từng order, tenant, user.
4. Chống CSRF cho endpoint sử dụng **cookie như credential ambient**.
5. Hạn chế host/path/TTL và log giá trị cookie; không cho cookie mang token dành cho một API bị phát tán đến host khác.

**Đừng nhầm** cookie `HttpOnly` với khả năng tự chứng minh issuer hoặc audience. Một token có `aud=billing-api` vẫn phải bị Orders API từ chối dù cookie được gửi đúng host.

### Vì sao cookie không phải lúc nào cũng phù hợp cho JWT dài?

Cookie được gửi trong **nhiều request tới host/path phù hợp**, kể cả khi endpoint không cần token. JWT chứa nhiều claims có thể lớn và làm tăng:

- Kích thước header/chi phí băng thông cho mỗi request.
- Rủi ro vượt giới hạn kích thước header của browser, reverse proxy hoặc server, dẫn đến lỗi như HTTP `431 Request Header Fields Too Large`.
- Diện lộ nếu logging/monitoring vô tình ghi `Cookie`.

Hạn mức cookie khác nhau theo browser/hạ tầng; không đặt giả thiết “một cookie luôn được phép tới N byte” mà không kiểm chứng. **Opaque session ID ngắn** với state server-side có thể phù hợp hơn khi website dùng session lâu dài.

### Refresh token trong cookie?

Nếu hệ thống quyết định đưa refresh token vào cookie, cần hạn chế cực kỳ cẩn thận:

- Chỉ gửi tới endpoint được thiết kế để **refresh**, không gửi bừa đến API nghiệp vụ.
- Dùng `HttpOnly; Secure`, `SameSite` và phạm vi host/path hẹp theo threat model.
- Kiểm tra **CSRF/Origin** cho luồng refresh nếu browser tự gửi cookie.
- AS/BFF phải áp dụng rotation, reuse detection hoặc sender-constraining theo loại client/chính sách.
- Không đưa refresh token vào JavaScript, URL hoặc log.

**Refresh token không phải access token**: không được chấp nhận nó ở Resource Server chỉ vì cùng là credential có trong cookie.

## 10. Phiên, refresh, logout và thu hồi trên đường truyền cookie

### Khi login thành công

Server cần tạo hoặc xoay session ID, tránh **session fixation**. Session ID được gửi qua `Set-Cookie` từ response tin cậy; backend gắn ID với trạng thái phiên và principal đã xác minh.

### Khi nâng quyền hoặc xác thực lại

Nếu user từ phiên khách trở thành user đăng nhập, hoặc chuyển sang phiên quyền cao, framework nên **rotate session ID** theo chính sách. Không tự nâng vai trò của một session ID cũ do attacker có thể đã biết.

### Khi access token phía BFF hết hạn

BFF có thể dùng refresh token đã giữ an toàn để xin access token mới trong phạm vi grant. Refresh token rotation và trạng thái thu hồi phải được xử lý độc lập với thời hạn cookie của browser. Một cookie còn hiệu lực **không chứng minh refresh grant còn hợp lệ**.

### Khi logout

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant F as BFF
    participant AS as Authorization Server
    B->>F: POST /logout + Cookie session + CSRF
    F->>F: Invalidate session tại server
    F->>AS: Revoke token/grant nếu policy yêu cầu
    F-->>B: Set-Cookie session rỗng, Max-Age=0
    B->>F: Thử lại với bản sao session ID cũ
    F-->>B: Từ chối vì ID đã bị vô hiệu hóa
~~~

Xóa cookie phía trình duyệt **không đủ** nếu session ID cũ vẫn được server chấp nhận. Backend phải vô hiệu hóa session, và xử lý access/refresh token liên quan theo chính sách.

~~~http
HTTP/1.1 204 No Content
Set-Cookie: __Host-session=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0
Cache-Control: no-store
~~~

Để xóa cookie cần dùng tên/`Path`/`Domain` tương ứng với cookie lúc tạo. Với `__Host-session` không có `Domain`, việc xóa cũng không cần `Domain`.

**Lưu ý thu hồi JWT:** nếu access token JWT đã được đưa ra ngoài và Resource Server chỉ kiểm tra chữ ký/`exp`, việc BFF logout hoặc browser xóa cookie **không bảo đảm bản sao JWT đã lộ bị vô hiệu hóa ngay**. Cần TTL, introspection/denylist/thu hồi hoặc kiểm tra trạng thái theo mức rủi ro.

## 11. Cấu hình HTTP và Java/Spring minh họa

### ResponseCookie phát cookie phiên

Ví dụ Spring gửi **opaque session ID**, không gửi JWT nhạy cảm về JavaScript:

~~~java
import java.time.Duration;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;

final class CookieTransport {
    static void issueSession(
            HttpServletResponse response,
            String serverGeneratedOpaqueSessionId) {
        // ID phải do session service tạo bằng CSPRNG.
        ResponseCookie cookie = ResponseCookie
                .from("__Host-session", serverGeneratedOpaqueSessionId)
                .secure(true)
                .httpOnly(true)
                .sameSite("Lax")
                .path("/")
                .maxAge(Duration.ofMinutes(15))
                .build();
        response.addHeader(HttpHeaders.SET_COOKIE, cookie.toString());
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
    }
}
~~~

Không có `Domain`, phù hợp prefix `__Host-`. Ví dụ này chỉ **phát cookie**: chưa triển khai xác thực, session store, rotation, CSRF, login flow hoặc authorization. Không tạo session ID từ timestamp, user ID hoặc `java.util.Random`.

### Spring Boot session cookie

Nếu dùng session của Servlet container, cấu hình tham khảo (xác nhận property theo phiên bản Spring Boot hiện tại của dự án):

~~~yaml
server:
  servlet:
    session:
      cookie:
        name: __Host-session
        secure: true
        http-only: true
        same-site: lax
        path: /
~~~

Session timeout và invalidation phía backend được quản lý **riêng**. Sau khi triển khai sau CDN/proxy, phải kiểm tra thực tế response `Set-Cookie` không bị thêm `Domain`, thiếu `Secure` hoặc sai `SameSite`.

### Bảo vệ web endpoints dùng cookie session

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/health").permitAll()
            .anyRequest().authenticated())
        .csrf(Customizer.withDefaults());

    // Session authentication và cơ chế login cần được cấu hình riêng.
    // Giữ CSRF protection cho các endpoint dùng cookie xác thực.
    return http.build();
}
~~~

Không tắt CSRF toàn ứng dụng chỉ vì `SameSite=Lax` hoặc `HttpOnly`. Nếu frontend SPA cần gửi CSRF token, thiết kế phương thức cấp token hợp lệ (HTML/meta tag, CSRF endpoint hoặc repository phù hợp) và header đối chiếu; cookie xác thực **vẫn nên HttpOnly**.

### Controller/API chỉ nên đọc credential từ nguồn tin cậy

Đoạn mã **minh họa anti-pattern**:

~~~java
// KHÔNG NÊN: nhận "userId" từ cookie do client tự khai báo
// rồi coi đó là principal đã xác thực.
String userId = request.getCookies()[0].getValue();
return orderRepository.findAllByOwnerId(userId);
~~~

Thay vào đó:

1. Middleware xác minh **session ID** tại session store hoặc xác minh access token theo profile.
2. Framework tạo **principal/security context** đã được xác minh.
3. Controller/service chỉ nhận principal đã xác thực và kiểm tra **scope, audience, tenant, owner, action** của request.

Cookie có thể bị sửa ở client; **mọi giá trị cookie đầu vào đều phải được coi là không tin cậy cho đến khi được xác minh**.

## 12. Proxy, CDN, HTTPS và các nguy cơ truyền qua hạ tầng

### Chỉ bật Secure ở browser có đủ không?

Không. `Secure` điều khiển hành vi **browser**. Nếu reverse proxy nhận HTTPS nhưng nối HTTP không được bảo vệ tới backend qua mạng có rủi ro, credential vẫn có thể bị lộ ở đoạn hạ tầng đó. Cần bảo vệ kết nối proxy–backend, phân quyền proxy/service mesh và tránh log credentials.

### Forwarded headers có thể bị giả mạo

Backend có thể dựa vào `X-Forwarded-Proto`/`Forwarded` để xác định request gốc có HTTPS hay không. Chỉ tin metadata từ **proxy được kiểm soát**, phải xóa/ghi đè forwarded headers do client Internet tự cung cấp. Nếu sai, app có thể phát cookie thiếu `Secure`, tạo redirect không an toàn hoặc xử lý callback sai scheme.

### Cache response có credential

Response xác thực, token response hoặc nội dung riêng tư cần chính sách cache phù hợp, ví dụ `Cache-Control: no-store` khi có dữ liệu nhạy cảm. CDN/shared cache không được vô tình lưu và phục vụ `Set-Cookie` hoặc dữ liệu user A cho user B; kiểm tra `Vary`, cookie forwarding và chính sách cache route của hạ tầng.

### Không ghi Cookie/Set-Cookie vào log

Kiểm tra:

- Access log ở CDN/proxy/API có ghi `Cookie` hay `Set-Cookie` không?
- Trace/Apm có lưu cả `Authorization` hoặc query login callback không?
- Lỗi exception có dump toàn bộ request headers không?
- Công cụ support có nhận nguyên session/access/refresh token không?

Nên redaction credential tại mọi tầng. Token/cookie bị lộ từ log **có thể bị replay** nếu còn hiệu lực; `HttpOnly` và `Secure` không bảo vệ giá trị sau khi nó bị server log.

## 13. Chẩn đoán lỗi cookie không được gửi

Khi frontend báo “đã login nhưng API trả 401”, cần phân biệt **cookie không được vận chuyển** với **cookie đã gửi nhưng session/token không hợp lệ**:

~~~mermaid
flowchart TD
    A["API request bị 401"] --> B{"Request có Cookie header phù hợp?"}
    B -- Không --> C{"Cookie đã được browser lưu?"}
    C -- Không --> D["Kiểm tra Set-Cookie, Secure, prefix, third-party policy"]
    C -- Có --> E["Kiểm tra Domain/Path/SameSite, scheme, credentials"]
    E --> F["Kiểm tra CORS nếu cross-origin và browser diagnostics"]
    B -- Có --> G{"Backend xác minh session/token thành công?"}
    G -- Không --> H["Session hết hạn/thu hồi; JWT sai iss/aud/exp; kho session lỗi"]
    G -- Có --> I{"Action có đủ scope/ownership/tenant?"}
    I -- Không --> J["403 hoặc 404 theo policy"]
    I -- Có --> K["Kiểm tra routing, middleware và response logic"]
~~~

| Hiện tượng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Không thấy cookie được lưu | `Set-Cookie` sai `Secure`/`SameSite`/prefix, Domain không hợp lệ, browser policy chặn. | Network panel và lý do cookie bị block. |
| Cookie lưu nhưng không đi tới API | Host-only cookie thuộc app, API khác host; Path không khớp; SameSite chặn; thiếu `credentials: "include"`. | Cookie attributes, URL request, fetch credentials. |
| Cookie đi rồi nhưng JS không đọc được response | Credentialed CORS thiếu hoặc sai ACAO/ACC; preflight lỗi. | CORS response và browser console; không nhầm với cookie mất. |
| Cookie gửi nhưng 401 | Session bị xóa/hết hạn, token không hợp lệ, sai issuer/audience, key rotation, trạng thái thu hồi. | Server-side authentication audit có redaction. |
| Cookie gửi, xác thực thành công nhưng 403 | Thiếu scope/role/permission hoặc sai tenant/owner. | Authorization policy, không tự refresh token liên tục. |
| OAuth callback mất correlation session | SameSite Strict hoặc callback POST cross-site không gửi cookie. | Redirect mode, state/PKCE, SameSite và browser policy. |
| Chỉ xảy ra sau proxy/CDN | Header `Set-Cookie` bị đổi/bỏ; sai scheme forwarded; cache nhầm user. | Headers trước/sau proxy, trust boundary, cache config. |
| Có lỗi 431 hoặc 400 khi request | Cookie/header quá lớn, nhiều cookie trùng, JWT quá dài. | Kích thước Cookie header và hạn mức hạ tầng. |

**Đừng sửa mọi lỗi 401 bằng cách đặt `SameSite=None`, tắt CSRF hoặc chuyển session token sang `localStorage`.** Trước tiên phải tìm đúng nguyên nhân.

## 14. Các ngộ nhận về Cookie transport

| Ngộ nhận | Vì sao sai? | Cách hiểu đúng |
|---|---|---|
| “Cookie là JWT.” | Cookie là phương tiện truyền tên–giá trị; có thể chứa ID opaque. | Phân biệt transport, format và purpose. |
| “HttpOnly làm JavaScript không thể gửi request có cookie.” | Browser vẫn tự đính cookie vào request phù hợp. | HttpOnly chủ yếu hạn chế JS đọc/sửa cookie. |
| “Secure mã hóa cookie trong máy.” | Secure yêu cầu kênh truyền an toàn. | Bảo vệ local storage và thiết bị riêng. |
| “SameSite=Lax ngăn mọi CSRF.” | Top-level GET cross-site có thể mang cookie; same-site subdomain và các tình huống khác vẫn cần policy. | CSRF token/Origin/Fetch Metadata và không đổi state qua GET. |
| “Khác origin nghĩa là khác site.” | Subdomain có thể khác origin nhưng cùng site. | Phân biệt CORS và SameSite. |
| “`credentials: include` bắt browser gửi cookie bất kể chính sách.” | Domain, SameSite, Secure và third-party policy vẫn quyết định. | Kiểm tra đầy đủ cookie scope. |
| “CORS chặn mọi request cross-site.” | CORS chủ yếu điều chỉnh JS đọc response, không phải CSRF defense hoàn chỉnh. | Thiết kế CSRF riêng. |
| “Muốn frontend và API dùng chung cookie phải đặt Domain rộng.” | API có thể dùng host-only cookie của chính API. | Ưu tiên cookie giới hạn đúng host cần nhận. |
| “Có cookie HttpOnly thì BFF tuyệt đối an toàn trước XSS.” | XSS vẫn có thể gửi request cùng origin. | Chống XSS và kiểm tra quyền nghiệp vụ. |
| “Xóa cookie khi logout là thu hồi session.” | Bản sao ID cũ vẫn có thể được server chấp nhận. | Invalidate session server-side; xử lý grant/token. |
| “JWT đúng cookie path thì API bỏ qua audience.” | Cookie scope không chứng minh token được cấp cho API. | RS phải validate issuer/audience/scope. |
| “Chỉ cần HttpOnly/Secure nên không cần TLS nội bộ.” | Browser flags không bảo vệ đoạn proxy–backend. | Bảo vệ transport ở từng trust boundary. |

## 15. Ma trận kiểm thử Cookie transport

Giả sử ứng dụng `https://app.example.test` dùng session ID trong cookie `__Host-session` với `Path=/; Secure; HttpOnly; SameSite=Lax`, không `Domain`. Backend xác minh session tại server và có CSRF protection:

| Trường hợp | Kết quả kỳ vọng | Điều kiểm chứng |
|---|---|---|
| Browser nhận `Set-Cookie` hợp lệ từ HTTPS app | Lưu cookie nếu browser policy cho phép. | Thiết lập transport. |
| Server gửi `__Host-session` nhưng có `Domain=example.test` | Browser hỗ trợ prefix phải từ chối cookie đó. | Ràng buộc `__Host-`. |
| JS đọc `document.cookie` | Không đọc được cookie session HttpOnly. | Giới hạn script. |
| Browser gọi same-origin `GET /account` | Có thể gửi cookie phù hợp. | HttpOnly không ngăn request. |
| Browser gọi `http://app.example.test` | Không gửi cookie Secure trong trường hợp production thông thường. | Bảo vệ scheme. |
| Browser gọi `https://api.example.test` | Không tự gửi host-only cookie của app. | Phạm vi host. |
| Cookie với `Domain=example.test` tới blog subdomain | Có thể được gửi, cho thấy rủi ro phạm vi rộng. | Domain scope. |
| `SameSite=Lax` gặp top-level GET từ site khác | Cookie có thể được gửi; endpoint GET không được đổi trạng thái. | SameSite và safe methods. |
| Cross-site POST thực hiện thao tác nhạy cảm | Bị từ chối nếu thiếu CSRF/Origin hợp lệ, dù cookie được gửi. | CSRF defense. |
| Frontend cross-origin fetch không dùng `credentials: "include"` | Cookie thường không được gửi trong fetch cross-origin. | Fetch credentials mode. |
| Credentialed CORS dùng `Access-Control-Allow-Origin: *` | Browser không cho JS đọc response theo policy. | CORS cấu hình đúng. |
| Cross-origin response có `Set-Cookie`, JS gọi `headers.get("Set-Cookie")` | Không đọc trực tiếp được header đó từ JS. | Forbidden response header. |
| Browser chặn third-party cookie dù SameSite=None | Cookie không gửi/lưu theo browser policy. | Third-party restrictions. |
| OAuth callback GET với cookie Strict và AS khác site | Có thể mất cookie tương quan; login phải xử lý an toàn. | Callback behavior. |
| Cookie session vẫn còn nhưng session server hết hạn | 401/từ chối. | Server-side expiry. |
| Logout rồi trình lại bản sao session ID | Từ chối vì backend invalidated. | Logout/replay. |
| Cookie gửi nhưng access token backend sai `aud` | Resource Server từ chối. | Token validation. |
| Cookie gửi, token hợp lệ nhưng order thuộc tenant khác | 403/404 theo policy. | Object-level authorization. |
| CDN/proxy ghi header `Cookie` vào log | Kiểm thử/kiểm toán phải phát hiện và loại bỏ. | Tránh lộ credential. |

Test nên chạy trên **trình duyệt thật**, kết hợp request network inspection và test backend. Unit test Java chỉ xác nhận chuỗi `Set-Cookie` **không đủ** để chứng minh cookie được browser gửi/không gửi đúng ở callback, cross-origin, SameSite và third-party contexts.

## 16. Tình huống suy luận

**Tình huống A — Cookie tự gửi.** Browser đã đăng nhập qua cookie HttpOnly. Một script XSS trong origin gọi `POST /orders/42/cancel`. Script không đọc được session ID; liệu request có thể được gửi kèm cookie không?

**Giải thích:** Có. Browser vẫn tự đính cookie khi request phù hợp. HttpOnly giảm khả năng trích xuất trực tiếp chuỗi cookie, không ngăn XSS thao tác trong phiên. Phải chống XSS, kiểm tra action, scope và quyền đối tượng.

**Tình huống B — Cross-origin nhưng cùng site.** Frontend `app.example.test` gọi API `api.example.test` bằng `fetch`; API phát cookie host-only của chính API. Có cần đặt `Domain=example.test` để browser gửi cookie cho API không?

**Giải thích:** Không. Cookie host-only từ API có thể gửi lại chính API host, nếu credentials mode và các thuộc tính khác cho phép. Frontend vẫn cần CORS đúng để đọc response vì khác origin.

**Tình huống C — CORS thay CSRF?** API chỉ cho `Access-Control-Allow-Origin: https://app.example.test`, nhưng chấp nhận cookie trên `POST /transfer` và không có CSRF defense. Đã an toàn chưa?

**Giải thích:** Chưa. Browser có thể gửi một số request cross-origin mà script bên ngoài không đọc được response. CORS không thay CSRF token/Origin và policy action.

**Tình huống D — OAuth callback qua POST.** Ứng dụng dùng SameSite=Lax cho cookie chứa dữ liệu tương quan login, nhưng AS trả kết quả qua cross-site form POST. Có bảo đảm cookie được gửi không?

**Giải thích:** Không. Lax tường minh thường không gửi cookie trong cross-site POST. Thiết kế phải chọn response mode, cookie/correlation và biện pháp CSRF thích hợp, không bỏ kiểm tra `state` hoặc PKCE.

**Tình huống E — SameSite=None vẫn không có cookie.** Browser chặn third-party cookies; frontend gọi API ở site khác với `credentials: include`. Có thể chỉ thêm `HttpOnly` để sửa không?

**Giải thích:** Không. HttpOnly không điều khiển third-party cookie policy. Cần xem browser diagnostics và cân nhắc same-site/BFF hoặc kiến trúc khác.

**Tình huống F — BFF logout.** BFF gửi `Set-Cookie: __Host-session=; Max-Age=0` nhưng không vô hiệu hóa session trong kho. Attacker có bản sao ID cũ. Có rủi ro gì?

**Giải thích:** Attacker có thể dùng lại ID cho đến khi session server hết hiệu lực. Cần invalidate server-side và xử lý refresh/access token liên quan theo policy.

**Tình huống G — Cookie chứa access token sai API.** Cookie gửi được đến Orders API nhưng JWT có `aud=billing-api`, chữ ký đúng. Orders có thể chấp nhận vì cookie thuộc đúng host không?

**Giải thích:** Không. Cookie chỉ giúp vận chuyển chuỗi; RS vẫn bắt buộc kiểm tra issuer, audience, token purpose, thời hạn, scope và quyền trên đối tượng.

**Tình huống H — Proxy và Secure.** Browser truy cập HTTPS đến proxy, backend nhìn thấy HTTP nội bộ và cố xóa thuộc tính Secure để “cookie hoạt động”. Đây có phải cách sửa đúng?

**Giải thích:** Không. Cần cấu hình TLS termination và forwarded headers qua **trust boundary đã kiểm soát**, duy trì `Secure` ở cookie auth và bảo vệ đường proxy–backend. Không cho client tùy ý giả scheme.

## Checklist triển khai Cookie transport

1. **Xác định credential thật:** session ID, access token hay refresh token? Tách mục đích và nơi được phép nhận.
2. **Định nghĩa transport:** browser gửi `Cookie` tới BFF hoặc API; downstream API dùng `Authorization` hay cơ chế được thỏa thuận riêng.
3. **Hạn chế cookie scope:** host-only nếu có thể; `Path` đúng nhu cầu; cân nhắc `__Host-` và tránh `Domain` rộng.
4. **Bảo vệ trên browser:** `Secure; HttpOnly; SameSite` phù hợp, HTTPS/TLS, HSTS khi môi trường sẵn sàng.
5. **Thiết kế CSRF:** token, Origin/Fetch Metadata, phương thức HTTP đúng và chính sách riêng cho endpoint nhạy cảm.
6. **Thiết kế OAuth callback:** Authorization Code + PKCE, `state`/`nonce` khi cần; kiểm thử SameSite với redirect GET hoặc form POST.
7. **Thiết kế cross-origin:** fetch credentials, CORS allowlist, ACC/ACAO, third-party cookie policies; đừng phản chiếu mọi Origin.
8. **Lựa chọn kiến trúc:** cân nhắc BFF + opaque session cookie và giữ OAuth token ở backend thay vì đưa refresh token cho JavaScript.
9. **Quản lý vòng đời:** session rotation sau login/đổi quyền, TTL, refresh token rotation, logout và invalidation phía server.
10. **Bảo vệ hạ tầng:** cache, proxy, forwarded headers, TLS hop, redaction `Cookie`/`Set-Cookie`/`Authorization` trong log.
11. **Không bỏ token validation:** issuer, audience, token type, exp/nbf, scope và quyền trên owner/tenant/resource tại RS.
12. **Kiểm thử phủ định:** cookie không gửi, cookie gửi nhầm host, CSRF, XSS thao tác, cross-origin, callback, replay ID cũ, cookie quá lớn và proxy spoofing.

## Ghi nhớ

**Cookie transport** là việc browser **nhận credential qua `Set-Cookie` và tự gửi lại qua `Cookie` theo chính sách cookie**. Nó tiện cho session web nhưng tạo đặc tính **ambient credential**, nên cần chống CSRF ngoài `HttpOnly`, `Secure` và `SameSite`. **SameSite dựa trên site; CORS dựa trên origin** và không thay thế nhau. Với ứng dụng OAuth/OIDC trên web, mô hình **BFF giữ access/refresh token phía server, browser giữ opaque session cookie** thường giúp hạn chế lộ OAuth token tới JavaScript, nhưng vẫn phải quản lý session và chống XSS/CSRF. Dù token đi qua cookie hay `Authorization` header, **Resource Server luôn phải xác minh token và quyền trên từng tài nguyên**; một giá trị bị đánh cắp vẫn có thể bị phát lại nếu không có kiểm soát vòng đời phù hợp.

### Tài liệu tham khảo

- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie)
- [MDN — Request.credentials / Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
