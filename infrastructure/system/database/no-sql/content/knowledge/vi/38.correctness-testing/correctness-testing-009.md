# Kiểm thử đọc sau ghi, đọc dữ liệu cũ và thay đổi phiên kết nối trong NoSQL

## 1. Tình huống: vừa sửa hồ sơ xong nhưng mở lại thấy dữ liệu cũ

Một ứng dụng Java cho người dùng cập nhật địa chỉ giao hàng:

```text
                 NoSQL primary                 Replica / cache
                        |                             |
Client A -- WRITE v11 ->|                             |
         <-- SUCCESS ---|                             |
                        | -- async replication -----> |
Client A -- READ ------------------------------------->|
         <-- v10 (old address) ------------------------|
```

Người dùng nhìn thấy thông báo “Cập nhật thành công”, nhưng một lần đọc ngay sau đó lại trả địa chỉ cũ. Nếu người dùng tải lại lần nữa hoặc mở ứng dụng trên thiết bị khác, kết quả có thể thay đổi.

Một kỹ sư thử dùng cùng kết nối với nút chính và lần nào cũng đọc được dữ liệu mới. Bài kiểm thử được đánh dấu *PASS*. Tuy nhiên, production dùng connection pool, load balancer, read replicas, cache và có thể tạo phiên kết nối mới sau timeout. Bài kiểm thử **chỉ xác nhận một đường đi cụ thể**, chưa chứng minh yêu cầu đọc sau ghi trên những đường đi khác.

Một kịch bản còn phức tạp hơn:

```text
T0: Session S1 reads profile revision 10.
T1: Session S1 writes revision 11; receives acknowledged success.
T2: Client reconnects; session S2 reads revision 10.
T3: S2 reads revision 11.
T4: A cache or another replica returns revision 10 again.
```

Kết quả ở T2 vi phạm **read-your-writes** nếu hợp đồng của ứng dụng cam kết đọc sau ghi qua reconnect. Kết quả ở T4 còn liên quan đến **monotonic reads**: sau khi đã nhìn thấy revision 11, không nên quay lại revision 10 trong cùng phạm vi session guarantee đã hứa.

Mục tiêu của bài học, thuộc chương **Kiểm thử tính đúng** trong module **Database No SQL**, là biến các phát biểu mơ hồ như “NoSQL của chúng tôi nhất quán” thành **những lịch sử thao tác, điều kiện quan sát và thí nghiệm có thể lặp lại**, đặc biệt khi client thay phiên, đổi node, đổi region hoặc đi qua lớp dữ liệu dẫn xuất.

## 2. Mục tiêu học tập

Sau bài này, bạn cần:

1. Phân biệt **read-after-write/read-your-writes**, **monotonic reads**, **causal consistency**, **linearizability** và **eventual consistency**.
2. Xác định một guarantee áp dụng trong phạm vi **một key, partition, client, session, connection, process, user hay toàn hệ thống**.
3. Viết **test oracle** dựa vào source revision/operation ID thay vì dựa vào cảm giác dữ liệu “có vẻ mới”.
4. Đọc đúng write acknowledgment, durability, read concern, quorum và phạm vi dữ liệu mà từng NoSQL bảo đảm.
5. Tạo lịch sử read/write có invocation/completion, session ID, endpoint/node, revision và error classes.
6. Kiểm thử đọc cũ khi route tới replica/cache/search index, đổi kết nối hoặc đổi region.
7. Tạo thí nghiệm deterministic có barriers, fault injection có giới hạn, stress và kiểm thử hồi phục sau reconnect.
8. Viết test harness Java 17 với API trừu tượng để thử các consistency contract.
9. Đối chiếu các lựa chọn MongoDB, Cassandra, DynamoDB, Redis, Elasticsearch/OpenSearch, Cosmos DB và Neo4j mà không gán nhãn đơn giản cho cả sản phẩm.
10. Xác định biện pháp sửa: session token/bookmark, leader/read routing, strong read, version gate, bounded retry hoặc thay đổi UX khi consistency yếu được chấp nhận.

## 3. Các định nghĩa cần thống nhất trước khi thử

| Khái niệm | Phát biểu cụ thể |
|---|---|
| **Read-after-write / RYW** | Sau khi một phiên đã ghi thành công, các lần đọc sau của phiên đó thấy chính ghi ấy hoặc trạng thái mới hơn |
| **Monotonic reads** | Một phiên không quan sát dữ liệu quay ngược về version cũ hơn đã quan sát |
| **Monotonic writes** | Writes của cùng phiên được thực thi theo thứ tự đã quy định |
| **Writes-follow-reads** | Ghi sau một lần đọc phải có quan hệ nhân quả phù hợp với dữ liệu đã đọc |
| **Causal consistency** | Các thao tác có quan hệ nhân quả được quan sát theo thứ tự nhân quả; concurrent independent writes có thể khác thứ tự |
| **Linearizability** | Mỗi thao tác như xảy ra tại một thời điểm giữa invocation và response, tôn trọng real-time order |
| **Eventual consistency** | Khi không còn updates, các replicas sẽ hội tụ dưới những giả định/liveness của hệ |
| **Bounded staleness** | Dữ liệu không cũ hơn một bound được định nghĩa theo version/thời gian, theo mô hình cụ thể |

### RYW là một dạng session guarantee

Giả sử writer A tạo revision 11 và nhận thành công, rồi cùng phiên A đọc:

```text
write(v11) ---- ACK ---- read() => v10
``

Nếu contract là read-your-writes, đây là **vi phạm**. Nhưng nếu reader B hoàn toàn độc lập, chưa nhận causal context từ A và service chỉ cam kết session consistency, B đọc v10 có thể **được phép**.

### Linearizability mạnh hơn RYW trong phạm vi đúng

Với object có linearizable read/write, một read **bắt đầu sau khi** write thành công hoàn tất phải thấy write đó hoặc một trạng thái sau nó, bất kể client/session. RYW chỉ đề cập lịch sử thao tác của một phiên hoặc causal context theo contract.

### Không đồng nhất eventual với “đọc cũ vô hạn đều chấp nhận”

Eventual consistency chỉ có ý nghĩa dưới những giả định về hệ sẽ tiến triển, faults dừng và replication/reconciliation tiếp tục. Sản phẩm vẫn có thể có SLA về freshness hoặc bounded staleness bổ sung; phải đo theo **hợp đồng đã công bố**.

## 4. RYW không có nghĩa mọi trường hợp đều phải trả đúng giá trị vừa ghi

Hai clients có thể ghi cùng một object:

```text
Client A writes status=PAID, revision=11, receives success.
Client B subsequently writes status=CANCELED, revision=12.
Client A reads status=CANCELED, revision=12.
```

Đây **không phải** lỗi đọc sau ghi: A đã thấy trạng thái **mới hơn**. Một assertion sai:

```java
assertEquals("PAID", read().status());
```

có thể báo lỗi giả nếu concurrent write hợp lệ đã ghi đè.

### Test oracle đúng hơn

Khi model có source revision toàn thứ tự cho cùng entity:

```text
observedRevision >= acknowledgedWriteRevision
```

Nhưng **version tăng** chỉ chứng minh điều cần đo nếu:

- Revision được phát bởi authority đáng tin.
- Có nghĩa thứ tự trên cùng entity/partition.
- Không bị reset sau delete/recreate mà thiếu incarnation/epoch.
- Read result chứa revision khớp với nội dung business state.
- Với concurrent branches/vector clocks, không so sánh các version bằng một số integer giả.

Nếu hệ dùng merge, CRDT hoặc per-field versions, cần oracle theo **causal dominance hoặc invariant**, không mặc định một số revision là đủ.

## 5. Phạm vi guarantee quan trọng hơn tên gọi

Một bảng contract cần viết rõ:

| Phạm vi | Điều có thể được cam kết | Điều không tự suy ra |
|---|---|---|
| Một physical connection | Các request trên cùng kết nối có thể dùng cùng backend | Reconnect giữ mọi session metadata |
| Một SDK session | Driver chuyển causal/session metadata | Session chia sẻ thread-safe hoặc tồn tại mãi |
| Một process/JVM | Ứng dụng có thể giữ minimum revision trong RAM | App restart vẫn giữ RYW |
| Một user/session đăng nhập | Có thể mang token qua nhiều requests | Token tự theo user giữa thiết bị |
| Một entity/partition | Đảm bảo theo key hoặc partition | Cross-partition total order |
| Một region | Read/write policies tại region đó | Cross-region visibility tức thì |
| Toàn service | Router/SDK có thể cung cấp higher-level contract | Mọi downstream cache/search tự được bảo đảm |

### Định nghĩa “phiên” trong bài kiểm thử

Không nên viết “same session” mà chưa nêu:

- Driver session object hay connection?
- Authentication web session của user?
- Client SDK instance?
- Logical session ID lưu trong distributed store?
- Context gồm session token/bookmark/revision nào?
- Context có được chuyển qua HTTP gateway, message bus, app restart hay mobile device không?

**Session ứng dụng** và **session của database driver** là hai khái niệm khác nhau. Một backend HTTP request có thể tạo database session mới trên mỗi request dù user vẫn đăng nhập bằng cùng cookie.

## 6. Phân biệt đọc sau ghi với read-your-writes và monotonic reads

Một lịch sử:

```text
S1: write X=1 [ACK]
S1: read X -> 1
S1: read X -> 0
```

Lần đọc thứ hai vi phạm:

- RYW vì thấy trước ghi của S1.
- Monotonic reads vì quay lại 0 sau khi đã thấy 1.

Một lịch sử khác:

```text
S1: read X -> 5
S1: read X -> 4
```

Vi phạm monotonic reads nếu revisions 5/4 so sánh được, **dù S1 chưa tự ghi gì**. Do đó một test chỉ write-then-read không kiểm tra đầy đủ monotonic reads.

### Những gì read-your-writes không giải quyết

RYW không tự đảm bảo:

- Một client khác lập tức thấy write.
- Atomic snapshot khi đọc nhiều keys.
- Không có concurrent stale overwrites.
- Không double-commit khi write timeout.
- Cross-region failover RPO=0.
- Có thứ tự chung tuyệt đối cho mọi operations.

**Mỗi tính chất cần test oracle riêng.**

## 7. Hợp đồng của thao tác ghi: “ACK” nghĩa là gì?

Một test RYW bắt đầu sau “write thành công”. Nhưng thành công cần định nghĩa:

```text
Client -- write request --> Database
    |
    +-- accepted into memory?
    +-- written to leader?
    +-- persisted in journal/WAL?
    +-- replicated to quorum?
    +-- visible to same node?
    +-- visible to read replicas?
```

### Các câu hỏi quan trọng

1. Response thành công có nghĩa **write đã commit** theo contract nào?
2. Write concern/consistency level là gì?
3. Operation là put/replace/conditional update hay một append delta?
4. Có async indexing/refresh sau commit không?
5. Nếu response timeout, commit outcome có thể unknown không?
6. Tại node mới khi failover, acknowledged write có còn không?

### Không suy ACK = durable global

Một primary có thể ACK local write trước khi replication hoàn tất tùy configuration. Một lần đọc từ replica chưa catch up trả data cũ; nếu original primary mất, một số ACKed writes có thể không đáp ứng durability contract mong muốn. Đo **read visibility** và **durability after failure** riêng.

## 8. Read concern và đường đi của lần đọc

Trong thực tế, một `read()` có thể đi qua nhiều lớp:

```text
Java service
   |
   +-- in-process cache
   +-- Redis cache
   +-- load balancer / region router
   +-- database primary / leader
   +-- database replica
   +-- search / materialized view
``

Một stale response từ Redis không chứng minh core NoSQL database có read concern yếu. Ngược lại test chỉ gửi read trực tiếp tới primary không chứng minh API có RYW khi production thực sự route qua cache.

### Cần phân biệt hai loại test

**Storage contract test:** đọc/ghi trực tiếp qua driver và cấu hình được ghi rõ, để kiểm tra guarantee của datastore.

**End-to-end service contract test:** qua cùng HTTP/cache/routing/authorization path mà người dùng sử dụng, để kiểm tra cam kết của ứng dụng.

Khi thất bại, so hai test để khoanh vùng:

| Storage direct | End-to-end API | Giả thuyết |
|---|---|---|
| Pass | Pass | Đường đã thử đáp ứng |
| Pass | Fail | Cache, routing, application session, read model |
| Fail | Fail | Consistency mode/replica lag hoặc thiết lập kiểm thử |
| Fail | Pass | App có thể bù bằng primary routing/version gate/cache; cần xem contract |

## 9. Định nghĩa stale theo version, không chỉ theo đồng hồ

Một response:

```json
{
  "orderId": "O100",
  "status": "PENDING",
  "revision": 10,
  "sourceCommittedAt": "2026-11-14T10:00:00Z"
}
```

Writer đã ACK revision 11; reader trả revision 10. Nếu cùng source identity, đó là **đọc cũ** theo ordering của entity.

### Đo lag bằng thời gian

Nếu có authoritative commit timestamp \(t_c\) và read response tại \(t_r\), một phép đo đơn giản:

\[
\mathrm{StalenessAge}\approx t_r-t_c
\]

Tuy nhiên chỉ đúng khi clocks/time points đáng tin và timestamp mang nghĩa đúng. Với multiple replicas có clock skew, thời gian client không thể tự chứng minh server snapshot là bao nhiêu.

### Cách đo mạnh hơn

- Ghi **revision/commit sequence/source log position** tại write ACK.
- Sau read, lấy revision quan sát.
- Nếu source có per-key total order, kiểm tra `observed >= expected`.
- Đo elapsed time bằng monotonic client timer tới khi revision xuất hiện.
- Đưa clock-derived freshness metrics riêng với uncertainty.

### Phân biệt missing với stale

Một read trả `404` ngay sau insert cũng có thể là stale visibility nếu replica/cache chưa thấy insert. Một deleted record vẫn xuất hiện sau delete là **stale resurrection**, cần oracle theo tombstone/revision.

## 10. Mô hình kết quả của phép thử

Một phép thử không chỉ trả PASS/FAIL:

```text
PASS:
  observed contract satisfied under known settings

FAIL:
  confirmed violation with trustworthy history

INCONCLUSIVE:
  insufficient evidence, ambiguous commit, telemetry gap,
  wrong scope, token expired, uncontrolled concurrent writer
```

**Inconclusive không được coi là PASS**, nhưng cũng không nên báo bug datastore khi setup không đủ để kết luận.

### Lịch sử cần lưu

```json
{
  "runId": "RYW-2026-11-14-001",
  "entityId": "synthetic-order-001",
  "sessionId": "logical-S1",
  "writerAckRevision": 11,
  "readObservedRevision": 10,
  "writeResultClass": "ACKNOWLEDGED",
  "readResultClass": "SUCCESS",
  "route": "replica-in-zone-B",
  "writeCompletedAt": "2026-11-14T10:01:10Z",
  "readInvokedAt": "2026-11-14T10:01:11Z",
  "consistencyMode": "configured-mode",
  "verdict": "FAIL_IF_RYW_PROMISED_FOR_SCOPE"
}
```

Các IDs/timestamps là dữ liệu **giả lập**. Lịch sử production phải che PII/tokens và tránh xuất raw payload.

## 11. “Bắt đầu đọc sau khi ghi xong” là điều kiện thiết yếu

So sánh hai histories:

```text
History A:
write invocation 10:00:00
read invocation  10:00:01
write ACK        10:00:02
read returns old 10:00:03

History B:
write invocation 10:00:00
write ACK        10:00:02
read invocation  10:00:03
read returns old 10:00:04
```

History A có hai operations **overlap**; một read cũ chưa chắc vi phạm linearizability/RYW, tùy session operation ordering và contract. History B rõ hơn: write hoàn tất trước khi read bắt đầu.

### Dùng barriers thay vì `sleep` tùy ý

