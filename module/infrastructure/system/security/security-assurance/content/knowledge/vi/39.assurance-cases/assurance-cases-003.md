# Argument: Xây dựng lập luận có cấu trúc trong security assurance case

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích **argument** trong assurance case và phân biệt **claim, argument, evidence, context, assumption, justification, limitation và rebuttal**.
2. Trình bày cấu trúc lập luận **Claim–Argument–Evidence (CAE)** và cách biểu diễn bằng các thành phần thường gặp của **Goal Structuring Notation (GSN)**.
3. Chuyển một tuyên bố bảo mật tổng quát thành **các subclaims có đủ phạm vi**, xác định quan hệ suy luận và các điều kiện để kết luận cấp trên được hỗ trợ.
4. Lựa chọn chiến lược phân rã theo **mục tiêu bảo mật, threat scenario, kiến trúc, vòng đời và security controls**, không đánh đồng số lượng control với mức tin cậy.
5. Đánh giá chứng cứ theo **relevance, sufficiency, freshness, independence, provenance và limitations**; xử lý các giả định chưa được xác minh.
6. Nhận diện **defeaters, counterexamples, uncertainty, circular reasoning và missing premises** khiến một lập luận bảo mật chưa đủ vững.
7. Thiết kế, rà soát và duy trì một assurance argument có thể audit cho các hệ thống thực tế như IAM, detection engineering, logging và disaster recovery.

## 1. Vì sao security assurance cần argument?

Một tổ chức có thể sở hữu rất nhiều bằng chứng: báo cáo pentest, log SIEM, cấu hình IAM, chứng nhận nhà cung cấp, biên bản access review, kết quả kiểm thử khôi phục và danh sách vulnerabilities. Tuy nhiên, **nhiều dữ liệu không tự tạo thành một kết luận đáng tin**.

Ví dụ, tổ chức đưa ra tuyên bố:

> Hệ thống xử lý đơn hàng production được bảo vệ phù hợp trước rủi ro lạm dụng quyền quản trị.

Sau đó đính kèm ba file: ảnh chụp cấu hình MFA, báo cáo pentest năm trước và biểu đồ số lượng alerts. Chúng có thể hữu ích nhưng chưa trả lời:

- Có những đường nào dẫn tới quyền quản trị, gồm human accounts, service accounts, CI/CD và break-glass?
- MFA có thực sự được thực thi cho đúng nhóm danh tính và đường đăng nhập không?
- Báo cáo pentest có kiểm tra đúng các đường đặc quyền của phiên bản production đang vận hành không?
- Alert có bao phủ hành vi tăng quyền, đến đúng người nhận và đủ thời gian phản ứng không?
- Có những thay đổi sau đợt đánh giá khiến bằng chứng cũ không còn phù hợp không?
- Nếu một control thất bại, điều đó ảnh hưởng thế nào tới kết luận tổng thể?

**Argument** là cầu nối diễn giải từ các **yêu cầu và giả thuyết về hệ thống** tới **những bằng chứng cụ thể**, thể hiện rõ tại sao có lý do để tin một claim trong một phạm vi xác định.

Trong mô-đun **SECURITY_SECURITY_ASSURANCE**, argument phục vụ mục tiêu đánh giá hệ thống có bằng chứng: từ phân tích rủi ro và security objectives, qua lựa chọn controls, kiểm thử, audit, xử lý findings đến đánh giá lại liên tục.

### 1.1. Định nghĩa làm việc

**Assurance argument** là một tập hợp các bước lập luận có cấu trúc, cho thấy các kết luận cấp dưới, giả định và bằng chứng được sử dụng như thế nào để hỗ trợ một tuyên bố cấp cao về một hệ thống hoặc hoạt động.

Một argument cần **có thể chất vấn được**: reviewer phải nhìn thấy tiền đề, chiến lược suy luận, nguồn bằng chứng và những điều kiện mà khi chúng sai, kết luận có thể không còn giá trị.

**Assurance case** là bộ hồ sơ rộng hơn, thường bao gồm:

- Các claim và cấu trúc argument.
- Context, assumption, rationale và ranh giới đánh giá.
- Evidence với provenance, phiên bản và giới hạn.
- Các defeaters, issues, findings và risk decisions.
- Kết luận review, người chịu trách nhiệm và quy trình cập nhật.

**Argument không phải là chứng minh toán học tuyệt đối rằng hệ thống không thể bị xâm nhập.** Các lập luận an ninh thường dựa trên bằng chứng không hoàn hảo, giả định về threat model, tính đại diện của test và trạng thái hệ thống thay đổi theo thời gian.

### 1.2. Những câu trả lời sai nhưng dễ gặp

| Nhận định | Vấn đề |
|---|---|
| "Có báo cáo kiểm toán nên hệ thống an toàn." | Báo cáo có scope, tiêu chí, thời kỳ và exceptions; chưa kết nối tới claim đang nêu. |
| "Có 100 security controls nên assurance mạnh." | Số lượng control không cho biết mức độ phù hợp, coverage hoặc hiệu lực. |
| "Không thấy incident nên hệ thống chống được tấn công." | Có thể thiếu detection, thiếu telemetry hoặc chưa gặp hành vi đó. |
| "Unit test của rule pass nên mọi hành vi đe dọa sẽ bị phát hiện." | Test có thể bỏ qua parser, nguồn production, đường truyền, variants và response. |
| "Backup job thành công nên có thể recovery đúng RTO." | Khả năng restore, giải mã, dependencies, dữ liệu và chức năng chưa được chứng minh. |
| "Tất cả subclaims đều xanh nên top claim chắc chắn đúng." | Subclaims có thể không đủ bao phủ hoặc suy luận kết hợp có lỗ hổng. |

Lập luận tốt giúp phát hiện **khoảng trống giữa điều đã kiểm tra và điều muốn tuyên bố**.

## 2. Cấu trúc Claim–Argument–Evidence (CAE)

Một cách tiếp cận phổ biến là mô hình **Claim–Argument–Evidence**:

- **Claim:** điều muốn khẳng định về hệ thống hoặc quá trình.
- **Argument:** lý do giải thích tại sao một tập các bằng chứng và subclaims hỗ trợ claim đó.
- **Evidence:** dữ liệu hoặc kết quả có nguồn gốc và phạm vi xác định dùng để kiểm tra các tiền đề.

~~~mermaid
flowchart TD
    TOP["Claim cấp cao: mục tiêu bảo mật đạt trong scope"]
    ARG["Argument: phân rã mục tiêu và quan hệ suy luận"]
    C1["Subclaim A: control được thiết kế phù hợp"]
    C2["Subclaim B: control được triển khai đúng"]
    C3["Subclaim C: control vận hành hiệu lực"]
    E1["Evidence: threat model, thiết kế"]
    E2["Evidence: configuration, inventory"]
    E3["Evidence: tests, audit events, monitoring"]
    TOP --> ARG
    ARG --> C1
    ARG --> C2
    ARG --> C3
    C1 --> E1
    C2 --> E2
    C3 --> E3
~~~

**Sơ đồ chỉ là ví dụ một cách phân rã.** Với một threat phức tạp, ba subclaims thiết kế–triển khai–vận hành có thể chưa đủ; phải bổ sung coverage của tài sản, đường tấn công, giả định về phụ thuộc, người vận hành, data integrity và rủi ro tồn dư.

### 2.1. Claim phải có ranh giới

Một claim như "Ứng dụng an toàn" không chỉ mơ hồ mà còn khó kiểm chứng: không xác định mục tiêu, threat, phiên bản, kỳ hay môi trường.

Một claim khả dụng hơn:

> Từ ngày 01 đến 30/11/2026, trong các cloud accounts production liệt kê trong asset inventory đã kiểm tra, các lần cấp quyền quản trị mới đều phải qua cơ chế phê duyệt có thể truy vết; các hành vi cấp quyền trái chính sách được phát hiện và chuyển cảnh báo theo mục tiêu đã phê duyệt, ngoại trừ những giới hạn được ghi nhận trong hồ sơ.

Claim này vẫn cần kiểm tra:

- Population có đầy đủ và đáng tin không?
- Yêu cầu phê duyệt có áp dụng cho mọi kiểu privilege grant?
- "Phát hiện" và "chuyển cảnh báo" có định nghĩa và ngưỡng rõ không?
- Nếu có ngoại lệ, chúng đã được phê duyệt và còn hiệu lực không?
- Mọi thay đổi trong kỳ hay chỉ một mẫu được kiểm tra?

**Không nên viết claim mạnh hơn khả năng đánh giá.**

### 2.2. Argument nói về quan hệ suy luận

Giả sử có:

1. Một security requirement yêu cầu tất cả thay đổi quyền quản trị phải có approval.
2. Một kiểm thử cho thấy workflow cấp quyền từ giao diện hoạt động.
3. Một ảnh cấu hình cho thấy IAM policy đang bật.

