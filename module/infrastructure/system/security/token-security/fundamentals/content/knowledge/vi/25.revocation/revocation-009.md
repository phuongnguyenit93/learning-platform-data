# Admin revoke sau incident

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **admin revoke sau incident** là hành động quản trị nhằm vô hiệu hóa credential, grant hoặc session có rủi ro trước thời điểm hết hạn bình thường.
- Xác định đúng **đối tượng thu hồi**: access token (AT), refresh token (RT), cả refresh-token family, authorization grant, phiên ứng dụng/SSO, client credential, client registration hoặc signing key.
- Phân biệt **RFC 7009 Token Revocation** với các **administrative revocation API** riêng; hiểu vì sao response thành công từ AS chưa chứng minh mọi Resource Server (RS) đã chặn token.
- Thiết kế quy trình phát hiện, khoanh vùng, xác thực quyền admin, phê duyệt, thực hiện, phát tán trạng thái, kiểm chứng hiệu lực và phục hồi sau sự cố.
- Hiểu cơ chế thu hồi của **opaque token qua introspection** so với **JWT offline**, cache/denylist và giới hạn propagation.
- Giải quyết race condition giữa revoke và refresh, token reuse, duplicate requests, multi-tenant và multi-RS.
- Xây dựng playbook ứng phó token theft, RT reuse, client-secret compromise, signing-key compromise và account takeover.
- Đọc ví dụ HTTP, Mermaid, Java/pseudocode, negative tests và checklist vận hành production.

## 1. Admin revoke là gì trong vòng đời token?

Một OAuth 2.0 access token có vòng đời khái quát:

~~~text
Authorization Server cấp access token
    -> client lưu/nhận credential
    -> client gửi token đến Resource Server
    -> RS kiểm issuer, audience, scope, expiry và trạng thái
    -> token hết hạn hoặc bị thu hồi
    -> client phải có grant hợp lệ để lấy token mới
~~~

**Admin revoke** là lệnh được một **security administrator/incident responder được ủy quyền** thực hiện nhằm chặn việc tiếp tục sử dụng token hoặc nguồn cấp token, khi credential hoặc phiên không còn đáng tin cậy.

Ví dụ:

- Access token bị đưa nhầm vào log, mã nguồn, bản dump hoặc ticket.
- Refresh token bị lấy trộm hoặc phát hiện **refresh-token reuse**.
- Tài khoản user bị chiếm quyền, thiết bị thất lạc hoặc phiên SSO bị lạm dụng.
- Client secret, private key, mTLS credential của workload bị lộ.
- JWT signing private key của Authorization Server bị nghi ngờ xâm phạm.
- AS phát token có scope/audience quá rộng do cấu hình sai.
- Một nhân viên nghỉ việc nhưng grant/token trên thiết bị cũ vẫn còn hiệu lực.

**Revoke không đồng nghĩa xóa sự cố đã xảy ra.** Nó chặn nguy cơ tiếp diễn, trong khi đội ứng phó vẫn cần điều tra dữ liệu đã bị truy cập, hành động đã thực hiện và nguyên nhân rò rỉ.

### Ai chịu trách nhiệm?

- **Authorization Server (AS)** quản lý phát hành token, RT/grant/client status và key material theo thiết kế.
- **Resource Server (RS)** thực thi việc chấp nhận hoặc từ chối access token tại endpoint.
- **Relying Party (RP)/OP** nếu có OIDC có thể quản lý các phiên SSO và cookie session riêng.
- **Admin** được phép yêu cầu hành động trong một phạm vi issuer/tenant/client nhất định.
- **Client** có thể vẫn giữ bản sao token đã bị thu hồi; điểm mấu chốt là AS/RS không cho credential đó tiếp tục được sử dụng.

## 2. Revoke ở AS không tự động đồng nghĩa token bị từ chối ở mọi RS

Giả sử AS phát một JWT access token:

~~~text
iss = https://identity.example.test
aud = https://orders.example.test/api
scope = orders:read
jti = token-123
exp = còn 15 phút
~~~

Admin đánh dấu jti=token-123 là revoked trong database AS. Tuy nhiên Orders API đang **xác minh JWT offline**, không hỏi AS:

~~~text
signature valid: yes
issuer trusted: yes
audience correct: yes
expiration valid: yes
scope granted: yes
~~~

Nếu không có cơ chế trạng thái, Orders API có thể **vẫn nhận token** cho đến exp dù AS đã ghi revoked=true.

Với opaque token, RS thường hỏi introspection endpoint và có thể nhận active=false; nhưng nếu RS giữ cache active=true thì việc thu hồi cũng có **độ trễ**.

Cần phân biệt rõ bốn khái niệm:

1. **Control-plane revocation**: AS ghi trạng thái bị thu hồi.
2. **Issuance prevention**: client/attacker không dùng RT/grant/credential cũ xin AT mới.
3. **Data-plane enforcement**: RS thực tế không chấp nhận AT đã thu hồi.
4. **Propagation verification**: đo được quá trình RS/gateway/cache cập nhật trạng thái trong SLO yêu cầu.

**Chỉ thấy HTTP 200 từ lệnh revoke không đủ để đóng incident.**

## 3. Thu hồi chính xác đối tượng nào?

| Đối tượng | Hành động mong muốn | Điều không tự xảy ra |
| --- | --- | --- |
| **Một access token** | RS từ chối AT đó trong SLO. | RT cùng grant cũng bị khóa nếu không có policy liên đới. |
| **Refresh token hiện tại** | Không dùng RT đó xin AT mới. | Cả rotation family tự mất hiệu lực nếu không có family logic. |
| **Refresh-token family** | Chặn toàn bộ RT thuộc chuỗi rotation bị ảnh hưởng. | AT đã cấp trước đó tự bị mọi RS offline từ chối. |
| **Authorization grant** | Chặn issuance tiếp theo theo grant và revoke token liên quan theo policy. | OP/SSO session hoặc RP cookie tự hết hạn. |
| **Application session** | Cookie/session của RP không còn được dùng. | AT/RT nằm ngoài session bị revoke. |
| **OP/SSO session** | Chấm dứt phiên xác thực tại OP. | Mọi ứng dụng RP đã đăng nhập lập tức đóng phiên. |
| **Client secret/private key** | Credential cũ không xác thực client tại AS được nữa. | AT trước đó mất hiệu lực ở RS offline. |
| **Client registration** | Không cho client tiếp tục grant/token issuance. | Mọi token cũ tự bị chặn ngay. |
| **Signing key** | RS không còn tin token ký bằng khóa bị nghi lộ. | Có thể loại riêng token giả mà giữ mọi token thật ký cùng key. |
| **Role/permission** | Chặn nghiệp vụ mà principal không còn quyền. | Claims và permission cache cũ tự cập nhật ngay. |

### Hẹp nhất còn an toàn, rộng hơn khi bằng chứng chưa đủ

- Nếu chỉ lộ **một AT**, RT/client credential được chứng minh vẫn an toàn: có thể revoke AT cụ thể và kiểm lạm dụng.
- Nếu lộ **RT**, phải cân nhắc revoke **cả family** và AT đã phát từ family.
- Nếu **client secret** bị lộ, chỉ revoke một AT là chưa đủ vì attacker có thể xin AT mới.
- Nếu **signing key AS** bị lộ, denylist các jti nhìn thấy có thể không đủ vì attacker có thể tự ký JWT giả.

### Không dùng “revoke all” mà không nói phạm vi

~~~text
Revoke all:
    của user nào?
    issuer nào?
    tenant nào?
    client hoặc device nào?
    all access tokens hay all refresh-token families?
    grant có bị đóng?
    SSO/app sessions có bị terminate?
    có ảnh hưởng toàn bộ môi trường prod không?
~~~

Admin UI, API và runbook cần hiển thị rõ **đối tượng, phạm vi, hậu quả và độ trễ thực thi**.

## 4. Phân loại incident và phạm vi phản ứng

| Loại incident | Containment ban đầu | Điều cần đánh giá thêm |
| --- | --- | --- |
| AT lộ ở log | Revoke AT, dừng kênh rò rỉ. | Access logs, cache/RS enforcement, dữ liệu đã bị truy cập. |
| AT bị công khai | Revoke AT khẩn, xác định audience và thời gian. | Có RT/client credential cùng bị lộ không? |
| RT bị đánh cắp hoặc reuse | Revoke RT family/grant. | AT đã cấp, device/session, reauthentication. |
| Account takeover | Vô hiệu sessions và grants liên quan. | MFA factors, account recovery, hoạt động bất thường. |
| Client secret leak | Disable/rotate secret. | Revoke tokens/grants đã phát và kiểm hoạt động client. |
| Workload private key leak | Thay key/cert/workload identity. | Quét token issuance bất thường, cô lập runtime. |
| Signing private key leak | Xử lý emergency key trust, rotation. | JWT giả, tác động hàng loạt, JWKS/cache. |
| AS cấp sai scope/aud | Khóa policy sai, ngăn cấp mới. | Thu hồi token sai, kiểm dữ liệu đã truy cập. |
| Thiết bị thất lạc | Vô hiệu device-specific grant/session/RT. | Những AT đang còn hạn và lưu trên device. |

