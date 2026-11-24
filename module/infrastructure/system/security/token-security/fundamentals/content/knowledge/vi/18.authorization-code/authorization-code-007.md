# Authorization code lifetime

Trong luồng **OAuth 2.0 Authorization Code**, Authorization Server (AS) không trả access token trực tiếp qua browser. Sau khi user đã được xác thực và yêu cầu ủy quyền được chấp thuận, AS phát hành **authorization code** — một giá trị khó đoán, có hiệu lực **rất ngắn**, dùng để client đổi lấy token tại **token endpoint**. Cửa sổ hiệu lực ngắn giúp giảm cơ hội khai thác khi code bị ghi vào URL callback, trình duyệt, proxy hoặc hệ thống log.

Bài học **“Authorization code lifetime”** thuộc chương **Authorization Code** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Chủ đề gắn với mô hình tin cậy, vòng đời phát hành–kiểm tra–hết hạn–thu hồi, phân biệt JWT và opaque token, access/refresh/ID token, kiểm tra client, redirect URI, PKCE, issuer, audience, scope, cũng như phòng chống việc mã ủy quyền bị đánh cắp hoặc phát lại.

> **Thông điệp chính:** authorization code phải **hết hạn nhanh, chỉ đổi được một lần, gắn với đúng client/redirect và PKCE transaction**. Thời hạn ngắn **không thay thế** việc tiêu thụ nguyên tử, bảo vệ code trong URL hay kiểm tra grant trước khi cấp token.

## 1. Authorization code là gì — và không phải là gì?

Authorization code là một **authorization grant dạng tạm thời** mà AS cấp cho một client thông qua redirect sau khi authorization request được xử lý. Client trình nó ở token endpoint để xin token, kèm các bằng chứng và ràng buộc phù hợp.

| Hiện vật | Nơi dùng đúng | Mục đích | Quan hệ với lifetime |
|---|---|---|---|
| **Authorization code** | Token endpoint của chính AS đã cấp | Đổi **một lần** thành token theo grant | **Rất ngắn**, bắt đầu từ khi AS phát hành code |
| **Access token** | Resource Server có audience tương ứng | Gọi API trong phạm vi quyền được cấp | Có `exp` hoặc trạng thái/thời hạn khác theo profile |
| **Refresh token** | AS token endpoint | Xin access token mới nếu grant còn hiệu lực | Chính sách riêng, rotation và revocation; **không dùng lại code** |
| **ID token (OIDC)** | OIDC Client/Relying Party | Thông tin về sự kiện authentication | Kiểm tra `iat`, `exp`, `aud`, `iss` và các ràng buộc OIDC |
| **PKCE code_verifier** | Token endpoint trong quá trình đổi code | Chứng minh client sở hữu bí mật gắn `code_challenge` | Chỉ giữ trong vòng đời transaction; không phải authorization code |
| **OAuth `state`** | Authorization request/callback của client | Liên kết response với request ban đầu | Client quản lý transaction TTL riêng |

**Authorization code không phải access token.** API nghiệp vụ không được chấp nhận code tại `Authorization: Bearer`. Code cũng không phải refresh token và không thể dùng để xin nhiều bộ token khi access token hết hạn.

Một authorization code có thể được AS triển khai như chuỗi opaque ngẫu nhiên và tra trạng thái server-side. Định dạng chi tiết **không do RFC 6749 bắt buộc là JWT**. Nếu hệ thống dùng code tự chứa, nó vẫn phải đáp ứng **hết hạn, dùng một lần và binding**; chữ ký hợp lệ đơn lẻ không chứng minh code chưa bị dùng.

## 2. RFC 6749 quy định lifetime và single-use thế nào?

**RFC 6749, Section 4.1.2**, đặt ra ba nhóm yêu cầu quan trọng cho authorization code:

1. Code **MUST** hết hạn ngay sau một khoảng ngắn kể từ khi phát hành để giảm nguy cơ bị lộ.
2. **Thời hạn tối đa 10 phút được RECOMMENDED** (khuyến nghị), **không phải** một con số bắt buộc mọi AS dùng đúng 10 phút.
3. Client **MUST NOT** dùng authorization code hơn một lần. Nếu code bị dùng lại, AS **MUST** từ chối yêu cầu và **SHOULD** thu hồi, khi có thể, mọi token trước đó được cấp dựa trên code ấy.

RFC cũng yêu cầu code được **ràng buộc với client identifier và redirection URI**. Những ràng buộc hiện đại như PKCE còn bổ sung kiểm tra `code_verifier` tại token endpoint.

### Hiểu chính xác MUST, SHOULD và RECOMMENDED

| Từ khóa | Cách hiểu trong bài | Ứng dụng thực tế |
|---|---|---|
| **MUST** | Yêu cầu của chuẩn | Không cho code sống vô hạn; không cấp token lần thứ hai khi code dùng lại |
| **MUST NOT** | Hành vi bị cấm | Client không cố dùng lại code |
| **SHOULD** | Khuyến nghị mạnh, ngoại lệ phải có lý do | Khi phát hiện reuse, cân nhắc revoke token đã cấp từ code đó |
| **RECOMMENDED** | Nên áp dụng trừ khi có lý do hợp lệ | Chọn **không quá 10 phút** làm trần theo khuyến nghị RFC 6749 |

**Không nên viết “code bắt buộc hết hạn đúng sau 10 phút”.** 10 phút là **mức tối đa được khuyến nghị**. Nhiều hệ thống chọn **30, 60, 90, 120 hoặc 300 giây** theo threat model, độ trễ redirect và trải nghiệm thực tế. Đây là **ví dụ cấu hình**, không phải bộ giá trị chuẩn.

### Hai điều kiện độc lập

- **Chưa hết hạn** không có nghĩa **chưa được dùng**.
- **Chưa được dùng** không có nghĩa **còn trong thời hạn**.

Ở token endpoint, AS phải kiểm tra **cả hai**, cùng client, redirect, PKCE và grant. Một code còn hạn 2 phút nhưng đã đổi token thành công **phải bị từ chối ngay trong lần thử thứ hai**.

## 3. Đồng hồ lifetime bắt đầu từ lúc nào?

Điểm dễ sai nhất là tính thời gian sống của code từ lúc **user bắt đầu đăng nhập** hoặc từ lúc client gọi `/authorize`. Thực tế, code chỉ được phát hành **sau** khi AS hoàn tất các bước cần thiết.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as Client
    participant B as Browser
    participant AS as Authorization Server

    C->>C: Tạo state và PKCE verifier/challenge
    C->>B: Bắt đầu authorization transaction
    B->>AS: GET /authorize
    AS->>U: Đăng nhập / MFA / consent nếu cần
    Note over AS: Chưa có authorization code; code lifetime chưa bắt đầu
    U-->>AS: Hoàn thành xác thực và grant
    AS->>AS: Phát hành code lúc T_issued; lưu T_expires
    AS-->>B: 302 redirect_uri?code=...&state=...
    B-->>C: Callback tới client
    C->>C: Kiểm tra state, issuer và transaction
    C->>AS: POST /token + code + PKCE verifier
    AS->>AS: Kiểm tra chưa expired, chưa dùng, binding và PKCE
    AS-->>C: Token response hoặc invalid_grant
~~~

**Phân biệt ba đồng hồ:**

