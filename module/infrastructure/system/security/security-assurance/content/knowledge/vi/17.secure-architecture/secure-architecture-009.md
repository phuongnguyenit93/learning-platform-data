# Architecture Decision (Quyết định kiến trúc)

## 1. Vì sao cần quyết định kiến trúc có cấu trúc?

Một nền tảng SaaS quản lý hóa đơn phục vụ hàng trăm doanh nghiệp phải chọn cách cô lập dữ liệu giữa tenants, xác thực người dùng, kết nối dịch vụ, lưu khóa mã hóa và xử lý sự kiện bất đồng bộ. Có nhiều phương án đều có thể chạy được: dùng một database chung với tenant identifier, tách schema, tạo database riêng cho từng khách hàng hoặc tách cloud account theo tenant.

Nếu quyết định chỉ dựa trên thói quen của đội kỹ thuật hoặc một benchmark hiệu năng, những hệ quả như **cross-tenant data exposure, quyền vận hành quá rộng, khó khôi phục, chi phí migration và phụ thuộc nhà cung cấp** có thể chỉ xuất hiện sau khi hệ thống đã có dữ liệu thật.

**Architecture decision (quyết định kiến trúc)** là lựa chọn có chủ đích giữa các phương án thiết kế có ảnh hưởng đáng kể tới cấu trúc, hành vi, chất lượng, rủi ro và khả năng phát triển của hệ thống. Một quyết định tốt phải nêu rõ **bối cảnh, mục tiêu, các yếu tố chi phối, phương án đã cân nhắc, lý do chọn, trade-offs, hệ quả, rủi ro còn lại, người chịu trách nhiệm và điều kiện đánh giá lại**.

Trong module **SECURITY_SECURITY_ASSURANCE**, quyết định kiến trúc cần hỗ trợ việc chứng minh hệ thống đáp ứng mục tiêu bảo mật. Vì vậy, quyết định không dừng ở câu “chọn công nghệ X”; nó phải nối:

**Business context → quality/security attributes → constraints and risks → options → decision → controls → verification → evidence → reassessment.**

Quyết định có thể ảnh hưởng nhiều năm tới cách bảo vệ dữ liệu, danh tính, khóa, hạ tầng, vận hành và chi phí. Ghi lại quyết định giúp đội hiện tại hiểu lý do, giúp reviewer kiểm tra giả định và giúp đội tương lai biết **khi nào quyết định còn phù hợp, khi nào cần thay đổi**.

> Một quyết định kiến trúc không chỉ trả lời “chọn gì”; nó phải giải thích “vì sao lựa chọn này phù hợp trong bối cảnh đã nêu, chấp nhận hệ quả nào và kiểm chứng bằng cách nào”.

## 2. Architecture decision là gì và không phải là gì?

Một quyết định kiến trúc thường có phạm vi ảnh hưởng vượt một dòng code hoặc một thay đổi cấu hình nhỏ. Nó có thể thay đổi:

- Ranh giới giữa các hệ thống, services, modules hoặc teams.
- Cách dữ liệu được lưu, truyền, phân vùng, mã hóa, chia sẻ và xóa.
- Cách danh tính được xác thực, liên kết và phân quyền.
- Cách workload, network, cloud accounts và môi trường được cô lập.
- Cách phần mềm được build, ký, phát hành và triển khai.
- Cách hệ thống phát hiện sự cố, phục hồi và đáp ứng mục tiêu availability.
- Khả năng mở rộng, hiệu năng, chi phí, khả năng thay nhà cung cấp và độ phức tạp vận hành.

| Hoạt động/tài liệu | Mục đích | Quan hệ với architecture decision |
| --- | --- | --- |
| **Architecture decision** | Chọn phương án và ghi lý do/hệ quả. | Là đối tượng chính cần quản trị. |
| **Architecture Decision Record (ADR)** | Lưu quyết định theo cấu trúc có thể tra cứu. | Là hiện vật ghi lại decision. |
| **Architecture diagram** | Mô tả cấu trúc, thành phần và luồng. | Cung cấp góc nhìn hỗ trợ quyết định. |
| **Threat model** | Xác định threats, attack paths và mitigations. | Cung cấp đầu vào bảo mật cho decision. |
| **Architecture review** | Đánh giá thiết kế và evidence theo tiêu chí. | Kiểm tra decision và việc thực hiện. |
| **Implementation design** | Mô tả cách hiện thực cụ thể. | Triển khai decision thành code/config. |
| **Runbook/standard** | Hướng dẫn vận hành hoặc yêu cầu áp dụng lặp lại. | Có thể là hệ quả hoặc constraint của decision. |
| **Change request** | Đề xuất thay đổi hệ thống. | Có thể kích hoạt decision mới hoặc thay decision cũ. |

Không phải mọi lựa chọn kỹ thuật đều cần ADR. Đổi tên biến hoặc sửa một câu SQL không ảnh hưởng đáng kể tới kiến trúc thường không cần. Nhưng thay authorization model, database isolation, identity provider, key management, event delivery hoặc cloud account boundary có thể cần decision record vì hệ quả lan rộng và khó đảo ngược.

## 3. Khi nào một quyết định đủ quan trọng để ghi lại?

Một decision đáng ghi lại khi nó có một hoặc nhiều đặc điểm:

1. Ảnh hưởng nhiều service, nhóm phát triển hoặc nhóm vận hành.
2. Làm thay đổi trust boundary, data flow, identity hoặc quyền đặc biệt.
3. Ảnh hưởng dữ liệu nhạy cảm, dữ liệu cá nhân, khóa hoặc tài sản quan trọng.
4. Tạo phụ thuộc lâu dài vào vendor, protocol, framework hoặc nền tảng.
5. Có trade-off đáng kể giữa security, availability, performance, cost và maintainability.
6. Khó đảo ngược hoặc migration có chi phí/rủi ro lớn.
7. Cần phê duyệt, chấp nhận rủi ro hoặc chứng minh với auditor/khách hàng.
8. Đã từng có nhiều phương án tranh luận hoặc có giả định cần theo dõi.
9. Có thể trở thành mẫu thiết kế được tái sử dụng cho nhiều hệ thống.

### Decision significance scale minh họa

| Mức | Đặc điểm | Ví dụ | Hồ sơ phù hợp |
| --- | --- | --- | --- |
| **Local** | Ảnh hưởng hẹp, dễ đảo ngược, rủi ro thấp. | Chọn thư viện format ngày cho một module. | Pull request/design note. |
| **Component** | Ảnh hưởng một service hoặc data flow. | Chọn cache strategy cho endpoint. | ADR ngắn, test/impact notes. |
| **System** | Ảnh hưởng nhiều service, security boundary hoặc lifecycle. | Chọn mô hình tenant isolation. | ADR đầy đủ, threat analysis, review. |
| **Enterprise/platform** | Ảnh hưởng nhiều sản phẩm, tổ chức hoặc nhà cung cấp. | Chuẩn identity federation toàn công ty. | Architecture decision package, governance và assurance. |

Đây là thang phân loại minh họa. Tổ chức cần định nghĩa ngưỡng và điều kiện bắt buộc ghi ADR theo risk appetite, chính sách và mức độ quan trọng của hệ thống.

## 4. Những yếu tố chi phối quyết định (decision drivers)

Không thể chọn kiến trúc chỉ theo một tiêu chí. Một quyết định phải nêu **điều gì quan trọng nhất trong bối cảnh cụ thể**.

| Driver | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Security** | Threat nào cần giảm, trust boundary nào phải bảo vệ? | Ngăn truy cập chéo tenant, giảm quyền admin. |
| **Privacy** | Dữ liệu nào được xử lý, ai nhận, mục đích và retention? | Giảm trường gửi sang analytics. |
| **Availability** | Hệ thống chịu được failure nào và cần phục hồi bao lâu? | Multi-zone, queue durability, DR. |
| **Integrity** | Giao dịch và dữ liệu cần nhất quán ở mức nào? | Idempotency cho payment/export jobs. |
| **Performance** | Latency, throughput và concurrency mục tiêu? | Cache, partitioning, asynchronous processing. |
| **Scalability** | Tăng tenant, dữ liệu và traffic ảnh hưởng ra sao? | Shared DB so với DB per tenant. |
| **Operability** | Ai triển khai, giám sát, khắc phục và on-call? | Số database, key rotation, runbook. |
| **Maintainability** | Có thể sửa, nâng cấp và kiểm thử không? | Module boundaries, schema versioning. |
| **Cost** | Chi phí hạ tầng, license, vendor và migration? | Dedicated environment cho khách hàng lớn. |
| **Interoperability** | Có cần tương thích IdP, API hoặc hệ thống cũ? | OIDC/SAML, event schemas. |
| **Portability** | Có thể chuyển cloud/provider hoặc công nghệ không? | Managed database so với self-hosted. |
| **Compliance/contract** | Có yêu cầu bắt buộc theo phạm vi nào? | Data residency, auditability, retention. |
| **Time to market** | Thời gian triển khai và phụ thuộc? | Dùng managed service để rút ngắn vận hành. |
| **Reversibility** | Nếu sai, đổi phương án có khó không? | Vendor-specific data model hoặc key format. |

