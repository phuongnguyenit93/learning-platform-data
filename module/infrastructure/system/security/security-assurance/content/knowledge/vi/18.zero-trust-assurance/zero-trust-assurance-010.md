# Đo lường Zero Trust (Zero Trust Measurement) trong Security Assurance

## 1. Vấn đề: có Zero Trust controls chưa chắc có Zero Trust assurance

Một nền tảng SaaS quản lý hóa đơn tuyên bố đã áp dụng Zero Trust vì nhân viên dùng MFA, máy tính có EDR, API triển khai sau gateway và các dịch vụ nội bộ kết nối bằng mTLS. Bảng điều khiển còn báo “95% Zero Trust maturity”. Tuy nhiên, một background worker vẫn dùng tài khoản dịch vụ có thể đọc hóa đơn của mọi tenant, một API export không kiểm tra lại quyền sau khi tạo job, và đội vận hành không biết có bao nhiêu kết nối nội bộ không đi qua policy enforcement.

Vấn đề không chỉ là hệ thống đã **cài đặt những sản phẩm nào**, mà là có thể chứng minh các nguyên tắc Zero Trust **đang được thực thi trên những tài sản, danh tính, phiên, hành động và luồng dữ liệu quan trọng hay không**.

**Đo lường Zero Trust** là quá trình định nghĩa, thu thập, kiểm tra và diễn giải các thước đo về **phạm vi bao phủ (coverage), hiệu lực (effectiveness), độ tin cậy của bằng chứng (evidence quality), thời gian phản ứng (responsiveness), độ trưởng thành (maturity) và rủi ro còn lại (residual risk)** của các biện pháp Zero Trust. Đầu ra phải giúp chủ sở hữu hệ thống quyết định cần cải thiện điều gì, không chỉ cung cấp một điểm số đẹp.

Trong module **SECURITY_SECURITY_ASSURANCE**, đo lường là một phần của chương trình đánh giá có bằng chứng: đi từ phân tích rủi ro và yêu cầu bảo mật, đến thiết kế controls, kiểm thử, audit, phát hiện thiếu sót, khắc phục và đánh giá lại liên tục.

Chuỗi lập luận xuyên suốt bài:

**Protected resources → threat scenarios → Zero Trust requirements → controls/decision points → observable behavior → metrics/tests/evidence → assurance conclusion → corrective actions.**

> **Không có công thức phổ quát nào biến số lượng MFA, EDR, mTLS và micro-segmentation thành bằng chứng hệ thống đã “đạt Zero Trust”.** Mọi kết luận phải ghi rõ phạm vi, mẫu số, phương pháp, thời kỳ, nguồn dữ liệu và các phần chưa được quan sát.

## 2. Zero Trust là chiến lược kiến trúc, không phải một sản phẩm

Zero Trust chủ trương **không cấp sự tin cậy mặc nhiên chỉ vì vị trí mạng hoặc quan hệ nội bộ**, mà đánh giá quyền truy cập theo danh tính, tài nguyên, hành động, ngữ cảnh và chính sách; thực thi tại các điểm phù hợp, đồng thời liên tục theo dõi thay đổi và điều chỉnh khi cần. Các thiết kế thường áp dụng xác minh rõ ràng, quyền tối thiểu và giả định rằng một thành phần có thể đã bị xâm nhập.

Trong các mô hình Zero Trust Architecture như NIST SP 800-207, có thể phân biệt **policy decision** và **policy enforcement**. Cách tổ chức cụ thể tùy sản phẩm, nhưng ý chính là yêu cầu truy cập phải được đánh giá và quyết định được thực thi tại nơi thực sự kiểm soát tài nguyên.

### Ba nguyên tắc chuyển thành phép đo

| Nguyên tắc | Câu hỏi đo lường | Bằng chứng cần thiết |
| --- | --- | --- |
| **Verify explicitly** | Bao nhiêu yêu cầu truy cập trong scope được đánh giá với các tín hiệu xác minh phù hợp trước khi cấp quyền? | PDP/PEP decision records, credential/device/risk signal freshness, negative tests. |
| **Least privilege** | Những identity nào có quyền vượt nhu cầu và có thực thi trên từng resource/action không? | Effective permissions, policy reviews, resource-level denied-use tests, time-bounded grants. |
| **Assume breach / limit blast radius** | Nếu user, máy hoặc workload bị chiếm, có thể truy cập rộng đến đâu và hệ thống phát hiện/giới hạn trong bao lâu? | Attack-path tests, segmentation validation, revocation drills, containment evidence. |

**Zero Trust không đồng nghĩa luôn xác thực lại bằng mật khẩu hoặc MFA ở mọi packet.** Chính sách có thể sử dụng session, token, attested workload identity và dữ liệu ngữ cảnh theo thời gian. Điều cần đo là **cơ chế có kiểm tra đúng điều kiện ở đúng điểm, trong thời hạn rủi ro cho phép** hay không.

## 3. Phân biệt maturity, implementation, effectiveness và outcome

Đây là bốn lớp đo lường khác nhau:

| Lớp | Ví dụ câu hỏi | Ví dụ chỉ số | Điều chưa được chứng minh |
| --- | --- | --- | --- |
| **Maturity** | Tổ chức đã có năng lực, quy trình và automation ở mức nào? | Tỷ lệ domains có owner, policy-as-code và review định kỳ. | Mọi quyền truy cập thực đều được kiểm soát. |
| **Implementation/coverage** | Control đã được triển khai cho bao nhiêu thực thể trong scope? | Tỷ lệ applications có PEP bắt buộc. | PEP không bị bypass và quyết định chính xác. |
| **Control effectiveness** | Control thực sự cho phép/khước từ đúng theo yêu cầu? | Tỷ lệ negative authorization tests đạt. | Chặn được mọi attack path chưa thử. |
| **Security outcome** | Rủi ro, blast radius và thời gian phát hiện/thu hồi có giảm? | Verified lateral movement paths bị chặn, thời gian revoke có thực đo. | Không còn sự cố hay rủi ro bên ngoài scope. |

Đừng gọi một sản phẩm có chức năng “continuous access evaluation” là bằng chứng thời gian thu hồi đã đạt; cần đo **từ lúc signal thay đổi tới khi quyền không còn sử dụng được trong các đường truy cập thuộc scope**.

### Leading và lagging indicators

- **Leading indicators:** tỷ lệ policy coverage, posture freshness, privileged access expiry, số đường không có PEP, test coverage, telemetry health.
- **Lagging indicators:** confirmed unauthorized access, time-to-containment sau sự cố, kết quả purple-team, số lần policy failure gây impact.

Số incident bằng 0 có thể do không có incident, nhưng cũng có thể vì không phát hiện được. Chỉ số dẫn dắt và kết quả cần được **kiểm tra chéo**, không dùng một loại thay loại kia.

## 4. Đơn vị đo: đang quan sát điều gì?

Các phép đo Zero Trust có thể nói về các đơn vị khác nhau:

| Đơn vị | Ví dụ | Sai lầm thường gặp |
| --- | --- | --- |
| **Identity** | Nhân viên, admin, service principal, workload identity. | Đếm nhân viên nhưng bỏ identities máy hoặc tài khoản đặc quyền. |
| **Device** | Laptop, mobile, server, container host. | Dùng mẫu số chỉ là thiết bị đã đăng ký, bỏ unmanaged endpoints. |
| **Resource** | App, API, endpoint, record, bucket, dataset. | Đếm application mà bỏ endpoint admin/export. |
| **Access request/decision** | User X muốn READ invoice Y ở thời điểm T. | Đếm lần login như số lần mọi hành động được authorize. |
| **Session/token/grant** | Phiên, token, quyền tạm hoặc capability URL. | Không đo quyền sau khi token bị thu hồi. |
| **Flow/edge** | Workload A → Service B qua port/protocol. | Đếm VPC thay cho thực tế các luồng được kiểm soát. |
| **Control path** | PEP, PDP, context provider, IAM, policy store. | Đếm có PEP mà không kiểm tra đường bypass. |
| **Test scenario** | Cross-tenant access, compromised device, wrong audience. | Tỷ lệ PASS cao nhưng test cases không đại diện threat. |
| **Incident/finding** | Authorization failure, policy drift hoặc data exposure. | Đóng ticket được coi là hiệu lực đã phục hồi. |

**Không cộng trực tiếp những đơn vị này thành một tỷ lệ.** Ví dụ 90% devices compliant và 98% apps có SSO không có nghĩa 94% Zero Trust effectiveness.

## 5. Kiến trúc đo lường: PDP, PEP, policy signals và evidence

Trong mô hình kiến trúc minh họa, **Policy Decision Point (PDP)** đánh giá yêu cầu truy cập dựa trên policies và tín hiệu; **Policy Enforcement Point (PEP)** thực thi allow/deny trên đường tới tài nguyên. Một số triển khai tách policy engine, policy administrator và điểm thực thi; tên gọi và phân chia có thể khác tùy nền tảng.

~~~mermaid
flowchart LR
    ACT["User / workload"] -->|"Request resource and action"| PEP["Policy Enforcement Point"]
    PEP -->|"Decision request"| PDP["Policy Decision Point"]
    IDP["Identity and authentication"] --> PDP
    DEV["Device posture and health"] --> PDP
    RISK["Risk and threat signals"] --> PDP
    POLICY["Versioned policies"] --> PDP
    PDP -->|"Allow / deny / step-up / constraints"| PEP
    PEP -->|"Allowed requests only"| RES[("Protected resource")]
    PEP --> EVT["Decision and enforcement telemetry"]
    PDP --> EVT
    RES --> EVT
    EVT --> PIPE["Correlate, validate, measure"]
    PIPE --> DASH["Assurance metrics and findings"]
~~~

### Những điều phải xác minh ở mỗi lớp

**PDP:** có policy đúng version, nhận tín hiệu đúng principal/resource/action, xử lý unknown/stale signals đúng yêu cầu và trả quyết định có khả năng giải thích/kiểm tra không?

**PEP:** có bao phủ cả API, data layer, background job, download, admin path, service-to-service flow không? Có thực hiện đúng decision và constraints không? Có đường trực tiếp tới tài nguyên bỏ qua PEP không?

**Signal providers:** device compliance, identity risk, token status và resource classification có cập nhật đúng thời hạn không? Có thể bị giả mạo hoặc thiếu không?

**Evidence pipeline:** bản ghi có chứa ID kết nối PDP decision, PEP enforcement và resource outcome không? Mất log, duplicate, clock skew hoặc sampling làm sai mẫu số tới mức nào?

### Đừng suy từ PDP allow rằng truy cập đã thành công

PDP có thể trả allow nhưng PEP thất bại, network lỗi hoặc ứng dụng từ chối vì điều kiện nghiệp vụ. Tương tự, PDP deny không tự chứng minh mọi đường đến tài nguyên đã bị chặn nếu có bypass. Cần **correlation của quyết định và enforcement outcome**.

## 6. Phạm vi đo lường và bài toán mẫu số

**Mẫu số là một phần của lời tuyên bố bảo mật.** Một tỷ lệ cao vô nghĩa nếu tổ chức không biết mình đã loại bỏ những gì.

### Cần định nghĩa scope trước

