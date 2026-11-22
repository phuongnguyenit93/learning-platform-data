# Giới hạn của tự động hóa và quy trình can thiệp thủ công

Tự động hóa là thành phần quan trọng của hệ thống PostgreSQL có tính sẵn sàng cao (High Availability — HA). Health checks, replication monitoring, leader election, failover orchestration và endpoint routing có thể rút ngắn thời gian phát hiện sự cố và chuyển dịch vụ sang node dự phòng. Tuy nhiên, tự động hóa chỉ hành động dựa trên tín hiệu, quy tắc và quyền mà con người đã thiết kế. Nó không luôn biết primary thực sự đã chết, dữ liệu nào là mới nhất, thao tác nào là an toàn về nghiệp vụ, hoặc một network partition có khiến hai node cùng nhận writes hay không.

Một failover tự động quá sớm có thể tạo split-brain. Một failover quá muộn có thể kéo dài downtime. Một hệ thống chỉ dựa vào ping có thể promote standby trong khi primary vẫn hoạt động nhưng mất đường mạng từ phía monitor. Ngược lại, một hệ thống chờ quá nhiều xác nhận có thể không phục hồi khi một số failure domains cùng mất kết nối. Vì vậy, HA production cần xác định rõ **ranh giới giữa quyết định tự động và quyết định cần con người**, cùng với cơ chế fencing, quyền phê duyệt, runbook, bằng chứng và diễn tập.

Can thiệp thủ công không có nghĩa là mọi thao tác đều phải chạy bằng tay. Nhiều bước vẫn có thể được script hóa và kiểm soát. Điểm quan trọng là các quyết định có hậu quả lớn — như chọn node authoritative, chấp nhận khả năng mất dữ liệu, mở lại writes, xử lý hai primary cùng hoạt động hoặc thực hiện failback — phải có tiêu chí rõ, người chịu trách nhiệm và phương án dừng. Automation nên thực thi một quyết định đã được xác định an toàn; khi trạng thái không đủ chắc chắn, nó phải chuyển sang chế độ bảo vệ và gọi đúng người.

Bài học thuộc chương **Tính sẵn sàng cao** của module **Database Engine Relational PostgreSQL**. Nội dung trình bày các giới hạn kỹ thuật và vận hành của HA automation, những tình huống cần human-in-the-loop, quy trình failover/failback có fencing và cách xây dựng runbook để con người can thiệp nhất quán.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích automation làm được gì và không thể tự suy luận điều gì trong HA.
- Phân biệt failure detection, failure declaration, leader election, fencing, promotion và traffic routing.
- Nhận diện false positive, false negative, network partition và partial failure.
- Giải thích split-brain, stale primary và nguy cơ divergent writes.
- Đánh giá quorum, witness, lease và fencing token ở mức kiến trúc.
- Hiểu vì sao replication lag và commit acknowledgement ảnh hưởng quyết định failover.
- Xây dựng policy phân biệt auto-failover với manual approval.
- Thiết kế break-glass access, incident roles và change/audit trail.
- Viết runbook phát hiện, xác nhận, fence, promote, route và validate.
- Xử lý failback, rejoin, rewind và rebuild node cũ.
- Thực hành tình huống automation bị lỗi hoặc không đủ bằng chứng.
- Đo RTO, kiểm tra alert path và diễn tập cả thao tác tự động lẫn thủ công.

## 2. Automation trong HA PostgreSQL gồm những lớp nào?

Một HA system thường gồm nhiều thành phần phối hợp. Không nên xem “failover automation” là một lệnh đơn lẻ.

~~~text
                Monitoring / Health checks
                         |
                         v
                 Failure detection
                         |
                         v
              HA manager / Coordinator
                         |
             +-----------+-----------+
             |                       |
             v                       v
       Election / policy          Fencing control
             |                       |
             +-----------+-----------+
                         |
                         v
                 Promote standby
                         |
                         v
             Endpoint / proxy / DNS
                         |
                         v
                  Applications
                         |
                         v
                Validation / alerts
~~~

### 2.1. Monitoring

Thu thập server availability, replication state, lag, disk/CPU, query health, application errors và network signals.

### 2.2. Failure detection

Xác định một node hoặc service không đáp ứng health criteria trong một khoảng thời gian. Đây là nhận định dựa trên quan sát, chưa chắc là kết luận node đã chết.

### 2.3. Coordination và election

HA manager xác định node nào có quyền trở thành primary mới. Quyết định có thể dựa trên quorum, priority, timeline/LSN, synchronous state và policy.

### 2.4. Fencing

Ngăn node cũ tiếp tục nhận writes. Fencing có thể dùng power control, cloud API, storage/network isolation hoặc cơ chế độc lập khác.

### 2.5. Promotion

Chuyển standby thành primary có thể ghi. Promotion tạo trạng thái/timeline mới và phải được thực hiện đúng một lần theo quyết định authoritative.

### 2.6. Routing và validation

Chuyển clients tới primary mới, refresh connection pools, kiểm tra application readiness và xác nhận chỉ một writer đang hoạt động.

## 3. Automation có thể làm tốt điều gì?

Automation đặc biệt hiệu quả với các bước lặp lại, có tín hiệu đo được và có kết quả xác định.

### 3.1. Phát hiện health degradation

Có thể kiểm tra PostgreSQL process, SQL connectivity, replication receiver/sender, disk capacity, WAL archive lag và service-level probes.

### 3.2. Thu thập bằng chứng

Tự động snapshot metrics, logs, LSNs, timeline, node identities, timestamps và trạng thái network trước khi quyết định.

### 3.3. Thực thi thao tác đã được kiểm soát

Có thể chạy promote, update proxy membership, rotate endpoint hoặc rebuild standby khi preconditions đã được thỏa mãn.

### 3.4. Thực hiện validation lặp lại

Có thể chạy smoke queries, check writable endpoint, verify replication state và kiểm tra business invariants đã định nghĩa.

### 3.5. Gửi cảnh báo và mở incident

Tự động thông báo đúng on-call, gắn runbook, tạo incident context và lưu audit events.

## 4. Những quyết định automation không thể tự hiểu

Công cụ chỉ biết các tín hiệu được cung cấp. Nó không tự hiểu ý nghĩa nghiệp vụ hoặc bối cảnh sự cố ngoài thiết kế.

### 4.1. Node không phản hồi có thực sự đã chết?

Một node có thể còn hoạt động nhưng bị network partition, CPU starvation, TLS/auth failure hoặc overloaded. Health check từ một vị trí duy nhất không phân biệt được mọi trường hợp.

### 4.2. Node nào có dữ liệu tốt nhất?

Standby có LSN lớn hơn không luôn có nghĩa dữ liệu hợp lệ hơn nếu có timeline divergence, corruption hoặc lỗi logic. Cần xem lineage và failure timeline.

### 4.3. Mất dữ liệu có thể chấp nhận không?

RPO là quyết định business đã phê duyệt. Automation có thể đo khoảng cách dữ liệu nhưng không tự quyết định chấp nhận mất giao dịch payment/order.

### 4.4. Một giao dịch có đúng nghiệp vụ không?

PostgreSQL có thể commit một câu UPDATE hợp lệ về cú pháp nhưng sai nghiệp vụ. Failover không thể khôi phục logic đúng nếu không có backup/PITR và quy trình điều tra.

### 4.5. Có nên mở writes ngay không?

Cluster có thể accept writes nhưng ứng dụng, queue, identity, payment gateway hoặc DNS chưa sẵn sàng. Service readiness cần kiểm tra end-to-end.

## 5. Failure detection không phải failure declaration

Đây là một ranh giới quan trọng trong HA.

### 5.1. Detection

Một probe timeout, connection failure hoặc heartbeat bị mất là tín hiệu phát hiện. Nó nói rằng observer không nhận được phản hồi đúng hạn.

### 5.2. Declaration

Failure declaration là quyết định hệ thống sẽ xử lý node như unavailable theo policy. Quyết định này có thể kích hoạt election/failover.

### 5.3. False positive

Node khỏe bị đánh dấu down do network congestion, GC/CPU stall, overloaded disk, firewall hoặc probe timeout quá ngắn.

### 5.4. False negative

Node đã hỏng nhưng health check vẫn pass vì chỉ kiểm tra TCP port hoặc process còn chạy trong khi queries không thể hoàn thành.

### 5.5. Multi-signal detection

Kết hợp SQL probe, process/service state, network path, replication health, host metrics và application error signals. Mỗi tín hiệu cần biết nó quan sát từ đâu và failure domain nào.

## 6. Partial failure và network partition

