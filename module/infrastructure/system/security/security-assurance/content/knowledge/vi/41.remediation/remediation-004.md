# Ưu tiên sửa lỗi: sắp xếp remediation theo rủi ro, bằng chứng và khả năng thực thi

**Ưu tiên sửa lỗi (remediation prioritization)** là quá trình xác định **lỗ hổng, cấu hình sai, khoảng trống kiểm soát và phát hiện kiểm toán nào phải được xử lý trước, bằng biện pháp gì, trong thời hạn nào và ai có quyền chấp nhận rủi ro còn lại**. Mục tiêu không phải đóng nhiều ticket nhất, đạt điểm scanner đẹp nhất hoặc luôn sửa mục có CVSS cao nhất, mà là **giảm phơi nhiễm và hậu quả bảo mật đáng kể nhất trong những ràng buộc vận hành có thật**.

Trong chương **Remediation** thuộc module **SECURITY_SECURITY_ASSURANCE**, ưu tiên sửa lỗi là một phần của security assurance liên tục: tổ chức phải có bằng chứng rằng hệ thống đáp ứng mục tiêu bảo mật, từ phân tích rủi ro, security requirements và controls đến kiểm thử, audit, xử lý findings và xác minh hiệu lực sau khắc phục. Vì vậy, quyết định ưu tiên phải có **phạm vi, tiêu chí, dữ liệu nguồn, lý do, người chịu trách nhiệm, biện pháp tạm thời, mốc đánh giá lại và kết quả retest**.

Một lỗ hổng kỹ thuật nghiêm trọng nhưng nằm ở ứng dụng thử nghiệm bị cô lập có thể được xử lý sau một cấu hình danh tính “medium” đang cho phép quyền quản trị production vượt phạm vi. Ngược lại, không được lấy lý do “độ khó sửa cao” để trì hoãn vô thời hạn một điểm yếu đang bị khai thác. **Ưu tiên là quyết định quản trị rủi ro có thể kiểm chứng, không phải bài toán cộng điểm đơn thuần.**

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **vulnerability severity, exploitation likelihood, business impact, remediation priority, urgency, SLA và risk acceptance**.
2. Xác định population của findings và hợp nhất dữ liệu từ scanner, cloud posture, audit, incident, threat modeling, pentest và bug bounty mà không làm mất dấu vết.
3. Ưu tiên theo **tình trạng khai thác, phạm vi phơi nhiễm, quyền truy cập, mức độ quan trọng của tài sản, đường tấn công, tác động CIA và hiệu lực kiểm soát bù trừ**.
4. Sử dụng CVSS, thông tin khai thác thực tế, danh mục lỗ hổng đã được ghi nhận khai thác, EPSS và phương pháp ra quyết định như SSVC **đúng phạm vi và giới hạn**.
5. Thiết kế cơ chế **critical override/gating**, bộ tiêu chí phân tầng P0–P3 và deadline nội bộ có khả năng giải thích, không lấy điểm trung bình che lấp rủi ro trọng yếu.
6. So sánh patch, upgrade, cấu hình giảm phơi nhiễm, cô lập, vô hiệu tính năng, rotate credential, rollback, thay kiến trúc và các biện pháp tạm thời.
7. Lập remediation backlog theo dependency, chi phí, rủi ro khi thay đổi, năng lực thực hiện và lợi ích giảm rủi ro; không để ràng buộc nguồn lực trở thành lý do mặc định trì hoãn.
8. Ghi nhận quyết định ưu tiên, triage, exception, residual risk và phê duyệt có thời hạn.
9. Xác minh **đã khắc phục** bằng retest đúng asset/control/scenario, kiểm tra hiệu lực và ngăn tái diễn.
10. Đo hiệu quả ưu tiên bằng KPI có mẫu số, severity, tuổi tồn đọng, verified closure và recurrence.

## 2. Hiểu đúng “sửa lỗi” trong security assurance

### 2.1. Những đối tượng có thể cần remediation

| Nhóm | Ví dụ | Rủi ro nếu không xử lý |
|---|---|---|
| **Software vulnerability** | Thành phần có lỗ hổng đã công bố, thư viện lỗi, API thiếu kiểm tra quyền | Có thể bị khai thác, chiếm quyền hoặc rò dữ liệu |
| **Misconfiguration** | Bucket công khai ngoài ý muốn, IAM quá quyền, firewall mở rộng | Vượt ranh giới tin cậy hoặc làm mất khả năng bảo vệ |
| **Control gap** | MFA không bao phủ tài khoản local, nguồn log chưa onboarding, backup không được thử restore | Security objective không được đảm bảo hoặc không chứng minh được |
| **Compliance/audit finding** | Thiếu access review đúng kỳ, retention không đạt requirement áp dụng | Không đáp ứng nghĩa vụ, tạo rủi ro và khoảng trống bằng chứng |
| **Security architecture weakness** | Dùng chung khóa quản trị cho production và DR, thiếu phân đoạn mạng | Lỗi chung có thể lan rộng, blast radius lớn |
| **Detection blind spot** | Parser làm mất field, rule bị tắt, suppression quá rộng | Tăng thời gian attacker hoạt động mà không bị nhận biết |
| **Identity/secret exposure** | Token production bị lộ, quyền tạm thời không thu hồi | Truy cập trái phép đang hoặc có thể diễn ra |
| **Third-party weakness** | Vendor support access không có kiểm soát bắt buộc, subprocessor chưa đánh giá | Rủi ro phụ thuộc, xử lý dữ liệu và trách nhiệm chia sẻ |
| **Resilience gap** | Restore bị lỗi KMS, RPO không đạt, failback chưa kiểm | Không phục hồi dịch vụ/dữ liệu theo BIA |
| **Process or evidence gap** | Ticket được đánh Done nhưng chưa có retest, không lưu chứng cứ review | Không xác minh được hiệu lực hoặc vi phạm thực tế |

“Lỗi” ở đây được hiểu theo nghĩa rộng của **security remediation**, không chỉ là lỗi lập trình. Việc sửa một CVE thường chỉ là **correction** cho một đối tượng; chương trình remediation còn cần xem **root cause**, các đối tượng tương tự và cơ chế ngăn tái xuất hiện.

### 2.2. Các hành động không đồng nghĩa

- **Triage:** xác nhận finding có thật không, phạm vi và rủi ro, tránh hành động trên dữ liệu sai.
- **Containment:** hạn chế ảnh hưởng tức thời, ví dụ khóa token đang bị lộ, cô lập workload hoặc giảm quyền.
- **Mitigation:** giảm xác suất/tác động mà chưa loại bỏ hẳn nguyên nhân, ví dụ chặn một đường exploit được xác định.
- **Correction:** sửa sai lệch tại asset/tình huống cụ thể.
- **Remediation:** xử lý điều kiện không đạt và các nguyên nhân liên quan để đạt security objective.
- **Corrective action:** ngăn cùng nguyên nhân làm sai lệch xuất hiện lại, ví dụ sửa mẫu provisioning hoặc pipeline.
- **Compensating control:** kiểm soát thay thế được đánh giá đủ hiệu lực cho mục tiêu/ngoại lệ đã được phép.
- **Retest/verification:** kiểm tra lại control assertion trên đúng scope bằng bằng chứng mới.
- **Risk acceptance:** quyết định có thẩm quyền chấp nhận rủi ro chưa xử lý với điều kiện, không phải kết quả PASS.
- **Closure:** kết thúc finding theo thủ tục đã định, có thể là **verified closure**, accepted risk có quản lý hoặc reason khác được ghi rõ.

Một ticket **“đã triển khai patch”** không tự chứng minh đường exploit bị loại, package được tải lại, phiên bản runtime thay đổi hoặc hiệu lực security control đã đạt.

### 2.3. Severity không phải priority

**Severity** thường phản ánh mức nghiêm trọng của điểm yếu theo một phương pháp xác định (ví dụ CVSS cho đặc tính lỗ hổng). **Priority** phản ánh **hành động cần làm trước trong bối cảnh tài sản, threat, exposure, hậu quả, deadline và kiểm soát hiện hữu**.

| Khía cạnh | Severity | Remediation priority |
|---|---|---|
| Đối tượng | Đặc tính điểm yếu hoặc finding | Rủi ro và tính cấp bách đối với tổ chức |
| Phụ thuộc context? | Có thể một phần, tùy phương pháp | Bắt buộc xét service, exposure và dữ liệu thực tế |
| Dữ liệu | Vector kỹ thuật, impact, điều kiện khai thác | Severity + threat intelligence + asset + controls + nghĩa vụ |
| Thay đổi theo thời gian? | Có thể đổi khi có phân tích mới | Cần đổi khi khai thác/threat/exposure/criticality thay đổi |
| Kết quả | Nhóm severity/score | Thứ tự công việc, owner, deadline, escalation, quyết định |
| Cạm bẫy | Điểm cao không có nghĩa mọi triển khai có cùng risk | Điểm ưu tiên không được dùng như bằng chứng an toàn tuyệt đối |

Ví dụ một CVSS cao ở thành phần không được deploy trong production không có cùng exposure với một cấu hình truy cập dữ liệu khách hàng đang công khai. Việc “không được deploy” phải được xác minh từ inventory, SBOM và artifact thực, không chỉ dựa lời kể.

## 3. Chuỗi quyết định ưu tiên từ phát hiện đến retest

~~~mermaid
flowchart TD
    FIND["Finding từ scanner / audit / incident"] --> NORM["Chuẩn hóa và đối soát asset"]
    NORM --> VALID{"Finding hợp lệ và thuộc scope?"}
    VALID -- "Không rõ" --> INVEST["Xác minh nguồn, phiên bản, mẫu số"]
    INVEST --> VALID
    VALID -- "Không áp dụng đã chứng minh" --> REASON["Ghi N/A hoặc false positive có bằng chứng"]
    VALID -- "Có" --> THREAT["Đánh giá threat, exposure, impact, controls"]
    THREAT --> GATE{"Đang khai thác hoặc critical gate?"}
    GATE -- "Có" --> URGENT["Khống chế tức thời + escalation"]
    GATE -- "Không" --> TIER["Gán priority / deadline theo policy"]
    URGENT --> PLAN["Owner + phương án khắc phục + hạn"]
    TIER --> PLAN
    PLAN --> EXEC["Triển khai có kiểm soát"]
    EXEC --> VERIFY{"Retest đúng assertion đạt?"}
    VERIFY -- "Chưa" --> PLAN
    VERIFY -- "Có" --> CLOSE["Verified closure + evidence"]
    CLOSE --> PREVENT["RCA, regression, monitoring"]
~~~

Các bước vận hành cần trả lời bốn loại câu hỏi:

1. **Có thật và ở đâu?** Xác định CVE/advisory, asset, phiên bản, environment, control và đúng configuration path.
2. **Rủi ro nào, đang diễn ra hay chỉ tiềm tàng?** Phân tích evidence về khai thác, exposure, privilege, data và hậu quả.
3. **Xử lý bằng cách nào và khi nào?** Cân nhắc điều kiện khẩn cấp, SLA, remediation option, dependency và rủi ro khi triển khai.
4. **Làm sao biết đã đạt?** Retest control, data-flow/path, test âm/dương, evidence và theo dõi tái diễn.

Không nên chỉ tập trung câu hỏi thứ ba vì một danh sách ticket đã được sắp xếp mà **scope, risk và verification** chưa rõ sẽ tạo cảm giác quản lý tốt giả.

## 4. Xác định population trước khi xếp hạng

### 4.1. Nguồn findings và điểm mù

Một remediation backlog có thể thu từ:

- Vulnerability scanner, dependency scanning, container image scanning, software composition analysis.
- Cloud security posture management, identity security posture và configuration assessment.
- SAST/DAST, penetration testing, secure code review, bug bounty trong phạm vi được phép.
- Asset discovery, external attack surface management và inventory.
- Incident response, threat hunting, detection engineering và post-incident review.
- Audit, compliance assessment, security assurance, risk review và third-party assessment.
- Backup/DR exercise, resilience test, vendor notification và internal reports.

**Một danh sách từ scanner không phải toàn bộ remediation population.** Những tài sản chưa được quét, API không hiện trong inventory hoặc service account nằm ngoài IdP có thể tạo rủi ro lớn nhưng không có ticket.

### 4.2. Liên kết các nguồn bằng định danh ổn định

Với mỗi finding cần đối soát:

- Asset/workload identity (cloud account, instance, image digest, package, service, tenant).
- Business service và owner.
- Environment, vùng, network exposure, mức dữ liệu.
- Control/requirement và risk scenario liên quan.
- Fingerprint điểm yếu, thời điểm phát hiện/last seen.
- Nguồn quan sát, confidence và evidence.
- Tình trạng asset: active, retired, ephemeral, staging, production.
- Duplicate/correlation với finding đã có.

Một lỗ hổng có thể xuất hiện trong mười container cùng dùng một base image. Hợp nhất mười record thành một **root-fix campaign** có thể hiệu quả, nhưng phải giữ **mười asset affected và tình trạng triển khai** để không đóng sai phạm vi.

### 4.3. Những trạng thái cần giữ riêng