1. Business services, tenant tiers và data classifications.
2. Environments: production, pre-production, DR, analytics và support.
3. User populations: employees, contractors, customers, administrators, partners.
4. Non-human identities: service accounts, CI/CD runners, cloud workloads, bots.
5. Devices: managed, unmanaged, shared, BYOD và ephemeral.
6. Resources: apps, APIs, queues, databases, storage, exports và logs.
7. Network flows: ingress, east-west, egress, cross-region, vendor.
8. Thời kỳ đánh giá và những thay đổi cấu hình trong thời kỳ đó.
9. Exclusions có lý do, owner, expiry và risk acceptance nếu áp dụng.

### Hai mẫu số dễ bị nhầm

**Registered device coverage = managed compliant devices / enrolled devices** có thể cao dù nhiều thiết bị không được đăng ký vẫn truy cập SaaS. Đây chỉ là **tỷ lệ tuân thủ trong tập enrolled**.

**Protected resource device-policy coverage = access paths to protected resources requiring applicable device evaluation / all eligible access paths to those resources** trả lời câu hỏi liên quan chính sách Zero Trust hơn. Nhưng để dùng mẫu số thứ hai, phải có **asset/route inventory** đủ tin cậy và test đường bypass.

### Vấn đề “unknown unknowns”

Không thể tính toàn bộ đường truy cập bằng chỉ những đường đã biết trong một danh mục thiếu cập nhật. Kết hợp cloud discovery, configuration inventory, service catalogs, network flow analysis, API inventories, vulnerability/attack-path reviews và owner validation. Ghi **estimated inventory completeness** hoặc **unmapped flows count**, không biến thiếu dữ liệu thành mẫu số bằng 0.

## 7. Measurement specification: mọi KPI phải có hợp đồng dữ liệu

Mỗi metric nên có một bản mô tả **để hai nhóm độc lập tính được gần cùng một kết quả trên cùng nguồn**.

| Thành phần | Nội dung bắt buộc |
| --- | --- |
| **Metric ID/name** | Định danh, mục tiêu bảo mật và đơn vị đo. |
| **Population/denominator** | Tập thực thể, kỳ, điều kiện eligible và exclusions. |
| **Numerator** | Điều kiện nào được tính là đạt. |
| **Formula/aggregation** | Tỷ lệ, phân vị, thời gian, số lượng hoặc weighted metric. |
| **Source** | Inventory, PDP/PEP events, IAM, EDR, SIEM, tests. |
| **Data quality** | Completeness, freshness, deduplication, correlation, clock skew. |
| **Target/threshold** | Ngưỡng do risk owner/standard quyết định; không tự đặt toàn cục. |
| **Segment** | Tenant, resource sensitivity, user/admin, workload, region, environment. |
| **Frequency/window** | Mỗi phiên, hàng giờ, ngày, tháng, theo release hoặc event. |
| **Owner** | Người đảm bảo dữ liệu, người dùng metric và reviewer. |
| **Response** | Hành động khi metric xấu, missing hoặc không đáng tin. |
| **Caveats** | Điều gì không thể suy ra từ kết quả. |

### Ví dụ định nghĩa chặt

**ZT-POL-01 – Verified policy enforcement coverage:** tỷ lệ access attempts vào high-impact resources trong production, trong kỳ, có thể truy vết từ yêu cầu tới policy decision phù hợp và một enforcement outcome ở PEP được bảo vệ, loại trừ duy nhất các giao dịch trùng có xác nhận.

Nếu PDP thiếu log trong một giờ, các requests trong giờ đó **không tự động được tính là PASS**. Nếu không biết tổng số request thực tế, không nên công bố coverage chính xác; cần công bố **evidence gap** và độ bao phủ nguồn.

## 8. Metric taxonomy: KPI, KRI, KCI và assurance indicators

| Nhóm | Chức năng | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| **KPI – performance** | Đo tiến độ/năng lực vận hành. | Thời gian xử lý access revocation, policy deployment lead time. | Nhanh không đồng nghĩa policy đúng. |
| **KRI – risk** | Gợi ý rủi ro/phơi lộ. | Số privileged grants vượt hạn, số unmanaged access paths. | Tùy discovery và risk severity. |
| **KCI – control** | Đo control được thực thi đúng. | Negative cross-tenant tests PASS, denied unauthorized key usage. | Phải rõ test population. |
| **Coverage** | Đo phạm vi control hoặc giám sát. | Tỷ lệ critical APIs có verified PEP. | Coverage không đồng nghĩa effectiveness. |
| **Outcome** | Đo khả năng giảm tác động thực tế. | Blast radius trong breach simulation, confirmed time-to-containment. | Phụ thuộc kịch bản và phương pháp test. |
| **Confidence/evidence** | Đo tin cậy của kết luận. | Coverage telemetry, tuổi dữ liệu, unresolved evidence gaps. | Không phải điểm trưởng thành kỹ thuật. |

### Cấu trúc báo cáo hai trục

Nên hiển thị **Control outcome** và **Evidence confidence** như hai chiều riêng. Ví dụ:

| Kết quả control | Bằng chứng | Diễn giải |
| --- | --- | --- |
| PASS | High confidence | Có cơ sở kết luận trong scope/kỳ được nêu. |
| PASS trên mẫu nhỏ | Low confidence | Chỉ hỗ trợ kết luận hẹp; cần mở rộng population. |
| FAIL | High confidence | Phát hiện rõ ràng, cần xử lý theo risk. |
| Unknown | Low confidence | Không đủ cơ sở, không gán “an toàn” hoặc “đã vi phạm”. |

## 9. Trụ cột Identity: đo xác minh và đặc quyền

Identity là trọng tâm của nhiều chính sách Zero Trust. Tuy nhiên, **MFA enrollment** không tương đương **MFA được thực thi cho mọi access path cần bảo vệ**.

### Metrics điển hình

| Metric | Cách tính/tổ chức phép đo | Caveat |
| --- | --- | --- |
| **Strong authentication coverage** | Số eligible authentication paths bắt buộc phương thức được phê duyệt / mọi eligible paths thuộc scope. | Đếm paths, không chỉ số user đã đăng ký MFA. |
| **Phishing-resistant authentication adoption** | Số identities thuộc nhóm được duyệt đã sử dụng phương thức phishing-resistant phù hợp / mọi identities trong nhóm đó. | “Có đăng ký” khác với thực sự sử dụng và không có fallback yếu. |
| **Privileged JIT coverage** | Số privileged actions/grants được kiểm soát bằng approval và thời hạn / tổng privileged actions/grants thuộc scope. | Có JIT tool nhưng vẫn có standing admin bypass thì không đủ. |
| **Stale identity/grant rate** | Số identities/grants quá hạn hoặc không có owner / tổng được kiểm kê. | Phải khám phá cả service principals và break-glass. |
| **Deprovision propagation latency** | Phân vị thời gian từ revocation event tới hiệu lực deny trên đường truy cập được thử. | IdP disable không tự thu hồi session/token ở mọi resource. |
| **Identity binding correctness** | PASS/total negative tests wrong issuer, subject, audience, tenant và account linking. | Test coverage phải theo protocol và multi-tenant flows. |

### Tách user và non-human identity

Không dùng MFA adoption để đo workload security. Service identities cần những metrics riêng: credential lifetime, owner, scope, audience, attestation, rotation, grants và khả năng revoke.

### Đừng dùng “failed login” như bằng chứng chính

Số failed logins có thể tăng do attacker activity hoặc do chính sách đang chặn tốt. Giảm số thất bại cũng có thể do nguồn log bị tắt. Cần xem baseline, threats, detector health và business friction.

## 10. Trụ cột Devices: đo posture và độ mới của tín hiệu

Device posture có thể bao gồm quản lý thiết bị, OS/patch posture, endpoint protection, disk encryption, integrity signals và thông tin rủi ro. **Một thiết bị compliant tại lúc đăng nhập có thể trở nên không compliant sau đó**.

### Các câu hỏi định lượng

- Bao nhiêu access attempts vào resources quan trọng có device identity và posture attestation phù hợp?
- Tỷ lệ posture signals còn trong **maximum age** được policy cho phép?
- Có thể dùng thiết bị unmanaged đi qua app path khác không?
- Thời gian từ trạng thái compromised/non-compliant tới enforcement deny/step-up/restrict?
- Những devices offline, agent broken hoặc missing telemetry được xử lý ra sao?
- Có false deny ảnh hưởng người dùng hợp lệ và có đường support an toàn?

### Phân biệt ba chỉ số

1. **Device enrollment coverage:** biết thiết bị nào có trong hệ thống quản lý.
2. **Device compliance at decision:** posture đã được đánh giá và đạt đúng thời điểm quyết định quyền.
3. **Effective posture enforcement:** khi device không đạt, đường truy cập thực sự bị ngăn hoặc giảm quyền theo chính sách.

Một báo cáo “98% devices compliant” chỉ có ý nghĩa khi mẫu số và freshness rõ. Nó không chứng minh 2% còn lại không truy cập được dữ liệu quan trọng.

## 11. Trụ cột Networks: đo segmentation và trust boundaries

Network Zero Trust không chỉ là chặn port. Mục tiêu là **giới hạn đường tương tác được phép theo resource, identity và use case**, ngăn lateral movement vượt phạm vi.

| Metric | Cách hiểu đúng |
| --- | --- |
| **Known flow inventory coverage** | Bao nhiêu network/service flows trọng yếu đã được phát hiện, phân loại và có owner? |
| **Policy-enforced flow coverage** | Bao nhiêu flow paths thuộc scope có enforcement trên đúng hướng và port/protocol? |
| **Unauthorized path block rate** | Trong bộ negative attack-path tests có căn cứ, bao nhiêu đường bị chặn? |
| **Egress restriction coverage** | Workloads xử lý dữ liệu nhạy cảm có policy egress phù hợp trên thực tế? |
| **Network policy drift** | Số thay đổi effective policy ngoài baseline hoặc chưa được review. |
| **Service identity coverage** | Bao nhiêu service-to-service flows thực thi workload authentication/authorization theo yêu cầu? |
| **Containment latency** | Thời gian từ quyết định cô lập workload tới khi các paths thuộc scope không còn dùng được. |

### Tại sao chặn nhiều kết nối không đồng nghĩa tốt?

Một tường lửa chặn hàng triệu requests có thể do scanner, lỗi cấu hình hoặc một source lặp vô hạn. Số packet deny không đo sự đúng đắn của policy. Ngược lại, một allow rule quá rộng có thể không tạo denied events và vẫn là lỗ hổng.

### Micro-segmentation cần test từ vị trí attacker

Nếu một workload trong application zone bị chiếm, attacker có thể truy cập DB admin, metadata service, artifact registry hoặc tenant khác qua đường nào? Kiểm tra **effective policy**, không chỉ YAML firewall/Kubernetes NetworkPolicy được khai báo.

## 12. Trụ cột Applications & Workloads: đo authorization theo hành động

Một application có SSO và TLS vẫn có thể lộ dữ liệu vì thiếu **object-level authorization**, IDOR/BOLA hoặc service-to-service permissions quá rộng.

### Metrics quan trọng

