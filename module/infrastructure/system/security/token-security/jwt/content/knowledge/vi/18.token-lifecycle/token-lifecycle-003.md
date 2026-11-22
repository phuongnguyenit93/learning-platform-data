# Refresh token không mặc nhiên là JWT

## 1. Refresh token là vai trò, JWT là định dạng

Trong OAuth 2.0, **refresh token** là credential mà client gửi tới Authorization Server để xin cấp Access Token mới khi Access Token hiện tại hết hạn hoặc không còn phù hợp. Refresh token đại diện cho quyền tiếp tục sử dụng một authorization grant theo chính sách của Authorization Server.

**JWT (JSON Web Token)** lại là một định dạng biểu diễn claims, có thể được bảo vệ bằng chữ ký, MAC hoặc mã hóa theo JOSE. JWT mô tả cách dữ liệu được đóng gói và bảo vệ; nó không tự quyết định credential được dùng vào mục đích gì.

Hai khái niệm thuộc hai trục khác nhau:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Vai trò của token | Token được dùng để làm gì? | Access token, refresh token, ID token, assertion |
| Định dạng của token | Token được biểu diễn như thế nào? | Opaque/reference string, JWT/JWS, JWT/JWE |

Do đó, refresh token có thể là một chuỗi opaque ngẫu nhiên được Authorization Server tra cứu trong kho trạng thái. Nó cũng có thể được biểu diễn bằng JWT nếu hệ thống thiết kế một profile riêng cho mục đích đó. OAuth 2.0 không yêu cầu refresh token phải là JWT.

Một hệ thống phát hành Access Token dạng JWT hoàn toàn có thể phát hành Refresh Token dạng opaque. Đây là thiết kế phổ biến vì Authorization Server cần kiểm soát vòng đời, rotation, replay và thu hồi của refresh token.

Nội dung này thuộc module Security - JSON Web Token (JWT), chương Vòng đời token. Phạm vi là bảo mật OAuth/JWT tổng quát, không phụ thuộc Java, Spring Security hay một framework cụ thể.

## 2. Refresh token làm nhiệm vụ gì?

Access Token thường có thời hạn tương đối ngắn và được gửi tới Resource Server để truy cập tài nguyên. Refresh Token được gửi tới Authorization Server để đổi lấy Access Token mới.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>AS: Authorization Grant / Authentication
    AS-->>C: Access Token + Refresh Token
    C->>RS: Request với Access Token
    RS-->>C: Resource response
    Note over C,RS: Access Token hết hạn hoặc cần cấp mới
    C->>AS: grant_type=refresh_token
    AS->>AS: Kiểm tra refresh token và trạng thái
    AS-->>C: Access Token mới + Refresh Token mới nếu rotation
    C->>RS: Request với Access Token mới
    RS-->>C: Resource response
~~~

Refresh token giúp client tiếp tục phiên cấp quyền mà không phải yêu cầu người dùng thực hiện lại toàn bộ quy trình xác thực mỗi khi Access Token hết hạn. Điều này không có nghĩa refresh token là một phiên đăng nhập vô thời hạn. Authorization Server vẫn có thể áp dụng thời hạn tuyệt đối, thời hạn không hoạt động, thu hồi, xác thực lại hoặc yêu cầu consent tùy chính sách.

Theo OAuth 2.0:

- Refresh token được gửi tới Authorization Server.
- Refresh token không được gửi tới Resource Server để truy cập API.
- Client dùng refresh token tại Token Endpoint với grant type là refresh_token.
- Authorization Server có thể cấp Access Token mới và có thể cấp refresh token mới.
- Refresh token có thể bị ràng buộc với client đã được cấp nó.

Không đặt refresh token vào Authorization header của request API như thể nó là Access Token. Nếu Resource Server nhận refresh token, đó là lỗi phân tách vai trò credential.

## 3. Refresh token không có định dạng bắt buộc là JWT

RFC 6749 mô tả refresh token là một chuỗi đại diện cho authorization grant được dùng để lấy Access Token mới. Chuỗi này thường opaque đối với client: client không cần hiểu cấu trúc bên trong mà chỉ lưu giữ và gửi lại theo giao thức.

Authorization Server có thể chọn nhiều cách biểu diễn:

| Mô hình | Dữ liệu client nhận | Cách Authorization Server xử lý |
| --- | --- | --- |
| Opaque/reference token | Chuỗi ngẫu nhiên khó đoán | Tra cứu bản ghi và trạng thái trong kho dữ liệu |
| JWT refresh token | JWT có claims được bảo vệ | Xác minh mật mã và kiểm tra thêm trạng thái/vòng đời theo policy |
| Credential dạng tham chiếu có cấu trúc riêng | Chuỗi theo định dạng nội bộ | Phân tích theo hợp đồng riêng; không mặc nhiên là JWT |

Một chuỗi opaque có thể có tiền tố hoặc định dạng nội bộ để hỗ trợ định tuyến, phiên bản hoặc key identifier. Điều đó không làm nó trở thành JWT. Ngược lại, một chuỗi có ba phần phân tách bằng dấu chấm cũng chưa đủ để kết luận nó là JWT hợp lệ; cần xác định serialization và profile mà hệ thống thực sự hỗ trợ.

### 3.1. Vì sao opaque refresh token thường phù hợp?

Opaque token cho phép Authorization Server giữ toàn bộ trạng thái có thẩm quyền ở phía máy chủ:

- Client, subject và authorization grant được gắn với token.
- Scope và resource được cấp có thể được kiểm soát.
- Trạng thái active/revoked được cập nhật ngay trong kho dữ liệu.
- Rotation và phát hiện reuse có thể thực hiện bằng một lần cập nhật trạng thái.
- Không cần để client hoặc Resource Server diễn giải claims nội bộ.

Opaque token cũng giúp tránh đưa thông tin về subject, client, session hoặc cấu trúc nội bộ vào credential mà client đang giữ. Tuy nhiên, opaque không tự động an toàn: token vẫn cần entropy cao, truyền qua TLS, lưu trữ an toàn và có kiểm soát vòng đời.

### 3.2. Khi nào có thể chọn JWT refresh token?

JWT refresh token có thể phù hợp khi kiến trúc có lý do rõ ràng để cần một credential self-contained hoặc cần dùng chung cơ chế JOSE. Ví dụ, một hệ thống phân tán có thể muốn xác minh issuer và một số thuộc tính mà không cần tra cứu bản ghi đầy đủ cho mọi bước.

Tuy nhiên, refresh token có yêu cầu quản lý trạng thái cao hơn Access Token thông thường. Nếu hệ thống cần rotation, phát hiện replay, logout hoặc thu hồi tức thời, JWT refresh token vẫn cần kho trạng thái, denylist, token family, introspection hoặc một cơ chế tương đương.

Không nên chọn JWT chỉ vì Access Token đang dùng JWT hoặc vì muốn loại bỏ cơ sở dữ liệu. Việc ký một refresh token không làm cho replay và revocation tự biến mất.

## 4. Phân biệt Access Token và Refresh Token

| Tiêu chí | Access Token | Refresh Token |
| --- | --- | --- |
| Mục đích | Truy cập Resource Server | Xin cấp Access Token mới |
| Nơi gửi | Resource Server/API | Authorization Server/Token Endpoint |
| Thời hạn | Thường ngắn hơn | Thường dài hơn Access Token nhưng vẫn có giới hạn |
| Phạm vi sử dụng | Audience/resource được cấp | Client và authorization grant đã được ràng buộc |
| Được dùng như bearer credential? | Có thể, theo token type và profile | Thường là credential nhạy cảm mà ai sở hữu cũng có thể thử sử dụng |
| Có thể là JWT? | Có | Có thể, nhưng không bắt buộc |
| Trạng thái phía máy chủ | Có thể xác minh cục bộ nếu self-contained | Thường cần quản lý trạng thái để rotation/revocation |
| Khi bị lộ | Kẻ khác có thể truy cập tài nguyên trong phạm vi và thời hạn token | Kẻ khác có thể xin Access Token mới, thường gây ảnh hưởng lâu hơn |

Không dùng một loại token thay cho loại kia. Resource Server phải từ chối refresh token ngay cả khi token đó có chữ ký hợp lệ hoặc có các claims trông giống Access Token.

## 5. Refresh token opaque: mô hình tham chiếu có trạng thái

Với opaque refresh token, Authorization Server tạo một giá trị ngẫu nhiên đủ mạnh và lưu một bản ghi tương ứng. Client chỉ nhìn thấy chuỗi token; các thuộc tính như subject, client, grant, scope, expiry và trạng thái được lưu phía máy chủ.

Ví dụ một bản ghi logic:

~~~yaml
refreshTokenRecord:
  tokenId: rt-8f42
  tokenVerifier: hash-of-random-token
  clientId: web-client-01
  subjectId: user-123
  grantId: grant-92ab
  familyId: family-7d31
  scopes:
    - invoice:read
  resources:
    - https://api.example.org/invoices
  issuedAt: 1893456000
  expiresAt: 1896048000
  lastUsedAt: 1893456000
  status: active
~~~

Đây là cấu trúc minh họa, không phải schema OAuth tiêu chuẩn. Hệ thống có thể lưu thêm thông tin client binding, sender constraint, tenant, consent, rotation lineage hoặc lý do thu hồi.

### 5.1. Tạo giá trị opaque có entropy cao

Refresh token là credential có giá trị cao. Khi tạo token opaque:

- Dùng bộ sinh số ngẫu nhiên mật mã (CSPRNG).
- Tạo đủ entropy để không thể đoán hoặc dò bằng brute force trong thực tế.
- Không dùng user ID, email, timestamp, số thứ tự hoặc dữ liệu dễ suy đoán làm token.
- Không tái sử dụng giá trị token giữa các grant hoặc token family.
- Giới hạn độ dài và định dạng đầu vào tại Token Endpoint.

Token có thể được mã hóa thành Base64URL hoặc biểu diễn bằng chuỗi ký tự an toàn cho giao thức. Cách biểu diễn không thay thế entropy của dữ liệu ngẫu nhiên.

### 5.2. Lưu verifier thay vì raw token

Authorization Server có thể lưu hash/verifier của refresh token thay vì lưu nguyên giá trị bearer token. Khi client gửi token:

1. Server nhận giá trị qua TLS.
2. Tính verifier theo cơ chế lưu trữ đã chọn.
3. Tìm bản ghi tương ứng.
4. Kiểm tra client, grant, thời hạn và trạng thái.
5. Tiếp tục rotation hoặc cấp Access Token nếu hợp lệ.

Vì refresh token được tạo ngẫu nhiên với entropy cao, một hash mật mã phù hợp có thể dùng làm verifier. Có thể dùng HMAC với secret phía máy chủ nếu muốn giảm rủi ro khi chỉ cơ sở dữ liệu bị lộ; secret đó phải được quản lý riêng và không lưu cùng bảng token. Không dùng password hash chậm như một cách thay thế mặc định mà không đánh giá yêu cầu hiệu năng và mô hình đe dọa.

Không log raw refresh token, không đưa vào analytics, URL, crash report hoặc thông báo lỗi. Nếu cần tìm kiếm vận hành, dùng token record ID hoặc fingerprint đã được thiết kế để không tiết lộ credential.

## 6. Vòng đời của refresh token

Refresh token có một vòng đời riêng, thường gắn với authorization grant, client, subject hoặc session:

~~~mermaid
stateDiagram-v2
    [*] --> Issued
    Issued --> Active: Client nhận token
    Active --> Rotated: Refresh thành công và cấp token mới
    Rotated --> Consumed: Token cũ bị vô hiệu
    Active --> Revoked: Logout / admin / security event
    Active --> Expired: Hết hạn tuyệt đối hoặc idle timeout
    Consumed --> ReuseDetected: Token cũ đã bị dùng lại
    ReuseDetected --> FamilyRevoked: Thu hồi token còn hoạt động trong family
    Revoked --> [*]
    Expired --> [*]
    Consumed --> [*]
    FamilyRevoked --> [*]
~~~

Các trạng thái trên là mô hình quản lý phổ biến. Một triển khai có thể dùng tên hoặc cấu trúc khác, nhưng cần phân biệt token đang hoạt động, đã được thay thế, bị thu hồi, hết hạn và bị phát hiện reuse.

Các mốc thời gian thường được quản lý:

- **Absolute expiration:** thời điểm cuối cùng token được phép sử dụng, không phụ thuộc hoạt động gần đây.
- **Idle expiration:** thời điểm token hết hiệu lực nếu không được sử dụng trong một khoảng thời gian.
- **Issued/created time:** thời điểm phát hành.
- **Last used/refreshed time:** thời điểm sử dụng gần nhất.
- **Family lifetime:** giới hạn tổng thể của một chuỗi refresh token được rotation.

Không kéo dài vô hạn thời hạn tuyệt đối chỉ vì client liên tục refresh. Sliding expiration có thể hữu ích, nhưng nên có giới hạn tuyệt đối hoặc yêu cầu xác thực lại theo rủi ro.

