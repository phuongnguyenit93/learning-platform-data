# Thiết kế runbook và quy trình xử lý sự cố

Hệ thống cloud có thể gặp lỗi ở nhiều lớp: ứng dụng, network, identity, database, queue, storage, dịch vụ bên thứ ba hoặc chính control plane của nhà cung cấp. Khi sự cố xảy ra, đội vận hành phải nhanh chóng hiểu tác động, phân công người xử lý, giảm thiểu thiệt hại, khôi phục dịch vụ và giữ bằng chứng để điều tra. Nếu mọi bước chỉ tồn tại trong trí nhớ của một vài kỹ sư, phản ứng dễ chậm, thao tác thiếu nhất quán và có thể làm sự cố nghiêm trọng hơn.

**Runbook** mô tả cách thực hiện một thao tác vận hành cụ thể. **Incident response playbook** mô tả cách phối hợp để xử lý một loại sự cố. **Incident management process** quy định vòng đời sự cố, vai trò, mức độ nghiêm trọng, giao tiếp, quyết định và tiêu chí đóng sự cố. Ba thành phần bổ trợ cho nhau.

Trong module **CLOUD_ARCHITECTURE**, bài học này tập trung vào thiết kế runbook và quy trình xử lý sự cố để vận hành dịch vụ cloud có thể dự đoán, đo lường và cải tiến. Mục tiêu là giúp đội ngũ biết **khi nào kích hoạt incident, ai chỉ huy, làm gì trước, cách thay đổi hệ thống an toàn, bằng chứng nào cần giữ và điều kiện nào chứng minh dịch vụ đã phục hồi**.

## 1. Runbook, playbook và incident process

| Thành phần | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Runbook** | Thực hiện một tác vụ vận hành như thế nào? | Failover database, rotate credential, drain node |
| **Playbook** | Xử lý một nhóm tình huống theo trình tự nào? | Database latency, credential compromise, region outage |
| **Incident process** | Tổ chức phối hợp, ra quyết định và thông báo ra sao? | Severity, incident commander, escalation, closure |
| **Standard operating procedure (SOP)** | Công việc lặp lại cần tuân thủ tiêu chuẩn nào? | Access review, backup verification, patch window |

Một runbook tốt không chỉ là danh sách lệnh. Nó cần nêu mục tiêu, phạm vi, điều kiện vào, quyền cần có, rủi ro, bước thực hiện, kết quả mong đợi, cách rollback/stop và bằng chứng hoàn tất.

### Khi nào cần runbook?

- Thao tác có tác động lớn hoặc khó đảo ngược.
- Sự cố lặp lại hoặc thường xảy ra ngoài giờ làm việc.
- Công việc có nhiều bước hoặc phụ thuộc nhiều nhóm.
- Có nguy cơ mất dữ liệu, downtime, ảnh hưởng bảo mật hoặc chi phí lớn.
- Cần người trực không phải chuyên gia sâu vẫn thực hiện được bước đầu an toàn.
- Cần bằng chứng tuân thủ hoặc audit.

Không phải mọi thao tác nhỏ đều cần tài liệu dài. Tập trung runbook vào quyết định và hành động có rủi ro, những bước thường bị quên và đường thoát khi kết quả không như dự kiến.

## 2. Vòng đời incident

Một incident có thể đi qua các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> Detected
    Detected --> Triaging
    Triaging --> Declared
    Triaging --> Resolved: False positive / transient
    Declared --> Containing
    Containing --> Investigating
    Investigating --> Recovering
    Recovering --> Monitoring
    Monitoring --> Resolved: Recovery criteria met
    Monitoring --> Investigating: Regression
    Resolved --> Closed: Review / evidence complete
    Closed --> [*]
~~~

Đây là mô hình khái niệm; một tổ chức có thể gộp hoặc đổi tên trạng thái. Điều quan trọng là mọi người biết trạng thái hiện tại, người chịu trách nhiệm, quyết định đang chờ và điều kiện chuyển bước.

### Các pha chính

1. **Detect:** nhận alert, report từ khách hàng, nhân viên hoặc nhà cung cấp.
2. **Triage:** xác định phạm vi, mức độ tác động và có cần khai báo incident không.
3. **Declare/organize:** lập kênh xử lý, chỉ định Incident Commander và các vai trò.
4. **Contain:** giới hạn ảnh hưởng, bảo vệ dữ liệu và ngăn sự cố lan rộng.
5. **Diagnose:** thu thập bằng chứng, lập giả thuyết và kiểm tra có kiểm soát.
6. **Mitigate/recover:** áp dụng biện pháp giảm thiểu, khôi phục chức năng.
7. **Verify/monitor:** xác nhận SLI và hành vi nghiệp vụ bình thường, theo dõi tái phát.
8. **Close/learn:** hoàn thiện timeline, thông báo, post-incident review và action items.

Không bắt buộc phải hoàn thành chẩn đoán nguyên nhân gốc trước khi khôi phục. Trong nhiều sự cố, giảm tác động an toàn trước, điều tra sâu sau khi dịch vụ ổn định.

## 3. Phân loại severity và mức tác động

Severity thể hiện mức nghiêm trọng của tác động hiện tại/dự kiến, giúp quyết định tốc độ phản ứng và mức huy động. Không nên chỉ phân cấp theo tên lỗi kỹ thuật.

Một ma trận ví dụ:

| Mức | Tác động | Phản ứng mẫu |
| --- | --- | --- |
| **SEV-1 Critical** | Dịch vụ trọng yếu ngừng diện rộng, mất dữ liệu nghiêm trọng, breach đang diễn ra hoặc safety/compliance impact lớn | Kích hoạt ngay, chỉ huy tập trung, cập nhật liên tục theo cadence |
| **SEV-2 High** | Một chức năng trọng yếu suy giảm đáng kể, nhiều khách hàng bị ảnh hưởng, workaround hạn chế | Huy động nhóm liên quan, escalation nhanh |
| **SEV-3 Medium** | Tác động một phần/nhóm nhỏ, có workaround, không có dấu hiệu lan rộng | Nhóm sở hữu xử lý trong giờ phản ứng quy định |
| **SEV-4 Low** | Lỗi nhỏ, suy giảm không trọng yếu hoặc vấn đề vận hành không ảnh hưởng đáng kể | Theo dõi và xử lý theo backlog/maintenance |

Tên, SLA và ngưỡng cụ thể do tổ chức định nghĩa. Một lỗi có thể tăng severity khi phạm vi hoặc rủi ro thay đổi. Người khai báo không nên ngại nâng mức khi chưa rõ tác động; severity có thể được hạ sau khi có bằng chứng.

### Tiêu chí đánh giá tác động

- Số khách hàng/tenant/user và tỷ lệ traffic bị ảnh hưởng.
- Chức năng nghiệp vụ: đăng nhập, thanh toán, đặt chỗ, export, quản trị.
- Mức độ gián đoạn: lỗi hoàn toàn, latency, dữ liệu sai, chỉ một region.
- Rủi ro bảo mật: truy cập trái phép, lộ dữ liệu, credential compromise.
- Tính toàn vẹn/durability: ghi mất, ghi trùng, dữ liệu không nhất quán.
- Thời gian ảnh hưởng và tốc độ lan rộng.
- Có workaround an toàn không và khách hàng có tự phục hồi được không.
- Nghĩa vụ pháp lý/hợp đồng và uy tín.

