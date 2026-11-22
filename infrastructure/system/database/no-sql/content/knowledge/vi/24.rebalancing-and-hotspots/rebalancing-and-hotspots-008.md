# Truy cập trong khi dữ liệu đang di chuyển trong NoSQL

## 1. Bài toán: vừa cân bằng shard, người dùng vẫn đọc và ghi

Một nền tảng lưu đơn hàng trên ba shard. Shard S1 đang chịu tải quá cao vì nhiều khách hàng truy cập cùng nhóm dữ liệu. Hệ quyết định **di chuyển một khoảng khóa** chứa các đơn của tenant `T01` từ S1 sang S3 để cân bằng tải.

Trong lúc dữ liệu đang được copy, các request vẫn đến:

```text
                         Client / API
                              |
                         Shard Router
                              |
                   +----------+---------+
                   |                    |
                   v                    v
              Source S1             Destination S3
           orders T01 v100            snapshot v95
                |                         ^
                +---- stream/copy --------+

User A: GET /orders/ORD-1001          -> đọc ở đâu?
User B: PATCH /orders/ORD-1001        -> ghi ở đâu?
User C: DELETE /orders/ORD-2002       -> xử lý khi bản copy còn tồn tại?
User D: GET /orders?status=PAID       -> có thấy trùng/mất đơn không?
```

Những câu hỏi quan trọng hơn “copy xong chưa” là:

- **Ai đang sở hữu quyền nhận ghi** cho khóa được di chuyển?
- Bản đích đã có snapshot đến **mốc nào**, và các ghi phát sinh sau snapshot được đồng bộ ra sao?
- Router/các instance ứng dụng có thể còn giữ **metadata định tuyến cũ** không?
- Một request đang chạy dở đúng thời điểm chuyển ownership có thể nhận kết quả gì?
- Đọc trong migration có thể thấy **dữ liệu cũ, dữ liệu mới, mất bản ghi hoặc bản ghi trùng** không?
- Nếu source/destination crash, **write đã được ACK** có bị mất không?
- Khi một hot key được di chuyển, liệu điểm nóng có được giải quyết hay chỉ **chuyển sang shard khác**?

Trong chương **Cân bằng và điểm nóng** của NoSQL, bài học này tập trung vào **live migration/resharding**: thay đổi vị trí dữ liệu mà không mặc định dừng toàn bộ ứng dụng, đồng thời giữ đúng ranh giới nhất quán, quyền ghi và khả năng phục hồi.

## 2. “Dữ liệu đang di chuyển” gồm những hoạt động nào?

Không phải mọi thao tác di chuyển đều cùng một loại:

| Hoạt động | Mục tiêu | Điều dễ ảnh hưởng đến request |
|---|---|---|
| **Shard/chunk/range migration** | Chuyển một khoảng khóa từ shard này sang shard khác | Stale routing, owner chuyển, retry |
| **Resharding** | Đổi shard key hoặc bố trí phân vùng | Gần như mọi khóa có thể đổi đích; scan và dual data layouts |
| **Rebalancing** | Phân tải dung lượng/QPS giữa node | Copy/streaming cạnh tranh I/O và network với request |
| **Replica relocation** | Thay node chứa một bản sao | Read target thay đổi, replica catch-up |
| **Node bootstrap/decommission** | Thêm/bớt node trong cluster | Token ownership/streaming và thay đổi routing |
| **Index/shard relocation của search** | Chuyển index shards/replicas | Search routing, refresh và query fan-out |
| **Tách hot partition** | Chia hoặc thay ownership phần dữ liệu quá nóng | Có thể phải đổi schema/key hoặc gom/tách aggregate |
| **Region evacuation** | Di chuyển dữ liệu khỏi failure domain | Lag, WAN latency, chính sách residency/DR |

Một hệ có thể gọi các bước là `copy`, `streaming`, `bootstrap`, `relocation` hoặc `resharding`. Tên khác nhau, nhưng cùng đặt ra câu hỏi: **read/write được phục vụ đúng thế nào khi nhiều nơi tạm giữ bản biểu diễn của cùng dữ liệu?**

### “Có hai bản copy” không có nghĩa “có hai owner”

Trong migration, việc S1 và S3 cùng chứa document `ORD-1001` là bình thường. **Bản sao vật lý** và **quyền quyết định thay đổi** phải được tách:

```text
S1: source copy, current write owner
S3: destination copy, chưa được quyền ACK write độc lập
```

Hệ an toàn có thể có nhiều bản sao dữ liệu nhưng phải có cơ chế duy trì **một quyền sở hữu ghi hợp lệ** (hoặc giao thức multi-writer được định nghĩa rõ, mạnh tương ứng bất biến).

## 3. Ba bất biến phải xác định trước migration

### 3.1. Không mất write đã commit

Nếu API đã trả thành công theo hợp đồng ghi:

\[
ACK(w)\Rightarrow w\text{ thuộc lịch sử được bảo vệ khi chuyển owner}
\]

Điều đó yêu cầu phân biệt write đã **nhận**, **append**, **commit** và **durable**. Không phải mọi ACK đều có cùng cam kết; phải dùng đúng write concern/consistency level của engine.

### 3.2. Không có hai authority xung đột

Trong một cơ chế single-owner cho range `R`, ở cùng một epoch:

\[
\operatorname{validOwners}(R,epoch)\le1
\]

Trong thời gian chuyển quyền, việc copy có thể chạy song song, nhưng **không được cho owner cũ và mới cùng xác nhận những write mâu thuẫn** nếu invariant yêu cầu thứ tự commit duy nhất.

### 3.3. Đường đọc thỏa hợp đồng của nó

- **Strong/linearizable read:** không trả trạng thái cũ trái với thứ tự write đã commit theo thời gian thực trong phạm vi được cam kết.
- **Read-your-writes:** cùng session không “mất” kết quả vừa ghi khi request đổi shard.
- **Eventual read:** có thể thấy dữ liệu cũ trong giới hạn sản phẩm quy định; không được giả là strong read.
- **Cross-shard transaction/snapshot:** nếu API hứa nhìn một snapshot nhất quán, phải duy trì điều đó qua migration, không chỉ trả các record rời.

**Migration an toàn không có nghĩa mọi request phải hoàn tất ngay**, mà là mỗi request thành công phải giữ đúng cam kết. Một số request có thể phải chờ, retry, redirect hoặc tạm báo unavailable.

## 4. Trạng thái cơ bản của một lần di chuyển range

Giả sử range khóa `[1000,2000)` chuyển từ S1 sang S3:

```text
                 +------------+
                 | PLANNED    |
                 +------+-----+
                        |
                        v
                 +------------+
                 | COPYING    | Source vẫn nhận write
                 +------+-----+ Destination là shadow
                        |
                        v
                 +------------+
                 | CATCHING_UP| Replay changes sau snapshot
                 +------+-----+
                        |
                        v
                 +------------+
                 | CUTOVER    | Chuyển authority/routing atomically
                 +------+-----+ theo protocol
                        |
                        v
                 +------------+
                 | VERIFYING  | Đối soát và theo dõi old routers
                 +------+-----+
                        |
                        v
                 +------------+
                 | CLEANUP    | Dọn source copy khi an toàn
                 +------------+
```

**Đây là mô hình khái niệm**, không phải state machine chuẩn của một sản phẩm cụ thể. Hệ có thể dùng bước tên khác, tăng thêm checkpoint hoặc khởi động lại copy nếu có lỗi. Trong từng giai đoạn, cần xác định **owner, read path, write path, mốc đồng bộ và cách resume**.

### Bảng hành vi ở từng giai đoạn

| Giai đoạn | Source S1 | Destination S3 | Router/Client |
|---|---|---|---|
| Planned | Owner hiện tại | Chưa có/chuẩn bị | Gửi request tới S1 |
| Copying | Tiếp tục nhận write hợp lệ | Nhận snapshot, chưa ACK write độc lập | Thường route S1 |
| Catching up | Tiếp tục nhận write, tạo change log | Replay tới watermark | Route S1 hoặc theo protocol |
| Cutover | Dừng/forward/reject write mới theo epoch | Trở thành owner khi đủ điều kiện | Refresh routing/retry có giới hạn |
| Verifying | Có thể giữ bản cũ để rollback/fallback an toàn | Phục vụ traffic chính | Theo metadata mới |
| Cleanup | Không còn là owner; dọn dữ liệu cũ | Owner cuối | Không đọc source cũ bằng route lỗi thời |

Các policy này chỉ minh họa **một dạng migration single-owner**. Với Redis Cluster, Cassandra, MongoDB hay search shards, mức độ song song và cách redirect cụ thể khác nhau.

## 5. Vấn đề snapshot: copy xong bản cũ vẫn chưa đủ

Giả sử lúc `t0` source có:

```json
{
  "_id": "ORD-1001",
  "status": "DRAFT",
  "version": 7
}
```

Job copy lấy snapshot v7. Trong khi copy đang chạy:

```text
t0: S3 copy ORD-1001 v7
t1: Client UPDATE ORD-1001 -> SUBMITTED v8 trên S1, ACK
t2: S3 copy job hoàn tất
t3: Router chuyển sang S3
t4: GET ORD-1001 từ S3 -> DRAFT v7
```

Nếu chỉ quan sát “100% record đã copy”, hệ đã **mất một write được xác nhận khỏi đường đọc mới**.

### Cần snapshot kết hợp thay đổi phát sinh

Một giải pháp phổ biến:

1. Xác định **điểm bắt đầu snapshot** và **vị trí log/CDC tương ứng**.
2. Copy các record theo ảnh chụp nguồn có ngữ nghĩa rõ.
3. Trong lúc copy, lưu/stream các thay đổi mới.
4. Replay các thay đổi sau snapshot theo thứ tự, xử lý duplicate.
5. Kiểm tra destination đã bắt kịp **cutover watermark**.
6. Chỉ chuyển owner khi protocol đảm bảo không còn **khoảng ghi bị bỏ sót**.

