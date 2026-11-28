# Requirement về mã hóa: đặc tả yêu cầu mật mã có thể kiểm chứng

Một đội phát triển nền tảng học trực tuyến lưu thông tin cá nhân, bài kiểm tra và kết quả học tập của nhiều tổ chức (tenant). Tài liệu thiết kế chỉ có dòng: “Dữ liệu phải được mã hóa bằng AES và giao tiếp phải dùng HTTPS”. Đội dự án đánh dấu yêu cầu đã hoàn thành vì database bật encryption at rest và gateway cấp chứng thư TLS. Tuy nhiên, một service vẫn ghi token truy cập vào log; một bucket export không mã hóa theo cấu hình được duyệt; backup dùng khóa khác không rõ owner; nhiều kết nối nội bộ bỏ qua kiểm tra certificate; nhân viên hỗ trợ có quyền giải mã dữ liệu ngoài phạm vi nhiệm vụ.

Không nhất thiết thuật toán AES hoặc TLS đã bị phá. Vấn đề là **yêu cầu không quy định phạm vi tài sản, đối tượng cần bảo vệ, bên được phép giải mã, vòng đời khóa, xử lý ngoại lệ và tiêu chí chấp nhận**. “Có mã hóa” không đồng nghĩa “đạt mục tiêu bảo mật”.

**Requirement về mã hóa (cryptographic security requirement)** là một phát biểu có tính ràng buộc, xác định **tài sản hoặc luồng dữ liệu cần bảo vệ, thuộc tính bảo mật cần đạt, điều kiện áp dụng, hành vi được phép/cấm, trách nhiệm thực thi và cách kiểm chứng**. Một yêu cầu tốt đủ rõ để kiến trúc sư chọn giải pháp phù hợp, developer triển khai đúng, tester xác định kết quả mong đợi, auditor truy xuất bằng chứng và risk owner hiểu rủi ro còn lại.

Trong chương **Security requirements** của module **SECURITY_SECURITY_ASSURANCE**, mục tiêu là xây dựng cách đánh giá có bằng chứng rằng hệ thống đáp ứng mục tiêu bảo mật: từ phân tích rủi ro, security objectives và controls tới kiểm thử, audit, remediation và continuous assurance. Vì vậy, yêu cầu mã hóa phải được nối thành chuỗi:

**Tài sản và luồng dữ liệu → rủi ro/threat model → mục tiêu bảo mật → requirement → thiết kế/control → test → evidence → finding/residual risk → reassessment.**

> **Điểm then chốt:** Không đủ để ghi “phải mã hóa dữ liệu”. Phải biết **dữ liệu nào, ở đâu, lúc nào, trước ai, dùng cơ chế nào đã được phê duyệt, ai giữ khóa, điều gì xảy ra khi lỗi và evidence nào chứng minh kết quả**. Mã hóa chỉ có ý nghĩa trong một hệ thống có quản trị khóa, phân quyền, bảo vệ dữ liệu đang sử dụng và kiểm soát đường truy cập.

## 1. Phân biệt security objective, requirement và cryptographic control

Ba khái niệm liên quan nhưng không nên sử dụng thay cho nhau.

| Thành phần | Chức năng | Ví dụ |
|---|---|---|
| **Security objective** | Mục tiêu mong muốn về confidentiality, integrity, authenticity, availability | Chỉ tổ chức sở hữu mới được đọc hồ sơ học viên |
| **Risk scenario** | Cách mục tiêu có thể bị ảnh hưởng | Attacker lấy snapshot database và đọc hồ sơ khách hàng |
| **Security requirement** | Điều kiện bắt buộc, có thể đánh giá được | Các bản sao hồ sơ nhạy cảm phải được mã hóa khi lưu; đường giải mã chỉ cấp cho service được duyệt |
| **Control/design** | Cách đáp ứng requirement | TDE hoặc application-level AEAD; KMS với IAM và key separation |
| **Verification** | Cách kiểm tra yêu cầu được thực thi | Review config runtime, negative KMS permission test, backup inspection |
| **Evidence** | Dữ liệu/tài liệu thực tế hỗ trợ kết luận | Key policy export, deployment snapshot, test logs, approval records |
| **Assurance conclusion** | Quyết định có giới hạn theo scope và thời điểm | PASS/FAIL/INCONCLUSIVE, cùng residual risk và limitations |

Ví dụ:

- **Mục tiêu:** bảo mật các file export có PII.
- **Rủi ro:** file export nằm trong object storage có thể bị đọc khi cấu hình truy cập bị mở rộng.
- **Requirement:** mọi file export có PII phải được mã hóa bằng cơ chế được crypto policy phê duyệt, sử dụng khóa thuộc miền production, có owner và lifecycle; chỉ export service đã xác thực có quyền thực hiện operation cần thiết; file tự hết hạn theo retention policy.
- **Thiết kế:** object storage SSE-KMS kết hợp IAM, bucket policy, logging, retention và kiểm tra quyền download.
- **Đánh giá:** kiểm tra key reference, default encryption, object-level overrides, access policies, test tạo object mới và backup/replication.
- **Giới hạn:** SSE-KMS không ngăn một principal có quyền đọc object được dịch vụ storage tự động giải mã khi download.

Một security requirement cần mô tả **điều phải đúng**, không phụ thuộc hoàn toàn vào tên một sản phẩm. Thiết kế có thể thay đổi từ công nghệ A sang B nếu vẫn đáp ứng tiêu chí chấp nhận và được kiểm soát thay đổi.

## 2. Khi nào mã hóa là yêu cầu phù hợp?

Mã hóa thường giúp giảm một số rủi ro về:

- **Confidentiality:** ngăn bên không có khóa phù hợp đọc plaintext khi dữ liệu bị chặn bắt hoặc bản lưu bị lấy.
- **Integrity:** phát hiện dữ liệu hoặc thông điệp bị sửa trái phép khi dùng cơ chế xác thực phù hợp.
- **Authenticity:** hỗ trợ xác minh nguồn hoặc bên sở hữu khóa trong bối cảnh protocol/chữ ký.
- **Non-repudiation-related evidence:** chữ ký số có thể hỗ trợ quy trách nhiệm nhưng không tự chứng minh người ký đã chấp thuận nội dung hoặc khóa không bị lạm dụng.
- **Key separation:** giới hạn phạm vi tác động nếu một miền khóa bị lộ.
- **Privacy and regulatory obligations:** hỗ trợ bảo vệ dữ liệu theo mục đích và yêu cầu áp dụng.

Mã hóa **không tự bảo đảm**:

- User được quyền đọc dữ liệu chỉ vì họ có kết nối HTTPS.
- Dữ liệu không bị đọc khi ứng dụng đã giải mã trong memory.
- Không có SQL injection, SSRF, session theft, insider misuse.
- Không bị chỉnh sửa nếu chỉ dùng encryption không xác thực.
- Khóa không bị lộ nếu được hardcode trong code hoặc log.
- Backup và bản export không chứa plaintext.
- Mọi dữ liệu đã bị xóa khi xóa một khóa mà vẫn còn các bản copy khác.
- Một giao dịch hợp lệ về nghiệp vụ chỉ vì chữ ký mật mã hợp lệ.

Do đó cần kết hợp **authorization, least privilege, secret management, data minimization, monitoring, secure coding và incident response**.

## 3. Phân loại thông tin và lập phạm vi yêu cầu

Trước khi viết điều kiện về thuật toán hoặc TLS, cần xác định **dữ liệu nào được bảo vệ**.

### 3.1. Data inventory

Với một learning platform nhiều tenant, inventory có thể gồm:

| Tài sản | Ví dụ nội dung | Mức nhạy cảm minh họa | Nơi tồn tại |
|---|---|---|---|
| Hồ sơ học viên | Họ tên, email, nhóm, lịch sử học | PII/internal | DB, cache, backup, export |
| Kết quả bài thi | Điểm, câu trả lời, feedback | Confidential/business-sensitive | DB, search index, analytics |
| Access/refresh token | Credential cho session | Secret | Browser/app, cache, gateway logs |
| Khóa ký JWT | Private signing key | Cryptographic secret | KMS/HSM hoặc secret-management boundary |
| Bài giảng public | Tài nguyên công khai | Public | CDN, object storage |
| Thông tin thanh toán | Reference, thông tin nhạy cảm theo thiết kế | Restricted | Service riêng và provider |
| Audit events | Actor, thời điểm, IP, resource | Sensitive metadata | Logging/SIEM, archive |
| Backup/snapshot | Bản sao dữ liệu hỗn hợp | Theo phân loại cao nhất trong phạm vi | Backup service, region DR |

Mức nhạy cảm chỉ minh họa, phải theo data classification của tổ chức. Một bản backup chứa nhiều loại dữ liệu thường không thể coi là “ít nhạy cảm” chỉ vì được lưu trong hạ tầng nội bộ.

### 3.2. Data flow diagram và trust boundary

~~~mermaid
flowchart LR
    U["Learner browser/mobile"] -->|TLS| EDGE["API Gateway"]
    EDGE -->|TLS / mTLS as required| APP["Learning service"]
    APP -->|DB connection| DB[("Student database")]
    APP --> CACHE[("Cache")]
    APP --> EXP["Export job"]
    EXP --> OBJ[("Object storage")]
    DB --> BK[("Backup / DR")]
    APP --> AUD["Logging / SIEM"]
    KMS["KMS / HSM / key registry"] -. "Key operations and authorization" .-> APP
    KMS -. "Storage encryption keys" .-> OBJ
    KMS -. "Backup key governance" .-> BK
    IDP["Identity / IAM"] -. "Who may access data and keys" .-> APP
~~~

Một DFD giúp nhận diện các ranh giới:

- Internet/browser → gateway.
- Gateway → microservice.
- Microservice → database/cache/search.
- Ứng dụng → object storage/export.
- Database → snapshot/backup/DR.
- Workload → KMS/HSM.
- KMS → backup/restore/administration.
- Service → log/telemetry/incident tools.
- Production → development/test hoặc vùng của tenant khác.

**Một yêu cầu về mã hóa phải bao phủ những bản sao và các đường luân chuyển có liên quan**, không chỉ database chính.

### 3.3. Data state: at rest, in transit, in use

| Trạng thái | Thí dụ | Mục tiêu | Giới hạn |
|---|---|---|---|
| **Data at rest** | DB files, snapshot, object, local disk, backup | Giảm khả năng đọc plaintext khi lấy bản lưu/thiết bị | Service có quyền truy cập có thể nhận plaintext khi giải mã |
| **Data in transit** | HTTPS, service-to-service, DB, broker, replication | Chống nghe lén và sửa dữ liệu trên đường truyền theo protocol | Kết nối TLS kết thúc ở endpoint; không bảo vệ dữ liệu sau termination |
| **Data in use** | Memory, CPU, plaintext xử lý trong service | Hạn chế phơi lộ khi xử lý | Khó bảo vệ toàn diện; cần process isolation, memory hygiene, confidential computing khi phù hợp |
| **Data-derived copies** | Logs, search index, cache, analytics, screenshot, export | Bảo vệ tất cả bản copy có giá trị tương đương | Encryption trên bản gốc không tự lan sang bản copy |

Yêu cầu phải nêu rõ **threat boundary**. “Disk encryption” có thể bảo vệ ổ đĩa bị lấy cắp nhưng không nhất thiết bảo vệ khi attacker đăng nhập bằng quyền database administrator hoặc làm chủ host đang mở khóa.

## 4. Cấu trúc một requirement mã hóa có thể kiểm chứng

Một yêu cầu tốt nên có các trường tối thiểu:

| Trường | Câu hỏi |
|---|---|
| **ID** | Requirement được theo dõi bằng mã nào? |
| **Title / objective** | Điều gì phải được bảo vệ và tại sao? |
| **Scope / asset** | Dữ liệu, trạng thái, hệ thống, tenant, environment, bản sao nào? |
| **Threat/risk reference** | Ngăn kịch bản nào, theo risk register nào? |
| **Normative behavior** | Bắt buộc làm gì hoặc cấm điều gì? |
| **Cryptographic constraints** | Dùng crypto policy nào, algorithm/mode/key type được duyệt? |
| **Key ownership** | Ai sở hữu, ai được tạo/dùng/đổi/hủy khóa? |
| **Trust boundary** | Dữ liệu ở đường nào trước và sau mã hóa/giải mã? |
| **Failure behavior** | Thiếu key, TLS verification lỗi, KMS outage thì xử lý thế nào? |
| **Exceptions** | Khi nào cho phép ngoại lệ, ai phê duyệt, hết hạn lúc nào? |
| **Acceptance criteria** | Điều kiện pass/deny đo hoặc quan sát được là gì? |
| **Verification / evidence** | Test/config/log/records nào chứng minh? |
| **Traceability / lifecycle** | Control owner, test IDs, evidence IDs, phiên bản và trigger review? |