### Severity không phải priority của bug

Incident là sự kiện đang ảnh hưởng dịch vụ, còn backlog bug là công việc cần khắc phục. Một bug chưa gây tác động có thể priority cao nhưng chưa phải incident; một lỗi cấu hình nhỏ gây downtime lớn có thể là SEV-1. Tách hai khái niệm giúp điều phối đúng.

## 4. Vai trò và cấu trúc chỉ huy

Incident cần có người điều phối rõ ràng. Không để mọi người cùng sửa production hoặc nhiều người đưa ra quyết định trái nhau.

| Vai trò | Trách nhiệm |
| --- | --- |
| **Incident Commander (IC)** | Điều phối tổng thể, đặt mục tiêu, phân công, quyết định chuyển pha và giữ bức tranh chung |
| **Technical Lead** | Điều tra kỹ thuật, đề xuất mitigation/recovery, quản lý các thay đổi hệ thống |
| **Operations/Executor** | Thực hiện lệnh/runbook được giao, ghi kết quả và xác nhận |
| **Communications Lead** | Cập nhật stakeholder/khách hàng theo thông tin đã xác minh |
| **Scribe** | Ghi timeline, quyết định, giả thuyết, hành động và bằng chứng |
| **Domain/Service Owner** | Cung cấp kiến thức hệ thống và quyết định nghiệp vụ theo phạm vi |
| **Security/Privacy/Legal** | Tham gia khi có dấu hiệu breach, dữ liệu cá nhân hoặc nghĩa vụ pháp lý |

Ở đội nhỏ, một người có thể kiêm vai trò; nhưng IC không nên vừa điều phối vừa tự làm mọi thao tác kỹ thuật trong incident lớn. Phân vai giảm tải nhận thức và tăng khả năng quan sát.

### Nguyên tắc chỉ huy

- Một IC tại một thời điểm; khi đổi ca phải handover rõ.
- Mọi hành động production có owner và người thực hiện.
- Technical Lead đề xuất phương án, IC xác nhận ưu tiên/đánh đổi trong incident.
- Người ghi chép không cần tự suy đoán; ghi sự kiện, thời điểm và nguồn.
- Chỉ định một người thay thế khi vai trò chính rời khỏi incident.
- Không ra lệnh qua nhiều kênh chat không đồng bộ.

### RACI cho quyết định quan trọng

Trước incident, xác định ai Responsible, Accountable, Consulted và Informed cho: failover, disable feature, rollback release, rotate credential, data restore, customer notification và incident closure. Điều này đặc biệt quan trọng khi thao tác có ảnh hưởng bảo mật hoặc dữ liệu.

## 5. Thiết kế cấu trúc một runbook

Một template nhất quán giúp người trực tìm thông tin nhanh trong áp lực.

| Phần | Nội dung |
| --- | --- |
| Title/ID/owner | Tên, mã, service owner, ngày review |
| Purpose | Tình huống và mục tiêu |
| Trigger | Alert, symptom hoặc điều kiện bắt đầu |
| Scope/impact | Hệ thống, region, tenant và dữ liệu liên quan |
| Preconditions | Quyền, tool, access path, maintenance lock |
| Safety | Rủi ro, blast radius, không được làm |
| Diagnosis | Kiểm tra ban đầu, query/dashboard, giả thuyết |
| Actions | Bước thực hiện, expected output và checkpoint |
| Stop conditions | Khi nào dừng, escalation hoặc rollback |
| Recovery validation | SLI, business check và thời gian quan sát |
| Evidence | Log, event, command output, approval, ticket |
| Rollback | Cách đảo ngược hoặc phục hồi |
| Escalation | Người/nhóm liên hệ và thông tin cần cung cấp |
| Related docs | Architecture diagram, dashboard, service catalog |

### Viết bước hành động có thể kiểm chứng

Mỗi bước nên có cấu trúc:

1. **Action:** làm gì, trên resource nào và bằng identity nào.
2. **Expected result:** trạng thái/giá trị cần thấy.
3. **Verify:** lệnh/query/dashboard nào kiểm tra.
4. **If not expected:** dừng ở đâu và gọi ai.

Tránh ghi “restart service nếu cần” mà không nêu điều kiện, phạm vi replica, ảnh hưởng request đang xử lý, giới hạn concurrency và kiểm tra sau restart.

### Lệnh nguy hiểm

Lệnh xóa, restore, failover, rotate key hoặc thay firewall policy cần ghi rõ môi trường, resource ID, pre-check và yêu cầu approval. Dùng placeholder có tên rõ ràng; không nhúng credential/token hoặc lệnh chứa wildcard không giới hạn. Runbook nên có dry-run/preview nếu tool hỗ trợ.

## 6. Phát hiện và triage alert

Alert chỉ là tín hiệu để điều tra, không tự động là incident. Triage cần xác minh signal, phạm vi và tác động.

### Checklist triage ban đầu

1. Alert có còn firing hay đã tự hồi phục?
2. SLI nào bị ảnh hưởng: availability, latency, error rate, saturation, correctness?
3. Từ thời điểm nào và kéo dài bao lâu?
4. Tất cả region hay chỉ một AZ/service/tenant?
5. Có deployment, config change, traffic spike hoặc provider event gần thời điểm đó?
6. Có dấu hiệu security/data integrity?
7. Có workaround an toàn hoặc customer-visible impact?
8. Đã có incident tương tự đang mở chưa?

### Correlation

So sánh dashboard service với dependency, deploy timeline, cloud provider health, DNS/certificate, identity provider và network. Không kết luận root cause chỉ vì alert đầu tiên nằm ở một service; service đó có thể chỉ là nơi biểu hiện lỗi.

### Khử nhiễu alert

- Gom alert cùng symptom thành một incident.
- Dedupe theo resource/service và time window.
- Dùng alert theo user impact/SLO thay vì mọi ngưỡng tài nguyên.
- Giữ cảnh báo triệu chứng và nguyên nhân riêng khi có ích.
- Có owner, severity, runbook link và next action cho alert.
- Review false positive sau incident; không âm thầm tắt alert để giảm noise.

## 7. Thu thập bằng chứng và giữ timeline

Trước khi thay đổi trạng thái hệ thống, thu thập bằng chứng đủ để hiểu sự cố, trừ khi việc trì hoãn gây tác động lớn hơn. Với security incident, việc bảo toàn evidence có thể là yêu cầu trọng yếu.

### Evidence cần ghi

- Thời điểm UTC và timezone hiển thị.
- Incident ID, request/trace/correlation ID.
- Service, region, AZ, tenant hoặc resource bị ảnh hưởng.
- Alert, metric, log và trace liên quan.
- Deployment/config/policy change.
- Các lệnh đã chạy, người chạy, target và kết quả.
- Quyết định, người phê duyệt và lý do.
- Snapshot/backup/checkpoint nếu cần.
- Thông tin provider case hoặc external dependency.

### Timeline

| Thời điểm | Sự kiện/hành động | Người phụ trách | Kết quả/bằng chứng |
| --- | --- | --- | --- |
| 10:02 | Alert latency p99 fired | Monitoring | Dashboard link |
| 10:05 | Incident SEV-2 declared | IC | Incident channel |
| 10:10 | Rollout tạm dừng | Release owner | Deployment event |
| 10:18 | Traffic route sang pool khỏe | Technical lead | Error rate giảm |

