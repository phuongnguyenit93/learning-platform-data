# OAuth giữa service — Xác thực client và cấp quyền truy cập giữa các dịch vụ

> **Chương:** Service authentication  
> **Chủ đề:** OAuth giữa service  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào xác thực và cấp quyền cho giao tiếp service-to-service bằng OAuth 2.0: danh tính client, Client Credentials Grant, phương thức xác thực client, access token, scope, audience, vòng đời token và cách resource server kiểm tra quyền.

## 1. OAuth giữa service là gì?

**OAuth giữa service (service-to-service OAuth)** là cách một ứng dụng hoặc workload đại diện cho chính nó lấy access token từ Authorization Server (AS), rồi dùng token đó để gọi API của một Resource Server (RS). Không có người dùng cuối trực tiếp tham gia vào mỗi lần gọi; service client xác thực danh tính của chính nó với AS theo phương thức đã đăng ký.

Ví dụ, dịch vụ **order-service** cần gọi **inventory-service** để kiểm tra số lượng hàng. **order-service** gửi yêu cầu tới token endpoint bằng danh tính client đã đăng ký. AS xác minh client, kiểm tra scope được cấp và phát access token có audience dành cho **inventory-api**. **order-service** gửi token tới inventory API. Resource server xác minh token và policy, rồi chỉ cho phép thao tác đọc tồn kho trong phạm vi đã cấp.

Luồng này thường dùng **OAuth 2.0 Client Credentials Grant**. Client không đại diện cho một người dùng; token thể hiện quyền của ứng dụng/workload theo hợp đồng giữa client, AS và resource server.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả vai trò client, Authorization Server và Resource Server trong service-to-service OAuth.
2. Phân biệt xác thực client tại token endpoint với authorization tại API.
3. Triển khai đúng Client Credentials Grant cho confidential client.
4. So sánh client secret, private_key_jwt, mutual TLS và workload identity federation.
5. Thiết kế scope và audience theo nguyên tắc least privilege.
6. Phân biệt opaque token với JWT access token và xác minh từng loại đúng cách.
7. Quản lý token lifetime, rotation, revocation, caching và secret storage.
8. Phân biệt machine identity với delegated user identity và OIDC login.
9. Phòng chống token theft, replay, confused deputy và privilege escalation.
10. Xây dựng kiểm thử và giám sát cho giao tiếp giữa các service.

## 2. Các vai trò trong OAuth service-to-service

| Vai trò | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Client** | Service cần gọi API; xác thực với AS và yêu cầu token | order-service |
| **Authorization Server (AS)** | Xác minh client, áp dụng policy và phát access token | Identity platform |
| **Resource Server (RS)** | Nhận token, xác minh token và thực thi authorization | inventory-api |
| **Resource owner** | Chủ thể có quyền trên tài nguyên; trong Client Credentials không nhất thiết là người dùng đang đăng nhập | Tổ chức sở hữu inventory |
| **Client registry** | Lưu client identity, credential, grant và policy | Đăng ký order-service với AS |

Tên gọi “client” không có nghĩa là browser hoặc người dùng cuối. Trong flow này, client là một service có danh tính và credential được quản lý.

AS và RS có thể là hai hệ thống tách biệt hoặc hai thành phần của cùng nền tảng. Dù triển khai thế nào, trách nhiệm vẫn cần rõ: AS quyết định token được cấp cho client nào và resource server quyết định token có đủ quyền cho request cụ thể hay không.

## 3. Xác thực client khác authorization như thế nào?

Service-to-service OAuth có ít nhất hai quyết định:

1. **Client authentication tại AS:** client chứng minh nó kiểm soát credential đã đăng ký, ví dụ secret, private key hoặc client certificate.
2. **Authorization tại RS:** resource server kiểm tra access token có hợp lệ, dành cho API này và chứa quyền đủ cho action/resource đang yêu cầu hay không.

Ví dụ, order-service xác thực thành công với AS. Điều đó không có nghĩa nó được phép gọi mọi API. AS có thể chỉ cấp scope inventory.read; order-service không được dùng token này để gọi inventory.adjust hoặc payments.refund.

OAuth 2.0 là framework ủy quyền. Trong Client Credentials Grant, token thường biểu diễn quyền của client/workload. Không nên mô tả access token này như một bằng chứng đăng nhập của người dùng cuối. Nếu cần đăng nhập và xác thực người dùng, cần flow phù hợp với OpenID Connect hoặc cơ chế user authentication khác.

## 4. Khi nào dùng Client Credentials Grant?