| Trạng thái | Cách hiểu |
|---|---|
| **CONFIRMED** | Có bằng chứng điểm yếu hiện diện ở scope xác định |
| **POTENTIAL / NEEDS_VALIDATION** | Scanner/báo cáo nghi ngờ, cần xác minh cách deploy hoặc path thực |
| **NOT_APPLICABLE** | Đã chứng minh không áp dụng cho asset/phiên bản/scope |
| **FALSE_POSITIVE** | Phép phát hiện cho kết quả sai và có bằng chứng kiểm tra |
| **MITIGATED** | Rủi ro đã được giảm bằng biện pháp phù hợp nhưng nguyên nhân có thể còn |
| **FIX_IMPLEMENTED** | Đã triển khai thay đổi, chưa có retest đạt |
| **READY_FOR_RETEST** | Đã cung cấp đủ thông tin và môi trường để kiểm chứng lại |
| **CLOSED_VERIFIED** | Retest/đánh giá theo tiêu chí đóng đã đạt và được phê duyệt |
| **RISK_ACCEPTED** | Quyết định chấp nhận rủi ro còn lại có scope, thẩm quyền và hạn |
| **DECOMMISSIONED_VERIFIED** | Asset thực sự được loại khỏi phạm vi với bằng chứng thu hồi quyền/traffic/dữ liệu |

**Không gộp “không còn thấy trong scanner” với “đã khắc phục”.** Nhiều scanner chỉ quét tài sản được nối vào công cụ; tài sản bị mất telemetry dễ biến một lỗ hổng thành điểm mù.

## 5. Các yếu tố quyết định mức ưu tiên

### 5.1. Tình trạng bị khai thác và khả năng khai thác

| Tín hiệu | Ý nghĩa đối với triage | Giới hạn |
|---|---|---|
| **Đã có bằng chứng bị khai thác trên hệ thống của mình** | Kích hoạt incident handling/containment và ưu tiên khẩn cấp theo tác động | Cần chứng minh tín hiệu, tránh tự đồng nhất alert với incident |
| **Known exploited vulnerability** | Có bằng chứng đáng tin lỗ hổng đã bị khai thác ngoài thực tế | Không suy ra asset của mình đã bị tấn công |
| **Exploit đang phổ biến hoặc có exploit công khai đáng tin** | Có thể làm giảm chi phí/điều kiện cho attacker | PoC công khai không tự chứng minh khả năng trên cấu hình hiện tại |
| **Threat actor nhắm tới sản phẩm/đường truy cập liên quan** | Tăng relevance của scenario | Intelligence có thể chưa cập nhật hoặc sai ngữ cảnh |
| **Likelihood estimate / EPSS** | Hỗ trợ xếp mức khả năng exploit trong tập/dữ liệu được mô hình hóa | Là xác suất ước lượng có điều kiện, không thay hậu quả hay exposure nội bộ |
| **Attack complexity / prerequisites** | Giải thích điều kiện cần để khai thác | Scanner thường không biết hết authentication, network và compensations |
| **Exposure được xác minh** | Biết liệu attacker có thể tiếp cận attack surface | Cần effective network paths, không chỉ nhãn Internet-facing |

Nếu có dấu hiệu **đang bị khai thác**, hoạt động có thể chuyển từ remediation planning thông thường sang **incident response**; khi đó việc bảo toàn evidence, containment và phối hợp service owner là ưu tiên. Không trì hoãn để chờ tính risk score hoàn chỉnh.

### 5.2. CVSS giúp gì và không giúp gì?

**CVSS (Common Vulnerability Scoring System)** mô tả đặc tính/impact của lỗ hổng qua hệ thống metric có phiên bản; là một đầu vào hữu ích để chuẩn hóa severity. Khi sử dụng phải ghi:

- Phiên bản CVSS và nguồn cung cấp score/vector.
- Base metrics đã biết; nếu có environmental/threat metrics phù hợp thì ghi riêng.
- Sản phẩm, phiên bản, cấu hình, attack prerequisites và ảnh hưởng thật của asset.
- Những trường hợp scanner nhận sai package/version hoặc backport security patch.

**CVSS base cao không đồng nghĩa priority luôn cao hơn.** Nó không tự biết ứng dụng đang chạy ở production hay sandbox, data class, IAM boundary hay tính độc lập của backup. CVSS cũng không xác nhận asset đang có exploitable path.

### 5.3. KEV, EPSS và SSVC

- **CISA Known Exploited Vulnerabilities (KEV):** danh mục lỗ hổng có bằng chứng đã bị khai thác trong thực tế theo tiêu chí của đơn vị quản lý danh mục. Có thể là tín hiệu ưu tiên rất mạnh khi **đúng sản phẩm/phiên bản và asset bị ảnh hưởng**. Việc có tên trong KEV không chứng minh tài sản của mình bị khai thác; việc chưa có trong KEV không chứng minh không bị khai thác. Một số nghĩa vụ của một số đối tượng có thể gắn với danh mục này, phải xác minh phạm vi áp dụng.
- **Exploit Prediction Scoring System (EPSS):** cung cấp ước lượng xác suất khai thác của CVE theo mô hình và kỳ dự báo, có thể hỗ trợ sắp xếp workload remediation. Đây là thông tin về **threat likelihood ở mức CVE**, không phải chỉ số business impact hoặc xác suất lộ dữ liệu của tổ chức. Cần ghi snapshot/date vì điểm biến đổi theo thời gian.
- **Stakeholder-Specific Vulnerability Categorization (SSVC):** cây quyết định ưu tiên dựa trên các yếu tố như exploitation status, technical impact, automatability, mission/well-being impact tùy mô hình và stakeholder. Quy tắc, outcome và phương pháp áp dụng phải được tổ chức lựa chọn/document; không tự gọi một công thức tự chế là “chuẩn SSVC”.

Các nguồn có thể bổ trợ nhau nhưng **không nên cộng CVSS, EPSS và KEV thành một điểm giả chính xác** mà không định nghĩa sự khác biệt và kiểm tra tính hợp lý. Nếu sử dụng threat intelligence, ghi **nguồn, thời điểm, confidence và điều kiện thay đổi quyết định**.

### 5.4. Business impact và asset criticality

Câu hỏi cần đặt:

- Asset phục vụ nghiệp vụ nào, BIA xếp quan trọng ra sao?
- Có xử lý dữ liệu nhạy cảm, bí mật doanh nghiệp, giao dịch hoặc danh tính?
- Nếu chiếm quyền, attacker có thể di chuyển sang môi trường khác không?
- Lỗi có ảnh hưởng confidentiality, integrity, availability và khả năng khôi phục không?
- Blast radius nằm ở một pod, một account hay toàn organization?
- Có điểm lỗi chung như IdP, KMS, DNS, CI/CD, backup catalog?
- Có đối tượng bị ảnh hưởng ngoài công ty: khách hàng, vendor, đối tác?
- Tác động đã xảy ra hay chỉ là kịch bản tiềm tàng?

Một cấu hình IAM “medium” trên control plane có thể có **enterprise-wide impact**, trong khi một lỗ hổng local trên máy thử nghiệm cô lập có thể thấp hơn trong bối cảnh hiện tại.

### 5.5. Exposure và ranh giới tin cậy

Một số chiều cần xác minh:

- Public Internet → reverse proxy → API.
- Chỉ nội bộ nhưng có lateral movement path từ asset yếu.
- Authentication/authorization prerequisites thực sự.
- Quyền attacker cần có và quyền đạt được sau khai thác.
- Network policy, segmentation, WAF, access gateway, PAM có kiểm thử hay chỉ cấu hình trên giấy.
- Workload chạy code vulnerable thực sự hay dependency chỉ tồn tại trong build/test.
- Có dữ liệu thật hoặc secret tại runtime không?
- Có thể tấn công qua chain gồm nhiều điểm yếu dù từng điểm có severity thấp?

**Không có cổng public** không đồng nghĩa không có rủi ro nếu attacker có thể đi qua VPN, compromised vendor account hoặc service-to-service token.

### 5.6. Control bù trừ và mức tin cậy

Một control bù trừ chỉ nên giảm priority/risk nếu:

1. Đúng threat scenario và attack path.
2. Được triển khai trên **mọi tài sản trong scope**.
3. Có bằng chứng **effective state**, không chỉ tài liệu thiết kế.
4. Có test phù hợp và giám sát drift.
5. Có owner, expiry hoặc review trigger.
6. Không làm hỏng security requirement khác hoặc tạo lỗ hổng mới.

Ví dụ WAF rule có thể giảm phơi nhiễm với một kiểu request, nhưng không tự vá lỗi thư viện, không bảo vệ đường nội bộ bỏ qua WAF và có thể bị bypass. Nếu chưa kiểm chứng, ghi **proposed mitigation** chứ không trừ điểm rủi ro như đã có control đạt.

### 5.7. Những yếu tố không nên được dùng để hợp lý hóa trì hoãn

- Không có người sửa hôm nay.
- Ticket nằm ngoài sprint đang chạy.
- Chủ dự án không muốn downtime.
- Scanner đã báo lỗi nhiều tháng nhưng “chưa xảy ra gì”.
- CVE không được liệt kê trong một nguồn intelligence riêng.
- Kết quả scanner mất khỏi dashboard sau khi xóa sensor.
- Lỗi nằm ở code cũ, khó nâng cấp.
- Nhà cung cấp không có ngày phát hành patch.

Những yếu tố đó là **ràng buộc thực thi** cần quản lý bằng escalation, resource, mitigation và risk decision; không được âm thầm biến thành bằng chứng mức rủi ro thấp.

## 6. Thiết kế policy ưu tiên theo critical gates

### 6.1. Vì sao không nên chỉ cộng điểm?

Một mô hình trọng số trung bình có thể cho tình huống **đang bị khai thác một đường truy cập admin** điểm thấp nếu các yếu tố khác không được cộng đúng. Do đó, trước khi tính priority thông thường, cần các điều kiện **override/gate**.

Ví dụ các trigger có thể yêu cầu xử lý khẩn cấp theo policy:

- Có sự cố được xác nhận liên quan trực tiếp điểm yếu.
- Credential/token có quyền production nhạy cảm bị lộ hoặc nghi bị chiếm với tín hiệu có căn cứ.
- Một security boundary trọng yếu đang bị mở/không có kiểm soát trên production.
- Lỗ hổng đang bị khai thác và có exploitable path trên dịch vụ quan trọng.
- Tài sản chịu một nghĩa vụ bắt buộc có deadline không thể được miễn trừ bằng đánh giá nội bộ.
- Có thay đổi làm mất logging/detection ở nơi đang có nguy cơ cao.
- Một số tài sản hoặc recovery copies quan trọng có nguy cơ bị xóa/phá hoại đồng thời.

Danh sách này cần được tổ chức phê duyệt và **phân biệt “critical risk” với “đã có incident”**. Không tự gọi tất cả tín hiệu nghi ngờ là P0 trước khi xác minh tối thiểu điều kiện.

### 6.2. Mức ưu tiên P0–P3 chỉ là ví dụ

| Priority | Đặc điểm quyết định | Hành động điển hình |
|---|---|---|
| **P0 — Emergency** | Có tác động/sự cố đang xảy ra hoặc threat có khả năng ảnh hưởng nghiêm trọng tức thời, cần phối hợp khẩn | Incident/DR commander, containment, preserve evidence, theo dõi liên tục |
| **P1 — Urgent** | Rủi ro cao và gần, exploit/reachability đáng tin, critical asset hoặc control bắt buộc không đạt | Ưu tiên release/hotfix, mitigation tạm thời, escalation và retest |
| **P2 — Planned high/medium** | Rủi ro đáng kể nhưng chưa có trigger khẩn, có thể sửa theo kế hoạch được bảo đảm | Gán sprint/campaign, owner, hạn, test và giám sát |
| **P3 — Scheduled/low** | Rủi ro thấp trong bối cảnh đã xác minh và có thể quản lý theo backlog | Lên lịch nâng cấp/cải tiến, kiểm lại khi context đổi |

**Không có nghĩa mọi tổ chức phải dùng P0–P3**, và không có thời hạn cố định đúng cho mọi môi trường. Phương pháp nội bộ cần mô tả tiêu chí, trách nhiệm phê duyệt và liên kết với risk appetite, hợp đồng, quy định và SLAs thực tế.

### 6.3. Ma trận quyết định định tính

| Threat/exposure | Tác động nghiệp vụ | Control bù trừ đã kiểm | Gợi ý triage |
|---|---|---|---|
| Đang khai thác trên asset tổ chức | Cao | Không đủ hoặc chưa rõ | Emergency/incident pathway, không chờ scoring |
| Known exploited + asset public reachable | Cao | Không đủ | Ưu tiên khẩn, xác minh exposure và containment |
| Có exploit khả thi + privileged boundary | Cao | Một phần | Ưu tiên cao, thử control bù trừ và sửa theo hạn |
| Có điểm yếu nhưng production path bị cách ly xác minh | Trung bình/cao | Đạt trong scope | Vẫn có kế hoạch fix, review khi network đổi |
| Chỉ library dev/test không được deploy | Thấp trong scope hiện tại | Bằng chứng inventory rõ | Có thể kế hoạch thường, giữ trigger khi đưa vào production |
| Không đủ thông tin về asset hoặc exposure | Chưa rõ | Không rõ | **Needs validation** với hạn điều tra, không mặc định thấp |

Đây là **minh họa tư duy ưu tiên**. Mỗi quyết định thực tế vẫn cần risk rationale và yêu cầu áp dụng.

### 6.4. Không lấy phép cộng điểm che priority override

Nếu dùng một score như tham chiếu, cần quy định:

1. Trước hết kiểm các **hard triggers** P0/P1.
2. Sau đó chấm exposure, exploitability, impact, urgency và control confidence cho các case còn lại.
3. Ghi rõ score chỉ là **decision support**, không phải xác suất tổn thất.
4. Nếu thiếu dữ liệu quan trọng, trạng thái là **INCOMPLETE_CONTEXT** và có người điều tra.
5. Kết quả gán priority phải có **human-review/approval rule** theo severity và risk.
6. Khi có evidence mới, priority được cập nhật nhưng lịch sử quyết định không bị xóa.

### 6.5. Ví dụ tính điểm nội bộ có giới hạn

Giả định tổ chức chấm từng yếu tố từ 1 đến 5:

- **T:** threat/exploitation relevance.
- **E:** attack exposure/reachability.
- **B:** business/security impact.
- **C:** mức **thiếu** hiệu lực của kiểm soát phòng vệ (5 là rất thiếu).
- **U:** urgency do điều kiện thời gian đã được phê duyệt.

Một thang hỗ trợ triage có thể là:

\[
S = 0.25T + 0.20E + 0.30B + 0.15C + 0.10U
\]

Chọn ví dụ một điểm yếu được xác minh có T=4, E=5, B=5, C=4, U=4 thì:

\[
S = 1.0 + 1.0 + 1.5 + 0.6 + 0.4 = 4.5
\]

**Đây không phải công thức chuẩn của CVSS/EPSS/SSVC**, cũng không phải xác suất bị xâm phạm. Trọng số chỉ có giá trị khi tổ chức đã giải thích, thử với case thật và không dùng vượt phạm vi. **Critical gates được áp trước, không bị score thấp hơn override.** Không cho phép “thiếu dữ liệu” tự trở thành T=1 hoặc E=1.

## 7. Ưu tiên dựa trên attack path và chuỗi khai thác

Một security weakness thường không tồn tại riêng lẻ. Một lỗ hổng yêu cầu quyền nội bộ thấp có thể trở nên rất quan trọng khi kết hợp:

- Vendor VPN bị lộ tài khoản.
- Lateral movement tới workload có credential.
- Role over-privileged có quyền đọc secrets.
- KMS hoặc database chịu quyền chung.
- Logging bị tắt nên attacker khó bị phát hiện.

### 7.1. Sơ đồ tình huống

~~~mermaid
flowchart LR
    EXT["Initial access: credential vendor"] --> VPN["Vendor VPN access"]
    VPN --> APP["Ứng dụng internal vulnerable"]
    APP --> TOKEN["Service token quá quyền"]
    TOKEN --> DB["Database chứa dữ liệu khách hàng"]
    APP --> LOG["Detection blind spot"]
    LOG -. "Làm khó phát hiện" .-> TOKEN
~~~

Sơ đồ là một **threat scenario minh họa**, không mô tả cách tấn công từng bước. Nếu scanner chỉ thấy lỗi ứng dụng internal mức medium mà không xem token quá quyền và dữ liệu sau ranh giới, risk priority có thể thấp hơn thực tế.

### 7.2. Chọn “điểm cắt” rủi ro

Các biện pháp có thể cắt chuỗi theo nhiều vị trí:

- Thu hồi/quản lý lại quyền vendor, enforce MFA/PAM.
- Cô lập network path không cần thiết.
- Patch hoặc thay code ở internal API.
- Giảm scope service token và xoay credential nếu cần.
- Bật logging/detection để giảm thời gian không được nhận biết.
- Giới hạn database access và mã hóa/monitoring phù hợp.

Với nguồn lực có hạn, ưu tiên biện pháp **giảm nhiều attack paths, bảo vệ ranh giới quan trọng và có thể kiểm chứng**; nhưng phải tránh bỏ qua fix gốc khi chỉ có mitigation tạm thời.

### 7.3. Chứng minh attack path

Không nên suy ra một đường tấn công chỉ vì trên sơ đồ các hệ thống có mũi tên nối. Cần xem:

- Effective network policy, route, ingress, egress và authentication.
- Actual role permissions và điều kiện token.
- Vulnerable code path thật sự có thể gọi với dữ liệu attacker kiểm soát không.
- Các kiểm soát chặn/phát hiện và test phạm vi hợp lệ.
- Những giả định chưa được chứng minh.

Đường chưa xác định thì ghi **hypothesis**, điều tra theo rủi ro. Một finding có impact lớn dù attack path chưa được chứng minh có thể cần **containment tạm** nhưng không được báo như đã bị khai thác.

## 8. SLA, deadline và tính khẩn cấp

### 8.1. SLA remediation là gì?

**Remediation SLA** trong bài là thời hạn tổ chức/hợp đồng yêu cầu xử lý một loại finding theo điều kiện, risk tier hoặc severity. Nó có thể quy định **bắt đầu tính từ phát hiện, xác nhận, thông báo hoặc công bố** và kết thúc ở **implement fix, verified closure hoặc trạng thái được chấp nhận**; phải định nghĩa cụ thể.

Một số chương trình có **regulatory deadlines** khác với SLA nội bộ. Không được tự dùng deadline nội bộ để thay hạn có hiệu lực bên ngoài.

### 8.2. Mốc thời gian

| Mốc | Cần ghi rõ |
|---|---|
| **Discovered_at** | Tool/nhân sự đầu tiên ghi nhận finding |
| **Confirmed_at** | Thời điểm đã xác minh condition |
| **Exposure_start** | Mốc điểm yếu bắt đầu tồn tại, nếu có bằng chứng; có thể không biết |
| **Triage_decision_at** | Mốc gán priority và risk owner |
| **Mitigated_at** | Biện pháp giảm nguy cơ được kiểm chứng có hiệu lực |
| **Fix_deployed_at** | Đã triển khai correction lên đúng scope |
| **Retest_passed_at** | Bằng chứng control assertion đã đạt |
| **Closed_verified_at** | Closure được phê duyệt theo governance |
| **Exception_expires_at** | Khi quyết định tạm không còn hiệu lực |
| **Next_review_at** | Mốc xem lại threat/priority hoặc evidence freshness |

Không nên “khởi động lại SLA” chỉ vì chuyển ticket sang đội khác hoặc scanner đổi identifier.

### 8.3. Bảng deadline giả định để minh họa

| Priority giả định | Triage/response | Fix hoặc mitigation theo policy | Verification |
|---|---|---|---|
| **P0** | Hành động ngay theo incident playbook | Containment ưu tiên tức thời, fix theo tình trạng | Xác nhận containment và kiểm liên tục |
| **P1** | Escalation nhanh và gán owner rõ | Hạn ngắn do risk owner/pháp lý/phụ thuộc quy định | Retest theo thời điểm deploy, không để chờ vô thời hạn |
| **P2** | Lập kế hoạch theo kỳ đã phê duyệt | Deadline dựa trên risk tier và dependency | Retest trong cửa sổ kiểm soát |
| **P3** | Review định kỳ | Theo backlog có owner, review triggers | Xác minh sau thay đổi và trước closure |

Không gán số ngày tùy tiện thành **“chuẩn bắt buộc”**. Nếu sử dụng ví dụ định lượng trong lớp học, phải ghi **chính sách giả định** và không suy ra nghĩa vụ của mọi tổ chức.

### 8.4. Khi không có patch hoặc việc sửa nguy hiểm

Nhà cung cấp có thể chưa có bản vá, thay đổi có thể làm ngừng dịch vụ hoặc migration cần nhiều bước. Lựa chọn:

1. Xác minh điểm yếu và exposure để không sửa sai mục tiêu.
2. Cô lập/giảm attack surface bằng cấu hình, network hoặc disable feature nếu phù hợp.
3. Tăng monitoring và cảnh báo ở ranh giới liên quan.
4. Cân nhắc rollback, temporary service degradation hoặc emergency change khi an toàn.
5. Làm việc với vendor về workaround và timeline có thể xác minh.
6. Định nghĩa action plan chính với owner, dependency, acceptance criteria, date.
7. Giữ risk acceptance có điều kiện nếu được policy cho phép.
8. Tái đánh giá khi threat, asset hoặc dữ liệu thay đổi.

**Không được chỉ “gia hạn ticket” mà không có phân tích residual risk**; chi phí vận hành và khả năng gián đoạn là biến số quyết định cách sửa, không làm biến mất tác động bảo mật.

## 9. Chọn biện pháp sửa lỗi phù hợp

### 9.1. Các phương án remediation

| Phương án | Điều kiện áp dụng | Cần kiểm chứng |
|---|---|---|
| **Patch/upgrade** | Bản sửa được hỗ trợ, có đường triển khai hợp lệ | Phiên bản thực tế, path không còn lỗi, regression |
| **Configuration hardening** | Quyền, network, logging hoặc setting sai | Effective state, deny/allow test, drift monitor |
| **Disable vulnerable feature** | Tính năng không thiết yếu hoặc có phương án thay | Không còn đường gọi, tác động nghiệp vụ được chấp nhận |
| **Segmentation/temporary isolation** | Có thể giảm reachability mà vẫn vận hành | Network paths, alternate entry points, exceptions |
| **Credential revoke/rotate** | Key/token lộ, tài khoản có nguy cơ bị chiếm | Old token denied, new token least privilege, no residual sessions |
| **WAF/filter/rate limit** | Có dấu hiệu có thể chặn một kiểu traffic đã xác minh | Controlled positive/negative tests, false blocks, bypass paths |
| **Rebuild from trusted artifact** | Runtime/image có thể bị xâm phạm hoặc package lỗi | Provenance, digest, identity/config, data integrity |
| **Architectural change** | Root cause là trust boundary, key sharing hoặc dependency | Threat model, integration tests và migration controls |
| **Vendor workaround** | Chưa có bản vá, vendor cung cấp giảm thiểu | Tài liệu applicability, effective config và risk review |
| **Decommission** | Asset không còn cần thiết | Không còn route, credential, dữ liệu, DNS, billing hay dependency liên quan |
| **Compensating control** | Primary control chưa thể triển khai ngay | Đúng objective, scope, test, monitoring và expiry |

### 9.2. Đừng chọn mitigation chỉ vì nhanh

Một rule WAF có thể chặn một dạng request; nếu admin API có đường nội bộ không qua WAF, control này chưa đạt objective. Một cách hạn chế IP có thể bị sai khi có NAT/VPN/vendor access. Đội assurance cần yêu cầu **đường kiểm tra âm** để thấy bypass bị chặn và **đường kiểm tra dương** để bảo đảm nghiệp vụ được phép vẫn hoạt động.

### 9.3. Rủi ro thay đổi và khả năng rollback

Remediation có thể gây downtime, lỗi dữ liệu hoặc suy giảm dịch vụ. Cần lập kế hoạch an toàn:

- Phạm vi thay đổi và dependency.
- Backup/snapshot hợp lệ, phương án restore khi phù hợp.
- Test ở staging/canary theo khả năng đại diện.
- Change approval và lịch liên quan nghiệp vụ.
- Cách triển khai từng bước, giới hạn blast radius.
- Functional regression, security regression, logging/monitoring.
- Rollback criteria, người quyết định go/no-go.
- Retest chứng minh **cả fix lẫn controls liên quan**.

**Ưu tiên không đồng nghĩa triển khai bất chấp.** Trong rủi ro khẩn cấp, có thể cần containment an toàn trước fix để tránh gây gián đoạn không được kiểm soát.

## 10. Sắp xếp remediation backlog khi nguồn lực có hạn

### 10.1. Priority khác thứ tự triển khai chi tiết

**Priority** nói về tính quan trọng/khẩn cấp của rủi ro, còn **execution sequencing** quyết định công việc nào được làm trước trong một đợt triển khai cụ thể. Hai thứ có thể khác nhau vì:

- Có biện pháp containment phải thực hiện ngay trong khi patch cần change window.
- Một root cause fix có thể giải quyết hàng trăm findings cùng lúc.
- Một patch phụ thuộc upgrade runtime/database hoặc kiểm thử ứng dụng.
- Có công việc cần triển khai theo thứ tự: backup → schema migration → app upgrade → retest.
- Cùng một service owner phải phối hợp nhiều đội để tránh sửa một phần tạo rủi ro mới.
- Một thay đổi có thể xung đột với release khác hoặc ràng buộc availability.
- Một số findings đã có temporary mitigation hữu hiệu trong khi khác hoàn toàn không có.

**Việc P1 khó sửa không khiến nó trở thành P3.** Có thể xử lý P1 bằng containment trước, mở chương trình nâng cấp dài hạn và báo residual risk cho đúng cấp phê duyệt.

### 10.2. Lợi ích giảm rủi ro và công sức

Một ma trận tham khảo:

| Lợi ích giảm rủi ro | Độ khó thực thi | Hướng xử lý |
|---|---|---|
| Lớn, nhanh, dễ kiểm chứng | Thấp | Đưa vào early wins nếu không chặn việc khẩn |
| Lớn, nhiều dependency | Cao | Lập remediation program có milestone và owner quản trị |
| Vừa, giải quyết nhiều findings cùng root cause | Trung bình | Gom thành platform fix/campaign, giữ tracking từng affected asset |
| Thấp, ảnh hưởng ít tài sản ít quan trọng | Thấp | Có thể xử lý theo batch khi an toàn |
| Chưa biết vì evidence thiếu | Chưa rõ | Điều tra có hạn, không đưa vào “low risk” mặc định |

