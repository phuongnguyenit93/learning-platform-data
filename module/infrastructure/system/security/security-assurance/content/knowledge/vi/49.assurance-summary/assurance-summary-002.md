# Luồng từ Risk đến Evidence: Kết nối rủi ro, kiểm soát và bằng chứng trong Security Assurance

Một nhóm kỹ thuật báo cáo: “Hệ thống đã triển khai MFA, quét lỗ hổng hằng ngày và có 15 trang bằng chứng audit; vì vậy rủi ro được kiểm soát.” Người đánh giá hỏi tiếp: **MFA bảo vệ đường truy cập nào? Quét lỗ hổng bao phủ bao nhiêu tài sản? Bằng chứng gắn với yêu cầu nào? Rủi ro nào còn tồn tại? Ai xác nhận kết quả và khi nào cần đánh giá lại?** Nếu không trả lời được, nhiều artifact có thể tạo ấn tượng an toàn mà chưa hình thành một kết luận assurance có căn cứ.

**Luồng từ risk đến evidence** là phương pháp tổ chức chuỗi lập luận có thể kiểm chứng: **rủi ro nào cần quản trị → mục tiêu bảo mật nào phải đạt → yêu cầu và security controls nào xử lý rủi ro → phép kiểm tra nào đánh giá hiệu lực → bằng chứng nào được thu → kết luận nào được phép rút ra → quyết định và cải tiến tiếp theo là gì**. Nó không phải quy trình tuyến tính chỉ đi một chiều: một finding mới có thể làm thay đổi risk assessment; một thay đổi kiến trúc có thể làm bằng chứng cũ không còn hiệu lực; một lần retest có thể dẫn đến đóng finding nhưng vẫn cần theo dõi rủi ro còn lại.

Bài này thuộc chương **Tổng kết security assurance** của module **SECURITY_SECURITY_ASSURANCE**. Mục tiêu toàn module là **xây dựng cách đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật**, từ phân tích rủi ro, yêu cầu và security controls tới kiểm thử, audit, khắc phục phát hiện và tổ chức security assurance liên tục trong phát triển và vận hành. Bài tổng kết giúp người học ghép các hoạt động đó thành một **hệ thống quyết định dựa trên chứng cứ**, thay vì những danh sách kiểm tra rời rạc.

Sau khi học, bạn có thể vẽ traceability graph risk–requirement–control–test–evidence–claim, viết security risk scenario có phạm vi, thiết kế một bộ evidence có thể tái lập, phân biệt control failure với evidence gap, tạo kết luận PASS/FAIL/INCONCLUSIVE không vượt phạm vi, liên kết findings và remediation, cũng như xác định trigger phải đánh giá lại theo thời gian.

## 1. Nhìn toàn cảnh: Risk → Objective → Requirement → Control → Test → Evidence → Decision

~~~mermaid
flowchart TD
    B["Business process, tài sản, dữ liệu, trust boundaries"] --> R["Risk scenario / threat / exposure"]
    R --> O["Security objective: điều cần bảo vệ"]
    O --> Q["Requirement / acceptance criterion / policy version"]
    Q --> C["Control design và effective implementation"]
    C --> T["Test method / scope / expected outcome"]
    T --> E["Raw evidence + provenance + observed result"]
    E --> V["Control verdict: PASS / FAIL / INCONCLUSIVE"]
    V --> A["Assurance claim + warrant + limitations"]
    R --> K["Risk assessment / impact / likelihood"]
    V --> K
    A --> D["Risk owner và release/operate decision"]
    K --> D
    D --> F["Finding / mitigation / exception / remediation"]
    F --> X["Change + retest + verified residual risk"]
    X --> V
    X --> M["Continuous monitoring / event-driven reassessment"]
    M --> R
    M --> E
~~~

Sơ đồ này là **mô hình khái niệm**, không buộc mọi tổ chức đi theo một bộ công cụ. Có thể dùng GRC, ticketing, GitOps, CI/CD, log warehouse và evidence vault khác nhau. Điều bất biến phải được giữ là **khả năng truy vết quan hệ và chất lượng quyết định**.

Một luồng tốt cho phép kiểm tra cả hai hướng:

- **Từ risk xuống evidence:** Rủi ro này được xử lý bởi những controls nào? Có test và evidence nào xác nhận hiệu lực? Những giả định nào còn chưa chứng minh?
- **Từ evidence lên risk:** Artifact này đến từ đâu, đánh giá control nào, trên scope nào và có thể làm thay đổi risk assessment hoặc assurance claim nào?

**Một bản evidence không tự có ý nghĩa bảo đảm** cho tới khi được gắn với tiêu chí và lập luận thích hợp. Ngược lại, **một điểm risk không tự là bằng chứng control đang thiếu**.

## 2. Phân biệt các đối tượng để tránh “cùng một từ, nhiều nghĩa”

| Đối tượng | Câu hỏi nó trả lời | Ví dụ ngắn | Không được nhầm với |
|---|---|---|---|
| **Asset / business process** | Cái gì có giá trị và nằm trong phạm vi? | Dịch vụ hóa đơn, tenant data, KMS, IdP. | Một finding hoặc một threat. |
| **Threat scenario** | Điều bất lợi nào có thể xảy ra, theo đường nào? | User tenant A đọc dữ liệu tenant B. | Bằng chứng rằng sự cố đã xảy ra. |
| **Risk** | Kịch bản đó có hậu quả/khả năng gì trong bối cảnh? | Lộ hóa đơn và trách nhiệm bảo vệ dữ liệu. | Chỉ một CVE hay severity của scanner. |
| **Security objective** | Mục tiêu phòng ngừa, phát hiện hoặc phục hồi gì? | Không truy cập chéo tenant trái quyền. | Một công cụ hoặc cấu hình cụ thể. |
| **Requirement** | Điều kiện có thể kiểm tra, nguồn và phiên bản nào? | Mọi API trả hóa đơn phải xác thực ownership. | Lời hứa “ứng dụng an toàn”. |
| **Control** | Biện pháp kỹ thuật/quy trình nào đáp ứng yêu cầu? | Server-side authorization mỗi lần đọc. | Việc có viết tài liệu thiết kế. |
| **Test / assessment** | Dùng phương pháp nào kiểm tra điều kiện nào? | Negative cross-tenant API tests. | Thực tế toàn hệ thống nếu chỉ test mẫu. |
| **Evidence** | Dữ kiện quan sát có nguồn và thời điểm nào? | Request/response kiểm thử, policy export. | Kết luận PASS tuyệt đối. |
| **Finding** | Khoảng lệch đã được đánh giá và ghi nhận? | Hai endpoints trả dữ liệu sai tenant. | Risk acceptance hay remediation đã hoàn tất. |
| **Assurance claim** | Kết luận có thể bảo vệ dựa trên grounds/warrant? | Đường được kiểm đã chặn truy cập chéo tenant. | “Không có lỗ hổng trong mọi trường hợp”. |
| **Risk decision** | Ai cho phép, yêu cầu sửa, hạn chế hoặc chấp nhận gì? | Chặn release đến khi sửa và retest. | Kết quả kiểm thử kỹ thuật. |
| **Residual risk** | Rủi ro còn lại sau controls đã được đánh giá? | Khả năng sai phân quyền còn trên paths chưa thử. | Target risk dự kiến trong kế hoạch. |

Trong một dự án thực, các đối tượng này thường có quan hệ **nhiều–nhiều**: một control có thể giảm nhiều risk scenarios; một risk có nhiều controls; một test có thể đánh giá nhiều control criteria; một evidence item có thể được tái sử dụng nhưng **chỉ trong phạm vi mà nó thực sự hỗ trợ**.

## 3. Điểm bắt đầu: Business context và phạm vi có thể kiểm chứng

Một risk assessment bắt đầu từ bối cảnh, không từ danh sách alert. Xác định dịch vụ, loại dữ liệu, người dùng, nhà cung cấp, môi trường, tài sản, quyền quản trị và dependencies. Nếu bỏ asset khỏi inventory, các báo cáo control coverage có thể vô tình đẹp hơn thực tế.

### 3.1. Các câu hỏi scope

1. Dịch vụ hỗ trợ quy trình kinh doanh nào? Mất confidentiality, integrity, availability hoặc recoverability dẫn tới điều gì?
2. Hệ thống xử lý dữ liệu cá nhân, giao dịch, hóa đơn, bí mật hay tài sản trọng yếu nào?
3. Những tài khoản cloud, clusters, regions, tenants, tài khoản máy và tài khoản nhà cung cấp nào thuộc scope?
4. Những luồng nào vượt trust boundary? Có direct access, break-glass, background jobs hoặc admin support path?
5. Những thành phần ngoài tầm quan sát của tools vẫn có tác động đến claim?
6. Đang đánh giá ở **thời điểm T** hay cần bảo đảm một **kỳ**?
7. Có luật, hợp đồng, policy hoặc standard nào áp dụng cần kiểm tra đúng nguồn và phiên bản?

### 3.2. Phân tách hai tập đối tượng

- **Target population:** toàn bộ đối tượng mà requirement áp dụng.
- **Assessed population:** phần đối tượng được đánh giá bằng bằng chứng đủ điều kiện.

Ví dụ có 120 workloads production nhưng scanner đọc được 100. Không được kết luận “100% workloads đạt” nếu 100/100 đã quét đều PASS; **20 workload không có evidence vẫn nằm trong target population**. Thiếu evidence không tự chứng minh FAIL, nhưng cũng không thể bị xem là PASS.

### 3.3. Artifact cần tạo

Một **Scope Register** với asset IDs ổn định, owner, environment, data sensitivity, business service, trust boundary, last_verified_at, inventory source và trạng thái completeness. Nếu inventory là giả định hoặc chưa reconciliation, ghi rõ điều đó trước khi tính các chỉ số khác.

## 4. Risk discovery: Viết kịch bản rủi ro thay vì chỉ gắn điểm

Một risk record cần nêu **nguyên nhân/điều kiện, threat actor hoặc accidental event, đường tác động, asset, kết quả bất lợi và tác động tới mục tiêu bảo mật**.

