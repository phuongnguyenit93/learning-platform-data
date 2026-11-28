# Credential compromise

**Credential compromise** là tình huống một credential hoặc thành phần bí mật của nó bị lộ, bị đánh cắp, bị sử dụng trái phép, hoặc có cơ sở đáng tin để nghi ngờ **một bên không được phép đã có khả năng sử dụng credential**. Với xác thực HTTP request bằng HMAC, sự cố nghiêm trọng nhất thường là **shared secret** dùng để tính tag bị lộ: ai có secret đều có thể tạo một HMAC tag hợp lệ cho một canonical request mới mà không cần “bẻ” thuật toán HMAC.

Bài học thuộc chương **Credential lifecycle** của mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Mô-đun tập trung thiết kế xác thực HTTP request bằng HMAC dựa trên shared secret và canonical request chứa method, URI, signed headers và/hoặc body theo hợp đồng; thực hành xác minh tag, chống replay bằng timestamp/nonce, key rotation, kiểm thử proxy/gateway và phân biệt **authentication** với **authorization**.

> **Thông điệp quan trọng:** Khi shared secret đã bị compromise, **HMAC hợp lệ không còn là bằng chứng request do client hợp pháp gửi**. Attacker có thể tự ký request mới với timestamp còn fresh và nonce chưa dùng; vì vậy không thể chỉ tăng độ dài tag, đổi nonce, rút ngắn replay TTL hoặc dựa vào so sánh constant-time. Phải **ngăn credential bị lộ tiếp tục được chấp nhận**, cấp credential mới qua kênh an toàn, kiểm tra các tác động đã xảy ra và loại bỏ nguyên nhân rò rỉ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Định nghĩa credential compromise và phân biệt **key ID bị biết**, **secret bị lộ**, **client bị chiếm quyền**, **replay request** và **sự cố key registry**.
2. Giải thích chính xác vì sao HMAC vẫn hợp lệ khi attacker có shared secret.
3. Xác định phạm vi ảnh hưởng (*blast radius*) theo principal, tenant, audience, permission, key sharing và thời gian hiệu lực.
4. Nhận diện các dấu hiệu bất thường mà không nhầm HMAC thành một cơ chế phát hiện xâm nhập.
5. Thiết kế quy trình **phát hiện → cô lập/thu hồi → cấp credential mới → xác minh → điều tra → cải thiện**.
6. Phân biệt **rotation thông thường** với **emergency revocation** khi secret đã bị lộ; biết vì sao overlap kéo dài là nguy hiểm.
7. Kiểm thử revocation trên nhiều verifier nodes, gateway caches, key registry và khi các phụ thuộc gặp lỗi.
8. Viết Java 17 để biểu diễn credential status, thời hạn, key lookup và điều kiện từ chối key bị thu hồi.
9. Thiết kế unit/integration/chaos tests cho compromised key, rollback/failover, replay và authorization.
10. Xây dựng runbook, audit/observability và chính sách hạn chế lộ bí mật.

## 2. Credential gồm những gì trong HMAC authentication?

Ví dụ một client gửi request:

~~~http
POST /v1/payments HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a-k3
X-Timestamp: 1800000030
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <full-hmac-sha256-tag>

{"paymentId":"P42","amount":125000}
~~~

Một registry đáng tin có thể ánh xạ:

~~~text
keyId:         partner-a-k3
principalId:   partner-a-service
tenantId:      tenant-A
audience:      payments-api
algorithm:     HmacSHA256
status:        ACTIVE
notBefore:     2026-01-01T00:00:00Z
notAfter:      2027-01-01T00:00:00Z
secretRef:     secrets/partner-a-k3
allowedScopes: payments:create, payments:read
~~~

Đây là **metadata minh họa**, không phải credential thực. Shared secret phải được giữ trong kho bí mật thích hợp, tránh xuất hiện trong source code, logs, ticket, email, ảnh chụp màn hình hoặc tài liệu học.

| Thành phần | Có phải secret? | Nếu lộ hoặc bị sửa có nghĩa gì? |
| --- | --- | --- |
| **Key ID** | Thường **không**; là selector | Có thể lộ metadata/đối tác, nhưng không đủ tạo MAC |
| **HMAC shared secret** | **Có** | Có thể tạo tag hợp lệ cho signed request mới |
| **HMAC tag** | Không phải secret gốc | Có thể được dùng để replay **cùng request** nếu còn đủ điều kiện |
| **Signed timestamp** | Không | Ngăn request cũ theo policy, không chặn attacker có secret |
| **Signed nonce** | Không | Phát hiện nonce đã dùng, không chặn attacker sinh nonce mới |
| **Principal/tenant/scope** | Metadata policy | Giới hạn quyền và phạm vi ảnh hưởng của credential |
| **SecretRef** | Không đồng nghĩa secret | Có thể tiết lộ đường dẫn nội bộ; cần access control và redaction |
| **Bearer session/token khác** | Có thể là credential riêng | Cần đánh giá/thu hồi riêng nếu bị lộ cùng nguồn |

### 2.1. Biết key ID chưa phải compromise của HMAC secret

Attacker biết `partner-a-k3` mà **không** biết secret k3 không thể tự tính MAC cho một canonical request mới theo giả định HMAC an toàn. Tuy nhiên việc key ID bị liệt kê có thể hỗ trợ probing và gây áp lực lên registry, nên cần giới hạn tiết lộ thông tin và rate limiting phù hợp.

Ngược lại, nếu secret bị sao chép từ environment variable, file cấu hình, CI log, developer laptop hoặc backup, **không thể coi key vẫn an toàn chỉ vì key ID được giữ kín**.

### 2.2. Bản chất symmetric key và khả năng quy trách nhiệm

HMAC là một cơ chế **symmetric MAC**: client và server cùng có khả năng tính MAC bằng shared secret. Tag chứng minh một bên có quyền truy cập secret đã tham gia tạo tag, **không tự phân biệt client hợp pháp, attacker đã đánh cắp key hay chính verifier nếu verifier cũng có secret**.

Nếu một secret được dùng bởi nhiều clients/instances/partners, độ chính xác khi quy trách nhiệm còn kém hơn. Thiết kế nên cấp **một credential riêng cho mỗi client hoặc trust boundary phù hợp** để giảm blast radius và hỗ trợ revoke có mục tiêu.

## 3. Threat model: attacker có thể làm gì?

Giả sử attacker đã có **secret bytes của một credential còn được verifier chấp nhận**, nhưng không nhất thiết kiểm soát server registry, database hoặc mọi network path.

Attacker có thể:

- Chọn method/path/query/body nằm trong scope credential.
- Đặt timestamp gần thời gian hiện tại.
- Sinh nonce mới.
- Tạo canonical request đúng contract rồi tính HMAC đầy đủ.
- Gửi signed request hợp lệ tới service trong audience của key.
- Lặp nghiệp vụ bằng nhiều requests mới ký nếu business không có idempotency.
- Khai thác những header/URI/body **không được ký** nếu verifier/handler dùng chúng không an toàn.
- Duy trì hoạt động cho tới khi key bị revoke hoặc key/policy hết hiệu lực **trên tất cả đường xác minh**.

Attacker **không** mặc nhiên có quyền trên mọi resource: authorization theo principal/tenant/action vẫn phải được thực thi. Attacker cũng không tự có secret của credential khác nếu keys và storage được tách biệt đúng.

### 3.1. HMAC bị compromise không đồng nghĩa thuật toán bị phá

Có hai tình huống khác nhau:

1. **Cryptographic break:** attacker có thể tạo MAC hợp lệ mà không biết secret, do primitive/protocol yếu hoặc lỗi triển khai.
2. **Credential compromise:** attacker **đã biết hoặc sử dụng được secret**, nên tính MAC một cách bình thường.

Sự cố thứ hai có thể xảy ra ngay cả khi dùng HMAC-SHA256 full 32-byte tag, canonical request hoàn hảo và so sánh constant-time đúng. Thay SHA256 bằng SHA384 **không** lấy lại tính an toàn của secret đã bị lộ.

### 3.2. Replay một request cũ và ký request mới khác nhau

~~~text
Replay:
  capture R(timestamp=T, nonce=N, tag=S)
  send exact R again
  -> timestamp + nonce store có thể từ chối

Compromised secret:
  choose R2(timestamp=T2, nonce=N2, newBody, tag=S2)
  S2 = HMAC(stolenSecret, canonical(R2))
  -> HMAC, freshness và nonce uniqueness vẫn có thể PASS
~~~

**Đây là giới hạn thiết yếu của anti-replay.** Không thể chữa credential compromise chỉ bằng cách thay đổi nonce hoặc TTL.

### 3.3. Hệ quả của scope quá rộng

| Phạm vi credential bị lộ | Hậu quả tiềm năng |
| --- | --- |
| Key dành riêng một webhook consumer | Requests giả mạo cho endpoint đó |
| Key chỉ được `orders:read` | Đọc dữ liệu trong scope được cấp nếu authorization cho phép |
| Key có `payments:create` | Có thể tạo thanh toán nếu authorization và business constraints cho phép |
| Một key dùng chung nhiều services | Cross-service blast radius lớn hơn |
| Một secret dùng chung nhiều tenants | Cô lập tenant khó, rủi ro lan rộng |
| Shared admin/infrastructure key | Ảnh hưởng tới nhiều tài nguyên/hệ thống |
| Registry hoặc secret manager bị kiểm soát | Có thể ảnh hưởng hàng loạt keys và metadata, cần phản ứng rộng hơn |

**Least privilege, per-client keys và signed audience** giúp hạn chế hậu quả khi một secret riêng lẻ bị lộ.

## 4. Những nguồn làm lộ secret thường gặp

Không phải mọi sự cố đều đến từ thuật toán HMAC. Những nguồn cần kiểm soát:

1. **Source control:** hardcode secret trong repository, commit history hoặc sample config.
2. **CI/CD:** secret xuất hiện trong build logs, debugging output, cache artifacts hoặc test reports.
3. **Application logs/traces:** raw Authorization, environment dump, stack trace hoặc request diagnostic ghi nhầm bí mật.
4. **Runtime configuration:** biến môi trường, file config, container image hoặc Kubernetes Secret/RBAC bị truy cập trái phép.
5. **Developer/partner endpoints:** laptop bị malware, plaintext credentials, screenshot/ticket/email chia sẻ ngoài quy trình.
6. **Secret store permissions:** token service có quyền đọc nhiều secret hơn cần thiết.
7. **Backup/exports:** backup snapshot, DB dump, staging copy hoặc DR environment giữ bản secret cũ.
8. **Shared credential distribution:** nhiều bên nhận cùng secret qua những kênh khó thu hồi độc lập.
9. **Proxy/gateway misconfiguration:** forwarding thông tin nhạy cảm hoặc ghi dump request headers.
10. **Server/secret manager compromise:** attacker có quyền truy cập secret bytes hoặc thực thi cryptographic operations trái phép.
11. **Legacy key retention:** secret cũ vẫn được cho verify trong rotation overlap không giới hạn.
12. **Human operations:** copy-paste credential vào kênh chat, email, log hoặc quy trình hỗ trợ không được phép.

### 4.1. Không sử dụng hash secret làm bằng chứng secret vẫn an toàn

