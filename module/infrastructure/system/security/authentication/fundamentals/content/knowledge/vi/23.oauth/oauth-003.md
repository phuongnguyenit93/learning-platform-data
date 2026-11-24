# Client — Vai trò và bảo vệ OAuth client

Trong OAuth 2.0, **client** là ứng dụng hoặc thành phần phần mềm yêu cầu authorization server cấp quyền truy cập tài nguyên. Client có thể hoạt động thay mặt người dùng (ví dụ ứng dụng quản lý lịch truy cập lịch cá nhân) hoặc thay mặt chính workload của nó (ví dụ dịch vụ đồng bộ gọi API nội bộ). Client là một thành phần trong giao thức cấp quyền; nó không đồng nghĩa với người dùng, resource owner hay resource server.

Một OAuth client có **client identifier (client_id)** để authorization server nhận diện cấu hình ứng dụng. Tùy loại client, nó có thể phải chứng minh danh tính ở token endpoint bằng client authentication. Tuy nhiên, **client authentication không chứng minh người dùng đã đăng nhập** và cũng không tự cấp quyền truy cập dữ liệu. Việc người dùng cấp quyền, loại grant, scope, audience, consent và policy của resource server vẫn phải được xử lý riêng.

Bài học này thuộc chương **OAuth** trong nền tảng authentication, nơi người học tìm hiểu credential, token, phiên, liên kết danh tính và ranh giới tin cậy. Trọng tâm ở đây là hiểu client là ai trong giao thức, phân loại public/confidential client, đăng ký redirect URI, chọn phương thức xác thực client và bảo vệ token trong toàn bộ vòng đời.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vai trò client, resource owner, authorization server và resource server.
2. Phân biệt client_id, client secret, client authentication, user authentication và authorization grant.
3. Phân loại confidential client, public client, browser-based app, native app và machine-to-machine client.
4. Chọn phương thức xác thực client phù hợp với khả năng giữ bí mật của môi trường chạy.
5. Thiết kế client registration, redirect URI, grant type, response type, scope và token endpoint authentication method.
6. Mô tả Authorization Code Flow + PKCE và trách nhiệm của client trong từng bước.
7. Bảo vệ access token, refresh token, client secret và private key khỏi lộ lọt.
8. Nhận diện lỗi như redirect URI quá rộng, client impersonation, mix-up, secret nhúng trong ứng dụng công khai và token leakage.
9. Viết bộ kiểm thử để chứng minh client chỉ nhận token theo đúng client registration và quyền đã được cấp.

## 2. Các vai trò trong OAuth

OAuth 2.0 xác định các vai trò giao thức; trong một hệ thống thực tế, một ứng dụng có thể đồng thời chứa nhiều thành phần nhưng cần phân biệt trách nhiệm logic.

| Vai trò | Ý nghĩa | Ví dụ StudyHub |
| --- | --- | --- |
| **Resource owner** | Chủ thể có quyền cấp quyền truy cập tài nguyên được bảo vệ; thường là người dùng | Học viên cho phép ứng dụng lịch đọc danh sách khóa học của mình. |
| **Client** | Ứng dụng yêu cầu quyền truy cập resource server | Ứng dụng lịch StudyHub Calendar. |
| **Authorization server** | Xác thực resource owner, thu thập consent/chính sách và phát hành token | Campus Authorization Service. |
| **Resource server** | API lưu giữ hoặc cung cấp tài nguyên được bảo vệ, kiểm tra access token | StudyHub Course API. |

~~~mermaid
flowchart LR
    U["Resource owner"] -->|"Đăng nhập / consent"| AS["Authorization server"]
    C["OAuth client"] -->|"Authorization request"| AS
    AS -->|"Authorization code / tokens"| C
    C -->|"Access token"| RS["Resource server"]
    RS --> DATA[("Protected resource")]
~~~

**Client không phải authorization server.** Client khởi tạo request, nhận authorization code/token và gọi API. Authorization server quyết định có cấp token hay không. Resource server quyết định token có đủ điều kiện truy cập tài nguyên cụ thể hay không.

