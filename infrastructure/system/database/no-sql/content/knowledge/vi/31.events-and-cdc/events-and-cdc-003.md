# Snapshot ban đầu và chuyển tiếp sang luồng thay đổi liên tục

Khi triển khai **Change Data Capture (CDC)** cho một hệ thống NoSQL đang hoạt động, bài toán thường không bắt đầu ở việc đọc sự kiện mới nhất. Một downstream consumer như search index, cache, analytics warehouse, read model hoặc dịch vụ đồng bộ dữ liệu cần **toàn bộ trạng thái hiện có** trước khi tiếp tục áp những mutation phát sinh trong tương lai. Bước đọc dữ liệu sẵn có được gọi là **initial snapshot / bootstrap / backfill**; bước theo dõi các mutation được commit sau đó là **continuous change streaming**.

Vấn đề khó nằm ở **ranh giới giữa hai giai đoạn**. Nếu snapshot mất hai giờ để quét một tỷ documents, database vẫn nhận thêm writes trong hai giờ ấy. Một bản ghi có thể được chụp trước khi bị update, bị xóa trong lúc quét, hoặc được tạo sau khi một phân đoạn snapshot đã qua. Một consumer nối snapshot với CDC sai cách có thể:

- **Bỏ sót** một update xảy ra giữa lúc lấy snapshot và lúc bắt đầu đọc stream.
- **Hồi sinh** một record đã bị xóa vì bản snapshot đến sau delete event.
- **Ghi đè trạng thái mới** bằng bản cũ do các sự kiện đến sai thứ tự.
- Áp một mutation **hai lần** khi snapshot và CDC có khoảng chồng lấp.
- Xem các offset từ **hai shards không liên quan** như một thứ tự toàn cục.
- Không phục hồi được khi stream retention hết hạn trong lúc snapshot kéo dài.

Bài học thuộc chương **Sự kiện và CDC** của module **Database No SQL**, tập trung vào cách thiết kế **consistent cut**, **snapshot boundary / watermark**, **vị trí log / resume token**, **idempotency**, **checkpoint**, và cơ chế chuyển giao từ tải toàn bộ sang streaming sao cho không có khoảng trống dữ liệu.

> **Nguyên tắc cốt lõi:** Một snapshot và một change stream chỉ ghép thành trạng thái đúng khi tồn tại **giao thức nối hai nguồn**: xác định điểm ranh giới có ý nghĩa theo sản phẩm, không bỏ sót writes, xử lý chồng lấp và áp dụng dữ liệu theo thứ tự/phiên bản thích hợp. Không được suy rằng `scan table; then subscribe to changes` luôn an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **snapshot hiện trạng**, **consistent snapshot**, **incremental snapshot** và **CDC stream**.
2. Giải thích ba rủi ro lớn khi cutover: **gap, overlap và reordering**.
3. Phác họa một **điểm cắt nhất quán** giữa trạng thái được snapshot và lịch thay đổi được replay.
4. Hiểu phạm vi của **LSN, log offset, change-stream resume token, shard sequence và high/low watermark**.
5. Thiết kế hai họ giải pháp: **snapshot tại mốc log xác định** và **capture stream từ trước, buffer/merge cùng snapshot**.
6. Dùng **primary key, source version, tombstone, transaction metadata và idempotent upsert** để tránh đi lùi trạng thái.
7. Hiểu điều kiện để xử lý **snapshot theo chunks** và **incremental snapshots có low/high watermark**.
8. Phân tích trường hợp **log retention, schema change, partition move, replica failover, connector restart**.
9. Phân biệt ordering theo **một key, partition, transaction** và across shards.
10. Xây dựng **runbook, metrics và fault-injection tests** cho quy trình bootstrap rồi stream dài hạn.

## 2. Tình huống xuyên suốt: dựng Order Search từ NoSQL

Một Order Service lưu khoảng 80 triệu đơn hàng trong một document database. Search Service cần tạo Elasticsearch/OpenSearch index phục vụ lọc trạng thái, khách hàng và thời gian:

~~~text
Source NoSQL orders
  key = (tenantId, orderId)
  status, total, updatedAt, version, ...
         |
         | initial snapshot + continuous CDC
         v
Order Search Index
  one search document per order
~~~

Trong lúc bootstrap, source vẫn nhận:

~~~text
10:00:00   Order O101 = CREATED, version 3
10:00:03   O101 becomes PAID, version 4
10:00:05   O102 is created, version 1
10:00:10   O101 is deleted
10:00:12   O103 is shipped
~~~

Snapshot có thể quét hàng triệu rows trong nhiều giờ. Không thể ngăn người dùng đặt hàng, thanh toán hoặc hủy trong suốt thời gian này.

Mục tiêu hợp lý không phải “target ngay lập tức giống source trong mọi millisecond”, mà là:

> Sau khi bootstrap chuyển sang streaming thành công, và khi consumer đã theo kịp mọi mutation được source công bố tới một mốc được xác minh, **target phản ánh đúng trạng thái nguồn tại mốc ấy**, theo mô hình consistency và transaction scope đã chọn.

Nếu source tiếp tục ghi, target có thể có **replication lag**; hệ phải đặt SLO cho độ trễ và giải thích rõ điều nào chỉ là eventual, điều nào phải có read-your-writes hoặc stronger consistency.

### 2.1. Các thành phần trong pipeline

~~~mermaid
flowchart LR
    DB["NoSQL Source"] --> SNAP["Snapshot Scanner"]
    DB --> CDC["CDC / Change Stream Reader"]
    SNAP --> N["Normalization + Schema Mapping"]
    CDC --> N
    N --> APPLY["Ordered / Idempotent Applier"]
    APPLY --> IDX["Target Read Model"]
    CDC --> POS["Source Position Checkpoint"]
    SNAP --> CUR["Snapshot Chunk Progress"]
    POS --> REC["Recovery Controller"]
    CUR --> REC
~~~

**Snapshot scanner:** Quét dữ liệu ban đầu theo key range, token range, partition hay các chunk có checkpoint.

**CDC reader:** Đọc log/change feed, duy trì vị trí nguồn và xử lý lifecycle của stream/shards.

**Normalization:** Chuyển full-state record, event delta, delete marker và schema version về dạng target hiểu được.

**Applier:** Thực thi upsert/delete có bảo vệ ordering, version và idempotency.

**Coordinator/checkpoint:** Ghi trạng thái bootstrap/stream để crash/restart không gây gap.

### 2.2. Snapshot và CDC mang thông tin khác nhau

| Đặc tính | Snapshot | Continuous CDC |
| --- | --- | --- |
| Đơn vị thường thấy | Bản ghi hiện có | Mutation, transaction, event/change record |
| Mục tiêu | Nạp trạng thái ban đầu | Theo dõi thay đổi sau đó |
| Coverage | Rows nhìn thấy theo snapshot semantics | Changes còn trong log/stream retention |
| Thứ tự | Scan order không phải commit order | Theo log/shard/transaction scope được hỗ trợ |
| Delete đã xảy ra trước snapshot | Thường không còn bản ghi | Có thể đã nằm ngoài cửa sổ stream |
| Delete xảy ra khi đang quét | Có race | Cần delete event/tombstone |
| Khả năng restart | Chunk cursor/checkpoint | Offset/resume token/shard cursor |
| Khả năng phục hồi | Re-scan hoặc resume chunk | Replay từ offset còn retained |
| Rủi ro riêng | Không nhất quán theo thời điểm, page duplicates/misses | Retention, log reordering, retry, schema mismatch |

## 3. Thất bại số một: snapshot trước rồi mới bật CDC

Thiết kế trực giác:

~~~text
10:00:00   Start scanning orders.
10:40:00   Finish scanning all orders.
10:40:01   Create change-stream subscription at "now".
~~~

Giữa **10:00:00 và 10:40:01** có thể có hàng triệu writes. Nếu change stream chỉ phát các events **sau lúc subscribe**, thì writes trong khoảng này **không có nguồn nào bảo đảm được áp ở target**.

### 3.1. Timeline một update bị mất

~~~text
Time       Source Order O101      Snapshot      CDC
----       -----------------      --------      ---
t0         version=3              starts
t1         version=3              reads O101 v3
t2         version=4              already passed O101
t3         version=4              finishes
t4         version=4                            subscribes NOW
~~~

Target có O101 v3 nhưng event chuyển v3→v4 xuất hiện ở t2 **không nằm trong snapshot nữa, cũng không nằm trong stream bắt đầu t4**.

### 3.2. Một record mới cũng có thể bị bỏ sót

Giả sử scanner đã đi qua key range `K1000-K2000`, sau đó source insert record mới có key `K1500`. Nếu scan không giữ một snapshot nhất quán và CDC chỉ bắt đầu sau khi scan hoàn tất, record có thể không xuất hiện ở cả hai nguồn.

### 3.3. Delete còn nguy hiểm hơn

Scanner đã đọc O101, sau đó source xóa O101 trước khi CDC subscription hoạt động. Target tiếp tục chứa O101 **mãi mãi**, vì full scan ở những lần sau có thể không diễn ra.

### 3.4. “Quét lại các record có updatedAt lớn” chưa chắc đủ

Một số đội xử lý gap bằng truy vấn `updatedAt >= snapshotStart`:

- Nếu timestamp từ client, clock skew có thể làm sự kiện bị gắn giờ cũ.
- Delete có thể không còn row để truy vấn.
- Ghi đè/restore/schema transformation có thể không cập nhật `updatedAt` như kỳ vọng.
- Index/update timestamp có thể không transactional với mutation chính.
- Có thể phát hiện nhiều thay đổi hiện trạng nhưng **không khôi phục đủ chuỗi events** nếu consumers cần delta/transaction history.

Đó có thể là **chiến lược reconciliation bổ trợ**, không thay một CDC cutover protocol có chứng cứ.

## 4. Thất bại số hai: bật CDC sớm nhưng áp dữ liệu sai thứ tự

Đội vận hành sửa gap bằng cách subscribe stream từ 10:00:00 rồi quét snapshot, nhưng cho stream worker và snapshot worker **ghi thẳng vào target không có version guard**.

~~~text
t0  Start CDC reader.
t1  Source O101 version=3.
t2  Update O101 to version=4; CDC event arrives at target.
t3  Target upserts O101 version=4.
t4  Slow snapshot worker finally writes old O101 version=3.
~~~

Kết quả target **đi lùi từ v4 về v3** dù không bỏ sót event nào.

### 4.1. Delete có thể bị hồi sinh

~~~text
t1 Snapshot scanner reads O101 v3 into a buffered page.
t2 Source deletes O101.
t3 CDC delete reaches target -> remove O101.
t4 Snapshot buffered page flushes O101 v3 -> resurrects O101.
~~~

Nếu không giữ delete tombstone hoặc không có chiến lược áp event theo causal/commit ordering, target có thể sai vĩnh viễn.

### 4.2. Overlap không mặc nhiên xấu

Quy trình an toàn có thể **cố tình capture trùng** một số changes ở cả snapshot và CDC để tránh gap. Nhưng **overlap phải đi kèm idempotency, stable event identity và đúng thứ tự**. Hệ có thể chấp nhận “at least once” ở đường vận chuyển, nhưng không được áp một business delta hai lần.

### 4.3. Ba loại lỗi riêng

| Lỗi | Ví dụ | Bảo vệ |
| --- | --- | --- |
| **Gap** | Update xảy ra sau snapshot read nhưng trước stream start | Consistent cut / capture-before-snapshot / replay |
| **Overlap** | Cùng state xuất hiện trong snapshot và CDC | Idempotency/version guard/dedup |
| **Reordering** | CDC v4 đến trước snapshot v3; delete trước old upsert | Ordered apply, compare source versions, barrier/buffering |

## 5. Mục tiêu hình thức: một điểm cắt nhất quán

Giả sử log nguồn có chuỗi các committed mutations:

\[
C_1,C_2,\ldots,C_n,C_{n+1},\ldots
\]

Với một điểm cắt \(L_0\), ta muốn snapshot \(S(L_0)\) biểu diễn **trạng thái nguồn sau tất cả changes thuộc prefix đã commit tới \(L_0\)**, và **không chứa effects của những changes sau \(L_0\)**, theo phạm vi ordering và transaction semantics của engine.

Target về lý thuyết:

\[
T = \operatorname{apply}(S(L_0), C_{n+1},C_{n+2},\ldots)
\]

trong đó \(L_0\) đặt sau \(C_n\), và stream bắt đầu từ **vị trí tiếp theo hoặc vị trí bao gồm \(L_0\)** theo API contract để không có gap.

### 5.1. Điểm cắt phải cùng phạm vi với snapshot

Nếu DB là multi-shard và không có global transactional snapshot, **một số log offset đơn lẻ không tự mô tả trạng thái nhất quán toàn cluster**.

Có thể cần:

- Transactionally consistent snapshot được engine hỗ trợ.
- Một **vector of positions** theo shard/partition/stream.
- Snapshot theo partition kèm checkpoint và merge protocol.
- Một connector quản lý barrier/watermark theo các nguồn.
- Một giai đoạn quiesce writes nếu business cho phép và không có cơ chế tốt hơn.

### 5.2. Khái niệm consistent cut

Một tập sự kiện tạo **consistent cut** nếu mọi causal predecessor của một event trong tập cũng nằm trong tập. Nếu snapshot “đã thấy shipment created” nhưng chưa thấy order confirmed mà shipment phụ thuộc vào, đó có thể là một trạng thái không phù hợp với causal consistency mong muốn.

Một transactional snapshot còn phải bảo toàn **atomic visibility** của transactions trong phạm vi database cam kết. Không được snapshot nửa transaction hai records rồi gọi là “cùng thời điểm”.

### 5.3. Snapshot hoàn tất lúc nào không bằng cutover timestamp

~~~text
Snapshot began:  10:00
Snapshot ended:  11:30
Position L0:     source commit position with documented meaning
~~~

Không được tự coi `11:30` là log offset, và không được tự convert wall-clock lúc scanner kết thúc sang vị trí stream mà engine không hỗ trợ.

## 6. Source positions: LSN, offsets, resume tokens, sequence numbers

| Vị trí/metadata | Ví dụ khái niệm | Phạm vi và cảnh báo |
| --- | --- | --- |
| **Log Sequence Number (LSN)** | Log position trong WAL/oplog | Có thể có scope stream/instance hoặc transaction; xem engine |
| **Change stream resume token** | Opaque token | Phải lưu nguyên, không tự tính bằng timestamp |
| **Partition offset** | `(topic, partition, offset)` | Không có global order giữa partitions |
| **DynamoDB Streams sequence** | Sequence trong một stream shard | Shard lifecycle/lineage; không global table counter |
| **Commit timestamp** | Engine-assigned time | Scope, granularity và causal rules tùy engine |
| **Aggregate version** | `Order O101: 4` | Thứ tự mutation cùng authoritative aggregate |
| **Snapshot chunk cursor** | Last key/range completed | Cho biết tiến độ scan, **không** tự là CDC position |
| **Watermark/barrier** | Position đánh dấu đoạn lịch stream | Cần protocol định nghĩa low/high semantics |

### 6.1. Đừng so những thứ không cùng miền

~~~text
Kafka partition 0 offset 900
Kafka partition 1 offset 800
~~~

Không thể kết luận event ở offset 900 xảy ra **sau** event offset 800 trên partition khác. Tương tự, một DynamoDB stream shard sequence không tự là order chung cho mọi shard.

### 6.2. Stable source identity

Nếu một connector đọc nhiều clusters/collections/tables, checkpoint cần lưu đủ identity:

~~~json
{
  "sourceCluster": "orders-primary",
  "namespace": "app.orders",
  "sourcePartition": "shard-7",
  "position": "opaque-engine-position",
  "connectorGeneration": 12
}
~~~

