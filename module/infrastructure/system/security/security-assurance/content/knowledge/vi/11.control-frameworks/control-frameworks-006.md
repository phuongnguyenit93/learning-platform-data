# Control frequency – Tần suất thực thi và kiểm chứng security controls

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **control frequency** là gì và phân biệt tần suất **thực thi control**, **giám sát**, **kiểm thử hiệu lực**, **thu thập bằng chứng** và **review/phê duyệt**.
- Nhận diện các mô hình tần suất: **liên tục**, **mỗi giao dịch/sự kiện**, **theo thay đổi**, **định kỳ**, **kết hợp** và **kích hoạt theo rủi ro**.
- Xây dựng lịch control dựa trên mục tiêu bảo mật, mức rủi ro, tốc độ thay đổi, khả năng xảy ra sai lệch, hậu quả và yêu cầu của tổ chức.
- Đưa ra **tiêu chí đánh giá có thể kiểm chứng**: phạm vi, chu kỳ, hạn hoàn tất, bằng chứng, điều kiện PASS/FAIL/INCONCLUSIVE, xử lý bỏ lỡ, người chịu trách nhiệm và trigger tái đánh giá.
- Liên kết tần suất trong **control framework** với security requirements, kiểm thử, audit, finding, remediation và security assurance liên tục.
- Áp dụng ví dụ thực tế cho ứng dụng Java/Spring Boot, IAM, logging, CI/CD, backup/restore và kiểm tra trạng thái bằng chứng.

## 1. Control frequency là gì?

Trong một **control framework**, control frequency mô tả **khi nào và với nhịp độ nào hoạt động kiểm soát được yêu cầu diễn ra**. Có control cần được thực thi ở **mọi request**; có control gắn với **mỗi thay đổi production**; có hoạt động đánh giá lặp lại theo **ngày, tháng, quý hoặc năm**; và có kiểm tra phải thực hiện ngay khi xuất hiện sự kiện đặc biệt.

Một mô tả đúng phải chỉ ra **đối tượng và hành động**. Câu “security review: quarterly” chưa cho biết:

- Review cái gì: phân quyền privileged account, cấu hình firewall hay toàn bộ rủi ro dịch vụ?
- Review theo **lịch** hay sau **mỗi thay đổi trọng yếu**?
- Ai thực hiện, ai duyệt, cửa sổ bắt đầu/kết thúc là gì?
- Dựa trên dữ liệu và danh sách tài sản nào? Có bao phủ tài khoản mới phát sinh giữa hai kỳ không?
- Hoàn thành và kiểm chứng bằng bằng chứng nào? Nếu không có kết quả hoặc trễ hạn, trạng thái ra sao?

**Control frequency không phải bằng chứng rằng control đã hoạt động.** Một dòng trong policy ghi “review mỗi quý” chỉ nêu **yêu cầu**; để chứng minh hoạt động thật cần có population, chứng cứ review, kết quả, người thực hiện, thời điểm, phát hiện và hành động xử lý.

Trong module **SECURITY_SECURITY_ASSURANCE**, frequency giúp điều phối một chương trình đánh giá có bằng chứng: từ **phân tích rủi ro → yêu cầu → security controls → kiểm thử → audit → findings → remediation/retest**. Frequency kém phù hợp có thể khiến control thiết kế tốt nhưng **không hoạt động đủ thường xuyên để ngăn hoặc phát hiện sự kiện gây hại**.

### Ví dụ mở đầu

Một API thanh toán cần kiểm tra quyền xem giao dịch.

- Kiểm tra quyền cấp đối tượng phải chạy **mỗi request** cần bảo vệ.
- Bộ negative tests xác nhận quyền tenant có thể chạy **mỗi pull request/release** và khi thay chính sách authorization.
- Kiểm tra IAM và role mapping thực tế có thể được thực hiện **định kỳ** và **ngay sau thay đổi có tác động**.
- Giám sát hành vi truy cập bị từ chối có thể chạy **liên tục**, trong khi diễn tập phát hiện và phản hồi chạy theo lịch hoặc sau thay đổi detection pipeline.

Không thể chọn một con số chung, ví dụ “hàng tháng”, rồi thay thế bốn hoạt động khác nhau bằng một checkbox.

## 2. Năm loại tần suất cần tách biệt

| Khái niệm | Hỏi điều gì? | Ví dụ | Bằng chứng khác nhau ở đâu? |
| --- | --- | --- | --- |
| **Execution frequency** – tần suất thực thi control | Control phải can thiệp khi nào? | Authorization chạy với **mọi request** tài nguyên | Runtime behavior, negative tests, trace theo giao dịch |
| **Monitoring frequency** – nhịp giám sát | Khi nào hệ thống quan sát lỗi hay thay đổi của control? | Theo dõi trạng thái log collector và alert gần thời gian thực | Telemetry, health, event đến collector, alert |
| **Assessment/test frequency** – tần suất đánh giá hiệu lực | Bao lâu phải xác minh control đang hoạt động đúng? | Kiểm tra quyền từ chối sau mỗi thay đổi IAM và một lịch định kỳ | Test run, population, expected/observed, reviewer |
| **Evidence collection frequency** – nhịp lấy/chốt bằng chứng | Khi nào hiện vật được thu và gắn với phạm vi? | Snapshot quyền định kỳ, lưu test result cho mỗi build | Artifact ID, nguồn, thời điểm, phiên bản, integrity |
| **Governance/review frequency** – chu kỳ xem xét quản trị | Khi nào người có thẩm quyền đánh giá tính đầy đủ, sai lệch và rủi ro? | Chủ hệ thống review quyền đặc quyền theo quý nếu chính sách yêu cầu | Phê duyệt, quyết định giữ/thu hồi, finding, due date |

**Đừng nhầm giám sát liên tục với kiểm thử liên tục.** Một agent chạy 24/7 vẫn có thể bị cấu hình sai, không nhận đủ event hoặc không phát hiện lỗi của chính nó. Cần kiểm thử end-to-end định kỳ hoặc theo thay đổi để chứng minh rằng hoạt động giám sát thực sự bao phủ đường rủi ro.

Tương tự, **gửi báo cáo mỗi ngày** không đồng nghĩa control đã được **thực thi mỗi ngày**. Báo cáo có thể tổng hợp kết quả cũ, thậm chí lặp cùng một evidence đã hết hạn.

### Ba câu hỏi để tránh “compliance giả”

1. **Control có chạy đủ lúc cần chạy không?** Ví dụ authorization không được “chỉ kiểm tra cuối tháng”.
2. **Có cách phát hiện khi control không chạy hoặc mất hiệu lực không?** Ví dụ phát hiện cấu hình alert bị tắt, CI security gate bị bypass.
3. **Có bằng chứng độc lập đủ mới để assessor kết luận không?** Bằng chứng phải gắn đúng môi trường, phiên bản, population và kỳ đánh giá.

## 3. Các mô hình frequency trong thực tế

### 3.1. Continuous – hoạt động liên tục

Control duy trì một khả năng hoặc trạng thái trong suốt thời gian hệ thống hoạt động.

Ví dụ:
- Mã hóa dữ liệu trên đường truyền khi kết nối TLS được thiết lập.
- Firewall/network policy duy trì kiểm soát đường truy cập.
- EDR hoặc hệ thống phát hiện thực hiện thu thập và phân tích sự kiện khi chạy.
- Resource-level authorization thực thi trên mỗi thao tác cần bảo vệ.

Điều kiện cần phân biệt là **được thiết kế luôn bật** và **đã được xác minh luôn có hiệu lực**. Một control ở trạng thái “enabled” trong console không đủ để chứng minh không có đường bypass, không có gap quan sát hoặc drift.

### 3.2. Per transaction/request – với mỗi giao dịch

Control được yêu cầu thực hiện **mỗi lần xuất hiện hành động có rủi ro**:

- Kiểm tra quyền khi đọc/sửa/xóa dữ liệu.
- Xác minh chữ ký hoặc tính hợp lệ của message khi xử lý.
- Kiểm tra schema, giới hạn kích thước hoặc idempotency theo tác vụ.
- Ghi audit event cho mỗi hành động đặc quyền thuộc chính sách.

Tần suất **mỗi request** là đặc tính của control vận hành, nhưng assessor thường **kiểm thử bằng mẫu trường hợp đại diện**, kiểm tra mã/config, giám sát và review để lập luận rằng control được áp dụng trên đường xử lý thật. Không nên nói “đã kiểm thử mọi request từng xảy ra” nếu không có cơ sở.

### 3.3. Per event/change – theo sự kiện

Một số control phải kích hoạt khi một điều kiện xảy ra:

| Sự kiện | Hoạt động control |
| --- | --- |
| Nhân sự nghỉ việc hoặc đổi vai trò | Thu hồi/điều chỉnh quyền theo thời hạn đã duyệt |
| Cấp quyền đặc quyền | Phê duyệt, kiểm tra phạm vi và log hành động cấp |
| Thay IAM, ingress, firewall hoặc cấu hình bí mật | Đánh giá tác động, kiểm tra truy cập được/chặn và lưu evidence |
| Release hoặc thay dependency quan trọng | Security regression, policy/scan và đối chiếu bản deploy |
| Sự cố hoặc phát hiện khai thác | Reassess risk, containment, evidence preservation, khắc phục |
| Restore backup hoặc failover DR | Kiểm tra quyền, tính toàn vẹn, retention và khả năng phát hiện |

**Không thay event-driven control bằng lịch định kỳ** nếu yêu cầu cần phản ứng ngay. Ví dụ thu hồi quyền sau khi nhân viên rời tổ chức không thể chỉ đợi kỳ review hàng quý.

### 3.4. Periodic – theo lịch

Control hoặc hoạt động assurance thực hiện theo khoảng thời gian định nghĩa trước: ngày, tuần, tháng, quý hoặc năm. Những khoảng này phải được mô tả rõ:
- Chu kỳ từ **mốc nào**: lịch tháng/quý, ngày kết thúc lần trước, thời điểm tạo tài sản?
- **Time zone** và ngày hết hạn, đặc biệt với hoạt động xuyên khu vực.
- Cửa sổ thực hiện cho phép và hạn hoàn tất.
- Điều kiện ngày nghỉ/cuối tuần và người dự phòng.
- Cách xử lý tài sản/phát hiện mới hoặc bỏ lỡ kỳ.
- Tiêu chí hoàn thành, phê duyệt và ngày review tiếp theo.

Không nên coi “quarterly” lúc nào cũng là **90 ngày**. Quý lịch, ba tháng sau ngày đánh giá và 90×24 giờ có thể cho các hạn khác nhau; phải viết đúng ý nghĩa chính sách và code theo loại quy tắc.

### 3.5. Hybrid và risk-triggered – kết hợp lịch và trigger

Với control quan trọng, mô hình thường phù hợp hơn là:

> **Đánh giá định kỳ ở một tần suất tối thiểu và đánh giá bổ sung khi có thay đổi/sự kiện làm mất giá trị bằng chứng cũ.**

Ví dụ: kiểm tra các role IAM theo lịch nội bộ đã phê duyệt, nhưng **kiểm tra ngay** khi role được nới quyền, thay trust policy hoặc xuất hiện finding. Nếu chỉ chờ kỳ định kỳ, rủi ro có thể tồn tại nhiều tuần không được phát hiện.

## 4. Framework xác định tần suất ở mức nào?

Một **control framework** đưa ra mục tiêu, cấu trúc, yêu cầu hoặc các câu hỏi kiểm soát; tùy framework và yêu cầu áp dụng, một số control có **tần suất/điều kiện cụ thể**, còn nhiều control cần tổ chức **định nghĩa phương pháp thực hiện và nhịp đánh giá** dựa trên rủi ro.

Không được tự khẳng định “mọi control theo ISO/IEC 27001 phải được test hằng quý” hoặc “mọi control NIST bắt buộc chạy hằng ngày”. Tổ chức phải xét **phiên bản và điều khoản cụ thể** của chuẩn/framework, nghĩa vụ áp dụng, chính sách nội bộ, mục tiêu rủi ro và quyết định kiểm toán/assurance được phê duyệt.

### Một số cách đọc framework cho đúng

| Nguồn định hướng | Đóng góp cho tổ chức | Câu hỏi cần cụ thể hóa |
| --- | --- | --- |
| **ISO/IEC 27001 và bộ control tham chiếu ISO/IEC 27002** | Cấu trúc quản trị ISMS và các chủ đề control để lựa chọn/áp dụng theo rủi ro | Control nào áp dụng, cách triển khai và bằng chứng hiệu lực theo yêu cầu ISMS? |
| **NIST CSF** | Tổ chức kết quả quản lý rủi ro an ninh mạng theo các chức năng/kết quả | Những kết quả nào cần duy trì liên tục, những đánh giá nào diễn ra theo lịch hoặc trigger? |
| **NIST SP 800-53 / 800-53A** | Danh mục control và phương pháp đánh giá hỗ trợ phân loại, kế hoạch, lựa chọn và kiểm tra | Parameter/tần suất nào do tổ chức lựa chọn hoặc do yêu cầu cụ thể quy định, đánh giá gì? |
| **CIS Controls và Safeguards** | Gợi ý những thực hành bảo mật ưu tiên có thể map vào chương trình kiểm soát | Áp dụng ở tài sản nào, tần suất cụ thể theo phiên bản và hồ sơ áp dụng nào? |
| **Chính sách, hợp đồng hoặc nghĩa vụ ngành** | Yêu cầu bắt buộc theo bối cảnh áp dụng | Có hạn cụ thể cho review/đánh giá, lưu evidence hoặc khắc phục không? |

Bảng trên **không thay thế văn bản chuẩn có bản quyền hoặc điều khoản chính thức**. Khi audit, người đánh giá phải dùng đúng phiên bản, scope và điều khoản được tổ chức tuyên bố áp dụng. Frequency do chính sách nội bộ tự đặt phải được đánh dấu **organization-defined**, tránh quy nhầm cho framework bên ngoài.

### Control mapping và một control dùng cho nhiều yêu cầu

Một hoạt động như `IAM-ACCESS-REVIEW` có thể cung cấp bằng chứng cho nhiều yêu cầu quản lý truy cập. Nhưng mỗi yêu cầu có thể có **điều kiện áp dụng** khác nhau. Một test snapshot có thể tái sử dụng làm evidence cho nhiều claim **chỉ khi phạm vi, kỳ, population và tiêu chí đánh giá tương thích**; không nhân đôi số lần control đã vận hành trên dashboard.

## 5. Chọn frequency theo rủi ro và đặc tính control

Không nên bắt đầu bằng câu hỏi “nên chọn weekly hay monthly?” mà nên hỏi **bao lâu một sai lệch có thể tồn tại trước khi gây hậu quả đáng kể, và điều gì có thể làm control mất hiệu lực?**

### Các yếu tố chính

