# Viết tài liệu vận hành và giới hạn bảo mật

## Mục tiêu dự án

Trong dự án này, bạn sẽ xây dựng một bộ tài liệu vận hành cho hệ thống sử dụng token để xác thực và phân quyền. Bộ tài liệu phải giúp đội vận hành biết cách theo dõi, xử lý sự cố, thu hồi token, xoay vòng khóa và khôi phục dịch vụ. Đồng thời, tài liệu phải nói rõ hệ thống bảo vệ được điều gì, phụ thuộc vào giả định nào và còn giới hạn bảo mật nào cần được chấp nhận hoặc giảm thiểu.

Sau khi hoàn thành, bạn có thể:

- Lập bản đồ thành phần, luồng token và ranh giới trách nhiệm giữa Identity Provider, authorization server, gateway và resource server.
- Viết runbook có điều kiện kích hoạt, người chịu trách nhiệm, các bước xử lý và tiêu chí xác minh hoàn tất.
- Công bố rõ token policy, key policy, cache behavior, revocation latency và các giới hạn của JWT/opaque token.
- Thiết kế cảnh báo và bằng chứng vận hành mà không ghi lộ token hoặc bí mật.
- Ghi nhận rủi ro còn lại, biện pháp bù, người chấp nhận rủi ro và ngày rà soát.
- Kiểm thử tài liệu bằng tabletop exercise và diễn tập trong môi trường test.

**Sản phẩm bàn giao** là một bộ tài liệu có thể dùng trong ca trực và khi xảy ra sự cố, không chỉ là mô tả kiến trúc. Người trực phải tìm được đúng quy trình, biết cần gọi ai, biết lệnh hoặc API nào được phép sử dụng, và có thể xác minh hệ thống đã trở lại trạng thái an toàn.

## 1. Phạm vi và người đọc

Tài liệu vận hành token security thường phục vụ nhiều nhóm:

| Người đọc | Điều họ cần tìm |
| --- | --- |
| On-call/SRE | Tình trạng dịch vụ, cảnh báo, bước chẩn đoán, rollback và escalation |
| Identity platform team | Cấu hình issuer, client, token lifetime, key rotation và grant |
| Application/API team | Cách xác minh token, audience, scope, tenant và xử lý lỗi |
| Security operations | Điều tra token bị lộ, revoke, key compromise và bằng chứng |
| Compliance/audit | Policy, owner, phê duyệt, lịch sử thay đổi và rủi ro còn lại |
| Product/service owner | Ảnh hưởng tới người dùng, SLA và quyết định chấp nhận rủi ro |

Trước khi viết, xác định:

- Hệ thống nào nằm trong phạm vi: issuer, authorization server, resource server, gateway, mobile/web client, workload identity hay dịch vụ federation.
- Môi trường nào được mô tả: development, test, staging, production.
- Token nào được sử dụng: access token, refresh token, ID Token, opaque token, JWT hoặc token exchange output.
- Ai sở hữu từng thành phần và ai có quyền thực hiện thao tác nhạy cảm.
- Những dịch vụ ngoài phạm vi nhưng hệ thống phụ thuộc vào, ví dụ KMS/HSM, DNS, time service, database, cache, SIEM và message broker.

Không viết hướng dẫn chung chung kiểu “liên hệ quản trị viên” nếu có thể nêu rõ vai trò, kênh escalation và thông tin cần cung cấp. Không đưa secret, raw token, private key hoặc thông tin production nhạy cảm vào tài liệu.

## 2. Mô tả hệ thống và ranh giới tin cậy

Bắt đầu bằng một sơ đồ giúp người trực hiểu token đi qua những thành phần nào. Ví dụ:

~~~mermaid
flowchart LR
    U["User / Workload"] --> C["Client"]
    C -->|Authorization request| AS["Authorization Server / IdP"]
    AS -->|Access token| C
    C -->|Bearer token| GW["API Gateway"]
    GW --> RS["Resource Server"]
    RS --> DB["Protected resource"]
    AS --> KMS["KMS / HSM"]
    AS --> JWKS["JWKS endpoint"]
    RS -->|Fetch/cache public keys| JWKS
    RS --> OBS["Logs / Metrics / SIEM"]
    AS --> OBS
~~~

Sơ đồ phải được chỉnh theo kiến trúc thật. Đánh dấu trust boundary, luồng dữ liệu nhạy cảm và điểm thực thi quyền. Ghi rõ:

- Ai xác thực người dùng hoặc workload?
- Ai phát hành access token và refresh token?
- Ai giữ private signing key?
- Ai xác minh chữ ký, issuer, audience, expiration và scope?
- Ai kiểm tra quyền trên object và tenant?
- Ai lưu trạng thái refresh token, opaque token, session và revoke?
- JWKS/introspection cache nằm ở đâu?
- Khi một thành phần không khả dụng, thành phần còn lại xử lý theo chính sách nào?

### Ma trận trách nhiệm

| Thành phần | Trách nhiệm chính | Chủ sở hữu | Bằng chứng vận hành |
| --- | --- | --- | --- |
| Authorization server | Phát hành token, quản lý grant, refresh và revoke | Identity team | Token issuance/revoke events |
| KMS/HSM | Bảo vệ private key và kiểm soát thao tác ký | Platform/Security | Key audit log, key state |
| JWKS endpoint | Công bố public key đã được tin cậy | Identity team | JWKS version, cache headers |
| API gateway | Xác minh hoặc chuyển tiếp token theo thiết kế | API platform | Gateway metrics và policy version |
| Resource server | Kiểm tra token và quyền trên tài nguyên | Application team | Auth decision logs |
| Cache | Lưu trạng thái introspection/JWKS/authorization | Platform team | TTL, invalidation events |
| SIEM | Tập hợp cảnh báo và audit evidence | SecOps | Alert history, incident ID |

Nếu gateway xác minh token rồi resource server bỏ qua kiểm tra tenant/object-level authorization, tài liệu phải nêu rõ đây là ranh giới không an toàn và cần khắc phục. Không mặc định gateway có thể thay thế mọi kiểm soát ở ứng dụng.

## 3. Lập inventory token và policy

Một tài liệu vận hành cần một bảng token inventory làm nguồn tham chiếu thống nhất:

| Loại token | Mục đích | Ai phát hành/xác minh | Trạng thái và revoke |
| --- | --- | --- | --- |
| JWT access token | Gọi API/resource server | Authorization server ký; resource server xác minh | Có thể stateless; revoke sớm cần denylist/introspection hoặc key-level block |
| Opaque access token | Gọi API khi resource server tra trạng thái | Authorization server lưu; resource server introspect | Revoke tại token store; phải xử lý introspection cache |
| Refresh token | Xin access token mới | Authorization server phát hành và quản lý | Revoke token/family/session; kiểm tra rotation và reuse |
| ID Token | Truyền kết quả xác thực tới OIDC client | OpenID Provider phát hành; client xác minh | Không dùng làm access token cho API |
| Service/workload token | Gọi service-to-service | Identity/workload platform phát hành | Revoke theo workload identity, client/grant và token policy |

Với mỗi loại, ghi:

- Issuer, audience/resource và client/grant được phép.
- Claims bắt buộc, scope, tenant context và loại principal.
- Thuật toán ký và key ID policy.
- Thời hạn tối đa, clock skew và thời điểm refresh.
- Cơ chế revoke và thời gian lan truyền trạng thái.
- Vị trí lưu trữ ở client/server và cách bảo vệ.
- Các API/service phụ thuộc và người sở hữu.

### Ví dụ token policy

~~~yaml
tokenPolicy:
  accessToken:
    format: jwt
    maxLifetimeSeconds: 600
    allowedClockSkewSeconds: 60
    requiredClaims:
      - iss
      - sub
      - aud
      - exp
    audienceRestricted: true
  refreshToken:
    rotation: enabled
    reuseDetection: enabled
    familyRevocation: enabled
  validation:
    issuerAllowlist: managed-configuration
    algorithmAllowlist: managed-configuration
    unknownKid: reject
  revocation:
    targetPropagationSeconds: 30
~~~

Đây là ví dụ cấu trúc tài liệu, không phải cấu hình production hoặc ngưỡng phù hợp cho mọi hệ thống. Các giá trị phải được thay bằng policy đã phê duyệt và số liệu đo thực tế. Nếu hệ thống không hỗ trợ một trường, ghi rõ “không hỗ trợ” và biện pháp bù.

## 4. Viết token validation contract

Tài liệu phải mô tả chính xác điều kiện một token được chấp nhận. Một contract phổ biến gồm:

1. Token được nhận qua đúng cơ chế đã quy định, thường là Authorization Bearer header đối với bearer access token.
2. Cấu trúc token hợp lệ và thuật toán nằm trong allowlist cấu hình sẵn.
3. Chữ ký được xác minh bằng key thuộc issuer đã cấu hình.
4. Issuer (`iss`) đúng với trust configuration.
5. Audience (`aud`) bao gồm resource server hiện tại.
6. Token còn hạn (`exp`) và đã tới thời điểm bắt đầu hiệu lực (`nbf`) nếu claim này được dùng.
7. Token type/use phù hợp với API; không dùng ID Token thay access token.
8. Scope/permission đủ cho hành động.
9. Tenant context được xác minh và tài nguyên thuộc tenant đó.
10. Token/session/grant không bị revoke theo cơ chế trạng thái đang áp dụng.