Đây là timeline minh họa. Ghi thời điểm thực tế, không chỉnh sửa lịch sử để “đẹp”; correction nên được thêm như annotation có người và thời gian.

### Bảo toàn dữ liệu nhạy cảm

Không copy secret, private key, access token hoặc payload PII vào chat/ticket nếu không cần. Dùng reference tới log store có kiểm soát quyền. Security incident cần tuân thủ chain of custody và nơi lưu bằng chứng riêng.

## 8. Containment: giảm tác động trước khi điều tra sâu

Containment ngăn lỗi lan rộng hoặc giảm thiệt hại. Chọn biện pháp ít rủi ro nhất có thể đạt mục tiêu, hiểu blast radius và điều kiện rollback.

Các ví dụ:

- Dừng rollout hoặc rollback bản release mới.
- Tắt feature flag gây lỗi.
- Drain một node/AZ có vấn đề.
- Giới hạn concurrency/rate hoặc bật load shedding.
- Cô lập credential bị compromise, thu hồi session/token.
- Tạm ngừng consumer hoặc replication nếu đang lan truyền dữ liệu sai.
- Chuyển traffic sang region/pool dự phòng.
- Chặn endpoint/egress cụ thể theo policy bảo mật.

### Chọn containment theo loại rủi ro

| Sự cố | Containment có thể cân nhắc | Cảnh báo |
| --- | --- | --- |
| Release lỗi | Pause rollout/rollback | Kiểm tra migration đã chạy và backward compatibility |
| Database overload | Admission control, giảm query nặng | Không kill session hàng loạt nếu chưa hiểu transaction |
| Credential compromise | Revoke/rotate, isolate workload | Bảo đảm credential mới và dependency được đồng bộ |
| Data corruption | Dừng writer/consumer gây lỗi | Không restore trước khi xác định mốc dữ liệu tốt |
| Region outage | Route failover theo plan | Tránh split-brain và kiểm tra RPO |
| Queue backlog | Giảm producer/consumer concurrency | Đừng tăng consumer khi downstream đang lỗi |
| DDoS/abuse | WAF/rate limit/traffic filtering | Bảo vệ traffic hợp lệ và tránh block sai |

### Containment không phải recovery

Giảm tải hoặc tắt feature có thể làm tác động nhỏ lại nhưng dịch vụ chưa chắc đã phục hồi hoàn toàn. Ghi rõ trạng thái degraded, chức năng còn thiếu và rủi ro tồn tại; không đóng incident chỉ vì alert chính hết firing.

## 9. Diagnosis có kỷ luật

Trong incident, nhiều giả thuyết có thể cùng hợp lý. Thay vì thực hiện nhiều thay đổi cùng lúc, lập giả thuyết, chọn phép kiểm tra phân biệt và ghi kết quả.

### Hypothesis-driven troubleshooting

| Trường | Ví dụ |
| --- | --- |
| Observation | API p99 tăng từ 200 ms lên 4 giây |
| Hypothesis | Connection pool bị cạn do database chậm |
| Test | So pool wait, active connections, DB query latency |
| Expected if true | Pool wait tăng trước khi request timeout |
| Result | Pool wait tăng, DB CPU bình thường |
| Next step | Kiểm tra connection leak/long transaction |

### Thay đổi một biến khi có thể

Nếu cùng lúc tăng pool size, đổi timeout và restart database, rất khó biết thay đổi nào giúp hoặc gây lỗi. Thử từng biện pháp nhỏ, có checkpoint và rollback; ngoại lệ là tình huống khẩn cấp cần nhiều hành động đồng thời để ngăn thiệt hại, khi đó ghi rõ quyết định.

### Phân biệt symptom, trigger và root cause

- **Symptom:** điều người dùng/monitor quan sát.
- **Trigger:** sự kiện ngay trước khi sự cố bắt đầu.
- **Root cause/contributing factors:** điều kiện nền khiến sự cố xảy ra hoặc khuếch đại.

Một deployment có thể là trigger, nhưng root cause nằm ở thiếu capacity headroom hoặc schema không backward-compatible. Postmortem cần nhìn hệ thống, không dừng ở sự kiện gần nhất.

## 10. Recovery và xác minh dịch vụ

Recovery đưa hệ thống trở lại trạng thái phục vụ an toàn. “Process đang chạy” hoặc “HTTP 200 trở lại” không đủ chứng minh hệ thống phục hồi.

### Các chiều xác minh

- **Availability:** request hợp lệ được phục vụ.
- **Latency:** p95/p99 trở về vùng SLO hoặc ngưỡng degraded đã thống nhất.
- **Correctness:** dữ liệu và kết quả nghiệp vụ đúng.
- **Durability:** write quan trọng đã được commit và có khả năng phục hồi.
- **Security:** credential, policy và access path đã được kiểm soát.
- **Capacity:** hệ thống chịu được tải hiện tại và headroom hợp lý.
- **Backlog:** queue, retry và pending operation được xử lý ổn định.

### Quy trình recovery có kiểm soát

1. Xác định trạng thái an toàn mục tiêu và dữ liệu authoritative.
2. Kiểm tra điều kiện trước khi khôi phục: backup, replication lag, migration, credential, capacity.
3. Thực hiện một thay đổi nhỏ hoặc canary nếu có thể.
4. Kiểm tra smoke test và business transaction.
5. Tăng traffic/concurrency theo từng bước.
6. Theo dõi SLI, queue age, error budget và side effect bất thường.
7. Xác minh không có retry storm hoặc backlog thứ cấp.
8. Ghi lại thời điểm mitigation/recovery và người xác nhận.

### Đừng khôi phục tất cả cùng lúc

Sau outage dài, bật đồng thời mọi worker, consumer và scheduled job có thể tạo surge. Ramp-up theo batch, giới hạn concurrency và ưu tiên chức năng trọng yếu. Kiểm tra downstream trước khi mở toàn bộ traffic.

## 11. Runbook: database latency hoặc connection exhaustion

### Trigger

- API p95/p99 tăng.
- DB connection pool wait/timeout tăng.
- Database CPU, IOPS, lock wait hoặc replication lag bất thường.
- Error rate query tăng hoặc transaction mở lâu.

### Triage

1. Xác định ảnh hưởng theo database/cluster/region và endpoint.
2. So sánh thời điểm deployment, migration, batch job và traffic spike.
3. Kiểm tra active connections, pool wait, slow query, lock, CPU, memory và I/O.
4. Phân biệt DB quá tải với connection leak ở application.
5. Xác định read/write và tenant nào đang chiếm phần lớn tải mà không lộ dữ liệu nhạy cảm.

### Containment

- Tạm dừng batch/report query không trọng yếu.
- Giảm concurrency hoặc rate limit endpoint gây tải.
- Bật cache/stale serving chỉ với dữ liệu cho phép.
- Hạn chế pool mới nếu tổng connection vượt quota database.
- Nếu có connection leak, drain/restart instance theo từng nhóm sau khi cân nhắc request đang chạy.

### Recovery

- Xác minh connection count, pool wait, DB latency và query throughput trở lại ổn định.
- Chạy transaction kiểm tra đọc/ghi an toàn.
- Theo dõi lock/replication lag và backlog.
- Tăng traffic dần, bật lại batch theo lịch.