Client Credentials phù hợp khi:
- service gọi API bằng quyền của chính workload;
- không có người dùng cuối cần consent hoặc được đại diện trong request;
- client có thể bảo vệ credential ở backend hoặc môi trường thực thi được quản lý;
- AS có thể cấp scope/audience riêng cho workload;
- vòng đời và ownership của client identity được quản trị.

Ví dụ:
- billing-worker gọi invoice-api để tạo hóa đơn theo lịch;
- report-service đọc dữ liệu tổng hợp từ analytics-api;
- CI/CD workload yêu cầu token ngắn hạn để triển khai vào một môi trường được phép;
- notification-service gọi API gửi thông báo với scope giới hạn.

Không dùng Client Credentials chỉ vì nó dễ triển khai nếu request thực chất cần quyền của người dùng đang đăng nhập. Nếu hành động phải được quy cho user, phải chọn delegated flow hoặc token exchange có ràng buộc user context phù hợp.

## 5. Luồng Client Credentials Grant

Flow chuẩn ở mức khái niệm:

~~~mermaid
sequenceDiagram
    participant C as order-service (Client)
    participant AS as Authorization Server
    participant RS as inventory-api (Resource Server)
    C->>AS: POST /token + client authentication + grant_type
    AS->>AS: Xác minh client và policy
    AS->>AS: Kiểm tra grant, scope và resource
    AS-->>C: Access token ngắn hạn
    C->>RS: API request + Bearer access token
    RS->>RS: Xác minh token, audience, scope và trạng thái
    RS-->>C: Chỉ trả dữ liệu/hành động được phép
~~~

Các bước:
1. Client lấy credential từ secret manager, key store hoặc workload identity provider.
2. Client kết nối tới token endpoint qua TLS.
3. Client gửi grant_type=client_credentials và xác thực bằng phương thức đã đăng ký.
4. AS xác minh client, trạng thái, grant được phép, resource/audience và scope.
5. AS phát access token có lifetime và quyền phù hợp.
6. Client gửi token tới resource server qua TLS.
7. RS xác minh token theo loại token và policy.
8. RS kiểm tra quyền trên API/resource rồi thực thi hoặc từ chối.

Client không gửi password của người dùng trong flow này. Không có authorization code hoặc redirect browser như Authorization Code Flow.

## 6. Đăng ký client và tạo service identity

Trước khi lấy token, mỗi workload cần có một danh tính client được quản trị. Client registration nên xác định:

- client_id duy nhất trong phạm vi AS;
- owner/team chịu trách nhiệm;
- môi trường và workload được phép sử dụng;
- grant type được phép, ví dụ chỉ client_credentials;
- phương thức client authentication;
- scope tối đa có thể yêu cầu;
- resource/audience được phép;
- token lifetime và policy;
- trạng thái active/disabled;
- ngày tạo, expiry/review date và quy trình rotate/revoke.

Ví dụ registry:

~~~json
{
  "client_id": "order-service-prod",
  "owner": "commerce-platform",
  "environment": "production",
  "grant_types": ["client_credentials"],
  "token_endpoint_auth_method": "private_key_jwt",
  "allowed_scopes": ["inventory.read"],
  "allowed_resources": ["https://inventory.example.internal"],
  "status": "ACTIVE"
}
~~~

Đây là cấu trúc minh họa, không phải schema bắt buộc. Không dùng chung một client ID/secret cho mọi service hoặc mọi môi trường. Nếu staging và production dùng cùng credential, compromise ở staging có thể mở đường tới production.

### Một service, một identity có thể quản trị

Tách client identity theo workload và trust boundary:
- order-service-prod khác order-service-staging;
- worker có quyền đọc khác worker có quyền điều chỉnh;
- service chạy trong tenant hoặc account khác nhau có thể cần identity riêng;
- workload tạm thời nên dùng credential ngắn hạn hoặc federation thay vì secret lâu dài.

Không cấp một client platform-admin dùng chung cho nhiều service chỉ để giảm công sức vận hành.

## 7. Client authentication bằng client secret

Một cách đơn giản là AS cấp client_id và client_secret. Client dùng secret để xác thực tại token endpoint, thường qua HTTP Basic theo cấu hình đăng ký (client_secret_basic).

Ví dụ minh họa:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.internal
Authorization: Basic <base64(client_id:client_secret)>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.read
~~~

Base64 không phải mã hóa bảo mật. TLS bảo vệ secret khi truyền; client phải bảo vệ secret khi lưu và sử dụng.

Nguyên tắc:
- lưu secret trong secret manager hoặc vault;
- không nhúng secret vào source code, image, manifest public hoặc mobile app;
- không truyền secret qua query string;
- không log request header hoặc body chứa secret;
- giới hạn quyền đọc secret theo workload identity;
- có rotation, overlap window và revoke;
- tách secret theo môi trường và client;
- dùng secret có entropy cao do hệ thống tạo.

