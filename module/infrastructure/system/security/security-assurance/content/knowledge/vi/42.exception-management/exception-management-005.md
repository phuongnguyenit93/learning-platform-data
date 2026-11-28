# Risk owner phê duyệt: Quyết định chấp nhận ngoại lệ bảo mật có trách nhiệm và bằng chứng

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Giải thích **risk owner phê duyệt** trong quy trình **exception management** và phân biệt với control owner, requestor, security reviewer, compliance/legal và người triển khai.
2. Xác định ngoại lệ nào có thể được **risk owner chấp nhận**, ngoại lệ nào phải **escalate**, và vì sao không thể dùng phê duyệt nội bộ để bỏ qua nghĩa vụ pháp luật hoặc hợp đồng bắt buộc.
3. Chuyển một đề nghị ngoại lệ thành **hồ sơ quyết định** có phạm vi, nguyên nhân, kịch bản rủi ro, tác động, controls bù trừ, residual risk, thời hạn và tiêu chí kết thúc.
4. Đánh giá **risk appetite, quyền phê duyệt, xung đột lợi ích, separation of duties** và chất lượng bằng chứng trước khi ký quyết định.
5. Thiết kế workflow phê duyệt, từ chối, phê duyệt có điều kiện, chuyển cấp, giám sát, gia hạn và thu hồi ngoại lệ.
6. Xây dựng **approval record, exception register, audit evidence và test cases** để auditor truy vết từ quyết định tới thực trạng hệ thống.
7. Đo lường chất lượng quản lý ngoại lệ bằng các KPI và kết nối **risk → control gap → approval → monitoring → remediation → retest**.

## 1. Vì sao risk owner phải phê duyệt?

Trong thực tế, không phải mọi security control đều có thể đáp ứng ngay ở mọi thời điểm. Một thiết bị cũ không hỗ trợ agent bảo mật, một ứng dụng cần quyền đặc biệt trong giai đoạn migration, hoặc một bản vá không thể triển khai đúng hạn vì ảnh hưởng đến hệ thống giao dịch. Đội kỹ thuật có thể đề nghị **exception**: tạm thời không đáp ứng một yêu cầu hoặc dùng phương án khác đã được xem xét.

Nhưng **ai có quyền quyết định tổ chức sẽ sống chung với rủi ro đó**?

- Kỹ sư hiểu điều kiện kỹ thuật, nhưng có thể không chịu trách nhiệm cuối cùng về thiệt hại kinh doanh.
- Security team đánh giá mối đe dọa, controls và hậu quả, nhưng không nhất thiết có quyền chấp nhận mọi rủi ro của một hoạt động kinh doanh.
- Audit/compliance xác minh các yêu cầu và bằng chứng, nhưng không nên tự biến mình thành người cấp ngoại lệ cho phát hiện do chính mình kiểm toán.
- **Risk owner** là người được giao trách nhiệm quản lý một rủi ro xác định và, trong **giới hạn thẩm quyền**, có quyền quyết định cách xử lý rủi ro còn lại.

**Phê duyệt của risk owner** là một quyết định quản trị có trách nhiệm, có căn cứ và có thời hạn về việc chấp nhận một mức rủi ro tồn dư trong một phạm vi cụ thể. Đây **không phải giấy phép vô thời hạn cho phép bỏ qua security baseline**.

Trong mô-đun **SECURITY_SECURITY_ASSURANCE**, một quyết định ngoại lệ chỉ có giá trị assurance khi có thể kiểm chứng: điều gì không đạt, vì sao, tác động tới security objectives nào, bằng chứng đã được xét, ai có thẩm quyền, điều kiện bảo vệ thay thế ra sao, và khi nào phải khắc phục hoặc đánh giá lại.

### 1.1. Những thuật ngữ không nên đánh đồng

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Policy/control exception** | Một đối tượng được phép tạm lệch khỏi yêu cầu nội bộ cụ thể theo quy trình. | Chưa bật control EDR chuẩn trên máy chủ cũ đến khi thay hệ điều hành. |
| **Risk acceptance** | Quyết định chấp nhận residual risk trong thẩm quyền và appetite đã đặt. | Chủ sở hữu dịch vụ chấp nhận nguy cơ tăng trong 30 ngày, có giám sát bù trừ. |
| **Waiver** | Sự miễn áp dụng một yêu cầu theo cơ chế và ngôn ngữ quản trị cụ thể; có thể mang ý nghĩa khác giữa tổ chức. | Một chính sách nội bộ cho phép waiver đã được phê duyệt. |
| **Compensating control** | Biện pháp thay thế hoặc bổ sung nhằm giảm rủi ro khi control chuẩn không có. | Hạn chế mạng, allowlisting, giám sát host và review truy cập. |
| **Non-applicability (N/A)** | Yêu cầu không áp dụng vì điều kiện phạm vi được xác minh. | Chính sách MFA cho human login không áp dụng trực tiếp như vậy với non-interactive workload identity. |
| **Finding / nonconformity** | Bằng chứng cho thấy một yêu cầu áp dụng chưa được đáp ứng. | Một server production thiếu EDR theo baseline bắt buộc. |
| **Remediation plan** | Kế hoạch đưa hệ thống về đáp ứng yêu cầu hoặc loại bỏ nguy cơ. | Nâng OS, triển khai EDR, test lại và đóng exception. |
| **Temporary emergency deviation** | Ngoại lệ khẩn cấp theo quy trình riêng có kiểm soát và đánh giá hồi tố khi được phép. | Tạm thay đổi firewall để khôi phục một dịch vụ thiết yếu. |

Một ngoại lệ được phê duyệt **không tự chứng minh control đã đạt**. Có thể hồ sơ tuân thủ vẫn ghi **nonconformity**, trong khi rủi ro phát sinh được quản trị bằng một quyết định chấp nhận có điều kiện. Phải báo cáo riêng **control status**, **risk status** và **exception status**.

### 1.2. Tại sao không thể chỉ dùng chữ ký?

Một risk owner ký "đồng ý" nhưng không đọc evidence, không hiểu mức phơi nhiễm hoặc không có quyền đối với rủi ro đó thì quyết định **yếu về assurance**.

Ngược lại, hồ sơ chuẩn cần cho thấy **lý do có thể kiểm tra**:

- Đối tượng thuộc ranh giới hệ thống và dịch vụ nào.
- Yêu cầu nào không được đáp ứng, nguồn và phiên bản nào.
- Threat scenario và tác động có căn cứ.
- Tại sao không thể khắc phục ngay, lựa chọn thay thế đã cân nhắc.
- Residual risk sau các controls bù trừ, và mức uncertainty.
- Điều kiện phê duyệt, hiệu lực, owner, cảnh báo và ngày kết thúc.
- Ai đã xác nhận technical facts, ai rà soát tuân thủ, ai phê duyệt trong thẩm quyền.

**Approval là một sự kiện quản trị cần bằng chứng, không phải một trường boolean trong ticket.**

## 2. Phân vai: risk owner không phải control owner

### 2.1. Các bên thường tham gia

| Vai trò | Trách nhiệm chính | Điều không nên tự làm |
|---|---|---|
| **Requestor** | Mô tả gap, nhu cầu, thời gian, ảnh hưởng và phương án sửa. | Tự tuyên bố rủi ro được chấp nhận. |
| **Control owner** | Giải thích control chuẩn, khả năng triển khai, kiểm thử và remediation. | Tự hạ tiêu chí để coi gap đã đạt. |
| **Service/business owner** | Làm rõ tác động tới dịch vụ, khách hàng, chi phí và deadline. | Tự bỏ qua nghĩa vụ ngoài thẩm quyền. |
| **Security reviewer / risk analyst** | Threat assessment, mức rủi ro, controls bù trừ, evidence, cảnh báo và khuyến nghị. | Thay quyết định của risk owner nếu không có ủy quyền chính thức. |
| **Risk owner** | Chịu trách nhiệm về risk decision, phê duyệt/từ chối/chuyển cấp theo thẩm quyền. | Phê duyệt rủi ro vượt risk appetite hoặc thiếu dữ liệu trọng yếu. |
| **Legal / privacy / compliance** | Xác nhận nghĩa vụ áp dụng, điều kiện hợp đồng và giới hạn có thể miễn trừ. | Đánh đồng chấp nhận rủi ro với miễn nghĩa vụ bắt buộc. |
| **Risk committee / executive approver** | Quyết định rủi ro vượt mức phân quyền của owner, tác động liên đơn vị hoặc chiến lược. | Chấp thuận mơ hồ không có scope và trách nhiệm triển khai. |
| **Internal audit / independent assurance** | Đánh giá quy trình, bằng chứng, tính phù hợp của authority và effectiveness. | Là người duy nhất tự phê duyệt ngoại lệ mình đang kiểm tra. |

**Tên chức danh không tự xác định thẩm quyền.** Cần có **delegation-of-authority (DoA)** hoặc policy quản trị rủi ro được phê duyệt, nêu ngưỡng, điều kiện và người thay thế khi risk owner vắng mặt.

### 2.2. Một risk có thể liên quan nhiều owner

Ví dụ ngoại lệ **tắt kiểm tra certificate trên một API kết nối nhà cung cấp** có thể tác động:

- Đội ứng dụng vận hành API.
- Data owner chịu trách nhiệm thông tin khách hàng.
- Security owner quản lý trust boundary.
- Legal/vendor management chịu nghĩa vụ hợp đồng.
- Đơn vị kinh doanh phụ thuộc giao dịch.