Lưu hash/fingerprint của secret có thể giúp kiểm tra hai bản có giống nhau mà **không in secret**, nhưng hash không chứng minh attacker chưa sao chép secret. Nếu nghi ngờ đã có truy cập trái phép tới nơi secret được lưu, **không thể chữa bằng cách chỉ đổi cách biểu diễn secret** (hex ↔ Base64).

### 4.2. Mô hình capability chứ không chỉ data exfiltration

Đôi khi attacker **không đọc được bytes** nhưng đã chiếm được service có quyền yêu cầu HSM/KMS tính HMAC. Khi đó attacker cũng có **khả năng ký request** trong phạm vi credential, nên cần xử lý như một compromise về năng lực sử dụng key. Chỉ chuyển secret từ file vào HSM không tự sửa sự cố nếu attacker có quyền gọi signing API.

## 5. Phát hiện compromise: tín hiệu, bằng chứng và giới hạn

Hệ thống HMAC không có một phép toán nào nhìn tag rồi kết luận “được tạo bởi kẻ xấu”. Detection thường dựa vào **bất thường của hành vi**, telemetry hạ tầng, audit của secret store và thông tin từ đối tác.

| Nguồn tín hiệu | Ví dụ | Giới hạn |
| --- | --- | --- |
| API access audit | Key ID từ vùng mạng/ASN chưa từng thấy, endpoint lạ | NAT/proxy/client migration có thể hợp lệ |
| Request pattern | Volume đột biến, nonce mới nhiều bất thường, giờ truy cập khác thường | Batch/retry/traffic spike hợp pháp gây false positive |
| Authorization denials | Credential ký hàng loạt requests ngoài scope | Có thể do bug hoặc probing của client |
| Secret manager audit | Service account đọc secret lạ hoặc ngoài lịch | Chỉ thấy những lần đọc được log |
| CI/repository scanner | Phát hiện chuỗi có hình dạng secret trong artifact | Có false positive và không tìm thấy mọi đường lộ |
| Endpoint/EDR alert | Thiết bị đối tác/developer bị xâm nhập | Không tự chứng minh secret cụ thể đã bị đọc |
| External disclosure | Partner báo nhầm gửi credential vào ticket hoặc bị mất laptop | Phải xác minh thông tin và đánh giá exposure |
| API business anomaly | Payments mới ngoài workflow thông thường | Có thể là abuse bởi credential hợp lệ hoặc bị lộ |
| Key cache/rotation logs | Key cũ tiếp tục được dùng sau thời điểm revoke | Có thể do cache propagation lỗi |

### 5.1. Tín hiệu không phải bằng chứng tuyệt đối

Một IP lạ hoặc timestamp gần hiện tại **không khẳng định** secret bị đánh cắp; một request có HMAC hợp lệ cũng **không phủ nhận** compromise. Incident triage cần phân loại:

- **Confirmed:** có bằng chứng secret bị lộ hoặc unauthorized signing capability.
- **Suspected:** có tín hiệu đủ rủi ro nhưng chưa chứng minh được.
- **False positive / benign change:** xác minh được sự kiện hợp lệ.

Với credential có scope nhạy cảm, **nghi ngờ đáng tin** có thể đủ để kích hoạt emergency revoke theo policy thay vì chờ bằng chứng tuyệt đối.

### 5.2. Key ID và principal trong telemetry

Mỗi admission decision nên có correlation ID và record key ID/principal/audience từ registry sau khi xác minh; không ghi raw shared secret. Dữ liệu cần hỗ trợ điều tra:

~~~text
eventTimeUtc
requestId/correlationId
keyId (masked/tokenized nếu cần)
trustedPrincipalId
tenantId and audience
HMAC verification result
key policy status and version
nonce admission result
authorization decision
route/action
source network metadata from trusted edge
business operation ID
~~~

Giữ logs theo retention/privacy/security policy. Không in toàn bộ signed request còn hiệu lực vào logs chỉ để tái tạo sự cố; nếu cần forensic evidence phải bảo vệ và hạn chế quyền truy cập.

## 6. Ưu tiên ứng phó: ngăn ký mới được chấp nhận

Một incident runbook nên phân biệt **cô lập (containment)** với **khôi phục phục vụ (recovery)**. Nếu shared secret bị lộ và key vẫn ACTIVE, attacker có thể tiếp tục tạo fresh, nonce-unique signed requests. Vì vậy ưu tiên đầu tiên là **ngăn key cũ được verifier chấp nhận theo mức khẩn cấp của sự cố**.

### 6.1. Quy trình cấp cao

~~~mermaid
flowchart TD
    A[Phát hiện hoặc nghi compromise] --> B[Đánh giá scope, severity, evidence]
    B --> C[Containment: revoke/disable affected key]
    C --> D[Propagate revocation tới mọi verifier/gateway]
    D --> E{Old key bị từ chối tại mọi đường xác minh?}
    E -- Chưa --> F[Fail-closed / chặn route / tăng bảo vệ]
    F --> D
    E -- Rồi --> G[Cấp secret và key ID mới qua kênh tin cậy]
    G --> H[Validate signed request mới và least privilege]
    H --> I[Investigate unauthorized actions, remediate]
    I --> J[Close incident, rotate related keys as needed]
    J --> K[Post-incident review và prevention]
~~~

Không phải cứ tạo key mới là đã cô lập thành công: **nếu key cũ còn được chấp nhận**, attacker vẫn có thể sử dụng nó.

### 6.2. Các câu hỏi phải trả lời ngay

- Secret bị lộ hay chỉ key ID?
- Evidence cho thấy attacker **đọc được secret bytes** hay có quyền gọi signing service?
- Credential có thể tác động đến service/audience và scopes nào?
- Credential có được chia sẻ giữa nhiều clients, tenants, gateways hoặc environments không?
- Registry và secret manager có thể tin cậy hay chúng cũng bị xâm nhập?
- Các verifier có cache riêng không? Revocation propagation deadline là bao nhiêu?
- Có đường backend bypass gateway không?
- Có cần **tạm chặn thao tác nhạy cảm** cho principal/resource trong thời gian thu hồi?
- Có operation IDs/idempotency store để truy vết side effects không?
- Cần bảo toàn audit records/logs và thực hiện thông báo theo chính sách nào?

### 6.3. Disable/revoke có thể cần ưu tiên hơn availability

Một lệnh emergency revoke có thể làm request hợp lệ của partner tạm thời thất bại. Đó là tradeoff có chủ đích khi đang ngăn attacker có secret. Việc **giữ key bị lộ ACTIVE để client kịp đổi** có thể mở rộng cửa sổ tấn công; nếu mức độ rủi ro cao, không dùng rotation overlap thông thường.

## 7. Emergency revocation khác rotation thông thường

**Key rotation thông thường** và **compromise response** dùng một số kỹ thuật giống nhau nhưng có mục tiêu và thời hạn khác nhau.

| Tiêu chí | Rotation có kế hoạch | Emergency revoke do compromise |
| --- | --- | --- |
| Mục tiêu | Đổi secret theo chu kỳ, không làm gián đoạn | Dừng khả năng sử dụng credential đã bị lộ |
| Key cũ | Có thể `RETIRING` trong overlap được kiểm soát | Cần `REVOKED`/deny càng sớm càng tốt theo severity |
| Chấp nhận signed requests cũ | Có thể trong overlap | Không chấp nhận bằng compromised key sau effective revoke |
| Rollback | Có thể quay lại key cũ nếu vẫn an toàn và được phép | **Không** phục hồi secret đã lộ chỉ để sửa availability |
| Client rollout | Theo lịch và cơ chế giao nhận | Khẩn cấp, kênh xác thực, có bước xác minh đối tác |
| Monitoring | Tỷ lệ chuyển sang key mới | Attempt dùng key cũ, cache lag, side effects bất thường |
| Audit | Lịch rotation và thay đổi cấu hình | Incident timeline, evidence, impact, communication |

### 7.1. State machine cho credential

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONED
    PROVISIONED --> ACTIVE: activate
    ACTIVE --> RETIRING: planned rotation
    RETIRING --> REVOKED: overlap ends
    ACTIVE --> REVOKED: confirmed/suspected compromise
    RETIRING --> REVOKED: compromise discovered
    ACTIVE --> DISABLED: temporary administrative block
    DISABLED --> ACTIVE: only if secret remains trusted
    REVOKED --> [*]
~~~

Đây là state machine minh họa. Với key **đã bị compromise**, trạng thái REVOKED thường phải được coi là **terminal cho identity đó**; không cho nút rollback UI biến nó thành ACTIVE.

Nếu muốn thử một secret mới sau sự cố, hãy cấp **key ID mới**. Tái sử dụng ID cũ có thể làm cache/registry/version mơ hồ và phá forensic audit.

### 7.2. Không dùng signed timestamp để “hồi sinh” key bị thu hồi

Lỗi nguy hiểm:

~~~text
if signedTimestamp < revokedAt:
    accept key even though status == REVOKED
~~~

Attacker biết secret có thể tự tạo request mới nhưng đặt timestamp **trước revokedAt**; nếu timestamp đó vẫn nằm trong cửa sổ freshness, request có thể vượt logic trên.

**Chính sách khuyến nghị:** Với compromised key, verifier kiểm **trạng thái revocation hiện tại, authoritative theo server**, tại thời điểm admission. `X-Timestamp` là input do caller tạo và chỉ được bảo đảm tính toàn vẹn theo secret đã lộ; **không phải bằng chứng request thực sự đã tồn tại trước khi revoke**.

Nếu hệ thống có cơ chế chấp nhận các signed jobs được ký trước revoke, đó là protocol/forensic trust model riêng (ví dụ dựa trên trusted server receipt timestamp hoặc durable queue admission), không nên xây chỉ bằng signed client timestamp.

### 7.3. Key cũ cần bị từ chối bất chấp HMAC tag đúng

~~~text
keyId=k3 -> registry status REVOKED
tag = HMAC(stolenSecretK3, canonicalRequest)
tag matches -> cryptography correct
authorization decision -> not reached
authentication decision -> reject due to key policy
~~~

Tính HMAC đúng không khôi phục quyền sử dụng của key đã revoked. Trình tự có thể kiểm status trước khi tính MAC để loại sớm nhưng phải không tiết lộ key status trái policy.

## 8. Revocation propagation trong cluster và gateway

Một bản ghi `REVOKED` trong database **không đồng nghĩa** tất cả verifier đã từ chối key đó. Trong mô hình có cache/replicas:

~~~mermaid
flowchart LR
    IR[Security response] --> REG[Credential registry REVOKED]
    REG --> A[Verifier A cache]
    REG --> B[Verifier B cache]
    REG --> G[Gateway cache]
    A --> D[Reject k3]
    B --> E[May still accept stale k3]
    G --> F[Policy depends on cache freshness]
~~~

### 8.1. Stale ACTIVE là security bug nếu ngoài policy

Timeline:

~~~text
T0  k3 ACTIVE, shared secret exposed
T1  registry changes k3 -> REVOKED
T2  node A cache refreshes -> REVOKED
T3  node B continues using cached ACTIVE record
T4  attacker signs a new request using stolen secret
T5  node B verifies HMAC -> PASS and admits request
~~~

**Root cause:** revocation không được thực thi ở tất cả các admission paths; HMAC primitive không có lỗi.

