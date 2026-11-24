# Refresh token trong OAuth 2.0, OIDC và vòng đời danh tính IAM

> **Chương: OAuth và OIDC.** **Refresh token** là thông tin xác thực được Authorization Server (AS) cấp cho client nhằm xin **access token mới** khi access token trước đó hết hạn hoặc không còn phù hợp. Nó giúp duy trì khả năng sử dụng ứng dụng mà không bắt người dùng đăng nhập lại cho mỗi lần gọi API. Nhưng nếu refresh token bị đánh cắp, kẻ tấn công có thể tiếp tục xin token mới. Vì vậy, trong IAM theo **Joiner–Mover–Leaver**, quản lý refresh token phải gắn với phiên, client, phạm vi quyền, trạng thái danh tính, rotation, phát hiện phát lại, thu hồi và kiểm toán.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **refresh token**, **access token**, **ID token**, phiên đăng nhập tại IdP và phiên cục bộ ở ứng dụng.
2. Giải thích khi nào Authorization Server phát hành refresh token, cách sử dụng **refresh_token grant** và những ràng buộc về client, scope, thời hạn và chính sách.
3. Thiết kế **refresh token rotation**, chống replay, phát hiện reuse, xử lý lỗi đồng thời và sự cố mất phản hồi mạng.
4. Chọn cách lưu giữ và bảo vệ token theo loại client: backend/confidential client, SPA, ứng dụng di động và ứng dụng máy tính.
5. Phân tích tác động của **Joiner–Mover–Leaver**, SSO, SCIM, RBAC/ABAC, thu hồi phiên và quyền truy cập tồn dư.
6. Lập ma trận kiểm thử, kế hoạch đối soát, chỉ số vận hành và bằng chứng kiểm toán cho vòng đời refresh token.

## 1. Refresh token giải quyết vấn đề gì?

Giả sử một nhân viên đăng nhập ứng dụng quản lý công việc lúc 08:00. Ứng dụng nhận access token có thời hạn ngắn để gọi API. Đến khi token hết hạn, người dùng không nhất thiết phải nhập lại mật khẩu và MFA nếu client đang có refresh token hợp lệ và Authorization Server vẫn cho phép sử dụng.

Quy trình phổ biến:

1. Người dùng xác thực tại IdP/Authorization Server theo chính sách.
2. Client nhận access token, và **có thể** nhận refresh token nếu loại client, grant, phạm vi và chính sách cho phép.
3. Client dùng access token để gọi Resource Server.
4. Khi cần, client gửi refresh token tới **token endpoint của Authorization Server**, không gửi nó như credential để gọi API nghiệp vụ.
5. Authorization Server kiểm tra token, client và các điều kiện hiện hành, sau đó có thể cấp access token mới; một số cấu hình đồng thời cấp refresh token mới.
6. Khi refresh token hết hạn, bị thu hồi hoặc không còn được chấp nhận, client phải xử lý lỗi và có thể cần bắt đầu luồng authorization/xác thực lại.

**Điểm quan trọng:** refresh token không trao quyền truy cập trực tiếp cho API. Nó trao khả năng **yêu cầu một token truy cập khác**, do Authorization Server kiểm soát.

### Phân biệt các thành phần

| Thành phần | Được dùng ở đâu? | Mục đích | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| **Access token** | Resource Server/API đúng đối tượng nhận. | Cho phép gọi API theo scope, audience và chính sách. | Có hạn; không tự đại diện cho một phiên đăng nhập vô thời hạn. |
| **Refresh token** | Token endpoint của Authorization Server. | Xin access token mới khi được phép. | Là credential nhạy cảm; không gửi tới API nghiệp vụ hoặc log. |
| **ID token (OIDC)** | Relying Party/Client của OIDC. | Truyền thông tin về kết quả xác thực và chủ thể theo hợp đồng OIDC. | Không dùng tùy ý thay access token; refresh không đồng nghĩa tái xác thực. |
| **IdP/SSO session** | IdP/OpenID Provider. | Duy trì trạng thái đăng nhập tập trung. | Có thể hết hạn độc lập với refresh token. |
| **App session** | Chính ứng dụng RP/SP. | Giữ phiên ứng dụng, thường qua cookie hoặc session store. | Có thể tồn tại sau khi IdP session kết thúc nếu chưa có cơ chế đồng bộ/thu hồi. |

Ví dụ: một app web có phiên cục bộ hợp lệ, refresh token hết hạn và access token vẫn còn hạn vài phút. App có thể sử dụng token hiện tại theo chính sách cho đến khi nó hết hiệu lực, nhưng **không thể suy ra** sẽ lấy được token mới. Ngược lại, việc refresh thành công chưa chứng minh người dùng vừa thực hiện MFA.

## 2. Refresh token xuất hiện trong OAuth 2.0 và OIDC như thế nào?

**OAuth 2.0** là khuôn khổ ủy quyền giữa client, Authorization Server và Resource Server. **OpenID Connect (OIDC)** bổ sung cơ chế xác thực/định danh trên OAuth 2.0. Refresh token là cơ chế của OAuth; OIDC có thể sử dụng nó trong những luồng phù hợp.

### Những vai trò cơ bản

| Vai trò | Trách nhiệm |
| --- | --- |
| **Resource Owner / User** | Chủ thể ủy quyền hoặc tham gia quy trình xác thực, tùy ngữ cảnh. |
| **Client** | Ứng dụng nhận và sử dụng token theo grant đã được cho phép. |
| **Authorization Server (AS)** | Phát hành, kiểm tra và thu hồi access/refresh token theo chính sách. |
| **Resource Server (RS)** | API kiểm tra access token và quyết định truy cập tài nguyên. |
| **OpenID Provider (OP)** | Trong OIDC, là bên hỗ trợ xác thực và phát hành ID token cho RP. |

Một sản phẩm IdP có thể đồng thời đóng vai trò Authorization Server và OpenID Provider, nhưng các khái niệm không đồng nghĩa hoàn toàn.

### Luồng lấy token và làm mới

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as Client
    participant AS as Authorization Server / IdP
    participant API as Resource Server
    U->>C: Mở ứng dụng
    C->>AS: Authorization Code + PKCE (khi dùng)
    AS->>U: Login/MFA nếu cần
    U-->>AS: Hoàn tất
    AS-->>C: Authorization code
    C->>AS: Đổi code theo client binding
    AS-->>C: Access token (+ refresh token nếu được cấp)
    C->>API: Access token
    API-->>C: Kết quả sau kiểm tra quyền
    Note over C,AS: Access token hết hạn hoặc cần làm mới
    C->>AS: grant_type=refresh_token + refresh token
    AS->>AS: Validate client, token, expiry, grant và policy
    AS-->>C: Access token mới (+ refresh token mới nếu rotation)
    C->>API: Access token mới
    API-->>C: Kết quả theo quyền hiện hành
~~~

*Luồng minh họa. Cách client xác thực và cách token bị ràng buộc phụ thuộc loại client, giao thức và chính sách. Refresh token không bắt buộc được cấp trong mọi luồng.*

### Ví dụ yêu cầu đến token endpoint

Ví dụ theo biểu diễn HTTP đơn giản, dùng giá trị đã che; endpoint cụ thể tùy nhà cung cấp:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=REDACTED&client_id=work-app
~~~

