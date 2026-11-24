# User consent

## Mục tiêu học tập

Trong chương **Authorization Code** của học phần bảo mật token, **user consent** là quyết định người dùng chấp thuận hoặc từ chối cho một **OAuth Client** truy cập tài nguyên theo một phạm vi quyền cụ thể. Trong luồng **Authorization Code + PKCE**, consent thường diễn ra **tại Authorization Server (AS)** sau khi AS đã nhận biết và xác thực người dùng theo yêu cầu, nhưng trước khi phát hành authorization code đại diện cho một authorization grant được chấp thuận.

Điểm khó không nằm ở việc vẽ hai nút “Cho phép” và “Từ chối”, mà là đảm bảo **người dùng hiểu đúng ai xin quyền gì**, AS chỉ cho phép những quyền policy chấp nhận, quyết định consent được **gắn đúng giao dịch**, và access token cuối cùng **không vượt quá** quyền đã được cấp.

Sau bài học, bạn có thể:

1. Phân biệt **consent**, **authentication**, **authorization grant**, **client policy** và **authorization tại Resource Server**.
2. Xác định consent nằm ở đâu trong **Authorization Code + PKCE**, cùng trách nhiệm của Client, AS, Resource Owner và Resource Server.
3. Thiết kế màn hình consent rõ tên client, resource, scope, mục đích, thời hạn/quyền truy cập ngoại tuyến và cách từ chối.
4. Giải thích cách AS kiểm tra **scope được yêu cầu**, **quyền client**, **tenant policy**, **quyền người dùng** và **scope thực sự được cấp**.
5. Xử lý **người dùng từ chối**, **incremental consent**, **consent đã ghi nhớ**, OIDC `prompt=consent` / `prompt=none` và `offline_access`.
6. Nhận diện **consent phishing**, CSRF, thay đổi giao dịch giữa lúc hỏi quyền, sai redirect URI, authorization code injection và token bị sao chép/phát lại.
7. Đánh giá vòng đời consent, thu hồi grant, refresh token, JWT/opaque access token và kiểm thử các trường hợp không được cấp quyền.

## 1. Consent trong OAuth là gì và không phải là gì?

**User consent** là sự chấp thuận có ngữ cảnh của người dùng (Resource Owner trong nhiều trường hợp) để **một client xác định** sử dụng một số quyền truy cập tài nguyên nhất định. Ví dụ, ứng dụng **Spend Insights** xin đọc lịch sử đơn hàng thông qua **Orders API**.

~~~text
Người dùng:             user-123
Client xin quyền:        spend-insights-web
Authorization Server:    https://auth.example.test
Resource Server:         orders-api
Requested scope:         orders:read
Mục đích:                Hiển thị thống kê đơn đã mua
~~~

Một thông báo phù hợp có thể diễn đạt:

> “Spend Insights muốn xem những đơn hàng mà bạn được phép đọc. Ứng dụng không được sửa, hủy đơn hay thực hiện hoàn tiền.”

Người dùng có thể chấp thuận **quyền đọc đơn được mô tả**, nhưng không tự tạo thêm quyền:

- Nếu user chỉ được xem đơn của mình, consent **không** mở quyền xem đơn của tenant khác.
- Nếu client chỉ được AS đăng ký scope `orders:read`, user không thể qua một lần nhấn nút mà cấp scope `payments:refund` cho client đó.
- Nếu tổ chức cấm một client chưa kiểm duyệt, consent cá nhân **không** vượt policy của tenant.

### Bốn khái niệm phải tách riêng

| Hoạt động | Câu hỏi cần giải quyết | Trách nhiệm |
|---|---|---|
| **Authentication** | Người tương tác với AS là ai, đã xác thực đủ mạnh/chưa? | AS hoặc cơ chế định danh tin cậy của AS. |
| **User consent** | Người đó chấp thuận client này dùng những quyền nào? | AS thu quyết định theo giao dịch phù hợp. |
| **Authorization Server policy** | Grant, client, resource, tenant và scope có được hệ thống cho phép không? | AS quyết định quyền tối đa thực sự có thể cấp. |
| **Resource Server authorization** | Principal/client có được thực hiện action này trên bản ghi cụ thể không? | RS xác minh token, scope và policy dữ liệu. |

**Đăng nhập thành công không đồng nghĩa đồng ý cấp mọi quyền.** Đồng thời, **đã consent không đồng nghĩa access token sẽ dùng được tại mọi API** hoặc được truy cập mọi object.

### Consent OAuth và sự đồng ý về pháp lý

Consent trong OAuth là một cơ chế **ủy quyền kỹ thuật**. Nó **không mặc nhiên** đáp ứng tất cả yêu cầu pháp lý về sự đồng ý xử lý dữ liệu cá nhân, thông báo mục đích, khả năng rút lại hay cơ sở pháp lý. Một thiết kế sản phẩm cần đánh giá riêng yêu cầu pháp lý và quyền riêng tư theo khu vực, loại dữ liệu và quan hệ các bên.

## 2. Ai tham gia và consent diễn ra ở đâu?

Trong Authorization Code, các vai trò thường là:

| Vai trò | Ví dụ | Vai trò trong consent |
|---|---|---|
| **Resource Owner / User** | `user-123` | Xem yêu cầu, lựa chọn chấp thuận hoặc từ chối trong giới hạn quyền. |
| **OAuth Client** | `spend-insights-web` | Khởi tạo authorization request, yêu cầu scope/resource, nhận authorization response. |
| **Authorization Server** | `auth.example.test` | Xác thực user, xác minh client/redirect, quyết định cần consent không, ghi grant và cấp code/token theo policy. |
| **Resource Server** | `orders-api` | Sau khi nhận access token, kiểm tra audience/scope và quyền trên đơn cụ thể. |
| **Tenant administrator** (nếu có) | Quản trị tenant A | Có thể phê duyệt/chặn ứng dụng hoặc quyền ở cấp tổ chức theo chính sách. |

**Client không nên tự tạo màn hình xin quyền rồi khai rằng AS đã ghi nhận consent.** Một giao diện giới thiệu trong app không thay quyết định grant tại AS. Để tránh app giả mạo tên người dùng/ứng dụng hoặc thay scope, AS phải tự kiểm tra authorization request, trạng thái đăng nhập và lựa chọn được gửi về.

### Vị trí của consent trong luồng Authorization Code

~~~mermaid
sequenceDiagram
    actor U as User / Resource Owner
    participant B as Browser
    participant C as Client (BFF)
    participant AS as Authorization Server
    participant RS as Orders API
    U->>B: Chọn Kết nối đơn hàng
    B->>C: Khởi tạo authorization
    C->>C: Tạo state, PKCE verifier/challenge
    C-->>B: Redirect tới AS /authorize
    B->>AS: client_id + redirect_uri + scope + state + challenge
    AS->>AS: Kiểm tra client/redirect, login session và policy
    AS->>U: Hiển thị consent khi cần
    alt User từ chối hoặc policy cấm
        U-->>AS: Từ chối
        AS-->>B: Redirect lỗi tới callback hợp lệ (nếu được phép)
        B->>C: Nhận error + state
        C-->>B: Thông báo từ chối, không gọi Orders
    else User chấp thuận trong phạm vi cho phép
        U-->>AS: Chấp thuận
        AS->>AS: Ghi grant, phát authorization code ràng buộc giao dịch
        AS-->>B: Redirect code + state
        B->>C: Callback code + state
        C->>C: Kiểm tra state, issuer/response theo profile
        C->>AS: POST /token với code + PKCE verifier + client auth nếu cần
        AS-->>C: Access token audience Orders, scope được cấp
        C->>RS: Bearer access token /orders
        RS->>RS: Verify token + owner/tenant policy
        RS-->>C: Chỉ trả đơn được phép
    end
~~~