### 8.2. Các cơ chế giảm nguy cơ

Tùy yêu cầu, hệ thống có thể kết hợp:

- **Authoritative revocation check** trên request nhạy cảm hoặc theo thời hạn cache chặt.
- Push invalidation tới gateways/backend, có version/revision chống stale overwrite.
- Denylist/tombstone có tính đơn điệu: một ID đã REVOKED không được cache cũ âm thầm khôi phục.
- Global/tenant/key-level **kill switch** được enforce trước business handler.
- Cache TTL và **maximum revocation propagation SLA** được đo và cảnh báo.
- Nếu không xác nhận được trạng thái sau emergency revoke, **fail closed** trên route/credential có rủi ro cao.
- Block direct backend access để không bypass gateway policy.
- Kiểm soát rollout nhiều versions của verifier: version cũ không được hiểu `REVOKED` thành status cho phép.

Không có cơ chế cache bất đồng bộ nào tự bảo đảm **thu hồi tức thời tại mọi vùng** chỉ vì một database write thành công. Cần định nghĩa mức consistency và failover behavior thực tế.

### 8.3. Tránh stale refresh đè revocation

~~~text
T0 Thread A fetches stale ACTIVE record v9
T1 Registry marks REVOKED record v10
T2 Thread B caches REVOKED v10
T3 Thread A completes and overwrites cache with ACTIVE v9
~~~

Cần monotonic version checks hoặc fencing, không cho `v9` ghi đè `v10`; một revocation tombstone không được xóa bằng refresh không đáng tin. Test nên điều phối interleaving chủ động bằng barrier/latch.

### 8.4. Multi-region và partition

Nếu region A nhận revocation còn region B mất kết nối registry, region B không nên cho compromised key đi tiếp dựa trên cache ACTIVE không có giới hạn nếu policy yêu cầu mạnh. Có thể phải hy sinh availability tại B cho tới khi B có authority đáng tin.

Một replay store atomic trong region B **không giải quyết** stale key status. Hai bảo vệ này độc lập.

## 9. Cấp credential thay thế sau sự cố

Sau containment, cần tạo và triển khai **secret mới độc lập**, tránh vô tình đưa nó qua đúng đường đã làm lộ secret cũ.

### 9.1. Các bước khôi phục đề xuất

1. Chọn **new key ID**, ví dụ `partner-a-k4`, không tái sử dụng `k3` đã compromise.
2. Sinh secret mới từ **CSPRNG** có entropy phù hợp (ví dụ ngẫu nhiên 256 bit cho HMAC-SHA256); không dùng timestamp, UUID định dạng cố định, mật khẩu con người hoặc secret cũ đã hash nếu không có thiết kế KDF được kiểm toán.
3. Lưu dưới secret manager/KMS với access controls tối thiểu và audit.
4. Gắn principal/tenant/audience/allowed algorithm/scopes và validity hợp lý, không tự copy các quyền quá rộng từ compromised credential.
5. Chuyển secret cho client qua **kênh có xác thực, bảo mật** được thiết kế, không paste vào log/chat/email không an toàn.
6. Yêu cầu client thay cấu hình, loại secret cũ khỏi runtime, CI variables và nơi lưu khác; chú ý secret cũ trong backups.
7. Dùng một **test signed request ít tác động** để kiểm k4 hoạt động đúng canonical contract, MAC, timestamp/nonce, gateway và authorization.
8. Xác minh k3 vẫn **REVOKED trên mọi verifier**, kể cả khi client đã chuyển k4.
9. Giám sát attempts dùng k3 và traffic k4; không log raw secret/tag.
10. Cập nhật inventory, incident timeline, ownership và rotation policy.

### 9.2. Không coi rotation hoàn tất khi client nói đã đổi

Client-side deployment có thể đã cập nhật nhưng server vẫn còn key cũ ACTIVE; hoặc server đã kích hoạt k4 nhưng client đang dùng backup/staging với k3. **Điểm hoàn tất bảo mật** là k3 bị từ chối theo revocation guarantee của mọi admission path, không chỉ k4 hoạt động.

### 9.3. Cẩn thận với environments và copies

Nếu cùng secret được dùng ở dev/staging/prod, phải đánh giá **tất cả environments**; tốt hơn không chia sẻ secrets qua các môi trường. Nếu incident xuất phát từ CI, laptop hoặc gateway logs, secret mới đưa vào cùng đường rò có thể bị compromise ngay.

Hãy xử lý root cause trước hoặc đồng thời với cấp key mới, tăng kiểm soát tạm thời khi chưa xác minh được đường lộ đã bị đóng.

### 9.4. “Xoay secret” khác với “mã hóa lại cùng secret”

~~~text
hex(secretBytes) -> base64(secretBytes)
encryptThenDecrypt(sameSecretBytes)
rename keyId without changing secretBytes
~~~

Các thao tác đó không tạo một key mới độc lập. Attacker vẫn biết bytes cũ và có thể tiếp tục tính HMAC nếu verifier còn chấp nhận bytes đó. Recovery cần secret mới ngẫu nhiên **và key cũ bị từ chối**.

## 10. Blast radius và cách giới hạn

Một inventory theo credential nên trả lời:

~~~text
key ID
credential owner/client
environment
allowed audiences/services
allowed methods/routes/scopes
tenant/resource constraints
algorithm/version
secret storage and access principals
rotation/expiry/revocation owner
servers/gateways that accept this key
last accepted request and audit trail
~~~

### 10.1. Per-client/per-audience credentials

| Thiết kế | Hậu quả khi một secret bị lộ |
| --- | --- |
| Một secret dùng chung 100 partners | Phải nghi ngờ nhiều principal, khó revoke một partner |
| Một secret riêng từng partner | Có thể cô lập đúng partner bị ảnh hưởng |
| Cùng secret cho orders và payments | Có rủi ro lan sang nhiều services nếu policy/canonical audience sai |
| Secret riêng theo audience | Giảm phạm vi cross-service |
| Secret với scope write rộng | Có thể giả mạo nhiều thao tác nhạy cảm |
| Secret least-privilege | Giảm các thao tác attacker có thể yêu cầu |
| Không có unique business operation ID | Khó phân biệt/khôi phục tác động lặp |
| Có durable idempotency + audit | Hỗ trợ điều tra, giảm duplicate effects nhưng không chặn mọi request mới được ký |

### 10.2. Signed audience và authorization là lớp giới hạn thiệt hại

Một request có HMAC hợp lệ từ stolen key `orders-api` không nên được chấp nhận ở `payments-api` chỉ vì cả hai dùng cùng thuật toán. Cần binding audience/service trong canonical request hoặc key policy tương đương, đồng thời kiểm phương thức/route/scope.

Dù attacker có secret của principal tenant A, authorization vẫn phải từ chối hành động trên resource tenant B. **Đừng coi MAC hợp lệ là quyền thực thi bất kỳ yêu cầu nào.**

### 10.3. Rate limiting, risk controls và business constraints

Trong thời gian nghi compromise, có thể áp dụng:

- Giới hạn tốc độ theo trusted principal/key ID sau xác thực (và network source metadata đã được trusted edge xác nhận).
- Tạm hạn chế các hành động rủi ro cao hoặc yêu cầu out-of-band approval cho số tiền/lệnh vượt ngưỡng.
- Transaction caps, account allowlists và validation độc lập với HMAC.
- API operation status và business idempotency cho retry an toàn.
- Circuit breaker/key-level deny cho credential bị nghi ngờ.

Các biện pháp trên **giảm thiệt hại**, không thay emergency revocation khi shared secret đã lộ.

## 11. Tác động lên replay protection và idempotency

### 11.1. Attacker có thể có timestamp/nonce mới

~~~text
CompromisedKey k3 secret leaked
R1 = sign(k3, timestamp=T1, nonce=N1, body=payment-1)
R2 = sign(k3, timestamp=T2, nonce=N2, body=payment-2)

HMAC(R1) -> valid
HMAC(R2) -> valid
timestamp fresh -> valid
nonce new -> valid
~~~

Replay gate chỉ chặn **dùng lại nonce đã claim**, không biết N1/N2 là của attacker. Vì vậy không được dùng anti-replay metrics “ít duplicate” làm bằng chứng credential vẫn an toàn.

### 11.2. Không xóa nonce entries để “khởi động lại” key

Khi revoke k3, có thể không cần giữ tất cả nonce records lâu như lúc k3 còn ACTIVE **nếu mọi verifier chắc chắn không còn chấp nhận k3**; nhưng xóa sớm trong lúc revocation chưa propagate có thể mở lại replay window ở node stale. Thiết kế đơn giản là giữ nonce theo TTL đã cấp và để key status reject độc lập.

### 11.3. Idempotency ngăn tác động trùng, không ngăn attacker tạo việc mới

Attacker có stolen secret có thể gửi hai requests khác nhau với operation IDs khác nhau. Idempotency sẽ không coi đó là duplicate. Business layer vẫn cần authorization, limits, fraud detection và incident containment.

Nếu client hợp pháp retry cùng payment operation bằng nonce mới, idempotency store giúp tránh double charge. Do đó nonce và idempotency có **hai thời hạn lưu khác nhau** và xử lý hai mục tiêu khác nhau.

## 12. Audit, forensic và khắc phục tác động

Sau khi dừng key bị lộ, điều tra nhằm trả lời **đã xảy ra gì**, không chỉ “đã thay key chưa”.

### 12.1. Xây dựng khoảng thời gian có nguy cơ

Một số mốc:

~~~text
lastKnownSecureTime
firstPossibleExposureTime
firstSuspiciousUseTime
confirmedDetectionTime
revocationRequestedTime
effectiveRejectTimeAtAllVerifiers
newCredentialActivatedTime
rootCauseRemediatedTime
incidentClosedTime
~~~

Nếu không biết chính xác lúc secret bị đọc, đừng suy từ lần request bất thường đầu rằng mọi request trước đó đều an toàn. Dùng log retention, secret store audit, deployment history và bằng chứng endpoint để ước lượng khoảng ảnh hưởng; ghi rõ uncertainty.

### 12.2. Tìm thao tác không được phép

- Liệt kê các requests có key ID bị compromise trong time window.
- Liên kết correlation ID, principal, route, resource, tenant, request outcome và business operation ID.
- Đối chiếu với đối tác/client hợp pháp nếu có kênh xác minh.
- Xem các thao tác có tác động tiền, quyền, dữ liệu, webhook và downstream events.
- Phân biệt request rejected, accepted, committed, retried và trạng thái không xác định do mất response.
- Đối chiếu durable business records thay vì chỉ dựa access logs.
- Lập kế hoạch bồi hoàn/rollback/notification theo chính sách và yêu cầu áp dụng.

### 12.3. Không thể dựa vào HMAC để chứng minh request do ai ký sau compromise

Khi shared secret đã bị lộ, một tag hợp lệ của request trong khoảng ảnh hưởng **không phân biệt được legitimate client và attacker** chỉ bằng crypto. Cần thêm network logs, user approvals, transaction records, issuer audit, immutable evidence và các nguồn độc lập.

Nếu một secret được chia sẻ giữa nhiều parties, giới hạn quy trách nhiệm là một **đặc tính kiến trúc**, không phải lỗi có thể sửa hồi tố.

