# Promotion và bảo đảm chỉ một máy chủ nhận ghi trong PostgreSQL

Trong PostgreSQL high availability (HA), **promotion** là quá trình chuyển một standby server đang ở recovery mode thành primary có thể nhận writes. Promotion giúp dịch vụ tiếp tục hoạt động khi primary hiện tại bị lỗi hoặc khi DBA chủ động chuyển vai trò giữa hai máy chủ.

Promotion tự nó không bảo đảm rằng chỉ có một primary. Nếu primary cũ vẫn chạy và vẫn nhận được writes trong khi standby mới được promote, cả hai có thể cùng chấp nhận transaction. Đây là tình huống **split brain**: hai nhánh dữ liệu độc lập cùng được xem là authoritative, khiến việc hợp nhất trở nên khó khăn và có thể làm mất dữ liệu.

Muốn bảo đảm chỉ một máy chủ nhận ghi, hệ thống phải phối hợp ba việc:

1. **Chọn một node được quyền làm primary** bằng cơ chế điều phối có quorum hoặc một nguồn quyết định có thẩm quyền.
2. **Fencing primary cũ** để nó không thể tiếp tục nhận writes.
3. **Promote standby được chọn và chuyển routing** tới primary mới sau khi trạng thái an toàn đã được xác nhận.

Bài **“Promotion và bảo đảm chỉ một máy chủ nhận ghi”**, thuộc chương **Tính sẵn sàng cao** của module **Database Engine Relational PostgreSQL**, giải thích cơ chế promotion, timeline, failover và switchover, synchronous/asynchronous replication, quorum, fencing/STONITH, quản lý endpoint, rejoin node cũ, giám sát và quy trình xử lý sự cố.

> **Nguyên tắc cốt lõi:** PostgreSQL có thể promote một standby, nhưng PostgreSQL streaming replication không tự cung cấp một hệ thống leader election và fencing hoàn chỉnh. Muốn có single-writer guarantee, phải bảo đảm primary cũ đã mất khả năng ghi trước khi primary mới được phép nhận writes.

---

## 1. Primary và standby trong HA

Một topology physical streaming replication cơ bản có một primary và một hoặc nhiều standby:

~~~text
                    Ứng dụng
                       |
                       v
                 Write endpoint
                       |
                       v
                 Primary node
                  /         \
                 / WAL       \ WAL
                v             v
          Standby A       Standby B
          (recovery)      (recovery)
~~~

- **Primary:** nhận SQL writes và tạo WAL.
- **Standby:** nhận WAL từ primary, replay WAL và duy trì bản sao dữ liệu.
- **Promotion:** chuyển một standby thành primary mới.
- **Failover:** chuyển dịch vụ sang standby khi primary bị lỗi.
- **Switchover:** chuyển vai trò primary theo kế hoạch, thường để bảo trì hoặc di chuyển hạ tầng.

PostgreSQL physical replication là cơ chế chuyển WAL một chiều. Standby bình thường ở recovery mode và không nhận writes ứng dụng.

## 2. Promotion là gì?

Promotion kết thúc quá trình recovery của standby và chuyển server sang chế độ hoạt động bình thường.

Khi promotion hoàn tất:

- Server không còn ở standby recovery mode.
- Server có thể nhận writes.
- Server bắt đầu ghi WAL theo timeline mới.
- Các standby khác cần theo dõi timeline mới và kết nối tới primary mới theo cấu hình HA.
- Primary cũ, nếu còn tồn tại, phải được ngăn nhận writes và sau đó được rejoin theo quy trình.

Promotion không sao chép ngược dữ liệu về primary cũ và cũng không tự sửa routing của ứng dụng.

## 3. Promotion không đồng nghĩa với leader election

PostgreSQL cung cấp cơ chế để yêu cầu standby promote. Nó không tự quyết định toàn bộ câu hỏi phân tán:

- Primary cũ đã chết thật hay chỉ mất kết nối?
- Có node nào đang giữ quyền leader?
- Standby nào có WAL mới nhất?
- Node nào được phép nhận writes?
- Ai có quyền fencing primary cũ?
- Khi nào cập nhật endpoint?
- Node cũ sẽ được rejoin bằng cách nào?

Đây là trách nhiệm của HA manager/orchestrator hoặc một control plane được thiết kế cho mục đích đó.

Các hệ thống quản lý HA có thể phối hợp PostgreSQL với distributed configuration store, quorum, health checks, fencing và routing. Dù dùng công cụ nào, cần hiểu rõ guarantees và failure modes của công cụ đó.

## 4. Các bước logic của promotion

Ở mức khái niệm:

1. HA manager phát hiện primary không còn khỏe.
2. Hệ thống xác định đây là lỗi thật hay network partition.
3. Primary cũ bị fence hoặc được chứng minh không còn khả năng nhận writes.
4. Control plane có quorum chọn một standby làm candidate.
5. Candidate được yêu cầu promote.
6. PostgreSQL hoàn tất recovery tới WAL có sẵn và bắt đầu timeline mới.
7. Health checks xác nhận candidate là primary mới.
8. Write endpoint được chuyển tới node mới.
9. Những standby còn lại được cấu hình theo primary mới.
10. Primary cũ được giữ cách ly cho tới khi có thể rejoin an toàn.

~~~text
Primary failure suspected
          |
          v
   Verify failure / quorum
          |
          v
  Fence old primary
          |
          v
  Select one standby
          |
          v
      Promote
          |
          v
  Verify new primary
          |
          v
  Move write endpoint
          |
          v
  Rejoin other nodes
~~~

Thứ tự fencing và promotion rất quan trọng. Không được để hai node cùng có quyền nhận writes trong khoảng chuyển đổi.

## 5. Split brain là gì?

**Split brain** xảy ra khi hai hoặc nhiều PostgreSQL nodes cùng hoạt động như primary và cùng chấp nhận writes cho một logical database service.

Ví dụ:

- Primary A bị tách khỏi network của HA manager.
- A vẫn kết nối được với một nhóm ứng dụng.
- HA manager không nhìn thấy A và promote standby B.
- Một nhóm ứng dụng ghi vào A, nhóm khác ghi vào B.

~~~text
           Network partition
        +----------------------+
        |                      |
        v                      v
   Primary A               Standby B
   (vẫn nhận write)        (được promote)
        ^                      ^
        |                      |
    App group 1             App group 2

          Hai nhánh cùng nhận writes
                 SPLIT BRAIN
