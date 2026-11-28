# Review kiến trúc: Đánh giá thiết kế bảo mật và xây dựng bằng chứng assurance

## 1. Review kiến trúc bảo mật là gì?

**Security architecture review** (review kiến trúc bảo mật) là hoạt động đánh giá có cấu trúc về cách các thành phần, danh tính, dữ liệu, quyền truy cập và ranh giới tin cậy của một hệ thống được thiết kế để đáp ứng **security objectives**, **security requirements** và những rủi ro đã xác định.

Nó trả lời: **“Thiết kế hệ thống có đặt security controls đúng vị trí, bao phủ các đường tấn công quan trọng và đủ khả năng được kiểm chứng hay không?”**

Ví dụ, một nền tảng SaaS lưu đơn hàng của nhiều tổ chức trong cùng database. Review kiến trúc không dừng ở câu hỏi “Database có mã hóa không?” mà phải xem:

- User A có thể sử dụng token hợp lệ để đọc order của tenant B không?
- Tenant ID được lấy từ danh tính đáng tin hay từ header do client tự gửi?
- Những luồng export, queue, cache và reporting có giữ ranh giới tenant không?
- Service account có quyền quá rộng hoặc bypass database policy không?
- Một webhook payment giả mạo hoặc replay có thể thay đổi trạng thái giao dịch không?
- Khi policy engine hoặc identity provider lỗi, hệ thống có fail-open không?
- Bằng chứng thiết kế, triển khai và vận hành nào sẽ chứng minh các quyết định là hiệu quả?

Trong module **SECURITY_SECURITY_ASSURANCE**, review kiến trúc là một phần của chuỗi:

**Business/asset → Threat/risk → Security objectives → Requirements → Architecture controls → Test/audit → Evidence → Assurance conclusion → Findings/remediation/retest.**

> **Nguyên tắc:** thiết kế được phê duyệt không có nghĩa production đã an toàn. Review kiến trúc chủ yếu tạo căn cứ về **design effectiveness**; kiểm tra code, cấu hình, test và vận hành là các lớp bằng chứng tiếp theo.

### 1.1. Vì sao cần review sớm?

Một quyết định sai ở tầng kiến trúc có thể lan ra hàng chục service. Nếu một hệ thống thiết kế mọi worker dùng cùng credential quản trị, vài unit test cuối dự án không thể giải quyết gốc vấn đề.

Review sớm giúp:

1. Phát hiện giả định tin cậy không đúng.
2. Chọn mô hình identity và authorization có thể thực thi nhất quán.
3. Giảm blast radius khi một thành phần bị compromise.
4. Phân biệt yêu cầu thực sự với giải pháp công nghệ mang tính thói quen.
5. Thiết kế observability và các điểm kiểm thử từ đầu.
6. Xác định ai sở hữu control, ai chấp nhận risk và ai đánh giá evidence.
7. Ghi trade-off để quyết định có thể được đánh giá lại khi điều kiện thay đổi.

### 1.2. Review kiến trúc không phải checklist tên công nghệ

Một kiến trúc có API gateway, Kubernetes, mTLS, KMS và WAF vẫn có thể rò dữ liệu chéo tenant. Reviewer phải xem **control có thực thi đúng security property tại trust boundary cần bảo vệ không**, thay vì đếm số công cụ đã mua.

Một gateway xác thực JWT không tự đảm bảo người dùng được phép đọc từng order. mTLS xác thực peer không tự phân quyền operation. Vault bảo vệ giá trị secret khi lưu nhưng có thể cấp secret cho workload quá quyền. NetworkPolicy tồn tại trong manifest chưa chứng minh CNI thực thi chặn traffic runtime.

## 2. Phân biệt architecture review với các hoạt động liên quan

| Hoạt động | Câu hỏi trọng tâm | Evidence / đầu ra | Giới hạn |
| --- | --- | --- | --- |
| **Architecture review** | Thiết kế kiểm soát các threat và đáp ứng requirements như thế nào? | Design findings, decisions, verification plan | Không tự chứng minh đã triển khai |
| **Threat modeling** | Attacker có thể lợi dụng entry point, asset và trust boundary nào? | Threat scenarios, abuse cases | Chưa chứng minh controls hiệu quả |
| **Secure code review** | Code có thực thi security invariant và tránh lỗi không? | Code findings, review records | Có thể bỏ lỡ vấn đề toàn hệ thống |
| **Security testing** | Hành vi thực của build/config có đúng yêu cầu? | Test cases và actual results | Chỉ bao phủ các đường được test |
| **Cloud/config review** | IAM, network, runtime, IaC có đúng policy? | Config findings, runtime checks | Không thay application authorization |
| **Compliance audit** | Những nghĩa vụ đã xác nhận áp dụng có được đáp ứng? | Audit conclusions, gaps | Có tài liệu chưa chắc control vận hành |
| **Privacy review** | Mục đích, minimization, retention, data subject rights có được bảo vệ? | Privacy risks, controls | Bảo mật kỹ thuật chưa đủ toàn bộ privacy |
| **Architecture Decision Record (ADR)** | Vì sao chọn phương án kiến trúc này? | Decision, options, rationale | ADR không phải kết quả test |

Các hoạt động này **bổ sung nhau**. Threat model cung cấp các tình huống cần phòng, architecture review quyết định cách bảo vệ, security tests và operating reviews xác minh hiệu quả.

### 2.1. Ba câu hỏi phải phân biệt

- **Design effectiveness:** nếu triển khai đúng như thiết kế, control có khả năng giải quyết threat không?
- **Implementation effectiveness:** code, IAM, RLS, network policy và cấu hình có hiện thực hóa đúng thiết kế không?
- **Operating effectiveness:** trong thời gian và môi trường đang đánh giá, control có duy trì hiệu quả không?

Ví dụ thiết kế chỉ định tenant-scoped repository là hợp lý; unit test của service có thể đạt; nhưng nếu production worker dùng một truy vấn không giới hạn tenant thì overall assurance vẫn có gap.

## 3. Khi nào cần review kiến trúc?

Review theo **rủi ro và mức độ thay đổi ranh giới**, không nhất thiết tổ chức họp lớn cho mọi sửa đổi nhỏ.

### 3.1. Những trigger quan trọng

- Ra mắt hệ thống, sản phẩm, public API hoặc service mới.
- Thay identity provider, authentication, authorization hay tenant model.
- Chuyển single-tenant sang multi-tenant hoặc mở delegated/support access.
- Thêm dữ liệu Restricted/Confidential hoặc mục đích xử lý mới.
- Thêm cache, queue, data lake, search/vector store, AI/RAG hoặc reporting pipeline.
- Thêm payment provider, webhook, external integration hoặc third-party processor.
- Thay network zone, cloud account/project, cluster hoặc region.
- Thay key management, secret distribution hoặc encryption trust boundaries.
- Thêm privileged automation, CI/CD path hoặc admin/control plane.
- Thay transaction workflow như refund, chuyển tiền, provisioning, recovery.
- Sau incident/pentest/audit phát hiện lỗi kiến trúc lặp lại.
- Thay security standard, policy hoặc nghĩa vụ được xác nhận áp dụng.

### 3.2. Review ở nhiều mức

| Mức review | Phạm vi | Đầu ra |
| --- | --- | --- |
| **Lightweight** | Change có risk thấp, không tạo boundary mới | Changed control impact và regression tests |
| **Focused** | Một service, một luồng dữ liệu hay identity boundary | DFD/sequence, risks, design findings |
| **Full architecture** | Nền tảng mới, nhiều tenant, dữ liệu nhạy cảm, control plane | Architecture views, threat model, ADR, owners, gates |
| **Post-incident redesign** | Root cause mang tính hệ thống | Architecture remediation và cross-service retest |

