# Đo lường Zero Trust IAM — Từ quyền được cấp đến truy cập thực sự được kiểm soát

> **Chương:** Zero Trust IAM  
> **Chủ đề:** Đo lường Zero Trust IAM  
> **Phạm vi module:** Quản lý vòng đời danh tính và truy cập (Identity and Access Management) theo mô hình **Joiner–Mover–Leaver (JML)**, từ xác minh danh tính, tạo tài khoản, cấp quyền, rà soát đến thu hồi khi thay đổi vai trò. Bài học kết nối IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Xây dựng mô hình đo lường Zero Trust IAM theo **kết quả an ninh, mức độ thực thi và chất lượng vận hành**, thay vì dựa vào số lượng tính năng đã bật.
2. Định nghĩa chỉ số có **tử số, mẫu số, đơn vị, cửa sổ thời gian, nguồn sự thật, owner, ngưỡng và ngoại lệ** rõ ràng.
3. Đo chính xác **độ trễ cấp quyền/thu hồi** trong JML và phân biệt cập nhật tại control plane với khả năng sử dụng quyền tại data plane.
4. Đo mức độ **Verify explicitly, Least privilege, Assume breach**, liên hệ policy enforcement, RBAC/ABAC, MFA/SSO, device posture, workload identity và micro-segmentation.
5. Đánh giá chất lượng dữ liệu audit, hiệu lực của các điểm thực thi PEP/PDP, sai lệch giữa quyền mong muốn với quyền thực tế và khoảng hở do token/cache/SCIM.
6. Thiết kế dashboard, cảnh báo, SLO, báo cáo theo mức rủi ro và phép thử chủ động để **chứng minh truy cập trái chính sách đã bị chặn**.
7. Nhận diện nguy cơ **đo sai, làm đẹp chỉ số, mẫu số thiếu, thiên lệch chọn mẫu hoặc xâm phạm quyền riêng tư**, rồi đề xuất cách khắc phục.

## 2. Vì sao đo lường Zero Trust IAM khó hơn đếm số tài khoản?

Một chương trình IAM có thể báo cáo:

- 100% nhân viên sử dụng SSO.
- 98% tài khoản đã đăng ký MFA.
- 99% yêu cầu SCIM trả về mã thành công.
- 95% quản lý đã hoàn tất kỳ access review.

Những con số này hữu ích cho **mức độ triển khai**. Tuy nhiên, chúng chưa chứng minh được một nhân viên vừa Leaver không còn dùng access token cũ, một service account đã ngừng không còn quyền cloud, hay một API không trả dữ liệu của tenant khác.

**Zero Trust IAM phải đo cả đường đi từ “danh tính/quyền đáng có” đến “quyết định và kết quả được thực thi”.** Từ góc độ giảm rủi ro, câu hỏi quan trọng là:

> Khi một chủ thể **không còn được phép**, hệ thống có ngừng cho phép hành động liên quan **ở nơi tài nguyên thật được truy cập** trong thời hạn đã cam kết không?

Ngược lại, hệ thống quá chặt tới mức chặn hàng loạt nhân viên hợp lệ cũng không đáp ứng yêu cầu vận hành. Một chương trình đo lường tốt phải thể hiện **bảo mật, mức sẵn sàng và trải nghiệm công việc hợp lệ**.

### Ba lớp bằng chứng

| Lớp | Ví dụ điều quan sát được | Giới hạn |
|---|---|---|
| **Control plane** | HRIS ghi Leaver, IdP disable user, SCIM xác nhận cập nhật nhóm | Chưa chứng minh mọi token/phiên ở API đã bị chặn |
| **Decision plane** | PDP đánh giá Deny theo policy version 12 | Chưa chứng minh PEP đã thực thi Deny và không có đường bypass |
| **Data plane** | API từ chối request bằng token cũ; không tạo file export; database không có side effect | Là bằng chứng sát kết quả hơn, nhưng chỉ bao phủ những đường thực sự được kiểm tra |

**Không nên gộp ba lớp thành một metric “revoke success”**. Đội IAM cần đo tiến độ provisioning; đội ứng dụng cần xác nhận hành vi authorization; đội Security cần đánh giá các đường truy cập phụ và rủi ro còn lại.

## 3. Nguyên tắc xây dựng hệ đo lường

Một bộ chỉ số đáng tin cần tuân theo các nguyên tắc sau.

1. **Đo kết quả có ý nghĩa bảo mật.** Tránh chỉ đếm bao nhiêu policy được viết, bao nhiêu lần MFA được gửi hoặc bao nhiêu sự kiện Deny được ghi.
2. **Định nghĩa phạm vi trước khi tính.** Danh tính người, nhà thầu, tài khoản đặc quyền, workload, bot và SaaS integration phải có cách xác định mẫu số.
3. **Gắn mỗi metric với một quyết định.** Nếu chỉ số xấu, ai có quyền thay đổi điều gì? Nếu không ai hành động, metric có thể chỉ là đồ trang trí dashboard.
4. **Phân tầng theo rủi ro.** Quyền export dữ liệu khách hàng và quyền đọc thông báo chung không nên dùng cùng một SLA thu hồi.
5. **Đo luồng đầu cuối.** Với Leaver, việc IdP báo thành công chưa phải kết thúc; cần kiểm tra cả phiên, token, local account và tài nguyên đích.
6. **Bảo toàn dấu thời gian và version.** Phân biệt thời điểm sự kiện có hiệu lực, lúc tiếp nhận, lúc quyết định, lúc lệnh cấp/thu hồi được gửi, lúc quyền thực sự thay đổi.
7. **Đo độ bao phủ và chất lượng đo.** Nếu chỉ quan sát 40% API, không nên báo “100% request nhạy cảm đã được kiểm soát”.
8. **Theo dõi xu hướng và nguyên nhân.** Sự thay đổi tử số có thể do chương trình tốt hơn hoặc do hệ thống log ngừng gửi dữ liệu.
9. **Tránh thu thập quá mức.** Cần ID kỹ thuật và lý do quyết định; không cần ghi bí mật xác thực hay nội dung dữ liệu cá nhân vào bảng thống kê.
10. **Có phép thử độc lập.** Telemetry do chính PEP phát ra cần được đối chiếu bằng negative tests tại tài nguyên để phát hiện PEP bị bypass hoặc cấu hình sai.

Các chuẩn như **NIST SP 800-207** định hướng kiến trúc Zero Trust; chúng không tự đưa ra **một bộ ngưỡng phần trăm bắt buộc** cho mọi tổ chức. Các mục tiêu và SLA dưới đây là **minh họa**, phải được tổ chức xác định dựa trên nghiệp vụ, rủi ro và khả năng thực thi.

## 4. Xác định phạm vi: cái gì phải được đo?

Trước tiên cần một **inventory** đủ tốt để mô tả đối tượng. Không nên chỉ lấy danh sách user từ IdP rồi mặc định đó là toàn bộ danh tính.

| Đối tượng | Thuộc tính cần có | Vì sao cần |
|---|---|---|
| **Human identity** | Subject ID, loại nhân sự, manager, status, JML event, nhóm/role | Đo cấp quyền và thu hồi theo thay đổi công việc |
| **External identity** | Sponsor, hợp đồng, tenant, hạn quyền, hệ thống được vào | Phát hiện nhà thầu hết hạn vẫn được truy cập |
| **Privileged identity** | Owner, quyền cao, PAM/JIT, phê duyệt, thời hạn | Đo đặc quyền thường trực và thời gian phơi nhiễm |
| **Service/workload identity** | Principal ID, owner team, environment, deployment/job, token/secret, lifecycle | Ngăn bot và principal mồ côi |
| **Entitlement** | Subject, action, resource, scope, nguồn grant, hiệu lực/expiry, approver | Đo quyền được gán, quyền có hiệu lực và quyền thừa |
| **Application/resource** | Owner, criticality, tenant, classification, API paths, access channels | Tính mẫu số cho coverage và kiểm soát chéo tenant |
| **PEP/PDP** | Thành phần, version policy, action/resource được bảo vệ, trạng thái | Đo policy enforcement thật, sai lệch và lỗi |
| **Device/workload posture** | Subject/instance binding, nguồn tín hiệu, observed time, expiry, decision | Đo độ mới và khả năng phản ứng |
| **Access/session** | Subject, phiên hoặc token reference an toàn, action/resource, kết quả, timestamp | Xác nhận quyền thực tế còn hoạt động hay không |

### Mẫu số phải tránh “vòng tròn tự chọn”

Nếu chỉ đếm những ứng dụng **đã tích hợp PEP**, tỷ lệ enforcement coverage sẽ luôn cao dù nhiều hệ thống nhạy cảm chưa tích hợp. Mẫu số nên xuất phát từ **inventory tài nguyên có owner được xác nhận**, không chỉ từ danh sách tài nguyên do công cụ IAM tự báo cáo.

Tương tự, nếu SCIM chỉ hỗ trợ 15/20 ứng dụng, báo cáo phải phân biệt:

- Tỷ lệ thành công **trong số 15 ứng dụng đang tích hợp**;
- Tỷ lệ bao phủ **trên toàn bộ 20 ứng dụng cần kiểm soát**;
- Rủi ro của 5 ứng dụng còn theo quy trình thủ công.

Phải ghi các **ngoại lệ chưa quan sát được** thay vì âm thầm loại khỏi mẫu số.