| Yếu tố | Câu hỏi thực hành | Tác động tới frequency |
| --- | --- | --- |
| **Mức độ rủi ro** | Hậu quả và khả năng xảy ra khi control thất bại là gì? | Rủi ro cao thường đòi hỏi kiểm tra/giám sát nhanh hơn hoặc control liên tục hơn |
| **Criticality** | Control này có là lớp chặn chính của kịch bản nghiêm trọng không? | Control trọng yếu cần phát hiện lỗi, đường khôi phục và đánh giá hiệu lực đáng tin |
| **Rate of change** | IAM, code, mạng và dữ liệu thay đổi với nhịp độ nào? | Nhiều thay đổi đòi hỏi event-driven reassessment, không chỉ lịch xa |
| **Exposure** | Internet, mạng nội bộ, tenant, quyền đặc biệt hoặc dữ liệu thật? | Bề mặt phơi lộ cao có thể tăng nhu cầu giám sát và kiểm tra |
| **Failure detectability** | Nếu control tắt, ai biết và sau bao lâu? | Khó phát hiện cần synthetic test, alert health hoặc review bổ sung |
| **Time to harm** | Từ sai lệch tới thiệt hại là giây, giờ hay tháng? | Phản ứng hằng tháng không đủ cho kịch bản có thể gây hại trong phút |
| **Population size** | Có bao nhiêu user, service, tài nguyên, sự kiện hoặc bản ghi? | Cần cân bằng automation, toàn bộ population và sampling |
| **Control independence** | Có phụ thuộc vào cùng IdP/secret/monitoring với control khác? | Phát hiện sự cố chung và thử failover quan trọng hơn số lần tick checklist |
| **Bằng chứng và chi phí** | Thu evidence tốn nguồn lực hay có thể tự động hóa? | Tối ưu cách kiểm tra nhưng không giảm yêu cầu khi chưa được phê duyệt |
| **Yêu cầu bên ngoài** | Có hạn bắt buộc từ quy định/hợp đồng/framework áp dụng? | Không được tùy ý hạ tần suất dưới yêu cầu hợp lệ |

Ví dụ, một rule chặn kết nối storage public **phải có hiệu lực mọi lúc**. Quét cấu hình hàng tuần có thể phát hiện một số sai lệch, nhưng nếu storage có dữ liệu khách hàng nhạy cảm và policy có thể đổi bất kỳ lúc nào, tổ chức có thể cần **preventive policy-as-code hoặc event-driven change detection** thay vì chỉ quét cuối tuần.

### Quy trình chọn frequency có giải trình

1. **Xác định control objective**: hành vi nào cần ngăn, phát hiện hoặc khôi phục?
2. **Mô tả kịch bản rủi ro khi control thất bại**: actor, tài sản, điều kiện, time-to-harm và hậu quả.
3. **Xác định lúc control phải thực thi**: mọi request, mỗi release, mỗi thay đổi quyền, liên tục hay theo lịch.
4. **Xác định dấu hiệu control mất hiệu lực**: drift, lỗi agent, thiếu nguồn log, thay đổi topology, sự cố hoặc bypass.
5. **Chọn frequency kiểm tra và thu evidence**: đủ mới để hỗ trợ quyết định rủi ro và phù hợp yêu cầu áp dụng.
6. **Định nghĩa SLA, grace, owner và escalations**: thế nào là đến hạn, trễ, lỗi, không có bằng chứng.
7. **Kiểm tra nguồn lực, automation và ảnh hưởng production**: chọn cách thử an toàn, tránh làm hỏng dịch vụ.
8. **Được phê duyệt và version** theo quy trình; xem lại frequency sau sự cố, thay đổi quan trọng hoặc bằng chứng mới.

Một đánh giá thay đổi frequency phải có **rationale**. Ví dụ “chuyển IAM review từ quý sang năm vì tiết kiệm thời gian” chưa đủ; cần đánh giá rủi ro, những control tự động đang thay thế và chấp thuận của owner có thẩm quyền.

## 6. Ví dụ ma trận frequency cho nền tảng Java/Spring Boot

**Lưu ý:** các chu kỳ dưới đây **chỉ là ví dụ đào tạo**, không mặc định đáp ứng chuẩn bên ngoài. Tổ chức phải thiết kế theo phiên bản framework, nghĩa vụ, mức độ rủi ro và khả năng vận hành.

| Control / hoạt động | Nhịp thực thi control | Nhịp xác minh/evidence minh họa | Trigger bổ sung |
| --- | --- | --- | --- |
| Authorization theo resource/tenant | **Mỗi request** cần quyền | Negative/positive integration tests trong CI mỗi thay đổi liên quan; runtime kiểm tra theo kế hoạch | Route mới, role/tenant mapping mới, finding |
| Xác minh JWT issuer/audience và chữ ký | Mỗi request được bảo vệ | Security test mỗi thay đổi config/implementation | Xoay khóa, thay IdP, thay token policy |
| Secret scanning trong CI | Mỗi commit/PR hoặc theo pipeline policy | Log kết quả theo từng build; kiểm tra coverage định kỳ | Lộ secret, thay scan rule, repository mới |
| SAST/SCA cho source/dependency | Theo build/policy | Kết quả CI, triage findings; kiểm tra thêm theo lịch phê duyệt | Advisory mới, dependency mới, exploit được biết |
| Review IAM tài khoản đặc quyền | Theo chu kỳ tổ chức quyết định | Biên bản review, danh sách đầy đủ population và quyết định | Quyền mới, nhân sự đổi vai trò, sự cố |
| Provision/deprovision user | **Mỗi sự kiện** joiner/mover/leaver | Event/result audit theo từng case, sample kiểm chứng theo lịch | Thất bại provisioning, quyền tồn đọng |
| Kiểm tra network exposure | Policy áp dụng liên tục | Snapshot/drift detection và test từ vùng mạng đại diện | Ingress/IaC/cloud policy thay đổi |
| Thu thập security logs | Với mỗi sự kiện trong phạm vi | Monitoring ingestion liên tục; synthetic event test định kỳ | Đổi collector/agent/schema, outage |
| Review cảnh báo bảo mật | Theo event, ưu tiên xử lý theo SLA đã duyệt | Alert ticket/timeline, test delivery và on-call | Detection rule mới, sự cố chưa được phát hiện |
| Backup dữ liệu quan trọng | Theo RPO/backup policy | Kết quả mỗi job; restore test theo lịch | Sự cố backup, đổi dữ liệu/storage, DR failover |
| Kiểm tra phục hồi DR | Theo lịch và kịch bản đã duyệt | Rehearsal/đo RTO-RPO + review | Thay topology, incident, failover thật |
| Rà soát rule retention | Theo policy | Job outcome, đối soát dữ liệu hết hạn và review định kỳ | Thêm data store, legal hold, lỗi purge |
| Review ngoại lệ bảo mật | Theo hạn hiệu lực và rủi ro | Quyết định, status control, ngày review/expiry | Incident, control fail, điều kiện ngoại lệ đổi |
| Pentest hoặc manual threat assessment | Theo risk plan hoặc yêu cầu áp dụng | Scope, report, finding và retest | Thay trust boundary, tính năng rủi ro cao |

**Một control có thể cần nhiều nhịp riêng.** Ví dụ log collector thu sự kiện **liên tục**, health monitoring **liên tục**, alert xử lý **theo sự kiện**, nhưng bài thử end-to-end bằng synthetic event có thể có một lịch **định kỳ và theo thay đổi**. Không gộp tất cả thành nhãn “monthly logging control”.

## 7. Định nghĩa lịch, hạn hoàn thành và “quá hạn” rõ ràng

### Các trường cần chốt từ đầu

Một lịch assurance phải nêu:

- **Frequency type:** continuous, per-request, per-event, per-change, periodic hoặc hybrid.
- **Cadence/calendar:** khoảng thời gian hoặc quy tắc lịch; timezone, ngày làm việc/ngày nghỉ nếu áp dụng.
- **Start anchor:** ngày bắt đầu kỳ, sự kiện khởi tạo, lần hoàn thành được xác minh, hoặc một mốc lịch cố định.
- **Due date/time:** thời điểm phải hoàn thành, tính theo rule đã version.
- **Grace/window:** giới hạn thời gian bổ sung được phê duyệt; grace **không đồng nghĩa control vẫn đạt** nếu đã bỏ lỡ yêu cầu thực thi.
- **Owner, backup owner, reviewer:** ai thực hiện, ai xử lý cảnh báo và ai ký xác nhận.
- **Evidence cutoff:** chứng cứ phải bao phủ đến thời điểm nào, từ những nguồn nào.
- **Escalation:** nếu chưa chạy, chạy lỗi, chưa review hoặc gap lớn phải báo ai, theo mức nào.
- **State transition:** PASS/FAIL/INCONCLUSIVE/NOT_RUN/OVERDUE/EXCEPTION phải có định nghĩa nhất quán.