Client secret là bearer-like shared secret: ai lấy được secret có thể giả mạo client tới AS. Với môi trường có khả năng bảo vệ private key hoặc workload identity, cân nhắc phương thức mạnh hơn.

## 8. private_key_jwt: client chứng minh quyền kiểm soát private key

Với private_key_jwt, client tạo JWT client assertion và ký bằng private key. AS xác minh chữ ký bằng public key đã đăng ký hoặc JWKS được cấu hình tin cậy.

Assertion thường có các claim:
- iss: client identifier;
- sub: client identifier;
- aud: token endpoint hoặc audience AS được quy định;
- iat: thời điểm phát hành;
- exp: thời điểm hết hạn ngắn;
- jti: định danh duy nhất để phát hiện replay.

AS cần xác minh issuer/subject, audience, thời hạn, thuật toán được phép, key ID và replay policy. Assertion cần lifetime ngắn và jti được xử lý một lần trong cửa sổ hợp lệ.

Lợi ích:
- client không gửi private key;
- không phải chia sẻ cùng secret giữa client và AS;
- public key có thể được quản lý và rotate;
- phù hợp với backend có key store/HSM.

Giới hạn:
- private key bị lộ vẫn cho phép giả mạo client;
- cần quản trị key, JWKS, rotation và revoke;
- JWT assertion không tự giới hạn quyền API; AS vẫn quyết định scope/resource của access token.

## 9. Mutual TLS và certificate-bound access token

Với **mutual TLS (mTLS)**, client và server xác thực chứng chỉ trong TLS handshake. AS có thể dùng client certificate để xác thực client tại token endpoint. Một số triển khai còn ràng buộc access token với certificate public key để token chỉ dùng được khi client trình bày đúng certificate tương ứng.

Hai chức năng cần phân biệt:
- **mTLS client authentication:** certificate chứng minh client kiểm soát private key của chứng chỉ được AS tin cậy.
- **Certificate-bound token:** resource server kiểm tra token được ràng buộc với certificate của kết nối API.

mTLS có thể giảm nguy cơ token bearer bị đánh cắp rồi dùng từ một máy khác, nhưng cần:
- CA/trust store được quản trị;
- kiểm tra certificate path, validity, EKU và revocation;
- bảo vệ private key;
- rotation trước expiry;
- mapping certificate identity sang client identity;
- cấu hình proxy/service mesh để không làm mất hoặc giả mạo thông tin certificate.

Không tin một header X-Client-Cert từ request bất kỳ. Nếu TLS kết thúc tại proxy, chỉ tin metadata certificate được proxy xác thực và truyền qua channel nội bộ đã bảo vệ.

## 10. Workload identity federation

Workload identity federation cho phép service đổi một identity assertion từ môi trường thực thi thành OAuth access token mà không cần giữ client secret dài hạn.

Ví dụ, một workload trên cloud có thể nhận identity token ngắn hạn từ nền tảng. Client gửi token này tới AS hoặc broker đã cấu hình trust. Hệ thống xác minh issuer, subject, audience, thời hạn và điều kiện workload, sau đó phát access token cho resource được phép.

~~~mermaid
sequenceDiagram
    participant W as Workload
    participant IDP as Cloud/Platform Identity Provider
    participant AS as Token Broker / AS
    participant API as Target API
    W->>IDP: Yêu cầu workload identity token
    IDP-->>W: Short-lived signed identity assertion
    W->>AS: Token exchange / federation request
    AS->>AS: Verify issuer, subject, audience, expiry and trust policy
    AS-->>W: Short-lived OAuth access token
    W->>API: API request + access token
    API->>API: Validate token and authorize action
~~~

Federation policy nên giới hạn:
- issuer cụ thể;
- subject hoặc workload identity pattern chính xác;
- audience dành cho broker;
- namespace, service account, project/account hoặc environment;
- thời hạn assertion;
- resource và scope được cấp.

Không tin mọi token do một issuer phát hành. Trust policy quá rộng có thể cho workload không liên quan đổi token thành quyền production.

## 11. Yêu cầu token và scope

Client Credentials token request thường dùng application/x-www-form-urlencoded:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.internal
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication>

grant_type=client_credentials&scope=inventory.read
~~~

AS chỉ nên cấp các scope:
- client đã được phép yêu cầu;
- phù hợp với resource/audience;
- được policy và owner phê duyệt;
- cần thiết cho nhiệm vụ cụ thể.