| Metric | Đơn vị/mẫu số | Verification |
| --- | --- | --- |
| **Protected API action coverage** | Những endpoint/action thuộc scope có authorization policy bắt buộc / toàn bộ endpoint/action eligible. | API inventory + router/config/code + direct-call negative tests. |
| **Object-level deny correctness** | Cross-resource/tenant negative scenarios PASS / scenarios được thiết kế từ threat model. | Integration tests và runtime traces. |
| **Workload identity least privilege** | Identity grants phù hợp approval / tất cả effective grants cần review. | Permission graph, negative use tests. |
| **Secret/credential hygiene** | Workloads dùng credentials theo baseline / workloads thuộc scope. | Registry, secret scanner, effective runtime config. |
| **Pipeline trust coverage** | Production artifacts có provenance/verification theo policy / artifacts triển khai thuộc scope. | CI/CD policy, registry metadata, deploy gate. |
| **Unmanaged direct access paths** | Số đường gọi endpoint hoặc DB ngoài policy enforcement đã phát hiện. | Route scan, code review, attack-path test. |
| **Policy version alignment** | Instances thực thi phiên bản policy được phê duyệt / instances thuộc release scope. | Config readback và deployment inventory. |

### Workload identity không phải “có certificate là đủ”

mTLS có thể xác minh danh tính một workload theo trust chain, nhưng không thay quyết định về **resource/action/tenant**. Đo một quyền không đủ bằng số certificate đã cấp; cần test service A không thể đọc dữ liệu B ngoài nhiệm vụ ngay cả khi giao thức kết nối hợp lệ.

### Business logic vẫn quan trọng

PEP có thể chỉ hiểu role “USER”, trong khi yêu cầu thật là “USER được đọc invoice mà mình sở hữu trong tenant hiện hành”. Đo lường phải kiểm tra **authorization semantics**, không chỉ middleware có mặt.

## 13. Trụ cột Data: đo kiểm soát tới dữ liệu thực

Data-centric Zero Trust cần biết **dữ liệu nào, phân loại ra sao, tại đâu, được ai dùng và chuyển cho ai**.

### Metrics có ý nghĩa

- Data inventory/classification coverage trên nguồn và bản sao.
- Sensitive data flows có owner, purpose, recipient và controls.
- Object/record-level authorization tests qua API, export, search và analytics.
- Access path coverage đối với data stores, không chỉ với ứng dụng frontend.
- Encryption/key access policy effectiveness và quyền Decrypt theo scope.
- Retention/deletion verification ở source, cache, index, warehouse và backup trong phạm vi.
- Excessive privilege hoặc bulk export attempts được quan sát/kiểm tra.
- DLP/data movement rules có **precision/recall** được đánh giá trên tập test phù hợp.
- Data minimization compliance của các event/consumer contracts.

### DLP alert count dễ gây hiểu sai

Một số alert tăng có thể do detector tốt hơn hoặc do dữ liệu bị chia sẻ nhiều hơn; alert giảm có thể do false negatives hoặc telemetry bị mất. Cần **ground-truth tests**, sample review, tenant/flow context và xác minh kết quả ngăn chặn.

### Encryption không thay data authorization

Khi một API có quyền giải mã rồi trả hồ sơ của tenant khác, storage encryption có thể vẫn đạt đúng mục tiêu chống mất disk. Zero Trust data assurance phải đo cả **đúng người, đúng mục đích, đúng resource, đúng hành động và đúng thời điểm**.

## 14. Ba năng lực xuyên trụ cột: visibility, automation và governance

Một số mô hình maturity phân loại Zero Trust theo các trụ cột Identity, Devices, Networks, Applications and Workloads, Data cùng các năng lực xuyên suốt **Visibility and Analytics**, **Automation and Orchestration**, **Governance**. Đây là **khung tham chiếu để cấu trúc câu hỏi**, không phải một chứng nhận được tạo ra từ điểm tự chấm.

### Visibility and Analytics

- Độ đầy đủ và độ mới của identity/device/resource/flow inventory.
- Tỷ lệ critical decision/enforcement events có correlation.
- Khả năng phát hiện nguồn log im lặng, mất sự kiện hoặc clock skew.
- Telemetry đáp ứng forensic/incident use cases mà không ghi thừa dữ liệu nhạy cảm.

### Automation and Orchestration

- Tỷ lệ policy changes có kiểm tra và rollout/rollback tự động.
- Thời gian propagate revocation, quarantine và policy response.
- Tỷ lệ automated remediations có guardrails và post-action verification.
- Số lần automation bị bypass, rollback, race condition hoặc tạo false deny.

### Governance

- Coverage của policy owners, risk owners, approval và exception expiry.
- Requirements→controls→tests→evidence traceability.
- Frequency/freshness của access reviews, policy reviews và reassessments.
- Chất lượng findings, thời gian remediation và retest.

**Tự động hóa nhanh một policy sai chỉ làm phạm vi ảnh hưởng tăng nhanh hơn.** Đo chất lượng quyết định và outcome cùng với thời gian automation.

## 15. Đo tính đúng đắn của policy decision và enforcement

Một hệ thống có thể ghi nhận hàng triệu policy decisions, nhưng điều cần bảo đảm là quyết định **đúng theo requirements và được thực thi tại tài nguyên**.

### Bốn trạng thái cần phân biệt

| PDP decision | PEP behavior | Đánh giá |
| --- | --- | --- |
| Allow | Cho phép đúng action/resource theo requirement. | Có thể PASS nếu evidence đầy đủ. |
| Deny | Từ chối đúng action/resource trái quyền. | PASS với negative scenario đã xác định. |
| Allow | PEP bỏ qua constraints, trả dữ liệu thừa hoặc bypass. | FAIL về enforcement/business authorization. |
| Deny | PEP vẫn cho resource access qua đường khác. | FAIL nghiêm trọng về bypass. |

### Policy correctness khác policy volume

Tính tỷ lệ đúng trên **scenario suite** xây từ permissions matrix, threat model và business rules; không dùng nhãn “allow” hay “deny” trong log làm nhãn chân lý. Đối với các use cases đủ quan trọng, cần expected outcomes do owners xác nhận và review độc lập.

**Decision correctness on tested cases = số scenarios có observed outcome đúng / số scenarios có expected outcome được xác minh.**

### False permit và false deny

- **False permit:** hệ thống cho phép thao tác đáng lẽ phải từ chối; có thể gây lộ dữ liệu hoặc tăng quyền.
- **False deny:** hệ thống từ chối thao tác hợp lệ; ảnh hưởng availability, người dùng và có thể thúc đẩy workaround.

Hai loại lỗi có impact khác nhau. Không chỉ tối ưu “tỷ lệ deny cao”; phải đánh giá **chi phí bảo mật và trải nghiệm** cùng điều kiện hệ thống thực.

## 16. Continuous evaluation: đo độ trễ phản hồi tín hiệu rủi ro

Zero Trust thường cần thay đổi quyết định khi xuất hiện tín hiệu như device non-compliant, tài khoản bị vô hiệu hóa, privileged role bị thu hồi hoặc token/session bị hủy.

### Ba thời điểm cần đo

- **T0 – Signal occurred:** sự kiện gốc xảy ra, ví dụ thiết bị được đánh dấu compromised.
- **T1 – Signal available to decision process:** PDP hoặc hệ thống liên quan đã có tín hiệu.
- **T2 – Enforcement effective:** PEP/resource không còn cho phép hành động bị cấm.

**Signal propagation latency = T1 − T0.**

**Enforcement latency = T2 − T1.**

**End-to-end revocation latency = T2 − T0.**

### Cần thống kê phân vị và ngoại lệ

Báo cáo median có thể giấu nhóm users lâu bị thu hồi. Tùy threat model nên đo **p50, p95, p99, maximum observed, timed-out và unknown**; không được bỏ các phiên không có T2 để số liệu trông đẹp hơn.

Nếu một client có offline token hoặc bearer capability dùng được đến lúc hết hạn, policy phải định nghĩa **acceptable stale window** hoặc cơ chế thu hồi. Không tuyên bố “continuous” khi thực tế chỉ kiểm tra lúc đăng nhập mà không có reassessment phù hợp.

## 17. Session, token, cache và effective permissions

Chính sách được cập nhật tại PDP không đồng nghĩa một session, signed URL hoặc cache authorization cũ lập tức vô hiệu.

### Các đường cần đo

| Access mechanism | Rủi ro | Cách kiểm tra |
| --- | --- | --- |
| **Browser session** | Session sống sau deprovision. | Revoke user, thử hành động ở từng app/resource, đo T2. |
| **Access token** | Token cũ còn hợp lệ đến expiry. | Kiểm tra audience/scope, refresh/revocation semantics. |
| **Refresh token** | Có thể tạo phiên mới sau credential removal. | Revoke và thử refresh/relogin. |
| **Signed object URL** | Truy cập file không đi qua API sau khi tạo. | Wrong tenant/revoked/expired URL tests. |
| **PDP decision cache** | Quyền cũ được replay từ cache. | Thay policy/role, kiểm tra TTL và invalidation. |
| **Service credentials** | Secrets/keys sống lâu sau khi service bị vô hiệu. | Disable principal, thử truy cập resource thật trong scope. |
| **Offline endpoint** | Không nhận risk signal kịp. | Kiểm tra offline policy và reconciliation. |

**Đo trạng thái hiệu lực tại tài nguyên**, không chỉ đo thao tác gọi API revoke thành công. Một request trả 200 “revoked” có thể chưa thực sự vô hiệu session ở downstream.

## 18. Đo blast radius và chống lateral movement

Zero Trust không có nghĩa không bao giờ có compromised identity. Assurance phải trả lời **một compromise có thể mở rộng tới đâu**.

### Scenarios kiểm thử

1. Một workload trong app zone bị chiếm, thử đọc secrets của service khác.
2. User tenant A cố truy cập tenant B qua API, export, search và cache.
3. Non-admin workstation cố gọi privileged management endpoint.
4. Service principal ở test environment cố gọi production KMS/DB.
5. Một pod bị chiếm thử metadata service, registry hoặc cloud control plane.
6. Credential đã bị thu hồi thử dùng với phiên cũ.
7. Vendor integration key bị lạm dụng để gọi ngoài scope.

### Các cách biểu diễn kết quả

- **Blocked attack-path coverage:** số attack paths thuộc suite được ngăn đúng / số paths đã thử; nêu cách chọn suite.
- **Reachable critical assets from assumed foothold:** số tài sản quan trọng có thể tiếp cận trong mô hình/test; phân tách reachability và ability to read data.
- **Blast-radius bound:** số identities/resources/tenants thực sự có thể bị ảnh hưởng trong kịch bản đã giả lập.
- **Time to isolate:** thời gian từ containment command đến khi các paths thuộc scope không còn sử dụng được.

Các kết quả chỉ có giá trị đối với **foothold, phương pháp, policy version và thời kỳ thử nghiệm**. Không nên viết “lateral movement prevented 100%” khi chỉ thử hai đường.

## 19. Đo detection, response và corrective control

Zero Trust có thể dùng telemetry và risk signals để hạn quyền khi cần, nhưng phải chứng minh cả **phát hiện → quyết định → thực thi → xác minh → phục hồi**.