## 5. Kiến trúc thu thập bằng chứng

~~~mermaid
flowchart TD
    H["HRIS / hợp đồng: JML & effective time"] --> N["Chuẩn hóa sự kiện và identity mapping"]
    I["IdP / SSO / MFA / session"] --> N
    S["SCIM / provisioning / SaaS / local accounts"] --> N
    W["Cloud IAM / service identity / secret store"] --> N
    D["Device & workload posture"] --> N
    P["PDP decisions + policy versions"] --> N
    E["PEP enforcement + API/data outcomes"] --> N
    T["Active probes / authorized negative tests"] --> N

    N --> Q{"Kiểm tra dữ liệu"}
    Q -->|"Thiếu, trùng, sai thứ tự"| R["Quality flags / exception queue"]
    Q -->|"Hợp lệ và có lineage"| A["Event store và metric mart"]
    R --> A
    A --> M["Metric engine: coverage, latency, percentiles, drift"]
    M --> C["Dashboard theo risk / owner / hệ thống"]
    M --> L["SLO alerts + issue workflow"]
    L --> O["Owner xử lý / xác minh / cải tiến"]
    O --> H
    O --> P
~~~

### Dữ liệu phải liên kết được

Cần xác định các khóa:

- **subject_id / principal_id:** danh tính ổn định qua đổi email hoặc tên hiển thị.
- **event_id / correlation_id:** tránh tính trùng và kết nối JML event với provisioning, policy decision và enforcement.
- **application_id / resource_id / scope:** biết hệ thống nào và quyền nào đang đo.
- **policy_id / policy_version:** quyết định đang áp dụng phiên bản nào.
- **effective_at / observed_at / received_at:** tách thời điểm nghiệp vụ, quan sát và tiếp nhận.
- **source_system / evidence_confidence:** không đánh đồng sự kiện nguồn với sự kiện suy diễn.

**Không sử dụng email làm khóa duy nhất**: email có thể đổi, tái sử dụng; service account và khách hàng có thể không có email.

### Nguồn sự thật có thể khác theo trường

HRIS thường là nguồn cho trạng thái nhân sự; IdP là nguồn cho tình trạng tài khoản xác thực; ứng dụng đích là nguồn cho grant cục bộ; backend tài nguyên là nguồn cho owner/tenant và kết quả request; secret manager là nguồn cho credential đã phát hành. Cần có **bảng trách nhiệm thuộc tính** thay vì tuyên bố một hệ thống là nguồn duy nhất cho mọi thứ.

## 6. Phân loại bộ chỉ số theo mục tiêu Zero Trust

| Mục tiêu | Leading indicator (tín hiệu sớm) | Outcome / hiệu lực | Câu hỏi kiểm tra |
|---|---|---|---|
| **Verify explicitly** | Coverage xác minh subject, issuer/audience, device/workload context | Request sai điều kiện bị deny ở PEP/API | Bao nhiêu action nhạy cảm được kiểm tra đúng bằng chứng? |
| **Least privilege** | Tỷ lệ grant có scope/owner/expiry, độ phủ JIT | Effective privilege nhỏ, quyền thừa được gỡ | Nếu principal bị chiếm, có thể làm gì? |
| **Assume breach** | Session/revocation controls và test coverage | Lateral-movement probes bị chặn, blast radius giảm | Mất một credential có lan được sang hệ thống khác không? |
| **JML** | Sự kiện xử lý đủ, SCIM/reconciliation coverage | Quyền cũ bị chặn sau Mover/Leaver trong SLA | Bao lâu truy cập trái quyền còn hoạt động? |
| **Policy enforcement** | Policy version coverage, PEP rollout, audit completeness | Deny/obligation thực thi trước side effect | PDP trả Deny có chắc không lộ dữ liệu? |
| **Operations/UX** | Error rate, response time, recovery path | Người hợp lệ truy cập được; false deny giảm | Bảo vệ có gây gián đoạn không cần thiết không? |

Không phải chỉ số nào cũng là **tỷ lệ phần trăm**. Các metric thời gian nên dùng **phân phối và percentiles**; blast radius có thể là **số tài nguyên nhạy cảm reachable**; lỗi cấp quyền có thể là số lượng chưa xử lý theo tuổi và mức rủi ro.

## 7. Đo JML: từ sự kiện nguồn đến quyền hiệu lực

Đối với Joiner, Mover, Leaver, nên đo **end-to-end lifecycle**, không coi SCIM 2xx là đích cuối.

### 7.1. Joiner — thời gian để có đúng quyền

| Metric | Định nghĩa đề xuất | Cách sử dụng |
|---|---|---|
| **Time to authorized access** | Thời gian từ mốc có hiệu lực của Joiner đến khi quyền chuẩn đầu tiên có thể dùng đúng phạm vi | Đo hiệu quả onboarding, xem median/p95 |
| **Joiner provisioning completeness** | Số Joiner đã hoàn tất tất cả tài khoản/quyền bắt buộc ÷ số Joiner đủ điều kiện cần xử lý | Phát hiện bỏ sót hệ thống |
| **Joiner excess-access rate** | Số Joiner nhận quyền vượt baseline được phê duyệt ÷ số Joiner được đánh giá | Ngăn cấp admin vì tiện lợi |
| **Joiner first-access correctness** | Số bộ kiểm thử cho phép đúng action và từ chối ngoài scope ÷ số bộ kiểm thử đã chạy hợp lệ | Chứng minh quyền chuẩn không quá rộng |

**Thời gian tính từ đâu?** Nếu nhân viên bắt đầu hợp đồng vào sáng thứ Hai nhưng HRIS tạo record từ thứ Sáu, cần ghi rõ metric đo **thời điểm có hiệu lực**, **thời điểm sự kiện đến IAM** hay **thời điểm nhân viên đầu tiên cần sử dụng**. Không trộn các mốc vào một phân phối.

### 7.2. Mover — thời gian loại bỏ quyền không còn phù hợp

Mover thường khó hơn Joiner vì hệ thống có thể **cấp quyền mới đúng nhưng vẫn giữ quyền cũ**.

| Metric | Định nghĩa đề xuất | Chú ý |
|---|---|---|
| **Mover revocation latency** | Từ mốc thu hồi quyền cũ có hiệu lực đến lúc quyền cũ không còn dùng được trên mọi đường liên quan đã xác định | Đo data plane, không chỉ group update |
| **Residual entitlements per Mover** | Số grant cũ không còn nhu cầu nhưng vẫn có hiệu lực sau hạn xử lý ÷ số Mover hoặc tổng grant phải gỡ | Ghi rõ cách chuẩn hóa |
| **Role overlap exception rate** | Mover có quyền chồng lấp được phê duyệt, có hạn, có SoD ÷ tổng Mover có chồng lấp | Không mặc định overlap là lỗi nếu có phép |
| **Mover desired–actual drift** | Số quyền sai khác giữa desired và effective permissions sau mốc xử lý | Phải gồm grant trực tiếp và kế thừa |

Thời gian chồng lấp được phê duyệt phải có **scope và expiry**. Khi thống kê “quyền cũ tồn dư”, không xếp ngoại lệ hợp lệ vào lỗi, nhưng vẫn báo **phơi nhiễm đặc quyền được chấp nhận** để quản lý rủi ro.

### 7.3. Leaver — chặn truy cập cuối cùng

| Metric | Định nghĩa đề xuất | Chú ý |
|---|---|---|
| **Leaver identity disable latency** | Từ t0 hiệu lực Leaver đến thời điểm IdP/đích chặn đăng nhập mới | Là chỉ số control plane |
| **Leaver end-to-end revocation latency** | Từ t0 đến thời điểm xác minh không còn action bị cấm nào được phép qua các đường mục tiêu | Bao gồm app session, token, local account, API key |
| **Leaver orphaned access count** | Số session, credential, grant hoặc delegated path còn dùng được sau SLA | Phân theo hệ thống và độ nhạy |
| **Leaver application closure coverage** | Số app mục tiêu có bằng chứng xác nhận đóng quyền ÷ tổng app mục tiêu theo inventory/quan hệ quyền | Tránh bỏ sót SaaS không có SCIM |
| **Emergency offboarding completion** | Sự kiện khẩn cấp có kết quả đạt policy và đủ bằng chứng ÷ số sự kiện khẩn cấp | SLA có thể khác Leaver theo kế hoạch |

**Một Leaver có thể có nhiều tài khoản và token.** Không nên kết thúc đo lường ngay khi IdP ghi disabled; tài khoản cục bộ, key, refresh token, access token JWT tự chứa và bot do người đó quản lý cần được xử lý theo phạm vi và chính sách tương ứng.

## 8. Độ trễ thu hồi: mô hình thời gian và phép đo có thể chứng minh

Đây là một trong những chỉ số quan trọng nhất của Zero Trust IAM.

### 8.1. Các mốc thời gian cần tách riêng

Giả sử quyền customer.export của user An phải ngừng có hiệu lực lúc 09:00.

| Mốc | Ý nghĩa |
|---|---|
| **t0 = 09:00** | Quyền không còn hợp lệ theo sự kiện nguồn có hiệu lực |
| **t1 = 09:01** | IAM nhận event và tính desired entitlement mới |
| **t2 = 09:02** | IdP gỡ group / phát thông báo revoke |
| **t3 = 09:04** | SCIM/ứng dụng đích báo hoàn tất cập nhật grant |
| **t4 = 09:07** | PEP/API xác nhận request với quyền cũ không còn được phép |
| **t5 = 09:08** | Kiểm thử đường phụ bằng token/key/session cũ cũng bị từ chối |

