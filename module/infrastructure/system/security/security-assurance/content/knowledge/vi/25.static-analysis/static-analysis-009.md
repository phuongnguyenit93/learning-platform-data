# Rà soát kết quả scan trong Static Analysis và Security Assurance

## 1. Vì sao cần rà soát kết quả scan?

Một dịch vụ Java/Spring của nền tảng Invoice SaaS được phân tích tĩnh trong CI/CD. Dashboard xuất hiện 167 findings: 12 Critical, 25 High, 60 Medium và 70 Low. Đội phát triển muốn xử lý hết Critical trước khi phát hành, nhưng khi mở các finding, một số liên quan mã test không được đóng gói, một số trùng cùng một đường dữ liệu, một số là nguy cơ thật trên API production, và có các cảnh báo được gắn Low nhưng nằm trong chức năng xuất dữ liệu nhiều tenant.

Nếu chỉ lấy số lượng hoặc nhãn severity làm quyết định, tổ chức có thể **lãng phí nguồn lực cho cảnh báo không áp dụng**, đồng thời **bỏ sót lỗ hổng ảnh hưởng dữ liệu quan trọng**. Một pipeline xanh cũng có thể gây hiểu nhầm nếu scanner không quét thư mục mới, bỏ sót branch, dùng ruleset đã bị tắt hoặc không báo khi bước scan lỗi.

**Rà soát kết quả scan** là hoạt động kiểm tra có cấu trúc các findings và chất lượng của chính lần quét nhằm quyết định:

1. **Công cụ đã kiểm tra cái gì?** Phạm vi, phiên bản, nguồn mã, cấu hình, ruleset, cách thu kết quả và trạng thái công cụ.
2. **Finding mô tả điều gì?** Code location, data flow, taint source, sink, control hoặc security invariant liên quan.
3. **Finding có đúng và áp dụng được không?** True positive, false positive, needs investigation, not applicable hoặc duplicate, với lý do và evidence.
4. **Rủi ro thực tế là gì?** Attacker prerequisites, accessibility, business impact, existing controls và uncertainty.
5. **Ai xử lý, kiểm chứng và quyết định?** Owner, remediation, review, test, residual risk, exception và deadlines.
6. **Kết quả được phép hỗ trợ kết luận assurance nào?** Phải giới hạn theo commit, artifact, rule coverage, môi trường và thời kỳ.

Trong **SECURITY_SECURITY_ASSURANCE**, một báo cáo scan không chỉ là danh sách lỗi. Nó là **đầu vào có độ tin cậy cần được đánh giá** để xây dựng bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật thông qua phân tích rủi ro, kiểm soát, kiểm thử, audit và khắc phục liên tục.

> Phát hiện của scanner là một **giả thuyết có căn cứ về lỗi hoặc pattern nguy hiểm**, không tự động là bằng chứng đã có exploit; và không có finding cũng không tự động chứng minh code an toàn.

## 2. Phân biệt các loại static scan

Trong nhiều hệ thống, một pipeline có thể gọi nhiều công cụ là “static analysis” dù phương pháp và mức độ kết luận khác nhau.

| Loại phân tích | Đối tượng | Kết quả thường có | Không tự chứng minh |
| --- | --- | --- | --- |
| **SAST** (Static Application Security Testing) | Source/bytecode, control/data flow, API usage. | SQL injection, XSS, command injection, hardcoded secrets, unsafe APIs, authorization patterns. | Mọi vulnerability runtime hoặc exploitability đã được xác minh. |
| **SCA** (Software Composition Analysis) | Manifest, dependency resolution, SBOM/artifacts. | Vulnerable dependencies, license/composition facts. | Component có reachable vulnerable path trong runtime. |
| **Secrets scanning** | Source, commit history, configs và artifacts trong scope. | Candidate credentials, tokens, keys. | Secret vẫn active, có quyền, hoặc đã bị lạm dụng. |
| **IaC/static configuration** | Terraform, Kubernetes manifests, cloud policies. | Public exposure, broad IAM, missing encryption, insecure defaults. | Effective cloud runtime đúng như source khai báo. |
| **Container/image scan** | Image layers, OS packages, language components, metadata. | Package vulnerabilities, malware indicators theo tool. | Image đó đang chạy hoặc đã vá trên mọi nodes. |
| **Code quality linter** | Syntax/style/maintainability. | Dead code, style, unsafe constructs nếu rules có. | Bao phủ yêu cầu security assurance. |
| **Custom policy-as-code** | Repository/configuration conventions. | Vi phạm baseline của tổ chức. | Baseline đầy đủ và không có bypass. |

**Trọng tâm bài là review findings từ static application analysis (SAST)**, đồng thời minh họa cách liên kết với SCA, secrets và IaC khi một issue đi qua nhiều tầng. Tên một product hay màu dashboard không thay thế việc mô tả **scanner type, ruleset, coverage và evidence**.

## 3. Mục tiêu review: đúng, đủ, có ưu tiên và có thể kiểm chứng

Một hoạt động review tốt tạo ra các đầu ra sau:

- **Scan quality assessment:** xác nhận scanner đã chạy thành công trên đúng source/branch/commit/artifact và ruleset phù hợp.
- **Finding register được chuẩn hóa:** identifiers, rule, location, flow, severity, confidence và source metadata.
- **Triage decision:** true positive, false positive, duplicate, not applicable, needs investigation hoặc risk accepted, kèm lý do.
- **Risk and business mapping:** affected asset, endpoint/action, data classification, tenant/identity context, exploit prerequisites.
- **Ownership:** nhóm sửa code, platform/infra nếu liên quan, business/risk owner và independent reviewer khi cần.
- **Fix plan:** source changes, controls, dependencies, tests, rollout và exception/compensating controls.
- **Retest evidence:** scan lại đúng commit/artifact, regression/negative tests và runtime validation khi phù hợp.
- **Assurance report:** phạm vi, findings chưa xử lý, known unknowns, chất lượng bằng chứng và kết luận có giới hạn.

### Review không phải xóa cảnh báo cho dashboard đẹp

Một finding được đánh dấu False Positive phải có **lập luận kỹ thuật và evidence**, không phải vì team không muốn sửa. Một issue “Won't Fix” có thể là **risk acceptance/exception** nhưng không phải bằng chứng control PASS. Và một issue biến mất khỏi scan mới có thể do rule bị tắt hoặc file không còn được quét, không nhất thiết do code đã an toàn.

## 4. Vòng đời từ scan tới quyết định assurance

~~~mermaid
flowchart TD
    A["Source / commit / artifact + scanner configuration"] --> B["Static scan execution"]
    B --> C{"Scan successful and scope complete?"}
    C -- "No / unknown" --> D["Scan quality finding and rerun / repair"]
    D --> B
    C -- "Yes" --> E["Normalize, fingerprint and correlate findings"]
    E --> F["Review source-to-sink flow and security context"]
    F --> G{"Disposition"}
    G -- "Confirmed / actionable" --> H["Risk, priority, owner and remediation"]
    G -- "False positive / duplicate / N-A" --> I["Evidence-backed rationale and approval"]
    G -- "Uncertain" --> J["Investigation / targeted tests / owner"]
    J --> F
    H --> K["Fix and build approved artifact"]
    K --> L["Rescan + security negative tests"]
    L --> M{"Effective result verified?"}
    M -- "No" --> H
    M -- "Yes" --> N["Time-scoped closure and assurance record"]
    I --> N
    N --> O["Monitor changes, new rules and regressions"]
    O --> A
~~~

Hai điểm **quality gate** quan trọng: kiểm tra **lần scan có hợp lệ** trước khi tin findings; và kiểm tra **remediation thực sự có hiệu lực** trước khi đóng. Không được bỏ một trong hai.

## 5. Input cần thu trước khi review

| Input | Nội dung | Tác dụng |
| --- | --- | --- |
| **Repository/commit identity** | Repo, exact commit SHA, branch, tag/PR, build ID. | Tránh review findings trên source khác production. |
| **Scanner configuration** | Tool/build/rule version, enabled categories, exclusions, custom rules. | Đánh giá kết quả và missing coverage. |
| **Execution metadata** | Start/end time, exit result, failures, timeout, partial scan. | Xác nhận report có đáng tin. |
| **Scan scope** | Paths/modules/languages, generated code, dependency scope. | Xác định file được/không được phân tích. |
| **Findings metadata** | Rule ID, fingerprint, file/line, flow, confidence, severity, message. | Correlation và triage. |
| **Architecture/DFD** | Entry points, trust boundaries, services, data stores, API contracts. | Đánh giá reachability/exploitability. |
| **Security requirements** | AuthN/AuthZ, validation, logging, confidentiality, privacy. | Đặt kỳ vọng cần chứng minh. |
| **Asset/data classification** | Environment, criticality, tenant scope, data type. | Đánh giá impact. |
| **Existing controls** | Middleware, policy engine, query scoping, egress, monitoring. | Kiểm tra mitigation thực, tránh giả định. |
| **Baseline/previous scan** | Findings mới, còn tồn tại, tái xuất hiện hoặc đóng. | Phát hiện regressions và measurement drift. |
| **Tests/release evidence** | Unit, integration, security negative, deploy manifest, runtime state. | Đóng finding với bằng chứng, không chỉ status. |

### Bắt đầu bằng bốn câu hỏi

“Report thuộc commit nào?”, “Có phần nào không được scan?”, “Rule set có khác kỳ trước?”, “Kết quả scan có lỗi/partial không?”. Nếu không trả lời, review severity từng dòng có thể tạo **độ chính xác giả**.

## 6. Kiểm tra completeness và sức khỏe của lần scan

Scanner có thể trả thành công nhưng không phân tích được toàn bộ code vì build context, dependencies, unsupported language, config exclusions hoặc runtime constraints.

### Những điểm cần xem

1. **Exit code và job result:** scan bị cancel, timeout hay fail nhưng pipeline dùng continue-on-error?
2. **Source snapshot:** scanner chạy source nào? Có thay đổi sau scan trước khi merge/deploy?
3. **Full vs incremental:** phạm vi incremental chỉ đủ cho PR diff hay cần full baseline?
4. **Language/framework support:** rules cho Java/Spring, Kotlin, SQL templates và config có hỗ trợ phiên bản thực?
5. **Cross-module analysis:** xử lý được flow qua controller→service→repository hoặc qua modules?
6. **Generated code/binaries:** phần exclude có thực sự an toàn để bỏ hay chứa logic cần review?
7. **Scan configuration drift:** custom rules, severity overrides, suppressions hoặc exclusions thay đổi?
8. **Dependencies/build:** mất dependencies làm semantic analysis yếu hơn hay không?
9. **Report ingestion:** upload SARIF/report thành công, không bị truncate, mapping đúng project?
10. **Source health:** telemetry/scan result có timestamp, count, coverage và errors tương ứng?

### Không có findings là một kết quả cần ngữ cảnh

“0 findings” có thể là code thực sự không kích hoạt rules trong scope. Nó cũng có thể là scanner bị tắt, folder mới không nằm trong inclusion, ruleset không có Java security checks hoặc report ingest lỗi. **Không suy an toàn khi chưa xác minh scanner health/scope**.

### Ví dụ control cho pipeline

Nếu tool hỗ trợ partial results, policy phải quyết định **fail/unknown** cho critical modules thay vì vẫn publish PASS. Một scan thành công trên repo chỉ chứa test utilities không được coi thay cho production service analysis.

## 7. Baseline: phát hiện mới khác tồn tại từ trước

Nhiều hệ thống dùng **baseline** để phân biệt findings đã biết và findings mới xuất hiện trong pull request. Đây là cách quản lý noise, nhưng có rủi ro nếu baseline trở thành nơi che mọi lỗi cũ.

| Loại | Ý nghĩa | Hành động |
| --- | --- | --- |
| **New** | Finding xuất hiện ở code mới/scan mới theo correlation. | Triage sớm, kiểm tra gate policy. |
| **Existing/open** | Đã biết nhưng chưa khắc phục. | Rà owner, SLA, risk, evidence freshness. |
| **Reopened/regressed** | Từng closed nay xuất hiện lại hoặc đường mới tương tự. | Điều tra regression và test gaps. |
| **Resolved-by-change** | Không còn xuất hiện do sửa code/deploy. | Verify đúng fix/coverage, không tự đóng. |
| **Removed by scope/rule change** | Finding biến mất vì exclude/rule shift. | Đánh giá scan gap, không ghi security fixed. |
| **Accepted exception** | Tồn tại với authority/time-bound approval. | Monitor expiry/threat changes và retest. |

### Baseline là quản trị nợ, không phải bằng chứng an toàn

Một codebase có 300 existing findings và CI “no new High” PASS không chứng minh sản phẩm không có High-risk issues. Báo cáo cần tách **new-code gate** khỏi **total open exposure và aging**.

## 8. Anatomy: một finding tĩnh gồm những gì?

Một finding hữu ích thường có:

- **Finding ID / rule ID / category:** mô tả pattern hoặc security property.
- **Location:** file, line/range, symbol, component; có thể thay đổi khi format code.
- **Primary location và related locations:** source/sink/sanitizer/call chain nếu tool hỗ trợ.
- **Message:** điều kiện hoặc lý do scanner thấy nguy cơ.
- **Severity/confidence/precision:** tùy tool; không tự là risk rating của tổ chức.
- **Data flow path:** nguồn input, transformations, validation, sink.
- **Fingerprint/partial fingerprint:** giúp gắn finding qua lần scan.
- **Tool/version/rule config:** quyết định phát hiện thay đổi theo thời gian.
- **First/last seen:** lịch sử và status.
- **Disposition/owner/evidence refs:** kết quả triage, người chịu trách nhiệm.

### Khác nhau giữa finding và issue

Nhiều findings có thể cùng một **root cause**; một finding có thể ảnh hưởng nhiều endpoints. Cần có **raw findings**, **correlated issues**, và **remediation actions** riêng thay vì ép tỷ lệ 1:1.

### Không tin line number là identity vĩnh viễn

Khi thêm một đoạn code phía trên, finding chuyển từ dòng 80 sang 95. Nếu chỉ dựa file:line, có thể xem sai thành issue mới hoặc tưởng đã sửa. Dùng fingerprint, rule, symbol, source/sink semantics và version context.

## 9. Data flow và taint analysis: đọc đường từ nguồn tới sink

Nhiều cảnh báo SAST quan trọng dựa trên **taint/data flow**: một giá trị từ nguồn chưa tin cậy đi qua các phép xử lý rồi tới thao tác nhạy cảm.

### Các thuật ngữ cốt lõi

- **Source:** nơi dữ liệu chưa tin cậy đi vào, chẳng hạn HTTP query/body, event payload, request header, file, webhook, DB record do attacker ảnh hưởng.
- **Propagation:** các phép gán, truyền tham số, transform hoặc serialization đưa giá trị đi tiếp.
- **Sanitizer/validator:** bước giới hạn hoặc xử lý input **đúng ngữ cảnh** để ngăn vấn đề tại sink.
- **Sink:** thao tác rủi ro, như SQL execution, OS command, HTML rendering, file path resolution, SSRF-capable network request.
- **Trust boundary:** nơi dữ liệu đổi từ nguồn ít tin sang hành động có quyền cao.
- **Control/data dependence:** các điều kiện if/authorization/validation ảnh hưởng việc đến sink.

~~~mermaid
flowchart LR
    U["Untrusted request parameter"] --> C["Controller"]
    C --> S["Service and transformations"]
    S --> V{"Context-correct validation / authorization?"}
    V -- "Absent or bypassable" --> Q["Sensitive sink: DB, file, network, output"]
    V -- "Effective" --> SAFE["Constrained, authorized operation"]
    Q --> I["Potential security impact"]
~~~

### Reviewer cần tái dựng đường đi

1. Source có attacker-controlled thật không, và attacker cần loại quyền gì?
2. Giá trị có được thay bằng server-trusted value hay vẫn đi qua?
3. Sanitization có **phù hợp sink** hay chỉ regex chung chung?
4. Có authorization check đúng **principal, action, resource** không?
5. Có những code paths khác đi tới cùng sink và bypass control không?
6. Sink thực sự hoạt động ở environment/runtime nào?
7. Test nào có thể **bác bỏ hoặc xác nhận** threat ở đúng boundary?

### Không đánh đồng parsing với validation

Parse UUID thành công chỉ chứng minh định dạng, không chứng minh UUID thuộc tenant của user. HTML escaping không tự làm SQL parameterization; URL allowlist không tự bảo vệ command injection. **Control đúng phải phù hợp loại sink và attacker objective**.

## 10. Static analysis thiếu gì khi flow đi qua hệ phân tán?

Một SAST trên repository của Invoice API có thể thấy controller gọi message queue nhưng không thấy code worker ở repository khác. Nếu user-controlled tenantId đi vào job, scanner có thể không nối được tới database query ở worker.

### Cross-service threat

~~~mermaid
sequenceDiagram
    participant A as Tenant A user
    participant API as Invoice API
    participant Q as Job broker
    participant W as Export worker
    participant DB as Shared tenant database
    A->>API: Request export with invoice B ID
    API->>Q: Enqueue job (tenant context)
    Q->>W: Deliver serialized job
    W->>DB: Read invoice rows
    DB-->>W: Result
    Note over API,W: Static scan limited to API repo may miss full authorization path
~~~

### Kết luận đúng

SAST có thể phát hiện source→sink trong một codebase, nhưng **service contracts, queue identity, runtime permissions, API and object authorization** còn cần design review, cross-repo analysis, integration tests và effective policy evidence.

Không chấm “False Positive” chỉ vì scanner không chứng minh exploit end-to-end; cũng không tuyên bố toàn bộ attack path đã được xác nhận khi chỉ thấy untrusted field đi vào message constructor.

## 11. Bốn trạng thái nhận định cốt lõi

| Disposition | Nghĩa | Evidence cần có |
| --- | --- | --- |
| **Confirmed true positive** | Có đường hoặc vi phạm coding/security invariant áp dụng, đủ căn cứ xác nhận finding. | Code/data flow, relevant config, tests/requirements. |
| **False positive** | Trong đúng code/flow/scope, scanner suy ra pattern nguy hiểm nhưng điều kiện tạo lỗi không xảy ra. | Cụ thể control/branch/typed API khiến đường không khả thi, reviewer sign-off. |
| **Not applicable** | Finding không áp dụng với artifact/asset/version/environment của claim, có cơ sở scope. | Deployment/packaging/provenance và rationale. |
| **Needs investigation / inconclusive** | Thiếu thông tin để quyết định đúng/sai hoặc impact. | Open questions, owner, evidence plan, thời hạn. |

Các trạng thái vận hành bổ sung gồm **duplicate**, **fixed pending verification**, **risk accepted**, **remediated and verified**, **reopened**. Không ép “risk accepted” vào nhóm false positive vì nó vẫn có thể là vấn đề thật.

### Hạn chế của cách chia nhị phân

Một SAST finding có thể mô tả một **unsafe coding pattern** mà không có external exploitability hiện tại. Nó có thể vẫn vi phạm secure-coding baseline, đáng sửa để chống future changes, dù không gắn nhãn “actively exploitable production bug”. Triage phải ghi **issue type, scope, risk và treatment** thay vì chỉ chọn “true/false”.

## 12. Khi nào được kết luận False Positive?

Một false positive hợp lý cần chỉ rõ **chính giả định nào của scanner sai**, chẳng hạn:

- Giá trị “untrusted input” thực tế chỉ được tạo từ allowlisted server-owned enum và không có đường external write.
- Chuỗi SQL động scanner nghi ngờ là query text nhưng thực ra được chuyển sang parameterized query với placeholder ở đúng API.
- Sink nằm trong test fixture không đóng gói vào artifact/runtime đang đánh giá và scope không yêu cầu test code control đó.
- Đường xử lý nằm trong code dead theo control flow đã xác minh; lưu ý build flags/reflective calls có thể làm phân tích khó.
- Sanitizer/encoder được áp dụng đúng output context và không có bypass path.

### Điều **không đủ** để đánh dấu FP

- “Chưa ai khai thác.”
- “Người dùng phải đăng nhập.”
- “File này ít thay đổi.”
- “Đã có WAF/MFA”, nếu control không ngăn source→sink.
- “Scan tools thường hay báo sai.”
- “Code reviewer nghĩ chắc không tới được.”
- “Severity do scanner gán Low.”

FP disposition phải có **scope, code/config reference, rationale, owner, reviewer và điều kiện phải review lại** nếu source/path/callers thay đổi.

## 13. False Negative và những gì scanner không nhìn thấy

**False negative** là lỗi thật/vi phạm yêu cầu thuộc scope mà scanner không báo. Nó khó đo trực tiếp vì không biết toàn bộ lỗi thật trong hệ thống.

### Nguồn FN phổ biến

- Unsupported language/framework/custom DSL và code generation.
- Cross-repo, multi-service hoặc async data flows.
- Dynamic dispatch, reflection, native libraries, framework magic.
- Insufficient modeling of custom sanitizers, security wrappers, serializers.
- Business authorization/tenant logic không được biểu đạt bằng rule.
- Config/feature flags/runtime policies ngoài source.
- Scanner exclusions, partial runs, missing build semantic information.
- Ruleset không có pattern cho threat cụ thể.

### Không nên diễn giải “FN rate = 0”

Vì không thấy lỗ hổng không có nghĩa không có FN. Có thể dùng **seeded test fixtures, benchmark code, adversarial tests, independent code review, penetration testing, incident feedback và correlation với DAST/IaC/runtime** để ước lượng coverage trong scope.

### Assurance argument

Một kết luận đúng là “SAST đạt coverage đã định nghĩa đối với rule categories/languages và positive/negative controls được thử trong release R”, không phải “ứng dụng không có vulnerability”.

## 14. Dedupe và grouping: giảm noise nhưng không che impact

Ví dụ cùng một insecure helper sinh 20 findings tại nhiều call sites. Có thể nhóm thành một **root-cause remediation** nhưng vẫn phải giữ các **affected paths/assets**, bởi vì một đường có internet exposure và một đường chỉ nội bộ có risk khác nhau.

### Quy trình correlation

1. Chuẩn hóa rule/category và stable fingerprint.
2. Xác định source/sink, method/symbol và call chain.
3. So sánh code hash/commit/module/release.
4. Tìm shared root cause (helper/configuration/common dependency).
5. Giữ danh sách **all affected locations and business scopes**.
6. Chỉ kết luận closure khi **tất cả occurrences cần sửa** đã verified.

### Hai lỗi hay gặp

- **Under-dedup:** cùng issue báo nhiều lần, làm phồng backlog/metrics.
- **Over-dedup:** gom findings khác nhau chỉ vì cùng rule/file, vô tình bỏ lộ một critical path chưa fix.

### Findings xuyên phiên bản

Một finding có thể chuyển dòng, module hoặc fingerprint khi refactor. Nếu matcher thay, đừng auto-close mọi issue cũ: review **change in scan scope/rules và actual fix evidence**.

## 15. Phân biệt scanner severity, confidence và risk priority

| Dimension | Ý nghĩa | Nguồn/điều cần cân nhắc |
| --- | --- | --- |
| **Rule severity** | Mức nghiêm trọng mặc định của pattern/coding issue. | Tool/rule metadata; không hiểu hết business context. |
| **Confidence/precision** | Độ chắc chắn detector báo pattern đúng. | Rule model, data flow, known FPs. |
| **Exploitability/reachability** | Attacker có thể kích hoạt trong assumptions nào? | Entry points, authentication, prerequisites, runtime paths. |
| **Business impact** | Mất gì nếu exploit? | Confidentiality/integrity/availability, data/tenant scope. |
| **Existing controls** | Control nào thực thi, có bypass không? | Code, config, effective policy, tests/telemetry. |
| **Current residual risk** | Rủi ro với controls hiện đang hoạt động. | Risk methodology, uncertainty. |
| **Remediation priority** | Thứ tự/timeline xử lý theo chương trình. | Risk, SLA, exploit signals, dependencies, business constraints. |

### Ví dụ

Một rule SQL injection ở test utility không đóng gói production có thể có severity mặc định High nhưng low production applicability. Một rule Missing Authorization ở export API có thể được scanner xếp Medium do không hiểu dữ liệu nhiều tenant, nhưng **cross-tenant Confidential data impact** khiến review risk cao hơn.

**Priority phải dựa trên threat, affected assets, deployment và evidence**, không chỉ đổi nhãn cho khớp SLA.

## 16. Quy trình triage một finding theo thứ tự có thể lặp lại

Một reviewer có thể xử lý từng finding bằng trình tự:

1. **Verify scan:** rule, commit, file/module, parser support, scan status và report provenance.
2. **Understand rule:** security property nào có thể vi phạm? Source/sink và assumptions của analyzer là gì?
3. **Trace flow:** đọc call sites, validators, trust boundaries và code branches; mở rộng ra contracts/runtime nếu cần.
4. **Determine applicability:** code có build/deploy/run trong scope? Dependencies, feature flags, endpoint accessibility?
5. **Assess controls:** control hiện có được đặt đúng sink/boundary và hoạt động không?
6. **Set disposition:** confirmed, false positive, not applicable, duplicate hoặc needs investigation; cung cấp lý do.
7. **Evaluate risk:** attacker capability, asset/data, impact, blast radius, uncertainty và compensating controls.
8. **Plan action:** code fix, design change, control, exception, owner, timeline và test.
9. **Verify remediation:** build/scan lại đúng artifact, targeted security test, runtime/CI evidence.
10. **Close or monitor:** ghi decision, reviewer, evidence IDs, residual risk và reopen triggers.

### Decision tree khái niệm