Scope là biểu diễn quyền theo hợp đồng AS/RS. Không phải tên scope nào cũng có semantics chung. inventory.read trong hệ thống này có thể khác hệ thống khác; cần tài liệu hóa hành động và tài nguyên tương ứng.

Không cho client tự yêu cầu scope tùy ý rồi cấp toàn bộ. Nếu scope không hợp lệ hoặc vượt quyền, AS từ chối hoặc chỉ cấp tập quyền được policy cho phép theo hợp đồng đã định.

## 12. Audience và resource binding

Scope mô tả loại quyền; **audience** xác định token dành cho resource server nào. Một token cấp cho inventory-api không nên được chấp nhận ở payments-api chỉ vì cùng issuer.

Ví dụ:
- client: order-service-prod;
- audience/resource: https://inventory.example.internal;
- scope: inventory.read.

AS cần ràng buộc token với resource theo cấu hình. RS cần xác minh aud hoặc cơ chế resource binding tương ứng. Nếu token không có audience đúng, từ chối.

Không dùng một access token đa audience cho toàn bộ microservice nếu không có lý do và đánh giá rủi ro rõ ràng. Audience rộng làm tăng tác động khi token bị lộ và có thể tạo confused deputy.

## 13. Access token: opaque và JWT

Access token có thể là:

| Loại | Đặc điểm | Cách resource server kiểm tra |
| --- | --- | --- |
| **Opaque token** | Chuỗi không mang claims có thể đọc trực tiếp | Gọi introspection endpoint hoặc cơ chế tra cứu trạng thái được AS hỗ trợ |
| **JWT access token** | Token có claims được ký | Xác minh chữ ký và claims theo profile/token contract |

Opaque token giúp AS giữ quyền kiểm soát trạng thái tập trung, nhưng introspection tạo phụ thuộc network/availability. JWT có thể được xác minh cục bộ nhanh hơn, nhưng việc revoke tức thời khó hơn nếu RS không kiểm tra trạng thái bổ sung.

Không coi mọi JWT là access token. ID Token, client assertion và access token có mục đích khác nhau. Resource server chỉ chấp nhận loại token được thiết kế cho API và audience của nó.

## 14. Xác minh JWT access token ở Resource Server

Nếu AS phát JWT access token, RS cần xác minh ít nhất các yếu tố theo profile và hợp đồng:

1. Chữ ký hợp lệ bằng key từ issuer tin cậy.
2. Thuật toán nằm trong allowlist; không tin alg do token tự chọn.
3. iss đúng issuer đã cấu hình.
4. aud bao gồm resource server hiện tại.
5. exp chưa hết hạn và nbf đã tới nếu có.
6. iat nằm trong giới hạn hợp lý theo policy.
7. Token type/profile đúng loại access token.
8. Scope/authorization details đủ cho action.
9. Client/service principal được phép gọi endpoint.
10. Revocation, account/client status hoặc token version được kiểm tra nếu policy yêu cầu.

Không chỉ decode JWT rồi tin claims. Không lấy URL JWKS tùy ý từ token header; JWKS URI phải đến từ cấu hình issuer tin cậy hoặc metadata đã xác minh. Key rotation cần xử lý kid chưa biết, cache và refresh JWKS an toàn.

Ví dụ claims minh họa:

~~~json
{
  "iss": "https://auth.example.internal",
  "sub": "client:order-service-prod",
  "aud": ["https://inventory.example.internal"],
  "client_id": "order-service-prod",
  "scope": "inventory.read",
  "iat": 1795340400,
  "exp": 1795341000
}
~~~

Claim format phụ thuộc authorization server và access-token profile. Không mặc định mọi issuer dùng sub theo cùng cách; resource server cần mapping client identity theo hợp đồng đã xác minh.

## 15. Introspection cho opaque token và kiểm tra trạng thái

Với opaque token, resource server có thể gọi introspection endpoint của AS. Response thường cho biết token có active không và có thể chứa scope, client, subject, audience, expiry hoặc metadata theo cấu hình.

RS cần:
- xác thực chính nó khi gọi introspection;
- gọi đúng endpoint của issuer tin cậy;
- kiểm tra active và các thuộc tính cần thiết;
- cache response trong thời gian phù hợp với revocation SLA;
- xử lý AS timeout theo fail-safe policy;
- không log raw token trong request/response.

Cache quá lâu có thể khiến token đã revoke vẫn được chấp nhận. Không cache active status lâu hơn cửa sổ rủi ro cho API nhạy cảm. Nếu AS không khả dụng, không mặc định token active chỉ vì lần kiểm tra trước đã thành công.

## 16. Scope, role và quyền trên resource

Access token thường mang scope hoặc authorization claims, nhưng RS vẫn phải kiểm tra policy trên tài nguyên.