### Phân biệt constraint, driver và preference

- **Constraint:** điều kiện bắt buộc, ví dụ phải triển khai trong cloud account đã được tổ chức phê duyệt.
- **Decision driver:** yếu tố được dùng để so sánh phương án, ví dụ blast radius hoặc RTO.
- **Preference:** điều đội ngũ thích, ví dụ quen một framework. Preference có thể có giá trị nhưng không được ngụy trang thành yêu cầu bảo mật.

Một ADR tốt nêu rõ **constraint nào đã được xác minh**, driver nào được ưu tiên và preference nào chỉ là cân nhắc phụ.

## 5. Quy trình ra quyết định kiến trúc

Một quy trình có thể dùng cho decision có ảnh hưởng đáng kể:

1. **Xác định vấn đề:** điều gì cần quyết định, vì sao ngay lúc này?
2. **Chốt context và scope:** hệ thống, actors, data, environment, constraints và phụ thuộc.
3. **Xác định quality attributes:** security, privacy, availability, performance, operability và cost.
4. **Mô hình hóa rủi ro:** threat scenarios, impact, likelihood, assumptions và existing controls.
5. **Tạo phương án thực tế:** ít nhất một phương án hiện tại, các lựa chọn thay thế và phương án không làm gì nếu phù hợp.
6. **Đặt tiêu chí so sánh:** ưu tiên, trọng số nếu có cơ sở, ngưỡng bắt buộc và tiêu chí loại.
7. **Đánh giá trade-offs:** chi phí, độ phức tạp, failure modes, lock-in, migration và blast radius.
8. **Chọn và ghi decision:** rationale, rejected options, consequences, controls, owner và trạng thái.
9. **Review/approve theo thẩm quyền:** tham vấn security, privacy, operations, product và risk owner khi cần.
10. **Triển khai và kiểm chứng:** tests, configuration, runtime evidence, ADR linkage.
11. **Theo dõi và đánh giá lại:** trigger, assumption expiry, incident và change.

~~~mermaid
flowchart TD
    A["Problem / change / decision trigger"] --> B["Context, scope and constraints"]
    B --> C["Quality attributes and security objectives"]
    C --> D["Threat model and risk scenarios"]
    D --> E["Generate viable options"]
    E --> F["Compare trade-offs and consequences"]
    F --> G{"Option satisfies mandatory constraints?"}
    G -- "No" --> E
    G -- "Yes" --> H["Select decision + document rationale"]
    H --> I["Review / approval / risk authority"]
    I --> J["Implement controls and verification"]
    J --> K["Evidence, monitor assumptions and outcomes"]
    K --> L{"Trigger or material drift?"}
    L -- "Yes" --> B
    L -- "No" --> K
~~~

### Không bắt đầu bằng tên công nghệ

Nếu câu hỏi là “Có nên dùng Kubernetes?”, cần làm rõ vấn đề: cần orchestration, isolation, scaling, portability hay tiêu chuẩn vận hành nào? Nếu câu hỏi là “Có nên dùng service mesh?”, phải nêu yêu cầu identity-aware traffic, mTLS, telemetry, policy và chi phí vận hành. Công nghệ là một **phương án**, không phải mục tiêu.

## 6. Phân tích context trước khi so sánh phương án

Context cần đủ cụ thể để người không tham gia cuộc họp có thể hiểu quyết định sau này.

### Context checklist

- Business capability và user journeys liên quan.
- Hệ thống, services, modules và data assets trong scope.
- Data classification, privacy impact và data lifecycle.
- Actors: users, admins, workloads, vendors, partners.
- Trust boundaries: public/internal, tenant, account, region, organization.
- Existing architecture, legacy dependencies và constraints.
- Volume, latency, availability, recovery và growth expectations.
- Threat scenarios, incidents hoặc audit findings liên quan.
- Standards, contracts và legal obligations đã xác định.
- Assumptions chưa được kiểm chứng và owner xác minh.

### Ví dụ context chưa đủ

“Chúng ta cần database nhanh hơn.”

Context tốt hơn sẽ nói rõ hệ thống hóa đơn đang gặp query latency nào, tenant growth, write/read ratio, consistency requirements, data classification, backup/restore, tenant isolation, operational capacity và migration constraints. Khi đó phương án có thể là index, read replica, partitioning, cache, database upgrade hoặc tách workload — thay vì mặc định thay toàn bộ database.

## 7. Xác định security objectives và quality attributes

Security objectives phải được viết thành **kết quả mong muốn**, sau đó chuyển thành requirements có thể kiểm tra.

| Objective | Câu hỏi kiến trúc | Requirement minh họa |
| --- | --- | --- |
| **Confidentiality** | Ai được đọc dữ liệu và qua đường nào? | User chỉ đọc objects thuộc scope được cấp quyền. |
| **Integrity** | Ai được tạo/sửa và hệ thống phát hiện thay đổi thế nào? | Event giả/sửa trái phép bị từ chối hoặc phát hiện. |
| **Availability** | Failure nào được chịu đựng và phục hồi? | Dịch vụ phục hồi trong RTO/RPO đã duyệt. |
| **Authenticity** | Danh tính user/service được xác minh thế nào? | Chỉ issuer và workload identity được tin cậy. |
| **Accountability** | Có thể truy nguyên hành động quan trọng? | Export/admin/key events có audit và correlation. |
| **Isolation** | Một tenant hoặc service bị compromise ảnh hưởng tới đâu? | Worker không có quyền đọc dữ liệu ngoài nhiệm vụ. |
| **Privacy** | Dữ liệu có được dùng đúng mục đích và tối thiểu? | Analytics chỉ nhận fields đã được duyệt. |
| **Recoverability** | Có thể khôi phục dữ liệu và quyền sau sự cố? | Restore drill với key dependencies thành công. |

### Security requirement phải testable

Tránh viết “hệ thống phải an toàn”. Một requirement tốt nên có actor/principal, action, resource/data scope, conditions và trust assumptions, expected allow/deny/failure behavior, test method và evidence.

Ví dụ: “Export Worker chỉ xử lý job được tạo từ principal đã xác minh; tenant và resource scope lấy từ job record do server quản lý; job bị sửa tenant hoặc replay ngoài idempotency window phải bị từ chối và tạo audit event.”

## 8. Sinh phương án và tránh lựa chọn giả

Phương án phải đủ khác biệt để so sánh, nhưng không cần liệt kê mọi công nghệ trên thị trường.

### Một tập phương án cân bằng

1. **Baseline/current state:** giữ kiến trúc hiện tại và cải thiện controls.
2. **Incremental change:** thay đổi một phần, giảm rủi ro/migration.
3. **Alternative architecture:** thay đổi cấu trúc hoặc boundary.
4. **Managed solution:** chuyển một phần trách nhiệm cho provider.
5. **Defer/no change:** chỉ khi cần đánh giá tác động của việc trì hoãn.

### Tránh strawman

Không mô tả phương án A với mọi ưu điểm và phương án B chỉ bằng những nhược điểm. Mỗi phương án cần được đánh giá theo **cùng drivers, cùng scope và cùng threat assumptions**.

### Kiểm tra tính khả thi

- Có thể triển khai với năng lực và thời gian thực tế?
- Có dependency, license, region hoặc service quota?
- Có hỗ trợ backup, export, migration và exit?
- Có thể vận hành, monitor, debug và audit?
- Có tương thích yêu cầu bảo mật/riêng tư?
- Có thể thử bằng prototype hoặc spike trước khi cam kết?

Nếu không có đủ dữ liệu, ghi rõ uncertainty và tạo **time-boxed experiment**. Không dùng benchmark nhỏ làm bằng chứng cho tải production nếu workload khác biệt.

## 9. Đánh giá trade-offs và hệ quả

Một phương án hiếm khi tối ưu mọi tiêu chí. Decision record cần ghi **lợi ích, chi phí, rủi ro, phụ thuộc và hậu quả dài hạn**.

| Loại hệ quả | Câu hỏi |
| --- | --- |
| **Security** | Attack surface, blast radius, privilege, trust và detection thay đổi ra sao? |
| **Privacy** | Data recipients, purpose, retention và khả năng thực hiện quyền thay đổi thế nào? |
| **Availability** | Failure domains, single points, RTO/RPO và dependency? |
| **Integrity** | Consistency, ordering, replay, reconciliation và audit? |
| **Performance** | Latency, throughput, resource usage và scaling? |
| **Operability** | Ai trực, ai nâng cấp, cần kỹ năng và runbooks nào? |
| **Cost** | Hạ tầng, license, network egress, nhân lực và migration? |
| **Portability** | Lock-in, API-specific design, data export và exit strategy? |
| **Complexity** | Số thành phần, policy, failure modes và khả năng debug? |
| **Migration** | Cutover, dual-write, rollback, data conversion và downtime? |
| **Governance** | Owner, approvals, auditability và policy exceptions? |

