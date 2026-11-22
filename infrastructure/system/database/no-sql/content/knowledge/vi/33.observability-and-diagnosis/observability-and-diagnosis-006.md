# Đo replication lag và phân biệt với độ mới của kết quả đọc

Trong một hệ thống NoSQL có replication, câu hỏi **“Replica đang chậm bao nhiêu?”** không hoàn toàn giống câu hỏi **“Người dùng có đọc được dữ liệu mới nhất không?”**. Hai câu hỏi này liên quan nhưng khác về **phạm vi, điểm đo, tính nhất quán, đường định tuyến, cache, chỉ mục, thời gian hiển thị và hành vi ứng dụng**.

Một dashboard có thể báo replication lag chỉ 20 ms, nhưng người dùng vừa đổi trạng thái đơn hàng vẫn thấy dữ liệu cũ trong vài giây do request đọc từ một cache chưa invalidated. Ngược lại, follower có lag 2 giây ở một partition ít được truy cập, nhưng request đọc đúng primary/leader vẫn thấy mọi write đã commit trước lúc bắt đầu đọc. Thậm chí, một replica có timestamp cập nhật cuối cùng cách đây 24 giờ **không có nghĩa đang trễ 24 giờ** nếu thực sự không có write nào trong 24 giờ đó.

Bài này thuộc chương **Quan sát và chẩn đoán** của module **Database No SQL**. Ta sẽ xây dựng hệ thống khái niệm và phép đo để trả lời chính xác:

- **Replication progress:** Một replica đã nhận, ghi bền hoặc áp tới vị trí nào trong lịch thay đổi?
- **Replication delay:** Một mutation đã commit ở nguồn mất bao lâu mới được replica nhận, áp và phục vụ theo contract?
- **Read freshness/staleness:** Một phép đọc trả về **phiên bản nào**, so với những writes đáng lẽ đã phải nhìn thấy theo hợp đồng consistency và thời điểm đọc?
- **End-to-end freshness:** Từ khi source ghi thành công đến khi API, cache, search index hoặc read model thực sự trả kết quả mới mất bao lâu?
- **Confidence:** Phép đo của ta có loại trừ được clock skew, sampling, missing events, resharding và multi-region conflicts không?

> **Nguyên tắc quan trọng:** Đo replication lag là đo tiến độ trên **một luồng/authority cụ thể**. Đo độ mới của kết quả đọc là xác minh **giá trị/phiên bản trả về trên đường đọc thực tế** so với một mốc tham chiếu có ý nghĩa. Không suy ra tính chất thứ hai chỉ từ một biểu đồ lag trung bình.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **write acknowledged**, **committed**, **replicated/received**, **durable**, **applied** và **query-visible** theo contract của engine.
2. Hiểu replication lag tính theo **thời gian**, **offset/sequence gap**, **bytes backlog** và **số operations backlog**.
3. Phân biệt **replica progress** với **read-your-writes**, **monotonic reads**, **bounded staleness** và **linearizable reads**.
4. Xác định vì sao replica có lag thấp nhưng API đọc dữ liệu cũ vì **cache, search refresh, routing, session hoặc read model**.
5. Hiểu vì sao một phép đo bằng wall-clock timestamp có thể sai do **clock skew, no writes, timestamp source và granularity**.
6. Thiết kế phép thử **sentinel/canary writes + versioned reads** để đo write-to-visible latency.
7. Đọc đúng ý nghĩa và giới hạn các chỉ số theo MongoDB, Redis, Cassandra/ScyllaDB, DynamoDB Global Tables và Elasticsearch/OpenSearch.
8. Dùng Java để đo `ack→visibility` với `System.nanoTime()` và **không ghi nhận read success chỉ vì target có cùng timestamp**.
9. Chẩn đoán replication backlog, follower read staleness, failover, network partition, retry và multi-region conflicts.
10. Thiết kế dashboard, SLO, alert, thí nghiệm và runbook dựa trên **đường đọc mà người dùng thực sự sử dụng**.

## 2. Tình huống xuyên suốt: cập nhật Order rồi đọc lại

Một Order Service lưu đơn hàng trong cluster NoSQL nhiều replicas:

~~~text
                  Write: Order O900 status=PAID, version=18
                               |
                               v
                         Primary / Leader
                               |
                +--------------+--------------+
                |                             |
                v                             v
           Replica A                     Replica B
         apply delay 30ms             apply delay 800ms
                |                             |
                +--------------+--------------+
                               |
                            Read API
                               |
                      Cache / Search model
                               |
                             Client
~~~

Client gửi `POST /orders/O900/confirm`, nhận phản hồi thành công, sau đó gọi `GET /orders/O900`. Có lúc client nhận `status=CREATED` dù Order trên leader đã `PAID`.

Một số khả năng:

1. GET được định tuyến tới Replica B chưa apply mutation v18.
2. GET đến Replica A mới hơn, nhưng một cache ở Java đang giữ v17.
3. GET dùng search index có refresh/indexing delay, không phải bản ghi gốc.
4. GET dùng session khác nên mất **causal/session context** cần cho read-your-writes.
5. API response POST được trả **trước commit thật** theo ứng dụng, khiến giả định “write đã commit” sai.
6. Bản ghi bị một write concurrent/merge rule khác thay đổi; đây không đơn thuần là lag.
7. Đọc qua một region khác, có conflict/reconciliation hoặc replication scope khác.

Điều cần chẩn đoán là **phiên bản người dùng thấy, nó đến từ đâu, và theo contract request đáng lẽ phải thấy phiên bản nào**.

### 2.1. Một timeline minh họa

~~~text
Wall-clock of conceptual source timeline:

t=0ms      Leader commits O900 v18
t=10ms     Client receives write ACK
t=30ms     Replica A receives and applies v18
t=80ms     Client GET through cache returns v17
t=150ms    Search pipeline has received the event
t=300ms    Search index refresh makes v18 searchable
t=800ms    Replica B finally applies v18
t=1500ms   Cache TTL expires, GET returns v18
~~~

Trong timeline minh họa:

- Replica A apply lag: ~30 ms.
- Replica B apply lag: ~800 ms.
- Search write-to-search-visible: ~300 ms.
- API-through-cache write-to-visible: ~1.500 ms.
- **Một metric `replicationLag=30 ms` không mô tả tất cả những điều trên.**

Các mốc thời gian chỉ để hình dung; thực tế write ACK, commit point, receive/apply/durable và visibility có semantics riêng theo engine. Không suy “đã được ACK” luôn bằng “đã durable trên quorum” nếu write concern không cam kết.

### 2.2. Hai sơ đồ cần tách biệt

~~~mermaid
flowchart LR
    L["Leader log/commit"] --> X["Ship records"]
    X --> R["Replica receives"]
    R --> D["Replica durable"]
    R --> A["Replica applies"]
    A --> V["Replica query-visible"]
~~~

~~~mermaid
flowchart LR
    W["Write accepted"] --> L["Leader state"]
    L --> R["Replica selected by read policy"]
    R --> C["Application cache"]
    C --> S["Search/projection if used"]
    S --> A["API response observed by client"]
~~~

Sơ đồ thứ hai chỉ biểu diễn **những tầng có thể tham gia vào một đường đọc**; không phải mọi request đều đi qua cả cache và search theo đúng thứ tự. Với API trực tiếp tới leader, đường đi ngắn hơn nhiều.

## 3. Từ vựng: những mốc thường bị gộp nhầm

| Mốc | Ý nghĩa khái niệm | Điều không tự suy ra |
| --- | --- | --- |
| **Write received** | Server nhận lệnh ghi | Không chứng minh commit |
| **Write ACK** | Client nhận phản hồi theo write concern/durability mode | Không mặc nhiên quorum durable |
| **Commit point** | Mutation trở thành committed theo protocol | Không mặc nhiên mọi replica áp |
| **Replica received** | Replica đã nhận bản ghi/change | Không chắc đã apply/query-visible |
| **Replica persisted/durable** | Replica ghi bền theo contract | Không nhất thiết đã apply cho reads |
| **Replica applied/replayed** | Mutation đã được đưa vào local state machine/data structure | Chưa chắc mọi query/search index nhìn thấy |
| **Replica query-visible** | Một dạng read cụ thể có thể thấy state | Không chắc request thực sự định tuyến tới đó |
| **Cache invalidated/refreshed** | Cache không còn trả bản cũ | Không đồng nghĩa search index đã refresh |
| **Client observed** | API/client thật sự nhận một giá trị/version | Cần so với expected consistency |

**Chú ý:** Thứ tự giữa durable và applied **không có một quy luật duy nhất** áp cho mọi engine. Một số hệ ghi WAL trước khi apply, một số kỹ thuật in-memory replication có contract durability khác; hãy dựa vào khái niệm và chỉ số vendor thực sự cung cấp.

### 3.1. Source, authority và replica

Trong leader–follower, “source” thường là leader/primary tại một term/epoch xác định. Nhưng các hệ peer-to-peer, quorum, multi-master hoặc active-active **không có một leader toàn cục đơn giản**.

Nếu tồn tại nhiều writers, cần nói:

~~~text
Replication of what?
  From which region / authority / term?
  To which replica / region?
  For which partition / key?
  To what observable state?
~~~

Không gọi “lag toàn cluster” mà thiếu những phạm vi này.

### 3.2. Write concern quyết định mốc ACK

Một write ACK có thể đại diện:

- Được server nhận/đặt vào memory.
- Đã commit theo log của node chính.
- Đã được một số replicas thừa nhận.
- Đã được một số replicas ghi bền.

Tùy engine/consistency mode, các mức này khác nhau. **Cần định nghĩa `t_ack` trước khi dùng nó làm điểm bắt đầu SLO**.

### 3.3. Read concern quyết định mốc quan sát

Một read được cấu hình eventual, quorum, majority, causal session, linearizable hoặc bounded staleness có contract khác nhau:

- Đọc từ một follower tùy ý có thể thấy bản cũ.
- Đọc “majority committed” có thể yêu cầu mức committed nhưng không bảo đảm luôn là **commit mới nhất tại thời điểm đọc**.
- Đọc linearizable (nếu được hỗ trợ và cấu hình đúng) có yêu cầu strong recency theo thứ tự thực.
- Causal consistency/session token có thể bảo đảm read-your-writes trong phạm vi và điều kiện công bố.

Do đó **không thể diễn giải `stale read` nếu chưa biết hợp đồng consistency của request**.

## 4. Ba đại lượng đo phổ biến: time lag, position lag và byte lag

### 4.1. Time lag

Một định nghĩa khả dụng khi có timestamps tương thích:

\[
L_{\mathrm{apply}}(t)=
t_{\mathrm{now}}-t_{\mathrm{commit}}(P_{\mathrm{lastApplied}})
\]

Trong đó \(P_{\mathrm{lastApplied}}\) là vị trí log mới nhất replica đã apply, và nguồn phải cho biết commit time của vị trí tương ứng theo **một miền thời gian có thể so sánh**.

**Cảnh báo:** Nếu trong nhiều giờ không có write, `now - lastAppliedCommitTime` có thể tăng dù replica đã bắt kịp hoàn toàn. Để gọi đó là *lag*, thường cần so **tiến độ leader với replica** chứ không chỉ lấy tuổi bản ghi cuối.

Một cách mô tả khác:

\[
L_{\mathrm{timestamp}} =
T_{\mathrm{leaderLatest}}-T_{\mathrm{replicaLatestApplied}}
\]

với điều kiện cả hai timestamps được cấp theo **cùng nguồn/order semantics**. Đây là phép đo tiến độ tương đối; nó có thể bị sai hoặc không có ý nghĩa khi timestamps chỉ là wall clock của nodes khác nhau.

### 4.2. Position/sequence lag

Nếu leader log cùng partition đang ở offset 9.500 và replica apply tới offset 9.350:

\[
L_{\mathrm{position}}=9500-9350=150\text{ log entries}
\]

Với một **ordered append-only stream và cùng identity/epoch**, đây là 150 entries chưa apply theo quy tắc offset đó. Nó **không tự nói 150 entries mất bao nhiêu milliseconds hoặc bytes**.

### 4.3. Byte backlog

Nếu source log progress tới 1,80 GiB, replica đã nhận/tiêu thụ tới 1,65 GiB trong cùng stream:

\[
B_{\mathrm{backlog}}=1{,}80-1{,}65=0{,}15\text{ GiB}
\]

Một backlog 150 MiB có thể nhỏ đối với link 10 Gbit/s, nhưng rất lớn nếu cần replay nhiều random disk writes hoặc chịu một transaction apply chậm.

### 4.4. “Entries behind” khác “seconds behind”

Một entry có thể là một metadata operation vài bytes; entry khác có thể chứa một document 1 MiB hoặc trigger expensive index updates. **Không chia entries cho QPS một cách mù** để hứa lag thời gian.

### 4.5. Receive lag khác apply lag

~~~text
Leader offset:     10000
Replica received:   9990
Replica durable:    9820
Replica applied:    9500
~~~

Trong ví dụ:

- **Ship/receive gap**: 10 entries.
- **Durable gap**: 180 entries.
- **Apply gap**: 500 entries.

Network gần bắt kịp nhưng local apply còn chậm, có thể vì CPU, lock, index maintenance hoặc storage. Điều này chỉ là mô hình; từng sản phẩm có thể đặt tên/quan hệ các mốc khác.

## 5. Phân biệt “độ mới” của dữ liệu và “độ mới” của kết quả đọc

### 5.1. Bản ghi không đổi không đồng nghĩa stale

Một customer profile được chỉnh lần cuối **sáu tháng trước** và không có write mới. Một read hôm nay trả cùng version cũ vẫn có thể **hoàn toàn đúng và mới nhất**.

~~~text
Last write: 2026-05-01
Latest committed version today: v7
Read today returns: v7
~~~

Độ tuổi của `updatedAt` là sáu tháng, nhưng **version staleness = 0**.

### 5.2. Record age và read staleness khác nhau

| Metric | Câu hỏi |
| --- | --- |
| **Record age** | Đã bao lâu từ lần bản ghi được chỉnh? |
| **Replica progress lag** | Replica còn bao nhiêu thay đổi chưa nhận/apply? |
| **Read-version gap** | Kết quả đọc thiếu bao nhiêu versions so với authority? |
| **Write-to-visible delay** | Một write đã cam kết cần bao lâu để read path nhìn thấy? |
| **Read-your-writes violation** | Client đã ghi rồi đọc mà không thấy write của mình? |
| **Bounded staleness violation** | Kết quả cũ hơn giới hạn business/consistency đã thỏa thuận? |

Không dùng `now - record.updatedAt` như chỉ số replication lag.

### 5.3. Freshness phải gắn với điều kiện so sánh

Để nói “GET O900 stale”, cần trả lời:

1. Write nào **đã commit**?
2. Write đó xảy ra **trước lúc GET bắt đầu**, trước GET kết thúc, hay concurrent?
3. Read dùng policy consistency nào?
4. GET được route tới replica/cache/index nào?
5. Version/ETag hoặc dữ liệu kết quả là gì?
6. Có concurrent writes/conflict resolution làm source version thay đổi không?

Nếu write còn in-flight khi read bắt đầu, một GET trả trạng thái cũ có thể **không vi phạm** một consistency contract mạnh trong trường hợp concurrency hợp lệ. Phải xác định history của operations.

### 5.4. Read your writes

Một client gửi `PUT O900 v18` và nhận ACK đáp ứng contract. Trong cùng session/caller context, lần GET kế tiếp được kỳ vọng nhìn thấy ít nhất effect v18 nếu hệ cung cấp **read-your-writes guarantee**.

Ở hệ eventual consistency không có session pinning/causal token, kỳ vọng này có thể không được bảo đảm. Ứng dụng có thể:

- Đọc từ leader/primary theo policy phù hợp.
- Truyền session/causal consistency token và chờ replica bắt kịp.
- Dùng conditional/linearizable read nếu hệ hỗ trợ.
- Hiển thị optimistic UI/“đang đồng bộ” nếu UX chấp nhận eventual.

### 5.5. Monotonic reads

Client thấy Order v18 ở GET lần thứ nhất, rồi thấy v17 ở GET lần thứ hai do load balancer chuyển qua replica cũ hơn:

~~~text
GET #1 -> Replica A -> v18
GET #2 -> Replica B -> v17
~~~

Đây là **read regression** theo client. Một hệ có monotonic reads/session consistency không nên cho trải nghiệm đó trong phạm vi bảo đảm; raw eventual reads có thể xảy ra.

### 5.6. Search freshness khác point-read freshness

Search index có thể đã nhận event v18 nhưng chưa refresh segment để query tìm kiếm thấy tài liệu mới. Một API đọc document theo key có thể có semantics visibility khác search query. Đừng dùng chỉ số “follower replica caught up” để khẳng định search index mới.

### 5.7. Cache TTL không trực tiếp bằng replica lag

Một cache TTL 10 giây có thể giữ v17 ngay cả khi cả primary và followers đã apply v18. Nếu API lấy dữ liệu từ cache:

\[
\text{API freshness delay}
\approx\text{cache invalidation/expiry delay}
\]

trong trường hợp đó, không phải replication transport là giới hạn chi phối. Thời gian có thể dài hơn TTL khi stale-while-revalidate, refresh failures hoặc lỗi invalidation.

## 6. Tại sao một biểu đồ `replication_lag_seconds` có thể đánh lừa?

### 6.1. Trung bình che replica chậm nhất

Giả sử 5 replicas có lag:

~~~text
Replica A: 20 ms
Replica B: 30 ms
Replica C: 40 ms
Replica D: 50 ms
Replica E: 5,000 ms
~~~

Lag trung bình ~1.028 ms; con số này che việc **một replica lag 5 giây**. Nếu load balancer vẫn gửi 20% reads tới E, p95/p99 người dùng có thể xấu đáng kể.

Phân tích **max per replica/partition**, weighted exposure theo read routing và read-version observations.

### 6.2. Không có writes thì `lastAppliedAge` tăng

~~~text
00:00 leader last write L100
00:00 replica applied L100
12:00 leader still at L100; replica still at L100
~~~