### 4.1. Khung viết risk statement

~~~text
Do [actor/sự kiện] có thể lợi dụng [điều kiện/vulnerability/control gap]
qua [attack/operational path] trên [assets và trust boundary],
dẫn tới [undesired event] và gây [impact] cho [business/data scope].
~~~

**Ví dụ chưa tốt:** “API authorization: Critical.”

**Ví dụ có thể đánh giá:** “Người dùng tenant A có thể gửi request lấy hóa đơn qua API endpoint thiếu kiểm tra ownership ở server, nhận dữ liệu thuộc tenant B và gây mất bí mật dữ liệu khách hàng trên các endpoints bị ảnh hưởng.”

**Ví dụ chưa đủ căn cứ:** “Hệ thống backup chắc chắn mất dữ liệu vì chưa restore test.”

**Diễn đạt đúng hơn:** “Khi cần phục hồi sau KMS rotation, có nguy cơ backup không giải mã hoặc không đạt recovery objective do chưa có restore/decrypt evidence đủ mới; hiện tại khả năng phục hồi còn INCONCLUSIVE.”

### 4.2. Những nguồn phát hiện risk

- Threat modeling theo data flows, trust boundaries và misuse cases.
- Findings từ security testing, vulnerabilities, penetration testing hoặc configuration reviews.
- Audit observations, incidents, near misses và threat intelligence phù hợp.
- Change/release impact analysis, vendor/dependency changes và exception backlog.
- Business Impact Analysis, resilience tests và những giả định về thời gian phục hồi.
- Evidence pipeline gaps như logs bị mất hoặc inventory không đầy đủ.

Risk discovery là **giả thuyết có lý do để kiểm tra**, không phải kết luận đã có tấn công. Một finding có test chứng minh control thất bại; còn sự cố đã xảy ra cần evidence riêng về event và tác động.

## 5. Đánh giá Risk: Likelihood, impact và sự không chắc chắn

Rủi ro không chỉ phụ thuộc severity của vulnerability. Cần xem **reachability, exposure, attacker prerequisites, giá trị tài sản, khả năng khôi phục, controls hiện có và threat context**.

### 5.1. Ví dụ thang 5×5 trong bài

| Mức | Likelihood — cách hiểu mô phỏng | Impact — cách hiểu mô phỏng |
|---|---|---|
| **1** | Đường xảy ra rất hạn chế trong điều kiện đã biết. | Ảnh hưởng cục bộ, dễ khôi phục. |
| **2** | Khó xảy ra, có nhiều điều kiện hoặc bảo vệ hiệu lực. | Ảnh hưởng nhỏ, không lan rộng. |
| **3** | Kịch bản có khả năng, một số điều kiện đã hiện hữu. | Ảnh hưởng đáng kể một chức năng/tập dữ liệu. |
| **4** | Exposure thuận lợi, control gap rõ hoặc đường xảy ra dễ thực hiện. | Gián đoạn lớn hoặc lộ dữ liệu nhạy cảm. |
| **5** | Đang diễn ra/khả năng rất cao theo bối cảnh và evidence. | Sự cố rất nghiêm trọng, diện rộng hoặc khó phục hồi. |

**Thang điểm là mô hình minh họa**, không phải tiêu chuẩn phổ quát. Có thể tính **L × I** để ưu tiên thảo luận, nhưng phép nhân hai mức ordinal **không tạo ra xác suất tấn công hoặc expected monetary loss**. Nếu tổ chức dùng FAIR, định lượng tổn thất hoặc một risk method khác, phải tuân theo định nghĩa và nguồn dữ liệu đã phê duyệt.

### 5.2. Bốn trường cần tách

| Trường | Ý nghĩa | Có thể ghi gì khi chưa đủ evidence? |
|---|---|---|
| **Inherent risk** | Trước những controls được xét theo phương pháp. | Estimate với rationale/assumptions. |
| **Current risk** | Rủi ro hiện tại sau controls đang hoạt động được xác minh. | Provisional, kèm confidence và unknowns. |
| **Projected target risk** | Dự kiến nếu treatment hoàn tất và có hiệu lực. | Estimate; ghi rõ NOT_VERIFIED. |
| **Verified residual risk** | Rủi ro đánh giá lại sau remediation/retest. | NOT_ASSESSED cho đến khi có evidence mới. |

Một action plan chưa triển khai **không làm giảm current risk**; một risk acceptance được ký **không làm control FAIL chuyển thành PASS**. Confidence cao với một phép test đúng scope không đồng nghĩa confidence cao cho toàn bộ fleet hoặc lịch sử nhiều tháng.

## 6. Từ Risk sang Security Objective

Security objective nói rõ **điều cần bảo đảm**. Nó đủ độc lập với công nghệ để dùng đánh giá nhiều phương án.

Ví dụ, với risk truy cập chéo tenant:

- **RISK-AUTH-01:** khách hàng tenant A có thể đọc hóa đơn tenant B.
- **Objective SEC-OBJ-01:** bảo vệ tính bí mật và ranh giới ủy quyền giữa các tenants.
- **Không nên dùng objective:** “Triển khai một middleware authorization mới”, vì đây chỉ là **giải pháp** chứ không phải mục tiêu.
- **Objective đo được hơn:** “Mọi truy xuất hóa đơn phải có danh tính xác thực, quyền và ràng buộc tenant ownership hợp lệ; đường không hợp lệ bị từ chối và ghi audit theo yêu cầu.”

Một risk khác về audit logs có thể có objective “khả năng phát hiện và điều tra truy cập dữ liệu quan trọng”. Nhiều controls có thể cùng hỗ trợ một objective; cần xác định **kết quả cần đạt**, không chỉ tên công cụ.

### 6.1. Liên kết CIA và các thuộc tính khác

- **Confidentiality:** tránh đọc trái phép dữ liệu khách hàng.
- **Integrity:** tránh sửa invoice/transaction trái quyền hoặc không phát hiện.
- **Availability:** hệ thống phục vụ đúng SLO và giảm downtime.
- **Authenticity/accountability:** người thực hiện có thể xác minh, hành động có dấu vết.
- **Recoverability:** phục hồi được với RTO/RPO và trạng thái bảo mật phù hợp.
- **Privacy obligations:** xử lý dữ liệu đúng mục đích và nghĩa vụ áp dụng.

Đừng viết tất cả objective ở mức “bảo mật tốt” vì không thể thiết kế criteria kiểm chứng.

## 7. Từ Objective sang Requirement có tiêu chí nghiệm thu

**Requirement** biến một mục tiêu thành **điều kiện có thể đánh giá**, kèm nguồn, phiên bản, phạm vi và thẩm quyền.

| Objective | Requirement minh họa | Evidence/điều kiện đánh giá |
|---|---|---|
| Cô lập tenant. | **REQ-AUTH-01:** mọi API đọc/sửa hóa đơn phải kiểm tra server-side authorization gắn resource với tenant của principal. | Endpoint inventory + positive/negative tests trên scope. |
| Bảo vệ dữ liệu lưu trữ. | **REQ-DATA-02:** hóa đơn không được đọc ẩn danh trong production. | Effective bucket/access policy và anonymous-deny tests. |
| Least privilege. | **REQ-IAM-03:** service identity chỉ có effective permissions phù hợp nhiệm vụ, ngoại lệ phải được quản trị. | Principal inventory, policy export và allowed/denied action tests. |
| Auditability. | **REQ-LOG-04:** events quản trị quan trọng phải tới kho logs được bảo vệ theo tiêu chí latency/retention đã ban hành. | Source event → collector → SIEM test, coverage và retention evidence. |
| Recoverability. | **REQ-DR-05:** backup/keys và quy trình restore đạt RTO/RPO được xác định từ BIA. | Restore/decrypt rehearsal, integrity và timing records. |

Các mã REQ là **ví dụ trong bài**. Khi áp dụng tiêu chuẩn hoặc nghĩa vụ bên ngoài, cần lưu **source document/version, applicability và quyền xử lý nonconformity**. Một quyết định nội bộ không tự miễn pháp luật hoặc hợp đồng.

### 7.1. Viết tiêu chí có thể phản chứng

**Yếu:** “IAM phải đủ an toàn.”

**Có thể kiểm:** “Đối với identities trong inventory production, action ngoài allowlist của từng vai trò phải bị deny tại effective permissions và/hoặc policy enforcement theo tiêu chí, bao gồm đường support/break-glass được định nghĩa.”

Tiêu chí tốt có negative condition: **những hành vi nào nếu thành công sẽ chứng minh control FAIL**. Nó cho phép thiết kế test phù hợp và tránh diễn giải tùy tiện sau khi thấy kết quả.

## 8. Từ Requirement sang Control: Thiết kế và vận hành

Một control không chỉ là policy đã được viết; phải xác định **cách nó hoạt động và những giả định để nó bảo vệ đúng rủi ro**.

| Control class | Minh họa | Điều cần chứng minh |
|---|---|---|
| **Preventive** | Server-side resource authorization; chặn public bucket; MFA. | Đường trái quyền bị chặn trong scope. |
| **Detective** | Audit logs, alert on privilege escalation, EDR. | Event cần thiết được sinh, nhận và xử lý. |
| **Corrective** | Revoke quyền, remediation workflow, patch/restore. | Hành động thực sự sửa trạng thái và được retest. |
| **Recovery** | Backup, immutable copies, DR failover. | Dữ liệu/dịch vụ phục hồi được trong điều kiện kiểm thử. |
| **Administrative/governance** | Review quyền, change approval, risk acceptance. | Quyết định đúng quyền và được thực thi; không tự chứng minh hiệu quả kỹ thuật. |
| **Compensating** | Bastion MFA + chặn direct access cho hệ thống legacy. | Mục tiêu rủi ro được giảm bằng tests, hạn chế và quyền sử dụng được phép. |

### 8.1. Phân biệt ba mức kiểm chứng