### Không che trade-off bằng điểm số

Một bảng chấm điểm có thể giúp thảo luận nhưng không thay thế lý do. Ví dụ phương án database per tenant có thể giảm blast radius, nhưng nếu đội không đủ năng lực vận hành hàng nghìn database, backup/patching có thể trở nên không nhất quán. Cần nêu **rủi ro của chính phương án được chọn**, không chỉ rủi ro của phương án bị loại.

## 10. Security-first decision analysis

Mỗi phương án nên được kiểm tra bằng một tập câu hỏi bảo mật:

1. **Threat coverage:** phương án giảm threat nào và còn threat nào?
2. **Trust boundaries:** có thêm boundary, bridge hoặc trusted component mới?
3. **Identity:** principal nào được tạo, xác minh, ủy quyền và thu hồi?
4. **Authorization:** quyền được kiểm tra ở điểm nào, có bypass/async path?
5. **Data protection:** dữ liệu, bản sao, keys và logs được bảo vệ ra sao?
6. **Isolation:** blast radius nếu một service, account hoặc tenant bị compromise?
7. **Secure failure:** khi IdP, KMS, DNS, broker hoặc vendor lỗi, hệ thống phản ứng thế nào?
8. **Detection:** có telemetry để phát hiện abuse và xác minh controls?
9. **Recovery:** backup, DR, key recovery và incident response có khả thi?
10. **Verification:** requirement có thể kiểm thử trước và sau release?

### Threat modeling theo phương án

Không chỉ threat model kiến trúc hiện tại. Một lựa chọn mới có thể tạo attack path mới. Ví dụ chuyển từ synchronous API sang event-driven có thể giảm latency và coupling, nhưng bổ sung queue permissions, replay, dead-letter data, consumer inventory và retry semantics.

### Tách mitigation thật khỏi giả định

“Worker chạy trong private subnet” là một thuộc tính mạng. Nó không chứng minh worker có identity đúng, tenant scope đúng hoặc không bị gọi từ workload khác. Một mitigation chỉ được tính là hiệu quả khi **điều kiện thực thi và evidence** được xác định.

## 11. Decision matrix: sử dụng đúng cách

Ma trận giúp so sánh có cấu trúc. Trước khi gán điểm, phải xác định tiêu chí bắt buộc và tiêu chí có thể đánh đổi, thang điểm có định nghĩa, trọng số có cơ sở, nguồn evidence/ước lượng, ngưỡng loại phương án và người phê duyệt.

### Ví dụ ma trận tenant isolation

Giả sử hệ thống đang đánh giá bốn phương án: shared schema, separate schema, database per tenant và account/project per tenant. Bảng dưới đây là **minh họa định tính**, không phải kết luận cho mọi SaaS.

| Tiêu chí | Shared schema | Separate schema | DB per tenant | Account/project per tenant |
| --- | --- | --- | --- | --- |
| Isolation potential | Thấp hơn, phụ thuộc query/policy. | Trung bình, phụ thuộc grants/routing. | Cao hơn ở tầng database. | Có thể cao hơn ở control plane. |
| Operational complexity | Thấp hơn lúc đầu. | Trung bình. | Cao khi tenant tăng. | Rất cao nếu quản trị thủ công. |
| Cost | Thường thấp. | Thường thấp-trung bình. | Tăng theo số tenant/tài nguyên. | Có thể cao hơn đáng kể. |
| Backup/restore granularity | Cần logic tenant-aware. | Có thể chọn schema nhưng phức tạp. | Có thể theo database. | Có thể tách account/region. |
| Cross-tenant blast radius | Có thể rộng nếu query sai. | Giảm một số lỗi nhưng shared DB vẫn còn. | Hẹp hơn ở database layer. | Có thể hẹp hơn nhưng shared control plane vẫn còn. |
| Migration effort | Thấp ban đầu, khó tách sau nếu coupling cao. | Trung bình. | Cao nếu từ shared schema. | Cao nhất nếu phải tái cấu trúc platform. |
| Assurance burden | Cần test scoping mọi đường. | Cần test schema grants/routing. | Cần test provisioning, key, backup và isolation. | Cần test org/account IAM, networking và central ops. |

Không nên cộng “cao hơn” thành một điểm tổng nếu chưa có rubric. Một requirement bắt buộc như data isolation có thể **loại phương án** không đáp ứng được, dù phương án đó rẻ và nhanh.

## 12. Reversibility và mức cam kết của quyết định

| Loại | Đặc điểm | Cách quản trị |
| --- | --- | --- |
| **Reversible** | Có thể đổi nhanh, dữ liệu/clients ít phụ thuộc. | Prototype, feature flag, metric và rollback. |
| **Costly to reverse** | Có migration, compatibility hoặc vận hành phức tạp. | ADR đầy đủ, staged rollout, export/rollback plan. |
| **Hard to reverse** | Tạo lock-in, thay data model, trust boundary hoặc key format lâu dài. | Review cấp cao, proof-of-concept, exit strategy, risk approval. |
| **Irreversible/destructive** | Có thể mất dữ liệu hoặc khả năng giải mã. | Phê duyệt đặc biệt, backup/restore proof, safety gate và evidence. |

Nếu chưa chắc về lựa chọn, ưu tiên **giữ các đường thay đổi mở**: abstraction có ích, data export, schema versioning, provider adapters, key envelope versioning và contract tests. Tuy nhiên, abstraction quá mức cũng tạo complexity và có thể làm mờ security boundary.

Nếu trì hoãn sẽ khiến dữ liệu nhạy cảm được lưu vào cấu trúc khó migration hoặc tạo trust boundary yếu, có thể cần quyết định sớm dù còn uncertainty. Khi đó cần **time-boxed validation, guardrails và explicit assumptions**, thay vì chờ thông tin hoàn hảo.

## 13. Decision lifecycle và trạng thái

| Status | Ý nghĩa | Điều kiện chuyển |
| --- | --- | --- |
| **Proposed** | Đang đề xuất, chưa có quyết định. | Có context, options và owner để review. |
| **Under review** | Các bên đang xem xét trade-offs/risk. | Nhận comments, evidence và approvals cần thiết. |
| **Accepted** | Phương án được chọn theo thẩm quyền. | Rationale, consequences, conditions và owner rõ. |
| **Accepted with conditions** | Chọn có điều kiện hoặc control bắt buộc. | Conditions, deadlines, evidence và risk authority ghi rõ. |
| **Rejected** | Không chọn phương án. | Rationale và lý do loại được ghi. |
| **Superseded** | Có decision mới thay thế. | Liên kết ADR mới và migration/transition plan. |
| **Deprecated** | Không còn dùng nhưng cần ghi nhận lịch sử. | Phạm vi dừng và dependency đã xử lý. |
| **Withdrawn** | Đề xuất bị rút trước khi quyết định. | Ghi lý do và các công việc liên quan. |

Không đổi ADR cũ thành Accepted sau khi triển khai chỉ để làm hồ sơ đẹp. Nếu quyết định đã thay đổi, tạo **decision mới và liên kết decision cũ**, giữ lịch sử để biết tại sao hệ thống có trạng thái hiện tại.

## 14. Architecture Decision Record (ADR): cấu trúc chuẩn

Một ADR cần đủ ngắn để được đọc và đủ chi tiết để kiểm tra lại. Cấu trúc phổ biến:

1. **ID và title:** định danh duy nhất, tên quyết định.
2. **Status/date/owners:** trạng thái, ngày, người đề xuất/quyết định.
3. **Context:** vấn đề, business drivers, scope và constraints.
4. **Decision drivers:** tiêu chí và thứ tự ưu tiên.
5. **Options considered:** phương án, ưu/nhược và lý do loại.
6. **Decision:** phương án đã chọn và phạm vi áp dụng.
7. **Rationale:** vì sao phương án đáp ứng drivers.
8. **Consequences:** positive, negative, trade-offs và dependencies.
9. **Security/privacy impact:** threats, controls, data flows và residual risk.
10. **Implementation/verification:** tasks, tests, evidence và owner.
11. **Assumptions/open questions:** điều chưa xác minh.
12. **Review triggers:** sự kiện làm quyết định cần đánh giá lại.
13. **References:** diagrams, threat models, requirements và decisions liên quan.

### Ví dụ ADR ngắn

**ADR-024 — Chọn mô hình lưu trữ dữ liệu tenant**