Replica đã bắt kịp, dù `now - lastAppliedWallClock = 12 giờ`. Metric chỉ đo tuổi sự kiện cuối, **không** phải backlog.

Để đo trong thời gian không có writes có thể dùng **heartbeats/progress markers** được nguồn tạo trong cùng stream phù hợp; không tự suy heartbeat qua network có nghĩa mọi key đã apply.

### 6.3. Clock skew tạo lag âm hoặc dương giả

Nếu leader clock nhanh hơn follower 500 ms, lấy `follower now - leader timestamp` có thể cho lag âm hoặc lớn sai. Cần:

- So source positions/offsets trong cùng stream.
- Dùng source-assigned timestamps có cùng clock domain và contract.
- Đo elapsed duration monotonic tại cùng process cho probe writes/reads.
- Dùng clock-sync telemetry kèm uncertainty nếu phải so timestamps chéo node.

### 6.4. Metrics scrape không đồng bộ

Collector lấy leader progress lúc 12:00:01, follower progress lúc 12:00:05 rồi trừ có thể tạo **sai lệch giả** khi write rate cao. Nên đồng bộ/correlation snapshots, gắn collection timestamp và nêu measurement error.

### 6.5. Offset gap qua các shards không so trực tiếp

~~~text
Shard A: leader offset 1000, follower 900
Shard B: leader offset 50,   follower 48
~~~

Không cộng 100+2 rồi gọi là lag 102 entries trên một hàng đợi đồng nhất nếu log positions/shard operations có sizes/weights khác. Cần theo **từng stream/shard**, sau đó tổng hợp theo khái niệm đúng và gắn với đường đọc.

### 6.6. Replica caught up nhưng read vẫn stale

Các tình huống:

- Cache không invalidated.
- GET được route sang region khác chưa đồng bộ.
- Search refresh/derived projection chưa cập nhật.
- Read được phục vụ từ snapshot/transaction lâu đời.
- Client có local cache.
- `read concern` cho phép bản cũ hơn.
- Một key đã move shard nhưng routing/topology metadata chưa đồng bộ.

**Zero reported lag không chứng minh mọi read đã latest.**

### 6.7. Replica lag cao nhưng read vẫn fresh

GET buộc đọc từ primary với consistency phù hợp; follower B lag 5 giây không tác động trực tiếp GET này. Tuy nhiên **availability/failover risk** vẫn đáng quan tâm nếu replica B là ứng viên promotion hoặc cần quorum.

## 7. SLO: định nghĩa độ mới theo nghiệp vụ trước khi đo

Một hệ phải phân biệt:

**SLO A — Replication progress**

> Với mỗi follower có thể phục vụ reads, 99% thời gian chênh lệch commit-to-apply nằm dưới 500 ms, trừ những khoảng failover được công bố.

**SLO B — Read-your-writes**

> Sau khi `PUT Order` nhận ACK theo write concern được định nghĩa, GET kế tiếp của cùng session nhìn thấy write đó theo request contract.

**SLO C — Search freshness**

> 99% các thay đổi đã commit xuất hiện trong search results trong vòng 3 giây.

**SLO D — Analytics/read-model freshness**

> 99% các mutations thuộc dataset hỗ trợ được phản ánh trong materialized view trong vòng 60 giây.

**SLO E — Lag during failover**

> Khi failover, hệ phát hiện replica không eligible phục vụ reads vì quá ngưỡng staleness và không đưa traffic vào nó cho tới khi phục hồi.

Các ngưỡng trên đều là **giả định để học**, không phải cam kết của NoSQL cụ thể.

### 7.1. Định nghĩa SLI cho đúng

Ví dụ:

\[
\mathrm{SLI}_{\mathrm{freshReads}} =
\frac{\text{Eligible reads meeting defined freshness contract}}
{\text{All eligible reads observed}}
\]

Với read-your-writes, eligible reads phải có **được ghi nhận write ACK + session/version context** để kiểm tra. Không lấy mọi GET vô điều kiện rồi so `updatedAt` vì nhiều keys không có writes mới.

### 7.2. Độ mới có thể không phải một số giây

Ứng dụng có thể quan tâm “**có nhìn thấy ít nhất version v18 không?**” hơn “trễ bao nhiêu milliseconds”. Version-bound/causal guarantees thường kiểm chứng bằng version/operation identity. Một lần GET v18 có thể đến 50 ms sau ACK; một hệ khác GET v17 trong 5 ms không đạt read-your-writes dù rất nhanh.

### 7.3. Một SLO có thể cần nhiều loại phép đo

- **Replica progress lag** để phát hiện follower chậm trước khi ảnh hưởng user.
- **Versioned probe reads** để đo người dùng thật sự thấy gì.
- **Search refresh/indexing lag** để phân biệt CDC và search.
- **Cache hit/freshness** để phát hiện stale cache.
- **Error/timeout/retry rate** để tránh chỉ đo những probes thành công.

### 7.4. Một chỉ số quá tổng quát không thể đại diện nhiều contracts

Không đặt `max_lag < 1s` rồi coi đó là bằng chứng cho:

~~~text
No stale reads
No lost acknowledged writes
No cross-region conflicts
No eventual search lag
No read-your-writes violations
~~~

Mỗi mục có phạm vi và phương pháp xác minh riêng.

## 8. Thiết kế đo replication lag theo tiến độ log

Một phương pháp quan sát leader–follower là thu:

~~~text
source partition ID
source term / epoch
source commit/high-water position
replica received position
replica durable position
replica applied position
replica last query-visible position (nếu API cung cấp)
sample timestamps và collector identity
~~~

Nếu replica không có khái niệm query-visible position, **không tự ghi giá trị đó bằng lastApplied**. Khi đó cần phép đo read probe ở tầng cao hơn.

### 8.1. Bảng thu theo một partition

| Tầng | Ví dụ position | Lag tương đối |
| --- | ---: | ---: |
| Leader last committed | 4.800 | 0 |
| Replica received | 4.796 | 4 entries |
| Replica persisted | 4.790 | 10 entries |
| Replica applied | 4.720 | 80 entries |
| Target search index visible | Không có position tương ứng | Không suy được |

Chỉ được tính hiệu số nếu các positions **thuộc cùng ordered stream và cùng generation/term**. Nếu log truncation/failover tạo epoch mới, phải dùng API metadata để đối chiếu, không trừ offset vô nghĩa.

### 8.2. Nếu replica receive gần nhưng apply chậm

Các khả năng:

- Replica CPU/quota/GC cao.
- Write amplification, index maintenance.
- Storage write/fsync latency.
- Long transaction/apply lock.
- Replay bị chặn bởi dependency/order.
- Một partition có mutation đắt hơn nhiều partitions khác.

Mạng chưa chắc là nút thắt nếu bytes đã tới replica nhưng apply queue tăng.

### 8.3. Nếu replica receive chậm

Các khả năng:

- Network congestion/loss giữa nodes/regions.
- Source log shipper throttled.
- Bandwidth/quota/egress limit.
- Follower không thể fetch vì retry/connection churn.
- Lag lớn đến mức yêu cầu snapshot/reseed.
- Replica không còn eligible hoặc đang bootstrap/recovery.

Đo **source send rate**, follower receive rate, backlog bytes, retransmits, network RTT và health trạng thái replica.

### 8.4. Nếu durable chậm nhưng applied nhanh

Không suy replica an toàn cho failover chỉ vì read nhìn thấy state mới nếu durability contract yêu cầu persisted/quorum ACK. Theo engine, background fsync và state machine apply có thể khác thứ tự; phải đo **đúng mốc durability** và xác định promotion/ACK guarantees.

### 8.5. Nếu leader không có writes mới

Với stream event-driven, source và replica positions bằng nhau là dấu hiệu caught up về log, nhưng độ trễ của **lần nhận một write mới** chưa được kiểm tra. Dùng các probe writes có tần suất thấp nếu SLO yêu cầu đo liên tục; không tự suy đường replication sẽ luôn nhanh vì idle.

### 8.6. Một metric theo timestamp cần những điều kiện gì?

Nếu muốn dùng:

\[
L=T_{\text{source-most-recent-commit}}-
T_{\text{replica-most-recent-applied-commit}}
\]

thì phải có:

1. Hai timestamps đại diện **cùng logical commit timeline**.
2. Source và replica không dùng clock domains không thể so.
3. Có write đủ mới; nếu idle cần heartbeat.
4. Không lấy một shard cuối tiến xa để che shard chậm.
5. Không bị update/garbage collection của metric sai sampling window.

## 9. Đo từ góc nhìn người đọc: versioned write-to-visible probe

Muốn biết API hoặc follower có trả dữ liệu mới không, cần **tạo một thay đổi có phiên bản nhận diện được rồi đọc qua chính đường đọc cần kiểm tra**.

### 9.1. Giao thức probe cơ bản

1. Chọn một key thử nghiệm chuyên dụng, không chứa PII, và **target route** cụ thể.
2. Ghi một giá trị mới kèm `probeId`, `generation`, `version` theo source mutation contract.
3. Chỉ bắt đầu tính `ack→visible` sau **write ACK** đáp ứng mức consistency đã xác định.
4. Ghi mốc `t_ack` bằng **monotonic clock trong cùng probe process**.
5. Lặp GET qua đường read được kiểm tra, giữ deadline/poll interval hợp lý.
6. Lần đầu đọc thấy `generation/version >= expected` với đúng payload, ghi `t_visible`.
7. Tính:

\[
L_{\mathrm{write\to visible}} =
t_{\mathrm{visible}}-t_{\mathrm{ack}}
\]

8. Nếu hết deadline chưa thấy, ghi **censored observation/timeout**, không bỏ mẫu khỏi thống kê.

Nếu cần đo từ **source commit** thay vì client ACK, phải có source commit timestamp/position tương thích và xác định bù thêm ACK travel delay; đừng gọi `ack→visible` là `commit→visible` một cách im lặng.

### 9.2. Dữ liệu probe mẫu

~~~json
{
  "probeKey": "__observability/replication/probe-17",
  "generation": "run-2026-11-14-a",
  "version": 381,
  "nonce": "fixed-for-logical-write",
  "payload": "synthetic-only"
}
~~~

`nonce` và version giúp phát hiện stale read; không dùng timestamp client như version **trừ khi consistency contract bảo đảm điều đó**.

### 9.3. Đo đường đọc nào?

Một phép đọc có thể đi:

~~~text
Probe A -> direct leader primary-key read
Probe B -> direct follower primary-key read
Probe C -> regional read endpoint with normal routing
Probe D -> Java repository with application cache enabled
Probe E -> public API with CDN/edge caching
Probe F -> search/materialized view
~~~

Mỗi probe là **một SLI khác nhau**. Không trộn cả sáu vào một `replicationLag` histogram.

### 9.4. Vì sao không chỉ dùng một key thử nghiệm?

Một key có thể thuộc partition khỏe. Một số partitions khác có lag lớn vì hot keys, placement, compaction hoặc replication conflict.

Nên có một **tập probes rải theo partition/range/region/read route**, với tần suất và chi phí kiểm soát. Metadata chọn key phải phản ánh phân phối production nếu muốn dùng kết quả để nói về tổng hệ.

### 9.5. Tránh ghi dồn vào một probe key

Nếu liên tục cập nhật cùng key trước khi phiên bản trước visible, probe có thể thấy v400 khi đang đợi v398. Với mục tiêu “đã thấy ít nhất state sau write v398” có thể chấp nhận, nhưng nếu muốn đo **từng write’s exact visibility**, cập nhật chồng có thể làm v398 không bao giờ được đọc thấy riêng.

Có thể dùng:

- Key riêng cho mỗi sample hoặc generation.
- In-flight probe limit thấp.
- Trạng thái success `>= expected` nếu chỉ quan tâm causal progress.
- Source commit event/position mapping khi cần phân tích mọi mutation.

### 9.6. Poll interval tạo sai số

Nếu poll mỗi 250 ms, một write visible sau 10 ms có thể chỉ được phát hiện ở t=250 ms. Phép đo có **resolution/detection delay** xấp xỉ khoảng poll interval và scheduling/network overhead. Không quảng bá độ chính xác 1 ms từ probe poll 250 ms.

### 9.7. Failed reads và timeouts

Nếu GET timeout 10 lần rồi lần 11 thấy version mới, metric `t_visible−t_ack` bao gồm giai đoạn read failure. Đó là điều hữu ích đối với end-to-end user experience. Nhưng nếu muốn tách **replication progress** và **API availability**, cần thêm metric read error rate/latency riêng.

### 9.8. Security và cleanup

Probe writes phải:

- Không kích hoạt billing/payment/email hoặc tác vụ nghiệp vụ thật.
- Không tạo PII.
- Có TTL/retention/cleanup hợp lý.
- Không làm nóng một partition quá mức.
- Có namespace/permissions riêng.
- Không làm phá metric vì TTL delete là mutation mới làm đổi version bất ngờ.

## 10. So sánh observed version với source ground truth

Trong production, khó đo toàn bộ reads bằng synthetic probes. Một hướng khác là **gắn source version/ETag vào writes và reads**, rồi so sánh khi có context.

### 10.1. Một bản ghi Order có version

~~~json
{
  "tenantId": "tenant-a",
  "orderId": "O900",
  "status": "PAID",
  "version": 18,
  "generation": 1
}
~~~

Nếu client vừa có ACK cho version 18, GET trả version 17, đây là bằng chứng trực tiếp về **read regression so với write của client**, **nếu** version tăng đơn điệu dưới authority đó và read contract yêu cầu read-your-writes.

### 10.2. Phiên bản không tương đương wall-clock

Một `version=18` không cho biết bản cập nhật đã xảy ra bao lâu. Muốn đo seconds to visible, cần các mốc thời gian monotonic trong một probe hoặc một clock source đáng tin.

### 10.3. Hai phiên bản không đồng nghĩa lag “một giây”

`sourceVersion=100`, `readVersion=97` nghĩa thiếu **3 transitions**, nhưng 3 transitions có thể diễn ra trong 1 ms hoặc 3 ngày. Chỉ số:

\[
\mathrm{versionGap}=100-97=3
\]

chỉ có ý nghĩa nếu versions liên tiếp trong một phạm vi key và không reset; với source có reserved/skipped sequence numbers, hiệu số không nhất thiết bằng số mutations.

### 10.4. Multi-writer và version reset

Nếu two regions cùng cấp version 18 concurrent, không có winner rõ bằng phép so `max(version)`. Nếu Order bị delete/recreate cùng key và version reset về 1, read v1 mới không phải stale so với tombstone v19 cũ nếu có **generation/epoch** mới.

### 10.5. Gắn expected version với session context

Ứng dụng có thể lưu:

~~~text
sessionId: session-77
lastAcknowledgedWrite:
  aggregateId: tenant-a/O900
  generation: 1
  version: 18
~~~

GET trong session có thể dùng context này để:

- Route tới replica đủ mới nếu driver hỗ trợ.
- Đợi phù hợp deadline.
- Sử dụng stronger read policy.
- Hoặc trả trạng thái eventual kèm `currentVersion=17` và dấu `syncing`.

Không dùng một Redis local counter có thể mất dữ liệu thay cho source version authoritative.

### 10.6. Read-version sampling trong production

Một số requests có thể log:

~~~json
{
  "requestId": "synthetic-trace-92",
  "readRoute": "follower-region-b",
  "aggregateIdHash": "stable-anonymized-hash",
  "expectedGeneration": 1,
  "expectedVersion": 18,
  "observedVersion": 17,
  "consistencyContract": "causal-session",
  "result": "VERSION_BEHIND"
}
~~~

Không log raw customer IDs, content hay session secrets vào metrics. Log sampling cần phân tầng theo region/shard/read policy để không chỉ lấy thành công.

## 11. Bốn độ trễ khác nhau trong một đường đọc

Một write được gửi tới hệ và cuối cùng được thấy ở search endpoint:

~~~text
t0: source commit Order v18
t1: source follower applies v18
t2: CDC connector receives event v18
t3: target index writes document v18
t4: target search refresh makes v18 searchable
t5: application cache invalidates
t6: user GET/search returns v18
~~~

Ta có các chặng:

\[
L_{\mathrm{sourceReplica}}=t_1-t_0
\]

\[
L_{\mathrm{CDC}}=t_2-t_0
\]

\[
L_{\mathrm{indexVisible}}=t_4-t_0
\]

\[
L_{\mathrm{userObserved}}=t_6-t_0
\]

**Cảnh báo:** Nếu t1…t6 được lấy từ những hosts có clocks khác nhau, không tự trừ như đồng hồ đồng bộ tuyệt đối. Công thức minh họa để xác định *conceptual event time intervals*; phép đo thực cần monotonic probe, source-commit timestamps có semantics rõ, distributed tracing với clock uncertainty hoặc correlate positions.

### 11.1. Application cache có thể là điểm chậm nhất

Nếu source follower v18 sau 50 ms, search query thấy sau 200 ms, nhưng cache vẫn giữ v17 đến 5 giây, user-visible staleness bị cache quyết định.

### 11.2. CDC lag không bằng database replication lag

CDC connector đọc từ nguồn, đẩy sang broker/target index. Một CDC `consumer_lag=1000 offsets` là **tiến độ connector** trên một log, không phải primary/follower replication lag của storage engine.

### 11.3. Search indexing ACK khác search visibility

Việc target index xác nhận nhận write có thể đến trước lúc query search thấy tài liệu, tùy refresh/consistency. Một số search engines hỗ trợ real-time GET theo ID khác với search query. Đo đúng **endpoint người dùng sử dụng**.

### 11.4. Replica có latest state nhưng API trả cache stale

Muốn định vị:

1. Đọc source authoritative version.
2. Đọc trực tiếp replica được chọn (bypass app cache).
3. Đọc qua app repository có cache.
4. Đọc qua public API/CDN.
5. So các versions dưới cùng expected write context.

Không đo những steps này tại thời điểm xa nhau rồi coi là cùng snapshot nếu source còn thay đổi; cần versioned probe/history.

### 11.5. API trả stale không luôn là bug