Nếu chỉ lưu `offset=1000` nhưng không lưu partition/source identity, restart có thể resume sai nguồn hoặc tưởng đã xử lý dữ liệu khác.

### 6.3. Resume token thường là opaque

Không parse resume token thành số thứ tự để **tự cộng 1**, không tạo token “gần đúng” từ thời gian hiện tại. Hãy dùng đúng API `resumeAfter`, `startAfter`, `startAtOperationTime` hoặc tương đương **chỉ trong điều kiện sản phẩm cho phép**.

### 6.4. Phiên bản aggregate không thay log position

`Order O101 version=4` cho biết một thứ tự của **Order O101** nếu authority duy nhất cấp version. Nó không giúp resume CDC từ đúng mutation của mọi Orders trong shard. Hai trường phục vụ hai mục đích khác nhau.

## 7. Những tính chất cần khẳng định trước khi xây pipeline

Thiết kế nên viết rõ:

**Completeness**

> Mọi committed change thuộc phạm vi đồng bộ sau mốc bootstrap cuối cùng sẽ được phản ánh hoặc có cơ chế phát hiện và phục hồi nếu chưa phản ánh.

**No stale overwrite**

> Một snapshot row hoặc CDC event cũ không thể ghi đè một phiên bản newer đã được target chấp nhận trong cùng nguồn/order scope.

**Delete correctness**

> Bản xóa đã commit không bị một old snapshot/upsert hồi sinh sau đó.

**Idempotent replay**

> Replay cùng source event hoặc snapshot chunk không làm thay đổi kết quả nghiệp vụ ngoài một lần theo target semantics.

**Recoverability**

> Sau crash, pipeline có checkpoint và retained log/rebuild plan đủ để tiếp tục mà không “nhảy qua” những thay đổi chưa được áp.

**Transaction consistency**

> Nếu target cần thấy nhiều records đổi cùng transaction, giao thức apply phải giữ visibility/atomic grouping theo mức yêu cầu.

**Convergence**

> Khi source ngừng đổi và hệ downstream cùng các dependencies phục hồi, target cuối cùng có cùng trạng thái dữ liệu đã định nghĩa.

Các tính chất này chỉ có ý nghĩa khi **phạm vi và giả định** được nêu rõ: one key, one partition, one collection, cross-shard, single-writer hay multi-region concurrent writers.

## 8. Thuật toán A: consistent snapshot tại một mốc log xác định

Đây là mô hình khái niệm dễ lý luận nhất **nếu nguồn hỗ trợ** lấy một snapshot phản ánh trạng thái tại chính mốc log có thể dùng để resume CDC.

### 8.1. Quy trình

1. **Thiết lập điểm cut \(L_0\)** qua protocol nguồn; pin/read một consistent snapshot tại cùng boundary.
2. Lưu mốc \(L_0\) một cách bền vững trong bootstrap metadata.
3. Quét các records từ **snapshot \(S(L_0)\)** theo chunks.
4. Ghi target với idempotent upserts và checkpoint chunk progress.
5. Sau khi snapshot hoàn tất ở target, đọc CDC changes **sau \(L_0\)** hoặc từ vị trí bắt đầu hợp lệ theo contract, chống duplicate nếu có overlap.
6. Replay đến khi bắt kịp live stream, rồi chuyển state thành `STREAMING`.
7. Tiếp tục apply và checkpoint theo source positions.

~~~mermaid
sequenceDiagram
    participant DB as Source DB
    participant Scan as Snapshot Scanner
    participant CDC as Change Reader
    participant Target as Target
    DB-->>Scan: Consistent snapshot S(L0)
    DB-->>CDC: Durable position L0
    Scan->>Target: Upsert rows from S(L0) in chunks
    Scan->>Target: Commit snapshot-complete barrier
    CDC->>DB: Read log after L0 (documented position rule)
    DB-->>CDC: Changes C after L0
    CDC->>Target: Apply changes in source order
    CDC->>CDC: Checkpoint applied position
~~~

### 8.2. Vì sao không có gap?

Nếu \(S(L_0)\) **thật sự** chứa toàn bộ changes tới \(L_0\), còn stream cung cấp **mọi committed change sau \(L_0\)**, thì một mutation sẽ thuộc snapshot hoặc stream (hoặc cả hai nếu API có overlap nhưng đã dedup).

Đây là lập luận **dựa trên preconditions của protocol**; không có những preconditions ấy thì kết luận không còn đúng.

### 8.3. Vì sao snapshot không được “trôi theo từng trang”?

Nếu scanner đọc page 1 tại 10:00, page 2 tại 10:20 trên **live read không có cùng snapshot boundary**, hai trang có thể chứa trạng thái của các thời điểm khác nhau. Gọi đó là \(S(L_0)\) là sai.

Với những hệ không hỗ trợ consistent snapshot dài hoặc scan version cố định, phải dùng chiến lược khác: **capture-then-merge**, **incremental snapshot**, hoặc một bước reconciliation có protocol.

### 8.4. Log retention phải bao phủ snapshot duration

Giả sử snapshot chạy 3 giờ và CDC reader **chưa tiêu thụ log** cho tới khi snapshot xong, hệ phải bảo đảm log changes từ \(L_0\) còn retained đủ lâu. Nếu stream giữ tối đa 1 giờ, \(L_0\) có thể đã hết hạn trước cutover.

Một lựa chọn khác là **đọc và persist/buffer stream song song trong suốt snapshot**, hoặc mở rộng retention theo sản phẩm. Không thể khôi phục một mốc đã bị cắt bỏ chỉ bằng một resume token đã lưu.

### 8.5. Không giữ transaction snapshot vô hạn

Một database có thể cho snapshot read nhưng việc giữ transaction/snapshot nhiều giờ gây pressure lên MVCC history, oplog, compaction hoặc giới hạn transaction lifetime. Cần kiểm tra operational cost và dùng incremental snapshots nếu không thể pin snapshot dài.

## 9. Thuật toán B: bắt stream từ trước, sau đó snapshot và hòa giải

Khi không thể tạo một consistent snapshot toàn bảng tương ứng một log position, nhiều connector dùng biến thể:

1. Thiết lập CDC subscription/checkpoint **trước khi scanner có thể bỏ qua bất kỳ mutation nào**.
2. Đảm bảo những change records đến trong lúc scan **không bị mất do retention hoặc buffer overflow**.
3. Snapshot dữ liệu theo ranges/chunks, đồng thời thu các change events liên quan.
4. Dùng source versions, event positions, low/high watermarks hoặc giao thức dedup được chứng minh để xử lý **các thay đổi chồng lấp với snapshot**.
5. Khi chunk/snapshot đã có coverage và CDC catch-up đủ, chuyển sang streaming liên tục.

### 9.1. Điểm quan trọng: bắt sớm thôi chưa đủ

Nếu snapshot không nhất quán và target được cho **apply tất cả buffered events sau đó một cách mù quáng**, một event cũ vẫn có thể đè state snapshot mới:

~~~text
t0  Stream subscribes.
t1  Source O101 v4 -> v5; event E5 buffered.
t2  Snapshot scanner reads O101 v5.
t3  Target writes snapshot v5.
t4  Relay applies E5 as a "set v5" -> same state, harmless if idempotent.
~~~

Trong ví dụ này may mắn không sao. Nhưng nếu E5 là `INCREMENT balance by 10` và snapshot đã bao gồm increment, apply delta lần nữa là **sai**. Nếu source có thêm version v6 trước scanner read, việc apply E5 sau snapshot v6 có thể **đi lùi**.

**Bảo đảm đúng** cần gắn với loại event (full state vs delta), snapshot row version và event ordering, hoặc thuật toán low/high watermark mà sản phẩm/connector thực sự hỗ trợ.

### 9.2. Giải pháp một: snapshot rows mang source version có thứ tự

Nếu mỗi entity có version tăng đơn điệu **được cấp atomically bởi một authority**, scanner ghi:

~~~json
{
  "key": "tenant-a/O101",
  "sourceVersion": 6,
  "snapshotValue": {"status": "SHIPPED"}
}
~~~

CDC event E5 đến sau snapshot v6 thì **không được ghi đè v6**, kể cả event tới target muộn.

Điều kiện:

- `sourceVersion` là **thứ tự commit đúng phạm vi key**, không phải timestamp từ client.
- Snapshot row/version được đọc atomically với giá trị.
- Delete được lưu thành tombstone có version phù hợp.
- Mọi updates đồng nhất qua path có version guard.
- Delta events không được bỏ vô điều kiện nếu target phụ thuộc chuỗi deltas.

### 9.3. Giải pháp hai: low/high watermark theo chunk

Một connector có thể bao một snapshot chunk bằng **hai markers/barriers** trên stream hoặc bằng những mốc commit tương đương:

~~~text
Stream ---- Low watermark L ---- [chunk scan] ---- High watermark H ---->
                          \          |
                           \         +-- snapshot rows for key range R
                            \-- CDC events in interval (L,H]
~~~

Những keys được CDC thay đổi trong khoảng mở của chunk phải được **hòa giải theo thuật toán**: có thể giữ bản CDC mới nhất, loại snapshot row bị invalidated, hoặc cập nhật snapshot state theo version/position. Chỉ khi chunk được finalize theo protocol mới phát các snapshot records hợp lệ.

**Cảnh báo:** Các công cụ như Debezium có thuật toán incremental snapshot/watermark riêng; không tự xem mọi low/high markers là cùng một định nghĩa. Muốn áp dụng phải đọc đúng connector version và algorithm.

### 9.4. Buffer cần durable hoặc có replay

Nếu CDC buffer chỉ nằm trong RAM và process crash, bootstrap mất các changes xảy ra trong snapshot. Nếu không thể resume từ log vì retention hết, cần **restart snapshot hoặc reconcile từ authoritative source**.

Có thể dùng:

- Durable log/broker topic làm intermediate buffer.
- CDC reader với offset/checkpoint đúng.
- Snapshot chunk metadata và replay từ vị trí tương ứng.
- Controlled pause/resume khi buffer gần đầy.

### 9.5. Một thao tác CRUD có thể xuất hiện hai lần

Overlap có thể tạo:

~~~text
Snapshot O101 version 6
CDC event O101 version 6
~~~

Đối với **upsert full state** versioned, apply idempotently có thể chấp nhận. Đối với **delta/counter**, phải dùng event ID và exactly-once effect theo transaction của target hoặc một cơ chế merge được chứng minh, không chỉ “thấy version bằng nhau thì bỏ” nếu event/snapshot semantics không tương thích.

## 10. Snapshot theo chunks: không thể coi toàn bảng là một page

Một bảng 500 triệu rows không thể quét bằng một request và giữ tất cả trong RAM. Các hệ thực thường quét **theo chunk/page/range**:

~~~text
Range 1: [K0000, K1000)
Range 2: [K1000, K2000)
Range 3: [K2000, K3000)
...
~~~

Hoặc dùng:

- Partition-key/token ranges.
- Shard/chunk metadata.
- Keyset pagination theo primary key.
- Driver paging state/continuation token.
- Scan segments nếu API hỗ trợ.

### 10.1. Định danh chunk phải ổn định

Ví dụ metadata:

~~~json
{
  "bootstrapRunId": "bootstrap-2026-11-14-01",
  "source": "orders-cluster/app.orders",
  "rangeStartInclusive": "tenant-a/O1000",
  "rangeEndExclusive": "tenant-a/O2000",
  "chunkId": "chunk-017",
  "status": "IN_PROGRESS",
  "snapshotLowWatermark": "opaque-source-position-L",
  "snapshotHighWatermark": null,
  "lastCommittedKey": "tenant-a/O1468",
  "readRows": 468,
  "appliedRows": 468
}
~~~

Các giá trị này minh họa một state model; nhiều database dùng **opaque paging token** thay vì key string. Không nên sửa tay một paging token nếu API không cho phép.

### 10.2. Pagination bằng offset có thể không ổn định

Với một collection bị insert/delete liên tục:

~~~text
SELECT ... SKIP 10000 LIMIT 1000
~~~

một delete ở những records trước offset khiến các dòng dịch vị trí; page sau có thể **bỏ sót hoặc đọc trùng**. Keyset/range paging thường hữu ích hơn nhưng vẫn phải xét **consistent read semantics** và changes trong lúc quét.

### 10.3. Cùng key được đọc hai lần không nhất thiết nguy hiểm

Nếu snapshot chunk bị retry:

~~~text
First attempt writes O101 v6.
Process crashes before recording chunk COMPLETE.
Second attempt writes O101 v6 again.
~~~

Với target **idempotent upsert** và version guard đúng, lần thứ hai không làm thay đổi kết quả. Ngược lại, nếu snapshot row được xử lý bằng `incrementTotal()` hay `sendEmail()`, replay sẽ gây duplicate side effect.

**Snapshot nên tái tạo state, không kích hoạt ngẫu nhiên side effects chỉ vì một record được đọc lần đầu.**

### 10.4. Checkpoint chunk sau khi target apply bền

Không làm:

~~~text
Mark chunk COMPLETE.
Then write its rows to target.
~~~

Nếu crash giữa hai bước, connector tin chunk đã xử lý nhưng target thiếu dữ liệu.

An toàn hơn về mặt at-least-once:

~~~text
Write snapshot rows idempotently.
Confirm target persistence at required level.
Mark chunk COMPLETE.
~~~

Nếu crash sau write trước mark, chunk sẽ replay; idempotency xử lý duplicate. Nếu source+target+checkpoint có transaction chung trong phạm vi hỗ trợ, có thể dùng để giảm duplicate window, nhưng không mặc định chúng có chung transaction.

### 10.5. In-progress chunk và checkpoint partial

Nếu một chunk chứa 50.000 rows mà checkpoint lưu `lastKey` sau mỗi 5.000, cần bảo đảm `lastKey` chỉ **tiến sau các rows đã durable ở target**. Nếu không, restart có thể bỏ một đoạn.

### 10.6. Chunks và schema changes

Một chunk có thể đọc theo schema v3, chunk sau theo v4. Nếu transform cần schema registry/canonical target fields, checkpoint phải gắn source schema/version cần thiết để replay được; không đọc raw JSON cũ bằng assumptions của code mới rồi âm thầm mất field.

## 11. Low/high watermarks và collision window

Một incremental snapshot có thể sử dụng **watermark window** cho mỗi chunk hoặc key range.

Giả sử snapshot chunk R = orders `O100–O199`:

~~~text
Time          CDC stream                Snapshot scanner
----          ----------                ----------------
t0            low watermark L recorded
t1            update O120 -> v6         reads O100...O140
t2            delete O135              reads O141...O199
t3            update O190 -> v4
t4            high watermark H recorded
t5            reconcile snapshot rows with (L,H] changes
~~~

Các events trong `(L,H]` được gọi là **collision candidates** với snapshot rows. Nếu connector chọn snapshot value của O120 ở thời điểm khác CDC update, cần xác định **quy tắc winner** theo commit metadata/algorithm.

### 11.1. Không chỉ dùng “last timestamp wins”

Nếu nguồn là multi-shard với clock skew, sự kiện CDC có wall-clock timestamp lớn không nhất thiết là causal descendant của snapshot value.

Một watermark đúng là **barrier theo protocol của nguồn** và cho biết changes nào nằm trong cửa sổ; cách so giữa snapshot row và CDC event phải dựa trên **guarantee về snapshot isolation, per-key version hoặc commit ordering**.

### 11.2. Một quy tắc collision khái niệm

Trong một thuật toán mà CDC changes trong cửa sổ có đầy đủ **row-level after-image và delete marker**, connector có thể:

1. Đọc snapshot rows cho chunk R.
2. Buffer CDC changes cho keys thuộc R trong watermark window.
3. Với key đã bị thay đổi trong window, **không phát snapshot row cũ**; để CDC event thích hợp xác lập trạng thái.
4. Với key không collision, phát snapshot row.
5. Advance chunk progress chỉ sau khi dữ liệu đã đi qua apply/checkpoint an toàn.

Đây là nguyên tắc minh họa. Nếu CDC chỉ có delta mà không có full after-image, hoặc nếu snapshot scan có thể thấy changes sau high watermark, cần algorithm khác/stronger source guarantees. Không thể tự dùng bước 3 cho mọi engine rồi coi là chứng minh đúng.

### 11.3. Low watermark đến từ đâu?

Có hệ cho phép ghi/đọc marker vào **cùng ordered change stream**. Có hệ chỉ cung cấp stream positions theo shards, cần lấy một **set of positions** và theo dõi lineage. Có engine hỗ trợ transactionally consistent read snapshot với mốc position được cấp cùng lúc.

**Marker ghi ở một queue khác không tự trở thành barrier cho database log.** Nếu marker không được order tương đối với các source mutations cần bảo vệ, nó không giải quyết race.

### 11.4. High watermark phải nằm sau scan trong ordering được hỗ trợ

Nếu connector phát high watermark trước khi đọc xong chunk hoặc vị trí high không liên quan source ordering, các mutation trong cửa sổ scan có thể bị phân loại sai.

### 11.5. Một high watermark không nhất thiết đại diện toàn cluster

Nếu các shards có streams độc lập:

~~~text
Shard A: low_A ... high_A
Shard B: low_B ... high_B
~~~

Sử dụng một `high=A:500` để tuyên bố shard B đã scan xong là sai. Snapshot coordinator phải xác định cutover theo **từng stream/partition**, hoặc có protocol toàn cục được sản phẩm hỗ trợ.

## 12. Không tạo event nghiệp vụ giả từ snapshot

Snapshot mô tả **trạng thái hiện có**, không nhất thiết cung cấp lịch sử **tại sao** trạng thái ấy hình thành.

Ví dụ Order hiện là `SHIPPED`:

~~~json
{
  "orderId": "O101",
  "status": "SHIPPED",
  "version": 11
}
~~~

Snapshot không chứng minh:

- Payment đã được capture một lần hay nhiều lần.
- Shipment có thể được tạo bởi user hay back-office.
- Inventory có cần reserve lần nữa hay không.
- Các event `OrderCreated`, `OrderPaid`, `OrderShipped` đã từng phát khi nào.

### 12.1. Phân biệt hai loại downstream consumers

**State projection bootstrap:**

~~~text
SNAPSHOT_ROW(Order O101=SHIPPED) -> UPSERT search document.
~~~

Đây là trường hợp phù hợp cho snapshot.

**Business event handler:**

~~~text
OrderPaid event -> capture payment / send receipt.
~~~

Không được biến snapshot row `status=PAID` thành `OrderPaid` business event và gửi receipt/capture payment như thể đây là mutation mới. Cần **event type riêng**:

~~~json
{
  "recordKind": "SNAPSHOT",
  "aggregateId": "tenant-a/O101",
  "value": {"status": "SHIPPED"}
}
~~~

Consumer có thể dùng snapshot để **rebuild state** nhưng không chạy side effect không idempotent của event lịch sử.

### 12.2. Rehydration vs replay

**Rehydration**: Đặt target state bằng giá trị đã commit tại một mốc được định nghĩa.

**Event replay**: Diễn lại chuỗi mutation/event được lưu để tính state. Replay cần bảo đảm ordering, dedup và logic lịch sử/schema tương thích.

Một initial snapshot **không tự thay thế event history** nếu downstream cần các delta/event theo thời gian.

## 13. Delete, tombstone và chống hồi sinh record

Trong full-state replication, deletion không phải “không thấy row trong một page” theo nghĩa đủ để xóa target.

### 13.1. Vì sao không thấy row không chứng minh delete?

Một scan không nhất quán có thể bỏ qua record do:

- Partition/page boundary thay đổi.
- Read timeout và retry lỗi.
- Filter không đúng.
- TTL/visibility rules khác nhau.
- Shard bị split/rebalance.

Không được `DELETE target where key not seen in scan` trước khi **snapshot coverage được chứng minh đầy đủ** và policy deletion/synchronization cho phép.

### 13.2. Delete event với source ordering

~~~json
{
  "recordKind": "CDC_DELETE",
  "sourceKey": "tenant-a/O101",
  "sourceVersion": 12,
  "sourcePartition": "shard-3",
  "sourcePosition": "opaque-position",
  "deletedAt": "2026-11-14T09:12:00Z"
}
~~~

Nếu target đã áp delete v12, snapshot O101 v11 đến muộn phải bị **từ chối**.

### 13.3. Xóa vật lý ở target có thể mất metadata

Nếu target chỉ xóa document:

~~~text
DELETE O101
~~~

và không giữ bất kỳ `lastAppliedVersion`/tombstone nào, snapshot retry v11 có thể upsert O101 trở lại.

Một phương án:

~~~json
{
  "key": "tenant-a/O101",
  "lastAppliedSourceVersion": 12,
  "deleted": true,
  "payload": null
}
~~~

Target query có thể ẩn tombstones; cleanup vật lý chỉ khi chắc chắn không còn old data/CDC replay được chấp nhận mà không qua guard tương ứng.

### 13.4. Delete với version numbers không đáng tin

Nếu source không có source version tăng đơn điệu cho key, không tự tạo `deletedAt` từ client clock rồi coi nó là fencing token. Cần:

- Source commit position có ordering đủ cho key.
- Snapshot barrier/consistency phù hợp.
- Một dedicated key generation/identity.
- Tombstone stream và lifecycle/retention rõ.

### 13.5. Recreate cùng primary key

~~~text
O101 version 10 -> DELETE version 11
O101 recreated as "new order" version 1
~~~

Nếu business cho phép reuse key và version reset, rule `max(sourceVersion)` sẽ **vĩnh viễn bỏ bản mới**. Cần **generation/epoch + version**, hoặc không cho reuse key, hoặc một ordered source mutation sequence bao cả delete/recreate.

### 13.6. TTL và CDC

Một TTL expiration có thể phát event delete hoặc không, tùy engine và stream mode. Xóa vật lý thường **bất đồng bộ**, và event có thể khác user-initiated delete. Snapshot+CDC design phải hiểu:

- Record còn được scan sau logical expiry không?
- TTL deletes có xuất hiện trong change feed không?
- Event có thể đến muộn không?
- Retention/tombstone compaction ảnh hưởng recovery thế nào?

Không dùng TTL như thay thế tuyệt đối cho một delete event đã được giao.

## 14. Source version, CDC position và target version guard

Một target upsert có thể mang:

~~~json
{
  "targetKey": "tenant-a/O101",
  "value": {"status": "PAID"},
  "sourceGeneration": 3,
  "sourceVersion": 8,
  "sourcePartition": "shard-1",
  "sourcePosition": "log-offset-opaque",
  "lastApplyKind": "CDC_UPSERT"
}
~~~

Phải phân biệt:

- `sourceGeneration`: Nhận diện lần tạo/authority epoch nếu key có thể reset version.
- `sourceVersion`: Nếu nguồn cấp tăng theo **một key**, dùng để từ chối bản cũ.
- `sourcePosition`: Phục vụ **resume/checkpoint**, có thể chỉ có thứ tự theo partition/log.
- `eventId`: Phục vụ **dedup logical event**, kể cả khi cùng bản ghi có nhiều mutations.

### 14.1. Điều kiện áp dụng version guard

~~~text
if incoming.generation < current.generation:
    reject
else if incoming.generation == current.generation
     and incoming.sourceVersion < current.sourceVersion:
    reject
else:
    apply according to operation semantics
~~~

Đây là mô hình. Trường hợp `sourceVersion == current.sourceVersion` phải được định nghĩa:

- Cùng event/payload → duplicate no-op.
- Cùng version nhưng khác payload → conflict/integrity problem.
- Một transaction có nhiều events cùng version → cần `eventOrdinal` hoặc identity riêng.

### 14.2. Guard phải được thực thi tại target commit

Sai:

~~~text
Worker A reads target v7.
Worker B writes target v9.
Worker A writes snapshot v8 unconditionally.
~~~

Ngay cả khi Worker A đã kiểm tra local `v8 > v7`, kết quả vẫn sai vì target đổi giữa check và write.

Với database target cần một **conditional update/CAS/transaction** hoặc một single serialized applier per key trong fault model chấp nhận được. Chỉ có Java `if` trước network write là không đủ.

### 14.3. Với search index không phải NoSQL source

Elasticsearch/OpenSearch có các cách kiểm soát version/external version/seqNo-primaryTerm tùy API/version. Nếu dùng làm target, phải đọc rõ cơ chế versioning được hỗ trợ, delete behavior và xử lý version conflicts; không tự giả định mọi document delete đều giữ tombstone/version mãi mãi.

### 14.4. Multi-writer conflict không giải được bằng scalar version

Nếu region A và B tự cấp `version=10` cho hai writes concurrent, rule `max(version)` không phân biệt được. Cần authoritative commit order, vector/causal metadata, CRDT hoặc domain conflict resolution, tùy kiến trúc.

## 15. Ordering trên nhiều partitions và transactions

Một CDC connector có thể đọc streams:

~~~text
Shard A: A1 -> A2 -> A3
Shard B: B1 -> B2 -> B3
~~~

Trong đa số thiết kế, ta biết **ordering trong từng shard**, nhưng không có một total order giữa A2 và B2 nếu không có giao thức khác.

### 15.1. Bảo đảm nào thường đủ cho read model?

Nếu mỗi Order nằm trong một shard/authority và events của **cùng Order** đi qua một ordered path, có thể chỉ cần **per-key order**. Các Orders khác nhau có thể apply song song.

### 15.2. Khi transaction thay đổi nhiều keys

Giả sử transaction T cập nhật:

~~~text
Order O101 -> PAID
Payment P55 -> CAPTURED
~~~

Nếu downstream dashboard yêu cầu nhìn hai changes **atomically**, connector/target phải biết:

- Transaction boundary/ID.
- Tập changes thuộc T.
- Commit marker hoặc equivalent.
- Target transaction scope hoặc cách publish một materialized snapshot nhất quán.

Nếu target chỉ apply từng event không đồng bộ, có thể tạm thấy O101 PAID nhưng P55 chưa CAPTURED dù source commit cả hai cùng nhau. Điều đó có thể chấp nhận nếu read model eventual, nhưng **không được gọi là atomic visibility**.

### 15.3. Cross-collection snapshot

Quét `orders` xong rồi `payments` sau 30 phút không tạo một consistent snapshot cho cả hai collections nếu không có snapshot isolation/transaction boundary hỗ trợ. Nếu read model cần join chuẩn, phải dùng cùng cut hoặc eventual compensation/reconciliation.

### 15.4. Multi-region active-active

Hai regions có thể chấp nhận concurrent writes khi partitioned. CDC từ hai regions không tự đưa ra conflict resolution chính xác:

~~~text
Region A: Order O101 = CANCELLED
Region B: Order O101 = CONFIRMED
~~~

Người thiết kế phải xác định **authority/convergence rules** trước khi đưa changes vào một target. Timestamp hoặc thứ tự arrival không tự bảo đảm business invariant.

### 15.5. Shard split và merge

Trong một số stream services, shard A bị split thành A1/A2. Consumer không được chỉ lưu offset cũ và bỏ qua child shards. Cần theo dõi **shard lineage, parent completion, resharding semantics, sequence/leases/checkpoints** theo nguồn.

## 16. Checkpoint sao cho crash không làm mất apply

Một CDC consumer thường làm:

~~~text
1. Read event at source position P.
2. Apply event to target.
3. Persist checkpoint = P.
~~~

Điểm nguy hiểm là **checkpoint có thể tiến nhanh hơn dữ liệu target đã durable**.

### 16.1. Sai: checkpoint trước apply

~~~text
Read E18 at P18.
Persist checkpoint P18.
Crash before applying E18.
Restart after P18.
E18 is skipped.
~~~

Đây là **data loss ở target** dù source log chưa mất.

### 16.2. An toàn at-least-once: apply rồi checkpoint

~~~text
Read E18 at P18.
Apply E18 idempotently; confirm durable target write.
Crash before checkpoint P18.
Restart and re-read E18.
Duplicate E18 is ignored/merged safely.
~~~

### 16.3. Cùng transaction target nếu có thể

Nếu target hỗ trợ transaction cho **target state + consumer checkpoint/dedup marker**, có thể commit:

~~~text
BEGIN target transaction
  apply mutation E18
  record lastAppliedSourcePosition=P18
COMMIT
~~~

Điều này giúp tránh việc checkpoint đẩy quá dữ liệu target trong cùng atomic scope. Nhưng không có nghĩa stream source, target và broker đều nằm trong một distributed transaction.

### 16.4. Checkpoint liên quan nhiều sources

Nếu CDC có bốn shards:

~~~json
{
  "positions": {
    "shard-A": "opaque-A-101",
    "shard-B": "opaque-B-985",
    "shard-C": "opaque-C-220",
    "shard-D": "opaque-D-77"
  }
}
~~~

Cần coi checkpoint là **vector of progress theo stream scope**. Không dùng `max(P)` để suy toàn cụm đã bắt kịp nếu P thuộc các miền khác nhau.

### 16.5. Snapshot progress và CDC progress riêng

Một bootstrap checkpoint có thể chứa:

~~~yaml
bootstrapRunId: "bootstrap-2026-11-14-01"
phase: "SNAPSHOTTING"
sourceSnapshotBoundary: "opaque-consistent-boundary"
completedChunks:
  - "range-000"
  - "range-001"
inProgressChunk: "range-002"
streamProgress:
  shard-a: "opaque-position-a"
  shard-b: "opaque-position-b"
targetApplyCheckpoint:
  shard-a: "opaque-position-a-applied"
schemaVersion: 4
~~~

Nếu stream read ahead đang lưu buffer, **stream read position** và **last durably applied position** không nhất thiết là một. Chỉ resume từ vị trí mà những events trước đó đã được lưu an toàn ở buffer hoặc target.

### 16.6. Checkpoint generation để chống zombie worker

Hai connector instances có thể cùng nghĩ mình là owner sau failover/lease expiry. Nếu chúng dùng checkpoint khác nhau, writer cũ có thể ghi checkpoint lùi hoặc publish event out-of-order.

Cần consumer-group partition assignment/lease/fencing hoặc conditional checkpoint update theo **generation/epoch**, đúng contract của coordinator.

## 17. Sơ đồ trạng thái của một lần bootstrap

Không nên gắn một boolean `snapshotDone` rồi cho streaming chạy ngay. Một state machine rõ ràng giúp phục hồi:

~~~mermaid
flowchart TD
    A["NEW"] --> B["CAPTURING_CHANGE_POSITION"]
    B --> C["SNAPSHOTTING"]
    C --> D["SNAPSHOT_APPLY_COMPLETE"]
    D --> E["STREAM_CATCHING_UP"]
    E --> F["STREAMING"]
    C --> G["PAUSED / RECOVERABLE"]
    E --> G
    F --> G
    G --> C
    G --> E
    G --> F
    G --> H["REBOOTSTRAP_REQUIRED"]
    H --> A
~~~

### 17.1. Ý nghĩa từng phase