1. **Authorization transaction timeout:** thời hạn client/AS cho user hoàn tất login, MFA, consent và callback. Đây là chính sách riêng; không tự bằng code lifetime.
2. **Authorization code lifetime:** từ `issued_at` đến `expires_at` của code đã được cấp.
3. **Access/refresh token lifetime:** bắt đầu khi token tương ứng được cấp, theo chính sách và định dạng của chính token đó.

Ví dụ: user mất **4 phút** để nhập MFA, AS phát hành code lúc **10:04:00 UTC**, TTL code **90 giây**. Code hết hạn lúc **10:05:30 UTC**, **không phải 10:01:30** tính từ lúc bắt đầu login 10:00.

AS vẫn có thể đặt timeout cho **toàn bộ authorization request** để ngăn session/login treo quá lâu. Nhưng nếu timeout đó đã kết thúc trước consent, AS nên **từ chối request thay vì phát hành code đã hết hạn**.

## 4. Cách tính issued_at, expires_at và thời điểm cắt

Đặt:

~~~text
T_issued       = thời điểm AS tạo / commit authorization code
TTL_code       = khoảng thời gian hiệu lực do AS cấu hình
T_expires      = T_issued + TTL_code

Chỉ hợp lệ về thời gian nếu:
    T_issued <= T_now < T_expires

Tại đúng T_expires:
    code đã hết hạn
~~~

Ví dụ với TTL **120 giây**:

| Mốc UTC | Phép kiểm tra | Kết luận |
|---|---|---|
| `2026-11-23T10:00:00Z` | Code được phát hành | Bắt đầu cửa sổ |
| `10:00:45Z` | Chưa dùng, đúng binding | Có thể được đổi nếu mọi kiểm tra khác đạt |
| `10:01:59.999Z` | Chưa dùng | Vẫn nằm trước `expires_at` |
| `10:02:00Z` | `now >= expires_at` | **Hết hạn**, từ chối |
| `10:03:00Z` | Code chưa từng đổi | **Vẫn hết hạn**; không gia hạn do client đến trễ |

### Không “trượt hạn” khi có retry

Authorization code không phải sliding session. Không làm:

~~~text
onEveryTokenRequest(code):
    code.expires_at = now + 120 seconds  // Sai: kéo dài cửa sổ cho attacker
~~~

Thay vào đó, đặt `expires_at` **một lần** khi phát hành. Lần thử thất bại, refresh trang callback hoặc retry mạng **không** được tự kéo dài `expires_at`.

**Thời gian lấy từ nguồn tin cậy tại AS.** Không dùng clock client, cookie hoặc tham số `issued_at` do trình duyệt tự gửi để quyết định code còn hạn. Trong hệ thống phân tán, các AS nodes phải đồng bộ đồng hồ và có chính sách khi drift đáng kể.

### Có nên thêm clock skew cho code?

Clock skew có ý nghĩa khi nhiều thành phần độc lập ký/xác minh timestamp. Nhưng authorization code được **AS phát hành và AS kiểm tra trạng thái**, nên tốt nhất dựa vào **thời gian của hệ thống AS được kiểm soát**, không tùy tiện cộng “leeway” dài cho code hết hạn.

Nếu nhiều token endpoint nodes có clock lệch, hãy sửa đồng bộ thời gian và định nghĩa biên thời gian rõ ràng. Không coi thêm 5–10 phút grace sau `expires_at` là biện pháp chữa clock drift; làm vậy vô hiệu phần lớn lợi ích TTL ngắn.

## 5. Vòng đời authorization code là một state machine

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Authorization request được khởi tạo
    PENDING --> ISSUED: User/AS chấp thuận, code phát hành
    PENDING --> DENIED: User/AS từ chối hoặc transaction hết hạn
    ISSUED --> REDEEMED: Exchange hợp lệ; tiêu thụ một lần
    ISSUED --> EXPIRED: Chạm expires_at trước khi đổi
    ISSUED --> INVALIDATED: Grant/client/security policy vô hiệu
    REDEEMED --> REUSE_DETECTED: Một bên thử trình lại code
    REDEEMED --> [*]: Không dùng code để cấp thêm token
    REUSE_DETECTED --> [*]: Deny, đánh giá revoke token đã cấp
    EXPIRED --> [*]: Không dùng nữa
    INVALIDATED --> [*]: Không dùng nữa
    DENIED --> [*]: Không phát hành code
~~~

Các tên trạng thái là **mô hình kiến trúc gợi ý**, không phải enum chuẩn OAuth bắt buộc.

**Chỉ trạng thái `ISSUED` mới có khả năng đổi code** — và vẫn cần thỏa expiry, client binding, PKCE, redirect và policy. Code đã `REDEEMED` không quay trở lại `ISSUED` khi access token hết hạn.

### Các tình huống kết thúc

| Trạng thái | Điều đã xảy ra | Token endpoint làm gì khi nhận code? |
|---|---|---|
| **ISSUED + trước expiry** | Chưa đổi, chưa bị vô hiệu | Có thể cho exchange sau các kiểm tra |
| **EXPIRED** | Quá deadline | Từ chối, không cấp token |
| **REDEEMED** | Đã exchange thành công | Từ chối dùng lại; đánh giá replay |
| **INVALIDATED** | Grant, client, code hoặc transaction bị hủy | Từ chối |
| **UNKNOWN** | Không tìm thấy code | Từ chối, không để lộ trạng thái có tồn tại |
| **PENDING/DENIED** | AS chưa phát hành code | Không có code hợp lệ để đổi |

**Không dựa hoàn toàn vào cleanup job**: bản ghi cũ có thể còn trong database sau `expires_at` vì scheduler trễ. Token endpoint **phải tự kiểm tra expiry tại thời điểm exchange**, không chỉ dựa vào việc bản ghi đã bị xóa hay chưa.

## 6. Sinh code có entropy đủ và lưu trạng thái đúng cách

Lifetime ngắn **không bù lại** authorization code dễ đoán. AS nên sinh code từ **cryptographically secure random number generator (CSPRNG)**, đảm bảo khó suy đoán và không có pattern theo user/client/time.

Ví dụ ý tưởng:

~~~text
raw_code = BASE64URL(CSPRNG_32_bytes())  // 256-bit entropy
code_ref = HMAC_SHA256(server_lookup_key, raw_code)

AS lưu:
    code_ref
    client_id
    redirect_uri
    issuer / authorization transaction reference
    PKCE code_challenge + method
    subject / grant reference
    granted scopes / resource indicator
    issued_at
    expires_at
    lifecycle status
~~~

**256-bit entropy chỉ là lựa chọn thiết kế minh họa**, không phải kích thước bắt buộc do RFC 6749 chỉ định. RFC không yêu cầu authorization code có độ dài cố định và client không nên giả định code luôn dài 43 ký tự.

**Không lưu hoặc ghi raw authorization code rộng rãi.** Nếu code là giá trị entropy cao, có thể dùng digest/khóa tra cứu phù hợp; dùng HMAC với khóa riêng giúp giảm khả năng dò/liên kết khi hệ thống rò một phần dữ liệu. `code_ref` ở đây là tham chiếu nội bộ, không được gửi để thay code khi đổi token.

### Cần bảo vệ các trường binding