Ví dụ:
- inventory.read cho phép đọc tồn kho trong phạm vi API;
- token không tự cho phép đọc mọi warehouse nếu client chỉ được gán warehouse cụ thể;
- inventory.adjust có thể cần role/approval riêng;
- payments.refund cần policy khác và không nên nằm trong token cấp cho inventory.

Tách:
- **Scope:** quyền API được AS cấp cho client;
- **Role/entitlement:** quan hệ quyền trong ứng dụng hoặc tenant;
- **Resource ownership:** service có được thao tác trên đối tượng cụ thể không;
- **Business rule:** trạng thái nghiệp vụ có cho phép hành động không.

Không dùng scope như admin chung nếu có thể định nghĩa quyền nhỏ hơn. Không để RS suy ra quyền từ client_id mà bỏ qua token validation và policy.

## 17. Client Credentials không phải delegated user flow

Client Credentials thể hiện quyền của client/workload. Nếu service cần gọi API thay mặt người dùng, cần flow delegated phù hợp, ví dụ Authorization Code Flow ở client tương tác, hoặc token exchange/on-behalf-of theo nền tảng và hợp đồng được cấu hình.

| Nhu cầu | Mô hình phù hợp |
| --- | --- |
| Worker đọc dữ liệu của chính service | Client Credentials |
| Backend gọi API theo quyền của user đã đăng nhập | Delegated token/on-behalf-of hoặc token exchange |
| Người dùng đăng nhập và RP nhận thông tin xác thực | OpenID Connect |
| Service cần xác thực workload bằng certificate | mTLS/client certificate kết hợp OAuth theo policy |

Không tự gắn user_id do client gửi vào token để giả lập delegated authorization. Nếu quyền phụ thuộc người dùng, AS phải xác minh user context và resource server phải biết token đang đại diện cho ai, client nào, audience nào và scope nào.

## 18. Token exchange và chuỗi service

Trong kiến trúc nhiều service, một service có thể nhận token cho API A rồi cần gọi API B. Không nên chuyển tiếp token ban đầu một cách mù quáng tới mọi downstream service.

Các lựa chọn:
- cấp token riêng có audience B;
- dùng OAuth Token Exchange nếu AS hỗ trợ và policy cho phép;
- dùng client identity riêng của service gọi B nếu hành động thuộc quyền workload;
- giữ delegated user context nếu hành động thực sự thay mặt user.

Token exchange cần giới hạn subject token, actor, audience, scope và thời hạn. Resource server B cần biết token được cấp cho nó và policy nào cho phép actor thực hiện hành động. Tránh biến service trung gian thành confused deputy có thể dùng token rộng để truy cập mọi tài nguyên.

## 19. Token lifetime, cache và refresh

Access token nên có thời hạn phù hợp với mức rủi ro và cách resource server kiểm tra trạng thái. Token quá dài làm tăng cửa sổ sử dụng nếu bị đánh cắp; token quá ngắn có thể gây tải lớn lên AS và ảnh hưởng availability.

Với Client Credentials:
- client có thể lấy access token mới khi token gần hết hạn;
- thường không cần Refresh Token cho flow này; client xác thực lại với AS để lấy token mới;
- cache token theo client, audience/resource và scope;
- không chia sẻ token giữa workload hoặc môi trường có trust boundary khác;
- dùng single-flight/lock để tránh nhiều thread đồng thời lấy token;
- xử lý clock skew và expires_in;
- xóa token khỏi memory/cache khi hết hạn hoặc client bị revoke.

Không refresh bằng cách gửi lại user password. Không tiếp tục dùng token đã hết hạn chỉ vì AS tạm unavailable; fallback phải được policy xác định rõ.

## 20. Bảo vệ access token và client credential

Access token thường là bearer credential: ai sở hữu token có thể sử dụng trong phạm vi token cho phép, trừ khi token được sender-constrained.

Nguyên tắc:
- chỉ truyền qua TLS;
- đặt token trong Authorization: Bearer, không đặt trong URL/query string;
- không log token, secret hoặc assertion;
- không đưa token vào exception, tracing baggage hoặc analytics;
- lưu token trong memory hoặc secure store phù hợp, hạn chế thời gian tồn tại;
- giới hạn quyền truy cập secret manager;
- không bake secret vào container image hoặc source repository;
- rotate client secret/private key/certificate có kế hoạch;
- revoke client khi workload bị compromise;
- phân tách credential giữa production và non-production.

Không gửi access token tới host do client request tùy ý chọn. Khi service gọi downstream URL, cần allowlist destination và chống SSRF/token exfiltration.

## 21. Sender-constrained token: giảm replay khi token bị đánh cắp

