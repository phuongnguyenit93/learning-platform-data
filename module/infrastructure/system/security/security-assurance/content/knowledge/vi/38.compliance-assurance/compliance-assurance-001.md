# Compliance obligation: Xác định và chứng minh việc đáp ứng nghĩa vụ tuân thủ

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Giải thích **compliance obligation** và phân biệt yêu cầu có tính bắt buộc với tiêu chuẩn, hướng dẫn, cam kết hợp đồng, quy tắc nội bộ và mục tiêu security assurance.
2. Xác định điều kiện áp dụng của một nghĩa vụ theo **chủ thể, hoạt động, tài sản/dữ liệu, địa điểm, thời gian, vai trò và nguồn quy định**.
3. Xây dựng **obligation register** có mã định danh, nguồn, phiên bản, owner, deadline, tiêu chí thực hiện, controls, bằng chứng và cơ chế theo dõi thay đổi.
4. Chuyển nghĩa vụ được diễn giải thành các **yêu cầu có thể kiểm chứng**, liên kết tới rủi ro, security controls và phép thử phù hợp.
5. Đánh giá bằng chứng về **tính thích hợp, đầy đủ, cập nhật, nguồn gốc và độ tin cậy**, phân biệt trạng thái tuân thủ với tình trạng chưa đủ thông tin.
6. Quản lý khoảng trống, nghĩa vụ chồng lấn, ngoại lệ, sự cố, third-party dependencies và việc thay đổi phạm vi hoạt động.
7. Xây dựng chương trình **continuous compliance assurance** có kiểm tra định kỳ, monitoring, findings, hành động khắc phục và tái xác minh.

> **Phạm vi của bài:** Đây là nội dung đào tạo về quy trình và kỹ thuật security assurance. Các ví dụ về thời hạn và yêu cầu đều là **giả định minh họa** nếu không nêu rõ nguồn; không phải kết luận về luật cụ thể tại một quốc gia. Nghĩa vụ pháp lý thực tế cần được đội pháp chế/compliance có thẩm quyền xác định và kiểm tra theo phiên bản có hiệu lực.

## 1. Compliance obligation là gì?

**Compliance obligation** là một yêu cầu hoặc cam kết mà tổ chức phải thực hiện, hoặc đã chính thức chọn thực hiện, xuất phát từ một nguồn xác định. Nguồn có thể là **pháp luật, quy định, giấy phép, hợp đồng, chuẩn mực được chấp nhận, chính sách được phê duyệt hoặc cam kết với các bên liên quan**.

Điểm quan trọng là một nghĩa vụ có thể phát sinh theo nhiều cơ chế khác nhau:

- **Bắt buộc từ bên ngoài:** ví dụ một yêu cầu pháp lý hoặc điều kiện giấy phép áp dụng cho pháp nhân và hoạt động cụ thể.
- **Ràng buộc qua hợp đồng:** ví dụ một thỏa thuận xử lý dữ liệu, thỏa thuận cung cấp dịch vụ hoặc cam kết báo cáo sự cố.
- **Cam kết tự nguyện nhưng được phê duyệt:** ví dụ tổ chức chọn áp dụng một baseline, bộ chính sách hoặc chương trình chứng nhận.
- **Nghĩa vụ nội bộ:** ví dụ policy yêu cầu kiểm tra quyền định kỳ hoặc xác nhận khôi phục backup theo tần suất đã được phê duyệt.

Không phải mọi khuyến nghị thực hành tốt đều là một nghĩa vụ pháp lý. **Compliance obligation phải luôn gắn với nguồn, điều kiện áp dụng và vai trò chịu trách nhiệm**. Một danh sách checkbox tổng quát không thể thay thế việc xác định nguồn ràng buộc.

### 1.1. Các khái niệm cần phân biệt

| Khái niệm | Câu hỏi chính | Ví dụ minh họa |
|---|---|---|
| **Compliance obligation** | Tổ chức được yêu cầu hoặc cam kết phải làm gì? | Theo hợp đồng, dữ liệu khách hàng phải bị xóa theo quy trình đã thỏa thuận khi chấm dứt dịch vụ. |
| **Applicability** | Nghĩa vụ có áp dụng cho ai, dữ liệu nào, khi nào và ở đâu? | Chỉ áp dụng cho dịch vụ xử lý hồ sơ của khách hàng thuộc hợp đồng A. |
| **Compliance requirement** | Điều kiện cụ thể nào phải được thực hiện để đáp ứng nghĩa vụ? | Có quy trình nhận yêu cầu, kiểm tra trạng thái backup, ghi xác nhận xử lý. |
| **Security control** | Cơ chế/phương pháp giảm rủi ro và thực hiện yêu cầu? | Retention policy, IAM, logging, workflow phê duyệt, deletion job. |
| **Audit criterion** | Dựa trên thước đo nào để đánh giá mức đáp ứng? | Yêu cầu loại dữ liệu, thời hạn, vai trò duyệt và bằng chứng có hiệu lực theo nguồn đã chọn. |
| **Evidence** | Dữ liệu nào cho thấy control đã thực thi đúng? | Policy version, deletion log, test result, approval, audit trail. |
| **Compliance status** | Nghĩa vụ trong phạm vi đánh giá đang ở trạng thái nào? | Conform, nonconform, inconclusive, not applicable. |
| **Residual risk** | Còn nguy cơ nào sau controls và quyết định quản trị? | Một nhà cung cấp phụ trợ chưa thể chứng minh quy trình xóa trong backup. |

Một control có thể đáp ứng nhiều nghĩa vụ. Ngược lại, một nghĩa vụ có thể cần **nhiều controls, nhiều hệ thống và nhiều loại bằng chứng**.

### 1.2. Compliance assurance không đồng nghĩa “có giấy chứng nhận”

Chứng nhận hoặc báo cáo đánh giá độc lập hữu ích nhưng có **phạm vi, thời kỳ, đối tượng và tiêu chí** cụ thể. Không thể suy luận rằng tất cả luật áp dụng, mọi sản phẩm, mọi luồng dữ liệu và mọi thời điểm đều đã được kiểm chứng chỉ vì tổ chức có một chứng nhận hoặc một báo cáo audit.

Trong mô-đun **SECURITY_SECURITY_ASSURANCE**, compliance assurance đặt câu hỏi cụ thể hơn:

> Nghĩa vụ nào thực sự áp dụng, tại sao áp dụng, control nào đáp ứng, bằng chứng nào chứng minh và còn khoảng trống nào phải khắc phục?

Câu trả lời cần kết nối từ **risk assessment → obligations → requirements → controls → tests → audit → remediation → revalidation**.

## 2. Các nguồn nghĩa vụ và cách xác định thẩm quyền

### 2.1. Phân loại nguồn

| Nguồn | Tình huống điển hình | Điểm cần xác minh |
|---|---|---|
| **Luật/quy định** | Yêu cầu bảo vệ dữ liệu hoặc lưu hồ sơ theo lĩnh vực. | Pháp nhân, ngành, khu vực pháp lý, hoạt động, ngày hiệu lực, văn bản sửa đổi. |
| **Giấy phép/điều kiện hoạt động** | Điều kiện an toàn hoặc báo cáo để duy trì quyền cung cấp dịch vụ. | Cơ quan ban hành, phạm vi giấy phép, đối tượng chịu điều kiện. |
| **Hợp đồng/DPA/SLA** | Bảo vệ dữ liệu, thời hạn thông báo, hỗ trợ audit, xóa dữ liệu và khôi phục dịch vụ. | Các bên, sản phẩm, điều khoản, phụ lục, kỳ hiệu lực và ngoại lệ. |
| **Tiêu chuẩn/chứng nhận tự chọn** | ISO/IEC 27001 hoặc một baseline được tổ chức áp dụng. | Phiên bản, scope, mục tiêu, yêu cầu nào được đưa vào cam kết. |
| **Chương trình khách hàng/đối tác** | Bộ yêu cầu kỹ thuật hoặc bảo mật khi tham gia chuỗi cung ứng. | Cam kết nào thực sự ràng buộc, cách đối chiếu và bằng chứng được chấp nhận. |
| **Policy nội bộ** | MFA, data classification, access review, backup, logging, encryption. | Owner, văn bản đã phê duyệt, bản hiệu lực và điều kiện ngoại lệ. |
| **Risk-treatment decision** | Control bổ sung được phê duyệt để giảm một rủi ro ưu tiên. | Ai quyết định, asset/risk liên quan và điều kiện nghiệm thu. |
| **Cam kết công bố/thoả thuận với bên liên quan** | Tuyên bố về xử lý dữ liệu hoặc mức bảo vệ dịch vụ. | Nội dung công bố, tính ràng buộc thực tế và người có quyền diễn giải. |

**ISO/IEC 27001** là một ví dụ của tiêu chuẩn quản lý, không phải một “luật chung” mặc định áp dụng cho tất cả doanh nghiệp. **SOC 2** là cơ chế báo cáo assurance theo phạm vi tiêu chí và kỳ đánh giá, không phải một quy định pháp luật áp đặt cho mọi tổ chức. Cần phân loại đúng nguồn để tránh biến tài liệu tham chiếu thành nghĩa vụ không có căn cứ.

