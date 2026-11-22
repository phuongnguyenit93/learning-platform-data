# Độ bền, failover và ảnh hưởng khi cụm cache mất toàn bộ dữ liệu

## 1. Mở đầu: mất cache có phải là mất dữ liệu?

Một ứng dụng thương mại điện tử dùng **NoSQL database** làm nguồn dữ liệu chính và **Redis** làm bộ nhớ đệm cho thông tin sản phẩm:

~~~text
Client -> Product API -> Redis cache
                         |
                         | cache miss
                         v
                     NoSQL database
~~~

Ngày bình thường, 97% yêu cầu được trả lời từ cache. Lúc 10:00, toàn bộ cụm Redis bị mất dữ liệu do sự cố hạ tầng. API vẫn chạy, database vẫn còn đủ dữ liệu sản phẩm.

Ta có thể vội nói: “Không sao, cache mất thì lấy lại từ database.” Về **độ bền của dữ liệu nguồn**, điều đó có thể đúng. Nhưng về **khả năng phục vụ**, nó có thể là một sự cố lớn:

- 97% lượng truy vấn vốn không tới database giờ đồng loạt trở thành cache miss.
- Các key nóng khiến hàng nghìn requests cùng đọc một bản ghi.
- Connection pool và các shard của NoSQL database bị quá tải.
- Clients timeout rồi retry, tiếp tục nhân tải.
- Hệ mất khả năng tạo lại cache vì database không đủ sức phục vụ cả traffic thật lẫn warm-up.
- Nếu Redis còn giữ session, distributed lock, idempotency key hoặc job queue dưới dạng **bản duy nhất**, sự cố không còn là “mất cache có thể tái tạo”.

Bài học thuộc chương **Bộ nhớ đệm dữ liệu** của module **Database No SQL**, tập trung vào **độ bền, failover và ảnh hưởng khi cụm cache mất toàn bộ dữ liệu**.

Câu hỏi trung tâm không phải chỉ là “Redis có snapshot hay không?”, mà là:

**Nếu mọi key trong cache biến mất vào thời điểm xấu nhất, dữ liệu nào thực sự mất, hệ thống có còn đúng nghiệp vụ, database nguồn chịu được bao nhiêu miss và đường phục hồi được điều khiển thế nào?**

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **cache dạng dữ liệu dẫn xuất** với **state có giá trị nghiệp vụ duy nhất**.
2. Giải thích RAM, TTL, eviction, RDB snapshot, AOF và replication không phải cùng một bảo đảm.
3. Phân tích Redis Sentinel/Cluster failover và khoảng ghi có thể mất.
4. Nêu giới hạn của ACK, replica acknowledgment và persistence với cache có ghi.
5. Xây mô hình định lượng mức tăng tải về NoSQL khi hit ratio về 0.
6. Thiết kế cache-aside, read-through, write-through và write-behind với recovery đúng.
7. Dùng admission control, single-flight, TTL jitter, stale-while-revalidate và warm-up để tránh cache stampede.
8. Xác định tác động khi mất session, token, rate-limit counter, lock, idempotency ledger hoặc queue.
9. Triển khai một cache-aside service Java có đường fallback và giới hạn miss.
10. Viết runbook, dashboard, fault-injection test và tiêu chí khôi phục sau total cache loss.

---

## 2. Cache là tối ưu hóa hay nguồn sự thật?

Trước khi bàn về failover, phải định nghĩa **vai trò của từng key**.

| Loại dữ liệu trong cache | Ví dụ | Nếu toàn bộ cache mất | Mức rủi ro |
|---|---|---|---|
| **Dẫn xuất, tái tạo được** | Product detail từ MongoDB | Tải lại từ nguồn | Chủ yếu performance/availability |
| **Bản sao đọc có TTL** | User profile cache | Đọc lại DB, có thể tăng latency | Hiệu năng và consistency |
| **Dữ liệu tính toán đắt** | Recommendation list | Tính lại hoặc cung cấp fallback | Có thể ảnh hưởng đáng kể tới chi phí |
| **Session chỉ lưu tại cache** | Login session không có nguồn khác | Người dùng bị logout/mất phiên | Có thể là state loss nghiệp vụ |
| **Idempotency ledger chỉ lưu tại cache** | Key của yêu cầu checkout | Có thể xử lý lại cùng thao tác | Rủi ro duplicate side effects |
| **Quota/rate-limit counters** | Số requests còn trong cửa sổ | Counter reset hoặc không thể kiểm tra | Security/fairness/abuse |
| **Distributed locks/leases** | Quyền chạy một job | Owner cũ và owner mới có thể cùng hoạt động | Vi phạm exclusive ownership |
| **Job queue chỉ ở RAM** | Task cần gửi thanh toán | Tasks có thể biến mất | Mất công việc nghiệp vụ |
| **Write-behind buffer chưa flush** | Updates chỉ ghi vào cache | Những writes chưa bền có thể mất | Data loss thực sự |
| **Revocation/denylist** | Token bị thu hồi | Có thể cho phép token không hợp lệ | Rủi ro bảo mật nghiêm trọng |

### 2.1. Cache dẫn xuất

Nếu mọi giá trị cache đều có thể tái tạo chính xác từ **database/nguồn authoritative còn bền**, mất cache có thể không làm mất dữ liệu nguồn.

Ví dụ:

~~~text
MongoDB Orders collection  [authoritative]
          |
          v
Redis order-summary cache [derived]
~~~

Nếu Redis biến mất, các Order vẫn ở MongoDB. Tuy nhiên, tính đúng đắn còn phụ thuộc vào **quy trình tái tạo**: version, TTL, permission, tenant filtering, key format và business rules.

### 2.2. Cache kiêm source of truth

Nếu ứng dụng ghi giá trị chỉ vào cache rồi báo `200 OK`, không có nguồn bền nào khác, cache đó **không còn là cache chỉ để tối ưu**.

~~~text
Client -> Cache-only write -> ACK
                           |
                           X chưa từng ghi DB/broker bền
~~~

Sau total loss, không có nơi để tự khôi phục write.

### 2.3. Phải phân loại theo *khóa và workflow*, không theo tên sản phẩm

“Redis chỉ là cache” là câu nói không đủ. Một cluster Redis có thể chứa đồng thời:

~~~text
product:*      -> derived cache
session:*      -> session store
ratelimit:*    -> admission state
lock:*         -> coordination
queue:*        -> work backlog
idempotency:*  -> deduplication
~~~

Mỗi namespace có **RPO, RTO, mức độ an toàn và kế hoạch phục hồi khác nhau**. Không thể áp một runbook “flush và reload” chung mà không biết chức năng của chúng.

---

## 3. Năm khái niệm không được đánh đồng

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| **TTL / expiry** | Giá trị còn hợp lệ đến lúc nào? | Key hết hạn sau 60 giây |
| **Eviction** | Khi thiếu bộ nhớ, key nào được loại? | Cache loại key ít dùng |
| **Persistence / durability** | Dữ liệu còn sau restart/crash hay không? | AOF/RDB |
| **Replication** | Giá trị có được sao chép đến node khác? | Primary -> replica |
| **Failover** | Node nào tiếp tục phục vụ khi node hiện tại mất quyền? | Replica được promote |
| **Recovery** | Hệ khôi phục tính năng, state và capacity thế nào? | Reload cache, reconcile |

### 3.1. TTL không phải backup

Một key có TTL 24 giờ không có nghĩa nó được bảo toàn trong 24 giờ. TTL chỉ mô tả **thời hạn tồn tại tối đa theo policy** khi cache còn hoạt động.

### 3.2. Replication không đồng nghĩa ghi bền

Replica có thể giữ giá trị trong RAM nhưng chưa fsync, có thể bị chậm hoặc chưa nhận write. Nếu primary ACK trước replication, failover có thể làm mất write gần nhất.

### 3.3. Có persistence không đồng nghĩa không thể mất toàn bộ

Những điều kiện có thể làm mất state:

- Các bản sao và snapshot cùng bị xóa/corrupt.
- Cấu hình storage ephemeral.
- Cluster bị tạo lại mà không restore.
- Disaster ảnh hưởng cùng failure domain.
- Restore nhầm snapshot quá cũ.
- Secret/key giải mã không còn khả dụng.
- App dùng nhầm namespace hoặc key prefix mới và **trông như cache trống**.
- Dữ liệu hết TTL trong suốt khoảng downtime.

### 3.4. Failover tốt không tự chữa logical corruption

Nếu ứng dụng ghi nhầm giá trị `price=0` và giá trị đó replicate sang mọi replica, failover không làm giá trở lại đúng. Replication có thể **sao chép cả lỗi**; cần authoritative source và recovery logic.

---

## 4. Độ bền cần đo bằng RPO và RTO

### 4.1. Recovery Point Objective (RPO)

**RPO** là giới hạn tổ chức chấp nhận về lượng dữ liệu/độ lùi dữ liệu khi khôi phục sau một sự cố cụ thể.

Ví dụ:

~~~text
Cache derived từ database: business source RPO ≈ RPO của DB.
Redis làm nguồn session duy nhất: session RPO theo Redis policy.
Write-behind cache: các writes chưa flush phải tính vào RPO.
~~~

Không nói “cache RPO=0” chỉ vì có replica. Đặc biệt không dùng một con số RPO chung cho mọi namespace nếu chúng giữ state khác nhau.

### 4.2. Recovery Time Objective (RTO)

**RTO** là thời gian chấp nhận được để dịch vụ/khả năng cần thiết phục hồi sau sự cố.

Một ứng dụng có thể phục hồi process Redis sau 2 phút nhưng cần 30 phút để đạt lại 90% cache hit rate và p99 API trước sự cố.

Do đó nên đo ít nhất:

1. Thời gian cache endpoint sẵn sàng.
2. Thời gian ứng dụng định tuyến tới owner mới.
3. Thời gian database nguồn trở lại latency/throughput an toàn.
4. Thời gian cache warming đạt mục tiêu.
5. Thời gian state quan trọng được đối soát.

### 4.3. RPO và RTO không thay business invariant

Dù dịch vụ cache phục hồi trong 1 phút, nếu key `idempotency:payment` mất và payment bị thu hai lần, incident chưa được giải quyết.

### 4.4. Failure model phải ghi rõ

Ví dụ contract:

~~~text
Mất một cache primary:
  có thể failover sang replica.

Mất cả cache cluster nhưng database nguồn còn:
  derived cache được tái tạo, không mất business records.

Mất cả database nguồn và cache:
  recovery phụ thuộc backup/replication của database, không phải cache.

Mất idempotency ledger chỉ ở cache:
  cần giải pháp khác để tránh duplicate payment.
~~~

---

## 5. Sơ đồ failure domains: một replica không bằng khả năng chịu thảm họa

~~~mermaid
flowchart TD
    API["Java API"] --> P["Cache primary - Zone A"]
    P --> R["Cache replica - Zone B"]
    API --> DB["Authoritative NoSQL DB"]
    P -. "Primary failure" .-> F["Promote replica"]
    R -. "Zone/region failure" .-> L["Cache data unavailable"]
    L --> DB
    DB --> W["Controlled cache rebuild"]
~~~

Trong thiết kế thực, còn có cơ chế khám phá topology, quorum/election, routing, load balancer và storage. Sơ đồ chỉ biểu diễn hai đường **failover một phần** và **khôi phục sau mất cache**.

### 5.1. Node failure

Chỉ một node mất: các replica còn có thể phục vụ theo topology và consistency semantics, nhưng một số writes có thể chưa replicate.

### 5.2. Zone failure

Nếu primary và replica cùng phụ thuộc một zone, một sự cố zone có thể làm mất cả hai. Replica phải được đặt theo failure-domain policy phù hợp.

### 5.3. Region failure

Cross-region replication có thể giúp DR nhưng phải xét độ trễ, dữ liệu chưa đến region khác, network partition và quy tắc lựa chọn authoritative region.

### 5.4. Logical deletion

Một người vận hành dùng `FLUSHALL`/xóa cluster hoặc application nhầm prefix. Replication có thể lan tác động xóa; backup bất biến và quyền truy cập là câu chuyện khác với high availability.

### 5.5. Restore không phải failover

**Failover** chuyển hoạt động sang bản sao sẵn có. **Restore** tái tạo state từ snapshot/log/nguồn khác. Restore có thể làm dữ liệu cũ hơn hoặc cần replay; hai thao tác không có cùng RTO/RPO.