Khi sử dụng effort/benefit để sắp xếp, cần giữ **hard priority gates và các hạn bắt buộc**. Tối ưu effort thuần túy dễ khuyến khích đóng nhiều lỗi nhỏ trong khi vài lỗi nguy hiểm vẫn mở.

### 10.3. Một fix giải quyết nhiều findings

Ví dụ mười ứng dụng dùng chung image chứa một thư viện có điểm yếu:

1. Xác định các image digest/deployments thực sự sử dụng phiên bản bị ảnh hưởng.
2. Sửa base image hoặc dependency lockfile tại nguồn.
3. Build và kiểm artifact provenance.
4. Cập nhật lần lượt các dịch vụ với canary/rollout.
5. Kiểm tra các digest ở production đã thay đổi.
6. Chạy scan lại trên artifact và effective runtime.
7. Ghi tình trạng **từng affected deployment**; không đóng tất cả khi image mới chỉ được build.
8. Thêm CI dependency policy để ngăn tái xuất hiện.

**Root-fix campaign** giúp tiết kiệm nhân lực, nhưng metrics phải phân biệt **một action chung** và **mười đơn vị cần verified closure**.

### 10.4. Dependency graph cho remediation

~~~mermaid
flowchart TD
    P1["Finding: vulnerable runtime"] --> A["Kiểm tra ứng dụng và tương thích"]
    P1 --> M["Containment: giảm phơi nhiễm"]
    A --> B["Build image từ base mới"]
    B --> C["Deploy canary"]
    C --> D["Đo chức năng, latency, security"]
    D --> E{"Đủ điều kiện go?"}
    E -- "Không" --> F["Rollback / sửa / rerun test"]
    F --> C
    E -- "Có" --> G["Rollout toàn scope"]
    G --> H["Scan runtime + verify CVE/path"]
    H --> I["Verified closure từng deployment"]
    M --> H
~~~

Một ticket có thể được thực hiện thành nhiều subtask, nhưng risk finding vẫn tồn tại đến khi scope được kiểm chứng đạt hoặc có quyết định thay thế hợp lệ.

### 10.5. Bảo vệ nguồn lực xử lý P0/P1

Trong môi trường có nhiều đội, nên có:

- **Emergency/on-call capacity** cho sự cố và security controls trọng yếu.
- Quyền đưa critical fix vào change calendar/hotfix path.
- Kênh escalation khi P1 vượt capacity của một service owner.
- Năng lực hỗ trợ cross-team với vendor, legal, privacy hoặc infrastructure.
- Quy tắc hoãn công việc ít quan trọng khi risk vượt ngưỡng.
- Dashboard blocker và hiệu lực mitigation, không chỉ số ticket assigned.
- Quyết định về việc tạm giảm chức năng hoặc tắt dịch vụ rủi ro cao.

Nếu nhiều P1 tồn tại quá lâu, đây có thể là vấn đề **quản trị năng lực và kiến trúc**, không chỉ lỗi “chủ ticket chưa chăm”.

## 11. Quy trình triage có thể tái lập và audit được

### 11.1. Bước 1 — Kiểm tra finding đúng sự thật

Một scanner báo CVE chưa đủ. Cần xác định:

- CVE/advisory có áp dụng đúng package/version/build không?
- Vendor có backport patch khiến version string vẫn giống bản trước không?
- Package được build nhưng không được load hoặc không đi vào deployment?
- Lỗ hổng phụ thuộc một feature/configuration có thực sự được bật?
- Asset vẫn active hay đã được retired với bằng chứng?
- Scanner source có stale results, false mapping, missing metadata không?
- Nếu là audit finding, criterion có hiệu lực và scope đúng không?

**False positive phải có evidence**, không đơn thuần “developer nói không khai thác được”.

### 11.2. Bước 2 — Đánh giá threat và điều kiện khẩn

Nguồn:

- Evidence incident/hunting của tổ chức.
- Advisories của vendor và security researchers có căn cứ.
- Threat intelligence đã được đánh giá độ tin cậy.
- Tín hiệu known exploitation hoặc exploit availability.
- Tình trạng network/external exposure và attack path thực tế.

Một dấu hiệu exploitation đã xác nhận trên production có thể yêu cầu **điều phối incident response trước khi tiếp tục backlog scoring**.

### 11.3. Bước 3 — Đánh giá impact và controls

Tối thiểu xem:

- Service và BIA criticality.
- Dữ liệu, privilege, quyền di chuyển sang môi trường khác.
- CIA impact và blast radius.
- Failure domains chung và dependency trọng yếu.
- Biện pháp chặn, detection và khả năng phục hồi có bằng chứng.
- Hậu quả nghiệp vụ khi xử lý/không xử lý.

Với lỗi thiếu logging, impact liên quan **visibility và forensic readiness** có thể rất lớn dù không trực tiếp cấp quyền attacker.

### 11.4. Bước 4 — Xác định priority, deadlines và next action

Output triage nên có:

- Priority P0/P1/P2/P3 hoặc taxonomy nội bộ.
- Severity và confidence riêng.
- Lý do/critical trigger, evidence references.
- Remediation owner, risk owner và responder nếu khẩn.
- Immediate mitigation/containment.
- Long-term corrective action và dependency.
- Deadline/next review theo chính sách.
- Retest acceptance criteria.
- Những dữ liệu chưa xác định và ai phải bổ sung.

### 11.5. Bước 5 — Review theo thay đổi

Ưu tiên phải được đánh giá lại khi:

- Có dấu hiệu lỗ hổng đang bị khai thác.
- Một asset được đưa ra Internet hoặc cấp quyền cao.
- Thông báo vendor thay đổi điều kiện ảnh hưởng.
- Một control bù trừ bị tắt hoặc không còn hiệu lực.
- Hệ thống đổi business criticality, dữ liệu hoặc số người dùng.
- Phát hiện phạm vi rộng hơn/nhỏ hơn từ kết quả điều tra.
- Một exception quá hạn.
- Bản vá khả dụng hoặc có phương án giảm thiểu mới.
- Sự cố hoặc kiểm thử cho thấy attack path khả thi.

Không giữ priority “low” của năm trước khi asset đã chuyển từ sandbox sang production.

## 12. Mẫu hồ sơ remediation priority có bằng chứng

### 12.1. Record ví dụ YAML

~~~yaml
finding_id: "REM-F-2026-041"
source:
  type: "cloud-control-assessment"
  reference: "assessment/2026-11-28/iam-path"
  observed_at: "2026-11-28T08:00:00Z"
description: >
  Interactive local administrative access to the payment
  production account is not covered by required MFA policy.
affected_scope:
  business_service: "payments"
  environment: "production"
  account: "prod-account-example"
  access_path: "local-interactive-admin"
  data_classification: "restricted"
criterion:
  control_id: "IAM-PRIV-01"
  requirement_ref: "SEC-POL-ACCESS-v4"
  required_condition: "MFA enforced for all in-scope privileged login paths"
verification:
  status: "CONFIRMED"
  method: "effective-policy-and-controlled-auth-test"
  evidence_refs:
    - "REM-EV-2026-101"
    - "REM-EV-2026-102"
risk:
  technical_severity: "MEDIUM_BY_INTERNAL_ASSESSMENT"
  exploitation_status: "NO_CONFIRMED_ACTIVE_EXPLOITATION"
  exposure: "REACHABLE_FROM_APPROVED_ADMIN_NETWORK"
  business_impact: "HIGH"
  risk_priority: "P1"
  priority_reason: >
    Privileged access to critical production is not protected
    by a mandatory authentication control.
  confidence: "HIGH_FOR_CONDITION"
  observed_incident: "NOT_ESTABLISHED"
controls:
  existing:
    - "admin-network-access-restriction"
  effectiveness: "PARTIALLY_VERIFIED"
  limitations:
    - "Network restriction does not replace required MFA"
response:
  immediate_action: "Disable unnecessary local interactive access"
  corrective_action: "Enforce MFA and fix provisioning template"
  preventive_action: "Add privileged-path inventory gate and drift alert"
  control_owner: "identity-platform"
  risk_owner: "payments-security-owner"
  escalation: "security-risk-review"
  due_at: "2026-12-02T00:00:00Z"
  next_review_at: "2026-11-29T00:00:00Z"
retest:
  assertion: "No unapproved interactive privileged path bypasses MFA"
  expected_evidence:
    - "Effective policy export"
    - "Approved bypass denial test"
    - "Full privileged-path inventory reconciliation"
  required_result: "PASS"
status: "OPEN"
history:
  - action: "priority-assigned"
    at: "2026-11-28T09:00:00Z"
    decision_owner_role: "security-assurance-lead"
~~~

Đây là **bản ghi giả định** để học cấu trúc quyết định, không phải finding thật. **MEDIUM technical severity + P1 priority** được dùng để cho thấy tầm quan trọng của context. Các giá trị deadline và quyền phê duyệt phải được thay bằng chính sách thực tế khi triển khai.

### 12.2. Tại sao cần tách nhiều trường?

- **Severity:** tình trạng kỹ thuật hoặc mức nghiêm trọng theo phương pháp.
- **Risk priority:** thứ tự xử lý và tính khẩn trong ngữ cảnh.
- **Finding status:** việc đang được kiểm chứng, sửa hoặc đóng.
- **Remediation method:** cách giải quyết condition/root cause.
- **Residual risk:** rủi ro sau mitigation, không xóa bằng nhãn P2.
- **Evidence confidence:** mức chắc chắn về observation.
- **Risk decision:** cơ quan nào đã phê duyệt trì hoãn/ngoại lệ.
- **Retest verdict:** assertion đã đạt hay chưa.

Nếu gộp thành một trường **“risk=high”**, auditor sẽ khó hiểu vì sao công việc được ưu tiên và khi nào có thể đóng.

### 12.3. Lịch sử quyết định và tránh ghi đè

Khi priority giảm từ P1 xuống P2 sau khi cô lập network có kiểm chứng, nên lưu:

1. Priority cũ, lý do và thời điểm.
2. Control bù trừ mới, evidence test và scope.
3. Residual risk assessment.
4. Người có thẩm quyền thay priority.
5. Deadline và review trigger mới.
6. Finding vẫn mở nếu root cause chưa sửa.
7. Test monitor cho isolation để alert khi exposure thay đổi.

Không sửa lại báo cáo lịch sử rằng finding “từ đầu đã P2”.

## 13. Decision matrix và pseudocode ưu tiên

### 13.1. Decision tree có guardrails

~~~mermaid
flowchart TD
    F["Finding hợp lệ và thuộc scope?"] --> A{"Đã xác minh?"}
    A -- "Chưa" --> V["Điều tra có hạn / containment nếu nguy cơ lớn"]
    A -- "Rồi" --> X{"Có bằng chứng khai thác đang hoạt động?"}
    X -- "Có" --> IR["Incident triage + P0/P1 theo tác động"]
    X -- "Không" --> C{"Critical control boundary đang không đạt?"}
    C -- "Có" --> URG["P1 hoặc escalation theo policy"]
    C -- "Không" --> D{"Known exploitation + reachable + impact cao?"}
    D -- "Có" --> URG
    D -- "Không" --> R["Đánh giá risk context / controls / deadline"]
    R --> T["P1/P2/P3 theo rule được phê duyệt"]
    IR --> OWN["Owner + containment + verification"]
    URG --> OWN
    T --> OWN
    V --> OWN
~~~

Đường quyết định phải **chỉ rõ dữ liệu bắt buộc**. Ví dụ unknown reachability ở một privileged system không được tự hiểu là “không reachable”.

### 13.2. Pseudocode dùng để review logic

~~~text
function decide_priority(finding, context):
    if not finding.verified:
        return NEEDS_VALIDATION(
            deadline = context.validation_due,
            immediate_controls = context.safe_containment_if_warranted
        )

    if context.confirmed_active_incident:
        return EMERGENCY_IR_PATH

    if context.critical_policy_gate_failed:
        return URGENT_P1_WITH_ESCALATION

    if context.known_exploited
       and context.exploitable_path_verified
       and context.business_impact_is_high:
        return URGENT_P1_WITH_ESCALATION

    if context.required_risk_fields_missing:
        return INCOMPLETE_CONTEXT_NEEDS_REVIEW

    return approved_risk_based_matrix(
        technical_severity = finding.severity,
        threat_relevance = context.threat_relevance,
        exposure = context.exposure,
        business_impact = context.business_impact,
        compensating_control_confidence = context.control_confidence,
        obligations = context.applicable_requirements
    )
~~~

Pseudocode trên không quyết định tự động việc **tắt production**, cũng không thay thế thẩm quyền xử lý incident. Tổ chức phải kiểm thử decision logic bằng các trường hợp đối nghịch và đánh giá ngưỡng.

### 13.3. Một số test case cho decision logic

| Case | Dữ liệu đã có | Kết quả hợp lý |
|---|---|---|
| A | Confirmed exploitation + production asset | Emergency/incident pathway |
| B | Verified unprotected privileged access on critical service | Urgent P1/escalation theo policy |
| C | KEV match nhưng asset không có product/version bị ảnh hưởng | Xác minh N/A với evidence, không tự gán P1 |
| D | EPSS cao nhưng asset chỉ có môi trường cô lập, đường khai thác không có | Không mặc định P1; theo risk context đã xác minh |
| E | Severity high, asset không có inventory/owner | Validation và escalation asset ownership |
| F | Severity medium, public API chứa dữ liệu nhạy cảm, authz bị bypass | Có thể P1 theo impact/exposure |
| G | WAF mitigation đã triển khai nhưng chưa thử bypass | Chưa giảm risk priority chỉ vì có rule |
| H | Fix deployed nhưng scan mới chưa chạy | FIX_IMPLEMENTED/READY_FOR_RETEST, chưa CLOSED_VERIFIED |

