# Release risk: đánh giá rủi ro bảo mật của một bản phát hành

**Release risk (rủi ro phát hành)** là tập hợp những khả năng gây tác động bất lợi khi một **phiên bản sản phẩm hoặc gói thay đổi được đưa tới người dùng/môi trường đích**. Rủi ro có thể bắt nguồn từ lỗ hổng mã nguồn, sai cấu hình, dependency chưa tương thích, chuỗi cung ứng phần mềm, migration dữ liệu, khác biệt giữa môi trường thử nghiệm và production, kế hoạch rollout không phù hợp, hoặc nhiều thay đổi vốn an toàn riêng lẻ nhưng tương tác với nhau tạo ra lỗi.

Trong chương **Release assurance** thuộc module **SECURITY_SECURITY_ASSURANCE**, đánh giá release risk phải tạo ra **lập luận có bằng chứng** rằng bản phát hành đáp ứng các mục tiêu bảo mật trong phạm vi được duyệt. Kết quả không chỉ là câu “pipeline xanh” mà là một quyết định có căn cứ về khả năng **phát hành, hoãn, giới hạn rollout hoặc chấp nhận rủi ro có điều kiện**, kèm bằng chứng trước/sau triển khai và cơ chế theo dõi.

> **Câu hỏi chính:** Bản phát hành cụ thể này đưa những rủi ro nào vào môi trường đích, các security controls trọng yếu có còn hiệu lực không, những khoảng trống nào chưa được chứng minh và ai có thẩm quyền quyết định tiếp tục hay dừng?

**Phân biệt ngay từ đầu:** một change nhỏ có thể rất rủi ro; ngược lại, một release có nhiều change nhỏ có thể tạo **rủi ro cộng gộp** lớn do cùng tác động tới IAM, dữ liệu, API contract hoặc dependency. Release assurance phải xem xét **toàn bộ hành vi hệ thống sau khi các thay đổi được kết hợp**, không chỉ duyệt từng pull request.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Định nghĩa release risk và phân biệt **release risk**, **change risk**, **deployment risk**, **vulnerability risk** và **residual risk**.
2. Nhận diện rủi ro **tích lũy và tương tác** giữa nhiều thay đổi trong cùng một release.
3. Xác định release scope, release candidate, artifact, dependency, dữ liệu, môi trường và blast radius cần đánh giá.
4. Viết risk scenarios có **threat/failure mode, điều kiện, tài sản, tác động, bằng chứng và biện pháp kiểm soát**.
5. Thiết kế các cổng **release readiness / GO–NO-GO** dựa trên rủi ro và security requirements.
6. Hiểu cách sử dụng kết quả kiểm thử, SBOM, provenance, cấu hình, audit, threat modeling và nghiệm thu nghiệp vụ như **bằng chứng**, đồng thời biết giới hạn của từng nguồn.
7. Lựa chọn rollout/canary, feature flags, rollback/forward fix, giám sát và tiêu chí dừng phù hợp.
8. Quản lý security exceptions, deferred findings, risk ownership và phê duyệt rủi ro trước khi phát hành.
9. Ghi nhận kết quả **post-release verification** và quyết định đóng phát hành mà không suy rộng vượt quá bằng chứng.
10. Phân tích một release thanh toán có nhiều thay đổi và đưa ra quyết định phát hành có lý do.

---

## 2. Release risk khác Change risk như thế nào?

**Change risk** tập trung vào tác động khi chuyển một thành phần hay quy trình từ trạng thái A sang B. **Release risk** xem xét **gói thay đổi cuối cùng**, chuỗi build–test–approval–deployment và hành vi tích hợp của phiên bản được đưa ra thị trường hoặc production.

| Khía cạnh | Change risk | Release risk |
|---|---|---|
| Đối tượng | Một thay đổi hoặc nhóm công việc cụ thể | Một release candidate, tập thay đổi, artifact và kế hoạch phân phối |
| Câu hỏi | Thay đổi X có thể làm gì sai? | Khi X, Y, Z cùng được phát hành, hệ thống và khách hàng chịu rủi ro gì? |
| Phụ thuộc | Dependency trực tiếp của thay đổi | Tương thích liên dịch vụ, shared platform, feature flag, migration, release train |
| Dấu vết | Change request, PR, config diff | Release manifest, artifact/version, change set, SBOM, deployment plan |
| Kiểm thử | Unit/integration/security test cho phạm vi thay đổi | End-to-end, compatibility, regression, security assurance của toàn phiên bản |
| Quyết định | Cho phép hoặc từ chối thay đổi | GO/NO-GO, staged GO, hold, rollback, release acceptance |
| Hậu kiểm | Xác nhận change đã được triển khai an toàn | Xác minh đúng release đang chạy và hoạt động an toàn theo các tiêu chí của đợt phát hành |

Ví dụ, ba thay đổi đã được duyệt riêng:
- API chuyển cách xác thực token.
- Backend bổ sung một phiên bản thư viện token validator.
- Job xuất dữ liệu sử dụng service identity mới.

Mỗi thay đổi có test riêng. Nhưng nếu release đồng thời cập nhật IdP và thư viện backend, job cũ có thể không xác thực được token mới. Nếu đội chỉ nhìn vào các ticket “Approved”, họ sẽ bỏ qua **rủi ro tương thích của tổ hợp cuối cùng**.

### 2.1. Những thuật ngữ liên quan

- **Release candidate (RC):** tập artifact và cấu hình cụ thể được đề cử để phát hành; cần định danh đủ để kiểm tra và tái tạo.
- **Release baseline:** trạng thái được chấp nhận trước release, dùng để xác định thay đổi về security controls và hành vi.
- **Release manifest:** danh sách phiên bản, artifact, dependency, cấu hình và thay đổi có trong release.
- **Release readiness:** mức sẵn sàng của mã, test, vận hành, support, security, khôi phục và phê duyệt đối với phạm vi phát hành.
- **Deployment:** hành động đưa artifact/config tới môi trường; deployment thành công **không tự chứng minh** release được nghiệm thu bảo mật.
- **Feature exposure:** mức người dùng/tenant được phép sử dụng tính năng, có thể khác thời điểm artifact đã deploy.
- **Residual release risk:** các rủi ro còn lại sau kiểm soát, có owner và quyết định phù hợp.
- **Post-release verification:** kiểm tra có bằng chứng rằng bản đã triển khai đáp ứng tiêu chí về nghiệp vụ, bảo mật, quan sát và phục hồi.

## 3. Vì sao release risk không chỉ bằng tổng điểm rủi ro các change?

Một release có tính **hệ thống**: thay đổi này có thể làm mất hiệu lực assumption, test hoặc control của thay đổi kia.

### 3.1. Rủi ro tương tác

Ví dụ:

- Change A thay đổi quyền IAM tối thiểu để bảo vệ dữ liệu.
- Change B đổi secret path và quyền KMS.
- Change C triển khai worker đọc secret mới.

A và B có thể đúng riêng lẻ, nhưng tổ hợp có thể khiến worker không đọc được secret và gây gián đoạn. Nếu đội khắc phục gấp bằng policy wildcard, release lại có thể tạo rủi ro lộ secrets toàn account.

### 3.2. Rủi ro chung nguồn lỗi

Nhiều dịch vụ được nâng cùng base image hoặc thư viện. Nếu dependency dùng chung có lỗi, tác động có thể lan rộng dù từng service có ít thay đổi. Tương tự, một deployment template hoặc CI runner cấp quyền sai có thể ảnh hưởng tất cả artifact trong release train.

### 3.3. Rủi ro version hỗn hợp

Khi rolling deployment, dịch vụ cũ và mới cùng chạy:
- Producer mới gửi message schema mà consumer cũ không hiểu.
- Token mới được gateway mới chấp nhận nhưng worker cũ từ chối.
- App mới ghi dữ liệu dạng mới mà app cũ không thể rollback để đọc.
- Chính sách authorization được triển khai không đồng thời ở hai region.

Một release chỉ được thử ở trạng thái **100% phiên bản mới** có thể bỏ qua cửa sổ **mixed-version** vốn tồn tại khi rollout thật.

### 3.4. Rủi ro thời gian và lịch phát hành