Nếu client thuộc loại **confidential**, nó phải sử dụng cơ chế **client authentication** được Authorization Server yêu cầu, ví dụ client secret được bảo vệ, private_key_jwt hoặc mTLS theo cấu hình. Đoạn HTTP trên **không** mô tả đầy đủ phần xác thực client và không phải mẫu phù hợp cho mọi hệ thống.

Phản hồi thành công có thể có dạng:

~~~json
{
  "access_token": "REDACTED_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_token": "REDACTED_NEW_REFRESH_TOKEN",
  "scope": "profile tasks.read"
}
~~~

Khi **rotation** được áp dụng, server phát refresh token mới để thay token đã được sử dụng; client phải bảo vệ và cập nhật token mới theo cơ chế an toàn. Trong những triển khai khác, phản hồi có thể **không có** trường refresh_token mới. Không giả định response luôn chứa ID token, hoặc access token mới luôn có cùng tập quyền với token trước đó.

### OIDC và `offline_access`

Trong OIDC, scope **offline_access** là một tín hiệu yêu cầu truy cập khi người dùng không hiện diện; cách chấp nhận nó phụ thuộc các quy tắc và chính sách của OpenID Provider, gồm các điều kiện về đồng ý/ủy quyền khi áp dụng. **Yêu cầu offline_access không bảo đảm client sẽ được phát refresh token**. Tương tự, nếu có refresh token thì điều đó không đồng nghĩa người dùng được giữ quyền sau ngày nghỉ việc.

Một số client được cấp refresh token không cần cùng một scope hoặc hình thức triển khai OIDC như ví dụ trên, tùy Authorization Server và grant được hỗ trợ. Cần kiểm tra tài liệu và cấu hình của hệ thống cụ thể.

## 3. Vòng đời của một refresh token

Một refresh token có thể trải qua các trạng thái được mô hình hóa nội bộ như:

~~~mermaid
stateDiagram-v2
    [*] --> ISSUED
    ISSUED --> ACTIVE: Client được phép sử dụng
    ACTIVE --> ROTATED: Refresh thành công và phát token mới
    ACTIVE --> EXPIRED: Hết hạn tuyệt đối/không hoạt động
    ACTIVE --> REVOKED: User/admin/policy thu hồi
    ACTIVE --> COMPROMISED: Reuse hoặc tín hiệu lộ token
    ROTATED --> REUSE_DETECTED: Token cũ được trình lại
    REUSE_DETECTED --> FAMILY_REVOKED: Xử lý theo rotation policy
    COMPROMISED --> FAMILY_REVOKED: Đánh giá toàn grant/token family
    ROTATED --> [*]
    EXPIRED --> [*]
    REVOKED --> [*]
    FAMILY_REVOKED --> [*]
~~~

Đây là **mô hình quản trị nội bộ**, không phải tên trạng thái chuẩn bắt buộc của OAuth hoặc một Authorization Server. Hệ thống có thể lưu hash token, grant ID và trạng thái token family thay vì lưu chuỗi token thô.

### Thông tin nên được quản lý

| Thuộc tính | Mục đích |
| --- | --- |
| **Grant/authorization reference** | Biết token thuộc một ủy quyền nào, có thể rút cả grant khi cần. |
| **Client ID và loại client** | Ngăn token được dùng bởi client không hợp lệ. |
| **Subject/identity mapping** | Nối token với đúng người và trạng thái JML. |
| **Issuer, tenant, audience/resource** | Ngăn sử dụng sai nguồn cấp hoặc sai phạm vi tài nguyên. |
| **Scope được phép** | Giới hạn quyền token mới; không mở rộng vượt quyền đã được cấp. |
| **IssuedAt/LastUsedAt/ExpiresAt** | Kiểm tra hiệu lực, idle/absolute lifetime. |
| **Rotation family/generation** | Theo dõi chuỗi token và phát hiện dùng lại token cũ. |
| **Sender-binding reference (nếu có)** | Kiểm chứng token được dùng bởi đúng holder/key/certificate. |
| **Revocation reason/sourceVersion** | Phục vụ Leaver, security incident và audit. |

### Các thời hạn thường gặp

**Access token lifetime**, **refresh token lifetime**, **idle/inactivity expiry**, **absolute expiry** và **IdP session lifetime** có thể khác nhau. Không có một giá trị cố định luôn phù hợp:

- **Access token ngắn hạn** giảm thời gian sử dụng một token bị lộ, nhưng không tự giải quyết việc thu hồi ngay.
- **Refresh token có idle timeout** có thể hết hạn nếu client không sử dụng trong một khoảng thời gian.
- **Refresh token có absolute lifetime** có thể hết hạn dù vẫn được sử dụng; rotation không được mặc nhiên kéo dài vượt giới hạn mà server đã định.
- **IdP session hết hạn** có thể buộc người dùng xác thực lại khi bắt đầu một authorization request mới; refresh token còn hợp lệ có thể vẫn được AS chấp nhận hoặc bị chính sách từ chối tùy hệ thống.
- **EmploymentEndAt/LeaverEffectiveAt** là mốc nghiệp vụ cần được áp chính sách để ngừng quyền, không phụ thuộc riêng vào token TTL.

Nếu muốn khẳng định “đăng xuất khỏi IdP đồng nghĩa refresh token cũng bị thu hồi”, tổ chức phải **triển khai và kiểm thử chính sách đó**, không suy luận chỉ từ chữ logout.

## 4. Refresh token rotation và phát hiện reuse

**Refresh token rotation** là cơ chế mà mỗi lần làm mới hợp lệ, Authorization Server cấp refresh token kế tiếp và làm mất hiệu lực token vừa dùng. Việc trình lại token đã bị thay thế có thể là dấu hiệu token bị sao chép hoặc có vấn đề xử lý đồng thời.

### Vì sao cần rotation?

Giả sử refresh token R1 bị lấy cắp. Nếu R1 vẫn được dùng lặp lại vô thời hạn, kẻ tấn công có thể xin thêm access token trong một khoảng dài mà không cần biết mật khẩu. Với rotation:

1. Client hợp lệ dùng R1.
2. AS phát access token A2 và refresh token R2; đánh dấu R1 đã được dùng/không còn hợp lệ.
3. Nếu R1 được trình lại, AS phát hiện **reuse** và thực hiện phản ứng theo chính sách.
4. Tùy mô hình, AS có thể thu hồi **token family/grant hiện hành** để ngăn kẻ đang giữ token nào đó tiếp tục làm mới.

~~~mermaid
sequenceDiagram
    participant C as Client hợp lệ
    participant AS as Authorization Server
    participant X as Bên giữ bản sao R1
    C->>AS: Refresh(R1)
    AS->>AS: R1 đã dùng, tạo R2
    AS-->>C: Access A2 + Refresh R2
    X->>AS: Refresh(R1) lần nữa
    AS->>AS: Phát hiện reuse R1
    AS-->>X: Từ chối
    AS->>AS: Có thể thu hồi active family/grant theo policy
    Note over C,AS: Client có thể cần đăng nhập/ủy quyền lại
~~~

**Rotation không thể tự xác định ai là người hợp pháp** khi phát hiện token bị dùng lại. AS biết có reuse, nhưng không nhất thiết biết R1 ở tay nạn nhân hay kẻ tấn công tại thời điểm đầu tiên. Vì vậy cần chính sách xử lý sự kiện, giới hạn rủi ro, cảnh báo và trải nghiệm đăng nhập lại phù hợp.

### Reuse do lỗi đồng thời cũng là tình huống có thật

Không phải mọi reuse đều do tấn công:

- Hai request từ cùng một ứng dụng cùng nhận access token hết hạn và đồng thời dùng R1.
- Client gửi refresh, AS đã phát R2 nhưng response bị mất; client thử lại R1.
- Một ứng dụng có nhiều instance dùng chung bản lưu refresh token nhưng không phối hợp khóa.
- Client ghi R2 xuống storage lỗi, sau khi restart lại dùng R1.

Nếu hệ thống bật cơ chế revoke cả family khi thấy R1 được dùng lại, **race condition ở client có thể khiến chính người dùng bị buộc đăng nhập lại**. Đây là giá phải trả cần được tính trong thiết kế; không nên vô hiệu hóa reuse detection để “chữa” lỗi concurrency.

### Thiết kế client an toàn với rotation

1. **Single-flight refresh:** với một user/client/session, chỉ một tác vụ refresh được thực hiện tại một thời điểm.
2. **Atomic update:** lưu refresh token mới và version/generation một cách nhất quán, tránh hai worker ghi đè R2/R3.
3. **Compare-and-set/lease:** nếu nhiều instance cùng phục vụ một session, cần cơ chế phối hợp hoặc token manager tập trung.
4. **Timeout có suy xét:** khi response mất, không retry mù bằng token cũ rồi giả định an toàn; xem API và tính năng nhà cung cấp có hỗ trợ khôi phục, idempotency hoặc độ trễ xử lý hay không.
5. **Phản ứng khi invalid_grant:** không tạo vòng lặp làm mới vô hạn; chuyển tới reauthentication và ghi sự kiện phù hợp.
6. **Không log R1/R2:** dùng token reference, fingerprint hoặc dữ liệu đã che để điều tra.

Một số Authorization Server có thể hỗ trợ khoảng dung sai hoặc cơ chế riêng cho retry hợp lệ. Nếu có, cần hiểu **ngữ nghĩa chính xác và rủi ro replay**; không tự đặt “grace period” tùy ý ở client mà làm mất khả năng phát hiện sử dụng lại.

## 5. Sender-constrained refresh token và bảo vệ chống đánh cắp

**Bearer refresh token** có thể được sử dụng bởi bất kỳ bên nào đang giữ chuỗi token, nếu không có ràng buộc bổ sung. Một lựa chọn tăng bảo vệ là **sender-constraining**, ràng buộc việc sử dụng token với một khóa hoặc chứng chỉ của client.

| Cơ chế | Ý tưởng | Giới hạn |
| --- | --- | --- |
| **Refresh token rotation** | Mỗi lần dùng hợp lệ thay token cũ; phát hiện reuse. | Cần quản lý concurrency; không bảo đảm biết được ai đang giữ token. |
| **DPoP (Demonstrating Proof of Possession)** | Client chứng minh quyền giữ khóa khi trình token đã được ràng buộc theo cơ chế DPoP. | Phải kiểm chứng proof, key binding, replay và cách quản lý khóa; không tự ngăn mọi trường hợp thiết bị bị kiểm soát. |
| **mTLS sender-constrained token** | Ràng buộc token với chứng chỉ client theo giao thức/cấu hình. | Phù hợp các môi trường hỗ trợ quản lý chứng chỉ và kết nối mTLS. |
| **Client authentication** | Confidential client chứng minh danh tính với AS tại token endpoint. | Không thay thế hoàn toàn bảo vệ token bị lộ; phải quản lý bí mật/khóa client. |
| **Token storage bảo vệ** | Giảm nguy cơ token bị lấy từ trình duyệt, log hoặc ổ đĩa. | Không thay thế rotation, chính sách cấp/thu hồi và phát hiện lạm dụng. |

Đối với **public client**, nơi client không thể giữ bí mật client như một confidential backend, chính sách an toàn hiện đại thường yêu cầu cơ chế phát hiện replay như **rotation** hoặc **sender-constraining** khi cấp refresh token. Cách triển khai cụ thể cần tuân theo profile bảo mật và khả năng của Authorization Server được chọn.

**PKCE không phải cơ chế ràng buộc refresh token thay cho rotation.** PKCE chủ yếu bảo vệ việc đổi authorization code trong luồng phù hợp; một refresh token đã bị đánh cắp vẫn cần các biện pháp riêng để chống sử dụng trái phép.

### Scope và resource binding

Refresh token nên gắn với những phạm vi/quyền và Resource Server đã được cho phép; quá trình refresh **không được biến một grant hạn chế thành đặc quyền rộng hơn** chỉ vì client yêu cầu scope mới.

Ví dụ, R1 được cấp cho `tasks.read` không được tự tạo access token có `payroll.admin` nếu chưa có ủy quyền và chính sách hợp lệ. Mover sang vai trò nhạy cảm có thể đòi bước phê duyệt, xác thực tăng cường hoặc authorization flow mới, thay vì tự thêm scope trong một yêu cầu refresh.

## 6. Lưu trữ refresh token theo loại client

Một refresh token thường sống lâu hơn access token, nên tác hại khi bị lộ có thể nghiêm trọng hơn. Nơi lưu token phụ thuộc loại ứng dụng và trust boundary.

### Confidential server-side client

Ứng dụng backend có thể lưu refresh token **ở phía server** trong kho bí mật hoặc storage được mã hóa, giới hạn theo user/session/client và phân quyền chặt. Trình duyệt chỉ giữ **session cookie an toàn**, không nhận refresh token nếu không cần thiết.

Mô hình **Backend for Frontend (BFF)** có thể giúp tách token khỏi JavaScript frontend:

~~~mermaid
flowchart LR
    BR["Browser<br/>HttpOnly Secure session cookie"] --> BFF["Backend for Frontend<br/>session validation"]
    BFF --> VAULT["Protected token store<br/>refresh token"]
    BFF --> AS["Authorization Server<br/>token endpoint"]
    BFF --> API["Resource Server<br/>access token"]
    AS --> BFF
~~~

**BFF không tự loại bỏ mọi rủi ro.** Cần bảo vệ cookie, chống CSRF, session fixation, XSS, SSRF, quyền truy cập kho token và các hành động thay mặt user. BFF cũng phải xử lý rotation và refresh đồng thời an toàn.

### Single-page application (SPA) chạy trong browser

JavaScript trong SPA là một môi trường khó giữ bí mật dài hạn. Nếu refresh token có thể đọc bởi JavaScript, XSS hoặc mã third-party bị xâm phạm có thể lấy hoặc sử dụng nó.

Các lựa chọn cần đánh giá:

- Ưu tiên kiến trúc BFF hoặc giải pháp giữ token phía server khi phù hợp.
- Nếu nhà cung cấp cấp refresh token trực tiếp cho browser public client, yêu cầu cơ chế rotation hoặc sender-constraining và cấu hình thời hạn/phạm vi phù hợp.
- Không mặc định localStorage là kho lưu an toàn cho refresh token; một lỗ hổng XSS có thể đọc dữ liệu có thể truy cập từ JavaScript.
- Tránh đặt token trong URL, browser history, analytics, error report, console log hoặc thông điệp cross-origin chưa kiểm soát.
- Kiểm soát third-party script và Content Security Policy theo thiết kế, nhưng không xem chúng là thay thế cho bảo vệ token.

### Ứng dụng di động và desktop

Native client có thể dùng secure storage do hệ điều hành cung cấp khi phù hợp, nhưng vẫn phải xét malware, thiết bị bị root/jailbreak, backup và chia sẻ dữ liệu giữa ứng dụng. Cần kiểm tra:

1. Token được liên kết đúng application/client ID và account.
2. Dữ liệu lưu theo cơ chế bảo vệ của nền tảng; không lưu plaintext ở vị trí dễ sao chép.
3. Logout, mất thiết bị và thay đổi người dùng có cơ chế xóa/thu hồi token phù hợp.
4. Không đồng bộ refresh token sang thiết bị khác ngoài chính sách.
5. Các lần refresh đồng thời được điều phối và rotation không bị hỏng sau crash.

### Kho lưu ở Authorization Server

Phía AS nên quản lý grant, trạng thái và bằng chứng phát hiện reuse. Nếu thiết kế cho phép, AS có thể lưu **giá trị băm/token reference** thay vì chuỗi bearer token nguyên vẹn, để giảm ảnh hưởng khi dữ liệu bị lộ. **Client vẫn phải có khả năng trình credential hợp lệ** khi sử dụng refresh token; không thể chỉ giữ một hash không thể đổi ngược rồi dùng hash đó như token trừ khi giao thức được thiết kế cụ thể.

## 7. Mối quan hệ với SSO session, OIDC và xác thực lại

**Refresh token không phải phiên đăng nhập của IdP.** Hai thứ có thể được liên kết bởi chính sách của Authorization Server, nhưng vòng đời không nhất thiết trùng nhau.

### Những tình huống thường gặp

| Sự kiện | IdP/SSO session | Refresh token | Cần xác minh |
| --- | --- | --- | --- |
| Đăng nhập thành công | Có thể tạo IdP session. | Có thể được cấp theo grant/policy. | Đúng client, scope, subject, thời hạn. |
| Đóng trình duyệt | Cookie phiên có thể còn hoặc mất tùy cấu hình. | Có thể còn ở backend/native client. | Hành vi phiên sau khi mở lại app. |
| IdP session hết hạn | Cần xác thực lại cho tương tác IdP mới. | Có thể còn hợp lệ hoặc bị policy ràng buộc. | AS có cho refresh tiếp không? |
| Logout tại một ứng dụng | App session bị hủy theo thiết kế. | Có thể cần revoke riêng. | Có token còn nằm ở client/server không? |
| Logout toàn bộ theo chính sách | Các phiên thuộc phạm vi phải kết thúc. | Có thể cần revoke grant/refresh token family. | Đã thu hồi thật ở từng kênh hay chưa? |
| MFA reset hoặc security incident | Có thể yêu cầu xác thực lại. | Có thể cần thu hồi toàn bộ grant liên quan. | Có refresh token cũ nào còn dùng được không? |
| Leaver có hiệu lực | Không còn được đăng nhập mới. | Phải được xử lý để không tạo access mới trái chính sách. | Các app và API có còn access/session cũ không? |

### Refresh không có nghĩa là người dùng vừa xác thực lại

Trong OIDC, một refresh token grant có thể dẫn đến token mới theo khả năng và quy định của nhà cung cấp. Tuy nhiên:

- Việc client đổi refresh token thành công **không chứng minh user vừa nhập mật khẩu, dùng passkey hay thực hiện MFA**.
- Không được tự cập nhật **authentication time** của người dùng thành thời điểm refresh như thể đã có xác thực tương tác mới.
- Với tài nguyên nhạy cảm yêu cầu xác thực gần đây hoặc phishing-resistant MFA, RP/Resource Server phải dựa vào ngữ cảnh xác thực đáng tin cậy và có thể buộc thực hiện luồng reauthentication/step-up phù hợp.
- Một ID token mới nếu được cấp không tự làm cho mọi thuộc tính HR, vai trò hay manager trở nên đúng ở thời điểm hiện tại; cần xác định nguồn dữ liệu và độ mới.

Ví dụ, nhân viên có refresh token từ hôm trước không nên được cấp đặc quyền production vào sáng nay **chỉ vì refresh thành công**. Chính sách PAM/step-up và phê duyệt quyền phải được kiểm tra riêng.

## 8. Refresh token và Joiner–Mover–Leaver

Trong quản lý vòng đời danh tính, nguồn HR/hợp đồng và IAM/IGA quyết định **ai còn đủ điều kiện**, còn Authorization Server quyết định **token nào còn được chấp nhận**. Hai lớp phải được kết nối bằng sự kiện và chính sách đáng tin cậy.

| Sự kiện | Rủi ro liên quan refresh token | Kiểm soát mong đợi |
| --- | --- | --- |
| **Joiner chưa đến ngày kích hoạt** | Client nhận refresh token trước khi danh tính được phép truy cập nghiệp vụ. | Chặn cấp/sử dụng grant trái chính sách; chỉ cho phép onboarding scope giới hạn khi có phê duyệt. |
| **Joiner đã đủ điều kiện** | Token gắn nhầm User/tenant hoặc scope quá rộng. | Kiểm tra identity proofing, account mapping, client, scope, thời hạn và MFA. |
| **Mover đổi bộ phận** | Refresh tiếp tục tạo access token với role/scope cũ. | Tính lại authorization, thu hồi hoặc cập nhật grant khi cần; chặn entitlement dư. |
| **Mover lên đặc quyền** | Refresh cũ âm thầm tạo token quyền admin mới. | Không tự nâng scope/assurance; yêu cầu approval và step-up/PAM theo chính sách. |
| **Suspension** | Token còn giúp truy cập sau quyết định đình chỉ. | Chặn refresh mới, kiểm soát access token/session cũ và ghi hiệu lực. |
| **Leaver có hiệu lực** | Refresh token còn dùng được dù IdP User disabled. | Thu hồi grant/family, chặn phát token mới, đối soát API và account đích. |
| **Rehire** | Tự hồi sinh grant, token hoặc scope của lần làm việc trước. | Liên kết identity đúng người, tạo ủy quyền mới và quyền theo công việc hiện tại. |
| **Contractor expiry** | Token vượt qua ngày hợp đồng kết thúc. | Áp endAt trong quyết định cấp/sử dụng token và thu hồi đúng hạn. |

### Joiner: chuẩn bị account không đồng nghĩa cấp token

IdP/SCIM có thể tạo account trước ngày bắt đầu. Nhưng **pre-provisioning không trao quyền đương nhiên để cấp refresh token sử dụng được với API nghiệp vụ**. Nếu tổ chức cho phép người mới đăng ký MFA hoặc ký hồ sơ trước ngày làm, phạm vi truy cập nên được giới hạn riêng và có thời hạn theo chính sách.

Một kiểm thử quan trọng là: User đang `PENDING_ACTIVATION` có thể dùng refresh token cũ để xin access token gọi API nghiệp vụ không? Nếu có mà chính sách không cho phép, cần xem lại nguồn trạng thái và cách AS kiểm tra grant.

### Mover: xử lý entitlement drift và stale scopes

Giả sử Lan chuyển từ bộ phận hỗ trợ sang kế toán:

1. HR cập nhật bộ phận có hiệu lực.
2. IAM tính lại role và entitlement theo RBAC/ABAC.
3. IdP/SCIM cập nhật account và nhóm ở những đích liên quan.
4. Authorization Server phải xem liệu refresh grant hiện hành có còn phù hợp; nếu không, thu hồi hoặc giới hạn khả năng phát token mới theo chính sách.
5. Resource Server vẫn cần kiểm tra authorization đúng lúc sử dụng, vì **access token đã phát và còn hạn** có thể chứa quyền cũ.

Không nên suy ra rằng đổi department trong HR sẽ tự động làm refresh token hết hiệu lực. Việc này cần tích hợp và quy tắc rõ ràng.

