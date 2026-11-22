# Đo số phân mảnh được chạm và chứng minh lựa chọn khóa

Khi một hệ NoSQL được phân mảnh, cùng một truy vấn có thể chỉ chạy trên **một shard** hoặc phải chạy trên **nhiều shard** rồi hợp nhất kết quả. Điều này ảnh hưởng đến số node phải xử lý, lưu lượng mạng, CPU, bộ nhớ dùng để merge và độ trễ ở phần đuôi phân bố.

Ví dụ một hệ Order có 16 shard: tìm bằng `orderId` có thể được định tuyến trực tiếp nếu shard key phù hợp. Nhưng lọc `status="PENDING"` xuyên tất cả tenant có thể phải hỏi cả 16 shard. Dù trên mỗi shard đều có index `status`, router vẫn có thể không biết shard nào chứa kết quả.

Đây là hai bài toán khác nhau:

- **Shard routing:** router có biết dữ liệu cần tìm nằm ở shard nào không?
- **Local execution:** khi đã tới shard, query có sử dụng index hiệu quả không?

Bài học thuộc chương **Phân mảnh và định tuyến** của **Database No SQL**. Chúng ta sẽ đo số shard tham gia từng query shape, phân tích workload, so sánh các shard key, dùng MongoDB `explain` để kiểm chứng và mở rộng tư duy sang DynamoDB, Cassandra, Search index. Mục tiêu không phải tìm một công thức khóa tốt cho mọi hệ, mà biết **tạo bằng chứng định lượng để bảo vệ quyết định lựa chọn khóa**.

> Một shard key tốt phải vừa định tuyến những truy vấn quan trọng tới ít shard hợp lý, vừa phân bố dữ liệu và lưu lượng đủ đều, đồng thời giữ được các ràng buộc nghiệp vụ và mục tiêu vận hành.

## 1. Shard, replica, chunk và partition khác nhau thế nào?

Trong một MongoDB sharded cluster:

- **Shard** chứa một phần dữ liệu của collection; thường bản thân shard là một replica set.
- **Replica** là một bản sao của dữ liệu trong phạm vi shard đó.
- **Chunk/range** là một khoảng shard-key values có thể được đặt trên shard.
- **Router (`mongos`)** định tuyến request dựa trên shard key và metadata placement.
- **Node** là tiến trình hoặc máy tham gia hệ thống.

Ví dụ:

~~~text
Cluster: 4 shards
  Shard A: replica A1, A2, A3
  Shard B: replica B1, B2, B3
  Shard C: replica C1, C2, C3
  Shard D: replica D1, D2, D3
~~~

Nếu một query được định tuyến tới Shard B và được một replica member phục vụ, nó được tính là **chạm một shard**, không phải ba. Nếu một shard chứa 200 chunk, query chạm shard ấy vẫn là một shard trong metric tầng router.

Ở Cassandra hoặc DynamoDB, từ `partition` có semantics khác: logical partition key và physical storage partition không mặc nhiên tương đương MongoDB shard. Khi báo số “shard được chạm”, phải nêu rõ **loại đơn vị được đếm**.

## 2. Vì sao router có thể bỏ qua shard?

Sharding chia tập dữ liệu theo khóa. Router cần biết **điều kiện trên khóa** để xác định một tập shard có khả năng chứa dữ liệu.

~~~mermaid
flowchart TD
    API["Order API"] --> Router["Router"]
    Router -->|"Có khóa định tuyến đầy đủ"| S1["Shard A"]
    Router -->|"Không đủ thông tin"| S2["Shard B"]
    Router -->|"Không đủ thông tin"| S3["Shard C"]
    Router -->|"Không đủ thông tin"| S4["Shard D"]
~~~

Với query có shard-key equality đầy đủ, router thường có thể target một shard theo metadata, dù còn phải xét topology/migration.

Nếu query chỉ có field không thuộc shard key, router có thể phải hỏi tất cả shard. Nếu query ràng buộc một khoảng, nó có thể nhắm tới những shard chứa chunk giao với khoảng đó.

**Cần phân biệt** khả năng định tuyến theo range/chunk với số index entry/document được tìm bên trong shard.

## 3. Targeted, multi-shard và scatter-gather

Có ba trạng thái mô tả đơn giản:

| Loại truy vấn | Cách thực thi | Điều cần đo |
|---|---|---|
| Single-shard targeted | Chỉ một shard có thể chứa dữ liệu theo định tuyến | Một shard thực thi, local scan/index |
| Multi-shard targeted | Một tập con shard chứa những chunk phù hợp | K shard trên tổng N |
| Scatter-gather | Nhiều hoặc toàn bộ shard phải tìm kiếm rồi merge | Số shard, bytes, sort/merge cost |

Ví dụ collection có tám shard:

~~~text
Query A: chạm shard 2           -> 1/8
Query B: chạm shard 2, 5, 7     -> 3/8
Query C: chạm mọi shard         -> 8/8
~~~

Không có quy tắc rằng mọi multi-shard query đều là lỗi. Báo cáo toàn hệ có thể cần xem dữ liệu từ tất cả shard. Điều cần tránh là **một query vốn chỉ tìm đúng một Order nhưng vẫn broadcast tới toàn cluster do shard key không hợp với access pattern**.

## 4. Metric nền tảng: số shard được chạm

Với truy vấn `q`, định nghĩa:

\[
S(q)=|\{\text{shard thực sự tham gia xử lý }q\}|
\]

Nếu tại thời điểm đó collection có `N_q` shard đủ điều kiện, tỷ lệ fan-out:

\[
F(q)=\frac{S(q)}{N_q}
\]

Ví dụ `N_q=16`:

- Query chạm 1 shard: `F=1/16=6,25%`.
- Query chạm 4 shard: `F=4/16=25%`.
- Query chạm 16 shard: `F=16/16=100%`.

Mẫu số nên là số shard có thể chứa dữ liệu của collection theo topology, **không phải tổng số replica member hoặc server vật lý của cluster**.

Một phép đo đơn giản còn cần ghi rõ ở mức nào:

- Số shard router định gửi request.
- Số shard thực sự chạy query.
- Số shard trả kết quả.
- Số replica tham gia consistency/read concern.
- Số chunk/range có liên quan.

Chúng không đồng nhất.

## 5. Một shard chạm nhưng một triệu document vẫn tệ

Giả sử query chỉ nhắm Shard A nhưng không có index phù hợp:

~~~text
shardsTouched = 1
documentsExamined = 10.000.000
documentsReturned = 1
~~~

Điều này tốt về routing nhưng tệ về local execution.

Ngược lại:

~~~text
shardsTouched = 16
documentsExamined tổng = 16
documentsReturned = 1
~~~

Nếu 16 shard cùng chạy index lookup nhẹ, tổng docs examined thấp nhưng vẫn cần 16 network roundtrips/công việc theo fan-out.

Cần dùng hai trục:

1. **Router efficiency:** có loại bỏ được shard không cần thiết?
2. **Local plan efficiency:** mỗi shard scan bao nhiêu, sort/merge ra sao?

Một index rất tốt **không tự** làm query targeted nếu thiếu shard-key predicate.

## 6. Query shape: đơn vị phân tích quan trọng

Không thể chứng minh shard key chỉ bằng một câu query có dữ liệu đẹp.

Ví dụ:

~~~javascript
db.orders.find({ tenantId: "t-001", orderId: "o-100" });
db.orders.find({ tenantId: "t-002", orderId: "o-200" });
~~~