**Stop condition:** không tăng pool size mù khi database đã chạm connection limit; không kill transaction hoặc failover database nếu chưa biết tác động tới consistency/RPO.

## 12. Runbook: deployment hoặc configuration lỗi

### Trigger

- Error rate tăng ngay sau release.
- Health check fail trên phiên bản mới.
- Latency hoặc memory/CPU thay đổi bất thường.
- Một region/AZ có behavior khác do config drift.

### Triage

1. Ghi release ID, commit/config version và thời điểm rollout.
2. Xác định cohort/version/region bị ảnh hưởng.
3. So deployment event với SLI và log error.
4. Kiểm tra schema migration, secret, feature flag và dependency compatibility.
5. Xác định rollback có an toàn không.

### Containment và recovery

- Pause rollout/canary progression.
- Tắt feature flag nếu lỗi được cô lập và flag có semantics an toàn.
- Rollback artifact/config nếu schema và dữ liệu tương thích.
- Nếu database migration đã destructive, dùng forward fix hoặc recovery plan; không rollback binary một cách máy móc.
- Sau rollback, kiểm tra mọi instance đã về phiên bản/config mục tiêu.
- Chạy smoke test cho hành trình nghiệp vụ, không chỉ liveness endpoint.

**Stop condition:** không rollback database migration hoặc secret rotation nếu chưa hiểu tương thích hai chiều. Ghi phiên bản cũ/mới và lệnh thay đổi để tránh một instance còn dùng config khác.

## 13. Runbook: region/AZ outage và failover

### Trigger

- Health check/provider status xác nhận một failure domain không khả dụng.
- Traffic error/latency tập trung tại region/AZ.
- Control plane/data plane bị ảnh hưởng.

### Triage

1. Xác định scope: một AZ, toàn region, control plane hay một dịch vụ.
2. Kiểm tra provider health và telemetry độc lập.
3. Xác định replication lag, last known good write và RPO.
4. Xác định region dự phòng có capacity, key access, network và dependency.
5. Xác nhận hiện có primary/writer nào đang hoạt động để tránh split-brain.

### Failover

- Dùng runbook/provider procedure đã diễn tập.
- Fence/disable writer cũ theo cơ chế được hỗ trợ trước khi promote writer mới.
- Kiểm tra replication/data consistency và quyết định chấp nhận RPO.
- Chuyển traffic từng phần và xác minh DNS/service discovery/client connection.
- Theo dõi connection storm, cache warm-up, queue backlog và downstream quota.

### Failback

Failback không phải đơn giản đổi route về region cũ. Cần đồng bộ dữ liệu, xác định writer, kiểm tra replication direction, chuyển quyền sở hữu có kiểm soát và chuẩn bị rollback. Không chạy active-active nếu thiết kế dữ liệu không hỗ trợ concurrent write.

**Stop condition:** không promote replica khi chưa hiểu lag/data loss và không để hai writer hoạt động đồng thời ngoài mô hình đã thiết kế.

## 14. Runbook: credential compromise hoặc nghi ngờ data breach

Đây là incident có yêu cầu bảo toàn evidence và phối hợp Security/Privacy/Legal. Runbook nên được thiết kế cùng nhóm chuyên trách; người trực không tự suy đoán nghĩa vụ thông báo.

### Containment

1. Kích hoạt security incident channel và chỉ định incident lead phù hợp.
2. Xác định principal/credential/resource bị ảnh hưởng.
3. Revoke/disable credential hoặc session theo trình tự tránh khóa nhầm hệ thống phục hồi.
4. Cô lập workload/network/path nghi bị compromise.
5. Thu hồi quyền rộng, chặn egress hoặc session bất thường theo policy.
6. Bảo toàn audit, logs, image/snapshot và request ID.
7. Kiểm tra persistence, lateral movement và dữ liệu đã bị truy cập/export.

### Recovery

- Tạo credential mới bằng secret manager/rotation flow, không tái sử dụng bí mật cũ.
- Vá nguyên nhân cấp quyền/secret exposure.
- Chỉ mở lại workload sau khi xác minh image/config và identity.
- Theo dõi truy cập bất thường, data exfiltration và policy change.
- Privacy/Legal đánh giá phạm vi dữ liệu, nghĩa vụ và nội dung thông báo theo quy định áp dụng.

Không xóa log hoặc rebuild môi trường trước khi bảo toàn bằng chứng cần thiết. Không tự gửi thông báo ra ngoài khi chưa theo quy trình được ủy quyền.

## 15. Runbook: queue backlog và consumer lỗi

### Trigger

- Oldest message age vượt SLA.
- Queue depth tăng liên tục.
- DLQ tăng.
- Consumer error/timeout và dependency load tăng.

### Triage và containment

1. Xác định topic/partition/subscription và event type.
2. So producer rate, consumer throughput, retry/redelivery và dependency latency.
3. Kiểm tra poison message, schema mismatch và consumer deploy.
4. Giảm producer hoặc consumer concurrency nếu downstream quá tải.
5. Tách message lỗi sang DLQ/quarantine, tránh retry tức thì vô hạn.
6. Giữ idempotency/event order trong quá trình replay.

### Recovery

- Khôi phục consumer version/config.
- Kiểm tra dependency quota và capacity.
- Replay batch nhỏ từ DLQ sau khi sửa nguyên nhân.
- Theo dõi oldest message age và drain rate.
- Kiểm tra duplicate side effect và event bị mất/đến sai thứ tự.

**Stop condition:** không tăng worker nếu downstream là bottleneck; không replay DLQ hàng loạt trước khi biết message có thể tạo side effect trùng hay không.

## 16. Runbook: data corruption hoặc xóa nhầm

### Trigger

- Checksum mismatch, record count giảm bất thường.
- Khách hàng báo mất/sai dữ liệu.
- Audit ghi nhận bulk delete/overwrite ngoài kế hoạch.
- Pipeline tạo dữ liệu sai và lan sang replica/search/analytics.

### Triage

1. Dừng hoặc giới hạn writer/job gây hỏng dữ liệu.
2. Xác định loại dữ liệu, tenant, table/bucket/prefix và mốc sự cố.
3. Tìm last known good backup/version/transaction log.
4. Kiểm tra replication đã lan truyền lỗi chưa.
5. Bảo toàn audit, manifest, checksum và evidence.

### Recovery

- Restore vào môi trường cô lập trước.
- So checksum, count, version và business invariant.
- Áp deletion/retention/legal hold và các event cần replay.
- Chọn partial restore, point-in-time recovery hoặc forward correction theo blast radius.
- Chuyển traffic sau khi Data Owner/Technical Lead xác nhận dữ liệu đúng.
- Theo dõi sự kiện tái diễn và các projection downstream.

**Stop condition:** không restore đè trực tiếp production khi chưa xác định mốc tốt, không xóa evidence và không coi replication là backup độc lập.

## 17. Giao tiếp trong incident

Thông tin rõ ràng làm giảm số câu hỏi lặp lại và tránh các nhóm đưa ra quyết định dựa trên giả định khác nhau. Incident communication cần tách kênh điều phối nội bộ, kênh kỹ thuật và thông báo stakeholder/khách hàng.

### Nội dung cập nhật