Chưa đủ để suy ra **mọi thay đổi quyền quản trị đều được phê duyệt**. Cần xét các đường khác: API, IaC, automation, role inheritance, emergency grants, cross-account trust và các thay đổi trực tiếp bởi principal có quyền cao.

**Mệnh đề còn thiếu** có thể là:

> Tất cả các đường có thể làm phát sinh quyền quản trị trong phạm vi đã được nhận diện và nằm dưới cơ chế phê duyệt hoặc giám sát thích hợp.

Mệnh đề đó cần **một subclaim và evidence riêng**. Đây là tác dụng then chốt của argument: buộc người viết công khai những điều trước đây được ngầm cho là đúng.

## 3. Các thành phần lập luận trong GSN

**Goal Structuring Notation (GSN)** là một dạng ký pháp trình bày lập luận assurance có cấu trúc. Người học không cần một công cụ đặc biệt để hiểu ý tưởng, nhưng cần phân biệt rõ loại nút và quan hệ.

| Thành phần | Ký hiệu thường dùng | Vai trò | Ví dụ |
|---|---|---|---|
| **Goal** | G | Claim cần hỗ trợ. | G0: Quyền quản trị production được kiểm soát trong scope. |
| **Strategy** | S | Giải thích cách phân rã Goal thành các Goal khác. | S1: Lập luận theo coverage, enforcement và detection. |
| **Context** | C | Định nghĩa phạm vi, thuật ngữ, hệ thống, chuẩn hoặc tiền đề bối cảnh. | C1: Inventory accounts và định nghĩa quyền admin. |
| **Assumption** | A | Tiền đề được tạm chấp nhận; cần công khai và đánh giá sự hợp lý. | A1: Các nguồn audit trọng yếu có time sync nằm trong giới hạn. |
| **Justification** | J | Lý do chọn cách tiếp cận hoặc giải pháp suy luận. | J1: Ba lớp control tương ứng các đường giảm thiểu rủi ro ưu tiên. |
| **Solution** | Sn | Evidence hoặc kết quả đánh giá hỗ trợ Goal. | Sn1: Kết quả IAM access test và audit history. |
| **Undeveloped** | Chưa phát triển | Phần Goal chưa có lập luận/bằng chứng hoàn chỉnh. | Chưa đánh giá đường thay đổi quyền qua tài khoản ngoại lệ. |

Một số triển khai GSN còn dùng các biến thể tham chiếu đến argument ở nơi khác. Khi ghi ví dụ trong tài liệu, cần nêu **ký hiệu và phiên bản/qui ước đang dùng**, tránh hiểu sai nút evidence thành claim.

### 3.1. Biểu diễn ví dụ bằng sơ đồ

~~~mermaid
flowchart TD
    G0["G0 — Claim: thay đổi đặc quyền được kiểm soát"]
    C0["C0 — Context: production scope, period, policy"]
    A0["A0 — Assumption: audit source có coverage đáng tin"]
    S0["S0 — Strategy: theo prevention + detection + response"]
    G1["G1 — Quyền admin cấp mới có approval"]
    G2["G2 — Mọi thay đổi trái phép có tín hiệu phát hiện"]
    G3["G3 — Alert tới người trực đúng SLA"]
    SN1["Sn1 — IAM effective-permission & approval tests"]
    SN2["Sn2 — Detection positive/negative tests"]
    SN3["Sn3 — Alert routing & case timeline"]
    G0 --> C0
    G0 --> A0
    G0 --> S0
    S0 --> G1
    S0 --> G2
    S0 --> G3
    G1 --> SN1
    G2 --> SN2
    G3 --> SN3
~~~

Mermaid ở đây giúp hình dung; nó **không thay thế ký hiệu hình học GSN chuẩn**. Đặc biệt, đường nối context/assumption khác về ngữ nghĩa với quan hệ **supported by**. Trong công cụ GSN chuyên dụng, hãy dùng loại nút và liên kết đúng nghĩa.

### 3.2. Goal, context và assumption không thay thế nhau

**Goal:** "API chỉ trả dữ liệu khi người gọi có quyền".

**Context:** "API ở phiên bản release R, các endpoint theo inventory X, danh tính được xác thực bởi IdP Y".

**Assumption:** "Dịch vụ IdP phát token có claim chính xác và khóa xác minh không bị compromise trong kỳ đánh giá".

**Evidence:** "Kết quả negative authorization tests cho các endpoint và bộ quyền, kèm log denial và code review".

Nếu assumption về IdP chưa được đánh giá và có thể ảnh hưởng đáng kể tới claim, cần tạo subclaim hỗ trợ **độ tin cậy của IdP/token-validation controls**, thay vì chỉ giữ như lời nói không kiểm tra.

### 3.3. Justification giải thích cách phân rã

Một chiến lược "phân rã theo ba lớp prevent–detect–respond" cần giải thích tại sao ba lớp đó có liên quan và đủ cho threat scope. Điều này thường là **justification**:

- Prevent giảm khả năng hành vi bị cấm hoàn tất.
- Detect nhận diện khi prevention không đủ hoặc bị vượt qua.
- Respond giảm tác động sau khi phát hiện.
- Coverage của inventory và telemetry là điều kiện cần để các lớp trên bao phủ phạm vi mong muốn.

Nếu lập luận thiếu **coverage**, chỉ có ba loại control không chứng minh mọi đường đe dọa ưu tiên đã được giải quyết.

## 4. Cách xây một argument từ top claim

### 4.1. Quy trình tám bước

1. **Định nghĩa top claim:** trạng thái hoặc năng lực muốn khẳng định, mục tiêu và phạm vi.
2. **Xác định context:** hệ thống, release, environment, population, thời gian, security policy, threat model.
3. **Ghi assumptions:** điều chưa được chứng minh nhưng đang cần đúng để suy luận.
4. **Chọn strategy:** tách claim theo điều kiện cần, rủi ro hoặc thành phần.
5. **Viết subclaims:** mỗi claim cấp dưới có chủ thể, điều kiện và ranh giới có thể test.
6. **Nối evidence và warrants:** chọn chứng cứ cho từng subclaim và giải thích tại sao nó hỗ trợ điều đó.
7. **Tìm defeaters:** phản ví dụ, tiền đề yếu, missing coverage, evidence stale và điều kiện thay đổi.
8. **Review và duy trì:** đánh giá độc lập, ghi giới hạn, findings, quyết định và trigger cần cập nhật.

~~~mermaid
flowchart TD
    R["Risk & assurance objective"] --> G["Top claim có scope"]
    G --> CONTEXT["Context & assumptions"]
    CONTEXT --> STRAT["Argument strategy"]
    STRAT --> SUB["Subclaims có thể kiểm tra"]
    SUB --> EVID["Evidence + inference rationale"]
    EVID --> REVIEW["Challenge: counterexamples / defeaters"]
    REVIEW --> DEC{"Đủ hỗ trợ?"}
    DEC -->|Có| A["Qualified assurance conclusion"]
    DEC -->|Chưa| GAP["Gap / revise / new test"]
    GAP --> SUB
    A --> LIVE["Monitor change & revalidate"]
    LIVE --> CONTEXT
~~~

### 4.2. Chọn độ rộng claim

Claim quá rộng sẽ khó đủ evidence; claim quá hẹp có thể vô dụng với quyết định kinh doanh.

| Claim | Khuyết điểm | Bản điều chỉnh |
|---|---|---|
| "Mọi cuộc tấn công đều được ngăn chặn." | Tuyệt đối, không thể kiểm chứng với threat không giới hạn. | "Các attack paths ưu tiên trong threat model T được giảm xuống ngưỡng risk appetite bằng controls C trong scope R." |
| "MFA đã bật." | Chưa cho biết population, đường đăng nhập, hiệu lực. | "Human privileged interactive sign-ins thuộc inventory P tuân theo MFA policy V và test đã xác minh." |
| "Cloud DR đáp ứng yêu cầu." | Thiếu kịch bản, dữ liệu, thời gian. | "Trong kịch bản mất region A đã thử, dịch vụ X khôi phục chức năng Y trong RTO và điểm dữ liệu phục hồi đạt RPO đã phê duyệt." |
| "Pentest không có lỗi Critical nên sản phẩm an toàn." | Báo cáo chỉ bao phủ một scope/thời điểm/kỹ thuật. | "Các attack scenarios thuộc phạm vi PT-05 được kiểm tra; findings đã khắc phục được retest trong phạm vi đó." |

**Kết luận càng mạnh, nghĩa vụ hỗ trợ càng lớn**. Nếu một phần claim chưa được đánh giá, nên thu hẹp hoặc nêu rõ điều kiện và uncertainty.

## 5. Chiến lược phân rã lập luận

Không có một chiến lược duy nhất đúng cho mọi assurance case. Lựa chọn phải xuất phát từ **rủi ro, hệ thống và quyết định sẽ dựa vào kết luận**.

