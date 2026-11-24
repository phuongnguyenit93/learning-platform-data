# API key cho tích hợp — Case study thiết kế xác thực giữa hai hệ thống

## 1. Bối cảnh case study

Một nền tảng SaaS quản lý đơn hàng cần cho phép hệ thống ERP của khách hàng gửi đơn hàng mới và truy vấn trạng thái giao hàng qua REST API. Hai hệ thống không có người dùng tương tác trực tiếp ở mỗi request; ERP cần một credential dành cho workload để xác thực với API của SaaS.

Nhóm phát triển ban đầu định tạo một chuỗi API key cố định cho mỗi khách hàng, lưu trong cấu hình ứng dụng và kiểm tra bằng cách so sánh với một giá trị trong database. Sau vài tháng, số lượng tích hợp tăng, một key được dùng chung cho nhiều môi trường, log gateway ghi lại header xác thực và nhóm vận hành không thể biết key nào thuộc workload nào. Khi một nhân viên đối tác rời công ty, không có cách thu hồi quyền của riêng họ mà không làm gián đoạn các tích hợp còn lại.

Case study này thiết kế lại cơ chế API key theo các nguyên tắc của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**: hiểu credential, mật khẩu, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và khôi phục tài khoản; mô hình hóa ranh giới tin cậy; phòng chống phishing, replay và lạm dụng đăng nhập. Trọng tâm là xác thực workload-to-workload bằng API key, giới hạn quyền, quản lý vòng đời và ứng phó khi secret bị lộ.

## 2. Mục tiêu và yêu cầu nghiệp vụ

Nền tảng cần cho phép khách hàng tạo tích hợp mà không phải dùng tài khoản nhân viên hoặc mật khẩu cá nhân. Mỗi tích hợp cần có danh tính riêng, phạm vi quyền rõ ràng và khả năng thu hồi độc lập.

Yêu cầu:

- Mỗi API key thuộc một tenant, một integration và một môi trường.
- Một key chỉ có quyền cần thiết, ví dụ tạo đơn hàng và đọc trạng thái đơn hàng.
- Secret chỉ hiển thị một lần khi cấp; server không lưu secret bản rõ.
- Có thể đặt ngày hết hạn, rotate, suspend và revoke.
- Có thể xác định key nào gọi API, vào thời điểm nào và kết quả ra sao.
- Key bị lộ không được dùng để truy cập tenant khác.
- Hệ thống hỗ trợ nhiều key cùng lúc trong giai đoạn rotation ngắn.
- Request được bảo vệ bằng TLS và không để secret lọt vào URL, log hoặc telemetry.
- Có rate limit, quota, audit trail và cảnh báo hoạt động bất thường.
- Có quy trình khôi phục tích hợp khi key hết hạn, bị thu hồi hoặc bị lộ.

Phiên bản đầu không yêu cầu ký từng request bằng HMAC hoặc mutual TLS. Tuy nhiên, thiết kế cần chỉ ra giới hạn của bearer API key và đường nâng cấp cho tích hợp có rủi ro cao.

## 3. API key là gì và nó chứng minh điều gì?

API key là một credential thường được trình bày như một chuỗi bí mật mà client gửi cùng request để server nhận diện và xác thực một integration hoặc workload. Trong mô hình bearer, bên nào nắm được secret đều có thể sử dụng nó trong phạm vi key được cấp.

API key có thể giúp server trả lời:

- Credential nào đang được trình bày?
- Credential đó thuộc tenant và integration nào?
- Credential còn active, chưa hết hạn và chưa bị revoke không?
- Credential được phép gọi những API/scope nào?
- Request có vượt quota hoặc rate limit không?

API key tự nó không chứng minh người vận hành đang là ai, thiết bị nào đang gửi request hoặc người dùng cuối đã xác thực bằng MFA. Nó cũng không tự ràng buộc request với một máy chủ cụ thể. Nếu secret bị sao chép, attacker có thể sử dụng nó như workload hợp lệ cho tới khi bị phát hiện và thu hồi.

Vì vậy, cần phân biệt:

| Thành phần | Vai trò |
| --- | --- |
| API key | Credential để xác thực integration/workload. |
| Key ID/prefix | Giúp tìm record và quản lý key; không phải secret. |
| Tenant/integration identity | Danh tính mà key đại diện. |
| Scope/permission | Quyền mà key được phép thực hiện. |
| TLS | Bảo vệ kênh truyền và xác minh server endpoint. |
| Rate limit/quota | Giới hạn mức sử dụng và tác động khi bị lạm dụng. |
| Audit trail | Ghi lại việc cấp, dùng, rotate và revoke key. |

