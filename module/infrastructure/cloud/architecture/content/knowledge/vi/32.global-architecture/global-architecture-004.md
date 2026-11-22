# Sao chép xuyên khu vực và độ trễ đồng bộ

Ứng dụng cloud phục vụ nhiều vùng địa lý thường cần giữ dữ liệu ở nhiều region để giảm latency cho người dùng, tăng khả năng chịu lỗi và đáp ứng yêu cầu về nơi lưu trữ dữ liệu. Tuy nhiên, sao chép dữ liệu xuyên khu vực không đơn giản là tạo thêm một bản sao. Khoảng cách địa lý làm tăng round-trip time; replication bất đồng bộ tạo độ trễ đồng bộ và có thể mất một phần write khi region lỗi; replication đồng bộ lại làm write phụ thuộc vào network và sức khỏe của region từ xa.

Thiết kế cần trả lời: dữ liệu nào phải có mặt ở region nào, region nào có quyền ghi, write được xác nhận ở thời điểm nào, đọc được phép stale bao lâu, hệ thống xử lý conflict ra sao và chuyển vùng khi lỗi như thế nào. Các câu trả lời này cần khác nhau theo loại dữ liệu và invariant nghiệp vụ.

Trong module **CLOUD_ARCHITECTURE**, bài học này phân tích replication topology, synchronous/asynchronous replication, consistency, replication lag, RPO/RTO, conflict resolution, failover/failback, data residency và observability. Mục tiêu là chọn trade-off có thể giải thích và kiểm chứng giữa latency, availability, durability, data correctness, chi phí và vận hành.

## 1. Vì sao sao chép xuyên khu vực?

Một region thường gồm nhiều failure domain như Availability Zone, trung tâm dữ liệu hoặc cụm hạ tầng. Sao chép trong region có thể giúp chịu lỗi một node/AZ; sao chép sang region khác bổ sung khả năng phục hồi khi cả region bị gián đoạn hoặc cần phục vụ traffic gần người dùng ở xa.

Các mục tiêu chính:

- **Disaster recovery:** khôi phục dịch vụ khi region chính không hoạt động.
- **Read locality:** phục vụ truy vấn đọc từ region gần người dùng.
- **Data durability:** duy trì nhiều bản sao ở failure domain độc lập.
- **Availability:** tiếp tục một phần chức năng khi mất kết nối tới region khác.
- **Business continuity:** giảm gián đoạn cho các hoạt động quan trọng.
- **Residency/compliance:** lưu hoặc xử lý dữ liệu theo khu vực được phép.
- **Workload distribution:** phân tán read traffic và xử lý dữ liệu.

Các mục tiêu có thể xung đột. Ví dụ, phục vụ read local từ replica giúp giảm latency nhưng replica có thể chưa nhận write mới. Replication đồng bộ có thể bảo vệ write tốt hơn nhưng làm tăng latency và phụ thuộc network WAN.

## 2. Phân biệt replication, backup và disaster recovery

| Khái niệm | Mục đích | Giới hạn |
| --- | --- | --- |
| **Replication** | Duy trì bản sao gần thời gian thực ở node/region khác | Lỗi logic, xóa nhầm hoặc corruption có thể được sao chép theo |
| **Backup** | Lưu recovery point để khôi phục trạng thái trước đó | Có thể có khoảng mất dữ liệu và thời gian restore |
| **Disaster recovery (DR)** | Quy trình khôi phục dịch vụ và dữ liệu sau thảm họa | Cần cả compute, network, identity, key, config và người vận hành |
| **Failover** | Chuyển workload sang bản sao/region dự phòng | Cần kiểm soát ownership, consistency và traffic |
| **Failback** | Chuyển trở lại region ưu tiên sau khi phục hồi | Phải đồng bộ dữ liệu và chuyển writer an toàn |

Replication không thay backup. Nếu một câu lệnh xóa nhầm được commit ở primary và replication hoạt động đúng, lệnh xóa đó cũng sẽ tới replica. Backup hoặc point-in-time recovery mới cho khả năng quay lại trạng thái trước lỗi nếu retention và quy trình phù hợp.

DR không chỉ là promote database replica. Ứng dụng còn cần DNS/routing, certificates, secrets, KMS, container image, service discovery, queue, object storage, observability và capacity ở region dự phòng.

## 3. Các kiểu replication topology

Topology quyết định region/node nào được ghi, đọc và điều phối dữ liệu. Các thuật ngữ có thể khác theo database/cloud service; cần đối chiếu semantics của sản phẩm cụ thể.

### Primary–standby

Một region là primary/writer. Region khác nhận bản sao và thường ở trạng thái standby; khi primary lỗi, standby có thể được promote thành writer.

~~~mermaid
flowchart LR
    APP["Applications"]
    P["Region A\nPrimary writer"]
    S["Region B\nStandby replica"]
    APP --> P
    P -->|Replication stream| S
~~~

Ưu điểm là ownership rõ, conflict ghi thấp và dễ hiểu hơn cho transaction. Hạn chế là write phụ thuộc primary; read từ standby có thể stale; failover cần quyết định RPO và fencing writer cũ.

### Active–passive ở cấp ứng dụng

Một region nhận toàn bộ hoặc phần lớn write traffic; region còn lại có thể phục vụ read-only, health probe hoặc một phần workload. Khi failover, traffic được chuyển tới region đã sẵn sàng.

Ưu điểm là giảm chi phí chạy toàn bộ capacity active ở cả hai nơi. Hạn chế là region passive phải được kiểm tra capacity và readiness; nếu chỉ chạy hạ tầng tối thiểu, nó có thể không chịu nổi peak traffic khi failover.

### Active–active

Nhiều region cùng nhận request và có thể cùng ghi. Dữ liệu được đồng bộ qua các region theo topology hỗ trợ.

~~~mermaid
flowchart TB
    USERS["Global users"]
    RA["Region A\nActive"]
    RB["Region B\nActive"]
    RC["Region C\nActive"]
    USERS --> RA
    USERS --> RB
    USERS --> RC
    RA <-->|Replication| RB
    RB <-->|Replication| RC
    RC <-->|Replication| RA
~~~

Active–active có thể giảm latency và tăng khả năng phục vụ khi một region mất, nhưng xử lý concurrent write, conflict, ordering, uniqueness và transaction xuyên region phức tạp. Không phải mọi database đều hỗ trợ active–active write với semantics giống nhau.

### Multi-leader

Nhiều node/region nhận write và trao đổi thay đổi với nhau. Cần quy tắc phát hiện conflict và chọn kết quả. Multi-leader phù hợp hơn với dữ liệu có thể merge hoặc phân vùng quyền ghi; không tự động phù hợp cho mọi transaction.

### Leaderless/quorum-based

Client ghi/đọc qua nhiều replica; hệ thống dùng quorum hoặc version vector để xác định kết quả và repair. Quorum có thể tăng khả năng chịu lỗi nhưng semantics phụ thuộc replication factor, read/write quorum, consistency level và implementation.

## 4. Synchronous và asynchronous replication

Hai cách phổ biến khác nhau ở thời điểm primary báo write thành công.

### Synchronous replication