Mức review cần có rationale. Đừng bỏ review một thay đổi quan trọng chỉ vì thay ít dòng code.

## 4. Chuẩn bị trước phiên review

### 4.1. Input checklist

Tối thiểu nên có:

1. **Business context:** use cases, user journeys, tài sản và mức ảnh hưởng.
2. **Review scope:** design revision, services, environments, inclusions và exclusions.
3. **Data inventory:** loại dữ liệu, classification, owner, destinations.
4. **System context diagram:** actors, workloads và vendor.
5. **Data Flow Diagram (DFD):** nguồn, đích, đường dữ liệu, trust boundaries.
6. **Identity model:** issuers, subjects, roles, machine identities, token propagation.
7. **Threat model/risk assessment:** scenarios, attack paths và priorities.
8. **Security requirements:** control objectives, source, version và applicability.
9. **Deployment/network view:** ingress, egress, IAM, clusters, data stores.
10. **Key sequences:** authentication, export, payment, admin, recovery.
11. **Alternatives/constraints:** latency, cost, delivery, operability.
12. **Existing evidence:** trước đây đã review/test những gì và còn gaps nào.

Nếu tài liệu chưa đủ, reviewer có thể ghi **INSUFFICIENT_DESIGN_INFORMATION** thay vì tự suy đoán một đường dữ liệu “chắc là đã có”.

### 4.2. Các architecture views cần biết

| View | Câu hỏi |
| --- | --- |
| **Context** | Ai tương tác với hệ thống, ai ở ngoài trust zone? |
| **Component/container** | Chức năng và quyền được phân bổ cho những thành phần nào? |
| **DFD** | Dữ liệu đi từ đâu tới đâu, qua boundary nào? |
| **Deployment** | Process, container, VM, network, secrets chạy/lưu ở đâu? |
| **Identity & access** | Principal nào được làm action nào trên resource nào? |
| **Sequence** | Các bước phụ thuộc thời gian, transaction, queue, retry xảy ra thế nào? |
| **Data lifecycle** | Tạo, lưu, cache, search, export, backup và xóa dữ liệu thế nào? |
| **Control plane** | Ai có quyền sửa IAM, policy, deployment, vault và audit? |

Không nhất thiết cần tám sơ đồ riêng. Quan trọng là có đủ góc nhìn để review các **boundary quan trọng**.

### 4.3. Sơ đồ phải có ý nghĩa bảo mật

Một DFD hiệu quả nên ghi:

- Dữ liệu nào được truyền và mức phân loại.
- Direction, protocol và mục đích.
- Principal hoặc workload identity dùng trong luồng.
- Điểm authentication, authorization và encryption.
- External service và nơi dữ liệu được lưu.
- Boundaries giữa tenant, environment, network, control/data plane.
- Đường async và backup/logging, không chỉ HTTP request chính.
- Assumptions, version và phạm vi chưa được thể hiện.

Một diagram lỗi thời hoặc ghi “internal = trusted” không đủ hỗ trợ kết luận.

## 5. Quy trình security architecture review từ đầu đến cuối

### Bước 1. Xác định quyết định cần đưa ra

Review nhằm cho phép triển khai, yêu cầu redesign, phê duyệt phương án hoặc kiểm tra một change? Ghi review ID, owner, design version, risk tier, scope và time window.

### Bước 2. Đi qua business flow với engineering owner

Mô tả các thao tác bình thường, đặc biệt là luồng chứa dữ liệu nhạy cảm và quyền mạnh. Đặt câu hỏi:

- Actor nào khởi tạo?
- Ai xác thực actor?
- Workload nào dùng quyền để đọc/sửa tài nguyên?
- Nếu request không hợp lệ thì ai từ chối?
- Dữ liệu nào được tạo hoặc lưu?
- Những side effect nào xuất hiện qua worker/provider?

### Bước 3. Đánh dấu trust boundaries và assets

Tìm crossing giữa client/gateway, user/resource authorization, workload/DB, internal/external provider, queue/worker, data/control plane, tenant A/B, staging/prod. Mỗi crossing là nơi có thể cần control.

### Bước 4. Xây threat scenarios

Dùng STRIDE, misuse cases, known incidents và risk register. Threat phải chứa **attacker capability, entry point, precondition, asset, impact**.

Ví dụ: user A có token hợp lệ, biết order UUID của B và gửi request tới API đọc order.

### Bước 5. Map threat sang requirement và control

Ghi:

- Security requirement và source.
- Control thực thi tại boundary có thẩm quyền.
- Defense-in-depth.
- Owner và dependency.
- Failure behavior.
- Positive/negative/bypass test cần chạy.
- Monitoring và recovery.
- Residual risk còn lại.

### Bước 6. Challenge assumptions

Hãy đặt các câu hỏi ngược:

- Nếu token/secret bị lộ?
- Nếu service account bị compromise?
- Nếu event bị duplicate, delayed, reordered?
- Nếu client giả tenant/role?
- Nếu policy engine timeout?
- Nếu cache giữ quyền cũ?
- Nếu webhook thiếu signature hoặc replay?
- Nếu operator sửa policy của chính mình?
- Nếu một tenant chiếm hết resource?
- Nếu backup restore đưa lại dữ liệu/credential đã xóa?

Mục tiêu là tìm **failure mode và bypass path**, không chỉ chứng minh happy path.

### Bước 7. So sánh alternatives

So sánh risk reduction, complexity, cost, latency, operational burden, testability, migration, rollback, vendor dependency và blast radius. Ghi những trade-offs trong ADR.

### Bước 8. Lập findings và architectural decisions

Không viết “fix security” chung chung. Mỗi finding cần threat, gap, owner, severity/risk, action, deadline và closure evidence. Nếu có exception, ghi người phê duyệt, thời hạn và risk còn lại.

### Bước 9. Quyết định design gate và verification plan

Một thiết kế có thể **được phê duyệt để triển khai có điều kiện** nhưng chưa được phát hành. Chỉ rõ tests, runtime evidence, code/config review, audit cần trước release hoặc trước khi kết luận assurance.

### Bước 10. Re-review khi thay đổi

Nếu tenant model, data store, provider, token trust, cache, queue, network hoặc policy thay đổi, phải phân tích impact và xác định review lại phần bị ảnh hưởng. Không dựa mãi vào design approval cũ.

## 6. Flowchart của quá trình review

~~~mermaid
flowchart TD
    A["Design / Change request"] --> B["Scope + Owner + Risk tier"]
    B --> C["Gather DFD, assets, requirements"]
    C --> D["Map trust boundaries + threat scenarios"]
    D --> E["Evaluate controls and assumptions"]
    E --> F{"Design gaps or unresolved decisions?"}
    F -- "Yes" --> G["Findings / Alternatives / ADR"]
    G --> H["Revise design or bounded risk decision"]
    H --> D
    F -- "No" --> I["Conditional design approval"]
    I --> J["Verification plan: code, config, tests"]
    J --> K["Implementation and runtime evidence"]
    K --> L{"Requirements met with sufficient evidence?"}
    L -- "No / Unknown" --> M["Remediation, retest or collect evidence"]
    M --> K
    L -- "Yes" --> N["Assurance conclusion within scope"]
    N --> O["Monitor change, drift and incidents"]
    O --> B
~~~

Cần tách hai kết luận: **design review PASS theo phạm vi** và **control effective theo evidence triển khai/vận hành**.

## 7. Review theo STRIDE và trust boundary