Xác thực thành công không có nghĩa request được phép thực hiện mọi hành động. Sau khi xác thực key, API vẫn phải kiểm tra scope, tenant, resource ownership và trạng thái nghiệp vụ.

## 4. Phân biệt API key với password, access token và HMAC signing

| Cơ chế | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| Password | Bí mật do người dùng chọn, thường cần password hashing chậm và quy trình đăng nhập tương tác. | Xác thực người dùng; không dùng chung làm secret cho nhiều workload. |
| API key | Secret ngẫu nhiên, thường đại diện cho integration và được gửi trong mỗi request. | Tích hợp server-to-server đơn giản, có scope và vòng đời quản lý rõ. |
| OAuth access token | Token có issuer, audience, expiry và scope; thường được cấp từ authorization server. | Khi cần delegation, consent, token ngắn hạn hoặc nhiều resource server. |
| HMAC request signing | Client ký request bằng shared secret; server kiểm tra chữ ký và các thành phần request đã ký. | Khi cần integrity, chống một số dạng replay và xác minh request gắn với nội dung cụ thể. |
| mTLS/client certificate | Client chứng minh sở hữu private key trong TLS handshake. | Workload có PKI, yêu cầu danh tính máy và bảo vệ kênh mạnh hơn. |

API key có thể được dùng để đổi lấy access token, nhưng hai khái niệm không giống nhau. Nếu API key được gửi trực tiếp cho mọi service trong thời gian dài, phạm vi tác động khi lộ có thể lớn hơn token ngắn hạn.

HMAC signing cũng không tự động an toàn nếu client và server không thống nhất canonicalization, timestamp, nonce, key rotation và replay handling. mTLS cũng cần quản lý certificate/private key, trust chain và revocation.

## 5. Kiến trúc đề xuất

Thiết kế dùng một API credential service làm nguồn authoritative. API gateway hoặc resource API xác minh key thông qua credential verifier/cache, sau đó áp dụng authorization theo tenant và scope.

~~~mermaid
flowchart LR
    ERP["Customer ERP workload"]
    VAULT["Customer secret manager"]
    EDGE["TLS API gateway"]
    VER["API key verifier"]
    REG[("Credential registry")]
    CACHE[("Bounded verification cache")]
    AUTHZ["Tenant / scope authorization"]
    API["Order API"]
    AUDIT[("Audit and security events")]
    ERP -->|"Read secret"| VAULT
    ERP -->|"HTTPS + API key"| EDGE
    EDGE --> VER
    VER <--> CACHE
    VER --> REG
    VER --> AUTHZ
    AUTHZ --> API
    VER --> AUDIT
    AUTHZ --> AUDIT
~~~

Customer ERP giữ secret trong secret manager của khách hàng. API gateway nhận request qua TLS, loại bỏ header identity do client tự khai, rồi chuyển credential tới verifier. Verifier tìm key record, kiểm tra trạng thái và xác minh secret. Authorization layer ràng buộc tenant, scope và resource. Audit service nhận event đã được chuẩn hóa.

Credential registry lưu metadata và verifier của secret, không lưu secret bản rõ. Cache có TTL và invalidation để giảm tải nhưng phải giới hạn cửa sổ stale khi revoke. Các resource API chỉ nhận identity context đã được gateway xác minh qua kênh nội bộ đáng tin cậy.

## 6. Mô hình dữ liệu và định danh key

Mỗi API key có thể được mô hình hóa bằng hai phần:

- **Key ID:** định danh công khai hoặc prefix để tìm bản ghi.
- **Secret:** phần bí mật có entropy cao, chỉ được hiển thị một lần.

Ví dụ định dạng minh họa:

~~~text
ak_live_7F3K9D2M.<random-secret>
~~~

Prefix có thể cho biết loại key hoặc môi trường, nhưng không được chứa dữ liệu nhạy cảm. Key ID giúp tra cứu nhanh; secret mới là phần phải được bảo vệ như bearer credential.

Record metadata có thể gồm:

| Trường | Mục đích |
| --- | --- |
| key_id | Định danh duy nhất, không bí mật. |
| tenant_id | Tenant sở hữu integration. |
| integration_id | Hệ thống tích hợp cụ thể. |
| environment | Test, staging hoặc production. |
| secret_verifier | Giá trị xác minh secret đã được bảo vệ. |
| scopes | Danh sách quyền cho phép. |
| status | Pending, active, suspended, revoked hoặc expired. |
| created_at / expires_at | Vòng đời key. |
| last_used_at | Thời điểm sử dụng gần nhất nếu được cập nhật đáng tin. |
| created_by / approved_by | Actor và approver khi cấp key. |
| rotation_group | Liên kết key cũ và mới trong một lần rotation. |
| version | Version để kiểm soát update và cache invalidation. |