Một endpoint analytics “dữ liệu trễ tối đa 5 phút” có thể đúng contract khi trả snapshot cách 30 giây. Ngược lại, endpoint checkout cần kiểm tra stock/unique reservation có thể không được phép dựa vào read model eventual dù lag trung bình chỉ 100 ms.

**Correctness được đánh giá theo contract, không chỉ tuổi data.**

## 12. Consistency models và việc diễn giải stale reads

### 12.1. Eventual consistency

Nếu writes ngừng và các replicas có thể tiếp tục đồng bộ, dữ liệu cuối cùng hội tụ theo guarantee của hệ. Một read từ follower bất kỳ có thể thấy bản cũ trong thời gian chưa đồng bộ.

“Eventually” **không tự là một ngưỡng 500 ms**. Nếu ứng dụng cần bounded freshness, phải có SLO/selection policy/measurement riêng.

### 12.2. Strongly consistent/linearizable reads

Trong phạm vi sản phẩm hỗ trợ, linearizability yêu cầu một operation đọc thấy trạng thái phù hợp thứ tự thực của các completed operations. Một read sau write hoàn tất không thể “nhìn ngược” quá write ấy theo cùng object/authority contract.

Không gắn nhãn linearizable cho một read chỉ vì nó đi tới primary; cần đúng API, read concern, write concern, failover protocol và guarantee sản phẩm.

### 12.3. Causal consistency

Causal consistency có thể bảo vệ quan hệ “write của tôi xảy ra trước read của tôi” khi client truyền đúng **session/causal tokens** và driver/source hỗ trợ. Nó không tự bảo đảm mọi read ở mọi sessions nhìn thấy toàn bộ writes toàn cluster mới nhất.

### 12.4. Monotonic reads

Một client đã thấy v18 không bị quay về v17 qua các reads sau trong cùng phạm vi. Nếu load balancer đổi follower mà không có session token, client có thể thấy regression theo eventual behavior.

### 12.5. Bounded staleness

Một hệ có thể mô tả giới hạn theo **thời gian \(K\)** hoặc số phiên bản \(N\) trong phạm vi sản phẩm, nhưng không được tự suy bounded staleness từ một metric lag quan sát trung bình.

Để kiểm chứng, cần biết:

- Replica selection/eligibility algorithm.
- Khoảng chênh lệch version/time được engine cho phép.
- Các điều kiện partition/failover/quorum.
- Các ngoại lệ khi unavailable hoặc deadline expired.

### 12.6. Quorum reads/writes không luôn đồng nghĩa latest read

Trong leaderless/quorum NoSQL, thường có mô hình giao nhau read/write quorums, nhưng còn phụ thuộc RF, timing, sloppy quorum, hinted handoff, concurrent writes, repair, conflict resolution, clock/timestamp semantics và API. Không lấy khẩu hiệu `R + W > N` làm chứng minh duy nhất cho linearizable latest read trong mọi lịch lỗi.

### 12.7. Một đường read có thể cố ý chọn replica gần

Read-preference/geo-routing thường chọn nearby replica để giảm latency. Đây là trade-off latency vs freshness/consistency đã được công bố. Cần đo **observedVersion và route**, không suy rằng response nhanh từ follower đồng nghĩa latest.

## 13. Replication lag trong các sự kiện bất thường

### 13.1. Replica failover

Leader thay thế có thể làm:

- Thay term/epoch/log generation.
- Rollback/discard một số writes không đạt durability/quorum contract.
- Cho reconfiguration/recovery và chọn read eligibility khác.
- Tăng lag trong giai đoạn bắt kịp.

Metric `leaderOffset - followerOffset` **không được tính qua hai epochs không so được**. Xác định các metrics và write ACK guarantees đúng failover semantics.

### 13.2. Network partition

Một follower tách mạng có thể ngừng receive/apply, lag tăng theo write traffic. Nếu ứng dụng vẫn route read tới nó, staleness tăng. Nhưng hệ có thể chủ động **không cho reads từ replica bị cách ly**, khiến người dùng thấy timeout/failover thay vì stale data.

Do đó phải theo dõi cả **staleness và availability/rejection**, không chỉ một metric lag.

### 13.3. Source writes bùng nổ

Write rate 100.000/s trong khi replica apply được 70.000/s:

\[
\Delta\mathrm{backlog}/s =
100\,000-70\,000=30\,000\text{ entries/s}
\]

Sau 60 giây, backlog lý thuyết tăng 1,8 triệu entries nếu các rates giữ nguyên và không có behavior khác. Thời gian catch-up khi source hết burst phải tính từ **apply rate còn dư**, không đơn giản lấy backlog chia total apply rate nếu source tiếp tục ghi.

### 13.4. Apply rate bị giới hạn bởi một partition

Replica có CPU tổng còn rảnh nhưng một partition/shard có transaction/compaction rất nặng, khiến lag của keys trên partition ấy cao. Lag trung bình toàn replica có thể che việc một nhóm khách hàng đọc stale.

### 13.5. Replica seed/initial sync

Replica mới phải snapshot/backfill data trước khi bắt kịp changes. Nó có thể có state `INITIAL_SYNC`, `RECOVERING` hoặc tương đương và **chưa eligible** đọc. Không đưa nó vào pool read traffic chỉ vì metric lag đang giảm nếu engine chưa công bố khả dụng.

### 13.6. Disk hoặc apply contention

Source ship stream bình thường nhưng replica đã received đầy đủ mà apply chậm vì compaction, fsync, GC hoặc indexing. Cần nhìn separate received/apply/durable positions khi engine có, thay vì chỉ đo network throughput.

### 13.7. Replication lag tăng sau backup/CDC/read scan

Một backup hoặc analytics query có thể dùng chung network/disk/cache với replication. Khi lag tăng, xem **resource overlap** và deployment timing; không vội kết luận replication daemon lỗi.

## 14. MongoDB: optime của replica set khác độ mới của query

MongoDB replica set có primary và secondaries, với tiến độ sao chép trong **oplog**. Các khái niệm như **last applied optime, last durable optime, majority commit point** và timestamps xuất hiện tùy server version, topology và cách lấy metrics.

### 14.1. Quan sát replica set

Trong môi trường MongoDB có quyền, shell có thể dùng:

~~~javascript
// Example for an authorized MongoDB shell session.
const s = rs.status();
printjson(s.members.map(m => ({
  name: m.name,
  stateStr: m.stateStr,
  optime: m.optime,
  optimeDurable: m.optimeDurable,
  optimeDate: m.optimeDate,
  optimeDurableDate: m.optimeDurableDate
})));
~~~

Các field và cách biểu diễn cụ thể **thay đổi theo MongoDB server/shell version**. Một số môi trường có `lastAppliedWallTime`, `lastDurableWallTime`, `optimes` hoặc metrics tương đương. Không xây production monitor dựa trên một field chưa kiểm tra version/schema.

### 14.2. `rs.printSecondaryReplicationInfo()` không đo read freshness end-to-end

Các helper của MongoDB có thể hiển thị độ trễ secondaries so với primary dưới dạng thời gian. Đây là tín hiệu tiến độ replica set; nó không trả lời:

- GET thực tế dùng read preference nào?
- GET có session/causal token không?
- Có cache ứng dụng hoặc query/search index không?
- Read concern có yêu cầu majority/linearizability không?
- Mốc write ACK dùng write concern gì?

### 14.3. Primary optime và secondary optime

Một cách nhìn đơn giản:

~~~text
Primary latest optime:   (Timestamp, term)
Secondary applied:       older position in same history
Secondary durable:       may differ from applied
~~~

**Không trừ timestamps của hai terms không tương thích** khi có rollback/election; dùng những methods/documented metrics của replica set để xác định progress hợp lệ.

### 14.4. `readPreference=secondary` không đồng nghĩa read-your-writes

Nếu driver chọn secondary, GET có thể trả Order v17 trong khi primary đã commit v18, nếu read contract cho phép. Dùng session/causal consistency hoặc đọc primary/stronger operation mode nếu workflow cần tính chất mạnh hơn, đồng thời đọc docs chính thức về read/write concerns.

### 14.5. `maxStalenessSeconds` là chính sách chọn server, không phải SLO của ứng dụng

MongoDB có tùy chọn chọn secondary dựa trên một ước lượng staleness trong những chế độ read preference được hỗ trợ. Ý nghĩa và độ phân giải phụ thuộc driver/topology. Không coi `maxStalenessSeconds=90` là bằng chứng “mọi GET chỉ cũ tối đa 90 giây so với mọi write” hoặc là read-your-writes guarantee.

### 14.6. `readConcern: majority` không tự là latest snapshot

Read concern majority gắn với mức dữ liệu đã majority committed trong phạm vi product contract. Nó không mặc nhiên tương đương **linearizable** hoặc “mọi read từ mọi secondary phải thấy write mới nhất” trong mọi lịch concurrent operations.

### 14.7. Causal consistency với Java driver

Một session dùng causal consistency có thể mang causal context giữa writes/reads; các guarantees cụ thể thường đòi hỏi tổ hợp read/write concern phù hợp. Cần đọc tài liệu của đúng MongoDB Java driver, session và deployment. Không dùng **một implicit session khác cho GET** rồi khẳng định kết quả phải có read-your-writes.

### 14.8. Tách MongoDB replica lag khỏi ứng dụng dùng cache

Một phép điều tra:

1. Tìm primary/secondary optimes qua metrics được hỗ trợ.
2. Đọc Order v18 trực tiếp từ primary theo read concern phù hợp.
3. Đọc cùng Order qua secondary đã được dùng bởi API.
4. Đọc qua Java repository (có cache).
5. Đọc qua public API.

Nếu secondary trả v18 nhưng public API trả v17, replication log lag **không phải nguyên nhân trực tiếp của kết quả lỗi**.

### 14.9. Replication catch-up sau failover

Kiểm tra server state/term/rollback và eligibility của secondaries. Một secondary từng ở trạng thái khỏe có thể trở thành recovering sau rollback/resync; phép đo “lag=0” với một field absent hoặc không cập nhật **không** cho phép tự route reads.

## 15. Redis: offset replication và độ mới từ replica

Redis replication thường có primary và replicas truyền replication stream/log; status có thể quan sát qua:

~~~text
INFO replication
~~~

Những field như `master_repl_offset`, `slave_repl_offset`/`replica` metadata, replication link status và replica acknowledgement offsets có thể được phơi ra theo version/role. Hãy đọc docs cụ thể cho version/Redis-compatible implementation đang dùng.

### 15.1. Replication offsets đo bytes/stream progress

Một primary có progress 2.000.000 và replica đã acknowledge tới 1.995.000 trong cùng replication stream:

\[
\mathrm{offsetGap}=5000
\]

Đây là **độ lệch về replication stream bytes/positions theo contract**, không phải 5.000 user operations, cũng không phải 5.000 ms.

### 15.2. Replica read có thể stale

~~~text
SET order:O900 "PAID" -> primary ACK
GET order:O900 -> replica before apply -> "CREATED"
~~~

Nếu API đọc từ replica, đây có thể là eventual behavior. Muốn read-your-writes cần chọn đúng read path, session/pinning hoặc protocol hỗ trợ trong thiết kế của mình.

### 15.3. `WAIT` không phải distributed transaction

Redis có cơ chế chờ một số replicas acknowledge replication progress khi dùng các API tương ứng. **Replica acknowledgement** không tự đồng nghĩa mọi replica đã fsync durable hoặc ứng dụng có linearizable read từ một replica bất kỳ. Phải đọc guarantee của `WAIT` và của persistence/failover trong phiên bản đó.

### 15.4. Phân biệt replication delay và eviction

Nếu key biến mất từ replica vì eviction/expiration/config, đó không nhất thiết là lag. Đọc `INFO memory`, eviction stats, key TTL/expiration và read routing. Không gọi “stale” khi key đã bị một mutation delete hợp lệ hoặc policy eviction mà source của bạn không coi là dữ liệu bền.

### 15.5. TTL và expiration

Expiration có những semantics cụ thể đối với primary/replica và replication. Một probe dùng key TTL ngắn có thể hết hạn giữa các reads khiến việc phát hiện version trở nên sai. Với freshness canary, dùng TTL đủ dài và thu delete/expire events riêng.

### 15.6. Redis Cluster

Nếu data phân tán theo hash slots, lag cần đo theo **từng primary/replica pair**, không chỉ một endpoint. Sau slot migration/failover, source stream identity/offset cần được đánh giá lại. Một replica khỏe của slot A không nói gì về slot B.

## 16. Cassandra/ScyllaDB: replica convergence không có một “seconds behind leader” toàn cục

Cassandra/ScyllaDB thường là distributed wide-column systems với **replica sets theo partition** và consistency levels; không dùng một primary oplog chung cho mọi writes theo cách MongoDB replica set.

Vì vậy câu hỏi “lag của secondary so với primary là bao nhiêu giây?” thường **không có metric trực tiếp tương đương**.

### 16.1. Consistency levels và visible values

Một write ở consistency `ONE` được ACK theo contract khi một replica đáp ứng yêu cầu. Các replicas khác có thể chưa nhận/áp mutation.

Một read `ONE` có thể chọn replica khác và nhìn phiên bản cũ. Với read/write quorums, mức an toàn phụ thuộc `RF`, CLs, concurrency, timestamps và repair/conflict semantics.

### 16.2. `R + W > RF` không phải chứng minh đầy đủ trong mọi hoàn cảnh

Mô hình quorum intersection là khung lý thuyết hữu ích, nhưng không tự bao trùm:

- Concurrent conflicting writes và timestamps.
- Sloppy quorum/hints theo engine/config.
- Replica failure/recovery.
- Read repair và anti-entropy.
- Clock skew và last-write-wins conflict rules.
- Trạng thái in-flight, timeouts, client retry.

Muốn linearizable semantics cần primitive/consistency contract cụ thể như LWT khi thích hợp; không chỉ đo “lag thấp”.

### 16.3. Hints và repair backlog

Hints hoặc repair có thể giúp một replica từng offline bắt kịp. Nhưng **hint count/repair progress không tự đo staleness của một key đang phục vụ reads**. Không có một formula chung đổi hints thành “lag giây”.

### 16.4. Read-repair không bảo đảm ngay cả cluster luôn mới nhất

Một read có thể phát hiện replicas bất đồng và repair theo cơ chế của engine/version. Nó không thay toàn bộ anti-entropy plan; per-key freshness cần **versioned source probe và read consistency đúng**.

### 16.5. `nodetool netstats` và streaming operations

Một số commands/metrics như `nodetool netstats` cho biết streaming data khi bootstrap/rebuild/repair. **Streaming progress** là một tín hiệu operational, không nhất thiết bằng freshness delay của các writes đang đến trên một partition.

### 16.6. Server timestamps và last-write-wins

Cassandra lưu cell timestamps theo contract của engine. Nếu clients tự cấp timestamps hoặc clocks lệch, write đến muộn có thể bị so bằng timestamp cũ/mới không phản ánh causal order mong muốn. Một phép đo versioned probe nên dùng **domain version/authority guard** có nghĩa chứ không chỉ `writetime()` như “last committed” toàn hệ.

### 16.7. Dùng sentinel để đo observed freshness

Trên partition/key thử nghiệm:

1. Ghi v18 với CL xác định.
2. Đợi ACK.
3. Đọc cùng key ở CL `ONE`, `LOCAL_QUORUM` hoặc mức nghiệp vụ quan tâm.
4. Ghi observedVersion, selected coordinator/region khi SDK cung cấp, timeout và latency.
5. Lặp nhiều token ranges, RF và failure scenarios.

Không dùng một sentinel key để hứa tất cả partitions có độ mới giống nhau.

### 16.8. LWT/CAS và mutation applied

Với một operation cần conditional semantics, đo **kết quả CAS thành công và version thắng** thay vì chỉ biết replica trả lời. Một CAS conflict là business/consistency outcome, không giống replication lag.

## 17. DynamoDB: Global Tables replication và đọc trong/ngoài Region

DynamoDB là managed NoSQL service với semantics khác so với self-managed leader–follower. Trong một Region, mức đọc của API phụ thuộc read consistency option và resource type. Khi dùng **Global Tables**, dữ liệu được sao chép giữa các Regions theo chế độ/configuration được hỗ trợ.

### 17.1. Global Tables replication delay

AWS CloudWatch có thể cung cấp một metric có tên như **`ReplicationLatency`** cho Global Tables/đường replication trong các mode được hỗ trợ. Phải xác nhận:

- Metric tồn tại trong table mode/topology đang dùng.
- Nó đo đến region nào và theo dimension nào.
- Thước đo là average/sample/max/percentiles nào.
- Phạm vi, period, semantics của sample và điều kiện khi không có writes.

Không dùng một số CloudWatch trung bình để suy mọi item trong mọi Region đều latest.

### 17.2. Strongly consistent reads có scope

DynamoDB có strongly consistent read options cho một số operations/resources trong Region theo API contract. Điều đó **không tự là strongly consistent cross-region read** cho mọi Global Table mode.

Các tính năng multi-region strong consistency khác nhau có thể có assumptions/constraints riêng; cần kiểm tra **mode và phiên bản dịch vụ hiện hành**, không mang guarantee của một mode áp cho mode khác.

### 17.3. GSI lag và Global Table lag là hai đường khác nhau

Một query qua **Global Secondary Index (GSI)** có thể nhìn dữ liệu trễ so với base table ngay trong Region vì index update và consistency semantics. Một read qua Global Table ở Region khác lại chịu replication cross-region. **Đây không phải cùng một metric hay cùng một bottleneck.**

### 17.4. Global Tables và concurrent writers

Nếu nhiều Regions cùng ghi một item, kết quả quan sát được có thể phụ thuộc conflict resolution của mode. Hai writes concurrent có thể có winner/merge khác expectation. Một đọc trả status khác không phải luôn do replication chậm; có thể đã có **conflicting committed write**.

### 17.5. DynamoDB Streams và event processing

DynamoDB Streams cho event-driven integration. Chỉ số consumer stream lag đo tiến độ **đọc/process change records**, không phải độ mới của base-table read hoặc cross-region Global Table replication.

### 17.6. TTL và read staleness

