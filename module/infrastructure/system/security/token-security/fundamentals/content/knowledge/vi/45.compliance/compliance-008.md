# Regulatory evidence: thu thập và bảo vệ bằng chứng tuân thủ bảo mật token

## 1. Bối cảnh và mục tiêu

Một tổ chức có thể đã cấu hình JWT validator, giới hạn scope, đặt thời hạn access token ngắn, xoay vòng client secret và thu hồi refresh token đúng quy trình. Khi kiểm toán nội bộ, khách hàng hoặc cơ quan đánh giá yêu cầu chứng minh các kiểm soát đó đang hoạt động, câu trả lời không thể chỉ là “hệ thống đã được cấu hình an toàn”. Tổ chức cần **regulatory evidence**: bằng chứng có nguồn gốc, phạm vi, thời điểm và tính toàn vẹn đủ để người đánh giá kiểm tra độc lập.

Trong bảo mật token, bằng chứng có thể gồm chính sách phát hành token, cấu hình issuer/resource server, danh mục OAuth client, log xác thực và cấp token, sự kiện thu hồi, kết quả kiểm thử, lịch sử review quyền, hồ sơ xử lý ngoại lệ và bằng chứng khắc phục sự cố. Các tài liệu này phải thể hiện được cả **thiết kế kiểm soát** lẫn **hoạt động thực tế** trong khoảng thời gian được đánh giá.

Bài học thuộc chương **Compliance** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung gắn với mô hình tin cậy và vòng đời token bảo mật, phân biệt JWT, opaque token, access token và refresh token; xác thực, phân quyền OAuth 2.0/OIDC; issuer, claims, scope, audience; lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại.

Sau bài này, người học có thể:

1. Phân biệt yêu cầu tuân thủ, kiểm soát nội bộ và bằng chứng chứng minh kiểm soát.
2. Xây dựng ma trận mapping giữa mục tiêu kiểm soát token và tài liệu cần thu thập.
3. Thu thập bằng chứng cho phát hành, xác minh, sử dụng, refresh, rotation và revocation.
4. Bảo vệ tính toàn vẹn, nguồn gốc, thời gian và quyền truy cập của evidence.
5. Giảm thiểu dữ liệu nhạy cảm trong log và audit package.
6. Chuẩn bị evidence package có thể truy vết, lấy mẫu và tái kiểm tra.

## 2. Regulatory evidence là gì?

**Evidence** là thông tin hoặc hiện vật được dùng để hỗ trợ một kết luận về kiểm soát. Ví dụ, một chính sách quy định access token phải có audience cụ thể là bằng chứng về **thiết kế**. Cấu hình validator đang chạy cho thấy chính sách đó được triển khai. Log và kết quả test trong kỳ đánh giá cho thấy kiểm soát đã **vận hành**. Một ảnh chụp màn hình đơn lẻ thường không chứng minh được cả ba khía cạnh.

Nên tách bốn khái niệm:

| Khái niệm | Câu hỏi | Ví dụ trong token security |
| --- | --- | --- |
| Requirement / obligation | Tổ chức cần đáp ứng điều gì? | Hạn chế truy cập, bảo vệ thông tin xác thực, lưu audit log theo yêu cầu áp dụng. |
| Control objective | Kết quả bảo mật mong muốn là gì? | Chỉ resource server đúng audience mới chấp nhận access token. |
| Control activity | Hệ thống/con người thực hiện điều gì? | JWT validator kiểm issuer, signature, audience, expiry và scope. |
| Evidence | Có thể kiểm tra bằng chứng nào? | Cấu hình validator, log quyết định, test case và kết quả chạy trong kỳ. |

Evidence không tự làm cho một tổ chức tuân thủ. Nó giúp chứng minh một kiểm soát cụ thể được thiết kế, triển khai và vận hành. Nếu kiểm soát không tồn tại hoặc không hiệu quả, việc tạo nhiều báo cáo không khắc phục được khoảng trống đó.

### 2.1. Design evidence và operating evidence

- **Design evidence:** chính sách, kiến trúc, threat model, standard cấu hình, phân công owner, tiêu chí cấp quyền và runbook.
- **Implementation evidence:** cấu hình thực tế, client registration, policy version, deployment record, secret manager policy và trust configuration.
- **Operating evidence:** log, metrics, review, approval, ticket, kết quả kiểm thử, sự kiện rotation/revocation và bằng chứng xử lý cảnh báo.
- **Exception/remediation evidence:** ngoại lệ được phê duyệt, lý do, phạm vi, thời hạn, biện pháp bù trừ, owner và bằng chứng đóng ngoại lệ.

Một control có thể có design evidence tốt nhưng operating evidence thiếu. Ví dụ policy yêu cầu review OAuth client mỗi quý, nhưng không có danh sách client đã review, người thực hiện, thời điểm và quyết định xử lý. Trong trường hợp đó, không thể kết luận control review quyền đã vận hành chỉ dựa vào policy.

## 3. Xác định phạm vi và tiêu chí đánh giá

Trước khi thu thập, phải xác định chính xác hệ thống, environment, dịch vụ, loại token, khoảng thời gian và control objective nằm trong phạm vi. Nếu không, evidence dễ bị lấy từ môi trường test trong khi kết luận áp dụng cho production, hoặc từ một issuer nhưng bỏ sót issuer khác.

### 3.1. Phạm vi token security

Danh mục phạm vi thường cần làm rõ:

- Authorization server/identity provider và các issuer được tin cậy.
- OAuth/OIDC client, service account, workload identity và confidential client.
- Resource server/API gateway chấp nhận access token.
- JWT và opaque token; access token, refresh token, ID token và client assertion.
- Token exchange, delegation, service-to-service và asynchronous job.
- Secret manager, KMS/HSM, JWKS endpoint, certificate authority và trust store.
- Log pipeline, SIEM, audit store, monitoring, backup và quy trình incident response.
- Môi trường production, staging, development và các region liên quan.

### 3.2. Kỳ đánh giá và cách lấy mẫu

Kỳ đánh giá có thể là một tháng, một quý, một năm hoặc khoảng thời gian được hợp đồng/khung kiểm soát yêu cầu. Evidence phải thể hiện đúng kỳ đó. Cấu hình hiện tại không chứng minh cấu hình đã tồn tại suốt cả kỳ; cần lịch sử thay đổi hoặc snapshot theo thời điểm.

Khi lấy mẫu, ghi rõ:

1. Tổng thể cần lấy mẫu (population), ví dụ tất cả OAuth client production.
2. Nguồn tạo tổng thể và thời điểm trích xuất.
3. Phương pháp chọn mẫu và tiêu chí chọn.
4. Số lượng mẫu, các trường hợp ngoại lệ và lý do.
5. Người thực hiện, người review và thời điểm hoàn tất.

Không tự tuyên bố mẫu đại diện thống kê nếu chưa có phương pháp lấy mẫu phù hợp. Nếu dùng mẫu rủi ro cao (admin client, client có scope nhạy cảm, credential sắp hết hạn), ghi rõ đó là mẫu theo rủi ro.

## 4. Mapping mục tiêu kiểm soát với evidence

Một **control evidence matrix** giúp liên kết yêu cầu, hoạt động và tài liệu chứng minh. Ví dụ dưới đây là mẫu thiết kế; mỗi tổ chức cần điều chỉnh theo phạm vi pháp lý, hợp đồng và kiến trúc thực tế.

| Mục tiêu kiểm soát | Hoạt động token security | Evidence có thể thu thập | Owner |
| --- | --- | --- | --- |
| Chỉ client/workload được phê duyệt mới xin token | Client registration, client authentication, approval | Client inventory, registration export, approval record, auth method config | IAM / Platform |
| Token chỉ dùng đúng API | Audience/resource validation | Validator config, API policy, positive/negative test report | API owner |
| Token chỉ cấp quyền cần thiết | Scope/role mapping và least privilege | Scope catalog, client grants, access review, authorization test | IAM / Application owner |
| Token có vòng đời giới hạn | TTL, exp, nbf, refresh policy | Issuer policy, sample claims đã redact, expiry test, configuration history | IAM |
| Token bị thu hồi không tiếp tục refresh | Revocation và refresh-token rotation | Revocation event, negative refresh test, token-family state theo policy | IAM / Security |
| Secret và private key được bảo vệ | Secret manager, KMS/HSM, access control | IAM policy, secret access audit, key inventory, rotation records | Platform / Security |
| Quyết định xác thực có thể truy vết | Security logging và monitoring | Event schema, log sample đã redact, SIEM query, alert/ticket | SOC / Platform |
| Ngoại lệ được kiểm soát | Risk acceptance và compensating control | Exception register, approval, expiry date, remediation evidence | Risk owner |
| Quyền được review định kỳ | Access/client review | Review population, reviewer, decisions, removal tickets | IAM / System owner |

### 4.1. Mẫu control record

Mỗi control nên có mã ổn định và mô tả rõ:

~~~yaml
control_id: TOKEN-AUTH-004
objective: Resource server chỉ chấp nhận access token có issuer và audience được tin cậy
scope:
  environments:
    - production
  systems:
    - orders-api
  issuers:
    - corporate-identity-provider
implementation:
  owner: platform-security
  validator_policy: jwt-resource-server-v3
  required_checks:
    - signature
    - issuer
    - audience
    - expiration
    - token_profile
operating_frequency: continuous
evidence_refs:
  - evidence://TOKEN-AUTH-004/config/2026-Q4
  - evidence://TOKEN-AUTH-004/tests/2026-Q4
reviewed_at: 2026-11-20T08:00:00Z
~~~

Đây là metadata minh họa, không phải schema chuẩn của một framework kiểm toán. Không đưa raw token, client secret, private key hoặc dữ liệu cá nhân vào control record. Evidence reference nên trỏ tới kho lưu trữ có kiểm soát truy cập.

## 5. Evidence cho phát hành và xác thực token

### 5.1. Authorization server và issuer

Để chứng minh issuer chỉ phát hành token theo policy:

- Tài liệu kiến trúc xác định issuer, authorization server, resource owner, client và resource server.
- Cấu hình grant type được phép cho từng client.
- Cấu hình client authentication method và policy cấp quyền.
- Cấu hình TTL, signing algorithm, key management và rotation.
- Scope/resource/audience catalog và mapping tới API.
- Approval record cho client mới, client nhạy cảm hoặc thay đổi quyền.
- Lịch sử thay đổi cấu hình và deployment trong kỳ đánh giá.

Không chỉ export cấu hình hiện tại. Cần chứng minh cấu hình đó thuộc đúng environment và thời điểm được đánh giá; nếu policy thay đổi giữa kỳ, lưu version và approval tương ứng.

### 5.2. JWT validation