Không dùng email hoặc tên nhân viên làm key ID. Key đại diện cho integration; người quản lý integration là metadata ownership và có thể thay đổi mà không cần đổi danh tính workload.

## 7. Sinh secret đủ entropy

Secret phải được sinh bằng cryptographically secure random number generator (CSPRNG), không dựa vào timestamp, counter, UUID không phù hợp hoặc chuỗi do người dùng chọn.

Một lựa chọn phổ biến là 32 byte ngẫu nhiên, tương đương 256 bit entropy trước khi mã hóa biểu diễn. Có thể encode bằng Base64url hoặc encoding an toàn khác. Độ dài và định dạng cần được kiểm thử với header size, proxy và client library.

Nguyên tắc:

- Secret đủ dài và ngẫu nhiên.
- Mỗi key có secret độc lập, không dùng chung giữa tenant hoặc môi trường.
- Không tái sử dụng secret sau revoke.
- Không đưa secret vào log khi tạo key.
- Không dùng PRNG thông thường hoặc hash timestamp để sinh key.
- Sinh secret phía server trong thành phần được tin cậy.

Key ID có thể ngẫu nhiên riêng hoặc dùng định danh không thể đoán. Tuy nhiên, bảo mật không dựa vào việc giấu Key ID; server luôn cần xác minh secret.

## 8. Cấp phát và hiển thị key một lần

Quy trình tạo key:

1. Người quản trị tenant đã xác thực mở trang quản lý integration.
2. Hệ thống yêu cầu step-up nếu thao tác cấp credential có rủi ro cao.
3. Người dùng chọn environment, scope, expiry và integration owner.
4. Policy kiểm tra quyền cấp key và giới hạn số key.
5. Server sinh key ID và secret bằng CSPRNG.
6. Server lưu metadata cùng verifier của secret.
7. Secret được trả về đúng một lần qua kết nối TLS.
8. Giao diện yêu cầu người dùng lưu vào secret manager và xác nhận đã lưu.
9. Audit trail ghi actor, scope, key reference và kết quả, không ghi secret.

Không có nút “hiển thị lại secret” sau khi đóng trang. Nếu người dùng làm mất secret, họ phải tạo key mới và revoke key cũ khi đã chuyển consumer.

### Vì sao chỉ hiển thị một lần?

Nếu server có thể hiển thị lại secret, server phải giữ bản có thể giải mã hoặc một bản sao bản rõ. Điều đó làm tăng hậu quả khi database, backup hoặc quyền quản trị bị chiếm. Với secret ngẫu nhiên đủ entropy, lưu verifier phù hợp thường tốt hơn lưu secret có thể giải mã.

## 9. Lưu trữ verifier an toàn

Server cần xác minh secret nhưng không cần biết lại secret bản rõ sau khi tạo. Một thiết kế tham khảo:

1. Tách key ID và secret từ credential trình bày.
2. Dùng key ID để tìm record.
3. Tính verifier từ secret bằng HMAC-SHA-256 với pepper/key riêng trong KMS, hoặc một cơ chế keyed verifier được thiết kế và review phù hợp.
4. So sánh verifier theo cách constant-time.
5. Không log input hoặc verifier.

Vì secret được sinh ngẫu nhiên với entropy cao, password hashing chậm như Argon2id thường không phải lựa chọn bắt buộc cho API key theo cùng lý do như password người dùng. Tuy nhiên, lưu verifier bằng HMAC cần bảo vệ pepper/key trong KMS/HSM và giới hạn quyền sử dụng. Nếu dùng hash không keyed, cần đánh giá khả năng database-only compromise và entropy thực tế.

Không lưu secret bản rõ trong database, backup, analytics, support ticket hoặc application config. Không dùng mã hóa có thể giải mã nếu không có nhu cầu nghiệp vụ thực sự và threat model được phê duyệt.

## 10. Gửi API key trong request

Client gửi key qua HTTPS trong header chuyên dụng. Ví dụ:

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer ak_live_7F3K9D2M.random-secret-value
Content-Type: application/json
Idempotency-Key: order-2026-000184

{
  "external_order_id": "ERP-000184",
  "items": [
    {"sku": "SKU-42", "quantity": 3}
  ]
}
~~~

Ví dụ trên chỉ minh họa định dạng. API thực tế cần dùng hostname chính thức, TLS hợp lệ và secret do server cấp.

Không đặt API key trong:

- Query string hoặc URL path.
- HTML form, browser local storage hoặc mobile app binary.
- Git repository, source code hoặc container image.
- Error message, analytics event hoặc tracing baggage.
- Screenshot, email, chat hoặc tài liệu hỗ trợ.

