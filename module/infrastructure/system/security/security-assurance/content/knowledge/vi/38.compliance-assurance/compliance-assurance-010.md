# Duy trì compliance: vận hành tuân thủ liên tục bằng security controls và bằng chứng

**Duy trì compliance** là quá trình giữ cho tổ chức, hệ thống, dịch vụ và hoạt động xử lý dữ liệu **đáp ứng các nghĩa vụ áp dụng trong suốt vòng đời vận hành**, chứ không chỉ đạt một trạng thái đủ tài liệu vào ngày kiểm toán. Công việc này bao gồm nhận biết thay đổi yêu cầu, xác định phạm vi, thực thi controls, kiểm chứng hiệu lực, giữ bằng chứng, phát hiện sai lệch, xử lý finding và đánh giá lại khi kiến trúc, quy trình hoặc pháp lý thay đổi.

Trong chương **Compliance assurance** của module **SECURITY_SECURITY_ASSURANCE**, bài học xem việc duy trì tuân thủ như một **vấn đề kỹ thuật, quản trị rủi ro và bằng chứng**. Mục tiêu của module là xây dựng cách đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật, từ phân tích rủi ro, yêu cầu và security controls đến kiểm thử, audit, khắc phục phát hiện, và tổ chức security assurance liên tục trong phát triển và vận hành.

Điểm xuất phát quan trọng: **compliance không đồng nghĩa an toàn tuyệt đối**, và việc có chứng nhận hoặc hoàn thành một đợt audit không tự bảo đảm hệ thống tiếp tục đáp ứng yêu cầu sau khi triển khai thay đổi. Đồng thời, một dashboard xanh không thay thế được kết luận về tuân thủ các nghĩa vụ pháp lý hoặc hợp đồng: kết luận như vậy còn phụ thuộc định nghĩa yêu cầu, đối tượng, kỳ đánh giá, phương pháp, thẩm quyền và giới hạn bằng chứng.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt compliance, security assurance, control effectiveness, risk management và audit readiness.
2. Xây dựng **obligation register** cho yêu cầu pháp lý, hợp đồng, nội bộ và framework liên quan; đánh giá điều kiện áp dụng, phạm vi, phiên bản và chủ sở hữu.
3. Chuyển nghĩa vụ thành **control objective**, assertion, phép kiểm, chỉ số giám sát và bằng chứng có thể truy vết.
4. Thiết kế mô hình phối hợp giữa business owner, legal/compliance, control owner, engineering, security assurance và independent audit.
5. Giám sát thay đổi hạ tầng, danh tính, dữ liệu, nhà cung cấp và quy định để phát hiện **compliance drift**.
6. Phân biệt kiểm tra cấu hình tại một thời điểm với bằng chứng **operating effectiveness** trong một kỳ.
7. Thu thập và bảo vệ evidence liên tục mà không làm lộ dữ liệu cá nhân, secrets hoặc thông tin nhạy cảm.
8. Quản lý ngoại lệ, finding, corrective action, risk acceptance và retest trước khi kết luận một control đạt.
9. Tính và diễn giải đúng KPI coverage, evidence freshness, overdue findings và verified compliance controls.
10. Xây dựng lộ trình và checklist duy trì compliance phù hợp với hệ thống phát triển, vận hành liên tục.

## 2. Compliance cần được hiểu trong đúng phạm vi

### 2.1. Compliance khác security assurance thế nào?

| Khái niệm | Câu hỏi cốt lõi | Ví dụ |
|---|---|---|
| **Compliance** | Các nghĩa vụ áp dụng đã được đáp ứng trong scope và kỳ đánh giá chưa? | Dịch vụ có lưu audit log theo chính sách áp dụng không? |
| **Security control** | Cơ chế, quy trình hoặc hành động nào làm giảm rủi ro hoặc đáp ứng yêu cầu? | Bật audit log, bảo vệ quyền xóa, giám sát gián đoạn |
| **Control design** | Kiểm soát được thiết kế có khả năng đạt objective không? | Policy yêu cầu mọi môi trường production gửi security log |
| **Control implementation** | Cơ chế đã được triển khai đúng đối tượng chưa? | Mọi account production có logging destination |
| **Operating effectiveness** | Kiểm soát có thực sự vận hành đúng trong kỳ và tình huống đã xác định? | Kiểm tra mẫu event, cảnh báo khi sink mất và lịch sử thay đổi |
| **Security assurance** | Có bằng chứng tin cậy để đánh giá mức độ đạt mục tiêu bảo mật không? | Đối soát inventory, chạy test, lưu kết quả và giới hạn |
| **Audit** | Một hoạt động đánh giá theo criteria, scope và phương pháp đã xác định | Kiểm tra evidence của một kỳ vận hành |
| **Risk acceptance** | Ai có thẩm quyền quyết định xử lý hoặc chấp nhận rủi ro còn lại? | Phê duyệt ngoại lệ có hạn trong khi sửa hệ thống cũ |

Một control có thể được vận hành tốt nhưng không đủ để đáp ứng toàn bộ nghĩa vụ. Ngược lại, một yêu cầu có thể được chứng minh qua **nhiều controls kết hợp**. Không được giả định rằng một câu trả lời “YES” hay một bằng chứng cấu hình đơn lẻ có nghĩa toàn bộ compliance objective đã đạt.

### 2.2. “Đạt kiểm toán” và “duy trì tuân thủ” khác nhau

**Tuân thủ tại một thời điểm** thường trả lời: trạng thái được ghi nhận ngày X có đáp ứng criteria áp dụng không?

**Duy trì tuân thủ trong kỳ** còn phải trả lời:

- Các controls có được thực hiện đầy đủ trong khoảng thời gian yêu cầu không?
- Có tài sản, môi trường hoặc loại dữ liệu mới nằm ngoài inventory và kiểm tra không?
- Có thay đổi policy, hệ thống hoặc nghĩa vụ khiến kết luận cũ không còn chính xác không?
- Những ngoại lệ có hết hạn và có được tái phê duyệt đúng thẩm quyền không?
- Khi control fail, sai lệch được nhận biết, xử lý và kiểm chứng lại ra sao?
- Bằng chứng có đủ lịch sử để người kiểm tra khác tái dựng kết luận hay không?

Ví dụ, kiểm tra hôm nay cho thấy mọi tài khoản quản trị đều bật MFA nhưng trong ba tháng trước đã có tài khoản ngoại lệ chưa phê duyệt. Một ảnh cấu hình hiện tại **không đủ** để kết luận control đạt trong toàn bộ quý.

### 2.3. Ba câu hỏi phải báo cáo tách biệt

1. **Requirement applicability:** một nghĩa vụ có áp dụng cho pháp nhân, dịch vụ, dữ liệu, hoạt động và kỳ này không?
2. **Control conformance:** các control đáp ứng yêu cầu trong phạm vi và thời gian đã kiểm hay không?
3. **Risk posture:** còn rủi ro gì sau các controls, ngoại lệ và những phần chưa được kiểm chứng?

Đôi khi tổ chức chấp nhận một rủi ro kỹ thuật nhưng điều đó **không tự miễn trừ nghĩa vụ pháp lý hay hợp đồng**. Mức độ có thể áp dụng ngoại lệ phải được đánh giá bởi bộ phận có thẩm quyền và bên có quyền phê duyệt.

## 3. Mô hình vận hành tuân thủ liên tục

### 3.1. Chuỗi truy vết từ nghĩa vụ tới bằng chứng

~~~mermaid
flowchart LR
    O["Obligation / policy / contract"] --> S["Applicability + scope"]
    S --> R["Control objective + assertion"]
    R --> I["Implementation + owner"]
    I --> V["Test / monitor / evidence"]
    V --> D{"Đáp ứng?"}
    D -- "Đạt trong phạm vi" --> REP["Assurance record / audit readiness"]
    D -- "Không đạt hoặc chưa rõ" --> F["Finding / evidence gap"]
    F --> CAPA["Owner + remediation + risk decision"]
    CAPA --> RET["Retest / review"]
    RET --> D
    REP --> CHANGE["Change / periodic review"]
    CHANGE --> S
~~~

Mô hình này cho thấy **evidence là kết quả vận hành kiểm soát**, không chỉ là tập tin được thu thập khi auditor yêu cầu.

### 3.2. Sáu lớp cần duy trì đồng thời

| Lớp | Nhiệm vụ | Ví dụ đầu ra |
|---|---|---|
| **1. Obligations** | Biết nghĩa vụ nào áp dụng, từ nguồn và thời điểm nào | Obligation register, legal assessment, contract references |
| **2. Scope** | Biết tài sản, dữ liệu, người dùng, môi trường và nhà cung cấp liên quan | Service catalog, asset inventory, data-flow map |
| **3. Controls** | Mô tả hành vi/trạng thái phải đúng và chủ sở hữu | Control register, baseline, policy-as-code |
| **4. Operations** | Bảo đảm controls được thực thi và vận hành đúng kỳ | Configs, access reviews, log retention, backups |
| **5. Assurance** | Kiểm tra hiệu lực, mức bao phủ và giữ bằng chứng | Tests, evidence manifest, assessment verdict |
| **6. Improvement** | Xử lý drift, finding, ngoại lệ và đưa bài học vào quy trình | Remediation tickets, retest, RCA, trend |

Thiếu một lớp có thể làm kết luận sai. Ví dụ, pipeline kiểm soát hạ tầng tốt nhưng tổ chức không biết một dịch vụ SaaS mới được dùng để xử lý dữ liệu nhạy cảm thì việc đo coverage sẽ bỏ sót dịch vụ đó từ mẫu số.

### 3.3. Rủi ro của mô hình “compliance theo mùa”

Dấu hiệu thường gặp:

- Chỉ thu bằng chứng một hoặc hai tuần trước audit.
- Screenshot trạng thái cuối kỳ không có lịch sử điều chỉnh.
- Control owner nhớ thao tác trong đầu nhưng thiếu tài liệu và owner dự phòng.
- Evidence lưu nhiều nơi, quyền quá rộng hoặc không biết bản nào là cuối.
- Finding được đóng sau khi sửa ticket, chưa thử lại hiệu lực.
- Framework mapping được cập nhật nhưng không có review applicability.
- Dashboard chỉ đo controls đã onboard, bỏ sót tài sản mới.

Hậu quả là **không có khả năng phát hiện sai lệch giữa các kỳ**; audit readiness thấp dù số lượng file trong thư mục evidence rất lớn.

## 4. Xây dựng obligation register và applicability assessment

### 4.1. Phân loại nguồn yêu cầu

Nghĩa vụ có thể đến từ:

- **Luật và quy định:** tùy pháp nhân, vị trí, lĩnh vực, loại hoạt động và dữ liệu.
- **Hợp đồng/thoả thuận:** điều khoản khách hàng, bảo vệ dữ liệu, security addendum và nghĩa vụ với đối tác.
- **Chuẩn và chương trình đánh giá:** ví dụ ISO/IEC 27001, SOC 2 criteria, PCI DSS, hoặc các chương trình đặc thù khác khi tổ chức thực sự thuộc phạm vi/đã cam kết.
- **Chính sách nội bộ:** security baseline, data classification, IAM, incident response, retention.
- **Quyết định risk management:** risk treatment plan, approved control commitments, corrective actions từ audit trước.
- **Yêu cầu kiến trúc/nghiệp vụ:** RTO/RPO được phê duyệt, data locality hoặc yêu cầu customer-specific.

**Không mặc định mọi framework áp dụng cho mọi tổ chức.** Ví dụ, NIST CSF là một khung tổ chức quản trị rủi ro có thể dùng hỗ trợ mapping; không tự động trở thành nghĩa vụ pháp lý. Trạng thái chứng nhận ISO/IEC 27001 liên quan đến scope của ISMS được chứng nhận, không phải tuyên bố mọi ứng dụng không có lỗ hổng.

### 4.2. Metadata của một obligation

