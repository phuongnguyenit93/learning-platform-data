# Review secret usage: đánh giá thiết kế sử dụng secrets bằng bằng chứng

Một nhóm phát triển đưa dịch vụ xuất báo cáo vào production. Mật khẩu database được lấy từ secret manager, nên trong buổi review cả nhóm kết luận “secret đã an toàn”. Tuy nhiên, credential dùng chung giữa báo cáo và analytics; pipeline CI có quyền đọc secret production để chạy smoke test; một exception ghi toàn bộ HTTP authorization header vào log; secret cache không có thời hạn; và sau khi nhân viên vận hành nghỉ việc, token của service vẫn hoạt động bình thường.

Trong tình huống này, **secret không nhất thiết bị lưu sai ở secret manager**. Các điểm yếu nằm ở cách secret **được cấp cho ai, dùng vào mục đích gì, qua ranh giới tin cậy nào, tồn tại bao lâu, có tạo bản sao không và được vô hiệu hóa hiệu lực ra sao**.

**Review secret usage** là hoạt động security design review nhằm đánh giá **toàn bộ cách một secret hoặc năng lực mật mã được sử dụng trong hệ thống**, từ nhu cầu nghiệp vụ, tạo/cấp phát, phân phối, lưu trữ, sử dụng, cache, logging, rotation, revoke, khôi phục tới audit. Review không dừng ở câu hỏi “có hardcode mật khẩu không” mà đòi hỏi một lập luận có bằng chứng về **đúng danh tính, đúng mục đích, đúng quyền, đúng môi trường, đúng thời hạn và không có đường sử dụng ngoài policy**.

Trong chương **Security design review** của module **SECURITY_SECURITY_ASSURANCE**, bài học đặt việc sử dụng secrets vào chương trình security assurance: xây dựng và đánh giá bằng chứng rằng hệ thống đáp ứng mục tiêu bảo mật, từ threat modeling, security requirements và controls đến kiểm thử, findings, remediation và continuous assurance.

> **Nguyên tắc cốt lõi:** Secret manager, KMS hoặc HSM là thành phần bảo vệ quan trọng, nhưng **không thay thế việc kiểm soát chủ thể được dùng secret, quyền giải mã/ký, phạm vi dữ liệu và luồng xuất hiện plaintext**. Một review đáng tin phải nối **secret purpose → trust boundary → access and usage policy → failure handling → verification → evidence → residual risk**.

## 1. Mục tiêu và đầu ra của một cuộc review

Một security design review tốt cần trả lời:

1. **Secret là gì và được dùng để làm gì?** Đó là password, API token, signing key, mTLS private key hay một credential tạm thời?
2. **Ai tạo và sở hữu?** Có owner, service, environment, approval và vòng đời rõ không?
3. **Secret xuất hiện ở đâu?** Source, build, CI, deployment, runtime, memory, logs, backup, error handling và kênh hỗ trợ?
4. **Ai có thể lấy hoặc dùng?** Quyền trực tiếp, quyền gián tiếp, inheritance, role assumption, workload identity, admin và break-glass?
5. **Secret có cần rời trust boundary không?** Có thể dùng managed signing/decryption operation, token federation hoặc secretless authentication thay vì gửi raw secret vào application?
6. **Có scope và thời hạn?** Credential theo tenant, service, environment, purpose, action, resource và TTL nào?
7. **Điều gì xảy ra khi thiếu, hết hạn, bị compromise hoặc provider lỗi?** Có fallback hardcoded/debug bypass không?
8. **Có thể rotate/revoke/retire và xác minh hiệu lực không?** Consumer, connection pool, cached token, session và bản backup được xử lý ra sao?
9. **Evidence nào hỗ trợ?** Các file thiết kế, policy versions, runtime effective permissions, tests, audit logs, inventory và findings?
10. **Còn giới hạn nào?** Legacy path, shared credentials, provider limitation, inaccessible logs hay test chưa chạy?

### 1.1. Deliverables có thể đánh giá

Một buổi review nên tạo hoặc cập nhật:

- **Secret usage inventory:** danh sách secret IDs/references, loại, purpose, owner, consumers và data classification; **không chứa secret values**.
- **Secret data-flow diagram:** luồng cấp phát, đọc, dùng, cache, log, backup, revoke và trust boundaries.
- **Threat model:** giả định attacker, khả năng truy cập CI/workload/KMS, misuse paths, blast radius.
- **Usage policy:** danh tính, quyền, resource, environment, allowed operations, TTL và denied behaviors.
- **Requirement/control mapping:** mỗi risk có requirement/control/test tương ứng.
- **Verification plan:** positive, negative, rotation, revoke, outage và runtime checks.
- **Evidence package:** tham chiếu có nguồn tới config, API policies, review records, test outputs và audit events.
- **Findings và decisions:** severity, owner, deadline, remediation, exception, residual risk và retest.
- **Approval với phạm vi:** ai chấp nhận thiết kế, assumptions nào chưa chứng minh và khi nào reassess.

**Review design chưa phải chứng nhận toàn bộ runtime.** Một architecture diagram đúng giúp đánh giá design effectiveness, nhưng vẫn cần kiểm tra implementation và operating effectiveness.

## 2. Phân biệt secret, dữ liệu nhạy cảm và cryptographic capability

### 2.1. Secret là gì?

**Secret** là giá trị mà việc tiết lộ hoặc sử dụng trái phép có thể cấp quyền truy cập, giả mạo danh tính, thực hiện phép toán nhạy cảm hoặc phá cơ chế bảo vệ. Ví dụ:

| Loại | Ví dụ | Rủi ro khi lộ hoặc bị lạm dụng |
|---|---|---|
| **Human credential** | Password, recovery code, MFA seed | Account takeover, unauthorized recovery |
| **Machine credential** | API key, OAuth client secret, DB password | Giả service, đọc/ghi dữ liệu |
| **Access artifact** | Bearer access token, refresh token, session cookie | Session hijack, token replay |
| **Private key** | TLS/mTLS key, JWT signing key, code-signing key | Giả endpoint, ký token hoặc artifact giả |
| **Symmetric crypto key** | DEK, KEK, HMAC key | Đọc bản mã, giả MAC, mở rộng blast radius |
| **Bootstrap secret** | Initial admin enrollment token, join token | Đăng ký thiết bị/workload trái phép |
| **Infrastructure credential** | Cloud access key, database account, Git deploy token | Lateral movement, control-plane compromise |
| **Webhook signing secret** | Shared key cho event integrity | Giả payload, giả nguồn phát sự kiện |
| **Certificate/credential bundle** | Keystore chứa private key và password | Khôi phục danh tính hoặc signing capability |
| **Emergency credential** | Break-glass token/credential | Truy cập đặc quyền không qua flow thường |

Một **public key, certificate public, key ID, hash của một file công khai** thường không phải secret chỉ vì tên chứa từ “key” hoặc “certificate”. Ngược lại, **access token nằm trong log** vẫn là secret ngay cả khi trông giống một chuỗi ngẫu nhiên.

### 2.2. Secret khác PII/confidential business data

Hồ sơ học viên, báo cáo tài chính và dữ liệu cá nhân có thể cần encryption và access control mạnh, nhưng không nhất thiết là **credential hoặc cryptographic secret**. Review secret usage tập trung vào những giá trị **có thể cấp/đại diện quyền** hoặc thực hiện phép toán mật mã; review data protection đánh giá bảo vệ dữ liệu nói chung. Hai loại review giao nhau tại logging, encryption, export và key custody.

### 2.3. Sở hữu khóa khác quyền sử dụng khóa

Một private key **non-exportable** trong KMS/HSM có thể không rời module, nhưng một service được cấp quyền ký JWT tùy ý vẫn có thể tạo token trái phép. Vì vậy cần phân biệt:

- **Key material exposure:** raw key có bị lấy ra không?
- **Operation misuse:** caller có thể dùng ký/giải mã/unwrap vượt policy không?
- **Business authorization:** request phép toán đã được giao quyền/nghiệp vụ phê duyệt chưa?
- **Attestation/validation scope:** bằng chứng từ module hỗ trợ điều gì; có giới hạn gì?

**Secret không lộ byte vẫn có thể bị lạm dụng qua API.** Review phải xét quyền thực hiện operation.

## 3. Scope của review và cách chọn trust boundaries

Không nên chỉ tìm chuỗi trong code. Bắt đầu từ use case và chủ thể.

Một hệ thống SaaS đa tenant có thể có:

- Browser/mobile user đăng nhập qua IdP.
- API gateway xác thực request.
- Learning service gọi database bằng workload identity hoặc credential.
- Export worker đọc object storage và gọi email provider.
- CI/CD deploy image và provision roles.
- Secret manager hoặc KMS phát short-lived credential hoặc thực hiện cryptographic operations.
- Logging/SIEM nhận telemetry.
- Backup/DR sao chép dữ liệu và lưu metadata encrypted.
- Operator/incident team dùng break-glass.

### 3.1. Data-flow diagram: secret xuất hiện ở đâu?

~~~mermaid
flowchart LR
    DEV["Developer workstation"] -->|Commit / PR| REPO["Source repository"]
    REPO --> CI["CI pipeline"]
    CI -->|Build image / manifest| REG["Artifact registry"]
    REG --> DEP["Deployment control plane"]
    ID["Workload identity / IdP"] --> BROKER["Secret manager / credential broker"]
    DEP --> APP["Application runtime"]
    APP -->|Authenticate and request| BROKER
    BROKER -->|Short-lived credential, if needed| APP
    APP -->|Use scoped credential| DB[("Database / external API")]
    APP -->|Sign or decrypt operation| KMS["KMS / HSM"]
    APP --> LOG["Logs / traces / diagnostics"]
    APP --> CACHE["Process memory / cache"]
    BROKER --> AUD["Access audit"]
    KMS --> AUD
    APP --> AUD
    BK[("Backup / snapshots")] -. "May capture config, data or ciphertext" .-> APP
~~~

**Mũi tên không đồng nghĩa secret phải được sao chép.** Ví dụ signing key có thể **chỉ tồn tại trong HSM**, còn application gửi request ký đã được authorization. Với workload federation, application có thể lấy token ngắn hạn thay vì một password dài hạn.

### 3.2. Trust boundary và câu hỏi review

| Ranh giới | Câu hỏi | Kiểm soát cần xem |
|---|---|---|
| Developer → repository | Secret có thể lọt vào commit, PR description, test fixture? | Secret scanning, review, history remediation |
| Repository → CI | CI có quyền đọc production secret không cần thiết? | OIDC federation, scoped environment, approvals |
| CI → artifact | Build có bake key vào image/layer hoặc SBOM output? | Artifact inspection, scan, runtime injection |
| Control plane → workload | Ai được sửa service account, secret mount, env và deployment? | IAM/RBAC, admission, change control |
| Workload → manager | Caller identity thực, trust channel và secret path? | Workload auth, mutual trust, policy |
| Manager → runtime | Có thật sự cần raw secret? Có cache/log không? | Dynamic credentials, TTL, protected transport, data handling |
| Workload → downstream | Credential chỉ cấp quyền đúng API/DB/resource? | Resource/action scopes, audience, tenant |
| Workload → KMS/HSM | Có quyền decrypt/sign/unwrap vượt nhu cầu? | Operation-based grants, business policy |
| Runtime → logs/diagnostics | Password/token/header/stack/heap có lộ? | Redaction, schema allowlist, observability tests |
| Runtime → backups/DR | Config, key material hoặc credentials có được sao chép? | Backup scope, retention, encrypt/key access |
| Operations → production | Support/debug/break-glass có thể xem secret? | PAM, approval, auditable procedures |

### 3.3. Không bỏ qua “đường phụ”

Nguồn lộ secret thường nằm ngoài primary API: build artifacts, container image layer, support bundle, error tracking attachment, chat message, CI console, terminal history, process arguments, crash dump, telemetry SDK, object export, local cache hoặc ticket.

Một dòng secret scanner báo **zero findings** không chứng minh những đường runtime nói trên an toàn. Cần lập inventory theo **producers, stores, transports, consumers và sinks**.

## 4. Threat modeling cho secret usage

### 4.1. Asset, actor và mục tiêu của attacker

Những actor cần xét:

- Internet attacker cố lấy token qua lỗ hổng web.
- Malicious/compromised insider với quyền đọc repo, log hoặc production shell.
- Compromised CI runner hoặc supply-chain dependency.
- Compromised workload đọc process environment/memory.
- Third-party integration bị xâm nhập.
- Admin có quyền sửa IAM/KMS policies.
- Attacker có quyền đọc backup/snapshot/object storage.
- Người sở hữu token hợp lệ nhưng vượt mục đích nghiệp vụ.

Risk scenarios nên đi cùng **đường truy cập và tác động cụ thể**, không chỉ đặt nhãn “leak credentials”.

### 4.2. Threat scenarios theo STRIDE

| Nhóm | Kịch bản | Tác động | Hướng control |
|---|---|---|---|
| **Spoofing** | Token bị sao chép từ log và dùng giả service | Truy cập trái phép | Token scope/audience/TTL, redaction, sender-constraining khi phù hợp |
| **Tampering** | CI sửa secret ref sang key của môi trường khác | Dùng key sai hoặc giải mã vượt scope | Approved references, deployment policy, reviewer |
| **Repudiation** | Nhiều worker chia sẻ credential | Không truy nguồn hành động | Per-workload identities, audit correlation |
| **Information disclosure** | Secret nằm trong error event, heap dump, debug endpoint | Lộ credential/key | Minimize secret copies, restricted diagnostics |
| **Denial of service** | KMS lỗi, app fallback key cũ hoặc dừng hàng loạt | Mất confidentiality hoặc availability | HA/DR, fail-safe, runbook |
| **Elevation of privilege** | Service có quyền sửa IAM/KMS grant của chính nó | Tự mở rộng quyền | SoD, restricted control plane, approval |