STRIDE giúp hệ thống hóa câu hỏi:

| Threat class | Câu hỏi review | Ví dụ |
| --- | --- | --- |
| **Spoofing** | Có thể giả user, workload hoặc vendor? | Fake payment webhook |
| **Tampering** | Có thể sửa message, permission, state, policy? | Đổi tenant trong event |
| **Repudiation** | Có thể chối bỏ hành động do thiếu audit? | Refund không có actor |
| **Information Disclosure** | Dữ liệu có lộ qua path khác không? | Cache trả order tenant B |
| **Denial of Service** | Một actor có làm hết quota hoặc queue không? | Noisy-neighbor tenant |
| **Elevation of Privilege** | Từ user/service lên admin/host? | Worker có global DB admin credential |

STRIDE là công cụ hỗ trợ, không có nghĩa đã tìm mọi threat. Hệ thống còn cần xem business abuse, privacy, supply chain, insider và recovery theo bối cảnh.

### 7.1. Một trust boundary cần hồ sơ gì?

Một boundary record nên có:

- Boundary ID, source và destination.
- Data types và classification.
- Trust assumptions.
- Caller identity và cách xác minh.
- Authorization semantics và resource scope.
- Integrity, confidentiality, replay controls.
- Failure behavior.
- Owner và monitoring.
- Threats, requirements, tests và evidence references.

### 7.2. Confused deputy

Một service có quyền rộng hơn caller có thể bị lợi dụng để thực hiện một action caller không được phép.

Ví dụ report worker có quyền đọc tất cả tenant; user A gửi event mang tenant B, worker tạo báo cáo B và đưa link cho A. **Xác thực user A không giải quyết vấn đề**, vì worker đã dùng quyền riêng vượt phạm vi user.

Thiết kế đúng yêu cầu worker chỉ xử lý **verified context** và authorization ở resource boundary, cùng scoped workload permissions và audit.

## 8. Lăng kính Identity, Authentication và Authorization

### 8.1. Các câu hỏi về identity

- Issuer nào cấp user token và workload token?
- Token có được kiểm tra signature/proof, issuer, audience, expiry và claims?
- Có tin header tự khai từ client không?
- Service-to-service dùng danh tính riêng hay shared credential?
- Session revoke và permission revocation có semantics rõ?
- Support impersonation/break-glass có giới hạn phạm vi/thời gian?
- IdP unavailable thì operation nào deny, hold hay degraded?
- Mỗi môi trường dùng identity/credential riêng?

### 8.2. Các câu hỏi về authorization

- Kiểm tra subject–action–resource–context ở đâu?
- Function-level authorization khác object-level authorization thế nào?
- Ai xác minh tenant membership và resource ownership?
- Có cách gọi trực tiếp service bỏ qua gateway?
- Worker, export, search, cache có cùng invariant?
- Quyền thay đổi giữa check và use có được xử lý?
- Những account admin có thể bypass mọi policy không?
- Mỗi policy decision có audit metadata mà không lộ secret?

### 8.3. Điểm quyết định và thực thi quyền

Có thể tách:

- **Policy Decision Point (PDP):** xác định action có được phép.
- **Policy Enforcement Point (PEP):** chặn/cho phép tại nơi thao tác.
- **Policy Information Point (PIP):** cung cấp identity, group, ownership và context.

Nếu authorization được quyết định ở API nhưng report worker đi đường khác, cần một PEP phù hợp tại worker/data boundary. Không nên dựa duy nhất vào UI ẩn nút hoặc gateway xác thực.

## 9. Lăng kính Tenant Isolation và Data Access

### 9.1. Các dạng isolation

| Mô hình | Ưu điểm | Rủi ro phải review |
| --- | --- | --- |
| Shared DB + tenant column | Hiệu quả và đơn giản | Query/join/bulk thiếu filter |
| Shared DB + RLS | DB có lớp phòng vệ thêm | Session context, bypass role, connection pool |
| Schema/database per tenant | Boundary rõ hơn | Connection routing, migration, credential |
| Dedicated workload/account | Giảm một số blast radius | Cost, shared admin, central pipeline và drift |
| Hybrid | Điều chỉnh theo risk tier | Chính sách không nhất quán giữa các tier |

Tách database không tự đảm bảo an toàn nếu service account cùng credential có thể truy cập tất cả hoặc mapping tenant → DB sai.

### 9.2. Các đường dễ bị bỏ qua

- Cached response không có tenant trong key.
- Search/vector index thiếu tenant filter server-side.
- Export file được gán link cho user khác.
- Worker không revalidate hoặc kiểm tra provenance của message.
- Analytics/reporting dùng service account rộng.
- Backup restore trộn tenant.
- Support console có quyền global không có case-level authorization.
- Object storage prefix tách nhưng bucket policy rộng.

### 9.3. Data minimization và privacy

Security architecture review cần xem:

- Dữ liệu nào là cần thiết cho từng purpose?
- Có thu thập/truyền thêm PII qua event và log?
- Retention/deletion ở cache, data lake và backup?
- Data processor nhận đúng fields và điều kiện?
- Dữ liệu dùng trong analytics/AI có nguy cơ re-identification?
- Security evidence có tự tạo bản sao dữ liệu nhạy cảm không?

Những nghĩa vụ privacy cụ thể phụ thuộc context và luật được xác nhận áp dụng; **không tự coi consent là cơ sở cho mọi hoạt động xử lý**.

## 10. Lăng kính Network, Runtime và Control Plane

### 10.1. Network trust

- Public ingress nên tới những workload nào?
- DB/cache có public endpoint không cần thiết?
- Egress ra Internet hoặc metadata endpoint có giới hạn?
- Một compromised pod có thể gọi admin API nội bộ?
- Có default-deny ingress/egress hay rule allow-all rộng?
- mTLS có bảo vệ peer identity và còn authorization ở app?
- Network policy được bảo vệ khỏi actor thay đổi label/rule?
- Có runtime connectivity test, không chỉ manifest?

### 10.2. Container và Kubernetes

Các điểm cần xem:

- Chạy privileged hay host mount/host network không cần thiết?
- Non-root, capabilities, seccomp và MAC theo baseline?
- Service account đọc Secret/RoleBinding đến mức nào?
- Namespace isolation có đi cùng RBAC, NetworkPolicy và quota?
- Cluster admin có thể vượt boundary giữa tenant?
- Image/runner có credential sản xuất?
- Node pool/VM riêng có cần theo risk?
- ResourceQuota và backpressure có hạn chế noisy neighbor?

Container thường chia sẻ kernel host nên không đồng nghĩa VM. Chọn isolation theo threat model và mức đáng tin của code.

### 10.3. Control plane

Control plane quản lý quyền, cấu hình và deployment; rủi ro thường cao hơn data-plane requests:

- Tenant admin có thể tạo global role không?
- CI pipeline staging có quyền deploy production không?
- Ai đọc secrets và ai sửa policy vault?
- Ai có thể xóa audit về chính hành động của mình?
- Break-glass có alert, phê duyệt và review sau sử dụng?
- Quản trị cloud có được tách account/project không?

Nếu control plane bị chiếm, các controls ở data plane có thể bị tắt. Vì thế control-plane boundaries là phần quan trọng của architecture review.

## 11. Lăng kính Data Protection, Encryption và Secret Management

### 11.1. Data flow và lifecycle

Lập danh sách database, cache, queue, search/index, analytics, object storage, backup, snapshot, audit và vendor. Với mỗi data flow, ghi:

- Loại dữ liệu và classification.
- Owner và purpose.
- Principal/workload xử lý.
- Encryption/authorization.
- Retention và deletion.
- Trust boundary và destination.
- Audit/monitoring và failure behavior.