Distributed systems thường gặp tình trạng một phần hệ thống nhìn thấy node, phần khác không.

~~~text
              Network partition
        +----------------+   +----------------+
        | Region A       | X | Region B       |
        | Primary P      |   | Standby S      |
        | App clients    |   | HA observer    |
        +----------------+   +----------------+
~~~

### 6.1. Primary vẫn chạy

P có thể tiếp tục phục vụ clients trong Region A nhưng mất kết nối tới standby hoặc observer ở Region B.

### 6.2. Standby không nhìn thấy primary

S có thể nhận timeout và kết luận P unavailable, trong khi P vẫn nhận writes từ một số clients.

### 6.3. Hai phía có thể đưa ra quyết định khác nhau

Nếu cả hai phía tự promote hoặc route writes mà không có quorum/fencing, hai primary có thể cùng tồn tại.

### 6.4. Timeout không chứng minh process đã chết

Timeout phản ánh observer không nhận được phản hồi trong thời gian định nghĩa. Nó không chứng minh host đã tắt nguồn.

### 6.5. Thiết kế theo failure domains

Đặt witness/quorum members và fencing control sao cho một partition không cho phép hai phía cùng đạt quyền authoritative. Xem xét region, AZ, network, power và control plane độc lập.

## 7. Split-brain và hậu quả

Split-brain là trạng thái nhiều node cùng được xem là primary authoritative và nhận writes độc lập.

### 7.1. Divergent data

Mỗi primary tạo transaction riêng. Logical/physical replication không tự hợp nhất hai histories sau khi chúng diverge.

### 7.2. Duplicate business operations

Ứng dụng có thể tạo hai orders, charge/payment requests hoặc cập nhật inventory từ hai nhánh khác nhau.

### 7.3. Không thể chỉ chọn node có nhiều rows hơn

Một node có thể có nhiều rows nhưng chứa dữ liệu sai hoặc giao dịch duplicate. Cần timeline, WAL positions, audit và business reconciliation.

### 7.4. Split-brain có thể xảy ra dù chỉ có một PostgreSQL primary theo config

Một proxy hoặc application có thể vẫn route writes tới node cũ; control plane nói primary mới nhưng clients cũ chưa được fence.

### 7.5. Fencing là điều kiện bảo vệ quan trọng

Trước khi promote standby, phải có cơ chế ngăn old primary nhận writes hoặc chứng minh nó không còn khả năng làm writer.

## 8. Fencing: ngăn primary cũ tiếp tục ghi

Fencing là hành động làm node mất quyền phục vụ writes trong hệ thống authoritative.

### 8.1. Power fencing

Tắt hoặc reset host qua BMC/cloud provider/hypervisor. Cần control plane độc lập với node bị lỗi.

### 8.2. Network fencing

Chặn application traffic tới old primary bằng firewall/security group/network policy. Phải tính tới clients có kết nối sẵn và đường mạng thay thế.

### 8.3. Storage fencing

Thu hồi quyền truy cập storage dùng chung hoặc dùng storage lease/locking phù hợp. Không dùng thao tác filesystem tùy tiện có thể làm hỏng dữ liệu.

### 8.4. Process/service fencing

Dừng PostgreSQL hoặc service trên node cũ. Cách này chỉ đáng tin khi control path tới host còn hoạt động và có bằng chứng lệnh đã hoàn tất.

### 8.5. Fencing token/epoch

Control plane có thể cấp epoch/term tăng dần; storage/proxy/application chỉ chấp nhận writes từ leader có token hiện tại. Token phải được kiểm tra ở nơi thực sự bảo vệ write path.



## 9. Fencing và leader election phải phối hợp

Leader election trả lời node nào được quyền làm primary; fencing bảo đảm các node còn lại không tiếp tục ghi. Hai cơ chế này bổ sung cho nhau.

### 9.1. Election không tự dừng old primary

Một HA manager có thể chọn S làm leader mới, nhưng P có thể vẫn chạy và nhận writes nếu chưa bị fence.

### 9.2. Fencing trước promotion

Một quy trình an toàn thường yêu cầu xác nhận old primary đã bị fence trước khi promote standby. Nếu không thể chứng minh fencing, phải có policy xử lý partition cụ thể.

### 9.3. Fencing token cần được enforce

Một token chỉ nằm trong metadata không bảo vệ dữ liệu nếu application/proxy/storage không kiểm tra token trước khi ghi.

### 9.4. Fencing phải có timeout và xác nhận

Lệnh power-off/firewall có thể fail hoặc API trả trạng thái chưa chắc chắn. Cần verify kết quả từ control plane độc lập.

### 9.5. Fail-safe behavior

Khi fencing không xác nhận được, hệ thống nên dừng promotion tự động hoặc chuyển sang quy trình manual incident theo risk policy. Không coi timeout của fencing command là thành công.

## 10. Quorum, witness và quyền authoritative

Quorum giúp tránh hai nhóm node cùng tin mình có quyền lãnh đạo.

### 10.1. Quorum

Một quyết định cần đủ số phiếu từ các thành viên đủ điều kiện. Với quorum majority, chỉ một partition có thể giữ majority trong mô hình membership nhất quán.

### 10.2. Witness

Witness là thành viên điều phối/phiếu bầu có thể không chạy PostgreSQL data. Nó giúp phân biệt partition trong một số kiến trúc, nhưng không tự fence old primary.

### 10.3. Odd-numbered voters

Số voter lẻ thường giúp tránh tie trong majority voting. Số lượng và placement phải xét failure domains; ba voters cùng một AZ không chịu được mất AZ.

### 10.4. Quorum không chứng minh dữ liệu mới nhất

Quorum quyết định quyền điều phối, không tự đảm bảo candidate có mọi transaction đã commit ở primary cũ. Cần replication durability policy và LSN/acknowledgement state.

### 10.5. Quorum và synchronous replication là hai khái niệm

Quorum election chọn leader; synchronous replication xác định commit acknowledgement. Có thể dùng cùng hệ thống nhưng một cái không thay thế cái kia.

## 11. Lease và fencing token

Một số HA managers dùng lease/lock trong distributed configuration store để chỉ định leader.

### 11.1. Lease

Lease cấp quyền leader trong một khoảng thời gian, được renew định kỳ. Nếu leader không renew, một node khác có thể được phép tranh quyền theo coordinator.

### 11.2. Clock assumptions

Lease dựa vào thời gian và timeout cần giả định về clock drift, scheduling delays và network delay. Không tự suy rằng một lease hết hạn ở observer có nghĩa process cũ đã dừng.

### 11.3. Token/epoch tăng dần

Mỗi lần đổi leader, coordinator có thể tăng term/epoch. Thành phần bảo vệ write path phải từ chối requests mang token cũ.

### 11.4. Storage fencing

Nếu storage hỗ trợ fencing token/lease, node cũ với token hết hạn không thể ghi. Với PostgreSQL data directory local, cần kết hợp service/network/host fencing theo kiến trúc.

### 11.5. Kiểm tra implementation thực tế

Đọc cách HA manager lưu lock, renew lease, xử lý stale leader và fence. Tên tính năng “leader election” không đủ để kết luận split-brain đã được ngăn.

## 12. Replication state ảnh hưởng quyết định failover

Node có thể healthy nhưng lag; node khác có thể có LSN cao hơn nhưng không phù hợp làm leader do timeline/divergence.

### 12.1. Asynchronous replication

Primary không chờ standby flush WAL trước khi trả commit response theo cấu hình async. Khi primary mất đột ngột, standby có thể thiếu các commits cuối.

### 12.2. Synchronous replication

Commit có thể chờ acknowledgement từ synchronous standby theo `synchronous_commit</BT> và `synchronous_standby_names</BT>. Chế độ acknowledgement quyết định mức durability.

### 12.3. Remote write, flush và apply

Remote write/flush/apply thể hiện các mức xác nhận khác nhau. Chọn standby được promote phải xét mức xác nhận thực tế, không chỉ tên “synchronous”.

### 12.4. Candidate selection

Đánh giá timeline, receive/write/flush/replay LSN, synchronous state, archive/WAL availability và node health. Một LSN lớn hơn không tự chứng minh mọi transaction hợp lệ.

### 12.5. RPO phải được chấp nhận rõ

Nếu failover async có thể mất một số transactions, incident commander/business owner cần biết mức mất dữ liệu ước lượng và policy phê duyệt. Không giấu trade-off trong automation.

## 13. Auto-failover và manual failover

Không có một policy duy nhất cho mọi workload. Cần xác định điều kiện tự động và điều kiện chuyển sang human approval.