~~~mermaid
flowchart TD
    A["Scanner finding from commit R"] --> B{"Scan valid and relevant?"}
    B -- "No / unknown" --> C["Repair scan / investigate coverage"]
    B -- "Yes" --> D{"Same root cause as verified issue?"}
    D -- "Yes" --> E["Link duplicate, preserve affected path"]
    D -- "No" --> F["Review source, sink and security contract"]
    F --> G{"Finding applies to deployed path?"}
    G -- "No, evidenced" --> H["Not applicable / FP with rationale"]
    G -- "Unknown" --> I["Evidence task and due date"]
    G -- "Yes" --> J{"Security control effective?"}
    J -- "Yes, evidenced" --> K["FP / mitigated disposition as appropriate"]
    J -- "No / inadequate" --> L["Confirmed issue + risk priority"]
    L --> M["Owner fix / exception"]
    M --> N["Rescan, negative tests and deployment verification"]
    N --> O{"Meets acceptance criteria?"}
    O -- "No" --> M
    O -- "Yes" --> P["Evidence-backed closure"]
~~~

**Đừng cắt bỏ nhánh unknown.** Nếu scanner chưa mô hình hóa custom authorization, reviewer chưa đủ cơ sở tuyên bố FP. Ghi lại các câu hỏi và thiết kế test giúp review có thể tái lập.

## 17. Rà soát finding SQL Injection: từ mã tới truy vấn thực

Ví dụ Java/JDBC cố ý minh họa **pattern không an toàn**:

~~~java
// INSECURE EXAMPLE -- do not copy to production.
String query = "SELECT id, tenant_id FROM invoices WHERE invoice_code = '"
        + invoiceCodeFromRequest + "'";
try (Statement statement = connection.createStatement();
     ResultSet rows = statement.executeQuery(query)) {
    // ...
}
~~~

Ở đây input chưa tin cậy được **nối vào SQL syntax**, tạo nguy cơ injection. Scanner có thể thấy source→concatenation→executeQuery. Reviewer cần hỏi liệu code có reachable, input có attacker-controlled, account có quyền truy vấn gì, DB có tenant authorization, và query có chạy ở production hay chỉ là fixture.

### Hướng sửa minh họa

~~~java
// Illustrative safe parameter binding; authorization remains separate.
String query = """
    SELECT id, tenant_id
    FROM invoices
    WHERE invoice_code = ?
      AND tenant_id = ?
    """;
try (PreparedStatement statement =
         connection.prepareStatement(query)) {
    statement.setString(1, invoiceCodeFromRequest);
    statement.setObject(2, verifiedPrincipal.tenantId());
    try (ResultSet rows = statement.executeQuery()) {
        // Map only permitted results.
    }
}
~~~

**Parameter binding** ngăn dữ liệu thay đổi cấu trúc SQL cho values trong vị trí được hỗ trợ. Nó không tự làm tất cả query an toàn: dynamic table/column names phải được giới hạn bằng **trusted allowlist**, và tenantId phải đến từ **verified principal**, không từ query header do client đặt.

### Rà soát test

| Case | Expected |
| --- | --- |
| Input thông thường với mã hóa đơn hợp lệ. | Trả đúng invoice thuộc tenant của principal. |
| Input chứa ký tự có ý nghĩa trong SQL. | Được xử lý như **giá trị**, không đổi cấu trúc query. |
| User A yêu cầu invoice thuộc tenant B. | Không lộ dữ liệu B (authorization kiểm riêng). |
| Input rất dài/khác encoding. | Bị giới hạn/handled theo contract, không crash hoặc leak SQL. |
| Code path gọi query qua helper khác. | Không có concat bypass trên path khác. |

### Thế nào là closure?

Code change + built artifact chứa fix + test expected/observed + SAST readback đúng rule/scope. Nếu finding biến mất vì đã exclude lớp DAO khỏi scan, đó là **coverage regression**, không phải fix.

## 18. Rà soát XSS: encoding phải đúng output context

Một finding Cross-Site Scripting thường báo dữ liệu chưa tin cậy được đưa vào HTML, JavaScript, URL, CSS hoặc DOM API mà không có context-correct encoding.

### Ví dụ

~~~java
// INSECURE EXAMPLE: raw user data embedded in HTML.
String html = "<div class='invoice-note'>" + customerNote + "</div>";
return ResponseEntity.ok()
    .contentType(MediaType.TEXT_HTML)
    .body(html);
~~~

Điểm cần xem: customerNote có thể bị điều khiển? HTML được trình duyệt diễn giải hay chỉ lưu như text? Có template engine escaping mặc định? Nếu output qua nhiều contexts, HTML escaping phù hợp text node không tự phù hợp JavaScript string hoặc CSS.

### Hướng xử lý đúng

- Dùng template/rendering API có **autoescaping đúng context**.
- Tránh tự nối user content thành HTML/JS.
- Nếu hiển thị rich text, dùng sanitizer đáng tin được cấu hình theo allowlist phù hợp, có tests.
- Nếu cập nhật DOM, dùng **textContent** hoặc API không interpret HTML khi chỉ cần text.
- CSP có thể làm defense-in-depth nhưng không thay context-correct output encoding.

### Nhầm lẫn cần tránh

Một “HTML sanitize” tại lúc lưu dữ liệu có thể không bảo vệ khi dữ liệu được dùng trong JS/URL context sau này. Một scanner báo XSS có thể FP nếu framework autoescaping đúng trong ngữ cảnh, nhưng reviewer phải chứng minh **API template thực dùng và no unsafe bypass**, không chỉ nói “Spring đã lo”.

### Negative testing

Dùng dữ liệu kiểm thử không gây hại, chứa các ký tự đặc biệt và chuỗi được thiết kế để kiểm tra context encoding; xác nhận trình duyệt/DOM nhận **text** chứ không tạo executable markup ngoài contract. Không thử payload lên dữ liệu người dùng hoặc domain ngoài scope.

## 19. SSRF: từ external URL tới khả năng gọi mạng có quyền

**Server-Side Request Forgery (SSRF)** thường xuất hiện khi request từ client ảnh hưởng đích của một network call từ server. Scanner có thể thấy input HTTP → HTTP client. Nhưng không phải mọi request có input URL đều nguy hiểm ở cùng mức: còn phụ thuộc destination policy, redirects, DNS, egress, network permissions và data sensitivity.

### Mã minh họa cần review

~~~java
// Risky if user-provided URI controls arbitrary destination.
URI destination = URI.create(callbackUrlFromRequest);
HttpRequest outbound = HttpRequest.newBuilder(destination)
    .GET()
    .build();
HttpResponse<String> response =
    httpClient.send(outbound, HttpResponse.BodyHandlers.ofString());
~~~

### Điều reviewer phải xác minh

1. URL do user/tenant tự cung cấp hay server chọn từ một **registered endpoint catalog**?
2. Allowed schemes, hostname, port, redirect chain và target trust được ràng buộc thế nào?
3. Có DNS rebinding, proxy, IPv4/IPv6 hoặc các cách biểu diễn địa chỉ làm bypass không?
4. Runtime có thể truy cập **metadata/internal admin/private services** hay egress bị giới hạn?
5. HTTP client có tự follow redirects sang destination ngoài allowlist?
6. Response có bị chuyển lại cho attacker, lưu secrets hoặc tạo side effects không?

### Defense-in-depth

Thiết kế dùng **server-approved destination IDs** thay raw URLs khi có thể, xác minh destination ở đúng layer và có network egress restrictions. Chỉ “chặn chuỗi 127.0.0.1” là không đủ để chứng minh SSRF defense cho mọi dạng địa chỉ.

### Test và verdict

Với test destinations giả lập bên trong sandbox, kiểm tra allowed host, forbidden internal routes, cross-scheme redirects và DNS/canonicalization behavior. Nếu scanner không thể biết egress policy, không nên auto-FP; có thể kết luận **code pattern applicable nhưng exploit path bị hạn chế bởi control đã xác minh** và ghi residual risk.

## 20. Path traversal và file access: kiểm tra canonicalization

Finding path traversal có thể xuất hiện khi user-supplied filename đi vào file IO. Kiểm tra string prefix trước normalize có thể không đảm bảo path nằm trong approved directory.

### Mã có risk

~~~java
// Unsafe when fileName is untrusted.
Path destination = exportRoot.resolve(fileNameFromRequest);
Files.readAllBytes(destination);
~~~

### Thiết kế tốt hơn

**Không cho client chọn filesystem path** nếu chức năng chỉ cần download invoice. Tạo server-owned **file reference ID**, lookup metadata với object/tenant authorization, rồi dùng trusted storage key. Khi bắt buộc nhận relative path, normalize/canonicalize với ngữ nghĩa filesystem phù hợp và xử lý symlinks/race, giới hạn thư mục, filesystem permissions và test path variants.

### Reviewer phải phân biệt

- String validation và normalized path containment.
- Path lexical containment và **symlink-resolved real path**.
- Allowed directory và object-level business authorization.
- Filesystem local và object storage key semantics.
- Read permission của service identity và quyền actor thực.

Một sanitizer dùng replace ký tự phân cách đơn giản không tự chứng minh chống traversal. Nếu app truy cập dữ liệu theo server-generated opaque identifiers, cần kiểm tra mapping thực sự không tin path từ client.

## 21. Command injection và insecure process execution

SAST có thể phát hiện input đi vào shell/process APIs. Nguy cơ cao hơn khi dữ liệu người dùng được nối thành shell command; nhưng không phải cứ gọi process là có injection.

### Pattern không an toàn

~~~java
// INSECURE EXAMPLE: shell interpretation of untrusted data.
String shellCommand = "convert " + userFileName + " output.pdf";
new ProcessBuilder("sh", "-c", shellCommand).start();
~~~

### Hướng an toàn hơn

- Tránh shell nếu có library/API thực hiện trực tiếp chức năng.
- Nếu cần process, dùng **fixed executable** và argument list (không tự xây shell command string).
- Validate allowed operations và file references do server quản lý.
- Giới hạn permissions, working directory, resources, timeouts và network/file access.
- Không để attacker chọn executable, flags nguy hiểm hoặc arbitrary file path.

### Reviewer phải nhớ

Argument-list invocation giảm shell parsing risks, nhưng chương trình được gọi vẫn có thể diễn giải flags/arguments đặc biệt. Cần **operation-level allowlist và context-specific handling**; test phải thể hiện đúng subprocess semantics, không chỉ xem API name.

## 22. Unsafe deserialization và serialization format

Một finding insecure deserialization có thể dựa trên việc đọc dữ liệu chưa tin cậy thành arbitrary object hoặc sử dụng cơ chế serialization có thể tạo side effects.

### Câu hỏi đánh giá

- Dữ liệu đến từ user, message broker, internal API hay trusted build artifact?
- Trust boundary được xác minh bằng authentication/message integrity chưa?
- Parser có allowlist types, schema validation và size/depth/resource limits?
- Polymorphic type binding hoặc dynamic class loading có bật?
- Dependency versions có các cơ chế insecure defaults hay gadget surfaces?
- Message được retry/replay/forward qua phiên bản services khác nhau không?

### Ví dụ trong SaaS

Old export worker dùng một generic polymorphic JSON deserializer cho job event. Một update thay library version nhưng không sửa type trust. Reviewer cần xem **source of job message, permitted types, validation, authorization**, tests với malformed/unexpected schemas và resource constraints; không coi mọi JSON deserialize là cùng một vulnerability.

### Patch phải cân nhắc compatibility

Thay default typing/serializer có thể làm old events trong queue không giải mã được. Kết luận remediation phải kiểm tra **security invariant và mixed-version compatibility**, không chỉ sửa một rule.

## 23. Hardcoded secrets và credential exposure

Scanner có thể báo candidate API key/password/token trong source. Cần xử lý thận trọng vì **bản thân việc in secret vào ticket, chat hoặc scan report có thể tạo lộ lọt mới**.

### Những bước triage

1. **Đừng sao chép raw secret** sang báo cáo không an toàn; dùng masked reference hoặc fingerprint không thể dùng làm credential.
2. Kiểm tra pattern là credential thật, sample/dummy/test fixture hay false positive.
3. Xác định secret có từng active, scope/permissions nào, exposed ở branch/tag/history/artifacts nào.
4. Nếu secret thật có thể bị lộ, phối hợp owner để **revoke/rotate** theo incident/credential process; xóa khỏi latest commit không đủ.
5. Sửa code để lấy credential qua trusted secret/identity mechanism, không bake vào source/image.
6. Rà log, build artifacts, packages, forks và history để xác định exposure phạm vi.
7. Test revoked credential không còn sử dụng được và new runtime nhận rotated credential.

### Không chỉ nhìn code fix

Một token đã từng commit vào repository không trở nên an toàn chỉ vì sau đó được thay bằng environment variable. **Lifecycle và khả năng thu hồi hiệu lực** là yếu tố quan trọng. Đồng thời environment variables không phải nơi chứa secret “an toàn tuyệt đối”; phải xét process inspection, logging, permissions và secret delivery.

## 24. Authorization và business logic: cảnh báo nhỏ nhưng impact lớn