- `client_id` và `redirect_uri`: ngăn code cấp cho client/redirect khác.
- `code_challenge` và `code_challenge_method`: ngăn kẻ chỉ lấy code đổi token khi không có verifier.
- `issuer`/authorization transaction: chống code bị đưa sai AS trong hệ thống đa issuer.
- `grant_ref`, subject, scope và resource: bảo đảm token phát hành không vượt grant đã chấp thuận.
- `issued_at`/`expires_at` và trạng thái: cơ sở cho expiry/single-use/revocation.

Nếu code tồn tại như JWT self-contained, AS vẫn cần **một cơ chế ghi nhận đã dùng** (hoặc tương đương) để đảm bảo single-use. “JWT có `exp` nên không cần store” là sai đối với authorization code.

## 7. Code lifetime còn phụ thuộc client/redirect/PKCE binding

Một token request đúng thời hạn chỉ là **điều kiện cần**.

~~~mermaid
flowchart TD
    R["POST /token với authorization code"] --> I{"AS nhận biết code và issuer?"}
    I -->|"Không"| D["Từ chối invalid_grant"]
    I -->|"Có"| E{"T_now < expires_at?"}
    E -->|"Không"| D
    E -->|"Có"| S{"Code còn ISSUED/chưa dùng?"}
    S -->|"Không"| D
    S -->|"Có"| C{"Client đã xác định/xác thực đúng?"}
    C -->|"Không"| D
    C -->|"Có"| U{"Redirect URI đúng binding?"}
    U -->|"Không"| D
    U -->|"Có"| P{"PKCE verifier đúng challenge?"}
    P -->|"Không"| D
    P -->|"Có"| G{"Grant, scope, policy còn cho phép?"}
    G -->|"Không"| D
    G -->|"Có"| T["Consume nguyên tử, cấp token theo policy"]
~~~

Với **public client** (SPA/native), `client_id` chỉ là định danh; AS cần PKCE và các ràng buộc khác. Không thể nhúng secret chung trong mobile/JavaScript rồi coi đó là confidential client authentication.

Với **confidential client** (backend/BFF), AS còn xác thực client bằng phương thức đã đăng ký như `client_secret_basic`, `private_key_jwt` hoặc mTLS. **Client authentication và PKCE là hai lớp bảo vệ khác nhau**.

### PKCE S256

Theo RFC 7636:

~~~text
code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
~~~

Client tạo verifier ngẫu nhiên riêng cho **từng authorization transaction**; AS lưu challenge với chính code ấy. Khi đổi code, client gửi verifier gốc. Nếu sai, thiếu hoặc không thuộc transaction, AS phải từ chối theo policy và RFC 7636/9700.

**Code còn hạn không có nghĩa verifier sai được “thử lại mãi”.** AS cần rate limiting và cảnh báo thử nhiều lần. Tùy policy, việc trình sai verifier có thể làm AS vô hiệu code hoặc chỉ trả lỗi; đừng cho lỗi này mở cửa sổ vô hạn, và không cung cấp thông tin giúp attacker đoán verifier.

### Không chấp nhận downgrade

AS không được xử lý tình huống: authorization request có PKCE challenge, token request thiếu verifier, nhưng vẫn cấp token vì “client đã xác thực” hoặc “code còn hạn”. RFC 9700 yêu cầu AS chống PKCE downgrade và gắn chặt trạng thái có/không PKCE với code.

## 8. Authorization response: code được giao qua browser, không phải token

Sau khi user chấp thuận, AS trả redirect có code và `state`:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.test/auth/callback?code=<ONE_TIME_CODE>&state=<RANDOM_STATE>
Cache-Control: no-store
Referrer-Policy: no-referrer
~~~

**Ngay thời điểm AS phát hành code và tạo/bền vững hóa trạng thái tương ứng**, lifetime bắt đầu. `Location` là front-channel và browser có thể chuyển chậm hoặc user có thể đóng tab.

Rủi ro của URL callback:

- Code trong query có thể vào **browser history**, access log, reverse proxy/CDN, APM, crash reporter hoặc tham số được analytics ghi lại.
- Header HTTP **`Referer`** của request sau đó có thể mang path/query tùy `Referrer-Policy`, đặc biệt với request cùng origin.
- Fragment URL không đi trong HTTP `Referer` theo cơ chế thông thường, nhưng script có thể đọc fragment. Không chuyển code/token vào fragment để “giữ kín”.
- `state` cũng là dữ liệu liên kết security transaction và không nên bị log tùy tiện.
- Nếu user copy/paste callback URL cho người khác, code có thể bị phát tán khi vẫn còn thời hạn.

### Làm sạch callback sớm

Với backend/BFF, sau khi xử lý callback, thường dùng **`303 See Other`** sang đường dẫn cố định không có code/state:

~~~http
HTTP/1.1 303 See Other
Location: /app
Cache-Control: no-store
Referrer-Policy: no-referrer
~~~

Với SPA, OAuth SDK có thể dùng `history.replaceState` ngay sau khi đọc và giữ thông tin giao dịch cần thiết, **trước khi chạy analytics/third-party JS**. Chỉ làm sạch URL không thu hồi code/token đã bị sao chép; AS vẫn cần single-use/expiry/binding.

**Không xóa verifier hay transaction trước khi SDK/client hoàn tất kiểm tra state và exchange**; xử lý cleanup sai thứ tự có thể khiến code hợp lệ luôn bị `invalid_grant`.

## 9. Token endpoint: xử lý code trong thời hạn còn lại

Ví dụ public client đổi code với PKCE:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<ONE_TIME_CODE>&client_id=orders-mobile&redirect_uri=https%3A%2F%2Fapp.example.test%2Fauth%2Fcallback&code_verifier=<ORIGINAL_VERIFIER>
~~~

Token endpoint phải qua HTTPS. Trong request cho **confidential client**, còn có client authentication theo registration.

Thành công minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<ACCESS_TOKEN>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders:read"
}
~~~

**Bộ token trên chỉ là phản hồi minh họa của OAuth 2.0**. Không có nghĩa refresh token luôn được cấp hoặc access token luôn là JWT. Nếu thực hiện **OIDC Authorization Code Flow**, phản hồi thành công sẽ có `id_token` theo profile OIDC bên cạnh access token; ví dụ này không nhằm minh họa OIDC đầy đủ.

### Hết hạn hoặc đã dùng

Thường trả `invalid_grant` với HTTP 400 theo OAuth 2.0:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_grant"
}
~~~

Vì lý do bảo mật, không nên trả cho bên gọi không tin cậy chi tiết như “code của client X tồn tại, còn 3 giây” hoặc “verifier đúng nhưng redirect sai”. Log nội bộ có thể phân biệt reason code phù hợp, nhưng **không ghi raw code/verifier/token**.

**Phân biệt lỗi:**

| Lỗi/case | Nguyên nhân | Định hướng |
|---|---|---|
| `invalid_grant` | Code expired, already used, revoked, không khớp client/redirect hoặc PKCE sai theo profile | Không đổi bằng code đó nữa; cân nhắc tạo authorization flow mới |
| `invalid_client` | Confidential client authentication thất bại | Kiểm tra credential/cert/assertion phía server; không đưa bí mật vào logs |
| `unauthorized_client` | Client không được phép dùng grant type | Sửa registration/policy, không lách bằng flow khác |
| `invalid_request` | Thiếu/duplicate/malformed tham số | Sửa request; không log credential nguyên văn |
| `invalid_scope` | Yêu cầu scope không hợp lệ/không được phép theo ngữ cảnh | Xin phạm vi phù hợp, không cấp vượt quyền |

