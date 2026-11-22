# Phục hồi dữ liệu, xử lý phân kỳ và ngăn split-brain

Một hệ thống phân tán có thể tiếp tục hoạt động khi một node, availability zone hoặc region gặp sự cố, nhưng khả năng phục hồi không chỉ là khởi động một máy chủ dự phòng. Sau failover, dữ liệu có thể thiếu một phần giao dịch, hai node có thể đã nhận các thao tác ghi khác nhau, hoặc node cũ có thể quay lại và tiếp tục ghi với trạng thái lỗi thời. Nếu không kiểm soát các tình huống này, hệ thống có thể tạo dữ liệu phân kỳ, ghi đè cập nhật hợp lệ hoặc xác nhận hai kết quả mâu thuẫn.

**Phục hồi dữ liệu (data recovery)** khôi phục dữ liệu và dịch vụ về một trạng thái được chấp nhận sau sự cố. **Xử lý phân kỳ (divergence handling)** xác định và giải quyết khác biệt giữa các bản sao hoặc nhánh dữ liệu đã tiến triển độc lập. **Ngăn split-brain** bảo đảm chỉ một writer/leader hợp lệ được quyền tạo trạng thái mới trong cùng một phạm vi nhất quán. Ba phần này phải được thiết kế cùng nhau: backup và log phục hồi cung cấp đường khôi phục; replication và reconciliation giúp phát hiện/giải quyết sai khác; quorum, lease, epoch và fencing ngăn các writer xung đột tiếp tục hoạt động.

Bài học thuộc chương **Phục hồi thảm họa** của lộ trình **Cloud Architecture**. Nội dung tập trung vào cách thiết kế khôi phục dữ liệu, kiểm soát phân kỳ và bảo vệ tính đúng đắn khi failover/failback. Các quyết định cần gắn với mục tiêu nghiệp vụ, RPO/RTO, durability, consistency, bảo mật và khả năng vận hành thực tế.

Sau bài học, bạn có thể:

- Phân biệt backup, replication, snapshot, archive và point-in-time recovery.
- Chọn chiến lược recovery theo RPO, RTO, retention và mức độ quan trọng dữ liệu.
- Phục hồi theo backup kết hợp transaction log/WAL/binlog hoặc change stream.
- Phát hiện dữ liệu thiếu, trùng, sai thứ tự và phân kỳ giữa các bản sao.
- Thiết kế reconciliation, replay, conflict resolution và quy trình phục hồi có kiểm soát.
- Giải thích split-brain và nguyên nhân từ network partition, lỗi phát hiện leader hoặc failover đồng thời.
- Áp dụng quorum, lease, fencing token, epoch và writer isolation theo semantics hệ thống.
- Thiết kế failover, failback, rejoin node cũ và kiểm thử các kịch bản lỗi.

## 1. Recovery là một mục tiêu nghiệp vụ

Phục hồi thảm họa (disaster recovery, DR) không chỉ là khôi phục hạ tầng. Một hệ thống được coi là phục hồi khi các chức năng quan trọng hoạt động lại và dữ liệu đáp ứng mức mất mát, tính nhất quán và độ tin cậy đã cam kết.

Ví dụ nền tảng đặt thuê thiết bị có thể có các yêu cầu khác nhau:

- Payment ledger cần giữ mọi giao dịch đã xác nhận theo durability policy.
- Booking service có thể chấp nhận mất tối đa vài giây dữ liệu trong một kịch bản region failure nếu hợp đồng nghiệp vụ cho phép.
- Notification có thể chậm hơn nhưng không được mất message đã xác nhận durable.
- Analytics có thể được rebuild từ raw event và chấp nhận RTO dài hơn.
- Search index có thể tái tạo từ database hoặc event log, không cần backup cùng mức như nguồn dữ liệu chính.

Một chiến lược backup giống nhau cho mọi dataset có thể gây lãng phí ở nơi dữ liệu dễ tái tạo và thiếu bảo vệ ở nơi dữ liệu không thể thay thế.

## 2. RPO và RTO

Hai chỉ tiêu nền tảng để xác định chiến lược DR là **Recovery Point Objective (RPO)** và **Recovery Time Objective (RTO)**.

- **RPO:** mức dữ liệu tối đa có thể mất, thường biểu diễn bằng khoảng thời gian từ thời điểm sự cố tới điểm dữ liệu cuối cùng có thể phục hồi.
- **RTO:** thời gian mục tiêu để khôi phục dịch vụ hoặc chức năng nghiệp vụ tới mức hoạt động chấp nhận được.

Ví dụ nếu RPO là 5 phút, tổ chức chấp nhận khôi phục dữ liệu tới một điểm không cũ hơn quá 5 phút trước sự cố theo định nghĩa đã thống nhất. Nếu RTO là 30 phút, chức năng cần được phục hồi trong khoảng 30 phút. RPO/RTO không tự nói rằng mọi giao dịch trong 5 phút đó chắc chắn mất; chúng là mục tiêu thiết kế và đo kiểm, không phải dự báo chính xác của từng incident.

### 2.1. Timeline khái niệm

~~~mermaid
flowchart LR
    A["Last recoverable point"] --> B["Data changes"]
    B --> C["Failure time"]
    A -. "RPO window" .-> C
    C --> D["Detection / decision"]
    D --> E["Restore / promote / replay"]
    E --> F["Service recovered"]
    C -. "RTO window" .-> F
~~~

### 2.2. Tách RTO theo giai đoạn

RTO tổng không chỉ là thời gian restore database. Có thể phân rã:

| Giai đoạn | Công việc |
| --- | --- |
| Detection | Phát hiện và xác nhận sự cố |
| Decision | Chọn recovery site/backup/replica và phê duyệt chuyển đổi |
| Provision/restore | Tạo tài nguyên hoặc phục hồi database |
| Replay/reconciliation | Áp log, kiểm tra dữ liệu, xử lý sai khác |
| Routing | Chuyển endpoint, DNS, traffic hoặc tenant routing |
| Validation | Smoke test, kiểm tra invariant và quyền |
| Business recovery | Cho phép lại giao dịch và xử lý backlog |

Nếu restore mất 15 phút nhưng kiểm tra consistency và đổi traffic cần thêm 25 phút, RTO thực tế gần 40 phút. Phải đo từ góc nhìn người dùng và hành trình nghiệp vụ.

### 2.3. Tier recovery

| Tier dữ liệu/dịch vụ | RPO/RTO giả định | Kiểu bảo vệ có thể xem xét |
| --- | --- | --- |
| Ledger/payment | RPO gần 0 trong phạm vi cam kết; RTO ngắn | Sync/quorum replication, log durability, backup độc lập |
| Booking core | RPO thấp, RTO vài phút | Multi-zone HA, cross-region replica, PITR |
| Notification | Có thể trì hoãn, ưu tiên không mất message accepted | Durable queue, replicated storage, replay |
| Analytics curated | Có thể rebuild, RTO dài hơn | Raw archive, pipeline replay, catalog backup |
| Search/cache | Có thể tái tạo | Snapshot định kỳ hoặc rebuild từ source |

Các con số cần được xác định bằng phân tích tác động nghiệp vụ, hợp đồng và khả năng kỹ thuật. Không nên hứa RPO bằng 0 chỉ vì có synchronous replication: semantics acknowledgement, quorum, storage durability và lỗi đồng thời phải được kiểm chứng.

## 3. Backup, snapshot, replication và archive

Các cơ chế này bổ sung cho nhau nhưng không thay thế nhau.

| Cơ chế | Mục tiêu | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| Backup | Khôi phục sau xóa nhầm, corruption hoặc outage | Có thể phục hồi về điểm trước sự cố | Có độ trễ, cần restore và kiểm tra |
| Snapshot | Chụp trạng thái storage/database tại một thời điểm | Tạo điểm phục hồi nhanh hơn hoặc clone môi trường | Phụ thuộc consistency và retention; không tự bảo vệ mọi lỗi logic |
| Replication | Duy trì bản sao cập nhật ở node/site khác | Failover nhanh, có thể phục vụ read | Có thể replicate delete/corruption; async có lag |
| Transaction log/WAL archive | Lưu thay đổi sau full/incremental backup | Point-in-time recovery và replay | Cần chuỗi log liên tục, đúng thứ tự và retention |
| Archive | Lưu dữ liệu lịch sử/lâu dài | Chi phí lưu trữ và compliance | Restore/rehydrate chậm hơn, truy xuất phức tạp |
| Export/versioned object | Giữ bản dữ liệu theo version | Khôi phục file/dataset và chống overwrite | Không thay thế transaction-consistent backup nếu export không đồng bộ |

### 3.1. Vì sao replica không phải backup?

Nếu một operator xóa nhầm bảng, lệnh xóa thường được replication sang các replica. Nếu dữ liệu bị hỏng do bug ứng dụng, replica có thể nhận cùng dữ liệu hỏng. Replication giúp sẵn sàng nhưng không giữ lại trạng thái sạch trước sự cố.

Backup nên có bản sao nằm trong failure domain và quyền quản trị khác với hệ thống production; có retention/immutability phù hợp và được kiểm tra restore định kỳ.

### 3.2. Snapshot consistency

Snapshot của volume hoặc database phải có semantics rõ: crash-consistent hay application-consistent? Một snapshot chỉ bảo đảm các block được chụp gần cùng thời điểm chưa chắc tương đương một database transaction-consistent backup. Cần dùng cơ chế quiesce/checkpoint hoặc backup API của database khi cần đảm bảo transaction.

## 4. Full backup, incremental backup và log backup

Một chiến lược database recovery thường kết hợp:

- **Full backup:** bản sao đầy đủ tại một thời điểm.
- **Incremental/differential backup:** thay đổi kể từ backup trước hoặc từ full backup theo semantics công cụ.
- **Transaction log backup/archive:** log liên tục để phục hồi tới một thời điểm cụ thể.

Ví dụ quy trình:

~~~text
Sunday 00:00    Full backup B0
Monday 00:00    Incremental I1
Monday 12:00    Log segments L001...L120
Monday 14:20    Accidental data deletion
Recovery:
    Restore B0
    Apply I1
    Replay transaction logs up to 14:19:59
    Validate recovered database
    Open application traffic
~~~

Tên gọi và cách ghép incremental/differential khác nhau theo database/backup engine. Runbook phải dùng đúng semantics công cụ, không tự giả định mọi log có thể replay độc lập.

### 4.1. Point-in-time recovery (PITR)

PITR khôi phục database về một thời điểm cụ thể bằng cách restore backup nền rồi áp dụng log tới target time hoặc log position. Nó hữu ích khi cần phục hồi trước một thao tác sai hoặc corruption logic đã lan vào database.

PITR phụ thuộc:

- Một full/base backup có thể đọc.
- Toàn bộ chuỗi log cần thiết không bị thiếu.
- Timestamp/position được xác định chính xác.
- Backup, log và encryption key còn truy cập được.
- Có nơi restore đủ dung lượng và version tương thích.
- Quy trình validate và đổi endpoint đã được diễn tập.

Nếu transaction commit ở đúng thời điểm target không rõ ràng, cần xác định inclusive/exclusive semantics và dùng log position hoặc business record để xác nhận kết quả.

## 5. Backup phải được bảo vệ như production

Kẻ tấn công có quyền xóa database có thể tìm cách xóa backup, snapshot, key và log. Backup cùng account, cùng credential và cùng control plane có thể bị phá cùng production.