- **Status:** Accepted with conditions.
- **Context:** SaaS hóa đơn cần onboarding nhanh cho nhiều doanh nghiệp, dữ liệu có classification Confidential.
- **Drivers:** tenant isolation, operability, cost, backup/restore, migration.
- **Options:** shared schema; separate schema; DB per tenant; account/project per tenant.
- **Decision:** dùng shared schema cho nhóm tenant tiêu chuẩn với tenant-scoped queries và database policy; tenant có yêu cầu isolation/contract đặc biệt được đánh giá theo tier riêng.
- **Rationale:** đáp ứng scale và khả năng vận hành hiện tại nếu controls được kiểm chứng.
- **Consequences:** query/cache/job/export phải giữ tenant context; blast radius của shared DB vẫn còn.
- **Conditions:** negative tests xuyên API/worker/export; policy review; restore và audit coverage.
- **Residual risk:** lỗi shared service có thể ảnh hưởng nhiều tenant; risk owner theo dõi.
- **Reassessment:** thay data classification, customer contract, tenant volume hoặc xuất hiện cross-tenant incident.

Đây là **quyết định giả định để học**, không phải khuyến nghị mặc định cho mọi hệ thống. Trong thực tế phải xác minh yêu cầu hợp đồng, pháp lý, kiến trúc và năng lực vận hành.

## 15. Ghi nhận options và rejected alternatives

Ghi phương án bị loại là một phần quan trọng của decision record. Nó giúp tránh lặp lại tranh luận và cho biết **giả định nào khiến phương án chưa phù hợp**.

Mỗi option nên có cách hoạt động và phạm vi, security/privacy posture, availability/performance/cost, complexity và skill requirements, migration/rollback, vendor dependencies và exit, risks/assumptions, evidence như prototype, benchmark, test, provider docs hoặc expert review.

Một phương án bị loại hôm nay có thể phù hợp khi điều kiện thay đổi. Ví dụ DB per tenant bị loại do chi phí khi có 100 tenants, nhưng có thể phù hợp khi khách hàng enterprise yêu cầu dedicated isolation. Ghi rõ **lý do loại và trigger xem lại** giúp quyết định không trở thành giáo điều.

## 16. Architecture decision cho tenant isolation

Đây là quyết định có ảnh hưởng trực tiếp đến confidentiality, blast radius, backup, vận hành và khả năng mở rộng.

### Các phương án

1. **Shared database/shared schema:** mọi tenant dùng chung schema, mỗi row có tenant identifier.
2. **Shared database/separate schema:** phân tách logic bằng schema.
3. **Database per tenant:** mỗi tenant có database riêng.
4. **Dedicated account/project/cluster:** tách thêm hạ tầng và control plane theo mô hình cloud.

### Những câu hỏi cần trả lời

- Threat model có attacker nào: user, worker, DBA, cloud admin, compromised service?
- Một lỗi query, cache, export hoặc analytics có thể ảnh hưởng bao nhiêu tenants?
- Có RLS hoặc query scoping; ai có thể bypass?
- Connection pool và background jobs gắn tenant context thế nào?
- Search index, logs, backup và export có isolation tương tự không?
- Có yêu cầu dedicated key, data residency hoặc contractual isolation?
- Provisioning, patching, backup, restore và deletion được tự động hóa tới đâu?
- Ai kiểm tra effective access và drift?

### Controls theo lựa chọn shared schema

- Tenant context lấy từ principal đã xác minh.
- Repository/query luôn giới hạn tenant; không tin tenant ID từ client.
- Có database constraints/policies nếu phù hợp để defense in depth.
- Cache key, search filters, exports và background jobs giữ tenant scope.
- Service identities và database grants được giới hạn.
- Tests negative cross-tenant ở mọi data path.
- Audit event có actor/resource/outcome nhưng giảm dữ liệu nhạy cảm.
- Monitoring phát hiện truy cập chéo, bulk export và policy drift.

Nếu database per tenant nhưng analytics warehouse gom dữ liệu mọi tenant vào một bảng chung, kiến trúc tổng thể vẫn có shared boundary. Cần đánh giá **toàn bộ data lifecycle và các bản sao**.

## 17. Decision cho identity architecture

Một hệ thống có thể chọn local identities, enterprise federation, centralized identity broker hoặc kết hợp. Quyết định ảnh hưởng login, provisioning, account recovery, role mapping, session, availability và trách nhiệm với IdP.

| Option | Lợi ích | Trade-offs |
| --- | --- | --- |
| **Local account** | Tự chủ luồng, phù hợp nhóm user nhỏ hoặc external users. | Password/reset/MFA và lifecycle do ứng dụng quản lý; tăng attack surface. |
| **Enterprise federation** | Khách hàng quản lý authentication và lifecycle của nhân viên. | Phụ thuộc IdP, mapping, trust configuration và federation incident. |
| **Central identity broker** | Chuẩn hóa nhiều IdPs và policy. | Broker trở thành dependency quan trọng; cần availability, trust và key management. |
| **Hybrid** | Phù hợp nhiều nhóm user. | Nhiều authentication paths, policy consistency và account linking phức tạp. |

### Drivers và requirements

- Issuer/client/tenant trust được đăng ký và quản lý.
- Token/response validation gồm issuer, audience, signature, state/nonce hoặc protocol-specific protections.
- Identity binding dùng stable subject trong issuer context.
- Role mapping không tự nâng quyền từ group claim không tin cậy.
- JIT/SCIM provisioning và deprovisioning có audit.
- Session revocation, account recovery và break-glass.
- IdP outage có hành vi rõ, không mở fallback yếu.
- Service-to-service identity được quản lý riêng với user identity.

Thêm IdP, thay issuer/certificate, đổi subject mapping, thay role claims, incident federation hoặc yêu cầu MFA mới đều có thể kích hoạt decision review.

## 18. Decision cho synchronous API hay event-driven architecture

| Driver | Synchronous request/response | Event-driven/asynchronous |
| --- | --- | --- |
| Coupling | Caller phụ thuộc availability/latency của callee. | Giảm coupling thời điểm, nhưng phụ thuộc broker/consumer. |
| Response | Kết quả trực tiếp hoặc lỗi ngay. | Thường trả accepted; kết quả cuối đến sau. |
| Failure | Timeout/retry có thể tạo duplicate. | Retry, replay, DLQ và backlog cần thiết kế. |
| Security boundary | API authentication/authorization. | Thêm producer, broker, consumer và worker identities. |
| Data exposure | Request/response và API logs. | Payload có thể tồn tại trong topic, retry, DLQ và nhiều consumer. |
| Ordering/consistency | Có thể đồng bộ trong transaction scope. | Event ordering, eventual consistency và reconciliation. |
| Operations | Tracing call chain. | Correlation, lag, consumer health và replay operations. |

Khi chọn event-driven, ADR phải xác định event schema, owner, versioning và data minimization; producer/consumer authorization và topic isolation; tenant context và nguồn tin cậy của job; message integrity, replay/idempotency, ordering và duplicate handling; retention, DLQ, redaction, backup và deletion; monitoring lag, poison messages, consumer failures; ai được replay hoặc purge messages; evidence cho flow từ publish tới side effect cuối.

**Event-driven không tự an toàn hoặc mở rộng tốt hơn.** Nó chuyển một số rủi ro từ request chain sang message lifecycle và consumer governance.

## 19. Decision cho database, cache và data platform

Database decision cần xem **consistency, isolation, backup, recovery, data model, access, encryption và operational skills**.

Các lựa chọn thường gặp gồm relational database cho transactions và constraints, document database cho dữ liệu linh hoạt, key-value store cho access patterns cụ thể, search engine cho truy vấn/index, data warehouse/lake cho analytics và cache để giảm latency/tải nguồn.

Không chọn database chỉ vì một benchmark tổng quát. Cần đo workload thật, consistency requirements, transaction boundaries, query patterns và failure modes.

### Security/privacy implications

- Database role và application authorization có tách không?
- Encryption/key ownership và backup/restore?
- Row-level/tenant isolation có test?
- Search index có filter và access control đồng bộ?
- Cache key có bao gồm tenant/permission context?
- Analytics có nhận fields ngoài mục đích?
- Data retention/deletion có propagate tới bản sao?
- Replication/CDC có mở thêm recipient hoặc region?

Cache có thể giữ dữ liệu nhạy cảm lâu hơn kỳ vọng hoặc trả nhầm tenant nếu cache key không chứa scope cần thiết. ADR nên ghi TTL, invalidation, encryption nếu phù hợp, permission-aware cache strategy, stale data behavior và tests cross-tenant.

## 20. Decision cho cloud deployment và account boundaries

Một lựa chọn cloud architecture thường gồm single account/project với nhiều environments; tách production/non-production accounts/projects; central shared services và delegated administration; dedicated account/project cho từng sản phẩm/tenant/regulated workload; hoặc hybrid/multi-cloud.

### Các drivers

Isolation, blast radius, centralized governance, billing, data residency, IAM complexity, network connectivity, logging, backup, service availability và skill/cost.