### 2.1. Client có thể hoạt động thay mặt ai?

Có hai bối cảnh phổ biến:

- **Delegated access:** client yêu cầu quyền thay mặt người dùng. Ví dụ người dùng cấp cho ứng dụng quản lý tài liệu quyền đọc file của họ. Authorization server cần xác thực người dùng và áp dụng consent/policy.
- **Client/service access:** client yêu cầu token cho chính workload của nó, không có người dùng tương tác trực tiếp. Ví dụ batch service gọi API đồng bộ. Client có thể dùng Client Credentials grant nếu phù hợp và được cho phép.

Không được nhầm delegated access với service identity. Một token đại diện người dùng và một token đại diện workload có subject, scope, audience, audit và quyền khác nhau.

## 3. Client identifier không phải client secret

Khi đăng ký client, authorization server cấp hoặc chấp nhận một **client_id**. Đây là định danh dùng trong authorization request và token request. Nó thường không được xem là bí mật; người dùng có thể nhìn thấy nó trong URL authorize hoặc ứng dụng công khai.

**Client secret** là credential chỉ phù hợp với confidential client có thể giữ bí mật ở môi trường server-side được kiểm soát. Nếu secret nằm trong JavaScript, mobile binary, desktop package hoặc repository công khai, người dùng/attacker có thể trích xuất nó. Một secret nhúng trong ứng dụng phân phối cho nhiều người không còn là bằng chứng xác thực client đáng tin.

| Giá trị | Mục đích | Có cần bí mật? | Ai có thể giữ? |
| --- | --- | --- | --- |
| client_id | Nhận diện client registration | Thường không | Mọi loại client. |
| client_secret | Xác thực confidential client theo phương thức đã đăng ký | Có | Backend/service có nơi lưu secret an toàn. |
| Private key | Ký client assertion hoặc chứng minh sở hữu khóa | Có | HSM/KMS hoặc secure key store của confidential client. |
| Redirect URI | Đích callback được đăng ký | Không phải secret | Client và authorization server; phải khớp policy. |
| Access token | Gọi resource server theo scope/audience | Có | Client, lưu trong bộ nhớ hoặc kho được bảo vệ phù hợp. |
| Refresh token | Xin access token mới | Rất nhạy cảm | Chỉ client được cấp; lưu trữ và xoay vòng theo policy. |

**Client ID không cấp quyền.** Attacker biết client_id không có nghĩa họ có thể lấy token hoặc truy cập API. Nhưng cấu hình client sai, redirect URI lỏng hoặc thiếu PKCE có thể biến một định danh công khai thành điểm hỗ trợ tấn công.

## 4. Phân loại client: public và confidential

Phân loại dựa trên khả năng giữ credential bí mật trong môi trường triển khai, không dựa trên việc ứng dụng có giao diện hay không.

### 4.1. Confidential client

Confidential client có thể giữ credential bí mật và chứng minh danh tính với authorization server. Ví dụ:

- Backend web application chạy trên server do tổ chức kiểm soát.
- API gateway hoặc service backend có secret store/KMS.
- Workload server-to-server có private key hoặc chứng chỉ được quản lý.

Các kiểm soát thường cần:
- Client authentication tại token endpoint bằng phương thức đã đăng ký.
- Secret/private key không nằm trong source code, image hoặc log.
- Least privilege cho grant, scope và audience.
- Rotation, expiration, revocation và audit cho client credential.
- Phân tách credential theo environment và workload.

### 4.2. Public client

Public client chạy trong môi trường mà người dùng hoặc attacker có thể kiểm tra và trích xuất mã/cấu hình, nên không thể giữ client secret chung một cách đáng tin cậy. Ví dụ:

- Single-page application (SPA) chạy trong browser.
- Native mobile application.
- Desktop application được phân phối tới thiết bị người dùng.