Hai query thuộc cùng dạng: `GetOrderByTenantAndId`.

Nhưng:

~~~javascript
db.orders.find({
  tenantId: "t-001",
  status: "PENDING"
}).sort({ createdAt: -1 }).limit(20);
~~~

thuộc dạng `ListPendingOrdersByTenant`.

**Query shape** bao gồm cấu trúc filter, sort, projection, limit, aggregation và access path. Trong phân tích, nên loại bỏ giá trị cụ thể, giữ cấu trúc và chia thêm theo kích thước tenant/khoảng thời gian nếu chúng làm fan-out thay đổi.

## 7. Lập bảng workload thực tế

Giả sử hệ Order có các query shapes:

| Mã | Mục đích | Tỷ trọng read | Điều kiện |
|---|---|---:|---|
| Q1 | Lấy một Order | 60% | `tenantId + orderId` |
| Q2 | Xem Order mới nhất | 20% | `tenantId + createdAt range` |
| Q3 | Xem Order đang chờ | 10% | `tenantId + status` |
| Q4 | Báo cáo xuyên tenant | 7% | `status + createdAt range` |
| Q5 | Lịch sử theo Customer | 3% | `tenantId + customerId` |

Tổng tỷ trọng:

\[
60\%+20\%+10\%+7\%+3\%=100\%
\]

**Đây là workload minh họa**, không phải số liệu từ một hệ production cụ thể.

Bảng thực tế còn nên ghi:

- Read/write QPS và độ biến thiên theo giờ.
- P95/P99 latency yêu cầu cho từng shape.
- Số document trả về và kích thước kết quả.
- Dữ liệu thuộc tenant nhỏ/vừa/lớn.
- Query được gọi từ API nào và có shard key không.
- Những query xuyên tenant nào cần thiết.
- Update, delete, upsert và transaction liên quan.
- Sort, grouping, lookup, pagination.
- Thời gian và tốc độ tăng trưởng dữ liệu.

Tần suất query là một yếu tố, nhưng query hiếm có thể tiêu thụ tài nguyên rất lớn.

## 8. Bảng workload phải phản ánh đường API thật

Một endpoint:

~~~http
GET /tenants/t-001/orders/o-100
~~~

cung cấp cả `tenantId` và `orderId`.

Một endpoint khác:

~~~http
GET /orders/o-100
~~~

chỉ có `orderId`. Nếu shard key yêu cầu tenantId, endpoint thứ hai không tự có thông tin định tuyến.

Giải pháp tùy hệ:

- Buộc request có tenant trong ngữ cảnh authenticated.
- Có directory lookup `orderId -> tenantId`.
- Thiết kế shard key theo orderId nếu đó là đường truy vấn chính.
- Chấp nhận fan-out và giới hạn chi phí.
- Xây read model cho đường tra cứu riêng.

Không được giả định tất cả API luôn có tenantId chỉ vì dữ liệu có field đó. Đồng thời, có tenantId trong shard key **không thay thế authorization**: tenantId dùng để định tuyến vẫn phải được kiểm tra bằng context tin cậy.

## 9. Khóa A: hash theo orderId

Giả sử một collection được sharded theo một hashed key:

~~~javascript
// Mẫu minh họa MongoDB, cần tạo index/topology phù hợp.
sh.shardCollection("shop.orders", {
  orderId: "hashed"
});
~~~

Với query equality theo `orderId`, router có thể xác định hash và nhắm một shard thích hợp.

Ưu điểm:

- Point lookup theo Order ID dễ định tuyến.
- Order ID có phân phối đa dạng có thể giúp phân tán write.
- Không cần tenantId cho một số đường tìm kiếm bằng ID.

Hạn chế:

- List Order theo tenant nhưng không có orderId thường chạm nhiều shard.
- Thống kê theo tenant có thể trở thành cross-shard aggregation.
- Tenant-local transaction/unique rule cần xem lại.
- Range theo orderId gốc không có cùng tính chất pruning như range key vì hash không bảo toàn thứ tự.
- Vẫn phải có tenant authorization ở API.

Một hashed key có thể rất tốt cho point lookup mà không hợp workload danh sách.

## 10. Khóa B: hash theo tenantId

Ứng viên:

~~~javascript
sh.shardCollection("shop.orders", {
  tenantId: "hashed"
});
~~~

Với shard key đơn trường dạng hashed, toàn bộ document có cùng tenantId có cùng giá trị shard key đã hash, nên có thể tập trung vào một miền định tuyến.

Ưu điểm:

- Query có tenantId equality thường targeted một shard.
- Tenant list và các thao tác tenant-local thuận lợi.
- Với nhiều tenant kích thước tương đương, hash có thể phân phối khá đều.

Rủi ro:

- Một tenant lớn có thể đổ rất nhiều dữ liệu và write lên một shard.
- Tỷ lệ traffic theo tenant có thể rất lệch dù có hàng triệu tenant.
- Cross-tenant report vẫn phải scatter.
- Không thể tự chia tải một tenant “whale” qua nhiều shard chỉ bằng hash tenantId đơn trường.

**Định tuyến tốt không tự chứng minh cân bằng tải.**

## 11. Khóa C: tenant + hash orderId

Một compound hashed shard key, nếu phiên bản và topology hỗ trợ, có thể được thiết kế:

~~~javascript
sh.shardCollection("shop.orders", {
  tenantId: 1,
  orderId: "hashed"
});
~~~

Cần xác minh yêu cầu index, tính hợp lệ của compound hashed shard key và unique index theo phiên bản MongoDB triển khai.

Ưu điểm:

- Query equality có đầy đủ tenantId và orderId có thể target chính xác.
- Các order khác nhau trong cùng tenant có thể được phân vào nhiều chunk/shard nếu placement cho phép.
- Có thể giảm khả năng tenant lớn bị dồn vào một shard.

Đánh đổi:

- Query chỉ có tenantId có thể chạm **nhiều shard** nếu các chunk của tenant trải nhiều nơi.
- List Orders theo createdAt có thể cần merge.
- Unique constraint trên các business keys khác cần xem giới hạn sharding.
- Cần đo mức fan-out ở tenant lớn, không dựa vào tenant thử nghiệm có ít document.

## 12. Khóa D: tenant + thời gian

Ứng viên dạng range:

~~~javascript
sh.shardCollection("shop.orders", {
  tenantId: 1,
  createdAt: 1
});
~~~

Một query:

~~~javascript
db.orders.find({
  tenantId: "t-001",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
});
~~~

có thể giúp router loại bỏ chunk không giao khoảng tenant/time phù hợp.

Nhưng:

- Query tenantId đơn lẻ có thể chạm nhiều shard nếu tenant trải nhiều chunk thời gian.
- Point lookup bằng tenantId + orderId thiếu điều kiện createdAt có thể chạm nhiều shard.
- Write tăng dần theo thời gian có thể gây hot range ở chunk hiện tại.
- Range rất rộng có thể chạm nhiều shard.
- Local index vẫn cần phục vụ filter/sort.

Đừng cho rằng prefix tenantId **tự bảo đảm** single-shard query.

## 13. Vì sao prefix của shard key không bằng một shard?

Với `{tenantId:1, createdAt:1}`, một tenant có thể có các chunk:

~~~text
Shard A: tenant=t-001, year 2024
Shard B: tenant=t-001, year 2025
Shard C: tenant=t-001, year 2026
~~~

