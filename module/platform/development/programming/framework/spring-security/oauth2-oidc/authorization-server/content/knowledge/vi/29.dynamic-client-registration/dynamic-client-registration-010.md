# Quản lý vòng đời client đã đăng ký động và bảo vệ bí mật đăng ký

## 1. Vì sao Dynamic Client Registration cần quản lý vòng đời?

**Dynamic Client Registration (DCR)** cho phép một OAuth 2.0 Client hoặc nhà phát triển gửi metadata tới Authorization Server (AS) để tạo client registration mà không cần quản trị viên nhập từng trường thủ công. AS cấp `client_id`, có thể cấp `client_secret` và lưu cấu hình như redirect URI, grant type, scope, token endpoint authentication method và public key location.

Tạo registration chỉ là bước đầu. Một client có thể đổi redirect URI, cập nhật tên/metadata, thay secret, bị lộ credential, chuyển chủ sở hữu, ngừng hoạt động hoặc cần bị thu hồi. Nếu không có vòng đời rõ ràng, registration cũ có thể tồn tại vô hạn, secret không được thay, quyền cũ vẫn còn và người vận hành không biết ai đang quản lý client đó.

Bài thuộc chương **Đăng ký client động** của module `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`. Mục tiêu là thiết kế cách quản lý client đã đăng ký động và bảo vệ các credential liên quan trong ứng dụng Spring Boot, Spring Security và Spring Authorization Server (SAS).

Sau bài học, bạn cần:
1. Phân biệt client registration, client credential, Initial Access Token và Registration Access Token.
2. Hiểu vòng đời create, read, update, rotate, suspend, revoke và deprovision.
3. Áp dụng RFC 7591 và RFC 7592 đúng phạm vi.
4. Bảo vệ `client_secret` và `registration_access_token` từ lúc cấp tới lúc thu hồi.
5. Bật và tùy chỉnh OIDC Client Registration Endpoint trong SAS.
6. Nhận biết phần SAS 1.5.8 hỗ trợ mặc định và phần cần tự mở rộng.
7. Thiết kế secret rotation không làm gián đoạn client, xử lý sự cố và kiểm thử vòng đời.

## 2. Những định danh và credential phải phân biệt

| Giá trị | Ai cấp? | Dùng ở đâu? | Quyền hạn / tính chất |
| --- | --- | --- | --- |
| `client_id` | AS | Authorization Endpoint, Token Endpoint và API liên quan | Định danh client, thường là giá trị công khai |
| `client_secret` | AS, nếu client là confidential | Client Authentication tại Token Endpoint | Xác thực client; không phải khóa quản lý registration |
| **Initial Access Token (IAT)** | AS hoặc registrar được quản trị cấp | Client Registration Endpoint | Cho phép tạo registration mới; có thể là token dùng một lần |
| **Registration Access Token (RAT)** | AS sau khi đăng ký | Client Configuration Endpoint | Bearer credential quản lý một registration cụ thể |
| `registration_client_uri` | AS | Client Configuration Endpoint | URL đầy đủ để đọc/quản lý registration; client phải dùng nguyên URL được cấp |
| `software_statement` | Software publisher hoặc bên attestation | Client Registration Endpoint | JWT ký xác nhận metadata phần mềm; chỉ đáng tin khi issuer được AS tin cậy |

**IAT và RAT không phải cùng một token.** IAT cho phép gọi thao tác tạo client. RAT gắn với một registration đã tồn tại và cho phép truy cập cấu hình client theo management protocol. `client_secret` lại dùng để xác thực client tại Token Endpoint. Không dùng RAT thay client secret và không dùng client secret để gọi Client Configuration Endpoint.

### 2.1. Hai loại bearer credential có sức ảnh hưởng lớn

~~~text
Initial Access Token
  Quyền đăng ký client mới
  Authorization: Bearer INITIAL_ACCESS_TOKEN

Registration Access Token
  Quyền quản lý một client cụ thể
  Authorization: Bearer REGISTRATION_ACCESS_TOKEN
~~~

Cả hai đều là bearer credential: người có token có thể thực hiện thao tác được token cho phép. IAT bị lộ có thể dẫn đến đăng ký client trái phép; RAT bị lộ có thể dẫn đến đọc, thay đổi hoặc xóa registration tương ứng nếu AS hỗ trợ các thao tác đó.

## 3. Vòng đời client registration

Không nên coi registration là một bản ghi chỉ tạo một lần rồi bỏ quên. Cần quản lý trạng thái client và trạng thái credential riêng:

~~~mermaid
stateDiagram-v2
    [*] --> Pending: Nhận yêu cầu đăng ký
    Pending --> Active: Policy và metadata hợp lệ
    Pending --> Rejected: Không đạt policy
    Active --> Active: Đọc hoặc cập nhật metadata
    Active --> RotationPending: Đến hạn / nghi ngờ lộ secret
    RotationPending --> Active: Client xác nhận credential mới
    Active --> Suspended: Tạm dừng client
    Suspended --> Active: Khôi phục sau đánh giá
    Active --> Revoked: Thu hồi do sự cố hoặc vi phạm
    Suspended --> Revoked: Không khôi phục
    Revoked --> Deprovisioned: Xóa registration và credential
    Rejected --> [*]
    Deprovisioned --> [*]
~~~

| Trạng thái | Ý nghĩa | Hành động cần có |
| --- | --- | --- |
| Pending | Đang kiểm tra registration | Giữ ở vùng chờ, chưa cấp quyền rộng |
| Active | Client được phép hoạt động | Theo dõi owner, metadata, secret expiry và usage |
| Rotation pending | Đang thay credential | Phối hợp deploy secret mới và vô hiệu secret cũ |
| Suspended | Tạm ngừng sử dụng | Chặn authorization/token theo policy, giữ audit record |
| Revoked | Credential hoặc client bị thu hồi | Vô hiệu RAT/secret và xử lý token/grant liên quan |
| Deprovisioned | Registration đã bị xóa | Không còn chấp nhận client_id hoặc credential |

SAS `RegisteredClient` biểu diễn metadata client, nhưng trạng thái Pending/Suspended/Revoked và workflow phê duyệt thường cần thuộc tính hoặc kho quản lý của ứng dụng. Không nên giả định chỉ cần xóa một dòng trong `RegisteredClientRepository` là mọi access token, refresh token, authorization grant và cache ở các hệ thống khác lập tức biến mất.

