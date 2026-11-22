# Diễn tập sự cố toàn miền lỗi và đánh giá khả năng tiếp tục phục vụ

## 1. Tình huống mở đầu: ba bản sao nhưng vẫn không ghi được đơn hàng

Một hệ thống đặt hàng Java dùng một cụm cơ sở dữ liệu NoSQL có ba bản sao:

```text
                  Region R1

      Zone A          Zone B          Zone C
    +---------+     +---------+     +---------+
    | DB n1   |     | DB n2   |     | DB n3   |
    | replica |<--->| replica |<--->| replica |
    +---------+     +---------+     +---------+
         ^               ^               ^
         |               |               |
     App pool A      App pool B      App pool C
```

Đội vận hành đã thử tắt tiến trình database trên n1. Sau một thời gian ngắn, hệ thống tự chọn leader mới hoặc điều chỉnh routing và tiếp tục chạy. Bài kiểm tra được đánh dấu “high availability: passed”.

Một tháng sau, **toàn bộ Zone A** bị cô lập khỏi Zone B/C trong một sự cố hạ tầng. Khác với thử tắt n1, lần này:

- Nhiều application instances ở Zone A vẫn chạy và vẫn gửi requests.
- Các kết nối liên vùng bị timeout theo những hướng khác nhau.
- Load balancer vẫn có thể gửi traffic đến app ở Zone A do health check chỉ kiểm tra process.
- Một số clients giữ DNS cũ, pools cũ hoặc kết nối đến leader cũ.
- CDC worker, cache, authentication service hoặc metrics exporter cũng đặt tại Zone A.
- Dịch vụ phải giải quyết **write timeout có kết quả chưa rõ**: request đã commit hay chưa?

Cuối cùng, số bản sao là ba nhưng một số người dùng vẫn không checkout được. Một replica-test đơn lẻ không mô phỏng được **sự cố toàn miền lỗi** (*fault-domain failure*).

Vấn đề cốt lõi của bài học:

> **Không chỉ hỏi database còn bao nhiêu nodes, mà phải hỏi khi mất toàn bộ một miền lỗi thì những request nghiệp vụ cụ thể nào vẫn có thể hoàn tất đúng, trong bao lâu, với mức mất dữ liệu hoặc dữ liệu cũ nào được chấp nhận.**

## 2. Mục tiêu học tập

Sau bài này, bạn cần:

1. Phân biệt **sự cố một node**, **mất một Availability Zone (AZ)**, **mất region**, **network partition**, **mất control plane** và **mất dependency chung**.
2. Vẽ dependency map đủ chi tiết để tìm **shared failure domains** của ứng dụng, database, cache, broker, DNS, KMS, secret manager và observability.
3. Tính và giải thích khả năng còn quorum theo **replica placement, voter placement, read/write consistency**.
4. Hiểu **RTO, RPO, MTTD, MTTR, error budget, degraded-mode contract** và cách đo chúng trong diễn tập.
5. Thiết kế game day/chaos experiment có **hypothesis, blast radius, approvals, guardrails, abort criteria** và phương án rollback.
6. Phân biệt **availability thật từ client** với việc một node hoặc health endpoint vẫn còn trả 200.
7. Đánh giá read/write correctness, linearizability/freshness, idempotency, duplicate effects và ambiguous writes trong failover.
8. Thực hành với các loại NoSQL: MongoDB, Cassandra, Redis, DynamoDB, Elasticsearch/OpenSearch và các hệ partitioned/leaderless khác.
9. Kiểm tra ảnh hưởng tới **CDC, event pipeline, cache, derived read models, backup và restore**.
10. Tổng hợp evidence để quyết định cụm đáp ứng yêu cầu hay phải thay kiến trúc/runbook/capacity.

## 3. Miền lỗi là gì?

**Miền lỗi** (*fault domain*) là tập tài nguyên có thể bị ảnh hưởng đồng thời bởi một sự cố chung. Miền lỗi phụ thuộc hạ tầng thực tế và không chỉ là tên logic.

| Miền lỗi | Ví dụ | Rủi ro |
|---|---|---|
| Process | Một JVM hoặc mongod bị crash | Một service instance không phục vụ |
| Host/VM | OS, disk, NIC hoặc hypervisor lỗi | Nhiều processes cùng mất |
| Rack/ToR switch | Nguồn điện hoặc switch của một rack | Nhiều hosts mất liên lạc |
| AZ/datacenter zone | Power, networking hoặc dependencies của một AZ | Database và app nodes cùng ảnh hưởng |
| Region | Networking/control infrastructure rộng | Tất cả AZ trong region có thể ảnh hưởng |
| Network segment | DNS, firewall, route, MTU, packet loss | Các nodes còn chạy nhưng không liên lạc |
| Control plane | Autoscaling, orchestration API, deployment, IAM control APIs | Data plane có thể còn nhưng không scale/repair được |
| Shared dependency | KMS, DNS resolver, identity provider, broker, cache | Nhiều AZ cùng thất bại dù DB trải đều |
| Organization/process | Mất quyền break-glass, operator runbook, key | Không thể vận hành/restore khi sự cố |

### Đừng đồng nhất AZ với một máy chủ

AZ thường là một miền hạ tầng riêng có ý nghĩa cho kiến trúc, nhưng **mức cô lập cụ thể phụ thuộc cloud/provider và deployment**. Một managed NoSQL multi-AZ có thể che topology vật lý, trong khi self-managed cluster cần thiết kế placement chủ động.

### Miền lỗi có thể chồng lấp

```text
                    Region
        +-------------+-------------+
        |             |             |
      Zone A        Zone B        Zone C
        |             |             |
  app + DB node app + DB node app + DB node
        \             |             /
         \            |            /
           Shared DNS / KMS / IAM
```

Ba AZ có thể cùng phụ thuộc một endpoint/service region-level. Không có nghĩa cứ “ba AZ” thì chịu được **mọi** lỗi chung.

## 4. Sự cố node khác sự cố toàn miền lỗi như thế nào?

### Test đơn node

```text
Node n1 down
n2 and n3 retain normal connectivity
Clients can reconnect through normal network
```

Nhiều triển khai phục hồi khá dễ trong tình huống này.

### Test toàn AZ

```text
Zone A down or isolated
  DB n1 unavailable
  app-A unavailable or partitioned
  cache-A unavailable
  local load balancer targets may still be stale
  DNS/network changes may lag
  producers/CDC tasks in A may stop
```

Số thành phần hỏng và những điểm timeout tăng lên đáng kể.

### Test network partition

```text
Zone A                         Zones B + C
DB n1 alive                    DB n2,n3 alive
App A alive                    App B/C alive
     X  inter-zone traffic  X
```

**Hai phía đều có process chạy**, nhưng không thể nói chuyện. Đây là tình huống đặc biệt nguy hiểm nếu clients vẫn tin một leader cũ, nếu thiếu fencing, hoặc nếu nghiệp vụ cho phép hai phía ghi cùng một logical resource mà không có conflict protocol.

### Test region disaster

```text
Region R1 unavailable
R2 standby/read-only/active? 
DNS/routing cutover?
Data replication R1 -> R2 lag?
KMS and secrets available in R2?
```

Region disaster cần đánh giá một kiến trúc **cross-region**, không thể suy từ việc mất một AZ trong cùng region.

## 5. Định nghĩa “tiếp tục phục vụ” trước khi thử

Nếu hỏi “cụm còn sống không?”, câu trả lời có thể là “có” vì một node vẫn ping được. Nhưng business cần những luồng:

| Hành vi | Thành công nghĩa là gì? | Có được giảm chất lượng không? |
|---|---|---|
| Đọc thông tin sản phẩm | Trả danh sách hợp lệ trong deadline | Có thể chấp nhận cache stale ngắn theo SLO |
| Xem đơn của mình | Không nhầm tenant, dữ liệu đủ mới | Không nên trả trạng thái đã bị hủy như mới |
| Tạo đơn | Đảm bảo không tạo trùng với cùng idempotency key | Không được mất xác nhận commit đã xảy ra |
| Thanh toán | Một hiệu ứng tiền logic cho mỗi request | Có thể chuyển sang pending/reconciliation, không double charge |
| Trừ tồn kho | Không bán vượt invariant được định nghĩa | Có thể tạm chặn giao dịch thay vì ghi mù |
| Admin update | Chỉ principal hợp lệ, không bypass authz | Có thể tạm read-only khi mất quorum |
| Search sản phẩm | Trả kết quả có freshness bound | Có thể search stale nếu biểu thị rõ |
| CDC indexer | Bắt kịp backlog sau recovery | Có thể tạm lag theo recovery budget |

### Degraded mode là một trạng thái được thiết kế

Một hệ có thể **còn phục vụ đúng một phần**:

```text
Reads (stale permitted):     AVAILABLE
Strong writes:              TEMPORARILY UNAVAILABLE
Payment capture:            PAUSED / UNKNOWN-OUTCOME RECONCILIATION
Product search:             AVAILABLE WITH FRESHNESS WARNING
CDC pipeline:               BACKLOGGING
```

Không gọi toàn bộ hệ “healthy” chỉ vì read endpoint trả 200. Cũng không coi tạm từ chối write để bảo toàn invariant là hành vi sai nếu business contract đã ưu tiên consistency.

## 6. Bốn thời điểm bắt buộc ghi vào diễn tập

| Mốc | Ý nghĩa |
|---|---|
| \(t_{\text{fault}}\) | Bắt đầu thực thi fault đã phê duyệt |
| \(t_{\text{detect}}\) | Monitoring/on-call phát hiện user impact |
| \(t_{\text{mitigate}}\) | Service đạt degraded/normal threshold được chấp nhận |
| \(t_{\text{recover}}\) | Phục hồi toàn bộ invariant/backlog/replica state theo acceptance criteria |

Các phép đo tham khảo:

\[
MTTD = t_{\text{detect}}-t_{\text{fault}}
\]

\[
RTO_{\text{observed}}=t_{\text{recover}}-t_{\text{fault}}
\]

Không phải tổ chức nào cũng định nghĩa RTO từ đúng mốc fault hoặc đến full recovery; phải ghi **điểm bắt đầu/kết thúc đã cam kết**. Một số sẽ tách:

- **Time to degraded service**: khi các tính năng quan trọng còn phục vụ được với mức chất lượng chấp nhận.
- **Time to full recovery**: khi replica/CDC/cache capacity và mọi dữ liệu liên quan đã bắt kịp.

### RPO là điều gì?

**Recovery Point Objective** là mức mất dữ liệu chấp nhận được khi phục hồi sau sự cố theo định nghĩa business. Không suy RPO = 0 chỉ từ:

- Có ba bản sao.
- Write trả 200.
- Replication đang bật.
- Backup mỗi đêm.

Cần biết write ACK, consistency mode, cross-region replication, log durability, backup/replay, failover và unknown outcomes.

## 7. Availability SLI theo business operation

Một SLI minh họa:

\[
\text{SuccessRate}=
\frac{\text{logical requests hoàn tất đúng trong deadline}}
{\text{logical requests hợp lệ}}
\]

### Điều gì không nên tính là success?

- HTTP 200 nhưng dữ liệu thuộc tenant khác.
- HTTP 200 cho yêu cầu tạo đơn nhưng đơn bị tạo hai lần.
- Read trả state stale vượt freshness contract.
- Write được ACK nhưng mất sau failover trái RPO đã cam kết.
- Timeout có kết quả chưa rõ nhưng ứng dụng tuyên bố thất bại chắc chắn rồi retry tạo effect trùng.

### Điều gì có thể tính là success?

- Request read-only được phục vụ từ cache trong freshness allowance.
- Write tạm được xếp vào **durable intent queue** và API trả đúng semantics `202 Accepted` nếu contract cho phép.
- Một API trả trạng thái `PENDING` hợp lệ theo workflow thay vì đoán kết quả payment.

### Availability của driver không phải availability của ứng dụng

Driver báo cluster connected không đảm bảo business write thành công. Health endpoint chỉ kiểm tra TCP có thể xanh trong khi quorum lost hoặc application không route tới primary được.

## 8. RTO, RPO, freshness và consistency là bốn cam kết khác nhau

Một ví dụ:

```text
RTO: service can accept new orders within 5 minutes
RPO: no acknowledged order writes lost
Search freshness: order changes visible within 60 seconds
Consistency: cannot confirm two reservations for one seat
```

Một thiết kế khôi phục writes sau 3 phút có thể đạt RTO nhưng mất các writes đã ACK do async cross-region replication; **RPO không đạt**. Một thiết kế mất 0 confirmed writes nhưng search lag 20 phút cũng không đạt freshness SLO.

### Cần đo rõ

- Số acknowledged writes **thực sự tồn tại** sau failover.
- Số requests có outcome unknown cần reconciliation.
- Số duplicate business effects.
- Staleness theo source revision/time.
- Thời gian để API phục vụ lại.
- Thời gian để các replicas, caches và downstream projections bắt kịp.

**Không gộp tất cả thành một con số uptime**.

## 9. Quorum: với ba voter đặt ba zone

Một mô hình replicated consensus có ba voting members:

```text
A: voter n1
B: voter n2
C: voter n3

Quorum = floor(3/2)+1 = 2
```

Khi mất Zone A:

```text
Available voters: n2,n3 = 2
Majority still possible
```

Khi mất Zone A và Zone B:

```text
Available voters: n3 = 1
Majority unavailable
```

### Công thức tổng quát

Với \(V\) voters và majority quorum:

\[
Q=\left\lfloor\frac{V}{2}\right\rfloor+1
\]

Mất một fault domain vẫn còn majority nếu:

\[
V-\text{votersInLostDomain}\ge Q
\]

Đây là tính toán **mô hình quorum**, chưa chứng minh app thực tế phục vụ. Phải xét voting rules, leader election, networking, failover time, client configuration, cluster metadata, disk availability và consistency levels.

### Điểm dễ sai

Ba nodes không tự bảo đảm ba **voters độc lập**. Nếu:

```text
Zone A: n1,n2
Zone B: n3
Zone C: no voter
```

mất Zone A khiến chỉ còn một voter — dù bảng topology có ba nodes.

## 10. Quorum có ý nghĩa khác nhau giữa các NoSQL

| Kiểu hệ | Cơ chế liên quan | Điều không được suy |
|---|---|---|
| Leader-based consensus | Majority election/commit theo cluster policy | Mất node mà majority còn thì latency = 0 |
| Leaderless/dynamo-style replication | Read/write consistency và replica placement | Đọc `ONE` luôn mạnh như `QUORUM` |
| Async primary-replica | Primary ACK và replication lag | Replica có thể takeover mà không mất ACKed writes |
| Multi-region active-active | Replication/conflict resolution | Viết hai phía partition không có conflicts |
| Managed service | Provider durability/availability contract | Hình dung vật lý từ số nodes tự quản |