### 5.1. Phân rã theo yêu cầu bảo mật

Top claim "Hệ thống đáp ứng các security objectives được phê duyệt" có thể tách thành:

- Confidentiality objectives được đáp ứng cho tập dữ liệu X.
- Integrity objectives được đáp ứng cho giao dịch Y.
- Availability/recoverability objectives được đáp ứng cho chức năng Z.
- Security monitoring và response đáp ứng những scenario ưu tiên.

Ưu điểm: dễ truy vết yêu cầu. Nhược điểm: có thể bỏ qua **attack path xuyên nhiều mục tiêu** hoặc phụ thuộc chung.

### 5.2. Phân rã theo threat scenarios

Đối với một ứng dụng tài chính:

- Credential compromise.
- Privilege escalation.
- Unauthorized data export.
- Supply-chain compromise.
- Data corruption và ransomware.
- Regional outage hoặc denial of service.

Mỗi scenario được đánh giá theo attack paths, controls, test và residual risk.

Ưu điểm: gần risk-based assurance. Nhược điểm: **threat model không đầy đủ** khiến argument bỏ sót nguy cơ; phải có subclaim đánh giá độ đầy đủ và cập nhật threat model.

### 5.3. Phân rã theo kiến trúc / trust boundary

- User identity & session.
- Application/API authorization.
- Data storage & encryption keys.
- Cloud control plane/IaC.
- Network/ingress/egress.
- External service, SaaS, third party.
- Logging/detection/response.

Ưu điểm: gắn owner kỹ thuật, inventory và evidence. Nhược điểm: các đường tấn công có thể **đi qua nhiều boundary**; cần subclaim kết nối và review các interaction.

### 5.4. Phân rã theo vòng đời control

- Thiết kế: control phù hợp risk objective.
- Triển khai: control có mặt tại đúng resource.
- Vận hành: control thực thi khi cần.
- Giám sát: phát hiện control failure và drift.
- Khắc phục: failure có owner và retest.

Ưu điểm: phân biệt policy-on-paper với effectiveness. Nhược điểm: nếu lựa chọn control từ đầu đã không đủ coverage, cả vòng đời hoạt động tốt vẫn chưa chứng minh threat risk được kiểm soát.

### 5.5. Phân rã theo tình huống / mode vận hành

- Normal operation.
- Planned deployment/maintenance.
- Degraded mode.
- Incident containment.
- Disaster recovery/failover.
- Offboarding/termination.

Một claim có thể đúng ở trạng thái bình thường nhưng sai khi khẩn cấp, ví dụ break-glass bỏ qua MFA mà không có logging hoặc DR site thiếu audit.

### 5.6. Chọn chiến lược kết hợp

Thực tế thường dùng **nhiều lớp**: top claim theo security objective; một nhánh đánh giá threat coverage; từng threat chia theo prevent–detect–respond; một số controls lại được chia theo design–implementation–operation.

Độ sâu phải vừa đủ để:

- Không còn tiền đề quan trọng bị ngầm định.
- Mỗi leaf claim có thể được hỗ trợ bằng evidence có chất lượng xác định.
- Người đánh giá truy vết được từ top claim tới test và source.
- Các thay đổi của hệ thống có thể khoanh vùng những claim cần xem xét lại.

## 6. Quan hệ suy luận: khi nào subclaims thực sự đủ?

### 6.1. AND, OR và điều kiện bao phủ

Giả sử G0 là "Mọi thay đổi quyền admin trong scope đều có khả năng kiểm soát phù hợp". Một strategy phân rã thành:

- G1: Tất cả đường thay đổi đặc quyền đã được nhận diện.
- G2: Các đường đó bị kiểm soát hoặc giám sát theo chính sách.
- G3: Dữ liệu kiểm tra đầy đủ trong kỳ.
- G4: Ngoại lệ được quản lý và phát hiện sự sai lệch.

Các subclaims này thường có quan hệ **AND**: nếu G1 sai vì bỏ qua CI/CD service account, việc G2/G3/G4 đạt trên những đường đã biết không làm G0 đạt.

Với các lựa chọn thay thế:

- G-A: Control A ngăn chặn hành vi nguy hiểm.
- G-B: Nếu control A không áp dụng, control B đạt yêu cầu giảm rủi ro tương đương trong bối cảnh đã nêu.

Không được dùng quan hệ **OR** nếu chưa có bằng chứng rằng một trong hai giải pháp **đủ** cho từng tình huống trong population. Có thể có trường hợp cả hai đều không áp dụng.

### 6.2. Một bảng suy luận cần thử chất vấn

| Top claim | Subclaim | Điều kiện còn thiếu có thể làm sai suy luận |
|---|---|---|
| "Mọi thay đổi quyền được phê duyệt." | Tất cả change tickets đều có approval. | Thay đổi ngoài workflow có được đưa vào population? |
| "Không có dữ liệu khách hàng rò rỉ." | DLP không tạo alert. | DLP có bao phủ mọi data flow, loại dữ liệu và đường mã hóa? |
| "DR đạt RPO 15 phút." | Replication lag dưới 1 phút. | Điểm dữ liệu thực sự recoverable và nhất quán tại thời điểm thảm họa là gì? |
| "Vendor đáp ứng yêu cầu bảo mật." | Vendor có SOC 2 Type 2. | Báo cáo bao phủ đúng sản phẩm, kỳ, subservice và controls của khách hàng? |
| "Kubernetes workload an toàn." | Admission policy từ chối privileged pods. | Có workload preexisting, quyền bypass, host compromise hoặc đường runtime khác? |

Người viết assurance argument cần **giải thích phép suy ra**, không chỉ vẽ mũi tên từ evidence tới claim.

### 6.3. Warrant và inference rule

**Warrant** là lý do cho rằng một loại evidence hoặc subclaim đủ hỗ trợ kết luận trong một bối cảnh.

Ví dụ:

- Evidence: log kiểm thử cho thấy một principal không quyền nhận HTTP 403 từ API.
- Subclaim: endpoint A từ chối một yêu cầu không có quyền trong test case T.
- Warrant hợp lý: phép thử kiểm tra đúng endpoint, danh tính, data scope và phiên bản hệ thống.
- Warrant không hợp lý: vì endpoint A trả 403 ở một test nên **mọi** endpoint đều chống được mọi kiểu truy cập trái phép.

Khi cần suy luận cho cả population, phải có thêm căn cứ về **test coverage, kỹ thuật chọn mẫu, tính đại diện và kiểm tra các đường bypass**.

## 7. Context, assumptions và justifications

### 7.1. Những yếu tố context thường cần ghi

- System boundary, version, environment, region, tenant và data classification.
- Threat model version, attack scenarios và risk appetite.
- Policy/control framework/requirement version.
- Kỳ đánh giá, nguồn thời gian, cách định nghĩa "hoàn tất", "phát hiện", "khôi phục".
- Kiến trúc phụ thuộc: IAM, network, cloud, KMS, SaaS, Kubernetes.
- Phạm vi test và trường hợp bị loại trừ.

Nếu một điều kiện context thay đổi, **claim có thể hết hiệu lực ngay cả khi evidence vẫn nguyên vẹn**.

### 7.2. Ví dụ assumption register

| Assumption ID | Giả định | Lý do cần | Rủi ro khi sai | Cách kiểm tra |
|---|---|---|---|---|
| A-IAM-01 | IAM inventory bao gồm mọi principal có thể cấp quyền admin. | Xác định population. | Bỏ sót đường tăng quyền ngoài kiểm tra. | Đối chiếu role trust, APIs, group inheritance, IaC và accounts. |
| A-LOG-02 | Audit nguồn trọng yếu phát event đầy đủ trong kỳ. | Rule và review dựa vào log. | Không thấy vi phạm dù đã xảy ra. | Source coverage, health, reconciliation và synthetic tests. |
| A-TIME-03 | Timestamp của các nguồn đủ tin cậy cho SLA. | Đo detection/response latency. | Kết luận latency sai. | Time sync assessment, event/ingest timestamps và clock skew. |
| A-TPR-04 | Vendor thực thi control theo phạm vi contract. | Phụ thuộc third party. | Control thực tế ngoài scope assurance. | Scope report, exception review, customer-side tests và hợp đồng. |
| A-DR-05 | Backup có thể giải mã và restore khi primary mất. | Recovery argument. | Không đạt RTO dù có backup. | Restore test từ DR site với quyền/keys thực. |

Nếu một assumption có **tác động lớn tới top claim**, không nên để ở trạng thái "tin vậy" lâu dài. Cần biến nó thành claim có test hoặc ghi một limitation/risk decision cụ thể.

### 7.3. Justification phải có nội dung

Justification tốt:

> Lập luận được chia thành coverage, enforcement và monitoring vì mục tiêu chống tăng quyền trái phép đòi vừa biết đầy đủ các đường cấp quyền, vừa kiểm soát đường hợp lệ, vừa phát hiện đường bypass và thất bại của cơ chế kiểm soát.

