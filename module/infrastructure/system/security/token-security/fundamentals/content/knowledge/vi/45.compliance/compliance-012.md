# Đánh giá nhà cung cấp identity

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định phạm vi dịch vụ identity mà tổ chức đang mua hoặc tích hợp: Identity Provider (IdP), Customer Identity and Access Management (CIAM), workforce identity, federation broker hay dịch vụ phát hành token.
- Đánh giá khả năng bảo vệ vòng đời token, khóa ký, refresh token, session và luồng OAuth 2.0/OIDC của nhà cung cấp.
- Kiểm tra bằng chứng bảo mật, quyền riêng tư, tuân thủ, vận hành và khả năng ứng phó sự cố.
- Thiết kế proof of concept (PoC), tiêu chí nghiệm thu và thang điểm dựa trên rủi ro.
- Đưa các yêu cầu kỹ thuật vào hợp đồng, SLA và kế hoạch giám sát trong suốt thời gian sử dụng.
- Chuẩn bị phương án chuyển đổi hoặc rời nhà cung cấp mà không làm mất khả năng kiểm soát danh tính và token.

## 1. Vì sao phải đánh giá nhà cung cấp identity?

Nhà cung cấp identity thường nằm trên đường đi của đăng nhập, phát hành token và xác minh danh tính. Nếu dịch vụ này bị gián đoạn hoặc cấu hình sai, người dùng có thể không đăng nhập được; nếu tài khoản quản trị, khóa ký hoặc hệ thống phát hành token bị xâm phạm, kẻ tấn công có thể giả mạo danh tính và truy cập nhiều ứng dụng.

Với module bảo mật token, đánh giá nhà cung cấp không dừng ở câu hỏi “có hỗ trợ OAuth/OIDC không?”. Cần xác minh cách họ thực hiện các kiểm soát quan trọng:

- Token được ký, xác minh, giới hạn audience và scope ra sao?
- Khóa ký được tạo, lưu, xoay vòng và thu hồi thế nào?
- Refresh token có rotation, reuse detection và revoke không?
- Khi một token, client secret hoặc signing key bị lộ, thời gian chặn truy cập là bao lâu?
- Tổ chức có thể lấy log, điều tra, xuất dữ liệu và chuyển sang nhà cung cấp khác không?
- Dữ liệu danh tính và consent được lưu ở đâu, ai có thể truy cập và được giữ trong bao lâu?

Một nhà cung cấp có chứng nhận hoặc tài liệu tiếp thị tốt vẫn cần được kiểm tra theo kiến trúc và mức rủi ro cụ thể của tổ chức. Chứng nhận là một phần bằng chứng trong phạm vi được đánh giá; nó không tự chứng minh mọi tính năng, cấu hình tenant hoặc cách tích hợp của khách hàng đều an toàn.

## 2. Xác định đúng phạm vi nhà cung cấp

“Identity provider” có thể chỉ nhiều loại dịch vụ khác nhau. Trước khi so sánh, hãy xác định hệ thống sẽ giao phần trách nhiệm nào cho nhà cung cấp.

| Loại dịch vụ | Trách nhiệm thường gặp | Câu hỏi cần làm rõ |
| --- | --- | --- |
| Workforce IdP | Đăng nhập nhân viên, MFA, SSO tới ứng dụng nội bộ | Quản lý vòng đời nhân viên, thiết bị, tài khoản đặc quyền thế nào? |
| CIAM | Đăng ký, đăng nhập và quản lý người dùng khách hàng | Có hỗ trợ lưu lượng lớn, account recovery và chống account takeover không? |
| Authorization server | Phát hành access/refresh token và quản lý grant | Token policy, consent, revocation và custom authorization ra sao? |
| Federation broker | Kết nối nhiều IdP hoặc domain | Ánh xạ subject, issuer, claims và trust boundary thế nào? |
| Identity verification service | Xác minh danh tính hoặc thuộc tính | Dữ liệu giấy tờ/sinh trắc học được xử lý, lưu và xóa ra sao? |
| Managed directory | Lưu trữ account, group và thuộc tính | Đồng bộ, export, backup và phân quyền quản trị thế nào? |