| Trường | Ý nghĩa |
|---|---|
| obligation_id | ID ổn định dùng xuyên các kỳ |
| source_type, source_reference | Luật, hợp đồng, standard, policy và điều khoản cụ thể |
| source_version, effective_from | Phiên bản và mốc hiệu lực được xác minh |
| applicability_basis | Vì sao áp dụng: pháp nhân, dịch vụ, dữ liệu, địa lý, loại hoạt động |
| accountable_owner | Người/đội chịu trách nhiệm xác định và diễn giải nghĩa vụ |
| system_scope | Dịch vụ, môi trường, tài khoản, nhà cung cấp, dữ liệu liên quan |
| requirement_text/summary | Diễn giải nội bộ có kiểm soát, giữ tham chiếu nguồn |
| obligations_to_controls | Các control ID dùng đáp ứng yêu cầu |
| evidence_expectations | Loại và kỳ evidence cần cho việc chứng minh |
| review_frequency/trigger | Chu kỳ rà soát và sự kiện kích hoạt |
| status/exception | Applicable, not applicable, pending assessment, superseded... |
| last_reviewed_at, next_review | Dấu vết review định kỳ |
| approver | Chủ thể có thẩm quyền xác nhận applicability nếu cần |

Nên giữ **tham chiếu điều khoản nguồn** và đánh dấu rõ phần diễn giải nội bộ. Một câu viết ngắn gọn trong control register không nên được hiểu là toàn văn yêu cầu pháp lý.

### 4.3. Ví dụ obligation được mô hình hóa

~~~yaml
obligation_id: "OBL-SEC-LOG-001"
source:
  type: "internal-security-policy"
  reference: "SEC-POL-LOG-v4"
  section: "production-security-events"
  effective_from: "2026-10-01"
applicability:
  decision: "APPLICABLE"
  basis: "All customer-data production services"
  entity: "example-organization"
  scope:
    environments: ["production"]
    data_classes: ["customer-data"]
  approved_by_role: "security-governance"
summary: >
  Security-relevant administrative changes must be logged,
  centrally collected and protected from unauthorized modification.
mapped_controls:
  - "CTRL-LOG-01"
  - "CTRL-LOG-02"
  - "CTRL-LOG-03"
evidence_expectations:
  - "Data source inventory"
  - "Configuration and effective permissions"
  - "End-to-end event and tamper-detection test"
last_reviewed_at: "2026-11-28T07:00:00Z"
review_triggers:
  - "new-production-service"
  - "new-cloud-account"
  - "logging-policy-change"
~~~

Đây là **dữ liệu mẫu**, không phải nghĩa vụ áp dụng phổ quát. Thông tin nguồn, phạm vi và phê duyệt trong hệ thống thật phải có căn cứ từ tổ chức.

### 4.4. Applicability không phải một checkbox

Một obligation có thể chỉ áp dụng nếu:

- Dữ liệu là dữ liệu cá nhân hoặc thuộc loại được bảo vệ cụ thể.
- Dịch vụ được cung cấp tại một phạm vi địa lý hoặc bởi một pháp nhân nhất định.
- Tổ chức có vai trò controller/processor hay vai trò hợp đồng khác trong luồng dữ liệu.
- Hệ thống xử lý một loại giao dịch, chức năng hoặc khách hàng thuộc yêu cầu riêng.
- Một tiêu chuẩn hoặc điều khoản đã được đưa vào hợp đồng hoặc phạm vi chứng nhận.

Quyết định **NOT_APPLICABLE** cần lý do, scope và approver phù hợp. Nếu asset, data flow hoặc khách hàng thay đổi, quyết định đó phải được **đánh giá lại**, không giữ mặc định vô thời hạn.

### 4.5. Quản lý yêu cầu thay đổi

Mỗi lần phát hiện yêu cầu hoặc cách diễn giải thay đổi, cần:

1. Xác định nguồn đáng tin và phiên bản mới, ngày công bố và ngày hiệu lực.
2. Phân tích tác động với pháp nhân, hợp đồng, dữ liệu và system scope.
3. So sánh nghĩa vụ mới/cũ; xác nhận có thay đổi về controls hay evidence không.
4. Đánh giá **khoảng thời gian chuyển tiếp**, quyền quyết định, chi phí và hành động cần làm.
5. Cập nhật control mapping, implementation plan và owner.
6. Kiểm chứng thay đổi đã triển khai, lập finding nếu có yêu cầu đang áp dụng chưa đạt.
7. Giữ lịch sử applicability và kết luận của các kỳ trước.

Không tự coi ngày công bố là ngày bắt đầu nghĩa vụ nếu nguồn có thời điểm hiệu lực riêng. Đối với nghĩa vụ pháp lý và hợp đồng, cần có review của người có thẩm quyền thay vì suy đoán.

## 5. Control register: từ nghĩa vụ thành hành vi kiểm soát

### 5.1. Một obligation có thể cần nhiều controls

Ví dụ yêu cầu bảo vệ security audit log của production có thể đòi hỏi:

- **Định nghĩa event:** những loại hành động nào phải ghi.
- **Thu thập:** nguồn log từ mọi tài sản bắt buộc.
- **Vận chuyển:** pipeline có cơ chế tránh mất dữ liệu và cảnh báo drop.
- **Phân quyền:** người quản trị ứng dụng không tự sửa/xóa bản chứng cứ.
- **Retention:** dữ liệu được giữ theo kỳ được phê duyệt, kể cả ràng buộc privacy.
- **Integrity:** có cơ chế phát hiện sửa/xóa trong phạm vi đã cam kết.
- **Testing:** event thử đi qua pipeline và phép test tamper có kết quả phù hợp.
- **Monitoring:** khi nguồn im lặng hoặc cấu hình log thay đổi có alert.

Một trạng thái “logging enabled” tại một account không đủ chứng minh mọi mục trên.

### 5.2. Metadata của control

Một control nên có:

| Thành phần | Câu hỏi |
|---|---|
| control_id, name, objective | Control nhằm bảo vệ điều gì? |
| obligation_mapping | Đáp ứng những nghĩa vụ nào? |
| control_type | Preventive, detective, corrective hoặc hỗn hợp? |
| nature | Manual, automated hoặc hybrid? |
| owner/operating_team | Ai thực hiện, ai chịu trách nhiệm và ai verify? |
| in_scope_assets | Những loại tài sản/môi trường nào thuộc phạm vi? |
| expected_condition | Assertion nào có thể kiểm chứng và bị chứng minh sai? |
| frequency/event trigger | Control chạy theo kỳ hay được kích hoạt khi thay đổi? |
| evidence_contract | Cần dữ liệu nào, từ đâu, kỳ bao nhiêu, tiêu chí chất lượng? |
| test_method | Design, configuration, operation, negative test, sampling? |
| failure_handling | Khi fail sẽ alert, block, mở ticket hoặc xử lý thế nào? |
| exception_process | Ai có thể phê duyệt ngoại lệ, scope và expiry? |
| version | Phiên bản control và ngày hiệu lực |

### 5.3. Ví dụ control có thể kiểm chứng

~~~yaml
control_id: "CTRL-IAM-PRIV-001"
name: "MFA for interactive privileged access"
mapped_obligations:
  - "OBL-ACCESS-001"
scope:
  assets: "production-platforms"
  identities: "interactive-privileged-principals"
assertion: >
  All interactive privileged login paths enforce approved MFA,
  except explicitly approved exceptions permitted by the policy.
control_owner: "identity-platform"
assurance_owner: "security-assurance"
execution:
  type: "automated-and-manual"
  frequency: "continuous-check-plus-quarterly-review"
evidence_contract:
  population_source: "privileged-identity-inventory"
  artifacts:
    - "Effective authentication policy export"
    - "Time-bounded exception register"
    - "Controlled authorization test"
validation:
  positive_case: "Expected admin MFA flow succeeds"
  negative_case: "Attempt to bypass MFA is denied"
  pass_condition: "No unapproved privileged paths outside MFA enforcement"
  limitations: "No claim for identities outside the declared inventory"
failure_handling:
  severity_rationale: "Privileged identity exposure"
  remediation_owner: "identity-platform"
~~~

Dữ liệu minh họa giúp nhìn rõ sự khác nhau giữa **có policy** và **chứng minh mọi đường admin thuộc scope thực sự được bảo vệ**.

### 5.4. Kiểm tra control theo chiều thời gian

Để chứng minh một control đã hoạt động **trong kỳ**, cần hỏi:

- Control được trigger bao nhiêu lần theo kỳ vọng?
- Có lần nào không chạy hoặc chạy sai thời hạn?
- Kết quả có được phê duyệt, xử lý ngoại lệ và lưu dấu vết?
- Trong kỳ có asset/nhóm người dùng nào mới được thêm vào population?
- Có gap giữa thời điểm thay đổi và thời điểm control được bật?
- Có điều chỉnh policy hoặc rule làm thay đổi cách đánh giá giữa kỳ?

Ví dụ quarterly access review: bốn email nhắc lịch không chứng minh bốn quý đã được review. Cần danh sách đối tượng, người reviewer, quyết định, action được xử lý và dấu thời gian, phù hợp với quy định của tổ chức.

### 5.5. Không đồng nhất evidence collection với control effectiveness

Một agent có thể thu screenshot mỗi ngày nhưng hình ảnh không chứng minh vì sao cấu hình đó an toàn. Một API export là dữ liệu hữu ích, nhưng nếu filter loại mất những asset mới, report kết luận PASS có thể sai. Mọi tự động hóa evidence cần kiểm chứng cả **điều kiện nội dung** và **mẫu số phạm vi**.

## 6. Bằng chứng duy trì compliance: thiết kế cho kiểm chứng lại

### 6.1. Bằng chứng phục vụ assertion, không chỉ phục vụ lưu trữ

Bộ evidence liên tục nên trả lời:

- Assertion nào được kiểm và tiêu chí PASS là gì?
- Trong **kỳ nào** và **scope nào**?
- Dữ liệu đến từ source nào, quyền thu thập ra sao?
- Có đủ population và mẫu số, hay bỏ sót tài sản mới?
- Phương pháp xử lý, phiên bản rule và transform có được ghi lại?
- Kết quả kiểm tra, ngoại lệ và giới hạn là gì?
- Có thể bảo vệ và tìm lại bản gốc trong suốt kỳ retention không?

### 6.2. Năm yêu cầu chất lượng then chốt

| Yêu cầu | Ý nghĩa | Ví dụ lỗi |
|---|---|---|
| **Relevance** | Evidence trực tiếp hỗ trợ assertion đúng control | Báo cáo backup job được dùng để chứng minh restore được |
| **Sufficiency** | Đủ mẫu, kỳ và phạm vi để kết luận | Chỉ kiểm một account khi yêu cầu mọi account production |
| **Reliability/provenance** | Nguồn, phương pháp, quyền và người phát hành đáng tin | File CSV do người quản trị tự sửa không có xác nhận |
| **Integrity** | Có cách phát hiện sửa đổi trái phép đối với artifact và mốc tham chiếu | Hash lưu cạnh file với cùng quyền sửa |
| **Timeliness** | Evidence phù hợp thời điểm/kỳ và thay đổi của hệ thống | Screenshot từ trước khi triển khai kiến trúc mới |

Cần bổ sung **completeness, accuracy, confidentiality và traceability** khi dữ liệu có nhiều nguồn hoặc nhạy cảm.

### 6.3. Data quality và population integrity

Giả sử 50 cloud account production nhưng tool chỉ thu được cấu hình từ 47 account. Nếu dashboard hiển thị **47/47 control PASS = 100%**, đây là tỷ lệ của **nguồn đã kết nối**, không phải tỷ lệ của mọi account bắt buộc. Báo cáo đúng hơn cần phân biệt:

- **Required population:** 50.
- **Successfully evaluated:** 47.
- **Passed trong nhóm đã đánh giá:** giả sử 47.
- **Not evaluated / telemetry gap:** 3.
- **Verified coverage toàn phạm vi:** 47/50 = 94%, nếu mọi assertion ở 47 đã đạt.

Không tự coi 3 account chưa kiểm là FAIL kỹ thuật đã xác nhận, nhưng phải đưa chúng vào **evidence gap/INCONCLUSIVE** và risk triage.