Bearer token có thể bị replay từ một máy khác nếu attacker lấy được token trước khi hết hạn. Một số cơ chế có thể ràng buộc token với proof/key của client:

- **mTLS-bound access token:** token gắn với certificate public key; RS kiểm tra client certificate trong kết nối.
- **DPoP:** client tạo proof JWT ký bằng key và token có thể được ràng buộc với key thumbprint theo profile hỗ trợ.

Sender-constrained token giảm khả năng dùng token bị copy đơn thuần, nhưng không giải quyết mọi tình huống:
- attacker có cả token và private key vẫn có thể dùng;
- malware trong workload có thể yêu cầu key ký;
- proxy termination và key forwarding có thể làm mất binding;
- replay protection cần kiểm tra proof, thời gian và request binding theo protocol.

Chỉ triển khai DPoP hoặc mTLS-bound token khi AS, client và RS hỗ trợ cùng một profile; không tự thêm header tùy ý rồi gọi đó là sender-constrained.

## 22. Workload, service mesh và ranh giới tin cậy

Service mesh có thể cung cấp mTLS giữa workload, identity certificate ngắn hạn và policy ở proxy. OAuth access token có thể bổ sung quyền ở mức API/action.

Hai lớp có mục tiêu khác nhau:
- mTLS/service identity chứng minh workload peer kiểm soát certificate/key trong kết nối;
- OAuth token diễn tả quyền được AS cấp cho client đối với resource;
- application authorization kiểm tra action/resource cụ thể.

Không cho rằng mTLS tự động thay thế authorization. Hai service có thể kết nối TLS hợp lệ nhưng client vẫn không có scope để gọi endpoint quản trị. Ngược lại, token hợp lệ cũng không nhất thiết chứng minh peer là workload dự kiến nếu token là bearer và không ràng buộc với kết nối.

## 23. Những lỗi và kiểu tấn công thường gặp

| Lỗi/tấn công | Cách xảy ra | Phòng vệ |
| --- | --- | --- |
| Client secret hardcode | Secret lộ qua source/image/log | Secret manager, scanning, rotation |
| Dùng chung client identity | Compromise một service ảnh hưởng nhiều service | Identity riêng theo workload/environment |
| Scope quá rộng | Token dùng được cho hành động không cần thiết | Least privilege, scope nhỏ và review |
| Audience quá rộng | Token bị dùng ở API khác | Resource/audience binding |
| Token theft | Log, trace hoặc memory dump lộ bearer token | Redaction, TLS, short TTL, sender constraint |
| Token replay | Attacker gửi lại bearer token | TTL ngắn, revoke, mTLS/DPoP khi phù hợp |
| JWT chỉ decode | Không xác minh chữ ký/issuer/audience | Token validation đầy đủ |
| Thuật toán JWT tùy ý | Attacker lợi dụng algorithm confusion | Allowlist thuật toán và thư viện chuẩn |
| JWKS/key confusion | Tin key URL/header không đáng tin | Issuer metadata và JWKS cấu hình tin cậy |
| Client impersonation | Dùng secret/key bị lộ | Strong client auth, rotation, revoke |
| Confused deputy | Service dùng token rộng cho request ngoài mục đích | Audience, scope, actor/resource binding |
| SSRF token exfiltration | Service gửi token tới URL attacker kiểm soát | Destination allowlist, egress control |
| Federation trust quá rộng | Workload ngoài phạm vi đổi token | Issuer/subject/audience condition chính xác |
| Token cache sai key | Token của resource/scope này dùng cho resource khác | Cache key gồm client, audience, scope |
| AS outage fail-open | RS chấp nhận token không xác minh được | Fail-safe theo risk và token profile |
| Không revoke refresh/token family | Client tiếp tục lấy token sau compromise | Revoke client/token family và incident response |

## 24. Lỗi và response handling

Client và RS cần xử lý lỗi rõ ràng:
- invalid_client: client authentication không hợp lệ; không retry vô hạn.
- invalid_scope: scope không được phép; sửa cấu hình/policy thay vì tự xin scope rộng hơn.
- invalid_request hoặc unsupported_grant_type: request sai hoặc grant không được hỗ trợ.
- invalid_token: RS từ chối token hết hạn, sai audience hoặc không hợp lệ.
- insufficient_scope: token hợp lệ nhưng không đủ quyền cho endpoint.
- timeout/5xx ở AS: retry có backoff và jitter; tránh tạo request storm.
- timeout introspection: áp dụng fail-safe policy; không tự coi token active.

Không đưa client secret hoặc access token vào error message. Không retry invalid_client liên tục; có thể báo hiệu credential đã rotate/revoke hoặc cấu hình sai.