```text
                           Source S1
                              |
                   +----------+----------+
                   |                     |
                   v                     v
              Snapshot S0          Change log after S0
                   |                     |
                   v                     v
              Destination S3 <- replay/merge
                        |
                        v
               Applied through watermark W
```

Nếu CDC bắt đầu **sau khi** snapshot đã chụp mà không có phương án chống khoảng hở, một số write giữa hai điểm có thể bị mất. Thiết kế phải biết **đúng semantics snapshot và checkpoint của engine**.

## 6. Các mốc tiến độ: copied, received, applied, durable, visible

Một dashboard có thể báo:

```text
Source committed log position = 12,080
Destination received          = 12,080
Destination durable           = 12,070
Destination applied           = 12,045
Destination visible           = 12,045
Copy progress                 = 100% by documents
```

Điều này **chưa đủ** để chuyển mọi read mạnh sang S3. Destination đã nhận log tới 12.080 nhưng mới apply tới 12.045; một lệnh đọc có thể trả bản cũ.

| Mốc | Ý nghĩa | Không tự chứng minh |
|---|---|---|
| `copied_count` | Số record/snapshot bytes đã chuyển | Đã bắt kịp write sau snapshot |
| `received_offset` | Log đã đến destination | Đã ghi bền/áp dụng |
| `durable_offset` | Log đã ghi bền theo policy đích | Read path đã áp dụng |
| `applied_offset` | Thay đổi đã áp dụng | Search refresh/caches đã hội tụ |
| `visible_watermark` | Đường đọc được kiểm tra có thể thấy tới đây | Các path khác cùng mới |
| `committed_offset` | Mốc được authority xác nhận | Destination đương nhiên có mốc đó |

### Không trừ các offset không cùng hệ tọa độ

Nếu failover tạo log term mới, hoặc resharding thay đổi log identity, hai số có thể **không còn so trực tiếp được**. Checkpoint nên gắn với `rangeId`, `migrationId` và `epoch/term`, không chỉ một số nguyên.

### Đối với hệ không có một log tuyến tính duy nhất

Cassandra-like replication hoặc pipeline nhiều partition có thể cần **watermark theo partition/token range**, vector tiến độ hoặc đối soát theo key; một số “global offset” đơn giản không tồn tại.

## 7. Ownership và routing epoch: tránh hai bên cùng nhận ghi

Router cần biết shard nào sở hữu range:

```json
{
  "range": "[1000,2000)",
  "ownerShard": "S1",
  "epoch": 41,
  "state": "COPYING",
  "destination": "S3"
}
```

Sau cutover:

```json
{
  "range": "[1000,2000)",
  "ownerShard": "S3",
  "epoch": 42,
  "state": "ACTIVE"
}
```

**Epoch** hoặc generation là cách phân biệt **quyền sở hữu mới** với metadata cũ. Cơ chế thực có thể dùng term, config version, ownership generation hay token metadata.

### Quy tắc fencing

```text
Server nhận WRITE(key, expectedEpoch=41)
Current owner epoch=42

=> Reject NOT_OWNER / STALE_EPOCH
   hoặc forward theo protocol được hỗ trợ
```

S1 **không được tiếp tục ACK write như owner của epoch 41** sau khi epoch 42 đã được thiết lập và có thể phục vụ ở S3. Nếu S1 vẫn nhận ghi không phối hợp:

```text
Client A route cũ -> S1 -> UPDATE x=8 ACK
Client B route mới -> S3 -> UPDATE x=9 ACK
```

Hệ có thể có hai lịch sử xung đột.

### Fencing phải được enforce, không chỉ ghi vào log

Một trường `epoch=42` chỉ có tác dụng nếu server/coordinator **kiểm tra nguyên tử khi chấp nhận write**. Nếu ứng dụng đọc epoch rồi mới ghi ở thao tác khác, router/cutover vẫn có race giữa hai bước.

## 8. Cutover: chuyển quyền sở hữu mà không có khoảng hở dữ liệu

Một thuật toán khái niệm cho single-writer range:

```text
Precondition:
  S1 owns range R at epoch E
  S3 is shadow destination

1. Start snapshot + capture all post-snapshot changes.
2. Copy snapshot to S3.
3. Replay changes on S3; continue serving writes at S1.
4. Enter a short write barrier/fencing handoff for R:
     - prevent new E writes from committing at S1
     - finish/resolve in-flight writes
     - determine final committed source position W
5. Apply all committed changes through W at S3.
6. Atomically publish new ownership R -> S3, epoch E+1
   according to cluster coordination protocol.
7. Enable S3 to accept writes/strong reads under epoch E+1.
8. Redirect stale clients from S1; monitor and verify.
9. Cleanup old data only after protocol permits it.
```

**Đây là pseudocode về các thuộc tính cần đạt**, không phải một bộ thao tác có thể copy vào MongoDB/Cassandra/Redis. Các engine thực tế phối hợp một số bước khác thứ tự hoặc dùng forwarding mà không ngừng ghi hoàn toàn.

### Tại sao cần barrier/handoff?

Nếu source tiếp tục commit ghi mới sau khi destination được xác nhận đã bắt kịp W nhưng trước khi S3 nhận quyền, bản đích có thể lập tức thiếu update mới.

```text
S3 caught up to W=100
S1 ACK W=101
Router switches to S3 at W=100
=> W=101 tạm biến mất khỏi đường đọc/ghi mới
```

Handoff phải **khóa hoặc ràng buộc** những write trong khoảng chuyển quyền, hoặc dùng protocol đủ mạnh để forward/replay chúng mà không tạo hai owner tự do.

### Không phải lúc nào cần dừng mọi request toàn cluster

Barrier thường chỉ áp dụng cho **range hoặc shard đang di chuyển**, không bắt buộc đóng băng toàn database. Các range khác vẫn phục vụ bình thường.

Tuy nhiên nếu một transaction chạm nhiều range, coordinator có thể phải chờ một vài participant hoặc retry khi ownership thay đổi.

## 9. In-flight requests: điều gì xảy ra đúng thời điểm cutover?

Giả sử một lệnh cập nhật bắt đầu trên S1 trước cutover nhưng hoàn tất sau cutover:

```text
t0 Router epoch 41 -> S1
t1 S1 nhận UPDATE R
t2 Coordinator bắt đầu cutover
t3 Metadata epoch 42 -> S3
t4 S1 trả response cho UPDATE R
```

Có ít nhất hai cách diễn giải hợp lệ tùy protocol:

1. **Update được commit trước handoff barrier** và bao gồm trong mốc W đã replay sang S3; response có thể tới client sau khi metadata đã đổi.
2. **Update chưa commit trước barrier**, S1 phải từ chối/redirect hoặc giải quyết như một request pending để client retry an toàn.

Không được chỉ so thời điểm **response** với thời điểm đổi route để kết luận write bị mất. Phải biết **commit point và in-flight policy** của migration.

### Response và retry có thể trùng

```text
Client sends UPDATE operationId=OP-42 to S1
S1 commits, response lost
Router refresh -> sends OP-42 to S3 again
```

Nếu update là `balance += 100`, chạy hai lần tạo sai lệch. Routing retry phải đi cùng **idempotency key**, version/CAS hoặc cơ chế của operation đảm bảo áp dụng một lần theo nghĩa nghiệp vụ.

### Timeout nghĩa là gì?

Timeout có thể là:

- Request chưa tới owner.
- Owner cũ từ chối do epoch cũ.
- Write đã commit nhưng ACK bị mất.
- Destination chưa catch-up nên chờ.
- Transaction in-doubt khi participant đổi ownership.

**Không gộp mọi timeout thành “write thất bại, tạo request mới”.**

## 10. Xử lý lỗi định tuyến: NOT_OWNER, MOVED, ASK, RETRY

Router hoặc client có thể dùng metadata cũ:

```text
Client metadata: R -> S1, epoch=41
Cluster current: R -> S3, epoch=42

Client -> S1: GET/WRITE key in R
S1 -> Client: NOT_OWNER(R, epoch=42, hint=S3)
Client -> metadata service: refresh route
Client -> S3: retry according to operation semantics
```

### Các kiểu phản hồi cần phân biệt

| Trạng thái | Ý nghĩa | Client nên làm |
|---|---|---|
| `NOT_OWNER/STALE_EPOCH` | Request đến node không còn quyền | Refresh route; retry nếu outcome chưa commit/được bảo vệ |
| `MOVED` trong Redis Cluster | Chủ sở hữu slot đã đổi theo cơ chế Redis | Cập nhật slot cache và gửi lại đúng node |
| `ASK` trong Redis Cluster | Key/slot đang migration, redirect tạm thời | Dùng handshake `ASKING` cho request tiếp theo; không mặc định route đã đổi vĩnh viễn |
| `TRYAGAIN/RETRYABLE` | Trạng thái tạm thời, có thể do migration | Backoff, retry có giới hạn |
| `UNAVAILABLE` | Không thể phục vụ đúng hợp đồng | Không trả stale như fresh; báo lỗi/đợi |
| `UNKNOWN_COMMIT` | Không biết write đã commit chưa | Tra cứu theo operationId, không thực hiện lại vô điều kiện |

Các tên trừ Redis là **ký hiệu tổng quát**, không phải mã lỗi API chung cho mọi NoSQL.

### Tránh redirect loop

Nếu S1 và S3 đều có metadata khác nhau, client có thể bị chuyển qua lại:

```text
S1 -> MOVED S3
S3 -> MOVED S1
...
```

Client cần giới hạn số redirect, theo dõi epoch tăng đơn điệu nếu protocol hỗ trợ, refresh từ metadata authority và trả lỗi rõ khi trạng thái cluster bất thường. **Không retry vô hạn gây bão request**.

## 11. Đọc trong lúc copy: strong, causal và eventual

### 11.1. Strong read

Nếu S1 còn là authority, read mạnh nên được phục vụ theo đường có cơ chế đọc bảo vệ tính mới nhất tương ứng:

```text
GET key at epoch 41
    |
    v
S1 owner / authorized read protocol
    |
    v
Return current committed value
```

Không tự route strong read sang S3 chỉ vì snapshot copy gần xong. S3 có thể còn thiếu log cuối hoặc đang apply nhưng chưa đủ read barrier.

Sau cutover, S3 mới là owner; S1 phải redirect, chờ hoặc chỉ phục vụ **stale read được cho phép rõ**.

### 11.2. Read-your-writes

Client đã ghi `ORD-1001` version 8 trước migration và ngay sau cutover đọc lại:

```text
WRITE -> ACK version 8 at S1
Handoff -> S3 owner
GET -> minVersion 8
```

Backend cần bảo đảm S3 đã bao gồm write được ACK hoặc chờ/fallback thích hợp. Nếu S3 trả version 7, trải nghiệm và hợp đồng read-your-writes bị phá vỡ.

Một cơ chế có thể dùng `sessionToken`, `minVersion` hoặc read barrier nếu engine hỗ trợ. Token phải gắn đúng aggregate/epoch và **không phải bằng chứng quyền truy cập**.

### 11.3. Eventual read

Ứng dụng có thể cho phép đọc một replica cũ trong khoảng thời gian ngắn đối với **catalog preview**. Nhưng response cần nói rõ đường đọc và độ mới theo SLA. Không lấy một stale read để đưa ra quyết định bán vé, trừ tồn kho, thanh toán hay thu hồi quyền.

### 11.4. Không đánh đồng read availability với correctness

Nếu server cũ trả HTTP 200 với version 7 sau khi source đã commit version 8, nó có thể vẫn đang phục vụ một **eventual read** hợp lệ, nhưng **không được tự coi** đó là strong read thành công.

## 12. Ghi trong migration: một owner, forwarding hay controlled dual writes

Có vài chiến lược phổ biến:

### A. Chỉ source nhận ghi đến cutover

```text
During copy:  Client -> S1 -> commit
                            |
                            +--> stream to S3
At cutover:  fence S1, finish replay, transfer owner
After:       Client -> S3 -> commit
```

Ưu điểm: một nguồn quyền ghi rõ ràng. Đánh đổi: có thể có thời gian chờ/barrier khi cutover.

### B. Source forward request sang destination theo protocol

Sau khi ownership đổi:

```text
Stale client -> S1
S1 verifies no longer owner
S1 forwards/redirects -> S3 (with stable operationId)
S3 commits according to epoch=42
```

Forwarding phải tránh vòng lặp và **không cho S1 commit cạnh tranh**. Cần giữ nguyên ID/idempotency metadata.

### C. Controlled dual-write/dual-replication

Một số migration protocol phát mỗi update đến source và destination trong giai đoạn chuyển đổi. **Không được hiểu đó là hai write độc lập cùng được ACK tùy ý**.

Nếu hệ dùng dual writes, nó phải có:

- **Một thứ tự commit có thẩm quyền**.
- Cơ chế xác nhận thành công/failed replica rõ ràng.
- Retry/replay khi một bên lỗi.
- Idempotency/versioning để không apply duplicate.
- Barrier và fencing khi đổi owner.

Đoạn code ngây thơ sau không đảm bảo atomicity:

```javascript
await writeToS1(document);
await writeToS3(document);
return { ok: true };
```

Nếu S1 thành công, S3 lỗi rồi process crash, hai nơi lệch. Nếu đảo thứ tự vẫn có cửa sổ lỗi. **Cần giao thức phục hồi/commit**, không chỉ `try/catch`.

## 13. Update, CAS và version trong khi di chuyển

Một pattern hữu ích là lưu version trên aggregate:

```json
{
  "_id": "ORD-1001",
  "tenantId": "T01",
  "status": "DRAFT",
  "version": 7
}
```

Client cập nhật có điều kiện:

```javascript
db.orders.updateOne(
  {
    _id: "ORD-1001",
    tenantId: "T01",
    version: 7
  },
  {
    $set: { status: "SUBMITTED" },
    $inc: { version: 1 }
  }
);
```

Điều kiện version giúp chặn **lost update** trên owner hợp lệ. Khi migration, ngoài version dữ liệu còn cần **ownership epoch/routing validation** ở engine/router.

### Version dữ liệu khác version metadata

| Loại version | Ví dụ | Dùng để |
|---|---|---|
| `order.version=8` | Version aggregate | CAS, ordering, stale read |
| `range.epoch=42` | Version ownership | Fencing stale owner/router |
| `migrationId=M7` | Định danh một lần chuyển | Trace checkpoint, retry, cleanup |
| `logPosition=12080` | Mốc stream/commit | Catch-up và handoff |
| `schemaVersion=3` | Version định dạng document/event | Chuyển đổi schema đúng |

Không dùng `order.version` để suy ra toàn shard đã copy xong, cũng không dùng `range.epoch` như giá trị version của một đơn.

### Operation không idempotent

```text
INCREMENT inventory by -1
APPEND item to array
CHARGE payment
```

không thể retry vô điều kiện sau timeout. Giải pháp tùy nơi tác động: durable operation ledger, conditional state transition, unique request ID, hoặc provider idempotency key; một router tốt không thể tự sửa semantic duplicate cho mọi phép toán.

## 14. Delete và tombstone: dữ liệu xóa có thể quay lại

Ví dụ:

```text
t0 S3 snapshot Product P10 v11 ACTIVE
t1 S1 DELETE P10 at v12, ACK
t2 S3 vẫn còn snapshot P10 v11
t3 Cutover
t4 Query S3 -> Product P10 xuất hiện trở lại
```

Nếu pipeline chỉ copy các record còn tồn tại mà không mang **thông tin delete**, S3 có thể hồi sinh record.

Một cách thể hiện delete có version:

```json
{
  "_id": "P10",
  "sourceVersion": 12,
  "deleted": true
}
```

Migration/replay phải áp delete đúng thứ tự; event cập nhật v11 đến sau không được ghi đè tombstone v12.

### TTL cũng tạo thao tác xóa

Một record hết hạn trong lúc snapshot/copy có thể đã bị xóa ở nguồn nhưng còn tồn tại ở đích nếu TTL metadata không được truyền đúng hoặc expiration policy khác nhau.

Với dữ liệu có TTL, cần biết:

- TTL tính từ lúc tạo, lúc update hay thời điểm tuyệt đối?
- Snapshot có giữ **expiryAt** hay vô tình reset TTL từ lúc copy?
- Delete/expiration được log hoặc diễn giải tại destination thế nào?
- Sau rebalancing, record có bị tồn tại dài hơn hoặc biến mất sớm hơn không?

**Không chỉ đếm record để khẳng định dữ liệu đúng**; cần kiểm tra giá trị, version, delete state và expiry semantics.

## 15. Unique constraint trong lúc shard đổi vị trí

Nếu business rule là username duy nhất trong tenant, sharding thường dùng unique index hoặc guard/registry có owner rõ ràng.

Khi di chuyển range, nguy cơ:

```text
Old router -> S1: claim username anna
New router -> S3: claim username anna
```

Nếu cả hai shard cùng coi mình có quyền claim, có thể tạo hai owner. Do đó migration phải giữ:

\[
\operatorname{claimAuthority}(tenantId,usernameKey)\text{ duy nhất}
\]

theo giao thức chuyển epoch.

Một unique index cục bộ trên S1 và S3 **không tự tạo unique constraint toàn cục** nếu routing có thể tách hai request giống nhau sang hai nơi cùng nhận ghi.

### Các hướng bảo vệ

- Định tuyến mọi claim cùng business key đến cùng authority và chuyển authority có fencing.
- Dùng registry theo unique key; registry có quy trình migration riêng.
- Sử dụng transaction/index sharded unique được engine hỗ trợ, đúng điều kiện shard key.
- Khi không chắc đã chuyển quyền thành công, **không trả hai ACK claim thành công**.

## 16. Giao dịch nhiều shard khi một participant đang di chuyển

Giả sử chuyển tiền giữa hai tài khoản nằm trên S1 và S2:

```text
Transaction T
  Debit A on S1 (range R đang migrate sang S3)
  Credit B on S2
```

Trong khi T mở, range R đổi owner. Hệ phải giải quyết:

- T đã đọc/ghi trên owner cũ theo epoch nào?
- Prepare/lock/commit decision đã ghi ở đâu?
- Destination có nhận đầy đủ pending/committed transaction không?
- Nếu coordinator timeout, T đã commit hay chưa?
- Retry của client có thể tạo chuyển tiền hai lần không?

### Handoff và transaction coordinator

Một hệ hỗ trợ distributed transactions có thể chặn migration ở một đoạn, chờ giao dịch kết thúc, abort/retry transaction xung đột hoặc phối hợp state khi chuyển range. **Hành vi cụ thể phụ thuộc engine và phiên bản**.

Không có lý do để tin rằng chỉ cần router refresh là một transaction đã ghi nửa ở S1 sẽ tự hoàn tất chính xác trên S3.

### 2PC là một lựa chọn giao thức, không phải phép màu

Trong mô hình 2PC:

```text
T -> PREPARE S1, PREPARE S2
Coordinator -> quyết định COMMIT/ABORT
Participants -> thực hiện quyết định
```

Migration cần tôn trọng quyền participant và các decision đã bền. Nếu node chết hoặc network partition ở lúc prepare, transaction có thể bị chờ/`in-doubt`; không tự suy timeout là abort.

Giao dịch xuyên shard **không đồng thời commit** thay đổi trong email provider, Kafka hoặc Redis nếu chúng không cùng tham gia một giao thức được hỗ trợ. Với workflow xuyên service, cần outbox, idempotency và saga theo nhu cầu.

## 17. Range scan, pagination và query xuyên shard dễ mất/trùng record

Không phải request nào cũng là `GET by primary key`. Một trang quản trị có thể truy vấn:

```text
GET /orders?tenant=T01&createdAfter=...
ORDER BY createdAt
LIMIT 100
```

