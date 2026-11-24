# Service authentication audit

**Service authentication audit** là việc ghi nhận, bảo vệ và phân tích bằng chứng về cách một service, workload hoặc machine identity chứng minh danh tính khi giao tiếp với service khác. Audit cần trả lời được các câu hỏi: service nào khởi tạo kết nối, nó dùng credential hoặc cơ chế nào, issuer/authority nào được tin cậy, request hướng tới resource nào, quyết định xác thực là gì và sự kiện diễn ra trong phiên bản policy nào.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, người học tìm hiểu xác thực danh tính từ credential, password, MFA, passkey và certificate đến token, session, identity federation và account recovery. Với service authentication, chủ thể có thể là workload chạy trong container, backend API, batch job, agent hoặc thiết bị; không nhất thiết là con người. Vì vậy, audit cần ghi đúng machine identity, nguồn cấp credential, ranh giới tin cậy và quan hệ giữa client với resource server.

Điểm cốt lõi: **audit xác thực phải chứng minh được quyết định và nguồn danh tính mà hệ thống đã chấp nhận, nhưng không được lưu chính bí mật dùng để xác thực**. Log chứa client secret, private key, bearer token, session cookie hoặc HMAC key sẽ biến hệ thống audit thành mục tiêu chiếm quyền. Hãy lưu credential reference, key ID, certificate fingerprint và reason code cần thiết, rồi bảo vệ chúng bằng kiểm soát truy cập, tính toàn vẹn và retention phù hợp.

## 1. Service authentication audit là gì?

Service authentication là quá trình một machine identity chứng minh danh tính với một service hoặc resource server. Service authentication audit ghi lại các sự kiện liên quan đến quá trình đó, từ việc cấp hoặc đổi credential đến việc xác minh request và thu hồi quyền.

Ví dụ:
- Một workload trong Kubernetes dùng X.509 SVID hoặc client certificate để kết nối service nội bộ qua mTLS.
- Một backend dùng OAuth 2.0 Client Credentials để lấy access token từ authorization server rồi gọi API.
- Một service dùng private key để ký client assertion khi xác thực với token endpoint.
- Một integration dùng HMAC request signature để chứng minh request được tạo bởi bên giữ shared secret.
- Một workload dùng identity federation để đổi token từ môi trường cloud lấy credential có phạm vi hẹp.

Audit phải ghi được danh tính và kết quả đã xác minh, không chỉ ghi “HTTP 200” hoặc “login success”.

### 1.1. Mục tiêu của audit

Một hệ thống audit tốt hỗ trợ:

1. **Accountability:** xác định workload/client nào đã thực hiện một hoạt động.
2. **Incident response:** truy vết credential bị lộ, token replay, client giả mạo hoặc truy cập ngoài dự kiến.
3. **Policy verification:** chứng minh quyết định xác thực tuân theo issuer, audience, scope và trust policy.
4. **Lifecycle management:** theo dõi issuance, renewal, rotation, expiry và revocation.
5. **Compliance evidence:** cung cấp bằng chứng kiểm toán có nguồn gốc và thời điểm rõ ràng.
6. **Operational reliability:** phát hiện certificate sắp hết hạn, lỗi federation, clock drift và sự cố cấp token.
7. **Least privilege:** nhận ra service dùng scope, audience hoặc credential rộng hơn nhu cầu.

### 1.2. Audit khác debug log và distributed trace

| Loại dữ liệu | Câu hỏi chính | Đặc điểm |
| --- | --- | --- |
| **Security audit event** | Ai đã xác thực, bằng gì, với ai, theo policy nào và kết quả ra sao? | Có schema ổn định, actor/target rõ, được bảo vệ chống sửa đổi. |
| **Application log** | Ứng dụng đã xử lý nhánh logic nào và gặp lỗi gì? | Hữu ích cho vận hành, có thể thay đổi theo phiên bản code. |
| **Debug log** | Giá trị nội bộ nào giúp tìm lỗi? | Có thể rất chi tiết; nguy cơ vô tình ghi secret cao. |
| **Distributed trace** | Request đi qua những service nào và mất bao lâu? | Dùng trace/span ID để nối đường đi; không thay thế audit evidence. |
| **Metrics** | Tần suất, tỷ lệ lỗi và độ trễ là bao nhiêu? | Dữ liệu tổng hợp, không đủ để xác định từng actor/request. |

Có thể liên kết các loại dữ liệu bằng request ID hoặc trace ID, nhưng không nên dùng debug log làm nguồn audit duy nhất. Trace sampling có thể bỏ qua request; log ứng dụng có thể bị xoay vòng hoặc thiếu trường actor; metric không chứa đủ chi tiết để điều tra một lần truy cập cụ thể.

## 2. Xác định đúng service identity

Audit chỉ có giá trị nếu định danh được ghi nhận là định danh đã được xác minh. Tên process, pod name, IP hoặc user-agent do client gửi không tự chứng minh workload là ai.

### 2.1. Các loại machine identity