| Phase | Bảo đảm/việc đang làm | Điều kiện chuyển bước |
| --- | --- | --- |
| `NEW` | Chưa xác lập source boundary | Quyền đọc snapshot và log đã xác minh |
| `CAPTURING_CHANGE_POSITION` | Chuẩn bị resume positions / subscription | Vị trí được lưu bền và có coverage |
| `SNAPSHOTTING` | Quét chunks, apply state hoặc buffer | Mọi chunks đã durable/finalized |
| `SNAPSHOT_APPLY_COMPLETE` | Có snapshot target với phạm vi rõ | Áp stream từ boundary phù hợp |
| `STREAM_CATCHING_UP` | Replay backlog phát sinh trong snapshot | Stream caught up đến mốc gần live và không gap |
| `STREAMING` | Consume CDC liên tục | Checkpoint tiến đều, không có thiếu mốc |
| `PAUSED/RECOVERABLE` | Đã dừng nhưng log/checkpoints còn | Resume từ progress bền |
| `REBOOTSTRAP_REQUIRED` | Không thể resume vị trí do retention/corruption | Chọn boundary và bootstrap mới |

### 17.2. Không tự chuyển sang STREAMING khi chưa kiểm tra backlog

Snapshot scanner báo `done` không chứng minh CDC reader đã phát mọi changes xảy ra trong scan. Cần một **catch-up checkpoint/watermark** phù hợp và invariant no-gap.

### 17.3. Rebootstrap không phải xóa mọi target ngay

Nếu target phục vụ traffic, xóa index rồi xây lại có thể gây downtime. Có thể:

1. Tạo **shadow target/index** cho bootstrap mới.
2. Nạp snapshot, bắt CDC và catch up.
3. Kiểm tra completeness, lag và consistency.
4. Chuyển read alias/routing theo bước có kiểm soát.
5. Dọn target cũ theo retention/rollback policy.

Cách chuyển alias/index/traffic phụ thuộc target engine. Nói “swap atomically” chỉ khi target hỗ trợ thao tác tương ứng.

## 18. Java: mô hình record chung cho snapshot và CDC

Một normalized record có thể giữ đầy đủ provenance:

~~~java
import java.util.Map;

public enum RecordKind {
    SNAPSHOT_UPSERT,
    CDC_UPSERT,
    CDC_DELETE,
    SNAPSHOT_CHUNK_BARRIER
}

public record ReplicationRecord(
    RecordKind kind,
    String sourceId,
    String namespace,
    String sourceKey,
    String sourceGeneration,
    long sourceVersion,
    String sourcePartition,
    String sourcePosition,
    String eventId,
    int schemaVersion,
    Map<String, Object> value
) {}
~~~

**Giới hạn của mô hình minh họa:**

- `sourceVersion` trong ví dụ là `long`, nhưng nhiều engines **không cung cấp một version scalar per key**. Nếu không có thì phải dùng một comparator/metadata khác được protocol chứng minh.
- `sourcePosition` có thể là opaque token/structured data; biểu diễn string ở đây chỉ để demo.
- `SNAPSHOT_CHUNK_BARRIER` không phải mutation nghiệp vụ; nó quản lý trạng thái scan.
- Record chưa chứa transaction metadata, source timestamp uncertainty, namespace change và primary-key migrations.

### 18.1. Source key phải ổn định

Không dùng `updatedAt` hoặc một field có thể sửa làm primary identity của replication record. Nếu business key thay đổi, connector có thể cần biểu diễn **delete old key + insert new key** hoặc key migration event.

### 18.2. Payload không phải lúc nào cũng full image

CDC có thể chứa:

~~~json
{
  "operation": "update",
  "key": "tenant-a/O101",
  "changedFields": {"status": "PAID"},
  "removedFields": ["discountCode"]
}
~~~

Nếu target chỉ lưu `status`, delta có thể đủ; nhưng nếu target rebuild full document, cần **before/after image, read-after-write with race protection hoặc merge delta theo source order**. Không tự coi mọi CDC event là full state.

### 18.3. Event ID phải ổn định qua replay

Một logical source mutation được đọc lại sau restart vẫn nên có event identity/dedup key tương thích, dựa trên source log identity/transaction/position/event ordinal theo contract.

Không tạo UUID mới mỗi lần consume rồi hy vọng target dedup được.

## 19. Java: target apply với version và tombstone

Để tránh old snapshot overwrites, ta cần một **atomic conditional mutation tại target**.

Mẫu interface minh họa:

~~~java
public interface VersionedTargetStore {
    enum ApplyOutcome {
        APPLIED,
        DUPLICATE,
        STALE_IGNORED,
        CONFLICT
    }

    ApplyOutcome applyIfNewer(ReplicationRecord record);
}
~~~

Ý nghĩa mong muốn:

~~~text
applyIfNewer(record):
    in one atomic target operation:
      read last accepted (generation, version, event identity)

      if record older:
         return STALE_IGNORED

      if same version and same event identity:
         return DUPLICATE

      if same version but payload/event semantics conflict:
         return CONFLICT

      if newer:
         if record kind CDC_DELETE:
            persist tombstone with version
         else:
            persist source payload and version
         return APPLIED
~~~

### 19.1. Không dùng Java `synchronized` làm thay target transaction

Hai connector pods khác nhau có thể cùng apply một key:

~~~text
Pod A checked target v6
Pod B committed target v8
Pod A writes target v7
~~~

Một `synchronized` trong Pod A không bảo vệ Pod B. Condition phải được **cưỡng chế ở target commit**, hoặc tất cả writers phải đi qua một per-key single-authority ordering path có fault recovery đầy đủ.

### 19.2. Deletes và explicit tombstones

Nếu `CDC_DELETE` đến ở sourceVersion=9, target cần giữ đủ metadata để từ chối snapshot upsert sourceVersion=8. Việc ẩn record khỏi queries khác với xóa metadata ordering ngay lập tức.

### 19.3. Multi-region và generations

Thay vì chỉ `long sourceVersion`, có thể cần tuple:

~~~text
(sourceEpoch, sourceVersion, transactionOrdinal)
~~~

hoặc một engine-defined version/commit position. Tuple chỉ được so khi **protocol xác định thứ tự và scope của các thành phần**; không tự đặt epoch theo client clock.

## 20. Java: CDC loop với checkpoint sau apply

Ví dụ pseudocode Java:

~~~java
public final class ChangeStreamProcessor {
    private final SourceChangeReader reader;
    private final VersionedTargetStore target;
    private final CheckpointStore checkpoints;

    public ChangeStreamProcessor(
        SourceChangeReader reader,
        VersionedTargetStore target,
        CheckpointStore checkpoints
    ) {
        this.reader = reader;
        this.target = target;
        this.checkpoints = checkpoints;
    }

    public void runPartition(String partitionId) {
        String lastApplied = checkpoints.loadAppliedPosition(partitionId);
        reader.resume(partitionId, lastApplied);

        while (!Thread.currentThread().isInterrupted()) {
            ReplicationRecord event = reader.next(partitionId);
            if (event == null) {
                continue;
            }

            VersionedTargetStore.ApplyOutcome result =
                target.applyIfNewer(event);

            if (result ==
                VersionedTargetStore.ApplyOutcome.CONFLICT) {
                throw new IllegalStateException(
                    "Replication integrity conflict: " + event.eventId()
                );
            }

            // Only after target confirms durable apply/no-op.
            checkpoints.saveAppliedPositionConditionally(
                partitionId,
                event.sourcePosition()
            );
        }
    }
}
~~~

§SourceChangeReader§, §CheckpointStore§ là giả định. §saveAppliedPositionConditionally§ phải bảo đảm **không tiến sai/lùi checkpoint** khi nhiều workers cùng xử lý, và phải hiểu token ordering của engine.

### 20.1. Không coi đây là một connector production

Mã không có:

- Bounded queues/flow control.
- Lease/partition ownership.
- Schema change/catch-up barriers.
- Transaction grouping.
- Offset validation/resume error classification.
- Idempotency marker transaction tại target.
- Backoff/retries, error isolation và DLQ.
- Graceful shutdown, metrics, tracing.

Đây là mô hình giúp thấy **thứ tự apply → durable ack → checkpoint**.

### 20.2. Khi target apply trả DUPLICATE

Vẫn có thể advance checkpoint, **nếu** target đã bảo đảm trạng thái chính xác và event chỉ là replay. Không cần apply business effect lần hai.

### 20.3. Khi target apply trả STALE_IGNORED

Được phép checkpoint event cũ nếu protocol cho biết target đã nhận một version mạnh hơn tương thích và **không có missing delta/business effects**. Nếu event là delta phụ thuộc chuỗi đầy đủ, bỏ vì version thấp có thể sai.

### 20.4. Khi apply timeout

Target write có thể đã commit mà response mất. Không advance checkpoint nếu chưa biết outcome; retry bằng stable event ID/conditional operation. Nếu target giữ version/idempotency marker, replay sẽ trở thành no-op.

### 20.5. Tái lập lịch sau restart

Nếu checkpoint ở P100 nhưng target đã apply P101 rồi crash trước checkpoint, restart đọc lại P101. Target guard trả DUPLICATE/STABLE; checkpoint đi tiếp. Đây là lý do **at-least-once delivery + idempotent apply** thường đơn giản và đáng tin hơn mong đợi transport exactly-once qua các systems độc lập.

## 21. Java: snapshot scanner với bounded batches

Không tải tất cả rows vào một List:

~~~java
List<Order> all = database.findAll(); // Danger on huge datasets
all.forEach(target::save);
~~~

Một scanner phân trang:

~~~java
public final class SnapshotLoader {
    private final SnapshotSource source;
    private final VersionedTargetStore target;
    private final BootstrapCheckpointStore checkpoints;

    public void loadChunk(String chunkId) {
        String cursor = checkpoints.lastCommittedCursor(chunkId);

        while (true) {
            SnapshotPage page = source.nextPage(chunkId, cursor, 500);

            for (ReplicationRecord row : page.rows()) {
                target.applyIfNewer(row); // idempotent, version-aware
            }

            // Record progress only after rows are durable in target.
            checkpoints.markCursorApplied(
                chunkId, page.nextCursor()
            );
            cursor = page.nextCursor();

            if (page.isLast()) {
                checkpoints.markChunkComplete(chunkId);
                break;
            }
        }
    }
}
~~~

§SnapshotSource§/§SnapshotPage§ là giao diện giả định. **Không dùng mã này nếu nguồn không cung cấp một consistent snapshot boundary hoặc một collision-resolution protocol**: phân trang và version guard đơn lẻ không đủ để chứng minh mọi row đã được thấy trong các trường hợp key insert/delete giữa pages.

### 21.1. Page cursor có thể hết hạn

Một số paging state/continuation tokens chỉ có hiệu lực cho một khoảng hoặc topology nhất định. Nếu restart và cursor hết hạn:

- Re-scan chunk/range từ mốc an toàn.
- Sử dụng keyset pagination nếu protocol cho phép.
- Khởi tạo bootstrap mới nếu consistent snapshot không còn.
- Không tự bỏ qua chunk chỉ vì cursor không còn hợp lệ.

### 21.2. Mỗi batch phải có giới hạn memory và thời gian

Nếu mỗi row trung bình 8 KiB, page 10.000 rows có thể cần **80 MiB payload thô** trước khi tính Java object overhead, network buffers và serialization. Batching nên dựa trên **bytes, elapsed time và downstream capacity**, không chỉ số rows.

### 21.3. Cancellation

Khi worker bị hủy, có thể có page đã apply một phần. Checkpoint phải đại diện **durably applied prefix** hoặc replay được với idempotency. Đóng cursor/session/connection đúng vòng đời, không để connector cancel làm rò tài nguyên.

## 22. Incremental snapshot trên một hệ đang stream

Một ưu điểm của incremental snapshot là có thể **tiếp tục CDC streaming** và chụp bổ sung từng chunk mà không dừng toàn bộ connector.

Tình huống:

~~~text
Connector đã stream Orders từ hôm qua.
Hôm nay team thêm collection Customers vào connector.
Không muốn dừng Orders streaming trong 2 giờ để quét Customers.
~~~

Nếu connector hỗ trợ incremental snapshot theo nguồn:

1. Đăng ký chunk/range cần snapshot.
2. Thiết lập watermark(s) cho chunk.
3. Quét chunk trong lúc streaming tiếp tục.
4. Hòa giải CDC collisions.
5. Finalize chunk khi đã áp durable.
6. Tiếp tục streaming, không để chunks của dữ liệu khác bị đói tài nguyên.

### 22.1. Snapshot incremental khác snapshot mới toàn bộ

Một incremental snapshot có thể là **chiến lược scan từng chunk xen kẽ stream**, không đồng nghĩa chỉ quét “những rows thay đổi từ lần trước” như một incremental backup. Thuật ngữ cụ thể tùy sản phẩm/connector.

### 22.2. Debezium là ví dụ thuật toán connector

Một số Debezium connectors hỗ trợ incremental snapshots sử dụng **watermarking/windowing** và signal/coordination theo từng source. Khi học hoặc triển khai cần đọc đúng:

- Connector nào hỗ trợ.
- Cách trigger signal, snapshot modes.
- Low/high watermark algorithm.
- Cơ chế phát hiện collision giữa snapshot records và streamed changes.
- Transaction/log position semantics.
- Resumption, schema changes và limits.

Không suy một cơ chế dùng cho database transaction log truyền thống sẽ áp y nguyên với mọi NoSQL change feed hoặc mọi Debezium connector.

### 22.3. Tốc độ snapshot và streaming phải có ngân sách riêng

Nếu snapshot liên tục chiếm hết source read capacity, live CDC backlog sẽ tăng. Nên có:

~~~text
snapshotReadBudget = controlled
streamApplyPriority = higher when lag grows
maxConcurrentSnapshotChunks = bounded
memoryBufferLimit = bounded
~~~

Backpressure có thể làm snapshot chậm hơn nhưng giúp không vượt stream retention.

## 23. Snapshot chứa dữ liệu nào? Filter, transform và consistency

Một scanner có thể chỉ nạp:

~~~text
WHERE tenantStatus = ACTIVE
~~~

Nếu sau đó tenant chuyển từ INACTIVE sang ACTIVE, CDC phải làm sao để target có đủ Order history/state của tenant ấy?

### 23.1. Filtering cần hiểu lifecycle

Một predicate chỉ đúng lúc snapshot có thể thay đổi sau đó. Nếu filter của CDC khác filter snapshot, target có thể giữ stale rows hoặc thiếu records.

Ví dụ:

~~~text
Snapshot ignores INACTIVE tenant T1.
T1 becomes ACTIVE.
CDC only emits tenant metadata update, not all T1 orders.
~~~

Target thiếu Orders của T1. Cần thiết kế rebootstrap per tenant, dynamic inclusion semantics, hoặc target lưu đủ dữ liệu rồi filter tại read time.

### 23.2. Data transformation cần deterministic

Nếu snapshot transformer v1 tính:

~~~text
totalText = formatCurrency(total)
~~~

nhưng CDC transformer v2 tính theo schema khác, cùng source value có thể tạo target value không nhất quán.

Hãy version hóa transform/schema, xác định lúc nào reindex toàn bộ và đảm bảo **upserts/deltas phù hợp**.

### 23.3. Không phục hồi event history chỉ từ trạng thái

Nếu source đang là `balance=100`, snapshot không thể cho biết đã từng có các `+20,-10,+5` operations nào. Một consumer cần financial ledger phải đọc **event/transaction ledger** hoặc nguồn authoritative riêng, không dùng trạng thái balance cộng thêm những CDC deltas bắt đầu ở “now” rồi tin rằng lịch sử đã đầy đủ.

### 23.4. Target schema và source schema có thể đổi độc lập

Khi thêm field `couponCode`, phải xử lý:

- Existing snapshot rows thiếu field.
- CDC update có/không có before/after image.
- Null vs absent vs field deletion.
- Schema evolution trong retained logs.
- Reconciliation/backfill của dữ liệu cũ.