~~~

Hai node có thể cùng trả về kết quả pg_is_in_recovery() là false. PostgreSQL không tự hợp nhất các transaction của hai timeline độc lập thành một lịch sử chung.

## 6. Vì sao split brain nguy hiểm?

Sau khi hai primary nhận writes độc lập:

- Cùng một primary key có thể được tạo với hai giá trị khác nhau.
- Một row có thể được UPDATE trên cả hai nhánh theo hai hướng.
- DELETE trên một nhánh không tự xuất hiện ở nhánh kia.
- Sequence values có thể trùng hoặc lệch.
- Business transactions có thể bị thực hiện hai lần.
- Hai nhánh WAL có lịch sử khác nhau.
- Không có thao tác merge tổng quát an toàn cho mọi schema và business rules.

Có thể cần chọn một nhánh làm authoritative, trích xuất dữ liệu từ nhánh còn lại và reconcile thủ công. Đây là công việc phức tạp, không phải một lệnh failback đơn giản.

## 7. Single-writer guarantee cần nhiều lớp

Một thiết kế HA nên có các lớp:

| Lớp | Trách nhiệm |
|---|---|
| Replication | Duy trì standby có dữ liệu gần primary |
| Leader election/quorum | Quyết định node nào được quyền làm leader |
| Fencing | Ngăn primary cũ tiếp tục ghi |
| Promotion control | Promote đúng một candidate |
| Routing | Đưa ứng dụng tới primary đã được xác nhận |
| Monitoring | Phát hiện lag, split brain và trạng thái bất thường |
| Rejoin procedure | Đưa node cũ trở lại dưới dạng standby |

Routing và fencing là hai việc khác nhau. Chuyển load balancer sang B không tự ngăn ứng dụng hoặc người quản trị kết nối trực tiếp tới A.

## 8. Fencing là gì?

**Fencing** là hành động cô lập một node khỏi khả năng gây tác động lên hệ thống dùng chung hoặc nhận writes.

Mục tiêu là bảo đảm node cũ không thể tiếp tục hoạt động như primary sau khi quyền leader đã chuyển sang node mới.

Các cách fencing có thể gồm:

- Tắt nguồn node cũ qua hardware/cloud control plane (STONITH).
- Cắt quyền truy cập mạng tới database service và các client networks.
- Thu hồi quyền truy cập storage dùng chung trong topology có shared storage.
- Dùng watchdog hoặc cơ chế self-fencing đáng tin cậy khi node mất quyền lease.
- Kết hợp nhiều lớp fencing để tránh một đường truy cập còn sót.

Biện pháp cụ thể phụ thuộc hạ tầng. Phải kiểm chứng rằng fencing thật sự ngăn được writes, không chỉ làm health check thất bại.

## 9. STONITH

STONITH thường được hiểu là “Shoot The Other Node In The Head”: cơ chế buộc tắt hoặc cách ly node cũ qua một kênh quản trị độc lập.

Ví dụ hạ tầng có thể cung cấp:

- Cloud instance stop/terminate.
- IPMI/iLO/iDRAC power control.
- Hypervisor VM power-off.
- Storage fencing.
- Network switch/SDN isolation.

Kênh quản trị cần hoạt động độc lập với network path đang bị partition. Nếu fencing command không xác nhận được trạng thái, không được giả định node cũ đã bị tắt.

### 9.1. Fencing phải có kết quả kiểm chứng

Một automation gọi API stop instance nhưng nhận timeout không biết node đã tắt hay chưa. Nó cần xác minh trạng thái cuối từ control plane độc lập hoặc cơ chế fencing tương ứng.

Nếu không thể xác minh old primary đã bị fence, việc promote có thể tạo split brain. Hệ thống phải có policy rõ ràng: chờ, thử fencing lại hoặc hy sinh availability để bảo toàn single-writer safety.

## 10. Network isolation không luôn đủ

Cắt một interface hoặc đổi DNS có thể không ngăn mọi đường ghi:

- Ứng dụng có thể kết nối bằng IP trực tiếp.
- Có thể còn connection pool cũ.
- Có thể có job, DBA hoặc backup tool kết nối trực tiếp.
- Primary cũ vẫn có thể nhận writes từ mạng nội bộ khác.
- Một node bị partition khỏi control plane vẫn có thể kết nối storage hoặc client network.

Fencing phải xem xét toàn bộ đường ghi có thể có. DNS/load balancer chỉ là lớp routing, không thay thế fencing.

## 11. Quorum và leader election

Trong hệ thống phân tán, quorum là số phiếu tối thiểu cần để đưa ra một quyết định có thẩm quyền.

Ví dụ control plane có ba voting members. Majority là hai phiếu. Khi một node mất liên lạc với phần còn lại:

- Nhóm có majority có thể tiếp tục điều phối.
- Nhóm thiểu số không được tự nhận quyền leader.
- Một candidate chỉ được promote nếu control plane cấp quyền theo policy.

~~~text
Control plane: 3 voters

Healthy:
  Voter A + Voter B + Voter C
  Majority = 2

Partition:
  Group 1: A + B  -> có quorum
  Group 2: C      -> không có quorum

Chỉ nhóm có quorum được phép ra quyết định leader.
~~~

Quorum của control plane không tự động fence PostgreSQL. Nó giúp thống nhất quyết định; fencing hoặc self-fencing phải ngăn node mất quorum tiếp tục nhận writes.

## 12. Lease và nguy cơ lease cũ

Một số HA managers dùng lease có thời hạn để cấp quyền leader.

Một node chỉ được làm leader khi còn giữ lease hợp lệ. Khi lease hết hạn, node phải tự ngừng nhận writes hoặc bị fence.

Lease chỉ an toàn khi:

- Đồng hồ và timeout assumptions được thiết kế phù hợp.
- Node cũ không thể tiếp tục ghi sau khi lease hết hạn.
- Control plane có consensus/quorum đúng.
- Node mới không được promote quá sớm khi lease cũ còn hiệu lực.
- Network partition không làm node cũ bỏ qua việc tự fence.

Chỉ lưu timestamp lease trong một file hoặc dùng heartbeat đơn giản không tạo thành distributed lease an toàn.

## 13. PostgreSQL không tự fence primary cũ