Client **không nên tự động xin lại token bằng cùng code** khi thấy `invalid_grant`. Nếu code đã được tiêu thụ, chỉ authorization transaction mới (với verifier/state mới) có thể cấp code mới.

## 10. Một code chỉ dùng một lần — kể cả khi còn thời hạn

Giả sử code `K1` phát hành 10:00, hạn 10:02:

~~~text
10:00:00  AS phát hành K1, status=ISSUED
10:00:10  Client đổi K1 đúng code_verifier → thành công; status=REDEEMED
10:00:11  Request khác gửi K1 → PHẢI từ chối, dù chưa đến 10:02
10:02:00  Hết hạn nếu chưa dùng; không còn ý nghĩa với K1 đã REDEEMED
~~~

**Vì sao TTL không đủ chống replay?** Nếu AS chỉ kiểm tra `expires_at` mà không ghi nhận code đã dùng, attacker và client có thể đổi cùng code nhiều lần trước expiry. Thậm chí TTL 5 giây vẫn tạo cửa sổ cấp token lặp.

### Phát hiện code reuse và thu hồi token đã cấp

RFC 6749 yêu cầu AS **từ chối request dùng lại code**, và khuyến nghị **thu hồi các token đã cấp dựa trên code đó khi có thể**. Sở dĩ vậy vì trong một số tình huống AS không biết người đổi lần đầu là client hợp lệ hay attacker có đủ verifier/credential.

Khi ghi nhận reuse, AS nên có tham chiếu tới **authorization transaction và token issuance** để cân nhắc revoke access token/refresh token hoặc grant theo policy. Nhưng:

- Không phải mọi `invalid_grant` đều chứng minh code bị tấn công; có thể do **client gửi duplicate request, browser reload hoặc lỗi mạng**.
- Thu hồi một nhóm token có thể ảnh hưởng user hợp lệ, cần chính sách và audit minh bạch.
- Nếu JWT access token được API xác minh offline, việc AS “mark revoked” **không tự làm API từ chối ngay**. Cần trạng thái thu hồi/denylist/introspection hoặc chờ `exp` theo threat model.

**Lưu ý:** nếu AS xóa ngay hoàn toàn bản ghi code sau lần dùng đầu tiên, lần dùng thứ hai có thể chỉ hiện ra như “unknown code”, khó nhận biết reuse và truy token đã cấp. Có thể giữ **tombstone/code reference** ngắn hạn với quyền đọc hạn chế để phát hiện reuse, không lưu raw code.

## 11. Concurrency: hai lần đổi code trong cùng một mili giây

Một lỗi nguy hiểm là check-then-act không nguyên tử:

~~~text
Request A: SELECT code → thấy unused
Request B: SELECT code → thấy unused
Request A: phát token AT_A
Request B: phát token AT_B
Request A: UPDATE code.used=true
Request B: UPDATE code.used=true
~~~

Nếu chỉ kiểm tra `used=false` trước khi cấp token rồi cập nhật sau, cả hai request đều có thể thành công, trái với yêu cầu **single-use**.

### Cần atomic redemption

Tại AS, một request chỉ được **claim/consume code** sau khi hoàn tất các ràng buộc cần thiết, sử dụng transaction hoặc compare-and-swap đáng tin cậy. Các luồng khác không thể đồng thời dùng cùng code.

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Token request A
    participant B as Token request B
    participant DB as AS transaction store
    participant AS as Issuance service

    A->>DB: Lock / claim code K1
    DB-->>A: ISSUED, còn hạn
    A->>AS: Verify client, redirect, PKCE và grant
    AS-->>A: Hợp lệ
    A->>DB: Atomic consume K1 + persist issuance
    B->>DB: Thử claim K1
    DB-->>B: K1 đã tiêu thụ / chờ lock
    B-->>B: Deny invalid_grant
    A-->>A: Token response thành công
~~~

**Tính đúng đắn phải vượt qua nhiều process/node.** `synchronized` trong một instance Java không ngăn instance khác cùng đổi code. Cần state/transaction share được giữa mọi token endpoint nodes, hoặc cơ chế tương đương với consistency phù hợp.

### Database transaction và tình huống crash

- Nếu code bị mark used **trước** khi ghi token state và process crash, client có thể mất code nhưng chưa có token.
- Nếu token được cấp **trước** khi code dùng bị commit, crash/race có thể tạo hai bộ token.
- Nên thiết kế **transactional issuance** hoặc workflow bảo đảm một outcome nhất quán: consume code, lưu token/grant metadata và commit, rồi mới trả phản hồi.
- Với external side effects (token signing, event bus, cache), cần cơ chế idempotent nội bộ, durable outbox hoặc reconciliation **mà không cho client đổi code thêm lần nữa**.

**Không có cơ chế “retry code vô hạn cho tiện”**: nếu token response bị mất sau AS đã commit, client có thể không biết token đã cấp; thường nên quay lại authorization flow thay vì phá vỡ single-use. Mọi extension retry/idempotency nếu được dùng phải được định nghĩa và kiểm soát bởi AS, không tự suy từ RFC 6749.

## 12. Mô hình lưu trữ SQL ở Authorization Server

Bảng ví dụ cho hệ thống sử dụng code opaque ngẫu nhiên và tham chiếu digest/HMAC. Đây là **minh họa PostgreSQL**, không phải schema chuẩn OAuth bắt buộc:

~~~sql
CREATE TABLE authorization_codes (
    code_ref           TEXT PRIMARY KEY,
    issuer             TEXT NOT NULL,
    client_id          TEXT NOT NULL,
    redirect_uri       TEXT NOT NULL,
    code_challenge     TEXT NOT NULL,
    challenge_method   TEXT NOT NULL,
    grant_ref          TEXT NOT NULL,
    issued_at          TIMESTAMPTZ NOT NULL,
    expires_at         TIMESTAMPTZ NOT NULL,
    redeemed_at        TIMESTAMPTZ NULL,
    status             TEXT NOT NULL,
    CHECK (expires_at > issued_at),
    CHECK (status IN ('ISSUED', 'REDEEMED', 'INVALIDATED'))
);

CREATE INDEX idx_authorization_codes_expiry
    ON authorization_codes (expires_at);
~~~

`code_ref` được tính từ **raw code do AS phát hành**, ví dụ HMAC với khóa chỉ dùng cho lookup, không phải giá trị do browser tự quyết định. Ở production, còn cần bảo vệ khóa HMAC, PKCE method policy, issuer/tenant isolation và ánh xạ grant/scope/subject an toàn.

### Ví dụ khóa hàng, kiểm tra rồi consume

~~~sql
BEGIN;

SELECT
    code_ref, issuer, client_id, redirect_uri,
    code_challenge, challenge_method, grant_ref,
    issued_at, expires_at, redeemed_at, status
FROM authorization_codes
WHERE code_ref = :code_ref
FOR UPDATE;