| Loại identity | Ví dụ | Nguồn xác minh có thể dùng |
| --- | --- | --- |
| **OAuth client** | client ID của integration gọi API. | Client registration, client authentication tại authorization server. |
| **Workload identity** | Service chạy trong cluster hoặc cloud runtime. | Workload identity provider, SPIFFE ID, cloud instance identity. |
| **X.509 client identity** | Service dùng certificate trong mTLS. | Certificate chain, SAN, issuer, EKU và trust policy. |
| **Service account** | Principal dành cho automation hoặc batch. | Directory/IAM record và credential gắn với account. |
| **Device identity** | Thiết bị hoặc gateway kết nối backend. | Device certificate, attestation hoặc enrollment record. |
| **Signing client** | Client ký assertion/request bằng private key. | Public key đã đăng ký, key ID và proof of possession. |

Tên gọi có thể khác nhau giữa cloud, container platform và IAM product. Điều quan trọng là identity có owner, issuer, namespace, environment và mục đích được quản lý rõ.

### 2.2. Principal, workload instance và credential reference

Một service có thể chạy nhiều replica. Audit nên phân biệt:
- **Logical principal:** danh tính service ổn định, ví dụ payments-api.
- **Workload instance:** một pod, VM hoặc process cụ thể đã khởi tạo request.
- **Credential reference:** certificate serial/fingerprint, key ID, client registration ID hoặc secret version.
- **Issuer/authority:** hệ thống cấp hoặc xác nhận credential.
- **Target resource:** API, service, tenant hoặc audience được gọi.

Không dùng instance ID thay cho logical principal: pod có thể bị thay thế liên tục. Cũng không gộp tất cả workload của một team vào một identity chung nếu cần thu hồi riêng và truy vết chính xác.

### 2.3. Provenance và trust boundary

Với mỗi identity, cần biết:
- Ai tạo và phê duyệt identity.
- Namespace, tenant, environment và owner.
- Credential được cấp từ CA, secret manager, IdP hay cloud identity service nào.
- Public key hoặc certificate được đăng ký từ nguồn nào.
- Identity được phép gọi service/resource nào.
- Khi nào credential được rotate hoặc revoke.
- Mapping từ external identity sang principal nội bộ được thực hiện theo rule nào.

Nếu gateway ghi nhận client identity từ header như X-Client-ID, header đó chỉ đáng tin khi gateway xóa giá trị do client tự gửi và tự đặt lại sau khi xác minh credential. Nếu không, attacker có thể giả principal trong audit log.

## 3. Các cơ chế service authentication cần audit

Mỗi cơ chế tạo ra bằng chứng khác nhau. Audit schema có thể thống nhất ở mức sự kiện, nhưng phải giữ được loại credential và semantics của cơ chế.

### 3.1. Mutual TLS (mTLS)

Trong mTLS, cả client và server đều xác thực certificate trong TLS handshake. Client certificate có thể cung cấp bằng chứng về workload identity theo trust profile.

Audit phía server có thể ghi:
- TLS version và cipher suite nếu cần cho policy.
- Certificate issuer, serial number và fingerprint.
- Subject/SAN hoặc URI SAN đã được map thành principal.
- EKU/key usage và kết quả chain validation.
- Trạng thái validity và revocation check.
- Trust bundle/CA version hoặc policy version.
- Kết quả handshake và reason code khi thất bại.

Không ghi private key hoặc toàn bộ certificate chain vào mỗi event nếu fingerprint và metadata đủ dùng. Certificate có thể chứa thông tin nhạy cảm; chỉ giữ subject/SAN cần thiết theo mục đích.

mTLS handshake thành công chứng minh client kiểm soát private key tương ứng với certificate được chấp nhận theo trust policy. Nó không tự cấp quyền gọi mọi endpoint. Authorization vẫn phải kiểm tra principal, audience/resource, action và policy.

### 3.2. OAuth 2.0 Client Credentials

Client Credentials Grant thường được dùng khi một confidential client truy cập resource thay mặt chính nó, không phải thay mặt một người dùng tương tác.

Audit cần phân biệt:
- Client ID đã xác thực.
- Cơ chế client authentication: client secret, private_key_jwt, mTLS hoặc phương thức được hỗ trợ.
- Authorization server/token endpoint.
- Scope và resource/audience được yêu cầu.
- Grant/policy đã áp dụng.
- Token issuance result, token ID/reference nếu có và thời hạn.
- Resource server đã nhận token nào và quyết định ra sao.

Không ghi client secret hoặc access token thô. Nếu token có jti hoặc token identifier, có thể ghi identifier theo policy; nếu không, dùng một reference/hash được thiết kế để tương quan mà không biến log thành bearer credential.

Client Credentials không chứng minh có người dùng cuối. Không tự gán employee ID hoặc user subject cho request chỉ vì service được gọi bởi một user ở tầng trước. Nếu service hoạt động thay mặt người dùng, cần một delegation/on-behalf-of model được định nghĩa riêng và audit cả actor lẫn delegated subject.

### 3.3. Private key JWT và client assertion