Một DFD chỉ vẽ tuyến browser → API → DB có thể bỏ qua luồng rò thực tế qua debug log hoặc export worker.

### 11.2. Cryptography review

Các câu hỏi quan trọng:

- TLS termination và đường được mã hóa nằm ở đâu?
- Thuật toán/mode/key length có được baseline áp dụng cho phép?
- Keys do KMS/HSM/vault quản lý với role nào?
- Ai có quyền encrypt/decrypt/sign?
- Key rotation và revocation có ảnh hưởng consumer thế nào?
- Ciphertext có integrity/authentication phù hợp?
- Secret có bị đưa vào source, image, log hoặc environment dump?
- Backup/restore có thể hồi sinh credential cũ không?
- Có separation giữa production và development keys không?

Không tự xác định một thuật toán hoặc thời hạn rotation là bắt buộc chung; cần nguồn standard/policy và version có hiệu lực.

### 11.3. Vault không phải toàn bộ giải pháp

Một vault có thể bảo vệ secret at rest nhưng vẫn cho phép một workload dùng token toàn quyền đọc mọi secret.

Reviewer cần xem identity, least privilege, dynamic credentials, rotation/revoke, audit, bootstrap secret, availability, connection pool và incident response.

## 12. Lăng kính External Integration, Webhook và Async Processing

### 12.1. Webhook payment

Một webhook nhận event từ nhà cung cấp bên ngoài, rồi cập nhật trạng thái đơn hàng. Đây là trust boundary quan trọng.

Câu hỏi:

- Sender được xác minh bằng signature/MAC hoặc cơ chế đáng tin nào?
- Có kiểm tra integrity của raw body và metadata cần thiết?
- Có timestamp/nonce/event ID và replay protection phù hợp?
- Có đối chiếu order, amount, currency, tenant với trạng thái server?
- Event trùng, out-of-order và timeout được xử lý thế nào?
- Có transaction/unique constraint để chống duplicate business effect?
- Signing secret có được rotate/revoke không?
- Audit có nối event provider với order và quyết định?

IP allowlist có thể hỗ trợ nhưng thường không thay toàn bộ kiểm tra integrity và business mapping.

### 12.2. Queue và worker

- Ai được publish vào topic/queue?
- Event provenance và schema được xác minh thế nào?
- Dữ liệu trong dead-letter queue có bị giữ quá lâu hoặc lộ PII?
- Worker có quyền quá rộng?
- Event có tenant/actor context đáng tin?
- Retry/replay có làm thực hiện lại payment/refund?
- Có outbox/inbox hoặc idempotent processing?
- Có reconcile với state nguồn không?
- Khi consumer lỗi, dữ liệu có bị phát sai đích?

“Đã có idempotency key” không chứng minh exactly-once business effect nếu key không được lưu và kiểm tra nguyên tử tại transaction boundary.

### 12.3. SSRF và egress

Một service có chức năng tải URL do user cung cấp có thể bị lợi dụng gọi metadata endpoint hoặc internal admin API. Review cần xét URL validation, redirect, DNS, IPv4/IPv6, proxy, egress firewall, service identity và hạn quyền. Không chỉ chặn vài chuỗi URL bằng regex.

## 13. Lăng kính Availability, Recovery và Operations

### 13.1. Availability threats

Một tenant hoặc client có thể làm cạn:

- API rate budget.
- Database connections.
- CPU/memory hoặc worker threads.
- Queue backlog.
- Storage/temporary disk.
- External provider quota.
- Cache hoặc expensive query.

Review architecture cần quota, rate limit, backpressure, timeout, load-shedding, circuit breakers và resource isolation theo threat và SLO.

### 13.2. Failure modes

Ví dụ:

| Dependency lỗi | Failure behavior cần xác định |
| --- | --- |
| Authentication/identity service | Deny/hold hoặc degraded mode theo yêu cầu, không tự bypass |
| Authorization policy service | Không phát dữ liệu ngoài scope; alert và retry thích hợp |
| Secret manager | Không fallback sang hard-coded/default credential |
| Queue | Không mất business state hoặc gửi duplicate ngoài kiểm soát |
| Payment provider | Timeout/reconciliation/idempotency, không coi unknown là success |
| Audit pipeline | Cơ chế buffer/retry/block tùy operation và risk policy |
| Database | Không trả dữ liệu cache khác tenant, có recovery plan |
| KMS/key service | Không dùng weak plaintext fallback để tiếp tục xử lý |

Không có một câu trả lời “fail-closed mọi nơi” cho tất cả use cases. Thiết kế cần xác định **nghĩa vụ bảo vệ, availability và phương án được phê duyệt**.

### 13.3. Backup/restore và incident containment

- Có RPO/RTO được business/risk owner phê duyệt?
- Backups được mã hóa, phân quyền và cách ly đủ?
- Control-plane admin có thể xóa cả backup và audit không?
- Restore có phải replay data deletion/revoke state?
- Restore có giữ tenant boundary, permission và integrity?
- Có kiểm thử khôi phục với kết quả đo được?
- Hệ thống có khả năng cô lập compromised service/tenant không?

Backup tồn tại chưa chứng minh restore sẽ thành công và bảo đảm confidentiality/integrity.

## 14. Case study: Review kiến trúc Orders API multi-tenant

### 14.1. Bối cảnh giả định

Một nền tảng thương mại điện tử dùng **Java/Spring Boot** để phục vụ nhiều khách hàng tổ chức.

Thành phần gồm browser/mobile, API gateway, identity provider, Orders API, PostgreSQL chung, Redis, outbox/event bus, report worker, private export storage, payment webhook receiver, vault và audit pipeline.

Dữ liệu nhạy cảm: địa chỉ giao hàng, email liên hệ, giá trị đơn hàng và trạng thái thanh toán.

Người dùng: customer, tenant admin, support operator và platform operator.

### 14.2. Data Flow Diagram

~~~mermaid
flowchart LR
    U["Browser / Mobile"] -->|"Authenticated request"| GW["API Gateway"]
    GW -->|"Verified identity context"| API["Orders API"]
    API --> AUTHZ["Authorization / Membership"]
    API --> DB[("PostgreSQL Orders")]
    API --> CACHE[("Redis Cache")]
    API --> OUT[("Outbox / Event Bus")]
    OUT --> WORK["Report Worker"]
    WORK --> FILES[("Private Export Storage")]
    P["Payment Provider"] -->|"Signed webhook"| HOOK["Webhook Receiver"]
    HOOK --> API
    VAULT["Secret Manager"] --> API
    VAULT --> WORK
    SUPPORT["Support Operator"] -->|"Scoped support access"| API
    API --> AUDIT[("Protected Audit")]
    WORK --> AUDIT
~~~

Các trust boundaries:

- **TB-01:** Internet client → API gateway/backend.
- **TB-02:** authenticated principal → tenant/resource authorization.
- **TB-03:** Orders API → DB/cache dùng service privileges.
- **TB-04:** event producer → queue → worker/export storage.
- **TB-05:** external payment provider → webhook receiver.
- **TB-06:** support operator → dữ liệu tenant.
- **TB-07:** workloads → vault/audit/control plane.

Sơ đồ này chỉ là mô hình học tập, không phải kết quả đánh giá production.

### 14.3. Review theo attack path