**Sức mạnh của rule engine là tính nhất quán và truy vết**, không phải khả năng thay judgment trong mọi tình huống.

## 14. Ưu tiên các loại finding khác nhau trên cùng backlog

### 14.1. Không so sánh CVSS với mọi control gap như cùng thang

Một chương trình remediation có thể đồng thời xử lý:

1. CVE trên API.
2. MFA bypass ở cloud admin.
3. Log source thiếu của một account trọng yếu.
4. Backup restore failure.
5. Audit finding về access review quá hạn.
6. Risk của nhà cung cấp có access production.
7. Cấu hình secret exposed trong repo.
8. Container image outdated nhưng không triển khai.

Các mục có thể không có CVSS. Cần một **risk-based priority framework chung**, trong đó CVSS là một input riêng cho các vulnerability phù hợp.

### 14.2. Ví dụ so sánh quyết định

| Finding giả định | Severity đầu vào | Context | Priority tham khảo |
|---|---|---|---|
| Token admin production bị lộ, còn hiệu lực | Không có CVSS | Cred có thể được dùng ngay, blast radius lớn | P0/P1 + IR triage |
| API authorization gap cho dữ liệu khách hàng public | Technical finding mức cao | Path reachable, data sensitivity cao | P1 |
| Library CVSS rất cao trên binary không được deploy | CVSS cao | Không có deployed path được chứng minh | P3/N/A có evidence hoặc fix khi đưa vào scope |
| Log IAM không tới SIEM ở account quản trị trung tâm | Control gap | Blind spot cho thay đổi đặc quyền, critical service | P1/P2 tùy scope và threat |
| Restore test thất bại cho service có RTO nghiêm ngặt | Resilience finding | Business interruption impact cao | P1/P2 tùy BIA và khả năng thay thế |
| Quarterly access review trễ ở test environment ít nhạy cảm | Audit finding | Phạm vi nhỏ, không có dữ liệu thật, policy áp dụng | P2/P3 theo nghĩa vụ và risk |
| Legacy service P1 có containment hữu hiệu, fix cần migration | Original P1 | Control bù trừ verified, có milestone/expiry | Residual priority review; không tự đóng |

Tất cả priority trong bảng chỉ nhằm minh họa **quy trình ra quyết định**, không phải hướng dẫn gán mức tự động.

### 14.3. Một finding có nhiều dimensions

Ví dụ lỗi thiếu logging không phải “lỗ hổng khai thác trực tiếp” nhưng có thể:

- Làm tổ chức không nhận biết credential bị lộ.
- Cản trở điều tra khi incident xảy ra.
- Không đáp ứng nghĩa vụ lưu audit event.
- Cho attacker thời gian duy trì persistence lâu hơn.
- Làm evidence của các controls khác không đáng tin.

Nó phải được đánh giá theo **security objective và risk scenario**, không bị hạ xuống thấp vì không có CVSS.

## 15. Phân biệt xác nhận điểm yếu với bằng chứng rủi ro

### 15.1. Chứng cứ kỹ thuật và kết luận

| Claim | Bằng chứng có thể hỗ trợ | Không được suy ra |
|---|---|---|
| Thành phần có version bị ảnh hưởng | Package inventory, digest, runtime check, advisory | Exploitable path đã được attacker dùng |
| API public reachable | Route, policy, controlled access test | Có lỗ hổng dữ liệu trong mọi endpoint |
| WAF rule được bật | Configuration export | WAF chặn mọi bypass path |
| MFA được enforce trên SSO | Effective SSO policy và auth test | Local/break-glass không tồn tại |
| Scanner không còn finding | Scan với asset/runtime scope tương đương | Vulnerability đã chắc chắn sửa nếu asset mất khỏi scan |
| Credentials đã được rotate | Key lifecycle, revoke log, deny test | Attacker không giữ session/token khác |
| Backup job thành công | Job log, backup object | Restore được, giải mã được, RTO/RPO đạt |
| Patch đã merge | VCS commit, CI result | Production đã triển khai bản fix |
| Không có alert | Query result ở SIEM | Không có tấn công, rule/telemetry đều đầy đủ |

Từ góc nhìn assurance, những khoảng “chưa được chứng minh” có thể ảnh hưởng priority, nhưng phải ghi thành **uncertainty** hoặc **evidence gap**, không biến thành một kết luận chắc chắn ngược lại.

### 15.2. Tình huống uncertainty có impact cao

Nếu asset chủ chốt không có network inventory và không biết có public exposure không, tổ chức có thể:

- Hạn điều tra ngắn, phối hợp cloud/network owners.
- Giảm quyền hoặc hạn chế ingress tạm trong phạm vi an toàn.
- Tăng monitoring và quan sát external reachability được cấp phép.
- Ghi priority **provisional** khi cần bảo vệ trước.
- Review lại ngay sau khi có evidence.

**Không cho unknown một điểm rủi ro thấp mặc định.** Nhưng cũng không ghi “đang public exploitable” khi chưa có bằng chứng.

## 16. Quản lý rủi ro khi trì hoãn hoặc chấp nhận ngoại lệ

### 16.1. Ngoại lệ phải được giới hạn và có người chịu trách nhiệm

Một exception record tối thiểu:

~~~yaml
exception_id: "REM-EX-2026-014"
finding_id: "REM-F-2026-042"
control_reference: "PLAT-PATCH-001"
scope:
  service: "legacy-billing"
  environment: "production"
  affected_component: "runtime-example"
reason: "Vendor upgrade requires an application migration"
risk:
  original_priority: "P1"
  residual_priority: "P1_REVIEW_REQUIRED"
  rationale: "Critical service with potential reachable path"
compensating_controls:
  - control: "Restricted ingress to approved service consumers"
    evidence_ref: "REM-EV-2026-111"
    verified: true
  - control: "Enhanced detection of relevant activity"
    evidence_ref: "REM-EV-2026-112"
    verified: true
remediation:
  owner_role: "billing-platform-owner"
  plan_ref: "REM-PLAN-2026-014"
  next_milestone: "migration-canary"
  milestone_due: "2026-12-05"
approval:
  risk_owner_role: "billing-risk-owner"
  status: "PENDING_AUTHORIZED_REVIEW"
  valid_until: null
reassessment_triggers:
  - "Active exploitation evidence"
  - "Public reachability changes"
  - "Mitigation fails"
  - "New patch becomes deployable"
finding_status: "OPEN"
~~~

Bản ghi minh họa cố ý có **approval PENDING** và **valid_until null** để cho thấy nó **chưa phải ngoại lệ có hiệu lực**. Một hệ thống thật không nên chuyển finding sang RISK_ACCEPTED khi chưa có approval và expiry theo policy.

### 16.2. Risk acceptance không thay đổi nghĩa vụ áp dụng

Một risk owner có thể chấp thuận vận hành tạm với biện pháp bù trừ nếu chính sách cho phép. Nhưng:

- Không được ghi control PASS khi assertion chưa đạt.
- Không được coi phê duyệt nội bộ là miễn nghĩa vụ pháp lý/hợp đồng.
- Không được để ngoại lệ bao phủ nhiều asset hơn phạm vi đã đánh giá.
- Không được kéo dài expiry vô thời hạn mà không có review evidence.
- Không được âm thầm giảm priority mà không giữ audit trail.

Cần tham vấn bộ phận có thẩm quyền nếu rủi ro liên quan quyền riêng tư, hợp đồng, lĩnh vực được quản lý hoặc nghĩa vụ thông báo.

### 16.3. Điều kiện tái đánh giá ngoại lệ

Ngoại lệ phải được review sớm nếu:

- Lỗ hổng bị khai thác trong thực tế hoặc có alert phù hợp.
- Asset chuyển môi trường, mở network access hoặc nhận thêm dữ liệu.
- Compensating control không còn đạt kiểm thử.
- Có patch khả thi hoặc alternative architecture mới.
- Deadline, legal/contract requirement hoặc risk appetite đổi.
- Incident ảnh hưởng service hoặc dependency.
- Người phê duyệt/owner không còn đảm nhận trách nhiệm.

Một ngoại lệ hết hạn mà chưa được sửa/đánh giá lại là **một trạng thái quản trị rủi ro phải escalation**, không tự động nối hạn.

## 17. Retest và bằng chứng đóng finding

### 17.1. Định nghĩa “đã sửa” phải gắn với assertion

Với một finding về missing MFA:

- **Evidence fix:** policy change, IAM deploy, account inventory.
- **Test đúng:** effective enforcement trên mọi privileged interactive paths trong scope.
- **Negative test:** đường bypass không được phép bị từ chối.
- **Positive test:** admin hợp lệ vẫn đăng nhập đúng flow.
- **Population check:** không bỏ sót local/break-glass account.
- **Result:** PASS/FAIL/INCONCLUSIVE có scope, timestamp và evidence ID.

Với vulnerability code:

- Phiên bản/commit/image digest mang fix được deploy lên đúng environment.
- Lệnh/build output hoặc scanner cho thấy package thật thay đổi.
- Reproduction test theo đường lỗi được phê duyệt không còn xảy ra.
- Các security/functional regression liên quan đạt.
- Không còn deployment cũ đang phục vụ traffic hoặc đã có acceptance rõ.

**Retest không nên chỉ lặp lại cùng một scanner nếu scanner không kiểm được ngữ nghĩa lỗi.** Có thể cần kiểm code path, config effective hoặc test end-to-end.

### 17.2. Correction và phòng tái diễn

Một finding có thể PASS ở asset hiện tại nhưng root cause vẫn mở:

- Sửa một IAM policy nhưng provisioning workflow còn tạo sai principal.
- Patch một container nhưng base image mới tiếp tục chứa dependency cũ.
- Bật log cho một account nhưng cloud account mới không có onboarding gate.
- Sửa một câu SQL injection nhưng library/template cùng pattern còn lỗi.
- Restore test thành công một database nhưng DR plan chưa bao phủ KMS và broker.

Nên phân biệt:

1. **Condition corrected:** asset/scope hiện tại đáp ứng.
2. **Root cause addressed:** quy trình/kiến trúc tạo lỗi đã được sửa.
3. **Regression prevention verified:** thử trường hợp mới và kiểm drift hoạt động.
4. **Audit finding closure:** thực hiện theo acceptance criteria đã thỏa thuận và scope được phê duyệt.

Không bắt buộc mọi finding phải đợi các chương trình cải tiến dài hạn để đóng nếu tiêu chí được phê duyệt khác; nhưng những preventive actions chưa hoàn tất phải có owner và tracking riêng, không biến mất.

### 17.3. Các trạng thái sau retest

| Tình trạng | Cách báo cáo |
|---|---|
| Fix triển khai, chưa test | **FIX_IMPLEMENTED / AWAITING_VALIDATION** |
| Scan không chạy do source mất | **INCONCLUSIVE / TELEMETRY_GAP** |
| Test confirm lỗi vẫn còn | **RETEST_FAIL**, finding tiếp tục mở |
| Một phần scope đạt, phần khác chưa | **PARTIAL**, giữ danh sách affected/unknown |
| Fix và control assertion đạt trong scope | **CLOSED_VERIFIED** sau approval |
| Asset đã retired với evidence đầy đủ | **DECOMMISSIONED_VERIFIED** theo criterion |
| Có risk acceptance hợp lệ còn hạn | **RISK_ACCEPTED**, theo dõi expiry |
| Tái xuất hiện sau đóng | **REOPENED** hoặc finding liên quan với lịch sử |

### 17.4. Evidence manifest

~~~yaml
retest_id: "REM-RT-2026-019"
finding_id: "REM-F-2026-041"
tested_at: "2026-12-01T10:00:00Z"
criterion_ref: "SEC-POL-ACCESS-v4"
scope:
  service: "payments"
  environment: "production"
  required_paths: 18
  evaluated_paths: 18
methods:
  - "Reconcile interactive admin inventory"
  - "Check effective MFA enforcement"
  - "Run approved positive and negative auth tests"
evidence:
  - "REM-EV-2026-151"
  - "REM-EV-2026-152"
  - "REM-EV-2026-153"
results:
  verified_pass: 18
  fail: 0
  unknown: 0
  retest_verdict: "PASS_WITH_SCOPE"
limitations:
  - "Other services and tenants were not included"
assessor_role: "independent-security-assurance"
closure_approved_by_role: "authorized-audit-reviewer"
~~~

Giá trị mẫu chỉ minh họa cấu trúc. Trong thực tế, **lưu nguồn inventory, test scripts/results, audit trail và phạm vi đủ để tái kiểm**, không chỉ điền các con số rồi ký.

### 17.5. Cần tránh closure giả

- Đóng do elapsed time, không do fix.
- Đóng sau khi nhấn “Accept risk” nhưng không có phê duyệt.
- Đóng vì asset bị tắt scanner mà không retired.
- Đóng sau khi tag image được cập nhật nhưng các pod cũ vẫn chạy.
- Đóng vì backup job chạy lại nhưng restore test chưa có.
- Đóng vì SIEM nhận được một event trong khi required sources còn thiếu.
- Đóng vì external exposure giảm tạm thời nhưng control bù trừ chưa được kiểm.
- Đóng sau khi rule test PASS trong sandbox, trong khi production vẫn dùng rule khác.