Query:

~~~javascript
db.orders.find({
  tenantId: "t-001"
});
~~~

có thể chạm A, B và C nếu không có điều kiện time range.

Query thêm `createdAt` giới hạn trong một tháng có thể loại bớt chunk.

**Có phần đầu shard key giúp pruning trong một số trường hợp, nhưng số shard thật phụ thuộc range bounds và placement**.

## 14. Range so với hash

| Khía cạnh | Range key | Hashed key |
|---|---|---|
| Full equality | Có thể targeted | Có thể targeted |
| Range trên giá trị gốc | Có cơ hội pruning theo khoảng | Không bảo toàn thứ tự gốc |
| Giá trị tăng đơn điệu | Có nguy cơ hot range | Hash có thể phân tán tốt hơn |
| Query theo thời gian | Có thể thuận lợi | Có thể scatter |
| Giá trị cực phổ biến | Có thể tập trung nếu key đơn | Cũng có thể tập trung nếu cùng hash key |
| Compound prefix | Phụ thuộc chunk bounds | Phụ thuộc cấu trúc và placement |
| Unique/index semantics | Theo quy tắc engine | Theo quy tắc engine, có hạn chế riêng |

Không có một lựa chọn toàn thắng. Phải đo trên workload và thống kê giá trị thật.

## 15. So sánh bằng bảng fan-out giả định

Giả sử có 16 shard. Để minh họa phép đánh giá, ta **giả định** số shard bị chạm của từng ứng viên:

| Shape | Tỷ trọng | A: hash order | B: hash tenant | C: tenant+hash order | D: tenant+time |
|---|---:|---:|---:|---:|---:|
| Q1 — Get Order | 60% | 1 | 1 | 1 | 2 |
| Q2 — Recent Orders | 20% | 16 | 1 | 4 | 2 |
| Q3 — Pending Orders | 10% | 16 | 1 | 4 | 2 |
| Q4 — Global Report | 7% | 16 | 16 | 16 | 16 |
| Q5 — Customer History | 3% | 16 | 1 | 4 | 2 |

**Số liệu này do bài học đặt ra để tính toán, không phải explain output hoặc benchmark thực tế.** Trong sản phẩm thật, các ô có thể đổi theo query shape, tenant, chunk placement và balancer.

Bảng minh họa những trade-off:

- A tốt cho Get Order nhưng kém ở tenant scans.
- B giảm fan-out của các query tenant-local.
- C cho phép nhiều query tenant-only chạm vài shard trong khi Get Order vẫn targeted.
- D thuận lợi cho một số time-range nhưng Get Order thiếu createdAt không nhất thiết targeted.

## 16. Tính số shard trung bình có trọng số

Gọi `p_i` là tỷ lệ request thuộc shape i và `s_i` là số shard bị chạm. Tính:

\[
\overline S_w=\sum_i p_i s_i
\]

Với tổng `p_i=1`.

Ứng viên A:

\[
0.60(1)+0.20(16)+0.10(16)+0.07(16)+0.03(16)=7.00
\]

Ứng viên B:

\[
0.60(1)+0.20(1)+0.10(1)+0.07(16)+0.03(1)=2.05
\]

Ứng viên C:

\[
0.60(1)+0.20(4)+0.10(4)+0.07(16)+0.03(4)=3.04
\]

Ứng viên D:

\[
0.60(2)+0.20(2)+0.10(2)+0.07(16)+0.03(2)=2.98
\]

Nếu chỉ tối ưu **fan-out theo các giả định trong bảng**, B có điểm thấp nhất.

Nhưng B có thể rất tệ nếu một tenant chiếm 70% write và bị dồn vào một shard. Vì thế **không chọn khóa cuối cùng chỉ bằng trung bình số shard**.

## 17. Tỷ lệ fan-out và cost-weighted fan-out

Với 16 shard:

\[
\overline F_w=\frac{\overline S_w}{16}
\]

Ứng viên B có `2.05/16≈12.81%` trong ví dụ.

Tuy nhiên hai query cùng chạm bốn shard có thể khác nhau rất lớn:

- Query 1: mỗi shard IXSCAN một index entry.
- Query 2: mỗi shard scan 10 triệu document, sort rồi truyền dữ liệu lớn.

Vì vậy có thể dùng một metric chi phí bổ sung:

\[
\text{ExpectedCost}=\sum_i p_i \, c_i
\]

Trong đó `c_i` có thể là CPU time, bytes scanned, consumed units hoặc chi phí được định nghĩa rõ của shape i.

Không cộng tùy tiện CPU ms và network bytes thành một điểm nếu chưa chuẩn hóa và giải thích trọng số.

## 18. Vì sao p95/p99 và heavy queries cần được đo riêng?

Giả sử 99% request chạm một shard, 1% chạm 32 shard:

\[
\overline S=0.99(1)+0.01(32)=1.31
\]

Trung bình 1,31 trông đẹp, nhưng 1% query xuyên 32 shard vẫn có thể làm:

- P99 latency cao.
- Router/merger dùng nhiều RAM.
- Mọi shard mất CPU cho báo cáo.
- Cache bị đẩy ra.
- Network traffic tăng đột biến.
- Query khác trên những shard bị kéo chậm.

Cần đo:

- P50/P95/P99 `shardsTouched`.
- Fan-out theo shape.
- Fan-out theo tenant nhỏ/vừa/whale.
- Local docs/keys examined.
- CPU/IOPS/network per shard.
- Latency p95/p99 và timeout.
- Số concurrent scatter-gather queries.

**Một con số trung bình không thể thay thế biểu đồ phân bố.**

## 19. Index không thay shard key

Giả sử shard key là `tenantId` và trên mỗi shard có index:

~~~javascript
db.orders.createIndex({
  status: 1,
  createdAt: -1
});
~~~

Query:

~~~javascript
db.orders.find({
  status: "PENDING"
}).sort({ createdAt: -1 }).limit(20);
~~~

Nếu không có tenantId, router vẫn có thể phải tìm kết quả ở nhiều shard. Index giúp **mỗi shard** tìm những Order phù hợp nhanh hơn; index không tự biết shard nào có kết quả.

Ngược lại, một query targeted một shard vẫn có thể chậm nếu không có index phù hợp và phải collection scan.

Đánh giá phải chứa cả hai phần:

1. **Shard pruning:** bao nhiêu shard thực hiện request?
2. **Local plan:** trên shard đó có IXSCAN hay COLLSCAN, examined/returned ratio thế nào?

## 20. Các dạng truy vấn có thể mở rộng fan-out

Một số cấu trúc cần kiểm tra kỹ:

- Filter thiếu shard key.
- Filter chỉ có prefix của compound shard key.
- Range rất rộng.
- `$in` với nhiều giá trị khóa.
- `$or` có nhánh không ràng buộc shard key.
- Filter bằng expression/biến đổi field mà router không suy được key.
- Aggregation `$match` bị đặt sau stage không được push down như kỳ vọng.
- `$lookup` tới collection ở shard khác.
- Query sort/limit toàn hệ.
- Các truy vấn cập nhật hoặc upsert thiếu điều kiện routing phù hợp.

Ví dụ:

~~~javascript
db.orders.find({
  orderId: { $in: ["o-1", "o-2", "o-3"] }
});
~~~

Ba giá trị có thể map vào một, hai hoặc ba shard. **Số phần tử `$in` không tự bằng số shard chạm**.