PostgreSQL streaming replication không có một cơ chế tích hợp để primary cũ tự biết rằng standby khác vừa được promote ở nơi khác trong mọi network partition.

Vì vậy:

- pg_promote() không tắt primary cũ.
- pg_ctl promote không chuyển endpoint.
- pg_is_in_recovery() chỉ mô tả trạng thái local của node.
- pg_stat_replication không phải quorum service.
- Synchronous replication không tự thực hiện STONITH.

HA manager phải phối hợp những phần này.

## 14. Failover và switchover

| Tiêu chí | Failover | Switchover |
|---|---|---|
| Nguyên nhân | Primary lỗi/không còn an toàn | Chuyển đổi có kế hoạch |
| Primary cũ | Có thể không phản hồi | Có thể điều khiển được |
| Writes | Có thể bị gián đoạn đột ngột | Thường được quiesce trước |
| WAL candidate | Có thể thiếu một số commits async | Có thể chờ candidate catch up |
| Fencing | Rất quan trọng | Vẫn cần xác nhận old primary không còn nhận writes |
| RPO | Phụ thuộc replication mode và candidate | Có thể gần hoặc bằng 0 với quy trình đồng bộ phù hợp |
| RTO | Phụ thuộc phát hiện, fencing, promote, routing | Phụ thuộc lịch bảo trì và chuẩn bị |

Switchover thường ít rủi ro dữ liệu hơn vì có thể kiểm soát writes và đợi standby bắt kịp. Nhưng vẫn cần ngăn old primary nhận writes sau khi vai trò đổi.

## 15. Promotion thủ công bằng pg_promote

Trên standby, có thể yêu cầu promotion bằng SQL:

~~~sql
SELECT pg_promote();
~~~

Function có tham số tùy chọn để chờ promotion hoàn tất:

~~~sql
SELECT pg_promote(wait => true, wait_seconds => 60);
~~~

Tên và chữ ký cần đối chiếu PostgreSQL version. Khi wait bật, function chờ tới khi promotion hoàn tất hoặc hết thời gian chờ. Giá trị trả về cho biết yêu cầu promotion có thành công theo semantics của function.

Đây là thao tác trên node được gọi. Nó không kiểm tra quorum toàn cluster, không fence primary cũ và không cập nhật ứng dụng routing.

**Chỉ chạy promotion thủ công khi đã xác định candidate và old-primary fencing theo runbook.**

## 16. Promotion bằng pg_ctl

Có thể yêu cầu promote từ host quản trị:

~~~bash
pg_ctl promote -D /var/lib/postgresql/data
~~~

Tùy chọn timeout/wait của pg_ctl phụ thuộc version. Xác nhận trạng thái server và logs sau lệnh.

pg_ctl promote gửi yêu cầu tới PostgreSQL instance tương ứng. Nó không thay thế HA manager hoặc fencing.

## 17. Promotion hoạt động với recovery như thế nào?

Standby liên tục replay WAL trong recovery mode. Khi nhận yêu cầu promote:

- Recovery được yêu cầu kết thúc.
- PostgreSQL tiến tới điểm recovery có thể đạt được với WAL sẵn có.
- Server chuyển sang trạng thái hoạt động bình thường.
- Một timeline mới được tạo.
- Server bắt đầu phục vụ primary role.

Các transaction commit trên primary cũ nhưng WAL chưa tới candidate có thể bị mất trong asynchronous replication. Promotion không thể tạo lại WAL mà standby chưa nhận được.

## 18. Timeline sau promotion

PostgreSQL dùng timeline để phân biệt các nhánh lịch sử WAL.

~~~text
Timeline 1 (primary cũ)
       |
       +---- WAL ---- WAL ---- WAL
                              |
                              | promote standby
                              v
                        Timeline 2
                              |
                              +---- WAL ---- WAL
~~~

Sau promotion, primary mới ghi WAL trên timeline mới. Timeline history file mô tả điểm timeline mới tách khỏi lịch sử trước đó.

Timeline giúp PostgreSQL quản lý lịch sử WAL, nhưng không tự giải quyết việc chọn nhánh authoritative nếu hai primary đã cùng nhận writes.

## 19. RPO phụ thuộc replication mode

**RPO (Recovery Point Objective)** là lượng dữ liệu tối đa doanh nghiệp chấp nhận mất khi failover.

### 19.1. Asynchronous replication

Trong asynchronous replication, primary có thể xác nhận COMMIT trước khi standby nhận/flush WAL tương ứng.

Nếu primary mất đột ngột:

- Standby có thể thiếu WAL của các transaction vừa commit.
- Promote standby có thể làm mất những commits đó.
- RPO phụ thuộc lag, network, WAL generation và thời điểm failure.

Asynchronous replication thường có latency thấp hơn nhưng không bảo đảm zero data loss.

### 19.2. Synchronous replication

Synchronous replication có thể yêu cầu primary chờ standby xác nhận WAL trước khi trả COMMIT success.

Ví dụ cấu hình minh họa:

~~~text
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
~~~

Với policy này, primary chờ synchronous standby được chọn theo cấu hình đáp ứng acknowledgment requirement. Cần hiểu chính xác standby nào được xem là synchronous và candidate nào chứa các commits đã được xác nhận.

Synchronous replication có thể giảm RPO đáng kể, nhưng không tự đảm bảo failover candidate luôn có toàn bộ commits nếu topology/policy cho phép các standby khác nhau nhận acknowledgments.

## 20. synchronous_commit levels

Các mức phổ biến:

| Setting | Điều kiện chờ |
|---|---|
| local | Local WAL flush |
| remote_write | Standby ghi WAL tới OS |
| on | Standby flush WAL bền vững theo synchronous policy |
| remote_apply | Standby replay/apply transaction |
| off | Có thể trả COMMIT trước local WAL flush |

remote_apply có thể cần khi ứng dụng cần transaction đã được apply trên synchronous standby trước khi primary trả COMMIT. Nó thường tăng commit latency.

### 20.1. Synchronous không tự có nghĩa zero data loss trong mọi failover

Cần xét:

- synchronous_standby_names.
- FIRST hay ANY quorum mode.
- Standby nào đã xác nhận transaction cụ thể.
- Candidate nào được chọn promote.
- WAL đã flush hay mới write/apply.
- Có fencing và leader election đúng hay không.