Nhiều release có thể được triển khai gần nhau, cùng tác động shared database, IdP, KMS hoặc network. Tổng rủi ro phụ thuộc vào lịch thay đổi, tình trạng incident đang mở, mức tải và khả năng đội trực hỗ trợ. Đơn giản cộng các nhãn Low/Medium/High thường không cho biết điều này.

**Nguyên tắc:** đánh giá release phải xem xét **tính tương thích, dependency, thứ tự, đồng thời và blast radius**, không sử dụng tổng điểm cơ học nếu chưa có mô hình được kiểm định.

## 4. Xác định phạm vi release trước khi đánh giá

Nếu không biết chính xác **phiên bản nào và tài sản nào sẽ được phát hành**, mọi kết luận assurance đều thiếu căn cứ.

Một release scope tối thiểu cần:

| Thành phần | Cần xác định | Câu hỏi kiểm tra |
|---|---|---|
| Release identity | ID, tag/commit, artifact digest, ngày dự kiến | Có thể đối chiếu chính xác bản test với bản deploy? |
| Services | API, worker, UI, gateway, DB, cron, batch | Có dịch vụ/đường async bị bỏ sót? |
| Environments | Production, DR, staging, region, cloud account | Có khác biệt config so với nơi thử? |
| Changes included | PR, change requests, migrations, policy/config diff | Có thay đổi ngoài danh sách hoặc cherry-pick? |
| Dependencies | IdP, KMS, queue, cache, vendor API, library | Thư viện hoặc provider được dùng chung bởi ai? |
| Data | Loại dữ liệu, schema, encryption, retention | Có thay đổi processing, export hoặc backup? |
| Identities | Human/admin, service identity, support, break-glass | Quyền nào tăng/giảm, có path cấp quyền phụ? |
| Exposure | Người dùng/tenant, feature flag, traffic percentage | Bản mới được deploy có đồng nghĩa feature bật? |
| Timing | Release window, lịch change/incident, backup | Thời gian và nguồn lực ứng phó có đủ? |
| Recovery | Rollback, forward fix, backup, failover, owner | Đường khôi phục đã được thử đúng trạng thái dữ liệu? |

### 4.1. Release manifest là đầu vào quan trọng

Một manifest đơn giản có thể mô tả:

~~~yaml
release:
  id: REL-EXAMPLE-2026-014
  candidate: rc-3
  target_environment: production
  regions: [region-a, region-b]
  services:
    - name: checkout-api
      artifact_digest_ref: "restricted/artifacts/checkout-api/sha256"
    - name: payment-worker
      artifact_digest_ref: "restricted/artifacts/payment-worker/sha256"
    - name: identity-adapter
      artifact_digest_ref: "restricted/artifacts/identity-adapter/sha256"
  changes:
    - CHG-EXAMPLE-101
    - CHG-EXAMPLE-102
    - CHG-EXAMPLE-103
  schema_migrations:
    - MIG-EXAMPLE-08
  configuration_baseline_ref: "restricted/config/rel-014"
  feature_flags_ref: "restricted/flags/rel-014"
  dependency_inventory_ref: "restricted/dependencies/rel-014"
  security_requirements_ref: "restricted/requirements/checkout"
~~~

Đây là **mẫu minh họa**, chưa phải bằng chứng rằng artifact đã được xây dựng hoặc triển khai. Cần có build provenance, deployment record và kiểm tra runtime. Nếu thay candidate từ rc-3 sang rc-4, phải xem xét **những kiểm thử và phê duyệt nào còn hợp lệ**. Không tự sử dụng test của rc-3 để kết luận cho rc-4 khi có thay đổi ảnh hưởng đến phạm vi đã kiểm thử.

## 5. Phân nhóm rủi ro của release

Release security assurance thường cần xem xét nhiều thuộc tính cùng lúc.

| Nhóm rủi ro | Câu hỏi | Ví dụ |
|---|---|---|
| **Confidentiality** | Release tạo đường đọc/xuất dữ liệu trái quyền? | Endpoint export bỏ kiểm tra tenant |
| **Integrity** | Có thể ghi dữ liệu sai, mất thứ tự hay lặp giao dịch? | Migration mapping sai trạng thái thanh toán |
| **Availability** | Release có thể làm dịch vụ không khả dụng hoặc chậm quá mức? | Token rotation làm batch jobs thất bại |
| **Authentication / authorization** | Role, policy, token, session có thay đổi? | Gateway tin header tenant do client gửi |
| **Cryptographic protection** | Key, secret, mã hóa, ký artifact có bị ảnh hưởng? | KMS permission khiến backup không giải mã được |
| **Auditability / detection** | Logging, tracing, alert có còn bao phủ sự kiện bắt buộc? | Event format mới không được SIEM parse |
| **Privacy / compliance** | Dữ liệu được dùng, lưu, truyền hay chia sẻ khác trước? | Bổ sung analytics gửi PII ngoài phạm vi được duyệt |
| **Supply chain** | Artifact, dependency, build pipeline có đáng tin? | Build từ package chưa được xác minh |
| **Resilience / recovery** | Failover, restore, rollback và runbook còn phù hợp? | Release đổi schema nhưng DR site vẫn version cũ |
| **Operational governance** | Owner, approval, exception, support có đủ? | Rủi ro cao chưa có quyết định chấp nhận |
| **Third-party dependency** | Nhà cung cấp thay API/SLA/trust boundary? | Payment provider bỏ cơ chế xác thực cũ |

Một lỗi có thể thuộc nhiều nhóm. Ví dụ sai cấu hình KMS vừa làm giảm availability vừa làm mất khả năng phục hồi dữ liệu. Đánh giá nên ghi **các hậu quả và control liên quan**, không cố ép mọi thứ về một nhãn.

## 6. Phân tích rủi ro theo kịch bản

Một nhãn “Release High risk” thiếu lý do cụ thể. Hãy viết **risk scenario** có thể chuyển thành phép thử.

**Mẫu:**

> Khi release R triển khai thay đổi X trong ngữ cảnh C, sự kiện/hành vi Y có thể xảy ra do dependency hoặc control gap Z, gây tác động I tới asset/business process A. Mức rủi ro được đánh giá theo phương pháp M và được xử lý bằng các biện pháp T, cần evidence E.

Ví dụ:

> Khi release thay token signing key và cập nhật gateway, batch workers dùng cache khóa cũ có thể từ chối token mới trong cửa sổ mixed-version, khiến đơn hàng bị tồn đọng. Biện pháp giảm thiểu gồm giai đoạn chấp nhận khóa cũ/mới có giới hạn, thử worker compatibility, cảnh báo hàng đợi và kế hoạch rollback được kiểm chứng.

### 6.1. Kịch bản có cả yếu tố đối kháng lẫn sai sót

- **Threat-driven:** attacker lợi dụng API mới thiếu authorization để đọc hồ sơ tenant khác.
- **Failure-driven:** schema migration có bug khiến đơn hàng bị sai trạng thái.
- **Misconfiguration-driven:** CI template deploy làm network policy rộng hơn yêu cầu.
- **Dependency-driven:** provider đổi chứng chỉ, service không xác minh được TLS.
- **Operational-driven:** alert rule cũ không hiểu event format sau release.
- **Recovery-driven:** rollback app nhưng database đã chạy migration không tương thích.

Mỗi kịch bản phải có **owner, impact, likelihood hoặc mức phơi nhiễm theo quy tắc nội bộ, biện pháp kiểm soát, điều kiện kiểm chứng và rủi ro còn lại**.

### 6.2. Risk matrix minh họa

| Kịch bản | Inherent risk (minh họa) | Biện pháp | Bằng chứng để đánh giá residual risk |
|---|---|---|---|
| Cross-tenant export | Critical | Object-level authorization, negative tests | Test theo role/tenant/route trên đúng artifact |
| Worker không nhận token mới | High | Compatibility window, canary | Kết quả mixed-version và queue monitoring |
| Migration ghi sai dữ liệu | Critical | Rehearsal, reconciliation, rollback strategy | Kết quả đối chiếu nghiệp vụ và dữ liệu |
| Audit log mất một nguồn | High | End-to-end event tests, ingestion alerts | Truy vết event từ nguồn tới SIEM |
| Dependency có CVE chưa xử lý | Tùy asset/exposure | Update hoặc exception phù hợp | SBOM/version, triage, retest và risk decision |

Nhãn và mức trên chỉ **minh họa**, không phải định nghĩa severity bắt buộc. Không mặc định “Critical” có một SLA cụ thể nếu chưa có tiêu chí nội bộ hoặc nghĩa vụ áp dụng.