## 7. Refresh token rotation

**Refresh token rotation** là cơ chế Authorization Server cấp một refresh token mới sau mỗi lần refresh thành công và vô hiệu hóa refresh token cũ.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    C->>AS: Refresh Token R1
    AS->>AS: Xác minh R1 và trạng thái active
    AS->>AS: Vô hiệu R1, tạo R2
    AS-->>C: Access Token mới + Refresh Token R2
    C->>AS: Refresh Token R2
    AS->>AS: Vô hiệu R2, tạo R3
    AS-->>C: Access Token mới + Refresh Token R3
    C->>AS: Gửi lại R1 đã bị thay thế
    AS->>AS: Phát hiện reuse của R1
    AS->>AS: Thu hồi refresh token còn hoạt động trong family
    AS-->>C: Từ chối yêu cầu
~~~

Rotation giúp phát hiện trường hợp refresh token cũ bị đánh cắp và sử dụng lại sau khi client hợp lệ đã đổi token. Khi token cũ xuất hiện lần nữa, Authorization Server có thể suy ra credential đã bị sao chép hoặc có race condition cần điều tra.

### 7.1. Cập nhật trạng thái phải nguyên tử

Không triển khai rotation theo kiểu:

1. Đọc token và thấy active.
2. Cấp Access Token mới.
3. Sau đó mới đánh dấu refresh token cũ đã dùng.

Hai request đồng thời có thể cùng đọc trạng thái active và cùng được cấp token mới. Thay vào đó, thao tác kiểm tra và tiêu thụ token cũ phải được thực hiện theo transaction hoặc cơ chế compare-and-swap/atomic update:

~~~text
BEGIN TRANSACTION

record = load refresh token record for update
require record.status == ACTIVE
require record is not expired or revoked
require client and grant binding are valid

mark old record as CONSUMED
create replacement refresh token in the same family
issue new access token

COMMIT
~~~

Nếu việc phát hành token và cập nhật trạng thái đi qua nhiều hệ thống, cần thiết kế tính nhất quán, idempotency và phục hồi lỗi. Không để một lỗi mạng khiến token cũ vẫn active trong khi token mới đã được client nhận.

### 7.2. Xử lý request refresh đồng thời

Client có thể gửi hai request refresh gần như cùng lúc do nhiều tab, nhiều worker hoặc retry mạng. Với rotation nghiêm ngặt, request thứ hai có thể bị xem như reuse của token vừa bị tiêu thụ.

Client nên phối hợp để chỉ có một thao tác refresh đang diễn ra cho cùng một token/session (single-flight). Authorization Server cũng cần transaction và chính sách xử lý race rõ ràng. Một khoảng grace period tùy tiện có thể làm giảm khả năng phát hiện token bị đánh cắp; nếu dùng cơ chế dung sai, phải xác định chính xác điều kiện và giới hạn.

### 7.3. Token family và reuse detection

Token family là tập các refresh token nối tiếp nhau qua các lần rotation, cùng đại diện cho một grant/session. Authorization Server có thể giữ quan hệ:

~~~text
R1 [consumed] -> R2 [consumed] -> R3 [active]
~~~

Nếu R1 hoặc R2 đã bị thay thế nhưng xuất hiện lại, server phát hiện reuse. Theo chính sách bảo vệ, server có thể thu hồi refresh token hiện hành trong family, buộc client thực hiện authorization lại và ghi nhận sự kiện bảo mật.

Không phải mọi lỗi refresh đều chứng minh token bị đánh cắp. Cần phân biệt token hết hạn, client không hợp lệ, lỗi mạng, replay thực sự và race condition. Tuy nhiên, không được âm thầm chấp nhận token đã bị tiêu thụ như một token active mới.

## 8. Refresh token revocation và logout

Refresh token có thể cần bị vô hiệu trước thời hạn trong các tình huống:

- Người dùng đăng xuất.
- Quản trị viên kết thúc phiên.
- Người dùng đổi mật khẩu hoặc tài khoản bị khóa theo chính sách.
- Client bị thu hồi quyền hoặc bị xóa.
- Phát hiện refresh token reuse.
- Thiết bị bị mất hoặc credential bị lộ.
- Consent hoặc authorization grant bị thu hồi.

Authorization Server có thể quản lý revocation theo từng token, token family, session, grant hoặc client. Phạm vi thu hồi cần được xác định rõ để tránh chỉ thu hồi một token trong khi các token liên quan vẫn có thể tiếp tục cấp Access Token.