### 12.4. Evidence handling

Bảo toàn log và forensic evidence theo incident process, hạn chế người đọc, tránh di chuyển raw credentials không kiểm soát. Nếu cần xác minh rằng secret đã xuất hiện trong một artifact, dùng công cụ/luồng quét an toàn để đối chiếu thay vì copy secret ra chat hoặc báo cáo. Bảo đảm những thay đổi config/rotations được audit có timestamp và actor.

## 13. Java 17: credential status và policy khi compromise

Để viết test tái lập, ta tách **lifecycle policy** ra khỏi HTTP parser và crypto primitive. Ví dụ dưới đây dùng Java 17 và secret test giả; production có thể tách registry metadata với KMS/HSM, song phải giữ cùng semantics.

### 13.1. Trạng thái credential

~~~java
public enum KeyStatus {
    PROVISIONED,
    ACTIVE,
    RETIRING,
    DISABLED,
    REVOKED
}
~~~

Quy tắc học thuật trong bài:

- `ACTIVE`: có thể verify trong validity window nếu đúng audience và algorithm.
- `RETIRING`: chỉ verify trong overlap với `verifyUntil` rõ ràng; trạng thái này dùng cho rotation **không có dấu hiệu compromise**.
- `REVOKED`: **không bao giờ verify thành công**, kể cả signed timestamp trước `revokedAt`.
- `DISABLED`: không verify cho tới khi policy đáng tin cho phép thay đổi; không tự re-enable credential đã lộ.
- `PROVISIONED`: chưa có hiệu lực.
- Credentials hết hạn vẫn bị từ chối dù status ACTIVE.

### 13.2. Record minh họa với defensive copy

~~~java
import java.time.Instant;
import java.util.Objects;

public record CredentialRecord(
        String keyId,
        String principalId,
        String audience,
        KeyStatus status,
        Instant notBefore,
        Instant notAfter,
        Instant verifyUntil,
        Instant revokedAt,
        long revision,
        byte[] secretBytes) {

    public CredentialRecord {
        Objects.requireNonNull(keyId);
        Objects.requireNonNull(principalId);
        Objects.requireNonNull(audience);
        Objects.requireNonNull(status);
        Objects.requireNonNull(notBefore);
        Objects.requireNonNull(notAfter);
        Objects.requireNonNull(secretBytes);

        if (!notBefore.isBefore(notAfter)
                || revision < 0
                || secretBytes.length == 0) {
            throw new IllegalArgumentException("Invalid record");
        }
        secretBytes = secretBytes.clone();
    }

    @Override
    public byte[] secretBytes() {
        return secretBytes.clone();
    }
}
~~~

**Giới hạn của ví dụ:** `byte[]` trong record chỉ phù hợp test/ứng dụng đơn giản; production có thể dùng secret manager và crypto operations để giảm số bản sao secret. Không log record bằng `toString()` và không đưa record vào error response. Defensive copying không loại bỏ hoàn toàn secret tồn tại trong heap dump.

### 13.3. Policy verify theo server clock hiện tại

~~~java
import java.time.Instant;

public final class CredentialPolicyV1 {
    private CredentialPolicyV1() {}

    public static boolean canVerifyAt(
            CredentialRecord credential,
            String expectedAudience,
            Instant serverNow) {

        if (credential == null || serverNow == null
                || !"payments-api".equals(expectedAudience)
                || !expectedAudience.equals(credential.audience())
                || serverNow.isBefore(credential.notBefore())
                || !serverNow.isBefore(credential.notAfter())) {
            return false;
        }

        return switch (credential.status()) {
            case ACTIVE -> true;
            case RETIRING -> credential.verifyUntil() != null
                    && serverNow.isBefore(credential.verifyUntil());
            case PROVISIONED, DISABLED, REVOKED -> false;
        };
    }
}
~~~

Điểm quan trọng: `canVerifyAt` **không nhận signedTimestamp làm tham số quyết định status**. Vì attacker có compromised secret có thể tạo HMAC đúng với một timestamp tùy ý trong freshness window, `signedTimestamp < revokedAt` không phải bằng chứng một request đã được gửi từ trước khi lộ key.

Trong production, `expectedAudience` nên được lấy từ service route/registry, không tùy ý từ client. Policy algorithm cũng phải được kiểm trong key record/version phía server; ví dụ verifier ở mục sau cố định `HmacSHA256`.

### 13.4. Lưu thông tin revocation đáng tin

Một sự kiện revocation cần tối thiểu:

~~~text
credentialId
newStatus = REVOKED
revision = previousRevision + 1
effectiveAt = server-authoritative time
actor = incident response or authorized security service
reasonCode = COMPROMISED / SUSPECTED / POLICY
incidentId
changeAuditId
~~~

Không cần đưa `revocationReason` vào HMAC request hay trả nó trong public HTTP response. Nếu có replicated caches, revision giúp tránh record cũ đè record mới. Tuy nhiên revision **không tự đồng bộ** các node đã bị network partition; cần propagation guarantee/fail-closed riêng.

## 14. Java 17: strict key lookup và HMAC verifier

### 14.1. Key ID format và registry contract

~~~java
import java.util.Optional;
import java.util.regex.Pattern;

public interface CredentialRegistry {
    /**
     * Exact lookup. Empty chỉ dùng khi nguồn dữ liệu tin cậy xác nhận
     * không có credential; outage/timeout phải ném exception.
     */
    Optional<CredentialRecord> findExact(String keyId)
            throws RegistryUnavailableException;
}
~~~

~~~java
public final class RegistryUnavailableException
        extends RuntimeException {
    public RegistryUnavailableException(String message) {
        super(message);
    }
}
~~~

~~~java
import java.util.regex.Pattern;

public final class KeyIdV1 {
    private static final Pattern VALID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private KeyIdV1() {}

    public static String requireValid(String keyId) {
        if (keyId == null || !VALID.matcher(keyId).matches()) {
            throw new IllegalArgumentException("Invalid key ID");
        }
        // Không trim, lowercase, percent-decode hoặc alias fallback.
        return keyId;
    }
}
~~~

Trước khi gọi registry, HTTP edge phải xác minh **chính xác một source key ID** từ header/Authorization scheme đã định nghĩa; reject duplicate field names không phân biệt case. Nếu gateway đã merge/drop duplicates, backend khó phục hồi evidence; raw ingress tests là bắt buộc.

### 14.2. Kết quả nội bộ của MAC verifier

~~~java
public enum MacOutcome {
    INVALID_KEY_ID,
    UNKNOWN_KEY,
    KEY_NOT_ALLOWED,
    LOOKUP_UNAVAILABLE,
    INVALID_TAG,
    MAC_MISMATCH,
    MAC_VALID
}
~~~

Các trạng thái là **internal outcomes** phục vụ test/metrics. API bên ngoài có thể ánh xạ sang generic authentication failure để hạn chế key enumeration; không trả key status, secretRef hoặc expected tag.

### 14.3. Java verifier với key status trước HMAC

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Clock;
import java.util.Optional;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class CompromiseAwareMacVerifierV1 {
    private final CredentialRegistry registry;
    private final Clock clock;

    public CompromiseAwareMacVerifierV1(
            CredentialRegistry registry, Clock clock) {
        this.registry = registry;
        this.clock = clock;
    }

    /**
     * PRECONDITION:
     * - Parser HTTP đã từ chối duplicate/ambiguous signed headers.
     * - canonicalBytes do trusted verifier tái dựng từ HTTP request.
     * - keyId, timestamp, nonce, audience đều ràng buộc trong bytes ký.
     * - presentedTag là full HMAC-SHA256 tag đã strict decode (32 bytes).
     *
     * Helper này CHỈ kiểm key policy + HMAC; chưa làm anti-replay,
     * chưa tạo principal và chưa authorize business action.
     */
    public MacOutcome verify(
            String rawKeyId,
            byte[] canonicalBytes,
            byte[] presentedTag) {

        final String keyId;
        try {
            keyId = KeyIdV1.requireValid(rawKeyId);
        } catch (IllegalArgumentException invalid) {
            return MacOutcome.INVALID_KEY_ID;
        }

        if (canonicalBytes == null || presentedTag == null
                || presentedTag.length != 32) {
            return MacOutcome.INVALID_TAG;
        }

        final Optional<CredentialRecord> found;
        try {
            found = registry.findExact(keyId);
        } catch (RegistryUnavailableException unavailable) {
            return MacOutcome.LOOKUP_UNAVAILABLE;
        }

        if (found.isEmpty()) {
            return MacOutcome.UNKNOWN_KEY;
        }

        CredentialRecord record = found.get();
        if (!record.keyId().equals(keyId)
                || !CredentialPolicyV1.canVerifyAt(
                    record, "payments-api", clock.instant())) {
            return MacOutcome.KEY_NOT_ALLOWED;
        }

        final byte[] expected;
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(
                    record.secretBytes(), "HmacSHA256"));
            expected = mac.doFinal(canonicalBytes);
        } catch (GeneralSecurityException cryptoError) {
            // Không chấp nhận request khi crypto backend/config lỗi.
            return MacOutcome.LOOKUP_UNAVAILABLE;
        }

        return MessageDigest.isEqual(expected, presentedTag)
                ? MacOutcome.MAC_VALID
                : MacOutcome.MAC_MISMATCH;
    }
}
~~~

**Đọc đúng phạm vi ví dụ:** `MAC_VALID` không đồng nghĩa request được xử lý. Phải kiểm freshness, nonce atomic claim và authorization tiếp. Hàm giả định `canonicalBytes` được tạo bởi trusted canonicalizer bao gồm **exact key ID**. Nếu caller gửi canonical string để server dùng nguyên, attacker có thể điều khiển nội dung được xác minh và phá signing boundary.

### 14.4. Revocation bắt buộc thắng MAC

Giả sử attacker có test secret của k3; hắn tạo tag hợp lệ cho request mới. Nếu registry trả k3 với `status=REVOKED`, `verify` phải trả `KEY_NOT_ALLOWED` **mà không cần nhìn tag**. Đó là policy đúng, không phải false negative của HMAC.

### 14.5. Một giới hạn quan trọng: stale registry state

Helper chỉ có thể quyết định dựa trên **record mà registry adapter cung cấp**. Nếu adapter trả stale `ACTIVE` sau khi key đã revoke ở trung tâm, MAC vẫn có thể qua.

Vì vậy, production cần authoritative revocation source, cache invalidation/consistency policy, failure handling và integration tests. Unit test của helper **không** chứng minh mọi node đã nhận revocation.

### 14.6. Fail-closed nhưng không giấu sự cố

`LOOKUP_UNAVAILABLE` phải không tạo principal/không gọi business. Production nên phân biệt thêm `CRYPTO_UNAVAILABLE`, `SECRET_UNAVAILABLE`, `REVOCATION_STATE_UNCERTAIN` trong internal telemetry; không dùng những trạng thái này để tự chấp nhận request.

## 15. Java 17: sinh secret mới sau compromise

Một helper nhỏ để cấp **new key material**, không phải hệ thống phân phối production:

~~~java
import java.security.SecureRandom;
import java.util.Arrays;

public final class NewHmacSecretGenerator {
    private static final int SECRET_BYTES = 32;
    private final SecureRandom random = new SecureRandom();