Các biện pháp:

- Backup account/project hoặc vault tách biệt khi phù hợp.
- Immutable/WORM retention hoặc object lock theo policy.
- Tách quyền tạo, đọc, xóa và thay đổi retention.
- MFA/approval cho thao tác phá hủy.
- Mã hóa backup và bảo vệ key độc lập.
- Theo dõi backup job, log gap, retention và delete event.
- Kiểm tra backup integrity và restore trong môi trường cách ly.
- Giữ bản sao ở region/failure domain khác theo RPO/RTO.
- Bảo vệ metadata, catalog, configuration và recovery credential.

Immutability có thể gây khó khăn cho việc xóa dữ liệu theo chính sách hoặc yêu cầu pháp lý. Retention lock, legal hold và privacy erasure cần được thiết kế cùng nhau và xác nhận với owner có thẩm quyền.

## 6. Phục hồi dữ liệu không đồng nghĩa phục hồi toàn bộ hệ thống

Một database backup không đủ để khôi phục ứng dụng. Hệ thống còn phụ thuộc vào:

- Application artifact và version.
- Infrastructure as Code và network configuration.
- DNS, certificates và identity provider.
- Secret, key và quyền truy cập.
- Schema migration và compatibility.
- Queue, event offset và workflow state.
- Object storage, file attachments và search index.
- Tenant directory, feature/config data.
- Monitoring, alert và runbook.

Cần lập recovery dependency map và xác định thứ tự khôi phục. Ví dụ khởi động application trước khi secret/KMS/identity hoạt động có thể khiến instance không sẵn sàng; restore database trước khi chọn đúng schema version có thể làm application không tương thích.

## 7. Recovery sequence và dependency order

Một quy trình khôi phục điển hình có thể theo các bước:

1. Kích hoạt incident và xác định failure scope.
2. Bảo vệ bằng chứng/log và ngăn ghi tiếp vào hệ thống hỏng nếu cần.
3. Chọn recovery point và target environment.
4. Khôi phục control dependency: identity, key, network, DNS và secret theo thứ tự.
5. Restore database/storage hoặc promote replica theo chiến lược.
6. Replay transaction log/event và xác minh consistency.
7. Khôi phục queue/workflow checkpoint và xử lý message tồn đọng.
8. Chạy data quality/invariant/reconciliation checks.
9. Mở traffic theo cohort hoặc read-only trước nếu phù hợp.
10. Theo dõi lỗi, latency, duplicate và backlog.
11. Lưu quyết định recovery, dữ liệu có thể mất và các thao tác bù trừ.

Không mở ghi ngay khi database vừa online. Phải xác nhận node là writer hợp lệ, recovery point được chấp nhận, schema/version tương thích và không còn writer cũ hoạt động.

## 8. Data divergence là gì?

**Data divergence** xảy ra khi hai bản sao hoặc hai nhánh dữ liệu không còn phản ánh cùng một lịch sử hợp lệ. Nó có thể xuất hiện khi:

- Primary và replica tiến triển độc lập sau network partition.
- Hai region cùng nhận write trong active-active nhưng replication không đồng bộ.
- Failover promote replica chưa nhận đủ log.
- Một node cũ quay lại và phát lại dữ liệu từ trạng thái lỗi thời.
- Replay/retry tạo duplicate hoặc áp sự kiện sai thứ tự.
- Replication conflict được giải quyết bằng last-write-wins không phù hợp với nghiệp vụ.

Divergence không đơn giản là replica lag. Lag là chậm theo kịp; divergence là nội dung hoặc thứ tự đã khác nhau. Một replica lag có thể bắt kịp bằng cách tiếp tục replay; hai nhánh đã nhận write độc lập có thể cần conflict resolution hoặc phục hồi từ nguồn có thẩm quyền.

### 8.1. Ví dụ phân kỳ

Giả sử booking có trạng thái CONFIRMED ở primary A và replica B. Network partition khiến B được promote nhưng A vẫn nhận write. A ghi BookingCancelled; B ghi BookingRescheduled. Khi kết nối phục hồi, hai nhánh không thể chỉ nối log theo timestamp vì cả hai transition đều dựa trên cùng state cũ và có ý nghĩa xung đột.

~~~mermaid
sequenceDiagram
    participant A as Region A
    participant B as Region B

    Note over A,B: Cả hai có Booking v10 = CONFIRMED
    A->>A: Append v11 BookingCancelled
    B->>B: Append v11 BookingRescheduled
    Note over A,B: Network partition; hai nhánh diverge
    A--xB: Replication unavailable
    Note over A,B: Link recovers; conflict must be resolved
~~~

Timestamp lớn hơn không đồng nghĩa event đúng hơn. Cần quy tắc nghiệp vụ hoặc một cơ chế single-writer/quorum ngăn xung đột từ trước.

## 9. Phát hiện divergence

Không thể phát hiện mọi sai khác chỉ bằng cách kiểm tra node đang online. Cần nhiều lớp kiểm tra:

- **Replication position:** so sánh log sequence/offset theo semantics engine.
- **Checksums/hash:** so sánh partition/table/page hoặc dữ liệu theo key range.
- **Row counts/aggregates:** tổng record, tổng tiền và số trạng thái theo cùng snapshot point.
- **Business invariants:** booking không vừa cancelled vừa confirmed; ledger debit/credit cân bằng.
- **Event sequence:** phát hiện gap, duplicate, sequence conflict và event đến sai thứ tự.
- **Reconciliation:** so sánh nguồn có thẩm quyền với projection/replica.
- **Version/fencing metadata:** kiểm tra leader epoch, writer identity và generation.
- **Audit timeline:** xác định node nào nhận write trong thời điểm phân vùng.