~~~mermaid
flowchart TD
    A["Threat or posture event"] --> B["Signal detected and validated"]
    B --> C["Risk assessment and policy decision"]
    C --> D["PEP enforcement: deny / step-up / restrict"]
    D --> E["Verify access actually blocked"]
    E --> F{"Expected outcome observed?"}
    F -- "No" --> G["Finding + containment + root cause"]
    G --> H["Remediate, retest and update risk"]
    H --> B
    F -- "Yes" --> I["Evidence and monitored restoration"]
~~~

### Thời gian nên tách

| Thời gian | Bắt đầu → kết thúc | Vì sao khác nhau |
| --- | --- | --- |
| **Time to detect** | Sự kiện → detector tạo tín hiệu đáng tin. | Gắn với visibility. |
| **Time to decide** | Có tín hiệu → policy decision phù hợp. | Gắn với PDP/risk engine và policy latency. |
| **Time to enforce** | Decision → resource access bị chặn/hạn chế. | Gắn với PEP và caches. |
| **Time to verify containment** | Enforcement → kiểm tra các paths trong scope. | Gắn với bằng chứng kết quả, không chỉ lệnh đã gửi. |
| **Time to recover safely** | Khi được phê duyệt → chức năng hợp lệ hoạt động trở lại. | Tránh mở quyền vô hạn do khắc phục khẩn cấp. |

Một metric “MTTR 3 phút” vô nghĩa nếu không nói bắt đầu từ lúc nào, kết thúc khi nào và có đo quyền truy cập thật hay chỉ đo ticket closed.

## 20. Đo Zero Trust mà không tạo rủi ro quyền riêng tư mới

Đo lường cần dữ liệu identity, device, resource, location và session. Những dữ liệu này có thể liên quan đến cá nhân, tiết lộ hoạt động nhân viên hoặc dữ liệu khách hàng. Một chương trình assurance tốt cần hạn chế **dữ liệu cá nhân được sao chép vào dashboard và evidence**.

### Thiết kế telemetry tối thiểu

- Dùng stable references được kiểm soát khi cần correlation; không mặc định ghi email, địa chỉ, nội dung hóa đơn hoặc token.
- Hạn chế ghi device attributes chi tiết nếu risk model không cần.
- Phân tách policy/security event với payload nghiệp vụ.
- Bảo vệ collector, SIEM, data warehouse và export của chính metrics.
- Áp dụng data classification, owner, retention, access review và change control.
- Khi cần dùng sample gắn cá nhân để điều tra, có quy trình phê duyệt, redaction và bảo vệ phù hợp.

### Một xung đột cần giải quyết

Thu thập nhiều tín hiệu hơn có thể hỗ trợ phát hiện nhưng tăng attack surface và privacy harms. Cần nêu rõ **mục đích, necessity, minimization và retention**, không coi “security” là lý do tự động để lưu mọi hành vi vô thời hạn.

## 21. Danh mục metric cốt lõi: tử số, mẫu số và hành động

Các thước đo dưới đây là mẫu có thể điều chỉnh theo threat model. **Không có target tỷ lệ chung cho mọi tổ chức**. Mỗi metric phải đi cùng population, methodology và chất lượng evidence.

| Metric ID | Chỉ số và công thức/mẫu số | Ý nghĩa / hành động nếu không đạt |
| --- | --- | --- |
| **ZT-01** | **High-risk resource inventory coverage** = resources đã xác nhận owner/classification/access paths ÷ resources trong population được kiểm kê độc lập. | Thiếu inventory làm sai toàn bộ coverage. |
| **ZT-02** | **Verified PEP path coverage** = eligible access paths có enforcement thực chứng ÷ tổng eligible paths. | Điều tra direct routes/bypass. |
| **ZT-03** | **Decision–enforcement correlation** = eligible access attempts ghép được PDP+PEP+outcome ÷ tất cả access attempts quan sát được từ nguồn độc lập. | Thiếu evidence hoặc mismatch cần triage. |
| **ZT-04** | **Policy correctness tested** = expected scenarios có observed outcome đúng ÷ total tested scenarios có ground truth. | False permits/denies yêu cầu sửa policy hoặc tests. |
| **ZT-05** | **Strong auth enforced coverage** = eligible access paths thực thi phương thức đã duyệt ÷ mọi eligible paths. | Tìm fallback yếu, admin/service bypass. |
| **ZT-06** | **Phishing-resistant auth adoption** = identities trong nhóm yêu cầu thực sự dùng phương thức phù hợp ÷ identities cùng nhóm. | Kiểm tra exception, backup methods và identity lifecycle. |
| **ZT-07** | **Stale privileged grants** = grants quá hạn hoặc không owner ÷ grants trong privileged inventory. | Thu hồi/quản trị quyền. |
| **ZT-08** | **Revocation p95 latency** = phân vị 95 của (T2 − T0) trên verified revocation scenarios. | Xem cache, token, signed URL và session propagation. |
| **ZT-09** | **Device posture decision coverage** = access requests eligible có posture mới và được áp policy ÷ requests eligible. | Kiểm tra unmanaged/offline paths. |
| **ZT-10** | **Non-compliant device deny effectiveness** = negative scenarios thiết bị không đạt bị xử lý đúng ÷ cases tested. | Xem false permits, policy exceptions. |
| **ZT-11** | **Microsegmentation tested path block rate** = unauthorized paths bị chặn ÷ unauthorized paths thực tế đã thử. | Mở rộng graph và xử lý rule rộng. |
| **ZT-12** | **Unmanaged flow count** = discovered network/service flows không map với owner/policy. | Ghi số lượng tuyệt đối cùng discovery coverage. |
| **ZT-13** | **API object authz coverage** = protected actions có resource-level test phù hợp ÷ actions thuộc scope. | Ưu tiên BOLA, export, batch. |
| **ZT-14** | **Workload privilege exceptions** = effective grants ngoài baseline chưa được xử lý ÷ all grants được review. | Xử lý IAM drift và quyền kế thừa. |
| **ZT-15** | **Data flow classification coverage** = flows có source/recipient/classification/owner ÷ flows thuộc population. | Làm rõ dữ liệu analytics/log/backup. |
| **ZT-16** | **Cross-tenant negative test pass rate** = tests deny đúng ÷ negative scenarios đã chạy. | Critical failures không được che bằng trung bình. |
| **ZT-17** | **Sensitive data movement policy effectiveness** = test cases vượt field/recipient bị chặn ÷ attempted policy-violation cases. | Field allowlist và vendor contracts. |
| **ZT-18** | **Telemetry source health** = critical sources có heartbeat/lag/quality đạt ÷ critical sources thuộc inventory. | Thiếu log tạo evidence gap, không tự PASS. |
| **ZT-19** | **Risk signal freshness** = policy evaluations dùng signals không quá hạn ÷ eligible evaluations cần signal đó. | Điều chỉnh cache, TTL, sources. |
| **ZT-20** | **Verified containment latency** = phân phối thời gian từ trigger tới deny thực nghiệm. | Tách lệnh containment khỏi outcome. |
| **ZT-21** | **Policy change gate coverage** = security-relevant policy changes có review/test/deploy trace ÷ tất cả policy changes. | Tìm changes ngoài pipeline. |
| **ZT-22** | **Exceptions overdue** = số exceptions quá hạn chưa đóng/duyệt lại; phân loại impact. | Escalate risk owners và remediation. |
| **ZT-23** | **Evidence freshness** = controls có evidence đúng release/window được phê duyệt ÷ controls yêu cầu đánh giá. | Recollect/retest trên actual scope. |
| **ZT-24** | **Risk-driven remediation verified** = findings trong scope đã retest đạt ÷ findings đến hạn xử lý trong scope. | Phân biệt ticket closed và verified. |

### Lưu ý cách chia tỉ lệ

Nếu mẫu số bằng 0 hoặc không có dữ liệu chắc chắn, kết quả nên là **N/A hoặc Unknown**, không gán 100%. Nếu log thiếu, tỷ lệ quan sát trên nguồn còn hoạt động chỉ được báo **tỷ lệ của phần quan sát được**, không ngụ ý bao phủ toàn hệ thống.

### Phân tầng nguy cơ

Các metrics nên phân theo **critical resources, privileged identities, customer-facing paths, non-human identities, tenant tiers, cloud regions và exposure**. Một kết quả trung bình tốt có thể che thất bại ở tài sản rủi ro cao.

## 22. Ví dụ định lượng: cùng một dashboard, nhiều kết luận khác nhau

Giả sử đây là **dữ liệu giả lập** từ một SaaS trong một ngày, phục vụ minh họa cách tính, không phải kết quả đánh giá hệ thống thực:

- Một nguồn độc lập ghi nhận **12.500** attempts truy cập vào nhóm high-impact API.
- Có **12.150** attempts đối chiếu được policy decision và PEP enforcement outcome hợp lệ.
- Còn **350** attempts không đối chiếu đủ, bao gồm cả đường có thể chưa instrument.
- Bộ negative tests gồm **240** scenarios đáng lẽ phải bị từ chối: **228** observed deny đúng, **7** false permits và **5** inconclusive do thiếu evidence.
- Bộ positive tests riêng gồm **120** scenarios đáng lẽ được cho phép: **117** observed allow đúng và **3** false denies.

### Coverage trên tập đã biết

\[
\text{Verified decision-enforcement coverage} =
\frac{12.150}{12.500}\times100\%=97{,}2\%
\]

Điều này có nghĩa **97,2% attempts trong population được nguồn độc lập quan sát có bản ghi đủ điều kiện ghép nối**. Nó không có nghĩa chính sách đúng ở 97,2% attempts, càng không chứng minh 97,2% toàn bộ hệ thống được bảo vệ.

### Test result không được làm đẹp

Với 240 negative scenarios đã thử, tỷ lệ **có bằng chứng PASS trên toàn bộ scenarios** (bao gồm những trường hợp chưa kết luận trong mẫu số) là:

\[
\text{Verified negative scenario PASS proportion} =
\frac{228}{240}\times100\%=95\%
\]

Đây **không phải** tỷ lệ chính xác của policy trên toàn bộ traffic thực; nó chỉ mô tả bộ test đã chọn. Trong 240 negative scenarios vẫn có **7 false permits và 5 inconclusive**, không được bỏ 5 trường hợp chưa rõ để tăng tỷ lệ. Bộ 120 positive tests có **3 false denies**, cũng cần báo riêng.

Reviewer phải:

1. Tách suite thành **expected DENY** và **expected ALLOW**, rồi gắn PASS/FAIL/INCONCLUSIVE cho từng scenario.
2. Xác định 7 false permits thuộc đường nào, resource nào, criticality nào.
3. Kiểm tra 3 false denies trên bộ positive tests và mức ảnh hưởng nghiệp vụ.
4. Ghi 5 negative tests thiếu evidence là **Unknown**, không tự gán PASS.
5. Công bố riêng tỷ lệ PASS trên toàn bộ tests, failures, inconclusives và scope, tránh chỉ dùng một tỷ lệ aggregate.

Một tỷ lệ 95% có thể che **một false permit ở API có quyền xuất toàn bộ dữ liệu khách hàng**. Vì vậy, critical tests có thể phải đạt gate riêng thay vì gộp vào trung bình.

### Trường hợp mẫu số thiếu