### 6.4. Evidence register tham khảo

~~~yaml
evidence_id: "COMP-EV-2026-081"
assessment_id: "COMP-2026-Q4-PAY"
control_id: "CTRL-LOG-01"
source:
  system: "cloud-organization-inventory"
  collection_method: "approved-readonly-api"
  collector_identity: "compliance-evidence-reader"
collected_at: "2026-11-28T07:20:00Z"
evaluated_period:
  start: "2026-11-01T00:00:00Z"
  end: "2026-11-28T07:00:00Z"
scope:
  service: "payments"
  environment: "production"
  expected_assets: 50
  observed_assets: 47
artifact:
  reference: "restricted-evidence-store/COMP-EV-2026-081"
  digest_algorithm: "SHA-256"
  digest_value: "EXAMPLE_ONLY_NOT_A_REAL_HASH"
test:
  test_id: "COMP-TEST-LOG-01"
  control_version: "v3"
  passed: 47
  failed: 0
  not_evaluated: 3
result: "INCONCLUSIVE_FOR_FULL_SCOPE"
limitations:
  - "Ba account production không nằm trong đường thu thập hiện tại"
  - "Evidence không chứng minh trạng thái của asset ngoài scope đã thu"
reviewer_role: "security-assurance"
classification: "INTERNAL-RESTRICTED"
~~~

Đây là **bản ghi mẫu**, không phải evidence hay kết quả audit có thật. Một giá trị digest giả định hoặc nhãn “PASS” do người thu tự ghi chưa làm chứng cứ trở nên đáng tin. Cần giữ artifact, phương pháp và trust anchor phù hợp.

### 6.5. Chu kỳ sống của evidence

~~~mermaid
flowchart LR
    SOURCE["System of record"] --> COLLECT["Thu đúng quyền và scope"]
    COLLECT --> CHECK["Schema / population / time check"]
    CHECK --> STORE["Kho evidence phân quyền"]
    STORE --> VERIFY["Test assertion + reviewer"]
    VERIFY --> REPORT["Assurance verdict"]
    REPORT --> RETAIN["Retention / expiry / audit trail"]
    RETAIN --> REVIEW["Refresh khi thay đổi hoặc đến kỳ"]
    REVIEW --> COLLECT
~~~

Một quy trình phù hợp gồm:

1. **Inventory evidence requirements:** kiểm soát nào cần evidence, nguồn, kỳ và thời hạn.
2. **Collection:** ưu tiên tài khoản read-only, điều kiện API được phê duyệt, ghi phương pháp.
3. **Data quality checks:** đối soát population, missing fields, timestamp, parse errors.
4. **Validation:** chạy test, gắn result PASS/FAIL/INCONCLUSIVE đúng assertion.
5. **Protection:** mã hóa khi cần, giới hạn quyền, audit truy cập, giữ integrity metadata.
6. **Retention:** giữ theo chính sách và nghĩa vụ áp dụng; không lưu dữ liệu nhạy cảm vô hạn.
7. **Reassessment:** khi source đổi, control đổi hoặc dữ liệu hết hạn phải thu lại.
8. **Deletion/archival:** xử lý expiry có chứng cứ và điều kiện giữ hợp lệ.

### 6.6. Evidence đã bị biến đổi phải có trace

Log thô, log đã normalize và báo cáo tổng hợp có thể khác byte nhưng vẫn liên quan cùng một sự kiện. Nếu evidence được redacted hoặc chuyển định dạng, cần mô tả:

- Original reference và quyền xem.
- Transformation version, thời điểm, actor và quy tắc.
- Digest của bản gốc và bản đã chuyển nếu cần.
- Số bản ghi trước/sau, field bị ẩn và lý do.
- Cách auditor đối chiếu lại khi được phép.

Điều này đặc biệt quan trọng với log chứa dữ liệu cá nhân, kết quả pentest, hồ sơ HR và artifact nhà cung cấp.

### 6.7. Giới hạn kết luận về integrity

Checksum/hash có thể chứng minh file đang kiểm khớp với một giá trị tham chiếu đáng tin. Nếu attacker sửa được **cả file và checksum**, việc đối chiếu có thể bị đánh lừa. Chữ ký số giúp gắn với một signer theo mô hình khóa nhưng không chứng minh sự kiện nguồn đã trung thực hoặc không thiếu record. Để chứng minh audit trail theo kỳ cần xem **population, source completeness, checkpoint, trust boundary và chain of custody**.

## 7. Continuous compliance monitoring và phát hiện drift

### 7.1. Compliance drift là gì?

**Drift** là tình trạng hệ thống, hành vi, control hoặc phạm vi nghĩa vụ thay đổi khiến trạng thái hiện tại khác trạng thái đã được đánh giá hoặc kỳ vọng, ví dụ:

- Tài khoản privileged mới không nằm trong chính sách MFA.
- Bucket mới không có encryption hoặc retention như baseline bắt buộc.
- Cloud account mới không gửi log đến kho trung tâm.
- Log retention bị rút ngắn, dữ liệu bị xóa ngoài quy trình.
- Rule phát hiện bị tắt vì giảm false positives.
- Một dịch vụ xử lý dữ liệu cá nhân chuyển region hoặc thêm subprocessor chưa đánh giá.
- Kỳ access review, DR test hoặc pen test bị trễ so với quy định.
- Một ngoại lệ hết hạn nhưng chưa được xử lý.
- Auditor xác định requirement đổi nhưng control mapping chưa cập nhật.

Phải giám sát **trạng thái kỹ thuật và nghĩa vụ quy trình**, không chỉ scan cấu hình cloud.

### 7.2. Các loại tín hiệu

| Tín hiệu | Đối tượng | Ví dụ chỉ số |
|---|---|---|
| **Configuration posture** | IAM, storage, network, logging, encryption | Số tài sản vi phạm baseline / tổng tài sản |
| **Inventory coverage** | Account, cluster, service, danh tính, dữ liệu | Asset không có control owner hoặc telemetry |
| **Operational execution** | Review quyền, backup restore, incident exercise | Kỳ cần thực hiện so với kỳ đã có evidence |
| **Pipeline/data quality** | Log agent, collector, parser, evidence collector | Last-seen, missing fields, queue lag, drop |
| **Change events** | Deploy, policy, architecture, vendor, data flow | Change cần reassessment nhưng chưa hoàn tất |
| **Finding/exception** | Ticket, accepted risk, remediation | Quá hạn, chưa retest, ngoại lệ hết hạn |
| **Independent assurance** | Audit nội bộ/độc lập, pen test | Findings, scope và action closure |
| **Legal/contractual change** | Nghĩa vụ đã được xác minh | Yêu cầu mới/đổi cần mapping và review |

Một hệ thống chỉ thu cấu hình kỹ thuật sẽ không tự nhìn thấy lỗi **không có hồ sơ review đúng kỳ** hoặc **hợp đồng đổi nghĩa vụ**.

### 7.3. Chọn tần suất theo rủi ro

Một ví dụ operating cadence:

| Loại kiểm soát | Cách giám sát khả thi | Cần xác định thêm |
|---|---|---|
| MFA cho admin | Kiểm tra liên tục khi đổi principal/role, đối soát theo kỳ | Có đường local, API, break-glass không? |
| Storage encryption | Policy-as-code trước deploy và kiểm tra cấu hình sau deploy | Key responsibility và dữ liệu legacy |
| Security logging | Synthetic event/heartbeat, drop metrics, alert khi tắt sink | Nguồn ít event, late arrival và data quality |
| Vulnerability management | Scan định kỳ và theo thay đổi, tracking remediation | Coverage của scan và ngoại lệ đã phê duyệt |
| Access review | Review theo kỳ yêu cầu và audit hồ sơ hoàn thành | Population và quyền thừa kế |
| DR readiness | Restore component và diễn tập đầu cuối theo BIA/risk | Scenario, RTO/RPO, data integrity |
| Vendor assurance | Rà soát theo risk tier và khi có thay đổi trọng yếu | Data flow, subprocessor, audit report scope |
| Contractual obligation | Theo dõi lifecycle hợp đồng và amendments | Người diễn giải điều khoản và thời điểm hiệu lực |

Không có tần suất “hàng ngày” đúng cho mọi loại control. Continuous assurance là **khả năng nhận biết và phản ứng kịp thời theo rủi ro**, kết hợp automation, review theo kỳ và kiểm tra theo trigger.

### 7.4. Tín hiệu phải có phương án xử lý

Một cảnh báo posture không nên dừng ở “red” trên dashboard. Mỗi alert có thể cần:

- Control ID và obligation mapping.
- Asset ID, owner, production/sensitivity context.
- Cấu hình kỳ vọng so với observed; timestamp và rule version.
- Evidence ID/truy vấn xác nhận.
- Mức rủi ro và hạn xử lý theo chính sách.
- Biện pháp tự khắc phục nếu an toàn, hoặc ticket/escalation.
- Exception hợp lệ nếu có; không giấu trạng thái risk acceptance.
- Kết quả retest sau thay đổi và lịch sử sự kiện.

Nếu hệ thống **tự sửa cấu hình** bằng một policy enforcement, cần có change/audit trail, kiểm soát tác động nghiệp vụ và khả năng rollback. Không tự xóa resource hoặc chặn production một cách mù quáng chỉ để dashboard PASS.

### 7.5. False positive, false negative và silent failure

- **False positive:** công cụ báo vi phạm vì không hiểu ngoại lệ hợp lệ hoặc field được đổi tên.
- **False negative:** control thật sự sai nhưng rule bỏ sót đường bypass hoặc tài sản ngoài inventory.
- **Silent failure:** collector ngừng thu, parser lỗi, engine không chạy mà dashboard vẫn hiển thị kết quả cũ.

Assurance cần kiểm tra **sức khỏe của công cụ assurance**, gồm last successful scan, số nguồn kỳ vọng, số asset được đánh giá, error rate, phiên bản rule và test canary. Một dashboard 100% PASS với **0 tài sản được kiểm** là trạng thái rủi ro, không phải kết quả tốt.

## 8. Gắn compliance vào thay đổi kỹ thuật và DevSecOps

### 8.1. Shift-left và runtime verification

Hai hướng bổ sung nhau:

- **Shift-left:** kiểm chứng yêu cầu trước triển khai qua architecture review, code review, IaC scanning, policy-as-code, unit/integration test.
- **Runtime continuous validation:** xác minh trạng thái thực tế sau deploy, qua inventory, effective permissions, logging và kiểm tra vận hành.

Không nên coi CI/CD PASS là bằng chứng duy nhất. Runtime có thể bị đổi trực tiếp qua console, drift vì provider, sự cố hoặc có asset ngoài IaC.

### 8.2. Các điểm chặn trong delivery pipeline

~~~mermaid
flowchart LR
    REQ["Requirement / change proposal"] --> DESIGN["Design + scope impact"]
    DESIGN --> CODE["Code / IaC / policy"]
    CODE --> TEST["Automated control tests"]
    TEST --> GATE{"Critical requirements pass?"}
    GATE -- "Không" --> FIX["Sửa / phê duyệt exception theo policy"]
    FIX --> TEST
    GATE -- "Có" --> DEPLOY["Deploy / change record"]
    DEPLOY --> RUNTIME["Verify effective state"]
    RUNTIME --> EV["Evidence + change-linked assessment"]
    EV --> MON["Drift monitoring"]
    MON --> REQ
~~~

Ví dụ khi tạo cloud account mới:

1. Provisioning yêu cầu owner, environment, data class.
2. Account phải nhận baseline IAM, logging, monitoring và backup theo scope.
3. Policy-as-code kiểm tra cấu hình trước khi bàn giao.
4. Synthetic event kiểm tra log đi đến hệ thống trung tâm.
5. Runtime scanner xác minh effective configuration.
6. Evidence liên kết account ID, change ID, test ID và control version.
7. Chỉ đóng onboarding khi critical gates đạt hoặc có quyết định ngoại lệ đúng quyền hạn.

### 8.3. Các thay đổi cần impact assessment