| Tình huống | Hành động thường cân nhắc |
|---|---|
| Primary process chết, quorum còn, fencing xác nhận được | Auto-failover có thể phù hợp |
| Mất một node nhưng primary vẫn phục vụ writes | Alert/repair; không nhất thiết promote |
| Network partition, không rõ primary còn ghi không | Fencing/quorum trước; có thể cần manual decision |
| Replication lag vượt RPO | Escalate; đánh giá candidate/data loss |
| Nhiều candidates có timeline/LSN khác nhau | Manual review theo policy |
| Corruption logic hoặc thao tác xóa nhầm | PITR/isolated recovery, không chỉ failover |
| Ransomware/credential compromise | Incident response và clean recovery; không promote mù |
| Region loss, DR site đã được kiểm chứng | Theo DR runbook; human declaration tùy policy |

### 13.1. Điều kiện auto-failover

Phải có quorum/leader authority, fencing path đã xác minh, candidate đủ điều kiện, RPO policy và routing automation có thể kiểm chứng.

### 13.2. Điều kiện manual approval

Dùng khi có uncertainty về split-brain, data divergence, corruption, nhiều candidates, external dependencies hoặc business data loss.

### 13.3. Không tự động hóa một quyết định chưa định nghĩa

Nếu không có rule chọn candidate khi LSN/timeline khác nhau, automation không thể suy ra quyết định business-safe.

### 13.4. Manual không có nghĩa chậm tùy tiện

Runbook, pre-approved thresholds, on-call roster và break-glass access có thể giúp con người quyết định nhanh, nhất quán.

### 13.5. Review policy sau incident

Nếu một loại failure lặp lại và signals đủ rõ, có thể chuyển một bước từ manual sang auto sau khi có test, fencing và rollback plan.

## 14. Những việc nên tự động và những việc cần phê duyệt

| Công việc | Automation | Human role |
|---|---|---|
| Thu thập metrics/logs | Tự động | Xác nhận context |
| Alert/on-call routing | Tự động | Acknowledge/assign |
| Kiểm tra replication lag | Tự động | Chọn risk threshold |
| Kiểm tra quorum/lock | Tự động | Review khi trạng thái bất thường |
| Fencing đã được thiết kế | Có thể tự động | Approve tùy policy; verify |
| Candidate selection | Có thể tự động trong rule rõ | Quyết định khi ambiguity |
| Promotion | Có thể tự động sau preconditions | Manual override/approval |
| Endpoint routing | Tự động | Validate clients |
| Business data reconciliation | Hỗ trợ bằng scripts | Owner quyết định |
| Failback/rejoin | Một phần tự động | Review timeline/data divergence |

### 14.1. Automate evidence, not assumptions

Tự động thu thập LSN, timeline, sender state, fencing status và node identity. Không thay bằng một cờ `healthy=true</BT> không giải thích được.

### 14.2. Approval gates

Đặt approval gate trước những bước không dễ đảo ngược hoặc có thể làm mất dữ liệu: promote candidate không rõ, accept RPO breach, force failover khi không có quorum hoặc mở lại writes.

### 14.3. Idempotent actions

Các automation actions nên có thể chạy lại an toàn hoặc kiểm tra trạng thái trước khi chạy. Tránh lệnh promote/route được thực thi lặp gây trạng thái không xác định.

### 14.4. Dry-run và preflight

Trước khi thay đổi topology, hiển thị candidate, LSN/timeline, quorum, fencing result, target endpoint và dự kiến RPO/RTO.

### 14.5. Stop conditions

Nếu một precondition fail, automation phải dừng, giữ trạng thái an toàn và báo người vận hành. Không bỏ qua check để “cố hoàn thành”.

## 15. Các HA tools và giới hạn trách nhiệm

PostgreSQL thường kết hợp database engine với external HA manager, proxy và service discovery.

### 15.1. Patroni

Patroni quản lý PostgreSQL HA, leader election qua distributed configuration store và các thao tác promote/demote theo cấu hình. Cần hiểu DCS quorum, watchdog/fencing behavior, synchronous mode và routing integration.

### 15.2. repmgr

repmgr cung cấp công cụ quản lý/monitoring replication và hỗ trợ switchover/failover. Cần cấu hình failover policy, witness/monitoring và fencing phù hợp môi trường.

### 15.3. pg_auto_failover

pg_auto_failover dùng monitor để điều phối node states và failover theo state machine. Cần hiểu monitor availability, node roles và failure transitions.

### 15.4. Managed PostgreSQL services

Cloud provider có thể quản lý failover, endpoint và replicas. User vẫn cần hiểu failover semantics, RPO, maintenance behavior, zone/region scope và limitations của service tier.

### 15.5. Không tool nào tự hiểu business invariants

Dù tool nào được dùng, ứng dụng vẫn cần consistency policy, backup/PITR, data validation, fencing assurance và runbooks cho trường hợp bất thường.

## 16. Health checks: kiểm tra đúng lớp

Một health check nên trả lời câu hỏi cụ thể.

### 16.1. Process health

PostgreSQL process có đang chạy không? Process chạy không đồng nghĩa query path hoạt động.

### 16.2. SQL readiness

Có thể kết nối và chạy một query nhẹ không? Query có thể fail do connection exhaustion, locks hoặc disk I/O.

### 16.3. Write readiness

Primary có thể commit một transaction test theo policy không? Không chạy write probe tùy tiện vào business tables.

### 16.4. Replication health

Standby có receiver, sender connection và replay progress không? Kiểm tra LSN/lag và timeline.

### 16.5. Application health

Một request end-to-end có hoàn thành không? App có thể fail do DNS, credentials, pool, queue hoặc dependency dù database khỏe.


## 17. Health check design và threshold

Health check cần có threshold dựa trên workload, failure model và RTO, không dùng một timeout chung cho mọi lớp.

### 17.1. Timeout quá ngắn

Timeout ngắn có thể phát hiện nhanh nhưng tăng false positives khi có network jitter hoặc load spike. Một false positive có thể kích hoạt failover nguy hiểm.

### 17.2. Timeout quá dài

Timeout dài giảm false positives nhưng kéo dài detection time và RTO. Cần cân bằng với failure detection requirements.

### 17.3. Consecutive failures

Có thể yêu cầu nhiều lần probe thất bại liên tiếp trước khi declare node unhealthy. Điều này giảm transient failures nhưng phải tính tổng detection delay.

### 17.4. Multi-observer

Probe từ nhiều network locations giúp phân biệt node down với một đường mạng bị lỗi. Tuy nhiên, các observers phải có failure domains đủ độc lập.

### 17.5. Threshold theo service tier

Database payment có thể cần detection nhanh hơn analytics. Mỗi tier cần health SLO, alert thresholds và failover policy riêng.

## 18. Manual intervention: vai trò và trách nhiệm

Khi cần con người quyết định, vai trò phải rõ trước khi incident xảy ra.

### 18.1. Incident commander

Điều phối incident, duy trì timeline, phân công người xử lý và quyết định escalation theo incident policy.

### 18.2. DBA/recovery lead

Đánh giá PostgreSQL state, replication, LSN/timeline, candidate eligibility, backup/PITR và validation kỹ thuật.

### 18.3. Infrastructure/network owner

Xác nhận host, power, network partition, storage và fencing controls. Người này phải có quyền truy cập control plane độc lập.

### 18.4. Application owner

Xác nhận application connectivity, retry behavior, queue consumers, background jobs và smoke tests.

### 18.5. Business/service owner

Chấp nhận RPO/data loss trade-off, xác nhận business invariants và quyết định service priority khi có nhiều phương án.

## 19. Quyền break-glass và truy cập khẩn cấp

Manual failover có thể cần quyền cao hơn quyền vận hành hàng ngày. Quyền khẩn cấp phải được chuẩn bị và kiểm tra trước.

### 19.1. Tách identity

Dùng identity khẩn cấp riêng cho database, cloud control plane, network/firewall và secrets. Không phụ thuộc vào một tài khoản application đã có thể bị compromise.

### 19.2. MFA và approval

Bảo vệ break-glass credentials bằng MFA, vault, approval hoặc dual control theo policy. Ghi rõ ai được phép sử dụng và trong tình huống nào.

### 19.3. Access path độc lập

Nếu production identity provider hoặc network gặp sự cố, cần phương án truy cập khẩn cấp đã thử. Đường này phải có audit và giới hạn.

### 19.4. Credential availability

Secrets, certificates, KMS keys và recovery tokens cần sẵn sàng ở DR region/account. Quyền tồn tại trên giấy nhưng không truy cập được khi disaster không có giá trị.

### 19.5. Sau khi dùng break-glass

Thu hồi/rotate credentials, review audit logs, xác nhận mọi thay đổi và đóng quyền tạm thời. Không để emergency access tồn tại vô thời hạn.

## 20. Manual failover runbook: giai đoạn xác nhận

Trước khi promote candidate, người vận hành phải hiểu tình trạng primary và các standby.

### 20.1. Declare incident

Ghi T0, timezone, failure scope, service tier và người điều hành. Xác nhận đây là failover event hay chỉ là degradation.

### 20.2. Xác định primary có còn nhận writes không

Kiểm tra SQL, process, host, network, proxy và application connection paths. Đừng kết luận node down chỉ vì một observer timeout.

### 20.3. Xác nhận candidate list

Thu thập replication state từ primary còn truy cập được, receiver state trên standbys, replay/flush LSN, timeline và synchronous state. Dùng views như `pg_stat_replication</BT> và `pg_stat_wal_receiver</BT>.

### 20.4. Đánh giá data loss

Ước lượng transaction boundary có thể mất dựa trên acknowledgement mode và candidate state. Nếu vượt RPO, escalation business owner.

### 20.5. Chọn candidate theo policy

Chọn node có lineage/timeline hợp lệ, WAL state phù hợp và capacity. Không chọn chỉ theo hostname priority hoặc một LSN không được đối chiếu.

## 21. Manual failover runbook: fencing và promotion

### 21.1. Freeze writes

Nếu có thể, dừng hoặc pause application writers, queue consumers, scheduled jobs và admin jobs. Giữ lại trạng thái request/event để reconcile.

### 21.2. Fence old primary

Thực hiện power/network/service/storage fencing theo thiết kế. Xác nhận từ control plane độc lập rằng node cũ không thể nhận writes.

### 21.3. Ghi bằng chứng fencing

Lưu API response, instance state, firewall rule, service state hoặc fencing token/epoch. Nếu kết quả không rõ, chưa coi fencing hoàn tất.

### 21.4. Promote candidate

Sau khi preconditions đạt, promote bằng HA manager hoặc lệnh phù hợp. Không chạy nhiều cơ chế promotion cùng lúc.

### 21.5. Verify new primary

Kiểm tra `pg_is_in_recovery()</BT> trả false, SQL writes được cho phép theo policy, timeline mới và logs không có lỗi recovery. Chưa mở toàn bộ traffic trước validation.