### 4.1. Công thức gợi ý

Một mẫu câu hữu ích:

**“Đối với [tài sản/dữ liệu] trong [trạng thái và phạm vi], [thành phần có trách nhiệm] PHẢI [hành vi có thể xác minh], phù hợp [crypto/security policy], sao cho [đặc tính cần đạt]; khi [lỗi/ngoại lệ], hệ thống PHẢI [hành vi an toàn]. Điều kiện đạt là [acceptance criteria] và bằng chứng là [test/evidence].”**

Ví dụ:

**REQ-CRYPTO-REST-01:** “Mọi object được phân loại Confidential trở lên được tạo trong bucket export production PHẢI được mã hóa bằng cơ chế storage encryption được crypto policy chấp thuận, với khóa production được quản lý và policy truy cập tách khỏi nhóm đọc object. Object không có cấu hình encryption phù hợp phải bị từ chối khi ghi hoặc được ngăn từ trước bởi kiểm tra cấu hình có enforcement. Việc tạo, đọc, sao chép sang region khác và restore phải được kiểm chứng trên runtime configuration và object metadata.”

Đây là requirement có thể review. **Tên thuật toán, tham số, key type hoặc module validation** được tham chiếu tới crypto standard phiên bản áp dụng, thay vì đưa ra lựa chọn cứng không có vòng đời.

### 4.2. Không viết requirement chỉ dưới dạng “dùng AES-256”

Câu “Dữ liệu phải dùng AES-256” không trả lời:

- Dùng mode nào? Một mode không xác thực có thể không đáp ứng integrity.
- Khóa ở đâu, ai được giải mã?
- Nonce/IV có được quản lý đúng?
- Dữ liệu nào và ở đâu?
- Mã hóa trước hay sau khi rời application boundary?
- Backup, cache, file upload, log có được bảo vệ?
- Có một đường export plaintext không?
- Nếu key service lỗi, ứng dụng dừng hay dùng default key?
- Evidence nào chứng minh production áp đúng?

**Algorithm selection là một phần của yêu cầu và tiêu chuẩn kỹ thuật, không phải toàn bộ security requirement.**

## 5. Ví dụ chuyển yêu cầu mơ hồ thành tiêu chí nghiệm thu

| Mơ hồ | Chặt chẽ hơn | Cách kiểm chứng |
|---|---|---|
| “Mã hóa database” | Database production, snapshots và replicas chứa Restricted data phải có encryption at rest bật theo baseline; keys và admin access được kiểm soát | Config snapshot, restore test, KMS policy |
| “Luôn dùng HTTPS” | Browser → gateway và service boundaries mang token/PII phải dùng TLS được crypto policy cho phép, xác minh certificate và hostname | TLS configuration scan, invalid-certificate tests |
| “Không lưu mật khẩu lộ” | Password chỉ lưu bằng password hashing scheme được duyệt với salt/work factor phù hợp; không được có plaintext/reversible password store | Auth code/config review, sample-schema inspection, regression tests |
| “Dùng khóa an toàn” | Mỗi key có owner, purpose, allowed operations, lifecycle và policy truy cập; key material không hardcode trong artifacts | Key registry, access negatives, secrets scan |
| “Ký số giao dịch” | Phép ký phải sử dụng key và algorithm được duyệt, gắn với dữ liệu/approval đã xác minh; verifier từ chối payload sửa | Signature verification, business authorization tests |
| “Có mã hóa cho backup” | Tất cả backup copies và DR replicas thuộc scope mã hóa theo key custody và restore policy; kiểm tra sau phục hồi | Backup job config, restore exercise |
| “Thay khóa định kỳ” | Key rotation có sự kiện kích hoạt, approver, kế hoạch chuyển đổi/giữ key cũ và retest | Key version timeline, migration/restore test |
| “Giải mã khi cần” | Chỉ workload thuộc allowlist có quyền decrypt/unwrap đúng key/purpose; deny các workload/tenant khác | IAM/KMS negative tests và audit |

**Tiêu chí nghiệm thu phải đủ rõ để người kiểm thử có thể tạo cả ca được phép và ca bị từ chối**, không chỉ xác nhận có checkbox “encryption enabled”.

## 6. Requirement mã hóa dữ liệu lưu trữ (at rest)

Mã hóa lưu trữ có thể triển khai ở nhiều lớp:

- **Full-disk / volume encryption:** thường bảo vệ thiết bị/volume ở một số tình huống bị lấy bản lưu hoặc mất vật lý.
- **Database Transparent Data Encryption (TDE):** mã hóa files/blocks ở tầng database engine.
- **Storage service encryption:** object storage hoặc managed service tự mã hóa dữ liệu theo key policy.
- **Application/field-level encryption:** ứng dụng mã hóa dữ liệu trước khi lưu, có thể tách quyền data store và quyền giải mã.
- **Client-side encryption:** dữ liệu được mã hóa trước khi gửi lên dịch vụ trong một trust model cụ thể.
- **Backup/snapshot encryption:** bảo vệ các bản sao, phụ thuộc backup path và key ownership.

Các lớp có ưu điểm và giới hạn khác nhau. Không thể kết luận TDE thay thế application-layer encryption nếu threat model bao gồm database admin có khả năng query plaintext.

### 6.1. Một bộ requirement mẫu

**REQ-CRYPTO-REST-01 — Bảo vệ tất cả bản lưu thuộc scope**

Tất cả database files, object storage, volumes, backup, replica và exported artifacts chứa dữ liệu Restricted phải sử dụng cơ chế mã hóa lưu trữ được chấp thuận, với inventory và exception được quản lý.

**REQ-CRYPTO-REST-02 — Quản trị quyền giải mã**

Quyền decrypt/unwrap phải cấp theo workload purpose và resource scope, không tự gắn với mọi principal có quyền đọc metadata hoặc quản trị storage.

**REQ-CRYPTO-REST-03 — Backup và restore**

Bản backup phải có key custody, retention, restore procedure và kiểm chứng khôi phục, không tạo ra bản plaintext hoặc quyền giải mã ngoài policy.

**REQ-CRYPTO-REST-04 — Trạng thái mặc định**

Tài nguyên lưu trữ mới thuộc loại xử lý dữ liệu nhạy cảm phải có encryption configuration mặc định phù hợp; thao tác tạo tài nguyên không đáp ứng baseline phải bị ngăn hoặc được phát hiện và xử lý theo release gate/continuous control.

### 6.2. Threat model và giới hạn

| Tình huống | Layer có thể giúp | Cần thêm control |
|---|---|---|
| Đĩa vật lý bị mất | Disk/volume encryption | Endpoint management, key custody |
| Snapshot bị sao chép ngoài quyền | Snapshot encryption với key controls | Snapshot access, cross-account policy, audit |
| Storage admin lạm dụng quyền | Application encryption có key separation có thể giảm phơi lộ | IAM, SoD, data access audit |
| App bị chiếm khi đang xử lý plaintext | Mã hóa lưu trữ không chặn hoàn toàn | Runtime security, least privilege, detection |
| User hợp lệ tải quá nhiều dữ liệu | Encryption at rest không chặn | Authorization, purpose/export approval, rate controls |
| Backup bị mất khóa | Mã hóa ngăn đọc nhưng có thể mất khả năng restore | DR/key escrow theo policy, restore exercises |

## 7. Requirement bảo vệ dữ liệu truyền tải (in transit)

**TLS** là một cơ chế bảo vệ kênh truyền, với điều kiện protocol, thuật toán, certificate verification và session behavior được cấu hình đúng. Một kết nối được mã hóa nhưng **bỏ qua xác thực phía bên kia** có thể vẫn dễ bị man-in-the-middle.

### 7.1. Các kết nối cần lập danh sách

- Browser/mobile → CDN/edge/API gateway.
- Gateway → authentication service.
- API gateway → microservices.
- Microservices → databases, cache, message broker.
- Application → KMS/HSM.
- Service → logging/monitoring provider.
- Service → third-party payment/email/webhook.
- Primary region → replica/backup/DR.
- Admin console, operator tooling và CI/CD connections.

Lưu ý TLS termination: traffic HTTPS từ browser tới load balancer **không chứng minh** kết nối load balancer tới backend được bảo vệ. Cần phân tích trust boundary riêng.

### 7.2. Các nhóm requirement

**REQ-CRYPTO-TRANSIT-01 — Confidentiality và integrity trên kênh**

Các kết nối mang credential/PII hoặc dữ liệu nhạy cảm qua các trust boundaries đã xác định phải dùng TLS và cấu hình được crypto policy chấp thuận.

**REQ-CRYPTO-TRANSIT-02 — Peer authentication**

Client phải xác minh certificate chain, hostname/service identity, thời hạn và chính sách trust tương ứng; không cho phép bypass verification trong production.

**REQ-CRYPTO-TRANSIT-03 — Service identity**

Các service boundaries yêu cầu xác thực hai chiều phải dùng cơ chế như mTLS với credential lifecycle được quản lý, phù hợp service mesh hoặc nền tảng.

**REQ-CRYPTO-TRANSIT-04 — Safe failure**

Khi certificate không hợp lệ, bắt tay TLS không thành công hoặc chưa có trust anchor được phê duyệt, client phải từ chối kết nối nhạy cảm thay vì hạ xuống plaintext hoặc tắt xác minh.

**REQ-CRYPTO-TRANSIT-05 — Certificate renewal và observability**

Certificate có owner, expiry tracking, renewal procedure, rotation và cảnh báo phù hợp; cần test ứng dụng còn hoạt động sau rotation và từ chối chứng thư không tin cậy.

### 7.3. TLS không giải quyết mọi thứ

TLS xác thực endpoint và bảo vệ kênh, không tự bảo đảm:
- Request hợp lệ về nghiệp vụ.
- Backend được quyền truy cập resource.
- Payload không bị sửa sau khi TLS termination.
- Kết quả trả về không chứa dữ liệu của tenant khác.
- Các bản sao trong log, cache hoặc storage an toàn.
- User không bị phishing, endpoint không bị malware.

Cần kết hợp **resource-level authorization, authentication, API validation, logging và data controls**.

### 7.4. Những lỗi thiết kế cần negative test

- Trust-all certificate manager.
- Hostname verification bị vô hiệu hóa.
- Cho phép insecure protocol fallback.
- Dùng self-signed certificate không có trust/distribution policy.
- Quên mã hóa internal broker, database connection hoặc backup replication.
- Certificate còn hạn nhưng sai subject/service identity.
- Shared client certificate cho nhiều workload gây mất attribution.
- Không kiểm tra certificate rotation/expiry hoặc revoked credentials theo cơ chế phù hợp.

## 8. Mã hóa ở tầng ứng dụng: AEAD và bảo vệ tính toàn vẹn

Khi yêu cầu cần cả confidentiality và integrity tại application boundary, một hướng thiết kế thường gặp là **Authenticated Encryption with Associated Data (AEAD)** như AES-GCM theo crypto policy đã duyệt.

AEAD có thể cung cấp:
- Confidentiality cho plaintext.
- Authentication/integrity check cho ciphertext và AAD đã cung cấp.
- Thất bại giải mã khi ciphertext/tag/AAD không hợp lệ, trong giả định khóa và nonce được sử dụng đúng.

AEAD **không** tự cung cấp:
- Identity của người dùng cuối nếu không gắn với trust model.
- Authorization đối với resource.
- Anti-replay nếu protocol không thiết kế freshness/sequence.
- Bảo mật plaintext sau khi giải mã trong app memory.
- An toàn nếu cùng key và nonce được tái sử dụng không đúng.
- Khả năng chống traffic analysis hoặc lộ metadata ngoài ciphertext.

### 8.1. Nonce/IV và uniqueness

Với AES-GCM, **không được tái sử dụng cùng cặp key và nonce**. Reuse có thể làm mất bảo vệ confidentiality/integrity nghiêm trọng.