Không lấy claim từ JWT chỉ mới decode để ra quyết định. Phải xác minh chữ ký và các điều kiện trust trước. Không tự tải key từ URL do token header cung cấp; `kid` chỉ dùng chọn key trong JWKS của issuer đã được tin cậy.

### Phân biệt authentication và authorization

Token hợp lệ có thể xác nhận một principal và một tập quyền được cấp. Nó không tự chứng minh principal có quyền truy cập mọi object. Mỗi request cần kết hợp:

`principal + tenant context + action + resource`

Ví dụ, token có `orders.read` và tenant `tenant-a` vẫn không cho phép đọc một order thuộc `tenant-b`. Resource server phải thực hiện tenant isolation và object-level authorization.

## 5. Runbook vận hành thường ngày

Mỗi runbook cần có cùng cấu trúc để người trực dễ tìm:

- **Mục đích:** sự cố hoặc thao tác nào được xử lý.
- **Điều kiện kích hoạt:** alert, ticket, lịch bảo trì hoặc yêu cầu được phê duyệt.
- **Mức độ ảnh hưởng:** người dùng, API, tenant, region và loại token liên quan.
- **Quyền cần có:** role/approval bắt buộc.
- **Bước thực hiện:** hành động theo thứ tự và công cụ/API được phép.
- **Xác minh:** metric, trạng thái hoặc request test chứng minh kết quả.
- **Rollback/escalation:** điều kiện dừng, cách quay lại và người cần gọi.
- **Evidence:** incident/change ID và dữ liệu cần lưu.

### 5.1 Theo dõi trạng thái token service

Đầu ca trực:

1. Kiểm tra health của authorization server, token endpoint, discovery, JWKS và introspection nếu được sử dụng.
2. Kiểm tra trạng thái KMS/HSM, key đang active và lỗi ký.
3. Kiểm tra error rate của token issuance, validation, refresh và revoke.
4. Kiểm tra thời gian hệ thống và độ lệch đồng hồ.
5. Kiểm tra queue/event backlog dùng phân phối revocation hoặc key updates.
6. Kiểm tra alert đang mở và thay đổi policy gần nhất.

Không chỉ dựa vào health endpoint. Thực hiện synthetic transaction bằng client test: lấy token, gọi API test, kiểm tra token hết hạn hoặc revoke theo kịch bản và xác nhận resource server phản hồi đúng.

### 5.2 Xử lý lỗi xác minh token tăng đột biến

**Kích hoạt:** tăng `invalid_signature`, `unknown_kid`, `invalid_issuer`, `invalid_audience` hoặc 401 bất thường.

**Chẩn đoán:**

- Phân nhóm theo issuer, `kid`, API, region và phiên bản ứng dụng.
- Kiểm tra JWKS endpoint, cache age, ETag và lần refresh gần nhất.
- Xác định issuer có vừa đổi key hoặc thay discovery metadata không.
- Kiểm tra đồng hồ verifier và issuer.
- So sánh cấu hình allowlist thuật toán/issuer giữa các replica.

**Xử lý:**

- Nếu key mới chưa được phân phối, tạm dừng chuyển signing theo change procedure.
- Nếu một replica có cache cũ, thực hiện invalidation/refresh theo công cụ được phê duyệt.
- Nếu token sai issuer/audience hoặc chữ ký không hợp lệ, giữ nguyên từ chối và điều tra nguồn phát hành.
- Không tắt signature validation hoặc mở rộng issuer/algorithm allowlist chỉ để giảm 401.

**Hoàn tất khi:** mọi replica có trust configuration nhất quán, synthetic request hợp lệ thành công và token sai chữ ký/issuer/audience vẫn bị từ chối.

### 5.3 Xử lý refresh token thất bại

Kiểm tra:

- Token đã hết hạn, bị revoke hay đã bị rotation thay thế?
- Client có gửi đúng client authentication và redirect/client binding theo flow không?
- Có reuse detection hoặc token family revocation không?
- Authorization server có lỗi lưu trữ trạng thái hoặc clock drift không?
- Có thay đổi policy hoặc consent/membership gần đây không?