Ở một hệ thống đã có **grant/consent hợp lệ** hoặc chính sách quản trị phê duyệt sẵn, AS có thể **không cần hiển thị** màn hình consent mới. Việc không thấy màn hình không tự chứng minh hệ thống bỏ qua policy; phải xem điều kiện được AS áp dụng.

## 3. Client yêu cầu quyền bằng tham số nào?

Ví dụ client muốn dùng Authorization Code + PKCE để đọc Orders API:

~~~http
GET /authorize?response_type=code&client_id=spend-insights-web&redirect_uri=https%3A%2F%2Fapp.example.test%2Foauth%2Fcallback&scope=orders%3Aread&resource=https%3A%2F%2Fapi.example.test%2Forders&state=<RANDOM_STATE>&code_challenge=<S256_CHALLENGE>&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

Đây là **request minh họa rút gọn**, sử dụng placeholder. `resource` là tham số của **RFC 8707**, chỉ có tác dụng khi AS hỗ trợ. Trong OIDC, request còn có thể sử dụng `scope=openid ...`, `nonce` và những tham số riêng theo luồng/profile.

### Các tham số quan trọng

| Tham số | Client nêu điều gì? | AS phải làm gì? |
|---|---|---|
| `response_type=code` | Xin authorization code. | Chỉ cho client được dùng grant/response type này. |
| `client_id` | Client đã đăng ký nào đang yêu cầu? | Tra cứu client đáng tin; không coi client ID là secret. |
| `redirect_uri` | Đích gửi authorization response. | Kiểm tra khớp đăng ký theo quy tắc profile, tránh redirect tùy ý. |
| `scope` | Những quyền Client **muốn xin**. | Đối chiếu với registration, user/tenant/resource và consent. |
| `resource` | Resource Server đích, nếu AS hỗ trợ RFC 8707. | Kiểm tra target hợp lệ và ánh xạ audience đúng. |
| `state` | Liên kết authorization request/response và bảo vệ chống CSRF theo thiết kế. | Trả lại nguyên giá trị ở response tương ứng; Client kiểm tra. |
| `code_challenge` / `code_challenge_method` | Cam kết PKCE cho `code_verifier` chỉ Client nắm. | Ràng buộc code với PKCE để kiểm tra tại token endpoint. |
| `prompt` (OIDC, nếu dùng) | Mong muốn về tương tác user, ví dụ `consent`. | Áp dụng theo OIDC và policy; không tự cấp quyền vô điều kiện. |

**Requested scope không phải granted scope.** Việc Client đưa `orders:read payments:refund` lên URL **không** buộc AS phải cấp cả hai, cũng không chứng minh Resource Owner đã chấp thuận.

### Tên scope không thay audience

AS có thể ánh xạ:

~~~text
resource: https://api.example.test/orders
audience trong token: orders-api
scope được cấp: orders:read
~~~

`resource` và `aud` **không bắt buộc là chuỗi bằng nhau**. RS xác minh audience theo hợp đồng với AS; token có `scope=orders:read` nhưng `aud=billing-api` không được Orders chấp nhận.

## 4. AS phải kiểm tra điều gì trước khi hỏi consent?

Không nên hiển thị màn hình “Bạn có đồng ý không?” cho một request mà **client không hợp lệ**, redirect URI sai hoặc scope hoàn toàn bị policy cấm; điều đó có thể đánh lừa user rằng app đã được hệ thống tin tưởng.

### Các ranh giới trước màn hình

1. **Client registration:** `client_id` tồn tại, loại client phù hợp, response type/grant được cho phép, trạng thái client không bị khóa.
2. **Redirect URI:** đích callback hợp lệ, không phải URL tùy ý được kẻ tấn công cấy vào.
3. **Request consistency:** bảo vệ giao dịch (state, PKCE, issuer/transaction binding) và dữ liệu authorization request được giữ nguyên cho đến khi ra quyết định.
4. **Resource và scope:** AS có biết RS đích không; client có quyền xin những scope đó không?
5. **Người dùng:** đã đăng nhập với cơ chế và mức đảm bảo cần thiết chưa; user đang ở đúng tenant/organization?
6. **Policy tenant/admin:** tenant có cho phép app bên thứ ba, quyền đọc/ghi/nhạy cảm, hoặc bắt phê duyệt quản trị không?
7. **Consent trước đó:** đã có grant phù hợp đúng client, user, resource, tenant, scope, trạng thái và policy hiện hành chưa?

AS có thể loại bỏ scope không hợp lệ hoặc từ chối request theo policy/protocol. Nếu chọn hỗ trợ **cấp ít quyền hơn request**, màn hình và token sau đó phải phản ánh **đúng tập quyền thực sự được phép cấp**.

### Ví dụ đánh giá giới hạn

~~~text
Client requested       = {orders:read, orders:write, payments:refund}
Client allowed         = {orders:read, orders:write}
User entitlement       = {orders:read, orders:write}
Tenant policy          = {orders:read}
Resource supported     = {orders:read, orders:write}
Prior consent          = {orders:read}  (nếu còn hiệu lực)

Kết luận minh họa:
  orders:read          = có thể cấp
  orders:write         = không cấp vì tenant policy
  payments:refund      = không cấp vì client/resource/policy
~~~

Phép giao tập hợp trên chỉ giúp **hình dung giới hạn**; policy thật có thể còn điều kiện phụ thuộc vào thời điểm, loại client, dữ liệu, risk score và yêu cầu xác thực lại. **AS có thể từ chối cả request** thay vì tự động giảm scope nếu hệ thống không hỗ trợ partial grant.

### Consent chỉ có tác dụng trong phần quyền đã được phép

~~~mermaid
flowchart TD
    A["Authorization request"] --> B{"Client + redirect + grant hợp lệ?"}
    B -- Không --> X["Từ chối, không cấp code/token"]
    B -- Có --> C{"User/tenant/resource/scope policy cho phép?"}
    C -- Không --> X
    C -- Có --> D{"Đã có consent/grant tương ứng còn hiệu lực?"}
    D -- Có --> G["Xác định grant cuối cùng"]
    D -- Không --> E["Hiển thị consent cho đúng người dùng"]
    E --> F{"User chấp thuận quyền được phép?"}
    F -- Không --> X
    F -- Có --> G
    G --> H["Phát authorization code gắn với grant đã cho phép"]
    H --> I["Client đổi code, AS cấp token trong phạm vi grant"]
~~~

## 5. Màn hình consent tốt phải mô tả đúng điều gì?

Người dùng thường **không biết** `orders:read`, `offline_access` hay `reports:export` là gì. Giao diện cần chuyển scope thành **hành động hiểu được**, đồng thời tránh giấu bản chất quyền.

### Ví dụ nội dung consent minh bạch

~~~text
Spend Insights muốn kết nối với tài khoản của bạn

Ứng dụng: Spend Insights
Đơn vị phát hành: Công ty ứng dụng đã được kiểm tra theo trạng thái thực tế
Tài nguyên: Orders API

Ứng dụng muốn:
  ✓ Xem các đơn hàng mà tài khoản của bạn được phép đọc

Ứng dụng không được:
  ✗ Chỉnh sửa hoặc hủy đơn hàng
  ✗ Hoàn tiền hoặc truy cập thông tin thanh toán

Nếu bạn cho phép, ứng dụng có thể sử dụng quyền này
theo chính sách và trạng thái grant của tài khoản.
Bạn có thể xem và thu hồi quyền tại mục Ứng dụng đã kết nối.

[Từ chối]     [Cho phép đọc đơn hàng]
~~~

Đây là **mô phỏng giao diện**, không phải tuyên bố một ứng dụng cụ thể đã được xác minh. Trong giao diện thật, không được hiển thị nhãn “đã xác minh” nếu AS không có căn cứ kiểm chứng nhà phát triển/ứng dụng.

