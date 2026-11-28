# Quality gate trong static analysis: chốt chất lượng và rủi ro bảo mật bằng bằng chứng

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích **quality gate** trong phân tích tĩnh (static analysis), phân biệt **scanner, rule, finding, triage, policy, quality gate, CI check, release approval** và **assurance claim**.
2. Xây dựng **gate policy có thể kiểm thử**: tài sản/phạm vi, điểm kiểm soát, loại finding, severity, confidence, trạng thái, thời hạn, ngoại lệ, nguồn quy tắc và người có thẩm quyền.
3. Chọn **PR/merge, build, release, deployment và operational gates** theo mục tiêu; tách gate trên **new code** và quản trị **existing security debt** mà không che lỗ hổng tồn đọng.
4. Xử lý đúng **PASS, FAIL, BLOCKED, INDETERMINATE, SKIPPED_WITH_AUTHORIZATION và EXCEPTION_ACTIVE**, đặc biệt khi scanner timeout, mất quyền truy cập hoặc kết quả scan không đầy đủ.
5. Triển khai quy trình phân tích tĩnh có **coverage và provenance**: chuẩn bị source, chạy scanner/rulepack được duyệt, kiểm chứng tính đầy đủ, chuẩn hóa kết quả, triage, ra quyết định và lưu evidence.
6. Phân tích **false positive, false negative, suppression, baseline, accepted risk, vulnerability fix và reintroduced findings**; thiết kế quy trình có owner, expiry, independent review và retest.
7. Bảo vệ **CI/CD gate** khỏi bypass, untrusted pull request, thay chính sách, giả mạo kết quả, cache/artifact poisoning, và token/secret exposure.
8. Viết **quality gate specification**, pseudocode/policy-as-code, kịch bản Gherkin, ma trận verification, metrics, findings và assurance claim có giới hạn.

Trong module **SECURITY_SECURITY_ASSURANCE**, người học cần biết đánh giá **có bằng chứng** rằng hệ thống đáp ứng mục tiêu bảo mật: từ rủi ro, yêu cầu, security controls đến kiểm thử, audit, xử lý findings và assurance liên tục trong phát triển/vận hành. Bài **Quality gate**, thuộc chương **Static analysis**, trả lời: **Khi nào kết quả phân tích tĩnh đủ tin cậy để cho phép một thay đổi đi tiếp, khi nào phải chặn, và cần chứng cứ nào để bảo vệ quyết định đó?**

> **Thông điệp chính:** Một quality gate đáng tin không phải điều kiện “scanner chạy xanh” hay “không thấy lỗi Critical”. Nó là **quyết định có chính sách, scope, evidence và quyền phê duyệt rõ**, kết hợp kiểm tra scanner thực sự chạy đúng, có bao phủ phần mã cần đánh giá, xử lý finding theo rủi ro và chặn đường bypass. **PASS của SAST không bao giờ đồng nghĩa toàn bộ ứng dụng an toàn.**

## 1. Quality gate là gì?

**Quality gate** là một điểm kiểm soát trong vòng đời phần mềm, nơi một hoặc nhiều điều kiện được đánh giá để quyết định **tiếp tục, dừng, yêu cầu xử lý hoặc chuyển sang luồng ngoại lệ có thẩm quyền**. Trong **static analysis**, gate thường sử dụng các finding từ công cụ phân tích tĩnh kết hợp với:

- Trạng thái **scanner execution**: có chạy và thành công thực sự hay không?
- **Policy/ruleset**: chuẩn đánh giá nào, phiên bản nào, mức rủi ro áp dụng?
- **Target/scope**: repository, commit, branch, file, language, module, environment.
- **Analysis completeness**: phần nào được scan, phần nào bị loại/không hỗ trợ?
- **Finding disposition**: confirmed, suspected, false positive, duplicate, risk accepted, fixed, reopened.
- **Threshold/conditions**: điều kiện fail/pass có nguồn phê duyệt.
- **Risk owner, exception và approval**: ai được phép nhận rủi ro trong giới hạn nào?
- **Decision evidence**: scanner version, rulepack, logs, report digest, reviewer và policy evaluation.

Ví dụ: Một PR mới bổ sung truy vấn SQL xây dựng bằng chuỗi user input. Scanner tạo finding `SQL_INJECTION` có severity theo rulepack. Gate có thể **FAIL** PR nếu finding thuộc điều kiện chặn đã được duyệt, buộc sửa hoặc triage có bằng chứng. Nếu scanner không chạy do hết quota, gate phải báo **BLOCKED/INDETERMINATE**, không được coi “0 findings”.

### 1.1. Phân biệt các thành phần

| Khái niệm | Câu hỏi giải quyết | Ví dụ |
|---|---|---|
| **Security objective** | Cần bảo vệ thuộc tính nào? | Không thực thi truy vấn không an toàn từ đầu vào |
| **Security requirement** | Hệ thống phải đáp ứng điều gì? | Dữ liệu untrusted không được đi vào SQL execution thiếu parameterization |
| **SAST engine/scanner** | Phân tích source/build artifacts nào, bằng thuật toán gì? | Source/dataflow analyzer |
| **Rule/rulepack** | Mẫu hoặc dòng dữ liệu nào bị coi đáng ngờ? | Injection sink nhận tainted value |
| **Finding** | Kết quả phân tích cụ thể là gì? | Flow từ request parameter tới SQL sink |
| **Triage** | Finding có áp dụng, duplicate hay false positive? | Xác nhận nguy cơ ở đường API |
| **Quality gate policy** | Điều kiện nào cho phép tiến tới bước tiếp theo? | Chặn confirmed high-risk new findings chưa xử lý |
| **CI check** | Điểm tích hợp kỹ thuật truyền quyết định? | Required job status trên PR |
| **Exception/risk acceptance** | Ai có thể cho phép sai lệch trong phạm vi/thời hạn nào? | Exception có compensating controls và expiry |
| **Evidence** | Có chứng minh điều kiện và quyết định gate không? | Report, metadata, signed policy/result, logs |
| **Assurance claim** | Kết luận có căn cứ trong scope nào? | PR X không có new blocking findings trong SAST scope Y |

Quality gate là **control phòng ngừa** nếu nó thực sự chặn bước tiếp theo. Scanner cũng có thể hỗ trợ **detective control** qua cảnh báo/ticket. Nếu tất cả findings chỉ được lưu mà không ảnh hưởng release, đó **không phải enforcement gate** dù dashboard có trạng thái màu xanh/đỏ.

### 1.2. Chất lượng ≠ bảo mật tuyệt đối

Tên “quality gate” đôi khi bao gồm code coverage, duplicate code, maintainability, test failures, code smells, license, dependency hoặc IaC checks. Trong chương **Static analysis**, bài này nhấn mạnh **security findings từ phân tích tĩnh**; có thể kết hợp những tín hiệu khác khi policy cho phép nhưng phải giữ phân biệt:

- **SAST** phân tích mã nguồn/code structure và có thể theo dõi dataflow.
- **SCA** phân tích thành phần/phụ thuộc và known vulnerabilities; không thay SAST.
- **Secrets scanning** tìm dấu hiệu secret trong code/history; cũng có giới hạn.
- **IaC/static config checks** kiểm tra chính sách cấu hình; cần đối chiếu runtime.
- **DAST/pentest** đánh giá hành vi khi chạy; không thay source analysis.
- **Runtime monitoring** xác minh điều kiện vận hành; không tự sửa lỗ hổng mã.

Một gate “tổng hợp” phải ghi rõ **tín hiệu nào thuộc tiêu chí nào**. Đừng báo “SAST PASS” để ám chỉ SCA, penetration testing và threat modeling đã hoàn thành.

### 1.3. Ví dụ đánh giá ban đầu

Giả sử một service có:

- 2 findings mới loại injection có khả năng khai thác đáng kể.
- 8 findings đã tồn tại từ trước, đang theo remediation plan.
- 1 module Java chưa được scan do build lỗi.
- Scanner báo completed vì wrapper bỏ qua lỗi ở module Java.

Gate **không được PASS** chỉ vì tổng số findings mới trong các module được scan bằng 0. Cần đánh giá:

1. Hai findings mới có thuộc gate blocking policy không?
2. Tám existing findings có còn trong scope SLA/risk/exception không?
3. Module Java bị bỏ sót có nằm trong **required coverage** không?
4. Scanner execution có thực sự hoàn thành?
5. Có bypass path từ merge tới deploy không đi qua gate?

Đây là lý do cần **policy + scan completeness + findings + evidence**, không chỉ một con số.

## 2. Đặt quality gate ở đâu trong secure SDLC?

### 2.1. Các điểm chặn

| Vị trí | Mục tiêu | Nhược điểm nếu chỉ dùng vị trí này |
|---|---|---|
| **Developer/local/IDE** | Phản hồi nhanh trước commit | Không có bằng chứng tập trung, dễ bị tắt |
| **Pre-commit/pre-push** | Phát hiện mẫu lỗi sớm | Có thể bypass cục bộ, không nên là release authority duy nhất |
| **Pull request gate** | Chặn thay đổi chưa đạt trước merge | Chỉ kiểm tra changed/new code có thể bỏ existing risk |
| **Protected branch gate** | Xác minh commit hợp nhất đúng rule/check | Check trên PR head có thể khác merge result |
| **Build/package gate** | Phân tích code/dependencies tại trusted build | Có thể quá muộn nếu PR đã merge và phát sinh debt |
| **Release candidate gate** | Chốt đủ bằng chứng trước publish/promote | Dễ trì hoãn phát hiện tới sát deadline |
| **Deployment/admission gate** | Chặn artifact không đạt policy/provenance | Không đủ nếu deployment bypass hoặc attestation bị giả |
| **Periodic/operational reassessment** | Phát hiện rule mới, scanning gap, findings tồn đọng | Detective, không thể thay gate phòng ngừa trước đó |

Nên chọn **tầng kiểm soát bổ trợ** theo mức rủi ro: IDE/PR phản hồi sớm; protected branch chặn merge sai; trusted build/release đối chiếu source và policy; deployment chặn artifact sai; operational review xử lý drift và findings mới xuất hiện.

### 2.2. Gate cho PR không đồng nhất gate cho release

**PR gate** thường dùng câu hỏi:

> “Thay đổi trong PR có tạo **new findings** thuộc policy chặn, và scan có đủ coverage cho code được sửa không?”

**Release gate** dùng câu hỏi rộng hơn:

> “Source revision và artifact chuẩn bị phát hành đã được phân tích đầy đủ theo policy hiện hành, có findings chặn chưa xử lý hoặc exceptions quá hạn không, và report có gắn với đúng artifact đó không?”

Một PR có thể PASS vì **không tạo new findings**, trong khi release vẫn có **existing critical debt** đã quá hạn. Cả hai kết luận có thể đúng nếu policies được công bố rõ; **không được suy PR PASS ⇒ release PASS**.

### 2.3. Sơ đồ pipeline có gate nhiều lớp

~~~mermaid
flowchart TD
    A["Developer / PR"] --> B["Run SAST on proposed changes"]
    B --> C{"Scan complete and credible?"}
    C -- "No" --> D["BLOCKED/UNKNOWN; investigate scanner"]
    C -- "Yes" --> E["Evaluate new-code findings against PR policy"]
    E --> F{"PR gate decision"}
    F -- "FAIL" --> G["Remediate / triage / approved exception"]
    G --> B
    F -- "PASS" --> H["Protected-branch merge"]
    H --> I["Trusted build + full scoped analysis"]
    I --> J["Release gate: full findings, debt SLA, provenance"]
    J --> K{"Release allowed?"}
    K -- "No" --> L["Resolve findings / risk decision"]
    L --> I
    K -- "Yes" --> M["Verified artifact + deployment admission"]
    M --> N["Runtime/operational assurance + rule updates"]
    N --> B
~~~

Sơ đồ là **mô hình khái niệm**. Mỗi công cụ CI có triggers, merge strategies và permissions khác nhau. Reviewer phải kiểm tra **effective configuration**, không mặc định sơ đồ tương ứng đúng với thực tế.

## 3. Các yếu tố làm quality gate đáng tin

### 3.1. Năm câu hỏi bắt buộc

Một gate chỉ nên trả PASS khi trả lời có căn cứ:

1. **Đúng đối tượng?** Repo/commit/PR/build/environment cần đánh giá có trùng đối tượng của quyết định không?
2. **Quét đủ và đúng?** Scanner version, rules, languages, targets, generated sources, dependencies và coverage có phù hợp?
3. **Phát hiện được phân xử theo policy?** Blocking findings mới/tồn đọng, false positive và exceptions có evidence?
4. **Quyết định được enforce?** Protected branch/deployment thực sự chặn nếu FAIL/UNKNOWN?
5. **Có thể audit và tái lập?** Policy/version, result/digest, metadata và reviewer được lưu?

### 3.2. Sai lầm khi đếm findings

| Cách kết luận | Vấn đề | Cách tốt hơn |
|---|---|---|
| “0 findings = secure” | Có thể không scan hoặc scanner thiếu rules | Kiểm tra completeness, rule coverage và limitations |
| “Không có Critical là PASS” | High/Medium có thể nghiêm trọng theo context | Risk-based policy theo vulnerability class và exposure |
| “100% files scanned” | Một file scan chưa chắc mọi dataflow được phân tích | Ngôn ngữ, analysis mode, build success và reachable scope |
| “2 tools cùng PASS” | Hai công cụ có thể cùng blind spot | Independent scope/analysis reasoning |
| “All alerts reviewed” | Disposition có thể sai, expired hoặc do một người tự duyệt | Triage evidence, reviewer authority và sampling |
| “CI green = gate enforced” | Required check có thể không bắt buộc hoặc bị skip | Verify protected branch rules và bypass actors |
| “Fix committed = finding closed” | Scan trên commit cũ hoặc fix không effective | Rerun và đối chiếu source/artifact revision |

### 3.3. Quality gate là quyết định đa tín hiệu

Quyết định có thể dùng:

- **Finding characteristics:** rule/CWE, severity, confidence, exploitable path, asset/data sensitivity.
- **Origin/timing:** new, pre-existing, reopened, introduced by changed code, detected by new rule.
- **Triage quality:** confirmed, disputed, false positive, duplicate, risk accepted.
- **Process condition:** scanner passed, report complete, rulepack approved, no policy bypass.
- **Lifecycle:** exception/SLA expiry, target release, remediation stage.
- **Operational controls:** blockers ở release, mitigation đã kiểm chứng và risk owner decision.

Không nhất thiết dùng mọi tín hiệu trong một policy. Nhưng **các tín hiệu được dùng phải định nghĩa rõ và có bằng chứng**.

## 4. Xác định chính sách quality gate

### 4.1. Bắt đầu từ security objective và risk appetite

Không nên xây quality gate bằng một điều kiện tùy tiện như “tối đa 10 lỗi” vì số lượng không cho biết **loại lỗi, đường tấn công, ảnh hưởng và coverage**. Bắt đầu từ:

1. **Business/security objectives:** Không lộ dữ liệu liên tenant, không thực thi input untrusted như command, không hard-code secrets.
2. **Threat model và security requirements:** Các source–sink paths, privileged actions, object authorization và trust boundaries quan trọng.
3. **Asset criticality:** Payment, identity, data protection, internal tooling, development sandbox.
4. **Rule coverage và detection capability:** SAST có hỗ trợ language/framework/ruleset cần không?
5. **Governance:** Ai phê duyệt severity threshold, risk tier, exceptions và scan waivers?
6. **Operational feasibility:** Thời gian pipeline, mức false positive, release cadence và khả năng xử lý findings.
7. **Verification:** Làm sao chứng minh policy được thực thi, không chỉ được viết?

**Không có một ngưỡng tuyệt đối cho mọi hệ thống.** Các ví dụ severity/threshold ở đây chỉ để minh họa phương pháp; khi áp dụng thật cần decision record của risk/security owner.