Nếu tập các đường cần thu hồi đã được xác định đầy đủ và t5 là **thời điểm cuối cùng chứng minh mọi đường mục tiêu bị chặn**, độ trễ end-to-end quan sát được là **8 phút**, không phải **2 phút** (từ t0 đến cập nhật IdP).

**Đặt tên chỉ số minh bạch:**

- **Event ingestion lag:** t1 − t0.
- **IdP update lag:** t2 − t0.
- **Provisioning confirmation lag:** t3 − t0.
- **PEP verification lag:** t4 − t0.
- **End-to-end verified revocation lag:** t5 − t0.

### 8.2. Phân biệt thời điểm thực và thời điểm kiểm chứng

Nếu hệ thống chỉ chạy negative probe lúc 09:08, điều đó **chứng minh quyền bị chặn chậm nhất lúc 09:08**. Nó **không chứng minh thời điểm hệ thống thực sự bắt đầu chặn** chính xác là 09:08.

Có thể phát biểu:

- **Last observed allow:** request gần nhất vẫn được cho phép sau thời điểm cần thu hồi (nếu có).
- **First observed deny:** request đầu tiên bị từ chối.
- **Verified cutoff upper bound:** mốc muộn nhất trong các lần thử chứng minh tất cả đường kiểm tra bị chặn.
- **Observation gap:** khoảng giữa các lần quan sát; càng rộng thì ước lượng thời điểm thực càng kém chính xác.

Nếu chỉ có log “SCIM success” mà chưa có probe/data-plane telemetry, trạng thái phải là **unverified**, không gán latency bằng 0.

### 8.3. Định nghĩa SLO theo mức rủi ro

Ví dụ minh họa, **không phải ngưỡng của NIST**:

| Cấp truy cập | Mục tiêu giả định | Cách xác minh |
|---|---|---|
| Đặc quyền production, export dữ liệu nhạy cảm | Thu hồi được kiểm chứng trong một khoảng thời gian rất ngắn do tổ chức phê duyệt | Probe action cụ thể, phiên/token cũ và đường đặc quyền |
| User thông thường, ứng dụng nội bộ ít nhạy cảm | SLA dài hơn phù hợp với phân loại dữ liệu | Event + probe theo phạm vi |
| Tài khoản bên thứ ba/nhà thầu | Không tồn tại quyền sau hết hạn hợp đồng và SLA | Quét inventory, kết quả deprovision và thử truy cập |
| Workload bị quarantine do incident | Mục tiêu khẩn cấp riêng | Thử gọi API, token/secret và đường phụ từ principal bị ảnh hưởng |

Phải có owner chấp nhận SLO, khả năng quan sát và phương án khắc phục khi vượt ngưỡng. **SLO thiếu phép đo từ data plane có thể chỉ là cam kết trên giấy**.

## 9. Cách tính phần trăm, phân vị và backlog

### 9.1. Coverage

Giả sử có 120 endpoint/action được chủ sở hữu phân loại là nhạy cảm. Có 96 action đã có kiểm tra policy thực thi và negative test thành công.

**Verified enforcement coverage = 96 / 120 × 100% = 80%.**

Nếu 10 action khác mới chỉ có policy trong repository nhưng chưa xác nhận PEP chặn, **không được cộng 10 vào tử số verified**. Có thể công bố thêm chỉ số **policy-defined coverage** để theo dõi tiến độ kỹ thuật.

### 9.2. Tỷ lệ sự kiện đạt SLA

Giả sử trong tháng có 50 Leaver thuộc phạm vi, 44 sự kiện đã được xác minh chặn mọi đường mục tiêu trong SLA, 4 sự kiện bị trễ và 2 sự kiện chưa đủ bằng chứng.

**Verified-on-time rate = 44 / 50 × 100% = 88%.**

Hai sự kiện **chưa đủ bằng chứng** không được tính là thành công; có thể báo riêng **evidence completeness = 48 / 50 = 96%** nếu 48 hồ sơ có kết quả đủ để kết luận đạt/trễ. Nên nêu số lượng **unverified** thay vì loại khỏi mẫu số rồi công bố 44/48.

### 9.3. Percentiles thay vì chỉ trung bình

Giả sử năm sự kiện đã xác minh có độ trễ thu hồi: **2, 5, 8, 15, 45 phút**.

- Trung bình = (2 + 5 + 8 + 15 + 45) / 5 = **15 phút**.
- Median/p50 = **8 phút**.
- Với cách tính **nearest-rank**, p95 = giá trị thứ ceil(0,95 × 5) = thứ 5 = **45 phút**.

Các công cụ phân tích có thể dùng **phương pháp nội suy phân vị** khác nhau nên số p95 có thể khác với nearest-rank. Hãy khai báo thuật toán và cỡ mẫu, nhất quán khi so kỳ. Với chỉ 5 mẫu, p95 rất nhạy với từng sự kiện; cần hiển thị **N=5**, không coi như dự báo ổn định.

### 9.4. Backlog và tuổi tồn đọng

Tỷ lệ “95% request SCIM thành công” có thể che giấu **một Leaver quyền admin đã lỗi suốt hai ngày**. Báo cáo nên bổ sung:

- Số lỗi deprovisioning chưa giải quyết, chia theo criticality.
- **Tuổi lỗi lớn nhất** và p95 tuổi lỗi.
- Số lần lỗi được mở lại sau khi tưởng đã hoàn thành.
- Owner, hệ thống đích và **đường truy cập thực tế còn sử dụng được hay không**.

Trong xử lý rủi ro, một ngoại lệ nghiêm trọng chưa chặn có thể đáng quan tâm hơn hàng trăm sự kiện thành công.

## 10. Đo Verify explicitly

Nguyên tắc **Verify explicitly** nhấn mạnh đánh giá bằng chứng theo danh tính, phiên, hành động, tài nguyên và ngữ cảnh phù hợp. Chỉ số không thể chỉ đếm số lần đăng nhập.

| Metric | Gợi ý tử số/mẫu số hoặc đơn vị | Đọc kết quả như thế nào? |
|---|---|---|
| **Protected request coverage** | Request thuộc tập action nhạy cảm đi qua PEP thực thi đúng ÷ tổng request nhạy cảm quan sát được | Chưa thấy traffic ở đường bypass thì phải đo coverage từ inventory/test |
| **Resource-level AuthZ coverage** | Endpoint nhạy cảm có kiểm tra object/tenant/owner đã kiểm thử ÷ tổng endpoint nhạy cảm | Chống lỗi BOLA/IDOR, cross-tenant |
| **Token validation correctness** | Bộ test issuer/audience/expiry/scope sai được deny ÷ tổng bộ test hợp lệ | Không đánh đồng “token được parse” với xác minh đúng |
| **Fresh authentication requirement coverage** | Action cần step-up có chính sách và phép thử hoàn chỉnh ÷ tổng action cần step-up | Không đo chất lượng bằng số thông báo MFA |
| **Session/posture freshness** | Độ tuổi evidence lúc decision, phân theo action và nguồn | Đo request dùng dữ liệu quá cũ |
| **Decision evidence completeness** | Quyết định có đủ trường subject/action/resource/policy/time ÷ tổng quyết định thuộc phạm vi | Hỗ trợ điều tra và kiểm toán |

**Điểm phân biệt:** user có MFA mạnh vẫn không được xem hóa đơn của tenant khác. Vì vậy một chương trình có **MFA adoption cao** nhưng kiểm tra ở cấp tài nguyên yếu vẫn chưa thực thi Verify explicitly đầy đủ.

### Định nghĩa request hợp lệ trong mẫu đo

Cần lọc hoặc phân loại rõ:

- Tài nguyên công khai không cần đăng nhập;
- Health check/monitoring nội bộ có principal riêng;
- Thao tác đọc không nhạy cảm và export/approve/admin có rủi ro cao;
- Retry/duplicate request và request từ job nền;
- API chưa phát hành hoặc được gọi rất ít.

Nếu chỉ dùng traffic từng xảy ra làm mẫu số, một endpoint admin ít được dùng có thể biến mất khỏi báo cáo dù rủi ro rất cao. Nên có **coverage theo inventory** và **coverage theo traffic** song song.

## 11. Đo Least privilege: quyền thực tế nhỏ tới đâu?

Nguyên tắc **Least privilege** cần được đo trên **effective permissions**, không chỉ tên role được gán.

### Bộ chỉ số đề xuất

| Metric | Định nghĩa thực dụng | Cần tránh |
|---|---|---|
| **Standing privileged principal count** | Số human/workload principal có quyền cao thường trực trong kỳ | Không lấy số group admin trực tiếp rồi bỏ qua quyền kế thừa |
| **Privileged exposure time** | Tổng thời gian mỗi principal có thể dùng quyền cao theo phạm vi đã định | Không chỉ đếm phiên PAM được tạo |
| **JIT-covered privileged actions** | Số hành động/phiên đặc quyền diễn ra qua luồng JIT đã kiểm chứng ÷ tổng hành động/phiên đặc quyền thuộc phạm vi | Không bỏ qua thao tác admin bằng account khác |
| **Time-bound grant coverage** | Grant ngoại lệ có expiry/owner/approval đầy đủ ÷ tổng grant ngoại lệ | Expiry được lưu nhưng không thực thi vẫn chưa đạt |
| **Unused/high-risk grant backlog** | Số grant ít dùng/rủi ro cao đã được phân loại cần rà soát | “Không dùng” không tự chứng minh phải xóa |
| **SoD violation count** | Sự kiện hoặc trạng thái vi phạm quy tắc phân tách nhiệm vụ | Phải xét request và resource cụ thể |
| **Cross-tenant denied-path success** | Số phép thử ngoài tenant bị chặn ÷ tổng phép thử hợp lệ | Không dùng tỷ lệ deny traffic ngẫu nhiên thay test |

