# Security questionnaire: xây dựng và đánh giá bảng câu hỏi bảo mật nhà cung cấp dựa trên bằng chứng

**Security questionnaire** là bộ câu hỏi có cấu trúc dùng để thu thập thông tin về chính sách, quy trình, biện pháp kỹ thuật và cách vận hành bảo mật của một tổ chức, sản phẩm hoặc dịch vụ. Trong **third-party assurance**, bên sử dụng dịch vụ dùng bảng câu hỏi để hiểu và kiểm chứng mức độ bảo vệ của nhà cung cấp (vendor/supplier), nhận diện những khoảng trống và đưa ra quyết định chấp nhận, giảm thiểu hoặc từ chối rủi ro.

Bảng câu hỏi không phải chứng nhận bảo mật. Một câu trả lời **“Yes — chúng tôi có MFA”** chưa xác định được MFA áp dụng cho loại tài khoản nào, trên hệ thống nào, từ khi nào và có ngoại lệ hay không. Ngược lại, một câu trả lời **“Partial”** kèm bằng chứng, phạm vi, biện pháp bù trừ và thời hạn khắc phục có thể hữu ích hơn một dấu tick “Yes” thiếu căn cứ.

Bài học thuộc chương **Third-party assurance** của module **SECURITY_SECURITY_ASSURANCE**. Theo định hướng module, việc đánh giá phải có **bằng chứng** liên kết mục tiêu bảo mật với rủi ro, yêu cầu, security controls, kiểm thử, audit và xử lý phát hiện; không dừng ở khâu thu thập tài liệu rồi lưu trữ. Câu hỏi trung tâm là: **nhà cung cấp đang cung cấp dịch vụ nào, dữ liệu và quyền truy cập nào thuộc phạm vi, control nào cần có, bằng chứng nào chứng minh control được thiết kế và vận hành hiệu quả, và ai chịu trách nhiệm với rủi ro còn lại?**

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt security questionnaire với chứng nhận, báo cáo audit, kiểm thử thực tế và quyết định chấp nhận rủi ro.
2. Xác định đối tượng, dịch vụ, dữ liệu, trách nhiệm chia sẻ và mức rủi ro để lựa chọn bộ câu hỏi phù hợp.
3. Viết câu hỏi rõ ràng, một nghĩa, có điều kiện áp dụng, mốc thời gian, kỳ đánh giá và bằng chứng mong đợi.
4. Phân tích câu trả lời Yes/No/Partial/Not Applicable/Unknown mà không tự coi tự khai là chứng cứ đủ.
5. Đánh giá chất lượng và giới hạn của các minh chứng như chính sách, báo cáo SOC 2, chứng nhận ISO/IEC 27001, kết quả penetration test, log hoặc báo cáo diễn tập DR.
6. Liên kết mỗi điểm thiếu với control, tác động nghiệp vụ, owner, hợp đồng, biện pháp bù trừ, hạn và retest.
7. Xây dựng quy trình đánh giá ban đầu, tái đánh giá sau thay đổi và theo dõi assurance liên tục trong vòng đời nhà cung cấp.

## 2. Security questionnaire có vai trò gì trong third-party assurance?

### 2.1. Bối cảnh sử dụng

Một tổ chức có thể thuê bên thứ ba xử lý dữ liệu khách hàng, vận hành phần mềm SaaS, quản trị hạ tầng, cung cấp API hoặc truy cập môi trường nội bộ. Khi đó, một phần rủi ro và trách nhiệm kiểm soát nằm ở nhà cung cấp nhưng tổ chức sử dụng dịch vụ vẫn phải **hiểu, ra quyết định và quản trị các phụ thuộc** trong giới hạn nghĩa vụ của mình.

Security questionnaire hỗ trợ:

- **Trước khi ký hợp đồng/onboarding:** đánh giá năng lực bảo mật và điều kiện cần đáp ứng trước khi truy cập hệ thống hoặc dữ liệu.
- **Khi gia hạn hoặc mở rộng phạm vi:** kiểm tra control có còn phù hợp với lượng dữ liệu, loại kết nối và phạm vi xử lý mới.
- **Khi có thay đổi trọng yếu:** đánh giá lại khi nhà cung cấp chuyển region, thay subprocessors, xảy ra sự cố hoặc thay kiến trúc.
- **Theo kỳ:** xác nhận tình trạng control, bằng chứng mới, ngoại lệ và các finding chưa đóng.
- **Khi chấm dứt hợp đồng:** xác nhận thu hồi quyền truy cập, hoàn trả/xóa dữ liệu và nghĩa vụ tiếp tục liên quan.

### 2.2. Bảng câu hỏi đứng ở đâu trong chuỗi assurance?

~~~mermaid
flowchart LR
    CONTEXT["Dịch vụ / dữ liệu / kết nối"] --> RISK["Phân loại rủi ro"]
    RISK --> CTRL["Yêu cầu security control"]
    CTRL --> Q["Security questionnaire"]
    Q --> A["Câu trả lời + tài liệu chứng minh"]
    A --> VERIFY["Kiểm chứng tính phù hợp và hiệu lực"]
    VERIFY --> DEC{"Đáp ứng yêu cầu?"}
    DEC -- "Có" --> APP["Phê duyệt trong phạm vi"]
    DEC -- "Chưa" --> GAP["Finding + kế hoạch giảm rủi ro"]
    GAP --> DECISION["Chấp nhận có điều kiện / tạm dừng / từ chối"]
    APP --> RECHECK["Theo dõi, thay đổi, tái đánh giá"]
    DECISION --> RECHECK
~~~

Một kết quả “đã hoàn thành 100% bảng câu hỏi” chỉ chứng minh mức độ **trả lời**. Nó không chứng minh 100% control đạt, không chứng minh nhà cung cấp không có sự cố và không thay thế kiểm soát mà khách hàng phải tự triển khai.

### 2.3. Phân biệt những thuật ngữ liên quan

| Thuật ngữ | Vai trò | Không được suy ra |
|---|---|---|
| **Security questionnaire** | Thu thập mô tả kiểm soát, dữ liệu và minh chứng theo yêu cầu đánh giá | Mọi câu trả lời đều đúng và đủ |
| **Self-attestation** | Nhà cung cấp tự xác nhận một phát biểu | Đã được kiểm chứng độc lập |
| **Evidence / artifact** | Tài liệu hoặc kết quả có thể đối chiếu với yêu cầu | Tài liệu đúng tên chứng minh hiệu lực đầy đủ |
| **Certification** | Xác nhận theo chương trình và phạm vi cụ thể | Toàn bộ sản phẩm, region, đội và subprocessor đều đạt |
| **Audit/attestation report** | Kết quả đánh giá theo tiêu chí, kỳ và scope được mô tả | Không có ngoại lệ hoặc rủi ro ngoài phạm vi |
| **Penetration-test summary** | Ghi nhận kiểm thử bảo mật ở phạm vi, thời điểm, phương pháp nhất định | Không còn bất kỳ lỗ hổng nào |
| **Risk acceptance** | Quyết định có thẩm quyền chấp nhận rủi ro còn lại | Control đang không đạt trở thành PASS |
| **Continuous assurance** | Theo dõi bằng chứng, thay đổi và hiệu lực control qua thời gian | Một lần questionnaire là đủ vĩnh viễn |

## 3. Xác định phạm vi trước khi gửi câu hỏi

### 3.1. Đối tượng đánh giá là dịch vụ cụ thể

Không nên chỉ hỏi “Công ty bạn có ISO 27001 không?” rồi áp câu trả lời cho mọi sản phẩm. Cần xác định tối thiểu:

- **Vendor identity:** pháp nhân ký hợp đồng, đơn vị cung cấp trực tiếp và đơn vị xử lý phụ trợ nếu có.
- **Service/product:** tên, phiên bản hoặc phạm vi dịch vụ được sử dụng; hosting model.
- **Environment/region:** production, test, khu vực lưu/xử lý dữ liệu, vùng dự phòng.
- **Data:** phân loại, loại dữ liệu, khối lượng, thời hạn lưu, quyền truy cập và luồng truyền.
- **Integration:** API, SSO, VPN, network, webhook, privileged access, keys hoặc agent chạy trong hạ tầng khách hàng.
- **Operational role:** nhà cung cấp có thể chỉ xem dữ liệu, xử lý, quản trị hạ tầng hay trực tiếp thay cấu hình?
- **Business criticality:** nếu nhà cung cấp ngừng hoạt động, dịch vụ nghiệp vụ bị ảnh hưởng thế nào?
- **Shared responsibility:** bên nào cấu hình MFA, khóa, log, backup, phân quyền, data retention và incident response?
- **Contractual obligations:** các yêu cầu trong hợp đồng, chính sách nội bộ và quy định pháp luật áp dụng.

Cùng một nhà cung cấp có thể cần hai hồ sơ khác nhau: dịch vụ gửi email marketing nhận dữ liệu hạn chế và dịch vụ quản trị production bằng quyền đặc biệt mang mức rủi ro khác nhau.

### 3.2. Ví dụ data flow và ranh giới kiểm soát

Giả sử doanh nghiệp sử dụng SaaS hỗ trợ chăm sóc khách hàng:

~~~mermaid
flowchart LR
    USER["Nhân viên hỗ trợ"] --> SSO["IdP/SSO của khách hàng"]
    SSO --> APP["SaaS nhà cung cấp"]
    CUSTOMER["Dữ liệu ticket và liên hệ"] --> API["Tích hợp API"]
    API --> APP
    APP --> STORAGE["Lưu trữ / backup của nhà cung cấp"]
    APP --> SUB["Subprocessor: email/analytics"]
    APP --> LOG["Audit và security telemetry"]
    APP --> EXPORT["Xuất / trả / xóa dữ liệu khi kết thúc"]
~~~

Bản vẽ trên gợi ra những câu hỏi không thể chỉ dùng bảng câu hỏi chung:

1. Dữ liệu nào được SaaS tiếp nhận và có thể được subprocessor xử lý?
2. Ai cấp/quản lý SSO và tài khoản quản trị cục bộ còn tồn tại hay không?
3. Token API có quyền đọc/ghi nào, vòng đời và cách thu hồi ra sao?
4. Log ghi nhận hoạt động nhân viên hỗ trợ và admin ở đâu, ai truy cập được?
5. Nhà cung cấp có thể truy cập dữ liệu khách hàng ở cấp hạ tầng không?
6. Backup, recovery và xóa dữ liệu sau hợp đồng được xác định thế nào?

Phải kiểm tra ranh giới **customer-managed** so với **vendor-managed**; không yêu cầu nhà cung cấp chịu trách nhiệm một control mà khách hàng thực sự phải cấu hình, và cũng không bỏ qua nghĩa vụ hai bên phải phối hợp.

### 3.3. Phân tầng rủi ro

Thay vì gửi cùng một bảng dài cho mọi nhà cung cấp, tổ chức có thể phân tầng theo **risk tier**. Đây là ví dụ phương pháp, không phải chuẩn bắt buộc:

| Tier tham khảo | Tiêu chí điển hình | Mức độ assurance tương ứng |
|---|---|---|
| **Critical/High** | Truy cập dữ liệu nhạy cảm, quyền quản trị đặc biệt, dịch vụ cốt lõi hoặc gián đoạn gây tác động lớn | Questionnaire theo control trọng yếu, bằng chứng độc lập, đánh giá sâu, điều khoản hợp đồng, theo dõi thường xuyên |
| **Medium** | Xử lý dữ liệu nội bộ, tích hợp hạn chế, phụ thuộc có phương án thay thế | Bộ câu hỏi trọng tâm, đối chiếu evidence theo mức rủi ro, rà soát định kỳ |
| **Low** | Dịch vụ ít tích hợp, không xử lý dữ liệu đáng kể, tác động thấp | Sàng lọc cơ bản, xác nhận phạm vi, kiểm tra tối thiểu và trigger tái đánh giá |

**Tier không phải nhãn vĩnh viễn.** Khi dịch vụ mở rộng từ thử nghiệm không có dữ liệu thật sang production xử lý dữ liệu khách hàng, cần phân loại lại trước khi cấp thêm quyền/truy cập.

### 3.4. Dùng câu hỏi có điều kiện

Một số nhánh nên xuất hiện **chỉ khi áp dụng**:

- Nếu xử lý dữ liệu cá nhân: quyền riêng tư, xử lý yêu cầu chủ thể dữ liệu, lưu/xóa và chuyển dữ liệu qua biên giới khi áp dụng.
- Nếu có quyền quản trị vào mạng khách hàng: MFA, PAM, session recording, quản lý thiết bị quản trị và quyền break-glass.
- Nếu SaaS có API: xác thực, scope token, rate limiting, webhook signature, logging và kiểm thử API.
- Nếu cung cấp phần mềm cài trong hệ thống khách hàng: SDLC, SBOM/provenance, patch, vulnerability disclosure và trách nhiệm vận hành.
- Nếu dịch vụ có tính thiết yếu cao: business continuity, DR, diễn tập phục hồi, phụ thuộc cloud và exit plan.
- Nếu có subprocessor: danh sách, vai trò, dữ liệu, kiểm soát chuyển giao và nghĩa vụ thông báo thay đổi.

Câu hỏi có điều kiện giúp giảm mệt mỏi và tăng chất lượng câu trả lời, nhưng logic rẽ nhánh phải được giữ cùng phiên bản để auditor có thể biết câu nào đã được bỏ qua và vì sao.

## 4. Thiết kế câu hỏi có thể kiểm chứng

### 4.1. Một câu hỏi tốt có những thành phần gì?

Mỗi câu hỏi nên mô tả:

1. **ID và control objective:** yêu cầu đang muốn kiểm chứng.
2. **Scope:** service, asset, tài khoản, môi trường, người dùng hoặc loại dữ liệu liên quan.
3. **Assertion:** trạng thái/hoạt động cụ thể cần đạt.
4. **Thời gian:** hiện tại, trong kỳ 12 tháng vừa qua, tại thời điểm cụ thể hoặc theo chu kỳ.
5. **Bằng chứng:** loại artifact, kỳ, nguồn, bằng chứng vận hành hoặc kiểm thử.
6. **Phương án trả lời:** Yes / Partial / No / Not applicable / Unknown cùng lý do.
7. **Follow-up:** câu hỏi bổ sung khi câu trả lời có ngoại lệ hoặc thiếu chứng cứ.
8. **Độ nhạy cảm:** cách chia sẻ bằng chứng không làm lộ secret hoặc thông tin nội bộ quá mức.

Ví dụ kém:

> “Bạn có bảo mật tốt, mã hóa dữ liệu, kiểm thử định kỳ và quy trình ứng cứu đầy đủ không?”

Câu trên gộp nhiều control, không rõ scope, ngưỡng, kỳ và tiêu chuẩn đánh giá. Người trả lời có thể đánh Yes dù mới có một phần.

Ví dụ tốt:

> “Đối với các tài khoản quản trị có thể truy cập môi trường production của dịch vụ được đánh giá, MFA có bắt buộc với mọi đường đăng nhập tương tác hay không? Nếu có ngoại lệ, hãy nêu phạm vi, biện pháp bù trừ, thời hạn. Vui lòng cung cấp chính sách có hiệu lực và bằng chứng cấu hình đã che thông tin nhạy cảm.”

### 4.2. Tránh câu hỏi dẫn dắt và câu hỏi nhiều ý

| Câu hỏi chưa phù hợp | Vấn đề | Cách cải tiến |
|---|---|---|
| “Bạn tuân thủ tất cả tiêu chuẩn bảo mật chứ?” | Không có tiêu chuẩn hay scope | Hỏi kiểm soát cụ thể, kỳ và evidence |
| “Có dùng mã hóa mạnh không?” | “Mạnh” không định nghĩa | Nêu dữ liệu, trạng thái lưu/truyền, trách nhiệm và cách quản lý khóa |
| “Bạn có backup và DR đạt yêu cầu không?” | Gộp backup với phục hồi | Tách backup coverage, RPO/RTO, test restore và kết quả |
| “Có bao giờ bị hack không?” | Mơ hồ và có thể xung đột nghĩa vụ bảo mật | Hỏi cách quản lý incident, loại sự kiện phải thông báo và hồ sơ cải tiến phù hợp |
| “Bạn có SOC 2?” | Không rõ loại report, kỳ, hệ thống | Hỏi bản report áp dụng cho service, thời kỳ, criteria, exceptions và bridge period |
| “Bạn có pentest và đã sửa mọi lỗi?” | Không rõ thời điểm/scope/severity | Hỏi scope, thời gian, critical/high findings, remediation và retest |
| “Nhà thầu phụ có an toàn không?” | Không biết subprocessor nào | Hỏi danh sách, dữ liệu, trách nhiệm, phương pháp đánh giá và thay đổi |

### 4.3. Chuẩn trả lời

Có thể chuẩn hóa:

| Trạng thái | Ý nghĩa | Bằng chứng hoặc lý do cần thu |
|---|---|---|
| **YES** | Assertion đạt trong toàn bộ scope được hỏi và kỳ áp dụng | Artifact tương ứng và minh chứng hiệu lực khi cần |
| **PARTIAL** | Chỉ đạt một phần scope hoặc có ngoại lệ | Phần đạt/chưa đạt, lý do, mức rủi ro, kế hoạch khắc phục |
| **NO** | Không có control hoặc không đạt assertion | Tác động, compensating control và remediation |
| **NOT_APPLICABLE** | Control không áp dụng do bản chất dịch vụ/scope | Lý do cụ thể, người phê duyệt hoặc bằng chứng xác nhận |
| **UNKNOWN** | Bên trả lời chưa xác định được hoặc chưa có dữ liệu | Chủ thể điều tra, thời hạn cung cấp thông tin, trạng thái chưa kết luận |

**YES là tuyên bố của nhà cung cấp**, không phải kết quả xác minh của đội assurance. Nên có một trường riêng cho **assessment verdict**: PASS/FAIL/INCONCLUSIVE/NOT_TESTED/ACCEPTED_RISK, tránh đánh đồng hai trạng thái.

### 4.4. Gắn mỗi câu hỏi với đối tượng được kiểm tra

Một bộ metadata tham khảo:

~~~yaml
question_id: "TPQ-IAM-003"
version: "1.2"
domain: "Identity and access management"
control_objective: "Privileged access requires strong authentication"
scope:
  service: "Customer-support SaaS"
  environments: ["production"]
  accounts: "Interactive privileged identities"
question: >
  Is MFA enforced for all interactive privileged access paths
  to the in-scope production service?
response_options: ["YES", "PARTIAL", "NO", "NOT_APPLICABLE", "UNKNOWN"]
required_explanation:
  - "Authentication methods and enforcement scope"
  - "Known exceptions and compensating controls"
  - "Last reviewed date"
expected_evidence:
  - "Approved access policy effective during the review period"
  - "Redacted enforcement configuration or independent test result"
follow_up_if_partial:
  - "Which privileged paths are not covered and why?"
risk_if_unmet: "Unauthorized privileged access"
reviewer_role: "third-party-security-assessor"
~~~

Đây là **định dạng minh họa để học cách thiết kế câu hỏi**, không phải schema chính thức của một nền tảng questionnaire. Nội dung có thể được chuyển sang biểu mẫu, hệ thống quản lý rủi ro hay bảng tính tùy công cụ thực tế. Không lưu password hoặc secret trong phần evidence.

## 5. Các nhóm câu hỏi cốt lõi

Các domain nên được chọn theo dịch vụ và rủi ro, không nhất thiết gửi đủ mọi nhóm cho từng nhà cung cấp.

### 5.1. Governance và trách nhiệm

Mục tiêu là biết ai sở hữu rủi ro và cách tổ chức duy trì control.

**Câu hỏi tham khảo:**

- Ai chịu trách nhiệm phê duyệt chính sách an ninh và các ngoại lệ? Chính sách được rà soát theo sự kiện nào?
- Những hoạt động thuộc dịch vụ đang được đánh giá nằm trong phạm vi chương trình bảo mật nào?
- Có đánh giá rủi ro định kỳ và khi thay đổi lớn hay không? Ai theo dõi việc xử lý finding?
- Có quy trình nhân sự, onboarding/offboarding và đào tạo cho người có quyền truy cập dữ liệu khách hàng không?
- Nhà cung cấp giám sát compliance hoặc control effectiveness bằng chỉ số, audit và kiểm tra nào?

**Bằng chứng:** policy có phiên bản, scope, phê duyệt, risk register đã che thông tin nhạy cảm, báo cáo đánh giá phù hợp.

### 5.2. Danh tính và quyền truy cập

- MFA có bắt buộc với tài khoản quản trị tương tác trong phạm vi production không?
- Quyền được cấp theo role, nguyên tắc tối thiểu và có review theo kỳ hay theo thay đổi chức năng không?
- Tài khoản nhân sự nghỉ việc được vô hiệu hóa theo workflow nào?
- Truy cập hỗ trợ của vendor vào dữ liệu khách hàng có cần phê duyệt, ghi audit và giới hạn thời gian không?
- Tài khoản/service identity, API key và break-glass credential được quản lý, rotate và giám sát thế nào?

**Bằng chứng:** RBAC/IAM policy, bản cấu hình redacted, báo cáo access review, mẫu ticket phê duyệt đã khử nhạy cảm, log truy cập hỗ trợ.

### 5.3. Bảo vệ dữ liệu và quyền riêng tư