Checksum giống nhau không chứng minh mọi quy tắc nghiệp vụ đúng nếu cả hai bản sao cùng chứa lỗi logic. Row count giống nhau cũng không chứng minh cùng nội dung. Kết hợp kỹ thuật và business reconciliation.

### 9.1. Reconciliation theo domain

Ví dụ với booking:

| Kiểm tra | Mục tiêu |
| --- | --- |
| Booking ID uniqueness | Không tạo hai bản ghi cho cùng business identity |
| State transition | Không có transition trái luật |
| Payment reference | Không gắn một giao dịch thanh toán với hai booking |
| Reservation ownership | Một tài sản không bị xác nhận cho hai booking trùng thời gian |
| Amount/currency | Tổng tiền và currency tương ứng với event được xác nhận |
| Event sequence | Không thiếu version hoặc apply trùng |
| Tenant ownership | Bản ghi thuộc đúng tenant sau recovery |

Với ledger, cần kiểm tra cân bằng debit/credit theo transaction/currency; không chỉ so tổng số row.

## 10. Xử lý phân kỳ: chọn nguồn có thẩm quyền trước

Trước khi hợp nhất nhánh dữ liệu, phải xác định **source of truth** cho từng domain/aggregate và khoảng thời gian bị ảnh hưởng.

Một số lựa chọn:

1. **Single-writer authority:** chỉ một node/region có quyền ghi; nhánh không có quyền bị loại hoặc đưa vào quarantine.
2. **Quorum-committed history:** chỉ công nhận các thao tác có commit certificate/quorum theo consensus protocol.
3. **Business reconciliation:** domain owner quyết định event nào hợp lệ dựa trên bằng chứng và invariant.
4. **Replay từ authoritative log:** dựng lại projection/node từ lịch sử đã xác nhận.
5. **Manual adjudication:** các conflict không thể tự động giải quyết được đưa vào hàng đợi xử lý có audit.

Không nên merge dữ liệu hai database bằng cách copy row mới hơn theo timestamp. Cần xem transaction, version, actor, authority và hậu quả nghiệp vụ.

### 10.1. Conflict resolution strategies

| Chiến lược | Cách hoạt động | Phù hợp | Rủi ro |
| --- | --- | --- | --- |
| Last-write-wins | Chọn update có timestamp/version lớn hơn | Một số thuộc tính ít quan trọng, có clock/ordering đáng tin | Mất update hợp lệ, clock skew |
| Version-based rejection | Chỉ chấp nhận write trên expected version | Aggregate single-writer/optimistic concurrency | Caller phải retry hoặc xử lý conflict |
| Field-level merge | Hợp nhất các field không xung đột | Dữ liệu cộng tác có semantics từng field | Có thể tạo tổ hợp state không hợp lệ |
| CRDT/commutative operation | Dùng phép toán có thể hợp nhất và hội tụ | Counter, set hoặc cấu trúc phù hợp | Không phù hợp mọi invariant nghiệp vụ |
| Domain-specific resolution | Quy tắc theo ngữ nghĩa business | Booking, payment, inventory, ledger | Cần domain logic và có thể manual |
| Quarantine/manual review | Không tự merge; cách ly conflict | Tác động tài chính/pháp lý cao | Phục hồi chậm, cần đội xử lý |

### 10.2. Ví dụ field merge không an toàn

Một profile có hai cập nhật độc lập: người dùng đổi display name và nhân viên sửa contact status. Có thể merge từng field nếu semantics cho phép. Nhưng một booking có hai transition CONFIRMED→CANCELLED và CONFIRMED→RESCHEDULED không thể ghép field một cách cơ học; domain phải chọn một outcome hoặc tạo quy trình bù trừ.

## 11. Replay và rebuild từ nguồn có thẩm quyền

Nếu một replica hoặc projection đã phân kỳ, có thể xóa/rebuild từ nguồn dữ liệu có thẩm quyền khi lịch sử đầy đủ.

Quy trình khái niệm:

1. Fence node lỗi để nó không nhận write.
2. Xác định authoritative stream/log và recovery point.
3. Backup trạng thái phân kỳ để điều tra; không xóa bằng chứng.
4. Provision node sạch hoặc tạo projection target mới.
5. Restore snapshot/base backup phù hợp.
6. Apply log/event tới checkpoint được công nhận.
7. Rebuild index/materialized view/projection.
8. Reconcile business invariant và counts/checksum.
9. Chuyển traffic khi validation đạt.
10. Lưu node cũ ở read-only/quarantine trước khi retire theo policy.

Replay cần idempotent và không lặp side effect. Rebuild read model không được gửi lại email, gọi payment hoặc tạo giao dịch ngoài. Cần tách state projector khỏi integration handler.

## 12. Split-brain là gì?

**Split-brain** là trạng thái hai hoặc nhiều node cùng tin rằng mình có quyền làm leader/writer cho cùng một dữ liệu hoặc phạm vi nhất quán. Điều này thường xuất hiện khi network partition làm các node không thể xác nhận trạng thái leader, trong khi cơ chế failover hoặc health check cho phép nhiều phía tiếp tục nhận write.

Hậu quả:

- Hai lịch sử giao dịch cùng phát triển.
- Cùng một tài nguyên được cấp phát hai lần.
- Update bị ghi đè hoặc không thể merge.
- Sequence/version bị trùng.
- Replica khi tái kết nối không biết nhánh nào có authority.
- Dữ liệu tài chính hoặc trạng thái booking trở nên không thể giải thích.

Split-brain khác với multi-primary được thiết kế chủ đích. Multi-primary có cơ chế replication/conflict management rõ ràng; split-brain là tình trạng quyền ghi không được phối hợp an toàn.

### 12.1. Network partition và uncertainty

