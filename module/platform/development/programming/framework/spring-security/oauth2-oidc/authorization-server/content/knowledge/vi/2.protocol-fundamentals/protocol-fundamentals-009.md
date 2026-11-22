# Vòng đời authorization và mối liên hệ giữa token, consent, session

## 1. Vì sao phải hiểu ba khái niệm này cùng nhau?

Trong hệ thống OAuth 2.0/OpenID Connect (OIDC) xây dựng bằng **Spring Security** và **Spring Authorization Server** trên Spring Boot, một người dùng có thể đang đăng nhập, đã từng đồng ý cấp quyền cho một ứng dụng và sở hữu các token còn hiệu lực. Ba điều này liên quan nhưng **không đồng nghĩa**.

Hãy hình dung ứng dụng quản lý đơn hàng:

- Người dùng **Lan** mở ứng dụng web, được chuyển đến Authorization Server (AS) để đăng nhập.
- AS hỏi Lan có cho ứng dụng `orders-web` đọc danh sách đơn hàng (scope `orders.read`) hay không. Lan chọn đồng ý.
- AS phát hành authorization code, sau đó client đổi code lấy access token, có thể kèm refresh token và ID token khi sử dụng OIDC.
- Lan đăng xuất khỏi trang đăng nhập của AS nhưng access token vừa phát hành có thể vẫn dùng để gọi Orders API cho tới khi hết hạn hoặc bị vô hiệu hóa theo cơ chế triển khai.
- Lan đăng nhập lại: AS có thể nhận ra **consent đã lưu** và không cần hỏi lại cùng phạm vi, dù đây là một **login session mới**.

Nếu gộp session, consent và token vào một khái niệm, ta dễ mắc lỗi: cho rằng logout luôn thu hồi token, xóa consent sẽ tự chặn mọi access token cũ, hoặc có access token là người dùng đang có phiên trình duyệt hợp lệ.

Sau bài này, bạn sẽ:

1. Giải thích vòng đời của một **authorization grant** từ yêu cầu cấp quyền tới hết hạn/thu hồi.
2. Phân biệt **authentication session**, **authorization consent**, **OAuth2Authorization** và các token.
3. Mô tả điều gì thực sự xảy ra khi **đăng xuất**, **hết phiên**, **refresh token**, **thu hồi token** hoặc **rút consent**.
4. Ánh xạ các trạng thái này vào Spring Authorization Server và Spring Security.
5. Thiết kế lưu trữ, thời hạn, kiểm thử và giám sát đúng cho các hệ thống Spring Boot nhiều instance.

## 2. Bức tranh tổng thể: bốn lớp trạng thái

Một luồng cấp quyền qua trình duyệt thường đi qua bốn lớp:

| Lớp trạng thái | Câu hỏi nó trả lời | Chủ thể/địa điểm điển hình | Dữ liệu lưu |
|---|---|---|---|
| **Authentication session** (phiên đăng nhập) | “Trình duyệt này đã xác thực với ai, phiên còn hợp lệ không?” | AS/OP và/hoặc ứng dụng client | SecurityContext, cookie, HTTP session hoặc cơ chế phiên tương đương |
| **Authorization consent** (sự đồng ý cấp quyền) | “Người dùng đã đồng ý cho client này những quyền nào?” | AS/OP | Client, người dùng, các authority/scope được chấp thuận |
| **Authorization grant / OAuth2Authorization** | “Yêu cầu ủy quyền nào đã được xử lý và có những thông tin/token nào gắn với nó?” | AS | Client, principal, grant type, authorized scopes, token, metadata |
| **Issued tokens** (token đã phát hành) | “Bằng chứng nào cho phép client thực hiện bước tiếp theo?” | AS phát hành; client nắm giữ; RP/RS kiểm tra | Authorization code, access token, refresh token, ID token nếu OIDC |

Trong Spring Authorization Server, `OAuth2Authorization` là mô hình lưu trạng thái của **một authorization**, còn `OAuth2AuthorizationConsent` là mô hình **consent**. Phiên đăng nhập người dùng thường thuộc cơ chế xác thực/web session của **Spring Security**, không nằm trong cùng một bản ghi bắt buộc.

```mermaid
flowchart TB
    U["Người dùng"] -->|"Đăng nhập"| S["Phiên xác thực tại AS<br/>Spring Security / HttpSession"]
    U -->|"Đồng ý cấp quyền"| C["Consent đã lưu<br/>OAuth2AuthorizationConsentService"]
    S -->|"Xác định chủ thể khi /authorize"| D["Quyết định cấp authorization"]
    C -->|"Quyền đã chấp thuận"| D
    D --> A["Authorization record<br/>OAuth2AuthorizationService"]
    A --> T["Authorization code / Access token<br/>Refresh token / ID token nếu có"]
    T --> CL["Client / Relying Party"]
    CL -->|"Access token"| API["Resource Server / API"]
    API -->|"Kiểm tra token và quyền"| CL
```

Sơ đồ thể hiện **quan hệ nhân quả**, không hàm ý rằng bốn lớp có cùng thời hạn hay cùng cơ chế xóa. Một authorization record có thể chứa nhiều thông tin token; một người dùng có thể có nhiều authorization cho nhiều client hoặc nhiều lượt cấp quyền; một session trình duyệt có thể được dùng để xử lý nhiều authorization request.

### 2.1. “Authorization” có nhiều nghĩa trong tài liệu

Trong OAuth, *authorization* có thể chỉ **quá trình** cho phép một client truy cập tài nguyên, *authorization grant* là cách biểu diễn quyền đã được cấp (ví dụ authorization code), còn `OAuth2Authorization` là tên **đối tượng trạng thái** trong Spring Authorization Server. Từ *consent* thường chỉ quyết định chấp thuận một số quyền khi có người dùng tham gia.

Không nên suy ra rằng mọi authorization đều phải có màn hình consent: **Client Credentials Grant** có thể cấp access token cho chính dịch vụ gọi API mà không có người dùng cuối hoặc phiên trình duyệt.

## 3. Vòng đời Authorization Code + PKCE + OIDC

Xét mô hình:

- **Client/Relying Party:** ứng dụng backend-for-frontend (BFF) `orders-web`, giữ token ở phía máy chủ.
- **Authorization Server/OpenID Provider:** `https://auth.example.com`.
- **Resource Server:** `https://api.example.com`, cung cấp Orders API.
- **Người dùng:** Lan.
- **Scopes:** `openid`, `profile`, `orders.read`.
- **Luồng:** Authorization Code + PKCE; OIDC được kích hoạt khi yêu cầu chứa `openid`.