- Dịch vụ nhận loại dữ liệu nào, lưu/xử lý ở đâu, giữ trong bao lâu và bên nào có thể tiếp cận?
- Mã hóa dữ liệu khi truyền và khi lưu áp ở lớp nào, khóa do ai quản trị?
- Có cơ chế cô lập dữ liệu giữa các khách hàng/tenant và kiểm thử hiệu lực không?
- Có chính sách data retention, export, delete, backup expiration và kiểm tra xóa không?
- Có subprocessor, luồng dữ liệu xuyên biên giới hoặc nghĩa vụ xử lý dữ liệu cá nhân cần được phê duyệt không?

**Bằng chứng:** data flow, data processing terms theo nghĩa vụ áp dụng, security architecture, key policy, mô tả tenant isolation và test summary.

### 5.4. Secure development, change và vulnerability management

- Hệ thống có security review khi thiết kế và thay đổi quan trọng không?
- Repository, CI/CD và artifact có kiểm soát quyền, secret scanning và review không?
- SAST, dependency scanning, image/container scanning hoặc kiểm thử phù hợp được áp trong scope nào?
- Có quy trình tiếp nhận, phân loại và khắc phục lỗ hổng với thời hạn theo rủi ro không?
- Critical/high findings được theo dõi đến khi retest, hay chỉ cập nhật ticket?
- Có quy trình kiểm soát thay đổi và rollback cho môi trường production không?

**Bằng chứng:** mô tả SDLC, policy vulnerability, kết quả scan đã tổng hợp, pen test scope và remediation summary, change approval mẫu.

### 5.5. Logging, monitoring và incident response

- Những sự kiện quan trọng nào được ghi nhận: authentication, admin action, data access, configuration change?
- Ai có thể sửa/xóa log, log lưu ở đâu, retention và kiểm soát tính toàn vẹn là gì?
- Có giám sát nguồn im lặng, mất log, sai lệch thời gian hoặc thay đổi hệ thống phát hiện không?
- Khi xảy ra incident ảnh hưởng dữ liệu/dịch vụ khách hàng, quy trình escalation và thông báo thế nào?
- Có diễn tập response, tabletop hoặc bài kiểm tra detection định kỳ trong phạm vi dịch vụ không?
- Đối với sự cố nghiêm trọng, có thể cung cấp bằng chứng phục vụ điều tra trong phạm vi pháp lý/hợp đồng không?

**Bằng chứng:** logging standard, alert test, incident playbook, bảng phân công, báo cáo diễn tập đã khử nhạy cảm, điều khoản hỗ trợ điều tra.

### 5.6. Business continuity, disaster recovery và resilience

- Các chức năng cốt lõi của dịch vụ có RTO/RPO theo BIA và kỳ vọng của khách hàng không?
- Dữ liệu và cấu hình nào được backup; tần suất, retention, mã hóa và quyền xóa được bảo vệ thế nào?
- Đã diễn tập restore/failover đầu cuối gần nhất vào thời điểm nào, trên phạm vi nào, kết quả đo ra sao?
- Có kế hoạch xử lý mất region, cloud account, IAM, KMS hoặc đối tác phụ thuộc không?
- Có quy trình đánh giá bản phục hồi không bị nhiễm mã độc hoặc dữ liệu corrupt không?
- Khi kết thúc sử dụng dịch vụ, có thể export dữ liệu ở định dạng thực tế sử dụng được không?

**Bằng chứng:** DR policy, RTO/RPO đã phê duyệt, mô tả dependency, test report có scope và kết quả, exit plan.

### 5.7. Subprocessor, chuỗi cung ứng và nhà thầu phụ

- Những đơn vị nào xử lý hoặc có quyền tiếp cận dữ liệu/dịch vụ trong scope?
- Nhà cung cấp đánh giá security/privacy của subprocessor trước và trong quá trình hợp tác thế nào?
- Có điều khoản truyền đạt yêu cầu bảo mật xuống subprocessor và quyền audit/incident notification tương ứng không?
- Khi thay subprocessor, khách hàng được thông báo hoặc có cơ chế đánh giá tác động theo hợp đồng không?
- Có phụ thuộc nào khiến dữ liệu hoặc dịch vụ bị mất khi một subprocessor ngừng hoạt động không?

**Bằng chứng:** subprocessor register phù hợp chia sẻ, mô tả data flow, chính sách third-party review, contractual flow-down summary, continuity plans.

## 6. Bộ câu hỏi mẫu có thể kiểm chứng

Bảng sau là **bộ khung minh họa** cho dịch vụ SaaS xử lý thông tin khách hàng. Mỗi câu có thể được mở rộng bằng scope, kỳ kiểm tra và follow-up; không nên sao chép nguyên trạng mà bỏ qua phân loại rủi ro.

| ID | Câu hỏi kiểm soát | Evidence cần xem | Phương pháp đánh giá |
|---|---|---|---|
| **TPQ-01** | Dịch vụ trong scope có owner an ninh, quản lý rủi ro và chính sách được phê duyệt không? | Policy, owner, kỳ review | Đối chiếu tên dịch vụ, phiên bản và scope |
| **TPQ-02** | Tài khoản quản trị production có MFA trên mọi đường đăng nhập tương tác? | Enforcement policy, redacted config | Kiểm tra ngoại lệ và phương thức bypass |
| **TPQ-03** | Quyền truy cập dữ liệu khách hàng có giới hạn và được review? | Role matrix, access review sample | Đối chiếu role và khả năng vendor support access |
| **TPQ-04** | API token/service identity được phân quyền và thu hồi theo vòng đời? | Key policy, sample lifecycle, log | Xác định scope, expiry, owner và revoke |
| **TPQ-05** | Dữ liệu trong scope được bảo vệ khi truyền và lưu? | Data-flow, encryption design, key policy | Kiểm tra vị trí xử lý và key responsibility |
| **TPQ-06** | Tenant isolation có control và kiểm thử phù hợp? | Architecture, isolation test summary | Xem mức cô lập đối với loại dữ liệu được xử lý |
| **TPQ-07** | Có quy trình quản lý lỗ hổng và thời hạn khắc phục theo risk? | Vulnerability policy, dashboard summary | Kiểm tra tồn đọng, ngoại lệ và bằng chứng retest |
| **TPQ-08** | Thay đổi production được review, có trace và rollback? | Change workflow, sample records | Kiểm tra đường thay ngoài pipeline |
| **TPQ-09** | Sự kiện admin, authentication và data access quan trọng được ghi và bảo quản? | Logging standard, event sample đã khử nhạy cảm | Kiểm tra coverage, retention và quyền xóa |
| **TPQ-10** | Có năng lực xử lý sự cố và thông báo ảnh hưởng đến khách hàng? | IR plan, communication flow, exercise | Kiểm tra trigger, owner, nghĩa vụ trong hợp đồng |
| **TPQ-11** | Backup/DR được diễn tập với tiêu chí dịch vụ và dữ liệu? | Restore/failover report, RTO/RPO | Xem T0/T1, data reconciliation và giới hạn test |
| **TPQ-12** | Subprocessor trong scope được quản lý và cập nhật? | Subprocessor list, review approach | Đối chiếu data flow và điều khoản thay đổi |
| **TPQ-13** | Đơn vị có phương án export, trả/xóa dữ liệu và thu hồi quyền sau hợp đồng? | Exit procedure, retention/deletion terms | Kiểm tra tính khả thi, backup copies và nghĩa vụ lưu |
| **TPQ-14** | Tài sản xử lý dữ liệu được quản lý bản vá và cấu hình baseline? | Asset inventory summary, patch/benchmark results | Kiểm tra hệ thống nằm trong scope và ngoại lệ |
| **TPQ-15** | Có đánh giá độc lập liên quan trực tiếp đến dịch vụ hoặc control quan trọng? | SOC 2, chứng nhận có scope, test summaries | Kiểm tra kỳ, đối tượng, exceptions, carve-out |
| **TPQ-16** | Có quy trình phản ứng khi key/credential quản trị hoặc hệ thống log bị xâm phạm? | IR playbook, IAM/key recovery design | Kiểm tra biện pháp thu hồi, nguồn bằng chứng độc lập |
| **TPQ-17** | Có đánh giá thay đổi về vùng dữ liệu, subprocessor hoặc kiến trúc quan trọng? | Change governance, notification terms | Kiểm tra trigger đánh giá và thông báo |
| **TPQ-18** | Có theo dõi finding/ngoại lệ cho đến khi đã xác minh hiệu lực khắc phục? | Risk/finding register summary, retest evidence | Phân biệt “ticket Done” với control PASS |

### 6.1. Ví dụ cách hỏi sâu theo câu trả lời

Với **TPQ-11 — Disaster recovery**:

- **YES:** cung cấp bản diễn tập gần nhất, dịch vụ nào được kiểm, failure scenario, target RTO/RPO, số đo đạt được, tiêu chí dữ liệu và security gate. Nếu chỉ có tabletop, không kết luận restore đã được chứng minh.
- **PARTIAL:** nêu database nào đã restore nhưng API/message broker chưa được kiểm; kế hoạch và hạn diễn tập đầu cuối.
- **NO:** xác định ảnh hưởng business continuity, biện pháp thay thế và thẩm quyền chấp nhận rủi ro.
- **NOT_APPLICABLE:** yêu cầu giải thích vì sao dịch vụ không có nhu cầu phục hồi; phải đối chiếu với criticality và BIA của bên sử dụng.
- **UNKNOWN:** yêu cầu người chịu trách nhiệm, thời hạn cung cấp và kết luận tạm thời INCONCLUSIVE.

Ví dụ này cho thấy **cùng một câu hỏi** có thể sinh ra những đường kiểm chứng rất khác nhau. Không nên để logic xử lý các câu trả lời ngoài YES biến mất khỏi quy trình đánh giá.

## 7. Bằng chứng: điều kiện để chuyển câu trả lời thành assurance

Bằng chứng phải **liên quan trực tiếp đến assertion**, đáng tin về nguồn, đủ phạm vi và đủ mới cho kỳ đánh giá. Không phải mọi loại evidence đều chứng minh mức hiệu lực giống nhau.

### 7.1. Các cấp độ bằng chứng

| Loại bằng chứng | Có thể giúp chứng minh | Giới hạn thường gặp |
|---|---|---|
| **Self-attestation** | Mô tả control và cam kết trách nhiệm từ nhà cung cấp | Không phải xác minh độc lập; có thể bỏ qua ngoại lệ |
| **Policy/procedure** | Control được thiết kế và được tổ chức phê duyệt | Chưa chứng minh hệ thống thực sự áp dụng và người dùng tuân theo |
| **Architecture/design** | Ranh giới dữ liệu, cơ chế và trách nhiệm dự kiến | Có thể không khớp cấu hình production hoặc đã thay đổi |
| **Configuration export** | Thiết lập có hiệu lực trong một hệ thống ở một thời điểm | Không chứng minh mọi tài khoản/region có cùng thiết lập |
| **Operational record** | Access review, change approval, log, incident/drill record | Cần kiểm tra mẫu, nguồn, tính toàn vẹn và kỳ đánh giá |
| **Test result / retest** | Control được thực hiện và đã cho kết quả với test case cụ thể | Chỉ đại diện cho tình huống, thời điểm, dữ liệu và scope đã thử |
| **Independent assurance report** | Đánh giá bởi bên độc lập theo tiêu chí, phạm vi và kỳ cụ thể | Có thể có ngoại lệ, loại trừ hoặc nằm ngoài dịch vụ cần mua |
| **Live demonstration / interview** | Làm rõ quy trình, khả năng thực hiện và cách vận hành | Một lần demo không đủ chứng minh control được duy trì liên tục |

