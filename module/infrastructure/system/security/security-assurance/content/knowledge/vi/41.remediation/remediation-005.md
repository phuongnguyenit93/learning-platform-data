# Remediation deadline: Thiết lập, thực thi và kiểm chứng thời hạn khắc phục rủi ro bảo mật

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích **remediation deadline** và phân biệt nó với thời điểm phát hiện, phân loại, ngăn chặn, triển khai bản sửa, kiểm thử lại, đóng finding và chấp nhận rủi ro.
2. Xác định deadline dựa trên **mức độ rủi ro, khả năng khai thác, tác động kinh doanh, độ phơi nhiễm, nghĩa vụ áp dụng và mức độ sẵn sàng của biện pháp giảm thiểu**, thay vì chỉ lấy CVSS hoặc một nhãn severity.
3. Định nghĩa **đồng hồ SLA**, mốc bắt đầu, đơn vị thời gian, múi giờ, quy tắc ngày làm việc/ngày lịch, điều kiện tạm dừng và cách tính quá hạn nhất quán.
4. Thiết kế quy trình **finding → triage → risk treatment → action plan → implementation → verification → closure** với trách nhiệm và evidence rõ ràng.
5. Quản lý finding có hạn khắc phục sắp đến hoặc đã vượt, ngoại lệ và chấp nhận rủi ro có thời hạn, kiểm soát bù trừ và escalation theo thẩm quyền.
6. Xây dựng metric và báo cáo về **on-time remediation, overdue backlog, aging, deadline changes, verification delay và recurrence**, không làm sai tỷ lệ bằng cách bỏ các mục đang mở.
7. Đánh giá tình huống cloud IAM, lộ secret, logging/detection, dependency và disaster recovery để lựa chọn thời hạn và điều kiện đóng finding phù hợp.
8. Gắn remediation deadline với chương trình **security assurance liên tục**, lưu bằng chứng đủ để auditor độc lập kiểm chứng tính đúng hạn và hiệu lực của khắc phục.

## 1. Remediation deadline là gì?

**Remediation deadline** là mốc thời gian cuối cùng được xác lập để hoàn tất **một kết quả khắc phục đã định nghĩa rõ** đối với finding, điểm không phù hợp, lỗ hổng hoặc rủi ro bảo mật.

Nó không chỉ trả lời "phải xong khi nào?", mà còn đòi trả lời:

- Phải khắc phục **điều kiện gì**, trên **tập tài sản và môi trường nào**?
- Mốc thời gian được tính từ **sự kiện nào**, có dựa trên một nguồn nghĩa vụ cụ thể không?
- Việc áp dụng một biện pháp tạm thời có được tính là hoàn tất hay không?
- Ai là **risk owner**, ai thực hiện, ai kiểm chứng và ai chấp thuận ngoại lệ?
- Bằng chứng nào chứng minh đã sửa lỗi và đã giảm rủi ro trong đúng phạm vi?
- Nếu không thể đạt hạn, ai phải được báo, khi nào và quyết định tiếp theo là gì?

Ví dụ: scanner phát hiện một máy chủ production có dịch vụ quản trị mở ra Internet. Đội vận hành đóng cổng mạng sau 2 giờ, nhưng vẫn còn quyền truy cập quá rộng trong policy của một gateway khác. Nếu yêu cầu là **loại bỏ mọi đường truy cập quản trị không được phép**, việc đóng một firewall rule **chưa đủ chứng minh đã khắc phục**.

Trong mô-đun **SECURITY_SECURITY_ASSURANCE**, một deadline có giá trị khi truy vết được từ **threat/risk → security requirement/control → finding → action → test → evidence → verified closure**. Deadline là cơ chế quản trị việc giảm rủi ro trong thời gian, không phải chỉ là ngày hiển thị trên ticket.

### 1.1. Phân biệt các loại thời hạn

| Mốc | Ý nghĩa | Ví dụ |
|---|---|---|
| **Detection/notification target** | Mục tiêu phát hiện và thông báo về tình trạng cần xử lý. | SOC chuyển tín hiệu ưu tiên cao tới người trực theo mục tiêu đã duyệt. |
| **Triage deadline** | Hạn xác nhận tính hợp lệ, ảnh hưởng và owner. | Đánh giá liệu secret lộ có thực sự còn hiệu lực hay không. |
| **Containment deadline** | Hạn chặn hoặc hạn chế tác động cấp bách. | Tạm chặn route public hoặc vô hiệu một credential. |
| **Mitigation deadline** | Hạn triển khai biện pháp làm giảm rủi ro, có thể chưa giải quyết nguyên nhân. | Áp network allowlist tạm thời. |
| **Remediation implementation deadline** | Hạn hoàn thành sửa nguyên nhân/điều kiện không phù hợp trong phạm vi đã chốt. | Thay logic authorization và triển khai tới toàn bộ production. |
| **Verification/retest deadline** | Hạn xác minh bản sửa đáp ứng acceptance criteria. | Chạy negative access tests và kiểm tra trạng thái thực. |
| **Verified closure deadline** | Hạn có kết quả kiểm chứng đủ để đóng finding. | Security reviewer chấp thuận test, evidence và phạm vi. |
| **Risk-acceptance expiry** | Ngày quyết định chấp nhận rủi ro hoặc ngoại lệ hết hiệu lực. | Quyết định tạm dùng compensating control phải được xem lại. |
| **Compliance/contract deadline** | Hạn do nguồn nghĩa vụ áp dụng tạo ra. | Mốc đáp ứng theo điều khoản được legal xác nhận. |

Không tự coi các mốc này là giống nhau. Một đội có thể hoàn thành sửa lúc 17:00 nhưng test xác minh fail lúc 18:00; nếu tiêu chí đóng yêu cầu **được xác minh**, thì finding **chưa hoàn thành**, dù việc triển khai đã kết thúc.

### 1.2. Những phát biểu chưa đủ để chứng minh đạt hạn

- "Developer đã merge pull request" — chưa biết có deploy đúng production không.
- "Ticket đã chuyển Done" — chưa có evidence rằng control vận hành đúng.
- "Scanner không báo lại" — có thể asset biến mất khỏi phạm vi quét hoặc scanner lỗi.
- "Vendor cam kết patch" — đây là kế hoạch, không phải kết quả.
- "Đã có risk acceptance" — không chứng minh đã sửa, cũng không mặc nhiên hợp pháp hóa việc chưa đáp ứng nghĩa vụ bắt buộc.
- "Chúng tôi sửa đúng SLA" — chưa biết SLA bắt đầu lúc nào, kết thúc bằng tiêu chí nào và có bỏ mục quá hạn đang mở không.

## 2. Mối quan hệ giữa severity, risk và deadline

### 2.1. Severity không phải toàn bộ rủi ro

Một finding có thể có điểm kỹ thuật nghiêm trọng nhưng không thể khai thác trong cấu hình hiện tại. Ngược lại, một lỗi được chấm điểm kỹ thuật trung bình có thể rất cấp bách nếu ảnh hưởng trực tiếp tới giao dịch, tài khoản có đặc quyền hoặc dữ liệu nhạy cảm đang được Internet truy cập.

Khi đặt deadline cần xét:

1. **Exploitability:** có đường khai thác khả thi không, có yêu cầu xác thực hay quyền sẵn có không?
2. **Exposure:** dịch vụ có public, reachable từ mạng nội bộ, chỉ trong lab hay bị cô lập?
3. **Threat activity:** có bằng chứng về khai thác thực tế, incident liên quan hoặc attacker đang nhắm đến hệ thống không?
4. **Privilege và blast radius:** lỗi cho phép tăng quyền, xóa dữ liệu, kiểm soát cloud account hoặc di chuyển ngang tới đâu?
5. **Data sensitivity:** có PII, bí mật, khóa, dữ liệu tài chính hoặc dữ liệu an toàn quan trọng không?
6. **Business impact:** nếu bị khai thác, khả năng kinh doanh, an toàn, RTO/RPO và nghĩa vụ có thể bị ảnh hưởng như thế nào?
7. **Control environment:** đã có các kiểm soát bù trừ nào, chúng có thực sự hiệu lực không?
8. **Detection/response readiness:** có telemetry đáng tin và khả năng phát hiện/ngăn chặn không?
9. **Remediation feasibility:** có bản sửa, có thể tạm vô hiệu chức năng, điều kiện change window và dependency gì?
10. **Obligation:** policy, hợp đồng hoặc nguồn quy định đang áp dụng có yêu cầu thời hạn cụ thể không?

**CVSS**, nếu sử dụng để đánh giá lỗ hổng, là một nguồn thông tin đầu vào về đặc tính kỹ thuật; không phải đồng hồ remediation tự động áp dụng cho mọi hệ thống. Khi có dấu hiệu khai thác đang diễn ra, cần xem **incident response và containment ngay**, không chỉ xếp lại ticket vào một đợt vá định kỳ.

### 2.2. Kịch bản rủi ro quan trọng hơn nhãn chung