---

## 6. Redis: dữ liệu RAM, RDB, AOF và ý nghĩa thực sự

Redis thường được dùng làm in-memory cache, nhưng có nhiều lựa chọn persistence. Không nên suy các guarantee theo tên “Redis”; phải kiểm tra mode, cấu hình, deployment và Redis version thực tế.

### 6.1. Không bật persistence

Nếu process restart và không có snapshot/AOF hay nguồn khôi phục khác, dữ liệu cache có thể mất.

Đối với cache **thuần dẫn xuất**, điều này có thể là chủ ý: giảm I/O và chọn chiến lược refill từ database.

Đối với cache mang **trạng thái duy nhất**, chính sách ấy có thể không chấp nhận được.

### 6.2. RDB snapshots

RDB lưu ảnh chụp trạng thái tại những thời điểm theo trigger/configuration.

Ví dụ logic:

~~~text
10:00 snapshot RDB thành công.
10:04 có thêm 1.000 keys.
10:05 Redis crash.
10:06 restore từ RDB 10:00.
~~~

Những thay đổi sau snapshot có thể không có trong bản restore. RDB hữu ích cho recovery/bootstrap nhưng **không có nghĩa mọi ACK trước crash đã ở snapshot**.

### 6.3. AOF — Append Only File

AOF ghi log các thay đổi phù hợp cơ chế của Redis để có thể phục hồi trạng thái sau restart.

Các chính sách fsync thông dụng có tính chất khác nhau:

| Chính sách AOF | Ý tưởng | Trade-off |
|---|---|---|
| `appendfsync always` | Yêu cầu sync thường xuyên, gần mỗi thay đổi theo policy | I/O latency/throughput cao hơn; không thay cluster consensus |
| `appendfsync everysec` | Sync theo nhịp khoảng một giây | Có cửa sổ dữ liệu gần nhất có thể mất; không là cam kết tuyệt đối đúng một giây |
| `appendfsync no` | Phụ thuộc OS flush behavior | Cửa sổ mất dữ liệu có thể khó dự đoán hơn |

Chi tiết crash recovery, filesystem, AOF rewrite, disk errors và server version ảnh hưởng bảo đảm thực tế.

### 6.4. AOF rewrite không phải phép xóa “lịch sử” tùy tiện

Redis có cơ chế rewrite để giảm kích thước AOF theo state hiện hành. Khi vận hành cần theo dõi disk headroom, rewrite failures và fsync latency; không tự xóa file AOF vì thấy lớn.

### 6.5. Kết hợp persistence vẫn cần backup

RDB và AOF có thể được cấu hình theo nhu cầu. Một AOF nằm cùng volume bị xóa với instance không cứu được sự cố volume mất toàn bộ.

Backup/restore procedure, encryption, version compatibility và thử restore quan trọng hơn chỉ bật một tham số.

---

## 7. Redis replication và failover: ACK không luôn có nghĩa write được giữ

Xét primary A và replica B:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Redis primary A
    participant B as Replica B
    C->>A: SET cache:order:9001 value
    A-->>C: OK
    Note over A: Write đã ACK trên A
    A--xB: Replication delayed
    Note over A: Primary A gặp sự cố
    Note over B: B được promote
    C->>B: GET cache:order:9001
    B-->>C: NIL
~~~

Đây là **kịch bản có thể xảy ra** với asynchronous replication. Redis Sentinel/Cluster failover không thể được xem là bảo đảm rằng mọi write đã ACK ở primary cũ đều nằm trên primary mới.

### 7.1. Sentinel

Redis Sentinel theo dõi tình trạng primary và có thể điều phối failover trong mô hình triển khai phù hợp. Nó giúp availability/routing nhưng **không biến replication bất đồng bộ thành synchronous consensus replication**.

### 7.2. Redis Cluster

Redis Cluster phân phối hash slots giữa nodes/masters; replicas có thể được promote khi failover. Những keys thuộc slot của node gặp sự cố có thể tạm unavailable, có redirect/topology refresh và có khả năng mất những writes chưa đến replica được chọn.

### 7.3. `WAIT`

Redis `WAIT` có thể đợi một số replicas xác nhận đã nhận các writes của connection theo semantics của lệnh.

Điều đó có thể thu hẹp rủi ro replica lag, **nhưng không tự đảm bảo**:

- Ghi đã fsync trên tất cả các replica.
- Replica có write chắc chắn là replica sẽ được promote.
- Không có split-brain hoặc failover race ngoài protocol.
- Mọi cross-region copy đều có write.
- Kết quả đã committed theo một consensus contract tương đương Raft.

### 7.4. `WAITAOF` và những cơ chế xác nhận bền hơn

Một số phiên bản/triển khai có thể cung cấp cơ chế chờ việc ghi AOF trên các node tương ứng. Phải kiểm tra **hỗ trợ, cấu hình và semantics chính thức** trước khi dùng. Chờ persistence cũng không biến transaction nhiều hệ bên ngoài thành atomic.

### 7.5. Cấu hình tối thiểu replica cũng có giới hạn

Các cấu hình giới hạn chấp nhận ghi khi replica không đáp ứng một số điều kiện có thể **giảm cửa sổ rủi ro**, nhưng không nên được mô tả là bảo đảm mạnh như synchronous consensus với durable quorum commit.

### 7.6. Với cache dẫn xuất, chấp nhận mất là một quyết định hợp lệ

Nếu cache entry chỉ là bản sao sản phẩm và database nguồn đúng, có thể ưu tiên availability/cost và chấp nhận stale/loss ở cache. Nhưng tính toán **tải cold miss** và đường fallback vẫn bắt buộc.

---

## 8. Memcached, local cache và managed cache khác nhau ở đâu?

### 8.1. Memcached

Memcached thường được dùng như cache in-memory phân tán theo client-side key distribution. Mô hình phổ biến **không có persistence/replication như một durable database**; key có thể mất khi node restart hoặc bị eviction.

Những tổ chức cần full durability thường không xem Memcached là nơi giữ state duy nhất.

### 8.2. Local in-process cache — Caffeine/Guava

~~~text
Java instance A -> local Caffeine cache A
Java instance B -> local Caffeine cache B
Java instance C -> local Caffeine cache C
~~~

Nếu một instance restart, local cache của nó trống. Nếu tất cả JVMs rolling restart đồng thời, **mọi local caches có thể lạnh cùng lúc** dù không có Redis.

Lợi ích là nhanh, đơn giản, giảm network; đánh đổi là mỗi instance có state riêng, khó đồng bộ invalidation và mất dữ liệu local khi process exit.

### 8.3. Managed Redis-compatible caches

Dịch vụ managed có thể có Multi-AZ failover, snapshot backups, automatic node replacement hoặc những lựa chọn tier/persistence khác nhau. **Không giả định** mọi tier đều có persistence, mọi region có DR hoặc backup tự bao gồm mọi key.

Xem tài liệu và cấu hình của **dịch vụ/engine version/tier cụ thể**.

### 8.4. Near cache hai tầng

~~~text
Java L1 local cache
      |
      v
Redis L2 distributed cache
      |
      v
NoSQL source of truth
~~~

Nếu L2 mất toàn bộ nhưng L1 còn dữ liệu:

- L1 có thể giúp giảm đợt cold miss ban đầu.
- L1 có thể chứa dữ liệu đã stale.
- Invalidation messages qua Redis pub/sub có thể bị bỏ lỡ.
- Các instances restart khác thời điểm có hit rate khác nhau.

Một L1 hit không chứng minh dữ liệu đang đúng theo freshness/security contract.

### 8.5. In-memory data grid

Hazelcast/Ignite hoặc những hệ tương tự có thể hỗ trợ replication, partition ownership, persistence/backup theo cấu hình. Không lấy tính chất của một hệ này gán cho cache in-memory khác; cần đọc **durability contract** của chính deployment.

---

## 9. Bốn mẫu đọc/ghi và tác động khi cache mất

| Mẫu | Cơ chế cơ bản | Mất toàn bộ cache dẫn tới |
|---|---|---|
| Cache-aside / lazy loading | App đọc cache; miss thì đọc DB rồi fill | Nhiều cold misses, origin overload |
| Read-through | Cache layer tự load từ DB | Tương tự nhưng logic nạp ở cache/provider |
| Write-through | Ghi nguồn và cache theo protocol | Cache có thể phục hồi từ nguồn nếu source commit bền |
| Write-around | Ghi nguồn, không chủ động fill cache | Miss tăng cho dữ liệu mới |
| Write-behind / write-back | Ghi cache trước, flush nguồn sau | **Mất những thay đổi chưa flush** nếu không có durable log khác |

### 9.1. Cache-aside

~~~mermaid
flowchart TD
    R["GET product"] --> C{"Cache hit?"}
    C -- "Yes" --> H["Return cached value"]
    C -- "No" --> G["Read authoritative NoSQL DB"]
    G --> P["Best-effort cache put"]
    P --> U["Return source value"]
~~~

Mất cache chủ yếu làm tăng latency và tải nguồn, miễn source còn đủ dữ liệu, app không trả stale/hỏng trong quá trình refill.

### 9.2. Read-through

App không tự thực hiện miss loading; cache/provider có logic load. Tuy vậy, nếu provider bị mất dữ liệu, nó vẫn cần DB capacity để rebuild. Tính từ “read-through” **không tạo thêm origin throughput**.

### 9.3. Write-through

Một design có thể ghi DB và cập nhật cache:

~~~text
1. Update authoritative DB.
2. Update/invalidate cache.
3. Return outcome according to contract.
~~~

Nếu cập nhật cache thất bại, DB đã commit có thể vẫn đúng; phải định nghĩa cách API trả response và cách tránh stale cache.

**Không gọi hai writes độc lập ở DB và Redis là “atomic” chỉ vì chạy cùng method Java.**

### 9.4. Write-behind

~~~text
Client -> Redis accepts write -> ACK
                    |
                 pending buffer
                    |
                    v
               NoSQL database
~~~

Nếu cache mất trước khi flush, các writes đã ACK có thể biến mất. Nếu workflow cần durability mạnh, phải:

- Có durable write-ahead log/queue/outbox làm source.
- Hoặc không ACK như completed cho tới khi source durable commit.
- Hoặc chấp nhận/tài liệu hóa RPO write-behind.
- Và có idempotent replay/reconciliation.

### 9.5. Cache warm không được ghi đè dữ liệu mới

Một loader đọc DB version 7; lúc nó đang fill cache, một update version 8 commit. Nếu loader viết cache version 7 **sau** khi version 8 đã được invalidated, cache có thể trở lại stale. Cần version-aware cache entry/conditional set hoặc cache invalidation protocol phù hợp.

---

## 10. Total cache loss gây tăng tải bao nhiêu lần?

Đặt:

- \(Q\): tổng logical read requests/giây vào API.
- \(h\): cache hit ratio (0 đến 1).
- \(m=1-h\): miss ratio.
- \(Q_{DB}\): requests/giây tới database chỉ do đường cache lookup, bỏ qua fan-out và extra calls.

Một mô hình đơn giản:

\[
Q_{DB,\;normal}=Q(1-h).
\]

Nếu cache hoàn toàn trống và chưa kịp refill:

\[
Q_{DB,\;cold}\approx Q.
\]

Hệ số tăng ban đầu:

\[
A=\frac{Q_{DB,\;cold}}{Q_{DB,\;normal}}
 =\frac{1}{1-h}.
\]

### 10.1. Ví dụ số

Với \(Q=10\,000\) reads/s và \(h=0.97\):

\[
Q_{DB,\;normal}=10\,000\times0.03=300\text{ reads/s}.
\]

Ngay sau total loss:

\[
Q_{DB,\;cold}\approx10\,000\text{ reads/s}.
\]

Hệ số:

\[
A=\frac{10\,000}{300}\approx33.3.
\]

**Cùng 10.000 người dùng/requests nhưng database có thể nhìn thấy lượng reads tăng hơn 33 lần.**

### 10.2. Bảng nhạy cảm theo hit ratio

| Cache hit ratio trước sự cố | Miss bình thường | Hệ số tải DB khi full cold |
|---:|---:|---:|
| 50% | 50% | 2× |
| 80% | 20% | 5× |
| 90% | 10% | 10× |
| 95% | 5% | 20× |
| 97% | 3% | 33,3× |
| 98% | 2% | 50× |
| 99% | 1% | 100× |