## 7. Đánh giá rủi ro tích lũy và tương quan

Đây là điểm quan trọng nhất phân biệt release-level review với chỉ duyệt từng thay đổi.

### 7.1. Xây bản đồ phụ thuộc

~~~mermaid
flowchart TD
    R["Release candidate R"] --> A["API authz change"]
    R --> B["IdP/token rotation"]
    R --> C["Database migration"]
    R --> D["Logging pipeline update"]
    A --> E["Gateway + service identities"]
    B --> E
    B --> F["Batch workers + DR site"]
    C --> G["Checkout API + payment worker"]
    D --> H["SIEM parser + security alerts"]
    E --> I["Cross-service integration tests"]
    F --> I
    G --> I
    H --> I
~~~

Release-level assurance không chỉ hỏi bốn thay đổi có test riêng hay không; cần xem **đường tương tác** giữa chúng:

1. Đổi IdP có làm session hoặc workload identity hoạt động khác?
2. API authz mới có tin claim trong token sau rotation?
3. Payment worker có xử lý schema mới khi vẫn dùng token cũ?
4. Nếu rollback API, database đã được migration có tương thích không?
5. Logging mới có bắt được lỗi phát sinh khi các service đang chạy hai phiên bản?

### 7.2. Common-mode failure

Một dependency dùng chung như KMS, IdP, DNS, storage, feature flag service hoặc CI/CD có thể là điểm lỗi chung cho nhiều thành phần. Cùng một thay đổi nhỏ trên dependency đó làm blast radius tăng mạnh.

Không nên xem nhiều bài test từ **cùng một source lỗi** là nhiều nguồn xác nhận độc lập. Nếu mọi test chạy với mock IdP giống nhau, việc tất cả đều PASS không chứng minh tương tác với IdP production.

### 7.3. Rủi ro chồng thời gian

Một release có thể được triển khai khi:

- Incident khác đang diễn ra.
- Một bản vá cấp bách chưa hoàn tất.
- Hệ thống đang failover hoặc DR drill.
- Một nhà cung cấp có lịch bảo trì.
- Đội vận hành đã có thay đổi lớn trên shared database.

Nếu cửa sổ phát hành khiến khả năng phát hiện/rollback giảm, cần phản ánh trong quyết định rủi ro, kể cả mã nguồn không thay đổi.

## 8. Baseline và release delta: biết điều gì thực sự thay đổi

Risk assessment tốt so sánh **trạng thái được chấp nhận trước release** với trạng thái sẽ tồn tại sau release.

| Baseline trước | Release delta | Điều cần chứng minh |
|---|---|---|
| API kiểm tra tenant ID tại backend | Gateway chuyển tenant claim từ header | Header có được xác minh, backend có bypass? |
| Secret read chỉ trên một resource | Role được cập nhật cho secret mới | Không tạo wildcard privilege |
| Database schema v1 | Schema v2 và job migration | Không mất/nhân đôi/sai dữ liệu |
| Audit event format A | Format B | SIEM và alert parser xử lý B đúng |
| DR site dùng image X | Production dùng image Y | Compatibility của failover/rollback |
| Feature chưa public | Feature flag bật cho nhóm khách hàng | Đúng tenant/role, đường truy cập và dữ liệu |

Một phương pháp **delta threat modeling** hữu ích: xác định trust boundary, luồng dữ liệu, role, secret, endpoint, dependency và control nào mới hoặc thay đổi; rồi biến mỗi nguy cơ đáng kể thành security test hoặc điều kiện release gate.

Nếu release thêm đường API mới mà threat model và inventory vẫn dựa trên bản cũ, **evidence cũ không đủ đại diện** cho claim “mọi endpoint được kiểm soát”.

## 9. Release security gates: cổng nào phải đạt trước GO?

**Release gate** là điều kiện cần đáp ứng trước khi cho phép một release chuyển giai đoạn. Gate cần được xác định từ rủi ro và tiêu chí đã phê duyệt, không đơn thuần là số lượng checkbox.

| Gate | Câu hỏi kiểm tra | Evidence dự kiến |
|---|---|---|
| **G1 — Scope completeness** | Release manifest, asset, dependency, data và version đủ? | Manifest, SBOM, inventory, change diff |
| **G2 — Threat/security impact** | Các đường attack và security controls bị ảnh hưởng được xét? | Delta threat model, control mapping |
| **G3 — Trusted build** | Artifact được xây từ nguồn và pipeline đúng, không bị thay thế? | Build provenance, artifact digest, signing/attestations nếu áp dụng |
| **G4 — Security testing** | Positive/negative, vulnerability và regression tests phù hợp rủi ro đạt? | Test report kèm run ID, scope, version |
| **G5 — Compatibility** | Services/clients và mixed-version window hoạt động? | Contract tests, integration, consumer/provider checks |
| **G6 — Data/change integrity** | Migration, key, secret và data integrity được bảo vệ? | Rehearsal, reconciliation, KMS/restore test |
| **G7 — Operability** | Monitoring, alerts, incident/rollback runbook, người trực sẵn sàng? | Synthetic checks, drill logs, support readiness |
| **G8 — Findings/exception** | Finding còn mở và ngoại lệ có quyết định phù hợp? | Risk register, CAP, approval, expiry |
| **G9 — Release authorization** | Người có thẩm quyền GO/NO-GO với phạm vi và rủi ro còn lại? | Approval record, conditions, decision rationale |
| **G10 — Post-release plan** | Có kế hoạch kiểm chứng, guardrails và trigger dừng/rollback? | Monitoring plan, acceptance criteria, reviewer |

Các cổng có thể tự động hóa một phần, nhưng **một gate quan trọng bị FAIL không nên được “bù điểm” bằng nhiều test không liên quan**. Ví dụ 500 unit tests PASS không giải quyết việc không thể restore database sau migration.

### 9.1. Gate không nhất thiết đồng nhất cho mọi release

Một release chỉ sửa giao diện tĩnh có thể không cần migration rehearsal sâu. Một release đổi KMS root-of-trust hoặc quyền production có thể yêu cầu review độc lập và thử recovery trước khi GO.

Mức kiểm soát cần tương xứng với:
- Tài sản và dữ liệu chịu tác động.
- Mức thay đổi đối với trust boundary, quyền, crypto và dependency.
- Khả năng đảo ngược, phát hiện lỗi và phục hồi.
- Mức phơi nhiễm, số lượng khách hàng, region và yêu cầu bên ngoài.
- Độ tin cậy của test, inventory và môi trường thử nghiệm.

**Không áp dụng một score đơn giản để tự động miễn kiểm thử quan trọng** khi risk scenario đã có tác động lớn.

## 10. Bằng chứng release có giá trị khi gắn đúng artifact

Một failure phổ biến là **test một phiên bản và deploy một phiên bản khác**. Vì vậy assurance cần theo dấu toàn bộ chuỗi:

~~~text
Approved requirements / threat model
                ↓
Source revision + dependencies
                ↓
Trusted build / artifact identity
                ↓
Release candidate selected
                ↓
Tests against that candidate
                ↓
Review + GO decision for candidate
                ↓
Deployment of the same identified artifact
                ↓
Runtime version/config verification
                ↓
Post-release tests and monitoring
~~~

### 10.1. Cần xác minh điều gì?

- Commit/revision hoặc source provenance có được phép sử dụng?
- Dependency resolution có được khóa/ghi nhận đủ để biết artifact chứa gì?
- Build có chạy trên đường kiểm soát được phê duyệt không?
- Artifact có định danh ổn định (digest/checksum) và không bị thay sau khi test không?
- Nếu dùng ký số hoặc attestation, khóa và policy xác thực có đúng và còn hiệu lực không?
- Image được deploy trên đúng cluster/region/tenant? Có sidecar, init container hoặc job ngoài manifest không?
- Feature flags/config/secrets tại runtime có đúng baseline đã đánh giá?
- Canary và rollback artifact có được nhận diện, không quay lại bản rủi ro đã bị cấm?

**Một chữ ký số hợp lệ không chứng minh phần mềm không có lỗi.** Nó giúp xác minh các thuộc tính như nguồn/kết quả ký theo chính sách, còn tính đúng của code và security requirements cần những bằng chứng khác.