**Đây là khung đánh giá, không phải chính sách áp dụng mù quáng.** Mức độ ảnh hưởng đến vận hành phải được cân đối với rủi ro và ghi trong incident record.

## 5. Playbook tổng thể: phát hiện → revoke → kiểm chứng

~~~mermaid
flowchart TD
    A["Phát hiện token/credential compromise"] --> B["Tạo incident ID, giữ evidence an toàn"]
    B --> C["Xác định issuer, client, subject, tenant, resource, grant"]
    C --> D{"Admin có đủ quyền và approval?"}
    D -->|Không| E["Escalate và containment theo quyền sẵn có"]
    D -->|Có| F["Chọn scope revoke theo blast radius"]
    F --> G["Ghi trạng thái revoke có kiểm soát/idempotent"]
    G --> H["Chặn token issuance mới, phát tán state"]
    H --> I["Kiểm AS, RS, gateway, cache và session theo scope"]
    I --> J{"Enforcement đạt SLO?"}
    J -->|Không| K["Escalate: cache flush, emergency deny, key action"]
    K --> I
    J -->|Có| L["Điều tra hậu quả, phục hồi, ghi postmortem"]
~~~

### 5.1 Triage và evidence

Cần ghi:

- Incident ID, thời điểm phát hiện và nguồn cảnh báo.
- Issuer, client_id, tenant, resource audience, token/grant/session/device ID nếu có.
- Token type, hạn sử dụng, môi trường và hệ thống RS có liên quan.
- Dấu hiệu replay, unusual geography, token issuance, refresh reuse.
- Kiểu validation RS: JWT offline, introspection, gateway hoặc kết hợp.
- Mục tiêu SLO **ngăn cấp mới** và **ngăn request bằng token cũ**.
- Người quyết định và người phê duyệt mở rộng phạm vi.

**Không copy raw AT/RT vào ticket/chat**. Dùng token identifier, HMAC fingerprint/lookup handle hoặc thông tin audit đã được phân quyền.

### 5.2 Containment khi bằng chứng chưa hoàn chỉnh

Khi nguy cơ cao, có thể phải disable grant/client hoặc khóa tài khoản trước khi điều tra đủ. Phải ghi nhận phạm vi ảnh hưởng hợp pháp, người phê duyệt và kế hoạch khôi phục.

### 5.3 Sau revoke phải kiểm cả hai đường

- **Issuance path**: RT/grant/client credential bị lộ không thể phát sinh AT mới.
- **Resource path**: RS thực sự từ chối AT bị thu hồi theo SLO và không dùng cached authentication quá thời hạn.

Việc DB trả revoked=true **chưa tự chứng minh** RS đã áp chặn.

## 6. Bảo vệ thao tác admin revoke

Endpoint admin revoke là công cụ mạnh có thể làm gián đoạn cả công ty hoặc toàn bộ tenant.

Các kiểm soát nên có:

- MFA mạnh, step-up hoặc phishing-resistant factor cho thao tác nhạy cảm.
- RBAC/ABAC theo role admin, tenant, environment, issuer, loại token và resource.
- **JIT elevation** hoặc quyền thời hạn ngắn thay vì mọi nhân viên hỗ trợ đều có quyền vĩnh viễn.
- **Dual control/approval** cho revoke diện rộng, khóa ký hoặc ngừng client production quan trọng.
- Kiểm soát phạm vi ở backend; **không tin UI đã ẩn tùy chọn**.
- Bảo vệ CSRF nếu admin console dùng cookie; chống replay/idempotency cho API.
- Ghi **who/what/why/when/scope/outcome** trong audit chống sửa/xóa.
- Không cho phép admin không đủ quyền dò sự tồn tại token của tenant khác.
- Break-glass được ghi nhận, giám sát độc lập và review sau sử dụng.
- Hạn chế raw token/secret xuất hiện trong form, log hoặc response.

Ví dụ kiểm quyền:

~~~text
Admin được phép:
    tenant-blue, revoke_user_grant

Request:
    targetTenant = tenant-green

Result:
    DENY, dù admin có thể xem UI của tenant-blue
~~~

**Không lấy request JSON có isSuperAdmin=true hoặc approved=true làm chứng cứ đã được nâng quyền.**

## 7. RFC 7009 Token Revocation khác admin revoke thế nào?

**RFC 7009** định nghĩa OAuth 2.0 revocation endpoint để **client** yêu cầu AS thu hồi token.

Ví dụ:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: identity.example.test
Authorization: Basic EXAMPLE_REGISTERED_CLIENT_AUTH
Content-Type: application/x-www-form-urlencoded

token=EXAMPLE_REFRESH_TOKEN&token_type_hint=refresh_token
~~~

Đây là request minh họa, phải dùng HTTPS và xác thực client theo registration. Không log body chứa token.

Những điểm quan trọng:

1. **token** là field bắt buộc; **token_type_hint** chỉ để AS tối ưu lookup, không chứng minh token type.
2. AS xác thực/ủy quyền client đang yêu cầu revoke.
3. **HTTP 200** được dùng cho token được revoke hoặc token không hợp lệ/không tồn tại, giảm khả năng token enumeration.
4. Lỗi **unsupported_token_type** có thể được trả nếu AS không hỗ trợ loại token được chỉ định theo RFC.
5. Thu hồi RT có thể kéo theo vô hiệu các AT liên quan tùy chính sách/triển khai; thu hồi AT không tự đồng nghĩa RT/grant/session đã đóng.
6. Phải hiểu quy tắc của **AS cụ thể** để biết hiệu lực dây chuyền.

### Administrative revocation API không được RFC 7009 chuẩn hóa thống nhất

Security admin có thể phải revoke theo:

~~~text
user_id
tenant_id
client_id
grant_id
session_id
device_id
refresh_token_family_id
signing_key_id
~~~

Đó là hành động **management plane** do hệ thống/vender thiết kế, không phải một tiêu chuẩn OAuth chung có sẵn endpoint “admin revoke everything”.

Nếu admin API dùng RFC 7009 dưới lớp triển khai, backend vẫn phải **kiểm role/tenant/approval**, mapping token ownership và audit. Không trao cho một backend privileged khả năng gửi raw token bất kỳ tới AS mà không có policy.

### HTTP success không đồng nghĩa RS đã chặn

Response HTTP 200 chỉ xác nhận request được AS xử lý theo contract, **không chứng minh JWT offline, gateway hay introspection cache đã cập nhật**. Cần validation/acknowledgment riêng.

## 8. Revoke access token bị lộ

Ví dụ một JWT AT có claims minh họa:

~~~json
{
  "iss": "https://identity.example.test",
  "aud": "https://orders.example.test/api",
  "client_id": "dashboard-web",
  "sub": "user-42",
  "scope": "orders:read",
  "jti": "example-token-123",
  "iat": 1730000000,
  "exp": 1730000900
}
~~~

Payload giả, không phải token có chữ ký hoặc thời hạn còn hiệu lực.

**Các bước nên cân nhắc:**

1. Xác định issuer, aud, client/grant, token identifier và expiry từ **metadata đáng tin**.
2. Xác định Orders RS kiểm JWT offline, introspection hay qua gateway.
3. Ghi revoked token ID/state ở AS hoặc hệ thống status authoritative.
4. Phát event/invalidate cache/cập nhật denylist RS khi cần.
5. Xác nhận API từ chối AT trong SLO; nếu RS không thể cập nhật kịp, dùng emergency policy block theo runbook.
6. Kiểm request thực hiện trong thời gian lộ token, ghi nhận impact và tiến hành xử lý dữ liệu nếu cần.
7. Khắc phục nơi làm lộ token và tăng redaction.

Không yêu cầu user copy nguyên AT vào ticket để test; dùng token ID, fingerprint hoặc canary có kiểm soát.

### Chỉ revoke AT có thể chưa đủ

Nếu attacker còn **RT, client credential hoặc OP session** liên quan, chúng có thể xin token mới. Triage phải xác định **nguồn token** có còn bị compromise hay không, không tự dừng ở revoke một token string.

## 9. Refresh token bị đánh cắp hoặc phát hiện reuse

Refresh token thường có khả năng xin access token mới qua token endpoint. Vì vậy **thu hồi một AT không ngăn được attacker tiếp tục lấy AT khác nếu RT vẫn dùng được**.

### Rotation family và reuse detection

Trong nhiều triển khai, refresh token rotation có cấu trúc:

~~~text
RT-1 --refresh--> RT-2 --refresh--> RT-3

Cùng grant_id và family_id.
Mỗi RT cũ chỉ được dùng theo chính sách một lần.
~~~