Nếu rủi ro vượt một domain, risk owner được chỉ định cần **tham vấn các owners liên quan hoặc escalate** theo quy tắc. Không dùng chữ ký của một trưởng nhóm kỹ thuật để mặc định rủi ro của mọi bên đã được chấp nhận.

### 2.3. Separation of duties (SoD)

Một mô hình mong muốn:

1. **Requestor** trình bày nhu cầu.
2. **Security/technical reviewer** xác thực facts và ước lượng risk.
3. **Legal/compliance** rà soát ràng buộc nếu liên quan.
4. **Risk owner có thẩm quyền** đưa ra quyết định.
5. **Control owner** triển khai điều kiện bù trừ và remediation.
6. **Assurance reviewer** độc lập xác minh trạng thái và bằng chứng.

Trong tổ chức nhỏ, không phải lúc nào cũng có sáu người khác nhau. Khi cùng một người giữ nhiều vai trò, phải **công bố xung đột lợi ích và có biện pháp kiểm soát bù trừ** như second reviewer, escalation hoặc log phê duyệt không thể tự sửa.

Không nên để requestor vừa tạo ticket, tự đánh giá risk, tự phê duyệt, tự đổi trạng thái thành compliant và tự đóng finding mà không có ai xem xét.

## 3. Ba câu hỏi risk owner phải trả lời

Trước mỗi quyết định, risk owner phải có thể trả lời:

### 3.1. Tôi có thẩm quyền chấp nhận rủi ro này không?

Kiểm tra risk appetite, delegated authority, legal/contractual obligations, loại dữ liệu, criticality và mức residual risk.

Một ví dụ thang phân quyền **giả định**:

| Residual risk | Thẩm quyền minh họa | Điều kiện |
|---|---|---|
| **Low** | Risk owner của hệ thống. | Scope và expiry rõ, technical review đầy đủ. |
| **Medium** | Business/service risk owner được chỉ định. | Có compensating controls và remediation plan. |
| **High** | Chuyển lên risk committee hoặc cấp điều hành được policy chỉ định. | Phân tích trade-off, tác động liên đơn vị và giám sát tăng cường. |
| **Critical / vượt appetite** | Không phê duyệt theo luồng thông thường; escalate, giảm rủi ro hoặc dừng hoạt động. | Quyết định cần thẩm quyền/biện pháp theo governance và nghĩa vụ áp dụng. |

Bảng này **không phải một quy định chung**. Tổ chức có thể dùng ma trận khác. Quan trọng là người phê duyệt không **tự nâng quyền** vì nhu cầu triển khai gấp.

### 3.2. Những gì tôi chấp nhận đã được hiểu đầy đủ chưa?

Phải biết ít nhất:

- Asset, environment, data sensitivity và business criticality.
- Control requirement cụ thể đang không đáp ứng.
- Threat scenario, attack paths và tác động có thể xảy ra.
- Inherent risk, controls hiện có và residual risk.
- Khả năng control gap làm yếu các controls khác (logging, backup, IAM, incident response).
- Chất lượng evidence, giả định và điều còn unknown.
- Phương án remediation và hậu quả nếu ngoại lệ kéo dài.

Nếu mô tả chỉ ghi **"không tương thích kỹ thuật, cần gấp"**, thông tin chưa đủ để quyết định risk acceptance có trách nhiệm.

### 3.3. Tôi sẽ làm gì nếu rủi ro thay đổi?

Phải có:

- Điều kiện **stop/revoke** như có exploit đang bị khai thác, mất logging, thêm PII hoặc xuất hiện thay đổi lớn.
- Người theo dõi kiểm soát bù trừ, metric/alert và lịch review.
- Deadline remediation, expiry của approval và escalation khi trễ.
- Cách xử lý incident liên quan tới ngoại lệ.
- Quy tắc đóng ngoại lệ sau khi khắc phục và retest.

Một risk owner chịu trách nhiệm **đến khi rủi ro được xử lý**, không chỉ tại thời điểm bấm Approve.

## 4. Phân biệt risk appetite, tolerance và residual risk

### 4.1. Risk appetite và decision limit

- **Risk appetite:** loại và mức rủi ro tổ chức sẵn sàng chấp nhận để đạt mục tiêu.
- **Risk tolerance:** giới hạn dao động/chấp nhận trong một khía cạnh cụ thể theo chính sách.
- **Risk capacity:** khả năng tổ chức chịu hậu quả trong điều kiện thực tế; không đồng nghĩa appetite.
- **Inherent risk:** rủi ro trước khi xét hiệu quả của controls giảm thiểu liên quan.
- **Residual risk:** rủi ro còn lại sau controls thực tế đang hoạt động hoặc được kiểm chứng.

Một yêu cầu có residual risk Medium không tự được chấp nhận nếu **loại rủi ro đó bị cấm**, ví dụ xử lý dữ liệu khách hàng ngoài điều khoản cho phép. Cần kiểm tra cả **độ nghiêm trọng** lẫn **ràng buộc định tính**.

### 4.2. Mô hình điểm minh họa, không phải xác suất

Một tổ chức dùng likelihood L và impact I từ 1 đến 5 để ưu tiên:

\[
R = L \times I
\]

Ví dụ:

| Tình huống | Likelihood | Impact | Điểm ưu tiên | Nhận xét |
|---|---:|---:|---:|---|
| Server không có EDR và trực tiếp exposed ra internet. | 4 | 5 | 20 | High theo ví dụ; cân nhắc giải pháp cách ly trước approval. |
| Server tương tự nhưng chỉ ở isolated segment, có allowlist và monitoring đã test. | 2 | 5 | 10 | Exposure giảm, nhưng impact vẫn lớn khi bị compromise. |
| Máy dev không chứa dữ liệu nhạy cảm, không vào production. | 2 | 2 | 4 | Có thể mức thấp hơn theo policy, vẫn cần đánh giá scope. |

**Điểm số là thang xếp hạng giả định**. Không tự giảm L từ 4 xuống 2 chỉ vì requestor cam kết sẽ bật firewall; phải có **evidence** rằng control bù trừ đã được triển khai, áp dụng và kiểm tra. Không dùng R=10 như “10% xác suất vi phạm”.

### 4.3. Những yếu tố có thể không lượng hóa hết

- Thông tin cá nhân và nghĩa vụ công bố/thông báo.
- An toàn con người hoặc hệ thống có tác động vật lý.
- Tính toàn vẹn giao dịch tài chính hoặc ledger.
- Khả năng lan rộng giữa các tài khoản cloud.
- Rủi ro tập trung vào một third-party hoặc một privileged account.
- Khả năng bị tấn công mà giám sát không quan sát được.
- Rủi ro uy tín, khách hàng hoặc khả năng khôi phục kinh doanh.

Với các scenario trọng yếu, phải ghi nhận **uncertainty**, không ép tất cả vào phép nhân số.

## 5. Ranh giới không được miễn bằng approval nội bộ

Một quyết định risk acceptance nội bộ **không tự miễn** yêu cầu pháp luật, quy định, nghĩa vụ giấy phép hoặc cam kết hợp đồng bắt buộc. Ngoại lệ cũng không thể cho phép hành vi gây nguy hiểm ngoài giới hạn an toàn và thẩm quyền.

Ví dụ:

- Hợp đồng với khách hàng yêu cầu một loại dữ liệu được xử lý trong scope nhất định. Risk owner không thể đơn phương chấp thuận gửi dữ liệu vượt mục đích mà không xem lại quyền/điều khoản liên quan.
- Một control lưu trữ dữ liệu liên quan đến retention/deletion hoặc legal hold. Không chỉ chọn deadline kỹ thuật dễ thực hiện hơn nếu trái yêu cầu áp dụng.
- Một chuẩn nội bộ cho phép phương án bảo vệ thay thế. Risk owner có thể xem xét phương án đó nếu policy thực sự có cơ chế ngoại lệ và approval đúng cấp.
- Một vulnerability có khả năng gây tác động nghiêm trọng. Chấp nhận rủi ro không phải chứng cứ rằng hệ thống đã được vá.

**Quy trình khi chưa rõ ràng buộc:** đánh dấu **PENDING_LEGAL_OR_COMPLIANCE_REVIEW**, hạn chế thay đổi nguy hiểm, yêu cầu người có thẩm quyền đánh giá applicability và quyết định trước khi cấp ngoại lệ thông thường.

Không gọi sự không chắc chắn về luật là “N/A” và không coi việc risk owner sẵn lòng ký là cơ sở hợp lệ.

## 6. Điều kiện đầu vào của một hồ sơ phê duyệt

### 6.1. Tối thiểu phải có