```mermaid
sequenceDiagram
    actor U as Lan
    participant B as Trình duyệt
    participant C as Client / RP
    participant AS as Authorization Server / OP
    participant CS as Consent Service
    participant AZ as Authorization Service
    participant API as Orders API / RS

    U->>B: Chọn Đăng nhập
    B->>C: Yêu cầu đăng nhập
    C->>C: Tạo state, PKCE verifier/challenge, nonce
    C-->>B: Redirect đến /oauth2/authorize
    B->>AS: Authorization request
    AS->>AS: Kiểm tra client, redirect URI, scope, phiên
    opt Chưa có phiên đăng nhập tại AS
        AS-->>B: Hiển thị trang đăng nhập
        U->>B: Đăng nhập
        B->>AS: Gửi thông tin xác thực
        AS->>AS: Tạo phiên đăng nhập
    end
    AS->>CS: Kiểm tra consent cho client + Lan
    opt Cần consent mới hoặc scope bổ sung
        AS-->>B: Hiển thị quyền yêu cầu
        U->>B: Chấp thuận quyền
        B->>AS: Gửi quyết định consent
        AS->>CS: Lưu phạm vi được chấp thuận
    end
    AS->>AZ: Lưu authorization chứa code ngắn hạn
    AS-->>B: Redirect chứa code và state
    B->>C: Chuyển code đến callback
    C->>C: Kiểm tra state
    C->>AS: POST /oauth2/token (code + code_verifier)
    AS->>AZ: Xác minh code, client, PKCE; cập nhật authorization
    AS-->>C: Access token, ID token, tùy chọn refresh token
    C->>C: Xác minh ID token và tạo phiên ứng dụng
    C->>API: Authorization: Bearer ACCESS_TOKEN
    API->>API: Kiểm tra token, scope và quyền dữ liệu
    API-->>C: Trả dữ liệu được phép
```

Các bước có ý nghĩa khác nhau đối với session, consent và token.

### 3.1. Bước 0 — đăng ký client và chính sách cấp quyền

Trước khi có authorization request, AS cần biết client nào được phép tham gia: `client_id`, hình thức xác thực client, grant type, redirect URI, scope, yêu cầu PKCE, có bắt buộc consent hay không và thời hạn token.

Trong Spring Authorization Server, đây là trách nhiệm của `RegisteredClientRepository` và các thuộc tính `RegisteredClient`. **Đăng ký client là cấu hình tin cậy**, không phải việc người dùng đã đồng ý cấp quyền hoặc đã đăng nhập.

### 3.2. Bước 1 — nhận Authorization Request

Client chuyển trình duyệt tới Authorization Endpoint:

```http
GET /oauth2/authorize?response_type=code&client_id=orders-web
    &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Forders-web
    &scope=openid%20profile%20orders.read
    &state=RANDOM_STATE
    &nonce=RANDOM_NONCE
    &code_challenge=BASE64URL_SHA256_VERIFIER
    &code_challenge_method=S256
```

Đây là ví dụ được ngắt dòng để dễ đọc; URL thực tế cần encode hợp lệ và truyền trên HTTPS. AS kiểm tra client, redirect URI, response type, phạm vi và chính sách. Client giữ `state`, `nonce` cùng `code_verifier` trong ngữ cảnh yêu cầu ban đầu.

**Chưa có access token** chỉ vì AS nhận được yêu cầu. Yêu cầu có thể bị từ chối ngay khi client hoặc redirect URI sai.

### 3.3. Bước 2 — xác thực người dùng và phiên tại AS

Nếu trình duyệt chưa có phiên hợp lệ với AS, Spring Security yêu cầu đăng nhập. Sau khi xác thực thành công, một `Authentication`/`SecurityContext` được thiết lập; trong ứng dụng servlet dùng session, ngữ cảnh này thường gắn với HTTP session qua cookie của AS.

Nếu phiên tại AS **đã hợp lệ**, AS có thể tiếp tục kiểm tra yêu cầu cấp quyền mà không cần hỏi lại mật khẩu, tùy các ràng buộc OIDC như `prompt=login`, `max_age` và chính sách xác thực.

Điểm phân biệt:

- **Đăng nhập** chứng minh người dùng là ai trong phiên tại AS.
- **Consent** chứng minh người dùng đã chấp thuận một số quyền cho client, khi chính sách yêu cầu.
- **Token** là kết quả của bước phát hành sau khi yêu cầu cấp quyền hợp lệ.

Phiên đăng nhập ở AS cũng khác **phiên người dùng tại ứng dụng client**. Trong OIDC login, RP thường tạo phiên riêng sau khi kiểm tra ID token; xóa một phiên chưa chắc xóa phiên còn lại.

### 3.4. Bước 3 — kiểm tra và ghi nhận consent

AS xác định các scope client yêu cầu và những quyền người dùng đã chấp thuận trước đó. Nếu client yêu cầu consent và chưa có đủ quyền được lưu, người dùng được hỏi chấp thuận hoặc từ chối.

- **Chấp thuận:** các authority/scope tương ứng được ghi qua `OAuth2AuthorizationConsentService`. AS có thể tiếp tục cấp authorization.
- **Từ chối:** luồng không được cấp các quyền bị từ chối; khi yêu cầu không thể tiếp tục, AS trả lỗi như `access_denied` theo quy tắc giao thức.
- **Đã chấp thuận đủ scope:** với chính sách thông thường, AS có thể bỏ qua màn hình consent khi thực hiện yêu cầu tương đương, nhưng các tham số như `prompt=consent`, chính sách provider và cấu hình UX có thể khiến cần hỏi lại.
- **Xin thêm scope:** consent cũ cho `orders.read` không tự cho phép thêm `orders.write`. AS phải đánh giá yêu cầu mới theo chính sách cấp quyền.

Consent không phải cơ chế bảo đảm client có quyền vĩnh viễn. AS vẫn có thể từ chối quyền tại thời điểm phát hành, và Resource Server có trách nhiệm kiểm tra quyền nghiệp vụ ở thời điểm sử dụng.

### 3.5. Bước 4 — phát hành authorization code

Sau khi yêu cầu hợp lệ, AS tạo **authorization code** ngắn hạn, gắn với client, redirect URI và PKCE challenge. Spring Authorization Server lưu trạng thái liên quan vào `OAuth2AuthorizationService`.

Code là bằng chứng tạm thời để client đổi lấy token; nó **không phải access token để gọi API**. Client nhận code qua redirect và phải kiểm tra `state`. Code có thời hạn ngắn và chỉ được đổi thành công một lần.