RFC 7009 định nghĩa OAuth Token Revocation Endpoint. Client có thể yêu cầu thu hồi token theo giao thức; Authorization Server xác thực client và xử lý trạng thái tương ứng. Việc một endpoint trả phản hồi thành công không tự đảm bảo mọi cache hoặc Resource Server lập tức cập nhật trạng thái.

### 8.1. Logout và access token đã phát hành

Thu hồi refresh token ngăn việc dùng credential đó để xin Access Token mới. Nó không nhất thiết làm các Access Token đã cấp trước đó mất hiệu lực ngay lập tức.

Nếu Access Token là JWT được Resource Server xác minh cục bộ, token có thể tiếp tục được chấp nhận tới exp trừ khi hệ thống có thêm cơ chế như:

- Access Token có thời hạn ngắn.
- Denylist hoặc introspection.
- Session/version check.
- Vô hiệu hóa signing key trong tình huống nghiêm trọng.

Do đó, logout cần mô tả rõ phạm vi: chỉ ngăn refresh tiếp, kết thúc session, thu hồi token family hay còn yêu cầu vô hiệu Access Token đang hoạt động.

## 9. Ràng buộc refresh token với client

Refresh token là credential nhạy cảm. Nếu chỉ dựa vào việc sở hữu chuỗi token, kẻ tấn công đánh cắp token có thể thử gửi nó tới Token Endpoint.

Authorization Server cần ràng buộc refresh token với client đã được cấp nó và xác minh client theo loại client:

- **Confidential client:** xác thực client tại Token Endpoint theo phương thức đã đăng ký.
- **Public client:** không thể dựa vào một client secret được nhúng trong ứng dụng để chứng minh danh tính một cách đáng tin cậy.
- **Sender-constrained refresh token:** ràng buộc token với khóa/chứng thư mà client phải chứng minh đang sở hữu.

RFC 9700 yêu cầu Authorization Server bảo vệ refresh token của public client bằng một trong hai cách: sender-constrain refresh token hoặc dùng refresh token rotation để phát hiện replay.

Các cơ chế sender constraint có thể bao gồm DPoP hoặc mutual-TLS theo profile phù hợp. Việc chỉ đưa client_id vào payload không chứng minh người gửi đang giữ credential của client.

### 9.1. Ràng buộc client không đồng nghĩa với ràng buộc thiết bị tuyệt đối

Một client có thể chạy trên nhiều thiết bị hoặc nhiều phiên. Nếu chính sách cần tách biệt từng thiết bị, cần định danh session/device và quy trình thu hồi riêng. Không dùng chung một refresh token cho mọi thiết bị nếu việc thu hồi và phát hiện reuse cần hoạt động độc lập.

### 9.2. Scope và resource khi refresh

Khi client yêu cầu Access Token mới bằng refresh token, phạm vi quyền không được tự mở rộng vượt authorization grant ban đầu. Theo OAuth 2.0, nếu yêu cầu scope mới được gửi, nó phải không bao gồm scope ngoài phạm vi đã được cấp. Authorization Server cũng cần kiểm tra resource/audience theo chính sách và có thể yêu cầu consent hoặc xác thực lại khi cần.

Refresh token không phải cách nâng quyền. Nó tiếp tục một grant hiện có theo điều kiện mà Authorization Server đang quản lý.

## 10. Lưu trữ refresh token ở client

Refresh token thường sống lâu hơn Access Token nên cần được bảo vệ chặt hơn. Kẻ tấn công lấy được refresh token có thể liên tục xin Access Token mới cho tới khi token bị thu hồi, hết hạn hoặc bị ràng buộc ngăn sử dụng.

Nguyên tắc lưu trữ:

- Chỉ lưu ở nơi cần thiết và giới hạn tiến trình/thành phần có thể đọc.
- Không ghi token vào log, URL, lịch sử trình duyệt, analytics hoặc crash report.
- Bảo vệ dữ liệu khi lưu và khi truyền.
- Dùng kho lưu trữ bảo mật phù hợp với nền tảng.
- Xóa credential khi logout, thu hồi hoặc khi session không còn hợp lệ.
- Cập nhật refresh token mới sau rotation và loại bỏ token cũ.
- Tránh nhiều bản sao hoặc nhiều tiến trình cùng dùng một refresh token đã rotation.