    public byte[] newSecret() {
        byte[] value = new byte[SECRET_BYTES];
        random.nextBytes(value);
        return value;
    }

    public static void clearTemporaryCopy(byte[] secret) {
        if (secret != null) {
            Arrays.fill(secret, (byte) 0);
        }
    }
}
~~~

32 byte từ CSPRNG là **một lựa chọn ví dụ** phù hợp cho HMAC-SHA256, không phải thông số bắt buộc duy nhất của HMAC. Không lấy secret mới bằng cách tăng counter, nối key ID hoặc hash lại stolen secret rồi giả định an toàn.

**Cảnh báo production:** Việc trả về `byte[]` vẫn đặt secret trong memory và caller phải quản lý vòng đời. Việc zeroize một array không bảo đảm mọi bản sao/garbage-collected object/heap dump đã bị xóa. Nếu có HSM/KMS hỗ trợ sinh và sử dụng secret trong môi trường giới hạn export, nên cân nhắc cách đó. Không in secret ngay cả trong test output hoặc báo cáo sự cố.

### 15.1. Tránh “roll back” sang secret đã lộ

Nếu rollout k4 gặp lỗi canonicalization, **không tự kích hoạt lại k3 đã REVOKED**. Sửa contract, client deployment hoặc phát hành một credential mới khác. Rollback traffic có thể sử dụng một credential **vẫn được đánh giá an toàn** nếu đã được thiết kế trước, không dùng compromised secret.

## 16. Security pipeline đầy đủ

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant E as Edge Gateway
    participant V as HMAC Verifier
    participant K as Key Registry
    participant N as Replay Store
    participant A as Application

    C->>E: Request with key ID, timestamp, nonce, tag
    E->>E: Strict HTTP parsing, duplicates and size limits
    E->>V: Signed HTTP semantics under contract
    V->>K: Exact key lookup, current status and audience
    K-->>V: Active policy record / revoked / unavailable
    V->>V: Rebuild canonical bytes and verify HMAC
    V->>V: Check signed timestamp freshness
    V->>N: Atomic nonce admission after valid MAC
    N-->>V: New / replay / unavailable
    V->>A: Trusted principal only when admitted
    A->>A: Authorize action/resource/tenant
    A->>A: Idempotency and transaction
~~~

### 16.1. Key bị compromise phải bị chặn trước business

Sau emergency revoke, một request ký bằng k3 phải bị từ chối **bất kể**:

- K3 secret có thể tính HMAC đúng.
- Timestamp mới hoặc cũ nhưng còn fresh.
- Nonce chưa từng xuất hiện.
- Client gửi request trên path khác.
- Gateway chuyển HTTP/2 → HTTP/1.1.
- Key ID được viết trong `Authorization` hay header riêng theo contract.
- Client tự khai mình là trusted principal.
- Một pod khác chưa nhận được invalidation (pod này phải đáp ứng propagation/fail-closed guarantee).

### 16.2. Tách việc kiểm key khỏi phân quyền

Ngay cả với key k4 mới và MAC đúng, nếu principal tenant A gọi thao tác trên tenant B, authorization phải từ chối. Ngược lại, quyền theo business policy không được dùng để bỏ qua key revocation: một key đã bị compromise không nên được “cho qua vì role admin”.

### 16.3. Signed timestamp không chứng minh thời điểm tạo request

Khi secret đã lộ, attacker có thể ký một timestamp bất kỳ mà còn vượt freshness. Vì vậy việc quyết định key có bị revoke phải dựa vào **trusted server state ở thời điểm tiếp nhận/admission**, không chỉ so `signedTimestamp` với `revokedAt`.

## 17. JUnit 5: key bị lộ phải reject dù tag hợp lệ

Bộ kiểm thử dưới đây minh họa JUnit Jupiter cho `CredentialPolicyV1` và `CompromiseAwareMacVerifierV1`. Mỗi class/enum/record Java public cần đặt trong file Java tương ứng khi chạy trong project. Các secrets là **fixture test**, không phải secret production.

### 17.1. Fake registry chỉ dùng để kiểm logic

~~~java
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public final class FakeCredentialRegistry implements CredentialRegistry {
    private final Map<String, CredentialRecord> records =
            new ConcurrentHashMap<>();
    private volatile boolean unavailable;

    public void put(CredentialRecord record) {
        records.put(record.keyId(), record);
    }

    public void setUnavailable(boolean value) {
        unavailable = value;
    }

    @Override
    public Optional<CredentialRecord> findExact(String keyId) {
        if (unavailable) {
            throw new RegistryUnavailableException(
                    "Test registry unavailable");
        }
        return Optional.ofNullable(records.get(keyId));
    }
}
~~~

Fake không mô phỏng cache invalidation, replication, credential revision hoặc HSM. Nó chỉ hỗ trợ kiểm tra policy/cryptographic behavior trong một process.

### 17.2. Unit tests theo trạng thái key và thời gian

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import org.junit.jupiter.api.Test;

public final class CredentialPolicyV1Test {
    private static final Instant START =
            Instant.parse("2026-06-01T00:00:00Z");
    private static final Instant END =
            Instant.parse("2026-07-01T00:00:00Z");

    private static CredentialRecord record(
            KeyStatus status, Instant verifyUntil) {

        return new CredentialRecord(
                "partner-a-k3",
                "partner-a-service",
                "payments-api",
                status,
                START,
                END,
                verifyUntil,
                START.plusSeconds(3600),
                5L,
                "test-secret-only".getBytes(StandardCharsets.UTF_8));
    }

    @Test
    void revokedIsDeniedEvenWhenTimestampWouldBeFresh() {
        Instant serverNow = START.plusSeconds(3601);
        assertFalse(CredentialPolicyV1.canVerifyAt(
                record(KeyStatus.REVOKED, null),
                "payments-api", serverNow));
    }

    @Test
    void disabledAndProvisionedCannotVerify() {
        Instant serverNow = START.plusSeconds(30);
        assertFalse(CredentialPolicyV1.canVerifyAt(
                record(KeyStatus.DISABLED, null),
                "payments-api", serverNow));
        assertFalse(CredentialPolicyV1.canVerifyAt(
                record(KeyStatus.PROVISIONED, null),
                "payments-api", serverNow));
    }

    @Test
    void activeHasInclusiveStartExclusiveEnd() {
        CredentialRecord active = record(KeyStatus.ACTIVE, null);

        assertFalse(CredentialPolicyV1.canVerifyAt(
                active, "payments-api", START.minusNanos(1)));
        assertTrue(CredentialPolicyV1.canVerifyAt(
                active, "payments-api", START));
        assertTrue(CredentialPolicyV1.canVerifyAt(
                active, "payments-api", END.minusNanos(1)));
        assertFalse(CredentialPolicyV1.canVerifyAt(
                active, "payments-api", END));
    }

    @Test
    void retiringRequiresOverlapCutoff() {
        Instant cutoff = START.plusSeconds(120);
        CredentialRecord retiring =
                record(KeyStatus.RETIRING, cutoff);

        assertTrue(CredentialPolicyV1.canVerifyAt(
                retiring, "payments-api", cutoff.minusNanos(1)));
        assertFalse(CredentialPolicyV1.canVerifyAt(
                retiring, "payments-api", cutoff));
        assertFalse(CredentialPolicyV1.canVerifyAt(
                record(KeyStatus.RETIRING, null),
                "payments-api", START.plusSeconds(20)));
    }

    @Test
    void wrongAudienceFailsDespiteActiveKey() {
        assertFalse(CredentialPolicyV1.canVerifyAt(
                record(KeyStatus.ACTIVE, null),
                "orders-api", START.plusSeconds(20)));
    }
}
~~~

### 17.3. Test thực tế: signed timestamp trước revoke, MAC vẫn đúng

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.Test;

public final class CompromiseAwareMacVerifierV1Test {
    private static final Instant NOW =
            Instant.parse("2026-06-15T12:00:00Z");

    private static final byte[] TEST_SECRET =
            "fixture-hmac-key-not-for-production"
                    .getBytes(StandardCharsets.US_ASCII);

    private static byte[] signedBytes(
            String keyId, Instant timestamp) {

        String canonical = String.join("\n",
                "HMAC-REQUEST-V1",
                "POST",
                "/v1/payments",
                "",
                "audience:payments-api",
                "key-id:" + keyId,
                "timestamp:" + timestamp.getEpochSecond(),
                "nonce:6bfb21974a08417199273b09ca49a3ec",
                "body-sha256:3a6eb0790f39ac87c94f3856b2dd2c5d"
                    + "110e6811602261a9a923d3bb23adc8b7");

        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] sign(byte[] canonical)
            throws GeneralSecurityException {

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(TEST_SECRET, "HmacSHA256"));
        return mac.doFinal(canonical);
    }

    private static CredentialRecord record(
            String keyId, KeyStatus status) {

        return new CredentialRecord(
                keyId,
                "partner-a-service",
                "payments-api",
                status,
                NOW.minusSeconds(86400),
                NOW.plusSeconds(86400),
                null,
                NOW.minusSeconds(10),
                10L,
                TEST_SECRET);
    }

    @Test
    void stolenKeyCannotBeReplayedByBackdatingTimestamp()
            throws Exception {

        Instant clientSignedTs = NOW.minusSeconds(20);
        // Client timestamp trước revokedAt=NOW-10;
        // trong thực tế attacker có secret có thể tự chọn nó.
        byte[] canonical = signedBytes(
                "partner-a-k3", clientSignedTs);
        byte[] validMac = sign(canonical);

        FakeCredentialRegistry registry = new FakeCredentialRegistry();
        registry.put(record("partner-a-k3", KeyStatus.REVOKED));

        var verifier = new CompromiseAwareMacVerifierV1(
                registry, Clock.fixed(NOW, ZoneOffset.UTC));

        assertEquals(MacOutcome.KEY_NOT_ALLOWED,
                verifier.verify(
                    "partner-a-k3", canonical, validMac));
    }

    @Test
    void activeTestKeyCanPassMacButNeedsReplayAndAuthz()
            throws Exception {

        byte[] canonical = signedBytes(
                "partner-a-k4", NOW.minusSeconds(1));
        byte[] validMac = sign(canonical);

        FakeCredentialRegistry registry = new FakeCredentialRegistry();
        registry.put(record("partner-a-k4", KeyStatus.ACTIVE));

        var verifier = new CompromiseAwareMacVerifierV1(
                registry, Clock.fixed(NOW, ZoneOffset.UTC));

        assertEquals(MacOutcome.MAC_VALID,
                verifier.verify(
                    "partner-a-k4", canonical, validMac));
        // MAC_VALID chưa phải authenticated business request.
        // Middleware vẫn cần timestamp, nonce store và authz.
    }

    @Test
    void unknownKeyDoesNotFallBackToCompromisedSecret()
            throws Exception {

        byte[] canonical = signedBytes(
                "partner-a-k999", NOW);
        byte[] validForStolenSecret = sign(canonical);

        FakeCredentialRegistry registry = new FakeCredentialRegistry();
        registry.put(record("partner-a-k3", KeyStatus.ACTIVE));

        var verifier = new CompromiseAwareMacVerifierV1(
                registry, Clock.fixed(NOW, ZoneOffset.UTC));

        assertEquals(MacOutcome.UNKNOWN_KEY,
                verifier.verify(
                    "partner-a-k999",
                    canonical, validForStolenSecret));
    }

    @Test
    void registryOutageDoesNotAllowMac() throws Exception {
        byte[] canonical = signedBytes("partner-a-k4", NOW);
        byte[] validMac = sign(canonical);

        FakeCredentialRegistry registry = new FakeCredentialRegistry();
        registry.setUnavailable(true);

        var verifier = new CompromiseAwareMacVerifierV1(
                registry, Clock.fixed(NOW, ZoneOffset.UTC));

        assertEquals(MacOutcome.LOOKUP_UNAVAILABLE,
                verifier.verify("partner-a-k4", canonical, validMac));
    }

    @Test
    void changingKeyIdWithoutResigningFails()
            throws Exception {

        byte[] signedForK3 = signedBytes(
                "partner-a-k3", NOW);
        byte[] signedMac = sign(signedForK3);

        FakeCredentialRegistry registry = new FakeCredentialRegistry();
        registry.put(record("partner-a-k4", KeyStatus.ACTIVE));

        var verifier = new CompromiseAwareMacVerifierV1(
                registry, Clock.fixed(NOW, ZoneOffset.UTC));

        assertEquals(MacOutcome.MAC_MISMATCH,
                verifier.verify(
                    "partner-a-k4",
                    signedBytes("partner-a-k4", NOW),
                    signedMac));
    }
}
~~~