Không coi `null` và “không có field” là đồng nghĩa nếu domain phân biệt chúng.

## 24. Retention: giữ change log đủ dài cho bootstrap và recovery

CDC stream có một **retention window**. Nếu connector bị dừng lâu hơn window, nó có thể không resume từ vị trí đã lưu.

### 24.1. Một công thức ngân sách thời gian

Giả sử:

~~~text
Expected snapshot duration          = 6 hours
Possible outage during snapshot     = 2 hours
Catch-up and processing recovery    = 1 hour
Operational safety margin           = 3 hours
~~~

Nếu log chỉ retained 4 giờ thì rõ ràng không đủ cho phương án **đợi snapshot xong rồi đọc lại log từ mốc ban đầu**. Một ngân sách sơ bộ:

\[
R_{\min} > T_{\text{snapshot}} +
T_{\text{outage}} + T_{\text{catchup}} + T_{\text{margin}}
\]

Với ví dụ:

\[
R_{\min} > 6+2+1+3=12\text{ giờ}
\]

Chỉ là điều kiện thời gian **có tính bảo thủ** cho một thiết kế cụ thể. Nếu connector đang durably spool stream song song, yêu cầu retention nguồn có thể khác; lúc đó phải sizing **durable buffer** và thời gian hồi phục riêng.

### 24.2. Log volume tính theo bytes/s

Nếu source phát 10.000 mutations/s và mỗi change record trung bình 1 KiB:

\[
10\,000\times1024 = 10\,240\,000\text{ bytes/s}
\]

Trong 12 giờ:

\[
10\,240\,000\times12\times3600
=442\,368\,000\,000\text{ bytes}
\]

Khoảng **442 GB raw change payload** (decimal), chưa tính replication, headers, compression, indexes và storage overhead.

### 24.3. Retention là điều kiện, không phải tốc độ

Một stream có retention 24 giờ nhưng live CDC consumption chỉ đạt 80% tốc độ producer sẽ **tích lũy lag đến khi vượt retention**. Phải đo **source mutations/s, consumer applied/s, backlog bytes và oldest unprocessed age**.

### 24.4. Khi resume token hết hạn

Không làm:

~~~text
Resume fails -> subscribe NOW -> continue.
~~~

Điều đó tạo gap không được công bố. Thay vào đó:

- Đánh dấu bootstrap/replication **DEGRADED hoặc REBOOTSTRAP_REQUIRED**.
- Dừng tuyên bố target là đầy đủ.
- Tạo consistent snapshot/cutover mới hoặc thực hiện reconciliation có chứng minh.
- Dùng shadow target/alias nếu cần không gián đoạn.
- Ghi nguyên nhân và phạm vi dữ liệu cần repair.

### 24.5. Cleanup và compaction log

Một log compacted by key có thể giữ trạng thái cuối nhưng không giữ đầy đủ **mọi mutation/delta**. Nếu downstream cần replay toàn bộ event history, key compaction không mặc nhiên đủ. Ngược lại, nếu chỉ cần latest state, compacted changelog có thể hữu ích nếu semantics về deletes/tombstones và replay được thiết kế đúng.

## 25. MongoDB: collection snapshot và Change Streams

MongoDB là một ví dụ dễ thấy về document store có **change streams** cho các deployment được hỗ trợ, thường kết hợp với các thao tác đọc collection để bootstrap downstream.

### 25.1. Không đồng nhất `find()` với một snapshot tại một mốc stream

~~~javascript
const docs = db.collection("orders").find({});
// scan all docs ...
~~~

Một cursor quét nhiều pages trên collection đang được sửa **không được tự coi là ảnh chụp toàn collection ở cùng một thời điểm log**. Cần hiểu read concern, snapshot session/transaction, cursor lifetime và phạm vi consistent read mà MongoDB/driver hỗ trợ ở phiên bản/topology đang dùng.

### 25.2. Change stream có resume token

Conceptual JavaScript:

~~~javascript
const stream = db.collection("orders").watch([], {
  fullDocument: "updateLookup"
});

for await (const change of stream) {
  // change._id is a resume token. Persist safely as opaque data.
  // Handle insert/update/replace/delete/invalidate operations.
  // Apply to target, then checkpoint.
}
~~~

Đây là **đoạn minh họa đọc stream**, không phải thuật toán bootstrap đầy đủ. Khi dùng thật:

- Lưu resume token **nguyên vẹn**, không chỉ một timestamp.
- Đọc docs phân biệt `resumeAfter`, `startAfter` và `startAtOperationTime` với các trường hợp hỗ trợ.
- Xem oplog/stream retention, failover, collection drop/rename/invalidate behavior.
- Checkpoint sau target apply, theo semantics driver.
- Xác định thế nào để snapshot scan và stream **không có gap**.

### 25.3. `updateLookup` có thể gây hiểu nhầm

Full document lookup tại thời điểm xử lý change stream **không luôn đồng nghĩa chính xác post-image của một mutation lịch sử** nếu document đã đổi tiếp trước khi lookup, tùy API/semantics.

Ví dụ:

~~~text
Event E8: status=PAID
Event E9: status=SHIPPED
Connector processes E8 later and looks up latest document.
Result may reflect SHIPPED instead of the historical E8 state.
~~~

Khi cần exact before/after image, phải đọc tính năng **change stream pre/post images** của phiên bản và cấu hình, cùng retention của images, không suy một lookup “lấy fullDocument” luôn tái hiện transaction state tại E8.

### 25.4. Snapshot transaction và resource cost

Một long-running snapshot transaction có thể gặp giới hạn thời gian, MVCC history pressure và transaction conflict. Đừng mở transaction kéo dài nhiều giờ chỉ để giữ một consistent view mà không xác minh engine hỗ trợ. Khi dữ liệu lớn, cần giải pháp snapshot-aware/incremental connector hoặc nguồn backup/snapshot có **mốc CDC nối được**.

### 25.5. Sharded cluster

MongoDB sharded changes có thể đi qua nhiều shards/routers và change stream có semantics ordering/resume riêng. Không lấy một `updatedAt` từ client hoặc tự đọc shard oplogs rồi coi là consistent global cut. Nên dùng source API/connector bảo đảm phù hợp và kiểm tra behavior khi shard migration.

### 25.6. Delete và target

Change stream delete thường cung cấp key/metadata phù hợp API, nhưng **không được giả định delete có full document payload** trừ khi mode/features cho phép. Target cần khóa record và policy tombstone/version/ordering.

### 25.7. Runbook tối thiểu cho MongoDB

~~~text
Driver + server version?
Replica set or sharded deployment supported for streams?
Snapshot/read concern and boundary?
Which stream resume mode/token?
How long can oplog retain the initial token?
Pre/post images configured and retained?
How are updateLookup races handled?
How are invalidate events and resharding handled?
How are target apply + checkpoint made recoverable?
~~~

## 26. DynamoDB: Scan không tự tạo consistent snapshot + Streams

DynamoDB có **Scan** để liệt kê items và **DynamoDB Streams** để lấy change records của tables đã bật stream. Nhưng ghép hai API không tự tạo một snapshot nhất quán.

### 26.1. Strongly consistent Scan có nghĩa gì?

Một Scan với read consistency mạnh (trong những đường được hỗ trợ) vẫn **không cung cấp snapshot isolation của toàn bộ Scan**. Items được đọc ở những thời điểm khác nhau khi scan kéo dài.

Vì vậy:

~~~text
Scan with ConsistentRead=true
then subscribe to stream LATEST
~~~

không phải một bootstrap no-gap được chứng minh.

### 26.2. TRIM_HORIZON và LATEST

Streams API có các cách bắt đầu đọc trên từng shard như:

- `TRIM_HORIZON`: Từ record cũ nhất còn retained trong shard theo API semantics.
- `LATEST`: Gần các records mới nhất khi iterator được tạo.
- `AT_SEQUENCE_NUMBER`/`AFTER_SEQUENCE_NUMBER`: Tại/sau sequence phù hợp.

Chọn `LATEST` **sau** khi Scan xong có nguy cơ bỏ mutation trong scan. Chọn `TRIM_HORIZON` có thể tạo overlap, nhưng vẫn phải xử lý snapshot items trôi theo thời gian và retention.

### 26.3. Retention và thời gian bootstrap

DynamoDB Streams có cửa sổ giữ change records hữu hạn (thông thường 24 giờ). Với bảng lớn, một Scan kéo dài gần hoặc quá cửa sổ đó đòi hỏi stream được tiêu thụ/spool song song hoặc một thiết kế khác.

Đọc tài liệu dịch vụ đang dùng để xác nhận window, behavior khi iterator/sequence hết hạn và giới hạn throughput của stream consumers.

### 26.4. StreamViewType quyết định có gì trong event

Tùy cấu hình stream view:

- Keys only.
- New image.
- Old image.
- New and old images.

Nếu source chỉ phát keys, target muốn full-state mới nhất phải **đọc lại item**, dễ tạo lookup race và thêm read capacity. Nếu phát after image, vẫn cần ordering/dedup và payload/schema policy.

### 26.5. Parallel Scan và stream shard order

Parallel Scan giúp tăng tốc bootstrap nhưng không cho global scan order hay global snapshot cut. DynamoDB Streams chia shards; sequence numbers có scope và shard lineage. Consumer phải theo dõi **parent/child shards**, checkpoint theo shard, và bảo vệ per-item ordering theo contract.

### 26.6. Multi-region Global Tables

Một change feed của một region không tự tạo một global transaction order cho concurrent writers ở nhiều regions. Nếu target muốn đúng một state, cần hiểu conflict policy và authority của Global Tables.

### 26.7. TTL delete

TTL deletion có thể được ghi nhận trong stream theo behavior của dịch vụ/vùng và có metadata giúp phân biệt service deletion ở nơi phù hợp. Không mặc định TTL xóa đúng giây cấu hình hoặc mọi replica/region phát cùng một kiểu delete record.

### 26.8. Hướng triển khai an toàn hơn

Nếu dùng DynamoDB Scan + Streams để bootstrap:

1. Chọn connector/protocol đã nêu rõ **overlap, dedup và merge semantics**.
2. Đảm bảo consume/spool stream trước khi scan tạo gap.
3. Dùng per-item version/conditional writes nếu domain cho phép, hoặc watermark collision protocol.
4. Duy trì checkpoints riêng cho scan segments và stream shards.
5. Kiểm tra stream retention và resharding.
6. Nếu không có source guarantees cần thiết, thiết kế **đối soát hoặc rebootstrap** thay vì tuyên bố strongly consistent mirror.

## 27. Azure Cosmos DB for NoSQL: change feed và chế độ dữ liệu

Azure Cosmos DB có change feed cho dữ liệu trong container theo những mode và guarantees phụ thuộc phiên bản/sản phẩm.

### 27.1. Phân biệt các feed modes

Một số modes tối ưu cho **latest version** của items; một số khả năng khác hỗ trợ **all versions and deletes** với các yêu cầu/giới hạn dịch vụ riêng.

Nếu chỉ đọc latest-version feed:

- Không tự suy mỗi intermediate update đều còn trong stream.
- Phải kiểm tra delete behavior của mode.
- Không dùng feed đó làm **audit log đầy đủ** nếu contract không cam kết.

Nếu cần mọi mutation/delete để khôi phục state/history, chọn mode có semantics phù hợp và bảo đảm retention/permission/region constraints đúng theo docs.

### 27.2. Continuation token và ranges

Change feed processors dùng continuation/checkpoint tokens để resume. Token có thể phụ thuộc feed ranges/partition behavior và là **opaque** đối với application.

### 27.3. Snapshot của cả container

Một query quét items không nhất thiết cung cấp một transactionally consistent snapshot toàn container trong lúc liên tục có writes. Phải đọc consistency level, session tokens, transactional batch scope và change feed start position.

### 27.4. Logical partition và transaction

Một transactional batch cùng logical partition có atomicity riêng; điều này không tạo global transaction cho mọi partitions trong initial snapshot. Khi cần cross-partition consistent cut, phải xác định cơ chế khác hoặc chấp nhận eventual-state replay với reconciliation.

### 27.5. Partition split/merge và processor leases

Khi partition topology đổi, processor phải theo dõi feed ranges/leases/checkpoints theo SDK/service. Không tự coi một continuation token của range cũ dùng mãi cho mọi range mới.

### 27.6. Một checklist cho Cosmos DB

~~~text
Change feed mode and delete support?
Consistency level and session tokens?
Start position/continuation-token contract?
Transaction scope per logical partition?
Retention limitations for required mode?
Partition split/lease checkpoint behavior?
How is initial query reconciled with feed?
Are full item images or deltas available?
~~~

## 28. Cassandra/ScyllaDB: table scan và CDC không tự cho global snapshot

Trong wide-column NoSQL, initial load có thể quét dữ liệu theo **token ranges** trong khi CDC/tombstones biểu diễn thay đổi theo protocol của sản phẩm.

### 28.1. Token-range scan

Một scanner có thể chia ranges:

~~~text
Token range R1 -> worker A
Token range R2 -> worker B
Token range R3 -> worker C
~~~

Nhưng token order khác business-key order và không phải transaction commit order. Thêm nodes/rebalancing có thể ảnh hưởng ownership/range distribution. Cần snapshot/chunk plan độc lập với topology hiện thời hoặc có reconciliation khi topology thay đổi.

### 28.2. Regular reads có thể thấy các replica khác nhau

Consistency level của read quyết định quorum/replica behavior, nhưng một loạt queries không tạo **snapshot isolation toàn bảng**. Không suy `QUORUM` nghĩa toàn bộ scan cùng một thời điểm.

### 28.3. CDC mechanism và operational constraints

Cassandra/ScyllaDB có các CDC mechanisms/configuration khác nhau theo phiên bản. Phải đọc:

- CDC log production/retention/space management.
- Log segmentation/ordering.
- Replica ownership và node failure.
- Backfill/snapshot tools hỗ trợ.
- Tombstones/delete/TTL behavior.
- Có/không source version hợp lệ để chặn stale upsert.

Nếu log CDC đầy hoặc connector offline quá lâu, source có thể bị ảnh hưởng theo cấu hình; không chỉ downstream bị lag.

### 28.4. LWT không thay global snapshot

Lightweight transaction/CAS trên một row/partition có scope riêng. Nó không khiến một table scan trên nhiều partitions đồng thời có cùng consistent cut.

### 28.5. Không áp dụng sai assumptions của R+W>N

Quorum overlap giúp nhiều read/write properties theo giao thức, nhưng **không tự cấp một global commit position hay transaction snapshot**. Cần protocol bootstrap/CDC cụ thể.

## 29. Debezium và Kafka Connect: connector là một phần của giao thức

Trong thực tế, nhiều dự án không tự đọc raw WAL/streams mà dùng **Debezium, Kafka Connect, cloud CDC services hoặc vendor connectors**. Một connector tốt thường triển khai nhiều chi tiết mà application dễ bỏ sót:

- Snapshot modes.
- Source offset management.
- Transaction metadata.
- Schema history.
- Event keying.
- Incremental snapshots và watermarking ở connector hỗ trợ.
- Error/retry behavior.

### 29.1. Snapshot marker và stream marker

Một số connector phát bản ghi snapshot có metadata chỉ ra `snapshot=true`/`last` hoặc tương đương, rồi phát stream changes. Target phải biết **snapshot record khác live mutation** để không phát sinh business side effect như email/thanh toán.

### 29.2. Kafka offsets là consumer progress, không phải source commit boundary

Connector có thể ghi event vào Kafka topic. Có ít nhất hai loại vị trí:

~~~text
Database source position:
  WAL LSN / oplog resume token / stream sequence

Kafka topic position:
  (topic, partition, offset)
~~~