**Verified closure phải là kết luận có bằng chứng trong scope**, không phải nhãn trạng thái hành chính.

## 18. Continuous remediation: biến lỗi thành control tốt hơn

### 18.1. Remediation không nên đợi audit kế tiếp

Một vòng vận hành:

~~~mermaid
flowchart LR
    INV["Inventory + threat/risk"] --> FIND["Findings + detections"]
    FIND --> PRI["Risk-based priority + owner"]
    PRI --> MIT["Containment / fix plan"]
    MIT --> CHANGE["Deploy + change evidence"]
    CHANGE --> RET["Retest / control assertion"]
    RET --> DEC{"Đạt?"}
    DEC -- "Không" --> PRI
    DEC -- "Có" --> CLOSE["Verified closure"]
    CLOSE --> ROOT["Root-cause preventive controls"]
    ROOT --> MON["Continuous test / drift monitoring"]
    MON --> INV
~~~

### 18.2. Đưa bài học vào hệ thống delivery

| Finding điển hình | Preventive control phù hợp |
|---|---|
| Cloud account mới thiếu audit log | IaC provisioning gate + synthetic event test |
| Service token quá quyền | Token scope policy, approval và effective permission test |
| Library lỗi tái xuất hiện | Dependency pin/update, SBOM và CI security test |
| Scanner bỏ sót tài sản mới | Asset inventory reconciliation và missing-source alert |
| Network ingress mở sai | Policy-as-code + runtime drift detector |
| Backup chưa restore được | Restore automation và periodic exercise |
| Detection rule tắt ngoài quy trình | Detection-as-code review, synthetic regression |
| Exception quá hạn | Exception register, expiry notification và risk escalation |
| Vendor hỗ trợ còn quyền sau hợp đồng | Offboarding automation + access verification |

### 18.3. Reassessment triggers

- Vendor advisory/CVE exploitation evidence đổi.
- Asset chuyển criticality, data classification hoặc network exposure.
- New cloud account, cluster, dependency hoặc third-party integration.
- Incident cho thấy threat scenario chưa được đánh giá.
- CVSS/environment/EPSS/SSVC decision input được cập nhật có ý nghĩa.
- Patch/workaround mới có hoặc mitigation bị vô hiệu.
- Control version, security requirement hay SLA đổi.
- Exception hết hạn, root cause tái diễn hoặc test regression fail.

Tái đánh giá không chỉ để **tăng priority**; có thể hạ priority khi evidence xác minh tình huống ít rủi ro hơn, nhưng phải giữ lịch sử, thẩm quyền và lý do.

## 19. Case study 1: CVSS rất cao ở thư viện không deploy so với lỗi phân quyền production

### 19.1. Bối cảnh

Đội bảo mật của một doanh nghiệp thương mại điện tử nhận hai findings trong cùng buổi:

**Finding A:** dependency trong một repository thử nghiệm có advisory CVSS base **9.8**. Scanner ghi nhận phiên bản vulnerable trong lockfile. Repo chỉ được dùng cho một proof-of-concept đã dừng từ nhiều tháng trước; chưa có bằng chứng package được deploy vào hệ thống production.

**Finding B:** một endpoint API quản lý đơn hàng ở production có lỗi kiểm tra quyền được đánh technical severity **Medium** trong hệ thống nội bộ. Kiểm thử được cấp phép cho thấy role hỗ trợ có thể xem dữ liệu đơn hàng vượt phạm vi khách hàng được gán. Endpoint nằm sau authentication nhưng accessible từ luồng hỗ trợ nghiệp vụ; dữ liệu có tính nhạy cảm.

Mỗi finding đều cần xử lý, nhưng **độ khẩn không thể xác định chỉ từ 9.8 so với Medium**.

### 19.2. Triage từng finding

| Yếu tố | Finding A — CVSS 9.8 trong repo thử | Finding B — authorization ở API production |
|---|---|---|
| Technical severity | Critical theo nguồn advisory | Medium theo đánh giá nội bộ ban đầu |
| Asset criticality | Chưa có deployment production được chứng minh | API production xử lý dữ liệu khách hàng |
| Reachability | Chưa xác định runtime có đường khai thác | Test cho thấy truy cập vượt quyền với role cụ thể |
| Potential impact | Phụ thuộc việc package có được load/deploy hay không | Truy cập thông tin ngoài phạm vi được phép |
| Active exploitation | Không có bằng chứng | Không có bằng chứng |
| Control confidence | Inventory/repo chưa chứng minh toàn deployment | Controlled authz test đã xác nhận condition |
| Hành động | Xác minh SBOM/image digest/deployment, sửa dependency nếu cần | Giảm quyền/giới hạn endpoint, sửa authorization, retest |
| Priority tham khảo | **Needs validation**, có thể thấp nếu chứng minh không deploy | **P1** theo data impact/exposure |

Finding A có thể được **NOT_APPLICABLE cho production** nếu chứng minh rõ thư viện không hiện diện/không chạy trong mọi deployment thuộc scope; nhưng vẫn có thể là dependency hygiene task của repo dev. Không được mặc định N/A chỉ do nhãn “demo”.

Finding B không có CVSS cao nhưng có **confirmed authorization gap** trong production. Nó đáng ưu tiên do rủi ro dữ liệu thực tế, dù yêu cầu authentication làm phức tạp hơn cách khai thác.

### 19.3. Quy trình xử lý Finding B

1. Giữ evidence kiểm thử đã được phép, không thu/chia sẻ dữ liệu khách hàng quá mức cần thiết.
2. Kiểm tra phạm vi endpoint và role; xác định những biến thể API khác có logic tương tự.
3. Áp biện pháp tạm như hạn chế role hoặc disable route rủi ro theo phê duyệt nghiệp vụ.
4. Sửa quyền ở lớp server-side authorization, không chỉ ẩn nút giao diện.
5. Xác định object-level permission theo tenant/owner/resource.
6. Chạy negative test với role được phép và không được phép; kiểm regression với các API liên quan.
7. Triển khai có canary/rollback khi cần.
8. Retest production theo phương pháp an toàn hoặc bằng chứng runtime tương đương đã được phê duyệt.
9. Mở rộng phòng ngừa bằng security unit tests cho boundary này.

**Đóng finding** chỉ khi control assertion về phân quyền được kiểm chứng trong phạm vi, không khi UI không còn hiện nút xem dữ liệu.

### 19.4. Kết luận assurance

Một báo cáo hợp lý:

> Finding B được ưu tiên khẩn hơn Finding A vì điều kiện truy cập vượt quyền tại production đã được xác nhận và liên quan dữ liệu khách hàng; Finding A cần xác minh deployment/reachability trước khi kết luận mức rủi ro cho production. CVSS cao là đầu vào quan trọng nhưng không tự thay thế bằng chứng về phạm vi và tác động.

Không tuyên bố đã xảy ra data breach chỉ từ một test xác minh lỗi phân quyền. Hoạt động truy cập trái phép thực tế cần chứng cứ và incident handling riêng.

## 20. Case study 2: vulnerability đã bị khai thác ngoài thực tế và bản vá có rủi ro gián đoạn

### 20.1. Tình huống

Một dịch vụ internet-facing dùng một phiên bản sản phẩm có lỗ hổng trùng một advisory đáng tin, được ghi nhận có hoạt động khai thác ngoài thực tế. Vendor cung cấp bản vá nhưng đội kỹ thuật lo ngại upgrade làm hỏng tích hợp production. Service có business criticality cao; không có bằng chứng rằng tài sản nội bộ đã bị tấn công.

### 20.2. Các quyết định cần phân biệt

| Quyết định | Câu hỏi | Chủ thể |
|---|---|---|
| **Incident triage** | Có dấu hiệu đã bị khai thác trong môi trường mình không? | IR/SOC |
| **Exposure validation** | Endpoint và config nào thật sự reachable/vulnerable? | App/platform/security |
| **Immediate mitigation** | Có thể hạn chế đường nguy hiểm ngay mà vẫn giữ dịch vụ thiết yếu? | Service owner + platform |
| **Priority** | Tín hiệu known exploitation, exposure và impact có kích hoạt P1? | Security/risk triage |
| **Patch deployment** | Cần test integration, canary và rollback nào? | Engineering/change owner |
| **Residual risk acceptance** | Nếu chưa vá kịp, ai có quyền phê duyệt thời hạn và control thay thế? | Risk owner |
| **Closure** | Bản vá có ở runtime và exploit path đã được kiểm chứng loại bỏ? | Assurance/test owner |

### 20.3. Timeline vận hành minh họa

Các timestamp dưới đây là **ví dụ giả định**, không phải SLA chuẩn:

| Mốc | Hành động | Evidence |
|---|---|---|
| 08:00 | Threat intel/advisory được ingest | Advisory reference + timestamp |
| 08:20 | Inventory xác nhận hai instance production bị ảnh hưởng | Asset/image/config evidence |
| 08:40 | Kiểm tra exposure và các rule/network controls | Effective route/ACL + test |
| 09:00 | Priority P1, owner và executive escalation theo policy | Decision log |
| 09:30 | Hạn chế một đường truy cập không thiết yếu, test deny | Mitigation evidence |
| 11:00 | Build patch, kiểm integration và canary | Build provenance + change |
| 13:00 | Rollout sau go/no-go, đo sức khỏe nghiệp vụ | Deployment/health evidence |
| 13:30 | Security retest, inventory xác nhận không còn instance cũ | Retest + coverage |
| 14:00 | Review root cause, cập nhật dependency patch process | Preventive actions |

### 20.4. Khi patch chưa thể triển khai

Nếu integration regression FAIL ở canary:

- Dừng rollout theo điều kiện change control.
- Xác minh mitigation tạm có đúng scope và không bị bypass.
- Kiểm tra tăng cường log/detection và evidence phục vụ IR.
- Báo risk owner về phơi nhiễm còn lại, timebox và lộ trình fix.
- Phân tích rollback, upgrade sequencing hoặc cách tắt tính năng vulnerable.
- Không ghi **“vulnerable resolved”** chỉ vì một route đang bị chặn.
- Không giữ một biện pháp workaround mãi mãi mà không retest khi threat/path đổi.

**Bài học:** priority cao có thể yêu cầu **khống chế nguy cơ ngay** trước khi nâng cấp, nhưng không biện minh cho triển khai patch vội vàng làm mất khả năng phục hồi hoặc phá dữ liệu.

## 21. Case study 3: điểm mù logging và backup khi phải chọn việc nào trước

### 21.1. Bối cảnh

Một nền tảng thanh toán có hai findings cùng kỳ:

- **F-LOG:** cloud account production mới không gửi thay đổi IAM vào kho audit tập trung; các collector cũ vẫn healthy. Control requirement yêu cầu security audit event và mất nguồn phải được nhận biết.
- **F-DR:** backup database chạy hàng ngày, nhưng test restore vào recovery account thất bại vì quyền KMS không đúng. BIA yêu cầu RTO/RPO nghiêm ngặt; chưa có sự cố mất site.

Đội platform chỉ có một nhóm nhân sự hỗ trợ thay đổi ngay trong ngày. Câu hỏi không phải “lỗi logging hay DR có severity lớn hơn theo scanner”, mà là **rủi ro nào cần containment trước và công việc nào có thể song song**.

### 21.2. Threat và impact

| Yếu tố | F-LOG | F-DR |
|---|---|---|
| Rủi ro trực tiếp | Mất visibility đối với hành vi quản trị của account | Không khôi phục được dịch vụ khi cần DR |
| Asset criticality | Account có quyền quan trọng | Database thuộc service critical |
| Phép kiểm đã có | Controlled IAM event không tới SIEM | Restore exercise thất bại tại KMS decrypt |
| Khai thác đang xảy ra? | Chưa được xác nhận | Không áp dụng theo nghĩa khai thác lỗ hổng |
| Mitigation tạm | Bảo vệ log nguồn, monitoring độc lập và hạn chế quyền change | Duy trì site dự phòng, phương án export/key recovery nếu khả thi |
| Hạn phụ thuộc | Theo security logging requirement | Theo BIA/RTO-RPO và business continuity |
| Owner/đội | Cloud logging + SOC | DB/KMS/Resilience + service owner |

Cả hai có thể là P1 hoặc P2 cao tùy rủi ro đã chứng minh, khả năng thay thế và nghĩa vụ. Một **thang điểm số học đơn** khó phản ánh việc mất khả năng phát hiện và mất khả năng phục hồi.

### 21.3. Phương án điều hành

1. Security/risk owner xác định **critical gates, business exposure và khả năng xảy ra trong cửa sổ này**.
2. **Containment nhanh cho F-LOG** nếu có thể: bật logging hoặc giới hạn thay đổi quyền khi chưa có central audit.
3. **Đảm bảo F-DR không bị trì hoãn vô hạn**: phân công KMS/DB owners, kiểm quyền restore và lên test có thời hạn.
4. Nếu cùng đội chuyên môn, cấp người/cửa sổ theo mức risk và ràng buộc, đồng thời phối hợp đội khác cho phần độc lập.
5. Không gộp findings thành một “infrastructure security ticket” làm mất hai acceptance criteria.
6. Retest F-LOG bằng event source → pipeline → alert; retest F-DR bằng decrypt/restore/data integrity/RTO-RPO trong scope.
7. Nếu một rủi ro chưa xử lý, báo rõ residual risk, owner và giải pháp tạm phù hợp.