Nếu nguồn độc lập chỉ quan sát 70% resource routes theo discovery được xác minh, không được dùng 97,2% làm “coverage toàn công ty”. Cần thêm chỉ số route-inventory completeness và báo rõ **coverage đối với observed population**.

## 23. Mô hình dữ liệu đo lường: event nào cần thu?

Tối thiểu phải có khả năng liên kết **request → policy decision → enforcement → resource outcome** mà không sao chép plaintext hoặc secret không cần thiết.

### Ví dụ event giả lập

~~~json
{
  "schema_version": 1,
  "event_type": "ZT_ACCESS_EVALUATION",
  "event_id": "sample-event-001",
  "request_id": "sample-request-019",
  "occurred_at": "2026-11-28T03:00:00Z",
  "environment": "production",
  "resource_ref": "invoice-resource-virtual",
  "resource_classification": "CONFIDENTIAL",
  "principal_ref": "opaque-principal-ref",
  "principal_type": "WORKLOAD",
  "action": "READ",
  "tenant_scope_ref": "sample-tenant",
  "device_posture_state": "NOT_APPLICABLE_TO_WORKLOAD",
  "risk_signal_age_ms": 800,
  "policy_id": "ZT-INVOICE-READ",
  "policy_version": "v12",
  "decision": "DENY",
  "enforcement_point": "invoice-api-service",
  "enforcement_result": "DENIED",
  "resource_outcome": "NO_DATA_RETURNED",
  "collector_status": "COMPLETE"
}
~~~

Đây là **dữ liệu học tập**, không có principal hoặc tenant thật. Trường resource_ref có thể vẫn liên kết dữ liệu cá nhân trong hệ thống thực; dữ liệu measurement phải được phân loại, phân quyền và lưu giữ theo mục đích.

### Ba loại sự kiện nên phân biệt

| Event | Producer | Ý nghĩa | Rủi ro khi thiếu |
| --- | --- | --- | --- |
| **Access attempt** | Resource/API/gateway/independent sensor | Có một hành động truy cập được yêu cầu hoặc thử. | Không biết mẫu số và đường bypass. |
| **Policy evaluation** | PDP/decision service | Quyết định, policy version, tín hiệu và điều kiện. | Không chứng minh lý do/độ mới của quyết định. |
| **Enforcement outcome** | PEP/resource layer | Quyền đã được chặn, cho phép hoặc áp constraints thế nào. | PDP deny có thể bị bypass mà dashboard vẫn xanh. |

Trong kiến trúc phức tạp, còn cần **signal-change events**, **policy-change events**, **session/revocation outcomes**, **control health** và **test outcomes**. Mọi event nên có schema version, provenance, thời gian, source và cách kiểm soát thay đổi.

### Correlation phải chịu được xử lý bất đồng bộ

Một request có thể sinh nhiều policy evaluations, retry, job và resource accesses. Không nên dùng cùng một request_id rồi đếm mọi bản ghi như các attempts khác nhau. Cần xác định **access-attempt ID**, causal job ID, event ID và quy tắc deduplication/reconciliation.

## 24. Ví dụ SQL kiểm tra decision–enforcement coverage

Trong ví dụ sau, tổ chức giả định có ba bảng được xây dựng từ nguồn độc lập và logs. **request_id được ràng buộc duy nhất cho mỗi access attempt** trong các bảng đã chuẩn hóa. Mọi bảng đã có timestamp, environment và resource context được xác minh bởi pipeline.

~~~sql
-- Ví dụ minh họa trên SQL có hỗ trợ CTE và CASE.
-- Parameters :from_time và :to_time do hệ thống đo cung cấp.
WITH eligible_attempts AS (
    SELECT request_id, resource_ref, action
    FROM resource_access_attempts
    WHERE environment = 'production'
      AND resource_criticality = 'HIGH'
      AND attempted_at >= :from_time
      AND attempted_at < :to_time
),
joined_evidence AS (
    SELECT
        a.request_id,
        a.resource_ref,
        a.action,
        d.policy_id,
        d.policy_version,
        d.decision,
        e.enforcement_result
    FROM eligible_attempts a
    LEFT JOIN normalized_policy_decisions d
      ON d.request_id = a.request_id
     AND d.resource_ref = a.resource_ref
     AND d.action = a.action
    LEFT JOIN normalized_enforcement_outcomes e
      ON e.request_id = a.request_id
     AND e.resource_ref = a.resource_ref
     AND e.action = a.action
)
SELECT
    COUNT(*) AS total_eligible_attempts,
    SUM(
      CASE
        WHEN policy_id IS NOT NULL
         AND enforcement_result IS NOT NULL
        THEN 1 ELSE 0
      END
    ) AS correlated_attempts,
    SUM(
      CASE
        WHEN policy_id IS NULL
          OR enforcement_result IS NULL
        THEN 1 ELSE 0
      END
    ) AS evidence_gaps
FROM joined_evidence;
~~~

### Điều kiện để query có ý nghĩa

- normalized_policy_decisions và normalized_enforcement_outcomes phải được **deduplicate theo contract**, không chỉ nhặt ngẫu nhiên một event khi có hai quyết định mâu thuẫn.
- Việc join resource/action phải dùng identifiers ổn định và provenance phù hợp; request_id bị trùng giữa tenants/services có thể gây ghép nhầm.
- Thời gian event và ingestion cần có **window alignment**; sự kiện đến muộn phải có reconciliation.
- Access attempts bị bỏ sót ở resource_access_attempts vẫn không xuất hiện trong denominator.
- Query chỉ đếm **correlation completeness**, không đánh giá allow/deny có đúng theo business requirements.
- Để xác minh enforcement, có thể cần thêm resource outcome và negative tests; bản ghi PEP tự khai không đủ nếu PEP bị bypass.

### Kiểm tra mẫu số độc lập

Đối chiếu access attempt counts với resource request logs, API gateway, network observations, workload inventory hoặc controlled synthetic traffic. Nếu các nguồn bất đồng, cần tạo finding về **measurement completeness**, không chọn nguồn cho tỷ lệ đẹp nhất.

## 25. Độ tin cậy của telemetry và chống dashboard xanh giả

**Measurement assurance** là kiểm chứng chính hệ thống đo lường. Nếu data pipeline không đáng tin, metrics dù nhiều chữ số vẫn không đáng tin.

| Chỉ tiêu chất lượng | Cách kiểm tra | Hậu quả nếu thất bại |
| --- | --- | --- |
| **Completeness** | Số source/attempts/events kỳ vọng so với nhận được. | Thiếu traffic/decisions, coverage bị thổi phồng. |
| **Freshness** | Độ trễ từ event_time đến ingest/query. | Policy drift/compromise không được phản ánh kịp. |
| **Accuracy** | Sample event so với resource thực và expected outcome. | False permits/denies tính sai. |
| **Uniqueness** | event_id/attempt_id và deduplication rules. | Retry bị đếm nhiều lần. |
| **Consistency** | Policy version, resource/action, tenant scope giữa nguồn. | Ghép sai PDP và PEP hoặc so khác kỳ. |
| **Integrity** | Quyền sửa/xóa, signing/hash/version nếu phù hợp. | Evidence bị thay đổi hoặc giả mạo. |
| **Availability** | Heartbeat, source health, queue lag, retries, DLQ. | Không có log nhưng dashboard tưởng không có risk. |
| **Provenance** | Origin, collector, schema, config và timestamp. | Không thể audit/reproduce. |
| **Privacy minimization** | Field allowlist, redaction và access review. | Kho evidence thành điểm lộ dữ liệu mới. |
| **Retention** | Có đủ thời kỳ cho claim và investigation? | Không thể chứng minh hoạt động trong cả kỳ. |

### Metric cho hệ thống đo

**Critical telemetry source health ratio = sources có heartbeat + expected event arrival trong giới hạn / tổng critical sources được phê duyệt.**

Nhưng health ratio chỉ có ý nghĩa nếu **source inventory đủ**, và heartbeat không thể thay bằng chứng tất cả event paths đều được ghi.

### Thử nghiệm cố tình làm mất nguồn

Trong môi trường được phép, tạm dừng một collector test, làm chậm queue hoặc tạo event hỏng schema. Kỳ vọng pipeline **báo missing/late/bad data** và đánh dấu metric Unknown/Partial phù hợp, thay vì tiếp tục vẽ 100% coverage từ dữ liệu trước đó.

## 26. Phương pháp lấy mẫu, phân vị và độ không chắc chắn

Với hệ thống lớn không thể thủ công kiểm tra mọi access, cần có phương pháp sampling có lý do.

### Các lựa chọn mẫu

- **Full population:** thích hợp với machine-readable configuration hoặc event counts khi nguồn đủ tin cậy.
- **Risk-based:** ưu tiên privileged users, critical APIs, sensitive data, cross-tenant paths.
- **Random/stratified:** giúp ước lượng một số đặc tính trên population có xác định, với giả định phù hợp.
- **Adversarial/negative:** tạo các yêu cầu đáng lẽ phải bị từ chối theo threat model.
- **Canary synthetic:** đo policy path và signal propagation một cách lặp lại, tránh dùng dữ liệu thật.
- **Incident-driven:** mở rộng thử nghiệm khi có alert, anomaly hoặc finding.

### Không dùng sampling sai mục đích

Một mẫu ngẫu nhiên có thể quá ít privileged actions để kết luận về rủi ro cao. Một bộ test chỉ gồm critical attack paths không đại diện tỷ lệ lỗi của toàn bộ traffic. Cần **báo cả cách chọn mẫu, phạm vi và kết luận có thể rút ra**.

### Các thống kê cần ghi

- Population và coverage estimate.
- Số items/requests/tests trong mẫu.
- Số PASS, FAIL, PARTIAL, INCONCLUSIVE, NOT TESTED.
- Window, environment, control versions.
- Percentiles p50/p95/p99 cho latency khi đủ mẫu, số timed-out/unknown.
- Bias và known exclusions.
- Mức tin cậy của measurement method; nếu dùng confidence interval thì nêu model/giả định.

Không đặt target p95 thấp hơn giới hạn refresh của chính token/policy architecture mà không có kế hoạch kỹ thuật; khi mục tiêu chưa đạt, cần xem **risk appetite và control design**, không chỉ yêu cầu dashboard đổi màu.

## 27. Kiểm thử Zero Trust: từ positive tới negative và failure-mode

Đo lường thực tế cần **ground truth**: với cùng principal, action, resource và context, expected outcome là gì? Nếu không biết expected outcome thì không thể tính correctness.