### 4.2. Phân loại finding một cách nhất quán

| Thuộc tính | Ý nghĩa | Cần lưu ý |
|---|---|---|
| **Rule ID / weakness class** | Mẫu lỗi như SQL injection, XSS, path traversal, unsafe deserialization | Rule ID không phải proof-of-exploit |
| **CWE mapping** | Phân loại loại điểm yếu | CWE có thể rộng và có nhiều mapping |
| **Scanner severity** | Mức độ nghiêm trọng do công cụ đề xuất | Có thể không biết business impact |
| **Confidence** | Độ tin tưởng phát hiện theo thuật toán/công cụ | Không đồng nghĩa exploitability |
| **Reachability/context** | Đường dataflow/attack path có thể tiếp cận trong kiến trúc? | Phân tích cần source, input, guards và boundary |
| **New/existing** | Finding mới do PR hay thuộc baseline? | Mapping có thể đổi vì refactor hoặc rulepack |
| **Confirmed/suspected** | Được reviewer xác nhận đến mức nào? | Không được sửa result tùy hứng để qua gate |
| **Exception/disposition** | Có được risk owner chấp nhận? | Scope/expiry và mitigation là bắt buộc nếu policy yêu cầu |
| **Status in current revision** | Open, fixed, reopened, unknown | Phải đối chiếu commit và scan result mới |

### 4.3. Severity và confidence là hai trục khác nhau

Ví dụ:

- **High severity, high confidence:** Dataflow từ request input tới command execution thiếu validation; có thể cần chặn ngay.
- **High severity, low confidence:** Tool suy diễn đường không đủ context; cần triage, không tự loại.
- **Low severity, high confidence:** Lỗi có thể tái hiện rõ nhưng impact nhỏ trong scope; policy có thể cho phép xử lý theo SLA.
- **High confidence false positive:** Tool chỉ ra đúng cú pháp nhưng threat model cho thấy guard đáng tin trên đường khác; phải giữ explanation/test chứ không gắn nhãn sai mà không chứng minh.

**Severity công cụ không tự đại diện risk.** Context của hệ thống như dữ liệu tài chính, privileged execution, multi-tenant boundary có thể nâng ưu tiên; reachability bất khả thi **được chứng minh** có thể giảm risk.

### 4.4. Policy theo vulnerability class

Một ví dụ mang tính lý luận:

| Rule family | Criticality | Gate policy tham khảo | Verification |
|---|---|---|---|
| Injection từ untrusted input tới SQL/OS command | Rủi ro dữ liệu/đặc quyền | Chặn khi điều kiện phân tích và scope xác nhận | Dataflow review, negative integration test |
| Hard-coded production secret | Rủi ro lộ credential | Chặn cả commit mới và xem xét secret rotation | Secret scanner + credential owner evidence |
| Weak cryptographic primitive | Phụ thuộc mục đích và baseline | Chặn khi trái approved crypto baseline | Code/config review, crypto owner decision |
| Unsafe deserialization | Phụ thuộc input trust boundary | Risk-based block khi attacker-controlled inputs | Source-to-sink/path reasoning |
| Unsafe logging of sensitive data | Privacy/compliance scope | Chặn theo phân loại dữ liệu và policy | Field map, log/output tests |
| Maintainability/code style | Không nhất thiết security-critical | Có thể đưa vào nonsecurity quality gate | Team quality standards |

Điều kiện “chặn khi được xác nhận” cũng cần quy tắc khi **chưa được triage kịp**. Một finding High chưa review không nên tự chuyển thành PASS chỉ vì chưa có người xác nhận.

### 4.5. Rulepack và policy versioning

Gate output phải gắn với:

- **Gate policy ID/version**, owner và approval.
- **Scanner engine version** và plugins.
- **Rulepack ID/version/commit**; nguồn và checksum nếu phù hợp.
- Exclusion config, generated-code policy, language analyzers.
- Security baseline/risk tier áp dụng cho project.
- Effective PR/release policy tương ứng.

Vì ruleset thay đổi có thể làm xuất hiện findings mới mà code không đổi, **evidence từ scan cũ không tự phù hợp với policy mới**. Cần có **rule-change impact review** và rebaseline khi chính sách xác định.

### 4.6. Ngưỡng không nên khuyến khích hành vi làm đẹp số liệu

Một policy như “không quá 5 High findings” có thể vô tình khuyến khích:

- Chia/move code để scanner không thấy.
- Tắt rules gây phát hiện.
- Đánh dấu false positive vô căn cứ.
- Không nâng rulepack để giữ số không đổi.
- Dồn vulnerability sang một module ngoài scope.

Nên dùng **security properties, severe risk exceptions, freshness, ownership và scan coverage**; có thể áp **hard blockers cho new critical classes** kết hợp **remediation plan cho legacy debt** theo policy được phê duyệt.

## 5. Mô hình trạng thái của quality gate

### 5.1. Quyết định không chỉ nhị phân

| Decision | Ý nghĩa | Có được merge/release? |
|---|---|---|
| **PASS** | Các điều kiện gate áp dụng đều được chứng minh đạt, trong scope/version | Có, nếu các gates khác cũng đạt |
| **FAIL** | Có ít nhất một điều kiện chặn được xác nhận theo policy | Không theo đường thông thường |
| **BLOCKED / INDETERMINATE** | Thiếu scan, scanner lỗi, results không toàn vẹn, scope chưa đủ | Không được tự coi PASS |
| **PENDING_TRIAGE** | Findings có khả năng chặn chưa được phân loại đủ | Theo policy, thường không cho vào protected release |
| **EXCEPTION_ACTIVE** | Có sai lệch được thẩm quyền chấp thuận theo scope/expiry | Có thể đi theo exception path, không đồng nghĩa PASS |
| **SKIPPED_AUTHORIZED** | Scan được bỏ qua có lý do/authority được policy cho phép | Có điều kiện và evidence rõ; không gộp PASS |
| **NOT_APPLICABLE** | Thành phần/gate thực sự không áp dụng, có lý do | Exclude có kiểm soát và bằng chứng |
| **STALE / EXPIRED** | Kết quả không còn đại diện revision hoặc policy hiện tại | Không dùng thay current PASS |

**Chú ý:** Bộ trạng thái trên là mô hình logic đề xuất, không phải chuẩn bắt buộc của mọi CI tool. CI provider có thể chỉ nhận success/failure/pending; cần ánh xạ có chủ đích để **BLOCKED, UNKNOWN và EXCEPTION** không bị che thành một generic “success”.

### 5.2. Bảng logic ưu tiên

Một chính sách nghiêm ngặt có thể đánh giá theo thứ tự:

1. **Target mismatch?** Source revision khác, report của branch khác hoặc artifact không đúng → BLOCKED.
2. **Scan incomplete?** Timeout, analyzer crash, missing required module, rulepack không load → BLOCKED.
3. **Policy/config invalid?** Rulepack, exception store hoặc baseline không được xác minh → BLOCKED.
4. **Blocking finding?** Finding thuộc rule chặn, chưa fixed/exception có hiệu lực → FAIL.
5. **Authorized exception?** Ghi decision riêng, scope hẹp và expiry, có thể chuyển theo exceptional flow.
6. **Không có blocker và điều kiện đủ?** → PASS.

Tùy chính sách có thể phân biệt **FAIL với BLOCKED** khi vừa có critical finding vừa mất một module. Nhưng tuyệt đối không gán PASS khi bằng chứng thiếu.

### 5.3. Khi scanner timeout có được fail-open?

**Fail-open** trong release path tức là **cho phép merge/deploy dù không có kết quả đáng tin**. Có thể có ngoại lệ do business continuity được risk authority phê duyệt, nhưng không nên là mặc định.

Hướng xử lý:

- Tạm **BLOCKED** và retry có giới hạn.
- Kiểm tra scanner outage, rule service, license/quota, cache và build dependencies.
- Nếu cần emergency release, dùng **time-bound exception path** với controls bù, independent approval và audit.
- Không biến `scanner failed` thành `no vulnerabilities` trong report.
- Khi tool phục hồi, chạy **reassessment** và xử lý phát hiện.

Một service cần vá khẩn cấp có thể phải release ngay cả khi scanner outage; khi đó policy nên đưa ra **đường khẩn cấp có kiểm soát**, thay vì lén biến tất cả scanner failures thành pass.

### 5.4. Gate decision phải gắn chính xác revision

Ví dụ:

- Scan PASS trên commit `C1`.
- Developer push commit `C2`.
- CI UI vẫn hiển thị check xanh cho C1 hoặc cache kết quả cũ.
- Merge/release dùng C2.

Nếu không kiểm tra **commit equality**, gate có thể cho code chưa phân tích vào production. Tương tự với merge commit hoặc rebased PR: hãy kiểm tra policy yêu cầu scan **PR head, merge-result revision hay exact release commit**, và enforce đúng đối tượng.

### 5.5. Gate outcome và remediation state độc lập

Một vulnerability được đánh dấu `fixed-in-branch` chỉ là trạng thái workflow; để PASS cần **scan/review trên revision thực chứa bản sửa**. Một approved exception cho phép release có kiểm soát **không sửa lỗ hổng**.

Tách:

- **Finding state:** open, suspected, confirmed, fixed, risk-accepted, suppressed, duplicate.
- **Scan execution state:** complete, failed, partial, skipped.
- **Gate outcome:** PASS, FAIL, BLOCKED, exception route.
- **Release state:** not approved, approved, deployed, rolled back.

Trộn bốn lớp này sẽ khiến dashboard báo “Green” nhưng không rõ **cái gì thực sự đã được xác minh**.

## 6. Baseline, new code và legacy security debt

### 6.1. Vì sao cần baseline?

Một hệ thống lâu năm có hàng trăm findings; ép “zero findings trước khi merge” có thể làm đình trệ mọi sửa lỗi, kể cả các bản vá bảo mật quan trọng. **Baseline** là một snapshot các findings/conditions tồn tại trước một thời điểm, giúp:

- Chặn **giới thiệu lỗi mới** trong khi quản trị debt cũ.
- Phân công ownership và deadlines cho existing findings.
- Theo dõi fix/reopen/regression và rulepack impact.
- Không biến PR gate thành yêu cầu “sửa toàn bộ codebase”.

Nhưng baseline phải là **công cụ minh bạch hóa security debt**, không phải phương tiện hợp pháp hóa lỗ hổng.

### 6.2. Không suy “new finding” chỉ bằng dòng mã thay đổi

Cách xác định new/existing có thể dựa vào:

- Matching fingerprint/semantic identity từ scanner.
- Code location, rule ID, dataflow và source/sink.
- Source branch và comparison base.
- Tác động của rename/refactor và thay đổi rulepack.

**Diff-only scan** có thể bỏ sót vulnerability tạo ra bởi thay đổi ở chỗ khác trong call graph. Một method nguy hiểm nằm trong file không sửa có thể trở thành reachable vì PR thêm route mới. Vì vậy, đối với critical paths có thể cần **full-code or cross-file analysis** và dùng baseline chỉ để phân loại kết quả.

### 6.3. Hai chính sách bổ trợ

**New-code gate**

> Không đưa mới blocking findings vào protected branch hoặc release theo định nghĩa và risk policy được phê duyệt.

**Existing-debt management**

> Mọi existing blocking/important findings đều có owner, severity/risk, disposition, remediation deadline, exception nếu có, và kiểm tra quá hạn tại release/periodic gate.

Nếu chỉ có new-code gate, đội có thể sống mãi với critical vulnerability ở code cũ. Nếu chỉ có legacy debt scan, vulnerabilities mới có thể được merge rồi đưa vào backlog không được kiểm soát.

### 6.4. Baseline cần được bảo vệ

Baseline là một input quan trọng của gate. Attacker hoặc developer muốn bypass có thể:

- Thêm finding mới vào baseline bằng một commit không review.
- Tăng timestamp/baseline cutoff để coi lỗi vừa tạo thành “legacy”.
- Đổi fingerprint hoặc rule mapping.
- Xóa findings khỏi tracking mà chưa sửa.
- Đổi source branch/repo để scan không so sánh đúng.

Do đó:

- Baseline có **ID, source commit, approved change history và integrity reference**.
- Việc cập nhật baseline được review theo security governance.
- Baseline change có thể là **security-sensitive change** cần owner approval.
- Không cho code trong PR tự quyết định baseline áp dụng mà không có kiểm tra.
- Các findings loại khỏi gate vẫn phải có **debt tracking** và evidence.

### 6.5. Scanner/rulepack nâng cấp gây findings mới

Khi rule mới hoặc engine mới phát hiện lỗ hổng vốn đã có trong source:

- Không nên gắn “developer tạo lỗi” chỉ vì tool mới nhìn thấy.
- Không nên tự động bỏ qua vì “code cũ”.
- Phân loại **newly detected existing issue**, đánh giá risk và đưa vào remediation process.
- Chốt policy transition, owner và deadlines theo risk.
- Đối với exploited critical issue, có thể phải **block release hoặc áp mitigation ngay**, không chờ đợt cleanup.

Tách **regression do code change** và **new detection do detection capability change** giúp quản lý công bằng nhưng không làm giảm security accountability.

### 6.6. Tính metric theo baseline

Giả sử một repository có:

- Baseline được phê duyệt: 48 findings cũ.
- Sau một PR: 3 findings cũ đã fix, 2 findings mới xuất hiện.
- Trong 2 findings mới: 1 thuộc blocking policy, 1 thuộc nonblocking policy.

Kết quả:

~~~text
Baseline existing issues             = 48
Fixed existing issues in this PR     = 3
Existing issues remaining (assumed)  = 45
New issues detected                  = 2
New blocking issues                  = 1
PR gate decision                     = FAIL
~~~

Đây chỉ là ví dụ nếu không có reopen/deduplication hoặc rulepack change. **Giảm tổng findings từ 48 xuống 47 không đủ để PASS**, vì một lỗi mới thuộc blocking class vẫn xuất hiện.

## 7. Coverage: điều kiện tiên quyết trước khi xét findings

### 7.1. “Scanner đã chạy” không đồng nghĩa “đã scan đủ”

Static analysis có thể bỏ qua code khi:

- Language/framework không được hỗ trợ hoặc plugin bị tắt.
- Build prerequisites fail nhưng wrapper vẫn return success.
- Một module monorepo không được đưa vào analysis target.
- Generated code hoặc thư mục `src` bị loại quá rộng.
- External dependencies/sources không được phân tích khi context cần.
- Rulepack không load hoặc thiếu config.
- Scanner timeout nhưng pipeline bắt lỗi bằng `continue-on-error`.
- Files bị skip vì size/parser error, thiếu permission hoặc encoding.
- CI phân tích PR head nhưng deployment dùng merge commit khác.
- Analyzer không thực hiện cross-file/dataflow mode cần thiết.

### 7.2. Coverage phải được định nghĩa theo mục tiêu

| Chiều coverage | Câu hỏi | Evidence |
|---|---|---|
| **Repository/module** | Những repos/modules nào thuộc scope? | Source inventory, build target manifest |
| **Language/framework** | Analyzer nào được dùng, có hỗ trợ? | Analyzer matrix, engine config |
| **File inclusion** | Những files/path nào scanned/excluded? | Inclusion/exclusion manifest, skip reasons |
| **Build completeness** | Dependency/compiled IR/binding có đủ không? | Build logs, compilation state |
| **Rule coverage** | Loại lỗi bắt buộc có rules enabled? | Rulepack ID/version, policy mapping |
| **Dataflow depth** | Cross-file/cross-module analysis phù hợp threat? | Engine mode, source–sink trace limits |
| **Source revision** | Report có khớp exact commit/merge result? | Commit/ref, scan ID |
| **Execution completeness** | Có errors/timeouts/partial results? | Exit/result status và scanner diagnostics |
| **Artifact relationship** | Build/deploy có dùng chính source đã scan? | Source provenance, artifact digest và CI run |

