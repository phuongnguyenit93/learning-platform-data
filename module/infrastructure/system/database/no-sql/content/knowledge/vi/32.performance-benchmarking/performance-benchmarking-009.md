# Phân trang, kích thước lô và số lần trao đổi mạng trong hiệu năng NoSQL

## 1. Bài toán mở đầu: tại sao truy vấn nhanh nhưng API lại chậm?

Một ứng dụng Java đọc 100.000 đơn hàng từ cơ sở dữ liệu NoSQL để xuất báo cáo. Truy vấn theo index chỉ mất vài mili giây ở server, nhưng API lại mất hàng chục giây. Một lập trình viên phát hiện code đang yêu cầu **một đơn hàng ở mỗi lần gọi**:

```text
Java service                Database
   |---- GET order 1 ---------->|
   |<--------- result ----------|
   |---- GET order 2 ---------->|
   |<--------- result ----------|
   |          ...               |
   |---- GET order 100000 ----->|
   |<--------- result ----------|
```

Nếu mỗi lần trao đổi đi-về qua mạng mất trung bình 8 ms và các lời gọi được thực hiện tuần tự, chỉ riêng phần chờ mạng đã có thể lên tới:

\[
100\,000 \times 0.008\ \text{s}=800\ \text{s}
\]

Đây là **ước lượng lý tưởng hóa**, không phải kết quả benchmark: một client có thể multiplex, có caching, server xử lý không đồng đều và tổng thời gian thực tế còn gồm truyền bytes, giải mã, queueing, GC và I/O.

Một đồng nghiệp sửa thành “đọc 100.000 bản ghi trong một lần”:

```text
Java service ---- request huge result ----> Database
Java service <--- 100000 large documents -- Database
```

Số lần trao đổi ít đi, nhưng giờ response rất lớn, dễ gây heap pressure, GC pause, timeout và làm một request giữ kết nối quá lâu.

Giải pháp không nằm ở hai cực đoan “một record một request” hoặc “tất cả records trong một response”. Ta cần **phân trang**, **kích thước lô hợp lý**, **giới hạn lượng dữ liệu trả về**, và cách đo **network round trips** lẫn thời gian thực thi thật của NoSQL.

Bài này thuộc chương **Hiệu năng và đo tải**, giúp bạn thiết kế và đo các đường đọc/ghi nhiều bản ghi trên MongoDB, Cassandra, DynamoDB, Redis, Elasticsearch/OpenSearch, Neo4j hoặc những hệ NoSQL khác.

## 2. Mục tiêu học tập

Sau bài học, bạn cần:

1. Phân biệt **API page size**, **driver fetch size**, **database cursor batch size**, **batch write size** và **concurrency limit**.
2. So sánh offset pagination, keyset/seek pagination, server cursor và opaque continuation token.
3. Biết vì sao phân trang phải đi với **sort ổn định, tie-breaker, index/access pattern và consistency contract**.
4. Ước lượng ảnh hưởng của RTT, payload size, bandwidth, serialization, DB execution và request queueing đến throughput/p95/p99.
5. Giải thích vì sao lô nhỏ gây nhiều lần trao đổi còn lô quá lớn có thể tăng memory, tail latency, retry cost và hotspot.
6. Áp dụng phân trang/continuation token đúng phạm vi với MongoDB, Cassandra, DynamoDB, Redis và search engine.
7. Phân biệt bulk writes và pipelining với **transaction**, **exactly-once**, **idempotency** và **atomicity**.
8. Thiết kế cursor/page token có scope tenant, thời hạn, filter/sort và phiên bản định dạng.
9. Thực hiện benchmark có kiểm soát, đo số requests, bytes, pool waits, backpressure và kết quả đúng.
10. Chọn chiến lược cho UI danh sách, API mobile, export hàng triệu records và ingestion/batch workers.

## 3. Năm kích thước dễ bị nhầm

| Tham số | Nó kiểm soát điều gì? | Ví dụ | Không được suy điều gì? |
|---|---|---|---|
| **API page size** | Số phần tử một response HTTP cho người gọi | `limit=25` | Driver chỉ fetch đúng 25 records mỗi network round trip |
| **Driver fetch size** | Số rows/documents hoặc lượng dữ liệu lấy trong một đợt driver–DB | `fetchSize=500` | API trả luôn 500 rows |
| **Cursor batch size** | Số docs một batch cursor được yêu cầu, trong giới hạn server/protocol | `batchSize(200)` | Luôn nhận đúng 200 docs/batch |
| **Batch write size** | Số mutations gom trong một request/bulk call | `500 updates` | 500 updates tạo một transaction atomic |
| **Max in-flight operations** | Số operation đồng thời đang chờ/đang chạy | `32` | Server có 32 connections hoặc RTT biến mất |

Một API có thể trả 25 items, nhưng backend đọc 200 records để thực hiện filter, join mô phỏng hoặc prefetch. Một cursor có thể nhận nhiều batches nhưng chỉ gửi từng page nhỏ ra client. Một bulk write có thể chứa 500 mutations nhưng server vẫn thực hiện nhiều thao tác nội bộ và trả **partial failures**.

### Tham số không tồn tại trên mọi database

Một SDK dùng `pageSize`, SDK khác dùng `batchSize`, có hệ áp **giới hạn bytes trước giới hạn rows**. Đừng tự động ánh xạ cùng một con số cho tất cả adapters.

## 4. Đo số lần trao đổi mạng (*round trips*)

Một **network round trip** thường được hình dung là một request đi đến endpoint và response quay lại:

```text
Client ---- request ----> DB
Client <--- response ---- DB
          one round trip
```

Với \(N\) items, \(B\) items/batch và mỗi batch cần một request tuần tự, số lần lấy dữ liệu xấp xỉ:

\[
R_{\text{fetch}}\approx\left\lceil \frac{N}{B}\right\rceil
\]

Nếu \(N=10\,000\):

| Batch size B | Số đợt lý tưởng |
|---:|---:|
| 1 | 10.000 |
| 10 | 1.000 |
| 50 | 200 |
| 100 | 100 |
| 500 | 20 |
| 1.000 | 10 |
| 5.000 | 2 |

Đây là công thức **ước lượng lượng đợt lấy dữ liệu**, không phải tổng mọi network packets/round trips của driver: có thể còn handshake, topology discovery, auth, server cursor operations, retries, heartbeats, metadata calls và một lần fetch cuối để biết hết dữ liệu.

### Công thức thời gian đơn giản

Với batch requests **tuần tự**:

\[
T \approx R\times RTT + T_{\text{DB}} + T_{\text{transfer}} + T_{\text{decode}} + T_{\text{app}}
\]

Trong thực tế các thành phần có thể chồng lấp: database thực thi khi request đang transit, network truyền song song với decode streaming, SDK prefetch batches. Công thức chủ yếu giúp **phát hiện thành phần chi phối**.

### RTT khác bandwidth

Một đường mạng có RTT cao nhưng throughput tốt có thể bị ảnh hưởng nặng bởi quá nhiều requests nhỏ. Một đường có RTT thấp nhưng bandwidth thấp sẽ mất nhiều thời gian khi batch chứa document lớn.

## 5. Một ví dụ tính toán để trực giác rõ hơn

Giả sử:

- Cần đọc 12.000 records.
- Mỗi record sau projection trung bình 2 KiB.
- RTT trung bình là 15 ms.
- Driver thực hiện từng batch tuần tự.
- Thời gian DB/server execution và (de)serialization tạm bỏ qua để lập phép tính đơn giản.

Tổng payload:

\[
12\,000\times2\ \text{KiB}\approx23.4\ \text{MiB}
\]

Nếu fetch 20 records/batch:

\[
R=\lceil12\,000/20\rceil=600
\]

Network wait lý tưởng hóa:

\[
600\times15\ \text{ms}=9\ \text{s}
\]

Nếu fetch 300 records/batch:

\[
R=\lceil12\,000/300\rceil=40
\]

Network wait:

\[
40\times15\ \text{ms}=0.6\ \text{s}
\]

Nhưng batch 300 records x 2 KiB đã khoảng **600 KiB payload**, chưa gồm protocol/metadata, và tổng payload của cả job **vẫn gần 23.4 MiB**. Nếu mỗi record là 100 KiB thay vì 2 KiB, batch 300 thành khoảng 29 MiB và có thể vượt giới hạn response/command hoặc gây memory pressure.

**Kết luận:** giảm \(R\) thường hữu ích khi bị RTT chi phối, nhưng batch size phải được chọn cùng **kích thước bytes, độ phân tán rows, giới hạn driver/server và SLO tail latency**.

## 6. Bốn kiểu phân trang thường gặp

### 6.1. Offset/limit pagination

```text
GET /orders?page=101&pageSize=20
skip 2000, return 20
```

Ưu điểm: UI dễ hiểu, có thể nhảy đến trang bất kỳ khi backend hỗ trợ tốt.

Nhược điểm: ở nhiều NoSQL query plans, database vẫn phải **đi qua hoặc loại bỏ** nhiều rows trước offset, khiến trang sâu chậm; đồng thời insert/delete trong quá trình duyệt dễ gây trùng hoặc thiếu records.

### 6.2. Keyset/seek pagination

```text
First page:
  sort createdAt DESC, id DESC
  limit 20

Next page:
  sort createdAt DESC, id DESC
  where tuple(createdAt,id) < lastSeenTuple
  limit 20
```

Ưu điểm: tránh offset scan lớn khi index phù hợp, ổn định tương đối trước insert ở đầu danh sách.

Nhược điểm: cần sort key ổn định và unique tie-breaker, không dễ nhảy thẳng đến page 100, và **không tự bảo đảm snapshot nhất quán** nếu dữ liệu thay đổi trong lúc duyệt.

### 6.3. Server-side cursor

Database giữ hoặc cung cấp trạng thái truy vấn để lấy các batches tiếp theo:

```text
query -> first batch + cursor handle
getMore(cursor) -> next batch
...
close / exhaust cursor
```

Ưu điểm: phù hợp streaming kết quả và tránh gửi toàn bộ dữ liệu cùng lúc.

Nhược điểm: cursor có vòng đời, timeout, tài nguyên server/client và khả năng bị invalidated khi topology thay đổi; SDK khác nhau cung cấp semantics khác nhau.

### 6.4. Opaque continuation token

```json
{
  "items": ["..."],
  "nextPageToken": "opaque-token"
}
```

Token có thể chứa hoặc tham chiếu state query, last evaluated key, snapshot ID, filter hash hoặc paging state. Client nên **gửi lại token nguyên vẹn**, không tự tính `pageNumber*limit` trừ khi API định nghĩa rõ.

**Token không mặc định là cursor server-side**: nhiều NoSQL SDK trả token có thể dùng để resume query ở lần request mới, trong khi server cursor sử dụng trạng thái riêng.

## 7. Offset pagination: tiện nhưng trang sâu có giá

Giả sử collection có 5 triệu bản ghi và index theo `tenantId, createdAt`. Một API:

```text
/orders?tenant=T01&sort=createdAt_desc&skip=100000&limit=25
```

Ở nhiều kiểu kế hoạch thực thi, server phải đi qua một đoạn lớn của index để **skip 100.000** rồi mới trả 25 records. Không thể coi read cost luôn bằng 25 chỉ vì response trả 25.

### Vì sao càng sâu càng chậm?

- Phải traverse các index entries/records trước offset.
- Có thể fetch full documents nếu index không covering.
- Sort thiếu index có thể đòi đọc/sắp xếp nhiều rows.
- Filter có selectivity thấp làm tăng rows examined.
- CPU/IO/cache misses tăng ngay khi response size vẫn nhỏ.

Độ phức tạp tùy engine/query plan và index; không tuyên bố mọi offset pagination **chính xác** \(O(\text{offset})\). Nhưng nói chung **deep offset scan thường không phải đường truy cập tốt cho xuất dữ liệu lớn**.

### Trùng và thiếu khi dữ liệu đổi

```text
Page 1 (limit=3):
  A, B, C

Another user inserts X before A:
  X, A, B, C, D, ...

Page 2 (skip=3):
  C, D, E
```

Record C bị trả hai lần vì vị trí bị dịch. Nếu một record trước trang bị xóa, một record khác có thể bị bỏ.

### Khi offset vẫn phù hợp

- Tập dữ liệu nhỏ, ít thay đổi.
- UX yêu cầu page numbers/nhảy trang, với giới hạn độ sâu.
- Query plan và index thực sự đáp ứng SLO.
- Chấp nhận duplicate/missing ở các requests riêng lẻ.

Đặt `maxPage` hoặc `maxOffset`, đồng thời cung cấp keyset/token cho tải lớn.

## 8. Keyset pagination: sort key phải có tie-breaker

Giả sử sort:

```text
createdAt DESC
```

Hai records có thể cùng thời gian tạo:

```text
ORDER-1 createdAt=10:00:00.000
ORDER-2 createdAt=10:00:00.000
```

Nếu next-page filter chỉ là `createdAt < lastCreatedAt`, một record có cùng timestamp nhưng chưa nằm ở trang trước có thể bị **bỏ**.

Hãy sort bằng một tuple **tạo thứ tự toàn phần trong query scope**:

```text
createdAt DESC, _id DESC
```

Với anchor của item cuối trang trước `(t_last,id_last)`, trang kế tiếp thỏa:

\[
createdAt<t_{last}
\quad\lor\quad
(createdAt=t_{last}\ \land\ id<id_{last})
\]

Và vẫn sort `createdAt DESC, _id DESC`.

### Điều kiện bắt buộc

- `_id` unique trong tập đang duyệt.
- Kiểu so sánh giữa createdAt/id nhất quán với collation và DB index.
- Sort tuple được mã hóa vào continuation token.
- Index phù hợp để tránh full scan.
- Nếu sort theo score hoặc thuộc tính mutable, cần policy riêng.

### Mixed-direction sort

Nếu sort `score DESC, name ASC, id ASC` thì phép so sánh tuple không còn là “tất cả nhỏ hơn”. Phải dựng predicate theo **từng direction** và tie-breaker phù hợp. Đừng copy predicate DESC/DESC cho mọi sort.

## 9. Keyset không tự biến nhiều requests thành một snapshot

Một người duyệt báo cáo đơn hàng trong 5 phút; các record có thể được update/delete giữa các lần fetch:

```text
Page 1: O1 v3, O2 v1, O3 v7
Writer changes O5's sort field between pages.
Page 2: ...
```

Nếu sort field của O5 thay đổi từ trước cursor sang sau cursor, O5 có thể xuất hiện hai lần hoặc không xuất hiện tùy lịch. Keyset chỉ loại một số bất ổn do **dịch vị trí offset**; nó **không đóng băng dữ liệu**.

### Ba hợp đồng nhất quán

| Hợp đồng | Mô tả | Phù hợp |
|---|---|---|
| Live feed/eventual traversal | Các trang phản ánh state gần hiện tại; có thể thiếu/trùng khi thay đổi | Danh sách UI/live timeline |
| Snapshot-consistent traversal | Mọi trang đọc cùng mốc snapshot/version | Báo cáo, export, audit khi được hỗ trợ |
| Monotonic change feed | Đi theo source change token/offset chứ không quét query như bảng tĩnh | CDC, đồng bộ incremental |

### Cách giữ snapshot phụ thuộc hệ

Một số engine có read snapshot/transaction, point-in-time (PIT), as-of timestamp hoặc cursor semantics, nhưng thời hạn và chi phí tài nguyên khác nhau. Không dùng “keyset” làm từ đồng nghĩa với snapshot isolation.

### Khi yêu cầu **exactly once coverage** của dataset

Để xuất một tập nhất quán đúng một lần, cần định nghĩa:

- Dữ liệu tại **thời điểm nào**?
- Delete/update trong lúc export có được phản ánh không?
- Resume sau crash có dùng cùng snapshot được không?
- Có dedup/unique ID, immutable anchor hoặc revision barrier không?

Nếu nguồn không hỗ trợ snapshot phù hợp, có thể cần job materialization riêng hoặc thiết kế dữ liệu bất biến theo phiên bản.

## 10. API page token: phải ràng buộc scope và query

Một continuation token không chỉ là offset được Base64:

```json
{
  "tokenVersion": 2,
  "tenantId": "T01",
  "resource": "orders",
  "filterHash": "canonical-filter-digest",
  "sort": "createdAt_desc_id_desc",
  "pageSize": 50,
  "lastCreatedAt": "2026-11-14T09:00:00Z",
  "lastId": "O1001",
  "issuedAt": "2026-11-14T09:00:10Z",
  "expiresAt": "2026-11-14T09:10:10Z"
}
```

Đây là cấu trúc **minh họa nội dung logic**, không có nghĩa API phải phơi nguyên JSON. Nếu token chứa state phía client, nên ký/HMAC hoặc mã hóa và xác thực theo threat model, giới hạn kích thước, và từ chối token sửa đổi.

### Scope ràng buộc với quyền

Khi request next page:

1. Xác thực user và tenant hiện hành.
2. Kiểm tra token signature/expiry/version.
3. So token tenant/resource/filter/sort/page-size với request được phép.
4. Thực hiện authorization **lần nữa** theo yêu cầu nghiệp vụ.
5. Chạy query trong scope hợp lệ.

**Không xem token là giấy phép vượt quyền.** Nếu user bị thu hồi quyền sau page 1, page 2 phải tuân policy mới.

### Opaque token của SDK

Nếu driver trả paging token opaque, bạn có thể đóng gói nó trong token API đã ký và gắn scope metadata. **Không tự parse hoặc chỉnh bytes của token SDK**; các tokens có thể thay đổi theo version, query shape và thời hạn.

### Token hết hạn

Trả lỗi có mã rõ (ví dụ yêu cầu bắt đầu lại pagination) thay vì âm thầm reset về page 1 hay trả kết quả từ query khác. Nếu cursor/PIT đã hết hạn, client phải có UX để bắt đầu phiên duyệt mới.

## 11. Projection: giảm số bytes trước khi tăng batch size

Một document order có:

```json
{
  "_id": "O1",
  "tenantId": "T01",
  "status": "PAID",
  "createdAt": "2026-11-14T09:00:00Z",
  "items": ["... 500 nested items ..."],
  "auditTrail": ["... thousands of entries ..."],
  "metadata": {"...": "..."}
}
```

UI danh sách chỉ cần:

```json
{
  "_id": "O1",
  "status": "PAID",
  "createdAt": "2026-11-14T09:00:00Z"
}
```

Đặt projection trên query giúp giảm:

- Bytes qua network.
- Deserialization CPU.
- Heap allocation và GC.
- Chi phí đọc full document khi index có thể cover.
- Time-to-first-result.

### Thứ tự tối ưu

Thường nên:

1. Chọn đúng access pattern/index/filter.
2. Chỉ đọc các fields thực sự cần.
3. Đặt page/batch size phù hợp.
4. Đo RTT và throughput, rồi tinh chỉnh concurrency.

Tăng batch từ 100 lên 1.000 khi mỗi document chứa 1 MiB dữ liệu thừa **không phải tối ưu hiệu quả**.

## 12. Index và sort là điều kiện hiệu năng của phân trang

Một query:

```text
tenantId = T01
status = PAID
ORDER BY createdAt DESC, _id DESC
LIMIT 50
```

cần đường truy cập có thể lọc và trả thứ tự hiệu quả, ví dụ một compound index phù hợp:

```text
(tenantId, status, createdAt DESC, _id DESC)
```

Không có index/access path phù hợp, database có thể:

- Full-scan nhiều partitions.
- Gather/sort kết quả lớn.
- Dùng nhiều memory hoặc spill disk.
- Query nhiều shards và merge.
- Đọc nhiều rows rồi mới trả 50.

### Thiết kế index phụ thuộc engine và workload

MongoDB B-tree index, DynamoDB partition/sort key và GSI, Cassandra partition/clustering keys, Elasticsearch inverted index/doc values, graph traversals có cơ chế khác nhau. Không copy một câu SQL `ORDER BY` rồi mặc định mọi NoSQL làm tốt.

### Kiểm tra explain

Đo keys examined/docs examined, sort stage, bytes/rows scanned, index usage và thời gian từng bước theo công cụ của engine. Số results trả về **không phải** số records server đã phải đọc.

## 13. Tách page size của client và fetch size của driver

Giả sử frontend yêu cầu 25 orders:

```text
HTTP page size = 25
Driver batch size = 200
```

Một service chỉ cần hiển thị 25 orders có thể không nên fetch đủ 200 nếu không tận dụng prefetch/cursor. Trong khi một export job có thể fetch 500 từ DB, transform thành các lô 50 để ghi object storage, và không phải expose 500 records cùng lúc.

### Vì sao cần tách?

- **API size:** ảnh hưởng UX, response bytes, quota client.
- **Driver batch:** ảnh hưởng DB round trips, driver buffering.
- **Processing chunk:** ảnh hưởng CPU/memory/transaction boundary.
- **Output chunk:** ảnh hưởng downstream API/storage write limits.

Thiết kế theo pipeline:

```text
NoSQL cursor fetch 500 docs/batch
   |
   v
Process 50 docs/chunk
   |
   v
Write 5 MiB compressed part / export chunk
   |
   v
Return job status rather than huge HTTP response
```

Không đẩy thẳng driver fetch size vào query param HTTP không giới hạn; user có thể dùng nó để gây memory pressure hoặc scan cực sâu.

## 14. Đếm tổng số trang không miễn phí

UI thường yêu cầu:

```json
{
  "items": ["..."],
  "page": 10,
  "pageSize": 25,
  "totalCount": 1234567,
  "totalPages": 49383
}
```

Để trả `totalCount` chính xác, server có thể cần **một query count riêng**, scan index, aggregate hoặc đọc một counter duy trì trước. Các queries count có consistency semantics và execution cost khác query page.

### Hai race

Page query và count query chạy ở hai thời điểm:

```text
T1: count = 1,000
T2: someone inserts 3 records
T3: page query sees 1,003
```

Không nên mặc định totalCount và page items thuộc cùng snapshot.

### Các lựa chọn API

- Trả `hasMore` hoặc `nextPageToken`, không bắt buộc có totalCount.
- Trả estimate có nhãn rõ khi thích hợp.
- Cache/aggregate count với mô tả staleness.
- Chỉ tính exact count theo yêu cầu cho dataset nhỏ/đường query được tối ưu.

### Không tự biến estimate thành chính xác

Một thống kê collection/table lớn có thể là approximate hoặc bao gồm nhiều tenants; không dùng làm tổng exact cho filter tenant cụ thể khi business đòi chính xác.

## 15. Một ví dụ chi phí offset sâu và keyset

Giả sử mỗi tenant có 2 triệu orders, page size 50.

**Offset page 20.000**:

```text
skip = (20000 - 1) * 50 = 999950
limit = 50
```

Truy vấn có thể phải bỏ qua gần một triệu index entries theo plan.

**Keyset page kế tiếp**:

```text
after = (lastCreatedAt, lastId)
limit = 50
```

Query seek vào vùng index tương ứng rồi lấy khoảng 50 entries, tùy filter selectivity và index layout. Số item cần **traverse** có thể giảm mạnh.

### Đánh đổi thực tế

| Thuộc tính | Offset/limit | Keyset/seek |
|---|---|---|
| Dễ trả page numbers | Có | Khó |
| Jump trực tiếp trang 100 | Có, nhưng có thể đắt | Không trực tiếp |
| Deep pagination performance | Dễ xuống cấp | Thường ổn định khi index hỗ trợ |
| Sort tie-breaker | Vẫn cần để ổn định | **Bắt buộc** |
| Insert trước trang | Dễ trùng/thiếu | Tránh một số loại dịch offset |
| Update/delete của sort keys | Vẫn bất ổn | Vẫn có thể trùng/thiếu |
| Stateless token | Không cần token | Thường cần anchor token |
| Snapshot consistency | Không tự có | Không tự có |

Nếu mục tiêu là **export toàn bộ dữ liệu lớn**, keyset hoặc cursor thường được cân nhắc trước deep offset, nhưng phải xét source consistency và khả năng resume.

## 16. MongoDB: `skip/limit`, keyset và cursor `batchSize`

MongoDB Java Sync Driver hỗ trợ:

- `skip(n)` và `limit(n)` cho offset pagination.
- `sort(...)` để xác định thứ tự.
- `projection(...)` để giảm các trường cần đọc.
- `batchSize(n)` để đặt batch size cursor, với giới hạn thực tế do server/protocol quyết định.
- `MongoCursor` để duyệt kết quả và đóng tài nguyên.

### Offset pagination minh họa

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

int page = 3;
int pageSize = 25;
int skip = Math.multiplyExact(page - 1, pageSize);

var iterable = orders.find(
        Filters.eq("tenantId", verifiedTenantId)
    )
    .sort(Sorts.orderBy(
        Sorts.descending("createdAt"),
        Sorts.descending("_id")))
    .skip(skip)
    .limit(pageSize);
```

**Đây là ví dụ với page nhỏ.** Với page lớn, phải kiểm soát overflow `skip`, max offset và chi phí scan. `verifiedTenantId` phải đến từ authentication/authorization, không phải chuỗi query tùy ý được tin ngay.

### Keyset pagination cho sort giảm dần

Giả sử `createdAt` lưu kiểu BSON Date và `_id` là ObjectId. Anchor phải dùng đúng **BSON types** và collation/index:

```java
import java.util.Date;
import org.bson.types.ObjectId;
import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Sorts.*;
import static com.mongodb.client.model.Projections.*;