### Những yêu cầu UX–security

| Yêu cầu | Lý do bảo mật | Thực hành |
|---|---|---|
| **Danh tính Client rõ** | Chống app giả tên gần giống nhà phát triển uy tín. | Tên, đơn vị, thông tin xác minh theo nguồn đáng tin của AS. |
| **Mục đích và dữ liệu rõ** | User hiểu app dùng tài nguyên để làm gì. | “Xem lịch sử đơn”, không chỉ hiển thị `orders:read`. |
| **Phân biệt đọc/ghi/quản trị** | Tránh quyền nguy hiểm bị gộp trong nhãn chung. | “Xóa”, “xuất”, “hoàn tiền”, “đọc” là các quyền khác nhau. |
| **Từ chối dễ tìm** | Tránh thiết kế ép buộc/dark patterns. | Nút từ chối rõ ràng, không ẩn trong liên kết nhỏ. |
| **Không lạm dụng quyền dài hạn** | Giảm ảnh hưởng khi client bị lộ token. | Chỉ xin offline access khi thực sự cần. |
| **Nêu sự thay đổi** | Người dùng phân biệt consent trước và quyền đang xin thêm. | “Ứng dụng đang yêu cầu thêm quyền xuất báo cáo”. |
| **Công bố cách thu hồi** | User có thể cắt quyền không còn mong muốn. | Liên kết quản lý ứng dụng đã kết nối. |
| **Không cho dữ liệu client quyết định nhãn nhạy cảm** | Client độc hại có thể khai mô tả lừa user. | AS kiểm soát/kiểm duyệt metadata và mô tả quyền. |

### Client metadata không phải nguồn chân lý cho quyền

Tên ứng dụng, logo hay đường dẫn chính sách riêng tư có thể đến từ client registration; nếu AS hiển thị nguyên văn metadata do client tùy ý nhập, attacker có thể **giả danh ứng dụng phổ biến**. Quyền nào được phép xin và mô tả scope nhạy cảm phải dựa trên **hợp đồng và policy của AS/RS**, không chỉ đoạn văn do client tự tuyên bố.

### Partial consent: chỉ khi triển khai thật sự hỗ trợ

Một hệ thống có thể cho user chọn riêng:

~~~text
[x] Xem đơn hàng             (orders:read)
[ ] Thay đổi đơn hàng        (orders:write)
[ ] Xuất báo cáo định kỳ     (reports:export)
~~~

Khi đó AS phải chỉ ghi **những scope được chọn và được policy cho phép**, còn client phải kiểm tra scope cuối cùng. Nếu sản phẩm không hỗ trợ partial consent, giao diện nên minh bạch rằng user phải chấp thuận/từ chối **toàn bộ nhóm quyền** đang được đề nghị; không giả vờ user có thể chọn riêng rồi vẫn cấp tất cả.

## 6. Ràng buộc quyết định consent với đúng authorization request

Màn hình consent không nên là một form POST kiểu:

~~~http
POST /approve HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

client_id=trusted-app&scope=orders%3Aread%20payments%3Arefund&approved=true
~~~

nếu backend **tin nguyên `client_id`/`scope` trong body** mà không đối chiếu giao dịch đã xác minh. Caller có thể sửa form, thêm scope hoặc thay user/tenant.

### Thiết kế an toàn hơn

1. AS tạo một **authorization transaction** phía server hoặc một định danh giao dịch có bảo vệ toàn vẹn.
2. Giao dịch giữ **client ID, redirect URI, requested resource/scope, PKCE challenge, user/tenant, thời hạn và trạng thái** đã được xác minh.
3. Form consent chỉ chứa một **transaction reference chống giả mạo** và lựa chọn được phép; phải có biện pháp chống CSRF của trang AS.
4. Khi nhận quyết định, AS **lấy request gốc từ trạng thái đáng tin**, so khớp phiên user, tenant, client và policy hiện hành.
5. AS **không mở rộng** scope do tham số được gửi ở form; nếu user bỏ chọn quyền, AS giảm scope hoặc từ chối theo hợp đồng.
6. AS đánh dấu giao dịch **đã sử dụng/hết hạn** khi hoàn tất, ngăn cùng form bị gửi nhiều lần để tạo grant khác.

### Mã giả cho bước xử lý consent tại AS

~~~text
handleConsentPost(httpRequest):
    requireAuthenticatedSession()
    requireValidCsrfToken()

    tx = trustedAuthorizationTransactionStore.load(
        httpRequest.transactionId
    )
    if tx missing or expired or alreadyCompleted:
        deny

    if tx.authenticatedSubject != currentSession.subject:
        deny
    if tx.tenant != currentSession.tenant:
        deny

    client = trustedClientRegistry.find(tx.clientId)
    policy = evaluateCurrentAuthorizationPolicy(
        client, currentSession.subject, tx.resource, tx.requestedScopes
    )
    if policy.denies:
        deny

    approved = parseSelectedScopes(httpRequest.selectedScopes)
    if not approved subsetOf tx.requestedScopes:
        deny
    if not approved subsetOf policy.allowedScopes:
        deny
    if approved empty and policy.requiresNonEmptyGrant:
        deny

    saveConsentGrant(subject, client, tenant, resource, approved)
    markTransactionCompletedAtomically(tx)
    issueOneTimeAuthorizationCodeBoundTo(
        tx.clientId, tx.redirectUri, tx.codeChallenge,
        subject, tenant, resource, approved
    )
~~~

Đây là **pseudocode bảo mật**, không phải một AS triển khai hoàn chỉnh. Code phát hành sau consent phải dựa vào **trạng thái giao dịch đã xác minh**, không chấp nhận user ID, tenant hay scope được khai tùy tiện trong request từ browser.

**CSRF ở màn hình consent** khác với việc Client kiểm tra `state` tại callback. Hai bên xử lý hai ranh giới: AS bảo vệ thao tác chấp thuận, Client bảo vệ liên kết authorization response với lần khởi tạo trước đó.

## 7. Sau consent, authorization code đại diện cho điều gì?

Khi AS đã xác thực user, áp dụng policy và thu quyết định cần thiết, AS có thể phát **authorization code**. Code không phải access token và **không phải permission để Client dùng trực tiếp tại Resource Server**.

Ví dụ redirect response từ AS:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.test/oauth/callback?code=<AUTH_CODE>&state=<ORIGINAL_STATE>
Cache-Control: no-store
~~~

Client nhận code tại callback và đổi tại token endpoint:

~~~http
POST /token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<AUTH_CODE>&redirect_uri=https%3A%2F%2Fapp.example.test%2Foauth%2Fcallback&client_id=spend-insights-web&code_verifier=<ORIGINAL_PKCE_VERIFIER>
~~~

Ví dụ trên minh họa **public client**. **Confidential client** còn phải xác thực tại token endpoint theo phương thức đã đăng ký, không coi `client_id` trong body là mật khẩu. Request được gửi qua **HTTPS**.

### Authorization code phải được ràng buộc

AS cần kiểm tra code:

- Có tồn tại, **còn hạn** và **chưa được dùng**.
- Được phát hành cho **client ID** đang đổi code.
- Ràng buộc với **redirect URI** đã dùng trong authorization request nếu quy tắc grant yêu cầu.
- Ràng buộc với **PKCE challenge** và được đổi bằng `code_verifier` khớp.
- Gắn với **authorization grant** đã được cấp: principal, resource, scope và những hạn chế khác.
- Không bị sử dụng để **đổi sang scope/audience mới vượt grant** tại token endpoint.

**Chỉ chấp thuận rồi trả code chưa đủ.** Nếu token endpoint không xác minh code dùng một lần và PKCE, attacker có thể cố đổi code bị đánh cắp hoặc thay đổi context cấp token.