Một client có thể tạo JWT assertion và ký bằng private key để xác thực tại token endpoint. Audit nên ghi:
- Client ID và issuer/subject của assertion theo profile.
- Audience token endpoint.
- Key ID hoặc public-key fingerprint đã dùng.
- Thời điểm phát hành, expiry và assertion ID.
- Kết quả signature/claim validation.
- Replay detection result nếu assertion ID được theo dõi.

Assertion cần thời hạn ngắn, audience đúng và identifier dùng một lần theo profile. Không lưu assertion nguyên vẹn hoặc private key trong log. Một assertion hợp lệ cho token endpoint không phải access token để gửi tới API.

### 3.4. HMAC request authentication

Một số API dùng shared secret để tạo request signature. Nếu profile có hỗ trợ, audit có thể ghi key ID, canonicalization profile/version, timestamp, nonce reference, body digest reference và kết quả signature validation.

Request signature cần ràng buộc các thành phần như HTTP method, target/path, timestamp, nonce và digest của payload theo một specification nhất quán. Server cần chống replay bằng cửa sổ thời gian và lưu nonce/request identifier đã dùng. Không ghi shared secret hoặc chữ ký có thể bị tái sử dụng nếu chữ ký vẫn còn trong cửa sổ hợp lệ.

Không tự thiết kế HMAC protocol mới chỉ từ vài header tùy ý. Dùng profile đã được đánh giá, quy định rõ canonicalization, encoding, duplicate headers, proxy behavior, nonce store, clock skew và key rotation.

### 3.5. Workload identity federation

Workload có thể lấy identity token từ môi trường cloud hoặc orchestrator rồi đổi nó lấy token/certificate ở một authority khác. Audit nên nối được:
- External issuer và subject.
- Environment/cluster/namespace/service account đã được xác minh.
- Federation trust rule đã match.
- Target audience/resource.
- Credential mới được cấp và lifetime.
- Policy version, result và correlation ID.

Không tin claim do workload tự gửi ngoài token đã xác minh. Trust rule cần giới hạn issuer, subject pattern, audience và environment; wildcard quá rộng có thể cho workload khác mượn danh tính.

### 3.6. SPIFFE/SVID và service mesh

Trong kiến trúc dùng SPIFFE, workload identity có thể được biểu diễn bằng SPIFFE ID và được chứng minh qua X.509-SVID hoặc JWT-SVID theo trust domain. Audit có thể ghi SPIFFE ID, trust domain, SVID type, issuer/authority, certificate/key reference và thời hạn.

Service mesh có thể thực hiện mTLS ở sidecar/proxy. Khi đó audit ở application layer có thể chỉ thấy proxy identity hoặc header do mesh inject. Cần xác định proxy nào được tin, cách truyền principal tới ứng dụng và cách bảo vệ metadata khỏi spoofing. Không cho client bên ngoài tự gửi header giống header identity nội bộ.

## 4. Vòng đời credential và các sự kiện cần ghi

Audit không chỉ ghi lần authentication thành công. Cần theo dõi vòng đời credential để điều tra khi key bị lộ hoặc owner thay đổi.

### 4.1. Credential lifecycle events

| Event | Trường hợp | Bằng chứng cần lưu |
| --- | --- | --- |
| **Created/issued** | Client secret, certificate, SVID hoặc key reference được cấp. | Actor/authority, target identity, key/cert reference, scope, expiry, approval. |
| **Activated** | Credential bắt đầu được chấp nhận. | Thời điểm, environment, validation result và owner. |
| **Used** | Credential được dùng xác thực. | Principal, target, method, result, timestamp, correlation. |
| **Renewed/rotated** | Credential mới thay thế credential cũ. | Old/new references, overlap window, rollout status, actor/automation. |
| **Suspended** | Credential tạm dừng để review. | Lý do, người quyết định, phạm vi và thời hạn review. |
| **Revoked** | Credential không còn được tin cậy. | Thời điểm hiệu lực, reason, issuer/consumer acknowledgement. |
| **Expired** | Credential vượt thời hạn. | Expected expiry, observed rejection và consumer/resource. |
| **Deleted/retired** | Metadata hoặc registration được dọn dẹp. | Owner, retention basis và confirmation. |

Không phải mọi lần sử dụng đều cần ghi ở mọi tầng nếu volume quá lớn. Nhưng hệ thống phải xác định event nào là audit bắt buộc, event nào được aggregate và event nào có thể lấy từ trace/telemetry khác. Quyết định này phải dựa trên rủi ro và yêu cầu điều tra.

### 4.2. Issuance và usage phải liên kết được

Một certificate được cấp hôm nay nhưng không rõ workload nào dùng nó là inventory thiếu. Một request xác thực thành công mà không truy ngược được key/certificate version cũng khó điều tra.

Dùng credential reference ổn định:
- Certificate serial + issuer hoặc fingerprint.
- KID/public key fingerprint.
- Client registration ID và secret version reference.
- Workload identity subject.
- Token family/grant reference hoặc token ID theo policy.