Một Kafka offset **không tự là LSN**. Connector phải lưu mapping/offset state đúng để restart không bỏ records hoặc phát lại không kiểm soát.

### 29.3. Partitions và ordering

Nếu topic dùng `key=aggregateId`, các events cùng aggregate thường có thể được route vào một partition theo broker partitioner policy. Nhưng điều đó **không sửa được** trường hợp connector đã publish events sai thứ tự hoặc source không có per-key total order.

### 29.4. Connector defaults thay đổi theo version

Khi upgrade connector, phải xem:

- Snapshot default mode và signal semantics.
- Kafka Connect offset storage.
- Topic naming/partitioning.
- Schema history/DDL handling.
- Delete tombstone events.
- Stream resume behavior.

Không suy một recipe trên MySQL/PostgreSQL sẽ áp y nguyên cho MongoDB/DynamoDB/Cosmos vì **source contracts khác nhau**.

## 30. Consistency SLO: target “bắt kịp” nghĩa là gì?

Một connector báo `STREAMING` nhưng target vẫn lag 30 phút không đáp ứng yêu cầu gần real time.

Định nghĩa ít nhất:

**Snapshot completeness**

> 100% chunks thuộc phạm vi xác định đã được scan/finalized bền vững; không tồn tại gap chưa giải quyết.

**Stream catch-up**

> Last **applied and durable** CDC source position nằm trong ngưỡng lag chấp nhận so với source progress được đo theo cùng scope.

**State correctness**

> Với tập key mẫu và khi source đã quiesce hoặc dùng một consistent read boundary, target có cùng state, bao gồm deletes.

**End-to-end latency**

> Thời gian từ mutation được source commit đến khi read model phục vụ state tương ứng đáp ứng p95/p99 SLO.

### 30.1. Một ví dụ SLO

~~~yaml
bootstrap:
  targetCompletionHours: 8
  noUndetectedGaps: true

streaming:
  p95CommitToVisibleSeconds: 5
  p99CommitToVisibleSeconds: 30
  maximumSustainedLagMinutes: 2

recoverability:
  resumeFromCheckpoint: required
  rebootstrapOnExpiredSourcePosition: required
  tombstoneProtection: required
~~~

Đây là **mẫu SLO** để thảo luận, không phải bảo đảm chung cho mọi sản phẩm.

### 30.2. Không dùng wall clock của client để đo mọi lag

Một event từ node có clock chạy nhanh 10 phút sẽ cho `now - event.createdAt` âm hoặc sai lớn. Ưu tiên **source commit timestamps có uncertainty/semantics xác định**, broker/connector monotonic durations và progress watermark; kiểm soát clock skew trong metrics.

### 30.3. Lag theo shard

Nếu 9/10 shards đã bắt kịp nhưng shard 10 lag 3 giờ, số trung bình có thể trông đẹp. Sử dụng **max/percentile per shard hoặc oldest unprocessed event age** để nhận ra một partition bị kẹt.

### 30.4. “Exactly once” phải có scope

Một connector có thể quảng bá exactly-once trong phạm vi **Kafka transaction/offset handling**, nhưng không tự làm NoSQL source và target search index commit trong một transaction chung.

End-to-end cần định nghĩa:

~~~text
At-least-once delivery from source to connector.
Idempotent state mutation at target.
Atomic checkpoint with target state when possible.
Explicit recovery/rebuild when source position expires.
~~~

Không đếm một record được gửi đúng một lần rồi xem đó là chứng minh target state chính xác.

## 31. Theo dõi vận hành: metrics nào cần có?

### 31.1. Snapshot phase

| Metric | Ý nghĩa |
| --- | --- |
| `snapshot_chunks_total` | Tổng số chunks được xác định trong run |
| `snapshot_chunks_completed` | Số chunks đã ghi bền + finalize |
| `snapshot_chunks_in_progress` | Số chunks đang được scan |
| `snapshot_rows_read_total` | Rows scanner đã đọc |
| `snapshot_rows_applied_total` | Rows target đã nhận |
| `snapshot_rows_skipped_stale_total` | Snapshot rows bị version guard bỏ vì cũ |
| `snapshot_retry_count` | Retry chunks/pages |
| `snapshot_read_bytes_total` | Payload đã đọc |
| `snapshot_apply_bytes_total` | Payload đã ghi target |
| `snapshot_page_latency_ms` | Độ trễ đọc page |
| `snapshot_chunk_duration_ms` | Thời gian xử lý chunk |
| `snapshot_chunk_size_bytes` | Quy mô chunk |
| `snapshot_estimated_remaining_seconds` | ETA ước lượng, có sai số |

### 31.2. CDC phase

| Metric | Ý nghĩa |
| --- | --- |
| `cdc_records_read_total` | Số change records đã đọc |
| `cdc_records_applied_total` | Changes đã được target chấp nhận |
| `cdc_records_duplicate_total` | Replay/dedup |
| `cdc_records_stale_ignored_total` | Older events bị bỏ |
| `cdc_records_deleted_total` | Deletes/tombstones áp |
| `cdc_records_conflicted_total` | Cùng version khác payload/integrity |
| `cdc_buffer_bytes` | Lượng changes đang chờ apply |
| `cdc_oldest_unapplied_age_seconds` | Tuổi event chưa apply lâu nhất |
| `cdc_position_gap_total` | Lỗi position/retention/sequence |
| `cdc_resume_failures_total` | Resume token/iterator thất bại |
| `cdc_checkpoint_lag_seconds` | Checkpoint sau source high-water |
| `cdc_apply_latency_ms` | Độ trễ apply target |
| `cdc_backpressure_rejections_total` | Chặn đọc vì đầy buffer |
| `cdc_shard_assignment_changes_total` | Rebalance/lease move |

### 31.3. Correctness/quality metrics

- Số keys mismatch giữa source và target ở các **consistent sample boundaries**.
- Số tombstones ở target và old upsert bị chặn sau delete.
- Chênh lệch row count theo chunks/partition, nếu metric có nghĩa với filter/TTL.
- Số events đã source commit nhưng không có target apply position sau ngưỡng SLO.
- Số lần rebootstrap do retention hết.
- Số lần chunk bị đánh dấu complete rồi phát hiện target thiếu rows.
- Số transaction groups không được apply đầy đủ (nếu target cam kết atomic projection).

### 31.4. Cardinality và PII

Đừng tạo metric label cho từng `orderId` hoặc `eventId` nếu hàng chục triệu giá trị. Các ID cụ thể thuộc trace/log hoặc reconciliation store với quyền truy cập hạn chế. Metric labels nên theo source, partition bucket, phase, error class và operation type.

## 32. Load và backpressure: snapshot không được giết live stream

Một connector có hai nguồn tải:

~~~text
Snapshot:
  bulk scans -> source read IO, network, target writes

CDC:
  live mutations -> log read, transform, target writes
~~~

Nếu snapshot chiếm hết target write capacity, CDC buffer tăng. Nếu source retention hữu hạn, bị tụt sau window có thể phải bootstrap lại.

### 32.1. Throttling theo bytes và operations

Một cấu hình ý tưởng:

~~~yaml
snapshot:
  maxConcurrentChunks: 4
  targetBytesPerSecond: 40000000
  maxPageBytes: 4000000

stream:
  maxBufferedBytes: 2000000000
  highPriorityWhenLagSecondsAbove: 60

target:
  maxInFlightWrites: 100
  perKeyOrdering: required
~~~

Đây là **mẫu điều khiển tải**, không phải YAML chạy được của một connector nhất định.

### 32.2. Memory buffer và durable buffer

Một buffer 2 GB RAM bị mất khi process crash. Nếu source vẫn giữ changes và checkpoint không tiến qua phần chưa apply thì có thể replay. Nếu source đã cắt log, buffer mất đồng nghĩa gap.

Với snapshot dài và source log ngắn, có thể cần **durable spool** để giữ changes. Durable spool cũng phải có:

- Offset mapping.
- Ordering per source partition.
- Retention/cleanup.
- Checksum/integrity.
- Backpressure khi disk gần đầy.
- Checkpoint để không bỏ records mới được spool nhưng chưa apply.

### 32.3. Không làm vô hạn HTTP requests để quét

Java async scanner có thể tạo 100.000 futures để đọc 100.000 pages, vượt capacity nguồn. Giới hạn in-flight reads, batching, page size và response processing theo source quotas.

### 32.4. Chọn ưu tiên khi CDC lag tăng

Một policy có thể:

~~~text
if CDC lag > 60 seconds:
    reduce snapshot concurrency from 4 to 1
    reserve target write capacity for CDC
else:
    allow snapshot to use spare capacity
~~~

Đừng pause snapshot mãi nếu log retention vẫn bị tiến lên và bootstrap không bao giờ xong. Cần tối ưu tổng thời gian và bảo đảm recovery, không chỉ phản ứng với một metric.

### 32.5. Rate limit của source không bằng target

NoSQL source có scan capacity, CDC stream read limits, target có bulk indexing/write quotas. Một limiter duy nhất không nhất thiết bảo vệ cả ba. Theo dõi từng phía và giảm tải ở nơi làm tăng queue đầu tiên.

## 33. Fault injection: kiểm tra no-gap và no-resurrection

Các thí nghiệm nên chạy trên môi trường kiểm thử với dữ liệu giả, log mutation đầy đủ để đối chiếu **source truth**. Không tắt CDC production hay làm hỏng source thật để thử.

### 33.1. Dataset khởi tạo

~~~text
O100: {status:CREATED, version:1}
O101: {status:PAID,    version:3}
O102: {status:NEW,     version:1}
O103: {status:HELD,    version:4}
O104: absent
~~~

### 33.2. Mutation schedule

~~~text
t0: Open CDC from a documented safe position.
t1: Start snapshot chunks.
t2: Update O100 version 2.
t3: Delete O101 version 4.
t4: Insert O104 version 1.
t5: Update O103 version 5.
t6: Crash snapshot scanner after target writes, before chunk checkpoint.
t7: Restart scanner; replay last chunk.
t8: Crash CDC reader after target apply E5, before checkpoint.
t9: Restart CDC; replay E5.
t10: Wait until target catches up to a verified source boundary.
~~~

### 33.3. Invariants

~~~text
At verified boundary:
  O100 reflects version 2
  O101 is absent/tombstoned at version 4
  O104 exists at version 1
  O103 reflects version 5

No duplicate business side effects from snapshot/replay.
No snapshot v3 resurrects deleted O101.
No older CDC event overwrites newer source state.
~~~

### 33.4. Case A — Gap between scan and subscription

1. Tạo old implementation `snapshot; subscribe LATEST`.
2. Ghi O100 update ở giữa.
3. Xác minh target thiếu update.
4. Sửa bằng safe boundary/capture-before-snapshot protocol.

### 33.5. Case B — CDC event đến trước snapshot page

1. Buffer một snapshot page chứa O101 v3.
2. Source delete O101 v4; CDC applier xử lý delete.
3. Sau đó flush snapshot page v3.
4. Verify target **không hồi sinh O101**.

### 33.6. Case C — Snapshot trước CDC event cũ

1. Stream capture E4 từ lúc scan bắt đầu.
2. Snapshot đọc O100 v5.
3. Relay áp E4 sau snapshot.
4. Với full-state/versioned semantics, target phải **không đi lùi**.

### 33.7. Case D — Duplicate CDC replay

1. Đọc event E7.
2. Target apply E7 thành công.
3. Crash trước checkpoint E7.
4. Restart đọc lại E7.
5. Verify event identity/version làm lần hai thành no-op.

### 33.8. Case E — Delete/recreate cùng key

1. O102 có version 9.
2. Delete version 10.
3. Tạo lại O102 với generation mới/version 1.
4. Verify comparator không coi bản mới là stale chỉ vì `1 < 10`; cần generation/authority rules.

### 33.9. Case F — Stream retention exhausted

1. Tạo safe boundary L0.
2. Ngừng connector đủ lâu để L0 không còn retained trong lab.
3. Resume nhận lỗi.
4. Hệ phải báo `REBOOTSTRAP_REQUIRED` hoặc repair plan.
5. Verify không subscribe ở `LATEST` rồi tuyên bố thành công.

### 33.10. Case G — Shard split

1. Đang stream parent shard P.
2. Theo test setup, nguồn split P thành children C1/C2.
3. Verify reader theo source shard-lineage API, không bỏ child records.
4. Checkpoint theo từng shard.
5. Verify no-gap và ordering per key.

### 33.11. Case H — DDL/schema change

1. Snapshot chunk đầu chứa schema v1.
2. Source thêm/rename field.
3. Stream phát mutation theo schema v2.
4. Verify transformer hỗ trợ cả hai hoặc báo lỗi rõ.
5. Không silent-drop fields trong target.

### 33.12. Case I — Async target apply và checkpoint

1. CDC reader nhận E10, E11.
2. E11 target write trả sớm; E10 vẫn pending.
3. Reader muốn checkpoint E11.
4. Verify chỉ advance tới **contiguous durably applied prefix** của source order hoặc metadata phù hợp; không skip E10.

### 33.13. Case J — Cross-key transaction

1. Source transaction cập nhật Order và Payment.
2. Snapshot thấy chỉ một phần vì scan không có transaction snapshot.
3. Verify pipeline có transaction grouping/consistent cut hoặc **contract eventual projection** được khai báo.
4. Nếu target hứa atomic visibility, test phải fail khi chỉ có một record commit.

### 33.14. Case K — Resume token lỗi và failover

1. Lưu token, làm primary/leader failover theo lab.
2. Reconnect qua driver/SDK.
3. Verify token semantics được tôn trọng.
4. Phân loại lỗi retryable, invalidated và permanently expired.

### 33.15. Case L — Multi-region conflict

1. Region A và B concurrent update cùng key.
2. CDC từ cả hai streams.
3. Verify target conflict resolution theo authority/domain.
4. Không chọn winner bằng timestamp wall-clock một cách âm thầm nếu business invariant không cho phép.

## 34. Reconciliation: chứng minh trạng thái target khớp nguồn

Sau khi pipeline catch up, không nên chỉ kiểm tra `snapshotRowsRead=sourceRowCount` vì:

- Số row thay đổi khi scan.
- Target có filter/transform.
- Deletes không hiện trong row count.
- Hai wrong values có thể vẫn cho tổng count giống nhau.

### 34.1. Snapshot-consistent sampling

Với một tập keys được chọn, đọc source ở một **mốc consistency có ý nghĩa** và đối chiếu target sau khi đã catch up tới mốc tương ứng.

So sánh:

~~~text
key
existence vs tombstone
canonical projected fields
source version / generation
target last applied version
schema version
~~~

Không so một source read ở t=12:00 với target ở t=12:01 rồi kết luận mismatch nếu source đã đổi trong lúc đó; cần causal/checkpoint boundary để loại trừ race.

### 34.2. Hashing theo ranges

Với dữ liệu lớn, có thể tính **canonical hashes** theo chunks/ranges:

~~~text
hash(R) = hash(sorted key + normalized value + version for keys in R)
~~~

Hai phía cần cùng normalization/filter và một consistent boundary. Hash mismatch báo có lỗi; hash match giúp tăng confidence nhưng không phải formal proof tuyệt đối nếu dùng hash hữu hạn, và không cho biết row nào sai cho tới khi drill down.

### 34.3. Reconciliation jobs

Một job chạy định kỳ có thể:

1. Chọn sample/ranges.
2. Chụp source state với boundary.
3. Chờ target applied position vượt boundary phù hợp.
4. So value/existence.
5. Enqueue repair cho mismatch.
6. Ghi audit/provenance của sửa chữa.

Không để repair job upsert dữ liệu cũ không có version guard, nếu không chính nó có thể làm target đi lùi.

### 34.4. Tái dựng index bằng shadow target