### 10.2. Software Bill of Materials (SBOM)

SBOM hoặc danh mục thành phần có thể giúp nhận diện dependency và phục vụ đánh giá lỗ hổng. Tuy vậy SBOM **không tự bảo đảm**:
- Nó có đầy đủ mọi dependency transitive/runtime không.
- Những phiên bản ghi trong SBOM chính là phiên bản đang chạy.
- Không có lỗ hổng chưa công bố.
- Các security controls cấp ứng dụng đều đúng.

Cần gắn SBOM với artifact cụ thể và kiểm tra provenance, phạm vi và phương pháp tạo. Khi có finding quan trọng, sử dụng risk triage để đánh giá khả năng khai thác và tác động trong ngữ cảnh thay vì chỉ đếm CVE.

## 11. Kiểm thử release: lớp kiểm tra nào hỗ trợ mục tiêu nào?

Một bộ test phù hợp bao phủ cả **chức năng, bảo mật, tương thích và vận hành**.

| Lớp | Mục tiêu | Giới hạn điển hình |
|---|---|---|
| Unit tests | Xác minh logic cục bộ và edge cases | Không mô phỏng đầy đủ IAM/network và dependency |
| Integration tests | Tương tác giữa các module/service | Có thể dùng mock thiếu hành vi production |
| Contract tests | Khả năng tương thích API/event giữa các consumer/provider | Không chứng minh tính an toàn của mọi luồng dữ liệu |
| Security regression | Bảo vệ các yêu cầu đã từng có finding | Chỉ bao phủ những lỗi/kịch bản đã mã hóa thành test |
| SAST/dependency/config scans | Tìm sai sót theo rule và thành phần biết trước | Không xác minh toàn bộ logic nghiệp vụ |
| DAST/authorized security testing | Kiểm tra hành vi bảo mật ở hệ thống chạy | Phạm vi và quyền test có thể giới hạn |
| E2E business tests | Nghiệp vụ chính hoạt động sau tích hợp | Có thể không phát hiện lỗ hổng bảo mật ẩn |
| Migration/data integrity | Kết quả chuyển dữ liệu đúng và nhất quán | Cần dữ liệu đại diện, test idempotency và recovery |
| Performance/load tests | Đánh giá dung lượng/độ trễ trong tải giả lập | Tải thật hoặc tương quan sự cố có thể khác |
| DR/rollback drills | Có thể phục hồi trong điều kiện đã thử | Không bao phủ mọi loại thảm họa và thời điểm |
| Production-safe checks | Xác minh đúng artifact/config và đường nghiệp vụ thực | Không nên chạy payload gây hại hoặc phá dữ liệu |

### 11.1. Positive và negative security tests

Nếu release thay cơ chế authorization cho export, cần thử:

- **Positive:** user có quyền xuất đúng dữ liệu của tenant mình.
- **Negative:** user tenant A không xem, tải hoặc tham chiếu được kết quả của tenant B.
- **Variant:** role hỗ trợ, async job, download link, phiên hết hạn, path thay thế, cache.
- **Regression:** chức năng hợp lệ và logging vẫn hoạt động.

Nếu bản sửa chỉ chặn tất cả request, negative tests có thể PASS nhưng nghiệp vụ FAIL. Một kết luận bảo mật đúng phải đặt cạnh **availability và integrity**, không đánh đổi bằng cách làm hỏng dịch vụ mà không có quyết định phù hợp.

### 11.2. Test đúng candidate và môi trường

Test trên staging chỉ hỗ trợ kết luận về production khi có bằng chứng đủ rằng artifact và cấu hình liên quan tương đương. Nếu staging dùng IdP mock, khóa riêng, không có role support hoặc không chạy job export, nên ghi **limitations** và bổ sung production-safe checks.

Khi candidate được thay, cần **impact analysis** xem test nào phải chạy lại; không có quy tắc “mọi test luôn chạy lại” cho mọi thay đổi, nhưng các test liên quan đến delta và gate bắt buộc không được bỏ qua.

## 12. Release readiness vượt ra ngoài chất lượng mã

Có trường hợp mã đúng nhưng hệ thống chưa sẵn sàng phát hành.

### 12.1. Người và quy trình vận hành

- Có người chịu trách nhiệm release, approval và người ra quyết định dừng.
- Đội trực vận hành và security có thông tin phạm vi, thay đổi, rủi ro và giờ rollout.
- Runbook thao tác, phản ứng lỗi, rollback/forward fix có version và người sở hữu.
- Quy trình incident và liên hệ nhà cung cấp sẵn sàng nếu dependency gặp lỗi.
- Support và business owner hiểu tính năng mới, điều kiện kích hoạt và trường hợp dừng.

### 12.2. Giám sát và kiểm thử hậu triển khai

- Đã có baseline của latency, 5xx, throughput, backlog và các giao dịch trọng yếu.
- Có **security signals**: authn/authz denials, privilege changes, secret access, audit logging coverage, config drift.
- Có synthetic check hoặc sự kiện thử end-to-end để xác nhận log vào kho được chỉ định.
- Có khả năng phân biệt bản canary và bản cũ khi đo metric.
- Đã thống nhất cửa sổ quan sát, điều kiện dừng, owner escalation và người xác nhận.

### 12.3. Trạng thái rủi ro và finding

Release không nhất thiết cần **zero findings**; nhưng phải biết:
- Finding nào là **blocking** theo chính sách/risk decision.
- Finding nào đã retest verified fixed, ở đúng artifact.
- Finding nào được hoãn xử lý, với căn cứ, thời hạn, bù trừ và người duyệt.
- Finding nào còn thiếu evidence và không thể dùng nhãn “accepted” để biến thành PASS.
- Các nghĩa vụ pháp lý/hợp đồng có cho phép chấp nhận sai khác hay không.

## 13. GO, NO-GO và GO có điều kiện

Quyết định release là **quyết định quản trị dựa trên bằng chứng**, không phải thao tác ký tên thay cho đánh giá.

| Kết quả | Khi nào có thể áp dụng | Điều kiện ghi nhận |
|---|---|---|
| **GO** | Các gate bắt buộc đạt, residual risk trong mức được chấp nhận | Đúng candidate, scope, approval, monitoring và rollback |
| **CONDITIONAL / LIMITED GO** | Một phần rủi ro được quản lý bằng hạn chế exposure, control bù trừ hoặc điều kiện đã phê duyệt | Định nghĩa tenant/region/percentage, thời hạn, stop conditions |
| **HOLD / PENDING EVIDENCE** | Chưa đủ evidence cho một gate trọng yếu | Nêu nguồn cần thu, owner, hạn và điều kiện đánh giá lại |
| **NO-GO** | Có blocker, phản chứng hoặc rủi ro không được chấp nhận | Ghi lý do, evidence, CAP, tiêu chí để xét lại |
| **EMERGENCY GO** | Có lý do khẩn cấp được quy trình cho phép, đánh giá nhanh và kiểm soát bổ sung | Quyền hạn, giới hạn, log, post-release review và xử lý sai khác |

**Phê duyệt GO có điều kiện** không tự động cho phép bật toàn bộ feature hay triển khai mọi region. Điều kiện phải có thể thực thi/giám sát, ví dụ chỉ bật cho tenant nội bộ hoặc canary 1% trong khoảng thời gian được chốt. Phần trăm chỉ là ví dụ, không phải ngưỡng đề xuất chung.

### 13.1. Ai ra quyết định?

Trong release có rủi ro cao, trách nhiệm thường được phân tách:

| Vai trò | Trách nhiệm |
|---|---|
| Release manager | Phối hợp manifest, lịch, checkpoints và ghi quyết định |
| Service/business owner | Xác định tác động nghiệp vụ và chịu trách nhiệm rủi ro trong thẩm quyền |
| Security assurance / AppSec | Kiểm tra security gates, bằng chứng và các lỗ hổng lập luận |
| Platform/SRE | Kiểm tra deploy, rollout, observability, rollback và DR |
| QA/Test owner | Xác nhận phạm vi/kết quả test và regression |
| Data owner/DBA | Đánh giá migration, integrity, privacy và restore |
| Compliance/GRC | Kiểm tra chính sách, nghĩa vụ, findings và exceptions |
| Authorized risk authority | Phê duyệt rủi ro vượt ngưỡng hoặc ngoại lệ theo quy định |