Trong ứng dụng trình duyệt, lưu refresh token dài hạn ở nơi JavaScript có thể đọc làm tăng tác động của XSS. Kiến trúc Backend-for-Frontend (BFF) có thể giữ token ở server và dùng cookie phiên được bảo vệ cho trình duyệt. Nếu dùng cookie, vẫn phải thiết kế CSRF protection, SameSite, Secure, HttpOnly và phạm vi cookie phù hợp.

Ứng dụng native nên dùng kho lưu trữ credential bảo mật của hệ điều hành thay vì file hoặc preference không được bảo vệ. Dù nền tảng nào, không coi mã hóa local bằng một secret được đóng gói sẵn trong ứng dụng là biện pháp bảo vệ đầy đủ.

## 11. Nếu refresh token được biểu diễn bằng JWT

JWT refresh token là một lựa chọn triển khai, không phải yêu cầu OAuth. Nếu chọn mô hình này, cần định nghĩa một **token profile riêng** để không nhầm refresh token với Access Token, ID Token hoặc assertion khác.

### 11.1. Phân biệt profile và mục đích

Một profile JWT refresh token có thể quy định:

- Issuer là Authorization Server được tin cậy.
- Subject/client/grant mà token đại diện.
- Audience hoặc recipient giới hạn ở Authorization Server/Token Endpoint theo hợp đồng.
- Loại token rõ ràng, ví dụ một typ riêng được các bên thống nhất; không giả định có giá trị typ chuẩn phổ quát cho mọi refresh token.
- Claims thời gian và thời hạn tuyệt đối/không hoạt động.
- jti hoặc token identifier.
- Grant/session/token-family identifier nếu cần quản lý vòng đời.
- Client hoặc sender binding.
- Scope/resource tối đa được phép tiếp tục cấp.

Ví dụ minh họa:

~~~json
{
  "iss": "https://identity.example.org/",
  "sub": "user-123",
  "aud": "https://identity.example.org/token",
  "typ": "example-refresh-token",
  "jti": "rt-unique-9f32",
  "iat": 1893456000,
  "exp": 1896048000,
  "client_id": "web-client-01",
  "grant_id": "grant-92ab",
  "family_id": "family-7d31"
}
~~~

Các tên và giá trị trong ví dụ là thiết kế minh họa, không phải claims bắt buộc hoặc một profile tiêu chuẩn chung. Không dùng typ minh họa này như một giá trị interoperable nếu chưa có hợp đồng.

### 11.2. Xác minh JWT refresh token

Khi nhận JWT refresh token, Authorization Server cần:

1. Chọn policy refresh-token từ Token Endpoint và client context tin cậy.
2. Parse token có giới hạn; xem header/claims trước xác minh là chưa tin cậy.
3. Kiểm tra thuật toán trong allowlist và chọn khóa tin cậy theo issuer.
4. Xác minh chữ ký hoặc authenticated decryption bằng thư viện JOSE phù hợp.
5. Kiểm tra issuer, audience/recipient, token type/profile và claims bắt buộc.
6. Kiểm tra exp, nbf, iat, maximum age và các giới hạn vòng đời.
7. Kiểm tra client/grant/session/family binding.
8. Kiểm tra trạng thái active, revocation và reuse.
9. Thực hiện rotation nguyên tử nếu refresh thành công.

Chữ ký hợp lệ chỉ chứng minh token được ký bằng khóa tương ứng. Nó không chứng minh token chưa bị thu hồi, chưa bị sử dụng lại hoặc vẫn thuộc một grant active.

### 11.3. JWT vẫn cần trạng thái khi có rotation/revocation

Nếu Authorization Server muốn phát hiện reuse, nó phải biết jti/family nào đã được tiêu thụ hoặc thu hồi. Một JWT self-contained không tự nhớ rằng client đã dùng nó ở request trước.

Có thể lưu:

- jti đã tiêu thụ hoặc đã thu hồi.
- Token family và token hiện hành.
- Phiên bản grant hoặc token version.
- Trạng thái session/client.
- Thời điểm rotation và quan hệ token cũ/mới.

Nếu không có trạng thái, một JWT refresh token có thể bị phát lại nhiều lần trong thời hạn hiệu lực. Điều này làm mất một lợi ích quan trọng của rotation.

### 11.4. Không dùng chung validator với Access Token

Ngay cả khi cả hai đều là JWT và cùng issuer:

- Access Token được Resource Server nhận.
- Refresh Token được Authorization Server nhận.
- Audience, token type, claims, lifetime và policy khác nhau.
- Resource Server không nên chấp nhận refresh-token profile.
- Token Endpoint không nên nhận Access Token như refresh token.

Phải có validator loại trừ lẫn nhau theo mục đích. Không chấp nhận một JWT chỉ vì chữ ký đúng và có exp.

## 12. Refresh token opaque và JWT: so sánh lựa chọn

| Tiêu chí | Opaque/reference refresh token | JWT refresh token |
| --- | --- | --- |
| Dữ liệu client nhìn thấy | Chuỗi không mang cấu trúc có ý nghĩa với client | JWT có serialization nhận diện được |
| Kiểm tra cơ bản | Tra cứu trạng thái server-side | Xác minh JOSE và claims |
| Thu hồi | Cập nhật bản ghi trạng thái | Vẫn cần trạng thái hoặc cơ chế tương đương nếu muốn thu hồi trước exp |
| Rotation/reuse detection | Tự nhiên gắn với bản ghi và token family | Cần lưu jti/family/consumption state |
| Lộ thông tin | Có thể giảm metadata lộ ra ngoài | Claims có thể đọc được nếu JWS không mã hóa |
| Khả năng xác minh phân tán | Thường cần truy cập trạng thái | Có thể xác minh chữ ký phân tán, nhưng lifecycle vẫn có thể cần trạng thái |
| Độ phức tạp | Quản lý kho token và lookup | Quản lý JOSE, claims, khóa và trạng thái vòng đời |
| Phù hợp thường gặp | Hệ thống cần kiểm soát rotation/revocation tập trung | Hệ thống có profile và lý do rõ ràng cho credential self-contained |

Không có lựa chọn nào tự động an toàn trong mọi tình huống. Opaque token vẫn có thể bị đánh cắp; JWT vẫn có thể cần database và cơ chế revocation. Hãy chọn dựa trên yêu cầu vòng đời, kiến trúc, khả năng vận hành và mô hình đe dọa.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Nghĩ mọi refresh token đều là JWT | Thiết kế phụ thuộc vào claims/parse không cần thiết | Phân biệt vai trò token với định dạng |
| Nghĩ Access Token JWT thì Refresh Token cũng phải JWT | Chọn sai mô hình chỉ để đồng nhất serialization | Chọn opaque/JWT theo nhu cầu lifecycle |
| Gửi refresh token tới Resource Server | Credential có thể bị dùng sai mục đích | Chỉ gửi tới Token Endpoint |
| Chấp nhận Access Token ở refresh_token parameter | Nhầm lẫn credential và grant | Validator riêng, token type riêng |
| JWT refresh chỉ kiểm tra chữ ký | Token đã bị thu hồi hoặc replay vẫn được chấp nhận | Kiểm tra state, family và binding |
| Opaque token entropy thấp | Có thể bị đoán/brute force | CSPRNG và entropy cao |
| Lưu raw refresh token trong database/log | Rò rỉ database/log trở thành chiếm phiên | Lưu verifier, bảo vệ log và kho dữ liệu |
| Không rotation hoặc không phát hiện reuse cho public client | Token bị đánh cắp có thể dùng lại lâu dài | Sender constraint hoặc rotation theo RFC 9700 |
| Rotation không nguyên tử | Hai request cùng tiêu thụ một token | Transaction/atomic update |
| Không thu hồi token family khi reuse | Kẻ tấn công có thể tiếp tục dùng token mới trong family | Reuse detection và family revocation |
| Chỉ thu hồi refresh token khi logout nhưng tuyên bố mọi access token hết hiệu lực | Access Token đã cấp vẫn có thể hoạt động | Xác định riêng access-token revocation |
| Dùng sliding expiration vô hạn | Credential có thể tồn tại không giới hạn | Absolute lifetime và re-authentication policy |
| Dùng chung refresh token cho nhiều thiết bị | Khó thu hồi và phát hiện bất thường theo thiết bị | Tách session/family theo thiết bị khi cần |

## 14. Kiểm thử vòng đời refresh token