Trong lúc S1 đang copy sang S3, một query fan-out có thể:

1. Đọc 100 record từ S1 trước cutover.
2. Router refresh, trang tiếp theo đọc từ S3.
3. Một vài record đổi owner giữa hai lần đọc.

Hậu quả có thể là **duplicate, missing record hoặc thứ tự trang không ổn định** nếu API không có snapshot/pagination semantics phù hợp.

### Ví dụ offset pagination gặp thay đổi

```text
Page 1 on old layout: OFFSET 0 LIMIT 100
Migration + concurrent inserts/deletes
Page 2 on new layout: OFFSET 100 LIMIT 100
```

Offset gắn với vị trí trong tập sắp xếp **đang thay đổi**, nên không bảo đảm duyệt đúng mỗi record một lần.

### Thiết kế có thể dùng

- **Keyset/cursor pagination** theo khóa sắp xếp ổn định, ví dụ `(createdAt,orderId)`.
- **Snapshot timestamp/read transaction** nếu engine/API hỗ trợ trên phạm vi query.
- Cursor có **layout epoch/version** và khả năng resume theo giao thức.
- De-dup theo `_id` trên client/aggregator khi query phân tán cho phép.
- Xử lý delete/tombstone, sort tie-breakers và new inserts rõ ràng.
- Nếu yêu cầu export chính xác tại một thời điểm, chạy trên một **consistent snapshot**, không chỉ “GET mỗi trang đến khi hết”.

### Keyset chưa tự bảo đảm snapshot

Keyset pagination giúp chống một số lệch do offset và sắp xếp, nhưng nếu bản ghi đổi khóa sắp xếp, bị xóa hoặc xuất hiện mới giữa các page, vẫn có thể gặp biến động. API cần công bố **duyệt live data** hay **duyệt snapshot cố định**.

## 18. Secondary index, cache và search trong migration

Một shard có thể chứa nhiều cấu trúc:

```text
Authoritative document
   |
   +--- local secondary indexes
   +--- materialized views
   +--- Redis cache / invalidation
   +--- CDC / outbox events
   +--- external search index
```

### Secondary indexes nội bộ

Khi một document chuyển shard, hệ phải duy trì/khôi phục index tương ứng theo cơ chế migration của engine. Nếu index chưa sẵn sàng ở destination mà router đã cho query mới dùng, query có thể trả thiếu hoặc chậm.

Không nên tự copy collection bằng script rồi quên indexes/collation/constraints và tuyên bố cutover hoàn tất.

### Redis cache

Cache có thể chứa dữ liệu **không phụ thuộc vị trí shard**:

```text
cache key = order:ORD-1001
value = {status: "DRAFT", version: 7}
```

Khi source đổi sang v8 rồi migration cutover, cache vẫn có thể v7. Cần invalidation/version CAS/read barrier, không chỉ cập nhật shard routing.

Nếu cache value còn chứa **node address/owner shard**, TTL lâu có thể làm request tiếp tục gửi tới node cũ.

### Search read model

Elasticsearch/OpenSearch có routing/index relocation riêng và có thể nhận event từ CDC. Lag search **không đồng nghĩa** lag shard migration nguồn. Nên theo dõi source commit, projector checkpoint và search visibility riêng.

### Không nhân đôi event trong lúc copy

Nếu migration phát lại mọi document như “Created” thay vì phân biệt snapshot/backfill với business events, downstream consumer có thể **gửi email/charge tiền hai lần**. Snapshot là hoạt động tái tạo dữ liệu; event nghiệp vụ mới có ý nghĩa side effect khác.

Gắn `migrationId`/`sourceVersion` và tách pipeline materialization khỏi event tạo tác động khi phù hợp.

## 19. Điểm nóng: di chuyển dữ liệu chưa chắc di chuyển được tải

Một shard nóng có thể do:

- **Storage hotspot:** một shard chứa quá nhiều dữ liệu.
- **CPU/I/O hotspot:** query/compaction/index maintenance quá nặng.
- **Partition hotspot:** nhiều request tập trung một partition/range.
- **Single-key hotspot:** một key như `inventory:SKU-P10` bị cập nhật liên tục.
- **Skewed tenants:** một tenant chiếm phần lớn workload.
- **Temporal hotspot:** mọi write vào khoảng thời gian mới nhất của khóa tăng dần.

Chuyển một chunk lớn có thể giải quyết storage skew, nhưng không nhất thiết giải quyết **single-key write contention**.

### Ví dụ chuyển nóng từ S1 sang S3

```text
Before:
  S1 CPU 95%, hot key K = 20k writes/s
  S3 CPU 30%

After moving K:
  S1 CPU 30%
  S3 CPU 95%, hot key K still 20k writes/s
```

Ta chỉ **đổi địa chỉ điểm nghẽn**.

### Nếu một key không thể chia

Các lựa chọn tùy nghiệp vụ:

- Gom nhiều update bằng batching/coalescing.
- Dùng counter phân mảnh nếu phép toán cho phép và có cách tổng hợp.
- Phân bổ quota/escrow khi cần bounded counter.
- Chuyển từ single-key fan-in sang append-only event log + aggregator.
- Caching read-heavy và invalidate có kiểm soát.
- Giảm contention bằng state machine/conditional write tối ưu.
- Tách trường không cần atomic cùng nhau khỏi aggregate nóng.

Không tự **shard một unique key** thành nhiều owner ghi độc lập nếu vẫn cần invariant “chỉ một người được giữ ghế” hoặc “không bán vượt kho”. Việc chia tải phải giữ ranh giới quyết định của nghiệp vụ.

## 20. Chi phí migration cạnh tranh với traffic thật

Trong lúc copy/stream, source và destination cùng chịu:

```text
Source:
  foreground reads/writes
  snapshot scan
  log capture
  network send

Destination:
  normal traffic
  bulk import/index build
  replay/compaction
  validation
```

### Resource budgets

| Tài nguyên | Nếu migration dùng quá mức | Triệu chứng |
|---|---|---|
| Disk I/O | Foreground query bị tranh I/O | p99 latency tăng |
| Network bandwidth | Replication/client traffic nghẽn | timeout, lag tăng |
| CPU | Serialization/compression/index build | throughput giảm |
| Memory | Buffer/cache bị đẩy ra | GC/eviction, cache miss tăng |
| WAL/oplog retention | Backlog vượt vùng log giữ được | Migration phải resnapshot |
| Database locks | Cutover/transaction chờ nhau | queue, abort/conflict |
| Router metadata service | Nhiều node refresh cùng lúc | control-plane overload |

### Điều tiết lưu lượng

Có thể:

- Giới hạn MB/s hoặc IOPS của copy.
- Chuyển từng range/batch có checkpoint.
- Tránh bắt đầu nhiều migration lớn cùng lúc.
- Giảm tốc khi p99 foreground vượt SLO.
- Ưu tiên xử lý log tail để tránh mất khả năng catch-up.
- Lập lịch theo thời gian tải thấp, nhưng vẫn thử đúng điều kiện peak cần phục vụ.

**Copy càng nhanh chưa chắc downtime càng thấp**: nếu bulk copy làm log tail backlog tăng nhanh, destination có thể không bao giờ bắt kịp để cutover.

## 21. Cách tính catch-up time và giới hạn của ước lượng

Giả sử source sinh thêm thay đổi:

\[
\lambda = 40\text{ MB/s}
\]

Destination replay được:

\[
\mu = 55\text{ MB/s}
\]

Với backlog ban đầu \(Q_0=3000\text{ MB}\), tốc độ giảm backlog gần đúng:

\[
\mu-\lambda=15\text{ MB/s}
\]

Nếu tốc độ ổn định và không có overhead:

\[
T_{\text{catch-up}}\approx\frac{3000}{15}=200\text{ s}
\]

Đây chỉ là **ước lượng minh họa**. Thực tế:

- Kích thước change log không bằng bytes của document sau nén.
- Replay có thể tạo nhiều index updates.
- Write rate có thể tăng trong giờ cao điểm.
- Destination có thể bị compaction hoặc I/O nghẽn.
- Quá trình cutover còn cần barrier/metadata coordination.

Nếu \(\mu\le\lambda\) kéo dài, backlog **không giảm**, nên tăng thời gian chờ không giải quyết vấn đề. Cần giảm write rate hợp lý, cấp thêm năng lực apply, chia migration hoặc thay chiến lược.

## 22. Đọc/ghi với metadata router cũ

Trong hệ có nhiều app instance, metadata cache có thể cập nhật khác thời điểm:

```text
Metadata authority: R -> S3 epoch=42
App A cache:         R -> S1 epoch=41
App B cache:         R -> S3 epoch=42
```

Một hệ đúng không thể dựa vào giả định “mọi app refresh routing đồng thời”.

### Giao thức mong muốn

1. Router gửi request kèm routing version/epoch khi có API hỗ trợ.
2. Shard cũ nhận ra không còn quyền với range.
3. Trả redirect/not-owner hoặc forward theo protocol.
4. Client refresh route và retry có giới hạn, **giữ nguyên operation ID**.
5. Nếu kết quả write cũ không rõ, dùng idempotency ledger/status lookup thay vì blindly replay.

### Không hard-code địa chỉ shard trong business data

Ví dụ không nên lưu như một “chân lý lâu dài”:

```json
{
  "orderId": "ORD-1001",
  "physicalShardAddress": "10.0.0.11:27017"
}
```

nếu ứng dụng có thể di chuyển dữ liệu. Một định danh ổn định như `orderId` hoặc logical partition key phải được ánh xạ qua router/metadata có thể đổi.

Nếu cần cache location, nó phải có **version/TTL/invalidation và xử lý redirect**, không trở thành khóa nghiệp vụ.

## 23. Ví dụ Java: retry khi route đổi nhưng giữ idempotency

Ví dụ Java 17 sau minh họa một client adapter. Nó **không phải SDK của một database cụ thể**.