TTL deletion diễn ra theo semantics nền; item vượt thời điểm TTL có thể chưa bị xóa ngay. Nếu user yêu cầu “không trả record đã hết hạn tại thời điểm t”, API có thể cần **filter theo business expiration field** thay vì trông chờ physical TTL deletion. Đây là freshness theo nghiệp vụ, không đơn thuần replica lag.

### 17.7. Bảng phân biệt cho một app DynamoDB

| Người dùng thấy | Kiểm tra |
| --- | --- |
| GET base item trong same Region có giá trị cũ | Read consistency, write outcome, request routing, cache |
| Query GSI trả giá trị cũ | GSI eventual indexing, key/query, projection |
| GET ở Region B khác Region A | Global Table replication/mode/region conflict |
| Stream consumer chưa thấy write | Stream enablement/shard progress/retention |
| App trả bản cũ dù base read đã mới | SDK/app cache, read model |

## 18. Elasticsearch/OpenSearch: replication progress khác search visibility

Một search engine có replicas và indexing pipeline. Nó có thể nhận/index write nhưng **search query chưa thấy document mới** do refresh semantics, ngay cả khi replica recovery/replication metrics khỏe.

### 18.1. Indexing ACK, refresh và query

~~~text
Index document v18 acknowledged
  -> Lucene/index buffers
  -> refresh makes searchable
  -> query sees v18
~~~

Một HTTP GET by ID có thể có realtime behavior khác một search query; phụ thuộc engine và API.

### 18.2. Sequence numbers/checkpoints

Một số engines cung cấp `seq_no`, local/global checkpoints và shard replication/recovery metrics. Chúng có ý nghĩa cho **replication/progress trong shard** theo contract của sản phẩm. Không coi `global checkpoint == local checkpoint` là chứng minh search query mới nếu refresh chưa xảy ra.

### 18.3. Refresh interval

Refresh interval ảnh hưởng trade-off giữa indexing/search visibility và background work. Không đổi interval xuống cực thấp để “cải thiện freshness” mà không đo indexing throughput, merge overhead, CPU và memory.

### 18.4. `refresh=wait_for` và API contract

Trong một số search APIs, write request có thể chọn mode chờ refresh phù hợp để xác nhận search visibility của write theo scope. Nó có chi phí latency và concurrency; không tự đồng nghĩa cross-region replication hoặc external cache đã cập nhật.

### 18.5. Cross-cluster replication

Độ trễ sao chép giữa leader/follower indexes ở các clusters (nếu sử dụng CCR tương ứng) là một tầng khác. Hãy tách:

- Source index write.
- Replication/CCR fetch/apply.
- Target index refresh.
- Application search result cache.

### 18.6. Query routing và stale pages

Một search service có thể cache kết quả/query hoặc client giữ pagination/search-after context. Dù index mới refresh, request vẫn có thể trả snapshot từ một point-in-time search context cũ. Đây là **semantics của read context**, không nhất thiết replica replication lag.

## 19. CDC/read-model lag: nhiều hàng đợi ghép nối

Một kiến trúc khác:

~~~mermaid
flowchart LR
    DB["Source NoSQL commit"] --> LOG["Change stream / CDC"]
    LOG --> BROKER["Broker topic"]
    BROKER --> C["Consumer"]
    C --> TARGET["Read model"]
    TARGET --> CACHE["API cache"]
    CACHE --> USER["Client read"]
~~~

Ta có ít nhất bốn progress signals:

1. **Source replica lag:** Storage replicas của source tiến tới commit point.
2. **CDC cursor lag:** Connector đọc source changes tới đâu.
3. **Broker consumer lag:** Consumer đọc/commit offsets tới đâu.
4. **Target apply/visible lag:** State ở target đã durable và query-visible đến đâu.

### 19.1. Consumer committed offset có thể cao hơn target applied state

Nếu connector commit broker offset **trước khi target apply**, nó có thể bỏ qua event sau crash. Lag metric broker có thể bằng 0 trong khi target thiếu records. Phải phân biệt **read/received/committed offsets và last durable apply**.

### 19.2. Consumer lag=0 không có nghĩa data fresh

Một pipeline có thể không nhận được source event do CDC gap/connector outage nhưng broker consumer vẫn caught up với **những events đã tới broker**. Vì vậy cần end-to-end marker/sequence và reconciliation, không chỉ broker offset difference.

### 19.3. Time since last event khác replication lag

Nếu Order service không có writes trong một giờ, consumer last processed timestamp cách một giờ không phải sai. Cần source progress/heartbeats/monitoring canaries tương ứng.

### 19.4. Checkpoint sau target apply

Trong mô hình at-least-once:

~~~text
Read E18
  -> apply E18 idempotently to target
  -> verify durable success
  -> checkpoint/ack E18
~~~

Nếu checkpoint trước apply, lag metric có thể đẹp nhưng dữ liệu target sai. Nếu apply trước checkpoint, replay duplicates có thể xảy ra; target cần idempotency/version guard.

### 19.5. Tombstones và deletes

Một target có thể giữ bản ghi cũ vì delete event không đến, đã hết retention, hoặc bị xử lý sai. Đây là **độ mới của state/existence**, không thể đo bằng `updatedAt` của record đã xóa vì nó **không còn tồn tại ở source**.

### 19.6. Độ mới của join/materialized projection

Nếu view ghép `Order` và `Payment`, mỗi nguồn có watermark riêng. Một view có thể chứa Order v18 nhưng Payment v5 cũ. Cần **vector of source positions/watermarks hoặc transaction coordination** theo consistency mong muốn, không một scalar lag vô nghĩa.

## 20. Java: xây phép đo `write ACK → read visible` có version

Để kiểm chứng read path, ta có thể tạo một **abstraction về write/read** và đo bằng một clock monotonic trong **cùng JVM**.

Thiết kế cần phân biệt:

- **Write ACK** trả về version/identity của mutation đã chấp nhận.
- **Read** trả version/identity thực sự quan sát trên đường đọc kiểm tra.
- **Probe result** chứa thời gian chờ visibility và số attempts/errors.
- **Observation timeout** khác “đã đo được lag bằng đúng timeout”.

### 20.1. Interface cho source và read path

~~~java
public record ProbeValue(
    String generation,
    long version,
    String payloadHash
) {}

public interface VersionedProbeStore {
    // Contract: returns only when the configured write ACK condition is met.
    ProbeValue writeAndAwaitAck(String key, String generation);

    // Contract: reads through the exact path selected for measurement.
    // This may be a replica, region, cache, search or public API.
    ProbeValue read(String key);
}
~~~

Implementation cụ thể phải sử dụng đúng SDK/API của NoSQL đang đo. Không phải tất cả engines tự trả `long version`: có thể application phải duy trì một field tăng có kiểm soát theo entity/key hoặc source-generated causal token.

### 20.2. DTO kết quả

~~~java
public record ProbeObservation(
    String probeKey,
    String targetRoute,
    long expectedVersion,
    long observedVersion,
    boolean visible,
    boolean timedOut,
    long elapsedNanosFromAck,
    int readAttempts,
    int readFailures
) {}
~~~

`timedOut` giúp phân biệt **censored sample** với một sample thành công bằng deadline. `readFailures` hỗ trợ đánh giá availability.

### 20.3. Java implementation minh họa

~~~java
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

public final class VisibilityProbe {
    private final VersionedProbeStore store;
    private final String route;

    public VisibilityProbe(VersionedProbeStore store, String route) {
        this.store = Objects.requireNonNull(store);
        this.route = Objects.requireNonNull(route);
    }

    public ProbeObservation run(
        String probeKey,
        String generation,
        Duration maxObserveTime,
        Duration pollInterval
    ) throws InterruptedException {
        if (maxObserveTime.isNegative() || pollInterval.isZero()
                || pollInterval.isNegative()) {
            throw new IllegalArgumentException("invalid durations");
        }

        // Write method must have a well-documented ACK contract.
        ProbeValue expected =
            store.writeAndAwaitAck(probeKey, generation);

        // Start timer immediately after successful write ACK.
        long startNanos = System.nanoTime();
        long budgetNanos = maxObserveTime.toNanos();
        long pollNanos = pollInterval.toNanos();
        int attempts = 0;
        int failures = 0;
        long observedVersion = -1L;

        while (true) {
            long elapsed = System.nanoTime() - startNanos;
            if (elapsed >= budgetNanos) {
                return new ProbeObservation(
                    probeKey, route, expected.version(),
                    observedVersion, false, true,
                    Math.max(0L, elapsed), attempts, failures
                );
            }

            attempts++;
            try {
                ProbeValue observed = store.read(probeKey);
                if (observed != null) {
                    observedVersion = observed.version();
                    boolean sameGeneration =
                        expected.generation().equals(
                            observed.generation()
                        );
                    boolean caughtUp =
                        sameGeneration
                        && observed.version() >= expected.version();

                    if (caughtUp) {
                        return new ProbeObservation(
                            probeKey, route, expected.version(),
                            observedVersion, true, false,
                            System.nanoTime() - startNanos,
                            attempts, failures
                        );
                    }
                }
            } catch (RuntimeException readError) {
                // Record a metric with the error class, then retry under
                // a bounded policy. Production code needs classification:
                // not every error should be retried.
                failures++;
            }

            long remaining =
                budgetNanos - (System.nanoTime() - startNanos);
            if (remaining <= 0L) {
                continue;
            }
            long sleepNanos = Math.min(pollNanos, remaining);
            TimeUnit.NANOSECONDS.sleep(sleepNanos);
        }
    }
}
~~~

### 20.4. Phạm vi của ví dụ

Mã minh họa **không phải module production hoàn chỉnh**, vì:

- `writeAndAwaitAck` phải xác định nguồn version và tính duy nhất của mutation.
- Một error ở write có thể là **unknown outcome**, không được coi chắc chắn thất bại.
- `read()` có thể block lâu hơn remaining deadline nếu SDK không có per-attempt timeout.
- Một `RuntimeException` có thể là auth/validation error không nên retry.
- `Duration.toNanos()` có thể overflow với giá trị cực lớn.
- Cần jitter/backoff, cancellation, shutdown, metrics, request tracing.
- `>= expectedVersion` chỉ đúng nếu generation/version thực sự có **per-key monotonic semantics**.
- Nếu cùng version nhưng payload khác do bug/conflict, phải nhận diện integrity error bằng payload hash.

### 20.5. Vì sao không dùng `Instant.now()` để đo 200 ms?

`System.nanoTime()` đo elapsed time trong một process, ít nhạy với điều chỉnh wall clock. Không gửi số `nanoTime()` qua HTTP cho replica rồi lấy `replica.nanoTime - client.nanoTime`, vì monotonic origins của hai processes không chia sẻ.

### 20.6. Vì sao `>= expected` có thể hữu ích?

Giả sử probe ghi v18, nhưng trước lúc read, một writer hợp lệ ghi v19. Read thấy v19 theo cùng generation/authority có thể chứng minh đường đọc đã tiến ít nhất qua v18 nếu history tuyến tính và v19 bao gồm effect cần xác minh. Nếu v19 overwrite/đảo nghiệp vụ, **thấy version cao hơn chưa chắc thấy chính payload của write v18**; khi đo business effect, phải kiểm tra invariant/payload hoặc history phù hợp.

### 20.7. Không tạo thí nghiệm gây write conflict

Không dùng chính Order đang được người dùng cập nhật làm probe vô điều kiện. Dùng key synthetic riêng, không chứa thông tin cá nhân và **không tham gia workflow có side effects**. Với một hệ phân vùng theo tenant, nên phân bổ keys có kiểm soát theo nhiều partitions thay vì chỉ hot một key.

## 21. Java: instrument read-your-writes tại API boundary

Probe tổng hợp là tốt để đo chủ động, nhưng có thể cần giám sát **những request thật có expected version**.

### 21.1. Một hợp đồng HTTP minh họa

~~~text
PUT /orders/O900
Request:
  expectedVersion = 17
  status = PAID

Response 200:
  orderId = O900
  generation = 1
  version = 18

GET /orders/O900
Headers:
  X-Min-Order-Generation: 1
  X-Min-Order-Version: 18
~~~

Các headers là **ví dụ thiết kế ứng dụng**, không phải HTTP standard. Nếu user/session yêu cầu read-your-writes, backend phải:

1. Truyền expected generation/version.
2. Đọc từ path có thể đáp ứng contract hoặc chờ/fallback.
3. Không trả v17 dưới dạng success khẳng định mới nếu contract yêu cầu ≥v18.
4. Nếu không thể đáp ứng trong deadline, trả trạng thái retryable/degraded được định nghĩa rõ.

### 21.2. Java helper kiểm tra observed version

~~~java
public final class ReadFreshness {
    public enum Result {
        SATISFIED,
        STALE,
        UNCOMPARABLE,
        MISSING
    }

    public static Result compare(
        ProbeValue expected,
        ProbeValue actual
    ) {
        if (actual == null) {
            return Result.MISSING;
        }
        if (!expected.generation().equals(actual.generation())) {
            return Result.UNCOMPARABLE;
        }
        return actual.version() >= expected.version()
            ? Result.SATISFIED
            : Result.STALE;
    }
}
~~~

Ở đây `UNCOMPARABLE` yêu cầu domain policy (key recreated, source epoch changed, multi-writer conflict), không tự xếp vào `fresh` hay `stale`. `MISSING` cần phân biệt bản ghi chưa tạo, bị delete hợp lệ, cache miss và read error.

### 21.3. Expected version phải từ nguồn đáng tin

Không chấp nhận bất kỳ version do client bịa ra để làm backend chờ vô hạn hoặc vượt quota. Session token/expected version có thể cần integrity, scope, TTL, authorization, tenant isolation và max wait budget.

### 21.4. Stronger reads có chi phí

Một GET đòi ≥v18 có thể cần đọc leader hoặc quorum thay vì replica gần; điều đó có thể tăng network RTT, CPU và availability trade-offs. Nếu API có cả eventual dashboard và critical checkout, nên chọn **consistency theo operation** thay vì bật strongest read toàn hệ mà không đo.

### 21.5. `write ACK` cần gắn outcome identity

Nếu client timeout sau write request, có thể chưa biết source đã commit hay không. Trong trường hợp đó chưa thể xác nhận expected version mới từ ACK. Cần **idempotency key/operation lookup** trước khi khẳng định read đang stale.

## 22. Thu histograms và xử lý các mẫu không nhìn thấy

### 22.1. Censored observations

Nếu probe deadline 2 giây mà không thấy v18:

~~~text
expectedVersion = 18
lastObservedVersion = 17
elapsed = 2,000 ms
visible = false
timedOut = true
~~~

Không ghi đây là một phép đo thành công **lag = đúng 2.000 ms**. Thực tế visibility delay lớn hơn 2 giây **hoặc hệ không phục vụ read đủ để quan sát**, tức đây là **right-censored/unknown** sample theo mục tiêu đo.

### 22.2. Không bỏ failed samples khỏi percentile

Nếu 90 probes thành công dưới 100 ms và 10 probes timeout sau 5 giây, p99 của chỉ 90 successful probes trông đẹp nhưng không mô tả user experience. Báo ít nhất:

- Completion/visibility rate trong SLO deadline.
- Timeout/non-visible count.
- Successful visibility latency percentiles.
- Read error rate.
- Number of read attempts và polling interval.

Nếu cần một percentile đúng có xét censoring, có thể dùng survival-analysis hoặc báo percentile bounds theo phương pháp thống kê được xác định, không tự thay timeout thành số đo exact.

### 22.3. p99 cần đủ samples

Với 100 samples, p99 chịu ảnh hưởng rất lớn của một observation. Cần số lượng đủ, chia theo region/shard, không chỉ mean, và ghi confidence/variability khi so hai bản deploy.

### 22.4. Không gộp p99 bằng cách tính trung bình p99 các pods

Percentiles **không có tính cộng tuyến**. Một pod có 100 requests và pod khác 100.000 requests; trung bình hai p99 không phải p99 toàn hệ. Dùng histogram có thể aggregate đúng theo count hoặc data points gốc theo cách công cụ hỗ trợ.

### 22.5. Polling overhead có thể làm metrics sai

Nếu cứ 1 ms lại read cùng key ở 100 probes, bạn có thể tạo tải giả làm source hoặc replica chậm, rồi đo chính sự chậm đó. Cần frequency, concurrency và per-tenant quotas có giới hạn; poll interval, sampled routes và overhead phải được công bố.

### 22.6. Đo write-to-first-visible và write-to-stable-visible

Một read thấy v18, sau đó read route khác lại thấy v17. `firstVisibleTime=50ms` có vẻ tốt nhưng **monotonic read chưa được bảo đảm**. Có thể đo thêm:

- First observed at least version v18.
- Fraction of subsequent reads that regress.
- Time until **all eligible routes** hoặc một tỷ lệ routes đáp ứng minVersion.
- Max staleness observed per route.

“Tất cả replicas” có thể khó kiểm chứng nếu cluster/partitions đổi trong lúc đo; phải định nghĩa danh sách eligible/read pools.

### 22.7. Read sampling có thiên lệch

Nếu chỉ gửi probes tới replica nhanh nhất vì load balancer ưu tiên nó, bạn có thể không phát hiện một follower lag nhưng vẫn thỉnh thoảng phục vụ traffic. Muốn đo theo user exposure, cần record actual route hoặc sampling theo route weights, ngoài các probes nhắm thẳng từng replica.

## 23. Tách commit→apply và ACK→visible trên cùng một chart

Dashboard lý tưởng có:

~~~text
Panel 1: Leader/replica progress (per shard/node)
Panel 2: Received vs applied vs durable backlog (if exposed)
Panel 3: Synthetic ack-to-visible per read route
Panel 4: Real session read-your-writes violations
Panel 5: Search/CDC/consumer lag
Panel 6: Read errors/timeouts and traffic routing
Panel 7: Network/CPU/disk/compaction/GC health
~~~

### 23.1. Ví dụ diễn giải đúng