### Đo quyền được gán khác quyền có hiệu lực

Một account có thể bị gỡ khỏi group admin ở IdP, nhưng còn:

- Grant trực tiếp trong SaaS;
- Role kế thừa qua nhóm lồng nhau;
- Cloud permission qua resource policy hoặc assume-role;
- Token/chứng chỉ được phát trước khi role bị thu hồi;
- DB account local không dùng SSO.

Nếu chỉ đo **assigned permissions** trong IdP, biểu đồ có thể đẹp lên trong khi **effective privilege** gần như không đổi.

### Ước lượng thời gian phơi nhiễm

Một kỹ sư được cấp quyền admin thường trực 30 ngày có khoảng thời gian quyền có thể sử dụng rất lớn so với quyền JIT trong vài phiên mỗi phiên 20 phút. Tuy nhiên, không nên tuyên bố “giảm rủi ro 99%” chỉ từ tỷ lệ giảm thời gian: rủi ro còn phụ thuộc **scope, mức nhạy cảm, khả năng token bị dùng sau TTL và đường truy cập phụ**.

Có thể biểu diễn một chỉ số nội bộ:

**Privileged exposure = tổng (thời lượng grant hiệu lực × trọng số phân loại tài nguyên)**.

Đây là **proxy do tổ chức tự định nghĩa**; trọng số không phải hằng số chuẩn và cần được tài liệu hóa. Báo cáo thêm các số gốc để tránh che dấu tình huống một grant đặc biệt nguy hiểm.

## 12. Đo Assume breach: nếu một danh tính bị chiếm, chuyện gì xảy ra?

Zero Trust không thể chứng minh “không bao giờ bị xâm nhập”. Nhưng có thể kiểm tra **những đường nào còn mở** nếu một chủ thể hoặc workload bị chiếm.

### Đo phạm vi ảnh hưởng có điều kiện

Hãy mô hình hóa hệ thống thành đồ thị:

- **Node:** principal, service, API, database, cloud account, tenant hoặc dữ liệu.
- **Edge:** một kết nối hay action thực sự có thể được thực hiện từ node nguồn tới node đích.
- **Edge properties:** identity, permission, action, scope, time window, policy version và bằng chứng thực thi.
- **Criticality:** phân loại tài nguyên ảnh hưởng kinh doanh/bảo mật.

Với một principal giả định bị chiếm, đặt câu hỏi:

1. Nó kết nối được tới bao nhiêu dịch vụ?
2. Sau khi kết nối, nó được thực hiện bao nhiêu hành động nhạy cảm?
3. Nó có thể phát hành credential mới, assume-role hoặc thay policy không?
4. Nó có đường sang tenant khác hoặc management plane không?
5. Khi phát hiện bất thường, bao lâu các đường đó bị chặn?

**Blast-radius proxy** có thể là số tài nguyên nhạy cảm reachable trong mô hình đã xác minh, hoặc tổng trọng số rủi ro của chúng. Đây là thước đo **khả năng tiếp cận theo mô hình**, không phải lượng thiệt hại thật nếu tấn công xảy ra.

### Chỉ số cho containment

| Metric | Định nghĩa | Cách chứng minh |
|---|---|---|
| **Lateral movement deny effectiveness** | Phép thử di chuyển ngang ngoài whitelist bị chặn ÷ tổng phép thử hợp lệ | Probe ở network + service identity + API |
| **Blast-radius reachable resource count** | Số tài nguyên nhạy cảm một principal có thể truy cập theo mô hình và kiểm thử | Flow mapping + quyền hiệu lực + negative tests |
| **Event-to-containment latency** | Từ thời điểm sự kiện cần containment có hiệu lực/được xác nhận đến khi đường truy cập mục tiêu bị chặn | Kết hợp incident events và data-plane probes |
| **Orphaned critical credential count** | Credential/service principal không owner hoặc hết nghiệp vụ nhưng còn có thể dùng | Inventory + kiểm tra đích |
| **Incident re-entry rate** | Trường hợp quyền/credential bị thu hồi nhưng đường truy cập xuất hiện lại | Theo dõi policy/grant mới sau sự cố |
| **Break-glass verification coverage** | Đường break-glass được kiểm thử, có owner, expiry, audit ÷ đường break-glass thuộc phạm vi | Không biến quyền cứu hộ thành admin hằng ngày |

Cần phân biệt **thời gian phát hiện** (MTTD), **thời gian khoanh vùng** (MTTC) và **thời gian khôi phục**. Các mốc khởi đầu/kết thúc phải do quy trình điều tra định nghĩa, tránh so sánh hai đơn vị đang dùng định nghĩa khác nhau.

## 13. Đo policy enforcement, RBAC/ABAC và tính nhất quán

**Policy-as-code** hay một PDP tập trung không tự bảo đảm PEP áp dụng quyết định. Cần đo cả chuỗi.

| Metric | Định nghĩa | Tại sao cần |
|---|---|---|
| **Defined policy coverage** | Action/resource có chính sách được duyệt ÷ tổng action/resource cần chính sách | Mức tiến độ thiết kế |
| **Deployed policy coverage** | PEP mục tiêu xác nhận nhận version đúng ÷ tổng PEP mục tiêu | Mức độ triển khai |
| **Verified enforcement coverage** | Action/resource có phép thử allow/deny đạt tại data plane ÷ tổng thuộc phạm vi | Mức độ bảo vệ đã chứng minh |
| **Policy-version skew** | PEP còn dùng version không được chấp nhận, theo số lượng và tuổi | Nguy cơ triển khai không đồng nhất |
| **Deny enforcement correctness** | Phép thử PDP Deny dẫn tới không có side effect ÷ tổng trường hợp hợp lệ | Phát hiện PEP bỏ qua quyết định |
| **Obligation completion rate** | Permit kèm obligation được thực hiện đầy đủ ÷ tổng Permit có nghĩa vụ | Tránh trả PII chưa mask/giới hạn |
| **Policy evaluation error rate** | Quyết định lỗi, thiếu thuộc tính, timeout ÷ tổng quyết định thuộc phạm vi | Đo độ tin cậy của dịch vụ policy |
| **Policy change regression rate** | Bản phát hành gây false allow/false deny hoặc bypass ÷ số bản phát hành đã kiểm chứng | Quản trị thay đổi và hồi quy |

### Đo lỗi phân quyền cần đi đến dữ liệu

Ví dụ PDP trả **Deny** cho request invoice.read thuộc tenant B. Nếu API vẫn trả dữ liệu, việc log một bản ghi Deny không làm sự cố biến mất. Negative test phải xác nhận:

- HTTP/API outcome phù hợp;
- Không trả dữ liệu ngoài phạm vi;
- Không có thay đổi trạng thái bất hợp pháp;
- Không có đường phụ qua export worker, signed URL, GraphQL resolver hoặc database account.

Ngược lại, PDP trả **Permit** nhưng obligation bắt buộc là mask trường dữ liệu nhạy cảm thì **chỉ tính pass khi ứng dụng thực hiện mask**.

### Một số metric theo RBAC/ABAC

- Role có **owner, purpose, action set, scope, review date** rõ ràng ÷ tổng role thuộc phạm vi.
- Action nhạy cảm được bảo vệ bởi điều kiện **subject + resource + tenant + context** đã kiểm thử.
- Số trường hợp role explosion hoặc grant ngoại lệ tích lũy dẫn đến quyền khó giải thích.
- Số thay đổi ABAC thuộc tính sai nguồn hoặc stale dẫn đến allow/deny không mong muốn.

Việc có rất nhiều rule ABAC không chứng minh chính sách tốt. Chỉ số đúng cần xem **coverage, tính đúng, hiệu năng và khả năng giải thích**.

## 14. Đo xác thực liên tục, phiên và posture

### 14.1. Xác thực và đánh giá lại liên tục

| Metric | Cách đo | Nguy cơ diễn giải sai |
|---|---|---|
| **Phishing-resistant auth coverage** | Phiên/tài khoản thuộc phạm vi có bằng chứng phương thức xác thực đáp ứng policy ÷ tổng thuộc phạm vi | Phải hiểu cấu hình IdP và ngữ nghĩa bằng chứng |
| **Step-up coverage** | Action cần mức xác thực cao có cơ chế và test đạt ÷ tổng action cần step-up | Không đếm số lần gửi prompt |
| **Step-up completion/abandonment** | Tỷ lệ hoàn thành hoặc bỏ dở challenge theo action/risk | Tỷ lệ bỏ dở cao có thể do UX hoặc tấn công |
| **Risk-event enforcement latency** | Từ event phiên/device risk đến khi action nhạy cảm bị chặn hoặc challenge | Chỉ đo trigger chính sách đã công bố |
| **Stale session authorization rate** | Request dùng session/quyền vượt freshness policy ÷ tổng request thuộc phạm vi | Cần biết source và TTL hợp lệ |
| **False challenge/false deny** | Kết quả yêu cầu lại hoặc deny được xác nhận sai sau điều tra | Đo quyền truy cập hợp lệ bị cản trở |