## 22. Manual failover runbook: routing và validation

### 22.1. Update endpoint

Chuyển proxy/service discovery/DNS theo cơ chế đã chuẩn bị. Kiểm tra DNS TTL và connection pools có thể giữ endpoint cũ.

### 22.2. Refresh clients

Recycle connection pools hoặc restart application instances theo kế hoạch. Đảm bảo clients cũ không còn kết nối old primary.

### 22.3. Smoke tests

Chạy read/write test nghiệp vụ an toàn, kiểm tra auth/permissions, transaction commit và external dependencies trong phạm vi controlled rollout.

### 22.4. Mở traffic từng bước

Bắt đầu với một nhóm clients/traffic nhỏ nếu kiến trúc hỗ trợ. Theo dõi errors, latency, lock waits, replication lag và business metrics.

### 22.5. Ghi RPO thực tế

Ghi candidate, recovery LSN/timeline, transaction boundary cuối được xác nhận và data reconciliation cần thiết. So sánh với RPO đã phê duyệt.

## 23. Manual switchover khác manual failover

Switchover là chuyển primary có kế hoạch khi hệ thống còn hoạt động; failover xử lý sự cố không mong muốn.

### 23.1. Switchover có thể đồng bộ có kiểm soát

Có thể drain writes, chờ standby catch up, xác nhận LSN và chuyển role trong maintenance window.

### 23.2. Failover có thể thiếu dữ liệu cuối

Primary có thể đã mất trước khi WAL cuối được truyền/flush. Candidate có thể thiếu một số commits async.

### 23.3. Switchover vẫn cần fencing logic

Dù primary cũ khỏe, phải bảo đảm nó không tiếp tục nhận writes sau khi role thay đổi. Không dựa vào thao tác DNS đơn lẻ.

### 23.4. Switchover nên có abort criteria

Nếu standby lag vượt threshold, replication connection down hoặc validation fail, dừng và quay lại trạng thái ban đầu trước khi promotion.

### 23.5. Diễn tập riêng hai loại

Một switchover thành công không chứng minh failover an toàn khi primary mất đột ngột. Test cả hai scenarios.

## 24. Khi automation bị kẹt hoặc báo trạng thái mâu thuẫn

HA manager có thể gặp DCS unavailable, monitor down, stale lock, API timeout hoặc state transition chưa hoàn tất.

### 24.1. Không chạy promote thủ công ngay lập tức

Trước tiên xác định HA manager có đang thực hiện promotion hay node khác đã được chọn. Hai actor cùng promote có thể tạo divergence.

### 24.2. Xem state machine

Đọc trạng thái cluster/leader lock/lease và node state theo công cụ đang dùng. Ghi timestamp và owner/epoch.

### 24.3. Kiểm tra process và PostgreSQL role

Trên từng node, xác định primary/standby state, recovery status, active connections và timeline. Đối chiếu với HA manager state.

### 24.4. Kiểm tra DCS/quorum

Nếu distributed configuration store mất quorum, tránh thao tác làm thay đổi leader ownership cho tới khi hiểu control plane.

### 24.5. Escalate theo runbook

Nếu state không nhất quán, chuyển sang incident commander/DBA lead. Giữ writes đóng hoặc giữ node fenced theo policy cho tới khi authority rõ ràng.

## 25. Manual recovery khi không thể xác định primary cũ

Một số disaster làm mất liên lạc với primary nhưng không thể xác nhận nó đã tắt.

### 25.1. Không coi “không truy cập được” là “đã fence”

Primary có thể tiếp tục chạy ở network partition bên kia. Nếu promote standby mà không fence, split-brain có thể xảy ra.

### 25.2. Sử dụng independent control plane

Kiểm tra cloud/hypervisor power state, network ACL, storage attachment/lease hoặc out-of-band management.

### 25.3. Nếu không có fencing path

Áp dụng policy đã được phê duyệt cho trường hợp không thể chứng minh old primary stopped. Có thể cần chờ, khôi phục connectivity, hoặc chấp nhận risk có kiểm soát theo DR declaration.

### 25.4. Document uncertainty

Ghi rõ những gì đã xác minh, những gì chỉ suy đoán và rủi ro còn lại. Không ghi “fenced” khi chỉ có ping timeout.

### 25.5. Sau khi old primary quay lại

Giữ nó isolated, không cho nhận writes. Xác định timeline divergence và chọn pg_rewind hoặc rebuild từ base backup phù hợp.

## 26. Failback: đưa hệ thống về topology mong muốn

Failback là chuyển workload trở lại node/site ban đầu hoặc một topology được chọn sau khi disaster đã được xử lý.

### 26.1. Failback không phải đổi DNS ngược

Node cũ có thể đã diverge và thiếu writes mới. Cần rejoin như standby trước khi có thể cân nhắc switchover.

### 26.2. Giữ một authoritative primary

Chỉ một node được nhận writes trong quá trình rebuild/rejoin. Fence các node khác.

### 26.3. pg_rewind khi đủ điều kiện