### 21.4. Điểm cần chứng minh

**F-LOG:** log được thu và phát hiện mất nguồn; không chỉ “agent healthy”.

**F-DR:** restore thực sự thành công trong failure scenario/BIA đã xác định; không chỉ “backup success”.

**Bài học:** các finding có severity kỹ thuật không tương đồng vẫn phải được ưu tiên trên **cùng hệ thống mục tiêu bảo mật, rủi ro và nghĩa vụ**. Nên báo riêng các critical gates thay vì một điểm backlog tổng.

## 22. Governance: ai quyết định, ai sửa và ai xác minh?

### 22.1. RACI minh họa

R = Responsible (thực hiện); A = Accountable (chịu trách nhiệm cuối với hoạt động); C = Consulted (tham vấn); I = Informed (được thông báo).

| Hoạt động | Security/IR | Service owner | Engineering | Risk owner | Assurance |
|---|---|---|---|---|---|
| Xác minh security finding | **A/R** theo nguồn | C | C | I | C |
| Xác định asset/business impact | C | **A/R** | R | C | C |
| Phê duyệt priority/risk triage | R | C | C | **A** theo governance | C |
| Hành động containment khẩn | **A/R** theo incident plan | C | R | I | I |
| Xây remediation solution | C | **A** cho service impact | **R** | C | C |
| Deploy/rollback | C | A theo change control | **R** | I | C |
| Retest và xác minh hiệu lực | C | I | C | I | **A/R** theo quy định |
| Chấp nhận rủi ro còn lại | C | C | C | **A/R** | C |
| Report trend và overdue | C | C | C | I | **A/R** |

Đây là ví dụ tổ chức vai trò. Thẩm quyền thực sự phải theo policy, không mặc định cùng một người có quyền ưu tiên, phê duyệt ngoại lệ và tự xác minh closure đối với mọi finding.

### 22.2. Cuộc họp triage hiệu quả

Với backlog lớn, thay vì đi từng ticket theo tuổi, agenda có thể là:

1. **Active exploitation/incident signals:** việc cần xử lý tức thời.
2. **Critical gates và nghĩa vụ có hạn:** những việc không thể chờ.
3. **New exposure:** tài sản/dịch vụ mới public, privilege mới, control drift.
4. **Overdue P1/P2:** chặn vì thiếu owner, dependency, release window nào?
5. **Compensating controls:** có bằng chứng hoạt động và expiry không?
6. **Root-cause campaigns:** nhiều findings có thể xử lý bằng một thay đổi chung.
7. **Retest bottlenecks:** đã sửa nhưng chưa xác minh, ai cần hỗ trợ?
8. **Risk decisions:** yêu cầu phê duyệt hoặc tạm dừng dịch vụ.
9. **Monitoring:** threat/asset changes khiến priority cần điều chỉnh.
10. **Outcomes:** decision ID, owner, due date, next review, evidence.

Một cuộc triage không tạo ra **quyết định có người chịu trách nhiệm** sẽ dễ thành buổi đọc dashboard lặp lại.

### 22.3. Khi có bất đồng ưu tiên

Service owner có thể lo outage; security owner lo exploit. Nên yêu cầu:

- Mỗi bên nêu **dữ kiện và tác động**, không chỉ ý kiến.
- Xem evidence về exposure, threat, test và business cost.
- Phân biệt rủi ro trì hoãn với rủi ro triển khai.
- Đề xuất mitigation/canary/degraded mode nếu có.
- Escalate theo policy khi không thống nhất.
- Ghi quyết định, điều kiện kiểm lại và người có thẩm quyền.

**Không giải quyết bất đồng bằng cách tự hạ priority trên ticket**, vì như vậy làm mất tính trung thực của audit trail.

## 23. KPI đo hiệu quả ưu tiên và remediation

### 23.1. KPI phải phản ánh verified risk reduction

| KPI | Định nghĩa có ích | Giới hạn |
|---|---|---|
| **High-risk exposure backlog** | Finding P0/P1 chưa verified closed, phân theo age/criticality | Finding count bị ảnh hưởng bởi coverage của tool |
| **Overdue high-priority findings** | Finding đã tới deadline mà chưa đạt điều kiện đóng hoặc xử lý risk hợp lệ | Deadline có thể bị chỉnh để làm đẹp metric |
| **Time to triage** | Từ nhận finding đến quyết định ưu tiên có bằng chứng | Không chứng minh remediation đã xảy ra |
| **Time to mitigate** | Từ mốc start đã định đến mitigation verified | Mitigation có thể chưa loại root cause |
| **Time to fix** | Đến lúc correction được triển khai đúng scope | Không tự chứng minh đã retest |
| **Time to verified closure** | Từ confirmed đến lúc test PASS và approval | Phải xử lý các finding còn mở đúng cách |
| **Retest pass rate** | Retest PASS / retests có kết quả hợp lệ | Không phản ánh những finding chưa được đưa đi test |
| **Remediation coverage** | Required affected units đã verified PASS / toàn population bị ảnh hưởng | Phải giữ những asset chưa test trong mẫu số |
| **Recurring findings** | Finding đã closed nhưng xuất hiện lại cùng root cause/scope | Cần taxonomy nhất quán |
| **Temporary mitigation expiry** | Mitigations/exception tới hạn chưa review | Một số mitigation hết hiệu lực khi network đổi |
| **Evidence gap aging** | Tuổi finding chưa đủ evidence và owner | Không gộp unknown vào low |
| **Risk acceptance overdue** | Ngoại lệ quá hạn hoặc chưa có approver hợp lệ | Acceptance không có nghĩa compliance PASS |
| **Critical asset protection** | Critical units đạt mandatory control assertion / required critical units | Không dùng tổng tỷ lệ che một critical FAIL |

### 23.2. Công thức verified remediation coverage

\[
\text{Verified Remediation Coverage}
=
\frac{N_{\text{affected units verified fixed}}}
{N_{\text{affected units requiring remediation}}}
\times 100\%
\]

Giả sử một vulnerable base image nằm trong 20 deployment:

- 12 deployment có image fix và retest PASS.
- 3 deployment đã roll out nhưng chưa retest.
- 4 deployment chưa cập nhật.
- 1 deployment đang mất telemetry.

**Verified coverage = 12/20 = 60%.**

Không báo 15/20 = 75% đã sửa nếu ba deployment chỉ mới triển khai mà chưa chứng minh condition. Cũng không loại asset mất telemetry khỏi mẫu số mà không có quyết định scope hợp lệ.

### 23.3. SLA theo cohort và thời kỳ

Ví dụ tổ chức có 30 findings P1 **đến hạn trong tháng**:

- 19 được verified closed đúng deadline.
- 4 triển khai fix đúng hạn nhưng retest sau hạn.
- 5 overdue chưa sửa xong.
- 2 có risk exception hợp lệ được duyệt nhưng criterion/SLAs không cho tính như verified closure.

Nếu SLA đo **verified closure**:

\[
\text{On-time Verified Closure Rate}=\frac{19}{30}\times 100\%\approx63.3\%
\]

Có thể báo thêm **risk decisions within policy**, nhưng không cộng hai accepted-risk vào numerator trừ khi định nghĩa cụ thể cho một KPI **khác** và điều khoản cho phép. Việc thay đổi deadline phải có lịch sử để đánh giá thời gian thực.

### 23.4. KPI “số finding đóng” có thể bị thao túng

Hệ thống đo tốt cần phát hiện:

- Severity/priority bị hạ không có evidence hoặc approver.
- Deadline bị gia hạn nhiều lần.
- Finding bị xóa, merge hoặc mất khỏi scanner.
- Asset bị retired trong tool nhưng còn chạy production.
- Ticket chuyển sang Done khi chưa có retest.
- Risk acceptance hết hạn vẫn được tính là xử lý.
- High-priority finding bị chia nhỏ thành nhiều low-priority ticket để làm giảm backlog.
- Số lượng phát hiện giảm vì mất asset/sensor coverage.

Nên theo dõi **coverage của hệ thống phát hiện, thời gian phơi nhiễm rủi ro và verified closure** cùng nhau.

### 23.5. Tập dữ liệu chưa đóng và độ lệch thống kê

Nếu một finding vẫn mở ở cuối kỳ, không được tính “thời gian đến khi đóng = 0” hoặc loại khỏi mọi báo cáo mà không nhắc. Nó là **open/censored item** đối với phân tích thời gian đóng. Có thể báo tuổi hiện tại, số overdue và phân phối theo severity; khi phân tích thời gian xử lý cần xử lý cohort và censoring phù hợp.

Một vài P0/P1 hiếm có thể chi phối mean. Nên xem **median, tail, count và các case nguy hiểm nhất** thay vì chỉ trung bình chung.

## 24. Sai lầm phổ biến khi ưu tiên sửa lỗi

| Sai lầm | Vì sao gây rủi ro | Cách làm phù hợp |
|---|---|---|
| “CVSS cao nhất phải sửa trước mọi trường hợp.” | Bỏ qua production exposure và blast radius | CVSS là input; dùng risk context, threat và control gates |
| “Không có CVSS nghĩa là priority thấp.” | IAM, logging, DR, privacy gap có thể rất nghiêm trọng | Xếp theo control objective và impact |
| “EPSS thấp nghĩa không cần sửa.” | Là ước lượng, có thể đổi và không biết asset impact | Kết hợp với exposure, criticality và obligations |
| “KEV không ghi tên thì không bị khai thác.” | Danh mục không thể bao phủ mọi activity | Không suy ra sự an toàn từ sự vắng mặt |
| “Một WAF rule đủ để giảm priority.” | Có thể thiếu scope hoặc bị bypass | Chứng minh control effectiveness, xem expiry |
| “Unknown exposure = internal = low.” | Thiếu evidence không chứng minh không reachable | Validation có hạn và containment theo rủi ro |
| “Fix khó thì chuyển P1 thành P3.” | Effort không làm giảm security impact | Giữ priority, lên mitigation và escalation |
| “Báo cáo scanner chỉ có findings đang thấy.” | Asset không onboard bị bỏ khỏi mẫu số | Đối soát inventory độc lập |
| “Đã đổi version trên repo nghĩa production đã vá.” | Image/runtime cũ có thể vẫn chạy | Kiểm actual deployed version/path |
| “Đã rotate secret nghĩa mọi token cũ vô hiệu.” | Sessions hoặc alternate credentials có thể còn hiệu lực | Revoke/deny test toàn scope |
| “Ticket Done tức finding closed.” | Không có retest assertion | Theo dõi implemented và verified riêng |
| “Sửa một affected asset là sửa toàn bộ.” | Root fix chưa rollout đủ deployments | Giữ population và status từng unit |
| “Đã chấp nhận risk nên control PASS.” | Risk decision khác control effectiveness | Giữ condition, scope, approver và expiry |
| “Sau incident mới cần nâng priority.” | Có thể phòng ngừa trước exploitation | Dùng credible threats và critical gates |
| “Chỉ ưu tiên rủi ro dễ khai thác qua Internet.” | Internal privilege, lateral movement và backup compromise có thể quan trọng | Threat modeling và attack path |
| “Bằng chứng nhiều là chắc.” | Evidence có thể stale hoặc sai scope | Kiểm provenance, completeness, validity |
| “Tỷ lệ backlog giảm là giảm rủi ro.” | Có thể do xóa asset hoặc đổi scanner | Đo verified risk reduction và coverage |
| “Risk score cho ra thứ tự đúng tuyệt đối.” | Trọng số/chấm điểm ước lượng có sai số | Guardrails và review có thẩm quyền |
| “Có thể tự gia hạn ngoại lệ khi quá hạn.” | Mất quản trị residual risk | Reassessment và approval theo policy |
| “Hết deadline nghĩa tự đóng ticket.” | Không chứng minh control sửa | Escalate và báo overdue minh bạch |

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Một thư viện có CVSS rất cao trong repository nhưng không có trong các deployment thuộc scope đã kiểm. Có phải P0 không?

**Gợi ý:** Không thể kết luận P0 chỉ từ CVSS. Cần xác minh artifact/deployment/reachability và nghĩa vụ; nếu không thuộc runtime scope, priority có thể thấp hơn hoặc N/A có evidence, nhưng vẫn cần quản lý rủi ro đưa dependency vào production sau này.

**Câu 2.** Một lỗi authorization Medium theo scanner cho phép tài khoản hỗ trợ đọc dữ liệu khách hàng ngoài scope. Nên ưu tiên ra sao?

**Gợi ý:** Đánh risk theo dữ liệu, xác nhận đường truy cập, quyền attacker, blast radius và control bù trừ. Có thể là P1 và cần containment dù severity gốc Medium.

**Câu 3.** Một CVE nằm trong KEV. Điều đó có chứng minh server của tổ chức đã bị khai thác không?

**Gợi ý:** Không. KEV là bằng chứng về khai thác trong thực tế đối với CVE theo tiêu chí danh mục, không phải forensic evidence về server cụ thể. Cần xác định affected product/version, exposure và điều tra incident nếu có tín hiệu.

**Câu 4.** EPSS cao nhưng application đang chạy trên một môi trường test không kết nối production. Có thể dùng EPSS để kết luận priority P1 không?

**Gợi ý:** EPSS hỗ trợ ước lượng likelihood chung, không biết impact và exposure nội bộ. Cần xem cách triển khai, dữ liệu, quyền, nghĩa vụ và khả năng đổi scope.