Không nên đưa một số phần trăm “SAST coverage” nếu chưa định nghĩa mẫu số **files, modules, analyzers, rules, languages hay threat classes**.

### 7.3. Monorepo và multi-language

Một monorepo chứa Java backend, TypeScript frontend, Terraform IaC và Python data job. Nếu chỉ chạy Java SAST mà dashboard báo “0 High”, không có nghĩa:

- Frontend XSS đã được kiểm tra.
- Terraform IAM/public exposure đã được đánh giá.
- Python deserialization/command injection đã được quét.
- Secrets trong history đã được xét.

Một gate tổng hợp có thể chia:

- Java SAST gate.
- TypeScript SAST gate.
- Python SAST gate.
- IaC security checks.
- Secrets scanning và SCA controls.

Nếu thiếu một **required sub-gate**, kết quả tổng hợp phải phản ánh BLOCKED/INDETERMINATE hoặc policy-defined exception, không bỏ qua im lặng.

### 7.4. Exclusions có trách nhiệm

Một đường file có thể được exclude vì:

- Vendor-generated code không do đội sở hữu và được quản trị theo risk riêng.
- Binary assets scanner không hỗ trợ.
- Test fixtures chứa mẫu tấn công có chủ đích.
- Third-party dependencies dùng SCA hoặc provenance controls khác.

Nhưng exclusions cần **path pattern, rationale, owner, expiry/review trigger và compensating coverage**. Không chấp nhận wildcard exclude toàn bộ `src/main` hoặc critical module chỉ để gate PASS.

### 7.5. Báo cáo scan completeness độc lập với findings

Ví dụ:

~~~text
Repository scope              : billing-service
Source commit                 : C-BILL-2026-042
Required modules              : 6
Analyzed modules              : 5
Missing module                : billing-admin
Scanner result                : PARTIAL
Security findings in 5 modules: 0 blocking
Quality gate                  : BLOCKED (scope incomplete)
~~~

**0 blockers trong 5/6 modules** không chứng minh 6/6 modules không có lỗi. Đường `billing-admin` có thể có quyền cao nhất nên càng không được bỏ qua.

## 8. Kiến trúc quality gate có thể kiểm chứng

### 8.1. Các thành phần chính

Một kiến trúc đơn giản gồm:

- **Source resolver:** Xác minh repo identity và exact commit/merge result.
- **Scan orchestrator:** Chạy đúng scanners/analyzers theo language và policy.
- **Result collector:** Nhận exit status, logs, findings, scan diagnostics, coverage.
- **Finding normalizer:** Chuyển các định dạng scanner sang schema nhất quán.
- **Triage/disposition service:** Liên kết finding với owner, review và exception.
- **Policy evaluator:** Ra quyết định theo rulepack/gate policy.
- **Gate enforcer:** Đưa quyết định tới branch protection, release manager hoặc deployment admission.
- **Evidence store:** Lưu kết quả, policy, source identity, signed/checksummed references và audit.
- **Finding tracker:** Điều phối remediation, SLA và retest.

### 8.2. Sơ đồ luồng quyết định

~~~mermaid
flowchart TD
    SRC["Approved repository + exact commit"] --> SC["Static analysis orchestrator"]
    R["Approved scanner/rulepack versions"] --> SC
    SC --> RES["Results + scan diagnostics + coverage"]
    RES --> N["Normalize and correlate findings"]
    N --> EVAL["Policy evaluator"]
    POL["Versioned gate policy + project risk tier"] --> EVAL
    TRI["Triage, baseline and exception records"] --> EVAL
    EVAL --> DEC{"Decision"}
    DEC -- "PASS" --> ENF["Protected merge / release / deploy"]
    DEC -- "FAIL" --> FIX["Fix finding, retest, or governed exception"]
    DEC -- "BLOCKED" --> INVEST["Repair scan/coverage/trust evidence"]
    FIX --> SC
    INVEST --> SC
    EVAL --> AUD[("Protected decision + evidence store")]
    ENF --> AUD
~~~

### 8.3. Bảo đảm không dùng kết quả “từ PR tự khai”

Trong CI, một PR chưa được duyệt có thể sửa scripts và file cấu hình. Nếu chính PR cũng điều khiển:

- Scanner binary/rulepack tải về.
- Bước “báo success” cho required check.
- Threshold và exclusion patterns.
- Script tính tổng findings và exit code.

Thì gate có thể bị vô hiệu hóa bằng cách thay script để luôn trả PASS. Cần kiến trúc để **gate policy/evaluator/trusted workflow** được bảo vệ độc lập với nguồn input chưa tin cậy, hoặc mọi thay đổi kiểm soát gate phải qua governance thực thi được.

### 8.4. Các boundary quan trọng

| Boundary | Trust risk | Control |
|---|---|---|
| External contributor → PR code | PR có thể chứa code độc hại muốn truy cập secrets | Untrusted runner, minimal token permissions |
| PR code/config → Scanner | PR có thể tắt rules hoặc gây parser crash | Trusted scanner/rules, diagnostics validation |
| Scanner process → Result collector | Report có thể bị giả, cũ hoặc bị sửa | Authenticated source, digest/attestation, revision binding |
| Results → Policy evaluator | Normalization sai hoặc bỏ finding | Schema validation và reconciliation |
| Policy author → Effective gate | Một người có thể tự hạ policy | Protected policy repo, independent review và audit |
| Gate result → Branch/release enforcement | CI check không bắt buộc, có bypass | Protected rules/admission và negative tests |
| Exception store → Gate evaluator | Exception giả, quá hạn hoặc quá scope | Signed/approved record, scope/expiry validation |
| Release artifact → Production | Artifact khác revision đã scan | Provenance/digest verification |

### 8.5. Không dùng CI output làm oracle duy nhất

Một PR có thể chứa script in `All security checks passed` nhưng:

- Scanner chưa được chạy.
- Một submodule không được scan.
- Job trả exit code 0 dù report lỗi.
- CI check đã bị đổi tên và branch rule không còn ràng buộc.

Reviewer phải kiểm tra **source of result** và **effective enforcement configuration**. Khi cần assurance cao, nên có **trusted evaluator** và audit evidence ngoài quyền của PR contributor.

## 9. Policy-as-code cho quality gate

### 9.1. Dữ liệu thiết kế

Một quality gate specification nên có:

| Trường | Ý nghĩa |
|---|---|
| **Gate ID/version** | Policy nào đang được dùng? |
| **Owner/approver** | Ai chịu trách nhiệm điều kiện và ngoại lệ? |
| **Stage** | PR, merge, release hoặc deployment? |
| **Target identity** | Repo, project, branch, revision, artifact nếu có |
| **Required scanners** | Công cụ/ruleset/analysis mode bắt buộc |
| **Required coverage** | Languages, modules, paths và exclusions được phép |
| **Blocking criteria** | Rule class, severity/risk, new/existing, triage và status |
| **Baseline/debt policy** | Cách xử lý findings trước ngày chốt |
| **Failure handling** | Scanner timeout, partial, unavailable, invalid result |
| **Exception policy** | Authority, scope, expiry, compensating controls và review |
| **Evidence contract** | Metadata, result, version, integrity và retention |
| **Reevaluation triggers** | New commit, rulepack update, risk/architecture changes |

### 9.2. YAML minh họa

Đây là **schema giáo dục**, không phải cấu hình có thể nạp trực tiếp vào một sản phẩm SAST/CI cụ thể. Những severity và names chỉ minh họa; khi triển khai phải ánh xạ với vendor/tool và approved risk policy.

~~~yaml
qualityGate:
  id: SAST-GATE-BILLING-01
  version: "2.1"
  lifecycleStatus: approved
  project: billing-platform
  ownerRoles:
    policyOwner: Application Security Owner
    releaseAuthority: Release Security Authority
    findingOwner: Service Engineering Owner
    exceptionApprover: Business Risk Owner
    evidenceReviewer: Security Assurance

  stagePolicies:
    pullRequest:
      sourceRevision: exact-pr-merge-result-if-supported
      blockNewCriticalAndHigh: true
      baselineReference: APPROVED-SAST-BASELINE-2026-11
      exceptionPolicyReference: SAST-EXCEPTION-POLICY
      requireTrustedCiCheck: true
    release:
      sourceRevision: exact-approved-release-commit
      checkExistingOverdueRisk: true
      blockUnresolvedRiskReference: APPROVED-RELEASE-RISK-RULES
      requireProvenanceLinkToArtifact: true

  requiredAnalysis:
    scannerPolicyReference: APPROVED-SAST-TOOLS-V4
    rulepackReference: APPROVED-SECURITY-RULEPACK-V9
    coverageCatalogReference: BILLING-MODULE-LANGUAGE-INVENTORY
    allowedExclusionsReference: SECURITY-APPROVED-EXCLUSION-LIST
    requireSuccessfulScannerExecution: true
    requireCompleteMandatoryModules: true
    requireSourceRevisionMatch: true
    verifyDiagnosticAndParseErrors: true

  riskEvaluation:
    ruleSeverityMappingReference: SECURITY-SEVERITY-MAPPING
    useFindingDisposition: true
    pendingTriageHandling: block-when-potentially-blocking
    falsePositiveNeedsEvidence: true
    baselineChangesNeedApproval: true
    exceptionNeedsOwnerScopeExpiry: true

  failures:
    scannerTimeout: BLOCKED
    scannerCrash: BLOCKED
    missingModule: BLOCKED
    unsupportedRequiredLanguage: BLOCKED
    invalidRulepack: BLOCKED
    staleOrWrongCommitResult: BLOCKED
    invalidExceptionEvidence: BLOCKED
    missingFindingResponse: BLOCKED
    zeroFindingsWithIncompleteScan: BLOCKED

  enforcement:
    prMergeProtectionReference: PROTECTED-REPOSITORY-RULES
    releaseGateReference: TRUSTED-RELEASE-POLICY
    deploymentBindingReference: VERIFIED-ARTIFACT-PROVENANCE
    bypassPolicyReference: EMERGENCY-SECURITY-GATE-EXCEPTION

  evidence:
    requiredFields:
      - repository-identity
      - exact-source-commit
      - policy-and-rulepack-version
      - scanner-engine-version
      - included-excluded-modules
      - scan-execution-status
      - findings-and-dispositions
      - gate-decision-and-reasons
      - reviewer-and-exceptions
      - report-and-artifact-references
    protectedStorageReference: SECURITY-ASSURANCE-EVIDENCE-STORE

  changeTriggers:
    - new-commit-to-target
    - rulepack-or-scanner-update
    - security-policy-change
    - newly-discovered-critical-issue
    - exception-expiration
    - build-or-deployment-source-change

  verification:
    testIds:
      - TEST-GATE-BLOCK-SQLI
      - TEST-GATE-PARTIAL-SCAN-BLOCKED
      - TEST-GATE-WRONG-REVISION
      - TEST-GATE-EXPIRED-EXCEPTION
      - TEST-GATE-UNTRUSTED-PR-BYPASS
    lastAssessmentReference: null
    status: NOT_ASSESSED
~~~

**Lưu ý:** `verification.status: NOT_ASSESSED` có nghĩa mẫu này chưa được chạy; `rulepackReference` chỉ là ID minh họa chứ không chứng minh rulepack thực có. Không nên dùng chính tài liệu mô tả policy làm bằng chứng rằng enforcement đã hoạt động.

### 9.3. Finding/report schema minh họa

~~~json
{
  "scan": {
    "scanId": "SCAN-BILLING-042",
    "repositoryId": "SCM-REPO-BILLING-01",
    "commitId": "COMMIT-BILLING-042",
    "scannerVersion": "APPROVED-SCANNER-VERSION",
    "rulepackVersion": "SEC-RULEPACK-9",
    "executionStatus": "COMPLETE",
    "requiredModules": 6,
    "analyzedModules": 6,
    "skippedModules": [],
    "reportReference": "EV-SCAN-042"
  },
  "findings": [
    {
      "findingId": "FIND-042-1",
      "ruleId": "SEC-SQL-INJECTION",
      "severity": "HIGH",
      "confidence": "HIGH",
      "changeClassification": "NEW",
      "triageStatus": "OPEN",
      "affectedComponent": "billing-api",
      "evidenceReference": "EV-FLOW-SOURCE-TO-SINK-042"
    }
  ],
  "gate": {
    "policyVersion": "SAST-GATE-BILLING-01:2.1",
    "result": "FAIL",
    "reasons": [
      "Unresolved NEW HIGH finding in required analysis scope"
    ],
    "exceptionReferences": []
  }
}
~~~

Không lưu trực tiếp source code nhạy cảm, token hoặc dữ liệu thật vào output nếu không cần. Trong hệ thống thực, cần kiểm tra **schema, source authentication, scan ID, result integrity và correlation** thay vì tin JSON do một job tùy ý đưa lên.

### 9.4. Pseudocode bộ đánh giá

Pseudocode dưới đây cố ý **không phụ thuộc vendor**. Nó minh họa thứ tự ưu tiên, không thay security policy đầy đủ:

~~~text
function evaluateGate(target, scanReport, policy, triageStore):
    if not isApprovedPolicy(policy):
        return BLOCKED("policy integrity or approval missing")

    if not matchesExactTarget(scanReport, target):
        return BLOCKED("wrong repository, commit or artifact")

    if not isTrustedScanProducer(scanReport):
        return BLOCKED("untrusted result provenance")

    if scanReport.executionStatus != COMPLETE:
        return BLOCKED("scan did not complete")

    if not requiredCoverageIsPresent(scanReport, policy):
        return BLOCKED("required analyzer or module missing")

    if not rulesAndScannerMatchPolicy(scanReport, policy):
        return BLOCKED("scanner/ruleset mismatch")

    blocking = []
    for finding in scanReport.findings:
        if not isFindingInRequiredScope(finding, policy):
            continue

        disposition = triageStore.lookup(finding)
        if isValidApprovedFalsePositive(disposition, finding):
            continue
        if isValidApprovedException(disposition, finding, target, policy):
            recordExceptionExposure(finding, disposition)
            continue

        if isBlockingUnderPolicy(finding, disposition, target, policy):
            blocking.append(finding)

    if length(blocking) > 0:
        return FAIL(blocking)

    if hasUnresolvedPotentiallyBlockingUntriagedFindings(scanReport, policy):
        return PENDING_TRIAGE("review required")

    if length(recordedExceptions()) > 0:
        return EXCEPTION_ACTIVE("exception route required", recordedExceptions())

    return PASS("all applicable checks satisfied")
~~~

**Điểm cẩn trọng:** Đường `continue` trong pseudocode chỉ hợp lệ nếu `isValidApprovedFalsePositive` và `isValidApprovedException` kiểm tra đủ **owner, authority, scope, justification, evidence, expiry và policy version**. Không được cho một trường do developer tự khai `falsePositive=true` miễn gate.

### 9.5. Aggregate gate logic

Một hệ thống có nhiều required sub-gates có thể dùng quy tắc:

- Bất kỳ **required FAIL** → aggregate FAIL.
- Không có FAIL nhưng có **BLOCKED/INDETERMINATE** → aggregate BLOCKED.
- Có findings cần triage → aggregate PENDING_TRIAGE theo policy.
- Có exception hợp lệ → aggregate decision phải hiển thị exception exposure và route.
- Chỉ PASS khi **mọi required checks** đạt và evidence đúng target.

Một optional informational scanner có thể fail mà không chặn release **nếu điều đó được policy định nghĩa rõ**; không được bí mật biến required scanner thành optional bằng cách sửa script.

## 10. Tích hợp vào CI/CD và chống bypass

### 10.1. Required check thật, không chỉ job tên đẹp

Một CI job chạy SAST có thể trả PASS nhưng branch protection:

- Không đánh dấu job là required.
- Chỉ yêu cầu một check khác cùng tên dễ giả mạo.
- Cho admins/service accounts bypass.
- Không buộc test trên latest commit/merge result.
- Cho direct push hoặc merge qua alternate path.
- Dùng release branch khác không có rules.