```java
import java.util.Objects;

record Route(String shardId, long epoch) {}
record WriteCommand(
    String tenantId,
    String orderId,
    String operationId,
    long expectedVersion,
    String newStatus
) {}
record WriteResult(
    String orderId,
    long newVersion,
    String operationId
) {}

interface RouteDirectory {
    Route lookup(String tenantId, String orderId) throws Exception;
    void invalidate(String tenantId, String orderId);
}

interface ShardTransport {
    // Request phải được server fence theo owner epoch.
    // operationId phải được deduplicate BỀN ở authority.
    WriteResult update(
        Route route, WriteCommand command
    ) throws NotOwnerException, UnknownCommitException, Exception;
}

final class NotOwnerException extends Exception {}
final class UnknownCommitException extends Exception {}

final class RoutedOrderWriter {
    private final RouteDirectory directory;
    private final ShardTransport transport;

    RoutedOrderWriter(
        RouteDirectory directory,
        ShardTransport transport
    ) {
        this.directory = Objects.requireNonNull(directory);
        this.transport = Objects.requireNonNull(transport);
    }

    WriteResult update(WriteCommand command) throws Exception {
        // operationId được tính một lần từ logical request,
        // không tạo ID mới mỗi lần gặp NOT_OWNER.
        if (command.operationId() == null) {
            throw new IllegalArgumentException("Missing operationId");
        }

        for (int attempt = 0; attempt < 3; attempt++) {
            Route route = directory.lookup(
                command.tenantId(), command.orderId()
            );

            try {
                return transport.update(route, command);
            } catch (NotOwnerException stale) {
                directory.invalidate(
                    command.tenantId(), command.orderId()
                );
                // Theo contract: NOT_OWNER được trả khi server
                // CHƯA commit request dưới route này.
                // Chỉ lúc ấy mới retry theo route mới.
            } catch (UnknownCommitException unknown) {
                // Outcome mơ hồ: phải tra operation ledger/status;
                // KHÔNG âm thầm thực hiện lại như request mới.
                throw unknown;
            }
        }

        throw new IllegalStateException(
            "Could not resolve current shard owner"
        );
    }
}
```

### Điều kiện không thể bỏ qua

- `NotOwnerException` phải có nghĩa rõ **request chưa commit tại node này**; nếu API có thể trả lỗi sau commit, xử lý như `UnknownCommit`.
- `operationId` chỉ có tác dụng chống duplicate nếu **server giữ một bảng idempotency/ledger bền** trong phạm vi authority và recovery.
- `expectedVersion` là CAS trên aggregate; nó không thay thế `epoch` bảo vệ owner.
- Retry có giới hạn, backoff/jitter và deadline toàn request; ví dụ rút gọn để dễ học.
- `tenantId` phải được xác thực từ principal; không dùng giá trị client đưa vào để vượt quyền shard/tenant.
- Cần kiểm tra exception thực tế của SDK và topology. Không dịch mọi lỗi mạng thành `NotOwner`.
- Với transaction đa key, retry lại từng write riêng lẻ sẽ phá atomicity; phải retry/resolve **toàn bộ transaction** theo hợp đồng coordinator.

Đây là cách tách **lỗi định tuyến được biết là an toàn để thử lại** khỏi **kết quả ghi không rõ**, một phân biệt đặc biệt quan trọng khi dữ liệu chuyển owner.

## 24. MongoDB: chunk migration, balancer và resharding

MongoDB sharded cluster sử dụng metadata định tuyến để quyết định shard chứa dữ liệu theo shard key. Trong các triển khai thích hợp, `mongos` định tuyến request, và **balancer/chunk migration** có thể chuyển một range giữa shard.

### Trong lúc chuyển range

Điều cần tìm hiểu theo phiên bản MongoDB đang chạy:

- Copy dữ liệu ở donor sang recipient.
- Cách các thay đổi mới tại donor được theo dõi/catch-up.
- Điều kiện chuyển ownership metadata.
- Cách `mongos` phát hiện metadata stale và xử lý lại request.
- Ảnh hưởng đến transaction, index và long-running query.
- Thời gian/giới hạn của bước commit migration và cleanup orphaned ranges.

Hệ quản trị xử lý nhiều chi tiết đó bằng giao thức nội bộ; **ứng dụng không nên tự gửi request thẳng đến shard cũ thay cho router hỗ trợ** nếu muốn hưởng semantics migration chính thức.

### Phân biệt chunk balancing với resharding

- **Chunk/range migration:** chuyển một vùng khóa giữa các shard trong layout hiện tại.
- **Resharding:** đổi shard key; dữ liệu có thể phải được phân phối lại theo layout mới với nhiều bước và điều kiện khác.

Các lệnh điều hành và giới hạn phụ thuộc phiên bản. Không suy rằng vì balancer có thể di chuyển chunk online nên mọi kiểu resharding đều **không có chặn/latency tại bất kỳ giai đoạn nào**.

### Read/write concern và session

Một write đã commit theo concern phù hợp phải được phân biệt với write chỉ nhận local ACK, có thể chịu rủi ro khác khi failover. Causal session, transaction và read concern có phạm vi riêng; migration không tự làm mọi secondary read linearizable.

Khi ứng dụng cần read-your-writes sau update, cần dùng driver/session và read/write options theo **hợp đồng MongoDB**, không dựa vào “chunk đã copy 100%”.

### Index và shard key

Khi shard key liên quan uniqueness hoặc query route, migration/resharding phải giữ các index constraints được hỗ trợ. Không tự kết luận một unique index chỉ theo email là global trên mọi sharded collection; phạm vi unique phụ thuộc shard key và giới hạn của engine.

### Những tín hiệu vận hành

Theo dõi các operation/migration status, balancer activity, shard distribution, router stale metadata/retry, latency/read/write errors, resource utilization, replication lag, transaction abort và tình trạng orphan cleanup **theo công cụ/phương thức của đúng phiên bản**.

## 25. Redis Cluster: MOVED, ASK và trạng thái slot migration

Redis Cluster dùng **hash slots** để định tuyến key. Khi một slot di chuyển từ node A sang B, client cluster-aware phải xử lý các phản hồi đặc thù.

### `MOVED` là redirect dài hạn

Ví dụ minh họa:

```text
Client -> A: GET key
A -> Client: MOVED <slot> B
Client refreshes slot map
Client -> B: GET key
```

`MOVED` báo rằng owner của hash slot đã thay đổi theo cluster topology. Client có thể cập nhật bảng định tuyến cho slot.

### `ASK` là redirect tạm thời trong migration

Trong giai đoạn slot đang `MIGRATING` ở source và `IMPORTING` ở destination, một request có thể được chỉ tới đích tạm thời qua `ASK`:

```text
Client -> A: command for key in moving slot
A -> Client: ASK <slot> B
Client -> B: ASKING
Client -> B: command
```

**Không nên cập nhật slot mapping vĩnh viễn chỉ vì nhận `ASK`**; đó khác `MOVED`. Thư viện Redis Cluster client chính thống thường tự xử lý handshake này.

### Trạng thái key hiện diện và các request đồng thời

Trong migration, key có thể đang ở source hoặc đã chuyển sang destination; hành vi redirect phụ thuộc trạng thái key/slot và quy tắc của Redis Cluster. Client không nên tự chọn “node nào có bản mới hơn” bằng cách gọi cả hai rồi so timestamp.

### Multi-key operations

Các thao tác Redis Cluster liên quan nhiều key có giới hạn khi keys thuộc **khác hash slot**, và trong lúc resharding một số lệnh có thể nhận retryable errors dù ở cùng slot. Khi nghiệp vụ cần atomic multi-key, cần kiểm tra **hash tags, slot colocation và đặc tả lệnh**.

```redis
MGET {cart:123}:summary {cart:123}:items
```

Ví dụ dùng hash tag để cùng slot nếu key naming phù hợp, nhưng **cùng slot không tự nghĩa transaction chung với MongoDB/Kafka**.

### Không copy key bằng script rồi tự cập nhật slot

Di chuyển slot phải dùng cơ chế Redis Cluster được hỗ trợ để giữ metadata/redirect/TTL và trạng thái key. Một script `DUMP/RESTORE` độc lập không tự giải quyết concurrent writes, client routing và cutover.

## 26. Cassandra/ScyllaDB: token ranges và streaming khi bootstrap/decommission

Trong các hệ wide-column có partitioning theo token, thêm/bớt node có thể làm **token range ownership** thay đổi. Dữ liệu thường được streaming giữa những replica theo quy tắc token/replication factor.

### Những câu hỏi cần đặt

- Node mới đã ở trạng thái **bootstrap/normal** nào?
- Token ranges nào đang chuyển ownership?
- Cấu hình replication factor và consistency level là gì?
- Một coordinator đang định tuyến read/write đến những replica nào?
- Hints, repair và streaming có theo kịp các mutations mới không?
- Node cũ có thể decommission an toàn chưa?

Không có một leader log toàn cluster giống mọi mô hình primary/secondary, nên không nên áp nguyên xi sơ đồ “S1 là write owner duy nhất” của mục trước lên mọi phiên bản Cassandra.

### Consistency level và migration

Với Cassandra, sự đúng của read/write trong lúc topology thay đổi phụ thuộc **giao thức replica placement/topology transitions, CL, hints/repair và failure scenarios**. Ví dụ read ở `ONE` có thể thấy replica cũ hơn, còn `QUORUM` có semantics khác; **không mặc định QUORUM = global linearizable transaction**.

### Streaming không thay thế repair

Một node mới nhận snapshot/streaming có thể chưa phản ánh mọi update concurrent hoặc không có dữ liệu nhất quán toàn keyspace nếu trạng thái/repair không được hoàn tất theo quy trình engine.

Cần theo dõi `nodetool status`, `nodetool netstats` hoặc telemetry tương đương được phiên bản hỗ trợ, các chỉ số streaming, dropped messages, pending compactions, repair và read/write latency.

### CQL BATCH không phải cách “khóa cả cluster”