Bằng chứng càng “độc lập” chưa chắc càng “phù hợp”: một chứng nhận ở trụ sở công ty có thể không bao phủ dịch vụ SaaS mà khách hàng định sử dụng. Ngược lại, một bản cấu hình truy cập production đúng service và thời điểm có thể là minh chứng trực tiếp mạnh cho assertion hẹp, nhưng vẫn cần xem độ bao phủ và khả năng sửa cấu hình.

### 7.2. Sáu chiều kiểm tra bằng chứng

1. **Relevance (liên quan):** tài liệu chứng minh đúng control, rủi ro và câu hỏi hay chỉ là một tuyên bố chung?
2. **Scope (phạm vi):** đúng pháp nhân, sản phẩm, environment, region, hệ thống, subprocessor và nhóm người dùng?
3. **Time (thời gian):** kỳ vận hành và ngày chốt của evidence có bao phủ thời điểm ra quyết định? Có thay đổi trọng yếu sau đó?
4. **Authenticity/integrity (nguồn và tính toàn vẹn):** ai phát hành, có thể truy lại bản gốc, phiên bản, chữ ký hoặc cách xác minh hợp lý không?
5. **Completeness (đầy đủ):** có ngoại lệ, hệ thống bị loại trừ, kiểm soát bổ sung của khách hàng, dữ liệu thiếu hoặc khoảng không được quan sát?
6. **Operating effectiveness (hiệu lực):** chỉ có thiết kế/chính sách hay có dấu vết control được vận hành, kiểm thử và khắc phục finding?

Bằng chứng nên gắn với **assessment cutoff**. Tài liệu lập từ năm trước không tự động sai, nhưng khi một đội vừa thay kiến trúc, quyền hoặc nhà cung cấp hạ tầng, nó có thể không còn đủ để kết luận trạng thái hiện tại.

### 7.3. Đọc báo cáo và chứng nhận mà không suy rộng

**SOC 2:** báo cáo Type I thường xem mô tả hệ thống và thiết kế kiểm soát tại một thời điểm; Type II bao gồm đánh giá hoạt động của kiểm soát trong một kỳ báo cáo. Khi xem báo cáo cần kiểm tra dịch vụ/hệ thống nằm trong scope, trust services criteria áp dụng, kỳ kiểm tra, ngoại lệ, ý kiến kiểm toán, carve-out/inclusive approach đối với subservice organizations và những **complementary user entity controls** mà khách hàng cần tự thực hiện. Một báo cáo không phải tuyên bố rằng mọi control ở mọi thời điểm đều đạt.

**ISO/IEC 27001:** chứng nhận liên quan đến hệ thống quản lý an toàn thông tin (**ISMS**) trong phạm vi được chứng nhận. Phải xem pháp nhân, địa điểm, hoạt động, sản phẩm/dịch vụ và thời hạn áp dụng. Chứng nhận không có nghĩa mỗi thành phần phần mềm đều không có lỗ hổng. Có thể hỏi thêm phạm vi ISMS, nội dung liên quan trong Statement of Applicability hoặc bằng chứng control phù hợp mà nhà cung cấp có thể chia sẻ.

**Penetration test:** xem phạm vi (ứng dụng/API/cloud/tenant isolation), ngày thực hiện, phương pháp ở mức cần thiết, các findings theo mức rủi ro và tình trạng remediation/retest. Một “executive letter” chỉ ghi “đã pentest” không chứng minh tất cả critical findings được xử lý, nhưng cũng không nhất thiết cần yêu cầu raw exploit chain chứa dữ liệu nhạy cảm.

**Vulnerability scanner report:** đánh giá nguồn asset, mức bao phủ, ngày scan, logic loại trừ, tuổi của finding, exception và cách xử lý. Điểm “không có critical vulnerability” không chứng minh không còn lỗi ứng dụng hoặc chưa có CVE mới xuất hiện sau kỳ quét.

**DR exercise report:** đối chiếu RTO/RPO được phê duyệt, failure scenario, service/dependency, điểm dữ liệu nhất quán và mốc kết thúc. Tabletop không chứng minh phục hồi đầu cuối.

**Bridge/gap period:** nếu báo cáo độc lập kết thúc trước thời điểm đánh giá, yêu cầu giải thích các thay đổi trọng yếu và tình trạng control trong khoảng chưa được bao phủ; không tự xem một thư cam kết của management tương đương kiểm toán độc lập.

### 7.4. Tài liệu quá nhạy cảm thì làm gì?

Không nên buộc nhà cung cấp chuyển private keys, database dumps, danh sách tài khoản thật, kết quả pentest chi tiết chưa được hạn chế hoặc network diagrams có thể tạo rủi ro nếu bị lộ.

Các lựa chọn thay thế phù hợp:

- Yêu cầu **bản redacted** giữ được các trường chứng minh assertion (scope, thời gian, trạng thái và kết quả).
- Review có giám sát trong portal bảo mật hoặc phòng dữ liệu có kiểm soát, ghi nhận **đã xem gì** và kết luận, không sao chép tài liệu nhạy cảm.
- Dùng **report summary có provenance**, thư xác nhận của auditor hoặc excerpt hợp lệ.
- Thực hiện demonstration trên tài khoản hoặc dữ liệu test được phê duyệt.
- Bổ sung điều khoản bảo mật/NDA và giới hạn thời gian truy cập cho evaluator.
- Khi không thể thu evidence đủ mạnh, đánh dấu **INCONCLUSIVE** hoặc residual risk và quyết định theo thẩm quyền, không tự chuyển thành PASS.

### 7.5. Evidence register

~~~yaml
evidence_id: "TP-EV-2026-044"
vendor_id: "vendor-example-17"
service_id: "support-saas"
assessment_id: "TP-ASS-2026-009"
question_id: "TPQ-02"
type: "redacted-configuration-export"
issued_by: "vendor-security-team"
reviewed_at: "2026-11-28T08:30:00Z"
evidence_as_of: "2026-11-25T00:00:00Z"
scope:
  environment: "production"
  systems: ["privileged-identity-platform"]
  excluded: ["legacy-break-glass-local-account"]
reference: "secure-evidence-store/vendor17/mfa-review"
limitations:
  - "Chưa có kiểm thử đường break-glass local"
  - "Export chỉ thể hiện thời điểm được nêu"
review_result: "PARTIAL_COVERAGE"
reviewer_role: "third-party-security-assessor"
~~~

Đây là **dữ liệu giả định**. Bản ghi quan trọng ở chỗ phân biệt evidence thật có thể truy xuất với mô tả, đồng thời không giấu phần bị loại trừ.

## 8. Quy trình đánh giá questionnaire từ đầu đến cuối

### 8.1. Các bước chính

1. **Intake:** bộ phận sử dụng mô tả nhà cung cấp, dịch vụ, data flow, tích hợp, kỳ vọng và business owner.
2. **Risk triage:** xác định criticality, quyền, dữ liệu, phụ thuộc và yêu cầu pháp lý/hợp đồng áp dụng.
3. **Scope agreement:** thống nhất pháp nhân, service, region, environment và shared responsibility.
4. **Questionnaire selection:** chọn baseline, nhánh điều kiện và control trọng yếu; sử dụng câu hỏi đã có nếu vẫn phù hợp.
5. **Evidence request:** gửi bộ câu hỏi có hướng dẫn định dạng, mốc chốt, mức nhạy cảm và kênh nộp an toàn.
6. **Supplier response:** nhà cung cấp trả lời, giải thích phạm vi, đính kèm evidence và công bố ngoại lệ.
7. **Assurance review:** kiểm tra câu trả lời, kiểm chứng evidence và đối chiếu với control objective.
8. **Follow-up:** hỏi lại dữ liệu không nhất quán, yêu cầu bằng chứng bổ sung hoặc buổi walkthrough trong phạm vi được phép.
9. **Risk decision:** đánh giá finding và residual risk, chọn approve, conditional approval, defer hoặc reject theo thẩm quyền.
10. **Contract/onboarding gate:** đưa nghĩa vụ đã thống nhất vào hợp đồng/điều khoản, cấu hình quyền và giới hạn dữ liệu trước go-live.
11. **Monitoring/reassessment:** theo dõi finding, thay đổi, incident, kỳ đánh giá và exit controls.

~~~mermaid
flowchart TB
    IN["Intake dịch vụ / dữ liệu"] --> TIER["Risk tier và scope"]
    TIER --> Q["Chọn questionnaire"]
    Q --> ANS["Vendor trả lời + evidence"]
    ANS --> REVIEW["Assessor kiểm chứng"]
    REVIEW --> GAP{"Khoảng trống?"}
    GAP -- "Không" --> APPROVE["Approve trong scope"]
    GAP -- "Có" --> REM["Finding + remediation/compensation"]
    REM --> DEC["Risk owner phê duyệt có điều kiện, hoãn hoặc từ chối"]
    APPROVE --> GATE["Contract + onboarding"]
    DEC --> GATE
    GATE --> MON["Monitoring + retest + reassessment"]
    MON --> TIER
~~~

**Không được hiểu mọi quyết định có điều kiện đều cho phép go-live.** Những critical blockers phải được giải quyết trước khi cấp truy cập hoặc dữ liệu; nếu tổ chức chấp nhận ngoại lệ, đó phải là quyết định được phê duyệt theo chính sách và giới hạn cụ thể.

### 8.2. Vai trò và phân tách trách nhiệm

| Vai trò | Trách nhiệm |
|---|---|
| **Business/service owner** | Giải thích nhu cầu, tác động khi ngừng dịch vụ, quyền và dữ liệu cần thiết |
| **Vendor relationship/procurement** | Xác định pháp nhân, hợp đồng, liên hệ và thay đổi dịch vụ |
| **Third-party security assessor** | Thiết kế scope/questionnaire, kiểm chứng bằng chứng, lập finding |
| **Privacy/legal/compliance** | Đánh giá nghĩa vụ dữ liệu, hợp đồng, thông báo và quyền liên quan theo phạm vi |
| **Architecture/platform/identity** | Đánh giá kết nối, quyền, logging, shared responsibility và kiểm soát tại phía khách hàng |
| **Vendor control owner** | Cung cấp thông tin chính xác, bằng chứng, owner và kế hoạch sửa phía nhà cung cấp |
| **Risk owner/approver** | Quyết định xử lý residual risk trong quyền hạn, có thời hạn và điều kiện |
| **Monitoring/audit** | Theo dõi kỳ reassessment, ngoại lệ, bằng chứng và retest |