Các kiểm soát thường cần:
- Không nhúng client secret như thể đó là bí mật.
- Dùng Authorization Code Flow với PKCE.
- Đăng ký redirect URI chính xác và kiểm tra đúng response.
- Bảo vệ refresh token bằng rotation/reuse detection hoặc sender-constraining theo yêu cầu bảo mật hiện hành.
- Dùng secure storage của nền tảng cho token trên mobile/desktop.
- Hạn chế scope và thời hạn token.

| Đặc điểm | Confidential client | Public client |
| --- | --- | --- |
| Có thể giữ client secret? | Có, nếu môi trường và vận hành được kiểm soát | Không thể tin cậy secret nhúng trong bản phân phối |
| Ví dụ | Server-side web app, backend service | SPA, mobile, desktop app |
| Client authentication | Có thể dùng client secret, private_key_jwt, mTLS hoặc phương thức được đăng ký | Thường không dùng client secret; có thể dùng PKCE và sender-constraining |
| PKCE | Nên dùng cho authorization code flow | Bắt buộc trong thiết kế hiện đại theo best practice |
| Nơi giữ token | Server-side token/session store | Browser/mobile secure storage hoặc BFF |
| Rủi ro nổi bật | Lộ secret/private key, quyền backend quá rộng | XSS, thiết bị bị chiếm, token theft, redirect và custom scheme |

**Có giao diện không đồng nghĩa public; không có giao diện không đồng nghĩa confidential.** Một SPA có thể gọi backend BFF; trong mô hình đó BFF là confidential client, còn SPA là browser client tương tác với BFF. Phải phân loại từng thành phần thực sự nói chuyện với authorization server.

## 5. Đăng ký OAuth client

Client registration là quá trình thiết lập cấu hình để authorization server biết client nào được phép sử dụng giao thức và trong phạm vi nào. Có thể là đăng ký tĩnh bởi quản trị viên, quy trình onboarding của tổ chức hoặc Dynamic Client Registration khi authorization server hỗ trợ và kiểm soát chặt.

Metadata client thường gồm:

| Metadata | Ý nghĩa |
| --- | --- |
| client_id | Định danh client. |
| client_name | Tên hiển thị để người dùng nhận biết khi consent. |
| redirect_uris | Danh sách callback URI được phép. |
| grant_types | Các grant client được phép dùng. |
| response_types | Các loại authorization response được hỗ trợ. |
| token_endpoint_auth_method | Phương thức client authentication tại token endpoint. |
| scope/policy | Phạm vi quyền client có thể yêu cầu; authorization server vẫn áp grant/consent. |
| application_type | Loại ứng dụng, ví dụ web hoặc native theo profile. |
| contacts/owner | Nhóm chịu trách nhiệm, thông tin vận hành. |
| software_statement / policy reference | Bằng chứng/metadata bổ sung nếu quy trình onboarding yêu cầu. |

Không cấp tất cả grant type cho mọi client. Một SPA không cần Client Credentials grant chỉ vì server hỗ trợ nó. Một service integration không cần quyền đăng nhập người dùng nếu chỉ gọi API nội bộ.

### 5.1. Quản lý môi trường và tenant

Tách client registration giữa development, staging và production. Redirect URI, token audience, client credential và scope của production phải được quản lý độc lập. Nếu một nền tảng multi-tenant dùng client chung, phải xác định tenant nào được phép, cách ràng buộc tenant trong authorization request và token, và ai được quyền thay đổi cấu hình.

Không lấy tenant_id, client_id hoặc redirect URI từ dữ liệu client gửi rồi tin trực tiếp. Server phải tra cứu registration và policy đã được phê duyệt.

## 6. Redirect URI là ranh giới bảo mật

Authorization server chuyển authorization response về redirect URI của client. Nếu URI quá rộng hoặc có thể bị thao túng, authorization code hoặc token có thể bị gửi tới attacker.