Evidence của resource server xác minh JWT có thể gồm:

1. Cấu hình issuer allowlist và JWKS/key source.
2. Cấu hình thuật toán được phép; không tin thuật toán chỉ vì token header tự khai báo.
3. Cấu hình kiểm tra signature, iss, aud, exp, nbf, token type/profile và claim bắt buộc.
4. Kiểm tra scope/role cùng quyền nghiệp vụ trên resource.
5. Kết quả test với token đúng và token sai chữ ký, sai issuer, sai audience, hết hạn hoặc thiếu scope.
6. Lịch sử thay đổi validator và kết quả deployment.

JWT payload đã decode không phải bằng chứng token hợp lệ. Nếu đưa sample token vào audit package, chỉ dùng token giả lập hoặc payload đã được redact, kèm mô tả nguồn và cách xác minh; không lưu bearer token có thể sử dụng.

### 5.3. Opaque token và introspection

Với opaque access token, evidence thường tập trung vào:

- Introspection endpoint và client authentication giữa resource server với authorization server.
- Policy xử lý active, scope, aud, exp và các thuộc tính trả về.
- Timeout, cache TTL, fail-closed behavior và xử lý lỗi.
- Test với token active, inactive, expired, revoked và introspection service unavailable.
- Metrics về lỗi introspection, cache age và độ trễ propagation.

Không lưu raw opaque token trong log hoặc report. Một chuỗi opaque không thể được kiểm chứng bằng cách parse; phải dựa vào introspection contract và hành vi resource server.

## 6. Evidence cho access, refresh và ID token

Các token có mục đích khác nhau, do đó evidence cũng khác:

| Token | Evidence cần quan tâm | Sai lầm cần tránh |
| --- | --- | --- |
| Access token | Audience, scope, TTL, validator, resource-server decision | Dùng sample access token còn hiệu lực trong hồ sơ audit. |
| Refresh token | Client binding, storage, rotation, reuse detection, revocation | Coi refresh token như access token hoặc secret dùng chung. |
| ID token | OIDC client, iss, aud, nonce, signature và authentication context theo flow | Dùng ID token để gọi API nghiệp vụ. |
| Client assertion | Client authentication method, signing key, iss, sub, aud, exp, jti theo profile | Ghi assertion raw hoặc dùng lại assertion cũ. |
| Delegation/exchanged token | Subject, actor, target audience, scope và policy của STS | Chỉ kiểm token hợp lệ mà không kiểm actor được phép hành động thay subject. |

Evidence có thể gồm policy, cấu hình, audit event và test report. Không cần lưu credential thực để chứng minh vòng đời; thường chỉ cần ID tham chiếu, trạng thái, thời gian, owner và kết quả kiểm thử.

## 7. Evidence cho secret, key và certificate lifecycle

Token security phụ thuộc vào signing key và credential của OAuth client. Hồ sơ cần cho thấy ai có quyền tạo, đọc, dùng, xoay vòng và thu hồi credential.

### 7.1. Client secret

Evidence:

- Danh sách client, owner và secret reference/version.
- Secret manager policy giới hạn quyền đọc theo workload/role.
- Audit log về việc tạo, đọc, cập nhật và disable secret.
- Rotation schedule, change approval và deployment record.
- Test xác nhận secret cũ bị từ chối sau khi revoke.
- Bằng chứng secret không nằm trong repository, image, log hoặc CI artifact theo kiểm tra đã thực hiện.

Không export giá trị secret. Secret reference/version và trạng thái thường đủ để đối chiếu.

### 7.2. Signing key/JWKS

Evidence:

- Key inventory gồm key ID (kid), thuật toán, mục đích, owner, trạng thái và thời hạn.
- KMS/HSM access policy và audit.
- Quy trình tạo key, đăng ký public key, overlap, rollover và retire key cũ.
- JWKS snapshot đã xác định thời điểm, không kèm private key.
- Test xác minh token mới bằng key mới và cách hệ thống xử lý key cũ trong overlap.
- Alert khi key sắp hết hạn hoặc có thay đổi ngoài lịch.

Không đưa private key, seed hoặc HSM export vào evidence package. Public JWKS không phải secret, nhưng cần giữ nguồn và thời điểm để chứng minh nó đến từ issuer tin cậy.

### 7.3. mTLS certificate

Evidence:

- Certificate inventory: serial number, issuer, subject/SAN, EKU, validity và owner.
- CA/trust store configuration.
- Quy trình phát hành, phân phối, renewal và revocation.
- Kết quả TLS/client-auth test.
- CRL/OCSP hoặc trust-store update evidence nếu được sử dụng.
- Kiểm tra certificate-bound access token khi kiến trúc áp dụng RFC 8705.

Không lưu private key trong report. Certificate fingerprint và serial thường phù hợp hơn để liên kết sự kiện.

## 8. Evidence cho revocation và incident response

Thu hồi token là kiểm soát quan trọng khi user logout, consent bị rút, client bị xâm nhập hoặc credential bị lộ. Evidence nên cho thấy yêu cầu thu hồi được tiếp nhận, trạng thái được cập nhật và các thành phần liên quan phản ứng theo thời gian cam kết.

### 8.1. Refresh token revocation

Thu thập:

1. Policy về refresh token lifetime, rotation, client binding và reuse detection.
2. Audit event khi client gọi revocation endpoint.
3. Kết quả endpoint theo RFC 7009 (không chứa token raw).
4. Negative test chứng minh refresh token đã thu hồi không cấp access token mới.
5. Token-family/session state hoặc reference nếu issuer cung cấp.
6. Bằng chứng propagation giữa các node nếu hệ thống phân tán.