Người mua dịch vụ có thể yêu cầu quyết định nhanh, nhưng không nên đồng thời tự xác minh mọi control và phê duyệt một ngoại lệ rủi ro cao mà không qua quy trình phù hợp.

## 9. Đánh giá câu trả lời và quyết định theo rủi ro

### 9.1. Tách ba kết quả khác nhau

Bộ hồ sơ nên có ba trục:

1. **Vendor response:** YES/PARTIAL/NO/NOT_APPLICABLE/UNKNOWN.
2. **Assurance verdict:** PASS/FAIL/INCONCLUSIVE/NOT_TESTED/NOT_APPLICABLE, với scope, evidence, độ tin cậy.
3. **Risk decision:** APPROVED/APPROVED_WITH_CONDITIONS/DEFERRED/REJECTED hoặc ACCEPTED_RISK theo quy định.

Ví dụ:

| Vendor response | Assessor kết luận | Risk decision có thể xảy ra |
|---|---|---|
| YES, evidence đủ scope và hiệu lực | PASS_WITH_SCOPE | Approved nếu các control bắt buộc khác đạt |
| YES, tài liệu chỉ là chính sách không có dấu vết vận hành | INCONCLUSIVE | Yêu cầu evidence bổ sung; có thể defer |
| PARTIAL, thiếu MFA cho một đường admin | FAIL cho assertion “mọi đường” | Blocker hoặc conditional với biện pháp bù trừ được phê duyệt |
| NO, không có DR test | FAIL nếu DR test là yêu cầu | Hoãn go-live hoặc xử lý rủi ro theo thẩm quyền |
| NOT_APPLICABLE với lý do không phù hợp thực tế | FAIL/INCONCLUSIVE | Yêu cầu giải thích, cập nhật phạm vi |
| UNKNOWN do chưa biết cấu hình | INCONCLUSIVE | Không xem như đã đạt; tiếp tục điều tra |

### 9.2. Cẩn trọng với chấm điểm

Một cách gắn nhãn chất lượng evidence nội bộ:

| Mức | Ví dụ |
|---|---|
| **E0 — Unsubstantiated** | Chỉ có Yes/No, không có giải thích hoặc không đúng scope |
| **E1 — Described** | Có policy, thiết kế hoặc lời giải thích rõ nhưng chưa có bằng chứng vận hành |
| **E2 — Observed** | Có configuration/operational evidence đúng scope và thời điểm |
| **E3 — Validated** | Có đánh giá độc lập hoặc test phù hợp, minh chứng đã kiểm chứng, kèm xử lý ngoại lệ |

Đây **không phải chuẩn ngành** và không nên cộng các mức này rồi suy ra “độ an toàn 90%”. Nguồn độc lập có thể thiếu scope; một test đạt cho một account không đại diện toàn bộ tenant. Mức tin cậy phải được ghi theo assertion, không tự động gán cho toàn vendor.

### 9.3. Critical gate và severity

Không nên dùng trung bình số học để bù một thiếu sót nghiêm trọng bằng nhiều câu trả lời tốt. Ví dụ, 17/18 câu hỏi YES không thể làm mất rủi ro khi câu còn lại là **nhà cung cấp có quyền quản trị production nhưng không có MFA hoặc giám sát truy cập**.

Một quy trình quyết định phù hợp:

1. Phân loại control trọng yếu theo loại dữ liệu, đặc quyền và nghiệp vụ.
2. Xác minh những control đó có bằng chứng đạt.
3. Nếu không đạt, xác định đường giảm rủi ro: khắc phục trước go-live, giới hạn phạm vi, kiểm soát bù trừ, chấp nhận có điều kiện hoặc từ chối.
4. Những control không trọng yếu cũng phải có finding và owner nhưng có thể có kế hoạch sau onboarding theo rủi ro.
5. Quyết định ghi được **người phê duyệt, phạm vi, thời hạn và điều kiện thu hồi**.

### 9.4. Trạng thái chưa biết không phải rủi ro bằng không

Nhà cung cấp có thể không chia sẻ evidence do NDA hoặc không đủ khả năng tạo báo cáo theo mẫu. Khi đó, kết luận nên là **không đủ bằng chứng**. Risk owner cân nhắc tác động của sự bất định, yêu cầu phương án xác minh thay thế hoặc giới hạn dữ liệu/quyền trong kỳ chờ.

Không nên tự động chuyển UNKNOWN thành NO rồi “phạt điểm” như đã xác nhận thiếu control. Cũng không được biến UNKNOWN thành YES chỉ vì vendor có thương hiệu lớn.

## 10. Shared responsibility và các nghĩa vụ cần đối chiếu

### 10.1. Câu trả lời của vendor không thay trách nhiệm khách hàng

Nhà cung cấp có thể bảo vệ hạ tầng SaaS rất tốt, nhưng khách hàng vẫn cần cấu hình IdP/SSO, người dùng, role, dữ liệu được đưa vào SaaS và tài khoản API. Một câu hỏi quá chung sẽ làm mờ các phần đó.

Ví dụ trách nhiệm theo một dịch vụ SaaS giả định:

| Control | Vendor phụ trách | Customer phụ trách | Phép kiểm tích hợp |
|---|---|---|---|
| Platform patching | Patch OS/runtime và dịch vụ của vendor | Không áp cho SaaS core nếu không quản trị được | Vendor patch evidence và scope |
| SSO integration | Hỗ trợ protocol và enforcement theo thiết kế | Cấu hình IdP, phân nhóm user, yêu cầu MFA của tổ chức | Test đăng nhập user/admin và đường bypass |
| Role/access | Cung cấp RBAC và audit | Cấp role theo nhu cầu, review user của khách hàng | Test quyền và định kỳ review |
| Encryption at rest | Cơ chế mã hóa phía vendor trong scope | Quản lý customer key nếu dịch vụ hỗ trợ và đã lựa chọn | Kiểm tra key responsibility, quyền và luồng dữ liệu |
| Audit logging | Sinh và giữ log nền tảng theo tính năng cam kết | Bật export/retention tại tenant nếu là lựa chọn cấu hình | Event test từ tenant đến hệ thống giám sát |
| Backup/DR | Phục hồi nền tảng của vendor trong phạm vi cam kết | Export/backup dữ liệu riêng nếu hợp đồng yêu cầu | So sánh RTO/RPO với BIA và restore test |
| Incident communication | Thông báo và hỗ trợ theo điều khoản | Liên hệ, phản ứng bên trong, nghĩa vụ tiếp theo với khách hàng | Diễn tập contact/escalation |
| Data deletion | Xóa theo điều khoản và phạm vi bản sao do vendor kiểm soát | Gỡ tích hợp, thu hồi API key, xử lý bản dữ liệu đã export | Exit checklist, confirmation và hạn chế retention |

Bảng trên là **mẫu minh họa**, không khẳng định mọi SaaS có trách nhiệm phân chia giống nhau. Cần đối chiếu hợp đồng và kiến trúc thật.

### 10.2. Điểm mù về subprocessor

Một vendor có thể trả lời “chúng tôi lưu dữ liệu ở region X”, trong khi dịch vụ gửi email hoặc analytics có thể chuyển một phần dữ liệu sang subprocessor. Cần hỏi:

- Subprocessor nào nhận loại dữ liệu gì?
- Dữ liệu được lưu, xử lý hoặc truy cập từ region nào, theo điều kiện nào?
- Nhà cung cấp chính có đánh giá và truyền nghĩa vụ bảo mật xuống đối tác phụ không?
- Khách hàng có được thông báo thay đổi danh sách subprocessor theo hợp đồng không?
- Khi subprocessor xảy ra incident, đường thông báo và quyền điều tra có đáp ứng yêu cầu không?

Câu hỏi về nơi lưu dữ liệu phải phân biệt **primary storage**, **backup**, **support access**, **telemetry** và **subprocessor processing** để tránh trả lời sai phạm vi.

## 11. Tình huống thực tế: đánh giá một SaaS hỗ trợ khách hàng

Một doanh nghiệp giả định muốn mua dịch vụ **HelpDeskCloud** để xử lý ticket hỗ trợ. SaaS sẽ nhận tên, email, nội dung hỗ trợ và một số thông tin giao dịch; tích hợp với IdP của doanh nghiệp và API quản lý đơn hàng có quyền đọc giới hạn. Dịch vụ được coi là **high risk** do xử lý dữ liệu khách hàng và có tác động nếu gián đoạn lâu.

### 11.1. Câu trả lời ban đầu

Nhà cung cấp nộp questionnaire 18 câu; phần lớn được đánh YES. Các tài liệu gồm một báo cáo kiểm toán độc lập, bản chứng nhận phạm vi doanh nghiệp, chính sách MFA, mô tả DR và danh sách subprocessors.

Khi kiểm tra sâu, đội assurance phát hiện:

| Chủ đề | Câu trả lời vendor | Bằng chứng thực tế | Kết luận |
|---|---|---|---|
| MFA admin | YES | MFA áp cho admin qua SSO, nhưng có tài khoản local break-glass chưa chứng minh enforce | **INCONCLUSIVE/FAIL** tùy assertion và quyền đường local |
| Audit log | YES | Có log admin 30 ngày; hợp đồng dự kiến cần truy xuất 90 ngày cho một nhóm sự kiện | **FAIL** theo yêu cầu retention đang xem xét |
| DR | YES | Có tabletop sáu tháng trước, chưa có restore test đầu cuối cho dịch vụ đang mua | **INCONCLUSIVE** về RTO/RPO đã đạt |
| Independent audit | YES | Report liên quan nền tảng vendor, nhưng chức năng add-on tích hợp API nằm ngoài scope | **PASS_WITH_SCOPE** cho phần report bao phủ; add-on chưa đủ chứng cứ |
| Subprocessors | YES | Mới sử dụng dịch vụ email khác, chưa cập nhật danh sách nộp cho khách hàng | **Finding** về inventory/thông báo thay đổi |
| Vulnerability management | YES | Chính sách có thời hạn xử lý, cung cấp remediation summary cho findings thuộc scope | **PASS_WITH_SCOPE** nếu kỳ và scope phù hợp |

Không nên tuyên bố “vendor bảo mật kém” dựa trên một bảng thiếu thông tin. Cần phân biệt **control chưa đạt** với **control chưa có đủ bằng chứng** và gắn từng tình huống với tác động cụ thể.

### 11.2. Câu hỏi bổ sung

Đội assurance yêu cầu:

1. **MFA:** xác nhận có đường local admin thực sự truy cập production hay chỉ dùng cho khôi phục, enforcement hiện tại, approval/break-glass log và quyền hiệu lực.
2. **Retention:** xác định khả năng cấu hình xuất log sang hệ thống khách hàng hoặc kéo dài retention, ai chịu chi phí và trách nhiệm.
3. **DR:** cung cấp kết quả restore test theo scope phù hợp, target/achieved RTO/RPO, điểm dữ liệu nhất quán và kế hoạch xử lý finding.
4. **Audit scope:** xác định add-on API chịu control nào và có test bảo mật nào trực tiếp cho add-on.
5. **Subprocessor:** danh sách cập nhật, loại dữ liệu chuyển, điều khoản và quy trình thông báo thay đổi.

Nếu một thiếu sót liên quan **critical gate**, quyết định có thể là hoãn kết nối production dù questionnaire gần như hoàn tất.

### 11.3. Action register và quyết định có điều kiện

| Finding | Rủi ro | Hành động đề xuất | Owner | Điều kiện đóng |
|---|---|---|---|---|
| **TP-F01: local admin** | Bypass xác thực mạnh vào production | Bật MFA/PAM hoặc khóa đường local không cần thiết, giám sát break-glass | Vendor IAM owner | Effective policy + controlled verification |
| **TP-F02: audit retention** | Thiếu dấu vết điều tra trong kỳ bắt buộc | Cấu hình export/retention và quyền đối soát | Vendor + customer security | Test event + truy xuất và retention policy |
| **TP-F03: DR test** | RTO/RPO chưa được chứng minh | Diễn tập restore theo scope dịch vụ và dependency | Vendor resilience owner | Test report có T0/T1/data check |
| **TP-F04: add-on scope** | Chức năng API không được báo cáo audit bao phủ | Test API/architecture review hoặc evidence thay thế | Vendor engineering | Evidence phù hợp scope và xử lý finding |
| **TP-F05: subprocessor** | Dữ liệu chuyển cho bên phụ chưa được đánh giá | Cập nhật registry và flow-down controls | Vendor privacy/TPRM | Approved list + obligations review |

Giả định risk owner chỉ cho phép **sandbox không có dữ liệu khách hàng thật** trong khi TP-F01 và TP-F02 chưa khắc phục. Khi đã có bằng chứng đối với hai critical gates, tổ chức có thể xem xét go-live giới hạn; TP-F03/F04/F05 được quản lý theo điều kiện, hạn và kiểm soát bù trừ nếu chính sách cho phép.

Đây là một ví dụ về **quyết định phân tầng**, không phải hướng dẫn tự động cho phép một vendor có điểm thiếu quan trọng đi vào production.

### 11.4. Đọc kết quả đúng nghĩa

Một số kết luận:

- “18 câu đã trả lời” là tiến độ hoàn thành bảng hỏi.
- “13 câu có evidence được chấp nhận” thể hiện số assertion được xác minh trong scope đó.
- “2 critical gates chưa đạt” là thông tin quyết định go-live cần ưu tiên, dù tỷ lệ tổng có thể cao.
- “Vendor được thử ở sandbox” là quyết định hạn chế, không phải phê duyệt xử lý dữ liệu nhạy cảm trong production.
- “Finding đã sửa” chỉ có giá trị khi được **retest** hoặc kiểm chứng trên cấu hình đúng phạm vi.

Một questionnaire có ích nhất khi giúp tổ chức **giới hạn rủi ro trong quá trình ra quyết định**, không chỉ tạo điểm xếp hạng vendor.

## 12. Mẫu hồ sơ questionnaire và kết quả assurance

### 12.1. Phân biệt hồ sơ câu hỏi, câu trả lời và kết luận

Một hệ thống quản lý questionnaire nên có các thực thể tách biệt:

- **Question template:** ID, phiên bản, domain, control objective, applicability, evidence expectation.
- **Assessment:** vendor, service, scope, risk tier, kỳ, người phụ trách, mốc chốt.
- **Response:** người trả lời, trạng thái, giải thích, ngoại lệ, ngày trả lời, reference.
- **Evidence:** artifact ID, nguồn, phạm vi, kỳ, nơi lưu an toàn, người đã xem.
- **Reviewer observation:** điều kiểm được, điều chưa đủ, confidence, câu hỏi cần tiếp tục.
- **Finding:** assertion chưa đạt, tác động, owner, thời hạn, hành động và kết quả kiểm lại.
- **Decision:** authority, điều kiện cấp quyền/dữ liệu, residual risk, thời gian hiệu lực và trigger đánh giá lại.

Việc tách riêng giúp tránh lỗi phổ biến: vendor thay câu trả lời YES sau khi sửa control rồi hệ thống vô tình ghi đè bằng chứng cho thấy trước đó từng có finding.

### 12.2. Hồ sơ assessment hoàn chỉnh — ví dụ YAML

~~~yaml
assessment_id: "TP-ASS-2026-009"
service:
  vendor_id: "vendor-example-17"
  name: "Customer-support SaaS"
  environments_in_scope:
    - "production"
  processing:
    data_classes: ["customer-contact", "support-ticket"]
    customer_api_access: "read-only"
  hosting_regions: ["region-example-a"]
  business_criticality: "HIGH"
assessment:
  type: "initial-onboarding"
  risk_tier: "HIGH"
  questionnaire_version: "tpq-baseline-v3"
  started_at: "2026-11-20T00:00:00Z"
  cutoff_at: "2026-11-28T09:00:00Z"
  business_owner: "customer-support-owner"
  security_reviewer: "third-party-assurance-team"
responses:
  - question_id: "TPQ-02"
    vendor_response: "PARTIAL"
    vendor_explanation: >
      MFA applies to SSO admins; emergency local access
      has a documented exception.
    evidence_refs: ["TP-EV-2026-044"]
    assurance_verdict: "FAIL"
    scope_limitation: "Emergency local admin access"
    finding_id: "TP-F01"
  - question_id: "TPQ-11"
    vendor_response: "YES"
    vendor_explanation: "DR runbook reviewed in tabletop"
    evidence_refs: ["TP-EV-2026-052"]
    assurance_verdict: "INCONCLUSIVE"
    scope_limitation: "No end-to-end restore demonstration"
    finding_id: "TP-F03"
decision:
  status: "DEFER_PRODUCTION"
  allowed_interim_scope: "sandbox-with-synthetic-data-only"
  authority: "designated-third-party-risk-owner"
  decision_at: "2026-11-28T10:00:00Z"
  conditions:
    - "Resolve TP-F01 before production privileged access"
    - "Validate logging and retention for customer-data scope"
  next_review_on: "2026-12-15"
  change_triggers:
    - "new-subprocessor"
    - "privileged-access-change"
    - "security-incident"
evidence_store: "restricted-tprm-repository"
~~~

Đây là **mẫu dữ liệu giả định**. Vendor response, verdict và risk decision là ba lớp khác nhau. Một vendor có thể trả YES cho DR vì có tabletop, còn assessor vẫn INCONCLUSIVE đối với yêu cầu kiểm thử phục hồi đầu cuối. Dữ liệu thực phải dùng ID, thời hạn, scope, nhà cung cấp và phê duyệt đã xác minh.

### 12.3. Liên kết requirement → question → evidence → finding

Ví dụ chuỗi truy vết:

~~~mermaid
flowchart TD
    R["Yêu cầu: production admin không dùng xác thực yếu"] --> C["Control: MFA trên mọi đường admin tương tác"]
    C --> Q["TPQ-02: câu hỏi và scope"]
    Q --> A["Vendor response: PARTIAL"]
    A --> E["Evidence: SSO MFA + đường local ngoại lệ"]
    E --> V["Assurance verdict: FAIL cho assertion toàn phạm vi"]
    V --> F["TP-F01: finding và rủi ro"]
    F --> ACT["Remediation: sửa đường local/PAM"]
    ACT --> TEST["Retest effective auth controls"]
    TEST --> DEC["Risk owner review quyết định"]
~~~

Đường truy vết như vậy hỗ trợ audit: người kiểm tra có thể biết quyết định cuối được đưa ra từ bằng chứng nào và tìm đúng artifact khi kiểm tra lại.

### 12.4. Versioning và tính toàn vẹn hồ sơ

Không nên ghi đè lặng lẽ câu trả lời, file evidence hoặc decision cũ. Khi vendor nộp evidence mới:

1. Đánh dấu phiên bản/cutoff của assessment hiện hành.
2. Lưu artifact mới cùng metadata nguồn và ngày có hiệu lực.
3. Ghi assessment observation nào được cập nhật.
4. Retest assertion liên quan; giữ kết quả cũ như lịch sử.
5. Đưa decision mới cho người có thẩm quyền nếu thay đổi residual risk.
6. Ghi sự kiện thay đổi vào audit trail và thông báo stakeholder liên quan.

Chính sách retention và phân quyền đối với questionnaire phải phù hợp mức nhạy cảm. Không cần giữ vô thời hạn các report bảo mật của vendor nếu không có mục đích/nghĩa vụ phù hợp.

## 13. Hợp đồng và điều kiện onboarding

### 13.1. Chuyển requirement thành nghĩa vụ có thể thực thi

Questionnaire là công cụ đánh giá và giao tiếp; nhưng một số yêu cầu cần được quy định tại hợp đồng, phụ lục bảo mật hoặc mô hình trách nhiệm giữa các bên. Những điều khoản thường cần xem xét, tùy luật và loại dịch vụ:

- **Bảo vệ dữ liệu:** mục đích, loại dữ liệu, quyền xử lý, nơi xử lý, phân quyền và quy tắc xóa/hoàn trả.
- **Security baseline:** các control bắt buộc cho service, ngoại lệ và nghĩa vụ duy trì.
- **Incident notification:** định nghĩa sự cố cần thông báo, người nhận, kênh, thời hạn và loại thông tin cần cung cấp theo nghĩa vụ áp dụng.
- **Audit/assurance:** loại bằng chứng định kỳ, báo cáo độc lập có thể chia sẻ, cơ chế xác minh thay thế và bảo vệ bí mật.
- **Subprocessor:** điều kiện dùng bên xử lý phụ, thông báo thay đổi, trách nhiệm tiếp nối và xử lý phản đối theo thỏa thuận.
- **Vulnerability management:** trách nhiệm khắc phục, phối hợp disclosure và thông báo thay đổi ảnh hưởng khách hàng.
- **Resilience:** chỉ tiêu dịch vụ, dữ liệu, continuity, RTO/RPO hoặc các điều kiện phục hồi đã được thống nhất.
- **Exit/transition:** export dữ liệu, thu hồi quyền, xóa bản sao và hỗ trợ chuyển nhà cung cấp trong phạm vi khả thi.

Điều khoản phải **phù hợp với dịch vụ đã thỏa thuận**, không sao chép mơ hồ “vendor sẽ bảo mật tuyệt đối”. Các vấn đề pháp lý, quyền riêng tư hoặc ngành đặc thù cần được chuyên gia có thẩm quyền rà soát, không suy ra từ bảng hỏi.

### 13.2. Phê duyệt onboarding không chỉ là ký hợp đồng