### 2.2. Hệ phân cấp và xung đột nghĩa vụ

Giả sử một policy nội bộ yêu cầu giữ một loại log 90 ngày, hợp đồng quy định giữ 180 ngày, còn một nghĩa vụ khác yêu cầu xóa dữ liệu cá nhân khi kết thúc mục đích, trừ trường hợp được giữ hợp lệ.

Không nên tự chọn **con số dài nhất hoặc ngắn nhất** mà chưa xác định:

1. Hai yêu cầu có đang áp dụng cho **cùng một tập dữ liệu** không?
2. Loại dữ liệu nào chứa thông tin cá nhân hoặc thông tin đặc biệt nhạy cảm?
3. Văn bản nào ràng buộc pháp nhân, hoạt động và dịch vụ?
4. Có điều kiện lưu giữ ngoại lệ, yêu cầu bảo toàn chứng cứ hoặc nghĩa vụ không được tiết lộ không?
5. Cơ chế xóa/ẩn danh, khóa retention và bản sao backup ảnh hưởng thế nào?
6. Ai có thẩm quyền diễn giải và quyết định khi các nguồn có vẻ mâu thuẫn?

**Không để kỹ sư hoặc auditor tự giải quyết một xung đột pháp lý bằng phép suy luận kỹ thuật đơn thuần.** Đội legal/compliance xác định nghĩa vụ áp dụng; security/platform/data owner chuyển nghĩa vụ đã thống nhất thành controls có thể vận hành và kiểm chứng.

### 2.3. Phân biệt nguồn gốc và mức độ ràng buộc

Một tiêu chí nên lưu hai thông tin riêng:

- **Source type / authority:** luật, hợp đồng, cam kết tự chọn, policy nội bộ.
- **Applicability rationale:** vì sao nó áp dụng với pháp nhân/dịch vụ/dữ liệu và kỳ đang xét.

Không suy luận “một tiêu chuẩn rất phổ biến” đồng nghĩa “bắt buộc đối với chúng ta”. Ngược lại, một yêu cầu chỉ xuất hiện trong phụ lục hợp đồng với một khách hàng vẫn có thể ràng buộc nghiêm ngặt với dịch vụ cụ thể.

## 3. Applicability assessment: nghĩa vụ có thực sự áp dụng không?

Đánh giá **applicability** phải đi trước việc viết test hoặc kết luận vi phạm. Với nghĩa vụ bên ngoài, một sai lầm về phạm vi có thể gây hai hậu quả: bỏ sót nghĩa vụ đang áp dụng, hoặc áp một yêu cầu không liên quan rồi tạo finding sai.

### 3.1. Sáu chiều áp dụng

| Chiều | Câu hỏi cần trả lời |
|---|---|
| **Legal entity / role** | Pháp nhân nào và dưới vai trò nào? Ví dụ đơn vị quyết định mục đích xử lý, đơn vị xử lý thay, bên cung cấp dịch vụ hay nhà thầu phụ? |
| **Jurisdiction / geography** | Hoạt động, dữ liệu, người dùng, trụ sở hoặc nơi xử lý có yếu tố khu vực nào làm phát sinh nghĩa vụ? |
| **Activity / business process** | Dịch vụ nào đang thu thập, lưu, truyền, xử lý, chia sẻ, xóa dữ liệu hoặc vận hành hạ tầng? |
| **Data / asset class** | Thông tin cá nhân, giao dịch, bí mật, log, dữ liệu tài chính, khóa, artifact phần mềm hay tài sản khác? |
| **Time / lifecycle** | Ngày hiệu lực, kỳ đánh giá, khi ký hợp đồng, khi phát hiện sự cố, khi nhận yêu cầu hay khi kết thúc hợp đồng? |
| **Conditions / exemptions** | Ngưỡng, loại trừ, đặc thù xử lý, vai trò nhà thầu phụ hoặc điều kiện kích hoạt nào đã được xác định? |

**Ví dụ:** tổ chức vận hành một ứng dụng ở nhiều quốc gia, dùng cloud region A để xử lý dữ liệu của khách hàng thuộc hợp đồng B. Không thể quyết định quy định áp dụng chỉ từ **vị trí máy chủ**. Phải xem pháp nhân, khách hàng, hoạt động xử lý, vai trò các bên, điều khoản và những điều kiện xác định trong nguồn luật/hợp đồng.

### 3.2. Ma trận applicability

| Obligation ID | Đối tượng đánh giá | Điều kiện áp dụng | Kết luận minh họa | Evidence |
|---|---|---|---|---|
| OBL-CON-001 | Dịch vụ Order API cho khách hàng X | Phụ lục bảo vệ dữ liệu của hợp đồng X có hiệu lực. | Applicable cho dữ liệu trong hợp đồng X. | Contract version, asset/data-flow map. |
| OBL-POL-002 | Human admin trong production | Có quyền đặc quyền tương tác theo policy IAM. | Applicable với account thuộc IAM inventory. | Policy, effective-access report. |
| OBL-REG-003 | Một nghiệp vụ chịu quản lý chuyên ngành | Có thỏa các điều kiện từ văn bản áp dụng và vai trò đã được xác định? | Pending legal review. | Applicability memo, legal signoff cần bổ sung. |
| OBL-STD-004 | Phạm vi ISMS được chứng nhận | Có nằm trong SoA và scope của hệ thống quản lý đã chọn? | Applicable theo scope ISMS được duyệt. | Scope statement, SoA, control mapping. |

Các ID và điều kiện là minh họa. Trạng thái **pending legal review** không được tự biến thành Not applicable hoặc Compliant. Khi không rõ căn cứ, ghi **uncertainty, owner và ngày cần quyết định**.

### 3.3. Quy tắc đánh giá trạng thái áp dụng

- **Applicable:** có căn cứ đủ rõ rằng nghĩa vụ áp dụng cho population và thời gian cụ thể.
- **Not applicable:** có bằng chứng và thẩm quyền xác nhận điều kiện áp dụng không thỏa.
- **Conditional:** phụ thuộc một trigger chưa xảy ra hoặc một ngưỡng được xác định.
- **Under review / unknown:** chưa đủ thông tin hoặc còn tranh luận về diễn giải.

Không nên mặc định **Not applicable** chỉ vì sản phẩm chưa có log hoặc không có người biết nghĩa vụ đó. Đây có thể là **evidence gap hoặc governance gap**.

## 4. Obligation register: sổ đăng ký nghĩa vụ

Một **obligation register** là nguồn quản trị có kiểm soát, cho biết tổ chức phải làm gì, vì sao, ai chịu trách nhiệm và chứng minh bằng cách nào.

### 4.1. Các trường nên có

| Nhóm | Trường quan trọng | Mục đích |
|---|---|---|
| **Định danh** | Obligation ID, title, category, status. | Truy vết qua hệ thống và kỳ đánh giá. |
| **Nguồn** | Source type, document/reference, clause, version, publisher, hiệu lực. | Không mất căn cứ hoặc áp sai bản. |
| **Applicability** | Legal entity, business process, role, data class, location, population, điều kiện. | Xác định rõ ai/cái gì phải đáp ứng. |
| **Diễn giải** | Legal/compliance interpretation, giả định, quyết định, ngày review. | Tránh kỹ thuật tự đặt thêm nghĩa vụ. |
| **Requirement** | Hành động, trạng thái hoặc kết quả phải đạt; deadline/trigger. | Làm cho nghĩa vụ đo được. |
| **Mapping** | Risk ID, control IDs, asset IDs, owner, evidence IDs. | Traceability và phân định trách nhiệm. |
| **Assessment** | Test procedure, kỳ, sampling, acceptance, verdict, evidence quality. | Đánh giá có thể tái hiện. |
| **Lifecycle** | Change trigger, next review, exceptions, findings, approval, retest. | Duy trì assurance liên tục. |

### 4.2. Mẫu YAML minh họa

~~~yaml
obligation_id: OBL-CON-001
title: "Xử lý yêu cầu xóa dữ liệu theo phụ lục hợp đồng"
source:
  type: contract
  reference: "DPA-CUSTOMER-X"
  clause: "Section 8 (illustrative)"
  version: "2.1"
  effective_from: "2026-10-01"
  source_owner: legal-team
applicability:
  status: applicable
  legal_entity: "Service-Provider-A"
  service: "order-platform"
  data_scope: "customer-X-data"
  role: "processor-per-contract"
  evidence_ref: "EV-CONTRACT-SCOPE-01"
requirement:
  trigger: "approved-deletion-request"
  timeframe: "within-contractual-deadline"
  exceptions: "retention-approved-by-legal"
  acceptance: "request handled and outcome traceable"
control_mapping:
  - CTRL-DATA-RETENTION-01
  - CTRL-REQUEST-WORKFLOW-02
  - CTRL-VENDOR-DELETION-03
assessment:
  methods: ["examine", "test"]
  evidence:
    - "request-ledger"
    - "deletion-job-audit"
    - "subprocessor-confirmation"
  decision_rule: "obligation-specific-criteria-v1"