Mỗi update nên nêu:

- Incident ID và severity hiện tại.
- Tóm tắt tác động đã xác minh.
- Thời điểm bắt đầu/ước lượng hiện tại, nếu đã có bằng chứng.
- Hệ thống/region/chức năng bị ảnh hưởng.
- Biện pháp đang thực hiện và kết quả.
- Workaround an toàn cho người dùng, nếu có.
- Việc đang điều tra và điều chưa biết.
- Thời điểm cập nhật tiếp theo.

Không suy đoán root cause hoặc cam kết thời gian khôi phục nếu chưa có cơ sở. Nói rõ “chưa xác định” tốt hơn đưa ra một kết luận có vẻ chắc chắn nhưng sai.

### Cadence theo severity

Tổ chức có thể định nghĩa cadence khác nhau cho SEV-1/2/3. Ví dụ incident nghiêm trọng được cập nhật ngắn theo chu kỳ 15–30 phút, hoặc ngay khi có thay đổi trọng yếu; incident thấp hơn có thể cập nhật theo giờ. Cadence phải đủ để stakeholder biết tình trạng mà không làm IC mất thời gian điều phối.

### Mẫu status update

~~~text
Incident: INC-2026-042
Severity: SEV-2
Status: Mitigating
Impact: Một phần request tạo booking tại region-2 bị timeout.
Start: 10:02 UTC (đang xác minh phạm vi đầy đủ).
Actions: Đã pause rollout; đang chuyển traffic từng phần sang pool khỏe.
Known risks: Một số operation có trạng thái payment chưa xác định; đang đối soát.
Next update: 10:30 UTC hoặc sớm hơn khi có thay đổi trọng yếu.
~~~

Mẫu trên minh họa cấu trúc; dùng thời gian, tên hệ thống và mức độ đã xác minh cho incident thực tế.

### Customer communications

Thông báo khách hàng cần tập trung vào tác động và hành động họ có thể làm:

- Tính năng nào bị ảnh hưởng?
- Dữ liệu có bị mất/sai hay chỉ chậm/không truy cập?
- Có workaround an toàn không?
- Đã khôi phục hay vẫn đang degraded?
- Khi nào có update tiếp theo?

Thông tin về breach, dữ liệu cá nhân hoặc nghĩa vụ thông báo phải được Security/Privacy/Legal duyệt theo policy và quy định áp dụng.

## 18. Escalation và gọi đúng chuyên gia

Runbook cần escalation path rõ:

- Primary on-call và secondary on-call.
- Service owner/domain expert.
- SRE/platform/network/database/security.
- Cloud provider support.
- Third-party vendor/payment provider.
- Incident executive/business owner.
- Privacy/legal/compliance khi liên quan dữ liệu hoặc nghĩa vụ.

### Thông tin khi escalation

Đừng chỉ gửi “service đang lỗi”. Cung cấp:

1. Incident ID và severity.
2. Impact/region/tenant/time window.
3. SLI và symptom cụ thể.
4. Những bước đã làm và kết quả.
5. Giả thuyết đang kiểm tra, điều chưa biết.
6. Quyết định cần người nhận hỗ trợ.
7. Link dashboard/log/trace đã cấp quyền.

### Escalation khi không có phản hồi

Định nghĩa timeout escalation: sau bao lâu không ack thì gọi số dự phòng/manager. Với SEV-1, không chờ hết nhiều chu kỳ chat; dùng kênh paging/phone được phê duyệt. Hạn chế chia sẻ secret hoặc dữ liệu khách hàng trong kênh không phù hợp.

## 19. Handover giữa ca trực

Incident có thể kéo dài qua nhiều giờ hoặc nhiều ngày. Handover phải chuyển cả trách nhiệm và bối cảnh, không chỉ gửi link chat.

### Handover checklist

- Incident ID, severity và trạng thái.
- Impact hiện tại và thời gian bắt đầu.
- IC/Technical Lead/Communications Lead hiện tại.
- Những giả thuyết đã kiểm tra và kết quả.
- Thay đổi production đã thực hiện, phiên bản/config hiện tại.
- Rủi ro còn mở và operation chưa xác định.
- Các việc tiếp theo, owner và deadline.
- Alert/dashboard/log/trace và provider case.
- Quyết định cần phê duyệt.
- Lịch cập nhật stakeholder tiếp theo.

### Handover đồng bộ

Với incident nghiêm trọng, outgoing IC tóm tắt trực tiếp và incoming IC xác nhận đã nhận quyền điều phối. Cập nhật incident channel, ticket và contact tree. Không để hai IC cùng nghĩ người kia đang chỉ huy.

## 20. Tiêu chí recovery và đóng incident

Một incident chỉ nên chuyển Resolved khi tiêu chí kỹ thuật và nghiệp vụ đã đạt. Incident đóng sau khi các việc hậu kiểm và bằng chứng tối thiểu được hoàn tất hoặc được chuyển thành action item có owner.

### Recovery acceptance criteria

- SLI chính trở về ngưỡng mục tiêu trong một khoảng quan sát đủ dài.
- Hành trình nghiệp vụ đầu-cuối hoạt động, không chỉ health endpoint.
- Data integrity/durability được xác minh hoặc trạng thái unknown được quản lý.
- Queue backlog/retry/pending jobs đang drain ổn định.
- Security controls/credential/policy đã được phục hồi an toàn.
- Không còn traffic route tới node/version lỗi ngoài kế hoạch.
- Capacity có đủ headroom cho tải hiện tại.
- Không có dấu hiệu regression sau khi ramp-up.

### Resolved khác với Closed

Resolved nghĩa là tác động hiện tại đã kết thúc hoặc được giảm xuống mức chấp nhận. Closed nghĩa là incident record có timeline, impact, communication, evidence và post-incident review/action items theo quy trình. Một sự cố có thể Resolved nhưng vẫn còn việc follow-up.

### Theo dõi sau phục hồi

Đặt monitoring period dựa trên đặc tính lỗi. Với lỗi chỉ xuất hiện theo chu kỳ, quan sát đủ một chu kỳ hoặc kiểm tra synthetic. Không hạ severity quá sớm khi queue vẫn tích tụ hoặc operation chưa đối soát.

## 21. Post-incident review và blameless postmortem

Postmortem tìm hiểu cách hệ thống và quy trình cho phép sự cố xảy ra, vì sao phát hiện/chặn/khôi phục mất thời gian và cách giảm khả năng tái diễn. Mục tiêu là học hỏi và cải thiện, không quy lỗi cá nhân.

### Nội dung postmortem

1. Executive summary: điều gì xảy ra và tác động.
2. Timeline: sự kiện, quyết định và hành động theo thời gian.
3. Impact: khách hàng, tenant, data, SLO, financial/contractual impact.
4. Detection: alert nào phát hiện, alert nào thiếu hoặc nhiễu.
5. Root cause và contributing factors.
6. What went well / what was difficult.
7. Mitigation/recovery effectiveness.
8. Action items có owner, priority và due date.
9. Lessons cho architecture, runbook, test, monitoring và training.

### Blameless không có nghĩa không có accountability

Phân tích tập trung vào điều kiện hệ thống, guardrail, thông tin sẵn có và áp lực ra quyết định. Vẫn cần owner cụ thể để sửa lỗi, theo dõi deadline và đo kết quả. Tránh mô tả kiểu “operator quên bước X” nếu hệ thống không có automation/checklist để ngăn lỗi có thể dự đoán.