HTTP 200 từ RFC 7009 không chứng minh token đầu vào từng hợp lệ, vì endpoint được thiết kế tránh tiết lộ trạng thái token. Vì vậy, evidence cần kết hợp test sử dụng token sau revocation.

### 8.2. Access token đã phát hành

Phân biệt việc thu hồi refresh token với trạng thái access token đang tồn tại. JWT được xác minh offline có thể còn được chấp nhận tới exp nếu không có denylist, grant/session check hoặc cơ chế thu hồi bổ sung. Opaque token qua introspection có thể phản ánh active=false, nhưng cache có thể tạo độ trễ.

Evidence phải mô tả chính xác cơ chế của hệ thống:

- Token nào được revoke (refresh token, access token, grant, session hay client credential).
- Resource server kiểm tra trạng thái bằng cách nào.
- Thời gian propagation/caching được cam kết.
- Test đo thời điểm resource server bắt đầu từ chối.
- Những trường hợp token cũ còn hợp lệ tới hết hạn đã được chấp nhận theo risk decision nào.

Không ghi kết luận “logout lập tức vô hiệu mọi token” nếu kiến trúc không chứng minh được điều đó.

### 8.3. Incident evidence

Khi token hoặc secret bị lộ, evidence có thể gồm timeline sự cố, alert, client/issuer liên quan, credential version, token issuance bất thường, revoke event, containment, remediation và post-incident review. Dùng subject reference hoặc ID đã pseudonymize khi có thể. Không đính kèm bearer token, refresh token hoặc private key vào ticket sự cố.

## 9. Audit logging và schema sự kiện

Audit log cần trả lời được: **ai hoặc workload nào thực hiện hành động, hành động gì, trên resource nào, khi nào, kết quả ra sao và quyết định dựa trên policy nào?** Log phải đủ để điều tra nhưng không được trở thành nơi lưu credential.

### 9.1. Các sự kiện hữu ích

| Event | Trường có thể ghi |
| --- | --- |
| client.authentication | client ID, auth method, credential/key reference, result, reason code, timestamp |
| token.issued | issuer ID, client ID, grant type, audience/resource, granted scope, expiry, token reference |
| token.validation | resource server, issuer, audience check, scope decision, result, reason code |
| token.introspection | resource server client ID, active result, latency, cache hit/miss |
| token.exchanged | subject reference, actor/client ID, target audience, scope, policy decision |
| token.revoked | token type, grant/session reference, revocation result, propagation state |
| client.credential.rotated | client ID, credential version, auth method, change ID, actor, timestamp |
| access.review.completed | population reference, reviewer, review period, decisions and remediation references |

### 9.2. Ví dụ audit event đã tối thiểu hóa

~~~json
{
  "event_id": "evt-7f21",
  "event_type": "token.validation",
  "occurred_at": "2026-11-23T10:30:00Z",
  "issuer_id": "corporate-idp",
  "resource_server": "orders-api",
  "client_id": "web-portal",
  "subject_ref": "subj-9a3c",
  "audience_check": "passed",
  "scope_decision": "orders:read",
  "token_reference": "hmac-ref-71b2",
  "policy_version": "jwt-validator-v3",
  "result": "allowed",
  "correlation_id": "trace-5b12"
}
~~~

Đây là schema minh họa. subject_ref và token_reference phải được tạo bằng cơ chế bảo vệ phù hợp, tránh dùng hash đơn giản trên ID có thể đoán. Không đưa Authorization, raw JWT, refresh token, client secret, private key, DPoP proof hoặc toàn bộ claims vào event.

### 9.3. Đồng bộ thời gian và thứ tự sự kiện

Audit event nên có timestamp UTC, nguồn tạo, event ID duy nhất và correlation ID. Đồng bộ thời gian hệ thống giúp dựng timeline; nếu nhiều node có clock skew, cần ghi nhận offset hoặc metadata nguồn thời gian khi có thể. Không suy ra thứ tự nhân quả chỉ từ timestamp nếu event bus có thể giao trễ; dùng sequence/trace/correlation metadata để liên kết.

## 10. Tính toàn vẹn, nguồn gốc và chain of custody

Evidence có giá trị khi người đánh giá có thể xác định nó đến từ đâu, được thu thập khi nào, ai đã truy cập/chỉnh sửa và liệu nó có bị thay đổi sau khi tạo hay không.

### 10.1. Các thuộc tính chất lượng evidence

| Thuộc tính | Cách chứng minh |
| --- | --- |
| Authenticity | Nguồn hệ thống xác định, collector identity, export metadata và approval. |
| Integrity | Hash/checksum, chữ ký hoặc storage immutability; kiểm tra lại khi nhận và khi review. |
| Completeness | Query scope, population count, time range, pagination/retention status và số record. |
| Accuracy | Đối chiếu với nguồn gốc, cấu hình triển khai và test độc lập. |
| Timeliness | Timestamp UTC, thời điểm trích xuất, kỳ đánh giá và độ trễ log ingestion. |
| Reproducibility | Query/script/version, filter, tham số và bước tạo evidence được lưu. |
| Confidentiality | RBAC, encryption, redaction, retention và audit truy cập evidence. |

### 10.2. Hash và lưu trữ bất biến