SAST thường phát hiện tốt một số injection patterns nhưng khó suy ra **người dùng nào có quyền trên object nào**. Với SaaS nhiều tenant, thiếu authorization có thể nguy hiểm dù không có một sink “unsafe API” rõ ràng.

### Java/Spring example

~~~java
// DANGEROUS DESIGN: authentication alone is not object authorization.
@GetMapping("/api/invoices/{invoiceId}")
public InvoiceDto getInvoice(@PathVariable UUID invoiceId) {
    return invoiceRepository.findById(invoiceId)
        .map(InvoiceDto::from)
        .orElseThrow(() -> new ResponseStatusException(
            HttpStatus.NOT_FOUND));
}
~~~

Nếu method chỉ đòi authenticated session ở filter chain, nó có thể trả invoice thuộc tenant B cho user A. SAST không nhất thiết biết data ownership relation.

### Thiết kế có tenant-scoped access

~~~java
// Illustrative service-layer enforcement; integration tests required.
public InvoiceDto read(
        UUID invoiceId,
        VerifiedPrincipal principal) {
    if (principal == null || principal.tenantId() == null
            || !principal.mayReadInvoices()) {
        throw new AccessDeniedException("Not permitted");
    }
    Invoice invoice = invoiceRepository
        .findByIdAndTenantId(invoiceId, principal.tenantId())
        .orElseThrow(() -> new ResponseStatusException(
            HttpStatus.NOT_FOUND));
    return InvoiceDto.fromAllowedFields(invoice);
}
~~~

**VerifiedPrincipal** phải được tạo từ verified session/token/tenant binding, không được dựng từ tenantId trong HTTP body/query/header do client đặt. Repository phải thực sự dùng tenant-scoped query. Authorization cần kiểm ở **worker, cache, export/download và async paths**, không chỉ controller.

### Negative test quan trọng

Tạo synthetic tenants A/B, accounts có roles khác nhau, và request invoice B bằng user A. Expected **no B data** qua mọi supported endpoint/operation, kể cả file download/worker results. SAST không báo lỗi không đủ để kết luận BOLA đã được ngăn.

## 25. Logging, privacy và thông tin nhạy cảm trong source

Một số findings về logging hoặc data exposure không có injection sink. Chúng có thể cho thấy:

- Raw bearer tokens, session cookies, passwords, OTPs, API keys bị ghi log.
- PII/financial records xuất hiện ở debug/error traces.
- Exception messages tiết lộ SQL queries, internal identifiers hoặc stack traces.
- Audit không ghi security decisions quan trọng hoặc thiếu actor/tenant context.
- Log output có thể bị giả mạo/trộn dòng bởi input chưa xử lý đúng.

### Reviewer cần phân biệt các mục tiêu

**Security logging** cần đủ correlation để điều tra, trong khi **privacy/data minimization** giới hạn loại dữ liệu được lưu. Một rule “log all requests” có thể vi phạm privacy hoặc làm lộ secrets; một rule “never log anything” phá auditability.

### Evidence phù hợp

Code/log schema review, controlled canary events, redaction tests, sink configuration, source-health monitoring và retention/access controls. Không đưa raw secrets vào test expected output. Khi scanner báo một lệnh logger với biến tên password, xác minh **giá trị thực và serialization behavior** trước khi quyết định.

## 26. Kết hợp SAST với SCA, IaC và image/runtime evidence

Một security issue có thể không nằm trong một file source:

| Finding | Scanner type phù hợp | Cần kết hợp evidence |
| --- | --- | --- |
| Java method xây SQL bằng concat | SAST | Runtime call path, tenant authorization, negative tests. |
| Vulnerable transitive library | SCA/SBOM | Resolved version, fixed advisory, deployed artifact digest. |
| Image chứa OS package dễ bị ảnh hưởng | Image scan | Actual image digest đang chạy, vendor backport, restart/rollout. |
| Kubernetes manifest mount secret rộng | IaC | Effective runtime service account, secret access tests. |
| Hardcoded credential ở commit cũ | Secrets scan | Credential validity, revoke/rotate, history/artifact scope. |
| API thiếu object authorization | SAST custom rule/design review | Threat model, cross-tenant integration tests. |
| Public storage policy không an toàn | IaC/cloud posture | Effective cloud policy, external reachability, data scope. |

### CVE/CVSS/KEV/EPSS thuộc ngữ cảnh nào?

CVE/advisory hỗ trợ nhận diện lỗ hổng thành phần; CVSS mô tả characteristics severity theo phương pháp; KEV và EPSS là tín hiệu khai thác theo danh mục/mô hình. Chúng **không phải trường bắt buộc của mọi SAST code finding** và không thay chứng minh đường source→sink. Một custom authorization flaw có thể không có CVE nào.

### Khi scanner sources mâu thuẫn

SAST báo unsafe API usage nhưng integration test không reproduce; không tự dismiss. SCA báo vulnerable package nhưng vendor backport fixed; cần kiểm chứng advisory và build. IaC nói bucket private nhưng cloud effective policy public; runtime evidence có thể bác bỏ design intent. **Ghi contradiction và investigate**, không chỉ chọn report màu xanh nhất.

## 27. Threat model và security requirements định hướng triage

Security assurance phải nối một finding tới **tài sản, nguy cơ và yêu cầu cần đạt**. Ví dụ:

| Threat ID | Security requirement | Finding/test liên quan |
| --- | --- | --- |
| **TH-INJ-01** | User input không được thay đổi SQL syntax ngoài contract. | SAST SQL injection + parameterization regression. |
| **TH-TEN-02** | User chỉ đọc/export objects thuộc tenant được cấp quyền. | BOLA code review, cross-tenant negative tests. |
| **TH-SSR-03** | Backend không gọi arbitrary attacker-selected destinations. | SAST SSRF + controlled egress tests. |
| **TH-SECRET-04** | Production credentials không có trong source/artifacts, có revoke/rotation. | Secrets scan + credential lifecycle evidence. |
| **TH-XSS-05** | Untrusted content không được render thành executable script. | XSS SAST + context output tests. |
| **TH-LOG-06** | Sensitive logs không chứa secrets nhưng events vẫn đủ audit. | Logging rules + canary redaction/source health. |

### Khi không có finding nhưng có requirement quan trọng

Ví dụ business authorization policy yêu cầu **two-person approval** cho hoàn tiền. Scanner không báo lỗi không thay review quy trình, state machine, role conflict và authorization tests. Thiếu rule bao phủ một requirement có thể là **assurance gap**, cần bổ sung custom rule, secure code review hoặc tests.

## 28. Risk-based prioritization: không chạy theo nhãn tool

Một phương pháp triage thực tế có thể xét:

1. **Applicability:** code/artifact nào, runtime release nào, có gọi không?
2. **Entry:** unauthenticated Internet, authenticated tenant, internal service, privileged insider?
3. **Exposure:** route, API, background job, file export, network egress.
4. **Preconditions:** cần quyền/token/insider hay không?
5. **Impact:** Confidential/Restricted data, tenant boundary, finance integrity, availability.
6. **Blast radius:** một request, một tenant, shared multi-tenant, production control plane.
7. **Existing controls:** có hiệu lực theo evidence? Có bypass hoặc common-mode failure?
8. **Uncertainty:** chưa biết điều gì? Có cần containment trong lúc điều tra?
9. **Exploit signals:** incident, security research hoặc confirmed exploit path khi phù hợp.
10. **Remediation dependency:** fix có cần major upgrade, migration, vendor coordination?

### Risk priority và fix order khác nhau

Một finding có thể có **rủi ro cao nhưng bản vá cần nhiều prerequisites**. Có thể phải giảm exposure hoặc tăng monitoring tạm thời, đồng thời triển khai fix. Ngược lại, sửa một Low-risk issue dễ không nên tự động đẩy critical BOLA ra cuối backlog.

### False positive ảnh hưởng metric

Không tính false positives đã xác minh như confirmed open risk; nhưng **nếu review chưa xong** không được xem finding là false positive. Có thể báo tách **raw tool severity**, **reviewed risk tier** và **triage backlog**.

## 29. Một decision record nên chứa gì?

Mỗi finding quan trọng cần được giải thích đủ để reviewer khác hiểu và tái đánh giá sau thay đổi.

| Field | Ý nghĩa |
| --- | --- |
| **Finding ID / rule ID** | Liên kết raw scan và policy/rule. |
| **Fingerprint / location** | Nhận diện qua nhiều lần scan, có source/sink path. |
| **Scan context** | Repo, commit, artifact, tool version, ruleset, timestamp. |
| **Affected asset** | Service/API/module, release, environment, tenant/data context. |
| **Threat/requirement refs** | Vì sao issue quan trọng, policy nào bị vi phạm. |
| **Observed code behavior** | Code path, input validation, existing controls. |
| **Disposition** | Confirmed/FP/N-A/duplicate/uncertain/fixed/exception. |
| **Risk rationale** | Capability, exposure, impact, confidence và known unknowns. |
| **Owner/approver** | Người sửa, người review và risk owner nếu exception. |
| **Remediation plan** | Code/config/design change, dependencies, due date. |
| **Verification plan** | Scan repeat, negative tests, runtime/integration checks. |
| **Evidence refs** | Test run, code diff, deployment/digest, audit. |
| **Expiry/reopen triggers** | Thay ruleset, trust boundary, callers, endpoint, deployment. |

### Mẫu quyết định có ích

“Finding SAST-INV-028 là confirmed SQL injection pattern trong InvoiceQueryService thuộc release R và được gọi từ API GET /invoices/search. Input query đến từ authenticated tenant user, không parameterized trước JDBC execution. Asset phục vụ Confidential multi-tenant data; current severity/risk được đánh giá High theo rubric và cần fix trước gate. Retest gồm parameterization, request with SQL metacharacters, cross-tenant negative test và runtime artifact readback.”

Câu mẫu này mô tả **giả định minh họa**, không phải finding thực. Nó có thể được kiểm chứng vì ghi flow, asset, security requirement và expected tests.

## 30. SARIF và định dạng dữ liệu của kết quả scan

**SARIF (Static Analysis Results Interchange Format)** là một định dạng trao đổi kết quả phân tích tĩnh, hỗ trợ mô tả tool/rules/results/locations và những cấu trúc bổ sung như code flows hoặc fingerprints khi analyzer cung cấp. Nhiều công cụ có định dạng riêng; review pipeline nên chuẩn hóa các trường quan trọng nhưng **không xóa raw source/provenance**.

### Ví dụ SARIF rút gọn minh họa

~~~json
{
  "version": "2.1.0",
  "runs": [
    {
      "tool": {
        "driver": {
          "name": "IllustrativeJavaScanner",
          "version": "example-1",
          "rules": [
            {
              "id": "JAVA-UNSAFE-SQL-CONCAT",
              "name": "Dynamic SQL with untrusted input",
              "shortDescription": {
                "text": "Request input reaches SQL execution"
              }
            }
          ]
        }
      },
      "results": [
        {
          "ruleId": "JAVA-UNSAFE-SQL-CONCAT",
          "level": "error",
          "message": {
            "text": "Review untrusted data reaching SQL execution"
          },
          "locations": [
            {
              "physicalLocation": {
                "artifactLocation": {
                  "uri": "src/main/java/example/InvoiceQueryService.java"
                },
                "region": {
                  "startLine": 42
                }
              }
            }
          ],
          "partialFingerprints": {
            "illustrativeFindingHash": "example-hash-42"
          }
        }
      ]
    }
  ]
}
~~~

Ví dụ chỉ chứa một phần các trường SARIF thường gặp; nó **không phải output của một scanner thật** và không tự mang đầy đủ code-flow trace, automation metadata hay schema link.

### Dùng SARIF đúng cách

- Lưu **raw report** kèm source repository, exact commit, tool version và scan config.
- Chuẩn hóa severity/rule/fingerprint một cách có version, tránh map mọi tool level “error” thành Critical.
- Dùng code flows và locations khi có, nhưng không tự tạo “attacker path confirmed” từ một trace thiếu context.
- Nếu upstream không có fingerprint ổn định, correlation phải lưu confidence và dùng code location/symbol/rule có kiểm soát.
- Không thay finding status thành Fixed chỉ vì một SARIF file không chứa finding trong lần quét sau.
- Giữ đường link đúng commit, không trỏ line number sang branch mới khiến evidence sai.
- Bảo vệ reports nếu chúng chứa source snippets, token-like values hoặc internal architecture.

### Severity semantics không hoàn toàn tương đương

Tools có thể dùng error/warning/note hoặc Critical/High/Medium/Low theo những tiêu chí khác nhau. Một mapping nội bộ cần **documented method**, tool/version và override rationale. Tránh cộng severity như thể mọi scanner dùng cùng rubric.

## 31. Suppression, waiver và exception: ba hành động khác nhau

**Suppression** làm công cụ không hiển thị hoặc không chặn một result theo scope; **waiver/exception** là quyết định quản trị cho requirement/risk chưa được đáp ứng; **false-positive disposition** là nhận định bằng chứng cho thấy pattern không áp dụng hoặc detector sai.