## 4. RFC 7591 và RFC 7592 giải quyết phần nào?

| Tài liệu | Trạng thái | Phạm vi |
| --- | --- | --- |
| **RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol** | Standards Track | Tạo client registration, client metadata, software statement và Client Information Response |
| **RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol** | Experimental | Đọc, cập nhật và xóa registration đã tạo; dùng Registration Access Token |

RFC 7591 mô tả cách client gửi HTTP POST tới Client Registration Endpoint. AS kiểm tra metadata, cấp `client_id` và có thể cấp secret. RFC 7592 mở rộng vòng đời bằng Client Configuration Endpoint với các phương thức GET, PUT và DELETE.

**RFC 7592 là Experimental RFC**, không phải Standards Track. Vì vậy, phải xác nhận cả AS lẫn client hỗ trợ các thao tác management trước khi dựa vào chúng trong hợp đồng vận hành. Không phải AS nào có DCR cũng hỗ trợ update/delete hoặc credential rotation.
## 5. Đăng ký client ban đầu theo RFC 7591

### 5.1. Bảo vệ Client Registration Endpoint

Client Registration Endpoint nhận HTTP POST với JSON metadata. Endpoint **MUST** được bảo vệ bằng transport-layer security. AS có thể:
- Cho phép open registration không cần IAT, nhưng nên áp rate limit, quota và kiểm soát lạm dụng.
- Yêu cầu IAT do quy trình quản trị cấp ngoài băng.
- Yêu cầu `software_statement` được ký bởi software publisher hoặc bên attestation được tin cậy.
- Kết hợp IAT, software statement và metadata để quyết định có chấp nhận registration hay không.

Không cấp IAT vô thời hạn cho mọi caller chỉ để làm DCR dễ tích hợp. IAT nên có audience/endpoint phù hợp, thời hạn ngắn hoặc giới hạn số lần sử dụng, và quyền tạo registration được giới hạn theo tenant/partner/software.

### 5.2. Metadata request minh họa

~~~http
POST /connect/register HTTP/1.1
Host: auth.example.com
Authorization: Bearer INITIAL_ACCESS_TOKEN
Content-Type: application/json
Accept: application/json

{
  "client_name": "Portal Web",
  "redirect_uris": [
    "https://portal.example.com/login/oauth2/code/portal"
  ],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "client_secret_basic",
  "scope": "openid profile email"
}
~~~

Đây là metadata client mong muốn. AS có quyền từ chối hoặc thay một số giá trị bằng policy/default của mình. Không được hiểu rằng mọi trường client gửi đều tự động trở thành cấu hình được chấp nhận.

### 5.3. Kiểm tra metadata trước khi cấp client_id

AS cần kiểm tra tối thiểu:
- `redirect_uris` là absolute URI, dùng HTTPS trong production và không trùng với endpoint không thuộc quyền kiểm soát của client.
- `grant_types` và `response_types` là tổ hợp được phép; không cấp flow yếu hoặc không được hỗ trợ.
- `token_endpoint_auth_method` phù hợp loại client. Public client không thể giữ bí mật chỉ bằng cách nhúng secret vào app.
- `scope` nằm trong tập scope được policy cho client/tenant.
- `jwks_uri` hoặc `jwks` nếu dùng private_key_jwt phải qua validation và trust policy.
- `client_uri`, `logo_uri`, `policy_uri`, `tos_uri` là metadata tự khai; cần kiểm soát nội dung/host trước khi hiển thị.
- `software_id`, `software_version` và `software_statement` nếu có phải được kiểm tra theo trust relationship đã cấu hình.

Metadata tự khai không chứng minh người gửi sở hữu domain, logo hoặc phần mềm có tên tương ứng. Một software statement được ký cũng chỉ là assertion của issuer; AS vẫn phải tin issuer đó và đánh giá toàn bộ registration request.

### 5.4. Software Statement

Software Statement là JWT ký hoặc MAC, chứa claims mô tả phần mềm client. Khi sử dụng:
1. Xác minh chữ ký bằng key của issuer đã được tin cậy.
2. Kiểm tra `iss`, thời hạn và các claim bắt buộc theo profile của tổ chức.
3. Kiểm tra `software_id`, `software_version` và metadata liên quan.
4. Nếu metadata JSON mâu thuẫn với claim trong statement, áp dụng quy tắc ưu tiên của RFC 7591 và policy.
5. Không xem chữ ký hợp lệ là bằng chứng tuyệt đối rằng binary đang chạy là phần mềm được khai báo.

## 6. Client Information Response và bảo vệ credential

Response thành công của RFC 7591 thường dùng HTTP `201 Created` và JSON. Ví dụ rút gọn:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "client_id": "portal-client-8f31",
  "client_id_issued_at": 1794800000,
  "client_secret": "ONE_TIME_CLIENT_SECRET",
  "client_secret_expires_at": 1797392000,
  "registration_access_token": "REGISTRATION_ACCESS_TOKEN",
  "registration_client_uri": "https://auth.example.com/connect/register/portal-client-8f31",
  "redirect_uris": [
    "https://portal.example.com/login/oauth2/code/portal"
  ],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "client_secret_basic"
}
~~~

Các giá trị trong ví dụ chỉ minh họa. `client_secret` có thể không được cấp nếu client là public hoặc dùng phương thức xác thực khác. `client_secret_expires_at` là NumericDate theo UTC; giá trị `0` biểu thị secret không hết hạn trong RFC 7591. Nếu có secret expiry, AS cần công bố và thực thi thời hạn đó.

Response chứa credential phải được gửi qua TLS và có `Cache-Control: no-store`, `Pragma: no-cache`. Client cần lưu credential ngay vào kho bí mật phù hợp; không đưa response vào log, telemetry, ticket, browser storage hoặc source control.

### 6.1. Phân biệt client_id và client_secret

- `client_id` là định danh client, không phải password. Nó có thể xuất hiện trong authorization request và log theo policy.
- `client_secret` là credential của confidential client. Phải giữ kín và chỉ gửi tới đúng AS/token endpoint theo authentication method đã đăng ký.
- `client_secret_expires_at` là mốc thời gian, không phải thời lượng tính từ lúc đọc response.
- `registration_access_token` là quyền quản lý registration, có thể mạnh hơn quyền client secret.
- `registration_client_uri` là endpoint quản lý; không tự dựng URL từ `client_id`.