**“MFA được bật” không đồng nghĩa “MFA chống phishing”, cũng không thay authorization theo tenant**. Mỗi chỉ số chỉ chứng minh điều được định nghĩa.

### 14.2. Device posture

Đo:

- Tỷ lệ thiết bị thuộc diện bắt buộc **managed/compliant** theo owner và nền tảng.
- Tỷ lệ request nhạy cảm sử dụng **posture evidence đủ mới, đúng thiết bị/phiên**.
- Tỷ lệ posture **unknown, stale, noncompliant**.
- Thời gian từ event device lost/high risk đến khi PEP/API chặn action nhạy cảm.
- Thời gian khắc phục false deny và tỷ lệ người dùng bị gián đoạn không đáng có.

**Thiết bị được đăng ký MDM** là một điều kiện triển khai; trạng thái compliant tại thời điểm request cần có nguồn và thời điểm. Bằng chứng ở thiết bị A không được sử dụng để chứng minh request thực sự phát từ thiết bị B.

### 14.3. Workload posture

Đo:

- Service principal có owner/mục đích/environment/expiry ÷ tổng principal.
- Release thuộc phạm vi được xác minh **provenance, image digest, admission policy**.
- Runtime workloads có trạng thái/độ mới posture phù hợp trước khi truy cập tài nguyên nhạy cảm.
- Thời gian từ **quarantine/retire** tới khi credential và action đích bị chặn.
- Số service account dùng chung, thiếu owner, credential dài hạn hoặc quyền production không cần thiết.

**Image ký hợp lệ** không tự chứng minh runtime an toàn. Workload token còn hạn sau quarantine có thể vẫn dùng được nếu resource server không đánh giá lại trạng thái.

## 15. Đo micro-segmentation và các đường truy cập phụ

Micro-segmentation liên quan trực tiếp tới khả năng **Assume breach**: khi một workload bị chiếm, nó có thể tiếp cận đích nào?

| Metric | Tử số/mẫu số hoặc đơn vị | Kiểm chứng |
|---|---|---|
| **Segmentation enforcement coverage** | Workload/tài nguyên nhạy cảm có ranh giới thực thi ÷ tổng thuộc phạm vi | CNI/firewall/mesh test thật |
| **Unnecessary reachability** | Số cạnh nguồn→đích không có nhu cầu/phê duyệt nhưng đang allow | Flow map + owner review |
| **Cross-boundary negative test pass rate** | Luồng bị cấm được chặn ÷ tổng luồng thử hợp lệ | Test network và API tương ứng |
| **Identity-aware connection coverage** | Kết nối nhạy cảm được xác minh peer principal ÷ kết nối nhạy cảm thuộc phạm vi | mTLS/identity PEP telemetry |
| **Orphaned access rule backlog** | Rule không owner, service đã retire, rule tạm quá hạn | So desired với effective rule |
| **Policy rollout drift** | Điểm thực thi dùng cấu hình không đúng phiên bản | Kiểm tra effective policy, không chỉ repository |

**Lưu ý Kubernetes:** chỉ đếm số đối tượng NetworkPolicy không xác nhận CNI thực thi, cũng không tính được rule cộng dồn cho phép nguồn rộng hơn mong muốn. Phải chạy **positive và negative connection tests**, kiểm tra policy hiệu lực và AuthZ ở đích.

Không nên so trực tiếp số gói bị chặn giữa hai môi trường có khối lượng traffic khác nhau mà không chuẩn hóa. Một ngày nhiều Deny có thể do attacker, health check lỗi hoặc test tự động tăng; cần phân loại.

## 16. Từ log sang metric: hợp đồng dữ liệu

Các trường sau giúp tránh việc tính toán dựa vào event mơ hồ:

| Field | Kiểu/ý nghĩa | Lưu ý đo lường |
|---|---|---|
| event_id | ID duy nhất của sự kiện nguồn | Dedupe theo id + nguồn/phiên bản nếu cần |
| event_type | jml_effective, grant_revoked, pep_denied, probe_result... | Danh mục chuẩn và version schema |
| subject_id/principal_id | Danh tính ổn định | Không dùng email duy nhất |
| actor_id | Người/tiến trình gây ra thay đổi nếu khác subject | Phân biệt requester và service account |
| resource_id/application_id | Đích/tài nguyên có owner | Mapping thống nhất giữa các hệ thống |
| action/entitlement_id | Hành động hoặc quyền cần chặn | Không gộp mọi quyền thành “access” |
| tenant/scope | Phạm vi truy cập | Không lưu dữ liệu nhạy cảm hơn mức cần |
| effective_at | Mốc nghiệp vụ có hiệu lực | Phân biệt planned và emergency |
| observed_at | Thời điểm nguồn ghi nhận trạng thái | Khác received_at khi có network delay |
| received_at | Thời điểm pipeline nhận event | Đo ingestion lag |
| decision/policy_version | Kết quả PDP và rule áp dụng | Cần đối chiếu enforcement outcome |
| enforcement_outcome | blocked, allowed, obligation_applied | Không tự đồng nhất với PDP decision |
| evidence_source/quality | Nguồn và cờ độ tin cậy | Phân biệt verified, inferred, missing |
| correlation_id | Liên kết JML, SCIM, PEP, probe, incident | Tránh đo lệch luồng |

### JSON minh họa

~~~json
{
  "event_id": "evt-20261123-1742",
  "event_type": "authorization_enforcement",
  "timestamp": "2026-11-23T09:08:02Z",
  "correlation_id": "jml-req-204",
  "subject_id": "usr-204",
  "application_id": "crm",
  "resource_id": "customer-dataset",
  "action": "customer.export",
  "scope": "tenant-A",
  "lifecycle_event_id": "mover-981",
  "lifecycle_effective_at": "2026-11-23T09:00:00Z",
  "subject_state_version": 18,
  "policy_id": "crm.export",
  "policy_version": 12,
  "decision": "deny",
  "enforcement_outcome": "blocked",
  "reason_code": "ROLE_REVOKED",
  "evidence_source": "crm-api-pep",
  "evidence_quality": "runtime_observed"
}
~~~

Đây là **schema minh họa**, không phải định dạng bắt buộc. Không lưu **access token, refresh token, session cookie, private key, mật khẩu, toàn bộ PII** trong audit chỉ để tính metric.

### Quan hệ giữa event và kết quả

Một event Leaver có thể sinh:

- Một thay đổi trạng thái IdP;
- Nhiều yêu cầu SCIM;
- Nhiều bản ghi revoke token/key;
- Nhiều quyết định PEP ở từng ứng dụng;
- Nhiều negative probes và audit xác nhận.

Đừng tính mỗi bản ghi thành một Leaver mới. **Cần quy tắc correlation một-nhiều** và định nghĩa khi nào một sự kiện coi là hoàn tất. Nếu chưa tìm thấy bằng chứng của một đích thì trạng thái là **pending/unverified**, không tự coi đã thành công.

## 17. Ví dụ SQL cho báo cáo cấp quyền và thu hồi

Giả sử hệ thống phân tích có bảng chuẩn hóa:

~~~sql
-- Ví dụ schema logic, không tự tạo bảng trong hệ thống thật.
-- jml_events: lifecycle_event_id, subject_id, event_type,
--             effective_at, risk_tier
-- access_revocation_checks: lifecycle_event_id, application_id,
--             required_scope, verified_denied_at, evidence_quality
-- required_revocations: lifecycle_event_id, application_id,
--             required_scope
~~~

Để tính phần trăm các **đường bắt buộc** đã xác minh chặn trong một khoảng thời gian, cần giữ cả những đường chưa có bằng chứng. Ví dụ PostgreSQL mang tính minh họa:

~~~sql
SELECT
  date_trunc('day', j.effective_at) AS event_day,
  COUNT(*) AS required_paths,
  COUNT(*) FILTER (
    WHERE c.verified_denied_at IS NOT NULL
      AND c.verified_denied_at >= j.effective_at
      AND c.evidence_quality = 'runtime_observed'
  ) AS verified_paths,
  ROUND(
    100.0 * COUNT(*) FILTER (
      WHERE c.verified_denied_at IS NOT NULL
        AND c.verified_denied_at >= j.effective_at
        AND c.evidence_quality = 'runtime_observed'
    ) / NULLIF(COUNT(*), 0),
    2
  ) AS verified_percent
FROM required_revocations r
JOIN jml_events j
  ON j.lifecycle_event_id = r.lifecycle_event_id
LEFT JOIN access_revocation_checks c
  ON c.lifecycle_event_id = r.lifecycle_event_id
 AND c.application_id = r.application_id
 AND c.required_scope = r.required_scope
WHERE j.event_type IN ('mover', 'leaver')
GROUP BY 1
ORDER BY 1;
~~~

**Giả định quan trọng:** truy vấn trên chỉ đúng khi mỗi đường bắt buộc có **tối đa một bản ghi xác nhận cuối cùng** trong bảng checks và mỗi required_revocations là duy nhất theo khóa nghiệp vụ. Nếu có nhiều probe, phải tạo bảng tổng hợp/CTE lấy trạng thái xác minh hợp lệ cho từng đường trước khi JOIN, tránh đếm trùng.