Query string thường bị lưu trong access log, browser history, proxy và referrer. Header cũng có thể bị log nếu cấu hình sai; cần redact Authorization ở gateway, APM và log collector.

## 11. Luồng xác thực request

Một request hợp lệ đi qua các bước:

~~~mermaid
sequenceDiagram
    participant C as ERP client
    participant G as API gateway
    participant V as Key verifier
    participant R as Credential registry
    participant Z as Authorization
    participant A as Order API
    C->>G: HTTPS request + key ID/secret
    G->>V: Credential material over trusted channel
    V->>R: Lookup key ID
    R-->>V: Status, verifier, tenant, scopes
    V->>V: Verify secret and expiry
    V-->>G: Authenticated integration context
    G->>Z: Check tenant, scope, resource
    Z-->>G: Allow / deny
    G->>A: Forward verified context
    A-->>C: Response
~~~

Thứ tự quan trọng:

1. Kiểm tra TLS và request size.
2. Parse credential theo format được hỗ trợ.
3. Tra cứu key ID và kiểm tra record tồn tại.
4. Xác minh secret bằng constant-time comparison.
5. Kiểm tra status active, thời hạn và environment.
6. Tạo authenticated integration context từ record server-side.
7. Kiểm tra tenant, scope, resource ownership và policy.
8. Ghi audit metadata và thực thi request.

Không tin tenant ID, role hoặc scope do client gửi trong body/header. Các giá trị này phải lấy từ record đã xác minh và policy authoritative.

## 12. Authentication và authorization phải tách biệt

Sau khi key được xác minh, server biết request đại diện cho integration nào. Nó vẫn phải kiểm tra:

- Key có scope phù hợp với endpoint/action không?
- Resource có thuộc tenant mà key đại diện không?
- Integration có được phép truy cập dữ liệu đó không?
- Environment có khớp không?
- Account/tenant có đang active không?
- Quota, rate limit và business constraints có được đáp ứng không?

Ví dụ, key có scope orders:write chỉ được tạo đơn hàng. Nó không được đọc thông tin thanh toán, thay đổi tenant owner hoặc cấp API key mới.

Áp dụng deny-by-default: scope không có trong allowlist thì từ chối. Không coi một key hợp lệ là quyền quản trị toàn hệ thống.

## 13. Scope, tenant isolation và environment separation

Scope nên biểu diễn quyền nhỏ và rõ:

| Scope ví dụ | Quyền |
| --- | --- |
| orders:read | Đọc trạng thái đơn hàng. |
| orders:write | Tạo hoặc cập nhật đơn hàng theo policy. |
| shipments:read | Đọc trạng thái vận chuyển. |
| webhooks:manage | Quản lý endpoint webhook nếu được phép. |

Không tạo scope chung chung như admin nếu integration chỉ cần một số thao tác. Tách key theo environment: test key không được truy cập production, production key không được dùng trong staging.

Mọi truy vấn dữ liệu cần gắn tenant từ authenticated context. Không lấy tenant từ body rồi tin trực tiếp. Nếu request chỉ định resource ID, server phải xác minh resource thuộc tenant của key để ngăn IDOR/cross-tenant access.

## 14. Rate limit, quota và chống lạm dụng

API key bị lộ có thể được sử dụng tự động với tốc độ cao. Cần nhiều lớp giới hạn:

- Theo key ID.
- Theo tenant/integration.
- Theo endpoint và operation.
- Theo IP/network signal khi phù hợp.
- Theo toàn hệ thống để bảo vệ capacity.
- Theo quota nghiệp vụ như số đơn hàng hoặc số lần export.

Trả status phù hợp và thông tin retry có giới hạn; không tiết lộ nội bộ về key record. Rate limit phải phân tán và nhất quán đủ mức, tránh mỗi gateway node áp dụng quota riêng khiến tổng mức vượt quá dự kiến.

Không chỉ dựa vào IP allowlist. Đối tác có thể dùng NAT, cloud egress thay đổi hoặc nhiều region. IP restriction có thể là lớp bổ sung, nhưng không thay thế secret protection, scope và rotation.

## 15. Chống replay và giới hạn của bearer API key

TLS bảo vệ dữ liệu trên đường truyền tới endpoint đã xác minh, nhưng không ngăn attacker sử dụng lại secret đã lấy được từ log, endpoint, memory dump hoặc máy khách bị compromise. Với bearer key, request hợp lệ có thể bị phát lại nếu attacker có credential và request data.

Các biện pháp giảm rủi ro:

- Dùng HTTPS bắt buộc và HSTS ở browser-facing endpoint khi phù hợp.
- Không ghi Authorization header.
- Dùng idempotency key cho thao tác tạo/cập nhật có thể retry.
- Giới hạn key scope và expiry.
- Rate limit, anomaly detection và revoke nhanh.
- Với giao dịch nhạy cảm, ràng buộc challenge hoặc chữ ký với nội dung request.

Idempotency key ngăn một số tác động lặp của thao tác nghiệp vụ nhưng không xác thực client. Nếu threat model cần request integrity và replay resistance mạnh hơn, cân nhắc HMAC signing với timestamp/nonce hoặc mTLS.

## 16. Nâng cấp: HMAC request signing

Trong mô hình HMAC, client và server dùng shared secret để tính chữ ký trên canonical request. Server tính lại và so sánh chữ ký, từ đó xác minh request gắn với các thành phần đã ký.

Một canonical message có thể bao gồm:

~~~text
HTTP_METHOD
CANONICAL_PATH
CANONICAL_QUERY
CONTENT_HASH
TIMESTAMP
NONCE
KEY_ID
~~~

Client gửi key ID, timestamp, nonce và signature. Server kiểm tra:

- Key còn active và đúng scope.
- Timestamp nằm trong cửa sổ cho phép.
- Nonce chưa từng được dùng trong phạm vi key/window.
- Canonicalization giống hệt giữa client và server.
- Content hash và signature hợp lệ.
- Request được xử lý trong tenant/audience phù hợp.

HMAC không tự giải quyết mọi replay nếu server không lưu nonce hoặc không ràng buộc timestamp. Nó cũng tạo yêu cầu quản lý shared secret và canonicalization phức tạp hơn. Chỉ nâng cấp khi rủi ro và yêu cầu tích hợp xứng đáng với chi phí vận hành.

## 17. Nâng cấp: mutual TLS và workload identity

mTLS cho phép client trình bày certificate và chứng minh sở hữu private key trong TLS handshake. Server xác minh certificate chain, identity mapping, expiry và revocation theo trust policy.

Ưu điểm:

- Có thể ràng buộc kết nối với workload certificate.
- Private key có thể được bảo vệ trong HSM/TPM hoặc workload platform.
- Không phải gửi một bearer secret trong từng HTTP request.
- Có thể kết hợp với API key hoặc authorization layer để phân biệt integration/scope.

Đổi lại, cần quản lý CA, issuance, renewal, trust bundle, certificate rotation, revocation và private key lifecycle. Certificate không tự quyết định quyền trên API; authorization vẫn cần tenant/scope policy.

## 18. Rotation không gây gián đoạn

Key cần được rotate định kỳ theo policy hoặc ngay khi nghi ngờ bị lộ. Một quy trình không gây downtime:

1. Owner tạo key mới với scope và expiry tương đương hoặc hẹp hơn.
2. Server lưu key mới ở trạng thái active hoặc pending activation theo thiết kế.
3. Secret hiển thị một lần và được lưu vào secret manager phía client.
4. Consumer chuyển sang key mới.
5. Monitoring xác nhận request hợp lệ đã dùng key mới.
6. Owner revoke key cũ sau khi xác nhận không còn consumer cần nó.
7. Cache invalidation lan truyền và verifier từ chối key cũ.
8. Audit ghi liên kết rotation, actor, thời điểm và kết quả.

Overlap chỉ nên kéo dài trong một cửa sổ ngắn, có deadline và monitoring. Không để hai key cùng active vô thời hạn vì làm tăng số secret có thể bị lộ.

Nếu key cũ đang bị attacker sử dụng tích cực, ưu tiên revoke ngay và chấp nhận gián đoạn có kiểm soát thay vì giữ overlap để tiện migration.

## 19. Expiry, suspend và revoke

Các trạng thái nên có semantics rõ:

| Trạng thái | Ý nghĩa | Request mới |
| --- | --- | --- |
| pending | Chưa được kích hoạt hoặc đang chờ approval. | Từ chối. |
| active | Được phép sử dụng trong scope và thời hạn. | Xác minh secret rồi authorize. |
| suspended | Tạm dừng do risk hoặc quản trị. | Từ chối. |
| revoked | Thu hồi không thể dùng lại. | Từ chối. |
| expired | Quá thời hạn. | Từ chối. |

Revoke phải có hiệu lực tại mọi verifier trong propagation SLA. Nếu verifier cache record active, cần TTL, event invalidation hoặc revalidation. Không cho phép cache stale làm sống lại key đã revoke.

Suspension có thể được dùng khi cần điều tra và có khả năng khôi phục; revoked thường là trạng thái cuối. Không chuyển revoked trở lại active bằng cách đổi status thủ công; cấp key mới nếu cần tiếp tục tích hợp.