Tại thời điểm này:

| Trạng thái | Tình hình |
|---|---|
| Phiên tại AS | Thường vẫn hoạt động nếu đăng nhập qua trình duyệt |
| Consent | Có thể đã được lưu, tùy chính sách |
| Authorization | Có bản ghi liên quan đến code và ngữ cảnh đã cấp |
| Access/refresh/ID token | Chưa được trao cho client ở bước đổi code |

### 3.6. Bước 5 — đổi code thành token

Client gửi yêu cầu tới Token Endpoint qua TLS:

```http
POST /oauth2/token
Authorization: Basic BASE64_ENCODED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=AUTHORIZATION_CODE&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Forders-web&code_verifier=ORIGINAL_RANDOM_VERIFIER
```

Ví dụ dùng **confidential client** với `client_secret_basic`. Public client không gửi client secret; quy tắc xác thực/nhận diện client tại Token Endpoint phải theo client đã đăng ký. PKCE verifier được kiểm tra với challenge đã lưu; code hết hạn, code đã dùng, redirect URI không khớp hoặc xác thực client thất bại phải bị từ chối.

Phản hồi ví dụ khi có OIDC:

```json
{
  "token_type": "Bearer",
  "access_token": "ACCESS_TOKEN_VALUE",
  "expires_in": 600,
  "refresh_token": "REFRESH_TOKEN_VALUE",
  "scope": "openid profile orders.read",
  "id_token": "SIGNED_ID_TOKEN_JWT"
}
```

**Không phải mọi grant đều tạo đủ các token trên.** Authorization Code Flow thông thường không có `id_token` nếu không phải yêu cầu OIDC; việc có refresh token phụ thuộc grant, client và chính sách. Client Credentials Grant không có end-user ID token. Trong OIDC, RP phải kiểm tra ID token để thiết lập ngữ cảnh đăng nhập; ID token không thay access token để gọi Orders API.

Spring Authorization Server cập nhật `OAuth2Authorization` với token và metadata tương ứng. Authorization code đã tiêu thụ không được sử dụng lại, dù dữ liệu lịch sử liên quan có thể còn trong bản ghi phục vụ theo dõi/kiểm tra trạng thái.

### 3.7. Bước 6 — sử dụng access token tại API

Client gửi access token đến Resource Server:

```http
GET /orders
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
```

Orders API kiểm tra token theo cơ chế đã cấu hình (ví dụ JWT signature/claims hoặc opaque token introspection), sau đó xác thực scope như `orders.read` và quyền trên từng đơn hàng. **Consent và session ở AS không được kiểm tra trực tiếp tại mỗi request API**, trừ khi hệ thống cố ý thiết kế thêm quy trình kiểm tra theo thời gian thực.

Một access token có thể hợp lệ ngay cả khi người dùng đã đóng trình duyệt, hết login session tại AS hoặc đăng xuất khỏi ứng dụng client.

### 3.8. Bước 7 — gia hạn bằng refresh token

Khi access token hết hạn, client có refresh token hợp lệ có thể yêu cầu token mới mà **không cần mở lại trang đăng nhập**:

```http
POST /oauth2/token
Authorization: Basic BASE64_ENCODED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=REFRESH_TOKEN_VALUE
```

AS xác minh client, refresh token, thời hạn, trạng thái thu hồi và chính sách. Nếu được phép, AS phát hành access token mới; có thể phát hành refresh token mới khi bật cơ chế rotation. Token được refresh **không có nghĩa là phiên đăng nhập trình duyệt tại AS đã được gia hạn**.

Đặc biệt:

- **Access token hết hạn** không tự khiến refresh token hết hạn.
- **Refresh token hết hạn hoặc bị thu hồi** không đương nhiên xóa login session tại AS.
- **Refresh token rotation** giảm thời gian hữu dụng của token cũ. Nó **không tự bảo đảm** có hệ thống phát hiện replay/tái sử dụng token theo cả chuỗi token; muốn có chính sách *refresh token family* và cảnh báo đánh cắp phải xác minh khả năng của bản triển khai và bổ sung cơ chế phù hợp.
- Không nên lưu refresh token trong browser storage khi kiến trúc cho phép giữ token an toàn ở backend; các public client cần được xử lý theo chính sách và hỗ trợ thực tế của Authorization Server.

### 3.9. Bước 8 — hết hạn, thu hồi và kết thúc quyền truy cập

Một authorization không nhất thiết “kết thúc” bằng một hành động duy nhất. Những sự kiện khác nhau tác động vào những lớp khác nhau: authorization code hết hạn; access token hết hạn; refresh token bị thu hồi; consent bị rút; phiên đăng nhập bị xóa; tài khoản bị khóa; hoặc chính sách quyền thay đổi.

Muốn vô hiệu hóa truy cập hiệu quả, hệ thống phải xác định **token nào còn hiệu lực ở đâu** và Resource Server có nhận được quyết định thu hồi kịp thời hay không.

## 4. So sánh chi tiết: session, consent, authorization và token

| Thuộc tính | Session tại AS | Consent | OAuth2Authorization | Token |
|---|---|---|---|---|
| Đơn vị gắn kết | Trình duyệt/thiết bị hoặc phiên của chủ thể | Người dùng + registered client | Một lần/ngữ cảnh cấp authorization | Token và đối tượng nhận token |
| Điều kiện tạo | Xác thực thành công theo cơ chế AS | Chấp thuận quyền khi chính sách yêu cầu | Luồng cấp authorization được xử lý | Grant phù hợp tại endpoint liên quan |
| Mục đích | Nhớ trạng thái xác thực của trình duyệt | Nhớ quyền người dùng đã đồng ý cho client | Quản lý trạng thái grant, scopes, token và metadata | Cho phép đổi code, truy cập API, refresh hoặc xác thực OIDC |
| Lưu trữ Spring | Spring Security / HTTP session, tùy kiến trúc | `OAuth2AuthorizationConsentService` | `OAuth2AuthorizationService` | Thường nằm trong bản ghi authorization; client cũng giữ token được cấp |
| Có thể tồn tại sau logout? | Phiên bị logout sẽ hết hiệu lực theo cơ chế logout | **Có** | **Có** | **Có thể** |
| Có thể tồn tại sau khi consent bị rút? | **Có** | Bản ghi bị thay đổi/xóa | **Có thể** | **Có thể**, tùy chính sách thu hồi phối hợp |
| Luôn cần có người dùng cuối? | Có nếu là phiên người dùng | Có cho consent của người dùng | **Không**: có thể là Client Credentials | **Không**: access token có thể đại diện client |
| Có dùng làm credential để gọi API? | Không mặc nhiên | Không | Không gửi cả bản ghi | **Access token** được dùng cho API theo thiết kế |