Không ghi nguyên response registration vào application log chỉ để “debug”. Nếu cần audit, lưu client ID, owner, metadata version, timestamp và outcome; không lưu raw secret hoặc bearer token.

## 7. Initial Access Token và Registration Access Token

### 7.1. Initial Access Token

IAT được dùng để gọi Client Registration Endpoint khi AS yêu cầu protected registration. IAT có thể được cấp qua portal quản trị, onboarding partner hoặc một quy trình ngoài băng.

Trong Spring Authorization Server 1.5.8, hướng dẫn DCR sử dụng registrar client đã được cấu hình sẵn với:
- Grant type `client_credentials`.
- Scope `client.create` để tạo client.
- Scope `client.read` nếu registrar cần đọc registration.

IAT dùng để đăng ký cần access token chỉ có scope `client.create`; SAS guide nêu token này chỉ được dùng một lần và bị vô hiệu sau khi registration thành công. Đây là cơ chế của triển khai SAS trong hướng dẫn, không phải yêu cầu chung rằng mọi IAT theo RFC 7591 đều phải dùng một lần.

### 7.2. Registration Access Token

RAT được AS cấp cùng thông tin registration. Theo RFC 7592, đây là Bearer Token dùng tại Client Configuration Endpoint. Nó được gắn với một `client_id` và phải xuất hiện trong mọi request quản lý registration.

RAT có thể cho phép holder:
- Đọc metadata hiện tại.
- Thay metadata bằng PUT nếu AS hỗ trợ.
- Xóa registration bằng DELETE nếu AS hỗ trợ.

RAT không dùng tại Token Endpoint để xác thực client. Không chia sẻ một RAT cho nhiều instance/tenant không liên quan: một instance bị compromise có thể thay đổi hoặc xóa registration chung.

### 7.3. Ví dụ Client Read

Dùng đúng URL do AS trả về:

~~~http
GET /connect/register/portal-client-8f31 HTTP/1.1
Host: auth.example.com
Authorization: Bearer REGISTRATION_ACCESS_TOKEN
Accept: application/json
~~~

Client phải dùng `registration_client_uri` được cấp nguyên vẹn. RFC 7592 không yêu cầu client tự nối path hoặc suy URL từ issuer và `client_id`.

Nếu RAT không hợp lệ, AS trả lỗi Bearer Token tương ứng. Nếu registration đã bị deprovision, các RAT còn lại phải bị vô hiệu; không để token quản lý vẫn xác thực thành công sau khi client đã bị xóa.

## 8. Đọc, cập nhật và xóa registration theo RFC 7592

### 8.1. GET — đọc cấu hình hiện tại

GET dùng RAT để lấy metadata hiện đang được AS lưu. Response có thể chứa giá trị mới của `client_secret` hoặc `registration_access_token`. Nếu AS cấp credential mới trong response, client **MUST** lập tức loại bỏ credential cũ và dùng credential mới cho các lần tiếp theo.

Một số AS không trả lại RAT mới ở mỗi lần read. Client không được tự giả định token đã đổi nếu response không cấp token mới.

### 8.2. PUT — cập nhật toàn bộ metadata

RFC 7592 sử dụng HTTP PUT với JSON chứa **toàn bộ metadata hiện tại** của client. Đây không phải PATCH chỉ gửi vài field muốn thay đổi.

Các quy tắc quan trọng:
- Request phải chứa `client_id` hiện tại.
- Metadata gửi lên thay thế metadata trước đó, không tự động merge.
- Field bị bỏ khỏi request được xử lý như null/empty để yêu cầu xóa, tùy policy AS.
- Request không được tự gửi `registration_access_token`, `registration_client_uri`, `client_secret_expires_at` hoặc `client_id_issued_at`.
- Nếu gửi `client_secret`, giá trị phải khớp secret hiện tại; client không được tự chọn secret mới để ghi đè. AS là bên quyết định cấp credential mới.

`client_id` phải giữ nguyên qua các lần read/update. Nếu response có `client_secret` hoặc RAT mới, client phải bỏ credential cũ và chuyển sang credential mới theo đúng contract của AS.

Client phải giữ lại tất cả metadata muốn tiếp tục sử dụng. Nếu quên gửi một redirect URI, nó có thể bị xóa khỏi registration sau PUT.

### 8.3. DELETE — deprovision client

DELETE tại Client Configuration Endpoint được xác thực bằng RAT. Thành công trả HTTP `204 No Content`. AS phải vô hiệu `client_id`, `client_secret` và RAT của registration. RFC 7592 còn khuyến nghị AS thu hồi authorization grants, access tokens, refresh tokens và các token liên quan nếu có thể.

Deprovision cần được hiểu là chấm dứt registration. Việc chỉ xóa metadata nhưng giữ nguyên credential hoặc RAT sẽ tạo trạng thái không nhất quán và mở đường truy cập ngoài dự kiến.
## 9. Bảo vệ client_secret trong suốt vòng đời

### 9.1. Chọn đúng loại client

| Loại client | Có thể giữ bí mật? | Cách xác thực phù hợp |
| --- | --- | --- |
| Server-side web application | Có, nếu secret chỉ ở backend | `client_secret_basic`, `private_key_jwt`, mTLS |
| Service-to-service workload | Có, nếu có secret/key storage được quản lý | `private_key_jwt`, mTLS hoặc secret theo policy |
| Browser SPA | Không thể giữ secret bền vững | Public client, Authorization Code + PKCE |
| Native mobile/desktop app | Không thể giữ secret dùng chung trong binary | Public client, Authorization Code + PKCE |
| Device/CLI cài trên máy người dùng | Thường không thể giữ secret dùng chung | Public client hoặc cơ chế proof-of-possession phù hợp |

Không cấp client secret cho SPA/mobile với suy nghĩ minify/obfuscate sẽ bảo vệ được. Mọi secret nhúng trong binary hoặc JavaScript đều có thể bị trích xuất.

### 9.2. Sinh secret có entropy cao

Với confidential client dùng shared secret, AS nên sinh secret bằng CSPRNG. Ví dụ Java:

~~~java
static String generateClientSecret() {
    byte[] random = new byte[32]; // 256 bit
    SecureRandom secureRandom = new SecureRandom();
    secureRandom.nextBytes(random);

    return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(random);
}
~~~