| Finding | Yếu tố quyết định tính khẩn cấp | Hành động phù hợp |
|---|---|---|
| Secret còn hiệu lực xuất hiện ở repository public. | Có thể bị truy cập bởi người ngoài; quyền token và audit của thời gian lộ. | Revoke/rotate và đánh giá lạm dụng ngay, sau đó sửa nguồn rò rỉ. |
| API cho phép đọc record của tenant khác. | Có thể lộ dữ liệu nhạy cảm giữa khách hàng. | Cô lập đường truy cập hoặc chặn chức năng nguy hiểm, sửa authorization và test. |
| Workload Kubernetes chạy privileged theo ngoại lệ không còn hiệu lực. | Quyền node/host, network, runtime và khả năng thoát container. | Giảm quyền, enforce admission, xem lại workload và exception. |
| Critical audit source không gửi event. | Mất khả năng quan sát hành vi, có thể ảnh hưởng điều tra và nghĩa vụ. | Khôi phục logging/health, đánh giá khoảng trống và test rule. |
| Thư viện phụ thuộc có lỗ hổng nhưng mã dễ tổn thương không reachable trong scope đã kiểm tra. | Mức độ khai thác thực tế, thay đổi trong tương lai, độ tin cậy của kết luận. | Xác minh bằng chứng, đặt hạn theo rủi ro, tiếp tục theo dõi. |
| Backup quan trọng không thể giải mã trong DR drill. | Khả năng mất dữ liệu và không đạt RTO/RPO khi thảm họa. | Khôi phục đường key/restore, ưu tiên test recovery và phương án dự phòng. |

Không nên lấy mức độ dễ sửa làm thước đo duy nhất. Một lỗi nguy hiểm nhưng khó sửa có thể cần **hạn containment ngắn** và **hạn khắc phục tận gốc dài hơn**, cùng quyết định rủi ro trong khoảng chờ.

## 3. Xác định thời hạn: từ nguồn nghĩa vụ đến quyết định theo rủi ro

Một **deadline policy** tốt phải nhất quán, có thẩm quyền và cho phép điều chỉnh theo bối cảnh được ghi nhận.

### 3.1. Thứ tự câu hỏi khi chọn hạn

1. Có **nghĩa vụ pháp lý, quy định, hợp đồng hay cam kết nội bộ** nào đặt hạn cụ thể cho finding này không?
2. Nếu có, **nghĩa vụ áp dụng cho ai, điều kiện nào, bắt đầu lúc nào và hoàn tất nghĩa là gì**?
3. Nếu không có hạn bắt buộc đã được xác nhận, policy bảo mật và risk appetite quy định **risk tier, SLA hoặc ngưỡng escalation** ra sao?
4. Nếu đang có khai thác hoặc sự cố nghiêm trọng, có cần chuyển sang **incident response/containment** thay vì chỉ remediation workflow?
5. Những controls tạm thời có thể giảm nguy cơ ngay trước khi có bản sửa đầy đủ không?
6. Những ràng buộc kỹ thuật và vận hành có cần lịch khác, người phê duyệt khác hay giai đoạn chuyển tiếp không?
7. Khi nào kết quả đã được triển khai và **kiểm chứng** đầy đủ?
8. Nếu không đáp ứng đúng hạn, quy trình escalation, exception hoặc ngừng dịch vụ là gì?

**Không được chọn hạn mới dài hơn chỉ vì team không đủ người rồi trình bày như hạn gốc.** Nếu cần điều chỉnh, phải giữ lịch sử, lý do, thẩm quyền và rủi ro tồn dư.

### 3.2. Ma trận thời hạn minh họa

Bảng dưới đây là **ví dụ chính sách đào tạo** cho một tổ chức giả định, **không phải SLA chuẩn cho mọi doanh nghiệp, tiêu chuẩn quốc tế hay thời hạn pháp lý**.

| Ưu tiên nội bộ | Ví dụ điều kiện | Mục tiêu containment | Hạn remediation được minh họa | Mức review |
|---|---|---|---|---|
| **P0 / Emergency** | Đang khai thác trên production hoặc có nguy cơ truy cập trái phép tức thời, tác động nghiêm trọng. | Bắt đầu hành động khẩn cấp; mốc cụ thể do IR playbook quyết định. | Hạn riêng theo incident, không áp một con số cố định. | Incident commander, security và risk owner. |
| **P1 / Critical** | Đường khai thác khả thi, phơi nhiễm cao, tài sản Critical hoặc tác động lớn. | Trong **4 giờ** từ mốc trigger theo policy giả định. | **7 ngày lịch** để khắc phục và kiểm chứng. | Security lead + business/risk owner. |
| **P2 / High** | Rủi ro cao nhưng chưa có dấu hiệu khai thác cấp bách. | Trong **1 ngày lịch** nếu cần biện pháp tạm. | **30 ngày lịch**. | Control owner và risk reviewer. |
| **P3 / Medium** | Rủi ro vừa, có kế hoạch sửa trong chu kỳ gần. | Theo đánh giá. | **60 ngày lịch**. | Service owner. |
| **P4 / Low** | Tác động/phơi nhiễm thấp với các giả định đã kiểm chứng. | Thường không cần ngăn chặn khẩn. | **90 ngày lịch**. | Service owner, theo policy. |

Đối với P1–P4, tổ chức có thể thiết lập **hai đồng hồ tách biệt**: implementation phải hoàn thành trước thời điểm đủ để đội assurance kịp retest, và **verified closure** phải đạt deadline cuối nếu policy định nghĩa như vậy.

### 3.3. Khi một finding phù hợp nhiều policy

Ví dụ cùng một phát hiện liên quan:

- SLA xử lý vulnerability theo chính sách bảo mật.
- Thời hạn phải báo và/hoặc sửa theo hợp đồng.
- Yêu cầu kiểm soát vận hành của ngành hoặc quy định áp dụng.
- Deadline riêng trong một corrective action plan đã phê duyệt.

Cần **tài liệu hóa từng nghĩa vụ**, nguồn, trigger, phạm vi và owner. Không tự hợp nhất thành một hạn "dài nhất" hoặc một hạn mới thuận lợi hơn mà có thể làm mất nghĩa vụ khác. Đội legal/compliance xác minh cách các nguồn áp dụng; risk owner và control owner sắp xếp thực hiện để đáp ứng chúng.

### 3.4. Containment không đồng nghĩa remediation

Một finding truy cập public không mong muốn có thể được **chặn ngay bằng firewall**, nhưng căn nguyên là IaC deployment cho phép mặc định public. Nếu chỉ sửa firewall thủ công:

- Đợt deploy kế tiếp có thể mở lại.
- Test automation không phát hiện regression.
- Một route khác hoặc một account khác có cùng lỗi.
- Người review không biết ai sở hữu security requirement.

Khi đó nên ghi:

- **Containment:** đóng đường public đang bị lạm dụng.
- **Root-cause remediation:** sửa IaC/policy/admission, đánh giá toàn population.
- **Verification:** negative network test, configuration scan, deployment regression test.
- **Closure:** reviewer xác nhận không còn lỗ hổng trong phạm vi và có giám sát drift.

## 4. Định nghĩa đồng hồ remediation một cách chính xác

Một deadline không kiểm toán được nếu không có **clock contract**.

### 4.1. Các mốc thời gian trong vòng đời

| Trường thời gian | Định nghĩa và mục đích |
|---|---|
| **observed_at** | Dấu thời gian đầu tiên của sự kiện/điều kiện, nếu có thể xác minh. |
| **detected_at** | Khi sensor hoặc người đánh giá phát hiện, phân biệt event time và ingest time nếu cần. |
| **reported_at** | Khi một nguồn tin đáng tin gửi thông báo/ticket; có thể là trigger theo một policy cụ thể. |
| **validated_at** | Khi triage xác nhận finding hợp lệ và phạm vi. |
| **clock_start_at** | Mốc chính thức bắt đầu SLA theo policy/contract; phải có nguồn và không được tự thay. |
| **severity_assessed_at** | Thời điểm severity/risk tier được xác lập hoặc điều chỉnh với lý do. |
| **assigned_at** | Thời điểm có control owner và action owner. |
| **containment_at** | Thời điểm biện pháp ngăn chặn được triển khai và bằng chứng xác nhận. |
| **implementation_at** | Thời điểm giải pháp được triển khai tới phạm vi yêu cầu. |
| **verification_at** | Thời điểm retest/assurance xác nhận các điều kiện nghiệm thu. |
| **closed_at** | Thời điểm finding được đóng theo quy trình, có liên kết evidence và reviewer. |
| **deadline_at** | Hạn gốc hoặc hạn hiện hành đã phê duyệt, phân biệt rõ từng loại. |
| **exception_expires_at** | Thời điểm quyết định ngoại lệ/chấp nhận rủi ro hết hiệu lực. |

**Không dùng ticket created_at để thay clock_start_at** khi policy thực sự tính từ một sự kiện trước đó. Tương tự, nếu kết thúc SLA bằng verified closure, dùng implementation_at sẽ báo kết quả đẹp nhưng sai.

### 4.2. Ngày lịch hay ngày làm việc?

Một policy cần quy định ít nhất:

- **Duration type:** giờ liên tục, ngày lịch, ngày làm việc, ca trực hoặc thời gian theo lịch hỗ trợ.
- **Timezone:** thường lưu các mốc dưới dạng UTC/offset; có quy tắc tính ngày địa phương nếu nguồn quy định.
- **Start/end semantics:** deadline có bao gồm giây/phút cuối? Khoảng thời gian tính kiểu inclusive hay exclusive?
- **Holidays/weekends:** áp dụng lịch của vùng/đơn vị nào nếu tính ngày làm việc?
- **Pause/stop condition:** có trường hợp nào được phép dừng đồng hồ, ai phê duyệt, evidence ra sao?
- **Reclassification:** đổi severity có thay deadline không và có được áp dụng hồi tố không?
- **Reopen:** finding đóng rồi tái xuất hiện có giữ lịch sử vi phạm hay tạo hồ sơ mới có liên kết?
- **Required completion:** triển khai, kiểm tra lại hay được quản trị xác nhận đóng?