Đây là phép tính **giả định một cache read tương ứng tối đa một origin read khi miss**. Trong thực tế, fan-out, quorum, retries, negative caching, tiered caches và coalescing có thể làm con số khác.

### 10.3. Hit ratio cao là lợi ích và rủi ro phục hồi

Hit rate 99% tiết kiệm DB load lớn, nhưng khiến DB có thể **không còn được cấp phát cho workload miss 100%**. Khi cache biến mất, không thể mong hệ tự đáp ứng y như trước mà không có phương án graceful degradation.

### 10.4. Chỉ số cần tính theo key/class

Một số endpoints có thể có 99% hit, số khác 40%. Nếu product catalog chiếm phần lớn reads, nó có thể quyết định origin overload. Tính riêng:

~~~text
endpoint
tenant
key range / shard
region
cache layer
read/write request class
```

Average cache hit rate toàn cluster có thể che một hot partition có 0% hit.

---

## 11. Origin capacity: cache mất có thể kéo sập cả database nguồn

Giả sử NoSQL database phục vụ ổn định thêm được **1.000 origin reads/s** ở mức p99 an toàn, trong khi cache cold tạo **10.000 miss/s**.

Tải tới sẽ lớn hơn capacity khoảng 10 lần. Nếu app xếp hàng tất cả:

~~~text
9.000 requests/s backlog
      |
      v
connection wait + request queue
      |
      v
long latency + timeouts
      |
      v
client retries
      |
      v
even more DB attempts
~~~

### 11.1. Không dùng queue vô hạn làm “bộ đệm” chính

Một queue vô hạn chỉ dời lỗi từ `503` tức thời thành response timeout, heap pressure, GC pause và retry storm.

### 11.2. Cần có admission control

Một recovery mode có thể giới hạn:

- Global origin reads/s.
- Origin reads in-flight.
- Per-partition/per-tenant concurrency.
- Background warm-up rate.
- Retry attempts/s.
- Database connection acquisition queue.
- Search/analytics thấp ưu tiên.

### 11.3. Quyết định trả lỗi nhanh khi không thể phục vụ

Nếu không có stale value hợp lệ và origin capacity hết, API có thể trả `503` tạm thời hoặc lỗi typed phù hợp, với retry hint có budget. Đó có thể là lựa chọn **tốt hơn** nhận 10.000 requests rồi để tất cả timeout.

### 11.4. Autoscaling không tức thời

Thêm database nodes có thể cần bootstrap/rebalance, làm nóng index/page cache và tốn băng thông. Trong thời gian đó, admission và workload shedding vẫn cần thiết.

---

## 12. Cache stampede: nhiều clients cùng tải lại một key

Giả sử key `product:hot-1` có 4.000 reads/s. Khi cache trống:

~~~text
Client 1 --> MISS --> DB read hot-1
Client 2 --> MISS --> DB read hot-1
Client 3 --> MISS --> DB read hot-1
...
Client 4000 --> MISS --> DB read hot-1
~~~

Trong khi chỉ cần một kết quả để fill cache.

### 12.1. Local single-flight/request coalescing

Một process có thể cho các requests cùng key chia sẻ một in-flight load:

~~~text
100 requests for key K
        |
        v
1 in-flight loader for K
        |
        v
NoSQL read once
        |
        v
Fan out result to 100 waiting callers
~~~

Java Caffeine `Cache.get(key, mappingFunction)` có thể đồng bộ computation cho cùng key theo semantics của cache. `AsyncLoadingCache` có thể giúp chia sẻ in-flight future ở một process.

### 12.2. Single-flight local không đủ cho toàn cluster

Nếu có 50 app instances, mỗi instance single-flight một lần, NoSQL vẫn có thể nhận **50 reads cho cùng key**. Có thể cần shared coordination hoặc chiến lược khác nếu hot key cực nóng.

### 12.3. Dùng lock phân tán để warm cũng có rủi ro

Một Redis-based mutex đang nằm trên chính cụm cache bị sự cố có thể mất cùng các keys. Sau failover, owner cũ và mới có thể cùng chạy loader.

Nếu load chỉ là **đọc idempotent** từ DB, duplicate load có thể chấp nhận được nếu có rate limit. Nếu loader có side effect business, cần authority/fencing khác; không dùng cache lock như chứng cứ exclusive mutation.

### 12.4. Không để tất cả chờ một loader vô hạn

Single-flight cần bounded waiting/deadline. Nếu loader mắc kẹt, các request đang đợi phải được timeout/fallback; lỗi của một key không nên khóa toàn service.

---

## 13. TTL jitter: tránh nhiều key hết hạn cùng lúc

Một chiến lược thường dùng là thêm jitter quanh TTL:

~~~text
TTL base: 60 giây
TTL thực tế: ngẫu nhiên 50-70 giây
~~~

Điều này làm các key không cùng hết hạn một mốc nếu được tạo theo batch.

### 13.1. Ví dụ Java

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class CacheTtl {

    public static Duration productTtl() {
        int seconds = ThreadLocalRandom.current()
            .nextInt(50, 71);
        return Duration.ofSeconds(seconds);
    }
}
~~~

### 13.2. Jitter không cứu total loss tức thời

Nếu cả cluster mất sạch, **mọi key đều miss cùng lúc**, không còn TTL spread trước đó. TTL jitter giúp sau refill giảm đồng bộ expiry nhưng phải kết hợp admission, coalescing và warm-up để xử lý mất toàn bộ.

### 13.3. TTL không được tự tăng cho dữ liệu nhạy cảm

Một permission/price/token state có freshness contract nghiêm ngặt có thể không cho phép kéo dài TTL chỉ để giảm tải. Cần phân loại per-cache namespace.

### 13.4. Eviction và TTL là hai điều kiện khác

Một key có TTL 1 giờ vẫn có thể bị eviction trước 1 giờ khi thiếu bộ nhớ. SLO không được giả định “đã set TTL một giờ thì chắc chắn hit suốt một giờ”.

---

## 14. Stale-while-revalidate và stale-if-error

Một chiến lược phục hồi có thể dùng giá trị hơi cũ để giảm tải nguồn trong lúc background refresh:

~~~text
Fresh:           trả ngay
Stale allowable: trả stale + trigger bounded refresh
Too old:         bắt buộc đọc authoritative source hoặc báo unavailable
~~~

### 14.1. Không áp dụng tùy tiện

Có thể phù hợp cho:

- Tên sản phẩm và hình ảnh.
- Danh mục đọc thường xuyên.
- Thông tin gợi ý hoặc bài viết.
- Metadata có độ trễ cho phép.

Có thể nguy hiểm cho:

- Số lượng tồn kho cần chính xác khi xác nhận mua.
- Giá giao dịch cuối cùng.
- Quyền truy cập đã bị thu hồi.
- Số dư tài khoản.
- Điều kiện chống gian lận.
- Token/session revocation.

### 14.2. Stale-if-error cần contract rõ

Nếu Redis L2 mất và NoSQL đang quá tải, một L1 local cache có dữ liệu 2 phút trước có thể giúp render trang catalog. Nhưng API phải xác định **những field nào được phép stale và trong bao lâu**.

### 14.3. Không biến stale read thành authoritative write decision

Có thể hiển thị “còn hàng” từ cache, nhưng bước đặt hàng cần atomic reservation/conditional write trên authoritative storage. Cache availability không phải quyền cấp phát.

### 14.4. Staleness phải có metadata

Một cache entry có thể lưu:

~~~json
{
  "value": {
    "productId": "prd-42",
    "displayName": "Camera"
  },
  "sourceVersion": 128,
  "refreshedAt": "2026-11-14T08:00:00Z"
}
~~~

Nếu refresh logic cần biết freshness, đừng xóa metadata chỉ để tối ưu serialization mà làm mất khả năng ngăn stale overwrite.

---

## 15. Negative caching: tránh đánh DB liên tục với key không tồn tại

Cache chỉ lưu dữ liệu tìm thấy có thể gặp một tình huống:

~~~text
GET /products/non-existing-id 2.000 lần/s
Every call -> Redis NIL -> NoSQL 404
~~~

**Negative caching** lưu kết quả “không tồn tại” trong một khoảng ngắn.

### 15.1. Lợi ích

Giảm origin load từ invalid IDs, broken links, bots và hot misses.

### 15.2. Rủi ro

- Sản phẩm vừa được tạo có thể vẫn bị nhìn là không tồn tại.
- Nếu một read stale từ replica trả 404, negative cache có thể che dữ liệu đã commit.
- Không nên negative-cache permission errors như 404 nếu không hiểu security semantics.
- Cache key phải gồm tenant/auth scope khi cần, tránh rò thông tin tồn tại của resource.

### 15.3. TTL ngắn và version-aware invalidation

Negative TTL thường cần khác positive TTL. Một create event có thể invalidate negative entry. Nhưng hệ phải xử lý event bị mất/đảo thứ tự sau failover.

### 15.4. Tránh cache mọi mã lỗi

`503` hoặc DB timeout **không phải** kết quả “record không tồn tại”. Nếu lưu chúng thành negative cache, một sự cố ngắn có thể tạo sai dữ liệu kéo dài.

---

## 16. Warm-up sau mất cache: ưu tiên key nóng, không nạp tất cả ngay

Một chiến lược “đọc toàn bộ database để làm nóng cache” có thể chính là đợt tải làm DB chết lần hai.

Thay vào đó:

1. Xác định các **hot keys** theo thống kê đủ tin cậy.
2. Tạm giới hạn origin reads và warm-up reads riêng.
3. Ưu tiên những keys phục vụ endpoints quan trọng.
4. Dùng batching/pagination với query/index hiệu quả.
5. Giữ một ngân sách IOPS/network/CPU để phục vụ traffic thật.
6. Warm theo nhiều đợt, có checkpoint/stop condition.
7. Ghi nhận hit ratio/DB latency/evictions giữa các đợt.
8. Dừng hoặc giảm warm-up khi nguồn bị throttling.
9. Duy trì TTL jitter và version correctness.
10. Chỉ bỏ recovery mode khi SLO ổn định.

### 16.1. Lịch phục hồi minh họa

~~~text
Phase A: Cache endpoint/cluster khỏe, chưa cho all traffic.
Phase B: Cho 10% traffic + bounded origin reads.
Phase C: Nạp hot product keys theo ngân sách nền.
Phase D: Mở dần 25% -> 50% -> 100%.
Phase E: Theo dõi p99, hit ratio và origin throttling.
Phase F: Kết thúc sau khi đối soát state quan trọng.
~~~

Các tỷ lệ là ví dụ; điều kiện chính phải dựa trên số đo chứ không phải mốc thời gian cố định.

### 16.2. Không nạp dữ liệu không còn hợp lệ

Warm-up từ snapshot cũ có thể viết đè cache với state lỗi thời. Hãy chọn authoritative source và version cutoff thích hợp, tôn trọng các lệnh xóa/revocation.

### 16.3. Xem xét memory overhead

Cache 2 triệu keys, mỗi payload ~1,2 KiB có logical payload khoảng:

\[
2\,000\,000\times1.2\text{ KiB}
\approx2.29\text{ GiB}.
\]

Chưa tính key bytes, allocator, object/Redis overhead, replicas, fragmentation, metadata hoặc eviction headroom. Không cấp đúng 2,29 GiB RAM rồi kỳ vọng chứa toàn bộ mà không eviction.

### 16.4. Cache warm có thể tranh I/O với backup/repair

NoSQL source có thể đang repair sau cùng sự cố vùng. Warm-up quá mạnh làm tăng compaction, disk pressure và replication lag. Cần điều phối với database recovery.

---

## 17. Load shedding và graceful degradation

Khi cache mất, không nhất thiết mọi tính năng phải hoạt động ở chất lượng đầy đủ.

Một quyết định theo cấp độ:

| Chức năng | Khi cache mất | Chính sách hợp lý tùy sản phẩm |
|---|---|---|
| Product detail | Origin read tăng | Cho một phần đọc, rate limit, stale-safe |
| Search recommendation | Tính toán đắt | Fallback gợi ý tĩnh hoặc tạm tắt |
| Analytics dashboard | Query rộng | Hoãn/batch và thông báo chậm |
| Checkout inventory | Cần chính xác | Bảo vệ origin capacity và conditional transaction |
| Authentication | Phụ thuộc state | Fail-safe theo security contract |
| Admin exports | Không urgent | Hoãn trong recovery window |
| Background cache warmer | Tạo tải bổ sung | Giữ ngân sách thấp, pause khi DB chậm |
| Payment confirmation | Correctness rất cao | Tra nguồn authoritative, không suy từ cache |

### 17.1. Load shedding có thể tăng trải nghiệm tổng thể

Nếu origin chỉ có capacity cho 1.000 req/s, từ chối nhanh 9.000 req/s có thể giữ một số giao dịch quan trọng trong SLO, thay vì nhận hết 10.000 rồi mọi thứ timeout.

### 17.2. Có loại lỗi không được “degrade thành success”

Nếu không kiểm tra được quyền truy cập hoặc trạng thái thanh toán authoritative, trả dữ liệu không an toàn chỉ để đạt 200 OK là sai.

### 17.3. Tách read và write budgets

Write critical có thể cần đảm bảo capacity riêng. Không để cache warming/read traffic chiếm connection/CPU khiến source không commit được giao dịch.

### 17.4. User-visible behavior

Có thể trả mã `503 Service Unavailable`, `429 Too Many Requests`, thông tin `Retry-After` hoặc trải nghiệm read-only có thông báo tùy API contract. Đừng để frontend tự retry vô hạn trên cùng key.

---

## 18. Java: cache-aside với fail-open cache và admission nguồn

Ví dụ sau mô tả **cache chỉ là dữ liệu dẫn xuất**: khi cache lỗi, service có thể bỏ qua cache để đọc NoSQL source, nhưng luôn giới hạn số origin reads đang chạy.

~~~java
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.Semaphore;

public final class ProductService {

    public record Product(
        String id,
        String displayName,
        long priceMinor,
        long version
    ) {}

    public interface ProductStore {
        Optional<Product> findById(String productId);
    }

    public interface ProductCache {
        Optional<Product> get(String productId);
        void put(Product product);
        void invalidate(String productId);
    }

    public static final class OriginOverloadedException
            extends RuntimeException {
        public OriginOverloadedException() {
            super("Origin capacity exhausted");
        }
    }

    private final ProductStore source;
    private final ProductCache cache;
    private final Semaphore originPermits;

    public ProductService(
            ProductStore source,
            ProductCache cache,
            int maxConcurrentOriginReads) {

        this.source = Objects.requireNonNull(source);
        this.cache = Objects.requireNonNull(cache);

        if (maxConcurrentOriginReads < 1) {
            throw new IllegalArgumentException(
                "maxConcurrentOriginReads must be positive"
            );
        }

        this.originPermits =
            new Semaphore(maxConcurrentOriginReads);
    }

    public Optional<Product> get(String productId) {
        Objects.requireNonNull(productId);

        // Cache lỗi được xử lý như miss; không được coi
        // lỗi nguồn dữ liệu là cache miss.
        try {
            Optional<Product> cached = cache.get(productId);
            if (cached.isPresent()) {
                return cached;
            }
        } catch (RuntimeException cacheFailure) {
            recordCacheFailure(cacheFailure);
        }

        if (!originPermits.tryAcquire()) {
            throw new OriginOverloadedException();
        }

        try {
            // Source vẫn là authoritative. Nếu source lỗi,
            // lỗi phải được trả lên thay vì "not found".
            Optional<Product> found =
                source.findById(productId);

            found.ifPresent(product -> {
                try {
                    cache.put(product);
                } catch (RuntimeException cacheFailure) {
                    recordCacheFailure(cacheFailure);
                }
            });

            return found;
        } finally {
            originPermits.release();
        }
    }

    private void recordCacheFailure(RuntimeException failure) {
        // Thực tế: metrics/tracing, log có giới hạn.
        // Không log secrets/PII hoặc tạo log storm.
    }
}
~~~

### 18.1. Điểm an toàn của ví dụ

- Cache failure **không bị coi là dữ liệu không tồn tại**.
- Origin read là nguồn authoritative.
- Origin concurrency được giới hạn bằng semaphore.
- Cache fill lỗi không phủ định dữ liệu vừa đọc từ DB.
- `finally` bảo đảm trả permit khi origin throw.
- Không tạo queue vô hạn trong service.

### 18.2. Điểm chưa có trong production

Ví dụ không tự giải quyết:

- Per-tenant/per-key fairness.
- Single-flight trên hot key.
- TTL và negative caching.
- Consistency/version-aware cache set.
- Authorization và tenant-specific cache key.
- Deadline/timeouts ở DB driver.
- Distributed rate limit across all instances.
- Retry budgets/circuit breaker.
- Stale-if-error hoặc cache fallback policy.
- Monitoring và graceful shutdown.

### 18.3. Fail-open ở cache không phải fail-open cho bảo mật

Bỏ qua lỗi **product cache** để đọc **authoritative DB** có thể an toàn. Nhưng nếu cache giữ denylist/revocation hoặc dùng như nguồn cấp phép duy nhất, fail-open có thể gây vi phạm quyền truy cập. **Chính sách fallback phải theo loại dữ liệu**.

### 18.4. `Optional.empty()` không tự được negative-cache

Service trên chỉ `put` khi source trả Product. Một missing key lặp lại vẫn đánh DB nhiều lần; thêm negative caching cần TTL và semantics riêng.

---

## 19. Java + Caffeine: giảm stampede cục bộ

Một ví dụ Java với Caffeine:

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;
import java.util.Optional;

public final class LocalProductCache {

    private final ProductRepository source;

    private final Cache<String, Optional<Product>> cache =
        Caffeine.newBuilder()
            .maximumSize(20_000)
            .expireAfterWrite(Duration.ofSeconds(60))
            .build();

    public LocalProductCache(ProductRepository source) {
        this.source = source;
    }

    public Optional<Product> get(String id) {
        return cache.get(id, key -> source.findById(key));
    }

    public void invalidate(String id) {
        cache.invalidate(id);
    }

    public interface ProductRepository {
        Optional<Product> findById(String id);
    }

    public record Product(
        String id,
        String name,
        long version
    ) {}
}
~~~

### 19.1. Vì sao `Cache.get(key, mappingFunction)` hữu ích?

Caffeine có semantics atomic load cho một key trong **cùng cache instance**, giúp giảm nhiều loader đồng thời khi cache miss cùng key.

### 19.2. Các giới hạn

- Đây là **local** cache; 20 Java instances vẫn có thể cùng load một hot key.
- Loader đang chạy có thể chặn caller threads; nếu source chậm, cần deadline/admission.
- `expireAfterWrite` định nghĩa expiry, **không** bảo toàn dữ liệu qua JVM restart.
- `Optional.empty()` được cache với TTL chung trong ví dụ; ứng dụng thực có thể cần TTL ngắn hơn cho negative results.
- Cache key thiếu tenant context nếu IDs không global unique.
- `invalidate()` ở một instance không đồng nghĩa invalidation toàn cluster.
- Nếu source thay đổi trong lúc loader chạy, stale overwrite cần được xử lý theo thiết kế.

### 19.3. Caffeine không cần persistence để làm đúng vai trò derived cache

Khi Java process restart, cache có thể mất toàn bộ. Điều đó chấp nhận được nếu **source durable, miss load có kiểm soát và user-facing SLO cho phép**.

---

## 20. Java + Spring Data Redis: lỗi cache và nguồn phải được phân loại

Ở những dự án dùng Spring, `StringRedisTemplate` thường dùng cho cache strings; mapper có thể encode/decode JSON và giữ metadata `version`.

Một cấu trúc logic:

~~~java
public Optional<Product> getProduct(String productId) {
    try {
        String encoded =
            redisTemplate.opsForValue().get(cacheKey(productId));

        if (encoded != null) {
            return Optional.of(decodeAndValidate(encoded));
        }
    } catch (RedisConnectionFailureException cacheFailure) {
        metrics.incrementCacheUnavailable();
        // Cache-only failure -> bypass.
    }

    Product authoritative = productRepository
        .findById(productId)
        .orElse(null);

    if (authoritative == null) {
        return Optional.empty();
    }

    try {
        redisTemplate.opsForValue().set(
            cacheKey(productId),
            encode(authoritative),
            Duration.ofSeconds(60)
        );
    } catch (RedisConnectionFailureException cacheFailure) {
        metrics.incrementCacheWriteFailure();
    }

    return Optional.of(authoritative);
}
~~~

Đây là **pseudocode Java trong một service**: `Product`, repository, `encode`, `decodeAndValidate`, `metrics`, `cacheKey` và imports được giả định có sẵn. Một implementation production cần phân biệt cache timeout, invalid payload, authentication error, source failure, TTL, idempotency và bảo vệ nguồn khỏi stampede.

### 20.1. Không `catch (Exception) -> Optional.empty()`

Nếu Redis lỗi rồi database cũng lỗi, trả `Optional.empty()` sẽ biến một sự cố thành business “product not found”, có thể negative-cache sai.

### 20.2. Redis cache put là best-effort trong mô hình này

DB đã trả Product, Redis `SET` không thành công thì vẫn trả kết quả từ nguồn. Nhưng một **write path** cần quy tắc invalidation khác để không trả stale data sau update.

### 20.3. Version-aware cache entries

Một cache entry gồm `sourceVersion` có thể giúp chặn ghi lùi trong những race. Việc so/version update phải atomic ở nơi cache khi có concurrent writers/loaders; chỉ so version trong Java rồi gửi `SET` riêng không đủ nếu có nhiều processes.

### 20.4. Cấu hình client timeout và pool

Một cache dependency đang lỗi nên fail fast, không giữ mọi request 3 giây ở Redis trước khi fallback. Cache timeout phải nằm trong **end-to-end deadline** và không biến cache thành bottleneck khi nó đang không sẵn sàng.

---

## 21. Race condition: DB đã đổi nhưng cache bị ghi ngược

Xét cache-aside với hai requests:

~~~text
T0 Cache không có product:42.
T1 Reader R bắt đầu đọc DB version 7.
T2 Writer W commit DB version 8.
T3 Writer W invalidate cache key.
T4 Reader R trả DB version 7 về application.
T5 Reader R put cache version 7.
```