### 4.3. Risk scenario có thể kiểm chứng

**RISK-SECRET-01:** Một developer có quyền xem CI logs nhưng không có quyền database production có thể thu hồi credential production nếu build ghi kết quả secret retrieval lên console.

- **Threat boundary:** CI runner → CI log service → nhóm developer.
- **Asset:** production DB credential.
- **Precondition:** runner có quyền đọc credential hoặc artifact chứa credential.
- **Impact:** dữ liệu production bị đọc/sửa ngoài policy.
- **Requirement:** CI build thông thường không được cấp quyền đọc production DB secret; nếu deployment cần credential thì dùng runtime workload identity/dynamic secret injection; log phải redact theo schema.
- **Test:** chạy synthetic secret canary qua CI, kiểm output/artifacts; test role của runner không đọc được secret production.
- **Evidence:** CI IAM policies, runtime run record, negative access test, logs đã redacted.
- **Residual risk:** privileged CI admin vẫn có thể sửa pipeline; cần quản trị pipeline và approvals.

## 5. Secret lifecycle: từng giai đoạn đều là điểm review

~~~mermaid
flowchart TD
    A["Business purpose / asset & risk"] --> B["Approve secret type and owner"]
    B --> C["Generate / issue / enroll"]
    C --> D["Store under protected custody"]
    D --> E["Distribute or allow cryptographic operation"]
    E --> F["Consume with least privilege"]
    F --> G["Observe usage without logging value"]
    G --> H{"Rotate / expire / incident / role change?"}
    H -- "No" --> F
    H -- "Yes" --> I["Rotate / replace or revoke"]
    I --> J["Invalidate consumers, sessions and caches"]
    J --> K["Retest effective access and availability"]
    K --> L["Retire / destroy or retain as authorized"]
    L --> M["Evidence, audit and reassessment"]
~~~

### 5.1. Generation/issuance

- Secret có được sinh bằng nguồn ngẫu nhiên phù hợp và công cụ được phê duyệt không?
- Có sử dụng key/algorithm đúng crypto policy?
- Có secret mẫu/default chia sẻ giữa khách hàng không?
- Credential có gắn owner, environment, service identity và purpose không?
- Initial distribution có được bảo vệ tránh email/chat/plaintext ticket không?
- Key/credential có hạn sử dụng hoặc cách revoke rõ không?
- Có thể thay long-lived secret bằng workload identity hoặc federation không?

### 5.2. Storage/custody

- Tồn tại bản sao trong source control, image, CI var, secret manager, file, environment, memory, backup, logs?
- Bản sao nào là source of truth?
- Ai có quyền đọc raw value, ai chỉ có quyền gọi operation?
- Khóa dùng để bảo vệ secret store có được quản lý tách khỏi dữ liệu và account?
- Có audit cho read, issue, rotate, revoke và policy change không?
- Có cần encryption at rest/HA/replication/backup cho secret store không?

### 5.3. Distribution/consumption

- Phân phối secret qua kênh nào? TLS, platform mount, IPC, SDK, sidecar, credential broker?
- App có thật sự cần raw key/password không?
- Secret có đi vào một process có trust boundary rộng hơn không?
- Có copy sang child process, argv, filesystem tạm hoặc crash dump?
- Consumer có xử lý expiry/revocation và rotation trong connection pool?
- Có secret được dùng cho nhiều audience/tenant/purpose không?

### 5.4. Rotation/revocation/destruction

- Có trigger định kỳ hoặc theo compromise, vendor change, privilege change, employee exit?
- Có phương thức chuyển đổi consumers không gây downtime ngoài mức cho phép?
- Old credential có thực sự bị reject sau thời hạn?
- Các session/token/caches/signed URLs đang tồn tại có bị thu hồi hoặc hết hạn trong mục tiêu?
- Backup của secret/key có còn cần thiết để restore dữ liệu lịch sử?
- Có evidence chứng minh revoke hiệu lực, không chỉ hiển thị trạng thái “disabled”?

## 6. Secret inventory: cách ghi mà không tạo thêm rò rỉ

Một inventory có thể có:

| Field | Mục đích |
|---|---|
| **Secret reference** | Mã logic hoặc path an toàn, không chứa giá trị secret |
| **Secret type** | API token, DB credential, private key, HMAC key, signing capability |
| **Business purpose** | Tại sao cần dùng; action nào được phép |
| **Producer / issuer** | Nguồn cấp, đăng ký hoặc tạo |
| **Owner / custodian** | Người chịu trách nhiệm nghiệp vụ và key custody |
| **Environment** | Dev/test/staging/prod và regional/tenant boundaries |
| **Consumers** | Các workload/human identities có quyền dùng |
| **Allowed operations** | Get value, sign, decrypt, unwrap, authenticate, rotate |
| **Scope & audience** | Resource, API, tenant, database/schema, token audience |
| **TTL/lifetime** | Expiry, rotation, grace/overlap policy |
| **Storage / transit** | Vault/KMS/HSM, mount, cache, env, process |
| **Recovery** | Backup/restore/DR cần thiết và owner |
| **Audit / monitoring** | Decision logs, anomalous use, policy changes |
| **Exception / finding** | Bypass tạm, residual risk và deadline |
| **Verification** | Test IDs, evidence references, ngày/phiên bản |

### 6.1. Không đưa raw values vào spreadsheet hoặc ticket

Nếu review yêu cầu “gửi password để security kiểm tra”, đó là dấu hiệu review đang tạo thêm copy nguy hiểm. Thay bằng:

- Secret ID/alias và policy.
- Effective permission report.
- Metadata được redact.
- Attestation hoặc kết quả crypto operation hợp lệ.
- Controlled negative tests.
- Audit event có actor, time, keyRef, outcome nhưng không có secret/plaintext.

Một review về mật mã không nên biến người đánh giá thành một consumer không cần thiết của raw secret.

### 6.2. Kiểm tra completeness của inventory

So sánh từ nhiều nguồn:
- Cloud IAM, secret manager/KMS/HSM resource listings.
- Kubernetes Secret và workload mounts/references.
- CI/CD variables, environments, service connections.
- Application config và outbound dependencies.
- IdP/OAuth clients, API key portals.
- Source/container/image scanning.
- Runtime traces, network access, KMS audit.
- Incident records, expired credentials, backup inventory.

Một secret không có trong inventory vẫn có thể được sử dụng. **Không dùng tỷ lệ “100% inventory” nếu chưa kiểm population từ các nguồn độc lập.**

## 7. Có thể loại bỏ secret lâu dài không?

Một phần quan trọng của security design review là hỏi **“có cần tạo ra credential tĩnh ngay từ đầu không?”**.

### 7.1. Ưu tiên thay static secret khi khả thi

Ví dụ:
- Dùng **workload identity federation** để lấy credentials ngắn hạn thay vì lưu cloud access key dài hạn.
- Dùng identity của service mesh/mTLS certificate có rotation quản lý thay vì shared password giữa microservices.
- Dùng managed identity cho database nếu nền tảng hỗ trợ.
- Gọi HSM/KMS signing API thay vì export private signing key vào app.
- Sử dụng OAuth token đúng audience/scope/expiry thay vì một API key chung toàn tổ chức.
- Dùng temporary presigned resource access với scope và lifetime phù hợp thay vì credentials storage dài hạn.

**Secretless** trong thực hành thường có nghĩa **ứng dụng không giữ secret tĩnh lâu dài**. Nó không có nghĩa hệ thống không còn keys, trust anchors, tokens hoặc credentials ở mọi tầng. Quyền dùng identity broker, khả năng mint token và key controls vẫn là risk cần đánh giá.

### 7.2. Khi static secret chưa thể loại bỏ

Một vendor API có thể chỉ hỗ trợ một API key dài hạn. Khi đó:
- Tách key theo environment và mục đích khi provider cho phép.
- Hạn chế scopes/audience/IP/source nếu provider hỗ trợ và có assurance thực tế.
- Cấp key vào đúng workload, không shared giữa các hệ thống.
- Store trong managed secret store; không bake vào image.
- Rotate với kế hoạch cutover, rollback và audit.
- Monitor usage/anomaly và kiểm tra revocation.
- Lập exception/risk acceptance nếu không thể đạt baseline ngắn hạn.

Không “giấu” key bằng base64, encoding hoặc obfuscation rồi tuyên bố đã bảo vệ. Encoding không tạo confidentiality.

## 8. Review nguồn tạo và cấp phát secret

### 8.1. Randomness và bootstrap

Secrets như signing key, encryption key, session key hoặc random API token cần nguồn sinh phù hợp với security requirements. Cần review:

- Key generation qua approved module/provider.
- SecureRandom/CSPRNG và giới hạn nền tảng.
- Không dùng random seed cố định, username, timestamp hoặc UUID từ nguồn không phù hợp để thay key entropy.
- Key size, algorithm và mode theo crypto standard.
- Certificate/key enrollment có authentication/approval.
- Bootstrap token đủ hạn, single-use khi phù hợp và không tái sử dụng giữa tenants.
- Quy trình phục hồi/re-provision khi secret mất hoặc bị compromise.

### 8.2. Self-service secret creation

Nếu mỗi developer có quyền tạo token production, cần xem:
- Ai có thể tạo, rotate, revoke?
- Có mandatory owner/ticket và expiration không?
- Có thể tự tăng scope hoặc tạo token impersonating admin không?
- Issuer có audit và alert không?
- Có thể tạo credential ngoài inventory không?
- Consumer có dùng key ngay sau khi bị khóa hoặc pending approval không?

### 8.3. Third-party issuer

Với bên thứ ba:
- Kênh cấp key có bảo vệ không?
- Có key test/sandbox và production riêng không?
- Key có granular scopes và expiration không?
- Có rotation/revoke API, webhook/alert và recovery flow không?
- Bên thứ ba có shared administrator accounts không?
- Incident ở provider có cơ chế thông báo và revoke hiệu lực không?

Không suy diễn vendor có đủ năng lực chỉ vì có trang “API Keys”. Cần kiểm docs/cấu hình/negative tests của integration cụ thể khi kiểm tra implementation.

## 9. Secret manager, KMS và HSM: chọn đúng chức năng

| Thành phần | Thường hỗ trợ | Cần tránh hiểu lầm |
|---|---|---|
| **Secret manager** | Lưu/phát credential, versioning, rotation, IAM, audit | Có vault không đồng nghĩa consumer dùng secret đúng scope |
| **KMS** | Key lifecycle, policy, cryptographic operations, wrapping | Quyền decrypt/sign rộng vẫn tạo misuse |
| **HSM** | Hardware cryptographic boundary, non-exportable keys theo profile | Không tự kiểm business authorization |
| **Workload identity broker** | Xác thực workload và cấp short-lived credential | Không loại bỏ nhu cầu kiểm issuer/audience/TTL |
| **Certificate authority / PKI** | Cấp, renew, revoke chứng thư | Chứng thư hợp lệ không chứng minh endpoint không bị chiếm |
| **Service mesh** | TLS identity, communication policy, rotation theo implementation | mTLS không thay resource-level authorization |
| **CI/CD secret store** | Giữ credential dùng trong pipeline | CI là control plane đặc quyền; cần phân tách environment và workflow |
| **Encrypted configuration** | Mã hóa config trên repo/at rest | CI/runtime vẫn cần key giải mã và permission phù hợp |

### 9.1. Đúng mô hình shared responsibility

Managed service có thể đảm bảo một phần encryption, HA hoặc key custody, nhưng tổ chức vẫn chịu trách nhiệm về:
- Grants và IAM.
- Secret path naming và classification.
- Rotation schedule và operator workflow.
- Identity trust/issuance.
- Resource authorization.
- Audit access và incident response.
- Insecure copies sau khi secret được retrieval.
- Backup/retention/DR theo phạm vi.

### 9.2. Secret store encryption không ngăn read-with-permission

Nếu một service có quyền read raw DB password, attacker kiểm soát service có thể thử đọc password qua API secret store. Kẻ tấn công cũng có thể **dùng** signing/decrypt API dù key không được export nếu operation không có business policy. Vì vậy cần **least privilege và control plane hardening** tại cả provider và consumer.

## 10. Review quyền: danh tính, resource, action và purpose

### 10.1. Effective permissions quan trọng hơn role name

Review cần xem:
- Direct roles, nested groups, inherited policies.
- Cloud account/project/organization scope.
- Service account association và impersonation.
- Kubernetes create/patch pod, exec và secret mount.
- CI runners, GitHub/GitLab environment/token permissions.
- KMS decrypt/sign/unwrap vs key-admin/change-policy operations.
- Database roles và downstream permissions.
- Break-glass và emergency accounts.
- Delegated tokens, cached credentials và mTLS identities.
- Rights to change **who can read/use secret**, không chỉ direct read.

Một actor không có quyền đọc key trực tiếp nhưng có quyền thay deployment để gắn service account được cấp key-use có thể có đường leo thang quyền.

### 10.2. Separation of duties

Ví dụ:
- App owner đề xuất sử dụng key.
- Security/key custodian phê duyệt purpose và crypto constraints theo policy.
- IAM/platform owner triển khai grants.
- Independent reviewer xác minh effective permissions.
- Auditor đọc logs/evidence mà không có raw key.
- Break-glass được giám sát và hậu kiểm.

Không bắt mọi request low risk phải có nhiều chữ ký thủ công. Phân tách trách nhiệm **theo sensitivity của secret và tác động khi misuse**, có approval có thể chứng minh.

### 10.3. Review quyền của operations, không chỉ key retrieval

Một crypto service có thể có các operation:
- encrypt, decrypt.
- sign, verify.
- wrap, unwrap.
- generate/import/rotate.
- disable/destroy.
- grant/revoke permission.
- audit/configure logging.

Cần kiểm **operation allowlist, key/purpose scope, environment, caller identity, condition và approval**. Ví dụ signing service cấp quyền sign arbitrary JWT payload cho workload không được phép có thể dẫn tới privilege escalation.