accountability:
  business_owner: data-governance
  control_owner: platform-and-privacy-operations
  legal_reviewer: legal-team
lifecycle:
  next_review: "2027-01-15"
  current_verdict: not-assessed
~~~

Đây là **schema học tập**, không phải nội dung một điều khoản hợp đồng có thật. Những trường như **within-contractual-deadline** và **retention-approved-by-legal** phải được thay bằng điều kiện đã được thẩm quyền xác nhận trước khi dùng để kiểm toán.

### 4.3. Nguyên tắc quản lý phiên bản

- Không sửa nội dung nghĩa vụ cũ một cách âm thầm khi hợp đồng/quy định được cập nhật.
- Giữ lịch sử các bản source, interpretation, hiệu lực, owner và scope.
- Test result tham chiếu **obligation version và criterion version** đã dùng.
- Khi thay deadline, role hoặc phạm vi dữ liệu, ghi impact assessment.
- Có người phê duyệt cập nhật và ngày áp dụng; tránh retroactively đánh giá sai kỳ quá khứ.
- Không tự đóng finding từ bản cũ chỉ vì nghĩa vụ mới có tiêu chí nhẹ hơn.

## 5. Chuyển một nghĩa vụ thành yêu cầu có thể kiểm chứng

Một nghĩa vụ trong văn bản có thể rất dài hoặc chỉ nêu nguyên tắc; control kỹ thuật cần chia thành những phần **nguyên tử có thể kiểm tra**.

### 5.1. Chuỗi từ nguồn đến kết luận

~~~mermaid
flowchart TD
    A["Nguồn nghĩa vụ có hiệu lực"] --> B["Applicability + legal/compliance interpretation"]
    B --> C["Yêu cầu nguyên tử + deadline / trigger"]
    C --> D["Control objective + risk"]
    D --> E["Controls và owner"]
    E --> F["Test / audit criterion"]
    F --> G["Evidence + data quality"]
    G --> H{"Conformance?"}
    H -->|Đạt| I["Record assurance + monitor"]
    H -->|Không đạt| J["Finding + remediation / escalation"]
    H -->|Thiếu chứng cứ| K["Evidence gap + re-assessment"]
    J --> F
    K --> F
~~~

Mỗi bước có một mục đích khác nhau:

1. **Nguồn:** nội dung ràng buộc và điều kiện áp dụng.
2. **Diễn giải:** chủ thể, dữ liệu, vai trò, phạm vi, thời gian và ngoại lệ.
3. **Yêu cầu nguyên tử:** một hành động hoặc kết quả có thể quan sát.
4. **Control:** biện pháp giúp đáp ứng yêu cầu.
5. **Test:** cách xác minh theo tiêu chí đã được phê duyệt.
6. **Evidence:** dữ liệu thực tế, giới hạn và độ tin cậy.
7. **Decision:** kết luận, finding, chấp nhận rủi ro nếu thích hợp hoặc escalation.

### 5.2. Ví dụ phân rã nghĩa vụ xóa dữ liệu theo hợp đồng

Giả sử một **điều khoản hợp đồng giả định** yêu cầu bên xử lý xử lý yêu cầu xóa dữ liệu khách hàng theo deadline đã được thống nhất, ngoại trừ các trường hợp được phép giữ hợp lệ.

| Requirement ID | Yêu cầu nguyên tử | Control | Bằng chứng |
|---|---|---|---|
| REQ-DEL-01 | Yêu cầu được tiếp nhận, xác thực quyền và ghi thời điểm trigger. | Ticket/workflow có kiểm tra danh tính và authorization. | Request ledger, audit của phê duyệt. |
| REQ-DEL-02 | Xác định mọi hệ thống và bản sao chứa dữ liệu thuộc phạm vi. | Data inventory và data lineage. | Data map, asset inventory, vendor/subprocessor register. |
| REQ-DEL-03 | Thực hiện xóa/ẩn danh theo quyết định đã được phép. | Deletion jobs, privacy workflow, phân quyền. | Job execution, per-system deletion record. |
| REQ-DEL-04 | Quản lý các bản backup theo chính sách retention đã được xác nhận. | Backup retention controls và quy trình restore-safe deletion. | Backup policy, restore behavior test, legal decision. |
| REQ-DEL-05 | Xử lý nghĩa vụ với subprocessors. | Contract obligations, vendor workflow. | Subprocessor requests, confirmations. |
| REQ-DEL-06 | Gửi kết quả và đóng yêu cầu trong thời hạn hợp lệ. | SLA workflow và escalation. | Case timeline, notification record. |

Nếu chỉ có deletion job thành công ở database chính, không thể tuyên bố **toàn bộ yêu cầu xóa đã đạt** khi vẫn chưa đánh giá object storage, replica, backup, log hoặc các bên xử lý khác.

### 5.3. Ví dụ nghĩa vụ thông báo sự cố

Một nghĩa vụ hợp đồng có thể quy định phải thông báo cho đối tác khi một loại sự cố **đáp ứng điều kiện kích hoạt**. Cần tách:

- Khi nào một sự kiện trở thành sự cố trong phạm vi hợp đồng?
- Ai xác định mốc bắt đầu tính thời hạn: lúc phát hiện, xác nhận hay nhận thông tin từ vendor?
- Những thành phần dữ liệu/pháp nhân nào thuộc phạm vi thông báo?
- Ai được phép duyệt nội dung, gửi qua kênh nào và lưu bằng chứng đã gửi?
- Nếu chưa xác minh hết tác động, có cần cập nhật bổ sung theo quy trình đã thống nhất không?
- Điều kiện nào kích hoạt escalation, hold và điều phối pháp lý?

**Không tự gán một thời hạn pháp lý chung** khi văn bản nguồn hoặc jurisdiction chưa được xác định. Mốc 24 giờ hay 72 giờ xuất hiện trong ví dụ vận hành chỉ là một giá trị giả định trừ khi có nguồn có hiệu lực và đã được thẩm quyền xác minh.

## 6. RACI: ai chịu trách nhiệm về compliance obligation?

| Vai trò | Trách nhiệm điển hình |
|---|---|
| **Legal / regulatory affairs** | Xác định nghĩa vụ pháp lý, diễn giải nguồn áp dụng, cập nhật văn bản và xử lý mâu thuẫn. |
| **Compliance / GRC** | Quản lý register, lịch đánh giá, mapping, theo dõi trạng thái và reporting. |
| **Business owner** | Xác định hoạt động, mức tác động, mục tiêu và quyết định ưu tiên nguồn lực. |
| **Data protection / privacy role** | Quản lý dữ liệu cá nhân, yêu cầu chủ thể, retention, sharing và các đánh giá riêng tư nếu áp dụng. |
| **Security architecture / engineering** | Thiết kế controls bảo vệ, threat model và các yêu cầu kỹ thuật có thể test. |
| **Platform/application owner** | Triển khai, vận hành, giám sát và sửa lỗi controls trên hệ thống thực. |
| **Third-party/vendor management** | Quản lý yêu cầu đối với nhà cung cấp và subprocessors, điều khoản và bằng chứng. |
| **Incident response / SOC** | Phát hiện tình huống kích hoạt, preserve evidence, điều phối và thông báo theo runbook. |
| **Internal audit / independent reviewer** | Đánh giá bằng chứng khách quan, kiểm tra criteria, báo findings và giới hạn assurance. |
| **Risk owner / management** | Chấp thuận biện pháp xử lý rủi ro trong quyền hạn và tài trợ khắc phục; không tự miễn trừ nghĩa vụ pháp luật. |

Cần phân biệt **accountability của nghĩa vụ** với **ownership của control**. Một data owner có thể chịu trách nhiệm đáp ứng điều khoản với khách hàng dù các bước thực hiện thuộc platform, privacy operations và nhà cung cấp phụ trợ.

### 6.1. Mô hình phân công theo một nghĩa vụ

~~~text
OBL-CON-001  Hợp đồng yêu cầu xử lý deletion request
ACCOUNTABLE  Data Governance Owner
INTERPRETS   Legal + Privacy
IMPLEMENTS   Platform + Application + Vendor Management
VALIDATES    Security Assurance / Internal Audit
APPROVES     Authorized business/risk decision maker
TRIGGERS     Approved request event
RECORDS      Request ledger + jobs + vendor confirmations
ESCALATES    Deadline, failed job, scope gap, legal conflict
~~~

Đây là cách mô tả phân vai; thẩm quyền thực tế cần phù hợp cấu trúc doanh nghiệp và quy định. Người vận hành không nên có quyền **tự bỏ điều kiện hợp đồng** chỉ để làm dashboard hoàn thành.

## 7. Chứng minh compliance: design, implementation và operation

Chỉ đọc một chính sách không đủ để kết luận nghĩa vụ đã được đáp ứng. Phải phân biệt ba cấp kiểm chứng.

| Cấp | Câu hỏi | Bằng chứng |
|---|---|---|
| **Design effectiveness** | Quy trình và controls có được thiết kế để đáp ứng điều kiện nghĩa vụ? | Policy, workflow, architecture, RACI, risk assessment, legal interpretation. |
| **Implementation** | Controls thực sự tồn tại và áp dụng vào đúng population? | IAM/config exports, deployed resources, automation, data map, ticket workflow. |
| **Operating effectiveness** | Controls có hoạt động đúng trong kỳ, dưới điều kiện thực tế? | Execution logs, event history, approvals, negative tests, case timeline, incident records, retest. |