Truy vấn cho biết **coverage các đường đã xác minh**, chưa phải SLO end-to-end của từng Leaver. Để tính end-to-end latency, cần:

1. Xác định đầy đủ tập đường bắt buộc của một event;
2. Chỉ kết luận hoàn tất nếu **mọi đường** được kiểm chứng;
3. Lấy mốc muộn nhất của các đường đủ điều kiện;
4. Tính chênh lệch từ effective_at;
5. Tách event chưa hoàn tất khỏi phân phối latency và báo backlog riêng.

### SQL minh họa xác định event hoàn tất

~~~sql
WITH path_status AS (
  SELECT
    j.lifecycle_event_id,
    j.effective_at,
    r.application_id,
    r.required_scope,
    MAX(c.verified_denied_at) FILTER (
      WHERE c.evidence_quality = 'runtime_observed'
        AND c.verified_denied_at >= j.effective_at
    ) AS verified_at
  FROM jml_events j
  JOIN required_revocations r
    ON r.lifecycle_event_id = j.lifecycle_event_id
  LEFT JOIN access_revocation_checks c
    ON c.lifecycle_event_id = r.lifecycle_event_id
   AND c.application_id = r.application_id
   AND c.required_scope = r.required_scope
  WHERE j.event_type = 'leaver'
  GROUP BY 1, 2, 3, 4
),
event_status AS (
  SELECT
    lifecycle_event_id,
    MIN(effective_at) AS effective_at,
    COUNT(*) AS required_paths,
    COUNT(verified_at) AS verified_paths,
    MAX(verified_at) AS fully_verified_at
  FROM path_status
  GROUP BY lifecycle_event_id
)
SELECT
  lifecycle_event_id,
  required_paths,
  verified_paths,
  CASE
    WHEN verified_paths = required_paths
    THEN EXTRACT(EPOCH FROM (fully_verified_at - effective_at)) / 60.0
    ELSE NULL
  END AS verified_latency_minutes
FROM event_status;
~~~

**Giới hạn của mẫu SQL:** MAX thời điểm probe trả Deny không tự chứng minh trạng thái bị chặn **liên tục** kể từ đó, và không bảo đảm probe bao phủ mọi đường ngoài danh sách đã kiểm kê. Nếu một đường có nhiều lần allow/deny xen kẽ, phải phân tích **state timeline** và thời điểm chặn ổn định; có thể cần kiểm thử lặp và kết hợp log thực. Các sự kiện chưa hoàn tất là **right-censored/open** và phải được theo dõi, không bỏ khỏi dashboard rủi ro.

## 18. Thiết kế dashboard theo đối tượng quyết định

Một bảng điều khiển chung có thể che các điểm nóng. Nên cho mỗi nhóm người dùng một **câu hỏi ưu tiên**.

### 18.1. Executive / chủ chương trình IAM

Hiển thị một số chỉ số có liên kết tới bằng chứng:

- Tỷ lệ **tài nguyên nhạy cảm đã có verified enforcement**.
- Tỷ lệ JML đạt SLO end-to-end, riêng cho Mover/Leaver.
- Số **quyền cao thường trực**, principal mồ côi và đường kết nối rủi ro cao.
- Xu hướng kiểm thử lateral movement/cross-tenant đã chặn.
- Các ngoại lệ nghiêm trọng quá SLA có owner và thời gian giải quyết.

Không nên che tất cả các chiều vào **một điểm Zero Trust duy nhất**. Một composite score có thể che việc control plane tốt nhưng một API tài chính vẫn bị bypass.

### 18.2. IAM / Platform Operations

- Event JML chờ xử lý, event lỗi và tuổi lỗi;
- SCIM success/apply/verification lag theo từng ứng dụng;
- Drift desired–actual entitlements;
- Refresh token/session/key chưa xử lý sau Leaver;
- Độ mới thuộc tính, cache invalidation và lỗi correlation.

### 18.3. Application owners

- Tỷ lệ endpoint/action nhạy cảm có AuthZ object-level;
- Policy version đang chạy tại từng PEP;
- Deny/permit outcome và obligation thực thi;
- False deny, lỗi PDP và độ trễ authorization;
- Danh sách đường phụ chưa có negative tests.

### 18.4. Security / Incident Response

- Principal quyền cao có đường vào dữ liệu quan trọng;
- Workload/quarantine event chưa được chặn tại data plane;
- Blast-radius simulation và kết quả diễn tập;
- Credential bị nghi lộ nhưng chưa thu hồi;
- Các chênh lệch giữa log IdP, PEP, API và resource effect.

### 18.5. Ví dụ dashboard ở dạng bảng

| KPI giả định | Giá trị minh họa | Mục tiêu minh họa | Đơn vị hành động |
|---|---:|---:|---|
| Verified enforcement coverage — high risk | 80% (96/120) | 100% cho phạm vi đã phê duyệt | Application Security |
| Leaver verified on-time rate | 88% (44/50) | SLO do tổ chức đặt | IAM Operations |
| JML events thiếu bằng chứng | 2 | 0 tồn đọng quá SLA | IAM + app owners |
| Standing production admins | 14 principal | Giảm theo kế hoạch JIT | Platform Security |
| Workload principals thiếu owner | 9 | 0 sau remediation | Service owners |
| Runtime posture stale requests | 2,3% | Theo rủi ro/action | Endpoint/Workload team |
| Policy-version drift | 3 PEP | 0 PEP quá rollout window | Policy Platform |
| False deny đã xác minh | 7 trường hợp | Giảm theo SLO trải nghiệm | App + IAM |

**Tất cả giá trị trên chỉ minh họa**, không phản ánh dữ liệu thực của tổ chức nào. Dashboard thực phải có time window, nguồn, cỡ mẫu, phương pháp đo và liên kết tới issue/runbook.

## 19. SLO, cảnh báo và ưu tiên hành động

Một metric đáng dùng phải giúp quyết định **ai cần làm gì và khi nào**. Có thể thiết kế SLO theo cấu trúc:

~~~yaml
# Cấu hình SLO minh họa; không phải ngưỡng khuyến nghị phổ quát.
objective_id: leaver-privileged-access-revocation
scope:
  identity_type: [human, external]
  risk_tier: critical
  actions: [admin, export, secret_read]
measurement:
  start_event: lifecycle_effective_at
  success_evidence: all_required_paths_verified_denied
  exclude: []
  track_unverified_as: not_met
  window: rolling_30_days
target:
  verified_on_time_percent: 99
  maximum_verified_latency_minutes: 15
  # Các số 99 và 15 chỉ là giá trị giả định để minh họa.
alert:
  pending_near_deadline: true
  failed_or_unverified_after_deadline: page_on_call
owner: iam-operations
escalation: security-incident-response
~~~

Không nên đặt mục tiêu 99% chỉ vì con số đẹp. Đội ngũ phải chứng minh năng lực **phát hiện, chặn và ghi nhận** theo hệ thống thực và cấp rủi ro.

### Cách tránh alert noise

1. **Gắn cảnh báo với mức ảnh hưởng**: một token admin còn hoạt động sau Leaver quan trọng hơn 20 lần retry của quyền ít nhạy cảm.
2. **Nhóm theo nguyên nhân**: nếu SCIM connector lỗi ảnh hưởng 100 user, tạo incident nguyên nhân chung nhưng vẫn giữ từng record để xác minh quyền.
3. **Có owner và thời hạn**: cảnh báo không có người xử lý dễ trở thành backlog mù.
4. **Phân biệt thiếu bằng chứng với xác nhận xâm nhập**: unverified là rủi ro/không chắc chắn, không mặc định coi là attack.
5. **Kiểm tra cảnh báo định kỳ bằng tình huống thử**: nếu sự cố giả lập không tạo alert, metric pipeline chưa đáng tin.

### Ngưỡng cảnh báo đa chiều

Nên phân theo identity type, application criticality, action sensitivity, tenant classification, môi trường production/staging và mức độ có sẵn của evidence. Cùng 10 phút trễ có thể được xem là khác nhau với ứng dụng chỉ xem lịch nghỉ và ứng dụng cấp quyền root.

## 20. Chất lượng dữ liệu, thiên lệch và quyền riêng tư

Một chương trình measurement có thể thất bại dù mọi biểu đồ đều có số nếu **cách thu thập hoặc diễn giải không đúng**.

### 20.1. Chất lượng dữ liệu

| Vấn đề | Ví dụ | Cách xử lý |
|---|---|---|
| Thiếu mẫu số | Chỉ các app đã tích hợp tool xuất hiện trên dashboard | Dùng inventory độc lập, gắn cờ tài nguyên chưa quan sát |
| Sự kiện trùng lặp | SCIM retry gửi 3 lần, tính thành 3 lần hoàn tất | Dedupe theo event_id và khóa idempotency |
| Sai thứ tự | Grant cũ đến sau revoke mới | Version/effective_at, đối soát authoritative state |
| Đồng hồ lệch | Log API chạy nhanh hơn IdP 4 phút | Đồng bộ thời gian, lưu source timestamps và sai số |
| Missingness không ngẫu nhiên | App legacy rủi ro cao không gửi log | Báo riêng coverage và unknown, không bỏ qua |
| Chỉ đo log thành công | Probe Deny không được gửi khi system lỗi | Ghi lỗi quan sát thành trạng thái unverified |
| Trộn đơn vị đo | Phút nghiệp vụ với giờ làm việc, event-count với user-count | Data dictionary và công thức thống nhất |
| Thay đổi schema | Field action đổi tên làm giảm số deny giả tạo | Version schema, regression tests của pipeline |
| Goodhart/gaming | Nhóm giảm reported latency bằng cách chỉ tính SCIM ack | Review độc lập bằng probe ở data plane |