### \(R+W>N\) không đủ chứng minh global linearizability

Trong một hệ đọc/ghi quorum, điều kiện read quorum và write quorum giao nhau là một phần lập luận, nhưng **không đủ cho mọi bảo đảm consistency** nếu có hinted handoff, sloppy quorum, versioning, concurrent writes, clock behavior hoặc topology changes. Đọc đúng API/consistency guarantee của engine.

### Availability theo operation

Cụm có thể:

- Cho phép stale read ở minority partition.
- Từ chối strong write ở minority partition.
- Cho phép write tạm vào một queue hoặc conflict-bearing state.

Không gắn nhãn “cụm vẫn available” mà không nói **API nào, consistency mode nào và phía partition nào**.

## 11. Fault-domain placement và dữ liệu không đồng đều

Không chỉ phân bố số node; phải phân bố:

- Replicas/voters.
- Shards/partitions và những leader/primary của chúng.
- App instances/ingress targets.
- Coordinator nodes và seed/discovery endpoints.
- Broker topics/partition leaders.
- Backup/snapshot jobs.
- DNS, KMS, metrics và alerting access.

Một layout có ba nodes mỗi zone nhưng 90% **hot partition leaders** nằm ở Zone A có thể bị giảm throughput lớn khi mất A dù data vẫn replicated. Ngay cả lúc failover thành công, Zone B/C có thể phải chịu 150% tải và tăng p99.

### Capacity khi mất một zone

Giả sử bình thường 3 zones chia đều tải 900 requests/s:

```text
Normal:       A=300, B=300, C=300
After A lost: A=0,   B=450, C=450
```

Nếu mỗi zone chỉ chịu tốt 350 requests/s, database vẫn có majority nhưng **không đủ capacity**. Fault tolerance về quorum và khả năng tiếp tục đáp ứng **SLO throughput/latency** là hai bài toán riêng.

## 12. Rủi ro chung: service ở ba AZ nhưng dependency chỉ ở một AZ

Sơ đồ:

```text
App A ----\
App B -----+---> Shared Redis primary in Zone A
App C ----/
             \
              +---> Shared Kafka connector in Zone A
```

Ứng dụng đã deploy ở A/B/C nhưng Redis, connector, reverse proxy, secret injection hoặc DNS forwarder có thể nằm ở A. Khi Zone A mất, cả ứng dụng B/C cũng chịu tác động.

### Danh mục phụ thuộc cần rà soát

1. Client-facing DNS/ingress/load balancer.
2. Authentication/authorization, identity provider, session store.
3. Database discovery/configuration/quorum.
4. Cache (và có fallback an toàn không).
5. Stream broker/CDC/outbox relay.
6. KMS/secret manager/certificate trust.
7. Control plane và autoscaler.
8. Network routes/NAT/egress proxies.
9. Object storage, snapshots và backup repository.
10. Observability/alert notification/incident communication.

### Phân biệt data plane và control plane

**Data plane** có thể tiếp tục phục vụ các queries sẵn có dù API để tạo node/đổi cấu hình bị lỗi. Ngược lại, khi AZ mất và cần tự mở thêm nodes, một **control plane outage** có thể cản trở phục hồi capacity.

Diễn tập nên đo:

- Các nodes/clients hiện có tiếp tục hoạt động bao lâu?
- Khi cần rotate secret hoặc discover leader mới, dependency hoạt động không?
- Autoscaler có tạo replacement ở vùng còn sống không?
- Nếu control plane tạm mất, có thể vận hành qua đường break-glass được duyệt không?

## 13. Network partition: an toàn dữ liệu không giống availability mọi phía

Giả sử n1 ở Zone A và n2/n3 ở Zone B/C:

```text
               Partition

   A (n1)      X       B,C (n2,n3)
     |         X          |
  app A        X        app B/C
```

Để bảo vệ strong consistency với quorum majority, n1 ở minority **không thể tự tuyên bố hoàn tất new majority writes**. N2/n3 có thể chọn primary hợp lệ sau khi đáp ứng các điều kiện election.

### Ba kiểu phản ứng có thể

| Kiểu phản ứng | Điều xảy ra | Đánh đổi |
|---|---|---|
| Từ chối writes ở phía minority | Bảo vệ invariant/consensus | Một số clients không thể ghi |
| Cho phép local writes ở cả hai phía | Người dùng ở mỗi phía có thể tiếp tục | Có thể có xung đột/đòi CRDT, reconciliation, compensation |
| Queue commands/intents bền | API nhận yêu cầu để xử lý sau | Trả `accepted`, chưa được nói `committed` |

Không thể vừa cho cả hai partition độc lập commit một write có ảnh hưởng invariant toàn cục, vừa đảm bảo một thứ tự strong duy nhất, nếu không có giao tiếp/giao thức đủ mạnh theo yêu cầu hệ.

### Chọn theo nghiệp vụ

- Like count/social feeds có thể chấp nhận eventual state/merge.
- Đặt một ghế duy nhất hoặc trừ số dư không âm đòi cơ chế kiểm soát chặt.
- Catalog browsing có thể chấp nhận read-only hoặc stale mode.
- Payment không được tự tạo duplicate charges khi retry sau partition.

### Diễn tập đánh giá hành vi thực

Thay vì đo “query có HTTP response không”, xác nhận **mỗi loại response có đúng semantics**: thành công, tạm không khả dụng, pending hay retryable. Một lỗi bị âm thầm che bằng stale cache cũng là kết quả phải đánh giá.

## 14. Client routing sau failover: database khỏe chưa chắc ứng dụng khỏe

Sau khi cluster chọn leader mới:

```text
DB leader elected in Zone B
         |
         v
App B successfully reconnects
         |
         +-- App C still uses stale topology?
         +-- App A still accepts external traffic?
         +-- Load balancer considers app A healthy?
         +-- DNS cache retains old targets?
```

### Những thứ cần đo

- Thời gian driver phát hiện topology change.
- Thời gian pool loại connection cũ và dựng connection mới.
- Server selection timeouts và retry storms.
- DNS TTL và caching thật của runtime/resolver.
- Ingress health checks có phân biệt service **ready** với process **alive** không.
- Client requests có bị route đến AZ không thể phục vụ không.
- Các client SDK versions có cùng behavior không.

### Readiness khác liveness

`Liveness` trả lời “process còn có thể tiếp tục chạy?”; `readiness` trả lời “instance nên nhận requests mới trong mode hiện tại không?”. Với microservice:

- Liveness không nên tùy tiện kill toàn bộ pods vì DB tạm unreachable, gây restart storm.
- Readiness cần phản ánh khả năng phục vụ endpoint hoặc mode phù hợp, tránh gửi traffic vào instance không thể làm việc.
- Nếu service có cả public catalog read và critical write path, một readiness bit chung có thể quá thô; cân nhắc route/mode theo use case.

### DNS failover không tức thời

Giảm TTL có thể giúp nhưng không bảo đảm mọi resolver/client refresh đúng thời điểm; connection pools, long-lived streams, TLS sessions và caches cũng ảnh hưởng. Không giả định thay DNS là hoàn tất failover.

## 15. Unknown write outcome: timeout không có nghĩa chưa commit

Lịch sử:

```text
Client                Primary
  |--- CreateOrder ID=O1 --->|
  |                          | write committed
  |          X lost response |
  |<------ timeout ---------X|
  |
  |--- retry create order --> ? 
```

Client thấy timeout nhưng không thể biết write đã:

1. Chưa tới server.
2. Tới server nhưng bị từ chối.
3. Được commit rồi response mất.
4. Đang ở trạng thái chưa thể xác định.

Nếu retry với order ID mới, có thể tạo **hai đơn**. Nếu API trả “failed, chắc chắn không có đơn” là một phát biểu không có căn cứ.

### Hợp đồng idempotency

```text
POST /orders
Idempotency-Key: request-xyz

Create order using request-xyz as unique claim.
If retry with same key:
  return previous committed outcome (or PENDING/UNKNOWN per policy)
```

Để có tác dụng, server phải lưu request key/outcome **bền và atomic với business write** trong phạm vi authority phù hợp, hoặc có protocol reconciliation. Một cache in-memory của idempotency keys không đủ khi cả AZ bị mất.

### Kiểm tra trong diễn tập

Gây failure **sau server commit nhưng trước client nhận response**, rồi retry cùng request key. Đánh giá:

- Có đúng một logical order không?
- Có đúng một payment intent không?
- Client có nhận được state rõ hay rơi vào UNKNOWN cần tra cứu?
- Event/outbox có bị publish trùng không?

Đối với thanh toán, ngoài application idempotency còn phải tuân idempotency contract của payment provider và reconciliation.

## 16. Retry: cứu availability hoặc gây outage dây chuyền

Khi mất một AZ, clients có thể đồng loạt retry:

```text
1000 logical requests
    |
    +-- original attempts: 1000
    +-- retries x3:       3000
    +-- background retry: 2000
    |
    v
Surviving database nodes already overloaded
```

### Giới hạn cần có

- Retry **chỉ khi operation có thể retry an toàn** và kết quả chưa terminal.
- Total deadline/retry budget theo logical request.
- Exponential backoff với jitter.
- Circuit breaker/rate limit khi downstream suy giảm.
- Max in-flight requests và bounded queues.
- Không tất cả client cùng retry đúng một nhịp.
- Phân biệt error classes (timeout, authz, validation, insufficient quorum, throttling).
- Giám sát attempts/logical request và retry amplification.

### Đừng retry vô hạn write không idempotent

`INCR`, `$inc`, payment capture hoặc append event có thể gây duplicate effect nếu kết quả trước unknown. Cần conditional mutation/request ledger/provider idempotency hoặc chuyển sang trạng thái cần reconciliation.

### Fail-fast và admission control

Nếu surviving zone không đủ capacity, tạm từ chối một số requests theo priority có thể bảo vệ critical flows. API phải trả status phù hợp và Retry-After/rate-limit theo hợp đồng, không che lỗi bằng kết quả thành công giả.

## 17. Fencing: leader cũ không được quay về và ghi đè

Một kịch bản:

```text
T0 Worker A/leader n1 owns lease epoch=7.
T1 Zone A partitioned; lease expires.
T2 Worker B gets lease epoch=8.
T3 Worker A wakes and writes stale update.
```

Một distributed lock lease **không tự ngăn worker cũ đang chạy**, vì nó có thể tiếp tục sau timeout hoặc GC pause. Nếu authoritative sink hỗ trợ, dùng fencing token/epoch monotonic:

```text
write(data, epoch=7) -> REJECT (current epoch=8)
write(data, epoch=8) -> ACCEPT (authorized owner)
```

### Điều kiện thiết kế

Epoch phải được phát bởi authority bảo đảm đơn điệu/phân quyền phù hợp, và **sink phải thực thi check**. Một token ghi trong log nhưng sink không kiểm tra sẽ không có tác dụng.

### Ở NoSQL replicated system

Cluster leader election/term có thể có fencing nội tại trong protocol. Nhưng các **external side effects** như search index updates, backup jobs, CDC workers, Redis locks hoặc payment orchestration vẫn cần hiểu ownership/replay semantics riêng.

### Diễn tập

Giữ một worker cũ bằng pause hoặc network delay trong lab, chuyển ownership sang worker khác, sau đó cho worker cũ tiếp tục. Kiểm tra không có stale writes/duplicate effects.

## 18. Phân biệt “mất zone” và “không thể truy cập từ một phía”

Một AZ bị tắt hẳn:

```text
Power/VM unavailable
No application or database processes running
```

Một AZ bị cô lập mạng:

```text
Processes running
Some local traffic works
Cross-zone links broken or asymmetric
```

Đây là hai fault classes khác nhau. Trong partition:

- Nodes có thể tiếp tục nhận writes từ clients cục bộ theo API.
- Health probes cục bộ có thể xanh.
- DNS/ingress từ vùng ngoài có thể còn route tới minority.
- Connection timeouts có thể dài và không đối xứng.
- Recovery/rejoin có thể gây conflict resolution hoặc rollback theo engine.

### Asymmetric faults

```text
A -> B requests succeed
B -> A responses dropped
A <-> C partially works
```

Kịch bản này có thể khó phát hiện hơn đứt mạng hoàn toàn. Nếu bài diễn tập chỉ “disable NIC” sẽ không đại diện cho tất cả network partitions; cần chọn lớp fault theo hypothesis.

## 19. Failure matrix theo diện mất và chế độ consistency

Một bảng thiết kế kiểm thử:

| Sự cố | Read `ONE`/eventual | Strong/quorum read | Strong/quorum write | Nguồn rủi ro |
|---|---|---|---|---|
| Một replica mất, majority còn | Có thể phục vụ | Có thể phục vụ tùy routing/quorum | Có thể phục vụ | Latency, capacity, node discovery |
| Một AZ mất, majority còn | Có thể phục vụ từ zones còn | Có thể phục vụ theo source contract | Có thể phục vụ sau election/re-routing | Load spikes, old leader connections |
| Majority mất | Có thể có stale read nếu API cho phép | Thường không thể đáp ứng quorum | Thường bị từ chối | Availability giảm để bảo vệ consistency |
| Hai phía partition ghi local | Có thể đọc các bản khác nhau | Cần protocol thống nhất | Chỉ một phía hoặc conflict-bearing writes | Split-brain/merge/conflict |
| Region chính mất, async standby | Standby có thể đọc data cũ | Phụ thuộc standby protocol | Có thể fail over | RPO > 0, DNS/KMS changes |
| Cache AZ mất, DB vẫn khỏe | Cache miss/fallback | DB có thể strong | Không đổi semantics nếu DB authority | Stampede và saturation |

Đây là **ma trận khái niệm**, không phải lời cam kết về một sản phẩm hoặc consistency setting. Khi lập test thực tế, ghi rõ engine/version/topology/read-write concerns, cơ chế replication, và các thao tác thật của client.

## 20. Health checks cần thực hiện đúng loại thao tác

Các cấp:

```text
TCP reachable?                 -> weak signal
Driver topology known?         -> operational hint
DB command read succeeds?      -> read path hint
Quorum write succeeds?         -> write path hint
End-to-end business canary?    -> business SLI evidence
```

### Synthetic canary

Một record giả trong namespace test với permission riêng có thể được ghi, đọc và kiểm tra revision:

```text
create/update canary revision N
read with required concern
assert revision >= N
validate response time
```

Không để canary:

- Tạo payment/notification thật.
- Chiếm cùng hot key với tenant lớn.
- Gây mutation xung đột với production data.
- Tạo unbounded documents/TTL leakage.
- Làm tất cả live pods bị restart nếu một probe tạm thất bại.

### Blackbox và whitebox