| Nhóm | Ca kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| Phân loại | Access Token gửi tới Token Endpoint như refresh token | Từ chối |
| Phân loại | Refresh Token gửi tới Resource Server | Từ chối |
| Opaque token | Token đúng, sai, ngẫu nhiên, quá dài, bị sửa | Chỉ token có bản ghi/verifier hợp lệ được tiếp tục |
| JWT token | Chữ ký sai, issuer/audience/type sai, exp hết hạn | Từ chối |
| Client binding | Client khác dùng refresh token | Từ chối |
| Rotation | Refresh token active được dùng lần đầu | Cấp Access Token và token thay thế theo policy |
| Reuse | Token cũ đã rotation được gửi lại | Phát hiện reuse và xử lý family theo policy |
| Concurrency | Hai request dùng cùng token đồng thời | Chỉ một lần tiêu thụ thành công |
| Expiration | Absolute expiry và idle timeout | Từ chối đúng ranh giới |
| Revocation | Logout, admin revoke, client revoke, grant revoke | Không thể refresh tiếp |
| Failure | Database/rotation store lỗi giữa giao dịch | Không để trạng thái token cũ/mới mâu thuẫn |
| Storage | Log, analytics, crash report | Không có raw refresh token |
| Sender constraint | DPoP/mTLS proof đúng và sai | Chỉ proof gắn đúng client/key được chấp nhận |
| Scope | Yêu cầu scope rộng hơn grant ban đầu | Từ chối hoặc giới hạn theo grant |
| Token family | Reuse token cũ trong family đã rotation | Thu hồi token hiện hành theo chính sách |

Kiểm thử đồng thời và lỗi giữa giao dịch rất quan trọng. Một triển khai có thể hoạt động đúng trong test tuần tự nhưng vẫn cho phép hai request cùng refresh một token nếu thao tác trạng thái không nguyên tử.

## 15. Checklist thiết kế và vận hành

1. [ ] Phân biệt rõ vai trò refresh token với định dạng JWT.
2. [ ] Xác định refresh token opaque hay JWT dựa trên yêu cầu thực tế.
3. [ ] Chỉ gửi refresh token tới Authorization Server/Token Endpoint qua TLS.
4. [ ] Không chấp nhận refresh token tại Resource Server hoặc dùng Access Token làm refresh token.
5. [ ] Ràng buộc token với client, grant, subject và session theo policy.
6. [ ] Token opaque được tạo bằng CSPRNG với entropy cao; storage không giữ raw token nếu không cần.
7. [ ] Đặt absolute expiration, idle expiration và giới hạn token family phù hợp.
8. [ ] Dùng rotation và reuse detection cho public client theo RFC 9700, hoặc sender-constrain refresh token.
9. [ ] Cập nhật trạng thái rotation nguyên tử và xử lý request đồng thời.
10. [ ] Có cơ chế thu hồi token, family, session hoặc grant khi logout/sự cố.
11. [ ] Hiểu rằng thu hồi refresh token không tự động làm Access Token đã cấp hết hiệu lực.
12. [ ] Nếu dùng JWT refresh token, định nghĩa profile riêng, audience/recipient, type, issuer và claims bắt buộc.
13. [ ] JWT refresh token vẫn được kiểm tra revocation, reuse và family state khi policy yêu cầu.
14. [ ] Không dùng chung validator Access Token và Refresh Token.
15. [ ] Client lưu refresh token trong kho bảo mật, không ghi log hoặc để lộ qua URL.
16. [ ] Có kiểm thử replay, rotation, concurrency, expiry, revocation và client binding.

## 16. Tài liệu tiêu chuẩn liên quan

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Section 1.5 định nghĩa refresh token; Section 6 mô tả sử dụng refresh token tại Token Endpoint và quy tắc scope.
- **RFC 7009 — OAuth 2.0 Token Revocation:** cơ chế yêu cầu Authorization Server thu hồi token.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ refresh token, rotation, reuse detection và sender-constrained refresh token cho public client.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** cơ chế sender constraint bằng proof-of-possession.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** xác thực client và ràng buộc token với chứng thư.
- **RFC 7519 — JSON Web Token (JWT):** định dạng JWT và registered claims; không quy định mọi refresh token phải là JWT.
- **RFC 8725 — JSON Web Token Best Current Practices:** thực hành xác minh JWT và tách biệt token profile.

**Nguyên tắc ghi nhớ:** Refresh token là credential để xin Access Token mới; JWT chỉ là một định dạng có thể dùng để biểu diễn credential đó. Opaque refresh token thường phù hợp khi cần kiểm soát vòng đời tập trung. Nếu chọn JWT, vẫn phải có policy riêng và trạng thái cần thiết cho rotation, replay detection, revocation và client binding. 