Ví dụ một chính sách quy định “mọi tài khoản đặc quyền được review mỗi quý” mới chứng minh **ý định thiết kế**. Để kiểm chứng vận hành, cần population tài khoản trong kỳ, lịch review, evidence owner đã review, trường hợp ngoại lệ và xử lý findings. Một ảnh chụp quyền cuối quý chưa chứng minh mọi thay đổi trong kỳ được kiểm soát.

### 7.1. Examine, interview, test

- **Examine:** kiểm tra văn bản, contracts, policies, architecture, inventory, audit events, approvals và evidence trail.
- **Interview:** hỏi owner, operator, legal/compliance và vendor để hiểu quy trình, thay đổi, hành vi thực tế; lời nói không thay thế bằng chứng kỹ thuật.
- **Test:** kiểm tra hành vi với dữ liệu, tài khoản hoặc môi trường được phép; xác minh deny, retention, alert, SLA workflow hoặc khả năng restore.

Cần tổ hợp phương pháp theo **rủi ro và điều kiện của nghĩa vụ**. Những phép thử có thể ảnh hưởng dữ liệu production phải được ủy quyền, có kế hoạch an toàn, cleanup và ghi log.

### 7.2. Điều gì khiến evidence đáng tin?

| Thuộc tính | Câu hỏi kiểm chứng | Lỗi thường gặp |
|---|---|---|
| **Relevance** | Evidence chứng minh điều kiện nào của nghĩa vụ? | Có penetration test nhưng nghĩa vụ là xóa dữ liệu đúng hạn. |
| **Scope** | Đúng pháp nhân, dịch vụ, account, tenant, region và loại dữ liệu? | Chỉ chứng minh một SaaS trong khi dữ liệu còn ở hệ thống nội bộ. |
| **Recency** | Evidence thuộc kỳ và phiên bản control/source đang đánh giá? | Báo cáo cũ trước khi hệ thống đổi nhà cung cấp. |
| **Completeness** | Population, sự kiện, số record và hệ thống có được bao phủ? | API export bỏ trang, cloud audit thiếu region. |
| **Reliability/provenance** | Biết nguồn, cách xuất, ai xử lý và có khả năng đối chiếu? | CSV sửa tay không link tới raw event. |
| **Independence** | Có nguồn hoặc reviewer độc lập hỗ trợ claim? | Chỉ lời tự khẳng định của control owner. |
| **Reproducibility** | Reviewer khác có thể thực hiện lại kiểm tra trong điều kiện tương đương? | Screenshot không có timestamp, query, policy version. |

Dữ liệu thiếu không chứng minh có vi phạm, nhưng **cũng không chứng minh đạt**. Cần có trạng thái riêng **inconclusive / insufficient evidence** và finding về chất lượng telemetry/recordkeeping nếu cần.

## 8. Obligation → control → test → evidence: ma trận truy vết

### 8.1. Ví dụ cross-domain

| Obligation/requirement giả định | Control tại hệ thống | Test/criterion | Evidence | Điểm mù cần nêu |
|---|---|---|---|---|
| **OBL-ACC:** tài khoản admin phải được phê duyệt và xác thực theo policy. | IAM, MFA, PAM, access review. | Kiểm tra effective access, approval trước quyền, negative authentication test. | IAM audit, IdP policy, approvals, test log. | Human/admin vs service identity, break-glass và group nesting. |
| **OBL-DATA:** dữ liệu nhóm X chỉ lưu trong phạm vi được phê duyệt. | Data classification, region policy, egress control. | Đối chiếu data flow với storage/processing inventory và vendor paths. | Config, inventory, DLP/egress, vendor attestations. | Serverless/cache/backup/subprocessors khó nhìn thấy. |
| **OBL-RET:** dữ liệu nhóm X tuân thủ retention/deletion rule đã phê duyệt. | Lifecycle policy, deletion workflow. | Test hết hạn, deletion case và restore/backup implications. | Job logs, object versions, case records. | Snapshot, immutable archives và legal hold. |
| **OBL-IR:** sự cố thuộc phạm vi được báo theo kênh/thời hạn thỏa thuận. | IR playbook, case workflow, contact/escalation. | Diễn tập điều kiện kích hoạt, timestamp và bằng chứng gửi/nhận. | Incident ledger, notification record, approval. | Trigger ambiguity, giờ ngoài hành chính, vendor delay. |
| **OBL-DR:** chức năng Critical đạt RTO/RPO theo cam kết. | Backup, replication, DR site, failover. | Recovery exercise và đối chiếu recovery point. | Backup/restore logs, transactions, timeline. | Site khác nhưng IAM/KMS chung, dữ liệu không nhất quán. |
| **OBL-TPR:** nhà cung cấp xử lý dữ liệu theo thỏa thuận. | Contract, least privilege, subprocessor review. | Scope assessment, token access denial, change notification review. | DPA, risk register, access test, assurance reports. | Controls nội bộ vendor không thể quan sát trực tiếp. |
| **OBL-LOG:** hoạt động nhạy cảm có audit trail. | Logging pipeline, retention, tamper alerts. | Source coverage, event generation, health/ingest test. | Raw events, ingestion metrics, rule test results. | Mất log, clock skew, source ngoài inventory. |

**Không suy ngược một control có hiệu lực thành tuân thủ mọi nghĩa vụ liên quan**. Ví dụ MFA bảo vệ đăng nhập nhưng không tự giải quyết retention, thông báo sự cố hoặc giới hạn mục đích xử lý dữ liệu.

### 8.2. Mô tả audit criterion cụ thể

Ví dụ giả định đối với một policy nội bộ đã được phê duyệt:

~~~text
CRITERION_ID: CMP-ACCESS-001
SOURCE: SEC-IAM-04 v3.2
APPLICABILITY:
  Production human privileged accounts
  according to authoritative IAM inventory
PERIOD:
  [2026-11-01T00:00:00Z, 2026-12-01T00:00:00Z)
REQUIREMENT:
  Every privileged interactive sign-in must satisfy
  approved MFA policy or an explicitly permitted
  alternate control with valid authorization.
METHODS:
  Examine identity policy and effective assignments
  Test authorized interactive sign-in/deny paths
  Review sign-in logs and documented exceptions
PASS:
  All assessed items satisfy applicable policy
FAIL:
  Evidence proves a valid item violates policy
INCONCLUSIVE:
  Coverage/source or effective assignments cannot
  be verified with sufficient reliable evidence
EVIDENCE:
  Policy snapshot, account population, sign-in logs,
  test IDs, exceptions, reviewer decision
~~~

**Không áp một yêu cầu MFA của human accounts cho mọi service account** nếu source policy không quy định như vậy. Service identities cần criteria về token, certificate, workload identity hoặc secret lifecycle theo nghĩa vụ thực tế.

## 9. Một nghĩa vụ có thể có nhiều trigger và thời hạn

Nhiều nghĩa vụ không chỉ yêu cầu trạng thái "bật/tắt" mà kích hoạt bởi một sự kiện:

- Khách hàng gửi yêu cầu truy cập hoặc xóa thông tin.
- Phát hiện/đánh giá một sự cố bảo mật đạt điều kiện thông báo.
- Nhà cung cấp thêm subprocessor hoặc chuyển nơi xử lý dữ liệu.
- Nhân sự nghỉ việc hoặc đổi vai trò cần thu hồi quyền.
- Hợp đồng hết hạn; phải export và xóa dữ liệu.
- Phiên bản chính sách thay đổi, đòi cập nhật baseline.
- Kỳ kiểm tra/quản trị có hạn, ví dụ access review định kỳ.

### 9.1. Đo đúng thời gian

Với nghĩa vụ có deadline, cần xác định:

| Mốc | Ví dụ | Ý nghĩa |
|---|---|---|
| **triggered_at** | Lúc yêu cầu hợp lệ được tiếp nhận hoặc incident đạt điều kiện kích hoạt. | Mốc gốc theo định nghĩa của nghĩa vụ. |
| **qualified_at** | Lúc xác minh phạm vi, danh tính hoặc điều kiện áp dụng. | Có thể khác triggered_at; không tự thay mốc nếu nguồn không cho phép. |
| **assigned_at** | Workflow giao cho owner. | Giúp đánh giá vận hành, không nhất thiết là mốc deadline. |
| **completed_at** | Control đã thực hiện đủ yêu cầu. | Cần xác định "đủ" là xong job, xác minh hay đã thông báo. |
| **verified_at** | Reviewer xác minh kết quả. | Hỗ trợ assurance và audit trail. |
| **notified_at** | Thời gian gửi thông tin hoặc xác nhận nhận. | Phải phân biệt send/receive nếu nguồn yêu cầu. |