Ví dụ:

~~~javascript
db.orders.find({
  $or: [
    { tenantId: "t-001", orderId: "o-1" },
    { status: "PENDING" }
  ]
});
~~~

Nếu một nhánh không ràng buộc shard key, optimizer có thể phải xem nhiều shard. Cần kiểm tra explain thực tế thay vì suy từ nhánh đầu.

## 21. Đảm bảo kiểu dữ liệu khóa nhất quán

Hai filter có vẻ chỉ khác hình thức nhưng không cùng nghĩa:

~~~javascript
{ tenantId: "42" }
{ tenantId: 42 }
{ tenantId: null }
{ tenantId: { $exists: false } }
~~~

String, numeric, null và missing có semantics riêng trong MongoDB.

Một schema không thống nhất có thể:

- Làm một số query không match dữ liệu đã lưu.
- Tạo đường fallback scatter do API thiếu khóa.
- Làm index/routing khó dự đoán.
- Tăng rủi ro tenant isolation.
- Phá các assumption của phép đo cardinality.

Nên định nghĩa cách chuẩn hóa `tenantId`, `orderId`, time bucket, kiểu dữ liệu BSON và chính sách missing/null.

## 22. MongoDB mongos: quan sát routing đúng nơi

Trong MongoDB sharded cluster, client thường gửi truy vấn tới `mongos`. Router dùng shard-key metadata và chunk placement để quyết định shard thực hiện.

~~~text
Application
    |
  mongos
    |
    +-- Shard A (chunks...)
    +-- Shard B (chunks...)
    +-- Shard C (chunks...)
    +-- Shard D (chunks...)
~~~

Nếu chạy giải thích query trực tiếp ở một node thành viên của một shard, có thể chỉ thấy local plan, không phải bức tranh fan-out tại router. Vì vậy **thử nghiệm routing phải thực hiện qua đúng đường truy cập sharded cluster**.

Dữ liệu placement có thể thay đổi khi chunk migrate, collection reshard hoặc topology điều chỉnh.

## 23. MongoDB explain: bước quan sát quan trọng

Trên một cluster đã sharded, thử:

~~~javascript
const query = {
  tenantId: "t-001",
  orderId: "o-100"
};

const explained = db.orders
  .find(query)
  .explain("executionStats");

printjson(explained);
~~~

So với query tenant-only:

~~~javascript
const explained = db.orders
  .find({
    tenantId: "t-001",
    status: "PENDING"
  })
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");

printjson(explained);
~~~

Và aggregation:

~~~javascript
const explained = db.orders
  .explain("executionStats")
  .aggregate([
    {
      $match: {
        tenantId: "t-001",
        createdAt: {
          $gte: ISODate("2026-11-01T00:00:00Z")
        }
      }
    },
    {
      $group: {
        _id: "$status",
        total: { $sum: 1 }
      }
    }
  ]);

printjson(explained);
~~~

Các ví dụ là cách **tạo bằng chứng**, không phải lời khẳng định output luôn có một trường cố định. Hình dạng explain khác theo MongoDB version, classic/SBE execution, sharded plans và các loại pipeline.

## 24. Đọc những gì từ explain?

Khi xem explain, cần xác định:

- Những shard nào xuất hiện trong execution plan.
- Query nhắm một shard, một tập subset hay tất cả shard.
- Có merge stage phía router hay không.
- Filter đã được push down hay chưa.
- `totalKeysExamined` và `totalDocsExamined` nếu output có.
- `nReturned` và các execution stats khả dụng.
- Local plan là IXSCAN hay COLLSCAN.
- Có sort, limit hoặc group được thực hiện từng shard/merge.
- Có bước truy cập collection khác trong `$lookup` không.
- Những shard được nhắm có thay đổi giữa tenant nhỏ và lớn không.

Explain có thể chứa cấu trúc theo shard, stage `SHARD_MERGE` hoặc stage tương đương, nhưng **không nên viết parser phụ thuộc một tên field duy nhất rồi áp cho mọi phiên bản**.

### Ví dụ một record đo chuẩn hóa

Đây là JSON **do nhóm ứng dụng tự xây từ explain/telemetry**, không phải format MongoDB công bố:

~~~json
{
  "queryShape": "GetOrderByTenantAndId",
  "topologyShardCount": 16,
  "targetedShardIds": ["shard-a"],
  "shardsTouched": 1,
  "docsExamined": 1,
  "nReturned": 1
}
~~~

Ví dụ query rộng:

~~~json
{
  "queryShape": "CrossTenantReport",
  "topologyShardCount": 16,
  "targetedShardIds": [
    "shard-a", "shard-b", "shard-c", "shard-d"
  ],
  "shardsTouched": 4,
  "docsExamined": 80000,
  "nReturned": 125
}
~~~

Không tưởng rằng `targetedShardIds` là field có sẵn trong mọi bản explain. Đó là field trong **schema ghi nhận do nhóm định nghĩa**.

## 25. Phân biệt số shard chạy và số shard trả dữ liệu

Giả sử một query tìm mã khách hàng:

~~~text
Shard A: không tìm thấy document
Shard B: không tìm thấy document
Shard C: tìm thấy một document
Shard D: không tìm thấy document
~~~

Nếu router đã gửi query tới cả bốn shard, kết quả:

~~~text
shardsTouched = 4
shardsWithMatches = 1
documentsReturned = 1
~~~

Đếm chỉ shard có kết quả rồi báo fan-out 1 là sai. Cũng không nên đếm số chunk mà truy vấn đi qua rồi báo đó là số shard.

## 26. Đếm theo stage với aggregation phức tạp

Một pipeline có thể:

1. Match từ một phần collection chính.
2. Group trong từng shard.
3. Merge ở router/merger.
4. Lookup collection phụ.
5. Sort và limit toàn bộ kết quả.

Nếu chỉ đếm shard của stage `$match` ban đầu, có thể bỏ qua fan-out của `$lookup` hoặc công việc trên collection khác.

Cần ghi rõ scope:

- Số shard của **collection chính**.
- Số shard của **tất cả collection liên quan**.
- Số subrequests của từng stage.
- Bytes trung gian truyền qua router.
- CPU/sort memory ở merge stage.

Trong các hồ sơ kỹ thuật, tránh công bố một con số `shardsTouched` chung nếu người đọc không biết cách tính.

## 27. Explain có phải là số liệu production không?

Không hoàn toàn. `explain` giúp thấy plan và execution trong tình huống thử nghiệm, nhưng chưa nói:

- Query shape được gọi bao nhiêu lần một ngày.
- Tỷ lệ tenant cực lớn.
- Load và concurrency của production.
- Chi phí cache miss.
- Mức độ shard migration trong ngày.
- P99 latency khi một shard chậm.
- Tỷ lệ lỗi/throttling.
- Mức độ query của các API khác ảnh hưởng lẫn nhau.

**Kết hợp explain với traffic telemetry và load testing** mới đủ đưa ra quyết định.

### Đo ở những thời điểm nào?

- Bình thường khi balancer ổn định.
- Giờ cao điểm.
- Sau khi dữ liệu tăng trưởng.
- Khi tenant lớn mới xuất hiện.
- Sau chunk migration/rebalance.
- Sau thay đổi index/query builder.
- Sau nâng phiên bản MongoDB nếu explain format hoặc plan đổi.