Primary chờ một hoặc nhiều replica xác nhận dữ liệu đã được nhận/ghi theo mức đảm bảo của hệ thống trước khi xác nhận commit cho client.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Primary
    participant R as Remote replica
    C->>P: Write
    P->>R: Replicate log/data
    R-->>P: Acknowledge
    P-->>C: Commit success
~~~

Ưu điểm:

- Giảm khả năng mất write đã được xác nhận khi lỗi primary, tùy semantics xác nhận và quorum.
- Replica có thể bắt kịp gần như ngay tại commit point.
- Có thể hỗ trợ read-after-write từ các replica đủ điều kiện.

Đánh đổi:

- Write latency tăng do WAN round trip.
- Network partition hoặc replica chậm có thể làm write bị block/fail.
- Availability của write phụ thuộc thành phần remote trong cấu hình đồng bộ.
- Chi phí network và vận hành tăng.

“Synchronous” không phải thuật ngữ bảo đảm giống nhau ở mọi sản phẩm. Có hệ thống chỉ chờ log tới durable storage của một replica, có hệ thống chờ quorum commit. Phải đọc đúng guarantee: nhận message, flush log hay commit durable.

### Asynchronous replication

Primary xác nhận write sau khi commit cục bộ; replication tới region khác diễn ra sau đó.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Primary
    participant R as Remote replica
    C->>P: Write
    P-->>C: Commit success
    P->>R: Replicate later
    R-->>P: Applied/acknowledged
~~~

Ưu điểm:

- Write latency thấp hơn và ít phụ thuộc WAN.
- Primary có thể tiếp tục write khi replica remote tạm gián đoạn.
- Phù hợp cho read replica, DR replica hoặc dữ liệu chấp nhận eventual consistency.

Đánh đổi:

- Replica có replication lag.
- Khi primary mất đột ngột, các write chưa tới replica có thể mất.
- Read local có thể stale.
- Failover phải đo lag/last applied position và xác định RPO thực tế.

## 5. Chọn consistency level theo workload

Không phải mọi dữ liệu cần cùng độ nhất quán. Cần bắt đầu từ invariant nghiệp vụ và câu hỏi đọc/ghi.

| Mức/kiểu semantics | Hành vi | Ví dụ có thể phù hợp |
| --- | --- | --- |
| Strong/linearizable | Đọc thấy kết quả mới nhất theo một thứ tự toàn cục được định nghĩa | Quyền sở hữu, inventory cuối cùng, số dư quan trọng |
| Read-after-write | Writer đọc lại thấy write của mình | Trang cài đặt sau khi user lưu |
| Monotonic reads | Một client không bị lùi về phiên bản cũ hơn phiên bản đã thấy | Timeline phiên làm việc |
| Bounded staleness | Replica được phép trễ trong một giới hạn | Catalog hoặc cấu hình có stale budget |
| Eventual consistency | Nếu không có write mới, các replica cuối cùng hội tụ | View count, feed, analytics |

Các tên consistency level phụ thuộc hệ thống phân tán và database. “Strong consistency” cũng cần xác định scope: một key, một partition, một region hay toàn bộ database.

### Phân loại dữ liệu theo invariant

- Product description có thể chấp nhận stale vài giây.
- Booking availability có thể cần kiểm tra authoritative tại thời điểm commit.
- Session preference có thể dùng read-your-writes trong session.
- Payment ledger cần semantics chặt và đối soát.
- Analytics event có thể chấp nhận hội tụ theo thời gian.
- Feature flag có thể cần propagation nhanh nhưng có thể có fallback rõ.

Không chọn eventual consistency chỉ vì nó nhanh. Cần có stale budget, conflict policy và cách xử lý khi người dùng đọc dữ liệu chưa đồng bộ.

## 6. CAP và giới hạn khi network partition

CAP mô tả đánh đổi trong một distributed data system khi xảy ra network partition: hệ thống không thể đồng thời bảo đảm availability đầy đủ cho mọi request và strong consistency theo nghĩa linearizability trong mọi tình huống partition.

Khi các region không liên lạc được:

- Hệ thống ưu tiên consistency có thể từ chối hoặc block một số write/read để tránh trả dữ liệu không nhất quán.
- Hệ thống ưu tiên availability có thể tiếp tục nhận write tại nhiều nơi, sau đó cần xử lý conflict/hội tụ.

CAP không có nghĩa lúc nào cũng chỉ được chọn hai trong ba thuộc tính theo kiểu cấu hình cố định. Khi không có partition, hệ thống vẫn có thể cung cấp cả consistency và availability theo semantics của nó; đánh đổi bộc lộ khi network partition xuất hiện.

### Network partition khác latency cao

Latency cao có thể vẫn có response; partition là không thể giao tiếp trong thời gian cần thiết. Timeout khiến caller không biết operation đã commit hay chưa. Phải phân biệt:

- Request chưa tới primary.
- Request đã tới nhưng chưa commit.
- Primary đã commit nhưng response bị mất.
- Commit đã xảy ra nhưng replica chưa nhận.

Trạng thái “unknown” đặc biệt quan trọng với payment/booking; không nên coi timeout là chắc chắn thất bại.

## 7. Quorum, replication factor và consistency

Một số hệ thống phân tán dùng quorum để yêu cầu số replica xác nhận trước khi đọc/ghi thành công.

Giả sử replication factor là \(N\), write quorum là \(W\), read quorum là \(R\). Trong một số mô hình quorum cơ bản, điều kiện:

\[
R+W>N
\]

có thể bảo đảm giao nhau giữa tập replica đọc và tập replica ghi. Tuy nhiên, đây không tự động chứng minh linearizability; còn phụ thuộc versioning, conflict resolution, concurrent write, hinted handoff, repair và semantics của database.

### Ví dụ

Với \(N=3\), \(W=2\), \(R=2\), ít nhất một replica thường nằm trong cả tập write và read. Nhưng nếu write đồng thời có hai version, read có thể cần quy tắc chọn version hoặc merge; quorum chỉ giúp giao nhau, không tự giải quyết mọi conflict.

### Quorum xuyên region

Nếu quorum yêu cầu xác nhận từ nhiều region, write latency chịu WAN RTT và availability giảm khi một region không kết nối. Nếu quorum chỉ nằm trong region chính, remote replica có thể bất đồng bộ và RPO khi mất cả region không bằng 0.

### Majority và split brain

Majority quorum thường giúp tránh hai phía của partition cùng được quyền commit nếu membership và consensus protocol hoạt động đúng. Nhưng cần fencing/term/epoch để node cũ không tiếp tục ghi sau khi mất quorum hoặc bị promote leader mới.

Không tự triển khai quorum bằng cách đếm HTTP response từ nhiều region nếu chưa có protocol membership, leader election, fencing và log replication được thiết kế đầy đủ.

## 8. Replication lag và cách đọc độ trễ đồng bộ

Replication lag là khoảng cách giữa trạng thái dữ liệu nguồn và replica. Có thể đo theo thời gian, log sequence number/offset, transaction timestamp, applied index hoặc số byte/event chưa được áp dụng.

### Các loại lag

- **Transport lag:** thay đổi chưa tới network receiver.
- **Apply lag:** đã tới nhưng replica chưa áp dụng.
- **Commit/flush lag:** đã nhận/applied nhưng chưa durable theo guarantee.
- **Query visibility lag:** dữ liệu đã replicate nhưng chưa hiển thị cho query/index.
- **End-to-end projection lag:** event đã commit nhưng cache/search/warehouse chưa cập nhật.