Đây là một ví dụ sinh chuỗi ngẫu nhiên; entropy thực tế phụ thuộc CSPRNG và số byte. Không dùng UUID v1, timestamp, client ID, username hoặc chuỗi có thể đoán làm client secret.

RFC 7591 yêu cầu secret được cấp phải unique cho từng `client_id` và khuyến nghị secret riêng giữa nhiều instance của cùng một client. Không dùng một secret dùng chung cho nhiều ứng dụng/tenant chỉ vì chúng cùng một nhà phát triển.

### 9.3. Lưu trữ phía Authorization Server

Trong Spring Authorization Server, `RegisteredClient.clientSecret` nên được mã hóa bằng `PasswordEncoder` trước khi lưu. Không dùng `{noop}` ở production.

~~~java
RegisteredClient registeredClient = RegisteredClient.withId(internalId)
        .clientId(clientId)
        .clientSecret(passwordEncoder.encode(rawClientSecret))
        .clientSecretExpiresAt(secretExpiresAt)
        .build();
~~~

Đoạn code chỉ minh họa cách tạo metadata; các giá trị `internalId`, `clientId`, `rawClientSecret` và `secretExpiresAt` phải được tạo/kiểm tra bởi registration service. Không log object `RegisteredClient` nếu có thể làm lộ encoded credential hoặc metadata nhạy cảm.

`PasswordEncoder` là cơ chế one-way: AS không thể khôi phục raw secret từ hash để hiển thị lại. Nếu management API cần trả một secret mới, phải tạo secret mới, lưu verifier/hash và trả raw secret mới đúng một lần theo contract; tuyệt đối không trả encoded hash như thể đó là credential có thể dùng tại Token Endpoint. Với Client Read, chỉ trả secret hiện tại nếu implementation thực sự có cách bảo vệ và cung cấp đúng raw credential; nếu không, thiết kế thao tác rotate riêng.

### 9.4. Lưu trữ phía client

Client phải lưu secret trong:
- Secret manager hoặc vault của môi trường triển khai.
- Kubernetes Secret được mã hóa at rest và phân quyền truy cập phù hợp.
- Hệ thống quản lý secret của cloud/runtime.
- OS keychain hoặc secure enclave khi mô hình ứng dụng hỗ trợ.

Tránh lưu trong:
- Git, Docker image layer hoặc file cấu hình đã commit.
- Browser localStorage/sessionStorage.
- Log, APM trace, crash report hoặc analytics.
- Chat, email và ticket không có cơ chế quản lý bí mật.
- Biến môi trường nếu hệ thống có thể đọc/dump rộng rãi; nếu dùng, cần kiểm soát process, debug và runtime permissions.

### 9.5. Bảo vệ Registration Access Token

RAT thường sống lâu hơn access token thông thường vì nó dùng để quản lý registration. RFC 7592 khuyến nghị không để RAT tự hết hạn khi client vẫn đang active nếu điều đó có thể khóa client khỏi việc đọc/cập nhật/xóa registration. AS có thể xoay RAT khi client thực hiện read/update.

Do đó:
- RAT cần entropy cao, TLS và bảo vệ như một credential đặc quyền.
- Không đặt RAT vào browser, URL, query string, source code hoặc log.
- Lưu RAT tách biệt client secret và chỉ cho phép management service đọc.
- Không chia sẻ RAT giữa các client instance không cùng quyền sở hữu.
- Thu hồi mọi RAT khi client deprovision.
- Có quy trình khôi phục nếu RAT bị mất; không mặc định cấp RAT mới cho người chỉ biết `client_id`.

## 10. Rotation client secret mà không gián đoạn dịch vụ

### 10.1. Khi nào cần rotation?

- Secret sắp đến `client_secret_expires_at`.
- Nhân sự hoặc workload có quyền truy cập secret rời hệ thống.
- Secret xuất hiện trong log, ticket, repository hoặc incident.
- Thay đổi môi trường/tenant/owner.
- Định kỳ theo policy.
- Sau khi chuyển từ shared secret sang `private_key_jwt` hoặc mTLS.

Không đợi tới khi secret chắc chắn bị lạm dụng mới bắt đầu rotation. Cần lịch rotation, owner, thời gian overlap và kiểm thử xác thực trước ngày hết hạn.

### 10.2. Quy trình rotation hai pha

~~~mermaid
sequenceDiagram
    autonumber
    participant AS as Authorization Server
    participant V as Secret Manager
    participant C as Client workload
    participant T as Token Endpoint
    AS->>AS: Sinh secret mới và cập nhật registration
    AS->>V: Ghi secret mới ở version mới
    V-->>C: Cấp secret mới qua workload identity
    C->>T: Xác thực bằng secret mới
    T-->>C: Client authentication thành công
    C->>AS: Báo đã chuyển sang secret mới
    AS->>AS: Thu hồi secret cũ
    AS->>AS: Audit rotation hoàn tất
~~~

Một quy trình triển khai an toàn:
1. Xác định tất cả workload dùng secret cũ.
2. Sinh secret mới và đặt thời điểm hiệu lực.
3. Cập nhật secret mới vào secret manager.
4. Triển khai client đọc version mới.
5. Kiểm thử client authentication tại Token Endpoint.
6. Theo dõi lỗi `invalid_client` và traffic dùng secret cũ.
7. Thu hồi secret cũ sau khi mọi instance đã chuyển hoặc khi incident yêu cầu thu hồi tức thì.
8. Lưu metadata expiry, version, owner và audit event; không lưu raw secret trong audit.

Nếu AS chỉ cho phép một secret active tại một thời điểm, không thể mặc nhiên có overlap hai secret. Để zero-downtime, có thể dùng credential slots/dual-secret validation trong custom authentication provider hoặc chuyển dần sang `private_key_jwt`/mTLS. Đây là extension cần kiểm thử concurrency và rollback.

### 10.3. Rotation theo RFC 7592

RFC 7592 cho phép AS cấp client secret mới và/hoặc RAT mới trong response của Client Read hoặc Client Update. Tần suất rotation do AS quyết định, không phải client tự yêu cầu bằng cách gửi secret tùy chọn.

Khi response trả credential mới:
- Client phải lưu credential mới trước khi bỏ credential cũ.
- Client phải ngừng dùng credential cũ ngay theo semantics của protocol.
- AS nên vô hiệu credential cũ nếu có thể.
- Không gửi secret mới do client tự chọn trong PUT để ghi đè secret hiện hành.