- Thêm/mở rộng xử lý dữ liệu cá nhân hoặc dữ liệu nhạy cảm.
- Đổi phạm vi lưu trữ, region, retention hoặc KMS.
- Thêm account, identity, role, đặc quyền hoặc đường hỗ trợ vendor.
- Thay architecture từ VM sang container/serverless hoặc hybrid cloud.
- Thêm SaaS, subprocessor hoặc tích hợp API.
- Đổi logging, backup, vulnerability management hoặc incident response.
- Thay policy/standard/contract hoặc risk acceptance.
- Mua lại, hợp nhất hoặc phân tách pháp nhân/hệ thống.

Một thay đổi không liên quan tới code, ví dụ hợp đồng khách hàng bổ sung yêu cầu thông báo sự cố, vẫn có thể làm thay đổi control obligation và playbook.

### 8.4. Gating có giới hạn và quản trị rủi ro

Không nên chặn mọi deployment khi một dashboard bất kỳ báo đỏ. Cần phân loại:

- **Critical gate** liên quan dữ liệu/đặc quyền/nghĩa vụ bắt buộc: không được bỏ qua ngoài cơ chế phê duyệt được định nghĩa.
- **Remediation có hạn** cho sai lệch không trọng yếu hoặc không trực tiếp ảnh hưởng go-live.
- **Exception:** có scope, reason, compensating control, approver và expiry.
- **False positive:** xử lý nguồn đánh giá, không tạo đường bỏ qua vĩnh viễn.
- **Emergency change:** vẫn phải có owner, ghi nhận lý do, theo dõi và kiểm tra sau triển khai.

Gating là một phần quản trị thay đổi, không phải công cụ tự tạo quyền miễn trừ compliance.

## 9. Audit readiness quanh năm

### 9.1. Audit readiness là kết quả của vận hành

Tổ chức chuẩn bị cho kỳ audit tốt hơn khi có sẵn:

- Danh mục yêu cầu, scope, trách nhiệm và phiên bản.
- Control register kèm assertion, tần suất, owner và kỳ bằng chứng.
- Evidence manifest có thể truy vết lại source/test.
- Lịch thay đổi control và những ngoại lệ trong kỳ.
- Finding register, risk acceptance và các kết quả retest.
- Kết quả independent test, vendor review và bài tập DR/IR phù hợp.
- Hồ sơ chứng minh những người có quyền đã thực sự thực hiện review, approval và corrective actions.

Một **bộ tài liệu đã hoàn chỉnh vào cuối kỳ** phải phản ánh đúng điều đã xảy ra trong kỳ, không được dựng lại hồ sơ lịch sử như thể control đã thực hiện đúng hạn khi thực tế không có.

### 9.2. Readiness review nên hỏi gì?

| Câu hỏi | Bằng chứng |
|---|---|
| Nghĩa vụ nào áp dụng và tại sao? | Obligation register, source reference, legal/contract assessment |
| Scope có khớp thực tế không? | Service/data/asset inventory, data flow và vendor register |
| Controls nào được dùng đáp ứng? | Mapping, control objective, version và ownership |
| Control đã hoạt động khi nào? | Operational record, log, approval, test timestamps |
| Những tài sản nào chưa được kiểm? | Population reconciliation, data quality dashboard |
| Có ngoại lệ hoặc finding nào? | Risk register, exception, CAPA, retest |
| Control nào thay đổi trong kỳ? | Change records, policy/architecture diff |
| Bằng chứng có bảo vệ/truy xuất được không? | Evidence manifest, ACL, retention, collection method |
| Kết quả trước đó còn hiệu lực? | Drift checks, change impact review, refresh evidence |

### 9.3. Đừng đánh đồng report độc lập với compliance toàn tổ chức

Một báo cáo SOC 2, chứng nhận ISO/IEC 27001 hoặc báo cáo đánh giá độc lập có thể hỗ trợ assurance trong **scope và kỳ được mô tả**. Cần kiểm tra:

- Đúng dịch vụ, pháp nhân, region, môi trường, hoạt động.
- Criteria áp dụng, loại báo cáo và kỳ hiệu lực.
- Ngoại lệ, ý kiến kiểm tra và hạng mục bị loại trừ.
- Các controls bổ sung mà khách hàng hoặc nhà cung cấp phụ phải vận hành.
- Các thay đổi từ lúc báo cáo kết thúc đến thời điểm ra quyết định.

Không suy ra “không có lỗ hổng” hoặc “mọi yêu cầu đã đạt” chỉ từ logo chứng nhận hay kết quả pass của một audit.

### 9.4. Báo cáo định kỳ dựa trên bằng chứng

Một báo cáo tháng/quý hữu ích nên tách:

1. **Applicability update:** yêu cầu mới/đổi, hợp đồng, scope.
2. **Control coverage:** có bao nhiêu assertion đã được kiểm và đạt trong kỳ.
3. **Evidence status:** đủ, thiếu, hết hạn, chưa thể truy xuất.
4. **Control failures:** loại control, asset, risk, tuổi finding.
5. **Remediation:** tiến độ correction, CAPA, tỷ lệ retest đạt.
6. **Exceptions:** còn hiệu lực, sắp hết hạn, quá hạn.
7. **Material changes:** tác động từ cloud, data, identity và vendor.
8. **Decisions required:** điểm phải phê duyệt hoặc đầu tư, rủi ro còn lại.
9. **Scope/limitations:** những gì chưa được đánh giá hoặc không thể kết luận.

Dashboard có thể hỗ trợ đọc nhanh, nhưng báo cáo cần giữ **mẫu số, kỳ, phương pháp và limitations**, tránh tạo cảm giác chính xác giả.

## 10. Ownership và mô hình phối hợp duy trì compliance

Một tổ chức có thể có đội compliance riêng nhưng khả năng đáp ứng yêu cầu thực tế thường nằm ở **người thiết kế, triển khai và vận hành hệ thống**. Nếu không xác định trách nhiệm, nghĩa vụ dễ bị hiểu là “việc của auditor” và chỉ được chú ý vào kỳ đánh giá.

### 10.1. Các vai trò thường cần

| Vai trò | Trách nhiệm chủ yếu | Ví dụ hoạt động |
|---|---|---|
| **Business/service owner** | Chịu trách nhiệm rủi ro và kết quả đối với dịch vụ | Phê duyệt criticality, scope và ưu tiên remediation |
| **Legal / regulatory compliance** | Theo dõi, diễn giải nghĩa vụ pháp lý/hợp đồng trong thẩm quyền | Review applicability, effective dates, nghĩa vụ báo cáo |
| **Security governance / GRC** | Quản lý control framework, register, policy và quy trình ngoại lệ | Control mapping, compliance calendar, dashboard |
| **Control owner** | Chịu trách nhiệm control đáp ứng objective | Access review, backup protection hoặc logging retention |
| **Engineering / platform / operations** | Triển khai, vận hành, thu telemetry và sửa kỹ thuật | IaC, runtime validation, remediation deployment |
| **Security assurance assessor** | Kiểm chứng assertion, chất lượng evidence và retest | Thiết kế phép kiểm, ghi verdict có scope |
| **Internal / external auditor** | Đánh giá theo mandate, kỳ và tiêu chí độc lập phù hợp | Kiểm tra evidence, lập observation/finding |
| **Privacy / data protection** | Đánh giá nghĩa vụ liên quan dữ liệu cá nhân theo vai trò | Data mapping, retention và xử lý quyền dữ liệu |
| **Third-party / procurement owner** | Quản lý phụ thuộc hợp đồng và thay đổi nhà cung cấp | Risk tier, kiểm tra subprocessor, reassessment |
| **Risk acceptance authority** | Quyết định xử lý rủi ro trong giới hạn quyền hạn | Phê duyệt ngoại lệ có điều kiện và expiry |

Tên đội có thể khác, nhưng cần phân biệt **ai thực hiện control**, **ai xác minh** và **ai quyết định risk acceptance**. Không mặc định bộ phận compliance có thể sửa IAM hay audit pipeline nếu họ không sở hữu công cụ.

### 10.2. RACI tham khảo

RACI dùng R = Responsible (thực hiện), A = Accountable (chịu trách nhiệm cuối cho quyết định/đầu ra), C = Consulted (tham vấn), I = Informed (được thông báo).

| Hoạt động | Legal/Compliance | Service owner | Control owner | Security assurance | Risk owner |
|---|---|---|---|---|---|
| Diễn giải applicability pháp lý | **A/R** | C | C | C | I |
| Chốt phạm vi asset/data của dịch vụ | C | **A/R** | R | C | I |
| Triển khai control kỹ thuật | I | A | **R** | C | I |
| Thực hiện control định kỳ | I | A | **R** | C | I |
| Kiểm tra hiệu lực/evidence | C | I | C | **A/R** | I |
| Khắc phục finding | I | A | **R** | C | I |
| Chấp nhận residual risk đúng quyền | C | C | C | C | **A/R** |
| Báo cáo cấp quản lý | R | C | C | R | **A** theo governance |

Bảng chỉ minh họa. Trong thực tế, **mỗi quyết định nên có một accountable owner rõ ràng** theo governance được phê duyệt. Không áp cứng RACI nếu làm mất các yêu cầu độc lập của kiểm toán.

### 10.3. Kiểm soát kế thừa và control dùng chung

Một tổ chức nhiều dịch vụ thường có **central control** như SSO/MFA, SIEM, vulnerability scanner hoặc platform backup. Service owner có thể dựa vào control tập trung nếu:

1. Central control thật sự bao phủ service, môi trường và account của họ.
2. Có evidence rõ phạm vi, kỳ, phiên bản và người vận hành.
3. Có cam kết xử lý sự cố hoặc drift ở cả mức platform và service.
4. Các control bổ sung tại application/customer side đã được xác định.
5. Không có đường bypass hoặc tài sản ngoài quản trị không nằm trong mẫu số.

Không nên mỗi service tự đánh PASS chỉ vì central platform có một bản chính sách tốt. Service owner cần chứng minh **onboarding và coverage** thực tế.

### 10.4. Control ownership khi nhân sự thay đổi

Một nguy cơ compliance phổ biến là control phụ thuộc vào một cá nhân:

- Chỉ một kỹ sư biết cách xuất evidence từ cloud.
- Chỉ một người được phép approve access review.
- Contact của vendor hoặc auditor đã nghỉ nhưng chưa cập nhật.
- Credential collector chưa có quy trình rotate và bàn giao.
- Runbook nằm trong tài khoản cá nhân, không có quyền dự phòng.

Cần có owner theo **vai trò**, đại diện thay thế, quản lý quyền tối thiểu, tài liệu hóa workflow và kiểm thử khi nhân sự chủ chốt vắng mặt. Một quy trình được thiết kế để chạy hàng quý nhưng không có backup owner có thể thất bại dù hạ tầng kỹ thuật vẫn hoạt động.

## 11. Compliance với third-party và shared responsibility

### 11.1. Nghĩa vụ không dừng ở ranh giới công ty

Khi dịch vụ phụ thuộc cloud, SaaS, outsourced operations hoặc subprocessor, cần xác định:

- Nhà cung cấp có xử lý loại dữ liệu thuộc phạm vi nghĩa vụ không?
- Hệ thống của vendor và khách hàng giao tiếp qua quyền, key và network nào?
- Ai thực thi encryption, access control, logging, incident notification và deletion?
- Có yêu cầu đánh giá subcontractor, thay đổi region hoặc continuity không?
- Bằng chứng vendor đưa ra có đúng service/region/kỳ hay chỉ là tài liệu công ty chung?
- Những quyền hoặc cấu hình nào khách hàng phải tự bật để đạt control?
- Nhà cung cấp có thay đổi mô hình dịch vụ làm mapping cũ không còn đúng không?

Một nhà cung cấp “đã được kiểm toán” không có nghĩa tổ chức sử dụng tự động đáp ứng mọi nghĩa vụ.

### 11.2. Shared responsibility matrix ví dụ

Giả sử doanh nghiệp dùng SaaS lưu ticket hỗ trợ khách hàng:

| Control objective | Vendor chịu trách nhiệm | Khách hàng chịu trách nhiệm | Phép kiểm tích hợp |
|---|---|---|---|
| Xác thực người dùng | Hỗ trợ SSO, bảo vệ đường admin do vendor quản lý | Cấu hình IdP, MFA và vòng đời user của tenant | Test login, đường bypass và phân quyền |
| Quản lý truy cập | Cung cấp RBAC và audit | Cấp role/nhóm cho nhân viên theo nhu cầu | Effective permission review và test deny |
| Mã hóa dữ liệu | Mã hóa nền tảng và key controls đã cam kết | Cấu hình customer-managed key khi tính năng và hợp đồng yêu cầu | Đối chiếu design, phạm vi key và test theo khả năng |
| Security logging | Sinh log, bảo vệ log ở nền tảng | Bật export, chọn retention và giám sát tenant nếu khách hàng được giao | Synthetic event đến SIEM, nguồn và thời gian |
| Backup/DR | Phục hồi nền tảng theo scope/SLA | Đánh giá RTO/RPO với BIA, phương án export/exit nếu cần | Review test report và ứng dụng phụ thuộc |
| Incident handling | Điều tra và thông báo theo thỏa thuận | Tiếp nhận, quyết định, phản ứng nội bộ và nghĩa vụ tiếp theo | Communications exercise và contact test |
| Deletion/retention | Xử lý bản sao vendor quản lý theo điều khoản | Xác định dữ liệu/hạn, thu hồi quyền, xử lý bản export | Exit checklist và confirmation có scope |

Bảng trên không phải mô hình trách nhiệm cố định cho mọi SaaS. Phải đối chiếu **hợp đồng và hướng dẫn vận hành dịch vụ được mua**.

### 11.3. Đánh giá evidence nhà cung cấp

Nên phân biệt:

- **Self-attestation:** mô tả tự khai, có thể dùng triage nhưng không tự đủ cho critical assertion.
- **Chứng nhận/báo cáo độc lập:** xem scope, kỳ, ngoại lệ, subservice organizations và complementary controls.
- **Operational evidence:** khả năng trace control trong dịch vụ thật và kỳ cần đánh giá.
- **Test evidence:** kết quả test được phép, đủ điều kiện và không gây tác động trái phép.
- **Bridge/period updates:** thông tin về thay đổi sau kỳ kiểm của báo cáo độc lập.

Nếu báo cáo SOC 2 của vendor không bao phủ add-on API đang được dùng, cần đánh giá riêng phần đó; không suy rộng. Nếu một chứng nhận ISO/IEC 27001 chỉ bao phủ ISMS cho bộ phận nhất định, cần xét phạm vi thực sự của dịch vụ.

### 11.4. Theo dõi vendor trong suốt hợp đồng

Những trigger thường cần đánh giá lại:

- Thêm subprocessor hoặc thay nơi xử lý dữ liệu.
- Bổ sung tích hợp có quyền đọc/ghi nhạy cảm.
- Vendor thông báo incident, outage hoặc thay đổi control quan trọng.
- Kỳ report độc lập mới có exceptions hoặc thay đổi scope.
- SLA, RTO/RPO, retention hoặc nghĩa vụ thông báo thay đổi.
- Vendor không khắc phục finding đúng hạn.
- Gia hạn/hủy hợp đồng và thực hiện data exit.

**Chấm dứt hợp đồng** cũng là sự kiện compliance: cần thu hồi API keys, SSO grants, quyền truy cập hỗ trợ, kiểm tra luồng dữ liệu ngừng và có bằng chứng về export/xóa dữ liệu theo điều khoản áp dụng.

## 12. Quản lý findings, corrective actions và risk acceptance

### 12.1. Phân biệt các tình trạng

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| **Control PASS_WITH_SCOPE** | Bằng chứng hỗ trợ assertion trong phạm vi, kỳ đã xét | 47 account trong scope kiểm thực sự đáp ứng test |
| **Control FAIL** | Có bằng chứng điều kiện bắt buộc không đạt | Một account production không có audit logging |
| **INCONCLUSIVE** | Chưa đủ bằng chứng để xác nhận đạt/không đạt | Agent không truy cập được ba account |
| **NOT_TESTED** | Chưa thực hiện phép kiểm cần thiết | DR runbook tồn tại nhưng chưa diễn tập |
| **NOT_APPLICABLE** | Điều kiện được chứng minh không áp dụng với scope | Một loại workload không tồn tại trong dịch vụ |
| **RISK_ACCEPTED** | Sai lệch còn tồn tại nhưng có quyết định chấp nhận hợp lệ trong quyền hạn | Legacy workload có ngoại lệ tạm thời |
| **CLOSED_VERIFIED** | Remediation đã được retest và phê duyệt đóng | Test mới chứng minh toàn population đạt assertion |

**Risk acceptance là quyết định quản trị**, không phải trạng thái control đạt về kỹ thuật. Một nghĩa vụ không cho phép ngoại lệ vẫn phải được xử lý theo yêu cầu tương ứng dù nội bộ muốn chấp nhận rủi ro.

### 12.2. Cấu trúc finding có thể hành động

Finding nên có:

1. **Criterion:** nghĩa vụ/control version áp dụng.
2. **Condition:** điều quan sát được, số asset và kỳ.
3. **Evidence:** ID, nguồn, phương pháp kiểm, quality.
4. **Scope/limitation:** phần đã xác minh và phần chưa kiểm.
5. **Effect/risk:** impact có thể xảy ra, tách impact thực tế.
6. **Cause:** nguyên nhân đã xác minh hoặc giả thuyết cần RCA.
7. **Owner/severity/due:** người thực hiện, mức ưu tiên theo risk rating.
8. **Remediation:** correction và hành động ngăn tái diễn.
9. **Retest assertion:** điều kiện PASS và dữ liệu cần có.
10. **Decision history:** phê duyệt, ngoại lệ, thay đổi hạn và closure.

Không nên viết “chưa an toàn” hoặc “không compliant” chung chung khi điều kiện thực tế chỉ cho thấy một control chưa được kiểm chứng.

### 12.3. Correction khác corrective action

Giả sử ba cloud account mới không có audit sink:

- **Correction:** bật logging cho ba account.
- **Corrective action:** sửa provisioning workflow để account mới mặc định được tạo sink và không thể bàn giao khi test log chưa đạt.
- **Preventive action:** đối soát inventory với log sources toàn tổ chức; tạo alert khi phát hiện account chưa onboard.
- **Compensating control:** trong khi chờ sửa workflow, review control-plane audit nguồn độc lập theo kỳ.
- **Retest:** xác minh ba account đã có event và tạo account test mới để kiểm chứng workflow cùng alert.

Nếu chỉ bật log cho ba account mà không sửa provisioning, finding có nguy cơ tái diễn.

### 12.4. Retest phải đo đúng assertion

Một retest cần ghi:

- Phiên bản criterion/control sau sửa và scope dự kiến.
- Population thực tế sau remediation, các thay đổi asset.
- Data source và phương pháp test độc lập/được ủy quyền.
- Test dương: hành vi đúng phải được cho phép/ghi nhận.
- Test âm: đường bypass hoặc trạng thái vi phạm phải bị chặn/phát hiện.
- Bằng chứng config và operation; lưu thời điểm và môi trường.
- Kết quả PASS, FAIL, INCONCLUSIVE và lý do.
- Reviewer và người phê duyệt closure.
- Residual risk, exception còn hiệu lực và monitoring sau đóng.

Đối với control cần hoạt động trong một kỳ (ví dụ review quyền theo quý), một thay đổi procedure và walkthrough ngày đầu tiên chưa chứng minh effectiveness cả kỳ. Có thể lưu **IMPLEMENTED_PENDING_OPERATIONAL_VALIDATION** đến khi đủ evidence.

### 12.5. Exception management

Một exception hợp lệ thường có:

| Trường | Mục đích |
|---|---|
| exception_id, obligation/control_id | Truy vết rõ yêu cầu bị ảnh hưởng |
| asset/service/scope | Giới hạn đối tượng và môi trường |
| condition/rationale | Lý do chưa đạt và rủi ro được nhận diện |
| owner/approver | Người chịu trách nhiệm và thẩm quyền |
| start/end, review_date | Không để ngoại lệ vô thời hạn |
| compensating_controls | Control bù trừ có thể kiểm chứng |
| remediation_plan | Kế hoạch sửa, nguồn lực, hạn |
| monitoring_trigger | Điều gì làm phải đánh giá lại sớm |
| allowed/forbidden activities | Ví dụ chỉ sandbox, không xử lý production data |

Đội assurance cần kiểm tra cả **ngoại lệ quá hạn**, ngoại lệ tồn tại nhưng không có owner, và ngoại lệ áp dụng quá rộng khiến control bị vô hiệu hóa trên các tài sản khác.

## 13. Ví dụ kỹ thuật: kiểm tra compliance coverage bằng dữ liệu

### 13.1. Bài toán

Một doanh nghiệp vận hành nhiều cloud account. Theo **chính sách nội bộ giả định**, mọi account production đang hoạt động phải có:

- Cloud control-plane audit logging.
- Đường chuyển security log về trung tâm.
- Logging retention theo kỳ riêng được phê duyệt.
- Owner và inventory entry còn hiệu lực.
- Alert khi logging bị tắt hoặc nguồn ngừng phát.

Nếu chỉ truy vấn danh sách SIEM sources, account chưa onboard sẽ không xuất hiện; dashboard có thể báo 100% dù thực tế thiếu.

### 13.2. Phép đối soát theo population

SQL dưới đây là **pseudocode theo mô hình dữ liệu minh họa**; điều chỉnh theo schema, database và thời gian thực tế:

~~~sql
WITH required_accounts AS (
    SELECT account_id, service_owner, environment
    FROM organization_asset_inventory
    WHERE lifecycle_status = 'active'
      AND environment = 'production'
),
logged_accounts AS (
    SELECT DISTINCT account_id
    FROM central_log_source_inventory
    WHERE enabled = TRUE
      AND validation_status = 'PASS'
      AND last_validated_at >= :required_freshness_cutoff
)
SELECT
    r.account_id,
    r.service_owner,
    CASE
        WHEN l.account_id IS NULL THEN 'NOT_VERIFIED'
        ELSE 'VERIFIED'
    END AS logging_assurance_status
FROM required_accounts AS r
LEFT JOIN logged_accounts AS l
    ON r.account_id = l.account_id;
~~~

**Cảnh báo quan trọng:** câu truy vấn chỉ kiểm bằng chứng onboarding/validation có trong các bảng được giả định. Nó không tự chứng minh retention, integrity hay nội dung log đầy đủ. Để kiểm control, cần các phép test riêng có evidence tương ứng; kết quả NOT_VERIFIED không tự chứng minh logging thực sự bị tắt.

### 13.3. Một control có nhiều phép kiểm

| Test ID | Assertion | Evidence cần thu |
|---|---|---|
| **LOG-T1** | Mọi account required có logging source được cấu hình | Organization inventory đối chiếu logging inventory |
| **LOG-T2** | Event class bắt buộc có dữ liệu thực và đủ field | Synthetic event hoặc controlled admin change |
| **LOG-T3** | Dữ liệu tới central store trong giới hạn độ trễ | Source event, ingestion record và timestamps |
| **LOG-T4** | Đường xóa/sửa trái phép bị hạn chế hoặc phát hiện | Effective IAM/retention policy, controlled deny test |
| **LOG-T5** | Khi logging bị dừng, cảnh báo đến đúng owner | Health/heartbeat fault test, alert và acknowledgment |
| **LOG-T6** | Evidence kỳ đã lưu có integrity/scope/retention đúng | Manifest, ACL, configuration và test verification |

Một control tổng **PASS** chỉ khi các assertion bắt buộc trong scope đạt. Một test chưa có evidence nên được phản ánh bằng INCONCLUSIVE hoặc NOT_TESTED theo quy ước, không bị loại khỏi bảng mà không có lý do.

### 13.4. Kết quả ví dụ