Giả sử **hợp đồng minh họa** quy định xử lý một loại yêu cầu trong tối đa **10 ngày lịch** kể từ triggered_at. Một case bắt đầu ngày 01/11 và hoàn tất ngày 12/11, nếu không có điều kiện tạm dừng/gia hạn hợp lệ thì **không đạt** tiêu chí này. Đây **không** phải thời hạn của một luật cụ thể. Khi đo ngày/giờ, phải làm rõ timezone, ngày nghỉ, điểm bắt đầu, cách tính deadline và ngoại lệ theo nguồn.

### 9.2. Chặn sai lệch mốc thời gian

Không đổi triggered_at thành assigned_at chỉ để cải thiện compliance KPI. Một ticket tạo muộn có thể che sự kiện thực đã xảy ra trước đó. Nên giữ raw event timestamp, ingestion timestamp, workflow timestamp, timezone, đồng bộ đồng hồ và mọi thao tác chỉnh sửa.

## 10. Conflict management: retention, privacy và preservation

### 10.1. Một tình huống khó

Một hệ thống chứa nhật ký truy cập có PII. Có ba mục tiêu:

- Chỉ giữ dữ liệu trong thời gian và mục đích được phép.
- Bảo toàn chứng cứ khi có nghi vấn sự cố và yêu cầu hợp lệ.
- Đáp ứng yêu cầu cung cấp/xóa dữ liệu theo phạm vi áp dụng.

**Không thể áp dụng máy móc "xóa tất cả ngay" hoặc "giữ tất cả vô thời hạn".**

Quy trình xử lý:

1. Phân loại dữ liệu và mục đích; xác định thực thể và nghĩa vụ liên quan.
2. Nhờ legal/privacy xác nhận trường hợp cần giữ, giới hạn, cách phân vùng và điều kiện release.
3. Thiết kế controls thực thi: retention tags, legal hold, quyền truy cập, immutable storage khi phù hợp.
4. Giữ audit ai đặt/gỡ hold, lý do, thời gian và đối tượng.
5. Test dữ liệu hết hạn được xử lý đúng khi không có hold; dữ liệu có hold được bảo vệ; khi hold kết thúc, quy trình tiếp tục theo nghĩa vụ hiện hành.
6. Ghi lại phần dữ liệu không thể xử lý tức thời do công nghệ/backup và phương án được phê duyệt.

### 10.2. Backup và dữ liệu dẫn xuất

Một data deletion workflow phải xét không chỉ bảng production mà còn:

- Object storage, cache và search index.
- Replica, snapshots và backup archives.
- Log, trace và analytics datasets có chứa trường dữ liệu liên quan.
- Dữ liệu trên hệ thống vendor/subprocessor.
- ETL/export ở các môi trường tạm và test.
- Dữ liệu đã được tổng hợp/ẩn danh và có còn định danh được chủ thể hay không theo cách đánh giá áp dụng.

Một yêu cầu hợp đồng có thể cho phép cách xử lý khác giữa bản vận hành và backup không trực tiếp truy cập được; **không tự suy luận điều đó luôn hợp lệ**. Cần diễn giải theo nguồn, thiết kế thực thi và kiểm tra quy trình khôi phục để tránh vô tình đưa dữ liệu đã xóa trở lại.

## 11. Continuous compliance assurance

Compliance không nên chỉ là việc chuẩn bị tài liệu trước đợt audit. Hệ thống, dữ liệu, quyền và quy định liên tục thay đổi, vì vậy phải giám sát **điều kiện tuân thủ và chất lượng bằng chứng**.

### 11.1. Kiến trúc vận hành

~~~mermaid
flowchart LR
    SRC["Legal/contract/policy sources"] --> REG["Versioned obligation register"]
    REG --> MAP["Scope + controls + owners"]
    SYS["IAM, cloud, app, data, vendors"] --> COL["Telemetry + configuration + workflow evidence"]
    MAP --> RULE["Compliance criteria/tests"]
    COL --> RULE
    RULE --> RES["Verdict + evidence package"]
    RES --> FIND["Findings / exceptions"]
    FIND --> FIX["Remediation + retest"]
    FIX --> RULE
    SRC --> CHANGE["Change intake & impact analysis"]
    CHANGE --> REG
~~~

**Chú ý:** tự động hóa có thể đánh giá một số criteria định lượng, nhưng không tự thay legal interpretation, risk owner decision hoặc audit độc lập khi cần. Chương trình phải thể hiện rõ phần **machine-assessable**, phần **human review** và phần **unknown**.

### 11.2. Khi nào trigger tái đánh giá?

- Có văn bản hoặc hợp đồng mới/sửa đổi có hiệu lực hoặc thời gian chuyển tiếp.
- Dịch vụ mở thị trường mới, thay pháp nhân hoặc vai trò xử lý dữ liệu.
- Thêm data category, tính năng AI, vendor/subprocessor hoặc cloud region.
- IAM, encryption, logging, retention, DR hoặc security architecture thay đổi.
- Có incident, finding hoặc yêu cầu từ khách hàng/cơ quan có thẩm quyền.
- Kỳ review/chứng nhận đến hạn hoặc chứng cứ đã hết phù hợp.
- Control bị tắt, không còn telemetry, job lỗi hoặc kết quả kiểm thử regression fail.
- Hợp đồng chấm dứt hoặc dữ liệu chuyển sang đơn vị vận hành khác.

Mỗi trigger phải có **intake record, owner, impact assessment và quyết định cập nhật register/control/test**.

### 11.3. Những kiểm tra tự động có giá trị

| Nhóm | Kiểm tra ví dụ | Tín hiệu khi không đạt |
|---|---|---|
| **IAM** | Effective privileged identities so với access policy. | Quyền tăng trái approval, MFA policy không khớp, tài khoản hết hạn chưa revoke. |
| **Data location** | Resource region, processing destinations so với inventory đã phê duyệt. | Dữ liệu mới ở region ngoài phạm vi hoặc luồng dữ liệu không khai báo. |
| **Logging** | Các nguồn bắt buộc có heartbeat, ingest và audit configuration. | Nguồn mất, pipeline trễ, rule không chạy. |
| **Retention** | Lifecycle policy, job execution, exception/hold, backlog. | Job xóa fail, dữ liệu quá hạn chưa được xử lý. |
| **Vulnerability management** | Findings thuộc scope, deadline, exceptions và retest. | Quá hạn khắc phục hoặc exception hết hiệu lực. |
| **Third-party** | Vendor review status, subprocessor changes, token scopes. | Evidence hết hạn, tăng quyền hoặc vendor đổi phạm vi. |
| **Incident workflow** | Notification events với deadline và decision log. | Điều kiện đã kích hoạt nhưng case chưa được xử lý/escalate. |
| **DR/BC** | Backup restore tests, recovery exercise và mức đạt RTO/RPO. | Restore không thực hiện được hoặc achieved objectives vượt ngưỡng. |

Một rule phát hiện sai cấu hình chỉ hỗ trợ claim ở **phạm vi rule và nguồn đã quan sát**. Cần theo dõi completeness của inventory, nguồn, parser và trạng thái công cụ; nếu không, kết quả “0 violations” có thể che **0 visibility**.

## 12. Mô hình đánh giá và reporting

### 12.1. Trạng thái theo từng nghĩa vụ

| Trạng thái | Ý nghĩa | Yêu cầu xử lý |
|---|---|---|
| **Conform / compliant within scope** | Có evidence thích hợp, đủ và cho thấy điều kiện đã đáp ứng trong phạm vi/kỳ đánh giá. | Ghi phiên bản, nguồn, owner, review date và limitations. |
| **Nonconform / noncompliant** | Có bằng chứng đáng tin về việc không đáp ứng nghĩa vụ áp dụng. | Finding, phân loại tác động, escalation, remediation và retest. |
| **Inconclusive / insufficient evidence** | Thiếu nguồn, phạm vi, dữ liệu, quyền hoặc cơ sở diễn giải để kết luận. | Giải quyết evidence/applicability gap; không tính là conform. |
| **Not applicable** | Nguồn và điều kiện chứng minh nghĩa vụ không áp dụng. | Ghi rationale, review/approval và trigger thay đổi. |
| **Not assessed** | Áp dụng nhưng chưa thực hiện đánh giá cần thiết. | Lập kế hoạch đánh giá và ghi rủi ro chưa được kiểm chứng. |
| **Approved exception / accepted residual risk** | Có quyết định quản trị về rủi ro hoặc xử lý ngoại lệ trong phạm vi được phép. | Ghi owner, expiry, compensating controls và thẩm quyền; **không biến thành compliant** khi nghĩa vụ vẫn chưa đáp ứng. |

Đặc biệt, **một tổ chức không thể tự miễn tuân thủ một yêu cầu pháp lý chỉ bằng việc ký giấy chấp nhận rủi ro**. Khi phát hiện có khả năng vi phạm pháp luật, cần chuyển cho legal/compliance xử lý nghĩa vụ cụ thể, không dùng cơ chế exception kỹ thuật như cách xóa trách nhiệm.

### 12.2. Compliance risk vs. security risk

Một control có thể tuân thủ văn bản nhưng vẫn chưa bảo vệ đủ trước mối đe dọa mới. Ngược lại, một hệ thống có biện pháp kỹ thuật tốt vẫn có thể vi phạm nghĩa vụ về thông báo, mục đích sử dụng dữ liệu hoặc hồ sơ.