Trong test:

1. Gửi write với unique test key.
2. Chờ tương lai write hoàn tất **theo API contract**.
3. Ghi ACK/revision và release latch.
4. Chỉ sau latch đó mới gửi read.
5. Phân loại output, có timeout nhưng không coi mọi timeout là stale.

Lệnh `Thread.sleep(1000)` không chứng minh causal ordering; nó chỉ trì hoãn.

## 12. Ma trận thí nghiệm đọc sau ghi

| Cấu hình | Write | Read ngay sau ACK | Cần xem |
|---|---|---|---|
| Same session, same connection | v11 | Same path | RYW tối thiểu |
| Same logical session, new physical connection | v11 | Reconnect | Driver session context có còn |
| New driver session, same Java client | v11 | Replica | Guarantee có vượt driver session không |
| New JVM, same user identity | v11 | Replica | Propagation token/revision |
| New device, same user | v11 | Region khác | App-level session guarantee |
| Same session, switch primary→secondary | v11 | Replica | Causal read/bookmark/concern |
| App API, Redis cache hit | v11 | Cache | Invalidation/version gate |
| Search index | v11 | Search immediately | Async refresh/freshness contract |
| Failover between ACK and read | v11 | New primary | Durability và RYW sau failover |
| Network partition | v11 ACK theo policy | Minority/majority path | Availability/consistency trade-off |

### Test theo phạm vi cam kết

Nếu engine chỉ cam kết causal consistency **khi mang cùng session context**, một bài tạo completely independent session và không chuyển causal token **không phải bằng chứng engine vi phạm cam kết đó**. Nó là một test hữu ích cho application contract nếu ứng dụng hứa RYW qua login session hoặc thiết bị.

## 13. Các yếu tố phải pin để tái lập kết quả

Một test report cần:

```yaml
test:
  id: "ryw-session-switch"
  environment: "isolated-test"
  source:
    engine: "specified-nosql"
    version: "documented"
    cluster_id: "test-cluster"
    topology: "3 replicas across 3 fault domains"
  client:
    driver_version: "documented"
    pool_settings: "documented"
    retry_policy: "documented"
  write:
    operation: "conditional-set"
    concern: "configured"
  read:
    operation: "get-by-primary-key"
    concern: "configured"
    routing: "replica"
  session:
    same_logical_user: true
    same_driver_session: false
    causal_context_propagated: false
  fault:
    class: "none"
  oracle:
    minimum_revision: 11
```

Đây là **hợp đồng thí nghiệm minh họa**, không phải YAML cho một công cụ cụ thể.

### Vì sao phải pin SDK version?

Driver có thể khác nhau về topology discovery, defaults, read preference, retries, sessions, token propagation và failover. Đổi SDK có thể thay behavior dù server cluster không đổi.

## 14. Phân loại các nguồn gây đọc cũ

| Nguồn | Ví dụ | Cách xác minh |
|---|---|---|
| Async replica | Secondary chưa apply v11 | Replica applied/visible position |
| Causal context thất lạc | Reconnect dùng session mới | So session token/afterClusterTime/bookmark |
| Cache | Redis key v10 còn TTL | Cache version, hit/miss, bypass comparison |
| Derived index | CDC đã commit source nhưng search chưa refresh | Source-to-visible revision |
| Client caching | Mobile app/offline state | Disable cache, compare wire response |
| Failover | Leader mới thiếu write vì ACK yếu | Write concern, oplog/commit history |
| Load balancer | Reader bị route sang vùng chậm | Node/region route trace |
| Concurrent writer | v12 ghi sau v11 | Event history; không coi trạng thái khác là stale |
| Stale transaction snapshot | Read transaction bắt đầu trước write | Snapshot/transaction start time |
| TTL/delete | Record đã hết hạn nhưng replica/index chưa cập nhật | Tombstone/expiry contract |

Không dùng câu “NoSQL eventual consistency nên vậy” để kết luận trước khi xác định lớp nào trả response và **hợp đồng của lớp đó**.

## 15. Một test oracle tốt cần phân biệt revision và nội dung

Giả sử record:

```json
{
  "id": "P100",
  "tenantId": "T01",
  "address": "new-address",
  "revision": 11
}
```

Việc đọc được `revision=11` không đủ nếu trường `address` vẫn là giá trị cũ do bug trong projection/serialization. Có hai loại assertion:

**Thứ tự:** `observedRevision >= acknowledgedRevision` theo revision authority của entity.

**Nội dung và invariant:** dữ liệu ở revision đó phản ánh thao tác thành công hoặc một thao tác mới hơn hợp lệ.

### Test khi không có concurrent writers

Để cô lập RYW, dùng unique synthetic key không có writer khác:

```text
create key K with value v0
write K=v1, revision=1
await ACK
read K
assert revision >=1 AND value=v1
``

Đây là phép thử hẹp, dễ kết luận.

### Test khi có concurrent writers

Tạo lịch sử các writes được xác nhận, chứa parent revision/operation ID. Khi read trả revision mới hơn, xác minh state có thể suy ra từ một **legal sequential/causal history**. Không đòi value bằng v1 nếu một write v2 đã thay đổi hợp lệ.

### Khi cần kiểm tra multi-key

Nếu một transaction cập nhật cả order và payment, per-key RYW không chứng minh atomic visibility:

```text
order v11 visible
payment v10 visible
``

Cần oracle theo **transaction/snapshot consistency** của API; có thể tách bài riêng cho atomic multi-document read.

## 16. Kiểm thử tồn tại, update và delete

RYW không chỉ là cập nhật một field:

| Thao tác | Assertion đọc sau thành công |
|---|---|
| Insert | Read by exact ID nhìn thấy entity và revision mới |
| Replace/Update | Read nhìn thấy thay đổi hoặc state sau đó |
| Conditional update | Chỉ kiểm tra khi condition applied; condition-not-met không phải write ACK |
| Delete | Read không còn trả bản live cũ theo contract; có thể thấy tombstone nếu API công bố |
| TTL update | Read tuân expiry timestamp/TTL semantics |
| Bulk write | Kiểm tra outcome từng item; top-level HTTP success có thể là partial success |
| Transaction | Kiểm tra commit outcome và snapshot/read concern phù hợp |

### Test delete khó hơn insert

Một cache hoặc search index có thể giữ bản live cũ ngay sau delete:

```text
Source DELETE O1 revision=12 acknowledged.
API read through cache returns O1 revision=11.
``

Nếu delete có privacy/authorization semantics, stale read có thể nghiêm trọng hơn việc thiếu một hồ sơ vừa được tạo.

### Tombstone phải có version

Nếu delete được biểu diễn bằng `deleted=true,revision=12`, test oracle có thể nhận diện việc stale replica/CDC replay v11 hồi sinh record. Nếu target xóa vật lý và mất version metadata, phải có cơ chế khác để chống replay cũ.

## 17. RYW và durability sau failover là hai bài kiểm tra độc lập

Một test đơn giản:

```text
1. Write revision 11 to current primary; receive ACK.
2. Read immediately from same primary; see revision 11.
3. Crash/isolate primary.
4. Reconnect to new primary.
5. Read; see revision 10.
``

Phần 1–2 có thể **PASS RYW trong cùng node**. Phần 3–5 cho thấy khả năng mất acknowledged write hoặc đọc từ một replica chưa catch up, tùy ACK/consistency contract và topology. Không trộn kết luận:

- “same-node visibility” có thể đạt.
- “majority durable write survives failover” có thể không đạt nếu cấu hình yếu.
- “RYW across reconnect” có thể không được cam kết nếu session context đã mất.

### Kiểm tra authority

Sau failover, cần xác minh:

1. Write concern/ack thực tế của operation.
2. New primary/leader được bầu hợp lệ và epoch/term.
3. Read concern/route của lần đọc.
4. Source commit/revision history.
5. Có concurrent overwrite hoặc rollback/repair được công bố không.

Không dùng một lần stale read sau failover để tuyên bố database làm mất dữ liệu nếu thiếu bằng chứng về commit/durability.

## 18. Một phiên kết nối đổi vì những nguyên nhân nào?

```text
Java SDK client
    |
    +-- TCP connection closed / idle timeout
    +-- TLS session renegotiation / network reset
    +-- connection pool replacement
    +-- leader or replica topology change
    +-- load balancer route change
    +-- driver retries with another server
    +-- JVM restart, SDK client recreation
    +-- HTTP request served by another app pod
    +-- mobile device reconnect / region failover
``

### Physical connection không phải causal context

Một driver có thể thực hiện nhiều operations trên các socket khác nhau trong cùng **logical session**. Ngược lại hai requests trên cùng TCP socket không nhất thiết được coi là một causal session của application.

### Test cần cố ý thay đúng biến

Nếu muốn kiểm tra *physical reconnect*, giữ nguyên logical session và causal token khi API hỗ trợ, chỉ thay socket/route.

Nếu muốn kiểm tra *logical session reset*, tạo session mới **không** chuyển token.

Nếu muốn kiểm tra *context propagation*, tạo session mới **có** chuyển minimum revision/session token/bookmark theo contract.

Thay cả region, SDK version, consistency level và session token cùng lúc sẽ khiến thất bại khó giải thích.

## 19. Ba phép thử reconnect quan trọng

### Trường hợp A — Giữ logical session, đổi physical connection

```text
S1: write K=v11 -> ACK
force socket reconnection / pool refresh
S1: read K -> ?
``

Nếu driver cam kết causal session trên S1 và route có khả năng đáp ứng, mong muốn là không đọc cũ. Phải bảo đảm test thực sự đổi socket nhưng không mất session context.

### Trường hợp B — Tạo logical session mới, không chuyển context

```text
S1: write K=v11 -> ACK
close S1
create S2 with no causal context
S2: read K -> ?
``

Nếu datastore chỉ cung cấp session guarantee và read là eventual, S2 đọc cũ có thể đúng contract. Đây là **negative/control experiment** giúp phân biệt session semantics.

### Trường hợp C — Tạo session mới và chuyển context

```text
S1: write K=v11 -> ACK + causal marker M
close S1
create S2 carrying M
S2: read K with min-visible marker M
``

Nếu API hỗ trợ portable marker và read chờ/route tới node đủ mới, test kỳ vọng không trả version cũ hơn boundary. Nếu API không có cách nhập causal context, đừng tự cho rằng token có thể được chuyển.

## 20. Session token, bookmark và minimum revision

Một cách biểu diễn:

```text
Write response:
  sourceRevision = 11
  causalToken    = opaque M11

Next read request:
  requiredMinimumRevision = 11
  causalContext = M11
``

Các hệ có cơ chế khác nhau:

- Có hệ cho causal session time/cluster time.
- Có hệ cấp session token cho SDK/client.
- Có hệ cho bookmark để bảo đảm routing follower đã bắt kịp.
- Có hệ chỉ cho đọc mạnh ở leader/quorum và không có session token portable.
- Có hệ application phải giữ minimum revision và so sánh version tự xây.

### Không tự sửa opaque token

Session tokens/bookmarks là metadata theo provider, không phải version do ứng dụng có thể cộng `+1`. Chúng có thể gắn partition, cluster incarnation, consistency level hoặc scope authentication.

### Giữ token an toàn

- Không chèn raw token vào logs/traces rộng quyền.
- Ràng buộc theo user/tenant/source region nếu contract đòi.
- Không để client thay token nhằm vượt authorization.
- Version/expire/rotate token theo API policy.
- Không ghi token của một user vào cache chung không có scope.

**Causal ordering không thay thế tenant authentication/authorization.**

## 21. Test latency của RYW và timeout

Một hệ có thể bảo đảm RYW bằng cách **đợi replica bắt kịp**. Điều đó làm tăng latency:

```text
Write v11 acknowledged at t0.
Read routed to replica at t0+5ms.
Replica currently v10.
Read waits 150ms for v11.
Read returns v11 at t0+155ms.
``

Đây có thể là RYW **PASS**, nhưng nếu application SLO p99=100ms thì latency **FAIL**.

### Phân biệt ba outcome

1. Read trả v10 trong deadline → RYW FAIL nếu contract bắt buộc v11.
2. Read đợi, trả v11 trước deadline → RYW PASS; kiểm latency SLO riêng.
3. Read timeout do replica chưa bắt kịp → không có stale value, nhưng **availability/latency FAIL** theo business contract.

Không biến stale read thành timeout vô hạn để nói “consistency hoàn hảo”. Tính đúng và khả năng phục vụ phải cùng được đo.

## 22. Bounded staleness: đo đúng bound và phân bố

Một sản phẩm có thể không hứa RYW ngay trên mọi reader, nhưng ứng dụng cho phép:

```text
95% reads see updates within 2 seconds
99.9% reads see updates within 10 seconds
``

Đây là một **freshness SLO** ứng dụng phải đo, không tự suy từ eventual consistency.

### Thí nghiệm

1. Ghi một revision mới bằng write concern được xác định.
2. Sau ACK, đọc từ route cần kiểm tra ở thời điểm \(0,100,200,\ldots\) ms.
3. Đo **time to first visibility** và **stale read frequency**.
4. Lặp đủ nhiều mẫu qua các AZ/regions và tải thực tế.
5. Đo cả **regressions**: sau khi đã thấy v11, có quay lại v10 không?

### Không suy một lần thấy v11 là đã hội tụ toàn cụm

Một reader thấy v11 từ replica A rồi chuyển sang replica B trả v10. Cần đo per replica/route và monotonic reads, không chỉ first-success.

### Percentile và histogram

P99 visibility delay không tính bằng cách lấy trung bình các p99 của từng replica. Dùng distribution/histogram và aggregation đúng scope; ghi missing/timeout separately để không tạo selection bias chỉ trên các reads thành công.

## 23. Negative control và positive control

Để biết test có thật sự phát hiện stale data:

**Positive control:** đọc trực tiếp từ một authoritative path được cấu hình mạnh/causal context hợp lệ, mong chờ thấy v11.

**Negative control:** cố ý dùng delayed replica hoặc fake stale adapter trong lab trả v10, test oracle phải báo FAIL.

Nếu negative control vẫn PASS, assertion sai hoặc harness không nhìn đúng revision.

### Cần tránh đánh đồng control với product guarantee

Một test negative control đọc eventual replica v10 không phải “lỗi sản phẩm” nếu eventual read cho phép. Nó giúp chứng minh **harness biết nhận ra dữ liệu cũ**, sau đó đánh giá scope contract mới là PASS/FAIL.

### Reproducibility

Ghi seed, test IDs, topology, injected delay, region routing và kết quả. Một test ngẫu nhiên 1.000 lần không thấy stale **chưa chứng minh** không có stale ở mọi lịch sử tương lai.

## 24. Thiết kế lớp oracle độc lập với driver

Test infrastructure nên tách:

```text
Test scenario
    |
    +-- Operation scheduler / barriers
    +-- Client/session manager
    +-- Driver adapter for engine
    +-- History recorder
    +-- Oracle for contract
    +-- Report / metrics
``

Vì sao?

- Khi đổi MongoDB sang Cassandra, vẫn kiểm được cùng business contract nhưng adapter dùng read concern khác.
- Khi đổi driver/session logic, oracle vẫn như cũ.
- Khi có failover, scheduler có thể inject fault sau ACK.
- Khi test báo FAIL, history có thể tái dựng điều gì xảy ra mà không cần phụ thuộc logs server.

### Mỗi operation record tối thiểu

```text
operationId
entityId / key (synthetic)
logicalClientId
logicalSessionId
driverSessionId/causalContext identifier if accessible
endpoint/region/route
operation type
invocation time
completion time
write ACK / unknown / rejected
acknowledged revision/commit token
read observed revision/value
exception category and retry attempts
``

Không cần xuất raw session tokens/PII vào báo cáo; có thể dùng hash/redacted identifiers để correlate.

## 25. Test một client không đại diện cho mọi clients

Mẫu chỉ gồm:

```text
Client A write then Client A read through same connection.
``