Một yêu cầu cụ thể cần quy định:
- Nonce length theo crypto standard/implementation; cấu hình phổ biến dùng 96-bit nonce.
- Phương pháp sinh nonce phù hợp và các giới hạn tổng số bản mã/khóa.
- Cơ chế chống reuse qua process restart, replication, cluster và retry.
- Cách kiểm soát key lifetime và rotation trước ngưỡng nguy hiểm.
- Nonce không cần bí mật nhưng phải bảo đảm đúng uniqueness theo cơ chế.
- Test hợp lệ và failure modes; không coi “random nonce” tự động là bảo đảm tuyệt đối ở mọi quy mô.

**Ở hệ thống có volume cao hoặc nhiều node**, cần tính đến xác suất va chạm, giới hạn của thuật toán và yêu cầu từ tiêu chuẩn/vendor; có thể dùng chiến lược cấp phát nonce theo bộ đếm/miền khóa hoặc cơ chế khác được review.

### 8.2. AAD: ràng buộc ngữ cảnh

AAD không được mã hóa, nhưng được gắn với authentication tag. Có thể dùng AAD để ràng buộc ciphertext với:

- Tenant ID.
- Record ID.
- Schema version.
- Field type.
- Purpose/data classification.
- Cryptographic envelope version.

Ví dụ mã hóa câu trả lời bài kiểm tra của tenant A, record 42; AAD có thể biểu diễn canonical form của những thuộc tính này. Khi một ciphertext bị di chuyển sang record 99 hoặc tenant B, decryption phải thất bại nếu AAD phía giải mã được dựng từ ngữ cảnh authoritative của record đích.

**Không được lấy AAD duy nhất từ metadata do attacker tự cung cấp cùng ciphertext rồi coi đó là authorization.** Server phải xác minh tenant/resource ownership và dựng hoặc kiểm chứng AAD từ nguồn tin cậy.

### 8.3. Ciphertext format/version

Yêu cầu ứng dụng cần một envelope có thể version hóa:

| Field | Ý nghĩa |
|---|---|
| Format version | Giúp đọc dữ liệu qua migration |
| Key ID/version | Chọn đúng khóa; không nên là bí mật cần giấu |
| Algorithm/mode | Chỉ nhận những giá trị thuộc allowlist |
| Nonce/IV | Được lưu cùng ciphertext khi phù hợp |
| Ciphertext + authentication tag | Dữ liệu được mã hóa/xác thực |
| AAD context reference | Có thể cần dùng để dựng AAD đúng cách |
| Metadata về migration/retention | Hỗ trợ rotate, restore, audit |

Không cho phép untrusted input tùy ý chọn algorithm yếu hoặc key alias production. Decrypt operation phải dựa trên **trusted key registry và version policy**.

## 9. Mật khẩu, hashing, MAC và chữ ký số: không dùng một cơ chế cho mọi mục tiêu

### 9.1. Password storage

Mật khẩu **không nên được mã hóa đảo ngược chỉ để xác thực**. Phải dùng **password hashing/password-based key derivation phù hợp**, có salt độc nhất và work factor được quản lý theo chuẩn chính sách; lựa chọn như Argon2id, scrypt hoặc PBKDF2 tùy yêu cầu và môi trường được duyệt.

Các requirement phải bao gồm:
- Không lưu plaintext hoặc reversible password trong hệ thống xác thực không có nhu cầu đặc biệt được duyệt.
- Salt unique theo mật khẩu; không thay bằng một salt toàn hệ thống.
- Work factor/parameters phù hợp khả năng chống brute-force và ngân sách vận hành.
- Hỗ trợ nâng cấp parameters/hash format qua thời gian.
- Không log password hoặc password hash.
- Bảo vệ reset/recovery token và rate limiting.
- Có thể xem xét pepper được bảo vệ tách biệt theo threat model, nhưng không mặc định cần cho mọi trường hợp.

**Hash nhanh thuần SHA-256 không phải giải pháp lưu password phù hợp** dù SHA-256 là một hàm băm mạnh cho mục đích khác.

### 9.2. Hash thông thường

Cryptographic hash có thể hỗ trợ kiểm tra tính toàn vẹn hoặc làm thành phần trong chữ ký, nhưng **một checksum/hash công khai đơn lẻ không chứng minh nguồn gửi đáng tin**. Attacker có khả năng sửa file và hash đi kèm có thể tính lại cả hai.

### 9.3. MAC/HMAC

MAC sử dụng shared secret để xác thực dữ liệu giữa các bên biết key. Requirement cần:
- Key management và separation theo purpose.
- Canonical message format.
- Scope, expiry hoặc anti-replay khi protocol cần.
- Constant-time comparison ở nơi thích hợp.
- Không cho phép attacker tự chọn khóa/trust boundary.

HMAC không tự cung cấp non-repudiation giữa hai bên cùng giữ một shared key.

### 9.4. Chữ ký số

Digital signature có thể hỗ trợ integrity và chứng minh phép ký gắn với một private key. Requirement cần xem:
- Signer identity, key custody, algorithm và certificate/trust chain.
- Payload canonicalization, version và signature encoding.
- Chỉ ký dữ liệu đã được workflow/approval cho phép.
- Key usage, rotation, revocation và verification lịch sử.
- Timestamp/trust evidence phù hợp use case.
- Verifier từ chối dữ liệu bị sửa, sai key hoặc thuật toán không được chấp thuận.

Một chữ ký mật mã hợp lệ **không tự chứng minh người dùng đã phê duyệt hành động nghiệp vụ**, nếu signing service bị chiếm hoặc được phép ký mọi payload.

## 10. Key management là phần bắt buộc của requirement

**Encryption mạnh nhưng key management yếu vẫn có thể làm mất mục tiêu bảo vệ.** Cần mô tả vòng đời khóa từ tạo, phê duyệt, sử dụng tới backup, rotate, revoke và destroy.

### 10.1. Lifecycle tối thiểu

~~~mermaid
flowchart TD
    A["Risk, purpose and key request"] --> B["Approve owner / algorithm / usage"]
    B --> C["Generate or controlled import"]
    C --> D["Activate and restrict operations"]
    D --> E["Use / monitor / audit"]
    E --> F{"Trigger: time / risk / compromise?"}
    F -- "No" --> E
    F -- "Yes" --> G["Rotate / rewrap / re-encrypt"]
    G --> H["Retain old key only while needed"]
    H --> I["Revoke / disable / archive"]
    I --> J["Destroy with copy / backup review"]
    J --> K["Verify and retain evidence"]
~~~

### 10.2. Requirement về khóa

**REQ-KEY-01 — Generation và import:** Khóa phải được sinh bằng cơ chế mật mã được chấp thuận và nguồn ngẫu nhiên phù hợp hoặc import qua quy trình được duyệt; nguồn và key attributes được kiểm chứng.

**REQ-KEY-02 — Registry/ownership:** Mỗi khóa phải có ID, owner, purpose, environment, allowed operations, data/resource scope, activation/rotation state và evidence references.

**REQ-KEY-03 — Least privilege:** Chỉ workload/operator được phê duyệt có quyền encrypt/decrypt/sign/wrap/unwrap đúng key. Quyền quản trị key không tự cho phép đọc dữ liệu nghiệp vụ.

**REQ-KEY-04 — Custody/protection:** Key material phải được bảo vệ theo risk bằng KMS/HSM/secure module hoặc cơ chế được phê duyệt; không hardcode trong repository, container image hoặc log.

**REQ-KEY-05 — Rotation/revocation:** Có triggers định kỳ hoặc sự kiện (compromise, role change, vendor, algorithm migration), cách cập nhật key references, rollback và kiểm chứng old-key behavior.

**REQ-KEY-06 — Backup/restore:** Nếu khả năng khôi phục dữ liệu phụ thuộc khóa, phải có backup/custody/recovery process và diễn tập thực tế theo RTO/RPO áp dụng.

**REQ-KEY-07 — Destruction:** Hủy key cần xét key bản sao, wrapped backup, replica, archive và nghĩa vụ giải mã dữ liệu lịch sử; ghi evidence và giới hạn kết luận.

**REQ-KEY-08 — Audit:** Key operation và thay đổi policy/role phải có audit events phù hợp, tránh lộ key/plaintext và bảo vệ tính toàn vẹn/retention.

### 10.3. KMS và HSM khác nhau

- **KMS:** API/service quản lý keys, policy, grants, lifecycle và có thể thực hiện crypto operations; một KMS có thể sử dụng HSM bên dưới.
- **HSM:** cryptographic module chuyên dụng có phần cứng/firmware và key/operation boundary cụ thể.
- **Cloud-managed KMS:** thuận tiện nhưng cần hiểu key backing, shared responsibility, audit, availability và restrictions.
- **Application secret store:** thường phục vụ secrets nhưng không mặc định là một cryptographic HSM hay hỗ trợ key non-exportability.

Requirement nên xác định **mức key custody/assurance cần đạt**, không chỉ ghi tên dịch vụ. Nếu policy yêu cầu validated cryptographic module, cần xác minh certificate, version, operational mode và scope áp dụng. **Validation của module không chứng minh toàn hệ thống IAM, key lifecycle hoặc application authorization đã đạt.**

### 10.4. Separation of duties và key ceremony

Khóa quan trọng có thể cần phân tách:
- Requester và approver.
- Security officer và application operator.
- Key custodian và auditor.
- Backup/restore operator và risk owner.
- Dual control hoặc M-of-N quorum theo sensitivity.

Không phải mọi DEK tạm thời cần một ceremony nhiều người. Scope control theo rủi ro của key; đừng tạo quy trình quá nặng cho thao tác không cần thiết, nhưng phải có **ceremony evidence** cho key quan trọng như root CA, code signing hay backup root khi policy yêu cầu.

## 11. Envelope encryption và tách KEK/DEK

Một mô hình phổ biến dùng **Data Encryption Key (DEK)** để mã hóa dữ liệu, còn **Key Encryption Key (KEK)** dùng để wrap/bảo vệ DEK.

~~~mermaid
flowchart LR
    DATA["Plaintext sensitive record"] --> ENC["App encryption: AEAD with DEK"]
    DEK["DEK / per object or dataset"] --> ENC
    ENC --> CT[("Ciphertext + IV + tag")]
    KEK["KEK in managed KMS/HSM"] --> WRAP["Wrap DEK"]
    DEK --> WRAP
    WRAP --> WDEK[("Wrapped DEK")]
    CT --> STORE[("Encrypted storage")]
    WDEK --> STORE
    STORE --> AUTH["Authorized read path"]
    AUTH --> UNWRAP["KMS unwrap after IAM/purpose check"]
    KEK --> UNWRAP
    UNWRAP --> DEC["AEAD decrypt with trusted AAD"]
    DEC --> OUT["Plaintext only to authorized consumer"]
~~~

Các vấn đề cần đặc tả:

- Ai được tạo/lấy DEK và unwrap DEK?
- DEK plaintext xuất hiện ở process memory nào và trong bao lâu?
- Key wrapping metadata có được kiểm tra integrity/purpose không?
- KEK và DEK có tách theo tenant, environment, dữ liệu hoặc use case không?
- Có thể swap wrapped DEK/ciphertext giữa tenant không?
- KMS outage làm hệ thống xử lý ra sao?
- Rotation KEK có cần rewrap, rotation DEK có cần re-encrypt dữ liệu?
- Key version cũ được giữ để đọc/restore tới bao giờ?
- Key deletion có làm mất backup/DR hoặc dữ liệu phải giữ theo retention không?

### 11.1. Không nhầm rotate KEK với rotate DEK

**Rotate KEK** thường đòi hỏi rewrap các DEK (tùy thiết kế); nếu DEK và ciphertext không đổi, rủi ro liên quan tới DEK có thể không được giải quyết.

**Rotate DEK** có thể đòi hỏi re-encrypt dữ liệu và thay metadata. Nếu key compromise đã xảy ra, cần đánh giá lại dữ liệu đã bị phơi lộ; chỉ rotate không thể xóa hậu quả của việc plaintext hoặc old key đã bị attacker lấy.

## 12. Yêu cầu về crypto-agility và vòng đời thuật toán

Security requirements nên có khả năng thích ứng khi thuật toán, key size, TLS protocols, certificate schemes hoặc provider trở nên không còn phù hợp.