Trong ANY N quorum, một transaction được xác nhận bởi N standby bất kỳ trong nhóm. Không thể suy ra mọi standby candidate đều đã nhận transaction đó. HA manager phải chọn candidate có WAL phù hợp hoặc có policy chấp nhận RPO tương ứng.

## 21. Quorum synchronous replication

Cấu hình quorum có thể dùng dạng:

~~~text
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
~~~

Ý nghĩa là commit chờ acknowledgment từ hai standby bất kỳ trong danh sách theo semantics của synchronous replication.

Điều này tăng khả năng tiếp tục commit khi một standby lỗi, nhưng khi failover phải biết node nào đã có WAL được xác nhận. Quorum commit không đồng nghĩa mọi node đều giống nhau tại mọi thời điểm.

Thiết kế quorum cần tính cả số voting/replication nodes, failure domains, candidate selection, network partitions, latency và RPO/RTO objectives.

## 22. WAL positions để chọn candidate

Trên primary, có thể quan sát standby progress:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication
ORDER BY application_name;
~~~

- sent_lsn: WAL đã gửi.
- write_lsn: WAL đã được standby ghi nhận ở mức write.
- flush_lsn: WAL đã flush trên standby.
- replay_lsn: WAL đã replay trên standby.

Candidate có flush/replay LSN gần nhất thường có ít WAL gap hơn, nhưng quyết định phải tính timeline, sync policy, WAL receiver state và thời điểm metrics được lấy.

Không chọn candidate chỉ dựa trên ping latency hoặc node có health check xanh.

## 23. Theo dõi standby receive và replay

Trên standby:

~~~sql
SELECT
    pg_is_in_recovery() AS in_recovery,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_time;
~~~

Có thể quan sát WAL receiver:

~~~sql
SELECT *
FROM pg_stat_wal_receiver;
~~~

- Receive LSN cho biết WAL đã nhận.
- Replay LSN cho biết WAL đã áp dụng.
- Khoảng cách giữa hai giá trị phản ánh WAL backlog trên standby.
- Nếu walreceiver không có row, standby có thể đang disconnected hoặc lấy WAL qua archive.

pg_last_xact_replay_timestamp() có thể cũ khi primary idle. Không dùng riêng timestamp này để kết luận lag.

## 24. pg_is_in_recovery không chứng minh node là leader duy nhất

~~~sql
SELECT pg_is_in_recovery();
~~~

- true: node đang ở recovery mode, thường là standby.
- false: node không còn ở recovery mode, thường là primary sau startup/promotion.

Nếu split brain đã xảy ra, cả primary cũ và primary mới đều có thể trả false.

Do đó, function này chỉ trả lời “node này có đang recovery không?”, không trả lời “node này có phải primary duy nhất được phép nhận writes không?”.

Cần kết hợp với authoritative leader state từ HA manager, fencing status và routing policy.

## 25. Write endpoint và connection routing

Ứng dụng thường kết nối thông qua:

- HAProxy.
- PgBouncer kết hợp health check/endpoint.
- Virtual IP.
- DNS/service discovery.
- Cloud database endpoint.
- Kubernetes Service hoặc operator-managed endpoint.

Endpoint nên trỏ tới primary đã được xác nhận. Health check cần phân biệt primary/standby và kiểm tra quyền leader từ control plane khi có thể.

### 25.1. Routing không phải fencing

Nếu endpoint chuyển từ A sang B:

- Connection pool cũ có thể vẫn giữ kết nối A.
- Một job có thể dùng IP trực tiếp của A.
- DBA có thể mở session trực tiếp vào A.
- A có thể vẫn mở port và nhận writes.

Cần đóng/cắt những đường ghi cũ bằng fencing và/hoặc policy phía database/network, không chỉ đổi DNS.

## 26. Client reconnect sau promotion

Khi primary đổi:

- Connection TCP cũ thường bị ngắt hoặc trở nên lỗi.
- Ứng dụng cần retry có backoff.
- Connection pool cần bỏ connection cũ.
- Transaction đang chạy có thể có kết quả không rõ với client nếu kết nối mất trước khi nhận COMMIT response.
- Các request không idempotent có nguy cơ được gửi lại và thực thi hai lần.

Thiết kế application retry cần transaction idempotency hoặc request keys cho nghiệp vụ nhạy cảm. Không tự động retry mọi transaction sau connection loss mà không đánh giá kết quả commit.

## 27. DNS TTL và virtual IP

DNS failover có thể bị ảnh hưởng bởi client DNS cache, runtime resolver cache, connection pool, TTL, proxy/service discovery cache và network route convergence.

Virtual IP hoặc load balancer có thể chuyển nhanh hơn nhưng vẫn chỉ là routing. Cần xác nhận primary cũ bị fence.

Dùng endpoint quản lý tập trung và tránh hardcode địa chỉ primary trong nhiều services.

## 28. Planned switchover

Một quy trình switchover tổng quát:

1. Chọn standby candidate.
2. Xác nhận standby khỏe và đủ WAL capacity.
3. Dừng hoặc quiesce application writes trên primary.
4. Chờ transactions đang chạy hoàn tất hoặc xử lý theo policy.
5. Lấy LSN cuối cùng của primary.
6. Chờ candidate nhận và replay tới boundary đó.
7. Xác nhận candidate đã bắt kịp.
8. Stop/demote old primary và xác nhận nó không nhận writes.
9. Promote candidate.
10. Verify timeline, recovery state và write capability.
11. Chuyển write endpoint.
12. Cấu hình old primary thành standby của primary mới.
13. Rejoin và kiểm tra replication.

Chi tiết lệnh phụ thuộc HA manager và topology. Một quy trình có kiểm soát thường có RPO thấp hơn failover bất ngờ vì có thể chờ replay đầy đủ trước khi promote.

## 29. Unplanned failover

Khi primary mất:

1. Health check phát hiện failure.
2. Control plane xác định quorum và trạng thái node.
3. Fencing old primary.
4. Chọn standby theo WAL progress và synchronous policy.
5. Promote candidate.
6. Verify primary mới.
7. Update routing.
8. Xác nhận ứng dụng reconnect.
9. Rebuild/rejoin các standby khác.
10. Ghi nhận RPO thực tế và điều tra nguyên nhân.

Không promote đồng thời nhiều standbys. Chỉ một candidate được cấp quyền leader.