### Vì sao lag tăng?

- WAN latency, packet loss hoặc throughput thấp.
- Write volume vượt khả năng apply của replica.
- Transaction lớn hoặc lock dài.
- Replica CPU/IOPS thấp hơn primary.
- Backlog do batch, vacuum/compaction hoặc maintenance.
- Network throttling, quota hoặc service degradation.
- Replication slot/log retention không đủ hoặc consumer bị dừng.

### Đo lag

Nên kết hợp:

| Metric | Câu hỏi |
| --- | --- |
| Seconds behind source | Replica chậm bao lâu theo timestamp? |
| Log/LSN/offset gap | Còn bao nhiêu thay đổi chưa áp dụng? |
| Apply throughput | Replica xử lý được bao nhiêu change/giây? |
| Queue/backlog age | Thay đổi cũ nhất đang chờ bao lâu? |
| Last replicated transaction | Write nào mới nhất đã được xác nhận tới replica? |
| Replica query latency | Đọc từ replica có đang chậm không? |

Timestamp cần đồng bộ clock và semantics thống nhất. Một metric “seconds behind” có thể sai lệch khi source không phát sinh write hoặc clock lệch; hãy xem thêm log position/offset.

### Lag không nhất thiết tăng tuyến tính

Khi workload burst, replication lag có thể tăng nhanh rồi giảm khi tải về mức bình thường. Capacity plan cần biết replica có thể drain backlog nhanh hơn tốc độ phát sinh bao nhiêu. Nếu replication throughput chỉ bằng write rate, lag sẽ không tự giảm sau burst.

## 9. Độ trễ WAN và ngân sách latency

Độ trễ vật lý tăng theo khoảng cách địa lý và số hop network. Một write đồng bộ cần chờ remote acknowledgment có thể thêm ít nhất một WAN round trip, chưa tính xử lý replica, TLS, queue và contention.

### Ví dụ ngân sách

Giả sử write API có budget 250 ms:

| Thành phần | Ước lượng |
| --- | ---: |
| Client-to-region network | 35 ms |
| App processing | 25 ms |
| Local database commit | 20 ms |
| WAN replication round trip | 110 ms |
| Remote durable/apply acknowledgment | 35 ms |
| Response overhead/headroom | 25 ms |
| **Tổng** | **250 ms** |

Các số liệu chỉ để minh họa. RTT thực tế phụ thuộc region pair, routing, provider network, giờ cao điểm và giao thức; cần benchmark từ workload thật.

### Đồng bộ hay bất đồng bộ?

Nếu user-facing write yêu cầu latency thấp và chấp nhận RPO nhỏ nhưng khác 0, asynchronous replication có thể phù hợp. Nếu một write không được xác nhận trước khi có durability ở failure domain thứ hai, synchronous/quorum có thể cần thiết nhưng latency tăng.

### Tối ưu network

- Chọn region placement gần nơi xử lý dữ liệu và người dùng.
- Dùng private connectivity/peering theo kiến trúc và service hỗ trợ.
- Batch các thay đổi khi semantics cho phép.
- Nén log/event nếu tiết kiệm bandwidth lớn hơn chi phí CPU.
- Tách stream dữ liệu quan trọng và telemetry/bulk.
- Provision bandwidth và quota theo peak, không chỉ average.
- Theo dõi packet loss, retransmission, RTT và connection reset.

Không batch quá lớn nếu làm tăng commit latency hoặc tạo replay storm khi lỗi.

## 10. RPO và RTO cho replication xuyên region

**RPO (Recovery Point Objective)** là lượng dữ liệu mất tối đa có thể chấp nhận khi khôi phục, thường thể hiện bằng khoảng thời gian. **RTO (Recovery Time Objective)** là thời gian mục tiêu để khôi phục dịch vụ.

Replication lag ảnh hưởng RPO của failover. Nếu asynchronous replica chậm 8 giây tại thời điểm primary mất, một số write gần nhất có thể chưa có ở replica. RPO thực tế phụ thuộc last durable/applied position, không phải chỉ giá trị trung bình trong dashboard.

### Ví dụ phân lớp mục tiêu

| Workload | RPO giả định | RTO giả định | Kiểu kiến trúc có thể cân nhắc |
| --- | --- | --- | --- |
| Product catalog | Vài phút | 30 phút | Async replica, backup |
| User preference | Vài giây | 15 phút | Async replication, versioned events |
| Booking ledger | Gần 0 theo thiết kế | Vài phút | Synchronous/quorum hoặc log durability, reconciliation |
| Analytics warehouse | Hàng giờ | Vài giờ | Async/batch replication, rebuild pipeline |

Mục tiêu chỉ minh họa; owner nghiệp vụ cần xác định theo tổn thất chấp nhận được và chi phí.

### Đo và báo cáo RPO

Ghi lại:

- Last write acknowledged ở primary.
- Last write durable/known at replica.
- Replica lag ở thời điểm failure.
- Last known good recovery point.
- Số operation ở trạng thái unknown.
- Data reconciliation sau failover.

Không tuyên bố RPO=0 chỉ vì bật synchronous replication nếu guarantee không bao gồm failure mode đang xét (ví dụ mất cả region, quorum mất, acknowledged commit chưa fsync hoặc provider semantics khác).

### RTO không chỉ là database promotion

RTO phải bao gồm detection, incident declaration, decision/approval, fencing, promotion, route change, cache warm-up, application scaling, validation và mở traffic. DR drill cần đo toàn bộ chuỗi.

## 11. Conflict trong multi-writer replication

Khi nhiều region nhận write đồng thời trên cùng dữ liệu, có thể xuất hiện conflict. Replication engine cần xác định version và quy tắc giải quyết.

### Các cách xử lý

| Cách | Mô tả | Phù hợp khi |
| --- | --- | --- |
| Last-write-wins (LWW) | Chọn write có timestamp/version được xem là mới nhất | Dữ liệu preference đơn giản, chấp nhận overwrite |
| Version vector | Theo dõi quan hệ nhân quả giữa các update | Cần phát hiện concurrent update |
| Application merge | Ghép thay đổi theo domain rule | Dữ liệu có merge semantics |
| Single-writer per key/partition | Chỉ owner được phép ghi tại một thời điểm | Cần hạn chế conflict |
| Conflict queue/manual resolution | Đưa conflict để xử lý nghiệp vụ/người vận hành | Dữ liệu quan trọng, khó merge tự động |

### LWW và clock skew

LWW dựa trên timestamp có thể chọn sai nếu clock giữa region lệch hoặc timestamp do client điều khiển. Cần server timestamp/monotonic version hoặc logic provider hỗ trợ; vẫn phải hiểu semantics khi hai update đồng thời.

### Merge theo nghiệp vụ

Ví dụ hai region cập nhật hai field độc lập của hồ sơ, có thể merge field-level nếu không có invariant chéo. Nhưng hai region cùng bán một đơn vị inventory cuối cùng không thể đơn giản lấy max/min hoặc cộng trừ tùy tiện. Cần reservation/ownership/quorum/transaction logic authoritative.

### CRDT