Kiểm tra kỹ thuật phải bao gồm **effective repository/branch rules, workflow identity, required check source, bypass list, merge queue behavior, release paths**, không chỉ đọc pipeline YAML.

### 10.2. Input chưa tin cậy trong PR pipeline

Một PR từ fork hoặc contributor có thể:

- Thay scanner config để loại rules.
- Sửa script tính exit code.
- Đổi build target làm mất một module.
- Chèn dữ liệu vào workflow command string.
- Làm scanner crash/timeout để kích hoạt soft-fail.
- Cài dependency/plugin nhằm đọc secrets nếu runner có quyền cao.
- Upload artifact giả mạo report hoặc cache để trusted job sử dụng.

Biện pháp:

1. Chạy PR code trên **untrusted execution context** không có production secrets/deploy/publish permissions.
2. Bảo vệ **trusted gate evaluator và ruleset** khỏi thay đổi tùy ý bởi PR author.
3. Giữ permissions của CI token theo least privilege.
4. Tách cache/artifact namespaces giữa untrusted và trusted jobs khi cần.
5. Xác minh **source revision và report provenance**, không tin success text tự in.
6. Các thay đổi workflow/policy/scanner config phải có **security owner review**.
7. So hiệu lực enforcement, không chỉ dựa vào thông báo UI.

### 10.3. Thay rulepack để giảm phát hiện

Ví dụ một PR thay:

~~~yaml
analysis:
  rulepack: security-rules-v9
  exclusions:
    - "src/**"
~~~

Nếu gate đọc exclusions từ chính PR và không áp security policy, nó có thể phân tích **0 file ứng dụng** và vẫn trả “0 findings”. Cần:

- Policy bảo vệ exclusions và approval.
- Coverage check: expected modules/paths không thể bằng 0 nếu inventory yêu cầu.
- Negative test thay exclusion pattern rồi xác minh gate BLOCKED.
- Tách **allowed exclusions** khỏi tùy chọn scanner do PR cung cấp.

### 10.4. Khi branch policy và release policy khác nhau

Một PR có thể đã qua SAST nhưng pipeline release có thể:

- Checkout một commit khác.
- Merge thêm code chưa qua scan.
- Build với dependency/config khác.
- Dùng tag mutable.
- Publish artifact mới nhưng admission nhận image cũ.

Cần **source→build→artifact→deployment linkage**, nhất là hệ thống chịu rủi ro cao. Một report gắn commit `C1` không chứng minh artifact `A2` build từ `C2` đạt gate.

### 10.5. Manual và emergency paths

Hỏi:

- Có thể merge bằng admin override?
- Có manual dispatch workflow chỉ nhận flag `skip_scan=true`?
- Có offline build hoặc direct registry push?
- Hotfix route có tắt required checks?
- Rollback có chọn artifact chưa kiểm chứng?

Nếu có đường khẩn cấp hợp lệ, cần **role, scope, reason, expiry, independent approval, compensating checks, audit và retrospective scan**. Không chấp nhận đường bỏ qua cố định nhưng ẩn sau tên “emergency”.

### 10.6. Gate thất bại vì công cụ không khả dụng

Khi scanner service mất kết nối:

1. Ghi **scan execution failure** độc lập với findings.
2. Retry có giới hạn, không vòng lặp vô hạn.
3. Nếu có scanner dự phòng, phải bảo đảm capability và policy equivalence được review.
4. Escalate owner, nêu impact tới merge/release.
5. Ngoại lệ khẩn cấp theo authority nếu business risk yêu cầu.
6. Chạy lại full required analysis ngay khi khôi phục và tạo findings.

Không lưu một **cached PASS** từ commit cũ để “chống outage” trừ khi policy có điều kiện cực kỳ rõ cho reuse kết quả và target/policy/rules hoàn toàn phù hợp.

## 11. Triage, false positive và finding disposition

### 11.1. Không coi mọi finding là bug đã được chứng minh

SAST suy luận dựa trên mã, mô hình dataflow và rule heuristics. Một cảnh báo có thể là:

- **True positive:** Có weakness và đường ảnh hưởng được xác định.
- **False positive:** Tool báo điểm yếu nhưng điều kiện cụ thể đã được chứng minh không áp dụng.
- **Potentially exploitable/needs analysis:** Dữ liệu hiện tại chưa đủ kết luận.
- **Duplicate:** Nhiều alerts mô tả cùng một root cause hoặc dòng dataflow.
- **Informational:** Signal hữu ích nhưng không thuộc security blocking policy.
- **Accepted risk:** Weakness có thật nhưng được phê duyệt giữ lại tạm thời theo governance.
- **Fixed:** Có remediation thực và retest trên source revision phù hợp.

Không được tự tạo nhãn “false positive” cho finding để đạt PASS khi không có **reasoning và bằng chứng kiểm tra được**.

### 11.2. Quy trình triage

Một triage reviewer nên:

1. Xác minh scanner/source/rule và path cụ thể.
2. Xác định **taint source, sink, validation/sanitization và trust boundary**.
3. Phân tích liệu attacker có thể điều khiển input và reachability.
4. Đối chiếu application architecture, framework behavior, security controls.
5. Đánh giá business impact/data classification và existing mitigations.
6. Đưa ra **disposition** với rationale và evidence (code review, unit/integration/negative test, config).
7. Gán owner, priority và deadline nếu true positive hoặc chưa kết luận.
8. Xác định gate decision và trigger retest nếu thay code/rule/assumptions.

### 11.3. Ví dụ dataflow SQL injection

SAST tìm thấy:

~~~java
// Ví dụ thiếu an toàn: chỉ dùng để học cách triage.
String order = request.getParameter("order");
String sql = "SELECT * FROM invoices ORDER BY " + order;
Statement stmt = connection.createStatement();
ResultSet rs = stmt.executeQuery(sql);
~~~

Ngay cả khi developer nói “frontend chỉ cho hai lựa chọn”, **client có thể giả request**. Input chưa đáng tin đi vào **SQL syntax**. Cần kiểm soát tại backend: với tên cột hoặc hướng sắp xếp, dùng **mapping allowlist tới identifiers cố định**; với dữ liệu values thì dùng prepared statements/bind parameters theo API tương ứng.

Ví dụ pattern có kiểm soát:

~~~java
// Mô hình minh họa: ánh xạ lựa chọn bên ngoài sang identifier cố định.
String requested = request.getParameter("order");
Map<String, String> allowedColumns = Map.of(
    "date", "created_at",
    "amount", "total_amount"
);
String column = allowedColumns.get(requested);
if (column == null) {
    throw new IllegalArgumentException("Unsupported sort field");
}
String sql = "SELECT * FROM invoices ORDER BY " + column;
// Quan hệ tenant và authorization vẫn cần được enforce riêng.
~~~

**Chú ý:** Mã minh họa chỉ xử lý lựa chọn column, chưa là implementation đầy đủ cho authentication, authorization, pagination, parameters hay DB access. Quality gate có thể kiểm tra pattern injection nhưng không nên tự suy đoạn này bảo vệ tenant isolation.

### 11.4. False-positive disposition cần gì?

Ví dụ scanner cảnh báo unsafe log call, nhưng reviewer cho rằng dữ liệu đã được redacted. Ghi:

- Finding ID, rule/version, source commit và code location.
- Vì sao luồng **không thể chứa dữ liệu nhạy cảm** theo nguồn dữ liệu được kiểm chứng.
- Reference tới redaction code/path và test trên test fixture.
- Reviewer và ngày quyết định.
- Scope của disposition; nếu sanitizer hoặc logging pipeline thay đổi, **invalidate** disposition.
- Nếu confidence còn thấp và impact cao, yêu cầu additional verification.

Không dùng câu “false positive – không sao” làm evidence.

### 11.5. Suppression nên có lý do, thời hạn và độ hẹp

Một inline suppression hoặc project exclusion có thể che các findings tương lai. Chính sách tốt có thể yêu cầu:

- Scope **rule + file/path + code/flow** càng hẹp càng tốt.
- Finding ID hoặc risk reference.
- Reason được giải thích, reviewer/approver.
- Expiry hoặc periodic re-review phù hợp.
- Không cho phép user tự sửa suppression và bypass independent review nếu policy cấm.
- Audit và metrics của suppressions.

Khác biệt:

**False positive suppression** nói finding không thực sự là lỗ hổng trong điều kiện được chứng minh. **Risk exception** thừa nhận lỗ hổng/rủi ro còn tồn tại nhưng cho phép tạm thời với owner và kiểm soát bù. Hai trạng thái này **không được đồng nhất**.

### 11.6. Duplicate không nên làm mất root cause

Nhiều alerts cùng dẫn tới một unsafe helper method. Có thể đóng duplicate để tránh ticket trùng, nhưng:

- Phải có canonical finding/root cause.
- Không được đóng toàn bộ khi helper chưa sửa.
- Khi helper sửa, cần retest các call paths quan trọng.
- Nếu một alert có attacker path/impact khác biệt, có thể không thực sự duplicate.

## 12. Exception, risk acceptance và debt governance

### 12.1. Điều kiện chấp nhận ngoại lệ

Một quality gate exception nên có:

| Trường | Ý nghĩa |
|---|---|
| **Exception ID** | Định danh duy nhất, không dùng “temporary” chung |
| **Finding/requirement IDs** | Vấn đề nào được miễn điều kiện chặn |
| **Affected scope** | Repo, component, branch/release, environment, resource hoặc data class |
| **Business rationale** | Vì sao cần đi tiếp dù control chưa đạt |
| **Risk assessment** | Likelihood/impact/conditions và sự phụ thuộc |
| **Compensating controls** | Mitigations, owner và bằng chứng hiệu lực |
| **Approver/authority** | Risk owner có thẩm quyền, tách khỏi người tự xin |
| **Valid from/expiry** | Thời hạn và tiêu chí hết hiệu lực |
| **Remediation owner/plan** | Hành động, milestones và retest |
| **Monitoring/trigger** | Khi risk thay đổi, finding bị exploited, rule được nâng hoặc exception hết hạn |
| **Audit reference** | Decision và evidence không thể tùy tiện sửa/xóa |

Một ngoại lệ có thể không được phép nếu xung đột **nghĩa vụ bắt buộc** hoặc authority không đủ. Review phải xác định điều này, không dùng một nút “override” để xóa constraint.

### 12.2. Ví dụ YAML ngoại lệ có kiểm soát

~~~yaml
securityGateException:
  id: EXC-SAST-BILLING-042
  status: ACTIVE
  findingIds:
    - FIND-LEGACY-217
  gatePolicyId: SAST-GATE-BILLING-01
  sourceScopeReference: APPROVED-LEGACY-COMMIT-BASELINE
  affectedComponent: billing-legacy-reports
  affectedEnvironments:
    - production
  riskReference: RISK-BILLING-LEGACY-042
  businessJustificationReference: DECISION-RELEASE-042
  mitigatingControls:
    - id: CTRL-LEGACY-REPORTS-ACCESS-RESTRICTION
      evidenceReference: EV-ACCESS-RESTRICTION-042
    - id: CTRL-LEGACY-REPORTS-DETECTION
      evidenceReference: EV-DETECTION-042
  ownerRoles:
    riskOwner: Billing Business Risk Owner
    remediationOwner: Billing Engineering Owner
    approver: Authorized Risk Authority
    reviewer: Application Security
  validFromReference: APPROVAL-START-042
  expirationReference: APPROVAL-EXPIRY-042
  remediationTrackingReference: FIX-LEGACY-217
  nextReviewTrigger:
    - exception-expiry
    - privileged-path-change
    - evidence-of-exploitation
    - source-or-rulepack-change
  auditReference: AUDIT-EXCEPTION-042
~~~

Mẫu trên chỉ mô tả **fields cần thiết**; không khẳng định một exception thực tồn tại. Khi runtime policy evaluation, phải xác minh **signature/authority/expiration/source scope và effective mitigations** từ nguồn không bị người xin ngoại lệ tự ý thay.

### 12.3. Không dùng exception để nuốt scanner failure

Một finding risk accepted khác với việc không biết scanner có chạy không.

- **Finding exception:** Rủi ro đã được hiểu và chủ thể có thẩm quyền quyết định trong scope.
- **Scan waiver:** Không thực hiện một kiểm tra; mức độ bất định có thể lớn hơn nhiều vì **không biết có findings gì**.

Scan waiver cần **đánh giá riêng**, thời hạn ngắn nhất phù hợp, compensating tests và kế hoạch chạy lại. Không áp một exception cho vulnerability đã biết để tự động miễn mọi scanner failures.

### 12.4. Expiry không được gia hạn âm thầm

Một exception hết hạn phải **không còn dùng được trong gate** nếu chưa qua quyết định mới. Việc gia hạn cần đánh giá lại:

- Tình hình threat, new exploits và asset exposure.
- Tiến độ remediation.
- Mitigation còn hoạt động không.
- Business impact và legal obligations.
- Risk owner và người phê duyệt còn đúng thẩm quyền không.

Một script tự động tăng expiry mà không có review sẽ biến exception thành bypass vĩnh viễn.

### 12.5. Debt burn-down song hành cùng new-code gate

Quản trị existing debt:

1. Chốt baseline được duyệt theo source/revision/ruleset.
2. Triage và ưu tiên theo risk, không chỉ scanner severity.
3. Tạo remediation backlog với owner, target, test plan.
4. Thiết lập release blockers cho **overdue high-risk** theo policy.
5. Đo debt fixed, reopened, new, aged và accepted risk riêng.
6. Chạy full scan khi rulepack đổi hoặc architecture mở attack path mới.
7. Đánh giá control effectiveness bằng evidence, không chỉ ticket closure.

### 12.6. Tình huống emergency release

Ví dụ: Production gặp sự cố cần hotfix nhưng SAST service outage.

Có thể làm:

- Dùng trusted local/alternative scanning nếu capability đủ và policy cho phép.
- Review manual targeted source/security changes, focused tests và rollback/monitoring.
- Bắt buộc approved emergency decision từ authority có thẩm quyền.
- Ghi **gate SKIPPED_AUTHORIZED/BLOCKED_OVERRIDDEN** theo policy, không đổi giả thành PASS.
- Lưu source commit, artifacts, người quyết định và time window.
- Khi scanner phục hồi, chạy SAST lại trên exact released source, xử lý findings và post-incident review.

Mục tiêu là **quản trị residual risk**, không giả vờ đã có bằng chứng mà thực tế không có.

## 13. Bảo đảm integrity của scan results và policy

### 13.1. Kết quả bị giả hoặc stale

Các kịch bản:

- PR ghi một file JSON “0 vulnerabilities” thay kết quả tool thật.
- Scanner job bị thay để echo `SUCCESS`.
- Report từ commit C1 bị dùng cho commit C2.
- Một service khác có quyền cập nhật CI check status.
- Cache cũ bị đọc như full scan mới.
- Rulepack hoặc exclusion config bị đổi mà không có approval.

Quality gate phải xác minh **provenance của scan**, người/process sinh report, đúng target và toàn vẹn.

### 13.2. Evidence trust chain

~~~mermaid
flowchart LR
  S["Approved source identity + commit"] --> J["Trusted CI runner + SAST job"]
  P["Approved scanner + rulepack/policy"] --> J
  J --> R["Analysis report + diagnostics + coverage"]
  R --> V["Trusted policy evaluator"]
  X["Approved triage + exceptions"] --> V
  V --> D["Versioned gate decision"]
  D --> E["Protected branch / release / deploy"]
  D --> A[("Protected audit + evidence")]
  R --> A
  E --> A
~~~

Khi threat model đòi hỏi, có thể dùng ký/attestation đối với report và decision. **Chữ ký chỉ có ý nghĩa khi verifier kiểm tra đúng signer, trust root, subject, source commit và policy context**. Một signature hợp lệ bởi danh tính không được phép vẫn không làm report đáng tin.