## 30. Primary cũ quay trở lại

Sau failover, primary cũ có thể khởi động lại với lịch sử WAL cũ.

Không cho node đó nhận writes hoặc expose vào write endpoint.

Nếu node cũ đã bị divergent so với primary mới, nó cần được đưa về cùng lịch sử. Các lựa chọn:

- pg_rewind nếu đủ điều kiện.
- Tạo lại standby từ base backup của primary mới.
- Restore theo quy trình physical recovery được hỗ trợ.

Không đơn giản khởi động primary cũ như primary độc lập rồi kết nối lại ứng dụng.

## 31. pg_rewind

pg_rewind có thể đồng bộ một data directory bị divergent với một source cluster bằng cách xác định và sao chép các blocks đã thay đổi kể từ điểm phân nhánh.

Ví dụ khái niệm:

~~~bash
pg_rewind --target-pgdata=/var/lib/postgresql/old-primary \
          --source-server="host=new-primary.example dbname=postgres user=rewind_user"
~~~

Các điều kiện quan trọng thường gồm:

- Data checksums được bật khi initdb hoặc wal_log_hints=on.
- full_page_writes=on.
- Target cluster đã được shutdown cleanly theo yêu cầu của pg_rewind.
- Source server là cluster authoritative mới.
- Có đủ WAL từ điểm cần xác định divergence; có thể cần archive theo cấu hình phù hợp.
- Phiên bản và quyền truy cập đáp ứng yêu cầu của công cụ.

Đọc tài liệu đúng major version trước khi chạy. pg_rewind thay đổi target data directory; backup/giữ bản cũ và xác nhận đúng target path trước khi thực hiện.

## 32. Rejoin primary cũ thành standby

Sau khi rewind hoặc rebuild:

1. Đảm bảo old primary đã bị fence trong lúc thao tác.
2. Cấu hình standby.signal và connection tới primary mới theo version.
3. Cấu hình primary_conninfo và slot phù hợp nếu dùng.
4. Khởi động node dưới dạng standby.
5. Xác nhận pg_is_in_recovery() trả true.
6. Kiểm tra WAL receiver kết nối primary mới.
7. Theo dõi receive/replay LSN.
8. Chỉ đưa node vào candidate pool sau khi replication ổn định.

Không đưa node trở lại HA candidate pool chỉ vì process PostgreSQL đã chạy.

## 33. Timeline và history sau failover

Sau promotion, primary mới ghi trên timeline mới. Các standby khác cần biết timeline mới và lấy WAL đúng nhánh.

Kiểm tra timeline/control information bằng công cụ phù hợp:

~~~bash
pg_controldata /var/lib/postgresql/data
~~~

Timeline history files trong WAL archive giúp xác định quan hệ giữa timeline cũ và mới.

Nếu archive thiếu history file hoặc WAL segment, standby có thể không theo được nhánh mong muốn.

## 34. Fencing khi primary bị partition

Đây là tình huống nguy hiểm nhất:

- Primary A mất kết nối tới HA manager.
- A vẫn có network tới một số clients.
- HA manager có quorum và chọn B.
- B sắp được promote.

Trước khi B nhận writes, phải bảo đảm A không thể tiếp tục ghi. Các lựa chọn gồm hardware/cloud power fencing, storage/network isolation có kiểm chứng hoặc self-fencing dựa trên lease/watchdog đáng tin cậy.

Nếu không có cách xác nhận A đã bị vô hiệu hóa, hệ thống phải có policy không promote để bảo vệ single-writer safety. Đây là trade-off giữa availability và consistency.

## 35. Quorum control plane phải độc lập với PostgreSQL data plane

Một HA manager thường lưu leader state trong distributed store/consensus system.

Data plane là PostgreSQL nodes và replication connections. Control plane là nơi quyết định ai được leader.

Nếu control plane mất quorum:

- Không được để hai nhóm tự bầu leader độc lập.
- Node cũ cần tự fence khi không còn quyền leader nếu thiết kế dựa trên lease.
- Candidate mới không được promote chỉ vì không ping được primary.
- Phải tuân theo fail-safe policy.

Một distributed store có ba members nhưng tất cả cùng nằm trên một host hoặc một failure domain không tạo được fault tolerance thực sự.

## 36. Health check cần phân biệt trạng thái

Một health check có thể kiểm tra:

- TCP connection tới PostgreSQL.
- Query SELECT 1.
- pg_is_in_recovery().
- Replication lag.
- WAL receiver state.
- Disk capacity.
- Control-plane leader state.
- Fencing status.

SELECT 1 chỉ chứng minh database nhận query. Nó không chứng minh node được quyền nhận writes.

Một node có thể khỏe về process nhưng không phải leader. Health check cho write endpoint phải kiểm tra role và quyền leader theo thiết kế HA.

## 37. Kiểm soát writes như lớp phòng thủ bổ sung

Ngoài fencing, có thể giới hạn writes qua:

- Chỉ cấp application write credentials trên primary được điều phối.
- Tách read/write endpoints.
- Chặn client networks tới standby/old primary.
- Dùng proxy kiểm tra role.
- Giới hạn quyền quản trị và direct connections.
- Giám sát writes ngoài đường ứng dụng chuẩn.

Những biện pháp này là defense in depth. Nếu old primary vẫn có superuser/local access hoặc đường kết nối khác, ACL đơn thuần không thay thế fencing.

## 38. Synchronous standby và candidate selection

Nếu yêu cầu RPO thấp, phải bảo đảm standby được chọn promote có WAL chứa những commits mà primary đã xác nhận.

Với một synchronous standby cố định, điều phối candidate có thể đơn giản hơn nhưng vẫn cần theo dõi state.

Với nhiều synchronous standbys hoặc quorum ANY, manager cần biết node nào đã flush WAL. Không chỉ nhìn danh sách sync candidates hoặc sync_state hiện tại để kết luận mọi candidate có cùng WAL.

Có thể dùng một quy trình:

1. Lấy commit policy và danh sách synchronous standbys.
2. Theo dõi flush/replay LSN.
3. Khi failover, chọn node có WAL progress phù hợp.
4. Fence primary cũ.
5. Promote candidate.
6. Xác minh RPO thực tế.

## 39. Asynchronous failover và dữ liệu có thể mất