| Trường | Câu hỏi | Ví dụ |
|---|---|---|
| **Exception ID** | Có mã duy nhất? | EXC-2026-014. |
| **Requestor / owner** | Ai yêu cầu, ai quản lý risk, ai sửa? | Platform lead / order-service risk owner. |
| **Source requirement** | Yêu cầu nào, phiên bản nào chưa đạt? | SEC-ENDPOINT-03 v2.5. |
| **Scope** | Asset IDs, account, namespace, version, data class nào? | Legacy host order-sync-01 tại production. |
| **Observed deviation** | Thực tế khác yêu cầu ra sao? | EDR agent không hỗ trợ kernel hiện tại. |
| **Business rationale** | Tại sao phải tiếp tục hoạt động? | Migration cần giữ đồng bộ đơn hàng trong một kỳ. |
| **Alternatives evaluated** | Có giải pháp khác an toàn hơn không? | Upgrade ngay, tách dịch vụ, shutdown, isolation. |
| **Threat and impact** | Kịch bản nào tác động tài sản nào? | Remote code execution, lateral movement, dữ liệu đơn hàng. |
| **Risk rating** | Inherent/residual, tiêu chí và mức uncertainty? | High trước controls, Medium sau test controls. |
| **Compensating controls** | Control gì, ở đâu, ai xác minh và test nào? | Network isolation, allowlisting, log canary. |
| **Remediation plan** | Ngày sửa, bước, owner, test acceptance? | Nâng OS, cài agent, retest trước hạn. |
| **Monitoring** | Những tín hiệu nào làm stop/review? | Firewall drift, loss of audit, exploit indicators. |
| **Approval request** | Loại quyết định, thời gian hiệu lực, cấp phê duyệt? | Temporary exception trong 30 ngày. |
| **Evidence refs** | Dữ liệu nào hỗ trợ từng claim? | Scan, config export, test, ticket, source inventory. |
| **Stakeholder reviews** | Security, data/privacy, compliance, risk đã xem? | Review records theo điều kiện áp dụng. |

Nếu thiếu **source requirement, scope, responsible risk owner hoặc risk assessment**, hồ sơ cần được trả về làm rõ trước khi phê duyệt. Riêng với những ngoại lệ có tác động cao, thiếu evidence của compensating controls có thể làm residual risk không thể đánh giá.

### 6.2. Chất lượng evidence

| Thuộc tính | Yêu cầu | Cảnh báo |
|---|---|---|
| **Relevance** | Chứng minh đúng control/risk cần đánh giá. | Báo cáo pentest unrelated được đính kèm để tăng số tài liệu. |
| **Scope** | Đúng asset, tenant, vùng và release. | Kết quả test dev được dùng thay production khi behavior khác. |
| **Recency** | Có hiệu lực tại thời điểm approval. | Screenshot cũ trước thay đổi firewall. |
| **Completeness** | Bao phủ population và đường phơi nhiễm trọng yếu. | Inventory thiếu cloud account hoặc service principal. |
| **Integrity/provenance** | Có nguồn, timestamp, tool/query và đường lưu. | File CSV sửa tay không thể truy nguồn. |
| **Independence** | Có reviewer khác xác nhận phần quan trọng. | Requestor tự xác nhận mọi điều kiện đều đạt. |
| **Testability** | Có expected/actual và khả năng retest. | Chỉ ghi “đã tăng cường giám sát” không có use case hay alert test. |

**Bằng chứng về ý định cấu hình** không thay thế bằng chứng **control đang chạy**. Ví dụ firewall rule đã đề xuất trong ticket nhưng chưa có effective network policy thì chưa thể dùng làm lý do hạ residual risk.

## 7. Quy trình phê duyệt ngoại lệ có kiểm soát

### 7.1. Workflow chuẩn

~~~mermaid
flowchart TD
    REQ["Request: deviation + reason + scope"] --> VALID["Preflight: policy source, owner, applicability"]
    VALID -->|Thiếu thông tin| RETURN["Return for clarification"]
    VALID -->|Đủ| RA["Threat, inherent/residual risk assessment"]
    RA --> TECH["Validate compensating controls + remediation"]
    TECH --> REG{"Legal/compliance restrictions?"}
    REG -->|Có / chưa rõ| LEGAL["Review nghĩa vụ và phạm vi được phép"]
    REG -->|Không| AUTH["Check approval authority / risk appetite"]
    LEGAL --> AUTH
    AUTH -->|Vượt thẩm quyền| ESC["Escalate to authorized level"]
    AUTH -->|Trong thẩm quyền| DEC{"Risk owner decision"}
    ESC --> DEC
    DEC -->|Reject| DENY["Reject / alternative / pause activity"]
    DEC -->|Conditional| PEND["Conditions must be verified"]
    PEND -->|PASS| ACTIVE["Activate time-bound exception"]
    DEC -->|Approve| ACTIVE
    ACTIVE --> MON["Monitor controls + expiry + changes"]
    MON -->|Trigger/violation| REVOKE["Reassess / revoke / escalate"]
    MON -->|Fix complete| RETEST["Remediation + independent retest"]
    RETEST --> CLOSE["Close + archive evidence"]
    MON -->|Cần gia hạn| RENEW["New assessment / new approval"]
    RENEW --> AUTH
~~~

Sơ đồ là quy trình tổng quát. Các bước **legal review, risk escalation và kiểm tra controls** có thể chạy song song theo chính sách, nhưng **ngoại lệ chưa được coi là có hiệu lực nếu các điều kiện tiên quyết chưa đáp ứng**.

### 7.2. Các trạng thái workflow

| Trạng thái | Ý nghĩa | Có được vận hành theo ngoại lệ? |
|---|---|---|
| **DRAFT** | Requestor đang soạn hồ sơ. | Không, trừ quy trình khẩn cấp riêng đã cho phép. |
| **UNDER_REVIEW** | Security/legal/owner đang kiểm tra. | Không mặc định. |
| **PENDING_INFORMATION** | Thiếu risk assessment, evidence hoặc source. | Không mặc định. |
| **PENDING_APPROVAL** | Đủ thông tin nhưng chưa có quyết định đúng thẩm quyền. | Không mặc định. |
| **APPROVED_CONDITIONAL** | Đã có quyết định về nguyên tắc, còn điều kiện bắt buộc. | Chỉ theo phạm vi điều kiện đã xác minh và chính sách cho phép. |
| **ACTIVE_APPROVED** | Đủ approvals và conditions; còn hiệu lực. | Có, trong scope và thời hạn đã ghi. |
| **REJECTED** | Không được chấp thuận. | Không. |
| **EXPIRED** | Hết hiệu lực theo thời gian. | Không; phải khắc phục hoặc xử lý tiếp theo đúng chính sách. |
| **REVOKED** | Bị thu hồi do thay đổi rủi ro/vi phạm điều kiện. | Không. |
| **CLOSED_REMEDIATED** | Control gap được sửa và retest đạt. | Không cần ngoại lệ tiếp tục. |

**APPROVED_CONDITIONAL không bằng ACTIVE_APPROVED.** Không nên tự động kích hoạt ngoại lệ chỉ vì risk owner gửi email “đồng ý nếu bật monitoring” nhưng monitoring chưa được xác minh.

### 7.3. Các lựa chọn quyết định của risk owner

- **Approve:** trong thẩm quyền, đủ căn cứ, risk trong appetite, điều kiện và thời hạn rõ.
- **Approve with conditions:** có thể chấp nhận khi các điều kiện tiên quyết được đáp ứng và kiểm chứng; chỉ activate sau khi hoàn tất.
- **Reject:** rủi ro vượt appetite, evidence yếu, controls bù trừ không đủ hoặc không có căn cứ hợp lệ.
- **Request information:** thiếu scope, nguồn, risk analysis, test hoặc owner.
- **Escalate:** tác động vượt quyền, nhiều business owners, liên quan nghĩa vụ bên ngoài hoặc rủi ro chiến lược.
- **Suspend/revoke:** rủi ro đã thay đổi, vi phạm điều kiện, có incident liên quan hoặc hết hạn.
- **Renew:** chỉ sau đánh giá lại, không mặc định kéo dài từ approval cũ.

Một quyết định **Reject** cũng cần lý do, người quyết định và phương án giảm tác động; không phải thất bại quản trị nếu nó ngăn rủi ro vượt ngưỡng.

## 8. Trách nhiệm người phê duyệt: kiểm tra trước khi ký

### 8.1. Decision checklist của risk owner

Trước khi phê duyệt, người nhận trách nhiệm cần xác nhận:

1. **Tôi là người được phân quyền phê duyệt đúng loại/mức rủi ro này.**
2. Requirement đang bị lệch và applicability của nó được xác minh.
3. Mỗi asset/data flow/identity nằm trong scope được xác định, không mập mờ “toàn bộ hệ thống”.
4. Business need có thật và không có phương án thay thế an toàn hơn với chi phí/tác động phù hợp.
5. Threat scenarios và tác động đến confidentiality, integrity, availability, privacy đã được đánh giá.
6. Inherent risk, residual risk và uncertainty có căn cứ, không chỉ sao chép số điểm từ requestor.
7. Controls bù trừ đang được vận hành, có evidence/test và monitoring trong thời gian ngoại lệ.
8. Không có ràng buộc pháp luật/hợp đồng bị bỏ qua bằng cách ký chấp nhận.
9. Có owner, kế hoạch remediation, milestone và hạn hoàn tất.
10. Có expiry, review date, sự kiện kích hoạt reassessment và điều kiện revoke.
11. Các bên bị ảnh hưởng đã được tham vấn theo policy.
12. Tôi sẵn sàng chịu trách nhiệm về quyết định và kết quả báo cáo trong phạm vi được giao.

**Tối thiểu một câu không đủ bằng chứng** có thể làm quyết định phải hoãn hoặc chuyển cấp, đặc biệt với rủi ro trọng yếu.

### 8.2. Những câu hỏi dùng để chất vấn risk assessment

- Attack path được dùng để xếp likelihood có còn phù hợp threat intelligence và exposure mới?
- Compensating control có giảm đúng attack path hay chỉ cải thiện một khía cạnh khác?
- Đã thử **negative cases** và lỗi control chưa, hay chỉ test luồng bình thường?
- Nếu detection pipeline bị tắt, ai nhận biết và trong bao lâu?
- Có tác động dây chuyền tới backup, key, CI/CD, IAM hoặc một third-party không?
- Liệu một system chưa có owner hoặc source health có tạo **unknown risk** lớn hơn báo cáo?
- Nếu ngoại lệ phải kéo dài gấp đôi, mức rủi ro có đổi không?
- Có chấp nhận được việc client hoặc bên khác đang dựa vào một assurance claim không còn đúng không?