Giả sử asset inventory có **50 account production**:

- 44 account đạt đầy đủ LOG-T1..LOG-T6.
- 2 account xác nhận thiếu log sink.
- 3 account không thể thu bằng chứng do quyền collector bị lỗi.
- 1 account đang chờ test alert route.

Kết quả phù hợp:

| Trạng thái | Số account | Tỷ lệ theo mẫu số 50 |
|---|---:|---:|
| Verified PASS | 44 | 88% |
| Confirmed FAIL | 2 | 4% |
| INCONCLUSIVE — evidence gap | 3 | 6% |
| NOT_TESTED — pending test | 1 | 2% |
| **Tổng population** | **50** | **100%** |

Không báo **44/46 = 95,7% compliant** mà không giải thích vì đã bỏ bốn account chưa chứng minh. Nếu báo metric “pass rate among evaluated conclusive accounts” thì phải ghi đúng mẫu số 46 và mục đích, tách khỏi **verified coverage toàn population**.

### 13.5. Giữ bằng chứng theo thời gian

Để duy trì assurance trong nhiều tháng, hệ thống kiểm tra có thể lưu:

- Snapshot inventory từng ngày/chu kỳ hoặc event tạo/xóa asset.
- Rule version và kỳ hạn đánh giá.
- Evidence ID, collection method và digest khi cần.
- Kết quả mỗi assertion theo asset, timestamps và độ tin cậy.
- Thay đổi trạng thái PASS → FAIL, nguyên nhân và ticket.
- Thời gian khắc phục và retest PASS.
- Khi NOT_APPLICABLE được phê duyệt hoặc scope thay đổi, giữ lịch sử quyết định.

Điều này cho phép truy vấn: **trong giai đoạn 01–30/11, account nào từng vi phạm, vi phạm tồn tại bao lâu và ai đã phê duyệt xử lý?** Ảnh dashboard ngày 30/11 không trả lời được câu hỏi lịch sử đó.

## 14. Case study 1: cloud account mới làm sai lệch kết luận tuân thủ

### 14.1. Bối cảnh

Một tổ chức có dịch vụ thanh toán ở production. Chương trình compliance định kỳ yêu cầu mọi cloud account xử lý dữ liệu khách hàng phải có audit log, access controls và evidence validation. Dashboard GRC cuối tháng báo 100% log coverage.

Đội security assurance đối soát service catalog với cloud organization inventory và phát hiện **ba account vừa được tạo trong tháng chưa được onboarding vào collector**. Việc GRC báo 100% là chính xác đối với account **đang có trong dữ liệu của GRC**, nhưng không phản ánh population thật.

### 14.2. Evidence và phân tích

| Evidence ID | Quan sát | Giới hạn |
|---|---|---|
| E-101 | Service catalog có ba account mới gắn dịch vụ production | Cần xác minh effective production status |
| E-102 | Organization inventory xác nhận account đang hoạt động | Mốc export có thể khác mốc dashboard |
| E-103 | Collector source inventory không có ba account | Cần loại trừ alias/mapping khác |
| E-104 | IAM/control-plane audit nguồn có event thay đổi quyền tại account A | Chỉ đại diện nhóm event đã kiểm |
| E-105 | Tìm kiếm central store không có event với ID nguồn sau cửa sổ ingest hợp lệ | Cần kiểm filter/retention/lag |
| E-106 | Provisioning workflow thiếu bước xác minh logging | Gợi ý root cause kỹ thuật |
| E-107 | Dashboard chỉ đếm onboarded sources | Giải thích mẫu số sai |

**Confirmed condition:** ít nhất các account được kiểm chưa có bằng chứng logging central đúng yêu cầu; với account A đã xác minh một event có ở nguồn nhưng không tới đích trong kỳ kiểm. **Potential impact:** hành vi quản trị có thể không được giám sát/điều tra đủ ở các account này. **Unknown:** toàn bộ lịch sử log và hoạt động trong kỳ còn có thể được khôi phục từ nguồn hay không.

Không kết luận "đã có breach" chỉ vì thiếu log. Không kết luận mọi event lịch sử bị mất nếu chưa kiểm tra thời gian lưu ở nguồn.

### 14.3. Quy trình xử lý

1. Tạo **finding** gắn OBL-SEC-LOG-001 và các control liên quan, liệt kê phạm vi ba account.
2. Gán severity dựa trên criticality, quyền và dữ liệu, không chỉ số lượng account.
3. Khắc phục tức thời bằng cấu hình sink/retention và quyền phù hợp.
4. Tạo event thử, theo dõi source → collector → SIEM → alert, ghi evidence IDs.
5. Sửa provisioning workflow và thêm policy-as-code gate.
6. Đối soát toàn bộ organization inventory với GRC coverage population.
7. Thêm monitor phát hiện account mới không có collector trong thời hạn đã phê duyệt.
8. Xác định khoảng lịch sử chưa kiểm chứng, backfill nếu có khả năng và ghi residual risk.
9. Retest trên account mới được tạo có kiểm soát, không chỉ ba account cũ.
10. Cập nhật dashboard với mẫu số required assets và phân loại INCONCLUSIVE/NOT_TESTED.

### 14.4. Kết luận assurance

Một báo cáo đúng nên ghi:

> Trong scope các cloud account production được kiểm ngày 28/11/2026, chương trình phát hiện thiếu coverage ở ba account mới. Bằng chứng xác nhận ít nhất một security audit event tại account A chưa tới kho trung tâm theo điều kiện test. Sau khắc phục, việc xác minh sink và event flow được thực hiện trong các account được nêu; operating effectiveness cho toàn kỳ chỉ được kết luận ở những phần có đủ evidence. Mẫu số dashboard đã được điều chỉnh theo inventory độc lập.

Bản này **không** được sửa ngược trạng thái lịch sử thành 100% PASS sau khi khắc phục. Cần giữ dấu vết khoảng gap.

## 15. Case study 2: hợp đồng thay đổi trong khi controls chưa đổi

### 15.1. Tình huống

Một doanh nghiệp đang dùng SaaS để quản lý hồ sơ hỗ trợ. Ban đầu dịch vụ chỉ xử lý dữ liệu nội bộ, với yêu cầu audit và retention thông thường. Sau khi mở rộng hợp đồng, dịch vụ bắt đầu nhận **dữ liệu khách hàng có tính nhạy cảm hơn**, đồng thời khách hàng yêu cầu một nhóm sự kiện phải có thể xuất để phục vụ điều tra theo thời hạn được thỏa thuận.

Đội mua sắm ký thay đổi hợp đồng nhưng control register vẫn giữ applicability cũ. SaaS có audit log mặc định, nhưng chưa bật export ra hệ thống của khách hàng và chưa đối chiếu kỳ retention. Không có incident xảy ra tại thời điểm phát hiện.

### 15.2. Sai lệch trong compliance lifecycle

| Lớp | Điều bị thiếu | Rủi ro |
|---|---|---|
| Obligations | Amendment chưa được đưa vào register | Requirement mới không có owner |
| Scope/data flow | Dữ liệu nhạy cảm mới chưa được phân loại | Risk tier và kiểm soát cũ không còn phù hợp |
| Shared responsibility | Không rõ ai phải bật audit export | Vendor và customer đều tưởng bên kia phụ trách |
| Implementation | Export chưa được cấu hình tại tenant | Không có chứng cứ audit tập trung theo cam kết |
| Evidence | Báo cáo audit vendor chỉ bao phủ nền tảng chung | Không chứng minh tenant configuration |
| Monitoring | Không có trigger từ hợp đồng sang security review | Drift tồn tại đến kỳ audit |

### 15.3. Hành động thực tế

1. Legal/compliance và data owner xác minh điều khoản, effective date và scope dữ liệu.
2. Cập nhật obligation register, data flow, risk tier và control mapping.
3. Vendor owner đối chiếu tính năng/giới hạn log và thỏa thuận các nghĩa vụ có thể thực hiện.
4. Customer platform bật audit export, giới hạn API key và cấu hình retention theo trách nhiệm.
5. Security assurance thử một sự kiện admin và data access giả định phù hợp quyền test.
6. Xác minh event đến đúng store, field, retention, quyền xóa và đường alert.
7. Ghi rõ khoảng thời gian trước khi control được bật, evidence còn có thể lấy và khả năng không thể kết luận cho lịch sử.
8. Tạo trigger cho hợp đồng, data processing change và subprocessor change để mở delta assessment trong tương lai.

Không nên tuyên bố “vendor vi phạm” trước khi phân tích đúng hợp đồng và ranh giới customer/vendor responsibilities. Nếu control thật sự phải có từ effective date và chưa được bật, finding cần trình bày rõ dữ kiện, owner và cách xử lý.

### 15.4. Bài học

**Duy trì compliance là quản lý thay đổi của cả nghĩa vụ lẫn hệ thống.** Continuous scanner có thể không phát hiện được yêu cầu hợp đồng mới nếu nó không được chuyển thành assertion/controle. Do đó, luồng thông tin từ legal/procurement tới engineering và security assurance là một security control quan trọng.

## 16. KPI và bảng điều khiển compliance assurance

### 16.1. Định nghĩa mẫu số trước khi tính

Một KPI về compliance nên xác định:

- **Unit:** obligation, control, assertion, service × control, asset × control, hoặc kỳ thực thi?
- **Population:** nguồn inventory độc lập nào định nghĩa các đơn vị cần đánh giá?
- **Period:** snapshot tại ngày nào hay bằng chứng hoạt động trong khoảng nào?
- **Verdict:** điều kiện PASS/FAIL/INCONCLUSIVE/NOT_TESTED/ACCEPTED_RISK?
- **Confidence:** evidence chất lượng ra sao, có ngoại lệ không?
- **Responsibility:** ai sở hữu action và deadline?

Nếu không có định nghĩa, hai dashboard dùng cùng nhãn **“Compliance 90%”** có thể đo hai điều hoàn toàn khác.

### 16.2. Bộ chỉ số đề xuất

| KPI | Cách đo | Giới hạn và nguy cơ hiểu sai |
|---|---|---|
| **Obligation applicability coverage** | Nghĩa vụ cần xem đã xác định applicability và owner / tổng nghĩa vụ cần xem | Source register thiếu làm mẫu số sai |
| **Control mapping coverage** | Nghĩa vụ applicable có control owner và assertion / nghĩa vụ applicable | Có mapping chưa chứng minh control hoạt động |
| **Verified control coverage** | Đơn vị assertion bắt buộc PASS / toàn bộ assertion bắt buộc thuộc scope | NOT_TESTED và INCONCLUSIVE không tự loại khỏi mẫu số |
| **Evidence completeness** | Assertion có evidence đủ scope/kỳ / tổng assertion cần evidence | File tồn tại chưa chứng minh evidence đáng tin |
| **Evidence freshness** | Evidence còn phù hợp thời điểm/kỳ / tổng evidence cần dùng | Evidence mới cũng có thể sai scope |
| **Population coverage** | Asset thuộc yêu cầu đã được kiểm / tổng asset thuộc yêu cầu | Dashboard chỉ nhìn onboarded assets sẽ bỏ sót |
| **Drift detection latency** | Từ thay đổi tạo sai lệch đến alert có thể hành động | Phải xác định thời điểm thay đổi thực và clock accuracy |
| **Time to remediate** | Từ finding xác nhận đến correction được triển khai | Chưa chứng minh effectiveness |
| **Verified closure time** | Từ finding xác nhận đến retest PASS và approval | Ticket Done không phải verified closure |
| **Overdue critical findings** | Critical findings quá hạn vẫn không đạt / tổng critical findings đã đến hạn | Không đổi hạn tùy tiện để làm KPI đẹp |
| **Exception expiry rate** | Ngoại lệ đến hạn nhưng chưa review / tổng ngoại lệ đến hạn | Ngoại lệ không có ngày hết hạn cũng là vấn đề |
| **Assessment change responsiveness** | Từ trigger thay đổi đến impact assessment được hoàn thành | Không đo được nếu không phát hiện trigger |
| **Recurring findings** | Finding tái xuất hiện theo root-cause taxonomy / tập finding được theo dõi | Cần mapping nguyên nhân và scope nhất quán |
| **Audit request turnaround** | Thời gian cung cấp evidence đáng tin theo yêu cầu kiểm toán | Nhanh nhưng sai evidence không có giá trị |