Một nhà cung cấp có thể cung cấp nhiều loại dịch vụ. Hãy lập sơ đồ ranh giới trách nhiệm giữa vendor, tổ chức và các hệ thống tích hợp. Ví dụ, IdP có thể xác thực người dùng và phát hành token, nhưng resource server của tổ chức vẫn phải kiểm tra audience, scope, tenant và quyền trên từng tài nguyên.

~~~mermaid
flowchart LR
    U["Người dùng / Workload"] --> I["Nhà cung cấp Identity"]
    I -->|ID Token / Access Token| C["Ứng dụng / API Gateway"]
    C --> R["Resource Server"]
    R --> D["Dữ liệu và nghiệp vụ"]
    I --> L["Audit / Event / Admin API"]
    L --> M["SIEM và hệ thống giám sát của tổ chức"]
    K["KMS / HSM / JWKS"] --> I
~~~

Sơ đồ chỉ là mô hình khái quát. Trong một số kiến trúc, tổ chức tự quản lý KMS/HSM hoặc signing key; trong kiến trúc khác, nhà cung cấp quản lý toàn bộ. Hãy ghi rõ ai kiểm soát từng khóa, ai có quyền thay đổi cấu hình và ai chịu trách nhiệm khi xảy ra sự cố.

## 3. Đánh giá giao thức và khả năng tương thích

### 3.1 OAuth 2.0 và OpenID Connect

Xác minh nhà cung cấp hỗ trợ đúng các luồng cần dùng, không chỉ có checkbox “OAuth 2.0”:

- Authorization Code Flow với PKCE cho ứng dụng người dùng và public client.
- OIDC ID Token validation, discovery metadata và JWKS endpoint.
- Client authentication phù hợp với loại client; ưu tiên cơ chế mạnh như private_key_jwt hoặc mTLS khi kiến trúc hỗ trợ.
- Audience/resource restriction và scope có ý nghĩa rõ.
- Refresh token rotation, reuse detection và revoke.
- Token introspection/revocation khi dùng opaque token hoặc khi cần trạng thái tập trung.
- PAR, JAR, mTLS hoặc DPoP nếu mô hình rủi ro và profile yêu cầu.

Không chấp nhận Implicit Flow hoặc Resource Owner Password Credentials cho một triển khai mới nếu không có ngoại lệ được đánh giá và phê duyệt theo tiêu chuẩn hiện hành. Với ứng dụng browser/mobile, cần đánh giá redirect URI chính xác, PKCE, state/nonce, deep link và cách lưu token trên thiết bị.

### 3.2 Kiểm tra metadata và token contract

Yêu cầu vendor cung cấp discovery document, ví dụ OIDC discovery metadata, và mẫu token đã loại bỏ dữ liệu thật. Kiểm tra:

| Thành phần | Câu hỏi đánh giá |
| --- | --- |
| Issuer | Giá trị issuer có ổn định, duy nhất và được tài liệu hóa không? |
| JWKS | Endpoint có TLS, hỗ trợ nhiều key khi rotation và công bố kid rõ ràng không? |
| Signing algorithm | Có allowlist thuật toán an toàn và từ chối thuật toán không được phép không? |
| Audience | Có phát hành token riêng theo API/resource không? |
| Scope | Có giới hạn scope theo client, user, tenant và grant không? |
| Claims | Có thể kiểm soát claim cần thiết, tránh phát hành PII dư thừa không? |
| Expiration | Access token, ID Token và refresh token có lifetime policy riêng không? |
| Clock tolerance | Clock skew được cấu hình và giới hạn ra sao? |
| Token type | Có phân biệt ID Token, access token và token dành cho mục đích khác không? |
| Key ID | Có hỗ trợ rotation và hành vi rõ khi `kid` không còn tin cậy không? |