| Replica apply lag | ACK→API visible | Điều cần kiểm tra |
| --- | --- | --- |
| 30 ms | 20 ms | API có thể đọc primary, không có vấn đề rõ ở route này |
| 30 ms | 5 s | Cache/search/route khác hoặc probe sai |
| 4 s | 30 ms | API đọc leader hoặc follower khác; lag replica vẫn là risk |
| 4 s | 5 s | Replica lag có thể là contributor; cần route/version evidence |
| Không đo được | 100 ms | User experience có thể tốt nhưng chưa biết replica health |
| 0 entries | Không thấy version | Không có writes, read cache, wrong key/region hoặc offset metric sai |

### 23.2. Đọc cùng một mốc nguồn mới hợp lệ

Nếu Panel 1 đo leader source shard A, Panel 3 đo API route vào region B hoặc cache index C, không được suy causal link trước khi hiểu data flow. Trace phải gắn:

~~~text
source identity
source region / shard / epoch
read region / replica
target index/cache identity
version / event identity
consistency mode
timestamp sample window
~~~

### 23.3. Percentiles theo user route

Một route ít người dùng nhưng lag 10 giây có thể quan trọng với premium tenant hoặc payment flow. Aggregate weighted p99 nên đi kèm **per-region/per-route max và error budgets**.

## 24. Read-your-writes và sticky routing: lợi ích và giới hạn

Một chiến lược thực dụng là giữ reads của client tại leader/region vừa chấp nhận write trong một khoảng, hoặc gửi **session version token** để reads không regress.

### 24.1. Sticky route không phải proof of correctness

Nếu leader vừa failover, session state đổi, hoặc application cache vẫn giữ v17, sticky routing có thể chưa đủ. Phải kiểm tra đúng source state và session/consistency contract.

### 24.2. Read repair/fallback

Nếu GET từ replica trả `version < minVersion`, application có thể:

1. Chờ ngắn để replica catch up.
2. Fallback sang leader/strong read.
3. Trả `still synchronizing` nếu không thể đáp ứng deadline.

Các bước phải có **bounded wait, rate limit và retry budget**. Nếu mọi stale GET fallback về leader giữa một outage, leader có thể bị quá tải; cần admission và capacity planning.

### 24.3. Cache invalidation theo version

Một cache entry có thể lưu:

~~~json
{
  "key": "tenant-a/O900",
  "generation": 1,
  "version": 17,
  "value": {"status": "CREATED"},
  "cachedAt": "2026-11-14T09:00:00Z"
}
~~~

Khi request mang `minVersion=18`, cache **không được coi v17 là đủ**. Có thể bypass hoặc fetch lại nguồn có stronger policy. Một notification invalidation đến sai thứ tự cũng phải có version guard để không làm cache áp bản cũ.

### 24.4. TTL là fallback, không thay invariants

TTL ngắn giảm khoảng giữ stale cache theo một số workload, nhưng tăng load và không bảo đảm read-your-writes ngay sau write ACK. Một key TTL 10 giây có thể được làm mới sai phiên bản hoặc stale-while-revalidate còn dài hơn.

### 24.5. Cache stampede

Nếu invalidation làm 100.000 requests cùng cache miss và đọc leader, hệ có thể tạo thảm họa. Version-aware cache cần thêm **single-flight/coalescing, admission và bounded fallback** theo domain SLO.

### 24.6. Multi-level caches

Một request có thể đi qua:

~~~text
browser/service worker
  -> CDN/edge cache
  -> API response cache
  -> local Java cache
  -> distributed Redis cache
  -> DB replica
~~~

Nếu nguồn DB đã mới, cần tìm **cache đầu tiên trả stale**. Không tăng database replication bandwidth để sửa browser cache đang giữ response cũ.

## 25. Quản lý clocks khi đo lag bằng thời gian

### 25.1. Có ba clock families

1. **Wall clock** như Unix timestamp: Có thể lệch, nhảy khi NTP điều chỉnh; dùng cho log/audit với uncertainty.
2. **Monotonic elapsed clock** như `System.nanoTime()`: Dùng đo durations trong một process; origins không chung giữa hosts.
3. **Logical/source clocks** như log positions, terms, vector clocks, aggregate versions: Có ordering semantics trong scope công bố; không tự chuyển thành giây.

### 25.2. `updatedAt` do client cấp không phải commit timestamp

Client A đồng hồ nhanh 2 phút có thể ghi `updatedAt` tương lai. Nếu đo `now−updatedAt`, kết quả có thể âm; nếu client B đồng hồ chậm, record trông quá cũ. Một `updatedAt` không atomic với business write còn có thể sai phiên bản.

### 25.3. Source timestamp cũng cần hiểu granularity

Ngay cả server-assigned commit timestamp, granularity có thể là milliseconds/seconds hoặc một logical timestamp không hoàn toàn là wall clock. Không tự lấy hai `Timestamp` theo format giống nhau rồi coi có thể trừ nếu chúng thuộc partitions/epochs khác nhau.

### 25.4. So progress thay vì dựa clocks khi có thể

Nếu leader và follower cung cấp offset hợp lệ trong cùng log, vị trí nào đi sau vị trí nào thường chắc hơn so với chênh lệch wall clocks. Tuy nhiên offset lag không nói **bao nhiêu giây stale**; cần throughput/visibility probes để đo delay.

### 25.5. Khi bắt buộc dùng cross-host timestamps

Lưu:

~~~text
sourceTimestamp
sourceClockDomain
collectorTimestamp
collectorClockOffsetEstimate
clockUncertainty
sampleTime
~~~

Nếu uncertainty 30 ms mà báo lag 5 ms, phép đo không đủ phân giải để khẳng định 5 ms. Gắn uncertainty vào SLO hoặc dùng monotonic end-to-end probe.

### 25.6. Heartbeat measurement

Một heartbeat được **ghi/commit qua cùng ordered replication channel** có thể giúp ước lượng delay khi không có business writes. Nhưng:

- Heartbeat nhận được ở tầng transport không chứng minh query-visible nếu apply path khác.
- Một heartbeat ở shard A không nói shard B caught up.
- Heartbeat interval và scheduling tạo measurement resolution.
- Nếu heartbeat dùng cache/route riêng, nó không đại diện user read path.

## 26. Backpressure và tải: lag có thể tự khuếch đại

Nếu nguồn ghi 10.000 mutations/s, replica apply được 8.000/s:

\[
\Delta B=10\,000-8\,000=2\,000\text{ entries/s}
\]

Sau 15 phút, backlog lý tưởng:

\[
2\,000\times900=1\,800\,000\text{ entries}
\]

Giả sử sau đó nguồn giảm xuống 6.000/s, replica vẫn apply 8.000/s, **capacity còn lại để catch up** là 2.000 entries/s:

\[
T_{\mathrm{catchup}}
=\frac{1\,800\,000}{8\,000-6\,000}
=900\text{ s}=15\text{ phút}
\]

Đây là mô hình hàng đợi đơn giản, giả định entry cost đồng đều, backlog không đổi do TTL/compaction và apply capacity ổn định. Trong thực tế, network, compaction, per-partition ordering và large transactions có thể khiến catch-up chậm hơn.

### 26.1. Throttle writes hay scale replicas?

Một số giải pháp:

- Giảm batch writes/bulk imports trong lúc follower catch up.
- Tăng apply capacity nếu bottleneck CPU/disk.
- Giảm index/write amplification.
- Tối ưu hot partition distribution.
- Tách workloads analytics/cache/search.
- Điều chỉnh traffic đọc để không ép replica đang chậm.

Không chỉ tăng `replication network threads` nếu receive đã bắt kịp mà apply queue mới là nút thắt.

### 26.2. Retry read có thể làm xấu thêm lag

Nếu mọi GET stale đều retry ngay 10 lần, replica đang yếu phải trả thêm 10 requests, có thể làm apply cạnh tranh CPU/disk với read traffic. Dùng bounded retry/fallback, session eligibility và backoff.

### 26.3. Replica lag và failover RPO

Replication lag đo tiến độ không tự chuyển thành **số acknowledged writes có nguy cơ mất** khi failover. RPO/durability phụ thuộc quorum ACK, commit point, promotion policy và failure scenarios. Nếu ACK xảy ra trước durable replication, rủi ro khác với majority/quorum durable ACK.

### 26.4. Replica lag và availability

Nếu quá nhiều replicas bị đánh dấu không eligible cho reads vì stale, traffic dồn sang ít replicas còn lại; read latency/errors có thể tăng dù hệ chọn giữ freshness. Đây là trade-off giữa **consistency, availability và latency** cần được quan sát, không ép mọi chỉ số cùng về 0.

## 27. Dashboard quan sát replication và freshness

Một dashboard hữu ích nên tách **source–replica health** và **end-user read behavior**.

### 27.1. Lớp nguồn

| Metric khái niệm | Phạm vi | Mục đích |
| --- | --- | --- |
| `source_committed_position` | Source/shard/epoch | Tiến độ authority |
| `replica_received_position` | Replica/shard/epoch | Đã nhận records tới đâu |
| `replica_durable_position` | Replica/shard/epoch | Đã bền tới đâu nếu product cung cấp |
| `replica_applied_position` | Replica/shard/epoch | Đã apply tới đâu |
| `replica_apply_backlog_entries` | Replica/shard | Số entries chờ |
| `replica_receive_backlog_bytes` | Replica/shard | Network/log shipping backlog |
| `replica_apply_rate` | Replica/shard | Năng lực apply |
| `replica_recovery_state` | Replica/node | Healthy, recovering, resync... |
| `replication_transport_errors_total` | Replica/source path | Network/auth/stream errors |
| `replication_term_changes_total` | Source/partition | Elections/epoch changes |

Tên metric là **mô hình để thiết kế dashboard**, không nhất thiết có y nguyên ở mọi NoSQL vendor. Phải map sang tên và semantics đúng sản phẩm.

### 27.2. Lớp read route

| Metric | Mục tiêu |
| --- | --- |
| `read_requests_total` | Request volume theo route/consistency |
| `read_versions_observed` | Phân phối version/generation nếu có expected context |
| `read_your_writes_violations_total` | Session reads không đạt expected version |
| `read_regressions_total` | Client đọc sau thấy version thấp hơn lần trước |
| `read_freshness_probe_attempts_total` | Probe attempts |
| `read_freshness_probe_visible_total` | Probe success trong deadline |
| `read_freshness_probe_timeout_total` | Không visible trước deadline |
| `read_freshness_probe_duration_seconds` | Histogram ACK→visible khi hoàn tất |
| `read_freshness_probe_read_errors_total` | Lỗi trong poll |
| `read_freshness_stale_by_route_total` | Stale theo primary/follower/region/cache |
| `read_route_fallback_total` | Số read fallback sang stronger source |
| `read_route_ineligible_replicas` | Replicas bị loại theo health/staleness |

Không dùng số version cụ thể hoặc Order ID làm time-series metric labels nếu cardinality cao.

### 27.3. Lớp cache/search/CDC

| Metric | Vì sao cần |
| --- | --- |
| `cache_stale_reads_total` | Cache trả version thấp hơn minVersion |
| `cache_invalidation_lag` | Từ mutation/invalidate signal đến cache update |
| `cdc_source_read_position` | CDC đọc nguồn tới đâu |
| `cdc_target_applied_position` | Đã apply bền tới đâu |
| `broker_consumer_lag` | Consumer sau broker đến đâu |
| `search_index_visible_lag` | Query search thấy mutation khi nào |
| `target_version_regressions_total` | Target apply bản cũ |
| `target_tombstone_resurrections_total` | Delete bị hồi sinh |

### 27.4. Lớp tài nguyên

- Leader/follower CPU per core và cgroup throttling.
- Network RTT, retransmission, bandwidth/egress.
- Disk read/write latency, WAL/fsync, IOPS, compaction.
- JVM heap/GC nếu engine hoặc service Java.
- Hot shard/partition write distribution.
- Read traffic lên lagging replicas.
- Snapshot/backup/repair/rebalance jobs đang chạy.

Nếu lag tăng nhưng không đo CPU/network/disk, rất khó phân biệt **chậm receive** và **chậm apply**.

## 28. Một bảng điều tra qua nhiều lớp

Giả sử Order v18 commit, người dùng đọc v17 trong 2 giây:

| Tầng | Bằng chứng có thể đo | Giải thích nếu mới/cũ |
| --- | --- | --- |
| Primary/source | Direct authoritative read v18 | Write đã có ở authority |
| Follower A | Direct read v18 | A không phải lý do của stale result này |
| Follower B | Direct read v17 | B vẫn thiếu hoặc chưa query-visible |
| CDC cursor | Processed source E18 | CDC đã đọc event |
| Read model target | Stored v18 | Target storage có bản mới |
| Search query | Returns v17 | Có thể refresh/query cache/route |
| API cache | Entry version 17 | API đang phục vụ cache cũ |
| Public API | Returns v17 | Client thực sự thấy stale |

**Không đo đồng thời các tầng mà bỏ qua concurrent writes**: một bản ghi có thể đổi v19 trong lúc điều tra. Cần trace/version/causal context để xác định giá trị cũ và nguồn dữ liệu, không chỉ timestamp của lần query.

### 28.1. Dấu hiệu replication thật

~~~text
Primary v18
Follower direct read v17
Follower applied position behind commit of v18
Read API routed to that follower
~~~

Đây là chuỗi bằng chứng mạnh hơn chỉ một metric lag. Cần kiểm tra read policy cho phép stale hay đang vi phạm SLO.

### 28.2. Dấu hiệu stale cache

~~~text
Primary v18
Follower direct read v18
API cache entry v17
Public API returns v17
~~~

Lúc này tăng bandwidth replication không xử lý cache; điều tra invalidation/TTL/refresh/data version.

### 28.3. Dấu hiệu search refresh delay

~~~text
Source v18
CDC delivered E18
Target write ACK v18
Search query still returns v17
Search refresh later exposes v18
~~~

Đây là indexing/search visibility delay, không phải source replica lag.

### 28.4. Dấu hiệu không có enough evidence

~~~text
GET returns old looking timestamp
No expected version, no source commit ID,
no read route, no consistency mode.
~~~

Không thể kết luận là stale read chỉ từ `updatedAt` cũ. Trước hết bổ sung provenance/version telemetry.

## 29. Runbook điều tra: người dùng vừa ghi nhưng đọc thấy bản cũ

### Bước 1 — Xác minh write outcome

Thu:

~~~text
logicalOperationId
write request start/end
write ACK status
source cluster/region
write concern/consistency
committed aggregate version
transaction/commit position nếu có
~~~

Nếu write timeout không rõ commit, phải **tra source/idempotency ledger**. Không bắt đầu bằng “replica lag” khi chưa biết write đã commit hay chưa.

### Bước 2 — Xác định read contract

GET là eventual, causal, bounded stale hay linearizable? Có session token hoặc minVersion không? Nếu eventual, đọc bản cũ có thể hợp lệ trong một khoảng nhưng vẫn có thể vi phạm **business freshness SLO**.

### Bước 3 — Xác định đường đọc thật

Trace:

~~~text
client -> CDN? -> API cache? -> repository?
    -> primary or follower?
    -> which region/shard?
    -> search/read model?
~~~

Không so follower metrics ở region A nếu request thật đi tới region B.

### Bước 4 — Đối chiếu version từng tầng

Đọc source authority, targeted replica, cache/index và API theo một expected version; ghi các timestamps và requests cùng trace/correlation.

### Bước 5 — Đo backlog tiến độ

- Leader/source commit position.
- Follower receive/durable/applied positions.
- CDC/broker/target positions.
- Stream epoch/term và replica state.
- Scan/repair/compaction/backfill workload.

### Bước 6 — Tìm resource saturation

- Network loss/RTT/egress limit giữa source–replica?
- Replica apply CPU/GC/fsync?
- Hot partition?
- Replica initial sync/reshard?
- Target search refresh?
- Cache invalidation backlog?

### Bước 7 — Giảm ảnh hưởng có kiểm soát

- Loại lagging follower khỏi **read-eligible pool** nếu policy cho phép.
- Fallback stronger read cho critical endpoints có bounded deadline.
- Throttle background scans/bulk writes làm tắc apply.
- Giảm retry storm.
- Sửa cache invalidation hoặc version-aware read.
- Scale tài nguyên nếu bottleneck và contract cho phép.

Không tự hạ write concern/quorum để tăng tốc replication mà bỏ qua durability/consistency requirements.

### Bước 8 — Chứng minh recovery

Không chỉ thấy `lagSeconds=0`. Cần verify:

- Replica applied source position đã bắt kịp.
- Versioned probes qua các read routes đáp ứng SLO.
- Cache/index/search visible versions đủ mới.
- Không có read regressions.
- Error/timeout rate trở lại baseline.
- Failover/replica eligibility được phục hồi an toàn.

### Bước 9 — Hậu kiểm

Nêu root cause, phạm vi key/region, khoảng thời gian, số users affected, mất dữ liệu hay chỉ delay, trade-off consistency, nguyên nhân alert không phát hiện sớm, giải pháp dài hạn.

## 30. Cây quyết định cho stale result

~~~mermaid
flowchart TD
    A["Client read sees unexpected old value"] --> B{"Write outcome known committed?"}
    B -->|No| Q["Resolve unknown outcome / operation ID"]
    B -->|Yes| C{"Read contract requires newer version?"}
    C -->|No| D["Eventual lag within or beyond freshness SLO?"]
    C -->|Yes| E{"Direct authoritative read has expected version?"}
    E -->|No| F["Conflict, wrong key, authority or write assumption"]
    E -->|Yes| G{"Direct selected replica has expected version?"}
    G -->|No| H["Replica progress/consistency/routing issue"]
    G -->|Yes| I{"Cache or search path returns older version?"}
    I -->|Yes| J["Invalidation/index refresh/derived model lag"]
    I -->|No| K["App mapping/session/context/observability issue"]
~~~

Sơ đồ định hướng **phép đo tiếp theo**, không phải thuật toán chứng minh root cause tự động. Ví dụ, một active-active conflict có thể làm “authoritative” state không còn một scalar version đơn giản.

## 31. Case study A — MongoDB follower lag nhưng user reads vẫn mới