Nếu sau khi RT-2 đã bị thay bằng RT-3 mà RT-2 được trình lại, hệ thống có thể coi là **reuse signal**. Không phải lần reuse nào cũng chứng minh attacker có RT; mạng/retry/race có thể tạo trùng request. Nhưng khi không thể xác định bên hợp pháp, policy an toàn có thể **revoke cả family** và yêu cầu reauthentication.

~~~mermaid
sequenceDiagram
    participant C as Legitimate Client
    participant X as Attacker
    participant AS as Authorization Server

    C->>AS: Refresh RT-2
    AS->>AS: Kiểm ACTIVE và atomically rotate
    AS-->>C: AT-3 + RT-3
    X->>AS: Thử dùng RT-2 đã rotated
    AS->>AS: Phát hiện reuse / policy
    AS->>AS: Revoke family, chặn cấp AT mới
    AS-->>X: invalid_grant
    C->>AS: Thử dùng RT-3
    AS-->>C: invalid_grant sau family revocation
~~~

### Admin action khi nghi RT bị lộ

1. Xác định **issuer, client, grant_id, family_id, principal, device** bằng dữ liệu tin cậy.
2. Revoke **family hoặc grant** nếu risk policy đòi hỏi, không chỉ RT hiện tại đang nhìn thấy.
3. Xử lý **AT đã phát từ family**: revoke riêng, denylist hoặc chấp nhận TTL theo SLO đã định.
4. Chặn grant/token issuance cũ và yêu cầu người dùng đăng nhập lại.
5. Kiểm dấu hiệu thiết bị nhiễm mã độc, browser XSS, log/backup chứa token, session hijack.
6. Audit refresh attempts theo token identifier/fingerprint, không ghi raw RT.

### Race giữa refresh và revoke

Tình huống nguy hiểm:

~~~text
Thread A: kiểm family ACTIVE.
Thread B: admin đặt family REVOKED.
Thread A: vẫn tạo và commit RT-NEW + AT-NEW.
~~~

**Revoke phải thắng hoặc đồng bộ với phát token mới** theo cơ chế giao dịch/quy tắc version.

Một cách mô hình hóa:

~~~text
BEGIN TRANSACTION
  LOCK grant/family row
  VERIFY family.status == ACTIVE
  VERIFY client/session/grant allowed
  ROTATE old RT atomically
  ISSUE new token record tied to same current grant generation
COMMIT
~~~

Admin revoke:

~~~text
BEGIN TRANSACTION
  LOCK grant/family row
  SET status = REVOKED
  INCREMENT generation
  PERSIST audit/outbox
COMMIT
~~~

Nếu request refresh đang chạy, nó phải thấy generation/status mới hoặc bị conflict và từ chối. Chi tiết locking, isolation, issuance commit và token signing phải được thiết kế để **không phát token hữu dụng sau thời điểm revoke thắng**. Một access token đã được phát trước commit revoke vẫn cần data-plane enforcement.

### Không nhầm retry hợp pháp với token reuse

Refresh clients cần single-flight, retry/idempotency strategy phù hợp; nhưng AS **không dùng “network retry” làm lý do chấp nhận vô hạn RT đã rotated**. Nếu cần grace window, phải giới hạn rủi ro, chứng minh sender và tuân chính sách được kiểm toán.

## 10. Account takeover, SSO và application session

Một người dùng có thể có:

~~~text
OP/SSO session cookie
    ├── OAuth grant for dashboard-web
    │     ├── RT family for browser/device A
    │     └── ATs for Orders API
    └── OAuth grant for mobile-app
          ├── RT family for device B
          └── ATs for Reports API

Dashboard app session cookie
Mobile app local session
~~~

Nếu tài khoản bị chiếm, **chỉ revoke AT Orders** chưa đủ để chặn attacker sử dụng session/RT khác.

### Các lớp cần đánh giá

| Lớp | Thao tác có thể cần | Giới hạn |
| --- | --- | --- |
| **RP application session** | Terminate phiên/cookie cụ thể hoặc mọi phiên của account. | Không mặc định revoke AT/RT được lưu ở client khác. |
| **OP/SSO session** | Terminate session tại OP theo giao thức hỗ trợ. | Các RP đã có session riêng có thể chưa nhận logout. |
| **OAuth grants** | Thu hồi grant/client/device liên quan. | AT offline cần enforcement bổ sung. |
| **Refresh-token families** | Ngăn tiếp tục đổi token. | Không chặn AT trước đó nếu RS chưa cập nhật. |
| **User credentials/factors** | Reset password, khóa recovery factor, thay security factor khi cần. | Không tự chấm dứt mọi token/credential đã phát. |
| **RS permission** | Khóa account/tenant action theo risk policy. | Phải lan đến RS và cache quyền. |

**OIDC logout** (front-channel/back-channel hoặc RP-Initiated Logout theo khả năng triển khai) có thể hỗ trợ chấm dứt phiên, nhưng **không tự là RFC 7009 token revocation**. Cần xác định liệu AS có xử lý revoke tokens khi logout theo chính sách cụ thể hay không.

### Reauthentication sau containment

Sau khi revoke, người dùng hợp pháp cần một đường khôi phục:

- Xác minh danh tính bằng kênh không bị nghi xâm phạm.
- Reset credential/factor đã lộ, đăng xuất phiên cũ.
- Cấp mới grant/tokens/session theo policy.
- Tránh cho attacker dùng **recovery channel** đã bị chiếm để tạo phiên mới.
- Thông báo hoạt động bất thường bằng nội dung không làm lộ thông tin incident nhạy cảm.

Không tự mở lại RT family đã bị revoke chỉ để người dùng hết lỗi đăng nhập.

## 11. Client secret, private key và workload compromise

Với **client_credentials grant**, một attacker có client secret hoặc private key của workload có thể xin **nhiều access token mới** nếu AS vẫn chấp nhận credential.

Một service:

~~~text
client_id = payments-batch-worker
grant = client_credentials
allowed_resource = payments-api
scope = payments:reconcile
~~~

Nếu secret bị lộ, chỉ revoke AT hiện tại không đủ.

### Playbook tối thiểu

1. Xác định credential **cụ thể** đã lộ: client secret version, private_key_jwt key, mTLS certificate hoặc cloud workload identity.
2. **Disable/revoke credential cũ**, có thể đồng thời khóa client grant nếu không xác định được phạm vi.
3. Issue và triển khai credential mới qua secret manager/certificate lifecycle **sau khi runtime an toàn**.
4. Phân tích token issuance theo client, key/certificate, timeframe và audience; thu hồi AT liên quan theo risk policy.
5. Kiểm API usage, dữ liệu truy cập, thay đổi bị thực hiện và việc token forwarding.
6. Kiểm thử client credential cũ không xin token mới được; credential mới chỉ có scope/resource tối thiểu.
7. Đảm bảo logs và deployment artifacts không còn rò rỉ secret cũ.

### Rotate không đồng nghĩa revoke

Nếu hệ thống hỗ trợ **hai client secret song song** trong giai đoạn chuyển đổi, thao tác **tạo secret mới** không tự khiến secret cũ ngừng hoạt động. Phải biết chính xác thời điểm **disable old secret** và xác nhận AS từ chối xác thực bằng nó.

### Không tạo downtime không kiểm soát

Với service quan trọng, cần plan failover/credential rollout. Nhưng đừng kéo dài cửa sổ attacker còn dùng secret bị lộ chỉ để tránh lỗi. Có thể tạm dừng workload, giới hạn scope/issuer/audience hoặc thực hiện break-glass theo approval.

## 12. AS signing key compromise: phạm vi khác hoàn toàn AT/RT theft

Khi private signing key của AS bị lộ, attacker có thể ký **JWT giả** mà RS chấp nhận nếu RS vẫn tin public key tương ứng.

**Đây là sự cố về gốc tin cậy**, khác với đánh cắp một JWT duy nhất.

~~~text
AS trusted signing key K-old
    -> nhiều JWT hợp lệ đã phát
    -> RS tin K-old trong JWKS/cache

Attacker có K-old:
    -> có thể tạo JWT mới với claims nguy hiểm
    -> RS có thể tin chữ ký nếu K-old vẫn là trusted key
~~~

### Vì sao denylist jti không đủ?

Attacker có thể tự đặt một jti mới cho JWT giả. Nếu RS chỉ chặn các jti đã biết là bị lộ, token giả khác có thể vượt qua.

### Playbook cấp cao

1. **Cô lập signing infrastructure** và dừng tiếp tục sử dụng key bị nghi ngờ.
2. **Rotate đến key sạch** được tạo/quản lý bởi môi trường tin cậy.
3. **Loại key bị compromise khỏi trust set**, cập nhật JWKS/verification configuration, xử lý cache của mọi RS theo emergency SLO.
4. **Đánh giá tác động đến các token hợp lệ** đã ký bằng key cũ; có thể cần buộc tất cả client xin token mới.
5. Dùng giải pháp stateful/introspection/emergency deny nếu quá trình JWKS propagation chưa đủ nhanh và risk policy cho phép.
6. Rà soát issuer/algorithm allowlist, token type/audience validation, key ID handling và dấu hiệu JWT forged.
7. Thực hiện key lifecycle incident documentation, audit và bảo đảm không tái dùng key cũ.