### Phân loại lý do suppression

| Lý do | Có thể hợp lệ không? | Cần bổ sung |
| --- | --- | --- |
| Scanner false positive đã được chứng minh. | Có. | Code-flow rationale, reviewer, reopen triggers. |
| Rule không áp dụng cho test fixture không đóng gói. | Có thể. | Artifact/scope proof, security tests không bị bỏ. |
| Temporary incompatibility với dependency. | Có thể là exception. | Risk, interim controls, owner, expiry và roadmap. |
| Existing debt nằm trong baseline. | Không tự đủ để suppress. | Risk tier, tracking và treatment date. |
| Security issue sẽ được sửa “sau”. | Không đủ. | Explicit change/risk decision và deadline. |
| Không muốn CI fail. | Không. | Sửa cause hoặc thiết kế exception được phê duyệt. |

### Yêu cầu đối với inline suppression

Nếu tool hỗ trợ marker trong source, cần giới hạn **rule ID, code region, justification, ticket, reviewer và expiry/review policy**. Không dùng file-wide wildcard suppression để che các issues mới. Việc suppress cũng là **change bảo mật** và nên được code reviewed.

### Tool-level exclusions

Một folder bị exclude có thể chứa code production do refactor. Review tất cả thay đổi **scanner policy/exclusions/rulesets**, bởi chúng có thể làm dashboard giảm findings mà không thay security risk.

### Example of decision

“Rule R báo string concatenation, nhưng sink là logging of a server-generated enum vào structured logger, không có SQL/shell/HTML context; call chain và runtime route đã xác minh. FP suppression chỉ cho file/method này, reviewer X, recheck nếu sink đổi.” Đây là lý do có thể kiểm tra, khác “noise”.

## 32. Ma trận 36 kịch bản kiểm thử cho review findings

Test matrix là **minh họa**, phải chọn theo threat model, asset và loại scanner thực tế. Không thực hiện payloads trên hệ thống ngoài scope; dùng synthetic principals, data fixtures, sandbox và kiểm soát tác động.

| Test ID | Kịch bản | Expected/evidence |
| --- | --- | --- |
| **SA-T01** | Scan chạy trên wrong commit so với PR/release. | Gate phát hiện mismatch; report không được dùng kết luận. |
| **SA-T02** | Scanner job exit success nhưng report ingestion lỗi. | Source-health kiểm tra missing results và mark UNKNOWN. |
| **SA-T03** | Thêm Java production module nhưng scan config không include. | Coverage check phát hiện missing module. |
| **SA-T04** | Scanner bị timeout khi phân tích cross-module. | Partial/failure status, không tự PASS. |
| **SA-T05** | Ruleset vô tình tắt SQL injection rule. | Policy/config diff và benchmark canary báo drift. |
| **SA-T06** | Tạo finding ở dòng mới, fingerprint thay. | Correlation không tạo closed/duplicate sai. |
| **SA-T07** | Hai warnings từ cùng helper, impact ở hai API. | Group root cause, giữ affected paths. |
| **SA-T08** | User input đi tới SQL concat. | SAST + code trace xác định issue, fix bằng parameterization. |
| **SA-T09** | Query dùng bind parameters đúng ngữ cảnh. | Evidence-backed FP/mitigated disposition nếu scanner báo. |
| **SA-T10** | Data thuộc tenant B truy cập qua user A. | Business AuthZ test DENY dù SAST không báo. |
| **SA-T11** | Output user text qua template autoescaping. | Browser/DOM test chứng minh không execute markup. |
| **SA-T12** | User content đi vào unsafe HTML injection sink. | Review identifies issue; fix/test context encoding. |
| **SA-T13** | User-controlled callback URL thử gọi internal test endpoint. | App/egress policies deny theo contract. |
| **SA-T14** | SSRF kiểm tra hostname nhưng redirect sang forbidden destination. | Redirect validation/egress gate ngăn. |
| **SA-T15** | File path chứa path-control variants. | Chỉ file reference được duyệt truy cập; no traversal. |
| **SA-T16** | Process invoked với untrusted arguments. | No shell interpolation/unauthorized command operations. |
| **SA-T17** | Deserializer nhận loại/field ngoài schema. | Reject/ignore theo contract, không tạo side effect. |
| **SA-T18** | Hardcoded test token bị scanner báo như production secret. | Phân loại đúng fixture/provenance, không auto-delete finding. |
| **SA-T19** | Credential thật trong commit history. | Revoke/rotate effective, sanitize evidence, remediation traced. |
| **SA-T20** | SAST không thấy flow từ API sang worker khác repo. | Coverage limitation và cross-service test được ghi. |
| **SA-T21** | SCA báo vulnerable component chỉ trong source dev dependency. | Artifact/runtime applicability review. |
| **SA-T22** | Vulnerable component được đóng gói trong production image. | Mapping từ build digest tới deployed runtime, risk assessed. |
| **SA-T23** | Vendor backport khiến version scanner báo false positive. | Vendor/build applicability evidence, approved disposition. |
| **SA-T24** | IaC manifest private nhưng effective bucket policy public. | Runtime evidence bác bỏ design; finding giữ open. |
| **SA-T25** | Finding biến mất khi exclude folder. | Coverage regression, không auto-mark remediated. |
| **SA-T26** | Inline suppression thiếu rationale/expiry. | Governance gate FAIL/needs review. |
| **SA-T27** | PR merged nhưng deployed artifact vẫn old digest. | Remediation chưa VERIFIED. |
| **SA-T28** | Code fix chưa có negative regression test. | Closure pending theo policy. |
| **SA-T29** | Security helper shared có fix nhưng alternate callsite còn vulnerable. | All affected paths retested. |
| **SA-T30** | Risk accepted finding đến expiry. | Reopen/escalate theo risk owner policy. |
| **SA-T31** | Tool severity Medium, impact cross-tenant Confidential. | Risk review nâng ưu tiên có rationale. |
| **SA-T32** | CI baseline không có new findings nhưng critical debt vẫn open. | Báo new-code gate riêng total risk inventory. |
| **SA-T33** | Critical telemetry source down lúc security regression test. | Evidence marked inconclusive, không PASS giả. |
| **SA-T34** | Static rule đã được cải tiến, báo thêm issue cũ. | Classify detection change vs introduced vulnerability. |
| **SA-T35** | Credential/PII vô tình nằm trong raw scan report. | Redaction/secure storage và incident assessment. |
| **SA-T36** | Finding fixed trong code nhưng runtime authz vẫn bypass qua queued job. | Integration/effective policy test FAIL; issue còn open. |

### Mẫu test record

**SA-T10 – Cross-tenant negative test:** chuẩn bị tenant A/B và synthetic invoice B; đăng nhập user A với quyền đọc trong A; gọi API bằng ID của B và kiểm tra API, cache, worker, download, audit. **Expected:** không trả dữ liệu B và có security decision phù hợp. **Observed:** ghi response/resource evidence đúng build, time, principal và environment. Nếu chỉ thấy status 403 ở API nhưng file đã được tạo qua background worker, test **không PASS**.

### Chất lượng test suite

Số tests chạy không tự chứng minh coverage. Cần map từng test tới **security requirement, threat scenario, source/sink/asset path và expected outcome**, đồng thời biết limitations như mock behavior, staging vs production hay absence of legacy clients.

## 33. Remediation: sửa đúng root cause thay vì chỉ làm warning biến mất

Một review finding xác nhận phải dẫn đến **bản sửa phù hợp security invariant**:

| Finding category | Fix strategy | Cần tránh |
| --- | --- | --- |
| SQL injection | Prepared statements, trusted identifier allowlist, DB authorization. | Escaping bằng chuỗi tự tạo. |
| XSS | Context-correct encoding, safe DOM API, trusted sanitization khi cần rich text. | Dùng cùng một sanitizer cho mọi output contexts. |
| SSRF | Server-selected destinations, redirect-aware validation, network egress controls. | Chặn vài IP strings rồi coi hết bypass. |
| Path traversal | Opaque object IDs, server-owned key mapping, canonicalization/permissions. | String prefix check đơn giản. |
| Command injection | Không dùng shell nếu không cần, fixed command/allowed args, sandbox. | Đổi API nhưng vẫn cho user chọn arbitrary flags/executable. |
| Insecure deserialization | Type/schema constraints, safe parser configuration, resource limits. | Chỉ tăng version library mà giữ unsafe polymorphism. |
| Secret exposure | Revoke/rotate, replace delivery method, clean distribution/artifacts. | Chỉ xóa line ở latest commit. |
| Broken authorization | Centralized resource/action/tenant enforcement, tests qua all paths. | Chỉ ẩn nút UI hoặc check authenticated. |
| Sensitive logging | Field-level redaction/minimization, structured events, access/retention. | Tắt toàn bộ security audit. |

### Sửa shared helper có thể chưa đủ

Khi một vulnerability xuất hiện ở nhiều code paths, fix phải bao phủ **callers, background jobs, admin/support routes, async consumers, old versions và alternate deployments**. Nếu một path vẫn dùng API cũ, finding có thể cần reopen dù scanner mới không thấy file đó.

### Sửa code phải cân nhắc tính tương thích

Siết validation, thay parser, encoder hoặc ORM có thể ảnh hưởng input hợp lệ và dữ liệu lịch sử. Thực hiện functional regression và security tests song song; nhưng không dùng khó khăn tương thích làm lý do suppress vô thời hạn mà không có decision/risk treatment.

## 34. Verification sau fix: ba lớp không được gộp

### Lớp 1 — Source-level resolution

Re-scan chính xác source commit chứa fix bằng rule coverage đủ; code/data-flow review xác nhận risky pattern không còn hoặc control mới hợp lệ. **Không đủ** nếu scanner khác cấu hình hoặc rule bị tắt.

### Lớp 2 — Behavioral validation

Chạy targeted negative tests theo attacker prerequisites và security requirement; chạy positive/compatibility tests để đảm bảo function vẫn đúng; xác minh controls qua code, configuration và output. Với SSRF, file access hay authz, cần kiểm tra **side effects** thay vì chỉ response status.

### Lớp 3 — Effective deployment

Nối commit → build artifact hash/image digest → release manifest → runtime deployment/loaded version. Nếu code fix chưa được deploy tới production, issue có thể là **fixed in source but still exposed in production**.

### Trạng thái rõ ràng

- **FIXED_IN_SOURCE:** change hợp lệ trong repo, cần deploy/test.
- **TESTED_IN_STAGING:** tests trên staging đạt, chưa đủ production claim.
- **DEPLOYED_PENDING_VERIFICATION:** runtime mới lên nhưng effective test/evidence chưa xong.
- **VERIFIED_FIXED:** tests và runtime scope đạt theo acceptance criteria.
- **PARTIAL/FAILED/UNKNOWN:** còn paths hoặc evidence chưa đủ.

### Security assurance claim

Một finding được verified fixed **trên các code paths và release đã kiểm tra**; không tự chứng minh các business functions ngoài scope hoặc không có những vulnerabilities khác.

## 35. CI/CD quality gates: không làm biến mất nợ cũ

Gates có thể kết hợp **new findings, reviewed risk, scan validity, approved exceptions và existing critical debt**. Tùy risk policy của tổ chức, có thể chặn:

- New High/Critical confirmed issues ở security-critical code.
- Unreviewed new findings có potential high impact mà không có owner/decision.
- Scanner disabled, incomplete, unsupported module hoặc output ingestion failed.
- Suppression/exception trái policy, expired hoặc thiếu scope.
- Missing negative tests cho security-sensitive change.
- Fixed code không gắn approved artifact provenance.

### Một policy minh họa

~~~yaml
policy_id: "SAST-GATE-EXAMPLE"
status: "ILLUSTRATIVE"
scope:
  application: "invoice-saas"
  branches:
    - "main"
  critical_modules:
    - "invoice-api"
    - "export-worker"
scan_quality:
  require_successful_execution: true
  require_expected_modules: true
  require_ruleset_baseline: true
  unknown_results_are_pass: false
new_findings:
  block_if:
    - "confirmed-critical"
    - "confirmed-high-without-approved-treatment"
    - "high-impact-unreviewed"
exceptions:
  require_owner: true
  require_scope: true
  require_risk_authority: true
  require_expiry: true
verification:
  require_negative_tests_for_security_fix: true
  track_deployed_artifact_digest: true
existing_debt:
  report_open_risk_separately: true
  do_not_discard_when_pr_is_green: true
~~~

Đây là **policy teaching example**, không phải cấu hình có thể đưa thẳng vào một CI product. Tên keys, integration và gate semantics cần được triển khai theo tool và governance thực tế.

### Gate fail là một trạng thái vận hành, không tự là vulnerability

Scanner timeout có thể chặn release vì **insufficient evidence**, không vì đã xác minh một exploit. Báo cáo phải phân biệt **security failure** và **assurance/control failure**, giúp các nhóm xử lý đúng nguyên nhân.