### Action item tốt

Action cần có:

- Hành động cụ thể, không chỉ “cải thiện monitoring”.
- Owner là cá nhân/nhóm chịu trách nhiệm.
- Priority và due date.
- Tiêu chí hoàn thành có thể kiểm tra.
- Link incident/ticket và metric xác minh.

Ví dụ: “Thêm alert khi oldest message age của payment-events vượt 5 phút trong 3 cửa sổ liên tiếp; owner Payments SRE; verify bằng test backlog.” Ngưỡng thực tế cần dựa vào SLA.

## 22. Quản lý thay đổi khẩn cấp trong incident

Emergency change có thể cần thiết để giảm tác động nhưng vẫn phải được kiểm soát.

### Guardrail

- Xác định người có quyền approve.
- Nêu mục tiêu, blast radius và risk.
- Dùng thay đổi nhỏ nhất có thể.
- Có pre-check, verification và rollback.
- Ghi ai chạy, lệnh/config, thời điểm và kết quả.
- Review sau incident và cập nhật IaC/config source để tránh drift.

Không sửa trực tiếp cloud console rồi bỏ quên IaC; lần deploy tiếp theo có thể ghi đè hoặc tạo drift khó hiểu. Nếu bắt buộc thay đổi trực tiếp, tạo follow-up để đồng bộ source of truth.

### Break-glass access

Break-glass cho phép truy cập đặc quyền khi quy trình bình thường không đáp ứng thời gian phản ứng. Cần MFA/strong authentication, cấp quyền ngắn hạn, phê duyệt hoặc thông báo hậu kiểm, audit độc lập, cảnh báo sử dụng và thu hồi sau incident. Không dùng break-glass làm tài khoản vận hành thường ngày.

### Risk/rollback decision

Một mitigation có thể giảm downtime nhưng tăng rủi ro data loss. IC và Technical Lead cần ghi rõ trade-off, RPO/RTO, approval và điều kiện dừng. Với security incident, phối hợp Security/Legal trước hành động có thể làm mất evidence.

## 23. Operational readiness trước khi phát hành

Một service chưa sẵn sàng vận hành nếu chỉ có deployment pipeline và dashboard. Trước production, cần xác minh nhóm trực biết cách phát hiện, điều tra, rollback và phục hồi.

### Operational readiness review

- Có service owner, on-call rotation và escalation path.
- Có sơ đồ dependency, data flow, trust boundary và failure domain.
- Có SLI/SLO, dashboard, alert và synthetic check.
- Có runbook cho failure mode có impact lớn.
- Có backup/restore, DR và RPO/RTO đã thử.
- Có capacity limit, quota, autoscaling và load shedding.
- Có deploy/rollback và emergency change procedure.
- Có credential/secret rotation và security incident path.
- Có logging/tracing/audit đủ dùng mà không lộ secret/PII.
- Có retention, data ownership và processor contact nếu cần.
- Có status page/customer communication template.
- Có record known risks, limitations và dependency SLA.

### Service catalog

Service catalog có thể lưu:

| Trường | Mục đích |
| --- | --- |
| Service name/owner | Xác định nhóm chịu trách nhiệm |
| Criticality/SLO | Biết mức ưu tiên |
| Dependencies | Liên hệ đúng nhóm khi sự cố |
| Runtime/region | Biết nơi đang chạy |
| Data classification | Biết rủi ro dữ liệu |
| Dashboard/alerts | Vào đúng công cụ |
| Runbooks/playbooks | Tìm quy trình xử lý |
| On-call/escalation | Gọi đúng người |
| Backup/DR | Biết phương án phục hồi |
| Change history | Tra cứu thay đổi gần đây |

Catalog cần có owner và quy trình cập nhật; danh sách cũ có thể gây chậm phản ứng hơn không có thông tin.

## 24. SLI, SLO, error budget và incident policy

SLI là chỉ số phản ánh trải nghiệm/kết quả dịch vụ; SLO là mục tiêu cho SLI trong một cửa sổ; error budget là phần lỗi/suy giảm được phép trong mục tiêu đó.

Ví dụ:

- Availability: tỷ lệ request hợp lệ hoàn tất thành công.
- Latency: tỷ lệ request hoàn tất dưới ngưỡng.
- Durability/correctness: tỷ lệ transaction được lưu đúng hoặc không mất.
- Freshness: độ trễ dữ liệu projection.
- Job completion: tỷ lệ job hoàn tất trước deadline.

### SLO ảnh hưởng incident response

Khi burn rate tăng nhanh, hệ thống có thể kích hoạt alert nghiêm trọng và ưu tiên reliability work. Khi error budget đã cạn, tổ chức có thể hạn chế release rủi ro hoặc thay đổi tập trung vào độ ổn định. Không chỉ alert theo CPU 90% nếu người dùng chưa bị ảnh hưởng; CPU là saturation signal, còn SLI phản ánh service outcome.

### Multi-window burn-rate alert

Một alert có thể so mức tiêu thụ error budget ở cửa sổ ngắn và dài để phát hiện sự cố nhanh nhưng tránh noise. Ngưỡng burn rate và cửa sổ phải gắn SLO, traffic và hậu quả; không sao chép cùng một config cho mọi service.

### Error budget policy

Quy định trước cách sử dụng error budget:

- Khi nào pause feature release.
- Khi nào ưu tiên reliability tasks.
- Ai có quyền chấp nhận ngoại lệ.
- Khi nào được resume release.
- Cách thông báo stakeholder và review định kỳ.

Error budget là công cụ ra quyết định, không phải mục tiêu để “tiêu hết” hay lý do bỏ qua incident có rủi ro bảo mật/toàn vẹn dữ liệu.

## 25. Backup, restore và disaster recovery runbook

Backup chỉ có giá trị khi khôi phục được trong thời gian và điểm mất dữ liệu chấp nhận được.

### Các thuật ngữ

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất, đo bằng thời gian từ recovery point tới sự cố.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ.
- **MTTR:** thời gian trung bình để sửa/khôi phục; cách đo phụ thuộc tổ chức.
- **Failover:** chuyển hoạt động sang hệ thống dự phòng.
- **Failback:** chuyển hoạt động trở lại môi trường ưu tiên.

### Runbook restore

1. Xác định dataset/system và incident scope.
2. Chọn recovery point theo RPO và last known good.
3. Xác minh backup integrity, encryption key và quyền truy cập.
4. Restore vào isolated environment hoặc target đã chuẩn bị.
5. Áp deletion ledger/legal hold và các migration cần thiết.
6. Kiểm tra row/object count, checksum và business invariant.
7. Phục hồi dependency, network, secret và identity.
8. Chạy smoke test/transaction nghiệp vụ.
9. Mở traffic theo canary và theo dõi.
10. Ghi điểm khôi phục thực tế, RPO/RTO và sai lệch.

### Restore test định kỳ

Không chỉ xác nhận backup job “success”. Thực hiện restore drill có đo thời gian, kiểm tra dữ liệu và quyền truy cập. Test một phần dataset đại diện và full recovery theo criticality. Backup immutable/cross-account cần thử cả đường truy cập khi production account bị compromise.