## 20. Phát hiện key bị lộ hoặc bị lạm dụng

Các tín hiệu:

- Request từ nguồn/region chưa từng thấy hoặc thay đổi đột ngột.
- Tăng bất thường về volume, error rate hoặc endpoint được gọi.
- Scope được sử dụng theo mẫu khác với baseline.
- Key hoạt động ngoài giờ hoặc sau khi integration owner báo ngừng.
- Nhiều lần xác thực thất bại với cùng key ID.
- Key bị phát hiện trong repository, log, artifact hoặc paste site.
- Một key được dùng đồng thời từ nhiều môi trường không phù hợp.

Không coi một IP mới là bằng chứng compromise duy nhất. Kết hợp key usage, tenant, endpoint, volume, thời gian và thông tin từ owner.

Alert nên chứa key ID, integration, tenant reference, event time, signal và hướng xử lý; không chứa secret. Dashboard phải mask identifier khi người xem không cần biết đầy đủ.

## 21. Incident response khi API key bị lộ

Quy trình xử lý:

1. Tạo incident và xác định key ID, owner, tenant, scope, environment.
2. Bảo toàn metadata, audit event và nguồn phát hiện; không sao chép secret vào ticket.
3. Đánh giá key có quyền gì và có bằng chứng sử dụng trái phép không.
4. Nếu risk cao, suspend/revoke tại credential authority.
5. Kiểm tra propagation tới gateway, cache và downstream verifier.
6. Điều tra request history, dữ liệu đã đọc/sửa và token/grant phát sinh.
7. Cấp key mới sau khi xác minh owner và cập nhật secret manager.
8. Xác nhận consumer hợp lệ đã chuyển; revoke key cũ nếu chưa làm.
9. Quét Git history, CI logs, artifacts, container images, APM và backup.
10. Theo dõi việc thử sử dụng key cũ và hoạt động sau containment.

Xóa key khỏi source không làm secret đã lộ mất hiệu lực. Cần revoke/rotate và xác minh server từ chối key cũ.

## 22. Audit trail và khả năng truy vết

Ghi nhận các sự kiện:

- API key created, approved, activated.
- Secret displayed once (chỉ ghi event, không ghi secret).
- Key used: key ID, integration, tenant, endpoint class, outcome.
- Scope denied, rate limited hoặc quota exceeded.
- Key rotated, suspended, revoked hoặc expired.
- Owner/integration changed.
- Secret manager retrieval nếu có tích hợp và policy cho phép.
- Admin access, export và thay đổi policy.

Audit record cần actor, subject, target reference, timestamp, outcome, reason code và correlation ID. Không ghi raw Authorization header, secret verifier, request body nhạy cảm hoặc token phát sinh.

Log cần được bảo vệ integrity, phân quyền đọc, retention và export. Nếu một key bị nghi lộ, điều tra viên cần nối các request với session, grant hoặc credential khác được tạo sau đó.

## 23. Quy trình vận hành cho khách hàng tích hợp

Trang quản lý integration nên cung cấp:

- Danh sách key theo môi trường, trạng thái và ngày hết hạn.
- Key ID/prefix, không hiển thị secret đã tạo.
- Scope, owner, ngày tạo và last-used metadata.
- Tạo key mới với xác nhận purpose và expiry.
- Hướng dẫn lưu vào secret manager.
- Rotation workflow và trạng thái consumer migration.
- Suspend/revoke với xác nhận hậu quả.
- Audit history và thông báo hoạt động bất thường.

Không hiển thị secret trong bảng danh sách hoặc email. Không cho support agent xem secret. Khi khách hàng làm mất key, tạo key mới thay vì khôi phục key cũ.

## 24. Mã giả: cấp phát và xác minh API key

Mã giả dưới đây thể hiện nguyên tắc, không phải thư viện triển khai hoàn chỉnh:

~~~text
createApiKey(actor, tenant, integration, scopes, expiry):
    require actorCanManageIntegration(actor, integration)
    require scopesAreSubsetOfAllowedScopes(tenant, scopes)
    require expiryWithinPolicy(expiry)
    require stepUpIfRequired(actor, "create_api_key")

    keyId = generateUniqueKeyId()
    secret = CSPRNG(32 bytes)
    verifier = HMAC_SHA256(kmsPepperVersion, secret)

    atomically:
        saveKeyRecord(
            keyId = keyId,
            tenant = tenant.id,
            integration = integration.id,
            scopes = scopes,
            verifier = verifier,
            status = "active",
            expiresAt = expiry
        )
        appendAuditEvent("api_key.created", keyId, actor)

    return showSecretOnce(keyId, secret)