Khi A không liên lạc được B, A không thể biết chắc B đã hỏng hay chỉ bị cô lập mạng. Nếu cả hai đều tự promote dựa trên timeout riêng mà không có quorum/lease/fencing, chúng có thể cùng nhận write.

Health check chứng minh node phản hồi; nó không tự chứng minh node có quyền leader. Quyết định leadership phải dựa vào protocol và authority, không chỉ dựa vào việc node có ping được hay không.

## 13. Quorum và consensus

**Quorum** là số lượng thành viên cần đồng ý để thực hiện một quyết định nhất định, ví dụ bầu leader hoặc commit entry. Trong một cụm consensus có 2f+1 voting members, quorum đa số thường là f+1; có thể chịu f member lỗi trong điều kiện protocol/network assumptions phù hợp.

Ví dụ cụm 3 voter cần 2 phiếu để bầu leader/commit theo protocol. Khi một node bị cô lập, nhóm có 2 voter vẫn có thể đạt quorum; node còn lại không đủ phiếu nên phải từ chối write. Đây là cách ngăn hai phía cùng commit.

~~~mermaid
flowchart TB
    subgraph QUORUM["3 voting members"]
        A["Node A"]
        B["Node B"]
        C["Node C"]
    end
    A --- B
    B --- C
    C --- A
    A --> L["Leader được quorum bầu"]
    B --> L
~~~

Sơ đồ chỉ minh họa quorum majority. Hệ thống thực tế có thể dùng witness, weighted voting, joint consensus hoặc topology khác. Không được tùy tiện thay số node hoặc cấu hình quorum nếu chưa hiểu protocol; một witness có thể bỏ phiếu nhưng không giữ dữ liệu đầy đủ.

### 13.1. Vì sao hai node thường không đủ?

Với hai voter và yêu cầu majority, quorum là 2. Khi một node mất kết nối, không phía nào có đủ phiếu để tiếp tục commit an toàn. Một số kiến trúc dùng witness/third voter để phân giải tie. Đây là đánh đổi giữa availability và khả năng tránh hai leader.

### 13.2. Quorum không tự giải quyết mọi lỗi

Quorum consensus bảo vệ quyết định trong phạm vi cluster/protocol được định nghĩa. Nó không tự bảo vệ các hệ thống ngoài cluster, ví dụ một payment provider hoặc một database phụ không tham gia quorum. Integration và side effect vẫn cần idempotency, fencing hoặc authority check thích hợp.

## 14. Lease, epoch và fencing token

Các cơ chế sau thường phối hợp để bảo vệ quyền ghi.

### 14.1. Lease

Lease là quyền sở hữu có thời hạn. Leader được quyền ghi trong thời gian lease còn hiệu lực theo clock/coordination assumptions của hệ thống. Khi lease hết hạn, leader phải dừng thao tác yêu cầu quyền đó nếu không gia hạn thành công.

Lease cần xử lý clock drift, pause dài, network delay và quá trình revoke/renew. Một process có thể bị pause lâu rồi tỉnh lại với suy nghĩ lease vẫn hợp lệ; vì vậy lease đơn lẻ không phải luôn đủ.

### 14.2. Epoch/generation

Mỗi lần bầu leader hoặc chuyển writer, hệ thống tăng epoch/generation. Request mang epoch cũ bị từ chối khi resource/server đã biết epoch mới hơn.

Ví dụ:

~~~text
Epoch 41: Region A is writer
Failover / new leader election
Epoch 42: Region B is writer

Any write carrying epoch 41:
    reject as stale leader
~~~

Epoch cần được cấp bởi authority có tính nhất quán, tăng đơn điệu và được lưu/kiểm tra tại nơi thực thi write.

### 14.3. Fencing token

Fencing token là token có thứ tự tăng dần, được kiểm tra tại resource được bảo vệ. Khi leader mới nhận token cao hơn, resource từ chối request từ leader cũ có token thấp hơn.

Đây là điểm quan trọng: chỉ yêu cầu application tự ngừng khi lease hết hạn có thể không đủ vì process cũ có thể pause hoặc partition. Resource/database/storage phải có cách thực thi fencing hoặc hệ thống phải bảo đảm node cũ bị vô hiệu hóa ở tầng tương đương trước khi writer mới hoạt động.

### 14.4. Fencing sequence

~~~mermaid
sequenceDiagram
    participant C as Coordinator
    participant A as Old leader
    participant B as New leader
    participant S as Protected storage

    C->>A: Epoch 41 lease
    A->>S: Write with token 41
    S-->>A: Accepted
    C->>B: Grant epoch 42
    B->>S: Register / write with token 42
    S-->>B: Accepted
    A->>S: Delayed write with token 41
    S-->>A: Rejected: stale token
~~~

Một số database không nhận token fencing trực tiếp từ ứng dụng. Khi đó cần dùng cơ chế promotion/role của database, revoke writer access, network fencing hoặc control plane đã được chứng minh để ngăn node cũ ghi.

## 15. Fencing ở những lớp nào?

Fencing cần chặn quyền ghi tại tất cả resource có thể tạo trạng thái xung đột:

- Database primary/writer endpoint.
- Object storage nếu nhiều leader ghi cùng key/manifest.
- Queue producer hoặc workflow state store.
- Distributed lock/resource coordinator.
- Scheduler/job executor có thể tạo side effect.
- File system/shared volume.
- External service nếu nó hỗ trợ idempotency/lease/ownership token.

Chặn traffic ở load balancer nhưng node cũ vẫn giữ DB credential và kết nối trực tiếp thì chưa chắc đủ. Revoke credential cũng có thể có độ trễ nếu connection/session cũ còn sống. Phải hiểu enforcement point và thời gian vô hiệu thực tế.

## 16. Failover an toàn: thứ tự quan trọng