Không yêu cầu người dùng gửi raw refresh token vào ticket. Dùng request ID, client ID, subject reference và token fingerprint an toàn để điều tra. Nếu nghi refresh token bị đánh cắp, chuyển sang runbook incident thay vì chỉ yêu cầu đăng nhập lại.

## 6. Runbook key rotation

Planned key rotation phải có lịch, owner, change ID và thời gian quan sát. Tài liệu cần phân biệt ba khoảng:

- **Publish lead:** public key mới được công bố đủ sớm để mọi verifier tải được trước khi issuer bắt đầu ký.
- **Old-key verification window:** giữ public key cũ để xác minh token hợp lệ đã phát hành.
- **Trust-cache convergence:** thời gian để mọi verifier nhận thay đổi khi key cũ bị gỡ.

Quy trình:

1. Xác nhận key mới được tạo trong KMS/HSM và có owner, `kid`, thuật toán, mục đích.
2. Publish public key mới lên JWKS cùng key hiện hành.
3. Kiểm tra nhiều verifier/region đã nhận key mới.
4. Chuyển issuer sang ký bằng key mới và theo dõi lỗi xác minh.
5. Ghi thời điểm cuối cùng key cũ được dùng để ký.
6. Giữ key cũ để verify tới khi token hợp lệ cuối cùng hết hạn, cộng clock skew và margin đã phê duyệt.
7. Gỡ key cũ, refresh cache và xác minh token mới vẫn hoạt động, token cũ hết hạn bị từ chối.
8. Disable/delete private key cũ theo policy; lưu metadata cần thiết cho audit.

Nếu private key bị compromise, không dùng quy trình overlap thông thường. Chuyển sang emergency rotation: dừng ký, chặn `kid` bị ảnh hưởng, purge cache, đánh giá token giả mạo và xác minh từng verifier. Có thể phải từ chối token còn hạn ký bằng key cũ để containment.

### Điều kiện dừng/rollback

- Unknown key hoặc signature failure vượt ngưỡng đã định.
- Một hay nhiều region chưa nhận public key mới.
- KMS/HSM báo key state không xác định.
- Issuer phát hành token bằng `kid` chưa được công bố.
- Audit event hoặc approval không đầy đủ.

Chỉ rollback về key cũ nếu key đó còn an toàn, chưa compromise và còn được policy cho phép. Không rollback về key đã bị xâm phạm.

## 7. Runbook revoke và token compromise

**Kích hoạt:** token xuất hiện trong log không đáng tin cậy, phát hiện replay, refresh reuse, client secret bị lộ, session bị chiếm hoặc signing key có dấu hiệu compromise.

~~~mermaid
flowchart TD
    A["Phát hiện credential bị lộ"] --> B["Xác định loại token/key và phạm vi"]
    B --> C["Ngăn phát hành mới"]
    C --> D["Revoke token, family, session hoặc client"]
    D --> E["Cập nhật denylist / JWKS / cache"]
    E --> F["Kiểm tra mọi resource server"]
    F --> G["Theo dõi replay và lưu evidence"]
    G --> H["Recovery và đóng incident"]
~~~

Các bước:

1. Tạo incident ID; xác định issuer, subject/client, tenant, audience, token type, `jti`/fingerprint và thời điểm lộ.
2. Không đưa raw token vào ticket hoặc chat; hạn chế người được xem evidence.
3. Chặn khả năng cấp token mới từ credential bị lộ: disable client/grant, chặn refresh hoặc dừng ký bằng key compromise.
4. Revoke opaque token tại token store; revoke refresh token family/session/grant liên quan.
5. Với JWT, cập nhật denylist/stateful validation nếu có; nếu signing key bị lộ, emergency rotate và chặn key cũ.
6. Invalidate introspection/JWKS/authorization cache và phân phối trạng thái tới gateway, resource server, worker và region.
7. Thử lại bằng token bị revoke ở từng resource server và xác minh refresh không thể cấp token mới.
8. Theo dõi replay, refresh reuse, request bị từ chối và node chưa nhận trạng thái mới.

**Không đóng incident chỉ vì revoke API trả thành công.** Chỉ đóng khi đã xác minh điểm thực thi quyền từ chối credential bị ảnh hưởng và revocation latency nằm trong SLA.

## 8. Runbook khi Identity Provider hoặc dependency không khả dụng

Ghi rõ cách hệ thống hoạt động khi:

| Dependency lỗi | Câu hỏi cần trả lời | Hướng dẫn cần có |
| --- | --- | --- |
| Authorization server | Có thể đăng nhập/refresh token mới không? | Thông báo ảnh hưởng, retry policy và recovery |
| JWKS endpoint | Verifier có key trong cache không? | Cache lifetime, stale-if-error và điều kiện fail closed |
| Introspection | Token status không tra được thì sao? | Fail closed hoặc fallback được phê duyệt theo loại tài nguyên |
| KMS/HSM | Có ký token mới được không? | Dừng issuance hay dùng key dự phòng đã phê duyệt |
| Revocation event bus | Revoke chưa lan tới verifier? | Queue, retry, reconciliation và SLA |
| Time service | Clock drift vượt ngưỡng? | Cảnh báo, cách khôi phục đồng hồ và xử lý token |
| Database/token store | Không đọc được grant/session? | Quy tắc từ chối, backup và khôi phục |

Không dùng một chính sách fallback cho mọi API. Một endpoint đọc dữ liệu công khai và một endpoint chuyển tiền có mức rủi ro khác nhau. Nếu có degraded mode, phải nêu rõ tài nguyên nào được truy cập, thời gian tối đa, điều kiện kích hoạt và người phê duyệt.

## 9. Ghi rõ giới hạn bảo mật

Phần này thường bị bỏ quên. Tài liệu vận hành phải nêu rõ các giới hạn đã biết để đội phát triển, vận hành và chủ sở hữu dịch vụ không hiểu nhầm khả năng bảo vệ của token.

### 9.1 JWT tự chứa không tự revoke tức thì

JWT có thể được xác minh cục bộ mà không gọi authorization server. Nếu verifier chỉ kiểm tra chữ ký và claims, nó không biết token vừa bị revoke. Token có thể tiếp tục được chấp nhận tới `exp`. Biện pháp bù gồm access token TTL ngắn, denylist, introspection hoặc kiểm tra trạng thái tập trung. Ghi rõ SLA revoke thực tế.

### 9.2 Bearer token có thể bị replay

Ai sở hữu bearer token có thể sử dụng nó trong thời gian token còn hợp lệ và trong phạm vi được cấp. TLS bảo vệ dữ liệu trên đường truyền nhưng không ngăn token bị lấy từ endpoint, browser storage, log, crash dump hoặc malware. Biện pháp bù gồm bảo vệ thiết bị, giảm nơi lưu token, tránh log secret, token TTL ngắn và sender-constrained token như mTLS/DPoP khi phù hợp.

### 9.3 Scope không thay thế object authorization

Scope thường mô tả loại hành động hoặc quyền tương đối rộng. Token có `orders.read` không có nghĩa người dùng được đọc mọi order. Resource server vẫn phải kiểm tra tenant ownership, quan hệ với object và policy nghiệp vụ.

### 9.4 Claims có thể cũ

Role, group, tenant membership hoặc trạng thái tài khoản trong JWT phản ánh thời điểm token được phát hành. Nếu quyền bị thu hồi sau đó, claim trong token không tự thay đổi. Biện pháp bù gồm token lifetime phù hợp, online policy check, revocation event hoặc introspection tùy mức độ cần cập nhật.

### 9.5 Clock skew tạo cửa sổ dung sai

Verifier có thể chấp nhận một khoảng clock skew để xử lý đồng hồ lệch. Dung sai lớn làm tăng khoảng thời gian token có thể được chấp nhận quanh ranh giới `exp`/`nbf`. Ghi giá trị được phép, owner và cách giám sát đồng hồ.

### 9.6 Opaque token phụ thuộc availability của trạng thái

Opaque token thường cần introspection hoặc token store. Khi dependency lỗi, resource server phải áp dụng fallback đã xác định. Cache kết quả active có thể làm revoke chậm; ghi rõ TTL và propagation.

### 9.7 Key rotation không thu hồi mọi token cũ

Trong planned rotation, public key cũ thường cần được giữ để xác minh token hợp lệ đã phát hành. Xóa private key không khiến verifier quên public key. Khi private key bị compromise, cần emergency block và cache invalidation.

### 9.8 Token không chứng minh consent hoặc ý định người dùng

Scope trong access token biểu diễn quyền được cấp theo policy, không thay thế consent record, nội dung thông báo hay bằng chứng pháp lý. Nếu hệ thống cần chứng minh consent, phải lưu record riêng và liên kết với authorization grant.

### 9.9 Token không bảo vệ endpoint đã bị chiếm

Nếu thiết bị hoặc server giữ token đã bị compromise, attacker có thể lấy token hoặc sử dụng ứng dụng như chính principal hợp lệ. Token validation không thay thế endpoint protection, secure storage, MFA, workload hardening và monitoring.

### 9.10 Phụ thuộc nhà cung cấp và giới hạn quan sát