Do đó nên báo cáo riêng:

- **Compliance finding:** điều kiện của nghĩa vụ áp dụng không được đáp ứng.
- **Security risk finding:** kỹ thuật hoặc quy trình còn có khả năng gây thiệt hại, dù không có tiêu chí compliance cụ thể.
- **Evidence gap:** chưa đủ thông tin để đánh giá.
- **Control improvement:** cơ hội tăng hiệu lực hoặc giảm rủi ro, không mặc nhiên là vi phạm.

Không dùng “đạt compliance” làm bằng chứng tổng quát rằng hệ thống không còn lỗ hổng bảo mật.

### 12.3. Mẫu finding

~~~yaml
finding_id: CMP-2026-008
obligation_id: OBL-CON-001
criterion_id: CMP-DEL-003
source_version: "DPA-CUSTOMER-X v2.1"
scope: "customer-X-data / order-platform"
assessment_period: "2026-11"
status: nonconform
condition:
  description: "Một deletion request hợp lệ chưa hoàn thành đúng yêu cầu đã phê duyệt"
  observed_in: ["request-ledger", "deletion-job-audit"]
evidence:
  - "EV-REQ-102"
  - "EV-JOB-044"
impact:
  assessment: "Rủi ro lưu dữ liệu vượt thời hạn hợp đồng"
root_cause:
  status: investigating
owner: "data-platform"
remediation:
  action: "Sửa workflow retry/escalation và đánh giá dữ liệu tồn đọng"
  deadline: "2026-12-15"
retest:
  required: true
  result: pending
legal_review:
  required: true
~~~

Đây là dữ liệu giả lập. Một finding tốt tách **condition đã quan sát** khỏi **root cause chưa xác minh** và **tác động có thể xảy ra**. Không kết luận một vi phạm pháp lý đã được cơ quan có thẩm quyền xác nhận nếu hiện mới là đánh giá nội bộ hoặc nghi vấn.

## 13. Bài thực hành xuyên suốt: dịch vụ SaaS xử lý hồ sơ khách hàng

### 13.1. Bối cảnh

Một doanh nghiệp vận hành **Customer Portal**, lưu hồ sơ khách hàng trên database production, backup và object storage, dùng SaaS gửi email thông báo cùng một cloud provider. Hợp đồng giả định với khách hàng X quy định:

- Dữ liệu chỉ được sử dụng trong các mục đích đã thống nhất.
- Yêu cầu xóa hợp lệ phải được xử lý và phản hồi theo deadline hợp đồng.
- Khi phát hiện loại sự cố được định nghĩa trong hợp đồng, phải phối hợp đánh giá và thông báo bằng kênh đã thỏa thuận.
- Có trách nhiệm kiểm soát bên xử lý phụ trợ và lưu bằng chứng cần thiết về việc thực hiện.

Những điều khoản này **giả định cho bài học**, không viện dẫn luật cụ thể. Tổ chức còn có policy nội bộ về privileged access, encryption, log và DR.

### 13.2. Data flow và phạm vi

~~~mermaid
flowchart LR
    CLIENT["Khách hàng X"] --> WEB["Customer Portal"]
    WEB --> API["Customer API"]
    API --> DB["Production DB"]
    API --> OBJ["Object storage"]
    DB --> BAK["Encrypted backups"]
    API --> MAIL["Notification SaaS"]
    MAIL --> SUB["SaaS subprocessor"]
    IAM["IAM / MFA"] --> API
    AUD["Audit + monitoring"] --> API
    AUD --> DB
    AUD --> OBJ
~~~

Các mũi tên đại diện luồng chức năng hoặc phụ thuộc. Phải kiểm tra có dữ liệu định danh nào gửi sang SaaS, subprocessors xử lý gì, region/retention của các bản sao và ai có quyền truy cập.

### 13.3. Register sơ bộ

| ID | Nghĩa vụ | Trigger/scope | Owner | Tiêu chí kiểm chứng |
|---|---|---|---|---|
| **OBL-X-01** | Dùng dữ liệu đúng mục đích đã thỏa thuận. | Mọi luồng xuất dữ liệu liên quan khách hàng X. | Data governance + application. | Đối chiếu data flow, schema allowlist, test dữ liệu không được phép không ra ngoài. |
| **OBL-X-02** | Xử lý deletion request hợp lệ. | Yêu cầu hợp lệ của khách hàng X, deadline theo hợp đồng. | Privacy operations. | Request timeline + per-system deletion + vendor handling có evidence. |
| **OBL-X-03** | Xử lý và thông báo sự cố thuộc điều kiện hợp đồng. | Khi có incident trigger thỏa điều khoản. | Incident commander + legal. | Decision log, timeline, kênh và nội dung thông báo. |
| **OBL-X-04** | Giám sát subprocessors theo cam kết. | Vendor SaaS và các bên xử lý phụ trợ. | Vendor management. | Danh sách, hợp đồng, notice và review khi thay đổi. |
| **OBL-POL-05** | Bảo vệ quyền đặc quyền. | Human admin và service identities trong scope policy. | IAM team. | Effective access, MFA/credential policy, approvals và tests. |
| **OBL-POL-06** | Có khả năng phục hồi dịch vụ. | Customer Portal Critical theo BIA. | Platform/DR owner. | Restore exercise, recovery point, RTO/RPO theo policy. |

Bài toán không chỉ hỏi “hợp đồng có yêu cầu không”, mà còn “ai kiểm tra đường dữ liệu và bằng chứng kiểm toán nằm đâu”.

### 13.4. Scenario A — Yêu cầu xóa dữ liệu

Yêu cầu được tạo ở case REQ-501 vào thời điểm đã xác minh. Workflow xóa dữ liệu khỏi DB, nhưng object storage chưa chạy xong, một backup vẫn giữ dữ liệu theo chính sách và SaaS chưa gửi xác nhận.

Đánh giá:

1. **Applicability:** REQ-501 có hợp lệ và thuộc hợp đồng/loại dữ liệu nào?
2. **Scope:** hồ sơ, object, bản sao, vendor nào thực sự thuộc yêu cầu?
3. **Conditions:** hợp đồng và nghĩa vụ áp dụng nói gì về backup, trường hợp giữ dữ liệu và deadline?
4. **Evidence:** nhận yêu cầu, kiểm tra danh tính, ticket, kết quả per-system, vendor confirmation.
5. **Verdict:** nếu thiếu dữ liệu và chưa xác định xử lý backup được phép hay không, có thể là **inconclusive/partial**; không kết luận toàn bộ đã đạt chỉ vì DB job trả success.
6. **Remediation:** sửa object storage workflow, làm rõ retention với legal và vendor, đặt monitoring quá hạn, test end-to-end.

**Đối với bài kiểm tra đã có điều kiện rõ**, nếu case hợp lệ đã quá hạn mà các bước bắt buộc vẫn chưa hoàn tất, kết luận **nonconform** theo tiêu chí tương ứng.

### 13.5. Scenario B — Sự cố bên thứ ba

SaaS gửi thông báo về nghi vấn truy cập trái phép liên quan một subprocessor. Tổ chức phải xác định dữ liệu khách hàng X có bị ảnh hưởng và có trigger thông báo theo hợp đồng hay không.

Các bước cần thiết:

- Xác minh nguồn thông báo, thời điểm nhận, kênh liên lạc và incident ID.
- Xác định data categories, tenant, subprocessor, access window và phạm vi mà vendor đã xác minh.
- Đối chiếu điều kiện kích hoạt, thời hạn và bên nhận thông báo theo nguồn hiện hành.
- Phối hợp IR/legal/privacy, bảo toàn logs, revoke token hoặc giới hạn data flow khi cần.
- Ghi decision log, giả thuyết chưa xác minh, internal approvals và mọi thông báo/cập nhật.
- Theo dõi corrective action của vendor và test lại access controls hoặc data minimization.

Không kết luận “không phải sự cố của mình” chỉ vì nguồn sự kiện nằm ở nhà cung cấp. Ngược lại, không tự tuyên bố nghĩa vụ thông báo đã kích hoạt khi điều kiện pháp lý/hợp đồng chưa được xác định.

### 13.6. Test plan cho bài thực hành

| Test ID | Mục tiêu | Cách thực hiện có kiểm soát | Pass criteria | Evidence |
|---|---|---|---|---|
| T01 | Kiểm tra data minimization | Phát event giả với trường không được phép gửi sang SaaS. | Schema ngoài allowlist bị loại, không có PII ngoài scope. | Input/output đã làm sạch, schema version, test log. |
| T02 | Kiểm tra quyền truy cập | Dùng test identity gọi API dữ liệu khách hàng ngoài scope. | API deny, IAM scopes đúng policy. | HTTP result, effective-access snapshot, audit. |
| T03 | Kiểm tra deletion workflow | Tạo một hồ sơ giả có bản sao ở DB/object/vendor test. | Các bước xử lý trong scope hoàn tất; giữ dữ liệu có ngoại lệ được ghi đúng. | Case ledger, deletion jobs, vendor response. |
| T04 | Kiểm tra trigger và thời hạn | Tabletop sự cố SaaS với timestamps giả định. | Runbook quyết định đúng theo điều kiện đã phê duyệt; escalation có owner. | Exercise transcript, decision log, reviewer. |
| T05 | Kiểm tra third-party | Đối chiếu subprocessor list với hợp đồng và data map. | Những bên trong scope được nhận diện; thiếu sót có finding. | Vendor register, contract review, source links. |
| T06 | Kiểm tra telemetry | Ngắt nguồn synthetic trong sandbox hoặc dùng health-canary. | Có finding/alert về mất telemetry, không lặng lẽ coi là không có event. | Health metrics, alert timeline, test result. |
| T07 | Kiểm tra retest | Cố ý tạo workflow failure trong lab, sau đó sửa. | Finding closed chỉ khi actual đạt expected theo version mới. | Before/after tests, ticket, approval. |