## 11. Review phân phối, injection và cache secret

### 11.1. Các cách đưa secret vào workload

| Cách | Ưu điểm | Rủi ro/câu hỏi cần review |
|---|---|---|
| **Environment variable** | Tích hợp đơn giản | Có thể lộ qua diagnostics, process inspection, crash dump, logs, child processes; rotation khó tùy ứng dụng |
| **Mounted file/volume** | Tách khỏi command-line và cấu hình application | File permission, mount scope, lifecycle, backup, token cleanup, watcher/rotation |
| **Runtime secret retrieval SDK** | Dễ scope theo identity và TTL | App cầm raw value, memory/cache, retries/logging và outage |
| **Sidecar/agent** | Có thể broker credential hoặc rotation | IPC/loopback boundary, workload isolation và sidecar permissions |
| **Brokered session credential** | Giảm long-lived secret | Token/session issuance, audience, replay, renew/revoke |
| **KMS/HSM operation API** | Không cần export raw private key | Operation misuse, IAM, availability, audit |
| **CI pipeline injection** | Có thể dùng cho signing/deploy | Rủi ro runner trust, PR permissions, artifacts và logs |

**Không có kênh nào tự an toàn trong mọi kiến trúc.** Một secret mount file readonly vẫn có thể bị đọc bởi process có quyền mount; environment variables cũng có thể phù hợp ở use case giới hạn nếu threat model và controls đáp ứng.

### 11.2. Memory và process boundary

Đánh giá:
- Secret được giữ plaintext trong process bao lâu?
- Có bản sao trong String, StringBuilder, JSON mapper, exception, cache và HTTP headers?
- Có được đưa vào command-line arguments hoặc process environment do child process kế thừa?
- Có core dump, heap dump, profiler, debug endpoint và support bundle không?
- Có các cơ chế memory hygiene phù hợp môi trường không?
- Một process bị chiếm có thể gọi API decrypt/sign/secret manager bao lâu?
- TTL và lease có enforcement server-side hay chỉ là biến trong app?

Trong Java, **String bất biến và không thể chủ động xóa nội dung khỏi bộ nhớ theo cách tin cậy**. Dùng char[]/byte[] có thể giúp xóa một bản sao trong ứng dụng, nhưng **không bảo đảm xóa mọi bản copy trong JVM, provider, HTTP library hoặc OS**. Review nên ưu tiên **không đưa raw secret vào process khi không cần**, hạn chế thời gian và quyền, tránh log và dùng key handles/managed operations.

### 11.3. Cache không được thành credential vĩnh viễn

Nếu consumer cache secret:
- TTL có phù hợp rotation/revocation objective?
- Cache có key theo tenant, environment, purpose, secret version?
- Có thể invalidate khi provider đổi version hoặc phát compromise event không?
- Connection pool có dùng credential cũ sau rotate không?
- Không chạy lại provider có tự fallback sang secret cũ quá hạn không?
- Secret có leak vào metrics, debug cache dump hay persisted cache không?
- Circuit breaker/outage mode có fail-safe không?

**Cache hit** không đồng nghĩa secret còn được phép sử dụng. Đặc biệt với các operation nhạy cảm, server/provider phải kiểm trạng thái revocation tại điểm thực thi theo control đã chọn.

## 12. Review secret exposure qua log, exception, metrics và trace

### 12.1. Các nguồn lộ phổ biến

- Request/response logging middleware ghi Authorization, Cookie, X-API-Key.
- HTTP debugging bật logging đầy đủ headers/body.
- Exception chứa connection string, JDBC URL hoặc raw config.
- Structured log serialization của config object có password field.
- Trace spans ghi header, query string chứa token hoặc credential.
- CI console in environment, secret output hoặc command có tham số.
- Metrics label có API key, token hoặc user-scoped secrets.
- Error reporting SaaS thu heap/context và body request.
- Audit event ghi raw secret thay vì keyRef/actor/outcome.
- Support ticket hoặc runbook hướng dẫn dán secret để xử lý sự cố.

### 12.2. Log secret usage đúng cách

Một audit event nên ghi:
- Request/correlation ID.
- Verified workload identity và environment.
- Secret **reference** hoặc key ID, không phải key/plaintext.
- Operation name (read, sign, decrypt, issue, rotate, revoke).
- Resource/purpose/scope.
- Decision và result code.
- Timestamp và policy version.
- Evidence source/trace ID đủ dùng cho điều tra.

Không cần ghi:
- Raw token/password/private key.
- Raw sensitive request payload.
- Entire HTTP authorization header.
- Full signed message nếu nó chứa PII ngoài yêu cầu audit.
- Secrets in query parameters hoặc exception chains.

### 12.3. Redaction cần kiểm thử, không chỉ “bật mask”

Mỗi công cụ logging/observability có điểm vào khác nhau. Masking một chuỗi trong CI UI **không chứng minh** secret không có trong artifacts, raw log exports, traces hoặc các payload biến đổi/encoded. Review nên sử dụng **synthetic secret canary** và kiểm các output thuộc scope, không sử dụng credential production thật để thử.

### 12.4. Secret scanner và giới hạn

Secret scanning giúp phát hiện patterns/tokens, nhưng có:
- False positive từ chuỗi test.
- False negative với credential tự định dạng hoặc đã transform.
- Lịch sử Git/commit trước đó vẫn chứa secret dù code hiện tại đã xóa.
- Scanner không biết credential có hoạt động hoặc đúng scope không.
- Một token đã bị publish cần **revoke/rotate và điều tra exposure**, không chỉ xóa dòng source.

**Không bao giờ kết luận an toàn chỉ từ số lượng scanner findings bằng 0.**


## 13. Review secrets trong CI/CD và software supply chain

Pipeline thường là một **control plane** có quyền build, publish và deploy. Secret dùng trong pipeline có thể gây tác động rộng hơn secret của một instance runtime.

### 13.1. Các đường tiết lộ cần tìm

- Secret được lưu trực tiếp trong pipeline YAML, shell script, test fixture hoặc Git history.
- Workflow chạy từ pull request không đáng tin nhưng có quyền đọc secrets.
- Runner dùng chung workspace/cache giữa jobs có trust level khác nhau.
- Build output ghi môi trường hoặc dòng command chứa token.
- Docker build ARG hoặc COPY đưa credential vào image layer/history.
- CI artifact, test report, coverage output, SBOM hoặc diagnostic archive chứa secret.
- Deployment job dùng quyền admin cloud toàn account để deploy một service nhỏ.
- Pipeline dùng personal access token của nhân viên thay vì service/workload identity.
- Định danh runner bị giả hoặc federation trust quá rộng cho mọi branch/repository.
- Environment approval bị tắt hoặc người tạo change tự phê duyệt.

### 13.2. CI identity và release security

Đối với workload federation/OIDC trong CI, review cần xác minh:
- Issuer được tin cậy và audience đúng service cung cấp credentials.
- Claims về repository, branch/tag, workflow/environment đủ giới hạn theo policy.
- Token ngắn hạn, renew/revoke được quản lý.
- PR từ nguồn không tin cậy không được tự lấy production role.
- IAM role chỉ cho phép đúng artifact registry, deployment target và resources.
- Không có trust policy wildcard cho mọi repository/project ngoài phạm vi.
- Audit liên kết action với commit, run ID, reviewer và environment.
- Build job và deploy job có danh tính/quyền tách biệt nếu threat model yêu cầu.

**OIDC federation giảm nhu cầu static cloud key**, nhưng nếu trust policy sai thì attacker có thể đổi một CI claim thành quyền production. Assurance phải kiểm tra **effective trust policy và negative tests**, không chỉ có biểu tượng OIDC trong sơ đồ.

### 13.3. Negative tests cho pipeline

- PR từ fork không được đọc deploy secret.
- Branch không được duyệt không assume được prod role.
- Build image không chứa key trong layers hoặc metadata.
- Shell trace/debug không in header/token.
- Developer có quyền đọc pipeline logs không được gọi KMS decrypt production.
- Pipeline chỉ được dùng artifact signing key cho đúng action, repository và release workflow.
- Revoke CI credential được xác minh ở job còn đang chạy hoặc token còn hiệu lực theo chính sách.

## 14. Review secret usage trong Kubernetes, container và cloud

### 14.1. Kubernetes Secret không phải lời bảo đảm cuối cùng

Một resource kiểu Kubernetes Secret là đối tượng được control plane quản lý. Nó **không tự động chứng minh** rằng:
- Dữ liệu mã hóa đúng ở etcd/backup theo yêu cầu.
- Mọi pod không được đọc Secret.
- Người có quyền tạo pod/exec không thể sử dụng service account hay mount Secret.
- Secret không xuất hiện dưới dạng environment trong process.
- Ứng dụng nạp được secret đã rotate mà không restart.
- Audit không ghi secret hoặc CRD/controller không tạo copy ngoài kiểm soát.

Việc **base64-encode** dữ liệu Secret trong manifest không phải encryption; đánh giá at-rest protection phải dựa vào cấu hình thực tế của cluster và provider.

### 14.2. Pod và runtime service account

Review những điểm sau:
- Workload có service account riêng và owner không?
- Service account có cần gọi Kubernetes API không? Nếu không, cân nhắc tắt token automount.
- Ai được create/patch Deployment, Pod, ServiceAccount, RoleBinding, Secret?
- Pod có thể mount secret của workload khác không?
- Admission policy có chặn privileged/hostPath/capabilities không cần thiết?
- Secret volume có permissions phù hợp, không bị copy vào image hoặc persistent disk?
- Network policy hạn chế kết nối đến secret provider/metadata service theo mô hình thực tế?
- Debug/exec/ephemeral container permissions có tạo khả năng lấy secret không?
- Sidecar có quyền rộng hơn workload chính không?
- CSI/provider rotation có được consumer xử lý hay chỉ thay file?

### 14.3. Ví dụ manifest minh họa

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: export-worker
  namespace: learning-prod
spec:
  replicas: 2
  selector:
    matchLabels:
      app: export-worker
  template:
    metadata:
      labels:
        app: export-worker
    spec:
      serviceAccountName: export-worker
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: export-worker
          image: registry.example.invalid/export-worker@sha256:<approved-digest>
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          env:
            - name: SIGNING_KEY_REFERENCE
              value: "learning-export-signing/prod"
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "1"
              memory: "512Mi"
~~~

Đây là **manifest minh họa**, chưa đủ để chạy production. Một key reference **không phải raw private key**; signing service, certificate, workload identity và key-use grants phải được cung cấp theo kiến trúc thực tế. Không sao chép container digest placeholder vào môi trường thật. Nếu workload cần gọi cluster API, token automount có thể phải được bật **có lý do và giới hạn quyền**, không áp dụng cứng cho mọi hệ thống.

### 14.4. Cloud IAM và KMS policy

Cần xác định quyền theo:
- Account/project/region/environment.
- Workload role và assumed role chain.
- Key aliases/versions, encryption context, permitted operations.
- Resource policies và identity policies.
- Key administrator vs key consumer.
- Cross-account grants và service-linked roles.
- Logging, revocation, emergency access.
- Ownership của instance profiles, compute metadata và CI deployment roles.

Một ứng dụng không có quyền đọc raw key nhưng được cấp decrypt với mọi ciphertext trong account vẫn có thể làm lộ dữ liệu. Dù KMS bảo vệ key material, **quyền decrypt là một quyền nhạy cảm**.

## 15. Review secret usage trong Java/Spring và ứng dụng backend

### 15.1. Anti-pattern: fallback secret mặc định

~~~java
// MINH HỌA ANTI-PATTERN: KHÔNG DÙNG TRONG PRODUCTION.
String dbPassword = System.getenv().getOrDefault(
        "DB_PASSWORD", "change-me");
~~~

Nếu config bị thiếu, ứng dụng dùng giá trị công khai hoặc được biết trước. Với credential bắt buộc, **missing/invalid phải làm ứng dụng từ chối khởi động phần chức năng nhạy cảm** hoặc áp degraded mode đã được duyệt.

### 15.2. Anti-pattern: log raw secret

~~~java
// MINH HỌA ANTI-PATTERN: KHÔNG DÙNG TRONG PRODUCTION.
String apiKey = System.getenv("VENDOR_API_KEY");
logger.info("Connecting vendor with key={}", apiKey);
~~~

Vấn đề nằm ở log sink. Dù log storage được mã hóa, nhiều nhóm có thể xem log, hoặc log có thể được export sang SIEM/third-party error reporting.

### 15.3. Anti-pattern: signing key export khi không cần

~~~text
Application reads raw private signing key from a secret store.
    → Key remains in process memory.
    → A debug dump, compromised service or support tool may obtain it.
    → Every app replica has a usable copy.

Alternative review path:
Application authenticates as scoped workload identity.
    → Trusted signing gateway verifies intent and caller.
    → Managed KMS/HSM performs signing operation.
    → Application receives signature, not raw private key.
    → Operation and policy decisions are audited.
~~~

Cách thay thế chỉ phù hợp nếu threat model, latency, availability và KMS/HSM capabilities đáp ứng. **Key non-exportability không ngăn signing API bị lạm dụng**, nên cần kiểm soát nội dung/purpose được phép ký.

### 15.4. Framework configuration và debug

Trong ứng dụng Spring/Java, review thêm:
- Configuration precedence giữa environment, application properties, remote config và secret provider.
- Actuator/diagnostic endpoint có phơi lộ config hay không.
- Bean logging/toString có in credential hay API key không.
- HTTP client logging/interceptors có log Authorization header không.
- DataSource connection pool có giữ credential cũ khi rotate không.
- JWT/OAuth libraries có cố lưu token trong cache, log/exception hay metrics không.
- Secret lookup có được thực hiện bằng identity của service, không phải shared admin token không.
- Key provider/JCE/JCA được chọn theo policy; không tắt certificate verification để “sửa” lỗi dev.
- Graceful shutdown và rotation cập nhật runtime instances như thế nào.