Khuyến nghị thực tiễn là lưu deadline dưới dạng **mốc thời gian tuyệt đối** đã được tính từ rule được duyệt để tránh những dashboard dùng ngày địa phương khác nhau cho kết quả khác nhau.

### 4.3. Ví dụ tính ngày lịch

Giả định chính sách nội bộ quy định:

- P1 phải đạt **verified closure trong 7 × 24 giờ** từ clock_start_at.
- Clock bắt đầu **2026-11-01 10:00 UTC**.

Khi đó deadline là **2026-11-08 10:00 UTC**.

- Hoàn thành sửa **2026-11-07 16:00 UTC** nhưng test pass **2026-11-08 11:00 UTC** → **quá hạn 1 giờ** theo quy tắc lấy verification_at.
- Nếu test pass **2026-11-08 09:00 UTC**, reviewer đóng ticket **2026-11-08 12:00 UTC**, kết luận phụ thuộc contract: nếu SLA kết thúc khi test được xác minh, đạt; nếu đòi đóng được phê duyệt trước hạn, chưa đạt. Phải quy định trước.
- Nếu thực hiện containment từ ngày 1 và deploy bản sửa vào ngày 7, vẫn không tự gọi là đạt SLA verified closure khi retest trễ.

Đây là ví dụ **giờ liên tục**, không tự chuyển thành "7 ngày làm việc".

### 4.4. Deadline có giá trị ngày, không có giờ

Nếu một hợp đồng chỉ quy định “trong ngày 08/11” theo múi giờ đã xác nhận, cần diễn giải ngày cuối theo nguồn; không tự đổi thành 08/11 00:00 UTC. Nên lưu thêm **source deadline expression**, **timezone** và **derived deadline_at**, người chấp thuận chuyển đổi và logic xử lý DST nếu có.

### 4.5. Trạng thái at-risk, due và overdue

Với finding còn mở:

- **Time remaining** = deadline_at − now_at.
- **Overdue duration** = max(0, now_at − deadline_at).
- **At risk**: thời gian còn lại ít hơn lead time cần thiết cho triển khai/retest hoặc khả năng hoàn thành thấp theo assessment.

Nếu finding đã verified closed, tính **lateness** so với deadline từ mốc kết thúc được chấp nhận, không phải từ thời gian xem dashboard. Một item đóng muộn vẫn là **historical SLA breach**, không tự biến thành đúng hạn khi closed.

## 5. Lifecycle từ phát hiện đến đóng finding

### 5.1. Sơ đồ

~~~mermaid
flowchart TD
    D["Detect / Audit finding"] --> T["Validate + scope + severity"]
    T --> O["Owner + deadline contract"]
    O --> C{"Urgent containment?"}
    C -->|Có| I["Containment + evidence"]
    C -->|Không| P["Action plan"]
    I --> P
    P --> A["Implement root-cause fix"]
    A --> V["Independent retest / verification"]
    V --> K{"Acceptance met?"}
    K -->|Có| X["Verified closure + evidence"]
    K -->|Không| F["Reopen / remediate again"]
    F --> P
    P --> R["Due-date monitoring + escalation"]
    R --> E{"Delay / exception needed?"}
    E -->|Có| M["Formal risk decision + compensating control"]
    M --> P
    E -->|Không| P
~~~

Mũi tên mô tả luồng nghiệp vụ; một finding có thể chuyển thẳng sang incident response nếu có tấn công đang diễn ra. **Risk acceptance** là quyết định xử lý rủi ro và trạng thái riêng, không được ngầm nối với “verified closure” như thể control đã sửa.

### 5.2. Bước 1 — Validation và scope

Trước khi gắn deadline:

- Xác minh finding có thật, xác định false positive nếu có bằng chứng.
- Ghi nguồn và độ tin cậy, affected assets, data classes, environments.
- Đánh giá nguyên nhân hoặc điều kiện đã quan sát, không tự suy đoán attacker.
- Kết nối finding với control objective, security requirement và risk scenario.
- Xác định owner có khả năng xử lý, các team phụ thuộc và quyền phê duyệt.
- Xác định policy/source áp dụng cho deadline, mốc bắt đầu và severity.

**Triage chưa xong không có nghĩa là rủi ro không tồn tại.** Với phát hiện cấp bách, thực hiện containment theo IR ngay khi đủ căn cứ và quyền hạn, đồng thời tiếp tục xác minh phạm vi.

### 5.3. Bước 2 — Action plan có thể nghiệm thu

Một kế hoạch sửa nên ghi:

1. Điều kiện hiện tại và nguyên nhân đã xác minh hoặc đang điều tra.
2. Hành động containment/mitigation tạm thời, tính hiệu lực và giới hạn.
3. Phương án sửa tận gốc và lựa chọn nếu bản vá chưa khả dụng.
4. Tập tài sản và service được sửa.
5. Thứ tự rollout, change approval, người thực hiện và phương án rollback.
6. Tiêu chí test pass/fail, evidence dự kiến và người retest.
7. Mốc nội bộ: thiết kế xong, triển khai lab, canary, rollout, verification.
8. Deadline theo nghĩa vụ; buffer để xử lý kết quả test fail.
9. Nguy cơ còn lại trong thời gian chờ, ai giám sát và trigger escalation.

Một action plan chỉ ghi “patch next sprint” mà không có release, population, acceptance criteria và thời điểm retest thường chưa đủ để quản trị rủi ro.

### 5.4. Bước 3 — Thực thi và bằng chứng

Khi triển khai:

- Lưu change records, commit/digest, config và release identifiers.
- Có audit ai thay đổi, ở đâu, lúc nào và theo thẩm quyền nào.
- Xác minh deployment tới đủ assets/account/region/cluster.
- Theo dõi rollback, test fail, side effect và các trường hợp drift.
- Duy trì controls tạm thời tới khi bản sửa có bằng chứng hiệu lực.
- Nếu có thay đổi phạm vi, cập nhật finding và risk assessment, không lặng lẽ giảm population.

### 5.5. Bước 4 — Verification và closure

Đóng finding cần ít nhất:

- **Observed condition** ban đầu đã được giải quyết trong đúng phạm vi.
- Test phù hợp được chạy lại, gồm negative/boundary/integration tests nếu cần.
- Không còn đường bypass hoặc recurrence đã biết theo criteria.
- Evidence hiện hành, đủ provenance và liên kết tới source/finding.
- Reviewer có thẩm quyền xác nhận kết quả.
- Ngày verified closure được ghi chính xác.
- Tình trạng deadline và breach history được bảo toàn.
- Theo dõi rủi ro tồn dư hoặc hành động phòng ngừa tái phát nếu cần.

**Không nên đóng finding chỉ vì patch đã deploy**, đặc biệt khi security assurance yêu cầu chứng minh control vận hành hiệu lực.

## 6. Deadline gốc, hạn sửa đổi và hồ sơ phê duyệt

Thời hạn có thể cần thay đổi do thực tế: không có patch, thiết bị legacy cần thay thế, test phát hiện ảnh hưởng vận hành, vendor phụ thuộc hoặc yêu cầu pháp lý được xác định lại. Tuy nhiên thay deadline phải **có kiểm soát**.

### 6.1. Những trường cần giữ đồng thời

- **Original deadline:** thời hạn được xác định lần đầu theo policy/nguồn đã áp dụng.
- **Current approved deadline:** hạn hiện hành nếu được phép điều chỉnh.
- **Deadline revision history:** ai đổi, từ mốc nào sang mốc nào, lý do, ngày duyệt và nguồn thẩm quyền.
- **SLA breach against original:** đã từng vượt hạn gốc hay chưa.
- **SLA status under current approval:** tình trạng theo hạn được phê duyệt hiện hành.
- **Risk acceptance/exception:** quyết định riêng, phạm vi, expiry và controls bù trừ.
- **Escalation history:** đã thông báo ai, khi nào, phản hồi và quyết định.

Nhờ giữ hai đường đánh giá, tổ chức có thể quản lý thực tế mà không làm số liệu lịch sử biến mất.

### 6.2. Trường hợp điều chỉnh hợp lệ

Có thể xem xét điều chỉnh theo policy khi:

- Phạm vi technical finding thay đổi sau khi có bằng chứng mới.
- Patch chính thức bị rút lại do gây gián đoạn nghiêm trọng; phải có biện pháp giảm rủi ro và deadline thay thế.
- Hạ tầng legacy không thể vá ngay nhưng có phương án cô lập, thay thế và decommission được duyệt.
- Có yêu cầu change freeze hoặc quy trình an toàn áp dụng, trong khi nguy cơ được quản trị bằng controls tạm.
- Một yêu cầu mới có thời hạn chuyển tiếp đã được xác định đúng thẩm quyền.
- Vendor dependency cần cơ chế thẩm định/phê duyệt và phương án contingency.

**Điều chỉnh có thẩm quyền không chứng minh rằng yêu cầu pháp luật hoặc hợp đồng được miễn.** Nếu deadline gắn nghĩa vụ bắt buộc, phải xử lý qua legal/compliance và cơ chế áp dụng, không chỉ risk owner nội bộ.

### 6.3. Trường hợp không nên dùng làm lý do làm mới đồng hồ

- Đổi người nhận ticket.
- Chuyển ticket giữa hai hệ thống tracking.
- Chia một finding quá hạn thành nhiều child tickets mà không giữ parent/history.
- Đổi severity sau khi đã quá hạn chỉ để tránh báo cáo vi phạm, không có evidence rủi ro mới.
- Đóng và mở lại ticket vì validation chưa pass.
- Coi “đã gửi yêu cầu cho vendor” là hoàn tất toàn bộ nghĩa vụ khắc phục.
- Loại asset khỏi inventory vì thiếu quyền truy cập hoặc không quét được.