### 10.4. Hết hạn client secret

`client_secret_expires_at` là NumericDate. Trong SAS, `RegisteredClient.Builder.clientSecretExpiresAt(Instant)` biểu diễn thời điểm hết hạn; `null` biểu diễn không có thời điểm hết hạn.

AS phải kiểm tra expiry trong quá trình client authentication, không chỉ hiển thị timestamp cho client. Trước khi hết hạn, gửi cảnh báo tới owner và cung cấp quy trình rotation. Không tự kéo dài expiry bằng cách cập nhật timestamp nếu secret chưa được thay hoặc policy chưa duyệt.

## 11. Thu hồi, suspend và deprovision client

### 11.1. Suspend — tạm ngừng client

Suspend hữu ích khi cần điều tra hoặc chờ owner xác nhận. AS nên:
- Ngăn client lấy token mới.
- Ngăn authorization request mới theo policy.
- Giữ metadata và audit để điều tra.
- Có thể vô hiệu refresh token hoặc session liên quan nếu rủi ro yêu cầu.
- Không xóa ngay registration nếu cần khôi phục.

Trạng thái suspend thường là logic ứng dụng bổ sung, không phải một HTTP method chuẩn của RFC 7591.

### 11.2. Revoke credential

Khi secret hoặc RAT bị lộ:
1. Vô hiệu credential bị lộ ngay.
2. Phát hành credential mới nếu client vẫn được phép hoạt động.
3. Xem xét thu hồi authorization grants và refresh tokens.
4. Xem xét access tokens đang hoạt động; JWT tự chứa có thể vẫn hợp lệ cho tới expiry nếu Resource Server chỉ xác minh chữ ký và thời hạn.
5. Điều tra log, token usage, IP/device và thời điểm credential bị lộ.
6. Thông báo owner theo incident process.

Không chỉ đổi secret rồi bỏ qua refresh token hoặc access token đã phát hành trước đó. Secret rotation bảo vệ lần xác thực client tiếp theo; nó không tự làm mọi token cũ biến mất.

### 11.3. Deprovision

Khi client không còn được sử dụng:
- Xác nhận owner và workload đã dừng.
- Xóa hoặc disable registration theo policy.
- Vô hiệu `client_id`/secret/RAT.
- Thu hồi authorization grants, access/refresh tokens nếu có thể.
- Xóa mapping metadata tùy biến, redirect URI, software statement reference và secret manager entries.
- Giữ audit record theo retention policy.
- Trả lỗi xác thực phù hợp cho request sau khi client bị xóa.

Nếu cần tạo lại ứng dụng, thường nên tạo registration mới với `client_id` mới thay vì tái sử dụng client ID đã deprovision.
## 12. Bật Dynamic Client Registration trong Spring Authorization Server 1.5.8

### 12.1. Endpoint mặc định và điều kiện

Theo tài liệu SAS 1.5.8:
- OIDC Dynamic Client Registration Endpoint **tắt mặc định**.
- Endpoint mặc định là `/connect/register`.
- `OidcClientRegistrationEndpointConfigurer` cấu hình request converter, AuthenticationProvider, response handler và error handler.
- Endpoint dùng OAuth2 Bearer access token.
- Client Registration request cần scope `client.create`.
- Client Read request cần scope `client.read`.
- Một `JwtDecoder` bean là REQUIRED cho endpoint này.

Cấu hình minh họa:

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {
    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .oidc(oidc -> oidc
                .clientRegistrationEndpoint(Customizer.withDefaults())
            )
        )
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        );

    return http.build();
}
~~~

Ứng dụng vẫn cần các bean hạ tầng khác như `RegisteredClientRepository`, `OAuth2AuthorizationService`, token generator, issuer, JWK source, `JwtDecoder` và security chain xử lý login. Không xem đoạn cấu hình trên là một Authorization Server chạy độc lập.

Ví dụ khai báo `JwtDecoder` từ JWK source:

~~~java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

JWK source phải được cấu hình với signing keys của AS. Không dùng khóa private làm JWKS public và không bỏ validation chữ ký/issuer của access token được trình tới registration endpoint.

### 12.2. Cấu hình endpoint path

Có thể đặt path trong `AuthorizationServerSettings`:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .oidcClientRegistrationEndpoint("/connect/register")
            .build();
}
~~~

Nếu thay đổi path, phải cập nhật metadata `registration_endpoint` và client integration tương ứng. Reverse proxy phải công bố external HTTPS URL; không trả host nội bộ cho client.

### 12.3. Cấu hình registrar client

Registrar là một client đã được provision trước, có quyền tạo và đọc registration:

~~~java
RegisteredClient registrar = RegisteredClient.withId("registrar-internal-id")
        .clientId("registrar-service")
        .clientSecret(passwordEncoder.encode(registrarSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("client.create")
        .scope("client.read")
        .build();
~~~

`registrarSecret` phải được cấp từ secret manager; ví dụ không chứa raw secret trong code. Trong production, registrar nên có scope tối thiểu theo công việc. Nếu một registrar chỉ tạo client mà không cần đọc, không cấp `client.read`.

### 12.4. Lấy Initial Access Token

Để đăng ký client, registrar lấy access token chỉ có scope `client.create`:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64(registrar-service:REGISTRAR_SECRET)
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=client.create
~~~

SAS guide yêu cầu token registration chứa đúng scope `client.create`; nếu có thêm scope khác, request registration bị từ chối. Trong flow guide, IAT chỉ dùng một lần và bị vô hiệu sau khi đăng ký thành công.

Để đọc registration, registrar lấy access token riêng có scope `client.read` theo policy/token configuration của ứng dụng. Không dùng token có cả quyền rộng nếu không cần.

### 12.5. Đăng ký và đọc client

Request đăng ký:

~~~http
POST /connect/register HTTP/1.1
Host: auth.example.com
Authorization: Bearer INITIAL_ACCESS_TOKEN
Content-Type: application/json

{
  "client_name": "Orders Portal",
  "redirect_uris": ["https://orders.example.com/login/oauth2/code/portal"],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "client_secret_basic",
  "scope": "openid profile"
}
~~~

Lưu lại `registration_access_token` và `registration_client_uri` từ response trong secret store/management store. Khi cần đọc, gọi GET với RAT:

~~~http
GET https://auth.example.com/connect/register/CLIENT_CONFIGURATION_PATH
Authorization: Bearer REGISTRATION_ACCESS_TOKEN
Accept: application/json
~~~

Trong ví dụ SAS, response của Client Read chứa metadata registration nhưng không có `registration_access_token` mới. Không giả định mỗi lần GET đều tự động rotate RAT; hãy dựa vào response và contract thực tế của AS.

### 12.6. Tùy chỉnh validation của registration

SAS cho phép cấu hình AuthenticationProvider để áp dụng validator phù hợp. Ví dụ dưới đây kết hợp các validator mặc định cho redirect URI, post-logout redirect URI, JWKS URI và scope:

~~~java
private static Consumer<List<AuthenticationProvider>> registrationValidators() {
    return providers -> providers.forEach(provider -> {
        if (provider instanceof OidcClientRegistrationAuthenticationProvider registrationProvider) {
            registrationProvider.setAuthenticationValidator(
                    OidcClientRegistrationAuthenticationValidator.DEFAULT_REDIRECT_URI_VALIDATOR
                            .andThen(OidcClientRegistrationAuthenticationValidator.DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR)
                            .andThen(OidcClientRegistrationAuthenticationValidator.DEFAULT_JWK_SET_URI_VALIDATOR)
                            .andThen(OidcClientRegistrationAuthenticationValidator.SIMPLE_SCOPE_VALIDATOR)
            );
        }
    });
}
~~~

Sau đó truyền consumer này vào `clientRegistrationEndpoint(...).authenticationProviders(...)`. Đây là điểm mở rộng để giữ validator mặc định và bổ sung policy của tổ chức, chẳng hạn allowlist scope, trust tier, redirect domain ownership hoặc software statement. Không thay toàn bộ validator mặc định bằng một kiểm tra đơn giản chỉ xác minh client_name.

### 12.7. Dùng repository bền vững

Ví dụ registrar trong hướng dẫn SAS có thể dùng `InMemoryRegisteredClientRepository` cho demo. Production cần repository bền vững như JDBC hoặc implementation riêng để registration tồn tại qua restart, có backup, transaction và audit. Quản lý update/delete cần có thao tác cập nhật nguyên tử theo internal registration ID; không dựa vào cache hoặc bản sao in-memory làm nguồn sự thật.

## 13. Ranh giới hỗ trợ của SAS và phần cần mở rộng

### 13.1. SAS 1.5.8 hỗ trợ những gì?

Tài liệu SAS 1.5.8 mô tả:
- POST để tạo OIDC Client Registration.
- GET Client Read tại URL được cấp.
- `OidcClientRegistrationEndpointConfigurer` để tùy chỉnh request converter, authentication provider, response handler và error handler.
- `OidcClientRegistrationAuthenticationProvider` để kiểm tra và tạo registration.
- `OidcClientConfigurationAuthenticationProvider` để xử lý Client Read.
- Custom converter để lưu và trả metadata mở rộng.

### 13.2. Không nhầm Client Read với RFC 7592 Management đầy đủ

Hướng dẫn SAS 1.5.8 mô tả **register và retrieve/read** client. Nó không tài liệu hóa default PUT Client Update và DELETE Client Deprovision theo RFC 7592. Do đó:
- Không giả định SAS có sẵn API PUT để đổi redirect URI hoặc secret.
- Không giả định DELETE endpoint tự deprovision client.
- Không quảng cáo capability update/delete trong contract của hệ thống nếu chưa triển khai.
- Nếu cần RFC 7592 đầy đủ, phải xây extension/management service hoặc chọn AS cung cấp đầy đủ protocol.

RFC 7592 cũng là Experimental; cần quyết định rõ có cần interoperability với RFC này hay chỉ cần lifecycle nội bộ.

### 13.3. Kiến trúc management service mở rộng

Một service riêng có thể thực hiện:
1. Xác thực RAT và ràng buộc token với đúng client ID.
2. Kiểm tra owner/tenant và quyền read/update/delete.
3. Validate đầy đủ metadata sau update.
4. Sinh và mã hóa secret mới nếu cần rotation.
5. Persist registration mới theo transaction.
6. Invalidate credential cũ và các authorization/token cần thiết.
7. Phát audit event và trả Client Information Response phù hợp.
8. Khi DELETE, deprovision registration và vô hiệu mọi RAT còn lại.

Không nên viết controller nhận `client_id` rồi cho phép sửa bất kỳ RegisteredClient nào. Management service phải kiểm tra bearer token, audience/resource, registration binding, tenant và operation permission.

### 13.4. Cập nhật RegisteredClient trong kho ứng dụng

`RegisteredClient` có `clientSecret` và `clientSecretExpiresAt`. Builder có thể tạo bản sao registration với secret mới:

~~~java
RegisteredClient replacement = RegisteredClient.from(current)
        .clientSecret(passwordEncoder.encode(newRawSecret))
        .clientSecretExpiresAt(newSecretExpiry)
        .build();
~~~

Đây mới là object cấu hình mới. Phần ghi vào database phải được thực hiện qua repository/persistence implementation của ứng dụng trong transaction, bảo đảm update đúng record theo internal ID và client ID. Không thay client ID khi chỉ rotation secret.

Khi cập nhật các metadata khác, phải thay đổi đúng các field được policy cho phép, chẳng hạn redirect URIs, authentication methods hoặc scopes. Không để client tự nâng grant/scope/authentication method vượt trust tier đã được duyệt.

### 13.5. Custom metadata converter

Nếu cần lưu metadata ngoài `RegisteredClient` chuẩn, SAS cung cấp extension point để tùy chỉnh converter giữa `OidcClientRegistration` và `RegisteredClient`. Ví dụ metadata `logo_uri` hoặc `contacts` có thể được lưu trong `ClientSettings` hoặc một kho metadata riêng.

Chỉ cho phép một allowlist field; không nhận mọi JSON property rồi lưu tùy tiện. Khi Client Read trả metadata, phải loại bỏ field nội bộ, secret hash, token store identifiers và dữ liệu vận hành không thuộc Client Information Response.
## 14. Kiểm soát metadata sau khi client đã active

Registration metadata có thể ảnh hưởng trực tiếp tới bảo mật authorization:
- Thêm redirect URI có thể chuyển authorization code tới một domain mới.
- Thêm grant type có thể mở thêm cách lấy token.
- Thêm scope có thể tăng quyền client được xin.
- Đổi token endpoint authentication method có thể làm client mất hoặc thay đổi cơ chế xác thực.
- Đổi `jwks_uri` có thể thay nguồn public key mà AS dùng xác minh `private_key_jwt`.
- Đổi `post_logout_redirect_uris` có thể ảnh hưởng logout redirect.
- Đổi `client_name` hoặc `logo_uri` có thể ảnh hưởng nội dung consent mà người dùng nhìn thấy.

Vì vậy, update metadata nên có policy theo từng field. Ví dụ:
- Redirect URI thêm mới cần xác minh domain/ownership hoặc approval.
- Grant type và scope tăng quyền cần phê duyệt.
- Authentication method đổi từ shared secret sang private key cần onboarding key.
- Metadata hiển thị người dùng phải qua kiểm tra nội dung.
- Custom claims không được dùng làm quyền bảo mật nếu chưa được validator kiểm tra.

Không cho phép một client tự cập nhật `redirect_uris` tới bất kỳ domain nào chỉ vì RAT hợp lệ. RAT chứng minh quyền quản lý registration; AS vẫn có thể áp policy bổ sung hoặc từ chối update.

## 15. Xử lý sự cố credential bị lộ

Khi nghi ngờ client secret hoặc RAT bị lộ, cần ưu tiên thu hẹp khả năng sử dụng:

1. Xác định loại credential, client ID, tenant, owner và phạm vi quyền.
2. Thu hồi ngay RAT nếu RAT bị lộ; RAT có thể đọc hoặc thay đổi registration.
3. Nếu client secret bị lộ, vô hiệu secret cũ và cấp secret/key mới theo authentication method.
4. Nếu registrar IAT bị lộ, revoke IAT và rà soát các client được tạo trong khoảng thời gian liên quan.
5. Tạm suspend client nếu chưa xác định được mức độ ảnh hưởng.
6. Thu hồi refresh token/grants liên quan và đánh giá access token đang hoạt động.
7. Kiểm tra log Token Endpoint, Registration Endpoint, Client Configuration Endpoint và audit trail.
8. Kiểm tra redirect URI, scopes, grant types, JWKS URI và authentication method có bị thay đổi trái phép.
9. Thông báo owner và triển khai credential mới.
10. Lưu bằng chứng, timestamp, event ID và quyết định xử lý mà không ghi raw credential.

Nếu RAT bị lộ, attacker có thể dùng nó để thay đổi metadata hoặc deprovision client nếu AS hỗ trợ. Vì vậy, incident xử lý RAT có thể nghiêm trọng hơn rotation client secret thông thường.

## 16. Ma trận kiểm thử vòng đời registration

### 16.1. Registration và Client Read

| Test | Hành động | Kết quả mong đợi |
| --- | --- | --- |
| DCR disabled | POST tới registration endpoint khi OIDC DCR tắt | Không cho tạo client |
| Missing IAT | POST không có bearer token trong protected mode | Từ chối |
| Wrong IAT scope | Token không có đúng `client.create` | Từ chối |
| Reuse IAT | Dùng lại IAT đã dùng trong SAS guide flow | Từ chối |
| Invalid redirect URI | Gửi URI không hợp lệ hoặc không qua policy | Registration bị từ chối |
| Unsupported grant | Xin grant không được AS hỗ trợ | Từ chối hoặc thay bằng policy đã công bố |
| Public client secret | Đăng ký client `none` | Không phát secret không cần thiết |
| Confidential client | Đăng ký `client_secret_basic` | Secret được sinh và expiry được công bố |
| Read without RAT | GET Client Configuration không có RAT | Từ chối |
| Read with wrong RAT | RAT của client A dùng cho client B | Từ chối |
| Read wrong scope | Access token thiếu `client.read` | Từ chối |
| Read after delete | GET registration đã deprovision | RAT bị vô hiệu, không đọc được |
| Metadata consistency | So response với RegisteredClient đã lưu | Khớp metadata được chấp nhận |

### 16.2. Update, rotation và delete

| Test | Hành động | Kết quả mong đợi |
| --- | --- | --- |
| PUT incomplete metadata | Bỏ field cần giữ | Hệ thống xử lý đúng semantics full replacement |
| PUT client_id mismatch | Gửi client ID khác | Từ chối |
| PUT secret overwrite | Client gửi secret tự chọn | Từ chối; AS mới là bên cấp secret |
| PUT untrusted redirect | Thêm redirect URI không được duyệt | Từ chối hoặc chờ approval |
| Rotate client secret | AS cấp secret mới | Client dùng secret mới, secret cũ bị vô hiệu theo policy |
| Secret expiry | Dùng secret sau client_secret_expires_at | Client authentication thất bại |
| RAT rotation | AS trả RAT mới | Client dùng RAT mới và loại bỏ RAT cũ |
| RAT revoked | Gọi management bằng RAT cũ | 401 |
| DELETE valid RAT | Deprovision client | 204 và vô hiệu credential/registration |
| DELETE wrong RAT | Dùng RAT của client khác | Từ chối |
| Delete outstanding tokens | Xóa client có refresh/access tokens | Thu hồi theo policy và kiểm tra token behavior |
| Concurrent update | Hai request PUT cùng lúc | Version/locking tránh lost update |
| Concurrent rotation | Hai lần rotation đồng thời | Chỉ credential version hợp lệ được active |
| Retry after timeout | Client không biết update thành công hay chưa | Có idempotency/version strategy, không làm mất secret mới |

Nếu triển khai SAS 1.5.8 chỉ với endpoint mặc định, kiểm thử PUT/DELETE cần xác nhận các method chưa được hỗ trợ thay vì giả định chúng hoạt động. Các test update/delete chỉ áp dụng khi management extension đã được xây dựng.

### 16.3. Kiểm thử bảo mật và vận hành

- Raw client secret không xuất hiện trong log, tracing, metrics hoặc error response.
- RAT và IAT không xuất hiện trong query string, source code hoặc browser storage.
- TLS certificate được xác minh ở registrar/client.
- `Cache-Control: no-store` và `Pragma: no-cache` có mặt trên response chứa credential.
- Client secret được lưu qua `PasswordEncoder`, không dùng `{noop}`.
- Public client không được cấp shared secret nhúng trong app.
- Registrar client chỉ có `client.create` và/hoặc `client.read` theo nhu cầu.
- Software statement sai issuer/chữ ký/expiry bị từ chối.
- Redirect URI, scope, grant type và auth method đều qua validator.
- Deprovision vô hiệu mọi RAT còn tồn tại.
- Token/grant lifecycle được kiểm tra riêng sau khi client bị suspend/revoke/delete.
- Audit ghi client ID, actor, metadata version và outcome nhưng không ghi raw secret.

## 17. Bài tập tình huống

Một doanh nghiệp có registrar service dùng Spring Authorization Server 1.5.8 để đăng ký các client portal theo từng đối tác. Mỗi portal là confidential client dùng `client_secret_basic`. Một client có metadata:

~~~json
{
  "client_id": "partner-portal-7",
  "client_name": "Partner Portal",
  "redirect_uris": ["https://partner.example.com/callback"],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "client_secret_basic",
  "client_secret_expires_at": 1797392000,
  "registration_client_uri": "https://auth.example.com/connect/register/partner-portal-7"
}
~~~

Sự cố:
- Client secret xuất hiện trong log CI.
- RAT được lưu chung trong file cấu hình của nhiều instance.
- Partner muốn đổi redirect URI và rotate secret cùng lúc.
- Đội vận hành gửi PUT tới SAS `/connect/register/partner-portal-7` nhưng nhận method error.
- Client vẫn có refresh token cũ và access token JWT chưa hết hạn.

Hãy phân tích:

1. Secret và RAT có quyền hạn khác nhau thế nào? Token nào cần thu hồi đầu tiên khi RAT bị lộ?
2. Vì sao không nên chia sẻ RAT giữa nhiều instance không liên quan?
3. Làm sao triển khai rotation secret mà không gián đoạn portal?
4. Vì sao SAS 1.5.8 mặc định không xử lý đầy đủ PUT/DELETE theo RFC 7592?
5. Cần mở rộng những service/repository nào để cập nhật metadata và credential?
6. Làm thế nào bảo đảm redirect URI mới thuộc quyền kiểm soát của partner?
7. Sau rotation, refresh token và access token đã phát hành được xử lý ra sao?
8. Thiết kế quy trình deprovision và audit cho client không còn sử dụng.
9. Đề xuất test cho wrong RAT, expired secret, concurrent rotation, update metadata và delete.

**Gợi ý:** IAT tạo registration; RAT quản lý registration; client secret xác thực client ở Token Endpoint. SAS 1.5.8 có DCR POST và Client Read GET, không có management PUT/DELETE được tài liệu hóa mặc định. Cần custom management service hoặc giải pháp AS hỗ trợ RFC 7592. Rotation phải thay secret ở AS và secret store của client theo một quy trình phối hợp; việc thay secret không tự thu hồi token đã phát hành.

## 18. Checklist production

1. **Registration policy:** quyết định open/protected registration, registrar owner, quota, rate limit và approval.
2. **IAT:** cấp riêng theo registrar, scope tối thiểu, giới hạn sử dụng và thu hồi khi nghi lộ.
3. **Metadata validation:** kiểm tra redirect URI, grant, scope, auth method, JWKS và software statement.
4. **Client type:** public client không dùng secret nhúng; confidential client có credential storage phù hợp.
5. **Credential generation:** dùng CSPRNG và entropy đủ cao.
6. **Secret storage:** `PasswordEncoder` ở AS; secret manager/vault ở client; không log raw secret.
7. **RAT:** lưu tách biệt, high entropy, bound to client, không dùng cho Token Endpoint.
8. **Registration URL:** dùng nguyên `registration_client_uri` do AS cấp.
9. **Expiry:** quản lý `client_secret_expires_at`, cảnh báo và rotation trước hạn.
10. **Rotation:** có owner, version, overlap window, rollback và thu hồi secret cũ.
11. **RFC 7592:** xác định rõ AS có hỗ trợ GET/PUT/DELETE và credential rotation hay không.
12. **SAS version:** kiểm tra DCR disabled-by-default, `JwtDecoder`, `client.create`, `client.read` và management support theo đúng version.
13. **Repository:** dùng persistence bền vững, transaction/version control và audit cho client lifecycle.
14. **Suspend/revoke:** chặn token mới, thu hồi credential, xử lý grants và tokens đang hoạt động.
15. **Deprovision:** vô hiệu client ID, secret, RAT và authorization/token liên quan.
16. **Incident response:** có quy trình xử lý IAT/RAT/client secret compromise.
17. **Observability:** audit metadata version và outcome; redact mọi credential.
18. **Testing:** kiểm thử registration/read/update/delete, rotation, replay, race, expiry và token behavior.

## 19. Tài liệu chuẩn và Spring cần đối chiếu

- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591.html): client metadata, registration request/response, software statement và security considerations.
- [RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol](https://www.rfc-editor.org/rfc/rfc7592.html): Client Read, Update, Delete, Registration Access Token và credential rotation. Đây là Experimental RFC.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): client types, client authentication và token endpoint.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): bảo vệ bearer credentials và Authorization header.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): security practice hiện đại cho OAuth clients và token handling.
- [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html): OIDC client registration metadata và Client Read.
- [Spring Authorization Server 1.5.8 — How-to: Register a client dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html): bật DCR, registrar scopes, initial access token, registration và client retrieval.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OidcClientRegistrationEndpointConfigurer`, providers, converters và response handlers.
- [Spring Authorization Server 1.5.8 — RegisteredClient.Builder](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/client/RegisteredClient.Builder.html): `clientSecret`, `clientSecretExpiresAt` và client metadata.
- [Spring Authorization Server 1.5.8 — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClientRepository` và lưu trữ client registration.

**Ghi nhớ:** DCR tạo ra client registration; quản lý vòng đời đòi hỏi thêm read, update, rotation, suspend, revoke và deprovision. IAT cho phép đăng ký client mới; RAT quản lý một registration cụ thể; client secret xác thực confidential client tại Token Endpoint. RFC 7591 định nghĩa đăng ký ban đầu, còn RFC 7592 Experimental mở rộng GET/PUT/DELETE và credential rotation. Spring Authorization Server 1.5.8 tắt DCR mặc định, hỗ trợ registration và Client Read khi bật endpoint, với registrar scopes `client.create` và `client.read`; không nên giả định PUT/DELETE management đã có sẵn. Hãy lưu secret bằng `PasswordEncoder`, giữ raw credential trong secret manager, kiểm tra metadata theo policy và vô hiệu mọi credential/token liên quan khi client bị thu hồi.