| Threat ID | Attacker capability | Attack path | Impact |
| --- | --- | --- | --- |
| THR-ORD-01 | User A có token hợp lệ | Thay order ID B | Cross-tenant data disclosure |
| THR-ORD-02 | Có thể gửi report request | Fake tenant ID trong queued event | Export dữ liệu tenant khác |
| THR-ORD-03 | Gửi được callback hoặc replay | Fake/duplicate payment webhook | State hoặc amount sai |
| THR-ORD-04 | User mất quyền | Cache/session cũ vẫn allow | Unauthorized data access |
| THR-ORD-05 | Compromised worker | Service credential đọc mọi tenant | Lateral movement / mass export |
| THR-ORD-06 | Tenant tạo tải cao | Chiếm DB pool/queue | Availability incident |
| THR-ORD-07 | Support user quá quyền | Xem các tenant không có case | Excessive privileged access |
| THR-ORD-08 | CI credential lộ | Deploy artifact trái phép | Compromise production |
| THR-ORD-09 | Policy engine timeout | API fail-open | Authorization bypass |

### 14.4. Design controls cho THR-ORD-01

Security objective: không có dữ liệu order của tenant B bị tiết lộ cho principal A ngoài quyền.

Các controls:

1. Principal và tenant membership xác minh từ identity source đáng tin.
2. Object-level authorization trước khi trả dữ liệu.
3. Query repository có tenant scope.
4. RLS hoặc data-layer policy nếu phù hợp với threat model.
5. Cache/search áp cùng tenant and permission scope.
6. Audit và phát hiện anomalous access.
7. Fail-safe nếu thiếu principal/policy context.
8. Negative tests trên API, export, worker và cache.

Một JWT hợp lệ ở gateway chỉ chứng minh authentication, không đủ bảo đảm authorization.

### 14.5. Design controls cho THR-ORD-02

- Producer chỉ tạo event sau authorization.
- Tenant/actor context có provenance từ service đáng tin.
- Consumer xác minh event source và binding tới resource.
- Worker có least-privilege role, không mặc định admin global.
- Export artifact chỉ chứa dữ liệu được phép.
- Download URL/link có recipient scope và expiry.
- Retry/dead-letter giữ context, không phát bản sao ngoài scope.
- Có reconciliation và protected audit.

### 14.6. Design controls cho THR-ORD-03

- Verify signature/MAC và sender identity trước side effect.
- Xác thực event ID/timestamp theo replay policy.
- Mapping order/amount/currency tới server-side transaction.
- Idempotency được thực thi nguyên tử ở DB/state machine.
- Không chuyển order từ state không hợp lệ chỉ vì event đến.
- Audit outcome, retry và reconciliation provider.
- Revoke/rotate signing secret khi compromise.

Review cần kiểm tra **exact trust boundary** và điểm quyết định chứ không chỉ note “signed webhook”.

### 14.7. Conditional review conclusion

Ví dụ kết luận hợp lý:

> Thiết kế Orders API có thể tiếp tục triển khai với điều kiện tenant context được xác minh từ identity source, repository/cache/worker áp authorization nhất quán, webhook có integrity và idempotent state transitions, và các negative/integration tests được chạy trước release. Các phần audit production, rollback và actual network IAM chưa được đánh giá nên chưa có kết luận operating effectiveness.

Kết luận này rõ hơn “Architecture approved: secure”.

## 15. Java/Spring Boot: một security design có thể review

### 15.1. Anti-pattern: authentication bị nhầm với authorization

~~~java
// KHONG AN TOAN neu caller khong duoc kiem tra owner/tenant.
public OrderDto getOrder(UUID orderId) {
    return repository.findById(orderId)
            .map(OrderDto::from)
            .orElseThrow(ResourceNotFoundException::new);
}
~~~

Một authenticated user có thể biết UUID của order thuộc tenant khác. UUID khó đoán không phải security control.

### 15.2. Tenant-scoped service

~~~java
public record VerifiedPrincipal(
        String subjectId,
        UUID tenantId,
        Set<String> permissions) {
}

public interface OrderRepository {
    Optional<Order> findByIdAndTenantId(UUID id, UUID tenantId);
}

@Service
public final class OrderQueryService {
    private final OrderRepository repository;
    private final OrderPolicy policy;

    public OrderQueryService(
            OrderRepository repository,
            OrderPolicy policy) {
        this.repository = repository;
        this.policy = policy;
    }

    public OrderDto getOrder(UUID orderId, VerifiedPrincipal caller) {
        // Principal phai duoc xay tu authentication va membership tin cay.
        policy.requireAllowed(caller, "orders.read", caller.tenantId());

        Order order = repository
                .findByIdAndTenantId(orderId, caller.tenantId())
                .orElseThrow(ResourceNotFoundException::new);

        return OrderDto.from(order);
    }
}
~~~

**Điều kiện thiết kế:**

- VerifiedPrincipal được xây ở server sau xác minh token, không bind trực tiếp từ JSON/header client.
- OrderPolicy kiểm tra action/resource/tenant theo quy tắc thật, không chỉ một boolean từ client.
- Query implementation và DB roles phải được kiểm tra thực tế.
- Worker/export/cache không tự bypass policy.
- Audit metadata phản ánh actor, resource, tenant và decision.
- Quyền support đặc biệt phải có case/scope/time/approval nếu policy yêu cầu.

Đoạn code là ví dụ minh họa, chưa chứng minh hệ thống thực triển khai đúng.

### 15.3. Fail-safe khi policy service lỗi

~~~java
public AccessDecision authorizeExport(
        VerifiedPrincipal caller, UUID tenantId) {
    if (caller == null || tenantId == null
            || !tenantId.equals(caller.tenantId())) {
        return AccessDecision.DENY;
    }

    try {
        return policyClient.evaluate(caller, "orders.export", tenantId);
    } catch (PolicyServiceUnavailableException ex) {
        audit.recordPolicyUnavailable("orders.export", tenantId);
        return AccessDecision.DENY;
    }
}
~~~

Đây là failure behavior **minh họa** cho export Confidential theo policy deny-on-indeterminate. Nếu yêu cầu availability đặc thù, cần thiết kế degraded behavior được phê duyệt, không tự sử dụng admin fallback.

### 15.4. Thiết kế DB RLS có thể bổ trợ

Ví dụ PostgreSQL ở mức thiết kế:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_policy
ON orders
USING (
    tenant_id = current_setting('app.tenant_id', true)::uuid
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)::uuid
);
~~~

Các câu hỏi review:

- Application DB role có quyền bypass RLS không?
- Tenant context được set từ principal tin cậy và **reset đúng** khi reuse connection?
- App có dùng transaction-local context thay vì giữ session state sai?
- Stored procedures hoặc background jobs có bypass?
- Có negative tests cho query, update, bulk, join, connection pool?
- Có đường admin/migration riêng và được review?

RLS không thay application authorization. Nếu current_setting thiếu hoặc không hợp lệ, cần kiểm tra thực tế behavior và error-handling của ORM/driver.

### 15.5. Test matrix từ quyết định kiến trúc

| Scenario | Kết quả cần chứng minh |
| --- | --- |
| A đọc order A được phép | Success và đúng dữ liệu |
| A đọc order B | Deny/no data B |
| A gửi tenant header của B | Không thay quyền thực |
| A dùng bulk export có order B | Không phát dữ liệu B |
| Policy engine unavailable | Không fail-open |
| Cache có response tenant B | A không nhận B |
| Worker nhận event giả tenant | Reject/quarantine |
| User bị revoke membership | Quyền không tiếp tục trái semantics |
| DB connection pool tái sử dụng | Không giữ tenant context cũ |
| Webhook invalid signature | Không thay order state |
| Webhook duplicate/replay | Không tạo duplicate effect |
| Support không có approved case | Không có cross-tenant access |