## 36. Case study: rà soát kết quả static scan cho Invoice SaaS đa tenant

### 36.1. Bối cảnh

Một release Invoice SaaS bổ sung tính năng bulk export, webhook và dashboard. Nguồn Java/Spring được phân tích bằng SAST; SCA/SBOM, IaC và security integration tests là các evidence bổ sung. Hệ thống có:

- Invoice API xử lý requests/authentication.
- Shared database với tenant ID.
- Export worker chạy từ queue và lưu file vào object storage.
- Webhook delivery cho third-party integrations.
- Tenant Admin/Support API, telemetry và CI/CD.

### 36.2. Báo cáo raw minh họa

Một lần scan giả định báo 46 findings trên repository gồm 7 High, 15 Medium, 24 Low. Review phát hiện **hai module mới chưa được scan semantic đầy đủ** vì build classpath lỗi. Do đó **raw count không thể là coverage rate**.

### 36.3. Mười findings chọn để review

| ID | Raw rule / observation | Review outcome minh họa |
| --- | --- | --- |
| **SAST-01** | User search term nối vào SQL query. | Confirmed injection pattern; cần parameterization và tests. |
| **SAST-02** | Invoice ID lookup chỉ dùng findById. | Suspected BOLA; xác nhận bằng authz flow và negative test. |
| **SAST-03** | Raw invoice note render HTML. | Confirmed/needs context-specific XSS review. |
| **SAST-04** | Webhook target URL từ request. | Potential SSRF; cần catalog/redirect/egress evidence. |
| **SAST-05** | File name từ user đi vào export temp path. | Path traversal/permission analysis required. |
| **SAST-06** | Secret-like text trong test source. | Needs classification: dummy hay active secret. |
| **SAST-07** | Logger nhận Authorization header. | Possible credential leakage, high-impact if raw. |
| **SAST-08** | Dynamic SQL in migration test code. | Potential N/A nếu thật không đóng gói; evidence required. |
| **SAST-09** | Framework old dependency theo SCA. | Package/advisory/runtime applicability, không xử lý như SAST flow. |
| **SAST-10** | Worker tenant context không được check ở API repo. | Cross-service gap: test queue/worker/data path. |

### 36.4. Tình huống SAST-02: severity bị đánh giá thấp

Rule tool đánh dấu Medium vì thấy repository.findById() thiếu tenant scoping, nhưng không biết API phục vụ Confidential multi-tenant data. Reviewer kiểm tra controller chỉ yêu cầu authenticated session; service không có object-level authorization. Synthetic user A đọc invoice B thành công trong sandbox → xác nhận critical **cross-tenant data authorization flaw** theo risk rubric của bài toán.

**Điều cần sửa:** trusted principal→tenant mapping; resource-level authorization; repository scoped query; kiểm tra cache, export worker và download paths; thêm negative tests. Không đóng bằng cách đổi finding thành Low hoặc gắn @SuppressWarnings.

### 36.5. Tình huống SAST-08: có thể not applicable

Mã có dynamic SQL nằm trong test utility, không vào main artifact hoặc production release. Reviewer cần kiểm tra **build packaging, classpath, invocation paths, CI/test environments và mục tiêu policy**. Nếu thực sự không thuộc production exposure và policy cho phép loại, có thể ghi N/A cho claim production **nhưng không có nghĩa test environment không cần bảo vệ**.

### 36.6. Tình huống SAST-10: scanner không đủ visibility

Invoice API scan không thấy worker code ở repository khác; SAST không báo BOLA end-to-end. Reviewer liên kết DFD: request→queue→worker→DB→storage→download, ghi assurance gap và yêu cầu cross-service authorization test, broker ACL, trusted job identity và effective DB permissions.

### 36.7. Phân biệt disposition và remediation

| Finding | Triage status | Risk/treatment | Closure requirement |
| --- | --- | --- | --- |
| SAST-01 | CONFIRMED | Fix parameterization và kiểm tra tenant scope. | Code+scan+negative test+runtime artifact. |
| SAST-02 | CONFIRMED nếu sandbox reproduces | Priority theo Confidential cross-tenant exposure. | End-to-end access tests all paths. |
| SAST-03 | PENDING_CONTEXT | Template escaping/DOM behavior cần verify. | Context-appropriate output tests. |
| SAST-04 | PENDING_EGRESS | Allowlist+redirect+egress risk controls. | Authorized destination tests. |
| SAST-05 | PENDING_PATH | Server-owned ID/path validation. | Traversal/symlink/authorization tests. |
| SAST-06 | PENDING_SECRET_VALIDATION | Masked token handling; revoke nếu active. | Secret lifecycle + artifact/history review. |
| SAST-07 | PENDING_LOG_REVIEW | Redaction, access/retention. | Canary log and source-health test. |
| SAST-08 | N/A only with evidence | Test code scope + policy decision. | Packaging/commit refs + reviewer. |
| SAST-09 | SCA_APPLICABILITY_PENDING | Verify fixed advisory/deploy. | SBOM, exact digest, runtime readback. |
| SAST-10 | ASSURANCE_GAP | Cross-service AuthZ review. | Worker/db/storage integration tests. |

### 36.8. Release decision

Nếu scan không phân tích hết hai modules và chưa có negative tests cho confirmed cross-tenant risk, **không có đủ căn cứ công bố release “security scan passed”**. Policy có thể đưa ra release blocker/conditional decision theo thẩm quyền. Missing scanner coverage và confirmed authorization flaw cần ghi thành **hai dạng finding riêng**, không che bằng một tỷ lệ chung.

### 36.9. Đóng theo bằng chứng, không theo số hàng giảm

Sau remediation, assessor cần exact source/commit, SAST config/status, code diffs, tests, artifact digest và runtime evidence. Nếu raw count giảm từ 46 xuống 10 nhưng phần lớn do config exclude, kết luận không cải thiện. Nếu có 10 findings nhưng 9 là confirmed FP/N-A và 1 issue critical open, **một critical issue vẫn quyết định risk**.

## 37. Claim–Argument–Evidence (CAE) cho rà soát scan

### Claim mẫu

> “Đối với các Java/Spring modules và deployed release R thuộc scope Invoice SaaS, static scans đã chạy đầy đủ theo baseline ruleset; các findings có khả năng ảnh hưởng security requirements trọng yếu đã được triage có evidence, những confirmed issues đã remediation hoặc quản trị rủi ro đúng policy, và các fixes được kiểm tra bằng scan, negative tests cùng runtime provenance tương ứng.”

### Argument

1. **Scope verified:** repository, modules, languages, commits, artifact và environments có identity rõ.
2. **Scanner health:** tool/ruleset/version, parsing/build context, exclusions, partial failures được kiểm.
3. **Finding validity:** source/sink, control flow, trust boundaries, reachable assets, disposition có technical rationale.
4. **Risk prioritization:** business impact/tenant/data classification được xét, không chỉ severity tool.
5. **Treatment:** fixes, exceptions hoặc no-action có owner/risk authority và time bounds.
6. **Verification:** security negative/functional tests và rescans đúng source; deployed versions có readback.
7. **Residual risk/unknowns:** gaps, unassessed paths và limitations được báo minh bạch.

### CAE evidence matrix

| Assertion | Evidence nên có | Giới hạn thường gặp |
| --- | --- | --- |
| Scan phù hợp với release. | Commit SHA, job/run ID, tool and config, artifact digest. | Merge/deploy có thể khác commit. |
| Rule coverage đủ theo scope. | Enabled rule list, benchmark canaries, exclusions/config diff. | Business logic không thể suy chỉ từ ruleset. |
| Findings triage đúng. | Reviewer rationale, code/data-flow references, tests, disposition records. | Human error và unknown paths vẫn có thể tồn tại. |
| High-impact risks đã xử lý. | Threat/control map, fixes, policy, negative tests. | Runtime bypass và third-party systems ngoài scope. |
| FP/N-A đúng. | Source/flow/packaging proofs và approvals. | Code changes có thể làm rationale lỗi thời. |
| Fix có hiệu lực. | Source diff, rescan, approved build, runtime digest, observed tests. | Một region/replica vẫn dùng bản cũ. |
| Assurance có monitoring. | Source health, regressions, reopened findings, exception expiry. | Không phát hiện incident không chứng minh không có incident. |

### Evidence phản bác

Một report scan cho commit C và CI PASS có thể bị bác bỏ bởi artifact runtime build từ commit D, hoặc scan config đã exclude module mới. Một finding SQLi marked Fixed nhưng query vẫn nối input qua code path khác là evidence mâu thuẫn. Reviewer phải **ghi issue và đánh giá lại claim**, không chỉ chọn screenshot có kết quả tốt.

## 38. Evidence quality, provenance và quyền truy cập kết quả scan

Raw scan report có thể chứa **source snippets, file paths, API routes, dependency versions, detected secrets và thông tin về lỗ hổng chưa được sửa**. Vì thế nó vừa là evidence cho assurance, vừa là tài sản cần bảo vệ.

### Thuộc tính evidence cần kiểm tra

| Quality | Câu hỏi đánh giá |
| --- | --- |
| **Relevance** | Report chứng minh đúng requirement, finding, asset và security claim? |
| **Completeness** | Các modules/paths/rulesets cần có đã được phân tích? |
| **Accuracy** | Triage rationale phản ánh đúng code/data-flow và runtime context? |
| **Freshness** | Scan/test sau commit hoặc change cuối cùng liên quan chưa? |
| **Integrity** | Có thể xác định source report đã bị thay/sửa hay xóa sau thu? |
| **Provenance** | Scanner tool/version/config, build, actor, source commit và timestamp có rõ? |
| **Repeatability** | Người khác có thể chạy lại với config/scope tương đương? |
| **Independence** | Có reviewer/test evidence ngoài người sửa issue cho critical findings khi cần? |
| **Traceability** | Từ threat→finding→fix→test→deployment nối được hai chiều? |
| **Limitations** | Unknown paths, unsupported languages, false negatives và exclusions được công bố? |

### Bảo vệ raw reports và triage notes

- Lưu reports trong hệ thống có phân quyền theo project, role và sensitivity.
- Chỉ đưa masked credential indicators vào tickets; raw secrets thuộc quy trình xử lý bảo mật riêng.
- Không đẩy raw scan reports với source snippets/confidential config lên public dashboards.
- Ghi source/report hash hoặc immutable reference nếu retention/audit cần kiểm tra integrity.
- Lưu versioned triage decisions và code-context refs; hạn chế sửa status không có audit trail.
- Xác định thời hạn lưu findings và dữ liệu cá nhân phù hợp mục đích và nghĩa vụ.
- Kiểm tra third-party scanner/SaaS provider xử lý source code, telemetry và secrets ra sao theo hợp đồng.

### Hash không chứng minh scanner đúng

Checksum có thể cho thấy report không đổi **sau khi xuất**, nhưng không chứng minh scanner đã quét đầy đủ source hoặc rule engine không có bug. Đây là lý do phải kết hợp **scan health, scope reconciliation và security benchmark tests**.

## 39. Mẫu YAML một finding review decision

Mẫu sau dùng IDs/versions giả định, **không phải metadata bài học hay kết quả kiểm thử thật**. Nó minh họa cách nối một static finding với security requirement, trách nhiệm và điều kiện đóng.

~~~yaml
schema_version: "1.0"
record_type: "static_scan_finding_review"
finding_id: "SAST-INV-028"
status: "ILLUSTRATIVE_PENDING_RETEST"
scan:
  tool: "ExampleJavaAnalyzer"
  version: "illustrative"
  ruleset: "approved-application-security-baseline"
  run_id: "scan-example-2026-11"
  repository: "invoice-saas"
  commit: "EXAMPLE_COMMIT_SHA"
  artifact_digest: "PENDING_BUILD_PROVENANCE"
  source_complete: "TO_BE_VERIFIED"
  executed_at: "2026-11-28T02:00:00Z"
finding:
  rule_id: "JAVA-UNSAFE-SQL-CONCAT"
  fingerprint: "illustrative-fingerprint"
  file: "src/main/java/example/InvoiceQueryService.java"
  code_path:
    source: "HTTP query parameter"
    sink: "JDBC Statement.executeQuery"
    sanitizer: "NONE_OBSERVED_IN_EXAMPLE"
  raw_severity: "HIGH"
  raw_confidence: "MEDIUM"
  disposition: "CONFIRMED_IN_EXAMPLE"
scope:
  service: "invoice-api"
  environment: "production"
  data_classification: "Confidential"
  tenant_scope: "multi-tenant-shared"
  asset_owner: "Invoice Application Team"
security_context:
  threats:
    - "TH-INJ-01"
  requirements:
    - "REQ-INJ-01"
  expected_outcome: >
    Untrusted values must not alter SQL syntax, and
    the query must remain tenant-scoped.
  risk:
    level: "TO_BE_APPROVED_WITH_RUBRIC"
    uncertainty:
      - "Production reachability pending"
