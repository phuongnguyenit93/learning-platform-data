# Đánh giá hội tụ, mất cập nhật và bất biến sau khi lỗi được khắc phục

Một hệ NoSQL phân tán có thể bị phân vùng mạng, mất kết nối tới một replica, leader chuyển vai trò hoặc CDC consumer bị đình trệ. Khi lỗi được khắc phục, các nút có thể hoạt động trở lại và dần đồng bộ dữ liệu. Tuy nhiên, **cùng dữ liệu không có nghĩa dữ liệu đúng**. Nếu hai người dùng cùng tăng bộ đếm từ 0 lên 1 ở hai vùng mạng cô lập, hệ dùng last-write-wins (LWW) có thể chọn một bản khi hợp nhất. Sau đó tất cả replicas đều có giá trị 1, dù hai thao tác tăng độc lập đã được xác nhận thành công.

Với ứng dụng cho thuê, sự khác biệt này đặc biệt quan trọng: hai booking có thể được xác nhận cho một phòng cuối cùng; một payment đã thu nhưng booking bị mất; lệnh hủy bị hồi sinh; dữ liệu search vẫn hiển thị phòng đã hết; hoặc client retry khiến hiệu ứng nghiệp vụ lặp lại. Hệ thống có thể **hội tụ về trạng thái sai** mà dashboard về availability vẫn xanh.

Bài học thuộc chương **Kiểm thử lỗi và tải** trong module **Database No SQL**. Nội dung hướng dẫn thiết kế bài kiểm sau network partition, failover hoặc backlog: định nghĩa hội tụ đúng phạm vi, phân biệt lost update với stale read, đối soát acknowledged intents, đo time-to-converge, kiểm bất biến xuyên các bản ghi/hệ thống, tiêm lỗi có kiểm soát, và lập kết luận có bằng chứng. Một chương trình Java 17 sẽ mô phỏng trực tiếp trường hợp **LWW hội tụ nhưng mất cập nhật**, so với một authority sử dụng CAS/idempotency.

> **Nguyên tắc cốt lõi:** Không kết luận “phục hồi thành công” chỉ vì replica đã online, các nodes trả cùng giá trị hoặc tỷ lệ lỗi API giảm. Phải chứng minh rằng **những thao tác cần được bảo toàn vẫn còn**, **những thao tác không hợp lệ không được áp**, và **các bất biến nghiệp vụ đúng sau recovery**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt phục hồi kết nối, availability, replication convergence và business correctness.
2. Xác định cutoff, keyspace, replica/partition scope và read consistency cho một phép so.
3. Phân biệt tính chất **safety** và **liveness**.
4. Nhận diện lost update qua LWW, blind overwrite, failover, CDC gap và retry.
5. Hiểu điều kiện áp dụng CAS, conditional write, quorum và CRDT.
6. Thu operation history gồm SUCCESS, REJECTED, ABORTED, UNKNOWN.
7. Thiết kế fault injection và workload cạnh tranh cùng key.
8. Đo replication lag, CDC backlog, repair throughput và time-to-converge.
9. Kiểm invariant về tồn kho, thanh toán, version, deletion và tenant isolation.
10. Lập verdict PASS/FAIL/INDETERMINATE cùng runbook điều tra.

## 2. Ví dụ xuyên suốt: booking ở ba vùng lỗi

Giả sử:

~~~text
                         Booking API
                        /     |     \
                     Zone A  Zone B  Zone C
                       |      |      |
                     DB A   DB B   DB C
                        \     |     /
                         Replication
                              |
                             CDC
                              |
                         Search index
~~~

Lúc 10:00, một partition ngăn hai nhóm nodes trao đổi. Trong thời gian lỗi, các writes có thể được chấp nhận, bị chặn hoặc thất bại tùy quorum/leader và consistency contract. Lúc 10:05, mạng thông; các bản sao bắt đầu catch-up. Search còn có thể trễ.

Hãy tách câu hỏi:

- **Đã hết lỗi mạng chưa?**
- **Write API đã đáp ứng SLO chưa?**
- **Các replica đã đến cùng commit position chưa?**
- **Có write nào được ACK nhưng không tồn tại sau heal không?**
- **Nếu có conflicts, chúng được giải quyết đúng luật nghiệp vụ chưa?**
- **Payment, booking và inventory còn nhất quán không?**

Một câu “cluster healthy 3/3” không trả lời những câu còn lại.

## 3. Bốn mốc phục hồi

~~~text
t0  Network/node fault active
       |
t1  Fault healed; connectivity restored
       |
t2  User-facing APIs satisfy latency/error SLO
       |
t3  Relevant replicas/projections caught up
       |
t4  Business reconciliation completed
~~~

| Mốc | Chứng minh gì? | Chưa chứng minh gì? |
| --- | --- | --- |
| t1 | Có thể liên lạc lại | Replica có thể lag |
| t2 | API phục vụ trở lại | Có thể còn missing updates |
| t3 | Dữ liệu hội tụ tới cutoff | Giá trị hội tụ có thể sai |
| t4 | Invariants/accepted effects đã kiểm | Cần tiếp tục giám sát drift |

Tùy hệ thống, t2 xảy ra trước t3; t4 cần đối soát độc lập. **Đừng dừng thử nghiệm ở t1**.

## 4. Safety và liveness

Hai loại yêu cầu:

- **Safety:** điều xấu không xảy ra. Ví dụ một phòng capacity=1 không có hai confirmed bookings, một payment intent không bị charge hai lần.
- **Liveness:** khi các điều kiện vận hành lại phù hợp, công việc cần thiết cuối cùng hoàn thành. Ví dụ replicas bắt kịp dữ liệu, backlog giảm và consumer xử lý các events còn thiếu.

Một hệ có thể giữ safety bằng cách từ chối writes khi mất quorum, đổi lại availability thấp. Một hệ cho phép nhiều vùng ghi cục bộ có thể tiếp tục phục vụ nhưng phải xử lý conflicts. **Bài kiểm cần định nghĩa rõ hợp đồng của từng operation**, không đòi mọi writes thành công dưới mọi partition.

## 5. Định nghĩa hội tụ ở cùng cutoff

Với replicas $R_1, R_2,\ldots,R_n$ cùng chứa logical keyspace và cùng tập operations có hiệu lực đến mốc $W$:

\[
State(R_i,W)=State(R_j,W)
\]

cho các cặp replicas thuộc phạm vi kiểm.

Đây là cách mô tả logical convergence, không có nghĩa thực hiện hai lệnh đọc từ hai thời điểm khác nhau rồi so trực tiếp là đủ. Cần công bố:

- **Keyspace:** tenant, entity type, partitions, shards.
- **Cutoff:** commit position, version hoặc vector watermarks.
- **Read semantics:** primary/quorum/linearizable/eventual/snapshot.
- **Equivalence:** trường nào phải bằng, TTL/deletes và schema mapping.
- **Conflict policy:** LWW, CAS, merge, application resolution.
- **Liveness condition:** workload quiescent hay đang tiếp tục nhận writes?