Các thành phần cần:
- **Crypto standard version:** nguồn phê duyệt thuật toán/parameter và ngày hiệu lực.
- **Algorithm allowlist:** không cho phép fallback sang weak/legacy algorithm ngoài exception.
- **Key/ciphertext versioning:** dữ liệu có thể giải mã qua giai đoạn migration.
- **Dual-read/single-write:** có thể viết mới bằng thuật toán/key mới nhưng đọc lại dữ liệu cũ có kiểm soát trong giai đoạn chuyển tiếp.
- **Cutover plan:** migration, rollback, performance, capacity và business continuity.
- **Certificate/key lifetime:** rotation/reissue/renewal và trust distribution.
- **Inventory:** biết nơi dùng thuật toán/key nào, kể cả bên thứ ba.
- **Reassessment triggers:** security advisory, vendor lifecycle, standard update, incident hoặc thay đổi yêu cầu.

**Không hardcode lựa chọn mật mã như một giá trị tồn tại vĩnh viễn**. Một hệ thống có “AES-256” vẫn cần kiểm soát mode, nonce, permissions, key lifetime và dữ liệu đang sử dụng. Một hệ thống có “TLS 1.3” vẫn cần xác minh peer/identity và các trust boundaries khác.

### 12.1. Chuẩn mật mã và crypto policy

Một requirement có thể tham chiếu phiên bản đã phê duyệt của:
- Chính sách mật mã nội bộ.
- Chuẩn/khuyến nghị kỹ thuật do tổ chức hoặc cơ quan có thẩm quyền chấp nhận.
- Requirements theo hợp đồng, ngành và quốc gia áp dụng.
- Validation requirements đối với cryptographic modules nếu thật sự bắt buộc.

Không suy đoán rằng mọi hệ thống ở mọi nước đều phải theo một mức FIPS hoặc một thuật toán nhất định. **Ràng buộc pháp lý/kỹ thuật cụ thể cần được xác nhận theo phạm vi thực tế** bởi bộ phận có thẩm quyền trước khi ghi thành tiêu chí nghiệm thu.


## 13. Yêu cầu chống lỗi và hành vi fail-safe

Một thiết kế mật mã có thể đạt kiểm thử “happy path” nhưng hỏng khi key, certificate, provider hoặc metadata không khả dụng. Requirement phải mô tả cụ thể behavior tại các điểm thất bại.

| Lỗi | Hành vi nguy hiểm | Yêu cầu cần xác định |
|---|---|---|
| KMS không khả dụng | Dùng key hardcode/fallback plaintext | Không âm thầm giảm bảo vệ; fail-safe/degraded mode có thiết kế và phê duyệt |
| Key alias không tồn tại | Tạo key mới bất kỳ hoặc dùng default key chung | Từ chối operation không có key binding, ghi alert có kiểm soát |
| Authentication tag sai | Trả plaintext một phần hoặc nuốt exception | Từ chối dữ liệu, không dùng plaintext chưa xác thực |
| TLS certificate sai | Tắt hostname/certificate verification | Từ chối kết nối; lỗi được ghi không lộ secret |
| Certificate hết hạn | Hạ xuống HTTP | Không fallback plaintext; quy trình rotation và rollback |
| Randomness provider lỗi | Dùng seed cố định để tiếp tục | Không tạo key/nonce không đạt policy; fail-safe |
| Key bị revoke | Dùng bản backup cũ mà không kiểm tra | Kiểm lifecycle và policy khi sử dụng |
| AEAD algorithm/key version unknown | Thử các mode yếu cho tới khi decrypt thành công | Từ chối unsupported format/version; có migration path |
| Audit pipeline lỗi | Tắt audit vĩnh viễn | Durable queue/alert hoặc hạn chế operation nhạy cảm theo policy |
| Backup restore thiếu key | Bỏ mã hóa bản khôi phục | Restore đúng key policy hoặc dừng/quyết định DR có kiểm soát |

Không phải mọi outage phải làm toàn hệ thống ngừng hoạt động. Có thể cho phép hiển thị tài nguyên public trong khi khóa chức năng nhạy cảm. Nhưng hành vi degraded phải được **phân loại theo resource/action, kiểm thử và audit**, thay vì dùng permissive fallback.

### 13.1. Confidentiality–availability trade-off

Nếu KMS bị lỗi, hệ thống không thể decrypt dữ liệu mới. Giải pháp có thể gồm:
- Multi-zone KMS endpoints/HA theo dịch vụ được hỗ trợ.
- Retry có giới hạn, timeout và circuit breaker.
- Caching key material/derived keys **chỉ khi crypto policy cho phép**, với scope/TTL và bảo vệ memory phù hợp.
- Controlled read-only/degraded service khi không cần decrypt dữ liệu nhạy cảm.
- Runbook DR và diễn tập restore/region failure.
- Phê duyệt risk owner cho trường hợp khẩn cấp.

Không được biến cache khóa dài hạn không quản lý thành lời giải vô điều kiện cho availability; điều đó có thể làm tăng hậu quả host compromise.

## 14. Multi-tenant encryption và cô lập khóa/dữ liệu

Trong SaaS nhiều tenant, cần xác định xem mã hóa được thực hiện:
- Bằng một key chung cho toàn tổ chức.
- Theo application/region/environment.
- Theo tenant.
- Theo dataset/document.
- Theo object/record hoặc mỗi lần mã hóa.

**Không tồn tại một mức key granularity luôn tốt nhất.** Cô lập theo tenant có thể giảm một số blast radius nhưng tăng số keys, chi phí, lifecycle và độ phức tạp phục hồi. Requirement phải dựa trên risk, isolation objective, điều kiện dữ liệu và quản trị.

### 14.1. Ví dụ các yêu cầu

**REQ-CRYPTO-TENANT-01:** Dữ liệu của tenant A và B không được giải mã qua quyền của workload/identity chỉ thuộc tenant khác nếu policy không cho phép.

**REQ-CRYPTO-TENANT-02:** Application-layer ciphertext phải gắn với trusted tenant/resource context, bằng AAD hoặc mechanism tương đương phù hợp, và backend authorization phải độc lập kiểm tenant ownership.

**REQ-CRYPTO-TENANT-03:** Key registry/KMS permission phải hạn chế key use theo service, environment và key purpose; không để user tự chọn key của tenant khác từ request.

**REQ-CRYPTO-TENANT-04:** Backup, export, analytics, cache và search indices phải nằm trong scope phân tách dữ liệu; không coi tenant encryption trên bảng chính là đủ.

### 14.2. Đánh giá quyền hiệu lực

Một service có decrypt access cho key của tenant A nhưng cũng có quyền đổi KMS policy hoặc dùng deployment credential đặc quyền để giả mạo service B thì risk vẫn cao. Cần phân tích **effective access graph**: application IAM, KMS grants, control-plane roles, database queries và resource ownership.

Một ciphertext gắn AAD tenant A nhưng backend xây AAD từ query parameter do client điều khiển có thể vẫn bị lạm dụng. Phải dùng tenant context từ **verified principal và record metadata đáng tin**.

## 15. Mã hóa và key management trong cloud/container/CI/CD

### 15.1. Infrastructure as Code và policy-as-code

Requirements có thể được chuyển thành các checks:

- Object storage bật encryption mặc định và key policy hợp lệ.
- Volume/database/backup bật encryption theo classification.
- Không cho deploy secret hardcode hoặc service account quá quyền.
- IAM/KMS grants theo least privilege; không dùng wildcard ngoài exception.
- TLS enabled và certificate validation không bị tắt.
- Log/monitoring/alerting cho key operations và configuration changes.
- Replication/DR dùng key/region policy phù hợp.
- Runtime config được đối chiếu với IaC sau khi triển khai.

**IaC có cấu hình đúng không chứng minh runtime đang đúng.** Console edit, remote config, legacy deployment và provider defaults có thể thay đổi effective state.

### 15.2. Container và secret handling

Không nhúng private key, mật khẩu keystore hoặc KMS credential vào:
- Source repository.
- Dockerfile hoặc image layers.
- Plaintext config file trong artifact.
- CI/CD logs và build output.
- Debug endpoint/heap dump công khai.
- Các biến cấu hình default được commit.

Secret manager, workload identity và HSM/KMS APIs giúp tách key custody khỏi code, nhưng cũng cần kiểm soát ai được cấp secret, rotation, session và audit.

### 15.3. Continuous validation

Mỗi release nên có:
- Crypto dependency inventory và version review.
- Static checks cho insecure algorithms/modes và hardcoded secrets.
- Config tests cho TLS, IAM/KMS, storage encryption và certificate validation.
- Unit tests cho API mã hóa/xác thực.
- Integration tests cho authorized/unauthorized decrypt, key rotation và KMS outages.
- Runtime evidence snapshot và drift detection.
- Policy approval, exception registry, findings và retest.

## 16. Java 17: ví dụ yêu cầu bảo vệ một trường dữ liệu bằng AES-GCM

**Requirement minh họa — REQ-CRYPTO-APP-01:** “Trường kết quả thi chứa dữ liệu nhạy cảm được mã hóa theo cơ chế AEAD được phê duyệt trước khi ghi vào persistence layer; bản mã ràng buộc với tenant/record context, không thể giải mã thành plaintext hợp lệ khi ciphertext/tag/AAD bị sửa; key được cấp theo chính sách và quản lý ngoài code.”

Để minh họa phần **encrypt/decrypt**, ví dụ Java 17 sau dùng JCA với AES-GCM, random nonce 96-bit và authentication tag 128-bit. Nó **không triển khai KMS, envelope encryption, key registry production hoặc distributed nonce allocation**. Key chỉ được tạo trong memory phục vụ demo; trong hệ thống thật, key phải có owner, lifecycle, permission và provider/KMS phù hợp.

### 16.1. Cấu trúc ciphertext có version

~~~java
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

record EncryptedField(String keyId, byte[] nonce, byte[] ciphertext) {
    EncryptedField {
        if (keyId == null || keyId.isBlank()
                || nonce == null || nonce.length != 12
                || ciphertext == null || ciphertext.length < 16) {
            throw new IllegalArgumentException(
                    "Invalid encrypted field metadata");
        }

        // Avoid retaining mutable arrays owned by the caller.
        nonce = nonce.clone();
        ciphertext = ciphertext.clone();
    }

    @Override public byte[] nonce() {
        return nonce.clone();
    }

    @Override public byte[] ciphertext() {
        return ciphertext.clone();
    }
}

public final class AeadFieldCipher {
    private static final int NONCE_SIZE_BYTES = 12;
    private static final int AUTH_TAG_BITS = 128;
    private static final SecureRandom RANDOM = new SecureRandom();

    private AeadFieldCipher() {}

    // DEMO ONLY. Production keys need managed custody/lifecycle.
    public static SecretKey newDemoKey()
            throws GeneralSecurityException {
        KeyGenerator gen = KeyGenerator.getInstance("AES");
        gen.init(256, RANDOM);
        return gen.generateKey();
    }

    public static EncryptedField encrypt(
            String approvedKeyId,
            SecretKey key,
            byte[] plaintext,
            byte[] trustedAad) throws GeneralSecurityException {

        validateKeyAndContext(approvedKeyId, key, trustedAad);

        if (plaintext == null) {
            throw new IllegalArgumentException(
                    "Plaintext must be provided");
        }

        byte[] nonce = new byte[NONCE_SIZE_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(AUTH_TAG_BITS, nonce));
        cipher.updateAAD(trustedAad);

        // In Java GCM, doFinal returns ciphertext plus auth tag.
        byte[] ciphertext = cipher.doFinal(plaintext);
        return new EncryptedField(
                approvedKeyId, nonce, ciphertext);
    }

    public static byte[] decrypt(
            EncryptedField field,
            String expectedKeyId,
            SecretKey key,
            byte[] trustedAad) throws GeneralSecurityException {

        if (field == null) {
            throw new IllegalArgumentException(
                    "Encrypted field is missing");
        }
        validateKeyAndContext(expectedKeyId, key, trustedAad);

        // Prevent switching to an unrelated key alias from metadata.
        if (!Objects.equals(field.keyId(), expectedKeyId)) {
            throw new SecurityException("Unexpected key id");
        }

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(AUTH_TAG_BITS, field.nonce()));
        cipher.updateAAD(trustedAad);