Có thể dùng `pg_rewind</BT> để đồng bộ node đã diverge theo timeline mới nếu prerequisites và WAL cần thiết đáp ứng. Nếu không, reseed bằng base backup.

### 26.4. Kiểm tra catch-up

Xác nhận standby receiver/sender state, replay lag, timeline và archive. Chỉ xem xét switchover khi node đã bắt kịp và validation đạt.

### 26.5. Failback có thể không cần thiết

Nếu DR site có capacity và đáp ứng SLO, có thể giữ site mới làm primary cho tới maintenance window phù hợp. Business owner quyết định dựa trên risk/cost.


## 27. Rejoin standby và rebuild node cũ

Sau failover, old primary thường không thể chỉ khởi động lại rồi tham gia topology.

### 27.1. Giữ node cũ isolated

Chặn application writes và replication connections ngoài quy trình rejoin. Thu thập logs/data cần thiết cho điều tra.

### 27.2. Kiểm tra timeline divergence

Xác định node cũ có timeline cũ và có transactions riêng hay không. Không để nó trở thành writer chỉ vì process đã chạy.

### 27.3. pg_rewind

Nếu prerequisites như data checksums hoặc `wal_log_hints</BT> và WAL cần thiết đáp ứng, `pg_rewind</BT> có thể đưa data directory cũ theo timeline của primary mới. Xác nhận version/compatibility và backup trước thao tác.

### 27.4. Reseed từ base backup

Nếu không thể rewind hoặc dữ liệu không đáng tin, tạo standby mới từ base backup của primary hiện tại. Đây là phương án rõ ràng khi divergence lớn hoặc thiếu WAL.

### 27.5. Verify rejoin

Kiểm tra sender/receiver state, timeline, replay LSN, slots, archive và monitoring. Chỉ mở topology bình thường sau khi node bắt kịp và không còn stale endpoint.

## 28. HA manager không thay thế runbook

Một tool có thể tự động hóa state transitions nhưng vẫn cần quy trình cho trường hợp tool hoặc dependency bị lỗi.

### 28.1. DCS/monitor outage

Nếu distributed configuration store hoặc monitor mất quorum, HA manager có thể không đưa ra quyết định mới. Cần biết node nào giữ lock/lease và trạng thái hiện tại.

### 28.2. Watchdog/fencing failure

Nếu watchdog không hoạt động hoặc host không bị fence, automation có thể không đáp ứng safety assumptions. Có quy trình dừng promotion và gọi infrastructure owner.

### 28.3. Proxy/service discovery failure

Database có thể đã promote nhưng clients vẫn kết nối old endpoint. Cần runbook kiểm tra proxy health, DNS cache, poolers và stale connections.

### 28.4. API/control-plane failure

Cloud API có thể timeout hoặc rate limit. Đừng lặp lệnh destructive không idempotent; kiểm tra trạng thái thực tế trước khi retry.

### 28.5. Version/configuration drift

HA manager, PostgreSQL, DCS, proxy và agents phải có version/configuration inventory. Thay đổi không đồng bộ có thể tạo state transitions khác dự kiến.

## 29. Idempotency và an toàn khi retry automation

Incident làm tăng xác suất operator hoặc controller chạy lại cùng một thao tác.

### 29.1. Check current state first

Trước khi promote, kiểm tra node đang ở recovery hay đã primary, timeline và leader ownership. Trước khi route, kiểm tra endpoint hiện tại.

### 29.2. Idempotent API/actions

Automation nên trả cùng kết quả khi lệnh được gửi lại sau timeout, hoặc cung cấp operation ID để truy vấn kết quả lần đầu.

### 29.3. Không suy timeout là action fail

API có thể đã thực hiện fencing/promote nhưng response bị mất. Kiểm tra state trước khi chạy lại.

### 29.4. Lock/serialization

Chỉ một controller/incident action được phép thay đổi leader state tại một thời điểm. Dùng lock/lease có fencing semantics và audit.

### 29.5. Action log

Ghi actor, operation ID, preconditions, command, result, timestamp và state trước/sau. Điều này hỗ trợ recovery khi process bị ngắt giữa chừng.

## 30. Human-in-the-loop không được trở thành single point of failure

Quy trình cần người quyết định nhưng phải tránh phụ thuộc một cá nhân duy nhất.

### 30.1. Primary và backup on-call

Có người chính và người thay thế. Danh sách liên hệ cần được kiểm tra định kỳ.

### 30.2. Escalation timeout

Nếu người chịu trách nhiệm không phản hồi trong thời gian quy định, chuyển cấp tiếp theo theo incident policy. Không chờ vô hạn.

### 30.3. Delegated authority

Xác định ai có quyền approve promotion, chấp nhận RPO breach và declare DR. Quyền này phải có hiệu lực ngoài giờ.

### 30.4. Two-person control cho thao tác rủi ro

Với force failover hoặc thao tác có nguy cơ mất dữ liệu, có thể yêu cầu hai người xác nhận độc lập. Không áp dụng máy móc cho mọi thao tác nhỏ.

### 30.5. Training và rotation

Nhiều người cần thực hành runbook để giảm key-person risk. On-call rotation phải có quyền và kỹ năng tương ứng.

## 31. Giao tiếp trong incident

Can thiệp kỹ thuật có thể đúng nhưng thất bại nếu các nhóm không biết trạng thái và quyết định.

### 31.1. Một incident timeline chung

Ghi thời điểm phát hiện, declare, fencing, promotion, routing, validation và service restored. Dùng timezone thống nhất.

### 31.2. Một người điều phối

Incident commander quản lý thông tin và quyết định escalation; DBA không phải vừa chạy lệnh vừa điều phối mọi nhóm.

### 31.3. Status update có cấu trúc

Nêu impact, hiện trạng, hành động đã xác nhận, rủi ro RPO/data loss, bước tiếp theo và thời điểm update kế tiếp.

### 31.4. Phân biệt fact và hypothesis

Ví dụ “P không phản hồi từ region B” là fact; “P đã chết” có thể chỉ là hypothesis cho tới khi fencing xác nhận.

### 31.5. Ghi quyết định và người phê duyệt

Đặc biệt với RPO breach, force promotion, data reconciliation và cutover. Sau incident, phải truy lại được lý do.

## 32. Audit trail và bằng chứng vận hành

Mọi thao tác failover/manual intervention cần có bằng chứng để điều tra và cải thiện.

### 32.1. State snapshots

Lưu node role, timeline, LSN, replication state, quorum, slot state và endpoint trước/sau.

### 32.2. Command/audit logs

Lưu command, actor, host, timestamp, exit status và output cần thiết. Redact passwords/tokens.

### 32.3. Control-plane events

Lưu cloud power actions, network policy changes, storage detach/attach, DCS lease transitions và proxy membership changes.

### 32.4. Data-loss record

Ghi recovery point cuối, transaction boundary, dữ liệu mất/được reconcile và business approval.

### 32.5. Retention

Giữ logs theo incident/security policy, đồng bộ clock và bảo vệ khỏi sửa/xóa cùng production credentials.

## 33. Runbook phải có preconditions và stop conditions

Một runbook chỉ liệt kê commands không đủ để vận hành an toàn.

### 33.1. Preconditions

Ghi điều kiện phải có trước mỗi bước: quyền truy cập, node identity, target, backup/LSN, quorum, fencing path và approvals.

### 33.2. Expected result

Mỗi command/action cần mô tả output/state mong đợi. Ví dụ sau promote, node phải rời recovery state và có timeline mới.

### 33.3. Stop conditions

Dừng khi fencing chưa xác nhận, candidate timeline không rõ, WAL gap, DCS state mâu thuẫn, hoặc application/data validation fail.

### 33.4. Recovery from partial execution

Nếu runbook dừng sau khi fence nhưng trước promote, mô tả node nào giữ fenced, ai quyết định tiếp và cách tránh hai writers.

### 33.5. Escalation

Ghi người liên hệ, quyền phê duyệt, provider support path và cách xử lý khi control plane không truy cập được.

## 34. Change management và bảo trì HA

Thay đổi cấu hình HA có thể ảnh hưởng failover behavior ngay cả khi database vẫn hoạt động.

### 34.1. Thay đổi topology

Thêm/bớt standby, đổi synchronous policy, DCS membership hoặc proxy routing cần change plan và rollback path.

### 34.2. Maintenance một node

Drain read traffic, kiểm tra standby còn lại đủ capacity/quorum, rồi mới restart/patch node. Không bảo trì đồng thời các thành viên cần cho quorum.

### 34.3. Upgrade PostgreSQL/HA manager

Kiểm tra compatibility matrix, replication behavior, catalog/slot support và failover process. Diễn tập trên staging trước.

### 34.4. Rotate certificates/secrets

Xác nhận mọi nodes/agents/proxies nhận credential mới và có thể reconnect trước khi thu hồi credential cũ.

### 34.5. Configuration drift

Dùng configuration management/IaC, version control và drift detection. Không chỉnh tay một node rồi quên cập nhật inventory/automation.

## 35. Observability: dashboard phục vụ quyết định

Dashboard cần trả lời câu hỏi operator phải quyết định trong incident.

### 35.1. Cluster role map

Hiển thị node nào là primary, standby, relay, witness/monitor và endpoint nào đang được app sử dụng.

### 35.2. Replication freshness

Hiển thị receive/flush/replay LSN, lag theo bytes/time, synchronous state và WAL archive lag.

### 35.3. Fencing/authority

Hiển thị leader lock/lease owner, epoch/token, quorum state và fencing confirmation nếu integration cung cấp.

### 35.4. Client routing

Hiển thị proxy pool members, active connections, DNS/service discovery target và client error rates.

### 35.5. Business health

Theo dõi transaction success, queue backlog, payment/order invariants và user-facing latency; database process health không đủ.

## 36. Alerting và escalation

Alert phải giúp người trực biết cần hành động gì và ai có quyền làm.

### 36.1. Severity theo impact

Primary down, quorum lost, fencing failure, RPO breach và split-brain risk thường có severity cao hơn một replica read-only bị lag nhẹ.

### 36.2. Alert fatigue

Gộp alerts liên quan, dùng duration/threshold hợp lý và phân biệt transient network jitter với sustained outage.

### 36.3. Alert có context

Đính kèm node, region, current leader, candidate, replication lag, LSN/timeline, fencing state và runbook link.

### 36.4. Escalation routing

Gửi tới DBA on-call, infrastructure/network owner và incident commander theo failure mode. Business owner được gọi khi có data loss/RPO decision.

### 36.5. Test alert path

Diễn tập alert delivery, paging, acknowledgement và escalation. Alert không tới người có quyền hành động là một failure của HA process.

## 37. Security incident khác node failure

Nếu primary mất do ransomware hoặc credentials bị compromise, failover sang standby có thể sao chép cùng dữ liệu bị phá hoại hoặc mở rộng attacker access.

### 37.1. Không promote mù quáng

Xác định compromise scope, identities và backup cleanliness. Một standby đang replicate có thể đã nhận malicious changes.

### 37.2. Isolate identities/network

Thu hồi/rotate credentials bị lộ, chặn attacker path và dùng DR identity độc lập.

### 37.3. Chọn clean recovery point

Dùng immutable/offsite backup và PITR target trước thời điểm compromise nếu xác định được. Restore vào clean environment để kiểm tra.

### 37.4. Validate integrity

Kiểm tra database, application binaries, extensions, jobs, roles và secrets trước khi mở traffic.

### 37.5. Incident response coordination

Phối hợp security, DBA, infrastructure, application và business owners. Giữ evidence theo forensic/legal policy.

## 38. Backup và HA là các lớp bổ sung

Automation failover giảm downtime cho node failure; backup/PITR phục hồi từ các lỗi mà replication có thể lan truyền.

### 38.1. Standby không phải backup

Standby nhận thay đổi logic/physical từ primary. DELETE nhầm, corruption logic hoặc ransomware có thể lan sang standby.

### 38.2. PITR xử lý lịch sử

Base backup + WAL archive cho phép dựng cluster tại một recovery point trước lỗi, nếu chain đầy đủ.

### 38.3. Immutable/offsite

Bảo vệ backup khỏi cùng blast radius với primary/replicas. Cần identity, keys và retention độc lập.

### 38.4. Restore drill

Thử phục hồi không phụ thuộc HA manager/primary hiện tại. Đo thời gian retrieve, restore, replay, validation và cutover.

### 38.5. HA recovery sau failover

Sau promotion, tạo lại backup chain/standbys trên timeline mới và kiểm tra archive. Một failover thành công nhưng không khôi phục protection sẽ để hệ thống dễ tổn thương.

## 39. Đo RTO của quy trình tự động và thủ công

RTO end-to-end gồm nhiều giai đoạn, không chỉ thời gian promote.

~~~text
T_RTO =
  T_detect
+ T_decide
+ T_fence
+ T_promote
+ T_route
+ T_validate
~~~

### 39.1. T_detect

Từ sự cố tới khi alert/monitor phát hiện.

### 39.2. T_decide

Thời gian xác nhận failure và chọn candidate. Manual approval có thể tăng thời gian nhưng giảm risk trong ambiguity.

### 39.3. T_fence

Thời gian chặn old primary và xác minh fencing. Đây là bước không nên bỏ chỉ để giảm RTO.

### 39.4. T_promote và T_route

Thời gian promotion, update proxy/DNS/service discovery và refresh clients.

### 39.5. T_validate

Thời gian smoke tests/business checks tới khi service-ready. Chốt rõ RTO kết thúc ở application ready hay traffic fully restored.

## 40. Đánh giá automation bằng failure scenarios

Đừng chỉ test happy path. Mỗi scenario cần expected behavior, stop conditions và evidence.

| Scenario | Hành vi cần kiểm chứng |
|---|---|
| Primary process crash | Detect, fence, promote theo policy |
| Network partition | Không tạo hai writers |
| DCS/witness outage | Không có leader transition không an toàn |
| Standby lag cao | Candidate selection xét RPO |
| Fencing API timeout | Không giả định fencing thành công |
| Proxy stale connections | Old primary không còn nhận writes |
| Two candidates disagree | Escalate/manual decision |
| Backup/WAL unavailable | Không tuyên bố DR ready |
| Credential compromise | Isolate identity, clean recovery |
| Failback old primary | Rewind/reseed, không tự nhận writer |

### 40.1. Chaos testing có giới hạn

Fault injection cần có scope, blast radius, abort path và môi trường phù hợp. Không thử ngắt network/fence trên production nếu chưa có authorization/change plan.

### 40.2. Test partial failure

Mô phỏng một network path hỏng nhưng node vẫn chạy. Đây là scenario dễ bộc lộ split-brain logic.

### 40.3. Test control plane failure

Thử mất DCS/monitor/API hoặc credentials để biết automation fail-safe ra sao.

### 40.4. Test manual override

Xác minh người trực có thể dừng automation, xác định state và tiếp tục runbook bằng quyền khẩn cấp.

### 40.5. Test restore path

Sau failover, thử backup/PITR độc lập để bảo đảm HA không che khuất backup gaps.


## 41. Lab: phân biệt process failure và network partition

Lab dùng hai PostgreSQL nodes và một observer trong network thử nghiệm.

### 41.1. Ghi baseline

Ghi role của P/S, SQL readiness, sender/receiver state, replay LSN, current endpoint và node reachability từ từng observer.

### 41.2. Mô phỏng PostgreSQL process failure

Dừng PostgreSQL trên P theo cách có kiểm soát. Quan sát process health, SQL probe, alert và HA manager state.

### 41.3. Mô phỏng network partition

Chặn một đường mạng giữa observer/standby và P nhưng giữ P chạy. Kiểm tra observer khác có còn kết nối được P không và P có còn nhận writes từ app subnet không.

### 41.4. Quan sát quyết định

Xác nhận HA manager có đủ quorum và fencing path không. Không để test tự promote production node; dùng lab-only fencing integration.

### 41.5. So sánh kết quả

Ghi detection time, false-positive behavior, decision state và action. Xác định signals nào phân biệt process failure với partition.

## 42. Lab: fencing trước promotion

### 42.1. Chuẩn bị hai node

Dựng primary và standby, cùng một control plane lab có thể tắt VM hoặc chặn network của primary.

### 42.2. Kiểm tra preconditions

Ghi candidate replay LSN, timeline, synchronous state và current leader ownership.

### 42.3. Mô phỏng fencing command

Chạy fencing action lab-only. Lưu control-plane result và xác nhận old primary không thể nhận application writes.

### 42.4. Thử fencing failure

Cho fencing API timeout hoặc trả trạng thái chưa xác nhận. Kiểm tra automation có dừng promotion và báo người vận hành hay không.

### 42.5. Promote sau khi xác nhận

Chỉ trong lab, promote standby sau khi fencing đã được xác nhận. Kiểm tra `pg_is_in_recovery()</BT> và endpoint routing.