`BEGIN BATCH ... APPLY BATCH` có semantics riêng nhưng không tự tạo một distributed serializable transaction tổng quát trên nhiều partition. Nếu migration chạm một invariant liên quan nhiều partition, cần xem xét LWT, partition design hoặc workflow/ledger phù hợp.

## 27. DynamoDB: scaling và internal partition movement

DynamoDB là dịch vụ managed; ứng dụng thường không điều khiển trực tiếp **nội bộ partition movement** hoặc thấy chi tiết mọi bước copy như khi tự chạy MongoDB/Cassandra.

Những điều có thể quản lý ở tầng ứng dụng:

- Chọn partition key phân tán tải hợp lý.
- Dùng conditional writes/transactions phù hợp với invariant.
- Theo dõi throttling/consumed capacity/latency.
- Tránh hot partitions và access patterns tạo key skew.
- Phân biệt base table, GSI và Streams/consumer.
- Khi tự thực hiện data migration giữa **bảng hoặc region**, thiết kế copy + CDC/outbox + cutover có checkpoint rõ.

### Phân biệt internal movement với application migration

Một lần DynamoDB tự cân bằng partition không đồng nghĩa bạn phải sửa shard router thủ công. Nhưng nếu ứng dụng chủ động chuyển record giữa **hai bảng**, đổi logical partition key hoặc copy dữ liệu sang region khác, bạn đang thực hiện một **migration cấp ứng dụng** với yêu cầu uniqueness, concurrent writes, TTL, streams và rollback.

### GSI không là source of truth cho việc cấp quyền

Trong lúc chuyển layout, GSI có thể chưa đồng bộ ngay. Không dùng `Query GSI thấy không có email` làm quyết định tạo user nếu ràng buộc cần duy nhất. Dùng guard key/conditional write hoặc transaction API được hỗ trợ.

### Global Tables và nhiều region

Khi chuyển traffic giữa region, cần biết consistency mode và conflict semantics của deployment. Một write ACK tại A không tự đồng nghĩa bản ở B đã xuất hiện ngay trong mọi mode. Nếu cần single authority cho account/seat, phải thiết kế routing/coordination đúng thay vì dựa vào eventual replica.

## 28. Elasticsearch/OpenSearch: relocation và query visibility

Search clusters cũng phân bổ **primary/replica shards** và có cơ chế relocation/recovery khi cân tải hoặc thay node.

Khác biệt:

- **Storage recovery/relocation:** chuyển dữ liệu index shard giữa các node.
- **Search refresh:** làm document mới có thể thấy qua `_search`.
- **Source-to-search projection lag:** thay đổi từ database nguồn đến search index.

Ba tiến độ có thể hoàn toàn khác nhau.

### Một query đang chạy trong khi shard relocation

Query coordinator có thể phải tìm bản shard có thể phục vụ, retry một phần query hoặc báo partial failure theo cấu hình/hợp đồng. **Một API search trả HTTP thành công không tự đồng nghĩa mọi shard đã trả dữ liệu** nếu hệ hỗ trợ partial results; cần kiểm tra thông tin failures/response metadata.

### Index được rebuild, không chỉ relocated

Nếu tạo một index layout mới từ database nguồn:

```text
Source snapshot -> search_v2
CDC updates     -> search_v2
Catch up        -> watermark W
Switch alias    -> search_v2
```

cần đảm bảo không bỏ sót ghi giữa snapshot và CDC, không cho event cũ ghi lùi. Một index alias switch theo API hỗ trợ có thể giúp cutover đường query, nhưng **không tự đồng bộ** source database hoặc cache khác.

## 29. Chuyển vùng địa lý và data residency

Di chuyển dữ liệu giữa region/datacenter không chỉ là băng thông:

- RTT lớn làm replay/cutover chậm.
- Egress cost có thể đáng kể.
- Encryption in transit và key management phải được duy trì.
- Data residency hoặc policy hợp đồng có thể cấm copy một số trường sang vùng mới.
- Region mới có thể có read replicas/GSI chưa sẵn sàng.
- Rollback sau cutover phải xét những write mới chỉ tồn tại tại region đích.

### Cutover vùng cần ownership rõ

```text
Before: Region A authoritative
During: Region B shadow/replay
After:  Region B authoritative with new epoch
```

Không dùng hai region cùng ghi độc lập trên một key nếu nghiệp vụ yêu cầu một thứ tự quyết định duy nhất mà không có protocol multi-writer phù hợp.

### Rollback không đơn giản đổi DNS ngược

Nếu region B đã nhận những write mới sau cutover, đưa traffic về region A cũ mà chưa replay các write ấy sẽ làm mất dữ liệu từ góc nhìn client.

**Rollback phải có kế hoạch dữ liệu**, không chỉ thay routing.

## 30. Khi migration thất bại: tiếp tục, rollback hay rebuild?

Một state machine migration cần có đường xử lý lỗi:

```text
COPYING
  |
  +-- network failure -> pause/retry from checkpoint
  +-- source log expired -> resnapshot/rebuild
  +-- bad checksum -> repair/copy again

CATCHING_UP
  |
  +-- replay lag grows -> throttle/tune/abort plan

CUTOVER
  |
  +-- coordinator unavailable -> follow in-doubt protocol
  +-- stale routers -> redirect/refresh/fence

POST-CUTOVER
  |
  +-- destination failure -> failover/recovery per new authority
  +-- need rollback -> replay new writes before transfer back
```

### Trước cutover

Source vẫn là authority trong một số thiết kế, nên có thể **bỏ bản shadow của destination** và thử lại sau. Nhưng phải dọn trạng thái migration đúng cách, không xóa nhầm source.

### Đúng lúc cutover

Trạng thái ownership có thể không rõ với một số client/worker. **Không quyết định owner bằng cảm giác hoặc đồng hồ**, cần metadata authority/term/epoch từ coordinator.

### Sau cutover

Destination đã nhận write mới. Một đường rollback chỉ an toàn khi:

- Giải quyết mọi write đã ACK ở đích.
- Chuyển quyền có epoch mới và fencing.
- Handoff không tạo khoảng mất dữ liệu.
- Read/write về nguồn cũ sau rollback vẫn đáp ứng hợp đồng.

Không xem “source còn copy cũ” là backup nhất quán có thể dùng ngay.

## 31. Đối soát sau khi di chuyển: đếm record là chưa đủ

Một migration có thể báo:

```text
Source count:      1,000,000
Destination count: 1,000,000
```

nhưng vẫn sai vì có một record thiếu và một record trùng, hoặc version của một record đã bị ghi lùi.

### Những phép kiểm tra cần cân nhắc

| Loại kiểm | Ví dụ |
|---|---|
| **Key coverage** | Mọi key thuộc range đã có ở destination |
| **No extra records** | Không copy nhầm key ngoài range |
| **Version alignment** | Destination version tương ứng source ở cùng watermark |
| **Delete/tombstone** | Record đã xóa không hồi sinh |
| **TTL/expiry** | Không kéo dài hạn dùng ngoài ý muốn |
| **Value checksum** | Hash của field đã chuẩn hóa theo schema |
| **Index readiness** | Các query dùng index trả đúng |
| **Unique constraints** | Không có hai owner cùng business key |
| **Transactional effects** | Không có debit thiếu credit hoặc duplicate side effect |
| **Routing** | Client cũ đã được redirect, không còn stale writes được ACK |

### Đừng so hai snapshot ở hai thời điểm rồi kết luận mất dữ liệu

Nếu source vẫn có update, `count(S1 at t1)` và `count(S3 at t2)` có thể khác hợp lệ. Cần một **watermark/snapshot boundary chung** hoặc cơ chế đối soát nhận biết event đang in-flight.

### Repair an toàn

Job repair phải:

1. Xác định source of truth đúng epoch.
2. Đọc lại trạng thái hiện tại trước khi ghi.
3. Chỉ áp write có điều kiện theo version/generation.
4. Không tạo lại side effect khi replay snapshot.
5. Ghi audit `migrationId`, key và nguyên nhân.

Không dùng một bản copy cũ để ghi đè owner mới nếu chưa xác minh commit history.

## 32. Giám sát migration theo ba góc nhìn

### 32.1. Data movement

| Metric | Ý nghĩa |
|---|---|
| `migration_bytes_total` | Dung lượng mục tiêu/công việc |
| `migration_bytes_copied` | Tiến độ snapshot/copy |
| `migration_records_copied` | Số record đã copy |
| `migration_log_backlog_bytes` | Thay đổi phát sinh chưa replay |
| `migration_source_committed_position` | Mốc source authority |
| `migration_destination_applied_position` | Mốc đã áp ở destination |
| `migration_resume_checkpoint_age` | Checkpoint gần nhất |
| `migration_checksum_mismatch_count` | Phát hiện dữ liệu khác |

### 32.2. Routing/correctness

| Metric | Ý nghĩa |
|---|---|
| `stale_epoch_rejection_total` | Request dùng ownership cũ |
| `redirect_total` | Redirect theo shard/range |
| `redirect_loop_failure_total` | Retry quá giới hạn/vòng lặp |
| `write_unknown_outcome_total` | Write không rõ commit |
| `idempotent_replay_total` | Retry cùng logical operation |
| `read_required_version_unavailable_total` | Chưa đáp ứng read barrier |
| `duplicate_key_conflict_total` | Tranh chấp unique key |
| `cross_shard_transaction_abort_total` | Transaction abort khi migration |

### 32.3. Tác động dịch vụ

| Metric | Ý nghĩa |
|---|---|
| `read_latency_p99` | Tail latency khi định tuyến/copy |
| `write_latency_p99` | Ghi có chờ barrier/metadata |
| `read_write_error_rate` | Lỗi theo API và shard |
| `throughput_by_shard` | Sau migration có cân tải không |
| `cpu_disk_network_utilization` | Bottleneck khi copy/replay |
| `hot_partition_qps` | Một partition có còn nóng không |
| `foreground_slo_violation_total` | Vi phạm SLO user |
| `migration_duration_seconds` | Thời gian toàn bộ quá trình |