Blackbox probe từ ngoài đường client thấy được availability end-to-end; whitebox metrics từ DB cho biết election, quorum, locks, replication, capacity. **Cần cả hai** để phát hiện đúng và chẩn đoán.

## 21. Diễn tập có trách nhiệm: hypothesis trước, fault sau

Một bài **game day** tốt bắt đầu từ giả thuyết đo được:

> “Khi Zone A mất kết nối với B/C trong 10 phút, ứng dụng Orders vẫn phục vụ ít nhất 99% truy vấn đọc được phép stale trong 2 giây, không tạo duplicate orders, các writes cần majority hoặc hoàn tất trong 5 giây hoặc trả lỗi/pending đúng hợp đồng; sau hồi phục, CDC bắt kịp trong 15 phút.”

Giả thuyết nêu:

- Phạm vi lỗi.
- Thời lượng.
- Các operation được phép/không được phép.
- Chỉ tiêu latency, correctness, freshness và recovery.
- Evidence để pass/fail.

Một bài “tắt AZ thử xem có lỗi gì” chưa có hypothesis, blast radius và điều kiện dừng là **hành động rủi ro**, không phải thí nghiệm có kiểm soát.

### Bốn nhóm mục tiêu

| Mục tiêu | Câu hỏi |
|---|---|
| **Safety** | Có mất/nhân đôi acknowledged data không? Invariant có giữ không? |
| **Liveness** | Sau lỗi, yêu cầu nào vẫn hoàn tất trong deadline? |
| **Performance** | p95/p99, throughput, queue và retry amplification có đạt SLO? |
| **Recoverability** | Khi fault kết thúc, cluster/CDC/cache phục hồi thế nào, trong bao lâu? |

Không dùng latency tốt để kết luận safety tốt; cũng không coi zero data loss là thành công nếu mọi API đều ngừng phục vụ vượt RTO mà business yêu cầu.

## 22. Steady state: phải định nghĩa trước khi gây lỗi

Trước mỗi kịch bản, ghi baseline:

```text
Traffic:
  read logical requests/s
  write logical requests/s
  request size / document size distribution
  per-tenant / per-region distribution

Client:
  p50 / p95 / p99 latency
  error / timeout / retry rates
  connection pool waits

Data:
  acknowledged writes
  revisions / checksums / invariant results
  replication freshness
  CDC source-to-sink lag

Cluster:
  primary/voters/replicas/shards
  CPU/disk/network
  queue/compaction/broker lag
```

### Vì sao baseline quan trọng?

Nếu p99 bình thường đã 900 ms, diễn tập đặt điều kiện “p99 dưới 100 ms” vô nghĩa. Nếu một replica đã lag 20 phút **trước khi** gây lỗi, không được quy toàn bộ lag sau thử cho fault mới.

### Traffic cần đại diện

- Peak và off-peak.
- Read-heavy và write-heavy.
- Small và large documents.
- Hot tenants/hot keys.
- Interactive và background workloads.
- Cross-region và same-region clients.

Một lab có traffic 1 request/s không thể chứng minh surviving zones chịu tải 10.000 requests/s.

## 23. Phạm vi blast radius và thứ tự nâng mức khó

Không bắt đầu bằng cách ngắt kết nối cả một AZ production khi chưa biết tính đúng của ứng dụng.

Một lộ trình an toàn hơn:

```text
Level 0: Model/tabletop, no mutation
   |
   v
Level 1: Isolated test cluster with synthetic data
   |
   v
Level 2: Staging/representative preproduction load
   |
   v
Level 3: Controlled narrow production fault (if approved)
   |
   v
Level 4: Full-fault-domain simulation under explicit policy
```

### Thu hẹp blast radius

Trong các môi trường có cơ chế cô lập:

- Test một namespace hoặc service class.
- Chỉ dùng synthetic canary tenants.
- Giới hạn zone/replica/traffic segment trong bài thí nghiệm.
- Dùng traffic shaping/routing controlled thay vì phá hủy hạ tầng.
- Gắn thời gian hết hạn bắt buộc cho fault injection.
- Tránh thử trên resources đang chứa dữ liệu thật nếu chưa có sự chấp thuận và bảo vệ tương đương.

### Không ngầm hiểu được phép inject ở production

Sự chấp thuận chạy một bài test **không tự cho phép** gián đoạn toàn bộ khu vực hoặc xóa dữ liệu. Cần policy, maintenance/communication và người chịu trách nhiệm cho phạm vi cụ thể.

## 24. Preflight checklist trước khi game day

| Điều kiện | Cần xác nhận |
|---|---|
| Mục tiêu | Hypothesis, success/failure criteria được viết |
| Phạm vi | Cluster, vùng, services, tenants và thời lượng |
| Quyền | Approval/chế độ thực thi theo production policy |
| Dữ liệu | Synthetic/canary hoặc data-protection plan |
| Backup | Recovery point, integrity và khả năng restore đã xác minh |
| Fault mechanism | Có rollback/automatic expiry |
| Safety | Abort criteria, error budget và blast-radius guardrails |
| Owners | Incident commander, DB, app, networking, security liên quan |
| Observability | Dashboards/probes/logging/alerting hoạt động độc lập |
| Controls | Quyền dừng fault và đường liên lạc ngoài vùng lỗi |
| Capacity | Surviving zones/headroom có được tính |
| Time | Cửa sổ thử, các thay đổi khác đang diễn ra |
| Recovery | Runbook rejoin/rebalance/reconcile, data validation |

### Hủy/hoãn bài diễn tập nếu

- Production đang có incident chưa xử lý.
- Backup hoặc recovery path không được kiểm chứng.
- Monitoring chính đang mất hoặc notifications không hoạt động.
- Không có người đủ quyền rollback.
- Không thể giới hạn blast radius theo phê duyệt.
- Source đang gần hết dung lượng/durability headroom.
- Change/deployment đồng thời khiến kết quả không thể quy trách nhiệm.

## 25. Abort criteria phải rõ và được kích hoạt tự động khi phù hợp

Một thí nghiệm có thể đặt:

```text
ABORT if:
  - verified risk of data loss or cross-tenant exposure
  - critical write error rate above allowed threshold for X minutes
  - surviving DB nodes above safe CPU/disk/network utilization limit
  - backup/restore safety or quorum protection lost unexpectedly
  - fault scope extends beyond approved zone/service
  - monitoring/control channel unavailable
  - incident commander orders stop
```

Các thresholds phải cụ thể hóa theo cluster/SLO thật, không sao chép nguyên `X phút`.

### Không coi undo fault là hoàn thành rollback

Khi link A–B được nối lại, các nodes có thể đang:

- Bầu lại leader hoặc hồi nhập cluster.
- Replay WAL/oplog/change logs.
- Repair/anti-entropy.
- Rebuild indexes.
- Rewarm caches.
- Catch up CDC.
- Reconcile conflicting writes hoặc unknown outcomes.

Vì thế quy trình rollback gồm **tắt fault, xác minh cluster health và chứng minh dữ liệu phục hồi**, không chỉ nhấn “Stop experiment”.

### Kill switch riêng cho fault injector

Fault injector phải có owner, TTL và cách vô hiệu **ngoài fault domain đang thử**. Nếu cơ chế dừng cũng phụ thuộc Zone A bị cô lập, bạn có thể không thể kết thúc test đúng hạn.

## 26. Bảo vệ production bằng dry run và simulation

Trước khi tác động hạ tầng:

1. Vẽ quorum/voter map và dự đoán replica còn lại.
2. Tính surviving capacity với N−1 zone.
3. Phân tích dependency graph, DNS/KMS/identity route.
4. Chạy tabletop với timeline giả.
5. Test client retries/unknown commit trên môi trường cô lập.
6. Test restore access và alert delivery qua đường độc lập.
7. Đối chiếu phương án rollback từng bước.

### Fault models thường dùng

| Kiểu | Thứ cần mô phỏng | Ví dụ trong lab |
|---|---|---|
| Process crash | Một DB/worker process chết | Dừng container/process trong test namespace |
| Node unavailable | Mất một host | Cô lập test node khỏi client cluster |
| Zone isolation | Mất mạng tới toàn bộ members trong zone | Fault injection có scope network và TTL |
| Latency | Inter-zone RTT tăng | Network delay emulation ở test network |
| Packet loss | TCP requests/responses bị mất | Loss rules có giới hạn |
| Asymmetric partition | Một chiều không trả lời | Route/filter với direction cụ thể |
| Disk exhaustion | Writes/compaction bị từ chối | Fake/quota-limited volume trong lab |
| Control-plane outage | Không auto-scale/reconfigure được | Tắt API giả hoặc deny temporary test role |
| Slow dependency | KMS/DNS/secret source chậm | Dependency simulator |
| Clock skew | Timestamp-based assumptions bị phá | Controlled clock test ở isolated environment |

Không đưa lệnh hệ thống ngắt mạng/xóa disk không có scope vào runbook chung để nhân viên copy trong production. Khai báo kịch bản qua **approved fault injection service**, tài nguyên test và hạn sử dụng.

## 27. Tabletop: bài diễn tập không cần phá bất cứ thứ gì

Mỗi người nhận một role:

```text
Incident commander: decision/communication
SRE: ingress, metrics, retries, capacity
DBA: quorum, replicas, failover, consistency
App owner: business SLO, idempotency, degraded mode
Data pipeline owner: CDC, read models
Security: data exposure, access/restore controls
```

Một moderator đưa tình huống theo thời gian:

```text
09:00 Zone A network partially fails.
09:02 App A health remains green, DB majority in B+C.
09:04 Checkout retries amplify 4x.
09:06 New primary elected, writes still timeout from some clients.
09:09 CDC lag grows; Redis cache misses rise.
09:15 Network restored; old worker writes stale projection.
```

Nhóm cần trả lời:

- Ai phát hiện sự cố đầu tiên?
- Có đủ evidence để biết fault domain?
- Khi nào tắt route vào app A?
- Có nên bật read-only/degraded mode?
- Có thể retry payment/order an toàn không?
- Ai xác minh data correctness sau recovery?

**Tabletop hữu ích để tìm khoảng trống quy trình** trước khi thử fault có tác động thật.

## 28. Diễn tập một zone mất hoàn toàn: timeline có kiểm soát

Một ví dụ kịch bản **trong lab/staging**:

```text
T-30m  Verify backups, quorum, load, dashboards, approvals.
T-10m  Start synthetic business probes and event recorder.
T-05m  Snapshot baseline; note current primary/shard leaders.
T0     Fault injector isolates Zone A (approved scope).
T+01m  Observe client latency, retries, errors, leader elections.
T+03m  Validate allowed reads and strong writes from Zones B/C.
T+05m  Check idempotent retries and unknown outcomes.
T+07m  Check CDC freshness and cache fallback load.
T+10m  Remove fault according to abort/experiment policy.
T+12m  Observe node rejoin, repair, rebalance, backlog drain.
T+20m  Reconcile all synthetic requests/records and projections.
T+30m  Collect incident evidence and pass/fail report.
```

Thời gian là minh họa cho test đã được duyệt, không phải khuyến nghị tự ý kéo dài lỗi khi SLO bị ảnh hưởng.

### Evidence tối thiểu mỗi giai đoạn

- Fault injector audit: start/stop/actual affected resources.
- Client request history và idempotency keys.
- Cluster election/topology/reachability.
- Time-series latency/errors/retries.
- Data source revisions/quorum ACK.
- Downstream source-to-visible lag.
- Capacity và resource pressure.

Nếu không biết fault đã thực sự cô lập những tài nguyên nào, một kết quả “pass” thiếu giá trị.

## 29. Diễn tập network partition: hai bên cùng sống

Trong môi trường cô lập, tạo partition:

```text
{Zone A}  X  {Zone B, Zone C}
```

Gửi requests từ cả hai phía bằng các synthetic clients:

| Client | Read stale hợp lệ | Majority write | Expected |
|---|---|---|---|
| A, minority | Có thể success nếu API cho phép và data local | Không được commit trái majority contract | Fail/pending hợp lệ |
| B, majority | Theo source read concern | Có thể success sau election | One committed outcome |
| C, majority | Theo source read concern | Có thể success sau election | One committed outcome |

### Khi test

- Có test cùng entity ID từ hai phía.
- Có test concurrent update có điều kiện.
- Có test read-after-write từ cùng client/session.
- Có test retry khi ACK bị mất.
- Có test rejoin và rollback/merge tùy engine.
- Ghi history với request invocation/completion timestamps, source revisions và response classifications.

### Không suy một phản hồi “OK” là đúng nếu không kiểm tra nguồn

Một minority client có thể trả 200 từ local cache. Điều đó chấp nhận cho catalog trong stale budget, nhưng không đúng nếu endpoint hứa strong read về inventory đã bán hết.

## 30. Ma trận kết quả pass/fail theo business workflow

| Workflow | Pass khi | Fail khi |
|---|---|---|
| Public catalog read | Trả đúng scope, độ trễ và freshness trong policy | Cache stale vượt bound, sai tenant |
| Create order | At-most-one logical order cho mỗi idempotency key; ACKed result durable | Duplicate orders, ACKed write lost |
| Reserve unique seat | Không xác nhận hai người cùng một ghế | Hai phía partition đều commit seat |
| Payment orchestration | Một external effect logic hoặc outcome NEEDS_RECONCILIATION | Retry tạo double charge |
| Account permission revoke | Không trả access cũ vượt revocation contract | Stale allowed access |
| Search projection | Có thể lag trong thời gian đã công bố, rồi catch up | Mất events, không recover, silent gap |
| Export job | Có durable checkpoint và resume không trùng output | Partial output bị báo complete |
| Audit trail | Ghi nhận thay đổi theo durability contract | Audit mất không có cảnh báo |

Mỗi dòng nên có **measurement method và ngưỡng cụ thể** trong kế hoạch thật. Nếu không có yêu cầu rõ, dễ kết luận tùy ý sau khi đã nhìn kết quả.

## 31. MongoDB: replica set, voting members và election

Một MongoDB replica set có primary/secondaries và voting configuration. Sự cố toàn AZ cần xem:

```text
Zone A: member A, voting, initially primary
Zone B: member B, voting, secondary
Zone C: member C, voting, secondary
```

Khi Zone A mất:

1. Clients có thể tạm gặp server-selection errors khi primary cũ biến mất.
2. Members B/C đủ majority votes trong ví dụ và có thể bầu primary mới khi đáp ứng điều kiện.
3. Clients cần khám phá topology mới.
4. Writes mới cần đúng write concern (ví dụ majority khi contract yêu cầu).
5. Replication lag/oplog/rejoin của A cần được giám sát sau khi phục hồi.

### Election success không tự bằng business recovery

DB có primary mới nhưng:

- App vẫn kết nối tới host cũ.
- Pool/driver DNS discovery chậm.
- Application retries tạo duplicate orders.
- CDC stream bị invalidate/resume gap.
- Surviving nodes bị quá tải vì mất một AZ.

Do đó cần đo **time-to-first-successful-write** từ client và **last-failed-request time**, không chỉ timestamp election complete trong DB log.

### Write concern và RPO

Một write với acknowledgment yếu có thể không có cùng durability guarantee với majority-acknowledged write khi primary bị mất. Không tự suy mọi acknowledged write đều còn sau failover. Diễn tập dùng **synthetic write ledger** và đối soát theo write concern/read concern thực tế.

### Arbiter không chứa data

Một replica set có arbiter có thể giúp voting nhưng không là bản sao dữ liệu. Nếu:

```text
Zone A: primary data member
Zone B: secondary data member
Zone C: arbiter
```

mất Zone B làm giảm redundancy của data members dù majority votes có thể vẫn còn nếu các member còn kết nối. Bố trí voter/arbiter không thay nhu cầu durability/replica placement.

### Test đặc thù

- Primary stepdown hợp lệ.
- Mất AZ chứa primary và mất AZ không chứa primary.
- Cô lập primary cũ thay vì kill process.
- Replica secondary lagging trước failover.
- Test writes với configured concern và ambiguous outcomes.
- Verify critical change streams resume đúng và không mất event.

## 32. Cassandra: replica placement và consistency level

Cassandra thường sử dụng mô hình dữ liệu phân tán theo partition key, replication strategy và read/write consistency levels. Không có một leader toàn cluster cho mọi mutation như replica set single-primary.

### Ví dụ replication factor 3 trong một datacenter

```text
RF=3
Zone A: replica 1
Zone B: replica 2
Zone C: replica 3
```

Nếu mỗi partition thật sự có một replica ở mỗi zone (cần kiểm chứng placement/snitch/cluster configuration), mất một zone có thể để lại hai replicas.

- Requests với consistency level phù hợp có thể còn phục vụ.
- Một số operations đòi mức mạnh hơn có thể bị timeout/unavailable.
- Coordinator, token ownership và routing có thể thay đổi.
- Trường hợp một **partition rất lớn/hot** có throughput khác hẳn số liệu trung bình.

### Đừng đồng nhất RF=3 với ba fault domains

Replication factor 3 không đảm bảo ba replicas của mọi partition nằm ở ba AZ **nếu cấu hình placement không làm vậy**. Đánh giá replica distribution thực tế.

### Test cần đo

1. Read/write availability theo `ONE`, `LOCAL_QUORUM` hoặc consistency mode đang dùng.
2. Latency ở coordinator khi một AZ mất.
3. Hinted handoff/anti-entropy/repair backlog sau recovery, theo engine/version.
4. Compaction, tombstones và disk headroom khi nodes còn lại chịu tải.
5. Data reconciliation, conflict resolution, không để stale overwrites.
6. LWT/conditional operations riêng: không suy semantics từ normal writes.

### Lưu ý repair

Không chạy full repair/major compaction không có kế hoạch ngay trong diễn tập chỉ để “cụm xanh”. Những thao tác này có thể tăng I/O và làm p99 xấu hơn. Runbook phải dựa vào version, topology và khuyến nghị vận hành đã được xác minh.

## 33. Redis: primary/replica, Sentinel và Cluster khác nhau

Redis có nhiều chế độ triển khai:

- Standalone hoặc primary với replicas.
- Redis Sentinel để phát hiện/failover trong cấu hình phù hợp.
- Redis Cluster với shards/hash slots, primaries và replicas.
- Managed Redis có failover/placement policy do provider cung cấp.

### Diễn tập cache outage

Nếu Redis là **cache có thể tái tạo**, mục tiêu không chỉ Redis reconnect nhanh:

```text
Redis Zone A fails
   |
   v
Cache hit ratio drops
   |
   v
MongoDB fallback QPS doubles
   |
   v
DB pool wait / p99 increases
```

Ứng dụng có fallback đúng nhưng **không đủ capacity** vẫn có outage.

### Diễn tập Redis làm source trạng thái quan trọng

Nếu Redis giữ sessions, rate limits, locks hoặc stream events, các bảo đảm cần khác:

- Replication/persistence settings và durability thực tế.
- Async replication có thể gây data loss trong một số failover.
- Sentinel/quorum và Redis Cluster failover semantics.
- TTL/lease/fencing của distributed locks.
- PEL/consumer claims của Redis Streams, nếu dùng.

Không gọi Redis “chỉ là cache” để bỏ qua những dữ liệu nghiệp vụ đang thực sự lưu trong nó.

### Redis Cluster: hash slots và AZ mất

Một cluster trải các primaries/replicas giữa zones. Khi mất zone:

- Shard nào mất primary?
- Shard nào có replica thích hợp có thể tiếp quản?
- Slot coverage có còn không?
- Clients có xử lý MOVED/ASK/topology changes không?
- Có hotspot do hash tags gom cả tenant vào một slot không?
- Cụm có đủ memory/capacity sau failover không?

**Một shard không còn serving slot** có thể khiến một phần keys không thể truy cập dù các shards khác khỏe.

### Không chấp nhận split-brain ở lock service

Nếu dùng Redis lock cho một external effect quan trọng, kiểm tra lease expiry, stale worker và fencing. Không suy Redis Sentinel/Cluster failover tự bảo vệ mọi external write.

## 34. DynamoDB: fault-domain test với managed service

Với managed NoSQL như DynamoDB, người dùng thường **không được tùy ý tắt AZ hoặc điều khiển replicas vật lý** của dịch vụ. Cần phân biệt:

- **Provider-level resilience** theo hợp đồng được công bố.
- **Application-level resilience** khi client, network, IAM, route, region hoặc dependent services bị lỗi.
- **Experiment scope** mà người dùng được phép điều khiển.

### Diễn tập an toàn hơn

Trong môi trường test:

- Chặn kết nối từ một nhóm application clients tới DynamoDB endpoint bằng công cụ được phê duyệt.
- Tăng latency/timeout cho SDK calls.
- Mô phỏng throttling/provisioned capacity limits.
- Kiểm tra retry/backoff, conditional writes/idempotency.
- Cô lập một AZ của ứng dụng, đánh giá traffic của các AZ còn lại.
- Nếu có Global Tables/multi-region pattern, diễn tập route tới region dự phòng theo runbook.

### Không được tuyên bố đã chứng minh AZ resilience của managed database

Việc làm mất mạng ở **client** kiểm tra khả năng ứng dụng xử lý endpoint unavailable, **không chứng minh** chính managed database sống sót khi AZ thực bị mất. Ghi chính xác fault model trong kết quả.

### Global Tables và conflict semantics

Multi-region active-active replication có semantics khác nhau theo chế độ hỗ trợ. Đồng thời ghi cùng logical item ở nhiều regions có thể tạo conflicts hoặc phụ thuộc conflict resolution protocol. Không suy “hai regions writable” nghĩa invariant global mạnh.

### Throttling và fallback

Trong disaster, traffic dồn sang region/table khác có thể tăng hot-key pressure và throttling. Ghi logical request success, attempts, consumed capacity và end-to-end p99, không chỉ SDK retry count.

## 35. Elasticsearch/OpenSearch: shard allocation và search/write continuity

Search cluster có:

```text
Index orders
  primary shard P0
  replica shard R0

Zone A: P0
Zone B: R0
Zone C: coordinator / other shards
```

Khi Zone A mất:

- Replica có thể được promote theo engine/allocation policy.
- Cluster sẽ có thời gian phát hiện, elect/master hoặc reassign shard.
- Search queries có thể thành công/partial fail tùy shard availability và query policy.
- Indexing latency có thể tăng hoặc reject.
- Shard recovery/rebalancing tăng I/O sau fault.

### Search ACK khác search visibility

```text
Index write acknowledged
Search index refresh pending
Query still returns old result
```

Khi đánh giá, phân biệt:

- Search API availability.
- Indexing API ACK/durability.
- Refresh/query visibility lag.
- Source-to-index freshness (CDC).
- Missing/duplicate documents.

### Không chỉ nhìn cluster color

Một cluster có trạng thái phân bổ shards “green/yellow” không đủ chứng minh p99, data correctness hoặc end-user search. Ngược lại, một replica thiếu làm giảm fault tolerance nhưng search hiện vẫn hoạt động; severity phụ thuộc risk và time-to-repair.

## 36. Document vs graph vs wide-column: mục tiêu fault khác nhau

| Kiểu datastore | Những thứ cần kiểm tra thêm |
|---|---|
| Document | Transaction/read concern, primary election, change streams |
| Key-value | Single-key authority, TTL/caches, conditional writes |
| Wide-column | Partition hotspots, replica placement, consistency per query |
| Graph | Traversal fan-out, cross-partition edges, consistency của quan hệ |
| Search | Shard allocation, index refresh, replica promotion |
| Vector | ANN index availability, shard retrieval completeness, stale embeddings |
| Time series | Ingest ordering, retention, downsampling/rollups |

Không sử dụng một canary `GET key=foo` để chứng minh một **graph traversal nhiều hops** còn đáp ứng latency hoặc một **vector search** còn đủ chất lượng recall khi mất một AZ.

### Kết quả theo từng access pattern

Với graph:

```text
Get node by ID: 20 ms
Traverse relationships depth 5: timeout
```

Với search:

```text
Index document success: yes
Query returns incomplete shards: yes
```

Với time-series:

```text
Ingest accepts points
Late events or rollups not visible
```

**Availability SLO phải gắn với operation thực**, không dùng một kết quả health check chung cho mọi kiểu truy vấn.

## 37. Sharding: mất một zone có thể ảnh hưởng không đều

Một NoSQL sharded cluster:

```text
Shard S1: primary in A, replicas B/C
Shard S2: primary in A, replicas B/C
Shard S3: primary in B, replicas A/C
Shard S4: primary in C, replicas A/B
```

Mất A khiến S1/S2 cần failover; S3/S4 vẫn còn primaries nhưng mất secondary capacity. Một client query có thể:

- Chỉ route tới một shard.
- Scatter-gather tới nhiều shards.
- Thực hiện transaction/conditional operation trên một hay nhiều shards.

### Đo theo shard

- Which shards became unavailable?
- Shard leader election duration.
- Replica lag và recovery workload.
- Query latency theo hot shard.
- Cross-shard transactions/aggregations.
- Rebalancing data movement.

Global average query latency có thể che một hot shard ngừng phục vụ cho một tenant lớn. Nhưng alert theo từng partition key/user ID có thể gây cardinality lớn; dùng bounded shard/cluster identifiers và trace samples phù hợp.

## 38. CDC và event pipelines: nguồn khỏe chưa đủ

Một pipeline:

```text
MongoDB Orders
   |
   v
CDC connector -> Kafka -> Search consumer -> Search index
```

Khi Zone A mất:

- Connector pod có thể mất.
- Connector đọc source log nhưng chưa checkpoint một position.
- Broker partition leaders phải failover.
- Consumer group rebalance.
- Search index có shard relocation.

### Ba tiến độ độc lập

1. Source CDC position/resume token được checkpoint.
2. Broker topic/partition offsets được publish bền.
3. Consumer checkpoint đã áp event tới sink.

Một trong ba tăng không chứng minh cả hệ đã hoàn tất.

### Diễn tập cần xác minh

- Event acknowledged từ source có mặt trên broker theo bridge contract.
- Duplicate publish sau connector failover không tạo duplicate business effect.
- No missing event across source position resume.
- Consumer không commit offset trước sink durable effect.
- Search source revision đạt latest expected revision sau catch-up.
- Source WAL/oplog/stream retention còn đủ khi connector lag.

### CDC backlog là một phần thời gian phục hồi

DB read/write đã phục hồi sau 3 phút nhưng search index còn trễ 45 phút. Nếu user-facing contract cần search mới trong 60 giây, **hệ chưa phục hồi hoàn toàn** dù cluster chính healthy.

## 39. Cửa sổ retention và khả năng catch-up

Giả sử:

```text
Source change log retention: 60 min
Connector unavailable:       45 min
Connector backlog replay:    30 min
```

Nếu source log chỉ giữ lịch sử 60 phút và connector không đọc kịp, có thể hết nguồn history trước khi hoàn tất. Đây là tình huống **mất khả năng replay**, không phải chỉ “consumer chậm”.

### Ước lượng drain time

Nếu backlog có \(B\) events, source tiếp tục tạo \(\lambda_{\text{in}}\) events/s và consumer xử lý \(\mu_{\text{out}}\) events/s:

\[
T_{\text{drain}}\approx
\frac{B}{\mu_{\text{out}}-\lambda_{\text{in}}}
\]

chỉ khi \(\mu_{\text{out}}>\lambda_{\text{in}}\), công suất ổn định và không bị retention/troubles khác. Nếu tốc độ xử lý 1.000 events/s nhưng nguồn mới tạo 1.200 events/s, backlog **không thể giảm** chỉ bằng chờ.

### Đo thêm

- Oldest unprocessed event age.
- Source log retention headroom.
- Source replication/WAL backlog.
- Broker partition offset lag.
- Consumer sink write failures.
- End-to-end source-to-visible latency.

Một alert “Kafka lag = 0” không phát hiện source connector đã dừng publish từ nhiều phút trước.

## 40. Cache fallback: khi mất một AZ, database có chịu được miss storm?

Sự cố cache:

```text
Redis cache in Zone A fails
     |
     v
App B/C cache MISS
     |
     v
DB read QPS increases 5x
     |
     +-- pool wait increases
     +-- read p99 increases
     +-- DB write quorum overloaded
```

### Biện pháp có thể kiểm chứng

- Cache keys đầy đủ tenant/scope.
- Bounded fallback concurrency.
- Singleflight/coalescing theo đúng canonical key.
- TTL jitter và prewarm có giới hạn.
- Rate-limits ưu tiên critical read/write paths.
- Stale-while-revalidate nếu freshness contract cho phép.
- Không dùng stale authorization allow hoặc old inventory khi nghiệp vụ cấm.

### Khi thực hành

Không chỉ giả lập một Redis MISS. Hãy mô phỏng lượng cache miss đại diện khi **toàn một zone mất**, đồng thời có traffic đọc/ghi bình thường.

### Rewarm sau fault

Redis trở lại không có nghĩa hệ hết tải: hàng triệu keys có thể phải rewarm, tạo secondary stampede. Đo time-to-normal-hit-ratio, DB fallback QPS, p99 và memory evictions sau recovery.

## 41. Multi-region: active-passive, warm standby và active-active

Các mô hình thường gặp:

### Active-passive

```text
Region R1: serves reads/writes
    |
    +-- async replication --> Region R2: standby
```

Khi R1 mất, R2 được promote/route traffic theo runbook. Cần biết:

- RPO theo replication lag.
- RTO cho promotion, DNS/ingress, client config.
- Key management/secret availability ở R2.
- R2 có đủ capacity không?
- Source of truth sau failover là bên nào?
- Có cơ chế failback an toàn không?

### Warm standby

R2 chạy với công suất thấp hơn và cần scale up khi disaster. RTO bao gồm **thời gian scale, warm indexes/cache và điều chỉnh topology**. Nếu control plane cũng lỗi, cần đánh giá khả năng scale trong tình huống xấu.

### Active-active

```text
R1 handles local writes  <--->  R2 handles local writes
```

Khó hơn ở conflict resolution, global uniqueness, ordering, session consistency và data ownership. Hai regions có thể tiếp tục nhận local writes khi WAN partition nhưng business invariant cần:

- Per-region ownership/escrow quota.
- CRDT/merge semantics phù hợp.
- Conditional access to a shared authority nếu có.
- Conflict queue/compensation/reconciliation.

Không viết “active-active = không mất data, không conflict” nếu không có protocol tương ứng.

## 42. Region failover cần chống split-brain và failback sai

Một disaster runbook thiếu fencing:

```text
T0 R1 active.
T1 R1 unreachable from operators.
T2 Promote R2.
T3 R1 still serves some local clients.
T4 Both R1 and R2 accept writes.
```

Khi mạng hồi phục, hai regions đã có writes không tương thích. Một hệ không có multi-master conflict strategy có thể gặp **split-brain**.

### Cần có

- Quy tắc xác định **write authority**/epoch.
- Fencing/disable old-primary write path theo giao thức hỗ trợ.
- Quorum/control authority hoặc failover policy rõ.
- Idempotency keys và reconciliation sau failover.
- Biện pháp chặn clients route tới authority cũ.
- Kiểm tra replication catch-up trước **failback**.
- Không đảo chiều replication bừa khi hai phía đã có khác biệt.

### Failure detection khác failure proof

Nếu R1 unreachable từ R2, điều đó **không chứng minh R1 đã chết**. Nó có thể chỉ bị network partition. Failover phải được thiết kế để không giả định “không thấy = không còn ghi”.

### Recovery safety

Khi R1 trở lại, không tự thêm nó vào replication topology rồi để nó ghi đè state mới của R2. Cần rejoin/rebuild/failback procedure theo engine và integrity checks.

## 43. Lựa chọn failover: manual hay automatic?

| Tiêu chí | Automatic failover | Manual failover |
|---|---|---|
| Tốc độ | Có thể nhanh hơn | Tùy thời gian người vận hành |
| Risk split-brain | Cần correctness protocol mạnh | Con người vẫn có thể quyết sai |
| Ước lượng lỗi | Dựa health checks/election | Có thể xác minh thêm bằng nhiều kênh |
| Scale | Tự động tốt cho sự cố lặp lại | Khó cho hàng nghìn incidents |
| Kiểm soát | Rules và abort guardrails | Approval và evidence |

Không có một lựa chọn luôn tốt. Một system có consensus leader election nội tại có thể failover automatic trong cluster, nhưng **cross-region promotion** có thể cần cơ chế kiểm soát chặt do RPO/conflict và network partition.

### Quyết định dựa trên rủi ro

- Một order read cache path cho phép stale có thể auto switch.
- Payment ledger/cross-region strong write authority đòi xác minh epoch/partition và provider state.
- Bypass authorization hoặc giảm write durability chỉ để giảm RTO là phương án nguy hiểm.

## 44. Capacity N−1 và cơ hội “failover thành công nhưng hiệu năng không đạt”

Giả sử ba AZ bình thường có tổng năng lực phục vụ 12.000 requests/s, chia đều 4.000 mỗi AZ. Khi mất một AZ, 2 AZ còn lại phải phục vụ 12.000, tức 6.000 mỗi AZ.

Nếu mỗi AZ tối đa 5.000 requests/s trong SLO:

\[
2\times5000=10000<12000
\]

Dù replication/quorum khỏe, **thiếu 2.000 requests/s capacity**.

### Hai cách đáp ứng

1. Dành sẵn headroom để N−1 capacity đủ chịu peak.
2. Chấp nhận degraded mode có **priority admission control** và business contract đã công bố.

Không dựa vào autoscaling phản ứng “tức thì” nếu scale nodes, warm cache hoặc rebalance mất nhiều phút. Thời gian đó vẫn phải tính vào RTO/availability SLO.

### Workload không chia đều

Một hot tenant/partition có thể dồn QPS vào shard cụ thể. Tổng capacity toàn cụm đủ nhưng một shard không đủ, vẫn gây tail latency. Cần đo theo shard/tenant tier/kind of operation chứ không chỉ tổng CPU.

## 45. Phiên bản phần mềm và failover

Trong rolling upgrade:

```text
Zone A: app v4 / DB version X
Zone B: app v5 / DB version X
Zone C: app v5 / DB version X
```

Nếu mất A, các clients v5 phải tiếp tục. Nếu mất B/C, app v4 còn lại có thể không hiểu schema mới.

### Diễn tập nên thử khi nào?

- Trước/giữa rolling upgrade theo môi trường được phép.
- Khi cả old/new clients đồng tồn tại.
- Khi schema/codec hoặc event version thay đổi.
- Khi driver/client retry semantics đã được chỉnh.
- Khi topology/quorum migration.

### Rủi ro

- Old app không deserialize value mới.
- Event consumer cũ không đọc new schema.
- Old client failover discovery không hỗ trợ topology mới.
- Feature flag khác giữa zones.
- Schema migration đã chạy trên DB nhưng application rollback không tương thích.

**High availability là thuộc tính của cả quá trình triển khai**, không chỉ một trạng thái cluster ổn định.

## 46. Khi rơi vào degraded mode phải hiển thị đúng API semantics

Một policy:

| Endpoint | Degraded response | Điều kiện |
|---|---|---|
| `GET /products` | Trả stale catalog kèm freshness metadata | Không vượt stale allowance |
| `GET /orders/{id}` | Có thể từ chối strong read nếu không đạt source contract | Không trả trạng thái sai |
| `POST /orders` | `503` hoặc `202 Pending` nếu durable intent thực sự ghi được | Không giả thành công |
| `POST /payments` | Trạng thái unknown/reconciliation | Không double capture |
| `GET /search` | Trả index stale hoặc cảnh báo degraded | Theo freshness SLO |
| Admin writes | Từ chối khi không bảo đảm authz/quorum | Không bypass security |

### 202 Accepted có điều kiện

Chỉ trả `202` nếu **yêu cầu đã được lưu bền** ở một authority hợp lệ và có workflow xử lý/retry. Không lưu request vào RAM ở Zone A có nguy cơ mất rồi hứa xử lý sau.

### Retry-After không phải lời hứa thời gian

Một response `503` kèm `Retry-After` có thể hướng client retry sau khoảng phù hợp, nhưng khi recovery chưa chắc chắn không nên cam kết thời điểm mà hệ không kiểm soát. Client cần backoff/jitter và idempotency.

## 47. SLO evaluation phải bao gồm phân bố thời gian và số request

Một phép đo “99.9% uptime trong giờ thử” có thể che:

- 30 giây đầu hệ hoàn toàn thất bại, sau đó khỏe.
- Một zone/tenant lớn chịu 100% lỗi.
- p99 latency tăng 20 lần nhưng requests vẫn trả 200.
- CDC source-to-visible lag tăng đến 20 phút.
- Hệ trả cached stale data quá thời hạn.

### Các cách tổng hợp

- Availability ratio theo logical business requests.
- Latency percentiles/rate dưới threshold (p50/p95/p99).
- Error budget consumed trong thí nghiệm.
- Per-region/per-zone/per-tenant-tier impact.
- Worst minute/short-window availability.
- User journey completion ratio (checkout).
- Recovery time distribution cho mỗi loại operation.

### Traffic-weighted và zone-specific

Nếu Region R1 có 99% traffic và R2 1%, global success ratio có thể che R2 outage. Vì vậy cần SLO cho global và những local slices critical, song tránh metric labels per-user/tenant gây cardinality quá cao.

## 48. Observability phải tồn tại bên ngoài miền lỗi đang thử

Một anti-pattern:

```text
Metrics server: Zone A
Logs collector: Zone A
Alertmanager: Zone A
Chaos controller: Zone A

Experiment: isolate Zone A
Result: monitoring disappears
```

Khi fault đúng, **không còn evidence** để biết hệ có đang đáp ứng SLO. Cần:

- Đường blackbox probes từ zones khác.
- Monitoring/telemetry storage có availability phù hợp.
- Artifact của fault injector được ghi tới vùng/cơ chế độc lập.
- Notification path không phụ thuộc độc nhất vào vùng bị thử.
- Clock/time synchronization/trace correlation được hiểu đúng.
- Một kênh vận hành để tắt thí nghiệm khi metrics mất.

### Missing data khác zero failures

Nếu exporter của Zone A mất, Prometheus query có thể trả empty vector. Không tự coi đó là “lag=0” hoặc “errors=0”. Có alerts cho **telemetry coverage/missing data** và synthetic probes.

### Timestamps có thể lệch

Khi mạng bị partition, đồng hồ nodes có thể không chính xác; việc so source event timestamp và client completion timestamp phải xét clock skew. Để đánh giá linearizability, cần một instrumentation method có ranh giới invocation/completion đáng tin và uncertainty được nhận diện, không chỉ sort log theo timestamp.

## 49. Metrics cần thu thập trong game day

| Metric gợi ý | Mục đích |
|---|---|
| `business_read_success_ratio` | Đọc hợp lệ đáp ứng deadline/consistency |
| `business_write_success_ratio` | Ghi đúng nghiệp vụ |
| `business_unknown_outcome_total` | Writes chưa xác định commit |
| `request_duration_seconds` histogram | p95/p99 và error-budget |
| `client_driver_retry_attempts_total` | Retry amplification |
| `client_pool_wait_seconds` | Connection pressure |
| `client_server_selection_latency` | Topology re-discovery |
| `db_quorum_availability` | Quorum/election status |
| `db_leader_changes_total` | Failover/fencing |
| `db_replica_lag_seconds` | RPO/freshness indicator, theo engine |
| `db_repair_or_rebuild_backlog` | Recovery progress |
| `db_disk_capacity_headroom` | Compaction/rejoin safety |
| `redis_evictions_total` | Cache pressure |
| `cache_fallback_qps` | Shock xuống DB |
| `cdc_source_checkpoint_lag` | Source reader progress |
| `broker_consumer_lag` | Broker backlog |
| `projection_freshness_seconds` | Dữ liệu dẫn xuất visible |
| `duplicate_business_effects_total` | Correctness violations |
| `acked_writes_missing_total` | Durability violations |
| `fencing_rejects_total` | Old owner stale writes |
| `fault_injector_scope_audit` | Fault tác động đúng scope |
| `test_restore_duration` | Recoverability nếu cần |

Đây là **tên minh họa**, không phải metric mặc định của mọi SDK/NoSQL. Cần map sang counters, gauges, histograms, events và data reconciliation jobs thực tế.

### Thu cả số lần retry và số requests logic

```text
1 customer order
  -> attempt1 timeout
  -> attempt2 success

business logical requests = 1
driver attempts           = 2
```

Không lấy driver attempt error ratio làm user-facing availability ratio nếu định nghĩa SLO ở logical operation boundary.

## 50. Kiểm tra history sau diễn tập

Một record thí nghiệm:

```json
{
  "testRunId": "GAME-2026-11-14-01",
  "requestId": "REQ-1001",
  "operation": "CreateOrder",
  "idempotencyKey": "REQ-1001",
  "scope": "synthetic-tenant-T01",
  "invokeTime": "2026-11-14T10:00:00Z",
  "completeTime": "2026-11-14T10:00:05Z",
  "resultClass": "UNKNOWN_TIMEOUT",
  "sourceRevision": null,
  "observedOrderIdsAfterRecovery": ["ORDER-1001"]
}
```

Đây là **record synthetic minh họa**, không phải proof of correctness một mình.

### Vì sao lưu invocation/completion?

Có thể kiểm tra:

- Hai requests nào overlap?
- Một read có bắt đầu sau khi một write đã hoàn tất?
- Có read trả state cũ trái consistency contract không?
- Một idempotency key có tạo hai successful effects không?
- Writes đã được ACK nhưng biến mất khi read source sau recovery không?

### Unknown outcome phải được xử lý

Đừng gán `UNKNOWN_TIMEOUT` vào category “write failed chắc chắn” và bỏ qua. Sau fault, truy vấn ledger/source authority để xem effect đã commit, pending hay cần manual reconciliation.

### Dữ liệu thử

Chỉ dùng synthetic customers/orders/payments hoặc môi trường được phép, không cố tạo payment thật để kiểm chứng double charge.

## 51. Java 17: mô hình client probe ghi nhận logical outcomes

Để đo khả năng tiếp tục phục vụ, một Java probe nên phân biệt **business result** với số lần gọi DB và giữ được request history. Ví dụ dưới đây không phụ thuộc driver cụ thể, phù hợp để kết nối một adapter MongoDB/Cassandra/DynamoDB test.

```java
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

enum Outcome {
    SUCCESS,
    REJECTED_BY_CONTRACT,
    UNKNOWN_TIMEOUT,
    UNEXPECTED_FAILURE
}

record ProbeResult(
    String operationId,
    String operation,
    Instant invokedAt,
    Instant completedAt,
    Outcome outcome,
    String observedRevision,
    String errorCategory
) {}

interface NoSqlCanaryAdapter {
    // Must use a dedicated synthetic namespace.
    String writeIdempotently(
        String operationId,
        String payload,
        Duration deadline
    ) throws Exception;

    String readRevision(
        String operationId,
        Duration deadline
    ) throws Exception;
}

public final class AvailabilityProbe {
    private final NoSqlCanaryAdapter adapter;

    public AvailabilityProbe(NoSqlCanaryAdapter adapter) {
        this.adapter = adapter;
    }

    public ProbeResult createOne(Duration deadline) {
        String id = UUID.randomUUID().toString();
        Instant start = Instant.now();
        Outcome outcome = Outcome.UNEXPECTED_FAILURE;
        String revision = null;
        String error = null;

        try {
            revision = adapter.writeIdempotently(
                id,
                "synthetic-canary-data",
                deadline
            );
            outcome = Outcome.SUCCESS;
        } catch (java.util.concurrent.TimeoutException ex) {
            // Remote outcome may be unknown even though client timed out.
            outcome = Outcome.UNKNOWN_TIMEOUT;
            error = "timeout";
        } catch (Exception ex) {
            error = "other";
        }

        return new ProbeResult(
            id, "CreateCanary", start, Instant.now(),
            outcome, revision, error
        );
    }
}
```