Một chữ ký từ đội kỹ thuật không tự thay thế quyết định chấp nhận rủi ro nghiệp vụ khi mức tác động vượt thẩm quyền của đội đó. Cần lưu **ai quyết định gì, dựa trên tập evidence nào và với điều kiện nào**.

## 14. Chiến lược rollout và exposure control

Release risk có thể được giảm nhờ **giới hạn độ phơi nhiễm và khả năng dừng**.

| Chiến lược | Lợi ích | Rủi ro cần kiểm tra |
|---|---|---|
| **Canary** | Tiếp xúc với lượng traffic/instance giới hạn | Canary có đại diện cho role, tenant và đường rủi ro không? |
| **Blue–green** | Chuyển đổi và quay lại tương đối nhanh ở tầng app | Cả hai cùng dùng database đã migration thì rollback chưa chắc an toàn |
| **Rolling deployment** | Giảm downtime | Mixed-version protocol/schema, cache, session, queue |
| **Feature flags** | Tách deploy khỏi kích hoạt tính năng | Sai targeting có thể mở feature cho sai tenant/role |
| **Region/account stages** | Giảm blast radius theo vùng | DR và shared dependencies có thể vẫn bị tác động chung |
| **Shadow/dry-run** | So kết quả trước khi áp dụng | Không được gây side effect hoặc lộ dữ liệu thật |
| **Limited audience** | Đánh giá với nhóm người dùng được phê duyệt | Bảo vệ dữ liệu/thẩm quyền của nhóm thử, tránh suy rộng |

### 14.1. Canary phải đo đúng rủi ro

Nếu rủi ro chính là **cross-tenant data exposure**, chỉ theo dõi HTTP 500 và latency không đủ. Cần synthetic negative tests, anomaly detection và audit logs phù hợp. Nếu rủi ro là mất giao dịch, phải đo reconciliation, backlog và duplicate processing.

### 14.2. Feature flag không thay security boundary

Một flag tắt UI có thể không ngăn một endpoint vẫn public. Một flag được gán theo tenant có thể lỗi ở shared cache. Security control phải được cưỡng chế **ở đúng trust boundary**, không mặc định feature visibility là authorization.

### 14.3. Tránh “canary giả”

Đôi khi canary chỉ chạy ở region ít tải, không có job nền hoặc dùng dữ liệu giả không đại diện. Kết quả tốt của canary này chưa đủ cho GO toàn bộ nếu đường có rủi ro không được thử. Cần ghi rõ **canary population** và suy luận được phép từ nó.

## 15. Rollback, forward fix và rủi ro không thể đảo ngược

Một release có kế hoạch rollback chưa chắc có **rollback an toàn**. Các tình huống cần phân tích:

- Database schema đã được thay và code cũ không còn đọc được.
- Key cũ bị thu hồi; rollback cần key đó để xác minh token hoặc giải mã backup.
- Message/event đã được phát ra cho đối tác, không thể “thu hồi” trạng thái bên ngoài.
- Worker bản mới xử lý một phần giao dịch, bản cũ xử lý lại gây duplicate.
- Cấu hình security bản cũ yếu hơn; rollback đưa lỗ hổng đã vá trở lại.
- Data migration làm mất thông tin nếu đảo ngược mà không có backup/reconciliation.

### 15.1. Một kế hoạch phục hồi release cần

1. **Trigger** rõ: metric, security finding, integrity check hoặc điều kiện nghiệp vụ không đạt.
2. **Authority**: ai được dừng rollout, rollback hay forward fix.
3. **Thời điểm quyết định**: tránh đợi quá lâu khiến dữ liệu không còn đảo ngược.
4. **Artifacts và configs** được lưu: bản cũ/mới có provenance, không dùng image không xác minh.
5. **Data strategy**: backup/restore point, compatibility, idempotency, reconciliation.
6. **Security consequences**: credential/session, IAM, encryption, logs và control nào bị ảnh hưởng khi rollback.
7. **Communication và evidence**: ai được thông báo, ghi nhận gì.
8. **Validation sau khôi phục**: giao dịch, dữ liệu, log, quyền và khả năng phục hồi.

**Rollback code thành công không có nghĩa dữ liệu và security posture đã trở lại baseline.** Đối với migration không đảo ngược, có thể cần **forward fix** thay vì rollback; phương án này phải được dự tính trước, có test và quyền quyết định.

## 16. Kế hoạch giám sát và điều kiện dừng phát hành

Release assurance phải có **guardrails** dựa trên failure scenarios đã xác định, không dùng duy nhất dashboard availability.

| Tín hiệu | Rủi ro liên quan | Cách kiểm chứng |
|---|---|---|
| Error rate / latency | Gián đoạn hoặc giảm chất lượng | Baseline + threshold trong cửa sổ đã duyệt |
| Queue backlog / duplicate events | Sai xử lý async/integrity | Counts, idempotency checks, reconciliation |
| Authorization denies và test canary | Phân quyền sai hoặc bypass | Positive/negative checks, log correlation |
| Privileged changes | IAM/secret/policy drift | Cloud audit trail và alert |
| Security log ingestion | Mù giám sát sau đổi event format | Synthetic event source-to-SIEM |
| Data reconciliation | Migration làm sai/mất dữ liệu | Count/hash/semantic business checks |
| Payment/order completion | Sai nghiệp vụ dù HTTP 200 | Giao dịch thử, financial reconciliation |
| KMS/key errors | Token/secret/backup không dùng được | Verify/decrypt checks được phép |
| DR/readiness status | Không còn đường phục hồi an toàn | Runbook checks, targeted restoration exercise |

**Ngưỡng và cửa sổ quan sát phải được phê duyệt cho hệ thống cụ thể.** Ví dụ tỷ lệ 5xx tăng 1% có thể quan trọng ở dịch vụ thanh toán nhưng bình thường với một API dùng cho thử nghiệm. Không có ngưỡng tiêu chuẩn chung cho mọi release.

### 16.1. Stop condition và action

~~~text
IF unauthorized cross-tenant data read is observed:
  - Stop exposure rollout immediately under approved incident procedure.
  - Isolate affected feature/path using a safe control.
  - Preserve evidence and assess data impact.
  - Escalate to security incident / risk owner.
  - Do not declare release accepted.

IF queue backlog crosses approved threshold:
  - Pause progression; verify business transaction integrity.
  - Choose rollback or forward fix according to data compatibility.
  - Validate recovery, not just HTTP health.

IF logging source disappears:
  - Treat security telemetry coverage as a gate issue.
  - Determine lost period and operational impact.
  - Restore/verify pipeline; document historical evidence gap.
~~~

Đây là **logic minh họa**; hành động production thực tế phải theo runbook đã được phép, chú trọng tránh làm gián đoạn hoặc mất dữ liệu ngoài dự kiến.

## 17. Post-release verification: release đã thực sự đạt chưa?

Sau deployment, phải phân biệt:

- **Deployed:** artifact/config đã xuất hiện ở môi trường đích.
- **Activated:** tính năng/luồng mới đã được bật cho một nhóm người dùng.
- **Technically healthy:** các chỉ số kỹ thuật theo criteria đạt.
- **Security verified:** security controls và phép thử trong scope đạt theo bằng chứng.
- **Business accepted:** luồng nghiệp vụ quan trọng đáp ứng tiêu chí nghiệm thu.
- **Fully released:** rollout/exposure đạt phạm vi kế hoạch sau khi các điều kiện bắt buộc hoàn thành.
- **Closed:** hồ sơ, reviewer, residual risk, monitoring/follow-up được cập nhật theo quy trình.

Một bản release có thể đã deploy xong nhưng **chưa được phép bật toàn bộ feature**. Nếu chưa có security verification cho mọi region, không nên báo trạng thái “security assurance complete”.

### 17.1. Kiểm tra sau triển khai

- Đối chiếu runtime artifact digests của mọi service/region.
- Kiểm tra feature flags, IAM roles, KMS policies, network và cấu hình của bản phát hành.
- Chạy synthetic nghiệp vụ và security negative tests trong phạm vi an toàn.
- Đối chiếu dữ liệu migration, queue và event processing.
- Thử truy vết một audit event từ nguồn đến SIEM và xác nhận alert phù hợp.
- Kiểm tra canary/rollout guardrails và bất thường tài sản ngoài scope.
- Kiểm tra hệ thống standby/DR hoặc dependency được coi là quan trọng.
- Ghi residual risk, phát hiện mới, CAP và reviewer decision.