Có thể tính SHA-256 cho file evidence sau khi export và lưu hash trong manifest hoặc hệ thống quản lý evidence. Kho lưu trữ có versioning, retention lock/WORM hoặc chữ ký số có thể giúp phát hiện thay đổi. Tuy nhiên:

- Hash chỉ chứng minh file hiện tại khớp với hash đã ghi; nó không tự chứng minh nguồn tạo file đáng tin.
- Hash không chứng minh dữ liệu nguồn đầy đủ hoặc query không bị lọc sai.
- Người tạo hash và người review nên được phân tách khi mức rủi ro yêu cầu.
- Manifest/hash cũng cần được bảo vệ và lưu audit.

### 10.3. Chain of custody

Ghi nhận tối thiểu:

1. Evidence ID và tên artifact.
2. Hệ thống nguồn, environment và tài khoản collector.
3. Query/filter hoặc phương pháp trích xuất.
4. Thời gian bắt đầu/kết thúc và thời gian export.
5. Hash, kích thước và định dạng file.
6. Người tạo, người review, lần chuyển giao và quyền truy cập.
7. Redaction/transformation đã thực hiện.
8. Vị trí lưu, retention class và ngày hết hạn.

Nếu evidence được chuyển cho auditor hoặc bên thứ ba, ghi nhận ai nhận, khi nào, mục đích và phạm vi truy cập. Chỉ chia sẻ artifact cần thiết; không gửi toàn bộ log chứa thông tin cá nhân nếu một trích xuất đã redact đủ trả lời control objective.

## 11. Bảo vệ dữ liệu cá nhân và bí mật trong evidence

Audit evidence có thể chứa subject ID, IP, client ID, tenant, email, device ID, correlation ID và dữ liệu hoạt động. Việc thu thập phục vụ compliance không đồng nghĩa được phép lưu mọi dữ liệu vô thời hạn.

### 11.1. Nguyên tắc tối thiểu hóa

- Không lưu raw access token, refresh token, ID token hoặc client assertion.
- Không lưu client secret, private key, HSM material hoặc DPoP proof.
- Chỉ lưu claim cần thiết để chứng minh quyết định; pseudonymize subject khi có thể.
- Không ghi toàn bộ request/response body nếu chỉ cần event metadata.
- Redact authorization headers tại application, proxy, APM, SIEM và support tooling.
- Giới hạn truy cập evidence theo role và mục đích; bật audit access.
- Mã hóa khi truyền và khi lưu; quản lý khóa tách biệt.
- Định nghĩa retention, legal hold và quy trình xóa theo nghĩa vụ áp dụng.

### 11.2. Retention và deletion

Không có một thời hạn retention duy nhất phù hợp mọi loại evidence. Thời hạn phụ thuộc quy định áp dụng, hợp đồng, ngành nghề, kỳ kiểm toán, yêu cầu điều tra, privacy notice và chính sách nội bộ. Tạo retention schedule theo loại dữ liệu:

| Loại evidence | Câu hỏi retention |
| --- | --- |
| Security event logs | Có yêu cầu lưu bao lâu, cần searchable online bao lâu và archive bao lâu? |
| Token/secret lifecycle records | Cần lưu metadata bao lâu để chứng minh rotation/revocation? |
| Access review records | Cần giữ qua bao nhiêu kỳ review/audit? |
| Test reports | Cần lưu phiên bản code/config, kỳ chạy và remediation đến khi nào? |
| Incident records | Có legal hold hoặc yêu cầu điều tra/khách hàng không? |
| Evidence có dữ liệu cá nhân | Có thể pseudonymize, aggregate hoặc xóa khi hết mục đích không? |

Khi hết retention, xóa an toàn theo quy trình và lưu bằng chứng deletion phù hợp. Không giữ token raw trong kho audit với lý do “phòng khi cần đối chiếu”.

## 12. Mapping tham khảo với các khung và quy định

Các khung dưới đây có thể giúp định hướng control mapping. Đây là **mapping tham khảo**, không phải kết luận pháp lý hoặc tuyên bố rằng một tập evidence bất kỳ tự động đáp ứng toàn bộ framework. Phiên bản, phạm vi áp dụng, ngành nghề, hợp đồng và kết quả đánh giá phải được xác nhận bởi compliance/legal owner.

| Framework / regulation | Chủ đề có thể liên quan đến token security | Evidence thường hữu ích |
| --- | --- | --- |
| ISO/IEC 27001:2022 | Identity management, access control, authentication information, access rights, logging, monitoring, cryptography | Policy, IAM inventory, approval/review, validator config, key lifecycle, logs, monitoring và test records |
| SOC 2 Trust Services Criteria | Logical access, authentication, authorization, logging, change management, monitoring và incident response | Control description, population/sample, approvals, access review, change tickets, audit logs, incident/test evidence |
| NIST SP 800-53 Rev. 5 | Access Control (AC), Identification and Authentication (IA), Audit and Accountability (AU), System and Communications Protection (SC) | Control implementation statement, configuration, access logs, key management, test results và assessment findings |
| PCI DSS v4.0.1 | Access control, authentication, account management, logging/monitoring và cryptographic protection trong phạm vi cardholder data environment | Account/client inventory, authentication config, privileged access review, log retention, key management và test records |
| GDPR | Accountability, data protection by design, integrity/confidentiality và security of processing khi log/evidence có dữ liệu cá nhân | Processing purpose, data minimization, access controls, retention schedule, incident records và security measures |
| HIPAA Security Rule | Access control, audit controls, integrity, person/entity authentication và transmission security khi áp dụng cho ePHI | Unique identity, access/audit logs, authentication config, integrity controls, TLS evidence và review records |