### Những điểm chưa được giải quyết bởi code này

- `NoSqlCanaryAdapter` phải cung cấp **atomic idempotency** và source-specific durability, không chỉ insert với random key rồi retry.
- `TimeoutException` có thể được SDK wrap bởi error khác; adapter cần phân loại theo chính API.
- `Instant.now()` không phải monotonic clock; nếu cần latency, dùng `System.nanoTime()` hoặc timer monotonic và ghi wall clock chỉ để correlation.
- Một result `SUCCESS` có thể vẫn cần post-failover verification để phát hiện data loss.
- Không ghi payload nhạy cảm, credentials hoặc raw exception stack vào metrics.
- Tất cả probes phải có rate limit, cleanup/TTL và kill switch.
- Code **không tự chạy**; chỉ là thiết kế adapter/probe học tập.

## 52. Java: kiểm tra read-your-writes và idempotent retries

Một phép đo cơ bản:

```text
1. Create synthetic order with idempotencyKey K.
2. Record ACK/revision R if success.
3. Simulate/recover from fault.
4. Retry create with K.
5. Read authoritative source by K.
6. Assert exactly one logical order and expected revision.
```

Pseudo-Java:

```java
record OrderAttempt(
    String idempotencyKey,
    String orderId,
    String resultClass
) {}

interface OrderTestRepository {
    OrderAttempt createWithKey(
        String key,
        String syntheticPayload
    ) throws Exception;

    long countOrdersByIdempotencyKey(String key)
        throws Exception;
}

public final class IdempotencyProbe {
    public static void assertOneLogicalOrder(
        OrderTestRepository repository,
        String key
    ) throws Exception {
        long count = repository.countOrdersByIdempotencyKey(key);
        if (count != 1L) {
            throw new IllegalStateException(
                "Expected one order for test key; count=" + count
            );
        }
    }
}
```

### Mục tiêu

Mã không chứng minh ứng dụng có correct idempotency. Nó giúp diễn đạt **assertion cần kiểm tra sau retry/failover**. Repository phải query source có authority phù hợp, không dùng cache có thể stale để đếm rồi kết luận.

### Nếu count = 0 sau timeout?

Cần đối chiếu transaction/operation ledger và retry semantics; có thể write chưa commit hoặc đang pending. Nếu một write đã được ACK thành công trước fault rồi count = 0 sau recovery, đó là tín hiệu **durability/RPO violation** theo hợp đồng đã đặt.

## 53. Quản lý thời gian và đo p99 đúng cách

Một công cụ đo có thể báo:

```text
Average latency: 80 ms
Max latency: 20 seconds
p99 latency: 4 seconds
```

Average thấp không có nghĩa SLO của người dùng vẫn đạt. Trong failover, một phần nhỏ requests có thể bị đợi hết server-selection timeout, retries hoặc queueing.

### Đo theo các pha

1. Baseline trước fault.
2. Fault injection và leader transition.
3. Steady state khi miền lỗi còn mất.
4. Khôi phục link/nodes.
5. Rebuild/repair/CDC catch-up.

Nếu chỉ tổng hợp tất cả pha, một hồi phục dài có thể bị che bởi khoảng baseline.

### Coordinated omission

Load generator kiểu **closed-loop** (đợi request trước hoàn thành mới gửi tiếp) có thể tự giảm arrival rate khi DB chậm, khiến số requests bị ảnh hưởng bị báo thấp. Muốn đánh giá capacity/latency dưới offered load cố định, cân nhắc open-loop generator có kiểm soát và báo riêng:

- Offered requests/s.
- Achieved successful requests/s.
- Rejected/throttled requests.
- Queue wait, client timeout.
- p50/p95/p99 và histogram đầy đủ.

### Không chạy load quá mức đã phê duyệt

Phép đo under load phải có giới hạn rate và abort criteria. Một stress test đến khi DB sập hoàn toàn khác bài chứng minh khả năng chịu mất một zone.

## 54. Kết hợp PromQL và reconciliation thay vì một biểu đồ duy nhất

Giả sử Java services xuất metric:

```text
business_operations_total{
  service="orders",
  operation="create",
  outcome="success|error|unknown"
}
```

Một tỷ lệ thất bại logic theo 5 phút (biểu thức mẫu):

```promql
sum by (service, operation) (
  rate(business_operations_total{
    service="orders",
    operation="create",
    outcome="error"
  }[5m])
)
/
clamp_min(
  sum by (service, operation) (
    rate(business_operations_total{
      service="orders",
      operation="create"
    }[5m])
  ),
  1e-9
)
```

Đây chỉ là công thức giả định labels/instrumentation đúng. `unknown` được tính trong denominator nhưng không numerator của “error”; với SLO thật cần **định nghĩa riêng unknown outcome là bad event hay pending trong deadline**, không âm thầm coi unknown là success.

### Alert mất telemetry

Nếu Zone A chứa exporter và nó ngừng báo, một metric per-node có thể biến mất; `lag > threshold` sẽ không firing khi series không tồn tại. Cần:

- Scrape target health.
- Synthetic probes từ nơi độc lập.
- Alert no-data khi expected source biến mất.
- External heartbeat cho notification pipeline nếu cần.

### Reconciliation vẫn bắt buộc

Metric success rate không phát hiện một order bị nhân đôi nếu API trả 200. Chỉ đối chiếu **idempotency ledger + source state + downstream effects** mới phát hiện correctness violations.

## 55. Tránh metric cardinality explosion trong game day

Anti-pattern:

```text
db_probe_latency{
  requestId="REQ-123456",
  orderId="O-1001",
  email="person@example.invalid"
}
```

Một series mỗi request gây nổ cardinality và có nguy cơ lộ PII.

### Labels phù hợp hơn

```text
environment, service, operation, region,
zone, database_cluster, error_class, experiment_id
```

`experiment_id` cần là ID có số lượng giới hạn trong retention window. Raw request IDs và order IDs để trong structured logs/traces có quyền, **không** trong metric labels.

### Data protection

Canary data nên synthetic, logs redacted, không đưa provider secrets, payloads hay names của khách hàng thật vào dashboard. Một diễn tập resilience không nên tự trở thành sự cố bảo mật.

## 56. Phục hồi khi mạng nối lại: rejoin không có nghĩa hết sự cố

Khi fault injector khôi phục network:

```text
Zone A reconnects
    |
    +-- old leader/worker may return
    +-- replicas catch up
    +-- shards redistribute
    +-- CDC replay duplicates possible
    +-- caches rewarm
    +-- background repair/compaction increases load
```

### Phân biệt các pha recovery

**Phase 1 — Network recovered:** connections hoạt động.

**Phase 2 — Cluster control recovered:** election/topology/config đồng thuận.

**Phase 3 — Data recovered:** replicas/partitions catch up hoặc repair.

**Phase 4 — Downstream recovered:** CDC/search/cache projections trong freshness bound.

**Phase 5 — Business reconciled:** unknown writes, duplicates và invariants được xác minh.

Không đóng game day chỉ ở Phase 1 nếu mục tiêu là tiếp tục phục vụ **đúng và đủ**.

## 57. Catch-up và rebalancing có thể gây sự cố thứ cấp

Một zone mới trở lại và bắt đầu nhận replicated data:

```text
Disk/network: busy with replica catch-up
CPU: index rebuild
DB clients: normal production traffic
Cache: cold keys
CDC: backlog replay
```

Các công việc recovery cạnh tranh với user traffic. Có thể cần:

- Bounded repair/rebuild concurrency.
- Throttle background jobs.
- Prioritize critical traffic.
- Rebalance theo waves có monitor.
- Đảm bảo disk headroom cho compaction/index rebuilding.
- Trì hoãn scale-down quá sớm khi backlog chưa hoàn tất.

### Một kết quả tưởng như lạ

Write p99 có thể **xấu hơn sau khi fault kết thúc** do hàng loạt rebuild và cache warm-up. Vì vậy đo cả post-fault tail latency thay vì chỉ t0–t10.

## 58. Restore và backup trong kịch bản mất toàn miền lỗi

Nếu majority/source log không phục hồi được và phải restore:

```text
Select verified recovery point
   |
   v
Validate object integrity and decryption keys
   |
   v
Restore into approved isolated target
   |
   v
Replay change logs within retained window
   |
   v
Validate tenant scope / invariants / indexes
   |
   v
Promote/route clients with fencing
```

### Các phép đo

- Có backup hợp lệ ngoài fault domain bị mất không?
- KMS key/identity đủ để decrypt trong vùng phục hồi không?
- Restore thực tế mất bao lâu (RTO)?
- Recovery point tương ứng mất bao nhiêu acknowledged writes (RPO)?
- Backup/snapshot và log replay có cùng consistent boundary không?
- Có hồi sinh deleted data hoặc ghi đè revisions mới không?

### Disaster recovery không chỉ có backup file

Một backup có thể tồn tại nhưng:

- Không đủ key grants.
- Không có IaC/schema/index configuration.
- Chỉ còn trong storage cùng region đang lỗi.
- Log retention không đủ để replay.
- Restore capacity/quotas không khả dụng.
- Runbook chưa được diễn tập.

**Backup availability khác restore capability**.

## 59. Security và quyền khẩn cấp khi failover

Trong disaster, đội vận hành có thể muốn cấp quyền quá rộng để sửa nhanh:

```text
Grant DB admin to all operators
Open public object storage
Disable TLS verification
Disable authz for API
```

Đây không phải phương án resiliency hợp lệ chỉ vì giảm RTO ngắn hạn.

### Break-glass an toàn hơn

- Credential/role ngắn hạn, phê duyệt theo policy.
- Strong authentication và audit.
- Scope destination/environment/operation.
- Tách quyền restore vs key decrypt khi phù hợp.
- Hạn thời gian và tự revoke.
- Kế hoạch rollback/reconciliation.

### Khôi phục không được lộ tenant data

Một cross-region restore/rebuild có thể thay route/ACL/index mapping. Sau restore cần xác minh:

- App tenant scope.
- Source DB policies/roles.
- Search index aliases.
- Cache keys có tenant scope.
- CDC consumer ACL và downstream secrets.

Việc phục vụ lại 100% requests nhưng trả dữ liệu của tenant khác là **thất bại nghiêm trọng**.

## 60. Rủi ro của “tự sửa” trong diễn tập

Một số hành động dễ làm sự cố tệ hơn:

| Hành động phản xạ | Vì sao nguy hiểm? | Cách tiếp cận |
|---|---|---|
| Restart toàn bộ replicas | Có thể mất quorum/leader | Xác minh fault domain, rolling procedure |
| Force primary mà không fencing | Split-brain/conflicting writes | Có authority/quorum policy rõ |
| Tắt write concern/durability | Có thể mất acknowledged data | Duy trì business durability contract |
| Retry payment với ID mới | Double charge | Idempotency + provider reconciliation |
| Flush toàn bộ cache | DB stampede | Controlled fallback/TTL/generation |
| Skip CDC offset cho nhanh | Mất derived data | Replay/DLQ/reconcile theo protocol |
| Tăng concurrency không giới hạn | Retry storm, quá tải survivors | Bounded admission/backoff |
| Chạy full repair/compaction ngay | Disk/IO overload | Planned rate-limited recovery |
| Scale down khi replica còn lag | Mất redundancy/capacity | Verify catch-up and redundancy |
| Tắt alerts bằng broad silence | Che secondary incident | Scope/time-bound alert handling |

### Diễn tập một quyết định vận hành

Một game day tốt phải cho team thực hành **chọn không thực hiện một hành động nguy hiểm**, chứ không chỉ chọn lệnh khôi phục. Mục tiêu là **sự đúng đắn và tính liên tục**, không phải đưa dashboard xanh nhanh nhất.

## 61. Mẫu kế hoạch game day có thể dùng lại

```yaml
experiment:
  id: "GF-2026-11"
  title: "Orders - simulated Zone A isolation"
  environment: "isolated-preproduction"
  owner: "orders-sre"
  approved_by: "policy-defined-approvers"
  hypothesis:
    reads: "allowed reads within stated freshness/latency SLO"
    writes: "majority-backed writes do not lose acknowledged effects"
    retries: "idempotent writes produce one logical effect"
    recovery: "CDC projections catch up within defined budget"
  fault:
    class: "zone-network-isolation"
    scope: "approved-zone-A-test-resources"
    direction: "bidirectional"
    duration: "approved-short-duration"
    automatic_expiry: true
  controls:
    synthetic_data_only: true
    independent_monitoring: true
    manual_kill_switch: true
    rollback_documented: true
    abort_thresholds: "see experiment approval"
  evidence:
    - "synthetic-request-history"
    - "cluster-topology-timeline"
    - "client-error-and-latency-metrics"
    - "cdc-source-and-consumer-checkpoints"
    - "post-recovery-reconciliation"
```

Đây là **file minh họa** cho phần mô tả thiết kế; nó không tương ứng syntax của chaos tool cụ thể, và không được xem là authorization để inject fault. Trên hệ thật, approval, scope, abort thresholds và experiment duration phải là các giá trị được xác nhận.

### Tránh thiếu điều kiện dừng

Không dùng `abort_thresholds: "any errors"` nếu test cố ý muốn quan sát khoảng lỗi có kiểm soát; ngược lại cũng không dùng “abort only when every node dead” khi business đã bị ảnh hưởng nghiêm trọng trước đó. Đặt tiêu chí từ SLO, data safety và blast radius.

## 62. Mẫu báo cáo kết quả: pass/fail phải có bằng chứng

```text
Experiment: GF-2026-11
Environment: preproduction
Fault: Zone A bidirectional isolation, 10-minute window
Actual affected resources: 3 app pods, 1 DB member, 1 cache replica

Expected:
  - majority writes from B/C resume under 60s
  - no acknowledged order lost
  - no duplicate order per idempotency key
  - search freshness returns under 60s within 15m of recovery

Observed (hypothetical):
  - majority writes resumed in 78s (FAIL)
  - 0 acked orders missing (PASS)
  - 0 duplicate orders (PASS)
  - search caught up after 21m (FAIL)

Root findings:
  - client DNS cache retained old primary route
  - CDC workers underprovisioned for catch-up

Actions:
  - adjust discovery/driver configuration after verification
  - increase bounded CDC recovery capacity
  - re-run game day with identical workload/fault scope
```

Các số ở đây là **giả định phục vụ học tập**, không phải kết quả đo từ một cụm thực tế.

### Những trường nên thêm trong report thật