**Một screenshot dashboard xanh cuối ngày không đủ chứng minh mọi control hoạt động trong cả cửa sổ rollout.** Khi cần kết luận về thời kỳ, dùng log/telemetry có nguồn, thời gian và độ bao phủ rõ.

## 18. Quản lý exceptions và deferred findings trong release

Một release có thể phải đi cùng những vấn đề chưa giải quyết. Không nhất thiết cứ có finding là NO-GO, nhưng xử lý phải có cấu trúc.

| Trạng thái | Hành động với release |
|---|---|
| Finding verified fixed trên đúng RC | Đánh giá bằng chứng, xác nhận không có regression |
| Finding còn mở và là blocking theo tiêu chí | Không GO nếu chưa có quyết định đúng thẩm quyền hoặc phương án xử lý hợp lệ |
| Finding đã có compensating control | Kiểm tra hiệu lực control và residual risk, không mặc định PASS |
| Finding risk accepted có hạn | Xác minh scope, người duyệt, điều kiện, expiry và nghĩa vụ liên quan |
| Finding thiếu evidence | Ghi NOT DEMONSTRATED, đánh giá khả năng blocker |
| Finding phát hiện trong canary | Tạm dừng/giới hạn rollout, phân loại tác động, mở CAP hoặc incident |
| Finding đã đóng nhưng tái xuất hiện | Reopen hoặc tạo liên kết theo quy trình; đánh giá lại release |

**Security exception** là quyết định quản trị phạm vi sai khác tạm thời. Nó không đồng nghĩa control đáp ứng; cũng không thể tự miễn nghĩa vụ pháp luật/hợp đồng mà người phê duyệt không có quyền thay đổi.

Một bảng risk acceptance phù hợp nên có mã, đối tượng, finding/control, phạm vi asset/version/tenant, lý do, residual risk, compensating controls, người duyệt, thời hạn và trigger thu hồi. Nếu release thêm asset hoặc mở exposure rộng hơn, phải xem xét liệu ngoại lệ còn đủ phạm vi không.

## 19. Minh họa end-to-end: release nền tảng checkout

Tất cả thông tin và số liệu trong ví dụ dưới đây **giả định để học**.

### 19.1. Release candidate

Nền tảng thanh toán chuẩn bị phát hành **REL-014** trong production trên hai region. Gói gồm:

1. Checkout API thêm endpoint xuất báo cáo hóa đơn.
2. IdP luân chuyển khóa ký token.
3. Payment worker sử dụng schema sự kiện mới.
4. Database migration thêm trạng thái hoàn tiền.
5. Logging pipeline đổi format audit event.
6. Feature flag kích hoạt chức năng hoàn tiền cho một nhóm tenant.

Mỗi thay đổi riêng lẻ đã có owner, code review và test cơ bản. Nhưng release-level review phải xác minh **mối tương quan**.

### 19.2. Đánh giá risk scenarios

| ID | Kịch bản | Tác động | Evidence cần có |
|---|---|---|---|
| R1 | Endpoint xuất báo cáo thiếu tenant-level authz | Lộ dữ liệu tài chính giữa các tenant | Authz negative tests theo tenant, role, export/download |
| R2 | Token mới bị worker cũ từ chối khi rolling deploy | Giao dịch/hoàn tiền bị tồn đọng | Mixed-version tests, JWKS/key rotation plan, queue metrics |
| R3 | Migration mapping sai trạng thái hoàn tiền | Sai đối soát và integrity | Rehearsal trên dữ liệu đại diện, semantic reconciliation |
| R4 | SIEM không đọc format event mới | Mất khả năng phát hiện sự kiện quan trọng | Synthetic event và alert source-to-SIEM |
| R5 | Feature flag nhầm tenant ngoài chương trình thử | Tăng exposure trái kế hoạch | Flag targeting tests, tenant inventory, runtime checks |
| R6 | Rollback API nhưng schema mới không tương thích | Mất khả năng xử lý hoặc dữ liệu sai | Compatibility plan, migration rollback/forward fix rehearsal |
| R7 | DR site còn key/worker/config cũ | Không failover an toàn | DR key/worker compatibility test |

Các risk scenario này không thể giải quyết bằng cách cộng tổng số unit tests PASS.

### 19.3. Kết quả kiểm tra vòng đầu

Giả sử có bằng chứng:

- SAST/dependency scan hoàn tất, không có finding blocking theo các rule đã chọn.
- Unit tests của sáu thay đổi riêng đều PASS.
- Authz test của endpoint export mới chỉ chạy cho user thông thường, **chưa thử support role và signed download URL**.
- Mixed-version test phát hiện worker cũ từ chối token mới.
- Migration rehearsal tìm thấy 0,3% bản ghi thuộc trạng thái hoàn tiền hiếm bị mapping sai.
- SIEM ingest event mới nhưng alert rule cho hành động privileged refund chưa được kiểm tra.
- DR site chưa được thử với bộ signing keys mới.

**Kết luận:** Có ít nhất hai phản chứng trực tiếp (worker compatibility và integrity migration), nhiều security evidence gaps. Vì vậy **NO-GO** đối với full release theo tiêu chí đã đặt, dù tất cả unit tests PASS.

Đây không phải “QA thất bại toàn bộ”, mà là một quyết định có chứng cứ cụ thể cho từng blocker.

### 19.4. Kế hoạch khắc phục có thể kiểm tra

| Action | Owner giả định | Điều kiện kết thúc |
|---|---|---|
| A1: kiểm tra role và signed URL của export | AppSec/API team | Positive/negative tests bao phủ các role và đường truy cập đã định |
| A2: xử lý token compatibility | Identity + payment worker | Mixed-version window PASS, fallback/key plan an toàn |
| A3: sửa migration mapping | Data engineering | Rehearsal và reconciliation đạt theo mọi nhóm nghiệp vụ trọng yếu |
| A4: xác nhận alert privileged refund | SecOps | Tạo event thử và nhận alert có định danh đúng |
| A5: kiểm chứng DR key/worker | SRE/DR owner | Recovery-path check theo tiêu chí đã duyệt |
| A6: bổ sung rollout plan | Release manager | Targeting đúng tenant, stop triggers và rollback/forward fix rõ |
| A7: re-run tests trên RC mới | QA + security assurance | Artifacts tương ứng với bản sẽ deploy, evidence còn hiệu lực |

Sau các action này, nhóm phải chốt **RC mới**, thực hiện impact-based retesting, lưu artifact identity và yêu cầu phê duyệt GO/NO-GO lại.

### 19.5. Vì sao chỉ “sửa bug và deploy” vẫn chưa đủ?

Nếu nhóm sửa worker và migration rồi chạy lại unit tests, vẫn còn câu hỏi:

- Signed URL có bị lộ qua đường ngoài tenant?
- Security alert sau format đổi có thực sự phát?
- Region dự phòng có key material và worker tương thích?
- Feature flag có chỉ bật cho nhóm tenant được duyệt?
- Có thể rollback sau một phần migration mà không mất dữ liệu?

Đây chính là phần release-level assurance phải hoàn thiện trước khi tuyên bố release đã đạt yêu cầu.

## 20. Ví dụ thứ hai: release API đa tenant và điều kiện GO hạn chế

Một sản phẩm SaaS có 50 endpoint. Release thêm một API bulk export; có 49/50 endpoint được kiểm thử authz đầy đủ, nhưng endpoint bulk export chưa có negative tests cho role support. Product muốn GO có giới hạn để kiểm tra telemetry.

Có thể xem xét các lựa chọn:

| Lựa chọn | Điều kiện cần xem |
|---|---|
| **NO-GO toàn bộ** | Phù hợp nếu export là đường dữ liệu nhạy cảm và không có kiểm soát bù trừ đủ tin cậy |
| **Deploy nhưng giữ feature tắt** | Phải xác minh endpoint không reachable ngoài phạm vi, flag không phải authorization thay thế và có giám sát |
| **GO canary cho tenant nội bộ** | Cần phê duyệt risk/exposure, test tối thiểu, dữ liệu thử, guardrail và stop criteria |
| **GO toàn bộ với risk acceptance** | Chỉ hợp lệ nếu quyền phê duyệt, yêu cầu bên ngoài và mức rủi ro thực tế cho phép; không được đổi finding thành PASS |