Risk owner không cần tự chạy mọi phép thử nhưng cần hiểu **evidence nào hỗ trợ từng luận điểm** và giới hạn của chúng.

### 8.3. Không ký theo áp lực tiến độ

Một câu thường gặp là “không ký exception thì release trễ”. Đây là lý do nghiệp vụ cần xem xét, nhưng không thay cho đánh giá rủi ro.

Risk owner có thể chọn:

- Hoãn release.
- Giảm scope sản phẩm hoặc dữ liệu.
- Dùng chế độ read-only/degraded được kiểm soát.
- Triển khai controls bù trừ trước và giới hạn thời gian.
- Chuyển cấp quyết định kèm risk analysis nếu vượt thẩm quyền.

**Không hợp thức hóa một trạng thái trái policy bằng cách tạo ticket sau khi hệ thống đã chạy ngoài kiểm soát**, trừ khi quy trình khẩn cấp được phép và có cơ chế xem xét riêng. Kỳ tồn tại gap trước approval vẫn phải được ghi nhận trung thực.

## 9. Mẫu approval record có thể kiểm toán

### 9.1. Hồ sơ YAML minh họa

~~~yaml
exception:
  id: EXC-2026-014
  title: "EDR exception for legacy order-sync host"
  requirement:
    policy: SEC-ENDPOINT-03
    version: "2.5"
    control_id: CTRL-EDR-001
  deviation:
    type: temporary-policy-exception
    description: "Legacy kernel cannot run approved EDR agent"
  scope:
    environment: production
    assets: ["order-sync-01"]
    data_classification: confidential
    business_service: order-platform
  request:
    submitted_by: platform-lead
    business_reason: "Maintain synchronization during OS migration"
    alternatives_evaluated:
      - "Immediate OS upgrade with outage"
      - "Service isolation and shorter transition period"
  risk:
    scenario: "Host compromise and lateral movement"
    inherent_rating: high
    residual_rating: medium
    uncertainty: "Residual exposure depends on continuous network enforcement"
    assessment_ref: RISK-2026-043
  compensating_controls:
    - id: NET-SEG-01
      owner: network-team
      test_ref: TEST-NET-017
      status: verified
    - id: DET-MON-02
      owner: soc-team
      test_ref: TEST-DET-022
      status: verified
  remediation:
    owner: platform-team
    work_item: REM-2026-077
    acceptance: "EDR healthy on upgraded OS with detection test"
    due_at: "2026-12-28T00:00:00Z"
  governance:
    risk_owner: order-business-risk-owner
    security_reviewer: security-architecture
    compliance_review: no_external_constraint_identified_in_defined_scope
    authority_policy: RISK-DOA-02
    authority_checked: true
  decision:
    outcome: approved
    decided_by: order-business-risk-owner
    approved_at: "2026-11-28T09:30:00Z"
    effective_from: "2026-11-28T09:30:00Z"
    expires_at: "2026-12-28T00:00:00Z"
    rationale: "Residual risk within delegated appetite for limited period"
    conditions:
      - "Restrict host egress to approved endpoints"
      - "Page on collector failure or policy drift"
      - "Weekly review of threat and remediation status"
    revocation_triggers:
      - "Exploitation of relevant weakness"
      - "Network isolation or monitoring no longer effective"
      - "Scope changes or expiry"
  assurance:
    evidence_index: EV-PACK-EXC-014
    next_review_at: "2026-12-05T09:30:00Z"
    status: ACTIVE_APPROVED
~~~

Đây là **mô hình quản trị giả định**, không phải hồ sơ phê duyệt thực tế hoặc yêu cầu từ một tiêu chuẩn cụ thể. Các mốc thời gian, tên policy, thang risk và kết luận không có nghĩa là một tổ chức bất kỳ đã chấp nhận rủi ro đó.

### 9.2. Những bất biến dữ liệu quan trọng

Một hệ thống quản lý ngoại lệ nên chặn hoặc cảnh báo:

- **effective_from trước approved_at** nếu policy không quy định trường hợp emergency hợp lệ.
- **expires_at không tồn tại** đối với ngoại lệ bắt buộc có thời hạn.
- Decision được ký bởi người không nằm trong **DoA**.
- Requestor tự duyệt dù quy trình yêu cầu independent approval.
- Một asset không nằm trong scope lại dùng exception đó.
- Residual risk cao hơn limit cho phép nhưng không được escalate.
- Compensating control ở trạng thái planned nhưng hồ sơ ghi verified.
- Exception đã hết hạn vẫn được hiển thị như active.
- Đổi policy/scope hoặc conditions sau khi ký nhưng không có reapproval.
- Một exception bị đóng chỉ vì remediation ticket chuyển “Done” mà chưa test.

**Chữ ký và dữ liệu cần được ghi bất biến theo phiên bản hoặc có audit log**: ai phê duyệt bản nào, lúc nào, dựa trên những evidence và điều kiện nào.

## 10. Approval rationale: viết như thế nào cho đủ sức thuyết phục?

### 10.1. Mẫu lời phê duyệt có điều kiện

> Tôi phê duyệt ngoại lệ EXC-2026-014 chỉ cho máy chủ order-sync-01 trong production, từ thời điểm ghi trong hồ sơ đến ngày hết hạn đã định. Căn cứ là đánh giá RISK-2026-043, các controls NET-SEG-01 và DET-MON-02 đã được kiểm chứng, và kế hoạch nâng cấp REM-2026-077 có owner. Mức rủi ro tồn dư được chấp nhận trong giới hạn DoA hiện hành với các điều kiện: mạng không mở rộng ngoài allowlist, nguồn audit duy trì healthy và việc khắc phục được kiểm tra hàng tuần. Nếu có hoạt động khai thác liên quan, control bù trừ mất hiệu lực, phạm vi thay đổi hoặc hết hạn, quyết định phải được xem lại/thu hồi. Đây không phải xác nhận control EDR đã đáp ứng baseline.

Mẫu trên là **cách diễn đạt minh họa**, không thay thế chữ ký theo hệ thống được tổ chức chấp thuận.

### 10.2. Những lời phê duyệt không đủ

| Lời phê duyệt | Thiếu gì? |
|---|---|
| "Approved." | Scope, risk, authority, hiệu lực, conditions, rationale. |
| "Business cần gấp, đồng ý." | Không chứng minh risk assessment và appetite. |
| "Security chịu trách nhiệm." | Risk owner đang chuyển trách nhiệm sang reviewer. |
| "Chấp nhận đến khi nào sửa xong." | Không có expiry rõ ràng và điều kiện escalation. |
| "Risk Medium nên tự động pass." | Thang điểm chưa đủ; thiếu quyền và ngoại lệ bắt buộc. |
| "Có EDR ở những máy khác nên máy này không đáng lo." | Không đánh giá attack path và exposure riêng. |
| "Compliance đã ký nên hợp pháp." | Phải xem họ thực sự kết luận điều gì và nguồn áp dụng. |
| "Ticket đóng rồi, không còn rủi ro." | Chưa có evidence remediated và retest. |

### 10.3. Lý do từ chối cũng cần evidence

Ví dụ:

> Request bị từ chối vì chưa chứng minh được control phân đoạn mạng hoạt động trên đường egress tới dữ liệu Confidential; scope gồm nhiều máy nhưng chỉ có test một máy; rủi ro tồn dư chưa đánh giá đầy đủ. Chỉ xem xét lại khi có effective network policy, connectivity negative tests, inventory đối chiếu và remediation deadline.

Như vậy requestor biết rõ **điều kiện cần bổ sung**, thay vì xem rejection là quyết định tùy ý.

## 11. Compensating controls phải được thử trong phạm vi ngoại lệ

Một ngoại lệ thường phụ thuộc vào controls thay thế. Nhưng **control bù trừ chỉ có giá trị khi giảm đúng rủi ro mà control chuẩn vốn được thiết kế để giải quyết**.

### 11.1. Ví dụ kiểm tra control bù trừ

| Gap | Control bù trừ đề nghị | Bằng chứng kiểm chứng | Còn giới hạn gì? |
|---|---|---|---|
| EDR không hỗ trợ host legacy. | Network isolation, application allowlisting, host logs, SOC alert. | Effective firewall/ACL, authorized reachability test, process audit và detection test. | Thiếu khả năng kiểm soát trên host, attacker có thể lợi dụng đường cho phép. |
| Hệ thống chưa hỗ trợ MFA trực tiếp. | SSO/PAM proxy với MFA và session control. | Login positive/negative, bypass test, effective routing, session audit. | Đường direct login cần được chặn và kiểm chứng. |
| Container cần quyền privileged tạm thời. | Node riêng, admission exception scoped, network segmentation, image provenance. | Effective PodSpec, namespace scope, node policy, runtime/audit test. | Container escape hoặc node compromise vẫn có thể nghiêm trọng. |
| Patch critical chậm triển khai. | WAF/IPS phù hợp, disable feature, limit exposure, detect attempt. | Attack-path-specific test, policy config, log/alert. | Chưa loại bỏ vulnerability; bypass có thể tồn tại. |
| Cloud audit chưa hỗ trợ một nguồn. | Alternative audit source và active monitoring coverage. | Source inventory, canary test, event-to-alert trace. | Event types ngoài nguồn thay thế vẫn có thể không quan sát. |