Nếu standby candidate thiếu một số transaction đã commit trên primary cũ, các transactions đó không có trong lịch sử primary mới.

Sau failover, không nên cố replay writes từ primary cũ bằng cách nối hai timeline một cách tùy tiện. Cần đánh giá dữ liệu còn lại trên old primary, xác định authoritative history và thực hiện business reconciliation có kiểm soát nếu cần.

Ghi nhận candidate replay LSN tại thời điểm promote, primary last known WAL/commit position, lag ước lượng, transactions có kết quả commit không rõ ở ứng dụng và các nghiệp vụ cần reconcile.

## 40. Không dùng hai primary để “dự phòng”

Một standby được giữ ở recovery mode là bản dự phòng. Một primary thứ hai nhận writes độc lập không phải HA standby.

Nếu muốn nhiều writers, cần giải pháp multi-writer được thiết kế rõ ràng, có conflict handling, key allocation, consistency semantics và application support. PostgreSQL physical streaming replication không cung cấp điều đó.

## 41. Patroni, repmgr và các HA managers

Các công cụ quản lý PostgreSQL HA có thể tự động hóa:

- Health checks.
- Leader election.
- Quorum/Distributed Configuration Store.
- Promotion.
- Fencing/watchdog integration.
- Reconfiguration of standbys.
- Endpoint/routing hooks.
- Rejoin/rewind workflows.

Ví dụ trong hệ sinh thái PostgreSQL có Patroni và repmgr. Chúng có mô hình, cấu hình và guarantees khác nhau; phải đọc tài liệu của version đang triển khai.

Không đánh đồng việc cài một HA manager với việc đã có fencing an toàn. Kiểm tra rõ DCS/consensus topology, lease/TTL semantics, watchdog/fencing configuration, behavior khi mất quorum, candidate selection policy, synchronous mode handling, routing update hooks và recovery sau split brain.

## 42. Kubernetes và container environments

Trong Kubernetes, Pod readiness hoặc Service endpoint update không phải fencing đầy đủ.

Một Pod cũ có thể tiếp tục chạy và nhận kết nối nếu còn đường mạng khác. Operator phải quản lý leader state, storage, pod lifecycle và failover.

Cần xác định:

- PersistentVolume có được attach độc quyền không?
- Node partition behavior.
- Pod termination có được xác nhận?
- Service có loại old primary khỏi endpoints?
- Old node có thể tiếp tục nhận writes qua địa chỉ khác?
- Operator có quorum/leader election và fencing phù hợp?

Không tự promote một Pod bằng lệnh SQL chỉ vì Kubernetes báo primary Pod unhealthy.

## 43. Backup không thay thế HA

HA giúp dịch vụ tiếp tục hoạt động khi node lỗi. Backup/PITR giúp phục hồi khi dữ liệu bị xóa/hỏng hoặc mọi replicas cùng chứa lỗi logic.

Replication cũng replicate logical mistakes như DROP TABLE hoặc UPDATE sai.

Một hệ thống production cần base backups, WAL archiving, restore tests, standbys, fencing/failover, monitoring và runbooks.

Không coi standby là backup độc lập.

## 44. RTO và thời gian failover

**RTO (Recovery Time Objective)** là thời gian mục tiêu để dịch vụ hoạt động lại.

~~~text
Detection
   + Quorum/election
   + Fencing
   + Promotion
   + Routing convergence
   + Client reconnect
   + Application recovery
~~~

Tối ưu thời gian promotion mà bỏ qua fencing sẽ giảm RTO trên giấy nhưng tạo rủi ro split brain. Đo thời gian từng bước trong lab và chọn timeout phù hợp với failure detection, network và application retry.

## 45. Monitoring cho single-writer safety

Các tín hiệu nên theo dõi:

| Metric/state | Ý nghĩa |
|---|---|
| Authoritative leader ID | Node đang được control plane cấp quyền leader |
| Quorum status | Control plane còn majority không |
| Fencing result | Old primary đã bị cô lập chưa |
| pg_is_in_recovery() | Role local của PostgreSQL node |
| Timeline ID | Nhánh WAL hiện tại |
| Standby flush/replay LSN | Replication progress |
| Logical/physical slot health | WAL retention state |
| Write endpoint target | Ứng dụng đang được route tới đâu |
| Connection count | Client còn kết nối node cũ không |
| Disk/WAL capacity | Khả năng tiếp tục nhận WAL |
| Failover events | Lịch sử promotion/demotion |

Cần cảnh báo khi có hơn một node báo role primary hoặc khi write endpoint không trùng authoritative leader.

## 46. Phát hiện hai primary

Có thể thu thập từ mọi node:

~~~sql
SELECT
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    pg_is_in_recovery() AS in_recovery;
~~~

Kết hợp timeline và HA manager state.

Nếu hai node đều trả in_recovery=false, đó là tín hiệu cần điều tra ngay. Nhưng một node false không chứng minh nó được quyền leader; cần đối chiếu authoritative leader và fencing state.

Automation không nên tự động drop/rewind node dựa trên một query duy nhất.

## 47. Incident response khi nghi split brain

1. Dừng hoặc hạn chế writes ở application layer theo incident policy.
2. Xác định authoritative leader từ control plane/quorum.
3. Fence node không được chọn.
4. Xác nhận chỉ một node còn nhận writes.
5. Ghi lại timeline, LSN, logs và thời điểm promotion.
6. Đánh giá hai nhánh có phát sinh writes độc lập không.
7. Chọn authoritative history theo policy.
8. Trích xuất và reconcile dữ liệu cần giữ từ nhánh còn lại.
9. Rewind/rebuild node cũ thành standby.
10. Chỉ mở lại writes khi single-writer state được xác nhận.

Không cố “merge WAL” của hai primary bằng thao tác thủ công thiếu kế hoạch. WAL timelines không phải công cụ merge nghiệp vụ.

## 48. Lab: promote standby thủ công

Thực hiện trong hai PostgreSQL lab instances, không dùng production.

1. Tạo primary và physical standby.
2. Xác nhận standby đang ở recovery.
3. Dừng writes trên primary lab.
4. Dừng/cách ly primary lab để không thể nhận writes.
5. Yêu cầu standby promote:

~~~sql
SELECT pg_promote(wait => true, wait_seconds => 60);
~~~

6. Kiểm tra:

~~~sql
SELECT pg_is_in_recovery();
~~~