review:
  technical_rationale: >
    Untrusted request value is concatenated into a query
    that is executed using a JDBC Statement.
  owner_role: "Application Security Engineer"
  reviewer_role: "Security Assurance Reviewer"
  reviewed_at: "NOT_REVIEWED_IN_REAL_SYSTEM"
remediation:
  plan: "Bind SQL values and enforce verified tenant scope"
  code_change: "PENDING"
  tests:
    - "SA-T08"
    - "SA-T10"
  effective_runtime_version: "NOT_VERIFIED"
verification:
  rescan: "NOT_RUN"
  negative_tests: "NOT_RUN"
  deployment_readback: "NOT_RUN"
  evidence_refs: []
  conclusion: "NOT_VERIFIED"
reopen_triggers:
  - "query-path-change"
  - "scanner-ruleset-change"
  - "new-repository-consumer"
  - "affected-runtime-asset-added"
~~~

### Cách hiểu

Record có một ví dụ về logic xác nhận coding issue nhưng mọi trường verification thực tế vẫn **NOT_RUN/NOT_VERIFIED**. Không nên đọc status ILLUSTRATIVE_PENDING_RETEST như production đã fix; dữ liệu minh họa không thể dùng làm evidence compliance.

### Vòng đời file review

Sau mỗi significant source change, phải xem lại affected code path và applicability. Một FP disposition từ release R có thể không còn đúng khi helper được dùng làm API public ở release R+1. Vì vậy, status/owner/expiry và links tới exact commit có giá trị hơn một comment “safe” bất biến.

## 40. KPI/KRI/KCI cho việc rà soát scan

Metrics nên giúp phát hiện **risk, chất lượng triage, độ phủ và nguồn bằng chứng**, không chỉ tối ưu số findings.

| Metric ID | Định nghĩa hoặc phương pháp | Giới hạn |
| --- | --- | --- |
| **SA-M01 Scan scope coverage** | Required modules/paths có valid scan / independently known required scope. | Tool-known paths không đủ làm denominator. |
| **SA-M02 Scan health** | Required scan jobs thành công, không partial và có reports hợp lệ / required jobs. | Successful process chưa chứng minh rule coverage. |
| **SA-M03 Rule baseline adherence** | Projects có effective approved ruleset / projects cần baseline. | Cần kiểm config drift và custom rules. |
| **SA-M04 Finding triage coverage** | In-scope material findings có reviewed disposition/evidence / findings cần triage. | Triage hoàn tất chưa chắc disposition đúng. |
| **SA-M05 Triage lead time** | Thời gian từ finding first seen tới reviewed decision, theo priority. | Không dùng average che high-risk backlog. |
| **SA-M06 Confirmed open issues** | Số distinct confirmed issues mở, theo criticality, exposure, age. | Dedup có thể sai; không chỉ đếm rows. |
| **SA-M07 False-positive proportion** | Reviewed findings bị kết luận FP / reviewed findings trong cohort. | Không suy trực tiếp precision nếu sample không đại diện. |
| **SA-M08 Needs-investigation age** | Số/tuổi issues chưa đủ evidence, theo potential impact. | Unknown không tự là Low. |
| **SA-M09 Suppression governance** | Active suppressions có rationale/owner/expiry và review / required suppressions. | Có waiver không bằng security PASS. |
| **SA-M10 Risk-based remediation time** | Thời gian first confirmed tới verified fixed, theo risk tier. | Tránh dùng ticket close time thay verification. |
| **SA-M11 Verification coverage** | Fixed issues có rescan + required negative tests + artifact evidence / issues đến hạn. | Test scope có thể thiếu paths. |
| **SA-M12 Reopen/regression rate** | Verified issues tái xuất hiện theo cohort/version. | Rule model thay có thể tạo “new” sai. |
| **SA-M13 Baseline aging** | Open known debt theo severity, owner và overdue threshold. | PR no-new gate không làm debt biến mất. |
| **SA-M14 Cross-tool agreement** | Confirmed cases có evidence từ SAST/SCA/DAST/review theo loại. | Các tools không độc lập hoặc đo khác vấn đề. |
| **SA-M15 Scanner sensitivity checks** | Seeded/benchmark cases được phát hiện / expected cases trong tested rule scope. | Không chứng minh phát hiện mọi real vulnerabilities. |
| **SA-M16 Evidence freshness** | Critical findings có evidence trên current relevant commits/releases. | “Last scanned” khác “deployed fixed”. |
| **SA-M17 Runtime fix alignment** | Target deployments có verified fixed artifact / independently identified affected deployments. | Ephemeral/legacy assets cần inventory riêng. |
| **SA-M18 Collector/report completeness** | Expected scan reports ingested với schema/health đúng / expected reports. | Raw counts không đủ nếu policy thay. |

### Mẫu số và thời gian phải minh bạch

Nếu repository có 20 in-scope modules và scanner chạy đúng trên 17, **module scan coverage = 17/20**, không phải 17/17. Nhưng ngay cả 17/20 cũng chưa cho biết ruleset có bao phủ security requirements trọng yếu hay không.

### Đánh giá performance của scanner

**Precision** thường liên quan proportion cảnh báo thực sự đúng trong tập findings được đánh giá; **recall/sensitivity** liên quan phần các issues thật mà scanner tìm thấy trong population có ground truth. Không thể suy recall từ tỷ lệ false positive trong một backlog hoặc từ việc scanner phát hiện 0 issues. Muốn đo tương đối cần **labeled benchmarks/controlled test cases** và nêu bias/limitations.

### Critical gate hơn là trung bình

Một dashboard “98% findings resolved” có thể vẫn chứa một confirmed cross-tenant authorization flaw. **Risk decision phải xét critical assets và blockers**, không lấy tỷ lệ trung bình che serious findings.

## 41. RACI và phân tách trách nhiệm review

| Vai trò | Trách nhiệm |
| --- | --- |
| **Application developer** | Hiểu code path, xác nhận coding behavior, sửa code và unit/integration tests. |
| **Application/service owner** | Ownership, exposure, security requirements, due dates và deployment. |
| **Security reviewer/AppSec** | Phân tích rules, data flow, false positives, risk rationale và fix patterns. |
| **SAST/scanner platform owner** | Ruleset, scanner health, integrations, coverage, benchmarking, data retention. |
| **Architect/threat model owner** | Trust boundaries, cross-service paths, business authorization và design review. |
| **Platform/IAM/data owners** | Effective runtime controls, service identities, databases và storage evidence. |
| **Vulnerability management lead** | Backlog, SLAs, prioritization, exceptions, remediation verification. |
| **Security assurance assessor** | Independent challenge, evidence quality, conclusion scope, retest assessment. |
| **Business/risk owner** | Quyết định residual risk/waivers theo thẩm quyền và nghĩa vụ. |
| **Release/change owner** | CI gates, release scope, approval, deployment/provenance and rollback. |

### RACI minh họa

**R** = người thực hiện; **A** = chịu trách nhiệm cuối cùng; **C** = tham vấn; **I** = được thông báo.

| Hoạt động | Dev/App | AppSec | Scanner owner | Assurance | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| Rule baseline và scan completeness | C | R | **A/R** | C | I |
| Truy vết code/source–sink | R | **A/R** | C | C | I |
| Quyết định FP/N-A của finding high-impact | R | **A/R** | C | C | I |
| Remediation code, tests và deploy | **A/R** | C | I | C | I |
| Independent evidence/retest assessment | C | R | C | **A/R** | I |
| Risk acceptance/exception | C | C | I | C | **A/R** |

Nhóm nhỏ có thể gộp roles, nhưng với high-impact issues cần cân nhắc **độc lập đánh giá và separation of duties**. Người viết patch không nên tự tuyên bố đã giảm mọi rủi ro production mà không có verification.

## 42. Quản lý exceptions và residual risk

Có thể chưa sửa ngay finding vì vendor limitation, major framework upgrade, nghiệp vụ legacy hoặc constraints vận hành. **Exception có thời hạn** là cơ chế quản trị rủi ro; không phải thao tác gắn label false positive.

### Những trường bắt buộc cho exception

1. Finding/threat/requirement ID và affected assets/releases.
2. Technical root cause và evidence chứng minh applicability.
3. Attacker prerequisites, exposure, data/tenant/business impact.
4. Current controls và evidence về hiệu quả, không chỉ design intent.
5. Proposed compensating controls, tests và known bypasses.
6. Owner, remediation timeline và milestones có thể theo dõi.
7. Risk owner đúng thẩm quyền và date/expiry.
8. Trigger xem lại: incident, exposed route, new exploit, dependency change, ruleset change.
9. Regulatory/contractual considerations có được xác minh không.
10. Criteria đóng exception sau fix và retest.

### Các quyết định không nên nhầm

| Decision | Ý nghĩa |
| --- | --- |
| **FP** | Detector không áp dụng đúng ở code/context đã chứng minh. |
| **Not applicable** | Finding không thuộc asset/artifact/scope của claim có chứng cứ. |
| **Compensating mitigation** | Risk giảm bởi control khác đã thử hiệu lực; underlying issue có thể còn. |
| **Risk accepted** | Residual risk được chấp thuận trong thời gian/scope nhất định. |
| **Fixed and verified** | Requirement được thỏa trên path/release đã thử; có evidence. |

### Exceptions không tự miễn nghĩa vụ

Một waiver nội bộ không thay điều khoản hợp đồng, luật hoặc standard bắt buộc. Nếu security requirement không cho phép ngoại lệ, reviewer phải escalate đúng governance thay vì dùng “business approved” để tự bỏ control.

### Khi nào cần mở lại?

SAST rule đổi, input path trở nên public, asset được chuyển sang multi-tenant, một control mất hiệu lực, hoặc exception hết hạn — đều có thể khiến kết luận trước không còn hợp lệ. Ghi reopen trigger trong finding register.

## 43. Continuous review: cập nhật findings khi code và risk đổi

Một scan có giá trị trong **source snapshot và ruleset** của nó, không phải chứng nhận vĩnh viễn. Dịch vụ, dependencies, identities và business flows có thể thay ngay sau khi review.

### Trigger reassessment

- New endpoint, GraphQL operation, gRPC method, WebSocket hoặc event consumer.
- Code refactor, shared helper, input validation, parser, authorization hoặc database query thay đổi.
- Nâng framework/JDK, security library, serialization package hoặc base image.
- Chuyển feature từ internal sang internet-facing hoặc thêm tenant tier/data type nhạy cảm.
- Thay middleware, identity trust, role mapping, KMS/secret delivery hoặc cloud policy.
- SAST ruleset/tool version/suppression/scanner scope thay đổi.
- Triaged false positive có call site hoặc output context mới.
- New vulnerability research, incident, pentest finding hoặc reopened issue.
- Scan/report source ngừng hoạt động, mất coverage hoặc schema ingestion lỗi.
- Verified fix được rollback hoặc runtime deployment khác approved build.

### Continuous assurance loop

~~~mermaid
flowchart TD
    A["Approved code and security baseline"] --> B["Source / dependency / design changes"]
    B --> C["Scan with expected scope and rules"]
    C --> D{"Scan quality complete?"}
    D -- "No" --> E["Coverage / tool health issue"]
    E --> C
    D -- "Yes" --> F["Fingerprint and triage findings"]
    F --> G["Risk, owner, fix or exception"]
    G --> H["Secure remediation and tests"]
    H --> I["Deploy approved artifact"]
    I --> J{"Security requirement verified?"}
    J -- "No / unknown" --> G
    J -- "Yes" --> K["Time-scoped assurance record"]
    K --> L["Monitor runtime, drift and incident feedback"]
    L --> B
~~~

### Dùng automation đúng mục đích

Automation có thể gắn scan vào PR, gợi ý reviewer, so sánh ruleset hashes, phát hiện suppressions mới, tạo change requests và link issues→commits→tests. Tuy nhiên **machine-generated disposition** không thay risk owner/technical reviewer khi flow phức tạp. Với auto-dismiss, cần explicit criteria, sampled review, audit trail và reopen logic.

### Đo two-way traceability

Từ một threat như **cross-tenant export** phải truy đến SAST checks hoặc lý do scanner không bao phủ, rồi tới security integration tests. Từ một scanner rule phải truy ngược được nó phục vụ **requirement/security objective nào**. Những links không có test hoặc không có impacted asset phải hiện thành **coverage gap**, không phải 0 risk.

## 44. Anti-patterns khi rà soát scan