### Phản hồi token cần thể hiện phạm vi thực tế

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<OPAQUE_ACCESS_TOKEN_PLACEHOLDER>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders:read"
}
~~~

Đây là **phản hồi minh họa**. Theo OAuth 2.0, trường `scope` trong token response được yêu cầu khi **khác phạm vi đã yêu cầu**, và có thể lược bỏ khi như cũ. Client không được suy rằng `requested_scope = granted_scope` nếu AS đã giới hạn quyền. Refresh token chỉ được cấp **khi policy và profile cho phép**, không phải kết quả bắt buộc của mọi consent.

## 8. User consent, scope và authorization trên dữ liệu

Giả sử token đã được AS cấp có metadata đã xác minh:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "client_id": "spend-insights-web",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1893456000,
  "exp": 1893456600,
  "tenant_id": "tenant-a"
}
~~~

Payload chỉ minh họa, **không phải JWT thật**. Nếu Client yêu cầu:

~~~http
GET /orders/order-42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN_FOR_ORDERS>
~~~

nhưng database lưu:

~~~json
{
  "id": "order-42",
  "tenantId": "tenant-b",
  "ownerId": "user-999"
}
~~~

thì Orders API **phải từ chối** nếu user-123 không có quyền liên tenant được cấp riêng.

### Năm điều RS phải kiểm tra

1. **Tính tin cậy của token**: JWT signature/issuer/thuật toán/khóa hoặc opaque introspection từ AS tin cậy.
2. **Đúng audience, loại, trạng thái và thời hạn**: token dành cho Orders API, không phải ID token của OIDC client hay refresh token.
3. **Scope action**: `orders:read` được cấp thực sự; không chỉ là scope Client từng xin trên URL.
4. **Quyền trên object**: owner, tenant, role/permission, trạng thái và chính sách dữ liệu tại thời điểm thực hiện.
5. **Sender proof nếu có**: DPoP hoặc mTLS-bound token cần RS kiểm tra khả năng sử dụng khóa/chứng chỉ đã ràng buộc.

**Consent chỉ cho Client quyền yêu cầu loại thao tác trong phạm vi được cấp**; nó không thay kiểm tra từng đơn hàng, dữ liệu cá nhân, quyền field-level hay chính sách nghiệp vụ hiện hành.

### Ba chuỗi không được đồng nhất

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| `client_id` | `spend-insights-web` | Ứng dụng được AS xác định là Client. |
| `sub` | `user-123` | Subject theo token/profile; thường là user với delegated grant. |
| `aud` | `orders-api` | Bên nhận access token hợp lệ. |

Client ID đúng không có nghĩa client được xem mọi record; subject đúng không có nghĩa user chính là người đang cầm bearer token; audience đúng không có nghĩa scope hoặc quyền dữ liệu đủ.

## 9. Khi nào AS không hiển thị consent mới?

**OAuth 2.0 không yêu cầu mọi authorization request phải hiện một hộp thoại consent mỗi lần.** AS có thể dựa vào những điều kiện quản trị/ủy quyền đã có, miễn quyết định cấp quyền vẫn được kiểm soát.

Các trường hợp thường gặp:

| Trường hợp | Có thể bỏ màn hình mới? | Điều kiện |
|---|---|---|
| **Grant đã ghi nhớ** cho cùng user/client/resource/scope | **Có thể**. | Grant còn hiệu lực, policy hiện hành cho phép tái sử dụng. |
| **Client first-party** trong hệ thống nội bộ | **Có thể**. | Chính sách tin cậy/phê duyệt được AS kiểm soát; không miễn kiểm tra quyền. |
| **Admin consent/phê duyệt tổ chức** | **Có thể**. | Người quản trị có quyền phù hợp trong đúng tenant và phạm vi. |
| **Ứng dụng chỉ xin scope đã được phép trước** | **Có thể**. | Không mở rộng quyền hoặc ngữ cảnh mới. |
| **Client xin scope mới/quyền nhạy cảm hơn** | **Thường cần quyết định mới**. | AS phải đánh giá policy và consent/phê duyệt cho quyền mới. |
| **Grant đã bị rút hoặc hết hiệu lực** | **Không được tái sử dụng**. | Chặn hoặc yêu cầu cấp quyền mới theo quy trình. |

### Consent đã lưu phải gắn với ngữ cảnh

Một bản ghi grant có thể có các chiều:

~~~json
{
  "subject": "user-123",
  "client_id": "spend-insights-web",
  "tenant_id": "tenant-a",
  "resource": "orders-api",
  "approved_scopes": ["orders:read"],
  "status": "active",
  "granted_at": "2026-11-23T08:30:00Z",
  "policy_version": "v3"
}
~~~

Đây là **schema minh họa**, không phải chuẩn bắt buộc của OAuth. `granted_at` chỉ là ví dụ về thời điểm lưu grant. Hệ thống phải ngăn sử dụng grant của **user A cho user B**, **client A cho client B**, hoặc **tenant A cho tenant B**.

### Thay đổi policy sau khi user đã consent

Giả sử tenant admin chặn ứng dụng Spend Insights sau khi user từng chấp thuận. AS không được tiếp tục cấp token mới **chỉ vì** có bản ghi consent cũ. Khi policy thay đổi, hệ thống phải xác định grant nào cần hết hiệu lực, phạm vi nào bị hủy và phương pháp thông báo cho user.

## 10. Incremental consent và quyền được bổ sung

**Incremental consent** là cách Client xin thêm quyền **khi tính năng cần dùng**, thay vì yêu cầu quá nhiều quyền ngay khi đăng nhập.

### Ví dụ

~~~text
Lần 1: User kết nối app để xem lịch sử đơn
  requested: orders:read
  granted:   orders:read

Lần 2: User bật chức năng gắn ghi chú vào đơn
  requested: orders:write (hoặc tập scope theo chính sách AS)
  quyết định mới: hỏi/duyệt quyền mới nếu cần

Không hợp lệ:
  Diễn giải consent cũ orders:read thành orders:write.
~~~

AS có thể dùng **grant đã có** và thu thêm quyết định cho quyền mới. Cách gộp scope cũ/mới phụ thuộc AS/profile; Client phải đọc **phạm vi thực tế** và không mặc định có toàn bộ quyền chỉ vì user từng đồng ý cho một tính năng.

### Tác dụng bảo mật và trải nghiệm

- **Giảm đặc quyền ban đầu:** token đọc đơn không đồng thời có quyền sửa/xóa.
- **Dễ hiểu mục đích:** user thấy quyền mới khi chủ động bật tính năng tương ứng.
- **Giảm thiệt hại khi token bị lộ:** bearer token chỉ có scope đã cấp.
- **Dễ quản lý quyền:** hệ thống có thể thu hồi một scope/grant cụ thể theo khả năng AS.

Một app cố gợi ý hàng loạt request consent để người dùng liên tục “bấm cho xong” có thể làm mất mục đích của incremental consent. Nên giới hạn tần suất hỏi và giải thích **điểm khác biệt** so với grant hiện có.

## 11. OIDC `prompt=consent`, `prompt=none` và `offline_access`

Nếu Authorization Code được dùng trong **OpenID Connect**, Client thường còn là **Relying Party (RP)**. OIDC bổ sung các quy tắc về xác thực user và tương tác consent; **không nên áp dụng tham số OIDC như một đặc điểm mặc định của mọi OAuth 2.0 server**.

### `prompt=consent`

OIDC cho phép Client đề nghị OP/AS **nhắc lại tương tác consent**:

~~~http
GET /authorize?response_type=code&client_id=spend-insights-web&scope=openid%20orders%3Aread&prompt=consent&state=<STATE>&code_challenge=<CHALLENGE>&code_challenge_method=S256&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback HTTP/1.1
Host: auth.example.test
~~~