Test cần ghi build, environment, fixtures và actual results; test plan không phải evidence PASS.

## 16. So sánh phương án và trade-off

Giả sử có ba lựa chọn:

- **A:** shared DB + application authorization.
- **B:** shared DB + application authorization + DB RLS.
- **C:** dedicated DB per tenant.

| Tiêu chí | A | B | C |
| --- | --- | --- | --- |
| Chi phí và vận hành | Thường thấp hơn | Tăng complexity policy/session | Tăng số DB, migration, connections |
| Defense-in-depth khi app query sai | Ít lớp hơn | RLS có thể chặn nếu role/context đúng | Cách ly theo DB, vẫn có routing risk |
| Blast radius credential | Lớn nếu role rộng | Phụ thuộc RLS và role | Có thể nhỏ hơn nếu credential tách |
| Tenant routing | Query filter | Query + session context | DB routing phải đúng |
| Backup/restore | Cần lọc tenant | Cần xét RLS/recovery | Có thể thuận tiện per-tenant nhưng tốn chi phí |
| Test complexity | API/query tests | Thêm RLS/bypass/pool tests | Thêm routing/admin/DB isolation tests |

Không có phương án tuyệt đối. Chọn theo data sensitivity, attacker model, operating capability, scale và assurance expectations.

### 16.1. Một ADR nên ghi gì?

- Decision ID và revision.
- Context, mục tiêu, source requirements.
- Alternatives, benefits, risks và limitations.
- Assumptions và cách xác minh.
- Quyết định/rationale.
- Control owner và risk owner.
- Implementation dependencies.
- Required tests, release gate và evidence.
- Residual risk và exceptions.
- Triggers để đánh giá lại.

### 16.2. Không nới yêu cầu bằng cách đổi tên solution

Nếu một yêu cầu bắt buộc là “không cho truy cập dữ liệu khác tenant”, việc thay “database riêng” bằng “shared DB + RLS” chỉ hợp lệ nếu đáp ứng **mức bảo vệ yêu cầu** và được review/phê duyệt trong scope. Không được đổi requirement thành “có tenant column” để đạt trên giấy.

## 17. Findings và remediation trong design review

### 17.1. Các loại gap

| Loại finding | Ví dụ |
| --- | --- |
| **Design gap** | Export worker không có authorization boundary |
| **Requirement gap** | Chưa xác định mục tiêu kiểm soát data residency |
| **Identity gap** | Client-supplied role được coi là trusted |
| **Isolation gap** | Service account chung cho toàn bộ tenants |
| **Data-flow gap** | Không biết bản sao trong analytics/backup |
| **Control-plane gap** | Deployment runner đọc production secrets không cần |
| **Failure-mode gap** | Authz timeout dẫn tới allow-all |
| **Availability gap** | Tenant chiếm hết DB pool |
| **Ownership gap** | Không có owner xử lý key revoke/downstream deletion |
| **Evidence gap** | Không có test/runtime verification cho claim |
| **Decision gap** | Residual risk chưa có approval |
| **Architecture drift** | Deployment thực tế khác ADR/diagram |

### 17.2. Finding record

Một finding nên có:

- ID ổn định, design revision, affected components.
- Threat/risk scenario và security requirement.
- Evidence về thiết kế hiện tại.
- Gap và impact với giả định rõ ràng.
- Severity/risk rationale.
- Options và recommended architecture changes.
- Owner, due date và approving role.
- Acceptance criteria và verification gates.
- Exception/residual risk khi có.
- Retest hoặc re-review và closure evidence.

### 17.3. Ví dụ finding

**Finding ARCH-007:** report worker xử lý export bằng global DB credential, tin tenant ID từ event chưa được xác minh.

**Risk:** attacker có thể tác động vào event để tạo báo cáo của tenant khác. Có nguy cơ disclosure diện rộng.

**Remediation:** producer xác thực quyền, event có provenance, worker kiểm tra tenant/resource binding, giới hạn DB role và download artifact; test forged/duplicate/replayed events.

**Design closure:** updated DFD, ADR, requirements và owner được review.

**Implementation closure:** tests và runtime/config evidence PASS trên đúng build và environment. Không đánh đồng hai mức.

### 17.4. Ngoại lệ

Ngoại lệ cần người phê duyệt có thẩm quyền, lý do, scope, thời hạn, controls bù trừ đã kiểm chứng, plan loại bỏ và re-review. Ngoại lệ không biến control còn thiếu thành effective và không miễn nghĩa vụ pháp lý/bắt buộc trái thẩm quyền.

## 18. Mẫu hồ sơ Review kiến trúc và ADR

~~~yaml
review_id: "SEC-DESIGN-REVIEW-DEMO-002"
module: "SECURITY_SECURITY_ASSURANCE"
title: "Orders API multi-tenant design review"
design_revision: "demo-v2"
status: "DRAFT"
scope:
  environment: "integration"
  services:
    - "orders-api"
    - "report-worker"
    - "payment-webhook"
  excluded:
    - "payment-provider-internal-platform"
assets:
  - "customer-order-data"
  - "payment-state"
data_classification: "CONFIDENTIAL_DEMO"
trust_boundaries:
  - "client-to-api"
  - "identity-to-tenant-resource"
  - "api-to-db-and-cache"
  - "queue-to-worker"
  - "provider-to-webhook"
threats:
  - "THR-ORD-01"
  - "THR-ORD-02"
  - "THR-ORD-03"
security_requirements:
  - "ARC-REQ-01"
  - "ARC-REQ-02"
  - "ARC-REQ-03"
decision:
  adr_id: "ADR-ORDERS-ISOLATION"
  option: "shared-db-with-app-authz-and-rls"
  status: "PENDING_APPROVAL"
  rationale: "Defense-in-depth with manageable operational cost"
open_assumptions:
  - "Tenant context is derived from verified identity"
  - "Application DB role cannot bypass RLS"
findings:
  - id: "ARCH-007"
    issue: "Worker trusts unverified event tenant context"
    state: "OPEN"
    owner: "Reporting Engineering"
verification_gates:
  - "cross-tenant-api-and-export-tests"
  - "rls-and-connection-pool-tests"
  - "webhook-signature-and-replay-tests"
  - "runtime-identity-and-iam-review"
design_effectiveness: "NOT_VERIFIED"
implementation_effectiveness: "NOT_VERIFIED"
operating_effectiveness: "NOT_VERIFIED"
assurance_conclusion: "INSUFFICIENT_EVIDENCE"
evidence_refs: []
risk_owner: "Orders Product Risk Owner"
reviewer: null
next_action: "Resolve design findings and execute tests"
~~~

Đây là YAML **minh họa**, chưa xác minh production. Không ghi raw PII, credential hoặc token vào review artifact.

### 18.1. Một review report dễ kiểm toán

- Executive summary với scope, phiên bản và decision.
- Business assets, sensitivity và architecture context.
- Diagrams/DFD và trust boundary inventory.
- Requirements, threat scenarios và source references.
- Control analysis và design alternatives.
- Findings, risk impact và owner.
- Open assumptions, exceptions và residual risk.
- Verification plan với acceptance criteria.
- Approvals, conditions và review triggers.
- Exclusions, limitations và evidence references.

## 19. Evidence và security assurance sau review

### 19.1. Những loại evidence