**Lưu ý kiểm thử:** `signedBytes` là fixture tối giản với digest cố định; nó **không thay** canonicalizer production và không chứng minh body digest đúng. Có thể dùng RFC 4231 known-answer vectors để kiểm riêng HMAC primitive, còn e2e tests cần tạo signature từ raw HTTP request/body thật.

### 17.4. Các assertions đặc biệt đáng giá

- K3 đã `REVOKED` + tag tính đúng dưới secret k3 → **reject**.
- K3 đã `REVOKED` + client-signed timestamp trước revoke → **reject**.
- Không tìm thấy ID k999 nhưng tag được ký bằng một secret còn tồn tại → **reject**, không fallback.
- Key mới k4 ACTIVE nhưng tag tính bằng k3 → **MAC mismatch**.
- Registry/KMS timeout → **fail closed**; không tạo principal hoặc claim nonce.
- `RETIRING` chỉ được phép trong overlap **nếu key chưa có dấu hiệu compromise**.
- Key record mới mang revision cao hơn không bị cache fetch cũ đè lên.
- Key status được kiểm tại **server admission time**; không dựa vào signed timestamp để phục hồi trạng thái cũ.

## 18. Kiểm thử hệ thống phân tán sau emergency revoke

Một unit test tại một node không chứng minh **tất cả nodes** đã ngừng chấp nhận key.

### 18.1. Scenario multi-node

~~~text
Setup:
  k3 ACTIVE on registry
  gateway G, verifier nodes A/B/C all accept k3
  k4 new key pending

T0:
  generate valid signed request using test secret k3
  assert accepted before revocation in test environment

T1:
  mark k3 REVOKED, increment credential revision

T2:
  send fresh signed requests with new nonce under k3
  through G->A, G->B, G->C and allowed regions

Expected:
  all paths reject under declared revocation propagation guarantee

T3:
  activate k4, sign with independent new secret

Expected:
  k4 passes HMAC/policy and still enforces authorization and replay
  k3 remains REVOKED, even when k4 traffic has problems
~~~

**Không chạy thử với secret/payment thật** nếu không có phạm vi kiểm thử được cấp phép; sử dụng fixture và môi trường test hoặc traffic kiểm soát.

### 18.2. Race và cache version

Test bằng barrier/latch:

~~~text
Worker A fetches credential k3 version 9 (ACTIVE), pauses
Security service revokes k3, stores version 10 (REVOKED)
Worker B refreshes cache with version 10
Worker A resumes with old version 9

Expected:
  stale version 9 must NOT overwrite version 10
~~~

Nếu triển khai không có version fencing mà chỉ dùng TTL, phải ghi rõ maximum revocation lag và khả năng một node accept trong lag; không tuyên bố immediate revocation.

### 18.3. Registry outage đúng lúc thu hồi

~~~text
Registry:
  k3 -> REVOKED

Verifier B:
  has stale ACTIVE in cache
  cannot reach registry due to partition

Required result for strict emergency policy:
  reject k3 or suspend admission until state trustworthy
~~~

Một thiết kế ưu tiên availability có thể vẫn accept từ stale cache nhưng **phải xem đó là giới hạn an ninh đáng kể**, không phải một implementation của immediate revoke.

### 18.4. Gateway bypass và double verification

Nếu gateway reject k3 nhưng backend endpoint có thể truy cập trực tiếp và vẫn nhận k3, containment chưa hoàn thành. Test cả public ingress, internal routing, failover/secondary hostname và backend direct-access protections.

Nếu gateway đã claim nonce và backend cũng claim lại same namespace, request hợp lệ k4 có thể bị replay reject sai. Cần chỉ định owner của replay admission; vấn đề này độc lập với emergency revocation.

### 18.5. Key revoke còn cần giới hạn trên connections đang hoạt động

HMAC thường xác thực từng HTTP request; nếu client duy trì keep-alive hoặc HTTP/2 connection sau revoke, **mỗi request mới** vẫn phải được áp key status policy. Không dựa vào việc connection đã bắt tay/TLS từ trước rồi bỏ kiểm credential cho requests về sau.

Nếu hệ thống còn cấp bearer token/session từ một request ký HMAC trước đây, phải đánh giá **thu hồi các credentials phát sinh** theo phạm vi sự cố; revoke HMAC key không tự xóa những sessions/tokens đã cấp từ trước.

## 19. Ma trận kiểm thử Credential compromise

Test phải tách **cryptographic correctness** khỏi **credential policy**, **operational containment** và **business impact**. Một implementation HMAC hoàn toàn chính xác vẫn có thể thất bại khi secret bị lộ.

### 19.1. Key status và secret pairing

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Happy path | k4 ACTIVE, secret mới, đúng audience | Qua bước MAC, còn cần replay/authz |
| Compromise | k3 REVOKED, tag được tính đúng dưới stolen secret k3 | **Reject** |
| Compromise | k3 REVOKED, signed timestamp trước revokedAt | **Reject** |
| Compromise | k3 REVOKED, nonce mới chưa từng xuất hiện | **Reject** |
| Compromise | k3 REVOKED, HMAC tag có đủ 32 byte đúng | **Reject** |
| Compromise | k3 REVOKED, request gửi qua gateway phụ | **Reject** |
| Compromise | k3 bị disable tạm theo incident policy | **Reject** |
| Identity | K4 key ID nhưng signature tính bằng k3 | MAC mismatch |
| Identity | Unknown ID k999 với signature từ k3 | Reject, không fallback |
| Identity | Key ID đổi case hoặc chứa ký tự lạ | Exact-match reject/invalid |
| Identity | Duplicate `X-Key-Id`/`Authorization` | Reject HTTP ambiguity |
| Lifecycle | PROVISIONED chưa kích hoạt | Reject |
| Lifecycle | ACTIVE trước notBefore | Reject |
| Lifecycle | ACTIVE tại notAfter, exclusive boundary | Reject |
| Lifecycle | RETIRING vượt verifyUntil | Reject |
| Lifecycle | RETIRING nhưng bị nghi compromise | Emergency revoke, reject |
| Lifecycle | Rollback thử re-activate compromised k3 | Denied by policy |
| Audience | Key k4 orders chỉ ký payments | Reject |
| Algorithm | Client khai downgrade algorithm | Không override server policy |
| Scope | K4 least-privilege gọi route ngoài scope | Authorization reject |

### 19.2. Timestamp, nonce và request signing

| Test | Tình huống | Kỳ vọng |
| --- | --- | --- |
| Replay | Cùng signed request R gửi lại | Nonce store reject nếu k chưa revoke |
| Compromise | New signature, fresh timestamp, new nonce trên key revoked | Reject theo key status |
| Forged timestamp | Attacker khai T trước revokedAt còn trong freshness | Vẫn reject |
| MAC tampering | Sửa body/path/signed header mà giữ tag | MAC mismatch |
| Nonce tampering | Sửa nonce mà giữ tag | MAC mismatch |
| Timestamp too old | Quá maxPastAge | Reject |
| Timestamp too future | Vượt futureSkew | Reject |
| Nonce claim timing | Request MAC sai/REVOKED | Không ghi nonce từ request chưa authenticated |
| Replay store outage | MAC hợp lệ nhưng claim không chắc chắn | Fail closed với API nhạy cảm |
| Nonce retention | TTL nhỏ hơn freshness acceptance window | Negative test phát hiện replay gap |
| Business duplicate | Cùng paymentId qua two valid new nonces | Idempotency ngăn duplicate effect |

### 19.3. Registry, caches và multi-node

| Test | Failure mode | Kỳ vọng |
| --- | --- | --- |
| Registry unavailable | Không có authoritative status | Không fail open |
| Secret manager unavailable | Không lấy được secret k4 | Không sử dụng k3/default |
| Cache stale ACTIVE | K3 đã REVOKED trung tâm | Node không accept ngoài guarantee |
| Cache refresh race | V9 ACTIVE đến sau V10 REVOKED | V9 không overwrite V10 |
| Negative cache | K4 mới provision nhưng cached missing | Đúng SLA/invalidation |
| Multi-node | A/B/C cache khác status | Đáp ứng deadline revoke đã công bố |
| Multi-region | Region A revoked, B partitioned | Strict policy deny tại B |
| Gateway bypass | Direct backend route | Không chấp nhận compromised k3 |
| HTTP/2 connection reuse | Request mới sau revoke trên same connection | Reject k3 |
| Rolling verifier deployment | Version cũ chưa hiểu REVOKED | Không được tiếp tục admit |
| Failover/rollback | Replica/promoted registry dùng snapshot cũ | Không hồi sinh revoked key |
| CI secret leak | Tạo k4 qua cùng đường rò chưa sửa | Test quy trình kiểm soát distribution |
| Production telemetry | Attempts dùng k3 sau revoke | Alert và audit có thời gian |

### 19.4. Điều tra và phục hồi

| Test / tabletop | Câu hỏi chứng minh |
| --- | --- |
| Incident runbook | Có người chịu trách nhiệm quyết định revoke và evidence handling? |
| Key inventory | Tìm được mọi service/audience/client dùng secret k3? |
| Containment | Có xác nhận effectiveReject trên tất cả admission paths? |
| New secret | Sinh độc lập bằng CSPRNG, phân phối qua kênh được xác thực? |
| Consumer rollout | K4 hoạt động và K3 vẫn bị reject? |
| Authorization | Stolen key không vượt principal/tenant scopes? |
| Business reconciliation | Xác định được side effects, idempotency records và operation states? |
| Logging | Không in shared secret, signature, raw sensitive body? |
| Notification | Có process theo chính sách nội bộ và nghĩa vụ áp dụng? |
| Closure | Root cause rò rỉ đã xử lý, các copies/backup được đánh giá? |

## 20. Runbook thực hành: một secret HMAC bị lộ

Runbook sau là **mẫu áp dụng trong môi trường được phép**, không thay quy trình incident response chính thức của tổ chức.