7. Kiểm tra timeline bằng pg_controldata và server logs.
8. Thực hiện một write test trên primary mới.

Mục tiêu là quan sát promotion và role transition sau khi old primary đã được cô lập.

## 49. Lab: mô phỏng network partition và fencing

Trong môi trường VM/network lab cô lập:

1. Tạo primary A và standby B.
2. Tạo control-plane test có quorum.
3. Mô phỏng A mất kết nối tới control plane nhưng vẫn reachable từ một client test.
4. Không promote B khi A vẫn nhận writes.
5. Thực hiện fencing A bằng cơ chế VM/network test.
6. Xác minh A không còn nhận kết nối/write.
7. Promote B.
8. Chuyển client endpoint sang B.
9. Xác nhận chỉ B nhận writes.

Lab này minh họa tại sao network partition và process health không đủ để kết luận primary cũ đã chết.

## 50. Lab: asynchronous replication và RPO

Trong lab:

1. Cấu hình asynchronous streaming replication.
2. Tạo một workload ghi.
3. Quan sát primary/standby LSN.
4. Dừng standby hoặc làm chậm mạng.
5. Tạo thêm transaction trên primary.
6. Dừng/fence primary.
7. Promote standby.
8. So sánh dữ liệu đã commit trước đó với dữ liệu trên standby.

Kết quả cho thấy standby có thể thiếu các commits gần thời điểm failure.

## 51. Lab: synchronous replication

Trong lab riêng:

1. Cấu hình một synchronous standby.
2. Đặt synchronous_standby_names phù hợp.
3. Chọn synchronous_commit=on.
4. Ghi transaction và quan sát commit behavior.
5. Theo dõi pg_stat_replication flush LSN.
6. Dừng standby và quan sát ảnh hưởng lên writes theo policy.
7. Thử remote_apply và so sánh latency.

Không dùng lab để suy ra mọi synchronous topology có RPO=0. Candidate selection và fencing vẫn phải được kiểm tra riêng.

## 52. Lab: switchover có kế hoạch

Trong môi trường test:

1. Chọn candidate.
2. Chặn application writes tạm thời.
3. Chờ candidate replay tới LSN boundary.
4. Stop old primary cleanly hoặc fence theo runbook.
5. Promote candidate.
6. Verify primary state và timeline.
7. Chuyển endpoint.
8. Rewind/rebuild old primary thành standby.
9. Kiểm tra replication ổn định trước khi kết thúc lab.

Ghi lại RTO và thời gian client reconnect.

## 53. Những sai lầm thường gặp

### 53.1. Chỉ cần promote standby là HA hoàn tất

Sai. Còn cần fencing, leader election, routing và rejoin.

### 53.2. Primary không ping được nghĩa là đã chết

Sai. Nó có thể bị network partition nhưng vẫn nhận writes từ client khác.

### 53.3. Đổi DNS là đủ ngăn split brain

Sai. Client có thể dùng IP trực tiếp hoặc connection cũ; old primary vẫn chạy.

### 53.4. pg_is_in_recovery=false chứng minh node là primary duy nhất

Sai. Nó chỉ mô tả trạng thái local; hai node có thể cùng false sau split brain.

### 53.5. Synchronous replication tự động chọn candidate an toàn

Sai. Cần chọn candidate có WAL phù hợp và phối hợp với fencing/manager.

### 53.6. Mọi synchronous standby đều có mọi commit

Sai với quorum ANY và nhiều cấu hình synchronous khác nhau; phải hiểu acknowledgments của từng transaction.

### 53.7. Promote primary mới rồi để primary cũ tự kết nối lại

Sai. Old primary có thể divergent và phải rewind/rebuild thành standby.

### 53.8. pg_rewind luôn chạy được

Sai. Nó có prerequisites về checksums/wal_log_hints, full_page_writes, shutdown state và WAL availability.

### 53.9. Hai timeline có thể merge tự động

Sai. Nếu cả hai primary nhận writes, cần chọn authoritative history và reconcile dữ liệu nghiệp vụ.

### 53.10. Standby là backup

Sai. Standby cũng nhận các thay đổi sai được replicate; cần backup và PITR riêng.

## 54. Checklist thiết kế HA single-writer

**Topology và replication**

1. Có ít nhất một standby phù hợp?
2. WAL level/slots/senders đủ?
3. Replication mode và RPO đã xác định?
4. Standby candidate có thể catch up?
5. Archive/WAL backup có đầy đủ?

**Control plane**

6. Leader election dùng quorum/consensus?
7. Control plane có failure domains độc lập?
8. Lease/TTL semantics rõ?
9. Node mất quorum có self-fence?
10. Có watchdog/STONITH hoặc fencing mechanism?

**Promotion**

11. Candidate selection dựa trên WAL progress?
12. Old primary được fence trước khi mở writes?
13. Chỉ một candidate được promote?
14. Promotion result được xác minh?
15. Timeline mới được nhận diện?

**Routing và ứng dụng**

16. Write endpoint trỏ đúng leader?
17. Direct connections tới old primary bị chặn?
18. Connection pools có reconnect?
19. Retry có idempotency?
20. Health checks phân biệt role và leader authorization?

**Rejoin và recovery**

21. Old primary được giữ cách ly?
22. Có pg_rewind hoặc rebuild procedure?
23. Có đủ WAL/history files?
24. Slot và standby config được tạo lại?
25. Restore/failover/split-brain drills đã thực hiện?

## 55. Checklist vận hành failover

Khi primary gặp sự cố:

- Ghi thời điểm và triệu chứng.
- Kiểm tra quorum/control plane.
- Phân biệt crash với network partition.
- Xác định fencing method và xác nhận kết quả.
- Chọn standby có WAL progress phù hợp.
- Promote đúng một candidate.
- Kiểm tra pg_is_in_recovery() và timeline.
- Chuyển write endpoint.
- Kiểm tra ứng dụng reconnect và commit outcomes.
- Kiểm tra những standby còn lại.
- Rejoin old primary bằng rewind/rebuild.
- Ghi RPO/RTO thực tế và nguyên nhân sự cố.

Nếu fencing không thể xác nhận, giữ writes đóng theo policy cho đến khi single-writer safety được bảo đảm.

## 56. Các câu lệnh và views quan trọng

~~~sql
-- Role local của node.
SELECT pg_is_in_recovery();