Hai replicas trả cùng một value trong một lần đọc không đủ chứng minh toàn bộ cluster hội tụ.

## 6. Eventual consistency không tự hứa số giây

Với các hệ eventual consistency, khi không có updates mới và việc trao đổi/repair được bảo đảm theo giả định của thiết kế, các replicas cuối cùng có thể hội tụ. **Không có thời hạn hội tụ cố định được suy ra chỉ từ tên gọi**.

Một SLO do ứng dụng tự đặt có thể là:

~~~text
After fault heals:
  99% eligible source changes visible in search < 10s
  replica repair backlog drained within 20 minutes
  zero critical records unresolved at cutoff
~~~

Các mục tiêu này phải được kiểm với tải thật; chúng không phải mặc định của mọi NoSQL. Nếu một key quan trọng không bao giờ catch-up, một percentile tốt vẫn không làm tình trạng đó trở nên đúng.

## 7. Quiescence và workload không ngừng ghi

Trong bài lab đầu tiên:

~~~text
Seed → Write → Inject fault → Concurrent writes
     → Heal → Stop new writes → Await catch-up
     → Compare replicas and business invariants
~~~

Khi writers dừng, tập operations hữu hạn dễ đối soát hơn. Đây là **quiescent test**.

Trong production, writes thường không dừng. Vì vậy cần snapshot/commit cutoff và **per-partition applied watermarks**, loại các events sau cutoff khỏi so sánh. Một hệ đang ghi mới liên tục không nhất thiết cho hai lần đọc lệch vài giây có cùng state.

## 8. Commit position không đồng nghĩa wall-clock

Ví dụ:

~~~text
businessTime       10:00:00
sourceCommitTime   10:00:03
cdcObservedTime    10:00:05
targetAppliedTime  10:00:07
queryVisibleTime   10:00:08
~~~

`createdAt` của nghiệp vụ có thể khác thứ tự commit. Client clock lệch có thể khiến timestamps không phản ánh quan hệ nhân quả.

Ưu tiên:

- Source commit sequence/CDC resume position khi có guarantee.
- Aggregate version monotonic theo authority.
- Vector positions cho các streams nhiều partitions.
- Monotonic clock để đo elapsed time trong cùng process.
- UTC timestamps để correlation, nhưng ghi nhận clock skew.

## 9. Vector watermarks

Một source có ba partitions:

~~~text
Required cutoff:
  P0=100, P1=200, P2=300

Target applied:
  P0=120, P1=199, P2=350
~~~

Target **chưa caught up** vì P1 thiếu một event. Không dùng maximum offset 350 để tuyên bố mọi partition đã đồng bộ.

Kiểm thêm:

- Offset được ghi sau **durable apply**, không chỉ nhận message.
- Có gap hoặc partition không được subscribe không?
- Consumer xử lý duplicate/out-of-order events thế nào?
- Snapshot watermark nối với CDC có khoảng trống không?
- Poison events trong DLQ đã xử lý hay bị skip?

Không phải mọi provider dùng offset dạng số như ví dụ; áp semantics của đúng stream.

## 10. Stale read khác lost update

~~~text
Replica A: version=9
Replica B: version=8
~~~

Nếu B đang bắt kịp và hệ cho phép eventual reads, đây có thể là **stale read tạm thời**, không chứng minh update mất vĩnh viễn.

Ngược lại:

~~~text
Replica A: count=1
Replica B: count=1
ACKed unique increments: 2
~~~

Hệ đã hội tụ nhưng một increment có thể đã mất.

**Chỉ sau khi đọc đúng cutoff/consistency contract và đối soát operation IDs mới có thể kết luận.**

## 11. Lost update: các nguyên nhân phổ biến

| Cơ chế | Ví dụ | Cách phát hiện |
| --- | --- | --- |
| Read-modify-write race | Hai clients đọc v7 rồi cùng ghi v8 | Version/CAS history |
| LWW conflict | Hai regions ACK hai values | Conflict/intent log |
| Failover rollback | Write ACK ở mức không đủ durable | Election/write concern |
| CDC gap | Event commit không có ở target | Per-partition watermark/diff |
| Out-of-order apply | Event v7 thắng v9 | Version guard |
| Blind restore | Snapshot v7 đè production v9 | Conditional repair manifest |
| Delete resurrection | Replica cũ đẩy record đã xóa | Tombstone/TTL audit |
| Duplicate retry | Một business intent bị apply hai lần | Idempotency key |

Không tự coi mọi hiện tượng là bug database. Database có thể làm đúng LWW contract nhưng contract đó không phù hợp yêu cầu giữ mọi incremental business effect.

## 12. Ví dụ: LWW hội tụ nhưng mất increment

Hai replicas cùng bắt đầu `counter=0`. Trong partition:

~~~text
Replica A:
  req-A reads 0 → writes 1 → ACK

Replica B:
  req-B reads 0 → writes 1 → ACK

After heal:
  LWW chooses B's snapshot
  both replicas store count=1
~~~

Kết luận:

~~~text
Converged state?        YES
ACKed distinct intents? 2
Required increment sum? 2
Final stored count?     1
Business correctness?   FAIL
~~~

Nếu ứng dụng dùng register với yêu cầu LWW, việc bỏ một giá trị cạnh tranh có thể là đúng API. Nhưng nếu clients tin rằng hai increments độc lập **đều được bảo toàn**, business contract đã bị vi phạm. **Convergence và intent preservation là hai assertions riêng**.

## 13. LWW và clock skew

Giả sử Region A có đồng hồ đi trước:

~~~text
Region A timestamp 10:05:10 → write X
Region B timestamp 10:05:03 → write Y later in real time
~~~

Nếu cơ chế conflict chọn timestamp lớn nhất từ client clocks, X có thể thắng Y dù Y xảy ra sau theo thời gian thực.

Các câu hỏi:

- Timestamp do server hay client tạo?
- Engine có hybrid logical clock hoặc causal metadata không?
- Với timestamps bằng nhau, tie-breaker là gì?
- Hai updates có concurrent hay causally ordered?
- Cần cho user chọn field-by-field merge không?

Không suy “last writer” có nghĩa “người thực hiện sau theo ý nghĩa nghiệp vụ”.

## 14. CAS, optimistic concurrency và giới hạn

Mô hình:

~~~text
Read version 7
Compute updated state
Write IF current.version == 7

Success → version 8
Conflict → re-read and re-evaluate
~~~

CAS trên authority tránh việc một writer im lặng ghi đè thay đổi mới của writer khác. Tuy vậy:

- Check và mutation phải là **một atomic database operation**.
- Mọi writers liên quan phải cùng tuân protocol.
- CAS một document không tạo transaction xuyên documents.
- CAS thực hiện ở **hai regions độc lập** vẫn có thể conflict sau replication nếu product cho phép local writes.
- Timeout có thể là UNKNOWN, không phải automatically rejected.

## 15. CRDT và các thao tác có thể hợp nhất

Với grow-only counter (G-Counter), mỗi replica có một component:

~~~text
A component = 3
B component = 4

Merge: component-wise maximum
Read: 3 + 4 = 7
~~~

Merge cần có tính **associative, commutative, idempotent**. Không cộng hai total counters một cách ngây thơ vì có thể nhân đôi events đã được replicate.

### Ranh giới nghiệp vụ

G-Counter có thể bảo toàn increments và hội tụ, nhưng không tự bảo đảm **không oversell** trong hệ có hard capacity=1. Hai vùng có thể cùng cấp một booking cục bộ. Cần authority/quorum/escrow hoặc protocol khác để bảo vệ bất biến giới hạn.

## 16. Vector versions và causal conflicts

Một số thiết kế lưu causal metadata:

~~~text
Version A: [zoneA:4, zoneB:2]
Version B: [zoneA:3, zoneB:3]
~~~

Không vector nào trội hoàn toàn vector kia; có khả năng đây là concurrent updates. Thay vì tự chọn winner bằng clock, hệ có thể expose conflict để domain merge.

Không giả định mọi NoSQL có vector clocks. Scalar aggregate version thường đủ cho một authority key; vector metadata chỉ hữu ích khi data model và API hỗ trợ.

## 17. Deletes và data resurrection

~~~text
10:00 Replica A holds voucher V1
10:01 Replica B receives DELETE V1
10:02 Network heals
10:03 Replica A streams old V1
~~~

Hệ phải tuân deletion/tombstone/TTL semantics để bản cũ không hồi sinh ngoài ý muốn.

Nguy cơ:

- Tombstone bị dọn sớm so với repair window.
- Một replica offline quá lâu.
- Restore backup cũ với unconditional overwrite.
- Delete event thiếu trong CDC.
- TTL expiration/clock skew.
- Cache chưa invalidated.

Nếu dữ liệu phải xóa theo privacy hoặc retention policy, **resurrection là sai nghiệp vụ dù replicas đã hội tụ**.

## 18. Sau heal, còn nhiều công việc

~~~text
Network healed
  |
  +→ leader/quorum stabilization
  +→ pending replication delivery
  +→ repair/stream missing segments
  +→ conflict resolution
  +→ compaction/tombstone reconciliation
  +→ CDC/search/cache catch-up
  +→ accepted intent reconciliation
  +→ business invariant verification
~~~

Không phải mọi hệ có hinted handoff, Merkle repair hay transaction log giống nhau. Trạng thái node `UP` không chứng minh tất cả các pha hoàn thành.

## 19. Backlog và tốc độ drain

Giả sử:

~~~text
Backlog after fault:       600,000 events
New writes arriving:        1,000 events/s
Consumer apply capacity:    1,200 events/s
~~~

\[
NetDrainRate=1200-1000=200\;\mathrm{events/s}
\]

\[
DrainTime=\frac{600000}{200}
=3000\;\mathrm{s}=50\;\mathrm{minutes}
\]

Nếu consumer chỉ xử lý 900 events/s trong khi nhận 1.000/s thì backlog **tiếp tục tăng** sau heal. Các phép tính chỉ là ước lượng với rates ổn định, events có chi phí giống nhau và không có retries/poison records.

**Sustained apply throughput, không phải burst throughput vài giây**, quyết định khả năng bắt kịp.

## 20. Capacity recovery và tác động SLO

Ví dụ stream 1 TiB trong hai giờ:

\[
RequiredRate\approx\frac{1024\times1024\;\mathrm{MiB}}{7200\;\mathrm{s}}
\approx146\;\mathrm{MiB/s}
\]

Tương đương khoảng 1,22 Gbps payload, chưa gồm protocol overhead, read/write disk traffic và client requests.

Khi repair:

- Disk IOPS/throughput tăng.
- CPU nén, checksum, serialization tăng.
- Network congestion có thể xảy ra.
- Cache bị đẩy khỏi RAM.
- Foreground p95/p99 có thể xấu đi.

Không để repair chiếm mọi tài nguyên khiến hệ mất user SLO; cần rate limits và recovery budget theo mục tiêu.

## 21. Các mốc thời gian phải ghi

~~~text
t_fault_start
t_heal_confirmed
t_quorum_healthy
t_api_slo_recovered
t_replica_cutoff_reached
t_search_cutoff_visible
t_business_verified
~~~

\[
TimeToReplicaConverge=
t_{\mathrm{replica\_cutoff\_reached}}
-t_{\mathrm{heal\_confirmed}}
\]

\[
TimeToBusinessRecovery=
t_{\mathrm{business\_verified}}
-t_{\mathrm{heal\_confirmed}}
\]

Đo theo mốc khác (incident detection hoặc fault start) cũng được nếu **công bố rõ định nghĩa**, tránh so những con số khác nhau về điểm bắt đầu.

## 22. SLI/metrics cần theo dõi

| Nhóm | Metrics/evidence |
| --- | --- |
| Quorum/replicas | Membership, leader, per-replica lag |
| Repair | Pending ranges/hints/streaming bytes |
| CDC | Per-shard offsets, oldest event age, DLQ |
| Search | Source-commit-to-visible lag |
| Storage | Disk IOPS/throughput, compaction, available space |
| CPU/network | Saturation, retransmits, cross-zone throughput |
| User-facing | Request rate, p95/p99 latency, error ratio |
| Correctness | Missing/extra keys, value/version mismatches |
| Intents | ACKed, rejected, unknown, duplicate effects |
| Domain | Booking/ledger/tenant invariant violations |

Một dashboard `lag=0` có thể sai nếu consumer bỏ sót một partition hoặc checkpoint trước khi durable apply. Cần xác minh per-partition completeness.

## 23. Kiểm bất biến booking

Với một phòng capacity=1 vào một ngày:

\[
\sum_{b\in Confirmed(room,date)}units(b)\le1
\]

Sau partition có thể:

~~~text
Region A: Booking B101 confirmed
Region B: Booking B102 confirmed
After heal: inventory register says available=0
~~~

Counter có thể khớp ở mọi replica nhưng có **hai xác nhận**. Oracle cần:

- Full room/date/tenant key.
- Booking statuses và accepted intent IDs.
- Inventory allocation records.
- Holds, expirations và cancellations.
- Payment/notification effects liên quan.
- Conflict compensation nếu đã hứa với hai khách.

Không chỉ xem một field `available` rồi kết luận no-double-booking.

## 24. Kiểm payment và ledger

Một giao dịch chuyển 100 đơn vị:

~~~text
Debit A 100
Credit B 100
~~~

Nếu được bảo vệ bởi transaction/invariant theo contract:

\[
TotalDebits=TotalCredits
\]

Tuy nhiên, tổng bằng nhau vẫn có thể che **một transaction mất và một transaction thừa cùng số tiền**. Cần:

- Per-transaction ID uniqueness.
- Currency/minor unit precision.
- No double capture/refund for one intent.
- Booking–payment reconciliation.
- Effects sau retries/CDC duplicates.
- External payment authority evidence.

Không lấy event count làm bằng chứng mọi payment side effect đúng.