Nếu issuer, KMS hoặc introspection do bên thứ ba vận hành, tổ chức phụ thuộc SLA, khả năng xuất log và thời gian xử lý sự cố của vendor. Nếu vendor không cung cấp đủ telemetry, ghi rõ điểm mù, bằng chứng thay thế và rủi ro còn lại.

## 10. Sổ đăng ký giới hạn và rủi ro còn lại

Mỗi giới hạn cần có owner và hành động cụ thể. Không ghi “rủi ro thấp” mà không giải thích căn cứ.

| ID | Giới hạn/rủi ro | Tác động | Biện pháp bù | Rủi ro còn lại/owner |
| --- | --- | --- | --- | --- |
| LIM-01 | JWT không có revoke tức thì | Token bị lộ có thể dùng tới exp | TTL ngắn, denylist cho API nhạy cảm | Ghi SLA và owner Identity |
| LIM-02 | Bearer token có thể replay | Attacker dùng token bị đánh cắp | TLS, secure storage, không log token, DPoP/mTLS nếu phù hợp | Owner Client Security |
| LIM-03 | Role claim cũ | Quyền đã thu hồi vẫn nằm trong token | Online policy check hoặc TTL ngắn | Owner Authorization |
| LIM-04 | JWKS cache chậm cập nhật | Token ký bằng key cũ vẫn được xác minh | Cache bound, purge và verifier telemetry | Owner Platform |
| LIM-05 | Introspection dependency outage | Không xác định được trạng thái opaque token | Fail-closed cho API nhạy cảm, HA và alert | Owner Identity/SRE |
| LIM-06 | Thiếu telemetry ở vendor | Chậm điều tra token misuse | Audit API, contract SLA, log correlation | Vendor owner |

Các trường cần có trong risk register đầy đủ:

- ID và mô tả giới hạn.
- Tài sản, luồng và tenant bị ảnh hưởng.
- Threat scenario và điều kiện khai thác.
- Likelihood/impact theo phương pháp đánh giá của tổ chức.
- Biện pháp hiện có và biện pháp bổ sung.
- Residual risk sau biện pháp.
- Owner, approver và ngày chấp nhận rủi ro.
- Ngày rà soát, trigger đánh giá lại và trạng thái remediation.

Rủi ro chỉ được coi là chấp nhận khi người có thẩm quyền chấp thuận theo quy trình của tổ chức. Người viết tài liệu không tự thay mặt business owner chấp nhận rủi ro.

## 11. Logging, metrics và alerting

### Logging an toàn

Ghi sự kiện đủ để điều tra nhưng không ghi credential:

- Timestamp UTC, request/correlation ID.
- Issuer, client ID, subject reference đã được bảo vệ và audience.
- `kid`, token type, decision và reason code.
- Scope cần thiết để phân tích, theo nguyên tắc data minimization.
- API/resource, tenant reference và region.
- Event revoke, refresh reuse, key rotation và policy change.

Không ghi raw access token, refresh token, Authorization header, private key, client secret hoặc cookie session. Nếu cần liên kết token, dùng `jti` đã xác minh hoặc fingerprint/hash được tạo theo chuẩn nội bộ; kiểm soát quyền truy cập log và retention.

### Metrics đề xuất

| Metric | Mục đích |
| --- | --- |
| `token_issuance_total` | Theo dõi số token được cấp theo client/grant |
| `token_validation_failure_total` | Phân loại lỗi chữ ký, issuer, audience, expiration |
| `token_refresh_failure_total` | Theo dõi refresh lỗi và reuse detection |
| `token_revocation_total` | Theo dõi số token/grant bị revoke |
| `revocation_propagation_seconds` | Đo thời gian revoke tới verifier cuối cùng |
| `jwks_cache_age_seconds` | Phát hiện verifier dùng JWKS quá cũ |
| `unknown_kid_total` | Phát hiện rollout sai hoặc token giả |
| `clock_offset_seconds` | Giám sát đồng hồ issuer/verifier |
| `key_sign_operation_failure_total` | Theo dõi lỗi KMS/HSM |
| `post_revoke_accept_total` | Phát hiện token bị revoke vẫn được chấp nhận |

### Alert cần có

- Tăng đột biến token validation failure theo issuer hoặc `kid`.
- Refresh token reuse hoặc refresh từ vị trí/client bất thường.
- Key sign operation lỗi hoặc key state thay đổi ngoài change window.
- JWKS cache vượt giới hạn.
- Revocation propagation vượt SLA.
- Có request thành công bằng token đã revoke.
- Admin role, issuer, redirect URI, audience hoặc signing policy thay đổi bất thường.