### 20.2. Các nguyên tắc privacy-by-design

- Chỉ lưu **subject ID được quản trị**, không cần bản sao giấy tờ cá nhân, mật khẩu hay token để đo quyền.
- Với phân tích hành vi, ưu tiên **aggregate và phân quyền truy cập**, tránh biến telemetry bảo mật thành theo dõi nhân viên ngoài mục đích đã phê duyệt.
- Mã hóa và phân quyền lưu trữ event; giới hạn khả năng xem từng subject ở dashboard.
- Có **retention** và cơ sở xử lý dữ liệu theo quy định nội bộ/pháp luật áp dụng.
- Khi cần liên kết session, dùng session reference hoặc mã băm phù hợp, không ghi session cookie.
- Chứng minh audit log không thể bị thay đổi tùy ý bởi chính principal có quyền vận hành hệ thống được kiểm toán.

**Báo cáo Zero Trust IAM phải đủ dữ liệu để kiểm toán nhưng không tự tạo kho credential hoặc dữ liệu nhạy cảm mới.**

## 21. Phương pháp kiểm thử để hiệu chuẩn các metric

Đếm log không đủ, cần **active validation** với principal và tài nguyên thử nghiệm được ủy quyền. Mỗi test case phải nêu **input, action, expected decision, expected enforcement outcome và thời điểm**.

| ID | Tình huống | Metric được kiểm tra | Kết quả cần quan sát |
|---|---|---|---|
| T1 | User đúng role, ticket được giao cùng tenant | Verified enforcement coverage | Allow đúng dữ liệu |
| T2 | Cùng user xem ticket tenant khác | Resource-level AuthZ | Deny không lộ dữ liệu |
| T3 | JWT hợp lệ nhưng sai audience | Token validation correctness | Deny |
| T4 | Mover xóa role, token cũ còn hạn | Mover revocation latency | API chặn quyền cũ trong SLA |
| T5 | Leaver nhưng ứng dụng giữ local session | End-to-end Leaver coverage | Session cũ không còn truy cập |
| T6 | SCIM báo success nhưng grant trực tiếp vẫn tồn tại | Desired–actual drift | Đối soát phát hiện, không tính completed |
| T7 | JIT quyền admin hết TTL, kết nối còn mở | JIT expiry enforcement | Action admin tiếp theo bị từ chối |
| T8 | PDP Deny nhưng backend tiếp tục ghi dữ liệu trong bản thử lỗi | Deny enforcement correctness | Test phải FAIL, tạo issue |
| T9 | PDP Permit với nghĩa vụ mask PII | Obligation completion rate | Trường dữ liệu được mask đúng |
| T10 | Device báo lost khi user còn token hợp lệ | Event-to-enforcement latency | Action nhạy cảm bị chặn |
| T11 | Workload bị quarantine với token chưa hết hạn | Workload posture enforcement | API đích từ chối theo policy |
| T12 | Staging workload yêu cầu token production | Workload federation policy | Issuer/subject/environment policy deny |
| T13 | Pod không được phép thử kết nối DB | Segmentation effectiveness | CNI/mesh/DB chặn tương ứng |
| T14 | Một allow-all NetworkPolicy khác còn tồn tại | Effective policy correctness | Test phát hiện bypass |
| T15 | Event grant cũ đến sau revoke mới | State reconciliation correctness | Quyền không được hồi sinh |
| T16 | PDP lỗi khi export nhạy cảm | Fail-safe correctness | Fail closed theo policy |
| T17 | User Leaver có export job đang chờ | Async authorization coverage | Worker không phát hành dữ liệu trái ủy quyền |
| T18 | Workload/service account đã retire nhưng key còn hạn | Credential revocation latency | Đường phụ bị chặn trong SLA |
| T19 | Rollout policy mới không tới một PEP | Policy version consistency | Alert phát hiện version drift |
| T20 | Nhập sai dữ liệu clock/duplicate vào metric pipeline | Measurement data quality | Không báo thành công sai; lỗi được đánh dấu |

### Một vòng kiểm thử end-to-end cho Mover

1. Tạo user thử nghiệm có role Support và quyền customer.export với phạm vi tenant A.
2. Kiểm tra trước khi Mover: **allow đúng scope, deny tenant B**.
3. Phát sự kiện Mover có thời điểm hiệu lực xác định; gỡ quyền Support theo workflow.
4. Giữ lại một access token có thời hạn theo thiết kế thử để xác minh tác động.
5. Thử API export tại các thời điểm theo lịch, ghi **last allow / first deny** và kết quả dữ liệu.
6. Đối soát IdP, SCIM, app grant, policy version, session, token và mọi đường phụ có liên quan.
7. Tính độ trễ đã xác minh và độ thiếu chắc chắn của phép quan sát; gắn evidence quality.
8. Nếu một đường không thể kiểm tra, báo **unknown/unverified**, không tuyên bố thu hồi end-to-end thành công.
9. Lập issue và đo lại sau khi sửa.

Các phép thử phải sử dụng tài khoản và tài nguyên được phê duyệt, không cố truy cập trái phép hệ thống thật.

## 22. Tình huống thực hành: dashboard xanh nhưng quyền vẫn còn mở

### Bối cảnh

Một doanh nghiệp dùng HRIS làm nguồn JML, IdP/SSO để đăng nhập, SCIM đồng bộ CRM và Finance, API Gateway làm PEP, cùng một số workload chạy bằng service account.

Báo cáo tháng:

- “SSO coverage: 100%”.
- “MFA enrollment: 99%”.
- “SCIM success: 98%”.
- “Access review completion: 100%”.
- “Zero Trust score: 96/100”.

Tuy nhiên, sự kiện sau xảy ra:

| Thời điểm | Diễn biến |
|---|---|
| 09:00 | HRIS xác nhận nhân viên Bình chuyển từ Support sang Finance |
| 09:01 | IdP gỡ group Support, thêm Finance |
| 09:02 | Connector CRM nhận yêu cầu SCIM nhưng một tài khoản local vẫn giữ quyền customer.export |
| 09:05 | Bình dùng token CRM phát lúc 08:30, vẫn được export tenant A |
| 09:10 | API Gateway có PDP Deny nhưng export-worker nhận job từ queue và tạo file |
| 09:20 | Link tải file được tạo dưới credential của service account dùng chung |
| 10:00 | Token cũ hết hạn, nhưng link tải và local account chưa được xử lý |
| 11:00 | Auditor phát hiện dashboard không có dữ liệu runtime của export-worker |

### Nhiệm vụ

1. Giải thích vì sao bốn chỉ số ban đầu **không chứng minh** Zero Trust IAM đã bảo vệ được dữ liệu khách hàng.
2. Đề xuất ít nhất **sáu metric** và phân biệt control plane, decision plane, data plane.
3. Với các thời điểm trong bảng, có thể báo cáo chính xác **revocation latency** là bao nhiêu không? Vì sao?
4. Chỉ ra những **đường chưa được bao phủ** trong inventory và negative testing.
5. Thiết kế một cảnh báo có owner/SLO/điều kiện rõ ràng để phát hiện đúng sự cố.
6. Đề xuất kế hoạch cải tiến theo ba giai đoạn có thể kiểm chứng.

### Lời giải tham khảo

**1. Bốn chỉ số chỉ đo quá trình/coverage.** SSO nói về cửa đăng nhập; MFA enrollment không bảo đảm mọi phiên hay hành động được kiểm tra; SCIM success không xác nhận local grant/token cũ; access review completion không chứng minh quyết định đã thực thi. “96/100” không có data dictionary và không phản ánh export-worker bị bypass.

**2. Bộ metric bổ sung:**

- **Control plane:** Mover desired–actual drift; SCM/SCIM application-closure completeness; local account exception backlog.
- **Decision plane:** policy-version consistency; PDP decision evidence completeness; revoked-role decision deny rate trên action mục tiêu.
- **Data plane:** customer.export negative-test pass rate; end-to-end revocation latency; export job actor-authorization coverage; signed URL lifecycle coverage và số artifact phát hành sau mốc thu hồi.

**3. Chưa thể kết luận một con số chính xác.** Từ log cho thấy request vẫn được allow lúc 09:05, export-worker tạo file lúc 09:10 và link tải tồn tại lúc 10:00. Không có bằng chứng rằng **mọi đường** bị chặn sau mốc này. Event phải ở trạng thái **not fully verified / SLA breached** nếu vượt hạn chính sách. Không thể báo latency bằng 2 phút chỉ vì IdP gỡ group lúc 09:01 hoặc SCIM nhận yêu cầu lúc 09:02.

**4. Đường bị bỏ sót:** CRM local grant, JWT còn hạn, việc PEP Deny không được worker tuân thủ, queue authorization, signed URL và service account dùng chung. Cần liên kết actor Bình với tác vụ của worker, đồng thời bảo đảm principal của worker chỉ có quyền kỹ thuật tối thiểu.