Justification yếu:

> Chia ba phần vì đây là best practice.

Người review cần có thể kiểm tra rationale có phù hợp threat model và hệ thống không, chứ không chỉ vì một sơ đồ đẹp.

## 8. Defeaters: điều gì có thể bác bỏ lập luận?

Một assurance argument vững phải chủ động tìm **defeaters**: dữ kiện hoặc tình huống làm suy yếu kết luận, tiền đề hoặc mối liên kết suy luận.

Một phân loại hữu ích trong lập luận là:

- **Rebutting defeater:** bằng chứng trực tiếp chống lại claim. Ví dụ một tài khoản admin thực sự đăng nhập thành công mà không đi qua MFA bắt buộc.
- **Undermining defeater:** làm yếu độ tin cậy của evidence/tiền đề. Ví dụ log export bỏ sót một region hoặc dashboard có parser lỗi.
- **Undercutting defeater:** làm yếu quan hệ suy luận từ tiền đề tới kết luận. Ví dụ approval ticket có đủ nhưng một API cấp quyền hoàn toàn ngoài workflow, nên ticket population không đại diện mọi thay đổi.

Các thuật ngữ này là cách phân tích lập luận, **không phải ba loại sự cố kỹ thuật cố định**.

### 8.1. Defeater register

| ID | Claim bị ảnh hưởng | Defeater | Evidence/tình trạng | Hành động |
|---|---|---|---|---|
| D-01 | G0: quyền admin được kiểm soát. | Cross-account role bypass được workflow approval. | IAM audit chứa event chưa khớp change ticket. | Mở finding, mở rộng population và retest. |
| D-02 | G2: detection có coverage. | Collector thiếu log một cloud account. | Source health FAIL trong một khoảng thời gian. | Ghi coverage gap, sửa collector, test ingestion. |
| D-03 | G3: alert trong 5 phút. | Timestamp nguồn lệch 8 phút. | Time sync discrepancy. | Đánh giá lại latency, sửa đồng hồ và test. |
| D-04 | G4: vendor được kiểm chứng. | SOC report không bao phủ product mới. | Scope/version review. | Thu evidence bổ sung hoặc giới hạn claim. |
| D-05 | G5: DR luôn recover từ điểm sạch. | Snapshot mới nhất đã chứa dữ liệu bị mã hóa. | Isolated restore/forensic assessment. | Chọn recovery point trước compromise và chứng minh sạch. |

Không phải defeater nào cũng ngay lập tức chứng minh top claim sai; nhưng **mỗi defeater trọng yếu phải được xử lý** trước khi đưa ra kết luận mạnh.

### 8.2. Thử phản ví dụ thay vì chỉ tìm evidence ủng hộ

Với claim "mọi sự kiện cấp quyền admin được phát hiện":

- Nếu một update thay đổi quyền gián tiếp qua group thì sao?
- Nếu audit action thành công nhưng field actor null thì sao?
- Nếu log đến trễ hơn cửa sổ correlation thì sao?
- Nếu rule được tạm tắt khi bảo trì thì sao?
- Nếu cả SIEM và source nằm cùng fault domain thì sao?
- Nếu đối tượng tấn công có quyền tắt logging trước khi thay đổi role thì sao?
- Nếu một authorized change tạo alert thì negative test có đánh giá được nhiễu không?

**Lập luận tốt không chỉ tích lũy bằng chứng thuận chiều**; nó ghi nhận những đường khiến conclusion có thể không đúng và cách giảm hoặc chấp nhận uncertainty.

## 9. Chất lượng evidence: không phải mọi hiện vật đều có trọng lượng như nhau

### 9.1. Sáu thuộc tính quan trọng

| Thuộc tính | Câu hỏi | Vấn đề điển hình |
|---|---|---|
| **Relevance** | Evidence chứng minh đúng phần nào của claim? | Report backup job cho claim failover end-to-end. |
| **Completeness/coverage** | Có bao phủ đúng tài sản, event, tenant, region và kỳ đánh giá? | IAM export thiếu service accounts. |
| **Freshness** | Evidence còn phù hợp với version/scope hiện tại không? | Pentest của release trước, policy đã đổi. |
| **Reliability/provenance** | Nguồn, công cụ, người thu, timestamp và chuyển đổi có rõ? | CSV sửa tay không có raw source. |
| **Independence/corroboration** | Có kiểm tra độc lập hoặc nguồn thứ hai hỗ trợ không? | Chỉ một lời tự xác nhận của control owner. |
| **Reproducibility/testability** | Người khác có thể kiểm tra lại cách suy luận và kết quả không? | Screenshot thiếu query, ID, thời gian và config version. |

Một báo cáo độc lập có thể rất đáng tin **về phần nó thực sự kiểm tra**, nhưng yếu với claim nằm ngoài scope báo cáo. Một test kỹ thuật do nhóm nội bộ thực hiện có thể mạnh cho một behavior cụ thể nếu có provenance và reviewer phù hợp.

### 9.2. Đánh giá sự tương ứng giữa evidence và claim

| Evidence | Hỗ trợ claim nào? | Không nên suy ra |
|---|---|---|
| Policy MFA đã phê duyệt. | Có yêu cầu thiết kế/governance. | MFA thực sự chặn mọi login đặc quyền. |
| IdP policy + effective assignment. | Cấu hình MFA áp dụng tại thời điểm xem. | Mọi phiên trong cả quý đều đã qua MFA. |
| Negative sign-in test. | Một đường đăng nhập trái policy đã bị từ chối trong test. | Tất cả đường bypass đã được kiểm tra. |
| IAM audit + review approvals. | Những thay đổi trong population đã đối chiếu theo kỳ. | Population đầy đủ khi không có coverage evidence. |
| SIEM positive/negative tests. | Rule phân biệt một tập test case và tạo output. | Nguồn production không bao giờ mất log. |
| DR restore exercise. | Recovery hoạt động trong kịch bản/phiên bản/lượng dữ liệu đã thử. | Khôi phục an toàn trong mọi sự cố hay mọi trạng thái compromise. |

### 9.3. Không dùng evidence thiếu để suy "không có vi phạm"

Một số security claims yêu cầu phát biểu về **sự vắng mặt của hành vi**. Đây là thách thức đặc biệt.

Ví dụ một pipeline không ghi event truy cập trái phép trong 30 ngày có thể phản ánh:

1. Không có truy cập trái phép.
2. Có truy cập nhưng control chưa quan sát được.
3. Đã có event nhưng collector, parser hoặc retention làm mất.
4. Có event nhưng bị phân loại sai hoặc không được đưa vào dashboard.
5. Nguồn thiếu hệ thống, tenant hoặc thời điểm quan trọng.

Do đó, cần thêm **coverage và health argument**, không dùng số lượng alert bằng 0 làm bằng chứng độc lập rằng rủi ro bằng 0.

## 10. Ví dụ xuyên suốt: assurance argument cho cloud privileged access

### 10.1. Bài toán

Một tổ chức vận hành ba cloud accounts production và một cluster Kubernetes production. Security objective là giảm rủi ro **tăng quyền quản trị không được phê duyệt**, kể cả khi attacker chiếm danh tính người dùng hoặc automation.

**Top claim G0:**

> Trong phạm vi các accounts và cluster production đã định nghĩa, từ ngày 01 đến 30/11/2026, các đường cấp quyền quản trị trọng yếu được quản lý theo policy P v3; thay đổi ngoài phê duyệt có khả năng phát hiện và được chuyển cho người chịu trách nhiệm theo mục tiêu thời gian đã phê duyệt, với các giới hạn và gaps được công bố.

Đây là claim hỗn hợp về **prevention, detection và response readiness**; nó không khẳng định mọi cuộc tấn công đã bị ngăn chặn tuyệt đối.

### 10.2. Phân rã cấu trúc argument

~~~mermaid
flowchart TD
    G0["G0 — Risk of unauthorized privilege grants is controlled in scope"]
    S0["S0 — Strategy: inventory/approval/detection/response"]
    G1["G1 — Privilege-grant paths and population known"]
    G2["G2 — Approval and enforcement cover authorized paths"]
    G3["G3 — Unauthorized paths create detectable telemetry"]
    G4["G4 — Detections alert responsible responders in time"]
    G5["G5 — Exceptions and drift are governed"]
    E1["E1 — Effective permission inventory and path review"]
    E2["E2 — IAM approval join tests and policy enforcement"]
    E3["E3 — Source health and detection tests"]
    E4["E4 — Alert/case timeline and on-call exercise"]
    E5["E5 — Exception register and review"]
    G0 --> S0
    S0 --> G1
    S0 --> G2
    S0 --> G3
    S0 --> G4
    S0 --> G5
    G1 --> E1
    G2 --> E2
    G3 --> E3
    G4 --> E4
    G5 --> E5
~~~