Lưu ý: session trong bảng là **login session tại AS**, không phải **session của RP**. RP có thể tạo cookie phiên của chính nó sau một lần đăng nhập OIDC; API stateless thường không duy trì session người dùng theo từng access token.

### 4.1. Những loại token chính và tuổi thọ

| Loại | Dùng ở đâu? | Có thể tái sử dụng? | Quy tắc nổi bật |
|---|---|---|---|
| **Authorization code** | Client gửi tới Token Endpoint | **Không**, chỉ đổi một lần | Rất ngắn hạn, ràng buộc client/redirect URI/PKCE |
| **Access token** | Resource Server | Có, khi còn hiệu lực và đúng audience/scope | Có thể là JWT hoặc opaque, luôn cần bảo vệ như credential |
| **Refresh token** | Client gửi tới Token Endpoint | Tùy chính sách reuse/rotation | Dài hạn hơn, cần bảo vệ chặt, bị thu hồi/hết hạn độc lập |
| **ID token (OIDC)** | OIDC RP xác minh kết quả xác thực | Không dùng như API bearer token | JWT chứa thông tin xác thực, cần kiểm tra chữ ký/issuer/audience/thời gian/nonce khi áp dụng |

Trong một hệ thống có hàng nghìn token, không nên dùng `sub` của ID token hoặc `principalName` làm khóa duy nhất để xóa “mọi trạng thái đăng nhập”; chúng đại diện các tầng khác nhau. Mỗi authorization cần được truy vấn, vô hiệu hóa hoặc kiểm tra theo dữ liệu thực của nó.

## 5. Một trục thời gian: khi nào trạng thái nào còn sống?

Giả sử chính sách minh họa là:

- Login session tại AS: tối đa **30 phút không hoạt động**.
- Authorization code: **3 phút**.
- Access token: **10 phút**.
- Refresh token: **7 ngày**.
- Consent cho `orders.read`: được lưu cho đến khi bị thu hồi, thay đổi hoặc hết hiệu lực theo chính sách.

| Thời điểm giả định | Sự kiện | Hệ quả |
|---|---|---|
| 08:00 | Lan đăng nhập AS | Bắt đầu phiên trình duyệt tại AS |
| 08:02 | Lan consent `orders.read` | Bản ghi consent được lưu |
| 08:02:00 | AS tạo code | Code có hạn đến khoảng 08:05 |
| 08:02:10 | Client đổi code thành công | Code không dùng lại được; access token hết hạn khoảng 08:12:10 |
| 08:12:10 | Access token đầu tiên hết hạn | Client có thể dùng refresh token còn hợp lệ để xin access token mới |
| 08:30 | Phiên tại AS không hoạt động đủ lâu và hết hạn | Lần `/authorize` sau có thể yêu cầu đăng nhập lại |
| Ngày thứ 2 | Client dùng refresh token còn hiệu lực | Có thể nhận access token mới dù không có phiên trình duyệt tại AS |
| Ngày thứ 7 hoặc theo chính sách | Refresh token hết hạn | Client cần grant mới nếu không có cơ chế cấp quyền khác |

Đây là **ví dụ thời hạn tự chọn**, không phải mặc định chung của Spring Authorization Server. Từng cấu hình TTL, session timeout, refresh token rotation và consent retention phải do hệ thống xác định.

**Điểm mấu chốt:** “Người dùng không còn login session” và “API phải từ chối mọi access token của người dùng” là **hai mệnh đề riêng**. Để mệnh đề thứ hai đúng ngay lập tức, cần cơ chế vô hiệu hóa token và thông báo/tra cứu phù hợp ở Resource Server.

## 6. Mô hình dữ liệu trong Spring Authorization Server

Spring Authorization Server cung cấp các abstraction quan trọng:

### 6.1. `RegisteredClientRepository` — ai được phép yêu cầu?

Lưu cấu hình của client: `clientId`, xác thực client, grant type, redirect URI, scopes, `ClientSettings` và `TokenSettings`. Ví dụ `requireAuthorizationConsent(true)` yêu cầu bước consent phù hợp, trong khi `requireProofKey(true)` yêu cầu PKCE cho Authorization Code Grant của client.

Đừng nhầm **các scope được đăng ký cho client** với **các scope đã được người dùng chấp thuận** hoặc **các scope thực sự được phát hành cho từng access token**. Ba tập hợp này có thể khác nhau.

### 6.2. `OAuth2AuthorizationConsentService` — người dùng đã đồng ý những gì?

`OAuth2AuthorizationConsent` gắn với **registered client ID** và **principal name**, có một tập `GrantedAuthority` biểu diễn quyền đã chấp thuận; nhiều tích hợp Spring sử dụng authority dạng `SCOPE_orders.read`.

Các thao tác điển hình:

- `findById(registeredClientId, principalName)` — tìm consent.
- `save(authorizationConsent)` — lưu/đổi consent.
- `remove(authorizationConsent)` — xóa consent.

Xóa consent khiến lần xin cấp quyền tiếp theo phải đánh giá lại theo chính sách. **Xóa consent không đồng nghĩa tự tìm và thu hồi mọi access/refresh token phát hành trước đó.** Nếu sản phẩm có chức năng “ngắt kết nối ứng dụng”, nghiệp vụ nên phối hợp xóa consent và vô hiệu hóa authorization/token liên quan.

### 6.3. `OAuth2AuthorizationService` — authorization và token đang ở trạng thái nào?

`OAuth2Authorization` có thể lưu những dữ liệu như:

- `registeredClientId`, `principalName`, `authorizationGrantType`;
- `authorizedScopes` đã được cấp trong authorization cụ thể;
- attributes/metadata gắn với grant và quá trình xác thực;
- authorization code, access token, refresh token và OIDC ID token nếu tương ứng;
- trạng thái từng token: thời điểm phát hành, hết hạn, metadata invalidation.

Các API chính của `OAuth2AuthorizationService`:

```java
// Minh họa chữ ký API, không phải toàn bộ service triển khai.
void save(OAuth2Authorization authorization);
void remove(OAuth2Authorization authorization);
OAuth2Authorization findById(String id);
OAuth2Authorization findByToken(String token, OAuth2TokenType tokenType);
```