Trước khi cấp quyền hoặc dữ liệu production, nên kiểm tra những điều kiện thực thi phía khách hàng:

| Điều kiện | Ví dụ phép kiểm |
|---|---|
| SSO/identity | Người dùng và admin đăng nhập đúng IdP, không có đường bypass ngoài scope |
| Least privilege | API key/role giới hạn đúng hành động và tài nguyên, có test deny |
| Data minimization | Chỉ trường dữ liệu cần thiết được chuyển sang vendor |
| Network integration | Endpoint/egress, webhook verification, certificate và logging đúng thiết kế |
| Log/audit | Event test xuất hiện ở nơi giám sát với thời điểm và actor đúng |
| Contract obligations | Điều khoản quan trọng đã được phê duyệt và lưu đúng version |
| Finding gate | Critical blockers đã xử lý hoặc có quyết định rủi ro trong quyền hạn được cấp |
| Owner/contacts | Có owner dịch vụ, hỗ trợ, incident channel và escalation |
| Exit readiness | Biết cách export/xóa dữ liệu, thu hồi token và đóng kết nối |

Một vendor có evidence mạnh nhưng khách hàng cấp API token toàn quyền hoặc tải dữ liệu nhạy cảm không cần thiết vẫn tạo rủi ro lớn. Đây là lý do **third-party assurance phải đi cùng kiểm tra shared responsibility**.

### 13.3. Quyền audit có giới hạn thực tế

Một số vendor chỉ cho khách hàng xem báo cáo độc lập hoặc security portal, không chấp nhận kiểm thử trực tiếp lên môi trường sản xuất. Điều này không tự động có nghĩa vendor thiếu an toàn. Đội mua dịch vụ cần đánh giá evidence thay thế, phạm vi quyền truy cập và điều khoản có thể thương lượng. Không nên tự thực hiện penetration test hoặc quét hạ tầng vendor khi chưa có quyền cho phép.

## 14. Continuous assurance sau khi ký hợp đồng

Rủi ro không dừng tại thời điểm questionnaire được phê duyệt. Nhà cung cấp có thể thay đội quản trị, hạ tầng, cloud region, subprocessor, phương thức xác thực hoặc quy trình xử lý dữ liệu.

### 14.1. Triggers tái đánh giá

Một quy trình mature theo dõi:

1. **Theo kỳ đã phê duyệt:** cập nhật risk tier, bằng chứng trọng yếu, exceptions và owner.
2. **Thay đổi dịch vụ:** thêm sản phẩm/add-on, tích hợp sâu hơn, cấp quyền mới hoặc tăng lượng dữ liệu.
3. **Thay đổi nhà cung cấp:** đổi pháp nhân, subprocessor, hosting region, phương thức xử lý hoặc key responsibility.
4. **Sự cố bảo mật:** thông báo incident, breach, outage hoặc lỗ hổng ảnh hưởng service.
5. **Kết quả audit/test:** báo cáo mới có ngoại lệ, scope thay đổi hoặc finding nghiêm trọng.
6. **Hết hạn chứng cứ:** báo cáo cũ không bao phủ kỳ hoặc không còn đáp ứng quy tắc freshness.
7. **Không đạt nghĩa vụ:** SLA, incident communication, hỗ trợ điều tra hoặc xử lý finding bị vi phạm.
8. **Thay đổi rủi ro khách hàng:** dữ liệu nay nhạy cảm hơn hoặc dịch vụ trở thành dependency trọng yếu.
9. **Chuẩn bị exit:** cần đánh giá dữ liệu, quyền và kết nối trước khi kết thúc hợp tác.

Không cần làm lại toàn bộ bảng hỏi mỗi khi có thay đổi nhỏ. Có thể **delta assessment** những control bị ảnh hưởng, kết hợp rà soát scope và quyết định risk tier; luôn ghi vì sao các control khác được coi là không thay đổi.

### 14.2. Theo dõi findings

Một finding không được xem là đóng khi vendor chỉ thông báo “đã sửa”. Cần:

- Mô tả assertion đã không đạt và phạm vi trước sửa.
- Nhận change record hoặc evidence thực tế của thay đổi.
- Xác minh control hoạt động trong service và kỳ phù hợp.
- Đối chiếu phạm vi chưa sửa, ngoại lệ và biện pháp bù trừ.
- Cập nhật trạng thái, owner, quyết định rủi ro, lịch review.
- Khi cần, kiểm tra lại phía khách hàng như quyền tích hợp, export log hoặc luồng dữ liệu.

Một fix MFA cho portal nhân viên vendor không giải quyết finding về service-account token hoặc local admin nếu đó là scope bị ảnh hưởng.

### 14.3. Khi nhà cung cấp ngừng hợp tác

Third-party assurance còn cần bảo đảm **offboarding**:

- Thu hồi SSO app, API key, OAuth grant, VPN, SSH hoặc các quyền vendor support.
- Ngừng luồng dữ liệu và webhook.
- Export/kiểm tra khả năng sử dụng dữ liệu trước khi xóa ở vendor.
- Yêu cầu xử lý dữ liệu theo điều khoản retention, backup và nghĩa vụ lưu bắt buộc.
- Xác minh các subprocessors và hệ thống phụ thuộc được xử lý đúng phạm vi hợp đồng.
- Lưu confirmation/biên bản và bằng chứng kiểm tra sau exit.
- Cập nhật inventory, tài sản, contact và monitoring không còn phụ thuộc vendor.

Thông báo “dữ liệu đã xóa” cần mô tả loại dữ liệu và ngoại lệ lưu giữ hợp lệ, như backup chưa đến thời điểm xóa theo chính sách, thay vì ngầm hiểu mọi byte biến mất ngay.

## 15. Đo hiệu quả của chương trình security questionnaire

### 15.1. KPI có mẫu số và giới hạn

| KPI | Gợi ý cách đo | Điều dễ hiểu sai |
|---|---|---|
| **Assessment coverage** | Dịch vụ third-party cần đánh giá đã có assessment hiện hành / tổng dịch vụ cần đánh giá | Inventory bỏ sót shadow SaaS làm mẫu số sai |
| **Critical control coverage** | Control trọng yếu được verify PASS / tổng control trọng yếu áp dụng | Không tính self-attestation YES là PASS |
| **Evidence coverage** | Assertion có evidence phù hợp, đủ kỳ và scope / assertion bắt buộc | Artifact tồn tại chưa chứng minh chất lượng |
| **Response completion rate** | Số câu hỏi được vendor trả lời hợp lệ / tổng câu hỏi phải trả lời | Chỉ là tiến độ, không phải rủi ro đã xử lý |
| **Inconclusive backlog** | Assertion còn thiếu bằng chứng theo tuổi và severity | UNKNOWN không được coi là không rủi ro |
| **Overdue findings** | Finding quá hạn chưa retest đạt / tổng finding cần xử lý đã đến hạn | Vendor “Done” có thể chưa được verify |
| **Exception expiry** | Ngoại lệ hết hạn chưa tái phê duyệt / tổng ngoại lệ đến hạn | Thiếu owner hoặc expiry cũng là vấn đề |
| **Reassessment timeliness** | Assessment cần review đã hoàn tất trước hạn / tổng đến hạn | Nên tách tier/risk criticality |
| **Vendor change responsiveness** | Thời gian từ trigger thay đổi đến khi scope/decision được cập nhật | Phụ thuộc khả năng nhận biết trigger |
| **Incident communication performance** | Sự kiện thuộc nghĩa vụ thông báo được xử lý trong yêu cầu / số sự kiện phù hợp | Cần ground truth và thỏa thuận thời gian |
| **Exit completion** | Vendor offboard có bằng chứng thu hồi và xử lý dữ liệu / tổng vendor đã exit | Check box “cancel subscription” chưa đủ |

Một tỷ lệ “95% YES” dễ tạo cảm giác an toàn giả. Nếu 5% còn lại gồm các critical gates, chương trình assurance vẫn có rủi ro cao. Nên báo cáo **theo domain, risk tier, service criticality và số finding nghiêm trọng**.

### 15.2. Phân biệt nhiều loại độ bao phủ

Ví dụ trong một kỳ có:

- 20 dịch vụ third-party thuộc diện phải đánh giá.
- 18 dịch vụ đã nhận đủ questionnaire.
- 16 dịch vụ đã hoàn thành security review.
- 13 dịch vụ có bằng chứng đủ cho mọi critical control thuộc scope.
- 3 dịch vụ đang chờ xử lý finding quan trọng.

Khi đó:

- **Questionnaire response coverage:** 18/20 = 90%.
- **Assessment completion coverage:** 16/20 = 80%.
- **Critical control verified coverage theo cấp dịch vụ:** 13/20 = 65%, nếu mẫu số là 20 dịch vụ bắt buộc như giả định.

Không nên chọn mẫu số 16 hoặc 13 mà không công bố định nghĩa. Cũng không được suy ra rằng 65% số vendor của doanh nghiệp “an toàn” theo nghĩa tuyệt đối; đây chỉ là tỷ lệ dịch vụ chứng minh được tập assertion trọng yếu trong phạm vi đánh giá.

### 15.3. Chất lượng cao không đồng nghĩa bảng hỏi càng dài

Questionnaire quá dài có thể khiến nhà cung cấp chọn câu trả lời mẫu và reviewer không đủ thời gian kiểm chứng. Một chương trình hiệu quả cần đo **finding có giá trị, thời gian ra quyết định, mức rủi ro được giảm và retest đạt**, không chỉ số lượng câu hỏi gửi đi.

Có thể duy trì một **baseline câu hỏi dùng lại**, mapping theo control framework và risk tier; bổ sung các câu theo service/data flow. Khi tái sử dụng evidence, phải kiểm tra scope, ngày và thay đổi; tránh tái dùng bản cũ chỉ vì tên file giống nhau.