1. **Control designed:** thiết kế nhằm đạt mục tiêu, assumptions và các đường phụ thuộc đã được review.
2. **Control implemented:** cấu hình/code/process thực sự được triển khai trên scope.
3. **Control operating effectively:** control hoạt động đúng theo test, trong phạm vi và kỳ được đánh giá.

Một PR đã merge hỗ trợ việc thay đổi source; một screenshot rule **enabled** hỗ trợ sự tồn tại của cấu hình; cả hai chưa đủ chứng minh effective runtime behavior.

### 8.2. Defense in depth nhưng không cộng PASS tùy tiện

Ví dụ WAF chặn một mẫu request không thay được server-side tenant authorization nếu requirement yêu cầu kiểm tra ownership tại ứng dụng. WAF có thể giảm rủi ro cho một tập đường tấn công, nhưng cần đánh giá bypass, error handling và những trường hợp WAF không quan sát. Không mặc định **hai control yếu tạo thành một control mạnh** nếu không có luận cứ.

## 9. Từ Control sang Test: Thiết kế phép kiểm tra hợp lệ

Chất lượng test quyết định evidence có thực sự hỗ trợ claim hay không. Cần viết rõ **claim cần chứng minh, scope, preconditions, expected và actual outcome**.

### 9.1. Test matrix cho một ứng dụng SaaS

| Test ID | Control/requirement | Method / kỳ | Expected | Khi nào FAIL? |
|---|---|---|---|---|
| **T-AUTH-01** | CTRL-AUTH-01 / REQ-AUTH-01 | Authenticated tenant A yêu cầu hóa đơn của A. | PASS nghiệp vụ, trả đúng resource. | Luồng hợp lệ bị chặn hoặc dữ liệu sai. |
| **T-AUTH-02** | CTRL-AUTH-01 / REQ-AUTH-01 | Tenant A yêu cầu hóa đơn của B, với test data an toàn. | Deny; không lộ dữ liệu B. | Trả dữ liệu hoặc thực hiện action trái quyền. |
| **T-DATA-03** | CTRL-DATA-02 / REQ-DATA-02 | Anonymous read vào object test trong production-like scope phù hợp. | Deny theo policy. | Anonymous GET được phép. |
| **T-IAM-04** | CTRL-IAM-03 / REQ-IAM-03 | Effective service role: allowed/denied operations. | Nghiệp vụ cần thiết PASS; ngoài quyền DENY. | Wildcard cho phép thao tác ngoài scope. |
| **T-LOG-05** | CTRL-LOG-04 / REQ-LOG-04 | Synthetic audit event từ nguồn tới SIEM. | Đủ attributes, nhận đúng hạn, tìm lại được. | Event có ở nguồn nhưng không tới đích theo tiêu chí. |
| **T-DR-06** | CTRL-DR-05 / REQ-DR-05 | Restore/decrypt backup test. | Data integrity, key access, recovery time đạt mục tiêu. | Restore fail hoặc vượt tiêu chí được ban hành. |

### 9.2. Các thuộc tính một test record phải có

- Test ID, method version, tester/collector, authorization cho phép thử.
- Source revision/image digest/config version, asset IDs, environment và thời gian.
- Input là test data được phép; không dùng dữ liệu khách hàng thật khi không cần.
- Expected/actual outcomes, PASS/FAIL/SKIP/ERROR/INCONCLUSIVE.
- Coverage: bao nhiêu trong target population, những đường nào chưa thử.
- Raw result reference, timestamp, tool version và limitations.
- Reviewer giải thích liệu test có đủ đại diện cho production/period không.

**SKIP hoặc ERROR không được tự ghi PASS**. Một test PASS trên staging khác IAM/tenant routing của production có thể chỉ hỗ trợ một phần claim và cần đánh giá environment delta.

## 10. Từ Test sang Evidence: Dữ liệu phải có nguồn, scope và thời gian

**Evidence** là thông tin được thu từ quan sát, cấu hình, hành vi, log, test, phê duyệt hoặc tài liệu phù hợp. Evidence tốt không chỉ là nhiều file; phải **relevant, authentic, complete, timely, integrity-protected và có thể giải thích**.

### 10.1. Một evidence manifest chuẩn hóa

| Field | Ý nghĩa |
|---|---|
| **evidence_id** | ID ổn định để liên kết control/test/finding. |
| **source_system/resource_locator** | Nguồn nào, tenant/account/region/asset nào. |
| **observed_at / collected_at_utc** | Thời gian trạng thái xảy ra và thời điểm xuất dữ liệu. |
| **collector_id / test_run / tool_version** | Ai, bằng gì, với quyền gì thu dữ kiện. |
| **scope / population / coverage** | Đối tượng nào đã test, đối tượng nào chưa. |
| **method / inputs / expected / actual** | Có thể tái lập phép kiểm tra và hiểu kết quả. |
| **raw_artifact_ref** | Vị trí bản gốc được bảo vệ. |
| **normalization / derived_ref** | Các phép biến đổi, bộ lọc, query version. |
| **digest / object version** | Dấu hiệu kiểm tra thay đổi sau khi chốt. |
| **classification / retention** | Quyền xem và thời gian lưu theo policy. |
| **reviewer / limitations** | Người xem xét và ranh giới suy luận. |

### 10.2. Provenance khác với “file có hash”

Một file CSV thiếu 20 cloud accounts vẫn có SHA-256 hợp lệ. Hash giúp phát hiện file bị thay đổi **sau mốc đáng tin**, không xác minh scanner đã export đầy đủ, không chứng minh collector đủ quyền và không tự chứng minh nội dung là sự thật.

Để kiểm tra **completeness**, cần so asset inventory, API pagination, error codes, access scopes, event source/collector health và những records bị filter. Để kiểm tra **timeliness**, so snapshot với change events sau thời điểm chụp. Để kiểm tra **authenticity**, xem source identity, pipeline trust và audit trail.

### 10.3. Bảo vệ chính evidence

Security evidence có thể chứa sơ đồ mạng, access paths, vulnerability details, thông tin cá nhân và tài khoản đặc quyền. Áp dụng **least privilege, phân loại, mã hóa, versioning/immutable storage khi phù hợp, retention và audit access**. Không dán plaintext secrets, tokens hoặc private keys vào ticket/report.

## 11. Từ Evidence sang Assurance Claim: Grounds, Warrant và Limitation

Một **claim** là điều tổ chức muốn khẳng định. **Grounds/evidence** là dữ kiện hỗ trợ. **Warrant** là quy tắc giải thích **vì sao evidence có thể dẫn tới claim**. **Backing** củng cố warrant bằng phương pháp/kiến trúc/yêu cầu; **assumptions, qualifier và defeater** cho biết ranh giới và điều có thể làm lập luận sai.

### 11.1. Ví dụ một lập luận có giới hạn

- **Claim:** Trong phiên bản API R, hai đường lấy hóa đơn đã kiểm **không còn trả hóa đơn của tenant khác** tại thời điểm retest.
- **Grounds:** T-AUTH-02 chạy trên image digest H, effective route map, request/response của hai endpoints với nhiều cặp tenants thử nghiệm.
- **Warrant:** Nếu server xác thực principal và kiểm tra resource ownership tại đường xử lý áp dụng, các negative tests có test accounts/data hợp lệ phản ánh việc enforcement hoạt động trên những đường đã kiểm.
- **Backing:** Review implementation, route inventory, kiểm tra policy và test method đã được phê duyệt.
- **Assumptions:** Artifact runtime đúng digest H; không có đường bypass khác trong scope; identity/tenant mapping của test đúng.
- **Defeaters:** Endpoint mới, tenant routing khác, role bypass, emergency config hoặc token/session path ngoài kiểm thử.
- **Qualifier:** PASS trên tập đường được kiểm ở mốc T; **chưa đủ kết luận toàn bộ hệ thống vĩnh viễn an toàn**.

### 11.2. Cấu trúc assurance case

~~~mermaid
flowchart TD
    G["Goal / Claim: control đạt trong scope"] --> STR["Strategy: tách các đường truy cập và điều kiện"]
    STR --> S1["Subclaim 1: danh mục endpoints đầy đủ"]
    STR --> S2["Subclaim 2: unauthorized requests bị từ chối"]
    STR --> S3["Subclaim 3: legitimate requests vẫn hoạt động"]
    STR --> S4["Subclaim 4: deployment là đúng artifact đã test"]
    S1 --> E1["Route inventory + reconciliation"]
    S2 --> E2["Negative test evidence"]
    S3 --> E3["Positive regression evidence"]
    S4 --> E4["Observed digest + approval"]
    A["Assumptions, warrant, backing và rebuttals"] --> G
~~~

Một screenshot “200 tests passed” chỉ có thể hỗ trợ claim nếu 200 tests **đủ liên quan và đúng điều kiện**. Khi inventory thiếu, phần claim về toàn bộ endpoint có thể **INCONCLUSIVE** dù các đường đã thử đều PASS.

## 12. Bốn verdict cần dùng đúng: PASS, FAIL, INCONCLUSIVE và NOT_APPLICABLE

| Verdict | Khi dùng | Ví dụ |
|---|---|---|
| **PASS** | Bằng chứng đủ chất lượng, đúng scope/time chứng minh tiêu chí được đáp ứng. | Unauthorized request bị chặn trên tất cả endpoints trong scope đã reconciliation, test phù hợp. |
| **FAIL** | Có bằng chứng đáng tin rằng một tiêu chí áp dụng không được đáp ứng. | Test trả dữ liệu của tenant B cho tenant A. |
| **INCONCLUSIVE** | Không đủ evidence, thiếu coverage, source lỗi, phép thử không đại diện hoặc claim chưa rõ. | Collector không có quyền đọc account mới; không thể xác minh audit logs. |
| **NOT_APPLICABLE** | Requirement không áp dụng theo nguồn và scope đã xác minh, có căn cứ. | Rule cho một loại dữ liệu được xác nhận không nằm trong service đang xét. |

### 12.1. Các lỗi suy luận cần cấm