ADR cần chỉ rõ provider quản lý control nào, khách hàng chịu trách nhiệm cấu hình gì, evidence nào được provider cung cấp và phần nào phải kiểm tra ở account/runtime của tổ chức.

**Multi-cloud không tự giảm rủi ro.** Thêm cloud provider có thể tăng resilience hoặc giảm phụ thuộc, nhưng cũng thêm IAM models, network paths, key systems, logging formats, policy drift và vận hành. Cần có lý do cụ thể và phương án kiểm chứng từng nền tảng.

## 21. Decision cho cryptography và key management

Các lựa chọn có thể gồm provider-managed encryption at rest, customer-managed KMS keys, application-layer envelope encryption, field-level encryption/tokenization, HSM-backed signing hoặc key operations, và dedicated key scope theo service/tenant.

| Driver | Câu hỏi |
| --- | --- |
| Threat model | Cần bảo vệ trước mất storage, cloud operator, application compromise hay insider? |
| Key control | Ai tạo, dùng, rotate, disable và destroy key? |
| Separation | Có tách key admin khỏi data access? |
| Data lifecycle | Backup, archive, export và old ciphertext phụ thuộc key nào? |
| Performance | KMS call latency, throughput, quotas và caching? |
| Recovery | Có khôi phục được key và dữ liệu khi region/account lỗi? |
| Agility | Có thể migrate algorithm/provider và đọc dữ liệu cũ? |
| Evidence | Có effective policy, denied-use tests, audit và restore drills? |

Một key riêng cho mỗi tenant có thể giảm blast radius nhưng tăng key inventory, quota, provisioning và rotation burden. Key chung có thể phù hợp trong một số mô hình nhưng đòi hỏi controls về authorization, context và isolation. **Không có lựa chọn phổ quát nếu chưa có threat model và requirements.**

## 22. Decision cho API gateway, service mesh và network controls

### API gateway

Phù hợp với ingress policies, authentication integration, routing, rate limiting và telemetry. Tuy nhiên, gateway không thay authorization theo object trong service và không thể là điểm kiểm soát duy nhất nếu có internal callers hoặc async jobs.

### Service mesh

Có thể cung cấp mTLS, service identity, traffic policy và telemetry giữa workloads. Trade-offs gồm control-plane dependency, certificate lifecycle, policy complexity, debugging và failure modes. mTLS xác thực workload theo trust model nhưng **không tự quyết định service được phép thao tác trên dữ liệu nào**.

### Network segmentation

Có thể giảm lateral movement và giới hạn ingress/egress. Nhưng network rules dễ drift và không thay application authorization. Cần test effective routes/policies, DNS, egress và các đường quản trị.

ADR cần nêu threats mà gateway/mesh/network policy giải quyết; identity và authorization còn thực thi ở đâu; TLS termination và các chặng truyền; bypass paths như direct service access/admin port/alternate ingress; failure khi control plane/certificate provider không khả dụng; monitoring, policy rollout, rollback và evidence.

## 23. Decision cho modular monolith hay microservices

| Tiêu chí | Modular monolith | Microservices |
| --- | --- | --- |
| Deployment | Một artifact/deployment unit hoặc ít đơn vị hơn. | Nhiều services deploy độc lập. |
| Network boundary | Nhiều tương tác trong process. | Nhiều service-to-service flows. |
| Data ownership | Có thể dùng chung database nhưng module boundaries cần rõ. | Có thể sở hữu data riêng, nhưng consistency/integration phức tạp. |
| Operational complexity | Thường thấp hơn lúc đầu. | Cao hơn do service discovery, observability, deployment và on-call. |
| Blast radius | Process lỗi có thể ảnh hưởng nhiều modules. | Có thể cô lập hơn nếu boundaries và dependencies đúng. |
| Security | Giảm một số network attack surfaces nhưng cần module authorization. | Có nhiều identity/network policies, secrets và APIs cần quản trị. |
| Scalability | Scale thường theo application unit. | Có thể scale theo service, với chi phí vận hành. |

Microservices không mặc định an toàn hơn vì mỗi service có boundary. Nếu mọi service dùng cùng credential admin, cùng database quyền rộng và không có service identity, boundary chỉ tồn tại trên sơ đồ.

Modular monolith không mặc định kém an toàn. Module boundaries, dependency rules, authorization, data ownership và deployment controls có thể được kiểm chứng. Quyết định phải phù hợp quy mô tổ chức và khả năng vận hành.

## 24. Decision cho build, artifact và deployment

Software supply chain là một phần của kiến trúc bảo mật. Quyết định cần xác định:

- Build chạy ở đâu, ai có thể thay pipeline?
- CI runner có ephemeral, isolation và egress restrictions?
- Dependencies được pin, kiểm tra và cập nhật thế nào?
- Artifact có provenance, SBOM và signature?
- Signing keys được bảo vệ, rotation và audit ra sao?
- Ai được deploy production, có tách build/deploy identities?
- Rollback và verification sau deploy?
- IaC/policy changes có review và drift detection?

| Option | Ưu điểm | Trade-offs |
| --- | --- | --- |
| Shared CI runners | Dễ quản lý và tiết kiệm tài nguyên. | Cross-project contamination, secrets và network scope. |
| Ephemeral isolated runners | Giảm persistence và cross-job contamination. | Chi phí, startup time, quản lý cache. |
| Central deployment controller | Governance và audit tập trung. | Control plane trở thành dependency quan trọng. |
| Per-team deployment credentials | Tự chủ đội nhóm. | Permission drift và khó audit tập trung. |

Một ADR tốt không chỉ chọn công cụ CI; nó định nghĩa **trust chain từ source tới artifact tới production** và các phép kiểm chứng.

## 25. Decision cho observability, audit và incident response

Một hệ thống cần telemetry đủ để phát hiện/điều tra nhưng không tạo thêm dữ liệu nhạy cảm ngoài mục đích.

### Các quyết định cần ghi

- Event nào là security/audit event?
- Log/trace/metric chứa field nào, có PII/secret không?
- Correlation giữa actor, request, job, object và service ra sao?
- Log được chuyển tới đâu, ai là vendor/recipient?
- Ai có quyền xem, export, xóa và thay retention?
- Có chống sửa/xóa log khi phù hợp?
- Health monitoring có phát hiện nguồn im lặng và ingestion lag?
- Incident response có runbook, owner, evidence preservation và escalation?

Log quá ít khiến điều tra thiếu dữ kiện; log quá nhiều có thể làm tăng privacy risk, chi phí và blast radius khi kho log bị lộ. Quyết định cần **data minimization, threat-driven event design và test**.

## 26. ADR và liên kết với security architecture review

ADR ghi lại lựa chọn; **security architecture review** đánh giá quyết định và hệ quả theo yêu cầu. Hai hiện vật cần tham chiếu nhau.

| ADR chứa | Review kiểm tra |
| --- | --- |
| Context, scope và drivers. | Có đầy đủ assets, actors, flows và constraints? |
| Options và rationale. | Có xem xét phương án khả thi và trade-offs cân bằng? |
| Threats/security implications. | Threat model có bao phủ boundary/attack paths? |
| Controls và consequences. | Controls đặt đúng nơi, có owner và failure behavior? |
| Assumptions. | Assumptions nào chưa xác minh và có cách kiểm tra? |
| Verification plan. | Tests/evidence có đủ cho design và operation? |
| Approval/status. | Người phê duyệt có thẩm quyền, residual risk có owner? |
| Reassessment triggers. | Có cơ chế kích hoạt review lại khi điều kiện đổi? |

ADR nói “đã chấp nhận rủi ro” không tự hợp thức hóa một control bắt buộc bị thiếu. Risk acceptance cần đúng thẩm quyền và không thể ghi đè các yêu cầu pháp lý/hợp đồng/chuẩn bắt buộc. Review cần ghi **điều kiện và evidence**, không chỉ kiểm tra chữ ký.

## 27. Evidence cho một quyết định kiến trúc

Một quyết định có thể được lập luận hợp lý nhưng chưa đủ cơ sở nếu thiếu dữ liệu thực tế. Evidence nên phù hợp từng loại claim.

| Loại claim | Evidence hỗ trợ |
| --- | --- |
| Option đáp ứng throughput/latency. | Workload model, benchmark có thể tái lập, test ở cấu hình gần production. |
| Isolation đáp ứng threat. | Threat model, IAM/DB policy, negative cross-tenant tests. |
| Managed service có control cần thiết. | Provider documentation/attestation đúng service/region/time và config của customer. |
| Key design an toàn. | Key inventory, policies, crypto review, denied-use tests, restore drills. |
| Event architecture không mất dữ liệu. | Failure injection có kiểm soát, outbox/reconciliation tests, backlog metrics. |
| Vendor đáp ứng yêu cầu. | Contract, data flow, assurance reports trong scope và customer-side configuration. |
| Migration có thể rollback. | Prototype, migration rehearsal, data reconciliation và rollback test. |
| Quyết định giảm rủi ro. | Risk comparison có rationale, controls đã triển khai, test và residual risk assessment. |