Mọi thay đổi phải giữ **original event, source, owner, severity history và audit trail**.

## 7. Ngoại lệ, risk acceptance và compensating controls

### 7.1. Trường hợp không thể sửa trước hạn

Một nhóm có thể cần tiếp tục vận hành trong khi chưa sửa được finding. Quy trình phù hợp gồm:

1. Xác nhận deadline gốc, affected assets và rủi ro nếu không sửa.
2. Phân tích các phương án **avoid, mitigate, replace, disable feature, isolate hoặc accept**.
3. Chọn compensating controls giúp giảm likelihood/impact phù hợp, xác định thời gian áp dụng.
4. Test hiệu lực của controls tạm, không chỉ ghi một ý tưởng vào ticket.
5. Xác định risk owner có thẩm quyền và legal/compliance nếu liên quan nghĩa vụ bên ngoài.
6. Ghi thời hạn hết hiệu lực, điều kiện revoke, người giám sát và re-review trigger.
7. Duy trì kế hoạch sửa tận gốc hoặc quyết định loại bỏ dịch vụ có owner và mốc.
8. Theo dõi trạng thái remediation và assurance riêng, không tự chuyển sang VERIFIED_CLOSED.

### 7.2. Mẫu quyết định ngoại lệ

~~~yaml
exception_id: EXC-2026-014
finding_id: FIND-IAM-207
source_policy: "SEC-REMEDIATION-v2"
affected_assets:
  - "legacy-prod-gateway"
condition: "Admin access path not fully compliant"
original_deadline_at: "2026-11-08T10:00:00Z"
requested_deadline_at: "2026-11-22T10:00:00Z"
reason: "Vendor firmware upgrade requires staged validation"
inherent_risk: critical
compensating_controls:
  - "Isolate management path from public networks"
  - "Restrict access to privileged jump hosts"
  - "Monitor management sessions and changes"
verification:
  test_ids: ["NET-T01", "IAM-T04", "LOG-T03"]
  status: "pending"
risk_owner: "business-service-owner"
approvers:
  - "security-risk-authority"
expires_at: "2026-11-22T10:00:00Z"
legal_compliance_review: "required-if-contractual-deadline-applies"
exception_status: requested
finding_status: open
~~~

Đây là dữ liệu **giả định để minh họa**; status **requested** có nghĩa là chưa được phê duyệt. Việc ghi requested_deadline_at không làm SLA tự thay đổi. Ngoại lệ cần được xử lý qua workflow thẩm quyền và phải có bằng chứng rằng compensating controls thực sự đã triển khai.

### 7.3. Phân biệt các kết luận

| Tình trạng | Cách ghi trung thực |
|---|---|
| Finding đã sửa, retest PASS đúng hạn. | Verified closed on time. |
| Finding đã sửa, retest PASS nhưng sau hạn gốc. | Verified closed late; giữ lịch sử breach, có thể ghi current approval nếu phù hợp. |
| Có containment hiệu lực nhưng chưa sửa tận gốc. | Mitigated/contained, remediation open. |
| Được chấp nhận rủi ro có thời hạn nhưng control chưa sửa. | Risk accepted with conditions; finding vẫn chưa verified remediated. |
| Test fail sau khi đội triển khai báo hoàn tất. | Remediation verification FAIL; sửa lại và đánh giá deadline. |
| Thiếu telemetry hoặc không thể retest. | Inconclusive / insufficient evidence, không coi là PASS. |
| Finding xác định là false positive bằng evidence phù hợp. | Closed as invalid/false positive, tách khỏi verified remediation. |
| Asset đã decommission có bằng chứng kiểm tra không còn trong phạm vi. | Resolved by verified removal, theo policy; không tính như đã patch. |

Cần tránh một trạng thái “Closed” duy nhất gộp tất cả các trường hợp trên, vì nó làm mất khả năng đánh giá chất lượng remediation.

## 8. Escalation trước hạn, khi đến hạn và sau hạn

Remediation deadlines nên có **cơ chế cảnh báo theo thời gian và rủi ro**, không đợi quá hạn mới hành động.

### 8.1. Ví dụ escalation ladder

| Giai đoạn | Tín hiệu | Hành động | Ai nhận |
|---|---|---|---|
| **Triage overdue** | Chưa có owner/severity đúng thời hạn triage. | Escalate việc phân loại, tạm áp controls khẩn khi phù hợp. | Security triage lead, service owner. |
| **At risk** | Công việc còn lại lớn hơn thời gian còn lại; patch chưa có hoặc test slot chưa được đặt. | Replan, hỗ trợ nguồn lực, áp mitigation, dự báo breach. | Delivery lead, security và business owner. |
| **Approaching deadline** | Còn ít thời gian theo ngưỡng trong policy. | Xác minh rollout, đặt retest, nhắc evidence và kiểm tra phụ thuộc. | Action owner, assurance reviewer. |
| **Deadline reached** | Chưa đạt tiêu chí hoàn thành tại mốc deadline. | Ghi breach; xem rủi ro và kích hoạt escalation phù hợp. | Security lead, risk owner, management theo tier. |
| **Overdue continuing** | Ngày/giờ quá hạn tăng hoặc biện pháp tạm mất hiệu lực. | Tăng ưu tiên, review tần suất dày, xem xét ngừng dịch vụ nếu rủi ro không chấp nhận. | Risk committee/business leadership nếu policy quy định. |
| **Verified closure** | Retest PASS và reviewer chấp thuận. | Lưu result, tính on-time/late đúng mốc và cập nhật metrics. | Finding owner, assurance/GRC. |

Ngưỡng “còn 7 ngày” hoặc “quá hạn 24 giờ” chỉ là lựa chọn theo policy, không có một thang escalation phổ quát. Với finding P0 có khai thác đang diễn ra, một ngưỡng thông báo theo ngày là không phù hợp.

### 8.2. Theo dõi deadline dự báo

**At-risk finding** có thể chưa quá hạn nhưng:

- Không có remediation owner được xác nhận.
- Một dependency vendor chưa có cam kết chắc chắn.
- Change window sau deadline.
- Không có môi trường test hoặc người reviewer.
- Deploy được lên staging nhưng production cần rollout theo nhóm.
- Compensating control đang fail hoặc hết hạn.
- Dữ liệu evidence chưa có, nhất là các log trong kỳ.

Do vậy dashboard cần trạng thái **forecast** và **blocker**, không chỉ “due in 3 days”.

### 8.3. Đừng để escalation biến thành việc dời ngày

Mục tiêu escalation là **làm rõ quyết định quản trị rủi ro**: huy động nguồn lực, giảm exposure, ngừng tính năng, chuyển phương án, phê duyệt xử lý phù hợp hoặc chấp nhận rủi ro trong thẩm quyền. Nếu chỉ thay due date hàng tuần, chương trình không còn đo được thời gian tổ chức phơi nhiễm.

## 9. Evidence để chứng minh đúng hạn

### 9.1. Hồ sơ remediation tối thiểu

Một finding có thể kiểm toán cần:

- Finding ID, source, control/requirement ID, severity và evidence ban đầu.
- Affected assets với scope rõ, data class và business service.
- Original detection/notification, triage, clock start, deadline policy.
- Current approved deadline, mọi quyết định revision và risk acceptance.
- Root cause hoặc condition cần sửa, action plan và owner.
- Containment/mitigation action, thời gian và kết quả test.
- Implementation artifacts: commit/release/change ID, config, change approval, rollout history.
- Retest artifacts: expected/actual, negative tests, raw telemetry, coverage, tool/version.
- Verified close time và reviewer decision.
- SLA breach/late history, exceptions, unresolved residual risk.
- Links tới incident, vendor request, audit finding hoặc compliance obligation nếu có.

### 9.2. Provenance và độ tin cậy

| Evidence | Hỗ trợ claim | Không tự chứng minh |
|---|---|---|
| Scanner report lúc phát hiện. | Một điều kiện có thể tồn tại ở asset đã quét. | Tất cả asset bị ảnh hưởng đã được tìm thấy. |
| Pull request và CI PASS. | Code thay đổi đã được review và test ở pipeline. | Production đã áp dụng và không có bypass. |
| Change/deployment record. | Artifact/config đã được triển khai tới phạm vi ghi trong record. | Control thực sự ngăn hành vi sau deploy. |
| Negative authorization/reachability test. | Đường truy cập trái phép được kiểm tra bị từ chối. | Mọi đường bypass đều đã được kiểm tra. |
| IAM/config snapshot hiện hành. | Trạng thái cấu hình tại thời điểm được chụp. | Trạng thái cả kỳ hoặc mọi effective permission. |
| Restore/DR exercise. | Khả năng recovery trong kịch bản, data và thời gian đã thử. | Recovery đạt mọi kịch bản hoặc sạch khỏi ransomware. |
| Formal risk acceptance. | Rủi ro được quyết định theo thẩm quyền và điều kiện nhất định. | Finding đã được sửa hoặc nghĩa vụ pháp lý được miễn. |
| Reviewer signoff. | Quy trình đã đánh giá evidence theo tiêu chí. | Evidence chính xác nếu reviewer thiếu nguồn hoặc scope. |

**Hash đúng** giúp phát hiện thay đổi của một artifact kể từ khi ghi nhận; không chứng minh nguồn scanner đầy đủ, timestamp đúng hoặc nội dung kết luận không sai.

### 9.3. Đo clock từ các nguồn nhất quán