### JWKS cache là một nguồn trễ

Một RS có thể đã cache public key K-old trong nhiều giờ. AS chỉ xóa key khỏi endpoint JWKS **chưa bảo đảm RS lập tức quên key**. Cần quản lý cache invalidation, restart/refresh đúng chuẩn, metrics và xác nhận thực tế với từng RS.

**Không cho RS tải khóa từ URL tự khai trong JWT header** để “nhanh sửa” sự cố; đó là một trust-boundary risk khác.

## 13. Opaque token qua introspection và revocation

Với opaque AT:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Orders RS
    participant AS as AS Token Store
    participant ADM as Admin

    C->>RS: Bearer opaque-T
    RS->>AS: Introspect opaque-T
    AS-->>RS: active=true, aud=Orders, scope=orders:read
    ADM->>AS: Revoke opaque-T / grant
    AS->>AS: Mark inactive
    C->>RS: Bearer opaque-T lần nữa
    RS->>AS: Re-introspect khi cache miss/TTL hết
    AS-->>RS: active=false
    RS-->>C: 401 invalid_token
~~~

Ưu điểm là AS có thể cập nhật trạng thái tập trung. Nhưng RS có thể cache kết quả:

~~~text
10:00:00 introspection active=true
10:00:30 admin revoke tại AS
10:01:00 RS còn cached active=true
10:02:00 cache hết hạn; RS nhận active=false
~~~

**Revocation latency** tối đa phải được đánh giá theo TTL cache, dữ liệu phân tán và trạng thái API.

### Kiểm sai lầm thường gặp

Không:

~~~text
if response.active == true:
    allowEverything()
~~~

RS vẫn kiểm:

- token type là **access token**, không phải RT/ID token.
- issuer và audience đúng RS.
- scope và quyền nghiệp vụ.
- time constraints nếu contract yêu cầu.
- principal/service identity, tenant/ownership.
- sender proof nếu dùng DPoP/mTLS-bound token.

Nếu introspection timeout/HTTP 503, **không tự chấp nhận token vì AS đang lỗi**. Có thể dùng cache còn hợp lệ theo chính sách nếu đã thiết kế; không giữ cache quá hạn tùy ý.

## 14. JWT offline: denylist, revocation version và TTL

Một RS xác minh JWT chỉ với **chữ ký + claims** sẽ không nhìn thấy thay đổi trạng thái ở AS. Các chiến lược bổ sung:

| Cơ chế | Cách hoạt động | Giới hạn |
| --- | --- | --- |
| **AT TTL ngắn** | Token tự hết hạn nhanh hơn. | Không chặn tức thời trước exp. |
| **Denylist theo token identifier** | RS kiểm jti/fingerprint đã bị revoke. | Cần phân phối trạng thái, giới hạn storage/lookup. |
| **Version/generation theo grant/session** | Token mang version; RS so với trạng thái hiện hành. | Cần lookup/cached version và giao thức đồng nhất. |
| **Token introspection** | RS hỏi AS về trạng thái token. | Latency/availability/cache. |
| **Emergency permission block** | RS chặn client/principal/tenant/route theo incident. | Dễ ảnh hưởng user hợp pháp, cần scope cụ thể. |
| **Signing key trust removal** | RS ngừng tin JWT ký bởi key bị lộ. | Có thể vô hiệu hóa hàng loạt token hợp lệ. |

### Denylist key phải không mơ hồ

Không chỉ dùng jti nếu nhiều issuer có thể phát trùng identifier. Một cấu trúc có thể là:

~~~text
denyKey = (trustedIssuer, jti, expectedTokenProfile)
expiresAt = token.exp + boundedClockSkew
~~~

Hoặc sử dụng HMAC/token fingerprint theo hợp đồng đã đánh giá. Chỉ tin jti **sau khi JWT đã được xác minh**; không tạo quyền từ unverified payload.

### Không lưu denylist vĩnh viễn nếu không cần

Nếu token hết hạn tại exp, entry denylist có thể được dọn theo exp + skew/retention policy. Tập trạng thái revoke dài hạn cho grant/session thì quản lý riêng, không ép mọi jti tồn tại mãi mãi.

### Phiên bản grant không phải client token version toàn cục

Một user có nhiều thiết bị/grant. Nếu chỉ muốn revoke device A, key/generation cần ràng đúng **grant/session/device**. Dùng user-wide version cho mọi incident có thể tạo downtime lớn; nhưng khi account compromise diện rộng, user-wide block lại có thể cần. Chọn theo phạm vi đã được duyệt.

## 15. Phát tán trạng thái đến nhiều Resource Server

Sau khi admin revoke tại AS, có thể cần cập nhật:

~~~text
Authorization Server / Revocation Store
    |
    | durable outbox event
    v
Message Broker / Control Channel
    |
    +--> Orders RS denylist/cache invalidation
    +--> Payments RS denylist/cache invalidation
    +--> API Gateway token cache invalidation
    +--> Authz policy service version update
    +--> Session management / RP logout handler (nếu áp dụng)
~~~

### Event tối thiểu

Một event minh họa không chứa raw token:

~~~json
{
  "event_id": "evt-example-105",
  "incident_id": "inc-example-874",
  "issuer": "https://identity.example.test",
  "target_kind": "REFRESH_TOKEN_FAMILY",
  "target_id": "family-example-72",
  "revocation_generation": 16,
  "effective_at": "2026-11-23T00:00:00Z",
  "reason_code": "SUSPECTED_CREDENTIAL_THEFT"
}
~~~

Các ID là dữ liệu giả. **Event schema nội bộ không phải RFC 7009.**

### Delivery và ordering

- Có **transactional outbox** hoặc giải pháp tương đương để trạng thái revoke và event không lệch nhau.
- Consumer phải **idempotent** vì broker có thể giao event trùng.
- So **generation/version**, không cho event cũ ghi đè trạng thái revoked mới.
- Có replay/backfill hoặc snapshot khi RS bị offline.
- Quan sát dead-letter queue, event lag và số RS chưa áp trạng thái.
- Nếu event bị mất, phải có **periodic reconciliation** với authoritative store.
- Không chỉ dựa vào message success của broker để tuyên bố RS đã thực thi deny rule.

### Định nghĩa điểm thành công

Thành công có thể tách:

~~~text
ACCEPTED:
    Admin request được tiếp nhận hợp lệ.

COMMITTED:
    Authoritative revocation state đã được lưu.

PROPAGATING:
    Đang gửi tới các enforcement points.

ENFORCED:
    Các RS bắt buộc đã xác nhận hoặc kiểm thử đạt.

PARTIALLY_ENFORCED:
    Một số RS chưa cập nhật.

FAILED:
    Không commit được hoặc không thể xác minh trong SLO.
~~~

Những trạng thái này chỉ là mô hình gợi ý. **Không gắn nhãn Completed quá sớm** nếu một API quan trọng vẫn nhận credential.

## 16. Revoke phải nguyên tử, monotonic và idempotent

Security admin có thể bấm revoke hai lần, ứng dụng retry do timeout, hoặc message broker giao cùng event nhiều lần. Kết quả đúng là **credential vẫn bị thu hồi**; việc retry không tái kích hoạt grant hay tạo trạng thái mâu thuẫn.

Các thuộc tính mong muốn:

1. **Monotonic:** trạng thái REVOKED không trở lại ACTIVE do event/response cũ đến muộn.
2. **Idempotent:** retry cùng actor, target, action và idempotency key cho cùng kết quả.
3. **Atomic:** thay đổi grant/token state và ghi audit/outbox cùng transaction, hoặc một cơ chế consistency tương đương.
4. **Versioned:** tăng generation/version để consumer bỏ qua event cũ.
5. **Durable:** AS vẫn nhớ revocation sau restart.
6. **Least-scoped:** không vô tình vô hiệu tenant hoặc client khác.
7. **Auditable:** không mất dấu người phê duyệt, incident và thời điểm thực hiện.

### Trạng thái có thể dùng

~~~text
ACTIVE -> REVOKING -> REVOKED

Không cho:
REVOKED -> ACTIVE do replay event cũ

Khôi phục hoạt động hợp pháp:
    cấp grant/token/credential mới qua kiểm soát
    không mở lại RT family đã compromise
~~~

**REVOKED ở AS** và **ENFORCED ở RS** là hai mốc khác nhau. Một boolean duy nhất không diễn tả được trạng thái propagation.

### Race với token refresh

Giả sử refresh-token family F có generation=12:

~~~text
A: dùng RT của family F để xin AT mới
B: admin revoke family F

Nếu A kiểm ACTIVE ở ngoài transaction,
B commit REVOKED,
rồi A vẫn cấp AT+RT mới,
thì issuance barrier bị vượt qua.
~~~