Conflict-free Replicated Data Types (CRDT) được thiết kế với phép toán hội tụ khi replicas trao đổi state/update theo điều kiện của kiểu dữ liệu. Counter/set có thể có CRDT phù hợp, nhưng không biến mọi domain object thành conflict-free. Cần chọn loại CRDT đúng, kiểm tra semantics remove/update và chi phí metadata.

### Conflict observability

Đo số conflict theo entity/type/region, tỷ lệ tự resolve, thời gian pending và số lần manual override. Nếu conflict tăng, cần điều tra clock, routing, ownership hoặc traffic split chứ không chỉ tăng retry.

## 12. Single-writer, partition ownership và data locality

Một cách giảm conflict là gán mỗi key/tenant/partition cho một region làm owner ghi. Các region khác có thể đọc replica hoặc gửi write tới owner.

### Single-writer per entity

- Một booking/ledger record có một authoritative writer.
- Request từ region khác route tới owner hoặc queue command tới owner.
- Khi failover, ownership được chuyển qua epoch/lease/fencing.
- Replica nhận update và phục vụ read theo stale budget.

Ưu điểm là tránh nhiều writer cùng sửa một invariant. Đánh đổi là write có thể phải đi WAN tới owner; khi owner lỗi cần failover có kiểm soát.

### Partition by region

Có thể phân vùng dữ liệu theo khách hàng, account, tenant hoặc địa lý. Ví dụ mỗi tenant có home region; write tenant A do region A sở hữu, tenant B do region B sở hữu.

Điều này giảm conflict và cross-region write nhưng cần giải quyết:

- Tenant/user đổi region hoặc cần di chuyển dữ liệu.
- Request liên quan nhiều tenant/region.
- Global search/report.
- Availability khi home region bị lỗi.
- Cross-region relationship và uniqueness.
- Data residency.

### Ownership registry

Một control plane có thể ánh xạ entity/tenant tới home region, epoch và trạng thái. Registry là dữ liệu control quan trọng, cần versioning, audit và consistency. Khi failover, chỉ owner mới có epoch cao hơn mới được chấp nhận write; node cũ phải bị fence.

Không chỉ đổi DNS hoặc config để chuyển owner. Client cũ có thể tiếp tục gửi write tới region cũ; database/service cần kiểm tra fencing token/epoch tại điểm commit.

## 13. Read routing và stale data policy

Read có thể được route tới primary, local replica hoặc replica trong cùng region. Quyết định nên dựa trên consistency requirement và latency budget.

### Các lựa chọn

- **Read from primary:** dữ liệu mới nhất theo semantics primary nhưng có thể tăng tải/latency.
- **Read from local replica:** latency thấp, chấp nhận replication lag.
- **Read-your-writes routing:** sau khi user write, route các lần đọc tiếp theo tới primary hoặc replica đã catch up.
- **Session consistency token:** client gửi version/LSN cần đạt; replica chỉ phục vụ khi đã áp đủ version hoặc fallback sang primary.
- **Stale-while-revalidate:** trả dữ liệu cũ trong stale window cho workload chấp nhận.

### Read-your-writes

Sau khi user cập nhật địa chỉ tại region A rồi đọc tại region B, replica B có thể chưa nhận update. Có thể dùng session token gắn commit position; region B đợi replica đạt position đó hoặc route về primary. Cần giới hạn thời gian chờ; không giữ request vô hạn.

### Bounded staleness

Đặt stale budget theo dataset, ví dụ catalog cho phép chậm tối đa 10 giây, còn payment state không đọc từ replica quá stale. Nếu replica vượt budget, không phục vụ stale data cho endpoint yêu cầu freshness; fallback về source hoặc trả trạng thái retry-later.

### Read-after-write khác với strong consistency

Read-your-writes trong một session không tự bảo đảm mọi client ở mọi region thấy cùng một thứ tự global. Hãy mô tả guarantee cụ thể thay vì gọi chung là “consistent”.

## 14. Transaction xuyên region và distributed workflow

Transaction ACID trong một database/region thường không kéo dài tự nhiên qua nhiều region hoặc nhiều service. Distributed transaction có thể dùng consensus/2-phase commit nhưng tăng latency và coupling; nhiều hệ thống dùng saga/outbox/eventual consistency.

### Khi cần transaction toàn cục

Các invariant như “không bán vượt tồn kho” hoặc “một payment chỉ capture một lần” có thể cần một điểm tuần tự hóa/authority. Lựa chọn:

- Single-writer/partition ownership.
- Strongly consistent database hoặc distributed transaction service.
- Reservation/lease với expiration và idempotency.
- Saga với state machine và compensating actions.

Không dùng asynchronous replication để quyết định đồng thời hai request ở hai region cùng mua đơn vị cuối cùng nếu chưa có cơ chế invariant.

### Saga xuyên region

Một workflow có thể giữ state tại owner region và phát command/event tới dịch vụ khác. Mỗi bước có idempotency key, timeout, retry policy, operation status và compensation. Tenant/region context cần được truyền cùng correlation ID; event replay không được tạo side effect trùng.

### Outbox và replication

Ghi business state cùng outbox event trong cùng local transaction, sau đó relay publish. Consumer ở region khác apply idempotently. Nếu source fail sau commit nhưng trước publish, outbox đảm bảo event còn để retry. Cần retention đủ lâu và replay path để phục hồi consumer lag.

## 15. Failover: ownership, fencing và split brain

Failover là thay đổi quyền phục vụ/ghi từ region hoặc node lỗi sang nơi dự phòng. Đây là thao tác có rủi ro consistency cao.

### Checklist failover

1. Xác định failure scope và xác nhận primary thực sự unavailable hay chỉ mất kết nối.
2. Đo replication lag và last durable/applied position.
3. Xác định RPO thực tế, write/operation đang unknown và quyết định chấp nhận.
4. Fence hoặc revoke writer cũ bằng cơ chế supported.
5. Promote replica/leader mới theo protocol.
6. Cập nhật ownership registry/epoch.
7. Chuyển routing và client discovery theo wave.
8. Warm cache, scale capacity và kiểm tra dependency.
9. Xác minh business transaction, data consistency và duplicate.
10. Theo dõi region mới trước khi mở toàn bộ traffic.

### Split brain

Split brain xảy ra khi hai node/region cùng tin mình là authoritative writer. Một partition có thể làm region cũ không nhận được thông tin promote mới nhưng vẫn nhận request từ client cũ.

Biện pháp:

- Consensus/leader election có quorum.
- Epoch/term/fencing token tăng đơn điệu.
- Lease có semantics rõ và kiểm tra tại storage/commit path.
- Network/service routing phối hợp nhưng không là lớp bảo vệ duy nhất.
- Khi không xác định owner, fail closed cho write nhạy cảm thay vì cho cả hai bên ghi.

### Failover có thể gây mất dữ liệu

Với async replication, promote replica có thể bỏ qua write chưa replicate. Cần ghi lại recovery point và operation chưa chắc đã đến. Sau khi primary cũ trở lại, không tự động merge toàn bộ log theo timestamp; phải xác định authoritative branch và reconciliation plan.

## 16. Failback và resynchronization

Sau khi region chính phục hồi, không nên route traffic về ngay. Region đã failover có thể đã nhận write mới, vì vậy hai database đã lệch nhau.

### Quy trình failback