### Leaver: thu hồi refresh token chưa đủ nếu access token còn hạn

Khi một Leaver có hiệu lực, quy trình nên:

1. Xác minh sự kiện từ nguồn có thẩm quyền, identityId, thời điểm hiệu lực và sourceVersion.
2. Disable/suspend khả năng đăng nhập mới theo chính sách tại IdP và ứng dụng.
3. **Thu hồi refresh token và các grant liên quan** của người rời đi theo khả năng Authorization Server.
4. Chấm dứt IdP session và RP/SP session khi có thể, xử lý local auth và credential riêng.
5. Thu hồi quyền/account ở hệ thống đích qua SCIM/connector/API và kiểm tra trạng thái thực tế.
6. Đánh giá access token đã phát nhưng chưa hết hạn; dùng cơ chế kiểm tra trạng thái, revocation/denylist hoặc giới hạn TTL phù hợp với SLA thu hồi.
7. Đối soát bằng chứng trên từng ứng dụng/API, báo rõ những đường truy cập chưa thể xác minh hoặc thu hồi tức thời.
8. Ngăn retry của Joiner/Mover cũ cấp lại grant hoặc bật lại quyền theo sourceVersion lỗi thời.

**Chặn refresh mới ngăn phát sinh access token tiếp theo, không mặc nhiên thu hồi một access token còn hạn**. Đây là điểm phân biệt rất quan trọng khi giảm quyền truy cập tồn dư.

## 9. Revocation, introspection và quyền thực tế tại API

OAuth có những cơ chế và profile hỗ trợ thu hồi hoặc kiểm tra token; tuy nhiên **mức hiệu quả phụ thuộc vào việc từng thành phần thực sự tích hợp**.

### Token revocation

Một client có thể gửi yêu cầu tới **revocation endpoint** khi Authorization Server hỗ trợ theo giao thức/cấu hình tương ứng. Ví dụ minh họa:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: login.example.org
Content-Type: application/x-www-form-urlencoded

token=REDACTED_REFRESH_TOKEN&token_type_hint=refresh_token
~~~

Request thực tế cần xác thực client theo yêu cầu của Authorization Server. Theo thiết kế giao thức, một phản hồi revocation thành công **không phải bằng chứng** mọi access token, cookie hay phiên ở mọi ứng dụng đã bị hủy. Tác động đến token cùng grant hoặc token family phụ thuộc chính sách và sản phẩm; cần kiểm thử.

### Token introspection

Với access token được kiểm tra qua **introspection**, Resource Server có thể hỏi Authorization Server về trạng thái token. Khả năng ngăn truy cập sau Leaver phụ thuộc:

- Resource Server có thật sự thực hiện introspection hoặc kiểm tra trạng thái tương đương không?
- Introspection có báo token không còn active sau khi grant/identity bị thu hồi không?
- API có cache kết quả `active=true` quá lâu không?
- Có kênh API nào vẫn kiểm tra JWT offline mà không xét trạng thái Leaver không?
- Scope, audience và authorization tài nguyên có được kiểm tra độc lập không?

### Bảng khác biệt

| Đường kiểm tra | Điều có thể làm | Không bảo đảm nếu thiếu cơ chế bổ sung |
| --- | --- | --- |
| AS từ chối refresh token | Ngăn phát access token mới qua refresh grant đó. | Token cũ ở API tự động mất hiệu lực ngay. |
| Thu hồi grant/token family | Chấm dứt các refresh token thuộc phạm vi chính sách. | App-local session, PAT hoặc khóa API ở ứng dụng khác đã bị rút. |
| Introspection tại API | API có thể cập nhật quyết định theo trạng thái server. | Mọi API đều gọi introspection hoặc cache đủ ngắn. |
| JWT offline validation | API kiểm chữ ký và thời hạn không cần AS trực tiếp. | Thu hồi ngay khi HR phát Leaver. |
| SCIM active=false | Ứng dụng thay đổi trạng thái User/Group theo khả năng. | Access token, phiên hoặc credential không qua SCIM đã hết hiệu lực. |
| RP/SP logout | Hủy những session thuộc phạm vi logout được hỗ trợ. | Token của mọi client khác đã bị thu hồi. |

**Revocation phải được hiểu là thay đổi trạng thái của một credential/grant trong phạm vi cụ thể**, không phải một công tắc xóa mọi quyền truy cập trên hệ sinh thái.

## 10. Thiết kế Authorization Server kiểm tra refresh grant theo JML

Để tránh cấp token theo trạng thái HR lỗi thời, Authorization Server hoặc thành phần policy hỗ trợ cần có nguồn tin cậy về **lifecycle và quyền hiện hành**.

Pseudocode sau diễn giải các điều kiện khái niệm:

~~~text
refresh(request):
    client = authenticateOrValidateClientByType(request)
    grant = resolveRefreshGrant(request.refreshToken)

    if grant is absent or grant.revoked or grant.expired:
        return OAUTH_ERROR("invalid_grant")
    if not grant.belongsTo(client.id):
        return OAUTH_ERROR("invalid_grant")
    if grant.senderConstrained and not validSenderProof(request, grant):
        return DENY_AND_AUDIT
    if grant.isRotatedOrReused:
        handleReuseAccordingToPolicy(grant.familyId)
        return OAUTH_ERROR("invalid_grant")

    identity = resolveIdentityByTrustedSubject(grant.issuer, grant.subject)
    current = loadTrustedLifecycleState(identity.sourceKey)

    if current is unavailable:
        return applyDocumentedRiskPolicyWithoutPrivilegeEscalation()
    if current.status in [TERMINATED, SUSPENDED]:
        revokeGrantFamily(grant.familyId)
        return OAUTH_ERROR("invalid_grant")
    if now() < current.accessActivationAt:
        return OAUTH_ERROR("invalid_grant")
    if current.endAt exists and now() >= current.endAt:
        revokeGrantFamily(grant.familyId)
        return OAUTH_ERROR("invalid_grant")

    allowed = intersection(
        grant.originallyApprovedScopes,
        currentPolicyAndApprovals(identity, client)
    )
    if allowed is empty or grant.noLongerAuthorized:
        revokeGrantAsPolicyRequires(grant)
        return OAUTH_ERROR("invalid_grant")

    result = atomicallyIssueAccessAndRotateIfConfigured(
        grant,
        client,
        allowed
    )
    writeAuditWithoutSecrets(grant, current.version, result)
    return result
~~~

**Đây là pseudocode để học thiết kế, không phải mã triển khai OAuth hoàn chỉnh.** Nó không mô tả mọi kiểu grant, mức kiểm tra authentication context, giao thức chứng minh sở hữu khóa, transaction hoặc chi tiết lỗi. Một hệ thống thật không cần gọi trực tiếp HR cho từng lần refresh; có thể dùng trạng thái IAM/Policy Engine **đáng tin cậy, đủ mới**, có thiết kế xử lý khi nguồn mất kết nối.

### Ba điểm cần kiểm tra tách biệt

1. **Authorization Server:** có được cấp token mới từ grant đó nữa không?
2. **Client:** có đang giữ và sử dụng refresh token đúng cách, không gây rotation race hoặc lộ credential không?
3. **Resource Server:** access token nhận được có hợp lệ và có quyền với hành động/tài nguyên hiện tại không?

Một test chỉ chứng minh điều (1) **không** chứng minh (2) và (3) đã an toàn.