Kiểm tra ứng dụng có thể xác minh chữ ký, issuer, audience, thời hạn và loại token theo contract mà không cần dựa vào claim không được bảo đảm. Không dùng ID Token thay cho access token khi gọi API.

### 3.3 Federation và liên kết tài khoản

Nếu kết nối nhiều IdP, đánh giá:

- Cách ánh xạ subject ổn định và tránh ghép nhầm hai tài khoản.
- Cách xử lý issuer mới, issuer bị thu hồi và thay đổi domain.
- Chính sách xác minh email/phone trước khi liên kết account.
- Quy tắc account linking, unlinking và recovery.
- Kiểm soát claim transformation, group mapping và role mapping.
- Khả năng ngăn một IdP bên ngoài tự cấp quyền quản trị nội bộ qua claim không được tin cậy.

## 4. Đánh giá bảo mật token và khóa ký

Đây là phần trọng tâm đối với hệ thống xác thực và phân quyền.

### 4.1 Signing key và key management

Yêu cầu nhà cung cấp mô tả:

- Key được tạo trong KMS/HSM hay tạo bên ngoài rồi import?
- Private key có thể export không? Ai có quyền export hoặc sử dụng key?
- Có phân tách key theo tenant, môi trường, issuer hoặc mục đích không?
- Rotation có overlap key, thông báo trước và lịch retire cụ thể không?
- Có emergency revoke khi key bị compromise không?
- JWKS cache được cập nhật thế nào và có cơ chế xác nhận verifier đã nhận key mới không?
- Có audit event cho create, rotate, disable, delete và policy change không?

Đừng chỉ hỏi vendor có “HSM” hay không. Hãy hỏi key boundary, quyền quản trị, separation of duties, backup/recovery, audit và cách phản ứng khi key bị lộ. Nếu vendor không cho khách hàng kiểm soát private key, cần hiểu rõ đây là mô hình trust và trách nhiệm chấp nhận.

### 4.2 Access token và refresh token

Kiểm tra:

- Access token có lifetime phù hợp với mức rủi ro và khả năng revoke không?
- Có ràng buộc audience/resource để giảm nguy cơ token bị dùng sai API không?
- Scope có thể giới hạn theo client, user, tenant và loại grant không?
- Refresh token có rotation và phát hiện reuse không?
- Có thể revoke một token, một token family, một session, một client hoặc toàn bộ grant không?
- Token có thể được sender-constrain bằng mTLS hoặc DPoP nếu cần không?
- Token endpoint có rate limit và chống brute force/replay phù hợp không?

Hỏi rõ semantics của revoke: endpoint trả thành công có nghĩa token đã bị vô hiệu hóa ở authorization server, hay tất cả resource server cũng đã từ chối? Nếu có cache, thời gian tối đa để trạng thái revoke lan tới mọi verifier là bao lâu?

### 4.3 Claims và dữ liệu nhạy cảm

Yêu cầu cấu hình claim allowlist. Chỉ phát hành thông tin cần cho mục đích xác thực/phân quyền. Tránh đưa địa chỉ, số điện thoại, dữ liệu nhạy cảm hoặc thông tin hồ sơ đầy đủ vào access token nếu resource server không cần.

Đánh giá:

- Claim `sub` có ổn định và không tái sử dụng ngoài ý muốn không?
- Claim tenant/role/group có được kiểm soát nguồn và freshness không?
- Có thể phân biệt user, service principal và actor trong delegated flow không?
- Có custom claim namespace để tránh xung đột không?
- Claim thay đổi hoặc membership bị thu hồi được phản ánh tới token hiện hành như thế nào?

### 4.4 Tenant isolation và phân quyền quản trị

Với dịch vụ multi-tenant, kiểm tra:

- Tenant administrator chỉ quản trị tenant của mình.
- API quản trị không thể đọc hoặc thay đổi user, client, key hay consent của tenant khác.
- Log, export, support tooling và backup không trộn dữ liệu tenant.
- Support engineer của vendor có quyền truy cập theo nguyên tắc least privilege và có audit.
- Cấu hình issuer, domain, callback, branding và policy được cô lập đúng tenant.