### Một ví dụ về kiểm tra định kỳ

Giả sử policy nội bộ yêu cầu review IAM **mỗi ba tháng lịch**, theo kỳ kết thúc ngày cuối mỗi quý; report có thể hoàn thành trong **cửa sổ kiểm toán được phê duyệt**. Khi đó:

- Population cần là danh sách tài khoản/quyền tương ứng với **kỳ được đánh giá**, không phải file cũ tải lại.
- Reviewer ghi các quyền được **giữ/thu hồi/cần điều tra**, rationale và người chịu trách nhiệm.
- Nếu một account xuất hiện sau lần chốt snapshot, phải có cách **xử lý delta** hoặc giới hạn claim; không suy rằng đã review tất cả accounts tại mọi thời điểm.
- Một thay đổi quyền đặc quyền trong kỳ vẫn cần thực hiện control **theo sự kiện**, không đợi ba tháng.
- Chỉ tính “đã hoàn thành review” khi việc kiểm tra và phê duyệt theo policy có **thời điểm/đầu ra** rõ, không phải lúc job gửi email nhắc việc.

### Bỏ lỡ một lần khác với control chưa đạt mọi lúc

Một cuộc diễn tập restore bị trễ là **assessment cadence breach** và có thể làm độ tin cậy của recovery control giảm. Điều đó **không tự chứng minh mọi bản backup đã lỗi**. Ngược lại, backup job thất bại tối qua là **operational failure** dù lịch diễn tập restore năm nay vẫn đạt. Cần tách cả hai để triage đúng.

## 8. “Continuous control” cần bằng chứng chất lượng nào?

Một tuyên bố như “authorization áp dụng liên tục” nên được cụ thể hóa:

- **Design:** threat model, API contract, yêu cầu quyền theo resource, policy và kiến trúc.
- **Implementation:** service code, security filter, infrastructure/IAM policy, review, build và tests.
- **Operational:** build đang chạy, effective config, positive/negative tests theo phạm vi được duyệt, telemetry và phát hiện drift.
- **Coverage:** endpoints, roles, tenants, service identities, protocol và các trường hợp ngoại lệ.
- **Reassessment:** mỗi thay đổi có thể làm thay đổi quyền hoặc đường truy cập.

**Không phải mọi request production được thao tác thử bằng pentest.** Cần kết hợp lập luận thiết kế, kiểm thử trên đường xử lý thật, runtime verification và theo dõi thay đổi để có **assurance hợp lý trong phạm vi được ghi rõ**.

### Phát hiện control có thể “mất tiếng”

Đặc biệt với logging và monitoring:

1. Tạo một **synthetic event an toàn** với định danh riêng và thời điểm ghi nhận.
2. Xác minh event xuất hiện tại collector đúng môi trường và nguồn.
3. Kiểm tra rule, routing, alert tới người nhận có trách nhiệm.
4. Ghi độ trễ, kết quả, những thành phần chưa được kiểm tra.
5. Cấu hình cảnh báo khi nguồn log ngừng gửi hoặc pipeline mất dữ liệu.

Chỉ đếm số log/số alert **không chứng minh** mỗi nguồn sự kiện cần thiết đều được bao phủ. Khi nguồn không phát dữ liệu, dashboard có thể hiển thị “0 lỗi” nhưng thật ra **không còn quan sát**.

## 9. Frequency, phạm vi đánh giá và phương pháp lấy mẫu

Một control đánh giá “hàng tháng” có thể được thực hiện trên:

- **Toàn bộ population:** tất cả quyền admin đang còn hiệu lực.
- **Một mẫu:** chọn các giao dịch hoặc người dùng theo phương pháp được định nghĩa.
- **Phân tầng:** mẫu riêng theo nhóm rủi ro, tài khoản đặc quyền, vùng dữ liệu và thay đổi.
- **Kiểm tra tự động đầy đủ + review thủ công theo mẫu:** dùng automation để sàng lọc, rồi con người xác minh các ngoại lệ.

Cần giữ rõ **mẫu nào đại diện cho điều gì**. Một lựa chọn ngẫu nhiên từ 10 tài khoản thường không thể chứng minh quyền của **mọi super-admin** đều hợp lệ. Các nhóm có rủi ro đặc biệt có thể cần kiểm tra toàn bộ.

### Population, numerator và denominator

Ví dụ trong một kỳ có **20 thay đổi production cần security approval**. Có 18 thay đổi có đầy đủ approval trước khi thực hiện. Chỉ số đáp ứng theo record là:

\[
\text{Coverage}=\frac{18}{20}\times100\%=90\%
\]

Chỉ số 90% **không có nghĩa 90% hệ thống an toàn** hoặc 10% rủi ro còn lại. Hai thay đổi thiếu approval cần được triage theo **tác động và hoàn cảnh**; một thay đổi quyền IAM cốt lõi có thể quan trọng hơn nhiều thay đổi không ảnh hưởng bảo mật.

### Bằng chứng nào làm thay đổi kết luận?

| Kết quả | Có thể kết luận | Không thể kết luận |
| --- | --- | --- |
| 100% sampled records hợp lệ | Các record đã kiểm tra đáp ứng tiêu chí trong kỳ | Toàn bộ population đều đúng nếu mẫu không phủ hết |
| Automation pass trên cấu hình mong muốn | Desired state qua policy check tại thời điểm scan | Runtime không drift hoặc không có thay đổi ngoài hệ thống |
| Một synthetic alert thành công | Đường event thử đã hoạt động tại thời điểm đó | Mọi detector và mọi kiểu sự cố đều có thể phát hiện |
| Review quý có sign-off | Một người có trách nhiệm đã kết luận phạm vi được review | Người duyệt đã xem toàn bộ population nếu tài liệu không chứng minh |
| Không có finding mới | Chưa ghi thêm vi phạm trong phạm vi quan sát | Rủi ro thấp hoặc không có sai lệch chưa phát hiện |

**Evidence freshness** phải tương thích với quyết định cần đưa ra. Một snapshot IAM từ sáu tháng trước có thể hữu ích cho audit quá khứ nhưng không đủ để khẳng định quyền **hiện tại** sau ba đợt thay đổi.

## 10. Thiết kế control register có frequency có thể quản trị

Một control cần được quản lý bằng **định danh ổn định và phiên bản chính sách**, không dựa vào tên lịch tự phát.

| Trường | Ý nghĩa |
| --- | --- |
| Control ID / name | Biện pháp/hoạt động cần thực hiện |
| Risk/requirement/framework refs | Mục tiêu và căn cứ áp dụng |
| Scope | Service, tài sản, data, environment, actor, population |
| Frequency type | Per-request, per-event, periodic, continuous, hybrid |
| Schedule rule | Mốc, timezone, khoảng thời gian, deadline, grace |
| Trigger list | Thay đổi/sự cố nào buộc đánh giá ngoài lịch |
| Owner/reviewer | Ai vận hành, review, quản lý ngoại lệ |
| Evidence plan | Nguồn hiện vật, định dạng, bảo vệ và retention |
| Acceptance criteria | Khi nào PASS/FAIL/INCONCLUSIVE; độ bao phủ tối thiểu |
| Last execution / verification | Hai thời điểm riêng khi cần |
| Finding/exception links | Các sai lệch, rủi ro, thời hạn và quyết định |
| Next due / last assessed | Mốc được tính bằng rule version hiện hành |
| Reassessment conditions | Event nào làm evidence cũ mất hiệu lực |

### Mẫu YAML control frequency

Tất cả giá trị `<...>` là placeholder minh họa. Các lịch và ID dưới đây không phải nghĩa vụ của một framework bên ngoài.