1. Xác nhận region cũ ổn định và security/identity/network đã phục hồi.
2. Quyết định region nào là writer authoritative hiện tại.
3. Thiết lập replication từ current writer sang region cũ hoặc rebuild replica theo procedure.
4. Theo dõi lag tới khi đạt tiêu chí.
5. Reconcile conflict/operation unknown và kiểm tra data integrity.
6. Chuyển role/ownership có fencing và epoch mới.
7. Chuyển traffic từng bước về region đích.
8. Giữ phương án quay lại current region trong cửa sổ quan sát.

### Rebuild replica hay reverse replication?

Nếu hai nhánh đã diverge, rebuild từ authoritative source có thể an toàn hơn nối replication hai chiều mù. Nếu dùng reverse replication, phải xác định log position, conflict và dữ liệu đã ghi ở mỗi bên. Chọn theo khả năng database và runbook đã thử.

### Không kết thúc DR khi traffic đã chuyển

Phải xác nhận backup schedule, monitoring, alert routing, KMS, capacity, replication health và on-call ownership đã trở lại trạng thái chuẩn. Ghi actual RTO/RPO, gap và action item.

## 17. Network architecture cho replication

Replication xuyên region phụ thuộc network throughput, latency, route, encryption, MTU, connection và provider quota.

### Network path

Xác định:

- Source/destination endpoint và region.
- Private connectivity, peering, transit gateway hoặc provider backbone phù hợp.
- Firewall/security group/NACL/route table.
- DNS resolution và failover endpoint.
- TLS/mTLS, certificate rotation và trust chain.
- Bandwidth, packet loss, retransmission và egress quota.
- Monitoring riêng cho replication stream.

### Dedicated replication path

Nếu replication cạnh tranh với user traffic, có thể tách network class/QoS hoặc bandwidth reservation. Tách path giúp kiểm soát nhưng không loại bỏ failure chung như backbone/provider outage; cần test congestion và route change.

### Compression và batching

Compression giảm bytes truyền nhưng tăng CPU và có thể tăng latency cho payload nhỏ. Batching tăng throughput nhưng làm dữ liệu chờ lâu hơn trước khi phát. Chọn theo workload, record size, lag SLO và khả năng apply ở replica.

### TLS và encryption

Mã hóa replication stream theo service support; quản lý certificate/key ở mọi region. Kiểm tra rotation không làm ngắt stream dài hạn. Nếu dùng customer-managed key, DR region phải có quyền truy cập hợp lệ theo policy; không chia sẻ quyền KMS quá rộng chỉ để failover dễ hơn.

## 18. Data residency, sovereignty và placement

Replication có thể tạo bản sao dữ liệu ở khu vực khác với primary. Kiến trúc phải xem xét residency, sovereignty, contractual commitment và quyền truy cập vận hành.

### Data classification theo region

Không nhất thiết mọi dataset cần cùng topology:

| Loại dữ liệu | Placement có thể cân nhắc |
| --- | --- |
| Public catalog | Global cache/read replica |
| User profile | Home region theo tenant/subject, replicate metadata theo policy |
| Payment/financial ledger | Region/zone được phê duyệt, durability và audit chặt |
| Security logs | Region lưu theo yêu cầu, access cross-region hạn chế |
| Aggregated analytics | Cross-region sau minimization/approval |
| Secrets/keys | KMS/HSM region-specific, replication/key grant có kiểm soát |

### Residency không chỉ là primary database

Backup, logs, traces, cache, search index, data lake, support exports và disaster recovery copy đều có thể chứa dữ liệu. Cần data-flow map có region, processor và access location.

### Global routing

Geo-DNS/anycast/latency-based routing có thể đưa user tới region gần nhất, nhưng data owner/home region có thể khác. Request cần route data read/write theo consistency và residency policy, không chỉ theo khoảng cách mạng.

### Legal/contract policy

Các yêu cầu pháp lý thay đổi theo ngành và khu vực. Bài học kiến trúc không thay tư vấn pháp lý; owner compliance cần xác định dữ liệu nào được replicate, xử lý ở đâu, ai được truy cập và bằng chứng cần giữ.

## 19. Observability cho replication xuyên region

Không thể vận hành replication chỉ bằng một dashboard hiển thị “replica healthy”. Cần quan sát tiến độ truyền, apply, độ mới dữ liệu, lỗi và khả năng phục hồi.

### Metrics nền tảng

| Nhóm | Metric |
| --- | --- |
| Latency | WAN RTT, replication delay, commit acknowledgment latency |
| Progress | LSN/offset/index gap, last applied position |
| Throughput | Bytes/sec, transactions/events per second |
| Backlog | Pending bytes/events, oldest unreplicated age |
| Apply | Apply rate, apply errors, conflict count |
| Health | Connection state, stream reconnect, replica role/state |
| Capacity | CPU, memory, IOPS, network bandwidth, disk/log usage |
| Correctness | Checksum/row count reconciliation, duplicate/constraint errors |
| Recovery | Promotion duration, actual RPO/RTO, failback completion |

### Alert theo lag budget

Đặt ngưỡng lag theo RPO/staleness requirement của dataset. Một catalog có stale budget 30 giây có thể cảnh báo khi lag vượt 10 giây và critical khi vượt 25 giây; ledger yêu cầu chặt hơn nhiều. Đây chỉ là minh họa; ngưỡng nên dựa trên phân bố thực tế và runbook.

### Global dashboard

Dashboard nên thể hiện:

- Topology và current writer/replica role.
- Replication direction và region pair.
- Last acknowledged/applied position.
- Lag p50/p95/max và backlog age.
- Conflict/error theo dataset.
- Region health, WAN RTT và provider incident.
- RPO risk và operation unknown.
- Failover/failback state.

Không dùng trung bình toàn cầu che một region/partition có lag rất cao. Theo dõi per-region pair và per-critical-dataset.

### Trace và audit

Gắn operation ID/correlation ID để theo dõi từ write tới replica projection khi có thể. Ghi role promotion, fencing epoch, routing change và manual conflict resolution vào audit. Không log payload nhạy cảm hoặc credential trong replication trace.

## 20. Capacity planning và chi phí replication

Replication làm tăng storage, network transfer, compute, license/service tier và chi phí vận hành. Active–active có thể tăng chi phí nhiều hơn số region vì còn conflict processing, cross-region query và capacity headroom.

### Ước lượng bandwidth

Giả sử nguồn tạo trung bình 8 MB/s change log; peak bằng 4 lần trong 10 phút; có hai remote replica.

Peak throughput tới mỗi replica:

\[
8\text{ MB/s}\times4=32\text{ MB/s}.
\]

Nếu cả hai replica nhận toàn bộ stream, tổng outbound replication khoảng 64 MB/s trước overhead/compression. Trong 10 phút peak, một replica nhận:

\[
32\text{ MB/s}\times600\text{ s}=19.200\text{ MB}\approx18,3\text{ GiB}.
\]

Capacity cần thêm headroom cho packet overhead, retransmission, snapshot/initial sync và backlog recovery. Khi replica chậm, network cần vừa truyền write mới vừa drain backlog cũ.

### Initial sync

Khi tạo replica mới, initial snapshot có thể tiêu thụ nhiều bandwidth và I/O, ảnh hưởng primary. Cần:

- Ước lượng dataset size và network window.
- Dùng snapshot/seed theo khả năng provider.
- Throttle để không ảnh hưởng production.
- Kiểm tra log retention đủ trong khi snapshot.
- Đo lag và catch-up rate.
- Xác minh checksum/consistency trước khi đưa vào read traffic.

### Storage multiplier

Ba bản sao dữ liệu không chỉ tốn ba lần storage base. Còn có index, WAL/log retention, backup, snapshot, object version và temporary copy. Sizing theo physical bytes và retention thực tế.

### Cost model

Tính:

- Storage GB-month theo region/replica.
- Cross-region data transfer/egress.
- Compute/IOPS cho replica apply và query.
- Backup và snapshot.
- KMS/API calls, monitoring và logging.
- Dedicated network/connection.
- License/support tier.
- On-call, DR drill và vận hành conflict.

Không tối ưu chi phí bằng cách bỏ replica nếu RPO/RTO đã cam kết; thay vào đó phân loại dữ liệu và chọn protection tier theo giá trị nghiệp vụ.

## 21. Security và governance cho replication

Replication stream mang dữ liệu nhạy cảm và thường có quyền đọc rộng. Một credential replication bị lộ có thể cho phép trích xuất dữ liệu với quy mô lớn.

### Kiểm soát

- TLS/mTLS theo khả năng dịch vụ.
- Workload identity và credential riêng cho replication.
- Quyền đọc log/stream tối thiểu; tách quyền quản trị và quyền data.
- KMS key và grant theo region/dataset.
- Encryption at rest cho primary, replica, snapshot và backup.
- Network allowlist/private connectivity.
- Audit role change, config update và access.
- Secret rotation và revoke procedure đã thử.
- Data minimization trước khi replicate sang analytics/secondary region.

### Replication lag và bảo mật

Replica có thể phục vụ dữ liệu cũ sau khi quyền truy cập bị thu hồi hoặc dữ liệu bị xóa. Với authorization/security policy, cần propagation SLA và nguồn authoritative. Không dựa vào eventual replication duy nhất cho revoke nhạy cảm; có thể cần check policy tại serving region hoặc deny khi control plane chưa đồng bộ.

### Data deletion và tombstone

Xóa dữ liệu ở primary có thể được replicate như delete, nhưng backup và snapshot cũ vẫn giữ record. Cần deletion ledger/retention policy cho backup và restore. Khi rebuild replica từ snapshot cũ, phải áp lại deletion markers còn hiệu lực trước khi cho đọc.

## 22. Failure modes và chiến lược ứng phó

| Failure mode | Tác động | Hành động chính |
| --- | --- | --- |
| WAN latency/loss | Lag tăng hoặc sync write timeout | Đo path, giảm bulk, bảo vệ write budget |
| Replica down | Không apply change, backlog tích tụ | Kiểm tra capacity/log retention, reconnect/reseed |
| Primary loss | Write ngừng, failover cần quyết định | Đo last applied, fencing, promote theo RPO |
| Network partition | Hai region mất liên lạc, ownership không rõ | Quorum/fencing, fail closed cho write quan trọng |
| Split brain | Hai writer tạo diverged state | Dừng writer sai, bảo toàn branch, reconcile |
| Disk/log full | Replication dừng, primary có thể bị ảnh hưởng | Alert headroom, xử lý retention theo protocol |
| Schema incompatibility | Replica/consumer không apply được | Version schema, compatibility, pause promotion |
| Clock skew | LWW hoặc ordering sai | Đồng bộ clock, server version/causal metadata |
| Region overload | Catch-up chậm, user workload cạnh tranh | Reserve capacity, throttle read/batch |
| Credential expiry | Stream ngừng hoặc reconnect fail | Rotate theo overlap window, verify trust |
| Accidental delete/corruption | Lỗi lan sang replicas | Stop propagation nếu supported, restore/PITR, reconcile |

### Stop condition

Không promote replica khi chưa biết writer cũ có bị fence không. Không chạy hai chiều replication để “tự merge” nếu database không hỗ trợ. Không xóa log/WAL cần cho catch-up trước khi kiểm tra replica state. Không cho read traffic vào replica vừa seed mà chưa verify.

## 23. Runbook: replication lag tăng cao

### Trigger

- Lag vượt stale budget/RPO alert.
- Backlog bytes/events tăng.
- Replica apply rate thấp hơn source change rate.
- Read query tại replica trả dữ liệu quá cũ.

### Triage

1. Xác định region pair, dataset/partition và thời điểm bắt đầu.
2. So source write rate với replication throughput.
3. Kiểm tra WAN RTT, packet loss, bandwidth và connection reset.
4. Kiểm tra replica CPU, IOPS, disk, lock và apply errors.
5. Xác định initial sync, batch job hoặc schema change mới.
6. Kiểm tra log/WAL retention còn đủ để replica catch up không.

### Containment

- Ngừng hoặc throttle workload bulk không trọng yếu.
- Route read yêu cầu freshness về primary hoặc trả degraded status.
- Hạn chế peak write nếu lag đe dọa RPO và business policy cho phép.
- Không đổi topology/force reseed khi chưa bảo toàn recovery position.

### Recovery

- Khôi phục network/replica resource.
- Theo dõi apply rate phải cao hơn write rate để drain backlog.
- Xác minh lag giảm liên tục, checksum/position và query visibility.
- Mở lại read route theo stale policy.
- Ghi lại thời gian vượt budget và impact.

## 24. Runbook: regional failover và failback

### Trước failover

- Xác định region health và failure domain.
- Xác định current primary, epoch/lease và fencing mechanism.
- Lấy last durable/applied position và replication lag.
- Ghi operation/transaction chưa xác định.
- Xác định RPO và người có quyền chấp nhận.

### Failover

1. Khai báo incident và chỉ định Incident Commander/DB lead.
2. Fence writer cũ hoặc xác minh quorum loại bỏ quyền ghi của nó.
3. Promote region mới theo runbook của database/provider.
4. Cập nhật ownership epoch và control-plane registry.
5. Chuyển application route từng bước.
6. Kiểm tra commit/read/write nghiệp vụ và duplicate.
7. Scale capacity, warm cache và drain backlog.
8. Theo dõi SLO, consistency và unknown operations.

### Failback

1. Xác nhận region cũ đã ổn định.
2. Chọn authoritative writer hiện tại.
3. Reseed hoặc reverse-replicate theo procedure đã phê duyệt.
4. Chờ catch-up và reconciliation.
5. Chuyển writer ownership có fencing.
6. Chuyển traffic từng wave.
7. Theo dõi và hoàn tất backup/monitoring/alert route.

Không failback chỉ vì provider status đã xanh; cần chứng minh dữ liệu đồng bộ và writer ownership đúng.

## 25. Case study: catalog toàn cầu với read replica

Một nền tảng bán dịch vụ có người dùng ở ba khu vực. Catalog gồm mô tả, ảnh, thuộc tính và category; dữ liệu thay đổi không thường xuyên nhưng có lượng read lớn. Yêu cầu giả định:

- Read p99 dưới 200 ms tại từng khu vực.
- Catalog được phép stale tối đa 60 giây.
- RPO DR tối đa 5 phút.
- Một region có thể ngừng phục vụ mà không làm mất khả năng đọc catalog.