## 5. Đánh giá xác thực người dùng và account lifecycle

Token chỉ an toàn nếu danh tính được xác thực và duy trì đúng. Đánh giá các chức năng:

| Chủ đề | Bằng chứng cần yêu cầu |
| --- | --- |
| MFA | Phương thức hỗ trợ, policy bắt buộc, step-up và chống bypass |
| Phishing resistance | Hỗ trợ passkey/WebAuthn hoặc cơ chế tương đương cho tài khoản rủi ro cao |
| Account recovery | Kiểm soát reset password, mất thiết bị, đổi email/phone và recovery code |
| Provisioning | SCIM/API đồng bộ user/group và xử lý disable/deprovision |
| Privileged access | Role quản trị, MFA bắt buộc, approval và audit |
| Session management | Session lifetime, idle timeout, logout và revoke all sessions |
| Risk detection | Phát hiện đăng nhập bất thường, credential stuffing và account takeover |
| Service identity | Workload identity, client authentication và vòng đời machine credential |

Đặc biệt kiểm thử trường hợp nhân viên nghỉ việc hoặc người dùng bị khóa: tài khoản bị disable có ngăn refresh token, session và token issuance mới không? Các access token đã cấp còn dùng được bao lâu? Có cách thu hồi khẩn cấp và xác minh trên các API không?

## 6. Đánh giá bảo mật, tuân thủ và bằng chứng

### 6.1 Tài liệu assurance

Yêu cầu tài liệu phù hợp với quy mô và mức rủi ro:

- SOC 2 Type II report hoặc báo cáo assurance tương đương, kèm phạm vi, kỳ đánh giá, ngoại lệ và subservice organizations.
- ISO/IEC 27001 certificate và Statement of Applicability hoặc phạm vi ISMS liên quan.
- Báo cáo penetration test gần đây, phạm vi, mức độ phát hiện và trạng thái khắc phục.
- Vulnerability management policy, SLA xử lý lỗ hổng và quy trình disclosure.
- Secure development lifecycle, code review, dependency scanning và software supply chain controls.
- Business continuity/disaster recovery test và kết quả khôi phục.
- Chính sách quản lý nhân sự, background screening và quyền truy cập production.

Đọc kỹ scope và thời gian. Một chứng nhận của công ty mẹ không mặc nhiên bao phủ dịch vụ, region, data center hoặc tính năng mà tổ chức đang mua. Một penetration test chỉ có giá trị cho phạm vi và thời điểm được kiểm thử.

### 6.2 Privacy và data processing

Kiểm tra:

- Vai trò controller/processor và thỏa thuận xử lý dữ liệu (DPA).
- Vị trí lưu trữ, backup, replication và data residency.
- Danh sách subprocessor và quy trình thông báo thay đổi.
- Mục đích sử dụng dữ liệu, telemetry và dữ liệu phục vụ analytics.
- Retention, export, deletion và xác minh xóa khi chấm dứt hợp đồng.
- Cơ chế xử lý data subject request và hỗ trợ nghĩa vụ pháp lý.
- Chuyển dữ liệu xuyên biên giới và cơ chế pháp lý liên quan nếu áp dụng.

Không chỉ hỏi dữ liệu được lưu ở quốc gia nào. Hỏi cả nơi xử lý support ticket, log, backup, telemetry, disaster recovery và subprocessor.

### 6.3 Incident notification và trách nhiệm

Hợp đồng nên xác định:

- Thời hạn vendor phải thông báo khi có sự cố ảnh hưởng dữ liệu hoặc credential.
- Kênh liên lạc khẩn cấp 24/7 và escalation path.
- Nội dung thông báo ban đầu và các bản cập nhật điều tra.
- Trách nhiệm phối hợp revoke token, rotate key, cung cấp log và bảo toàn evidence.
- Cách xác định phạm vi khách hàng/tenant bị ảnh hưởng.
- Trách nhiệm thông báo cho cơ quan quản lý hoặc chủ thể dữ liệu theo phân công pháp lý.