Phần bên dưới sẽ bổ sung điều kiện và evidence để tránh biến sơ đồ thành danh sách checkbox.

### 10.3. Context và assumptions

**Context C1:** tập cloud accounts/cluster được đối chiếu với authoritative inventory; environment production; policy P v3; thời gian đánh giá theo UTC.

**Context C2:** "privilege-grant path" bao gồm IAM role/policy/grant, group membership, Kubernetes RBAC binding, automation/IaC, delegated admin và break-glass theo threat model.

**Assumption A1:** cloud/Kubernetes audit nguồn trọng yếu đang hoạt động và có đủ event để kiểm tra trong kỳ.

**Assumption A2:** hệ thống phê duyệt và IAM có ID/timestamp đủ đáng tin để nối event với approval.

**Assumption A3:** on-call routing và case system còn hoạt động trong những kịch bản nằm trong scope.

Nếu A1–A3 là giả định trọng yếu, cần tạo **subclaim kiểm chứng** hoặc ghi giới hạn của kết luận. Chỉ dán nhãn assumption không làm chúng trở nên đúng.

### 10.4. Các subclaims và evidence

| Nút | Claim kiểm chứng | Loại evidence | Điều kiện chưa thể suy rộng |
|---|---|---|---|
| **G1** | Inventory bao phủ các principal/đường cấp quyền có thể thay đổi admin theo threat model v2. | Effective IAM/RBAC, role trust, account map, CI/CD paths, review. | Asset/role mới hoặc bypass ngoài threat model. |
| **G2** | Các thay đổi đã kiểm tra có approval hợp lệ đúng actor, target và thời gian, hoặc đường ngăn chặn không cho phép vượt quyền. | Raw change audit, approvals, negative access tests. | API path không nằm trong population hoặc approval không độc lập. |
| **G3** | Những hành vi test trái phê duyệt tạo đủ telemetry và detection theo rule version. | Source health, fixtures, authorized emulation, event-to-alert traces. | Technique biến thể, log loss, parser drift, time-window. |
| **G4** | Alert được gửi đúng người/kênh trong SLA và có đủ context. | Case history, routing rules, timestamps, triage exercises. | Sự cố mất IdP/on-call system hoặc tình huống tải lớn. |
| **G5** | Ngoại lệ được phê duyệt, giới hạn, hết hạn và rà soát. | Exception register, approval, expiry test, periodic review. | Ticket không có thực thi monitoring hoặc ngoại lệ sai scope. |

**Warrant kết hợp:** nếu đường cấp quyền trọng yếu được nhận diện, yêu cầu được enforced/observed, hành vi ngoài phê duyệt được phát hiện và chuyển đúng nơi, cùng với governance cho các ngoại lệ và drift, thì tổ chức có cơ sở đánh giá rủi ro theo mục tiêu đã nêu. Tuy nhiên, độ mạnh của kết luận vẫn phụ thuộc vào **threat model coverage, kết quả thực tế và residual risk**, không phải chỉ vào sự hiện diện của năm mục.

### 10.5. Các test cases để thử phá lập luận

| Test ID | Tình huống | Claim bị thử | Expected evidence |
|---|---|---|---|
| T01 | Một user không được phép thử cấp admin trong sandbox. | G2 | Deny, audit event, actor/target, time. |
| T02 | Một thay đổi quyền được phép có approval hợp lệ. | G2/G3 | Audit đầy đủ, không phân loại sai thành vi phạm theo contract. |
| T03 | Tạo một RBAC binding nhạy cảm không có approval trong cluster test. | G3/G4 | Positive detection, alert/case đúng scope và SLA. |
| T04 | Đổi tên role nhưng giữ quyền hiệu lực nhạy cảm. | G1/G3 | Rule không chỉ dựa vào role name; kết quả theo privilege semantics. |
| T05 | Event đến trễ/trùng hoặc mất trường actor. | G3 | Dedupe/late handling hoặc health finding; không silent pass. |
| T06 | Tắt một nguồn audit synthetic trong môi trường kiểm thử. | A1/G3 | Source health alert, gap report và recovery evidence. |
| T07 | Exception hết hạn hoặc thuộc account khác. | G5 | Không che hành vi trái chính sách, có audit. |
| T08 | Hệ thống case/on-call không nhận alert theo giả định. | A3/G4 | Failover/escalation hoặc finding về delivery gap. |
| T09 | CI/CD service principal có đường cấp admin ngoài UI workflow. | G1/G2 | Đường này nằm trong inventory và được test đúng. |

Các test phải được **ủy quyền và thực hiện trong môi trường thích hợp**. Không cấp cluster-admin production hoặc tắt audit production chỉ để tạo bằng chứng nếu có thể thử ở sandbox/canary được kiểm soát.

### 10.6. Ví dụ hồ sơ đánh giá có gap

Giả sử kết quả như sau:

- G1: inventory bao phủ ba accounts và cluster, nhưng chưa xác minh đầy đủ một delegated-admin path.
- G2: 128/130 IAM changes có approval được kiểm tra hợp lệ; hai thay đổi còn lại không có approval đúng chính sách.
- G3: positive/negative fixtures pass, nhưng source health phát hiện khoảng mất log 23 phút.
- G4: thử alert delivery trong 90 giây, dưới mục tiêu giả định 5 phút.
- G5: một exception đã hết hạn nhưng chưa được review.

**Không thể kết luận G0 đã được chứng minh đầy đủ.** Có bằng chứng phản bác các phần G2/G5; thiếu evidence cho G1; G3 có data gap; chỉ G4 được hỗ trợ trong phạm vi test cụ thể.

Hành động cần làm:

1. Ghi finding cho hai privilege grants không có approval và điều tra tác động.
2. Xác minh delegated-admin path; sửa inventory/threat model.
3. Sửa pipeline telemetry, đánh giá sự kiện trong 23 phút bị thiếu và chạy lại source health/detection tests.
4. Thu hồi hoặc xử lý exception hết hạn theo thẩm quyền.
5. Duy trì kết quả G4 như evidence có phạm vi; không dùng nó để che những nhánh còn fail.
6. Rà soát lại top claim, giới hạn và residual risk sau retest.

**Một argument tốt có thể đưa ra kết luận "chưa đủ assurance"**. Đó là kết quả có giá trị, không phải thất bại của phương pháp.

## 11. Ví dụ thứ hai: assurance argument cho cyber recovery

### 11.1. Đặt top claim

Giả sử dịch vụ thanh toán có mục tiêu DR:

> Trong kịch bản ransomware làm hỏng hệ thống primary, tổ chức có thể khôi phục chức năng ghi và tra cứu giao dịch từ một điểm dữ liệu được đánh giá sạch, trong mục tiêu RTO/RPO đã phê duyệt, mà không đưa credential hoặc đường tấn công đã biết sang môi trường mới.

Đây là claim mạnh, gồm nhiều phần **phải đồng thời đúng**:

- Có recovery point sử dụng được.
- Recovery point phù hợp consistency và RPO.
- Khả năng giải mã, hạ tầng, artifact và dependencies sẵn có.
- Thời gian end-to-end nằm trong RTO.
- Môi trường recovery không có compromise đã biết trong scope kiểm tra.
- IAM, secrets, network và audit vẫn đáp ứng yêu cầu tối thiểu.

### 11.2. Mẫu phân rã theo failure modes

| Claim | Bằng chứng phù hợp | Defeater điển hình |
|---|---|---|
| G-DR1: recovery point tồn tại và bảo toàn. | Backup catalog, versioning, immutable vault controls, integrity checks. | Attacker cùng quyền có thể xóa snapshot và manifest. |
| G-DR2: dữ liệu nhất quán và đúng RPO. | Commit markers, restore test, reconciliation, recovery-point timeline. | Cross-service snapshot không đồng bộ. |
| G-DR3: nền tảng có thể khôi phục trong RTO. | Exercise end-to-end có timestamps, capacity, IAM/KMS, DNS và app test. | Chỉ test restore DB; KMS key ở site primary. |
| G-DR4: điểm khôi phục đủ sạch theo threat model. | Isolated restore, artifact provenance, review persistence, detection scans. | Malware tồn tại trong image/backup hoặc credential cũ tái sử dụng. |
| G-DR5: điều hành DR đúng quy trình. | Runbook execution, roles, approvals, failover/failback evidence. | SSO bị lỗi và break-glass chưa từng test. |

Một restore exercise chỉ test G-DR3 ở điều kiện bình thường **không chứng minh G-DR4** cho tình huống ransomware. Nếu điểm dữ liệu sạch cuối cùng nằm ngoài RPO, có thể không đạt tất cả mục tiêu cùng lúc. Argument phải công khai trade-off và đưa tới người có thẩm quyền quyết định, không lặng lẽ điều chỉnh timestamp để đạt KPI.

### 11.3. So sánh mức kết luận

**Kết luận không hợp lệ:**