| Loại evidence | Có thể hỗ trợ kết luận | Không tự chứng minh |
| --- | --- | --- |
| DFD và ADR | Intended design và rationale | Code/runtime đúng |
| Threat model và requirements | Risk coverage dự kiến | Mọi threat đã được xử lý |
| IAM/NetworkPolicy/RLS config | Policy được khai báo hoặc áp ở thời điểm kiểm tra | Bypass không tồn tại |
| Code review | Một số đường thực thi controls | Mọi API/worker đều đúng |
| Positive/negative tests | Hành vi của build trong test scope | Tất cả trường hợp ngoài test |
| Runtime audit và monitoring | Hoạt động trong một thời kỳ | Mọi sự kiện đều được phát hiện |
| Retest | Fix đúng ở version và environment đã test | Không tái phát sau mọi change |

### 19.2. Chất lượng evidence

Đánh giá relevance, completeness, correctness, freshness, traceability, integrity, repeatability, independence, protection và limitations.

Metadata cần:

- Control/requirement/threat ID.
- Design revision, build, config/policy version.
- Environment, tenant/role/resource fixtures.
- Test run, timestamp, expected/actual results.
- Reviewer và evidence reference.
- Findings, action owner, retest và risk decision.
- Excluded paths và mức confidence.

### 19.3. Các trạng thái kết luận

- **Design adequate for assessed scope:** thiết kế phù hợp yêu cầu trong phạm vi, còn phải triển khai/test.
- **Design gaps unresolved:** có security design gap cần sửa.
- **Implementation effective in tested scope:** có evidence của code/config/tests tương ứng.
- **Operating effective in assessed period:** có runtime evidence đủ theo kỳ.
- **Partially effective:** một phần đạt, còn gaps.
- **Insufficient evidence:** chưa đủ căn cứ.
- **Approved exception:** residual risk được chấp nhận có điều kiện, không là PASS.
- **Not applicable:** có căn cứ không áp dụng.

Không tuyên bố “hệ thống secure 100%”. Kết luận phải có scope, time, assumptions, uncertainty và evidence.

## 20. Release gates và change governance

| Gate | Nội dung được xác nhận | Không được suy ra |
| --- | --- | --- |
| Requirements approved | Có tiêu chí bảo mật đã review | Control được triển khai |
| Design approved | Có architecture solution và review conditions | Build đã test |
| Implementation verified | Code/config/tests có evidence PASS trong scope | Production luôn an toàn |
| Release authorized | Open risk/finding được xử lý theo policy | Không còn unknown vulnerabilities |
| Operating review | Runtime controls có evidence qua thời kỳ | Không thể có incident mới |

Một gate có thể chặn release khi requirement bắt buộc không đạt hoặc evidence không đầy đủ. Không cho test bị **SKIPPED**, **NOT_RUN** hoặc tool failure tự tính là PASS.

### 20.1. Re-review triggers

- Thay role/tenant trust.
- Thay API, DB, cache hoặc queue.
- Thêm vendor/SDK/AI service.
- Thay encryption/secret management.
- Thay network/cloud account/cluster.
- Thêm admin/CI/CD privilege.
- Incident, audit finding hoặc repeated security bug.
- Thay policy/standard đã xác nhận áp dụng.

Giữ version/traceability để biết kết luận trước đây còn đúng phần nào.

## 21. KPI/KRI của review kiến trúc

| Metric | Điều phản ánh | Giới hạn |
| --- | --- | --- |
| **Review coverage theo risk tier** | Changes quan trọng đã được review | Review không đồng nghĩa đạt |
| **Threat-control mapping coverage** | Threat đáng kể có controls | Threat model có thể thiếu |
| **Open high-risk design findings** | Gaps cần ưu tiên | Severity theo impact/context |
| **Open assumptions** | Những tiền đề cần xác minh | Số ít có thể do ghi thiếu |
| **Verification plan coverage** | Design claims đã có tests | Test plan chưa có kết quả |
| **Control owner coverage** | Có người chịu trách nhiệm | Có tên owner chưa bảo đảm hành động |
| **Evidence freshness** | Gắn đúng design/build mới | Báo cáo cũ có thể mất hiệu lực |
| **Post-release architecture defects** | Lỗi thiết kế lọt ra vận hành | Phụ thuộc detection coverage |
| **Drift findings** | Cấu hình thực tế khác design | Cần đánh giá risk |
| **Finding remediation/retest time** | Khả năng giảm rủi ro | Ticket Done không đủ |
| **Expired exceptions** | Ngoại lệ quá hạn | Exception không phải trạng thái đạt |

**Ví dụ giả định:** 30 changes thuộc phạm vi bắt buộc review, 21 có decision đã ghi, 5 đang review và 4 chưa review. **Review decision coverage = 21/30 = 70%**. Không được kết luận hệ thống an toàn 70%. Bốn changes chưa đánh giá có thể là những changes nhiều rủi ro nhất.

## 22. Roles và RACI

| Vai trò | Trách nhiệm |
| --- | --- |
| **Security architect/AppSec** | Review trust boundaries, requirements, threats, controls và assurance plan |
| **System architect** | Sơ đồ, alternatives, quyết định và constraints |
| **Product/business owner** | Business flows, impact và constraints |
| **Engineering owner** | Implement control và remediation |
| **Identity/platform/cloud owner** | IAM, network, runtime, secrets và control plane |
| **Data/privacy owner** | Classification, data lifecycle, privacy applicability |
| **SRE/operations** | Availability, monitoring, recovery, deployment |
| **QA/security tester** | Test strategy, negative/bypass/failure tests |
| **Risk owner** | Residual-risk decision theo thẩm quyền |
| **Assurance/auditor** | Evidence quality, findings, independent conclusion |

RACI minh họa:

| Hoạt động | Architect | AppSec | Engineering | Platform | Risk owner | Assurance |
| --- | --- | --- | --- | --- | --- | --- |
| Architecture/DFD | **A/R** | C | R | C | I | C |
| Threat mapping | R | **A/R** | C | C | C | C |
| Control design review | R | **A** | R | R | C | C |
| Fix findings | C | C | **A/R** | R nếu liên quan | I | C |
| Verification plan | C | **A/R** | R | R | I | C |
| Approve residual risk | C | C | C | C | **A/R** | I |
| Independent evidence review | C | C | C | C | I | **A/R** |

RACI phải điều chỉnh theo quy chế thật; không mặc định một vai trò có quyền miễn nghĩa vụ bắt buộc.

## 23. Các sai lầm phổ biến

### 23.1. Review quá muộn

Chọn sai tenant model hoặc identity architecture rồi mới tìm lỗi khi chuẩn bị release. **Khắc phục:** review trước implementation và mỗi material change.

### 23.2. Một sơ đồ không có trust boundary

Không biết dữ liệu và quyền crossing ở đâu. **Khắc phục:** DFD có actor, dữ liệu, flow direction, identity và boundary.

### 23.3. Xem internal network là trusted

Compromised workload có thể di chuyển ngang. **Khắc phục:** workload identity, least privilege, app authorization và network controls.

### 23.4. Đồng nhất authentication và authorization

Token hợp lệ không có nghĩa được đọc mọi object. **Khắc phục:** resource-level checks và cross-tenant negative tests.

### 23.5. Quên queue, cache và exports

API đúng nhưng worker dùng admin credential. **Khắc phục:** review mọi đường thực thi và data sinks.

### 23.6. Chỉ ghi “dùng encryption”

Không biết ai có quyền decrypt và key nằm đâu. **Khắc phục:** key/secret access lifecycle và threat-based verification.

### 23.7. Bỏ CI/CD, support và control plane

Admin hoặc runner quyền rộng có thể phá data-plane protections. **Khắc phục:** review privilege boundaries và audit integrity.

### 23.8. Thiếu failure behavior

Policy service lỗi được mặc định allow. **Khắc phục:** design deny/hold/degraded mode theo risk và acceptance tests.