`findByToken` hỗ trợ tra cứu token trong storage thích hợp, chẳng hạn khi xử lý Token Endpoint, Revocation/Introspection. Việc vô hiệu hóa token theo đúng giao thức có thể cần **cập nhật metadata/trạng thái trong authorization** thay vì chỉ xóa một dòng dữ liệu tùy tiện. Tránh tự viết logic xóa DB trực tiếp làm sai invariant hoặc phá luồng refresh/revocation.

Không được giả định có **một** `OAuth2Authorization` duy nhất cho mỗi principal. Cùng một người dùng có thể cấp nhiều lần cho cùng client hoặc nhiều client; Client Credentials cũng có thể tạo authorization không có user session.

### 6.4. `SecurityContext` và HTTP session — trạng thái xác thực ở lớp web

Phiên xác thực của Spring Security servlet có thể dùng `SecurityContext` gắn với session, cookie `JSESSIONID` hoặc tên cookie cấu hình riêng. Nếu có nhiều instance, cần chiến lược chia sẻ phiên hoặc bảo đảm luồng tương thích; **Spring Session** là một lựa chọn để quản lý session qua kho lưu trữ chung.

Lưu trữ `OAuth2AuthorizationService` bằng JDBC không tự biến HTTP session thành session dùng chung, và lưu session bằng Spring Session cũng không tự biến consent/token thành dữ liệu bền vững. Cần cấu hình **cả hai nhu cầu lưu trữ** theo mục đích của chúng.

### 6.5. Cách tổ chức persistence

| Thành phần | Dành cho dev/test đơn giản | Đề xuất cho ứng dụng vận hành nhiều instance |
|---|---|---|
| Registered client | `InMemoryRegisteredClientRepository` | Kho cấu hình bền vững như JDBC hoặc giải pháp phù hợp |
| Authorization/token state | `InMemoryOAuth2AuthorizationService` | `JdbcOAuth2AuthorizationService` hoặc triển khai bền vững |
| Consent | `InMemoryOAuth2AuthorizationConsentService` | `JdbcOAuth2AuthorizationConsentService` hoặc triển khai bền vững |
| Phiên đăng nhập AS | HttpSession tại một instance | Session store dùng chung theo chính sách kiến trúc; có thể dùng Spring Session |
| Khóa ký token | JWK cấu hình cục bộ phục vụ demo | Quản lý khóa an toàn, đồng bộ giữa instance, có kế hoạch rotate |

In-memory rất tiện để học, nhưng restart có thể làm mất consent/refresh token state hoặc session; trong môi trường có nhiều instance, lưu state phân tán thiếu nhất quán có thể gây lỗi `invalid_grant` bất thường hoặc yêu cầu login liên tục.

## 7. Ví dụ cấu hình chính sách authorization, consent và token

Giả sử `orders-web` là **confidential BFF**, giữ client secret và token ở backend. Đoạn Java dưới đây tập trung vào `RegisteredClient`; repository, key material, login SecurityFilterChain và cấu hình OIDC còn phải được thiết lập riêng:

```java
RegisteredClient createOrdersWebClient(
        String clientSecretFromSecureConfiguration,
        PasswordEncoder passwordEncoder) {

    return RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("orders-web")
        .clientSecret(passwordEncoder.encode(clientSecretFromSecureConfiguration))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://app.example.com/login/oauth2/code/orders-web")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
            .requireProofKey(true)
            .requireAuthorizationConsent(true)
            .build())
        .tokenSettings(TokenSettings.builder()
            .authorizationCodeTimeToLive(Duration.ofMinutes(3))
            .accessTokenTimeToLive(Duration.ofMinutes(10))
            .refreshTokenTimeToLive(Duration.ofDays(7))
            .reuseRefreshTokens(false)
            .build())
        .build();
}
```

Ý nghĩa:

1. `requireProofKey(true)` buộc client cung cấp và chứng minh PKCE verifier.
2. `requireAuthorizationConsent(true)` yêu cầu xử lý sự đồng ý cho phạm vi client đề nghị theo chính sách.
3. `authorizationCodeTimeToLive`, `accessTokenTimeToLive` và `refreshTokenTimeToLive` là ba đồng hồ khác nhau.
4. `reuseRefreshTokens(false)` hướng tới phát hành refresh token mới khi refresh; phải kiểm thử chính xác token cũ bị xử lý thế nào trên phiên bản đang dùng.
5. Client secret phải lấy từ cơ chế quản lý bí mật an toàn; không ghi secret rõ trong source code hay đưa vào browser.

Ví dụ cấu hình persistence bằng JDBC:

```java
@Bean
OAuth2AuthorizationService authorizationService(
        JdbcOperations jdbcOperations,
        RegisteredClientRepository registeredClientRepository) {

    return new JdbcOAuth2AuthorizationService(
        jdbcOperations, registeredClientRepository);
}

@Bean
OAuth2AuthorizationConsentService authorizationConsentService(
        JdbcOperations jdbcOperations,
        RegisteredClientRepository registeredClientRepository) {

    return new JdbcOAuth2AuthorizationConsentService(
        jdbcOperations, registeredClientRepository);
}
```

Các snippet giả định import, bean `JdbcOperations` và `RegisteredClientRepository` đã có. **Database schema phải tương thích với phiên bản Spring Authorization Server**, có migration rõ ràng, bảo vệ dữ liệu nhạy cảm và cơ chế backup/cleanup. Đây là phần cấu hình state, không phải toàn bộ Authorization Server chạy production.

### 7.1. Đồng bộ thời hạn token với thời hạn phiên

Không có yêu cầu phổ quát rằng `accessTokenTimeToLive` phải bằng HTTP session timeout. Chọn thời hạn theo threat model và UX:

- API quan trọng có thể cần access token ngắn và kiểm tra quyền thường xuyên.
- Refresh token dài cần khả năng thu hồi, ràng buộc client và lưu trữ bảo mật.
- Phiên trình duyệt cần chính sách inactivity, absolute timeout, session fixation protection và cookie an toàn.
- Consent retention cần đáp ứng quy tắc sản phẩm: quyền nào được lưu, người dùng tự quản lý ở đâu và khi nào phải hỏi lại.

Khi thay đổi TTL, token **đã phát hành** thường mang thời điểm hết hạn được quyết định tại lúc phát hành; thay đổi policy mới không mặc nhiên viết lại tất cả token cũ. Nếu cần cắt hiệu lực ngay, phải có cơ chế thu hồi phù hợp.

## 8. Logout, revocation, xóa consent: hiệu ứng thực tế