`prompt=consent` **không buộc AS cấp scope**, không vượt policy tenant và không xác thực user thay các biện pháp login. Nó chỉ chỉ dẫn về hành vi tương tác theo OIDC trong giới hạn đặc tả/chính sách.

### `prompt=none`

`prompt=none` yêu cầu OP/AS **không hiển thị UI tương tác**. Nếu chưa xác thực user hoặc chưa có quyết định cần thiết mà không thể hoàn tất âm thầm, OP có thể trả lỗi như `login_required`, `consent_required` hay `interaction_required` theo OIDC và tình huống.

Không được xử lý “không được hiện consent” bằng cách **tự động chấp thuận**. `prompt=none` nghĩa là không được tương tác, **không phải** miễn policy.

### `offline_access` và refresh token

Trong OIDC, `offline_access` là scope liên quan đến quyền truy cập khi user **không đang hiện diện trực tiếp**. Khi client đề nghị khả năng dùng refresh token để tiếp tục gọi API, AS/OP phải áp dụng các điều kiện theo OIDC và chính sách; yêu cầu consent có vai trò quan trọng trong việc cho phép truy cập dài hạn.

~~~text
scope=openid orders:read offline_access
~~~

Điểm cần phân biệt:

- **Xin `offline_access` không bảo đảm AS cấp refresh token.**
- Nếu refresh token được cấp, Client phải lưu giữ và bảo vệ đặc biệt, chỉ dùng tại **token endpoint của AS**.
- Refresh token không được trình trực tiếp cho Orders API.
- Refresh token dùng để xin access token mới **trong giới hạn grant**, không tạo scope vượt consent/policy đã cho phép.
- Với public client, AS cần biện pháp bảo vệ refresh token phù hợp, chẳng hạn **rotation** hoặc **sender-constraining** theo BCP/profile áp dụng.
- User rút consent hoặc admin thu hồi grant thì AS phải chặn những lần cấp token mới dựa trên grant đã bị thu hồi.

### ID token và access token không giống nhau

OIDC **ID token** dành cho Client/RP để đánh giá kết quả xác thực user, thường có `aud` là **client ID**. OAuth **access token** dành cho **Resource Server**, thường có audience API. **Không** trình ID token cho Orders API chỉ vì hai token được phát hành sau cùng một lần user consent.

## 12. Nếu user từ chối: lỗi được xử lý ra sao?

Từ chối quyền là **một kết quả hợp lệ của luồng**, không phải trường hợp client được ép user thử lại mãi.

Khi user từ chối và **Client + redirect URI đã được xác minh hợp lệ**, AS có thể gửi authorization error theo OAuth:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.test/oauth/callback?error=access_denied&state=<ORIGINAL_STATE>
Cache-Control: no-store
~~~

Client cần:

1. **Kiểm tra `state`** và sự tương ứng với phiên giao dịch đã khởi tạo.
2. Xác định `error=access_denied`, xử lý như **quyền chưa được cấp**, không giả định còn authorization code hợp lệ.
3. Thông báo trung tính, không áp lực: “Bạn chưa cấp quyền kết nối đơn hàng. Bạn vẫn có thể dùng các phần khác của ứng dụng.”
4. Không gọi Resource Server như thể đã nhận token, không tự ý chuyển sang quyền của client khác.
5. Nếu thật sự cần tính năng, cho user khởi tạo một giao dịch mới có giải thích scope chính xác.

### Không redirect tới URI chưa được xác thực

Nếu `client_id` không hợp lệ, `redirect_uri` không khớp hoặc không thể xác định Client an toàn, AS **không được tự động đưa lỗi/code đến một địa chỉ redirect không đáng tin**. Một lỗi callback có thể làm lộ authorization code/state hoặc chuyển user sang website attacker.

### Những trường hợp lỗi khác

| Nguồn lỗi | Ví dụ | Ứng xử |
|---|---|---|
| **User từ chối** | OAuth `access_denied`. | Không cấp grant tương ứng, cho phép hủy tính năng. |
| **Client không được phép scope** | `invalid_scope` hoặc error theo profile. | Sửa registration/policy; không hỏi user để vượt hạn chế. |
| **Không đủ tương tác OIDC** | `login_required`, `consent_required`, `interaction_required` khi phù hợp. | Khởi tạo luồng tương tác nếu policy cho phép. |
| **Request invalid** | Sai client/redirect hoặc request giả mạo. | Không redirect tới đích không xác minh; từ chối an toàn. |
| **Code đã dùng/sai PKCE** | Lỗi ở token endpoint. | Không phát token; cần luồng mới hợp lệ. |
| **Token hợp lệ nhưng thiếu scope tại RS** | HTTP 403, `insufficient_scope` khi phù hợp. | Không tự tăng scope; có thể xin quyền mới qua grant mới. |
| **Token thiếu/hết hạn/sai issuer/audience** | HTTP 401 tại RS. | Xử lý token đúng lifecycle, không bỏ xác minh. |

**Phân biệt lỗi authorization endpoint với HTTP 401/403 từ Resource Server.** Người dùng từ chối consent ở AS nghĩa là Client **chưa nhận quyền**; 403 ở RS thường là Client **có token nhưng quyền không đủ** cho action/resource.

## 13. Admin consent và quyền phê duyệt theo tổ chức

Không phải quyền nào một user cũng có thể tự cấp cho Client. Một hệ thống doanh nghiệp có thể quy định:

| Quyền/ứng dụng | Ai có thể phê duyệt? | Ví dụ |
|---|---|---|
| Xem dữ liệu cá nhân user được phép xem | User, nếu tenant policy cho phép. | `orders:read` cho danh sách đơn của user. |
| Đọc báo cáo cả bộ phận | User có quyền riêng hoặc tenant admin theo policy. | `reports:read:department`. |
| Truy cập dữ liệu cấp tổ chức | Admin có thẩm quyền theo tenant, tùy mô hình. | `directory:read:all`. |
| Ứng dụng chưa được kiểm duyệt xin scope rủi ro cao | Có thể bị chặn hoặc cần admin review. | `payments:refund`. |

**Admin consent không phải giấy phép vô hạn**. Admin tenant A không mặc nhiên có quyền phê duyệt truy cập dữ liệu của tenant B. AS cần kiểm tra ai là admin, phê duyệt cho **client nào**, **resource nào**, **scope nào** và **tenant nào**.

Một tổ chức có thể chủ động cho phép **first-party app** hoặc ứng dụng đã được kiểm duyệt truy cập những quyền nhất định không cần hỏi user mỗi lần. Tuy nhiên, RS vẫn phải kiểm tra quyền trên từng đối tượng; không đánh đồng “app được admin phê duyệt” với “user có quyền xem mọi dữ liệu”.

### Không nhầm client credentials với user consent

Trong grant `client_credentials`, ứng dụng nhận **quyền dịch vụ**, không có user tương tác mỗi lần xin token; quyền phải được phê duyệt trước theo chính sách tổ chức/AS. Trong **Authorization Code**, Client thường yêu cầu **quyền truy cập theo ngữ cảnh user**. Không dùng service token quyền rộng để “đi vòng” user đã từ chối consent.

## 14. Lưu grant, thu hồi consent và tác động tới token đã cấp

User có thể rút quyền của Client qua danh sách **ứng dụng đã kết nối**. AS cần liên kết quyết định đó với các grant liên quan; tuy nhiên, cần phân biệt **rút consent** và **vô hiệu hóa access token đã phát hành**.

### Quy trình thu hồi điển hình