### 23.9. Coi diagram/config là runtime evidence

Manifest có policy nhưng triển khai sai hoặc bypass. **Khắc phục:** effective config + runtime negative tests.

### 23.10. Review chỉ để ký duyệt

Findings không có owner, test và deadline. **Khắc phục:** conditional decision, actions và verification gates.

### 23.11. Không so sánh alternatives

Chọn giải pháp theo sở thích tool. **Khắc phục:** ADR với trade-offs, rationale và residual risks.

### 23.12. Kết luận ngoài scope

Review một service rồi nói toàn nền tảng đã đạt. **Khắc phục:** nêu components, design revision, environment, exclusions và uncertainty.

### 23.13. Không đánh giá lại khi thay đổi

Thêm provider/cache/AI retrieval nhưng dùng kết luận cũ. **Khắc phục:** impact analysis và re-review triggers.

### 23.14. Để report rò dữ liệu

Architecture diagrams, secret examples và log traces có thể chứa thông tin nhạy cảm. **Khắc phục:** protected evidence, redaction, synthetic data và retention.

## 24. Checklist thực hành Architecture Review

- [ ] Có review ID, design revision, scope, environment và owner.
- [ ] Đã xác định business assets, risk tier và data classification.
- [ ] Có system context, DFD và trust boundaries.
- [ ] Có identity/authorization và privileged actor views.
- [ ] Bao phủ các đường HTTP, queue, worker, cache, search, export, vendor.
- [ ] Đã xác định data lifecycle, backups, logging, analytics.
- [ ] Có threat scenarios với attacker capability và impact.
- [ ] Có security requirements và source/rationale.
- [ ] Mỗi threat quan trọng có control hoặc risk decision.
- [ ] Principal và token trust được kiểm tra tại boundary phù hợp.
- [ ] Object-level và tenant authorization được design rõ.
- [ ] Workload identity riêng, quyền tối thiểu, không admin mặc định.
- [ ] DB/cache/search/worker giữ đúng data scope.
- [ ] Event/webhook có provenance, integrity, replay/idempotency.
- [ ] Network ingress/egress, SSRF và metadata/control endpoints được review.
- [ ] Container/VM/Kubernetes isolation phù hợp threat.
- [ ] CI/CD, artifacts, secrets và production privileges được review.
- [ ] Crypto/key management và data-at-rest/in-transit có baseline rõ.
- [ ] Có fail-safe behavior khi identity, policy, vault hoặc audit lỗi.
- [ ] Có audit/detection và bảo vệ evidence.
- [ ] Có quota/rate limit, resilience và recovery objectives.
- [ ] Alternatives và trade-offs được ghi trong ADR.
- [ ] Open assumptions và design findings có owner, severity, due date.
- [ ] Exceptions có approval đúng quyền, expiry và compensating controls.
- [ ] Mỗi claim có positive, negative, bypass và failure tests phù hợp.
- [ ] Có verification gates gắn build/environment/config revision.
- [ ] Design approval được tách khỏi implementation/operation evidence.
- [ ] Có change/re-review triggers và traceability.
- [ ] Kết luận ghi scope, confidence, exclusions và residual risk.

Checklist chỉ giúp tổ chức review; **không thay cho security tests hoặc assurance evidence từ hệ thống thực**.

## 25. Bài tập thực hành

### Bài tập 1 — Vẽ trust boundaries

Cho hệ thống browser, gateway, Orders API, Redis, PostgreSQL, payment provider, report worker, support console. Hãy vẽ DFD, xác định tối thiểu năm boundaries, ghi một threat và một control tại mỗi boundary.

### Bài tập 2 — Phản biện cache

Architect đề xuất cache key chỉ gồm order UUID vì ID là duy nhất. Hãy phân tích vì sao UUID không thay authorization, cách dùng tenant/permission scope, invalidation và test.

### Bài tập 3 — Webhook

Provider retry payment event. Hãy thiết kế signature validation, source mapping, atomic idempotency, out-of-order handling, audit và negative tests.

### Bài tập 4 — Finding

Report worker dùng admin DB credential và tenant ID do client tự khai. Viết finding gồm threat, evidence, impact, owner, remediation, risk decision, acceptance criteria và retest.

### Bài tập 5 — ADR

So sánh shared DB + app authorization, shared DB + RLS, dedicated DB per tenant theo risk, cost, operability, blast radius và testing. Ghi phương án có điều kiện thay vì tuyên bố tuyệt đối.

## 26. Câu hỏi tự kiểm tra

1. Security architecture review khác threat modeling và code review thế nào?
2. Vì sao design approval chưa đủ để kết luận production an toàn?
3. Những tài liệu nào cần có trước buổi architecture review?
4. DFD thiếu queue hoặc backup có thể dẫn tới bỏ sót những rủi ro gì?
5. Một trust boundary record nên ghi những trường nào?
6. Vì sao internal network không phải bằng chứng authorization?
7. JWT hợp lệ có thể được dùng để khai thác BOLA ra sao?
8. Confused deputy xuất hiện thế nào ở report worker?
9. Cache/search có thể làm mất tenant isolation dù DB query đã scope?
10. Khi nào DB RLS giúp defense-in-depth và khi nào có thể bị bypass?
11. Vì sao mTLS không thay service-level authorization?
12. NetworkPolicy manifest khác runtime evidence thế nào?
13. Các rủi ro control plane và CI/CD cần review là gì?
14. Một secret manager có thể gây rủi ro nếu workload role quá rộng?
15. Webhook cần những kiểm soát nào về integrity và replay?
16. Vì sao event ID không tự tạo exactly-once processing?
17. Một tenant làm cạn DB connections thuộc mục tiêu bảo mật nào?
18. Review encryption cần xét key owner và quyền decrypt như thế nào?
19. Một finding thuộc design gap khác evidence gap ra sao?
20. Vì sao risk acceptance không tự biến control thành effective?
21. Kiến trúc có fail-safe behavior cần thể hiện gì?
22. Một ADR tốt cần giải thích alternatives và trade-offs thế nào?
23. Khi nào bắt buộc re-review?
24. Review decision coverage 70% có nghĩa hệ thống an toàn 70% không?
25. Những test nào cần để xác minh Orders API tenant isolation?
26. Làm sao chứng minh report worker không thể gửi file của tenant B cho user A?
27. Restore từ backup có thể làm sai trạng thái credential hoặc tenant không?
28. Những metadata nào nên gắn với review evidence?
29. Ai phê duyệt residual risk và ai xác minh implementation?
30. Nếu bổ sung AI/RAG vào SaaS nhiều tenant, những boundaries nào cần review?

## 27. Tổng kết

**Review kiến trúc** là quá trình đánh giá liệu cấu trúc hệ thống, identity, data flows và trust boundaries có đủ cơ chế bảo vệ trước threats và đáp ứng security requirements không. Một review có giá trị cần **business context, DFD, threat/risk mapping, control ownership, design alternatives, failure modes, verification plan và findings rõ ràng**. Reviewer phải xem xét **authentication, object-level authorization, tenant/data isolation, cache/async flows, network/runtime, external providers/webhooks, CI/CD/control plane, cryptography, secret management, monitoring và recovery**. Trong module **SECURITY_SECURITY_ASSURANCE**, kết quả review chủ yếu hỗ trợ **design effectiveness**; để kết luận control thật sự hiệu quả cần thêm **implementation tests, runtime evidence, audit, remediation và retest**. Mỗi kết luận phải có scope, design revision, giả định, evidence, rủi ro còn lại và trigger đánh giá lại khi hệ thống thay đổi.