## 25. Observability và audit

Có thể ghi:
- client ID/service principal;
- AS issuer và token endpoint identifier;
- grant type;
- audience/resource và scope đã cấp;
- credential method (secret, private key, mTLS, federation);
- token issuance time, expiry và key/certificate reference;
- request correlation ID;
- RS decision, endpoint/action và reason code;
- token introspection/revocation outcome;
- client registration, key rotation và revoke events.

Không log:
- client secret;
- private key;
- raw client assertion;
- access token/refresh token;
- mTLS private key material;
- toàn bộ Authorization header.

Metrics nên theo dõi token issuance rate, invalid client, invalid scope, token validation failure, audience mismatch, introspection latency, token cache hit/miss, rotation failure, federation denial và RS authorization decision. Phân tích theo client/resource nhưng không lưu secret.

## 26. Pseudocode lấy token và gọi API

Ví dụ Java khái niệm:

~~~java
AccessToken getServiceToken(
        ClientIdentity client,
        ResourceId resource,
        Set<Scope> requestedScopes) {

    TokenCacheKey key = new TokenCacheKey(
        client.id(), resource.value(), canonicalize(requestedScopes));

    return tokenCache.getOrLoad(key, () -> {
        ClientAssertion auth = clientAuthenticator.createAssertion(client);

        TokenResponse response = tokenClient.request(
            tokenEndpointFor(client.issuer()),
            "client_credentials",
            auth,
            resource,
            requestedScopes);

        tokenResponseVerifier.requireExpectedIssuerAndResource(
            response, client.issuer(), resource);

        return AccessToken.from(
            response.accessToken(),
            response.expiresIn(),
            response.tokenType());
    });
}
~~~

Ví dụ resource server:

~~~java
ApiResponse readInventory(HttpRequest request) {
    AccessToken token = bearerTokenExtractor.require(request);

    VerifiedAccessToken verified =
        accessTokenVerifier.verifyForAudience(
            token, "https://inventory.example.internal");

    authorizationPolicy.requireScope(verified, "inventory.read");
    authorizationPolicy.requireClientAllowed(
        verified.clientIdentity(), "inventory.read");

    return inventoryService.readAllowedItems(verified);
}
~~~

Đây là pseudocode minh họa, không phải API thư viện cụ thể. Production cần:
- dùng OAuth client/token library đã được kiểm chứng;
- không tự xây JWT signing/validation;
- xác minh response schema và token_type;
- cache theo client + resource/audience + scope;
- kiểm tra token expiry trước khi sử dụng;
- xử lý secret/key rotation và AS outage;
- RS kiểm tra signature/introspection, issuer, audience, expiry, scope và policy;
- không tin client_id hoặc scope do request header tự khai.

## 27. Kiểm thử service-to-service OAuth

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Client hợp lệ yêu cầu Client Credentials | AS phát token theo scope/resource policy. |
| Client secret sai | AS trả lỗi xác thực client; không cấp token. |
| Client đã disabled/revoked | AS từ chối token request. |
| Grant type không được đăng ký | AS từ chối. |
| Scope vượt quyền | AS từ chối hoặc chỉ cấp phần được policy cho phép theo contract. |
| Resource/audience không được phép | AS từ chối. |
| private_key_jwt chữ ký sai | AS từ chối assertion. |
| Client assertion hết hạn | AS từ chối. |
| jti assertion bị replay | AS từ chối trong replay window. |
| mTLS certificate không tin cậy/hết hạn | TLS/client authentication thất bại. |
| Federation issuer không tin cậy | Token exchange bị từ chối. |
| Federation subject/audience sai | Token exchange bị từ chối. |
| JWT access token chữ ký sai | RS từ chối. |
| JWT issuer sai | RS từ chối. |
| JWT audience dành cho API khác | RS từ chối. |
| JWT hết hạn hoặc chưa tới nbf | RS từ chối. |
| JWT dùng thuật toán ngoài allowlist | RS từ chối. |
| Opaque token inactive | RS từ chối. |
| Introspection endpoint timeout | RS áp dụng fail-safe policy, không tự coi token active. |
| Scope hợp lệ nhưng endpoint yêu cầu scope khác | RS trả insufficient scope/deny. |
| Token bị gửi tới API khác | Audience check ngăn chấp nhận. |
| Bearer token bị copy | Sender constraint/revocation/TTL giới hạn khả năng sử dụng theo thiết kế. |
| Token cache dùng sai audience | Test phát hiện cache key thiếu resource binding. |
| Client secret bị rotate | Token request mới dùng credential mới; credential cũ bị thu hồi theo overlap policy. |
| Token hết hạn trong lúc request | RS áp dụng expiry policy; client lấy token mới theo flow. |
| AS rate limit hoặc 5xx | Client backoff/jitter; không tạo request storm. |
| Client identity staging gọi production API | RS/AS từ chối do audience/scope/client policy. |
| Client Credentials được dùng thay user delegation | Architecture/security review phát hiện sai mô hình principal. |
| Log/tracing review | Không có secret, assertion, access token hoặc Authorization header. |