### Chất lượng evidence

- **Relevance:** đúng claim, option và requirement.
- **Completeness:** bao phủ population, flow, version và điều kiện cần.
- **Accuracy:** phương pháp, nguồn và observed result đáng tin.
- **Freshness:** phù hợp release, provider, configuration và thời kỳ.
- **Provenance:** biết ai/công cụ nào thu thập và từ đâu.
- **Repeatability:** có thể chạy lại hoặc kiểm tra lại.
- **Independence:** mức độc lập phù hợp với mức rủi ro.
- **Limitations:** ghi rõ phần chưa đo, giả định và sample.

Một benchmark chạy trên laptop không đủ chứng minh production capacity; một screenshot policy không đủ chứng minh effective permissions; một tài liệu vendor không đủ chứng minh cấu hình account của khách hàng.

## 28. Claim–Argument–Evidence cho Architecture decision

### Claim mẫu

“Mô hình tenant isolation được chọn cho Invoice SaaS đáp ứng yêu cầu bảo mật và vận hành trong phạm vi tenant tiêu chuẩn, với các controls và verification đã định nghĩa; các trường hợp cần isolation cao hơn được xử lý qua decision path riêng.”

### Argument

1. Business context, classification, threat model và requirements xác định mức isolation cần thiết.
2. Các phương án được so sánh trên cùng drivers và điều kiện.
3. Phương án được chọn có controls ở API, worker, database, cache, export và analytics.
4. Controls có owner, test cases và evidence.
5. Operational capacity, backup/restore và migration được đánh giá.
6. Assumptions, exceptions và triggers được quản trị.

### Evidence

- Versioned ADR và architecture diagrams.
- Threat model/risk assessment.
- Decision matrix và prototype results.
- Security requirements/control mapping.
- Code/IaC/config review và negative tests.
- Production verification, logs, access reviews.
- Migration/restore drills.
- Risk acceptance, findings, retest và reassessment records.

### Điều gì bác bỏ claim?

- Test cross-tenant đọc được dữ liệu ngoài scope.
- Production config khác ADR hoặc có quyền wildcard ngoài kiểm soát.
- Benchmark không đại diện workload thực.
- Backup/restore không hoạt động do decision bỏ qua key dependencies.
- Vendor/data flow không có trong scope nhưng nhận dữ liệu nhạy cảm.

Khi evidence trái chiều xuất hiện, decision phải được xem xét lại; không được coi ADR là bằng chứng quyết định ban đầu luôn đúng.

## 29. Ví dụ ADR đầy đủ: chọn mô hình tenant isolation cho Invoice SaaS

### ADR-024 — Tenant data isolation model

**Status:** Accepted with conditions.

**Context:** Invoice SaaS phục vụ doanh nghiệp nhỏ và vừa. Mỗi tenant có hóa đơn, thông tin liên hệ và tài liệu PDF. Hệ thống cần onboarding nhanh, chi phí có thể dự báo và hỗ trợ khách hàng có yêu cầu isolation khác nhau.

**Problem:** Chọn cách phân vùng dữ liệu và quyền sao cho hạn chế cross-tenant exposure, có thể backup/restore, đáp ứng nhu cầu tăng trưởng và vận hành được với năng lực hiện tại.

**Decision drivers:**

1. Ngăn truy cập chéo tenant.
2. Giới hạn blast radius của lỗi service hoặc query.
3. Có thể kiểm chứng quyền ở API, worker, export và data platform.
4. Backup/restore và deletion theo tenant khả thi.
5. Chi phí và vận hành phù hợp với quy mô hiện tại.
6. Có đường nâng cấp sang isolation mạnh hơn khi khách hàng yêu cầu.

**Options considered:**

- A: Shared DB/shared schema.
- B: Shared DB/separate schema.
- C: Database per tenant.
- D: Dedicated account/project/cluster cho tenant.

**Decision:** Chọn A cho tier tiêu chuẩn với điều kiện tenant context được lấy từ principal đã xác minh, mọi data access được scope theo tenant, background jobs và exports có kiểm tra riêng, cache/search/analytics được bao phủ, và negative tests chạy trong CI. Các khách hàng có yêu cầu isolation cao hoặc ràng buộc hợp đồng riêng sẽ được đánh giá theo tier/decision riêng; không tự động đưa vào A.

**Rationale:** Phương án A phù hợp vận hành và chi phí ở quy mô hiện tại nếu controls được thực thi ở tất cả data paths. Việc thiết kế tenant-aware repositories, schema constraints/policies phù hợp và data contracts làm giảm nguy cơ lỗi logic. Phương án có thể nâng cấp theo nhu cầu, nhưng migration cần được kiểm soát.

**Consequences:**

- Shared database vẫn là failure domain chung.
- Query, cache, export, event, backup và support tools phải giữ tenant context.
- Data owner và platform owner phải duy trì inventory/lineage.
- Provisioning/backup/restore cần có test ở cả tenant-level và platform-level.
- Onboarding khách hàng mới phải tạo metadata và policies theo chuẩn.

**Security requirements:**

- SAR-TEN-01: User chỉ đọc/sửa object thuộc tenant được cấp quyền.
- SAR-TEN-02: Worker chỉ xử lý job có tenant/resource scope được server xác minh.
- SAR-TEN-03: Download file yêu cầu authorization và giới hạn thời gian.
- SAR-TEN-04: Consumer analytics chỉ nhận fields được duyệt.
- SAR-TEN-05: Service identities không có quyền ngoài nhiệm vụ.
- SAR-TEN-06: Backup/restore và deletion có thể đối soát theo scope.

**Verification plan:**

- Cross-tenant API/search/export negative tests.
- Forged tenant/job and replay tests.
- Effective DB/IAM/storage permission review.
- Cache key and data lineage tests.
- Restore drill và deletion verification.
- Runtime monitoring for denied cross-tenant access.

**Risks/limitations:**

- Shared DB compromise hoặc lỗi logic có thể ảnh hưởng nhiều tenants.
- Một số bản sao analytics/backup có thể có lifecycle khác.
- Khả năng phát hiện truy cập sai phụ thuộc log coverage.

**Owners:** Solution Architect, Invoice Service Owner, Data Platform Owner, Security Control Owner.

**Risk owner:** người được tổ chức ủy quyền cho customer data risk.

**Reassessment triggers:** cross-tenant incident, tenant growth vượt capacity, thay data classification, khách hàng yêu cầu dedicated isolation, thay cloud/data platform, audit finding nghiêm trọng.

**Approval conditions:** Chỉ coi decision được triển khai đạt khi controls, negative tests và runtime evidence trong scope có kết quả phù hợp; trước đó trạng thái là Accepted with conditions / Implementation pending.

Đây là ADR giả định để minh họa cách lập luận. Trong dự án thực, các yêu cầu và kết luận phải được xác nhận bằng data, contract, threat model và evidence thật.

## 30. Java/Spring: quyết định kiến trúc cho module boundaries và authorization

Một quyết định có thể quy định **service layer sở hữu business authorization**, repository chỉ cung cấp truy vấn theo tenant/resource và controller không tự quyết định quyền dựa trên client fields.

~~~java
@Service
public class InvoiceQueryService {
    private final InvoiceRepository repository;

    public InvoiceQueryService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public InvoiceSummary get(
            UUID invoiceId, VerifiedPrincipal principal) {

        String tenantId = principal.tenantId();
        if (tenantId == null || !principal.mayReadInvoices()) {
            throw new AccessDeniedException("Not authorized");
        }

        Invoice invoice = repository
                .findByIdAndTenantId(invoiceId, tenantId)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND));

        return new InvoiceSummary(
                invoice.getId(),
                invoice.getIssueDate(),
                invoice.getAmount(),
                invoice.getStatus());
    }
}
~~~

### Quyết định này cần nêu rõ

- VerifiedPrincipal được tạo từ đâu và được xác minh thế nào?
- Service method có được gọi qua Spring Security proxy/interceptor phù hợp?
- Repository có query tenant-scoped và test negative?
- Worker/export/batch có dùng cùng policy hay cần decision khác?
- DTO có loại bỏ trường ngoài purpose?
- Cache/search index có giữ tenant scope?
- Có audit và monitoring cho denied access?

Đoạn code chỉ minh họa một cách hiện thực. Một quyết định kiến trúc không thể được chứng minh bằng code snippet; cần code review, integration tests, configuration và runtime evidence.

## 31. Mẫu ADR YAML có thể quản trị bằng hệ thống

Mẫu dưới đây minh họa cấu trúc dữ liệu cho decision record. Đây không phải metadata của module và không phải schema bắt buộc của một công cụ:

~~~yaml
adr:
  id: ADR-024
  title: "Tenant data isolation model"
  status: accepted_with_conditions
  date: "2026-11-28"
  owners:
    proposer: "Solution Architecture"
    decision_owner: "Platform Architecture Board"
    implementation_owner: "Invoice Service Team"
    risk_owner: "Customer Data Risk Owner"
  context:
    system: "invoice-saas"
    scope:
      - invoice-api
      - invoice-database
      - export-worker
      - analytics-pipeline
    constraints:
      - "Support standard SaaS tier"
      - "Meet approved tenant isolation requirements"
  drivers:
    - id: D1
      name: "Cross-tenant confidentiality"
      priority: mandatory
    - id: D2
      name: "Operational scalability"
      priority: high
    - id: D3
      name: "Tenant-level recovery"
      priority: high
  options:
    - id: A
      name: "Shared database and schema"
      disposition: selected
    - id: B
      name: "Shared database with separate schemas"
      disposition: rejected
      rationale: "Migration and routing complexity for current scale"
    - id: C
      name: "Database per tenant"
      disposition: deferred_for_dedicated_tier
  decision:
    option: A
    rationale: "Meets current drivers if listed controls are verified"
    conditions:
      - "Tenant context is server-verified"
      - "API, worker, export and analytics have negative tests"
      - "Backup and deletion flows are verified"
  security:
    threat_model_ref: "restricted://architecture/threat-model"
    requirements:
      - SAR-TEN-01
      - SAR-TEN-02
      - SAR-TEN-03
      - SAR-TEN-04
      - SAR-TEN-05
      - SAR-TEN-06
  consequences:
    positive:
      - "Lower initial operational overhead"
    negative:
      - "Shared database remains a common failure domain"
  verification:
    tests:
      - "cross_tenant_api_negative"
      - "forged_job_tenant_negative"
      - "export_download_authorization"
      - "analytics_field_allowlist"
      - "backup_restore_and_deletion"
    evidence_state: pending
  assumptions:
    - "Current tenant count and workload remain within tested capacity"
  reassessment_triggers:
    - "cross_tenant_incident"
    - "new_customer_isolation_requirement"
    - "data_classification_change"
    - "platform_migration"
~~~

Một hồ sơ thực cần thêm approval records, decision history, evidence IDs có thật, version, links được quản trị, thời hạn và status transition. Không ghi secret, private key hoặc dữ liệu cá nhân thật vào ADR.

## 32. Governance: ai đề xuất, ai quyết định và ai chấp nhận rủi ro?

| Vai trò | Trách nhiệm |
| --- | --- |
| **Decision proposer** | Mô tả vấn đề, context, options và evidence ban đầu. |
| **Solution/system architect** | Điều phối phương án, dependencies, views và trade-offs. |
| **Security architect** | Phân tích threat, requirements, security controls và residual risk. |
| **Data/privacy owner** | Xem data purpose, classification, flows, retention và nghĩa vụ privacy. |
| **Platform/operations owner** | Đánh giá operability, availability, recovery, monitoring và capacity. |
| **Product/business owner** | Ưu tiên business drivers và chấp nhận tác động nghiệp vụ trong thẩm quyền. |
| **Architecture board/reviewer** | Review consistency, standards, cross-system impact và decision quality. |
| **Independent assurance** | Đánh giá evidence, testability và control effectiveness. |
| **Risk owner** | Quyết định residual risk/exception theo thẩm quyền. |
| **Implementation owner** | Triển khai decision, cập nhật artifacts và chứng minh kết quả. |

### RACI minh họa

**R** = thực hiện; **A** = chịu trách nhiệm cuối cùng; **C** = tham vấn; **I** = thông báo.

| Hoạt động | Proposer/Architect | Security | Data/Privacy | Operations | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| Xác định context/options | **A/R** | C | C | C | I |
| Threat/risk analysis | R | **A/R** | C | C | I |
| Privacy/data flow impact | C | C | **A/R** | C | I |
| Operability/DR assessment | C | C | I | **A/R** | I |
| Decision approval theo governance | R | C | C | C | **A** |
| Implement và verification | C | C | C | **A/R** | I |
| Residual risk acceptance | C | C | C | C | **A/R** |

RACI phải điều chỉnh theo cơ cấu thực tế. Người đề xuất có thể trình bày rationale nhưng không mặc nhiên có quyền phê duyệt ngoại lệ hoặc chấp nhận rủi ro ngoài thẩm quyền.

## 33. Decision debt và quản lý các quyết định cũ

**Decision debt** xuất hiện khi quyết định quan trọng không được ghi lại, giả định đã hết hạn, hoặc implementation không còn khớp với rationale ban đầu.

### Dấu hiệu

- Nhiều service triển khai cùng một chức năng theo cách khác nhau.
- Team không biết tại sao dùng vendor/protocol/identity model hiện tại.
- ADR nói một điều nhưng production config khác.
- Không ai sở hữu key, certificate, trust boundary hoặc exception.
- Migration/exit plan không còn khả thi.
- Một incident lặp lại vì assumption cũ không được kiểm tra.
- Decision record không có links tới code/config/test.

### Cách giảm decision debt

1. Duy trì ADR index theo system/domain và trạng thái.
2. Liên kết ADR với architecture diagrams, repos, deployment và controls.
3. Định kỳ review các decisions có risk cao hoặc phụ thuộc thay đổi nhanh.
4. Đánh dấu Superseded/Deprecated và trỏ tới decision thay thế.
5. Kiểm tra implementation drift và các assumptions.
6. Tạo remediation cho decision không còn đáp ứng requirements.

Không cần biến mọi ADR thành tài liệu dài hàng chục trang. **Chất lượng rationale và khả năng trace** quan trọng hơn độ dài.

## 34. Continuous Architecture Decision Assurance

Một decision cần được đánh giá lại khi context, threat hoặc assumptions thay đổi.

~~~mermaid
flowchart TD
    A["Accepted ADR + requirements + assumptions"] --> B["Implementation and runtime"]
    B --> C["Tests, telemetry, incidents and cost signals"]
    C --> D{"Assumptions and drivers still valid?"}
    D -- "Yes" --> E["Retain decision with fresh evidence"]
    E --> C
    D -- "No" --> F["Open reassessment / new ADR"]
    F --> G["Compare current and new options"]
    G --> H["Supersede, retain or rollback decision"]
    H --> I["Migrate controls and update evidence"]
    I --> A
~~~

### Trigger cần theo dõi

- Business scale, workload, tenant count hoặc data classification thay đổi.
- Thêm user group, identity provider, vendor, region hoặc data recipient.
- Threat landscape hoặc vulnerability ảnh hưởng giả định của decision.
- Incident, audit finding hoặc test failure.
- Key/crypto protocol, network topology hoặc cloud platform thay đổi.
- Provider deprecates service/API, thay contract hoặc thay region availability.
- Cost/latency/capacity vượt ngưỡng đã dùng khi lựa chọn.
- RTO/RPO, compliance obligation hoặc customer contract thay đổi.
- Một assumption không còn đúng hoặc không thể thu thập evidence.

### Metrics có thể kích hoạt reassessment

- Error rate, latency, queue lag, capacity và recovery time.
- Cross-tenant denial anomalies hoặc privileged access.
- Cost per tenant, cost of operations và vendor egress.
- Key/certificate rotation failures.
- Open findings và exception age.
- Data flow/consumer drift.
- Dependency vulnerabilities và supply-chain incidents.

### Fitness functions cho decision

Có thể tự động hóa các điều kiện như không cho tạo public storage ngoài baseline, không cho workload dùng wildcard admin, yêu cầu mọi data flow có owner, hoặc bắt buộc production deployment liên kết ADR. Nhưng fitness function không thể thay người đánh giá **trade-offs và threat model**.

## 35. Architecture decision và residual risk

Một decision có thể chọn phương án giảm rủi ro nhưng vẫn còn phần không thể loại bỏ hoàn toàn.

### Cần ghi riêng

- **Inherent/current risk:** rủi ro theo bối cảnh trước hoặc ngoài controls, theo phương pháp tổ chức.
- **Current residual risk:** mức rủi ro còn lại với controls thực sự đang vận hành.
- **Target residual risk:** mức dự kiến sau khi các controls/mitigations được triển khai và retest.
- **Accepted risk:** phần risk được người có thẩm quyền chấp nhận trong scope/thời hạn cụ thể.

### Một acceptance record cần có

1. Decision/requirement và risk scenario.
2. Affected assets, flows, environments và tenants.
3. Existing controls có bằng chứng.
4. Reason không thể xử lý ngay và các phương án đã cân nhắc.
5. Compensating controls, owner và cách kiểm chứng.
6. Risk owner, approval, expiry/review date.
7. Trigger để rút acceptance.
8. Retest criteria và target state.

Risk acceptance **không tự làm một yêu cầu bắt buộc biến mất**. Nếu có nghĩa vụ pháp lý, hợp đồng hoặc baseline bắt buộc, cần xử lý theo cơ chế có thẩm quyền và tư vấn phù hợp.