Cache bây giờ có giá trị **cũ hơn** sau khi writer đã invalidate.

### 21.1. Tại sao chỉ “invalidate after write” chưa đủ?

Vì một in-flight reader có thể load phiên bản cũ rồi cache lại sau khi invalidation diễn ra.

### 21.2. Những hướng khắc phục tùy yêu cầu

- TTL đủ ngắn cho những field cho phép stale.
- Versioned cache value, conditional put chỉ khi version không cũ hơn.
- Generation/namespace version trong cache key.
- Read source với consistency phù hợp.
- Invalidation theo version và xử lý late events.
- Chỉ cache dữ liệu bất biến/immutable khi có thể.
- Sau update quan trọng, bypass cache hoặc session-aware read.
- Với security/business invariant, không dùng stale cache làm nguồn quyết định.

### 21.3. Version phải có thẩm quyền

Một version từ DB mutation/transaction là cơ sở tốt hơn `System.currentTimeMillis()` của từng client khi đồng hồ lệch. Version cho mỗi key cũng không tự tạo thứ tự toàn cluster.

### 21.4. TTL không thay consistency contract

Nếu dữ liệu tiền, giá, revocation đòi cập nhật ngay, “stale tối đa 60 giây” có thể vẫn sai; cần thiết kế đường authoritative.

---

## 22. Invalidation bị mất trong lúc failover

Một hệ cache invalidation có thể dùng pub/sub:

~~~text
DB write -> publish invalidate(product:42)
                      |
                      v
             Java instances clear L1 caches
~~~

Nếu broker Redis chính đang failover, một số subscribers có thể không nhận thông báo. L1 caches tiếp tục phục vụ giá trị cũ.

### 22.1. Pub/sub không phải durable invalidation log

Với một cơ chế pub/sub không lưu lịch sử, subscriber offline có thể bỏ lỡ event. Nếu correctness phụ thuộc vào **không bao giờ bỏ lỡ invalidation**, cần durable stream/outbox/CDC hoặc một cách đối soát/version check khác.

### 22.2. Không chỉ xét “Redis phục hồi rồi”

Sau khi Redis L2 phục hồi, các Java L1 caches có thể chưa được làm sạch. Runbook cần kiểm:

- Cache namespace/epoch mới.
- Consumer offsets/watermarks.
- Last seen source version.
- Reconnect subscriptions.
- Invalidation backlog có replay được không?
- TTL tối đa của local entries.

### 22.3. Epoch cho invalidation generation

Một strategy có thể đổi `cacheGeneration` sau total loss hoặc migration, buộc L1 keys cũ không được xem là hợp lệ. Phải quản lý generation từ nguồn **có thẩm quyền và tồn tại qua crash**, không chỉ đặt trong Redis vừa mất hết state.

---

## 23. Session cache mất: người dùng có thể bị đăng xuất hàng loạt

Nhiều hệ lưu web session state trong Redis vì TTL và share giữa app instances.

### 23.1. Nếu session chỉ có ở Redis

Total loss có thể làm mọi session không còn tồn tại:

~~~text
Browser sends session cookie
      |
      v
App reads session ID in Redis
      |
      v
NIL -> user must reauthenticate
~~~

Không có database “product source” nào giúp tái tạo state session cũ nếu nó chỉ tồn tại trong cache.

### 23.2. Có thể phục hồi bằng cách nào?

Tùy kiến trúc:

- Chấp nhận forced logout theo risk/SLO.
- Dùng durable session store.
- Dùng token có đủ thông tin và kiểm tra chữ ký, nếu security model cho phép.
- Dùng session backup/replication có RPO rõ.
- Tách session state quan trọng khỏi ephemeral cache.
- Thiết kế graceful reauthentication để tránh login service overload.

### 23.3. JWT không tự giải mọi vấn đề

JWT tự chứa có thể giảm dependency đọc session, nhưng revocation, rotation, device logout và token theft vẫn cần state hoặc chính sách expiration. Mất revocation cache có thể nguy hiểm.

### 23.4. Authentication storm

Nếu 100.000 users bị logout cùng lúc, login/identity provider có thể nhận burst lớn. Cần tính rate limits, sign-in queues và user messaging cho kịch bản DR.

---

## 24. Rate limit counter mất: fail-open hay fail-closed?

Một API dùng Redis để lưu:

~~~text
ratelimit:tenant-7:window-2026-11-14T08:00Z = 499
```

Nếu cache mất toàn bộ, counter có thể reset về 0, làm tenant được “cấp lại” request quota trong cùng cửa sổ.

### 24.1. Fail-open

Cho request qua khi rate-limit backend không sẵn sàng.

Ưu điểm: giảm nguy cơ khóa nhầm người dùng hợp lệ.

Rủi ro: abuse, credential stuffing, vượt quota/cost, overload backend.

### 24.2. Fail-closed

Từ chối khi không thể kiểm tra budget.

Ưu điểm: bảo vệ endpoint nhạy cảm.

Rủi ro: gây từ chối dịch vụ diện rộng cho khách hàng hợp lệ.

### 24.3. Chính sách theo endpoint

| Endpoint | Khi mất Redis rate limiter | Điểm cần cân nhắc |
|---|---|---|
| Product catalog GET | Có thể fail-open có giới hạn local | Bảo vệ origin bằng admission khác |
| Login/password reset | Có thể cần fail-closed/chống brute-force khác | Security impact |
| Payment/withdrawal | Cần kiểm soát đáng tin | Financial fraud limits |
| Low-risk health check | Có thể không cần Redis | Tránh phụ thuộc không cần |
| Expensive report | Có thể reject/defer | Protect DB |
| Admin API | Policy nghiêm ngặt | Permission và audit |

Không có một câu trả lời fail-open/fail-closed đúng cho mọi endpoint. Cần security review và một **fallback limiter độc lập** nếu chức năng trọng yếu.

### 24.4. Local fallback counters không hoàn toàn tương đương

Một limiter per-instance có thể giới hạn từng JVM, nhưng 20 instances nhân tổng hạn mức. Phải biết giới hạn là local hay cluster-wide.

---

## 25. Distributed locks mất: đừng dựa vào cache làm quyền tuyệt đối

Giả sử một job chỉ được một worker chạy:

~~~text
Worker A gets lock in Redis.
A starts long-running export.
Redis cluster loses all keys.
Worker B gets new lock.
A is still running.
~~~

Cả A và B có thể thực hiện export hoặc side effect.

### 25.1. TTL/lock không tự thu hồi worker cũ

Một worker bị pause có thể tỉnh lại sau khi lease hết hạn hoặc cache failover. Nó không tự biết mọi lock đã bị mất.

### 25.2. Fencing token

Nếu tác vụ sửa một resource quan trọng, có thể dùng token thế hệ tăng từ một nguồn cấp phát an toàn và buộc **nơi áp dụng side effect** từ chối token cũ.

~~~text
B obtains token 52.
Destination accepts writes only from token >= 52.

A still holds token 51.
A's later write -> rejected.
~~~

Một token generation được cấp chỉ trong Redis đã mất toàn bộ dữ liệu có thể reset hoặc trùng; đó không phải fencing đáng tin nếu nó cần monotonically increase qua disaster.

### 25.3. Lock khác idempotency

Dù chỉ một worker chạy tại một thời điểm, worker crash sau khi gửi payment nhưng trước ACK vẫn có thể chạy lại. Cần provider idempotency/reconciliation.

### 25.4. Lựa chọn thiết kế

Không dùng ephemeral cache như **nguồn quyền ghi duy nhất** cho operations đòi safety cao. Cần database transaction/CAS, durable coordinator, lease có fencing hoặc domain-specific unique constraint.

---

## 26. Idempotency keys mất: retry có thể gây ghi trùng

Một checkout API sử dụng:

~~~text
Idempotency-Key: checkout-9001
```

Nếu “đã xử lý `checkout-9001`” chỉ được lưu trong Redis, total loss có thể khiến retry được xem như yêu cầu mới.

### 26.1. Timeline nguy hiểm

~~~text
T1: Request K thanh toán thành công.
T2: Redis lưu K=SUCCESS.
T3: Response tới client bị mất.
T4: Cache cluster mất toàn bộ.
T5: Client retry K.
T6: API thấy K chưa tồn tại -> charge lần nữa.
~~~

Vấn đề không được chữa bằng cách thêm Redis replica nếu retention/failover policy vẫn có thể làm mất key.

### 26.2. Bảo vệ phù hợp

- Durable business request ledger trong authoritative storage.
- Unique request ID/transaction constraint.
- Provider idempotency key giữ ổn định.
- Read authoritative result trước khi retry.
- Atomicity giữa business update và idempotency record khi có thể.
- Retention bao phủ retry/callback/replay horizon.
- Reconciliation khi outcome không xác định.

### 26.3. Cache vẫn có thể tăng tốc idempotency lookup

Có thể cache kết quả request đã hoàn tất để trả nhanh. Nhưng sau cache miss, API phải **kiểm ledger bền** chứ không lập tức thực hiện side effect mới.

### 26.4. TTL không phải business expiration đơn giản

Nếu callback từ provider có thể đến sau 30 ngày, cache TTL 24 giờ không đủ để đảm bảo dedup suốt callback window. Không đưa ra một thời hạn duy nhất nếu chưa có provider/business contract.

---

## 27. Queue hoặc stream trong cache: nguy cơ mất công việc

Một ứng dụng có thể dùng Redis Streams, lists hoặc một broker-like cấu trúc để chứa job.

### 27.1. Redis List trong RAM

Nếu queue chỉ ở RAM và không có persistence/durable source khác, restart/loss có thể mất những jobs chưa xử lý.

### 27.2. Redis Streams

Redis Streams có consumer groups/pending entries theo semantics của Redis; nhưng durability của stream data vẫn phụ thuộc persistence/replication và topology, không tự trở thành log bền như một hệ broker có contract riêng.

### 27.3. Pub/Sub

Redis Pub/Sub không phải durable work queue cho subscribers offline theo mô hình phổ biến. Mất subscriber hoặc cluster có thể làm thông báo không được nhận.

### 27.4. Hợp đồng nhận job

Nếu HTTP API trả:

~~~text
202 Accepted
jobId=job-42
~~~

thì người dùng cần biết **ý định job đã được lưu bền tới đâu**, có thể tra cứu state/status và khi nào nó được thực thi. Chỉ enqueue vào RAM rồi trả 202 có thể không phù hợp nếu business cam kết không mất job.

### 27.5. Khôi phục

- Nếu durable job source tồn tại: replay theo checkpoint và idempotency.
- Nếu chỉ RAM: có thể không phục hồi được jobs đã mất.
- Nếu một phần jobs đã thực hiện side effects: reconciliation để tránh xử lý trùng.
- Nếu consumer acks trước DB commit: có nguy cơ mất công việc nghiệp vụ.
- Nếu DB commit trước ack: có thể redelivery, cần idempotency.

---

## 28. Bảo mật và quyền truy cập khi cache bị xóa

Một cache có thể lưu:

~~~text
permission:user-42 -> canView=TRUE
revokedToken:abc -> TRUE
acl:resource-17 -> [...]
```

### 28.1. Permission caching

Khi cache miss, nên xác minh từ một authoritative ACL/policy source phù hợp. Không mặc định “không có dữ liệu quyền -> cho phép”.

### 28.2. Revocation state

Nếu chỉ có denylist/revocation entries trong cache, mất cache có thể khiến token từng bị thu hồi được chấp nhận trở lại khi token vẫn còn hiệu lực về mặt chữ ký.

### 28.3. Failover có thể tạo stale-positive

Ngay cả khi cache không mất hết, replica mới có thể thiếu invalidation gần nhất, khiến quyền cũ sống lại. Vì vậy cơ chế authorization không thể chỉ dựa trên asynchronous cache replication khi threat model đòi immediate revocation.

### 28.4. Cleanup và PII

Warm-up không nên khôi phục hồ sơ đã bị xóa theo chính sách bằng cách dùng một snapshot cũ. Cần replay delete events/tombstones/consent state và tuân thủ retention.

### 28.5. Cache keys cũng có thể rò thông tin

Không đưa email, token hoặc thông tin nhạy cảm trực tiếp vào key/log/metrics khi không cần. Cache disaster recovery logs cũng phải tránh xuất payload PII.

---

## 29. Phân biệt mất cache với trả dữ liệu cũ sau failover

Hai kịch bản khác nhau:

### A. Total loss

~~~text
Redis GET returns NIL for all keys.
App reloads from authoritative DB.
~~~

Rủi ro chính: cold misses và mất state không thể tái tạo.

### B. Stale replica promoted

~~~text
Primary had version 12.
Replica had version 11.
Failover promotes replica.
Cache now returns version 11.
~~~

Rủi ro chính: dữ liệu **có tồn tại nhưng sai mới nhất**. API có thể không phát hiện vì đây là cache hit.

### 29.1. Cache hit không phải bằng chứng freshness

Nếu version 11 không được phép sau khi transaction version 12 đã commit và client được ACK, cache hit version 11 cần bị bypass/invalidated hoặc được phép stale theo contract.

### 29.2. Cache source version

Một key có thể lưu `{value, sourceVersion, refreshedAt}`. Nhưng cần cơ chế kiểm/source watermark để biết một cached version còn hợp lệ. Chỉ lưu version mà không bao giờ đối chiếu/invalidate không tự phát hiện stale.

### 29.3. Correctness-critical reads

Checkout, quyền truy cập và số dư có thể cần authoritative read/transaction. Không dùng cache response làm cơ sở duy nhất để cấp hàng/cho phép giao dịch khi invariant yêu cầu dữ liệu mới.

---

## 30. Multi-region cache: giảm latency nhưng tăng số điểm lệch

Sơ đồ:

~~~text
Region A: API A -> Redis A -> NoSQL source
Region B: API B -> Redis B -> NoSQL source/replica
```

### 30.1. Region-local caches có thể độc lập

Khi A cache một giá trị mới, B chưa chắc thấy ngay. TTL/invalidation/CDC quyết định độ trễ cập nhật theo thiết kế.

### 30.2. Cross-region failover

Nếu traffic chuyển từ A sang B nhưng Redis B chưa warm, DB B/source có thể bị cold miss storm dù Redis A vẫn đầy dữ liệu.

### 30.3. Không sao chép cache mutable tùy tiện giữa regions

Replication có thể lan stale values hoặc conflicts. Nếu nhiều regions cùng ghi cache, cần conflict semantics, source version và quy tắc ownership.