~~~yaml
control_id: CTRL-IAM-ACCESS-REVIEW
control_title: "Rà soát quyền đặc quyền theo phạm vi"
framework_reference: "<APPLICABLE_FRAMEWORK_CONTROL_ID_AND_VERSION>"
requirement_id: REQ-IAM-PRIVILEGED-ACCESS
risk_ids:
  - RISK-IAM-OVERPRIVILEGE
scope:
  environment: production
  asset_groups: ["cloud-iam", "kubernetes", "secret-store"]
  population_source: "<EFFECTIVE_PRIVILEGED_IDENTITIES>"
owner: "<IAM_CONTROL_OWNER>"
reviewer: "<INDEPENDENT_OR_AUTHORIZED_REVIEWER>"
frequency:
  type: hybrid
  periodic:
    rule: "calendar-quarter"
    timezone: "UTC"
    window_definition: "<APPROVED_QUARTERLY_WINDOW>"
    due_policy: "<APPROVED_DUE_DATE_AND_GRACE_RULE>"
  event_triggers:
    - "new privileged role or permission"
    - "identity ownership change"
    - "incident or finding affecting access"
    - "new high-risk trust relationship"
operation:
  execution: "Access grant/revoke checks on each relevant event"
  assessment: "Review privileges and removal decisions"
  monitoring: "IAM change events and unusual privilege behavior"
  acceptance_criteria:
    - "Full in-scope population enumerated"
    - "Owner decisions and exceptions documented"
    - "Revocations tracked to actual effective permissions"
evidence:
  source_refs:
    - "<EFFECTIVE_IAM_SNAPSHOT>"
    - "<REVIEW_SIGN_OFF>"
    - "<ACCESS_REMOVAL_RETEST>"
  storage_policy: "<EVIDENCE_RETENTION_AND_ACCESS_RULE>"
  data_redaction: "<SENSITIVE_DATA_HANDLING>"
status:
  control_operational_result: "<PASS_FAIL_INCONCLUSIVE>"
  last_completed_at: "<ISO_8601_UTC>"
  last_verified_at: "<ISO_8601_UTC>"
  last_evidence_id: "<EVIDENCE_ID>"
  next_due_at: "<APPROVED_SCHEDULE_CALCULATION>"
  overdue: "<TRUE_OR_FALSE>"
change_review: "<STANDARD_OR_RISK_TRIGGERED_REASSESSMENT>"
~~~

Ở dự án thực tế, cần quyết định từ trước **điều gì tạo ra một kỳ mới** và **điều gì tính là hoàn thành**. Việc cho scheduler tự sinh `next_due_at` không chứng minh lịch đã được thực thi, cũng không giải quyết ngoại lệ nếu người review chưa xác nhận kết quả.

## 11. Lập bằng chứng cho từng kỳ control

Một evidence record tốt cần liên kết **một lần thực thi hoặc đánh giá** với đúng lịch và phạm vi. Dùng các trạng thái có ý nghĩa:

- **PASS:** đủ bằng chứng control đáp ứng yêu cầu trong phạm vi/kỳ đã đánh giá.
- **FAIL:** bằng chứng cho thấy control hoặc hoạt động không đáp ứng yêu cầu.
- **INCONCLUSIVE:** chưa thể kết luận do thiếu dữ liệu, phạm vi không đầy đủ hoặc kết quả không chắc chắn.
- **NOT_RUN:** hoạt động đã được lên lịch hoặc yêu cầu nhưng chưa diễn ra.
- **OVERDUE:** vượt hạn hoàn tất đã định nghĩa; có thể đồng thời mang trạng thái NOT_RUN hoặc review chưa xong.
- **EXCEPTION_APPROVED:** quyết định quản trị chấp nhận sai lệch/rủi ro trong điều kiện cho phép; **không thay thế PASS**.

### Mẫu evidence record cho một kỳ

~~~yaml
evidence_id: EV-IAM-Q4-EXAMPLE
control_id: CTRL-IAM-ACCESS-REVIEW
control_rule_version: 3
assessment_period:
  starts_at: "<START_UTC>"
  ends_at: "<END_UTC>"
frequency_rule: "calendar-quarter-plus-change-triggers"
schedule_due_at: "<DUE_UTC>"
actual_execution_at: "<EXECUTION_UTC>"
verification_at: "<REVIEW_UTC>"
environment: production
population:
  source: "<EFFECTIVE_IAM_SOURCE>"
  total_in_scope: "<COUNT>"
  tested_or_reviewed: "<COUNT>"
  exclusions: "<EXCLUSIONS_WITH_APPROVAL>"
method: "Enumeration, owner review and effective permission validation"
acceptance_criteria: "<VERSIONED_CONTROL_CRITERIA>"
result: "<PASS_FAIL_INCONCLUSIVE_NOT_RUN>"
operational_issue_ref: "<FAILED_OR_DELAYED_CONTROL_TICKET>"
finding_refs: ["<FINDING_IF_ANY>"]
exception_ref: "<APPROVED_EXCEPTION_IF_ANY>"
artifact_refs:
  - "<SANITIZED_IAM_SNAPSHOT>"
  - "<REVIEWER_DECISION_RECORD>"
  - "<REVOCATION_VERIFICATION>"
owner: "<CONTROL_OWNER>"
assessor: "<ASSESSOR>"
limitations: "<COVERAGE_OR_TIMING_GAPS>"
next_due: "<CALCULATED_FROM_APPROVED_SCHEDULE>"
reassessment_triggers:
  - "IAM changes affecting privileged access"
  - "Audit finding, security incident or scope change"
~~~

Người đánh giá phải có thể kiểm tra **nguyên bản hiện vật**, nguồn, thời gian, phiên bản, phương pháp, người thực hiện và người review. Không nên trích nguyên secret, token hoặc dữ liệu khách hàng vào evidence chỉ để chứng minh control đã chạy.

## 12. Ví dụ Java 17: phát hiện lịch xác minh quá hạn

Một service quản lý security controls có thể cần tính trạng thái kỳ tiếp theo. Mã sau minh họa **lịch theo khoảng thời gian cố định** với `Duration` và `Clock`; nó **không triển khai calendar-quarter**, lịch ngày làm việc, sự kiện hay trigger thay đổi. Với các quy tắc lịch, phải sử dụng định nghĩa Calendar/ZoneId và policy version được phê duyệt.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class ControlVerificationSchedule {
    public enum State {
        NO_VERIFIED_EVIDENCE,
        CURRENT,
        DUE,
        OVERDUE
    }

    public record Rule(Duration interval, Duration grace) {
        public Rule {
            Objects.requireNonNull(interval, "interval");
            Objects.requireNonNull(grace, "grace");
            if (interval.isNegative() || interval.isZero()) {
                throw new IllegalArgumentException("interval phải dương");
            }
            if (grace.isNegative()) {
                throw new IllegalArgumentException("grace không được âm");
            }
        }
    }

    public static State evaluate(
            Rule rule, Instant lastVerifiedAt, Clock clock) {
        Objects.requireNonNull(rule, "rule");
        Objects.requireNonNull(clock, "clock");

        if (lastVerifiedAt == null) {
            // Không có evidence đã xác minh không thể coi là PASS.
            return State.NO_VERIFIED_EVIDENCE;
        }

        Instant now = clock.instant();
        Instant dueAt = lastVerifiedAt.plus(rule.interval());
        Instant overdueAt = dueAt.plus(rule.grace());

        if (now.isBefore(dueAt)) {
            return State.CURRENT;
        }
        if (now.isBefore(overdueAt)) {
            return State.DUE;
        }
        return State.OVERDUE;
    }
}
~~~

