# Phân định quyền sở hữu dịch vụ và mô hình trực vận hành

> **Chương:** Vận hành hệ thống  
> **Module:** CLOUD_ARCHITECTURE  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai; cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích service ownership và vì sao mỗi dịch vụ cần một nhóm chịu trách nhiệm rõ ràng trong suốt vòng đời.
2. Phân biệt trách nhiệm của service owner, engineering team, platform team, operations, security, product owner và incident commander.
3. Thiết kế mô hình trực vận hành phù hợp với mức độ quan trọng, SLO, quy mô đội và khả năng hỗ trợ.
4. Xây dựng lịch trực primary/secondary, quy tắc escalation, handover và cơ chế gọi hỗ trợ ngoài giờ.
5. Kết nối ownership với SLO, error budget, observability, runbook, deployment và quản lý thay đổi.
6. Tổ chức incident response với vai trò và kênh liên lạc rõ ràng; chuyển từ xử lý khẩn cấp sang follow-up và cải tiến.
7. Đánh giá rủi ro về quá tải trực, phụ thuộc cá nhân, alert fatigue và thiếu năng lực phục hồi.
8. Áp dụng RACI, service catalog, ownership metadata và bài thực hành để thiết kế mô hình vận hành có thể kiểm chứng.

## 1. Vì sao cần phân định quyền sở hữu dịch vụ?

Một dịch vụ cloud có thể được xây bởi nhiều nhóm: product định nghĩa trải nghiệm, backend phát triển API, platform cung cấp cluster và pipeline, data team quản lý database, security xây chính sách, operations theo dõi hệ thống. Khi mọi thứ hoạt động tốt, ranh giới trách nhiệm có thể chưa rõ. Khi xảy ra sự cố lúc nửa đêm, những câu hỏi này trở nên cấp thiết:

- Ai nhận alert và xác định mức độ ảnh hưởng?
- Ai có quyền rollback bản phát hành vừa triển khai?
- Ai hiểu luồng nghiệp vụ và biết giao dịch nào có thể bị mất?
- Ai sở hữu database, queue, certificate, secret và dependency?
- Ai quyết định giảm tính năng, chuyển traffic hoặc kích hoạt DR?
- Ai thông báo cho khách hàng và người quản lý nghiệp vụ?
- Sau khi khôi phục, ai chịu trách nhiệm xử lý nguyên nhân gốc và ngăn tái diễn?

Nếu không có câu trả lời đã thống nhất, incident dễ bị chuyển vòng giữa các nhóm, mỗi nhóm chỉ kiểm tra phần của mình và không ai chịu trách nhiệm đến khi dịch vụ phục hồi.

**Service ownership** xác định một nhóm/đơn vị chịu trách nhiệm cho sức khỏe, hành vi và kết quả vận hành của dịch vụ. Ownership không có nghĩa một người phải tự làm mọi việc. Nó có nghĩa có một owner chịu trách nhiệm điều phối, giữ tài liệu và năng lực vận hành sẵn sàng, đồng thời biết khi nào cần gọi nhóm chuyên môn khác.

### 1.1. Ownership xuyên suốt vòng đời

Trách nhiệm không kết thúc khi merge code hoặc deploy production. Một dịch vụ cần ownership trong các giai đoạn:

| Giai đoạn | Trách nhiệm chính |
|---|---|
| Thiết kế | Xác định SLO, dependency, threat model, failure mode và kế hoạch vận hành |
| Build | Test, instrumentation, security control, migration và automation |
| Release | Release plan, canary, rollback, compatibility và change communication |
| Run | Theo dõi SLI, nhận alert, xử lý incident, capacity, backup và support |
| Improve | Post-incident review, giảm toil, sửa lỗi lặp lại và nâng độ tin cậy |
| Retire | Di chuyển consumer, lưu/xóa dữ liệu, thu hồi quyền, tắt alert và hạ tầng |

Ownership phải được bàn giao có chủ đích khi team thay đổi, dịch vụ chuyển sang platform hoặc hệ thống được chia/tách. Chỉ đổi tên team trong catalog mà không chuyển runbook, quyền, dashboard và lịch trực sẽ tạo khoảng trống trách nhiệm.

### 1.2. Phân biệt owner, operator và contributor

- **Service owner:** nhóm chịu trách nhiệm tổng thể về dịch vụ, SLO, rủi ro, vận hành và roadmap độ tin cậy.
- **Operator/on-call responder:** người đang trong ca trực, nhận alert và điều phối bước xử lý ban đầu.
- **Contributor:** nhóm cung cấp một dependency hoặc năng lực chuyên môn như database, network, identity, security hoặc platform.
- **Business/product owner:** người quyết định mức ưu tiên nghiệp vụ, tác động tới khách hàng và đánh đổi giữa khả năng phục vụ với rủi ro.

Một người có thể giữ nhiều vai trò ở nhóm nhỏ, nhưng trong incident lớn nên tách các vai trò có xung đột hoặc tải công việc cao. Ví dụ người đang debug database không nên đồng thời phải viết mọi thông báo khách hàng và điều phối toàn bộ incident.

## 2. Xác định ranh giới dịch vụ và owner

### 2.1. Ownership phải gắn với một service boundary

Service boundary cần đủ rõ để biết:

- API/event/job nào thuộc dịch vụ.
- Dữ liệu nào là source of truth và ai được thay đổi schema.
- Hạ tầng, database, queue, cache và tài khoản cloud nào được quản lý.
- Dependency nào thuộc team khác và hợp đồng hỗ trợ ra sao.
- SLI/SLO nào đo chất lượng của dịch vụ.
- Alert nào được gửi tới on-call team.
- Quy trình release, rollback, backup/restore và DR nằm ở đâu.

Nếu một alert chỉ ghi “platform slow” mà không có service, endpoint, region, tenant cohort và owner thì responder mất thời gian tìm phạm vi. Catalog và telemetry nên dùng cùng service identifier.

### 2.2. Service catalog tối thiểu

Một bản ghi catalog có thể gồm:

| Trường | Nội dung |
|---|---|
| service_id / name | Định danh ổn định của service |
| description | Mục đích và năng lực nghiệp vụ |
| owning_team | Nhóm chịu trách nhiệm chính |
| technical_owner | Đầu mối kỹ thuật, escalation |
| product_owner | Đầu mối quyết định ưu tiên nghiệp vụ |
| tier / criticality | Mức độ quan trọng và phạm vi hỗ trợ |
| SLO / SLA reference | Mục tiêu chất lượng và hợp đồng liên quan |
| dependencies | Service, database, queue, provider và owner |
| repo / pipeline | Mã nguồn, build, release, IaC |
| dashboards / alerts | Link dashboard, alert và telemetry |
| runbooks | Quy trình vận hành, rollback, restore, DR |
| data classification | Loại dữ liệu và yêu cầu bảo mật |
| support model | Giờ hỗ trợ, on-call, escalation path |
| lifecycle | Proposed, active, maintenance, deprecated, retired |

Catalog cần có owner kiểm tra định kỳ. Một bản ghi đầy đủ nhưng link hỏng, lịch trực cũ hoặc service đã đổi tên vẫn gây rủi ro. Tự động lấy metadata từ repository/deployment có thể giảm drift, nhưng các trường trách nhiệm và nghiệp vụ vẫn cần người xác nhận.

### 2.3. Một service, một accountable owner

Có thể có nhiều nhóm cùng đóng góp, nhưng cần một nhóm accountable cho kết quả end-to-end. Nếu ownership chia đôi không rõ, khi incident nhóm A có thể cho rằng vấn đề thuộc B và ngược lại.

Đối với capability dùng chung như identity, observability hoặc data platform, một platform team sở hữu dịch vụ nền; các product team vẫn chịu trách nhiệm cách tích hợp, cấu hình và sử dụng dependency đó. “Dùng platform” không loại bỏ trách nhiệm xử lý lỗi trong code hoặc policy do service team tạo ra.

## 3. Phân định trách nhiệm: RACI và ma trận hỗ trợ

### 3.1. RACI là gì?

RACI là cách làm rõ ai thực hiện và ai chịu trách nhiệm cuối cùng:

- **R — Responsible:** người/nhóm thực hiện công việc.
- **A — Accountable:** người/nhóm chịu trách nhiệm cuối cùng và quyết định kết quả; nên có một A rõ cho mỗi đầu việc.
- **C — Consulted:** người/nhóm được tham vấn trước quyết định.
- **I — Informed:** người/nhóm cần được thông báo.

RACI không thay thế incident command. Nó mô tả trách nhiệm thường xuyên; trong sự cố, incident commander điều phối theo vai trò đã được huấn luyện.

### 3.2. Ví dụ RACI cho một dịch vụ đặt lịch

| Hoạt động | Service team | Platform | Security | Product | Operations/Incident lead |
|---|---|---|---|---|---|
| Thiết kế API và business logic | A/R | C | C | C | I |
| SLO và error budget của service | R | C | I | A | C |
| Cluster/network nền | C | A/R | C | I | C |
| IAM policy và threat model | R | C | A | I | C |
| Release ứng dụng | A/R | C | C | I | I |
| Nhận alert service | A/R | C | C | I | R theo lịch |
| Incident ảnh hưởng khách hàng | R | C | C | A về business impact | A/R về điều phối incident |
| Khôi phục database | R cùng data owner | C | C | I | Điều phối |
| Thông báo khách hàng | C | I | C | A/R | C |
| Post-incident action | A/R cho service fixes | R cho platform fixes | R cho security fixes | C | Theo dõi action |

Ma trận minh họa cần được điều chỉnh theo tổ chức. Nếu role “operations” không tồn tại như một team riêng, responsibility có thể thuộc on-call engineer của service. Không để một hoạt động có nhiều A mà không định nghĩa quyền ra quyết định khi có bất đồng.

### 3.3. Ownership của dependency

Service phụ thuộc database platform, message broker, identity và network. Hợp đồng vận hành giữa consumer và provider cần xác định:

- Owner của dependency và kênh gọi hỗ trợ.
- SLO/availability hoặc support window của dependency.
- Giới hạn quota, timeout, retry và hành vi khi dependency lỗi.
- Dashboard/metric mà consumer được xem.
- Quy trình thay đổi breaking change và lịch bảo trì.
- Bên nào điều tra trước khi lỗi chưa rõ nằm ở đâu.

Một service team không cần có quyền admin database để sở hữu API. Tuy vậy, team cần đủ telemetry và quyền chẩn đoán; nếu mọi lần điều tra đều phải nhờ một cá nhân duy nhất, đó là rủi ro vận hành.

## 4. Thiết kế mô hình trực vận hành

### 4.1. On-call là gì?

**On-call** là cơ chế phân công người sẵn sàng phản hồi khi hệ thống cần hỗ trợ ngoài giờ làm việc thông thường hoặc trong một ca vận hành cụ thể. Người trực không có nghĩa phải liên tục thao tác hệ thống; mục tiêu là nhận tín hiệu quan trọng, đánh giá đúng mức độ và đưa incident tới người có khả năng xử lý.

Một mô hình trực cần xác định:

- Dịch vụ nào được trực 24/7, dịch vụ nào chỉ trong giờ làm việc?
- Alert nào gọi người trực, alert nào tạo ticket để xử lý ngày làm việc tiếp theo?
- Ai là primary, ai là secondary và ai là escalation manager?
- Thời gian xác nhận alert và thời điểm escalation là bao lâu?
- Kênh paging, điện thoại, chat và incident bridge nào được dùng?
- Người trực có quyền rollback, disable feature, failover hoặc hạn chế traffic đến đâu?
- Làm sao bàn giao ca, thay người khi nghỉ và xử lý khi responder không liên lạc được?

Mức trực phải phù hợp với business criticality và cam kết dịch vụ. Không nên tuyên bố hỗ trợ 24/7 nếu không có người, quyền, quy trình và dependency hỗ trợ tương ứng.

### 4.2. Các mô hình trực phổ biến