        // Fails authentication when tag, ciphertext or AAD differs.
        return cipher.doFinal(field.ciphertext());
    }

    // Canonical, unambiguous AAD built from verified identifiers.
    public static byte[] aad(String tenantId, String recordId) {
        if (tenantId == null || tenantId.isBlank()
                || recordId == null || recordId.isBlank()) {
            throw new IllegalArgumentException(
                    "Tenant and record must be verified");
        }

        byte[] tenant = tenantId.getBytes(StandardCharsets.UTF_8);
        byte[] record = recordId.getBytes(StandardCharsets.UTF_8);

        return ByteBuffer.allocate(8 + tenant.length + record.length)
                .putInt(tenant.length)
                .put(tenant)
                .putInt(record.length)
                .put(record)
                .array();
    }

    private static void validateKeyAndContext(
            String keyId, SecretKey key, byte[] aad) {

        if (keyId == null || keyId.isBlank()
                || key == null
                || !"AES".equalsIgnoreCase(key.getAlgorithm())
                || aad == null || aad.length == 0) {
            throw new IllegalArgumentException(
                    "Invalid key or trusted context");
        }
    }
}
~~~

### 16.2. Điều code đã và chưa chứng minh

**Đã minh họa:**
- Sử dụng API AEAD với AES-GCM.
- Nonce ngẫu nhiên được sinh cho mỗi encryption.
- Không trả plaintext khi authentication tag không hợp lệ.
- AAD ràng buộc theo tenant và record, dùng canonical encoding với length prefix.
- Từ chối key identifier không phải expectedKeyId.
- Không dùng key hardcode trong demo.

**Chưa chứng minh:**
- Key được bảo vệ trong KMS/HSM hoặc không thể export.
- KMS IAM thực sự chặn dịch vụ không được phép decrypt.
- Nonce không bao giờ va chạm trong hệ phân tán/high-volume; **random nonce cần được đánh giá theo lượng dữ liệu, giới hạn thuật toán, key lifetime và risk**.
- Encryption at rest của database/backup và TLS của API.
- Caller đã authenticated/authorized; tenantId/recordId phải đến từ nguồn đáng tin.
- Ciphertext versioning/migration đầy đủ; record demo chỉ có keyId, không có explicit envelope version.
- Chống replay: attacker có thể phát lại một ciphertext cũ vẫn xác thực được nếu không có sequence/anti-replay rule.
- Logging/memory không làm lộ plaintext sau giải mã.
- Khóa demo được lưu/cấp/rotate/backup đúng chính sách.

**Chú ý:** Java arrays là mutable; code đã sao chép byte arrays trong constructor/accessor để tránh thay đổi không mong muốn qua record. Production cần thiết kế xử lý memory, concurrency, provider behavior và resource lifecycle phù hợp, chứ không xem việc clone arrays là cơ chế xóa dữ liệu bí mật.

### 16.3. JUnit 5 kiểm thử acceptance criteria

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.charset.StandardCharsets;
import javax.crypto.AEADBadTagException;
import javax.crypto.SecretKey;
import org.junit.jupiter.api.Test;

class AeadFieldCipherTest {