Không dùng dữ liệu khách hàng thật, secrets thực hoặc phá hệ thống production để tạo test nếu có thể đạt mục tiêu bằng sandbox và synthetic evidence được ủy quyền.

### 13.7. Assurance conclusion mẫu

> **OBL-X-01:** trong phạm vi data-flow và test fixtures đã kiểm tra, event proxy chỉ gửi các trường allowlist; kết quả T01 PASS. Chưa đánh giá dữ liệu của feature mới đang thử nghiệm, vì vậy claim không áp dụng cho feature này.
>
> **OBL-X-02:** T03 phát hiện một object test chưa được xử lý, FAIL theo criterion đã định. Cần khắc phục workflow, đánh giá ảnh hưởng tới dữ liệu thật và chạy lại test.
>
> **OBL-X-03:** tabletop đã xác minh quy trình liên lạc, nhưng chưa có sự cố thật đại diện để kiểm tra operating effectiveness đầy đủ; kết quả không được trình bày như bằng chứng mọi thông báo luôn đúng hạn.
>
> **OBL-X-04:** danh mục subprocessors chưa có đủ evidence cập nhật; đánh giá INCONCLUSIVE và có owner xử lý.

Điểm cốt lõi là **kết luận phải có phạm vi**, thừa nhận phần chưa kiểm chứng và không chuyển nghĩa vụ chưa đạt thành “đạt có điều kiện” chỉ để cải thiện báo cáo.

## 14. Lưu bằng chứng và kiểm soát nguồn gốc

### 14.1. Evidence package mẫu

~~~text
assurance/compliance/customer-portal/
  register/
    obligations-current.yaml
    source-index.csv
    applicability-decisions.md
    source-version-history.md
  mapping/
    assets-and-data-flows.md
    controls-and-owners.csv
    criteria-and-test-cases.csv
  assessments/
    run-2026-11-28/
      scope-and-approvals.md
      sampled-population.csv
      technical-test-results.json
      workflow-timelines.csv
      raw-evidence-references.md
      evidence-integrity-manifest.txt
      legal-and-contract-review.md
      vendor-assurance-summary.md
      verdict-and-limitations.md
  findings/
    remediation-register.csv
    exceptions-and-approvals.md
    retest-records.json
  change-management/
    regulatory-intake-log.csv
    impact-and-review-decisions.md
~~~

Đây là bố cục minh họa. Hồ sơ thật có thể nằm trong GRC, ticketing, SIEM, kho dữ liệu hoặc hệ thống quản lý tài liệu với quyền truy cập được kiểm soát; **không cần sao chép mọi dữ liệu nhạy cảm ra thư mục chung**.

### 14.2. Những yêu cầu đối với mỗi evidence record

- ID, obligation ID, criterion ID, test ID và assessment run.
- Nguồn, ngày lấy, phạm vi, phiên bản source/contract/control.
- Ai thu hoặc cung cấp, cách xuất, dữ liệu gốc và biến đổi.
- Asset, account, tenant, environment và time range.
- Expected vs actual, error và hạn chế của phương pháp.
- Quyền truy cập, độ nhạy, retention và integrity/hash nếu cần.
- Reviewer, ngày đánh giá, verdict và link finding/retest.

Một screenshot dashboard **không có nguồn, mốc thời gian và rule/criterion version** thường chưa đủ cho một kết luận compliance quan trọng.

### 14.3. Bảo vệ và retention của bằng chứng

Bằng chứng có thể chứa bản hợp đồng, tài liệu kiểm toán độc lập, cấu hình IAM, log truy cập, dữ liệu cá nhân hoặc thông tin sự cố. Cần:

- Giới hạn quyền theo vai trò; tách người thu, người review và người quản trị retention khi phù hợp.
- Mã hóa dữ liệu lưu và đường truyền; audit mọi truy cập/export quan trọng.
- Bảo toàn raw/provenance; redaction trên bản báo cáo hoặc bản làm việc.
- Retention theo nguồn nghĩa vụ có hiệu lực và privacy/data minimization.
- Kiểm tra restore, khả năng truy xuất và hash khi chuyển giao nếu cần.
- Có quy trình legal hold và release được phê duyệt; không tự giữ vô hạn hoặc xóa trước hạn.

## 15. Quản lý thay đổi nghĩa vụ và ảnh hưởng đến hệ thống

### 15.1. Regulatory/contract change intake

Khi nhận tin về một thay đổi nghĩa vụ, không nên chỉ gửi email “có luật mới” cho kỹ thuật. Cần một workflow:

1. Ghi source, phiên bản, ngày công bố/hiệu lực và phạm vi khả dĩ.
2. Xác minh tính chính thức và phân công legal/compliance diễn giải.
3. Xác định legal entities, sản phẩm, business processes, data flows và vendors bị ảnh hưởng.
4. Đối chiếu obligation register hiện hành để thấy requirement thêm/sửa/bỏ.
5. Ước lượng gaps, rủi ro, deadline triển khai và thứ tự ưu tiên.
6. Giao control owner viết kế hoạch thay đổi, test và evidence.
7. Cập nhật policies, architecture, workflows, contracts nếu được phê duyệt.
8. Đánh giá lại controls và lưu verdict; thông báo các bên liên quan.
9. Đưa trigger mới vào chương trình monitoring, onboarding và renewal.

### 15.2. Không sửa tiêu chí sau khi thấy kết quả fail

Nếu criterion cũ yêu cầu một control trong kỳ đã qua, việc sửa chính sách về sau **không làm lịch sử vận hành đổi lại**. Giữ nguyên đánh giá theo phiên bản và ngày hiệu lực cũ; áp dụng quy tắc mới cho kỳ tương ứng và ghi rationale.

Tương tự, nếu có ngoại lệ hợp lệ về mặt **policy nội bộ**, phải đánh giá ngoại lệ theo chính policy có hiệu lực. Nếu đó là yêu cầu pháp lý bắt buộc, risk owner **không thể** đơn phương bãi bỏ bằng giấy chấp nhận rủi ro.

## 16. KPI và báo cáo cho chương trình compliance assurance

| KPI | Cách tính/diễn giải | Giới hạn |
|---|---|---|
| **Obligation inventory coverage** | Nghĩa vụ trong scope đã có source, applicability, owner / tổng nghĩa vụ đã nhận diện. | Có thể bỏ sót nguồn chưa được phát hiện; cần monitoring nguồn bên ngoài. |
| **Applicability review freshness** | Tỷ lệ nghĩa vụ có quyết định applicability còn phù hợp sau thay đổi phạm vi. | Review mới nhưng sai diễn giải vẫn có rủi ro. |
| **Control mapping coverage** | Nghĩa vụ áp dụng có đủ controls/owners và criteria / tổng nghĩa vụ áp dụng. | Mapping trên giấy chưa chứng minh hoạt động. |
| **Evidence sufficiency rate** | Phép đánh giá có evidence thích hợp/đủ / tổng phép đánh giá hợp lệ. | Cần tiêu chuẩn chất lượng và reviewer độc lập. |
| **Assessment execution rate** | Phép đánh giá đến hạn đã thực hiện / tổng phép đánh giá đến hạn. | Not assessed không tính Pass. |
| **Nonconformity age** | Số ngày finding còn mở, phân nhóm severity và hạn. | Số finding ít không chứng minh ít rủi ro nếu test kém. |
| **Retest closure rate** | Finding đã xác minh khắc phục đạt / finding đã báo xong remediation. | Đóng ticket không đủ nếu chưa retest. |
| **Exception/waiver expiry** | Số ngoại lệ quá hạn hoặc không còn điều kiện hợp lệ. | Legal obligations không được waived bằng cơ chế nội bộ. |
| **Trigger response timeliness** | Thời gian từ event kích hoạt đến quyết định/thực hiện theo nghĩa vụ. | Phải dùng đúng mốc trigger và deadline của nguồn. |
| **Unresolved legal/evidence gaps** | Số applicability issues hoặc evidence gaps còn mở, theo mức ảnh hưởng. | Không được gộp Inconclusive thành Compliant. |

Không đặt mục tiêu “100% xanh” bằng cách ẩn các điều kiện chưa kiểm chứng. KPI tốt giúp ưu tiên remediation, phát hiện nơi thiếu evidence và ngăn lặp lại vấn đề.