### 13.3. Quyền sửa policy và evidence

Hỏi:

- Ai có thể disable required scanner?
- Ai có thể hạ severity mapping hoặc thay whitelist?
- Ai có thể phát hành CI check status?
- Ai có thể ghi đè result artifact?
- Ai có thể xóa/đổi findings/dispositions?
- Ai phê duyệt exception?
- Ai có thể sửa audit history?

Thiết kế **least privilege và separation of duties** phù hợp criticality. Nếu developer có thể vừa tạo risky change, vừa thay policy, vừa tự approve exception và deploy, gate dễ bị bypass bằng quyền quản trị hơn là tấn công engine.

### 13.4. Phạm vi kiểm soát SAST tool

Scanner cũng là **phần mềm trong supply chain**:

- Bản scanner/plugin phải từ nguồn được phê duyệt và version được quản lý.
- Rulepack updates phải được review và test.
- Scanner chạy mã không đáng tin cần sandbox/permissions phù hợp.
- SAST có thể đọc toàn bộ source chứa bí mật kinh doanh; giới hạn data exfiltration và third-party SaaS access.
- Dữ liệu report có snippet nhạy cảm cần access controls và retention.
- Scanner token/license keys không được lộ trong PR logs.

Khi phân tích repo PR từ nguồn không đáng tin, đừng giao CI token có quyền repository write hoặc production deploy chỉ để scanner đọc source.

### 13.5. Gate còn hoạt động khi pipeline thay đổi?

Một lần cấu hình đúng không bảo đảm mãi mãi:

- CI provider đổi default token permissions.
- Monorepo chuyển module/path.
- Branch protection bị thay tên required check.
- Project đổi language/framework.
- Scanner engine nâng cấp và mất analyzer.
- Một release workflow mới không gọi gate.

Cần **configuration drift assessment**, change-triggered review và **negative enforcement tests** phù hợp, không chỉ chạy scanner định kỳ.

## 14. Thiết kế kiểm thử cho chính quality gate

### 14.1. Gate là một security control cần được test

Chạy SAST trên ứng dụng là kiểm thử **mã ứng dụng**. Nhưng gate cũng là **một control riêng**. Cần test rằng:

- Policy evaluator xác định đúng trạng thái khi có findings.
- CI enforcement chặn merge/release khi FAIL/BLOCKED.
- Scanner failure không bị đổi thành PASS.
- Exceptions có hiệu lực đúng phạm vi, không vượt scope/expiry.
- Report cũ hoặc sai commit không thể tái sử dụng.
- Thay config/required check không vô hiệu hóa gate.
- Bằng chứng phản ánh đúng scanner output.

Không thể dùng chính sự kiện “gate báo PASS” làm bằng chứng độc lập rằng **gate logic đúng**. Cần bộ test riêng cho policy/evaluator/enforcement.

### 14.2. Test matrix

| Test ID | Input/sự kiện | Expected gate outcome | Verification |
|---|---|---|---|
| **GATE-001** | Required scan hoàn tất, không blocking findings, đủ scope | PASS | Report/coverage/policy match |
| **GATE-002** | New confirmed blocking injection | FAIL | Finding→policy mapping và merge bị chặn |
| **GATE-003** | Scanner timeout | BLOCKED | Pipeline không ghi PASS hoặc deploy |
| **GATE-004** | Module bắt buộc bị skip | BLOCKED | Expected modules vs analyzed modules |
| **GATE-005** | Source revision mismatch | BLOCKED | Commit equality check |
| **GATE-006** | Rulepack sai hoặc thiếu approved version | BLOCKED | Policy integrity/version check |
| **GATE-007** | Finding được gắn false positive nhưng không có evidence/approval | FAIL/PENDING | Disposition validator |
| **GATE-008** | Exception hết hạn hoặc áp sai project/release | FAIL/PENDING | Authority/expiry/scope check |
| **GATE-009** | Exception hợp lệ cho finding đúng scope | EXCEPTION_ACTIVE | Exceptional approval path và audit |
| **GATE-010** | Baseline tự sửa để che lỗi mới | FAIL/BLOCKED | Baseline approval/integrity |
| **GATE-011** | PR đổi exclusions loại toàn bộ source | BLOCKED | Coverage và approved exclusion policy |
| **GATE-012** | CI job xanh nhưng required branch check không enforce | FAIL control assessment | Negative merge attempt có phép |
| **GATE-013** | PR C2 được merge bằng report C1 | BLOCKED | Exact revision binding |
| **GATE-014** | Finding fixed, tool rerun trên C2 | PASS nếu mọi điều kiện khác đạt | Regression scanning + actual source |
| **GATE-015** | Legacy blocking finding quá hạn release SLA | FAIL nếu policy yêu cầu | Debt register và expiry |
| **GATE-016** | New analyzer rule phát hiện existing issue | Risk reassessment theo policy | Rule-change impact và owner |
| **GATE-017** | Optional informational scanner lỗi | Outcome theo chính sách đã duyệt | Optional vs required rõ và audit |
| **GATE-018** | Untrusted PR job cố dùng privileged publisher token | Denied | CI permissions và sandbox |
| **GATE-019** | Manual release path không chạy gate | Rejected hoặc governed exception | Release workflow/integrity gate |
| **GATE-020** | Artifact digest không liên kết scanned commit | BLOCKED release/admission | Provenance/subject verification |

**Lưu ý:** “FAIL control assessment” ở GATE-012 là kết luận kiểm tra **enforcement design/implementation**, khác với một FAIL do mã ứng dụng có vulnerability. Nếu required check chưa được cấu hình, CI job có thể PASS nhưng *control* thực chất không vận hành đúng.

### 14.3. Phải quan sát actual effect

Thử nghiệm “scanner trả code 1” chưa chứng minh merge bị chặn. Cần:

1. Dùng test repository/branch hoặc sandbox được phê duyệt.
2. Sinh một commit có fixture finding rõ, ví dụ `TEST_RULE_BLOCKING`.
3. Chạy scanner/policy evaluator với policy version cố định.
4. Ghi gate decision và check state.
5. **Thử merge qua đường được phép kiểm thử** và quan sát enforcement reject.
6. Kiểm tra branch ref/production artifact **không bị thay đổi** trái policy.
7. Lưu test run, actors/permissions, timestamps và audit.

Không thực hiện thao tác push/merge trái phép vào repo thực; làm bằng **sandbox có quyền** hoặc kiểm tra cấu hình/negative tests qua interface được phê duyệt.

### 14.4. Test phát hiện false negative của gate

Một **known-vulnerable synthetic fixture** giúp kiểm tra analyzer/rulepack không bị vô hiệu hóa. Ví dụ:

- Input request không tin cậy đưa vào command execution.
- SQL string concatenation thiếu parameterization.
- Hard-coded fake test secret có pattern kiểm soát.
- Missing output encoding khi rule/tool hỗ trợ.

Những fixtures này phải **không chứa secrets thật và không được deploy production**. Việc scanner không phát hiện một fixture cũng chưa chứng minh mọi vulnerabilities khác sẽ bị bỏ sót; nó cho thấy **detection capability hoặc configuration** có thể đang hỏng và cần điều tra.

### 14.5. Positive và negative test theo policy

Chỉ có negative test để chứng minh chặn có thể tạo một gate **luôn FAIL**, phá developer productivity. Cần thử:

- Safe change có required coverage → PASS.
- High-risk blocking finding → FAIL.
- False positive đã được review đúng → xử lý theo policy mà không hạ standards.
- Exception đúng scope → exceptional path hoạt động và có audit.
- Scanner lỗi → BLOCKED.
- Fix thật trên revision mới → PASS sau rerun.

Quality gate tốt vừa **ngăn sai lệch** vừa **cho phép những thay đổi hợp lệ** theo chính sách.

## 15. Gherkin: quality gate verification

Các kịch bản sau có thể dùng để thiết kế bộ kiểm thử policy và CI; **Gherkin không phải bằng chứng đã chạy**.

~~~gherkin
Feature: Evidence-based static analysis quality gate

  Background:
    Given repository billing-service has an approved SAST gate policy
    And the required scanner and rulepack versions are documented
    And protected branches enforce the trusted gate check

  Scenario: Complete clean analysis allows a valid proposed change
    Given a PR has an exact source revision C1
    And all mandatory analyzers completed for C1
    And all required modules are covered
    And no unresolved blocking findings are present
    When the trusted policy evaluator runs
    Then the gate decision must be PASS for C1
    And the decision must include policy, scanner and coverage evidence

  Scenario: A new high-risk injection finding blocks merge
    Given a required scan on C2 finds a new blocking SQL injection weakness
    And no valid exception or approved false-positive disposition applies
    When the PR gate evaluates C2
    Then the gate decision must be FAIL
    And a normal protected-branch merge must not succeed
    And the finding and reasons must be traceable

  Scenario: Scanner timeout is not zero findings
    Given a required analyzer times out before finishing
    When the gate collector receives a partial result
    Then the decision must be BLOCKED or INDETERMINATE
    And no zero-finding PASS may be issued
    And a controlled retry or escalation must be recorded

  Scenario: Missing mandatory module blocks the gate
    Given the expected scan inventory contains six modules
    And only five modules were analyzed successfully
    When the policy evaluator checks coverage
    Then the aggregate gate must not be PASS
    And the missing module must appear in diagnostic evidence

  Scenario: A report for an older commit cannot authorize a new commit
    Given scan report R1 was produced for commit C1
    And PR head or merge-result revision is now C2
    When the gate is asked to approve C2 using R1
    Then the result must be BLOCKED as stale or mismatched
    And C2 must require verification under the effective policy

  Scenario: A new source exclusion cannot silently bypass required coverage
    Given the approved scope requires scanning application source paths
    And a PR changes the scan configuration to exclude those paths
    When the trusted coverage evaluator runs
    Then the exclusion must not silently satisfy the gate
    And approval or restoration of required coverage must be requested

  Scenario: An invalid false-positive claim cannot erase a blocker
    Given finding F1 is covered by the blocking policy
    And a developer marks F1 false positive without approved evidence
    When the gate evaluates finding dispositions
    Then F1 must remain unresolved for gate purposes
    And a false-positive bypass must not be granted

  Scenario: Expired risk acceptance cannot authorize release
    Given finding F2 is within a release blocking rule
    And exception E2 expired before the target release
    When the release gate evaluates F2
    Then the exception must be rejected
    And the release must follow the normal failure or new approval workflow

  Scenario: A valid narrowly scoped exception is visible and auditable
    Given finding F3 has an exception approved by an authorized risk owner
    And the exception matches this exact target and is still valid
    When the gate evaluates the release
    Then the result must identify an EXCEPTION_ACTIVE route
    And the finding must not be represented as remediated
    And the decision and expiry must be recorded

  Scenario: Self-modified rulepack is not trusted by the gate
    Given required rulepack V9 has been approved for protected release
    And an untrusted PR supplies a weaker rulepack V0
    When the trusted gate evaluator resolves its effective rules
    Then V0 must not replace V9 without authorized policy change
    And a mismatched or invalid rulepack must block verification

  Scenario: New-code PASS does not bypass existing overdue critical debt
    Given the PR gate found no new blocking issues in C4
    And a previously accepted critical finding exceeded the release deadline
    When the separate release gate evaluates C4
    Then release must follow the existing-debt blocking policy
    And PR PASS must not be treated as release approval

  Scenario: A fixed issue requires rescanning the actual revision
    Given finding F4 blocked a PR at commit C5
    And the developer submitted a fix at commit C6
    When the approved analyzer scans the correct C6 revision
    Then the decision must use C6 evidence rather than C5 status
    And it may PASS only if all required criteria are satisfied

  Scenario: An untrusted pull request cannot forge the required gate
    Given an external contributor controls PR contents but not gate authority
    When the contributor changes PR scripts to print a fake success message
    Then trusted policy evaluation and required branch enforcement must not change
    And the fake message must not authorize merge

  Scenario: Replacing a report artifact cannot forge the source binding
    Given a verified report is bound to repository R and commit C7
    When a different untrusted report claims success for C8
    Then its provenance or revision mismatch must be detected
    And the gate must not authorize C8 using that report

  Scenario: Emergency release records a waiver and triggers reassessment
    Given the scanner is unavailable during an authorized emergency
    And the designated risk authority approves a bounded scan waiver
    When the emergency release proceeds through its approved path
    Then no normal SAST PASS must be claimed
    And the waiver, mitigations and released revision must be recorded
    And follow-up SAST verification must be tracked

  Scenario: Wrong build artifact cannot reuse an approved SAST report
    Given SAST report R9 applies to source commit C9
    And the artifact was built from a different unapproved commit C10
    When the release or deployment gate checks provenance
    Then the mismatch must reject or block the artifact
    And the approved source-artifact chain must be preserved

  Scenario: Unscanned unsupported language does not look like clean code
    Given project inventory includes a required Python module
    And the configured SAST engine has no working Python analyzer
    When the quality gate reviews analysis completeness
    Then the Python module must be reported as unsupported or missing
    And the overall required analysis must not silently PASS

  Scenario: Remediated legacy finding is reflected in the next baseline assessment
    Given a legacy finding F5 has a remediation ticket
    And the source fix is merged through approved controls
    When the full scan evaluates the approved revision
    Then F5 must be marked fixed only with matching verification evidence
    And the historical debt register must preserve the closure trace
~~~

### 15.1. Kịch bản vận hành cần bổ sung

Không phải tình huống nào cũng thể hiện tốt chỉ bằng Given–When–Then:

- Thay đổi IAM của CI token.
- Đổi rulepack lớn và rebaseline.
- Thêm ngôn ngữ/framework mới.
- Kiểm tra audit store integrity và retention.
- Đánh giá exception approvals độc lập.
- Stress test scanner timeouts/queue saturation.
- Recovery drill khi tool provider unavailable.

Các trường hợp này có thể dùng **configuration inspection, security review, chaos/fault tests, audit sampling và tabletop exercises**, kèm actual evidence.

## 16. Quality gate và các phép kiểm soát liên quan

### 16.1. SAST không bao phủ mọi security requirement

| Security property | SAST hỗ trợ | Cần bổ sung |
|---|---|---|
| Injection vào query/command | Dataflow/rule detection ở nhiều ngôn ngữ | Negative integration tests, data validation review |
| Authentication/authorization correctness | Một số patterns/rules | Object-level authz/tenant tests, threat modeling |
| Cryptography misuse | Patterns của API/algorithms/config | Approved crypto baseline, key management, runtime config |
| Secrets exposure trong code | Một số scanner hỗ trợ; chuyên dụng tốt hơn với patterns riêng | Secret management, revocation/rotation, history scanning |
| Dependency CVEs | Thường là SCA, không phải năng lực cốt lõi của SAST | SBOM, provenance, reachability/risk assessment |
| IaC misconfiguration | IaC static checks riêng | Cloud effective config, drift detection |
| Business logic/SoD | Có thể phát hiện một số coding patterns | Manual design review, domain-specific tests |
| Security monitoring/incident response | SAST gần như không chứng minh runtime effectiveness | SIEM/EDR detection exercises và operating evidence |
| Supply-chain provenance | Không giải bằng source SAST đơn lẻ | Build attestations, artifact signature/digest/admission |

SAST gate là **một phần** của chương trình assurance. Không “pass SAST” rồi bỏ qua kiểm thử nghiệp vụ, tenant isolation hoặc release provenance.

### 16.2. Gate composition theo rủi ro

Một **security release gate** rộng có thể yêu cầu:

- SAST có đủ scope và không có unresolved blocking findings.
- SCA có triage cho affected/reachable dependencies.
- Secrets scan và credential response cho secrets thật.
- IaC checks đối chiếu security baseline.
- Unit/integration/negative tests cho security requirements.
- Change approval và policy ownership.
- Build provenance/artifact verification.
- Operational readiness và exception register.