### 15.5. Chuỗi static secret trong source không phải vấn đề duy nhất

Một code review có thể không thấy hardcoded key nhưng vẫn gặp:
- Credential lấy từ request parameter do client điều khiển.
- Key alias do user chọn, tạo cross-tenant decrypt.
- Secret manager read trả dữ liệu của environment sai.
- Một token được dùng cho nhiều API audience.
- Signature tạo từ payload không được business approval.
- Retry mở rộng phạm vi hoặc gửi credential sang endpoint khác khi redirect.
- Error serialization ghi full config.
- Legacy integration có fallback credential.

Vì vậy, review theo **data flow và quyền thực tế**, không chỉ pattern search.

## 16. Review secrets trong API, OAuth, webhook và mTLS

### 16.1. Bearer token và OAuth credentials

- Access token có issuer, audience, scope, expiry đúng API/resource?
- Refresh token có rotation, reuse detection hoặc controls phù hợp?
- Client secret thực sự cần không? Public client không nên được xem là confidential chỉ vì nhúng secret vào app.
- Token có bị đặt trong URL/query parameter dẫn đến log/referrer/history không?
- Application có gửi bearer token qua redirect sang host khác không?
- Token có được quản lý theo principal/session, không dùng chung qua tenants không?
- Có sender-constraining như DPoP/mTLS khi threat model và platform hỗ trợ không?
- KMS/IdP operation có tách quyền quản trị token issuer khỏi consumer không?

**Bearer token possession có thể cấp quyền**; TLS chỉ bảo vệ trên đường truyền khi kênh được thiết lập, không ngăn token bị đánh cắp từ endpoint/log.

### 16.2. Webhook secret

Một webhook receiver cần:
- Xác định nguồn khóa/signing secret và scope theo provider/tenant.
- Xác minh signature/MAC theo canonical payload gốc và chính sách.
- Có timestamp/nonce/event ID chống replay khi protocol hỗ trợ.
- Có rotation/overlap window và audit.
- Không log raw signing secret hoặc payload nhạy cảm vượt nhu cầu.
- Không coi việc IP thuộc allowlist là thay thế hoàn toàn signature khi threat model yêu cầu xác thực message.

Một shared HMAC secret không chứng minh non-repudiation giữa các bên cùng giữ key. Nếu nhiều tenants dùng chung webhook secret, cần phân tích blast radius và replay/cross-tenant mapping.

### 16.3. mTLS private key

Certificate công khai thường không phải secret, nhưng **private key liên quan** cần kiểm soát. Review:
- Khóa có exportable không, lưu ở đâu, ai có thể mount/use?
- Trust domain và service identity có được xác minh không?
- Certificate issuance/renewal/revocation và key rotation.
- Credential riêng từng workload hay chia sẻ giữa replica/services?
- Sử dụng session identity có cho phép quá rộng không?
- mTLS có bảo vệ kênh đúng, nhưng application vẫn cần resource authorization.

## 17. Review secret usage cho database, cache, message broker và vendor API

### 17.1. Database credentials

Một DB password thường trở thành quyền đọc/ghi dữ liệu. Review:
- Runtime service dùng account riêng, không phải superuser.
- Quyền DB theo schema/table/operation và row/tenant context.
- Migration account tách khỏi runtime account.
- Credential không dùng chung staging/prod hoặc nhiều tenant ngoài quyết định.
- Connection pool có hỗ trợ credential rotation không?
- Password có xuất hiện trong JDBC URL, log hoặc exception không?
- DB audit liên kết operation với service/workload; có thể cần application-level actor correlation.
- Nếu dùng IAM database authentication, token expiry/renewal và connection reuse có được xử lý không?
- Incident revoke credential có tác động tới connections hiện có thế nào?

### 17.2. Caches và message brokers

- Cache credential không tự có quyền truy cập mọi keyspace.
- Queue producer/consumer có đúng topic và action (publish/consume/admin) không?
- Message payload chứa secret không cần thiết?
- DLQ và retry archive có lưu raw token/credential không?
- Consumer debug logs có in payload nhạy cảm không?
- Broker admin có quyền xem message; cần SoD/audit và retention phù hợp.
- Retry path có thể gửi credential tới một endpoint không được duyệt khi target thay đổi không?

### 17.3. Third-party API key

- Nếu provider chỉ cấp một global API key, có thể giới hạn sub-accounts hoặc purpose không?
- Redirect, proxy và HTTP client có nguy cơ gửi credential sai host không?
- Rate quota, scope, IP restrictions, callback allowlist nào thực sự được vendor enforcement?
- Khi provider compromise, có runbook rotate và đánh giá log/usage không?
- Có key dùng chung giữa nhiều deployment hoặc team làm tăng blast radius không?
- Network egress và DNS/SSRF protections hỗ trợ giới hạn nơi gửi key không?

### 17.4. Secret không được nằm trong URL

Credential trong URL/query có thể bị ghi bởi:
- Browser history.
- Reverse proxy/access logs.
- Monitoring/tracing.
- Analytics và referrer.
- Error report.
- Ticket/chat.

Ưu tiên authorization headers hoặc cơ chế chuẩn đã được review; vẫn cần bảo vệ headers/logging/redirect. Với signed URL, xem TTL, scope, operation, one-time semantics khi phù hợp và cách revoke trước expiry.

## 18. Rotation, revocation và decommission: kiểm tra quyền hiệu lực

**Rotation** là chuyển sang secret/key mới theo kế hoạch; **revocation** là chấm dứt khả năng sử dụng; **decommission** là kết thúc vòng đời credential/resource. Không được dùng các từ này như thể là một thao tác duy nhất.

### 18.1. Rotation patterns

| Pattern | Cách làm | Lưu ý |
|---|---|---|
| **Atomic switch** | Đổi secret và cập nhật consumer đồng thời | Nếu nhiều replica, có thể phát sinh downtime |
| **Dual credential overlap** | Tạm dùng old/new credential rồi loại old | Scope overlap phải có hạn, giám sát và kiểm soát |
| **Short-lived lease** | Credential tự hết hạn/renew | Dependency outage, connection pool/clock-skew handling |
| **Certificate renewal** | Cấp cert/key mới, chuyển clients, revoke cũ | Trust distribution và session termination |
| **Key versioning** | New write dùng key mới, old data decrypt có kiểm soát | Không xóa old key trước khi migration/retention được xác nhận |
| **Rewrap / re-encrypt** | Đổi KEK hoặc DEK cho dữ liệu mã hóa | Rewrap KEK không tự thay DEK/ciphertext |
| **Provider token rotation** | Tạo token mới, cập nhật consumer, revoke token cũ | Confirm key ID/audience/permissions và audit |

### 18.2. Revocation phải kiểm tra từ góc độ consumer

Một secret store hiển thị **disabled** có thể không đủ vì:
- Consumer đã cache raw secret.
- DB pool còn connection đã authenticated.
- Access token đã phát hành còn hợp lệ.
- Replica/DR giữ secret phiên bản cũ.
- Một service khác còn credential thứ hai với cùng quyền.
- Key bị disable nhưng signing session hoặc signed URL còn usable.
- Credential đã lộ cho attacker và quyền đã bị dùng trước khi revoke.

**Effective revocation** đòi hỏi xác minh bên nhận còn chấp nhận secret không, không chỉ một metadata flag.

### 18.3. Kịch bản compromise

Khi thấy secret lộ:
1. Xác định loại, owner, scope, issuer, consumers và grants.
2. Phân loại mức tác động; kích hoạt incident process khi cần.
3. Hạn chế truy cập, revoke/rotate bằng quy trình đã phê duyệt.
4. Kiểm tra logs/usage để đánh giá có bị dùng trái phép không.
5. Thu hồi sessions/tokens/connections và bản copy trong CI/log/artifacts khi khả thi.
6. Review privileges và đường leo thang liên quan.
7. Remediate nguyên nhân lộ: logging, pipeline, misconfigured IAM hoặc code path.
8. Kiểm tra service khôi phục được với credential mới.
9. Đo thời gian effective restriction và ghi residual risk.
10. Cập nhật security requirements, controls và test regression.

**Xóa secret khỏi Git HEAD không xóa được lịch sử, bản clone, artifacts hoặc secret đã bị exfiltrate.** Cần revoke/rotate trước khi chỉ tập trung dọn repository.

## 19. Hành vi fail-safe khi secret provider lỗi

| Sự kiện | Anti-pattern | Hành vi cần thiết kế và kiểm thử |
|---|---|---|
| Secret manager unavailable | Fallback sang password hardcode | Không dùng insecure fallback; queue/retry hoặc dừng action nhạy cảm |
| Signing key unavailable | Ký bằng key local mặc định | Fail safely; theo DR policy nếu có key chính thức khác |
| KMS permission denied | Thử key alias khác hoặc impersonate admin | Không nâng quyền; audit deny |
| Credential expired | Dùng bản cũ vô hạn | Renew trong hạn hoặc từ chối operation |
| Wrong environment ref | Tự chuyển sang production secret | Chặn mismatch và cảnh báo |
| Unknown secret version | Chọn version bất kỳ | Deny hoặc review; migration có kiểm soát |
| Rotation in progress | Bỏ qua kiểm tra phiên bản và dùng cả hai vô hạn | Overlap window có hạn, metrics và cutover test |
| Audit pipeline error | Tắt audit vĩnh viễn | Buffer bền vững hoặc hạn chế action có audit bắt buộc |
| TLS validation error | Tắt kiểm tra certificate | Fail secure và sửa trust configuration |
| Credential broker latency | Cache raw secret không hạn | Timeout/bounded retry + cache/lease policy theo risk |

### 19.1. Availability cũng là một security objective

Một thiết kế làm tất cả services fail khi broker outage có thể gây availability incident và tạo áp lực tắt security controls. Review cần:
- HA/DR của secret provider.
- Latency/error budget và retry behavior.
- Token lease renewal trước expiry.
- Các operation có thể degraded safely.
- Bounded caches và cách revoke khi provider offline.
- Break-glass và emergency operation có approval/logging.
- Error handling tránh leak secret qua stack trace.
- Diễn tập outage và recovery.

**Fail closed không phải lúc nào cũng tắt toàn bộ ứng dụng.** Cần xác định action/resource có thể tiếp tục phục vụ an toàn và phương thức hạn chế scope.

## 20. Java 17: policy review trước khi gọi managed signing operation

Ví dụ ứng dụng cần ký một bản export đã được approve. Thay vì nạp raw private key vào JVM, ứng dụng có thể gửi digest đến dịch vụ ký được quản lý. **Trước khi gọi** dịch vụ ký, phải kiểm tra verified workload identity, environment, tenant, signing key purpose và approval. Dịch vụ ký/KMS cũng cần independently enforce IAM/key-use policy.

**Thiết kế ví dụ chỉ là một lớp policy**, không phải giao thức ký đầy đủ, không trực tiếp chứng minh cryptographic module hoặc chống token theft.

### 20.1. Policy fail-safe với metadata từ nguồn tin cậy

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.Set;

record VerifiedWorkload(
        String id,
        String environment,
        String tenantId,
        Set<String> allowedKeyRefs,
        boolean authenticated) {}

record ManagedSigningKey(
        String keyRef,
        String environment,
        String purpose,
        boolean enabled,
        Instant validUntil) {}

record ApprovedSigningIntent(
        String approvalId,
        String tenantId,
        String action,
        Instant validUntil,
        boolean independentlyApproved) {}

enum SecretUseDecision {
    ALLOW, DENY
}

final class SecretUsePolicy {
    private SecretUsePolicy() {}

    static SecretUseDecision evaluate(
            VerifiedWorkload workload,
            ManagedSigningKey key,
            ApprovedSigningIntent intent,
            Instant now) {

        if (workload == null || key == null
                || intent == null || now == null
                || workload.id() == null
                || workload.id().isBlank()
                || workload.environment() == null
                || workload.environment().isBlank()
                || workload.tenantId() == null
                || workload.tenantId().isBlank()
                || workload.allowedKeyRefs() == null
                || key.keyRef() == null
                || key.keyRef().isBlank()
                || key.environment() == null
                || key.environment().isBlank()
                || key.purpose() == null
                || key.purpose().isBlank()
                || key.validUntil() == null
                || intent.approvalId() == null
                || intent.approvalId().isBlank()
                || intent.tenantId() == null
                || intent.tenantId().isBlank()
                || intent.action() == null
                || intent.action().isBlank()
                || intent.validUntil() == null) {
            return SecretUseDecision.DENY;
        }

        // Subject authentication and authorized key use
        // must come from trusted IAM/IdP and provider policy.
        if (!workload.authenticated()
                || !key.enabled()
                || !workload.allowedKeyRefs().contains(key.keyRef())) {
            return SecretUseDecision.DENY;
        }

        // Cross-environment or cross-tenant use is forbidden.
        if (!Objects.equals(
                workload.environment(), key.environment())
                || !Objects.equals(
                workload.tenantId(), intent.tenantId())) {
            return SecretUseDecision.DENY;
        }

        // This key is authorized for one narrow signing purpose.
        if (!"EXPORT_SIGNING".equals(key.purpose())
                || !"SIGN_APPROVED_EXPORT".equals(intent.action())
                || !intent.independentlyApproved()) {
            return SecretUseDecision.DENY;
        }

        // Both key and approval must remain valid.
        if (!key.validUntil().isAfter(now)
                || !intent.validUntil().isAfter(now)) {
            return SecretUseDecision.DENY;
        }

        return SecretUseDecision.ALLOW;
    }
}
~~~

### 20.2. Điều bắt buộc nằm ngoài snippet