**Câu 5.** Vì sao hiệu lực WAF phải được thử trước khi dùng làm căn cứ giảm priority?

**Gợi ý:** WAF có thể không bao phủ đường nội bộ hoặc attack variants; cần negative/positive test, kiểm bypass, monitoring và scope.

**Câu 6.** Patch đã merge vào main branch nhưng Kubernetes vẫn chạy image digest cũ. Finding đã khắc phục chưa?

**Gợi ý:** Chưa đối với runtime đang chạy. Cần deploy image fix và xác minh mọi deployment thuộc scope đã thay, retest condition và regression.

**Câu 7.** Có 20 affected deployments, 12 verified fixed, 3 deployed chưa retest, 4 chưa sửa và 1 mất telemetry. Verified coverage là bao nhiêu?

**Gợi ý:** 12/20 = 60%; ba đã deploy chưa được tính PASS và một unknown vẫn nằm trong mẫu số.

**Câu 8.** Một finding critical chưa có patch. Nhóm kỹ thuật có thể tự chuyển thành low priority vì khó sửa không?

**Gợi ý:** Không. Cần mitigation, giới hạn exposure, vendor escalation, risk owner và plan; khó sửa là dependency/effort, không phải bằng chứng rủi ro giảm.

**Câu 9.** Một token sản xuất bị lộ và có bằng chứng vẫn còn hiệu lực. Nên đợi risk scoring đầy đủ hay containment trước?

**Gợi ý:** Triển khai incident/security triage khẩn và containment theo playbook, bảo toàn evidence, kiểm revoke/rotate và đánh giá residual access; không chờ chấm điểm.

**Câu 10.** Một cloud account mới thiếu audit logging nhưng không có CVE. Có thể coi không cần sửa vì không phải software bug không?

**Gợi ý:** Không. Đây là control gap có thể làm mất detection và forensic evidence. Ưu tiên theo criticality, exposure, requirement và khả năng kiểm tra.

**Câu 11.** Một P1 đã có compensating control được kiểm chứng, risk owner chấp thuận tạm. Có thể đóng finding PASSED không?

**Gợi ý:** Chỉ khi acceptance criteria thực sự được chứng minh; mitigation/risk acceptance không mặc định loại root cause. Giữ trạng thái phù hợp, scope, expiry và review trigger.

**Câu 12.** Vì sao không nên tính remediation SLA từ lúc chuyển ticket sang đội hiện tại?

**Gợi ý:** Thời gian rủi ro đã tồn tại không biến mất khi chuyển chủ sở hữu. SLA phải theo mốc đã định và giữ lịch sử, trừ khi chính sách hợp lệ quy định khác với lý do rõ.

**Câu 13.** Scanner mới phát hiện nhiều lỗ hổng hơn tháng trước. Điều đó có chứng minh security posture xấu đi không?

**Gợi ý:** Chưa. Có thể do tăng coverage hoặc quy tắc phát hiện đổi. Cần so sánh population, version, exposure và verified remediation.

**Câu 14.** Một finding được retest PASS hôm nay nhưng provisioning template có thể tạo ra lỗi tương tự ngày mai. Nên làm gì?

**Gợi ý:** Ghi tình trạng correction, xử lý RCA, bổ sung preventive control, regression và owner; theo tiêu chí closure đã duyệt, không bỏ preventive action chưa hoàn thành.

## 26. Bài thực hành: lập danh sách ưu tiên từ backlog hỗn hợp

Giả sử bạn là security assurance engineer cho nền tảng có dịch vụ thanh toán, quản lý đơn hàng, logging tập trung, backup/DR và các hệ thống phát triển. Tổ chức có các findings sau, **hoàn toàn giả định**:

| ID | Finding | Thông tin ban đầu | Dữ liệu chưa có |
|---|---|---|---|
| **F01** | Token quản trị production bị lộ | Token còn hiệu lực, quyền thay cấu hình critical | Đã được dùng trái phép hay chưa |
| **F02** | API authorization gap | Controlled test xác nhận role hỗ trợ đọc dữ liệu tenant khác | Các API tương tự có bị ảnh hưởng? |
| **F03** | CVE trong public gateway | Sản phẩm/phiên bản matching known exploited advisory, endpoint public | Mitigation hiện hành có chặn được path không |
| **F04** | Package CVSS cao trong repo demo | Chưa thấy trong production inventory | Artifact demo có chạy ở hệ thống khác không |
| **F05** | Cloud account mới thiếu audit log | Event IAM ở nguồn không tới SIEM | Lịch sử thiếu log dài bao lâu |
| **F06** | DR restore KMS failure | BIA critical, restore test thất bại | Có recovery point thay thế giải mã được không |
| **F07** | Quarterly access review quá hạn | Một nhóm test có data không nhạy cảm | Có nghĩa vụ áp dụng riêng không |
| **F08** | Base image vulnerable | 12 workloads production cùng base image | Có dependency path usable và patch compatibility không |
| **F09** | Vendor support quyền quá rộng | Tài khoản vendor có quyền đọc nhiều resource | Quyền còn hiệu lực và có monitoring bù trừ không |
| **F10** | Detection suppression quá rộng | Rule quan trọng bị suppress, chưa có test âm | Có threat scenario nào đang bị che không |

### 26.1. Bài cần hoàn thành

1. Gắn **owner và business service** cho từng finding, ghi nguồn và confidence.
2. Phân biệt **confirmed**, **needs validation**, **potential incident** và **not applicable nếu có căn cứ**.
3. Xác định trigger khẩn cần xử lý **trước scoring**, nêu lý do.
4. Đề xuất priority P0/P1/P2/P3 **theo chính sách giả định** và ghi những điểm phải xác minh trước khi kết luận.
5. Với mỗi finding, viết **một immediate mitigation** có thể thử hoặc lý do không có.
6. Đề xuất một fix gốc và một cách kiểm tra **scope toàn population**.
7. Thiết kế dependency sequence để xử lý F03 và F08 mà không tạo downtime không kiểm soát.
8. Thiết kế retest cho F02, F05, F06 và F10 bằng test dương/âm hoặc end-to-end.
9. Đề xuất risk acceptance record cho một tình huống chưa có patch, nhưng không tự coi là được phê duyệt.
10. Tính verified remediation coverage khi 5/10 findings có fix được triển khai nhưng chỉ 3/10 có retest PASS, giả sử mỗi finding là một unit bằng nhau.
11. Viết một bản thông báo ngắn cho risk owner: top risks, residual exposures, người xử lý và quyết định cần phê duyệt.
12. Đưa ra trigger tái đánh giá nếu một hệ thống sandbox chuyển sang production hoặc có exploitation evidence mới.

### 26.2. Một cách phân nhóm hợp lý để thảo luận

| Nhóm | Finding | Gợi ý logic ưu tiên |
|---|---|---|
| **Khẩn theo evidence/impact** | F01 | Token active với quyền critical cần containment/IR triage; có thể là P0/P1 tùy tín hiệu |
| **Có khả năng P1 sau triage** | F02, F03 | Confirmed authz gap hoặc known exploited + reachable gateway cần action nhanh |
| **Rủi ro cao tùy business/threat scenario** | F05, F06, F09, F10 | Control gap ở logging/DR/vendor/detection, cần xác minh hiệu lực và impact |
| **Campaign remediation** | F08 | Nhiều workloads cùng root image; ưu tiên theo exposure/impact và fix chung |
| **Validation trước kết luận** | F04 | Có CVSS cao nhưng chưa biết deployment |
| **Theo nghĩa vụ và risk tier** | F07 | Access review quá hạn vẫn cần xử lý, priority tùy scope/requirement |

Đây **không phải bảng xếp hạng duy nhất đúng**: khi có evidence mới, một finding F05/F06/F09/F10 có thể chuyển ngay sang P1 hoặc khẩn hơn. Tính chính xác nằm ở **lý do, bằng chứng, giới hạn, owner và phản ứng**, không nằm ở việc cố áp một thứ tự cứng cho mọi giả định thiếu dữ liệu.

### 26.3. Kết quả tính KPI bài tập

Nếu chỉ **3/10 finding units** đã có retest PASS:

\[
\text{Verified Remediation Coverage} = \frac{3}{10}\times100\%=30\%
\]

**5/10** đã triển khai fix là **implementation progress = 50%**, không phải verified remediation. Mỗi finding có thể khác trọng số rủi ro và số affected assets; thực tế nên bổ sung bảng theo risk tier và asset units, không xem 30% như mức giảm rủi ro chung tuyệt đối.

### 26.4. Tiêu chí chấm bài

| Tiêu chí | Đạt khi |
|---|---|
| **Context** | Có service, asset, environment, data, owner, exposure |
| **Threat** | Dùng khai thác và intelligence đúng phạm vi, không tự suy diễn incident |
| **Decision** | Priority, critical override, reason và approver rõ |
| **Unknown** | Dữ liệu chưa có được ghi và có hạn điều tra |
| **Action** | Có mitigation, root fix, dependency và rollout plan |
| **Verification** | Retest đúng assertion và đầy đủ population |
| **Governance** | Risk acceptance/exception có thẩm quyền, scope và expiry |
| **Measurement** | Không tính implemented/accepted vào verified PASS |
| **Continuous** | Có regression, monitoring và trigger reassessment |
| **Integrity** | Evidence và quyết định ưu tiên truy vết được, không sửa lịch sử |

## 27. Checklist triển khai ưu tiên sửa lỗi

- [ ] Định nghĩa chính xác đối tượng remediation: vulnerability, misconfig, control gap, incident finding, vendor và resilience.
- [ ] Thu findings từ nhiều nguồn, không coi scanner backlog là toàn bộ population.
- [ ] Đối soát asset/service inventory độc lập, nhận diện missing/unknown assets.
- [ ] Chuẩn hóa asset identity, finding fingerprint, duplicate và affected deployments.
- [ ] Xác minh version, configuration, environment và exploitable path trước khi quyết định.
- [ ] Phân biệt severity kỹ thuật, exploitation likelihood, business impact và priority.
- [ ] Có nguồn threat intelligence, thời điểm, confidence và hướng dẫn dùng KEV/EPSS/SSVC phù hợp.
- [ ] Không lấy thiếu thông tin về exposure làm bằng chứng rủi ro thấp.
- [ ] Có critical gates cho incident, credential leak, boundary failure và nghĩa vụ trọng yếu.
- [ ] Có risk rating policy, priority levels, decision owner và review cadence.
- [ ] Các priority khẩn được escalated và phối hợp containment theo IR plan.
- [ ] Priority gắn security objective, affected service, data class và blast radius.
- [ ] Kiểm tra hiệu lực controls bù trừ trước khi dùng để hạ residual risk.
- [ ] Không dùng effort hoặc lịch sprint làm lý do tự hạ priority.
- [ ] SLA/deadline có mốc bắt đầu, mốc kết thúc, timezone và lịch sử chỉnh sửa.
- [ ] Những deadline bắt buộc theo luật/hợp đồng được review bởi bên có thẩm quyền.
- [ ] Remediation plan có owner, patch/mitigation, dependency, cost, rollback và acceptance criteria.
- [ ] Phân biệt immediate containment, correction, corrective action và preventive action.
- [ ] Fix ảnh hưởng nhiều assets được triển khai và tracked trên từng affected unit.
- [ ] Release/production change có functional và security regression phù hợp.
- [ ] Kiểm patch/upgrade trên **effective runtime** không chỉ repository hoặc build artifact.
- [ ] Retest có scope, timestamp, phương pháp, positive/negative cases và evidence IDs.
- [ ] Fix implemented, retest PASS, risk accepted và verified closed là các trạng thái khác nhau.
- [ ] Risk acceptance có approver, rationale, compensating control, expiry và review triggers.
- [ ] Không chỉnh sửa lặng lẽ priority, due date, severity, trạng thái hoặc evidence lịch sử.
- [ ] KPI có mẫu số required affected units, age, overdue và verified closure.
- [ ] Có kiểm tra scanner/source coverage và finding disappearance bất thường.
- [ ] Cùng root cause được xử lý ở provisioning/IaC/CI/CD/runtime monitoring khi thích hợp.
- [ ] Finding tái xuất hiện được reopened hoặc liên kết với root-cause record trước đó.
- [ ] Sau incident, vendor advisory, architecture/data change và exception expiry phải tái triage.
- [ ] Báo cáo lãnh đạo nêu top risks, unknowns, mitigation, owner và decisions required.

## Kết luận

**Ưu tiên sửa lỗi trong security assurance là đưa nguồn lực vào các sai lệch làm tăng rủi ro đáng kể nhất, theo cách có căn cứ và kiểm chứng được.** Chỉ số kỹ thuật như CVSS có giá trị nhưng không thay thế threat relevance, asset criticality, exploitable path, business impact, nghĩa vụ áp dụng và hiệu lực của controls hiện hữu. Những trường hợp khẩn cấp cần containment và escalation theo chính sách; những trường hợp chưa đủ evidence cần điều tra có hạn, không tự xếp thấp.

Trong **SECURITY_SECURITY_ASSURANCE**, quyết định ưu tiên phải tạo được chuỗi truy vết **finding → evidence → risk context → priority → owner/deadline → mitigation và remediation → retest → verified closure → preventive control**. Khi tổ chức giữ riêng severity, priority, trạng thái sửa, kết quả kiểm chứng và residual risk, remediation trở thành một chương trình giảm rủi ro liên tục thay vì cuộc đua đóng ticket và làm đẹp dashboard.