### Phase 1 — Triage

1. Ghi thời điểm nhận tin, nguồn báo cáo và credential ID.
2. Xác định loại bằng chứng: secret bytes lộ, khả năng dùng signing API, hay chỉ key ID.
3. Tra trusted credential registry và owner để biết principal, audience, tenant, scopes, active services/environments.
4. Đánh giá mức độ nhạy cảm của các actions có thể ký.
5. Quyết định confirmed/suspected và mức containment khẩn cấp.
6. Bảo toàn evidence cần thiết mà không nhân bản secret sang log/chat không an toàn.

### Phase 2 — Containment

1. Mark compromised key ID là REVOKED hoặc áp emergency deny theo approved control plane.
2. Đảm bảo deny thắng stale ACTIVE cache và không có fallback secret.
3. Nếu revocation chưa propagate đủ, tạm chặn key-level route/tenant hoặc các hành động nhạy cảm theo risk policy.
4. Kiểm tra gateway, backend direct access, secondary ingress và regions.
5. Giám sát requests dùng key cũ và đo **effective reject time**.
6. Không re-enable key bị lộ để giảm lỗi client.

### Phase 3 — Recovery

1. Sinh new key ID/new independent secret với CSPRNG.
2. Gắn correct principal/audience/algorithm và review least-privilege scopes.
3. Cấp key mới qua một authenticated secret delivery workflow.
4. Partner/client đổi secret ở các runtime và môi trường liên quan.
5. Dùng signed smoke tests: k4 hợp lệ có thể verify, k3 bị reject.
6. Xác minh timestamp/nonce, replay store và authorization vẫn hoạt động.
7. Nếu vẫn có service chấp nhận k3, coi containment chưa xong.

### Phase 4 — Investigation và remediation

1. Xây timeline exposure, suspicious use, revoke request/effect và k4 activation.
2. Audit secret manager, repository/CI, gateway logs, endpoint access và backups.
3. Đối chiếu accepted requests với business commits, operation IDs, audit trails.
4. Xác định side effects không được phép và phương án reconciliation/compensation theo policy.
5. Sửa nguyên nhân gốc, permissions, logging, secret distribution hoặc key sharing quá rộng.
6. Đánh giá có cần rotate **các credentials khác** nếu registry/KMS/CI bị compromise rộng hơn một key.
7. Chuẩn bị thông báo bên liên quan theo quy định áp dụng.

### Phase 5 — Closure

1. Hoàn thiện incident report: evidence, actions, blast radius, uncertainty và lessons learned.
2. Kiểm tra k3 không còn được các verifier chấp nhận sau failover/rollback.
3. Cập nhật runbook, tests, monitoring, owner và rotation schedule.
4. Làm tabletop drill định kỳ với **test secrets** thay vì secrets thật.
5. Ghi rõ những giới hạn còn lại, ví dụ revocation propagation delay chưa thể bằng zero.

## 21. Tình huống thực tế: API thanh toán và compromised key

Một đối tác gọi `payments-api` bằng HMAC key `partner-a-k3`. Key được lưu trong CI/CD của họ và vô tình xuất hiện trong một diagnostic artifact. Hệ thống nhận tín hiệu rằng một bên không được phép đã tải artifact đó.

### 21.1. Timeline minh họa

~~~text
T0  K3 ACTIVE, permission payments:create.
T1  CI artifact contains copied secret for k3.
T2  Unknown actor downloads artifact.
T3  Actor signs POST /v1/payments with timestamp NOW, nonce NEW.
T4  Gateway verifies HMAC successfully.
T5  Replay store sees nonce NEW and accepts.
T6  Payment handler checks tenant/account authorization.
T7  Incident response marks k3 REVOKED.
T8  Some backend nodes still cache k3 ACTIVE.
T9  Attacker sends another freshly signed request to stale node.
~~~

Tại `T3–T5`, HMAC và anti-replay có thể hoạt động **đúng thiết kế**. Nếu authorization cho phép principal thực hiện payment trong tenant A, request giả mạo có thể gây side effect trong scope đó. Không có cách mật mã nào để từ tag xác nhận client hợp pháp đã ký hay attacker.

Tại `T8–T9`, hệ thống bị thêm vấn đề **revocation propagation**. Mark k3 REVOKED trong registry chưa đủ nếu stale nodes vẫn accept.

### 21.2. Lớp giảm thiểu

- Emergency revoke k3 tại mọi verification path.
- Tạm giới hạn payment creation/risk checks trong lúc chờ propagation.
- Cấp k4 secret mới, phối hợp client thay CI secret, sửa artifact exposure.
- Dùng per-partner scoped key, giới hạn audience và tenant.
- Dựa vào authorization và transaction limits để giảm blast radius.
- Dùng business idempotency để ngăn **tác động trùng**, không coi nó chặn các operation khác nhau do attacker tạo.
- Điều tra payment IDs và durable transaction records trong time window nghi compromise.
- Kiểm tra old secret không nằm trong logs, copies, backups hoặc production config tiếp tục được sử dụng.

### 21.3. Một bug có vẻ vô hại nhưng nguy hiểm

Nếu verifier kiểm:

~~~java
// SAI cho compromised key:
if (signedTimestamp.isBefore(record.revokedAt())) {
    return acceptIfHmacMatches();
}
~~~

attacker có secret có thể ký một timestamp nằm **trước revokedAt** nhưng vẫn fresh theo cửa sổ. Điều kiện trên không xác định thời gian thực sự request được tạo. **Server-authoritative revocation** tại admission phải thắng signed client timestamp.

## 22. Những sai lầm phổ biến

### 22.1. “HMAC đúng chứng minh client hợp pháp gửi”

Không. Sau compromise, attacker dùng secret thật và tạo tag đúng như client.

### 22.2. “Có nonce và timestamp nên attacker không làm gì được”

Sai. Attacker có secret có thể tạo nonce mới và timestamp fresh.

### 22.3. “Dùng HMAC-SHA384 thay SHA256 thì secret bị lộ an toàn lại”

Không. Tăng độ mạnh primitive không thu hồi secret bị đánh cắp.

### 22.4. “Chỉ đổi key ID là đã rotate”

Nếu vẫn dùng secret bytes cũ, attacker vẫn có signing capability khi server chấp nhận chúng.

### 22.5. “Đã provision key mới nên được giữ key cũ RETIRING thêm một tháng”

Với **confirmed compromise**, overlap thường mở rộng cửa sổ abuse. Emergency revoke phải theo severity, không mặc định dùng lịch rotation thông thường.

### 22.6. “Có thể chấp nhận key revoked nếu client khai timestamp trước revoke”

Không đáng tin, vì client có stolen secret có thể ký bất kỳ timestamp còn nằm trong freshness window.

### 22.7. “Đã đổi status trong DB nghĩa là mọi node từ chối”

Stale caches, region replication và backend bypass có thể còn nhận key cũ.

### 22.8. “Rollback sang secret cũ nếu k4 deploy lỗi”

Một secret đã lộ không trở nên an toàn khi service gặp lỗi triển khai.

### 22.9. “Chỉ cần rotate client key, bỏ qua CI/log/secret-store permissions”

Root cause còn tồn tại có thể làm lộ ngay secret k4.

### 22.10. “Idempotency ngăn mọi request giả mạo”

Nó chỉ ngăn duplicate business operation theo operation ID; attacker có thể tạo IDs mới.

### 22.11. “Authorization không quan trọng vì key đã HMAC verify”

Principal A với stolen secret vẫn phải bị giới hạn theo tenant/resource/actions.

### 22.12. “Có thể chứng minh request nào do attacker gửi chỉ từ HMAC”

Không; shared secret đã lộ khiến MAC không thể phân biệt các bên có secret. Cần evidence độc lập.

### 22.13. “UNKNOWN registry status thì dùng cached ACTIVE vô hạn”

Đây là fail-open đối với revocation uncertainty. Cần consistency/TTL/fail-closed theo risk policy.

### 22.14. “Log secret để phân tích sự cố cho tiện”

Làm tăng phạm vi lộ và rủi ro tiếp diễn. Logs nên redacted, evidence cần access controls.

## 23. Bài tập thực hành

### Bài tập 1 — HMAC hợp lệ nhưng credential revoked

Tạo `CredentialRecord` k3 với một test secret và status `REVOKED`. Ký một canonical request bằng chính secret đó. Dùng `CompromiseAwareMacVerifierV1` để chứng minh expected HMAC có thể tính đúng nhưng policy vẫn phải reject k3. Giải thích vì sao điều này là tính chất bảo mật, không phải lỗi crypto.

### Bài tập 2 — Backdated signed timestamp

Đặt `serverNow=T`, `revokedAt=T-10s` và `signedTimestamp=T-20s` (vẫn trong freshness window 300 giây). Ký request bằng compromised secret. Viết test đảm bảo key bị từ chối **bất kể client timestamp nhỏ hơn revokedAt**. Sau đó thử đổi sang một timestamp mới `T`, kết quả vẫn reject.

### Bài tập 3 — Rotation có kế hoạch và emergency revoke

Mô tả hai workflows:

- K2 RETIRING khi rotation theo lịch, có `verifyUntil` và một key k3 ACTIVE.
- K3 bị compromise, phải chuyển REVOKED ngay theo policy và cấp k4 mới.

Viết bảng expected outcomes của requests ký bằng k2/k3/k4 trước và sau mốc sự kiện. Giải thích vì sao **không dùng overlap k3 sau compromise**.

### Bài tập 4 — Cache stale trong cluster

Dùng hai fake registries A/B để mô phỏng node A nhận REVOCATION, B còn record ACTIVE. Đầu tiên chứng minh B có thể trả `MAC_VALID` nếu chỉ đọc cached record; sau đó thiết kế consistency/invalidation/fail-closed mechanism và integration test xác nhận không nhận k3 ngoài guarantee.

### Bài tập 5 — Race stale refresh

Điều phối thread A fetch bản ACTIVE revision 9 nhưng chậm; sau đó thread B ghi REVOKED revision 10; cuối cùng A hoàn tất. Thực hiện một cache policy chỉ cho revision mới hơn hoặc bằng theo quy tắc monotonic an toàn, và test revision 9 **không thể** overwrite revocation revision 10.

### Bài tập 6 — Secret mới và scoped privilege

Tạo một test secret mới 32 byte bằng `SecureRandom`, phát ID k4 riêng cho `payments-api` với quyền tối thiểu. Xác nhận k4 hoạt động khi request đúng audience và bị từ chối khi chuyển sang `orders-api` hoặc resource của tenant khác.

### Bài tập 7 — Incident tabletop

Giả sử CI artifact chứa k3 secret bị public trong 30 phút. Đóng vai Incident Commander và xây timeline:

- Khi nào có thể bắt đầu exposure?
- Registry nào và verifier nodes nào đang nhận k3?
- Khi nào revoke được yêu cầu và khi nào mọi node thật sự reject?
- Những business operations nào phải đối chiếu?
- Làm sao giao k4 mà không lặp lại đường rò cũ?
- Các bằng chứng nào được bảo vệ, ai được truy cập?

### Bài tập 8 — Replay vs compromised secret