### 12.1. Ví dụ mapping chi tiết ở mức mục tiêu

- **Identity and access:** chứng minh OAuth client có owner, được phê duyệt, quyền đúng mục đích và được review định kỳ.
- **Authentication information:** chứng minh secret/private key/certificate được lưu, phân quyền, xoay vòng và thu hồi.
- **Secure authentication:** chứng minh resource server xác minh token đúng issuer, audience, signature, thời hạn và token profile.
- **Audit and monitoring:** chứng minh sự kiện cấp, xác minh, exchange, revoke và thất bại được ghi nhận, cảnh báo và review.
- **Cryptographic protection:** chứng minh signing key và TLS certificate được quản lý theo lifecycle, thuật toán và trust policy.
- **Privacy/accountability:** chứng minh log/evidence được tối thiểu hóa, giới hạn truy cập và lưu/xóa theo mục đích.

Để gắn một control vào điều khoản cụ thể, phải đối chiếu văn bản framework chính thức và phạm vi áp dụng. Không gán số điều khoản chỉ dựa trên tên chủ đề hoặc một bảng mapping mẫu.

## 13. Quy trình tạo evidence package

Một quy trình lặp lại được có thể chia thành các bước:

1. **Scope:** chốt hệ thống, environment, issuer, resource server, kỳ đánh giá và control objective.
2. **Map:** lập control evidence matrix, owner, nguồn dữ liệu, tần suất và retention.
3. **Collect:** trích xuất từ nguồn gốc bằng tài khoản collector được cấp quyền tối thiểu.
4. **Validate:** kiểm tra số lượng record, thời gian, filter, môi trường và tính đầy đủ.
5. **Redact:** loại bỏ token/secret/PII không cần thiết, ghi nhận phép biến đổi.
6. **Integrity:** tạo hash/manifest và lưu vào kho được kiểm soát.
7. **Review:** người độc lập kiểm tra sample, query, kết quả và exception.
8. **Remediate:** mở finding/ticket cho khoảng trống, gắn owner và deadline.
9. **Deliver:** cung cấp đúng artifact cần thiết cho auditor, theo dõi truy cập và thu hồi quyền sau kỳ đánh giá.

~~~mermaid
flowchart TD
    A[Scope và control objective] --> B[Evidence matrix]
    B --> C[Collect từ nguồn gốc]
    C --> D[Validate completeness và time range]
    D --> E[Redact dữ liệu nhạy cảm]
    E --> F[Hash và lưu immutable]
    F --> G[Independent review]
    G --> H{Đạt yêu cầu?}
    H -->|Không| I[Finding và remediation]
    I --> C
    H -->|Có| J[Evidence package]
    J --> K[Auditor review và access tracking]
~~~

### 13.1. Cấu trúc package gợi ý

~~~text
evidence-package/
  manifest.json
  scope/
    system-boundary.md
    control-matrix.csv
  design/
    token-security-policy.pdf
    trust-architecture.pdf
  implementation/
    issuer-config-redacted.json
    resource-server-validator-redacted.yaml
    oauth-client-inventory.csv
    key-inventory.csv
  operation/
    token-lifecycle-events-redacted.jsonl
    access-review-records.pdf
    rotation-and-revocation-records.pdf
    monitoring-alert-samples.pdf
  testing/
    jwt-validation-test-report.pdf
    revocation-test-report.pdf
    clock-skew-test-report.pdf
  exceptions/
    exception-register.csv
  integrity/
    SHA256SUMS
    collection-log.json
~~~

Tên thư mục và định dạng chỉ là gợi ý. Không export nhiều dữ liệu hơn mức auditor cần. Có thể dùng liên kết tới evidence vault thay vì sao chép artifact nếu cơ chế truy cập và retention được kiểm soát.

### 13.2. Evidence manifest mẫu

~~~json
{
  "package_id": "token-security-2026-q4",
  "scope": {
    "environment": "production",
    "systems": ["orders-api", "identity-provider"],
    "period_start": "2026-10-01T00:00:00Z",
    "period_end": "2026-12-31T23:59:59Z"
  },
  "artifacts": [
    {
      "evidence_id": "TOKEN-AUTH-004-CONFIG",
      "path": "implementation/resource-server-validator-redacted.yaml",
      "source": "configuration-management",
      "collected_at": "2026-11-23T10:00:00Z",
      "sha256": "<sha256-of-exported-file>",
      "redacted": true,
      "review_status": "approved"
    }
  ]
}
~~~

Manifest không nên chứa credential. Hash được tính trên đúng artifact đã lưu trong package; nếu redact sau khi tính hash thì phải tạo hash mới cho bản đã redact và giữ record về phép biến đổi theo quy trình.

## 14. Ví dụ thu thập evidence và truy vấn audit

Một truy vấn SIEM có thể lọc sự kiện theo client ID, loại event, khoảng thời gian và kết quả. Cú pháp thực tế phụ thuộc nền tảng; ví dụ dưới đây chỉ thể hiện logic:

~~~text
event_type IN (
  "client.authentication",
  "token.issued",
  "token.exchanged",
  "token.revoked"
)
AND environment = "production"
AND occurred_at >= "2026-10-01T00:00:00Z"
AND occurred_at <  "2027-01-01T00:00:00Z"
AND client_id IN approved_client_population
~~~