## 16. Những lỗi thường gặp khi dùng security questionnaire

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Gửi cùng 200 câu cho mọi vendor | Tăng tải, giảm chất lượng trả lời | Risk-based tier và conditional branching |
| Hỏi “Có MFA không?” mà không nêu admin/system | YES dễ che đường bypass | Chỉ rõ mọi đường truy cập và phạm vi identity |
| Chấp nhận “Yes” là PASS | Không có bằng chứng hiệu lực | Yêu cầu evidence và reviewer verdict riêng |
| Xem chứng nhận bao phủ toàn bộ vendor | Bỏ sót dịch vụ ngoài ISMS scope | Kiểm tra pháp nhân, sản phẩm, region, kỳ |
| Nhầm SOC 2 report với bảo đảm tuyệt đối | Bỏ qua exceptions và customer controls | Đọc scope, kỳ, kết luận và trách nhiệm bổ sung |
| Chấp nhận report DR tabletop thay cho restore | RTO/RPO chưa được chứng minh | Yêu cầu test đầu cuối phù hợp hoặc ghi INCONCLUSIVE |
| Không hỏi subprocessor | Bỏ sót luồng dữ liệu và nghĩa vụ | Data flow và registry phụ, trigger cập nhật |
| Dùng điểm trung bình để bù critical FAIL | Go-live khi rủi ro nghiêm trọng chưa xử lý | Critical gates và risk acceptance tách riêng |
| Đánh NOT_APPLICABLE không có lý do | Che control đáng lẽ phải có | Require justification và scope review |
| UNKNOWN được tự động coi là NO hoặc YES | Kết luận thiếu chính xác | INCONCLUSIVE cùng kế hoạch thu thêm evidence |
| Đòi raw secret/pen test exploit quá chi tiết | Tăng nguy cơ rò rỉ | Redaction, controlled review, summary phù hợp |
| Bỏ qua control phía khách hàng | Shared-responsibility gap | Matrix nhiệm vụ và onboarding verification |
| Lưu report trên thư mục rộng quyền | Lộ kiến trúc, lỗ hổng và dữ liệu vendor | Restricted evidence store, retention, audit access |
| Chỉ đánh giá lúc ký hợp đồng | Control drift và finding quá hạn | Reassessment theo trigger và kỳ |
| Đóng finding khi vendor nói đã sửa | Không chứng minh control đã đạt | Retest đúng scope và giữ evidence |
| Không kiểm soát exit | Token hoặc dữ liệu vẫn tồn tại sau hợp đồng | Offboarding checklist và xác nhận có căn cứ |

## 17. Bài tập tự kiểm tra

**Câu 1.** Vendor trả YES cho câu hỏi “Có mã hóa dữ liệu khi lưu không?” và gửi một policy về encryption của toàn công ty. Có thể chấm PASS ngay không?

**Gợi ý:** Chưa. Cần xác định dữ liệu và service trong scope, nơi lưu, trách nhiệm quản lý khóa, cấu hình thực tế hoặc bằng chứng phù hợp kỳ và phạm vi. Policy chỉ chứng minh một phần control design.

**Câu 2.** Một báo cáo audit độc lập không có finding quan trọng, nhưng phạm vi audit không bao gồm add-on API mà khách hàng muốn mua. Kết luận hợp lý là gì?

**Gợi ý:** Báo cáo có thể dùng cho các thành phần được bao phủ; add-on API cần evidence hoặc test riêng. Không suy rộng PASS toàn dịch vụ.

**Câu 3.** Nhà cung cấp nói DR đạt RTO 1 giờ vì đã chạy tabletop. Bạn nên hỏi thêm gì?

**Gợi ý:** Failure scenario, scope, RTO/RPO target, timestamps T0/T1, data consistency, end-to-end service test và kết quả security controls. Tabletop không phải bằng chứng thời gian restore đã đạt.

**Câu 4.** Một vendor có 98% câu hỏi YES nhưng không có MFA cho tài khoản hỗ trợ đặc quyền vào production. Đánh giá theo điểm trung bình có phù hợp không?

**Gợi ý:** Không. Cần đánh giá critical gate dựa trên quyền truy cập, dữ liệu và khả năng bị lợi dụng, có thể hoãn go-live hoặc giới hạn scope đến khi có remediation và retest.

**Câu 5.** Vendor trả NOT_APPLICABLE cho câu hỏi quản lý dữ liệu cá nhân, nhưng data flow cho thấy họ nhận email và ticket chứa thông tin cá nhân của khách hàng. Bạn xử lý thế nào?

**Gợi ý:** Yêu cầu giải thích mâu thuẫn, cập nhật data inventory và đánh giá lại applicability; không chấm NOT_APPLICABLE khi dữ liệu thực tế nằm trong scope.

**Câu 6.** Bằng chứng cho thấy MFA trên SSO được bật, nhưng admin local break-glass chưa được đánh giá. Có nên ghi YES/PASS không?

**Gợi ý:** Nếu assertion yêu cầu mọi đường admin tương tác, reviewer chưa thể kết luận đạt toàn scope. Ghi exception hoặc INCONCLUSIVE/FAIL theo những gì đã xác minh; yêu cầu kiểm tra đường local.

**Câu 7.** Khách hàng có API key toàn quyền truy cập SaaS dù nhà cung cấp đã đáp ứng tất cả control nền tảng. Rủi ro thuộc về ai?

**Gợi ý:** Cần xem shared responsibility. Khách hàng có thể chịu trách nhiệm cấu hình token đúng scope và bảo vệ credential, vendor chịu trách nhiệm cung cấp cơ chế hạn quyền/giám sát theo thỏa thuận.

**Câu 8.** Vendor vừa thêm subprocessor mới sau khi assessment được phê duyệt. Có cần gửi lại toàn bộ questionnaire từ đầu không?

**Gợi ý:** Không nhất thiết; cần đánh giá tác động thay đổi, phạm vi dữ liệu, điều khoản thông báo và các control bị ảnh hưởng. Dùng delta assessment có truy vết và cập nhật quyết định rủi ro.

## 18. Bài thực hành: xây dựng bảng câu hỏi cho một dịch vụ xử lý dữ liệu nhạy cảm

Giả sử bạn thuộc đội third-party assurance. Một phòng ban muốn mua nền tảng SaaS giúp phân tích phản hồi khách hàng. Dịch vụ sẽ nhận tên, địa chỉ email, nội dung hỗ trợ; có API import/export, SSO và một subprocessor để phân tích. Sau ba tháng, phòng ban dự kiến cấp thêm quyền kết nối database nội bộ.

**Nhiệm vụ:**

1. Vẽ data flow và liệt kê những vùng dữ liệu, danh tính, nguồn log và subprocessor thuộc phạm vi.
2. Lập **risk tier ban đầu**, giải thích các yếu tố business criticality, privacy, credential access và tác động gián đoạn.
3. Chọn tối thiểu mười câu hỏi từ TPQ-01..TPQ-18; chỉnh lại scope, kỳ, điều kiện áp dụng và bằng chứng mong đợi.
4. Viết hai câu hỏi bổ sung về API import/export và phạm vi dữ liệu cho subprocessor.
5. Đề xuất bộ trạng thái vendor response, reviewer verdict và risk decision riêng biệt.
6. Nhận được ba câu trả lời giả định: **YES không có evidence**, **PARTIAL với ngoại lệ MFA**, và **NOT_APPLICABLE mâu thuẫn data flow**. Ghi cách xử lý và yêu cầu follow-up.
7. Tạo evidence register, finding register và một quyết định onboarding hạn chế nếu critical gates chưa đạt.
8. Định nghĩa trigger **delta assessment** khi phòng ban yêu cầu thêm kết nối database nội bộ.
9. Thiết kế checklist offboarding để thu hồi credential và xử lý bản sao dữ liệu.

**Tiêu chí đánh giá:**

| Tiêu chí | Đạt khi |
|---|---|
| Phạm vi | Xác định đúng dịch vụ, dữ liệu, role, region và bên xử lý phụ |
| Tính đo được | Câu hỏi không nhập nhằng, có kỳ và evidence cụ thể |
| Phân tích | Không đánh YES thành PASS tự động, ghi giới hạn và tình trạng chưa đủ dữ liệu |
| Ưu tiên | Critical control được đánh giá theo rủi ro, không bị điểm trung bình che |
| Truy vết | Question ID → evidence → verdict → finding → remediation → retest |
| Governance | Có risk owner, điều kiện cấp quyền, hạn ngoại lệ và change triggers |
| Vòng đời | Có reassessment và exit verification |

## 19. Checklist triển khai security questionnaire assurance

- [ ] Dịch vụ và pháp nhân vendor đã được xác định trong inventory có owner.
- [ ] Có data flow, loại dữ liệu, region, privileged integration và trách nhiệm chia sẻ.
- [ ] Đã phân loại risk tier và chọn bộ câu hỏi phù hợp, không dùng một mẫu cứng cho mọi trường hợp.
- [ ] Mỗi câu hỏi có ID, control objective, scope, kỳ đánh giá, trạng thái và evidence expectation.
- [ ] Các nhánh conditional cho privacy, API, privileged access, subprocessor và resilience được xác định.
- [ ] Vendor response tách khỏi assurance verdict và quyết định risk owner.
- [ ] Có kiểm tra scope, freshness, nguồn, ngoại lệ và hiệu lực của bằng chứng.
- [ ] Các báo cáo SOC 2, chứng nhận ISO hoặc test summary được đọc đúng phạm vi, kỳ và giới hạn.
- [ ] Không yêu cầu secret hoặc tài liệu vượt mức cần thiết; evidence được nộp qua kênh bảo vệ.
- [ ] Mọi YES quan trọng có thể dẫn tới bằng chứng phù hợp, không chỉ self-attestation.
- [ ] UNKNOWN và NOT_APPLICABLE có giải thích; không bị tự động chuyển thành PASS.
- [ ] Critical gates được áp riêng, không đánh đổi bằng điểm trung bình.
- [ ] Có control mapping cho phần trách nhiệm của vendor và khách hàng.
- [ ] Finding có risk rationale, owner, deadline, compensating control và retest evidence.
- [ ] Quyết định onboarding ghi scope dữ liệu/quyền được phép, người phê duyệt và điều kiện.
- [ ] Hợp đồng/phụ lục phản ánh những yêu cầu bảo mật và thông báo cần duy trì theo thỏa thuận.
- [ ] Có trigger tái đánh giá khi thay đổi dịch vụ, data flow, region, subprocessor hoặc xảy ra incident.
- [ ] Báo cáo KPI có mẫu số inventory và trạng thái chưa kiểm chứng tách biệt.
- [ ] Có quy trình exit để thu hồi quyền và xử lý dữ liệu, bản sao và subprocessors.
- [ ] Audit trail giữ các phiên bản câu hỏi, câu trả lời, evidence, finding và quyết định.

## Kết luận

**Security questionnaire là công cụ khởi đầu cho việc thu thập và đối chiếu bằng chứng bảo mật của nhà cung cấp, không phải một phép chứng nhận an toàn độc lập.** Chất lượng đánh giá phụ thuộc vào phạm vi dịch vụ, dữ liệu và quyền truy cập được mô tả chính xác; câu hỏi có thể kiểm thử; bằng chứng liên quan, còn hiệu lực và đủ mạnh; khả năng nhận diện những câu trả lời thiếu hoặc mâu thuẫn; và quyết định rủi ro có thẩm quyền.

Trong **SECURITY_SECURITY_ASSURANCE**, quy trình hiệu quả phải liên kết **rủi ro → security requirement → question → response → evidence → verification → finding → remediation → retest → risk decision**. Khi việc giám sát thay đổi, gia hạn và offboarding được đưa vào vòng đời quan hệ nhà cung cấp, security questionnaire trở thành một phần của chương trình **third-party assurance liên tục**, giúp tổ chức không chỉ hỏi nhà cung cấp đang làm gì mà còn có căn cứ xác nhận những control quan trọng đang thực sự đáp ứng mục tiêu bảo mật.