**5. Cảnh báo:** Khi Mover thu hồi customer.export, tạo tập tài nguyên/đường bắt buộc và deadline theo risk policy; nếu bất cứ đường nào còn allow hoặc chưa kiểm chứng khi gần/vượt deadline, gửi alert cho IAM Operations và Application Owner, escalation tới Security nếu hành động nhạy cảm còn sử dụng được. Alert phải giữ event ID, mốc hiệu lực, affected paths và evidence.

**6. Ba giai đoạn cải tiến:**

- **Đo đúng:** hoàn chỉnh inventory và event correlation; bổ sung runtime logs/probes cho CRM, worker, storage; không loại bỏ unverified.
- **Chặn đúng:** kiểm quyền tại enqueue và trước worker side effect, thu hồi local grant và token/phiên, quản lý URL và tách service account.
- **Xác minh liên tục:** regression tests T4/T6/T8/T17, dashboard end-to-end latency, policy drift, false deny và SLO alert theo criticality.

### Câu hỏi mở rộng

Một ứng dụng SaaS không cung cấp khả năng kiểm tra token/phiên còn hiệu lực ngay tại API. Hãy phân biệt **“đích đã xác nhận deprovision”** với **“không còn khả năng sử dụng phiên cũ”**, đề xuất kiểm soát bù (ví dụ TTL, proxy, chặn kết nối hoặc quy trình chủ động phù hợp) và nêu cách báo cáo **giới hạn quan sát** thay vì hứa chắc không còn rủi ro.

## 23. Kế hoạch xây dựng chương trình đo lường theo giai đoạn

Không cần đợi một data platform hoàn hảo mới bắt đầu, nhưng phải chọn **ít metric chất lượng cao, có owner và bằng chứng**.

### Giai đoạn A — Chuẩn hóa danh tính và phạm vi

- Xây inventory người dùng, nhà thầu, privileged principal, workload, ứng dụng và action nhạy cảm.
- Ghi owner và phân loại rủi ro.
- Thiết lập data dictionary cho JML effective time, entitlement, policy version và kết quả enforcement.
- Xác định tập đường bắt buộc cho từng loại Leaver/Mover.
- Chọn vài ứng dụng critical để làm thí điểm.

**Điều kiện hoàn tất:** có thể đếm được cả những tài nguyên **chưa tích hợp và chưa quan sát được**.

### Giai đoạn B — Liên kết sự kiện và đo từ data plane

- Kết nối HRIS/JML, IdP/SSO, SCIM, IAM role, PEP/PDP và audit API.
- Xây correlation trên subject, event, action/resource và policy version.
- Bổ sung negative probes theo tài nguyên/đường truy cập.
- Tách observed deny, provisioned, inferred và unverified.
- Công bố median/p95/p99 latency **kèm N**, backlog và các event chưa hoàn tất.

**Điều kiện hoàn tất:** có thể giải thích một Leaver đã được chặn ra sao, tại những hệ thống nào và mốc bằng chứng nào.

### Giai đoạn C — Dùng số liệu để điều khiển cải tiến

- Thiết lập SLO theo criticality và on-call owner.
- Giảm grant thường trực, đưa quyền cao sang JIT khi phù hợp.
- Giảm decision/policy drift, sửa bypass ở worker và data layer.
- Cải thiện runtime posture và event-to-enforcement latency.
- Kiểm thử biến cố SCIM lỗi, token cũ, rủi ro thiết bị/workload và policy outage.
- Đo cả false deny, UX remediation và hiệu suất của hệ thống.

**Điều kiện hoàn tất:** không chỉ biết điểm yếu mà chứng minh được **trước/sau thay đổi** có giảm quyền tồn dư, bề mặt tấn công và lỗi chặn nhầm, với cách đo không đổi.

## 24. Checklist và tài liệu tham khảo

### Checklist thiết kế metric

- [ ] Mỗi metric có mô tả, owner, phân loại rủi ro, tử số/mẫu số, đơn vị và cửa sổ thời gian.
- [ ] Tài nguyên/ứng dụng/identity chưa tích hợp được đưa vào coverage hoặc ngoại lệ có thể thấy.
- [ ] JML dùng mốc hiệu lực đúng, phân biệt ingestion, provision, enforcement và verification.
- [ ] Các trường hợp chưa có đủ bằng chứng được đánh dấu **unverified**, không tính là thành công.
- [ ] Percentiles được công bố cùng cỡ mẫu và phương pháp tính.
- [ ] Effective permissions bao gồm role kế thừa, grant trực tiếp và quyền ở ứng dụng đích.
- [ ] Theo dõi token, local session, API key, service account, workload và đường truy cập phụ.
- [ ] Verify explicitly được đo bằng authorization đúng cấp object/action/tenant, không chỉ MFA.
- [ ] Least privilege đo quyền cao thường trực, JIT, scope và quyền hết hạn thực tế.
- [ ] Assume breach có negative tests, reachability và containment latency.
- [ ] PEP/PDP đo decision và **enforcement outcome**, kể cả obligation, bypass, cache/version drift.
- [ ] SCIM success rate được phân biệt với application closure và data-plane revocation.
- [ ] Device/workload posture có nguồn, thời điểm, freshness và phản ứng khi thay đổi.
- [ ] Dashboard có alert gắn owner/SLO, không bị che bởi composite score.
- [ ] Data pipeline xử lý duplicate, out-of-order, clock skew, schema change và missingness.
- [ ] Audit không lưu password, token, private key hay dữ liệu cá nhân không cần thiết.
- [ ] Có kiểm thử định kỳ và diễn tập lỗi nhằm **hiệu chuẩn độ tin cậy của metric**.
- [ ] Từng chỉ số có hành động cải tiến và bằng chứng đánh giá lại sau khi sửa.

### Từ khóa

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Control plane** | Nơi thay đổi trạng thái danh tính, entitlement, phiên bản chính sách và provisioning |
| **Data plane** | Nơi request thực tế được cho phép hoặc từ chối trên tài nguyên |
| **PEP/PDP** | Điểm thực thi chính sách / thành phần quyết định theo chính sách |
| **Verified enforcement** | Có bằng chứng rằng điểm truy cập thật sự thực thi allow/deny và nghĩa vụ |
| **Effective permission** | Quyền có hiệu lực sau khi xét kế thừa, grant trực tiếp, policy và điều kiện |
| **JML latency** | Thời gian từ Joiner/Mover/Leaver tới trạng thái truy cập mong muốn được xác nhận |
| **Revocation latency** | Thời gian tới khi quyền phải thu hồi thực sự không còn sử dụng được trong phạm vi xác định |
| **Residual access** | Quyền/phiên/token/key còn dùng được dù nhu cầu hoặc ủy quyền đã chấm dứt |
| **SLO / SLA** | Mục tiêu mức dịch vụ / cam kết hoặc thỏa thuận mức dịch vụ |
| **p50/p95/p99** | Phân vị của phân phối độ trễ hoặc một đại lượng; cần công bố phương pháp và mẫu |
| **Drift** | Sai lệch giữa quyền/chính sách mong muốn và trạng thái thực tế |
| **Unknown/unverified** | Thiếu bằng chứng để kết luận thành công hoặc thất bại |
| **Negative test** | Phép thử yêu cầu bị cấm nhằm xác minh hệ thống thực sự từ chối |
| **Blast radius** | Phạm vi tác động tiềm năng nếu một danh tính/credential bị xâm nhập |
| **Right-censored** | Sự kiện chưa quan sát được thời điểm hoàn tất trong khoảng theo dõi |
| **Data dictionary** | Bộ định nghĩa chuẩn về field, đơn vị, cách tính, nguồn và trách nhiệm |

### Tài liệu tham khảo để học sâu

- **NIST SP 800-207 — Zero Trust Architecture:** nền tảng cho xác minh theo chính sách, hạn chế tin cậy ngầm, PEP/PDP và giám sát quyết định truy cập.
- **NIST SP 800-53 — Security and Privacy Controls:** tham khảo các nhóm kiểm soát AC, IA, AU, CM, IR và hoạt động rà soát/kiểm toán.
- **NIST SP 800-63 — Digital Identity Guidelines:** khái niệm xác minh danh tính, xác thực, phiên và mức bảo đảm.
- **RFC 7643 / RFC 7644 — SCIM:** mô hình và giao thức đồng bộ user/group; cần phân biệt provisioning với authorization tại request.
- **OpenID Connect và OAuth 2.0:** danh tính, access token, resource server, audience/scope và những giới hạn của token.
- **OWASP API Security Top 10:** các lỗi ở cấp đối tượng/chức năng và kiểm tra end-to-end.
- **Tài liệu kiểm toán/observability của IdP, cloud IAM, policy engine, service mesh và hệ thống API được sử dụng:** để xác định nguồn event, khả năng token revocation và semantics kết quả thực tế.

**Điểm cần nhớ:** Đo lường Zero Trust IAM có ý nghĩa khi chuyển từ báo cáo **“chúng ta đã cấp, đồng bộ hoặc khai báo policy”** sang bằng chứng **“đúng danh tính chỉ thực hiện được đúng hành động trên đúng tài nguyên, và khi quyền/ngữ cảnh thay đổi thì truy cập trái chính sách bị chặn trong thời hạn xác định”**. Hệ đo lường phải nêu được phạm vi quan sát, độ trễ, ngoại lệ, hiệu lực thực tế và giới hạn chưa thể chứng minh — đó là nền tảng để giảm quyền truy cập tồn dư qua toàn bộ vòng đời Joiner–Mover–Leaver.
