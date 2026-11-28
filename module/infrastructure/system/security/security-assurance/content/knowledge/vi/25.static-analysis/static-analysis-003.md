# False positive

**False positive (dương tính giả)** trong **static analysis** là trường hợp công cụ phân tích tĩnh phát ra một cảnh báo về một lỗi hoặc hành vi bị coi là không an toàn, nhưng sau khi đánh giá đầy đủ theo **định nghĩa rule, đường dữ liệu, cấu hình, sản phẩm và phạm vi áp dụng**, nhận định vi phạm đó **không đúng**. Trong phân tích bảo mật (SAST – Static Application Security Testing), false positive có thể khiến nhóm phát triển mất thời gian, quá tải cảnh báo hoặc tắt bừa các rule. Ngược lại, gắn nhãn “false positive” cho một lỗi thực là cách làm giảm khả năng phát hiện rủi ro.

Ví dụ, công cụ báo **SQL injection** vì thấy dữ liệu từ HTTP request đi tới một câu truy vấn. Nhưng code thực tế dùng **PreparedStatement** để bind giá trị và không ghép input vào cú pháp SQL. Nếu công cụ nhận diện sai cơ chế xử lý này, finding có thể là false positive **cho weakness SQL injection được rule mô tả**, sau khi reviewer xác minh đầy đủ query construction và những nhánh liên quan. Tuy nhiên, cùng endpoint đó vẫn có thể thiếu **tenant/object authorization**; việc cảnh báo SQL injection là sai **không chứng minh toàn endpoint an toàn**.

Bài thuộc chương **Static analysis** của module **SECURITY_SECURITY_ASSURANCE**, với mục tiêu *xây dựng cách đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật, từ phân tích rủi ro, yêu cầu và security controls đến kiểm thử, audit và khắc phục phát hiện; học tổ chức chương trình security assurance liên tục trong phát triển và vận hành*. Vì thế, trọng tâm không phải tìm mẹo “làm scanner xanh”, mà là xây dựng **quy trình phân loại finding có chứng cứ, reviewer chịu trách nhiệm, quyết định có phạm vi và kiểm soát được biến động theo thời gian**.

**Thông điệp chính:** false positive là **kết luận có căn cứ về một cảnh báo trong một phiên bản/phạm vi**, không phải một nhãn tiện lợi để loại cảnh báo khỏi dashboard. **Không có báo cáo từ scanner** hoặc **scan lỗi** cũng không có nghĩa không có lỗ hổng.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Định nghĩa true positive, false positive, true negative, false negative và hiểu mối liên hệ giữa chúng.
2. Phân biệt **false positive**, **not applicable**, **mitigated**, **risk accepted**, **duplicate**, **already fixed** và **insufficient evidence**.
3. Phân tích một SAST finding theo **source → propagation → sanitizer/validator → sink**, trust boundary và attack preconditions.
4. Hiểu vì sao rule heuristics, framework models, aliases, reflection, dependency injection, dynamic dispatch và configuration có thể tạo cảnh báo sai.
5. Phân biệt rule detection với **khả năng khai thác thực tế**, đồng thời tránh tự bác bỏ vấn đề chỉ vì chưa tái hiện exploit.
6. Thiết kế triage workflow có baseline, evidence, confidence, reviewer và SLA theo rủi ro.
7. Đánh giá ví dụ Java/Spring liên quan SQL injection, XSS, path traversal, SSRF, hardcoded secrets, cryptography và authorization.
8. Hiểu cách dùng **suppressions, exclusions, baselines, triage statuses** đúng ngữ nghĩa và kiểm soát thay đổi.
9. Viết rationale phản biện finding ngắn, rõ, có code/context, test và phạm vi áp dụng.
10. Xây regression tests cho false-positive fixes và phát hiện khi suppressed rule trở nên nguy hiểm sau code change.
11. Đánh giá precision, recall, false-positive rate và metrics triage mà không tạo KPI đánh lừa.
12. Phân biệt SAST, SCA, DAST, unit/integration test, threat model và runtime evidence trong Claim–Argument–Evidence.
13. Thiết kế CI/CD security gates không biến scanner error thành zero findings hoặc tự động chấp nhận suppression.
14. Điều phối developer, reviewer, AppSec, product owner và risk owner trong quyết định finding.
15. Quản lý kỹ thuật và governance để **giảm noise mà không tăng false negatives**.
16. Tổ chức continuous assurance: retest, audit trail, reopen triggers và đo chất lượng kết luận qua từng release.

## 2. Bản chất của false positive trong SAST

### 2.1. Tool finding khác vulnerability đã xác nhận

**Finding** là đầu ra của một phép kiểm tra. Nó có thể gồm rule ID, file, dòng, severity, message, data-flow trace, CWE mapping và một gợi ý remediation. Finding chưa tự động chứng minh:

- Có luồng dữ liệu không đáng tin tới sink thực.
- Đường chạy đó reachable ở build/runtime.
- Sanitizer/parameterization sai hoặc thiếu.
- Threat preconditions thỏa mãn.
- Người dùng có quyền gọi entry point.
- Component thuộc artifact được deploy.
- Severity thể hiện đúng impact.
- Vulnerability đang tồn tại trong mọi environment/tenant.
- Không có safeguards khác hoặc alternate paths.

**Triage** là quá trình kiểm chứng những điều trên và xác định finding đại diện cho rủi ro nào. Tool finding đáng chú ý, nhưng kết luận phải dựa trên **evidence**.

### 2.2. Hai câu hỏi rất khác nhau

1. **Rule nói có vi phạm; thông tin và dữ liệu có chứng minh vi phạm theo rule không?** Đây là câu hỏi về true positive/false positive.
2. **Nếu vi phạm có thật, nó có thể bị khai thác, gây hại ở sản phẩm cụ thể và cần ưu tiên ra sao?** Đây là câu hỏi về exploitability/risk.

Một **true positive** có thể được giảm rủi ro bằng kiểm soát bù trừ. Khi đó không nên gọi nó false positive. Một cảnh báo về API **không nằm trong sản phẩm được đánh giá** có thể là **not applicable** theo scope; không nên tự dùng nhãn false positive nếu vấn đề thực tế tồn tại ở artifact khác.

### 2.3. Minh họa chuỗi đánh giá

~~~mermaid
flowchart TD
    F["SAST finding"] --> I["Nhận diện rule, target, build"]
    I --> D{"Có bằng chứng về unsafe behavior theo rule?"}
    D -->|"Có"| T["True-positive technical finding"]
    D -->|"Không, có chứng cứ"| FP["False positive theo scope"]
    D -->|"Chưa rõ"| U["Needs investigation / evidence gap"]
    T --> R["Đánh giá exposure, impact, controls"]
    R --> X{"Risk decision"}
    X -->|"Fix"| M["Remediate + verify"]
    X -->|"Compensating control"| C["Mitigated, residual risk"]
    X -->|"Approved exception"| A["Accepted risk có thời hạn"]
    FP --> E["Document rationale + regression trigger"]
    U --> V["Review code, config, data flow, tests"]
    V --> D
~~~

### 2.4. Vì sao nhãn FP sai nguy hiểm?

Nếu một SQLi thật bị đánh dấu FP:
- Developer có thể không sửa vulnerability.
- CI có thể suppress finding mãi.
- Code tương tự có thể được coi là “an toàn” khi review.
- Audit report báo tỷ lệ findings đã xử lý quá cao.
- Incident response không biết có vùng bị ảnh hưởng.
- Risk owner không được thông báo về residual risk.
- Scanner rule có thể bị tắt ở phạm vi toàn tổ chức.

Vì vậy **false-positive classification phải có traceable reasoning và reviewer đúng thẩm quyền**.

## 3. Confusion matrix: TP, FP, TN, FN

### 3.1. Khái niệm

| Thực tế / Kết quả scanner | Scanner cảnh báo | Scanner không cảnh báo |
|---|---|---|
| **Có weakness đúng định nghĩa trong scope** | **True Positive (TP)** | **False Negative (FN)** |
| **Không có weakness đúng định nghĩa trong scope** | **False Positive (FP)** | **True Negative (TN)** |

Ví dụ:
- TP: code ghép untrusted parameter vào SQL syntax, SAST báo SQL injection, review xác nhận.
- FP: code sử dụng parameter binding đúng, nhưng taint engine vẫn báo giá trị đến sink unsafe.
- FN: code có SQL injection nhưng SAST bỏ sót vì dynamic query builder không được mô hình hóa.
- TN: code an toàn và scanner không báo.

### 3.2. Một cảnh báo không đủ để tính TN và FN toàn hệ thống

Trong thực tế, **TN và FN thường không biết đầy đủ** vì bạn không thể dễ dàng biết mọi chỗ không có vulnerability hoặc đã bị bỏ sót. Chỉ khi có **labeled benchmark/ground truth được kiểm soát**, confusion matrix mới có dữ liệu đầy đủ cho một population xác định.

Không suy **recall = 100%** chỉ vì tất cả findings được review và không có bug ngoài scanner được ghi nhận.

### 3.3. Công thức cơ bản

Với **TP, FP, TN, FN** đã được xác định trong cùng một tập đánh giá:

- **Precision (độ chính xác cảnh báo):** TP / (TP + FP). Trong các cảnh báo phát ra, bao nhiêu thực sự đúng?
- **Recall / True Positive Rate (độ bao phủ lỗi thật):** TP / (TP + FN). Trong các trường hợp có lỗi, scanner phát hiện bao nhiêu?
- **False Positive Rate (FPR):** FP / (FP + TN). Trong các trường hợp không có lỗi, bao nhiêu bị cảnh báo sai?
- **Specificity:** TN / (TN + FP).
- **False Discovery Rate (FDR):** FP / (TP + FP) = 1 − precision (khi mẫu số khác 0).
- **F1:** 2 × precision × recall / (precision + recall), khi có đủ dữ liệu.

**Chú ý:** “Tỷ lệ FP trong các alerts đã triage” = FP / tổng alerts được phân loại **khác** FPR = FP/(FP+TN). Trong vận hành SAST thường chỉ biết tập alerts đã được triage, nên dễ đo **FP proportion/precision ước tính**, khó tính FPR thật.

### 3.4. Ví dụ tính toán

Một benchmark có ground truth cho 200 cases:
- TP = 70
- FP = 20
- FN = 10
- TN = 100

Khi đó:
- Precision = 70 / (70 + 20) = **77,78%**.
- Recall = 70 / (70 + 10) = **87,50%**.
- FPR = 20 / (20 + 100) = **16,67%**.
- FDR = 20 / 90 = **22,22%**.
- Specificity = 100 / 120 = **83,33%**.

Các số này chỉ có ý nghĩa với **benchmark và điều kiện quét được định nghĩa**. Không được dùng để tuyên bố một scanner có cùng hiệu quả trên mọi Java service, framework, threat model hoặc ruleset.

### 3.5. Precision–recall trade-off

Một rule nhạy hơn có thể phát hiện nhiều bugs nhưng cũng tạo nhiều FP; một rule rất chặt có thể ít FP nhưng tăng FN. Mục tiêu của chương trình security assurance không chỉ tối thiểu FP, mà là **phát hiện risk quan trọng với chi phí triage hợp lý và không che vulnerabilities**.

Một detector cho **critical remote code execution** có thể ưu tiên recall cao với triage bổ sung. Một style rule có thể ưu tiên noise thấp. Sự đánh đổi phụ thuộc impact, trust boundary và năng lực vận hành.

## 4. Static analysis hoạt động và vì sao xuất hiện FP

### 4.1. Source → data flow → sink

Nhiều security SAST rules dựa trên mô hình **taint analysis**:

~~~mermaid
flowchart LR
    S["Source: user input"] --> P["Propagation qua biến/hàm"]
    P --> V["Validation / transformation"]
    V --> K["Sink: SQL, HTML, process, file, URL"]
    K --> F{"Rule/model cho rằng unsafe?"}
    F -->|"Có"| A["Finding"]
    F -->|"Không"| N["No finding"]
~~~

- **Source:** nơi dữ liệu không đáng tin đi vào, ví dụ request query, headers, message queue hoặc file.
- **Propagation:** các phép gán, concatenation, method calls, object fields.
- **Sanitizer/validator:** cơ chế có thể loại một số nguy cơ hoặc giảm mức taint **trong một context nhất định**.
- **Sink:** thao tác nhạy cảm như SQL execution, HTML rendering, OS command, URL fetch, filesystem access, deserialization.
- **Rule/model:** định nghĩa những đường/điều kiện nào đáng cảnh báo.

FP có thể xảy ra khi tool **không hiểu đầy đủ** một lớp bảo vệ hợp lệ hoặc suy rộng đường dữ liệu không thể xảy ra.

### 4.2. Những nguyên nhân kỹ thuật thường gặp

| Nguyên nhân | Tình huống | Cần xác minh |
|---|---|---|
| **Framework modeling thiếu** | Tool không biết prepared parameter binding của wrapper nội bộ | Wrapper thực sự bind, không nối SQL |
| **Custom sanitizer không được nhận diện** | Library escape HTML phù hợp context | Có sanitizer đúng sink/context/encoding? |
| **Path-insensitive analysis** | Tool gộp hai nhánh điều kiện loại trừ nhau | Control-flow/guard có thật ở runtime? |
| **Context-insensitive analysis** | Kết quả từ call site an toàn bị trộn call site khác | Function call context và arguments |
| **Alias/points-to imprecision** | Tool giả định hai object cùng trỏ dữ liệu | Đường tham chiếu thực và mutation |
| **Reflection/dynamic dispatch** | Có nhiều khả năng target được suy đoán rộng | Runtime wiring/configuration |
| **Dependency injection** | Spring bean được tool ánh xạ sai | Bean active/profile/qualifier thực |
| **Generated/test code** | Scanner thấy code không thuộc production | Build/test scope và asset mapping |
| **Unreachable/dead code** | Code không được đóng gói hoặc gọi trong release | Artifact và runtime reachability evidence |
| **Constant propagation yếu** | Giá trị hằng an toàn bị coi untrusted | Giá trị có thể đổi qua config/inputs không? |
| **Regex/heuristic pattern** | Comment chứa “password” bị coi secret | Credential có thật và dùng được không? |
| **Source type không chuẩn** | Tool gán mọi data field là user-controlled | Provenance nguồn dữ liệu |
| **Security library API chưa model** | Tool không biết route builder parameterized | Verify generated query/command |
| **Sanitizer overload/confusion** | Tool báo dù chính xác là safe wrapper | Kiểm tra mọi overload/version và bypass |