### Hạn chế cardinality

Không gắn email, số điện thoại, raw key hay hàng triệu `orderId` vào metric label. Dùng `rangeId`, `shardId`, `migrationId` hoặc nhóm tenant có cardinality được kiểm soát; lưu trace chi tiết có quyền riêng.

### Metric cần cùng nghĩa ở source và destination

Không so `received_offset` với `applied_offset` rồi gọi “lag bằng 0” vì chúng không cùng giai đoạn. Định nghĩa rõ **unit, epoch, phase và sampling time** của mỗi metric.

## 33. SLO cho live migration

Một bộ mục tiêu **minh họa**, không phải SLA mặc định của sản phẩm:

```text
Correctness:
  - Zero acknowledged writes lost across cutover
  - Zero duplicate confirmed reservations for same seat
  - No stale owner can commit after new epoch active

Availability:
  - 99.9% foreground GET successful during planned movement
  - Write cutover unavailable window < configured threshold

Latency:
  - Foreground read/write p99 stays within service SLO
  - Routing refresh attempts bounded

Progress:
  - Destination replay backlog decreases before cutover
  - Migration does not outrun source change-log retention

Recovery:
  - Failed migration can resume/abort safely
  - Repair and rollback plans documented
```

Một mục tiêu “zero lost ACK writes” là **bất biến correctness** cần được thiết kế và xác minh theo commit semantics, không thể thay bằng percentile. Ngược lại, p99 latency là SLO thống kê, không bảo đảm từng request luôn dưới ngưỡng.

## 34. Kịch bản thử nghiệm có kiểm soát

Chỉ thực hiện fault injection trên **lab/staging với dữ liệu giả**, không tự ngắt mạng hoặc ép chuyển shard trên production để học.

### Chuẩn bị

```text
Range R: tenant T01, 10,000 fake orders
Source: S1
Destination: S3
Initial owner epoch: 41
Load: 100 read/s + 50 write/s (minh họa)
Operation IDs: unique and stable per logical request
Telemetry: route, epoch, version, commit result, latency
```

### Test A — Đọc liên tục trong lúc copy

Ghi checksum/version của một tập sample. Khi copy chạy, read theo owner/strong path và so với trạng thái có thẩm quyền. Đừng lấy shadow destination làm expected source nếu chưa catch-up.

### Test B — Write tại ranh giới cutover

Gửi nhiều conditional updates liên tiếp cùng key trước, trong và sau cutover. Đảm bảo:

- Không mất version được ACK.
- Không có hai owner cùng commit một expectedVersion xung đột.
- Có retry an toàn khi nhận stale-epoch.
- Read-your-writes sau chuyển owner được giữ theo hợp đồng.

### Test C — Timeout sau commit

Tạo điều kiện mất phản hồi sau khi write commit (nếu harness hỗ trợ). Client retry cùng `operationId`, xác minh side effect chỉ áp một lần về mặt nghiệp vụ.

### Test D — Delete và TTL

Xóa một record ở source trong lúc snapshot copy. Kiểm tra destination không hồi sinh nó. Test TTL và expire semantics khi đồng hồ/streaming chậm.

### Test E — Source/destination crash

Giả lập node chết trước/during/after cutover. Quan sát coordinator chọn owner và quyết định resume/abort, không tự sửa metadata thủ công khi chưa biết protocol.

### Test F — Router cũ

Cố ý giữ metadata epoch 41 ở một test client sau khi cutover epoch 42. Đo redirect, retry và bảo đảm stale owner không ACK một write mới sai.

### Test G — Range scan/pagination

Trong lúc nhiều record được insert/update/delete, quét toàn range bằng cursor/snapshot theo hợp đồng. So các ID với authoritative snapshot tại watermark tương đương, kiểm tra duplicate/missing.

### Test H — Hot key

Di chuyển một range chứa hot key. So QPS, p99, CPU, disk I/O trước/sau. Nếu hot key chỉ chuyển nguồn nghẽn sang destination, cần đổi mô hình dữ liệu/traffic, không tiếp tục di chuyển vô hạn.

## 35. Thử nghiệm history: điều gì phải được ghi?

Một record sự kiện:

```json
{
  "runId": "migration-test-001",
  "operationId": "OP-42",
  "clientId": "C03",
  "kind": "UPDATE",
  "key": "ORD-1001",
  "expectedVersion": 7,
  "returnedVersion": 8,
  "routingEpoch": 41,
  "servingShard": "S1",
  "invokedAt": "2026-11-14T10:00:00.100Z",
  "completedAt": "2026-11-14T10:00:00.190Z",
  "result": "COMMITTED"
}
```

Ghi cả event của migration coordinator:

```json
{
  "migrationId": "M07",
  "rangeId": "R1000-1999",
  "state": "CUTOVER",
  "sourceEpoch": 41,
  "destinationEpoch": 42,
  "finalSourceCommitPosition": 12080,
  "destinationAppliedPosition": 12080
}
```

Các timestamp là **dữ liệu minh họa**. Khi kiểm tra linearizability, cần biết operation nào **hoàn tất trước** operation khác bắt đầu; nếu hai máy có clock skew, dùng controller/causal handoff hoặc đồng hồ được hiệu chỉnh, không so wall-clock vô điều kiện.

### Những câu hỏi mà history giải đáp

- Một write được ACK ở S1 có xuất hiện trong authoritative state S3 sau cutover không?
- Có hai write xung đột cùng được ACK ở epoch khác nhau nhưng không có thứ tự hợp lệ không?
- Read sau ACK theo hợp đồng mạnh có trả version thấp hơn không?
- Retry `OP-42` có áp side effect hai lần không?
- Một delete ở v9 có bị update v8 replay muộn làm hồi sinh không?

Không chỉ dựa vào snapshot cuối: nếu một API đã **trả sai trong 10 giây rồi tự hội tụ**, history mới phát hiện tác động đã thấy bởi người dùng.

## 36. Runbook khi migration làm tăng lỗi hoặc latency

### Bước 1 — Xác định migration/range chịu ảnh hưởng

Ghi `migrationId`, source, destination, range, current epoch và state. Xác nhận request lỗi thực sự thuộc range đó thay vì một sự cố toàn cluster.

### Bước 2 — Kiểm tra control plane

Metadata authority còn hoạt động không? Router đang dùng các epoch nào? Có stale redirect loop hoặc leader election liên tục không?

### Bước 3 — Kiểm tra data plane

Copy progress, log tail backlog, source commit index, destination applied/durable position, network/replay errors, log retention và resource saturation.

### Bước 4 — Phân loại API lỗi

- `NOT_OWNER` an toàn để route lại theo contract?
- `UNKNOWN_COMMIT` cần tra ledger?
- `READ_STALE` do chưa đạt watermark?
- Transaction abort vì ownership đổi?
- Query pagination có missing/duplicate?

Không cấu hình client retry tất cả 500 errors vô hạn.

### Bước 5 — Giảm tải hoặc tạm dừng an toàn

Nếu copy cạnh tranh quá mạnh, giảm concurrency/throttle theo khả năng engine. Nếu log tail đang sắp vượt retention, cần ưu tiên quyết định **tiếp tục catch-up, resnapshot hoặc abort** theo runbook. Không tự xóa change log để giảm disk.

### Bước 6 — Quyết định tiếp tục/abort/rollback

**Trước cutover:** có thể hủy shadow và giữ source authority nếu protocol cho phép.

**Sau cutover:** phải bảo toàn tất cả write mới ở destination trước khi chuyển authority trở lại, không chỉ đổi router.

### Bước 7 — Xác minh phục hồi

So key coverage/version/tombstone ở watermark, traffic distribution, request errors, latency p99 và business invariants. Chỉ đóng incident khi cả consistency và đường đọc/ghi quan trọng đã hồi phục.

## 37. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách thay thế |
|---|---|---|
| “Copy 100% là chuyển owner được” | Bỏ sót write sau snapshot | Snapshot + log tail + cutover watermark |
| “Source và destination cùng có dữ liệu thì cùng nhận write được” | Split-brain, xung đột | Single authority/fencing hoặc giao thức multi-writer |
| “Router cache luôn cập nhật tức thời” | Request vào shard cũ | Epoch, redirect và refresh |
| “Retry mọi lỗi là vô hại” | Double increment/charge | Stable operationId, CAS, status lookup |
| “Timeout nghĩa write không commit” | Retry tạo side effect trùng | Unknown-outcome handling |
| “Received offset = visible offset” | Đọc thiếu update | Phân biệt received/durable/applied/visible |
| “Không cần cutover barrier” | Source commit sau mốc replay | Handoff protocol/forwarding an toàn |
| “Secondary stale read cũng là strong read” | Vi phạm read contract | Read barrier/authoritative route |
| “Copy live record tự bao gồm delete” | Record hồi sinh | Tombstone và delete replay |
| “TTL reset khi copy không sao” | Expire sớm/muộn | Giữ expiry semantics |
| “Giữ unique index local là đủ khi đổi owner” | Double claim khi stale router | Unique authority và ownership fencing |
| “Distributed transaction tự vượt mọi cutover” | In-doubt/abort/partial logic | Dùng engine coordinator và retry contract |
| “Offset pagination quét đúng mỗi record một lần” | Thiếu/trùng do layout/write thay đổi | Snapshot/cursor semantics |
| “Cache và search tự theo kịp sau route đổi” | Stale UI và quyền truy cập | Theo dõi projection riêng |
| “Chuyển hot key sẽ hết điểm nóng” | Hotspot chỉ đổi node | Thay đổi key/model/traffic |
| “Copy nhanh nhất là tốt nhất” | Foreground p99 tăng, replay không kịp | Throttle theo SLO và backlog |
| “Rollback chỉ cần đổi DNS về source” | Mất write mới tại destination | Reverse catch-up và ownership handoff |
| “Node khỏe sau migration nghĩa dữ liệu đúng” | Có thể mất write hoặc index sai | Reconciliation và history |
| “Dùng timestamp lớn nhất để chọn owner” | Clock skew/term sai | Coordinator epoch/term/commit history |
| “Một test happy-path chứng minh online migration an toàn” | Crash/partition làm lộ race | Fault injection và lịch sử request |