- **VerifiedWorkload** được tạo từ identity đã xác minh, không từ HTTP JSON body.
- **allowedKeyRefs** là effective grant đã kiểm từ IAM/authorization, không từ client claims không đáng tin.
- **ManagedSigningKey** đến từ signed/authoritative registry hoặc KMS; trạng thái key có thể đổi giữa check và use.
- **ApprovedSigningIntent** phải được xác minh qua workflow approval/SoD thực tế; một boolean do caller đặt không đủ.
- **Digest/data được ký** phải ràng buộc chính xác với export, tenant, content version, approval và người yêu cầu; snippet chưa làm điều này.
- **KMS/HSM signing permission** cần kiểm độc lập ở điểm thực thi, hạn chế TOCTOU, audit và signer key usage.
- **Failure/audit:** nếu approval service hoặc key provider không khả dụng, không tự bỏ check. Cần structured event với reference IDs và không có private key/plaintext.
- **Replay:** một approval ID có thể bị tái dùng nếu workflow không thực thi single-use hoặc hạn mức; snippet không tự chống replay.
- **Tenant boundary:** signing gateway cũng cần kiểm đúng request resource và tenant; match hai chuỗi không thay thế policy ở backend.
- **Revocation:** cached approval và key state phải tôn trọng hiệu lực revoke theo objective.

Một policy function thuần giúp reviewer xác định **đường cho phép và từ chối**. Nó không phải implementation đầy đủ cho hệ thống phê duyệt và ký số production.

### 20.3. JUnit 5: kiểm thử quyền dùng secret cho đúng purpose

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Instant;
import java.util.Set;
import org.junit.jupiter.api.Test;

class SecretUsePolicyTest {
    private static final Instant NOW =
            Instant.parse("2026-11-28T00:00:00Z");

    private static VerifiedWorkload workload() {
        return new VerifiedWorkload(
                "export-worker", "prod", "tenant-A",
                Set.of("key/export-prod-v3"), true);
    }

    private static ManagedSigningKey key() {
        return new ManagedSigningKey(
                "key/export-prod-v3", "prod", "EXPORT_SIGNING",
                true, NOW.plusSeconds(300));
    }

    private static ApprovedSigningIntent approval() {
        return new ApprovedSigningIntent(
                "approval-42", "tenant-A", "SIGN_APPROVED_EXPORT",
                NOW.plusSeconds(180), true);
    }

    @Test
    void allowsIntendedSigningUseWithinValidity() {
        assertEquals(SecretUseDecision.ALLOW,
                SecretUsePolicy.evaluate(
                        workload(), key(), approval(), NOW));
    }

    @Test
    void deniesUnknownWorkloadOrMissingContext() {
        assertEquals(SecretUseDecision.DENY,
                SecretUsePolicy.evaluate(
                        null, key(), approval(), NOW));
        assertEquals(SecretUseDecision.DENY,
                SecretUsePolicy.evaluate(
                        workload(), null, approval(), NOW));
    }

    @Test
    void deniesUnauthorizedKeyReference() {
        var outsider = new VerifiedWorkload(
                "analytics-worker", "prod", "tenant-A",
                Set.of("key/analytics-prod"), true);
        assertEquals(SecretUseDecision.DENY,
                SecretUsePolicy.evaluate(
                        outsider, key(), approval(), NOW));
    }

    @Test
    void deniesCrossEnvironmentAccess() {
        var staging = new VerifiedWorkload(
                "export-worker", "staging", "tenant-A",
                Set.of("key/export-prod-v3"), true);
        assertEquals(SecretUseDecision.DENY,
                SecretUsePolicy.evaluate(
                        staging, key(), approval(), NOW));
    }

    @Test
    void deniesCrossTenantSigningIntent() {
        var wrongTenant = new ApprovedSigningIntent(
                "approval-42", "tenant-B", "SIGN_APPROVED_EXPORT",
                NOW.plusSeconds(180), true);
        assertEquals(SecretUseDecision.DENY,
                SecretUsePolicy.evaluate(
                        workload(), key(), wrongTenant, NOW));
    }

    @Test
    void deniesUnapprovedOrWrongPurposeUse() {
        var unapproved = new ApprovedSigningIntent(
                "approval-42", "tenant-A", "SIGN_APPROVED_EXPORT",
                NOW.plusSeconds(180), false);
        var wrongPurpose = new ManagedSigningKey(
                "key/export-prod-v3", "prod", "JWT_SIGNING",
                true, NOW.plusSeconds(300));

        assertEquals(SecretUseDecision.DENY,
                SecretUsePolicy.evaluate(
                        workload(), key(), unapproved, NOW));
        assertEquals(SecretUseDecision.DENY,
                SecretUsePolicy.evaluate(
                        workload(), wrongPurpose, approval(), NOW));
    }

    @Test
    void deniesExpiredApprovalOrKey() {
        assertEquals(SecretUseDecision.DENY,
                SecretUsePolicy.evaluate(
                        workload(), key(), approval(),
                        NOW.plusSeconds(181)));
        var longerApproval = new ApprovedSigningIntent(
                "approval-42", "tenant-A", "SIGN_APPROVED_EXPORT",
                NOW.plusSeconds(600), true);
        assertEquals(SecretUseDecision.DENY,
                SecretUsePolicy.evaluate(
                        workload(), key(), longerApproval,
                        NOW.plusSeconds(301)));
    }

    @Test
    void deniesDisabledKeyEvenIfGrantAndApprovalAreValid() {
        var disabled = new ManagedSigningKey(
                "key/export-prod-v3", "prod", "EXPORT_SIGNING",
                false, NOW.plusSeconds(300));
        assertEquals(SecretUseDecision.DENY,
                SecretUsePolicy.evaluate(
                        workload(), disabled, approval(), NOW));
    }

    @Test
    void deniesAnonymousWorkload() {
        var unauthenticated = new VerifiedWorkload(
                "export-worker", "prod", "tenant-A",
                Set.of("key/export-prod-v3"), false);
        assertEquals(SecretUseDecision.DENY,
                SecretUsePolicy.evaluate(
                        unauthenticated, key(), approval(), NOW));
    }
}
~~~

**Điểm cần nhớ khi review:** unit test pass là bằng chứng về logic của một lớp. Reviewer vẫn phải xác minh **sai key alias ở runtime, key disabled/revoked, provider IAM policy, approval provenance, exception logs và đường access bypass** qua integration/E2E tests. Không được tự ghi PASS cho yêu cầu custody/approval chỉ vì các object trong unit test được điền đúng giá trị.

## 21. Phân tích anti-pattern theo mức độ rủi ro

| Anti-pattern | Nguyên nhân/rủi ro | Quyết định review gợi ý |
|---|---|---|
| Secret hardcode trong production code/image | Credential có thể lan tới mọi clone và artifact | Tạo finding; revoke/rotate và loại bỏ đường phân phối |
| Long-lived cloud key trong CI khi có federation | Key persistence và supply-chain blast radius | Đánh giá thay bằng workload federation; giới hạn migration |
| Admin credential dùng cho DB runtime | Quyền vượt nhiệm vụ, lateral movement | Tách account/role và negative access test |
| Signing key exportable không cần thiết | Key material có nhiều bản sao và process copies | Chuyển sang managed operation nếu khả thi |
| Key non-exportable nhưng sign arbitrary payload | Operation abuse vẫn có thể tạo signature giả | Signing intent policy, approval binding, test |
| Secret manager read toàn namespace | Một workload compromise lấy nhiều secret | Per-service paths, IAM, resource scope, inventory |
| Shared credential giữa tenants/environments | Tăng blast radius, mất attribution | Segmentation theo use case/risk |
| App log raw credential | Exfiltration qua log viewers, third parties | Schema allowlist/redaction, incident handling |
| Static secret không có owner/expiry | Privilege creep, khó revoke | Lifecycle governance, rotate, owner assignment |
| Rotation nhưng old credential vẫn dùng vô hạn | Compromise risk tồn tại | Overlap TTL, effective revoke test |
| KMS outage fallback sang key mẫu | Fail-open, mất confidentiality/integrity | Stop sensitive operation, HA/DR design |
| Backup chứa key/plaintext không quản lý | Bản sao vẫn lộ dù runtime đã sửa | Backup inventory, access, retention, purge/restore |
| Developer có thể tự mở IAM KMS grants | Privilege escalation | SoD, policy review, restricted control plane |
| BYOD/endpoint logs chứa refresh tokens | Device theft/token replay | Endpoint/session controls, limited offline storage |
| Hệ thống chỉ chạy secret scanner | Bỏ sót runtime/config/authorization và use misuse | Bổ sung DFD, effective permission, negative tests |

Severity phải dựa vào **có thực sự exploitable hay không, tác động nếu lộ/lạm dụng, scope quyền, thời gian tồn tại, mức kiểm soát bù đắp và bằng chứng**, không chỉ dựa vào tên công cụ hoặc mức “critical” do scanner gán.

## 22. Review workflow: từ thiết kế tới release

### 22.1. Bước 1 — Xác định business operation

Ví dụ: export kết quả thi của tenant A và ký file export để người nhận xác minh nguồn. Xác định data classification, issuer, operator, consumer và threat scenarios.

### 22.2. Bước 2 — Vẽ secret-specific data flow

Đánh dấu:
- Secret issuance và trust roots.
- Điểm raw secret xuất hiện hoặc không xuất hiện.
- Khi nào signing/decrypt operation được gọi.
- Những copy trong memory/cache/log/CI/backup.
- Đường trực tiếp và gián tiếp từ actor tới key-use.
- Credential rotation và revocation propagation.

### 22.3. Bước 3 — Xác định policy và bảo đảm cần đạt

Mỗi secret:
- Có owner, purpose, environment, tenant/resource scope.
- Cơ chế cấp phát/nguồn identity đã kiểm.
- Allowed/denied operations.
- TTL/rotation/revoke.
- Storage/transport/runtime trust boundary.
- Monitoring/audit.
- Fallback behavior và DR.
- Rationale cho các ngoại lệ.

### 22.4. Bước 4 — Tính effective access

Đừng chỉ đọc policy tại secret store. Lập graph gồm:
- Human users, privileged accounts, vendor accounts.
- Runtime workload identities.
- CI runners và deployment roles.
- Kubernetes namespaces/service accounts/exec.
- KMS policy, secret manager grants.
- IAM role assumption, group inheritance và policy edit permissions.
- Downstream resource access.
- Audit/log/config readers.

Một quyền không thể đọc raw key nhưng có thể sửa signing policy có thể là đường attack path tương đương.

### 22.5. Bước 5 — Đề xuất verification

- Positive và negative tests cho caller/purpose/scope.
- Invalid/expired/rotated/revoked credentials.
- CI/repo/container/log secret leakage.
- Wrong environment/tenant.
- KMS outage, malformed response và timeout.
- PEP/API/direct-path bypass.
- Effective revoke, session/connection pool.
- Key or certificate backup/restore.
- Audit completeness và privacy constraints.

### 22.6. Bước 6 — Ghi decision và release gate

Các outcome có thể là:
- **APPROVED:** design controls đáp ứng acceptance, không có blocker trong phạm vi đã review.
- **APPROVED_WITH_CONDITIONS:** được phép theo điều kiện, owner/expiry/compensating controls đã được thẩm quyền chấp nhận.
- **REWORK_REQUIRED:** requirement/control thiếu hoặc có risk không thể chấp nhận.
- **INCONCLUSIVE:** chưa đủ evidence hoặc thiếu access paths/permissions.
- **EXCEPTION_ACCEPTED:** risk owner đã phê duyệt một exception được quản lý, **không có nghĩa control đã PASS**.

Review decision **không tự thay thế** security test hoặc production runtime validation. Khi release thực tế khác bản thiết kế, phải reassess.

### 22.7. Bước 7 — Remediation và retest

Finding cần có:
- Criteria vs condition.
- Asset/secret ID và scope.
- Evidence/steps to reproduce ở môi trường được ủy quyền.
- Risk/impact, root cause, exploitability.
- Owner, severity, due date, dependency.
- Remediation plan, rollback/migration.
- Test/retest evidence và actual environment.
- Residual risk/closure approval.

Không đóng finding chỉ vì “đã chuyển password vào vault” nếu IAM vẫn cho nhiều workload khác đọc, log còn copy và old credential còn hoạt động.


## 23. Mẫu biên bản security design review bằng YAML

Hồ sơ dưới đây là **mẫu học tập**. Những evidence reference có dấu placeholder không phải bằng chứng thực tế và trạng thái INCONCLUSIVE cố ý thể hiện còn gap.

~~~yaml
review:
  id: "SDR-SECRET-007"
  module: "SECURITY_SECURITY_ASSURANCE"
  chapter: "Security design review"
  topic: "Review secret usage"
  version: "1.0"
  review_type: "architecture-and-change-review"
  status: "INCONCLUSIVE"
  reviewer: "<security-reviewer>"
  requested_by: "<service-owner>"
  review_at: "<ISO-8601>"
scope:
  service: "learning-export-worker"
  environment: "production"
  release: "<release-id>"
  tenant_scope: ["tenant-A", "tenant-B"]
  business_operations:
    - "export-exam-results"
    - "sign-export-artifact"
  access_paths:
    - "api"
    - "batch-worker"
    - "signing-gateway"
    - "ci-deploy"