Một query tenant prefix có thể chạm hai shard hôm nay nhưng ba shard ngày mai do chunk placement.

## 28. Logs, profiler và correlation ID

Nếu hệ quản trị và quyền vận hành cho phép, có thể kết hợp:

- Query profiler/slow query logs.
- Trace ở API gateway.
- Router-side telemetry.
- Shard-side logs/tracing.
- Query shape hoặc query hash.
- Correlation ID cho request.

Ví dụ mongosh có `comment` để gắn dấu vết cho operation khi được hỗ trợ:

~~~javascript
db.orders.find({
  tenantId: "t-001",
  status: "PENDING"
}).comment("shape=ListPendingOrders;trace=example-001");
~~~

Nhưng **driver command monitoring ở client thường quan sát command tới mongos**, không tự lộ mọi subrequest nội bộ tới từng shard. Muốn đếm shards thật từ production cần nguồn telemetry thích hợp hoặc đối chiếu explain.

Profiler có overhead và có thể ghi thông tin nhạy cảm. Không bật sampling quá cao hoặc log nguyên payload cá nhân mà không tuân thủ quy định bảo vệ dữ liệu.

## 29. Một bảng kết quả đo có thể tái hiện

| Trường | Ví dụ | Cách hiểu |
|---|---|---|
| `timestamp` | 2026-11-14T09:00:00Z | Mốc topology |
| `shape` | GetOrder | Nhóm query |
| `keyCandidate` | TenantHash | Phương án |
| `tenantClass` | Whale | Phân nhóm dữ liệu |
| `eligibleShards` | 16 | Mẫu số |
| `shardsTouched` | 4 | Fan-out |
| `shardIds` | a,b,c,d | Bằng chứng |
| `docsExamined` | 12000 | Local cost |
| `keysExamined` | 12500 | Local index work |
| `nReturned` | 20 | Kết quả |
| `durationMs` | 35 | Latency đo |
| `bytesReturned` | 48000 | Network result |
| `topologyVersion` | snapshot-17 | Đối chiếu placement |

Không phải tất cả các trường đều do explain trực tiếp cung cấp. Một vài giá trị có thể cần profiler/tracer/counter khác. Nếu không quan sát được, để trống và nêu hạn chế thay vì bịa số.

## 30. Những lỗi thường gặp khi đo fan-out

- Đếm số node trong connection pool là số shard.
- Đếm số replica ACK là số shard.
- Đếm số chunk thay vì số shard.
- Chỉ đếm shard trả document.
- Đếm retry cùng shard thành nhiều shard khác nhau mà không phân biệt operation.
- Dùng explain local ở shard thành fan-out toàn cluster.
- Đếm số client command rồi suy số subrequest phía router.
- Dùng query ví dụ khác với query ORM/driver thực sự gửi.
- Bỏ qua `$lookup`, merge và read model phụ.
- Đo sau khi cache hit mà gọi đó là read database.
- Trộn shard của collection A và replica của collection B.
- So hai ứng viên khi số shard/topology/dataset khác nhau quá lớn.

Mục tiêu là **một cách đếm có định nghĩa, kiểm chứng và lặp lại được**, không phải một con số dễ lấy nhất.

## 31. Đừng bỏ các write paths

Shard key phải phục vụ cả ghi:

- Insert document mới.
- Update theo full shard key.
- Update chỉ có ID nghiệp vụ.
- Delete theo tenant và ID.
- Bulk insert nhiều tenant.
- Upsert với filter không đủ key.
- Transaction nhiều document.
- Unique check.
- Event-driven projection update.

Trong MongoDB, thao tác update/delete/upsert không có đủ shard-key information có những giới hạn và hành vi khác nhau tùy command/phiên bản. Không được tự giả định mọi write thiếu key đều được broadcast đúng và an toàn.

Đặc biệt một batch 1000 Order có thể chạm nhiều shard dù mỗi insert riêng là targeted. Cần ghi rõ đang đo **fan-out một document operation hay cả batch**.

## 32. Atomic scope và cross-shard transaction

Nếu Order nằm Shard A còn Inventory nằm Shard B, một nghiệp vụ tạo Order và trừ stock có thể cần transaction hoặc workflow, tùy engine và mô hình aggregate.

Một key tập trung mọi entity của tenant vào một shard có thể giảm một số cross-shard operation, nhưng có nguy cơ tenant lớn thành điểm nóng.

Đánh giá phải xét:

- Invariant được bảo vệ ở document nào?
- Transaction/cross-shard commit có được hỗ trợ không?
- Latency và abort/retry rate của transaction.
- Unique constraint có đủ phạm vi không?
- Idempotency khi timeout.
- Cần outbox/saga cho external side effects không?

**Fan-out thấp không tự chứng minh đúng nghiệp vụ**, và fan-out cao không tự có nghĩa transaction sai; phụ thuộc guarantees của engine.

## 33. Global sort và pagination

Query:

~~~javascript
db.orders.find({
  status: "PENDING"
}).sort({ createdAt: -1 }).limit(20);
~~~

Nếu không có shard key trong filter, router có thể hỏi tất cả shard để xác định top 20 toàn hệ. Từng shard có index tốt vẫn có thể cần gửi ứng viên về merge stage.

Một `limit(20)` không đồng nghĩa chỉ có 20 shard hoặc 20 documents examined.

Deep `skip` có thể đặc biệt tốn kém. Keyset/cursor pagination dựa trên `createdAt` và tie-breaker có thể cải thiện một số query, nhưng **không tự giảm fan-out** nếu routing vẫn thiếu khóa.

## 34. Báo cáo toàn hệ nên là read model riêng khi cần

Một báo cáo mỗi phút tính tổng Order từ mọi tenant sẽ có tính chất xuyên shard nếu dữ liệu nằm trải trên các shard.

Thay vì làm hỏng toàn bộ shard key OLTP để tối ưu một báo cáo, có thể:

- Tạo materialized aggregate theo ngày/tenant.
- Dùng outbox/CDC stream để cập nhật counter.
- Chuyển analytics workload sang hệ OLAP/warehouse.
- Chạy batch theo lịch tránh giờ cao điểm.
- Định nghĩa freshness lag của read model.

Tuy nhiên read model bất đồng bộ có thể stale, và metric `dataAsOf` cần trung thực. Không dùng báo cáo eventual làm nguồn quyết định thanh toán hoặc tồn kho.

## 35. Phân bố dữ liệu và phân bố tải là hai bài toán

Giảm số shard mỗi query chạm có thể tập trung mọi request vào một shard nóng.

Cần đo hai nhóm:

**Data skew:** document count, storage bytes, index bytes, chunk/range placement theo shard.

**Traffic skew:** read QPS, write QPS, CPU, disk IOPS, network, queue depth, tail latency, replication lag và throttling theo shard.

Một chỉ số trực giác:

\[
\text{LoadSkewRatio}=
\frac{\max(\text{load per shard})}
{\operatorname{mean}(\text{load per shard})}
\]

Nếu một shard dùng 80% CPU, đa số shard khác chỉ dùng 10%, hệ đang có nguy cơ bottleneck dù mọi query đều targeted đẹp.

Tỷ lệ này cần tính theo time window và loại load. CPU 80% trong một burst ngắn không giống liên tục quá tải hàng giờ.

## 36. Cardinality cao nhưng một tenant vẫn có thể nóng

Giả sử có một triệu tenant:

~~~text
tenant-whale: 70% tổng write
999.999 tenant còn lại: 30% tổng write
~~~

Nếu shard key là hash `tenantId` đơn trường, tenant-whale vẫn tương ứng một giá trị hash. Có thể xảy ra hot shard.

Cần đo:

- Distinct key count.
- Top-N heavy hitters.
- Số documents/bytes mỗi key.
- Read/write QPS mỗi key.
- Tốc độ tăng trưởng.
- Tính đơn điệu hoặc tương quan của key với thời gian.
- Tần suất cập nhật cùng một document.
- Kích thước tenant lớn nhất so với capacity một shard.

**Cardinality không thay thế phân phối tần suất và request rate**.

## 37. Một số cách giảm hot shard

| Phương án | Lợi ích | Đánh đổi |
|---|---|---|
| Hash orderId | Chia write cho các Order khác nhau | Tenant-only scan nhiều shard |
| Tenant + hash orderId | Phân tán Order của tenant lớn | Tenant query phải merge |
| Tenant + time bucket | Có thể giới hạn time range | Bucket hiện tại có thể nóng |
| Tách tenant lớn | Cô lập capacity | Routing/vận hành phức tạp |
| Read model per-tenant | Tenant list nhanh | Tăng chi phí đồng bộ và stale |
| Phân mảnh counter | Giảm contention | Tổng hợp và invariant tổng thể khó |
| Queue theo entity owner | Bảo vệ thứ tự ghi | Tăng latency/độ phức tạp |

Không nên chọn suffix ngẫu nhiên chỉ để chia tải nếu mọi query phải tìm lại trên tất cả bucket. Cần biết **cách xác định bucket ở đường đọc**.

## 38. Zone sharding, vị trí và tính tuân thủ

Nếu dữ liệu tenant phải nằm trong một region hoặc zone do chính sách, shard key còn có yêu cầu locality.

Điểm cần chứng minh:

- Placement có đúng vùng được phép?
- Một query targeted có phải đi xuyên WAN không?
- Mất một zone có làm mất toàn bộ replica của shard không?
- Có policy tenant migration không?
- Cross-region report được phép xử lý dữ liệu ở đâu?
- Cache/search projection có sao dữ liệu ra vùng không phù hợp không?

Một key cho fan-out thấp nhất có thể vẫn sai nếu phá yêu cầu data residency hoặc làm latency rất cao do shard mục tiêu quá xa.

## 39. Thí nghiệm phải công bằng

Khi so các khóa ứng viên, chuẩn bị:

1. Cùng query catalog và phân bố tần suất.
2. Dataset có quy mô và skew đại diện.
3. Cùng số shard hoặc mô hình so sánh được.
4. Index hợp lý cho mỗi ứng viên, ghi chi phí index.
5. Tình trạng balancer/chunk placement có thể quan sát.
6. Cùng concurrency, cache warm/cold policy và máy đo.
7. Explain cho tenant nhỏ/vừa/whale.
8. Thử equality, range, `$in`, `$or` và aggregation.
9. Đo storage/QPS/CPU/latency theo shard.
10. Test tăng trưởng, shard chậm và chunk migration.
11. Tính kết quả có trọng số theo workload.
12. Ghi những giới hạn/giả định chưa xác minh.

Không nên lấy latency trên 10.000 document của ứng viên A so với 100 triệu document của ứng viên B rồi tuyên bố A tốt hơn.

## 40. Cần phân nhóm tenant để không bị trung bình lừa

Một kết quả minh họa:

~~~text
Small tenants: p95 shardsTouched = 1
Medium tenants: p95 shardsTouched = 2
Whale tenants: p95 shardsTouched = 12
~~~

Kết luận “truy vấn theo tenant luôn một shard” sẽ sai.

Nên phân nhóm tenant theo bytes, Order count và QPS:

- P50 tenant size.
- P90/P99 tenant size.
- Top 1% tenant theo write rate.
- Tenant đang tăng trưởng nhanh.
- Tenant có lịch sử nhiều năm.
- Tenant có burst write.
- Tenant vừa được migrate.

Thống kê fan-out cần đi kèm **độ lớn và mức tải nhóm được thử**.

## 41. Hai nhóm bằng chứng để phê duyệt khóa

### Bằng chứng routing

- Query shapes chính đã được liệt kê.
- Có `explain` cho mỗi shape với mẫu giá trị đại diện.
- Có số shard targeted/executing theo định nghĩa.
- Biết behavior khi dùng thiếu shard key.
- Biết fan-out của range, `$in`, `$or` và global aggregation.
- Có dữ liệu về query hiếm nhưng đắt.

### Bằng chứng capacity và correctness

- Data bytes, QPS và hot shard nằm trong khả năng cho phép.
- Không có tenant/key quá nóng ngoài kế hoạch xử lý.
- p95/p99 latency và lỗi đạt mục tiêu.
- Unique constraints và tenant isolation còn đúng.
- Transaction/cross-shard operation có chi phí chấp nhận.
- Rebalance/failover không phá SLO quá mức.
- Có lộ trình reshard khi workload thay đổi.

Nếu chỉ có routing, có thể chọn một key tạo hotspot. Nếu chỉ có cân bằng hash, có thể chọn key khiến mọi nghiệp vụ danh sách thành scatter-gather.

## 42. Lập hồ sơ quyết định theo dữ liệu

Một ADR hoặc decision record có thể ghi:

~~~yaml
collection: orders
topic: shardKeyDecision
sourceOfTruth: orderDocuments
numberOfShardsInTest: 16
workload:
  GetOrder: 60
  ListRecentOrders: 20
  PendingOrders: 10
  CrossTenantReport: 7
  CustomerHistory: 3
candidate: "tenantId + hashed(orderId)"
evidenceRequired:
  - explainForRepresentativeQueryShapes
  - fanoutByTenantSegment
  - p95p99ReadLatency
  - writeQpsAndCpuByShard
  - topHeavyTenants
  - docsAndKeysExamined
  - uniqueConstraintReview
  - transactionScopeReview
  - failureAndRebalanceTest
tradeoffs:
  - tenantOnlyQueriesMayTouchMultipleShards
  - globalReportsRequireReadModel
  - pointLookupNeedsTenantAndOrderId
mitigations:
  - precomputedAnalytics
  - boundedDateRangeForLists
  - monitoringOfHotTenants
  - reshardingRunbook
status: proposed
~~~

YAML này là **tài liệu kiến trúc**, không phải cấu hình tự được database thực thi. Các giá trị đo và ngưỡng chấp nhận phải đến từ thí nghiệm và telemetry thực tế.

## 43. DynamoDB: logical partition không phải MongoDB shard

DynamoDB dùng partition key và có thể thêm sort key. Với key cụ thể, `GetItem`/`Query` có thể xác định item collection phù hợp.

Nhưng:

- Physical partitions được dịch vụ quản lý.
- Một logical partition key không phải tên một physical shard công khai.
- Hot partition keys có thể ảnh hưởng capacity/throttling.
- Application bucket fan-out là số truy vấn tới các PK khác nhau, không tự bằng số physical partitions bị chạm.

Ví dụ single-tenant key:

~~~text
PK = TENANT#t-001
SK = ORDER#2026-11-14#o-100
~~~

Một query theo tenant dễ diễn đạt. Nhưng tenant quá lớn có thể cần bucket:

~~~text
PK = TENANT#t-001#BUCKET#2026-11
SK = ORDER#o-100
~~~