## 25. State-machine, version và idempotency

Một booking:

~~~text
PENDING(v1) → CONFIRMED(v2) → COMPLETED(v3)
                 |
                 +→ CANCELLED(v3)
~~~

Sau fault:

- Event cũ không được ghi đè version mới trái protocol.
- Một intent retry không tạo booking thứ hai.
- Không gửi lại charge/email/loyalty award nếu side effect đã xảy ra.
- Một DELETE hợp lệ không bị phục hồi ngoài ý muốn.
- Một `BookingRestored` không bị coi như business booking mới.

**Final state hash** không thay được kiểm operation history và external side effects.

## 26. Tenant isolation

Hai tenants có thể cùng display reservation ID:

~~~text
tenant:T1/reservation:R101
tenant:T2/reservation:R101
~~~

Manifest và reconciliation phải dùng **full authoritative business key**, không chỉ `R101`. Một repair script ghép sai tenant có thể làm rò dữ liệu dù số lượng và hashes theo kiểu sai vẫn khớp.

Kiểm network/access routing, CDC tenant filters, authorization, secure logs và sự tồn tại của cross-tenant records sau failover.

## 27. Đối soát theo nhiều tầng

~~~text
Connectivity
    |
Replica/partition watermark
    |
Exact keyset and canonical values
    |
ACKed-intent versus committed-effect history
    |
Business invariants
~~~

Một count match không đủ:

~~~text
Source keys: A,B,C
Target keys: A,B,D
~~~

Cả hai count=3 nhưng C missing, D extra. Tương tự, các replicas có thể chứa **cùng một record sai**. Phải kiểm cả identity, values và domain rules.

## 28. Canonical comparison và bucket hash

Để so replicas/target:

- Dùng full key và tenant.
- Chuẩn hóa logical fields (không chỉ raw JSON string).
- Giữ numeric precision, units, null/missing semantics.
- Chuẩn hóa instant/timezone theo contract.
- Không sort arrays nếu thứ tự mang nghĩa.
- So versions, TTL và tombstones.
- Không log PII/secrets để debug hashes.

Với dữ liệu lớn, chia theo `hash(fullBusinessKey) mod N`, tính exact counts và deterministic digests trên sorted key/value pairs; drill down buckets bị lệch. Một XOR hash không đủ nếu duplicates có thể triệt tiêu.

**Hash equality không chứng minh dữ liệu đúng nghiệp vụ**, chỉ giúp kiểm representation đã chọn.

## 29. Lưu operation history

~~~json
{
  "runId": "fault-561",
  "operationId": "op-101",
  "intentId": "reserve-B101",
  "clientId": "writer-A",
  "fullKey": "T1/R1/2026-11-20",
  "kind": "RESERVE",
  "invokedAtMonoNs": 1000000,
  "completedAtMonoNs": 2400000,
  "result": "SUCCESS",
  "reportedVersion": 8,
  "faultPhase": "partition-active"
}
~~~

Một request timeout:

~~~json
{
  "operationId": "op-102",
  "intentId": "reserve-B102",
  "result": "UNKNOWN",
  "errorCategory": "RESPONSE_TIMEOUT"
}
~~~

Không chỉ log exception text. Cần thời điểm invoke/complete, read/write concern, retry count, region, session và stable intent IDs tùy API.

## 30. SUCCESS, REJECTED, ABORTED, UNKNOWN

| Kết quả | Ý nghĩa cần kiểm |
| --- | --- |
| SUCCESS | API đã xác nhận theo consistency/durability contract |
| REJECTED | Condition/validation từ chối rõ ràng |
| ABORTED | Transaction được xác nhận không commit |
| UNKNOWN | Server có thể đã commit nhưng response mất |

Timeout sau commit không phải abort. Nếu retry bằng **ID khác**, một intent có thể tạo hai effects mặc dù từng write nguyên tử.

Một checker đúng có thể trả `INDETERMINATE` khi chưa đủ evidence.

## 31. Điểm tiêm lỗi phải có ý nghĩa

~~~text
Client → Coordinator → Replica
   |          |            |
   |          +→ ACK       +→ Peer replication
   |
   +→ CDC consumer → Search
~~~

Các faults:

1. Drop request trước khi server nhận.
2. Reset socket khi request in-flight.
3. Drop ACK sau khi server commit.
4. Ngắt replica→replica link.
5. Tạo partition giữa zones/regions.
6. Kill leader trong lab được phép.
7. Throttle disk/network/CPU để làm chậm repair.
8. Pause CDC, reorder/duplicate events trong test harness.

Không mô tả client-side socket reset là nội bộ quorum partition; scope hai phép thử khác nhau.

## 32. Ma trận fault × correctness

| ID | Fault/scenario | Oracle sau heal |
| --- | --- | --- |
| F1 | Một replica offline | Catch-up đúng cutoff |
| F2 | Partition giữa zones | Quorum/authority policy đúng |
| F3 | Leader crash sau ACK | Durable writes còn theo contract |
| F4 | ACK lost sau commit | Idempotency, unknown resolution |
| F5 | Hai writers đọc same version | Không silent lost update nếu CAS |
| F6 | Multi-region concurrent same-key writes | Conflict policy và business preservation |
| F7 | CDC pause | Backlog drain/freshness |
| F8 | Duplicate CDC delivery | Không double business effects |
| F9 | Out-of-order events | Version monotonic |
| F10 | Tombstone delayed | Không data resurrection |
| F11 | TTL expire trong partition | Lifecycle đúng |
| F12 | Repair dưới hot-key peak | Tail latency và converge SLO |
| F13 | Restore old backup | Không overwrite valid new writes |
| F14 | Search rebuild | Logical mapping/cutoff |
| F15 | Cross-region routing failover | Không split-brain booking |
| F16 | Clock skew | Conflict resolution được hiểu đúng |

Luôn ghi engine/version/topology và documented guarantees để chọn expected results.

## 33. Workload cạnh tranh thực

~~~text
Low contention:
  100,000 requests on 100,000 keys

High contention:
  10,000 requests on 10 keys
  with one heavily accessed key
~~~

Muốn tìm lost-update race, cần **concurrent writers cùng key** với barrier/random schedule, không chỉ tổng QPS lớn. Chạy nhiều vòng, giữ random seed, ghi offered load/throughput/errors.

Một load generator closed-loop có thể giảm arrival rate khi server chậm; nếu cần đo burst thật, phải hiểu open-loop/closed-loop và tránh coordinated omission.

## 34. Ba pha test

### Baseline

1. Ghi database product/version, RF, topology, consistency settings.
2. Nạp dataset đại diện và known versions.
3. Kiểm invariant ban đầu.
4. Chạy workload không lỗi để đo p99/lag baseline.
5. Xác minh history/watermark collection.

### Fault active

1. Tiêm lỗi có quyền và giới hạn.
2. Tiếp tục concurrent writes/reads theo policy.
3. Ghi SUCCESS/REJECTED/UNKNOWN.
4. Ghi quorum/leader/CDC/lag.
5. Không âm thầm bỏ các requests bị timeout.