-- Application kiểm tra dưới lock/transaction:
-- 1) issuer/client/redirect/PKCE/grant đúng
-- 2) status = 'ISSUED'
-- 3) expires_at > server_now
-- Không in raw code/verifier vào log.
-- Nếu bất kỳ kiểm tra nào lỗi: ROLLBACK và trả invalid_grant.

UPDATE authorization_codes
SET status = 'REDEEMED',
    redeemed_at = CURRENT_TIMESTAMP
WHERE code_ref = :code_ref
  AND status = 'ISSUED'
  AND expires_at > CURRENT_TIMESTAMP;

-- Require affected rows = 1.
-- Lưu các metadata token/issuance trong cùng transaction
-- (hoặc workflow bền vững đảm bảo consistency).
-- Khi tất cả hợp lệ:
COMMIT;
~~~

**Đây là SQL hướng dẫn, không phải script chạy nguyên vẹn**, vì các điều kiện app-level và token state chưa được triển khai. Nhiều hệ thống sẽ dùng `SELECT ... FOR UPDATE` hoặc **atomic conditional UPDATE**; điều quan trọng là **chỉ một request có thể thắng**, và mọi kiểm tra ràng buộc gắn với record đúng.

**Không dùng `DELETE FROM authorization_codes WHERE expires_at < NOW()` làm chính sách expiry duy nhất.** Cleanup job có thể bị trễ, lỗi hoặc không chạy; token endpoint vẫn phải kiểm tra thời hạn và trạng thái trong điều kiện cấp token.

## 13. Java 17: kiểm tra deadline với Clock và policy TTL

Ví dụ Java 17 sau minh họa cách tính **deadline theo thời điểm phát hành của AS** và xác định code còn trong khoảng thời gian hay không. Đây là helper policy thuần Java, **không tự thực hiện client authentication, PKCE, token issuance hay transaction lock**.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class AuthorizationCodeLifetime {
    // Lựa chọn vận hành minh họa, KHÔNG phải TTL bắt buộc.
    private static final Duration CODE_TTL = Duration.ofSeconds(120);

    public record CodeWindow(
            Instant issuedAt,
            Instant expiresAt,
            boolean alreadyRedeemed
    ) {
        public CodeWindow {
            Objects.requireNonNull(issuedAt);
            Objects.requireNonNull(expiresAt);
            if (!expiresAt.isAfter(issuedAt)) {
                throw new IllegalArgumentException(
                        "expiresAt must be after issuedAt"
                );
            }
        }
    }

    public static CodeWindow issue(Clock clock) {
        Instant issued = clock.instant();
        return new CodeWindow(
                issued,
                issued.plus(CODE_TTL),
                false
        );
    }

    public static boolean mayRedeemByTime(
            CodeWindow code,
            Clock clock
    ) {
        Instant now = clock.instant();
        return !code.alreadyRedeemed()
                && !now.isBefore(code.issuedAt())
                && now.isBefore(code.expiresAt());
    }

    public static void main(String[] args) {
        Instant issuedAt =
                Instant.parse("2026-11-23T10:00:00Z");
        CodeWindow code = new CodeWindow(
                issuedAt,
                issuedAt.plus(CODE_TTL),
                false
        );

        Clock beforeExpiry = Clock.fixed(
                Instant.parse("2026-11-23T10:01:59Z"),
                java.time.ZoneOffset.UTC
        );
        Clock atExpiry = Clock.fixed(
                Instant.parse("2026-11-23T10:02:00Z"),
                java.time.ZoneOffset.UTC
        );

        System.out.println(mayRedeemByTime(code, beforeExpiry));
        System.out.println(mayRedeemByTime(code, atExpiry));
        // true
        // false
    }
}
~~~

### Tại sao truyền Clock thay vì dùng Instant.now() rải rác?

- Test được **đúng ranh giới `expires_at`** mà không phải ngủ/chờ thời gian thật.
- Dễ xác minh hành vi ở mốc trước/sau deadline và khi đồng hồ được giả lập.
- Đưa việc lấy thời gian vào một abstraction do AS kiểm soát.
- Giảm việc các component tự tính TTL lệch nhau.

**Nhưng có giới hạn:** `alreadyRedeemed` chỉ là snapshot trong record, không bảo đảm atomicity. Trong triển khai thật, trạng thái sống và việc consume phải nằm trong storage/transaction tin cậy. Có thể nhiều instance Java cùng đọc `false`; **đừng dùng helper này thay database lock/CAS**.

### Không tin expires_at từ client

Không cho `expires_at`, `issued_at` do client gửi vào `/token` quyết định. Nếu code được ký, AS vẫn phải xác minh chữ ký/issuer/audience/purpose và trạng thái single-use, không chỉ parse timestamp.

## 14. TTL trong môi trường phân tán, cache và vận hành

Các Authorization Server thường chạy nhiều instance, nhiều khu vực hoặc có cache Redis/database. Một chính sách TTL chỉ đúng nếu **mọi token endpoint** thống nhất ranh giới.

### Những vấn đề cần thiết kế

| Tình huống | Rủi ro | Hướng xử lý |
|---|---|---|
| AS A phát hành, AS B xử lý code | B không thấy code hoặc dùng clock lệch | Shared transaction state hoặc routing có consistency được chứng minh; time sync |
| Redis key có TTL nhưng trạng thái dùng lại nằm ở process memory | Node khác vẫn chấp nhận code | Single-use phải global/atomic, không theo instance |
| Cache hết hạn trễ | Bản ghi expired vẫn có thể đọc | Luôn kiểm tra `expires_at` ở token endpoint |
| Cache eviction sớm | Code còn hạn biến mất | Client có thể phải restart flow; đo lỗi và capacity |
| Multi-region replication bất đồng bộ | Hai region cùng thấy chưa redeemed | Consistency/claim cơ chế mạnh hoặc home-region issuer routing |
| Retry mạng sau token response mất | Client không biết code đã dùng | Không phát token lần hai theo code; hướng dẫn khởi tạo lại flow |
| Clock lệch 30–60 giây | Code bị từ chối sớm hoặc sống lâu hơn | Đồng bộ clock, đo drift; không dùng leeway quá lớn |
| GC xóa ngay code redeemed | Khó phát hiện replay và truy lần issuance | Giữ tombstone/tham chiếu có retention phù hợp |
| Rate limit token endpoint yếu | Attacker brute force hoặc flooding | CSPRNG code, rate limit, audit, generic errors |

**TTL của cache không nhất thiết là toàn bộ chính sách lifetime.** Ví dụ Redis `EXPIRE` xóa key sau 120 giây, nhưng nếu cơ chế consume được ghi ở database khác hoặc replication trễ, ứng dụng phải làm rõ **nguồn sự thật** nào quyết định code hợp lệ.

### Nên giữ code redeemed/expired trong database bao lâu?

Có ba mục tiêu có thể khác nhau:

1. **Bảo mật runtime:** không được chấp nhận sau `expires_at` hoặc sau redeem.
2. **Phát hiện replay:** cần biết code nào bị trình lại và có token nào trước đó được phát hành.
3. **Privacy/retention:** không giữ định danh/metadata nhạy cảm vô hạn.

Giải pháp thường là **giữ reference/tombstone và audit metadata có giới hạn**, trong khi không bao giờ cho đổi lại. Thời hạn retention tùy nhu cầu điều tra, luật/chính sách và lượng dữ liệu; **không có một chuẩn chung “giữ code 30 ngày”**.