Failover không nên là lệnh “promote replica” chạy ngay khi health check timeout. Một quy trình an toàn phải xác định node cũ không còn authority trước khi node mới nhận write.

Một flow khái niệm:

~~~mermaid
flowchart TD
    A["Primary suspected failed"] --> B["Confirm failure scope"]
    B --> C{"Can establish quorum / authority?"}
    C -- "No" --> D["Keep writes disabled or degraded"]
    C -- "Yes" --> E["Fence old writer"]
    E --> F["Select eligible candidate"]
    F --> G["Check log position and RPO"]
    G --> H["Promote with new epoch"]
    H --> I["Update writer routing"]
    I --> J["Validate invariants and transactions"]
    J --> K["Enable writes"]
~~~

Nếu không thể chứng minh writer cũ đã bị fence, lựa chọn an toàn cho dữ liệu quan trọng có thể là tạm dừng write. Đây là trade-off consistency/availability; không phải outage nào cũng có thể tiếp tục ghi an toàn.

### 16.1. Candidate selection

Candidate nên được đánh giá theo:

- Replication position/last durable commit.
- Health và khả năng lưu trữ.
- Region/zone placement.
- Engine version và schema compatibility.
- Khả năng đạt quorum hoặc promotion policy.
- RPO nếu phải chấp nhận mất một số log chưa replicate.
- Capacity để phục vụ production workload.

Không chọn node chỉ vì nó phản hồi nhanh nhất.

## 17. Failback và tái gia nhập node cũ

Sau khi DR site được promote, node/region cũ có thể quay lại. Không nên tự động đưa nó trở lại thành primary hoặc nối log hai chiều mà chưa kiểm tra.

Quy trình rejoin an toàn:

1. Giữ node cũ ở trạng thái fenced/read-only.
2. Lưu log và snapshot phục vụ điều tra nếu cần.
3. Xác định epoch/leader hiện tại và authoritative history.
4. Đánh giá node cũ có dữ liệu phân kỳ hay không.
5. Re-seed từ primary mới hoặc restore/replay theo protocol.
6. Kiểm tra version, checksum, business invariants và replication lag.
7. Cấu hình nó làm replica mới, không tự giành writer role.
8. Diễn tập failback trong cửa sổ có kiểm soát.
9. Chỉ chuyển primary về site cũ nếu có kế hoạch, fencing và approval phù hợp.

Failback không nhất thiết phải nhanh. Nhiều hệ thống nên duy trì DR site làm primary một thời gian rồi chuyển về khi rủi ro thấp và capacity đầy đủ.

## 18. Unknown commit và idempotency trong DR

Một tình huống khó là client gửi command tới primary, primary commit thành công, nhưng response bị mất khi network partition xảy ra. Client không biết transaction đã commit hay chưa. Nếu retry sang writer mới, có thể tạo bản ghi hoặc giao dịch thứ hai.

Cần:

- Idempotency key ổn định theo business operation.
- Unique constraint trên business identifier khi phù hợp.
- Lưu kết quả command và trạng thái transaction.
- Query/reconciliation trên writer authority mới trước khi retry.
- Không tạo side effect bên ngoài trước khi có trạng thái durable rõ ràng.
- Sử dụng idempotency support của provider cho payment/refund.
- Trạng thái PENDING/UNKNOWN để thể hiện kết quả chưa xác định.

Không thể dùng request ID ngẫu nhiên mới cho mỗi retry nếu muốn nhận diện cùng một thao tác nghiệp vụ.

## 19. Event sourcing và log-based recovery

Với hệ thống event-sourced, event store có thể là lịch sử nguồn để dựng lại aggregate/projection. Tuy nhiên, phải phân biệt:

- Event đã commit vào authoritative event store.
- Event đã publish tới message broker.
- Consumer đã áp dụng event.
- Projection đã commit và checkpoint.
- Side effect bên ngoài đã hoàn tất.

Mỗi mốc có failure mode riêng. Nếu chỉ có event store authoritative, có thể rebuild projection từ stream; nhưng không thể giả định email/payment provider cũng có thể được “undo” bằng replay.

### 19.1. Rebuild projection

Projection có thể rebuild vào bảng mới, kiểm tra số lượng/checksum/metric rồi chuyển reader sang version mới. Trong lúc replay, giới hạn tốc độ để tránh chiếm tài nguyên production. Consumer side effect cần tách riêng và được disable trong chế độ rebuild.

## 20. Active-active và conflict policy

Active-active cho phép nhiều region phục vụ traffic và có thể cho nhiều nơi nhận write. Điều này tăng khả năng phục vụ địa lý nhưng tạo thêm yêu cầu consistency.

Các lựa chọn:

- **Home-region per tenant/aggregate:** chỉ một region sở hữu write cho mỗi đối tượng.
- **Partitioned ownership:** các shard/tenant được phân vùng writer rõ ràng.
- **Single-writer with local reads:** region khác đọc replica nhưng command chuyển về home writer.
- **Conflict-free data types:** chỉ dùng khi phép toán và semantics thật sự commutative/convergent.
- **Application-level conflict resolution:** phù hợp một số dữ liệu có thể hợp nhất theo business rules.
- **Manual reconciliation:** với giao dịch nhạy cảm không thể tự động merge.

Không dùng last-write-wins cho ledger, booking allocation hay inventory chỉ vì triển khai dễ. Clock skew và update có ý nghĩa nghiệp vụ khác nhau có thể làm mất dữ liệu hợp lệ.

### 20.1. Khi nào single-writer tốt hơn?

Single-writer thường dễ bảo vệ invariant hơn cho một aggregate có thứ tự bắt buộc. Đổi lại, người dùng ở region xa có thể chịu latency cao hơn và một region trở thành nơi phải failover khi lỗi. Sharding theo tenant/aggregate có thể phân bổ home writer nhưng làm tăng complexity của routing và migration.