### 16.3. Ví dụ tính verified coverage

Giả sử trong kỳ đánh giá có **200 assertion units bắt buộc**:

- 158 đã có evidence và retest/validation PASS.
- 12 confirmed FAIL.
- 18 INCONCLUSIVE do evidence thiếu hoặc không đúng scope.
- 10 NOT_TESTED.
- 2 đang có ACCEPTED_RISK vì control chưa đạt nhưng được chấp nhận đúng thẩm quyền.

**Verified coverage = 158/200 × 100% = 79%.**

Đơn vị accepted risk **không được cộng vào PASS**. Tổng báo cáo nên hiển thị đầy đủ năm nhóm, kèm phân tổ criticality; không dùng “(158+2)/200 = 80%” như bằng chứng compliance kỹ thuật.

Cũng cần phân biệt:

- **Assessment completion:** bao nhiêu đơn vị đã được kiểm đến mức có verdict?
- **Control effectiveness coverage:** bao nhiêu đơn vị được xác minh PASS?
- **Risk decision coverage:** bao nhiêu rủi ro đã có owner và quyết định?
- **Compliance conclusion:** yêu cầu áp dụng thực tế có được đáp ứng không trong phạm vi, kỳ và giới hạn?

### 16.4. Cảnh báo về “điểm compliance” tổng hợp

Một trung bình số học có thể che một control critical FAIL. Ví dụ, dịch vụ đạt 99/100 control nhưng control thứ 100 liên quan đặc quyền root trong production không đáp ứng yêu cầu. Khi đó cần **critical gate** và severity-based reporting; không thể tuyên bố “99% secure” một cách có ý nghĩa.

Nếu chương trình xây điểm tổng hợp, nó chỉ nên là **chỉ số điều hành có phương pháp công khai**, không thay thế kết luận về nghĩa vụ cụ thể. Một số nghĩa vụ yêu cầu đạt tất cả điều kiện áp dụng, không cho phép bù trừ số học.

## 17. Hồ sơ assurance định kỳ và tài liệu audit

### 17.1. Mẫu assessment record

~~~yaml
assessment_id: "COMP-ASS-2026-11-PAY"
service_id: "payments"
period:
  from: "2026-11-01T00:00:00Z"
  to: "2026-11-28T11:00:00Z"
scope:
  environments: ["production"]
  business_owner: "payments-business"
  asset_inventory_reference: "inventory/2026-11-28"
applicability:
  register_version: "obl-register-v9"
  reviewer_role: "compliance-governance"
  changes_since_last_review:
    - "Three new cloud accounts"
controls:
  - control_id: "CTRL-LOG-01"
    assertion: "Production admin events reach central audit storage"
    required_units: 50
    evaluated_units: 47
    passed_units: 44
    failed_units: 3
    not_evaluated_units: 3
    verdict: "FAIL_WITH_SCOPE"
    evidence_refs:
      - "COMP-EV-2026-081"
      - "COMP-EV-2026-082"
    finding_ids:
      - "COMP-F-2026-019"
    limitations:
      - "Three required accounts not evaluated"
  - control_id: "CTRL-IAM-PRIV-001"
    assertion: "Interactive privileged access enforces MFA"
    verdict: "PASS_WITH_SCOPE"
    evidence_refs:
      - "COMP-EV-2026-093"
findings:
  open: 1
  awaiting_retest: 0
exceptions:
  active: 0
  expired: 0
report:
  generated_at: "2026-11-28T12:00:00Z"
  reviewer_role: "security-assurance"
  decision_owner: "payments-risk-owner"
  overall_result: "NOT_FULLY_VERIFIED"
  limitations:
    - "Không suy rộng kết quả ngoài các assertion đã kiểm"
~~~

Mọi số liệu và ID đều **minh họa**. Nếu sử dụng làm công cụ thật, cần bảo đảm số liệu nhất quán: trong ví dụ 47 evaluated = 44 PASS + 3 FAIL, ba not evaluated được ghi riêng, toàn population 50. Verdict FAIL áp cho control trong scope đã có trường hợp confirmed failure; kết luận tổng vẫn phải ghi trạng thái chưa kiểm chứng của phần còn lại.

### 17.2. Báo cáo quyết định theo ba lớp

Một báo cáo quản lý nên trình bày:

**Lớp 1 — Executive view:** nghĩa vụ trọng yếu có thay đổi không, rủi ro nổi bật, critical findings, việc cần phê duyệt.

**Lớp 2 — Control assurance:** coverage theo service/control, thời kỳ, verdict, evidence quality, ngoại lệ và action.

**Lớp 3 — Audit/evidence details:** references, test, nguyên tắc chọn mẫu, versions, data lineage, custody, detailed observations.

Không nhất thiết gửi raw evidence cho mọi người đọc; phần chi tiết cần kho lưu trữ có phân quyền và audit. Điều này giúp bảo vệ dữ liệu nhạy cảm mà vẫn bảo đảm khả năng truy vết.

### 17.3. Audit evidence khi kỳ báo cáo đã kết thúc

Không thay đổi lặng lẽ evidence lịch sử sau khi phát hiện control không đạt. Khi sửa kỹ thuật vào tháng sau:

- Giữ lại trạng thái và finding của kỳ đã kết thúc.
- Tạo change record và evidence của remediation.
- Tiến hành retest vào kỳ mới.
- Ghi kết luận “đã khắc phục từ ngày Y” nếu có bằng chứng, không viết lại rằng kỳ cũ đạt.
- Nếu bằng chứng cũ được phát hiện sai, phát hành correction/addendum với lý do và approval.

Lịch sử trung thực là nền tảng của continuous assurance; chỉnh KPI quá khứ để trông đẹp làm mất khả năng đánh giá xu hướng và hiệu lực chương trình.

## 18. Lộ trình triển khai chương trình duy trì compliance

Không cần tự động hóa mọi control ngay từ đầu. Có thể triển khai theo các mức trưởng thành, phù hợp nguồn lực và rủi ro.

### 18.1. Giai đoạn 1 — Nhận diện và sở hữu

- Xác định những nghĩa vụ và cam kết thực sự áp dụng.
- Lập register có owner, source, version, applicability và review trigger.
- Tạo asset/service/data/vendor inventory tối thiểu.
- Chỉ ra những controls trọng yếu và người phụ trách.
- Rà soát các finding, exception hiện có.
- Chọn một số service có rủi ro cao để thiết lập baseline kiểm chứng.

**Kết quả cần chứng minh:** nghĩa vụ trọng yếu có phạm vi và owner; không có control critical “không ai chịu trách nhiệm”.

### 18.2. Giai đoạn 2 — Chuẩn hóa controls và evidence

- Viết control objective/assertion, PASS/FAIL criteria, frequency và test methods.
- Xây evidence contract và nơi lưu có phân quyền.
- Chuẩn hóa finding register, CAPA, risk acceptance và retest.
- Đối soát population trước mỗi đợt đánh giá.
- Tạo mẫu báo cáo có scope, kỳ, sources và limitations.
- Kiểm tra hoạt động của ít nhất một quy trình end-to-end từ finding đến verified closure.

**Kết quả cần chứng minh:** từ obligation bất kỳ có thể lần tới control, evidence, owner và trạng thái đánh giá.

### 18.3. Giai đoạn 3 — Tự động hóa theo rủi ro

- Dùng API read-only để thu effective IAM, storage, cloud, scan và log evidence.
- Policy-as-code kiểm tra IaC trước deploy, nhưng vẫn kiểm runtime.
- Tạo alert về population gap, stale evidence, expired exception và missing control run.
- Tích hợp change events với scope/applicability review.
- Tự động gắn ticket và xuất báo cáo, giữ reviewer khi cần judgment.
- Kiểm thử **collector health**, false positive, false negative và dữ liệu thiếu.

**Kết quả cần chứng minh:** thay đổi control hoặc tạo tài sản ngoài baseline được nhận biết trong cửa sổ đã định và tạo hành động phù hợp.

### 18.4. Giai đoạn 4 — Liên tục cải tiến và kiểm chứng độc lập

- Đánh giá xu hướng drift và recurring findings.
- Phân tích incident/hunting/pentest để phát hiện control thiếu.
- Chạy regression test sau sửa và khi kiến trúc đổi.
- Kiểm thử quy trình compliance khi đội owner vắng mặt.
- Định kỳ kiểm chứng độc lập các critical controls, không chỉ tin dashboard nội bộ.
- Rà soát lại mẫu số, risk tier và khả năng đáp ứng nghĩa vụ mới.
- Điều chỉnh công cụ và workflow theo evidence từ các kỳ audit.

**Kết quả cần chứng minh:** không chỉ “nhiều control PASS hơn”, mà các finding critical giảm bền vững, thời gian phát hiện/sửa và chất lượng evidence cải thiện.

### 18.5. Cadence vận hành tham khảo

| Mốc | Hoạt động | Chủ thể |
|---|---|---|
| Khi tạo/thay service | Applicability và control impact assessment | Service owner + compliance + security |
| Mỗi thay đổi kỹ thuật quan trọng | Policy checks, runtime validation, evidence update | Engineering/control owner |
| Theo chu kỳ monitoring của control | Detect drift, nguồn im lặng, mất scope, lỗi collector | Control owner/SOC/GRC |
| Hằng tháng hoặc theo risk tier | Review open findings, evidence freshness, exceptions | Assurance + risk/control owners |
| Hằng quý hoặc theo requirement | Access review, governance review và các control định kỳ | Control owner và người phê duyệt |
| Theo lịch kiểm toán | Audit readiness, independent sample và evidence pack | Audit/assurance |
| Sau incident hoặc material change | Phân tích control failure, cập nhật requirement và tests | IR + security + business/legal |
| Khi gia hạn/offboard vendor | Reassessment, data/credential cleanup và contractual checks | Third-party owner + privacy/security |

Tần suất này là **ví dụ**, không phải yêu cầu bắt buộc của mọi luật/framework. Lịch thật cần xuất phát từ nguồn nghĩa vụ, mức rủi ro và mô hình vận hành.

## 19. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Đã qua audit nên cả năm chắc chắn compliant.” | Audit có kỳ và scope; trạng thái thay đổi cần monitoring và evidence mới. |
| “Compliance tương đương security.” | Compliance là đáp ứng nghĩa vụ; security assurance còn đánh giá rủi ro và hiệu lực kiểm soát. |
| “Có chứng nhận ISO/IEC 27001 nghĩa là mọi app an toàn.” | Chứng nhận liên quan ISMS và scope; không chứng minh không có lỗ hổng. |
| “SOC 2 report của vendor chứng minh tất cả dịch vụ đều đạt.” | Cần đọc scope, kỳ, exceptions, customer responsibilities. |
| “Dashboard 100% xanh nghĩa toàn bộ asset đạt.” | Phải kiểm required inventory, sources bị bỏ sót và stale evidence. |
| “Có policy là control operating effective.” | Policy là design; cần implementation và dấu vết thực thi theo kỳ. |
| “Evidence càng nhiều càng chắc chắn.” | Evidence có thể sai scope, sai kỳ hoặc trùng lặp và không liên quan assertion. |
| “Một screenshot cuối tháng chứng minh control đạt cả tháng.” | Chỉ chứng minh snapshot nếu không có dữ liệu lịch sử. |
| “Pipeline test PASS nên production chắc chắn compliant.” | Runtime drift, asset ngoài IaC và cấu hình manual vẫn có thể sai. |
| “NOT_TESTED tương đương PASS nếu hệ thống chưa có incident.” | Chưa kiểm chứng không phải bằng chứng đạt. |
| “Risk accepted nghĩa là nghĩa vụ pháp lý được miễn trừ.” | Chấp nhận rủi ro nội bộ không tự thay đổi nghĩa vụ áp dụng. |
| “Ticket Done đồng nghĩa control đã sửa.” | Cần retest đúng assertion và đủ population. |
| “Control central PASS nghĩa mọi service đều PASS.” | Phải xác minh service thực sự được onboard và không có bypass. |
| “Mọi control cần kiểm realtime.” | Một số phải kiểm theo kỳ, event trigger hoặc human approval. |
| “Compliance chỉ là trách nhiệm GRC.” | Legal, owner nghiệp vụ, platform và assurance có trách nhiệm khác nhau. |
| “Không có log lỗi nghĩa hệ thống hoạt động đúng.” | Có thể collector im lặng hoặc thiếu data quality; cần health/coverage checks. |
| “Một framework mapping đáp ứng mọi hợp đồng.” | Mỗi obligation cần applicability và control/evidence cụ thể. |
| “Sửa lỗi ở kỳ này có thể biến kỳ trước thành PASS.” | Giữ lịch sử và ghi remediation có hiệu lực từ lúc được xác minh. |

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Tại ngày audit, mọi admin production có MFA. Điều này có chứng minh toàn bộ quý trước luôn đạt yêu cầu không?