| Mô hình | Cách tổ chức | Phù hợp | Đánh đổi |
|---|---|---|---|
| **Business-hours support** | Một nhóm tiếp nhận trong giờ làm việc | Hệ thống nội bộ hoặc ít criticality | Sự cố ngoài giờ có thể chờ tới ca tiếp |
| **Follow-the-sun** | Các nhóm ở nhiều múi giờ chuyển giao ca | Tổ chức đa vùng, muốn giảm trực đêm | Handover và chuẩn hóa runbook phức tạp |
| **Primary/secondary rotation** | Primary nhận alert, secondary hỗ trợ khi escalation | Service team nhỏ/vừa | Cần đủ người và lịch công bằng |
| **Central NOC/SRE + service escalation** | NOC/SRE giám sát ban đầu, gọi service owner khi cần | Nhiều dịch vụ, tiêu chuẩn hóa vận hành | Dễ tạo tầng chuyển tiếp nếu NOC thiếu context |
| **Dedicated operations team** | Nhóm chuyên trách trực và vận hành | Workload lớn, quy trình ổn định | Có thể tạo khoảng cách giữa build và run |
| **Embedded service ownership** | Team xây dựng cũng trực service của mình | Product team sở hữu end-to-end | Cần đầu tư năng lực vận hành và giới hạn tải trực |

Follow-the-sun không đơn giản là có người ở ba múi giờ. Cần transfer context, ticket, incident timeline, quyền và trách nhiệm một cách rõ ràng. Nếu nhóm sau không biết trạng thái và hành động đang thực hiện, việc đổi ca có thể tạo lỗi thứ hai.

### 4.3. Sơ đồ primary/secondary

~~~mermaid
flowchart TD
    ALERT[Monitoring / Paging Alert] --> PAGE[On-call Scheduler]
    PAGE --> P[Primary Responder]
    P --> ACK{Acknowledged in target window?}
    ACK -->|Yes| TRIAGE[Triage and classify]
    ACK -->|No| S[Secondary Responder]
    S --> ACK2{Acknowledged?}
    ACK2 -->|Yes| TRIAGE
    ACK2 -->|No| M[On-call Manager / Escalation]
    M --> TRIAGE
    TRIAGE -->|Need specialist| SME[Service / Platform / Data SME]
    TRIAGE -->|Major incident| IC[Incident Commander]
    SME --> RESOLVE[Mitigate and recover]
    IC --> RESOLVE
    RESOLVE --> CLOSE[Validate, communicate and hand off follow-up]
~~~

Sơ đồ là luồng tham chiếu. Thời hạn acknowledge, retry paging và escalation cần dựa trên mức criticality, support agreement và khả năng nhân sự thực tế.

## 5. Xác định cấp độ trực và phạm vi dịch vụ

### 5.1. Phân tầng service criticality

Một cách phân loại tham khảo:

| Tier | Đặc điểm | Hỗ trợ có thể áp dụng |
|---|---|---|
| Tier 0 / Critical | Dừng gây ảnh hưởng rộng, giao dịch cốt lõi hoặc an toàn | 24/7 primary/secondary, major incident process, DR |
| Tier 1 / High | Nghiệp vụ quan trọng, có workaround hạn chế | 24/7 hoặc extended hours theo SLO |
| Tier 2 / Standard | Tác động có giới hạn, có thể trì hoãn | Business-hours/on-call best effort |
| Tier 3 / Internal | Công cụ nội bộ hoặc thử nghiệm | Ticket/office-hours, không paging trừ rủi ro đặc biệt |

Tier không chỉ phản ánh doanh thu. Cần xét số người bị ảnh hưởng, dữ liệu và compliance, dependency downstream, khả năng workaround, thời gian mất dịch vụ và hậu quả an toàn.

### 5.2. Alert severity và escalation

| Mức | Ví dụ | Phản ứng |
|---|---|---|
| SEV1 | Dịch vụ cốt lõi ngừng, mất dữ liệu hoặc ảnh hưởng diện rộng | Page ngay, incident commander, bridge, cập nhật định kỳ |
| SEV2 | Suy giảm nghiêm trọng, một nhóm khách hàng lớn bị ảnh hưởng, SLO burn nhanh | Page primary, thêm specialist, cân nhắc incident lead |
| SEV3 | Lỗi có workaround, phạm vi/ảnh hưởng giới hạn | Ticket hoặc page theo support policy |
| SEV4 | Cảnh báo thông tin, lỗi nhỏ không ảnh hưởng dịch vụ | Backlog, theo dõi trong giờ làm việc |

Tên severity và tiêu chí phải thống nhất toàn tổ chức. Không sử dụng SEV1 cho mọi alert; nếu mọi thứ đều urgent, người trực sẽ mất khả năng phân biệt.

### 5.3. Acknowledge, triage và resolution là ba mốc khác nhau

- **Acknowledge:** xác nhận alert đã có người tiếp nhận.
- **Triage:** xác định phạm vi, severity, symptom, owner và hành động tiếp theo.
- **Mitigation/recovery:** khôi phục dịch vụ hoặc giảm tác động.
- **Resolution:** xử lý nguyên nhân hoặc có giải pháp ổn định đã xác nhận.
- **Follow-up:** action để ngăn tái diễn, tăng khả năng phát hiện hoặc giảm thời gian phục hồi.

Đáp ứng thời gian acknowledge không đồng nghĩa incident đã được giải quyết. Dashboard cần phân biệt thời gian phát hiện, acknowledge, triage, mitigation và recovery.

## 6. Xây dựng lịch trực bền vững

### 6.1. Nguyên tắc thiết kế lịch

- Phân bổ công bằng theo kỹ năng, múi giờ, kinh nghiệm và khả năng hỗ trợ.
- Có primary và secondary thực sự khả dụng, không xếp trùng vào kỳ nghỉ hoặc thời gian không thể liên lạc.
- Tránh một người trực liên tiếp quá nhiều ngày/tuần hoặc trực nhiều service cùng lúc không có giới hạn.
- Dành thời gian nghỉ bù và giảm tải công việc ban ngày sau đêm có incident.
- Có backup khi người trực ốm, mất kết nối hoặc không thể tiếp tục ca.
- Xác định escalation khi service owner không phản hồi hoặc không có chuyên gia sẵn sàng.
- Kiểm tra quyền truy cập, thiết bị xác thực, VPN và công cụ paging trước khi bắt đầu ca.