## 21. Data validation sau recovery

Sau khi restore/promote, cần xác nhận dữ liệu trước khi mở toàn bộ traffic.

Các lớp validation:

1. **Physical/integrity:** database recovery hoàn tất, page/checksum/storage khỏe.
2. **Log continuity:** không thiếu transaction log/sequence trong khoảng đã cam kết.
3. **Schema compatibility:** migration version và application build tương thích.
4. **Referential integrity:** foreign keys hoặc business references hợp lệ.
5. **Business invariants:** số dư, reservation, payment state, uniqueness và trạng thái hợp lệ.
6. **Completeness:** record count/amount theo cửa sổ được đối soát.
7. **Security:** credential, role, tenant isolation và encryption hoạt động.
8. **Operational readiness:** backup mới, replication topology, monitoring và alert đã sẵn sàng.

Nếu validation phát hiện sai khác, giữ write disabled hoặc giới hạn traffic vào chức năng không bị ảnh hưởng; cách ly record nghi vấn, lưu bằng chứng và chạy reconciliation có owner.

## 22. Runbook phục hồi dữ liệu

Một runbook thực tế cần có:

- Trigger và scope để kích hoạt recovery.
- Người có quyền quyết định và người thực thi.
- Nguồn backup/log/replica được công nhận.
- Recovery target, RPO/RTO và lựa chọn mất dữ liệu nếu có.
- Lệnh hoặc automation theo đúng phiên bản công cụ.
- Bước fencing writer cũ.
- Thứ tự restore, replay và migration.
- Validation technical/business.
- Routing, DNS, certificate và secret update.
- Kiểm soát mở write theo cohort.
- Reconciliation/compensation và xử lý message backlog.
- Truyền thông với owner nghiệp vụ.
- Tiêu chí kết thúc incident và lưu evidence.

Runbook phải dùng đường dẫn secret/credential qua vault, không ghi password hoặc key trực tiếp. Tài liệu cần có version, owner, ngày diễn tập gần nhất và phụ thuộc nền tảng.

## 23. Kiểm thử DR và diễn tập

Backup job xanh không chứng minh khả năng phục hồi. Phải restore thực tế và đo thời gian.

Các bài test cần có:

- Restore full backup vào môi trường cách ly.
- PITR tới thời điểm trước thao tác xóa nhầm.
- Thiếu một transaction log segment và xác nhận hệ thống báo lỗi, không âm thầm phục hồi thiếu.
- Mất primary trong lúc write.
- Network partition giữa các node và kiểm tra không có hai writer.
- Leader cũ quay lại với epoch/token cũ và bị từ chối.
- Replica lag vượt ngưỡng trước promotion.
- Client timeout đúng thời điểm commit và retry idempotent.
- Rebuild projection từ raw/event log.
- Failback và rejoin node cũ.
- Restore secret, KMS access, DNS, identity và application dependency.
- Đo RPO/RTO thực tế bằng timestamp và business transaction ID.

Mỗi thử nghiệm phải có hypothesis, scope, guardrail, stop condition, owner và tiêu chí PASS. Sau diễn tập, cập nhật runbook, automation và capacity plan.

## 24. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Coi replica là backup | Delete/corruption lan sang bản sao | Backup độc lập và PITR |
| Không đặt RPO/RTO theo nghiệp vụ | Chiến lược DR không đáp ứng chức năng quan trọng | Tier service/data và đo recovery thực |
| Backup không được restore test | Phát hiện lỗi khi đã xảy ra thảm họa | Diễn tập restore có lịch |
| Backup cùng quyền/account production | Kẻ tấn công xóa cả backup | Immutable/offsite copy và tách quyền |
| Promote node chưa bắt kịp | Mất giao dịch đã commit ở primary cũ | Candidate criteria và log-position check |
| Chỉ đổi DNS để failover | Writer cũ vẫn nhận write, gây split-brain | Fencing tại resource và writer authorization |
| Hai region cùng ghi khi partition | Hai nhánh dữ liệu xung đột | Quorum, home writer hoặc conflict protocol |
| Merge theo timestamp | Mất update hợp lệ do clock skew/semantic khác | Version và domain-specific reconciliation |
| Replay side effect | Gửi email/thu tiền/hoàn tiền trùng | Tách projector và integration handler |
| Bỏ qua unknown commit | Retry tạo giao dịch trùng | Idempotency và reconciliation |
| Rejoin node cũ trực tiếp | Dữ liệu phân kỳ ghi ngược vào primary | Fence, re-seed và rejoin thành replica |
| Chỉ kiểm tra row count | Bỏ sót sai lệch nội dung/business | Checksum và invariant reconciliation |
| Bật ghi trước khi validate | Corruption lan rộng sau recovery | Read-only validation gate |
| Failback vội vàng | Outage thứ hai hoặc split-brain mới | Kế hoạch failback riêng và diễn tập |
| Không backup control metadata | Database có nhưng thiếu key/config để chạy | Recovery dependency map |

## 25. Quy trình thiết kế và triển khai