verifyApiKey(presentedCredential, request):
    keyId, secret = parseCredential(presentedCredential)
    record = lookupKeyRecord(keyId)
    require record exists
    require record.status == "active"
    require trustedServerTime() < record.expiresAt

    candidate = HMAC_SHA256(kmsPepperVersion(record), secret)
    require constantTimeEqual(candidate, record.verifier)

    context = authenticatedIntegrationContext(
        tenant = record.tenant,
        integration = record.integration,
        scopes = record.scopes,
        keyId = record.keyId
    )

    require authorize(context, request.action, request.resource)
    enforceRateLimit(context, request)
    appendAuditMetadata(context, request, "allowed")
    return context
~~~

Trong triển khai thật:

- Secret phải được sinh bằng CSPRNG và không xuất hiện trong log.
- Verifier/pepper cần versioning và quyền KMS tối thiểu.
- So sánh secret constant-time.
- Tra cứu record và authorization phải chống cross-tenant access.
- Cache cần TTL/invalidation và kiểm thử revoke propagation.
- Cấp key, ghi audit và lưu record phải có transaction/idempotency phù hợp.
- Error response không được tiết lộ key ID tồn tại hay không theo cách hỗ trợ enumeration.

## 25. Tình huống thực tế: key bị lộ trong CI log

Một khách hàng tích hợp ERP với API đơn hàng. Pipeline CI chạy script kiểm thử và vô tình in toàn bộ environment variables khi một bước thất bại. API key production xuất hiện trong log build. Log có quyền đọc cho nhiều developer và nhà thầu.

### Phân tích rủi ro

- Secret đã vượt khỏi secret manager và xuất hiện trong log có quyền rộng.
- Key có scope orders:read và orders:write.
- Build log có thể được tải xuống hoặc lưu trong artifact retention.
- Chưa có bằng chứng attacker dùng key, nhưng không thể chứng minh không ai đã sao chép.

### Hành động

1. Ghi nhận build ID, log reference, thời điểm và key ID mà không sao chép secret.
2. Owner xác định consumer và tạo key mới với scope tương đương.
3. Cập nhật CI secret store và triển khai consumer.
4. Xác minh request production dùng key mới.
5. Revoke key cũ và xác nhận gateway từ chối.
6. Rà soát API audit log từ thời điểm đầu tiên log có thể bị đọc.
7. Giới hạn quyền truy cập build log, xử lý bản export và điều chỉnh retention theo policy.
8. Tắt lệnh dump environment, thêm masking và secret scanning.
9. Kiểm tra repository, cache, artifact và backup liên quan.
10. Theo dõi mọi request dùng key cũ sau revoke.

### Bài học

Secret manager chỉ bảo vệ secret tại nơi lưu trữ. Pipeline, shell tracing, debug output, crash dump và log cũng là ranh giới tin cậy. Cần kiểm soát nơi secret được đưa vào memory/process và nơi có thể vô tình ghi nó ra.

## 26. Kiểm thử và tiêu chí chấp nhận

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Key hợp lệ, scope phù hợp | Request được xác thực và authorize đúng tenant. |
| Secret sai | Từ chối với response chung, không lộ trạng thái record. |
| Key ID không tồn tại | Từ chối tương tự secret sai; không hỗ trợ enumeration. |
| Key pending/suspended/revoked | Từ chối. |
| Key hết hạn | Từ chối theo trusted server time. |
| Key test gọi production | Từ chối do environment mismatch. |
| Key tenant A truy cập resource tenant B | Từ chối ở authorization/resource ownership check. |
| Scope không đủ | Từ chối dù authentication thành công. |
| Authorization header bị log | Test phải phát hiện redaction failure; release không đạt. |
| Key đặt trong query string | Request bị từ chối hoặc cảnh báo theo policy; không ghi URL chứa secret. |
| Rotation overlap | Key mới hoạt động, key cũ chỉ hoạt động trong cửa sổ đã định. |
| Revoke trong lúc cache còn active | Verifier từ chối trong propagation SLA. |
| Request burst | Rate limit/quota áp dụng theo key và tenant. |
| Replay cùng idempotency key | Không tạo side effect trùng ngoài semantics đã công bố. |
| Concurrent create/rotate | Không sinh record mồ côi hoặc key active ngoài ý muốn. |
| KMS/pepper service lỗi | Không bỏ qua verifier; lỗi được xử lý an toàn. |
| Secret trong CI log | Scanner phát hiện; key được rotate và log access được xử lý. |
| Key bị dùng từ nguồn lạ | Alert có key reference, không chứa secret. |
| Owner rời tổ chức | Owner được thay đổi; credential được review, rotate hoặc revoke theo policy. |
| Backup restore | Key đã revoke không trở lại active do snapshot cũ. |