Lịch trực là một phần của thiết kế hệ thống, không phải công việc hành chính. Nếu chỉ có một engineer hiểu cách restore database, service đang có single point of failure ở con người.

### 6.2. Ví dụ rotation tuần

| Tuần | Primary | Secondary | Escalation manager |
|---|---|---|---|
| 1 | Engineer A | Engineer B | Engineering Manager |
| 2 | Engineer B | Engineer C | Engineering Manager |
| 3 | Engineer C | Engineer A | Engineering Manager |
| 4 | Engineer A | Engineer C | Engineering Manager |

Bảng trên chỉ minh họa cách luân phiên với đội nhỏ, chưa phải lịch được khuyến nghị cho mọi nhóm. Cần xét số người đủ năng lực, luật lao động/chính sách nội bộ, ngày nghỉ và mức incident thực tế. Nếu đội không đủ người để trực an toàn, phải giảm support scope, tăng automation hoặc có thỏa thuận hỗ trợ khác; không thể giải quyết bằng cách dồn ca cho một cá nhân.

### 6.3. Handover giữa các ca

Handover nên ghi:

- Incident đang mở, severity và customer impact.
- Những điều đã thử, kết quả và giả thuyết còn lại.
- Hành động đang chạy, command/job chưa hoàn tất và rủi ro nếu dừng.
- Người liên hệ, bridge/ticket, incident commander và thời gian update tiếp theo.
- Dashboard/trace/query quan trọng và mốc thời gian.
- Quyết định đã được phê duyệt, rollback/mitigation đang có hiệu lực.
- Alert đang mute/silence và thời hạn kết thúc.

Không chuyển ca bằng một câu “đang xử lý”. Người nhận cần có đủ context để tiếp tục trong vài phút mà không lặp lại toàn bộ điều tra.

### 6.4. Sau ca trực

Theo dõi page volume, số incident ngoài giờ, thời gian gián đoạn giấc ngủ, số lần escalation và toil. Nếu một service liên tục đánh thức người trực vì lỗi không cần phản ứng ngay, cần sửa alerting hoặc reliability thay vì chấp nhận đó là bản chất công việc.

## 7. Alerting và observability phục vụ người trực

### 7.1. Page theo symptom và customer impact

Alert nên trả lời “người dùng hoặc nghiệp vụ đang bị ảnh hưởng thế nào?” thay vì chỉ “CPU cao”. CPU cao có thể là tín hiệu, nhưng page khi nó gắn với saturation/latency/error có ý nghĩa.

Alert tốt thường có:

- Service, environment, region, tenant cohort và endpoint.
- Severity, SLI/SLO đang vi phạm hoặc burn rate.
- Thời điểm bắt đầu, duration và xu hướng.
- Link dashboard, trace, log query và runbook.
- Owner/on-call schedule và escalation policy.
- Hành động đầu tiên an toàn, điều kiện dừng và cách rollback nếu có.

### 7.2. Golden signals và SLI

Các nhóm metric thường hữu ích:

| Nhóm | Ví dụ | Câu hỏi |
|---|---|---|
| Latency | p50/p95/p99, queue age | Người dùng chờ bao lâu? |
| Traffic | RPS, concurrent requests, messages/s | Tải tăng hay pattern đổi? |
| Errors | 5xx, timeout, failed jobs, business rejection | Có request thất bại hoặc nghiệp vụ sai không? |
| Saturation | CPU, memory, DB connection, IOPS, queue capacity | Dependency còn headroom? |
| Freshness | Replication lag, data age, last successful job | Dữ liệu có cập nhật đủ mới? |
| Availability | Successful eligible requests / total eligible requests | Dịch vụ có đáp ứng yêu cầu? |
| Business outcome | Booking completed, payment success, duplicate booking | Người dùng hoàn thành nghiệp vụ không? |

Metric cần phân biệt lỗi hệ thống và lỗi nghiệp vụ hợp lệ. Ví dụ booking bị từ chối vì slot đã hết không nhất thiết là lỗi availability; nhưng timeout khi xác nhận booking là symptom khác.

### 7.3. Alert fatigue

Alert fatigue xảy ra khi lượng cảnh báo quá lớn, nhiều cảnh báo lặp hoặc không cần hành động làm responder giảm chú ý. Cách giảm:

- Chỉ page khi có hành động cần thực hiện trong thời gian trực.
- Dùng ticket/notification cho vấn đề không khẩn.
- Gom alert theo incident/root symptom.
- Thiết lập deduplication, suppression có điều kiện và maintenance window.
- Đặt threshold dựa trên SLO, baseline và thời gian duy trì.
- Review page không hành động được và xóa/đổi metric.
- Có owner và thời hạn cho alert silenced; không mute vô thời hạn để làm dashboard xanh.

### 7.4. Runbook phải gần alert

Runbook nên có:

1. Symptom và điều kiện xác định incident.
2. Phạm vi/ảnh hưởng và kiểm tra an toàn ban đầu.
3. Dashboard, log, trace và query cần mở.
4. Lệnh hoặc thao tác read-only trước; hành động thay đổi sau.
5. Điều kiện escalation và khi nào phải dừng.
6. Cách mitigate, rollback hoặc failover cùng rủi ro.
7. Cách xác minh recovery và dữ liệu đúng.
8. Liên hệ owner, dependency và incident channel.

Command nguy hiểm cần mô tả quyền, tác động, precondition, phê duyệt và bước xác minh. Không đưa secret, token hoặc dữ liệu cá nhân vào runbook.

## 8. Incident response: vai trò và luồng điều phối

### 8.1. Các vai trò trong major incident