Không dùng raw secret làm correlation ID. Không dùng một hash không khóa của secret ngắn/dễ đoán làm reference, vì có thể cho phép offline guessing. Ưu tiên ID do issuer/secret manager cấp hoặc keyed reference được bảo vệ.

## 5. Schema của một authentication audit event

Một event cần đủ trường để xác định actor, target, cơ chế, quyết định và provenance. Schema phải version hóa để các consumer không hiểu sai khi field thay đổi.

### 5.1. Các nhóm trường đề xuất

| Nhóm | Trường ví dụ | Mục đích |
| --- | --- | --- |
| **Event envelope** | event_id, event_type, schema_version | Định danh event và schema. |
| **Time** | occurred_at, observed_at, ingested_at | Phân biệt thời điểm xảy ra, collector quan sát và SIEM nhận. |
| **Actor** | principal_id, principal_type, issuer, tenant, workload_instance | Xác định service đã được xác minh. |
| **Credential** | auth_method, credential_type, credential_ref, key_id | Biết credential nào được dùng mà không lộ secret. |
| **Target** | resource_server, audience, service, endpoint, action | Xác định service/resource nhận request. |
| **Decision** | outcome, reason_code, policy_id, policy_version | Giải thích kết quả xác thực. |
| **Context** | environment, cluster, namespace, source network | Bổ sung ngữ cảnh có nguồn tin cậy. |
| **Correlation** | request_id, trace_id, span_id, transaction_id | Nối event với request và hệ thống khác. |
| **Evidence** | issuer_key_ref, certificate_fingerprint, validation_flags | Ghi bằng chứng xác minh tối thiểu. |
| **Lifecycle** | credential_expiry, rotation_version, revocation_state | Hỗ trợ theo dõi credential. |

Không bắt buộc mọi event phải có mọi field. Field không áp dụng cần được biểu diễn rõ theo schema, không điền giá trị giả như “unknown trusted”.

### 5.2. Ví dụ event JSON

    {
      "event_id": "evt-8b31",
      "schema_version": "1.0",
      "event_type": "service.authentication",
      "occurred_at": "2026-11-22T06:10:12.410Z",
      "observed_at": "2026-11-22T06:10:12.415Z",
      "actor": {
        "principal_id": "spiffe://prod.example/ns/payments/sa/worker",
        "principal_type": "workload",
        "issuer": "https://identity.example/issuer",
        "workload_instance": "pod-7d9c",
        "tenant_id": "org-7"
      },
      "credential": {
        "type": "x509_svid",
        "reference": "cert-fingerprint-ref-71",
        "issuer_key_id": "ca-key-2026-04",
        "expires_at": "2026-11-22T06:25:00Z"
      },
      "target": {
        "service": "ledger-api",
        "audience": "ledger-api",
        "action": "connect"
      },
      "decision": {
        "outcome": "success",
        "reason_code": "CLIENT_CERT_VALID",
        "policy_id": "prod-service-mtls",
        "policy_version": "12"
      },
      "correlation": {
        "request_id": "req-a192",
        "trace_id": "trace-5c01"
      }
    }

Đây là schema minh họa, không phải chuẩn giao thức. Các identifier và timestamp cần theo quy ước nội bộ; credential reference trong ví dụ là metadata, không phải certificate private key hay token có thể dùng để truy cập.

### 5.3. Ghi cả success và failure

Chỉ ghi thành công sẽ bỏ mất nhiều dấu hiệu tấn công. Failure event cần ghi reason code đủ hữu ích nhưng không tiết lộ chi tiết giúp attacker dò cấu hình.

Ví dụ reason code:
- UNKNOWN_CLIENT
- ISSUER_MISMATCH
- AUDIENCE_MISMATCH
- SIGNATURE_INVALID
- CERTIFICATE_EXPIRED
- CERTIFICATE_REVOKED
- CLIENT_NOT_AUTHORIZED
- PROOF_OF_POSSESSION_FAILED
- ASSERTION_REPLAY
- CLOCK_SKEW_EXCEEDED
- CREDENTIAL_DISABLED
- TRUST_POLICY_MISMATCH

Có thể nhóm lỗi trả về client để tránh enumeration, trong khi audit nội bộ giữ reason code chi tiết với quyền truy cập hạn chế.

## 6. Correlation trong hệ thống nhiều service

Một request có thể đi qua gateway, service A, service B, authorization server và resource server. Audit cần nối các sự kiện mà không nhầm principal ban đầu với principal của từng hop.

### 6.1. Request ID và trace ID

Dùng:
- Request ID để nhận diện một request tại boundary.
- Trace ID để nối distributed trace.
- Span ID để xác định một hop.
- Transaction ID cho một nghiệp vụ gồm nhiều request.
- Credential reference để liên kết sự kiện với key/certificate/token family.

Không để client tùy ý ghi đè trace context tin cậy nếu giá trị đó được dùng cho security correlation. Gateway có thể tiếp nhận hoặc tạo ID mới theo policy, validate format và ghi lại nguồn.

### 6.2. Giữ quan hệ giữa caller và delegated service