secret_usages:
  - id: "SU-KEY-001"
    kind: "managed-asymmetric-signing-key"
    secret_reference: "keys/learning-export-signing/prod"
    purpose: "SIGN_APPROVED_EXPORT"
    owner: "<key-owner>"
    issuer: "<approved-kms-or-hsm>"
    exportable: false
    raw_material_in_workload: false
    allowed_operations: ["sign"]
    allowed_consumers: ["learning-export-worker"]
    workload_identity_ref: "<verified-workload-id>"
    environment: "production"
    scope:
      allowed_tenants: ["tenant-A", "tenant-B"]
      approval_required: true
      approval_id_source: "<trusted-approval-service>"
    lifecycle:
      key_version: "<approved-key-version>"
      expiry: "<date-or-policy-reference>"
      rotation_policy: "<policy-id>"
      revocation_procedure: "<procedure-id>"
    evidence_refs:
      - "<key-policy-and-status>"
      - "<signing-operation-negative-test>"
      - "<audit-event-sample>"
  - id: "SU-API-002"
    kind: "vendor-api-credential"
    secret_reference: "vendor/email/prod"
    purpose: "SEND_EXPORT_NOTIFICATION"
    owner: "<integration-owner>"
    issuer: "<approved-third-party>"
    allowed_consumers: ["notification-service"]
    delivery: "runtime-secret-broker"
    scope:
      vendor_account: "<approved-account>"
      allowed_api_actions: ["send-notification"]
      environment: "production"
    lifecycle:
      max_lifetime: "<approved-duration>"
      rotation_policy: "<policy-id>"
      revocation_procedure: "<procedure-id>"
    evidence_refs:
      - "<vendor-role-scope-evidence>"
      - "<log-leak-negative-test>"
controls:
  - id: "CTRL-SU-01"
    description: "No raw signing key leaves approved module"
    test_ids: ["TEST-SU-01", "TEST-SU-04", "TEST-SU-11"]
  - id: "CTRL-SU-02"
    description: "Workload identity and operation are scoped"
    test_ids: ["TEST-SU-02", "TEST-SU-03", "TEST-SU-15"]
  - id: "CTRL-SU-03"
    description: "No secrets in source, CI, logs or artifacts"
    test_ids: ["TEST-SU-06", "TEST-SU-07", "TEST-SU-08"]
  - id: "CTRL-SU-04"
    description: "Rotation and revocation effective"
    test_ids: ["TEST-SU-19", "TEST-SU-20"]
  - id: "CTRL-SU-05"
    description: "Fail-safe when manager is unavailable"
    test_ids: ["TEST-SU-22", "TEST-SU-23"]
threats:
  - id: "RISK-SU-01"
    scenario: "CI job leaks production credential"
    requirements: ["REQ-SU-01"]
    controls: ["CTRL-SU-03"]
  - id: "RISK-SU-02"
    scenario: "Compromised worker signs outside approved purpose"
    requirements: ["REQ-SU-02"]
    controls: ["CTRL-SU-01", "CTRL-SU-02"]
review_decision:
  design_effectiveness: "PENDING"
  implementation_effectiveness: "PENDING"
  operating_effectiveness: "NOT_ASSESSED"
  findings: ["<finding-id-or-none>"]
  limitations:
    - "Legacy pipeline role has not been tested"
    - "Key revocation has not been exercised end-to-end"
  exceptions:
    - "<approved-exception-reference-or-none>"
  residual_risk_owner: "<authorized-risk-owner>"
  release_gate: "REWORK_OR_EVIDENCE_REQUIRED"
reassessment_triggers:
  - "New secret consumer or secret scope"
  - "Change in CI trust, IAM, KMS/HSM or token issuance"
  - "Secret exposure, compromise or failed revoke"
  - "New environment, tenant, vendor or data export path"
~~~

**Không lưu raw secret value, private key, token, password hoặc plaintext PII vào review artifact.** Khi cần chia sẻ evidence, dùng định danh tới kho bảo mật có permissions và retention rõ; không chép kết quả chứa credential vào tài liệu dùng chung.

## 24. Requirement-to-control-to-evidence mapping

Để review có thể kiểm chứng, mỗi finding và requirement cần nối với risk scenario.

| Risk ID | Requirement | Control | Test / evidence |
|---|---|---|---|
| **RISK-SU-01:** secret trong code/artifact/CI | **REQ-SU-01:** pipeline và artifacts không phát secret production ngoài phạm vi | **CTRL-SU-01:** federation, scanner, artifact isolation | CI role negative test; image/layer/log scan |
| **RISK-SU-02:** signing operation bị lạm dụng | **REQ-SU-02:** chỉ ký dữ liệu đã approve đúng key/purpose | **CTRL-SU-02:** IAM, signing policy, SoD | Wrong-purpose/tenant/approval test, KMS audit |
| **RISK-SU-03:** secret manager permissions quá rộng | **REQ-SU-03:** consumer chỉ có quyền đúng secret/operation | **CTRL-SU-03:** per-workload access grant | Effective permission export, denied read |
| **RISK-SU-04:** secret được log | **REQ-SU-04:** không log raw credential ở logs/traces/metrics | **CTRL-SU-04:** schema redaction/minimization | Synthetic canary search across sinks |
| **RISK-SU-05:** session/token bị tái sử dụng | **REQ-SU-05:** credential có TTL, audience và binding theo risk | **CTRL-SU-05:** session/token protection | Wrong audience, expired/replay tests |
| **RISK-SU-06:** shared credential giữa môi trường | **REQ-SU-06:** secret tách scope dev/test/prod | **CTRL-SU-06:** environment boundary policy | Staging cannot read prod test |
| **RISK-SU-07:** stale secret sau rotate | **REQ-SU-07:** overlap có hạn, old credential hết hiệu lực | **CTRL-SU-07:** rotation/revoke process | Connection pool/old token retest |
| **RISK-SU-08:** key bị lộ từ runtime | **REQ-SU-08:** hạn chế raw key; dùng managed operation khi phù hợp | **CTRL-SU-08:** KMS/HSM custody and isolation | Key export denied; runtime data-flow review |
| **RISK-SU-09:** KMS outage làm fail-open | **REQ-SU-09:** không dùng hardcoded/weak fallback | **CTRL-SU-09:** fail-safe + DR | Provider timeout/fault injection |
| **RISK-SU-10:** kiểm kê thiếu consumer | **REQ-SU-10:** mọi active secret có owner, purpose, consumers | **CTRL-SU-10:** inventory reconciliation | Manager/IAM/CI/runtime population cross-check |
| **RISK-SU-11:** quyền gián tiếp mở secret access | **REQ-SU-11:** control-plane grants không tạo path trái phép | **CTRL-SU-11:** RBAC/PAM/admission/SoD | Pod impersonation and role escalation tests |
| **RISK-SU-12:** backup chứa secret không quản lý | **REQ-SU-12:** copies có encryption, retention và access policy | **CTRL-SU-12:** backup governance | Snapshot/archive review, restore test |
| **RISK-SU-13:** vendor credential không revoke được | **REQ-SU-13:** credential có lifecycle và compensating controls | **CTRL-SU-13:** vendor token governance | Vendor revoke evidence, incident runbook |
| **RISK-SU-14:** API key dùng sai mục đích | **REQ-SU-14:** token/key scope theo caller, action và resource | **CTRL-SU-14:** resource/purpose authorization | Unauthorized API/op negative test |

Các ID trên do bài học tạo ra để minh họa, **không phải ID của chuẩn bên ngoài**. Một control có thể xử lý nhiều risks và một requirement có thể cần nhiều controls. Không nên báo 100% mapping chỉ vì mỗi ô có tên; cần đánh giá **implementation và evidence thực tế**.

### 24.1. Dấu hiệu coverage chưa đủ

- Secret có IAM grant nhưng không có negative test.
- Có rotation policy nhưng không có test old credential bị reject.
- Secret nằm trong KMS nhưng không rõ app có quyền sign/decrypt arbitrary payload hay không.
- Không có bằng chứng environment isolation.
- Không có CI/repository/runner trong inventory.
- Chỉ kiểm scanner, không kiểm log/trace/heap artifacts.
- Review chỉ dùng staging config nhưng claim cho production.
- Consumer có quyền quản trị secret grant nhưng bảng review chỉ liệt kê quyền read.
- Không biết legacy service còn dùng credential trước migration hay không.

## 25. Ma trận kiểm thử: Review secret usage

**Kiểm thử nên chứng minh cả luồng hợp lệ và đường sử dụng ngoài policy bị từ chối.** Các hành động giả lập compromise, đọc secret, revoke và fault injection chỉ được thực hiện trong phạm vi đã được phép, ưu tiên tài khoản/credential synthetic.

| Test ID | Kịch bản | Kỳ vọng | Evidence |
|---|---|---|---|
| **TEST-SU-01** | Workload hợp lệ yêu cầu ký artifact đã duyệt | Ký thành công theo key/purpose/scope | Approved intent + signer audit |
| **TEST-SU-02** | Analytics workload dùng signing key export | DENY | KMS/IAM operation test |
| **TEST-SU-03** | Staging workload gọi key production | DENY | Cross-environment negative |
| **TEST-SU-04** | Ứng dụng yêu cầu export raw private signing key | DENY theo key policy | Non-exportability/API test |
| **TEST-SU-05** | Worker ký cho tenant không được phép | DENY | Cross-tenant signing test |
| **TEST-SU-06** | CI job từ PR không tin cậy yêu cầu prod credential | DENY | CI federation trust test |
| **TEST-SU-07** | Repo/image/CI artifacts chứa synthetic secret canary | Không xuất hiện ngoài sink đã duyệt | Scanner/artifact inspection |
| **TEST-SU-08** | HTTP interceptor nhận Authorization/Api-Key | Log/trace không có raw value | Observability regression |
| **TEST-SU-09** | Service account không cần Kubernetes API token | Token không được auto-mount theo policy | Pod manifest/runtime review |
| **TEST-SU-10** | User có quyền patch pod thử mount secret của workload khác | Admission/RBAC chặn theo policy | Kubernetes RBAC test |
| **TEST-SU-11** | Workload được phép ký cố gọi decrypt/unwrap khác purpose | DENY | Operation-level negative test |
| **TEST-SU-12** | Secret ref được đổi sang key không có trong allowlist | DENY | Policy validation |
| **TEST-SU-13** | Approval id chưa tồn tại hoặc sai actor | DENY | Workflow integration |
| **TEST-SU-14** | Approval đã hết hạn | DENY | Expiry test |
| **TEST-SU-15** | Caller không authenticated hoặc IAM grant thiếu | DENY | Identity/grant negative |
| **TEST-SU-16** | Token có audience khác API đích | DENY | Token validation |
| **TEST-SU-17** | Service bị redirect sang host không duyệt | Credential không được chuyển tiếp | HTTP client negative |
| **TEST-SU-18** | Secret manager trả version unknown/disabled | Không dùng arbitrary fallback | Retrieval failure test |
| **TEST-SU-19** | Rotate DB password với connection pools | New connections dùng credential mới; old bị giới hạn theo policy | Rotation exercise |
| **TEST-SU-20** | Old API key bị revoke | Provider/consumer không còn chấp nhận trong latency objective | Effective revoke test |
| **TEST-SU-21** | Key signing bị disable nhưng cached decision còn | Signing operation DENY theo effective policy | Cache/revoke integration |
| **TEST-SU-22** | Secret manager timeout hoặc outage | Fail-safe; không hardcode/plaintext fallback | Fault injection |
| **TEST-SU-23** | KMS permission denied | Không assume admin hoặc thử key khác | Error-path test |
| **TEST-SU-24** | Backup/restore có secret hoặc wrapped key | Phạm vi, encryption và access đáp ứng policy | Restore test, backup inventory |
| **TEST-SU-25** | Vendor key bị compromise | Tạo key mới, revoke old, khôi phục consumer theo plan | Incident tabletop/controlled exercise |
| **TEST-SU-26** | Audit pipeline lỗi khi thao tác nhạy cảm | Hành vi theo approved audit policy, không silently disable | Reliability/fail-safe test |
| **TEST-SU-27** | Người phê duyệt cũng là người yêu cầu signing intent | SoD policy chặn khi yêu cầu độc lập | Approval negative |
| **TEST-SU-28** | Một principal có quyền read secret qua group lồng nhau | Effective permissions được phát hiện và review | Entitlement graph |
| **TEST-SU-29** | Thay KMS/IAM policy ngoài IaC | Drift detection và incident/approval flow | Runtime vs source diff |
| **TEST-SU-30** | Một raw credential xuất hiện trong exception chain | Redaction, không lưu sang error-tracking | Exception path inspection |
| **TEST-SU-31** | Secret lease hết hạn khi job kéo dài | Job renew có kiểm soát hoặc fail; không dùng expired credential | Lease lifecycle test |
| **TEST-SU-32** | Một tenant dùng secret ref thuộc tenant khác | DENY | Tenant/key scoping E2E |
| **TEST-SU-33** | Secret được cấp cho job cũ nhưng user/vendor đã offboarded | Không còn quyền hiệu lực | Offboarding negative |
| **TEST-SU-34** | Requester lặp lại signing approval một lần dùng | Từ chối replay nếu yêu cầu single-use | Idempotency/approval replay test |
| **TEST-SU-35** | Security exception hết hạn nhưng grant vẫn còn | Alert/chặn hoặc có reapproval theo policy | Exception expiry test |
| **TEST-SU-36** | Khởi động production thiếu secret bắt buộc | Fail safely, không dùng default | Startup configuration test |

### 25.1. Chứng minh kết quả thực tế

Mỗi test nên có:
- Test ID, requirement/control IDs.
- Scope, environment, release/build, secret reference **không có giá trị**.
- Test principal/workload, action, resource.
- Expected vs actual result.
- Thời gian, policy/key version.
- Logs đã redact, relevant event IDs và reviewer.
- Remediation/defect ID nếu fail.
- Limitations nếu một path chưa thể test.

Đánh giá “test passed” phải xem liệu **test thực sự đi qua production-equivalent enforcement point**. Một mock secret manager trả DENY chỉ chứng minh mock, không chứng minh cloud IAM hoặc KMS policy.

### 25.2. Kiểm soát an toàn khi test

- Không đăng nhập hoặc lấy secrets của người khác ngoài phạm vi ủy quyền.
- Không copy raw production credential để tạo test fixtures.
- Không chạy destructive key deletion/credential revoke trên production nếu chưa có runbook và approval.
- Dùng synthetic canary/token chỉ có quyền test.
- Khi kiểm third-party API, dùng sandbox/test tenant hoặc thử với account do nhóm quản lý.
- Đảm bảo log/evidence không tạo thêm rò rỉ.
- Với hệ thống không thể test trực tiếp, ghi gap/alternative evidence và mức assurance giới hạn.