## 11. Xử lý lỗi, timeout và concurrency

Các ứng dụng thực tế thường làm mới access token khi hết hạn hoặc gần hết hạn. Nếu xử lý lỗi không tốt, chúng có thể làm hỏng refresh token family, lặp vô hạn hoặc tự tạo nhiều request trái phép.

| Tình huống | Nguyên nhân khả dĩ | Hành vi nên có |
| --- | --- | --- |
| `invalid_grant` | Token hết hạn, bị thu hồi, sai client binding hoặc đã bị thay thế. | Ngừng dùng token lỗi; xử lý reauthorization/login và audit theo rủi ro. |
| `invalid_client` | Confidential client không xác thực đúng với AS. | Sửa cấu hình/credential client; không thử lặp bằng bí mật không đúng. |
| Kết nối timeout | AS có thể đã rotation thành công nhưng client không nhận response. | Không retry mù; dùng chiến lược recovery/idempotency hỗ trợ bởi AS, tránh reuse giả. |
| Hai request cùng refresh | Multi-tab, multi-thread, nhiều pod cùng dùng R1. | Single-flight, lock hoặc token manager tập trung, CAS khi lưu thế hệ mới. |
| Server trả 5xx/rate limit | Hệ thống đang quá tải hoặc gián đoạn. | Backoff có giới hạn, tránh tạo thác request. |
| Leaver giữa lúc refresh | HR/IAM chuyển trạng thái trong giao dịch đang xử lý. | Kiểm tra version và policy tại thời điểm phát token, rồi đối soát quyền/token hiệu lực. |
| Đổi scope sau Mover | Grant cũ không còn phù hợp với quyền hiện hành. | Downscope hoặc revoke; yêu cầu grant mới khi cần và đủ phê duyệt. |
| Thiết bị mất hoặc ứng dụng bị gỡ | Token trên thiết bị có thể không còn kiểm soát được. | Thu hồi grant/session từ server, không dựa vào việc ứng dụng đã uninstall. |

### Mẫu lưu refresh token có generation

Một token manager phía server có thể dùng cấu trúc logic:

~~~json
{
  "sessionRef": "session-882",
  "identityId": "ID-LAN-2041",
  "clientId": "work-app-bff",
  "tokenFamilyRef": "family-31",
  "generation": 7,
  "refreshTokenSecretRef": "vault://work-app/session-882/refresh",
  "lastRotatedAt": "2026-12-01T09:05:00+07:00",
  "state": "ACTIVE"
}
~~~

Đây là dữ liệu minh họa, **không phải schema của OAuth/OIDC**. Trường secretRef phải là tham chiếu đến kho kiểm soát truy cập, không phải URL công khai để lấy bearer token. Nếu dùng nhiều instance, phải kết hợp transactional update/lock để không cùng sử dụng một generation theo cách gây reuse.

## 12. Refresh token cho workload và service account

Danh tính máy có thể sử dụng **client credentials grant**, workload federation, mTLS hoặc các cơ chế tương tự. **Trong luồng client_credentials thông thường, refresh token thường không được cấp**, vì client có thể xác thực trực tiếp bằng credential/mối quan hệ tin cậy để xin access token mới.

Không nên tạo refresh token chỉ để “giữ phiên” cho mọi service account khi không có nhu cầu hoặc cơ chế phù hợp. Những kiểm soát quan trọng hơn thường là:

- Xác minh workload thực sự tồn tại, service owner, môi trường triển khai và trust relationship.
- Giới hạn audience, scope, tài nguyên, thời hạn access token và quyền theo least privilege.
- Sử dụng credential ngắn hạn, workload identity federation hoặc rotation phù hợp khi nền tảng hỗ trợ.
- Thu hồi service principal, secret/certificate và grant khi workload ngừng hoặc đổi owner theo chính sách.
- Không gắn việc nghỉ việc của một developer với **xóa tự động mọi service account** đang phục vụ sản xuất; cần bàn giao owner và rotate bí mật từng người từng biết.

**Không dùng quy trình identity proofing giấy tờ dành cho con người để “xác minh máy”.** Với workload identity, cần kiểm tra nguồn phát hành, triển khai, owner và thuộc tính kỹ thuật của chủ thể máy.

## 13. Kiểm thử refresh token

Kiểm thử phải bao phủ cả **luồng thành công**, **luồng bị từ chối**, các lỗi rotation/concurrency và **trạng thái JML**. Sử dụng client, token và identity tổng hợp trong môi trường được ủy quyền; không đưa refresh token thật vào log test.

### Ma trận test

| ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| RT-01 | Client có grant hợp lệ và refresh token chưa hết hạn. | AS cấp access token phù hợp với scope/policy hiện hành. |
| RT-02 | Refresh token sai hoặc không tồn tại. | Bị từ chối; không có access token sử dụng được. |
| RT-03 | Refresh token đã hết hạn hoặc bị revoke. | `invalid_grant` hoặc lỗi tương ứng; không phát token mới. |
| RT-04 | Token thuộc client A được trình bởi client B. | Bị từ chối theo client binding. |
| RT-05 | Sender-constrained token dùng với key/cert không đúng. | Bị từ chối; có audit nếu rủi ro. |
| RT-06 | Token R1 được refresh, nhận R2; R1 được trình lại. | Reuse bị phát hiện và xử lý theo rotation policy. |
| RT-07 | Hai request dùng R1 đồng thời. | Hệ thống không vô tình phát các thế hệ token độc lập trái chính sách; client quản lý race đúng. |
| RT-08 | AS xử lý refresh nhưng response bị mất. | Client không gây vòng lặp reuse vô hạn; xử lý trạng thái mơ hồ an toàn. |
| RT-09 | Grant chỉ có `tasks.read`, client yêu cầu `payroll.admin`. | Không được nâng scope ngoài grant/phê duyệt. |
| RT-10 | User chưa đến ngày activation. | Không cấp access token nghiệp vụ trái chính sách. |
| RT-11 | HR phát Mover thu hồi một vai trò. | Token mới không tái cấp quyền cũ; kiểm thử cả access token cũ tại API. |
| RT-12 | Mover lên vai trò admin nhưng chưa step-up/approval. | Refresh cũ không tự cấp quyền admin. |
| RT-13 | Leaver có hiệu lực trong lúc client chuẩn bị refresh. | Refresh mới bị từ chối theo policy; token đã phát được kiểm soát theo revocation boundary. |
| RT-14 | Leaver rồi retry Joiner cũ. | Grant/token không bị tái kích hoạt trái sourceVersion mới. |
| RT-15 | Logout một thiết bị so với logout tất cả. | Phạm vi revoke đúng chính sách, được kiểm tra tại những client liên quan. |
| RT-16 | Rehire sau khi grant cũ đã revoke. | Không tự phục hồi refresh token/grant cũ. |
| RT-17 | AS tạm unavailable. | Client không gửi token tới bên khác hoặc fallback bằng grant yếu hơn. |
| RT-18 | JWT access token còn hạn sau refresh grant bị revoke. | Ghi nhận đúng hành vi Resource Server và giới hạn truy cập tồn dư. |
| RT-19 | Browser gặp XSS trong môi trường test. | Kiến trúc token storage hạn chế khả năng đọc/lấy refresh token theo threat model; không log secret. |
| RT-20 | Grant của nhà thầu tới ngày hết hạn. | Token không tiếp tục được sử dụng để cấp access mới ngoài thời hạn được phép. |

### Test case Given–When–Then