1. **Phân loại dữ liệu và dịch vụ:** xác định business criticality, owner và khả năng tái tạo.
2. **Đặt RPO/RTO:** theo hành trình người dùng và tác động tài chính/pháp lý.
3. **Chọn recovery mechanism:** backup, PITR, snapshot, replication, archive hoặc replay.
4. **Thiết kế backup isolation:** offsite/immutable, quyền, encryption key và retention.
5. **Xây recovery dependency map:** identity, KMS, DNS, network, app, DB, queue và config.
6. **Thiết kế authority model:** single writer, quorum, home region, epoch và fencing.
7. **Định nghĩa divergence detection:** log position, version, checksum và business reconciliation.
8. **Định nghĩa conflict policy:** auto merge khi an toàn, quarantine/manual khi không thể chứng minh.
9. **Thiết kế failover:** fence cũ, chọn candidate, kiểm tra RPO, promote và route.
10. **Thiết kế failback/rejoin:** giữ node cũ read-only, re-seed, validate và chuyển có kiểm soát.
11. **Bảo vệ command/side effect:** idempotency, unknown commit, replay mode và compensation.
12. **Thiết lập monitoring/runbook:** backup age, log gap, replica lag, recovery progress, epoch và writer identity.
13. **Diễn tập:** restore, PITR, partition, split-brain, failover, failback và reconciliation.

## 26. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi thiết kế |
| --- | --- |
| **Độ tin cậy** | Backup/PITR có restore được? RPO/RTO đã đo? Failover có fencing? Divergence được phát hiện và giải quyết trước khi mở write? |
| **Bảo mật** | Backup/key có tách quyền? Recovery credential được bảo vệ? Ai được promote writer, restore hoặc export dữ liệu? |
| **Hiệu quả hiệu năng** | Restore/replay có hoàn thành trong RTO? Backfill/reconciliation có giới hạn tải? Recovery node có đủ capacity? |
| **Tối ưu chi phí** | Retention/replication/archive có theo tier? Chi phí DR có tương xứng với business impact? |
| **Khả năng vận hành** | Có runbook, owner, alert log gap/backup age/lag, audit epoch và diễn tập failover/failback? |

### Checklist nghiệm thu

- [ ] Dataset/service được phân loại theo criticality, source of truth và khả năng tái tạo.
- [ ] RPO/RTO được định nghĩa theo nghiệp vụ và kiểm chứng qua diễn tập.
- [ ] Backup, snapshot, replication, archive và PITR có mục tiêu riêng.
- [ ] Backup độc lập failure domain/quyền production, được mã hóa và restore test.
- [ ] Transaction log/WAL/binlog retention đủ cho PITR theo policy.
- [ ] Recovery dependency map bao gồm identity, KMS, DNS, network, secrets, app và data.
- [ ] Writer/leader authority có quorum/lease/epoch hoặc cơ chế tương đương.
- [ ] Fencing được thực thi tại nơi có thể tạo side effect hoặc ghi dữ liệu.
- [ ] Replica candidate được chọn theo freshness, capacity và RPO.
- [ ] Divergence được phát hiện bằng log position, checksum và business invariants.
- [ ] Conflict resolution theo domain; không merge mù theo timestamp.
- [ ] Unknown commit/retry có idempotency và reconciliation.
- [ ] Replay không lặp side effect; projection có thể rebuild an toàn.
- [ ] Failback giữ node cũ fenced, re-seed và validate trước khi rejoin.
- [ ] Write chỉ mở sau integrity, schema, security và business validation.
- [ ] Runbook có owner, guardrail, stop condition và evidence.
- [ ] Restore, PITR, partition, split-brain, failover và failback đã được diễn tập.

## 27. Bài tập áp dụng

Một nền tảng đặt thuê thiết bị có primary database tại Region A và replica bất đồng bộ tại Region B. Mục tiêu RPO là 30 giây, RTO là 10 phút. Một sự cố mạng làm hai region mất liên lạc. Đội vận hành nghi ngờ primary A bị lỗi và promote replica B. Tuy nhiên, primary A vẫn hoạt động với một số client kết nối cũ. Trong khoảng partition, A ghi BookingCancelled còn B ghi BookingRescheduled cho cùng một booking. Sau 4 phút, mạng phục hồi.

Hãy thiết kế:

1. Làm sao xác định region nào có authority và replica B có đủ dữ liệu trong RPO?
2. Trình tự fencing primary A trước và sau khi promote B là gì?
3. Làm sao phát hiện hai event version cùng phát sinh từ một state cũ?
4. Booking nào là nguồn có thẩm quyền để giải quyết cancel/reschedule? Ai quyết định?
5. Có thể tự động merge hay phải quarantine/manual review? Vì sao?
6. Làm sao giữ lại log và bằng chứng của cả hai nhánh trước khi rebuild?
7. Node A sẽ được re-seed và rejoin thành replica như thế nào?
8. Transaction client không rõ kết quả commit được xử lý bằng idempotency/reconciliation ra sao?
9. Kiểm tra nào cần hoàn tất trước khi mở lại write đầy đủ?
10. Diễn tập nào chứng minh RPO 30 giây và RTO 10 phút trong thực tế?

Một phương án an toàn phải chứng minh B đã được promote với authority mới và A đã bị fence. Hai event nghiệp vụ mâu thuẫn phải được xác định từ business evidence và domain policy; không chọn event chỉ vì timestamp lớn hơn. Sau khi lưu bằng chứng, có thể tạo state đúng trên writer hiện tại bằng command/reconciliation có audit, rồi re-seed A từ nguồn có thẩm quyền. Nếu không thể xác nhận authority hoặc dữ liệu có thể mất vượt RPO, cần giữ write ở trạng thái hạn chế và escalte quyết định thay vì cho hai node tiếp tục ghi.

**Điểm cốt lõi:** backup và log phục hồi cung cấp đường quay về trạng thái đã biết; reconciliation và replay xử lý dữ liệu thiếu/trùng/phân kỳ; quorum, epoch và fencing ngăn hai writer cùng tạo lịch sử. Failover an toàn đòi hỏi xác định authority, vô hiệu writer cũ, kiểm tra recovery point và chỉ mở ghi sau validation. Phục hồi chỉ hoàn tất khi dữ liệu đúng theo invariant nghiệp vụ và hệ thống có thể tiếp tục vận hành trong một topology được kiểm soát.