Ví dụ cấu hình an toàn hơn:
- Đăng ký https://app.studyhub.example/oauth/callback.
- So khớp redirect URI theo quy tắc exact matching với URI đã đăng ký, trừ các ngoại lệ chuẩn cho native loopback redirect.
- Không chấp nhận wildcard domain, open redirect hoặc URI do request tùy ý chỉ định.
- Không dùng redirect endpoint có tham số next/return_to tùy ý để chuyển code sang domain khác.
- Bảo vệ callback khỏi bị ghi log code/token; dùng TLS và hạn chế dữ liệu query.
- Với native app, dùng claimed HTTPS links/universal links hoặc loopback redirect phù hợp profile; tránh custom URI scheme không có biện pháp bảo vệ khi có thể bị app khác chiếm.

### 6.1. Vì sao wildcard nguy hiểm?

Nếu server cho phép mọi URI dưới *.studyhub.example, một subdomain yếu hoặc bị chiếm có thể trở thành nơi nhận authorization response. Nếu endpoint callback tự chuyển hướng theo return_to không kiểm soát, attacker có thể dùng nó làm open redirect.

Redirect URI cần được gắn với client registration. Không được coi một URI hợp lệ của client A là hợp lệ cho client B.

## 7. Client trong Authorization Code Flow + PKCE

Đây là luồng thường được khuyến nghị cho web, mobile và native app. Client tạo PKCE verifier/challenge, gửi authorization request tới authorization server, nhận code tại callback rồi đổi code tại token endpoint.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as OAuth Client
    participant B as Browser
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>C: Tạo state, nonce (nếu OIDC), code_verifier
    C->>C: Tính code_challenge = BASE64URL(SHA256(verifier))
    C->>B: Mở authorization request
    B->>AS: client_id, redirect_uri, scope, state, code_challenge
    AS->>U: Xác thực và yêu cầu consent theo policy
    U-->>AS: Hoàn tất
    AS-->>B: Redirect callback với authorization code + state
    B-->>C: Client nhận callback
    C->>C: Kiểm tra state và transaction
    C->>AS: POST token endpoint với code + code_verifier
    AS->>AS: Kiểm tra code, client, redirect URI và PKCE
    AS-->>C: Access token (và refresh token nếu được cấp)
    C->>RS: API request với access token
    RS-->>C: Resource response
~~~

### 7.1. Trách nhiệm của client

1. Tạo giá trị ngẫu nhiên state để liên kết callback với giao dịch đã khởi tạo và giảm CSRF/login CSRF.
2. Với OIDC, tạo nonce và kiểm tra claim tương ứng trong ID token.
3. Tạo PKCE code_verifier đủ ngẫu nhiên; dùng S256 để tạo code_challenge.
4. Dùng redirect URI đã đăng ký và lưu nó trong giao dịch đang chờ.
5. Kiểm tra state, issuer/authorization server và các điều kiện callback trước khi đổi code.
6. Gửi code tới token endpoint của đúng issuer, cùng code_verifier và client authentication nếu là confidential client.
7. Xác minh ID token theo OIDC nếu client dùng OIDC; không suy ra danh tính chỉ từ access token.
8. Lưu token ở nơi phù hợp, áp scope/audience đúng và tránh log token.

PKCE ràng buộc authorization code với client giữ verifier. Nó giảm rủi ro code bị chặn hoặc bị dùng bởi client khác, nhưng không thay thế redirect URI chính xác, state, issuer validation, client authentication khi cần hoặc bảo vệ token sau khi cấp.

### 7.2. Client không được tự tin vào callback

Callback là dữ liệu đến qua browser/front channel. Client cần đối chiếu state với giao dịch đã tạo, xử lý lỗi authorization response, kiểm tra issuer nếu hỗ trợ nhiều authorization server và không đổi code với endpoint do callback chỉ định tùy ý.

Không đưa client secret hoặc PKCE verifier vào URL. Không lưu code trong analytics, browser history dài hạn hoặc log reverse proxy. Sau khi hoàn tất callback, điều hướng tới URL nội bộ sạch để giảm lưu vết.