## 26. Claim – Argument – Evidence (CAE) cho Review secret usage

Một security assurance claim phải nói rõ **service, secret loại nào, môi trường, loại operation, thời kỳ và đường truy cập**.

| Thành phần | Ví dụ ứng dụng xuất báo cáo |
|---|---|
| **Risk** | Kẻ kiểm soát worker hoặc CI lấy quyền ký/export vượt tenant/purpose |
| **Claim** | Với release và environment thuộc scope, raw private export signing key không rời approved key boundary; chỉ export worker đã được cấp quyền và có approval hợp lệ mới được gọi signing operation |
| **Argument** | Key ở managed boundary; per-workload identity; operation grants scope key/purpose; signing approval được xác minh; CI không có quyền đọc raw key; audit có keyRef/actor/decision |
| **Evidence – design** | DFD, threat model, ADR chọn managed signing, key lifecycle specification |
| **Evidence – implementation** | Key attributes, effective IAM/KMS policies, service identity config, app policy code |
| **Evidence – tests** | Wrong workload, wrong environment, wrong purpose, invalid approval, disabled key, bypass attempts |
| **Evidence – operations** | Signing audit events, rotation/revoke samples, IAM drift reports, incidents/finding closure |
| **Assumptions** | IAM/IdP, approved signer service và audit pipeline nằm trong controls liên quan |
| **Limitations** | Một legacy CI deploy role chưa được test; browser export API chưa đủ đường E2E |
| **Residual risk** | Compromised approved worker có thể gọi signing API trong policy scope; detection và revoke latency |
| **Conclusion** | PASS/FAIL/INCONCLUSIVE **theo scope**, không tuyên bố “secret không thể bị lạm dụng” |

### 26.1. Design effectiveness

Câu hỏi:
- Secret type/purpose/issuer phù hợp risk?
- Có thể tránh raw secret không?
- Least privilege, SoD, fail-safe và lifecycle được định nghĩa?
- Ranh giới trust rõ, không bypass?
- Có thể quan sát quyết định mà không lộ raw values?

Evidence: architecture/DFD, risk scenarios, policy, review records.

### 26.2. Implementation effectiveness

Câu hỏi:
- IAM/key policies có thực thi đúng thiết kế?
- CI/containers/secret manager được cấu hình đúng environment?
- Java code không có insecure fallback, unrestricted logging?
- Signing/decrypt gọi đúng service và verified business context?
- Negative integration tests có chứng minh denied operations?

Evidence: effective runtime policies, build/release config, test traces.

### 26.3. Operating effectiveness

Câu hỏi:
- Trong kỳ, secret issuance/rotation/revoke/expiry có diễn ra đúng?
- Privileged accesses và exceptions được review?
- Secret exposure incidents được xử lý và retest?
- Có runtime drift chưa khắc phục?
- Logs và evidence có completeness/freshness?

Evidence: population, audit logs, sample requests, incident tickets, rotation/revoke records.

**Một sơ đồ kiến trúc không chứng minh runtime. Một unit test không chứng minh KMS IAM. Một dashboard secret manager không chứng minh credential đã ngừng hoạt động ở bên nhận.**

## 27. Finding mẫu: CI pipeline có quyền ký artifact ngoài phạm vi

Giả định một pipeline build ứng dụng học tập có thể gọi KMS signing key production. Workflow chạy cho cả branch thử nghiệm và branch phát hành; trust policy không giới hạn môi trường và reviewer chỉ kiểm “key non-exportable”. Một nhánh không được bảo vệ có thể ký artifact trông giống release chính thức.

| Trường | Mô tả |
|---|---|
| **Finding ID** | FND-SU-007 |
| **Criteria** | REQ-SU-02: signing operation chỉ cho workflow/release được duyệt, với danh tính, purpose và approval đúng |
| **Condition** | CI role có sign grant rộng; OIDC trust policy không giới hạn protected branch/environment |
| **Evidence** | Effective IAM trust/key policies, CI claims, staged unauthorized-sign negative test |
| **Impact** | Artifact giả có thể được ký bằng key tin cậy; downstream verifier có thể chấp nhận nếu thiếu release metadata controls |
| **Root cause cần xác minh** | Thiết kế kiểm non-exportability nhưng bỏ review quyền thực hiện signing operation |
| **Immediate containment** | Giới hạn grant, tạm khóa unapproved pipeline paths, rà audit đã ký |
| **Owner** | CI/platform owner, key custodian, release security owner |
| **Remediation** | Tách build và release identities; giới hạn claims/branch/environment, key purpose và approval; enforce release signing policy |
| **Verification** | Protected release path ký hợp lệ; branch/runner không được duyệt bị DENY; kiểm policy/runtime sau deploy |
| **Residual risk** | CI admin hoặc được phép sửa release workflow có thể tác động tương lai; cần SoD/PAM và audit |
| **Closure** | Chỉ sau retest ở môi trường đúng, audit exposure assessment và owner sign-off |

**Không đóng finding** bằng cách “chuyển key sang HSM” nếu key vẫn non-exportable từ trước và issue nằm ở **quyền sử dụng phép ký**.

### 27.1. Finding mẫu thứ hai: secret rò rỉ qua log

Một service ghi OAuth refresh token vào trace attribute. Cách xử lý:
- Xác định tokens còn hiệu lực, phạm vi và sink nhận telemetry.
- Revoke/rotate, thu hồi sessions theo policy.
- Loại raw headers/token khỏi logging, thêm redaction test.
- Xử lý log copies, retention và third-party access theo quy trình.
- Tìm các sinks tương tự từ app, gateway, proxy và error tracking.
- Đánh giá incident/privacy impact với owner phù hợp.
- Dùng synthetic secret canary để chứng minh fix, không dán token thật vào báo cáo.

Finding severity không chỉ phụ thuộc credential “đang ở log”; cần xét quyền sử dụng, TTL, người có quyền xem log, nơi đã được export và evidence về misuse.

## 28. Audit secret usage: population và sampling

### 28.1. Population phải bao gồm cả secret lẫn người dùng quyền

Auditor nên đối chiếu:
- Secret manager/KMS/HSM inventories.
- IAM groups/roles/policies và inherited permissions.
- Users, service accounts, workload identities, CI runners.
- Applications, environment, tenants, vendors.
- Key usage events, token issuance, signing/decrypt operations.
- Git/code scanners và build artifacts.
- Container images, ConfigMaps, Kubernetes Secret references.
- Logs/traces/monitoring destinations.
- Rotation/revoke/offboarding/incident histories.
- Break-glass accounts và expired exceptions.
- Legacy services và shadow integrations.

Nếu sampling chỉ từ secret manager inventory, **hardcoded credentials và vendor keys nằm ngoài manager có thể bị bỏ sót**. Đánh giá completeness cần đối chiếu các nguồn độc lập, không chỉ một danh sách.

### 28.2. Ví dụ lấy mẫu

Giả sử tổng 180 secrets active đã được inventory; auditor chọn 24 secret usages theo mục tiêu đánh giá và tìm 5 usage không có evidence rằng old credential bị revoke sau rotation.

Kết luận được hỗ trợ là **5/24 usages được chọn thiếu revoke evidence**. Không tự suy rộng thành 20,8% toàn bộ 180 nếu phương pháp chọn mẫu không hỗ trợ thống kê. Cần xem trọng số risk: privileged signing keys, CI deploy credentials, database production, cross-tenant keys và third-party tokens thường quan trọng hơn các test credentials vô hại.

### 28.3. Evidence quality

| Thuộc tính | Câu hỏi |
|---|---|
| **Completeness** | Có toàn bộ producers, consumers, access paths, copies và credential types? |
| **Relevance** | Evidence có hỗ trợ đúng secret, operation và threat scenario? |
| **Provenance** | Nguồn IAM/KMS/CI/runtime nào, actor/timestamp nào? |
| **Integrity** | Logs/config/review approvals được bảo vệ khỏi sửa xóa trái phép? |
| **Freshness** | Có đúng release, secret/key version và kỳ đánh giá? |
| **Repeatability** | Có steps, test account và expected/actual outcome để tái kiểm? |
| **Independence** | Người cấu hình có tự chứng nhận khi cần reviewer độc lập? |
| **Confidentiality** | Evidence không đưa raw secret vào kho audit? |
| **Traceability** | Nối được secret usage → requirement/control → test → risk/finding? |

### 28.4. Audit theo đường truy cập không có trong tài liệu

Một bảng thiết kế nói chỉ export-worker có quyền dùng signing key. Audit nên kiểm cả:
- CI deployment principal có thể sửa workload để giả export-worker?
- Kubernetes admin có thể exec hoặc mount token?
- KMS grant có resource wildcard hoặc principal impersonation?
- Support tool có chức năng “sign on behalf”?
- Một ứng dụng legacy còn gọi cùng key?
- Key version cũ có policy rộng hơn?
- Emergency credential có thể bypass audit?

Đây là khác biệt giữa **review policy trực tiếp** và **review effective secret-use capability**.

## 29. Metrics quản trị secret usage

| Metric | Điều đo | Giới hạn |
|---|---|---|
| **Secrets without owners** | Số secret không có custodian/purpose rõ | Ít không chứng minh scopes phù hợp |
| **Long-lived static credentials** | Secret vượt lifetime policy | Cần xem vendor constraints và exceptions |
| **Shared credential count** | Credential dùng bởi nhiều workloads/tenants | Không phải mọi sharing đều sai; xem risk |
| **Excess read/sign/decrypt grants** | Principal có operation permissions vượt nhu cầu | Cần effective privilege graph |
| **CI secret exposure findings** | Leak qua pipeline, artifacts, logs | Scanner false negatives và runtime paths |
| **Rotation overdue** | Secrets quá trigger rotation mà chưa thay | Rotation không chứng minh revoke |
| **Effective revocation latency** | Thời gian từ revoke tới downstream rejection | Cần kiểm cache, session, DB connection |
| **Secrets with no negative test** | Usage chưa có unauthorized-access evidence | Có test vẫn cần xem độ đúng |
| **Unknown secret usage** | Runtime sử dụng credentials không có inventory | Population completeness ảnh hưởng mẫu số |
| **Expired exception still active** | Bypass còn hoạt động sau expiry | Nên theo dõi severity/owner |
| **Key operations without purpose context** | Audit thiếu business intent/approval references | KMS operation log tự nó không có context nghiệp vụ |
| **Provider outage fail-open paths** | Các path có fallback insecure hoặc chưa test | Không chỉ đếm outage đã xảy ra |
| **Evidence freshness** | Bằng chứng có phản ánh current release/policy? | Fresh vẫn có thể không complete |
| **Repeat secret leaks** | Findings tái phát sau remediation | Giúp chỉ ra root cause trong workflow |
| **Secretless migration coverage** | Các tích hợp loại bỏ static credential phù hợp | Secretless không đồng nghĩa risk bằng 0 |

### 29.1. Ví dụ số liệu minh bạch

Trong 100 secret usages thuộc scope đã xác định:
- 72 có owner, purpose, IAM scope và negative test đạt yêu cầu.
- 18 có finding kiểm soát chưa đạt.
- 10 không đủ evidence để kết luận.

Có thể báo: **Verified compliant = 72/100; known noncompliant = 18/100; inconclusive = 10/100** cho **bộ tiêu chí cụ thể**.

Không báo “72% secrets an toàn”. Một signing key production và một token sandbox có mức rủi ro khác nhau; nên ưu tiên theo severity/blast radius, không dùng tỷ lệ tổng để che các trường hợp đặc quyền nguy hiểm.

## 30. Governance và trách nhiệm

| Vai trò | Trách nhiệm |
|---|---|
| **Business/application owner** | Xác định purpose, consumer, data scope, approval và business impact |
| **Security architect/reviewer** | DFD, trust boundary, threat model, requirements, review decisions |
| **Secret manager/KMS/HSM owner** | Custody, key attributes, provider policies, lifecycle, availability |
| **IAM owner** | Workload/human identity, effective access, revocation và SoD |
| **CI/CD owner** | Protected pipelines, federation, artifact controls và release gates |
| **Platform/cloud/Kubernetes owner** | Runtime identity, deployment permissions, mounts và network boundaries |
| **Application developer** | Safe consumption, no raw-key copies where avoidable, error/logging behavior |
| **Security testing/QA** | Positive/negative/fault-injection/rotation tests và regression |
| **SOC/incident response** | Exposure triage, compromise assessment, revoke, monitoring |
| **Privacy/compliance** | Dữ liệu nhạy cảm trong logs/evidence, retention và nghĩa vụ |
| **Risk owner/approver** | Exception/residual risk decisions theo thẩm quyền |
| **Auditor/assessor** | Kiểm evidence, completeness, operating effectiveness và closure |

### 30.1. RACI minh họa cho một thay đổi key-use grant

| Hoạt động | App owner | IAM/KMS owner | Security reviewer | Risk owner |
|---|---|---|---|---|
| Đề xuất purpose/operation | **R** | C | C | I |
| Đánh giá trust boundaries/risks | C | C | **R** | I |
| Phê duyệt exception có rủi ro | C | C | C | **A** |
| Áp policy grant | I | **R** | C | I |
| Negative test | C | C | **R** | I |
| Xác nhận release gate | C | C | **R** | A theo chính sách |

R = Responsible, A = Accountable, C = Consulted, I = Informed. Bảng không thay thế ma trận RACI chính thức; tổ chức phải xác định thẩm quyền và tránh việc một người tự cấp, tự xác nhận và tự đóng finding cho quyền nhạy cảm.

## 31. Continuous secret-usage assurance trong SDLC