### DR không chỉ là database

Kế hoạch cần cả network, DNS, identity, KMS, secrets, container images, IaC, service discovery, queue, object storage, certificates và on-call. Nếu database có bản sao nhưng key không truy cập được hoặc DNS không chuyển được, dịch vụ vẫn không phục hồi.

## 26. Capacity, saturation và graceful degradation

Nhiều incident bắt đầu từ capacity và sau đó bị khuếch đại bởi retry, queue hoặc traffic shift.

### Capacity runbook cần biết

- Normal/peak traffic và growth forecast.
- CPU/memory/network/IOPS của từng failure domain.
- Connection pool, file descriptor, thread/worker limit.
- Queue throughput và backlog age.
- Autoscaling signal, cooldown và quota cloud.
- Downstream/vendor quota.
- Headroom khi mất một AZ/node/region.

### Graceful degradation

Khi thiếu capacity, hệ thống có thể giảm một số chức năng không trọng yếu:

- Bỏ recommendation/personalization.
- Trả dữ liệu cache trong stale window đã chấp nhận.
- Giãn export/batch.
- Giảm tần suất polling.
- Tắt báo cáo realtime để giữ transaction.
- Từ chối sớm request vượt quota.

Không giảm cấp các kiểm soát bảo mật, xác thực, authorization hoặc tính toàn vẹn giao dịch để “giữ availability”. Cần định nghĩa degradation matrix từ trước.

### Noisy neighbor và fairness

Khi một tenant hoặc workload chiếm phần lớn tài nguyên, runbook phải có quota, per-tenant rate limit và worker concurrency. Chỉ throttling sau khi xác minh identity/scope; không dùng IP làm tenant identity. Theo dõi tác động của throttling với tenant khác.

## 27. Automation và self-healing có guardrail

Automation giảm thao tác lặp, nhưng một hành động tự động sai có thể lan nhanh hơn thao tác thủ công.

### Khi nào tự động hóa?

- Hành động có điều kiện rõ, output có thể xác minh.
- Rủi ro và blast radius giới hạn.
- Có idempotency và retry bounded.
- Có audit, alert và rollback/stop condition.
- Có chế độ dry-run hoặc canary.
- Đã thử trong môi trường staging/chaos test.

### Ví dụ automation an toàn

- Tự restart một replica unhealthy sau khi drain và kiểm tra quorum/capacity.
- Scale out trong giới hạn quota và theo metric đã xác thực.
- Tự retry job idempotent với backoff/jitter.
- Tự chuyển traffic khỏi unhealthy instance theo health signal nhiều chiều.
- Tự tạo incident ticket và đính kèm dashboard context khi alert đủ điều kiện.

### Automation cần approval

- Xóa dữ liệu hàng loạt.
- Failover database/region có RPO risk.
- Revoke credential hệ thống rộng.
- Thay đổi firewall/network access toàn nền tảng.
- Restore/overwrite production.
- Gỡ legal hold hoặc giảm retention.

Tự động hóa có thể chuẩn bị plan và thực hiện dry-run; thao tác phá hủy hoặc có ảnh hưởng pháp lý cần approval theo policy.

## 28. Chaos engineering và game day

Chaos engineering kiểm tra giả thuyết về khả năng chịu lỗi bằng cách tạo failure có kiểm soát. Game day là buổi diễn tập có người tham gia, mục tiêu, vai trò và đánh giá.

### Nguyên tắc thử nghiệm

1. Có giả thuyết cụ thể, ví dụ “mất một AZ không làm SLO vượt ngưỡng quá 5 phút”.
2. Xác định blast radius, scope và stop condition.
3. Chọn môi trường an toàn hoặc tenant/canary đã phê duyệt.
4. Có người chỉ huy, người quan sát và người dừng thử nghiệm.
5. Theo dõi SLI, data integrity và dependency.
6. Khôi phục môi trường và kiểm tra trạng thái cuối.
7. Ghi phát hiện, runbook gap và action item.

### Kịch bản game day

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| Kill một application instance | Load balancer/health check phân phối lại |
| Block dependency network | Timeout, breaker, bulkhead và fallback hoạt động |
| Database failover | RPO/RTO, fencing và client reconnect |
| Queue backlog | Backpressure, DLQ và drain rate |
| Expire/rotate credential | Rotation không làm outage ngoài dự kiến |
| Lose một AZ | Capacity còn lại đủ và traffic chuyển đúng |
| Restore backup | Runbook, key, data integrity và thời gian đạt mục tiêu |
| Alert fatigue drill | On-call phát hiện tín hiệu quan trọng trong noise |

Không chạy chaos experiment trong production nếu chưa có phê duyệt, giới hạn tác động, quan sát và stop control phù hợp.

## 29. Case study: incident thanh toán tăng timeout sau một đợt phát hành

Một nền tảng đặt chỗ phát hành phiên bản mới của Booking API. Sau 8 phút, alert cho thấy p99 tăng từ 350 ms lên 4 giây, timeout tăng ở endpoint tạo booking và số request tới Payment provider tăng gấp ba. Một số khách hàng báo không biết booking đã được xác nhận hay chưa.

### Phát hiện và tổ chức

1. On-call xác minh alert còn firing và thấy error budget burn tăng nhanh.
2. Incident được khai báo SEV-2 vì một hành trình cốt lõi suy giảm trên nhiều tenant.
3. IC chỉ định Technical Lead, Communications Lead và Scribe.
4. Release owner cung cấp release ID, rollout time và config diff.
5. Payment owner được gọi vì downstream attempts tăng bất thường.

### Triage và giả thuyết

| Quan sát | Giả thuyết | Kiểm tra |
| --- | --- | --- |
| p99 tăng ngay sau release | Code path mới làm tăng số call | So trace trước/sau release |
| Payment request tăng gấp ba | Retry/chained call bị nhân | So original booking với payment attempts |
| Pool wait tăng | Request giữ connection lâu | Xem thread/connection pool và dependency latency |
| Có operation chưa rõ trạng thái | Response timeout sau side effect | Tra cứu idempotency/operation status |

### Containment

- Pause rollout để không thêm instance version mới.
- Tạm route traffic về phiên bản cũ nếu schema/API tương thích.
- Giữ nguyên idempotency record; không retry payment bằng key mới.
- Hạn chế concurrency tới Payment và bật circuit breaker theo policy.
- Giảm tải chức năng phụ trên booking path.

### Recovery

Sau rollback, đội kiểm tra p99, error rate, payment attempts/request, pool wait và database. Các operation có payment outcome unknown được đối soát bằng provider reference/idempotency key. Traffic mở lại theo canary; worker reconciliation chạy với concurrency giới hạn.

### Đóng incident

Chỉ Resolved khi booking flow ổn định, không còn duplicate payment, pending operation có owner/trạng thái, queue không tích tụ và customer update đã được gửi theo policy. Postmortem xác định retry policy và thiếu test timeout-after-commit là contributing factors; action item gồm test fault injection, alert attempts/original ratio và retry budget cho Payment.

## 30. Case study: credential bị lộ trong log CI/CD

Một engineer phát hiện log pipeline chứa credential của workload production. Chưa có bằng chứng credential đã bị dùng, nhưng log được nhiều người có quyền đọc và được giữ ở artifact store.

### Điều phối