Revoke và refresh phải dùng **cùng nguồn trạng thái nhất quán**; ví dụ row locking, serializable transaction, compare-and-swap generation hoặc cơ chế tương đương.

Một mô hình:

~~~text
REFRESH:
    lock F
    require F.status == ACTIVE
    require correct RT rotation generation
    atomically mark old RT spent and persist new RT state
    commit issuance outcome consistently

REVOKE:
    lock F
    set F.status = REVOKED
    increment F.generation
    persist operation, audit and outbox
    commit

Any refresh with stale generation:
    DENY
~~~

Không ký/phát credential hữu dụng ngoài transaction rồi mặc định nó đã được bảo vệ khỏi revoke xảy ra song song. Một AT đã phát trước revoke vẫn cần chặn ở RS.

## 17. Mô hình dữ liệu và audit record

Một schema PostgreSQL minh họa, không phải thiết kế production hoàn chỉnh:

~~~sql
CREATE TABLE oauth_grant_state (
    grant_id              UUID PRIMARY KEY,
    issuer_id             TEXT NOT NULL,
    tenant_id             TEXT NOT NULL,
    client_id             TEXT NOT NULL,
    principal_id          TEXT,
    refresh_family_id     UUID,
    status                TEXT NOT NULL,
    generation            BIGINT NOT NULL DEFAULT 0,
    revoked_at            TIMESTAMPTZ
);

CREATE TABLE admin_revocation_operation (
    operation_id          UUID PRIMARY KEY,
    incident_id           TEXT NOT NULL,
    actor_id              TEXT NOT NULL,
    issuer_id             TEXT NOT NULL,
    tenant_id             TEXT NOT NULL,
    target_kind           TEXT NOT NULL,
    target_id             TEXT NOT NULL,
    idempotency_key       TEXT NOT NULL,
    command_fingerprint   TEXT NOT NULL,
    status                TEXT NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL,
    committed_at          TIMESTAMPTZ,
    UNIQUE (tenant_id, actor_id, idempotency_key)
);

CREATE TABLE revocation_outbox (
    event_id              UUID PRIMARY KEY,
    operation_id          UUID NOT NULL,
    issuer_id             TEXT NOT NULL,
    target_kind           TEXT NOT NULL,
    target_id             TEXT NOT NULL,
    generation            BIGINT NOT NULL,
    occurred_at           TIMESTAMPTZ NOT NULL,
    published_at          TIMESTAMPTZ
);
~~~

Thực tế cần thêm foreign keys, indexes, audit immutability, retention, uniqueness, constraints, encryption và quyền truy cập. Tránh lưu **raw bearer/refresh token** nếu không thực sự cần và chưa đánh giá an toàn.

### Một incident, nhiều operations

~~~text
Incident: nghi account takeover

Operation 1: revoke RT family device A
Operation 2: revoke RT family device B
Operation 3: terminate OP session
Operation 4: terminate application sessions
Operation 5: emergency deny high-risk action at RS
~~~

Mỗi operation có **status và bằng chứng** riêng. Không kết luận toàn incident xong chỉ vì một operation đã commit.

### Bảo vệ idempotency key

Idempotency key phải được ràng với **actor, tenant, issuer, target, action, payload fingerprint**. Nếu dùng cùng key nhưng payload khác, trả conflict theo contract; không tự thay target.

Hai requests đồng thời cùng key cần **unique constraint/locking**, không chỉ SELECT rồi INSERT, vì vẫn có race.

## 18. HTTP admin revoke là API riêng, không phải endpoint chuẩn RFC 7009

Ví dụ thiết kế management-plane API:

~~~http
POST /admin/security/revocations HTTP/1.1
Host: admin.identity.example.test
Authorization: Bearer EXAMPLE_ADMIN_ACCESS_TOKEN
Content-Type: application/json
Idempotency-Key: INC-EXAMPLE-874-family-72

{
  "incident_id": "INC-EXAMPLE-874",
  "target": {
    "kind": "REFRESH_TOKEN_FAMILY",
    "issuer": "https://identity.example.test",
    "tenant_id": "tenant-blue",
    "family_id": "family-example-72"
  },
  "reason_code": "SUSPECTED_REFRESH_TOKEN_THEFT",
  "requested_effect": "BLOCK_NEW_ISSUANCE_AND_REVOKE_DESCENDANTS"
}
~~~

**Endpoint này là ví dụ tùy biến**, không được RFC 7009 định nghĩa. Admin bearer token phải mang quyền quản trị đúng issuer/tenant và backend phải xác thực mạnh, phê duyệt theo risk policy, chống CSRF nếu dùng cookie.

### Trạng thái tiếp nhận không phải trạng thái hoàn tất

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /admin/security/revocations/operation-example-23

{
  "operation_id": "operation-example-23",
  "status": "PROPAGATING",
  "authoritative_revocation_committed": true,
  "enforcement": {
    "required_targets": 3,
    "confirmed_targets": 1
  }
}
~~~

Chỉ được điền **committed=true** nếu giao dịch authoritative thực sự commit. **202** không tự chứng minh mọi RS/gateway đã cập nhật.

### Kiểm operation status

~~~http
GET /admin/security/revocations/operation-example-23 HTTP/1.1
Host: admin.identity.example.test
Authorization: Bearer EXAMPLE_ADMIN_ACCESS_TOKEN
~~~

Response minh họa:

~~~json
{
  "operation_id": "operation-example-23",
  "status": "ENFORCED",
  "issuer": "https://identity.example.test",
  "target_kind": "REFRESH_TOKEN_FAMILY",
  "target_id": "family-example-72",
  "confirmed_targets": [
    "token-endpoint",
    "orders-api",
    "api-gateway"
  ]
}
~~~

Chỉ admin có quyền mới đọc được operation metadata. **Location/operation ID không phải chứng cứ authorization.**

### Các trường hợp lỗi

| Trạng thái | Ý nghĩa |
| --- | --- |
| **401** | Admin chưa được xác thực đúng. |
| **403** | Admin thiếu role, tenant, approval hoặc chính sách khác. |
| **409** | Idempotency key đã dùng với payload khác, hoặc conflict được xác định. |
| **202 PROPAGATING** | State đã commit/đang phát tán theo contract. |
| **PARTIALLY_ENFORCED** | Chỉ một số RS đã xác nhận. |
| **FAILED** | Không commit được hoặc không xác minh hiệu lực; cần xử lý sự cố. |

Không báo **ENFORCED** nếu một RS quan trọng vẫn chấp nhận token hoặc chưa có bằng chứng kiểm.

## 19. Java/Spring: cấu trúc service cho admin revoke

Đoạn Java dưới đây minh họa **backend authorization, giao dịch và transactional outbox**. Những interface như GrantRepository, AdminPolicy, OperationRepository và OutboxRepository là abstraction của hệ thống, chưa được hiện thực trong ví dụ.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AdminRevocationService {

    private final GrantRepository grants;
    private final AdminPolicy adminPolicy;
    private final OperationRepository operations;
    private final OutboxRepository outbox;
    private final Clock clock;

    public AdminRevocationService(
            GrantRepository grants,
            AdminPolicy adminPolicy,
            OperationRepository operations,
            OutboxRepository outbox,
            Clock clock) {
        this.grants = grants;
        this.adminPolicy = adminPolicy;
        this.operations = operations;
        this.outbox = outbox;
        this.clock = clock;
    }

    @Transactional
    public UUID revokeRefreshFamily(
            VerifiedAdminContext admin,
            RevokeFamilyCommand command) {

        // Context do backend tạo từ authentication đáng tin.
        // Kiểm RBAC/ABAC, tenant, issuer và approval.
        adminPolicy.requireMayRevoke(admin, command);

        // Lookup đúng issuer + tenant + family, khóa record.
        RefreshGrant grant = grants.lockForUpdate(
                command.issuer(),
                command.tenantId(),
                command.familyId()
        );

        adminPolicy.requireMayInspect(admin, grant);

        // Idempotency được bảo vệ bằng unique constraint ở DB.
        UUID existing = operations.findSameCommand(
                admin.principalId(),
                command.tenantId(),
                command.idempotencyKey(),
                command.commandFingerprint()
        );

        if (existing != null) {
            return existing;
        }

        // Reusing key for different payload must fail.
        operations.requireNoConflictingKey(
                admin.principalId(),
                command.tenantId(),
                command.idempotencyKey(),
                command.commandFingerprint()
        );

        Instant now = Instant.now(clock);
        grant.revokeAndIncrementGeneration(now);

        UUID operationId = UUID.randomUUID();
        operations.recordCommitted(
                operationId,
                admin.principalId(),
                command,
                now
        );

        outbox.recordRefreshFamilyRevoked(
                UUID.randomUUID(),
                operationId,
                command.issuer(),
                command.familyId(),
                grant.generation(),
                now
        );

        return operationId;
    }
}
~~~