| Nhóm | Nội dung |
|---|---|
| Traceability | Experiment ID, tickets, approvals, versions |
| Baseline | Traffic, p99, pool, cluster topology, resource headroom |
| Fault actual | Scope, start/stop timestamps, injection audit |
| Service | Success/error/timeout, throughput, p50/p95/p99 |
| Data | ACKed writes, source revisions, consistency, duplicates |
| Recovery | Leader change, rejoin, repair, CDC catch-up |
| Safety | Abort events, unintended impacts, security observations |
| Follow-up | Owners, severity, due dates, regression tests |

### Khi nào đánh dấu inconclusive?

- Fault injector không thật sự cô lập zone dự kiến.
- Traffic không đủ đại diện.
- Telemetry mất trong lúc test.
- Cluster đang có incident ngoài phạm vi.
- Không có source of truth để xác minh writes.
- Abort quá sớm theo policy khiến chưa đủ bằng chứng.

**Inconclusive không phải pass.** Có thể báo “chưa chứng minh” thay vì cố biến kết quả mơ hồ thành thành công.

## 63. Fault-injection matrix cho một service NoSQL

| Kịch bản | Trục thử | Câu hỏi chính |
|---|---|---|
| Kill 1 DB process | Node crash | Quorum/leader thay đổi? Client phát hiện? |
| Lose AZ containing leader | Full fault domain | RTO và capacity survivors? |
| Lose AZ without leader | Full fault domain | Replication/redundancy có giảm nguy hiểm? |
| Isolate minority AZ | Network partition | Minority có bị fence đúng? |
| Make network asymmetric | Partial partition | Client retry/unknown outcomes? |
| Delay inter-zone packets | Network latency | p99/commit latency và failure detector? |
| Fail DNS/metadata endpoint | Discovery/control dependency | DB còn sống nhưng client có route không? |
| Deny KMS/secret API temporarily | Security dependency | Existing sessions/new starts khác nhau? |
| Cache AZ unavailable | Dependent failure | DB fallback đủ capacity? |
| Broker zone lost | Event pipeline | CDC/consumer offsets và lag? |
| Pause CDC connector | Log retention | Resume/replay có mất gap? |
| Pause old worker across lease expiry | Stale ownership | Sink reject old epoch? |
| Kill app after sink commit before checkpoint | Ambiguous processing | Duplicate-safe replay? |
| Remove search replica AZ | Derived serving | Query availability và visibility lag? |
| Fail backup-region access | Recoverability | Backup/key độc lập? |
| Restore old snapshot to isolated region | DR | RPO/RTO/deletion replay? |
| High load after zone loss | N−1 capacity | p99, queuing, throttling? |
| Simulated client request timeout after commit | Ambiguous write | Exactly one business effect? |
| End fault and rejoin all nodes | Recovery | Repair/backlog pressure, no regression? |

Khi chọn một case, **một trục thay đổi chính** giúp biết nguyên nhân hơn là ngắt cả network, disk, DNS, KMS cùng lúc trong một bài đầu tiên.

## 64. Case study A: ba voters nhưng hai ở cùng AZ

Topology:

```text
Zone A: Voter 1, Voter 2
Zone B: Voter 3
Zone C: App only
```

Majority của ba voters là 2. Khi mất A:

\[
3-2=1<Q=2
\]

Cụm không còn majority, writes yêu cầu quorum không thể cam kết. Thay đổi application retries **không tạo ra majority**.

### Bài học

Khi mục tiêu là chịu mất bất kỳ một zone, phải xét voter/replica placement theo mỗi zone, không chỉ tổng số nodes.

### Đánh giá

- Nếu thiết kế đã công bố “chịu mất một AZ bất kỳ”, đây là **kiến trúc không đạt mục tiêu**.
- Nếu business chấp nhận tạm read-only, kiểm tra degraded mode có trả status đúng.
- Thay đổi placement/voting cần thực hiện theo maintenance protocol và đánh giá dữ liệu, không dời nodes tùy ý trong incident.

## 65. Case study B: quorum còn nhưng pool wait phá SLO

Topology ba zones, một AZ mất. Majority còn, primary mới được bầu.

```text
Normal:
  requests/s = 6000
  DB CPU ~45%
  client pool wait p99 = 5ms

After losing Zone A:
  surviving DB CPU ~95%
  retry amplification = 3x
  pool wait p99 = 3s
  business write timeout ratio = 17%
```

Các số giả định. Quorum bảo đảm một số điều kiện an toàn, nhưng surviving capacity không đủ và retries làm tải tăng.

### Root hypothesis

- Retries thiếu bounded budget/jitter.
- Pool/worker concurrency vượt DB capacity.
- Hot shard leaders dồn vào zones B/C.
- Cold cache tăng fallback queries.

### Thay đổi

Giới hạn retries, ưu tiên critical requests, sử dụng N−1 headroom, xử lý hot shards/partition design, tách background workloads. Sau đó **chạy lại cùng fault model và offered load** để xác nhận.

### Không khắc phục bằng giảm durability mù

Nếu writes đang yêu cầu majority, chuyển sang single-replica ACK để hạ p99 có thể đổi RPO/consistency contract; không được gọi đây là “đã đạt availability” khi tính đúng bị hy sinh ngoài chính sách.

## 66. Case study C: application AZ còn sống nhưng bị route sai

```text
Zone A isolated from DB B/C
App A still responds to /healthz
Ingress routes 33% users to App A
App A DB queries hang 30s
Apps B/C are healthy
```

### Sự cố

Database có majority ở B/C; client routing/health check mới là điểm gây HTTP timeouts.

### Hành động có thể kiểm chứng

1. Kiểm tra readiness/blackbox probe khác liveness.
2. Bỏ app A khỏi target group theo quy trình, không nhất thiết kill DB.
3. Theo dõi error budget và retry QPS.
4. Kiểm tra khi A rejoin readiness chỉ mở khi phụ thuộc tối thiểu đủ tốt.
5. Giữ audit của route change và verify traffic không dồn quá mức B/C.

### Kết luận

Một diễn tập chỉ kiểm tra DB failover sẽ **bỏ sót lỗi ở đường client**. End-to-end business SLI mới phân biệt được.

## 67. Case study D: cached allow sau khi revoke quyền

Giả sử authorization data có source quorum ở B/C, nhưng cache ở Zone A giữ:

```text
user U role = ADMIN (stale)
source role = VIEWER (new)
```

Khi A partition, app A có thể trả cached `ADMIN` nếu policy cho phép stale. Đây là **security correctness violation** khi revocation contract yêu cầu deny ngay hoặc trong bound ngắn hơn.

### Cần quyết định

- Policy epoch/version trong authorization cache.
- Hard TTL và invalidation guarantee.
- Fail-closed cho action nhạy cảm.
- Strong authority read cho permission revoke path.
- Không dùng stale-while-revalidate tùy tiện cho authorization allow.

### Test

Revoke quyền trên source, partition cache/app, thử hành động admin bằng synthetic principal, xác minh response **bị từ chối** theo contract.

### Bài học

“Read available” không phải thành công nếu đọc cho phép hành động không được ủy quyền.

## 68. Case study E: vùng dự phòng bị thiếu khóa giải mã

```text
Region R1 primary down
Region R2 contains replicated backup archive
KMS decrypt grant exists only in R1
Restore worker in R2 cannot decrypt
```

### Tác động

Backup ở R2 có nhưng **không dùng được**; mục tiêu RTO không đạt.

### Phòng ngừa

- Document key references/grants trong inventory.
- Test restore từ region/identity dự phòng, không chỉ production credential.
- Kiểm tra compliance/least privilege và key rotation.
- Có break-glass procedure được audit.
- Xác nhận encryption metadata và integrity.

### Lưu ý

Không giải quyết bằng cách bật public access hoặc tắt mã hóa. Khả năng phục hồi và bảo mật cần được thiết kế cùng nhau.

## 69. Case study F: search backlog sau khi DB đã phục hồi

```text
T0: Zone A lost; MongoDB primary moves.
T+03m: Orders API restored.
T+05m: CDC connector recovered, backlog 200k events.
T+10m: Search sink throttles; lag still grows.
T+25m: Search eventually catches up.
```

Nếu search freshness SLO là 2 phút, **vi phạm kéo dài đến T+25m**, không phải T+03m. Một game day báo thành công ngay khi Orders API quay lại đã đánh giá thiếu.

### Giảm thiểu

- Bounded sink concurrency và backpressure.
- Tăng recovery capacity trong giới hạn đã xác minh.
- Ưu tiên updates mới/critical projections khi model cho phép.
- Rebuild snapshot nếu source retention gap, không skip offset.
- So source revisions và search-visible revisions.

### Không dùng offset lag duy nhất

Broker lag có thể giảm về 0 nhưng index chưa refresh/visible. Đo từ **source commit đến query-visible state**, không chỉ consumer checkpoint.

## 70. Case study G: primary cũ quay lại

```text
T0: Zone A leader has epoch 10.
T1: Zone A partitioned; B/C elect epoch 11.
T2: B/C accept new writes.
T3: Zone A reconnects.
T4: Old async task from epoch 10 attempts stale write.
```

### Expected

- DB protocol xử lý old leader đúng semantics.
- External sink hoặc application state **không nhận stale write** nếu policy đòi epoch fencing.
- Idempotency ledger không bị trùng.
- Rejoin không làm ACKed data từ majority biến mất.

### Nếu không thể fencing external effect

Dùng provider idempotency, durable workflow, reconciliation và hạn chế stale workers để giảm rủi ro. **Một lease hết hạn không tự biến worker cũ thành process đã dừng**.

## 71. Runbook điều phối diễn tập theo từng pha

### Pha A — Chuẩn bị

1. Ghi hypothesis, expected SLI và data invariants.
2. Xác nhận topology/voters/replicas/shards và failure-domain placement.
3. Kiểm tra cluster health/lag/capacity trước fault.
4. Xác nhận approved fault scope, owner, window, abort criteria.
5. Chuẩn bị synthetic request generators và event ledgers.
6. Xác nhận monitoring/alert delivery/kill switch nằm ngoài vùng bị thử.
7. Kiểm tra rollback/failback/restore runbooks.

### Pha B — Gây lỗi

1. Bắt đầu traffic có kiểm soát.
2. Đánh dấu timestamp t0 và audit config của fault injector.
3. Kích hoạt approved failure mode có tự hết hạn.
4. Quan sát latency, errors, retries, quorum/election, traffic routes.
5. Dừng ngay khi một abort condition xảy ra.

### Pha C — Phục vụ trong lúc lỗi

1. Kiểm tra API read/write theo consistency contract.
2. Xác minh source of truth của canary records.
3. Kiểm tra duplicate effects và pending/unknown outcomes.
4. Xem fallback/cache/queue capacity, CDC retention.
5. Quan sát routing/minority behavior và incident notifications.

### Pha D — Khôi phục

1. Gỡ fault theo protocol approved.
2. Xác minh topology/election và ngăn stale owner.
3. Giới hạn repair/rebalance để tránh overload.
4. Đo replication/CDC/index/cache catch-up.
5. Đối soát ACKed writes, revisions và business invariants.

### Pha E — Kết luận

1. Ghi observed RTO/RPO và error-budget impact.
2. Liệt kê pass/fail/inconclusive theo từng workflow.
3. Liên kết evidence: plots, logs, audit và request histories.
4. Đặt owner/due date cho fix.
5. Tạo regression test/game-day replay sau thay đổi.

## 72. Những hiểu lầm phổ biến

| Hiểu lầm | Thực tế |
|---|---|
| “Ba replicas luôn chịu được mất một AZ” | Phụ thuộc placement, quorum và voting |
| “Đã thử kill một node là đã thử toàn AZ” | Một AZ còn chứa app, cache, route, broker, shared dependencies |
| “Majority còn là mọi request tiếp tục phục vụ” | Client routing, capacity và latency vẫn có thể hỏng |
| “DB có primary mới là incident hết” | Apps, CDC, cache, repairs có thể còn lag |
| “Health endpoint 200 nghĩa writes được” | Liveness/readiness khác business SLO |
| “Timeout nghĩa DB chắc chưa ghi” | Có thể commit nhưng ACK mất |
| “Retry luôn giúp availability” | Có thể gây duplicate effect và retry storm |
| “Lease hết hạn nghĩa worker cũ không còn ghi” | Cần fencing ở sink |
| “Một zone hỏng nên cứ chuyển DNS là xong” | DNS caching/pools/long-lived connections làm delay |
| “RPO=0 vì backup chạy hằng ngày” | Backup interval không chứng minh no ACKed write loss |
| “RTO bằng thời gian primary election” | Cần tính cả client recovery và business paths |
| “Quorum write đủ chứng minh mọi read linearizable” | Phụ thuộc đầy đủ protocol, read concern và topology |
| “Stale read là luôn sai” | Có thể được phép với freshness contract rõ |
| “Stale read là luôn chấp nhận” | Không với permission/payment/inventory khi contract cấm |
| “Redis trở lại là hệ đã khỏe” | Cache rewarm có thể dồn tải vào DB |
| “Kafka lag = 0 nghĩa search đã mới” | Source connector, sink visibility và consistency riêng |
| “Mất exporter nghĩa lag=0” | No-data phải được alert riêng |
| “Region backup có nghĩa restore được” | Cần keys, roles, manifests, capacity và runbook |
| “Active-active không bao giờ xung đột” | Replication/conflict protocol quyết định |
| “Failover sang R2 chứng minh R1 đã chết” | Có thể chỉ partition mạng; cần fencing |
| “Tất cả tests đều phải chạy production” | Lab, staging, tabletop và controlled scopes vẫn có giá trị |
| “Thử thật càng rộng càng chính xác” | Blast radius không cần thiết tăng nguy cơ cho user |
| “Không có HTTP 5xx là pass” | Data loss, stale reads, duplicate effects vẫn có thể xảy ra |
| “Dừng fault injection là khôi phục xong” | Còn repair/rebalance/CDC/invariant verification |
| “Một test pass là hệ sẵn sàng mãi mãi” | Topology, workload, version và dependencies có thể thay đổi |

## 73. Ba mươi bài tập thực hành

### Bài 1 — Phân biệt fault domain

Liệt kê các miền lỗi trong hệ có 3 AZ, 2 regions, một DNS resolver dùng chung và một Redis primary ở Zone A. Những thành phần nào có thể cùng thất bại dù đặt ở ba AZ?

### Bài 2 — Quorum math

Replica set có 5 voters đặt A=3, B=1, C=1. Tính quorum và kiểm tra mất mỗi zone. Đề xuất placement tốt hơn nếu yêu cầu mất bất kỳ một zone vẫn đủ majority, đồng thời chỉ ra giới hạn khi mất hai zones.

### Bài 3 — Chỉ một zone

Cluster 3 voters A/B/C, quorum 2. Mất Zone A và B cùng một lúc: có được confirm majority write? Nếu business cần luôn ghi được, còn lựa chọn kiến trúc nào và trade-off gì?