### 30.4. DR drills phải chuyển traffic thật trong staging

Test chỉ restart Redis instance trong cùng AZ không đại diện cho failover toàn region, DNS/routing TTL, cold caches ở region đích và origin capacity cross-region.

### 30.5. Data residency

Warm-up từ một source region khác có thể vi phạm dữ liệu residency hoặc làm tăng chi phí egress. Recovery plan cần tuân thủ quyền truy cập, region policy và băng thông.

---

## 31. Khôi phục cache từ backup: lợi ích và giới hạn

### 31.1. Restore snapshot có thể rút ngắn warm-up

Nếu cache có hàng triệu keys đắt để tính toán, snapshot giúp khôi phục một phần state nhanh hơn so với đọc toàn bộ NoSQL source.

### 31.2. Nhưng snapshot có thể stale

Snapshot lúc 09:00, restore lúc 10:00 có thể chứa:

- Giá đã thay đổi.
- Người dùng đã thu hồi quyền.
- Sản phẩm đã bị xóa.
- TTL không còn phù hợp.
- Session đã logout.
- Reservation đã hết hạn.
- Key prefix/schema version cũ.

### 31.3. Restore derived cache cần validation

Có thể chọn:

- Chỉ restore namespaces an toàn.
- Đặt namespace generation mới.
- Clear/migrate những keys nhạy cảm.
- Replay invalidation/change log từ checkpoint.
- Đối chiếu sourceVersion khi cần.
- Để TTL giới hạn staleness.

### 31.4. Backup không thay restore drill

Một snapshot tồn tại không chứng minh có thể restore trong thời gian cần, đủ CPU/RAM, đúng encryption keys và có ứng dụng tương thích để đọc.

### 31.5. Cache backup có thể mang dữ liệu cá nhân

Nếu backup chứa PII/sessions, backup/restore phải chịu cùng những yêu cầu access control, encryption và retention như nguồn dữ liệu liên quan.

---

## 32. Phục hồi không đồng nghĩa fill cache càng nhanh càng tốt

Một recovery controller có thể dựa vào signals:

~~~text
if DB p99 high:
    pause warm-up and reduce miss admission

if DB healthy and cache hit improving:
    slowly increase warm-up concurrency

if Redis evictions high:
    stop bulk loading; revisit memory sizing

if source replica lag high:
    avoid loading from stale replica when correctness requires fresh
```

### 32.1. Headroom

Giữ một phần origin capacity để xử lý business writes, recovery/repair và user-facing critical reads.

### 32.2. Ưu tiên nạp key thực sự nóng

Dùng historical request counts, sampling, access logs/metrics đã có hoặc precomputed hot sets. Tránh quét source toàn bộ chỉ vì biết danh sách tất cả keys.

### 32.3. Warm-up theo batch

Batch size và concurrency phải có giới hạn. Một batch quá lớn có thể gây network burst hoặc memory pressure.

### 32.4. Dừng trên tín hiệu lỗi

Warm-up có thể bị pause khi:
- DB throttles.
- Redis memory evictions tăng.
- API p99 vượt SLO.
- Retry amplification tăng.
- Replication/repair lag cao.
- Một partition/key bắt đầu thành hotspot.

### 32.5. Không warm dữ liệu nhạy cảm theo default

Một namespace chứa revocation/security state cần quy trình authoritative, không đơn giản lấy snapshot cũ để fill hàng loạt.

---

## 33. TTL, LRU/LFU eviction và cache memory exhaustion

### 33.1. TTL

Key hết hạn theo thời gian, bất kể còn memory hay không.

### 33.2. Eviction

Khi memory pressure, Redis hoặc cache library có thể loại key theo chính sách như LRU/LFU/TTL-aware hoặc từ chối ghi, tùy cấu hình.

### 33.3. Chính sách eviction ảnh hưởng workload

Nếu cache đầy:

- Các key nóng có thể vẫn còn nếu policy phù hợp.
- New keys có thể bị từ chối hoặc eviction.
- Cache refill có thể gây **churn** liên tục: nạp key A đẩy B, request B nạp lại đẩy A.

### 33.4. Đừng cấu hình `noeviction` như giải pháp correctness mặc định

Nếu `noeviction` làm cache writes bị reject, app phải biết đó là optional cache fill hay durable business operation. Không biến cache fill failure thành lỗi business nếu source đã trả dữ liệu đúng, nhưng cũng không nuốt lỗi khi cache đang là source duy nhất.

### 33.5. Đặt memory headroom

Memory cần cho keys, values, allocator fragmentation, replication buffers, persistence rewrite, connections, command buffers và workload peak. Đừng lấy kích thước JSON payload nhân số keys rồi coi là RSS tối đa.

---

## 34. Cache key design ảnh hưởng đường khôi phục

Một key thường nên ghi rõ:

~~~text
app:env:tenant:entity:identifier:schemaVersion
```

Ví dụ:

~~~text
shop:prod:tenant-7:product:prd-42:v3
```

### 34.1. Version hóa key

Khi đổi payload schema, có thể dùng key namespace/version mới để tránh app cũ decode sai.

### 34.2. Tenant isolation

Đừng để `product:42` bị dùng chung nếu `42` chỉ unique trong mỗi tenant. Mất cache rồi refill không được trộn dữ liệu giữa tenants.

### 34.3. Không chứa secrets

Tránh keys có raw access token hoặc email nếu có giải pháp hash/opaque identifiers phù hợp.

### 34.4. Key cardinality

Một key theo request ID hoặc timestamp quá chi tiết có thể tạo hàng triệu entries ít được tái sử dụng, làm hot keys bị eviction. Kế hoạch warm-up nên chọn key hữu ích, không copy toàn bộ namespace vô điều kiện.

### 34.5. Schema migration và fallback

Nếu cả apps v2/v3 chạy cùng lúc, versioned keys giúp tách serializer; nhưng mỗi version có cold miss riêng. Tính memory và origin load trong rolling deployment.

---

## 35. Cần giữ origin database healthy khi cache đang phục hồi

Một mô hình tối giản:

~~~text
User traffic -> API admission
                  |
                  v
             cache GET
              /     \
           hit       miss
           |          |
         return    origin gate
                      |
               +------+------+
               |             |
             permit        reject
               |             |
             DB read       503/429
               |
            cache fill
               |
             return
~~~

### 35.1. Origin gate trước query

Đặt semaphore/bulkhead ngay trước DB call, không sau khi đã tạo hàng nghìn futures/subscriptions.

### 35.2. Per-key single-flight trước hoặc trong origin gate

Giúp tránh cùng key dùng nhiều origin permits trong một process.

### 35.3. Deadline

Nếu một request đã chờ 400 ms trên HTTP deadline 500 ms, DB read 300 ms có thể không có ích. Không gửi request đã hết hạn vào origin chỉ để fill cache.

### 35.4. Cache circuit breaker

Khi cache không sẵn sàng, dừng thử mọi operation cache trong một khoảng có kiểm soát có thể giảm timeout overhead. Nhưng fallback DB cũng phải có limiter.

### 35.5. DB circuit breaker và fallback

Khi source quá tải, không chuyển toàn bộ reads sang một secondary yếu hơn rồi phá luôn vùng còn lại. Fallback phải có capacity và consistency contract phù hợp.

---

## 36. Metrics: theo dõi cache và nguồn cùng lúc

| Nhóm | Chỉ số | Vì sao cần |
|---|---|---|
| Cache availability | Node health, failover events | Biết cache endpoint có sẵn không |
| Cache hit/miss | Hit ratio theo namespace, tenant, endpoint | Đo cold start |
| Cache payload | Key count, memory, bytes/key | Dự đoán warm-up |
| Cache eviction | Evictions, expirations | Phân biệt thiếu memory với TTL |
| Replication | Replica lag, sync status | Ước lượng risk khi promote |
| Persistence | Last snapshot, AOF fsync latency/failures | Durability/recovery |
| Failover | Primary changes, routing redirects | Xác định sự cố topology |
| Origin | Reads/s, writes/s, per-shard load | Bảo vệ database |
| Origin latency | p95/p99, connection wait | Xem cold misses gây overload |
| Stampede | Concurrent loads/key, coalescing ratio | Phát hiện hot-key herd |
| Admission | Accepted/rejected/bulkhead utilization | Biết load shedding có hiệu lực |
| Retry | Attempts per logical request | Phát hiện amplification |
| Warm-up | Keys/s, success, remaining hot set | Đánh giá tiến độ |
| Staleness | Version mismatch, stale reads | Không chỉ nhìn hit rate |
| Business | Double charge, duplicate order, invalid auth | Phát hiện mất state quan trọng |
| Sessions | Authentication errors, forced logout rate | Tác động người dùng |
| Security | Rate-limit bypass, revocation misses | Tác động khi cache state mất |
| Recovery | Time to stable p99/hit-rate | RTO thực tế |

### 36.1. Không đo hit ratio một mình

Có thể cache đạt 95% hit nhưng toàn bộ 5% misses thuộc một shard nóng gây quá tải. Quan sát **per-key/per-shard origin load** và p99.

### 36.2. Misses vs intentional bypass

Khi circuit breaker tắt Redis, app có thể không gọi cache GET; metric cache miss dựa trên Redis responses không còn đo hết origin demand. Cần `cache_bypass_total` và `origin_read_attempts_total`.

### 36.3. Warm-up thành công nhưng evictions cao

Nếu nạp 100.000 keys/s nhưng cache eviction cũng tăng tương ứng, hit rate có thể không cải thiện. Đo memory pressure và working set.

### 36.4. SLO critical

Một dashboard cache xanh khi Redis primary healthy nhưng checkout vẫn double-charge do ledger mất là chưa đủ. **Business correctness phải được đo riêng.**

---

## 37. Ma trận các kịch bản mất cache

| ID | Kịch bản | Dữ liệu có thể mất | Kết quả cần kiểm |
|---|---|---|---|
| F01 | Restart một node cache thuần derived | Entries cục bộ | Read fallback đúng, no data loss nguồn |
| F02 | Failover primary khi write chưa tới replica | Một số cache writes | Stale/miss behavior theo contract |
| F03 | Full cluster empty | Mọi derived keys | DB không sập vì cold miss |
| F04 | Full cluster empty giờ cao điểm | Key nóng | Admission/coalescing hoạt động |
| F05 | RDB restore snapshot cũ | Entries sau snapshot | Staleness và invalidations đúng |
| F06 | AOF lỗi/corrupt ở test | Entries chưa durable | Restore plan/RPO evidence |
| F07 | Cache unavailable 10 phút | Không phục vụ cache | Graceful degradation |
| F08 | L1 còn cache, L2 mất | L1 có thể stale | Namespace version/invalidation |
| F09 | Session-only Redis lost | Sessions | Auth re-login impact/SLO |
| F10 | Rate-limit key lost | Counters | Security fallback đúng |
| F11 | Revocation key lost | Revocation data | Không cho phép token không hợp lệ |
| F12 | Lock key lost | Ownership metadata | Stale worker không side effect |
| F13 | Idempotency key lost | Dedup metadata | Không double-charge/order |
| F14 | Write-behind buffer lost | Unflushed writes | RPO hoặc durable replay |
| F15 | Queue jobs only in Redis lost | Pending jobs | Reconciliation/job loss |
| F16 | Cache recovers but DB still slow | Origin capacity | Warm-up throttling |
| F17 | Hot key expired + many clients | Cache entry | Single-flight/coalescing |
| F18 | Cache entries evicted continuously | Hot working set | Memory capacity/churn |
| F19 | Reorder invalidations after failover | Version freshness | No stale overwrite |
| F20 | Cross-region traffic shift | Region B cold cache | DR admission/latency |
| F21 | Backup restores deleted PII | Old keys | Deletion security invariant |
| F22 | Cache response timeout after write | Unknown outcome | Stable ID/reconciliation |
| F23 | Schema version changes during restore | Serialized payload | Versioned keys/decoder |
| F24 | Client retries GET after cache failure | Extra attempts | Retry budget |
| F25 | All app JVM local caches restart | L1 cache entries | Origin surge prevention |
| F26 | CDN/L1 + Redis L2 fail together | Multiple cache tiers | Source capacity by tier |
| F27 | Cache warmed from stale read replica | Old values | Source/version validation |
| F28 | Warm-up tool scans all records | Source I/O pressure | Pause/recovery SLO |
| F29 | Restore has expired TTL keys | Old cache state | Expiry policy correct |
| F30 | Network partition splits cache cluster | Inconsistent routing | No unsafe writes/authority |

Không phải mọi test cần chạy trên production. Những sự cố phá trạng thái như `FLUSHALL`, network partition, disk corruption và failure injection **chỉ chạy trong môi trường đã được phê duyệt**.

---

## 38. Viết kịch bản F03: toàn bộ cache mất nhưng DB còn

### Setup

~~~text
3 Java API instances.
1 derived Redis cache cluster.
NoSQL source đầy đủ.
Product read workload 2.000 logical req/s.
Cache hit ratio trước lỗi: 95%.
~~~

### Steps

1. Đo origin requests/s và API p99 baseline.
2. Tạo full cache loss có kiểm soát trong test env.
3. Xác nhận cache miss/bypass tăng.
4. Kiểm origin limiter và fast rejection.
5. Kiểm hot-key single-flight.
6. Phục hồi cache cluster endpoint.
7. Warm theo từng đợt dưới DB capacity budget.
8. Theo dõi hit ratio, queue wait, retries và evictions.
9. So kết quả key cohort với authoritative source.
10. Đưa traffic về mức bình thường khi SLO đạt.

### Oracle

- Không mất Product records trong source.
- Không trả sai tenant hoặc stale value vượt policy.
- Origin QPS/in-flight nằm trong giới hạn dự kiến.
- Không có queue vô hạn/OOM.
- Rejected requests có typed outcome.
- Recovery đủ nhanh theo RTO đã đặt.
- Warm-up không gây DB outage thứ hai.

### Không đủ để pass

Chỉ thấy “Redis ping PONG” và “server API vẫn còn chạy” không chứng minh recovery thành công.

---

## 39. Viết kịch bản F02: failover làm mất cache write gần nhất

### Setup

~~~text
A: cache primary
B: cache replica
Source DB: authoritative Product version 12
Cache on A: version 12
B temporarily: version 11
~~~

### Steps

1. Tạo replication lag có kiểm soát trong staging.
2. Cập nhật nguồn và cache theo policy đã quy định.
3. Cho A mất quyền trước khi B nhận cache update.
4. B được promote theo engine protocol.
5. Client đọc cache từ B.
6. So cache value/version với source.
7. Kiểm invalidation/fallback protocol.
8. Đo thời gian sửa stale state.

### Oracle

- Nếu policy cho phép stale trong X giây, test đo thời gian thực.
- Nếu policy không cho phép stale, đường critical read phải bypass/xác minh nguồn.
- Không dùng cache value version 11 để ghi đè source version 12.
- Client driver xử lý topology refresh/redirect đúng.
- Những writes đã acknowledged theo source business contract không được hiểu lại từ cache.

---

## 40. Viết kịch bản F13: mất idempotency cache

### Setup

~~~text
Payment provider chargeId=P123 was successful.
Order source has orderId=O99.
Redis idempotency key K=checkout-99.
~~~

### Steps

1. Client gửi checkout K.
2. Chờ provider đã có charge theo contract.
3. Mô phỏng response lost.
4. Xóa toàn bộ **test cache**.
5. Retry cùng K.
6. Đối soát transaction ledger authoritative.
7. Kiểm số provider charges và order records.
8. Kiểm trạng thái trả cho client.

### Oracle

- Tối đa một charge cho cùng business intent theo provider contract.
- Tối đa một Order confirmed theo invariant.
- Nếu outcome chưa rõ, hệ giữ `UNKNOWN/PENDING` và reconcile.
- Không tạo ID mới chỉ vì Redis không còn key.

### Kết luận quan trọng

Một Redis cache thất lạc **không được phép xóa bằng chứng** nghiệp vụ đã xử lý nếu bằng chứng đó cần chống double-charge.

---

## 41. Viết kịch bản F12: lock mất, stale worker tiếp tục chạy

### Setup

~~~text
Worker A obtains job lock, ownerGeneration=41.
Cache cluster loses lock keys.
Worker B starts same job, generation=42 from safe authority.
Worker A resumes after a pause.
~~~

### Oracle

- Destination từ chối writes của generation 41 sau khi 42 có quyền.
- Job output không bị ghi đè bởi worker cũ.
- Nếu có external side effects, idempotency bảo vệ duplicates.
- Cần audit evidence để phân biệt hai workers.

### Bẫy kiểm thử

Nếu generation counter cũng nằm trong Redis vừa mất state, nó có thể reset về 1. Test phải bảo đảm token được cấp bởi một authority có thứ tự hợp lệ **qua sự cố**.

---

## 42. Viết kịch bản F21: restore snapshot cũ chứa dữ liệu đã xóa

### Setup

~~~text
T0: Snapshot cache có user profile P.
T1: User data được xóa theo chính sách.
T2: Cache cluster mất.
T3: Restore snapshot T0.
~~~

### Oracle

- Dữ liệu P không được tiếp tục phục vụ trái policy.
- Cache cần xóa/bỏ qua những entries không hợp lệ.
- Quy trình revalidate với source/deletion log/consent state phù hợp.
- Backup/restore access được audit.
- Không hồi sinh quyền bị thu hồi hoặc token đã logout.

### Bài học

**Restore kỹ thuật thành công có thể là một thất bại compliance** nếu snapshot cũ trái với trạng thái xóa/thu hồi hiện hành.

---

## 43. Thử cold-start capacity và Little's Law

Giả sử:

~~~text
Traffic:            6.000 reads/s
Cache hit normal:   95%
DB read time mean:  30 ms
Cold read mean:     150 ms under load
~~~

### 43.1. Baseline origin load

\[
Q_{DB}=6000(1-0.95)=300\text{ reads/s}.
\]

Trung bình origin in-flight ở trạng thái ổn định:

\[
L=300\times0.03=9.
\]

### 43.2. Cache mất, nếu DB vẫn có thể hoàn thành 6.000/s

Khi mean response thành 150 ms:

\[
L=6000\times0.15=900.
\]

Nhưng điều kiện **“DB vẫn hoàn thành 6.000 reads/s” có thể không đúng**. Nếu capacity thật chỉ 800/s, offered load 6.000/s làm backlog tăng; không dùng công thức ổn định để suy throughput tự đạt.

### 43.3. Cần budget

Nếu origin có thể tiếp nhận bền vững 800/s, bạn phải:

- Cho một phần lưu lượng qua.
- Dùng stale-safe responses/fallback cho phần được phép.
- Reject/defer phần còn lại.
- Dùng single-flight để giảm origin requests cho hot keys.
- Warm từ từ khi database còn headroom.
- Không retry toàn bộ 5.200/s bị từ chối ngay lập tức.

### 43.4. Không lấy `DB max connections` làm throughput

Connection count chỉ là một resource. Throughput còn phụ thuộc CPU, I/O, index, quorum, hot partition và request cost.

---

## 44. Runbook khi cache cluster mất toàn bộ

### Pha 1 — Xác nhận loại sự cố

- Cache endpoint mất kết nối hay mọi key thực sự bị xóa?
- Cụm có đang failover?
- L1 caches còn dữ liệu không?
- Cache persistence/replicas/backups có sẵn không?
- Namespace nào giữ state derived, namespace nào giữ business state?
- Có dấu hiệu delete/corruption/security incident không?

### Pha 2 — Bảo vệ database nguồn ngay lập tức

- Tạm giảm hoặc tắt warm-up jobs.
- Giới hạn origin reads/s và in-flight.
- Ưu tiên authentication/checkout/read-critical theo chính sách.
- Hoãn analytics/report/exports.
- Giảm retries, dùng jitter/deadlines.
- Kiểm origin per-shard capacity.
- Tránh queue vô hạn.

### Pha 3 — Đánh giá mất dữ liệu không thể tái tạo

Kiểm:

~~~text
sessions
idempotency ledger
rate limiting
revocation
locks/leases
pending jobs
write-behind buffers
temporary upload state
outbox/callback cursors
```

Nếu những namespace này có state duy nhất, mở incident xử lý correctness/security; không chỉ chạy script fill sản phẩm.

### Pha 4 — Khôi phục cache hạ tầng

- Dùng cơ chế failover/restore chính thức của engine.
- Xác minh topology, routing, auth/TLS, DNS/driver discovery.
- Kiểm memory/headroom, persistence và replication.
- Không tự thao tác phá hủy backup/AOF để “chạy nhanh”.
- Không cho app truy cập vào instance chưa đạt điều kiện an toàn.

### Pha 5 — Quyết định restore hay rebuild

**Restore** khi state hữu ích, snapshot hợp lệ và có thể đối soát.

**Rebuild from source** khi source bền, cache chỉ là dẫn xuất, restore có thể stale/không đáng giá.

**Manual reconciliation** khi business state/callbacks chưa rõ outcome.

### Pha 6 — Warm-up có ngân sách

- Tập key nóng.
- Bounded batch/concurrency.
- TTL jitter.
- Version validation.
- Per-tenant fairness.
- Pause khi DB p99/throttling xấu.
- Theo dõi cache hit ratio và evictions.

### Pha 7 — Mở traffic từng bước

- Mở dần read traffic.
- Giữ critical write capacity.
- Đo error, origin QPS, queue wait, p99.
- Kiểm invalidations/near-cache freshness.
- Không đóng incident khi cache ping khỏe nhưng API vẫn timeout.

### Pha 8 — Đối soát business correctness

- Duplicate payment/order?
- Session/login impact?
- Rate limit/security failures?
- Lock stale owner?
- Queue jobs lost?
- PII resurrected?
- Source/cache version mismatch?
- Outbox/CDC lag?

### Pha 9 — Sau sự cố

Lưu timeline, config, failure domain, RPO/RTO thực tế, peak origin amplification, warm-up duration, missing critical state, các kiến trúc cần thay đổi và những tests phải bổ sung.

**Không chủ động `FLUSHALL`, phá replica hoặc xóa snapshot trên production để “thử recovery” nếu chưa có quy trình và phê duyệt.**

---

## 45. Những hiểu lầm thường gặp

| Ngộ nhận | Vì sao sai | Cách xử lý |
|---|---|---|
| “Cache mất không sao vì luôn có DB.” | Origin có thể không chịu 100% cold misses | Capacity model + admission |
| “Cache hit 99% càng an toàn.” | Cold amplification có thể tới 100× | DR load test |
| “TTL 1 ngày nghĩa key sống 1 ngày.” | Eviction/crash vẫn xóa trước | Hiểu expiry vs durability |
| “Redis có replica thì mọi ACK đều bền.” | Replication có thể async | Chọn RPO/contract đúng |
| “Sentinel cung cấp synchronous consensus.” | Failover không thay write semantics | Đánh giá replication windows |
| “Redis WAIT đảm bảo write sẽ sống qua mọi failover.” | Không là general durable consensus commit | Không lưu business state duy nhất |
| “AOF everysec mất tối đa đúng một giây trong mọi lỗi.” | Crash/storage/network khác nhau | Kiểm failure model |
| “RDB là backup mọi write gần nhất.” | Snapshot có checkpoint cũ | RPO và restore tests |
| “Managed cache tự có DR đầy đủ.” | Tier/cấu hình khác nhau | Kiểm service contract |
| “Memcached có tính bền như DB.” | Thường ephemeral | Chỉ lưu derived values |
| “Caffeine local cache được replicate.” | Mỗi JVM có state riêng | L1 invalidation strategy |
| “Redis L2 mất thì L1 chắc đúng.” | Có thể bỏ lỡ invalidation | Version/epoch/freshness |
| “Write-through là atomic DB+cache.” | Hai hệ độc lập có failure window | Transaction/outbox/invalidation |
| “Write-behind ACK chắc chắn vào DB.” | Buffer chưa flush có thể mất | Durable log/source |
| “Cache GET miss nghĩa record không tồn tại.” | Cache lỗi/TTL/eviction | Read authoritative source |
| “Negative cache mọi 404/timeout đều tốt.” | Timeout không là not-found | Typed classification |
| “Single-flight local bảo vệ toàn cụm.” | Mỗi JVM vẫn load riêng | Per-key/global budget |
| “TTL jitter chữa full cache outage.” | Mọi key cùng biến mất | Admission + warm-up |
| “Warm-up càng nhanh càng tốt.” | Có thể phá origin và gây eviction | Throttle theo p99 |
| “Stale cache luôn chấp nhận được.” | Quyền/tiền/tồn kho có invariant | Theo data class |
| “Cache lock TTL bảo vệ exclusive write tuyệt đối.” | Stale worker tiếp tục chạy | Fencing + business idempotency |
| “Mất rate limiter thì cho qua hết.” | Có thể mở cửa abuse | Per-endpoint fallback |
| “Mất cache session chỉ làm chậm login.” | Có thể logout diện rộng | Session RPO/UX plan |
| “Idempotency key chỉ cần Redis.” | Mất cache làm duplicate effects | Durable ledger |
| “Mọi Redis stream là durable broker.” | Persistence/replication vẫn quyết định | Xem message contract |
| “Restore snapshot cũ luôn tốt.” | Có thể hồi sinh stale/PII | Validate/reconcile |
| “Cache healthy nghĩa incident đóng.” | Origin/business anomalies còn | End-to-end SLO + correctness |
| “Chuyển region là có hot cache.” | Region mới có thể cold | DR capacity plan |
| “Tăng connection pool là đủ.” | Hot shard/CPU/IOPS có giới hạn | Bounded load + data model |
| “Retry 3 lần luôn giúp recovery.” | Retry amplification lúc origin yếu | Budget/backoff/jitter |