## 43. Lab: manual failover khi HA manager không sẵn sàng

### 43.1. Mô phỏng control-plane outage

Trong lab, làm monitor/DCS không thể truy cập nhưng giữ node state để điều tra. Không can thiệp hệ thống production.

### 43.2. Thu thập trạng thái

Kiểm tra PostgreSQL role, timeline, LSN, active sessions, replication connections và network reachability từ nhiều vị trí.

### 43.3. Xác định quyền authoritative

Đọc leader lock/lease/epoch từ control plane nếu còn khả dụng. Nếu state không rõ, ghi uncertainty và dừng thao tác promote.

### 43.4. Fencing bằng đường độc lập

Thực hiện power/network fencing qua control plane lab độc lập. Xác nhận old primary không thể ghi.

### 43.5. Manual promote và route

Theo runbook, promote candidate, cập nhật endpoint, refresh clients, chạy smoke tests và ghi timeline/RPO/RTO.

## 44. Lab: xử lý failback và rejoin

### 44.1. Ghi lại timeline

Sau promotion lab, ghi timeline mới và LSN của primary hiện tại.

### 44.2. Khởi động lại old primary ở trạng thái isolated

Không mở application traffic. Xác nhận node cũ không được coi là primary authoritative.

### 44.3. Thử pg_rewind

Nếu lab đáp ứng prerequisites, dùng pg_rewind để đưa node cũ theo timeline mới. Nếu không, tạo base backup mới.

### 44.4. Rejoin như standby

Cấu hình upstream, replication slot/credentials và start node. Theo dõi receiver/replay progress.