## 28. Bài tập tình huống

Một hệ thống có ba service: orders, inventory và payments. Đội phát triển tạo một OAuth client tên backend-admin, dùng chung client secret trong cả ba container. AS cấp token có scope api.admin và không ràng buộc audience. Mọi API chỉ decode JWT, không xác minh chữ ký hoặc issuer. Token có thời hạn 24 giờ và được ghi trong log khi request lỗi.

**Yêu cầu phân tích:**

1. Vì sao một client identity dùng chung làm tăng blast radius?
2. Vì sao scope api.admin và audience rộng vi phạm least privilege?
3. Resource server phải xác minh JWT những gì?
4. Nên tách client identity và scope cho từng service như thế nào?
5. Khi nào dùng private_key_jwt, mTLS hoặc workload identity federation?
6. Nếu token bị lộ, cần revoke và rotate những gì?
7. Làm sao bảo đảm orders không dùng token để gọi API quản trị payments?
8. Những test nào chứng minh token chỉ được dùng đúng resource và action?

**Hướng phân tích:** Tạo client identity riêng theo service và môi trường; cấp scope nhỏ như inventory.read hoặc payments.refund.request theo owner approval. AS ràng buộc audience từng API. RS xác minh signature, issuer, audience, expiry, token type và scope. Dùng secret manager hoặc private key/mTLS/federation theo môi trường; không ghi token vào log. Khi compromise, revoke client/credential và token family, rotate key/secret, kiểm tra log và giảm TTL. Thêm test cross-audience, insufficient scope, client disabled và token replay.

## 29. Checklist review

- [ ] Mỗi workload có client identity riêng theo trust boundary và môi trường.
- [ ] Client Credentials chỉ dùng khi service hành động bằng quyền của chính nó.
- [ ] Client được đăng ký là confidential client và chỉ được phép dùng grant cần thiết.
- [ ] Client authentication method được chọn và quản trị rõ ràng.
- [ ] Secret/private key/certificate không nằm trong source, image hoặc log.
- [ ] Secret/key rotation, expiry và revoke có quy trình.
- [ ] Token request dùng TLS và không truyền credential qua URL.
- [ ] Scope được giới hạn theo nhiệm vụ và resource.
- [ ] Audience/resource binding được cấu hình và kiểm tra ở RS.
- [ ] RS xác minh token đầy đủ; không chỉ decode JWT.
- [ ] Opaque token introspection có cache/revocation SLA rõ.
- [ ] Token lifetime phù hợp; Client Credentials không dựa vào refresh token không cần thiết.
- [ ] Token cache key bao gồm client, audience/resource và scope.
- [ ] Bearer token được bảo vệ khỏi log, trace, URL và exfiltration.
- [ ] Sender-constrained token được dùng khi threat model yêu cầu và mọi thành phần hỗ trợ.
- [ ] Federation trust policy giới hạn issuer, subject, audience và workload.
- [ ] Service-to-service mTLS không bị nhầm với application authorization.
- [ ] Delegated user flow được tách khỏi Client Credentials.
- [ ] Downstream token exchange giữ đúng subject, actor, audience và scope.
- [ ] AS/RS outage, retry, rate limit và fail-safe behavior được kiểm thử.
- [ ] Audit ghi client/resource/action và decision mà không chứa secret/token.

## 30. Ghi nhớ

**OAuth giữa service cho phép một workload xác thực với Authorization Server để nhận access token đại diện cho quyền của chính client, rồi dùng token đó gọi đúng Resource Server.** Client Credentials Grant phù hợp khi không có user context cần đại diện. AS xác minh client và cấp scope/resource; RS xác minh token và quyết định quyền trên action/resource cụ thể.

Thiết kế an toàn cần identity riêng cho từng workload, client authentication được bảo vệ, scope nhỏ, audience chính xác, token lifetime ngắn phù hợp, revocation/rotation có quy trình và không để token rò vào log. Khi review, hãy hỏi: **Service nào đang gọi? Nó chứng minh identity bằng credential nào? AS cấp quyền gì và cho audience nào? RS xác minh token ra sao? Token bị copy có thể bị replay không? Nếu client hoặc workload bị compromise, có thể revoke toàn bộ đường truy cập nhanh đến mức nào?**