Một số kiểm thử JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class ControlVerificationScheduleTest {
    private final Clock clock = Clock.fixed(
            Instant.parse("2026-11-28T00:00:00Z"), ZoneOffset.UTC);
    private final ControlVerificationSchedule.Rule rule =
            new ControlVerificationSchedule.Rule(
                    Duration.ofDays(30), Duration.ofDays(3));

    @Test
    void noVerifiedEvidenceMustNotBecomeCurrent() {
        assertEquals(
                ControlVerificationSchedule.State.NO_VERIFIED_EVIDENCE,
                ControlVerificationSchedule.evaluate(rule, null, clock));
    }

    @Test
    void dueExactlyAtBoundary() {
        Instant last = Instant.parse("2026-10-29T00:00:00Z");
        assertEquals(
                ControlVerificationSchedule.State.DUE,
                ControlVerificationSchedule.evaluate(rule, last, clock));
    }

    @Test
    void overdueAfterGraceWindow() {
        Instant last = Instant.parse("2026-10-25T00:00:00Z");
        assertEquals(
                ControlVerificationSchedule.State.OVERDUE,
                ControlVerificationSchedule.evaluate(rule, last, clock));
    }

    @Test
    void stillCurrentBeforeDue() {
        Instant last = Instant.parse("2026-11-20T00:00:00Z");
        assertEquals(
                ControlVerificationSchedule.State.CURRENT,
                ControlVerificationSchedule.evaluate(rule, last, clock));
    }
}
~~~

**Đây chỉ là kiểm tra freshness của một mốc xác minh, không phải proof of control effectiveness.** Nếu kết quả kiểm thử mới nhất là FAIL thì thời điểm `lastVerifiedAt` có thể rất mới nhưng **control vẫn FAIL**. Trong ứng dụng thật, cần tách **kết quả đánh giá** khỏi **mốc đã xác minh**, theo dõi missing run, phê duyệt, control scope, hoàn thành kỳ, exceptions và cả trigger theo sự kiện.

Ngoài ra, công thức `lastVerifiedAt + interval` có thể bị “trôi lịch” nếu control chạy trễ. Với lịch cố định theo quý/tháng, **due date phải xuất phát từ lịch đã phê duyệt**, không tự dịch chuyển sang ngày muộn hơn mỗi khi hoàn thành trễ.

## 13. Case study: Control frequency cho báo cáo tài chính đa tenant

### Bối cảnh

Một nền tảng Java/Spring Boot cho người dùng tải báo cáo giao dịch. Luồng chính:

~~~mermaid
flowchart LR
    U["User tenant A/B"] --> GW["API Gateway"]
    GW --> API["Spring Boot report-api"]
    API --> IAM["Authorization / tenant policy"]
    API --> Q["Export Queue"]
    Q --> W["Report Worker"]
    W --> DB[("Financial Data")]
    W --> STORE[("Object Storage")]
    API --> LOG["Audit Events"]
    W --> LOG
    LOG --> SOC["Collector + SOC Alert"]
~~~

Một cuộc audit phát hiện bảng control chỉ có “Access review – quarterly”, “SAST – weekly” và “Logging – monthly”. Auditor đặt câu hỏi: **lịch đó có bảo đảm user tenant A không đọc dữ liệu tenant B hoặc hoạt động xuất bất thường được phát hiện không?**

### Phân tích theo mục tiêu

| Risk scenario | Control objective | Tần suất thực thi cần có | Cách đánh giá hiệu lực |
| --- | --- | --- | --- |
| **RISK-01:** user A đọc/export báo cáo B | Ngăn đọc/xuất trái quyền theo đối tượng | Authorization ở **mỗi request và mỗi job** cần quyền | Cross-tenant negative tests khi thay route/policy và theo chương trình review |
| **RISK-02:** workload dùng IAM quyền quá rộng | Giới hạn quyền tới dataset/bucket cần thiết | IAM luôn có hiệu lực; cấp/sửa/thu hồi quyền theo event | Effective permissions review, test deny sau thay IAM và định kỳ |
| **RISK-03:** job xuất dữ liệu hàng loạt làm cạn worker | Giới hạn request/job theo actor và tài nguyên | Quota/concurrency áp dụng trên mỗi tác vụ | Load/abuse tests khi đổi gateway, worker và theo risk plan |
| **RISK-04:** thiếu log làm mất dấu tải dữ liệu | Có đủ telemetry phát hiện/truy vết | Audit event theo hành động; collector quan sát liên tục | Synthetic event, ingestion/alert delivery test theo change + lịch |
| **RISK-05:** storage link tồn tại quá hạn | Giới hạn thời gian truy cập và vòng đời file | Access/expiry enforcement khi tải; purge theo lifecycle | Test expiry, object reconciliation, monitoring backlog |

**Điểm mấu chốt:** một review IAM mỗi quý có thể phát hiện đặc quyền sai sau một thời gian, nhưng **không thay thế** quyền authorization được kiểm tra **trong mỗi thao tác**. Tương tự, logging được review hằng tháng không đảm bảo hệ thống nhận event ở ngày mà một sự cố xảy ra.

### Thiết kế lịch bám vào release và vận hành

1. **Khi thay API/controller/policy:** chạy integration/negative tests với hai tenant, actor thiếu quyền và đường export.
2. **Khi thay gateway/IAM/storage:** kiểm tra quyền thực tế, direct access bypass và điều kiện hết hạn link.
3. **Khi deploy production:** đối chiếu image digest, identity, policy và route đang chạy; ghi evidence cho phiên bản đó.
4. **Mỗi hành động xuất báo cáo:** thực thi authorization và tạo audit event theo tiêu chí nghiệp vụ.
5. **Liên tục:** theo dõi ingestion health, drift quan trọng và các alert đã được định nghĩa.
6. **Theo lịch đã duyệt:** review quyền đặc quyền, thử detection end-to-end, kiểm tra data retention và khả năng khôi phục.
7. **Khi incident/finding:** đánh giá lại control, bằng chứng cũ, frequency, scope và residual risk.
8. **Khi control FAIL:** triage theo mức rủi ro, khắc phục, retest, ghi rõ khoảng thời gian chưa có bảo vệ hoặc chưa có quan sát.

### Minh họa một finding về frequency

**FIND-FREQ-01:** sau khi thay schema, log của export-worker ngừng được nhận trong 11 ngày. Dashboard review định kỳ vẫn hiển thị “completed” vì dùng bản báo cáo tháng trước.

Đánh giá đúng phải tách:
- **Control execution:** worker có thực sự tạo event không?
- **Transport:** event có đến collector trong 11 ngày không?
- **Detection:** rule có nhận event phù hợp không?
- **Assurance:** đã có test end-to-end và kiểm tra nguồn log trong kỳ đó chưa?
- **Impact:** những thao tác nào có thể không được truy vết, có nguồn bằng chứng thay thế và có cần điều tra thêm không?

Kế hoạch xử lý gồm sửa schema/pipeline, kiểm tra event thử, xác định thời gian và phạm vi mất quan sát, điều tra theo cơ sở còn lại, cập nhật cảnh báo mất nguồn log và điều chỉnh frequency kiểm tra phù hợp. Không đóng finding chỉ vì sau sửa dashboard đã quay về màu xanh.

## 14. Control frequency và quy trình audit

Một auditor có thể kiểm tra hai loại câu hỏi khác nhau:

1. **Design effectiveness:** lịch và phương pháp đánh giá có đủ để đáp ứng mục tiêu bảo mật không? Ai quyết định và dựa vào rủi ro nào?
2. **Operating effectiveness:** trong kỳ đánh giá, control có thực hiện đúng lịch, đúng population, có kết quả và bằng chứng đáng tin không?

Một control thiết kế “review quarterly” nhưng không có **mốc thực hiện, population và sign-off** trong quý vừa rồi chưa thể kết luận hoạt động đạt. Một control có nhiều báo cáo PASS nhưng **frequency không phù hợp time-to-harm** cũng có thể cần cải tiến thiết kế.

### Audit một control theo chuỗi