- Kích hoạt security incident, giữ nguyên log/artifact và giới hạn quyền truy cập.
- Chỉ định security incident lead; thông báo IAM, platform và privacy/legal theo policy.
- Tạo danh sách credential, account, resource và pipeline có khả năng bị ảnh hưởng.

### Containment

1. Xác định credential còn hiệu lực và quyền hiện có.
2. Chuẩn bị credential thay thế/rotation theo dependency.
3. Revoke credential cũ khi consumer đã sẵn sàng hoặc theo chiến lược khẩn cấp.
4. Chặn truy cập artifact/log với vai trò không cần thiết.
5. Kiểm tra audit trail cho lần sử dụng credential bất thường.

### Recovery và evidence

- Cập nhật pipeline dùng secret manager và masking.
- Xóa/rotate các bản secret còn hoạt động, nhưng giữ evidence theo hướng dẫn security.
- Kiểm tra log copy, cache, artifact mirror và retention.
- Review quyền đọc log và secret scanning.
- Không tuyên bố breach đã xảy ra nếu chưa có evidence; cũng không khẳng định không có breach chỉ vì chưa thấy alert.

### Bài học

Runbook phải xử lý cả credential rotation lẫn bảo toàn evidence. Thu hồi ngay có thể cần thiết để giảm rủi ro, nhưng log/artifact phải được bảo vệ để điều tra; giao tiếp bên ngoài phải theo người có thẩm quyền.

## 31. Chỉ số đo chất lượng incident management

Các metric cần được diễn giải cùng impact và độ phức tạp của incident:

| Metric | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| MTTD | Mean Time to Detect | Thời gian từ bắt đầu tác động tới khi phát hiện |
| Time to acknowledge | Từ alert/page tới người trực xác nhận | Đo paging/on-call health |
| Time to declare | Từ phát hiện tới khai báo incident | Phản ánh triage và severity policy |
| Time to mitigate | Tới khi tác động được giảm | Khác với thời gian root cause được xác định |
| MTTR | Mean Time to Restore/Repair tùy định nghĩa | Phải thống nhất điểm bắt đầu/kết thúc |
| Reopen/regression rate | Incident tái mở hoặc lỗi tái diễn | Phản ánh recovery chưa vững |
| Runbook success rate | Tỷ lệ thao tác đạt kết quả theo runbook | Cần ghi nhận deviation |
| Alert precision/noise | Tỷ lệ alert hữu ích và false positive | Không tối ưu bằng cách tắt cảnh báo quan trọng |
| Postmortem action completion | Action item hoàn thành đúng hạn | Theo dõi chất lượng cải tiến |
| Repeat incident rate | Sự cố cùng nguyên nhân/tác động tái diễn | Phân nhóm taxonomy tốt |

### Không dùng MTTR làm KPI cá nhân

MTTR chịu ảnh hưởng của kiến trúc, dependency, mức độ sự cố và quyết định giảm thiểu. Dùng metric để tìm điểm nghẽn và cải thiện hệ thống, không khuyến khích đóng incident sớm hoặc che giấu thời gian ảnh hưởng.

### Đo độ trưởng thành runbook

- **Coverage:** failure mode trọng yếu có runbook chưa?
- **Freshness:** owner và review date còn hợp lệ?
- **Executability:** người trực khác tác giả có thực hiện được?
- **Safety:** có pre-check, stop condition và rollback?
- **Evidence:** thao tác có lưu output/approval?
- **Tested:** runbook đã được game day hoặc restore drill kiểm tra?

## 32. Quản lý runbook như mã nguồn

Runbook thay đổi cùng kiến trúc, quyền, tên service và dashboard. Nên lưu trong version control cùng review process:

- Có owner và reviewer thuộc service/domain liên quan.
- Mỗi thay đổi hạ tầng quan trọng đánh giá runbook impact.
- Dùng pull request, version và changelog.
- Kiểm tra link dashboard, contact và command trước khi merge.
- Không lưu secret hoặc thông tin truy cập cá nhân.
- Dùng lint/template để kiểm tra section bắt buộc.
- Gắn runbook version vào incident record khi thực hiện.
- Review sau mỗi incident và theo lịch định kỳ.

### Runbook test tự động

Một số phần có thể kiểm tra tự động:

- Link không bị hỏng.
- Lệnh/manifest không chứa secret pattern.
- Resource name/region là placeholder hợp lệ.
- Script có dry-run hoặc confirmation cho action nguy hiểm.
- Alert/runbook URL tồn tại.
- Policy-as-code và configuration validation pass.

Không nên tự động chạy lệnh production từ bước lint. Kiểm tra cấu trúc tài liệu khác với thực thi thao tác.

## 33. Checklist review incident process

- Incident severity và trigger có được định nghĩa theo impact không?
- IC, Technical Lead, Scribe, Communications Lead và escalation backup rõ chưa?
- Runbook có owner, trigger, precondition, safety, action, verification và rollback không?
- Alert có SLI/SLO, context và link runbook?
- Có triage checklist và cách correlation với deploy/provider event?
- Timeline/evidence được lưu ở hệ thống có access control?
- Containment có stop condition và blast-radius estimate?
- Database, deployment, region, security, queue và data-corruption scenarios có playbook?
- Recovery có kiểm tra correctness, backlog, capacity và security?
- Customer/stakeholder communication có template và approval?
- Handover có trạng thái, decision, owner và next action?
- Incident closure phân biệt Resolved và Closed?
- Postmortem blameless có action item owner/deadline?
- Emergency change/break-glass được audit và đồng bộ về IaC?
- Backup/DR được restore drill theo RPO/RTO?
- Automation/self-healing có guardrail và kill switch?
- Chaos/game day có giả thuyết, scope, stop condition và debrief?
- Runbook được version control, review và kiểm tra freshness?

## 34. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Độ tin cậy** | Incident có được phát hiện, containment và recovery trong RTO/SLO không? | Alert, runbook, DR drill, SLI, failover test |
| **Bảo mật** | Security incident, credential compromise và evidence được xử lý an toàn không? | IAM, break-glass, audit, evidence handling, escalation |
| **Hiệu năng** | Hệ thống có duy trì performance và graceful degradation khi overload? | Capacity plan, load shedding, pool/queue metrics |
| **Tối ưu chi phí** | Automation, alerting và recovery có giảm công việc lặp nhưng không tạo resource waste? | Cost-aware runbook, right-sizing, retry/queue metrics |
| **Vận hành xuất sắc** | Vai trò, quy trình, runbook, postmortem và cải tiến có rõ ràng? | Incident timeline, ownership, game day, action completion |
| **Tính bền vững** | Tài nguyên và batch workload có được điều phối khi sự cố để tránh lãng phí? | Graceful degradation, bounded retries, controlled recovery |

Quy trình xử lý sự cố hiệu quả kết hợp **phát hiện sớm, chỉ huy rõ, containment an toàn, điều tra có bằng chứng, recovery có xác minh và cải tiến sau incident**. Runbook cần đủ cụ thể để người trực thực hiện được, nhưng cũng phải chỉ ra khi nào dừng và gọi chuyên gia. Độ tin cậy không đến từ việc không bao giờ có lỗi; nó đến từ khả năng giới hạn tác động, phục hồi có kiểm soát và học hỏi để sự cố tương tự ít có khả năng tái diễn.