### Thiết kế topology

- Region A là primary writer.
- Region B và C giữ asynchronous read replicas.
- Object ảnh được replicate qua storage service theo policy.
- CDN/cache phục vụ nội dung public có TTL phù hợp.
- Mọi update catalog mang version và event ID.

~~~mermaid
flowchart TB
    ADMIN["Catalog admin"]
    PA["Region A\nPrimary catalog"]
    RB["Region B\nRead replica"]
    RC["Region C\nRead replica"]
    CDN["Global CDN/cache"]
    U["Global users"]
    ADMIN --> PA
    PA -->|Async replication| RB
    PA -->|Async replication| RC
    PA --> CDN
    RB --> CDN
    RC --> CDN
    U --> CDN
~~~

### Read/write behavior

Admin write tới Region A. API trả version/operation ID sau commit primary. Nếu user ở Region C đọc ngay sau update, hệ thống có thể:

- Route một số read-after-write session về Region A.
- Đợi replica C đạt version yêu cầu trong một thời gian giới hạn.
- Cho phép stale read trong catalog page nếu user không yêu cầu freshness.

Không để mọi read toàn cầu chờ remote sync; điều đó sẽ phá mục tiêu latency.

### Lag policy

Dashboard theo dõi lag per region. Nếu Region B vượt 60 giây, tạm ngừng route các endpoint cần catalog mới tới replica B hoặc dùng fallback phù hợp. Cache/CDN invalidation có version để tránh phục vụ asset stale vô hạn.

### DR

Nếu Region A mất, đánh giá last applied position ở B/C và RPO thực tế. Chọn một replica để promote, fence A và chuyển writer ownership. Sau phục hồi A, reseed/replicate từ writer mới trước khi failback.

### Tại sao phù hợp?

Catalog có stale tolerance và write rate tương đối thấp. Async replication giúp user đọc gần region, write latency thấp và giảm coupling WAN. Trade-off là update chưa kịp tới replica có thể stale; quy trình read-your-writes và DR xử lý giới hạn đó.

## 26. Case study: booking/payment ledger cần single-writer

Một hệ thống đặt chỗ phục vụ người dùng toàn cầu. Booking và payment ledger có invariant:

- Không xác nhận hai booking cho cùng một slot cuối cùng.
- Một payment operation không được capture hai lần.
- Giao dịch đã xác nhận cần có durability cao.
- User cần xem trạng thái booking sau khi tạo.

### Thiết kế

- Mỗi booking/slot hoặc tenant được gán home region/partition owner.
- Write được route về owner region.
- Ledger dùng database có consistency/durability phù hợp, backup và replica DR.
- Remote region phục vụ read theo consistency policy.
- Payment provider call dùng idempotency key và operation state.
- Event tới analytics/search được replicate bất đồng bộ.

### Luồng tạo booking

1. Request tới edge region và xác thực tenant/user.
2. Control plane xác định home region/partition owner.
3. Booking command được gửi tới owner.
4. Owner kiểm tra availability và thực hiện transaction/conditional write.
5. Payment được gọi với idempotency key; operation state lưu bền vững.
6. Commit ledger/booking theo workflow đã thiết kế.
7. Outbox publish event; projection ở region khác cập nhật bất đồng bộ.
8. User đọc state authoritative hoặc dùng read-your-writes token.

### Khi home region bị partition

Không cho hai region tự nhận write cho cùng slot nếu chưa có fencing/consensus. Hệ thống có thể:

- Từ chối tạm write nhạy cảm.
- Duy trì read-only cho dữ liệu đã có.
- Failover owner sau khi fence primary cũ và đánh giá RPO.
- Ghi operation pending/unknown và reconciliation.

### Vì sao không active–active write cho mọi field?

Hai request ở hai region có thể cùng thấy slot còn trống rồi cùng xác nhận. Eventual replication chỉ phát hiện conflict sau đó, khi side effect/payment có thể đã xảy ra. Single-writer/strongly consistent reservation giữ invariant dễ hơn; những projection như activity feed hoặc analytics vẫn có thể active-active/eventual.

## 27. Case study: multi-region analytics và event pipeline

Một platform thu thập event từ nhiều region để tạo dashboard toàn cầu. Event có tenant ID, event ID, schema version và timestamp; một số field chứa thông tin nhạy cảm.

### Kiến trúc

- Producer ghi event vào regional broker.
- Regional consumer validate schema và publish/replicate sang analytics pipeline.
- Event được dedupe theo event ID.
- Data lake đặt tại region được phê duyệt; global aggregation chỉ lấy field cần thiết.
- Dashboard chấp nhận freshness vài phút.

### Xử lý lag và replay

Nếu WAN link mất, regional broker giữ event trong retention. Khi kết nối trở lại, consumer drain backlog với concurrency giới hạn. Analytics phải idempotent; event có thể đến trễ hoặc lặp, nên aggregate theo event time và dedupe.

### Privacy và residency

Không replicate raw PII sang global warehouse nếu chỉ cần aggregate. Dùng token/pseudonymous key hoặc local aggregation trước khi transfer. Data lineage và deletion tombstone cần theo được tới dataset downstream.

### Trade-off

Eventual consistency phù hợp dashboard không realtime. Có thể chấp nhận lag và replay thay vì block user transaction vì WAN. Tuy nhiên cần quota, retention, backpressure và metric oldest-event-age.

## 28. Bài tập thực hành và đáp án định hướng

Một ứng dụng SaaS chạy ở Region A và B. Có ba dataset:

| Dataset | Workload | Yêu cầu |
| --- | --- | --- |
| Product catalog | 95% read, write ít | Stale tối đa 30 giây |
| Booking inventory | Write cạnh tranh | Không overbook |
| Analytics events | Append-only, dashboard trễ vài phút được | RPO event theo retention và replay |

WAN RTT giữa hai region khoảng 80 ms trong điều kiện bình thường; có lúc packet loss cao và partition ngắn.

### Câu 1 — Có nên dùng synchronous replication cho cả ba dataset?

**Đáp án định hướng:** Không nhất thiết. Catalog có thể dùng async read replica với stale budget 30 giây. Inventory cần authority/consistency chặt, có thể single-writer per partition hoặc strongly consistent transaction. Analytics phù hợp async/eventual với replay.

### Câu 2 — Vì sao inventory không nên chỉ dùng multi-writer eventual replication?

**Đáp án:** Hai region có thể đồng thời xác nhận cùng slot trước khi nhận update của nhau. Conflict resolution sau đó không thể tự đảo side effect đã phát sinh. Cần tuần tự hóa reservation qua owner/quorum/conditional write.

### Câu 3 — Khi replica catalog lag 45 giây, hành vi nào phù hợp?

**Đáp án:** Nó vượt stale budget 30 giây. Không route read freshness-sensitive tới replica đó; route primary/healthy replica hoặc trả degraded/fallback theo policy. Cảnh báo replication pipeline và theo dõi catch-up.

### Câu 4 — Nếu Region A mất, có thể lập tức promote Region B?

**Đáp án:** Chỉ khi xác định failure, fence writer cũ, đo last applied position và quyết định RPO. Nếu A chỉ partition nhưng vẫn ghi được, promotion không có fencing có thể tạo split brain.