## 15. Chọn TTL bao nhiêu để vừa an toàn vừa dùng được?

Nếu code lifetime quá dài, kẻ lấy được code có thêm thời gian để khai thác, nhất là khi PKCE/redirect binding bị lỗi hoặc verifier bị lộ. Nếu quá ngắn, client hợp lệ có thể hết hạn trong quá trình browser redirect, cold start mobile, reverse proxy, load hoặc mạng chập chờn.

Một số mốc tham khảo **chỉ để đánh giá kiến trúc**:

| TTL code | Tình huống cân nhắc | Trade-off |
|---|---|---|
| **30 giây** | Hệ thống có callback và exchange rất nhanh, hạ tầng ổn định | Rủi ro UX lớn hơn trên mobile mạng yếu/cold start |
| **60–120 giây** | Nhiều web/BFF flow phản hồi nhanh | Cần đo tail latency và tình huống tải cao |
| **3–5 phút** | Có redirect qua app/device hoặc latency đáng kể | Cửa sổ lộ rộng hơn, vẫn dưới mức trần khuyến nghị |
| **10 phút** | Mức tối đa **được RFC 6749 khuyến nghị** | Không phải mặc định tối ưu; cân nhắc giảm khi có thể |
| **Trên 10 phút** | Cần giải trình rõ vì đi ngược khuyến nghị trần | Cửa sổ khai thác rộng, nên xem lại flow/architecture |

**Không lấy thời gian user nhập MFA/consent để bắt buộc tăng code TTL.** User có thể mất 5 phút cho MFA **trước khi code tồn tại**; code có thể được phát hành với TTL 90 giây **sau khi** login hoàn tất.

### Dữ liệu nên dùng để chọn TTL

- Độ trễ **từ code issued → callback received → token request** thực tế, phân theo browser/mobile, vùng địa lý, app cold start.
- `p95`/`p99` exchange latency (dùng metrics, không log code nguyên văn).
- Tỷ lệ `invalid_grant` do **expired** riêng khỏi reuse, redirect mismatch và PKCE mismatch.
- Thời gian xử lý callback của ứng dụng, retry network và tắc nghẽn AS.
- Mức độ nhạy cảm scope/audience mà grant có thể cấp.
- Mức bảo vệ bổ sung: PKCE S256, client authentication, strict redirects, logging hygiene, code entropy, rate limits.

Tối ưu đúng là **giảm latency kiến trúc và code TTL vừa đủ**, không chỉ kéo dài expiry để ẩn một lỗi triển khai.

## 16. So sánh với access token và refresh token lifetime

| Loại thời gian | Bắt đầu từ | Cơ chế hết hạn/từ chối | Tại sao không giống code TTL? |
|---|---|---|---|
| **Authorization code lifetime** | Khi AS phát hành code | Expiry nhanh + single-use + binding + policy | Grant tạm thời đi qua front-channel |
| **Access token lifetime** | Khi AS cấp access token | `exp`, introspection/denylist hoặc trạng thái theo profile | Token dùng gọi API; cần giảm ảnh hưởng nếu lộ |
| **Refresh token lifetime** | Khi AS cấp refresh token | AS grant state, absolute/inactivity expiry, rotation/revoke | Credential cho phiên tiếp diễn, có policy riêng |
| **ID token validity** | Khi OP phát ID token | OIDC client kiểm tra time/signature/issuer/audience | Dành cho xác thực người dùng tại client, không API authorization |
| **User login/SSO session** | Khi tạo session | Cookie/session timeout, logout, reauthentication | Session có thể tồn tại lâu hơn code |
| **Consent/authorization grant** | Khi AS chấp thuận grant | Policy, user revoke, scope changes | Grant không biến code thành credential nhiều lần dùng |
| **PKCE transaction context** | Khi client khởi tạo request | Client timeout, callback, state consume | Có thể tồn tại **trước khi code được phát hành** |

Ví dụ user đã xác thực xong và code **K** được phát hành với TTL 120 giây. Client đổi K thành access token **AT1** có `expires_in=600` và refresh token **RT1** theo policy. Sau 120 giây K hết hạn (hoặc sớm hơn nếu đã dùng), nhưng **AT1 không bị vô hiệu chỉ vì K hết hạn**. RT1 cũng **không được thay bằng việc “refresh K”**.

**Một code phát hành trước đó bị xác định có reuse** là tình huống đặc biệt: RFC 6749 khuyến nghị AS thu hồi token đã cấp từ code đó khi có thể, nhưng không phải mọi lần code tự nhiên hết hạn đều khiến token đã cấp bị thu hồi.

## 17. Trải nghiệm client khi code expired hoặc response bị mất

### Browser reload/back button

User nhấn reload trên callback URL có `code=K` sau khi ứng dụng đã exchange thành công. Nếu controller/SDK chạy lại token request bằng K, AS đúng chuẩn từ chối. Ứng dụng nên:

- Xử lý callback một lần với transaction state rõ ràng.
- Sau exchange thành công, **redirect sang URL sạch** và tạo session ứng dụng.
- Nếu user reload callback cũ, hiện trạng thái phù hợp hoặc điều hướng lại, **không replay code**.
- Khi thực sự cần login mới, bắt đầu **authorization flow mới với state và PKCE verifier mới**.

### Token response bị mất do mạng

AS có thể đã consume code và commit token, nhưng kết nối hỏng trước khi client nhận response. Client sẽ gặp tình huống không thể dùng K lần hai. Đó là trade-off có chủ ý của one-time code.

**Không dùng workaround thiếu an toàn:** “nếu request thất bại, AS cho code dùng hai lần trong 30 giây”. Nếu cần resilience đặc biệt, thiết kế retry/idempotency phải được AS chuẩn hóa trong hệ thống và đảm bảo không phát hành hai bộ token trái chính sách. Với nhiều client, **đưa người dùng khởi tạo lại flow** là cách dễ đúng.

### Mobile app cold start hoặc universal link

Trên thiết bị mobile, khi browser chuyển về app, hệ điều hành có thể cần mở tiến trình từ trạng thái cold start. App phải giữ transaction context/verifier an toàn đủ để nhận callback; nếu callback đến sau expiry, client **không được cố kéo dài code từ phía app**. Cần cải thiện latency và chọn TTL có dữ liệu đo đạc thực tế.

### Nhiều tab hoặc nhiều flow song song

Mỗi flow có **state, verifier, issuer, redirect và deadline riêng**. Không đặt một biến `currentCodeVerifier` toàn cục bị overwrite giữa hai tab, dẫn đến code không thể đổi hoặc nguy cơ transaction confusion.

## 18. Bảo vệ URL, log và audit lifetime

Một code ngắn hạn vẫn có thể bị sao chép qua URL/telemetry, nên cần hạn chế **mọi nơi nó xuất hiện**.

### Nguyên tắc truyền và ghi log

- Callback HTTPS và response `Referrer-Policy: no-referrer`, `Cache-Control: no-store` cho trang nhạy cảm.
- Không log raw `code`, `state`, `code_verifier`, `Authorization` header, access/refresh token hoặc client secret.
- Trên CDN/gateway/reverse proxy, ưu tiên route template `/auth/callback` thay vì raw request URI chứa query.
- Không tải analytics/tag manager trước khi làm sạch callback.
- Không đưa code vào query mới, exception message, support ticket, screenshot, clipboard hoặc crash report.
- Chỉ gửi access token cho đúng API qua cơ chế được hỗ trợ; refresh token chỉ gửi AS token endpoint.