## 8. Client authentication tại token endpoint

Client authentication là cách confidential client chứng minh danh tính của **ứng dụng** khi gọi token endpoint. Nó khác với user authentication diễn ra tại authorization endpoint.

Các phương thức thường gặp:

| Phương thức | Cách hoạt động | Cân nhắc |
| --- | --- | --- |
| client_secret_basic | Gửi client ID/secret qua HTTP Basic trong TLS | Dễ tích hợp; secret cần được bảo vệ và rotation. |
| client_secret_post | Gửi client ID/secret trong body form | Chỉ dùng khi được hỗ trợ/đăng ký; tránh log body và ưu tiên phương thức phù hợp hơn theo policy. |
| private_key_jwt | Client ký JWT assertion bằng private key; authorization server xác minh bằng public key đã đăng ký | Tránh chia sẻ secret đối xứng; cần bảo vệ private key, kiểm tra iss, sub, aud, exp, jti và replay. |
| tls_client_auth / mTLS | Client chứng minh sở hữu private key của chứng chỉ TLS | Phù hợp môi trường có PKI/quản lý chứng chỉ; cần rotation và mapping certificate-client. |
| none | Không client authentication tại token endpoint | Thường dùng với public client; cần PKCE và các kiểm soát phù hợp. |

Không bật nhiều phương thức mà không có lý do. Client và authorization server phải thống nhất phương thức đã đăng ký; server không nên tự hạ xuống phương thức yếu hơn nếu client authentication thất bại.

### 8.1. private_key_jwt cần ràng buộc gì?

JWT client assertion thường có:
- iss và sub là client identifier theo profile.
- aud trỏ đúng authorization server/token endpoint theo yêu cầu.
- exp ngắn.
- jti duy nhất để giảm replay.
- Chữ ký bằng private key đã đăng ký cho client.

Authorization server phải kiểm tra chữ ký, issuer/subject, audience, thời gian, thuật toán được phép và chống replay jti theo policy. Không nhận public key hoặc JWKS URL tùy ý từ assertion mà không có nguồn tin cậy.

## 9. Client Credentials grant cho workload

Client Credentials grant dùng khi client yêu cầu token cho chính nó, thường trong service-to-service, không có resource owner tương tác ở thời điểm cấp token.

~~~http
POST /oauth/token HTTP/1.1
Host: auth.studyhub.example
Authorization: Basic <client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
scope=course.sync
~~~

Authorization server xác thực client, kiểm tra grant và scope được phép, rồi cấp access token đại diện cho client/workload. Không nên phát refresh token cho Client Credentials grant theo thiết kế OAuth phổ biến; workload thường xin access token mới bằng client authentication khi cần.

Ví dụ:
- course-sync-worker gọi API đồng bộ danh sách khóa học.
- Token có audience course-api và scope course.sync.
- Resource server kiểm tra token và chỉ cho phép thao tác đồng bộ được cấp.
- Audit ghi workload/client ID, không gán request cho một người dùng không có mặt.

Không dùng Client Credentials để giả lập người dùng hoặc bỏ qua consent. Nếu workload cần hành động thay mặt user, cần mô hình delegation phù hợp thay vì gán token service thành user token.

## 10. Token và session ở phía client

Sau khi nhận token, client phải bảo vệ chúng theo loại ứng dụng:

- **Backend web app/BFF:** ưu tiên giữ access/refresh token phía server; browser chỉ giữ session cookie được bảo vệ.
- **SPA:** cân nhắc BFF để giảm token dài hạn trong JavaScript. Nếu SPA trực tiếp dùng OAuth, cần đánh giá XSS, memory/storage, refresh token rotation hoặc sender constraint và lifetime ngắn.
- **Mobile/native:** dùng secure storage của hệ điều hành, tránh file cấu hình/log/backup không an toàn; mở authorization request qua external user-agent theo best practice.
- **Workload:** dùng secret manager, KMS/HSM, workload identity hoặc client certificate; hạn chế credential chia sẻ.