Đây là phần thường gây lỗi vận hành nghiêm trọng nhất.

| Người dùng hoặc hệ thống thực hiện | Session tại AS | Session tại RP | Consent | Token đã phát hành |
|---|---|---|---|---|
| Logout ở ứng dụng RP | Tùy cơ chế single logout; có thể vẫn còn | Thường bị xóa tại RP | Thường giữ | Có thể vẫn còn hiệu lực |
| Logout ở AS | Session của AS bị chấm dứt | Có thể vẫn còn nếu không có phối hợp logout | Thường giữ | Không mặc nhiên bị thu hồi |
| OIDC RP-Initiated Logout | Kích hoạt luồng logout tại OP nếu hỗ trợ/cấu hình | RP cần xử lý phiên của mình | Thường giữ | Không mặc nhiên thu hồi toàn bộ OAuth token |
| Thu hồi một refresh token qua revocation | Không tự xóa | Không tự xóa | Thường giữ | Refresh token đó không còn dùng được; tác động tới access token liên quan tùy chính sách triển khai |
| Access token hết hạn | Không ảnh hưởng trực tiếp | Không ảnh hưởng trực tiếp | Không ảnh hưởng | Access token đó không được API chấp nhận nữa |
| Người dùng rút consent | Không tự xóa | Không tự xóa | Bản ghi consent được thay đổi/xóa | Token cũ có thể vẫn dùng được nếu không xử lý thu hồi cùng lúc |
| Admin khóa người dùng | Phụ thuộc quy trình khóa phiên | Phụ thuộc tích hợp | Phụ thuộc chính sách | Cần chủ động xử lý vô hiệu hóa nếu muốn hiệu lực ngay |

### 8.1. Vì sao logout không tự thu hồi token?

OAuth Bearer access token là credential độc lập với cookie phiên. Resource Server kiểm tra token theo định dạng và thiết kế:

- **JWT tự xác minh:** API có thể xác minh chữ ký, issuer, audience, thời hạn và claims mà không hỏi lại AS. Nếu JWT chưa hết hạn và API không có cơ chế kiểm tra thu hồi, logout AS **không làm JWT tự mất hiệu lực**.
- **Opaque token + introspection:** API hỏi Authorization Server hoặc dịch vụ liên quan xem token còn `active` không; nếu trạng thái thu hồi đã được cập nhật và introspection không bị cache quá mức, hiệu lực có thể bị cắt sớm.
- **JWT có revocation check riêng:** Có thể dùng denylist, token version, sự kiện thu hồi hoặc kiểm tra trạng thái tại API; phải cân nhắc consistency, cache và hiệu năng.

Do đó, một nút “Đăng xuất khỏi mọi thiết bị” cần quy trình tổng thể: chấm dứt các phiên liên quan, vô hiệu hóa refresh token/authorization có thể cần, quyết định cách chặn access token đang sống, đồng bộ trạng thái giữa các dịch vụ và xử lý cả phiên của RP nếu thiết kế hỗ trợ.

### 8.2. Revocation khác expiration

**Expiration** xảy ra theo thời gian `expiresAt`; **revocation** là quyết định chủ động làm token không còn sử dụng được trước hạn. RFC 7009 định nghĩa Token Revocation Endpoint; Spring Authorization Server có thể cung cấp endpoint thường là `/oauth2/revoke`. Client cần xác thực theo quy tắc endpoint, và hệ thống cần xác định các token liên quan bị tác động ra sao.

Việc revoke refresh token không bảo đảm API JWT tự xác minh sẽ ngừng chấp nhận access token đã phát hành. RFC và cấu hình triển khai có những lựa chọn khác nhau về mức lan truyền revocation giữa token.

### 8.3. Rút consent khác “ngắt truy cập ngay”

Giả sử Lan vào phần “Ứng dụng đã kết nối” và chọn gỡ `orders-web`. Nếu tính năng chỉ gọi `OAuth2AuthorizationConsentService.remove(...)` thì:

1. Consent đã lưu biến mất.
2. Lần xin authorization tương lai có thể cần consent lại.
3. Một access token cũ vẫn có thể hợp lệ.
4. Refresh token cũ vẫn có thể đổi lấy access token mới nếu quy trình refresh không được gắn thêm chính sách ngắt kết nối.

Nếu yêu cầu sản phẩm là **ngắt hoàn toàn quyền truy cập**, nghiệp vụ phải kết hợp quản lý consent và authorization/token. Không nên trình bày UI “đã ngắt truy cập” khi mới xóa consent nhưng token còn sử dụng được.

## 9. Scope, consent và sự thay đổi quyền theo thời gian

Xét ba lần yêu cầu:

| Lượt | Scope yêu cầu | Consent đã lưu trước đó | Quyết định hợp lý |
|---|---|---|---|
| A | `openid orders.read` | Chưa có | Hỏi consent nếu chính sách yêu cầu |
| B | `openid orders.read` | Đã có cùng scopes | Có thể cấp quyền tiếp mà không hỏi lại |
| C | `openid orders.read orders.write` | Mới có `orders.read` | Phải đánh giá và xin chấp thuận phần quyền mới nếu cần |

Chủ thể có thể từ chối `orders.write` nhưng vẫn cho `orders.read` nếu server/client hỗ trợ cấp scope hẹp hơn; client phải đọc các scope thực tế được cấp. **Không suy ra rằng client được tất cả scope từng yêu cầu.**

Cũng cần phân biệt **consent** và **authorization policy**:

- Consent trả lời người dùng có chấp thuận việc chia sẻ quyền hay không.
- Client registration và chính sách AS giới hạn quyền client được yêu cầu/cấp.
- Resource Server tiếp tục áp dụng phân quyền theo tài nguyên, ví dụ người dùng chỉ được xem đơn hàng thuộc tài khoản của mình.

Nếu quyền người dùng bị thu hẹp sau khi token phát hành, claims đã nằm trong JWT có thể bị cũ. Thiết kế cần cân nhắc access token ngắn hạn, kiểm tra quyền động hoặc thu hồi; consent không tự làm mới role/scope của mọi token cũ.

## 10. Ba session khác nhau có thể cùng tồn tại

Khi sử dụng OIDC, chữ “session” cần ghi rõ nó thuộc thành phần nào:

| Phiên | Được tạo khi nào? | Ai duy trì? | Xóa phiên này tác động gì? |
|---|---|---|---|
| **AS login session** | Người dùng xác thực tại Authorization Server | Spring Security của AS/OP | Yêu cầu `/authorize` tiếp theo có thể cần login |
| **RP/application session** | Client xác minh đăng nhập và tạo phiên ứng dụng | Ứng dụng `orders-web` | Người dùng không còn phiên tại RP, nhưng có thể còn SSO tại AS |
| **Resource Server session** (nếu có) | Theo thiết kế API | API | Riêng biệt; API bearer token thông thường có thể stateless |

Ví dụ:

1. Lan logout khỏi `orders-web`; RP xóa session cookie của ứng dụng.
2. Lan nhấn Login lần nữa; AS vẫn có session SSO hợp lệ.
3. AS có thể xác thực Lan mà không hỏi lại mật khẩu, đồng thời tái sử dụng consent được lưu.
4. RP nhận code và token mới rồi tạo **application session mới**.

Nếu muốn logout khiến lần đăng nhập sau phải nhập lại thông tin xác thực, cần có chính sách/luồng OIDC phù hợp (ví dụ yêu cầu tái xác thực), không chỉ gọi logout cục bộ của RP.

## 11. Các mối đe dọa theo vòng đời

| Rủi ro | Giai đoạn | Phòng vệ chính |
|---|---|---|
| Authorization code bị chặn | Redirect/code exchange | Authorization Code + PKCE `S256`, code ngắn hạn, một lần, redirect URI chặt |
| Tấn công CSRF/mix-up ở callback | Authorization response | `state`, kiểm tra issuer khi cần, cấu hình callback đúng |
| ID token bị thay thế hoặc phát lại | OIDC login | Xác minh chữ ký, `iss`, `aud`, `exp`, `nonce` nếu sử dụng, ràng buộc ngữ cảnh yêu cầu |
| Consent giả mạo hoặc ép người dùng đồng ý | Consent UI | Chống CSRF, hiển thị client/scope đáng tin, chống clickjacking, audit sự kiện |
| Session hijacking/fixation | Đăng nhập và duy trì phiên | HTTPS, cookie Secure/HttpOnly/SameSite phù hợp, session fixation protection, timeout |
| Access token bị đánh cắp | Gọi API | TLS, hạn chế log token, token TTL phù hợp, giới hạn audience/scope, cân nhắc sender-constrained token nếu hệ thống hỗ trợ |
| Refresh token bị đánh cắp | Gia hạn token | Lưu bí mật phía server khi có thể, xác thực client, rotation, phát hiện reuse theo thiết kế, khả năng thu hồi |
| JWT còn dùng được sau logout | Sau đăng xuất/thu hồi | Short-lived JWT, introspection hoặc revocation check phù hợp, đồng bộ sự kiện bảo mật |
| Principal bị đổi quyền | Giữa hai lần phát token | Token TTL ngắn, chính sách API động, thu hồi hoặc re-authorization khi cần |
| Dữ liệu token/consent lộ qua DB/log | Persistence/vận hành | Phân quyền DB, mã hóa theo chính sách, che log, backup và rotation keys |

**Không ghi access token, refresh token, authorization code, client secret hoặc cookie phiên vào log ở dạng rõ.** Nếu cần tương quan sự kiện, dùng request ID, authorization ID an toàn và các thuộc tính không phải credential.

### 11.1. Một vài nguyên tắc thiết kế

- Trước khi phát hành code: xác thực client/redirect, đảm bảo người dùng phù hợp, áp dụng consent và PKCE.
- Trước khi phát hành access token: xác minh grant hợp lệ, PKCE/client authentication, scope được phép và chính sách.
- Trước khi cho truy cập API: xác minh đúng **access token dành cho API**, kiểm tra hiệu lực, scope và quyền đối tượng.
- Khi refresh: kiểm tra **refresh token** và client, không nhầm với phiên trình duyệt.
- Khi logout/ngắt kết nối: xác định cần đóng những session nào, thu hồi những authorization/token nào, làm sao API biết quyết định đó.
- Khi vận hành nhiều node: dữ liệu authorization, consent, session và khóa ký phải được quản lý nhất quán theo mô hình triển khai.

## 12. Kiểm thử vòng đời end-to-end

Kiểm thử không nên chỉ dừng ở “đăng nhập thành công và gọi API được”. Các tình huống sau phát hiện sai lệch giữa session, consent và token:

| Ca kiểm thử | Thiết lập/thao tác | Kết quả mong đợi |
|---|---|---|
| Consent lần đầu | Người dùng mới yêu cầu `openid orders.read`, client yêu cầu consent | Hiển thị quyền phù hợp; chỉ phát hành sau khi xử lý consent hợp lệ |
| Consent được tái sử dụng | Đăng nhập lại, yêu cầu cùng scope đã chấp thuận | Theo chính sách, có thể không hỏi consent lại |
| Scope mở rộng | Xin thêm `orders.write` | Consent cũ không tự cấp scope mới |
| Từ chối consent | Chọn từ chối | Không được phát hành authorization cho quyền bị từ chối; client nhận lỗi phù hợp |
| Hết login session | Để session AS hết hạn, giữ token còn hiệu lực | Authorization request mới cần xác thực lại; API có thể vẫn chấp nhận token hợp lệ |
| Đăng xuất RP | Logout cục bộ tại web client | RP session bị xóa; AS session và token tuân theo cơ chế riêng |
| Đăng xuất AS | Logout ở Authorization Server | AS session mất; access token đang sống không mặc nhiên bị API từ chối |
| Code được đổi hai lần | Gửi lại cùng authorization code | Lần đổi thứ hai bị từ chối |
| PKCE sai | Đổi code với `code_verifier` sai | Token Endpoint từ chối, không phát hành token |
| Access token hết hạn | Gọi API bằng token quá `exp` | API từ chối; client có thể refresh nếu hợp lệ |
| Refresh token rotation | Refresh khi `reuseRefreshTokens(false)` | Token mới được phát hành; kiểm tra chính sách vô hiệu hóa token cũ |
| Refresh token bị revoke | Thu hồi refresh token rồi thử lại | Token Endpoint từ chối việc dùng refresh token đã bị thu hồi |
| Consent bị rút | Xóa consent rồi thực hiện authorization request mới | Quyền phải được đánh giá lại; token cũ chỉ bị chặn nếu có cơ chế thu hồi |
| Token sai mục đích | Dùng ID token làm Bearer token tới Orders API | API từ chối |
| Token sai audience/scope | Dùng access token không dành cho API hoặc thiếu `orders.read` | API từ chối |
| Multi-instance | Login/consent ở node A, đổi code ở node B | Hoạt động nhất quán nếu storage và khóa được chia sẻ đúng |