### Event taxonomy để theo dõi

| Event | Tạo ở đâu | Fields an toàn nên có |
|---|---|---|
| `authorization.code.issued` | AS | `code_ref`, client ID, issuer, grant ref, issued_at, expires_at, policy version |
| `authorization.code.redeemed` | AS | `code_ref`, redeemed_at, latency, outcome, client, method |
| `authorization.code.rejected` | AS | `code_ref` nếu nhận dạng an toàn, reason enum, time, client ref |
| `authorization.code.reused` | AS | Code ref, token issuance ref, incident/correlation ID |
| `authorization.code.expired` | AS/metrics | Số lượng theo client/issuer, time; phân biệt GC với lúc chạm expiry |
| `token.issued` | AS | Client, audience, granted scopes, token reference, TTL, grant ref |

**Không dùng raw `code` làm event_id.** Một reference được AS tạo hoặc HMAC có kiểm soát cho phép liên kết issuance → redemption → replay investigation mà không lưu bí mật nguyên văn.

### Các chỉ số vận hành

- **Code redemption success rate** theo client/flow/region, phân biệt authorized-denied, expired và invalid credentials.
- **Code redemption latency**: `redeemed_at - issued_at` với các code thành công, theo p50/p95/p99.
- **Expired-code rejection rate** và phân bố time-to-redeem gần deadline.
- **Reuse detection rate**: phân biệt browser reload, client duplicate request và dấu hiệu cố ý khai thác.
- **No-PKCE/downgrade rejects**, wrong-client/redirect/issuer rejects.
- **Audit coverage và event ingestion delay** để biết có mất dấu vết hay không.

Một spike `invalid_grant` sau deploy có thể do client gửi sai redirect hoặc verifier, **không nhất thiết là TTL quá ngắn**. Cần reason code nội bộ được bảo vệ để tránh tăng TTL một cách sai lầm.

## 19. Case study: code còn hạn nhưng đã dùng — và code chưa dùng nhưng hết hạn

Ứng dụng `orders-web` dùng Authorization Code + PKCE S256 với AS `https://auth.example.test`, scope `orders:read`, Resource Server `https://orders-api.example.test`. AS đặt **TTL code = 120 giây**.

| UTC | Hành động | Trạng thái K1 | Kết quả |
|---|---|---|---|
| 10:00:00 | User đã hoàn tất login và AS phát hành K1 | ISSUED, expires 10:02:00 | Code có thể đổi |
| 10:00:10 | Browser nhận callback K1, client xác minh state | ISSUED | Chưa cấp token |
| 10:00:11 | Client POST K1 + verifier V1 | REDEEMED nếu mọi kiểm tra đúng | AS cấp AT1 theo grant |
| 10:00:12 | Attacker đọc callback log và gửi K1 | REDEEMED, **vẫn trước expiry** | **Từ chối**, ghi dấu hiệu reuse |
| 10:02:00 | Deadline của K1 | K1 đã REDEEMED | Không làm AT1 tự hết hạn |
| 10:03:00 | Client cố dùng lại K1 vì refresh AT1 thất bại | REDEEMED/expired | **Từ chối**; refresh cần RT hoặc flow mới |

Giả sử một authorization transaction khác phát hành **K2 lúc 10:05:00**, client bị kẹt mạng và **không đổi trước 10:07:00**:

| UTC | Hành động | Trạng thái K2 | Kết quả |
|---|---|---|---|
| 10:05:00 | AS phát K2, expires 10:07:00 | ISSUED | Chưa dùng |
| 10:06:59 | Client gửi K2 đúng verifier | ISSUED trước expiry | Có thể thành công nếu mọi điều kiện thỏa |
| 10:07:00 | Token endpoint nhận K2 lần đầu | EXPIRED | **Từ chối** |
| 10:07:30 | Client retry K2, xin “gia hạn 30 giây” | EXPIRED | **Từ chối**; flow mới |

**Ba bài học từ tình huống:**

1. **Single-use và expiry là hai điều kiện độc lập**.
2. Hết hạn code **không** làm access token đã phát hành từ lần exchange hợp lệ tự hết hạn. Reuse bất thường lại có thể kích hoạt điều tra/revoke theo RFC.
3. Client phải **xử lý expired code bằng authorization transaction mới**, không tăng `expires_at` khi retry.

### Kẻ tấn công chỉ có K1 thì sao?

Nếu K1 chưa được đổi nhưng attacker chỉ lấy được code và **không có PKCE verifier**, AS đúng chuẩn phải từ chối exchange của attacker. Nếu attacker có **cả code và verifier**, thời hạn ngắn và single-use giúp thu hẹp cửa sổ, nhưng không thay việc bảo vệ browser/device hoặc confidential-client credential.

## 20. Ma trận kiểm thử lifetime và single-use

| Test | Điều kiện | Kết quả mong đợi |
|---|---|---|
| **T1 — Issuance time** | Login kéo dài 5 phút rồi AS mới phát code | Code TTL tính **từ lúc phát hành**, không từ lúc bắt đầu login |
| **T2 — Trước expiry** | `now=expires_at-1ms`, code chưa dùng/binding đúng | Có thể exchange |
| **T3 — Tại expiry** | `now=expires_at` | **Từ chối** |
| **T4 — Sau expiry** | `now=expires_at+1ms` | **Từ chối** |
| **T5 — Single-use** | Đổi K thành công rồi dùng lại trước expiry | AS từ chối lần hai |
| **T6 — Parallel redemption** | Hai request đổi cùng code đồng thời ở hai node | Tối đa một lần cấp token thành công |
| **T7 — Missing PKCE verifier** | Code có challenge S256, request thiếu verifier | Từ chối |
| **T8 — Wrong verifier** | Verifier khác transaction | Từ chối; không chuyển sang `plain` |
| **T9 — PKCE downgrade** | Code không có challenge nhưng client gửi verifier trong deployment có PKCE support | Từ chối theo RFC 9700 |
| **T10 — Wrong client** | Client B đổi code của client A | Từ chối |
| **T11 — Wrong redirect** | `redirect_uri` không khớp binding | Từ chối |
| **T12 — Unknown issuer** | Đổi code ở AS khác | Từ chối, client không gửi verifier đến issuer lạ |
| **T13 — Grant revoked** | Code còn hạn nhưng grant bị hủy | Từ chối theo policy |
| **T14 — Cleanup job delay** | Bản ghi code hết hạn còn trong DB | Endpoint vẫn từ chối |
| **T15 — Cache eviction** | Code chưa hết hạn nhưng state bị mất | Không cấp token sai; client xử lý flow lỗi |
| **T16 — Clock skew** | Nodes có drift trong môi trường test | Báo lỗi/cảnh báo thích hợp; không kéo leeway không kiểm soát |
| **T17 — Lost token response** | AS đã commit, response bị ngắt | Không cấp token lần hai theo cùng code |
| **T18 — Browser callback reload** | Reload URL chứa code đã đổi | Client không replay vô hạn; chuyển trạng thái an toàn |
| **T19 — Multi-tab** | Hai flow đồng thời với hai state/verifier | Mỗi code đúng verifier, không ghi đè |
| **T20 — Reuse audit** | Code đã redeem bị dùng lại | Tạo dấu vết và đánh giá revoke token đã phát hành |
| **T21 — Log privacy** | Canary code giả qua CDN/gateway/app | Không có raw code/verifier/token trong log/analytics |
| **T22 — Access token lifetime** | Code K hết hạn sau AT issuance | AT vẫn tuân TTL/trạng thái riêng, không nhầm theo code |
| **T23 — Invalid response** | Token endpoint trả `invalid_grant` | Không lộ code hoặc chi tiết grant của client khác |
| **T24 — TTL policy** | Cấu hình code TTL vượt trần được khuyến nghị | Policy/config review cảnh báo hoặc chặn theo quyết định tổ chức |