Đừng ép mọi dữ liệu vào một scalar score nếu mất ý nghĩa. **Aggregate decision** nên giữ được reasons của từng sub-gate, đặc biệt khi một sub-gate BLOCKED còn một sub-gate FAIL.

### 16.3. DAST và manual pentest vẫn có vai trò

Một flaw liên quan:

- BOLA/IDOR giữa tenants.
- Broken workflow approvals.
- Session fixation hoặc stale privilege.
- Service mesh authorization bypass.
- Contextual SSRF chain.

có thể không được SAST phát hiện đủ. Vì vậy test plans nên xuất phát từ **risk/requirements**, không chỉ từ khả năng rulepack hiện có. Findings ngoài SAST có thể đi vào **release risk decision** ngay cả khi SAST gate PASS.

## 17. Quality gate evidence, traceability và audit

### 17.1. Chuỗi claim–requirement–control–test–evidence

Một **security assurance program** cần truy vết được:

~~~mermaid
flowchart TD
    R["Risk / security objective"] --> Q["Requirement + gate condition"]
    Q --> C["SAST rulepack + enforcement control"]
    C --> T["Scanner and gate verification tests"]
    T --> EV["Scan results + execution + policy evidence"]
    EV --> D["Gate decision for exact commit/release"]
    D --> A["Assurance claim with scope + limitations"]
    D --> F["Finding / exception / remediation"]
    F --> T
    A --> N["Monitor, rule changes, revalidation"]
    N --> R
~~~

Đường mũi tên là quan hệ **cần có**, không phải bằng chứng các bước đã hoàn tất.

### 17.2. Evidence package cần gì?

| Nhóm evidence | Ví dụ | Câu hỏi |
|---|---|---|
| **Source identity** | Repo ID, branch, commit SHA, PR ID | Đúng source nào được scan? |
| **Scan execution** | Job ID, start/end, exit status, diagnostics | Tool có chạy và hoàn tất? |
| **Rules/engines** | Engine version, rulepack ID/hash, approved baseline | Phân tích dựa trên tiêu chí nào? |
| **Coverage** | Required/analyzed modules, language matrix, exclusions | Phần nào chưa được scan? |
| **Findings** | Rule ID, severity, confidence, flow, fingerprint, status | Lỗi nào xuất hiện và được hiểu thế nào? |
| **Triage/exception** | Reviewer, decision, rationale, risk owner, expiry | Ai cho phép đóng/đi tiếp và vì sao? |
| **Policy evaluation** | Gate ID/version, decision reason, input references | Rule nào quyết định PASS/FAIL/BLOCKED? |
| **Enforcement** | Protected branch checks, release admission, audit | Decision có thực sự chặn/cho phép bước tiếp theo? |
| **Artifact binding** | Build ID, source revision, artifact digest | Artifact nào dùng chính source đó? |
| **Operations** | Drift, policy changes, recurring scans, findings aging | Gate còn hoạt động sau release không? |
| **Review limitations** | Exclusions, unsupported languages, scope/time window | Không thể kết luận gì? |

### 17.3. Evidence freshness

Kết quả có thể hết giá trị khi:

- Code/commit thay đổi.
- Rulepack hoặc scanner engine thay.
- Security objective/risk appetite và severity mapping đổi.
- Một module/language mới xuất hiện.
- Branch protection hoặc required check bị thay.
- Scanner phát hiện thêm lỗ hổng trong code cũ.
- Một risk exception hết hạn.
- Build/deploy dùng source khác.

Một report từ quý trước có thể hữu ích cho **history**, nhưng không thể mặc định thay cho **current required analysis**. Cần chính sách kết luận evidence còn phù hợp dựa trên **revision and effective policy**, không chỉ ngày tạo.

### 17.4. Mẫu quality gate verification record

~~~yaml
qualityGateVerification:
  recordId: VERIFY-SAST-BILLING-042
  gateId: SAST-GATE-BILLING-01
  gatePolicyVersion: "2.1"
  targetStage: pull-request
  target:
    repositoryId: SCM-REPO-BILLING-01
    commitReference: COMMIT-BILLING-C42
    pullRequestReference: PR-BILLING-42
    branchPolicyReference: PROTECTED-MAIN-RULES-V7

  execution:
    scannerJobReference: CI-SAST-JOB-042
    scannerIdentityReference: TRUSTED-SAST-RUNNER
    engineVersionReference: SAST-ENGINE-APPROVED
    rulepackVersionReference: SECURITY-RULEPACK-V9
    resultIntegrityReference: SCAN-REPORT-DIGEST-042
    status: COMPLETE
    environmentReference: CI-SECURITY-ENV-042

  coverage:
    expectedInventoryReference: MODULES-LANGUAGES-042
    requiredModules: 6
    analyzedModules: 6
    excludedPathsReference: APPROVED-EXCLUSIONS-V3
    skippedRequiredPaths: []

  findings:
    - id: FIND-BILLING-SEC-042
      weaknessClass: SQL_INJECTION
      status: OPEN
      relativeToBaseline: NEW
      evidenceReference: DATAFLOW-TRACE-042

  triage:
    reviewerRole: Application Security
    dispositionReference: TRIAGE-FIND-042
    exceptions: []

  decision:
    result: FAIL
    reasonReferences:
      - BLOCKING-NEW-SECURITY-FINDING
    enforcedAtReference: REQUIRED-CHECK-042
    mergeAttemptReference: NEGATIVE-MERGE-042
    reviewOwnerRole: Security Assurance Reviewer
    limitations:
      - Runtime exploitability not independently tested in this record

  retention:
    evidenceStoreReference: ASSURANCE-REPORTS-042
    accessPolicyReference: SECURITY-EVIDENCE-ACCESS-V2
~~~

Trong ví dụ này kết quả **FAIL** dù scan chạy thành công và đủ scope. Đây là cách phân biệt *scanner success* với *security gate approval*. Các references là giả định cho mục đích học tập, **không phải evidence thật**.

### 17.5. Bảo vệ evidence

SAST report có thể chứa:

- Source paths và code snippets độc quyền.
- Dataflow nhạy cảm, file names và system internals.
- Dấu vết secrets hoặc test credentials.
- Tenant IDs hoặc hardcoded sample values.

Cần access controls, retention, masking khi thích hợp và integrity protection. Không đăng toàn bộ report công khai chỉ vì CI artifact có thể share link. Audit log của người sửa policy/exception phải được bảo vệ khỏi chính người thực hiện hành động nếu threat model yêu cầu.

### 17.6. Audit trail của một quyết định merge

Ví dụ chuỗi:

~~~text
Repo ID: SCM-BILLING-01
Pull request: PR-247
Source/merge result commit: C-BILLING-247
Scanner job: SAST-RUN-247 (COMPLETE)
Rulepack: SECURITY-RULEPACK-V9
Coverage: Java 4/4 modules, TypeScript 2/2 modules
Baseline: SAST-BASELINE-2026-11
Blocking findings: 0
Pending triage: 0
Exceptions: none
Gate policy: SAST-GATE-BILLING-01 v2.1
Decision: PASS for C-BILLING-247
Required check: enforced on protected branch
Release build: BUILD-BILLING-247
Artifact digest: DIGEST-BILLING-247
Independent review: EV-GATE-REVIEW-247
~~~

Nếu từng bước trên chỉ được **log bởi một script mà PR có quyền sửa**, bằng chứng có thể yếu. Hãy xác minh provenance/authority của reporter và enforcement.

## 18. Metrics: đo effectiveness thay vì đếm lần chạy scanner

### 18.1. Phân biệt các mẫu số

| Metric | Tử số | Mẫu số | Giới hạn |
|---|---|---|---|
| **Required gate execution coverage** | Target revisions có required scan được chạy | Target revisions thuộc scope | Có chạy chưa chắc complete |
| **Analysis completeness** | Required modules/languages được phân tích thành công | Expected required modules/languages | Đếm module chưa đo mọi taint flow |
| **Gate decision coverage** | Target revisions có decision đáng tin | Target revisions phải được gate | PASS/FAIL/BLOCKED cần tách |
| **First-pass PASS rate** | Gate đạt ngay lần đầu theo policy | Evaluated revisions | Có thể bị thao túng bằng giảm rules |
| **Blocking findings introduced** | Findings mới thuộc blocking class | PRs/releases hoặc lines theo định nghĩa | So sánh không chuẩn có thể sai lệch |
| **True-positive rate in reviewed sample** | Confirmed relevant findings | Findings được triage trong mẫu | Sampling/selection bias |
| **False-positive burden** | Findings confirmed false-positive | Findings được triage | Không thể suy false-negative rate |
| **Open high-risk debt aging** | Findings quá hạn theo policy | Applicable existing debt population | Severity/risk và owner quan trọng |
| **Exception exposure** | Exceptions active by risk tier | Policy-relevant findings hoặc projects | Exception không phải PASS |
| **Policy drift detection** | Unauthorized gate config changes được phát hiện | Known change events trong kỳ | Không thấy change có thể do thiếu telemetry |
| **Gate bypass attempts** | Bypass events được ghi và xử lý | Attempt/event population theo threat model | Không có event chưa chắc không có bypass |
| **Evidence freshness** | Decisions khớp current source/policy | Decisions được sử dụng để phê duyệt | Evidence stale có thể invalid |

### 18.2. Ví dụ về kết quả gate

Giả sử một tuần có **50 PRs thuộc scope bắt buộc gate**:

- 34 PRs có **PASS** với scan hoàn tất và evidence đủ.
- 8 PRs **FAIL** do blocking findings.
- 4 PRs **BLOCKED** do scanner crash hoặc coverage thiếu.
- 2 PRs **PENDING_TRIAGE**.
- 2 PRs có **EXCEPTION_ACTIVE** được approve cho scope cụ thể.

Tổng: 34 + 8 + 4 + 2 + 2 = 50.

~~~text
Scoped PRs                                 = 50
Verified normal PASS                      = 34
Gate normal PASS rate                     = 34 / 50 = 68%
Blocking security findings (FAIL)         = 8 PRs
Analysis unavailable/incomplete (BLOCKED) = 4 PRs
Triage pending                            = 2 PRs
Exception route (not normal PASS)         = 2 PRs
~~~

**Không báo 36/50 PASS bằng cách cộng 2 exceptions**, cũng không loại 4 BLOCKED khỏi mẫu số để làm số liệu tốt hơn. Nếu 50 PR không bao gồm các PR đi đường admin bypass, mẫu số vẫn **thiếu**.

### 18.3. Scanner false negative là điều khó đo

Nếu tool báo 0 findings nhưng 1 security review phát hiện lỗ hổng, ta biết có một **missed case** trong ngữ cảnh đó. Không thể tính chính xác **false-negative rate cho toàn bộ codebase** nếu chưa biết tổng số vulnerabilities thực sự.

Có thể đánh giá một cách có giới hạn:

- Known-vulnerable synthetic fixtures.
- Manually reviewed high-risk samples.
- Comparison với independent tools hoặc targeted test.
- Post-incident analysis những flaws scanner đã không thấy.
- Rule coverage mapping tới CWE/threats cần bảo vệ.

Đừng tạo số “99,9% SAST accuracy” chỉ vì scanner ít cảnh báo; ít alerts cũng có thể là scan thiếu.

### 18.4. Không chạy theo tỷ lệ xanh

Nếu một đội bị ép “100% gate PASS”, họ có thể:

- Tắt rule gây nhiều finding.
- Tăng exclusions.
- Đổi severity mapping.
- Cho PR nhỏ nhưng nhiều bước làm tránh scan cross-file.
- Áp exception rộng không hết hạn.
- Chỉ scan code dễ qua.

Metrics cần được **kiểm toán kèm policy/coverage stability, exceptions và bypass evidence**, không dùng “% green” đơn độc để chấm điểm hiệu quả security.

### 18.5. Time-to-remediate và aging

Nên phân biệt:

- **Time to triage:** Từ finding xuất hiện tới disposition có evidence.
- **Time to fix:** Từ xác nhận tới code fix.
- **Time to verified remediation:** Từ finding tới retest PASS trên revision thực.
- **Exception age:** Thời gian risk chưa xử lý.
- **Reopened finding rate:** Findings trở lại sau khi từng được đóng.

Một ticket “Done” không đồng nghĩa **verified remediation** nếu scanner chưa chạy lại trên commit/branch/artifact đúng.

## 19. Continuous assurance: gate không kết thúc khi merge

### 19.1. Reassessment triggers

Chạy hoặc xem xét lại khi:

- Source commit mới, release branch được tạo hoặc build target đổi.
- Scanner/rulepack nâng cấp; phát hiện class vulnerability mới.
- Security policy, severity mapping, baseline hoặc exception thay đổi.
- New language/module/framework xuất hiện.
- Một vulnerability có khai thác được ghi nhận hoặc incident liên quan.
- Dependency/build architecture đổi, SAST mất cross-file context.
- CI/branch rules/check names hoặc actor permissions thay đổi.
- Artifact deployment/registry thay, nguồn build không trùng scan.
- Finding được đóng, reopen hoặc overdue.
- Một dịch vụ critical thay data classification hoặc attack surface.

### 19.2. Control monitoring

Vận hành có thể theo dõi:

- Scanner success, partial/error rate, runtime latency, tool availability.
- Expected vs observed source/modules/languages.
- Rulepack/version drift và exclusions tăng đột biến.
- CI check bypass hoặc unapproved workflow changes.
- Finding aging, reopened, overdue, false-positive review.
- Exception expiry và unusual approval volume.
- Release/artifact mismatch với gate result.

**Mục tiêu monitoring là phát hiện control hỏng**, không chỉ phát hiện bugs trong source.

### 19.3. Trách nhiệm sau release

Nếu rulepack mới phát hiện High finding trong release đang chạy:

1. Xác minh scope, validity và business risk.
2. Giao remediation owner, triage và deadline theo risk.
3. Xét mitigation/hotfix và release gate.
4. Nếu evidence exploitation, phối hợp incident response.
5. Patch và verify trên revision mới.
6. Giữ lịch sử finding và evidence closure.

Không đổi lịch sử “release gate PASS thời điểm trước” thành “không bao giờ có lỗ hổng”. PASS trước đó là **kết luận có điều kiện dựa vào rulepack/scope/evidence lúc đó**.

### 19.4. Quy tắc chống tái phát

Khi một lỗ hổng lọt qua gate:

- Xác định detection gap: rule thiếu, language unsupported, excluded path hay context?
- Xác định governance gap: bypass, false-positive label, exception sai authority?
- Bổ sung test fixture/regression rule hoặc targeted code test.
- Review scanner upgrade/analysis mode.
- Retest gate và evidence chain.
- Theo dõi metrics để biết control improved chứ không chỉ đóng incident.

## 20. Case study: PR “xanh” nhưng quality gate bị bỏ qua

### 20.1. Bối cảnh

Nền tảng giả định **BillingHub** có:

- Monorepo: Java billing API, TypeScript admin UI, Python reconciliation worker.
- CI chạy SAST trên pull requests và gửi status về SCM provider.
- Default branch được cấu hình một required check tên `build-success`.
- Một dashboard hiển thị SAST warnings và code quality.
- Release pipeline build container images và deploy từ release branch.
- Existing debt: một số findings cũ trên module reconciliation.
- Security requirements: không có injection trong privileged billing paths, phân quyền tenant và không lộ secrets.

Đội phát triển tin rằng “mỗi PR đều chạy pipeline, build xanh thì có thể merge”.

### 20.2. Vấn đề phát hiện trong review

Đội assurance kiểm tra và nhận thấy:

1. CI có job SAST nhưng **không phải required check** trên protected branch.
2. Required check `build-success` không phụ thuộc vào SAST.
3. Scanner chỉ quét **Java API**, bỏ qua TypeScript và Python dù nằm trong release scope.
4. Một PR sửa build script để thêm exclusion mới; không có security owner review.
5. Scanner CLI trả timeout, wrapper đổi exit code thành success để tránh làm “hỏng pipeline”.
6. Kết quả SAST gắn PR head C1 nhưng merge queue tạo revision C2.
7. Release pipeline chạy trên release branch ít kiểm soát hơn default branch.
8. Một finding SQL injection có thể thuộc blocking class nhưng được ghi “false positive” không có bằng chứng.
9. Exception của existing debt đã hết hạn nhưng dashboard vẫn coi “accepted”.
10. Image được deploy theo tag `billing-api:release`, không chứng minh digest gắn với source đã scan.

**Kết luận:** Việc job có tên SAST và CI xanh không chứng minh **enforcement**. Hệ thống có các **trust/coverage gaps** độc lập.

### 20.3. Sơ đồ failure paths

~~~mermaid
flowchart TD
    PR["Proposed PR"] --> CI["CI build-success"]
    PR --> S["SAST on Java only"]
    S --> X["Scanner timeout handled as success"]
    CI --> M["Merge allowed: SAST not required"]
    X --> M
    M --> R["Release branch without equivalent gate"]
    R --> B["Build tagged image"]
    B --> D["Deploy by mutable tag"]
    D --> P["Production"]
    G["Unverified exclusions/false positive/exception"] --> S
~~~

Sơ đồ mô tả một **kịch bản giả định**; kết quả thực tế phải được chứng minh qua configuration inspection, controlled negative tests và logs. Không được giả định đã có một exploit trên production chỉ vì gate có lỗ hổng.

### 20.4. Threat scenarios

| Risk ID | Attacker capability/condition | Consequence | Expected control |
|---|---|---|---|
| **R-GATE-01** | Contributor có thể tạo PR chứa injection | Merge code risky không bị chặn | Required SAST policy gate với đúng source |
| **R-GATE-02** | PR thay scanner config và exclude source | False-clean report | Protected policy/exclusion control |
| **R-GATE-03** | Scanner timeout do lỗi phụ thuộc | Soft-fail thành success | BLOCKED và controlled retry |
| **R-GATE-04** | Mã Python không được scan | Blind spot cho worker privileged | Required language coverage |
| **R-GATE-05** | Maintainer thay finding disposition | False-positive bypass | Evidence + independent review |
| **R-GATE-06** | Exception expiry không được check | Accepted risk vĩnh viễn | Scope/expiry validation |
| **R-GATE-07** | PR scan C1 nhưng merge C2 | Code chưa kiểm chứng được merge | Exact revision binding |
| **R-GATE-08** | Release/deploy bỏ gate hoặc build khác source | Artifact sai thoát kiểm soát | Trusted release/admission provenance |

### 20.5. Chuyển thành testable requirements

| ID | Requirement | Verification |
|---|---|---|
| **BH-GATE-01** | Mọi merge vào protected release branches phải có required SAST decision trên target revision, không có bypass không phê duyệt | Branch rules inspection + negative merge test |
| **BH-GATE-02** | Required Java/TypeScript/Python modules phải được phân tích đầy đủ; thiếu bất kỳ module nào → BLOCKED | Coverage manifest + failed-module simulation |
| **BH-GATE-03** | Scanner execution lỗi/timeout không tạo PASS | Fault injection, CI exit code/control test |
| **BH-GATE-04** | Thay rulepack/exclusions/baseline cần policy owner review | Malicious exclusion PR test |
| **BH-GATE-05** | Blocking findings không được đóng bằng disposition thiếu evidence và thẩm quyền | Unauthorized suppression/false-positive test |
| **BH-GATE-06** | Expired exceptions không được áp tại release gate | Exception expiry test |
| **BH-GATE-07** | Artifact production phải liên kết exact source commit đã được verify | Wrong revision/digest provenance test |
| **BH-GATE-08** | Existing debt phải được quản lý theo approved SLA/risk, không ẩn sau PR new-code PASS | Debt due-date test + release assessment |

### 20.6. Remediation theo lớp

**Lớp policy và governance**

- Thông qua quality gate policy, risk tier và rulepack.
- Bảo vệ scanner config, baseline/exclusions và review của security owners.
- Chuẩn hóa false-positive/exception workflow.

**Lớp scanning và coverage**

- Chạy analyzer cho required Java, TypeScript và Python modules.
- Đối chiếu expected/actual modules và partial diagnostics.
- Loại soft-fail của scanner bắt buộc; retry có kiểm soát.
- Chốt CI version/scanner/rulepack và exact revision.

**Lớp merge/release enforcement**

- Áp required trusted SAST check trên đúng protected branches.
- Thử manual/direct merge path trong sandbox.
- Release pipeline phải dùng source đã được đánh giá và áp release policy riêng.
- Verify digest/provenance tại deployment admission.

**Lớp operating assurance**

- Lưu per-PR policy/result/evidence.
- Reevaluate existing debt và exceptions.
- Monitoring branch/rule drift và scanner availability.
- Bổ sung regression tests khi có bypass hoặc missed finding.

### 20.7. Kết quả sau một đợt kiểm thử giả định

Đội thực hiện kiểm tra **50 PRs** với policy mới:

| Kết quả | Số PR | Diễn giải |
|---|---:|---|
| PASS bình thường | 34 | Required coverage, scan, policy đạt |
| FAIL | 8 | Có unresolved new blockers |
| BLOCKED | 4 | Scanner/coverage chưa đủ |
| PENDING_TRIAGE | 2 | Có findings chưa phân xử |
| EXCEPTION_ACTIVE | 2 | Có decision hợp lệ, chưa vá |
| **Tổng** | **50** | Tập PRs trong scope giả định |

Một PR FAIL vì injection trong Java code. Hai PR BLOCKED vì thiếu Python analyzer. Một exceptional release được phê duyệt với risk owner và follow-up; nó **không được ghi PASS**.

### 20.8. Assurance claim trước và sau sửa

**Trước remediation:**

> **Claim:** Một số PR đã chạy SAST job và hiển thị build-success, nhưng chưa có cơ sở kết luận code được merge/deploy bắt buộc vượt qua SAST quality gate.
>
> **Argument:** Required check chưa ràng buộc SAST, scanner có blind spots và timeout soft-fail, release không liên kết scanned source.
>
> **Evidence:** Effective branch rules, workflow/rulepack configs, scanner diagnostics, coverage manifest và review observations.
>
> **Limitations:** Đây là đánh giá **control weakness**, không phải khẳng định mọi merged change chứa lỗ hổng hoặc đã bị khai thác.

**Sau remediation và verification:**

> **Claim:** Trong các PRs thuộc BillingHub release scope được kiểm tra trong kỳ, quality gate đã enforce approved SAST policy đối với exact revisions và required modules; 34/50 PRs đạt normal PASS, các PRs còn lại được giữ ở các trạng thái FAIL/BLOCKED/PENDING/EXCEPTION riêng theo evidence.
>
> **Argument:** Trusted evaluator xác minh scan completion/rulepack/coverage; protected branch và release gates có negative tests chống bypass; policies/baseline/exception được kiểm soát.
>
> **Evidence:** Repo/CI effective settings, test results, coverage, gate decisions, report integrity refs, required check and release admission logs.
>
> **Limitations:** Kết luận chỉ hỗ trợ **hiệu lực quality gate trong scope và time window**, không chứng minh SAST phát hiện mọi vulnerabilities hay production không có runtime/design flaws.

### 20.9. Lessons learned

1. Chỉ kiểm tra **dashboard xanh** là chưa đủ.
2. Scanner execution, completeness và policy evaluation là **ba điều kiện độc lập**.
3. Required check phải được **enforce tại merge/release**, không chỉ tồn tại.
4. False-positive label và exception cần **thẩm quyền và evidence**.
5. Source commit và artifact identity phải khớp; tránh reuse scan cũ.
6. Gate cần **negative tests cho chính bản thân nó**.

## 21. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| “Scanner chạy xanh = secure” | Findings bị bỏ sót hoặc chưa đủ coverage | Report completion, rulepack và limits |
| Không yêu cầu SAST check ở branch rule | PR có thể merge dù SAST FAIL | Required trusted status + negative merge tests |
| Dùng exit code 0 dù scanner timeout | Báo 0 findings giả | BLOCKED khi required scanner error |
| Không có inventory modules/languages | SAST scan chỉ một phần project | Expected/actual coverage matrix |
| Dùng diff-only mà không xét cross-file flow | Lỗi do thay context bị bỏ sót | Analysis mode và threat-based full scan |
| Đánh dấu report C1 PASS cho merge C2 | Dùng evidence stale | Exact revision/merge-result binding |
| PR có quyền sửa chính gate policy | Có thể tự bỏ rules | Protected policy/CI workflow và independent approval |
| Required check name dễ giả mạo | Fake success có thể cho merge | Trusted job identity/source checks |
| Soft-fail mọi scanner outage | Tool lỗi tạo bypass | Explicit BLOCKED và exceptional workflow |
| “Không có Critical” đủ PASS | High-risk issues có thể bị bỏ qua | Risk-class rules và required triage |
| Dùng score tổng thay cho findings | Che một blocker trong nhiều warnings | Non-compensatory blocking conditions |
| Baseline toàn bộ hiện trạng mãi mãi | Existing security debt không được sửa | Owner, SLA, debt burn-down và release gate |
| PR không tạo lỗi mới = mọi release an toàn | Debt cũ quá hạn vẫn tồn tại | Distinct PR và release policies |
| Rulepack mới thấy lỗi cũ thì bỏ luôn | Known vulnerability tồn tại mà không remediation | Newly detected existing risk handling |
| Label false positive không giải thích | True positive bị che | Evidence + reviewer + retest trigger |
| Inline suppression quá rộng | Che finding mới sau refactor | Scoped/time-bound suppression |
| Risk accepted = fixed | Residual risk bị xóa khỏi báo cáo | Exception riêng có expiry và owner |
| Ngoại lệ tự gia hạn vô hạn | Bypass trở thành thường trực | Authorized renewal/reassessment |
| Chỉ đếm số alerts, không xem severity/context | Rủi ro bị đo sai | CWE/dataflow/exposure/business impact |
| Không test bản thân gate | Gate có thể luôn PASS | Positive/negative/failure-path tests |
| Untrusted PR chạy với privileged secrets | Có thể lộ token/ảnh hưởng release | Runner isolation và least privilege |
| Không bảo vệ cache/report artifacts | Untrusted result được dùng làm authority | Trusted provenance và namespaces |
| Chỉ đọc pipeline YAML | Effective branch/CI enforcement có thể khác | Configuration inspection và actual test |
| Không kiểm tra release artifact | Deploy mã không khớp scan | Build provenance và exact digest |
| Scanner có rule nhưng language parser lỗi | Scan incomplete mà không rõ | Parse diagnostics và required analyzers |
| Đếm exception vào PASS | KPI đánh lừa | Separate exception exposure và risk |
| “0 findings = zero vulnerabilities” | SAST có false negatives và blind spots | Threat modeling, DAST, penetration/integration tests |
| Audit chứa source/secrets không kiểm soát | Evidence biến thành nguồn rò rỉ | Masking, access control và retention |
| Đóng finding ngay khi commit fix | Không có rerun/verified outcome | Rescan exact revision và regression tests |
| Bỏ qua change triggers sau release | Gate settings/rules drift không được nhận ra | Continuous control verification |

## 22. Governance, roles và quality gate operating model

### 22.1. Rõ ai quyết định điều gì

| Vai trò | Trách nhiệm |
|---|---|
| **Business/system owner** | Quyết định business criticality, risk appetite input và scope hệ thống |
| **Application Security (AppSec)** | Thiết kế SAST rulepack, risk mapping, threat-based gate criteria và triage guidance |
| **Quality gate policy owner** | Phê duyệt/duy trì các điều kiện gate, version và change controls |
| **Developer/tech lead** | Sửa code, giải thích dataflow và cung cấp tests/impact |
| **CI/CD/platform owner** | Chạy scanner có quyền hạn phù hợp, kết nối trusted evaluator/enforcement, giám sát availability |
| **Release manager** | Xác định candidate/commit/artifact, các checks trước release và emergency workflow |
| **Risk owner** | Chấp nhận residual risk trong thẩm quyền cho phép, không tự biến exception thành PASS |
| **Security assurance/QA** | Thiết kế test gate, xác minh evidence, đánh giá coverage, kiểm tra bypass/retest |
| **Internal audit/independent reviewer** | Đánh giá độc lập policy effectiveness và operating evidence theo phạm vi |
| **Incident response/SOC** | Đánh giá exploitation/incident và triggers cho reassessment/hotfix |

### 22.2. Mẫu RACI

RACI: **R** – thực hiện; **A** – chịu trách nhiệm cuối cùng; **C** – tham vấn; **I** – nhận thông tin.

| Hoạt động | AppSec | Engineering | CI platform | Risk owner | Assurance |
|---|---|---|---|---|---|
| Soạn SAST rulepack/risk mapping | **A/R** | C | C | C | C |
| Quy định quality gate policy | **A/R** | C | R | C | C |
| Chạy scanner/troubleshooting | C | R | **A/R** | I | C |
| Sửa confirmed vulnerability | C | **A/R** | C | I | C |
| Triage false positive | **A/R** | C | I | I | C |
| Quyết định risk acceptance | C | C | I | **A/R** | C |
| Kiểm thử enforcement gate | C | C | R | I | **A/R** |
| Release assurance report | C | C | C | I | **A/R** |
| Incident response liên quan missed issue | R | R | R | C | C |

RACI chỉ là **mẫu quản trị**, không tự cấp quyền phê duyệt rủi ro vượt các quy định pháp lý hoặc nội bộ.

### 22.3. Design review / Definition of Ready

Trước khi bật gate cho một project:

1. Có inventory repo, languages, modules, security objectives và risk tier.
2. Có approved SAST tools/rulepack/baseline, language support map.
3. Có quyết định **new code vs existing debt**.
4. Có threshold/blocked conditions, triage SLA và exception authority.
5. Có trusted CI runner, evaluator và report store.
6. Có branch/release/deploy enforcement và đường emergency rõ.
7. Có test plan positive/negative/failure, including bypass scenarios.
8. Có owner cho scanning errors, findings, policy drift và evidence.

Một team thiếu owner/rulepack hoặc chưa biết ngôn ngữ nào scan được nên ghi **onboarding gap**, không âm thầm tuyên bố full coverage.

### 22.4. Definition of Done cho gate implementation

Chỉ có thể ghi control implemented/verified trong scope khi:

- Required scanner/rulepack thực sự chạy trên selected target.
- Coverage expected/actual được đối chiếu.
- Policy evaluator dùng trusted inputs và decisions phân biệt trạng thái.
- Protected branch/release gate thật sự block khi FAIL/UNKNOWN.
- Negative tests chống stale report, invalid exception, exclusion bypass và wrong artifact đã chạy.
- Audit logs có actors, policies, scan/report IDs, status và reasons.
- Exception workflow có owner/expiry và independent governance.
- Có monitoring cho scanner outage, rule drift, bypass và evidence freshness.
- Reviewers có thể tái lập hoặc độc lập xác minh quyết định.

### 22.5. Định nghĩa quality gate service-level expectations

Quality gate là **dịch vụ nội bộ** ảnh hưởng developer velocity. Có thể cần:

- **Availability/latency SLO** cho scanner và evaluator theo chính sách tổ chức.
- Timeout/retry/backoff có giới hạn.
- Autoscale concurrency và quota management.
- Monitoring tool upgrades và deterministic failure classification.
- Cache theo key có source commit/rulepack/scanner identity, chống stale reuse.
- Release emergency procedure và after-action review.

**Không tự chọn SLO như “scan luôn dưới 2 phút”** cho codebase khác nhau. Hãy chốt mục tiêu theo size, risk, rule coverage và tính khả thi; giảm thời gian không được làm mất required analysis.

## 23. Bài tập thực hành