~~~mermaid
sequenceDiagram
    actor U as User
    participant AS as Authorization Server
    participant C as Client
    participant RS as Orders API
    AS-->>C: Access token A; có thể refresh token R
    U->>AS: Thu hồi quyền cho Spend Insights
    AS->>AS: Vô hiệu hóa grant tương ứng
    AS->>AS: Thu hồi R và token/trạng thái liên quan theo khả năng
    C->>AS: Thử dùng R xin access token mới
    AS-->>C: Từ chối nếu grant/R đã bị thu hồi
    C->>RS: Thử gọi API với access token A cũ
    RS->>RS: Kiểm tra exp và cơ chế thu hồi/state
    RS-->>C: Kết quả tùy trạng thái A và chính sách kiểm tra
~~~

### Tại sao rút consent không tự giết mọi JWT?

JWT access token có `exp` ở tương lai và chữ ký hợp lệ **có thể vẫn được RS chấp nhận** nếu RS chỉ kiểm tra chữ ký/`exp` mà **không tra cứu trạng thái thu hồi**. Rút grant tại AS có thể chặn cấp token **mới**, nhưng không tự động thay payload JWT mà RS đang kiểm tra offline.

Các cơ chế giải quyết tùy yêu cầu:

- **TTL access token ngắn** để giảm thời gian quyền cũ tồn tại.
- **Opaque token + introspection (RFC 7662)** hoặc stateful verification nếu cần cập nhật nhanh trạng thái.
- **Revocation (RFC 7009)**, denylist/session version và thông báo sự kiện tới RS theo kiến trúc.
- **Kiểm tra entitlement hiện hành** tại RS cho action nhạy cảm, kể cả khi token còn hạn.
- **Quy tắc cache** introspection/permission đủ ngắn so với mục tiêu thu hồi.

**Không ghi nguyên access token/refresh token vào bản ghi consent hoặc log** chỉ để lưu lịch sử ai đã đồng ý. Bản ghi grant và credential có mục đích/lifecycle khác nhau.

### Logout, revoke và disconnect không đồng nghĩa

| Hành động | Có thể thay đổi gì? | Điều không tự được bảo đảm |
|---|---|---|
| **Logout khỏi Client** | Kết thúc session ở Client/BFF. | Không tự thu hồi mọi access token/refresh token. |
| **Logout khỏi AS/OP** | Kết thúc phiên xác thực ở AS theo cơ chế hỗ trợ. | Không nhất thiết vô hiệu hóa mọi token Client đã có. |
| **Disconnect/revoke consent** | Hủy quyền Client đã được cấp trong AS. | Không tự làm JWT offline còn hạn bị RS từ chối ngay. |
| **Revoke refresh token** | Chặn refresh dựa trên token/grant bị thu hồi. | Không nhất thiết vô hiệu hóa bản sao access token cũ. |
| **Revoke access token** | Vô hiệu hóa token nếu AS/RS có cơ chế thực thi. | Cần xem RS có nhận/kiểm tra thay đổi không. |

## 15. Consent phishing và các mối đe dọa

### 15.1. Consent phishing — sử dụng trang AS thật để xin quyền sai

Attacker có thể đăng ký một OAuth Client với tên/biểu tượng giống ứng dụng đáng tin, gửi link yêu cầu người dùng đăng nhập **tại AS thật**, rồi dụ user chấp thuận các scope quá rộng.

~~~mermaid
flowchart LR
    A["Ứng dụng giả danh"] --> B["OAuth authorize URL với scope nhạy cảm"]
    B --> C["AS hiển thị consent thật"]
    C --> D{"User chấp thuận và policy có cho phép?"}
    D -- Có --> E["AS cấp token hợp lệ cho client của attacker"]
    E --> F["Client attacker truy cập trong phạm vi quyền"]
    D -- Không --> G["Không cấp grant tương ứng"]
~~~

Đây không phải kiểu tấn công bắt buộc lấy trộm mật khẩu. **Đăng nhập trên đúng website AS không bảo đảm Client xin quyền là đáng tin**. AS cần kiểm tra danh tính app, chính sách đăng ký, giới hạn scope nhạy cảm, admin approval và trình bày rõ consent.

### 15.2. Form consent bị sửa

Attacker thay field `approved_scopes` trên form từ `orders:read` thành `orders:read payments:refund`. Nếu AS tin body mà không tra transaction và policy, quyền có thể bị nâng. **Chặn bằng quyết định phía server**, CSRF protection và ràng buộc form với authorization transaction.

### 15.3. CSRF tại AS và login CSRF tại Client

Một thao tác consent thiếu CSRF protection có thể bị site khác kích hoạt trong phiên user. Đồng thời, Client không kiểm tra `state` có thể bị ép nhận authorization response thuộc một giao dịch khác. Phải bảo vệ **cả giao dịch consent tại AS** và **callback tại Client**.

### 15.4. Redirect URI/open redirect

Nếu AS cho redirect về URL attacker hoặc Client có open redirect, authorization code có thể rơi sai đích. AS phải xác minh redirect URI theo cấu hình, và Client không chuyển code/token đến URL tùy ý.

### 15.5. Code bị đánh cắp hoặc tiêm vào callback

PKCE `S256` cùng code verifier riêng giao dịch giúp chống việc người chỉ giữ code đổi thành token. `state`/ràng buộc issuer và authorization response giúp Client xác định callback thuộc giao dịch nào. Không đặt code/token vào log; code phải **ngắn hạn và dùng một lần**.

### 15.6. Token bị đánh cắp/phát lại

Một bearer access token do consent hợp lệ vẫn có thể bị **sao chép** từ browser, server logs hoặc thiết bị. Chữ ký JWT xác nhận toàn vẹn/issuer, **không chứng minh người đang cầm token chính là Client ban đầu**. Dùng TLS, scope/audience hẹp, TTL, lưu trữ an toàn, thu hồi và sender-constrained token (DPoP/mTLS) khi cần.

### 15.7. Quyền dữ liệu vượt scope danh nghĩa

Client có `orders:read` nhưng dùng API thiếu object authorization để đọc `/orders/{id}` của user khác. Đây là lỗi tại RS: **consent và scope không thay owner/tenant checks**.

## 16. Consent trong SPA, mobile và BFF

### SPA/public client

Nếu JavaScript trong browser là OAuth Client, đó là **public client**: không thể giữ một shared client secret như bí mật lâu dài. Authorization Code + PKCE, redirect URI chính xác và bảo vệ state/callback là quan trọng. User consent nên được quản lý ở AS, **không lưu một boolean “userApproved=true” trong localStorage rồi coi là grant tin cậy**.

### Native/mobile app

Native app cũng thường là public client. Theo best practice, dùng **system browser/external user-agent** để user tương tác với AS thay vì thu mật khẩu trong webview không phù hợp; PKCE và redirect URI/app-link handling cần được bảo vệ. Consent vẫn gắn với client registration và authorization transaction tại AS.

### Backend for Frontend (BFF)

Với web có backend đáng tin, BFF có thể là **confidential OAuth Client**; BFF nhận code, đổi token, giữ access/refresh token phía server. Browser giữ **opaque session ID** trong cookie `HttpOnly; Secure; SameSite`.

~~~mermaid
sequenceDiagram
    actor U as User
    participant Browser
    participant BFF
    participant AS as Authorization Server
    participant API as Orders API
    Browser->>BFF: Start OAuth connection
    BFF-->>Browser: Redirect tới AS với state + PKCE
    Browser->>AS: Authorization request
    AS->>U: Xác thực/consent nếu cần
    AS-->>Browser: Redirect code + state
    Browser->>BFF: Callback
    BFF->>AS: Token exchange (PKCE + client auth)
    AS-->>BFF: Access token (có thể refresh token)
    BFF->>BFF: Giữ token ở backend, tạo session
    BFF-->>Browser: Set-Cookie session HttpOnly; Secure
    Browser->>BFF: Request + cookie session
    BFF->>API: Bearer access token đúng audience
    API-->>BFF: Dữ liệu trong phạm vi được phép
~~~