**Kiểm thử với giả lập đồng hồ và credential staging** để chủ động thử ranh giới mà không cần đợi thời gian thật; không đưa raw code/token production vào báo cáo. Với test concurrency, chạy trên nhiều AS instances nếu kiến trúc production là multi-node.

## 21. Những hiểu lầm cần tránh

**“Authorization code mặc định có lifetime 10 phút và bắt buộc phải như vậy.”** Sai. RFC 6749 yêu cầu **hết hạn nhanh** và **khuyến nghị tối đa 10 phút**. Chọn thời hạn cụ thể là quyết định của AS theo rủi ro/vận hành.

**“User mất 7 phút xác thực MFA, nên code đã gần hết hạn.”** Không mặc định. Code thường chỉ được phát hành **sau khi** authorization được hoàn tất. Transaction/login timeout là chính sách khác.

**“Code còn hạn thì có thể đổi nhiều lần.”** Sai. Code phải **single-use**, và AS phải từ chối lần đổi tiếp theo.

**“JWT authorization code có `exp` là đủ, không cần trạng thái.”** Sai. `exp` không ngăn cùng code được dùng lại nhiều lần trước expiry. Cần kiểm soát single-use nhất quán.

**“Client retry lại code mỗi khi token request timeout.”** Nguy hiểm. AS có thể đã tiêu thụ code; retry có thể bị coi là reuse. Cần xử lý trạng thái transaction đúng và có thể khởi tạo flow mới.

**“Sau khi code hết hạn, access token đã cấp cũng phải hết hạn.”** Sai. Token đã phát hành có vòng đời riêng; ngoại lệ là khi AS chủ động thu hồi vì reuse/grant/security policy.

**“Code lifetime ngắn đủ thay PKCE.”** Sai. Attacker có thể dùng code trong vài giây nếu code bị lộ và AS không có binding hợp lệ. Cần PKCE S256, client/redirect binding, issuer, state và single-use.

**“Xóa code khỏi DB sau expiry là đủ.”** Sai. Cleanup bất đồng bộ có thể trễ; token endpoint phải kiểm tra deadline và trạng thái tại lúc exchange.

**“Ứng dụng có thể tự gia hạn code để không làm phiền người dùng.”** Sai. AS là bên quyết định code validity. Client không được sửa lifetime; khi expired phải có authorization transaction mới.

## 22. Checklist triển khai Authorization code lifetime

1. **Phát hành code khó đoán bằng CSPRNG**, có entropy và độ dài phù hợp; không chứa dữ liệu nhạy cảm dễ đọc.
2. **Đặt `issued_at` và `expires_at` khi code được phát hành**, không từ lúc user bắt đầu login.
3. **Dùng TTL ngắn theo threat model**; hiểu trần 10 phút của RFC 6749 là **RECOMMENDED**, không phải default bắt buộc.
4. **Không kéo dài expiry theo request/retry**, tránh sliding lifetime.
5. **Token endpoint tự kiểm tra `now < expires_at`**, không dựa vào cleanup job hoặc Redis TTL đơn độc.
6. **Code phải dùng một lần**; state `REDEEMED` không quay lại `ISSUED`.
7. **Tiêu thụ code nguyên tử** trên mọi AS nodes, bảo vệ race và mất response.
8. **Bind code với đúng client ID, redirect URI, issuer và transaction**, không chấp nhận code của client/issuer khác.
9. **Bắt buộc kiểm tra PKCE S256** khi flow yêu cầu; ngăn thiếu verifier, downgrade và sai challenge.
10. **Xác thực confidential client tại token endpoint** theo registration; PKCE không thay client auth.
11. **Trước issuance, kiểm tra grant, scope/audience và policy**; code đúng thời hạn không tự cho phép vượt quyền.
12. **Từ chối code expired/used/wrong binding bằng lỗi OAuth phù hợp**, tránh tiết lộ trạng thái code cho attacker.
13. **Khi phát hiện reuse**, ghi audit an toàn và đánh giá revoke token đã phát hành theo khuyến nghị RFC 6749.
14. **Không log raw code, verifier, token hoặc header nhạy cảm**, làm sạch callback, no-referrer/no-store và kiểm tra edge/proxy/APM.
15. **Giữ code reference/tombstone có kiểm soát** để phục vụ replay detection, không giữ raw code vô hạn.
16. **Đồng bộ thời gian và consistency phân tán**, tính đến cache, multi-region, failover và lưu trạng thái bền vững.
17. **Đo issued→redeemed latency p95/p99**, phân biệt expired với wrong redirect/PKCE/reuse, không tăng TTL mù quáng.
18. **Kiểm thử ranh giới**, concurrency, reload callback, multi-tab, response mất và code sau grant revoke.
19. **Phân biệt lifetime code với access/refresh/ID token**, user session, consent và PKCE transaction context.
20. **Khi code hết hạn**, client tạo authorization transaction mới với `state` và verifier mới; không dùng code cũ để refresh token.

**Kết luận:** authorization code tồn tại trong một **cửa sổ ngắn ngay sau khi AS cấp**, nhưng chỉ được dùng **một lần** và phải gắn với đúng **client, redirect URI, PKCE và authorization grant**. **TTL ngắn, expiry nghiêm ngặt, atomic redemption và bảo vệ URL/log** bổ trợ cho nhau. Đây là cách giảm thời gian kẻ tấn công có thể lợi dụng code bị lộ mà không nhầm code với access/refresh token hoặc session đăng nhập.

### Tài liệu chuẩn tham khảo

- [RFC 6749 — OAuth 2.0 Authorization Framework, Section 4.1.2](https://www.rfc-editor.org/rfc/rfc6749#section-4.1.2): lifetime ngắn, trần 10 phút khuyến nghị, single-use và xử lý reuse.
- [RFC 6749 — Section 4.1.3, Access Token Request](https://www.rfc-editor.org/rfc/rfc6749#section-4.1.3): token endpoint kiểm tra code, client và redirect URI.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): `code_challenge`/`code_verifier` và `S256`.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): bảo mật authorization response, PKCE downgrade và token lifecycle.
- [RFC 9207 — Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): issuer binding và phòng tránh AS mix-up.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): external user agent và redirect cho mobile/desktop.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): access token khác code và cần bảo vệ riêng.
- [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009) và [RFC 7662 — Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm soát token đã phát hành.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token và các claim thời gian.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC code flow, ID token và token response.
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): tránh rò code, redirect yếu, replay và các lỗi OAuth thường gặp.