Client không nên:
- Lưu access/refresh token trong URL.
- Ghi token vào console, crash log, telemetry hoặc ticket.
- Dùng một token cho nhiều resource server không đúng audience.
- Giữ refresh token lâu hơn grant hoặc không có rotation/revocation policy.
- Để token tự quyết định quyền mà không có kiểm tra authorization phía resource server.

## 11. Scope, audience và consent

Client có thể yêu cầu scope, nhưng authorization server quyết định phạm vi được cấp theo registration, consent và policy. Resource server phải kiểm tra scope/audience phù hợp với API.

Ví dụ:
- profile.read: đọc hồ sơ cơ bản.
- course.read: đọc danh sách khóa học.
- course.sync: đồng bộ dữ liệu dành cho workload.
- grades.write: quyền nhạy cảm, có thể yêu cầu consent/admin approval và step-up.

Không yêu cầu scope rộng như * hoặc quyền quản trị chỉ vì client muốn đơn giản hóa code. Client cần xin đúng quyền cần thiết, hiển thị mục đích dễ hiểu và xử lý trường hợp người dùng từ chối một phần quyền.

**Scope không thay thế authorization đầy đủ.** API còn cần kiểm tra subject, tenant, quan hệ với resource, trạng thái tài khoản, role nội bộ và điều kiện nghiệp vụ. Client không thể tự quyết định rằng người dùng được sửa mọi điểm chỉ vì đã nhận token.

## 12. Client đa authorization server và issuer mix-up

Một client có thể hỗ trợ nhiều authorization server, ví dụ đăng nhập qua trường học hoặc đối tác. Nếu không ràng buộc issuer theo giao dịch, client có thể gửi code tới nhầm token endpoint hoặc chấp nhận response từ server không mong đợi.

Kiểm soát:
- Lưu issuer/authorization server đã chọn trong transaction server-side.
- Ghim authorization endpoint, token endpoint, metadata và JWKS theo issuer được phê duyệt.
- Xác minh issuer trong authorization response khi profile hỗ trợ (ví dụ iss parameter theo RFC 9207).
- Không dùng dữ liệu callback để tự chọn token endpoint.
- Kiểm tra ID token iss và aud trong OIDC.
- Phân tách client registration và redirect URI theo provider/tenant khi cần.

~~~mermaid
flowchart TD
    A["Client khởi tạo login"] --> B["Chọn issuer từ allowlist"]
    B --> C["Lưu issuer + state + redirect URI trong transaction"]
    C --> D["Redirect tới authorization endpoint đã ghim"]
    D --> E["Callback"]
    E --> F{"Issuer/state khớp transaction?"}
    F -->|Không| G["Từ chối, không đổi code"]
    F -->|Có| H["Đổi code tại token endpoint đã ghim"]
    H --> I["Xác minh token theo issuer/client"]
~~~

Issuer mix-up có thể dẫn đến code/token bị gửi sai nơi hoặc nhầm danh tính. PKCE là bảo vệ quan trọng nhưng không nên xem nó thay thế toàn bộ issuer binding và response validation trong client đa IdP.

## 13. Threat model: các lỗi thường gặp của OAuth client