## 17. Sai lầm phổ biến

1. **“Mọi chuẩn bảo mật đều là luật.”** Tiêu chuẩn, luật, hợp đồng và policy có nguồn ràng buộc khác nhau.
2. **“Tổ chức có chứng nhận nên tuân thủ mọi nghĩa vụ.”** Chứng nhận có scope, kỳ và giới hạn riêng.
3. **“Có controls mạnh đồng nghĩa tuân thủ.”** Có thể vẫn thiếu nghĩa vụ về mục đích dùng dữ liệu, thông báo hoặc tài liệu hóa.
4. **“Đã ký hợp đồng với vendor thì hết trách nhiệm.”** Tổ chức vẫn phải quản lý nghĩa vụ trong quan hệ của mình và phân định vai trò.
5. **“Policy tồn tại nên operating effectiveness đã đạt.”** Cần evidence trong kỳ, test và log thực.
6. **“Không có log vi phạm nghĩa là compliant.”** Có thể thiếu telemetry, population hoặc parser lỗi.
7. **“Bất kỳ dữ liệu nào cũng giữ càng lâu càng tốt để audit.”** Retention phải theo mục đích/nghĩa vụ áp dụng và bảo vệ dữ liệu.
8. **“Chỉ cần xóa khỏi DB chính.”** Backup, object, cache, analytics, vendor và data lineage cần xem xét theo source.
9. **“Có ticket phê duyệt nghĩa là ngoại lệ hợp pháp.”** Phải xét quyền phê duyệt và nguồn nghĩa vụ; không thể tự miễn luật.
10. **“Compliance score giảm khi ghi nhận finding nên hạn chế báo.”** Che finding làm mất giá trị assurance và tạo rủi ro lặp.
11. **“Một ảnh dashboard chứng minh cả năm.”** Phải kiểm tra tính liên tục, thay đổi và phạm vi trong kỳ.
12. **“Đã pass ở một môi trường thì pass mọi tenant.”** Account, region, data class, vendor và policy có thể khác.
13. **“Ghi deadline sau khi team nhận ticket.”** Phải dùng mốc trigger theo nghĩa vụ, không chọn mốc có lợi.
14. **“Chỉnh policy để xóa lịch sử không tuân thủ.”** Giữ lịch sử source, effective date và verdict theo từng kỳ.

## 18. Bài tập ứng dụng

Một tổ chức cung cấp SaaS quản lý hợp đồng có bốn môi trường production, hai cloud regions và một vendor xử lý email. Customer Y yêu cầu xử lý yêu cầu xóa dữ liệu và thông báo sự cố theo thỏa thuận. Policy nội bộ đòi privileged access được xét duyệt và backup phục hồi được.

Trong một đợt audit phát hiện:

- Contract owner chưa lưu phiên bản phụ lục mới nhất, chưa xác minh trigger của nghĩa vụ thông báo.
- 20 yêu cầu xóa đã được xử lý ở DB nhưng 3 yêu cầu vẫn còn file đính kèm trong object storage.
- IAM report chỉ lấy region A; chưa có inventory effective access ở region B.
- Nhóm platform nói “backup chạy thành công” nhưng chưa restore thử.
- Vendor email có báo cáo kiểm toán độc lập, nhưng scope báo cáo không bao phủ feature mới đang sử dụng.

**Yêu cầu:**

1. Xác định nghĩa vụ nào là hợp đồng, policy nội bộ, yêu cầu chưa rõ applicability và controls tương ứng.
2. Viết 5 bản ghi obligation register có source/version, scope, owner, requirement, trigger và test.
3. Phân loại từng kết quả **nonconform, inconclusive hoặc not assessed** dựa trên evidence hiện có, tránh tuyên bố quá mức.
4. Chỉ ra vì sao một API report chỉ gồm region A không chứng minh IAM ở cả hai region đạt.
5. Thiết kế test deletion end-to-end với một bộ dữ liệu giả, gồm DB, object, backup và vendor.
6. Đề xuất thủ tục rà soát scope của báo cáo kiểm toán vendor và xử lý feature mới ngoài phạm vi.
7. Tạo finding cho các file chưa xóa, nêu condition, evidence, owner, deadline, retest và phần pháp lý cần review.
8. Thiết kế dashboard với ít nhất 4 KPI nhưng không gộp **inconclusive** thành compliant.

**Gợi ý:** Ba file đính kèm còn tồn tại có thể chứng minh một control không hoàn thành **nếu** yêu cầu xóa áp dụng và điều kiện thực thi đã rõ. Nghĩa vụ thông báo chưa có phiên bản/trigger rõ nên cần legal/contract review; không tự kết luận đạt hoặc không áp dụng. Backup success không thay thế restore test.

## 19. Checklist triển khai Compliance obligation

- [ ] Có danh mục nguồn nghĩa vụ gồm luật/quy định, hợp đồng, policy và cam kết đã chọn.
- [ ] Mỗi nghĩa vụ có mã, nguồn, điều khoản, version, ngày hiệu lực và thẩm quyền diễn giải.
- [ ] Có applicability assessment theo pháp nhân, role, jurisdiction, sản phẩm, dữ liệu và thời gian.
- [ ] Những điều kiện chưa rõ được đánh dấu unknown/pending và có người xử lý.
- [ ] Có obligation register được version và quản lý quyền cập nhật.
- [ ] Nghĩa vụ quan trọng được phân rã thành requirements có owner, trigger và deadline.
- [ ] Requirements gắn với risk/control IDs, assets, data flows và third parties.
- [ ] Criteria và decision rules được thống nhất trước khi thu thập evidence.
- [ ] Có kiểm tra design, implementation và operating effectiveness theo mức rủi ro.
- [ ] Evidence ghi scope, kỳ, nguồn, timestamp, version, phương pháp thu và giới hạn.
- [ ] Đã đánh giá completeness của inventory, logs, APIs và vendor evidence.
- [ ] Có phương pháp examine, interview và test; hoạt động test an toàn, có thẩm quyền.
- [ ] Có quy trình xử lý conflict về retention, deletion, legal hold và incident notification.
- [ ] Third-party/subprocessor obligations được mapping và giám sát.
- [ ] Có continuous monitoring cho data flows, IAM, logging, retention và incident workflows.
- [ ] Kết quả conform, nonconform, inconclusive, not applicable và not assessed được phân biệt.
- [ ] Exceptions có nguồn thẩm quyền, phạm vi và hạn; không dùng chấp nhận rủi ro để miễn nghĩa vụ pháp lý.
- [ ] Findings có condition, evidence, cause nếu biết, risk, owner, plan và retest.
- [ ] Quy trình cập nhật nguồn luật/hợp đồng/policy có trigger, impact assessment và phê duyệt.
- [ ] Báo cáo cho quản lý có uncertainty, limitations, evidence gaps và residual risk.
- [ ] Thường xuyên diễn tập nghĩa vụ có trigger như xóa dữ liệu, sự cố và offboarding.

## 20. Câu hỏi tự đánh giá

1. Vì sao một tiêu chuẩn hoặc hướng dẫn thực hành tốt không mặc nhiên là nghĩa vụ pháp lý?
2. Khi nào một điều khoản chỉ áp dụng cho một khách hàng vẫn cần có control riêng?
3. Tại sao phải xác định pháp nhân, vai trò xử lý dữ liệu và điều kiện trigger trước khi chọn kỹ thuật kiểm tra?
4. Một bộ log có hash đúng nhưng thiếu một cloud region có thể chứng minh tuân thủ trong toàn bộ production không?
5. Vì sao việc tồn tại policy khác với việc control đã triển khai và vận hành hiệu lực?
6. Khi legal hold và yêu cầu xóa dữ liệu có vẻ xung đột, kỹ thuật và pháp chế nên phối hợp ra sao?
7. Một giấy chấp nhận rủi ro của quản lý có thể tự làm mất hiệu lực nghĩa vụ pháp luật không?
8. Một vendor có chứng nhận có đủ chứng minh phần tích hợp của khách hàng đã bảo vệ đúng data scopes không?
9. Tại sao kỳ audit phải lưu phiên bản nghĩa vụ đã có hiệu lực ở thời điểm được đánh giá?
10. Nếu một ticket xử lý yêu cầu bị tạo muộn, cần dùng timestamp nào để kiểm tra deadline?
11. Hãy viết một obligation register entry về incident notification hoặc retention, kèm applicability, source, owner, requirements, tests và evidence.
12. Thiết kế một vòng monitoring và retest giúp phát hiện khi control tiếp tục không đáp ứng sau một lần sửa.

**Điểm cốt lõi:** **Compliance obligation chỉ có thể được đánh giá đúng khi biết yêu cầu nào áp dụng, cho ai, khi nào và vì sao.** Security assurance chuyển các nghĩa vụ ấy thành controls và tiêu chí có thể kiểm chứng, giữ bằng chứng đủ tin cậy, báo minh bạch những phần chưa đạt hoặc chưa biết, rồi khắc phục và tái đánh giá liên tục. **Một trạng thái “compliant” không có scope, phiên bản nguồn và evidence kiểm chứng không phải là bảo đảm đáng tin cậy.**