Không dùng câu “thông báo trong thời gian hợp lý” nếu hệ thống cần phản ứng nhanh. Đặt mốc thời gian cụ thể theo mức rủi ro và nghĩa vụ pháp lý của tổ chức.

## 7. Đánh giá vận hành và độ tin cậy dịch vụ

Identity là dependency quan trọng. Một outage có thể ngăn đăng nhập mới, refresh token hoặc kiểm tra introspection. Đánh giá:

- SLA availability cho login, token endpoint, discovery, JWKS, introspection và revoke.
- Latency theo percentile, throughput và giới hạn rate.
- Khu vực triển khai, multi-region failover và data replication.
- Lịch bảo trì, thông báo thay đổi và deprecation policy.
- Backup, RTO/RPO, disaster recovery test và bằng chứng khôi phục.
- Status page, incident history và post-incident report.
- Hỗ trợ kỹ thuật, thời gian phản hồi và escalation cho sự cố nghiêm trọng.

SLA chung của nền tảng không nhất thiết áp dụng giống nhau cho mọi endpoint. Hãy yêu cầu số liệu riêng cho token issuance, JWKS, introspection và revocation vì mỗi endpoint có tác động khác nhau.

### Failure mode cần thử

| Sự cố | Câu hỏi vận hành |
| --- | --- |
| Authorization server unavailable | Ứng dụng xử lý login/refresh ra sao? |
| JWKS endpoint timeout | Verifier dùng cache trong bao lâu và khi nào fail closed? |
| Introspection unavailable | Resource server từ chối hay dùng cache theo policy nào? |
| Revoke endpoint unavailable | Có retry, queue hoặc trạng thái pending để xác minh không? |
| Region outage | Token/issuer có tiếp tục được xác minh ở region khác không? |
| Clock drift | Token validation có dung sai được cấu hình và giám sát không? |
| Key rotation lỗi | Có rollback an toàn và quy trình emergency key change không? |

Không chấp nhận fallback “fail open” cho mọi lỗi identity. Nếu hệ thống có chế độ degraded, phải xác định tài nguyên nào được phép truy cập, thời hạn, điều kiện và audit.

## 8. Thực hiện PoC và kiểm thử nghiệm thu

Tài liệu vendor không thay thế thử nghiệm. Dựng sandbox với client, issuer, resource server và dữ liệu giả. Không dùng tài khoản, token hoặc dữ liệu production trong PoC.

### 8.1 Bộ test kỹ thuật tối thiểu

1. **Discovery/JWKS:** lấy metadata, xác minh issuer và tải key; thử key rotation và verifier cache.
2. **Signature validation:** token hợp lệ được chấp nhận; chữ ký sai, thuật toán không được phép và `kid` không tin cậy bị từ chối.
3. **Audience/scope:** token dành cho API A không gọi được API B; scope thiếu bị từ chối.
4. **Expiration:** token hết hạn và token có `nbf` ở tương lai bị từ chối; clock skew khớp policy.
5. **Refresh rotation:** refresh token cũ bị từ chối sau rotation; reuse detection hoạt động theo contract.
6. **Revocation:** revoke opaque token/refresh family; đo thời gian resource server từ chối.
7. **Client authentication:** secret/certificate/key sai bị từ chối; credential cũ không còn dùng được sau rotation.
8. **Tenant isolation:** admin/user tenant A không đọc hoặc thay đổi tenant B.
9. **MFA/recovery:** thử bypass MFA, reset và recovery theo các đường biên.
10. **Audit:** log đủ actor, client, event và timestamp nhưng không chứa raw token hoặc secret.

### 8.2 Test sự cố

Mô phỏng các tình huống có kiểm soát:

- Thu hồi refresh token family trong khi access token descendant còn hạn.
- Gỡ signing key khỏi JWKS và kiểm tra mọi verifier sau cache refresh.
- Disable client đang có session và grant.
- Tắt tạm thời introspection endpoint.
- Mất kết nối tới một region.
- Gửi sự kiện revoke trùng lặp hoặc đến sai thứ tự.

Ghi kết quả, thời gian phát hiện, thời gian revoke, thời gian lan truyền và hành vi fallback. Nếu vendor không cho mô phỏng một tình huống trong sandbox, yêu cầu bằng chứng test độc lập và ghi rõ giới hạn xác minh.

### 8.3 Tiêu chí nghiệm thu

Trước PoC, định nghĩa expected result cho từng test. Ví dụ:

| Tiêu chí | Điều kiện nghiệm thu minh họa |
| --- | --- |
| Issuer/audience validation | Mọi token sai issuer hoặc audience bị từ chối |
| Key rotation | Verifier nhận key mới trước khi token mới được sử dụng; key cũ bị loại theo lịch |
| Revoke propagation | Tất cả verifier từ chối token trong SLA đã thống nhất |
| Refresh reuse | Token family bị xử lý theo policy đã công bố |
| Audit | Có thể truy vết ai đã đổi policy/key/revoke token |
| Tenant isolation | Không có truy cập chéo tenant trong API và admin console |
| Incident support | Có kênh khẩn cấp và quy trình cung cấp evidence |

Các giá trị thời gian và ngưỡng phải được tổ chức xác định theo rủi ro. Không dùng các con số minh họa làm chuẩn mặc định cho mọi triển khai.

## 9. Scorecard đánh giá nhà cung cấp

Có thể dùng thang điểm 0–5:

- **0:** Không có khả năng hoặc không cung cấp bằng chứng.
- **1:** Có tuyên bố nhưng chưa có bằng chứng đủ.
- **2:** Có chức năng cơ bản, còn khoảng trống đáng kể.
- **3:** Đáp ứng yêu cầu, có tài liệu và bằng chứng phù hợp.
- **4:** Kiểm soát tốt, có test độc lập và vận hành đo lường được.
- **5:** Kiểm soát trưởng thành, bằng chứng cập nhật, có kiểm thử và cải tiến liên tục.

Ví dụ trọng số dưới đây chỉ là điểm khởi đầu:

| Nhóm đánh giá | Trọng số gợi ý |
| --- | ---: |
| Token security, key management và revocation | 25% |
| Authentication, account lifecycle và privileged access | 15% |
| Tenant isolation, API security và audit | 15% |
| Privacy, data processing và compliance evidence | 15% |
| Availability, resilience và incident response | 15% |
| Integration, portability và exit strategy | 10% |
| Support, documentation và product governance | 5% |

Điểm tổng có thể tính bằng tổng của điểm nhóm nhân trọng số. Tuy nhiên, không để điểm cao ở nhóm dễ bù cho một lỗ hổng nghiêm trọng ở nhóm token/key. Nên đặt **hard gate**: ví dụ không có khả năng revoke credential quan trọng, không kiểm soát signing key, không bảo đảm tenant isolation hoặc không có thông báo sự cố phù hợp thì không đạt, dù điểm tổng cao.

### Mẫu scorecard

~~~yaml
providerAssessment:
  provider: example-identity-vendor
  service: oidc-authorization-server
  assessmentDate: 2026-11-23
  environment: proof-of-concept
  groups:
    tokenSecurity:
      weight: 0.25
      score: null
      evidence: []
      gaps: []
    identityLifecycle:
      weight: 0.15
      score: null
      evidence: []
      gaps: []
    tenantAndApiSecurity:
      weight: 0.15
      score: null
      evidence: []
      gaps: []
    privacyAndCompliance:
      weight: 0.15
      score: null
      evidence: []
      gaps: []
    resilienceAndIncident:
      weight: 0.15
      score: null
      evidence: []
      gaps: []
    portability:
      weight: 0.10
      score: null
      evidence: []
      gaps: []
    supportAndGovernance:
      weight: 0.05
      score: null
      evidence: []
      gaps: []
  hardGates:
    signingKeyControl: NOT_ASSESSED
    revocationSla: NOT_ASSESSED
    tenantIsolation: NOT_ASSESSED
    incidentNotification: NOT_ASSESSED
  decision: PENDING