Khi tính hạn, nên lưu các timestamp **ISO 8601 có offset hoặc UTC**, giữ raw event time và ingestion time khác nhau khi cần. Nếu một scanner report có timestamp được tạo bởi collector chậm nhiều giờ, phải xác định **đồng hồ policy** đang dựa vào detection hay receipt, tránh sửa âm thầm thời gian.

Ticketing hệ thống khác nhau có thể dùng timezone, precision và trạng thái workflow khác; khi tổng hợp dashboard phải chuẩn hóa có provenance và ghi quy tắc chuyển đổi.

## 10. Data model cho remediation deadline

### 10.1. Một record minh họa

~~~json
{
  "finding_id": "FIND-CLOUD-2026-017",
  "source": "approved-cloud-security-assessment",
  "control_id": "CTRL-IAM-002",
  "business_service": "order-platform",
  "affected_assets": ["cloud-prod-account-a"],
  "risk": {
    "priority": "P1",
    "severity_source": "risk-assessment-v3",
    "exploitability": "high",
    "exposure": "production-management-path"
  },
  "time_contract": {
    "policy_id": "SEC-REMEDIATION-v2",
    "clock_start_at": "2026-11-01T10:00:00Z",
    "duration_type": "continuous-hours",
    "original_deadline_at": "2026-11-08T10:00:00Z",
    "current_approved_deadline_at": "2026-11-08T10:00:00Z",
    "completion_criterion": "verified-closure"
  },
  "status": "verification-pending",
  "owner": "identity-platform",
  "containment_at": "2026-11-01T13:00:00Z",
  "implementation_at": "2026-11-07T16:00:00Z",
  "verification_at": null,
  "closed_at": null,
  "evidence_refs": [
    "EV-IAM-CHANGE-001",
    "EV-NEGATIVE-TEST-PENDING"
  ],
  "exception_id": null,
  "deadline_revisions": [],
  "reviewer": "security-assurance"
}
~~~

Tất cả dữ liệu trên là **ví dụ giả lập**, không phải schema bắt buộc. Trạng thái verification-pending nói rõ bản sửa đã triển khai nhưng chưa đủ điều kiện để đóng.

### 10.2. Thiết kế quan hệ giữa các thực thể

~~~mermaid
flowchart LR
    R["Risk / Security objective"] --> FIND["Finding"]
    CR["Requirement / Control criterion"] --> FIND
    FIND --> CLOCK["Deadline contract + original/current"]
    FIND --> ACT["Actions + owner + change records"]
    ACT --> VER["Retest + evidence + reviewer"]
    CLOCK --> MET["SLA metrics"]
    VER --> MET
    FIND --> EX["Exception / risk decision"]
    EX --> MET
    FIND --> REP["Remediation dashboard"]
    MET --> REP
    VER --> REP
~~~

**Một finding có thể có nhiều assets hoặc nhiều actions.** Nếu tính tỷ lệ theo finding ID thay vì từng asset-control pair, có thể có một finding “đóng” khi vẫn còn asset chưa sửa. Đơn vị đo cần được chọn theo mục tiêu báo cáo và acceptance criteria.

## 11. Metrics: đo SLA mà không che backlog quá hạn

### 11.1. On-time verified closure rate

Với tập findings **có deadline đến hạn trong kỳ báo cáo**, có thể xác định:

\[
\text{On-time closure rate}
=\frac{\text{số finding đạt verified closure trước hoặc đúng hạn}}
{\text{số finding có deadline trong kỳ}}\times100\%
\]

Phải công bố:

- Có bao gồm findings còn mở khi deadline đã qua không? **Có**, nếu metric đo nghĩa vụ đến hạn, vì chúng là overdue.
- Có loại các mục được xác định false positive hoặc không áp dụng không? Chỉ theo quy tắc đã xác minh, công bố số bị loại.
- Có xét revised deadlines không? Báo riêng metric theo **original deadline** và **current approved deadline**.
- Có gồm các findings không đủ evidence để quyết định không? Báo **inconclusive/unknown** riêng, không mặc định đạt.
- Một finding được phát hiện vào cuối kỳ nhưng deadline trong kỳ sau thì không nằm trong cohort đã đến hạn, song vẫn xuất hiện ở backlog.

Một số tổ chức đo **on-time rate trên các findings đã đóng**; chỉ số đó hữu ích cho nhóm đã đóng, nhưng dễ gây thiên lệch vì bỏ các finding mở quá hạn. Không dùng nó thay thế metric dựa trên **cohort đến hạn**.

### 11.2. Các phép đo quan trọng khác

| Metric | Định nghĩa | Điểm phải kiểm soát |
|---|---|---|
| **Open overdue backlog** | Số finding còn mở đã vượt deadline tại snapshot, theo priority và owner. | Không bỏ finding có exception mà không nêu trạng thái. |
| **Overdue age** | Thời gian từ deadline đến now đối với finding còn mở quá hạn. | Cần timezone, giờ liên tục hay ngày làm việc. |
| **Finding age** | Thời gian từ clock_start tới now/close, tùy trạng thái. | Không trộn với overdue duration. |
| **Time to containment** | Containment verified time − trigger time. | Containment không phải verified remediation. |
| **Time to implementation** | Implementation time − clock start. | Patch deployed chưa chắc pass retest. |
| **Time to verified remediation** | Verified closure time − clock start. | Đo theo đúng completion criterion. |
| **Verification lag** | Verification time − implementation time. | Có thể âm sai do timestamp/clock error. |
| **Deadline revision rate** | Số findings có hạn được sửa / số findings thuộc cohort, theo chính sách. | Cần phân biệt revision do source đúng và dời vì trễ. |
| **Exception overdue/expiry** | Ngoại lệ quá hạn hoặc hết hiệu lực, theo severity. | Chấp nhận rủi ro không làm hết finding. |
| **Reopen/recurrence rate** | Findings tái xuất hiện sau closure trong một kỳ theo định nghĩa. | Truy vết root cause, không coi là finding mới hoàn toàn độc lập. |
| **At-risk due soon** | Findings chưa quá hạn nhưng dự báo không hoàn tất. | Cần milestone, dependency và retest slot. |
| **Evidence sufficiency rate** | Tỷ lệ closure decisions có evidence đủ theo acceptance criteria. | Ticket Done chưa chắc sufficient. |

Tên **MTTR** thường bị dùng cho *mean time to respond, repair, resolve* hoặc *recover*. Không đưa một con số MTTR vào báo cáo nếu không viết rõ **điểm bắt đầu và kết thúc**.

### 11.3. Ví dụ cohort có 10 findings đến hạn

Giả sử trong tháng có **10 findings P1/P2 đến deadline gốc**:

- 6 findings verified closed đúng hoặc trước hạn.
- 2 findings verified closed sau hạn.
- 1 finding vẫn mở và đã quá hạn.
- 1 finding được triển khai nhưng test chưa PASS khi hạn đến.

Khi đó **original-deadline on-time verified closure rate = 6/10 = 60%**.

Không báo **6/8 = 75%** nếu 8 là số đã đóng vì sẽ ẩn hai findings chưa đạt hạn. Nếu một trong hai mục mở có ngoại lệ được duyệt, cần báo riêng risk status; không xóa nó khỏi historical original-deadline cohort trừ khi chính sách định nghĩa phạm vi metric khác và được công bố.

### 11.4. Percentile và phân phối

Đối với các findings đã verified closed, nên xem **median, p90/p95** của thời gian khắc phục theo priority và business service để phát hiện đuôi dài, không chỉ trung bình.

Nhưng dữ liệu đóng có thiên lệch: **những finding khó nhất có thể vẫn đang mở**. Vì vậy cần xem đồng thời:

- Time-to-close distribution của nhóm đã đóng.
- Open backlog aging và deadline breaches.
- Cohort follow-up theo thời gian từ lúc phát hiện/đến hạn.
- Severity changes và exceptions.
- Incidents hoặc findings có tác động lớn không thể hiện trong số trung bình.

### 11.5. Báo cáo trạng thái theo mốc thời gian

Một dashboard nên hiển thị tại **as_of_at** cụ thể:

- Count open/not due, due soon, at risk, overdue, verification pending.
- Count verified closed on time, verified closed late và false-positive closed (riêng).
- Original deadline và current approved deadline.
- Containment/mitigation status và test result.
- Severity, business criticality, exposure và owner.
- Top unresolved risks và escalations đã thực hiện.

Không thay đổi định nghĩa giữa các kỳ mà không version metric và chú thích.

## 12. SQL minh họa để báo cáo deadline

Giả sử bảng đã làm sạch:

- **finding_id** là duy nhất, trạng thái cuối cùng và lịch sử revision được truy vết ở bảng khác.
- **clock_start_at**, **original_deadline_at**, **current_deadline_at**, **verified_at** là timestamps chuẩn UTC.
- **is_valid_finding** xác định finding thật, thuộc scope và không bị loại bởi false-positive decision có evidence.
- **verified_at** chỉ được ghi sau khi test đáp ứng các điều kiện closure.

~~~sql
SELECT
    priority,
    COUNT(*) AS due_findings,
    SUM(CASE
        WHEN verified_at IS NOT NULL
         AND verified_at <= original_deadline_at
        THEN 1 ELSE 0
    END) AS verified_on_time,
    SUM(CASE
        WHEN verified_at IS NULL
        THEN 1 ELSE 0
    END) AS not_yet_verified_at_report_time,
    SUM(CASE
        WHEN verified_at IS NOT NULL
         AND verified_at > original_deadline_at
        THEN 1 ELSE 0
    END) AS verified_late,
    ROUND(
        100.0 * SUM(CASE
            WHEN verified_at IS NOT NULL
             AND verified_at <= original_deadline_at
            THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0),
        2
    ) AS original_due_on_time_pct