Date lastCreatedAt = /* last page's timestamp */;
ObjectId lastId = /* last page's ObjectId */;

var query = and(
    eq("tenantId", verifiedTenantId),
    eq("status", "PAID"),
    or(
        lt("createdAt", lastCreatedAt),
        and(
            eq("createdAt", lastCreatedAt),
            lt("_id", lastId)
        )
    )
);

var results = orders.find(query)
    .sort(orderBy(
        descending("createdAt"),
        descending("_id")
    ))
    .projection(include(
        "_id", "createdAt", "status", "totalMinorUnits"
    ))
    .limit(51)         // 50 items + one look-ahead
    .batchSize(100);
```

Đây là **trích đoạn**, các biến `orders` và cursor anchor được inject/tạo ở code gọi. Trang đầu bỏ seek predicate và chỉ dùng tenant/status filters. Việc sort BSON Date/ObjectId phải phù hợp với ID thực tế.

### Lấy `limit + 1` để tính `hasMore`

Với API page size 50:

1. Query tối đa 51 results.
2. Trả 50 results đầu.
3. Nếu có result 51, đặt `hasMore=true`.
4. Token trang kế tiếp lấy **sort tuple của item thứ 50**, không phải item 51 đã look-ahead.

Vì item 51 chưa được trả, nó phải còn nằm trong tập next page. Nếu anchor là item 51, bạn sẽ **bỏ qua một phần tử**.

### Cursor streaming và đóng tài nguyên

```java
import com.mongodb.client.MongoCursor;
import org.bson.Document;

try (MongoCursor<Document> cursor = results.iterator()) {
    while (cursor.hasNext()) {
        Document item = cursor.next();
        process(item);
    }
}
```

Với export job, `batchSize` có thể giúp giảm `getMore` calls. Nhưng **batchSize không làm mọi response luôn chứa đúng n documents**: server áp giới hạn bytes, cursor state, initial batch và các điều kiện khác.

### Index gợi ý

Với filter tenant + status, sort createdAt/_id:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
```

Index thực tế còn phụ thuộc query shape, cardinality, write cost và explain. Không tạo index chỉ vì ví dụ nếu workload không dùng nó.

### Cursor không mặc định snapshot nhất quán

Một cursor thông thường có thể quan sát thay đổi theo semantics của read concern, query và topology. Nếu cần xuất dataset tại một thời điểm duy nhất, phải xem snapshot/transaction/read concern support của MongoDB và giới hạn thời gian/tài nguyên, thay vì mặc định cursor = frozen snapshot.

## 17. MongoDB: tránh giữ toàn bộ kết quả trong heap

### Cách dễ gây áp lực bộ nhớ

```java
List<Document> all = orders.find(
    Filters.eq("tenantId", tenantId)
).into(new ArrayList<>());
```

Với hàng triệu documents, cách này có thể tạo `OutOfMemoryError` hoặc GC stalls.

### Cách xử lý tuần tự

```java
try (var cursor = orders.find(
        Filters.eq("tenantId", tenantId)
    )
    .sort(Sorts.ascending("_id"))
    .batchSize(500)
    .iterator()) {

    while (cursor.hasNext()) {
        var doc = cursor.next();
        writeToExport(doc);
    }
}
```

`writeToExport` phải có **bounded output buffering** và chiến lược xử lý khi downstream chậm. Nếu hàm này đẩy vô hạn vào một queue, chỉ việc dùng MongoCursor chưa bảo vệ heap.

### Export có thể resume thế nào?

Server cursor ID có thể không còn khi process crash. Với resume bền, cần checkpoint bằng sort tuple hoặc source-specific snapshot token:

```json
{
  "jobId": "EXP-2026-101",
  "tenantId": "T01",
  "lastCommittedId": "O00012345",
  "exportPart": 72,
  "querySchema": 3
}
```

Chỉ cập nhật checkpoint khi output chunk đã được ghi bền theo hợp đồng. Nếu chunk ghi thành công nhưng checkpoint lỗi, lần sau có thể ghi lại: cần **idempotent part naming/generation** hoặc reconcile. Checkpoint theo ID cũng cần invariant thứ tự và dataset consistency.

## 18. DynamoDB: `LastEvaluatedKey` mới là chìa khóa trang tiếp

DynamoDB `Query` và `Scan` có giới hạn response và dùng **`LastEvaluatedKey`** cho paging. Với các API thông dụng, một Query/Scan đọc tối đa khoảng **1 MB dữ liệu cho một đợt** trước khi áp dụng một số bước filter/projection, tùy điều kiện và API.

### Ví dụ Java AWS SDK v2

```java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.QueryRequest;
import software.amazon.awssdk.services.dynamodb.model.QueryResponse;

public final class OrderReader {
    private final DynamoDbClient db;

    public OrderReader(DynamoDbClient db) {
        this.db = db;
    }

    public QueryResponse onePage(
        String verifiedTenantId,
        Map<String, AttributeValue> startKey
    ) {
        QueryRequest request = QueryRequest.builder()
            .tableName("Orders")
            .keyConditionExpression("tenantId = :tenant")
            .expressionAttributeValues(Map.of(
                ":tenant",
                AttributeValue.builder()
                    .s(verifiedTenantId)
                    .build()
            ))
            .exclusiveStartKey(startKey)
            .limit(50)
            .build();

        return db.query(request);
    }
}
```

Thực tế table/index key schema phải hỗ trợ query tenant, sort key và ordering mong muốn. `startKey` của trang đầu là map rỗng/không truyền theo SDK/API phù hợp; các trang sau dùng **nguyên map `LastEvaluatedKey`** mà response trả về, không tự đoán partition/sort key còn thiếu.

### Ý nghĩa của `Limit`

Khi Query có `FilterExpression`, `Limit` có thể giới hạn **số items được đánh giá trước filter**, không bảo đảm trả đúng 50 items sau filter.

Ví dụ:

```text
Evaluate 50 items
FilterExpression keeps only 3
Returned Items = 3
LastEvaluatedKey may still be present
```

Một response có **0 items** vẫn có thể có continuation key. Nếu code coi `items.isEmpty()` là “hết dữ liệu”, nó có thể bỏ các trang sau.

### Điều kiện dừng

Tiếp tục theo `LastEvaluatedKey` cho đến khi nó rỗng/không có theo API. Tuy nhiên token xuất hiện **không cam kết** sẽ còn kết quả thỏa filter ở trang tiếp.

### Đừng nhầm `ScannedCount` và `Count`

Trong DynamoDB response, số items được đánh giá và số items được trả có thể khác do filter. Query keys/index hiệu quả thường tốt hơn quét rồi dùng FilterExpression để bỏ phần lớn dữ liệu.

### Về consistency

DynamoDB base table/LSI có read consistency options khác GSI. GSI reads có semantics eventual theo API hiện hành. Một token paging không tự biến nhiều lần Query thành snapshot nhất quán.

## 19. Cassandra: partition key, clustering order và paging state

Với Cassandra, truy vấn tốt thường được thiết kế từ **partition key + clustering columns** thay vì cho phép phân trang một filter tùy ý trên toàn cụm.

Một bảng minh họa:

```sql
CREATE TABLE orders_by_tenant (
    tenant_id text,
    bucket_day date,
    created_at timestamp,
    order_id text,
    status text,
    total_minor_units bigint,
    PRIMARY KEY (
        (tenant_id, bucket_day),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id DESC
);
```

Query theo `tenant_id` và `bucket_day` để có một partition được kiểm soát; một tenant lớn cần bucket design phù hợp để tránh **partition quá lớn/hotspot**.

### Driver paging

Java Driver 4.x cho phép đặt page size trên statement:

```java
import com.datastax.oss.driver.api.core.CqlSession;

var prepared = session.prepare(
    "SELECT order_id, created_at, status " +
    "FROM orders_by_tenant " +
    "WHERE tenant_id = ? AND bucket_day = ?"
);

var bound = prepared.bind(tenantId, bucketDay)
    .setPageSize(200);

var resultSet = session.execute(bound);
for (var row : resultSet) {
    consume(row);
}
```

Trong sync API, driver có thể tự động fetch trang tiếp khi iterator tiến; đừng đo network trips bằng số lần gọi `execute` một cách mù quáng.

### Paging state

Driver có paging state để tiếp tục đọc trong các API phù hợp. Paging state phải gắn với **cùng query và bound values**, loại dữ liệu/statement và driver contract. Không tự chế `offset=page*200` rồi gắn vào Cassandra query.

Với external API, hãy kiểm tra điều kiện **safe paging state**, version/encoding, TTL và việc token có được phép lộ cho caller không. Token không thay tenant authorization.

### Giới hạn quan trọng

- `LIMIT` và `pageSize` không đồng nghĩa.
- Paging không làm toàn bộ query nhất quán như snapshot nếu dữ liệu thay đổi.
- Tombstone-heavy partitions có thể khiến server scan nhiều dữ liệu để trả ít rows.
- Query nhiều partitions/`ALLOW FILTERING` có thể rất tốn kém dù page size nhỏ.
- Partition key distribution ảnh hưởng throughput nhiều hơn chỉ tăng page size.

## 20. Redis: `SCAN` là iterator, không phải phân trang danh sách ổn định

`SCAN` có thể dùng để duyệt keyspace theo cursor:

```redis
SCAN 0 MATCH app:orders:* COUNT 100
```

Response trả:

```text
next cursor: "456"
keys: ["app:orders:1", "app:orders:8", ...]
```

Tiếp tục:

```redis
SCAN 456 MATCH app:orders:* COUNT 100
```

cho đến khi cursor trả về `0` theo giao thức.

### `COUNT` là gợi ý, không phải size page chính xác

Một lần `SCAN` có thể trả ít, nhiều hoặc không có key, dù cursor chưa kết thúc. Không dừng khi danh sách keys trống; dừng theo **cursor**.

### Có thể gặp duplicates

Redis `SCAN` không tạo một snapshot bất biến của keyspace. Trong quá trình duyệt có thể thấy keys trùng hoặc biến động do write/delete, nên client cần chấp nhận/reconcile duplicates theo yêu cầu.

### `SCAN` không thích hợp để làm UI page numbers

Không thể trực tiếp nói “mở trang 250” ổn định của toàn keyspace bằng cursor SCAN. Nó phù hợp hơn với **maintenance jobs, incremental iteration và controlled background scans**, không phải API “50 sản phẩm được sort chính xác”.

### Redis sorted set cho ordered result

Nếu dữ liệu đã được model trong sorted set theo score:

```redis
ZRANGE leaderboard 0 49 REV WITHSCORES
```

có thể đọc một đoạn theo rank. Nhưng khi thứ hạng thay đổi, các trang dựa trên rank vẫn có thể trùng/thiếu. Seek theo score/member cần đánh giá tie-breakers và khả năng dùng API score range tương ứng.

### Redis Cluster

Keyspace ở nhiều nodes; `SCAN` phải chạy trên các nodes/cluster API phù hợp. Một cursor từ node không phải continuation token toàn cluster. Đừng đo số round trips bằng số kết quả từ một node rồi suy cho cả cụm.

## 21. Elasticsearch/OpenSearch: `search_after` và PIT

Search engine có `from + size` giống offset pagination:

```json
{
  "from": 1000,
  "size": 20,
  "sort": [
    {"createdAt": "desc"},
    {"orderId": "desc"}
  ]
}
```

Tại deep pages, các shards có thể phải giữ/sắp xếp nhiều hits để tìm trang mong muốn. Elasticsearch thường có giới hạn mặc định **result window 10.000 hits** cho cách dùng `from + size` thông thường, có thể cấu hình nhưng tăng giới hạn không phải cách tối ưu deep pagination.

### `search_after`

Lấy `sort` values của hit cuối trang trước:

```json
{
  "size": 20,
  "sort": [
    {"createdAt": "desc"},
    {"orderId": "desc"}
  ],
  "search_after": [
    "2026-11-14T10:00:00Z",
    "ORDER-1001"
  ]
}
```

Các sort values phải cùng loại, cùng thứ tự fields/directions và phù hợp mappings. `orderId` nên là field sortable duy nhất/tie-breaker hoặc dùng cơ chế PIT tie-breaker được engine hỗ trợ; không mặc định một analyzed text field sort được.

### Point in Time (PIT)

Với deep traversal khi index liên tục update, PIT có thể giúp giữ **khung nhìn tìm kiếm tương đối ổn định** trong thời hạn cấu hình; thường kết hợp `search_after` và sort tie-breaker phù hợp như `_shard_doc` trong các API PIT được hỗ trợ.

PIT có chi phí tài nguyên và thời hạn; khi hết hạn, token không còn bảo đảm tiếp tục cùng snapshot. Không xem PIT ID là session vĩnh viễn.

### Scroll và export