| Anti-pattern | Hậu quả | Cách sửa |
| --- | --- | --- |
| **Scan completed = secure** | Không hiểu false negatives và missing coverage. | Scope health, threat review và tests. |
| **No findings = safe** | Scanner disabled hoặc unsupported code vẫn dashboard xanh. | Canary tests và config/source completeness. |
| **Severity = risk** | Bỏ business impact, tenant exposure và confidence. | Risk-based triage theo asset/threat. |
| **All findings are vulnerabilities** | Lãng phí cho FP/N-A và mất tin cậy. | Technical disposition có evidence. |
| **All findings are scanner noise** | Bỏ confirmed issues nghiêm trọng. | Source–sink review, independent checks. |
| **FP because authenticated** | Authenticated malicious user vẫn exploit được BOLA/injection. | Attacker capability/authorization analysis. |
| **FP because WAF exists** | WAF có bypass hoặc không ở đúng path. | Effective control tests và residual risk. |
| **One-click suppression** | Che issues mới, không có ownership/expiry. | Narrow suppressions với audit. |
| **Baseline hides all debt** | PR xanh nhưng critical backlog kéo dài. | Separate new findings và total risk inventory. |
| **File:line as stable ID** | Refactor gây false new/closed findings. | Fingerprint + context + history. |
| **Duplicate = no problem** | Grouping che high-impact call site. | Preserve every affected resource path. |
| **Scan only the changed lines** | Cross-module source→sink hoặc dependency changes bị bỏ. | Full baseline và targeted semantic tests. |
| **SAST replaces AuthZ review** | Business object/tenant rules bị bỏ sót. | Threat modeling và cross-tenant tests. |
| **SAST replaces SCA** | Transitive vulnerable packages không được xử lý. | SBOM/deployed artifact analysis. |
| **SAST replaces DAST/runtime** | Effective permissions, routes, config chưa được xác minh. | Complementary controls/tests. |
| **PR merged = fixed** | Production pods còn old image digest. | Runtime release provenance and readback. |
| **Finding vanished = fixed** | Rule/scope disabled, parsing failed. | Scan delta analysis và retest. |
| **Ticket closed = retested** | Không có observed security outcome. | Verification states và independent evidence. |
| **Exception = PASS** | Risk accepted nhưng unsafe behavior còn. | Report status/risk separately. |
| **Copy secret into ticket** | Tăng exposure và vi phạm retention. | Mask/redact, rotate/revoke workflow. |
| **One global security score** | High-impact cross-tenant issue bị average che. | Stratified metrics, critical gates. |
| **No owner for unknowns** | Finding treo mãi không quyết định. | Triage owner, deadline, risk escalation. |

### Bảy câu nói nên khiến reviewer hỏi lại

1. “Rule này hay báo sai, cứ bỏ.”
2. “App có MFA rồi, không thể injection.”
3. “Tất cả issues trong baseline đều được chấp nhận.”
4. “Chỉ cần fix code, không cần deploy/retest.”
5. “Một SAST tool không báo thì bug không tồn tại.”
6. “Không thấy alert production, vậy finding không khai thác được.”
7. “Đổi severity xuống Low để pipeline pass.”

Các câu trên không tự chứng minh lỗ hổng đã có; chúng **thiếu lập luận/evidence** để quyết định.

## 45. Checklist dành cho reviewer kết quả static scan

Dùng như một hướng dẫn kiểm tra, không phải checklist để ký tên mà không đọc code.

1. **Identity:** scan thuộc đúng repository, branch, commit, build và environment?
2. **Run health:** scanner hoàn thành, không timeout/partial, output được ingest đủ?
3. **Tool/rules:** version, security rule categories, precision, config, exclusions và suppressions rõ?
4. **Scope:** critical modules, languages, generated code, cross-repo paths được xét phù hợp?
5. **Baseline:** phân biệt new/existing/reopened/removed-by-scope-change?
6. **Fingerprint:** correlation theo rule/source/sink/symbol thay vì chỉ line?
7. **Finding metadata:** source, sink, data-flow và rule semantics có đủ?
8. **Attacker model:** input do ai kiểm soát, có prerequisites/privileges gì?
9. **Trust boundary:** dữ liệu đi qua boundary nào, control nằm ở đâu?
10. **Sanitization:** đúng sink/context, không chỉ validation hình thức?
11. **Authentication:** có nhầm login với authorization resource/action không?
12. **Tenant context:** object/tenant ownership và async/export paths được xem?
13. **Applicability:** source code có trong built/deployed artifact không?
14. **True/false positive:** rationale có được kiểm bằng code/test/evidence?
15. **Duplicates:** có gom root cause mà vẫn giữ tất cả affected paths?
16. **False-negative scope:** rule thiếu cho business invariants nào?
17. **Severity/risk:** business data, blast radius, exploitability và effective controls được xét?
18. **SCA/secrets/IaC:** có vấn đề cần evidence từ loại scan khác không?
19. **Owner:** service owner, code owner, AppSec và risk owner rõ?
20. **Remediation:** code/design fix phù hợp source→sink và root cause?
21. **Security tests:** có negative tests với expected/observed outcomes?
22. **Functional tests:** fix có tạo regression hoặc breaking change không?
23. **Runtime:** source fix gắn đúng artifact/release/digest/region?
24. **Scan delta:** issue biến mất do fix hay do tool/rule/exclusion change?
25. **Suppressions:** narrow, review, owner, expiry, không silent bypass?
26. **Exceptions:** risk approval, interim controls, deadline, legal/contract scope?
27. **Evidence:** provenance, integrity, recency, relevant time/scope và retention?
28. **Privacy:** scan report/tickets có tránh raw secrets và PII?
29. **Telemetry:** security logs/source health có hỗ trợ kết luận trong kỳ?
30. **Conclusion:** có ghi PASS/PARTIAL/FAIL/UNKNOWN/N-A, limitations, critical open findings và next actions?

### Kết quả checklist phải có trạng thái

Với mỗi control có rủi ro đáng kể, lưu **PASS, FAIL, PARTIAL, UNKNOWN hoặc N/A với lý do**, evidence ref, owner và deadline. Một module **UNKNOWN** do scanner lỗi không được xem như module “có 0 findings”.

## 46. Bài tập tình huống và gợi ý giải

### Bài tập A — Dashboard có 0 findings sau refactor

Release trước có 12 findings; release mới 0. Một kỹ sư phát hiện scan job không còn include thư mục service mới.

**Gợi ý:** Đây là **scan coverage failure**, không phải chứng cứ vulnerability fixed. So sánh tool config/paths, chạy lại full scan và kiểm tra old findings bằng fingerprint/commit.

### Bài tập B — SQL injection report trong code production

HTTP query được nối vào SQL string rồi đưa cho Statement.executeQuery. Developer nói user phải đăng nhập.

**Gợi ý:** AuthN không thay SQL syntax safety. Kiểm tra attacker capability, source→sink, parameter binding, DB role và tenant scope; viết targeted negative test. Đánh giá risk theo data/entry point, không auto-FP.

### Bài tập C — SAST báo XSS trong template

Tool báo raw output nhưng framework có autoescaping trong HTML text context. Dữ liệu còn được dùng trong JavaScript template khác.

**Gợi ý:** Phân loại theo **từng sink/output context**; autoescaping ở text node có thể khiến một warning FP, nhưng JS context cần riêng. Không suppress toàn file.

### Bài tập D — Library có CVE theo SCA nhưng không thấy trong runtime

Một test-only package xuất hiện trong manifest; production artifact không chứa package theo SBOM/digest đã xác minh.

**Gợi ý:** Cần applicability proof để đánh giá production N/A, nhưng xem lại test/CI exposure và source scan scope; không xóa finding chỉ vì team nói “chỉ test”.

### Bài tập E — Missing authorization không được scanner phát hiện

User A đọc được invoice B qua endpoint đã xác thực. SAST scan toàn repo không báo.

**Gợi ý:** Đây là **false negative/coverage limitation** tương đối với business authorization requirement. Ghi confirmed issue từ test, bổ sung object-level AuthZ, custom rules hoặc cross-tenant tests và review các paths tương tự.

### Bài tập F — SSRF rule có WAF

Application nhận callback URL do tenant khai, server gọi HTTP client. Team cho rằng WAF xử lý mọi request nên FP.

**Gợi ý:** WAF inbound không chứng minh outbound destination policy. Review allowed endpoints, redirects, DNS/network egress, internal reachability và callback contract; test sandbox rồi đánh giá controls thực.

### Bài tập G — Secret được xóa khỏi HEAD

Production API key từng có trong commit cũ, hiện source mới dùng secret manager. Ticket được đóng mà chưa rotate.

**Gợi ý:** Delete from HEAD không thu hồi credential. Điều tra nơi secret đã được phát tán, rotate/revoke và verify effective deny, kiểm tra artifacts/history và bảo vệ evidence.

### Bài tập H — Duplicate warnings cùng rule

Một helper format query tạo 20 warnings ở 20 endpoints, trong đó một endpoint có dữ liệu Restricted và 19 endpoints chỉ internal reports.

**Gợi ý:** Có thể nhóm một root-cause fix nhưng giữ **20 affected paths** và tách risk theo exposure/impact; retest tất cả relevant paths, không che Restricted endpoint.

### Bài tập I — CI báo No New High nhưng backlog cũ còn Critical

Trong PR không xuất hiện finding mới, nhưng có một confirmed Critical xuất hiện từ nhiều tháng trước ở production.

**Gợi ý:** New-code gate PASS không đồng nghĩa total risk PASS. Báo debt aging, owner, interim controls và risk owner decision; áp policy phát hành tương ứng.

### Bài tập J — Security fix bị rollback

Sau deploy một parser fix, ứng dụng lỗi, team rollback về image cũ để phục hồi availability.

**Gợi ý:** Reclassify finding theo **actual deployed digest**; security risk có thể quay lại. Ghi rollback/risk/containment và retest khi fix mới deploy, không để ticket ở VERIFIED_FIXED.

### Bài tập K — Scanner severity Medium, rủi ro thực High

Một rule warning thiếu validation trong export API xếp Medium nhưng API xử lý hàng triệu bản ghi Confidential nhiều tenant.

**Gợi ý:** Risk-based review nâng ưu tiên dựa impact, attacker preconditions, data/tenant scope; xác minh authz/control/test, không chỉ dùng tool category.

### Bài tập L — False positive disposition cũ không còn đúng

Một method trước kia chỉ dùng trusted enum nội bộ nay được gọi từ public API với user-controlled string. FP suppression vẫn tồn tại.

**Gợi ý:** Reopen khi trust boundary/caller đổi, kiểm tra source→sink mới, xóa/narrow suppression và thêm regression tests.

### Bài tập M — Tính precision/recall sai

Một đội báo “false positive rate 10% nên recall 90%”. Họ chỉ xem 100 warnings đã được scanner báo.

**Gợi ý:** FP proportion trong reported set không suy ra recall; recall cần biết issues thật nhưng scanner không báo trong ground-truth population. Dùng controlled fixtures/independent review với limitations.

### Bài tập N — Finding biến mất cùng lúc đổi ruleset

Trước khi release, security policy đổi ruleset và giảm 100 warnings xuống 5. Không có code change.

**Gợi ý:** Phân tích rule/config deltas, excluded modules và baseline mapping; không gọi các warnings vừa biến mất là Fixed. Đánh giá material control coverage và risk decision.

### Bài tập O — SAST báo fix, worker vẫn bị BOLA

API đã dùng tenant-scoped repository, nhưng queue message cho phép worker đọc hóa đơn khác tenant vì worker tin tenantId do producer gửi.

**Gợi ý:** Một layer được sửa chưa đủ. Đánh giá **cross-service trust/authorization**, broker permissions, server-owned job binding, worker DB permissions và end-to-end negative tests.

### Bài tập P — Report chứa token-like strings thật

Tool tự thu source snippet có một credential và upload vào hệ thống tickets mà nhiều người có thể đọc.

**Gợi ý:** Đây có thể là **evidence-handling incident** bên cạnh code secret finding. Hạn quyền/điều tra exposure, revoke/rotate nếu credential thật, redact report và sửa scanner export policy.

## 47. Kết luận

**Rà soát kết quả scan** trong **Static analysis** không chỉ là sắp xếp danh sách Critical/High/Medium/Low. Đó là quá trình xác minh **lần scan có hợp lệ**, phân tích source–sink/control flow, xác định **applicability và disposition** trên code thật, phân biệt severity của công cụ với business risk, xử lý ownership, remediation, exceptions và kiểm tra lại trên **đúng artifact/runtime**.

Trong **SECURITY_SECURITY_ASSURANCE**, mỗi finding đáng kể phải có thể truy vết tới **threat hoặc security requirement, affected asset, risk assessment, control, expected/observed test, evidence và residual risk**. SAST phát hiện nhiều vấn đề quan trọng nhưng không thay **SCA, IaC, threat modeling, business authorization review, integration tests và runtime assurance**; việc scanner không báo không chứng minh thiếu lỗ hổng.

Một kết luận có trách nhiệm phải nói rõ **commit, ruleset, modules, asset/release/environment, scan validity, triage decisions, confirmed issues, unknowns, suppressions, exceptions, verification results và thời kỳ đánh giá**. Nếu report không đầy đủ hoặc fix chưa được triển khai/kiểm thử hiệu lực, trạng thái phải là **PARTIAL/UNKNOWN/PENDING**, không tự chuyển xanh. **Mục tiêu cuối cùng là đưa kết quả phân tích tĩnh thành quyết định có bằng chứng, khắc phục được kiểm chứng và chương trình assurance liên tục theo thay đổi của hệ thống.**