Ví dụ service A gọi service B thay mặt một user. Cần phân biệt:
- Original actor/user nếu có delegation hợp lệ.
- Calling workload A.
- Receiving service B.
- Delegation token/claim hoặc authorization context.
- Action/resource được yêu cầu.

Không ghi service A thành user cuối, cũng không ghi user cuối như thể trực tiếp kết nối mTLS tới service B. Giữ cả hai lớp actor để điều tra trách nhiệm và kiểm tra delegation.

### 6.3. Clock và thứ tự sự kiện

Dùng timestamp UTC và đồng bộ clock trên workload, gateway, IdP, CA và collector. Nên ghi cả occurred_at và ingested_at để nhận biết event đến trễ. Không dựa vào thứ tự nhận log để kết luận thứ tự request nếu hệ thống phân tán.

Nếu clock drift vượt tolerance, có thể ảnh hưởng exp/nbf, certificate validity, HMAC timestamp hoặc replay window. Audit cần ghi clock health hoặc reason code khi thời gian là nguyên nhân xác thực thất bại.

## 7. Bảo vệ tính toàn vẹn và khả năng chống sửa audit

Audit log có giá trị điều tra nên cần bảo vệ khỏi sửa, xóa, giả mạo và truy cập trái phép. Nếu attacker kiểm soát service đã bị xâm nhập và có thể xóa log cục bộ, bằng chứng chỉ lưu cùng service đó không đủ tin cậy.

### 7.1. Kiến trúc thu thập

Một kiến trúc tham khảo:

    Service / Gateway / IdP / CA
                |
                v
        Local audit emitter
                |
                v
        Authenticated transport
                |
                v
        Central collector
                |
          Validate schema
                |
          Durable queue
                |
          Append-only store
                |
       SIEM / alert / reports

Emitter nên gửi event qua transport xác thực tới collector tập trung. Collector cần xác thực nguồn, validate schema, giới hạn kích thước, chống event injection và xử lý retry. Không để service có quyền sửa hoặc xóa audit record đã được lưu tập trung.

### 7.2. Tamper resistance

Có thể kết hợp:
- Append-only hoặc immutable/WORM storage.
- Phân tách quyền vận hành service với quyền quản trị audit.
- Encryption in transit và at rest.
- Hash chaining hoặc signed batch để phát hiện sửa đổi.
- Timestamp/sequence từ collector đáng tin.
- Backup tách biệt và kiểm tra restore.
- Audit mọi thao tác truy vấn, export, retention change và deletion.
- Alert khi log source đột ngột im lặng hoặc sequence bị đứt.

Hash chain chỉ giúp phát hiện thay đổi khi anchor/checkpoint được lưu ở nơi độc lập. Nếu attacker có thể sửa toàn bộ log và toàn bộ hash chain trước khi checkpoint được bảo vệ, chuỗi hash đơn thuần không đủ. Chữ ký batch cần key được bảo vệ và quy trình rotation.

### 7.3. Không nhầm immutable với inaccessible

Audit cần bất biến trước actor không có quyền, nhưng vẫn phải có quy trình truy cập điều tra và retention/deletion hợp pháp. Dùng role-based access, just-in-time approval, reason/ticket, export logging và separation of duties. Không để mọi developer có thể tải toàn bộ audit production.

## 8. Không ghi secret hoặc dữ liệu nhạy cảm

Audit phải cung cấp bằng chứng đủ dùng mà không biến thành kho credential thứ hai.

**Không ghi:**
- Password, client secret hoặc API key plaintext.
- Private key, HMAC shared secret hoặc TOTP seed.
- Access token, refresh token, ID Token hoặc bearer assertion nguyên vẹn.
- Session cookie, authorization header hoặc recovery code.
- Nội dung request/response nhạy cảm nếu không cần cho audit.
- Dữ liệu cá nhân vượt mục đích điều tra.

**Có thể ghi nếu cần và được bảo vệ:**
- Credential ID, secret version reference, key ID.
- Certificate serial/fingerprint, issuer và validity.
- Token jti hoặc keyed reference theo policy.
- Client ID, workload identity và audience.
- Scope đã được cấp ở mức cần thiết.
- Reason code và validation flags.
- Request/trace ID.
- Network metadata đã giảm chi tiết hoặc được kiểm soát.

### 8.1. Redaction phải diễn ra trước khi lưu

Không chỉ trông chờ SIEM tự che dữ liệu sau khi nhận log. Secret có thể đã bị sao chép sang queue, backup, archive và nhiều index. Redaction cần ở emitter/gateway hoặc collector trước khi ghi bền vững.

Cần có test để bảo đảm:
- Authorization header không bị log.
- Query string chứa token không bị ghi.
- Exception không in object chứa secret.
- TLS/client library không dump private key hoặc credential.
- Debug mode production không vô tình bật payload logging.

### 8.2. Pseudonymization và data minimization

Nếu cần liên kết cùng một client qua thời gian nhưng không cần hiển thị raw identifier, dùng reference hoặc keyed pseudonym có quản lý khóa. Không dùng hash không khóa cho identifier entropy thấp nếu có thể dò ngược. Chỉ thu thập IP/hostname/device metadata khi có mục đích rõ và retention phù hợp.