~~~gherkin
Feature: Refresh tokens follow identity lifecycle

  Scenario: Valid rotation replaces the previous refresh token
    Given a test client holds refresh token R1
    And the authorization grant is active
    When the client refreshes using R1
    Then it receives a valid access token
    And it receives R2 when rotation is configured
    And reusing R1 is rejected and handled by policy

  Scenario: Leaver cannot renew API access
    Given an identity has an active authorization grant
    And a Leaver event becomes effective
    When the client uses its previously issued refresh token
    Then the Authorization Server rejects renewal
    And previously issued access is assessed against revocation policy

  Scenario: Mover cannot gain unapproved administrator scope
    Given the grant permits only tasks.read
    And the identity changes to a privileged job role
    When the client refreshes and requests payroll.admin
    Then no unapproved administrator scope is issued
    And step-up and approval requirements remain enforced
~~~

Các kịch bản dùng dữ liệu tổng hợp. Một triển khai cụ thể cần biết OAuth profile, loại client và chính sách rotation/revoke để viết assertion đúng; **không tự xem mọi response có refresh_token mới** nếu hệ thống không dùng rotation.

### Kiểm thử concurrency và Leaver

~~~text
test("Leaver wins over stale refresh retry"):
    identity = createSyntheticActiveIdentity()
    grant = createTestGrant(identity, client = "work-app")

    taskA = startControlledRefresh(grant.currentRefreshToken)
    event = emitAuthoritativeLeaver(
        identity.sourceKey,
        effectiveAt = controlledClock.now,
        sourceVersion = 43
    )
    completeControlledRace(taskA, event)

    assert currentIdentityState(identity) == TERMINATED
    assert anySubsequentRefresh(grant).isDenied
    assert staleJoinerRetryCannotCreateNewGrant(identity)

    tokens = inspectTestAccessTokensIssuedNearEvent(identity)
    assert tokens.followDocumentedRevocationBoundary
    assert auditContainsSourceVersionAndCorrelationId(event)
~~~

Trong thực tế, một token có thể đã được cấp **trước** khi Leaver có hiệu lực nhưng tới client **sau** thời điểm đó. Cần xác định ranh giới nghiệp vụ và chính sách xử lý token đã phát, không chỉ căn cứ vào thứ tự nhận response.

## 14. Audit, chỉ số và vận hành

### Những gì cần kiểm toán

| Dữ liệu | Mục đích |
| --- | --- |
| Grant/token family reference | Truy vết chuỗi rotation và thu hồi mà không lộ token. |
| Identity ID, issuer, client ID, tenant | Xác nhận đúng người/client/phạm vi. |
| Scope/resource được phép | Phát hiện privilege escalation hoặc cấp token ngoài quyền. |
| IssuedAt, rotatedAt, expiresAt, lastUsedAt | Phân tích lifetime và lịch sử hoạt động. |
| Rotation generation và reuse flag | Điều tra concurrency, token theft và family revocation. |
| JML event, effectiveAt, sourceVersion | Chứng minh quyết định refresh gắn với trạng thái vòng đời hiện hành. |
| Result và error classification | Phân biệt token hết hạn, client lỗi, replay hoặc kết nối thất bại. |
| Revocation action và verifiedAt | Đo thời gian ngừng cấp token mới và quyền còn tồn. |
| Correlation ID và owner | Liên kết AS, IAM, RP và API; gán người xử lý lỗi. |

Ví dụ event nội bộ:

~~~json
{
  "eventType": "OAUTH_REFRESH_DENIED",
  "identityId": "ID-LAN-2041",
  "clientId": "work-app",
  "tokenFamilyRef": "family-31",
  "grantRef": "grant-882",
  "sourceEvent": "LEAVER",
  "sourceVersion": 43,
  "effectiveAt": "2026-12-01T17:00:00+07:00",
  "decision": "DENY_REFRESH",
  "reason": "IDENTITY_TERMINATED",
  "observedAt": "2026-12-01T17:00:02+07:00",
  "correlationId": "leaver-2041-v43"
}
~~~

Đây là schema minh họa, không phải chuẩn giao thức. **Không ghi raw refresh token, access token, mật khẩu, client secret, private key, cookie hoặc proof mật mã vào log**. Nếu muốn nhận diện một token trong sự cố, dùng token reference/fingerprint được bảo vệ theo chính sách và giới hạn quyền truy cập audit.

### Chỉ số vận hành quan trọng

| Chỉ số | Giúp phát hiện |
| --- | --- |
| **Refresh success/failure rate theo client** | Client cấu hình sai, outage hoặc thay đổi chính sách. |
| **Rotation reuse detections** | Có thể có token theft hoặc race/ghi storage lỗi. |
| **Token family revocations** | Quy mô ảnh hưởng của sự cố và mức độ người dùng phải đăng nhập lại. |
| **Refresh after Leaver attempts** | Grant cũ hoặc client còn cố sử dụng sau thời điểm chấm dứt. |
| **Time to stop renewal** | Độ trễ từ effectiveAt đến khi AS ngừng phát access mới. |
| **Residual access after revocation** | Token/API session cũ vẫn hoạt động bao lâu. |
| **Unexpected scope increase** | Cấp quyền rộng hơn grant/approval hoặc policy hiện hành. |
| **Inactive but unexpired grants** | Refresh token/grant không còn nhu cầu nhưng vẫn hợp lệ. |
| **Client concurrency conflict rate** | Tần suất refresh cùng token gây lỗi replay hoặc forced re-login. |
| **Revocation coverage** | Tỷ lệ client/grant nằm trong phạm vi thu hồi và kiểm chứng được. |

Không lấy “refresh thành công nhiều” làm thước đo an toàn. Một hệ thống có success rate cao vẫn có thể cấp token cho danh tính đã Leaver hoặc duy trì scope quá rộng nếu không kết hợp kiểm tra chính sách và kiểm toán.

## 15. Những sai lầm thiết kế phổ biến

1. **Đưa refresh token vào Resource Server** cùng access token. Điều này tăng bề mặt lộ và nhầm mục đích giao thức; refresh token chỉ dành cho AS/token endpoint.
2. **Lưu refresh token trong log hoặc browser storage không được đánh giá rủi ro.** Một bản log hoặc XSS có thể biến thành khả năng truy cập lâu dài.
3. **Không dùng rotation/sender-constraining với public client** khi chính sách yêu cầu, khiến token bị sao chép có thể được sử dụng tiếp.
4. **Rotation mà không xử lý đa luồng.** Hai request dùng R1 đồng thời có thể gây reuse detection và thu hồi cả family.
5. **Dùng refresh token làm bằng chứng user vừa xác thực MFA.** Refresh là cấp token dựa trên grant, không phải hành vi tái xác thực tương tác.
6. **Tin rằng IdP logout hoặc SCIM active=false thu hồi mọi token.** Phiên ứng dụng và access token offline có thể vẫn tồn tại.
7. **Không kiểm tra trạng thái Leaver tại thời điểm refresh.** Token cũ có thể tiếp tục phát access mới sau khi hợp đồng kết thúc.
8. **Tự thêm scope/admin permission khi Mover.** Thay đổi vai trò không tự cho phép mở rộng grant ngoài phê duyệt và step-up.
9. **Retry mù khi timeout.** AS có thể đã rotation thành công; retry R1 gây lỗi reuse không cần thiết.
10. **Đánh dấu thu hồi toàn bộ chỉ vì revocation endpoint trả thành công.** Cần readback và kiểm tra các Resource Server, app session và credential độc lập trong phạm vi yêu cầu.