FROM remediation_findings
WHERE is_valid_finding = 1
  AND original_deadline_at >= :period_start_utc
  AND original_deadline_at < :period_end_utc
GROUP BY priority
ORDER BY priority;
~~~

**Giới hạn của ví dụ:** Đây là pseudo-SQL gần với các dialect phổ biến; phải xử lý khác biệt hệ CSDL, timestamps và nguồn trạng thái. Nếu query chạy vào giữa kỳ, mục **not_yet_verified_at_report_time** có thể gồm những deadline chưa thực sự qua; chỉ gọi chúng **overdue** khi đã kiểm tra deadline ≤ as_of_at. Nếu một finding được verified closed rồi reopen do cùng defect, cần một data model với lịch sử sự kiện để tránh sai lệch kết luận và tính lại thời hạn theo policy.

### 12.1. Kiểm tra metric pipeline

- Một item mở quá hạn xuất hiện trong mẫu số cohort deadline và bảng overdue.
- Một item verified after due không được đổi thành on-time do reviewer sửa ticket ngày hôm sau.
- Một item có approved extension vẫn giữ original deadline và lịch sử revision.
- Một false positive chỉ bị loại sau quyết định có evidence.
- Một item không có owner hoặc thiếu start time được đưa vào data-quality exception, không tự xóa.
- Chia finding thành child tickets không làm biến mất parent breach.
- Chuyển severity không có rationale và timestamp bị cảnh báo.
- Đồng hồ bị timezone shift phải được phát hiện và tính lại theo source rule.
- Test fail sau deploy vẫn giữ finding open.
- Completion bằng điều kiện bù trừ chỉ được coi đạt nếu **alternative acceptance path** được phê duyệt và thực sự test.

## 13. Ví dụ xuyên suốt: lỗ hổng quyền quản trị ở Order Platform

### 13.1. Bối cảnh và security objective

Một tổ chức có **Order API**, Kubernetes cluster và hai cloud accounts production. Security objective yêu cầu **mọi đường tăng quyền quản trị phải được kiểm soát và có audit**, vì quyền quá rộng có thể làm lộ dữ liệu hoặc ảnh hưởng tính toàn vẹn đơn hàng.

Trong bài kiểm toán có kiểm soát, nhóm assurance xác định:

- **2026-11-01 10:00 UTC:** một service principal có thể tự gán quyền admin thông qua một IAM path ngoài workflow phê duyệt.
- Kịch bản có khả năng khai thác trên production; không có bằng chứng cho thấy đã có hành vi lạm dụng tại thời điểm triage, nhưng đó không chứng minh rủi ro bằng 0.
- Policy minh họa phân loại **P1**, yêu cầu containment trong **4 giờ**, verified closure trong **7 ngày liên tục** kể từ clock start.
- Root cause: IaC role binding thiếu điều kiện giới hạn principal và workflow không bao phủ delegated path.

Deadline cụ thể:

- **Containment target:** 2026-11-01 14:00 UTC.
- **Original verified closure deadline:** 2026-11-08 10:00 UTC.

### 13.2. Remediation plan

| Giai đoạn | Hành động | Ngày/giờ thực tế giả định | Evidence |
|---|---|---|---|
| **Validation** | Xác nhận role path, affected accounts, rule và người thực thi. | 01/11 10:30 UTC | IAM inventory, access analysis, approved test. |
| **Containment** | Giới hạn trust policy và chặn quyền tự gán ở đường có nguy cơ. | 01/11 12:00 UTC | Config snapshot, negative access test. |
| **Root cause fix** | Sửa IaC, bắt approval với delegated path và code review. | 04/11 15:00 UTC | Commit, review, CI test, design note. |
| **Deploy** | Canary ở account thử, sau đó cả hai production accounts. | 07/11 16:00 UTC | Change records, deployed policy IDs. |
| **Retest lần 1** | Kiểm tra cấp quyền qua user, service principal, automation. | 08/11 09:00 UTC | Một đường tự gán vẫn thành công → FAIL. |
| **Fix bổ sung** | Loại rule ngoại lệ cũ trên account thứ hai. | 08/11 13:00 UTC | IAM policy diff, change log. |
| **Retest lần 2** | Negative/positive tests đều đạt, audit đủ event. | 08/11 15:00 UTC | Raw IAM logs, test suite, reviewer signoff. |

### 13.3. Phân tích deadline

- **Containment:** hoàn thành lúc 12:00, trước hạn 14:00 → đạt mục tiêu containment, với điều kiện test chứng minh đường nguy hiểm đã bị chặn tạm thời.
- **Implementation ban đầu:** 07/11 16:00, trước deadline 08/11 10:00.
- **Verified closure:** 08/11 15:00, **quá hạn 5 giờ** theo policy mẫu.
- **Kết luận:** finding đạt verified remediation **muộn**, không thể đánh dấu “on time” chỉ vì deployment đầu tiên hoàn thành trước hạn.
- **Risk:** xem xét khoảng thời gian đường bypass còn tồn tại, audit toàn kỳ và các hoạt động liên quan để xác định tác động, không kết luận có hoặc không có compromise chỉ từ test.

### 13.4. Assurance traceability

~~~mermaid
flowchart LR
    R["Threat: unauthorized admin privilege"] --> C["Control: approval + least privilege"]
    C --> F["Finding: delegated IAM path bypass"]
    F --> D["Deadline: containment + verified closure"]
    D --> A["Patch IaC + enforce delegated approval"]
    A --> T["Negative and positive IAM tests"]
    T --> E["Evidence: config, event, reviewer"]
    E --> V["Verified late; breach retained"]
~~~

### 13.5. Bài học từ tình huống

1. Phạm vi phải gồm **tất cả delegated paths**, không chỉ giao diện IAM chính.
2. Một bản sửa được deploy không có nghĩa remediation đã hoàn tất.
3. Containment và root-cause remediation là hai kết quả có clock khác nhau.
4. Kiểm thử fail gần deadline cần buffer cho sửa và retest; phải được xem trong dự báo at-risk.
5. Retest pass muộn cần được ghi muộn dù cuối cùng finding đã khắc phục.
6. Nếu cùng lỗi có ở nhiều accounts, không được đóng khi chỉ một account pass.

## 14. Các tình huống deadline khó khác

### 14.1. Secret lộ và có thể đang bị dùng

**Finding:** token có quyền truy cập dữ liệu nhạy cảm bị đưa vào repository public.

Thứ tự ưu tiên có thể là:

1. Xác minh token còn hiệu lực và quyền thực tế; nếu nghi vấn lộ nghiêm trọng, **contain/revoke nhanh** theo quyền và IR.
2. Tạo credential thay thế ở nơi an toàn, tránh gây outage không kiểm soát.
3. Đánh giá access logs và mức độ sử dụng trong thời gian token có thể bị lộ.
4. Xóa secret khỏi luồng build/config và ngăn tái xuất hiện bằng policy/scanning.
5. Kiểm tra token cũ không còn dùng được; token mới có least privilege, rotation và audit.
6. Không coi việc **xóa dòng secret khỏi Git history hiển thị** là đủ nếu credential cũ vẫn có hiệu lực.
7. Khi có incident, phối hợp forensic/evidence preservation và legal/compliance theo nghĩa vụ.

**Deadline:** có thể cần containment ngắn hơn nhiều so với patch release thông thường; cụ thể phải theo policy/IR và threat context. Nếu token đã bị lạm dụng, đây không chỉ là backlog remediation.

### 14.2. Vulnerability phụ thuộc vendor không có patch

**Finding:** một dependency có lỗ hổng trong thành phần legacy, upstream chưa phát hành bản sửa.

Lựa chọn:

- Xác minh reachability, version, affected feature và threat intelligence.
- Disable vulnerable feature hoặc áp segmentation/WAF policy nếu phù hợp và đã test.
- Có roadmap thay thế/vá/chuyển nền tảng; không ghi “waiting for vendor” vô thời hạn.
- Tài liệu hóa vendor ticket, status, phương án thay và giám sát.
- Risk owner xử lý ngoại lệ/extension theo thẩm quyền; legal review nếu có nghĩa vụ.
- Đặt **milestone tạm thời, review date và expiry** kể cả khi không có patch.
- Sau khi có patch, kiểm thử regression và xác minh đúng toàn population.

Một compensating control có thể giảm rủi ro nhưng không tự loại vulnerability khỏi finding nếu root cause vẫn tồn tại.

### 14.3. Logging/detection source lỗi

**Finding:** security audit từ cloud account quan trọng không vào SIEM trong 12 giờ.

- **Containment/mitigation:** phục hồi source/pipeline, tăng monitoring và kiểm tra các đường audit còn lại.
- **Impact analysis:** xác định những khoảng thời gian không quan sát được, các hành vi nào có thể bị bỏ qua, liệu raw source còn phục hồi được không.
- **Root-cause fix:** sửa configuration/IaC, connector permissions, parser và source heartbeat alerting.
- **Verification:** tạo synthetic event có kiểm soát, xác nhận raw source → ingest → detection → alert/case, test mất nguồn.
- **Closure:** không tuyên bố 12 giờ quá khứ đã được bảo đảm chỉ vì logging đã hoạt động trở lại.

Deadline nên phản ánh mức phơi nhiễm của blind spot, threat scenario và nghĩa vụ; **việc bật connector** chưa là bằng chứng detection effectiveness.

### 14.4. Disaster recovery test không đạt