**BFF giảm khả năng JavaScript đọc và mang token OAuth ra ngoài**, nhưng **không xóa rủi ro XSS gửi request trong phiên** hoặc CSRF khi browser tự gắn cookie. BFF phải bảo vệ session, CSRF, refresh token và logout/thu hồi; RS vẫn kiểm tra authorization.

### User từ chối ở bất kỳ mô hình client nào

Dù SPA, native hay BFF, Client phải xem **từ chối là kết quả bình thường**. Không tự đổi sang Client Credentials với service token quyền rộng, không tìm cách lưu cookie/token cũ của user khác và không bắt user cung cấp mật khẩu để né màn hình AS.

## 17. Java: mô hình kiểm soát grant sau consent

Đoạn Java sau **không phải implementation của Authorization Server**. Nó minh họa một **policy check thuần Java** trên dữ liệu đã được AS xác thực và chuẩn hóa, tránh cấp scope vượt giới hạn.

~~~java
import java.util.Collections;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

record TrustedConsentContext(
    String authenticatedUserId,
    String registeredClientId,
    String resourceAudience,
    Set<String> requestedScopes,
    Set<String> clientAllowedScopes,
    Set<String> userEntitledScopes,
    Set<String> tenantAllowedScopes
) {}

record ConsentSelection(
    String authenticatedUserId,
    String registeredClientId,
    Set<String> approvedScopes
) {}

final class ConsentGrantPolicy {
    static Set<String> grantedScopes(
            TrustedConsentContext context, ConsentSelection selection) {
        if (context == null || selection == null
                || context.authenticatedUserId() == null
                || context.registeredClientId() == null
                || context.resourceAudience() == null
                || !Objects.equals(
                    context.authenticatedUserId(), selection.authenticatedUserId())
                || !Objects.equals(
                    context.registeredClientId(), selection.registeredClientId())
                || context.requestedScopes() == null
                || context.clientAllowedScopes() == null
                || context.userEntitledScopes() == null
                || context.tenantAllowedScopes() == null
                || selection.approvedScopes() == null
                || selection.approvedScopes().isEmpty()) {
            return Collections.emptySet();
        }

        Set<String> approved = selection.approvedScopes();
        // Không tự giảm quyền mà không thông báo: nếu chọn quyền vượt
        // giới hạn, từ chối giao dịch và yêu cầu xử lý policy rõ ràng.
        if (!context.requestedScopes().containsAll(approved)
                || !context.clientAllowedScopes().containsAll(approved)
                || !context.userEntitledScopes().containsAll(approved)
                || !context.tenantAllowedScopes().containsAll(approved)) {
            return Collections.emptySet();
        }
        return Collections.unmodifiableSet(new HashSet<>(approved));
    }
}
~~~

**Giới hạn quan trọng của ví dụ:**

- `TrustedConsentContext` phải đến từ **authorization transaction và policy phía AS**, không được dựng trực tiếp từ JSON/browser. Trong thực tế cần kiểm tra client, redirect, tenant, resource, trạng thái session, CSRF, thời hạn giao dịch và quyền động.
- `ConsentSelection` cần được ràng buộc với **phiên user và transaction ID đáng tin**. Field user/client trong selection ở đây chỉ nhấn mạnh việc đối chiếu; không tin các giá trị người dùng tự khai là bằng chứng danh tính.
- `Set<String>` minh họa **scope đơn giản**; một hệ thống có thể cần constraints theo resource, thời gian, tenant, role, action hoặc policy dựa trên thuộc tính.
- Tập rỗng trong ví dụ nghĩa là **không được cấp grant**; framework sản xuất cần trả lỗi OAuth/OIDC phù hợp thay vì trả token scope rỗng.
- Khi quyết định scope xong, AS còn phải phát **authorization code dùng một lần ràng buộc PKCE**, kiểm tra khi đổi code và phát token có đúng audience, scope và TTL.

### Resource Server kiểm tra scope sau khi token đã được xác minh

~~~text
GET /orders/{orderId}:
    token = verifyAccessTokenFromTrustedIssuerOrIntrospection()
    require token.aud containsExactly "orders-api"
    require token.scope includesExactly "orders:read"

    order = loadOrderFromDatabase(orderId)
    require order.tenant == authorizedPrincipal.tenant
    require order.owner == authorizedPrincipal.subject
            OR principal has explicit owner-override permission

    return only fields authorized for this principal
~~~

Không thay đoạn kiểm tra trên bằng `if consentGranted then allowAllOrders`. Grant quyết định **phạm vi Client có thể yêu cầu**; RS mới là nơi kiểm tra **tài nguyên cụ thể**.

## 18. Ma trận kiểm thử consent trong Authorization Code

Giả sử client `spend-insights-web` được phép xin `orders:read` tại `orders-api`, user `user-123` thuộc `tenant-a`, và AS yêu cầu consent khi chưa có grant phù hợp.

| Tình huống | Kỳ vọng | Điều được kiểm chứng |
|---|---|---|
| User chưa consent, Client xin `orders:read` hợp lệ | Hiển thị consent theo policy. | Đúng điều kiện tương tác. |
| User chấp thuận `orders:read` | Có thể phát code; sau exchange phát token trong phạm vi grant. | Quyết định được áp dụng đúng. |
| User từ chối | Không phát grant/token tương ứng; trả `access_denied` khi redirect hợp lệ. | Từ chối được tôn trọng. |
| Client xin `payments:refund` không được đăng ký | AS từ chối hoặc không cấp scope đó. | Consent không vượt client policy. |
| User chấp thuận scope vượt entitlement của mình | AS không cấp phần vượt quyền. | User consent không tự tạo entitlement. |
| Tenant admin đã chặn client | AS không cấp quyền dù user từng chấp thuận. | Tenant policy được thực thi. |
| Client chỉ xin scope cũ, grant còn hiệu lực | AS có thể bỏ qua màn hình mới. | Tái sử dụng grant đúng ngữ cảnh. |
| Client xin thêm `orders:write` | Yêu cầu quyết định mới hoặc từ chối theo policy. | Không mở rộng consent cũ. |
| Client thay user/tenant giữa consent và callback | Từ chối giao dịch không nhất quán. | Transaction binding. |
| Form consent POST thêm `payments:refund` so với request | AS không cấp scope được cấy. | Không tin body browser. |
| Gửi lại form consent đã hoàn tất | Từ chối/reject duplicate; không tạo grant khác. | Transaction one-time. |
| Consent POST thiếu/sai CSRF token theo chính sách AS | Từ chối. | Bảo vệ giao dịch AS. |
| `redirect_uri` không khớp đăng ký | AS không gửi code/error tới URI đó. | Không redirect tới đích không tin cậy. |
| Callback Client nhận `state` không đúng | Client từ chối response. | Chống authorization response injection. |
| Code đổi bằng `code_verifier` sai | Token endpoint từ chối. | PKCE ràng buộc code. |
| Cùng code được đổi lần thứ hai | Token endpoint từ chối. | Authorization code dùng một lần. |
| OIDC `prompt=none` nhưng bắt buộc tương tác consent | Trả lỗi OIDC phù hợp, không tự chấp thuận. | No-UI không phải bypass. |
| Client xin `offline_access` nhưng policy cấm refresh token | Không tự cấp refresh token. | Offline access bị giới hạn. |
| Token `aud=billing-api` mang `orders:read` gửi Orders | RS từ chối. | Scope không thay audience. |
| Token đúng scope nhưng order thuộc tenant B | RS từ chối. | Object-level authorization. |
| User rút consent, Client dùng refresh token đã bị thu hồi | AS từ chối refresh. | Grant/refresh revocation. |
| JWT access token cũ còn hạn, RS chỉ kiểm tra chữ ký/exp | Có thể vẫn được chấp nhận nếu không có revocation check. | Hạn chế thu hồi tức thời. |
| Attacker sao chép bearer token còn hạn | Có nguy cơ dùng lại trong phạm vi quyền. | Consent không chống replay. |
| Client giả tên giống ứng dụng uy tín, scope rộng | Chính sách AS cần giới hạn; người dùng được hiển thị danh tính rõ. | Chống consent phishing. |