| Vai trò | Trách nhiệm |
|---|---|
| Incident Commander (IC) | Điều phối, đặt mục tiêu, phân công, quyết định escalation và giữ timeline |
| Operations/Technical Lead | Điều phối chẩn đoán và khôi phục kỹ thuật |
| Service Owner | Cung cấp context kiến trúc, SLO, dependency và quyết định trong phạm vi service |
| Communications Lead | Cập nhật nội bộ/khách hàng theo tần suất và mẫu đã thống nhất |
| Scribe | Ghi timeline, quyết định, hành động và bằng chứng |
| Subject Matter Expert (SME) | Hỗ trợ chuyên sâu database, network, security, cloud provider |
| Business/Product Owner | Đánh giá tác động nghiệp vụ, chọn workaround và ưu tiên phục hồi |

Incident nhỏ có thể một người đảm nhiệm nhiều vai trò. Khi incident lớn, tách IC khỏi người trực tiếp sửa hệ thống để tránh mất góc nhìn tổng thể.

### 8.2. Luồng xử lý incident

~~~mermaid
flowchart TD
    A[Alert or customer report] --> B[On-call acknowledge]
    B --> C[Triage: scope, severity, service]
    C --> D{Major incident?}
    D -->|No| E[Service responder investigates]
    D -->|Yes| F[Assign Incident Commander]
    F --> G[Create incident channel and roles]
    G --> H[Set objective and update cadence]
    E --> I[Mitigate / recover]
    H --> I
    I --> J[Validate user and business outcomes]
    J --> K{Stable?}
    K -->|No| I
    K -->|Yes| L[Communicate recovery and close]
    L --> M[Post-incident review and actions]
~~~

Tại mỗi giai đoạn, thông tin cần được chia sẻ trong một kênh incident chuẩn. Tránh điều phối bằng DM rời rạc khiến người khác không biết quyết định nào đã được đưa ra.

### 8.3. Update cadence

Major incident cần một tần suất cập nhật thống nhất, ví dụ mỗi 15 hoặc 30 phút tùy mức độ. Thông báo nên nêu:

- Điều gì đang xảy ra và phạm vi ảnh hưởng đã xác nhận.
- Tính năng/region/tenant nào bị ảnh hưởng; điều gì vẫn hoạt động.
- Workaround có sẵn hay không.
- Hành động đang thực hiện, thời điểm update tiếp theo.
- Những điều chưa biết được nói rõ; không suy đoán ETA khi chưa có cơ sở.

Thông báo recovery chỉ gửi sau khi service owner kiểm tra SLI và luồng nghiệp vụ cần thiết. Một dashboard xanh duy nhất chưa đủ nếu queue backlog vẫn tăng hoặc dữ liệu chưa được đối soát.

## 9. Service ownership gắn với SLO và error budget

### 9.1. SLI, SLO và SLA

- **SLI (Service Level Indicator):** phép đo chất lượng, ví dụ tỷ lệ request thành công hoặc p95 latency.
- **SLO (Service Level Objective):** mục tiêu nội bộ cho SLI trong cửa sổ xác định.
- **SLA (Service Level Agreement):** cam kết với khách hàng/đối tác, có thể kèm điều khoản/credit.

Service owner chịu trách nhiệm xây dựng, theo dõi và cải thiện SLO cùng product/business. SLO phải đo được bằng telemetry đủ tin cậy; định nghĩa eligible request, error, window và exclusion rõ.

Ví dụ giả định: 99,9% request booking đủ điều kiện phải thành công trong cửa sổ 30 ngày, với p95 latency dưới 300 ms ở tải được định nghĩa. Mục tiêu cụ thể cần kiểm chứng theo traffic, region và nghiệp vụ.

### 9.2. Error budget

Error budget là phần lỗi/gián đoạn được chấp nhận tương ứng với SLO. Nếu availability SLO là 99,9% trong 30 ngày, budget thời gian lý thuyết xấp xỉ:

~~~text
30 ngày × 24 giờ × 60 phút × (1 - 0,999)
= 43,2 phút
~~~

Đây là cách quy đổi minh họa khi SLI là availability theo thời gian; với request-based SLI, error budget được tính theo số request lỗi so với tổng request đủ điều kiện.

Khi budget tiêu thụ nhanh:

- Ưu tiên reliability work và giảm risk release.
- Có thể tạm dừng rollout tính năng rủi ro cao theo policy đã thống nhất.
- Điều tra các lỗi lặp, noisy neighbor và dependency.
- Thông báo product owner để điều chỉnh ưu tiên.

Error budget không phải quota được phép làm lỗi. Nó là công cụ cân bằng tốc độ phát triển và ổn định; quyết định pause release cần rõ quyền và tiêu chí.

### 9.3. Ownership của SLO dependency

Service team cần định nghĩa SLO end-to-end nhưng không nhất thiết sở hữu từng dependency. Ví dụ Booking API có SLO 99,9%, phụ thuộc database SLO 99,95%, identity và payment provider. Service owner cần:

- Đo latency/error tại điểm người dùng quan sát.
- Biết ngân sách lỗi của từng dependency.
- Có timeout, retry, circuit breaker và fallback hợp lý.
- Không cộng availability dependency một cách máy móc nếu có redundancy hoặc failure correlation.
- Thống nhất escalation với provider/owner.

## 10. Release, thay đổi và quyền vận hành

### 10.1. Ai có quyền thay đổi production?

Ownership cần định nghĩa quyền thao tác:

- Ai có thể deploy, rollback và chỉnh feature flag?
- Ai có thể thay đổi schema, IAM, network, key và firewall?
- Ai có thể failover database hoặc chuyển traffic region?
- Ai có thể xóa dữ liệu, queue hoặc resource?
- Hành động nào cần dual approval hoặc incident commander?

Không cấp quyền admin rộng cho toàn bộ on-call để tiện xử lý. Nên dùng role ngắn hạn, just-in-time access, audit và break-glass có phê duyệt theo policy.

### 10.2. Change management dựa trên rủi ro

Mỗi thay đổi production cần xác định:

- Scope, owner, phiên bản, dependency và khách hàng bị ảnh hưởng.
- Precondition, test, canary và success metric.
- Rollback/roll-forward plan và điều kiện kích hoạt.
- Database/schema backward compatibility.
- Monitoring, người theo dõi và thời điểm kết thúc.
- Phê duyệt bổ sung nếu thay đổi rủi ro cao.