### Các điều kiện để ví dụ an toàn khi hiện thực

- **VerifiedAdminContext** phải được tạo từ principal đã xác thực ở backend; không lấy nguyên JSON do browser gửi.
- **AdminPolicy** kiểm cả quyền revoke và quyền đọc metadata của target, issuer/tenant, approver và trạng thái admin session.
- **lockForUpdate** bảo đảm concurrency với refresh/other revoke. Cần xử lý target không tồn tại theo policy chống enumeration.
- **findSameCommand và requireNoConflictingKey** chưa đủ nếu thiếu unique constraints và conflict handling từ database; hai request concurrent có thể cùng qua kiểm trước INSERT.
- **revokeAndIncrementGeneration** không được tự bật lại status khi record đã revoked; kết quả idempotent phải giữ nguyên.
- **recordCommitted** phản ánh thành công transaction local; **không** đồng nghĩa mọi RS đã áp dụng.
- **outbox** phải được lưu trong cùng transaction, được dispatcher retry an toàn và có reconciliation.
- **Client refresh token issuance** phải kiểm status/generation theo cùng consistency contract; code này không tự bảo vệ được race nếu token endpoint không tham gia.
- **Secret/token** không được ghi vào exception, logs hay audit record.
- Nếu target đã revoked trước đó, service nên trả một kết quả idempotent phù hợp thay vì tạo generation mới tùy tiện.

**Đây là ví dụ cấu trúc, không phải source code có thể compile độc lập.** Không tự dùng nó thay thư viện/AS production hoặc bỏ qua transaction isolation, permission và tests.

## 20. Event consumer: không cho trạng thái cũ ghi đè revoke

RS/gateway có thể nhận event từ outbox; message broker thường có thể giao **at least once**, nên consumer phải chịu được event trùng.

Pseudocode:

~~~text
function applyRevocationEvent(event):
    verifyEventOriginAndSchema(event)
    requireAuthorizedIssuerAndTargetScope(event)

    current = localRevocationState[event.targetKey]

    if current exists
       AND event.generation <= current.generation:
        ACK_DUPLICATE_OR_STALE()
        return

    ATOMICALLY:
        localRevocationState[event.targetKey] = {
            generation: event.generation,
            status: "REVOKED",
            effective_at: event.effective_at
        }
        invalidateAffectedAuthenticationCaches(event.targetKey)

    ACK_APPLIED_VERSION(event.generation)
~~~

### ACK broker khác ACK enforcement

Broker xác nhận **message delivered** chưa chứng minh RS đã cài deny rule. Nếu RS cần tải thêm state hoặc invalidate cache, nên ACK trạng thái **applied generation** sau khi việc cập nhật thực sự hoàn tất.

Khi RS offline:

- Replay từ offset được tin cậy hoặc lấy snapshot từ authoritative source.
- Chặn/giới hạn token chưa thể kiểm đúng trạng thái nếu rủi ro không cho phép dùng stale state.
- Xác nhận generation mới trước khi báo synchronized.
- Đo event lag, consumer failure và dead-letter queue.
- Có periodic reconciliation vì event transport có thể gặp lỗi ngoài dự kiến.

### Cache race

Một callback introspection active=true bắt đầu trước event revoke nhưng kết thúc sau event có thể ghi **cache true đè state revoked** nếu logic không so version.

Nên có quy tắc:

~~~text
If local grant/token revocation generation
    is newer than introspection/cache snapshot,
then do not install active=true cache entry.

If response lacks a generation:
    either invalidate and requery with ordering guarantees,
    or use policy that prioritizes local revoked state.
~~~

**Revoke state phải có ưu tiên áp dụng và được đo tính nhất quán**, không tùy thuộc thứ tự các thread hoàn thành.

## 21. Xác nhận enforcement với SLO đo được

Có thể tách các mốc:

~~~text
T_detect        = thời điểm phát hiện incident
T_commit        = AS commit authoritative revocation state
T_issue_blocked = token endpoint không nhận RT/client credential cũ
T_rs_enforced   = RS bắt buộc ngừng chấp nhận AT thuộc scope
T_verified      = bằng chứng và kiểm thử xác nhận containment
~~~

**SLO do tổ chức đặt theo risk**, không phải các con số cố định trong RFC 7009. Một API thanh toán có thể cần propagation nhanh hơn API dữ liệu công khai ít nhạy cảm.

Các bước xác minh:

1. **AS state:** status, generation, operation ID và commit timestamp.
2. **Issuance:** token endpoint từ chối RT/grant/client credential cũ qua phép thử được ủy quyền hoặc qua kết quả trạng thái tin cậy.
3. **Opaque AT:** introspection trả active=false theo hợp đồng và RS không dùng cache quá TTL.
4. **JWT offline:** denylist/version/emergency policy đã được cài ở mỗi RS được yêu cầu.
5. **Gateway:** cache/internals đã invalidate và không tin header X-Token-Active do client giả.
6. **RP/OP session:** logout/terminate state được xác nhận nếu nằm trong scope.
7. **Coverage:** danh sách RS yêu cầu, RS đã ack, chưa ack và lý do.
8. **Probe an toàn:** sử dụng test token/canary hoặc cơ chế kiểm tra trong scope được cho phép; không phát tán raw stolen token ra nhiều máy để “thử”.

### Không nhầm success với partial success

Một incident có:

~~~text
AS: committed
Token endpoint: blocked
Orders RS: enforced
Payments RS: enforced
Analytics RS: unreachable
~~~

Nếu Analytics RS thuộc phạm vi revoke bắt buộc, operation phải là **PARTIALLY_ENFORCED hoặc PROPAGATING**, chưa phải DONE. Đội vận hành cần containment phụ và theo dõi đến khi đạt yêu cầu.

## 22. Monitoring, audit và quyết định sau sự cố

Những metric/event có ích:

~~~text
ADMIN_REVOKE_REQUEST_COUNT
ADMIN_REVOKE_DENIED
ADMIN_REVOKE_COMMIT_LATENCY_MS
ADMIN_REVOKE_PROPAGATION_LATENCY_MS
ADMIN_REVOKE_RS_ACK_LAG
ADMIN_REVOKE_PARTIAL_ENFORCEMENT
REFRESH_TOKEN_REUSE_DETECTED
REVOKED_TOKEN_REPLAY_ATTEMPT
REVOKE_OUTBOX_DLQ_COUNT
REVOCATION_CACHE_STALE_HIT
CLIENT_CREDENTIAL_DISABLED
SIGNING_KEY_EMERGENCY_ROTATION
~~~

Các tên này là **gợi ý nội bộ**, không phải tên chuẩn RFC.

### Audit record tối thiểu

| Trường | Nội dung |
| --- | --- |
| **incident_id / operation_id** | Liên kết quyết định và hành động. |
| **actor và approval** | Ai yêu cầu, ai phê duyệt, quyền admin tại thời điểm đó. |
| **reason_code** | Sự cố nghi theft, reuse, key compromise, policy overgrant... |
| **target scope** | Issuer, tenant, client, grant/family/token/key/session identifier. |
| **state changes** | Previous state, new state, generation và commit time. |
| **enforcement evidence** | RS ack/version, probes được phép, thời gian và kết quả. |
| **exceptions** | RS chưa cập nhật, AS outage, manual override, escalation. |
| **recovery** | Credential/grant mới, quyền tối thiểu, thời điểm phục hồi. |

**Audit phải chống sửa/xóa theo chính sách**, có retention và phân quyền đọc. Không ghi raw AT/RT, signing private key, client secret, mật khẩu hoặc nhiều PII không cần thiết.

### Phát hiện replay sau revoke

Một RS tiếp tục thấy token đã revoked có thể là:

- Attacker vẫn đang phát lại token.
- Client hợp pháp chưa xử lý 401, vẫn retry token cũ.
- Gateway/RS đang dùng cache stale.
- Một instance chưa nhận event hoặc vẫn tin signing key cũ.
- Lỗi cấu hình issuer/audience/revocation validator.

Không tự kết luận mọi replay là attacker; nhưng cần correlation bằng metadata an toàn và điều tra.

### Post-incident review

Sau khi containment, rà soát:

1. Token đã lộ từ đâu và làm sao ngăn tái diễn.
2. Grant/credential nào thực sự bị ảnh hưởng.
3. Có phát sinh token mới trong race hoặc sau revoke không.
4. Có API nào chấp nhận JWT/opaque token quá SLO không.
5. Client/session/user recovery có an toàn không.
6. Có cần giảm TTL, thêm sender-constraining, phân tách signing key hoặc đổi cache policy không.
7. Negative tests và runbook có được cập nhật từ sự cố thật không.

## 23. Các kịch bản incident và quyết định revoke

### Case A — Một access token xuất hiện trong log của Orders API

**Bối cảnh:** Một bản log debug chứa Bearer AT do frontend gửi đến Orders. Token có aud=Orders, exp còn 12 phút và RS xác minh JWT offline.