### 4.3. “Sanitized” phải đúng context

Một helper đặt tên **sanitize** không tự đảm bảo an toàn. Ví dụ:
- HTML escaping không thay SQL parameterization.
- URL encoding không ngăn SSRF nếu server được phép fetch arbitrary destinations.
- Regex xóa dấu nháy không giải quyết shell injection.
- Cắt chuỗi **../** không luôn ngăn path traversal qua symlink/encoding.
- JWT decode không tương đương verify signature/issuer/audience.
- Input length validation không thay authorization.

Một FP chỉ hợp lệ khi protection được xác minh theo **threat/sink thực**, không dựa vào tên method.

### 4.4. Static reasoning có giới hạn

SAST có thể:
- Quét nhiều code paths nhanh và lặp lại trong CI.
- Phát hiện patterns có độ phủ tốt theo language/rules.
- Cung cấp taint traces hữu ích để kiểm chứng.
- Kiểm tra code chưa có runtime.

Nhưng thường không nắm đủ business roles/tenants, runtime policies, vendor config, dynamic loading hay attack context. **Một finding cảnh báo cần triage, và một vùng scanner không cảnh báo vẫn cần security tests theo risk**.

## 5. Phân biệt FP với các trạng thái khác

### 5.1. Bảng quyết định

| Trạng thái | Ý nghĩa | Hành động/đầu ra |
|---|---|---|
| **True positive** | Vi phạm kỹ thuật theo rule thực sự có | Remediate, mitigate hoặc risk decision |
| **False positive** | Rule/tool đánh giá sai đối với target/conditions đã xác minh | Lưu rationale, scope, review, regression trigger |
| **Not applicable** | Requirement/weakness không áp dụng với artifact, platform hoặc feature trong scope | Ghi lý do phạm vi, evidence, reassess trigger |
| **Duplicate** | Hai finding records mô tả cùng weakness/root cause | Link finding gốc, không bỏ risk |
| **Fixed already** | Lỗi đã tồn tại trước đây nhưng build đang đánh giá đã sửa | Verify version/deploy, close theo evidence |
| **Mitigated** | Weakness còn nhưng control khác làm giảm exposure | Validate compensating control, residual risk |
| **Risk accepted** | Weakness/risk được chấp nhận có thẩm quyền và thời hạn | Decision record, monitoring, expiry |
| **Needs investigation** | Chưa đủ thông tin phân loại | Gather code/config/test evidence |
| **Scanner error / unassessed** | Scan không hợp lệ hoặc không chạy | Tool health remediation, rerun; không Pass |
| **Suppressed** | Finding bị ẩn/bỏ qua theo cơ chế kỹ thuật | Cần biết underlying rationale/status; suppression không đồng nghĩa FP |

### 5.2. True positive nhưng không exploitable trong điều kiện hiện tại?

Ví dụ rule phát hiện unsafe deserialization trong module chỉ chạy trong internal maintenance test harness, không có input từ untrusted users ở sản phẩm được deploy. Có thể là:
- **Not applicable** cho production runtime nếu harness không có trong artifact.
- **True positive with low current exposure** nếu code có mặt nhưng đường nhận untrusted input đang bị network/auth controls chặn.
- **Needs investigation** nếu không biết plugin có thể được kích hoạt hay không.

Không nên mặc định gọi FP từ một lời khẳng định “không ai gọi method đó”. Muốn kết luận cần xem build, call paths, entry points, configuration và threat assumptions.

### 5.3. Risk score không quyết định tính đúng/sai

Một finding CVSS thấp vẫn có thể là true positive. Một finding critical có thể bị false positive. **Severity/priority** nói về hậu quả và tính cấp thiết (theo phương pháp đánh giá), **verdict FP/TP** nói về việc detection có đúng không. Không gắn hai nhãn thành một.

### 5.4. Chưa tái hiện exploit không tự chứng minh FP

Không tái hiện được vì:
- Chưa có precondition phù hợp.
- Test không đến đúng code path.
- Environment thiếu feature/config.
- Payload chưa bao phủ variant.
- WAF/rate limit che behavior.
- Race/timing khó tái hiện.
- Tool runtime test không hỗ trợ protocol.
- Lỗi có impact gián tiếp, không có ngay HTTP response.

Một kết luận FP cần **lập luận tích cực dựa trên source/sink/guard/config**, không chỉ “tôi thử vài payload không được”.

## 6. Preflight trước khi triage một SAST finding

### 6.1. Chuẩn hóa dữ liệu đầu vào

Thu thập:
1. Finding ID và stable fingerprint.
2. Scanner tên/version/rule ID/version/CWE mapping.
3. Rule message và nguyên lý phát hiện.
4. Source revision, build target/module, scan timestamp.
5. File path, line range và data-flow trace.
6. Source API, propagation steps, sink API.
7. Severity/confidence và tài liệu rule.
8. Relevant code/config/framework/library versions.
9. Runtime/environment/build inclusion (nếu liên quan).
10. Link tới bug/incident/previous triage.
11. Owner và thời hạn triage theo risk.
12. Các warnings: unsupported language, partial analysis, disabled rules, failed upload.

### 6.2. Xác định target và population

Finding trên test module khác production service. Có thể có:
- Multi-module Maven/Gradle.
- Shared library dùng ở nhiều services.
- Dynamic profiles.
- Generated classes.
- Native/JNI dependencies.
- Multiple branches/releases.
- Containerized worker.
- Legacy batch export.
- Cloud function/queue consumer.

Không chỉ xem path trong repository. Hãy xác minh **code nào thực sự build/deploy và ai là owner**.

### 6.3. Chuẩn bị câu hỏi triage

- Rule khẳng định vulnerability gì, không chỉ có keyword nào?
- Dữ liệu đến từ nguồn nào? Có thật sự do attacker kiểm soát?
- Luồng có đi được đến sink không?
- Validation/encoding/parameterization nào tồn tại, ở đâu?
- Control có đúng cho mọi branches/overloads?
- Sink có thực sự nguy hiểm trong context đó?
- Có khác biệt giữa static assumptions và runtime behavior?
- Tool bỏ qua component/role/tenant/config nào?
- Có chứng cứ gì bác bỏ hoặc xác nhận từng bước?
- Những điều chưa biết là gì?
- Nếu FP, thay đổi nào có thể khiến verdict cũ mất hiệu lực?

### 6.4. Không thu thập secrets làm evidence

Bằng chứng nên là code diffs, sanitized logs, synthetic fixtures, approved test results. Không paste production password, API token, private key hoặc dữ liệu học viên vào ticket để chứng minh một cảnh báo là thật/sai.

## 7. Triage workflow có bằng chứng

### 7.1. Quy trình khuyến nghị

~~~mermaid
flowchart TD
    F["Finding mới từ SAST"] --> H["Kiểm tra scan health + target/build"]
    H --> K["Đọc rule + trace, xác định weakness"]
    K --> S["Phân tích source, guards, propagation, sink"]
    S --> C{"Có căn cứ đủ?"}
    C -->|"Có bug"| TP["True positive"]
    C -->|"Có căn cứ tool sai"| FP["False positive"]
    C -->|"Chưa"| U["Need more evidence"]
    U --> V["Code/config review + safe test"]
    V --> S
    TP --> R["Fix / mitigation / risk decision"]
    FP --> D["Rationale + bounded suppression nếu cần"]
    D --> G["Review, expiry và change triggers"]
    R --> T["Retest + deployment verification"]
    T --> A["Assurance evidence/closure"]
    G --> A
~~~

### 7.2. Triage phải có hai đầu ra

**Technical verdict:** cảnh báo mô tả weakness thật hay không, dựa trên chứng cứ trong phạm vi.

**Security/risk decision:** nếu có weakness, remediation priority hoặc compensating controls, acceptance có thẩm quyền. Đừng thay technical verdict chỉ để đưa KPI về mức mục tiêu.

### 7.3. Thứ tự ưu tiên triage

Ưu tiên có thể xét:
- Internet-facing, public inputs và privileged sinks.
- Sensitive data và tenant isolation.
- Known exploited classes/rule quality.
- CWE/weakness impact (RCE, authz bypass, injection).
- Confidence của data flow.
- Asset criticality và blast radius.
- Fix complexity và scope.
- Unknowns/uncertainty.
- Tool false positive history theo rule **nhưng không dùng history để auto-dismiss**.

Không chỉ sắp xếp theo severity của scanner. Một low-priority finding ở authorization boundary có thể nguy hiểm hơn một high-severity heuristic trong test fixture.

### 7.4. Triage SLA và reviewer

Tổ chức nên có deadline theo risk, owner và reviewer tier. Ví dụ các findings có high-impact security boundary cần AppSec hoặc reviewer chuyên môn trước suppression, còn style rule có thể do tech lead xử lý. Đây là quyết định nội bộ, **không có một SLA phổ quát**.

### 7.5. Dấu hiệu phải escalate

- Nhiều call paths hoặc component cùng báo.
- Rule liên quan critical weakness và control khó chứng minh.
- Taint trace không rõ, dynamic/reflection và runtime context phức tạp.
- Mitigation chỉ dựa vào WAF hoặc network assumptions thay đổi thường xuyên.
- Finding có thể dẫn tới cross-tenant data exposure.
- Supplier component/version mapping ambiguous.
- Developer muốn suppress rộng toàn repository.
- Không có owner, missing tests hoặc scanner job health kém.

## 8. Case Java: SQL injection bị báo sai bởi wrapper

### 8.1. Vấn đề

Một Java API cho giảng viên lọc điểm theo classId. Tool đánh dấu **classId từ HTTP request → repository → SQL execution** là tainted. Trong implementation đã có parameter binding, nhưng wrapper nội bộ chưa được engine mô hình hóa.

~~~java
public List<GradeRow> findGrades(
        AuthenticatedPrincipal principal,
        long classId) {

    String query = """
        SELECT id, learner_id, grade
        FROM grades
        WHERE tenant_id = ? AND class_id = ?
        """;

    return jdbcTemplate.query(
            query,
            gradeRowMapper,
            principal.tenantId(),
            classId
    );
}
~~~

### 8.2. Vì sao finding có thể FP?

- SQL statement là **hằng**, không ghép input thành SQL syntax.
- Library API trong cấu hình này dùng **bind parameters** cho values.
- Parameter list tách biệt text query.
- Không có dynamic ORDER BY, table name hay raw SQL nối vào query.
- Actual code path đúng build được scan.
- Mapping/library version xác nhận semantics.
- Các overloads/call sites có thể khác cần xem riêng.

Nếu engine coi mọi chuỗi “đi vào query” là SQL injection, model của sink có thể quá rộng. **Review code và API contracts**, có thể dùng integration test chứng minh input là data.

### 8.3. Nhưng còn risk nào khác?

Đoạn code trên chưa chứng minh principal.tenantId() là identity được xác minh hoặc principal có quyền xem **classId**. Nếu endpoint cho teacher trong tenant A xem mọi lớp tenant A nhưng policy chỉ cho lớp được phân công, vẫn có **BOLA**. Phân loại SQLi là FP không đồng nghĩa policy authorization đạt.

### 8.4. Rationale mẫu

> **Verdict:** False positive cho rule SQL injection tại call site X trên source revision Y. Query text được định nghĩa cố định; giá trị tenantId và classId được JDBC bind vào placeholders qua API overload được xác minh. Không có input tham gia tạo SQL syntax trong path này; integration test với ký tự đặc biệt và code review xác nhận. **Scope:** call site đã kiểm tra, JDBC version/config ghi trong evidence. **Exclusions:** authorization và các dynamic queries khác không được kết luận từ review này. **Reassess:** khi wrapper/overload/query construction thay đổi.

Rationale tốt có **đối tượng, lý do kỹ thuật, evidence và giới hạn**, không chỉ ghi “false positive – library safe”.

## 9. Case Java: khi nào SQL injection warning là true positive?

### 9.1. Query text bị nối từ input

~~~java
// Anti-pattern: value không được bind.
String query =
        "SELECT * FROM grades WHERE class_id = "
        + request.getParameter("classId");

Statement statement = connection.createStatement();
ResultSet rows = statement.executeQuery(query);
~~~

Với data từ request đi vào **SQL syntax**, finding phù hợp. Lập luận “classId chỉ là số” không đủ khi không có server-side parsing/type enforcement đúng và query construction an toàn.

### 9.2. Trường hợp tưởng đã fix nhưng vẫn nguy hiểm

~~~java
// Value được bind; nhưng sortColumn đi trực tiếp vào SQL syntax.
String query =
        "SELECT id, grade FROM grades WHERE class_id = ?"
        + " ORDER BY " + request.getParameter("sortBy");

PreparedStatement statement = connection.prepareStatement(query);
statement.setLong(1, classId);
~~~

Binding classId **không bảo vệ sortBy**. Vì identifier/direction không thể dùng placeholder giá trị thông thường trong SQL syntax, cần allowlist và explicit mapping từ enum của client sang identifiers được phép ở server.

### 9.3. Triage đúng

- SQLi ở classId được xử lý bằng bind: có thể FP đối với classId path.
- SQLi ở sortBy vẫn là TP.
- Tenant scoping và DB least privilege là requirement khác.
- Nếu scanner báo chung một line, reviewer phải **tách sinks/data flows** và không suppress toàn method khi còn đường nguy hiểm.

## 10. Case Java: XSS và output encoding theo context

### 10.1. Cảnh báo XSS bị gắn ở vị trí template

Giả sử một controller trả phần **displayName** được đưa vào một template có auto-escaping trong HTML text context. SAST engine thấy dữ liệu từ profile đi đến template renderer và báo XSS.

~~~java
@GetMapping("/profile")
public String profile(Model model, AuthenticatedPrincipal principal) {
    UserProfile profile = profileService.loadFor(principal);
    model.addAttribute("displayName", profile.displayName());
    return "profile"; // Template engine xử lý HTML output.
}
~~~

Nếu template hiển thị displayName bằng cú pháp **escaped text output** theo framework/version/config đã xác minh, một finding dựa trên giả định output raw có thể là FP. Nhưng câu “template engine mặc định escape” chỉ là đầu mối, không phải evidence đầy đủ.

### 10.2. Những câu hỏi bắt buộc

- Đây là **HTML text**, attribute, JavaScript, CSS hay URL context?
- Template dùng escaped expression hay unescaped/raw HTML construct?
- Auto-escaping có bật tại đúng engine/version/template không?
- Dữ liệu đi qua client-side rendering/DOM methods tiếp theo?
- Có dùng custom helper/sanitizer hoặc URL resolver khác?
- Rich text có được sanitize theo allowlist trước khi render không?
- Có stored XSS trong admin dashboard/email/notification không?
- Có output path nào ghép vào inline JavaScript?
- Content Security Policy là defense in depth, không thay context-specific encoding.

### 10.3. Cùng giá trị, khác context

| Output context | Nhu cầu bảo vệ | Đánh giá FP |
|---|---|---|
| HTML text | HTML entity encoding theo template context | Có thể FP nếu auto-escaping được chứng minh |
| HTML attribute | Attribute encoding và tránh dangerous attribute contexts | Không suy từ HTML text test |
| JavaScript string/data | Safe serialization/context-aware handling; tránh nối script | HTML escaping thường không đủ |
| URL/redirect | Validate scheme/destination/policy; encode đúng URL component | Không suy từ HTML escaping |
| Rich HTML | Proven sanitizer/allowlist và renderer safe | Raw render có thể còn TP |
| DOM sink | Dùng textContent hoặc safe DOM APIs thay innerHTML khi phù hợp | Backend encoding chưa đủ nếu frontend reinterprets |

**Một sanitizer có thể đúng ở context A nhưng sai ở context B.** Không suppress mọi XSS warnings chỉ vì thấy tên function là escapeHtml.

### 10.4. Test xác minh

Dùng **synthetic payloads** trong môi trường được phép, kiểm tra:
- Output không chạy active script theo policy.
- Nội dung hợp lệ vẫn hiển thị.
- Client JavaScript không dùng unsafe sink.
- Template config/escaping được xác minh trên **deployed build**.
- Stored content hiển thị ở các views/roles relevant.
- Không lộ dữ liệu qua errors/logs.
- Tool FP suppression chỉ áp dụng đúng call site/context.

### 10.5. Kết luận đúng

Nếu finding chỉ khẳng định direct XSS qua HTML text mà template escape đúng, có thể FP cho **đường render này**. Nhưng cần mở finding riêng hoặc tiếp tục investigation nếu có unsafe raw HTML path. Không biến FP của một view thành “mọi dữ liệu user đều an toàn”.

## 11. Case Java: SSRF, destination allowlist và hạn chế của analyzer

### 11.1. Một URL đến HTTP client chưa đủ để kết luận

Giả sử code có tính năng import tài liệu từ URL. SAST báo **Server-Side Request Forgery (SSRF)** vì giá trị nhận từ request đi vào HTTP client.

Nếu endpoint chỉ cho user chọn một **partner ID** rồi server lấy URL đã được duyệt từ config bất biến có kiểm soát, cảnh báo dựa trên giả định user tự đặt arbitrary destination có thể là FP theo đúng data flow. Nhưng cần xem:
- Partner config có thật sự được kiểm soát? Ai có thể sửa?
- Parameter có ảnh hưởng tới host/scheme/port/path nào?
- HTTP client có theo redirects đến địa chỉ ngoài policy?
- DNS resolve/rebind/IPv6/private/link-local destinations được bảo vệ?
- Network egress có hạn chế?
- Headers/tokens có bị tự động forward?
- URL parsing/canonicalization có đúng?
- API có nhánh legacy cho phép raw URL?
- Plugin/config runtime có đổi target mà tool không nhìn thấy?

### 11.2. Thiết kế reduce attack surface

~~~java
// Mẫu khái niệm: server chỉ chọn endpoint từ danh sách
// đối tác đã được phê duyệt; user không nhập arbitrary URL.
URI url = approvedPartnerEndpoints.get(partnerId);
if (url == null) {
    throw new IllegalArgumentException("Unknown partner");
}
PartnerDocument document = restrictedPartnerClient.fetch(url);
~~~

**Code này chưa đủ** chứng minh hết SSRF: approvedPartnerEndpoints có thể chứa URL không đáng tin, restrictedPartnerClient có thể theo redirect, egress policy có thể không enforce. Phải xem configuration và runtime behavior.

### 11.3. Phân loại chính xác

- Client chỉ gọi URL hardcoded/trusted, không bị user tác động → finding về arbitrary destination có thể FP khi đã xác minh source provenance.
- User có thể nhập URL ngoài policy, nhưng WAF chặn một số IP → có thể là TP được mitigated, không tự FP.
- User chọn partner ID nhưng config do tenant admin tùy ý sửa → cần xét actor capabilities, không vội FP.
- Scanner không thấy data flow do resolver wrapper → có thể **false negative**, cần test thêm.

### 11.4. Bằng chứng cần

Data-flow analysis từ request đến destination, config ownership/permissions, client redirect policy, DNS/IP validation/egress controls, tests trong môi trường cô lập và phạm vi deployment. Không gọi yêu cầu “chặn localhost” là SSRF prevention đầy đủ.

## 12. Case Java: path traversal và canonicalization

### 12.1. Tại sao scanner dễ báo

Khi thấy **filename từ request → Files.readAllBytes**, SAST có thể cảnh báo traversal. Một cách xử lý thường thấy:

~~~java
Path base = Path.of("/srv/learning/uploads").toAbsolutePath().normalize();
Path candidate = base.resolve(userProvidedName).normalize();

if (!candidate.startsWith(base)) {
    throw new SecurityException("Out of allowed directory");
}
return Files.readAllBytes(candidate);
~~~

Đây là **mô hình kiểm tra đường dẫn**, không phải một solution production đầy đủ; symlinks, race/TOCTOU, platform behavior và quyền hệ thống có thể ảnh hưởng.

### 12.2. Cạm bẫy khi phân loại FP

Một reviewer thấy **normalize()** và **startsWith(base)** rồi đánh FP ngay. Nhưng:
- candidate có thể trỏ qua symlink ngoài base;
- check/use race có thể thay target giữa hai bước;
- relative base, encoded separators hoặc file permission scopes khác;
- user có thể tự đổi symlink trong upload folder;
- file ID/tenant authorization chưa được kiểm tra;
- service chạy với quyền filesystem quá rộng.

Nếu chưa kiểm soát những điều kiện này, một finding vẫn có thể là **true positive hoặc needs investigation**.

### 12.3. Thiết kế an toàn hơn

Thay vì cho user nhập filesystem path, nhận **opaque file ID**, tra storage key ở repository server-side, kiểm tra principal–tenant–file ownership, dùng object storage/controlled root và hạn chế process permissions. Nếu vẫn thao tác filesystem, cần safe resolution/open primitives phù hợp và xử lý symlink/race theo threat model.

### 12.4. Khi nào có thể FP?

Một API thực tế chỉ nhận server-generated file reference, source-of-truth mapping không do user sửa, storage API chặn path traversal và scanner chỉ thấy tên biến "filename" mà suy user-controlled path. Cần:
- xác minh source và mapping;
- scope liên quan file ID/ownership;
- code/storage implementation;
- positive/negative tests và deployment config;
- không có alternate path chấp nhận raw filenames.

**FP cho traversal không tự chứng minh không có BOLA trong file download.**

## 13. Case Java: hardcoded credentials và test fixtures

### 13.1. Heuristic scan có thể bị nhiễu

Scanner tìm chuỗi như "password", "token", "secret" hoặc chuỗi entropy cao. Ví dụ:

~~~java
// Test fixture rõ ràng không được chấp nhận làm credential thật.
private static final String SYNTHETIC_PASSWORD =
        "example-only-not-a-real-secret";
~~~

Nếu scanner báo exposed production credential cho fixture được chứng minh là fake/test-only, finding có thể FP theo rule **secret leak thực** hoặc not applicable theo taxonomy tool. Tuy nhiên **test-only source cũng có thể chứa secret thật**; không nên auto-accept mọi file trong thư mục test.

### 13.2. Phân biệt string và credential

Cần kiểm tra:
- Chuỗi có dùng làm credential ở đâu không?
- Nó có cấp quyền tới service thật không?
- Có bị dùng chung giữa test/staging/production không?
- Có từng hoạt động trong quá khứ không?
- Có xuất hiện trong Git history, image, artifact, logs?
- Test fixture có thể được pack vào production không?
- Có secrets manager reference thay cho raw secret không?
- Scanner rule chỉ là keyword hay provider-specific validator?
- Token có còn hiệu lực, có cần revoke/rotate không?

**Không in hoặc thử xác thực bằng secret thật tùy tiện** để chứng minh. Dùng secure owner confirmation, secret inventory/rotation evidence và synthetic canaries theo quy trình.

### 13.3. Kết quả triage

| Observation | Verdict phù hợp |
|---|---|
| Chuỗi giả được tạo rõ cho test, không có authority và không được dùng ngoài fixture | FP/not applicable theo rule taxonomy, kèm evidence |
| Password thật hardcoded trong Java production | TP, cần khắc phục và rotate |
| Credential cũ đã revoke nhưng vẫn trong history | Không mặc định FP; cần exposure, retention và risk assessment |
| Dummy password dùng trong deployment demo reachable | Cần xem default credential risk, có thể TP |
| Code chỉ có secret reference URI, không có secret value | Có thể FP nếu rule nhầm reference thành secret |
| Vendor token đã bị masking | Verify actual unmasked value không xuất hiện; không chỉ tin UI mask |

### 13.4. Không dùng suppression thay secret rotation

Nếu credential thật lộ, suppression chỉ làm scanner im lặng. Remediation có thể cần **revoke/rotate, remove exposure, inspect history/artifacts/log sinks, incident response và regression tests**. Phân loại FP không phù hợp chỉ vì developer đã xóa dòng code trên nhánh hiện tại.

## 14. Case Java: authentication/authorization và business logic

### 14.1. Tool có thể không hiểu security annotations

Ví dụ một controller được bảo vệ bởi Spring Security policy, custom permission evaluator hoặc filter chain. SAST có thể báo "missing authorization" do không phân tích được framework-specific enforcement.

~~~java
@GetMapping("/classes/{classId}/grades")
public GradeReport getGrades(
        @PathVariable long classId,
        Authentication authentication) {

    AuthenticatedPrincipal actor =
            principalFactory.fromVerifiedAuthentication(authentication);
    return gradeService.getAuthorizedGrades(actor, classId);
}
~~~

Nếu gradeService kiểm tra đúng actor–tenant–class, finding "không có authorization" chỉ vì controller không có annotation có thể là FP. Nhưng phải xác minh **service implementation, endpoint/filter config, method security, direct paths và test semantics**.

### 14.2. Role không phải object authorization

Một đoạn:

~~~java
if (!actor.hasRole("TEACHER")) {
    throw new AccessDeniedException("Denied");
}
return gradeRepository.findGradesByClassId(classId);
~~~

Không đủ nếu mỗi teacher chỉ được xem lớp được phân công. **Scanner không báo** không làm code này an toàn; đây là ví dụ **false negative về business authorization** nếu policy yêu cầu per-object check.

### 14.3. Muốn kết luận FP cần xem

- Principal đến từ authentication context được xác minh.
- Role/permission có đúng scope/tenant.
- Quan hệ actor–resource được enforce trên mọi code path.
- Cache/queue/worker/download path không bypass.
- Tests dùng **hai actors có quyền khác nhau và resources không thuộc quyền**.
- Có audit allow/deny và no unauthorized side effects.
- Không có config profile bỏ security filters.
- Ownership/risk context được ghi.
- Reviewer độc lập khi risk cao.

### 14.4. Ba kết luận có thể cùng tồn tại

Với một SAST finding "No authorization annotation":
- **False positive** nếu rule giả định annotation bắt buộc nhưng policy enforce đúng trong service.
- **True positive** nếu service thực tế thiếu object authz.
- **Not applicable** nếu function chỉ nằm trong test harness không deploy.

Không biến một config annotation là "safe" thành câu trả lời cho mọi threat về authorization.

## 15. Case Java: cryptography và rule heuristic

### 15.1. “Hardcoded IV”, “weak random” hoặc “weak hash”

Một tool có thể báo:
- Sử dụng **Random** thay SecureRandom cho token.
- SHA-256 dùng để lưu mật khẩu thay password hashing phù hợp.
- IV/nonce cố định trong chế độ cần uniqueness.
- Tắt TLS certificate validation.
- Hardcoded encryption key.
- Use of MD5/SHA-1 với mục đích khác nhau.

Các cảnh báo này phải được xem theo **security purpose**, không chỉ theo tên API.

### 15.2. Cùng hash API, mục đích khác nhau

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
byte[] sha256 = digest.digest(binaryArtifactBytes);
~~~

Nếu đoạn này dùng SHA-256 để **kiểm tra digest của artifact bytes** trong context phù hợp, một rule khẳng định "weak password storage" có thể là FP vì đây không phải password hashing. Nhưng nếu dùng:

~~~java
byte[] storedPassword =
        MessageDigest.getInstance("SHA-256")
                .digest(userPassword.getBytes(StandardCharsets.UTF_8));
~~~

thì raw SHA-256 đơn thuần **không phải** phương pháp lưu mật khẩu phù hợp vì thiếu work factor/memory-hardness/salt policy. Đây có thể là TP đối với "weak password storage".

### 15.3. Nonce/IV và context

Một hằng số IV dùng trong unit test để kiểm tra một known-answer test vector khác **hằng số IV được tái sử dụng trong production encryption**. Nhưng nếu test vector code được reuse bởi production helper hoặc output thật dùng IV cố định, cần cảnh giác.

### 15.4. Khác biệt giữa cryptographic validity và compliance

Một thuật toán có thể không phù hợp policy/hợp đồng dù chưa thấy attack cụ thể. Một finding “algorithm not approved by policy” có thể là **true-positive compliance/control issue** ngay cả khi reviewer cho rằng chưa có exploit. Đừng gọi FP chỉ vì “không ai phá được cipher”.

## 16. False positives trong dependency và configuration analysis

### 16.1. SCA không đồng nghĩa SAST

**Software Composition Analysis (SCA)** xác định packages/dependencies và đối chiếu advisory, còn **SAST** phân tích code/pattern/data flow. Cả hai tạo findings, nhưng các cơ chế FP khác nhau.

Ví dụ SCA FP có thể do:
- Package identity nhầm giữa forks/products.
- CPE mapping quá rộng.
- Version đã backport patch nhưng string trông cũ.
- Package không nằm trong release artifact scan scope.
- Advisory không áp dụng architecture/platform/configuration đó.
- Duplicate packages hoặc vendor metadata sai.

Những finding này cần **SBOM/component identity, deployed artifact mapping, vendor advisories và VEX/risk evidence**. Không dùng quy trình taint source/sink cho mọi SCA issue.

### 16.2. “Vulnerable package có trong image” nhưng không khai thác được?

Nếu package tồn tại với affected code nhưng attack path bị hạn chế, nó có thể là **true positive component vulnerability** với lower exploitability hoặc **not affected** theo VEX có supporting evidence tùy định nghĩa/trạng thái. Không nên tự gọi SCA FP vì không thấy network port Internet-facing; mã có thể bị gọi qua queue, admin path hoặc privilege escalation.

### 16.3. IaC/configuration FP

Một IaC scanner báo S3 bucket public trong template, nhưng stack deployment đã loại resource theo conditional hoặc quyền tổ chức chặn public access. Cần xem:
- IaC effective compiled plan.
- Actual cloud resources và IAM policies.
- Accounts/regions/environment.
- Public/anonymous access negative tests.
- Kết hợp control ở org/account/resource.
- Drift/out-of-band changes.
- Tool rule semantics: cảnh báo **config declaration** hay **effective exposure**?

Nếu rule yêu cầu "template phải khai báo block public access" để tuân policy, dù cloud org policy đang chặn, finding có thể vẫn là **true-positive policy compliance issue**. Kết luận FP phụ thuộc **định nghĩa requirement**, không chỉ outcome hiện tại.

## 17. Confidence và severity trong triage

### 17.1. Chỉ số scanner không thay chứng cứ

Một tool có thể gắn:
- Severity: Critical/High/Medium/Low.
- Confidence: High/Medium/Low.
- Likelihood/exploitability score.
- CWE/OWASP mappings.
- Rule-specific priority.

Đây là **metadata hỗ trợ phân loại**, không tự xác định technical truth. “High confidence” vẫn có thể FP khi framework semantics sai, “Low severity” vẫn có thể TP.

### 17.2. Đánh giá hai trục

| Technical validity | Business/risk impact | Quyết định |
|---|---|---|
| TP | High | Fix/contain ưu tiên, tests và evidence |
| TP | Low | Fix theo policy hoặc risk decision; không gọi FP |
| FP | Severity tool cao | Bác bỏ với evidence, update detector/model |
| Uncertain | Potentially high | Escalate, điều tra, safeguards tạm |
| Not applicable | Không có trong target scope | Ghi scope/config/build evidence |
| Mitigated TP | Residual risk có thể thấp | Validate control, risk acceptance nếu cần |

### 17.3. Không có exploit PoC vẫn có thể TP

Vulnerability validity có thể được xác nhận bằng **code data flow và policy violation** mà không cần dựng exploit hoàn chỉnh. Ngược lại, một exploit failure đơn lẻ không đủ bác bỏ. Hãy chọn level of proof **phù hợp risk và loại weakness**.

## 18. Quản lý suppressions: chặn noise mà không che rủi ro

### 18.1. Suppression là quyết định kỹ thuật, không phải verdict

Các công cụ có thể hỗ trợ:
- **Inline suppression:** annotation/comment tắt rule tại dòng/method.
- **File/path exclusion:** bỏ một file/thư mục.
- **Rule disable:** tắt rule cho module/project.
- **Baseline:** giữ findings đã biết ngoài gate cho code mới.
- **Triage state:** mark false positive/accepted/snoozed trên nền tảng quản lý.
- **Custom sanitizer model:** dạy tool semantics an toàn của helper.
- **Configuration tuning:** scope sources/sinks, severity, tags, framework profile.

Tùy tool, chúng có thể ảnh hưởng **reporting, detection hoặc gate** khác nhau. Cần hiểu chính xác mechanism trước khi sử dụng.

### 18.2. Thứ tự ưu tiên xử lý

1. **Xác minh finding:** không suppress khi chưa triage.
2. **Sửa code nếu TP** (hoặc quản lý mitigation/risk theo thẩm quyền).
3. Nếu FP vì model thiếu, **cập nhật model/sanitizer/sink** theo cách chứng minh được.
4. Nếu chỉ một call site có FP, áp dụng **suppression hẹp**, gắn rationale và owner.
5. Tránh tắt **toàn rule hoặc entire repository** để loại một vài findings.
6. Thêm regression tests cho tool behavior và code semantics.
7. Theo dõi expiry, code/rule/tool changes và unreviewed suppressions.

### 18.3. Ví dụ comment suppression có trách nhiệm

~~~java
// SAST-SUPPRESSION: SEC-FP-EXAMPLE-12
// Rule: SQL_INJECTION
// Scope: this JDBC call site only.
// Rationale: query is constant and values are bound as parameters.
// Evidence: security review SEC-REV-EXAMPLE-42 and integration test.
// Reviewer: AppSec reviewer assigned by policy.
// Reassess on: query builder or JDBC wrapper changes.
// <tool-specific suppression directive only if supported and approved>
return jdbcTemplate.query(SQL, mapper, tenantId, classId);
~~~

**Đây là comment mẫu, không phải directive cú pháp của một SAST tool cụ thể.** Trong code thật, điền ticket, reviewer, expiry/review trigger và dùng syntax chính thức được duyệt. Không ghi comment dài chứa secrets hoặc raw payload.

### 18.4. Suppression rộng có thể gây false negatives

Nếu loại toàn thư mục **src/main/java** hoặc disable rule SQLi để né FP trong một helper, tool có thể bỏ qua SQL injection thật phát sinh sau này. Vì vậy cần đo:
- Scope bị loại.
- Rule coverage trước/sau.
- Khả năng scan có synthetic seeded TP.
- Approval và expiry.
- Owner và lịch review.
- Logs về suppression changes.

### 18.5. Baseline nên có giới hạn

Dùng baseline để **không chặn toàn bộ repository bởi technical debt** có thể hợp lý, nhưng cần:
- Baseline fingerprint ổn định.
- Mỗi finding có status/risk owner/plan.
- New findings không bị baseline nuốt.
- Re-open khi code line/rule/impact thay đổi.
- Periodic review và expiry hoặc kế hoạch giảm nợ.
- Báo cáo **open existing risk** tách khỏi new PR risk.

Baseline không phải “miễn kiểm tra vĩnh viễn” cho mọi dòng code cũ.

### 18.6. Không dùng false-positive label cho risk acceptance

Nếu developer chấp nhận unauthenticated admin endpoint vì "chỉ mạng nội bộ", đó là **TP với network mitigation/accepted risk**, không phải FP. Bỏ nhãn technical vulnerability làm sai risk register và có thể dẫn tới bypass khi network topology đổi.

## 19. Hồ sơ triage có thể kiểm chứng

### 19.1. Những trường nên có

Một quyết định triage cần **traceability và tính lặp lại**. Đề xuất metadata:

| Trường | Ý nghĩa |
|---|---|
| Finding ID + fingerprint | Nhận diện cảnh báo qua lần scan/line move |
| Rule ID/version | Tool đang đánh giá điều kiện gì |
| Tool/version/config | Phân biệt thay đổi detector/analysis |
| Source commit/module | Phiên bản code được xét |
| File/line/method/sink | Call site được xét; line có thể thay |
| Weakness/CWE | Vấn đề chính xác đang bị cáo buộc |
| Data-flow summary | Source, propagation, guards, sink |
| Security context | Trust boundary, actors, data/resource |
| Verdict | FP/TP/not applicable/mitigated/needs investigation... |
| Technical rationale | Căn cứ code/config/semantic |
| Supporting evidence | Link code diff/test/tool docs (không nhúng secrets) |
| Scope/exclusions | Chỉ path/build/variant nào được kết luận |
| Confidence/uncertainty | Mức chắc chắn và điều chưa kiểm tra |
| Owner/reviewer/decision date | Accountability |
| Suppression rule/scope | Cơ chế nếu dùng |
| Expiry/reassess triggers | Khi nào kiểm tra lại |
| Build/deployment linkage | Phù hợp nếu claim nói về artifact đang chạy |
| Residual risk/related findings | Không gộp kết luận sai rule với những risk khác |

### 19.2. YAML record minh họa

Đây là **schema nội bộ minh họa**, không phải format chuẩn của một SAST vendor.

~~~yaml
triage_id: "FP-LEARNING-2026-EXAMPLE-01"
finding:
  id: "SAST-EXAMPLE-145"
  fingerprint: "replace-with-stable-fingerprint"
  tool: "example-static-analyzer"
  tool_version: "populate-actual-version"
  rule_id: "JAVA_SQL_INJECTION"
  rule_version: "populate-rule-version"
  weakness: "untrusted value reaches SQL execution"
  file: "learning-api/src/main/java/.../GradeRepository.java"
  method: "findGrades"
  line: "populate-reviewed-range"
source:
  repository_revision: "populate-commit-id"
  module: "learning-api"
  build_profile: "populate-build-profile"
technical_analysis:
  source: "request.classId (parsed long)"
  propagation: "controller -> service -> JDBC repository"
  sink: "parameterized JDBC query"
  guard:
    - "constant SQL text"
    - "values passed to JDBC bind parameters"
  verdict: "FALSE_POSITIVE"
  rationale: >
    Tool models a value reaching query execution but does not recognize
    the reviewed JDBC overload binds the value, not SQL syntax.
  known_limits:
    - "Only this call site and reviewed build"
    - "Object-level authorization is assessed separately"
evidence:
  code_review: "link-to-reviewed-diff"
  library_api_contract: "link-to-verified-api-version"
  integration_test: "link-to-synthetic-test-run"
review:
  technical_owner: "Learning Backend"
  approver: "AppSec reviewer"
  decided_at: "populate-timestamp"
suppression:
  type: "call-site-only-if-needed"
  reference: "link-to-suppression-change"
  expires_or_reassess_on:
    - "SQL construction or JDBC wrapper change"
    - "Analyzer or rule model change"
    - "New entry point or tenant scope"
related_risk:
  - "BOLA/object authorization handled by separate requirement"
status: "TRIAGED_WITH_EVIDENCE"
~~~

### 19.3. Không tin template tự bảo đảm sự thật

Mẫu có đủ các field nhưng nội dung rationale có thể sai hoặc stale. Reviewer phải xem **code và API semantics đúng phiên bản**, kết quả test và scope. Việc có ticket/evidence link là điều kiện truy vết, chưa đủ cho technical validity.

### 19.4. Rationale phải bác bỏ đúng cáo buộc

Ví dụ thông tin không đủ:

> Đã xem. Code an toàn. False positive.

Ví dụ tốt hơn:

> Rule JAVA_SQL_INJECTION báo từ request classId đến JdbcTemplate.query ở call site A. SQL literal không thay đổi theo input; overload được gọi bind cả tenantId và classId như parameters trên JDBC implementation/version B. Code review và integration test C xác minh không có SQL syntax manipulation ở path này. Verdict FP chỉ cho SQL injection tại call site A; tenant authorization và các queries khác thuộc đánh giá riêng.

**Một rationale tốt phải đọc được độc lập**, không cần reviewer nhớ toàn bộ lịch sử chat hoặc hỏi tác giả tại sao đã suppress.

## 20. Finding identity, SARIF và deduplication

### 20.1. Vì sao số dòng không phải định danh vững chắc?

Một SAST finding có thể đổi:
- File line number do format.
- Path do refactor.
- Rule identifier sau tool upgrade.
- Method name do extract.
- Message text do localization.
- Severity do policy update.

Nếu chỉ matching theo **file:line** thì moving code có thể khiến hệ thống xem finding cũ đã biến mất và tạo finding mới; cả triage history và CI gate đều sai.

### 20.2. Fingerprint nên bao gồm yếu tố ổn định

Tùy tool có thể kết hợp:
- Rule ID và weakness class.
- Semantic code location hoặc method signature.
- Source–sink path identity.
- Tokenized/syntax context.
- Repository/project/module identity.
- Artifact/branch/source revision liên quan.
- Tool-provided stable fingerprint.

Không có thuật toán fingerprint hoàn hảo; phải quản lý **collisions, duplicates, split/merge findings và rule migrations**.

### 20.3. SARIF

**SARIF (Static Analysis Results Interchange Format)** là một format trao đổi kết quả phân tích tĩnh, thường dùng để mô tả runs, tools/rules, results, locations, code flows và fingerprints khi các producer cung cấp. SARIF giúp nhập/quản lý findings giữa pipeline và issue trackers; nó **không chứng minh finding là TP hoặc FP**.

Một SARIF result có thể mang ruleId, location, message và fingerprint, nhưng **triage verdict/risk/evidence của tổ chức** vẫn cần được quản lý trong hệ thống có governance. Không mặc định mọi producer/consumer bảo toàn mọi property/extension qua conversion.

### 20.4. Khi rule ID thay đổi

- Lưu mapping old/new rules.
- Xác định detection semantics có thực sự tương đương không.
- Re-review suppressions dựa trên rule cũ.
- Không tự close all old findings do ID biến mất.
- Chạy comparison/seeded tests và ghi coverage delta.
- Giữ provenance run/version để audit.
- Mở findings mới khi rule mới phát hiện variant.

### 20.5. Deduplicate nhưng không gộp sai root causes

Một method có thể có hai unsafe sinks hoặc hai trust boundaries. Hai scanner alerts giống nhau về line chưa chắc duplicate. Nên gộp khi có **same underlying weakness/fix** và giữ links tới affected paths; không gộp SQLi và BOLA chỉ vì cùng controller.

## 21. Hiệu chỉnh rule và custom models để giảm false positives

### 21.1. Tune model thay vì tắt rule

Nếu công cụ báo sai hàng trăm lần trên cùng một **prepared query wrapper**, giải pháp bền vững có thể là:
- Tạo custom sink/source/sanitizer models đúng APIs.
- Điều chỉnh rule predicates dựa trên framework semantics.
- Thêm typed API annotations khi tool hỗ trợ.
- Sửa project scan configuration để chỉ quét build target cần thiết.
- Nâng analyzer version sửa framework model.
- Báo bug/submit minimal reproducible case cho tool vendor.
- Chạy seeded TP/FP regression test trước áp dụng rộng.

**Không dạy tool “mọi method tên safeSql() đều an toàn”** nếu wrapper có overload nhận raw query fragments.

### 21.2. Ví dụ wrapper có overload khác nhau

~~~java
// Overload 1: values bound to placeholders.
public List<Row> safeQuery(String constantSql, Object... bindValues) {
    return jdbcTemplate.query(constantSql, mapper, bindValues);
}

// Overload 2: raw fragments inserted into query syntax.
// Tên method có thể làm tool/reviewer hiểu nhầm.
public List<Row> safeQuery(String prefix, String rawSortClause) {
    return jdbcTemplate.query(prefix + rawSortClause, mapper);
}
~~~

Nếu custom model đánh dấu **cả hai overloads** là sanitizer, scanner có thể bỏ **true positives** của overload 2. Cần model theo **full signature, argument position và semantics**, test bản thân model bằng examples.

### 21.3. Data-flow model test cases

Một custom model tốt nên có:
- **Safe case:** binding thông qua overload được duyệt không bị báo SQLi.
- **Unsafe case:** raw string concatenation vẫn bị báo.
- **Mixed case:** one bound value + one untrusted raw fragment vẫn bị báo.
- **Alias/indirect wrapper case:** helper gọi qua nhiều layers.
- **Overload case:** chỉ overload an toàn được coi sanitizer.
- **Regression case:** khi API implementation đổi thì model/test fail hoặc yêu cầu review.
- **Version scope:** không dùng model cho library version khác nếu semantics thay.

### 21.4. Framework upgrades

Một SAST model chính xác với framework phiên bản A có thể sai với B. Nâng Spring, Hibernate, template engine, JSON mapper hay security plugin cần:
- Re-run FP/TP fixtures.
- Review data-flow assumptions.
- Revalidate custom annotations.
- Compare scan coverage/quality.
- Reassess suppressions dựa trên framework behavior cũ.

### 21.5. Chi phí triage và rủi ro chung

Không phải mọi FP đều xứng đáng viết custom model phức tạp. Chọn giải pháp dựa trên:
- Số findings lặp lại.
- Mức impact nếu rule bị model sai.
- Tool support và khả năng test model.
- Số codepaths share wrapper.
- Maintenance ownership.
- Expected time saved vs regression risk.

## 22. Tăng chất lượng rule bằng negative/positive fixtures

### 22.1. Rule QA cũng cần test

Nếu AppSec tune rule để giảm FP, cần test **hai chiều**:
- Có giảm alerts sai trong safe examples?
- Có giữ detection ở unsafe examples?

Một test chỉ xác minh “safeJdbcWrapper không bị báo nữa” có thể đạt bằng cách **tắt toàn rule** – rõ ràng không đạt mục tiêu assurance.

### 22.2. Fixture test suite

| Fixture ID | Code/pattern | Expected |
|---|---|---|
| FP-FX-01 | JDBC PreparedStatement + bind values | Không báo SQLi với values |
| FP-FX-02 | Raw SQL concatenation từ request | Vẫn báo SQLi |
| FP-FX-03 | Bound WHERE + raw ORDER BY | Vẫn báo dynamic identifier injection |
| FP-FX-04 | Auto-escaped HTML text template | Không báo XSS ở context đã xác minh |
| FP-FX-05 | Raw HTML insertion | Vẫn báo XSS |
| FP-FX-06 | Trusted server-selected fixed partner endpoint | Không báo arbitrary destination SSRF nếu đã chứng minh |
| FP-FX-07 | User-controlled URL → unrestricted client | Vẫn báo SSRF |
| FP-FX-08 | Opaque file ID + authorized object mapping | Không báo raw path traversal nếu path không user-controlled |
| FP-FX-09 | Raw user filename → file open | Vẫn báo traversal |
| FP-FX-10 | Synthetic test-only secret clearly tagged | False-secret detection được xử lý đúng taxonomy |
| FP-FX-11 | Realistic secret leak fixture, không dùng key thật | Vẫn phát hiện suspicious credential |
| FP-FX-12 | Password hashed bằng dedicated KDF | Không báo raw hash password misuse |
| FP-FX-13 | Raw fast hash dùng lưu mật khẩu | Vẫn báo weakness |
| FP-FX-14 | Object-level authz được enforce trong service | Không báo thiếu policy chỉ do thiếu annotation |
| FP-FX-15 | Role-only access không check object | Phát hiện hoặc đưa vào test khác vì SAST có giới hạn |
| FP-FX-16 | Test-only code excluded đúng scope | Không ảnh hưởng production scan; vẫn đánh giá build pipeline riêng |

### 22.3. Tính đại diện của fixtures

Các fixtures nên gần thực tế:
- Java/Spring versions được hỗ trợ.
- Multiple modules/overloads/aliases.
- Known framework mechanisms.
- Dynamic configuration.
- Positive và negative code paths.
- Compiler/build options tương đương.
- Tool scan config và ruleset version.

Một fixture có thể xác minh rule behavior nhưng **không chứng minh scanner phát hiện mọi vulnerability** trên hàng triệu dòng code. Kết luận coverage phải có scope.

### 22.4. Independent spot-checks

Khi loại FP hàng loạt, lấy mẫu ngẫu nhiên và mẫu risk-based các records đã bị suppress để review độc lập. Không chọn chỉ những case dễ. Metrics nên ghi **population, sampling method, FP reversal rate và findings discovered**.

## 23. CI/CD: làm giảm noise mà vẫn bảo vệ release

### 23.1. Vì sao PR gate dễ bị lệch?

Một repository có backlog 500 findings. Nếu PR pipeline luôn fail, developer có thể:
- Tắt SAST.
- Dùng baseline không có kiểm soát.
- Suppress toàn project.
- Tự đổi severity để qua gate.
- Bỏ review security findings.
- Giấu scanner errors.

Một gate trưởng thành cần **phân biệt technical findings, approved FP và known backlog**, không biến vấn đề process thành mất visibility.

### 23.2. Gate model

~~~mermaid
flowchart TD
    P["Pull request / commit"] --> B["Build + source identity"]
    B --> S["SAST chạy đúng rule/config"]
    S --> H{"Scanner healthy + scope đầy đủ?"}
    H -->|"Không"| U["Tool error / coverage gap"]
    H -->|"Có"| N["Findings và fingerprints"]
    N --> T["Triage: TP / FP / unknown"]
    T --> G{"Security gate policy"}
    G -->|"Blocking TP / unknown risk"| F["Fix / review / exception"]
    G -->|"Approved FP, bounded scope"| A["Record disposition + regression"]
    G -->|"No blocking issue"| R["Release eligible"]
    A --> R
    F --> P
~~~

### 23.3. Những điều gate phải phân biệt

| Quan sát | Gate behavior |
|---|---|
| Critical TP trong code mới | Block hoặc approved emergency exception theo policy |
| FP đã được review, đúng fingerprint/scope | Có thể không block, giữ rationale/audit |
| Finding mới chưa triage và có potential high impact | Investigate/escalate; không auto-FP |
| Existing approved risk exception còn hiệu lực | Quản lý riêng, không gọi FP |
| Scanner tool timeout/partial upload | Fail/Unknown theo policy, không Pass |
| Rule/plugin bị tắt không phê duyệt | Configuration deviation |
| Finding ID thay đổi do upgrade | Fingerprint migration/re-review |
| Suppression không có owner/justification/expiry | Governance failure |
| Library/framework nâng version khiến rationale cũ lỗi thời | Reassess FP decision |
| Scan no findings nhưng source/crawl coverage thiếu | Unverified, không tự kết luận secure |

### 23.4. Baseline and new-code policy

Có thể áp chính sách **new issues must be triaged** trong khi technical debt được quản lý bằng backlog riêng. Nhưng:
- New code không được khiến existing vulnerability reachable hơn.
- Baseline phải có owner, reason và plan.
- Suppression expiry/triggers cần hoạt động.
- Không tự gộp tất cả old findings thành FP.
- Risk assessment có thể yêu cầu xử lý backlog high risk trước release.

### 23.5. Gate YAML minh họa

~~~yaml
static_analysis_triage_gate:
  policy_version: "sast-fp-example-2026"
  scope:
    repositories: ["learning-api", "report-worker"]
    branches: ["main", "release/*"]
  scan_health:
    required: true
    fail_on:
      - "analyzer_failure"
      - "rulepack_not_loaded"
      - "missing_source_scope"
      - "artifact_revision_mismatch"
  triage:
    allowed_dispositions:
      - "TRUE_POSITIVE"
      - "FALSE_POSITIVE"
      - "NOT_APPLICABLE"
      - "DUPLICATE"
      - "NEEDS_INVESTIGATION"
    false_positive_requires:
      - "rule_id_and_fingerprint"
      - "technical_rationale"
      - "evidence_reference"
      - "reviewer"
      - "scope"
      - "reassessment_trigger"
    mitigation_or_acceptance:
      separate_from_false_positive: true
  suppressions:
    allow_inline: "only-with-approved-rationale"
    broad_rule_disable: "requires-security-owner-review"
    unknown_or_expired: "block-or-review"
  quality:
    run_seeded_safe_and_unsafe_fixtures_on_rule_changes: true
    compare_rule_coverage_on_upgrades: true
  evidence:
    link_to_commit_and_scan_run: true
    record_tool_and_ruleset_version: true
~~~

Đây là **cấu hình minh họa**, không phải cú pháp có thể nạp trực tiếp vào một CI platform. Cần thiết kế implementation, access/approval và kiểm thử trên tool thực tế.

### 23.6. Một thành công dễ bị hiểu sai

Nếu SAST scan report giảm từ 1.000 findings xuống 5 sau khi áp dụng một exclusion rộng, đó không phải bằng chứng chất lượng code tăng. Cần kiểm tra **covered lines, modules, active rules, true-positive sentinel fixtures và delta của suppressions**.

## 24. Metrics: đo FP một cách trung thực

### 24.1. Các số đo hữu ích

| Metric | Định nghĩa thực hành | Lưu ý |
|---|---|---|
| **Reviewed FP proportion** | FP / (FP + TP) trong findings đã phân loại rõ | Không bằng FPR trên toàn codebase |
| **Triage precision** | TP / (TP + FP) trong labeled alerts | Không ước được recall nếu không có FN data |
| **Untriaged backlog** | Số alerts chưa có verdict | Không coi như FP |
| **Median/P95 triage time** | Thời gian từ finding đến quyết định có evidence | Cần phân loại theo rule/severity |
| **FP recurrence rate** | FP cùng root cause tái xuất sau tool/code changes | Fingerprints có thể đổi |
| **Suppression coverage** | % rules/files/code scope bị loại khỏi scan | Nên đo cả nguy cơ blind spots |
| **Expired/unreviewed suppressions** | Items quá hạn hoặc thiếu reviewer | Không gộp với closed legitimate |
| **FP reversal rate** | Các quyết định FP sau đó bị lật thành TP | Cần independent QA và cause |
| **Missed TP in seeded fixtures** | Lỗi đúng mà scanner không còn phát hiện | Chỉ phản ánh fixture coverage |
| **Rule precision by category** | TP/(TP+FP) cho rule đã review | Cần số mẫu và confidence |
| **New TP vs new FP** | Phân loại findings trên changed code | Tool upgrades có thể thay population |
| **Scan completeness** | Target modules/rules/lang covered | “No findings” khi tool fail là vô nghĩa |
| **Risk of open TP** | Số TP chưa xử lý theo asset impact | Số lượng không đủ đo risk |
| **False-negative discovery** | Vulnerabilities được test/incident thấy mà SAST bỏ | Thường không có mẫu số hoàn chỉnh |
| **Suppression review coverage** | Số case review/total case theo kỳ | Review chất lượng khác tick approve |
| **Rule/model regression failures** | Fixtures bị sai sau tuning/upgrade | Cần giữ tests của detector |

### 24.2. Công thức không được nhầm

Giả sử đã triage **100 scanner alerts**: 40 TP, 60 FP. Có thể nói:
- **Observed precision trên 100 alerts đã triage** = 40%.
- **Observed FP share trên 100 alerts đã triage** = 60%.

Không thể nói:
- **Scanner false positive rate = 60%** theo định nghĩa FPR, vì chưa biết TN.
- **Recall của scanner = 100%**, vì chưa biết FN.
- **60% code là false positive**, vì mẫu số là alerts, không phải code locations.

Nếu chỉ triage top severity alerts, observed precision **không đại diện** cho mọi findings. Nêu sampling và selection bias.

### 24.3. Rule-level metrics

Một rule có 300 alerts, trong đó 280 được review là FP, có thể cần tune model. Nhưng cũng cần kiểm tra **20 TP còn lại có high-risk không**. Tắt rule toàn cục để giảm 280 FP có thể đánh đổi 20 vulnerabilities thật và nhiều bugs chưa phát hiện trong tương lai.

### 24.4. Chỉ số gây hành vi sai

Một KPI “giảm tổng findings 90%” có thể thúc đẩy suppressions. Thay bằng tổ hợp:
- % critical TP được xử lý và verified.
- Precision trên labeled alerts với confidence/sampling.
- Ratio of suppressions có owner/evidence.
- Fixture recall/coverage trên rule sets quan trọng.
- Time to triage high-risk new findings.
- Scan health/rule coverage.
- FP reversals và reopened findings.

## 25. Governance: ai được gọi một finding là FP?

### 25.1. Tách technical review và risk decision

Trong quy trình tốt:
- Developer cung cấp code/context và đề xuất verdict.
- AppSec/qualified reviewer đánh giá semantics và evidence, đặc biệt với high risk.
- Rule/tool owner quản lý custom models, false-positive tuning và scan QA.
- Product/asset owner cung cấp business context.
- Platform owner xác minh runtime/build/deployment khi cần.
- Risk owner quyết định **accepted residual risk**, không đổi TP thành FP.
- Auditor/assurance reviewer kiểm tra traceability và review independence theo policy.

### 25.2. RACI tham khảo

R = Responsible; A = Accountable; C = Consulted; I = Informed.

| Hoạt động | Developer/Tech Lead | AppSec/Assurance | Platform/CI | Product/Data Owner | Risk Owner |
|---|---|---|---|---|---|
| Cung cấp code/data-flow evidence | A/R | C | I | C | I |
| Định nghĩa triage policy/criteria | C | A/R | C | C | C |
| Review FP với high-risk rule | R | A/R | C | C | I |
| Tạo custom sanitizer/source/sink model | R | A/R | R hỗ trợ | I | I |
| SAST gate health, rule coverage | C | A policy | R vận hành | I | I |
| Suppression approval/expiry | R | A/R | C | I | I |
| Finding remediation và regression test | A/R | C/R verify | C | C | I |
| Business impact/risk triage | C | R | C | A/R context | C |
| Accepted risk decision | C | C | C | C | A/R |
| Evidence and assurance reporting | R cung cấp | A/R | R cung cấp | C | I |
| Reopen sau code/tool/config change | R | A/R | R | C | I |

Bảng là **minh họa**. Khi nhóm nhỏ, người có thể kiêm vai trò nhưng cần biện pháp bù trừ/peer review cho conflict of interest theo risk.

### 25.3. Tách self-attestation khỏi independent assessment

Tác giả PR không nên tự đánh FP rồi tự phê duyệt suppression rộng ở một critical authz boundary nếu policy yêu cầu review độc lập. Một reviewer có chuyên môn cần xem:
- Rule logic/data flow.
- Code và build config đúng.
- Tests và fixture quality.
- Rationale, scope và impacts.
- Suppression changes và risk of FN.
- Reassessment trigger.

### 25.4. Developer experience không đối lập bảo mật

Một chương trình FP triage tốt giảm thời gian vô ích bằng cách:
- Tạo templates concise.
- Cung cấp guidance theo rule.
- Tự động gom duplicates chính xác.
- Chạy analyzer incrementally cho code mới.
- Training về taint flows/secure APIs.
- Duy trì model library cho Spring/JDBC/template engine.
- Feedback loop từ developers tới rule owners.
- Không ép developer điền 30 field cho một low-risk heuristic mà vẫn giữ evidence cần thiết.

## 26. Bảo vệ bằng chứng triage và quyền riêng tư

### 26.1. SAST report có thể chứa thông tin nhạy cảm

Một report có thể hiển thị:
- Internal paths/project structure.
- Source snippets proprietary.
- Vulnerable code locations.
- Hardcoded secret strings.
- Private registry URLs.
- Cloud account/resource IDs.
- Personal data trong test fixtures.
- Internal architecture/trust boundaries.

Không post full unredacted SAST report vào issue tracker công khai hoặc gửi cho vendor khi chưa có approval.

### 26.2. Phân loại evidence và kiểm soát truy cập

- Role-based access theo project/risk.
- Secret redaction/token masking **trước** khi share.
- Controlled exports/links với expiration khi phù hợp.
- Audit of triage/suppression modifications.
- Retention theo audit/vulnerability response requirements.
- Legal/privacy review nếu chứa PII.
- Immutable/controlled original evidence khi cần chain of custody.
- Tách internal technical evidence với customer summary.

### 26.3. Dữ liệu phân tích không phải mọi lúc đúng

Một snapshot code có thể stale. Reviewer cần source revision, scan time và build context; nếu project thay đổi, FP rationale có thể không còn đúng. **Evidence freshness** là một phần của assurance.

## 27. Claim–Argument–Evidence cho false positive

### 27.1. Claim đúng phạm vi

> Đối với SAST finding F (rule R) trong phương thức M của Learning API tại commit C, cảnh báo SQL injection do analyzer coi bind parameter là SQL text không đại diện cho một data-flow weakness thực tế ở call site được kiểm tra. SQL query text được xác định tĩnh, các input values đi qua binding API đúng overload/version, và code/integration review xác nhận không có raw SQL syntax construction trong path này.

Claim chỉ về **rule/path/build**, không nói "không có SQL injection ở toàn platform".

### 27.2. Argument

1. Có rule semantics, source/sink trace và original finding.
2. Đã xác minh code revision và module đang được review.
3. Có analysis source provenance và propagation.
4. Query syntax không thay theo untrusted input.
5. JDBC API/overload/version bind values đúng.
6. Các paths/overloads khác không được tự gộp.
7. Test synthetic input và static review hỗ trợ semantics.
8. Suppression (nếu có) giới hạn đúng finding và có owner.
9. Scanner tuning còn phát hiện seeded TP.
10. Changes to code/API/tool sẽ trigger review lại.

### 27.3. Evidence chain

~~~mermaid
flowchart LR
    F["SAST finding + rule"] --> S["Source/sink and data-flow review"]
    S --> C["Code/config/API contract"]
    C --> T["Safe and unsafe test fixtures"]
    T --> D["Verdict FP/TP/Unknown + scope"]
    D --> R["Reviewer approval + rationale"]
    R --> U["Bounded suppression / rule tuning"]
    U --> M["Regression tests + monitor"]
    M --> E["Assurance report + reopen triggers"]
~~~

### 27.4. Design, implementation và operating effectiveness

| Lớp | Câu hỏi | Evidence |
|---|---|---|
| **Design** | Triage policy có định nghĩa TP/FP, scope, confidence, reviewer và safeguards? | Procedure, classification taxonomy, rule/model design |
| **Implementation** | Finding được triage đúng và suppression không bỏ TP? | Code/data-flow review, fixture tests, approval, CI config |
| **Operating** | Quy trình tiếp tục đúng qua releases/tool upgrades? | Audit of overrides, FP reversals, scan health trends, reassessment records |

Một FP conclusion hợp lệ cho một release chưa chứng minh suppression **vẫn đúng** khi helper, framework hoặc rule thay đổi.

### 27.5. Evidence gaps

Nếu scanner chỉ đưa một warning text, không có code flow hoặc source revision rõ, có thể cần đọc source/binary/config và thử model. Trong lúc đó kết luận hợp lý là **Needs Investigation / Insufficient Evidence**, không ép reviewer chọn FP/TP tùy tiện.

## 28. Catalog yêu cầu kiểm soát false positive

Các mã **FP-REQ-001…FP-REQ-030** dưới đây là **quy ước minh họa nội bộ của bài học**, không phải mã chuẩn của OWASP, NIST hay một công cụ SAST. Mỗi yêu cầu cần scope/owner/acceptance criteria/evidence phù hợp với chính sách thực tế.

| ID | Yêu cầu có thể kiểm chứng | Acceptance criteria |
|---|---|---|
| **FP-REQ-001** | Mọi SAST finding có rule và target identity | Rule ID/version, commit/module, file/sink và scan run |
| **FP-REQ-002** | Scan health được kiểm tra trước triage | Tool errors/partial runs không tạo verdict giả |
| **FP-REQ-003** | Phân loại TP/FP/Unknown có semantics chuẩn | Taxonomy được tài liệu hóa, không lẫn risk accepted |
| **FP-REQ-004** | FP quyết định dựa trên technical rationale | Source–sink/guard/API semantics có evidence |
| **FP-REQ-005** | Một quyết định FP có scope cụ thể | Call site, rule, version, configuration và exclusions |
| **FP-REQ-006** | High-impact FP có reviewer phù hợp | Review record/approval và người chịu trách nhiệm |
| **FP-REQ-007** | FP không tự áp dụng cho sibling paths | Scope/reuse chỉ khi có evidence tương đương |
| **FP-REQ-008** | Weakness đúng nhưng mitigated không được đổi FP | Test taxonomy và sample triage audit |
| **FP-REQ-009** | Finding chưa rõ không bị auto-discard | Needs investigation/owner/due date |
| **FP-REQ-010** | False-positive labels có audit history | Who/when/rationale/old-new status và review |
| **FP-REQ-011** | Stable fingerprint hoặc migration strategy | Line moves/rule upgrade không mất triage |
| **FP-REQ-012** | Suppression có scope hẹp và lý do | Rule/call site/fingerprint/owner/evidence |
| **FP-REQ-013** | Suppression có expiry hoặc reassess trigger | Code/tool/framework/config changes được theo dõi |
| **FP-REQ-014** | Rule-disable rộng phải có thẩm quyền | Coverage delta, approval và rollback plan |
| **FP-REQ-015** | Custom sanitizer/source/sink model có test | Safe fixture pass, unsafe fixture vẫn báo |
| **FP-REQ-016** | Scanner ruleset upgrades được kiểm tra | Before/after detection/coverage và suppression review |
| **FP-REQ-017** | Java/Spring frameworks có model đúng scope | JDBC, templates, DI, security filters sample checks |
| **FP-REQ-018** | Secret FP không che credential thật | Synthetic fixtures, credential review và secret policy |
| **FP-REQ-019** | Business authorization không bị bác bỏ bằng heuristic | Role/tenant/object relation tests theo requirement |
| **FP-REQ-020** | FP triage không thay privacy/access controls | Reports/redaction/permissions và safe evidence |
| **FP-REQ-021** | CI gate không coi scanner failed là zero finding | Forced tool error → Unknown/Fail theo policy |
| **FP-REQ-022** | Baseline không nuốt new TP | Changed-code detector/sentinel test và fingerprint |
| **FP-REQ-023** | FP metrics có đúng numerator/denominator | FP share khác FPR; sampling/limitations rõ |
| **FP-REQ-024** | Tỷ lệ FP reversal được theo dõi | FP bị lật sang TP có root-cause analysis |
| **FP-REQ-025** | Findings trùng được gộp có căn cứ | Không gộp khác sink/weakness/owner |
| **FP-REQ-026** | Findings high risk không bị bypass âm thầm | Reviewer/gate overrides có audit/approval |
| **FP-REQ-027** | FP decisions có thể bị re-open | Tool/code/API/attack exposure change triggers |
| **FP-REQ-028** | Evidence phục vụ repeatable assessment | Reproduction, config, source revision, reviewer |
| **FP-REQ-029** | Scan rule coverage được monitor | Disabled rules/exclusions/modules được phát hiện |
| **FP-REQ-030** | Assurance report nêu giới hạn kết luận | Claim–Argument–Evidence, uncertainties, residual gaps |

### 28.1. Một requirement chi tiết: FP-REQ-004

**Risk:** SAST finding bị loại sai làm vulnerability thật không được xử lý.

**Statement:** Mọi finding được phân loại FALSE_POSITIVE trong scope high-impact SAST rules phải có technical explanation trực tiếp bác bỏ chính weakness được rule mô tả, gắn với source revision, rule ID, call site, data-flow/sink conditions và code/API behavior. Reviewer có thẩm quyền phải phê duyệt; kết luận phải ghi assumptions và reassessment triggers.

**Expected tests:**
1. Một case JDBC binding an toàn được chấp nhận FP với evidence.
2. Một case raw SQL concatenation không thể nhận verdict FP chỉ vì một test không tái hiện.
3. Một case WAF mitigation vẫn được phân loại TP/Mitigated nếu weakness còn.
4. Một case tool timeout không được phân loại FP.
5. Khi code chuyển sang raw SQL, review cũ bị vô hiệu và finding được re-open.

**Evidence:** triage record, code/trace, tests, reviewer identity, suppression diff và regression run.

### 28.2. Một requirement chi tiết: FP-REQ-015

**Risk:** custom rule tuning giảm FP nhưng vô tình bỏ TP.

**Statement:** Trước khi phát hành model/rule change áp dụng nhiều repositories, pipeline phải chạy fixture suite có safe và unsafe examples liên quan; không được chấp nhận thay đổi nếu làm mất detection của bất kỳ high-impact reference unsafe fixture nào mà không qua risk/policy review.

**Acceptance tests:** seeded cases SQL safe/unsafe/mixed; context HTML; path traversal; secret detection; framework overload; analyzer failures được báo riêng. **Không dùng chỉ số “ít findings hơn” làm test oracle**.

### 28.3. Một requirement chi tiết: FP-REQ-023

**Risk:** dashboard báo false-positive rate bằng FP/alerts và đánh lừa lãnh đạo về chất lượng scanner.

**Statement:** Mọi metric FP cần nêu định nghĩa, numerator, denominator, period, rule set, sample selection, số cases chưa triage và confidence/limits. Không hiển thị FPR hoặc recall toàn hệ thống nếu chưa có labeled population với TN/FN tương ứng.

**Acceptance:** lấy dataset giả định có TP/FP/TN/FN đã biết và test công thức; lấy operational labeled alerts thiếu TN/FN và xác minh hệ thống báo precision/FP share, không bịa FPR.

## 29. Test matrix: kiểm chứng quy trình xử lý FP

Các mã **FP-T01…FP-T40** là test cases minh họa cần chọn theo risk, tool và policy. Một test “FP đúng” phải xác định **ground truth trong fixture** chứ không dựa vào verdict của chính scanner.

| Test ID | Kịch bản | Expected |
|---|---|---|
| **FP-T01** | JDBC bind values bị tool báo SQLi | FP có rationale, call site scope |
| **FP-T02** | Raw SQL request concatenation | TP, không suppress |
| **FP-T03** | Bound WHERE + raw ORDER BY | TP cho dynamic syntax path |
| **FP-T04** | Spring auto-escaped HTML text | FP nếu context/config đã xác minh |
| **FP-T05** | Raw template HTML/innerHTML | TP không bị model tuning che |
| **FP-T06** | Safe partner ID mapping | FP nếu URLs/redirect/egress được xác minh |
| **FP-T07** | User-supplied URL bất kỳ | SSRF concern không auto-FP |
| **FP-T08** | Opaque file ID với authorized mapping | Không tự cảnh báo traversal sai scope |
| **FP-T09** | Raw path có symlink/race case | Không bác bỏ chỉ nhờ normalize() |
| **FP-T10** | Synthetic test secret có documented no authority | FP/not applicable đúng semantics |
| **FP-T11** | Actual credential fixture có authority giả định | TP, không suppress |
| **FP-T12** | Password lưu bằng raw fast hash | TP password storage weakness |
| **FP-T13** | SHA-256 digest cho artifact integrity | Không báo weak password hashing sai context |
| **FP-T14** | Role-only check và cross-tenant data | Không được FP vì role đã authenticated |
| **FP-T15** | Service-level object authorization đúng | Rule annotation heuristic phải review evidence |
| **FP-T16** | WAF bảo vệ vulnerable backend | TP/Mitigated, không FP |
| **FP-T17** | Code chỉ thuộc test harness không deploy | Not applicable theo production scope có proof |
| **FP-T18** | Project tool scan thiếu module | Coverage gap/Unknown |
| **FP-T19** | Tool timeout, report 0 alerts | Scanner error, không Pass |
| **FP-T20** | Security rule bị disable trái approval | Gate/monitor flag deviation |
| **FP-T21** | Finding line move nhưng semantics giữ | Fingerprint giữ/merge triage đúng |
| **FP-T22** | Tool đổi ruleId | Migration/review, không auto-close |
| **FP-T23** | Hai sink khác nhau cùng dòng | Không gộp thành một FP sai |
| **FP-T24** | Broad suppression src/main/java | Từ chối/cần reviewer & coverage delta |
| **FP-T25** | Inline suppression thiếu rationale | Policy gate fail hoặc review |
| **FP-T26** | Suppression hết hạn | Reassess/alert |
| **FP-T27** | JDBC wrapper implementation đổi | FP decision bị re-review |
| **FP-T28** | Spring framework upgrade | Re-run safe/unsafe fixtures và models |
| **FP-T29** | Custom sanitizer model che unsafe overload | Fixture TP mất → model change reject |
| **FP-T30** | False-positive status bị sửa không có approval | Audit/governance failure |
| **FP-T31** | Developer dùng "no exploit reproduced" làm rationale duy nhất | Needs investigation, không auto-FP |
| **FP-T32** | SCA fork/backport ambiguity | Matching/rationale/review, không silent FP |
| **FP-T33** | IaC rule policy explicit, cloud effective exposure blocked | Phân biệt policy TP và exposure mitigation |
| **FP-T34** | SAST report chứa synthetic secret canary | Redact/report access theo policy |
| **FP-T35** | Scanner fix giảm alerts 90% nhưng rule coverage giảm | Gate detect regression |
| **FP-T36** | High-impact FP được actor thiếu thẩm quyền duyệt | Approval invalid, escalate |
| **FP-T37** | FP reclassified to TP sau incident | Reopen, root cause, impact review |
| **FP-T38** | Operational labeled alerts không có TN/FN | Không tính FPR/recall giả |
| **FP-T39** | Labeled benchmark 70TP/20FP/10FN/100TN | Precision/recall/FPR đúng công thức |
| **FP-T40** | Runtime code path mới dùng formerly safe wrapper sai | Change trigger/retest và new finding |

### 29.1. Bài test của detector khác bài test bảo mật ứng dụng

Nếu công cụ không báo FP ở prepared query, đó là **detector quality improvement**. Nó không chứng minh ứng dụng không có SQL injection ở chỗ khác. Nếu một test cross-tenant deny đạt, đó là **authorization behavior evidence** chứ không tự nói rule SAST đã phát hiện mọi BOLA.

Nên tách:
- Rule/model QA.
- Code security verification.
- CI pipeline/scan health.
- Triage governance.
- Assurance evidence review.

### 29.2. Regression matrix qua tool upgrades

| Tình huống | Cần xem trước/sau |
|---|---|
| Nâng analyzer | FP patterns, TP fixtures, rule coverage, runtime |
| Nâng Spring/JDBC | Wrapper APIs, security filters, template encoding |
| Thay custom model | Safe/unsafe overload tests |
| Refactor code | Fingerprint/taint flow/rationale validity |
| Thay scanner config | Rules excluded, files/modules scanned |
| Update vulnerability mapping | Advisory identity và FP/TP re-review |
| Thêm endpoint mới | New source–sink paths, authz contexts |

## 30. Case study xuyên suốt: Java Learning Platform có hàng loạt FP

### 30.1. Bối cảnh

Một nền tảng học trực tuyến dùng:
- Java/Spring API xử lý học viên, lớp, bài nộp và điểm.
- Report worker xuất bảng điểm.
- PostgreSQL qua JDBC/JPA.
- Template engine cho trang web và email.
- S3-compatible object storage với private objects.
- Service dùng HTTP client để import tài liệu đối tác.
- Maven/Gradle builds, CI pipeline có SAST/SCA.
- Multi-tenant security model.
- Logging/monitoring và security assurance program.

SAST release scan báo:
- 120 SQLi alerts trên custom query wrapper.
- 45 XSS alerts tại template views.
- 20 SSRF alerts tại partner URL fetch.
- 15 secrets alerts trong test fixtures.
- 10 authorization warnings trên controllers thiếu annotation.
- 5 high-confidence SQLi ở dynamic sort/filter endpoints.

Tổng **215 alerts** theo ví dụ, chưa phải 215 vulnerabilities.

### 30.2. Rủi ro nếu chỉ nhắm “zero findings”

Team có thể:
1. Tắt rule SQL injection toàn repo để giảm 125 alerts.
2. Exclude thư mục templates.
3. Tự mark tất cả URL fetch là safe do “đối tác đáng tin”.
4. Ignore test files mà không xem secrets có thật.
5. Coi thiếu annotation là false positive chỉ vì framework auto-secures.
6. Chấp nhận dashboard xanh sau scan mà không test.

Hệ quả: năm SQLi dynamic sort có thể bị che, và những path XSS/SSRF chưa review vẫn còn.

### 30.3. Kế hoạch triage theo nhóm

| Nhóm | Evidence cần | Hành động dự kiến |
|---|---|---|
| 120 JDBC wrapper alerts | Signature, overload, constant SQL, bound values, safe/unsafe fixture tests | Custom model cho safe overload; giữ detection cho raw syntax |
| 45 template alerts | Template expression, escaping context, stored views, frontend sinks | Mark FP từng context được chứng minh; fix raw HTML |
| 20 partner URL alerts | Source, partner config trust, redirects, DNS/IP/egress policy | FP/not applicable chỉ đúng scope; fix unrestricted fetch paths |
| 15 secret alerts | Test-only vs real, authority/rotation/history, packaging | Bác bỏ fixture giả có proof; xử lý real secrets |
| 10 authz warnings | Effective Spring filters, service policy, relationship tests | FP nếu business authz có thật; otherwise TP |
| 5 dynamic SQL alerts | Query syntax, raw sort, DB permissions, integration tests | TP và remediation |

### 30.4. Phân tích nhóm JDBC wrapper

SAST engine đánh mọi call của safe query wrapper là SQL injection vì không hiểu method overload. Triage mẫu:
- Chọn nhiều code paths representative.
- Chứng minh input không vào SQL string ở overload A.
- Chứng minh overload B có raw SQL fragment vẫn cảnh báo.
- Viết custom model hạn chế theo method signature.
- Chạy seeded TP/FP fixtures.
- Review diff model với AppSec.
- Áp dụng rule model rộng sau khi tests đạt.
- Theo dõi FP reversals và mất detection trên PR mới.

**Không được gọi toàn bộ 120 alerts FP chỉ dựa trên một call site**. Cần nhóm theo actual signatures và data flows; alerts khác biệt phải được xem riêng.

### 30.5. Phân tích năm dynamic sort endpoints

Ví dụ:
- Class search endpoint bind keyword nhưng nối sortBy.
- Report worker nối order clause.
- Admin dashboard nhận filter name và chuyển trực tiếp thành SQL fragment.

Các findings này **true positive** nếu input attacker-controlled ảnh hưởng SQL syntax. Cần explicit mapping/allowlist, parameterized values và tests, không tắt rule vì phần lớn alerts trước đó sai.

### 30.6. Kiểm tra XSS ở nhiều context

Một template view dùng escaped text có thể FP, nhưng view quản trị tạo HTML attribute từ cùng displayName với raw interpolation. Reviewer phải chia:
- HTML text safe, evidence → FP.
- Dangerous attribute/raw HTML → TP.
- HTML email template có renderer khác → unassessed cho tới khi review.

### 30.7. Kiểm tra SSRF theo trust boundary

Partner import có endpoint định sẵn. Nếu user chỉ chọn partner ID và HTTP client không thể ra ngoài approved egress, một số rule alerts có thể FP cho arbitrary URL control. Nhưng nếu admin được thêm URL mới hoặc client theo redirect không revalidate, vấn đề vẫn có thể tồn tại. **Config trust và runtime controls phải được kiểm chứng**, không chỉ đọc source.

### 30.8. Kiểm tra authorization warnings

Spring controller không có method annotation, nhưng service có chính sách class relationship. Để xác định FP, test:
- Teacher A chỉ đọc class thuộc quyền.
- Teacher B ngoài scope bị từ chối.
- Learner không nâng quyền bằng request.
- Direct API, GraphQL, worker/export không bypass.
- Cache/DB/storage không rò dữ liệu.
- Positive tests cho legitimate access.
- Relevant security filters/profile deployed.

Nếu tests không có tenant/resource relationships, kết luận tạm là Needs Investigation.

### 30.9. Rủi ro quản trị và kết luận

Sau triage giả định:
- 150 alerts được chứng minh FP với evidence.
- 20 TP đã sửa và verified trên affected paths.
- 10 TP còn open với owner.
- 25 alerts cần điều tra thêm.
- 10 duplicates đã liên kết với findings gốc.

Những con số ví dụ cộng lại **215**, nhưng **không phải** kết quả kiểm tra một hệ thống thật. Không dùng 150 FP để khẳng định 150 code paths an toàn ở mọi threat. Và trong một báo cáo thực, **duplicate** cần được xử lý như một trạng thái records riêng, tránh trộn với vulnerability population và đếm trùng risk.

### 30.10. Kết luận assurance cho case study

> Trong các SAST findings của release R được review theo rule set S, những cảnh báo đánh FP có rationale gắn call site, framework/API semantics và test evidence. Custom rule model đã được test với safe và unsafe fixtures để hạn chế false negatives. Các true positives còn lại được theo dõi riêng với owners, fix/retest và residual risk decisions. Các findings chưa đủ chứng cứ không được tính Fixed/False Positive, và không có tuyên bố bao phủ những modules, tool paths hoặc runtime configurations ngoài phạm vi.

**Đây là mẫu kết luận**, không phải chứng nhận nền tảng thật đã đạt.

## 31. Khi quyết định FP bị đảo ngược

### 31.1. FP reversal là tín hiệu cần điều tra

Một số FP được ghi nhận ở tháng trước có thể thành TP khi:
- Wrapper được refactor và bắt đầu nối SQL raw.
- Framework đổi default escaping.
- Route internal được public qua gateway mới.
- Feature flag mở path trước đây không reachable.
- Code từ test fixture bị copy vào production.
- Dynamic plugin tải version khác.
- Tool bổ sung call graph và phát hiện path bị bỏ sót.
- Incident/test độc lập chứng minh weakness thật.
- Reviewer ban đầu hiểu sai API overload.

### 31.2. Quy trình xử lý

1. Re-open finding hoặc tạo linked risk finding theo tracker semantics.
2. Đánh giá **thời điểm assumption không còn đúng**.
3. Xác định code/build/deployments affected.
4. Ngưng hoặc thu hẹp suppression sai.
5. Test true-positive detection và root cause.
6. Contain/mitigate nếu risk nghiêm trọng.
7. Remediate, verify và xem sibling paths.
8. Review các FP quyết định bằng rationale tương tự.
9. Cập nhật rule/model/triage policy.
10. Báo FP reversal rate cùng limitations, không che bản ghi lịch sử.

### 31.3. Đừng phạt việc phát hiện lại

Một chương trình trưởng thành khuyến khích **sửa sai phân loại**. Nếu KPI/phê bình khiến người review sợ đảo FP thành TP, hệ thống sẽ giữ risk bị che. Đánh giá chất lượng qua evidence, tốc độ khắc phục và bài học, không chỉ tỷ lệ "quyết định FP không bao giờ thay đổi".

## 32. Continuous false-positive assurance

### 32.1. Những trigger cần reassess

- Java/Spring/JDBC/template/security library update.
- Wrapper/sanitizer/validator được sửa.
- Security annotations, filters, route configs đổi.
- Thêm API, GraphQL resolver, queue consumer, admin path.
- Chuyển data từ trusted sang untrusted source.
- Input field được dùng trong sink mới.
- Thay tenant/role/resource policies.
- Custom rule/SAST analyzer/ruleset upgrades.
- Changes to baseline/suppression files.
- Build profile/target/packaging đổi.
- Deployment exposure/network/VEX context đổi.
- SCA/advisory mapping updates.
- Security finding, incident hoặc independent test chứng minh bug.
- CI scan failure/coverage reduction.

### 32.2. Tích hợp vào vòng đời

| Giai đoạn | Hoạt động | Evidence |
|---|---|---|
| Discovery | Identify codebases, trust boundaries, SAST tool assumptions | Inventory, policy |
| Architecture | Design data-flow/security patterns và threat model | Decisions, secure requirements |
| Implementation | Use safe APIs, tests và code review | Source, unit/integration |
| PR | SAST + triage new findings | Scan run, verdict, rationale |
| Model change | Run safe/unsafe reference fixtures | Rule QA report |
| Release | Verify scan coverage và suppression policy | CI gate evidence |
| Operations | Monitor FP reversals, missed TP, scanner health | Metrics, incidents |
| Incident | Revisit affected FP/suppressions | Impact/review records |
| Periodic assessment | Sample triage, review expiry/coverage | Assurance report |
| Retirement | Archive evidence and remove stale scan targets | Lifecycle record |

### 32.3. Continuous assurance không phải mỗi ngày mark FP lại

Một quyết định FP có evidence tốt có thể được tái sử dụng trong phạm vi đúng; nhưng **thay đổi code/model/config** phải trigger review. Tránh lặp thủ công vô ích bằng fingerprint, ownership và automation; đồng thời tránh “approve forever”.

## 33. Những sai lầm thường gặp

**“Scanner báo thì chắc chắn có vulnerability.”** SAST có heuristic/model limitations; cần xác minh.

**“Developer nói không exploit được nên là FP.”** Chưa tái hiện không chứng minh false positive; xem source–sink và preconditions.

**“Risk thấp đồng nghĩa FP.”** Risk priority khác technical validity.

**“WAF chặn request nghĩa code không có lỗi.”** Weakness có thể còn, chỉ được mitigated.

**“Internal endpoint không có lỗ hổng.”** Network boundary có thể thay đổi, insider/service compromise vẫn đáng xét.

**“Mọi framework annotation đều đảm bảo authorization.”** Business-level object/tenant policy vẫn cần kiểm chứng.

**“Controller không có annotation nghĩa thiếu authorization.”** Enforcement có thể nằm ở service/filter; cần xem actual path.

**“Có PreparedStatement là mọi SQLi đều FP.”** Dynamic identifiers, raw fragments và other call sites có thể còn TP.

**“Đặt tên safeSanitize() là đủ.”** Phải xác minh sanitizer đúng context và implementation.

**“HTML escape bảo vệ mọi output contexts.”** HTML text, attributes, JS, CSS, URL cần xử lý riêng.

**“Path.normalize() đã chặn symlinks và TOCTOU.”** Không mặc nhiên; cần safe open/permissions và tests.

**“Mọi test fixture secret đều giả.”** Test files có thể chứa credential thật; phải xem authority và history.

**“SHA-256 lúc nào cũng yếu.”** Digest artifact integrity khác password storage.

**“CPE match luôn chính xác.”** Package forks/backports/platforms làm mapping mơ hồ.

**“Nhiều FP nghĩa tắt rule.”** Có thể che TP; nên tune specific model và test unsafe fixtures.

**“Annotation suppression nghĩa finding được đánh giá.”** Suppression có thể không có owner/rationale, phải audit.

**“FP triage xong không bao giờ cần xem lại.”** Framework/code/tool/risk changes có thể làm verdict stale.

**“SARIF result ID là định danh bất biến qua refactor.”** Cần stable fingerprints, migration và review.

**“Line đổi nghĩa issue đã fixed.”** Rule/line movement không đại diện security state.

**“False-positive rate = FP / tất cả alerts.”** Đây thường là FP share/FDR; FPR cần TN.

**“Không có scanner findings nghĩa recall 100%.”** Không có FN ground truth; có thể scan incomplete.

**“Precision cao nghĩa không bỏ sót lỗi.”** Precision và recall đo khía cạnh khác.

**“Tất cả findings được review là assurance đủ.”** Còn tool coverage, false negatives, runtime, control effectiveness.

**“0 findings sau khi exclusion toàn source là thành công.”** Coverage giảm có thể phá security gate.

**“Scan timeout vẫn coi là Pass.”** Tool error = Insufficient Evidence.

**“High severity scanner luôn đúng.”** Severity không là bằng chứng technical truth.

**“Suppression FP có thể thay technical remediation.”** Với TP, cần fix/mitigate/risk decision; không dùng FP.

**“Tool có custom model thì không cần test model.”** Sai model có thể làm mất TP.

**“Bản report đã ký nghĩa phân loại FP đúng.”** Integrity của report không xác nhận rationale.

**“Một FP ở SQLi chứng minh endpoint hoàn toàn an toàn.”** Có thể còn BOLA, XSS, privacy và availability risks.

## 34. Bài tập thực hành

### Bài tập A — Phân biệt TP/FP/FN/TN

Cho 200 fixture cases có ground truth: TP=70, FP=20, FN=10, TN=100. Tính precision, recall, specificity, FPR, FDR và F1; giải thích ý nghĩa mẫu số. Sau đó giải thích vì sao không thể suy các metric ấy từ danh sách alerts của một scan production chưa có ground truth.

### Bài tập B — PreparedStatement nhưng còn ORDER BY

Java endpoint bind classId nhưng nối sortBy từ request vào SQL text. Hãy xác định từng data flow, vị trí sink, TP/FP theo rule, remediation và regression tests. Viết rationale tại sao không suppress toàn method.

### Bài tập C — Custom wrapper bị tool hiểu sai

Một wrapper có hai overloads: overload A bind values, overload B ghép raw SQL fragments. SAST báo cả hai. Hãy thiết kế custom sanitizer model **chỉ cho overload A** và ít nhất bốn safe/unsafe fixtures để chứng minh không làm mất TP.

### Bài tập D — XSS qua ba output contexts

Một displayName được hiển thị trong HTML text, attribute và inline JavaScript. Reviewer muốn mark mọi alert FP do template engine auto-escaping. Hãy phân tích từng context, required evidence, test cases và verdict phù hợp.

### Bài tập E — SSRF và trusted partner config

User chọn partner ID, server lấy URL từ config; HTTP client theo redirects. Nêu trust boundaries, actor nào sửa config, egress/redirect/DNS policy cần kiểm tra và vì sao không nên FP chỉ dựa trên việc user không nhập URL trực tiếp.

### Bài tập F — Path traversal

Code dùng Path.resolve(...).normalize().startsWith(base) trước Files.readAllBytes. Hãy nêu symlink/TOCTOU/race, opaque ID alternatives, authorization và tests. Phân loại warning thành FP/TP/Unknown với từng giả định.

### Bài tập G — Secret fixture

Một test file có chuỗi "example-password" và một token có vẻ thật. Hãy xác định loại evidence đủ để gọi dummy string FP, cách xử lý token có khả năng valid, phạm vi history/CI artifacts và cách tránh paste secret vào ticket.

### Bài tập H — Broken authorization

SAST báo controller thiếu annotation; service có custom policy nhưng test chỉ mock policy luôn trả false. Hãy đề xuất true integration/role/tenant/object tests, review filters, bypass routes và cách đánh giá independent evidence.

### Bài tập I — Rule tuning làm mất TP

Sau custom model update, SQLi alerts giảm 90%. Một seeded raw SQL fixture cũng không còn được báo. Hãy xử lý gate failure, rollback model, root cause và risk của các releases đã scan bằng model lỗi.

### Bài tập J — Suppression quá rộng

Developer thêm exclusion toàn src/main/java để né 200 alerts. Hãy viết review comment nêu impact, yêu cầu triage, allowed scope, approval, expiry, fixture regression và metrics monitoring.

### Bài tập K — Fingerprint sau refactor

Một finding FP có line 100 chuyển sang line 220 khi refactor, đồng thời method signature đổi. Hãy thiết kế workflow mapping finding, điều kiện reuse rationale, change triggers và cách không tự close/reopen sai.

### Bài tập L — Tính metrics từ operational alerts

Team có 300 alerts, 120 đã triage: 40 TP, 80 FP; 180 còn untriaged. Tính precision và FP share **chỉ cho tập đã triage**, nêu selection bias có thể có và giải thích vì sao không thể tính FPR/recall toàn codebase.

### Bài tập M — Risk accepted hay FP?

Một internal-only admin endpoint có unsafe deserialization nhưng bị network ACL chặn từ Internet. Risk owner muốn “FP vì không public”. Viết technical verdict, risk decision, compensating control tests, residual risk và reassessment trigger.

### Bài tập N — Cấu hình IaC

IaC scanner báo bucket public vì template thiếu public access block; cloud org policy đang chặn anonymous access. Phân biệt rule về **declared control compliance** và rule về **effective exposure**; xác định khi nào FP/TP/Mitigated/Not applicable.

### Bài tập O — Evidence record và Claim–Argument–Evidence

Tạo YAML triage cho JDBC FP, điền code/commit/tool/rule, data flow, binding API semantics, synthetic test, reviewer, scope/exclusions và trigger. Sau đó viết một claim **không khẳng định toàn system an toàn**.

### Bài tập P — FP reversal và sự cố

Nửa năm sau, custom wrapper từng an toàn được refactor để nối raw SQL. Scan vẫn không báo vì model cũ đã đánh “sanitizer”. Hãy đề xuất incident triage, affected release scoping, rollback/fix, re-enable rule, fixture tests, audit các FP cùng rationale và metrics cần công bố.

### Bài tập Q — Xây chương trình 90 ngày

Thiết kế false-positive management cho Java team:
1. Chuẩn hóa taxonomy/required rationale.
2. Inventory SAST rules/framework models và owners.
3. Chọn high-noise/high-risk rules ưu tiên.
4. Tạo safe/unsafe fixtures cho JDBC, XSS, SSRF và secrets.
5. Triển khai bounded suppressions, approvals, expiry.
6. Gắn triage records với fingerprints/commits.
7. Kiểm tra scan health/coverage và CI gates.
8. Huấn luyện reviewers về authorization/taint analysis.
9. Đo precision, FP share, untriaged backlog và reversals.
10. Đưa kết luận vào assurance report với scope/limitations.

### Bài tập R — Đánh giá tổng hợp

Một nền tảng có:
- 600 SAST alerts; 200 được mark FP do custom JDBC wrapper.
- 70 alerts suppressed theo project-level rule disable.
- 30 raw SQL fixtures không còn được báo sau model upgrade.
- 100 alerts chưa triage.
- SCA báo 0 CVE nhưng advisory feed đã lỗi.
- Một API vừa public một internal endpoint từng được coi unreachable.
- FP rationale không gắn build/commit.
- CI dashboard báo 98% alerts “resolved”.

Hãy:
1. Phân loại technical findings, FP evidence, suppression risks, scanner failures và scope changes.
2. Xác định những con số không thể kết luận từ dữ liệu hiện có.
3. Thiết kế immediate containment và verification ưu tiên.
4. Viết matrix owner/action/due date theo risk.
5. Định nghĩa 10 test cases để khôi phục rule detection quality.
6. Xây dashboard tách TP/FP/Unknown/Accepted Risk/Tool Error.
7. Viết claim có giới hạn và recovery plan cho continuous assurance.

## 35. Checklist triage và false-positive assurance

Checklist giúp review, **không tự chứng minh không còn vulnerabilities**.

- [ ] Scanner có scope/ruleset/tool version và scan run identity rõ.
- [ ] Scan completed/healthy, không timeout/skip/partial mà báo 0 findings.
- [ ] Finding ID, rule ID, source revision, module, code location được ghi.
- [ ] Rule semantics/weakness được đọc rõ trước khi quyết định.
- [ ] Taint source và quyền attacker kiểm soát dữ liệu được đánh giá.
- [ ] Propagation, guards, validators/sanitizers và sink được kiểm chứng.
- [ ] Sanitizer được xác minh đúng output/interpreter context.
- [ ] Framework/library wrapper, overload và version có supporting evidence.
- [ ] Build inclusion và runtime scope được xác định khi cần.
- [ ] Authorization/object/tenant relationships không bị bỏ qua.
- [ ] Không dùng severity, exploit reproduction failure hoặc WAF để tự gọi FP.
- [ ] FP được phân biệt với TP, mitigation, accepted risk, not applicable, duplicate.
- [ ] Needs Investigation/Evidence Gap có owner và next actions.
- [ ] FP rationale chỉ rõ technical reason, scope, test và limitations.
- [ ] Suppression hẹp đúng rule/call site/fingerprint, không tắt toàn thư mục/rule.
- [ ] Suppression có approval, owner, expiry/review trigger theo policy.
- [ ] Rule/model tuning có safe và unsafe seeded fixture tests.
- [ ] Scanner vẫn phát hiện representative unsafe cases sau tuning.
- [ ] Analyzer/ruleset/framework upgrades làm trigger reassessment.
- [ ] Code refactor/finding line change được quản lý qua fingerprint/migration.
- [ ] CI/CD gates không coi scanner health failure là no findings.
- [ ] SAST baselines không bỏ new TP hoặc re-exposed old risk.
- [ ] Reports/triage records được bảo vệ khỏi sửa/xóa trái phép.
- [ ] Không đính kèm raw secrets/PII trong evidence.
- [ ] Developer và reviewer independence phù hợp criticality.
- [ ] FP share/precision đúng mẫu số; không bịa FPR/recall khi thiếu TN/FN.
- [ ] Metrics nêu population/period/selection bias và findings chưa triage.
- [ ] FP reversals được theo dõi và điều tra nguyên nhân.
- [ ] Claims có source/build/rule/version/scope và supporting evidence.
- [ ] Separate findings/risk controls cho vấn đề khác ở cùng endpoint.
- [ ] Risk acceptance không biến technical TP thành FP.
- [ ] Có continuous monitoring và trigger reopen sau changes/incident.
- [ ] Executive report mô tả rõ còn những risk/gap nào chưa xử lý.

## 36. Ghi nhớ

1. **False positive là một cảnh báo phân tích tĩnh không đúng đối với weakness/target/conditions đã được đánh giá**, không phải tên gọi cho mọi finding khó xử lý.
2. **True positive, false positive, false negative và true negative** là bốn trạng thái của detection so với ground truth trong một population; operational alerts thường không đủ dữ liệu để tính recall/FPR toàn hệ thống.
3. **Precision = TP/(TP+FP)** và **FPR = FP/(FP+TN)** là hai chỉ số khác nhau; gọi FP/alerts là FPR là sai về mẫu số.
4. SAST cần hiểu **source → data flow → sanitizers/validators → sink** và framework semantics; thiếu model có thể tạo FP, tuning sai có thể tạo FN.
5. **Một FP ở SQL injection không chứng minh endpoint không có BOLA, XSS hoặc privacy risk**; kết luận phải đúng rule và call site.
6. **Không tái hiện exploit, WAF chặn, risk thấp hoặc endpoint nội bộ** không tự chứng minh FP; có thể là TP với mitigation/risk acceptance.
7. Java/Spring wrappers, prepared queries, template auto-escaping, safe file IDs và secret fixtures cần **đánh giá theo context, API/version và runtime path**.
8. **Suppression chỉ là cơ chế lọc**, không phải quyết định kỹ thuật; nên hẹp, có owner, rationale, approval và review triggers.
9. **Tối ưu SAST không chỉ giảm số alerts**, mà phải giữ detection của true-positive fixtures, scan health và coverage.
10. **Finding fingerprint và versioned evidence** giúp không mất lịch sử triage qua refactor/analyzer upgrades.
11. **Claim–Argument–Evidence** cần chỉ rõ dữ liệu, lập luận, code/config/tests, giới hạn, thời điểm và reviewer.
12. **Triage verdict khác risk decision**: FP, TP, Not applicable, Mitigated, Risk Accepted và Insufficient Evidence không được gộp.
13. **Scanner failure hoặc coverage gap không là zero vulnerabilities**; phải báo Unknown/Unhealthy cho tới khi có kết quả hợp lệ.
14. **Continuous false-positive assurance** là vòng lặp *finding → technical triage → evidence/review → bounded suppression/model tuning → rule QA → monitoring → reassessment*, duy trì khả năng phát hiện rủi ro trong phát triển và vận hành.