Đặt ngưỡng theo baseline và mức độ quan trọng của API. Cảnh báo phải chỉ ra owner, runbook liên quan và mức độ nghiêm trọng; tránh alert không có người nhận xử lý.

## 12. Change management và kiểm soát tài liệu

Tài liệu vận hành cần được quản lý như một phần của hệ thống:

- Mỗi trang có owner, reviewer, version, ngày cập nhật và ngày review tiếp theo.
- Thay đổi token lifetime, issuer, audience, scope, key, JWKS cache hoặc revoke semantics phải cập nhật tài liệu cùng change record.
- Runbook nhạy cảm cần phân quyền đọc; thao tác production cần phân quyền riêng và audit.
- Không đưa secret hoặc giá trị cấu hình nhạy cảm trực tiếp vào tài liệu; tham chiếu secret manager/path có kiểm soát.
- Link tới dashboard, alert, admin console và API docs phải được kiểm tra định kỳ.
- Tài liệu cũ phải được đánh dấu deprecated và trỏ tới phiên bản hiện hành.

### Trigger phải cập nhật tài liệu

| Thay đổi | Tài liệu cần rà soát |
| --- | --- |
| Đổi issuer/JWKS | Trust configuration, validation, rotation runbook |
| Đổi access token TTL/clock skew | Token policy, revocation latency, client behavior |
| Bật refresh rotation | Refresh runbook, reuse detection, recovery |
| Đổi introspection/cache TTL | Availability, revoke SLA, failure mode |
| Thêm API/audience/scope | Resource inventory, authorization contract |
| Thêm tenant hoặc IdP | Trust boundary, isolation, federation mapping |
| Thay vendor/KMS/HSM | Shared responsibility, key lifecycle, incident contacts |

## 13. Template tài liệu vận hành

Có thể dùng cấu trúc sau làm trang gốc:

~~~markdown
# Token Security Operations

## Document control
- Owner:
- Reviewer:
- Version:
- Last reviewed:
- Next review:

## Service overview
- Purpose and scope:
- Environments:
- Issuers and resource servers:
- Trust boundaries:
- Dependencies:

## Token and key inventory
- Token types and audiences:
- Claims and scopes:
- Token lifetimes:
- Signing algorithms and key IDs:
- JWKS/introspection cache:

## Validation contract
- Signature and issuer:
- Audience and token type:
- exp/nbf and clock skew:
- Scope, tenant and object authorization:
- Revocation check:

## Runbooks
- Daily health check:
- Validation failure:
- Refresh failure:
- Planned key rotation:
- Emergency key compromise:
- Token/session revocation:
- Identity provider outage:

## Security limitations
- Known limitations:
- Assumptions:
- Compensating controls:
- Residual risk owners:

## Monitoring and evidence
- Dashboards and alerts:
- Log fields:
- Metrics and SLAs:
- Incident evidence:

## Change and recovery
- Approval:
- Rollback:
- Backup/restore:
- Escalation contacts:
~~~

Template phải được điền bằng thông tin đã xác minh của hệ thống. Nếu chưa biết một thông số, ghi `TBD`, owner và hạn hoàn thành; không tự điền giá trị phỏng đoán.

## 14. Bài tập thực hành

Hãy giả định bạn đang vận hành một hệ thống có:

- Một authorization server phát hành JWT access token.
- Refresh token rotation được bật.
- Ba resource server: Orders, Billing và Files.
- JWKS được cache tại từng resource server.
- Một số API cần kiểm tra revoke qua denylist.

Hoàn thành các đầu việc:

1. Vẽ sơ đồ kiến trúc và đánh dấu trust boundary.
2. Lập inventory token, issuer, audience, scope, lifetime và owner.
3. Viết validation contract cho access token.
4. Viết runbook planned key rotation và tính publish lead/old-key verification window từ cache TTL, token lifetime, clock skew.
5. Viết emergency runbook khi private signing key bị lộ.
6. Viết runbook refresh token bị đánh cắp và xác định cách xử lý access token descendant.
7. Ghi ít nhất năm giới hạn bảo mật, mỗi giới hạn có biện pháp bù và owner.
8. Định nghĩa metrics, alert và SLA revocation propagation.
9. Tổ chức tabletop exercise cho một sự cố token bị replay.
10. Cập nhật tài liệu sau khi ghi nhận kết quả diễn tập và các điểm chưa rõ.

### Kịch bản tabletop