## 36. Anti-patterns khi ra quyết định kiến trúc

| Anti-pattern | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| **HiPPO decision** – chọn theo ý kiến người có chức vụ cao nhất. | Bỏ qua evidence và rủi ro. | Ghi drivers, options, rationale và review có căn cứ. |
| **Technology-first** – chọn sản phẩm trước khi hiểu vấn đề. | Công nghệ không giải quyết đúng requirement. | Bắt đầu từ context và quality attributes. |
| **One-option ADR** – chỉ ghi phương án đã chọn. | Không biết trade-offs hoặc phương án thay thế. | Ghi options thực tế và rejected reasons. |
| **Security theater** – dùng tên control nhưng không xác định threat. | Cảm giác an toàn giả. | Map threat→requirement→control→test. |
| **Unbounded exception** – chấp nhận rủi ro không có expiry. | Risk tồn tại vô thời hạn. | Scope, owner, expiry, review trigger. |
| **Architecture by diagram only** | Sơ đồ không phản ánh runtime. | Đối chiếu code, IaC, config và telemetry. |
| **Score manipulation** | Trọng số/điểm được chỉnh để hợp thức hóa phương án. | Định nghĩa rubric trước và giữ evidence. |
| **No rejected alternatives** | Lặp tranh luận và quên điều kiện cũ. | Lưu rationale và trigger đánh giá lại. |
| **ADR as approval stamp** | Chữ ký bị hiểu là control đã triển khai. | Tách decision acceptance và implementation verification. |
| **Big design up front** | Trì hoãn học hỏi và khóa chặt lựa chọn. | Prototype/time-boxed experiments và decision timing. |
| **No owner** | Không ai duy trì controls/assumptions. | Chỉ định decision, implementation và risk owners. |
| **No superseding record** | Lịch sử bị mất, rationale không truy được. | Tạo ADR mới, link và giữ decision cũ. |
| **Ignoring operational capacity** | Kiến trúc tốt trên giấy nhưng vận hành sai. | Review skill, on-call, automation, runbook và cost. |
| **Averaging away critical risk** | Một lỗi nghiêm trọng bị che bởi nhiều tiêu chí tốt. | Dùng mandatory gates và risk-based decisions. |

## 37. Checklist trước khi chấp nhận một Architecture Decision

1. **Problem:** vấn đề và lý do cần quyết định có rõ?
2. **Context:** hệ thống, actors, data, flows, constraints và dependencies được mô tả?
3. **Drivers:** security, privacy, availability, performance, cost và operability có thứ tự ưu tiên?
4. **Threats:** attacker capabilities, trust boundaries và abuse cases đã được xem?
5. **Requirements:** mục tiêu có testable criteria, owner và traceability?
6. **Options:** có các phương án khả thi, rejected alternatives và baseline/no-change?
7. **Fair comparison:** các option được so trên cùng drivers và evidence?
8. **Trade-offs:** consequences, blast radius, migration, lock-in và operational burden rõ?
9. **Reversibility:** có rollback, export, exit strategy và decision timing phù hợp?
10. **Controls:** mỗi risk quan trọng có control, owner, failure behavior?
11. **Verification:** positive/negative/failure tests và evidence plan?
12. **Governance:** proposer, reviewer, approver và risk owner đúng thẩm quyền?
13. **Assumptions:** điều chưa xác minh có owner và deadline?
14. **Residual risk:** current/target/accepted risk được phân biệt?
15. **Implementation:** có release linkage, migration plan và runtime verification?
16. **Lifecycle:** ADR có status, references, superseding link và reassessment triggers?

## 38. Bài tập tình huống và gợi ý giải

### Bài tập A — Chọn database theo benchmark

Đội chọn database X vì benchmark nội bộ nhanh hơn 30%, nhưng không đánh giá backup, tenant isolation, data export và năng lực vận hành.

**Gợi ý:** Bổ sung workload profile, consistency, data classification, isolation threat model, backup/restore, key management, migration và operator skills. Benchmark cần tái lập trên workload gần production; không dùng một con số duy nhất thay quyết định đa tiêu chí.

### Bài tập B — Chọn shared schema để giảm chi phí

SaaS dùng một bảng chung với tenant identifier. Không có test cho worker, cache và export.

**Gợi ý:** Ghi rationale chi phí nhưng phân tích blast radius; tenant context phải được tin cậy từ server, scoping ở API/repository/worker, cache/search/export, DB policy khi phù hợp và negative tests. Nếu không chứng minh được yêu cầu isolation, phương án chưa đủ cơ sở chấp nhận.

### Bài tập C — Dùng service mesh để giải quyết mọi authorization

Đội tin mTLS trong mesh nghĩa là service A có thể gọi service B và được đọc mọi dữ liệu.

**Gợi ý:** mTLS xác thực workload/kênh theo trust configuration; authorization nghiệp vụ và tenant/resource scope vẫn cần. ADR phải tách network identity khỏi permission, kiểm tra service policy, application authz và failure mode.

### Bài tập D — Chọn vendor không có exit plan

Một dịch vụ managed lưu dữ liệu và key theo format riêng. Đội chọn vì triển khai nhanh nhưng chưa đánh giá export, migration và key portability.

**Gợi ý:** Xem lock-in, data export, format/version, key ownership, recovery, contract, region và termination. Tạo prototype export/restore và exit strategy trước khi đưa dữ liệu quan trọng vào.

### Bài tập E — ADR ghi accepted nhưng chưa triển khai

Architecture board đã duyệt ADR yêu cầu mọi download có authorization, nhưng release chưa có negative tests.

**Gợi ý:** Decision accepted không đồng nghĩa implementation verified. Giữ trạng thái điều kiện/pending evidence; hoàn tất control, test wrong principal/tenant/expired link, đối chiếu runtime trước khi kết luận assurance.

### Bài tập F — Rejected option không được ghi

Một năm sau, team khác đề xuất database per tenant và không biết phương án này từng bị loại do backup cost và quota.

**Gợi ý:** ADR cần ghi rejected options, rationale, evidence và trigger xem lại. Điều kiện hiện tại có thể đã khác; không bác bỏ phương án cũ chỉ vì quyết định trước đây.

### Bài tập G — Risk acceptance vô thời hạn

Một legacy service dùng HTTP nội bộ. Risk owner ký chấp nhận nhưng không có compensating controls, owner kỹ thuật hoặc ngày review.

**Gợi ý:** Acceptance không đầy đủ. Cần xác định data/threat/segment, đánh giá TLS hoặc control thay thế, scope và expiry, monitoring, owner, migration plan và retest. Nếu yêu cầu bắt buộc không cho phép ngoại lệ, cần escalation.

### Bài tập H — Một scorecard che critical failure

Phương án có điểm trung bình cao nhưng không đáp ứng yêu cầu phục hồi dữ liệu đã được phê duyệt.

**Gợi ý:** Mandatory requirement là gate, không được bù bằng cost/performance. Cần loại phương án hoặc thiết kế bổ sung; chỉ chấp nhận ngoại lệ nếu đúng thẩm quyền và không vi phạm nghĩa vụ bắt buộc.

### Bài tập I — Context thay đổi nhưng ADR cũ vẫn được dùng

ADR chọn shared database cho 50 tenants. Hệ thống nay phục vụ 5.000 tenants và có khách hàng yêu cầu dedicated region.

**Gợi ý:** Decision drivers và assumptions đã đổi. Kích hoạt reassessment, đo capacity/cost/isolation, xem tiering hoặc migration, ghi ADR mới và liên kết ADR cũ.

### Bài tập J — Event-driven được chọn nhưng không ai sở hữu DLQ

ADR mô tả broker và worker, nhưng không chỉ định ai được replay/purge dead-letter messages có dữ liệu khách hàng.

**Gợi ý:** Decision chưa hoàn chỉnh về operability, data lifecycle và authorization. Xác định owner, purpose, ACL, retention, replay approval, idempotency, audit, redaction và deletion evidence.

## Kết luận

**Architecture decision** là lựa chọn có chủ đích giữa các phương án kiến trúc dựa trên bối cảnh, mục tiêu, constraints, threats và trade-offs. Một quyết định có chất lượng cần ghi rõ **vấn đề, drivers, options, rationale, consequences, security/privacy impact, owner, controls, verification, residual risk và trigger đánh giá lại**. ADR giữ lại lịch sử và lý do để người khác có thể hiểu, kiểm tra và thay thế quyết định khi điều kiện đổi. Trong **SECURITY_SECURITY_ASSURANCE**, giá trị của quyết định nằm ở khả năng nối lựa chọn kiến trúc với security requirements, controls, tests và evidence; một ADR được chấp nhận chưa chứng minh implementation đã đạt. **Chỉ kết luận quyết định được bảo đảm khi phương án đã chọn được kiểm chứng trong phạm vi và thời kỳ rõ ràng, các giả định được quản trị và rủi ro còn lại có chủ sở hữu**.