**Rủi ro:** Bất kỳ ai đọc log có thể phát lại token tại Orders cho đến khi token hết hạn hoặc RS thực thi revoke.

**Phản ứng:**

1. Tạo incident ID, giới hạn quyền truy cập log, chặn tiếp tục ghi Authorization header.
2. Xác định AT jti/fingerprint, client, issuer, audience và endpoints đã truy cập qua audit đáng tin.
3. Revoke AT và đẩy denylist jti tới **mọi Orders RS instance/gateway** nếu cơ chế có hỗ trợ.
4. Nếu chưa có denylist, đánh giá emergency user/client block hoặc chiến lược containment khác theo risk/approval.
5. Kiểm RS không chấp nhận AT bị revoke, kể cả instance được scale mới.
6. Kiểm dữ liệu đã được truy cập trước containment và sửa nguyên nhân log leak.
7. Không kết luận RT/SSO an toàn nếu evidence cho thấy client runtime cũng bị chiếm.

**Kết quả mong muốn:** AT không còn dùng được tại intended audience trong SLO; log pipeline không tiếp tục lộ token.

### Case B — Refresh token reuse sau rotation

**Bối cảnh:** RT-1 đã được dùng đổi RT-2; hệ thống thấy RT-1 được trình lại từ một network khác. Nguyên nhân có thể là attacker hoặc retry/race.

**Phản ứng:**

1. Kiểm evidence và xác định family/grant, client, device.
2. Áp **refresh reuse policy**, thường revoke family khi không thể phân biệt bên hợp pháp.
3. Revoke/deny các AT cấp từ family theo risk policy.
4. Yêu cầu reauthentication từ nguồn đáng tin; bảo vệ recovery/MFA.
5. Kiểm cơ chế client single-flight, retry logic, AS atomic rotation để phân biệt lỗi đồng thời.
6. Theo dõi sự kiện sau revoke; cảnh báo nếu vẫn có issuance hợp lệ từ family.

**Kết quả mong muốn:** Không client nào dùng RT thuộc family bị revoke để xin AT mới; RS xử lý AT cũ theo SLO được công bố.

### Case C — Client secret của payments-batch-worker bị commit nhầm

**Bối cảnh:** Một secret có quyền client_credentials bị lộ trong commit repository.

**Sai lầm phổ biến:** Chỉ rotate secret trên secret manager nhưng **giữ secret cũ active** trong AS.

**Phản ứng:**

1. Disable secret version cũ hoặc khóa client credential theo policy.
2. Triển khai credential mới từ môi trường sạch, bảo đảm workload nhận đúng secret và hạn quyền.
3. Rà soát token issuance theo client, resource, thời gian và key identifier.
4. Revoke AT/permission liên quan khi cần.
5. Kiểm secret cũ **không** còn xin token mới, ngay cả nếu client_id đúng.
6. Phân tích API usage, dữ liệu bị tác động và bảo vệ repository/log artifacts.

**Kết quả mong muốn:** Attacker không còn dùng secret cũ; workload hợp lệ chỉ chạy bằng credential mới có scope/resource tối thiểu.

### Case D — Signing private key của AS bị nghi compromise

**Bối cảnh:** K-old được dùng ký nhiều access token JWT. Một file backup private key lộ ra nơi không được phép.

**Phản ứng:**

1. Escalate mức độ nghiêm trọng và ngừng dùng K-old để ký mới.
2. Sinh key mới bằng quy trình HSM/KMS/secret management đã được phê duyệt.
3. Buộc các RS loại bỏ trust với K-old, kiểm JWKS/key caches và algorithm allowlist.
4. Đánh giá **token hợp lệ ký bằng K-old sẽ bị ảnh hưởng**, chuẩn bị issuance lại và liên lạc vận hành.
5. Tìm dấu hiệu token giả, không chỉ jti đã thấy.
6. Đo coverage mọi RS, kể cả service offline, mobile gateway hoặc edge cache.
7. Chỉ báo ENFORCED khi cơ chế trust thực tế không còn chấp nhận chữ ký K-old theo phạm vi.

**Kết quả mong muốn:** JWT do attacker ký bằng K-old không được RS chấp nhận. Cần lưu ý một RSA/ECDSA key được loại khỏi trust có thể làm mất hiệu lực hàng loạt JWT hợp pháp cùng key.

### Case E — Revoke nhầm tenant trong admin console

**Bối cảnh:** Admin có quyền tenant-blue nhưng thao tác bulk revoke nhầm target tenant-green.

**Hệ thống đúng phải:**

- Kiểm **issuer/tenant target tại backend**, không tin UI.
- Từ chối nếu admin không có quyền tenant-green.
- Yêu cầu approval khi thao tác diện rộng.
- Ghi audit reason, scope và result mà không tiết lộ token của tenant-green.
- Hỗ trợ sửa sai bằng **cấp lại credential/grant mới qua quy trình hợp lệ**, không tự hồi sinh RT đã revoke hoặc sửa audit cũ.

### Case F — Event revoked đến sau cached active=true

**Bối cảnh:** RS bắt đầu introspection; đồng thời admin revoke và event được nhận; response active=true từ request cũ về sau cùng.

**Yêu cầu:** RS không cài đặt active=true cache entry nếu local revocation state/version đã mới hơn. Nếu thiếu version, cơ chế hợp đồng cần ưu tiên revoked state hoặc revalidation an toàn.

**Kết quả mong muốn:** Không có race khiến token bị revoke trở lại hợp lệ.

## 24. Bảng phân biệt kết quả revoke và lỗi vận hành

| Trạng thái | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| **RFC 7009 trả 200** | AS xử lý revoke theo hợp đồng, kể cả token không tồn tại. | Không suy RS đã chặn mọi bản sao. |
| **Admin API 202** | Operation được tiếp nhận; có thể đang propagation. | Theo dõi operation ID và SLO. |
| **AS commit thành công, RS chưa ack** | State authoritative đã đổi, enforcement chưa xác nhận. | Giữ PROPAGATING/PARTIAL; escalate nếu vượt SLO. |
| **RT family revoked, refresh vẫn phát AT** | Issuance barrier thất bại hoặc state propagation lỗi. | Incident critical, chặn token endpoint path và sửa atomicity. |
| **JWT vẫn được RS nhận** | Offline validation/denylist/key cache chưa cập nhật. | Emergency containment, reconcile RS, kiểm key trust. |
| **Opaque AT introspection active=false** | AS không xác nhận token hoạt động. | RS từ chối credential. |
| **Introspection HTTP 401/403** | RS caller authentication/authorization bị lỗi. | Fail closed, xử lý credential/config; không coi token inactive có chứng cứ. |
| **Introspection HTTP 503/timeout** | Không xác minh được trạng thái token. | Fail closed theo policy; lỗi vận hành không là allow. |
| **Scope/aud mismatch** | Token có thể active nhưng không được dùng ở endpoint/RS này. | RS từ chối theo type/audience/authorization. |
| **Credential mới nhưng token cũ còn được nhận** | Rotate credential không tự revoke AT cũ. | Xử lý AT/grant theo phạm vi đã duyệt. |
| **Audit mất nhưng DB revoked** | Control-plane state có thể đúng nhưng thiếu forensic evidence. | Khôi phục audit theo policy, điều tra log pipeline; không bịa chứng cứ. |
| **RS được scale mới nhưng thiếu denylist** | Một replica mới không có state revoke. | Bootstrap snapshot/reconciliation trước phục vụ traffic nhạy cảm. |

### Cẩn thận với false confidence

Một số tín hiệu không đủ độc lập:

- Database hiển thị revoked=true.
- Admin console hiện nhãn Success.
- Broker trả publish ACK.
- Một RS duy nhất trả 401.
- Client hợp pháp không còn request.
- Token ngừng xuất hiện trên dashboard metrics.

Để kết luận containment, cần **phạm vi RS đầy đủ, issuance blocked và bằng chứng enforcement** theo incident policy.

## 25. Negative tests cho admin revoke

Bảng kiểm thử nên chạy với **test tokens và environment được ủy quyền**, không phát tán credential thật.