có thể PASS ngay cả khi:

- Cùng user mở ứng dụng trên điện thoại khác thấy dữ liệu cũ.
- HTTP request tiếp theo đi vào app pod khác, mất session token.
- Load balancer đổi replica.
- Cache trả bản cũ.
- Multi-region client chuyển nơi.
- Reconnect làm tạo driver session mới.

### Các trục cần kiểm soát

| Trục | Giá trị thử |
|---|---|
| SDK session | same/new-with-token/new-without-token |
| Physical socket | same/new |
| App pod | same/different |
| Storage read route | leader/replica |
| Region | same/other |
| Cache | bypass/hit/miss |
| Concurrent updates | none/one/many |
| Fault | none/delay/replica pause/election |
| Read mode | configured eventual/strong/causal |

Không cần chạy mọi tổ hợp nếu vô nghĩa; chọn **pairwise và risk-based coverage**, nhưng phải thử những đường mà ứng dụng hứa bảo đảm.

## 26. Causal consistency có thể yêu cầu operations tuần tự trong cùng session

Một causal session có thể theo thứ tự:

```text
S: write K=v11 -> ACK
S: read K       -> at least v11
``

Nếu hai threads dùng một session object không được thiết kế thread-safe và gửi operations song song, test có thể vi phạm điều kiện của SDK. Khi đo:

- Kiểm tra driver có cho concurrent operations trong cùng logical session không.
- Bảo đảm write ACK precedes read invocation qua barrier.
- Không share mutable session object giữa threads nếu SDK cấm.
- Nếu muốn chuyển causal context giữa requests, dùng cơ chế chính thức hoặc ứng dụng xây protocol của mình.

### Thread schedule và causal schedule

Hai threads đang chạy trên cùng JVM không tự có causal ordering chỉ vì thread B thực thi sau một khoảng wall-clock. Dùng `CompletableFuture` completion/latch hoặc handoff token rõ ràng để định nghĩa quan hệ nhân quả.

## 27. Một thử nghiệm đổi kết nối có ba kết quả riêng

Giả định application hứa RYW trong cùng **web login session**:

```text
POST /profile => 200, revision=11
GET  /profile from pod-A => revision=11
GET  /profile from pod-B => revision=10
``

**Storage-only test** có thể vẫn pass. **Application-level RYW contract** fail vì pod-B không nhận minimum revision từ login session hoặc cache/version store.

Trong báo cáo cần ghi:

- `STORAGE_SESSION_RYW: PASS` ở driver session A, nếu thí nghiệm tương ứng đạt.
- `APP_LOGIN_SESSION_RYW: FAIL` khi đổi pod A→B.
- Hypothesis: session token không lan qua stateless gateway, pod-local cache hoặc replica lag.

Không sửa bằng cách ép mọi GET đọc primary một cách vô thức nếu lưu lượng lớn; cân nhắc version token, conditional waits, cache invalidation, sticky routing có giới hạn và fallback phù hợp SLO.

## 28. Java 17: mô hình hóa contract bằng interface

Để không phụ thuộc một driver, định nghĩa một interface adapter:

```java
public interface VersionedNoSql {
    interface Session extends AutoCloseable {
        @Override void close();
    }

    record WriteAck(
        String operationId,
        long revision,
        String causalContext
    ) {}

    record ReadValue(
        String entityId,
        long revision,
        String payload
    ) {}

    // null context means a genuinely new logical session.
    // Non-null context is legal only if the adapter/provider supports it.
    Session openSession(String causalContext);

    // The adapter must only return WriteAck for an acknowledged,
    // successful write under the configured write concern.
    WriteAck put(
        Session session,
        String entityId,
        String operationId,
        long newRevision,
        String payload
    ) throws Exception;

    // Read mode and route are configured by the adapter/test scenario.
    ReadValue read(
        Session session,
        String entityId
    ) throws Exception;
}
```

### Điều bắt buộc của adapter

- Dùng **synthetic entity ID** không bị client khác sửa.
- Không chế tạo `WriteAck` nếu driver thực sự báo timeout/unknown outcome.
- Ghi rõ write concern, read mode, route/node, session semantics.
- Nếu `causalContext` không portable trong engine, **không giả vờ** `openSession(context)` được hỗ trợ.
- Không so các revisions không có cùng source authority.
- Không lấy source revision bằng cách đọc từ một replica eventual rồi tự tăng `+1` nếu cần uniqueness/ordering mạnh.

Như vậy harness kiểm đúng tính chất ứng dụng **mong đợi**, còn adapter là nơi thể hiện guarantee thật của NoSQL.

## 29. Java 17: phép thử RYW trong cùng driver session

```java
import java.util.UUID;

public final class ReadYourWritesProbe {
    public enum Verdict {
        PASS, STALE_READ, UNEXPECTED_VALUE, INCONCLUSIVE
    }

    public static Verdict sameSession(VersionedNoSql store)
            throws Exception {
        String entityId = "canary-" + UUID.randomUUID();
        String operationId = "write-" + UUID.randomUUID();
        long expectedRevision = 11L;
        String expectedValue = "synthetic-v11";

        try (VersionedNoSql.Session session =
                 store.openSession(null)) {
            VersionedNoSql.WriteAck ack = store.put(
                session,
                entityId,
                operationId,
                expectedRevision,
                expectedValue
            );

            if (ack == null
                    || !operationId.equals(ack.operationId())
                    || ack.revision() != expectedRevision) {
                return Verdict.INCONCLUSIVE;
            }

            // Synchronous ACK completes BEFORE read begins.
            VersionedNoSql.ReadValue value =
                store.read(session, entityId);

            if (value == null) {
                return Verdict.STALE_READ;
            }
            if (value.revision() < ack.revision()) {
                return Verdict.STALE_READ;
            }
            if (!expectedValue.equals(value.payload())) {
                // In this isolated canary there are no other writers.
                return Verdict.UNEXPECTED_VALUE;
            }
            return Verdict.PASS;
        }
    }
}
```

### Cách đọc kết quả

`STALE_READ` chỉ là **contract violation** nếu cấu hình test hứa RYW ở same session. Nếu dùng eventual read **không có guarantee** tương ứng, kết quả chứng minh đây là đường có thể stale, không phải lỗi ngoài contract.

### Giới hạn của ví dụ

- Revision 11 được gán cố định chỉ hợp lệ khi **key hoàn toàn mới** và adapter/source hỗ trợ thiết lập revision đó; production thường lấy version từ server.
- Một `read()` ném exception có thể là timeout/unavailable. Harness gọi phía ngoài phải phân loại riêng, không tự tính exception là stale.
- Không có retry/cleanup/metrics trong ví dụ; mỗi thử phải sử dụng namespace, TTL và quyền phù hợp.
- Payload assertion dựa trên assumption **không có concurrent writer**.
- Bài test không chứng minh durable state sau failover nếu chưa có fault.

## 30. Java: đóng session rồi mở session mới

Thí nghiệm tách hai biến:

```java
import java.util.UUID;

public final class SessionSwitchProbe {
    public record Result(
        long writtenRevision,
        long observedRevision,
        boolean satisfiesMinimum
    ) {}

    public static Result switchLogicalSession(
            VersionedNoSql store,
            boolean propagateCausalContext) throws Exception {

        String id = "canary-" + UUID.randomUUID();
        VersionedNoSql.WriteAck ack;

        try (VersionedNoSql.Session first =
                 store.openSession(null)) {
            ack = store.put(
                first, id, "op-" + id, 1L, "synthetic"
            );
        }

        // A non-null causalContext is passed only for adapters
        // that explicitly support importing causal metadata.
        String nextContext = propagateCausalContext
            ? ack.causalContext()
            : null;

        try (VersionedNoSql.Session second =
                 store.openSession(nextContext)) {
            VersionedNoSql.ReadValue read =
                store.read(second, id);

            long observed = (read == null)
                ? -1L
                : read.revision();

            return new Result(
                ack.revision(),
                observed,
                observed >= ack.revision()
            );
        }
    }
}
```

### So sánh hai run

| Run | Context giữa sessions | Mong đợi |
|---|---|---|
| A | Không chuyển | Đo behavior khi session reset, không mặc định bảo đảm |
| B | Chuyển đúng token theo API | RYW nếu provider/application cam kết và read có thể đáp ứng |

Chạy hai run trên **khóa thử riêng** hoặc reset source state có kiểm soát. Nếu B không được provider hỗ trợ, đánh dấu “unsupported contract”, không giả tạo token.

### Không giả đồng nghĩa “new session” với “new socket”

SDK có thể tái dùng physical socket ngay cả khi `openSession(null)` tạo logical session mới. Muốn kiểm tra reconnect vật lý, instrumentation phải xác nhận connection/route thật đã thay đổi.

## 31. Java: asynchronous barrier loại trừ write/read overlap

Trong hệ async, viết:

```java
import java.util.concurrent.CompletableFuture;

public final class AsyncCausalityProbe {
    public static CompletableFuture<VersionedNoSql.ReadValue>
            readOnlyAfterAck(
                CompletableFuture<VersionedNoSql.WriteAck>
                    acknowledgedWrite,
                java.util.function.Function<
                    VersionedNoSql.WriteAck,
                    CompletableFuture<VersionedNoSql.ReadValue>
                > startRead) {

        // thenCompose starts reading only once write future succeeds.
        return acknowledgedWrite.thenCompose(startRead);
    }
}
```

Nếu future hoàn thành khi SDK **chỉ enqueue request vào memory**, đó không phải write ACK; adapter phải định nghĩa completion đúng. Cũng cần xử lý cancellation và unknown outcomes. `thenCompose` tránh overlap ở tầng ứng dụng nhưng không thay **consistency mode** của database.

### Không dùng `Thread.sleep` làm primitive đồng bộ

```java
sendWriteAsync();
Thread.sleep(200);
read();
``

Đoạn này **không bảo đảm** write đã được ACK trước khi read bắt đầu. Trên máy chậm/GC pause hoặc network partition, thứ tự có thể khác dự đoán.

## 32. Java: kiểm tra monotonic reads khi đổi route

Giả sử adapter hỗ trợ đọc cùng entity từ nhiều routes đã cấu hình:

```java
public final class MonotonicReadOracle {
    public static void assertNonDecreasing(
            long[] observedRevisions) {
        long last = Long.MIN_VALUE;
        for (long revision : observedRevisions) {
            if (revision < last) {
                throw new AssertionError(
                    "Read regressed from " + last +
                    " to " + revision
                );
            }
            last = revision;
        }
    }
}
```

Thử:

```text
Read 1 from replica-A -> revision 11
Read 2 from replica-B -> revision 10
Read 3 from primary   -> revision 12
``

Oracle báo regression ở read 2. Tuy nhiên kết luận “vi phạm” chỉ khi logical session/account contract yêu cầu monotonic reads qua những routes ấy.

### Cần chú ý

- Không xem một read error/timeout là revision `-1` trong oracle này; phân loại riêng.
- Nếu entity bị delete/recreate, revision phải chứa source incarnation/epoch.
- Nếu read trả multiple causally concurrent versions, một scalar comparator không đủ.
- Nếu một transaction snapshot được cố định tại T0, việc read cũ trong transaction đó có thể là **đúng snapshot contract**; không áp oracle monotonic/RYW tùy tiện ngoài scope.

## 33. Java: polling visibility và đo thời gian

Khi contract chỉ yêu cầu **eventually visible** hoặc bounded freshness, đo đến khi phiên đọc nhìn thấy revision:

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public final class VisibilityProbe {
    public static long waitUntilVisibleNanos(
            VersionedNoSql store,
            VersionedNoSql.Session session,
            String id,
            long minimumRevision,
            Duration deadline,
            Duration interval) throws Exception {

        if (deadline.isNegative() || deadline.isZero()
                || interval.isNegative() || interval.isZero()) {
            throw new IllegalArgumentException("durations");
        }

        long start = System.nanoTime();
        long limit = deadline.toNanos();

        while (System.nanoTime() - start < limit) {
            VersionedNoSql.ReadValue value =
                store.read(session, id);

            if (value != null
                    && value.revision() >= minimumRevision) {
                return System.nanoTime() - start;
            }

            TimeUnit.NANOSECONDS.sleep(interval.toNanos());
        }
        throw new java.util.concurrent.TimeoutException(
            "not visible within observation window"
        );
    }
}
```

### Giới hạn

- Bắt đầu timer ở đầu polling; nếu muốn tính từ write ACK, truyền mốc monotonic ngay sau ACK vào probe.
- Một blocking read có thể kéo dài hơn deadline, nên adapter cần **per-read timeout**.
- `sleep` ở đây là **nhịp lấy mẫu sau ACK**, không dùng để tạo causal ordering.
- Polling có thể tăng tải khi interval nhỏ; cần rate budget/jitter.
- Lần đầu thấy revision không chứng minh monotonic reads sau đó.
- Hết timeout không chứng minh eventual convergence không bao giờ xảy ra; chỉ chứng minh **không đạt observation bound**.
- Nếu hệ hứa RYW tức thì, không được dùng polling để “che” một stale response đầu tiên rồi tính PASS RYW.

## 34. Java: mô tả history có invocation/completion

```java
import java.time.Instant;

public record OperationHistory(
    String runId,
    String operationId,
    String logicalClientId,
    String logicalSessionId,
    String route,
    String operation,
    long invokeNano,
    long completeNano,
    Instant observedWallTime,
    String resultClass,
    Long writtenRevision,
    Long readRevision
) {
    public OperationHistory {
        if (completeNano < invokeNano) {
            throw new IllegalArgumentException(
                "completion precedes invocation");
        }
    }
}
```

### Đồng hồ

`System.nanoTime()` phù hợp đo interval **trong cùng JVM**; giá trị không dùng để so thứ tự giữa hai JVM khác nhau. `Instant.now()` giúp correlation nhưng có thể lệch đồng hồ. Với distributed history checker, cần thu thập causal/barrier ordering và xử lý uncertainty về clock skew; không sort các logs ở nhiều hosts rồi coi timestamps là sự thật tuyệt đối.

### Recorded result classes

```text
ACKNOWLEDGED
CONDITION_NOT_MET
REJECTED
TIMEOUT_UNKNOWN_OUTCOME
READ_SUCCESS
READ_NOT_FOUND
READ_TIMEOUT
READ_ERROR
``

Tách **timeout chưa biết commit** khỏi “definitely not committed” để không tạo false positive hoặc duplicate side effect khi retry.

## 35. Đo tỷ lệ stale và độ trễ lần đầu nhìn thấy

Với \(N\) read attempts hợp lệ trong test:

\[
\mathrm{StaleReadRatio} =
\frac{\#\mathrm{reads\ returned\ an\ older\ version}}
{\#\mathrm{eligible\ completed\ reads}}
\]

Đây là thống kê **cho đúng route/consistency mode đã thử**, không phải toàn hệ nếu traffic sample bị lệch.

### Tách các loại failure

Một báo cáo:

```text
Total read attempts:     10000
Fresh/allowed reads:      9620
Stale successful reads:    230
Read timeouts:             120
Other errors:               30
``

Trong các read **hoàn tất và trả dữ liệu**, stale ratio là \(230/(9620+230)\), nhưng nếu SLO áp cho tất cả attempted logical reads, phải báo riêng timeout/error; không dùng mẫu số success-only để che availability failures.

### Đừng suy chắc chắn từ 0 stale trong 100 runs

`0/100` failures không chứng minh xác suất lỗi bằng 0. Nó chỉ không phát hiện lỗi trong mẫu đó. Có thể dùng khoảng tin cậy thống kê để diễn giải kết quả, nhưng test correctness với formal guarantee còn cần **adversarial histories** và reasoning về protocol.

## 36. Stress test phải giữ được causal ordering từng client

Ví dụ có 100 logical clients:

```text
For each client i:
  write K_i revision r_i
  await ACK
  read K_i after forced route/session change
  record outcome

Across clients:
  run concurrently at bounded rate
``

Nếu dùng một shared mutable session object cho tất cả threads, có thể phá contract của SDK và khiến test không hợp lệ.

### Cần tạo workload thực

- Nhiều readers/replicas.
- Read preference khác nhau.
- Peak/off-peak, tail latency.
- Driver connection pool churn.
- Leader election hoặc AZ loss trong **lab được phê duyệt**.
- App pod failover và network partition.

### Test có giới hạn

Use synthetic data, bounded concurrency, TTL/cleanup, abort thresholds, no real payments. Một bài test correctness không nên làm sập hệ production vì unbounded load.

## 37. MongoDB: primary, secondary và causal session

MongoDB cho phép cấu hình write concern, read concern, read preference và client session. Chúng là **các lựa chọn theo operation**, không có một mức guarantee duy nhất cho mọi thao tác.

### Kịch bản cơ bản

```text
Replica set: A=primary, B/C=secondaries

Write to A with configured acknowledgment.
Read immediately from B:
  B may not have applied the new operation yet.
``

Đọc từ secondary không có causal context có thể thấy state cũ, ngay cả khi primary đã ACK theo thiết lập write concern phù hợp. Muốn test RYW trên replica, cần xem **session causality và read concern** thay vì chỉ “viết xong rồi chọn secondary”.

### Một phép thử causal consistency

Với MongoDB hỗ trợ causal consistency session, các điều kiện quan trọng thường bao gồm:

- Sử dụng **cùng causally consistent session**, operations được thực hiện tuần tự phù hợp.
- Write concern `majority` cho writes được dùng làm causal boundary.
- Read concern `majority` cho reads được thực hiện trong causal session.
- Read theo read preference được hỗ trợ và server có thể đáp ứng causal time.

Trong các điều kiện được tài liệu hóa, session có thể truyền session/cluster time giúp read được thực hiện sau write không trả state trước causal boundary. Nếu replica chưa bắt kịp, read có thể đợi hoặc timeout theo giới hạn; **không phải được phép trả data cũ rồi tuyên bố đã đạt causal guarantee**.

### Java MongoDB Sync Driver — phác thảo

```java
import com.mongodb.ClientSessionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.UpdateOptions;
import com.mongodb.client.model.Updates;
import org.bson.Document;

public final class MongoCausalExample {
    public static Document updateThenRead(
        MongoClient client,
        String id,
        long nextRevision
    ) {
        MongoCollection<Document> collection = client
            .getDatabase("consistency_lab")
            .getCollection("canaries")
            .withWriteConcern(WriteConcern.MAJORITY)
            .withReadConcern(ReadConcern.MAJORITY)
            .withReadPreference(ReadPreference.secondaryPreferred());

        var options = ClientSessionOptions.builder()
            .causallyConsistent(true).build();

        try (ClientSession session =
                 client.startSession(options)) {
            var result = collection.updateOne(
                session,
                Filters.eq("_id", id),
                Updates.combine(
                    Updates.set("revision", nextRevision),
                    Updates.set("payload", "synthetic")
                ),
                new UpdateOptions().upsert(true)
            );
            if (!result.wasAcknowledged()) {
                throw new IllegalStateException(
                    "Write was not acknowledged");
            }

            return collection
                .find(session, Filters.eq("_id", id))
                .first();
        }
    }
}
```

Đây là ví dụ minh họa API. Để kiểm thử production semantics cần ghi driver/server version, write-result semantics, timeout, node route và đảm bảo unique synthetic record không có writer khác.

### Điểm đặc biệt cần tránh

- `secondaryPreferred` **có thể fallback về primary**, nên phải quan sát route thật nếu mục tiêu là test secondary. Khi muốn ép secondary, dùng cấu hình thích hợp và chấp nhận trường hợp không có secondary khả dụng.
- Session object có những giới hạn concurrency; không chia sẻ tùy tiện giữa threads.
- Tạo session mới mà không truyền causal context tương ứng có thể thay đổi guarantee.
- Read concern `majority` đơn lẻ và write concern `majority` đơn lẻ **không thay thế causal session** trong test RYW trên arbitrary secondary.
- `upsert` có thể tạo mới trong ví dụ; khi test update có condition, phải xác nhận result match/modify hay insert thật sự xảy ra.

### Test khác: linearizable read

MongoDB có chế độ read concern `linearizable` với điều kiện/phạm vi nhất định, thường dùng với primary và read concern/write concern thích hợp cho single-document real-time order. Nó **không đồng nghĩa** causal session read trên secondary; phải kiểm tra giới hạn read preference và lệnh được hỗ trợ trong phiên bản đang dùng.

## 38. MongoDB: đổi session nhưng giữ lại cluster time có đủ không?

Một câu hỏi thường gặp:

```text
HTTP request 1: startSession S1 -> write -> close S1
HTTP request 2: startSession S2 -> read
``

Nếu không có thông tin về causal time/operation time hoặc một application-level version fence được chuyển giữa hai requests, RYW không tự động nối liền bởi **cookie của user**.

### Các lựa chọn kiểm thử

1. Giữ cùng MongoDB `ClientSession` qua những thao tác tuần tự trong vòng đời phù hợp (không giả định nó có thể lưu dài hạn qua nhiều app pods).
2. Dùng driver/server-supported mechanisms để mang causal metadata khi thiết kế cho phép, với validation của session provenance và version compatibility.
3. Chọn đọc primary hoặc một đường đọc mạnh hơn cho thao tác yêu cầu RYW.
4. Giữ source revision của write trong application context; nếu lần read đi từ secondary trả version thấp hơn, chờ/route/fallback theo deadline.

### Không tự serialize session object thành JSON

Driver session có lifecycle, resource và thread-safety semantics. Một object session trong JVM không phải một bearer token tùy ý để lưu vào Redis và deserialize ở pod khác. Nếu muốn hỗ trợ “RYW across HTTP requests”, phải thiết kế **application protocol hoặc chức năng driver được hỗ trợ**, không dựa vào cách copy internal fields.

## 39. DynamoDB: eventually consistent và strongly consistent reads

DynamoDB cho phép một số read operations chọn **eventually consistent** hoặc **strongly consistent** trong các phạm vi được hỗ trợ.

### Test ở table/base item

```text
PutItem key K with value v11 -> successful ACK.
GetItem key K with ConsistentRead=false -> may see old state.
GetItem key K with ConsistentRead=true  -> check supported strong semantics.
``

Đối với read từ **base table và local secondary index (LSI)** trong region, API có thể hỗ trợ strongly consistent reads theo cấu hình. **Global secondary index (GSI)** có propagation bất đồng bộ và không hỗ trợ `ConsistentRead=true` cho query GSI.

### Java AWS SDK v2 — điểm khác biệt

```java
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.*;
import java.util.Map;

public final class DynamoStrongReadExample {
    public static GetItemResponse readByPrimaryKey(
            DynamoDbClient client, String id) {
        return client.getItem(
            GetItemRequest.builder()
                .tableName("ConsistencyCanaries")
                .key(Map.of(
                    "pk", AttributeValue.builder().s(id).build()
                ))
                .consistentRead(true)
                .build()
        );
    }
}
```

Đây chỉ là phần read; write đã ACK trước đó phải được thực hiện, và table key schema `pk` phải khớp. Kiểm tra `item()`, source revision và lỗi trong response. Không gửi `consistentRead(true)` cho GSI query rồi coi một exception là stale read.

### GSI read-after-write

```text
PutItem base table v11 ACK.
Query GSI by email/status -> may not yet include v11.
``

Nếu API yêu cầu trả bản ghi vừa tạo ngay sau khi write, có thể:

- Đọc theo base table primary key khi đã biết key.
- Dùng response của write để hiển thị trạng thái vừa thay đổi, kèm refresh policy.
- Dùng application read model/version gate.
- Thay đổi UX hoặc data model nếu GSI freshness bound không đáp ứng.

### Global tables và regional context

DynamoDB Global Tables có nhiều chế độ replication/consistency theo capability/configuration. **Không áp kết luận “mọi global table reads chỉ eventual” hoặc “mọi region đều strong” cho mọi cấu hình**. Trong thí nghiệm phải ghi regional endpoints, global-table mode, failover policy và precise read guarantee của chế độ đang dùng.

## 40. DynamoDB: test sau khi app client hoặc region đổi

Một bài cần tách:

```text
Writer client A -> region R1 -> PutItem ACK.
Reader client B -> region R1 -> ConsistentRead=true.

Writer client A -> region R1 -> PutItem ACK.
Reader client C -> region R2 -> configured read mode.
``

Hai bài **không đồng nghĩa**. RYW trong R1 với strong read không tự chứng minh same revision đã được replicate đến R2.

### Transactional reads

`TransactGetItems` có những bảo đảm đọc giao dịch theo API của DynamoDB trong phạm vi được hỗ trợ; không nên nhầm nó với tùy chọn strong read toàn cầu cho mọi index, region và downstream cache.

### Caching layer

Nếu ứng dụng có DAX/client cache, đường đọc qua cache có consistency/freshness semantics khác một direct table `GetItem`. Một test direct table PASS nhưng HTTP API FAIL có thể là stale cache.

### Test driver retry

Sau `PutItem` timeout, **đừng khẳng định write thất bại**. Với cùng item/version, dùng conditional put/update hoặc reconcile trước khi retry. Test RYW phải chỉ bắt đầu assertion sau acknowledged successful write, hoặc xử lý unknown state riêng.

## 41. Cassandra/ScyllaDB: consistency level quyết định đường đọc

Trong một datacenter RF=3:

```text
Replica A: new value v11
Replica B: new value v11
Replica C: old value v10
``

Nếu write đạt `LOCAL_QUORUM` hai replicas, read `ONE` có thể nhận replica C và thấy v10. Nếu read cần mạnh hơn, chọn read consistency thích hợp với replication topology.

### \(R+W>N\) là điều kiện giao nhau, không phải nhãn bảo đảm toàn diện

Ví dụ lý tưởng:

\[
N=3,\quad W=2,\quad R=2\Rightarrow R+W=4>N
\]

Giao giữa read/write quorums làm tăng khả năng read thấy write đã acknowledged theo protocol. Nhưng **không tự suy đầy đủ linearizability** trong mọi Cassandra deployment; phải xét timestamp resolution, last-write-wins, concurrent writes, hinted handoff, read repair, topology changes, write timeout/unknown outcomes và scope một datacenter.

### Test cần phân biệt

1. `WRITE ONE + READ ONE`.
2. `WRITE LOCAL_QUORUM + READ ONE`.
3. `WRITE LOCAL_QUORUM + READ LOCAL_QUORUM`.
4. Multi-DC với `LOCAL_QUORUM` ở các DC khác nhau.
5. Read/write dùng conditional operations (LWT) so với normal writes.
6. Replica C bị delay, sau đó được phép catch up.

### LWT

Cassandra/ScyllaDB LWT/conditional statements có Paxos/serial consistency semantics riêng. Không suy mọi normal `UPDATE` trở thành linearizable chỉ vì một thao tác khác có `IF`. Kiểm thử theo **đúng câu CQL và consistency settings**.

### Clock/timestamp

Last-write-wins dựa timestamp có thể gây bất ngờ khi clients gán timestamps khác nhau. Oracle nên dùng source-side revision/operation identity đáng tin, không dùng `writetime()` như một global transaction number nếu không có điều kiện.

## 42. Redis: đọc primary khác đọc replica

Redis thường có primary và replicas đồng bộ **bất đồng bộ**. Trong ví dụ:

```text
SET profile:C1 "v11" on primary -> OK.
GET profile:C1 on primary       -> v11 (normal path).
GET profile:C1 on replica       -> possibly v10.
``

### Kiểm thử route

- Primary direct read sau write ACK.
- Replica read ngay sau ACK.
- Replica read sau replication delay.
- Read sau primary failover, replica promotion.
- Redis Cluster client chọn route/slot khác sau reconnect.
- Client-side cache tracking invalidation khi network drop.

### `WAIT` không tự tạo strong global consistency

Redis `WAIT` có thể yêu cầu một số replicas xác nhận đã nhận writes tới một offset theo connection context, nhưng **không biến Redis replication thành một consensus protocol bảo đảm mọi acknowledged write không mất sau mọi failover**. Cần phân biệt replication acknowledgment, persistence, failover selection và RPO.

### Cache và authorization

Nếu Redis là cache của permissions, stale allow có thể nghiêm trọng. Test:

```text
Source revoke role ADMIN -> ACK.
Redis entry still allows ADMIN.
API tries sensitive action -> ?
``

Không chấp nhận “eventual” như một lý do đủ để cho phép quyền đã thu hồi ngoài revocation contract. Có thể cần fail-closed/versioned cache, invalidation hoặc strong authority read cho actions nhạy cảm.

### TTL và stale cache

Một key cũ có thể còn theo TTL trong khi database đã có revision mới. Test end-to-end API phải đo cache-hit và stale response, không chỉ direct Redis replication.

## 43. Elasticsearch/OpenSearch: realtime GET và gần-realtime Search

Một index write được ACK:

```text
Index O1 revision 11 -> ACK.
GET O1 by _id             -> may see indexed write through realtime GET path.
SEARCH for O1             -> may still reflect old searchable view until refresh.
``

### Phân biệt hai APIs

- **Document GET**: thường có realtime semantics theo API/option, lấy document bằng ID.
- **Search**: dựa trên index searcher/refresh, thường có gần-realtime visibility.
- **Point-in-time search (PIT)**: giữ search view tại một mốc; có thể chủ ý trả snapshot cũ dù index đã nhận ghi mới.

Một bài chỉ dùng GET sau write không chứng minh ứng dụng dùng search sẽ thấy document.

### Tùy chọn refresh

Các write APIs có thể hỗ trợ `refresh=wait_for` để đợi refresh phù hợp giúp dữ liệu được search-visible theo phạm vi API. `refresh=true` có thể ép refresh và tạo chi phí đáng kể nếu dùng liên tục. Cần đo tác động latency/throughput, đặc biệt với bulk ingest.

### Test

```text
1. Index synthetic document revision 11.
2. Receive write acknowledgment.
3. Search through application alias -> revision ?
4. Repeat after refresh/with refresh wait.
5. Create PIT before write; compare PIT search to new search.
``

Nếu PIT được tạo trước write, đọc kết quả cũ bên trong PIT **không tự là bug**; đó là snapshot contract. Test phải định nghĩa thời điểm tạo PIT.

### Versioning

Optimistic concurrency có thể dùng `_seq_no`/`_primary_term` hoặc cơ chế version phù hợp API để ngăn stale overwrite. Nhưng source revision của business không phải mặc nhiên bằng Elasticsearch sequence number; khi CDC import cần mapping/version protocol rõ.

## 44. Azure Cosmos DB: session consistency và token

Azure Cosmos DB có các consistency levels gồm mô hình **Session** trong những API/điều kiện được hỗ trợ. Session consistency liên quan đến việc client thấy writes của mình và monotonic reads theo phạm vi causal/session contract.

### Sự khác biệt giữa SDK instance và người dùng

```text
Application pod A:
  Cosmos SDK client A
  write item K -> ACK / session token tracked
  read K -> sees own write

Application pod B:
  Cosmos SDK client B
  no session token transferred
  read K -> may behave differently
``

SDK có thể tự quản lý session tokens bên trong client instance, nhưng điều đó không đồng nghĩa token được chia sẻ giữa application pods/mobile devices.

### Test đúng

- Ghi rõ consistency level của account/request.
- Giữ same SDK client và logical partition key.
- Tạo SDK client mới không chuyển session token.
- Tạo SDK client mới có chuyển session token theo **API được hỗ trợ**.
- Test region preference/failover và token behavior.
- Test partition scope của token; không chuyển token sai logical partition.

### Không biến session token thành authorization

Session token hỗ trợ consistency, **không cấp quyền truy cập dữ liệu**. Authorization dựa identity/tenant policy riêng. Cần tránh log/export token tràn lan; khi truyền giữa service, áp validation và source scoping.

### Đừng suy từ tên “Session” rằng mọi yêu cầu xuyên region đều thành công tức thì

Khi replica/region chưa có dữ liệu cần thiết, read có thể phải route/wait hoặc thất bại theo deadline/availability. Kiểm tra contract thực tế của API và phiên bản, không cho phép stale response chỉ vì route khác region.

## 45. Neo4j: bookmarks khi đổi driver session

Trong Neo4j cluster, một write có thể được commit trên leader rồi một read session mới được route tới một reader chưa bắt kịp.

### Bookmark mang causal dependency

```text
Session S1:
  CREATE/UPDATE node N
  transaction commits
  obtain bookmark B

Session S2:
  open with bookmark B
  execute MATCH query
  expect required causal state to be visible
``

Driver bookmarks là cơ chế hỗ trợ causal chaining qua sessions theo API. Nếu S2 mở **không có bookmark** trong một topology cho phép follower đọc, nó có thể không giữ cùng causal boundary.

### Phân biệt transaction result và commit

Đọc result records trước khi write transaction commit không phải boundary đúng cho test. Chờ transaction successfully committed, lấy bookmark đúng, rồi mở read session.

### App nhiều HTTP requests

Một web user có thể gọi API lần 1 trên pod A (write) và lần 2 trên pod B (read). Nếu ứng dụng muốn RYW xuyên pods, phải chuyển bookmark/causal context hoặc dùng một route/consistency strategy khác. Không giả định Neo4j driver ở pod B tự biết bookmark của pod A.

### Graph-specific invariants

Một traversal có thể đọc nhiều nodes/relationships. Cần test:

- Node vừa tạo có thấy không?
- Relationship vừa tạo có được query không?
- Có đọc một graph snapshot hợp lệ theo transaction contract không?
- Session switch có bookmark/version đúng không?

Một lần `MATCH (n {id:...})` thấy node chưa chứng minh mọi multi-hop traversal luôn có snapshot consistency tương đương.

## 46. Couchbase: KV GET và query qua index

Couchbase có đường đọc key-value và truy vấn SQL++/index, vì thế một mutation thành công không nhất thiết đồng nghĩa **mọi index query ngay lập tức** nhìn thấy thay đổi.

### Hai đường thử

```text
Upsert KV document K revision 11 -> ACK.
KV GET K -> verify document.

SQL++ SELECT ... WHERE secondary_indexed_field=...
     -> may see earlier index state depending on scan consistency.
``

### Các lựa chọn liên quan

Các query options như `request_plus` hoặc `at_plus`/`consistentWith` theo SDK/server API có thể yêu cầu index đạt một mốc nhất định, thay vì chỉ dùng scan consistency mặc định. Với `at_plus`, cần mutation tokens/state phù hợp từ writes trước đó.

### Test

1. Tạo synthetic document có indexed field.
2. Ghi nhận mutation token/result.
3. Chạy KV GET.
4. Chạy query với scan consistency mặc định.
5. Chạy query với mutation-consistent strategy được hỗ trợ.
6. Đổi SDK session/connection rồi kiểm tra token propagation.

Đừng lấy kết quả KV GET PASS để tuyên bố query/index read-after-write cũng PASS. Tính khả dụng của cơ chế và syntax phụ thuộc API/SDK version.

## 47. So sánh lựa chọn theo từng NoSQL

| Hệ / đường đọc | Có thể đọc cũ sau ACK? | Mechanism cần kiểm thử | Không được suy |
|---|---|---|---|
| MongoDB secondary | Có tùy read concern/session | Causal session, majority concerns, route | Mọi majority read tự RYW qua session reset |
| DynamoDB base table eventual | Có | `ConsistentRead` khi hỗ trợ | Strong ở base table tự làm GSI strong |
| DynamoDB GSI | Có vì async projection | Index freshness/model khác | `ConsistentRead=true` dùng được cho GSI |
| Cassandra `ONE` | Có thể | W/R CL và replica placement | `LOCAL_QUORUM` là global linearizability |
| Redis replica | Có vì async replication | Primary route, replica offset, failover | `WAIT` là consensus/durability toàn cục |
| Elasticsearch Search | Có thể trước refresh | Refresh strategy/PIT/index visibility | GET và Search có cùng read semantics |
| Cosmos DB Session | Phụ thuộc token/partition/client scope | SDK session token propagation | Login cookie tự chuyển session token |
| Neo4j follower read | Có thể nếu không truyền causal marker | Bookmarks | Cùng user nghĩa same driver session |
| Couchbase SQL++ index | Có thể do index lag | Scan consistency/mutation token | KV GET PASS đủ cho query parity |

Không dùng bảng này thay tài liệu phiên bản cụ thể. Mỗi hàng giả định một route/operation/setting; datastore và SDK có thể thay đổi capabilities.

## 48. Test với cache: dữ liệu gốc mới, cache vẫn cũ

Một service:

```text
POST /profile:
  MongoDB update profile revision 11 -> ACK

GET /profile:
  Redis cache key profile:T01:C01 -> revision 10
``

Nếu API hứa RYW trong login session, việc core MongoDB causal reads PASS vẫn chưa đủ.

### Biện pháp 1 — Invalidate cache sau write

```text
write source -> invalidate cache -> next read miss -> source
``

Nhưng nếu invalidation thất bại, retry hoặc concurrent write về cache từ reader cũ, stale entry có thể xuất hiện lại.

### Biện pháp 2 — Versioned cache

Cache value:

```json
{
  "revision": 10,
  "payload": "old profile"
}
``

Request mang minimum revision 11, cache hit v10 phải **không được trả cho client**. Service có thể bypass cache, đợi source/index bắt kịp hoặc trả lỗi theo deadline nếu không có dữ liệu đủ mới.

### Biện pháp 3 — Write-through / transaction-aware update

Có thể cập nhật cache sau DB commit bằng version guard, nhưng đây vẫn là hai hệ có failure window; phải có reconciliation/invalidation và không xem chúng atomic nếu không có protocol.

### Test race quan trọng

```text
T0 Reader R loads source revision 10.
T1 Writer updates source to revision 11 and cache to v11.
T2 Reader R writes its old revision 10 into cache.
T3 User read -> v10.
``

Nếu cache SET unconditional, **cache regression** xảy ra. Cần conditional version comparison, invalidate-after-fill strategy hoặc không cache giá trị cũ qua watermark.

## 49. Test read model/CDC: source đã ACK nhưng projection chưa bắt kịp

Pipeline:

```text
Orders NoSQL source
     |
     v
CDC connector -> stream broker -> consumer -> search index
                                             |
                                             v
                                          API read
``

Sau write source revision 11:

- Connector có thể chưa đọc source log.
- Broker có thể đã nhận event nhưng consumer chưa áp.
- Consumer có thể checkpoint trước khi sink search-visible.
- Search index có thể đã index nhưng chưa refresh.
- Cache trước search vẫn giữ kết quả cũ.

### Cần nhiều mốc

| Mốc | Chứng minh |
|---|---|
| Source write ACK | Source operation đạt write contract |
| Connector checkpoint | Reader đã xử lý/nhận log position nào |
| Broker published offset | Event vào broker theo publisher contract |
| Consumer sink checkpoint | Consumer đã ghi bền state nào |
| Search-visible revision | Query thực sự thấy revision |
| Application response | User nhận state phù hợp |

### Không chỉ hỏi “consumer lag = 0?”

Offset lag bằng 0 có thể xuất hiện khi source connector đã ngừng publish hoặc sink refresh chưa xong. Test RYW qua read model phải đo **source commit đến visible query**, không chỉ Kafka offset.

### Reconnect consumer và duplicate events

Nếu consumer xử lý cùng update v11 hai lần sau restart, application query vẫn phải đúng. Nhưng nếu delta-only event có side effect, duplicate replay có thể phá state. Có version guard/idempotent sink/ledger khi cần.

## 50. Có thể áp RYW trong ứng dụng như thế nào?

Không có một giải pháp tối ưu chung:

| Biện pháp | Ưu điểm | Giá phải trả |
|---|---|---|
| Route đọc tới leader/primary | Mô hình dễ hiểu nếu source hỗ trợ | Tăng tải leader, không giải quyết cache nếu vẫn đọc cache |
| Strong read theo API | Đọc đúng hơn trong phạm vi hỗ trợ | Latency/throughput/cost và availability khi không đạt quorum |
| Causal session token/bookmark | Chỉ đòi replica tối thiểu bắt kịp | Context propagation/lifecycle |
| Application minimum revision | Scope theo user/entity, áp được qua layers | Cần version authority và fallback |
| Sticky session/route | Giảm đổi replica đột ngột | Không bền qua failover/restart; hotspot |
| Cache version gate | Ngăn trả stale cache khi biết minimum | Metadata/cache invalidation complexity |
| Read-back response from write | UI hiển thị state vừa ghi ngay | Lần GET tiếp theo vẫn cần consistency |
| Await projection catch-up | RYW ở search/read model nếu đợi đúng mốc | Tăng latency, timeout cần xử lý |
| Async/pending UI | Phù hợp eventual consistency business | Không được nói “đã commit search-ready” khi chưa |

### Chọn theo dữ liệu

- **Profile:** thường cần RYW khi người dùng sửa rồi mở lại.
- **Tồn kho/đặt chỗ:** có thể cần strong consistency/conditional write.
- **Search index:** cho phép độ trễ đã công bố, nhưng nên hiển thị trạng thái cập nhật.
- **User permissions:** stale allow có thể không được phép; nên fail-closed theo revocation contract.
- **Analytics:** eventual freshness có thể đủ nếu báo rõ mốc dữ liệu.

Kiểm thử phải phản ánh **business intent và nguy cơ**, không áp linearizability lên mọi request để rồi tạo chi phí không cần thiết.

## 51. Application-level minimum revision qua HTTP requests

Giả sử hai HTTP requests của cùng user được phục vụ bởi hai app pods khác nhau:

```text
Client browser
  |
  | PATCH /profile
  v
Pod A -> DB write rev 11 -> ACK
  |
  | Response: ETag: "rev-11"
  v
Browser stores min required rev 11
  |
  | GET /profile
  | If-Required-Revision: 11 (illustrative application header)
  v
Pod B -> cache rev10 -> reject cache
      -> source/replica rev11 -> response
``

Ở đây `If-Required-Revision` chỉ là **header tự thiết kế để minh họa**, không phải chuẩn HTTP hoặc capability của mọi NoSQL.

### Giao thức hợp lệ cần định nghĩa

1. Server tạo revision có thứ tự hợp lệ cho entity.
2. Sau write ACK, response mang revision/opaque context tương ứng.
3. Client lưu minimum revision theo entity/tenant và session lifetime.
4. Request kế tiếp chuyển minimum revision bằng kênh xác thực.
5. Backend không trả bản cũ hơn minimum.
6. Nếu không có bản đủ mới trong deadline, trả **một response có nghĩa rõ** (timeout, retryable, pending...) thay vì v10.

### Không dùng token thay authentication

Một header có revision số 999999999 có thể khiến app đợi vô hạn. Server cần validate scope, source identity, reasonable bounds và quyền, hoặc dùng opaque/signed token nếu threat model đòi. Revision metadata không cấp quyền đọc entity người khác.

### Browser/mobile session khác driver session

Khi user mở tab khác hay chuyển device, application phải quyết định token có được lưu/đồng bộ không. Nếu contract là “chỉ trên thiết bị hiện tại”, cần nói rõ; nếu hứa “mọi thiết bị sau save đều thấy mới”, cần strong read hoặc propagation mechanism thích hợp.

## 52. Java 17: version gate trước khi trả cached response

Một ví dụ ứng dụng:

```java
import java.time.Duration;

record VersionedProfile(
    String id,
    long revision,
    String displayName
) {}

interface VersionedProfileRepository {
    VersionedProfile readFromCache(String id);
    VersionedProfile readFromAuthority(
        String id, Duration deadline);
}

public final class VersionGatedProfileReader {
    private final VersionedProfileRepository repository;

    public VersionGatedProfileReader(
            VersionedProfileRepository repository) {
        this.repository = repository;
    }

    public VersionedProfile read(
            String verifiedId,
            long requiredRevision,
            Duration deadline) {

        if (requiredRevision < 0
                || deadline.isNegative()
                || deadline.isZero()) {
            throw new IllegalArgumentException(
                "invalid consistency requirement");
        }

        VersionedProfile cached =
            repository.readFromCache(verifiedId);

        if (cached != null
                && cached.revision() >= requiredRevision) {
            return cached;
        }

        VersionedProfile source =
            repository.readFromAuthority(verifiedId, deadline);

        if (source == null ||
                source.revision() < requiredRevision) {
            throw new IllegalStateException(
                "required revision not available");
        }
        return source;
    }
}
```

### Giới hạn quan trọng

- `verifiedId` phải lấy từ **authorization-scoped route**; code không tự kiểm tra tenant.
- `readFromAuthority` phải có source read mode đáp ứng contract; nếu nó cũng là eventual replica không đủ mới, fallback chưa giải quyết gì.
- `revision>=requiredRevision` chỉ đáng tin nếu phiên bản so sánh được và không có nguồn khác cấp version không tương thích.
- Nếu record đã bị xóa tại revision mới, cần mô hình `tombstone/DeletedResult`, không dùng null mơ hồ.
- Production không nên dùng `IllegalStateException` làm HTTP policy: cần error mapping, bounded wait/retry, metrics và response semantics có chủ đích.
- Một cache trả revision rất cao nhưng payload sai vẫn vi phạm correctness; nên kiểm tra data model/validation.

### Version gate không tự tăng durability

Nếu source đã ACK v11 nhưng sau failover authoritative state rollback về v10, gate sẽ **không trả v10** và có thể timeout. Nó giúp tránh stale response, nhưng không thể tạo lại data đã mất; cần durability/quorum contract và recovery.

## 53. Sticky session: dễ áp dụng nhưng không phải bảo đảm bền

Một load balancer có thể cố route một user tới cùng app pod hoặc một service có thể ưu tiên cùng replica trong một thời gian:

```text
User U -> App pod A -> Replica R1
``

Nếu R1 đã nhìn thấy revision 11, các reads liên tiếp có thể dễ giữ monotonicity hơn.

Nhưng sticky routing thất bại khi:

- Pod A restart.
- R1 bị failover/đổi shard.
- Người dùng đổi thiết bị/region.
- Session cookie hết hạn.
- Pool connection bị thay.
- Cache entry trên pod khác cũ.

### Test phải cố ý phá stickiness

Một giải pháp chỉ PASS khi giữ pod cố định không đáp ứng yêu cầu **RYW across reconnect**. Nếu business chỉ cam kết RYW trong một session gắn route, ghi scope đó trong product contract và kiểm thử lỗi khi route mất.

### Không dùng stickiness thay invariant

Một request payment hoặc permission check không thể dựa vào sticky session để bảo đảm tính đúng của global state. Dùng authoritative conditional operations/consistency phù hợp.

## 54. Concurrent writes làm test dễ báo sai

Hai writers:

```text
A: read rev 10
B: read rev 10
A: write rev 11 status=PAID   -> ACK
B: write rev 11 status=FAILED -> ACK
A: read -> FAILED rev 11
``

Nếu revision do client tự tăng, **hai trạng thái khác nhau có cùng số 11**. Oracle `readRevision>=ackRevision` sẽ PASS sai.

### Cần bảo vệ write

- Conditional update `WHERE version=10` để chỉ một writer thắng và tạo revision 11.
- Server-generated sequence/etag/CAS semantics.
- Unique event IDs và causal parent references.
- Conflict resolution được công bố khi có multi-master.

### Test setup

Ở bài RYW đơn giản, dùng single-writer unique key. Ở bài concurrent correctness, dùng một lịch sử đầy đủ và assert theo legal outcomes/invariants.

Đừng gọi test concurrent correctness là test read-your-writes thuần túy; nó chạm đến lost updates, conflicts và atomicity.

## 55. Kiểm thử causal chain qua nhiều services

Một business flow:

```text
Service A writes Order O1 revision 11.
    |
    v
Service B receives event OrderUpdated(rev11).
    |
    v
Service B reads Order O1.
    |
    v
Service B creates ShippingTask linked to rev11.
``

Nếu B đọc replica v10, rồi phát shipping task dựa old shipping address, nó đã vi phạm yêu cầu **writes-follow-reads/causal dependency** của business flow.

### Test

1. Service A commit v11 và publish durable event với operation ID/revision.
2. Đảm bảo service B nhận event theo workflow.
3. Chặn replica B ở v10 trong lab.
4. B thực hiện read theo consistency context cần thiết.
5. Kiểm tra task không được commit dựa v10 khi event đã chỉ rõ v11.

### Giải pháp

- Mang minimum revision/causal token trong event metadata.
- Đọc source/replica đủ mới theo version gate.
- Chờ propagation hoặc fail/retry bounded.
- Nếu event đã có đầy đủ dữ liệu cần thiết và được authorize, xử lý state từ event theo revision contract để tránh read-back không cần thiết.

### Phân biệt event order và state order

Broker offset order trong một partition không tự là global source order của mọi entities/partitions. Chọn keying/ordering/causal metadata phù hợp.

## 56. Transaction snapshot có thể cố tình đọc state cũ

Một transaction/snapshot bắt đầu trước write:

```text
T0: Transaction R begins at snapshot rev10.
T1: Another session commits rev11.
T2: R reads object -> rev10.
``

Nếu transaction R dùng snapshot isolation, việc thấy rev10 có thể **đúng** theo snapshot của nó. Không thể lấy điều kiện “read invocation ở T2” rồi đánh giá như một fresh read độc lập nếu transaction context đã cố định T0.

### Test phải ghi mốc snapshot

- Transaction bắt đầu khi nào?
- Read timestamp/snapshot boundary?
- Write có xảy ra trong **cùng transaction** không?
- Transaction đã commit/abort?
- Read concern trong/outside transaction?

### “Read own uncommitted write”

Đọc những writes trong **cùng transaction trước commit** là một khả năng transaction visibility khác với read-after-write **sau một ACK committed write**. Không đánh đồng hai thuộc tính.

### Client pool reuse

Nếu Java code vô tình giữ transaction context/snapshot cũ qua nhiều requests, có thể liên tục trả state cũ. Khi debug stale reads, kiểm tra transaction lifecycle chứ không chỉ replication lag.

## 57. Cross-region failover và session context

Một tình huống:

```text
R1 write rev11 ACK.
Region router fails over client to R2.
R2 read returns rev10.
``

Phải trả lời:

1. Source replication cross-region đồng bộ hay bất đồng bộ?
2. R1 ACK bảo đảm điều gì về R2?
3. Session token có ý nghĩa ở R2 không?
4. R2 hỗ trợ chờ/routing/fail theo minimum revision không?
5. RPO và read freshness contract khi failover là bao nhiêu?
6. Có dual-primary/conflict resolution khiến revisions không so sánh tuyến tính được không?

### Không sửa bằng cách đổi consistency level tùy tiện

Một region có thể chưa nhận write dù local read ở R2 là strong **trong region đó**. Strong local read không tự đưa dữ liệu từ R1 sang R2.

### Test failover

- Ghi v11 tại R1, nhận ACK.
- Ghi nhận regional replication position.
- Gây mất route R1 trong môi trường được phê duyệt.
- Đọc tại R2 với documented semantics.
- Reconnect và xác minh token handling.
- Kiểm tra durability/invariant sau failback.

Kết luận phải chia riêng **regional RYW, cross-region visibility, failover RPO và session portability**.

## 58. Network partition: stale read có thể là degraded mode hợp lệ

Trong partition:

```text
Minority side:
  local replica last visible rev10

Majority side:
  write rev11 committed
``

Một API catalog có thể **cho phép trả rev10** trong thời gian ngắn theo freshness budget, nhưng API xác minh payment/authorization có thể phải từ chối nếu không thể đảm bảo revision tối thiểu.

### Test an toàn

- Dùng synthetic records, test namespace, fault injector có TTL và kill switch.
- Cấu hình client ở cả majority và minority.
- Đo responses: fresh, stale within allowance, stale beyond allowance, timeout/error.
- Không tự coi “có HTTP 200” là business success.
- Sau reconnect, kiểm tra stale regression và trạng thái cuối.

### Một hệ phải chọn đánh đổi

Không thể hứa arbitrary minority partition luôn trả strong writes/reads hợp lệ cho mọi dữ liệu khi không có communication/quorum cần thiết. Hãy thiết kế **degraded read-only/stale mode hoặc fail-closed** theo business contract.

## 59. Failover của cache và session-level stale regression

Một lịch sử:

```text
T0 Redis primary holds profile rev11.
T1 Client reads rev11.
T2 Primary fails before replica applies last change.
T3 Replica promoted with rev10.
T4 Client reads rev10.
``

Nếu Redis là cache, ứng dụng có thể bỏ bản cũ và đọc database authority. Nếu Redis là source of truth cho session state, phải đánh giá durability/RPO của mode Redis đó.

### Test gì?

- Replica lag trước failover.
- Client routing sau promotion.
- Cache invalidation và generation.
- Minimum revision propagation từ lần read trước.
- Có data loss/counter regression trên source hay chỉ cache?

Không nhầm cache “chưa kịp” với database source mất acknowledged write, dù cả hai đều có thể tạo stale response ở API.

## 60. Kiểm thử thời điểm mất session context

Một số sự kiện ứng dụng có thể khiến context biến mất:

- JWT refresh hoặc đổi authentication session.
- HTTP gateway restart.
- Microservice pod rollout.
- Mobile app process killed/backgrounded.
- Websocket reconnect.
- Database driver/client recreation.
- Load balancer cookie reset.
- Circuit breaker đổi route.
- Session store TTL expiry.

### Ma trận

| Sự kiện | Same user? | Same DB session? | Context cần giữ? |
|---|---|---|---|
| New TCP socket | Có | Có thể | Có, nếu DB API hỗ trợ trong same logical session |
| New HTTP request | Có | Có thể không | Nếu app hứa RYW across requests |
| JVM restart | Có | Thường không | Cần external/app token strategy |
| New phone | Có | Không | Nếu contract xuyên thiết bị |
| User logs out/in | Cùng account | Session mới | Tùy app contract, phải công bố rõ |
| Region failover | Có | Có thể khác | Cần regional replication/causal protocol |

Mỗi hàng là **một test scenario**, không phải lời hứa tự động từ NoSQL.

## 61. Test stale data và authorization revocation

Một flow:

```text
T0 User U has ADMIN permission rev10.
T1 Admin revokes ADMIN; source permission rev11 ACK.
T2 Service B reads stale rev10.
T3 Service B authorizes sensitive write.
``

Nếu security contract yêu cầu revocation áp dụng ngay hoặc trong bound ngắn hơn, stale read ở T2 dẫn đến **vi phạm bảo mật**, không chỉ trải nghiệm khó chịu.

### Kiểm thử

1. Tạo user/role synthetic trong lab.
2. Ghi permission rev11 (revoke) bằng authority.
3. Buộc cache/replica chậm.
4. Gửi request nhạy cảm từ session/connection mới.
5. Kiểm tra action bị từ chối nếu không có state đủ mới.
6. Ghi evidence nhưng không dùng quyền/admin thật.

### Biện pháp

Versioned policy epoch, fail-closed, short authoritative check cho operation critical hoặc token revocation strategy phù hợp. **Không để stale-while-revalidate cho authorization allow** nếu policy không chấp nhận.

## 62. Test stale data ở pagination và nhiều reads liên tiếp

Một client đọc trang 1 từ replica A ở revision 11 và trang 2 từ replica B ở revision 10:

```text
Page 1: sort snapshot S11
Page 2: sort snapshot S10
``

Có thể:

- Duplicate items giữa hai trang.
- Missing items.
- Thứ tự sort lệch.
- Read-your-writes của một entity xuất hiện ở trang trước nhưng mất ở trang sau.

### Một test khác với RYW đơn key

Đọc nhiều trang cần snapshot/PIT/cursor/continuation semantics phù hợp; **session RYW per key** không tự tạo globally consistent pagination snapshot.

### Test

- Lưu exact query/filter/sort và session token.
- Dùng unique tie-breaker key.
- Ghi snapshot/PIT boundary.
- Đổi physical route giữa pages (nếu API cho phép).
- Assert không duplicate/missing theo expected snapshot set.

Không dùng offset pagination trên dataset liên tục chèn/xóa rồi đổ mọi lỗi missing/duplicate cho replica consistency.

## 63. Đừng đo freshness bằng giờ client không đáng tin

Nếu mobile device chạy nhanh 3 phút, server A chậm 1 phút, server B chuẩn:

```text
Client timestamp: 10:03
Source commit timestamp: 09:59
Read response timestamp: 10:00
``

Độ lệch có thể do clocks, không chỉ replica lag. Với correctness test, ưu tiên:

- Source revision/sequence/operation ID có authority.
- Causal token/bookmark.
- Monotonic elapsed time đo tại một process.
- Server-side metric position khi có.
- Error bounds cho đo time across systems.

Nếu buộc dùng cross-host wall-clock, ghi clock sync status và uncertainty; đừng lấy phép trừ timestamps làm bằng chứng tuyệt đối của stale age.

## 64. False positives trong test RYW

Những lỗi thiết lập:

1. Write trả timeout nhưng test coi là ACK.
2. Concurrent writer ghi v12 rồi oracle đòi chính xác v11.
3. Read transaction mở snapshot trước write.
4. Source key bị delete/recreate, revision reset.
5. Test đọc sai tenant/partition/region.
6. Lấy response từ cache thay vì route được ghi trong test.
7. Token/session object không được truyền đúng.
8. Không đợi async write future hoàn thành.
9. So revision từ hai authorities không cùng order.
10. Driver retry ẩn làm thay đổi route mà test không ghi.

### Báo cáo khi không đủ evidence

Nếu không biết read thực sự đến replica nào, có thể kết luận “application read returned stale response”, nhưng không nên tuyên bố “replica B violated guarantee” mà không có route evidence.

## 65. False negatives trong test RYW

Những cách test có thể bỏ sót lỗi:

1. Luôn đọc primary, production lại đọc secondary.
2. Luôn reuse same JVM/driver session.
3. Sleep 5 giây trước mọi read nên không thấy transient stale.
4. Chỉ kiểm tra response `200`, không kiểm revision/payload.
5. Dùng unique key nhưng chỉ test insert, không test delete.
6. Không ép reconnect, rollover hoặc failover.
7. Chỉ đo trung bình, không nhìn p99/max.
8. Dừng ngay khi thấy v11, không kiểm monotonic regression.
9. Chạy khi traffic thấp, replica luôn bắt kịp.
10. Dùng một source record luôn cache hot và hit từ app-local state.

### Sửa

Đưa **route/session perturbation, replica lag injection, cache controls và workload concurrency** vào test plan. Giữ một vài happy-path tests nhưng không coi chúng đủ chứng minh production contract.

## 66. Fault injection: cố ý làm replica chậm trong lab

Một test chỉ chạy khi replica lag ≈0 thường khó phát hiện behavior trong production. Trong môi trường được phê duyệt có thể:

- Pause/delay replication apply của một test replica (theo công cụ chính thức).
- Tăng inter-node network latency hoặc packet loss với scope hẹp.
- Thay read preference/route tới replica có lag đã biết.
- Thay connection pool/session giữa write và read.
- Failover leader khi write ACK xong, trước read.
- Tạm disconnect cache invalidation stream.
- Chặn CDC consumer để tạo search freshness lag.

### Thí nghiệm minh họa

```text
Steady state: 3 replicas, synthetic tenant.
T0: Hold replica C at revision 10.
T1: Write revision 11 through legal primary route -> ACK.
T2: Read from replica C without causal context -> observe.
T3: Read from replica C with required context -> observe.
T4: Release replication hold; measure convergence.
``

### Thế nào là kết quả tốt?

- Test không có guarantee RYW trên C có thể trả v10; harness nhận diện stale chính xác.
- Test có causal requirement **không trả v10**; có thể wait/timeout theo API.
- Sau khi release, C hội tụ; thời gian đến visibility được đo.
- Session route/metadata trong lịch sử thí nghiệm khớp fault scope.

### An toàn

Chỉ chạy trên synthetic data hoặc môi trường được phê duyệt, có TTL/kill switch/abort criteria. Không tắt replication hoặc làm mất AZ production chỉ để thử một assertion RYW đơn key.

## 67. Test failover giữa ACK và READ

Kịch bản:

```text
Writer         Primary A         Replica B/C
  |-- v11 write --->|
  |<-- ACK ---------|
  |                [A becomes unavailable]
  |                [new leader elected]
  |-- read v11 via new route ------------> ?
``

### Bốn kết quả khác nhau

1. New leader trả v11 → PASS theo observed read, cần kiểm durability lâu hơn nếu goal có RPO.
2. New leader trả v10 → stale; đánh giá write durability/concern, session propagation, routing.
3. Read timeout → availability/latency failure; không đánh đồng stale value.
4. Write ACK thực tế ambiguous → không đủ để assert “mất ACKed write”; cần reconcile.

### Data integrity check

Sau hồi phục, kiểm tra source authoritative record bằng đúng consistency settings; đọc từ một stale replica đơn lẻ không chứng minh dữ liệu đã mất.

### Những thứ không được làm trong runbook

- Tự giảm write concern/durability để có câu trả lời nhanh.
- Retry non-idempotent payments/orders với new operation IDs sau timeout.
- Force leader cũ quay lại mà không có fencing/consensus protocol.

## 68. Điều tra một stale response ở production

Một người báo “đã đổi email nhưng vẫn thấy email cũ”:

```text
Step 1: Identify exact request and tenant-scoped entity.
   |
   v
Step 2: Verify write outcome and source revision.
   |
   v
Step 3: Trace GET route: cache / read replica / search / app state.
   |
   v
Step 4: Compare observed revision with required minimum.
   |
   v
Step 5: Check session context and connection changes.
   |
   v
Step 6: Inspect replica/CDC/cache lag and recent failover.
   |
   v
Step 7: Mitigate safely and verify user-visible contract.
``

### Triage cụ thể

| Bằng chứng | Giả thuyết ưu tiên |
|---|---|
| Source primary v11, Redis cached v10 | Invalidation/version gate lỗi |
| Source primary v11, secondary v10 | Replication lag/read preference |
| Same driver session PASS, new pod FAIL | Session context không được lan truyền |
| Direct DB PASS, search API FAIL | CDC/index refresh/read model lag |
| Source sau failover chỉ có v10 | Write ACK/durability, rollback hoặc identity |
| Source v12 hợp lệ, app trả status khác v11 | Concurrent update; cần oracle theo revision |
| Client UI v10, HTTP API v11 | Client-side cache/offline state |
| Read timeout with causal token | Replica chưa đáp ứng causal boundary hoặc routing/unavailability |

### Không điều tra bằng raw PII trong log

Sử dụng synthetic reproduction, redacted IDs, trace IDs được cấp quyền và per-key version metadata. Khi liên quan dữ liệu người dùng thật, chỉ xem fields tối thiểu theo incident/authorization policy.

## 69. Runbook sửa lỗi RYW theo lớp

### Lớp database

- Kiểm tra write/read concerns, read preference/CL, quorum/replica placement.
- Xem driver/topology/retry settings.
- Kiểm tra source revision hoặc commit position đã được ACK.
- Nếu cần RYW, dùng supported causal session/strong read hoặc target version condition.

### Lớp application

- Mang minimum revision/causal token qua HTTP/message boundaries.
- Giới hạn scope token theo user/tenant/entity.
- Không tự so sánh version từ sources khác nhau.
- Nếu reader chưa đủ mới, bounded retry/fallback hoặc trả error/pending rõ nghĩa.

### Lớp cache/search

- Invalidate hoặc version-gate cache.
- Chọn source-of-truth read cho thao tác critical.
- Dùng refresh/visibility token hoặc đợi projection phù hợp.
- Đo source-to-visible lag.

### Lớp vận hành

- Không suppress stale-read alerts bằng broad silence.
- Ghi runbook owner/SLO/budget.
- Có regression tests cho reconnect/failover.
- Kiểm tra resource impact của strong reads/causal waits.

### Recovery

Một fix chỉ được coi đủ khi:

1. Test oracle theo contract không còn thấy violation trong phạm vi đã thử.
2. Error/timeout/latency SLO không bị xấu ngoài budget.
3. Không tạo data duplication hoặc bypass authorization.
4. End-to-end API (không chỉ database direct) trả phiên bản phù hợp.

## 70. Tại sao “đổi tất cả đọc thành strong” chưa chắc là câu trả lời?

Một giải pháp nhanh:

```text
Read replica has occasional lag.
=> Force all reads to primary/strong mode.
``

Có thể giải quyết một số stale reads, nhưng:

- Tăng leader/quorum load và network cost.
- Read latency cao hơn nếu quorum unavailable.
- Global active-active consistency vẫn phụ thuộc regional replication protocol.
- Search/CDC/cache không tự được bảo vệ nếu application còn đi qua chúng.
- App có thể cần RYW **chỉ với user vừa ghi**; toàn bộ catalog reads không cần cùng chi phí.

### Cách tiếp cận theo nhu cầu

| Operation | Contract gợi ý để đánh giá |
|---|---|
| User xem profile ngay sau save | RYW trong logical user session |
| Public product listing | Bounded stale hoặc eventual freshness |
| Payment status | Không trả kết quả mâu thuẫn với acknowledged state |
| Permission check | Revocation-consistent/fail-closed |
| Search indexing | Source-to-visible freshness SLO |
| Analytics dashboard | Có thể dùng snapshot timestamp rõ ràng |

Không gán nhất loạt consistency level trước khi hiểu access patterns, SLO và correctness consequences.

## 71. Kịch bản test end-to-end cho web application

Ví dụ Java API có web login session, request A vào pod A, request B vào pod B:

```text
Preparation:
  create synthetic user and profile record rev 1

Write:
  PATCH /profile -> rev 2 acknowledged

Scenario 1:
  GET /profile through pod A -> rev ?

Scenario 2:
  GET /profile through pod B -> rev ?

Scenario 3:
  restart pod A, keep user session -> GET rev ?

Scenario 4:
  read with cache hit rev1 -> rev ?

Scenario 5:
  regional routing failover -> GET rev ?
``

### Dữ liệu phải thu

- HTTP request/response correlation IDs.
- Logical user session ID (redacted).
- Write ACK revision/operation ID.
- App pod identifier.
- Database/session/route mode.
- Cache hit/miss and cached revision.
- Read response revision/value hash.
- Time to first visibility, stale ratio, timeouts.

### Có thể dùng test harness HTTP bất kỳ

Không cần một công cụ cụ thể để chứng minh bài này. Quan trọng là **request sequence, route controls, oracle và evidence**. Nếu không thể ép pod/route một cách đáng tin, ghi thí nghiệm là không kết luận được cho trục đó.

## 72. Test matrix theo mức độ rủi ro của nghiệp vụ

| Nghiệp vụ | Same session | New session | Failover | Cache/read model | Ưu tiên |
|---|---|---|---|---|---|
| Profile update | Có | Có | Có | Có | UX + dữ liệu đúng |
| Change password/revoke access | Có | Có | Có | Có | Bảo mật, fail-closed |
| Order status after payment | Có | Có | Có | Có | Không mâu thuẫn với acknowledged effect |
| Inventory reservation | Có | Có | Có | Theo thiết kế | Bảo toàn invariant |
| Search product metadata | Có | Có | Có | Có | Freshness bound |
| Social feed like count | Có | Có | Có | Có | Có thể eventual nếu công bố |
| Analytics aggregate | Không nhất thiết RYW | Có snapshot timestamp | Theo RPO | Pipeline | Freshness SLA |

### Test theo impact

Không cần tạo mọi tổ hợp với hàng triệu requests trước khi có một test cơ bản. Bắt đầu với **một synthetic key, một ACK đáng tin, một read có revision**, sau đó tăng dần độ khó:

```text
same session
  -> physical reconnect
  -> logical session switch
  -> different app pod
  -> replica/cache route change
  -> failover/network partition
  -> multi-region and CDC projection
``

## 73. Cảnh báo và observability cho lỗi đọc cũ

Metrics gợi ý:

| Metric | Ý nghĩa |
|---|---|
| `ryw_check_total{result=pass|stale|error}` | Kết quả synthetic RYW probe |
| `minimum_revision_wait_seconds` | Thời gian chờ replica đủ mới |
| `read_revision_gap` | Khoảng cách version được quan sát trong test |
| `replication_applied_lag` | Replica lag theo source-specific metric |
| `cache_version_regression_total` | Cache ghi đè bằng version cũ |
| `cdc_source_to_visible_age_seconds` | Freshness của projection |
| `driver_server_selection_seconds` | Thời gian discovery/routing |
| `connection_reconnect_total` | Tần suất đổi connection |
| `session_context_missing_total` | Tỷ lệ request thiếu causal context khi cần |
| `read_timeout_total` | Availability cost khi chờ causal boundary |
| `write_outcome_unknown_total` | Writes chưa xác định, không nên dùng làm RYW assertion |

Đây là **metric names minh họa**, không phải metric sẵn của tất cả SDK.

### Labels không chứa dữ liệu nhạy cảm

Hợp lý: `service, region, route_class, consistency_mode, outcome`, các giá trị có cardinality giới hạn.

Không nên đặt vào metric labels: raw `userId`, `email`, `sessionToken`, `orderId`, raw query payload hoặc high-cardinality revision per request.

### Một alert có thể hành động

```text
[P2] Profile RYW synthetic probe failures after app-pod switch
Scope: prod / region R1 / profile-service
Observed: 3% stale values out of 1000 verified writes in last 10m
Owner: profile on-call
Runbook: trace cache version, session context and read routing
``

Ngưỡng giả định để minh họa. Với permission revocation/cross-tenant data exposure, **một confirmed violation** có thể cần xử lý ngay dù tỷ lệ thấp.

### Missing telemetry không phải PASS

Nếu probe chết vì region outage, không còn data point, không được coi result stale ratio = 0. Có no-data/heartbeat alert và blackbox test path độc lập khi cần.

## 74. Đánh giá hiệu năng đi cùng correctness

Một thay đổi:

```text
Before:
  stale responses 2%
  p99 read latency 80ms

After enabling causal waits:
  stale responses 0% (observed)
  p99 read latency 950ms
  read timeouts 3%
``

Không thể tuyên bố “đã thành công” chỉ vì stale về 0. Nếu user-facing SLO là p99 dưới 200ms và availability cao, giải pháp mới có vấn đề.

### Cần đo

- % reads RYW-pass under eligible post-ACK requests.
- % timeouts/errors.
- Tail latency, not just average.
- Replica lag distribution.
- Extra load/quorum capacity.
- Cross-region network egress.
- Consistency wait time.
- Business workflow completion.

### Dữ liệu dựa trên thí nghiệm

Ví dụ trên chỉ là số giả định; kết luận hiệu quả phải dựa trên **load và fault model thực tế**, không suy một consistency setting có chi phí cố định cho mọi workloads.

## 75. Báo cáo bài thử nên gắn với hypothesis

```text
Experiment ID: RYW-SWITCH-2026-11
Hypothesis:
  Within one web login session, writes acknowledged by
  profile API are visible to subsequent reads even when
  the next request is handled by a different app pod.

Source:
  synthetic profile P
  datastore/version/topology documented

Controls:
  no concurrent writer
  revision monotonic and authoritative
  write ACK verified
  new HTTP request after ACK
  pod route change confirmed

Observed (hypothetical):
  1000 verified writes
  1000 post-ACK reads
  7 stale reads from pod B cache
  12 read timeouts
  981 fresh reads

Verdict:
  FAIL RYW for specified app-level contract
  FAIL latency/availability separately for timed-out reads

Suspected cause:
  cache version gate absent on pod B

Action:
  introduce minimum-revision propagation and guarded cache reads
  replay the identical scenario after fix
``

Đây là **mẫu báo cáo giả định**, không phải kết quả đo thật. Không kết luận “datastore broken” nếu evidence cho thấy cache của ứng dụng mới là nơi trả stale.

## 76. Case study A: same-connection PASS, reconnect FAIL

### Bối cảnh

Ứng dụng lưu user profile trong MongoDB replica set. Đường write dùng primary, đường read dùng secondary. Trong một lần kiểm thử:

```text
T0: Write profile rev21 using S1 -> majority ACK
T1: Read rev21 within S1 -> PASS
T2: Close S1 and re-create driver session S2
T3: Route read to secondary -> rev20
T4: Wait 200 ms -> read rev21
``

### Phân tích

- Test same-session đã kiểm tra một causal path; không chứng minh session mới.
- Session S2 không có causal context đã được dùng.
- Secondary lag có thể giải thích một stale read ở T3.
- Nếu app contract là RYW xuyên HTTP requests/logical login session, T3 vi phạm.
- Nếu datastore API chỉ hứa causal RYW khi dùng đúng session context, T3 có thể là behavior ngoài guarantee.

### Sửa và test lại

1. Chọn contract application-level rõ.
2. Nếu cần RYW trên secondary, chuyển supported causal metadata hoặc dùng minimum-revision gate.
3. Không ép mọi query vào primary trước khi đo workload/latency.
4. Sau sửa, test same session, new session with context, new session without context và failover.

### Kết luận

**Session scope là một phần của contract**, không phải chi tiết implementation có thể bỏ qua.

## 77. Case study B: DynamoDB base table đúng nhưng GSI trả thiếu

### Bối cảnh

Một hệ đăng ký tài khoản:

```text
PutItem user U123, emailHash H -> ACK.
GetItem U123 from base table, strong read -> U123.
Query GSI by emailHash H immediately -> no matching items.
Query GSI after propagation -> U123.
``

### Phân tích

Query qua GSI không có cùng consistency contract với direct strongly consistent base table read. Test “GetItem PASS” chưa chứng minh “lookup by email via GSI PASS”.

### Những lựa chọn

- Trong request sau đăng ký, sử dụng ID từ write ACK và đọc base table.
- Kiểm tra uniqueness email bằng một **authoritative conditional claim**, không dựa vào GSI eventual query-then-insert.
- Nếu email lookup buộc phải lập tức thấy account, cân nhắc data model hoặc một authority khác phù hợp.
- Cho UI biết indexing/activation pending nếu business chấp nhận.

### Test tiếp

Stress concurrent signups cùng normalized email; GSI lag không được làm hệ tạo hai accounts khi business yêu cầu uniqueness. Đây là bài về invariant, rộng hơn RYW.

## 78. Case study C: hai lần đọc liên tiếp quay lùi

### Bối cảnh

```text
Replica R1 applied revision 45.
Replica R2 applied revision 43.

Session S:
  Read 1 routed R1 -> rev45.
  TCP reconnect.
  Read 2 routed R2 -> rev43.
``

### Phân tích

- Chưa cần write từ session S để nhận diện monotonic read violation.
- Connection change làm mất sticky route hoặc minimum revision tracking.
- Nếu ứng dụng chỉ hứa eventual reads, behavior có thể hợp lệ; nếu hứa monotonic reads trong logical session, không.

### Biện pháp

Minimum revision gate, supported session token hoặc route có khả năng đáp ứng at-least revision 45. Nếu không đạt trong deadline, trả lỗi/đợi có giới hạn thay vì trả 43.

### Test

Đưa lịch sử `45 → 43` vào oracle, phải được phát hiện. Đồng thời test `45 → 46` PASS và timeout không bị phân loại nhầm stale.

## 79. Case study D: CDC search index thấy xóa quá muộn

### Bối cảnh

Ứng dụng xóa đơn khỏi danh sách tìm kiếm:

```text
T0: Source delete order O1 at revision 18 -> ACK.
T1: API direct source GET O1 -> not found.
T2: Search index query returns O1 revision 17.
T3: CDC connector restarts.
T4: Search index eventually removes O1.
``

### Phân tích

Không phải mọi source write đều được search-visible ngay. Nhưng nếu xóa có ý nghĩa privacy/authorization, thời gian stale có thể không được phép.

### Kiểm thử

- Tạo synthetic delete, giữ tombstone/version.
- Đo source ACK đến index-visible deletion.
- Tạm chặn CDC trong lab để kiểm retention/catch-up.
- Kiểm query response và cache layers.
- Khi index restart, không cho replay cũ hồi sinh document.

### Mitigation

Nếu business yêu cầu không hiển thị O1 sau delete ACK, có thể cần query filter/fence theo authoritative deletion registry, chặn search result stale hoặc trì hoãn xác nhận xóa hoàn tất theo hợp đồng. **Không tự tuyên bố đã xóa khỏi mọi bản sao chỉ vì source trả 200**.

## 80. Case study E: read mới bị timeout thay vì trả stale

### Bối cảnh

Một session đã ghi revision 55. Sau đó đọc từ replica chưa bắt kịp với causal marker:

```text
Write rev55 -> ACK.
Read with min rev55 -> waits.
Read times out after 2s.
No stale response returned.
``

### Phân tích

Guarantee “không trả version cũ” có thể được duy trì, nhưng application **không đáp ứng read availability/latency**.

### Kiểm thử cần hai assertions

1. Safety: không có stale successful response.
2. Liveness: requests hoàn thành đúng hạn với tỷ lệ được cam kết.

Không tính timeout là “RYW PASS” rồi bỏ khỏi user-facing error budget. Nếu throughput cao khiến causal waits tích tụ, cần capacity/route strategy thay vì tăng timeout vô hạn.

## 81. Case study F: ACK chưa thực sự là ACK

### Bối cảnh

Ứng dụng gọi một async API:

```java
CompletableFuture<Void> future = submitWrite();
// Bug: tests mark write successful here, before future completes.
VersionedProfile p = readProfile();
``

Test thấy giá trị cũ và báo “NoSQL violates read-your-writes”.

### Phân tích

Write chưa hoàn tất nên không có quan hệ **write ACK precedes read invocation**. Lịch sử không chứng minh RYW violation.

### Sửa

Đợi future thực sự hoàn thành với confirmed commit outcome theo SDK contract. Nếu future bị timeout, ghi `UNKNOWN_WRITE_OUTCOME` và reconcile; đừng gán success.

### Bài học

Một test consistency mà không định nghĩa **success boundary** chính xác có thể tạo cả false positive và false negative.

## 82. Ba mươi bài tập thực hành

### Bài 1 — Nhận diện RYW violation

Client A ghi `X=1` và nhận successful ACK. Sau đó A đọc `X=0` trong cùng causal session. Guarantee nào bị vi phạm? Nếu A chỉ yêu cầu eventual read không có RYW contract, kết luận cần thay đổi thế nào?

### Bài 2 — Concurrent writer

A ghi `status=PAID` rev11, B sau đó ghi `status=CANCELED` rev12, A đọc rev12. Assertion “phải trả PAID” đúng hay sai? Viết assertion phù hợp khi revision là total order theo entity.

### Bài 3 — Monotonic reads

Một client đọc rev8, sau đó rev7 qua replica khác, chưa thực hiện write nào. Đây có phải RYW violation không? Tính chất nào mô tả chính xác hơn?

### Bài 4 — Linearizability

Write v11 từ client A hoàn tất trước khi read của client B bắt đầu. B đọc v10. Điều gì sai nếu object contract là linearizable? Vì sao điều này không tự vi phạm session-only guarantee khi B không có causal context?

### Bài 5 — Overlap

Write bắt đầu lúc T0, read bắt đầu T1, write ACK ở T2, read trả old ở T3 với T0<T1<T2<T3. Vì sao không được coi lịch sử này là bằng chứng chắc chắn vi phạm read-after-success?

### Bài 6 — ACK semantics

Một NoSQL ACK local primary trước replication. Primary mất ngay sau ACK. Hãy thiết kế hai tests: read visibility trong lúc primary sống và durability/RYW sau failover. Cần ghi những configuration nào?

### Bài 7 — Session scope

Web app dùng user cookie lâu 24 giờ; mỗi HTTP request tạo một MongoDB driver session mới. Có thể suy cùng user cookie => cùng causal session database không? Đề xuất application-level guarantee.

### Bài 8 — Physical reconnect

Viết kịch bản test khi driver socket bị đóng nhưng logical session được giữ. Bạn sẽ quan sát điều gì để chứng minh physical connection thực sự thay đổi mà causal context không bị mất?

### Bài 9 — Logical session reset

Giữ cùng SDK client nhưng đóng session S1 và tạo S2 không có causal token. Nếu S2 đọc old, cần ghi verdict như thế nào khi engine chỉ cam kết RYW trong S1?

### Bài 10 — Token propagation

S1 ghi revision 11, tạo token M; S2 nhận M và đọc. Thiết kế test xác nhận S2 không trả revision thấp hơn minimum, đồng thời xử lý timeout khi replica chưa bắt kịp.

### Bài 11 — Java async

Một chương trình gọi `sendWriteAsync()`, `sleep(100ms)`, rồi read. Vì sao không có causal order đáng tin? Viết lại bằng `CompletableFuture.thenCompose` và completion boundary.

### Bài 12 — MongoDB majority

Một test dùng write concern majority, read concern majority trên secondary, nhưng session được tạo mới không mang causal context. Có thể kết luận RYW qua session reset được bảo đảm không? Cần sửa thiết lập thử gì?

### Bài 13 — MongoDB read preference

Bạn đặt `secondaryPreferred` và test PASS 1.000 lần. Vì sao có thể thật ra mọi reads đã fallback tới primary? Cần thu route evidence nào?

### Bài 14 — DynamoDB GSI

`PutItem` ACK, `GetItem(ConsistentRead=true)` trả mới nhưng `Query GSI` chưa có item. Đây có nhất thiết là bug không? Có thể thiết kế lookup-on-signup nào khác để đáp ứng UX?

### Bài 15 — DynamoDB Global Tables

Một writer ghi region R1, reader đổi region R2. Liệt kê thông tin cần biết về global-table mode, read mode, replication và session/region routing trước khi đưa ra verdict.

### Bài 16 — Cassandra quorums

RF=3, W=2, R=1. Hai replicas đã ghi v11, replica thứ ba giữ v10. Read có thể thấy gì? Đổi R=2 sẽ thay đổi intersection trong mô hình lý tưởng như thế nào, và vì sao chưa đủ chứng minh linearizability toàn cục?

### Bài 17 — Cassandra LWT

So sánh write thường `UPDATE` với conditional `UPDATE ... IF version=10`. Test nào cần serial consistency, và vì sao không nên suy mọi writes tự mạnh như LWT?

### Bài 18 — Redis replica

`SET` ở primary thành công, reader ngay sau đó đọc replica cũ. Hãy thiết kế test cho primary read, replica read và failover. Vì sao lệnh `WAIT` không đồng nghĩa bảo đảm bền tuyệt đối sau mọi failover?

### Bài 19 — Elasticsearch refresh

Index document ACK, realtime GET đã thấy, Search chưa thấy. Giải thích khác biệt. Test `refresh=wait_for` và PIT tạo trước/ sau write sẽ cho những câu hỏi gì?

### Bài 20 — Neo4j bookmarks

Session S1 commit relationship, S2 đọc từ follower. Thiết kế test có/không có bookmark, ghi rõ bước chờ transaction commit và mục tiêu traversal.

### Bài 21 — Cosmos DB session

Một ứng dụng có hai SDK client instances ở hai pods. Pod A ghi, pod B đọc old. Tại sao cùng user ID chưa đủ? Thiết kế test session-token propagation theo logical partition.

### Bài 22 — Couchbase query

KV upsert thành công, SQL++ query qua index trả old. Nêu những scan consistency/mutation token mechanisms cần kiểm tra, và vì sao KV GET PASS không chứng minh query parity.

### Bài 23 — Cache version race

Reader R lấy v10, writer W ghi v11 và cập nhật cache, sau đó R ghi v10 vào cache. Đề xuất version guard/conditional fill để tránh stale regression.

### Bài 24 — Causal chain qua services

Service A ghi Order rev11 và publish event. Service B nhận event nhưng read source rev10 rồi tạo ShippingTask. Thiết kế causal token/minimum revision và fail-safe behavior để task không dùng state cũ.

### Bài 25 — Delete và privacy

Delete user record rev12 đã ACK, search index vẫn hiển thị rev11. Nếu yêu cầu bảo mật cấm lộ sau delete ACK, cần xử lý API/search/filter/revision như thế nào? Test nào xác nhận?

### Bài 26 — Transaction snapshot

Read transaction bắt đầu trước write rev11; nó trả rev10 sau khi writer ACK. Có thể coi đây là read-after-write violation của một fresh read không? Giải thích snapshot boundary.

### Bài 27 — Bounded staleness

Một ứng dụng hứa 99.9% updates search-visible trong 10 giây. Viết thí nghiệm đo time-to-first-visibility, missing/timeout samples và regression sau lần đầu thấy value mới.

### Bài 28 — Test report

Có 10.000 read attempts: 9.620 fresh, 230 stale, 120 timeout, 30 errors. Tính stale ratio trên completed reads và tổng non-fresh outcomes. Giải thích vì sao không bỏ timeout khỏi availability SLO.

### Bài 29 — Failover

Write rev99 ACK, primary chết, session chuyển sang region khác và read rev98. Hãy lập danh sách giả thuyết theo **durability, cross-region replication, session portability, routing và concurrent writer**; đề xuất bằng chứng để phân biệt.

### Bài 30 — Thiết kế tổng hợp

Thiết kế bộ kiểm thử cho hệ:

```text
Browser (same login across requests)
    |
    v
Java API (multiple pods)
    |
    +-- Redis cache
    |
    +-- MongoDB source + replicas
    |
    +-- CDC -> Kafka -> Elasticsearch read model
``

Bộ test phải gồm:

- RYW cùng driver session và sau session reset.
- New pod/client route và app-level causal context.
- Read from primary, secondary và stale Redis cache.
- CDC/search freshness và tombstone/delete handling.
- Bounded concurrency, revision oracle, single-writer và concurrent-writer cases.
- Failover/network partition test trong lab, abort criteria.
- Monotonic reads sau reconnect.
- Separate correctness, availability và latency verdicts.
- Evidence/metrics không chứa raw PII.
- Runbook sửa và chạy lại test sau thay đổi.

## 83. Checklist thiết kế và thực hiện test

### 83.1. Contract và source of truth

1. Tên guarantee chính xác: RYW, monotonic read, causal, bounded stale hay linearizable?
2. Phạm vi bảo đảm là key/partition/session/user/process/region nào?
3. SLO thời gian/availability/freshness có được định nghĩa không?
4. Source revision có authority, thứ tự và incarnation rõ?
5. Có concurrent writer làm oracle `value==expected` sai không?
6. Write ACK có nghĩa gì về concern/quorum/durability?
7. Nếu write outcome timeout/unknown, test có tách riêng không?
8. Read nằm trong transaction snapshot bắt đầu trước write không?
9. Test đang so source với source hay source với derived read model?
10. Business invariant nào phải kiểm tra ngoài revision?

### 83.2. Session, routing và data path

11. Driver session có được giữ đúng không? Có thread safety rule không?
12. Reconnect vật lý và reset logical session có được thử riêng?
13. Có test new SDK client/JVM/pod và cross-device khi application hứa?
14. Causal context/token/bookmark có được truyền đúng API?
15. Token có bị mất sau HTTP gateway/session store/region route không?
16. Test có thực sự đổi replica/node/region theo ý định?
17. Read concern/read preference/CL có được ghi rõ không?
18. Cache hit/miss và cached revision có quan sát được không?
19. GSI/search/CDC được phân biệt với base table/primary read không?
20. Có kiểm tra pagination/snapshot/PIT semantics khi đọc nhiều items không?

### 83.3. Lịch sử thao tác và oracle

21. Read invocation chỉ bắt đầu **sau write ACK** nếu test RYW?
22. Có dùng barrier/future thay cho sleep để tạo ordering không?
23. Có ghi operation IDs, session IDs, route và result classes?
24. Có phân biệt stale result, missing, timeout, authz error và unknown write?
25. Revision và payload/invariant đều được kiểm tra khi phù hợp?
26. Có test insert/update/delete và TTL/tombstone semantics?
27. Có negative control cố tình trả stale để kiểm tra oracle?
28. Có test monotonic regression sau khi đã thấy revision mới?
29. Có ghi time-to-visible và stale ratio kèm mẫu số/cửa sổ?
30. Có đánh dấu inconclusive khi route/source/token không xác minh được?

### 83.4. Sự cố, an toàn và vận hành

31. Có test replica lag/reconnect/leader failover trong môi trường được duyệt?
32. Fault injector có scope, timeout, abort/rollback controls?
33. Test không dùng payment/PII/thao tác production có tác động thật?
34. Có rate limit, cleanup/TTL và bounded concurrent probes?
35. Monitoring độc lập còn hoạt động khi fault domain lỗi?
36. Có đo lỗi/latency khi causal read phải chờ hoặc timeout?
37. Có phân tích session-loss khi app rollout/JVM restart?
38. Có test region failover với RPO và source revision reconciliation?
39. Có alert/metric cho stale responses, min-revision waits và telemetry loss?
40. Có owner/runbook, evidence và regression scenario sau khi sửa?

## 84. Những hiểu lầm thường gặp

| Hiểu lầm | Điều đúng hơn |
|---|---|
| “Write ACK rồi thì mọi replica đọc ngay sẽ thấy” | Phụ thuộc write concern, read concern, replication và route |
| “Một lần đọc primary PASS chứng minh RYW toàn hệ” | Chỉ chứng minh đường đã thử |
| “Same web login = same database session” | Không mặc định; app có thể tạo session khác ở mỗi request |
| “New TCP socket nghĩa causal context mất” | Driver session có thể giữ context qua socket thay đổi |
| “Same socket nghĩa causal session còn” | Không nhất thiết; logical session có lifecycle riêng |
| “Read trả đúng v11 mới là RYW” | Có thể trả valid newer v12 nếu concurrent write |
| “Revision lớn hơn luôn là mới hơn” | Phải là version cùng authority/order, tránh reset/conflicts |
| “Một timeout sau write nghĩa commit thất bại” | Remote commit có thể thành công, ACK mất |
| “Sleep 1 giây chứng minh ordering” | Phải đợi write completion/barrier |
| “Eventual read cũ là database bug” | Có thể là behavior được phép ngoài RYW contract |
| “Causal read chờ timeout là perfect availability” | Không trả stale nhưng latency/availability vẫn fail |
| “Quorum intersection đủ bảo đảm mọi linearizability” | Cần xét protocol, concurrency, topology và read/write settings |
| “MongoDB majority read tự giữ RYW sau đổi session” | Causal context/supported session protocol có thể cần |
| “DynamoDB strong GetItem làm GSI strong” | GSI có propagation/consistency semantics khác |
| “Redis WAIT là global transaction commit” | Replication ACK không đồng nghĩa consensus và durability mọi failover |
| “Elasticsearch GET và Search cùng visibility” | Search chịu refresh/PIT semantics |
| “Neo4j bookmarks chỉ là tracing metadata” | Bookmark được dùng trong causal chaining theo API |
| “Cosmos DB session tự theo một user qua mọi SDK instances” | Cần xét client-side token propagation/scope |
| “Cache invalidation luôn không race” | Reader cũ có thể ghi v10 đè cache v11 |
| “CDC lag=0 nghĩa API search RYW” | Còn connector, sink commit, refresh và cache |
| “Kết quả 0 stale trong 100 tests chứng minh không bao giờ stale” | Không đủ chứng minh toàn bộ interleavings |
| “Read-only snapshot cũ luôn là stale-read bug” | Snapshot contract có thể cho phép cố định mốc |
| “Sticky sessions giải quyết reconnect/failover” | Stickiness không tồn tại qua mọi topology change |
| “Đổi mọi read thành strong luôn là tối ưu” | Cần cân bằng correctness, latency, capacity và cost |

## 85. Kết luận

Để kiểm thử **đọc sau ghi, đọc dữ liệu cũ và thay đổi phiên kết nối** trong NoSQL, đừng chỉ viết:

```text
save(x)
assert read(x) == x
``

Một test có giá trị phải nói rõ:

1. **Write nào đã hoàn tất thành công**, bằng ACK/write concern nào?
2. **Read nào được bắt đầu sau đó**, trong session/connection/region/route nào?
3. **Guarantee nào đang được yêu cầu**, cho scope nào?
4. **Revision/causal boundary nào** định nghĩa “không cũ hơn”?
5. **Các kết quả khác nhau** — fresh, stale, timeout, unknown outcome — được phân loại thế nào?
6. **Session context được giữ hay mất** khi driver, JVM, app pod hoặc region thay đổi?
7. **Cache, replica, index, CDC và transaction snapshot** nằm ở đâu trong đường đọc?
8. **Khi failover hoặc replication lag**, hệ bảo vệ correctness bằng chờ, từ chối, fallback hay trả stale theo policy?
9. **Test có tái lập được không** với history, fault model, version settings và synthetic records?
10. **Sau khi sửa**, có đạt cả consistency, latency, availability và business invariants không?

### Sáu nguyên tắc cần nhớ

- **RYW là guarantee theo phạm vi, không phải nhãn chung của sản phẩm.**
- **Read cũ chỉ được kết luận từ lịch sử và source revision đáng tin.**
- **Write ACK, read concern, session token và route phải được ghi rõ.**
- **Đổi kết nối vật lý khác với reset logical session hoặc mất causal context.**
- **Một read model/index/cache có freshness contract riêng với source database.**
- **Không sửa stale read bằng việc che lỗi, chờ vô hạn hay bỏ qua durability/authorization.**

Câu hỏi thiết kế đáng nhớ:

> **“Sau khi người dùng nhận xác nhận ghi thành công, nếu request đọc tiếp theo đi tới một phiên khác hoặc một replica/cache chưa bắt kịp, chúng ta có cơ chế và bài kiểm thử nào chứng minh ứng dụng không trả phiên bản cũ hơn mức đã cam kết — hoặc từ chối rõ ràng khi chưa thể đáp ứng?”**

Khi trả lời được bằng **ACK boundary, version/causal token, end-to-end history, fault injection và test oracle đúng phạm vi**, bạn mới có cơ sở xác nhận hành vi đọc sau ghi của hệ NoSQL là **đúng theo hợp đồng nghiệp vụ**, kể cả khi kết nối hoặc topology thay đổi.