> Mọi thử nghiệm restore backup pass, do đó dịch vụ chắc chắn khôi phục an toàn sau mọi ransomware.

**Kết luận có phạm vi:**

> Với bài diễn tập RC-2026-11 ở recovery site B, nhóm đã khôi phục từ snapshot S, xác minh dữ liệu và các chức năng F trong thời gian T; các bước kiểm tra artifact, secrets và persistence theo kịch bản X không phát hiện dấu hiệu compromise đã biết. Kết quả hỗ trợ mục tiêu phục hồi đối với phạm vi và điều kiện bài diễn tập. Các attack paths ngoài kịch bản X và khả năng compromise trước thời điểm snapshot còn là residual uncertainty.

## 12. Đánh giá độ tin cậy của argument

Không nên chuyển một assurance case thành **một tỷ lệ phần trăm tin cậy tùy ý**. Độ tin cậy của kết luận phụ thuộc nhiều chiều:

| Chiều | Câu hỏi |
|---|---|
| **Claim clarity** | Claim đủ xác định và phù hợp quyết định cần ra? |
| **Argument validity** | Chiến lược phân rã có đầy đủ tiền đề và quan hệ suy luận hợp lý? |
| **Evidence quality** | Chứng cứ phù hợp, đầy đủ, đáng tin, mới và có phạm vi chính xác? |
| **Coverage** | Threats, assets, lifecycle, identity paths và exceptions có bị bỏ sót? |
| **Assumptions & dependencies** | Những giả định quan trọng có được kiểm tra hoặc ghi rủi ro? |
| **Defeaters** | Có phản ví dụ/finding nào chưa được xử lý làm yếu top claim? |
| **Change sensitivity** | Thay đổi phiên bản, môi trường, vendor hoặc policy có làm bằng chứng cũ mất hiệu lực? |
| **Independence of review** | Reviewer có thể đánh giá khác với người triển khai control không? |

### 12.1. Phân biệt confidence của evidence và confidence của suy luận

Ví dụ:

- Evidence có độ tin cậy cao: IAM audit API export đã xác minh toàn vẹn, đầy đủ phạm vi thời gian.
- Nhưng inference yếu: từ việc không có sự kiện cấp role trực tiếp suy ra không thể có privilege escalation qua một role trust path không kiểm tra.

Ngược lại, một lập luận được phân rã rất hợp lý nhưng chỉ dựa trên **self-attestation** và không có operational test vẫn chưa đủ assurance.

**Phải đánh giá cả hai:** độ tin cậy dữ liệu **và** tính hợp lý của mối liên hệ từ dữ liệu đến claim.

### 12.2. Dùng đánh giá định tính có kiểm soát

Một chương trình có thể dùng các nhãn:

- **Supported:** evidence đủ theo criterion và scope, không còn defeater trọng yếu chưa xử lý.
- **Partially supported:** một số subclaims có evidence nhưng còn phần chưa đánh giá hoặc residual uncertainty đã ghi.
- **Not supported / contradicted:** có evidence chống lại claim hoặc criterion quan trọng fail.
- **Inconclusive:** evidence hoặc context chưa đủ để đánh giá.
- **Out of scope:** điều kiện không nằm trong claim đã xác định.

Nếu dùng điểm số, phải công bố **phương pháp, ý nghĩa, giới hạn, ngưỡng và ai phê duyệt**. Điểm tổng cao không được bù một điều kiện bắt buộc bị fail, ví dụ backup không giải mã được hoặc quyền admin không có approval, nếu top claim yêu cầu điều đó.

### 12.3. Tránh đếm trùng evidence

Ba dashboard khác nhau có thể đều lấy dữ liệu từ cùng một SIEM index. Nếu index bị thiếu event, cả ba nguồn cùng sai.

**Corroboration thực sự** đòi xem độ độc lập tương đối: log nguồn, event tập trung, configuration history và authorized tests có thể cung cấp các góc nhìn bổ sung. Đếm số file không phải đếm số nguồn độc lập.

## 13. Cách mô hình hóa argument ở dạng dữ liệu

Một hệ thống nội bộ có thể lưu argument graph, evidence và trạng thái để hỗ trợ versioning và review.

### 13.1. YAML minh họa

~~~yaml
assurance_case:
  id: AC-PRIV-2026-11
  version: "1.2"
  owner: security-assurance-team
  system: order-platform
  scope:
    environments: ["production"]
    period_start: "2026-11-01T00:00:00Z"
    period_end_exclusive: "2026-12-01T00:00:00Z"
  top_claim: G0
  context:
    - id: C1
      description: "Inventory accounts, clusters and IAM policy P v3"
      evidence_ref: "EV-INV-01"
  assumptions:
    - id: A1
      statement: "Audit coverage complete for in-scope privileges"
      verification_status: under-review
      impact_if_false: high
  nodes:
    - id: G0
      type: goal
      statement: "Privileged changes controlled within defined scope"
      strategy_ref: S0
    - id: S0
      type: strategy
      rationale: "Reason over coverage, approval, detection and response"
      support_goals: [G1, G2, G3, G4]
    - id: G1
      type: goal
      statement: "All relevant privilege paths inventoried"
      evidence_refs: ["EV-IAM-01", "EV-REVIEW-02"]
    - id: G2
      type: goal
      statement: "Privileged grants satisfy approved workflow"
      evidence_refs: ["EV-APPROVAL-03"]
    - id: G3
      type: goal
      statement: "Unauthorized grants are detectable"
      evidence_refs: ["EV-DET-04", "EV-HEALTH-05"]
    - id: G4
      type: goal
      statement: "Alerts delivered to responders within objective"
      evidence_refs: ["EV-CASE-06"]
  defeaters:
    - id: D1
      affected_node: G3
      description: "Collector had a 23-minute telemetry gap"
      status: unresolved
      finding_ref: "FIND-2026-017"
  assessment:
    current_status: partially-supported
    last_reviewed: "2026-11-28"
    limitations:
      - "Delegated-admin path needs further assessment"
~~~

**Đây là schema học tập, không phải định dạng GSN chuẩn hoặc tiêu chuẩn đánh giá confidence.** Những trường status cần mapping tới quy trình của tổ chức; không tự động cho G0 thành supported chỉ vì các child node có một vài evidence_refs.

### 13.2. Điều kiện tự động kiểm tra tính nhất quán graph

Một công cụ có thể kiểm tra những vấn đề cấu trúc:

- Goal ID, strategy ID, evidence reference có tồn tại không?
- Nút Goal đã có hướng hỗ trợ hay đang undeveloped?
- Context và assumption có owner, phiên bản và scope?
- Evidence có hiệu lực, không bị stale theo tiêu chí đã định?
- Defeater hoặc finding đang mở có liên quan node không?
- Có node không thể truy từ top claim, evidence orphan hoặc vòng phụ thuộc logic không hợp lý?
- Status của top claim có mâu thuẫn với subclaim bắt buộc đang FAIL?
- Source/control versions có đồng nhất với kỳ đánh giá không?

Tuy nhiên, **kiểm tra đồ thị bằng máy không tự chứng minh inference hợp lý về bảo mật**. Việc đánh giá đủ coverage, strength của claim và implications từ evidence cần người hiểu hệ thống, rủi ro và kỹ thuật.

### 13.3. Pseudocode kiểm soát phát hành kết luận

~~~text
function review_assurance_case(case):
    require top_claim_has_scope_and_version(case)
    require all_material_goals_have_strategy_or_evidence(case)
    require contexts_and_assumptions_are_recorded(case)

    for each material_goal:
        validate_source_and_freshness_of_evidence()
        check_population_and_test_scope()
        check_open_defeaters_and_findings()
        review_inference_from_evidence_to_claim()

    if any mandatory_claim_is_contradicted:
        return "NOT SUPPORTED", findings

    if missing_material_evidence_or_unresolved_high_impact_assumption:
        return "INCONCLUSIVE OR PARTIAL", limitations

    if argument_is_relevant_and_sufficient_in_defined_scope:
        return "SUPPORTED WITH EXPLICIT SCOPE", evidence_refs

    return "REVIEW REQUIRED", open_questions
~~~

Pseudocode là **khung quy trình**, không định nghĩa thuật toán quyết định thay auditor. Nó cố ý không dùng phép cộng điểm để che một subclaim bắt buộc bị fail.

## 14. Duy trì living assurance argument

Security assurance là một hoạt động liên tục. Argument phải có vòng đời tương tự một artifact kỹ thuật quan trọng, thay vì chỉ làm một lần trước cuộc kiểm toán.

### 14.1. Những thay đổi có thể làm claim hết hiệu lực