### Câu 5 — Sau failover, A phục hồi nhưng có write chưa replicate thì sao?

**Đáp án:** Chọn writer authoritative hiện tại, bảo toàn log/branch của A, đối chiếu operation/ledger và thực hiện reconciliation. Không tự động merge theo timestamp. Rebuild/reseed A từ source authoritative nếu phù hợp.

### Câu 6 — Dashboard analytics có cần block producer khi WAN partition không?

**Đáp án:** Nếu broker/retention có capacity, producer có thể tiếp tục ghi regional event và async ship sau. Cần quota/backpressure và cảnh báo backlog age; không giữ user transaction chờ global dashboard.

### Câu 7 — RPO=0 có thể cam kết cho async replica không?

**Đáp án:** Không thể suy ra như vậy. Async replica có lag; write đã commit ở primary có thể chưa tới remote replica khi failure. Cần guarantee cụ thể từ storage/consensus protocol hoặc chấp nhận RPO khác 0.

### Câu 8 — Data residency ảnh hưởng gì tới active–active?

**Đáp án:** Có thể không được replicate mọi field tới mọi region. Phải phân loại dữ liệu, giới hạn region/processor, cân nhắc regional aggregation và xác định nơi support/backup/log được truy cập.

## 29. Những sai lầm thường gặp

1. **Coi replication là backup:** corruption hoặc delete cũng được sao chép.
2. **Gọi async replication là zero data loss:** lag có thể khiến write gần nhất mất khi failover.
3. **Bật synchronous replication mà không đo WAN RTT:** write latency tăng ngoài budget.
4. **Dùng một consistency level cho mọi dataset:** lãng phí latency hoặc không đủ bảo vệ invariant.
5. **Đọc replica không xét stale budget:** user thấy dữ liệu lùi hoặc trạng thái sai.
6. **Đếm timestamp lag là đủ:** clock skew/idle workload làm metric sai lệch.
7. **Không phân biệt transport lag và apply lag:** xử lý nhầm network khi replica CPU/IO là bottleneck.
8. **Failover không fence primary cũ:** split brain và diverged writes.
9. **Promote replica mà không đánh giá RPO:** mất write đã được xác nhận.
10. **Failback bằng cách đổi DNS:** dữ liệu chưa đồng bộ hoặc writer ownership còn sai.
11. **Merge conflict bằng LWW cho mọi entity:** overwrite nghiệp vụ quan trọng.
12. **Cho mọi region ghi inventory/payment:** invariant không được tuần tự hóa.
13. **Quorum không đi cùng membership/fencing:** hai nhóm có thể nghĩ mình có quyền commit.
14. **Không kiểm tra initial sync:** snapshot gây tải hoặc replica chưa catch up nhưng đã nhận read.
15. **Không reserve capacity DR:** region dự phòng không chịu được peak traffic.
16. **Quên KMS/secret/certificate ở region DR:** dữ liệu có replica nhưng app không đọc được.
17. **Không tính backup, log và analytics trong residency:** dữ liệu rời region qua đường phụ.
18. **Không quan sát per-region lag:** global average che partition chậm.
19. **Replay event không idempotent:** side effect lặp sau network recovery.
20. **Không diễn tập failback:** hệ thống chỉ thử được failover một chiều.

## 30. Checklist review thiết kế replication

- Mục tiêu replication được xác định: DR, read locality, availability hay residency?
- Có phân biệt replication, backup, HA và DR?
- Topology primary–standby, active–passive hay active–active phù hợp access pattern?
- Dataset đã được phân loại theo invariant và stale tolerance?
- Sync/async semantics được xác minh theo guarantee của dịch vụ cụ thể?
- Write acknowledgment có ý nghĩa durable/applied rõ ràng?
- RPO/RTO được owner nghiệp vụ chấp thuận và đo trong drill?
- Có metrics transport/apply/visibility lag theo region pair?
- Read routing có stale budget, read-your-writes và fallback?
- Multi-writer có conflict detection/resolution theo domain rule?
- Entity cần invariant mạnh có single-writer/quorum/transaction phù hợp?
- Ownership registry, epoch/lease và fencing chống split brain?
- WAN RTT, packet loss, bandwidth, egress và initial sync đã được sizing?
- DR region có đủ compute, network, KMS, identity, secret và capacity?
- Failover/failback có runbook, approval và validation?
- Data residency bao gồm primary, replica, backup, logs, analytics và support?
- Event replay/dedupe/outbox có idempotent?
- Deletion/tombstone và backup restore có giữ đúng lifecycle?
- Replication credential, TLS, IAM và audit được giới hạn?
- Có checksum/reconciliation để kiểm tra correctness?
- Có restore, failover, partition và failback drill định kỳ?

## 31. Các chỉ số cần theo dõi

| Nhóm | Chỉ số chính | Mục đích |
| --- | --- | --- |
| Network | RTT, packet loss, retransmits, bandwidth | Đo chất lượng WAN |
| Replication | Lag seconds, LSN/offset gap, apply rate | Biết freshness và catch-up |
| Data correctness | Conflict, checksum mismatch, duplicate | Phát hiện sai lệch |
| Availability | Replica/region health, connection state | Biết khả năng phục vụ |
| Capacity | CPU, IOPS, disk, log retention, egress | Tránh nghẽn |
| Read behavior | Stale response, primary fallback rate | Đánh giá trải nghiệm consistency |
| DR | Actual RPO/RTO, promotion/failback duration | Chứng minh khả năng phục hồi |
| Operations | Unknown operations, reconciliation backlog | Theo dõi giao dịch chưa rõ trạng thái |
| Cost | Storage multiplier, transfer GB, compute-hours | Hiểu TCO |

## 32. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Độ tin cậy** | Replication có đáp ứng RPO/RTO và tránh split brain khi region/network lỗi không? | Lag metrics, fencing, failover/failback drill, reconciliation |
| **Bảo mật** | Bản sao, key, stream và access có tuân thủ least privilege/residency không? | IAM, TLS, KMS, audit, data-flow map |
| **Hiệu năng** | WAN latency và replica lag có nằm trong budget? | RTT, apply throughput, read latency, stale policy |
| **Tối ưu chi phí** | Replication factor, network egress và DR capacity có phù hợp criticality? | Cost per dataset, storage/network/compute model |
| **Vận hành xuất sắc** | Có dashboard, runbook, automation và diễn tập cho lag/failover/failback? | Alert, owner, DR exercise, post-incident review |
| **Tính bền vững** | Dữ liệu nào thật sự cần replicate và giữ bao lâu? | Data classification, minimization, lifecycle, tiering |

Thiết kế sao chép xuyên khu vực cần bắt đầu từ yêu cầu dữ liệu và nghiệp vụ. **Replication topology quyết định nơi ghi/đọc; consistency và acknowledgment quyết định khi nào write được xem là thành công; lag quyết định độ mới và RPO; fencing/conflict policy quyết định tính đúng đắn khi nhiều region hoặc một region lỗi.** Async replication giúp giảm latency và tăng tính độc lập nhưng chấp nhận stale/RPO; sync hoặc quorum tăng durability/consistency nhưng phụ thuộc WAN và có thể giảm availability của write. Chỉ khi có observability, runbook và diễn tập failover/failback, các trade-off này mới trở thành cam kết vận hành có thể kiểm chứng.