Các API scroll/scan hoặc point-in-time có thể phù hợp export/batch jobs tùy engine/version, nhưng phải đóng/expire resources và không coi một search result cursor như transaction ACID. Với thay đổi index/mapping, token cần được xử lý theo contract.

## 22. Neo4j: `SKIP/LIMIT` và seek theo thuộc tính

Một query:

```cypher
MATCH (o:Order {tenantId: $tenantId})
RETURN o.orderId AS id, o.createdAt AS createdAt
ORDER BY o.createdAt DESC, o.orderId DESC
SKIP $skip
LIMIT $pageSize
```

giống offset pagination: trang sâu có thể tốn công tìm/skipping rows.

Seek:

```cypher
MATCH (o:Order {tenantId: $tenantId})
WHERE o.createdAt < $lastCreatedAt
   OR (o.createdAt = $lastCreatedAt
       AND o.orderId < $lastOrderId)
RETURN o.orderId AS id, o.createdAt AS createdAt
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $pageSize
```

Đây là minh họa predicate; **trang đầu** không có anchor cần query khác/điều kiện tùy chọn. Dữ liệu kiểu datetime và collation/order phải đồng nhất với sort. Index/constraints nên phù hợp filter và ordering.

### Khi nào không chỉ phân trang nodes?

Một traversal nhiều hops có số paths/results tăng nhanh. Giới hạn 20 kết quả trả ra không có nghĩa engine chỉ duyệt 20 paths trước đó. Cần kiểm tra query plan, lựa chọn starting nodes, giới hạn depth/branching, index và projections. Tránh lấy `SKIP/LIMIT` thay cho tối ưu graph query.

## 23. Bulk read: một query nhiều IDs có thể giảm RTT

Một API cần lấy 100 sản phẩm theo IDs:

**N+1 queries:**

```text
100 x GET product by id
```

**Batch lookup:**

```text
GET products by 100 IDs
```

Với MongoDB:

```javascript
db.products.find({
  tenantId: "T01",
  _id: { $in: ["SKU1", "SKU2", "SKU3"] }
})
```

Đây là cách gom lookup khi có index phù hợp và batch size trong giới hạn. Nhưng:

- `$in` với hàng trăm nghìn IDs có thể tạo query/response lớn, memory pressure hoặc plan xấu.
- Không được bỏ tenant filter khi các IDs không unique toàn hệ.
- Kết quả query theo danh sách IDs **không nhất thiết trả cùng thứ tự input**.
- Missing IDs cần mapping rõ, không tự coi index của response là index input.
- Một lookup nhiều IDs có thể bị ràng buộc bởi sharding, read capacity hoặc response size.

### DynamoDB BatchGetItem

Một ví dụ hệ có API chuyên cho multi-key reads: `BatchGetItem` có giới hạn số keys/response bytes theo API và có thể trả `UnprocessedKeys`. Không suy một call luôn trả mọi item đã yêu cầu; phải retry unprocessed keys với backoff theo contract và chỉ tiêu thụ những items nhận được.

### Cần xét fan-out

Gom 100 IDs trải trên 100 shards vẫn tạo công việc nội bộ. Giảm network trips ở Java không có nghĩa server làm ít việc hơn tương ứng.

## 24. Bulk write: giảm overhead nhưng không mặc định là transaction

Một ingest worker cập nhật 5.000 documents. Thay vì 5.000 requests nối tiếp, có thể gom nhiều operations trong bulk API:

```text
5,000 events
   |
   v
chunks of 250
   |
   v
20 bulk write requests
```

### Ưu điểm

- Giảm per-request overhead.
- Giảm round trips giữa client và DB.
- Driver/engine có thể tối ưu scheduling.
- Cho phép kiểm soát retry theo chunks.

### Nhược điểm

- Một batch lớn có thể bị timeout, throttle, vượt limit bytes/operations.
- Partial success khó xử lý hơn một record.
- Một document/item hotspot vẫn là bottleneck.
- Một batch có thể chứa writes tới nhiều partitions với chi phí routing cao.
- Retry cả batch không có idempotency có thể tạo **duplicate side effects**.

**Bulk write không tương đương transaction atomic trên tất cả items.** Phải xem hợp đồng engine và response per-operation.

## 25. MongoDB BulkWrite: ordered/unordered và partial failures

Java Sync Driver hỗ trợ `bulkWrite` với các `WriteModel`:

```java
import java.util.ArrayList;
import java.util.List;
import com.mongodb.client.model.BulkWriteOptions;
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.WriteModel;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

List<WriteModel<Document>> writes = new ArrayList<>();

for (var change : changes) {
    writes.add(new UpdateOneModel<Document>(
        Filters.and(
            Filters.eq("tenantId", change.tenantId()),
            Filters.eq("_id", change.orderId())
        ),
        Updates.set("state", change.state())
    ));
}

orders.bulkWrite(
    writes,
    new BulkWriteOptions().ordered(false)
);
```

Đây là ví dụ minh họa; `changes` là collection ứng dụng cung cấp. **Không** tạo bulk cực lớn không giới hạn chỉ để gọi một lần.

### Ordered

Trong ordered bulk, khi một operation lỗi, driver/engine có thể ngừng những operations phía sau theo semantics của bulk API. Không có nghĩa toàn batch rollback.

### Unordered

Unordered bulk có thể cho phép engine thực thi/tiếp tục operations độc lập hơn và báo các errors theo item. Không có bảo đảm thứ tự nghiệp vụ như một transaction.

### Rủi ro với cùng document

Nếu batch chứa:

```text
Order O1 -> PAID
Order O1 -> CANCELED
```

và ordered(false), không được giả định state cuối luôn là CANCELED nếu hai updates không có version predicate. Cần source revision, CAS hoặc nhóm/serialize per entity.

### Retry sau timeout

`$set` cùng giá trị thường dễ retry hơn `$inc`/`$push`, nhưng vẫn có thể xóa một update mới nếu đến muộn. Đối với ingest CDC cần sourceRevision guard hoặc inbox idempotency và kết quả bulk per item.

## 26. DynamoDB BatchWriteItem: giới hạn và `UnprocessedItems`

DynamoDB `BatchWriteItem` có các ràng buộc API, tiêu biểu:

- Tối đa **25 put/delete requests** trong một batch.
- Giới hạn request size **16 MB**.
- Item size và validation theo DynamoDB API, thường tối đa **400 KB/item**.
- Hỗ trợ Put/Delete trong BatchWriteItem, **không hỗ trợ UpdateItem hay condition expression trong batch đó**.
- Không có atomicity cho toàn bộ batch.
- Có thể trả `UnprocessedItems` khi capacity/throttle.

### Luồng xử lý

```text
Chunk up to 25 put/delete requests
      |
      v
BatchWriteItem
      |
      +-- processed items
      |
      +-- UnprocessedItems
                |
                v
       backoff with jitter
                |
                v
       retry only unprocessed items
```

Không coi HTTP 200 với `UnprocessedItems` khác rỗng là “toàn batch đã xong”.

### Idempotency

Put cùng key/payload có thể an toàn trong trường hợp thích hợp, nhưng Put không điều kiện có thể ghi đè version mới. Nếu cần exactly-once business semantics, dùng `TransactWriteItems`/conditional operations/ledger theo API và invariant, thay vì hy vọng BatchWriteItem tự cung cấp.

### BatchGetItem

Read counterpart có thể trả `UnprocessedKeys` và items không theo thứ tự yêu cầu; handler phải map theo key và retry có backoff. API có giới hạn keys/bytes; xem tài liệu phiên bản đang dùng.

## 27. Cassandra: CQL `BATCH` không phải công cụ bulk-loading chung

Cassandra có cú pháp `BEGIN BATCH ... APPLY BATCH`, nhưng **batch mutations** có semantics riêng:

```sql
BEGIN BATCH
  UPDATE orders_by_tenant
    SET status = 'PAID'
    WHERE tenant_id = 'T01'
      AND bucket_day = '2026-11-14'
      AND created_at = '2026-11-14T10:00:00Z'
      AND order_id = 'O1';
  UPDATE orders_by_tenant
    SET status = 'PAID'
    WHERE tenant_id = 'T01'
      AND bucket_day = '2026-11-14'
      AND created_at = '2026-11-14T10:01:00Z'
      AND order_id = 'O2';
APPLY BATCH;
```

Đây là cú pháp minh họa; kiểu literal date/timestamp cần đúng phiên bản CQL và schema.

### Vì sao không gom 10.000 partitions vào một CQL BATCH?

- Coordinator phải tổ chức writes tới nhiều partitions.
- Logged batch có batch log/overhead.
- Batch lớn có thể gây áp lực CPU/memory/network và timeouts.
- Không đem lại **transaction isolation** kiểu RDBMS cho nhiều rows.
- Có thể kém hiệu quả hơn **bounded concurrent prepared statements** được route theo partition keys.

Batch trong Cassandra có mục đích về semantics/atomicity của mutations theo CQL contract, không phải “mỗi BATCH càng nhiều records thì càng nhanh”.

### Cách đo thay thế

Khi ingest nhiều partitions độc lập:

1. Prepare statements.
2. Dùng async executions với concurrency limit.
3. Phân bố partition keys tránh hotspots.
4. Đo coordinator load, p99, timeouts, tombstone/memtable pressure.
5. Retry theo idempotency/consistency contract.

Chọn `BATCH` khi các mutations có quan hệ nghiệp vụ đòi semantics cụ thể mà Cassandra hỗ trợ, **không phải chỉ để giảm số lời gọi Java**.

## 28. Redis pipelining: giảm network latency, không tự atomic

Không pipeline:

```text
SET k1 v1 -> wait reply
SET k2 v2 -> wait reply
SET k3 v3 -> wait reply
```

Pipeline:

```text
SET k1 v1
SET k2 v2
SET k3 v3
send/flush together
receive replies
```

Pipelining giúp tránh phải chờ RTT cho từng command tuần tự. Nó **không đồng nghĩa**:

- Tất cả commands được thực thi atomically như một transaction.
- Một lỗi command làm các commands đã chạy tự rollback.
- Commands qua cluster nodes khác nhau thành một cross-slot transaction.
- Network timeout cho biết commands nào chưa được server áp dụng.

### Một ví dụ số

Giả sử 100 commands, RTT=5 ms:

```text
Sequential request/reply:
  ~100 * 5ms = 500ms RTT component.

Pipeline in one feasible flush:
  RTT component may approach a few RTTs,
  but response transfer/processing and buffers still cost.
```

Không suy pipeline đúng **1 network packet**, đặc biệt với Redis Cluster, large payloads, TLS framing và socket buffer. Lệnh nhiều hoặc pipeline quá lớn có thể tăng server/client reply memory.

### `MULTI/EXEC` là khái niệm khác

Redis transaction qua `MULTI/EXEC` có semantics atomic execution tại server trong phạm vi hợp lệ, nhưng không cung cấp rollback kiểu mọi database transaction cho mọi lỗi runtime; trên Redis Cluster có yêu cầu slot. Đừng dùng `pipeline()` để thay thế `MULTI/EXEC` khi business cần atomic operation.

### Redis Java Lettuce/Jedis

Lettuce có async command APIs và flush/pipelining controls; Jedis cũng có pipeline APIs. Cần tuân thủ thread-safety và **connection-local state**, đặc biệt khi dùng transaction, blocking commands, pub/sub. Dùng batch size và max in-flight phù hợp, không giữ hàng trăm nghìn replies trong RAM.

## 29. Batch size lớn hơn có thể **chậm** hơn

Đồ thị khái niệm:

```text
Latency/record
 ^
 | \
 |  \
 |   \___
 |       \__
 |          \___
 |              /\
 |             /  \____  (queueing, memory, retry, GC)
 +----------------------------------------------> Batch size
    tiny      medium                huge
```

Lô nhỏ bị fixed overhead/RTT. Lô vừa thường tận dụng tốt network và server. Lô rất lớn có thể:

- Vượt request/response byte limit.
- Bị server throttle hoặc bị chia nội bộ.
- Tăng p99 vì **head-of-line blocking**.
- Làm full-batch retry tốn kém.
- Giữ memory lớn và GC pressure.
- Giảm fairness giữa tenants.
- Tăng thời gian transaction/locks nếu backend giữ.
- Gây latency spikes cho workloads tương tác cùng pool.

Điểm tối ưu thay đổi theo:

- Kích thước record.
- RTT và bandwidth.
- Query selectivity/index.
- Compression ratio.
- Batch processing CPU.
- Cụm/shard topology.
- Concurrency.
- Error rate.

Không có quy tắc “batch=1.000 luôn tốt” đúng cho mọi NoSQL.

## 30. Batch size theo **bytes**, không chỉ theo số records

Nếu mỗi record có kích thước khác nhau:

```text
Order A:      0.5 KiB
Order B:      3.0 KiB
Order C:    800.0 KiB
Order D:      2.5 KiB
```

Batch 100 records có thể là 200 KiB hoặc 70 MiB tùy distribution.

### Hai giới hạn đồng thời

```text
maxItemsPerBatch = 200
maxEstimatedBytesPerBatch = 2 MiB
```

Flush khi chạm một trong hai:

```text
if items.size >= maxItems
    OR estimatedBytes + nextItemBytes > maxBytes:
        flush()
```

Đặt thêm **max wait time** để traffic ít vẫn được flush:

```text
flush when:
    count threshold
 OR byte threshold
 OR max latency threshold
```

### Chú ý row rất lớn

Nếu một item vượt byte cap, không được tạo batch rỗng rồi infinite loop. Phải:

- Reject/quarantine theo giới hạn API.
- Chia payload theo model cho phép.
- Chọn API stream/chunk khác.

### Kích thước wire khác Java object heap

Một 1 MiB JSON payload có thể chiếm nhiều hơn 1 MiB trong Java khi thành Strings, maps, buffers, decoded objects và garbage. Đo cả **serialized bytes, heap allocation và direct buffer usage**.

## 31. Batch writes: “gửi thành công” khác “mọi item đã áp dụng”

Một batch:

```text
Input events: E1 E2 E3 E4 E5
Bulk API:
  E1 = OK
  E2 = OK
  E3 = RETRYABLE (throttle)
  E4 = INVALID_SCHEMA
  E5 = OK
```

Nếu consumer chỉ kiểm tra HTTP status 200 rồi commit checkpoint sau E5, E3 và E4 có thể bị bỏ.

### Điều cần phân biệt

| Kết quả | Xử lý |
|---|---|
| Toàn bộ batch được xác nhận committed | Có thể tiến checkpoint tới completed contiguous prefix |
| Một số items thành công, một số retryable | Retry **đúng failed items** nếu API cho phép |
| Một số items invalid/permanent | Quarantine/DLQ/terminal handling theo contract |
| Timeout/unknown outcome | Không tự khẳng định batch chưa áp dụng gì |
| Duplicate event khi retry | Idempotency key/condition/source revision guard |

### Input offset và batch result

Nếu batch lấy từ một partition Kafka, checkpoint chỉ tiến qua **các offsets liên tục đã xử lý bền**, không dựa vào phần tử cuối của batch được đánh dấu success.

### Retry cả batch khi nào an toàn?

Chỉ khi mỗi operation có thể retry mà không tạo thêm business effect không mong muốn. `SET` một giá trị cố định có thể tương đối dễ retry nhưng có nguy cơ stale overwrite; `INCR`, `$inc`, append và gửi email cần dedup/ledger.

### Failure ở tầng network

Một write batch có thể đã commit một phần nhưng response bị mất. Client không thể suy mọi item fail chỉ từ timeout. Hãy sử dụng transaction/conditional source revisions, idempotency keys hoặc reconcile theo item.

## 32. Giới hạn concurrency: giảm RTT chưa đủ

Một service có thể chạy 100 requests tuần tự:

```text
R1 -> wait -> R2 -> wait -> ... -> R100
```

Hoặc chạy tối đa 10 đồng thời:

```text
R1..R10 -> wait
R11..R20 -> wait
...
```

Concurrency có thể **che RTT** và tăng throughput, nhưng nếu không giới hạn:

```text
100000 concurrent futures
  -> driver queue grows
  -> pool acquire waits
  -> DB CPU / throttling
  -> timeouts -> retries -> more load
```

### Little's Law

Trong điều kiện ổn định:

\[
L \approx \lambda W
\]

với \(L\) là số request đang trong hệ, \(\lambda\) là throughput và \(W\) là thời gian phản hồi trung bình.

Ví dụ mục tiêu 2.000 operations/s, latency trung bình 40 ms:

\[
L\approx2000\times0.040=80
\]

Con số 80 là **concurrency trung bình theo mô hình**, không khẳng định pool phải có 80 sockets; multiplexing, shard distribution, burstiness và p99 có thể thay đổi yêu cầu.

### Bulk và concurrency là hai nút điều chỉnh khác nhau

| Tuning | Giảm điều gì? | Có thể làm tăng điều gì? |
|---|---|---|
| Batch size lớn | Số requests/overhead | Memory, p99, retry cost |
| Concurrency lớn | RTT idle, total wall time | Queueing, throttling, DB load |
| Projection nhỏ | Bytes/record | Có thể cần thêm query nếu bỏ fields cần dùng |
| Compression | Network bytes | CPU, tail latency |
| Connection pool lớn | Pool wait khi đã saturation | Sockets/server pressure |
| Prefetch lớn | Chờ batch tiếp theo | Buffered rows/heap |

Không tinh chỉnh tất cả cùng lúc rồi khó xác định nguyên nhân hiệu năng.

## 33. Backpressure: consumer phải chậm lại khi sink chậm

Pipeline:

```text
NoSQL cursor
    |
    v
fetch batches of 1000
    |
    v
transform queue (unbounded?)
    |
    v
sink bulk writer
```

Nếu fetch 10.000 records/s mà sink ghi chỉ 2.000 records/s:

\[
\Delta Q \approx (10\,000-2\,000)t
\]

Sau 30 giây, queue có thể tăng khoảng 240.000 records nếu không có backpressure hoặc dropping. Với mỗi record 5 KiB, payload thuần đã hơn 1 GiB, chưa kể Java object overhead.

### Cách bảo vệ

1. **Bounded queue** với giới hạn items và bytes.
2. **Max in-flight batches**.
3. **Pause/resume** source consumer hoặc chỉ fetch batch tiếp sau khi xử lý xong.
4. **Semaphore/rate limiter** theo sink/throttling.
5. **Cancel/close cursors** khi job bị dừng.
6. **Persisted checkpoint** để resume thay vì giữ vô hạn trong RAM.
7. **Batch timeout** để hoàn tất lô nhỏ khi traffic ít.

### Không bỏ qua future completions

Nếu gửi async batches rồi tự coi thành công ngay sau dispatch, source checkpoint có thể vượt những batches chưa ghi bền. Release permits và đánh dấu items hoàn tất **chỉ sau khi future báo thành công theo sink contract**.

## 34. Java 17: giới hạn số batch gửi đồng thời

Ví dụ minh họa dùng `CompletableFuture` và `Semaphore`. Ứng dụng thật cần timeout, cancellations, error policy, bounded input queue và metrics.

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Semaphore;

interface AsyncBatchSink<T> {
    // Future must complete after the batch's required durable outcome.
    CompletableFuture<Void> write(List<T> immutableBatch);
}

public final class BoundedBatchDispatcher<T> {
    private final Semaphore permits;
    private final AsyncBatchSink<T> sink;

    public BoundedBatchDispatcher(
        int maxInflight,
        AsyncBatchSink<T> sink
    ) {
        if (maxInflight <= 0) {
            throw new IllegalArgumentException("maxInflight");
        }
        this.permits = new Semaphore(maxInflight);
        this.sink = sink;
    }

    public CompletableFuture<Void> dispatch(List<T> batch)
            throws InterruptedException {
        if (batch.isEmpty()) {
            return CompletableFuture.completedFuture(null);
        }

        // Backpressure to producer thread.
        permits.acquire();
        List<T> copy = List.copyOf(batch);

        try {
            CompletableFuture<Void> result = sink.write(copy);
            return result.whenComplete(
                (value, failure) -> permits.release()
            );
        } catch (RuntimeException ex) {
            permits.release();
            throw ex;
        }
    }
}
```

### Phạm vi ví dụ

- Caller vẫn phải **đợi/tập hợp các futures** và không checkpoint vượt batches chưa hoàn tất.
- Khi code gọi `sink.write` trả một future đã failed hoặc future canceled, `whenComplete` release permit.
- Nếu `sink.write` không bao giờ complete, permit bị giữ — cần timeout và một protocol rõ cho unknown outcome.
- Không lấy `List.copyOf` làm deep-copy: nếu phần tử bên trong mutable, việc chia sẻ giữa threads vẫn có thể race.
- Với Java task cancellation, không suy hủy future đã rollback write ở database.
- Semaphore giới hạn **số batch**, không giới hạn tổng bytes; nên thêm byte-weighted limit khi batch sizes biến thiên mạnh.
- `InterruptedException` phải được xử lý ở caller, không nuốt mà tiếp tục loop vô hạn.

## 35. Java 17: gom theo số item và byte budget

Một batching utility đơn giản:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.ToIntFunction;

public final class SizeBoundedBatcher<T> {
    private final int maxItems;
    private final long maxBytes;
    private final ToIntFunction<T> estimateBytes;
    private final List<T> pending = new ArrayList<>();
    private long bufferedBytes;

    public SizeBoundedBatcher(
        int maxItems,
        long maxBytes,
        ToIntFunction<T> estimateBytes
    ) {
        if (maxItems <= 0 || maxBytes <= 0) {
            throw new IllegalArgumentException("batch limits");
        }
        this.maxItems = maxItems;
        this.maxBytes = maxBytes;
        this.estimateBytes = estimateBytes;
    }

    public synchronized List<List<T>> add(T value) {
        int size = estimateBytes.applyAsInt(value);
        if (size <= 0 || size > maxBytes) {
            throw new IllegalArgumentException("invalid item size");
        }

        List<List<T>> ready = new ArrayList<>();
        if (!pending.isEmpty()
                && (pending.size() >= maxItems
                    || bufferedBytes + size > maxBytes)) {
            ready.add(drain());
        }

        pending.add(value);
        bufferedBytes += size;

        if (pending.size() >= maxItems) {
            ready.add(drain());
        }

        return ready;
    }

    public synchronized List<T> flush() {
        return drain();
    }

    private List<T> drain() {
        if (pending.isEmpty()) return List.of();
        List<T> batch = List.copyOf(pending);
        pending.clear();
        bufferedBytes = 0;
        return batch;
    }
}
```

### Production caveats

Đây là **buffer in-memory**: crash trước flush làm mất buffered events nếu không có durable source để replay. Phải gắn source checkpoint với kết quả sink, không chỉ với `batcher.add`.

Ví dụ không tự flush theo thời gian: cần một scheduler/worker đóng lô khi **max wait duration** đến, đồng bộ với `add`. Nếu scheduler cứ flush khi không có item, tránh tạo batch rỗng.

`estimateBytes` là **ước lượng**; actual serialized bytes có thể lớn hơn. Phải giữ margin so với giới hạn của SDK/server và validate sau serialization khi cần.

## 36. Tốc độ đầu tiên và tổng thời gian: hai SLO khác nhau

Đối với UI:

```text
Time to First Page (TTFP) = 80 ms
Page 1 response has 20 items
```

người dùng có thể bắt đầu tương tác ngay.

Đối với export:

```text
Time to First Batch = 80 ms
Total Job Completion = 120 seconds
```

TTFP tốt không có nghĩa export đạt SLO tổng, và ngược lại.

### Các metric nên tách

- Time to first item/page.
- Page p50/p95/p99.
- End-to-end export duration.
- Rows/s và MiB/s.
- Network RTT/bytes transferred.
- Number of fetch/getMore calls.
- CPU/GC per record.
- Peak heap/direct memory.
- Sink acknowledgment latency.
- Checkpoint/recovery overhead.

**Tối ưu theo mục tiêu trải nghiệm và correctness của workload**, không chỉ theo một trung bình chung.

## 37. Timeout budget và batch size

Một request HTTP có deadline 2 giây:

```text
HTTP deadline         2000 ms
Authentication          50 ms
DB query and paging   1300 ms
Serialization          150 ms
Network response       150 ms
Safety margin          350 ms
```

Nếu backend cố fetch 20.000 records trước khi trả page đầu, request có thể vượt deadline và client retry, gây thêm tải.

### Deadline phân tầng

- HTTP/caller deadline.
- Pool acquisition timeout.
- Database command timeout.
- Cursor fetch timeout.
- Batch write/retry budget.
- Total job/export deadline.

Một batch size lớn có thể kéo dài từng request đến mức retry storm. Hãy thiết kế **max batch processing time** và phân biệt timeout có outcome unknown với lỗi chắc chắn chưa commit.

### Khi chấp nhận async job

Nếu export mất vài phút, trả `202 Accepted + jobId` hoặc một giao thức streaming/job phù hợp có thể tốt hơn việc giữ request đồng bộ hàng phút.

Không đánh dấu job `COMPLETED` trước khi tất cả output parts được ghi bền và checkpoint phù hợp được cập nhật.

## 38. Prefetch có thể tăng throughput nhưng tăng memory

Driver hoặc app có thể prefetch batch \(k+1\) trong khi xử lý batch \(k\):

```text
Time:
  fetch batch 1 ---- process batch 1
             fetch batch 2 ---- process batch 2
                        fetch batch 3 ---- ...
```