### Bài tập 1 — Viết quality gate policy từ security objectives

Một hệ thống nhiều tenant có Java API và Python worker; mục tiêu là ngăn injection, lộ secret và sửa invoice trái phép. Team đang có rule “không quá 5 findings” và không kiểm tra scan completeness.

**Yêu cầu:** Thiết kế gate policy theo risk: repo/module/language, ruleset, severity/confidence, new/existing, source revision và failure behavior. Nêu điều kiện nào phải **FAIL**, điều kiện nào phải **BLOCKED**, và những security properties mà SAST không thể chứng minh một mình.

**Tự kiểm tra:** Không chọn một số threshold tùy ý nếu chưa có approved policy; có coverage và threat-based tests ngoài SAST.

### Bài tập 2 — Scanner thành công nhưng module bị bỏ qua

Một monorepo có 6 modules, scanner chỉ phân tích 5 do Java build dependency thiếu. Wrapper trả exit code 0 và dashboard báo zero critical findings.

**Yêu cầu:** Xác định **scan execution state**, **analysis coverage**, **finding state** và **quality gate outcome**. Viết một requirement và 2 negative tests đảm bảo missing module không bị coi PASS. Lập evidence cần thu.

**Tự kiểm tra:** “0 findings trong 5 modules” không phải evidence cho 6 modules.

### Bài tập 3 — PR head khác merge commit

Commit `C1` được SAST scan PASS. Một PR được rebase và merge queue sinh `C2` khác C1. Branch rule chỉ yêu cầu check đã từng xanh trên PR.

**Yêu cầu:** Vẽ trust/evidence path từ PR → merger → protected branch. Xác định policy phải gắn revision ở đâu, cách invalid stale result và negative test dùng report C1 xin quyền merge C2.

**Tự kiểm tra:** Có exact revision binding và effective branch check, không chỉ tên job.

### Bài tập 4 — False positive chưa được chứng minh

SAST cảnh báo SQL injection; developer đánh dấu false positive vì “frontend đã validate”. AppSec chưa review và code backend nối raw input vào SQL syntax.

**Yêu cầu:** Viết triage questions/source-sink reasoning, cách sửa an toàn, test oracle và policy handling trước khi có disposition. Định nghĩa ai duyệt false positive, evidence và invalidation triggers.

**Tự kiểm tra:** Frontend validation không phải trust boundary enforcement đủ; chưa được duyệt không tự động cho qua.

### Bài tập 5 — Legacy debt và quality gate mới

Repository có 48 findings baseline. PR sửa được 3 findings cũ nhưng phát sinh 2 mới, trong đó 1 thuộc blocking policy. Developer lập luận tổng số findings đã giảm nên gate phải PASS.

**Yêu cầu:** Tính findings còn lại theo giả định không có reopen/rule change, đánh giá new-code gate, phân biệt release gate và lập debt burn-down plan.

**Tự kiểm tra:** Tổng alerts giảm không xóa một blocker mới.

### Bài tập 6 — Scanner outage trong emergency hotfix

Production cần hotfix để khắc phục outage, nhưng SAST provider không phản hồi. Release manager muốn `continue-on-error=true` và đánh dấu PASS.

**Yêu cầu:** Thiết kế incident/emergency change process: BLOCKED mặc định, alternative checks, independent approval, residual risk, exact source/artifact binding, audit và mandatory follow-up scan. Viết một Gherkin scenario.

**Tự kiểm tra:** Không biến “không biết” thành “đã scan sạch”.

### Bài tập 7 — Thay rulepack và exclusions

Một PR chỉnh rulepack từ V9 về V0, thêm exclusion cho `src/main/**`, và CI job vẫn trả success. Files được scan giảm từ 500 xuống 12.

**Yêu cầu:** Phân tích attack path vào gate, so expected/actual scope, policy ownership, negative tests và protected configuration. Nêu phép đo nào sẽ phát hiện coverage drift.

**Tự kiểm tra:** Không để PR-controlled config làm authority duy nhất cho chính PR đó.

### Bài tập 8 — Exception đúng và sai scope

Một exception cho finding F1 được phê duyệt trên release R1, component legacy A, thời hạn đến kỳ review tiếp theo. Team dùng cùng exception để release R2 với module mới B và source revision khác.

**Yêu cầu:** Viết rule exception scope/expiry validation, các trường cần lưu, decision khi mismatched, ai được renew và cách test với invalid approver.

**Tự kiểm tra:** Exception không là wildcard permission; không đồng nghĩa fixed.

### Bài tập 9 — CI/CD bypass

Một job `sast-scan` chạy trên PR nhưng default branch chỉ yêu cầu `build-success`. Bot có quyền direct push; release branch không có protected rules.

**Yêu cầu:** Lập access/bypass matrix, xác định path nào có thể merge/deploy mà không qua SAST, viết 3 negative enforcement tests trong sandbox, và mô tả evidence thực tế từ provider settings/attempted merge.

**Tự kiểm tra:** Có đánh giá cả **branch, bot, release và emergency paths**, không chỉ pipeline YAML.

### Bài tập 10 — Kết quả scan bị giả

Một PR có thể upload `scan-report.json`. Gate đọc report này và chỉ kiểm tra field `blockingCount=0`. Attacker thay file và gửi metadata commit sai.

**Yêu cầu:** Thiết kế report provenance, authentication, integrity, source revision/rulepack binding và schema validation; viết negative tests cho wrong signer, wrong commit và missing coverage diagnostics.

**Tự kiểm tra:** Không tin một trường JSON success do source chưa tin cậy tự tạo.

### Bài tập 11 — Tính gate coverage trung thực

Trong 50 PRs: 34 PASS, 8 FAIL, 4 BLOCKED, 2 PENDING_TRIAGE và 2 EXCEPTION_ACTIVE. Ngoài ra có một admin direct merge chưa ghi vào bộ dữ liệu này.

**Yêu cầu:** Tính normal PASS rate trên 50 PRs đã biết, báo riêng các trạng thái còn lại và giải thích tại sao **population completeness** chưa đạt. Đề xuất metrics cho branch bypass và source revision freshness.

**Tự kiểm tra:** Không cộng exceptions vào PASS, không loại BLOCKED khỏi mẫu số.

### Bài tập 12 — Rulepack mới phát hiện vulnerability cũ

Scanner V2 phát hiện một issue High trong code tồn tại nhiều năm nhưng V1 không thấy. Team muốn đóng vì “không phải new code”.

**Yêu cầu:** Phân biệt newly detected existing issue với regression, đánh giá urgency theo risk/exploitation, tạo finding owner/SLA và xác định release blocking rule phù hợp policy.

**Tự kiểm tra:** Không trách developer của PR hiện tại một cách thiếu căn cứ, nhưng cũng không bỏ vulnerability thật.

### Bài tập 13 — Từ SAST PASS tới deploy artifact

Một artifact được build từ commit C2 nhưng report SAST PASS của C1 được dùng để deploy. Registry tag là mutable và deployment thiếu digest pinning.

**Yêu cầu:** Thiết kế release trust chain, required source/provenance/digest checks, gate decision expected và verification record. Phân tích vì sao scanner PASS của C1 không hỗ trợ claim về C2.

**Tự kiểm tra:** Có source→build→artifact→runtime evidence và admission enforcement.

### Bài tập 14 — Xây chương trình continuous quality gate assurance

Một tổ chức có 40 repositories, 4 language stacks, nhiều scanner versions và exceptions lịch sử. Nhiều repo đã thay branch rules, một số scans timeout và 8 repositories chưa có owner.

**Yêu cầu:** Thiết kế inventory, policy-tier, rulepack governance, coverage matrix, drift monitoring, exception review, metrics, RACI, evidence package và periodic negative tests. Chốt criteria để biết **gate implemented** khác **gate operating effectively**.

**Tự kiểm tra:** Báo cáo thể hiện UNKNOWN/UNOWNED và paths không được kiểm tra thay vì tuyên bố mọi repo PASS.

## 24. Checklist triển khai và kiểm chứng quality gate

### 24.1. Mục tiêu, scope và nguồn yêu cầu

- **Objective:** Đã định nghĩa security requirements/threat scenarios nào quality gate góp phần kiểm chứng?
- **Risk tier:** Project/data/identity/tenant criticality và business risk được xác định theo policy?
- **Source inventory:** Có đúng repo ID, protected branches, source revision và owner?
- **Languages/modules:** Có inventory của tất cả required languages, modules, generated code, build targets?
- **Rule scope:** Có mapping từ security objective/CWE classes tới SAST rules?
- **Analysis limits:** Có ghi những threat classes không được SAST hỗ trợ và controls bổ sung?
- **Target type:** PR, merge result, release candidate, artifact và deployed state được phân biệt?
- **Policy owner:** Gate conditions, exceptions, baseline và ruleset có owner/approver?

### 24.2. Scanner và scan completeness

- **Trusted scanner:** Engine/plugins/rulepack có nguồn và version được phê duyệt?
- **Exact source:** Scan report có liên kết commit/merge-result đúng target?
- **Required analyzers:** Mọi ngôn ngữ/module trong inventory có analyzer phù hợp?
- **Build context:** Dependencies/build IR/dataflow cần thiết có sẵn và không lỗi?
- **Execution status:** Timeout, crash, quota và partial scans được nhận diện, không biến thành success?
- **Coverage manifests:** Có expected vs analyzed files/modules/languages/paths và lý do skip?
- **Exclusions:** Patterns có owner, approval, scope, review trigger và không che critical sources?
- **Report integrity:** Scanner result có provenance, input, diagnostics và integrity reference?
- **Rule changes:** Rulepack update có impact analysis và rebaseline theo policy?
- **False negatives:** Có fixtures/test bổ sung và manual review high-risk paths?

### 24.3. Finding evaluation

- **Finding identity:** Rule/CWE, fingerprint, dataflow, source commit và impacted component?
- **Severity/confidence:** Có phân biệt scanner severity, confidence và risk contextual?
- **Triage:** Pending findings có owner và policy handling?
- **False positive:** Có reasoning/evidence/reviewer/expiry or reassessment?
- **Duplicates:** Có canonical root cause và không xóa impact khác?
- **Fix:** Finding được đóng bằng rerun/retest trên revision đúng, không chỉ ticket comment?
- **New vs existing:** Baseline được xác minh, không che newly detected existing vulnerabilities?
- **Debt SLA:** Existing high-risk issues được quản lý theo deadline/risk, không bỏ vô hạn?
- **Suppression:** Inline/project suppressions có scope hẹp và authority?
- **Exception:** Risk acceptance có owner, scope, expiry, controls bù và policy authority?
- **Expired exception:** Bị từ chối khi dùng cho release mới/khác scope?

### 24.4. Gate logic và trạng thái

- **Complete-first:** Không xét 0 blocking findings là PASS trước khi scan completeness đạt?
- **Decision model:** PASS/FAIL/BLOCKED/PENDING/EXCEPTION/N/A/STALE được định nghĩa?
- **No unknown-as-pass:** Khi scanner timeout/partial/unsupported, quyết định đúng theo policy?
- **Policy version:** Effective gate rules, severity mapping và baseline có integrity?
- **Source binding:** Report target repo/commit và artifact chính xác?
- **Multiple sub-gates:** Có kiểm tra mọi required scanner, không optionalize ngầm?
- **Reason codes:** Decision giải thích rule/finding/coverage nào khiến FAIL hoặc BLOCKED?
- **No arbitrary override:** Thay policy/waiver phải qua governance và audit?
- **Emergency:** Có exceptional path được phê duyệt, không ghi giả PASS?

### 24.5. CI/CD enforcement và trust boundaries

- **Required checks:** Branch protection/ruleset bắt đúng trusted SAST gate check?
- **Latest revision:** Merge queue/rebase/new commits có invalidate scan cũ?
- **Direct push:** Bot/admin/maintenance/release branches có đường bypass chưa quản lý?
- **Untrusted PR:** PR code không có production secrets, publish/deploy permissions?
- **Policy tampering:** PR không tự hạ rulepack, thresholds hoặc exclude scope?
- **Result tampering:** PR không thể tự upload forged report và làm trusted evaluator PASS?
- **Cache/artifact isolation:** Untrusted outputs không được đưa thẳng sang release gate?
- **Release path:** Full release source/baseline risk policy có được đánh giá riêng?
- **Artifact provenance:** Exact build source commit, builder và artifact digest được kiểm tra?
- **Deployment:** Admission chỉ nhận artifact đã qua policy, không dùng mutable tag làm proof duy nhất?
- **Negative bypass tests:** Đã thực hiện các thử nghiệm có phép để chứng minh enforcement?

### 24.6. Assurance evidence và vận hành

- **Evidence contract:** Repository, commit, scan job, rulepack, coverage, findings, evaluator, decision và reviewer đã được lưu?
- **Security of evidence:** Source snippets/tokens và report access được bảo vệ, retention có policy?
- **Reproducibility:** Reviewer độc lập có thể đánh giá lại theo rulepack/target?
- **Audit:** Policy, baseline, exclusions, overrides và exceptions có change history đáng tin?
- **Metrics:** PASS rate có mẫu số scope; FAIL/BLOCKED/PENDING/EXCEPTION được tách?
- **Population:** Có kiểm kê những PRs/releases đi đường admin/manual/bypass?
- **Freshness:** Evidence còn khớp current commit, policy và scanner?
- **Drift:** Scanner config/CI permission/branch rules thay đổi có alert/review?
- **Findings:** Có remediation owner, risk, time-to-verified-fix và independent retest?
- **Reassessment:** Rulepack, architecture, dependencies, incident, policy và exceptions đổi có trigger scan/review?
- **Assurance claim:** Chỉ kết luận điều scanner/gate thực sự chứng minh, nêu limitations?

## 25. Tổng kết

Một quality gate đúng nghĩa không bắt đầu và kết thúc bằng câu “SAST có bao nhiêu lỗi?” mà cần lần lượt hỏi:

1. **Đang đánh giá điều gì?** Mục tiêu bảo mật, risk tier, source revision, ngôn ngữ và modules thuộc scope.
2. **Scanner có đủ năng lực và đã chạy đúng?** Rulepack/engine được duyệt, required analyzers và coverage đủ; không có partial/error chưa xử lý.
3. **Findings nói gì?** Rule/CWE, severity, confidence, dataflow, context, new/existing và triage evidence.
4. **Chính sách quyết định thế nào?** Điều kiện blocking, baseline debt, source-of-truth, exception authority, expiry và special conditions.
5. **Khi thiếu bằng chứng có an toàn không?** Không biến scanner failure, stale report hoặc incomplete scope thành 0 findings.
6. **Gate có thực sự chặn không?** Protected branch/release/deploy effective enforcement, không có bypass im lặng.
7. **Có ràng buộc source đến release không?** Exact commit, trusted build, artifact digest và provenance.
8. **Có giải thích được kết luận không?** Evidence, audit, reviewer, scope, limitations, findings và retest.
9. **Có duy trì liên tục không?** Rulepack updates, policy drift, new modules, existing security debt và incidents được đưa vào reassessment.

**Điều cần ghi nhớ:** Trong **static analysis**, quality gate không đơn giản là “lấy status xanh từ công cụ”. Nó là một **security control có thể kiểm thử** gồm **policy rõ, scan đúng scope, finding được đánh giá theo rủi ro, quyết định PASS/FAIL/BLOCKED trung thực, enforcement đáng tin và evidence truy vết tới đúng revision/artifact**. Trong **SECURITY_SECURITY_ASSURANCE**, kết luận phù hợp phải nói rõ **điều gì được chứng minh, tại thời điểm nào, cho hệ thống/release nào, còn blind spots và residual risks nào**, rồi quản trị remediation, exceptions và reassessment liên tục. **Gate PASS làm tăng assurance trong phạm vi đã kiểm tra, không thay thế threat modeling, security testing, audit và kiểm soát vận hành.**