**Bối cảnh:** Replica set có primary P và secondaries S1, S2. S2 đang replication lag khoảng 6 giây sau storage maintenance.

~~~text
P:  latest committed Order v100
S1: applied Order v100
S2: applied Order v97

Critical GET routes: primary only
Analytics GET routes: secondary allowed
~~~

### 31.1. Triệu chứng

- Critical GET luôn trả v100.
- Analytics GET thỉnh thoảng trả v97.
- Dashboard cluster-wide max lag 6 giây.

### 31.2. Chẩn đoán

Max replication lag phản ánh S2 có vấn đề, nhưng **không đồng nghĩa critical reads đang stale**. Analytics stale behavior phụ thuộc read contract. Cần route IDs và session version telemetry để xác minh.

### 31.3. Hành động

Nếu S2 vượt freshness SLO, đưa nó ra khỏi eligible analytics read pool theo cơ chế hỗ trợ; vẫn quan sát recovery, failover safety và read capacity trên S1/P.

### 31.4. Bài học

Replication lag ảnh hưởng **rủi ro và những đường đọc chạm replica chậm**, không phải một con số thay thế mọi user-facing read freshness.

## 32. Case study B — Replication lag gần 0, cache vẫn trả stale

~~~text
Write O900 v18 committed:       10:00:00
All storage replicas applied:   10:00:00.030
Distributed cache retains v17: until 10:00:10
GET through API at 10:00:03:   returns v17
~~~

### 32.1. Sai lầm thường gặp

Team tăng database replica bandwidth hoặc thêm secondary. Không giảm stale result vì DB không phải nút thắt.

### 32.2. Kiểm chứng

Versioned read trực tiếp replica trả v18; cache diagnostics trả entry v17 và invalidation event bị trễ. API trace trỏ tới cache hit.

### 32.3. Sửa

Version-aware cache, invalidation pipeline có checkpoint/retry, fallback khi minVersion cao hơn cache value, bounded TTL và coalescing để tránh stampede.

### 32.4. Kết quả cần đo

Không chỉ `cache invalidated`; đo **ACK→API visible p95/p99** và read-your-writes violations sau fix.

## 33. Case study C — Cassandra đọc ONE thấy dữ liệu khác nhau

**Bối cảnh:** RF=3, write dùng một consistency level và read từ replicas có thể khác nhau.

~~~text
Logical write: Order O500 version 11
Replica A: v11
Replica B: v10
Replica C: v10
~~~

Nếu write chỉ đáp ứng ở A theo mức consistency được chọn, các reads `ONE` chạm B/C có thể thấy v10 theo protocol cho phép.

### 33.1. Vì sao “lag=0 trên node A” không giải thích user?

User read route có thể tới B, còn hệ không có một global primary log lag scalar. Cần quan sát **per-key result và consistency level**.

### 33.2. Thí nghiệm

Ghi synthetic key với một version, đọc lại nhiều lần theo CL/region/coordinator routes có kiểm soát, đo tỉ lệ stale/version gap, errors và thời gian hội tụ. Không suy từ một sentinel key sang mọi partitions.

### 33.3. Hành động

Chọn CL/read policy đúng business needs, đồng thời giải quyết replica health/repair/hints và timeouts. Nâng consistency có latency/availability trade-offs, không thay đổi khi chưa đánh giá.

## 34. Case study D — DynamoDB Global Table region B chậm

~~~text
Region A write Order v18 receives ACK.
Region A direct read sees v18.
Region B reads initially see v17.
Eventually Region B sees v18.
~~~

### 34.1. Ba giả thuyết

1. Cross-region replication đang trễ.
2. Region B read qua một GSI hoặc cache có additional delay.
3. Concurrent Region B writer đã tạo conflict/winner khác.

### 34.2. Đo đúng

Đối chiếu version và region, metric Global Table replication theo mode, direct base-table read, GSI query và cache/API route. Không lấy CloudWatch lag mean làm version-exact proof.

### 34.3. SLO

Nếu checkout cần read-your-writes cross-region và mode không cam kết, cần thiết kế session routing/strong-consistency feature theo contract hoặc không thực hiện quyết định critical từ read eventual ở Region B.

## 35. Case study E — Search index đã nhận nhưng chưa query-visible

~~~text
t=0ms    Source Order v18 committed
t=80ms   CDC consumer applied indexing request
t=90ms   Search index write ACK
t=850ms  Search refresh exposes v18
t=900ms  Client search query returns v18
~~~

**Replication source follower** có thể chỉ lag 15 ms; **search freshness** ~900 ms theo đường đọc này. Nếu mục tiêu search p99 dưới 500 ms, cần đo index refresh/indexing load, không phải tối ưu follower replication.

Một read by ID có thể thấy v18 trước search query theo engine/API semantics; kiểm tra đúng loại phép đọc.

## 36. Case study F — No writes nhưng biểu đồ “lag” tăng liên tục

~~~text
12:00   Source latest commit at position P100
12:00   Follower applied P100
18:00   No newer writes; both still at P100
Dashboard: now - lastAppliedWallTime = 6 hours
~~~

Nếu dashboard gọi 6 giờ đó là “replication lag”, metric bị định nghĩa sai cho idle case. **Cả hai progress positions đều bằng nhau**.

Có thể dùng periodic committed heartbeats trong cùng source stream để đo tiến độ khi idle, có quota và cleanup; không suy lag chỉ từ tuổi last event.

## 37. Case study G — Read có version regression sau failover

~~~text
GET #1 from healthy replica A: version 42
Failover/re-routing occurs
GET #2 from recovering route B: version 40
~~~

Nếu hợp đồng có monotonic reads, đây là lỗi cần điều tra:

- Session causal token có bị mất?
- Replica eligibility và term metadata?
- Có stale local cache?
- Source history có rollback hoặc conflicting writes?
- Version thuộc cùng generation/authority không?

Nếu GET được định tuyến qua eventual replicas mà không có session/monotonic guarantees, hiện tượng có thể được phép nhưng UX/SLO vẫn cần xử lý.

## 38. Case study H — Replication receive backlog thấp, apply backlog cao

~~~text
Source committed:       position 50,000
Replica received:       position 49,995
Replica durable:        position 49,980
Replica applied:        position 45,000
Replica CPU:            heavily throttled
Replica disk queue:     increasing
~~~

Vấn đề **không nằm chủ yếu ở network ship**; replica nhận gần đủ nhưng apply chậm. Điều tra CPU quota, disk fsync/compaction, expensive indexes hoặc một long transaction. Chỉ tăng bandwidth network không sửa backlog apply.

## 39. Case study I — Broker consumer lag=0 nhưng target thiếu records

~~~text
Source committed E100.
CDC failed to ship E100 due to expired token.
Broker topic has E1..E99.
Consumer processed E99, lag=0.
Target lacks E100.
~~~

Đây là **CDC gap**. Broker metric không thấy E100 vì event chưa từng vào topic. Cần end-to-end checkpoint/source high-water comparison, gap detection, reconciliation hoặc rebootstrap; không tuyên bố target fresh chỉ từ consumer lag=0.

## 40. Case study J — Metric p99 đẹp nhưng phần lớn probes timeout

~~~text
100 total synthetic writes.
80 were visible in <=80ms.
20 not visible within 5 seconds.

Dashboard reports: p99(successful only)=80ms.
~~~

Dashboard này bỏ 20% lỗi/unknown. Báo đúng:

- `visibleWithin5s = 80%`.
- `nonVisibleAt5s = 20%`.
- `successfulLatency p99 <=80ms` trên 80 samples thành công.
- Read errors và poll counts.

Không tự gán 5 giây là exact latency cho 20 mẫu chưa thấy; chỉ biết đã vượt ngưỡng hoặc chưa thể quan sát.

## 41. Thí nghiệm có kiểm soát: tách replication lag và read freshness

Các thí nghiệm sau chỉ dành cho **môi trường test/staging hoặc canary được cấp phép**. Không chủ động ngắt mạng, xóa replica, thay write concern hay tạo traffic lớn trên production của người dùng chỉ để chứng minh một metric.

### 41.1. Thiết lập dataset và đường đo

~~~yaml
experiment: "replication-vs-read-freshness"
source:
  name: "orders-primary"
  region: "region-a"
probe:
  namespace: "__monitoring/replication"
  keysAcrossPartitions: 30
  writeAckMode: "documented-per-engine"
  versionField: "version"
  generationField: "generation"
readPaths:
  - "direct-source"
  - "direct-follower-region-a"
  - "direct-follower-region-b"
  - "application-cache"
  - "public-order-api"
  - "search-index"
limits:
  maxConcurrentProbes: 5
  pollIntervalMillis: 100
  visibilityDeadlineSeconds: 5
~~~

Đây là **mẫu metadata**, không phải file cấu hình chạy được cho một SDK cụ thể. Với NoSQL không có leader/follower theo mô hình trên, thay `direct-follower` bằng read routes/consistency options thật của sản phẩm.

### 41.2. Baseline khi hệ khỏe

1. Ghi synthetic version lên các keys trải ở nhiều partitions.
2. Đợi ACK theo contract đã chọn.
3. Đọc qua từng path, ghi first visible duration.
4. Thu leader/follower progress metrics theo cùng source IDs.
5. Ghi read success/error rate.
6. Lặp đủ samples trong nhiều cửa sổ tải.

Kết quả nên là một bảng **per-route/per-partition**, không chỉ mean:

| Read route | p50 ACK→visible | p95 | p99 | Visible within 5 s |
| --- | ---: | ---: | ---: | ---: |
| Source direct | 15 ms | 25 ms | 60 ms | 100% |
| Local follower | 40 ms | 120 ms | 350 ms | 99,9% |
| Remote follower | 150 ms | 700 ms | 2.000 ms | 99% |
| App cache | 900 ms | 3.000 ms | 4.800 ms | 97% |
| Search API | 300 ms | 1.000 ms | 2.500 ms | 99,5% |

Đây là **số liệu giả định** để minh họa báo cáo, không phải benchmark sản phẩm nào.

### 41.3. Thử nghiệm A — Cố tình làm follower nhận chậm

Trong lab có quyền, gây network delay/bandwidth limit trên đường leader→follower (không tác động client→API):

- Theo dõi receive position/bytes backlog.
- So applied progress.
- Probe direct follower và direct leader.
- Đảm bảo read route không âm thầm fallback làm che kết quả.

**Kỳ vọng:** Follower lag và ACK→follower visibility tăng; ACK→leader direct visibility có thể gần baseline nếu authority vẫn khỏe.

### 41.4. Thử nghiệm B — Follower nhận đủ nhưng apply chậm

Giả lập CPU quota/disk contention trên follower trong staging:

- Received position gần leader.
- Applied position lùi.
- Direct follower probes chậm.
- Disk/CPU/compaction telemetry chỉ ra apply bottleneck.

**Kỳ vọng:** Tăng network bandwidth không sửa apply lag trong bài test này.

### 41.5. Thử nghiệm C — Cache TTL/invalidation chậm

Không can thiệp replication. Cố tình cấu hình cache giữ v17 theo test data trong thời hạn có giới hạn:

- Direct follower đã trả v18.
- API cache trả v17.
- Public API trả v17.
- Probe trực tiếp DB có latency tốt.

**Kỳ vọng:** Lag storage vẫn thấp; user-visible freshness delay tăng theo cache behavior.

### 41.6. Thử nghiệm D — Search index refresh bị trì hoãn

Cho CDC/indexing đạt ACK nhưng delay search visibility theo tính năng/test environment:

- Source and follower v18.
- Target index accepted v18.
- Search query chỉ thấy v17.
- Sau refresh, search thấy v18.

**Kỳ vọng:** Source replication lag không thay đổi đáng kể.

### 41.7. Thử nghiệm E — Không có business writes

Dừng synthetic writes trong lab (không chặn các writes của hệ khác nếu dùng shared source):

- Leader/replica positions cùng đứng yên.
- `timeSinceLastApplied` tăng.
- Không có backlog.

**Kỳ vọng:** Monitor không nên kết luận follower lag ngày càng lớn chỉ vì không có events. Có thể bật committed heartbeat riêng để đo khả năng progress tiếp tục.

### 41.8. Thử nghiệm F — Cross-region route change

Sau ACK từ Region A, chuyển một synthetic GET sang Region B:

- Ghi region và source version.
- So với same-region GET.
- Xem cross-region replication metrics.
- Xác minh không có concurrent writer conflict.

**Kỳ vọng:** Khác biệt giữa global table replication và same-region read/cache có thể được lượng hóa.

### 41.9. Thử nghiệm G — Clock skew

Thay wall clock trong môi trường giả lập hoặc inject skew vào timestamp **chỉ ở lớp thu metrics**, không phá NTP production:

- `now - updatedAt` biến âm/lớn sai.
- Monotonic ACK→visible trong một probe process vẫn có duration hợp lý.
- Position-based progress không bị clock skew của client tác động.

**Kỳ vọng:** Hệ giám sát báo clock uncertainty hoặc không dùng timestamps vô nghĩa để đánh giá freshness.

### 41.10. Thử nghiệm H — Failover và term change

Trong lab:

1. Ghi source position/term.
2. Thực hiện failover theo công cụ của engine.
3. Quan sát replica eligibility và term mới.
4. Đọc cùng synthetic key với session/version token.
5. Xác minh monitor không trừ offsets xuyên epochs sai.

**Kỳ vọng:** Nếu read-your-writes contract áp dụng sau failover, ứng dụng không được regress; nếu hệ chỉ eventual, phải đo convergence/error behavior và giải thích rõ giới hạn.

### 41.11. Thử nghiệm I — Retention gap trong CDC

Một connector bị dừng lâu hơn retention trong test:

~~~text
Source commits E100.
Connector cannot resume before E100.
Broker remains caught up with all it received.
Target misses E100.
~~~

**Kỳ vọng:** End-to-end source→target gap alarm phát hiện, chứ không chỉ dashboard broker lag=0.

### 41.12. Thử nghiệm J — Read regression giữa replicas

1. Client đọc version 18 từ healthy replica A.
2. Chuyển route sang lagging replica B.
3. Đọc lần nữa với/không có minVersion session context.
4. Thu observed versions.

**Kỳ vọng:** Với session contract bảo đảm monotonic reads, hệ chờ/fallback/reject thay vì trả v17; với eventual reads, tỷ lệ regression được đo và đánh giá theo business SLO.

### 41.13. Thử nghiệm K — Probe timeout nhưng read đã được ghi nhận ở source

Cho write ACK thành công, rồi tạo delay trên endpoint đọc:

- Probe hết deadline.
- Source/follower positions có thể đã bắt kịp.
- `visible=false`, `timedOut=true`.

**Kỳ vọng:** Report tách *unobserved due to read failure* khỏi *known version stale*, tránh coi timeout chính xác là replica apply lag.

### 41.14. Thử nghiệm L — Chồng writes cùng key

Ghi v18 rồi v19 nhanh hơn poll interval, GET đầu tiên đã thấy v19:

- Nếu metric đo progress ≥v18, thành công.
- Nếu metric cần exact visible v18, chưa có bằng chứng nó từng được đọc.
- Nếu v19 thay đổi business meaning, kiểm tra effect và event history.

**Kỳ vọng:** Thiết kế probe nêu rõ điều kiện `>=expected` được phép hay không.

## 42. Dùng trace/operation history để chứng minh read anomaly

Một bug report nên có **chuỗi operations gắn version**:

~~~text
Client session S:
  op-1: write Order O900 version 18
        ACK received at local monotonic t=1000ms
        write concern = documented mode

  op-2: read Order O900, started t=1010ms
        observed version 17
        route = follower B, region A
        read concern = eventual
        ended t=1030ms

  op-3: read Order O900, started t=1400ms
        observed version 18
        route = follower A, region A
        ended t=1418ms
~~~

Lịch này cho thấy **read-your-writes không được đáp ứng** nếu business expectation có, nhưng chỉ là **behavior hợp lệ của eventual read policy** nếu hệ không hứa causal consistency.

### 42.1. Read có thể overlap write

Nếu GET bắt đầu trước khi PUT được ACK/commit, đọc v17 có thể phù hợp linearizable schedule khi hai operations overlap. Không xếp mọi read v17 thành violation; phân tích **real-time precedence**.

### 42.2. Write ACK từ API không luôn là source commit ACK

Một API có thể trả `202 Accepted` trước khi async worker ghi DB. Khi client GET sau 202 thấy v17, đó có thể là workflow eventual behavior, không phải replica chậm.

Muốn phân biệt, ghi rõ:

~~~text
HTTP accepted (202)
DB mutation committed
Replica applied
API read visible
~~~

Không dùng HTTP status 2xx duy nhất làm bằng chứng commit.

### 42.3. Cache hit phải có provenance

Trace nên ghi:

~~~text
cacheLayer=local-caffeine
cacheHit=true
cacheEntryVersion=17
cacheEntryAgeMs=4500
minRequiredVersion=18
~~~

Các trường version/time nên anonymized; không đưa full payload của đơn hàng vào trace.

### 42.4. Write conflict không phải stale read

Nếu Order v18 `PAID` bị một request hợp lệ sau đó đổi sang v19 `CANCELLED`, GET v19 không phải stale so với v18. Nếu app chỉ so `status != PAID` và báo “read stale” là sai. Cần version/generation và business event history.

### 42.5. Delete semantics

Nếu source đã commit DELETE v20, GET trả `404` có thể là mới nhất; GET trả document v19 mới là stale. Một probe chỉ tìm record tồn tại sẽ thất bại; cần **tombstone/delete version marker** hoặc expected non-existence dưới guard đúng.

## 43. Đọc mới nhất có thể đắt hơn đọc gần nhất

Giữa availability, latency và consistency có trade-offs thực tế:

| Read type | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- |
| Nearby eventual follower | Latency thấp, phân tải | Có thể stale |
| Leader/primary read | Gần authority | Tăng tải leader, vẫn tùy read concern |
| Quorum/majority read | Bảo đảm theo quorum/commit contract | Thêm fan-out/latency, chưa chắc linearizable |
| Causal/session read | Bảo vệ writes trước của session trong scope hỗ trợ | Phải truyền token, chờ/fallback |
| Linearizable read | Recency mạnh theo contract | Có thể đắt/chậm/unavailable khi partition |
| Cache read | Rất nhanh, giảm DB load | Cần invalidation/version/TTL |
| Search/materialized view | Query linh hoạt, nhanh cho read pattern | Indexing/CDC/refresh lag |