~~~text
Risk: Quyền admin tồn đọng sau thay đổi vai trò
  -> Requirement: Quyền đặc quyền được cấp, giữ, thu hồi đúng policy
  -> Control: IAM Access Review + Event-driven Deprovisioning
  -> Frequency: Theo sự kiện + review định kỳ đã phê duyệt
  -> Population: Effective privileged identities trong kỳ
  -> Execution: Kết quả review/thu hồi và thời điểm
  -> Evidence: Snapshot, decision, IAM changes, retest
  -> Finding: Account không có owner hoặc review bỏ sót
  -> Remediation: Thu hồi/kiểm soát quyền, bổ sung detection
  -> Reassessment: Kết quả retest và điều chỉnh lịch nếu cần
~~~

Bằng chứng phải cho biết **kỳ nào** được kiểm tra, những tài khoản/đường truy cập nào được xét, người duyệt có đúng thẩm quyền không và các ngoại lệ có còn hiệu lực không.

### Thiếu bằng chứng không phải luôn là control thất bại

Nếu control không có log do hệ thống thu chứng cứ bị lỗi, assessor có thể kết luận **INCONCLUSIVE** về hiệu lực trong kỳ. Nhưng **không có bằng chứng** không được tự động thành PASS, và sự thiếu hụt bằng chứng có thể là finding riêng cần xử lý. Nếu có bằng chứng chính control thực tế không chạy, trạng thái cần là **FAIL** trong phạm vi liên quan.

## 15. Ngoại lệ và thay đổi control frequency

### Khi nào có thể thay tần suất?

Một thay đổi phải được đánh giá nếu:
- Kiến trúc hoặc tài sản giảm/tăng mức rủi ro.
- Tổ chức đưa vào giám sát tự động hoặc phát hiện theo event thay cho phần lớn kiểm tra thủ công.
- Control đã chứng minh tính ổn định trong một khoảng đánh giá phù hợp, và risk owner chấp nhận thay đổi.
- Framework, hợp đồng hoặc nghĩa vụ áp dụng có quy tắc mới.
- Sự cố/finding cho thấy lịch cũ **không phát hiện kịp** sai lệch.
- Có giới hạn tài nguyên khiến phương pháp kiểm thử cần tối ưu nhưng vẫn phải đạt mục tiêu bảo mật.

Điều kiện cần có: **rationale, phương pháp so sánh rủi ro, approval, hiệu lực từ ngày nào, cập nhật lịch, trigger, owner và evidence plan**. Một thay đổi không được để “khoảng trống” không ai giám sát.

### Nếu lần kiểm tra bị bỏ lỡ

1. Ghi nhận **due date gốc**, kỳ và thời gian trễ, không xóa lịch sử.
2. Phân loại nguyên nhân: chưa chạy, chạy lỗi, review chưa xong, thiếu population, thiếu evidence hoặc không thể truy cập hệ thống.
3. Xác định **rủi ro do khoảng trống**: control đang thất bại hay chỉ thiếu bằng chứng, hậu quả có thể xảy ra trước lần kiểm tra tiếp theo không?
4. Triển khai biện pháp khắc phục/tạm thời, tăng quan sát hoặc triage cấp có thẩm quyền nếu rủi ro cao.
5. Thực hiện đánh giá bù và kiểm tra xem nó có thể/không thể chứng minh **kỳ đã qua**; nhiều sự kiện quá khứ không thể dựng lại khi log bị mất.
6. Review frequency/automation và đóng finding sau khi có kết quả, không chỉ sau khi chạy bù một lần.

**Grace period là quy tắc lịch/khả năng vận hành**, không phải quyền bỏ qua control. Nếu một control phải chạy ở **mỗi giao dịch**, grace 3 ngày cho báo cáo không thể biện minh cho ba ngày bỏ qua authorization.

### Ngoại lệ đã được chấp nhận

Một ngoại lệ phải có phạm vi, tình huống, tác động, control bù trừ, thời hạn và **người phê duyệt đúng thẩm quyền**. Trạng thái **EXCEPTION_APPROVED** phản ánh quyết định quản trị, **không biến operating effectiveness FAIL thành PASS**. Bằng chứng và risk score phải được báo cáo trung thực.

## 16. Trách nhiệm và quy trình vận hành

| Vai trò | Trách nhiệm đối với frequency | Hiện vật thường cung cấp |
| --- | --- | --- |
| **Control Owner** | Đề xuất và duy trì cách thực thi/kiểm tra, SLA, owner và khắc phục | Control register, run logs, test kế hoạch và kết quả |
| **Service Owner / Risk Owner** | Xác định tác động, mức ưu tiên và quyết định điều chỉnh/ngoại lệ theo thẩm quyền | Risk assessment, approval, treatment plan |
| **Developer / Tech Lead** | Bảo đảm control trong ứng dụng chạy đúng lúc, thêm regression tests và hooks theo thay đổi | Source/PR, CI results, test report, release refs |
| **Ops / SRE / Platform** | Vận hành scheduler, IAM, monitoring, alerts, backup và configuration drift checks | Runtime config, job result, monitoring, deployment |
| **Security / AppSec / SOC** | Phân tích risk/time-to-harm, kiểm tra coverage, thực hiện detection review | Threat scenario, alert/test evidence, findings |
| **GRC / Security Governance** | Duy trì tiêu chí áp dụng framework, lịch control, định nghĩa compliance status | Versioned control framework, policy, exceptions |
| **Assessor / Audit** | Đánh giá design và operating effectiveness dựa trên bằng chứng | Assessment, sampling method, review trail, gaps |

Các vai trò có thể kiêm nhiệm tùy tổ chức, nhưng **ai triển khai, ai review và ai chấp nhận residual risk** phải được xác định rõ. Không nên để người sở hữu lịch tự sửa `next_due_at` và chấm PASS mà không có kiểm soát thay đổi hoặc lịch sử review.

### Handover và owner thay đổi

Khi Control Owner nghỉ việc hoặc dịch vụ chuyển nhóm:
- Chuyển giao danh sách control ID, các lịch và bằng chứng đang mở.
- Xác nhận backup owner và người nhận alert.
- Kiểm tra lịch nào đang DUE/OVERDUE hoặc cần review vì thay đổi.
- Không mặc định lịch tiếp tục được thực thi chỉ vì cron vẫn còn trong hệ thống.

## 17. Dashboard và các chỉ số cần diễn giải đúng

Một dashboard hữu ích hiển thị **mốc gần nhất và tiếp theo**, control status, evidence freshness, finding/exception, owner, scope và những nguồn mất quan sát.

| Chỉ số | Giúp trả lời | Hạn chế |
| --- | --- | --- |
| **On-time completion rate** | Bao nhiêu hoạt động định kỳ hoàn thành đúng hạn? | Không nói control có thiết kế phù hợp rủi ro hay không |
| **Coverage by population** | Tài sản/user/request class nào nằm trong scope kiểm tra? | Coverage cao chưa chắc bao phủ nhóm rủi ro lớn nhất |
| **Evidence freshness** | Bằng chứng đã bao lâu, còn phản ánh runtime không? | Bằng chứng mới có thể là kết quả FAIL |
| **Overdue controls by criticality** | Lịch bị bỏ lỡ ở tài sản/trọng yếu nào? | Phải phân biệt thiếu review với control thực sự không chạy |
| **Change-triggered review rate** | Những thay đổi quan trọng có được đánh giá ngoài lịch không? | Cần xác nhận danh sách thay đổi đầy đủ |
| **Detection pipeline health** | Log/alert có hoạt động và được thử định kỳ không? | Một thử nghiệm không chứng minh mọi source đều được bao phủ |
| **Remediation-to-retest time** | Phát hiện được sửa và xác minh nhanh đến đâu? | Ticket đóng không tự đồng nghĩa finding đã hết |

Không sử dụng **“100% checklist done”** như bằng chứng chương trình security assurance thành công. Nhiều control chỉ được tick theo lịch có thể vẫn bỏ sót rủi ro nghiêm trọng xảy ra giữa các kỳ hoặc giữa các môi trường.

## 18. Bài tập thực hành

**Tình huống:** một tổ chức dùng hệ thống Java/Spring Boot cho dữ liệu khách hàng, với ba môi trường development, staging và production. Các điểm đã biết:

- CI chạy security tests mỗi thứ Sáu, trong khi Developer merge nhiều pull request mỗi ngày.
- Security gateway áp dụng authorization theo JWT nhưng role mapping IAM thay đổi hằng ngày.
- Đội IAM review tài khoản đặc quyền mỗi sáu tháng và không có cảnh báo khi role được cấp thêm quyền.
- Log collector nhận event liên tục, nhưng chưa có test chứng minh alert thực sự được gửi cho on-call.
- Backup mỗi đêm; tháng trước một lần restore thử thất bại nhưng lịch kiểm tra vẫn được đánh dấu completed.
- Có một ngoại lệ cho một service legacy, đã hết hạn nhưng dashboard vẫn màu xanh.

### Yêu cầu

1. Liệt kê **ít nhất sáu control** và xác định nhịp **thực thi**, **giám sát**, **kiểm thử**, **thu evidence**, **review** cho từng control.
2. Giải thích vì sao test security chỉ chạy vào thứ Sáu có thể tạo khoảng trống với các thay đổi merge trong tuần, nhất là authorization.
3. Thiết kế control **hybrid** cho IAM: theo thay đổi quyền và theo kỳ đã phê duyệt. Nêu đầy đủ population, owner, due và expected evidence.
4. Phân biệt **backup job completed** với **restore control effectiveness**. Thất bại restore phải thể hiện thế nào?
5. Mô tả hai kiểu kiểm tra an toàn để chứng minh log collector và alert pipeline hoạt động.
6. Đề xuất dashboard trạng thái PASS/FAIL/INCONCLUSIVE/OVERDUE và cách xử lý ngoại lệ đã hết hạn.
7. Lập kế hoạch remediation có finding, thời hạn, retest, người duyệt và trigger đánh giá lại.

### Gợi ý lời giải

| Vấn đề | Hướng đánh giá |
| --- | --- |
| **CI security tests thứ Sáu** | Nếu security-critical code được merge trong tuần, test cần là gate theo PR/build hoặc có các quy tắc chặn thay đổi; lịch weekly không thay bảo vệ mỗi thay đổi. |
| **JWT/IAM** | Token validation và authorization theo request; test thay mapping theo change; review IAM theo lịch có risk rationale, population đầy đủ và effective policy. |
| **Không có alert khi role đổi** | Bổ sung event-driven kiểm tra/cảnh báo thay đổi quyền và xác minh người nhận; không chỉ đợi review sáu tháng. |
| **Collector thiếu end-to-end test** | Tạo event thử có correlation ID, kiểm tra đi qua collector/detection tới on-call; giám sát nguồn mất log hoặc rule không nhận. |
| **Backup/restore** | Backup mỗi đêm có evidence riêng; restore FAIL phải tạo finding về khả năng phục hồi, bất kể lịch chạy test đã completed. |
| **Ngoại lệ hết hạn** | Không giữ dashboard xanh; báo quá hạn, review residual risk, quyết định có thẩm quyền hoặc khắc phục control. |
| **Audit evidence** | Giữ rule version, scope, source, actual time, test result, reviewer, gaps và runtime version; không tái sử dụng file cũ thay cho control mới. |

### Câu hỏi nâng cao

Một hệ thống kiểm tra IAM tự động **mỗi 5 phút** và dùng kết quả để hiển thị compliance PASS. Sau một lần deploy, scanner mất quyền liệt kê tài khoản privileged và trả về danh sách rỗng; dashboard vẫn PASS.

Hãy cho biết control nào thiếu: **độ đầy đủ population**, **kiểm tra quyền/nguồn dữ liệu**, **trạng thái khi thiếu quan sát** và **alert mất khả năng kiểm chứng**. Tăng frequency lên mỗi phút có giải quyết được vấn đề không?

**Định hướng:** tần suất cao không giúp ích nếu nguồn quan sát sai hoặc không đầy đủ. Hệ thống phải kiểm tra source health và completeness, đánh dấu **INCONCLUSIVE/FAIL tùy tiêu chí**, cảnh báo owner và không diễn giải “0 tài khoản sai” thành “mọi tài khoản hợp lệ”.

## 19. Những sai lầm thường gặp

| Nhận định sai | Vì sao nguy hiểm? | Cách khắc phục |
| --- | --- | --- |
| “Có schedule nghĩa là control đã hoạt động.” | Lịch chỉ là ý định; cron, job, review có thể không chạy hoặc lỗi | Kiểm chứng execution, result, evidence và reviewer |
| “Continuous = không cần test.” | Agent hoặc rule có thể lệch/lỗi âm thầm | Test theo thay đổi và định kỳ, giám sát health và bypass |
| “Mỗi tháng xem IAM là đủ cho mọi tình huống.” | Quyền mới nguy hiểm có thể được cấp sau kỳ review | Trigger per change/joiner-mover-leaver cùng review định kỳ |
| “Chạy SAST một lần mỗi năm là giống SAST mỗi build.” | Rủi ro từ code mới xuất hiện giữa các kỳ | Chọn execution frequency khớp CI và risk |
| “Có report PASS hôm nay thì production hiện tại chắc chắn đạt.” | Report có thể dùng snapshot cũ, thiếu coverage hoặc phiên bản khác | Gắn với runtime, source, timestamp và scope |
| “Cùng một ngày kiểm tra là cùng phạm vi kiểm tra.” | Population/user/asset trong kỳ có thể khác | Lưu population, exclusion và phương pháp lấy mẫu |
| “Control test FAILED nhưng lịch completed nên status PASS.” | Tần suất hoàn thành khác hiệu lực | Tách completion status và assessment result |
| “Không có alert nghĩa là không có sự cố.” | Pipeline có thể không thu event hoặc bị mute | Synthetic tests và kiểm tra nguồn bị mất |
| “Chỉ cần theo cron, không cần event trigger.” | Change/incident làm evidence cũ mất giá trị | Thiết kế hybrid và reassessment |
| “Đã có exception thì không cần kiểm tra nữa.” | Ngoại lệ có thời hạn, condition và residual risk thay đổi | Review theo lịch và trigger, luôn báo status kỹ thuật |
| “Chạy lại trễ thì chuyển ngày đến hạn lần sau.” | Che kỳ bỏ lỡ và tạo lịch trôi mà không phê duyệt | Giữ due date và lịch sử, xử lý overdue và rule version |
| “Càng nhiều check càng ít rủi ro.” | Kiểm tra hình thức hoặc dữ liệu sai không giúp phát hiện đúng | Chọn tần suất dựa trên time-to-harm, coverage và chất lượng evidence |

## Ghi nhớ

- **Control frequency** mô tả **khi nào control phải hoạt động và khi nào phải được kiểm tra**; không nên gộp execution, monitoring, evidence collection và review thành một trường.
- Có các nhịp **continuous, per-request, per-event, per-change, periodic và hybrid**; control quan trọng thường cần **giám sát liên tục + đánh giá định kỳ + trigger theo thay đổi**.
- **Không có một tần suất chung áp dụng cho mọi framework và mọi control.** Cần xét đúng yêu cầu áp dụng, mức rủi ro, thời gian gây hại, tốc độ thay đổi, phạm vi và độ tin cậy của quan sát.
- Lịch phải có **mốc, timezone, due date, owner, population, tiêu chí kiểm tra, bằng chứng, escalation và xử lý bỏ lỡ**.
- **Một kết quả PASS mới nhưng sai population hoặc sai môi trường không đủ chứng minh hiệu lực**; thiếu dữ liệu phải được báo trung thực, không tự động coi đạt.
- Frequency gắn với **risk → security requirement → control → execution/test → evidence → audit/finding → remediation/retest**, và mọi lần thay đổi cần được version, phê duyệt và xem xét lại.
- **Security assurance là quá trình liên tục**: control có thể trôi cấu hình, mất nguồn log, đổi quyền hoặc hết hạn ngoại lệ ngay cả khi lịch review gần nhất từng hoàn thành.