### 44.5. Xác nhận topology

Kiểm tra sender/receiver views, timeline, lag và endpoint routing. Chỉ kết thúc lab khi old primary không còn nhận writes độc lập.

## 45. Mẫu decision record cho failover

Mỗi quyết định failover quan trọng nên có record ngắn, có thể kiểm tra lại.

| Trường | Nội dung cần ghi |
|---|---|
| Incident ID | Mã incident/change |
| T0/timezone | Thời điểm bắt đầu |
| Failure mode | Process, host, network, region, security |
| Primary state | Alive/down/unknown và bằng chứng |
| Quorum/leader | Voter/lease/epoch state |
| Candidate | Node, timeline, replay/flush LSN |
| Fencing | Cơ chế, kết quả, evidence |
| RPO impact | Mức dữ liệu có thể mất |
| Approval | Người quyết định và thời điểm |
| Action | Promote/route/recovery choice |
| Validation | Checks và kết quả |
| Follow-up | Rejoin, backup, reconciliation |

### 45.1. Ghi unknown khi chưa biết

Không điền “down” nếu chỉ mất ping. Ghi unknown/partial và hành động cần xác minh.

### 45.2. Ghi evidence reference

Liên kết logs, dashboards, cloud events hoặc command outputs theo incident system. Không chỉ ghi kết luận.

### 45.3. Record trước và sau action

Chụp state trước promotion và sau routing để có thể truy nguyên thay đổi.

### 45.4. Ghi RPO breach riêng

Nếu vượt RPO, ghi transaction boundary ước lượng, data reconciliation và business acceptance.

### 45.5. Review sau incident

Dùng record để cải thiện threshold, automation preconditions, runbook và training.

## 46. Các lỗi vận hành thường gặp

1. Promote standby chỉ vì primary không ping được từ một subnet.
2. Không fence old primary trước khi mở writes ở node mới.
3. Tin rằng leader election tự động dừng node cũ.
4. Chỉ kiểm tra process health mà không kiểm tra SQL/application readiness.
5. Chọn candidate theo priority mà không xem timeline/LSN/RPO.
6. Coi quorum là bằng chứng candidate có dữ liệu mới nhất.
7. Dùng synchronous label mà không biết remote write/flush/apply semantics.
8. Chạy manual promote trong lúc HA manager vẫn đang xử lý transition.
9. Retry fencing API sau timeout mà không kiểm tra action đầu đã thành công chưa.
10. Chuyển DNS nhưng để old connection pools tiếp tục ghi node cũ.
11. Không pause background jobs/queue consumers trong cutover.
12. Chấp nhận data loss mà không có business approval.
13. Dùng break-glass credentials không audit hoặc không rotate sau incident.
14. Không có người backup on-call hoặc escalation path.
15. Không ghi rõ preconditions/stop conditions trong runbook.
16. Chỉ diễn tập switchover có kế hoạch, không test crash/partition.
17. Không test DCS/monitor/proxy/control-plane outage.
18. Failback old primary bằng cách bật lại service và đổi endpoint.
19. Không rewind/reseed node cũ sau timeline divergence.
20. Không khôi phục backup/WAL archive/standby protection sau failover.
21. Không phân biệt node failure với logical corruption/ransomware.
22. Không test manual override khi automation kẹt.
23. Alert không tới người có quyền fencing/promote.
24. Dùng một threshold health check cho mọi service tier.
25. Không ghi timeline, LSN, fencing evidence và RPO thực tế.

## 47. Bài tập thực hành

### Bài 1 — Failure detection

Health check timeout chứng minh điều gì?

**Đáp án:** Observer không nhận phản hồi đúng hạn; không chứng minh host/process đã chết.

### Bài 2 — False positive

Nêu hai nguyên nhân node khỏe bị đánh dấu down.

**Gợi ý:** Network congestion, CPU starvation, overloaded disk, firewall hoặc timeout quá ngắn.

### Bài 3 — False negative

Vì sao process running không đủ chứng minh service healthy?

**Đáp án:** SQL/query path có thể không hoạt động do locks, disk, connection exhaustion hoặc dependencies.

### Bài 4 — Split-brain

Split-brain là gì?

**Đáp án:** Nhiều nodes cùng được xem là primary authoritative và nhận writes độc lập.

### Bài 5 — Fencing

Mục tiêu của fencing là gì?

**Đáp án:** Ngăn old primary tiếp tục nhận writes trước khi primary mới được mở.

### Bài 6 — DNS

Đổi DNS có phải fencing đầy đủ không?

**Đáp án:** Không; clients cũ có thể giữ connections hoặc endpoint cache.

### Bài 7 — Quorum

Quorum giúp giải quyết điều gì?

**Gợi ý:** Chỉ một partition có thể đạt majority trong membership nhất quán để giữ quyền điều phối.

### Bài 8 — Witness

Witness có tự tắt primary cũ không?

**Đáp án:** Không; nó hỗ trợ quyết định/quorum nhưng cần fencing mechanism.

### Bài 9 — Synchronous replication

Synchronous replication có đảm bảo candidate có mọi transaction nếu failover không?

**Đáp án:** Phụ thuộc acknowledgement mode, selected standby và failure model; phải kiểm tra cụ thể.

### Bài 10 — Candidate selection

Ngoài node priority, cần xem những gì?

**Gợi ý:** Timeline, receive/flush/replay LSN, synchronous state, WAL availability và node health.

### Bài 11 — Auto-failover

Nêu các preconditions quan trọng.

**Gợi ý:** Quorum/leader authority, fencing đã xác minh, candidate đủ điều kiện, RPO policy và routing path.

### Bài 12 — Manual approval

Khi nào nên chuyển sang manual decision?

**Gợi ý:** Network partition, fencing uncertainty, candidates khác timeline/LSN, corruption hoặc RPO breach.

### Bài 13 — Idempotency

Vì sao không nên chạy lại promote ngay sau API timeout?

**Đáp án:** Lệnh có thể đã thành công nhưng response bị mất; cần kiểm tra state trước.

### Bài 14 — HA manager

Patroni/repmgr/pg_auto_failover có thay thế business validation không?

**Đáp án:** Không.

### Bài 15 — Health layers

Nêu bốn lớp health cần xem.

**Gợi ý:** Process, SQL readiness, replication, application/service health.

### Bài 16 — Break-glass

Vì sao cần access path độc lập?

**Đáp án:** Production identity/network có thể chính là dependency đang bị sự cố.

### Bài 17 — Incident commander

Vai trò chính của incident commander là gì?

**Đáp án:** Điều phối, timeline, phân công và escalation; không nhất thiết tự chạy mọi lệnh DBA.

### Bài 18 — Business owner

Ai nên chấp nhận data loss vượt RPO?

**Đáp án:** Người có thẩm quyền business/service theo policy.

### Bài 19 — Freeze writes

Vì sao cần pause queue consumers và scheduled jobs khi cutover?

**Gợi ý:** Chúng có thể tiếp tục ghi vào old primary hoặc tạo side effects.

### Bài 20 — Manual failover

Nêu thứ tự chính của failover.

**Gợi ý:** Declare, xác nhận state, chọn candidate, freeze writes, fence old primary, promote, route, validate.

### Bài 21 — Switchover

Switchover khác failover thế nào?

**Đáp án:** Switchover có kế hoạch khi primary còn hoạt động; failover xử lý sự cố không mong muốn.

### Bài 22 — Fencing failure

Nếu fencing command timeout, có được coi là thành công không?

**Đáp án:** Không; cần xác minh qua control plane độc lập.

### Bài 23 — Rejoin

Old primary sau promotion có thể bật lại và nhận writes không?

**Đáp án:** Không; phải giữ isolated và rejoin như standby qua rewind/reseed.

### Bài 24 — pg_rewind

Khi nào có thể dùng?

**Gợi ý:** Khi prerequisites như checksums/wal_log_hints và WAL cần thiết đáp ứng, version phù hợp.

### Bài 25 — Reseed

Khi nào rebuild từ base backup là lựa chọn phù hợp?

**Đáp án:** Khi rewind không khả dụng, thiếu WAL hoặc node cũ không đáng tin.

### Bài 26 — RTO

RTO có chỉ gồm promote time không?

**Đáp án:** Không; gồm detect, decide, fence, promote, route và validate.

### Bài 27 — Partial failure

Vì sao cần probe từ nhiều network locations?

**Gợi ý:** Phân biệt node down với một network path bị partition.

### Bài 28 — DCS outage

Khi DCS mất quorum, vì sao không nên tự promote thủ công ngay?

**Đáp án:** HA manager có thể đang giữ lock/state chưa rõ; cần xác minh authority để tránh hai actors promote.