| Test ID | Scenario trong môi trường được phép | Expected outcome |
| --- | --- | --- |
| **ZT-T01** | User tenant A đọc hóa đơn tenant B qua API. | DENY và không lộ dữ liệu qua response/cache/log. |
| **ZT-T02** | User A gửi tenant_id B trong header/body. | Tenant binding tin vào principal/server context, không tin client claim. |
| **ZT-T03** | Service identity A gọi resource của service B ngoài scope. | DENY tại boundary tương ứng. |
| **ZT-T04** | Access token có audience hoặc issuer sai. | Từ chối, không fallback sang trust yếu. |
| **ZT-T05** | User đã bị deprovision nhưng còn session/token. | Theo policy, access bị chặn trong cửa sổ thời gian đã duyệt. |
| **ZT-T06** | Privileged JIT grant hết hạn. | Hành động privileged không còn được phép; audit đúng. |
| **ZT-T07** | Device chuyển từ compliant sang compromised. | PDP/PEP reassessment và deny/restrict/step-up theo risk policy. |
| **ZT-T08** | Device posture signal quá cũ hoặc missing. | Unknown được xử lý theo policy, không tự cho phép. |
| **ZT-T09** | Device không được quản lý thử đường login phụ. | Không bypass posture requirement của resource. |
| **ZT-T10** | Workload trong app zone thử gọi DB admin port. | Network/identity policy từ chối nếu ngoài allowed flow. |
| **ZT-T11** | Pod/runner thử lấy secret của workload khác. | Effective least privilege ngăn hành động. |
| **ZT-T12** | API gateway bị bypass qua direct service URL. | Không thể truy cập resource trái policy. |
| **ZT-T13** | Export worker nhận job có tenant context giả hoặc replay. | Job integrity/idempotency/authorization xử lý đúng. |
| **ZT-T14** | Signed download URL dùng sau khi quyền bị thu hồi. | Hành vi phù hợp thiết kế/cửa sổ thu hồi, ghi giới hạn nếu chưa thể revoke. |
| **ZT-T15** | Data event nhận thêm PII ngoài allowlist. | Contract/review gate ngăn hoặc báo FAIL. |
| **ZT-T16** | User có quyền READ nhưng thử BULK_EXPORT. | Không được quyền chỉ vì đã được READ. |
| **ZT-T17** | PEP trả allow nhưng resource authorization từ chối. | Event correlation phản ánh kết quả thật, không đếm access thành công. |
| **ZT-T18** | PDP trả deny nhưng tồn tại alternate route. | Test phát hiện bypass, FAIL. |
| **ZT-T19** | PDP/context provider không khả dụng. | Failure response theo approved policy; không fail open tùy tiện. |
| **ZT-T20** | Policy version drift giữa các replicas. | Phát hiện drift, có controlled rollout/rollback. |
| **ZT-T21** | KMS key grant bị thu hồi. | Service không còn Decrypt ngoài quyền, theo scope. |
| **ZT-T22** | Telemetry collector bị ngắt trong diễn tập. | Data health alert và trạng thái Unknown/Partial xuất hiện. |
| **ZT-T23** | Attacker giả định chiếm một workload để thử lateral access. | Các critical paths đã cấm vẫn bị chặn; blast radius được ghi. |
| **ZT-T24** | Policy chặn nhầm một user được phép. | False deny được ghi, escalation an toàn, không tạo bypass vĩnh viễn. |

### Cách viết test artifact

Mỗi test phải có:

1. Threat/requirement/control ID.
2. Environment, policy version, source và resource scope.
3. Principal/resource/action/context và trạng thái thiết bị giả định.
4. Expected result do owner có thẩm quyền phê duyệt.
5. Observed PDP decision, PEP enforcement và resource outcome.
6. Evidence reference, timestamp, collector/test tool.
7. PASS/FAIL/INCONCLUSIVE và lý do.
8. Finding, remediation, owner và retest nếu cần.

**Chỉ chạy các kịch bản trong môi trường, dữ liệu và quyền được phép.** Các thử nghiệm lateral movement và revocation nên dùng canary/synthetic resources, controlled identities và guardrails để không tạo disruption hoặc disclosure cho khách hàng thật.

## 28. Claim–Argument–Evidence (CAE) cho Zero Trust measurement

### Claim có thể kiểm tra

“Trong production release thuộc phạm vi đánh giá, các hành động đọc/xuất hóa đơn Confidential qua API, worker và download paths yêu cầu policy quyết định dựa trên danh tính/ngữ cảnh đã xác minh; các phép thử chéo tenant bị từ chối đúng và các policy enforcement events có evidence đủ theo tiêu chí được phê duyệt.”

### Argument

1. Resource inventory và flow maps xác định population thuộc scope.
2. Threat model và security requirements xác định expected decisions.
3. PEP được đặt trên tất cả paths trong inventory, PDP sử dụng policy/signals đã duyệt.
4. Independent access-attempt source cùng correlation chứng minh policy decision và enforcement outcome.
5. Negative tests kiểm tra false permits và bypass; positive tests kiểm tra false denies.
6. Telemetry quality, drift monitoring và response drills hỗ trợ kết luận trong thời kỳ.
7. Findings, exceptions, unknowns và residual risks được ghi rõ.

### Evidence tương ứng

| Assertion | Evidence | Giới hạn |
| --- | --- | --- |
| Mọi critical route có PEP. | Route/API/data flow inventory, config graph, direct-path negative tests. | Undiscovered routes có thể bị bỏ sót. |
| Policy dùng đúng inputs. | PDP config/version, signal integration tests, stale/invalid signal cases. | Logs có thể chỉ cho thấy signals đã gửi, chưa chứng minh authenticity. |
| Authorization đúng theo requirements. | Permission matrix, object-level positive/negative tests. | Suite có thể chưa bao phủ mọi combination. |
| Enforcement thực tế đúng. | PEP + resource outcome traces, bypass tests. | Nếu source log độc lập hỏng, confidence giảm. |
| Revocation đủ nhanh. | Controlled revoke experiments, timestamps T0/T1/T2. | Token/offline paths chưa thử phải ghi riêng. |
| Risk response hoạt động. | Exercises, incident traces, containment verification. | Drill không tự chứng minh mọi incident. |

### Design vs operating effectiveness

**Design effectiveness** kiểm tra policy, trust boundaries, PEP placement, signals, failure semantics và testability đã được thiết kế hợp lý chưa.

**Operating effectiveness** kiểm tra runtime configs, decisions, enforcement, sensor health, exceptions và outcomes **trong đúng kỳ/phiên bản**. Một thiết kế được duyệt không tự chứng minh production đã triển khai đúng.

## 29. Case study SaaS: đo hiệu quả Zero Trust khi xuất hóa đơn

### 29.1. Kiến trúc và mục tiêu

Invoice SaaS có nhiều tenant. Người dùng gọi API export; API tạo job trong queue; worker đọc database và tạo file PDF/CSV; object storage lưu file; một download service phục vụ kết quả.

**Business/security goal:** người dùng chỉ được tải dữ liệu thuộc tenant và quyền của mình; workers chỉ được đọc dữ liệu phục vụ job được xác minh; một service compromise không làm lộ dữ liệu tenants khác.

~~~mermaid
flowchart LR
    U["Tenant user"] --> GW["API gateway + ingress PEP"]
    GW --> API["Export API + object authz"]
    API --> JOB[("Server-owned job record")]
    API --> Q[("Message queue")]
    Q --> W["Export worker + workload identity"]
    JOB --> W
    W --> DB[("Tenant-scoped DB access")]
    W --> OBJ[("Private export storage")]
    OBJ --> DL["Download service + PEP"]
    U --> DL
    ID["IdP/device risk signals"] --> PDP["Policy decision and risk logic"]
    PDP --> API
    PDP --> DL
    API --> EV["Independent access/evidence pipeline"]
    W --> EV
    DL --> EV
    PDP --> EV
~~~

### 29.2. Risk scenarios

- **ZT-R01:** user A tự thay tenantId trong payload để đọc B.
- **ZT-R02:** worker có IAM quyền đọc toàn DB, một compromised worker ảnh hưởng mọi tenant.
- **ZT-R03:** policy kiểm tra lúc tạo job nhưng không kiểm tra khi tải file.
- **ZT-R04:** một signed URL tiếp tục dùng được sau khi user mất quyền.
- **ZT-R05:** queue replay tạo thêm file export ngoài scope.
- **ZT-R06:** log collector không ghi được download result; dashboard chỉ thấy policy allow.

### 29.3. Requirements và controls

| Requirement | Control | Verification |
| --- | --- | --- |
| ZT-INV-01: tenant/resource authorization. | Verified principal + object-scope policy tại API. | Wrong tenant/resource negative tests. |
| ZT-INV-02: job integrity. | Server-owned job record; trusted binding of actor, tenant and resource. | Forged/replayed message tests. |
| ZT-INV-03: workload least privilege. | Workload identity, scoped permissions, no unrelated admin rights. | Effective grants và denied-use tests. |
| ZT-INV-04: download reauthorization. | PEP kiểm tra actor/resource hoặc capability có giới hạn được duyệt. | Wrong principal, revoked, expired link tests. |
| ZT-INV-05: signal freshness. | Session/device/risk status được đánh giá theo policy. | Change/revoke T0→T2 measurement. |
| ZT-INV-06: observable enforcement. | Correlated attempt, decision, resource outcome. | Reconciliation, collector health simulation. |

### 29.4. Baseline giả định

Từ inventory và tests, team phát hiện:

- 32 protected API actions nhưng chỉ 27 có resource-level negative tests.
- Worker dùng 1 role có quyền read quá rộng.
- 5 đường tải file được biết; 1 đường CDN không đi qua app reauthorization.
- Revoke user tại IdP thành công nhưng signed link đã phát hành vẫn dùng được tối đa theo thời gian sống của nó.
- Evidence pipeline chưa có independent download outcome.

**Đừng viết “84% Zero Trust”.** Cần ghi rõ 27/32 là **API test coverage**, không phải tỷ lệ authorization đúng; một CDN bypass có thể là blocker dù nhiều metrics khác tốt.

### 29.5. Quyết định và remediation

1. Tạo resource/action inventory và link từ API, job, object tới owner.
2. Thêm server-owned job record, bind tenant và principal, validate lại tại worker.
3. Thu hẹp IAM grants cho worker; bổ sung denied-use tests.
4. Thiết kế download authorization/revocation semantics, xét cửa sổ signed URL còn hợp lệ theo risk.
5. Bổ sung negative tests cho mọi export/download paths, gồm CDN.
6. Đưa outcome records từ resource path vào evidence pipeline và kiểm tra source health.
7. Đo thời gian từ disable user tới T2 trên nhiều session/url scenarios.
8. Đóng finding chỉ sau runtime verification và đánh giá historical exposure khi cần.

### 29.6. Kết quả mong muốn sau retest

Không tự giả định fix đã thành công. Báo cáo phải điền **observed** sau khi thực sự chạy:

| Claim | Expected evidence | Trạng thái minh họa trước retest |
| --- | --- | --- |
| API object authz đầy đủ. | 32/32 actions có tests được review và chạy đúng. | PENDING |
| Worker deny ngoài scope. | Effective IAM + denied-use canaries. | PENDING |
| Download không bypass. | Tests trên mọi known path kể cả CDN. | PENDING |
| Revocation trong giới hạn. | T0/T2 trên sessions và links, percentiles/unknown. | PENDING |
| Telemetry đủ. | Independent attempts + PDP + PEP + outcome, health checks. | PENDING |

### 29.7. Kết luận có giới hạn

Nếu các tests đạt trong release được đánh giá, có thể hỗ trợ claim về **những data paths và threat scenarios đã kiểm chứng**. Không thể chỉ từ việc sửa policy kết luận **không có dữ liệu bị đọc trước đây**, hoặc mọi undocumented paths đã biến mất.