Khi export, ghi kèm:

- Query text/version và nguồn dữ liệu.
- Time range, timezone và ingestion delay.
- Tổng số record, số trang và trạng thái pagination.
- Filter đã áp dụng và danh sách client population.
- Thời điểm export, collector identity và hash file.
- Các field đã redact hoặc chuyển đổi.

Nếu query trả 0 record, không tự kết luận không có hoạt động. Kiểm tra pipeline có ingest event không, filter có đúng schema không, client population có được lấy đúng không và retention có bao phủ kỳ đánh giá không.

### 14.1. Đối chiếu độc lập

Để tăng độ tin cậy, đối chiếu một số nguồn:

- Client inventory từ authorization server với danh sách client trong deployment/configuration management.
- Secret version trong secret manager với version metadata ở workload.
- Token issuance event với client authentication event và workload deployment.
- Revocation event với negative refresh test và introspection/resource-server behavior.
- Access review decision với ticket thu hồi scope/role và trạng thái client sau thay đổi.

Đối chiếu không có nghĩa phải lưu tất cả dữ liệu thô. Có thể dùng reference ID, event ID và kết quả đối chiếu đã ký/review.

## 15. Ngoại lệ, finding và remediation

Không phải mọi kiểm soát đều hoàn hảo trong mọi thời điểm. Nếu phát hiện client không có owner, scope quá rộng, log thiếu event, secret quá hạn hoặc revocation propagation vượt SLO, cần ghi nhận finding thay vì chỉnh sửa evidence để che khoảng trống.

Một exception record nên có:

| Trường | Nội dung |
| --- | --- |
| Exception ID | Mã duy nhất. |
| Control ID | Kiểm soát bị ảnh hưởng. |
| System/environment | Phạm vi cụ thể. |
| Risk statement | Tình huống và tác động có thể xảy ra. |
| Root cause | Nguyên nhân đã xác minh hoặc trạng thái điều tra. |
| Compensating controls | Biện pháp bù trừ đang áp dụng. |
| Owner/approver | Người chịu trách nhiệm và người phê duyệt. |
| Expiry/review date | Ngày hết hạn hoặc ngày review tiếp theo. |
| Remediation ticket | Tham chiếu công việc khắc phục. |
| Closure evidence | Kết quả test/config/log chứng minh đã đóng. |

Ngoại lệ không được tồn tại vô thời hạn. Biện pháp bù trừ phải có hiệu lực đo được và được review. Nếu credential đang bị lộ hoặc có dấu hiệu bị lạm dụng, quy trình incident response và containment có thể cần ưu tiên hơn thời hạn remediation thông thường.

## 16. Kiểm thử chất lượng evidence

Evidence package cũng cần được kiểm thử. Có thể dùng test matrix sau:

| ID | Kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| EV-001 | Phạm vi environment | Artifact chỉ ra rõ production/test và không trộn lẫn. |
| EV-002 | Kỳ đánh giá | Tất cả log/config snapshot có time range phù hợp. |
| EV-003 | Nguồn gốc | Mỗi artifact có source system, collector và thời điểm thu thập. |
| EV-004 | Completeness | Population count, pagination và query filter được ghi nhận. |
| EV-005 | Integrity | Hash kiểm tra lại khớp với artifact đã lưu. |
| EV-006 | Access control | Chỉ reviewer/owner được phép truy cập evidence nhạy cảm. |
| EV-007 | Secret redaction | Không có raw access/refresh token, client secret hoặc private key. |
| EV-008 | PII minimization | Subject/email/IP chỉ xuất hiện khi có mục đích và quyền truy cập phù hợp. |
| EV-009 | JWT validation | Có cấu hình và test signature/issuer/audience/expiry/scope. |
| EV-010 | Opaque introspection | Có evidence active/inactive, cache và timeout behavior. |
| EV-011 | Revocation | Có revoke event và negative test sau revoke. |
| EV-012 | Key lifecycle | Có key inventory, approval, rotation và retirement evidence. |
| EV-013 | Client review | Population, reviewer, decision và remediation được liên kết. |
| EV-014 | Change traceability | Config change liên kết với approval, deployment và test. |
| EV-015 | Exception expiry | Exception có owner, approver và expiry/review date. |
| EV-016 | Reproducibility | Query/script/version và hướng dẫn tái tạo artifact có sẵn. |
| EV-017 | Retention | Artifact có retention class và ngày xóa/renewal phù hợp. |
| EV-018 | Chain of custody | Lịch sử transfer, access và review có thể truy vết. |
| EV-019 | Cross-source consistency | Inventory, log, secret version và deployment khớp nhau. |
| EV-020 | Auditor handoff | Người nhận chỉ được truy cập artifact cần thiết trong thời gian cần thiết. |

## 17. Các sai lầm thường gặp