Nó giúp chồng lấp network và CPU. Nhưng nếu sink chậm, prefetch sâu sẽ gây buffered results lớn và giữ server cursor/connection lâu.

### Chọn prefetch depth

Một số điểm cần đo:

- Fetch latency vs processing latency.
- Batch bytes.
- Max in-flight fetches/queued data.
- Heap/direct buffers.
- Cancellation cleanup.
- Source/sink consistency.

Không yêu cầu **prefetch=10** cho tất cả queries. Với mobile page nhỏ, không cần prefetch dữ liệu không được dùng. Với export scan, prefetch 1-2 batches có thể hữu ích nếu resources cho phép.

## 39. Compression: ít bytes hơn nhưng không miễn phí

NoSQL drivers/protocols có thể hỗ trợ compression, HTTP content encoding hoặc gRPC compression tùy stack.

Một batch:

```text
Uncompressed payload: 4 MiB
Compressed on wire:   1 MiB
```

có thể giảm transfer time khi bị bandwidth chi phối. Nhưng:

- Compression tốn CPU ở client/server.
- Các blobs/video đã nén khó nén thêm.
- Batch size bytes phải hiểu là **uncompressed request limits** hay wire bytes theo API.
- Một batch giải nén lớn có thể tăng peak memory.
- Payload chứa secrets và attacker-controlled bytes qua kênh phù hợp cần cân nhắc rủi ro side-channel compression theo threat model.

### Kiểm tra đúng chỉ số

Đo **wire bytes, payload bytes, compression CPU và latency**, không chỉ số request. Nhiều requests nhỏ có thể bị headers/metadata overhead chi phối; ít requests khổng lồ lại bị transfer/decode chi phối.

## 40. Connection pooling và HTTP/2 multiplexing

Một SDK có thể dùng:

- TCP connections/tls sessions.
- HTTP keep-alive.
- HTTP/2 multiplexing.
- Driver-specific binary protocol with multiple in-flight requests.
- Connection pools per node/endpoint.

Vì vậy:

> **100 logical requests không đồng nghĩa 100 sockets, và 1 bulk API call không đồng nghĩa 1 packet.**

### Những số cần theo dõi

- Active/idle connections.
- Pool wait queue.
- Requests in-flight per connection.
- Pending socket writes.
- Retry/redirect/leader discovery.
- Network throughput/packet loss.

Một pool quá nhỏ gây queueing, nhưng pool quá lớn có thể làm DB overload. Khi bài toán là query thiếu index, tăng pool/batch sẽ không chữa nguyên nhân.

### Không tạo client cho từng page

Java application thường nên tái sử dụng thread-safe NoSQL client theo lifecycle service, thay vì tạo client/TLS handshake/pool mới ở mỗi trang. Nhưng session/cursor/iterator cần scope và close phù hợp từng SDK.

## 41. Tối ưu batch size bằng thực nghiệm, không suy đoán

Thiết lập một ma trận:

```text
Page/fetch sizes:      25, 50, 100, 250, 500, 1000
Concurrent workers:    1, 4, 16, 32
Data size:             small, median, p99 document bytes
Page depth:            first, middle, deep
Traffic:               steady, burst
Concurrency mix:       read-only, read+write
```

Đo ở cùng dữ liệu và điều kiện:

| Cấu hình | Rows/s | p95/page | p99/page | Peak heap | DB CPU | Retries |
|---|---:|---:|---:|---:|---:|---:|
| B=25, C=4 | đo | đo | đo | đo | đo | đo |
| B=100, C=4 | đo | đo | đo | đo | đo | đo |
| B=500, C=4 | đo | đo | đo | đo | đo | đo |
| B=100, C=16 | đo | đo | đo | đo | đo | đo |

Không tự điền kết quả chưa đo vào bảng.

### Một cấu hình “tối ưu” phải thỏa nhiều ràng buộc

- API p99 không vượt SLO.
- Throughput đạt mục tiêu.
- Không vượt memory/CPU/connection limits.
- Không tạo rate limit/retry storm.
- Cost per 1.000 records hợp lý.
- Pagination correctness và tenant isolation được giữ.

Batch size lớn nhất **không phải** cấu hình tốt nhất nếu làm p99 của request tương tác xấu đi.

## 42. Dữ liệu benchmark phải giống thực tế

Một benchmark với 10.000 documents kích thước đều nhau trong RAM **không đại diện** cho production có:

- 100 triệu documents.
- Một số tenants chứa 90% dữ liệu.
- Documents có nested arrays từ 1 KiB tới 1 MiB.
- Hot partitions.
- Insert/update/delete chạy song song.
- Indexed và non-indexed access patterns.
- Dữ liệu có tombstones, compaction hoặc index fragmentation.
- Một số requests có query filter rất ít matches.

### Các biến cần cố định

| Nhóm | Cần mô tả |
|---|---|
| Dataset | Tổng records, bytes, phân bố kích thước, selectivity, skew theo tenant |
| Index | Các indexes thực tế và index build state |
| Query | Sort/filter, projection, page depth, read consistency |
| Client | Java/SDK version, serialization, pool, fetch size, retries |
| Network | RTT, bandwidth, packet loss, region placement |
| Server | Số shards/nodes, instance types, disk, compaction/load |
| Concurrency | Users/tasks, arrival rate, think time, burst |
| State | Warm/cold cache, replication lag, background writes |
| Correctness | Số records mong đợi, missing/duplicate và source revision |

### Phân bố theo tenant

Nếu 99% queries thuộc tenant nhỏ và 1% thuộc một tenant rất lớn, benchmark chỉ lấy “tenant trung bình” có thể che giấu p99 của tenant lớn. Cần sampling theo **distribution thực tế** và riêng các worst-case tenants, tránh công khai PII/IDs trong reports.

### Hạn chế data generator

Giả lập records bằng toàn dữ liệu ngẫu nhiên có thể làm compression ratio khác production, gây sai đánh giá network bytes. Các giá trị giống nhau lặp lại nhiều có thể nén quá tốt và làm batch trông nhanh bất thường.

## 43. Warm cache, cold cache và GC là các trạng thái khác nhau

Một phép đo:

```text
First page query after restart: 150 ms
Same page repeated 10,000 times: 5 ms
```

có thể chủ yếu đo **cache hit**, không đo NoSQL pagination.

Các tầng cache có thể gồm:

- Java process/JIT.
- Driver metadata/prepared statement cache.
- OS page cache.
- Database buffer cache.
- Redis/Caffeine application caches.
- Search index filesystem cache.
- DNS/TLS connection reuse.

### Một cách đo hợp lý

1. Chuẩn bị dataset đúng kích thước.
2. Warm-up JVM/driver và xác định trạng thái cache mong muốn.
3. Đo **cold start** riêng.
4. Đo **steady state** sau warm-up.
5. Chạy nhiều lần, ghi confidence/variance.
6. So results và server metrics trước/sau.

### GC và allocation

Nếu batch size tăng từ 100 lên 10.000, throughput có thể tăng ban đầu rồi giảm mạnh do allocation/GC. Đo heap occupancy, allocation rate, pause durations và direct buffer metrics thay vì chỉ CPU trung bình.

## 44. Open-loop và closed-loop load tests

### Closed-loop

Một số users cố định gửi request tiếp theo **sau khi request trước hoàn tất**:

```text
Client 1: request -> wait -> next request
Client 2: request -> wait -> next request
```

Khi server chậm, tốc độ request gửi vào tự giảm. Test có thể **che overload** của traffic thực với arrival rate cố định.

### Open-loop

Load generator cố tạo arrival rate độc lập với latency của các request trước:

```text
Target arrivals: 1000 requests/second
Even as p99 grows, offered load remains controlled
```

Hữu ích để nghiên cứu saturation, nhưng phải giới hạn an toàn và đo dropped/scheduled-late requests.

### Coordinated omission

Nếu tool chỉ đo latency của những requests được phát **sau khi hệ hồi phục**, nó có thể bỏ qua khoảng mà requests lẽ ra phải đến trong lúc server đứng. Khi đánh giá p99/tail latency, chọn load generator và reporting tránh thiên lệch này.

### Khuyến nghị phép đo

- Ghi **offered load** và **achieved throughput** riêng.
- Ghi queue wait và rejected/throttled count.
- Đo p50/p95/p99 cả client lẫn server.
- Thử ở mức trước, gần và sau saturation có kiểm soát.
- Không đo benchmark bằng một thread khi production có hàng trăm concurrent requests.

## 45. Chọn đơn vị benchmark đúng với use case

**Không trộn các chỉ tiêu khác nhau**:

| Workload | Unit | Mục tiêu điển hình |
|---|---|---|
| HTTP list endpoint | requests/s, p99/request | SLO người dùng |
| Export | records/s, MiB/s, job completion | Tổng thời gian |
| CDC ingest | events/s, lag, per-event latency | Bắt kịp source |
| Bulk backfill | documents/s, peak memory | Chi phí và ổn định |
| Mobile scrolling | bytes/page, time-to-first-page | Mạng yếu/battery |
| Admin keyspace scan | keys/s, DB impact | Không làm ảnh hưởng production |

Một cấu hình có thể đạt 50.000 records/s trong export nhưng tạo page p99 4 giây, không phù hợp UI.

### Throughput saturation curve

```text
Throughput
 ^
 |                   ______ plateau
 |               ___/
 |           ___/
 |       ___/
 |   ___/
 +---------------------------------> Concurrency
                      p99 rises sharply past knee
```

Khi tăng concurrency mà throughput không tăng nữa nhưng p99/error rate tăng, hệ đã gần hoặc vượt giới hạn capacity. Đừng cố tăng batch/pool thêm chỉ để thấy requests queued nhiều hơn.

## 46. Cross-shard fan-out và số lần trao đổi mạng thực

Một API Java gửi **một** query:

```text
Java -> coordinator: search across all tenants
```

Coordinator có thể fan-out tới 20 shards:

```text
                     +-- shard 1
                     +-- shard 2
Java -> coordinator --+-- shard 3
                     ...
                     +-- shard 20
```

Vì vậy một client round trip **không** có nghĩa một internal network trip. Query cross-shard có thể:

- Đợi shard chậm nhất.
- Kéo nhiều dữ liệu về coordinator để sort/merge.
- Dồn CPU/memory ở coordinator.
- Bị ảnh hưởng bởi scatter-gather latency.

### Tối ưu từ data model

- Route bằng partition/shard key khi có thể.
- Tránh query nhiều tenants nếu user chỉ xem một tenant.
- Thiết kế per-tenant/per-time bucket hợp lý.
- Dùng precomputed/materialized read models khi query không có index path khả thi.
- Không fan-out riêng từng record từ Java nếu backend có batch API.

### Đừng để batch size che hotspot

Nếu 90% mutations cùng đổ vào một key/partition, gom 500 writes/batch vẫn có thể bị nghẽn tại một owner. Cần phân bố/shard counters hoặc thay access pattern, không chỉ tăng batch.

## 47. Công bằng giữa tenants và các workload

Một tenant lớn chạy export 50 triệu records:

```text
Export worker batches 5000, concurrency 128
   |
   v
Shared DB pool
   |
   +-- other tenants' interactive queries wait
```

Ngay cả khi export đạt records/s rất cao, toàn service có thể **vi phạm SLO** cho tenants còn lại.

### Giải pháp

- Rate limit và concurrency budget theo tenant/workload.
- Tách bulk/export queue khỏi interactive API path.
- Dùng background job với schedule.
- Bounded per-tenant in-flight bytes.
- Tối ưu projection/index/bucket.
- Đo p99 của **cả workload phụ thuộc**, không chỉ job throughput.
- Có thể dùng client/pool riêng để giảm contention phía client khi cần, nhưng database vẫn là tài nguyên chung.

### Fairness trong batching

Nếu một batch chứa jobs từ nhiều tenants, cần giữ provenance và kết quả per-item để báo/retry đúng. Với dữ liệu nhạy cảm, không trả batch results cho requester khác hoặc dùng tenantKey thiếu scope.

## 48. Tự điều chỉnh batch size theo phản hồi

Một hệ có thể thay vì cố định \(B=500\) dùng controller nhẹ:

```text
Starting batch size = 100
Target p95 per batch < 200ms (example only)
Max serialized payload = 2 MiB
Minimum batch size = 25
Maximum batch size = 500

If latency low and no throttling:
    cautiously increase batch size.
If latency high, throttled, or memory high:
    decrease batch size.
```

Đây là pseudocode policy, không phải controller production.

### Nguy cơ dao động

- RTT có noise.
- Một record đặc biệt lớn làm batch bất thường.
- Autoscaling/shard movement thay đổi latency.
- Nhiều clients cùng adaptive tuning có thể đồng loạt tăng tải.
- Throttle responses có backoff yêu cầu riêng.

Do đó cần:

1. Clamp min/max sizes/bytes.
2. Đo p95/p99 theo cửa sổ đủ ổn định.
3. Hysteresis/cooldown tránh đổi liên tục.
4. Giảm mạnh khi throttle, tăng chậm khi ổn định (một ý tưởng kiểu AIMD).
5. Có hard deadlines và cancellation.
6. Version/config rollout có thể rollback.

**Tự điều chỉnh không thay fault handling.** Batch có partial failure vẫn phải retry per-item/idempotent, dù controller giảm B.

## 49. API guardrails: page size là đầu vào dễ bị lạm dụng

Một API:

```text
GET /orders?limit=1000000000
```

nếu tin tham số không giới hạn, có thể dẫn tới scan, memory pressure hoặc denial-of-service.

### Guardrails gợi ý

- Default page size hợp lý theo UX (ví dụ 20–50, chỉ minh họa).
- Hard max phù hợp response bytes và SLO.
- Kiểm tra `limit > 0`.
- Từ chối hoặc clamp số vượt giới hạn theo API contract.
- Giới hạn sort/filter chỉ các truy vấn đã có access path an toàn.
- Rate limit theo principal/tenant.
- Timeout và query max time.
- Quota cho export jobs.
- Opaque page token có signature/expiry/filter binding.
- Theo dõi deep pagination abuse.

### Không bỏ tenant và authz khi đổi page

```text
Page 1 token for tenant T01
Client switches to tenant T02
Client reuses token T01
```

Server phải từ chối token mismatch, không lấy tenant từ token làm quyền truy cập. Kiểm tra security context trước khi thực thi query ở trang sau.

### Overflow

Khi dùng `pageNumber * pageSize` trên Java `int`, giá trị lớn có thể overflow thành số âm. Dùng validation, `Math.multiplyExact` và giới hạn business, hoặc chuyển sang token pagination.

## 50. Độ ổn định của sort key khi phân trang

**Timestamp không unique** và nhiều business fields có thể mutable:

- `updatedAt` thay đổi khi user sửa.
- `score` thay đổi khi recommender recalculates.
- `rank` thay đổi khi có thêm likes.
- `status` thay đổi qua workflow.

Nếu phân trang theo một field có thể thay đổi:

```text
Page 1 read O1 score=100
O5 score changes from 10 to 200
Page 2 anchor score=50
O5 is now before anchor, so it may not appear on page 2.
```

### Một số lựa chọn

1. Sort theo **immutable creation sequence + stable ID** nếu use case phù hợp.
2. Snapshot/PIT cho việc duyệt nhất quán.
3. Dùng event log position thay vì query pagination cho incremental sync.
4. Client dedup theo ID nếu hợp đồng chấp nhận một số dữ liệu thay đổi trong traversal.
5. Nếu sort theo relevance/rank động, thiết kế UX như feed “load more” với kỳ vọng live result rõ ràng.

### Dedup client không chữa missing

Client lưu `seenIds` có thể loại records trùng nhưng **không phát hiện được records hoàn toàn bị bỏ** vì sort key di chuyển. Với báo cáo/audit, cần giải pháp ở source/snapshot, không chỉ frontend Set.

## 51. HTTP streaming so với page-by-page

Một endpoint export có thể:

**A. Trả các pages:**

```text
GET /export?pageToken=T1 -> page 1
GET /export?pageToken=T2 -> page 2
...
```

**B. HTTP streaming:**

```text
GET /export -> NDJSON/CSV stream over one response
```

**C. Background export job:**

```text
POST /exports -> jobId
GET /exports/{jobId} -> progress
GET signed object storage URL when ready
```

### Trade-offs

| Kiểu | Điểm mạnh | Giới hạn |
|---|---|---|
| API pages | Dễ resume, cache/UX load-more | Nhiều HTTP round trips |
| HTTP stream | Ít API calls, progressive output | Connection dài, disconnect/restart khó |
| Background job | Thích hợp hàng triệu records, checkpoint bền | Phức tạp hơn, cần job state và storage |

### HTTP stream vẫn cần DB paging bên trong

Một response HTTP duy nhất không có nghĩa DB chỉ một round trip. Server có thể duyệt cursor nhiều batches và stream tới client. Phải áp **backpressure từ HTTP writer tới DB cursor**; nếu client đọc chậm mà service cứ fetch, memory vẫn tăng.

### Client disconnect

Đóng cursor/cancel outstanding fetches khi không cần nữa, nhưng không coi cancel là rollback mutations đã commit. Với export job, phải định nghĩa liệu disconnect có dừng job hay job tiếp tục và cho phép resume.

## 52. Checkpoint khi export: xác nhận sau output bền

Một job:

```text
Fetch page with cursor C0
Transform 500 records
Upload output part P1
Save next cursor C1
```

Điểm crash:

**Crash sau C1 checkpoint trước khi P1 được lưu:**

```text
Resume at C1 -> P1 may be missing forever
```

**Crash sau P1 được lưu trước C1 checkpoint:**

```text
Resume at C0 -> P1 may be generated twice
```

### Giao thức an toàn hơn

1. Fetch page.
2. Transform deterministically theo snapshot/revision.
3. Ghi output part với **idempotent part ID**/conditional generation.
4. Xác minh durable part write.
5. Ghi checkpoint tiếp theo vào job state.
6. Khi replay, đối chiếu part manifest để tránh append trùng.

Khi output là CSV append trên một file không có transaction, retry khó hơn; dùng nhiều immutable parts và manifest commit có thể dễ quản lý.

### Cursor token còn hạn không?

Nếu job kéo dài hơn TTL của token/PIT/server cursor, resume có thể không hợp lệ. Cần checkpoint dựa trên **stable keyset/source position** hoặc snapshot materialization và retention policy. Đừng hứa resume vô hạn từ một paging token ngắn hạn.

### Multi-partition export

Nếu phân vùng theo tenant/day/shard, checkpoint là map hoặc manifest per partition, không phải global max ID khi IDs không có thứ tự toàn hệ.

## 53. Metrics để phân biệt nút thắt

| Metric (tên minh họa) | Câu hỏi cần trả lời |
|---|---|
| `api_page_latency_ms` (p50/p95/p99) | User chờ một trang bao lâu? |
| `api_page_items` | Một trang thực tế trả bao nhiêu items? |
| `api_page_response_bytes` | Payload lớn hay nhỏ? |
| `db_rows_examined` | Server phải scan bao nhiêu? |
| `db_rows_returned` | Bao nhiêu rows thực sự trả? |
| `db_fetch_roundtrips` | Bao nhiêu fetch/getMore/query calls? |
| `db_fetch_batch_items` | Rows thực tế mỗi batch |
| `db_fetch_batch_wire_bytes` | Bytes thực tế mỗi fetch |
| `db_command_latency_ms` | Server/driver chậm ở lệnh nào? |
| `pool_acquire_latency_ms` | Chờ mượn connection lâu không? |
| `cursor_open_duration_ms` | Cursor giữ tài nguyên bao lâu? |
| `active_cursors` | Có leak/long scans không? |
| `bulk_write_items_total` | Bao nhiêu mutations gửi? |
| `bulk_write_partial_failures` | Có errors theo item không? |
| `bulk_write_retry_items` | Retry bao nhiêu items và vì sao? |
| `batch_inflight` | Concurrency hiện tại |
| `batch_buffered_bytes` | Memory queue có phình không? |
| `rate_limit_throttles` | Server/provider đã overload? |
| `export_records_per_second` | Job throughput |
| `export_checkpoint_lag` | Job có tiến độ bền không? |
| `gc_pause_ms` | Batch có gây GC spikes? |
| `cross_tenant_scope_mismatch` | Có lỗi key/query/token scope không? |
| `pagination_duplicate_ids` | Có records lặp giữa pages không? |
| `pagination_missing_records` | Có thiếu records so với snapshot/reference không? |

Các tên trên **không phải metric built-in của mọi database**; cần map sang JMX/Micrometer/OpenTelemetry/driver metrics và profiling thực tế.

### Không đưa ID tùy ý vào metric labels

Nếu dùng `tenantId`, `orderId` hay raw token làm nhãn high-cardinality, chi phí telemetry có thể rất lớn và lộ thông tin. Dùng service, query class, index, page-depth bucket, batch-size bucket, outcome và region; với tenant phân tích riêng cần aggregate/audit có quyền.

### Đo cả correctness

Một benchmark “100.000 records/s” nhưng làm mất 2.000 records do scan/token/partial failures không phải thắng lợi hiệu năng. **Correctness, durability, authorization và resource limits** đều là điều kiện để công bố kết quả.

## 54. Runbook: truy vấn trang sâu chậm

### Bước 1 — Tách latency

Đo request queue, pool wait, DB execution, network transfer, decoding và HTTP serialization. Không suy “DB chậm” từ tổng HTTP p99.

### Bước 2 — Kiểm tra query shape

Xem filter/sort/projection, index, shard key và plan; nếu dùng `skip=1_000_000`, cân nhắc keyset hoặc continuation token.

### Bước 3 — Kiểm tra bytes

Một page 50 documents có thể là 1 MiB hoặc 50 MiB. Chỉ lấy fields cần, cân nhắc nén, giới hạn nested arrays và max payload.

### Bước 4 — Kiểm tra cursor/fetch

Đo số `getMore`/requests và average items/bytes mỗi batch. Nếu batch 1 khiến hàng nghìn RTT, thử các batch sizes có kiểm soát.

### Bước 5 — Kiểm tra consistency

Sự kiện insert/update/delete làm duplicate/missing? Query có sort tie-breaker không? API cần live view hay snapshot?

### Bước 6 — Đo workload cạnh tranh

Một export job có chiếm pool/shard làm page p99 xấu đi không? Thử bulkhead và concurrency budget.

### Bước 7 — Xử lý retry/throttle

Nếu nhiều timeouts, **đừng tự động tăng batch/concurrency**. Đo retry count, throttle, DB CPU, queue depth và giảm tải.

### Bước 8 — So sánh trước/sau

Giữ dataset/query và offered load nhất quán. Chỉ kết luận tốt hơn khi throughput, latency, memory, errors và correctness đều đạt yêu cầu.

## 55. Runbook: export job tăng heap và không tiến độ

Một export đọc 10 triệu rows:

```text
Heap steadily rising
Rows fetched > rows written
Output queue grows
Checkpoint unchanged
```

### Kiểm tra

1. Driver có prefetch quá nhiều không?
2. Có dùng `into(new ArrayList<>())` hoặc `collect(toList())` không?
3. Bounded queue thực sự có giới hạn bytes không?
4. Sink write futures hoàn tất chậm hay bị treo?
5. Có backpressure từ output writer tới source cursor không?
6. Có rows quá lớn ngoài byte budget?
7. Retry batch có giữ bản sao của toàn bộ batch trong RAM không?
8. Có cursor/connection leak khi exception/cancel không?
9. Snapshot/page token có hết hạn trước checkpoint không?

### Chữa theo nguyên nhân

- Đọc cursor theo batches, xử lý/ghi theo chunks bounded.
- Hạn chế in-flight batches/bytes.
- Áp timeouts và cancellation cleanup.
- Giảm batch size nếu oversized responses gây GC.
- Tăng batch size vừa phải nếu bị RTT chi phối và memory còn dư.
- Tách export khỏi interactive pool/traffic.
- Dùng idempotent output parts + durable checkpoint.

### Đừng xóa checkpoint để “chạy lại từ đầu” khi không cần

Nếu job đã ghi một phần output, restart từ đầu có thể ghi trùng hoặc tạo dữ liệu không nhất quán. Cần reconcile manifest/job state, xác định đúng recovery boundary.

## 56. Những ngộ nhận phổ biến