## 30. Scorecard nhiều chiều thay vì “Zero Trust score” duy nhất

Một scorecard tốt không nên cộng mọi tỷ lệ vào một số tổng hợp rồi bỏ thông tin quan trọng.

| Dimension | Coverage | Effectiveness | Evidence confidence | Critical findings |
| --- | --- | --- | --- | --- |
| Identity | Identity population và auth paths. | Authentication/privileged decision tests. | Identity logs, rights/role diff. | Wrong role elevation, stale admin. |
| Device | Posture-required paths. | Non-compliant device tests. | Sensor freshness và bypass checks. | Unmanaged path to critical data. |
| Network | Discovered/managed flows. | Unauthorized path deny tests. | Flow inventory + effective policy. | Direct management-plane access. |
| App/workload | Resource/action enforcement points. | Object/workload denied-use tests. | PDP/PEP/resource correlation. | BOLA, wildcard workload grants. |
| Data | Classified assets/recipient flows. | Data authz/minimization/retention tests. | Data lineage, access and export logs. | Unauthorized bulk export. |
| Crosscutting | Source owners, review gates, telemetry. | Detection/revocation/remediation drills. | Source health, provenance. | Evidence blind spot in key path. |

### Gate trước khi tổng hợp

Có thể đặt **mandatory gates** cho tình huống bất khả chấp nhận theo policy, chẳng hạn critical resource có đường bypass hoặc cross-tenant read được xác minh. Không dùng một tỷ lệ tốt ở Identity bù cho thất bại trọng yếu ở Data.

### Tách trạng thái

- **PASS:** tiêu chí đạt với evidence đủ trong scope/kỳ.
- **FAIL:** có bằng chứng cho thấy tiêu chí sai.
- **PARTIAL:** một phần đáp ứng hoặc scope chưa đầy đủ.
- **UNKNOWN/NOT TESTED:** không đủ dữ liệu/không thử.
- **NOT APPLICABLE:** có lý do hợp lệ trong scope.
- **EXCEPTION:** rủi ro được chấp nhận theo thẩm quyền; không tự chuyển thành PASS.

## 31. Maturity model có ích nhưng không thay assurance

Các mô hình trưởng thành Zero Trust giúp xác định **năng lực đang ở đâu và lộ trình cần xây**. Ví dụ một mô hình có thể chia các mức từ truyền thống tới tối ưu, hoặc đánh giá mức độ automation trên từng pillar.

### Hai cách hỏi khác nhau

**Maturity:** “Đội ngũ có quản lý policy tập trung, resource inventory, policy-as-code, automated reevaluation và continuous diagnostics không?”

**Assurance:** “Khi user mất quyền hoặc thiết bị bị compromised, các hành động trên tài nguyên nhạy cảm thật sự bị chặn trong thời hạn quy định, trên những paths đã xác định, với evidence nào?”

### Không biến maturity thành chứng nhận

Không tự gắn nhãn “NIST compliant” hoặc “CISA certified” chỉ vì tự chấm một bảng. Cần phân biệt **khung tham khảo**, **yêu cầu áp dụng thật** và **bằng chứng đáp ứng phạm vi**.

### Maturity khi không đủ data

Một chương trình có centralized policy nhưng inventory thiếu workloads nên có thể maturity tốt ở một hạng mục và confidence thấp ở outcome. Ghi **độ bất định** thay vì mặc định các mục không thấy đều tốt.

## 32. RACI và trách nhiệm đối với measurement

| Vai trò | Trách nhiệm chính |
| --- | --- |
| **Business/risk owner** | Xác định assets quan trọng, risk appetite, bắt buộc xử lý critical failures và phê duyệt residual risk. |
| **Zero Trust program owner** | Quản trị goals, measurement framework, roadmap và reporting cadence. |
| **Identity owner** | IdP, authentication, privileged grants, deprovision, identity evidence. |
| **Device/security endpoint owner** | Posture criteria, sensor coverage, device events, enforcement testing. |
| **Network/platform owner** | Segmentation, flow inventory, policy enforcement, workload paths. |
| **Application/workload owner** | Resource authorization, PEP integration, workload identities, runtime tests. |
| **Data owner/privacy owner** | Classification, purpose, data flows, recipients, access và lifecycle. |
| **Detection/response team** | Signal integrity, incident detection, containment drills, remediation. |
| **Data/measurement engineer** | Metric definitions, event pipeline, schema, data quality và dashboards. |
| **Assurance assessor** | Ground truth, methodology, evidence quality, independent verification và findings. |

### RACI minh họa cho một high-risk authorization metric

**R** = thực hiện; **A** = giải trình cuối cùng; **C** = tham vấn; **I** = thông báo.

| Hoạt động | App owner | Policy/IAM owner | Measurement team | Assurance | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| Resource/action population | **A/R** | C | C | C | I |
| Expected decisions và policy requirements | R | **A/R** | C | C | I |
| Instrument events và reconciliation | C | C | **A/R** | C | I |
| Independent tests và evidence review | C | C | C | **A/R** | I |
| Risk treatment cho critical false permit | R | R | C | C | **A** |
| Retest và closure evidence | R | R | C | **A/R** | I |

RACI phải phù hợp cơ cấu thực tế. Một người có thể giữ nhiều vai trò trong nhóm nhỏ, nhưng độ độc lập đánh giá cần tương xứng với mức rủi ro.

## 33. Continuous measurement: dashboard phải gắn với hành động

Một chương trình đo tốt có nhịp vận hành theo risk:

1. **Daily/near-real-time:** health of critical collectors, new bypass paths, expired privileged grants, severe policy drift, key identity anomalies.
2. **Weekly:** unresolved failed tests, stale signals, access review exceptions, data-flow/route inventory drift.
3. **Release/change gate:** policy version changes, new API/resource, new tenant tier, new workload or vendor path.
4. **Monthly/quarterly theo chương trình:** KPI/KRI trends, controlled revocation and segmentation drills, risk acceptance and remediation reviews.
5. **Incident-triggered:** mở rộng điều tra population/threat, kiểm tra policy efficacy và cập nhật expected scenarios.

### Một alert phải dẫn tới quyết định

Metric ZT-03 giảm vì PDP/PEP correlation missing:

- Ai được báo?
- Là lỗi collector, schema drift, route bypass hay policy path thực sự không được bảo vệ?
- Có cần hạn chế access, rollback hoặc mở incident không?
- Ai xác minh remediation?
- Có cần sửa claim đã công bố trong kỳ không?

Dashboard không có owner, action threshold và runbook có thể làm tăng nhiễu thay vì giảm rủi ro.

## 34. Quản lý ngoại lệ và residual risk trong Zero Trust

Một số hệ thống legacy hoặc vendor integrations có thể chưa đáp ứng toàn bộ yêu cầu. Ngoại lệ không phải “trừ khỏi mẫu số cho đẹp”.

### Một ngoại lệ tối thiểu cần

- Resource/identity/flow/action cụ thể.
- Requirement hoặc policy chưa đáp ứng.
- Threat scenario và impact.
- Existing controls có bằng chứng.
- Temporary compensating controls có thể kiểm tra.
- Owner, approver/risk owner, ngày hết hạn.
- Remediation plan và điều kiện retest.
- Reassessment triggers khi có incident, change hoặc control failure.

### Cách đưa vào metrics

**In-scope exceptions** nên được báo riêng, phân tầng theo criticality, tuổi và trạng thái. Nếu policy định nghĩa những ngoại lệ hợp lệ bị loại khỏi mẫu số một metric, phải công bố **số lượng và tác động của exclusions**, đồng thời có metric theo dõi overdue/unapproved exceptions.

### Current vs target

Nếu ngày hôm nay chỉ có 70% critical routes qua verified PEP và kế hoạch thêm gateway tháng tới, **current coverage vẫn là 70%** theo dữ liệu và scope hiện tại. Target có thể cao hơn, nhưng **plan chưa triển khai không phải control đã hiệu lực**.

## 35. Đánh giá thay đổi và hiệu quả thực nghiệm

Một mục tiêu Zero Trust có thể là giảm lateral movement hoặc giảm access persistence sau revoke. Để đo hiệu quả của một thay đổi:

1. Ghi **baseline** trước thay đổi, cùng metric definitions và discovery scope.
2. Định nghĩa **hypothesis**: sau thêm control X, kịch bản Y sẽ bị chặn hoặc giảm T2.
3. Xác định control, affected population và dependencies.
4. Chọn canary/pilot không gây rủi ro cho người dùng thật.
5. Kiểm tra positive/negative/failure cases và false-deny friction.
6. Đối chiếu outcomes trước–sau trên các điều kiện có thể so sánh.
7. Xem telemetry completeness, seasonality, changed threat/exposure và population drift.
8. Ra quyết định rollout/rollback cùng evidence và residual risk.

### Cẩn thận với before/after

Một dashboard cho thấy số denied requests tăng 40% sau triển khai policy không tự chứng minh risk giảm 40%. Có thể traffic tăng, detector đổi hoặc một client lỗi lặp requests. Cần chuẩn hóa theo exposure và kiểm tra **unauthorized access paths thực sự bị ngăn**.

### Cách đo pilot

Trên tập controlled synthetic attempts đại diện cho high-risk paths, đo tỷ lệ correct permit/correct deny, revocation latency, resource errors, login friction và availability. Đối với risk quá cao, không tạo false-permit test bằng dữ liệu khách hàng thật; dùng account/resource kiểm thử được kiểm soát.

## 36. Mẫu YAML cho một Zero Trust measurement specification

Mẫu dưới đây là **tài liệu minh họa có cấu trúc**, không phải cấu hình của sản phẩm thật và không phải bằng chứng đã đạt:

~~~yaml
measurement_id: ZT-POL-01
title: "Verified policy decision and enforcement coverage"
service: SECURITY_SECURITY_ASSURANCE
objective: "High-impact resource access must be evaluated and enforced"
environment: production
scope:
  resource_classes:
    - confidential-invoice-api
    - invoice-export-download
  principals:
    - customer-user
    - service-workload
  window: "calendar_day_utc"
  exclusions:
    - "Approved test traffic, reported separately"
owner_roles:
  resource_owner: "Invoice Product Owner"
  policy_owner: "IAM Control Owner"
  measurement_owner: "Security Analytics Owner"
  reviewer: "Independent Assurance"
formula:
  unit: "unique_access_attempt"
  numerator: >
    Attempts with validated policy decision and a matching
    verified PEP enforcement outcome in the required context
  denominator: >
    Eligible attempts discovered from independently validated
    in-scope resource access sources
  zero_denominator: "NOT_APPLICABLE_OR_UNKNOWN_WITH_REASON"
evidence_sources:
  - "versioned-resource-route-inventory"
  - "normalized-access-attempt-records"
  - "PDP-decision-logs"
  - "PEP-enforcement-events"
  - "negative-bypass-tests"
quality_gates:
  - "Required sources healthy during measurement window"
  - "No unexplained duplicate or uncorrelated event population"
  - "Schema versions and clock skew within approved bounds"
segments:
  - resource_criticality
  - principal_type
  - tenant_tier
  - region
  - policy_version
target:
  source: "Risk owner approved control criteria"
  value: "NOT_DEFINED_IN_EXAMPLE"