- “Không thấy alert” **không đồng nghĩa** “không có tấn công” nếu logging/coverage thiếu.
- “Không thấy vulnerability” **không đồng nghĩa** “không có lỗi” ngoài giới hạn scanner.
- “Exception đã được duyệt” **không đồng nghĩa** control gốc PASS.
- “Risk score đã hạ” **không đồng nghĩa** remediation đã hoàn tất.
- “Change approved” **không đồng nghĩa** runtime đã đúng hoặc post-deploy tests PASS.
- “Vendor có báo cáo audit” **không đồng nghĩa** tenant configuration của khách hàng được kiểm.
- “Có backup” **không đồng nghĩa** restore đạt RTO/RPO.

Khi kết luận thiếu evidence, **INCONCLUSIVE là một phát hiện hữu ích**. Nó phải dẫn tới yêu cầu thu thập thêm, owner và thời hạn/escalation, không bị gộp vào xanh để làm đẹp KPI.

## 13. Risk assessment được cập nhật lại từ Evidence như thế nào?

Luồng không kết thúc ở PASS/FAIL. Evidence mới có thể làm đổi **khả năng xảy ra, mức tác động, tính hiệu lực controls, confidence hoặc phạm vi**. Đây là vòng phản hồi risk-to-evidence-to-risk.

### 13.1. Ví dụ từng mốc

| Mốc | Evidence mới | Risk interpretation |
|---|---|---|
| **T0: initial discovery** | Threat model nghi vấn thiếu tenant authorization trên API. | Risk scenario mở, exposure/likelihood provisional. |
| **T1: initial test** | Negative test cho thấy 2 endpoints trả dữ liệu khác tenant. | Control FAIL confirmed trên paths đã test; priority tăng theo dữ liệu và access. |
| **T2: containment** | Affected routes tạm tắt an toàn, gateway deny tests đạt. | Exposure giảm trong scope nếu kiểm chứng; root cause chưa fixed. |
| **T3: permanent fix** | Code mới deployed qua approved release, route tests PASS. | Có thể reassess current/control effectiveness theo scope và artifact. |
| **T4: independent retest** | Full route inventory reconciled, negative/positive tests và audit events PASS. | Có cơ sở VERIFIED_CLOSED cho finding theo tiêu chí; residual risk cần owner review. |
| **T5: service expands** | Region hoặc endpoint mới, identity policy đổi. | Đánh giá lại assumption và applicability; không giữ PASS cũ cho scope mới. |

### 13.2. Đừng dùng score như nút “Đã sửa”

Một kịch bản từ 20 Critical dự kiến xuống 10 High sau fix **không nên được báo High hiện tại** khi action chưa hoàn thành. Sau retest, risk owner có thể đánh giá rủi ro còn lại khác mức dự kiến dựa trên bằng chứng. Cần lưu **original score, method version, rationale, reassessed_at, evidence IDs và approval**.

## 14. Case study xuyên suốt: Từ Risk chéo tenant tới Evidence kiểm chứng

Xét nền tảng SaaS giả định **Orchid Invoice**, nơi nhiều khách hàng dùng chung ứng dụng API. Mục tiêu là cô lập dữ liệu theo tenant. Nhóm phát triển dự kiến phát hành một chức năng xem hóa đơn mới.

### 14.1. Bước A — Xác định assets và rủi ro

- **ASSET-01:** Invoice API production, có endpoint GET invoice.
- **ASSET-02:** Invoice database, chứa dữ liệu liên hệ và hóa đơn thuộc tenants khác nhau.
- **ASSET-03:** IdP/authorization service.
- **ASSET-04:** Gateway/WAF.
- **ASSET-05:** Audit log pipeline.
- **RISK-01:** Người dùng tenant A lấy hóa đơn tenant B do thiếu server-side ownership check.
- **Threat context:** API có thể gọi từ Internet sau xác thực; attacker cần tài khoản hợp lệ nhưng không cần quyền tenant B.

Bằng chứng chưa có ban đầu: chưa rõ endpoint nào thiếu check, chưa biết route inventory đầy đủ. Risk assessment ở trạng thái **PROVISIONAL**, không khẳng định đã có breach.

### 14.2. Bước B — Security objective và requirements

| Object | ID | Diễn giải |
|---|---|---|
| Security objective | OBJ-TENANT-01 | Dữ liệu hóa đơn được truy cập đúng tenant/role. |
| Requirement | REQ-TENANT-01 | Mọi API truy xuất hóa đơn phải check ownership server-side. |
| Control | CTRL-TENANT-01 | Authorization enforcement ở service/data access layer. |
| Control hỗ trợ | CTRL-LOG-02 | Ghi audit cho các truy cập và deny events theo scope quy định. |
| Test | TEST-AUTH-NEG-01 | Cross-tenant request phải trả deny, không trả invoice B. |
| Test | TEST-AUTH-POS-01 | Tenant hợp lệ vẫn xem hóa đơn của mình. |
| Test | TEST-LOG-01 | Audit event từ API tới SIEM được tìm lại. |

### 14.3. Bước C — Evidence ban đầu và finding

Giả định test T0 kiểm 6 endpoints: **2 endpoints không từ chối yêu cầu trái tenant**; 4 endpoints xử lý đúng trong test. Test sử dụng synthetic data và hai tenant accounts được phép.

**Bằng chứng:** request IDs, image digest, endpoint inventory phiên bản thử nghiệm, actual response được redacted, tester, thời điểm, tool version, CI run và raw artifact link.

**Kết luận đúng:** CTRL-TENANT-01 **FAIL trên hai paths được xác minh**. Chưa có đủ cơ sở nói mọi endpoint đều sai hoặc cả ứng dụng đã bị tấn công. **Finding FIND-TENANT-01** được mở; risk exposure được đánh giá lại, chọn containment khi phù hợp.

**Kết luận sai:** “4/6 endpoints PASS, nên 67% hệ thống an toàn”; những endpoints không tương đương về độ nhạy cảm và một đường đọc dữ liệu khác tenant có thể là blocking failure.

### 14.4. Bước D — Risk treatment và quyết định phát hành

| Trục | Quyết định/hành động |
|---|---|
| **Immediate containment** | Giới hạn/tạm tắt hai paths lỗi qua change có quyền; kiểm tra negative deny và legitimate flows. |
| **Permanent remediation** | Bổ sung server-side ownership authorization cho các routes, không chỉ WAF rule. |
| **Test expansion** | Reconcile API inventory, nhiều tenant pairs, roles, tokens, service/admin paths. |
| **Operational safeguards** | Audit logging, alerts và incident triage nếu access logs cho thấy nghi vấn khai thác. |
| **Release gate** | Không GO cho scope còn FAIL khi mandatory authorization requirement chưa đáp ứng. |
| **Authority** | Security reviewer xác minh control, change/release authority duyệt triển khai, risk owner quyết định rủi ro trong giới hạn. |
| **Residual risk** | Reassess sau verified remediation; không tự ghi “Accepted” khi chưa có quyết định đúng quyền. |

Nếu hợp đồng hoặc nghĩa vụ pháp luật không cho phép kiểu deviation ấy, một **risk acceptance nội bộ không thay đổi nghĩa vụ**. Cần đánh giá riêng, không dùng waiver làm đường tắt phát hành.

### 14.5. Bước E — Retest và assurance claim cuối

Sau khi triển khai bản fix có digest H2:

1. Xác minh observed runtime image/manifest đúng H2 và đúng environment.
2. Kiểm tra inventory toàn bộ invoice endpoints được xác định trong scope.
3. Chạy **negative tests** với tài khoản tenant khác cho từng route cần bảo vệ.
4. Chạy **positive tests** bảo đảm luồng hợp lệ hoạt động.
5. Xác minh đường đặc quyền, background job, support access và error handling nếu nằm trong scope.
6. Kiểm tra audit logs được tạo và đến nơi nhận theo tiêu chí.
7. Đối chiếu finding, release ID, test runs, evidence digest, reviewer sign-off.
8. Xác định remaining assumptions và các điều kiện làm mất hiệu lực.

Nếu toàn bộ gates đạt, có thể kết luận **“Control đạt trong phạm vi và tại mốc retest được ghi”**, đóng finding theo quy trình và cập nhật verified residual assessment. **Không tự suy hệ thống không còn mọi lỗi hoặc toàn bộ các kỳ trước đều PASS**.

## 15. Traceability graph: Làm sao tránh đứt đoạn quan hệ?

Một hệ thống assurance trưởng thành cần **các ID và liên kết có kiểu quan hệ** thay vì chỉ một tài liệu mô tả bằng văn xuôi.

~~~mermaid
flowchart LR
    R["RISK-01"] -->|threatens| O["OBJ-TENANT-01"]
    O -->|specified_by| Q["REQ-TENANT-01"]
    Q -->|implemented_by| C["CTRL-TENANT-01"]
    C -->|tested_by| T["TEST-AUTH-NEG-01"]
    T -->|produces| E["EVID-AUTH-01"]
    E -->|supports/contradicts| V["VERDICT-CTRL-01"]
    V -->|informs| F["FIND-TENANT-01"]
    F -->|addressed_by| A["ACTION-TENANT-01"]
    A -->|verified_by| RT["RETEST-TENANT-02"]
    RT -->|updates| V
    V -->|feeds| R
~~~

### 15.1. Một số quan hệ cần chuẩn hóa

| Edge | Ý nghĩa | Ví dụ |
|---|---|---|
| **threatens** | Risk đe dọa objective hoặc tài sản. | RISK-01 threatens OBJ-TENANT-01. |
| **specified_by** | Objective được cụ thể bằng requirement. | OBJ-TENANT-01 specified_by REQ-TENANT-01. |
| **implemented_by** | Requirement được control hiện thực. | REQ-TENANT-01 implemented_by CTRL-TENANT-01. |
| **tested_by** | Control/requirement được kiểm bằng test. | CTRL-TENANT-01 tested_by TEST-AUTH-NEG-01. |
| **produces** | Test/collector sinh evidence. | TEST-AUTH-NEG-01 produces EVID-AUTH-01. |
| **supports / contradicts** | Evidence ủng hộ hoặc phủ định claim trong scope. | Test FAIL contradicts claim of enforcement. |
| **detected_as** | Control gap được ghi thành finding. | CTRL-TENANT-01 detected_as FIND-TENANT-01. |
| **addressed_by** | Finding/risk được action xử lý. | FIND-TENANT-01 addressed_by ACT-TENANT-01. |
| **verified_by** | Action/fix được retest kiểm chứng. | ACT-TENANT-01 verified_by RETEST-TENANT-02. |
| **accepted_by / authorized_by** | Risk decision hoặc ngoại lệ có người quyết định. | RISK-01 accepted_by DEC-RISK-01 nếu có. |