### Heal/verify

1. Gỡ fault và xác minh thực sự đã heal.
2. Quiesce test scope hoặc chọn common watermark.
3. Chờ per-partition catch-up với deadline hợp đồng.
4. So keys, values, versions và accepted intents.
5. Chạy domain invariant validators.
6. Đo recovery timeline.
7. Báo PASS/FAIL/INDETERMINATE với evidence.

## 35. Khi nào PASS, FAIL, INDETERMINATE?

| Verdict | Điều kiện |
| --- | --- |
| PASS | Tất cả assertions trong contract có bằng chứng đạt |
| FAIL | Có evidence vi phạm documented guarantee/invariant |
| INDETERMINATE | Thiếu watermark, còn critical UNKNOWN/conflict |
| INVALID_TEST | Fault sai scope, setup sai, oracle không hợp lệ |

Một sai lệch nhỏ trong historical analytics projection có thể có policy cho phép trì hoãn, nhưng double charge/cross-tenant leak/no-oversell thường cần zero tolerance. Không nới pass criteria hậu nghiệm chỉ để được màu xanh.

## 36. Java 17: mô phỏng hội tụ và lost update

Lab sau không cần database thật. Phần đầu mô phỏng hai replicas độc lập chấp nhận increments trong partition, sau đó LWW chọn một snapshot. Phần hai minh họa một **authority duy nhất trong JVM** sử dụng CAS để giữ cả hai intents và tránh retry nhân đôi.

Tạo file `ConvergenceLostUpdateLab.java`:

~~~java
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicReference;

public final class ConvergenceLostUpdateLab {
    record ReplicaSnapshot(
            long timestamp,
            int count,
            Set<String> acceptedIds) {}

    static ReplicaSnapshot localAccept(
            ReplicaSnapshot before,
            String requestId,
            long timestamp) {
        Set<String> ids = new HashSet<>(before.acceptedIds());
        ids.add(requestId);
        return new ReplicaSnapshot(
                timestamp,
                before.count() + 1,
                Set.copyOf(ids));
    }

    static ReplicaSnapshot mergeLww(
            ReplicaSnapshot a,
            ReplicaSnapshot b) {
        return a.timestamp() >= b.timestamp() ? a : b;
    }

    record AuthorityState(
            long version,
            int count,
            Set<String> processedIds) {}

    enum Result { APPLIED, ALREADY_APPLIED }

    static final class OneAuthority {
        private final AtomicReference<AuthorityState> state =
                new AtomicReference<>(
                        new AuthorityState(0, 0, Set.of()));

        Result increment(String requestId) {
            for (;;) {
                AuthorityState before = state.get();
                if (before.processedIds().contains(requestId)) {
                    return Result.ALREADY_APPLIED;
                }
                Set<String> ids =
                        new HashSet<>(before.processedIds());
                ids.add(requestId);
                AuthorityState after = new AuthorityState(
                        before.version() + 1,
                        before.count() + 1,
                        Set.copyOf(ids));

                if (state.compareAndSet(before, after)) {
                    return Result.APPLIED;
                }
                // Retry after reading the latest state.
            }
        }

        AuthorityState read() {
            return state.get();
        }
    }