Khi không thể chứng minh no-gap vì stream đã hết retention:

~~~text
Live target A serving requests.
Build shadow target B from new safe snapshot boundary.
Apply CDC to B until caught up.
Validate B against source.
Switch read routing/alias to B.
Keep A for rollback until policy allows cleanup.
~~~

Nếu source/target không hỗ trợ atomic alias switch, thực hiện cutover theo giao thức ứng dụng có thể chịu được read transition; không tuyên bố operation atomic khi không có product guarantee.

## 35. Chẩn đoán triệu chứng trong production

| Triệu chứng | Khả năng xảy ra | Điều cần kiểm tra |
| --- | --- | --- |
| Một số Orders thiếu ở target sau bootstrap | Gap scan→stream, cursor/pagination lỗi | Boundary, chunk coverage, resume positions |
| Record đã xóa xuất hiện lại | Old snapshot upsert hoặc old CDC replay | Tombstone/version compare |
| Status đi từ SHIPPED về PAID | Reordering, stale overwrite | Per-key order, target CAS |
| Consumer apply một counter delta hai lần | Snapshot/delta overlap hoặc replay | Operation IDs, dedup/checkpoint |
| Connector báo STREAMING nhưng lag lớn | Apply bottleneck/hot partition | Oldest event age, throughput, backpressure |
| CDC reader không resume sau restart | Token invalid/expired | Stream retention, API mode, lineage |
| Target row count lớn hơn source | Deletes thiếu, filters khác | Delete CDC and reconciliation |
| Row count bằng nhưng values khác | Lost updates, schema mapping | Version/hash comparisons |
| Một shard không tiến | Lease assignment, resharding | Per-shard checkpoints, parent-child graph |
| CDC buffer đầy | Snapshot quá nhanh hoặc target chậm | Rate budgets, buffer storage |
| Snapshot không kết thúc | Hot ranges, pagination loop, chunk owner dead | Chunk state/timeout |
| Schema fields biến mất | Old/new schema transforms mismatch | Schema registry/upcasters |
| Duplicate event IDs khác payload | Mutable transforms hoặc event identity bug | Payload hash, source identity |
| Read index tạm inconsistency multi-record | No atomic target transaction | Transaction grouping expectations |
| Old source token bị skip sau outage | Silent `LATEST` fallback | Gap detection/rebootstrap status |
| Source latency tăng mạnh khi bootstrap | Scan overload/compaction | Read budget, query shape, capacity |
| Failover làm write target hai lần | Multiple connector owners/checkpoint races | Generation fencing, idempotency |

### 35.1. Trình tự debug ưu tiên

1. Xác định **một key sai cụ thể**, source version và target version.
2. Ghi source commit event/time/position theo authoritative log.
3. Tìm snapshot chunk và boundary bao key ấy.
4. Kiểm tra có gap giữa chunk scan và stream subscription không.
5. Kiểm tra CDC event có được read, spool, apply, checkpoint không.
6. Tìm old upsert/delete replay có ghi đè version mới không.
7. Kiểm tra schema transform, filters, key mapping và key reuse.
8. Kiểm tra shard assignment/lineage và retention.
9. Đối soát target; sửa qua guarded repair.
10. Phân loại root cause và bổ sung fault test/recovery rule.

## 36. Case study: xây lại Order Search Index không dừng nhận đơn

Giả sử source có 80 triệu Orders, bốn shards, một read model đã lỗi schema và cần rebuild sang index mới.

**Yêu cầu:**

- Không dừng Order Service.
- Search index mới chứa tất cả Orders đang tồn tại theo projection schema v4.
- Những Orders bị delete trong bootstrap phải không còn được hiển thị.
- Không để old snapshot ghi đè CDC mới.
- Nếu connector crash, có thể restart từ checkpoint.
- Nếu source token hết hạn, phải phát hiện và rebuild an toàn.

### 36.1. Bước 1 — Xác định mức consistency thật sự cần

Search index là eventual read model, có thể chịu **một độ trễ vài giây**; nhưng không được thiếu/hồi sinh Order mãi mãi. Multi-order atomic visibility thường không bắt buộc cho tìm kiếm. Nếu search phục vụ quyết định ràng buộc mạnh (ví dụ inventory/payment), không nên dùng projection eventual làm source of truth.

### 36.2. Bước 2 — Tạo shadow index

~~~text
orders_search_v3  -> live index, đang phục vụ traffic
orders_search_v4  -> shadow index, trống
~~~

Mọi bootstrap/CDC v4 ghi vào shadow index, không làm v3 bị thiếu dữ liệu tạm thời.

### 36.3. Bước 3 — Thiết lập source positions và protocol

Nếu có consistent snapshot boundary dùng được, lấy \(L_0\) theo source API rồi snapshot đúng \(S(L_0)\). Nếu không, bắt stream **trước khi scan**, spool changes và dùng chunk watermark/version guard của connector đã được hỗ trợ.

Ví dụ:

~~~yaml
runId: "orders-rebuild-v4"
sourceScope:
  cluster: "orders-cluster"
  collection: "orders"
target: "orders_search_v4"
phase: "SNAPSHOTTING"
sourceBoundary:
  shardA: "opaque-A"
  shardB: "opaque-B"
  shardC: "opaque-C"
  shardD: "opaque-D"
snapshotChunks: 640
completedChunks: 0
streamBuffer: "durable-spool-orders-v4"
~~~

**Đây là mô hình state**, không phải cấu hình của MongoDB/DynamoDB hay một connector cụ thể. Vị trí source theo shard chỉ phù hợp nếu API/protocol cung cấp ordering/boundary tương ứng.

### 36.4. Bước 4 — Quét bounded chunks

Worker pool nhận chunks, mỗi worker có:

- Source read concurrency quota.
- Page size theo số bytes.
- Mốc checkpoint đã apply bền.
- Target bulk write capacity.
- Retry budget và immutable run ID.

Nếu cursor gặp lỗi, worker re-read chunk theo protocol; target upserts phải idempotent.

### 36.5. Bước 5 — Apply CDC chồng lấp an toàn

~~~text
Snapshot: O101 version 11
CDC:      O101 version 12 DELETE
~~~

Sau cả hai, v4 không có O101; target lưu metadata/tombstone để snapshot v11 replay không hồi sinh.

~~~text
Snapshot: O102 version 5
CDC:      O102 version 6 PAID
~~~

Sau cả hai, v4 hiển thị O102 version 6. Nếu CDC v6 đến trước snapshot v5, version guard không cho đi lùi.

### 36.6. Bước 6 — Catch up và validate

Khi scan đủ 640 chunks:

1. Xác minh chunk completion checkpoints bền.
2. Replay CDC buffered backlog.
3. Chờ target applied positions đạt một verified source boundary.
4. Chạy sampling/hash per source range.
5. Kiểm tra tombstone/delete coverage.
6. Quan sát lag per shard dưới SLO trong một khoảng ổn định.

### 36.7. Bước 7 — Chuyển traffic

Khi index mới đạt điều kiện, chuyển alias/routing từ v3 sang v4 bằng cơ chế được search engine hỗ trợ. Duy trì CDC v4 sau cutover. Nếu cần rollback, giữ v3 hoặc có plan để đồng bộ trở lại từ verified boundary.

### 36.8. Bước 8 — Dọn dữ liệu cũ

Chỉ xóa v3 sau thời gian quan sát/rollback. Dọn snapshot spool/checkpoints theo retention; không xóa stream positions hoặc tombstones khi vẫn có khả năng replay old events.

### 36.9. Nếu source stream hết retention trước cutover

**Không** gắn v4 làm live vì nó có gap không biết vị trí. Đánh dấu run thất bại và rebuild từ một boundary mới, hoặc thực hiện một reconciliation có proof coverage phù hợp. Index v3 tiếp tục phục vụ nếu còn chấp nhận được; có thể áp read fallback/maintenance policy theo business.

## 37. Một ma trận quyết định khi chọn kỹ thuật bootstrap

| Điều kiện của nguồn | Phương án xem xét | Điểm cần chứng minh |
| --- | --- | --- |
| Có consistent snapshot gắn được một source position | Snapshot tại boundary + replay sau boundary | Transaction/read scope, resume semantics |
| Không có global snapshot nhưng có CDC log giữ đủ lâu | Subscribe trước + durable spool + version-aware merge | No-gap, per-key order, deletes |
| Scan lâu và stream vẫn phải chạy | Incremental snapshot với chunk watermarks | Collision algorithm và checkpoints |
| Mọi record có monotonic version từ single authority | Versioned upsert/tombstone target | Atomic source version + target CAS |
| Snapshot chỉ có live reads không phiên bản | Connector-assisted reconciliation/backfill | Completeness under concurrent mutations |
| CDC log đã hết retention | Rebootstrap/new boundary | Không silent skip |
| Source multi-writer active-active | Causal conflict resolution hoặc single authority | Concurrent writers và delete policy |
| Target cần complete event history | Replay event/transaction ledger | Snapshot chỉ giữ hiện trạng, không đủ |
| Source không hỗ trợ delete events cần thiết | Reconciliation/hard delete coverage protocol | Không hồi sinh dữ liệu cũ |
| Thời gian quét dài hơn stream retention | Durable spool hoặc tăng retention/bounded chunks | Không tràn buffer hoặc mất resume |

### 37.1. Khi nào được quiesce writes?

Một hệ nội bộ nhỏ có thể dừng writes trong 5 phút:

~~~text
Pause writes.
Take snapshot.
Establish next log position.
Resume writes and stream.
~~~

Đây là phương án đơn giản về mặt lý luận **nếu việc pause thật sự được cưỡng chế** và snapshot/position thuộc cùng boundary. Nhưng với ứng dụng 24/7 hoặc multi-region, quiesce thường không khả thi; không tuyên bố “pause thành công” chỉ vì UI hiển thị maintenance.

### 37.2. Snapshot từ backup

Một database backup/snapshot có thể có **recovery log position** giúp nối từ bản backup tới CDC. Nếu được sản phẩm hỗ trợ, điều đó có thể giảm read load của snapshot production. Tuy nhiên phải xác minh:

- Backup là transactionally consistent theo scope cần.
- Log history từ backup position còn retained.
- Identity/generation của source không thay đổi.
- Restore làm thay source epochs/IDs hoặc schema không.
- Delete/tombstone/TTL behavior khi restore.

Backup file không tự là một source snapshot có thể nối stream nếu thiếu metadata cutover.

### 37.3. Trường hợp không cần stream liên tục

Một báo cáo batch chạy mỗi ngày có thể chấp nhận **full snapshot replacement** theo kỳ thay vì CDC liên tục. Đừng chọn CDC phức tạp khi yêu cầu chỉ là dữ liệu đủ mới mỗi 24 giờ và có thể rebuild target bằng snapshot atomically/replaceable.

## 38. Bài tập thực hành

### Bài 1 — Nhận diện gap

Một pipeline:

~~~text
09:00 Start scan.
09:10 Read O101 v3.
09:20 Source updates O101 v4.
10:00 Finish scan.
10:01 Subscribe CDC starting at LATEST.
~~~

1. O101 target sẽ ở version nào nếu không có bước khác?
2. Vì sao CDC không phát v4 cho subscriber bắt đầu lúc 10:01?
3. Đề xuất cách lấy consistent cut hoặc capture-before-snapshot.
4. Nếu O101 bị delete lúc 09:20, triệu chứng còn nguy hiểm hơn thế nào?

### Bài 2 — Snapshot đến muộn

CDC applier đã apply O202 v9. Một page snapshot cũ chứa O202 v7 đến sau.

1. Vì sao blindly upsert là sai?
2. Version guard cần thực thi ở đâu?
3. Nếu v7 là delta `+5 points`, có thể bỏ như snapshot full state không?
4. Nếu source có hai region tự cấp v9 concurrent, scalar version đủ không?

### Bài 3 — Consistent cut

Một source log có mutations `C1..C100`. Snapshot `S(100)` được nguồn xác nhận phản ánh toàn bộ changes tới 100, không chứa changes sau 100.

1. CDC phải bắt đầu từ position nào theo contract?
2. Nếu subscription chỉ cho inclusive resume tại 100, dedup/overlap xử lý ra sao?
3. Nếu scanner đọc một số pages tại state 102 nhưng vẫn gọi là S(100), lỗ hổng nào?
4. Nếu stream cắt log tới position 110 trước khi replay, điều gì xảy ra?

### Bài 4 — Source positions không cùng scope

~~~text
Shard A offset=1500
Shard B offset=1200
~~~

1. Có thể nói A đã tiến xa hơn B theo thời gian thật không?
2. Checkpoint cho hai shards nên lưu thế nào?
3. Nếu B bị split thành B1/B2, cần đọc gì trong stream contract?
4. Tại sao một `max(offset)` chung có thể gây mất dữ liệu?

### Bài 5 — Incremental chunk watermark

Scanner quét range `O100–O199` giữa low watermark L và high watermark H. Trong khoảng đó source:

~~~text
Update O120
Delete O135
Insert O175
~~~

1. Những keys nào có collision candidates?
2. Vì sao snapshot row O135 có thể hồi sinh record?
3. Cần information nào (before/after image, version, position, tombstone)?
4. Tại sao high watermark phải có nghĩa trong cùng source stream?

### Bài 6 — Snapshot không phải event history

Snapshot đọc `Order O101 status=SHIPPED`.

1. Có được phát `OrderPaid` cho payment consumer như một event mới không?
2. Những thông tin lịch sử nào không thể suy từ trạng thái SHIPPED?
3. Event/record type nào dùng để rebuild search index?
4. Nếu downstream cần financial ledger, phải lấy dữ liệu ở đâu?

### Bài 7 — Tombstone và delete

~~~text
Snapshot O101 v11 buffered.
CDC DELETE O101 v12 applied.
Snapshot v11 arrives.
~~~

1. Điều kiện nào chặn bản v11?
2. Vì sao chỉ xóa vật lý document ở target có thể không đủ?
3. Khi nào có thể dọn tombstone?
4. Nếu O101 được tạo lại với generation mới/version 1, comparator phải xử lý thế nào?

### Bài 8 — Chunk checkpoint

Scanner áp 500 rows rồi crash trước khi ghi `chunk COMPLETE`.

1. Khi restart nên retry hay bỏ qua chunk?
2. Target upsert cần idempotent thế nào?
3. Nếu `lastKey` đã được lưu trước khi áp rows cuối, lỗi gì?
4. Vì sao page size phải giới hạn theo bytes/latency?

### Bài 9 — CDC checkpoint

~~~text
Read event E18.
Write checkpoint E18.
Crash before target apply.
~~~

1. Có thể mất E18 không?
2. Đổi thứ tự apply→checkpoint giải quyết lớp rủi ro nào?
3. Vì sao vẫn có duplicate khi crash sau apply?
4. Khi nào target state và checkpoint có thể commit cùng transaction?

### Bài 10 — Source log retention

Snapshot mất 8 giờ, stream giữ 4 giờ.

1. Nếu không đọc stream trong lúc scan, có thể resume từ đầu scan không?
2. Nếu đọc song song vào durable spool, cần sizing những gì?
3. Nếu resume token đã hết hạn, fallback `LATEST` có được coi đúng không?
4. Đề xuất rebootstrap/repair strategy.

### Bài 11 — MongoDB Change Streams

Một connector dùng `watch()` sau khi `find()` quét toàn bộ collection.

1. Vì sao có gap?
2. `resumeAfter`/`startAfter`/`startAtOperationTime` cần được chọn theo điều kiện nào?
3. Vì sao `fullDocument: updateLookup` có thể không là exact historical post-image?
4. Delete event có chắc bao gồm mọi field của document cũ không?

### Bài 12 — DynamoDB Scan/Streams