Khi lấy dữ liệu 12 tháng, ứng dụng có thể phải Query 12 bucket rồi merge. Đó là fan-out **theo logical key/request** chứ không phải 12 physical partitions được xác nhận.

### Cách chứng minh trong DynamoDB

Đo những gì API hỗ trợ:

- `ConsumedCapacity` khi request được cấu hình trả.
- `ScannedCount` so với `Count`.
- QPS/latency theo access pattern.
- Số PK/bucket được query cho mỗi API.
- Throttling và hot key diagnostics.
- Chi phí GSI.
- RCU/WCU hoặc capacity units theo cơ chế dịch vụ.

Nếu không có API báo số physical partitions touched, phải ghi **không quan sát trực tiếp được**, thay vì bịa con số.

## 44. Cassandra: token-aware routing

Trong Cassandra, partition key dùng để tính token và đặt dữ liệu trên replica theo replication strategy.

Ví dụ CQL:

~~~sql
CREATE TABLE orders_by_tenant (
  tenant_id text,
  bucket text,
  created_at timestamp,
  order_id text,
  status text,
  PRIMARY KEY ((tenant_id, bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (
  created_at DESC,
  order_id ASC
);
~~~

Một query có đầy đủ partition key:

~~~sql
SELECT *
FROM orders_by_tenant
WHERE tenant_id = 't-001'
  AND bucket = '2026-11';
~~~

sẽ được route theo token-aware driver/protocol phù hợp.

Nếu lấy 12 bucket, ứng dụng cần nhiều partition queries. Cần phân biệt:

- **Logical partition keys** được đọc.
- **Replica nodes** tham gia theo consistency level.
- **Coordinator requests** và network hops.
- **Physical nodes** có dữ liệu theo token range.

RF=3 và read CL=QUORUM có thể cần nhiều replica phục vụ một partition, nhưng **không nên gọi số replica đó là số shard dữ liệu độc lập**.

### Bẫy Cassandra

- Query thiếu partition key thường không phù hợp với mô hình truy cập và có thể bị giới hạn.
- `ALLOW FILTERING` không thay thế thiết kế access pattern hiệu quả.
- Partition quá lớn tạo hotspot/read/compaction pressure.
- Bucket quá nhỏ làm API phải fan-out nhiều partitions.
- Tracing và latency metrics giúp phân tích routing, nhưng không có field chung `shardsTouched` cho mọi CQL query.

## 45. Elasticsearch/OpenSearch: search shards

Trong các search engines phân tán, search request có thể được gửi tới nhiều search shards. Routing khi index/query có thể giảm tập shard trong những trường hợp phù hợp.

Công cụ như shard-selection API hoặc profiling theo engine/version giúp điều tra:

- Index và shard nào nằm trong query.
- Query tới alias/multiple indices mở rộng thế nào.
- Có routing value trùng với giá trị đã dùng lúc index không.
- Phân bố query latency và merge.
- Replica nào được chọn phục vụ read.

Nhưng search shards **không phải** MongoDB shards của source. Đừng cộng lẫn số shard từ hai hệ vào một metric không định nghĩa rõ.

Search index còn có độ trễ đồng bộ từ nguồn; routing tốt không tự đảm bảo freshness.

## 46. Khi tăng shards, workload có tiếp tục tốt?

Một lựa chọn shard key cần được thử khi scale từ 4 lên 16 hoặc 32 shards.

Có thể gặp:

- Point lookup vẫn một shard.
- Tenant scan trước một shard nay chạm nhiều shard do chunk splitting.
- Global report từ 4 shards tăng lên 32 shards.
- Hash distribution cân bằng hơn nhưng transaction/sort merge đắt hơn.
- Hot tenant vẫn dồn vào một shard nếu key đơn là tenantId.

Cần đo **fan-out theo quy mô N** chứ không chỉ một N cố định. Một query có fan-out=4 trên N=4 và vẫn 4 trên N=32 là hai kết quả rất khác về tỷ lệ, nhưng chi phí thực cũng cần đo riêng.

## 47. Chunk migration và resharding

Khi chunk được chuyển từ Shard A sang Shard B, router metadata và placement thay đổi. Một query shape có thể chạm tập shard khác theo thời điểm.

Lộ trình resharding có thể cần:

- Sao chép/backfill.
- Quản lý double-read/double-write theo cách được hỗ trợ.
- Điều chỉnh index/unique constraints.
- Theo dõi transaction retries.
- Điều chỉnh routing API.
- Đồng bộ CDC/search projections.
- Cutover và rollback có kiểm soát.

Không nên nghĩ “đổi shard key” là một thay đổi cấu hình tức thì, không chi phí. Một ADR tốt ghi rõ **điều kiện nào kích hoạt xem xét reshard**.

## 48. Fault testing và độ ổn định fan-out

| Tình huống | Điều cần kiểm tra |
|---|---|
| Một shard chậm | Scatter-gather p99 tăng bao nhiêu? |
| Một shard unavailable | Query targeted và multi-shard phản ứng ra sao? |
| Chunk migration | Query có retry, timeout hoặc route lại không? |
| Tăng số shard | Fan-out và capacity scale thế nào? |
| Whale tenant đột biến | Hot shard có vượt giới hạn? |
| Global report chạy đồng thời | Có ảnh hưởng traffic OLTP không? |
| Cross-shard transaction | Latency/abort rate có tăng không? |
| Event out-of-order | Read model có lùi version không? |
| GSI/index lag | Dữ liệu hiển thị và dữ liệu nguồn khác nhau thế nào? |

Chỉ thực hiện thử nghiệm gây lỗi ở môi trường được phép và có cơ chế cô lập. Cần ghi mốc topology, dataset, query shape và load để có thể tái hiện.

## 49. Một quy trình quyết định có thể kiểm chứng

~~~mermaid
flowchart TD
    A["Liệt kê query shapes + tần suất"] --> B["Đề xuất shard key ứng viên"]
    B --> C["Chuẩn bị dataset/topology đại diện"]
    C --> D["Explain: đo shard fan-out"]
    D --> E["Load test: latency và resource"]
    E --> F["Đo skew/hot keys"]
    F --> G{"Đạt invariant + SLO?"}
    G -->|"Đạt"| H["Ghi ADR, canary"]
    G -->|"Chưa"| I["Đổi key/index/read model"]
    I --> C
    H --> J["Theo dõi và đánh giá lại"]
~~~

Nếu báo cáo toàn hệ là query hiếm nhưng đắt, có thể chọn một read model chuyên biệt. Nếu tenant lớn gây hotspot, có thể chấp nhận fan-out tenant scans cao hơn để phân tán writes. Nếu point lookup quan trọng nhất, cần đảm bảo API luôn có đủ shard key.

Không có “key đẹp nhất” tách rời workload và mục tiêu nghiệp vụ.

## 50. Bài tập 1 — Đếm shard so với replica

Cluster có 8 shard, mỗi shard gồm ba replica. Một query được router gửi tới một shard và một replica member phục vụ đọc.

**Hỏi:** query chạm 1, 3 hay 8 shard?

**Đáp án gợi ý:** một shard. Ba là số replica member thuộc shard; tám là số shard toàn collection.

## 51. Bài tập 2 — Fan-out trung bình có trọng số

Cluster có 12 shard. Q1 chạm 1, Q2 chạm 3, Q3 chạm 12. Tỷ lệ request lần lượt 50%, 30% và 20%.

\[
\overline S=0.5(1)+0.3(3)+0.2(12)=3.8
\]

**Hỏi:** giá trị 3,8 đã chứng minh latency tốt chưa?

**Đáp án:** chưa. Nó chỉ mô tả số shard trung bình theo mẫu, cần docs examined, bytes, p95/p99 và hot shard.

## 52. Bài tập 3 — Prefix compound key

Shard key `{tenantId:1, createdAt:1}`. Query chỉ lọc `tenantId=t-001`.

**Hỏi:** có chắc chỉ chạm một shard không?

**Đáp án:** không. Tenant có thể trải nhiều chunk theo createdAt và nhiều shard.

## 53. Bài tập 4 — Hash và range

Shard key là hash của orderId. Query tìm `orderId` trong khoảng từ o-1000 tới o-2000.

**Hỏi:** range trên orderId gốc có tự thành một khoảng hash liên tục không?

**Đáp án:** không. Hash không bảo toàn thứ tự gốc. Cần đo khả năng pruning thực tế.

## 54. Bài tập 5 — Index và shard routing

Shard key tenantId; đã có index `{status:1}`. Query chỉ có `status="PENDING"`.

**Hỏi:** có chắc targeted một shard?

**Đáp án:** không. Index giúp tìm trong mỗi shard, còn router thiếu tenantId.

## 55. Bài tập 6 — Số shard có kết quả

Query được gửi tới 16 shard; chỉ một shard trả document.

**Hỏi:** `shardsTouched` bằng bao nhiêu?

**Đáp án:** 16 nếu cả 16 đã xử lý. Một shard có kết quả không đồng nghĩa chỉ một shard được chạm.

## 56. Bài tập 7 — Hot tenant

Có một triệu tenant, một tenant chiếm 70% write. Key là hash tenantId đơn trường.

**Hỏi:** cardinality cao đã đủ chưa?

**Đáp án:** chưa. Tenant nóng vẫn có thể dồn vào một shard. Đo heavy hitters và QPS theo shard.

## 57. Bài tập 8 — Chọn khóa từ bảng

Ứng viên B có fan-out trung bình 2,05; C có 3,04. Nhưng B làm một shard nhận 70% write, C phân tán đều và đạt p99 mục tiêu.

**Hỏi:** có bắt buộc chọn B không?

**Đáp án:** không. Fan-out trung bình chỉ là một tiêu chí. Tải, latency, capacity và correctness có thể khiến C tốt hơn.

## 58. Bài tập 9 — DynamoDB partition

Một ứng dụng Query đúng một logical partition key DynamoDB.

**Hỏi:** có thể kết luận query chạm chính xác một physical partition không?

**Đáp án:** không tự kết luận từ API key. Physical partition mapping thuộc dịch vụ. Đo các metric công khai và số key/request ở tầng ứng dụng.

## 59. Bài tập 10 — Cassandra replication

Cassandra RF=3, read CL=QUORUM cho một logical partition key.

**Hỏi:** có phải query chạm hai “shard dữ liệu độc lập” vì cần hai replica?

**Đáp án:** không. Đây là nhiều replica của cùng logical partition; không đồng nhất với số shard của MongoDB.

## 60. Bài tập 11 — Global sort

Query tìm top 20 Order có status PENDING toàn hệ trên 32 shard.

**Hỏi:** `limit(20)` có bảo đảm chỉ chạm tối đa 20 shard không?

**Đáp án:** không. Router có thể cần xem candidate results từ tất cả 32 shard.

## 61. Bài tập 12 — Balancer

Một query tenantId hôm qua chạm hai shard, hôm nay chạm ba; code ứng dụng không đổi.

**Hỏi:** nguyên nhân khả dĩ?

**Đáp án:** chunk placement/rebalance thay đổi. Cần ghi mốc topology và kiểm tra explain hai thời điểm.

## 62. Bài tập 13 — Business invariant

Query GetStock targeted một shard nhưng checkout đọc available rồi ghi vô điều kiện.

**Hỏi:** shard key có tự ngăn overselling không?

**Đáp án:** không. Cần conditional write/transaction bảo vệ invariant tại nguồn.

## 63. Bài tập 14 — Báo cáo hiếm

99% request targeted một shard, 1% báo cáo chạy trên 32 shard và quét rất nhiều dữ liệu.

**Hỏi:** phải tối ưu shard key cho báo cáo trước hay có lựa chọn khác?

**Đáp án:** cần đo tổng cost. Có thể tách analytics/read model, batch hoặc precompute thay vì làm suy giảm OLTP.

## 64. Checklist chứng minh shard key

1. Có danh mục query shapes và tỷ lệ read/write thật.
2. Đã xác định shard-key fields có mặt trong API nào.
3. Đã tính tenant scope và authorization.
4. Có dữ liệu thử đại diện cho tenant nhỏ, vừa và lớn.
5. Đã đo cardinality **và** phân phối tần suất key.
6. Có `explain` ở đúng đường router của cluster.
7. Đã đếm shard targeted/executing, không nhầm replica.
8. Có kết quả cho equality, prefix, range, `$in` và `$or`.
9. Có local plan, keys/docs examined và nReturned.
10. Có fan-out theo shape, tenant class và time window.
11. Có p95/p99 latency, errors và timeouts.
12. Có storage bytes, read/write QPS, CPU/IOPS theo shard.
13. Có đánh giá hot tenant, hot range và thời gian tăng trưởng.
14. Có phương án cho cross-shard aggregation hoặc read model.
15. Có thiết kế unique constraint, transaction và idempotency.
16. Có quan sát cache/search route riêng với source.
17. Có thử nghiệm balancer, chunk migration và tăng số shard.
18. Các số không đo được được ghi là estimate hoặc unknown.
19. Có ADR nêu rõ lợi ích, đánh đổi, rủi ro và rollback.
20. Có dashboard và tiêu chí xem xét lại khóa sau triển khai.

## 65. Kết luận

Đo số phân mảnh được chạm là một cách trực tiếp kiểm tra shard key có phục vụ workload hay không. Nhưng một shard key tốt cần nhiều hơn con số “một shard”:

- **Routing:** các query quan trọng có được pruning đúng không?
- **Local execution:** index và query plan trong shard có hiệu quả?
- **Load distribution:** data và write traffic có cân bằng?
- **Latency:** p95/p99 và failure behavior có đạt SLO?
- **Correctness:** tenant isolation, unique constraint và invariant có đúng?
- **Scalability:** khi số shard tăng hoặc chunk di chuyển, fan-out biến đổi thế nào?

Phép tính:

\[
\overline S_w=\sum_i p_i S(q_i)
\]

giúp so sánh fan-out theo tỷ trọng workload, nhưng không thay thế đo tài nguyên, tail latency và skew.

> **Chứng minh shard key bằng query plan, workload và các giới hạn nghiệp vụ; đừng chỉ bằng tên field, cardinality hoặc một truy vấn đơn lẻ đẹp mắt.**

Một quyết định tốt có thể giải thích vì sao chấp nhận fan-out ở những truy vấn nào, vì sao những truy vấn khác phải targeted, hotspot đã được kiểm soát ra sao và khi nào cần thay đổi thiết kế. Đó là cách lựa chọn khóa phân mảnh trở thành một quyết định kiến trúc có thể đo, kiểm chứng và duy trì trong hệ NoSQL.