**Gợi ý:** Không. Cần evidence theo kỳ, các lần tạo/sửa tài khoản, exception và hiệu lực thực tế; snapshot chỉ thể hiện thời điểm được kiểm.

**Câu 2.** Dashboard cho thấy 100% compliance vì 47/47 cloud account đã onboard đều đạt. Service catalog có 50 account bắt buộc. Bạn nên báo cáo thế nào?

**Gợi ý:** 47/50 = 94% verified coverage nếu đủ assertion, ba account chưa đánh giá; phải kiểm tra population gap và không tự đánh PASS toàn phạm vi.

**Câu 3.** Security policy yêu cầu access review theo quý. Nhóm quản lý quyền sửa lại policy hôm nay và gửi screenshot role list. Có đủ để đóng finding thiếu review quý trước không?

**Gợi ý:** Không. Cần xác minh criterion, hồ sơ review trong kỳ hoặc nêu evidence deficiency/nonconformity; thay procedure hôm nay chưa tạo lịch sử review đã không thực hiện.

**Câu 4.** Tổ chức đã chấp nhận rủi ro cho hệ thống cũ thiếu một control. Có thể ghi “compliance PASS” không?

**Gợi ý:** Chỉ nếu criterion thực sự cho phép ngoại lệ và điều kiện được đáp ứng; risk acceptance không tự làm mọi nghĩa vụ trở nên đạt. Ghi kỹ control verdict, exception và thẩm quyền.

**Câu 5.** Một luật/điều khoản hợp đồng mới được công bố, nhưng chưa đến ngày hiệu lực. Đội engineering có cần hành động ngay không?

**Gợi ý:** Cần đánh giá applicability, effective date, khoảng chuyển tiếp, gap và lộ trình; không mặc định có vi phạm ngay khi công bố hoặc không cần chuẩn bị trước khi có hiệu lực.

**Câu 6.** CI/CD báo IaC encryption policy PASS, nhưng runtime có storage bucket tạo thủ công ngoài pipeline. Kết luận gì?

**Gợi ý:** IaC test chỉ hỗ trợ đường deploy đã kiểm; phải đối soát inventory/runtime và thiết lập drift detection hoặc provisioning gate.

**Câu 7.** Nhà cung cấp SaaS có báo cáo độc lập tốt, nhưng customer phải bật audit export mà chưa bật. Trách nhiệm đánh giá thuộc về ai?

**Gợi ý:** Đối chiếu shared responsibility, nghĩa vụ hợp đồng và cấu hình tenant; customer có thể là control owner của export, vendor chịu trách nhiệm cung cấp và bảo vệ chức năng trong scope.

**Câu 8.** Evidence collector không thể thu dữ liệu từ ba account, còn 47 account đều đạt. Nên đánh ba account là FAIL hay PASS?

**Gợi ý:** Chưa có căn cứ xác định thực trạng kỹ thuật, nên ghi INCONCLUSIVE/NOT_VERIFIED và điều tra nguyên nhân; nếu criterion yêu cầu chứng cứ theo kỳ, có thể có finding riêng về evidence availability.

**Câu 9.** Một ngoại lệ đã hết hạn nhưng control chưa được sửa. Có thể giữ nguyên trạng thái ACCEPTED_RISK vì phê duyệt cũ còn trong hệ thống không?

**Gợi ý:** Không. Phải review lại theo policy, escalation, cập nhật rủi ro và biện pháp bảo vệ; một phê duyệt hết hạn không tự tiếp tục hiệu lực.

**Câu 10.** Vì sao verified control coverage và questionnaire response completion phải là hai KPI riêng?

**Gợi ý:** Một câu đã trả lời không chứng minh control hoạt động; verdict cần evidence và test đúng scope. Hai tỷ lệ dùng mẫu số và định nghĩa khác nhau.

## 21. Bài thực hành: lập kế hoạch duy trì compliance cho một nền tảng SaaS

Giả sử một công ty cung cấp API phục vụ thanh toán và dashboard cho khách hàng. Hệ thống chạy trên nhiều cloud account, có cluster container, managed database, identity provider, CI/CD, SIEM và một SaaS bên thứ ba để xử lý ticket hỗ trợ. Nhóm compliance đã hoàn thành audit quý trước, nhưng hiện xảy ra các thay đổi:

- Có bốn cloud account production mới được tạo, chưa chắc đã bật logging đúng baseline.
- Một nhóm service account mới có quyền đọc dữ liệu nhạy cảm nhưng chưa được access review.
- Công ty thay nhà cung cấp backup và chưa có restore test cho vùng DR.
- SaaS hỗ trợ khách hàng bổ sung subprocessor phân tích dữ liệu.
- Hợp đồng khách hàng mới yêu cầu evidence về security events và phản hồi incident trong kỳ đã thống nhất.
- Dashboard GRC vẫn có 100% câu hỏi đã trả lời từ quý trước.
- Ba finding kỹ thuật đã được đánh “Done” trong ticket nhưng chưa có kết quả retest.
- Một ngoại lệ legacy MFA sẽ hết hạn trong hai tuần.

**Yêu cầu thực hành:**

1. Lập **obligation register** ít nhất sáu mục, ghi source type, applicability, effective date, owner và scope; không tự viết điều luật cụ thể chưa được cung cấp.
2. Tạo **asset/service/data inventory** và xác định những thay đổi làm mẫu số cũ không còn đúng.
3. Ánh xạ mỗi nghĩa vụ vào một hoặc nhiều control IDs với assertion có thể kiểm chứng.
4. Xây **evidence contract** cho ít nhất bốn control: admin MFA, audit logging, access review, backup/DR.
5. Xác định phép test dương/âm, mẫu số population và kỳ vận hành cần chứng minh.
6. Đề xuất **change trigger** cho contract amendment, new account, new service identity, subprocessor và DR architecture.
7. Phân loại trạng thái hiện tại PASS/FAIL/INCONCLUSIVE/NOT_TESTED/ACCEPTED_RISK dựa trên bằng chứng giả định; không coi ticket Done là PASS.
8. Tạo finding register cho các gap, có owner, severity rationale, due date, compensation, retest.
9. Lập kế hoạch xử lý ngoại lệ MFA trước ngày hết hạn và điều kiện escalation.
10. Tính verified control coverage với mẫu số rõ ràng, phân biệt các nhóm chưa kiểm chứng.
11. Viết executive summary gửi management: nghĩa vụ thay đổi, critical blockers, residual risks và quyết định cần phê duyệt.
12. Thiết kế kiểm tra liên tục để sau này cloud account mới không lọt khỏi danh mục logging.

**Tiêu chí đánh giá:**

| Tiêu chí | Đạt khi |
|---|---|
| Applicability | Có căn cứ về nghĩa vụ, scope và mốc hiệu lực |
| Traceability | Obligation → control → test → evidence → finding → retest |
| Population | Required assets độc lập với danh sách đang được tool theo dõi |
| Evidence quality | Tách policy, configuration snapshot và operating effectiveness |
| Accuracy | Không đổi UNKNOWN/NOT_TESTED thành PASS; không suy diễn vi phạm pháp lý |
| Risk management | Critical gates, owner, exception và thẩm quyền rõ |
| Monitoring | Có trigger cho config drift lẫn legal/contractual changes |
| Remediation | Có corrective/preventive action, deadline và bằng chứng retest |
| Reporting | KPI có mẫu số, kỳ, giới hạn và phân tổ mức rủi ro |

## 22. Checklist duy trì compliance trong vận hành

- [ ] Có inventory nghĩa vụ và source reference được quản lý theo phiên bản.
- [ ] Mỗi nghĩa vụ có applicability decision, phạm vi, owner và lịch review.
- [ ] Legal/contractual change có kênh chuyển thông tin tới control owner.
- [ ] Có danh mục tài sản, dữ liệu, danh tính, dịch vụ và nhà cung cấp đủ làm mẫu số.
- [ ] Mỗi control có objective, assertion, expected condition, owner và kỳ kiểm.
- [ ] Có mapping truy vết từ nghĩa vụ sang một hoặc nhiều security controls.
- [ ] Policy-as-code kiểm trước deploy và runtime validation kiểm sau deploy.
- [ ] Data quality của collector và population coverage được đo; công cụ assurance không im lặng mà không có alert.
- [ ] Evidence có source, kỳ, scope, timestamp, method, version và giới hạn.
- [ ] Evidence quan trọng được bảo vệ, phân quyền, lưu theo kỳ retention hợp lệ và có audit trail.
- [ ] Control manual/periodic có record thực hiện đúng kỳ, không chỉ policy.
- [ ] Có kiểm soát cho thay đổi IAM, data flow, region, vendor và subprocessors.
- [ ] Audit readiness review định kỳ phân biệt scope, control effectiveness và evidence gaps.
- [ ] Finding có criterion, condition, evidence, risk, owner, due date và plan.
- [ ] Triển khai correction không tự động được coi là verified closure.
- [ ] Retest kiểm assertion, population, điều kiện vận hành và nguyên nhân tái diễn.
- [ ] Exception/risk acceptance có approver, scope, compensating control, expiry.
- [ ] Những nghĩa vụ không cho phép ngoại lệ được xử lý theo yêu cầu áp dụng.
- [ ] KPI có mẫu số đáng tin, period, PASS/FAIL/INCONCLUSIVE/NOT_TESTED tách biệt.
- [ ] Có cảnh báo về overdue critical findings, stale evidence và ngoại lệ hết hạn.
- [ ] Chứng nhận/report bên thứ ba được đọc đúng phạm vi, kỳ và customer responsibilities.
- [ ] Sau incident, major change hoặc audit finding, control mapping và test được đánh giá lại.
- [ ] Lịch sử kỳ trước không bị ghi đè khi có remediation mới.
- [ ] Có owner dự phòng và runbook khi nhân sự/hệ thống assurance không sẵn sàng.

## Kết luận

**Duy trì compliance là giữ một chuỗi bảo đảm có thể kiểm chứng từ nghĩa vụ áp dụng đến kiểm soát thực tế, bằng chứng theo thời gian và quyết định xử lý sai lệch.** Đó không chỉ là duy trì hồ sơ audit, mà còn là xác định đúng scope, kiểm tra controls trong vận hành, nhận biết thay đổi pháp lý/hợp đồng/hệ thống, khắc phục điểm thiếu và chứng minh hiệu lực sau sửa.

Trong chương **Compliance assurance** của **SECURITY_SECURITY_ASSURANCE**, thực hành cốt lõi là **obligation → applicability → control assertion → implementation → evidence → assurance verdict → finding/risk decision → remediation → retest → continuous monitoring**. Khi tổ chức duy trì được vòng lặp này với trách nhiệm rõ ràng, dữ liệu có nguồn tin cậy, KPI có mẫu số và lịch sử trung thực, compliance trở thành một năng lực vận hành liên tục thay vì một chiến dịch chạy nước rút trước kỳ kiểm toán.