| Test | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| **Revoke một AT hợp lệ** | AT chưa exp, có jti. | State bị revoke; RS thực thi chặn trong SLO. |
| **Revoke AT lần hai** | Cùng operation/idempotency key. | Không undo, không nhân đôi side effects. |
| **Concurrent identical revoke** | Hai admin request cùng key/target. | Một trạng thái nhất quán, audit/idempotency đúng. |
| **Same key khác payload** | Một idempotency key nhưng family khác. | Conflict, không revoke nhầm. |
| **Target đã hết hạn** | AT exp trong quá khứ. | Kết quả idempotent hợp đồng, không resurrect token. |
| **Target không tồn tại** | ID ngẫu nhiên. | Không lộ token/tenant metadata cho admin không có quyền. |
| **Admin thiếu role** | User support gọi revoke endpoint. | 403, không đổi state. |
| **Admin tenant khác** | Quyền tenant-blue, target tenant-green. | Từ chối tại backend. |
| **Admin thiếu approval** | Revoke toàn user/issuer vượt ngưỡng. | Không thực hiện nếu thiếu control bắt buộc. |
| **Admin session hết hạn** | JWT/cookie quản trị hết hạn. | 401/reauth theo policy. |
| **Admin CSRF** | Browser cookie, request thiếu CSRF protection. | Từ chối khi profile dùng CSRF. |
| **Audit write lỗi** | Không thể commit audit/outbox. | Không báo COMMITTED; transaction rollback/compensating logic đúng. |
| **Outbox publish lỗi** | State revoke commit, broker unavailable. | Retry/reconcile, không báo ENFORCED sớm. |
| **Event duplicate** | Giao lại cùng event. | Consumer idempotent, generation không giảm. |
| **Event out-of-order** | Generation 14 đến sau 15. | Không ghi đè revocation version mới. |
| **New RS replica** | Instance lên sau revoke. | Tải state trước khi chấp nhận token liên quan. |
| **Cache active true stale** | Response cũ về sau revoked event. | Không ghi cache true đè revoked state. |
| **JWT offline no state lookup** | AT revoked nhưng còn exp. | Test phát hiện RS vẫn nhận; cấu hình phải đáp SLO. |
| **Opaque active=false** | AS đã revoke. | RS từ chối. |
| **Opaque AS 503** | Introspection unavailable. | Không bypass authentication. |
| **Opaque cache sau revoke** | RS còn cached active=true. | Hành vi trong TTL/SLO đã duyệt, đo propagation lag. |
| **RT family revoked** | Thử đổi RT mới nhất. | invalid_grant hoặc lỗi tương đương, không phát AT. |
| **RT cũ reuse** | Dùng RT đã rotated. | Áp reuse detection/family policy. |
| **Refresh/revoke race** | Hai transaction cùng family. | Không phát token hữu dụng sau revocation winner. |
| **AT trước revoke** | AT đã cấp trước khi RT family bị revoke. | RS chặn theo token propagation policy. |
| **Client secret disabled** | Dùng secret version cũ để xin AT. | AS từ chối client authentication. |
| **Secret rotated nhưng cũ còn active** | Rollout có hai secret. | Test cảnh báo chưa hoàn tất compromise containment. |
| **Signing key K-old revoked** | JWT ký bằng K-old và còn exp. | Mọi RS bắt buộc từ chối trong emergency SLO. |
| **JWKS cache cũ** | Một RS giữ K-old. | Kiểm phát hiện noncompliance; không báo ENFORCED. |
| **Audience khác** | AT Orders gửi Payments. | Payments từ chối, dù chưa revoke. |
| **Scope thiếu** | Token active chỉ có read cho POST approve. | RS từ chối authorization. |
| **Service principal giả user** | Client credentials token dùng ở user-only endpoint. | RS từ chối theo principal policy. |
| **Cross-tenant revoke request** | Chỉ sửa tenant trong JSON. | Backend không tin scope tự khai. |
| **Admin token bị lộ** | Attacker có token thiếu privilege/step-up. | Không thực hiện revoke trái quyền. |
| **Missing incident reference** | Revoke high-risk không có incident ID. | Từ chối hoặc áp break-glass policy đã được audit. |
| **Propagation ack sai** | RS báo delivered nhưng chưa apply. | Không đếm như enforcement ack. |
| **Partial outage** | Analytics RS unreachable. | Operation không đạt ENFORCED tổng thể. |
| **Phục hồi sau revoke** | User đăng nhập lại bằng grant mới. | Credential mới hợp lệ; family cũ vẫn revoked. |
| **Raw token in logs** | Kiểm request/response trong tracing. | Dữ liệu nhạy cảm được redact. |
| **Repeated token replay** | RS nhận token revoked nhiều lần. | Từ chối, audit metadata, không tiết lộ token raw. |

### Năm phép kiểm tối thiểu sau một lệnh revoke

~~~text
1. Authoritative store: status=REVOKED, generation tăng.
2. Token endpoint: RT/client credential đã revoke không xin AT mới.
3. Introspection/RS: token thuộc phạm vi bị từ chối.
4. Propagation: mọi RS bắt buộc có applied version/validation evidence.
5. Audit: incident, actor, approval, target, outcome, timestamps nguyên vẹn.
~~~

## 26. Checklist vận hành production

1. **Scope:** Đã xác định issuer, tenant, client, subject, grant, family, token, session hay key cần revoke?
2. **Incident ID:** Có ticket/correlation ID, reason code, mức độ nghiêm trọng và thời điểm phát hiện?
3. **Evidence:** Dùng token ID/fingerprint an toàn, không copy raw credential vào logs/ticket?
4. **Privilege:** Admin có đúng RBAC/ABAC, tenant scope, MFA/JIT và quyền loại thao tác?
5. **Approval:** Revoke hàng loạt/signing key có dual approval/break-glass audit khi policy yêu cầu?
6. **RFC 7009:** Biết client-driven revoke khác administrative API nội bộ?
7. **Idempotency:** Retry không đổi target/scope và không undo trạng thái?
8. **Atomicity:** Grant/family state, audit và outbox được commit nhất quán?
9. **Refresh race:** Token endpoint kiểm trạng thái/generation và rotation atomically?
10. **RT family:** Nếu RT bị lộ/reuse, có thu hồi toàn family/grant theo risk?
11. **AT liên đới:** Có đánh giá AT đã cấp trước khi RT/grant bị revoke?
12. **Session:** Có xét RP session, OP/SSO session và token grants riêng?
13. **Client credential:** Disable credential cũ, không chỉ thêm secret mới?
14. **Signing key:** Có playbook emergency rotate/remove trust và kiểm JWKS cache?
15. **Opaque:** RS introspection active=false sau revoke, cache TTL trong SLO?
16. **JWT offline:** Có denylist/version/emergency policy hoặc chấp nhận TTL được phê duyệt?
17. **Audience/type:** RS vẫn kiểm đúng AT type, issuer, audience, scope và principal?
18. **Tenant/permission:** Chính sách tài nguyên tại RS vẫn áp, không chỉ token status?
19. **Event:** Outbox/consumer idempotent, version monotonic và có replay/reconcile?
20. **Replica bootstrap:** RS mới/offline cập nhật revocation state trước khi cho traffic nhạy cảm?
21. **Cache ordering:** Stale active=true không được ghi đè revoked state mới?
22. **Issuance SLO:** Đã xác nhận grant/credential cũ không phát token mới?
23. **Enforcement SLO:** Có coverage toàn bộ RS/gateway được yêu cầu, không chỉ một API?
24. **Partial failure:** Operation status phản ánh PARTIAL/FAILED thay vì DONE sai?
25. **Monitoring:** Có alert cho propagation lag, refresh reuse, revoked-token replay, RS ack gap?
26. **Log hygiene:** Không ghi raw AT/RT/ID token, private key, client secret hay full admin credentials?
27. **Recovery:** Có đường cấp grant/credential mới sau khi xử lý root cause?
28. **Postmortem:** Đã cập nhật negative tests, runbook, TTL, secret management và controls?

## Kết luận

**Admin revoke sau incident là một quy trình bảo mật xuyên suốt phát hành token, trạng thái grant, phiên xác thực và enforcement tại Resource Server**, chứ không chỉ là một nút “Revoke” hay một câu lệnh database.

Khi incident liên quan **access token**, cần chặn token tại audience hợp lệ; khi liên quan **refresh token**, cần xử lý **family/grant** và token mới; khi liên quan **client credential**, phải ngăn client authentication tiếp diễn; và khi **signing key** bị xâm phạm, cần loại bỏ gốc tin cậy khỏi toàn bộ RS theo emergency playbook.

**RFC 7009** định nghĩa cơ chế client yêu cầu thu hồi token nhưng không chuẩn hóa toàn bộ admin incident workflow. Một implementation tốt cần **quyền admin tối thiểu, approval, transaction/idempotency, outbox/reconciliation, phân biệt JWT offline với opaque introspection, cache/revocation SLO, kiểm thử thực thi và audit đầy đủ**.

Nguyên tắc cuối cùng: **Revoke thành công ở AS chưa phải containment thành công nếu attacker vẫn có thể xin access token mới hoặc Resource Server còn chấp nhận credential cũ.**

### Tài liệu tham khảo

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7009 — Section 2.1 Revocation Request](https://www.rfc-editor.org/rfc/rfc7009#section-2.1)
- [RFC 7009 — Section 2.2 Revocation Response](https://www.rfc-editor.org/rfc/rfc7009#section-2.2)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8414 — Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8705 — OAuth 2.0 Mutual TLS and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Session Management 1.0](https://openid.net/specs/openid-connect-session-1_0.html)
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html)
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [NIST SP 800-61 Rev. 2 — Computer Security Incident Handling Guide](https://csrc.nist.gov/pubs/sp/800/61/r2/final)