Lúc 09:15, SecOps phát hiện một access token của user thuộc Tenant A xuất hiện trong log của một hệ thống bên ngoài. Token còn hạn 8 phút, có scope `orders.read` và audience `orders-api`. Một request lạ đã được gửi thành công tới Orders API. Refresh token của user chưa rõ có bị lộ hay không.

Đội vận hành phải trả lời:

- Ai là incident commander và ai sở hữu authorization server/Orders API?
- Dùng token ID/fingerprint nào để truy tìm mà không phát tán raw token?
- Có thể revoke token cụ thể hay phải revoke session/refresh family?
- JWT có denylist không? Nếu có, mọi replica nhận trạng thái trong bao lâu?
- Làm sao xác minh request sau revoke bị từ chối và không có side effect?
- Có cần kiểm tra Billing/Files API hay các token khác của subject không?
- Bằng chứng nào được lưu, ai được truy cập và khi nào incident được đóng?

Sau diễn tập, ghi lại quyết định, thời gian từng bước, điểm nghẽn, giả định chưa được kiểm chứng và action item có owner/deadline. Không biến kịch bản giả định thành sự cố production thật.

## 15. Tiêu chí nghiệm thu

| Hạng mục | Điều kiện đạt |
| --- | --- |
| Kiến trúc | Sơ đồ thể hiện issuer, verifier, key store, cache và trust boundary |
| Inventory | Mọi token type có purpose, issuer, audience, lifetime, revoke và owner |
| Validation | Có contract cho chữ ký, issuer, audience, expiration, scope, tenant và trạng thái revoke |
| Runbook | Mỗi thao tác có trigger, quyền, bước làm, verify, rollback/escalation |
| Security limitations | Có giới hạn, tác động, biện pháp bù và owner chấp nhận residual risk |
| Observability | Có metrics, alert, dashboard, log fields và cách không lộ secret |
| Incident response | Có quy trình token theft, refresh compromise và signing-key compromise |
| Review | Có owner, version, approval và lịch rà soát |
| Exercise | Tabletop được thực hiện và action item được theo dõi |

## 16. Checklist trước khi công bố

- [ ] Tài liệu xác định rõ phạm vi, người đọc và owner.
- [ ] Sơ đồ thể hiện trust boundary và luồng token.
- [ ] Token inventory có issuer, audience, scope, lifetime và revoke semantics.
- [ ] Validation contract phân biệt authentication, scope và object-level authorization.
- [ ] Runbook có điều kiện kích hoạt, quyền, bước thực hiện và tiêu chí hoàn tất.
- [ ] Planned rotation và emergency rotation được mô tả riêng.
- [ ] Có cách xử lý refresh token theft, token replay và key compromise.
- [ ] Failure mode của authorization server, JWKS, introspection, KMS và time service đã được ghi.
- [ ] Security limitations có tác động, biện pháp bù và owner.
- [ ] Metrics/alerts có ngưỡng và người nhận xử lý.
- [ ] Không có raw token, secret, private key hoặc dữ liệu production nhạy cảm.
- [ ] Thao tác production có approval, audit và rollback/escalation.
- [ ] Tabletop exercise đã được thực hiện và action item có người phụ trách.
- [ ] Tài liệu có version, ngày review và trigger cập nhật.

## Ghi nhớ

**Tài liệu vận hành tốt phải biến policy bảo mật thành hành động có thể thực hiện và xác minh.** Hãy mô tả ai làm gì, trong điều kiện nào, qua công cụ nào và bằng chứng nào chứng minh thao tác hoàn tất. Phần giới hạn bảo mật cần nói thẳng những gì token không bảo đảm, ví dụ JWT không tự revoke tức thì, bearer token có thể replay và claims có thể cũ. Khi giới hạn được ghi cùng biện pháp bù, owner và residual risk, đội vận hành có thể xử lý sự cố nhất quán và chủ sở hữu dịch vụ có cơ sở để ra quyết định.

### Tài liệu tham khảo

- IETF RFC 7519 — JSON Web Token (JWT): https://www.rfc-editor.org/rfc/rfc7519
- IETF RFC 7517 — JSON Web Key (JWK) và JWKS: https://www.rfc-editor.org/rfc/rfc7517
- IETF RFC 6749 — The OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- IETF RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009
- IETF RFC 7662 — OAuth 2.0 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
- IETF RFC 9700 — Best Current Practice for OAuth 2.0 Security: https://www.rfc-editor.org/rfc/rfc9700
- NIST SP 800-61 Rev. 2 — Computer Security Incident Handling Guide: https://csrc.nist.gov/pubs/sp/800/61/r2/final
- NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management: https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