## 9. Phát hiện bất thường từ service authentication audit

Audit event có thể giúp phát hiện service identity bị lạm dụng. Detector cần hiểu baseline theo workload, environment, resource và lịch triển khai.

### 9.1. Dấu hiệu cần theo dõi

- Client ID hoặc workload identity mới xuất hiện.
- Service gọi audience/resource chưa từng được cấp.
- Certificate fingerprint hoặc key ID thay đổi ngoài lịch rotation.
- Một credential được dùng đồng thời ở nhiều environment hoặc vị trí không phù hợp.
- Tỷ lệ authentication failure tăng đột ngột.
- Token issuance tăng bất thường hoặc scope rộng hơn bình thường.
- mTLS certificate gần hết hạn hoặc chain validation thất bại.
- Refresh/token exchange diễn ra từ workload không đúng namespace.
- HMAC nonce bị lặp hoặc timestamp nằm ngoài replay window.
- Identity tiếp tục hoạt động sau khi owner/service đã bị disable.
- Audit emitter im lặng, event sequence thiếu hoặc collector từ chối hàng loạt.

### 9.2. Baseline theo service và environment

Một workload batch có thể tạo burst vào cuối ngày; API tương tác có lưu lượng đều; service mesh có thể xác thực mỗi kết nối hoặc mỗi request tùy cấu hình. Không so sánh tất cả workload bằng cùng threshold.

Baseline cần xét:
- Logical principal và workload instance.
- Dev/test/staging/production.
- Audience, endpoint, scope và action.
- Lịch batch, deploy và autoscaling.
- Key/certificate rotation window.
- Số replica và network egress đã được phê duyệt.
- Owner, dependency và mức độ quan trọng của service.

### 9.3. Detection không tự động chứng minh compromise

Một certificate fingerprint mới có thể là rotation hợp lệ; một workload xuất hiện ở node khác có thể do rescheduling. Detection nên tạo signal và evidence. Policy/analyst cần đối chiếu deployment, change request, owner và trust state trước khi kết luận.

Với điều kiện chắc chắn như certificate revoked, signature invalid hoặc audience mismatch, resource server phải từ chối theo policy dù anomaly score thấp. Risk score không được ghi đè hard authentication checks.

## 10. Audit quyết định xác thực và authorization

Authentication audit và authorization audit liên quan nhưng cần phân biệt. Một service có thể xác thực thành công nhưng không được phép gọi action cụ thể.

Audit xác thực ghi:
- Principal đã được xác minh.
- Cơ chế và credential reference.
- Issuer, trust policy và audience.
- Kết quả kiểm tra credential/token.
- Thời điểm và correlation.

Audit authorization ghi:
- Actor và subject/delegated identity.
- Action và resource.
- Policy/rule được đánh giá.
- Quyền hoặc scope liên quan.
- Decision allow/deny và reason.
- Context hoặc approval cần thiết.

Một event có thể chứa cả hai kết quả nếu chúng diễn ra trong cùng request, nhưng không nên gộp thành một boolean “authenticated=true” rồi suy ra mọi hành động đều được phép.

### 10.1. Service-to-service delegation

Nếu service A gọi service B thay mặt user, audit phải ghi:
- Client/workload A đã xác thực.
- Subject user được delegate nếu có.
- Token/claim hoặc delegation context đã xác minh.
- Audience là service B.
- Scope/action/resource được yêu cầu.
- Authorization decision ở service B.

Nếu không có delegation, ghi rõ request là machine-to-machine của client A. Không tự gắn user identity từ header X-User do client gửi.

## 11. Vận hành pipeline audit

### 11.1. Reliability và event delivery

Audit pipeline phải xử lý:
- Retry và duplicate event.
- Out-of-order event.
- Collector hoặc queue outage.
- Backpressure và disk exhaustion.
- Schema version mới.
- Event malformed hoặc quá lớn.
- Source bị mất kết nối.
- Dead-letter và replay sau phục hồi.

Dùng event ID duy nhất và idempotent ingestion để tránh duplicate làm sai thống kê. Với event security quan trọng, xác định rõ nếu không ghi được audit thì request có bị từ chối, chuyển sang queue bền vững hoặc tiếp tục theo policy. Không để lỗi audit vô tình làm bỏ qua authentication.

### 11.2. Fail-open hay fail-closed?

Không có một lựa chọn chung cho mọi service:
- Nếu audit chỉ phục vụ analytics bổ trợ và event đã được ghi vào durable local queue, request có thể tiếp tục theo policy.
- Với hành động đặc quyền cần audit bắt buộc, có thể từ chối nếu không thể bảo đảm ghi nhận bằng chứng.
- Không bỏ qua signature, issuer, audience, expiry hoặc credential revocation chỉ vì collector lỗi.
- Cần cảnh báo khi queue đầy hoặc event bị drop; không im lặng bỏ audit.