- Bổ sung cloud account, cluster, tenant hoặc vùng xử lý dữ liệu.
- Thay authentication flow, IAM role, delegated admin hoặc SSO/IdP.
- Deploy application release có endpoint/API behavior mới.
- Thay parser, log source, SIEM rule, detection threshold, alert routing.
- Thêm nhà cung cấp hoặc đổi subprocessor/cloud region.
- Đổi backup, replication, key rotation, IaC hoặc DR topology.
- Bổ sung một threat scenario quan trọng hoặc phát hiện attack path mới.
- Evidence hết kỳ phù hợp, test fail hoặc có incident trái với claim cũ.
- Một assumption trọng yếu không còn đúng hoặc finding đã được khắc phục.

### 14.2. Change impact analysis

Khi đổi một control hoặc component:

1. Xác định dependency tới các Goal, Context, Assumption và Evidence.
2. Đánh dấu node có thể bị ảnh hưởng và review confidence/status.
3. Xác định test/evidence cần chạy lại, tránh retest toàn bộ không cần thiết.
4. Thu evidence phiên bản mới và đối chiếu điều kiện acceptance.
5. Xử lý những defeater mới và cập nhật limitation.
6. Lưu reviewer decision, effective date và version mới của assurance case.

Ví dụ đổi schema Kubernetes audit khiến field actor.id chuyển dạng. Các subclaims về event attribution, detection và alert context cần được đánh giá lại. Nó không nhất thiết làm mất hiệu lực một pen-test report độc lập về TLS, nhưng có thể ảnh hưởng top claim nếu detection là điều kiện bắt buộc.

### 14.3. Version và evidence freshness

Một assurance case nên ghi:

- Case ID/version, top claim version và thời kỳ đánh giá.
- Threat model version, system boundary và policy/control version.
- Evidence ID, source, tool/query version, timestamp, integrity và môi trường.
- Assessment result, assumptions, defeaters, limitations và owner.
- Thời điểm reviewer chấp thuận; sự kiện khiến phê duyệt phải được xem lại.
- Lịch đánh giá định kỳ và tần suất test phù hợp risk.

Không cần ép tất cả evidence cùng một thời hạn sử dụng. **Một policy được duyệt** có vòng đời khác **snapshot quyền IAM** hay **bài test khôi phục**; độ tươi cần phù hợp loại claim và tốc độ thay đổi hệ thống.

## 15. Review argument: người đánh giá nên hỏi gì?

Một buổi **argument review** không chỉ kiểm tra các ô màu xanh trên sơ đồ. Cần đặt câu hỏi nhằm tìm điểm yếu của suy luận.

### 15.1. Checklist câu hỏi cho reviewer

| Mối quan tâm | Câu hỏi review |
|---|---|
| **Top claim** | Claim có phạm vi, kỳ, release, security objective và điều kiện giới hạn đủ rõ? |
| **Strategy** | Tại sao chọn cách phân rã này? Các subclaims có thực sự đủ hỗ trợ claim cấp trên? |
| **Coverage** | Có attack path, principal, data flow, site hoặc lifecycle mode trọng yếu nào bị bỏ sót? |
| **Assumptions** | Assumption nào nếu sai sẽ đảo ngược kết luận? Chúng được kiểm chứng đến đâu? |
| **Evidence** | Nguồn nào độc lập? Population có đầy đủ? Test có đúng môi trường và thời gian? |
| **Causal link** | Test pass chứng minh điều gì? Có suy rộng ra các điều kiện chưa thử không? |
| **Defeaters** | Có phản ví dụ hoặc finding chưa được xử lý? Có bị che bằng risk acceptance không? |
| **Uncertainty** | Phần nào còn unknown/inconclusive và tác động lên quyết định là gì? |
| **Change** | Khi control/asset/release đổi, bằng cách nào nhận biết argument cần cập nhật? |
| **Ownership** | Ai chịu trách nhiệm về claim, evidence, review và remediation? |

### 15.2. Độc lập và tính khách quan

Người xây control và viết argument có thể có hiểu biết kỹ thuật sâu nhưng cũng có động cơ bảo vệ thiết kế của mình. Nên có review độc lập tương ứng rủi ro, ít nhất là peer reviewer có khả năng chất vấn assumptions và evidence.

Người review không được suy diễn "không đủ evidence" thành "control chắc chắn bị tấn công", nhưng cũng không nên đánh dấu PASS cho điểm chưa xác minh.

### 15.3. Hồ sơ review

Một review record gồm:

- Case ID/version, top claim, scope và ngày review.
- Danh sách reviewer, owner và vai trò.
- Các nodes/evidence đã xem, nguồn và phiên bản.
- Defeaters, câu hỏi chưa trả lời, findings liên quan.
- Quyết định: supported, partial, contradicted hoặc inconclusive trong phạm vi.
- Điều kiện phê duyệt, limitations, deadline và trigger review lại.

Đối với môi trường có yêu cầu audit, tài liệu phải đủ để một người không dự buổi review vẫn truy vết được lý do kết luận.

## 16. Mẫu assurance package và traceability

~~~text
security-assurance/
  cases/
    AC-PRIV-2026-11/
      claim-and-scope.md
      argument-graph.yaml
      context-and-assumptions.md
      threat-model-reference.md
      control-mapping.csv
      evidence-index.csv
      review/
        inference-review.md
        counterexamples-and-defeaters.csv
        limitations-and-risk-decision.md
      tests/
        approval-workflow-tests.json
        effective-permission-review.csv
        detection-regression-results.json
        source-health-and-ingestion.json
        response-delivery-timeline.csv
      evidence/
        iam-audit-references.md
        approved-change-references.md
        tool-and-source-versions.txt
        integrity-and-provenance-manifest.txt
      findings/
        remediation-register.csv
        retest-results.json
      decisions/
        reviewer-signoff.md
        next-review-and-change-triggers.md
~~~

Cấu trúc này **mang tính minh họa**; tài liệu thực có thể nằm trong GRC platform, hệ thống quản lý evidence, SIEM, issue tracker và repository với quyền phù hợp.

Mỗi **evidence record** cần có:

- Evidence ID và node/claim ID được hỗ trợ.
- Control/test ID, source và asset ID.
- Khoảng thời gian, timezone, environment, account/tenant.
- Tool/version, query, fixture, parser và commit/digest nếu liên quan.
- Expected vs actual, test scope, các lỗi và negative cases.
- Data provenance, transformation, integrity và mức độ đầy đủ.
- Owner, reviewer, classification, retention và hạn review lại.
- Link tới finding/exception khi có sai lệch.

Một screenshot không có timestamp và nguồn không đủ để hỗ trợ claim quan trọng; **log có hash** cũng không tự chứng minh dữ liệu đầu vào đầy đủ.

## 17. Các lỗi lập luận phổ biến

### 17.1. Circular reasoning

Ví dụ:

> Hệ thống an toàn vì đã tuân thủ chính sách; chính sách được cho là tuân thủ vì hệ thống an toàn.

Không có evidence độc lập hoặc tiêu chí rõ. Phải quay lại source requirement và thử control thực tế.

### 17.2. Appeal to authority

> Vendor có chứng nhận, nên mọi thành phần tích hợp của tổ chức đều an toàn.

Chứng nhận/báo cáo có scope và thời kỳ. Cần xác định những control do khách hàng thực hiện, exceptions, subservice và feature ngoài scope.

### 17.3. Cherry-picking

> Chỉ chọn những test pass để đưa vào assurance case.

Bỏ fail/negative/edge cases khiến claim mạnh giả tạo. Evidence package phải có kết quả trái chiều, limit và quyết định remediation.

### 17.4. Hasty generalization

> Một API endpoint trả 403 cho một role, do đó toàn bộ authorization của ứng dụng chính xác.

Một test case chỉ hỗ trợ phạm vi của nó. Cần population, test matrix, boundary cases, bypass paths và independent reviews.

### 17.5. Correlation vs. causation

> Sau khi bật SIEM, số incidents giảm, vậy SIEM đã ngăn tấn công.

Có thể do threat activity thay đổi, phát hiện giảm hoặc control khác tác động. Cần đo detection coverage và response outcomes, không quy hiệu quả từ một xu hướng thiếu đối chứng.

### 17.6. Absence of evidence

> Không thấy log truy cập trái phép nghĩa là không có truy cập trái phép.

Cần chứng minh telemetry health, coverage, completeness, retention và detection behavior.

### 17.7. False sense of independence

> Ba dashboards cùng xác nhận hệ thống không có event xấu.

Nếu cùng dùng một data source bị thiếu record, ba dashboard không phải ba nguồn xác nhận độc lập.

### 17.8. Overclaiming from a positive test

> Detection tạo alert trong một lần replay nên luôn phát hiện trong năm phút.

Replay có thể bỏ qua sự kiện nguồn, parser, queue và on-call. Phải gắn mức test T1/T3/T5 với claim tương ứng.

### 17.9. Ignoring lifecycle and emergency modes

> MFA và logging đạt trong ngày vận hành bình thường, vậy chế độ break-glass và DR cũng đạt.

Emergency IAM, DR network và logging path có thể khác; cần xem riêng.