Từ một rủi ro, người đánh giá phải đi được tới bằng chứng; từ một bằng chứng, phải biết **nó được dùng để hỗ trợ kết luận nào**. Thiết kế quan hệ nhiều–nhiều và versioned, tránh việc sửa một control ID làm mất toàn bộ dấu vết lịch sử.

### 15.2. Quy tắc tính nhất quán

- Không có evidence nào được dùng để PASS control nếu chưa gắn **test/assessment method và scope** thích hợp.
- Không đóng finding chỉ vì action ticket **DONE** nếu required retest chưa có.
- Không tự đánh dấu risk ACCEPTED khi **risk decision/authority/expiry** thiếu.
- Không dùng test trên artifact A cho claim của artifact B nếu chưa có lý do chứng minh đại diện.
- Không tự loại risk khỏi register vì control chưa có owner hoặc evidence source mất quyền.
- Không cho verdict PASS cho target population nếu chỉ có sample nhỏ ngoài tiêu chí cho phép suy rộng.

## 16. Schema tối thiểu cho một bộ hồ sơ liên kết

Một tổ chức có thể sử dụng nhiều hệ thống khác nhau. Sơ đồ bảng logic dưới đây đủ để hình dung quan hệ.

~~~text
RISK(id, scenario, assets, impact, likelihood, confidence,
     owner, assessed_at, risk_method_version, state)
OBJECTIVE(id, statement, business_process, scope)
REQUIREMENT(id, objective_id, source, source_version,
            applicability, criteria)
CONTROL(id, design, owner, implementation_scope, status)
ASSESSMENT(id, control_id, test_id, source_revision,
           population, observed_at, verdict, limitations)
EVIDENCE(id, assessment_id, source, collector, raw_ref,
         digest_ref, collected_at, data_quality, classification)
CLAIM(id, requirement_id, scope, period, warrant,
      backing, assumptions, verdict, reviewer)
FINDING(id, control_id, evidence_ids, severity, opened_at, state)
ACTION(id, finding_id, owner, method, due_at, status)
RETEST(id, action_id, assessment_id, verdict, reviewer)
DECISION(id, risk_id, authority, choice, conditions, expiry, version)

Link tables or typed edges connect many-to-many relationships.
Historical records use versions/time; do not overwrite past verdicts.
~~~

Mỗi bảng có thể trở thành document, ticket, database row hoặc graph node. Những trường trạng thái có thể khác tên trong công cụ thật, nhưng phải giữ **semantics**, scope, time và thẩm quyền.

### 16.1. Quy tắc versioning

Risk scoring method, requirement version, scanner rule, test method, source revision, control implementation và decision đều có thể thay. Nếu chỉ ghi bản mới nhất mà không giữ lịch sử, một auditor không thể tái dựng vì sao release tháng trước được cho phép.

## 17. Mẫu YAML minh họa cho một đường Risk-to-Evidence

Đây là **mẫu học tập tự chứa**, không phải schema chuẩn của ISO/NIST/PCI hoặc GRC cụ thể. Dữ liệu, ID và kết quả giả định. Mẫu cố ý chứa **control failure đã xác nhận** trong scope hẹp, **target remediation chưa verified**, và **kết luận toàn bộ API còn cần evidence**.

~~~yaml
assurance_trace:
  trace_id: "RISK-EVIDENCE-EXAMPLE-002"
  version: "1.0"
  module: "SECURITY_SECURITY_ASSURANCE"
  chapter: "Tổng kết security assurance"
  topic: "Luồng từ risk đến evidence"
  service: "orchid-invoice"
  environment: "production-like-lab"
  assessment_as_of_utc: "2026-11-28T05:00:00Z"

context:
  business_process: "Multi-tenant invoice viewing"
  assets: ["ASSET-01", "ASSET-02", "ASSET-03"]
  data_classification: "CUSTOMER_CONFIDENTIAL"
  target_scope: "All invoice read endpoints and supported identities"
  observed_scope: "Six sampled endpoints, two tenant test accounts"
  scope_reconciled: false
  external_obligations: "APPLICABILITY_REVIEW_REQUIRED"

risk:
  risk_id: "RISK-01"
  scenario: >
    A tenant user may access another tenant's invoice when server-side
    ownership authorization is missing on an affected API route.
  owner: "Customer Data Business Risk Owner"
  assessed_at_utc: "2026-11-28T05:00:00Z"
  methodology_version: "LAB-RISK-5X5-v1"
  current:
    likelihood: 4
    impact: 5
    score: 20
    tier: "CRITICAL"
    confidence: "MEDIUM_FOR_ENTIRE_API_SCOPE"
  projected_target_after_fix:
    likelihood: 2
    impact: 5
    score: 10
    tier: "HIGH"
    status: "NOT_VERIFIED"
  verified_residual:
    status: "NOT_ASSESSED"
    score: null

objective:
  objective_id: "OBJ-TENANT-01"
  statement: "Tenant invoice data must be isolated by authorization"

requirement:
  requirement_id: "REQ-TENANT-01"
  source: "INTERNAL-SECURITY-STANDARD-EXAMPLE"
  source_version: "v1"
  applicability: "IN_SCOPE"
  criterion: >
    Every invoice-read path must enforce server-side resource ownership
    for the authenticated principal and tenant.

control:
  control_id: "CTRL-TENANT-01"
  owner: "Application Security Owner"
  design: "Per-resource ownership enforcement in invoice service"
  implementation_claim: "DEPLOYED_BUT_INEFFECTIVE_ON_SAMPLED_PATHS"
  operating_effectiveness: "FAIL_ON_CONFIRMED_PATHS"

assessment:
  assessment_id: "ASSESS-TENANT-01"
  method_version: "NEGATIVE-ACCESS-TEST-v2"
  source_artifact_digest_ref: "restricted/assurance-002/image-digest"
  test_population:
    sampled_endpoints: 6
    endpoints_with_confirmed_failure: 2
    total_endpoints: "NOT_RECONCILED"
  performed_at_utc: "2026-11-28T04:00:00Z"
  test_cases:
    - test_id: "TEST-AUTH-NEG-01"
      expected: "Unauthorized cross-tenant read denied"
      actual: "Two tested endpoints returned an unauthorized invoice"
      verdict: "FAIL"
    - test_id: "TEST-AUTH-POS-01"
      expected: "Authorized same-tenant read succeeds"
      actual: "Passed on sampled paths"
      verdict: "PASS_ON_TESTED_SCOPE"

evidence:
  evidence_id: "EVID-AUTH-01"
  produced_by: "ASSESS-TENANT-01"
  raw_ref: "restricted/assurance-002/test-run-001"
  collector: "Security Test Runner"
  source_system: "Authorized lab API endpoint"
  collected_at_utc: "2026-11-28T04:05:00Z"
  completeness: "PARTIAL_ENDPOINT_COVERAGE"
  integrity_ref: "restricted/assurance-002/digests/test-run-001"
  classification: "CONFIDENTIAL"
  limitations:
    - "No assertion of exploitation by real attacker"
    - "No claim about untested endpoints"

claim_and_reasoning:
  claim: "Invoice ownership enforced for the complete API scope"
  claim_verdict: "FAIL_FOR_GLOBAL_REQUIREMENT"
  grounds: ["EVID-AUTH-01"]
  warrant: >
    A successful unauthorized read on an in-scope endpoint contradicts
    the requirement that every invoice-read path enforce ownership.
  backing: ["REQ-TENANT-01", "NEGATIVE-ACCESS-TEST-v2"]
  assumptions:
    - "Test identities and tenant mapping are valid"
    - "Response data belongs to the unauthorized tenant"
  qualifier: "Failure confirmed for two sampled paths"
  unresolved_questions:
    - "Total endpoint population and historical impact"
  reviewed_by: "Security Assurance Reviewer"

finding_and_treatment:
  finding_id: "FIND-TENANT-01"
  state: "OPEN"
  confirmed_control_gap: true
  treatment: "MITIGATE_AND_REMEDIATE"
  containment: "Restrict affected paths under approved change procedure"
  permanent_action: "Enforce ownership across all invoice routes"
  action_owner: "Invoice API Engineering Owner"
  required_retests:
    - "Full route inventory reconciliation"
    - "Cross-tenant deny tests for in-scope routes"
    - "Authorized invoice access regression"
    - "Effective deployment digest check"
  required_retest_status: "PENDING"
  closure_condition: "Independent tests meet all defined criteria"
  risk_acceptance_state: "NOT_APPROVED"

assurance_decision:
  current_control: "FAIL"
  coverage_for_full_api: "INCONCLUSIVE"
  exception_authorization: "NOT_PRESENT"
  verified_remediation: "NOT_YET"
  release_recommendation: "NO_GO_WHILE_MANDATORY_GATE_FAILS"
  authorized_release_decision: "PENDING_CHANGE_AUTHORITY"
  next_assessment_triggers:
    - "authorization-fix-deployed"
    - "new-invoice-route"
    - "tenant-identity-mapping-change"
    - "new-security-finding"

governance:
  evidence_vault: "restricted-security-assurance"
  decision_history_preserved: true
  source_and_method_versions_preserved: true
~~~

### 17.1. Vì sao “FAIL” và “INCONCLUSIVE” có thể cùng đúng?