Quyết định phải được xác định trong threat model, có owner và runbook. Nếu dùng local queue, cần bảo vệ khỏi sửa/xóa và giới hạn thời gian tồn đọng.

### 11.3. Schema evolution

Mỗi event nên có schema_version. Khi đổi tên field hoặc semantics:
- Tăng version và tài liệu hóa migration.
- Duy trì consumer tương thích trong giai đoạn chuyển đổi.
- Kiểm tra dashboard/rule không hiểu nhầm giá trị.
- Không tái sử dụng field cũ cho nghĩa khác.
- Kiểm tra dữ liệu cũ và mới có thể truy vấn nhất quán.

## 12. Retention, access control và privacy

Audit có thể chứa service topology, account ID, tenant, certificate subject, IP và lịch sử truy cập. Đây là dữ liệu nhạy cảm về vận hành và đôi khi là dữ liệu cá nhân.

Chính sách cần xác định:
- Mục đích và cơ sở lưu giữ.
- Thời hạn retention theo loại event và yêu cầu điều tra.
- Ai được đọc, tìm kiếm, export hoặc xóa.
- Cách mask/pseudonymize identifier.
- Phân vùng tenant và environment.
- Encryption key management.
- Legal hold và deletion process.
- Audit cho chính thao tác truy cập audit.

Không giữ mọi log vô thời hạn “để phòng khi cần”. Retention phải cân bằng nhu cầu điều tra, yêu cầu pháp lý, chi phí và rủi ro lộ dữ liệu. Khi xóa theo lịch, cần ghi nhận policy và kết quả mà không làm mất bằng chứng đang bị legal hold.

## 13. Incident response dựa trên audit

Khi nghi ngờ service credential bị lộ, audit giúp xác định phạm vi và trình tự hoạt động.

### 13.1. Câu hỏi điều tra

1. Principal nào đã được xác thực và issuer nào xác nhận?
2. Credential reference/key ID/certificate fingerprint nào được dùng?
3. Lần sử dụng hợp lệ cuối cùng là khi nào?
4. Request đi tới audience, service, endpoint và tenant nào?
5. Có dấu hiệu credential được dùng từ workload/environment khác không?
6. Có token issuance, exchange hoặc refresh bất thường không?
7. Credential đã bị rotate/revoke chưa và các consumer đã nhận trạng thái mới chưa?
8. Có service downstream nào chấp nhận request từ credential đó?
9. Audit source có bị mất, trễ, sửa hoặc drop event không?
10. Có user delegation hoặc OAuth grant liên quan không?

### 13.2. Containment

Theo mức độ và kiến trúc:
- Disable/revoke credential hoặc client registration bị ảnh hưởng.
- Rotate key/secret/certificate qua authority tin cậy.
- Revoke token family/grant và session liên quan.
- Chặn workload identity hoặc namespace có dấu hiệu compromise.
- Thu hẹp audience/scope và egress.
- Cô lập instance bị xâm nhập, bảo toàn evidence.
- Kiểm tra key cache, trust bundle và propagation tới mọi resource server.
- Theo dõi việc sử dụng credential cũ sau thời điểm revoke.

Không chỉ xóa secret khỏi vault rồi cho rằng attacker mất quyền. Credential có thể đã được copy; cần revoke ở verifier/issuer và đánh giá token/session downstream.

### 13.3. Bảo toàn bằng chứng

Giữ event gốc, schema version, collector metadata, integrity checkpoint và thời gian ingest. Ghi lại ai truy vấn/export evidence và mọi thay đổi trong incident timeline. Không sửa event gốc để “làm sạch”; bổ sung annotation/case record riêng có actor và timestamp.

## 14. Tình huống thực hành: workload dùng certificate không đúng môi trường

**Bối cảnh:** Service billing chạy ở production dùng mTLS để gọi ledger-api. Trong một đợt triển khai, một pod production bắt đầu xác thực bằng certificate fingerprint vốn chỉ được cấp cho staging. Một số request thành công vì trust bundle dùng chung cả hai môi trường.

**Phân tích:**

1. Chain có thể hợp lệ nhưng certificate được cấp cho environment khác.
2. Nếu policy chỉ kiểm CA chung mà không kiểm URI SAN, namespace hoặc environment, trust boundary quá rộng.
3. Audit cần ghi certificate reference, issuer, principal mapping, environment, target audience và policy version.
4. Một request thành công không chứng minh service có authority trong production.
5. Việc chia sẻ trust bundle không phân biệt environment làm tăng blast radius.

**Thiết kế lại:**

- Dùng trust domain hoặc CA/profile riêng theo environment khi phù hợp.
- Ràng buộc principal với URI SAN/namespace/service account và environment.
- Policy production chỉ chấp nhận identity đã đăng ký cho production.
- Audit success/failure gồm credential reference, mapped principal, target và rule đã match.
- Cảnh báo khi credential staging xuất hiện trong production.
- Rotate/revoke certificate bị dùng sai, kiểm tra các request đã được chấp nhận và thu hẹp trust bundle.
- Thêm kiểm thử negative case: certificate đúng CA nhưng sai namespace/environment phải bị từ chối.