    public static void main(String[] args)
            throws Exception {
        ReplicaSnapshot initial =
                new ReplicaSnapshot(0, 0, Set.of());

        // Simulate two independent ACKed writes during
        // a partition, both based on the old state.
        ReplicaSnapshot a =
                localAccept(initial, "req-A", 10);
        ReplicaSnapshot b =
                localAccept(initial, "req-B", 11);

        ReplicaSnapshot finalA = mergeLww(a, b);
        ReplicaSnapshot finalB = mergeLww(a, b);
        int acknowledgedUniqueIntents = 2;

        System.out.println(
                "LWW converged=" + finalA.equals(finalB));
        System.out.println(
                "LWW count=" + finalA.count());
        System.out.println(
                "LWW acceptedIntents="
                    + acknowledgedUniqueIntents);
        System.out.println(
                "LWW noLostUpdate="
                    + (finalA.count() == acknowledgedUniqueIntents));

        OneAuthority authority = new OneAuthority();
        ExecutorService pool =
                Executors.newFixedThreadPool(2);
        CountDownLatch go = new CountDownLatch(1);
        try {
            Future<Result> first = pool.submit(() -> {
                go.await();
                return authority.increment("req-A");
            });
            Future<Result> second = pool.submit(() -> {
                go.await();
                return authority.increment("req-B");
            });
            go.countDown();
            first.get();
            second.get();

            AuthorityState result = authority.read();
            System.out.println(
                    "CAS count=" + result.count());
            System.out.println(
                    "CAS uniqueIds="
                        + result.processedIds().size());
            System.out.println(
                    "CAS retry="
                        + authority.increment("req-A"));
            System.out.println(
                    "CAS noLostUpdate="
                        + (result.count() == 2
                        && result.processedIds().size() == 2));
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ConvergenceLostUpdateLab.java
java ConvergenceLostUpdateLab
~~~

Kết quả minh họa:

~~~text
LWW converged=true
LWW count=1
LWW acceptedIntents=2
LWW noLostUpdate=false
CAS count=2
CAS uniqueIds=2
CAS retry=ALREADY_APPLIED
CAS noLostUpdate=true
~~~

### Giải thích

Hai replicas có cùng snapshot sau LWW, nhưng một increment không tồn tại trong count. CAS của một authority duy nhất chấp nhận hai intents riêng, đồng thời retry cùng ID không cộng thêm. Nếu bài toán có capacity=1, authority phải **từ chối intent thứ hai theo predicate**, không dùng counter không giới hạn.

### Giới hạn

- Đây là Java in-memory simulation, **không phải NoSQL distributed engine**.
- `AtomicReference` chỉ bảo vệ một JVM, không durable sau crash.
- Một authority có thể từ chối writes khi unreachable; tradeoff khác với local multi-region writes.
- LWW thực tế có conflict/timestamp/tie-breaker semantics riêng theo engine.
- Không mô phỏng I/O, repair, leader election hoặc external side effects.
- Không dùng lab thay bài kiểm trên triển khai NoSQL thật.

## 37. Mở rộng Java lab

1. Thêm replica C và nhiều writes.
2. Chạy merge theo các thứ tự khác nhau.
3. Thêm một G-Counter có component theo replica.
4. Chứng minh merge idempotent trước duplicate delivery.
5. Thêm retries cùng business intent ID.
6. Thêm `stockLimit=1` và thử hai regions cùng reserve.
7. So state convergence với hard-capacity invariant.

Mục đích là nhận ra **mỗi data type/conflict policy cần một oracle riêng**; không có một phép “merge cho bằng nhau” phù hợp mọi nghiệp vụ.

## 38. MongoDB: replica set và rollback

Với MongoDB, bài thử cần ghi write concern, read concern, topology và election state.

### Kịch bản

1. Ghi known booking IDs khi cluster healthy.
2. Inject partition/leader failover trong staging được phép.
3. Tiếp tục writes với consistency setting đã xác định.
4. Thu set ACKed operations theo write concern.
5. Sau heal, readback từ authority theo phù hợp mode.
6. Kiểm writes được cam kết durable còn tồn tại.
7. Kiểm change streams, versions, transactions và rollback evidence.

Một secondary trả stale version **không chứng minh permanent lost write**. Ngược lại, một write ACK theo mức yếu hơn không có cùng durability guarantee với write được majority-acknowledged trong điều kiện thích hợp.

## 39. Cassandra: consistency levels và anti-entropy

Cassandra cần phân biệt:

- RF, placement và read/write consistency levels.
- Hinted handoff và anti-entropy repair.
- Tombstone/TTL/compaction.
- LWW timestamp conflicts.
- LWT nếu business cần CAS trong phạm vi hỗ trợ.
- Partition-level/hot-key behavior.

~~~text
Seed dataset
→ Isolate one replica
→ Write with known CL
→ Heal
→ Observe hints/repair
→ Read at agreed CL/cutoff
→ Verify missing/extra/values/deletes
→ Validate business invariants
~~~

Hints không thay đầy đủ repair. Không so raw SSTable record count với logical live rows, vì tombstones/TTL có thể tồn tại vật lý nhưng không còn hiển thị. Không chỉnh `gc_grace_seconds` trong production chỉ để ép một test pass.

## 40. DynamoDB: Global Tables và concurrent writes

Với DynamoDB Global Tables, phải xác định **loại bảng, replication/consistency mode và phiên bản chính sách** đang áp dụng. Các writes same-item ở nhiều regions có thể cần conflict resolution theo contract. Một conditional update được thực hiện nội vùng chưa chắc bảo vệ **global invariant** khi hai regions đồng thời nhận writes cục bộ.

Test cần:

- Region nào ACK từng intent?
- Những actions nào có conditional/transaction guarantee?
- Có conflicting versions khi heal không?
- Streams/shards đã được áp qua watermark chưa?
- Final item có bảo toàn business intents không?
- Có double booking hoặc missed payment event không?

Không áp một kết luận LWW chung cho mọi offering/mode mà chưa xác minh sản phẩm.

## 41. Redis: asynchronous replication và failover

Redis `INCR` là atomic command trong phạm vi instance, nhưng failover/durability là vấn đề khác.

- Master có thể ACK trước khi replica nhận write theo replication mode.
- Failover sang replica lag có nguy cơ mất write theo contract.
- Client timeout rồi retry `INCR` có thể double increment.
- TTL và cache invalidation có thể tạo stale values.
- Redis Cluster multi-key operations có hash-slot constraints.

Nếu Redis là cache, thường cần rebuild từ authority và đo cache freshness/stampede. Nếu Redis là primary store, phải kiểm persistence/replica policy và recovery guarantees. `WAIT` hoặc một replica acknowledgment **không đồng nghĩa durability tuyệt đối dưới mọi lỗi**.

## 42. Search/CDC: đối soát theo projection

Source:

~~~text
Listing L1 PUBLISHED → searchable
Listing L2 DRAFT     → excluded
Listing L3 DELETED   → removed
~~~

Source có ba records nhưng search chỉ một document có thể đúng. Sau partition, CDC có thể lag, bỏ event, gửi duplicate hoặc out-of-order; search bulk indexing có thể có per-item failures.

**Oracle:** tạo expected projection từ source tại cutoff W rồi so IDs, fields, phiên bản, deletion và freshness theo mapping. Không lấy raw count nguồn bằng search count làm điều kiện bắt buộc khi projection khác shape.

## 43. Managed NoSQL: giới hạn của fault injection

Một provider managed có thể không cho thao tác trực tiếp nodes/quorum. Khi đó:

- Test client→DB network failures qua proxy được phép.
- Test consumer pause/restart và application retries.
- Sử dụng provider-supported failover drills.
- Dùng sandbox để mô phỏng multi-region conflicts.
- Ghi rõ test network client **không tương đương** internal replica partition.
- Đối chiếu product documentation cho những guarantees không thể fault-test trực tiếp.

Không tiêm destructive faults lên production nếu chưa có quyền, guardrail, cleanup và rollback plan.

## 44. Repair có thể gây lost update mới

~~~text
Source backup: Booking R101 version 7
Target live:   Booking R101 version 9
Repair:        unconditional replace from backup v7
~~~

Sau “sửa”, target có thể giống bản backup nhưng **mất v9 hợp lệ**.

Quy trình an toàn:

1. Xác định authority và cutoff.
2. Phân loại missing/extra/value/version conflicts.
3. Lập dry-run manifest, provenance và approval.
4. Giữ legitimate post-snapshot writes.
5. Dùng conditional update/CAS hoặc unique insert.
6. Không hồi sinh TTL/legitimate deletes.
7. Canary rồi mới batch lớn.
8. Theo dõi CDC/payment/booking side effects.
9. Rerun reconciliation và ghi unresolved cases.

**Repair phải bảo vệ dữ liệu đúng đang sống**, không chỉ ép các bản sao có cùng bytes.

## 45. Mẫu acceptance gate

~~~yaml
experiment: "post-fault-convergence"
scope:
  entities: ["Booking", "Inventory", "Payment"]
  cutoff: "documented per-partition watermark"
  regions: ["A", "B", "C"]
acceptance:
  criticalMissingAcknowledgedWrites: 0
  duplicateBusinessEffects: 0
  inventoryInvariantViolations: 0
  paymentInvariantViolations: 0
  tombstoneResurrections: 0
  unresolvedCriticalUnknownOutcomes: 0
  replicaConvergence: "within agreed objective"
  searchFreshness: "within agreed SLO"
evidence:
  operationHistories: "required"
  sourceTargetWatermarks: "required"
  reconciliationManifest: "required"
  domainOwnerSignoff: "required"
~~~

Đây là hợp đồng test minh họa, không phải cấu hình mặc định của một công cụ. Các ngưỡng cần được sản phẩm/đội vận hành phê duyệt **trước test**, không nới sau khi gặp lỗi.

## 46. Mẫu báo cáo một thí nghiệm

~~~text
Run ID: fault-561-01
Fault: replica link partitioned
Fault duration: 10 minutes
Heal confirmed: 10:10:00 UTC
Quorum healthy: 10:10:20
Replica cutoff reached: 10:13:40
Search cutoff visible: 10:15:10
Domain verification done: 10:15:50

ACKed unique intents:        1,150,000
Rejected intents:               50,000
Unknown outcomes:                  200
Unknowns reconciled:               199
Unresolved unknowns:                 1
Missing critical effects:            0
Duplicate business effects:          0
Inventory invariant failures:        0
Payment invariant failures:          0
Data resurrections:                  0

Verdict: INDETERMINATE
Reason: one critical unknown outcome unresolved
Owner: Booking platform on-call
~~~

Các con số là giả định. Một unresolved critical payment/booking intent không được biến thành PASS chỉ vì replicas đã catch-up.

## 47. Runbook: replicas không hội tụ

1. Xác minh fault đã thực sự được khắc phục.
2. Kiểm leader/quorum/membership/routing.
3. Ghi RF/topology/consistency settings.
4. Chọn common cutoff.
5. Kiểm per-node/per-shard lag, hints và repair progress.
6. Kiểm disk IOPS, compaction, CPU và network capacity.
7. Kiểm CDC gaps/DLQ/missing partitions.
8. So affected full keys, values, versions và tombstones.
9. Phân biệt lag tạm thời với conflict vĩnh viễn.
10. Thực hiện repair theo đúng engine contract.
11. Revalidate source/target and business invariants.
12. Ghi RCA và regression test.

Không chỉ tăng read consistency trong một lần đọc rồi kết luận replica đã bắt kịp.

## 48. Runbook: hội tụ nhưng mất cập nhật

1. Xuất ACKed business intent IDs.
2. Đối soát với durable committed effects ở authority.
3. Kiểm retries/UNKNOWN outcomes.
4. Kiểm read-modify-write không có CAS.
5. Kiểm LWW timestamps và clock skew.
6. Kiểm failover write concern và rollback.
7. Kiểm CDC gap/out-of-order.
8. Phân loại conflict có thể merge vs cần compensation.
9. Repair có CAS/approval, không unconditional overwrite.
10. Rerun cùng fault dưới concurrent workload.

Nếu LWW thực hiện đúng contract nhưng business yêu cầu giữ mọi increments, cần đổi **data model/authority/conflict protocol**, không chỉ chờ lâu hơn.

## 49. Runbook: business invariant sai sau recovery

1. Giới hạn critical write path nếu tác hại còn tiếp diễn.
2. Xác định source of truth và đọc theo mode phù hợp.
3. Bảo vệ histories/IDs/versions/evidence.
4. Kiểm confirmed bookings, inventory và payment ledger.
5. Kiểm duplicate side effects, deletes và tenant mixing.
6. Phân biệt lỗi từ trước fault và lỗi do recovery.
7. Xây compensation/refund/rebooking được domain owner duyệt.
8. Áp conditional repair/transaction đúng boundary.
9. Rebuild/reconcile search/cache/CDC nếu cần.
10. Verify lại invariants, freshness và owner signoff.

Đừng chỉ sửa một counter cho khớp nếu business records vẫn có hai lời hứa trái nhau.

## 50. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Phương án |
| --- | --- | --- |
| Node xanh = phục hồi xong | Replicas chưa bắt kịp | Đo mốc t1–t4 |
| Replicas bằng nhau = đúng | LWW có thể mất update | So intents và invariant |
| `sleep(5s)` là convergence check | Không có cutoff/evidence | Watermarks + deadline |
| Timeout đồng nghĩa abort | Commit ACK có thể mất | UNKNOWN + reconciliation |
| LWW giữ mọi increments | Một version thắng | CAS/CRDT/domain merge |
| Timestamp lớn hơn luôn đúng | Clock skew | Causal/version semantics |
| CAS nội vùng bảo đảm toàn cầu | Multi-region conflicts | Global authority protocol |
| CRDT counter ngăn oversell | Không enforce hard cap | Escrow/quorum/authority |
| Hints thay repair | Thiếu anti-entropy | Theo repair policy |
| Lag 0 chứng minh không gap | Có thể thiếu shard | Full watermark reconciliation |
| Đọc replica cũ = lost write | Có thể stale read | Authority read |
| Redis replica ACK là tuyệt đối | Durability còn giới hạn | Failover test |
| Search count phải bằng source | Mapping khác | Logical projection compare |
| Full restore để ép giống nhau | Mất valid updates | Conditional merge |
| QPS cao đủ test race | Keys có thể không tranh | Hot-key workload |
| Chỉ so count/hashes | Không kiểm nghiệp vụ | Cross-record invariants |
| Không exception nghĩa đúng | Logical corruption | Intent/history validators |
| PASS khi còn critical UNKNOWN | Thiếu bằng chứng | INDETERMINATE |

## 51. Bài tập thực hành

### Bài 1 — Hội tụ

Hai replicas cùng trả value 7. Hãy nêu ba lý do khiến chưa thể tuyên bố recovery thành công.

### Bài 2 — Safety và liveness

Database từ chối writes khi mất quorum để tránh split-brain. Thuộc tính nào được ưu tiên, thuộc tính nào bị giảm tạm thời?

### Bài 3 — Timeline

Heal 10:05, quorum healthy 10:05:20, replica cutoff 10:09, domain verified 10:11. Tính hai khoảng time-to-converge và time-to-business-recovery tính từ heal.

**Gợi ý:** 4 phút và 6 phút.

### Bài 4 — LWW

Hai vùng ACK increments từ 0 thành 1, sau heal LWW ra 1. Vì sao có lost business update dù state converged?

### Bài 5 — CAS

Hai clients cùng đọc version 7. Viết pseudocode CAS và điều kiện re-evaluate sau conflict.

### Bài 6 — CRDT

G-Counter có A=3, B=4. Merge thế nào? Vì sao không cộng hai total counters đã replicate?

### Bài 7 — Global safety

Hai vùng cùng reserve phòng capacity=1. Vì sao một CRDT counter hội tụ không ngăn hai booking?

### Bài 8 — Vector clocks

So [A:4,B:2] và [A:3,B:3]. Có vector nào dominates vector còn lại?

### Bài 9 — Clock skew

Client B chậm đồng hồ 7 giây. Tại sao LWW theo client timestamps có thể chọn sai business winner?

### Bài 10 — Tombstone

Một replica cũ hồi sinh voucher bị xóa. Hãy thiết kế test phát hiện sau heal.

### Bài 11 — TTL

Voucher đã hết hạn xuất hiện lại sau restore. Cần kiểm TTL, privacy rule và commit/delete evidence nào?

### Bài 12 — Backlog

600.000 backlog, arrival 1.000/s và apply 1.200/s. Tính drain time.

**Gợi ý:** 50 phút theo rates không đổi.

### Bài 13 — Backlog tăng

Nếu arrival 1.000/s còn apply 900/s, backlog tăng thêm bao nhiêu sau 10 phút?

**Gợi ý:** 60.000 events.

### Bài 14 — Watermark

Cutoff P0=100, P1=200, P2=300; target 120,199,350. Hệ đã hội tụ toàn cutoff chưa?

### Bài 15 — Search

Source booking đúng nhưng search hiển thị booking đã hủy. Đây là replica convergence hay projection freshness vấn đề gì?

### Bài 16 — MongoDB

Thiết kế leader-failover test và so hai write concerns. Vì sao cần đọc authoritative state?

### Bài 17 — Cassandra

Giải thích khác biệt hinted handoff và anti-entropy repair. Tombstone ảnh hưởng ra sao?

### Bài 18 — Cassandra LWW

Old value có timestamp lớn hơn DELETE. Nêu các thông tin cần xem trước khi kết luận resurrection.

### Bài 19 — DynamoDB

Vì sao conditional update ở mỗi region không tự giải quyết global concurrent write conflict trong mọi Global Tables modes?

### Bài 20 — Redis

Master ACK INCR rồi failover sang replica chưa replicate. Test nào đánh giá atomicity, durability và freshness riêng?

### Bài 21 — Java lab

Chạy `ConvergenceLostUpdateLab.java`; giải thích `LWW converged=true` và `LWW noLostUpdate=false`.

### Bài 22 — CAS loop

Vì sao Java CAS loop phải đọc lại state sau khi thất bại?

### Bài 23 — Idempotency

Request timeout sau commit và retry bằng ID mới. Thiết kế cách phát hiện hai business effects.

### Bài 24 — Inventory

`available=0` nhưng có hai confirmed bookings. Cần đối chiếu những keys/ledger nào?

### Bài 25 — Payment

Tổng ledger vẫn bằng nhau nhưng thiếu một transaction và thừa một transaction. Tại sao per-ID reconciliation là bắt buộc?

### Bài 26 — Count equality

Source keys A,B,C; target keys A,B,D. Tổng counts giống nhau; phân loại missing/extra.

### Bài 27 — CDC gap

Consumer lag=0 nhưng bỏ sót một partition. Thiết kế watermark và keyset check.

### Bài 28 — Fault phases

So partition replica, lost ACK sau commit và clock skew. Những outcome classes nào cần thu?

### Bài 29 — Hot-key workload

So 100 clients/100 keys với 100 clients/1 key. Test nào dễ phát hiện lost update race?

### Bài 30 — Load generator

Tại sao closed-loop load test có thể che tail latency trong lúc service bị nghẽn?

### Bài 31 — Fixed sleep

Thay test `sleep(5000)` bằng kiểm cutoff, deadline SLO và invariants.

### Bài 32 — Repair

Source backup v7 còn production v9. Vì sao unconditional replace có thể phá valid writes?

### Bài 33 — Acceptance

Đề xuất SLO cho replica convergence và zero-tolerance invariants cho payment/inventory.

### Bài 34 — UNKNOWN

Không còn mismatch, nhưng một payment intent vẫn UNKNOWN. Verdict nên là gì? Cần thêm bằng chứng nào?

### Bài 35 — Bài tập tổng hợp

Ứng dụng thuê phòng dùng MongoDB booking authority, Cassandra event history, Redis cache, DynamoDB inventory và search projection. Khi xảy ra phân vùng mạng 10 phút dưới peak load:

1. Chọn source of truth và các replication/projection boundaries.
2. Ghi consistency policies và failure assumptions.
3. Thiết kế lịch sử ACKed/rejected/unknown theo intent ID.
4. Chọn common cutoff và per-partition watermarks.
5. Chạy concurrent workload lên hot booking keys.
6. Phân tích LWW, CAS, lost update và retry duplicate.
7. Đo repair/CDC backlog drain.
8. Kiểm no-oversell, ledger, TTL, tenant isolation.
9. Thiết kế conditional repair, canary và runbook.
10. Đưa verdict PASS/FAIL/INDETERMINATE có evidence.

**Gợi ý:** Cluster hội tụ nhưng mất một booking đã ACK hoặc có hai confirmed bookings cho một phòng vẫn là **FAIL về correctness**.

## 52. Checklist vận hành

1. Đã ghi đúng engine/version/topology/RF/consistency modes?
2. Đã xác định authority cho mỗi business entity?
3. Đã tách connectivity, API recovery, convergence và correctness?
4. Fault injection có tác động đúng đường dự kiến?
5. Có common cutoff hoặc quiescence rõ ràng?
6. Có watermark trên tất cả partitions cần thiết?
7. Có kiểm durable apply thay vì chỉ receive?
8. Có so full keys, canonical values và versions?
9. Có phân loại stale read với permanent mismatch?
10. Có tập ACKed/rejected/unknown intents?
11. Có tìm missing/extra/duplicate effects?
12. Có hiểu LWW/conflict resolution/clock skew?
13. Có CAS/conditional write khi business cần?
14. Có kiểm global invariants khi multi-region local writes?
15. Có kiểm tombstone/TTL data resurrection?
16. Có kiểm booking capacity theo room/date?
17. Có kiểm payments/ledger per ID và currency?
18. Có kiểm idempotency của retries/CDC?
19. Có kiểm state-machine version monotonicity?
20. Có full tenant key và access isolation?
21. Có kiểm search/cache theo mapping/freshness?
22. Có đo repair capacity dưới sustained peak?
23. Có time-to-converge từ confirmed heal time?
24. Có API p95/p99/errors trong lúc repair?
25. Có unresolved unknowns cần xử lý?
26. Có fault test guardrails/cleanup?
27. Có conditional repair manifest/approvals?
28. Có history/evidence/owner/regression?
29. Có verdict PASS/FAIL/INDETERMINATE/INVALID_TEST?
30. Có giám sát drift sau khi kết thúc thí nghiệm?

## 53. Tổng kết

1. **Kết nối phục hồi không có nghĩa dữ liệu hội tụ; hội tụ không có nghĩa dữ liệu đúng.**
2. **Convergence phải được định nghĩa theo scope/cutoff/read mode**, không so hai giá trị ngẫu nhiên ở hai thời điểm.
3. **Eventual consistency không tự đưa ra deadline**; backlog, repair lag và time-to-converge phải được đo.
4. **Lost update có nhiều dạng:** read-modify-write, LWW conflict, failover rollback, CDC gap, retry hoặc restore đè.
5. **LWW có thể làm mất acknowledged business intent** dù mọi replicas kết thúc giống nhau.
6. **CAS, CRDT, quorum và transaction có phạm vi riêng**; chọn theo business invariant và data model.
7. **Sự đúng đắn phải kiểm xuyên dữ liệu và side effects**, từ booking/inventory tới payment, idempotency, TTL và tenant isolation.
8. **Unknown commit outcome không được coi là abort**; cần stable intent ID và reconciliation.
9. **Fault testing cần concurrency, operation histories, watermarks và kiểm sau heal**, không chỉ error/uptime metrics.
10. **Repair sai có thể tạo mất cập nhật mới**, nên phải có conditional writes, dry-run, canary và approval.
11. **Lab Java minh họa convergence khác correctness**, không thay phép thử database thật dưới lỗi.
12. **Chỉ báo PASS khi có đầy đủ bằng chứng**, công bố rõ unresolved issues và owner.

**Nguyên tắc thực hành:** Sau khi lỗi mạng hoặc replica được khắc phục, hãy chứng minh **“các bản sao đã đạt cùng cutoff?”, “những writes được xác nhận có còn hiệu lực?”, “có retry nào tạo effect kép?”, “delete/TTL có đúng?”, và “booking, tồn kho, tiền tệ có giữ bất biến?”**. Hệ chỉ thực sự **hội tụ mà vẫn đúng** khi tất cả câu hỏi này có bằng chứng từ dữ liệu có thẩm quyền và lịch sử thao tác.