**Điểm học thuật:** có thể có **limited release decision** mà không gian dối về assurance status. Ví dụ ghi “được phép deploy artifact tới production nhưng chưa bật bulk export cho khách hàng; điều kiện bật là negative authz tests và review” khác hoàn toàn “đã phát hành an toàn toàn bộ tính năng”.

## 21. Release assurance record có thể kiểm toán

Một record tốt nên nối các lớp:

~~~text
Business objective / Security requirements
                 ↓
Release manifest & impacted assets
                 ↓
Change set + dependency/threat analysis
                 ↓
Risk scenarios, controls, residual risks
                 ↓
Security gates + test evidence
                 ↓
Release decision / exception authority
                 ↓
Artifact provenance + rollout record
                 ↓
Post-release verification
                 ↓
Release acceptance / open findings / follow-up
~~~

### 21.1. Mẫu YAML tổng hợp

Mẫu này dùng **giá trị giả định**, các trạng thái PENDING cố ý thể hiện việc chưa có bằng chứng. Nó không phải approval hoặc báo cáo thật:

~~~yaml
release_assurance:
  release_id: REL-EXAMPLE-014
  release_candidate: rc-4
  service: checkout-platform
  target:
    environment: production
    regions: [region-a, region-b]
    exposure: "limited-tenant-canary"
  manifest_ref: "restricted/releases/rel-014/manifest"
  artifact_digests_ref: "restricted/releases/rel-014/digests"
  sbom_ref: "restricted/releases/rel-014/sbom"
  dependency_map_ref: "restricted/architecture/checkout-dependencies"

  requirements:
    - AUTHZ-OBJECT-01
    - DATA-INTEGRITY-02
    - LOG-AUDIT-03
    - DR-RECOVERY-04

  risk_review:
    change_refs: [CHG-101, CHG-102, CHG-103]
    scenario_refs: [R1, R2, R3, R4, R5, R6, R7]
    aggregate_risk_assessment_ref: "restricted/risk/rel-014"
    residual_risk_status: PENDING_REVIEW

  pre_release_gates:
    manifest_complete: PASS
    supply_chain_review: PASS
    authz_negative_tests: PENDING
    mixed_version_compatibility: PASS
    migration_integrity: PENDING
    logging_alert_test: PASS
    dr_dependency_check: PENDING
    rollback_plan_review: PASS

  findings:
    open_blocking:
      - AUTHZ-EXAMPLE-007
    exceptions:
      - id: EXAMPLE-EX-02
        status: PENDING_APPROVAL
        expires_at_utc: "2026-12-31T00:00:00Z"

  release_decision:
    status: NO_GO
    reason: "Blocking authorization evidence and DR verification incomplete"
    decision_owner_role: AUTHORIZED_RELEASE_RISK_OWNER
    security_reviewer_role: SECURITY_ASSURANCE
    decision_evidence_ref: "restricted/releases/rel-014/decision"
    reevaluation_conditions:
      - "Authz negative tests pass for targeted export paths"
      - "DR compatibility checked and evidenced"
      - "All blocking findings have authorized dispositions"

  rollout:
    plan_ref: "restricted/releases/rel-014/rollout"
    stop_conditions_ref: "restricted/releases/rel-014/guardrails"
    status: NOT_STARTED

  post_release_verification:
    status: NOT_STARTED
    evidence_refs: []
    final_acceptance: PENDING
~~~

Một YAML có dòng **PASS** hoặc **NO_GO** chỉ biểu thị dữ liệu; người đánh giá phải có quyền mở **test report, source, deployment, reviewer decision và evidence gốc**. Tên, ngày và path là placeholder. Không chép secret, host nhạy cảm hoặc dữ liệu khách hàng thực vào record phát hành chia sẻ rộng.

## 22. Bảo vệ evidence và tính toàn vẹn của quyết định

Release evidence có thể chứa thiết kế IAM, dependency yếu, danh sách lỗ hổng, dữ liệu kiểm thử hoặc đường mạng nội bộ. Cần:

1. Lưu tại kho có phân quyền theo vai trò và ghi audit trail.
2. Dẫn chiếu từ release record qua ID; tránh sao chép thông tin nhạy cảm không cần thiết.
3. Gắn evidence với RC, commit/build, artifact, môi trường, timestamp và người thu thập.
4. Lưu bản gốc khi có thể, bao gồm kết quả FAIL; không chỉ lưu bản đã tổng hợp.
5. Có lịch sử phê duyệt, thay đổi scope, ngoại lệ, decision và lý do GO/NO-GO.
6. Thiết lập retention và quyền xóa phù hợp chính sách/nghĩa vụ.
7. Kiểm tra integrity của artifact và log; hiểu rằng **hash không chứng minh dữ liệu nguồn đúng hoặc đủ trước thời điểm băm**.
8. Kiểm tra người thực hiện thay đổi và người chấp thuận rủi ro có tách vai trò phù hợp.

Khi phát hiện một CI job bị cấu hình sai và không kiểm tra một phần source, đừng xóa kết quả PASS cũ rồi thay thế mà không có lịch sử. Cần ghi **lỗ hổng của evidence**, đánh dấu các release conclusion liên quan để xem xét lại và chạy phép kiểm tra đúng.

## 23. Chỉ số theo dõi chất lượng release assurance

| Chỉ số | Ý nghĩa | Tránh diễn giải sai |
|---|---|---|
| **High-risk releases without review** | Số release đáng kể thiếu risk/security assessment | Không được ẩn dưới tỷ lệ chung |
| **Pre-release blocking defect detection** | Phát hiện vấn đề trước khi ảnh hưởng production | Tăng tạm thời có thể phản ánh kiểm thử tốt hơn |
| **Post-release security regression** | Control suy yếu sau phát hành | Phải xét phạm vi monitoring và severity |
| **Change failure / rollback rate** | Tỷ lệ release gây lỗi theo định nghĩa tổ chức | Rollback chủ động có thể là quyết định an toàn |
| **Evidence-backed release acceptance** | Tỷ lệ release có hậu kiểm và evidence phù hợp | Đầy đủ trường không đồng nghĩa bằng chứng đủ tin cậy |
| **Unverified candidate changes** | RC có thay đổi sau lần test/approval cuối mà chưa impact-review | Rủi ro test không đúng bản phát hành |
| **Open blocking findings by age** | Vấn đề trọng yếu chưa xử lý trước release | Cần xem risk decision, không tự loại khỏi thống kê |
| **Canary escape rate** | Lỗi chỉ phát hiện sau khi mở rộng rollout | Cần biết canary có đại diện và guardrails có hoạt động |
| **Time to detect and recover** | Khả năng nhận diện và khôi phục sự cố release | Có thể khác theo loại release và dữ liệu |
| **Exception carryover** | Ngoại lệ được mang từ nhiều release liên tiếp | Rủi ro tích lũy và gia hạn không có tiến bộ |
| **Supply-chain evidence completeness** | RC có artifact identity và provenance kiểm tra được | Không đồng nghĩa artifact không có lỗ hổng |

**Không nên chỉ tối ưu tỷ lệ release thành công** bằng cách trì hoãn mọi bản vá cần thiết hoặc sửa định nghĩa incident. Mục đích các chỉ số là giúp phát hiện lỗ hổng trong quá trình ra quyết định và xác minh, không làm đẹp dashboard.

## 24. Những sai lầm thường gặp