### 12.1. Chú ý phân loại lỗi

- `invalid_request` / lỗi authorization: tham số thiếu, redirect không phù hợp hoặc yêu cầu không hợp lệ.
- `access_denied`: người dùng/AS từ chối cấp quyền.
- `invalid_grant`: authorization code hay refresh token không hợp lệ, hết hạn, đã dùng hoặc bị thu hồi (tùy tình huống).
- `invalid_client`: client authentication thất bại hoặc client không hợp lệ.
- **HTTP 401** tại API: token thiếu/không hợp lệ/hết hạn.
- **HTTP 403** tại API: request đã xác thực nhưng không đủ quyền.

Lỗi hiển thị thực tế còn tùy vị trí, framework và cấu hình. Ghi nhận **ngữ cảnh giao thức** khi chẩn đoán thay vì cho rằng mọi lỗi login đều do session hoặc mọi `401` đều do consent.

## 13. Tình huống vận hành: người dùng chọn “Ngắt kết nối ứng dụng”

Giả sử sản phẩm yêu cầu: “Khi Lan gỡ quyền của `orders-web`, ứng dụng không thể lấy token mới và không thể tiếp tục gọi API bằng credential đã có.”

Một triển khai có trách nhiệm cần:

1. **Xác định người dùng và client** chính xác; kiểm tra người thực hiện có quyền ngắt kết nối.
2. **Tìm và xóa/điều chỉnh consent** tại `OAuth2AuthorizationConsentService`.
3. **Tìm các authorization liên quan** qua cơ chế truy vấn/quản lý dữ liệu phù hợp, không giả định chỉ có một bản ghi.
4. **Vô hiệu hóa refresh token và các token cần thiết** theo API/quy trình được thiết kế, bảo đảm client không thể tiếp tục refresh.
5. **Xử lý access token đang sống**: nếu dùng JWT tự xác minh, chọn thời gian chấp nhận tồn dư có kiểm soát hoặc kiểm tra revocation bổ sung; nếu dùng introspection, đảm bảo API cập nhật trạng thái đúng thời điểm.
6. **Đóng session ứng dụng nếu chính sách yêu cầu**, phối hợp logout RP/OP theo các giao thức thực sự được triển khai.
7. **Ghi audit event và kiểm thử** ở AS, client và API; xác minh lời hứa “đã ngắt kết nối” đúng với hành vi thực tế.

Dữ liệu ở nhiều storage có thể không thể cập nhật cùng một transaction. Với mô hình nhiều dịch vụ, nên thiết kế xử lý idempotent, sự kiện điều phối và phương án retry để tránh trạng thái consent đã xóa nhưng refresh token vẫn còn hiệu lực lâu ngoài ý muốn.

## 14. Những nhầm lẫn thường gặp

**“Người dùng đang đăng nhập nên client đã được cấp mọi quyền.”** Sai. Authentication session chứng minh danh tính tại AS; quyền còn phụ thuộc đăng ký client, consent, scope và authorization policy.

**“Consent được lưu tức là có một access token đang tồn tại.”** Sai. Consent có thể vẫn lưu sau khi tất cả token đã hết hạn, và access token có thể được cấp trong grant không có consent của người dùng cuối.

**“Một OAuth2Authorization tương ứng với đúng một login session.”** Sai. Các bản ghi authorization và session có vòng đời độc lập, số lượng quan hệ không cố định.

**“Logout sẽ làm mọi API ngừng chấp nhận JWT ngay lập tức.”** Sai. JWT tự xác minh thường còn dùng được tới hạn nếu API không kiểm tra trạng thái thu hồi bổ sung.

**“Rút consent là đủ để chặn token cũ.”** Sai. Cần phối hợp xử lý authorization/token nếu sản phẩm yêu cầu ngắt truy cập hiện tại.

**“Refresh token là cách gia hạn login session.”** Sai. Refresh token là credential để xin token mới; nó không mặc định gia hạn session ở AS hoặc RP.

**“Resource Server phải truy vấn consent mỗi lần nhận request.”** Sai. API thường dựa vào access token và chính sách authorization tại API; nếu cần kiểm soát quyền tức thời, phải thiết kế thêm cơ chế phù hợp.

**“Client Credentials luôn có consent và session.”** Sai. Grant này đại diện client, không có đăng nhập/consent của End-User.

## 15. Checklist tư duy khi thiết kế một Authorization Server

Trước khi triển khai, hãy trả lời được các câu hỏi:

1. **Authentication:** Ai được xác thực? Session nào được tạo, ở đâu và kết thúc khi nào?
2. **Consent:** Client có cần người dùng chấp thuận không? Quyền đã chấp thuận lưu bao lâu? Rút quyền qua UI nào?
3. **Authorization:** Grant nào được phép; metadata và token state lưu trong repository nào; có bao nhiêu instance cùng xử lý?
4. **Token:** Access/refresh/ID token dùng đúng mục đích chưa? TTL, audience, scope, key rotation và storage được quản lý thế nào?
5. **Refresh:** Client nào được refresh; có rotation không; cách xử lý token cũ và token bị đánh cắp ra sao?
6. **Logout/revocation:** Đăng xuất RP, đăng xuất OP, ngắt consent và revoke token có tác động cụ thể đến nhau như thế nào?
7. **Resource Server:** API kiểm tra JWT hay introspection? Nếu cần thu hồi tức thời, cơ chế đồng bộ trạng thái là gì?
8. **Kiểm thử/vận hành:** Đã thử hết session nhưng token còn hiệu lực, rút consent nhưng token còn hiệu lực, token bị revoke và request qua nhiều instance chưa?

### Ghi nhớ cốt lõi

**Session** ghi nhớ một trạng thái xác thực tại thành phần cụ thể. **Consent** ghi nhận quyền mà người dùng đã đồng ý cho client, khi giao thức/chính sách yêu cầu. **OAuth2Authorization** quản lý trạng thái một lần cấp authorization, bao gồm các token liên quan. **Token** là credential được sử dụng ở đúng endpoint và đối tượng nhận của nó.

Bốn lớp tương tác trong một luồng Authorization Code + PKCE + OIDC, nhưng **không cùng tuổi thọ và không tự động chấm dứt cùng nhau**. Tách đúng các lớp này là nền tảng để thiết kế, cấu hình, bảo mật, kiểm thử và vận hành Spring Authorization Server đáng tin cậy.

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)
- [Spring Authorization Server Reference](https://docs.spring.io/spring-authorization-server/reference/)
- [Spring Security Reference](https://docs.spring.io/spring-security/reference/)