| Ngộ nhận | Điều đúng |
|---|---|
| “Một HTTP request chỉ tạo một DB round trip” | Backend có thể fetch nhiều pages và fan-out nhiều shards |
| “Batch size 500 luôn trả đúng 500 rows” | Có byte caps, filters, server paging semantics |
| “Page size và fetch size là một” | Một cái là API output, một cái là driver/network |
| “Tăng batch size vô hạn sẽ giảm latency” | Có memory/transfer/GC/timeout/retry costs |
| “Số rows trả về bằng số rows examined” | Query engine có thể scan nhiều hơn rất nhiều |
| “LIMIT 20 làm full scan nhanh” | Filter/sort/index path quyết định chi phí |
| “Offset/limit luôn đủ hiệu quả” | Deep offsets thường costly và dễ duplicate/missing |
| “Keyset tự tạo snapshot” | Sort key mutable/updates vẫn làm traversal thay đổi |
| “Sort theo timestamp là deterministic” | Nhiều items có cùng timestamp; cần tie-breaker |
| “Token Base64 nghĩa là không thể sửa” | Encode không phải ký/xác thực |
| “Token page 1 dùng lại được ở tenant khác” | Scope phải gắn với authz/query |
| “DynamoDB Limit=50 nghĩa 50 items return” | Filter/1MB cap có thể trả ít hoặc rỗng |
| “DynamoDB Items rỗng là hết dữ liệu” | Có thể còn LastEvaluatedKey |
| “Cassandra LIMIT là page size” | Query LIMIT khác driver fetch size |
| “Redis SCAN COUNT là kích thước cố định” | Chỉ là hint; cursor có thể còn dù results rỗng |
| “Redis SCAN là snapshot phân trang ổn định” | Có thể duplicates và concurrent changes |
| “Search after cho nhảy đến page bất kỳ” | Cần anchor/sort values từ trang trước |
| “BulkWrite là một transaction toàn batch” | Partial success và cross-item atomicity khác nhau |
| “Cassandra BATCH luôn tăng throughput” | Multi-partition BATCH có thể tốn chi phí lớn |
| “Redis pipeline = MULTI/EXEC” | Pipelining giảm RTT, không tự atomic |
| “HTTP 200 của bulk nghĩa mọi item thành công” | Kiểm tra `UnprocessedItems`/per-item errors |
| “Retry toàn batch luôn an toàn” | Mutation không idempotent có thể lặp effect |
| “Tăng pool sẽ sửa query chậm” | Có thể chỉ tăng tải server |
| “Cursor sẽ tự được GC đóng đúng hạn” | Đóng theo resource ownership, không chờ GC |
| “Client cancel nghĩa DB write bị rollback” | Remote write có thể đã commit |
| “Count tổng miễn phí nếu page nhỏ” | Exact count có thể là query/scan riêng |
| “Một benchmark warm cache nói lên cold p99” | Cần báo cáo cả cold/steady state |
| “Throughput tăng là đủ” | Cần p99, errors, fairness, correctness và cost |

## 57. Hai mươi lăm bài tập thực hành

### Bài 1 — Tính số fetch rounds

Cần đọc 24.000 rows. So \(R=\lceil N/B\rceil\) với B lần lượt 1, 50, 200 và 1.000. Nêu vì sao kết quả không bằng tổng mọi packet mạng.

### Bài 2 — RTT và payload

RTT 12 ms, 5.000 records x 3 KiB. Tính network-wait component của batch 25 so với batch 250 theo mô hình tuần tự. Giải thích vì sao tổng bytes truyền gần như không đổi.

### Bài 3 — API size và driver size

Frontend muốn 20 records, driver batch size 200. Những trường hợp nào prefetch 200 có lợi và trường hợp nào là lãng phí?

### Bài 4 — Deep offset

Một endpoint dùng `skip=1_500_000, limit=50`. Phân tích chi phí query plan, sort và index, rồi đề xuất keyset/continuation token.

### Bài 5 — Stable sort

Có 100 orders cùng `createdAt`. Hãy giải thích vì sao chỉ dùng `createdAt < last` làm thiếu dữ liệu. Viết predicate cho `createdAt DESC, _id DESC`.

### Bài 6 — Mixed sort

Sort `score DESC, name ASC, id ASC`. Viết logic seek predicate với ba nhánh lexicographic theo từng direction; giải thích tại sao không thể dùng tất cả dấu `<`.

### Bài 7 — Concurrent insert

Page 1 trả A,B,C. Một record X được chèn trước A. So kết quả page 2 của offset và keyset; keyset có thể bị sai kiểu khác khi sort field thay đổi không?

### Bài 8 — Token tenant

Một API phát token cho tenant T01, user dùng token với tenant T02. Thiết kế checks từ authentication, filter hash, signature và expiry.

### Bài 9 — MongoDB keyset

Viết Java query MongoDB lọc tenant+status, sort createdAt/_id, lấy 26 records cho page size 25. Token nên lấy anchor của item nào?

### Bài 10 — MongoDB cursor

Export 2 triệu documents dùng `find().into(new ArrayList<>())` gây OOM. Viết lại dạng cursor `batchSize` + try-with-resources và output chunks bounded.

### Bài 11 — DynamoDB filter

Query Limit=40 trả 0 items nhưng `LastEvaluatedKey` không rỗng. Có được dừng không? Vì sao `FilterExpression` tạo hiện tượng này?

### Bài 12 — DynamoDB bulk

Từ 80 put requests, chia thành các `BatchWriteItem` hợp lệ theo giới hạn items. Response có `UnprocessedItems`: đề xuất bounded retry/backoff và idempotency.

### Bài 13 — Cassandra paging

Phân biệt `LIMIT 500`, statement `setPageSize(100)` và năm lời gọi network fetch. Nếu query filter cần scan nhiều partitions, batch size có giải quyết data model không?

### Bài 14 — Redis SCAN

`SCAN 0 MATCH app:* COUNT 100` trả 0 keys nhưng cursor=456. Consumer có được dừng không? Vì sao cần dedup nếu keyspace thay đổi?

### Bài 15 — Redis pipeline

100 commands Redis mỗi command chờ RTT 5 ms nếu tuần tự. Pipeline giúp thế nào? Nó có đảm bảo atomicity, rollback hoặc exactly-once không?

### Bài 16 — Elasticsearch

So deep `from+size` với `search_after`. Tại sao cần sort tie-breaker? PIT giải quyết một phần consistency nào và khi nào hết hạn?

### Bài 17 — Neo4j

Một traversal 5 hops trả LIMIT 20 nhưng vẫn chậm. Vì sao LIMIT 20 không đồng nghĩa chỉ duyệt 20 paths? Đề xuất xem query plan và giới hạn branching.

### Bài 18 — Batch count/bytes

500 items có size: 499 x 2 KiB, 1 x 500 KiB. Với max 200 items hoặc max 512 KiB mỗi batch, hãy mô tả cách chunker flush mà không vượt size cap.

### Bài 19 — Partial bulk success

Batch offsets 100..104 có records 100,101,103,104 thành công, 102 lỗi. Checkpoint Kafka được tiến đến offset nào? Nếu retry 102 thành công thì sao?

### Bài 20 — Timeout after write

Một `$inc` MongoDB thành công nhưng response mất; client retry toàn batch. Phân tích duplicate effect và giải pháp conditional revision/inbox ledger.

### Bài 21 — Concurrency theo Little's Law

Mục tiêu 3.000 operations/s và latency trung bình 30 ms. Ước lượng số in-flight trung bình; giải thích vì sao không suy pool max chính xác bằng con số đó.

### Bài 22 — Pipeline backpressure

Source fetch 8.000 records/s, sink ghi 2.000 records/s. Sau 20 giây, queue tăng bao nhiêu record nếu không chặn? Thiết kế bounded queue/permits và source pause.

### Bài 23 — Benchmark khách quan

Lập ma trận B = {25, 100, 500}, C = {1, 8, 32}, thử first/deep pages, record size p50/p99, read-only và mixed workload. Những metrics nào cần thu để không đưa ra kết luận chỉ dựa trên throughput?

### Bài 24 — Snapshot vs live

Một export 10 triệu orders kéo dài 30 phút và có updates trong lúc chạy. So các lựa chọn live keyset, database snapshot, materialized export job và CDC catch-up. Cần làm gì nếu PIT/token hết hạn?

### Bài 25 — Thiết kế tổng hợp

Thiết kế một service Java gồm:

- API `GET /orders` trả page tối đa 50 records với signed token.
- MongoDB/Cassandra/DynamoDB adapter theo query/index tương ứng.
- Background export với cursor/keyset và durable checkpoint.
- Batch writer có item/byte/time thresholds.
- Giới hạn concurrency/backpressure.
- Metrics về p99, round trips, bytes và correctness.

Mô tả các điểm crash, retry idempotency, multi-tenant isolation và kế hoạch đo tải trước khi deploy.

## 58. Checklist lựa chọn phân trang và kích thước lô

1. **Use case là UI, mobile, export, CDC hay bulk backfill?** Ưu tiên first page hay total completion?
2. **Page size HTTP khác driver fetch size ở đâu?** Có giới hạn rõ cả hai không?
3. **Có deep offset không?** Nếu có, plan có scan nhiều index entries không?
4. **Đã định nghĩa sort toàn phần và tie-breaker unique chưa?**
5. **Sort keys có mutable không?** Có chấp nhận duplicate/missing do updates không?
6. **API cần live view hay snapshot-consistent traversal?**
7. **Có index/partition key/clustering order hỗ trợ filter và sort không?**
8. **Projection đã bỏ fields thừa chưa?**
9. **Đã đo records examined, response bytes và round trips thật chưa?**
10. **Token có ràng buộc tenant, query hash, sort, page size, version và expiry không?**
11. **Token có opaque/signed và được validate theo current authorization không?**
12. **Có phân biệt token tiếp trang của SDK với server cursor không?**
13. **Có xử lý API trả trang rỗng nhưng vẫn có token không?**
14. **Có đóng cursors/results/transport khi job dừng, lỗi hoặc cancel không?**
15. **Batch giới hạn cả số items và bytes, không chỉ một con số count không?**
16. **Có flush theo thời gian để tránh lô nhỏ chờ vô hạn không?**
17. **Nếu một item quá lớn, hệ xử lý thế nào?**
18. **Bulk API trả partial success/throttling có được kiểm tra per item không?**
19. **Retry sau timeout có idempotency và source version guard không?**
20. **Đã phân biệt Redis pipeline, Cassandra BATCH và transaction API chưa?**
21. **Có max in-flight requests, queue bytes và retry budget không?**
22. **Connection pool có dùng lại clients thay vì tạo client mỗi trang không?**
23. **Có đo warm vs cold cache, open-loop vs closed-loop load không?**
24. **Có thử p50/p95/p99 dưới mixed read/write workload không?**
25. **Có phân nhóm benchmark theo page depth, tenant size và record bytes distribution không?**
26. **Batch lớn có làm p99 của endpoints tương tác xấu hơn không?**
27. **Export có durable checkpoint sau output commit và có idempotent resume không?**
28. **Có kiểm tra missed/duplicated items khi dữ liệu thay đổi hoặc failover không?**
29. **Có metrics cho cursor lifetime, fetch count, bytes, queue, GC và throttles không?**
30. **Có runbook khi deep page chậm, partial failure hoặc OOM không?**

## 59. Kết luận

Phân trang và batching là hai đòn bẩy quan trọng để giảm chi phí trao đổi mạng và kiểm soát lượng dữ liệu trên đường đọc/ghi NoSQL. Nhưng tối ưu đúng phải xem **bốn lớp cùng lúc**:

1. **Đường truy cập:** partition/shard key, index, filter, sort, projection và số records server phải xét.
2. **Giao thức phân trang:** offset, keyset, cursor hay continuation token; thứ tự ổn định và consistency/snapshot phù hợp.
3. **Truyền và xử lý:** batch size theo count **và bytes**, RTT, bandwidth, pool, prefetch, concurrency/backpressure và CPU/GC.
4. **Tính đúng/vận hành:** tenant scope, idempotent retries, partial failures, cursor cleanup, checkpoint, retention và đo tải khách quan.

Ghi nhớ:

- **Ít round trips hơn thường tốt khi bị RTT chi phối**, nhưng một batch quá lớn có thể tăng p99, memory, timeouts và retry cost.
- **Deep offset thường tốn kém**; keyset hoặc opaque token giúp tiến qua index hiệu quả hơn khi dữ liệu có sort key/tie-breaker phù hợp.
- **Keyset không tự bảo đảm snapshot**; concurrent updates và mutable sort keys vẫn có thể làm thiếu/trùng data.
- **Page size không phải driver fetch size**, và cursor không mặc định trả batch đúng số rows cấu hình.
- **DynamoDB `LastEvaluatedKey`, Cassandra paging state, MongoDB cursor, Redis `SCAN` và Elasticsearch `search_after` có semantics khác nhau**; không ép vào một API page-number chung mà bỏ thông tin quan trọng.
- **Bulk writes và Redis pipelining không tự tạo transaction hoặc exactly-once**; phải đọc partial results và bảo vệ retry.
- **Hiệu năng phải đo cùng correctness**: throughput, page p99, server cost, bytes, memory, fairness và kết quả không mất/trùng.

Trước khi chọn `pageSize=500`, `batchSize=1000` hay tăng concurrency lên 64, hãy hỏi:

> **“Mỗi lần fetch thực sự đọc và truyền bao nhiêu bytes, tốn bao nhiêu network round trips, có scan dữ liệu thừa không, và nếu một batch bị lỗi hoặc dữ liệu đổi giữa hai trang thì hệ vẫn trả đủ đúng những bản ghi đã cam kết chứ?”**

Trả lời được các câu hỏi đó giúp tối ưu hiệu năng NoSQL bằng **số liệu và hợp đồng dữ liệu**, thay vì chỉ chọn một con số batch size lớn hơn.