Không giảm điểm residual risk dựa trên danh sách biện pháp **dự kiến**. Kiểm chứng ít nhất:

1. Control **đã hiện diện và hiệu lực** ở asset/đường phù hợp.
2. Control xử lý **threat path** quan trọng.
3. Có test tích cực và **negative/boundary tests**.
4. Có monitoring phát hiện control bị tắt hoặc drift.
5. Có owner, kỳ evidence và quy trình xử lý lỗi.
6. Có giới hạn rõ và phản ánh vào residual risk.

### 11.2. Chứng cứ hiệu lực khác chứng cứ cấu hình

Một ảnh firewall rule chứng minh cấu hình được khai báo, chưa chắc chứng minh:

- Rule đã có hiệu lực trên đúng đường.
- Không có đường route khác bypass.
- Rule không bị rule ưu tiên cao hơn ghi đè.
- Có log khi connection bị từ chối.
- Policy còn hiệu lực sau thay đổi.

Phê duyệt cần mức bằng chứng tương ứng **tác động của sai sót**.

## 12. Ngoại lệ khẩn cấp: an toàn, quyền hạn và hồi tố

Có trường hợp sự cố khiến phải làm một thay đổi nhanh để khôi phục dịch vụ. Nếu chính sách cho phép, tổ chức có thể có **emergency deviation workflow** riêng. Không nên lấy quy trình này làm đường tắt cho các ngoại lệ thông thường.

### 12.1. Điều kiện bảo vệ cơ bản

- Có tiêu chí thật sự **khẩn cấp**: đe dọa hoạt động thiết yếu, phục hồi hoặc an toàn.
- Có một người ra quyết định tạm thời được ủy quyền và kênh thông báo dự phòng.
- Chỉ mở **scope nhỏ nhất, thời hạn ngắn nhất và quyền tối thiểu**.
- Ghi ngay lý do, mốc thời gian, system IDs, thay đổi, người thực hiện.
- Ưu tiên các controls bù trừ có thể áp dụng ngay, audit mọi thay đổi.
- Có **post-implementation review** theo thời hạn policy, có quyền yêu cầu rollback và mở finding.
- Quyết định hồi tố không xóa lịch sử gap đã tồn tại trước đó.
- Không miễn yêu cầu pháp lý/hợp đồng bằng cách gắn nhãn "emergency".

### 12.2. Ví dụ giả định

Một incident khiến gateway cần mở tạm kết nối outbound tới địa chỉ DR để chuyển traffic. Incident commander theo quyền khẩn cấp cho phép thay đổi trong 2 giờ; network owner triển khai và log configuration change. Sau phục hồi:

1. Chặn traffic không còn cần thiết.
2. Xác nhận rule rollback.
3. Rà soát logs và dữ liệu đã đi qua đường mới.
4. Security reviewer kiểm tra necessity, scope, thời gian và evidence.
5. Risk owner/quyết định cấp phù hợp xem xét ngoại lệ theo emergency policy.
6. Tạo remediation nếu control thiết kế bình thường chưa hỗ trợ DR.
7. Ghi lessons learned, không coi thay đổi ngoài baseline là một **permanent approved design**.

**Không được phê duyệt hồi tố tùy ý để che hoạt động trái quy trình**. Chỉ áp dụng các điều kiện và thẩm quyền được định nghĩa trước.

## 13. Gia hạn, hết hạn và thu hồi quyết định

### 13.1. Không có "auto-renew" vì chưa sửa xong

Mỗi gia hạn phải đánh giá mới:

- Vì sao remediation không xong theo deadline cũ?
- Các điều kiện business và dữ liệu có thay đổi?
- Có exploit, incident, vulnerability, new attack path hoặc regulatory change?
- Compensating controls còn hiệu lực, evidence có cập nhật?
- Residual risk có tăng theo thời gian phơi nhiễm?
- Tổ chức có thể dừng, thay dịch vụ hoặc giảm scope thay vì tiếp tục?
- Risk owner cũ còn thẩm quyền? Có cần cấp duyệt cao hơn cho ngoại lệ lặp?
- Gia hạn tối đa và số lần gia hạn theo policy là bao nhiêu?

**Gia hạn là một quyết định mới**, có lịch sử và evidence của riêng nó; không sửa lại expiry cũ mà mất audit trail.

### 13.2. Các trigger bắt buộc re-evaluate

| Trigger | Ví dụ | Hành động |
|---|---|---|
| **Expiry** | Quá ngày phê duyệt. | Không tiếp tục coi active; khắc phục hoặc phê duyệt mới theo quy trình. |
| **Scope expansion** | Thêm region, tenant, host hoặc quyền. | Đánh giá lại; approval cũ không tự bao phủ asset mới. |
| **Control failure** | Monitoring/source health hoặc isolation fail. | Escalate, thu hồi/giới hạn hoạt động theo mức rủi ro. |
| **Threat change** | Có exploit thực tế đối với vulnerability chưa vá. | Tăng priority, cô lập/patch, risk decision mới. |
| **Incident** | Credential compromise liên quan đường ngoại lệ. | Kích hoạt IR và đánh giá lại claim về residual risk. |
| **Business impact change** | Dịch vụ được nâng lên Critical hoặc bắt đầu xử lý PII. | Xem lại appetite, thẩm quyền, controls và deadline. |
| **Legal/contract change** | Yêu cầu mới làm phương án không còn hợp lệ. | Legal/compliance review, đổi plan và xử lý nghĩa vụ. |
| **Owner/authority change** | Risk owner rời vai trò hoặc delegated authority thay. | Gán owner mới, rà soát hiệu lực quyết định theo policy. |

### 13.3. Đóng ngoại lệ phải có retest

Một remediation ticket chuyển Done không đủ để đóng exception. Ví dụ EDR gap:

1. OS nâng cấp xong.
2. Agent cài đặt trên đúng host.
3. Control policy thực sự áp dụng và có heartbeat.
4. Test detection hoặc health scenario phù hợp đạt.
5. Các controls bù trừ tạm thời được gỡ bỏ có kiểm soát nếu không còn cần.
6. Reviewer ghi evidence, cập nhật control coverage.
7. Exception được đóng, findings liên quan được xử lý theo quy trình.

Nếu control chuẩn vẫn fail, status phải phản ánh **chưa khắc phục**, dù ngày dự kiến đã qua.

## 14. Assurance case cho claim "risk owner đã phê duyệt hợp lệ"

Không chỉ cần biết exception tồn tại; phải chứng minh **approval có hiệu lực**.

### 14.1. Claim–Argument–Evidence

**Top claim G0:** "Ngoại lệ EXC-2026-014 được risk owner có thẩm quyền phê duyệt trên căn cứ rủi ro và điều kiện kiểm soát đã được xác minh, chỉ trong scope và thời hạn được định nghĩa."

~~~mermaid
flowchart TD
    G0["G0: Approval hợp lệ trong scope và thời hạn"]
    S0["Strategy: authority + assessment + controls + decision + lifecycle"]
    G1["G1: Source requirement và applicability rõ"]
    G2["G2: Risk owner có DoA và không có SoD conflict trọng yếu"]
    G3["G3: Residual risk và uncertainty được đánh giá"]
    G4["G4: Compensating controls có evidence hiệu lực"]
    G5["G5: Approval record đúng điều kiện, expiry và monitoring"]
    E1["Source policy, asset inventory, requirement"]
    E2["DoA matrix, identity, approval audit"]
    E3["Risk assessment, threat model, impact"]
    E4["Config, effective tests, monitoring"]
    E5["Signed decision, alerts, review, retest"]
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

**Warrant:** nếu yêu cầu và phạm vi được xác định, người quyết định có thẩm quyền, rủi ro tồn dư được đánh giá dựa trên controls có bằng chứng, và quyết định được lưu giữ với điều kiện/time-bound monitoring, thì có cơ sở xem approval hợp lệ theo chính sách quản trị đã chọn.

Tuy nhiên, G0 **không phải** claim rằng control chuẩn đã được triển khai hoặc system đã hoàn toàn an toàn. G0 cũng không tự chứng minh mọi nghĩa vụ pháp lý bên ngoài đều được đáp ứng.

### 14.2. Các defeaters phá hỏng claim

- DoA không cho phép risk owner chấp nhận mức rủi ro High.
- Chữ ký đến từ tài khoản không còn được ủy quyền, hoặc approval xảy ra sau thời điểm sử dụng ngoại lệ ngoài chính sách.
- Exception được copy từ asset A nhưng thực tế đang áp dụng cho asset B.
- Ngày expiry đã qua nhưng dashboard vẫn hiển thị active.
- Một control bù trừ chưa được triển khai ở production.
- Dữ liệu source audit thiếu hoặc risk assessment bỏ qua attack path quan trọng.
- Policy có yêu cầu không được waived nhưng legal review chưa thực hiện.
- Requestor tự ký khi quy trình yêu cầu reviewer độc lập.
- Kế hoạch remediation bị hủy mà không có risk reassessment.
- Có incident mới nhưng không kích hoạt review.

Mỗi defeater trọng yếu có thể dẫn tới **inconclusive, nonconformity hoặc thu hồi** tùy tình trạng bằng chứng và quy tắc áp dụng.

## 15. Tình huống thực hành: ngoại lệ MFA cho hệ thống legacy

### 15.1. Bối cảnh