| Sai lầm | Vì sao không đúng | Cách cải thiện |
|---|---|---|
| Các PR đều approved nên release an toàn | Tương tác nhiều change chưa được thử | Release-level risk review và E2E tests |
| CI xanh = GO | CI có thể thiếu threat, dependency và data checks | Gates theo risk scenarios và evidence |
| Test RC cũ rồi deploy RC mới | Bằng chứng không khớp artifact | Version binding, impact-based retest |
| Chỉ xem vulnerability scanner | Không kiểm tra authz, integrity, operability | Kết hợp threat, controls và test phù hợp |
| SBOM tồn tại nên supply chain an toàn | SBOM có thể thiếu/sai và không đánh giá behavior | Kiểm tra provenance, scope, policy, vulnerability risk |
| Không kiểm thử mixed-version | Lỗi xảy ra trong rolling rollout | Contract/compatibility tests theo từng giai đoạn |
| Chỉ theo dõi 5xx sau GO | Có thể lộ dữ liệu trong khi API vẫn trả 200 | Security/data guardrails |
| Canary không đại diện | Không thấy lỗi ở nhóm role/tenant quan trọng | Canary/fixture theo risk |
| Feature flag được coi là authz | Endpoint có thể vẫn reachable | Enforce security ở backend/trust boundary |
| Có rollback script là đủ | Có thể không đảo ngược data/key | Rehearsal, reconciliation và forward fix plan |
| Risk score thấp vì nhiều test PASS | Trộn coverage với xác suất an toàn | Scenario-based residual risk và limitations |
| Cộng rủi ro change bằng số học đơn giản | Bỏ phụ thuộc và common-mode failure | Aggregate risk/interaction analysis |
| “Release approved” là “risk accepted” | Sai thẩm quyền và phạm vi | Quyết định risk riêng có điều kiện |
| Ngoại lệ ở release trước tự kéo sang release mới | Scope/time/asset thay đổi | Review expiry và phạm vi từng RC |
| Thay đổi emergency không hậu kiểm | Thiếu audit trail, cấu hình tạm còn sót | Post-release verification và CAP |
| Deploy hoàn tất nên đóng release | Chưa xác nhận security/business controls | Post-release acceptance rõ |
| Bỏ qua DR/backups | Có thể không phục hồi sau dữ liệu mới | Targeted restore/DR checks |
| Không cập nhật assurance case | Claim dựa trên evidence phiên bản cũ | Change impact, update evidence và review |
| Chỉ xem dịch vụ riêng lẻ | Shared IdP/KMS/DB có thể gây lỗi chung | Dependency graph và cross-service testing |

## 25. Bài tập thực hành

### Bài tập A — Phân biệt Change risk và Release risk

Ba thay đổi độc lập được phê duyệt:

- Service A cập nhật token validator.
- IdP luân chuyển key ký.
- Service B đổi cách cache public keys.

1. Viết risk scenario cho từng thay đổi.
2. Nêu ít nhất ba kịch bản chỉ xuất hiện **khi cả ba thay đổi cùng phát hành**.
3. Thiết kế mixed-version test matrix gồm old/new IdP key, service A/B và thời điểm rotation.
4. Xác định guardrails và điều kiện rollback/forward fix.
5. Giải thích vì sao ba báo cáo unit tests PASS chưa đủ cho GO.

### Bài tập B — Release có migration dữ liệu

Release thay schema của 3 triệu bản ghi giao dịch. Rehearsal trên 100.000 bản ghi cho thấy 99,9% đúng; 0,1% lỗi thuộc trạng thái hoàn tiền quan trọng.

1. Vì sao tỷ lệ 99,9% không tự chứng minh đủ an toàn?
2. Xây tiêu chí integrity cho các nhóm nghiệp vụ trọng yếu.
3. Thiết kế reconciliation và kiểm tra idempotency, retry, mixed-version.
4. Nêu khi nào rollback không còn an toàn, cần forward fix.
5. Viết quyết định **NO-GO** có evidence và điều kiện đánh giá lại.

### Bài tập C — Canary có vẻ khỏe nhưng thiếu security logging

Một release rollout 10% traffic và đạt mục tiêu latency, error rate. Nhưng SIEM không nhận log từ các API mới, chưa kiểm tra cảnh báo privileged action.

1. Cổng nào bị ảnh hưởng? Có thể kết luận release đạt security assurance không?
2. Đề xuất synthetic event và kiểm tra source-to-SIEM.
3. Nêu cách ghi evidence gap của giai đoạn rollout.
4. Viết stop/hold conditions và kế hoạch sửa/kiểm chứng.
5. Phân biệt hậu kiểm hiện tại với việc chứng minh log đã đầy đủ trong quá khứ.

### Bài tập D — Release candidate đã đổi sau phê duyệt

Candidate rc-2 đã được security review và approval. Trước deployment, developer cherry-pick một hotfix vào rc-3, thay thư viện authorization. Release manager muốn giữ approval cũ.

1. Những evidence nào của rc-2 có thể còn giá trị, những gì cần impact review?
2. Security test nào bắt buộc đánh giá lại nếu authz library đổi?
3. Làm thế nào chứng minh rc-3 đúng là artifact production đang chạy?
4. Cần ai phê duyệt và ghi lại quyết định theo mức rủi ro?
5. Viết release record ngắn thể hiện rõ trạng thái **PENDING EVIDENCE** nếu test chưa hoàn tất.

### Bài tập E — GO có điều kiện với deferred finding

Release có một finding về bulk export chưa được khắc phục; feature hiện chỉ phục vụ tenant thử nghiệm.

1. Xác định phần data/identity/tenant exposure cần khóa.
2. Thiết kế điều kiện feature flag, authz enforcement và monitoring.
3. Nêu quyền phê duyệt, thời hạn exception và phạm vi risk acceptance.
4. Đề xuất cách chứng minh ngoài nhóm tenant thử nghiệm không thể dùng endpoint.
5. Phân biệt “deploy được phép” với “kích hoạt feature cho mọi khách hàng”.
6. Nêu điều kiện buộc phải thu hồi GO có điều kiện.

**Gợi ý chung:** Câu trả lời tốt sẽ nêu **candidate cụ thể, phạm vi, risk scenario, control, phép thử, evidence, mức rủi ro còn lại, người quyết định và điều kiện đánh giá lại**. Không dùng số lượng test PASS để thay cho lập luận.

## 26. Checklist trước khi ra quyết định release

- [ ] Mục tiêu và phạm vi release được xác định: dịch vụ, tenant, account, region, data, feature flags.
- [ ] Release manifest khớp với release candidate và mọi thay đổi liên quan.
- [ ] Artifact provenance/digest và dependency inventory được kiểm tra ở mức phù hợp.
- [ ] Risk assessment bao phủ **rủi ro tương tác, cộng gộp và common-mode failure**.
- [ ] Security requirements, threat model và control mapping được cập nhật cho release.
- [ ] Các security gates trọng yếu có tiêu chí PASS/FAIL cụ thể.
- [ ] Test bao phủ authn/authz, data integrity, crypto, logging, supply chain và dependency tùy loại release.
- [ ] Mixed-version window và contract compatibility đã được xem xét.
- [ ] Migration rehearsal, backup/restore, rollback hoặc forward fix được kiểm tra khi cần.
- [ ] Mọi blocker/finding/exception đều có trạng thái và quyết định đúng thẩm quyền.
- [ ] Canary/exposure plan có nhóm đại diện, guardrails và stop conditions.
- [ ] Người trực, incident plan, support, communication và runbook sẵn sàng.
- [ ] GO/NO-GO ký cho **đúng candidate và đúng phạm vi**.
- [ ] Deployment record và runtime artifact/config verification sẽ được thu thập.
- [ ] Có kế hoạch post-release checks về security, dữ liệu, nghiệp vụ và availability.
- [ ] Tài liệu assurance, risk register và evidence index được cập nhật sau quyết định.

Checklist không thay cho đánh giá rủi ro theo yêu cầu áp dụng, nhưng giúp kiểm tra chất lượng đầu vào trước khi một release tác động production.

## 27. Ghi nhớ

**Release risk là rủi ro của toàn bộ phiên bản được đưa vào môi trường đích**, gồm sự kết hợp giữa các thay đổi, dependency, artifact, cách rollout, dữ liệu và các security controls bị ảnh hưởng. Nó không được đánh giá đầy đủ chỉ từ tổng các PR đã duyệt, số lượng test PASS hay độ ổn định của pipeline.

Trong **SECURITY_SECURITY_ASSURANCE**, một chuỗi đảm bảo phát hành có thể truy vết là:

**Mục tiêu bảo mật / rủi ro → release candidate và manifest → phân tích tương tác/threat/dependency → release risk scenarios → security gates và evidence → GO/NO-GO đúng thẩm quyền → triển khai có giới hạn và guardrails → kiểm chứng sau release → residual risk, findings và cải tiến liên tục.**

Một kết luận release assurance đáng tin phải trả lời được **bản nào được đánh giá, điều gì thay đổi, tại đâu, những rủi ro chính là gì, bằng chứng nào xác nhận từng control, những gì chưa được chứng minh, ai đã quyết định và điều kiện nào sẽ khiến release phải dừng hoặc đánh giá lại**.