- **Yêu cầu “mọi đường invoice đều phải bảo vệ” đã FAIL** khi có ít nhất một in-scope endpoint trả dữ liệu chéo tenant; không cần quét đủ tất cả để xác nhận tồn tại phản ví dụ.
- **Độ phủ đánh giá toàn bộ endpoints vẫn INCONCLUSIVE** vì chưa reconcile route population. Không thể kết luận mức độ lỗi rộng đến đâu.
- **Risk score current là assessment có rationale**, không phải bằng chứng đã có breach; target sau fix chỉ là estimate.
- **Release recommendation NO-GO** không thay cho quyết định có thẩm quyền, nhưng chỉ rõ mandatory gate đang thất bại.
- **Closure pending** cho đến khi control và phạm vi được retest.

Đây là điểm quan trọng của luồng risk-to-evidence: **một evidence có thể đủ bác bỏ một mệnh đề “mọi đối tượng đều đạt”, đồng thời chưa đủ để khẳng định tỷ lệ/độ rộng của thất bại**.

## 18. Khi một Risk có nhiều Controls và nhiều Evidence sources

Không phải mọi risk đều có một control duy nhất. Với risk mất khả năng điều tra sự cố, ít nhất ba lớp có thể liên quan:

| Layer | Control | Bằng chứng | Giới hạn |
|---|---|---|---|
| **Source generation** | Ứng dụng/database sinh audit event đúng schema, timestamp và actor. | Source audit event và test generator. | Không chứng minh event đã tới SIEM. |
| **Transport/collection** | Agent/collector nhận và chuyển event theo target latency. | Collector health, queue metrics, synthetic trace. | Không chứng minh mọi source đang được onboard. |
| **Retention & integrity** | Kho lưu được bảo vệ và giữ đủ theo policy. | Retention policy, object versions, access tests. | Một cấu hình retention không chứng minh quá khứ không có gap. |
| **Detection/response** | Alert rule hoạt động, on-call nhận và xử lý theo tiêu chí. | Synthetic alert, ticket/action timeline. | ACK không tự chứng minh containment hoặc điều tra đầy đủ. |

Một claim “logging đầy đủ suốt tháng” phải có **dữ liệu lịch sử coverage và pipeline health**, không chỉ synthetic event hiện tại. Nếu source event có nhưng SIEM không nhận trong cửa sổ đã định, end-to-end control có thể FAIL trên đường được thử. Nếu source/API không truy cập được, trạng thái có thể INCONCLUSIVE; phân loại khác nhau giúp hành động đúng.

### 18.1. Evidence dùng chung nhưng claim không giống nhau

Một log event có thể hỗ trợ “control tạo audit” và “incident actor đã thao tác” trong scope phù hợp, nhưng **không tự chứng minh** rằng toàn bộ hành động của actor đã được ghi hoặc alert đã được xử lý. Khi tái sử dụng, giữ quan hệ evidence-to-claim và interpretation riêng.

## 19. Finding → Remediation → Retest: Khép vòng có bằng chứng

Security assurance phát hiện vấn đề nhưng không đưa tới hành động chỉ là báo cáo. Cần nối findings với một plan và **tiêu chí kiểm chứng đầu ra**.

~~~mermaid
flowchart TD
    F["Confirmed finding / evidence gap"] --> T["Risk triage + root cause"]
    T --> M["Containment/compensating controls nếu phù hợp"]
    T --> P["Action plan: owner, scope, dependency, due"]
    P --> CH["Change/release approved đúng revision"]
    CH --> DEP["Implementation + execution evidence"]
    DEP --> RET["Independent retest original requirement"]
    RET --> V{"Đạt toàn bộ acceptance criteria?"}
    V -->|Không| R["Reopen/replan; risk reassessment"]
    R --> P
    V -->|Có| C["Verified closure + residual risk review"]
    M --> MON["Monitor điều kiện và expiry"]
    MON --> R
    C --> MON
~~~

### 19.1. Những trạng thái phải phân biệt

- **Finding OPEN:** control chưa đạt hoặc evidence gap đang chờ xử lý.
- **Action PLANNED/IN_PROGRESS:** công việc đang thực hiện, không giảm risk nếu chưa có control hiệu lực.
- **Mitigation VERIFIED:** giảm phơi nhiễm một phần, có test; có thể không loại root cause.
- **Fix DEPLOYED:** thay đổi đã lên runtime, chưa đồng nghĩa control PASS.
- **Retest PASS/FAIL/INCONCLUSIVE:** kết quả kiểm chứng tiêu chí gốc.
- **Finding VERIFIED_CLOSED:** đóng theo policy khi đủ evidence và reviewer sign-off.
- **Risk ACCEPTED_WITH_CONDITIONS:** quyết định quản trị rủi ro có quyền/hạn, không phải fix.
- **External compliance:** đánh giá riêng, không tự đổi PASS từ sự hiện diện của waiver nội bộ.

### 19.2. Khi nào phải retest đầy đủ?

Nếu root cause sửa ở middleware chung, cần review route inventory, backward compatibility và bypass paths; một test trên endpoint từng lỗi chưa đủ nếu control objective áp dụng cả API. Retest phải dùng **đúng artifact đã deploy, đúng environment và dữ liệu test được phép**.

## 20. Exceptions, risk acceptance và compliance trong luồng Risk-to-Evidence

Một thay đổi không thể sửa ngay có thể tạo **security exception** nếu đúng nguồn yêu cầu cho phép. Điều đó cần hồ sơ riêng: deviation, risk scenario, effective mitigation, scope, owner, authority, expiry, monitoring và remediation target.

| Trục | Ví dụ trạng thái | Ý nghĩa |
|---|---|---|
| **Original requirement effectiveness** | FAIL | Control gốc chưa đạt. |
| **Compensating control** | PASS_ON_TESTED_SCOPE | Một biện pháp giảm rủi ro đã có test nhưng có giới hạn. |
| **Exception authorization** | ACTIVE_VALID_UNTIL_T | Có quyền vận hành lệch theo điều kiện, chưa tự làm control PASS. |
| **Risk decision** | ACCEPTED_WITH_CONDITIONS | Chủ thể có quyền chấp nhận một residual risk có giới hạn. |
| **Permanent fix** | PENDING_RETEST | Chưa có bằng chứng đóng khoảng lệch. |
| **External obligation** | INCONCLUSIVE | Pháp lý/hợp đồng cần review riêng, không tự coi được miễn. |

Một register tốt vẫn giữ **original finding, original due date, lịch sử gia hạn, rủi ro được chấp nhận và những giai đoạn ngoài hiệu lực**. Không xoá rủi ro khỏi dashboard chỉ vì hồ sơ exception tồn tại.

### 20.1. Điểm quyết định có thể là NO-GO

Khi một requirement bắt buộc FAIL và không có cơ chế hợp lệ cho phép lệch, risk owner nội bộ có thể **không có quyền** cho release hoặc vận hành trái nghĩa vụ. Đường xử lý là sửa, giảm scope, đổi thiết kế, hạn chế tính năng hoặc tìm thẩm quyền theo quy định; không gắn nhãn “accepted” để lách.

## 21. Từ Evidence tới Release/Change Assurance

Một kết quả security test chỉ dùng cho release nếu có thể xác định **test chạy trên candidate nào và candidate nào thực sự triển khai**.

### 21.1. Chốt liên kết cần có

~~~text
change_id / release_id
  -> approved source revision
  -> build pipeline run
  -> artifact digest / manifest version
  -> required security test runs
  -> known findings and accepted exceptions
  -> risk/approval decision with conditions
  -> observed production deployment digest
  -> post-change verification results
~~~

Nếu test chạy trên digest H1 nhưng deploy H2, decision có thể cần được xem lại dù version tag giống nhau. Nếu deployment mở region/tenant mới, scope và evidence có thể không còn đại diện. Cần reapproval triggers và cơ chế dừng rollout theo policy.

### 21.2. Pre-change, post-change và continuous evidence

| Thời điểm | Claim được xem xét | Ví dụ |
|---|---|---|
| **Trước thay đổi** | Scope, baseline, risk, tests và rollback readiness đủ để xem xét GO? | IAM diff, current state, integration tests và approved plan. |
| **Trong triển khai** | Có triển khai đúng artifact/procedure, có drift hoặc lỗi? | Deployment run, artifact digest, change events, staged rollout. |
| **Sau thay đổi** | Control hoạt động thực trên target? | Effective IAM, API negative tests, audit log synthetic checks. |
| **Trong vận hành** | Claim có còn hiệu lực sau new events/threats? | Drift detector, new asset, CVE, exceptions expiry, alert health. |

**Approval record** là bằng chứng về quyết định đúng thẩm quyền, không tự chứng minh production PASS. **Post-change retest** là evidence cần để khẳng định hiệu lực ở trạng thái mới.

## 22. Third-party, Audit và Evidence outside your system

Một control có thể do nhà cung cấp thực hiện hoặc phụ thuộc dịch vụ ngoài tổ chức. Tài liệu vendor cần được kiểm tra **scope, period, entity, service, customer responsibilities và exceptions**.

### 22.1. Chia trách nhiệm minh bạch

Ví dụ một cloud provider bảo vệ hạ tầng vật lý; khách hàng vẫn phải cấu hình quyền truy cập bucket, data classification, KMS policy và logging theo service model. Một báo cáo kiểm toán của provider **không tự chứng minh** tenant workload của khách hàng đã cấu hình đúng.

| Evidence từ vendor | Có thể hỗ trợ | Cần evidence bổ sung |
|---|---|---|
| SOC/assurance report có scope, period và exceptions. | Một tập controls của provider được đánh giá trong kỳ. | Customer controls, tenant configuration, shared responsibility mapping. |
| Data processing agreement/subprocessor list. | Nghĩa vụ và phạm vi xử lý đã thỏa thuận. | Dòng dữ liệu thật, quyền truy cập, thay đổi và notification. |
| Vendor statement “encryption enabled”. | Thiết kế hoặc tính năng được công bố. | Effective encryption/key ownership cho data của mình. |
| Service availability report. | Uptime theo phương pháp provider. | End-to-end dependency và business RTO/RPO thực tế. |
| Pen-test summary của vendor. | Tập kiểm thử được báo cáo trong scope. | Những API/feature/customer configuration nằm ngoài phạm vi. |