### Bài 29 — Backup

Vì sao standby không thay thế backup/PITR?

**Đáp án:** Logical corruption và malicious changes có thể được replicate sang standby.

### Bài 30 — Security incident

Vì sao ransomware cần quy trình khác node crash?

**Gợi ý:** Cần xác định compromise, isolate identities và chọn clean recovery point.

### Bài 31 — Approval gate

Nêu hai hành động nên có approval gate.

**Gợi ý:** Force promotion khi không có quorum, chấp nhận RPO breach, mở writes sau fencing.

### Bài 32 — Observability

Dashboard HA cần hiển thị những gì?

**Gợi ý:** Role map, LSN/lag, quorum/lease, fencing, endpoint routing và business health.

### Bài 33 — Alert context

Một alert failover tốt nên đính kèm gì?

**Gợi ý:** Node/region, leader/candidate, lag, LSN/timeline, fencing state và runbook.

### Bài 34 — Maintenance

Vì sao không nên restart đồng thời nhiều quorum members?

**Đáp án:** Có thể làm mất majority và khiến leader coordination unavailable.

### Bài 35 — Lease

Lease hết hạn có chứng minh old process đã dừng không?

**Đáp án:** Không; cần fencing/write-path enforcement.

### Bài 36 — Manual override

Manual override cần điều kiện nào?

**Gợi ý:** Người được ủy quyền, state snapshot, fencing proof, action log và validation plan.

### Bài 37 — Incident record

Tại sao cần ghi fact và hypothesis riêng?

**Đáp án:** Tránh quyết định dựa trên giả định chưa được xác minh.

### Bài 38 — Failback

Sau khi old primary rejoin như standby, khi nào mới switchover về nó?

**Gợi ý:** Khi catch up, timeline/replication khỏe, validation đạt và có maintenance/approval.

### Bài 39 — Automation test

Nêu một scenario ngoài happy path cần test.

**Gợi ý:** Network partition, DCS outage, fencing timeout, stale proxy connection hoặc two candidates disagree.

### Bài 40 — Thiết kế tổng hợp

Một PostgreSQL HA cluster có primary P, standby S, monitor ở region khác. Observer mất kết nối tới P nhưng application region vẫn ghi được vào P; S nhận timeout và muốn promote. Hãy mô tả quy trình an toàn.

**Gợi ý:** Xem đây là network partition chưa xác định node chết. Thu thập signals từ nhiều observers, kiểm tra quorum/lease và app write path; không promote chỉ vì timeout. Dùng independent fencing để chặn P, xác minh kết quả, đánh giá S replay/flush LSN và RPO, yêu cầu approval nếu data loss/authority chưa rõ, sau đó promote S, route traffic và validate. Giữ P fenced khi quay lại, rewind/reseed rồi rejoin.

## 48. Checklist thiết kế HA automation

### 48.1. Failure detection

- [ ] Health checks phân biệt process, SQL, replication và application?
- [ ] Có multi-observer/failure-domain checks?
- [ ] Timeout/consecutive failures phù hợp RTO và false-positive risk?
- [ ] Alert có context và escalation route?

### 48.2. Authority và fencing

- [ ] Leader election/quorum/lease semantics được hiểu?
- [ ] Fencing control plane độc lập với node bị lỗi?
- [ ] Fencing result được verify?
- [ ] Fencing token/epoch được enforce trên write path nếu dùng?
- [ ] Có stop condition khi fencing không xác nhận?

### 48.3. Candidate và data loss

- [ ] Candidate selection xét timeline/LSN/replication state?
- [ ] Synchronous acknowledgement semantics rõ?
- [ ] RPO breach có business approval?
- [ ] Logical corruption/ransomware có clean recovery path?

### 48.4. Promotion và routing

- [ ] Chỉ một actor được phép promote?
- [ ] Actions idempotent hoặc state-checked?
- [ ] Old primary được fence trước traffic?
- [ ] Proxy/DNS/connection pools được cập nhật?
- [ ] Application/business validation trước mở toàn bộ traffic?

### 48.5. Human operations

- [ ] Incident commander/DBA/infra/app/business roles rõ?
- [ ] Break-glass access đã thử và audit?
- [ ] On-call backup/escalation có sẵn?
- [ ] Runbook có preconditions, expected results và stop conditions?
- [ ] Failback/rejoin/rewind/reseed được diễn tập?

## 49. Checklist diễn tập và sau incident

- [ ] Test process crash?
- [ ] Test network partition/partial failure?
- [ ] Test quorum/DCS/monitor outage?
- [ ] Test fencing success và fencing timeout?
- [ ] Test stale clients/proxy routing?
- [ ] Test manual override và break-glass?
- [ ] Test async data-loss/RPO decision?
- [ ] Test old primary rejoin?
- [ ] Test backup/PITR độc lập?
- [ ] Đo RTO end-to-end?
- [ ] Ghi RPO thực tế và business acceptance?
- [ ] Có post-incident actions với owner/deadline?
- [ ] Alert/runbook/configuration được cập nhật?
- [ ] Diễn tập lại sau thay đổi lớn?

## 50. Bảng tra cứu nhanh

| Khái niệm | Ý nghĩa |
|---|---|
| HA automation | Tự động giám sát và chuyển role/routing khi failure |
| Failure detection | Phát hiện tín hiệu node/service không phản hồi |
| Failure declaration | Xác định node unavailable theo policy |
| False positive | Node khỏe bị đánh dấu down |
| False negative | Node lỗi nhưng health check vẫn pass |
| Partial failure | Một phần network/service/control plane bị lỗi |
| Network partition | Các nhóm nodes không liên lạc được |
| Split-brain | Nhiều primary cùng nhận writes |
| Quorum | Majority/đủ phiếu để giữ quyền điều phối |
| Witness | Thành viên hỗ trợ quorum/election |
| Lease | Quyền leader có thời hạn |
| Fencing | Ngăn old primary tiếp tục nhận writes |
| Fencing token | Epoch/token để từ chối writer cũ |
| Promotion | Chuyển standby thành primary |
| Switchover | Chuyển primary có kế hoạch |
| Failover | Chuyển primary do sự cố |
| Failback | Chuyển workload về topology mong muốn |
| Rejoin | Đưa node cũ trở lại như standby |
| pg_rewind | Đồng bộ node diverged khi đủ điều kiện |
| Break-glass | Quyền truy cập khẩn cấp có kiểm soát |
| Human-in-the-loop | Bước cần con người quyết định/approve |
| Stop condition | Điều kiện bắt buộc dừng automation/runbook |
| RPO | Mức mất dữ liệu tối đa chấp nhận |
| RTO | Thời gian phục hồi tối đa |
| Incident commander | Người điều phối incident |
| Audit trail | Bằng chứng actor/action/state/time |
| Idempotency | Retry action không tạo side effect ngoài dự kiến |

## 51. Kết luận

**Tự động hóa giúp HA phản ứng nhanh, nhưng không thể thay thế fencing, quy tắc dữ liệu và quyết định nghiệp vụ.** Health check chỉ quan sát một phần hệ thống; timeout không chứng minh primary đã chết. Quorum và leader election giúp xác định quyền điều phối, nhưng không tự bảo đảm candidate có dữ liệu mới nhất hoặc old primary đã ngừng ghi. Fencing phải được xác nhận trước khi mở writes trên primary mới để tránh split-brain.

Một thiết kế tốt tự động hóa các bước có tín hiệu và kết quả xác định: thu thập metrics/logs, alert, kiểm tra preconditions, fencing đã được thiết kế, promotion theo policy, routing và smoke tests. Khi có network partition, fencing uncertainty, candidates khác timeline/LSN, corruption, security incident hoặc RPO breach, quy trình cần human approval và business owner. Manual intervention phải có break-glass access, vai trò, escalation, preconditions, expected results, stop conditions và audit trail.

Sau failover, old primary cần được giữ isolated rồi rejoin bằng pg_rewind khi đủ điều kiện hoặc reseed từ base backup. Failback không phải đổi DNS ngược; phải có một authoritative writer, validation và kế hoạch xử lý writes phát sinh. Backup/PITR vẫn là lớp độc lập vì standby có thể nhận cùng logical corruption hoặc malicious changes.

Nguyên tắc vận hành: **tự động hóa thao tác có thể chứng minh an toàn, dừng khi bằng chứng không đủ, gọi đúng người cho quyết định có rủi ro dữ liệu, và diễn tập cả happy path lẫn partial failures.** Chỉ một quy trình được đo, audit và thử lại mới có thể đáp ứng RPO/RTO trong sự cố thật.