### Kiểm thử vận hành

- Đo latency xác minh key ở P50/P95/P99.
- Kiểm tra verifier capacity, cache hit ratio và KMS quota.
- Diễn tập rotation khi consumer có phiên bản cũ.
- Diễn tập revoke và đo propagation qua mọi region.
- Kiểm tra secret redaction trong gateway, APM, trace, CI và SIEM.
- Kiểm tra audit trail cho create/use/deny/rotate/revoke.
- Thử restore metadata và xác minh tombstone/revocation state.

## 27. Checklist thiết kế API key integration

- [ ] Mỗi integration và environment có key riêng.
- [ ] Key ID tách biệt secret; secret có entropy cao và được sinh bằng CSPRNG.
- [ ] Secret chỉ hiển thị một lần và được lưu trong secret manager phía client.
- [ ] Server chỉ lưu verifier được bảo vệ; không lưu secret bản rõ.
- [ ] Gửi key qua HTTPS header, không qua URL hoặc query string.
- [ ] Authorization header được redact khỏi log, trace, APM và error report.
- [ ] Key gắn với tenant, integration, scope, expiry và owner.
- [ ] Authentication tách biệt authorization; kiểm tra resource ownership và tenant boundary.
- [ ] Có rate limit, quota, anomaly detection và audit trail.
- [ ] Rotation có overlap ngắn, deadline và xác minh consumer migration.
- [ ] Suspend/revoke có semantics rõ và propagation được đo.
- [ ] Cache không làm sống lại key đã revoke.
- [ ] Có incident playbook khi secret xuất hiện trong Git, CI log hoặc artifact.
- [ ] Có phương án nâng cấp HMAC signing hoặc mTLS nếu threat model yêu cầu.
- [ ] Kiểm thử replay, cross-tenant access, enumeration, concurrency và restore.
- [ ] Owner, purpose và quy trình thay owner được quản lý.

## 28. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao API key không nên được xem là quyền truy cập toàn hệ thống?

**Gợi ý:** Key chỉ xác thực integration. Authorization vẫn phải kiểm tra scope, tenant, resource và action.

**Câu 2.** Vì sao server nên hiển thị secret một lần và lưu verifier?

**Gợi ý:** Giảm khả năng secret bản rõ xuất hiện trong database, backup hoặc giao diện quản trị; mất secret thì cấp key mới.

**Câu 3.** TLS có ngăn attacker replay API key đã bị đánh cắp không?

**Gợi ý:** Không. TLS bảo vệ kênh truyền; bearer key bị sao chép vẫn có thể được sử dụng. Cần revoke, scope, rate limit và có thể HMAC/mTLS.

**Câu 4.** Vì sao key cần tách theo tenant và environment?

**Gợi ý:** Giảm blast radius, ngăn test credential truy cập production và giúp revoke/rotation độc lập.

**Câu 5.** Khi rotate, vì sao không nên để key cũ và mới cùng active vô thời hạn?

**Gợi ý:** Mỗi key active là một bí mật có thể bị lộ; overlap dài làm tăng bề mặt tấn công và khó biết consumer nào chưa chuyển.

**Câu 6.** Revoke key ở registry có đủ không?

**Gợi ý:** Chưa chắc. Cache, gateway và downstream verifier phải nhận trạng thái mới trong propagation SLA.

**Câu 7.** Khi API key xuất hiện trong CI log, xóa log có đủ không?

**Gợi ý:** Không. Key có thể đã bị sao chép; cần revoke/rotate, điều tra access history và sửa pipeline/logging.

## 29. Ghi nhớ

**API key cho tích hợp là credential của workload, thường mang tính bearer, vì vậy phải được cấp riêng theo tenant/integration/environment, giới hạn scope và quản lý như một bí mật có vòng đời.** Secret cần entropy cao, chỉ hiển thị một lần, lưu verifier được bảo vệ và chỉ gửi qua HTTPS header đã được redaction khỏi log. Authentication phải tách khỏi authorization; mọi request tiếp tục được kiểm tra tenant, resource, scope, quota và policy. Rotation, expiry, suspend, revoke và cache invalidation phải có semantics rõ cùng bằng chứng thực thi. Khi key bị lộ, xóa khỏi source chưa đủ: cần revoke/rotate, điều tra session hoặc quyền phát sinh, xác minh mọi verifier từ chối key cũ và sửa nguồn rò rỉ. Với yêu cầu chống replay hoặc xác minh workload mạnh hơn, cân nhắc HMAC signing hoặc mTLS thay vì mở rộng quyền cho một bearer key dài hạn.