Dùng cùng signed request với nonce N gửi hai lần và kiểm replay store từ chối lần hai. Sau đó giả định attacker biết secret và gửi request mới nonce N2. Xác định vì sao replay gate không đủ, và bước nào phải chặn sau emergency revoke.

### Bài tập 9 — Gateway bypass

Hệ thống gateway đã chặn k3, nhưng backend vẫn có một route nội bộ mà client có thể truy cập. Tạo e2e test mô phỏng signed request k3 qua tất cả đường được cấu hình. Thảo luận network allowlist/mTLS/internal trusted-context và quy tắc không tin client-supplied identity headers.

### Bài tập 10 — Business impact

Một key `payments:create` bị compromise. Có 100 requests ký đúng trong exposure window, trong đó 20 failed authorization, 60 committed và 20 timeout không rõ trạng thái. Nêu bước điều tra đối chiếu với durable payment records/idempotency store, tránh kết luận từ access logs rằng toàn bộ 80 requests còn lại đều thành công hay đều giả mạo.

### Bài tập 11 — Secret manager outage

Giả lập registry trả k4 ACTIVE nhưng KMS không trả secret vì timeout. Verifier phải fail closed, không fallback về k3. Viết tests xác minh không gọi replay claim, không tạo principal và không gọi business handler.

### Bài tập 12 — Metrics và cảnh báo

Thiết kế một dashboard kiểm soát compromise chứa: active credential inventory, old-key attempts after revoke, effective revocation propagation time, stale-cache revision count, registry/KMS errors, HMAC failures, replay denials, unauthorized actions và business anomaly signals. Bảo đảm dashboard không chứa raw secret hoặc signed request tái sử dụng được.

## 24. Checklist phòng vệ và ứng phó Credential compromise

### 24.1. Trước khi xảy ra sự cố

- [ ] Mỗi client/trust boundary có credential riêng khi có thể; không dùng một shared secret cho nhiều unrelated tenants.
- [ ] Secret đủ entropy, sinh bằng CSPRNG hoặc secret manager/HSM.
- [ ] Không hardcode secret trong source, image, log, CI output hoặc sample docs.
- [ ] Secret manager RBAC/least privilege và audit accesses được cấu hình.
- [ ] Key inventory có owner, tenant, audience, scope, secretRef, status, expiry và verifier consumers.
- [ ] Key ID là selector exact match, không fallback secret/alias tùy tiện.
- [ ] Canonical request HMAC ký method, URI, relevant headers/body và credential metadata theo contract.
- [ ] Algorithm do server key policy quyết định; tag được so full-length bằng primitive phù hợp.
- [ ] Timestamp/nonce được ký và replay store có atomic claim với retention phù hợp.
- [ ] Authorization kiểm principal/action/resource/tenant độc lập với HMAC.
- [ ] Business idempotency theo operation ID với durable store cho side effects nhạy cảm.
- [ ] Có quy trình rotation thông thường, emergency revoke, secret delivery và contact owners.
- [ ] Revocation consistency/cache propagation có guarantee, tests và metrics rõ.
- [ ] Ingress/gateway/backend không cho bypass key verification.
- [ ] Logs/tracing redacted sensitive credentials.
- [ ] Có secret scanning, developer training và quy trình báo cáo lộ bí mật.

### 24.2. Khi phát hiện hoặc nghi compromise

- [ ] Xác định secret thực bị lộ hay chỉ key ID, đồng thời đánh giá khả năng ký từ HSM/service bị chiếm.
- [ ] Phân loại confirmed/suspected và severity dựa trên phạm vi quyền.
- [ ] Bảo toàn evidence theo incident response policy, không phát tán secret thêm.
- [ ] Revoke/disable key bị ảnh hưởng hoặc áp emergency deny; không chờ k4 hoạt động rồi mới chặn k3 nếu rủi ro cao.
- [ ] Không cho compromised key đi vào RETIRING overlap theo lịch thông thường.
- [ ] Không dùng signed client timestamp trước revokedAt làm cơ sở chấp nhận.
- [ ] Đo thời điểm mọi verifier/gateway/region thật sự reject key cũ.
- [ ] Chặn stale cache/old revision overwrite revocation.
- [ ] Khi key registry/revocation authority không tin cậy, fail closed theo security requirement.
- [ ] Kiểm direct backend path, HTTP/2 connections, secondary ingress và failover routes.
- [ ] Tăng giám sát old-key signing attempts và business anomalies.
- [ ] Áp các business safeguards tạm thời nếu risk profile yêu cầu.

### 24.3. Khi khôi phục

- [ ] Sinh independent new secret và key ID bằng approved process.
- [ ] Đánh giá lại least-privilege scopes/audience, không tự sao chép toàn quyền cũ.
- [ ] Truyền secret bằng kênh an toàn, có xác thực; không dùng logs/chat/email không bảo vệ.
- [ ] Client thay secret tại mọi runtime liên quan, kiểm backups/copies.
- [ ] Root cause làm lộ secret được xử lý; không đẩy k4 vào cùng đường rò.
- [ ] Test k4 ACTIVE hoạt động với đúng signed request, clock, nonce và routing.
- [ ] Test k3 vẫn REVOKED với fresh timestamp/new nonce/valid tag trên mọi verifier.
- [ ] Không rollback sang compromised secret dù gặp lỗi deploy.
- [ ] Đối chiếu business operations, idempotency states và downstream side effects.
- [ ] Ghi nhận audit timeline, thông báo theo policy và hoàn thiện incident report.
- [ ] Thêm regression/failure tests cho root cause đã phát hiện.

## 25. Câu hỏi tự kiểm tra

1. **Credential compromise là gì?** Secret/capability dùng credential bị lộ, sử dụng trái phép hoặc có nghi ngờ đáng tin dẫn tới mất khả năng tin cậy.
2. **Key ID bị biết có tương đương secret bị lộ không?** Không; ID thường chỉ là selector.
3. **HMAC-SHA256 có bị phá khi attacker dùng stolen secret ký request không?** Không; attacker đang dùng thuật toán hợp lệ với key đã bị lộ.
4. **Tại sao signed timestamp và nonce không chặn attacker có secret?** Attacker có thể tự tạo timestamp mới, nonce mới và MAC mới.
5. **Một HMAC tag sau compromise chứng minh request do ai gửi không?** Không; những bên có secret đều có thể tạo tag.
6. **Rotation thông thường khác emergency revoke như thế nào?** Rotation có thể có overlap; compromised key cần ngừng được chấp nhận khẩn cấp theo severity.
7. **Có nên giữ key bị lộ RETIRING trong một tháng vì sợ gián đoạn?** Không mặc định; overlap mở rộng thời gian attack.
8. **Đổi key ID nhưng giữ secret cũ có giải quyết compromise không?** Không.
9. **Tại sao key REVOKED vẫn phải reject khi MAC khớp?** Key policy không còn cho sử dụng secret đó.
10. **Vì sao không chấp nhận client signed timestamp trước revokedAt?** Attacker có stolen secret có thể tự ký lùi timestamp trong freshness window.
11. **Vì sao chỉ đổi status ở DB chưa đủ?** Cache/replication/gateway/backend có thể vẫn chấp nhận key cũ.
12. **Khi một node không thể kiểm chứng revocation state thì làm gì?** Fail closed hoặc theo một guarantee được phê duyệt; với strict policy không dùng stale ACTIVE vô hạn.
13. **Một key k3 REVOKED có thể re-enable để rollback không?** Không nên khi secret đã compromise; cấp ID/secret mới.
14. **Shared key giữa 20 clients gây rủi ro gì?** Blast radius lớn, khó cô lập và quy trách nhiệm.
15. **KMS/HSM có loại bỏ hoàn toàn nguy cơ compromise không?** Không; attacker có signing permission vẫn có thể lạm dụng.
16. **Tại sao cần kiểm tra secret distribution path?** Nếu đường cũ còn rò, k4 có thể bị lộ ngay.
17. **Business idempotency ngăn được attacker tạo operation ID mới không?** Không; chỉ ngăn tác động lặp cùng idempotency key theo policy.
18. **HMAC đúng có bỏ qua authorization được không?** Không; principal vẫn bị giới hạn theo action/resource/tenant.
19. **Làm sao xác định suspicious payments thật sự committed?** Đối chiếu durable business records và transaction/operation statuses, không chỉ HTTP logs.
20. **Có thể xác định chính xác ngày bắt đầu exposure từ first suspicious request không?** Không; đó chỉ là một mốc evidence, không chắc là thời điểm đầu.
21. **Vì sao không log raw Authorization/secret trong incident report?** Nó có thể làm lộ credential hoặc replayable request, tăng phạm vi sự cố.
22. **Điều kiện nào chứng minh containment kỹ thuật thành công?** Credential cũ bị từ chối ở mọi admission path theo consistency guarantee được công bố và đã kiểm chứng.
23. **Tại sao phải test trên nhiều nodes và sau failover?** Một node stale/snapshot cũ có thể tiếp tục nhận credential REVOKED.
24. **Một bài JUnit test chính sách key có thay e2e gateway test không?** Không; gateway, cache, routing và HTTP parsing là các ranh giới riêng.

## 26. Tài liệu tham khảo và hướng đọc thêm

- **RFC 2104 — HMAC: Keyed-Hashing for Message Authentication.** Nguyên lý MAC đối xứng và shared secret.
- **RFC 4231 — Identifiers and Test Vectors for HMAC-SHA-224/256/384/512.** Known-answer tests cho HMAC primitive.
- **RFC 9110 — HTTP Semantics.** Header authentication, method, request semantics.
- **RFC 9112 / RFC 9113 — HTTP/1.1 / HTTP/2.** Header parsing, message framing và gateway conversions.
- **NIST SP 800-57 Part 1 — Recommendation for Key Management.** Nguyên tắc quản lý key lifecycle và xử lý compromise.
- **NIST SP 800-61 — Computer Security Incident Handling guidance.** Khung tư duy phát hiện, phân tích, containment, eradication và recovery; chọn phiên bản phù hợp chính sách tổ chức.
- **OWASP Secrets Management Cheat Sheet.** Cấp phát, lưu, phân quyền, rotation và audit bí mật.
- **OWASP API Security guidance.** Authentication, authorization và hạn chế quyền API.
- **Java SE 17 API — `SecureRandom`, `Clock`, `Instant`, `javax.crypto.Mac`, `MessageDigest.isEqual`.** Các primitive phục vụ key lifecycle và xác minh HMAC.
- **JUnit 5 User Guide.** Unit/boundary/integration test patterns.

**Kết luận:** Khi **shared secret HMAC bị compromise**, một chữ ký hoàn toàn hợp lệ có thể do attacker tạo. Timestamp và nonce bảo vệ khỏi replay nguyên request, **không bảo vệ khỏi việc ký request mới bằng key đã lộ**. Phản ứng đúng là xác định scope, **thu hồi credential cũ và thực thi deny tại mọi verifier**, cấp secret/key ID mới qua kênh an toàn, xử lý nguồn rò, điều tra tác động đã xảy ra và giữ authorization/idempotency độc lập. Kiểm thử phải chứng minh một key `REVOKED` **không bao giờ được nhận chỉ vì MAC đúng**, kể cả khi request tự khai timestamp trước lúc revoke và khi hệ thống đang scale, failover hoặc có cache chưa đồng bộ.