| Giai đoạn | Review activity | Evidence |
|---|---|---|
| **Discovery** | Secret inventory, business purpose và required identities | Asset/secret registry |
| **Threat modeling** | Data-flow, trust boundaries, misuse paths | DFD, risk scenarios |
| **Architecture** | Secretless options, KMS/HSM usage, permissions và lifecycle | ADR, key/secret hierarchy |
| **Requirements** | Normative access, scope, TTL, failure, rotation, evidence | Approved requirement set |
| **Development** | Safe APIs, no hardcode/log, narrow signing/decrypt intent | Code review, unit tests |
| **CI/CD** | Federation, protected workflows, secret scan và artifact inspection | Pipeline config, policy checks |
| **Deployment** | Runtime IAM, mounts, key references, no fallback | Effective config snapshot |
| **Operation** | Observe key-use, token issuance, anomalies, drift | Audit events, alerts, tickets |
| **Rotation/revoke** | Cutover, old-secret rejection, restore | Rotation report, effective tests |
| **Incident** | Containment, leak investigation, revoke, evidence | Incident timeline, remediation |
| **Decommission** | Remove grants/consumers, token invalidation, backup handling | Deprovision/retirement evidence |
| **Reassessment** | Policy, vendor, IAM, tenant, architecture hoặc threat đổi | Updated threat/control mapping |

### 31.1. Trigger bắt buộc xem lại

- Thêm workload, pipeline, service account, vendor hoặc tenant.
- Secret purpose, resource/action hoặc environment scope thay đổi.
- Một credential được dùng lại cho service thứ hai.
- Thay KMS/HSM, secret manager, IAM trust policy, certificate issuer.
- Đổi cách injection (env → mount → sidecar) hoặc secret cache.
- Thêm logging/observability, crash dumping hoặc third-party monitoring.
- DevSecOps build pipeline, artifact registry hoặc source access thay đổi.
- Key compromise/leak, suspicious signing/decrypt operation hoặc incident.
- Rotation/revoke không đạt mục tiêu, expired exception còn active.
- Thay DR/backup, cross-region replication hoặc retention.
- Security advisory về library, credential format hay vendor.
- Chính sách, nghĩa vụ và risk appetite được cập nhật.

### 31.2. Closed-loop assurance

~~~mermaid
flowchart TD
    A["New secret or change event"] --> B["Update inventory, purpose and DFD"]
    B --> C["Threat and effective-permission review"]
    C --> D["Approve requirement, controls and exception"]
    D --> E["Deploy with CI/runtime gates"]
    E --> F["Positive, negative and lifecycle tests"]
    F --> G["Collect decision, usage and revoke evidence"]
    G --> H{"Assurance claim supported?"}
    H -- "Yes within scope" --> I["Continuous monitoring"]
    H -- "Fail / unknown" --> J["Finding, owner, incident or remediation"]
    J --> K["Fix, rotate/revoke if needed, retest"]
    K --> G
    I --> A
~~~

## 32. Những ngộ nhận phổ biến

| Ngộ nhận | Vì sao sai | Cách đánh giá tốt hơn |
|---|---|---|
| “Đã đưa password vào vault là xong.” | Consumer vẫn có thể quá quyền, log hoặc cache lâu | Review toàn lifecycle và effective access |
| “KMS key không export được nghĩa không lạm dụng được.” | Caller có thể gọi sign/decrypt quá rộng | Operation, purpose và business authorization |
| “Không hardcode là không có secret leak.” | Runtime/CI/log/trace/backup có thể chứa giá trị | DFD và multi-sink tests |
| “Base64 trong Kubernetes Secret là encryption.” | Chỉ là encoding | Review at-rest encryption + RBAC |
| “Environment variable luôn không an toàn.” | Rủi ro phụ thuộc OS/runtime/permissions | Threat model và scope, tránh tuyệt đối hóa |
| “Mounted file an toàn tuyệt đối.” | Process khác hoặc debug có thể đọc | File permissions, mounts, lifecycle |
| “Mask secret trong UI CI là đã loại rò rỉ.” | Artifacts/raw logs có thể còn dữ liệu | Synthetic canary và artifact inspection |
| “Secret scanner không báo lỗi thì review PASS.” | Không kiểm runtime, grants, operation misuse | Effective permissions, negative integration |
| “Mỗi release dùng chung API key cho tiện.” | Mất attribution, tăng blast radius | Per-service/tenant/environment scope |
| “Rotate đã xong vì key mới hoạt động.” | Old credential có thể còn usable | Effective revoke test và overlap expiry |
| “Xóa secret khỏi source là đã xử lý compromise.” | Git history/clones/artifacts/attacker vẫn có | Revoke/rotate, incident, purge theo policy |
| “Bearer token được gửi qua TLS thì không thể bị dùng lại.” | Token có thể bị lấy ở endpoint/log | Scope, TTL, audience, binding khi cần |
| “Secretless nghĩa không còn keys hoặc tokens.” | Broker/IdP còn cấp identity/credentials | Review trust issuer, grants, expiry |
| “Dùng HSM thì signing gateway tự biết payload hợp lệ.” | Hardware chỉ thực hiện cryptographic operation | Business approval binding, policy |
| “KMS outage thì tắt encryption tạm.” | Phá security objectives | Fail-safe/approved degraded mode |
| “Audit muốn chắc nên xin raw secret.” | Tạo bản sao/consumer không cần thiết | Metadata, policies và negative tests |
| “Read-only role không thể làm lộ secret.” | Read secret đủ để impersonate | Xem resource sensitivity và blast radius |
| “Một unit test policy pass đủ để kết luận IAM đạt.” | Mock/local input không phải runtime effective grant | KMS/IAM integration và production evidence |
| “Không có unusual sign operations thì không có abuse.” | Logging/detection có thể thiếu | Kiểm telemetry coverage và negative alert tests |
| “Exception được duyệt = control PASS.” | Exception thường xác nhận control gap có rủi ro được chấp nhận | Báo riêng status, expiry và residual risk |
| “Chỉ cần review secrets tồn tại trong secret manager.” | Legacy/third-party/hardcoded nằm ngoài inventory | Reconcile repo, CI, IAM, apps, runtime |
| “Mã hóa backup là không cần review secrets trong backup.” | Key copies, credentials và restore controls còn risk | Backup scope/retention/key custody |
| “Secret tự hết hạn nghĩa mọi session lập tức bị chấm dứt.” | Cache, DB pools, tokens có lifecycle riêng | Verify effective access latency |

## 33. Bài tập tình huống tổng hợp

Một công ty vận hành SaaS học tập nhiều tenant với:
- Learning API.
- Export worker.
- Analytics worker.
- CI/CD pipeline.
- Kubernetes cluster.
- Secret manager + KMS signing key.
- External email provider.
- Database và backup/DR.
- Logging/SIEM và support console.

Buổi design review phát hiện:

1. Export và analytics worker dùng chung database credential quyền đọc mọi bảng.
2. CI runner có quyền đọc secret production ngay cả khi chạy job trên nhánh thử nghiệm.
3. Private JWT signing key được lưu vào file tạm rồi load trong Java process mặc dù KMS có signing API.
4. Một signing key non-exportable nhưng signing gateway chấp nhận arbitrary payload không gắn approval.
5. HTTP middleware ghi Authorization header vào trace của bên thứ ba.
6. DB connection pool không tự reload credential sau rotation.
7. Secret manager outage khiến export job dùng password mẫu từ config.
8. Service account có quyền tạo pod, gắn service account khác và đọc namespace secrets.
9. Vendor API key không có owner, expire hoặc incident contact.
10. Audit report chỉ kèm ảnh chụp secret manager và kết quả scanner không có findings.

**Hãy giải quyết:**

1. Lập secret usage inventory theo producer, consumer, owner, type, purpose và environment.
2. Vẽ DFD thể hiện secret stores, signing operations, CI, logs, memory và các đường quyền gián tiếp.
3. Viết ít nhất tám risk scenarios, chỉ rõ trust boundary và blast radius.
4. Xác định điểm có thể thay raw credential bằng workload federation hoặc managed signing.
5. Viết requirements có acceptance criteria cho signing purpose, KMS IAM, CI trust, logging, rotation và fail-safe.
6. Thiết kế policy để export-worker không được dùng secret của analytics, tenant khác hoặc environment khác.
7. Viết negative tests cho arbitrary payload, wrong approval, wrong key alias, CI from untrusted branch và Kubernetes pod impersonation.
8. Xây runbook rotate DB/vendor credentials và kiểm old credential, connection pool, tokens và DR.
9. Xây Claim–Argument–Evidence **có giới hạn**, phân biệt design/implementation/operating.
10. Đề xuất findings, severity, owner, deadline, remediation và deployment-linked retest.
11. Xác định population và sampling cho một audit secret usage trong kỳ.
12. Đề xuất metrics về long-lived credentials, excessive grants, revoke latency và evidence freshness.

**Gợi ý tự kiểm:** Di chuyển JWT key vào KMS có thể giảm raw-key exposure nhưng không giải quyết arbitrary signing nếu KMS grants và business policy vẫn mở. Sửa CI bằng OIDC federation vẫn phải ràng buộc branch/environment. Xóa log header không đủ nếu token đã bị lộ: cần đánh giá revoke/incident. Credential rotation cần xử lý các connections cũ. Một review chỉ có screenshot vault phải ghi **INCONCLUSIVE** đối với các control chưa có runtime/negative test evidence.

## 34. Checklist review secret usage

### 34.1. Khởi tạo và inventory

- [ ] Xác định use case, data/resource scope, environment và trust boundaries.
- [ ] Inventory đủ human credentials, service tokens, API keys, cryptographic keys, certificates có private key, bootstrap và emergency secrets.
- [ ] Mỗi secret có owner, purpose, issuer, consumers và resource/action scope.
- [ ] Secret references được ghi, **raw values không đưa vào tài liệu review**.
- [ ] Đối chiếu inventory từ manager/KMS, IAM, CI, repo, cluster, apps và runtime.
- [ ] Đánh giá phương án loại static secret hoặc thay bằng workload federation/managed operation khi phù hợp.

### 34.2. Generation, custody và distribution

- [ ] Generation/issuance tuân crypto policy và identity approval.
- [ ] Không dùng default/shared secrets hoặc entropy yếu.
- [ ] Secret store/KMS/HSM có source of truth, version, access policy và audit.
- [ ] Key non-exportability, allowed operations và trust boundary được hiểu đúng.
- [ ] Runtime injection tránh image, shell history, command-line args và plaintext artifacts ngoài policy.
- [ ] File mounts/env/sidecar/SDK được đánh giá theo threat model thực tế.
- [ ] Memory/cache TTL, cleanup, permissions và revocation handling được xét.
- [ ] Backup/restore/DR chứa key/copies có access và retention rõ.

### 34.3. Identity, authorization và purpose

- [ ] Verified workload/user identity và service account riêng khi cần.
- [ ] IAM/KMS/secret manager grants theo service, action, key, tenant và environment.
- [ ] Quyền read khác quyền sign/decrypt/unwrap/grant/admin.
- [ ] Không có đường indirect privilege escalation qua CI, pod creation, role assumption hoặc policy editing.
- [ ] Key-use operation có business authorization/purpose binding khi cần.
- [ ] Signing service không ký arbitrary privileged payload ngoài scope.
- [ ] OAuth/webhook/mTLS token audience, TTL, binding và verification được kiểm.
- [ ] SoD, break-glass và admin overrides có owner/approval/audit.

### 34.4. Code, CI/CD và runtime exposure

- [ ] Không hardcode secret trong source, tests, configuration, image hoặc repository history.
- [ ] CI trust policy không cấp prod secrets cho PR/branch untrusted.
- [ ] Pipeline build/deploy/signing roles được giới hạn và kiểm effective permissions.
- [ ] Runtime không log credentials trong errors, HTTP headers, request bodies, traces hay metrics.
- [ ] Diagnostics/heap dumps/support bundles có controls và phạm vi xử lý.
- [ ] Synthetic secret canary và scanner có giới hạn được hiểu rõ.
- [ ] Không có fallback insecure khi secret/key/certificate bị thiếu.
- [ ] Secret reference/key alias không lấy trực tiếp từ untrusted request để mở tenant khác.
- [ ] Mọi direct/legacy/third-party access paths đều nằm trong scope.

### 34.5. Lifecycle, verification và assurance

- [ ] Có rotation triggers, expiry, overlap policy và rollback.
- [ ] Consumer reload/renew/connection pool/long-running jobs được thử khi rotate.
- [ ] Có effective revocation tests cho old credential/token/session/cache.
- [ ] KMS/provider outage và permission-denied fail safely theo risk.
- [ ] Key destruction và backup copies được đánh giá theo retention/restore.
- [ ] Positive/negative/failure-path tests gắn requirement và evidence IDs.
- [ ] Evidence có provenance, environment, release, version, timestamp và expected/actual outcome.
- [ ] Claim phân biệt design, implementation, operating effectiveness.
- [ ] Findings có criteria, condition, owner, root cause, severity, remediation và retest.
- [ ] Exceptions có risk owner, scope, approval, compensating controls và expiry.
- [ ] Metrics có denominator đầy đủ; tách PASS, FAIL và UNKNOWN.
- [ ] Thay workload, tenant, key, CI trust, KMS, logging, policy hoặc incident kích hoạt reassessment.

**Ghi nhớ:** **Review secret usage** là đánh giá **năng lực truy cập và sử dụng bí mật**, không chỉ vị trí lưu trữ một chuỗi ký tự. Trong **SECURITY_SECURITY_ASSURANCE**, cần chứng minh đúng **purpose, identity, key/secret custody, operation permissions, trust boundaries, lifecycle, safe failure và effective revocation**, bằng chuỗi **risk → requirement → control → test → runtime evidence → finding/remediation → reassessment**. Chỉ khi từng secret và quyền sử dụng nó được kiểm tra trong **đúng hệ thống, đúng môi trường, đúng release và thời kỳ**, reviewer mới có căn cứ đưa ra kết luận assurance có giới hạn thay vì khẳng định “đã dùng vault nên an toàn”.