~~~

Không điền điểm dựa trên marketing. Mỗi điểm phải liên kết tới bằng chứng cụ thể: tài liệu, report, kết quả PoC, cấu hình quan sát được hoặc điều khoản hợp đồng. Ghi rõ bằng chứng đã kiểm tra độc lập hay chỉ do vendor tự khai.

## 10. Hợp đồng, SLA và trách nhiệm chung

Trước khi ký, chuyển các yêu cầu quan trọng thành điều khoản có thể đo lường:

- Endpoint, protocol, feature và phiên bản được cam kết hỗ trợ.
- SLA riêng cho token endpoint, JWKS, introspection và revocation.
- Thời gian thông báo sự cố, kênh escalation và nội dung evidence.
- Thời hạn vá lỗ hổng theo mức độ nghiêm trọng và quy trình disclosure.
- Thông báo thay đổi API, claim, signing algorithm, issuer, key và deprecation.
- Quyền audit hoặc nhận assurance report định kỳ.
- DPA, subprocessor, data residency, retention và deletion.
- Quyền sở hữu dữ liệu, khả năng export và hỗ trợ chuyển đổi.
- Trách nhiệm khi vendor hoặc tổ chức cấu hình sai.
- Quy trình chấm dứt dịch vụ, thu hồi credential và xác minh xóa dữ liệu.

Phân định trách nhiệm shared responsibility. Vendor có thể bảo vệ hạ tầng và authorization server, nhưng tổ chức vẫn chịu trách nhiệm cấu hình redirect URI, audience, scope, role mapping, resource server validation, tenant authorization và cách lưu token ở client.

## 11. Exit strategy và khả năng chuyển đổi

Phụ thuộc identity vendor có thể tạo lock-in vì user ID, group, policy, federation, consent, custom claims và ứng dụng đã tích hợp sâu. Đánh giá trước:

- Có thể export user, group, client metadata, federation config và audit log ở định dạng có cấu trúc không?
- Có thể ánh xạ subject ổn định sang issuer mới không?
- Có thể chuyển password credential không, hay cần người dùng đặt lại mật khẩu?
- Passkey/WebAuthn credential có thể di chuyển theo tiêu chuẩn và policy bảo mật không?
- Consent/grant history có thể export mà vẫn giữ audit trail không?
- Ứng dụng có hỗ trợ nhiều issuer trong giai đoạn chuyển đổi không?
- Có kế hoạch chuyển JWKS, issuer, redirect URI và audience mà không chấp nhận token cũ ngoài ý muốn không?
- Khi chấm dứt hợp đồng, vendor xóa dữ liệu chính, backup và subprocessor theo lịch nào?

Không giả định mọi credential đều có thể export. Private key không export có thể là một kiểm soát bảo mật hợp lý; password hash hoặc passkey có thể bị giới hạn di chuyển. Exit plan cần xác định cách tái xác thực hoặc onboarding lại người dùng thay vì làm suy yếu bảo mật để đạt portability.

Một kế hoạch migration nên có giai đoạn chạy song song, mapping subject, kiểm thử federation, chuyển client, xử lý token đang còn hiệu lực, thông báo người dùng và tiêu chí rollback. Token do issuer cũ phát hành phải được chấp nhận hoặc từ chối theo một thời hạn và policy có chủ đích.

## 12. Những dấu hiệu cảnh báo