## 38. Bài tập thực hành

### Bài 1 — Snapshot cũ

Source có order v7 lúc copy, sau đó ghi v8 và ACK. Destination chỉ có v7 khi route đổi. Hãy xác định invariant bị phá và viết các bước snapshot/CDC/cutover để ngăn mất v8.

### Bài 2 — Hai owner

Metadata authority chuyển `R:S1@41` thành `R:S3@42`. Một app cũ vẫn gửi write đến S1. Phản hồi hoặc hành vi nào S1 được phép thực hiện để tránh hai owner? Vì sao chỉ ghi epoch trong log không đủ?

### Bài 3 — In-flight update

Một update được gửi tới S1 trước cutover nhưng client nhận ACK sau khi S3 đã thành owner. Có chắc đó là lỗi không? Nêu điều kiện theo commit watermark cho phép phản hồi này an toàn.

### Bài 4 — Retry tăng counter

Client gửi `INCR points +10` tới S1, write commit rồi ACK thất lạc. Client refresh route tới S3 và retry. Điều gì có thể sai? Thiết kế operation ID và ledger để một yêu cầu logic chỉ cộng một lần.

### Bài 5 — Received/applied

`sourceCommitted=1000`, `destReceived=1000`, `destDurable=985`, `destApplied=970`. Có nên cho strong read từ đích ngay không? Giải thích từng khoảng cách và điều kiện cần trước cutover.

### Bài 6 — Delete và TTL

S3 copy Product P10 v11 ACTIVE; S1 xóa v12; một update v10 đến trễ. Hãy thiết kế tombstone/version guard và cách giữ TTL/expiry để P10 không hồi sinh.

### Bài 7 — Cursor query

Một API phân trang theo OFFSET trong lúc các record đổi shard và có nhiều insert/delete. Nêu các kiểu thiếu/trùng có thể xảy ra và phân biệt keyset pagination với consistent snapshot.

### Bài 8 — Unique constraint

Hai router giữ metadata khác epoch. Một request claim username trên S1, request khác trên S3. Phân tích vì sao unique index **trên từng shard** chưa đủ, và cách single-owner guard/fencing bảo vệ.

### Bài 9 — Multi-shard transaction

Một giao dịch debit A ở S1 và credit B ở S2; range của A chuyển sang S3 khi giao dịch đang prepare. Những trạng thái in-doubt có thể xuất hiện? Vì sao retry từng update riêng lẻ là nguy hiểm?

### Bài 10 — Copy backlog

Backlog là 3.000 MB, source sinh 40 MB/s và destination replay 55 MB/s. Ước lượng catch-up time; nếu destination giảm còn 35 MB/s thì điều gì xảy ra? Các metric nào cần quan sát trước cutover?

### Bài 11 — Redis MOVED/ASK

Một Redis Cluster slot đang chuyển A → B. So sánh `MOVED` và `ASK`, giải thích vì sao khi nhận `ASK` cần `ASKING` và không nên cập nhật slot map vĩnh viễn ngay.

### Bài 12 — Cassandra bootstrap

Thêm node vào Cassandra cluster làm một token range đổi replica placement. Hãy liệt kê những thông tin về CL, streaming, hints/repair và topology cần biết trước khi kết luận read mới đã đúng.

### Bài 13 — MongoDB resharding

Phân biệt chuyển chunk trong layout cũ với resharding đổi shard key. Nêu ảnh hưởng có thể tới định tuyến, index uniqueness, transaction và ứng dụng đọc từ secondary.

### Bài 14 — Search index

Source đã cutover, nhưng search vẫn hiển thị version cũ. Làm sao tách nguyên nhân nguồn migration, CDC projector backlog và search refresh? Có thể dùng search để xác nhận quyền truy cập mới nhất không?

### Bài 15 — Hot key

Một hot key có 20.000 writes/s. Chuyển nó từ S1 sang S3 làm CPU S1 giảm nhưng S3 tăng tới 95%. Hãy giải thích vì sao rebalancing chưa giải quyết bottleneck và đề xuất hai mô hình thay đổi traffic hoặc dữ liệu.

### Bài 16 — Router loop

S1 chỉ sang S3, S3 chỉ ngược về S1. Hãy thiết kế giới hạn redirect, kiểm tra epoch và cách trả lỗi hữu ích mà không tạo retry storm.

### Bài 17 — Reverse rollback

Migration đã cutover S1 → S3, và S3 nhận thêm 100 write mới. Người vận hành muốn đổi router trở lại S1. Điều gì phải làm trước để không mất write? Thiết kế một reverse handoff có epoch mới.

### Bài 18 — Kiểm tra recovery

Sau khi mạng phục hồi, tất cả node báo healthy, nhưng một API trả order v8 trong khi nguồn có v10. Hãy mô tả cách xác định read path, source version, replica lag, cache/index và yêu cầu minVersion.

### Bài 19 — Lập test plan

Thiết kế một kịch bản lab di chuyển 10.000 document từ S1 sang S3 dưới tải đọc/ghi. Bao gồm fault injection, việc ghi history, SLO, kiểm tra no-lost-ACK, tombstone, metadata cũ, transaction, pagination và cleanup.

### Bài 20 — Chọn chính sách phục vụ

Ba API: `GET catalog`, `POST reserve-seat` và `GET my-order-after-submit`. Trong cutover, API nào được phép stale, API nào cần conditional authority, API nào cần minVersion token? Nếu không đảm bảo được, phản hồi nào nên được trả?

## 39. Quy trình thiết kế nhanh

Khi chuẩn bị di chuyển một range/shard đang phục vụ production, hãy trả lời:

1. **Đơn vị di chuyển là gì?** Key, range, partition, replica hay toàn layout shard key?
2. **Source of truth ở đâu trước và sau?** Owner/epoch có được duy trì bởi coordinator không?
3. **Tại thời điểm snapshot**, làm sao ghi lại mọi write phát sinh sau đó mà không có gap?
4. **Destination đã nhận, durable, apply và visible tới đâu?** Có watermark/epoch hợp lệ không?
5. **Strong reads và writes** được route tới đâu trong từng phase?
6. **Các request đang chạy dở** được hoàn tất, chờ hay retry theo hợp đồng nào?
7. **Client dùng metadata cũ** nhận redirect gì? Có chống loop và retry storm?
8. **Operation không idempotent** có key/ledger để xử lý unknown commit không?
9. **Delete, TTL, unique guard, index và transaction** được bảo vệ ra sao?
10. **Scan/cursor** có snapshot và sort key ổn định không?
11. **Copy/streaming** có làm p99 hoặc log backlog vượt giới hạn không?
12. **Hotspot** có được phân tán thực sự hay chỉ chuyển sang node khác?
13. **Khi lỗi trước cutover**, có abort an toàn không? **Sau cutover**, rollback cần replay dữ liệu mới thế nào?
14. **Sau migration**, lấy gì chứng minh không mất ACK write, không hồi sinh delete, không duplicate business effect?
15. **Runbook và metrics** có đủ để điều tra theo migrationId/rangeId/epoch không?

Nếu một câu hỏi quan trọng chưa rõ, kế hoạch migration vẫn còn rủi ro cần giải quyết trước khi chuyển traffic.

## 40. Kết luận

**Truy cập trong khi dữ liệu đang di chuyển** không chỉ là bài toán copy nhanh từ shard A sang shard B. Đây là bài toán phối hợp **dữ liệu, quyền sở hữu, định tuyến và lịch sử thao tác** khi các client vẫn đang đọc/ghi.

Những nguyên tắc quan trọng nhất:

- **Snapshot không bao gồm mọi write mới.** Cần theo dõi thay đổi sau snapshot, replay theo thứ tự và có cutover watermark.
- **Có nhiều bản copy nhưng không được mơ hồ về authority.** Ownership epoch/fencing hoặc giao thức multi-writer phù hợp ngăn nguồn cũ và mới cùng ACK xung đột.
- **Cutover không phải một lệnh sửa DNS đơn giản.** Cần xử lý in-flight operations, write barrier/handoff, stale router, redirect và retry an toàn.
- **Nhận log không đồng nghĩa có thể đọc bản mới.** Phân biệt received, durable, applied và visible.
- **Timeout có thể che giấu write đã commit.** Dùng request/operation ID ổn định, CAS, ledger và cách xác minh unknown outcome.
- **Delete, TTL, unique constraints, range scan và transaction** phải được kiểm tra riêng; “record count bằng nhau” không đủ.
- **Rebalancing và hotspot là hai bài toán liên quan nhưng khác nhau.** Chuyển một hot key có thể chỉ chuyển điểm nghẽn sang shard khác.
- **Hệ quản trị có giao thức riêng.** MongoDB chunk migration/resharding, Redis Cluster `MOVED/ASK`, Cassandra token streaming và các dịch vụ managed không có cùng routing/consistency semantics.
- **Thành công được đo bằng hành vi của ứng dụng.** Không mất write đã ACK, không có hai owner xung đột, read path đúng hợp đồng, tail latency chấp nhận được và có thể phục hồi khi migration lỗi.

Trước khi bấm “move shard”, hãy xác định:

> “Trong từng giai đoạn, **ai đang có quyền nhận ghi**, bản đích đã **áp dụng đến mốc nào**, client có metadata cũ sẽ được xử lý thế nào, và sau khi chuyển owner liệu có thể chứng minh **mọi write hợp lệ đã được giữ, mọi delete vẫn có hiệu lực, mọi retry không tạo tác động trùng** hay không?”

Đó là nền tảng để cân bằng tải NoSQL khi hệ vẫn phục vụ traffic, mà không đánh đổi tính đúng nghiệp vụ lấy một biểu đồ phân phối shard đẹp hơn.