### 43.1. Consistency theo nghiệp vụ

- **Inventory reserve:** Thường cần conditional/atomic source-of-truth, không ra quyết định dựa vào search/cache eventual.
- **Order status ngay sau checkout:** Read-your-writes/session context giúp UX nhất quán.
- **Public product catalog:** Có thể chấp nhận bounded staleness nếu được công bố.
- **Analytics dashboard:** Có thể hiển thị `dataAsOf` watermark.
- **Audit/ledger:** Cần integrity/event history và authority, không suy từ lag trung bình.

### 43.2. Giá trị của `dataAsOf`

Một API đọc projection có thể trả:

~~~json
{
  "orders": [{"orderId": "O900", "status": "PAID"}],
  "dataAsOf": "2026-11-14T08:00:00Z",
  "sourceWatermark": "opaque-source-position"
}
~~~

`dataAsOf` chỉ có ý nghĩa nếu đó là watermark **có contract cho dataset/partition/transaction scope**. Không dùng `serverNow` làm `dataAsOf` rồi coi dữ liệu đã fresh đến hiện tại.

### 43.3. Dataset nhiều sources có vector watermarks

~~~json
{
  "projection": "order-finance",
  "sourceProgress": {
    "orders": "opaque-orders-position",
    "payments": "opaque-payments-position"
  }
}
~~~

Nếu không có global consistent cut, một `dataAsOf` scalar duy nhất có thể làm người dùng hiểu sai. Cần mô tả freshness theo mỗi nguồn hoặc quy tắc phối hợp.

### 43.4. Graceful degradation

Khi source lag vượt SLO:

- Cho phép một số read-only dashboard tiếp tục với badge “đang đồng bộ” và watermark thật.
- Critical endpoints có thể fallback leader/strong source hoặc trả lỗi có nghĩa thay vì dữ liệu cũ không được phép.
- Load shedding để bảo vệ nguồn.
- Không tự nâng consistency lên strongest cho mọi request và gây outage dây chuyền.

## 44. Những sai lầm quan sát thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `now - updatedAt` là replication lag | Record lâu không update vẫn latest | Version/source position và probes |
| `now - lastAppliedTime` khi idle | Không có writes nhưng age tăng | So source/replica positions, heartbeats |
| Trung bình lag toàn cluster | Che replica/shard rất chậm | Max/per-route lag và exposure |
| Lag source=0 suy API fresh | Cache/search/route khác có thể stale | ACK→API visible probes |
| Broker consumer lag=0 suy target fresh | CDC gap hoặc target apply chưa bền | Source-to-target watermark/reconciliation |
| So offsets khác partitions | Không có total order | Checkpoints theo stream scope |
| Dùng client timestamp làm commit clock | Clock skew/timestamp không atomic | Source version/commit metadata |
| Bỏ timeout khỏi histogram | Freshness SLI bị thiên lệch | Visible rate + censored samples |
| Chỉ probe một key khỏe | Không thấy hot/lagging partitions | Phân tầng probes |
| Probe một lần rồi coi phân phối | Không đủ p99 confidence | Đủ samples, run windows |
| GET trước write ACK bị coi violation | Operations overlap | Operation history/precedence |
| HTTP 202 được xem DB commit | 202 có thể chỉ accepted | Xác định commit event/ACK |
| Majority read được xem linearizable | Guarantees khác nhau | Đọc consistency contract |
| Secondary `maxStaleness` xem như SLA | Server selection khác user freshness | Probe + consistency |
| Retry write timeout rồi đo stale | Write có unknown outcome | Idempotency/outcome lookup |
| Version cao hơn luôn chứa effect trước | Business overwrite/conflicts | Kiểm tra domain invariant/history |
| GSI freshness xem như Global Table replication | Hai pipelines khác nhau | Đo base/GSI/region riêng |
| Search index ACK xem như searchable | Refresh có thể trễ | Search query visibility probe |
| TTL delete chậm gọi replication lag | TTL process bất đồng bộ | Business expiration filter + metrics |
| Đọc follower cũ rồi tự tăng bandwidth | Có thể cache hoặc apply/disk | Bước-by-bước trace |
| Tăng retry khi replica lag | Retry gây thêm áp lực | Bounded retry/fallback/limits |
| Chỉ đo p99 successful probes | Censoring bị bỏ | SLI visible-within-deadline |
| Trừ log positions xuyên failover epoch | Offset histories khác nhau | Term/epoch awareness |
| Không log read region/route | Không truy nguyên stale | Route provenance |
| Gộp primary/follower/search/cached latencies | Không cùng contract | Tách read paths |

## 45. Một biểu mẫu báo cáo sự cố

~~~yaml
incident:
  title: "Order GET returned older version after acknowledged write"
  affectedService: "order-api"
  sourceSystem: "NoSQL source name / version"
  readPath: "region-b/follower/cache"
  writeContract: "specific write concern / consistency"
  readContract: "eventual / causal / linearizable ..."
  affectedTimeRange: "from ... to ..."
  expected:
    keyHash: "anonymized-key"
    generation: 1
    version: 18
  observed:
    generation: 1
    version: 17
    route: "region-b"
  sourceProgress:
    committedPosition: "opaque"
    replicaReceivedPosition: "opaque"
    replicaAppliedPosition: "opaque"
  targetProgress:
    cdcPosition: "opaque"
    cacheEntryVersion: 17
  symptoms:
    staleReadRate: "measured"
    readErrorRate: "measured"
    visibleWithinSlo: "measured"
  rootCause: "supported by evidence, not guess"
  mitigation: "bounded traffic/routing/cache action"
  rollback: "defined"
  followUp: "regression test and dashboard change"
~~~

Đây là template để lưu **chứng cứ**, không phải tài liệu thay thế vendor monitoring. Dữ liệu nhận diện người dùng phải được hash/anonymize và giữ theo chính sách bảo mật.

## 46. Bài tập thực hành

### Bài 1 — Record age không phải staleness

Một Order có `updatedAt=2025-01-01`, hiện đang là tháng 11/2026. Không có write mới kể từ đó. Primary và mọi replica đều lưu version 7.

1. Record age là bao lâu theo nghĩa thời gian từ update cuối?
2. Read trả version 7 có stale không?
3. Vì sao `now - updatedAt` không phải replication lag?
4. Muốn xác minh replica caught up cần xem gì?

### Bài 2 — Lag position

Một stream có leader commit offset 50.000, follower received 49.900 và applied 49.200.

1. Tính receive position gap.
2. Tính apply position gap.
3. Tại sao không thể đổi 800 entries thành 800 ms?
4. Nếu follower durable tới 49.000, những câu hỏi durability nào cần đặt?

### Bài 3 — Không có business writes

Từ 10:00 đến 16:00, leader và follower đều ở offset 200, không có writes.

1. Chỉ số `now - lastAppliedWallTime` sẽ báo gì?
2. Actual backlog có bao nhiêu?
3. Làm thế nào để đo đường replication đang khỏe khi idle?
4. Heartbeat ở shard A có chứng minh shard B bắt kịp không?

### Bài 4 — Clock skew

Leader clock nhanh 500 ms. Probe client ghi một document với client timestamp và tính `replicaClockNow - clientUpdatedAt`.

1. Vì sao kết quả có thể âm?
2. Có thể dùng `System.nanoTime()` giữa hai JVM để trừ không?
3. Cần metadata nào nếu dùng timestamps chéo hosts?
4. Một source position giải quyết được điều gì, không giải quyết điều gì?

### Bài 5 — Read your writes

Client nhận ACK `PUT O900 version 18`, rồi GET qua follower trả version 17.

1. Nếu GET contract là eventual, đó có nhất thiết là hệ lỗi không?
2. Nếu GET contract bảo đảm read-your-writes, cần xử lý ra sao?
3. Có thể giữ minVersion token tại client/session như thế nào?
4. Nếu write API trả `202 Accepted` trước DB commit, kết luận thay đổi thế nào?

### Bài 6 — Monotonic reads

~~~text
GET #1: version 21, follower A
GET #2: version 19, follower B
GET #3: version 22, leader
~~~

1. Có read regression không?
2. Replica replication lag metric có cho biết regression sẽ xảy ra không?
3. Làm thế nào ngăn regression khi re-route?
4. Nếu source có concurrent writers và version reset, cần metadata gì?

### Bài 7 — Hai replicas và một cache

~~~text
Primary O900: v18
Replica A:    v18
Replica B:    v17
Cache:        v17
Public API:   v17
~~~

1. Có thể kết luận public API chắc chắn đọc Replica B không?
2. Phép thử nào tách cache khỏi follower lag?
3. Nếu tắt cache và API trả v18, lỗi chính có thể ở đâu?
4. Tại sao phải quan sát read route?

### Bài 8 — Tính trung bình lag

5 replicas lag theo milliseconds: `20, 30, 40, 50, 5000`.

1. Tính mean lag.
2. Mean này có đại diện tốt cho p99 user reads không?
3. Nếu chỉ Replica E phục vụ 1% reads, tác động khác khi E phục vụ 50% như thế nào?
4. Chọn alert theo max, mean hay weighted exposure?

### Bài 9 — Write-to-visible

Một probe nhận ACK lúc monotonic t=100 ms, poll GET vào t=150, 250, 350 ms. Tại t=150 và 250 thấy v17, t=350 thấy v18.

1. ACK→first-observed-visible đo được là bao nhiêu?
2. Có khẳng định mutation thực sự bắt đầu visible chính xác ở t=350 không?
3. Khoảng sai số do poll interval?
4. Cần đo gì ngoài duration nếu GET tại t=250 timeout?

### Bài 10 — Timeouts là censored samples

100 probes có 85 success dưới 200 ms, 15 không thấy trước deadline 5 giây.

1. Tỷ lệ visible within deadline?
2. Có nên báo `p99=200ms` cho toàn bộ probes?
3. Có nên gán 5 giây làm duration thật của 15 probes?
4. Thiết kế ít nhất ba metric để phản ánh đúng.

### Bài 11 — Replication source còn mới, search vẫn cũ

~~~text
Source commit v18:     t=0
Follower apply v18:    t=30ms
CDC consumer apply:    t=100ms
Search write ACK:      t=120ms
Search query sees v18: t=900ms
~~~

1. Source replica apply lag?
2. Search write-to-query-visible latency?
3. Chỗ nào nên điều tra nếu search SLO là 500ms?
4. Vì sao search indexing ACK chưa đủ?

### Bài 12 — GSI và cross-region khác nhau

Application dùng DynamoDB base table ở Region A, GSI ở Region A và Global Table copy ở Region B.

1. Đâu là ba read paths?
2. GSI query lag có đồng nghĩa Region B replication lag không?
3. Metric `ReplicationLatency` nói gì và cần xác minh scope nào?
4. Strongly consistent read của Region A có tự bảo đảm same result ở Region B mọi mode không?

### Bài 13 — MongoDB secondary read preference

Driver sử dụng `secondaryPreferred`, ứng dụng vừa ghi v18 với một write concern cụ thể.

1. GET có thể tới primary hay secondary?
2. Read preference có tự bảo đảm read-your-writes?
3. `maxStalenessSeconds` có nghĩa gì về routing/selection?
4. Với causal session, cần kiểm tra những điều kiện nào?

### Bài 14 — Redis offset

Primary replication offset 800.000; replica 795.000.

1. Tính offset gap.
2. Có bao nhiêu user commands chưa replicate?
3. Có thể suy seconds lag không?
4. `WAIT` bảo đảm những gì và những gì không, theo contract?

### Bài 15 — Cassandra QUORUM

RF=3, một write ACK tại CL ONE, GET sau đó đọc CL ONE ở replica khác.

1. Vì sao GET có thể cũ?
2. Có thể dùng công thức `R+W>N` ở trường hợp này không, và các assumptions?
3. Có một universal replication lag scalar như leader–follower không?
4. Mục tiêu nào dùng versioned probe đọc cùng partition?

### Bài 16 — Multi-region conflict

Region A ghi `Order=PAID` version 10; Region B concurrent ghi `Order=CANCELLED` version 10.

1. Có thể quyết định winner bằng numeric max version không?
2. Tại sao wall-clock last-write-wins có trade-off?
3. Nếu GET trả CANCELLED, có chắc đang stale so với PAID không?
4. Domain authority/conflict resolution nên được thiết kế ở đâu?

### Bài 17 — Delete và tombstone

Source delete Order O900 ở generation 1 version 20. Target search còn version 19.

1. Có thể xác định stale bằng `updatedAt` của bản đã xóa không?
2. Target cần delete/tombstone event và metadata gì?
3. Điều gì xảy ra nếu snapshot version 19 tới sau delete?
4. Nếu O900 được tạo lại với generation 2 version 1, phải so thế nào?

### Bài 18 — Version gap không bằng time lag

Source version 100; read version 97.

1. Version gap bao nhiêu?
2. Có biết lag 3ms hay 3 ngày không?
3. Nếu version number có gaps từ ID allocation, hiệu số còn có nghĩa số mutations không?
4. Khi nào cần source commit timestamp/position mapping?

### Bài 19 — Catch-up throughput

Source ghi 12.000 entries/s, follower apply 9.000/s trong 10 phút. Sau đó source giảm còn 7.000/s, follower apply vẫn 9.000/s.

1. Backlog tăng bao nhiêu trong 10 phút?
2. Sau đó capacity dư để catch up bao nhiêu entries/s?
3. Thời gian catch-up lý tưởng?
4. Vì sao disk/compaction/transaction cost làm dự báo sai?

### Bài 20 — Failover epoch

Leader cũ epoch 7 offset 10.000; leader mới epoch 8 offset 9.900.

1. Có thể kết luận hệ “đi lùi 100 records” chỉ từ hiệu offset không?
2. Cần xem election/commit point/rollback metadata nào?
3. Vì sao acknowledged write durability phải xét write concern?
4. Làm sao kiểm tra read-your-writes sau failover?

### Bài 21 — SLI định nghĩa sai

Team định nghĩa:

~~~text
freshness = now() - latestOrder.updatedAt
SLO: freshness < 3 seconds
~~~

1. Trường hợp nào metric tăng vô hạn dù mọi replicas đều caught up?
2. Trường hợp nào metric thấp nhưng API vẫn trả stale?
3. Thiết kế thay thế bằng `visibleWithin3s` và source positions.
4. Các expected versions cần được lấy từ đâu?

### Bài 22 — Kafka lag=0

CDC source mất E120 do resume token hết hạn. Broker chứa E1...E119, consumer xử lý hết.

1. Broker lag?
2. Target fresh so với source không?
3. End-to-end watermark/gap alarm phải kiểm tra gì?
4. Cần rebootstrap/reconciliation khi nào?

### Bài 23 — Read policy và UX

Một ứng dụng có:

~~~text
Checkout inventory decision:   requires strong source correctness
Order status after checkout:   user wants read-your-writes
Analytics dashboard:           60s lag acceptable
Public catalog:                10s bounded staleness acceptable
~~~

Chọn read policy, source và SLI khác nhau cho bốn endpoints. Tránh dùng search cache eventual làm authority cho inventory stock.

### Bài 24 — Synthetic probes gây quá tải

Team chạy 10.000 probes, mỗi probe poll DB mỗi 1 ms.

1. Worst-case poll rate khoảng bao nhiêu/s?
2. Mức tải này có thể tác động replication lag không?
3. Đề xuất giới hạn concurrent probes/poll interval.
4. Làm sao sample theo shard và route mà không tạo hot key?

### Bài 25 — Clock uncertainty

Cross-host clock offset uncertainty ±40 ms, dashboard báo lag 8 ms.

1. Có thể khẳng định 8 ms chính xác không?
2. Nên báo uncertainty/bounds thế nào?
3. Dùng source positions và monotonic probes để cải thiện ra sao?
4. Khi alert SLO=20 ms, phải điều chỉnh phương pháp đo thế nào?

### Bài 26 — Target apply và checkpoint

CDC consumer:

~~~text
1. Reads E50.
2. Commits broker offset E50.
3. Crashes before writing E50 to target.
~~~

1. Target có thể vĩnh viễn thiếu E50 không?
2. Nếu đổi thứ tự apply→checkpoint, duplicate nào xuất hiện?
3. Khi nào có thể gộp target state và checkpoint atomically?
4. Vì sao consumer lag=0 có thể che mất event?

### Bài 27 — Censored latency và SLO

Một endpoint có deadline 2 s:

~~~text
Success under 200ms: 70%
Success from 200ms to 2s: 20%
No visible result by 2s: 10%
~~~

1. VisibleWithin2s SLI?
2. Nếu mục tiêu 99%, đã đạt chưa?
3. Có thể suy p99 exact của latency population không?
4. Các samples failed reads nên được báo thế nào?

### Bài 28 — App cache, API và fallback

API nhận minVersion=18, cache entry version=17, follower version=17, leader version=18:

1. Có nên trả cache entry v17 nếu contract yêu cầu minVersion18?
2. Có thể fallback leader ngay cho mọi GET không?
3. Cần bounded wait/concurrency/fallback budget thế nào?
4. Nếu leader overloaded, API nên degrade ra sao?

### Bài 29 — SLO search và CDC

Team đo:

~~~text
Source follower lag p99:     30ms
CDC processing lag p99:      800ms
Search refresh lag p99:      1200ms
API cache TTL:               5s
~~~

1. Có thể kết luận public search freshness p99 bằng phép cộng 30+800+1200+5000 không?
2. Vì sao spans có thể chồng và các metric đo scope khác nhau?
3. Cần probe end-to-end nào?
4. Sửa tầng nào trước nếu public search version đến sau 5 giây?

### Bài 30 — Viết runbook

Một client nhận write ACK v18 nhưng GET tiếp theo trả v17 ở Region B. Metrics cho thấy:

~~~text
Source region A:          v18
Remote base table B:      v18
Remote GSI B:             v17
Java cache in region B:   v17
Public API:               v17
~~~

Hãy:

1. Nêu ít nhất ba giả thuyết.
2. Đề xuất chuỗi probes để xác định API đọc từ GSI hay cache.
3. Chỉ ra vì sao Global Table replication chưa chắc là root cause.
4. Thiết kế mitigation bảo vệ critical reads mà không overload base table.
5. Xác định các SLI cần tiếp tục theo dõi sau fix.

## 47. Gợi ý lời giải và cách suy luận

### 47.1. Bài 1 — Record age

Order version 7 là latest trên source và replicas, vì không có write mới. `updatedAt` rất cũ **không có nghĩa** read stale. Có thể dùng source/replica positions hoặc thử versioned probe để xác minh đường replication/read vẫn khỏe.

### 47.2. Bài 2 — Offset gap

~~~text
Leader:    50,000
Received:  49,900  -> receive gap = 100 entries
Applied:   49,200  -> apply gap = 800 entries
~~~

Không có thông tin entry sizes, apply rate hay commit timestamps nên không thể kết luận bao nhiêu giây. Nếu durable chỉ tới 49.000, cần hiểu `durable` so với `applied` theo engine và những writes nào đủ điều kiện promotion/ACK.

### 47.3. Bài 3 — Idle stream

Hai positions đều 200 nên backlog theo positions bằng 0. `now - lastAppliedWallTime` có thể tăng tới 6 giờ vì idle; nó không đo replica trễ sau một write mới. Một committed heartbeat trong cùng stream có thể đo liveness/delay, nhưng chỉ đại diện cho stream/shard đi qua heartbeat.

### 47.4. Bài 4 — Clock skew

Nếu `updatedAt` được cấp theo client clock chạy nhanh, lấy wall-clock ở replica trừ giá trị đó có thể âm. `System.nanoTime()` đo duration **trong một JVM**, không có common origin giữa hosts. Cross-host cần source clock semantics và uncertainty; log positions giải quyết ordering/progress trong một scope, nhưng không tự chuyển thành milliseconds.

### 47.5. Bài 5 — Read-your-writes

GET v17 sau write ACK v18 có thể **được phép** dưới eventual read contract. Với hợp đồng read-your-writes, ứng dụng phải bảo vệ expected version bằng causal session/stronger read/fallback có deadline hoặc báo chưa thể đáp ứng thay vì trả stale as successful current state. Nếu PUT trả HTTP 202 trước DB commit, phải phân biệt accepted với committed; chưa thể lấy 202 làm mốc ACK v18.

### 47.6. Bài 8 — Mean lag

\[
\bar{L}=\frac{20+30+40+50+5000}{5}
=1028\text{ ms}
\]

Mean 1.028 ms che một replica lag 5.000 ms. User impact phụ thuộc **traffic route tới replica ấy, consistency policy và distribution of keys**. Dashboard nên hiển thị per-replica lag/max, eligibility và ACK→visible/error histograms theo route, không chỉ mean.

### 47.7. Bài 9 — Polling resolution

Probe thấy v18 lần đầu t=350 ms, write ACK t=100 ms:

\[
L_{\mathrm{observed}}=350-100=250\text{ ms}
\]

Nếu t=250 ms đã đọc v17 và t=350 ms thấy v18, thời điểm thật sự **bắt đầu visible nằm giữa hai phép đọc** theo điều kiện route/monotonicity phù hợp; không khẳng định chính xác 350 ms. GET timeout tại 250 ms không chứng minh v17 còn hiện diện lúc đó, chỉ chứng minh không quan sát thành công.

### 47.8. Bài 10 — Right-censoring

VisibleWithin5s = 85%. Không có đủ thông tin để báo p99 toàn population là 200 ms. 15 samples **non-visible at deadline** phải được báo riêng như timeout/censored observations; có thể thực tế nhìn thấy sau 5 giây hoặc read path vẫn lỗi. Cần visibility rate, successful latency histogram, read errors và deadline.

### 47.9. Bài 11 — Search delay

Follower apply lag 30 ms. Search query thấy v18 ở t=900 ms nên source commit→search-visible xấp xỉ 900 ms trong conceptual common-clock timeline. Nếu SLO 500 ms, điều tra **CDC processing 100 ms, indexing ACK 120 ms, refresh/query-visible 900 ms**, đặc biệt đoạn ACK→refresh. Không đồng nhất indexing ACK với searchable.

### 47.10. Bài 14 — Redis offset

Offset gap:

\[
800\,000-795\,000=5\,000
\]

Với một stream hợp lệ, đây là 5.000 đơn vị offset/bytes theo contract, **không phải 5.000 commands hoặc milliseconds**. Muốn đo time lag cần mốc/heartbeat/probe tương ứng. `WAIT` có replica acknowledgement semantics trong phạm vi của Redis, không phải transaction toàn cụm hay bảo đảm mọi replica đã durable.

### 47.11. Bài 18 — Version gap

Version difference = 3. Nhưng không biết 3 transitions xảy ra khi nào, cũng không biết sequence có gap hay không. Cần per-key source version semantics và commit-time mapping nếu muốn ước lượng delay giây.

### 47.12. Bài 19 — Catch-up capacity

Trong 10 phút:

\[
(12\,000-9\,000)\times600=1\,800\,000
\text{ entries}
\]

Sau burst:

\[
9\,000-7\,000=2\,000\text{ entries/s dư}
\]

\[
T_{\mathrm{catchup}}=\frac{1\,800\,000}{2\,000}
=900\text{ s}=15\text{ phút}
\]

Chỉ đúng dưới giả định apply capacity, write rate và entry cost không đổi. Apply queue có thể bị chặn bởi một transaction lớn, compaction/disk/CPU hoặc network bottleneck.

### 47.13. Bài 20 — Failover epoch

Offset 10.000 ở epoch 7 và 9.900 ở epoch 8 không cho phép tính **một độ trễ -100 entries** hay kết luận rollback 100 committed writes. Cần log history/term/commit point, election và rollback metadata. Một ACK đã durable theo quorum contract có mức bảo vệ khác một ACK ở memory/local; read-your-writes sau failover cần test theo exact policy.

### 47.14. Bài 21 — SLO viết sai

`now−latestOrder.updatedAt` tăng khi lâu không có write dù data latest. Nó có thể rất nhỏ dù cache trả một bản cũ nếu field updatedAt bị đổi bởi client hoặc record khác. SLI thay thế có thể là **tỷ lệ versioned probe writes được đọc đúng qua user route trong ≤3 giây**, cùng source/follower progress metrics.

### 47.15. Bài 22 — Broker lag bằng 0

Consumer bắt kịp broker E119, nên lag broker bằng 0, nhưng source E120 chưa được CDC gửi. Target **không fresh so với source**. Phải đo source commit position→CDC→broker→target apply, phát hiện source log gap và thực hiện reconciliation/rebootstrap nếu không thể replay.

### 47.16. Bài 24 — Overload do probes

10.000 probes × 1.000 polls/s có **lý thuyết tối đa 10 triệu read attempts/s** nếu tất cả hoạt động liên tục; thực tế bị giới hạn bởi latency/thread/connection. Đây là workload rất lớn, có thể gây chính sự cố đang đo. Cần giảm concurrency, tăng poll interval, sampling có phân tầng và rate budget, có stop conditions.

### 47.17. Bài 25 — Clock uncertainty

Một metric 8 ms với uncertainty ±40 ms không đủ cơ sở để báo 8 ms chính xác hoặc kết luận đạt SLO 20 ms. Cần công bố khoảng bất định hoặc đổi sang **monotonic end-to-end probe** và progress positions. Các ngưỡng cảnh báo phải tính đến độ phân giải/sai số phép đo.

### 47.18. Bài 26 — Checkpoint trước target apply

Commit offset E50 rồi crash trước target apply có thể khiến E50 bị bỏ qua sau restart. Apply trước checkpoint cho phép replay duplicate, nhưng với **idempotent/conditional target apply** có thể an toàn. Nếu checkpoint và target state nằm trong cùng transaction thực sự được hỗ trợ, có thể commit chúng cùng atomic boundary.

### 47.19. Bài 27 — Visibility rate

Success trong deadline = 70% + 20% = **90%**, không đạt mục tiêu 99%. Không đủ dữ liệu để xác định exact p99 latency cho toàn bộ outcomes vì 10% đã bị censored tại 2 giây. Phải báo timeout rate và successful latency distribution riêng.

### 47.20. Bài 29 — Không cộng p99 bừa

Các p99 của follower lag, CDC lag, refresh lag và TTL **không nhất thiết thuộc cùng events/requests, và các stages có thể overlap**. Tổng các p99 không phải p99 end-to-end. Cần source write version→**public search query** probe, đồng thời trace các stages để xác định critical path.

### 47.21. Bài 30 — Root cause cần được chứng minh

Base table Region B đã v18 cho thấy **ít nhất đường base read được kiểm tra đã bắt kịp**, nhưng GSI và cache còn v17. API có thể dùng GSI, cache, hoặc cả hai. Probe:

1. Bypass cache nhưng giữ GSI query.
2. Bypass GSI và dùng base-key read theo policy phù hợp.
3. Đọc public API với minVersion.
4. Gắn cacheHit, targetRoute, observedVersion.

Mitigation: version-aware cache/index, bounded fallback cho critical requests, admission để bảo vệ base table và đo ACK→API-visible. Không tự kết luận Cross-Region replication là root cause.

## 48. Checklist thiết kế phép đo replication lag

### 48.1. Xác định nguồn và phạm vi

1. Nguồn có leader–follower, leaderless quorum, multi-master hay managed regional replication?
2. Metric mô tả **nguồn nào tới replica nào**, trên partition/region/epoch nào?
3. Replica đó có **eligible phục vụ reads** không?
4. Write ACK có nghĩa **đã commit/durable** đến mức nào?
5. Read consistency của những endpoints bị ảnh hưởng là gì?
6. Có ghi term/epoch/shard identities kèm offset không?
7. Có hiểu “received”, “durable”, “applied” theo engine không?
8. Có phân biệt source latest commit position với source latest observed wall clock không?

### 48.2. Lag metrics

9. Position/byte backlog có cùng stream và epoch không?
10. Có source progress và replica progress được lấy **trong cùng sampling window** không?
11. Không có writes mới có làm `last event age` bị hiểu nhầm không?
12. Metric lag theo wall clock có xử lý clock skew không?
13. Có per-shard/per-replica lag thay vì chỉ mean toàn cụm không?
14. Có đo **receive gap** khác **apply gap** khi engine hỗ trợ không?
15. Có phát hiện replica state `RECOVERING`, `INITIAL_SYNC`, resync hoặc failover không?
16. Có theo dõi backlog bytes, apply rate và source write rate để ước lượng catch-up không?
17. Có phân biệt lag time theo event heartbeat với actual query visibility không?

### 48.3. Read freshness

18. Có expected generation/version từ **acknowledged/committed source** không?
19. GET kết quả có observed version/ETag hoặc metadata tương đương không?
20. Có record actual read route, region/replica và cache hit không?
21. Có tách read your writes khỏi eventual read contract không?
22. Có kiểm tra monotonic reads/regressions không?
23. Có source version comparator đúng khi key recreate hoặc active-active conflicts không?
24. Có tránh coi `updatedAt` như commit sequence không?
25. Delete/non-existence/tombstone cases có được probe không?
26. Có phân biệt “value changed again” với “older version” không?

### 48.4. Probes và thống kê

27. Synthetic probe có không gây business side effects không?
28. Probe có ghi t_ack bằng monotonic clock sau write ACK không?
29. Poll interval/deadline có được công bố không?
30. Có giới hạn probe QPS/concurrency/keys để không overload không?
31. Probe keys có rải đúng partitions/regions/read paths không?
32. Có đo ACK→visible ở **public API** chứ không chỉ direct DB không?
33. Có phân biệt exact-version visibility và at-least-version progress không?
34. Có ghi timeout/nonvisible samples như censored outcomes không?
35. Có báo `visibleWithinSLO`, errors, p50/p95/p99 successful latencies không?
36. Có đủ số samples/trials cho p99 không?
37. Percentiles có được aggregate từ histogram/data points đúng, không lấy mean của p99 không?

### 48.5. Cache, CDC và search

38. Có tách storage replication khỏi CDC connector lag không?
39. Broker consumer committed offset có thể vượt target durable apply không?
40. Có source-to-target watermark/reconciliation chống CDC gaps không?
41. Search indexing ACK có khác query visibility không?
42. Có đo refresh interval, cache invalidation, TTL và stale-while-revalidate không?
43. Có kiểm tra browser/CDN/local/distributed caches theo version không?
44. Nếu một read model có nhiều sources, có source-specific watermarks không?
45. Có audit/repair plan khi target thiếu delete/tombstone events không?

### 48.6. An toàn và vận hành

46. Có alert max lag/per-route freshness failures thay vì chỉ cluster average không?
47. Có fallback/strong-read policy cho critical endpoints trong deadline không?
48. Bounded retries/load shedding có bảo vệ source khi lag tăng không?
49. Có phân biệt unknown write outcome với stale read không?
50. Có tracking failover/term changes và cross-region conflicts không?
51. Có hiểu SLO freshness vs availability/latency trade-offs không?
52. Có fault-injection tests với network delay, apply stall, cache stale, failover không?
53. Có đo server CPU/disk/GC và network khi replication backlog tăng không?
54. Có stage-specific metrics và một probe end-to-end không?
55. Có runbook kiểm tra version từng tầng thay vì chỉnh config theo cảm tính không?
56. Có ghi source/driver version/topology và điều kiện vendor guarantees không?
57. Có tránh đưa PII/row payload vào metrics hoặc trace không?
58. Sau fix, có xác minh cả progress lag lẫn read freshness không?
59. Có lưu incident example với operation history, source version và actual read route không?
60. Có owner rõ ràng cho source replication, CDC, cache và API SLO không?

## 49. Bảng ghi nhớ: hỏi gì thì đo gì?

| Câu hỏi | Phép đo nên bắt đầu | Phép đo **không đủ** |
| --- | --- | --- |
| Follower đã nhận changes chưa? | Source vs follower receive position | `updatedAt` của một record |
| Follower đã apply chưa? | Last applied position và source commit point | Socket nhận bytes |
| Follower đã ghi bền chưa? | Durable position/ACK contract | Applied version đơn lẻ |
| Người dùng vừa ghi đã đọc thấy chưa? | Versioned ACK→user-read probe | Replica average lag |
| Search thấy write chưa? | Actual search query visibility | Index write ACK |
| Cache trả mới chưa? | Entry version vs expected minVersion | DB log offset |
| Một region khác đã bắt kịp chưa? | Region-specific write→read probe + global replication metrics | Same-region latency |
| Key không đổi nhiều ngày có stale không? | So latest committed version | Record age |
| Consumer broker caught up là target fresh chưa? | Source→target applied watermark + compare state | Broker offset lag=0 |
| Read sau failover có regression không? | Per-session version history/generation | CPU hoặc lag mean |
| Lag tăng do mạng hay apply? | Received vs applied gaps + resource telemetry | Một số seconds behind |
| Hệ đã phục hồi sau outage chưa? | Replica caught up + API freshness SLI + error rate | Lag=0 duy nhất |

## Kết luận

**Replication lag** và **độ mới của kết quả đọc** đều liên quan đến dữ liệu chưa được đồng bộ, nhưng chúng không đồng nghĩa:

- **Replication lag** mô tả tiến độ sao chép từ một source/authority tới replica theo phạm vi log, partition, term và mốc received/durable/applied.
- **Read freshness** mô tả phiên bản mà **đường đọc thực tế** trả về so với những writes cần nhìn thấy theo consistency contract và business SLO.
- **Record age** (`now − updatedAt`) không phải replication lag; bản ghi không đổi nhiều tháng vẫn có thể là bản mới nhất.
- **Lag trung bình thấp** không loại trừ một replica/hot shard rất chậm, một cache stale hoặc search index chưa refresh.
- **Lag cao** ở follower không luôn làm user read stale nếu user đọc leader/replica khác theo policy phù hợp.
- **Commit/ACK, received, durable, applied, query-visible, client-observed** là các mốc khác nhau; chỉ so được khi hiểu contract.
- **Source position, log offset, replica generation, aggregate version và wall-clock time** phục vụ các mục đích khác nhau, không thể hoán đổi tùy ý.
- **Versioned write-to-visible probes**, dùng monotonic clock và đúng read route, là công cụ mạnh để đo freshness từ góc nhìn ứng dụng.
- **Timeout/nonvisible samples** phải được báo riêng; không bỏ chúng rồi chỉ trình bày p99 của successes.
- **Read-your-writes, monotonic reads, causal consistency, bounded staleness và linearizability** đặt ra những yêu cầu khác nhau, nên phải chọn read policy theo nghiệp vụ.
- **CDC/broker/search/cache** có độ trễ độc lập với storage replica replication; mỗi tầng cần position/visibility SLI và phép đo end-to-end.
- **NoSQL engines khác nhau** về cách đo: MongoDB có oplog/optimes, Redis có replication offsets, Cassandra có quorum/repair semantics, DynamoDB có Global Tables/GSI paths, search engines có refresh/checkpoint paths.
- **Khi sự cố**, hãy xác minh write commit outcome, expected version, đường read thật, source/replica progress và cache/target visibility trước khi tăng network/CPU/connection pool.

Câu hỏi cần mang theo sau bài học là:

> **“Ta đang đo tiến độ của replica nào trong luồng nào, hay đang đo phiên bản mà người dùng thật sự nhận? Với một write đã được xác nhận, đâu là bằng chứng rằng kết quả đọc đáp ứng đúng consistency contract và độ trễ freshness đã cam kết?”**

Trả lời được hai phần này một cách độc lập, rồi liên kết chúng bằng versioned traces và fault-injection, sẽ giúp bạn tránh tối ưu sai tầng và xây dựng hệ thống NoSQL vừa **quan sát được**, vừa **đúng về dữ liệu**.