**Kịch bản tích hợp bắt buộc xem cả hai phía:** Client nhận authorization response và token; AS xác minh transaction/consent; RS xác minh token và permission. Test màn hình UI đơn lẻ không đủ chứng minh token được cấp/thu hồi đúng.

## 19. Tình huống tự luyện

**Tình huống A — Đã login thì có consent?** User đã đăng nhập AS trước đó. Một Client mới xin `orders:read`. AS có được mặc nhiên phát code mà bỏ mọi quyết định ủy quyền không?

**Giải thích:** Không. AS cần đánh giá client, policy, consent/grant hiện có và điều kiện được phép bỏ tương tác. Phiên đăng nhập chỉ giải quyết xác thực user.

**Tình huống B — User đồng ý cho đọc, Client xin ghi.** User từng chấp thuận `orders:read`. Hôm nay Client xin `orders:write`. AS có thể phát token ghi dựa trên consent cũ?

**Giải thích:** Không. Quyền mới cần được policy cho phép và có quyết định/consent tương ứng nếu yêu cầu; không suy quyền ghi từ quyền đọc.

**Tình huống C — Form bị chỉnh sửa.** Browser sửa `approvedScopes` thành `payments:refund` dù trang hiển thị chỉ có `orders:read`. AS nên làm gì?

**Giải thích:** Từ chối hoặc bỏ quyền không hợp lệ theo hợp đồng đã định nghĩa; không mở rộng scope. Lấy requested scopes và user/client/resource từ transaction phía server, không tin form.

**Tình huống D — User bấm Từ chối.** Client nhận callback `error=access_denied&state=...`. Client có được thử gọi Orders bằng ID token nhận ở lần đăng nhập khác không?

**Giải thích:** Không. ID token phục vụ OIDC RP, không phải access token của Orders; việc từ chối grant mới phải được tôn trọng.

**Tình huống E — OIDC prompt none.** Client gửi `prompt=none` khi cần user consent mới. AS có thể tự cấp để tránh lỗi không?

**Giải thích:** Không. Nếu phải tương tác mà prompt không cho phép UI, OP trả lỗi thích hợp như `consent_required`. Không dùng no-UI làm bypass.

**Tình huống F — Consent đúng nhưng đơn sai chủ.** Token `aud=orders-api`, `scope=orders:read` được cấp hợp lệ. User-123 yêu cầu order thuộc user-999. Có được trả không?

**Giải thích:** Không, trừ khi có quyền override rõ ràng. RS phải kiểm tra owner/tenant trên bản ghi thật.

**Tình huống G — Rút consent rồi JWT còn hạn.** User thu hồi quyền, nhưng attacker có bearer JWT access token còn 5 phút; RS chỉ xác minh chữ ký/exp. Token có thể vẫn dùng được không?

**Giải thích:** Có thể. Rút grant không tự làm JWT tự xác minh offline hết hạn. Cần TTL và cơ chế RS nhận biết thu hồi phù hợp.

**Tình huống H — App giả tên.** User đăng nhập ở AS thật và chấp thuận một app giả danh. Vì sao vẫn nguy hiểm?

**Giải thích:** AS có thể cấp **token hợp lệ cho Client độc hại** nếu client registration/scope policy yếu hoặc user bị lừa. Chữ ký token và trang đăng nhập thật không thay kiểm tra danh tính Client, giới hạn scope và thông tin consent rõ ràng.

**Tình huống I — Offline access.** Client xin `offline_access` và user đồng ý. Có chắc AS cấp refresh token dùng vô thời hạn không?

**Giải thích:** Không. AS phải tuân thủ OIDC/profile và policy; có thể không cấp refresh token, hoặc giới hạn TTL, rotation, ràng buộc/thu hồi của nó.

**Tình huống J — Consent của tenant khác.** Cùng user dùng Client ở tenant A và tenant B. AS có được dùng lại grant của tenant A trong tenant B?

**Giải thích:** Không tự mặc định. Grant cần gắn đúng ngữ cảnh tổ chức, resource và policy; tenant B có thể có quy định khác. Không dùng consent không phù hợp làm lý do mở quyền.

## Checklist thiết kế User consent

1. **Rõ ràng vai trò:** User/Resource Owner, Client, AS, RS và tenant admin có trách nhiệm riêng.
2. **Xác thực request trước màn hình:** Client registration, redirect URI, grant, resource, scope và session user theo chính sách.
3. **Tách authentication khỏi consent:** login thành công không tự cấp quyền Client; user consent không vượt AS/tenant policy.
4. **Gắn consent với transaction:** client ID, user/tenant, resource, requested scopes, PKCE challenge, thời hạn và CSRF của AS.
5. **Thiết kế UI minh bạch:** danh tính app được kiểm chứng theo trạng thái thực, mô tả scope bằng hành động, quyền nhạy cảm rõ ràng, nút từ chối dễ thấy.
6. **Giới hạn scope thực sự cấp:** không rộng hơn request, client allowance, user entitlement, tenant policy và lựa chọn consent.
7. **Hỗ trợ từ chối an toàn:** `access_denied` + state tại redirect đã xác minh, không tạo grant/token cho quyền bị từ chối.
8. **Bảo vệ Authorization Code + PKCE:** state, issuer/mix-up checks nếu cần, code dùng một lần, redirect binding, S256 verifier tại token endpoint.
9. **Tái sử dụng consent có điều kiện:** đúng user/client/tenant/resource/scope và policy hiện hành; hỏi lại hoặc từ chối khi xin quyền mới.
10. **Phân biệt OIDC:** `prompt=consent`, `prompt=none`, `offline_access` và ID token áp dụng theo OIDC/profile, không biến thành bypass.
11. **Quản lý grant lifecycle:** lưu an toàn, trang ứng dụng đã kết nối, rút quyền, revoke refresh token và thiết kế RS biết access token bị thu hồi.
12. **Thực thi tại RS:** issuer, audience, token type, exp/nbf, scope, trạng thái và object/tenant authorization; sender proof khi bắt buộc.
13. **Chống lạm dụng:** consent phishing, scope injection, open redirect, code injection, CSRF, XSS, lộ token trong log và bearer replay.
14. **Kiểm thử cả đường từ chối:** user deny, scope mới, admin block, prompt no-UI, callback sai, grant cũ, token bị thu hồi và tenant chéo.

## Ghi nhớ

**User consent trong Authorization Code** là quyết định chấp thuận có **ngữ cảnh** cho một Client truy cập resource theo scope cụ thể; nó không phải dấu hiệu user đã đăng nhập hay giấy phép bỏ qua policy. **Authorization Server** phải xác minh request, cho user biết rõ quyền đang được hỏi, ghi quyết định gắn đúng transaction và phát **authorization code** theo grant thực sự được chấp thuận. Client đổi code bằng **PKCE** (và client authentication nếu phù hợp), nhận access token đúng audience/scope; **Resource Server** vẫn xác minh token và quyền trên từng dữ liệu. Consent đã lưu có thể được tái sử dụng **chỉ khi còn phù hợp**; quyền mới cần quyết định mới; rút consent có thể chặn refresh/cấp token mới nhưng **không tự vô hiệu hóa tức thời mọi JWT đã phát hành**. Thiết kế đúng phải phối hợp bảo vệ UI, client registration, code exchange, token storage, thu hồi và chống token bị đánh cắp/phát lại.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0 — Consent, prompt and offline_access](https://openid.net/specs/openid-connect-core-1_0.html)
- [OWASP — OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