response_on_failure:
  - "Investigate instrumentation gaps and possible bypass paths"
  - "Open finding and test resource outcomes"
  - "Reassess published conclusion if evidence becomes incomplete"
status: "ILLUSTRATIVE_NOT_ASSESSED"
limitations:
  - "Unregistered resource routes require separate discovery"
reassessment_triggers:
  - "new_resource_or_endpoint"
  - "policy_or_PEP_change"
  - "telemetry_health_failure"
  - "confirmed_access_bypass"
~~~

**Không tự gán 100% hoặc một số target lý tưởng** khi chưa có baseline, threat analysis, triển khai và risk decision. Metric spec nên được version hóa; đổi định nghĩa mẫu số là một thay đổi có thể làm series lịch sử không còn so sánh trực tiếp được.

## 37. Những ngộ nhận thường gặp khi đo Zero Trust

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Có MFA là Zero Trust đã đạt.” | Phải đo MFA enforcement ở paths cần bảo vệ và các bypass/fallback. |
| “100% nhân viên đăng ký MFA nghĩa là mọi truy cập đã được xác minh.” | Service identities, sessions, admin paths và token flows có yêu cầu riêng. |
| “Đã triển khai mTLS nên mọi service được phân quyền đúng.” | mTLS hỗ trợ xác minh workload/kênh; resource authorization vẫn cần. |
| “98% devices compliant nghĩa là 98% requests an toàn.” | Device inventory, policy evaluation và enforcement có mẫu số khác nhau. |
| “Số firewall deny càng nhiều càng tốt.” | Deny count có thể bị ảnh hưởng bởi traffic lặp, scanners và lỗi cấu hình. |
| “PDP quyết định deny là PEP đã chặn.” | Phải kiểm tra enforcement outcome và bypass paths. |
| “Policy allow là quyền đúng.” | Cần ground truth từ requirements, owner và negative tests. |
| “Không có alert chứng minh không có attack.” | Sensor có thể im lặng, detector thiếu coverage hoặc log retention quá ngắn. |
| “Điểm maturity cao nghĩa là risk thấp.” | Maturity là năng lực; hiệu quả cần runtime evidence và tests. |
| “Zero Trust score 91% là thành công.” | Không có mẫu số chung tự nhiên; critical failures không được che. |
| “Một lần policy review chứng minh enforcement cả quý.” | Phải xét runtime config drift, thay đổi và khoảng thời gian. |
| “Revocation API trả success là user hết quyền.” | Phải đo effective deny ở các tài nguyên/session/cache. |
| “Có DLP nhưng không có alert nghĩa là không lộ dữ liệu.” | Cần kiểm tra detector quality, false negatives và recipient flows. |
| “100% test PASS nghĩa là mọi attacker bị chặn.” | Chỉ hỗ trợ các kịch bản/phạm vi được thử với quality đủ. |
| “Không thấy unknown resources tức inventory đủ.” | Có thể thiếu discovery; phải đối chiếu nguồn độc lập. |
| “Ngoại lệ có chữ ký có thể bỏ khỏi mọi báo cáo.” | Exclusions và accepted risks cần minh bạch và theo dõi. |
| “Tăng automation luôn nâng hiệu quả.” | Automation sai có thể khuếch đại false deny hoặc tạo bypass. |
| “Metric mới đẹp hơn nghĩa là risk giảm.” | Có thể khác mẫu số, nguồn log, traffic hoặc policy version. |

## 38. Checklist xây chương trình Đo lường Zero Trust

1. **Objectives:** mục tiêu bảo vệ nguồn lực và threat scenarios có rõ?
2. **Scope:** apps, identities, workloads, data, networks, regions và external paths được định nghĩa?
3. **Inventory:** có population, owners, criticality, discovery method và exclusions?
4. **Trust boundaries:** PEP/PDP và đường bypass đã được lập bản đồ?
5. **Policy requirements:** actor–action–resource–context và expected outcomes có thể test?
6. **Identity:** xác thực, privileged grants, non-human identities và deprovision có metrics riêng?
7. **Device:** posture freshness, unmanaged access và effective enforcement có được thử?
8. **Network:** unauthorized path tests và effective segmentation policies có đủ?
9. **App/workload:** object/tenant authz, token, job, export và workload grants có negative tests?
10. **Data:** sensitive flows, recipients, encryption, minimization, retention và access được đo?
11. **Continuous evaluation:** T0/T1/T2, offline sessions, cache và token windows đã định nghĩa?
12. **Events:** request, decision, enforcement, outcome có correlation và provenance?
13. **Data quality:** completeness, freshness, duplicate, clock skew, health và unknown handling?
14. **Metric specs:** numerator, denominator, units, time window, threshold, owner và caveats rõ?
15. **Sampling:** strategy phù hợp threat, population và risk; uncertainty được ghi?
16. **CAE:** claim–argument–evidence liên kết requirement, test và control?
17. **Reporting:** không trộn maturity/coverage/outcome; critical gate và confidence riêng?
18. **Exceptions:** có risk owner, expiry, compensating controls và retest plan?
19. **Response:** metric failure gắn alert, investigation, containment, remediation và retest?
20. **Change assurance:** policy/resource/vendor/device/identity changes có trigger reassessment?
21. **Privacy:** telemetry và evidence có minimization, access, retention phù hợp?
22. **Conclusion:** có scope, release, period, population, missing evidence và residual risk?

## 39. Bài tập thực hành và gợi ý giải

### Bài tập A — “98% MFA adoption” có nghĩa gì?

Bộ phận IAM báo 98% nhân viên đã đăng ký MFA. Nhưng ứng dụng legacy có thể đăng nhập bằng password-only ở URL khác.

**Gợi ý:** Tách **identity enrollment** khỏi **path enforcement**. Lập inventory mọi authentication paths, thử fallback và admin paths, đo tỷ lệ thực thi, phân tách service identities. Không diễn giải adoption thành đảm bảo mọi access.

### Bài tập B — PDP đã deny nhưng data vẫn bị đọc

Dashboard PDP cho biết request tenant A tới invoice B bị deny. Một direct API endpoint không đi qua gateway vẫn trả dữ liệu.

**Gợi ý:** Đây là failure ở **PEP coverage/complete mediation**. Kiểm tra resource routes, direct access, negative path tests, sửa enforcement ở layer phù hợp và đối chiếu logs với resource outcomes.

### Bài tập C — Device compliance cao nhưng dữ liệu vẫn lộ

99% laptops trong MDM compliant. Một unmanaged device vẫn truy cập được report export.

**Gợi ý:** Kiểm tra actual access paths và device-policy enforcement, không chỉ mẫu số enrolled devices. Thêm test device missing/non-compliant và xử lý ngoại lệ có phạm vi.

### Bài tập D — Revocation báo thành công sau một giây

IdP trả success khi disable account. Nhưng signed download links của người này vẫn sử dụng được nhiều giờ.

**Gợi ý:** Đo **T0→T2 tại resource**; phân biệt session/token/capability URLs, xác định cửa sổ risk phù hợp. Nếu links không thu hồi được theo thiết kế, phải ghi limitations, mitigation và trade-offs.

### Bài tập E — 100% segmentation tests PASS

Đội network thử hai đường giữa web và database, đều bị chặn. Sơ đồ thực tế có thêm CI runner, metadata service và admin plane chưa được thử.

**Gợi ý:** Tỷ lệ 2/2 chỉ đúng cho suite nhỏ. Cần attack-path inventory, criticality-based sampling, unknown paths và testing từ compromised footholds khác.

### Bài tập F — Số security alerts bằng 0

SIEM báo không có bất thường, nhưng collector của policy decisions đã dừng hai ngày.

**Gợi ý:** Không thể kết luận Zero Trust effective. Theo dõi telemetry source health, đánh dấu evidence gap, khôi phục/reconcile và xem lại báo cáo cho thời kỳ thiếu dữ liệu.

### Bài tập G — Decision correctness theo log

Team gọi mọi allow/deny do PDP tạo ra là “đúng” vì đó là kết quả policy engine.

**Gợi ý:** Phải có **ground truth**: requirement, permission matrix, owner-reviewed expected outcomes, positive/negative/failure tests. PDP self-report không tự chứng minh business authorization.

### Bài tập H — Bảng điểm 92% nhưng có cross-tenant BOLA

Năm trụ cột phần lớn được đánh giá xanh; còn một API có thể trả hóa đơn của tenant khác.

**Gợi ý:** Dùng **critical gate**, ghi FAIL và xử lý risk thay vì làm tròn theo điểm tổng. Maturity tốt không thay cho verified object-level authorization.

### Bài tập I — DLP alert giảm sau thay cấu hình

Alerts giảm 80% sau upgrade, nhưng detector mới không scan payload ở một consumer.

**Gợi ý:** Kiểm tra detection coverage, false negatives, source completeness và ground-truth cases. Không coi ít alert là data movement risk giảm.

### Bài tập J — Policy deployment tự động gây khóa diện rộng

Policy mới được rollout trong ba phút, nhưng chặn nhầm nhiều users hợp lệ, khiến họ chia sẻ một admin credential chung để làm việc.

**Gợi ý:** Đo false deny, business friction, unsafe workarounds và policy rollback, không chỉ deployment speed. Bổ sung pilot/canary, guardrails, người phê duyệt và secure exception workflow.

### Bài tập K — Service identities nằm ngoài MFA dashboard

MFA dashboard xanh toàn bộ nhưng một CI runner giữ long-lived production credential với quyền đọc secrets.

**Gợi ý:** Phân identity populations; đo workload owner, credential lifetime, effective grants, artifact trust, access logs và negative permission tests. MFA người dùng không đo được control của non-human identity.

### Bài tập L — Định nghĩa mẫu số thay đổi

Tháng trước báo PEP coverage 92% trên 100 APIs. Tháng này báo 98% nhưng chỉ còn 70 APIs trong inventory sau khi đổi công cụ discovery.

**Gợi ý:** Không khẳng định cải thiện. Đối chiếu population, inventory source, exclusions, version metric; có thể cần backfill/restate số cũ hoặc báo series mới và gap riêng.

## Kết luận

**Đo lường Zero Trust** là quá trình chứng minh **ai có thể truy cập tài nguyên nào, trong ngữ cảnh nào, với policy nào, điểm thực thi nào và kết quả gì**, đồng thời xác định rủi ro khi danh tính, thiết bị, workload hoặc đường truy cập bị compromise. Các tỷ lệ triển khai MFA, EDR, mTLS, ZTNA hay điểm maturity chỉ là **một phần đầu vào**. Zero Trust assurance cần định nghĩa đúng **population, numerator/denominator, data quality, ground truth, positive/negative tests, revocation latency, blast radius, telemetry health và residual risk**; sau đó nối metrics với **Claim–Argument–Evidence**, findings, remediation và continuous reassessment. Trong module **SECURITY_SECURITY_ASSURANCE**, kết luận có giá trị chỉ khi nói rõ **scope, thời kỳ, nguồn, mức tin cậy và phần chưa kiểm chứng**. **Không có một điểm Zero Trust duy nhất thay thế được bằng chứng rằng controls thực sự thực thi đúng chính sách và hạn chế tác động của những kịch bản rủi ro quan trọng.**