Một công ty vận hành **Legacy Reporting Portal** trên một môi trường cũ. Portal có người dùng quản trị tương tác và một account tích hợp có thể đọc dữ liệu báo cáo. Policy SEC-IAM-04 giả định yêu cầu MFA trên đường đăng nhập quản trị tương tác. Portal chưa hỗ trợ tích hợp MFA trực tiếp; business owner đề nghị ngoại lệ **45 ngày** để chuyển hệ thống sang SSO.

Requestor đưa ra ba thông tin:

- "Đã bật VPN."
- "Chỉ đội nội bộ mới truy cập."
- "Đang lên kế hoạch migration."

Chưa có architecture diagram, effective access test, kiểm tra direct-login bypass hoặc logging/alert test.

### 15.2. Phân tích trước khi approval

**Risk:** attacker có credential quản trị có thể đăng nhập vào portal mà không có yếu tố xác thực thứ hai, truy cập báo cáo, sửa quyền hoặc làm thay đổi dữ liệu tùy khả năng của portal.

Những câu hỏi phải trả lời:

1. Portal public hay private? Có thể truy cập trực tiếp ngoài VPN?
2. VPN có MFA và session control được enforce cho toàn bộ đường truy cập?
3. Có local admin account hoặc đường bypass sang portal?
4. Service account có quyền gì, lifecycle token ra sao?
5. Portal có PII hay dữ liệu nhạy cảm ảnh hưởng bên nào?
6. Có log thành công/thất bại khi đăng nhập và phát hiện brute force?
7. Ai sở hữu rủi ro mất dữ liệu, gián đoạn và nghĩa vụ hợp đồng?
8. Deadline migration có milestone và phương án rollback?
9. Residual risk có trong appetite và authority của risk owner?
10. Nếu SSO migration fail, ai quyết định dừng portal hoặc giới hạn chức năng?

### 15.3. Controls bù trừ có thể đề xuất

- Chặn mọi direct login từ internet và các đường mạng không được phê duyệt.
- Bắt buộc truy cập qua access gateway/SSO/VPN có MFA đã kiểm tra, nếu phù hợp kiến trúc.
- Áp role và privilege tối thiểu, hạn chế IP/network, session timeout.
- Alert cho admin login thất bại nhiều lần, thay đổi quyền và source-health failures.
- Tạm giới hạn thao tác export dữ liệu hoặc dữ liệu nhạy cảm nếu doanh nghiệp cho phép.
- Tăng lịch review active sessions và access history.
- Có kế hoạch migrate với thử nghiệm và deadline rõ.

Tất cả là **đề xuất cần kiểm chứng**, không tự động giảm residual risk chỉ vì được liệt kê.

### 15.4. Test plan trước khi risk owner ký

| Test ID | Kiểm thử | Điều kiện đạt | Evidence |
|---|---|---|---|
| **T01 Network path** | Từ điểm test ngoài đường VPN/SSO hợp lệ thử tiếp cận portal. | Không thể truy cập ứng dụng/đăng nhập quản trị theo boundary đã định. | Firewall effective policy, route và test result. |
| **T02 MFA gateway** | Dùng test identity tương tác theo đường được phê duyệt. | MFA enforced; negative case không qua MFA bị từ chối. | IdP config, sign-in logs, test IDs. |
| **T03 Bypass account** | Kiểm tra local accounts/alternate endpoints hợp lệ trong scope. | Không có đường admin bypass chưa được quản lý, hoặc gap được ghi. | Effective-access map, negative tests. |
| **T04 Detection** | Tạo login fail/privilege-change synthetic có kiểm soát. | Audit và alert đến đúng kênh trong mục tiêu đã phê duyệt. | Raw event, rule version, alert/case timeline. |
| **T05 Data exposure** | Đối chiếu data classification và chức năng export. | Data flows và scope/risk được trình bày đầy đủ. | Data map, inventory, security review. |
| **T06 Expiry enforcement** | Tạo test exception hết hạn trong workflow sandbox. | Phê duyệt không còn active; được đưa vào escalation. | Workflow/audit test, scheduled review. |
| **T07 Migration exit** | Sau nâng cấp SSO, thử lại admin login và kiểm tra logs. | Control chuẩn đáp ứng; ngoại lệ được đóng theo retest. | SSO login tests, config, reviewer signoff. |

Nếu **T01 không đạt** và vẫn tồn tại direct login bypass, không thể sử dụng "VPN có MFA" như một compensating control cho toàn bộ đường admin. Phê duyệt phải **từ chối, giới hạn scope hoặc chuyển cấp** thay vì tự hạ điểm residual risk.

### 15.5. Quyết định mẫu

**Lần đánh giá đầu:** **REQUEST_INFORMATION / NOT APPROVED**, vì chưa chứng minh tất cả đường đăng nhập đều đi qua gateway MFA và chưa có log/alert evidence. Kế hoạch migration là lý do nghiệp vụ, **chưa phải bằng chứng giảm rủi ro**.

**Nếu sau đó có bằng chứng đầy đủ:** Risk owner có thể xem xét **APPROVE_WITH_CONDITIONS** trong thẩm quyền, giới hạn 45 ngày, yêu cầu monitoring hằng ngày theo criticality, không mở thêm data scope, có migration milestone, trigger revoke và retest sau triển khai SSO. Quyết định cuối cùng phụ thuộc vào policy, risk appetite và ràng buộc bên ngoài.

**Nếu risk vượt thẩm quyền hoặc có nghĩa vụ không cho phép:** phải **escalate hoặc reject**; không hợp thức hóa bằng chữ ký tự chọn.

## 16. Tình huống thứ hai: ngoại lệ Kubernetes privileged workload

### 16.1. Bối cảnh

Một hệ thống giám sát hạ tầng dùng DaemonSet cần truy cập host-level information để thu thập security telemetry. Pod Security baseline hiện tại cấm **privileged containers** trong đa số namespaces. Nhóm vận hành yêu cầu ngoại lệ cho tất cả clusters production "đến khi vendor hỗ trợ chế độ khác".

**Điểm yếu trong request:**

- Scope quá rộng: "tất cả clusters".
- Không có expiry.
- Không nói image provenance, quyền host, network reachability, node placement.
- Không nêu alternative đã đánh giá.
- Chưa xác định nguy cơ container escape và quyền truy cập secret/host.
- Risk owner có thể không sở hữu mọi cluster hoặc dữ liệu nhạy cảm tương ứng.

### 16.2. Cách sửa request

- Giới hạn namespace, cluster, DaemonSet và image digest cụ thể.
- Xác nhận permissions và host mounts thật sự cần thiết.
- Xem có thể dùng unprivileged mode, eBPF/host service hoặc node agent khác không.
- Dùng dedicated nodes, isolation, restricted egress và RBAC tối thiểu nếu phù hợp.
- Bật audit và image provenance/attestation theo pipeline đã chọn.
- Kiểm tra effective PodSpec, admission exceptions và việc principal khác không thể lạm dụng đường miễn.
- Có thời hạn, owner và kế hoạch thay thế/thu hẹp đặc quyền.
- Xác định các bên chịu rủi ro cluster, cloud account và dữ liệu có liên quan.

### 16.3. Assurance claim phù hợp

> Ngoại lệ privileged chỉ áp dụng cho DaemonSet đã xác định ở các cluster và namespaces liệt kê trong hồ sơ, với controls phân đoạn, image integrity và audit được kiểm chứng trong kỳ; các workload khác vẫn bị policy từ chối.

Cần negative test với workload không nằm trong scope: **nó phải bị từ chối**. Nếu admission exception vô tình cho phép tất cả service accounts chạy privileged, điều kiện phê duyệt **không đạt** dù DaemonSet vendor hoạt động tốt.

## 17. Audit và evidence cho quyết định của risk owner

### 17.1. Ma trận claim → test → evidence

| Claim | Phép kiểm tra | Evidence |
|---|---|---|
| **A1 — Risk owner đúng thẩm quyền.** | Đối chiếu risk level, business scope và DoA tại thời điểm ký. | DoA version, risk owner assignment, approval event. |
| **A2 — Risk assessment có căn cứ.** | Xem threat scenarios, impact, likelihood, assumptions, alternative. | Risk register, threat model, technical review. |
| **A3 — External obligations được xử lý.** | Review applicability và quyết định legal/compliance khi có trigger. | Contract/policy refs, signoff, scope analysis. |
| **A4 — Compensating controls hoạt động.** | Xem effective config và authorized positive/negative tests. | Test logs, configurations, source-health, reviewer. |
| **A5 — Scope và hiệu lực không vượt approval.** | Đối chiếu asset inventory, timestamps, exceptions và effective status. | Asset map, decision version, workflow audit. |
| **A6 — Monitoring và revocation readiness đủ.** | Test control-failure alert, expired approval và escalation. | Alert/case timeline, expiry test, on-call routing. |
| **A7 — Remediation có kết quả và retest.** | Đối chiếu milestone, changed config và tests đạt. | Tickets, deployment records, validation, signoff. |
| **A8 — Mọi approval/reject/renewal có thể truy vết.** | Chọn mẫu decisions trong kỳ, đối chiếu người ký, lịch sử version. | Decision audit trail, evidence index, reviewer report. |

**Một bảng exception có trường APPROVED=true không đủ** cho bất kỳ claim nào ở trên nếu thiếu dấu vết, scope và thẩm quyền.

### 17.2. Những audit findings phổ biến