| Đe dọa/lỗi | Nguyên nhân | Hậu quả | Kiểm soát |
| --- | --- | --- | --- |
| **Client secret nhúng trong SPA/mobile** | Nhầm public client là confidential | Attacker trích xuất secret và giả client | Không nhúng secret; dùng PKCE và thiết kế public client. |
| **Redirect URI wildcard** | Cho phép domain/path quá rộng | Code/token có thể bị chuyển tới endpoint attacker | Exact matching, allowlist và không có open redirect. |
| **Authorization code interception** | Code lộ qua browser/log/custom scheme | Attacker thử đổi code | PKCE S256, redirect an toàn, code ngắn hạn và một lần. |
| **CSRF/login CSRF** | Không ràng buộc callback với request | Nạn nhân bị gắn nhầm account/session | state, transaction binding và cookie/CSRF controls phù hợp. |
| **Issuer mix-up** | Client đa IdP không ghim issuer | Code/token gửi tới sai server | Issuer binding, response issuer validation và endpoint cố định. |
| **Token leakage** | Log, URL, localStorage, crash report | Attacker dùng bearer token | Redaction, secure storage, BFF, TLS và lifetime phù hợp. |
| **Client impersonation** | Secret yếu, dùng chung hoặc bị lộ | Attacker giả confidential client | private_key_jwt/mTLS khi phù hợp, rotation, audit và secret manager. |
| **Over-scoping** | Client xin quyền quá rộng | Blast radius lớn nếu token bị lộ | Least privilege, consent rõ, resource/audience restriction. |
| **Refresh token replay** | Token dài hạn bị đánh cắp, không có rotation/binding | Attacker duy trì quyền truy cập | Rotation/reuse detection hoặc sender-constraining theo loại client. |
| **Public client giả client authentication** | Server tin client_secret nhúng trong app | Bảo vệ giả tạo, dễ impersonate | Đăng ký đúng public client, PKCE và kiểm soát grant. |
| **Open redirect sau callback** | return_to tùy ý | Rò rỉ code/token hoặc chuyển hướng phishing | Allowlist destination nội bộ, loại bỏ redirect tùy ý. |
| **Client registration takeover** | Quy trình onboarding/redirect URI thay đổi yếu | Attacker thêm endpoint hoặc credential | Owner verification, phê duyệt, audit và quản trị metadata. |

## 14. Bài thực hành: đăng ký hai OAuth client cho StudyHub

**Bối cảnh:** StudyHub có hai ứng dụng:
- studyhub-web: web backend/BFF xử lý đăng nhập học viên và gọi Course API thay mặt người dùng.
- course-sync-worker: workload chạy định kỳ đồng bộ danh sách khóa học, không có người dùng tương tác.

### 14.1. Thiết kế client registration

Hãy lập bảng:

| Thuộc tính | studyhub-web | course-sync-worker |
| --- | --- | --- |
| Loại client | Confidential (BFF backend) | Confidential workload |
| Grant | Authorization Code + PKCE | Client Credentials |
| Redirect URI | Callback HTTPS cố định | Không cần redirect URI |
| Client authentication | private_key_jwt hoặc mTLS/secret theo policy | private_key_jwt hoặc mTLS |
| Token audience | Course API | Course API |
| Scope | course.read, profile.read | course.sync |
| Token storage | Server-side token/session store | Secret manager/KMS và runtime memory |
| Owner | Web platform team | Integration platform team |
| Rotation/revocation | Theo client credential/token grant lifecycle | Theo workload credential lifecycle |

Đây là một cấu hình mẫu; phương thức cụ thể phải phù hợp hạ tầng, khả năng quản lý khóa và policy của authorization server.

### 14.2. Bộ ca kiểm thử chấp nhận

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Client gửi đúng client_id và redirect URI đã đăng ký | Authorization request được xử lý theo policy. |
| Client gửi redirect URI khác một ký tự | Từ chối nếu không thuộc ngoại lệ native được chuẩn cho phép. |
| Public SPA gửi client_secret nhúng trong bundle | Server không coi secret đó là bằng chứng confidential client đáng tin. |
| Authorization code được đổi mà thiếu/wrong PKCE verifier | Token endpoint từ chối. |
| Callback có state sai | Client từ chối, không đổi code. |
| Client A dùng authorization code của client B | Từ chối do code/client binding. |
| Client secret hết hạn/revoked | Client authentication thất bại; không cấp token. |
| private_key_jwt có audience sai hoặc jti replay | Token endpoint từ chối. |
| Client Credentials xin scope ngoài allowlist | Từ chối hoặc chỉ cấp scope được phép theo policy. |
| Token audience không phải Course API | Resource server từ chối. |
| Client đa IdP nhận callback issuer không khớp transaction | Từ chối và không gửi code tới endpoint khác. |
| Refresh token bị replay | Authorization server áp reuse detection/revocation policy. |
| Client logout/revoke grant | Refresh token/grant được thu hồi theo phạm vi đã định. |
| Client bị decommission | Credential, grant và redirect URI không còn được chấp nhận. |
| Client credential xuất hiện trong log | Kiểm thử thất bại; log pipeline phải redact. |