**Bài tập:** Nếu certificate staging có chữ ký CA hợp lệ và còn hạn, service production có nên chấp nhận không? Không, trừ khi trust policy đã chủ đích cho phép identity đó. Chain validity chỉ là một phần của xác thực; principal mapping và environment boundary vẫn phải được kiểm tra.

## 15. Checklist thiết kế service authentication audit

- [ ] Inventory service/client/workload identities, owner, tenant, environment và mục đích.
- [ ] Phân biệt logical principal, workload instance, credential reference và target resource.
- [ ] Xác định issuer/authority và trust boundary của từng cơ chế authentication.
- [ ] Audit mTLS certificate, OAuth client authentication, private_key_jwt, workload federation và HMAC theo semantics riêng.
- [ ] Ghi cả authentication success, failure, issuance, renewal, rotation, suspension, revocation và expiry.
- [ ] Dùng event ID/schema version, UTC timestamp và occurred/observed/ingested time.
- [ ] Ghi principal, issuer, credential reference, audience/resource, method, decision, reason và policy version.
- [ ] Correlate bằng request/trace/transaction ID nhưng không tin header client không được xác minh.
- [ ] Phân biệt machine identity với delegated user/subject; không giả mạo actor qua header.
- [ ] Không log password, client secret, private key, HMAC secret, bearer token, cookie, assertion hoặc recovery code.
- [ ] Redact trước khi ghi bền vững; kiểm thử exception, proxy và debug logging.
- [ ] Bảo vệ collector, queue và store bằng authentication, encryption, append-only/immutable storage và separation of duties.
- [ ] Có integrity checkpoint/signature hoặc cơ chế phát hiện sửa/xóa phù hợp.
- [ ] Theo dõi source silence, event loss, queue backlog, duplicate và out-of-order.
- [ ] Xây baseline theo principal, workload, environment, audience và deployment window.
- [ ] Cảnh báo credential mới, audience/scope lạ, replay, expiry, revoked key usage và trust mismatch.
- [ ] Tách authentication decision khỏi authorization decision; audit cả delegation khi có.
- [ ] Định nghĩa retention, access, export, privacy và legal hold.
- [ ] Có runbook revoke/rotate credential, token/grant và downstream sessions.
- [ ] Kiểm thử sai issuer, audience, certificate environment, replay, clock skew, collector outage và log tampering.

## 16. Câu hỏi tự kiểm tra

**1. Service authentication audit là gì?**  
Là ghi nhận và bảo vệ bằng chứng về service/workload nào đã xác thực, dùng credential nào, với issuer và target nào, theo policy nào và kết quả ra sao.

**2. Vì sao không thể dùng pod name hoặc IP làm service identity?**  
Chúng có thể thay đổi, được tái sử dụng hoặc giả mạo; cần principal được xác minh bằng credential và trust mapping.

**3. mTLS audit nên lưu gì?**  
Certificate issuer, serial/fingerprint, mapped principal, validity, chain/ revocation result, target và policy version; không lưu private key.

**4. Client Credentials Grant có đại diện người dùng cuối không?**  
Không mặc định. Nó thường đại diện confidential client. Nếu có delegation, phải audit riêng client actor và delegated subject.

**5. Vì sao không log access token hoặc client secret?**  
Vì log có thể bị đọc, sao chép hoặc lưu lâu; secret trong log có thể trực tiếp trở thành credential để truy cập.

**6. Audit event cần liên kết với request bằng gì?**  
Event ID, request ID, trace ID, span ID hoặc transaction ID được xác thực/kiểm soát, cùng credential reference phù hợp.

**7. Chữ ký certificate hợp lệ có đủ cho production access không?**  
Không. Cần kiểm tra principal mapping, SAN, environment, audience, action và authorization policy.

**8. Audit khác distributed trace thế nào?**  
Audit ghi bằng chứng bảo mật có tính trách nhiệm và integrity; trace mô tả đường đi/độ trễ và có thể bị sampling.

**9. Nếu collector audit tạm thời lỗi thì có bỏ kiểm tra authentication không?**  
Không. Áp dụng fallback audit đã định nghĩa, nhưng vẫn phải giữ các kiểm tra credential, issuer, audience, expiry và revocation bắt buộc.

**10. Khi service credential bị lộ, chỉ rotate secret có đủ không?**  
Không. Cần revoke credential cũ tại verifier/issuer, xử lý token/grant/session downstream, xác định phạm vi truy cập và theo dõi credential cũ sau revoke.

**Ghi nhớ:** Service authentication audit phải liên kết được machine identity đã xác minh, credential reference, issuer, target, policy và kết quả của từng quyết định quan trọng. Hãy ghi cả thành công lẫn thất bại, bảo vệ log chống sửa đổi, không lưu secret, tách authentication khỏi authorization và chuẩn bị quy trình revoke/rotate có thể truy vết. Audit tốt giúp tổ chức biết service nào đang được tin cậy, vì sao nó được tin và điều gì cần làm khi trust bị phá vỡ.