-- Promote standby khi runbook đã xác nhận fencing.
SELECT pg_promote(wait => true, wait_seconds => 60);

-- Primary: progress của standby.
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;

-- Standby: receive/replay progress.
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();

-- Standby: WAL receiver.
SELECT * FROM pg_stat_wal_receiver;

-- Replication configuration.
SHOW synchronous_standby_names;
SHOW synchronous_commit;
SHOW wal_level;
SHOW max_wal_senders;
SHOW max_replication_slots;
~~~

Các lệnh này quan sát hoặc điều khiển PostgreSQL local. Chúng không thay thế quorum, fencing, endpoint management và incident policy.

## 57. Câu hỏi thường gặp

### Promotion có tự tắt primary cũ không?

Không. Promotion tác động lên standby được promote. Primary cũ phải được fence/dừng riêng.

### Vì sao phải fence trước khi promote?

Để ngăn primary cũ tiếp tục nhận writes khi primary mới bắt đầu nhận writes. Đây là điều kiện quan trọng để tránh split brain.

### pg_promote có kiểm tra quorum không?

Không. Nó yêu cầu PostgreSQL local kết thúc recovery. Quorum và candidate selection thuộc HA manager/control plane.

### pg_is_in_recovery=false có nghĩa node là leader duy nhất?

Không. Nó chỉ cho biết node local không ở recovery mode.

### Synchronous replication có bảo đảm zero data loss không?

Nó có thể bảo đảm commit acknowledgment trên synchronous standby theo policy, nhưng failover an toàn còn phụ thuộc candidate selection, quorum mode, fencing và WAL state.

### remote_apply khác on thế nào?

on chờ synchronous standby flush WAL; remote_apply chờ transaction được replay/apply trên synchronous standby được chọn.

### Quorum ANY có nghĩa mọi standby đều có commit?

Không. Commit được xác nhận bởi số standby bất kỳ theo quorum requirement. Candidate cần được chọn dựa trên WAL thực tế đã nhận/flush.

### Đổi load balancer có đủ single-writer guarantee không?

Không. Nó chỉ thay routing; old primary có thể còn nhận kết nối trực tiếp hoặc connection cũ.

### Có thể dùng pg_rewind cho mọi old primary không?

Không. Cần đáp ứng prerequisites và WAL availability. Nếu không, rebuild từ base backup.

### Có thể merge dữ liệu của hai primary sau split brain không?

Không có thao tác merge WAL tổng quát. Phải chọn authoritative history và reconcile nghiệp vụ.

### Standby async có thể mất transaction không?

Có. Nếu primary xác nhận commit trước khi standby nhận/flush WAL và primary mất, candidate có thể thiếu transaction đó.

### Khi nào nên dùng switchover?

Khi có thể kiểm soát writes, chờ standby catch up, dừng old primary và chuyển vai trò theo kế hoạch.

### Khi control plane mất quorum có nên promote không?

Không tự động. Hệ thống phải ngăn nhóm thiểu số tự nhận leader. Cần tuân thủ lease/fencing policy để bảo toàn single-writer safety.

### Backup có thay thế standby không?

Không. Standby phục vụ HA; backup/WAL archive phục vụ khôi phục dữ liệu và PITR.

## 58. Tổng kết

Promotion là bước chuyển một standby thành primary mới. Để chỉ có một máy chủ nhận writes, cần một quy trình có thẩm quyền:

1. Phát hiện và phân loại primary failure.
2. Dùng quorum/control plane để chọn đúng một candidate.
3. Fence primary cũ và xác nhận nó không thể nhận writes.
4. Đánh giá WAL progress/RPO của candidate.
5. Promote candidate.
6. Verify role và timeline.
7. Chuyển write endpoint.
8. Xác nhận ứng dụng reconnect và chỉ ghi vào primary mới.
9. Rewind/rebuild old primary thành standby.
10. Theo dõi replication và kiểm tra toàn bộ HA topology.

Những nguyên tắc cần nhớ:

- pg_promote() và pg_ctl promote chỉ yêu cầu promotion trên một node.
- PostgreSQL streaming replication không tự cung cấp leader election/fencing đầy đủ.
- Split brain xảy ra khi hai primary cùng nhận writes.
- Fencing/STONITH ngăn primary cũ tiếp tục gây thay đổi.
- Quorum giúp control plane thống nhất quyết định; quorum đơn lẻ không fence data plane.
- Lease chỉ an toàn nếu node mất lease tự fence hoặc bị fence từ bên ngoài.
- Đổi DNS/load balancer không thay thế fencing.
- pg_is_in_recovery() chỉ mô tả role local, không chứng minh leader duy nhất.
- Synchronous replication giảm RPO theo acknowledgment policy nhưng không tự chọn candidate/fence old primary.
- ANY N quorum không có nghĩa mọi standby chứa mọi commit.
- Asynchronous failover có thể mất transaction đã commit trên primary cũ.
- Promotion tạo timeline mới; không merge tự động hai lịch sử WAL.
- Primary cũ phải được giữ cách ly và rejoin bằng pg_rewind hoặc rebuild.
- Backup và WAL archiving vẫn cần thiết bên cạnh standby.
- Failover drills phải kiểm tra network partition, fencing, routing và client reconnect.

Sơ đồ single-writer:

~~~text
              Primary failure suspected
                         |
                         v
               Control plane / quorum
                         |
                         v
              Chọn đúng một candidate
                         |
                         v
               Fence old primary
                         |
                 Fencing confirmed?
                    /       \
                  No         Yes
                  |            |
                  v            v
            Keep writes     Promote candidate
            closed / wait         |
                                  v
                         Verify new timeline
                                  |
                                  v
                         Update write endpoint
                                  |
                                  v
                         Client reconnect
                                  |
                                  v
                         Single writer active
                                  |
                                  v
                         Rejoin old primary
                         as a standby
~~~

**Kết luận:** Promotion giúp PostgreSQL tiếp tục phục vụ khi primary thay đổi, nhưng single-writer safety đến từ toàn bộ quy trình điều phối. Hệ thống phải **chọn leader bằng quorum, fence primary cũ, promote đúng một standby, cập nhật routing sau khi xác minh và rejoin node cũ như standby**. Nếu không thể chứng minh primary cũ đã mất quyền ghi, không được mở writes trên primary mới.