    private static byte[] bytes(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    @Test
    void roundTripWithinVerifiedRecordContext() throws Exception {
        SecretKey key = AeadFieldCipher.newDemoKey();
        byte[] aad = AeadFieldCipher.aad("tenant-A", "exam-42");

        EncryptedField sealed = AeadFieldCipher.encrypt(
                "exam-key-v3", key, bytes("answer-99"), aad);

        assertArrayEquals(bytes("answer-99"),
                AeadFieldCipher.decrypt(
                        sealed, "exam-key-v3", key, aad));
    }

    @Test
    void rejectsWrongTenantOrRecordContext() throws Exception {
        SecretKey key = AeadFieldCipher.newDemoKey();
        EncryptedField sealed = AeadFieldCipher.encrypt(
                "exam-key-v3", key, bytes("answer-99"),
                AeadFieldCipher.aad("tenant-A", "exam-42"));

        assertThrows(AEADBadTagException.class,
                () -> AeadFieldCipher.decrypt(
                        sealed, "exam-key-v3", key,
                        AeadFieldCipher.aad("tenant-B", "exam-42")));

        assertThrows(AEADBadTagException.class,
                () -> AeadFieldCipher.decrypt(
                        sealed, "exam-key-v3", key,
                        AeadFieldCipher.aad("tenant-A", "exam-43")));
    }

    @Test
    void rejectsTamperedCiphertext() throws Exception {
        SecretKey key = AeadFieldCipher.newDemoKey();
        byte[] aad = AeadFieldCipher.aad("tenant-A", "exam-42");
        EncryptedField sealed = AeadFieldCipher.encrypt(
                "exam-key-v3", key, bytes("answer-99"), aad);

        byte[] modified = sealed.ciphertext();
        modified[0] ^= 0x01;
        EncryptedField tampered = new EncryptedField(
                sealed.keyId(), sealed.nonce(), modified);

        assertThrows(AEADBadTagException.class,
                () -> AeadFieldCipher.decrypt(
                        tampered, "exam-key-v3", key, aad));
    }

    @Test
    void rejectsWrongKey() throws Exception {
        SecretKey key1 = AeadFieldCipher.newDemoKey();
        SecretKey key2 = AeadFieldCipher.newDemoKey();
        byte[] aad = AeadFieldCipher.aad("tenant-A", "exam-42");
        EncryptedField sealed = AeadFieldCipher.encrypt(
                "exam-key-v3", key1, bytes("answer-99"), aad);

        assertThrows(AEADBadTagException.class,
                () -> AeadFieldCipher.decrypt(
                        sealed, "exam-key-v3", key2, aad));
    }

    @Test
    void rejectsWrongKeyAliasEvenWithSameKey() throws Exception {
        SecretKey key = AeadFieldCipher.newDemoKey();
        byte[] aad = AeadFieldCipher.aad("tenant-A", "exam-42");
        EncryptedField sealed = AeadFieldCipher.encrypt(
                "exam-key-v3", key, bytes("answer-99"), aad);

        assertThrows(SecurityException.class,
                () -> AeadFieldCipher.decrypt(
                        sealed, "other-key", key, aad));
    }

    @Test
    void rejectsMissingTrustedAad() throws Exception {
        SecretKey key = AeadFieldCipher.newDemoKey();

        assertThrows(IllegalArgumentException.class,
                () -> AeadFieldCipher.encrypt(
                        "exam-key-v3", key, bytes("x"), null));
    }

    @Test
    void rejectsMalformedEnvelope() {
        assertThrows(IllegalArgumentException.class,
                () -> new EncryptedField("key", new byte[4], new byte[32]));
    }
}
~~~

### 16.4. Kiểm thử bên ngoài đơn vị mật mã

Các unit tests phía trên phải được bổ sung:

- **Integration KMS/IAM:** service được duyệt decrypt thành công; service khác, tenant khác, role hết hạn bị từ chối.
- **Persistence:** chỉ ciphertext xuất hiện trong DB/object log; backups/replicas thuộc scope được bảo vệ.
- **TLS:** certificate/hostname invalid bị từ chối, không có plaintext fallback.
- **Rotation:** đọc được bản ghi key version cũ theo policy; ghi mới dùng key mới; có kế hoạch disable/destroy.
- **Recovery:** restore encrypted backup với authorized key recovery, đo RTO/RPO thực tế.
- **Misuse:** không thể chọn key alias từ request, không thể swap ciphertext tenant/record và không có direct export plaintext ngoài policy.
- **Failure:** KMS timeout, key revoked, unknown envelope, invalid tag không được trả success hoặc plaintext chưa xác thực.
- **Audit:** key operations/authorization decisions được ghi theo schema tối thiểu, không chứa key/plaintext/PII không cần.

Không chạy destructive key rotation/delete/firmware tests trên production nếu chưa có ủy quyền và runbook.

## 17. Mẫu hồ sơ requirements bằng YAML

Một tài liệu requirements có thể chứa **normative behavior, rationale, acceptance criteria và traceability**, còn thuật toán/tham số thực tế tham chiếu tới crypto standard có version.

~~~yaml
requirements_set:
  id: "CRYPTO-REQ-LEARNING-005"
  module: "SECURITY_SECURITY_ASSURANCE"
  chapter: "Security requirements"
  topic: "Requirement về mã hóa"
  version: "1.0"
  environment: "production"
  owner: "<security-architect-and-data-owner>"
  crypto_policy:
    policy_id: "<approved-crypto-standard-id>"
    version: "<approved-version>"
  scope:
    system: "multi-tenant-learning-platform"
    assets:
      - "learner-pii"
      - "exam-results"
      - "exports"
      - "backups"
    data_states: ["at-rest", "in-transit", "in-use"]
    access_paths: ["web", "api", "batch-export", "backup-dr"]
  requirements:
    - id: "REQ-CRYPTO-REST-01"
      objective: "Confidentiality of sensitive data copies"
      statement: >
        All Confidential and Restricted data in primary storage,
        replicas, exports and backups must use approved encryption.
      owner: "<storage-data-owner>"
      risk_refs: ["RISK-CRYPTO-01"]
      controls: ["CTRL-CRYPTO-01"]
      acceptance:
        - "New objects use approved encryption and key policy"
        - "Runtime config and replication paths comply"
        - "Unauthorized key use is denied"
      tests: ["TEST-CRYPTO-01", "TEST-CRYPTO-04"]
      evidence_refs: ["<runtime-storage-snapshot>", "<kms-negative-test>"]
    - id: "REQ-CRYPTO-TRANSIT-01"
      objective: "Confidentiality and integrity in transit"
      statement: >
        Sensitive connections across documented trust boundaries
        must use approved TLS and verified peer identities.
      owner: "<network-platform-owner>"
      risk_refs: ["RISK-CRYPTO-02"]
      controls: ["CTRL-CRYPTO-02"]
      acceptance:
        - "Invalid certificate or hostname is rejected"
        - "No plaintext fallback on sensitive paths"
      tests: ["TEST-CRYPTO-06", "TEST-CRYPTO-07"]
      evidence_refs: ["<tls-config>", "<negative-certificate-test>"]
    - id: "REQ-CRYPTO-APP-01"
      objective: "Application-layer confidentiality and integrity"
      statement: >
        Exam result fields are protected by approved AEAD encryption
        with resource/tenant context and controlled key usage.
      owner: "<application-owner>"
      controls: ["CTRL-CRYPTO-03"]
      acceptance:
        - "Tampered ciphertext, tag or AAD is rejected"
        - "Wrong tenant/record context does not decrypt"
        - "Key version is validated by approved registry"
      tests: ["TEST-CRYPTO-11", "TEST-CRYPTO-13"]
      evidence_refs: ["<app-integration-tests>", "<key-registry-review>"]
    - id: "REQ-KEY-05"
      objective: "Safe cryptographic key lifecycle"
      statement: >
        Keys have approved rotation and recovery procedures,
        with evidence of old-key handling and access restrictions.
      owner: "<key-management-owner>"
      controls: ["CTRL-CRYPTO-04"]
      acceptance:
        - "New encrypt operations use approved current key"
        - "Old keys are disabled or retained only as authorized"
        - "Restore exercise meets approved recovery criteria"
      tests: ["TEST-CRYPTO-19", "TEST-CRYPTO-20"]
      evidence_refs: ["<rotation-report>", "<restore-report>"]
  assessment:
    release: "<release-id>"
    tested_at: "<ISO-8601>"
    status: "INCONCLUSIVE"
    limitations:
      - "Legacy export path is not yet assessed"
  exception_management:
    approver: "<authorized-risk-owner>"
    required_fields: ["scope", "rationale", "controls", "expiry"]
  reassessment_triggers:
    - "New data state, access path, tenant or export workflow"
    - "Key compromise, certificate or algorithm policy change"
    - "New storage, KMS, library, provider or DR architecture"
~~~

YAML này là **mẫu dữ liệu học tập, không phải config chạy được cho một sản phẩm cụ thể**. Khi áp dụng thật cần schema, validation và workflow quản lý version/approval. Không lưu raw key, secret, credential hoặc plaintext PII trong requirements/evidence record.

## 18. Requirements-to-controls traceability matrix

Một mapping minh bạch giúp xác định requirement nào chưa có control hoặc chưa được đánh giá đầy đủ.

| Risk / threat | Requirement | Control đề xuất | Phương pháp đánh giá | Evidence |
|---|---|---|---|---|
| **RISK-CRYPTO-01:** bản sao PII bị lấy | REQ-CRYPTO-REST-01 | CTRL-CRYPTO-01: storage encryption + KMS | Runtime config/object/backup review | Resource inventory, key policy, scan |
| **RISK-CRYPTO-02:** traffic bị nghe/sửa | REQ-CRYPTO-TRANSIT-01/02 | CTRL-CRYPTO-02: verified TLS/mTLS | Invalid-cert, plaintext-fallback tests | TLS config, PEP/service traces |
| **RISK-CRYPTO-03:** ciphertext bị sửa | REQ-CRYPTO-APP-01 | CTRL-CRYPTO-03: AEAD with trusted AAD | Tampered tag/ciphertext/AAD tests | Unit/integration reports |
| **RISK-CRYPTO-04:** key bị lộ từ artifact | REQ-KEY-04 | CTRL-CRYPTO-04: approved key custody | Secrets scan, runtime key review | KMS/HSM config, CI result |
| **RISK-CRYPTO-05:** decrypt quá quyền | REQ-KEY-03 | CTRL-CRYPTO-05: least-privilege KMS policies | Wrong-client/tenant/decrypt test | IAM diff, negative test, audit |
| **RISK-CRYPTO-06:** không khôi phục sau key loss | REQ-KEY-06 | CTRL-CRYPTO-06: backup/restore/DR | Restore exercise, key recovery test | DR report, actual RTO/RPO |
| **RISK-CRYPTO-07:** thuật toán cũ yếu | Crypto-agility requirement | CTRL-CRYPTO-07: allowlist/inventory/migration | Unsupported algorithm rejection | Policy version, inventory, CI checks |
| **RISK-CRYPTO-08:** nonce bị reuse | AEAD nonce requirement | CTRL-CRYPTO-08: nonce strategy + lifetime | Load/concurrency/restart analysis | Design proof, negative tests, usage metrics |
| **RISK-CRYPTO-09:** password dễ brute-force | Password hashing requirement | CTRL-CRYPTO-09: approved password hashing | Config/schema review, migrated hash tests | Auth design, regression evidence |
| **RISK-CRYPTO-10:** ký nội dung sai nghiệp vụ | Signature authorization requirement | CTRL-CRYPTO-10: signing policy/approval | Wrong-purpose/payload tests | Approval trace, signature logs |
| **RISK-CRYPTO-11:** plaintext từ logs/export | Data-copy requirement | CTRL-CRYPTO-11: minimization/secure export/logging | Synthetic secret, data-flow tests | Log sample, DLP/export review |
| **RISK-CRYPTO-12:** key revocation không hiệu lực | REQ-KEY-05/07 | CTRL-CRYPTO-12: key lifecycle and deny | Old-key access/revoke/restore tests | Key state, KMS logs, retest |

ID trong bảng là **ví dụ của bài học**, không phải định danh tiêu chuẩn bên ngoài. Khi tạo traceability thực tế cần liên kết tới risk register, security control catalogue, threat model và requirement version được duyệt.

### 18.1. Kiểm tra coverage từ hai chiều

**Forward traceability:** mỗi risk quan trọng có ít nhất một requirement; mỗi requirement có control, test và evidence.

**Backward traceability:** mỗi control và test có mục tiêu/risk hợp lý; không đưa vào controls chỉ vì một product bật được.

Các trường hợp cần cảnh báo:
- Requirement không có owner.
- Requirement có “implemented” nhưng không có evidence.
- Control có test happy path nhưng thiếu negative tests.
- Test kiểm cấu hình staging, trong khi conclusion tuyên bố production.
- Evidence thiếu timestamp/version/resource.
- Exception hết hạn vẫn được dùng.
- Finding đã đóng nhưng chưa retest effective operation.

## 19. Ma trận kiểm thử requirement về mã hóa

Để kết luận có bằng chứng, cần ít nhất **positive, negative, integration, failure-path và operational testing** theo phạm vi.

| Test ID | Kịch bản | Kỳ vọng | Evidence |
|---|---|---|---|
| **TEST-CRYPTO-01** | Tạo object nhạy cảm mới trong bucket production | Encryption và key ID đúng baseline | Runtime object metadata |
| **TEST-CRYPTO-02** | Tạo resource/storage với encryption disabled | IaC/admission/runtime policy chặn hoặc finding theo tiêu chí | Policy-as-code, runtime scan |
| **TEST-CRYPTO-03** | Backup/replica sang DR region | Encryption/key policy đúng và có restore path | Backup/replication evidence |
| **TEST-CRYPTO-04** | Workload không được cấp decrypt dùng KMS key | DENY | IAM/KMS negative test |
| **TEST-CRYPTO-05** | Storage principal đọc object ngoài scope | DENY theo data authorization; mã hóa không thay quyền | Access negative test |
| **TEST-CRYPTO-06** | Client TLS gặp certificate không tin cậy | Từ chối kết nối | TLS integration log |
| **TEST-CRYPTO-07** | Hostname của certificate không khớp | Từ chối, không tắt verification | Negative TLS test |
| **TEST-CRYPTO-08** | Backend TLS connection bị tắt | Chặn/alert theo policy, không chỉ kiểm edge | Service mesh/DB config test |
| **TEST-CRYPTO-09** | Certificate hết hạn hoặc thay version | Rotation thành công; expired certificate bị từ chối | Cert lifecycle test |
| **TEST-CRYPTO-10** | Nhận weak/unsupported TLS protocol | Reject | Protocol negotiation test |
| **TEST-CRYPTO-11** | AEAD encrypt/decrypt với đúng key, AAD | Round-trip thành công | Java unit test |
| **TEST-CRYPTO-12** | Thay ciphertext hoặc authentication tag | Authentication fail, không trả plaintext | Tamper negative test |
| **TEST-CRYPTO-13** | Thay tenant/record AAD | Không decrypt được | Context-binding test |
| **TEST-CRYPTO-14** | Dùng wrong key/key ID/version | Reject, không thử fallback key ngoài policy | Key-selection test |
| **TEST-CRYPTO-15** | Nonce/IV generation dưới parallel load | Tuân thủ chiến lược uniqueness và giới hạn vận hành | Design review, stress analysis |
| **TEST-CRYPTO-16** | Replay ciphertext/message cũ | Protocol ngăn hoặc phát hiện theo anti-replay requirement | Sequence/idempotency test |
| **TEST-CRYPTO-17** | Password mới được tạo | Chỉ lưu approved password hash/parameters | Auth storage/config tests |
| **TEST-CRYPTO-18** | Log nhận token, key, raw PII | Không lưu hoặc redact theo schema | Synthetic secret/log test |
| **TEST-CRYPTO-19** | Rotate key phiên bản mới | New write dùng key mới, read lịch sử theo policy | Rotation integration evidence |
| **TEST-CRYPTO-20** | Restore encrypted backup cùng key custody | Đọc/khôi phục thành công theo RTO/RPO | DR exercise report |
| **TEST-CRYPTO-21** | Key đã revoke, workload tiếp tục decrypt | Từ chối theo lifecycle semantics | KMS negative test |
| **TEST-CRYPTO-22** | KMS outage/timeout | Fail-safe; không dùng hardcoded key hoặc plaintext | Fault-injection report |
| **TEST-CRYPTO-23** | TLS trust store bị thiếu/khác | Reject hoặc lỗi có kiểm soát | Boot/runtime config test |
| **TEST-CRYPTO-24** | App producer gửi dữ liệu qua queue/logging | Các bản sao đáp ứng data-state policy | Data flow integration |
| **TEST-CRYPTO-25** | Public/legacy export dùng key/ACL khác | Không bypass policy hoặc có exception được duyệt | Direct-path negative test |
| **TEST-CRYPTO-26** | Thêm tenant mới hoặc region mới | Không tự dùng key/permission rộng ngoài baseline | Provisioning/tenant-isolation test |
| **TEST-CRYPTO-27** | Admin đổi KMS policy/algorithm selection | Có approval/audit/alert theo governance | Change-control evidence |
| **TEST-CRYPTO-28** | Xóa key khi còn backup hoặc dữ liệu lịch sử | Prevent hoặc risk-approved workflow, không gây mất dữ liệu bất ngờ | Destruction/restore procedure test |
| **TEST-CRYPTO-29** | Hệ thống dùng unsupported algorithm/ciphertext version | Reject; không tự downgrade | Version/format negative test |
| **TEST-CRYPTO-30** | Policy CI pass nhưng runtime config bị drift | Phát hiện và xử lý drift | CI-vs-runtime evidence |
| **TEST-CRYPTO-31** | User tenant A truy cập bản mã tenant B qua ứng dụng | Business authorization + key policy từ chối | Cross-tenant E2E |
| **TEST-CRYPTO-32** | Ký payload bị sửa/sai purpose | Verify hoặc signing gateway từ chối | Signature + business logic tests |

### 19.1. Kiểm thử có giới hạn và đủ quyền

- Dùng synthetic data, test keys, test partitions và môi trường được ủy quyền.
- Tránh hủy key hoặc xóa dữ liệu production để “thử xem có restore được không”.
- Test TLS negative cần có target environment hợp lệ, không tấn công hệ thống bên thứ ba.
- Backup/restore phải có runbook, checkpoint và người phê duyệt.
- Evidence không lưu raw private key, secret hoặc dữ liệu nhạy cảm.
- Ghi build/release, policy version, environment, data class, key version, timestamp, expected/actual outcome và test owner.
- Với environment có giới hạn không thể thực nghiệm trực tiếp, ghi **limitation và phương pháp thay thế**, không tự đánh dấu PASS.

### 19.2. Mốc chấp nhận phải gắn với risk

Một số yêu cầu cần ngưỡng có thể đo:
- Thời gian sửa lỗi key policy.
- Độ mới của access review/key inventory.
- Thời gian xử lý certificate gần hết hạn.
- Thời gian từ compromise tới effective key revoke.
- RTO/RPO sau restore.
- Tỷ lệ tài nguyên thuộc scope có encryption configuration được kiểm chứng.

Ngưỡng cụ thể cần đến từ **security policy, khả năng vận hành và risk owner**, không nên sao chép một con số tùy ý rồi coi là chuẩn chung.

## 20. Claim – Argument – Evidence cho requirement mã hóa

Một assurance claim cần có **scope, điều kiện và giới hạn**.

| Thành phần | Ví dụ |
|---|---|
| **Claim** | Dữ liệu hồ sơ học viên Confidential/Restricted trên các paths và environments thuộc phạm vi release đã đánh giá được bảo vệ bằng các controls mã hóa at rest và in transit phù hợp, cùng key governance và kiểm thử failure paths |
| **Argument** | Inventory/DFD xác định mọi bản copy; crypto policy quy định cơ chế; KMS/IAM giới hạn key use; TLS peer verification; application AEAD bảo vệ dữ liệu; runtime và negative tests hỗ trợ |
| **Evidence: design** | Threat model, data classification, DFD, crypto standard/ADR, requirements set |
| **Evidence: implementation** | IaC + runtime config, JCA provider setup, TLS settings, key registry và IAM policies |
| **Evidence: tests** | Tamper/AAD/TLS invalid cert, unauthorized KMS use, rotation, restore, outage |
| **Evidence: operations** | KMS/HSM access logs, key lifecycle records, cert monitoring, drift review, findings |
| **Assumptions** | Trust anchors, provider cryptographic primitives và identity sources hoạt động trong scope được kiểm soát |
| **Limitations** | Một đường export legacy chưa có runtime evidence; một offline backup chưa được restore trong kỳ |
| **Residual risk** | Ứng dụng có quyền giải mã bị chiếm; dữ liệu lộ trong memory/log ở path chưa bao phủ; certificate/key compromise detection delay |
| **Conclusion** | PASS/FAIL/INCONCLUSIVE có owner/risk decision, không tuyên bố an toàn tuyệt đối |

### 20.1. Design, implementation, operating và remediation effectiveness

| Mức | Câu hỏi | Evidence |
|---|---|---|
| **Design effectiveness** | Requirements và crypto design có giảm đúng rủi ro? | Threat model, requirement-to-control mapping, key hierarchy |
| **Implementation effectiveness** | Cấu hình/code đã áp dụng đúng trên release và resource? | Runtime storage/TLS/KMS config, negative integration |
| **Operating effectiveness** | Trong kỳ, rotation, certificate renewals, access review, restore và alerts diễn ra đúng? | KMS events, change records, DR tests, incident logs |
| **Remediation effectiveness** | Sai lệch đã sửa trên runtime và không tái diễn ở đường khác? | New release/config, retest, population scan, owner sign-off |

Một giấy xác nhận sản phẩm hỗ trợ thuật toán không chứng minh application dùng đúng mode hoặc key. Một lần encrypt/decrypt thành công không chứng minh data at rest hay backup đúng. Một config snapshot một node không chứng minh mọi replica hoặc region đã áp baseline.

### 20.2. Khi nào kết quả INCONCLUSIVE?

- Không có population đầy đủ các data stores/export paths.
- Chưa thấy key registry hoặc không rõ key owner.
- Không thể xác minh certificate validation behavior thực tế.
- Test chỉ chạy staging nhưng claim là production.
- Không thể xác định dữ liệu cache/log có plaintext.
- Chưa thử restore và không biết backup key custody.
- Evidence bị thiếu thời điểm hoặc version.
- Một exception quan trọng không có approver/expiry.

**INCONCLUSIVE không đồng nghĩa FAIL:** nó nói chưa đủ bằng chứng để kết luận. Nhưng risk owner vẫn phải quyết định hạn chế rollout hoặc compensating controls tùy tác động và nghĩa vụ.

## 21. Finding mẫu: TLS chỉ có ở gateway, backend bỏ qua verification

Giả định nhóm dự án kết luận REQ-CRYPTO-TRANSIT-02 đã đạt vì public URL có HTTPS. Audit phát hiện một internal HTTP client đặt trust-all verifier để kết nối tới certificate không hợp lệ trên service downstream.

| Trường | Nội dung |
|---|---|
| **Finding ID** | FND-CRYPTO-005 |
| **Criteria** | REQ-CRYPTO-TRANSIT-02: peer identity trên đường nhạy cảm phải được xác minh |
| **Condition** | Service-to-service HTTP client bỏ qua certificate chain/hostname checks |
| **Evidence** | Source/config review, negative test cho bad certificate và runtime connection trace |
| **Risk** | Kẻ có khả năng can thiệp mạng hoặc điều khiển endpoint có thể giả service, đọc/sửa dữ liệu |
| **Root cause cần xác minh** | Workaround từ môi trường test được kế thừa sang production; review chỉ kiểm edge TLS |
| **Owner** | Service owner, platform/security engineering |
| **Immediate action** | Khóa đường không được xác minh hoặc giới hạn truy cập; đánh giá session/data đã chịu ảnh hưởng |
| **Khắc phục** | Loại bỏ trust-all, dùng trust store/PKI/mTLS được duyệt, quản lý cert lifecycle, test fail-safe |
| **Verification** | Certificate hợp lệ kết nối được; bad chain/hostname bị từ chối trên runtime; scan các HTTP clients khác |
| **Residual risk** | Legacy client và lưu lượng sang vendor cần đánh giá theo DFD mới |

**Không đóng finding** chỉ bằng việc đổi một dòng source. Cần xác minh binary/release đang chạy, trust configuration, environment overrides và các HTTP client khác không còn đường bypass.

### 21.1. Finding khác: KMS key dùng chung không giới hạn

Một DB backup encrypted nhưng key được cấp cho mọi workload trong tài khoản cloud. Từ góc độ **at-rest encryption** có thể đúng; từ góc độ **unauthorized decrypt** requirement có thể chưa đạt. Remediation phải bao gồm policy IAM, key separation, credential lifecycle và negative authorization tests.

## 22. Audit security requirements: population, sampling và bằng chứng

### 22.1. Population không chỉ là bảng yêu cầu

Để đánh giá completeness, cần lập danh sách:
- Các data classes và datasets thuộc scope.
- Database, object storage, cache, search, log, backup, DR replicas.
- Network paths, internal services, external integrations, certificates.
- Encryption keys, key versions, signing keys, KEKs/DEKs.
- Key owners, KMS/HSM partitions, IAM grants và privileged operators.
- Applications, environments, releases và legacy deployments.
- Encryption exceptions, key rotation events, KMS incidents.
- Các yêu cầu và test results liên quan từ SDLC/operations.

Nếu chỉ lấy mẫu những bucket đã được gắn tag “encrypted”, sẽ bỏ sót bucket mới không có tag hoặc đường export legacy. **Completeness của scope** là điều kiện trước khi kết luận effectiveness.

### 22.2. Lấy mẫu có giới hạn

Giả định auditor chọn 20 object stores trong population 120 stores có PII; 3 stores không có bằng chứng key access review. Kết luận chắc chắn là **3/20 stores trong mẫu thiếu evidence review**. Không suy ra tỷ lệ 15% toàn bộ stores nếu sampling không được thiết kế hỗ trợ suy luận thống kê.

Mẫu cần ưu tiên risk cao: PII, signing keys, privilege grants, cross-account backup, public-facing endpoints, large exports, decrypt permissions và ngoại lệ vừa thay đổi.

### 22.3. Evidence quality

| Tiêu chí | Cần xác minh |
|---|---|
| **Relevance** | Evidence hỗ trợ đúng requirement/asset/property? |
| **Completeness** | Toàn bộ paths, resource copies và keys có trong population? |
| **Provenance** | Ai/công cụ nào tạo, từ account/resource nào? |
| **Integrity** | Config export, logs, approvals có bị sửa xóa không được phát hiện? |
| **Freshness** | Snapshot/test có đúng release và policy version đang đánh giá? |
| **Repeatability** | Có procedure và expected result để lặp lại? |
| **Independence** | Người tự cấu hình có tự phê duyệt/chứng nhận control khi policy yêu cầu kiểm tra độc lập? |
| **Confidentiality** | Evidence có vô tình lưu plaintext, key hoặc secret? |
| **Traceability** | Kết nối requirement → control → test → artifact → owner/finding? |

### 22.4. Tách bằng chứng cấu hình và hoạt động

- **Configuration evidence:** policy hiện tại định nghĩa encryption, key use và TLS như thế nào.
- **Runtime evidence:** một resource/connection đang thực sự áp cấu hình gì.
- **Test evidence:** khi cố truy cập trái phép, thao tác có bị từ chối không.
- **Operational evidence:** trong kỳ đã có rotation, restore, cert renewal, audit review và response như thế nào.

Không lấy một screenshot “encrypted=true” thay cho toàn bộ assurance case.

## 23. Metrics cho cryptographic requirements

| Metric | Câu hỏi trả lời | Giới hạn |
|---|---|---|
| **Encrypted storage coverage** | Các resources thuộc scope có encryption được kiểm chứng chiếm tỷ lệ nào? | Encryption không chứng minh key use bị hạn chế |
| **Transit protection coverage** | Những trust-boundary connections nào dùng verified TLS? | Edge TLS không bao phủ backend |
| **KMS/key owner coverage** | Khóa có owner, purpose và registry? | Có metadata không chứng minh quyền đúng |
| **Excess decrypt grants** | Bao nhiêu principal có quyền decrypt vượt nhiệm vụ? | Cần effective-permission analysis |
| **Certificate risk exposure** | Chứng thư yếu/hết hạn/sắp hết hạn theo policy | Số chứng thư không bằng chất lượng TLS |
| **Rotation policy compliance** | Key nào đã rotate theo triggers/plan? | Rotation không đồng nghĩa old key đã hủy |
| **Restore exercise pass rate** | Có khôi phục được dữ liệu encrypted trong mục tiêu? | Một lần restore không bao phủ mọi DR scenario |
| **Crypto test negative coverage** | Bao nhiêu failure paths đã test? | Số lượng test không chứng minh completeness |
| **Crypto drift age** | Sai lệch production tồn tại bao lâu? | Phải phân loại severity |
| **Unapproved algorithm usage** | Những vị trí dùng algorithm ngoài allowlist | Inventory thiếu làm chỉ số sai |
| **Key revocation effective latency** | Từ revoke tới khi operations bị từ chối | Cần đo ở API/KMS/session cụ thể |
| **Open cryptographic findings** | Rủi ro chưa khắc phục và thời gian mở | Cần impact, không chỉ count |
| **Evidence freshness** | Evidence có phản ánh release/current scope? | Evidence mới vẫn có thể thiếu nguồn hoặc không phù hợp |

### 23.1. Ví dụ diễn giải số liệu đúng

Nếu tổng 200 object stores đã xác định thuộc scope, 190 store có runtime evidence phù hợp, 5 store thiếu encryption và 5 store chưa thu được evidence, có thể ghi:
- **Verified compliant:** 190/200.
- **Known non-compliant:** 5/200.
- **Unknown/inconclusive:** 5/200.

Không gộp “chưa biết” vào “đạt” và không tuyên bố “95% dữ liệu đã an toàn”: object store có mức dữ liệu và quyền khác nhau; con số chỉ phản ánh **coverage của điều kiện đã định nghĩa**, chưa phản ánh mọi rủi ro.

## 24. Governance, trách nhiệm và phê duyệt

| Vai trò | Trách nhiệm |
|---|---|
| **Business/data owner** | Phân loại dữ liệu, mục đích, ảnh hưởng khi lộ/hỏng/mất dữ liệu |
| **Security architect** | Chuyển risk/objective thành requirements có thể kiểm chứng |
| **Cryptography/key management owner** | Crypto policy, key custody, algorithms, rotation và backup |
| **Application owner** | Triển khai application encryption, TLS validation, error handling, authorization |
| **Platform/cloud owner** | Storage/DB/network encryption, IAM/KMS config, CI/IaC policy |
| **Identity/IAM owner** | Workload identity, authorized key operations, privileged access |
| **Backup/DR owner** | Encrypted backup, key recovery và restore exercises |
| **QA/security tester** | Positive/negative/failure tests, regression và test evidence |
| **Privacy/legal/compliance** | Nghĩa vụ theo dữ liệu/ngành/quốc gia và limitation |
| **Auditor/assessor** | Đánh giá độc lập control design/implementation/operations |
| **Risk owner** | Chấp nhận residual risk/exception theo thẩm quyền |

### 24.1. RACI cần cho vòng đời khóa

Một người không nên tự tạo root/signing key, cấp mọi quyền decrypt, chỉnh audit log và phê duyệt chính thao tác đó khi policy yêu cầu SoD. Với key nhạy cảm, cân nhắc:
- Independent approval.
- Dual control/M-of-N quorum khi cần.
- Privileged access management.
- Key ceremony/witness evidence.
- Separate audit review.
- Break-glass có hạn, scope và hậu kiểm.

Không nên yêu cầu quorum cho mọi key session tạm thời nếu không có risk rationale; controls cần cân bằng tính thực thi và độ bảo đảm.

## 25. Requirements trong SDLC và continuous assurance

Một cryptographic requirement phải tồn tại xuyên suốt kiến trúc, code, deploy và vận hành.

| Giai đoạn | Việc cần làm | Bằng chứng |
|---|---|---|
| **Discovery** | Data inventory, classification, use cases, stakeholders | Inventory/DFD |
| **Risk assessment** | Threats về leak, tamper, key misuse, crypto failure | Risk register, STRIDE |
| **Requirement design** | Normative statements, acceptance criteria, crypto policy | Approved requirement set |
| **Architecture** | Chọn layers, key hierarchy, TLS/PKI, trust boundaries, DR | ADR, diagrams, policy mapping |
| **Development** | JCA/provider đúng, AEAD, secrets handling, business authz | Code review, static checks |
| **CI/CD** | Policy-as-code, crypto dependency review, test suite | Pipeline results, PR approvals |
| **Pre-production** | KMS/TLS/backup integration và failure-path tests | Reports, logs, evidence IDs |
| **Release** | Production config, key/cert refs, no insecure fallback, exceptions | Release gate, runtime snapshot |
| **Operations** | Monitor key operations, certificate expiry, drift, access reviews | KMS/HSM logs, alerts, tickets |
| **Rotation/incident** | Handle compromise, revoke, migration, key recovery | Incident timeline, rotation/restore tests |
| **Decommission** | Dispose data, key copies/backup, certificate retirement | Key destruction/retention evidence |
| **Reassessment** | Khi risk, standard, algorithm, architecture hoặc data scope đổi | Updated mapping, decisions, retest |

### 25.1. Triggers phải đánh giá lại

- Thêm tenant, data class hoặc bên nhận dữ liệu.
- Thay database, storage, cloud account, region/replication.
- Chuyển từ monolith sang microservices hoặc thêm public API.
- Thay KMS/HSM, key custody, key hierarchy hoặc IAM policy.
- Thay crypto provider/library/JDK hoặc TLS termination.
- Security advisory hoặc thuật toán không còn được duyệt.
- Key/certificate nghi compromise, mất quyền quản trị hoặc incident.
- Thay backup/DR, retention hoặc deletion/crypto-erasure policy.
- Thêm export, analytics, search, cache, mobile offline storage.
- Audit finding, KMS outage, restore test thất bại hoặc runtime drift.
- Chính sách, yêu cầu khách hàng, hợp đồng hoặc quy định áp dụng thay đổi.

### 25.2. Continuous feedback loop

~~~mermaid
flowchart TD
    A["Data / threat / architecture change"] --> B["Reassess risk and security objective"]
    B --> C["Update measurable crypto requirement"]
    C --> D["Approve controls, key design and exceptions"]
    D --> E["Implement and verify via tests"]
    E --> F["Capture runtime and operational evidence"]
    F --> G{"Claim supported?"}
    G -- "Yes within scope" --> H["Operate and monitor"]
    G -- "No / inconclusive" --> I["Finding, owner and remediation"]
    I --> J["Deploy fixes and retest"]
    J --> F
    H --> A
~~~

## 26. Những ngộ nhận phổ biến

| Ngộ nhận | Vì sao không đủ | Cách hiểu đúng |
|---|---|---|
| “Đã dùng AES-256 nên dữ liệu an toàn.” | Mode, nonce, key custody và plaintext paths có thể sai | Requirement phải kiểm cipher configuration và toàn data flow |
| “Đã bật TDE thì admin không đọc được dữ liệu.” | Database có thể giải mã khi phục vụ query | Xác định threat boundary và quyền giải mã |
| “HTTPS ở CDN nghĩa mọi hop đều bảo mật.” | TLS có thể terminate trước backend | Kiểm mọi trust boundary |
| “TLS không cần kiểm hostname nếu kênh đã encrypted.” | Không xác minh peer tạo cơ hội MITM | Verify chain/identity và fail-safe |
| “Hash password bằng SHA-256 là đủ.” | Hash nhanh không phù hợp password storage | Password hashing được thiết kế cho mật khẩu |
| “Dùng hash là dữ liệu không thể bị sửa.” | Attacker có thể tính lại hash không có secret/trust | MAC/signature/AEAD theo mục tiêu |
| “AES-GCM mã hóa luôn chống replay.” | Ciphertext cũ vẫn có thể xác thực | Thêm sequence/nonce protocol/idempotency theo use case |
| “Nonce là secret nên không được lưu cùng ciphertext.” | Nonce thường không cần bí mật, cần uniqueness | Bảo vệ key và nonce strategy |
| “Rotate KEK là đã rotate toàn bộ dữ liệu.” | DEK/ciphertext có thể không đổi | Phân biệt rewrap với re-encryption |
| “Có HSM thì app không thể lạm dụng key.” | App có thể gọi operation được cấp ngoài mục đích | Key use authorization và signing/decrypt policy |
| “Đã mã hóa backup nên restore chắc thành công.” | Có thể mất key/quorum/provider, dữ liệu sai version | Restore exercise và key custody |
| “Encryption at rest bảo vệ dữ liệu trong memory.” | App đã decrypt để xử lý | Runtime/memory/process controls |
| “Key non-exportable tức không có bản sao.” | Backup/wrapped copies và policies có thể khác | Review toàn key topology |
| “Một checkbox encrypted=true đủ cho audit.” | Không thấy key use, scope, paths hoặc runtime evidence | CAE và multi-source tests |
| “Dùng cùng key mọi tenant giúp đơn giản hóa mà không ảnh hưởng risk.” | Blast radius và isolation có thể tăng | Chọn key granularity theo threat model |
| “Mọi thứ nên encrypt bằng cùng thuật toán.” | Password, signature, MAC và AEAD có mục tiêu khác | Chọn primitive theo thuộc tính cần bảo vệ |
| “Không có lỗi decrypt nghĩa integrity tốt.” | Có thể dùng mode không có authentication | Test tamper/AAD/tag và policy |
| “Thuật toán validated đồng nghĩa hệ thống đạt compliance.” | Validation có scope module/firmware/mode cụ thể | Cần controls vận hành, IAM và application evidence |
| “Xóa key là xóa mọi dữ liệu.” | Backup/replica/old key copies có thể tồn tại | Destruction/crypto erase có scope và kiểm chứng |
| “KMS outage thì fallback plaintext để không gián đoạn.” | Phá mục tiêu bảo mật | Degraded mode có chủ đích và phê duyệt |
| “Key rotation định kỳ là đủ.” | Compromise, policy change, revoke và recovery cũng quan trọng | Key lifecycle theo cả thời gian và sự kiện |
| “Test encrypt/decrypt unit pass nghĩa requirement đạt.” | Không kiểm storage/TLS/authorization/DR | Tách unit, integration, runtime và operating evidence |

## 27. Bài tập tình huống: đặc tả yêu cầu mã hóa cho SaaS nhiều tenant

Một nền tảng học doanh nghiệp triển khai trên cloud, xử lý:

- Hồ sơ học viên và lịch sử đào tạo.
- Kết quả thi và dữ liệu phản hồi nhạy cảm.
- Tài liệu khóa học public và restricted.
- JWT/access tokens.
- Export theo yêu cầu quản trị viên.
- Analytics, search, cache, logs và backup/DR.

Audit ban đầu phát hiện:

1. Database đã bật TDE, nhưng export job tạo file CSV plaintext.
2. Backup của một region chưa xác minh encryption key ownership.
3. Gateway dùng TLS, nhưng một internal service tắt hostname verification.
4. Một app service có quyền decrypt mọi tenant.
5. Key ký JWT lưu trong CI variable và được nhiều pipeline đọc.
6. Developer gọi AES-GCM với nonce tái sử dụng từ một counter reset mỗi lần restart.
7. Password được lưu bằng SHA-256 không có password-specific work factor.
8. KMS outage làm một batch job tự chuyển sang key hardcode.
9. Báo cáo security assurance chỉ có screenshot “encrypted=true”.
10. Chưa thử restore dữ liệu được mã hóa sau khi rotate KEK.

**Nhiệm vụ:**

1. Phân loại tài sản và vẽ DFD, bao gồm source và derived copies.
2. Xác định ít nhất **tám threat scenarios**; phân biệt confidentiality, integrity, authenticity, availability và key misuse.
3. Viết tối thiểu **mười requirements có thể kiểm chứng**: REST, TRANSIT, APP, KEY, TENANT, PASSWORD, SIGNING, BACKUP/DR.
4. Chỉ rõ từng requirement có **scope, normative behavior, failure behavior, owner, acceptance và test/evidence**.
5. Chọn phương án **envelope encryption** và giải thích cách chọn key granularity.
6. Thiết kế plan sửa nonce lifecycle, kiểm tra AAD/AEAD và xử lý decrypt failures.
7. Viết negative tests cho wrong key, wrong tenant, bad cert, KMS access denied, KMS outage và plaintext fallback.
8. Lập kế hoạch rotate signing key, KEK/DEK và kiểm chứng dữ liệu/chữ ký lịch sử.
9. Lập **Claim–Argument–Evidence** có giới hạn; chỉ ra vì sao screenshot encryption không đủ.
10. Đề xuất findings, owners, deadlines, remediation, deployment-linked retest và residual risk.

**Gợi ý đối chiếu:** vấn đề không chỉ là bật TDE; cần kiểm export, backup, key custody, permission, TLS peer validation và password hashing. AES-GCM nonce reuse là lỗi nghiêm trọng cần xử lý theo phạm vi ảnh hưởng. Hardcoded fallback phá yêu cầu fail-safe. Trường hợp chưa rõ key access hoặc chưa test restore phải được ghi **INCONCLUSIVE hoặc finding tương ứng**, không tự đánh PASS.

## 28. Checklist đánh giá requirement về mã hóa

- [ ] **Risk-based scope:** tài sản, phân loại, data states và mọi bản copy/path được xác định.
- [ ] **Threat model:** rủi ro disclosure, tamper, replay, misuse, key loss và outage được mô tả.
- [ ] **Objectives:** confidentiality, integrity, authenticity, availability và privacy được phân biệt.
- [ ] **Requirement IDs:** mỗi yêu cầu có ID, owner, version và risk reference.
- [ ] **Normative statement:** có hành vi bắt buộc/cấm rõ, không chỉ tên thuật toán.
- [ ] **Acceptance criteria:** có điều kiện pass/fail đo hoặc quan sát được.
- [ ] **Algorithm policy:** thuật toán, key size, mode và parameters tham chiếu crypto standard được duyệt.
- [ ] **At rest:** DB, volumes, objects, cache, search, export, backup và replicas được xét đúng scope.
- [ ] **In transit:** TLS trên mọi trust boundary nhạy cảm, không chỉ public edge.
- [ ] **Peer verification:** certificate chain/hostname/service identity và fail-safe được kiểm chứng.
- [ ] **In use:** plaintext memory, process boundary, logging và export paths có controls bổ sung.
- [ ] **AEAD:** mode/tag, nonce strategy, uniqueness, AAD và format version được xác định.
- [ ] **Anti-replay:** khi nghiệp vụ cần, protocol có sequence/freshness/idempotency độc lập với AEAD.
- [ ] **Password storage:** scheme chuyên dùng password hashing, salt, work factor, migration và recovery.
- [ ] **MAC/signature:** primitive phù hợp; key custody, verification và workflow authorization được tách rõ.
- [ ] **Key registry:** owner, purpose, scope, allowed operations, activation, rotation và expiry được quản lý.
- [ ] **Key custody:** không hardcode/key material lộ trong repo/image/log; KMS/HSM phù hợp risk.
- [ ] **Least privilege:** workloads/operators có quyền encrypt/decrypt/sign/unwrap theo nhiệm vụ.
- [ ] **Multi-tenant:** tenant/key boundaries và resource authorization được kiểm thử xuyên suốt API/DB/KMS.
- [ ] **KEK/DEK:** hiểu key hierarchy, rewrap/re-encrypt và impact khi rotate.
- [ ] **Backup/DR:** key copies, custodians, recovery procedure, restore và RTO/RPO đã được đánh giá.
- [ ] **Revocation/destruction:** old keys và encrypted copies được xử lý đúng policy/retention.
- [ ] **Crypto-agility:** algorithm/key format version, migration và legacy exceptions có kế hoạch.
- [ ] **Failure paths:** missing key, wrong tag, invalid cert, unsupported version và KMS outage không fail-open.
- [ ] **CI/CD:** code/config/IaC scans phát hiện insecure modes, hardcoded secrets và permissive key policies.
- [ ] **Runtime:** đối chiếu config thực tế với baseline/crypto policy trên đúng release/environment.
- [ ] **Testing:** có positive, negative, integration, lifecycle, failure-injection và DR evidence.
- [ ] **Traceability:** nối risk → requirement → control → test → evidence → finding.
- [ ] **Evidence quality:** provenance, completeness, integrity, freshness và limitations được kiểm.
- [ ] **Audit:** key/cert/config changes, authorized operations, policy exceptions được ghi và review.
- [ ] **Governance:** SoD, approvers, key owners, resource owners và risk decisions rõ.
- [ ] **Metrics:** denominator/scope rõ; tách compliant, noncompliant và unknown.
- [ ] **Remediation:** finding có root cause, severity, owner, deadline và retest ở đúng runtime.
- [ ] **Reassessment:** thêm data path, key, tenant, algorithm, provider, incident hoặc standard change kích hoạt review.
- [ ] **Assurance conclusion:** chỉ kết luận trong scope/period đã có evidence, không suy rộng thành “dữ liệu tuyệt đối an toàn”.

**Ghi nhớ:** Requirement về mã hóa là **một đặc tả bảo mật có thể chứng minh**, không phải khẩu hiệu “dùng AES, HTTPS và KMS”. Trong **SECURITY_SECURITY_ASSURANCE**, yêu cầu chất lượng phải làm rõ **đối tượng và tình huống rủi ro, thuộc tính cần bảo vệ, phạm vi dữ liệu và đường truyền, cấu hình/thuật toán theo policy, key lifecycle, lỗi và ngoại lệ, phương pháp kiểm thử và bằng chứng vận hành**. Chỉ khi chuỗi **risk → requirement → design/control → test/evidence → finding/remediation → reassessment** được duy trì trên đúng phiên bản và môi trường, tổ chức mới có căn cứ kết luận các mục tiêu mã hóa được đáp ứng trong phạm vi đã đánh giá.