---

## 46. Bài tập 1: phân loại key sau total loss

Một cụm Redis có:

~~~text
product:42                  -> product detail from MongoDB
session:user-99             -> logged-in session
ratelimit:ip-10             -> login attempt count
revoked:token-123           -> token revoked
lock:invoice-runner         -> exclusive job lock
idempotency:checkout-9001   -> dedup result
queue:send-receipts         -> pending jobs
recommendations:tenant-7    -> derived expensive computation
```

Hãy trả lời:

1. Key nào là dữ liệu **derived**, key nào có thể là **authoritative state**?
2. Key nào có thể phục hồi tự động từ database?
3. Key nào có ảnh hưởng security?
4. Key nào cần durable request ledger?
5. Key nào cần fencing token ngoài cache?
6. Nếu queue mất, có thể khôi phục từ source events hay không?
7. Những endpoint nào nên fail-open/fail-closed?
8. Thiết kế một bảng RPO/RTO riêng theo namespace.

---

## 47. Bài tập 2: tính mức tăng tải nguồn

Cho:

~~~text
API GET traffic: 12.000 requests/s
Cache hit ratio: 98%
Origin sustainable capacity under SLO: 1.200 reads/s
```

1. Tính origin reads/s bình thường.
2. Tính origin reads/s ngay khi cache về 0% hit.
3. Tính amplification factor.
4. Nếu không có single-flight/admission, số reads/s vượt capacity bao nhiêu?
5. Nếu 70% traffic cùng hỏi 50 keys nóng, single-flight có thể giúp phần nào?
6. Tại sao vẫn cần giới hạn tổng source reads/s?
7. Vẽ kế hoạch recovery giữ p99 trong điều kiện đã đặt.

**Gợi ý:** baseline \(12\,000\times0.02=240\) reads/s. Cold demand 12.000/s, tức **50 lần** baseline và 10 lần origin capacity.

---

## 48. Bài tập 3: RDB, AOF và failover

Một Redis deployment có:

~~~text
RDB snapshot mỗi khoảng theo cấu hình.
AOF appendfsync everysec.
Primary A, replica B.
Replication async.
```

1. Dữ liệu nào có thể thiếu khi restore RDB?
2. AOF có giúp giảm cửa sổ mất gì?
3. Có được hứa RPO=0 tuyệt đối không?
4. Nếu A ACK write trước khi B nhận, rồi B được promote, chuyện gì có thể xảy ra?
5. `WAIT` giúp gì, và không đảm bảo những gì?
6. Nếu A/B và backups cùng nằm trong một failure domain, rủi ro gì?
7. Nếu cache chỉ chứa product details, có cần persistence như business DB không?
8. Nếu cache chứa job queue và session state, câu trả lời thay đổi thế nào?

---

## 49. Bài tập 4: cache-aside và stale race

Cho timeline:

~~~text
R reads Product version 5 from source.
W commits Product version 6.
W invalidates cache.
R caches version 5 after invalidation.
```

1. Vì sao invalidation sau DB commit chưa đủ?
2. TTL ngắn có giải quyết ngay yêu cầu strong freshness không?
3. Thiết kế version-aware cache value.
4. Atomic compare-and-set ở cache cần ở đâu?
5. Nếu invalidation event bị mất trong failover, làm sao khắc phục?
6. Với product display name, stale 30 giây có thể được chấp nhận không?
7. Với current price được dùng chốt thanh toán, chính sách phải khác thế nào?

---

## 50. Bài tập 5: xây service Java bảo vệ origin

Dựa trên ví dụ `ProductService`, hãy bổ sung:

1. Cache get/put latency metrics.
2. Circuit breaker cho cache để bypass nhanh khi Redis outage.
3. Per-key single-flight local.
4. Per-tenant origin permits.
5. Deadline propagation.
6. Bounded retries cho origin transient failures.
7. Negative cache TTL ngắn.
8. Cache entry có `sourceVersion`.
9. Source failure trả lỗi phù hợp, không biến thành not-found.
10. Test cache outage đồng thời 1.000 reads của một hot key.
11. Test `finally` release permits dù source throw.
12. Test source DB returns old/new version trong lúc invalidation.

Chú ý: các thao tác đổi business state phải dựa trên **authoritative source**, không dựa trên ProductCache.

---

## 51. Bài tập 6: thiết kế DR drill cho full cache loss

Một hệ có:

~~~text
20 app instances
1 Redis Cluster
MongoDB sharded source
3 regions of user traffic
Cache hit ratio=96%
Login sessions also in Redis
Inventory checkout is critical
Hourly analytics export
```

Yêu cầu:

- Phân loại namespace của Redis.
- Tính cold miss amplification.
- Xác định origin capacity theo shard.
- Đặt per-tenant/global admission.
- Ưu tiên inventory write.
- Kịch bản login storm sau session loss.
- Fallback cho analytics/recommendations.
- Phương pháp warm-up hot keys.
- Redis topology/persistence/restore plan.
- Metrics p95/p99, retries, DB throttling, cache evictions.
- Đánh giá recovery completion bằng business correctness.
- Ghi timeline/runbook/postmortem.

Không tiến hành phá dữ liệu cache trên production khi chưa có phê duyệt.

---

## 52. Bài tập 7: kiểm tra distributed lock và payment retry

Một worker sử dụng lock Redis để thực hiện payment settlement:

~~~text
A gets lock.
A calls provider and payment is captured.
Redis loses lock key.
B gets lock and calls provider.
A resumes.
```

Hãy thiết kế:

1. Fencing token cấp thế nào để không reset qua Redis disaster?
2. Provider idempotency key giữ thế nào?
3. Durable ledger ghi payment result ở đâu?
4. Nếu provider timeout sau capture, outcome là gì?
5. Nếu A/B cùng callback, làm sao ngăn double settlement?
6. Nếu queue job mất cùng Redis, có recovery source không?
7. Test nào chứng minh side effects không bị nhân đôi?
8. Khi nào cần manual reconciliation?

---

## 53. Bài tập 8: so sánh restore và rebuild

Một snapshot Redis được tạo 30 phút trước failure. Trong 30 phút đó:

~~~text
Product price changed.
100 accounts logged out.
50 tokens were revoked.
20.000 new product cache entries were created.
A batch of recommendation scores was recomputed.
```

1. Những namespace nào an toàn để restore nguyên xi?
2. Những namespace nào phải revalidate với source?
3. Khi restore, key TTL nào có thể đã hết hạn?
4. Làm sao không phục hồi revocation/authorization state trái policy?
5. Nếu có CDC invalidation log, sử dụng checkpoint nào?
6. Nếu cache chỉ làm derived product cache, rebuild có ưu điểm gì?
7. Nếu origin đang phục hồi sau DR, warm-up nên giới hạn thế nào?

---

## 54. Checklist trước khi coi cache là thành phần chịu được sự cố

- [ ] Mọi namespace cache đã được phân loại derived vs authoritative.
- [ ] Nguồn dữ liệu authoritative cho mỗi field/key được xác định.
- [ ] RPO/RTO được viết theo failure model chứ không suy từ replica count.
- [ ] TTL, eviction, persistence, replication và failover được phân biệt.
- [ ] Redis RDB/AOF/fsync settings có owner và runbook.
- [ ] Backups/restore được diễn tập; có failure-domain separation.
- [ ] Đã xem khả năng mất ACKed cache writes khi replica lag.
- [ ] Không dùng Redis `WAIT` như một cam kết durable consensus chung.
- [ ] Write-behind có durable log hoặc RPO chấp nhận được.
- [ ] Session/login loss có kịch bản vận hành.
- [ ] Idempotency/payment ledger không chỉ dựa trên ephemeral cache.
- [ ] Security revocation/rate limiting có fail-safe policy.
- [ ] Distributed locks dùng fencing khi có side effects quan trọng.
- [ ] Queue trong cache có persistence và replay semantics rõ.
- [ ] Near-cache L1 có invalidation/epoch và stale policy.
- [ ] Cache-aside fill không ghi lùi source version.
- [ ] Missing key khác cache error và source not-found.
- [ ] Origin capacity được tính từ cache hit ratio.
- [ ] Có global/per-tenant/per-shard origin admission.
- [ ] Có single-flight, TTL jitter và bounded retries.
- [ ] Warm-up không vượt headroom và có thể pause.
- [ ] Critical business writes được ưu tiên so với warm-up reads.
- [ ] SLO theo p99/goodput, không chỉ ping Redis.
- [ ] Metrics gồm evictions, replica lag, persistence và origin load.
- [ ] Restore không hồi sinh deleted data/PII.
- [ ] DR drill có toàn cụm cold, failover và cross-region shift.
- [ ] Incident chỉ đóng sau đối soát correctness.

---

## 55. Tổng kết

**Độ bền và failover của cache không thể được đánh giá chỉ bằng việc cache có bao nhiêu replica hay đã bật AOF hay chưa.** Phải xem cache đang giữ **bản sao có thể tái tạo** hay **dữ liệu duy nhất quyết định nghiệp vụ**, và hệ có còn an toàn khi cache biến mất hoàn toàn hay không.

Những điều cốt lõi:

1. **Dữ liệu dẫn xuất có thể mất mà không làm mất dữ liệu nguồn**, nhưng vẫn có thể khiến API/NoSQL database quá tải nghiêm trọng.
2. **TTL/eviction, persistence, replication, failover và backup là những cơ chế khác nhau**. Không dùng một cơ chế để suy bảo đảm của cơ chế khác.
3. **Redis primary–replica thường replication bất đồng bộ**; một write đã ACK trên primary có thể không tồn tại trên replica được promote.
4. **RDB/AOF giúp phục hồi trong phạm vi cấu hình**, nhưng không tạo durability tuyệt đối cho mọi failure mode và không thay transaction/business ledger.
5. **Total cache loss làm hit ratio tụt gần 0**, đẩy lưu lượng về nguồn; ở hit ratio 98%, tải origin ban đầu có thể tăng khoảng **50 lần** theo mô hình đơn giản.
6. **Origin protection là bắt buộc**: admission, bounded concurrency, single-flight, TTL jitter, retry budget và load shedding.
7. **Warm-up phải có ngân sách** và ưu tiên hot keys; nạp mọi key ngay có thể gây database outage thứ hai.
8. **Mất session, idempotency, revocation, locks hoặc queue không phải “cache miss bình thường”**. Những state đó cần nguồn authoritative/durable, security policy và reconciliation.
9. **Restore có thể hồi sinh dữ liệu cũ**; phải kiểm version, invalidation, TTL và deletion/PII contract.
10. **Khôi phục chỉ hoàn tất khi cả availability lẫn correctness trở lại**, không phải chỉ khi Redis trả `PONG`.

**Câu cần nhớ: “Cache nên giúp hệ nhanh hơn khi nó còn hoạt động, nhưng không được âm thầm trở thành nơi duy nhất giữ tính đúng đắn của hệ. Hãy thiết kế để mất toàn bộ cache vẫn biết dữ liệu nào còn, nguồn nào chịu được tải, ai được phép ghi và phục hồi thế nào mà không tạo lỗi nghiệp vụ mới.”**