Không phải mọi deploy đều cần họp duyệt thủ công. Pipeline với policy-as-code, test và progressive delivery có thể giảm rủi ro và toil; các thay đổi phá hủy hoặc ảnh hưởng dữ liệu/quyền cần mức kiểm soát cao hơn.

### 10.3. Run ownership và build ownership

Khi team phát triển không trực tiếp trực, cần có thỏa thuận rõ về:

- Ai xử lý alert đầu tiên và ai có quyền thay đổi code/config?
- Service owner có tham gia escalation trong khoảng thời gian nào?
- Platform có thể rollback hạ tầng mà không làm sai trạng thái ứng dụng?
- Ai xử lý migration, dữ liệu và consumer compatibility?
- Hỗ trợ ngoài giờ của vendor/managed service có SLA nào?

Mô hình build-and-run rút ngắn feedback loop nhưng cần đội có thời gian, kỹ năng và công cụ. Mô hình bàn giao cho operations chuyên trách cần tài liệu, automation và acceptance test; không thể coi bàn giao là chuyển trách nhiệm mà không chuyển năng lực.

## 11. Post-incident review và cải tiến liên tục

### 11.1. Review tập trung vào hệ thống

Post-incident review (PIR) nên tìm hiểu:

- Timeline và tác động thực tế.
- Trigger, contributing factors và điều kiện khiến lỗi lan rộng.
- Tín hiệu đã có, tín hiệu thiếu và thời điểm phát hiện.
- Quyết định, mitigation, điều gì hiệu quả/không hiệu quả.
- Khoảng trống ownership, permission, runbook hoặc dependency contract.
- Hành động để giảm xác suất, giảm blast radius, phát hiện sớm và phục hồi nhanh.

Review không nhằm tìm người để đổ lỗi. Nếu responder phải lựa chọn trong bối cảnh thông tin thiếu và công cụ hạn chế, cần cải thiện hệ thống để lần sau quyết định an toàn hơn.

### 11.2. Phân loại action

| Loại action | Ví dụ | Owner phù hợp |
|---|---|---|
| Prevent | Sửa race condition, quota, validation hoặc config unsafe | Service/platform owner |
| Detect | Thêm SLI, alert theo symptom, data integrity check | Service/SRE |
| Mitigate | Rate limit, feature flag, isolation, circuit breaker | Service/platform |
| Recover | Restore automation, rollback, failover/runbook | Service/data/platform |
| Learn | Cập nhật training, architecture decision, dependency map | Service owner/engineering manager |

Action cần có owner, priority, due date, acceptance criteria và trạng thái. “Cải thiện monitoring” không đủ cụ thể; “alert khi oldest queue age vượt 5 phút trong 3 cửa sổ và kèm runbook link” dễ kiểm chứng hơn.

### 11.3. Đóng vòng lặp

Service owner chịu trách nhiệm theo dõi action thuộc dịch vụ và phối hợp action liên nhóm. Engineering manager hoặc reliability review có thể kiểm tra action overdue và rủi ro được chấp nhận. PIR chỉ có giá trị khi các thay đổi được thực hiện và đo tác động sau đó.

## 12. Quản trị toil và năng lực đội trực

### 12.1. Toil là gì?

Toil là công việc vận hành lặp lại, thủ công, có thể dự đoán và không tạo nhiều giá trị dài hạn, ví dụ restart worker thủ công mỗi đêm, xử lý cùng một alert false positive, cấp credential lặp lại hoặc chạy script đối soát không có automation.

Theo dõi:

- Số page/ca, page không hành động, false positive.
- Thời gian xử lý lặp lại theo loại incident.
- Tỷ lệ ticket phải nhờ một chuyên gia duy nhất.
- Công việc thủ công định kỳ và phần trăm đã tự động hóa.
- Số runbook lỗi thời hoặc thao tác không thể thực hiện bằng role hiện có.

### 12.2. Giảm toil theo thứ tự

1. Xóa alert không hữu ích và sửa ngưỡng/dedup.
2. Làm rõ symptom, dashboard, runbook và escalation.
3. Tự động hóa thao tác read-only/chẩn đoán.
4. Tự động hóa mitigation an toàn với guardrail và rollback.
5. Khắc phục nguyên nhân gốc khiến thao tác lặp lại.
6. Đo lại page volume, MTTR và thời gian dành cho reliability work.

Không tự động hóa một thao tác nguy hiểm chỉ vì nó thường xảy ra. Automation production cần idempotency, permission scope, audit, rate limit, dry-run hoặc confirmation phù hợp, và điều kiện dừng an toàn.

### 12.3. Sức khỏe đội trực

Trực quá dày có thể gây mệt mỏi, giảm khả năng phán đoán và tăng lỗi. Tổ chức cần xem page volume cùng mức độ gián đoạn thực tế, đảm bảo nghỉ bù, quyền từ chối/đổi ca hợp lệ và đủ nhân lực backup. Nếu volume vượt khả năng nhóm, giải pháp là giảm lỗi, giảm alert, thêm người có kỹ năng hoặc thay support model; không bình thường hóa kiệt sức.

## 13. Kiến trúc vận hành: ownership trong môi trường cloud

### 13.1. Map ownership tới tài nguyên

Cloud resource nên gắn tag/label theo service, team, environment, cost center, data classification và owner. Từ đó có thể:

- Xác định ai quản lý resource khi có security alert.
- Truy vấn cost theo service/team.
- Biết tác động khi thay đổi shared VPC/database/cluster.
- Phân biệt resource production và thử nghiệm.
- Phát hiện orphan resource khi team hoặc service retired.

Tag không phải cơ chế authorization; IAM/policy vẫn phải thực thi quyền. Không để việc thiếu tag làm mất khả năng khôi phục một dịch vụ đang sự cố.

### 13.2. Shared platform và paved road

Platform team có thể cung cấp mẫu service, CI/CD, observability, secrets, network, deployment và runbook chuẩn. Paved road giảm gánh nặng cho product team nhưng cần hợp đồng rõ:

- Platform đảm bảo capability và support boundary nào?
- Product team chịu trách nhiệm cấu hình và code ở phần nào?
- Khi platform outage, escalation và status communication diễn ra ra sao?
- Có SLO cho platform API và service dependencies không?
- Cách nhận ngoại lệ và thời hạn chuyển về chuẩn?

Tự phục vụ tốt cần documentation, guardrail và default an toàn; không chỉ cung cấp portal tạo resource.

### 13.3. Dependency ownership map

~~~mermaid
flowchart TB
    subgraph Product[Product service]
        API[Booking API]
        WORKER[Notification Worker]
        DB[(Booking Database)]
    end
    subgraph Platform[Platform capabilities]
        NET[Network / Ingress]
        OBS[Observability]
        IAM[Identity / Secrets]
        MQ[Message Broker]
    end
    API --> DB
    API --> MQ
    WORKER --> MQ
    API --> IAM
    WORKER --> IAM
    API --> NET
    WORKER --> NET
    API -. telemetry .-> OBS
    WORKER -. telemetry .-> OBS
    DB -. telemetry .-> OBS
    OWN1[Booking team owns API, worker and data contract]
    OWN2[Platform team owns shared capabilities and SLO]
    OWN1 -.-> API
    OWN2 -.-> NET
~~~

Một dependency map nên có owner và escalation contact đi kèm từng node/edge. Sơ đồ không thay thế catalog; nó giúp nhìn ra nơi ownership hoặc support contract còn thiếu.

## 14. Quy trình xây dựng mô hình service ownership

Một nhóm có thể bắt đầu bằng quy trình sau:

1. **Inventory:** liệt kê service, resource, data, dependency, customer và business owner.
2. **Set criticality:** đánh giá impact, RTO/RPO, data sensitivity và support requirement.
3. **Assign owner:** chỉ định một owning team, technical owner, product owner và backup.
4. **Define service contract:** SLO/SLI, dependency, escalation, release và support window.
5. **Build operations kit:** dashboard, actionable alerts, runbook, access role, backup/restore và DR.
6. **Design rota:** primary/secondary, escalation, coverage, handover, holiday và backup staffing.
7. **Exercise:** giả lập alert, incident, rollback, dependency failure và restore.
8. **Measure:** page volume, MTTA, MTTR, SLO, toil, action closure và handover quality.
9. **Review:** định kỳ kiểm tra owner, catalog, rota, support scope và dependency contract.
10. **Transition/retire:** bàn giao ownership hoặc tắt dịch vụ cùng dữ liệu, quyền và monitoring.

### 14.1. Mẫu service ownership record

~~~text
Service: booking-api
Owning team: Booking Platform Product Team
Technical owner: On-call Engineering Lead
Product owner: Booking Product Manager
Criticality: Tier 0
Support: 24x7 primary + secondary
SLO:
  - successful eligible requests: 99.9% / 30 days
  - p95 latency: < 300 ms at defined load
Primary dashboard: [service dashboard reference]
Runbook: [incident and recovery runbook reference]
Dependencies:
  - booking-db (Data Platform Team)
  - identity (Platform Team)
  - event-broker (Messaging Team)
Escalation:
  - Primary -> Secondary -> Incident Commander
  - DB issue -> Data Platform on-call
Review date: [date]
~~~

Nội dung trong ngoặc vuông là chỗ cần điền bằng link thật của tổ chức, không phải địa chỉ đã tồn tại.

### 14.2. Mẫu escalation policy

| Điều kiện | Hành động | Owner |
|---|---|---|
| Alert SEV1/SEV2 | Page primary ngay | Scheduler |
| Primary chưa acknowledge trong target | Page secondary và gửi manager | Scheduler |
| Dependency thuộc team khác | Gọi dependency on-call, giữ service incident owner | Primary/IC |
| Ảnh hưởng diện rộng/đang tăng | Assign IC và mở incident bridge | Engineering manager/IC |
| Có rủi ro dữ liệu/bảo mật | Gọi security/data owner theo incident policy | IC |
| Phục hồi nhưng có backlog | Giữ incident theo dõi tới khi backlog/invariant đạt | Service owner |

Target time cần được điền theo service tier và chính sách hỗ trợ. Không có một thời gian acknowledge phù hợp cho mọi hệ thống.

## 15. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách cải thiện |
|---|---|---|
| Không có một owning team rõ | Incident chuyển vòng, action bị bỏ | Chỉ định accountable owner và catalog |
| Chỉ định một cá nhân làm owner duy nhất | Single point of failure, nghỉ phép là mất hỗ trợ | Ownership cấp team, backup và shared knowledge |
| Team build không có trách nhiệm run | Release tạo lỗi nhưng không ai xử lý end-to-end | Build/run contract và escalation rõ |
| NOC nhận alert nhưng thiếu context | Chuyển tiếp nhiều lần, MTTR tăng | Service catalog, runbook, symptom-based alert |
| Lịch trực không đủ backup | Không ai nhận page khi primary vắng mặt | Primary/secondary và escalation drill |
| Page mọi metric bất thường | Alert fatigue, bỏ sót incident thật | Page theo user impact/SLO và review alert |
| Không có quyền phù hợp trong ca trực | Responder phải chờ admin ngoài giờ | JIT access, role design và break-glass drill |
| Handover chỉ bằng lời nói | Lặp điều tra, bỏ sót hành động đang chạy | Incident log và handover template |
| Không đo page volume/toil | Không biết mô hình trực có bền vững | Theo dõi page, MTTA/MTTR và after-hours load |
| Post-incident không có owner/deadline | Lỗi lặp lại | Action cụ thể, acceptance criteria và tracking |
| Platform/product ownership chồng lấn | Không biết ai sửa lỗi ở boundary | RACI và dependency contract |
| Tuyên bố hỗ trợ 24/7 nhưng không có coverage | Kỳ vọng khách hàng sai và rủi ro SLA | Match support scope với nhân lực thực tế |

## 16. Bài thực hành: thiết kế ownership và on-call cho nền tảng đặt lịch