Nếu thiếu evidence từ vendor, có thể đánh giá **risk uncertainty** và yêu cầu bổ sung, không tự kết luận nhà cung cấp FAIL toàn bộ hoặc PASS toàn bộ. Nghĩa vụ bên ngoài phải review theo nguồn, không suy từ khái niệm “compliant”.

## 23. Continuous Assurance: Khi nào bằng chứng cũ hết giá trị?

**Security assurance không phải một lần ký xong vĩnh viễn.** Một kết luận PASS có điều kiện về **scope, revision, kỳ, assumptions và nguồn dữ liệu**. Khi chúng thay đổi đáng kể, phải đánh giá lại.

### 23.1. Trigger catalog mẫu

| Sự kiện | Đối tượng bị ảnh hưởng | Review cần kích hoạt |
|---|---|---|
| Deploy version/config mới. | Tests, artifact binding, IAM và logging. | Revalidate release gates và effective runtime state. |
| Tạo cloud account/region/service mới. | Inventory, policy applicability, coverage. | Onboard asset, cập nhật population, baseline tests. |
| Tăng quyền privileged identity. | Least privilege, approval và session audit. | Effective permissions, allowed/denied tests, owner decision. |
| Thêm data category hoặc vendor. | Encryption, privacy, DPA, data flow. | Applicability, supplier controls và risk reassessment. |
| CVE/advisory mới hoặc exploit evidence. | Vulnerability exposure, mitigations. | Asset/component mapping, attack path và priority. |
| Audit/log collector ngừng. | Detection claim và quality của evidence. | Health checks, synthetic trace, incident triage nếu cần. |
| Backup/key rotation hoặc failover. | Recoverability, RTO/RPO, DR security. | Restore/decrypt tests và integrity validation. |
| Exception hết hạn hoặc mitigation FAIL. | Authorization/risk treatment. | Reassess, revoke/renew đúng quyền, action plan. |
| Finding được sửa hoặc tái xuất hiện. | Control effectiveness, residual risk. | Independent retest, reopen/closure decision. |
| Framework/policy/hợp đồng thay đổi. | Requirements và applicability. | Versioned requirements mapping, new gaps/deadlines. |

### 23.2. Tự giám sát evidence pipeline

Nếu event source hoặc collector offline, “không có sự kiện mới” **không phải bằng chứng không có thay đổi**. Nên kiểm tra heartbeat, API permissions, schema/version, pagination, late events, dead-letter queues, clock skew và nguồn inventory đối chiếu độc lập. Luồng assurance cần khả năng báo **coverage gap** thay vì im lặng xanh.

### 23.3. Lưu lịch sử thay vì ghi đè

Một finding đã PASS ngày 10 và FAIL ngày 15 là hai trạng thái theo thời điểm, không mâu thuẫn nếu context đổi. Lưu evidence/decision versions, source timestamps, nguyên nhân invalidate, owner và time-to-retest. Không biến các kỳ FAIL trước thành PASS bằng cách chỉ giữ trạng thái cuối.

## 24. Automation: Biến traceability thành một hệ thống thực thi

Có thể tự động hóa **thu thập, liên kết, kiểm tra schema, đối chiếu population và mở review**, nhưng không nên mặc định mọi quyết định rủi ro cần được tự động đưa ra không qua thẩm quyền.

~~~mermaid
flowchart LR
    I["Inventory, GRC, risk register"] --> MAP["Requirement/control/risk mapping"]
    S["CI/CD, cloud APIs, IdP, scanners, vendor"] --> COL["Trusted evidence collectors"]
    COL --> Q["Normalize, validate, reconcile"]
    MAP --> V["Rule/test/claim evaluators"]
    Q --> V
    V --> REG["Versioned results + evidence vault"]
    REG --> ACT["Findings, remediation, risk decisions"]
    ACT --> RT["Deploy/retest"]
    RT --> COL
    REG --> DASH["Scope-aware assurance reporting"]
    H["Collector health + trigger monitoring"] --> COL
    H --> V
~~~

### 24.1. Những điều có thể kiểm tra tự động

- Risk, objective, requirement, control, test, evidence IDs tồn tại và liên kết đúng.
- Không có PASS khi required evidence missing, stale hoặc test SKIP/ERROR.
- Population reconciliation: số tài sản in-scope không bị scanner silently drop.
- Approval gắn đúng artifact digest, scope, risk tier và expiry.
- Current risk không bị tự thay bằng projected target trước verification.
- Finding không VERIFIED_CLOSED khi retest còn NOT_RUN, FAIL hoặc INCONCLUSIVE.
- New deployment/region/role triggers reassessment cần thiết.
- Evidence source health, collection errors và missingness được báo.
- Metric contract changes có version và lịch sử audit.

### 24.2. Pseudocode kiểm tra một assurance claim

~~~text
evaluate_claim(claim_id, target_population, assessment_period):
    required_controls = resolve_requirements_and_controls(claim_id)
    observed_population = reconcile_authoritative_inventory(target_population)
    evidence = collect_valid_evidence(required_controls, observed_population)

    if evidence.source_untrusted or evidence.missing_critical_scope:
        return INCONCLUSIVE_WITH_EVIDENCE_GAP

    verdicts = test_and_evaluate_controls(evidence, criteria_version)

    if any_blocking_requirement_contradicted(verdicts):
        return FAIL_WITH_FINDINGS

    if any_required_criterion_unknown_or_untested(verdicts):
        return INCONCLUSIVE_WITH_ACTION_OWNER

    return PASS_FOR_EXPLICIT_SCOPE_AND_PERIOD
~~~

Đây là mô tả logic, không phải code chạy trực tiếp. Trong thực tế, **không phải mọi claim đều có semantics “mọi đối tượng”**, và aggregation phải tuân theo tiêu chí đã định nghĩa. Một lỗi critical có thể là blocker dù tỷ lệ chung cao; một sample có thể đủ cho một claim thống kê nhưng không cho claim universal nếu chưa có phương pháp suy rộng hợp lệ.

## 25. Metrics đúng để theo dõi luồng Risk-to-Evidence

Một dashboard có thể minh bạch mà không cần nhãn “100% secure”. Hãy tách hiệu quả controls, khả năng quan sát và tiến độ xử lý.

| Metric | Câu hỏi | Cạm bẫy cần tránh |
|---|---|---|
| **Risk scenario coverage** | Bao nhiêu risk quan trọng có owner, objectives, controls và test/evidence plan? | Đếm row không chứng minh risk discovery đầy đủ. |
| **Control assessment coverage** | Có bao nhiêu assets/controls được đánh giá hợp lệ trong target population? | Bỏ unseen/ERROR khỏi mẫu số. |
| **Verified PASS coverage** | Bao nhiêu đối tượng có evidence PASS trên toàn scope? | Coi unknown là pass hoặc gộp control khác nghĩa. |
| **Evidence freshness/completeness** | Snapshot còn đại diện, nguồn có quyền và đủ population không? | File mới tạo nhưng dữ liệu bên trong cũ/thiếu. |
| **Critical FAIL và INCONCLUSIVE** | Những mandatory gates/rủi ro nào cần ưu tiên? | Dùng mean score che một critical failure. |
| **Risk treatment authorization** | Risk acceptance, exceptions có đúng quyền, scope và expiry? | Trộn exception active với original control PASS. |
| **Verified remediation ratio** | Findings được retest và đóng đúng tiêu chí? | Đếm PR merged/ticket closed như fixed. |
| **Reassessment latency** | Sau trigger mất bao lâu claim được đánh giá lại? | Đếm ticket ACK thay cho verdict. |
| **Overdue risk/action age** | Bao nhiêu risk/action chưa xử lý quá hạn? | Loại pending để đẹp KPI. |
| **Evidence lineage quality** | Người độc lập có thể truy đến raw source, tool, scope và decision? | Chỉ có screenshot hoặc tổng số trong slide. |

### 25.1. Một ví dụ có đủ mẫu số

Giả sử cloud có **50 assets** thuộc requirement logging, nhưng tại kỳ đánh giá:

- **40 assets** có đánh giá hợp lệ.
- Trong 40 đó **36 PASS**, **4 FAIL**.
- **10 assets** chưa đủ evidence do collector không đọc được.

Khi đó:

~~~text
Target population             = 50
Assessment coverage           = 40/50 = 80%
Pass rate among assessed      = 36/40 = 90%
Verified PASS coverage        = 36/50 = 72%
Known FAIL coverage           =  4/50 =  8%
Unassessed / INCONCLUSIVE     = 10/50 = 20%
~~~

**Không được báo “90% toàn hệ thống compliant”**; 90% chỉ là pass rate trên tập đã test. Ngay cả 72% cũng chỉ là **tỷ lệ có PASS được kiểm chứng theo phương pháp hiện hành**, không phải “xác suất toàn bộ hệ thống an toàn”. Nếu 10 unseen assets bao gồm hệ thống dữ liệu nhạy cảm, ưu tiên risk review có thể cao dù tỷ lệ chưa đánh giá chỉ 20%.

### 25.2. Tránh phép cộng risk score tùy tiện

Nếu risk register có 3 Critical, 4 High, 1 Medium, báo phân bố và bối cảnh; **không cộng điểm ordinal** rồi gọi đó là “tổng phần trăm rủi ro”. Khi thay scoring rubric hoặc population, công bố version/change và tránh so trend không còn tương thích.

## 26. Bài tập tổng hợp: Tái dựng một luồng Risk-to-Evidence bị đứt

Một nền tảng thương mại sử dụng API, cloud IAM và central logging. Trong tháng, Security trình bày:

- “Rủi ro truy cập dữ liệu đã giảm từ Critical xuống Medium.”
- “Service account đã được sửa quyền.”
- “Release mới được approved.”
- “Audit logs hoạt động 100%.”
- “Finding đã CLOSED.”

Nhưng reviewer phát hiện:

1. Risk score Medium lấy từ **target risk dự kiến**, không có verified residual assessment.
2. Pull request giảm quyền đã merge nhưng **chưa deploy ở production**.
3. Release approval gắn image digest H1, production chạy image H2.
4. SIEM có event từ 8/10 production accounts; hai accounts mới chưa onboard.
5. Finding được đóng theo trạng thái ticket DONE, **không có retest**.
6. Một external vendor truy cập production qua support path chưa có trong mô hình IAM.
7. Risk owner đã ký acceptance “30 ngày” nhưng hồ sơ không nêu control deviation, mitigation và ngày hiệu lực.

### 26.1. Yêu cầu thực hành

Hãy tạo:

1. Sơ đồ risk → objective → requirement → control → test → evidence → claim → decision.
2. Danh sách **confirmed facts**, **missing evidence** và **assumptions**.
3. Bảng **control verdict** riêng cho IAM, logging, release integrity và exception governance.
4. Risk reassessment có current vs projected vs verified residual tách biệt.
5. Danh sách evidence IDs cần thu để xác minh claim.
6. Một finding hoặc action cho từng control/evidence gap, có owner và verification gate.
7. Quyết định nên thực hiện ngay, bước nào cần thẩm quyền và khi nào phải NO-GO.
8. Executive summary không quá 200 từ, không tuyên bố rộng hơn evidence.

### 26.2. Gợi ý đáp án

| Mệnh đề được báo cáo | Thực tế hiện có | Kết luận tạm |
|---|---|---|
| Risk đã hạ Medium | Chỉ có projected score, chưa có effective controls/retest. | **Chưa được chứng minh**; cần current assessment mới. |
| IAM đã được sửa | PR merge, production chưa deploy; vendor path chưa map. | **Không đủ căn cứ PASS**; nếu current permission vi phạm có test thì FAIL. |
| Release authorized đúng bản | Approval H1 nhưng runtime H2. | **Authorization mismatch**, rà soát release/change ngay. |
| Logging đầy đủ | 8/10 accounts có observed evidence. | **Coverage 80%**, 2 accounts chưa được đánh giá; không thể báo 100%. |
| Finding verified closed | Ticket DONE không có retest. | **Closure evidence gap**, cần reopen/retest theo policy. |
| Risk acceptance hợp lệ | Thiếu scope/deviation/conditions/effective date. | **Governance INCONCLUSIVE/INVALID theo tiêu chí**, xác minh thẩm quyền. |

**Hành động:** kiểm tra effective IAM permissions và support path, xác minh H2 provenance/risk và quyền deploy, onboard hai accounts vào logging, khôi phục evidence và synthetic tests, mở lại finding cho tới khi có retest, yêu cầu risk owner đánh giá lại với conditions rõ. Nếu đang có dấu hiệu khai thác hoặc truy cập dữ liệu ngoài quyền, kích hoạt incident response và containment theo runbook; không trì hoãn bảo vệ hệ thống để hoàn thiện slide.

### 26.3. Một kết luận quản trị phù hợp

“Có dấu hiệu một số công việc khắc phục đã được lên kế hoạch nhưng chưa có bằng chứng hiệu lực production. Approval chưa khớp artifact, logging coverage hiện chỉ xác minh ở 8/10 accounts và finding thiếu retest. Vì vậy chưa đủ căn cứ tuyên bố risk đã giảm tới Medium hoặc toàn bộ controls PASS. Cần risk reassessment, release integrity review, IAM/tenant/vendor access tests, logging remediation và sign-off theo thẩm quyền trước khi mở rộng rollout.”

## 27. Những anti-pattern khiến luồng Risk-to-Evidence đứt gãy

| Anti-pattern | Sai ở mắt xích nào? | Cách sửa |
|---|---|---|
| Chấm điểm risk không có threat scenario. | Context → Risk. | Ghi actor/event/path/impact và rationale. |
| Yêu cầu “bảo mật tốt” không đo được. | Objective → Requirement. | Viết tiêu chí, scope, nguồn/version rõ. |
| Control có trên sơ đồ nhưng không chạy. | Requirement → Implementation. | Effective config và runtime verification. |
| Chỉ test happy path. | Control → Test. | Negative/bypass tests và inventory coverage. |
| Test staging suy production. | Test → Evidence applicability. | Environment delta và production verification. |
| Screenshot không có nguồn và timestamp. | Evidence provenance. | Raw artifact, IDs, collector, scope, digest/version. |
| 0 findings được hiểu không có lỗi. | Evidence → Claim. | Scanner coverage/limitations, missing data. |
| Một PASS ở mẫu nhỏ suy toàn fleet. | Claim scope/warrant. | Reconcile population; qualifier và unknown. |
| Risk acceptance biến FAIL thành PASS. | Risk decision vs control verdict. | Tách governance, kỹ thuật và external obligations. |
| PR merged thành finding fixed. | Remediation → Retest. | Verify deployment và independent retest. |
| Approval A được dùng deploy B. | Release evidence binding. | Digest/manifest và reapproval triggers. |
| Không có owner/expiry cho exception. | Decision governance. | Authority, validity, conditions, monitoring. |
| Collector chết nhưng dashboard xanh. | Continuous evidence pipeline. | Health checks, synthetic events, INCONCLUSIVE. |
| Vendor audit report thay customer control. | Third-party evidence. | Shared responsibility và tenant-specific tests. |
| Xóa lịch sử sau sửa lỗi. | Auditability/time validity. | Append-only/versioned records, gap periods. |
| Chỉ báo score tổng. | Reporting → Decision. | Critical gates, coverage, confidence và actions. |

## 28. Checklist tổng kết: Một chuỗi Risk-to-Evidence đã đủ đáng tin chưa?

Trước khi công bố một assurance conclusion, hãy tự kiểm tra:

1. **Business context:** Scope, business services, dữ liệu, asset IDs và trust boundaries được xác định?
2. **Population:** Target và assessed population đã được đối chiếu; exclusions có lý do?
3. **Risk scenario:** Có actor/sự kiện, attack/operational path, asset và impact?
4. **Risk method:** Likelihood/impact, assumptions, confidence và phiên bản phương pháp rõ?
5. **Security objective:** Đang bảo vệ điều gì, không chỉ liệt kê công cụ?
6. **Requirement:** ID, nguồn/version, applicability và tiêu chí PASS/FAIL có thể phản chứng?
7. **Control:** Có design, implementation, effective scope và owner?
8. **Control mapping:** Risk và requirement liên kết đúng với preventive/detective/corrective/recovery controls?
9. **Test scope:** Positive/negative tests, coverage, environment và artifact version có khớp claim?
10. **Evidence:** Có source, collector, timestamp, raw/derived references, tool version, method và limitations?
11. **Data quality:** Missing accounts, permission errors, API pagination, collector health và stale evidence đã xét?
12. **Integrity:** Evidence/decision history được bảo vệ nhưng không đánh đồng hash với completeness?
13. **Claim/warrant:** Có lý do tại sao evidence hỗ trợ kết luận, assumptions và defeaters?
14. **Verdict:** PASS/FAIL/INCONCLUSIVE/NOT_APPLICABLE được dùng đúng theo scope/kỳ?
15. **Risk feedback:** Current vs projected vs verified residual có tách biệt và được đánh giá lại?
16. **Finding:** Control gap và evidence gap có được phân loại để xử lý đúng?
17. **Treatment:** Có containment, root cause, action owner, deadlines và dependencies?
18. **Approval:** Risk acceptance/exception/release có đúng quyền, scope, conditions và expiry?
19. **External obligations:** Có review riêng với luật/hợp đồng/chương trình áp dụng nếu liên quan?
20. **Deployment:** Change/release artifact digest và observed runtime khớp bản đã test/approved?
21. **Retest:** Fix đã được kiểm chứng trên control gốc, có independent sign-off khi cần?
22. **Historical truth:** Mốc thời gian FAIL/unknown/approved/verified được giữ; không backdate?
23. **Continuous assurance:** Trigger IAM, data, vendor, release, threat, evidence health được định nghĩa?
24. **Reporting:** Numerator/denominator, confidence, known FAIL, unknown và critical blockers được hiển thị?
25. **Decision:** Người đọc có biết phải làm gì, ai ra quyết định và bằng chứng nào còn thiếu?
26. **Security of evidence:** Confidentiality, privacy, retention và audit access được thực hiện?
27. **Reproducibility:** Người độc lập có thể lần ngược từ executive claim tới raw evidence và tính lại kết quả?
28. **Learning loop:** Findings, incidents, drift và test failures có dẫn tới cải tiến controls/methods?

### Câu hỏi tự kiểm tra cuối cùng

Một nhóm có risk register, danh sách controls, scanner report, dashboard compliance và các release tickets. Họ khẳng định “đã có đủ thành phần security assurance”. Điều gì còn thiếu?

**Gợi ý:** Chưa chứng minh **mối liên kết và hiệu lực** giữa các thành phần. Hãy chọn một risk Critical, truy từ scenario tới security objective/requirement, xác định control hiện hữu, test trên đúng artifact/asset/scope, raw evidence và warrant, verdict/limitations, quyết định risk owner, remediation/verified retest và trigger reassessment. Nếu không truy được một mắt xích hoặc nguồn dữ liệu thiếu, claim cần giới hạn hoặc đánh dấu **INCONCLUSIVE**. Nhiều file riêng lẻ không tương đương một assurance case khép kín.

**Kết luận:** Luồng từ risk đến evidence biến hoạt động bảo mật rời rạc thành một chuỗi có thể phản biện: **rủi ro định hướng mục tiêu; mục tiêu tạo yêu cầu; yêu cầu được hiện thực bằng controls; controls được kiểm bằng test; test sinh evidence; evidence hỗ trợ hoặc bác bỏ claim trong phạm vi; kết luận dẫn tới quyết định, khắc phục và đánh giá lại**. Giá trị của security assurance không nằm ở số lượng artifact hay màu xanh của dashboard, mà nằm ở việc tổ chức **biết điều gì đã được chứng minh, điều gì chưa biết, điều gì đang sai và ai có trách nhiệm làm cho kết luận tốt lên bằng bằng chứng mới**.