**Finding:** restore thử không giải mã được bản backup, có nguy cơ không đạt RTO/RPO đã phê duyệt.

- Risk owner xem mức ảnh hưởng theo BIA, dữ liệu, criticality và phương án recovery khác.
- Có thể cần mitigation nhanh: kiểm tra key access, bản backup dự phòng, giảm shared failure domain.
- Root-cause fix: key policy, replication, backup/restore automation, tài liệu runbook.
- Evidence closure: restore đầy đủ với dữ liệu đại diện, validation nghiệp vụ và thời gian thực.
- Một ticket "backup job green" không đủ đóng finding không giải mã được.

Nếu tổ chức có cam kết khôi phục với khách hàng, cần xem cả nghĩa vụ hợp đồng và xử lý escalation phù hợp.

### 14.5. Phát hiện ở third party

**Finding:** SaaS hỗ trợ khách hàng có access control gap nhưng đội nội bộ không thể trực tiếp sửa nền tảng vendor.

- Ghi rõ **vendor action owner** và **customer risk owner**.
- Yêu cầu vendor plan, mốc containment, khắc phục, test và evidence.
- Xem xét giảm scope dữ liệu/quyền, tạm ngắt integration, dùng proxy hoặc dịch vụ thay thế.
- Quản lý deadlines theo hợp đồng và chính sách nội bộ, giữ lịch sử vendor communication.
- Không đánh dấu resolved chỉ vì vendor gửi email “fixed” nếu assurance yêu cầu evidence có độ tin cậy cao hơn.
- Nếu vendor không đáp ứng, escalation tới procurement/legal/business owner và đánh giá exit.

## 15. Quản trị deadline khi sự cố và compliance chồng lấn

### 15.1. Phân biệt remediation ticket và incident response

Một vulnerability có thể nằm trong backlog nhiều tuần, nhưng nếu có hành vi khai thác thực tế, workflow phải phối hợp với incident response:

- IR tập trung **detect, contain, eradicate, recover, preserve evidence, communicate**.
- Remediation tập trung **giải quyết root cause hoặc control gap**, phòng ngừa tái diễn và xác minh hiệu lực.
- Một incident có thể sinh nhiều findings, mỗi finding có owner và deadlines riêng.
- IR timeline không tự thay cho remediation SLA; hai loại hồ sơ cần có liên kết.

Khi incident commander đã cô lập hệ thống, vẫn cần xác nhận **điều kiện nào cần sửa để mở lại dịch vụ an toàn**. Nếu không, tổ chức có thể “recover” vào cùng cấu hình lỗi.

### 15.2. Nghĩa vụ bên ngoài và risk acceptance

Một tổ chức có thể chấp nhận **rủi ro kỹ thuật nội bộ** trong thẩm quyền phù hợp, nhưng không thể dùng quyết định đó để tự miễn một yêu cầu pháp lý đang áp dụng.

Nếu finding liên quan thông báo sự cố, dữ liệu cá nhân, hồ sơ phải lưu hoặc điều khoản hợp đồng, cần:

1. Xác định nguồn nghĩa vụ và điều kiện áp dụng.
2. Tách deadline **thông báo/khắc phục/chứng minh** nếu chúng khác nhau.
3. Giao legal/compliance xác nhận cách tính và thẩm quyền.
4. Lưu tất cả mốc sự kiện, nội dung thông báo và quyết định.
5. Báo cáo trạng thái remediation và trạng thái compliance **riêng** khi cần.

### 15.3. Việc sửa có thể tạo rủi ro mới

Một bản patch gấp có thể làm gián đoạn thanh toán, gây mất tính nhất quán dữ liệu hoặc ảnh hưởng business continuity. Cần chọn biện pháp theo rủi ro tổng thể:

- Có canary/staging và rollback được kiểm chứng?
- Có thể giảm exposure ngay bằng segmentation, permission reduction hoặc feature disable?
- Có change window và thông tin khách hàng liên quan?
- Có backup/restore, dữ liệu và kiểm thử nghiệp vụ đủ sẵn sàng?
- Nếu rollout fail, incident/BC/DR plan đã được chuẩn bị?

**Hạn khắc phục không có nghĩa phải thực hiện thay đổi nguy hiểm không kiểm soát**. Nó tạo nhu cầu ra quyết định rõ ràng và đúng thẩm quyền về cách giảm rủi ro.

## 16. Chương trình assurance liên tục cho remediation deadlines

### 16.1. Chuỗi truy vết

~~~mermaid
flowchart TD
    REQ["Security requirement / risk"] --> CTRL["Control & criterion"]
    CTRL --> DET["Audit / test / incident finding"]
    DET --> TRI["Risk triage and deadline contract"]
    TRI --> ACT["Remediation, containment, owner"]
    ACT --> TEST["Verification / retest"]
    TEST --> EVID["Evidence + reviewer"]
    EVID --> DEC{"Criterion met?"}
    DEC -->|Đạt| CLOSE["Verified closure, SLA result"]
    DEC -->|Chưa đạt| GAP["Finding still open + escalation"]
    GAP --> ACT
    TRI --> MON["Deadline monitoring and exceptions"]
    MON --> GAP
    CLOSE --> DRIFT["Monitor recurrence and change"]
    DRIFT --> REQ
~~~

### 16.2. Controls cần có cho chính quy trình remediation

| Control objective | Control/process | Test assurance | Evidence |
|---|---|---|---|
| Không bỏ sót finding ưu tiên cao. | Intake từ scanner, audit, incident, vendor, bug bounty và GRC. | Cross-source reconciliation và sampling. | Source inventory, ticket IDs, dedupe logic. |
| Hạn được gắn theo rủi ro. | Severity/priority rules và deadline contract. | Test nhiều risk scenarios với policy version. | Risk assessment, decisions, time fields. |
| Không bỏ ticket không owner. | Mandatory owner và escalation. | Tạo finding thiếu owner trong sandbox/test data. | Workflow tests và alert/case. |
| Hạn không bị dời âm thầm. | Immutable history hoặc audit trail cho changes. | Simulate revision không được duyệt. | Before/after values, approval và rejection. |
| Items gần quá hạn được xử lý. | Due-soon và at-risk alerts. | Test notification và routing tới người chịu trách nhiệm. | Alert timeline, on-call/owner response. |
| Ngoại lệ không tồn tại vô hạn. | Exception expiry và re-review. | Test exception expired. | Exception register, alert, decision. |
| Không đóng khi chưa sửa. | Verification gate và required evidence. | Thử close ticket khi retest fail/thiếu. | Workflow rule test và audit. |
| Không mất lịch sử breach. | Original due & revision history. | Close-late/reopen cases. | Historical snapshots, query tests. |
| Báo cáo không thiên lệch. | Cohort due-date và open backlog cùng được tính. | Test denominator với open overdue. | Metric contract, raw cohort, calculation. |
| Không tái phát. | Regression tests, policy as code và post-close monitoring. | Drift/reopen simulation theo scope. | CI/CD, runtime checks, recurrence records. |

### 16.3. Tiêu chí đánh giá chất lượng chương trình

Một chương trình tốt phải chứng minh:

- Findings từ các nguồn trọng yếu được nhận diện và gắn risk/owner.
- Deadline phù hợp nguồn nghĩa vụ, risk tier và thời điểm áp dụng.
- Clock được tính chính xác và không thay do thao tác ticket.
- Những rủi ro sắp/đã quá hạn được escalation tới đúng cấp.
- Compensating controls có evidence và expiry.
- Không có **verified closure giả** dựa trên ticket Done hoặc lời xác nhận.
- Metrics báo cả **open overdue** và các mục hoàn tất trễ.
- Retest thật sự xác nhận mức kiểm soát yêu cầu.
- Những failures lặp lại dẫn tới sửa design/process và đánh giá risk mới.

## 17. Những sai lầm thường gặp

1. **Đặt deadline từ severity duy nhất.** CVSS/nhãn scanner không thay thế exposure, exploitability, business impact và nghĩa vụ áp dụng.
2. **Dùng cùng SLA cho mọi finding.** Một secret lộ và một hardening recommendation có tính khẩn cấp khác nhau.
3. **Làm mới đồng hồ khi chuyển ticket.** Đổi owner/tool không làm biến mất thời gian đã phơi nhiễm.
4. **Tính hạn từ triage khi policy bắt đầu từ detection.** Làm sai kết quả và có thể bỏ thời gian phản ứng quan trọng.
5. **Lẫn ngày làm việc và ngày lịch.** "7 ngày" có thể ra kết quả khác nhau nếu không có rule và timezone rõ.
6. **Đánh dấu Done khi pull request merge.** Chưa deploy, retest hoặc xem population.
7. **Coi containment là khắc phục tận gốc.** Biện pháp tạm có thể mất hiệu lực hoặc bị deploy ghi đè.
8. **Cho rằng scanner sạch là bằng chứng đủ.** Scanner có thể mất visibility hoặc chưa kiểm tra các đường tấn công liên quan.
9. **Che breach bằng extension.** Giữ original deadline và lịch sử phê duyệt.
10. **Coi giấy ngoại lệ là compliant.** Risk acceptance không chứng minh control đã khắc phục, không tự miễn nghĩa vụ bên ngoài.
11. **Đợi quá hạn mới escalation.** Dự báo at-risk và đặt lịch retest trước deadline.
12. **Đếm on-time trên những mục đã đóng.** Bỏ các finding mở quá hạn khiến KPI lệch.
13. **Xóa false positive không có evidence.** Làm mất tính truy vết của data quality và audit.
14. **Dùng trung bình che đuôi dài.** Một số rủi ro Critical có thể tồn tại rất lâu dù mean thấp.
15. **Không test lại khi fix có thể gây regression.** Retest phải gồm đường bypass, boundary và production behavior phù hợp.
16. **Phân rã ticket để tránh quá hạn.** Parent finding/risk phải giữ lịch sử và coverage.
17. **Coi vendor ticket là remediation.** Vendor plan chưa chứng minh outcome của khách hàng được bảo vệ.
18. **Không tính delay do verification.** Nếu verified closure là tiêu chí, retest phải nằm trong kế hoạch thời gian.
19. **Đổi severity cuối kỳ để làm đẹp báo cáo.** Reclassification cần nguồn và audit trail.
20. **Không ghi residual risk khi đóng finding.** Một fix có thể đạt criterion nhưng vẫn còn attack paths ngoài scope cần quản trị riêng.