## 16. Tình huống thực hành

### Tình huống A — Hai tab refresh cùng lúc

**Bối cảnh:** Một SPA có R1, hai tab cùng thấy access token sắp hết hạn. Cả hai gửi refresh(R1). Tab thứ nhất nhận R2, tab thứ hai bị báo reuse.

**Câu hỏi:** Vì sao đăng nhập có thể bị gián đoạn ngay cả khi không có kẻ tấn công?

**Gợi ý:** Rotation yêu cầu sử dụng token theo thế hệ. Hai tab không điều phối có thể kích hoạt xử lý reuse và khiến grant/family bị thu hồi. Cần token manager, single-flight/lock và lưu generation nhất quán; không tắt kiểm tra replay để xử lý lỗi này.

### Tình huống B — Leaver nhưng API vẫn chấp nhận JWT

**Bối cảnh:** HR phát Leaver lúc 17:00; AS đã từ chối refresh từ 17:01. Tuy nhiên, một JWT access token phát lúc 16:59 có hạn đến 17:14 và API vẫn kiểm chữ ký offline.

**Câu hỏi:** Việc ngừng refresh có đủ đáp ứng yêu cầu thu hồi ngay không?

**Gợi ý:** Không. Cần cơ chế token validation/denylist/introspection hoặc chính sách TTL và kiểm soát bù đáp ứng rủi ro. Phải đo quyền truy cập tồn dư tại Resource Server, không chỉ nhìn trạng thái AS.

### Tình huống C — Mover tự nhiên có scope admin

**Bối cảnh:** Lan chuyển sang đội quản trị, refresh token cũ chỉ được cấp `tasks.read`; client gửi refresh yêu cầu `cloud.admin`.

**Câu hỏi:** AS có nên cho phép chỉ vì HR đã đổi chức danh?

**Gợi ý:** Không. Cần quyền thực sự được duyệt, scope/grant policy và mức xác thực/step-up phù hợp. Nếu cần authorization mới, phải thực hiện quy trình tương ứng; không tự nâng grant cũ.

### Tình huống D — Backend mất response của R2

**Bối cảnh:** AS xử lý R1, phát R2, nhưng mạng timeout trước khi backend nhận phản hồi. Backend chỉ còn R1 trong kho.

**Câu hỏi:** Tại sao retry vô điều kiện có thể nguy hiểm?

**Gợi ý:** R1 đã bị thay thế. Retry có thể bị xem là reuse, thu hồi cả family. Cần chiến lược xử lý trạng thái mơ hồ với cơ chế do AS hỗ trợ, không giả định request trước đó thất bại.

### Tình huống E — Đăng xuất web nhưng app di động vẫn hoạt động

**Bối cảnh:** Lan bấm Sign out trong browser. IdP session web kết thúc; native mobile app vẫn giữ refresh token hợp lệ.

**Câu hỏi:** Đây có nhất thiết là lỗi?

**Gợi ý:** Phải xem sản phẩm tuyên bố logout một thiết bị, một client hay tất cả phiên/grant. Nếu chính sách yêu cầu logout toàn bộ, cần revoke grant của mobile và xác minh; không suy ra từ việc cookie browser đã bị xóa.

### Tình huống F — Account dịch vụ bị gán nhầm refresh token

**Bối cảnh:** Một job CI/CD dùng client_credentials nhưng đội phát triển định thêm refresh token dài hạn để “đỡ phải gọi token endpoint”.

**Câu hỏi:** Có hợp lý không?

**Gợi ý:** Trong client_credentials thông thường, client có thể dùng thông tin xác thực hoặc workload federation để xin access token mới; refresh token thường không cần và không được phát theo mô hình tiêu chuẩn thông thường. Cần tối ưu caching, bảo vệ client credential và scope thay vì tự tạo bearer secret dài hạn không cần thiết.

## 17. Câu hỏi tự kiểm tra

**1. Refresh token có phải được gửi trong header Authorization tới API nghiệp vụ không?**

Không. Nó được dùng ở token endpoint của Authorization Server để xin access token mới; API nghiệp vụ sử dụng loại access token phù hợp.

**2. Sau khi refresh thành công, có thể suy ra user vừa thực hiện lại MFA không?**

Không. Refresh thường là một lần cấp token dựa trên grant hiện tại, không phải xác thực tương tác mới.

**3. Refresh token rotation giúp phát hiện tình huống gì?**

Việc token đã được thay thế bị dùng lại. Đó có thể là token bị sao chép hoặc là lỗi xử lý đồng thời/timeout; cần điều tra và chính sách family revocation.

**4. PKCE có thay thế được rotation hoặc sender-constraining cho refresh token không?**

Không. PKCE bảo vệ việc đổi authorization code; refresh token cần các biện pháp và vòng đời riêng.

**5. Vì sao không nên lưu refresh token trực tiếp trong localStorage mà không đánh giá rủi ro?**

Vì JavaScript trên cùng origin có thể đọc nó nếu có XSS hoặc mã third-party bị xâm phạm; nên xem xét BFF hoặc cơ chế lưu/bảo vệ phù hợp.

**6. Nếu refresh token đã bị revoke, access token JWT còn hạn có tự bị API từ chối không?**

Không mặc định. Nếu API chỉ kiểm chữ ký và exp offline, token có thể còn dùng tới hạn nếu không có kiểm soát bổ sung.

**7. Sau Mover, client có thể tự xin scope admin mới bằng refresh token cũ không?**

Không được mở rộng ngoài grant/phê duyệt và chính sách, dù chức danh đã đổi; có thể phải yêu cầu authorization và step-up mới.

**8. Leaver có hiệu lực nhưng một job retry Joiner cũ cố cấp lại token. Điều gì ngăn việc này?**

Kiểm tra lifecycle state, effectiveAt, sourceVersion/grant state, thực thi idempotent và đối soát giữa IAM với Authorization Server.

**9. Có nên dùng refresh token cho mọi service account gọi API không?**

Không. Với client_credentials thông thường, client xác thực để xin access token mới; cần quản trị workload credential và grant phù hợp, tránh tạo bí mật dài hạn không cần thiết.

## Ghi nhớ

- **Refresh token** là credential dùng tại **Authorization Server** để xin access token mới; khác với access token, ID token, IdP session và app session.
- **Rotation, sender-constraining, bảo vệ token storage và phát hiện reuse** giúp hạn chế rủi ro token bị đánh cắp; client phải xử lý concurrency/timeout để không tự làm hỏng token family.
- **Refresh không phải tái xác thực MFA**, không tự nâng phạm vi quyền và không chứng minh người dùng vẫn đủ điều kiện truy cập sau thay đổi nhân sự.
- **Joiner** không được dùng grant trước thời điểm cho phép; **Mover** cần đánh giá lại scope/quyền và assurance; **Leaver** phải chặn refresh, thu hồi grant/phiên và kiểm tra đường truy cập tồn dư.
- **IdP/SSO, SCIM, RBAC/ABAC và Resource Server** có trách nhiệm khác nhau; ngừng phát token mới chưa chứng minh access token cũ, cookie ứng dụng hoặc PAT đã bị thu hồi.
- **Readback, kiểm thử âm, xử lý sự kiện sai thứ tự, audit không lộ secret và đo thời gian tồn dư** là nền tảng để refresh token phục vụ trải nghiệm liên tục mà vẫn tuân thủ vòng đời IAM.