| Finding | Dấu hiệu | Tác động |
|---|---|---|
| **Unauthorized approval** | Người ký không nằm trong DoA tại thời điểm quyết định. | Không có cơ sở quản trị cho risk acceptance. |
| **Retroactive approval gap** | Activity lệch policy trước khi approval có hiệu lực. | Kỳ hoạt động ngoài kiểm soát bị che. |
| **Missing evidence** | Compensating controls chỉ được tự khai. | Residual risk không đủ căn cứ. |
| **Expired active exceptions** | Hết hạn nhưng vẫn active trong dashboard và runtime. | Exposed systems không có quyết định hiện hành. |
| **Overbroad scope** | Approval một máy nhưng thực tế áp dụng cả subnet. | Rủi ro vượt phần đã đánh giá. |
| **Conflict of interest** | Requestor tự ký và tự đóng trong quy trình đòi SoD. | Suy yếu độc lập và trách nhiệm. |
| **Unreviewed change** | Asset mới, data scope mới, exploit mới nhưng không reapprove. | Risk assessment trở nên lỗi thời. |
| **Closed without retest** | Ticket Done, control chuẩn vẫn fail. | Reporting sai; gap chưa khắc phục. |
| **Legal obligation ignored** | Risk owner chấp thuận sai phạm ngoài quyền miễn trừ. | Nguy cơ nghĩa vụ bắt buộc vẫn không đạt. |

### 17.3. Ví dụ audit finding

**Criterion:** Policy EXC-02 v3 giả định quy định ngoại lệ có thời hạn, được risk owner đúng thẩm quyền phê duyệt trước hiệu lực và phải có evidence cho compensating controls.

**Condition:** EXC-2026-014 hiển thị ACTIVE sau expiry, chưa có approval gia hạn; dữ liệu hệ thống xác nhận hai assets ngoài scope ban đầu được gắn exception ID này.

**Evidence:** approval record phiên bản 1, workflow audit timestamps, asset-control mapping và effective policy export.

**Risk:** những assets không được đánh giá có thể vận hành ngoài baseline; kết quả control coverage và residual risk report sai. Chưa có bằng chứng để khẳng định đã xảy ra compromise.

**Root cause:** đang điều tra liệu mapping tự động không kiểm tra expiry hoặc scope.

**Action:** đưa exception về trạng thái hợp lệ; cách ly/hạn chế controls nếu cần; đánh giá lại assets, sửa workflow, retrospective review và test expiry/scope enforcement.

**Closure:** chỉ sau khi workflow được sửa, quyền/trạng thái hiện hành đúng, retest đạt và người có thẩm quyền xác nhận. Không sửa ngày phê duyệt lịch sử để tránh finding.

## 18. KPI quản lý rủi ro từ ngoại lệ

Chương trình exception management cần đo cả **chất lượng quyết định** và **rủi ro tồn đọng**, không chỉ tỷ lệ tickets đã được ký.

| KPI | Định nghĩa minh họa | Điều cần chú ý |
|---|---|---|
| **Approved exceptions by risk tier** | Số ngoại lệ active theo Low/Medium/High và business service. | High count cần đọc cùng phạm vi và criticality. |
| **Expired-but-active count** | Số ngoại lệ đã quá expires_at nhưng vẫn được sử dụng hoặc hiển thị active. | Nên có cảnh báo và xử lý ưu tiên. |
| **Exceptions without valid risk owner** | Hồ sơ thiếu owner hoặc authority tại thời điểm hiệu lực. | Không coi là hợp lệ chỉ vì có tên người. |
| **Conditional approval leakage** | Hồ sơ conditional chưa verified nhưng đã active ở runtime. | Thể hiện lỗ hổng workflow. |
| **Compensating-control failure rate** | Số controls bù trừ fail theo tests/health trong kỳ. | Phân biệt fail thật với thiếu evidence. |
| **Renewal frequency / aging** | Tuổi ngoại lệ, số lần gia hạn và thời gian phơi nhiễm. | Gia hạn liên tục có thể phản ánh remediation bị trì hoãn. |
| **Remediation on-time completion** | Số ngoại lệ được sửa trước deadline với retest / tổng đến hạn. | Ticket Done chưa phải verified closed. |
| **Residual risk exposure** | Rủi ro tồn dư theo dịch vụ, data class, loại threat, có trọng số nếu chính sách. | Không coi là xác suất tổn thất đo thực nghiệm. |
| **Emergency deviations reviewed** | Tỷ lệ emergency changes được hậu kiểm đúng hạn theo policy. | Review không được hợp thức hóa hoạt động trái yêu cầu bên ngoài. |
| **Approval evidence completeness** | Hồ sơ có scope, risk, DoA, testing, expiry và decision/audit trail đầy đủ. | Số file nhiều không thay tính thích hợp của evidence. |
| **Scope drift detection** | Số trường hợp asset/quyền thực tế vượt exception scope được phát hiện. | Cần authoritative inventory và effective-state checks. |
| **Revoke/retest latency** | Thời gian từ trigger vi phạm tới revoke/containment và kiểm tra lại. | Timestamp phải đúng nguồn và timezone. |

Không dùng một metric **approval rate = approved / submitted** làm mục tiêu hiệu suất chính. Nó có thể khuyến khích phê duyệt dễ dãi thay vì giảm rủi ro. Có những request nên bị từ chối.

### 18.1. Ví dụ báo cáo cho risk committee

Giả sử tháng 11 có:

- 28 ngoại lệ ACTIVE_APPROVED.
- 4 ngoại lệ đã hết hạn nhưng hệ thống vẫn gắn ACTIVE trước khi kiểm tra lại.
- 6 ngoại lệ gia hạn ít nhất hai lần.
- 3 ngoại lệ High nằm trên dịch vụ Critical.
- 2 compensating controls bị mất health heartbeat.
- 10 remediation tickets báo Done, nhưng 7 có retest đạt.

Kết luận đúng không phải “28 ngoại lệ đã được giải quyết”. Cần ưu tiên **4 overdue, 2 controls không còn chứng cứ health, 3 High/critical exposures và 3 tickets chưa đủ retest**; soát tính hợp lệ của approval và quyền sử dụng ở từng scope.

## 19. Kiểm tra tự động workflow mà không tự thay risk decision

### 19.1. Một số invariants có thể lập trình

~~~text
function evaluate_exception_activation(ex):
    if ex.requirement_applicability is UNKNOWN:
        return HOLD_FOR_REVIEW

    if ex.legal_compliance_review is REQUIRED_AND_MISSING:
        return HOLD_FOR_REVIEW

    if not authority_valid(ex.decision.approver, ex.risk, ex.scope):
        return ESCALATE_AUTHORITY

    if ex.decision.outcome not in {APPROVED, APPROVED_CONDITIONAL}:
        return NOT_ACTIVE

    if ex.decision.outcome == APPROVED_CONDITIONAL:
        if not all_mandatory_conditions_verified(ex):
            return PENDING_CONDITIONS

    if now_outside_validity_period(ex):
        return EXPIRED

    if scope_drift_detected(ex):
        return REASSESS_OR_REVOKE

    if mandatory_compensating_control_failed(ex):
        return REASSESS_OR_REVOKE

    return ELIGIBLE_FOR_ACTIVE_STATUS
~~~

Đây là **pseudocode**, không phải chính sách thực thi. Quyết định chấp nhận rủi ro vẫn thuộc người được phân quyền; hệ thống tự động chỉ hỗ trợ **chặn thiếu dữ liệu, kiểm soát điều kiện, lịch sử và cảnh báo**.

### 19.2. Negative tests cho workflow

1. **Approval sai quyền:** tạo request Medium nhưng dùng người không có quyền theo DoA → không được ACTIVE.
2. **Scope drift:** approval cho asset A nhưng gán vào B → bị chặn hoặc tạo finding.
3. **Expiry:** đổi thời gian tới sau ngày hết hạn trong sandbox → không thể tiếp tục coi active.
4. **Unverified control:** đánh dấu compensating control planned → không được cấp verified.
5. **Conditional activation:** risk owner duyệt có điều kiện nhưng test chưa pass → giữ PENDING_CONDITIONS.
6. **Self-approval:** requestor cùng danh tính approver khi policy đòi SoD → reject/escalate.
7. **Legal hold:** required legal review chưa hoàn tất → không cấp approval hợp lệ cho ràng buộc đó.
8. **Renewal audit:** gia hạn phải tạo decision version mới; không sửa audit log cũ.
9. **Control drift:** test source-health fail → trigger review/revoke theo severity policy.
10. **Remediation closure:** ticket Done nhưng test fail → exception không chuyển CLOSED_REMEDIATED.
11. **Incorrect timezone:** expiry theo UTC bị diễn giải nhầm múi giờ → workflow phải dùng timestamp nhất quán.
12. **Revocation:** risk owner thu hồi → effective policy, dashboard và owner alerts phải đồng bộ, không chỉ thay nhãn UI.

### 19.3. Data quality của exception register

- Exception IDs phải duy nhất, liên kết đúng policy version, asset IDs và effective control.
- Decision records có **actor, timestamp, action, rationale, version và provenance**.
- Không lưu token/credential bí mật trong hồ sơ.
- Các nguồn inventory, IAM, control-test và ticket có thể được đối chiếu theo stable identifiers.
- Các exception mồ côi (không owner, không asset, source policy bị xóa) phải được gắn cờ.
- Nếu không thể xác minh dữ liệu, trạng thái **UNKNOWN / NEEDS_REVIEW**, không mặc định approved.
- Có retention và quyền truy cập phù hợp với nhạy cảm của threat model và báo cáo findings.

## 20. Vai trò trong security assurance liên tục