1. Vendor không giải thích được ai kiểm soát private signing key hoặc không có quy trình emergency revoke.
2. Không có bằng chứng về refresh token rotation/reuse detection dù use case yêu cầu.
3. Không thể giới hạn audience hoặc scope theo resource/client.
4. Revoke endpoint trả thành công nhưng không mô tả trạng thái ở resource server và cache.
5. Không cung cấp audit log cho thay đổi key, client, admin role hoặc policy.
6. Tenant administrator có thể xem dữ liệu hoặc cấu hình của tenant khác.
7. Chỉ đưa chứng nhận công ty mẹ mà không chứng minh phạm vi dịch vụ/region được mua.
8. Không có thời hạn thông báo sự cố hoặc kênh liên lạc khẩn cấp.
9. Không công bố subprocessor, vị trí xử lý dữ liệu hoặc retention.
10. Không có export/exit plan hoặc yêu cầu phí/điều kiện khiến tổ chức không thể rời dịch vụ.
11. Marketing khẳng định “compliant” nhưng không chỉ ra tiêu chuẩn, phạm vi, kỳ đánh giá và bằng chứng.
12. Không cho phép kiểm thử các hành vi bảo mật cơ bản trong sandbox và không cung cấp báo cáo độc lập thay thế.

Một red flag không tự động có nghĩa vendor chắc chắn không an toàn. Nó là lý do cần làm rõ, yêu cầu bằng chứng, áp điều kiện hợp đồng hoặc loại khỏi shortlist nếu rủi ro không thể chấp nhận.

## 13. Checklist quyết định

- [ ] Đã xác định loại dịch vụ identity và ranh giới trách nhiệm vendor/tổ chức.
- [ ] OAuth/OIDC flow phù hợp với loại client và use case.
- [ ] Issuer, audience, scope, claims, expiration và JWKS có contract rõ.
- [ ] Signing key được bảo vệ, audit, rotate và emergency revoke.
- [ ] Refresh token rotation, reuse detection, session revoke và grant revoke được kiểm chứng.
- [ ] MFA, account recovery, provisioning và privileged access đáp ứng yêu cầu.
- [ ] Tenant isolation được kiểm tra trên API, admin console, log và support process.
- [ ] Có assurance report, penetration test, vulnerability SLA và phạm vi chứng nhận rõ.
- [ ] DPA, subprocessor, residency, retention và deletion đã được xem xét.
- [ ] SLA endpoint, DR, incident notification và escalation được định nghĩa.
- [ ] PoC có test token, key, revoke, failure mode, audit và tenant boundary.
- [ ] Scorecard dựa trên evidence và có hard gate cho rủi ro nghiêm trọng.
- [ ] Hợp đồng quy định trách nhiệm shared responsibility và quyền audit.
- [ ] Có export, migration, issuer transition và exit strategy.

## Ghi nhớ

**Đánh giá nhà cung cấp identity là đánh giá cả khả năng kiểm soát danh tính, token, khóa và vận hành trong suốt vòng đời hợp tác.** Xác minh giao thức bằng PoC, kiểm tra bằng chứng độc lập, đo revocation và failure behavior, xem xét quyền riêng tư/hợp đồng, rồi lập exit strategy trước khi phụ thuộc sâu. Chọn nhà cung cấp dựa trên bằng chứng phù hợp với rủi ro và kiến trúc thực tế, không dựa riêng vào danh sách tính năng hoặc logo chứng nhận.

### Tài liệu tham khảo

- IETF RFC 9700 — Best Current Practice for OAuth 2.0 Security: https://www.rfc-editor.org/rfc/rfc9700
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html
- IETF RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009
- IETF RFC 7662 — OAuth 2.0 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
- IETF RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens: https://www.rfc-editor.org/rfc/rfc8705
- IETF RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP): https://www.rfc-editor.org/rfc/rfc9449
- NIST SP 800-63-4 — Digital Identity Guidelines: https://pages.nist.gov/800-63-4/
- ISO/IEC 27001 — Information security management systems: https://www.iso.org/standard/27001
- AICPA SOC 2 resources: https://www.aicpa-cima.com/resources/landing/system-and-organization-controls-soc-suite-of-services