### 17.10. Treating exception as evidence of compliance

> Một control fail nhưng có giấy risk acceptance nên top claim vẫn PASS.

Risk acceptance có thể quản lý residual risk **trong quyền hạn**; không làm evidence trái chiều biến mất và không tự miễn yêu cầu bắt buộc từ nguồn bên ngoài.

## 18. Bài tập tình huống: phản biện một assurance case yếu

**Bối cảnh:** tổ chức quản lý đơn hàng nói rằng "dữ liệu khách hàng không thể bị truy cập trái phép". Argument hiện tại gồm:

- G0: Dữ liệu khách hàng an toàn.
- G1: IAM dùng MFA.
- G2: Database encryption được bật.
- G3: SIEM đang chạy.
- Evidence: một ảnh IAM, một ảnh DB console và một biểu đồ alerts.

Dữ liệu có thể được truy cập qua API, support SaaS, backup, service account và một integration với analytics provider.

### 18.1. Nhiệm vụ 1 — Tìm lỗ hổng

Xác định ít nhất **tám điều cần hỏi** trước khi chấp nhận G0. Gợi ý:

1. Claim "không thể" có phù hợp với assurance thực tế không?
2. Có đủ inventory về dữ liệu, actors, integrations và attack paths không?
3. MFA có bao phủ service identities và bypass paths không, hay chỉ interactive login?
4. Database encryption có ngăn misuse của một danh tính đã có quyền đọc không?
5. API authorization đã có negative tests và object-level access controls chưa?
6. SaaS/subprocessors có quyền gì? Token được quản lý và giám sát ra sao?
7. Backup/log/exports có chứa dữ liệu có thể đọc không?
8. SIEM có nhận event truy cập nhạy cảm từ tất cả nguồn không?
9. Có thay đổi release/schema sau ngày screenshot không?
10. Findings và exceptions đang mở có ảnh hưởng top claim không?

### 18.2. Nhiệm vụ 2 — Viết lại top claim

Một ví dụ:

> Trong phiên bản Order Platform R và các data flows production được liệt kê tại inventory D, các truy cập đọc/sửa thông tin khách hàng chịu authorization theo policy A; các đường truy cập trọng yếu đã được đánh giá bằng tests và audit, còn các gaps và rủi ro được ghi nhận trong scope đánh giá từ ngày X đến Y.

Top claim này thận trọng hơn nhưng có thể kiểm chứng. Cần nêu rõ authorization requirements và test acceptance sau khi chọn nguồn policy có hiệu lực.

### 18.3. Nhiệm vụ 3 — Tạo argument tree

Yêu cầu tối thiểu:

- Một context cho inventory, release, policy và data classification.
- Một assumption về độ đầy đủ logging và cách kiểm tra nó.
- Subclaim về identity và authorization.
- Subclaim về data scope và third-party access.
- Subclaim về encryption/key management, bao gồm backup.
- Subclaim về monitoring/detection.
- Subclaim về exceptions, findings và change control.
- Với mỗi subclaim, một test/evidence cụ thể và một defeater có thể làm kết luận sai.

### 18.4. Nhiệm vụ 4 — Đánh giá bằng chứng

Giả sử:

- Negative authorization tests đã kiểm tra 12/15 endpoint.
- Kết quả tests pass cho 12 endpoint.
- Audit ở một cloud account bị thiếu hai ngày.
- Nhà cung cấp analytics chưa cung cấp phạm vi evidence cho feature mới.
- Một integration token có quyền đọc toàn bộ customer database nhưng business flow chỉ cần purchase events.

Hãy phân loại từng subclaim thành supported/partial/not supported/inconclusive và giải thích vì sao. Không lấy 12/15 làm xác suất bảo mật tổng quát, không coi thiếu audit là không có truy cập và không biến chứng cứ nhà cung cấp ngoài phạm vi thành PASS.

### 18.5. Nhiệm vụ 5 — Đề xuất hành động

Đề xuất:

1. Thử ba endpoint còn lại và xác định chúng thuộc threat/path nào.
2. Sửa data/identity inventory nếu cần và xây test coverage phù hợp.
3. Điều tra telemetry gap và bổ sung source health assurance.
4. Giảm quyền integration token và test denial các đường không được phép.
5. Rà soát scope vendor evidence và dữ liệu feature mới.
6. Cập nhật top claim, argument strategy, evidence index và defeaters.
7. Ghi owner, deadline, retest, reviewer decision và trigger tái đánh giá.

## 19. Checklist xây dựng security assurance argument

- [ ] Top claim mô tả mục tiêu rõ ràng, trong system boundary, môi trường, release và thời kỳ đánh giá.
- [ ] Có threat/risk context, security objectives và nguồn requirement được phê duyệt.
- [ ] Các thuật ngữ quan trọng được định nghĩa, không dùng "an toàn hoàn toàn" hoặc "mọi tấn công" một cách vô căn cứ.
- [ ] Strategy phân rã giải thích tại sao các subclaims cần thiết và đủ trong scope.
- [ ] Mỗi material subclaim có owner, test hoặc evidence thích hợp.
- [ ] Có warrant hoặc rationale cho các mối suy luận không hiển nhiên.
- [ ] Assumptions được ghi, phân loại tác động và có kế hoạch xác minh nếu trọng yếu.
- [ ] Context và justifications tách khỏi evidence và goals.
- [ ] Coverage gồm users, service accounts, API, cloud, containers, third parties và các mode vận hành phù hợp.
- [ ] Evidence ghi scope, population, version, timestamp, provenance, integrity, quality và limitations.
- [ ] Đã phân biệt design, implementation và operating effectiveness.
- [ ] Đã kiểm tra positive, negative, boundary, integration và end-to-end khi claim cần.
- [ ] Có kiểm tra telemetry completeness và không suy luận từ "không thấy event" thành "không có rủi ro".
- [ ] Defeaters, counterexamples và open findings được liên kết với claim chịu ảnh hưởng.
- [ ] Không dùng risk acceptance để che kết quả FAIL hay evidence missing.
- [ ] Confidence được đánh giá cả ở evidence và suy luận, không dựa trên số file hoặc màu dashboard.
- [ ] Reviewer có thể kiểm tra độc lập lý do từ subclaims và evidence tới top claim.
- [ ] Những claim chưa đủ support được ghi partial/inconclusive với giới hạn rõ.
- [ ] Có change triggers, review date, owner, kế hoạch retest và versioning.
- [ ] Kết luận không vượt quá scope và sức mạnh của phép kiểm tra.

## 20. Câu hỏi tự đánh giá

1. Vì sao một tập hợp báo cáo và log không tự động tạo thành một assurance argument?
2. Trong Claim–Argument–Evidence, phần nào trả lời "vì sao bằng chứng này hỗ trợ kết luận"?
3. Goal, Strategy, Context, Assumption, Justification và Solution trong GSN khác nhau thế nào?
4. Tại sao "SIEM nhận log" không tự suy ra "mọi hành vi tăng quyền trái phép được phát hiện"?
5. Hãy nêu một missing premise khi đánh giá tất cả lần cấp quyền admin chỉ từ change tickets.
6. Phân biệt rebutting, undermining và undercutting defeater bằng ba ví dụ kỹ thuật.
7. Nếu một unit test detection pass nhưng log production thiếu nguồn, claim ở tầng nào vẫn chưa được hỗ trợ?
8. Vì sao hai artifact có SHA-256 chính xác vẫn có thể không chứng minh source coverage?
9. Tại sao cùng một cloud failure domain có thể làm yếu những evidence tưởng là độc lập?
10. Phân biệt suy luận AND và OR khi phân rã claims; khi nào một đường OR không hợp lệ?
11. Nếu một assumption trọng yếu chưa xác minh, top claim nên được báo cáo thế nào?
12. Một restore test pass có đủ chứng minh cyber recovery an toàn sau ransomware không? Cần subclaims gì?
13. Khi thay IAM policy hoặc thêm cloud account, những phần nào của argument phải review lại?
14. Một reviewer nên hỏi gì để phát hiện việc chọn evidence chỉ ủng hộ kết luận mà bỏ qua test fail?
15. Hãy tự viết top claim cho một hệ thống quen thuộc, tạo ít nhất bốn subclaims, bốn evidence records và ba defeaters có kế hoạch xử lý.

**Điểm cốt lõi:** **Argument là phần lý giải có cấu trúc của một assurance case**, nối mục tiêu bảo mật với các subclaims, assumptions, phương pháp kiểm chứng và evidence. Một argument có giá trị không hứa hẹn bảo mật tuyệt đối; nó cho thấy **điều gì được hỗ trợ, vì sao được hỗ trợ, trong điều kiện nào, bởi bằng chứng nào và những phản ví dụ hoặc khoảng trống nào còn tồn tại**. Đó là nền tảng để security assurance trở thành quá trình ra quyết định dựa trên bằng chứng, có thể audit và được cập nhật liên tục.