| Sai lầm | Vì sao không đạt | Cách khắc phục |
| --- | --- | --- |
| Chỉ đưa policy mà không có operating evidence | Không chứng minh kiểm soát đã chạy trong kỳ | Bổ sung log, test, review và change record. |
| Dùng screenshot làm bằng chứng duy nhất | Khó chứng minh nguồn, phạm vi, tính đầy đủ và thời điểm | Export từ nguồn gốc, lưu query, metadata và hash. |
| Dùng cấu hình hiện tại để chứng minh cả năm | Không thể hiện lịch sử thay đổi | Lưu versioned config/deployment evidence theo thời điểm. |
| Đưa raw token vào audit package | Biến evidence store thành nơi chứa bearer credential | Redact; dùng token reference không thể tái sử dụng. |
| Hash file rồi kết luận evidence đáng tin | Hash không chứng minh nguồn hoặc completeness | Ghi source, collector, query, scope và independent review. |
| Không ghi query/filter | Auditor không thể tái tạo hoặc đánh giá sample | Lưu query version, time range, population và số record. |
| Trộn test với production | Kết quả không chứng minh control production | Gắn environment rõ và tách package. |
| Chỉ kiểm tra revoke endpoint HTTP 200 | Không chứng minh token không dùng lại được | Thực hiện negative refresh test và kiểm tra downstream theo policy. |
| Không ghi exception | Khoảng trống bị che khuất, không có owner/remediation | Duy trì exception register có expiry và closure evidence. |
| Lưu log vô thời hạn | Tăng rủi ro privacy và data exposure | Retention schedule, legal hold và deletion evidence. |
| Gửi toàn bộ log cho auditor | Chia sẻ quá mức dữ liệu nhạy cảm | Cung cấp extract tối thiểu, redacted và access-controlled. |
| Không đối chiếu nguồn | Evidence có thể không khớp trạng thái triển khai | Cross-check inventory, config, deployment và event records. |

## 18. Checklist chuẩn bị regulatory evidence

- [ ] Xác định framework, phiên bản, phạm vi và kỳ đánh giá áp dụng.
- [ ] Liệt kê issuer, OAuth client, resource server, token type và environment trong scope.
- [ ] Mapping mỗi control objective tới owner, activity, evidence source và tần suất.
- [ ] Có evidence thiết kế, triển khai và vận hành; lưu lịch sử thay đổi.
- [ ] Chứng minh kiểm tra signature, issuer, audience, expiry, scope và quyền nghiệp vụ.
- [ ] Chứng minh vòng đời refresh token, rotation, revocation và reuse detection theo policy.
- [ ] Chứng minh secret, signing key và certificate được bảo vệ và xoay vòng.
- [ ] Thu thập log đủ truy vết nhưng không chứa raw token/secret/private key.
- [ ] Ghi query, population, sample method, time range và completeness.
- [ ] Redact/pseudonymize dữ liệu cá nhân và giới hạn quyền truy cập.
- [ ] Tạo manifest, hash, chain of custody và lưu trong evidence vault được kiểm soát.
- [ ] Duy trì exception register, remediation owner và closure evidence.
- [ ] Review độc lập trước khi gửi auditor hoặc khách hàng.
- [ ] Áp dụng retention, legal hold và deletion theo yêu cầu đã xác định.

## 19. Kết luận và tài liệu tham khảo

Regulatory evidence cho token security cần chứng minh kiểm soát được **thiết kế đúng, triển khai đúng và vận hành trong đúng kỳ đánh giá**. Evidence đáng tin phải có nguồn gốc, phạm vi, thời gian, tính đầy đủ, tính toàn vẹn và quyền truy cập phù hợp. Hồ sơ nên bao phủ toàn bộ vòng đời: client registration, xác thực client, phát hành token, kiểm tra claims/scope/audience, lưu trữ, refresh, rotation, exchange, revocation, logging và incident response.

Không lưu raw credential để chứng minh rằng credential được bảo vệ. Thay vào đó, dùng policy, config đã redact, audit event, reference ID, test report, approval, hash và chain of custody. Mapping điều khoản phải dựa trên framework/phiên bản thực sự áp dụng và được compliance/legal owner xác nhận; một evidence package tốt hỗ trợ đánh giá nhưng không tự tạo ra chứng nhận tuân thủ.

Tài liệu tham khảo nên đối chiếu:

- **ISO/IEC 27001:2022 và ISO/IEC 27002:2022:** hệ thống quản lý an toàn thông tin và hướng dẫn kiểm soát identity, access, authentication, logging, monitoring, cryptography.
- **AICPA Trust Services Criteria:** tiêu chí đánh giá kiểm soát liên quan security, availability, processing integrity, confidentiality và privacy trong SOC 2.
- **NIST SP 800-53 Rev. 5:** catalog kiểm soát bảo mật và quyền riêng tư, gồm access control, identity/authentication và audit.
- **PCI DSS v4.0.1:** yêu cầu bảo vệ account, authentication, access và logging trong phạm vi áp dụng.
- **GDPR:** nguyên tắc accountability, data minimization, storage limitation và security of processing khi evidence có dữ liệu cá nhân.
- **HIPAA Security Rule:** administrative, physical và technical safeguards khi hệ thống thuộc phạm vi ePHI.
- **RFC 6749 — OAuth 2.0 Authorization Framework:** vai trò client, authorization server, access token và refresh token.
- **RFC 7009 — OAuth 2.0 Token Revocation:** endpoint thu hồi token.
- **RFC 7519 — JSON Web Token:** cấu trúc JWT và claims.
- **RFC 7662 — OAuth 2.0 Token Introspection:** kiểm tra trạng thái opaque token.
- **RFC 8693 — OAuth 2.0 Token Exchange:** trao đổi token và delegation.
- **OWASP Logging Cheat Sheet và Secrets Management Cheat Sheet:** thiết kế log an toàn, giảm thiểu dữ liệu nhạy cảm và quản lý secret lifecycle.