**Tình huống:** Một SaaS đặt lịch gồm Booking API, Notification Worker, relational database, event broker và dashboard analytics. Booking API xử lý giao dịch cốt lõi; notification có thể trễ; analytics có thể phục hồi trong ngày tiếp theo. Hiện có ba nhóm: Booking Product, Platform Engineering và Data Platform. Alert được gửi vào một kênh chat chung, không có service catalog hoặc lịch trực chuẩn.

Hãy đề xuất mô hình vận hành:

1. **Service inventory:** tách các service/capability, owner, dependency, data classification và criticality.
2. **RACI:** xác định accountable/responsible/consulted/informed cho deploy, incident, database restore, security incident, customer communication và post-incident action.
3. **Support tier:** gán Tier 0/1/2; quyết định support 24/7 hay business-hours và giải thích theo business impact.
4. **On-call rota:** thiết kế primary/secondary, escalation manager, backup khi nghỉ và handover.
5. **Alert taxonomy:** định nghĩa SEV1–SEV4, page vs ticket, acknowledge, triage và escalation condition.
6. **Observability/runbook:** chọn SLI cho booking, queue và analytics; tạo dashboard/alert có owner và hành động rõ.
7. **Incident process:** phân vai IC, technical lead, communications lead, scribe và SME; đặt update cadence.
8. **SLO/error budget:** đề xuất mục tiêu giả định, tính error budget và chính sách khi burn rate tăng.
9. **Access/release:** xác định JIT role, break-glass, quyền rollback, failover và thay đổi schema.
10. **Sustainability:** đo page load, toil, after-hours interruption, MTTA/MTTR và action closure.

### Bảng ownership mẫu

| Service/capability | Owning team | Tier | Support | SLI quan trọng |
|---|---|---|---|---|
| Booking API | Booking Product | 0 | 24x7 primary/secondary | Successful booking, p95 latency |
| Notification Worker | Booking Product | 1 | Extended hours hoặc 24x7 theo SLA | Oldest queue age, delivery success |
| Relational DB | Data Platform | 0 | 24x7 dependency escalation | Connection, transaction latency, replication lag |
| Event Broker | Platform Engineering | 1 | Platform on-call | Publish/consume error, backlog |
| Analytics | Data Platform/Analytics owner | 2 | Business-hours | Freshness, job success, completeness |

### Bảng kiểm tra readiness của ca trực

| Kiểm tra | Bằng chứng |
|---|---|
| Có primary và secondary | Scheduler hiển thị lịch hiện tại và ca tiếp |
| Acknowledge/escalation hoạt động | Test page tới primary rồi secondary |
| Có quyền an toàn | JIT role và break-glass đã diễn tập |
| Dashboard/runbook truy cập được | Link hoạt động, đúng environment |
| Dependency owner rõ | Catalog có contact và escalation |
| Handover đầy đủ | Mẫu incident log có đủ trạng thái và quyết định |
| Có cách thông báo | Channel, template, communications owner |
| Có post-incident process | Action tracker có owner/deadline |

**Tiêu chí hoàn thành:** Người review xác định được ai chịu trách nhiệm end-to-end cho mỗi service, ai nhận page, ai có quyền quyết định/khôi phục, escalation chạy thế nào và mô hình trực có bền vững với số người thực tế hay không. Các SLO và thời gian phản hồi chưa có bằng chứng phải được ghi là giả định cần xác minh.

## 17. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi về ownership và on-call | Bằng chứng |
|---|---|---|
| **Operational Excellence** | Service có owner, catalog, runbook, rota, handover và PIR không? | Ownership record, escalation drill, action closure |
| **Security** | Quyền trực, break-glass, audit và access review có đúng scope? | JIT access test, access log, role review |
| **Reliability** | Có người nhận alert và đủ kỹ năng/quyền để khôi phục theo SLO? | Paging drill, restore exercise, MTTA/MTTR |
| **Performance Efficiency** | Alert có phản ánh latency/traffic/saturation và workload thực? | SLI dashboard, page quality, capacity review |
| **Cost Optimization** | Mức trực, tooling và toil có phù hợp criticality? | Cost per service, page volume, toil tracking |
| **Sustainability** | Workload trực có bền vững, giảm interrupt và tự động hóa việc lặp? | After-hours load, rotation fairness, toil trend |

Ownership tốt giúp quyết định và hành động diễn ra nhanh, nhưng không phải để đẩy mọi trách nhiệm lên on-call. Mục tiêu của mô hình là dịch vụ có thể vận hành nhờ hệ thống, quy trình và kiến thức được chia sẻ, thay vì phụ thuộc vào một người luôn sẵn sàng.

## 18. Khung ghi nhớ

- **Service ownership** là trách nhiệm cấp nhóm đối với sức khỏe và kết quả vận hành của dịch vụ xuyên suốt vòng đời.
- **Một service cần accountable owner rõ**, service catalog, dependency map, SLO, dashboard và runbook.
- **RACI** làm rõ ai thực hiện, ai chịu trách nhiệm cuối cùng, ai được tham vấn và ai cần được thông báo.
- **On-call model** phải phù hợp criticality và năng lực nhân sự; primary cần secondary, escalation và handover.
- **Alert phải hành động được:** ưu tiên symptom/customer impact, SLO và saturation; giảm false positive và alert fatigue.
- **Incident response** cần IC, technical lead, communications, scribe và SME theo quy mô sự cố.
- **SLO/error budget** kết nối mục tiêu chất lượng với quyết định release và reliability work.
- **PIR và toil reduction** biến sự cố thành cải tiến có owner, deadline và acceptance criteria.

Phân định quyền sở hữu dịch vụ và mô hình trực vận hành biến trách nhiệm từ những thỏa thuận ngầm thành một hệ thống có thể nhìn thấy, kiểm tra và cải tiến. Khi owner, quyền, alert, runbook và escalation đã rõ, tổ chức có thể phản ứng nhất quán hơn, giảm thời gian phục hồi và duy trì chất lượng dịch vụ mà không đặt toàn bộ gánh nặng lên một vài cá nhân.