## 18. Bài tập tình huống: quyết định và báo cáo deadline

### 18.1. Dữ liệu giả định

Tổ chức có bốn findings trong tháng 11/2026; policy giả định:

- P1: verified closure trong **7 × 24 giờ**.
- P2: verified closure trong **30 × 24 giờ**.
- P3: verified closure trong **60 × 24 giờ**.
- Containment và IR targets là chỉ tiêu riêng.
- Thời gian tính từ clock_start_at, được lưu UTC.

| ID | Mức | Clock start | Deadline theo policy | Diễn biến |
|---|---|---|---|---|
| **F-101** | P1 | 01/11 10:00 | 08/11 10:00 | Fix deploy 07/11 18:00; test pass 08/11 09:30. |
| **F-102** | P1 | 01/11 10:00 | 08/11 10:00 | Fix deploy 07/11 17:00; test fail 08/11 09:00; retest pass 08/11 15:00. |
| **F-103** | P2 | 03/11 08:00 | 03/12 08:00 | Vendor chưa cung cấp patch; có tường lửa bù trừ nhưng chưa test đầy đủ. |
| **F-104** | P3 | 05/11 12:00 | 04/01/2027 12:00 | Không còn affected asset do dịch vụ đã decommission, cần xác minh thực tế. |

### 18.2. Câu hỏi

1. Với tiêu chí verified closure, F-101 và F-102 đạt hạn hay không?
2. F-103 có thể được đóng khi vendor gửi email "patch scheduled" không? Vì sao?
3. Với F-103, cần những tài liệu nào nếu business owner đề xuất gia hạn?
4. F-104 cần bằng chứng gì trước khi kết luận resolved by verified removal?
5. Nếu 10 findings đến hạn tháng 11 có 6 verified on time, 2 verified late, 2 còn mở quá hạn, on-time rate nên tính thế nào?
6. Hãy xác định ba alert cần có để phát hiện finding **at risk** trước deadline.
7. Nếu team chuyển F-102 sang ticket mới ngày 07/11, có nên cho clock bắt đầu lại không?
8. Một threat scenario thay đổi khiến F-103 trở thành P1; cần xử lý deadline và audit trail thế nào?
9. Viết điều kiện nghiệm thu cho remediation về IAM privilege escalation hoặc log-source outage.
10. Soạn một executive summary nêu critical overdue, verified late, exception status, risk impact và owner.

### 18.3. Gợi ý đáp án

- **F-101:** verified 08/11 09:30, trước hạn 10:00 → **on time**, nếu evidence và reviewer phù hợp.
- **F-102:** verified 08/11 15:00 → **late 5 giờ**; deploy sớm không thay trạng thái.
- **F-103:** **open**, vì kế hoạch vendor và firewall chưa được kiểm chứng không đủ để đóng; cần kế hoạch khắc phục, compensating control tests, owner, risk decision, expiry và deadlines có căn cứ.
- **F-104:** chỉ resolved theo decommission khi inventory, DNS/network routes, IAM/keys, data/backup dependencies và sự vắng mặt của asset trong scope đã được xác minh; không suy từ việc CMDB thiếu record.
- **On-time rate:** 6/10 = **60%** đối với cohort deadline gốc. Hai mục còn mở đã quá hạn phải ở mẫu số, không được bỏ.
- **Reclassification:** giữ priority và deadline cũ trong lịch sử; tạo quyết định mới với lý do, ngày hiệu lực và deadline/IR actions tương ứng policy; không âm thầm dùng severity mới để xóa breach trước đó.

## 19. Checklist quản lý Remediation deadline

- [ ] Finding có ID ổn định, nguồn, security requirement/control, affected assets và business owner.
- [ ] Phạm vi, điều kiện quan sát, khả năng khai thác và tác động được đánh giá, không dựa riêng một điểm scanner.
- [ ] Policy/hợp đồng/nghĩa vụ tạo deadline được ghi với phiên bản và điều kiện áp dụng.
- [ ] Clock start, deadline, timezone, duration type và completion criterion được định nghĩa.
- [ ] Tách mục tiêu triage, containment, mitigation, implementation, retest và verified closure nếu cần.
- [ ] Original deadline và current approved deadline đều được giữ.
- [ ] Severity/priority history và deadline revisions có approval, rationale và timestamps.
- [ ] Action plan có root cause, containment, rollout, owner, dependencies và acceptance tests.
- [ ] Có buffer thời gian cho retest và khả năng test fail.
- [ ] Controls tạm thời có evidence, người giám sát, điều kiện hết hiệu lực và kế hoạch thay thế.
- [ ] Nếu không đáp ứng hạn, escalation được thực hiện trước hoặc ngay khi cần theo rủi ro.
- [ ] Risk acceptance/exception chỉ được áp dụng trong thẩm quyền, có phạm vi và expiry; không xóa finding chưa sửa.
- [ ] Các nghĩa vụ bên ngoài được legal/compliance xem xét khi có chồng lấn.
- [ ] Tiến độ và blockers được cập nhật; có cảnh báo at risk, due soon và overdue.
- [ ] Verification xác minh đúng toàn population, không chỉ CI PASS hoặc một asset.
- [ ] Finding chỉ VERIFIED_CLOSED khi đạt criteria, evidence đủ và reviewer xác nhận.
- [ ] Retest fail hoặc thiếu telemetry không bị coi là completed.
- [ ] False positive, decommission, accepted risk và verified fix có trạng thái phân biệt.
- [ ] Báo cáo on-time dùng cohort deadline nhất quán và có open overdue trong mẫu số.
- [ ] Có dashboard overdue count/age, original breach history, risk tier, owner và business service.
- [ ] Data pipeline kiểm tra timestamp, timezone, duplicate, missing owner, revision và reopen.
- [ ] Báo cáo nêu rõ limitations, gaps, residual risk, pending verification và exceptions.
- [ ] Findings tái phát được liên kết với root cause, regression tests và bài học vận hành.
- [ ] Reviewer độc lập có thể truy từ claim đúng hạn tới timeline, evidence và quyết định.
- [ ] Kết quả được tái đánh giá khi control, tài sản, threat hoặc nghĩa vụ thay đổi.

## 20. Câu hỏi tự đánh giá

1. Remediation deadline khác containment deadline và verification deadline ở điểm nào?
2. Vì sao một vulnerability có CVSS cao không mặc nhiên có cùng deadline trên mọi hệ thống?
3. Có thể dùng thời điểm ticket tạo làm clock start nếu policy quy định bắt đầu từ phát hiện không?
4. Điều gì xảy ra khi bản sửa deploy trước hạn nhưng retest pass sau hạn?
5. Tại sao phải lưu đồng thời original deadline và approved current deadline?
6. Risk acceptance có thể tự miễn một deadline pháp lý hoặc biến finding đang mở thành verified closed không?
7. Khi dùng 7 ngày lịch, timezone và time-of-day ảnh hưởng kết quả ra sao?
8. Vì sao “waiting for vendor” không phải lý do để dừng quản trị một risk Critical?
9. Một security logging source được bật trở lại có khôi phục được bằng chứng đã mất trong 12 giờ trước không?
10. Khi nào một finding được resolved by verified decommission thay vì repaired?
11. Vì sao tỷ lệ đúng hạn dựa trên findings đã đóng có thể đánh giá sai backlog quá hạn?
12. Một service owner đóng ticket sau khi sửa nhưng không có negative test; reviewer cần làm gì?
13. Những control nào giúp phát hiện việc dời deadline không được phê duyệt trong ticketing system?
14. Hãy mô tả một compensating control có thể kiểm chứng cho hệ thống legacy chưa có patch.
15. Nếu severity thay đổi từ P2 sang P1, cần giữ những mốc và quyết định nào?
16. Hãy thiết kế một dashboard có on-time closure, overdue backlog, deadline revision, verification lag và exception expiry.
17. Với một phát hiện IAM bypass, viết hai acceptance criteria: một cho containment và một cho root-cause remediation.
18. Hãy dựng một assurance case ngắn giải thích tại sao finding đã khắc phục đúng hạn, gồm claim, timeline, evidence, reviewer và limitations.

**Điểm cốt lõi:** **Remediation deadline là cam kết giảm rủi ro được đo bằng sự kiện, thời gian và kết quả có thể kiểm chứng**. Một ngày đến hạn chỉ có ý nghĩa khi biết bắt đầu từ đâu, áp dụng theo nguồn nào, yêu cầu hoàn thành điều gì và bằng chứng xác nhận ra sao. Trong security assurance, phải **giữ nguyên lịch sử hạn gốc, tách containment khỏi verified remediation, công bố findings quá hạn và ngoại lệ, thử nghiệm lại kết quả** để không biến quản lý rủi ro thành việc dời ngày trên ticket.