### Bài 4 — N−1 capacity

Ba zones chịu 9000 requests/s, mỗi zone chỉ phục vụ 4000 requests/s trong p99 SLO. Nếu mất một zone, liệu hai vùng còn lại đủ không? Tính load trung bình per surviving zone nếu cân bằng hoàn hảo.

### Bài 5 — Hot shard

Một shard nhận 80% QPS và primary nằm ở Zone A. Mất A, replicas B/C takeover. Tại sao total cluster CPU trung bình có thể vẫn tốt mà tenant này timeout?

### Bài 6 — Node vs AZ game day

Một team kill DB process n1, kết quả pass. Hãy liệt kê ít nhất sáu khác biệt khi thật sự mất AZ, và đề xuất một hypothesis mới.

### Bài 7 — SLO operation

Trong fault, `GET /products` trả stale 30s, `POST /orders` trả 503, `GET /orders` trả status cũ. Với business contract cho phép catalog stale 60s nhưng order reads phải mới trong 5s, endpoint nào đạt?

### Bài 8 — RTO và RPO

Fault bắt đầu 10:00, user writes bắt đầu thành công lại 10:03, source replicas catch up 10:12, search catch up 10:25. Hãy nêu các mốc RTO theo mục đích khác nhau, và dữ liệu cần thu để đánh giá RPO.

### Bài 9 — Unknown outcome

Client gửi CreateOrder, server commit rồi response mất khi Zone A bị cô lập. Client retry bằng order ID mới. Viết history tạo duplicate và đề xuất idempotency protocol.

### Bài 10 — Retry storm

1000 logical requests/s, mỗi request retry tối đa 4 attempts. Tính worst-case attempt rate, rồi mô tả backoff/jitter/rate limiting để bảo vệ survivors.

### Bài 11 — Readiness và liveness

App Zone A còn trả `/healthz=200` nhưng không truy cập quorum được, ingress vẫn gửi traffic. Hãy thiết kế readiness/blackbox checks để loại A khỏi đường critical writes mà không gây restart storm.

### Bài 12 — DNS caching

DB bầu leader mới trong 8s nhưng một số Java clients timeout đến 2 phút. Liệt kê DNS, driver topology, connection pool và server selection hypotheses cần kiểm tra.

### Bài 13 — Asymmetric network

Client A có thể gửi tới n2 nhưng không nhận reply, trong khi n2 nhận write và commit. Vì sao một chiều network failure làm ambiguous outcome? Cần test gì?

### Bài 14 — Leader fencing

Worker A giữ epoch 7, bị pause, B nhận epoch 8 rồi ghi. A tỉnh lại ghi tiếp. Đề xuất nơi kiểm tra fencing token và điều xảy ra nếu sink không chặn.

### Bài 15 — MongoDB election

Đặt MongoDB 3 voting members ở 3 AZ, primary tại A. Khi A mất, các bước nào phải diễn ra trước khi client xác nhận write mới? Tại sao cần kiểm tra write concern?

### Bài 16 — Cassandra consistency

Một datacenter RF=3 có replicas ở 3 AZ. Nếu một AZ mất, so availability có thể có của consistency `ONE` và `LOCAL_QUORUM`, và giải thích vì sao không thể kết luận tính đúng chỉ từ số ACKs.

### Bài 17 — Redis Cluster

Một shard primary ở A có replica ở B, một shard khác chỉ có copy phục vụ ở A theo cấu hình. Mất A ảnh hưởng các hash slots thế nào? Query “cluster ping OK” có đủ không?

### Bài 18 — DynamoDB managed service

Bạn chỉ có thể gây timeout từ app client tới DynamoDB endpoint, không điều khiển underlying AZ. Ghi kết luận nào hợp lệ và kết luận nào không được phép đưa ra?

### Bài 19 — Elasticsearch visibility

Search indexing API ACK nhưng search query trả trạng thái cũ 15s. Phân biệt availability, indexing durability và search freshness. Canary nào đo end-to-end tốt hơn?

### Bài 20 — CDC retention

Connector dừng 40 phút, log retention là 60 phút và backlog drain dự kiến 30 phút. Rủi ro gì? Nếu processing rate thấp hơn incoming rate, công thức drain nói gì?

### Bài 21 — Cache stampede

Redis AZ mất, cache hits giảm 90%, MongoDB fallback QPS tăng 6x. Đề xuất bounded fallback/singleflight/jitter và chỉ ra dữ liệu nào không được stale.

### Bài 22 — Region promotion

R1 không liên lạc với R2 nhưng R1 vẫn có thể phục vụ local clients. Nếu promote R2 không fencing R1, tạo ra sự cố gì? Viết failback prerequisites.

### Bài 23 — Khóa mã hóa trong vùng dự phòng

Backup object ở R2 còn nguyên nhưng KMS key của R1 bị unavailable. Kết quả RTO/RPO có thể thế nào? Thiết kế preflight restore drill.

### Bài 24 — Observability outage

Monitoring stack nằm ở Zone A, bạn định cô lập A. Những metrics nào có thể biến mất? Hãy thiết kế independent blackbox probes và abort logic.

### Bài 25 — Test history

Một request write ACK tại 10:00:05, sau failover authoritative source không thấy record. Viết kết luận kỹ thuật đúng và dữ liệu bổ sung cần xác minh trước khi đóng incident.

### Bài 26 — Data invariants

Hai clients đồng thời reserve cùng một ghế từ hai phía partition, cả hai được trả success. Tại sao availability theo HTTP 200 là metric đánh giá sai? Chọn invariant checker thích hợp.

### Bài 27 — Recovery load

Zone A trở lại, replica catch-up và cache rewarm làm p99 cao hơn khi zone còn mất. Hãy đề xuất cách đo phases và rate-limit background recovery.

### Bài 28 — Blast radius

Nhóm định cô lập network toàn region production ngay vì đã test một node pass. Viết plan tăng cấp từ tabletop/lab/staging đến approved controlled production fault và abort criteria.

### Bài 29 — Báo cáo game day

Giả sử writes hồi phục sau 90s so mục tiêu 60s, zero ACKed writes lost, CDC catch up sau 22m so mục tiêu 15m. Đặt pass/fail đúng từng chiều và viết ba follow-up actions.

### Bài 30 — Thiết kế end-to-end

Thiết kế bài diễn tập cho:

```text
Java API (3 AZ)
   -> Redis cache
   -> MongoDB replica set
   -> CDC / Kafka
   -> Elasticsearch projection
   -> Recovery object storage in another region
```

Yêu cầu tối thiểu:

- Fault hypotheses cho mất leader AZ, minority partition và region DR.
- Tenant-scoped synthetic probes, idempotency keys và history recorder.
- Quorum placement, N−1 capacity, client routing/readiness.
- RTO/RPO/freshness/consistency acceptance criteria.
- Retry/CDC/cache safeguards.
- Backup/KMS/restore access.
- Fault scope, audit, kill switch, abort conditions.
- Pass/fail report và regression plan.

## 74. Checklist trước, trong và sau diễn tập

### 74.1. Trước khi gây lỗi

1. **Fault domain được định nghĩa chính xác**: process, node, AZ, region, network segment hay shared dependency?
2. Có vẽ dependency graph bao gồm app, ingress, NoSQL, cache, CDC, DNS, KMS và backup không?
3. Đã xác minh replica/voter/shard **placement thực tế** chưa?
4. Khi mất một domain bất kỳ, majority/read-write quorum nào còn?
5. Nếu quorum còn, **capacity N−1** đủ cho peak/load thực tế không?
6. Business contract nào được giữ, contract nào cho phép degraded mode?
7. Có SLI/SLO theo read/write/freshness/correctness, không chỉ health ping không?
8. RTO/RPO được định nghĩa theo **mốc thời gian và dữ liệu** nào?
9. Có synthetic test fixtures, idempotency IDs và tenant isolation không?
10. Có nguồn dữ liệu có thẩm quyền để reconcile hậu diễn tập không?
11. Có xét writes có outcome unknown và retries không?
12. Có backup/recovery point, encryption keys và restore path được kiểm chứng không?
13. Có owner, approval, fault scope, duration, abort thresholds và rollback không?
14. Fault injector/kill switch có **nằm ngoài miền lỗi** và có TTL tự hết không?
15. Monitoring và alert delivery có khả dụng khi một zone/region mất không?
16. Có lưu baseline latency, retry, source revisions, replica lag, CDC lag và capacity không?
17. Có chặn deployments/migrations song song làm kết quả khó giải thích không?

### 74.2. Khi lỗi đang xảy ra

18. Fault đã thực sự tác động **đúng resources/zone/direction** chưa?
19. Mỗi business operation có được đo ở logical request boundary không?
20. Clients minority có bị từ chối strong writes đúng contract không?
21. Read stale (nếu được phép) có nằm trong freshness bound không?
22. HTTP 200 có thật sự mang business state đúng/đúng tenant không?
23. Có duplicate order/payment hoặc inventory invariant violation không?
24. Unknown write outcomes có được ghi nhận và xử lý an toàn không?
25. Retry amplification/connection pool waits có vượt budget không?
26. Surviving zones có đủ CPU/memory/disk/network và write capacity không?
27. Load balancer/DNS có route vào app không ready không?
28. Quorum elections và old leader fencing có đúng không?
29. Cache fallback có gây DB stampede không?
30. CDC connector/broker/consumer có giữ durable progress và replay safety không?
31. Source log retention có còn đủ khi backlog tăng không?
32. Independent monitoring có báo user impact và no-data đúng không?
33. Abort criteria đã được giám sát và có thể kích hoạt khi cần không?

### 74.3. Sau khi khôi phục

34. Khi fault hết, có old worker/leader nào vẫn gửi stale writes không?
35. Quorum/topology và replica redundancy đã trở về trạng thái mong muốn chưa?
36. ACKed writes có đầy đủ sau recovery không? Có bút toán/event nào mất không?
37. Mỗi idempotency key có **một business effect logic** không?
38. Có kiểm tra read-your-writes, monotonic revisions và các invariants quan trọng không?
39. CDC/backlog đã catch up tới source position/visible read model chưa?
40. Search/derived views có còn stale vượt budget không?
41. Cache rewarm, repair và compaction có làm p99 tăng không?
42. Backup/restore readiness có còn nguyên và không bị mất key/quyền không?
43. Có restore hoặc rejoin nào hồi sinh dữ liệu đã bị delete/thu hồi quyền không?
44. Có tính MTTD, time-to-degraded-service, time-to-full-recovery và observed RPO không?
45. Có báo cáo riêng **PASS/FAIL/INCONCLUSIVE** từng yêu cầu không?
46. Có lưu evidence và audit fault injector, không chứa PII/secret không?
47. Có cập nhật runbook, alerts, driver settings, deployment policy không?
48. Có owner/due date cho issues và lịch regression game day không?

## 75. Một cách học thực tế: bắt đầu từ một giả thuyết nhỏ

Nếu chưa có phòng lab lớn, hãy bắt đầu bằng **tabletop + ba node test + synthetic business client**:

1. Vẽ ba failure domains và kiểm tra quorum trên giấy.
2. Tạo một synthetic workload gồm create/read/update với idempotency keys.
3. Chạy thử mất một DB process.
4. Chạy thử cô lập một node test khỏi những nodes khác qua tool đã được phép.
5. Ghi client latency/errors, positions và source revisions.
6. Kiểm tra dữ liệu sau khi nối lại và test retry an toàn.
7. Mở rộng mô hình đến mất toàn AZ và shared dependencies trong staging.

### Một thay đổi mỗi lần

Khi debug fault tolerance, điều khiển nhiều biến cùng lúc khiến nguyên nhân khó phân biệt. Ví dụ:

```text
Run A: primary node unavailable
Run B: full AZ unavailable
Run C: AZ network isolation (processes alive)
Run D: full AZ + normal peak load
Run E: full AZ during rolling deployment
```

Các lần chạy không hoàn toàn giống nhau về điều kiện; lưu topology, data volume, traffic, versions và fault settings để so sánh có trách nhiệm.

### Chất lượng kết quả hơn số lượng thí nghiệm

Một bài game day có request history, source reconciliation, root-cause evidence và remedial action thường có giá trị hơn 20 bài “kill container—cluster vẫn ping được” mà không kiểm tra business correctness.

## 76. Kết luận

Diễn tập sự cố **toàn miền lỗi** là một phép thử **của hệ thống và nghiệp vụ**, không chỉ của số lượng replicas. Một cụm NoSQL có thể vẫn có quorum nhưng service không tiếp tục phục vụ vì client routing, capacity, cache, auth, DNS, KMS, CDC hoặc thao tác vận hành không đúng.

Những nguyên tắc quan trọng:

1. **Phân tích miền lỗi thực tế.** Node, AZ, region, control plane và shared dependency có blast radius khác nhau.
2. **Đếm quorum theo placement và operation**, không chỉ tổng replica count.
3. **Đo end-to-end availability theo hợp đồng nghiệp vụ.** HTTP 200/health ping không chứng minh tính đúng.
4. **RTO, RPO, consistency và freshness khác nhau.** Mỗi trục cần tiêu chí và bằng chứng riêng.
5. **Mất một zone phải đủ cả capacity.** Majority còn nhưng survivors quá tải vẫn có thể vi phạm SLO.
6. **Thiết kế idempotency, fencing và retry budgets trước failover.** Timeout có outcome unknown; old workers có thể quay lại.
7. **Network partition không phải node crash.** Hai phía đều chạy nhưng không thể cùng tự xác nhận mọi invariant global.
8. **Theo dõi toàn bộ pipeline dữ liệu.** CDC, cache, search projections, backup và recovery có tiến độ độc lập.
9. **Game day phải an toàn và có rollback.** Hypothesis, approval, bounded blast radius, independent monitoring và abort criteria là bắt buộc.
10. **Phục hồi chỉ hoàn tất khi dữ liệu đúng.** Node rejoin không đủ; phải xác minh acknowledged writes, duplicate effects, read model freshness và recovery readiness.

Câu hỏi quyết định khi thiết kế một cuộc diễn tập:

> **“Nếu mất toàn bộ một AZ hoặc bị cô lập mạng trong khi traffic vẫn tiếp tục, người dùng có thể làm được những thao tác nào với kết quả đúng, những thao tác nào phải bị từ chối hoặc chuyển sang pending, và sau khi phục hồi chúng ta có bằng chứng gì rằng không mất/nhân đôi dữ liệu đã cam kết?”**

Khi có thể trả lời câu hỏi đó bằng **quorum/topology model, business SLO, client history, fault-injection evidence, reconciliation và runbook khôi phục**, hệ NoSQL mới có cơ sở để tuyên bố khả năng **tiếp tục phục vụ một cách đáng tin cậy** khi một miền lỗi thật sự biến mất.