~~~mermaid
flowchart LR
    RISKS["Risk assessment + appetite"] --> REQUEST["Exception request"]
    POLICY["Control requirements"] --> REQUEST
    REQUEST --> ANALYSIS["Security review + evidence"]
    ANALYSIS --> OWNER["Authorized risk owner decision"]
    OWNER --> MON["Conditional monitoring + expiry"]
    MON --> REM["Remediation / scope control"]
    REM --> RET["Independent retest"]
    RET --> CLOSE["Close exception / update assurance"]
    MON --> AUD["Audit / risk reporting"]
    AUD --> RISKS
~~~

Một chương trình security assurance có bằng chứng cần nối:

- **Security objective:** hệ thống phải đáp ứng mục tiêu bảo mật nào?
- **Requirement:** control baseline hoặc nghĩa vụ nào thực sự áp dụng?
- **Gap:** trạng thái thực tế khác yêu cầu ra sao?
- **Risk:** attack scenario và business consequence nào phát sinh?
- **Risk decision:** ai được phân quyền và vì sao chấp nhận rủi ro này?
- **Conditions:** controls thay thế và giám sát có hoạt động?
- **Evidence:** assessment, test, approval, audit trail và remediation.
- **Retest:** khi nào gap thực sự biến mất và assurance claim được khôi phục?

**Risk owner approval không kết thúc chuỗi này**; nó chỉ là một mốc trong vòng quản lý rủi ro còn tiếp diễn.

## 21. Checklist cho risk owner trước và sau phê duyệt

### 21.1. Trước quyết định

- [ ] Tôi có thẩm quyền chính thức theo DoA và risk appetite hiện hành.
- [ ] Request xác định chính xác requirement/policy version và applicability.
- [ ] Scope gồm asset IDs, quyền, dữ liệu, region/tenant và môi trường.
- [ ] Deviations được quan sát và có evidence, không chỉ mô tả phỏng đoán.
- [ ] Lý do nghiệp vụ và những phương án khác đã được đánh giá.
- [ ] Threat scenarios, inherent và residual risk có căn cứ.
- [ ] Các giả định/unknown trọng yếu được ghi và xử lý theo quy trình.
- [ ] Controls bù trừ đã triển khai và test đúng scope; chưa verified không được tính đạt.
- [ ] Legal/privacy/compliance review hoàn tất khi nguồn nghĩa vụ yêu cầu.
- [ ] Những stakeholder chịu tác động đã được tham vấn theo policy.
- [ ] Không có xung đột vai trò hoặc đã có biện pháp độc lập phù hợp.
- [ ] Remediation owner, milestones và deadline thực tế được ghi.
- [ ] Expiry, review interval, monitoring/alert và revoke triggers rõ.
- [ ] Từng quyết định approve/reject/escalate có lý do, người ký và timestamp.

### 21.2. Trong thời gian ngoại lệ

- [ ] Asset/control effective state vẫn nằm trong scope approval.
- [ ] Compensating controls được giám sát và có bằng chứng health.
- [ ] Risk owner nhận thông báo về incident, threat change hoặc policy drift.
- [ ] Remediation progress được review đúng lịch.
- [ ] Gia hạn được đánh giá mới; không sửa đè lịch sử và không gia hạn tự động.
- [ ] Dashboard không làm sai lệch control coverage hoặc compliance status.
- [ ] Ngoại lệ hết hạn/đã thu hồi không còn được coi hợp lệ ở runtime.

### 21.3. Khi đóng

- [ ] Control chuẩn hoặc phương án đáp ứng đã được phê duyệt có evidence đủ.
- [ ] Retest theo acceptance criteria đạt.
- [ ] Các thay đổi khẩn cấp/tạm thời được thu hồi an toàn nếu cần.
- [ ] Risk register, control coverage, findings và exception register được cập nhật nhất quán.
- [ ] Reviewer lưu kết luận và evidence, không chỉ đóng ticket.
- [ ] Bài học từ ngoại lệ lặp lại được đưa vào architecture, policy hoặc remediation program.

## 22. Bài tập tình huống

Một công ty fintech giả định có ba đề nghị:

**Đề nghị A — Chậm vá lỗ hổng:** Một API xử lý giao dịch Critical chưa kịp cập nhật phiên bản chứa lỗ hổng nghiêm trọng; requestor muốn gia hạn 90 ngày, đưa một ảnh WAF rule nhưng chưa thử đường bypass. Business owner có quyền phê duyệt tối đa rủi ro Medium; security đánh giá residual risk High.

**Đề nghị B — Ngoại lệ logging:** Một cluster mới chưa gửi cloud/Kubernetes admin audit về SIEM. Đội platform yêu cầu ngoại lệ 20 ngày; họ có source local và tính năng phát hiện thay thế nhưng chưa chứng minh alert delivery. Điều khoản với một khách hàng có thể yêu cầu audit trace cho hoạt động đặc quyền, còn đang chờ compliance xác định applicability.

**Đề nghị C — Phương án MFA thay thế:** Một portal legacy chưa hỗ trợ MFA nội bộ nhưng toàn bộ đường tương tác đã được chuyển qua gateway có MFA, direct access bị chặn và đã có negative tests, monitoring và migration plan trong 30 ngày. Risk assessment cho rằng residual risk nằm trong appetite; người phê duyệt thuộc DoA.

### 22.1. Yêu cầu thảo luận

1. Với A, có thể risk owner hiện tại tự ký không? Phải làm gì nếu vượt DoA?
2. Với A, bằng chứng WAF nào cần trước khi hạ residual risk và gia hạn?
3. Với B, vì sao không thể coi việc có local log đồng nghĩa audit requirement đã đáp ứng?
4. Với B, khi điều khoản hợp đồng chưa được diễn giải, trạng thái approval thích hợp là gì?
5. Với C, test nào chứng minh gateway không bị bypass và control thay thế đủ scope?
6. Viết hồ sơ phê duyệt mẫu cho C, gồm risk, conditions, expiry, triggers và remediation.
7. Đề xuất hai lý do khiến C phải bị revoke dù chưa tới ngày hết hạn.
8. Nếu A được một cấp có thẩm quyền cao hơn chấp nhận rủi ro, control status là PASS hay còn thiếu? Vì sao?
9. Sau 30 ngày, portal C vẫn chưa migrate; có thể tự kéo dài ngày hết hạn không?
10. Thiết kế một finding audit cho exception đã hết hạn vẫn active.

### 22.2. Gợi ý kết luận

- **A:** Risk owner Medium **không đủ thẩm quyền** cho residual risk High; cần escalation và đánh giá controls cùng phương án giảm scope. WAF screenshot chưa chứng minh chống exploit/bypass.
- **B:** thiếu evidence để xác minh audit coverage/alert delivery và chưa kết luận được yêu cầu hợp đồng; cần security và compliance review, không tự cấp N/A.
- **C:** có cơ sở để cân nhắc chấp thuận có điều kiện **nếu** evidence và authority hợp lệ; ngoại lệ vẫn có hạn và cần retest sau migration.
- **Gia hạn:** là decision mới có assessment và approval mới.
- **Risk acceptance:** không biến technical nonconformity thành PASS và không xóa nghĩa vụ bên ngoài.

## 23. Câu hỏi tự đánh giá

1. Vì sao risk owner không nhất thiết là control owner hoặc security reviewer?
2. Risk owner cần những thông tin nào ngoài một số điểm residual risk trước khi ký?
3. Phân biệt exception, compensating control, risk acceptance và N/A.
4. Vì sao một người không được ủy quyền không thể phê duyệt rủi ro High dù có chức danh quản lý?
5. Khi nào approval phải escalate đến cấp cao hơn hoặc dừng hoạt động?
6. Một ngoại lệ đối với policy nội bộ có thể tự miễn nghĩa vụ pháp lý không?
7. Vì sao approval có điều kiện không nên được coi là active khi controls chưa được kiểm chứng?
8. Điều gì tạo ra xung đột lợi ích khi requestor tự đánh giá và phê duyệt?
9. Cần evidence nào để khẳng định firewall/allowlisting thật sự giảm threat path?
10. Một ngoại lệ hết hạn nhưng vẫn chạy production cần xử lý và báo cáo ra sao?
11. Khi threat intelligence phát hiện exploit mới, approval còn hạn có cần review lại không?
12. Giữa ticket remediation Done và control test PASS có sự khác biệt gì?
13. Vì sao một bản risk assessment thiếu data flows, service principals hoặc third-party dependencies có thể dẫn đến chấp nhận rủi ro sai?
14. Thiết kế hai negative tests cho một workflow phê duyệt có kiểm soát SoD và expiry.
15. Hãy viết một decision record có đầy đủ scope, risk, DoA, controls, expiry, monitoring, rationale và revoke triggers.
16. Từ một ngoại lệ cụ thể, lập bảng nối **risk → requirement → compensating control → evidence → approval → finding → retest**.

**Điểm cốt lõi:** **Risk owner phê duyệt là một quyết định quản trị có thẩm quyền về rủi ro tồn dư, không phải dấu xác nhận hệ thống đã tuân thủ hoặc an toàn tuyệt đối.** Quyết định có giá trị khi có **phạm vi chính xác, requirement rõ, risk assessment có bằng chứng, controls bù trừ đã kiểm thử, giới hạn thẩm quyền, thời hạn, monitoring và cơ chế thu hồi/khắc phục**. Trong security assurance, mỗi approval phải truy vết được lý do và điều kiện duy trì, đồng thời chịu kiểm toán và tái đánh giá cho đến khi rủi ro được xử lý.