Team bật `ConsistentRead` trên `Scan` và bắt đầu stream từ `LATEST` khi scan xong.

1. Vì sao Scan không bảo đảm snapshot isolation toàn bảng?
2. Vì sao `LATEST` sau scan tạo gap?
3. Nếu Scan lâu hơn stream retention, chọn chiến lược nào?
4. StreamViewType ảnh hưởng khả năng tạo full target document thế nào?

### Bài 13 — Cosmos DB feed

Một consumer cần bắt **mọi intermediate update và delete** chứ không chỉ latest state.

1. Cần đọc feed mode nào và vì sao?
2. Các continuation tokens có scope theo feed range/partition không?
3. Single-partition transactional batch có tạo snapshot toàn container không?
4. Khi partition split, checkpoint/rebalance cần xử lý gì?

### Bài 14 — Cassandra token ranges

Scanner chia table thành 100 token ranges và quét bằng QUORUM reads.

1. QUORUM có tự tạo consistent cut toàn bảng không?
2. Điều gì xảy ra khi node join và token ownership thay đổi?
3. CDC/tombstone/TTL cần được theo dõi thế nào?
4. Nếu connector không có verified cutover protocol, có được tuyên bố mirror exact không?

### Bài 15 — Full state vs delta

Events được nhận:

~~~text
E11: points += 5
E12: points -= 2
~~~

Snapshot đã chứa points=103 sau E12, nhưng replay E11/E12 một lần nữa.

1. Tại sao kết quả có thể sai?
2. Nếu events mang full state snapshot mỗi version thì rule khác thế nào?
3. Khi nào event ID dedup đủ, khi nào cần baseline/cutover version?
4. Gợi ý replay ledger theo source prefix.

### Bài 16 — Transaction nhiều records

Một transaction T1 cập nhật Order và Payment, nhưng scanner quét hai collections tại những thời điểm khác nhau.

1. Có thể thấy half-transaction state không?
2. Khi nào điều đó chấp nhận được với eventual read model?
3. Khi nào cần transaction snapshot/target grouped commit?
4. Nếu event streams theo hai shards khác nhau, cần metadata gì?

### Bài 17 — Schema evolution

Giữa snapshot và CDC, schema đổi `total` thành `totalMinorUnits`, thêm `currency`.

1. Một versioned transformer nên làm gì?
2. Tại sao event record cần schema version?
3. Nếu rollback deployment, events mới có thể làm consumer cũ lỗi thế nào?
4. Rebootstrap/index migration cần được tổ chức ra sao?

### Bài 18 — Multi-region concurrent writers

Region A cập nhật O101 thành CANCELLED, region B cập nhật O101 thành CONFIRMED cùng lúc khi mất mạng.

1. Tại sao một global CDC reader cần conflict resolution?
2. Wall-clock LWW có thể làm mất intent gì?
3. Nếu business yêu cầu không double charge, authority phải đặt ở đâu?
4. Outbox/CDC có thể tự quyết định kết quả nghiệp vụ không?

### Bài 19 — Load test

Snapshot 500 triệu rows, row trung bình 2 KiB, source change rate 15.000 events/s, change record 800 bytes.

1. Tính raw snapshot bytes.
2. Tính change bytes phát sinh trong 6 giờ scan.
3. Nếu buffer giới hạn 100 GB, có đủ để spool tất cả changes 6 giờ không?
4. Nếu cần tăng scan throughput, những resource budgets nào phải theo dõi?

### Bài 20 — Runbook rebootstrap

Connector đang chạy 10 ngày thì stream token hết hạn sau outage 48 giờ. Target vẫn phục vụ người dùng.

Hãy thiết kế kế hoạch gồm:

1. Cách phát hiện và công bố trạng thái `DEGRADED`.
2. Cách tạo shadow target.
3. Cách chọn source boundary mới.
4. Snapshot chunks, buffering và delete correctness.
5. Reconciliation/checkpoint.
6. Cutover read traffic.
7. Retention, rollback và observability.

### Bài 21 — Quy trình kiểm tra end-to-end

Với lịch:

~~~text
t0 Start CDC safely.
t1 Start snapshot.
t2 O101 updates v4.
t3 O102 deletes v5.
t4 Scanner crashes.
t5 Source shard splits.
t6 Scanner resumes; CDC reader rebalances.
t7 Target catches up.
~~~

Vẽ:

- Snapshot progress per chunk.
- CDC positions per shard.
- Source versions/tombstones của O101 và O102.
- Crash windows cần idempotency.
- Các assertions để khẳng định no-gap/no-resurrection.

### Bài 22 — Phản biện một kiến trúc

Một proposal ghi:

> “Quét hết database bằng 20 threads, rồi bắt đầu MongoDB Change Stream từ thời điểm kết thúc. Nếu có record thiếu, chạy lại job mỗi tháng. Dùng `updatedAt` làm version cho target. Delete chỉ cần `DELETE` document. Checkpoint stream lưu ngay sau khi nhận event.”

Hãy chỉ ra **ít nhất tám lỗ hổng correctness** và đề xuất một protocol được hỗ trợ, gồm các biện pháp cho gap, overlap, delete, commit outcome và checkpoint.

## 39. Gợi ý giải một số bài tập

### 39.1. Bài 1 — Bỏ sót update ở khoảng giao

Snapshot đọc O101 v3 lúc 09:10, update v4 commit lúc 09:20, còn stream chỉ bắt đầu ở 10:01 nên target **có thể ở v3**. Nếu mutation là DELETE, target có thể giữ một record không còn ở nguồn. Cần một điểm cut có thể replay CDC từ trước update hoặc một capture-before-snapshot/chunk watermark protocol.

### 39.2. Bài 2 — CDC v9 trước snapshot v7

`applyIfNewer` ở **target commit boundary** phải từ chối v7 nếu v9 đã được chấp nhận. Với delta operations, việc bỏ một event dựa trên version có thể làm sai tổng nếu target chưa từng áp effect đó; cần baseline/cutover rõ ràng cùng sequence hoặc idempotent operation ledger.

### 39.3. Bài 3 — Quy tắc replay từ cut

Nếu `S(100)` chính xác là trạng thái sau C100, replay mutations **sau C100** trong source ordering. Nếu API chỉ hỗ trợ inclusive start tại C100, có thể đọc lại C100 rồi **dedup an toàn**, miễn không bỏ một event chưa có trong snapshot. Nếu log chỉ còn từ C110, không được nhảy đến C110 và vẫn tuyên bố no-gap.

### 39.4. Bài 4 — Không so chéo shard positions

Offset 1500 của shard A và 1200 của B thuộc **hai miền thứ tự khác nhau**. Checkpoint phải giữ từng shard position, theo dõi parent-child lineage nếu shard split và chỉ advance sau durable apply. `max(1500,1200)` không phải global checkpoint hợp lệ.

### 39.5. Bài 7 — Delete guard

Một tombstone v12 giữ metadata rằng O101 đã bị xóa. Khi snapshot v11 tới sau, target từ chối old upsert. Nếu chỉ xóa vật lý không giữ version/order guard, bản cũ có thể resurrect. Khi key được tái sử dụng, cần generation/epoch hoặc một source sequence tăng qua cả delete/recreate.

### 39.6. Bài 9 — Apply trước checkpoint

Checkpoint trước apply có thể khiến E18 bị skip sau crash. Apply trước rồi checkpoint có thể khiến replay duplicate, nhưng đúng nếu apply idempotent. Có thể gộp target state và checkpoint trong **một target transaction** khi chúng thực sự nằm trong atomic scope; không tự có transaction với source stream.

### 39.7. Bài 19 — Dung lượng ước lượng

Raw snapshot:

\[
500\,000\,000\times2048 =
1\,024\,000\,000\,000\text{ bytes}
\]

Xấp xỉ **1.024 TB decimal raw payload**; chưa tính indexes, compression, object overhead, replication.

Raw changes trong 6 giờ:

\[
15\,000\times800\times6\times3600 =
259\,200\,000\,000\text{ bytes}
\]

Xấp xỉ **259,2 GB decimal**, lớn hơn buffer 100 GB chưa tính overhead. Cần tăng spool capacity, consumer apply đồng thời hoặc giảm snapshot/catch-up duration, đồng thời xét retention nguồn.

### 39.8. Bài 22 — Những lỗi cần phát hiện

Proposal có thể sai ở:

1. Stream bắt đầu quá muộn tạo gap.
2. Scan bằng nhiều threads không tự tạo consistent snapshot.
3. `updatedAt` có thể chịu clock skew/client timestamps.
4. Target upsert không có atomic version guard.
5. Không giữ tombstone nên có thể resurrect.
6. Checkpoint ngay khi nhận event có thể skip uncommitted apply.
7. Không có recovery khi resume token hết retention.
8. Không có chunk coverage/retry idempotent protocol.
9. Không phân biệt snapshot row với mutation/delta.
10. Không có reconciliation trước khi target được công bố đầy đủ.

Hướng giải: dùng connector/snapshot protocol có **consistent cut hoặc capture-before-snapshot với watermarks/merge**, source-specific positions, durable checkpoints sau target apply và repair/rebootstrap khi gap không thể phục hồi.

## 40. Checklist triển khai snapshot → streaming

### Nguồn và giao thức

1. **Source of truth** có được xác định rõ không?
2. Phạm vi dữ liệu là table, collection, namespace, partition hay nhiều clusters?
3. Source có **consistent snapshot gắn mốc CDC** được không?
4. Nếu không, có capture-before-snapshot/collision-window protocol được hỗ trợ không?
5. Source positions thuộc scope nào: LSN, shard offset, resume token?
6. Có lưu **source identity, generation và topology metadata** kèm token không?
7. Có hiểu read concern/consistency và multi-region conflict semantics không?
8. Có xác định được source log retention đủ cho snapshot/recovery không?
9. Source phát deletes, TTL deletes, key changes và transaction metadata thế nào?
10. Các features cần thiết có hỗ trợ ở **đúng version, SDK và deployment** không?

### Snapshot

11. Có kế hoạch scan theo **bounded chunks/ranges** không?
12. Paging cursor có ổn định và resume được sau restart không?
13. Có checkpoint chỉ sau khi target đã durable apply không?
14. Chunk retry có idempotent không?
15. Có giới hạn memory/page bytes/concurrent scans không?
16. Snapshot record có được phân biệt khỏi business event không?
17. Snapshot rows có source version/metadata cần thiết để tránh stale overwrite không?
18. Có chính sách cho schema transformations/filter changes trong khi scan không?
19. Có phương án khi snapshot transaction quá lâu hoặc snapshot token hết hạn không?
20. Có xác minh complete coverage thay vì chỉ đếm số rows đọc không?

### Luồng thay đổi

21. CDC có bắt đầu đủ sớm để **không có gap** không?
22. Nếu snapshot/CDC overlap, có dedup/version/collision handling không?
23. Stream buffer có durable hoặc recoverable từ retained log không?
24. Có tách **read offset** khỏi **durably applied offset** không?
25. Có ordering theo key/partition và transaction grouping khi cần không?
26. Có tính toán effects của source shard split/rebalance không?
27. Có phát hiện resume position hết hạn và **không silent skip** không?
28. Có bounded retries, backpressure và lag alert không?
29. Có xử lý full-state events khác delta events không?
30. Event IDs/schemaVersions có ổn định qua replay/upgrade không?

### Target và correctness

31. Target upserts/deletes có **atomic conditional guard** tại commit không?
32. Có tombstone/version metadata để ngăn resurrection không?
33. Key reuse có generation/epoch strategy không?
34. Target có tránh duplicate business effects khi snapshot/replay không?
35. Có biết checkpoint cùng target transaction nếu sản phẩm hỗ trợ không?
36. Target có phục vụ eventual-state projections hay yêu cầu multi-record atomic visibility?
37. Có các bài test **gap, overlap, delete, rollback, retry, timeout, partition move** không?
38. Có reconciliation per key/range tại verified boundary không?
39. Có shadow target/cutover/rollback plan khi rebootstrap không?
40. SLO về snapshot completion, commit-to-visible lag và recoverability có đo được không?

### Vận hành

41. Có dashboard phase `SNAPSHOTTING`, `CATCHING_UP`, `STREAMING`, `DEGRADED` không?
42. Có metrics per-shard lag thay vì chỉ trung bình không?
43. Có alert oldest unprocessed age gần retention không?
44. Có giới hạn scan load để không làm source production quá tải không?
45. Có procedure backfill sau schema change hay gap đã mất không?
46. Có retention policy cho durable spool, checkpoints, tombstones và old target index không?
47. Có audit/source provenance của repair operations không?
48. Có tránh đưa PII/high-cardinality IDs vào metric labels không?
49. Khi thay phiên bản connector hoặc topology, có review lại cutover guarantee không?
50. Có một người/nhóm owner chịu trách nhiệm quyết định **target đủ điều kiện phục vụ** không?

## Kết luận

**Snapshot ban đầu và CDC liên tục không phải hai bước nối tuần tự một cách cơ học.** Đó là một giao thức đồng bộ phải bảo vệ trạng thái trong lúc nguồn vẫn nhận writes.

Những điểm cần nhớ:

- **`Scan; then subscribe LATEST` có thể bỏ sót updates/inserts/deletes** nằm giữa hai thao tác.
- **Subscribe sớm nhưng apply không có ordering/guard vẫn sai**: snapshot cũ có thể ghi đè CDC mới hoặc hồi sinh record đã xóa.
- **Consistent cut** là ranh giới cùng ý nghĩa giữa snapshot và source change history; log position chỉ có nghĩa trong **scope** của engine.
- Nếu nguồn hỗ trợ, dùng **snapshot tại mốc log xác định rồi replay từ vị trí đúng**. Nếu không, cần **capture-before-snapshot, buffering và thuật toán collision/watermark/merge được chứng minh**.
- **Incremental snapshot** cho phép quét theo chunks khi live stream vẫn chạy, nhưng đòi hỏi bookkeeping và source-specific semantics cẩn thận.
- **Source version, event ID và CDC position phục vụ các mục đích khác nhau**. Không dùng wall-clock `updatedAt` như một global commit sequence tùy ý.
- **Tombstones và version guards** bảo vệ delete correctness; xóa physical metadata quá sớm có thể cho old snapshot resurrect record.
- **Checkpoint chỉ được tiến sau khi event đã được target áp bền vững** hoặc lưu trong một buffer bền có thể replay. Duplicate delivery cần idempotent apply.
- **Per-partition/shard positions không tạo total order toàn cục**; multi-key transaction consistency cần metadata/commit protocol riêng.
- **Retention và backpressure là yêu cầu correctness**. Nếu connector mất source position và không thể replay, phải phát hiện gap và rebootstrap/reconcile.
- **Snapshot mang trạng thái, không phải lịch sử domain events**. Không tự kích hoạt thanh toán/email hoặc các non-idempotent side effects từ snapshot records.
- **MongoDB, DynamoDB, Cosmos DB, Cassandra và các connectors khác có guarantees khác nhau**; luôn đọc đúng API/phiên bản/topology, không bê nguyên thuật toán từ một nguồn sang nguồn khác.
- **Sau catch-up vẫn phải xác minh**: chunk coverage, per-shard progress, sample/source-target consistency, deletes, event ordering, replication lag và recovery.

Câu hỏi quan trọng nhất trước khi bật pipeline không phải “Snapshot chạy xong chưa?”, mà là: **“Ta chứng minh bằng cơ chế nào rằng mọi thay đổi tại ranh giới đã được đưa vào target ít nhất một lần, không có bản cũ ghi đè bản mới, và nếu có crash/retention gap thì hệ biết dừng, phục hồi hoặc khởi tạo lại một cách kiểm chứng được?”**