### 14.3. Câu hỏi tự đánh giá

1. Client khác resource owner và resource server như thế nào?
2. Vì sao client_id không phải secret?
3. Khi nào client được phân loại confidential, khi nào là public?
4. Vì sao không thể giấu client secret trong SPA hoặc mobile binary?
5. PKCE bảo vệ authorization code khỏi kiểu tấn công nào?
6. Vì sao redirect URI cần exact matching?
7. Client authentication khác user authentication ở điểm nào?
8. Khi nào dùng Client Credentials grant và token đại diện cho ai?
9. Scope và audience khác nhau như thế nào?
10. Client đa IdP cần ràng buộc issuer để tránh lỗi gì?

**Tiêu chí hoàn thành:** Người học có thể vẽ đúng vai trò client trong OAuth, phân loại ứng dụng theo khả năng giữ bí mật, thiết kế registration/redirect/authentication method, giải thích PKCE và chứng minh bằng test rằng client không thể lấy token ngoài grant, scope, audience và issuer đã được cấp.

## 15. Vận hành và quản trị client

Một client registration là tài sản bảo mật có vòng đời. Cần:
- Có owner/team chịu trách nhiệm và contact xử lý sự cố.
- Lưu metadata đã phê duyệt, grant, redirect URI, scope, environment và phương thức client authentication.
- Theo dõi ngày tạo, lần sử dụng, thời hạn credential, lần rotation và lần review gần nhất.
- Cảnh báo client không có owner, redirect URI cũ, scope rộng hoặc credential sắp hết hạn.
- Có quy trình thay đổi redirect URI, thêm grant, thay public key/certificate và thu hồi client.
- Tách quyền người phát triển khỏi quyền phê duyệt client production.
- Ghi audit ai thay đổi metadata, ai cấp credential và ai revoke client.
- Xóa/disable registration khi ứng dụng ngừng hoạt động; không để callback cũ tiếp tục được tin.

Khi xoay client secret hoặc private key, có thể cần giai đoạn overlap có giới hạn cho confidential client; phải kiểm tra mọi instance đã dùng credential mới rồi thu hồi credential cũ. Nếu credential bị compromise, revoke khẩn cấp thay vì chờ hết overlap.

## 16. Tài liệu nên đọc tiếp

- **RFC 6749 — OAuth 2.0 Authorization Framework**: vai trò client, resource owner, authorization server, resource server và grant.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security**: PKCE, redirect URI, public client, refresh token và bảo vệ flow.
- **RFC 7636 — Proof Key for Code Exchange (PKCE)**: code verifier và code challenge.
- **RFC 7591 — OAuth 2.0 Dynamic Client Registration**: đăng ký client động khi hệ thống hỗ trợ.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens**: mTLS cho client và token ràng buộc chứng chỉ.
- **RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants**: JWT bearer assertion, bao gồm client authentication bằng JWT.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification**: nhận diện issuer trong authorization response.
- **OWASP OAuth 2.0 Cheat Sheet và ASVS**: biến cấu hình client thành kiểm soát và tiêu chí kiểm thử.

Khi triển khai thật, hãy xác định rõ client chạy ở đâu, ai kiểm soát runtime, secret/private key có thể được bảo vệ tới mức nào, authorization server hỗ trợ phương thức nào và API nào sẽ nhận token. **Một OAuth client an toàn phải được nhận diện đúng, chỉ dùng grant đã đăng ký, giữ credential trong môi trường phù hợp và không được tự mở rộng quyền mà authorization server cấp.**
