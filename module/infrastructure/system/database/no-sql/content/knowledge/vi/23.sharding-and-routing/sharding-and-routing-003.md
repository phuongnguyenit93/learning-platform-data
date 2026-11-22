# Chọn shard key từ mẫu truy cập và phân bố dữ liệu

Một hệ thống NoSQL lưu hàng trăm triệu sự kiện và bắt đầu gặp những biểu hiện trái ngược: tổng CPU của cụm còn thấp nhưng một node thường xuyên quá tải; thêm node không làm tốc độ ghi tăng; truy vấn lấy lịch sử của một khách hàng phải gửi tới mọi shard; hoặc một shard chứa quá nhiều dữ liệu của tenant lớn trong khi các shard khác còn gần trống.

Điểm chung có thể là **shard key** — thuộc tính dùng để quyết định một bản ghi hoặc một đơn vị dữ liệu thuộc shard nào. Chọn đúng shard key giúp phân phối dữ liệu và tải theo mục tiêu, đồng thời đưa những truy vấn quan trọng tới **ít shard nhất có thể**. Chọn sai có thể khiến kiến trúc phải đánh đổi giữa **hot partition**, **scatter-gather**, **cross-shard transaction** và **di chuyển dữ liệu tốn kém**.

Bài học thuộc **Database No SQL → Phân mảnh và định tuyến** tập trung vào cách **chọn shard key từ mẫu truy cập và phân bố dữ liệu**, không chỉ từ tên cột hay tính duy nhất. Ta sẽ xây ma trận truy vấn, tính cardinality/skew, so sánh khóa theo tenant, định danh, thời gian, range, hash và compound key; phân tích **colocation, fan-out, hot keys, resharding**; đối chiếu cách hiểu ở MongoDB, DynamoDB, Cassandra, HBase, Redis Cluster và công cụ tìm kiếm; sau đó thiết kế benchmark và quy trình ra quyết định.

> **Phạm vi:** Shard key, partition key, routing key và row key **không hoàn toàn đồng nghĩa** giữa các sản phẩm. Cấu trúc partition vật lý, cách split/merge, hash/range routing, quy tắc index và các giới hạn giao dịch phụ thuộc engine và phiên bản. Các số liệu là giả định học tập để lập luận, không phải kết quả benchmark nhà cung cấp.

## 1. Sharding giải quyết điều gì?

**Sharding** là chia tập dữ liệu logic thành nhiều phần và phân công phần đó cho những đơn vị lưu trữ/điều phối khác nhau.

Ví dụ một collection **Orders** có 120 triệu bản ghi:

~~~~text
                   Logical collection: Orders
                           |
                Shard routing function
                           |
              +------------+-------------+
              |            |             |
            Shard A      Shard B       Shard C
          orders ...    orders ...     orders ...
~~~~

Khi số lượng bản ghi và lưu lượng vượt khả năng một node, sharding có thể giúp:
- Phân phối **dung lượng đĩa**.
- Phân phối **write throughput**.
- Cho phép nhiều node tham gia phục vụ **đọc**.
- Quản lý dữ liệu theo **tenant, region hoặc thời gian**.
- Cô lập hoặc di chuyển một phần workload.
- Tăng quy mô theo nhu cầu thay vì chỉ nâng phần cứng một node.

Nhưng sharding **không miễn phí**:
- Một truy vấn có thể phải chạm nhiều shard.
- Index và join có thể không còn nằm cùng node.
- Transaction xuyên shard thường phức tạp hoặc đắt hơn.
- Resharding cần sao chép dữ liệu, xử lý write đồng thời và cutover.
- Một shard hoặc một partition nóng có thể chi phối toàn bộ p99.

### 1.1. Phân biệt sharding với replication

| Khái niệm | Mục tiêu chính | Ví dụ |
| --- | --- | --- |
| **Sharding/partitioning** | Chia dữ liệu thành các phần có trách nhiệm khác nhau | SKU-A thuộc shard 1, SKU-B thuộc shard 2 |
| **Replication** | Giữ nhiều bản sao của cùng phần dữ liệu | Shard 1 có replica tại 3 node |
| **Rebalancing** | Chuyển các phần dữ liệu giữa node/shard | Di chuyển partition nóng khỏi node quá tải |
| **Resharding** | Đổi cách chia hoặc ánh xạ key → shard | Từ tenantId sang tenantId+bucket |
| **Routing** | Xác định shard phải nhận request | Hash tenantId → partition |
| **Secondary index** | Tìm dữ liệu theo trường không phải định danh phân mảnh | Tra order theo paymentStatus |

Một cụm có **16 shard, replication factor = 3** có thể chứa 48 bản dữ liệu shard (tính theo logic replica) trên tập node của hệ. **48 replica-placement** không đồng nghĩa có 48 shard độc lập hay 48 lần dung lượng logic.

### 1.2. Logical partition không luôn bằng physical shard

Nhiều hệ phân tầng:

~~~~text
Application key
    -> Logical partition/routing token
    -> Physical partition/tablet/chunk
    -> Storage node
    -> Replica group
~~~~

Một giá trị partition key có thể ánh xạ đến một hash range hoặc một đơn vị vật lý; một shard vật lý chứa rất nhiều giá trị key. Một số engine có thể tự split/merge physical partitions, nhưng **không phải lúc nào cũng có thể chia nhỏ tải của một logical key cực nóng** mà vẫn giữ nguyên mô hình atomicity.

Khi vận hành, phải biết metric đang nói tới:
- **Một giá trị key** quá nóng?
- **Một logical partition** quá lớn?
- **Một physical partition/tablet** bị dồn tải?
- **Một node** đang chứa nhiều partition nóng?
- **Một vùng dữ liệu** bị nghẽn network/replication?

Bốn nguyên nhân khác nhau có cách chữa khác nhau.

## 2. Shard key quyết định dữ liệu đi đâu

Một mô hình tổng quát:

\[
shard = route(shardKey, shardMap)
\]

Trong đó:
- **shardKey:** một hoặc nhiều thuộc tính trích từ bản ghi hoặc request.
- **route:** hàm hash/range/lookup hoặc cơ chế engine.
- **shardMap:** ánh xạ logical partition hoặc range tới các shard thực.

Ví dụ:

~~~~text
Order:
  orderId   = O-901
  tenantId  = T-42
  userId    = U-77
  createdAt = 2026-11-14T09:30:00Z

Candidate key A: tenantId
Candidate key B: orderId
Candidate key C: (tenantId, monthBucket)
Candidate key D: hash(userId)
Candidate key E: (region, tenantId, bucket)
~~~~

Mỗi lựa chọn tạo ra **một cách phân bố và một đường truy cập khác**. Không có khóa nào tốt nhất cho mọi workload.

### 2.1. Đường đọc có shard key

Ví dụ ứng dụng thường gọi:

~~~~http
GET /tenants/T-42/orders?from=2026-11-01&to=2026-11-30
~~~~

Nếu key định tuyến phù hợp với tenant và khoảng thời gian, request có thể được gửi tới tập shard/partition có phạm vi nhỏ.

Một query có predicate đủ để định tuyến:

~~~~text
tenantId = T-42
monthBucket in {2026-11}
~~~~

có thể khác hoàn toàn một query chỉ có:

~~~~text
paymentStatus = PENDING
~~~~

Nếu paymentStatus không nằm trong routing key, hệ có thể phải **scatter-gather**, dựa vào global index hoặc một read model riêng.

### 2.2. Scatter-gather

**Scatter-gather** là fan-out request tới nhiều shard, rồi hợp nhất kết quả:

~~~~mermaid
flowchart LR
    Q["Query status=PENDING"] --> ROUTER["Router"]
    ROUTER --> A["Shard A"]
    ROUTER --> B["Shard B"]
    ROUTER --> C["Shard C"]
    A --> MERGE["Merge, sort, limit"]
    B --> MERGE
    C --> MERGE
    MERGE --> RES["API response"]
~~~~

Chi phí có thể gồm:
- Một RPC tới mỗi shard liên quan.
- Local index lookup/scan trên từng shard.
- Network truyền candidate rows.
- Coordinator merge/sort/dedup.
- Tail latency phụ thuộc shard chậm nhất.
- Chi phí và concurrency tăng theo số shard.

Nếu có 64 shard nhưng mỗi page query cần toàn bộ 64 shard, tăng shard count có thể **làm một truy vấn người dùng đắt hơn**, dù tổng dung lượng mỗi shard giảm.

### 2.3. Truy vấn không mang shard key không nhất thiết luôn full scan

Tùy engine, có thể có:
- Global secondary index hoặc một bảng tra cứu key.
- Local secondary indexes trên từng shard.
- Lookup index định tuyến tới một tập shard.
- Search engine/read model được thiết kế cho query không theo shard key.
- Một cơ chế auto-routing hoặc query planner phức tạp.

Vì vậy cách diễn đạt chính xác là: **không có predicate định tuyến phù hợp có nguy cơ fan-out hoặc cần index phụ**, chứ không phải mọi truy vấn như vậy đều bắt buộc quét toàn bộ dữ liệu.

## 3. Bắt đầu từ access pattern, không bắt đầu từ tên cột

Shard key phải được chọn dựa trên **những thao tác thực sự chi phối tải và yêu cầu của hệ thống**.

Thay vì hỏi “Trường nào unique nhất?”, hãy liệt kê:
- API nào được gọi nhiều nhất?
- Truy vấn nào có SLO p99 chặt nhất?
- Các filter/range/sort nằm trên trường nào?
- Có bao nhiêu rows được đọc/ghi mỗi request?
- Đơn vị nào cần **atomic update hoặc transaction**?
- Những tenant/user/device nào tạo tải không đồng đều?
- Những query nào hiếm nhưng scan rất lớn?
- Giai đoạn dữ liệu tăng theo **thời gian hay tenant**?
- Các vùng địa lý có yêu cầu định tuyến hoặc data residency không?

### 3.1. Ví dụ ma trận access pattern của hệ đặt chỗ

Giả sử hệ lưu **Bookings**:

| Operation | Predicate chính | Tỷ lệ request giả định | SLO | Yêu cầu đặc biệt |
| --- | --- | ---: | --- | --- |
| Tạo booking | tenantId + bookingId | 22% | p99 150 ms | Không tạo trùng operationId |
| Xem booking | tenantId + bookingId | 30% | p99 80 ms | Point lookup |
| Danh sách booking của user | tenantId + userId + time range | 18% | p99 120 ms | Sort mới trước |
| Lịch đặt của một phòng | tenantId + roomId + time range | 12% | p99 120 ms | Kiểm tra xung đột slot |
| Admin liệt kê trạng thái PENDING | tenantId + status + time range | 6% | p99 300 ms | Có thể dùng projection |
| Tìm booking theo email | tenantId + normalizedEmail | 5% | p99 250 ms | Bảo vệ PII |
| Báo cáo doanh thu tháng | tenantId + month | 4% | Batch | Tổng hợp |
| Audit xuyên tenant | global/time range | 3% | Phút | Có thể chạy offline |

**Các tỷ lệ chỉ minh họa.** Trong một hệ thực, cần lấy từ tracing, query logs, metrics, business forecasts và load test, không tự giả định tuyến tính theo số API.

### 3.2. Phân loại đường truy cập

Từ ma trận, ta thấy:
- **tenantId + bookingId:** point lookup quan trọng, có thể định tuyến tốt khi biết tenantId.
- **tenantId + userId + time:** truy vấn lịch sử một user, cần tránh mở vô số partition.
- **tenantId + roomId + time:** liên quan bất biến không đặt hai booking cho một slot.
- **tenantId + status:** query trên toàn tenant; nếu tenant lớn có thể fan-out.
- **global audit:** không nên để 3% query batch quyết định partitioning của 97% traffic online.

Một shard key cần tối ưu các đường **tốn tài nguyên nhất và khó thay thế nhất**, còn những query khác có thể giải bằng index/read model được xây theo access pattern khác.

### 3.3. QPS không phải trọng số duy nhất

Hai query:
- Q1 chạy 10.000 lần/s, mỗi lần point lookup 1 KiB.
- Q2 chạy 10 lần/s, mỗi lần scan 1 GiB.

Q2 có QPS thấp nhưng mỗi giây có thể đọc **10 GiB** nếu dữ liệu thực đúng như mô hình. Vì vậy cần cân đối:
- Frequency.
- Bytes scanned/returned.
- CPU per query.
- Shards touched.
- Peak concurrency.
- p99 deadline.
- Business criticality.
- Compaction/index/update overhead.

Một mô hình chi phí sơ bộ có thể dùng:

\[
Cost_i = frequency_i \times costPerRequest_i
\]

Tuy nhiên **costPerRequest** phải được đo/suy luận theo topology và query plan; không lấy số field filter làm proxy chi phí một cách máy móc.

## 4. Phân bố dữ liệu: cardinality là cần nhưng chưa đủ

**Cardinality của shard-key values** là số giá trị phân biệt của khóa trong tập dữ liệu đang xét.

Ví dụ:
- **region** có 3 giá trị.
- **countryCode** có khoảng vài trăm giá trị.
- **tenantId** có 50.000 giá trị.
- **userId** có 20 triệu giá trị.
- **bookingId** gần bằng số booking.

Cardinality rất thấp thường làm khó phân phối tải trên nhiều shard nếu engine không thể chia nhỏ một giá trị key. Nhưng **cardinality rất cao cũng không tự chứng minh phân bố đều**.

### 4.1. Key có hàng nghìn giá trị vẫn có thể lệch nặng

Giả sử:
- 100.000 tenant.
- 1 tenant lớn phát sinh **35% tổng write traffic**.
- 99.999 tenant còn lại chia **65%**.

Nếu key = tenantId và mỗi tenant đơn lẻ được ràng buộc trong một logical partition không thể chia tiếp, **tenant lớn có thể trở thành hot partition** dù có tới 100.000 giá trị distinct.

Khi thêm shard:
- Các tenant nhỏ được chia đều hơn.
- Tenant lớn vẫn giữ 35% tải trên đơn vị chịu trách nhiệm về key đó, trừ khi storage engine có cách phân phối bổ sung phù hợp.

**Điểm quan trọng là phân bố tải theo key, không chỉ số key.**

### 4.2. Ba phân bố cần đo riêng

1. **Rows per key:** mỗi giá trị key có bao nhiêu bản ghi.
2. **Bytes per key:** tổng kích thước dữ liệu và index của mỗi key.
3. **Operations per key:** read/write QPS, byte I/O và CPU trên mỗi key.

Một key có 100 triệu rows lịch sử nhưng rất ít request có thể là **storage hot**, còn một key chỉ chứa một row nhưng bị update 50.000 lần/s là **write hot**.

### 4.3. Độ lệch (skew) và tỷ lệ top keys

Các con số hữu ích:
- Top 1 key chiếm bao nhiêu % writes?
- Top 10 keys chiếm bao nhiêu % reads?
- Top 1% tenant chiếm bao nhiêu % bytes?
- p50/p95/p99 rows hoặc bytes per key.
- Max-to-average load ratio.
- Gini coefficient/entropy nếu phân tích nâng cao.
- Phân bố theo **giờ cao điểm**, không chỉ tổng ngày.

Ví dụ:

~~~~text
Total writes: 100.000/s
Shard count: 10
Ideal average: 10.000/s per shard

Actual writes:
  Shard A: 47.000/s
  Shard B:  7.000/s
  ...
  Shard J:  5.000/s
~~~~

Mặc dù tổng capacity có thể là 10 × 15.000 = 150.000 write/s trong điều kiện lý tưởng, shard A đã vượt 15.000 write/s. Cụm bị nghẽn **do max shard**, không phải tổng throughput.

### 4.4. Công thức cân bằng tải cơ bản

Với S shard và tổng tải R:

\[
R_{avg} = \frac{R}{S}
\]

Đặt:

\[
SkewRatio = \frac{R_{maxShard}}{R_{avg}}
\]

Nếu R=100.000 write/s, S=10, shard nóng nhất 47.000/s:

\[
SkewRatio = \frac{47.000}{10.000} = 4{,}7
\]

Đây là thước đo trực giác, không phải metric chuẩn duy nhất. SkewRatio cao cho biết shard nóng hơn nhiều so với trung bình; cần xem thêm capacity node, replication, batch, CPU và I/O.

## 5. Những thuộc tính cần đánh giá của shard key

Một candidate shard key nên được phân tích qua nhiều chiều:

| Chiều | Câu hỏi |
| --- | --- |
| **Cardinality** | Có đủ giá trị phân biệt để phân phối dữ liệu và load? |
| **Frequency skew** | Một vài giá trị có chi phối reads/writes? |
| **Data-size skew** | Một vài key giữ quá nhiều byte hoặc row? |
| **Query targeting** | Bao nhiêu request có đủ key để route? |
| **Range locality** | Query theo time/range có được xử lý bởi ít partition không? |
| **Write distribution** | Ingest liên tục có dồn vào đầu/cuối của key range? |
| **Transaction scope** | Những record cần update cùng nhau có được co-locate? |
| **Uniqueness** | Global uniqueness/conditional guard có ràng buộc theo key? |
| **Mutability** | Giá trị key có đổi trong vòng đời record không? |
| **Growth** | Trong 12–24 tháng, hot keys và dữ liệu thay đổi ra sao? |
| **Geography** | Có yêu cầu định tuyến tenant về region hoặc residency? |
| **Operational flexibility** | Có thể split/migrate/reshard khi key xấu? |
| **Security** | Key có lộ PII, cho phép đoán ID hoặc làm enumeration dễ hơn? |
| **Cost** | Query fan-out, secondary indexes, replication, egress và storage? |

**Không có một điểm số tuyệt đối**: các chiều có thể xung đột. Khóa giúp point lookup nhanh có thể khiến report theo thời gian phân tán; khóa tốt cho range scan có thể tạo hot write range.

## 6. Khóa theo tenant: locality tốt, tenant lớn có thể thành điểm nóng

Trong ứng dụng multi-tenant, chọn **tenantId** thường hấp dẫn vì:
- Hầu hết query đều có tenantId.
- Dữ liệu cùng tenant có thể được nhóm hoặc định tuyến rõ.
- Thao tác backup/export/migration theo tenant thuận tiện hơn.
- Một số chính sách security/data residency có thể gắn với tenant.
- Có thể dễ đặt giới hạn QPS/billing cho tenant.

~~~~text
Tenant T1 -> dữ liệu và request T1
Tenant T2 -> dữ liệu và request T2
Tenant T3 -> dữ liệu và request T3
~~~~

Tuy nhiên tenantId một mình có thể là lựa chọn rất xấu khi một tenant có khối lượng lớn hoặc tạo burst.

### 6.1. Khi nào tenantId đơn lẻ có thể phù hợp?

- Số tenant đủ nhiều.
- Không một tenant nào chi phối tải.
- Mỗi tenant có kích thước dưới ngưỡng partition của engine.
- Truy vấn và invariant phần lớn nằm trong tenant.
- Engine có placement/routing hỗ trợ loại dữ liệu này.
- Workload growth không tạo “mega-tenant” bất ngờ.

### 6.2. Khi một tenant rất lớn

Giả sử:
- Tenant T-LARGE có 12 triệu booking, 40% write/s.
- Mỗi tenant nhỏ có vài nghìn booking.
- Logical partition theo tenant không thể chia tải bằng thêm node.

Một cách thường xét là **(tenantId, bucketId)**:

~~~~text
T-LARGE#bucket-00
T-LARGE#bucket-01
...
T-LARGE#bucket-15
~~~~

Bucket có thể dựa trên:
- Hash bookingId.
- Hash userId.
- Một bucket thời gian.
- Một shard suffix được cấp từ trước.

Nhưng query “tất cả booking của T-LARGE” nay phải **fan-out** qua nhiều bucket. Đây là đánh đổi có chủ đích: **phân phối writes vs locality của truy vấn tenant-wide**.

### 6.3. Tenant isolation không tự có chỉ vì tenantId nằm trong key

Khi có tenantId:
- Mọi API vẫn phải kiểm tra tenant trong auth context.
- Không cho client tự chọn tenantId của người khác.
- Index/read model phải mang tenant isolation.
- Permission filtering phải nằm trong đường dữ liệu có thẩm quyền.
- Không dùng shard location làm bằng chứng quyền truy cập.

**Shard key phục vụ routing; authorization là một hệ ràng buộc riêng.**

## 7. Khóa theo ID duy nhất: phân phối tốt, truy vấn theo nhóm có thể tốn

Nếu mỗi record có **bookingId** gần như ngẫu nhiên, dùng hash(bookingId) có thể phân phối rows khá đều.

~~~~text
bookingId=O-101 -> Shard A
bookingId=O-102 -> Shard C
bookingId=O-103 -> Shard B
~~~~

Lợi ích:
- Point lookup khi biết bookingId có thể target một shard.
- Write load phân tán khi ID/hash có entropy tốt.
- Tránh dồn ghi vào cuối một range nếu hash được phân bố.

Nhược điểm:
- Query theo **tenantId** có thể phải tới nhiều shard hoặc dùng secondary index.
- Danh sách booking của user không có locality tự nhiên.
- Transaction cập nhật nhiều booking cùng tenant có thể cross-shard.
- Export/retention theo tenant phức tạp hơn.

### 7.1. “Unique” không tự bảo đảm uniform routing

ID tăng tuần tự (1,2,3,...) là unique nhưng nếu sharding theo **range**, ghi mới có thể tập trung vào range mới nhất.

Ngược lại ID dạng thời gian có độ tăng đều nhưng hệ dùng **hash routing** vẫn có thể phân tán tốt. **Phải phân biệt phân bố giá trị key với cách engine ánh xạ key sang physical partition.**

### 7.2. Chọn orderId hay userId?

Nếu 90% workload là:

~~~~http
GET /orders/O-901
~~~~

và query đi cùng orderId đầy đủ, route theo orderId có thể hiệu quả.

Nếu 90% workload là:

~~~~http
GET /users/U-77/orders?limit=20
~~~~

thì route theo userId hoặc một mô hình read projection theo userId có thể phù hợp hơn.

**Truy vấn quan trọng nhất phải là đầu vào, không phải mức độc nhất của ID.**

## 8. Range sharding: locality tốt, nguy cơ hotspot ở ranh giới

**Range-based sharding** nhóm các giá trị key liên tiếp vào một phạm vi.

~~~~text
Shard A: orderDate < 2026-01
Shard B: 2026-01 <= orderDate < 2026-07
Shard C: orderDate >= 2026-07
~~~~

Lợi ích có thể có:
- Query theo khoảng thời gian/range chỉ chạm một số shard.
- Scan dữ liệu có thứ tự thuận tiện hơn.
- Dữ liệu theo khoảng có thể dễ archive/migrate nếu engine hỗ trợ.

Rủi ro:
- Toàn bộ write có timestamp mới nhất có thể dồn vào **range cuối**.
- Một ngày/tháng đột biến có thể làm partition nóng.
- Split/migrate có thể chạy sau khi hotspot đã xuất hiện.
- Một range có size thấp nhưng QPS rất cao, hoặc ngược lại.

### 8.1. Monotonically increasing key

Ví dụ key = createdAt:
 
~~~~text
09:00:00 -> tail range
09:00:01 -> tail range
09:00:02 -> tail range
...
~~~~

Đây là dạng **moving hotspot**: phần lớn ghi đi vào range chứa timestamp gần hiện tại.

Thêm physical shard có thể **không chia được write ngay** nếu cấu trúc vẫn liên tục dồn vào một range active và routing/split không phân tán lưu lượng đó.

### 8.2. Query range quan trọng thì có bắt buộc range sharding?

Không. Một hệ có thể:
- Hash theo tenant/user để phân phối write.
- Sắp xếp dữ liệu **theo time bên trong mỗi partition**.
- Dùng index theo time phù hợp.
- Xây projection theo date bucket.
- Batch query một tập partition biết trước.

Quan trọng là xác định **range query cần phủ qua phạm vi nào**: toàn hệ hay lịch sử của một tenant/thiết bị? Nếu query gần như luôn có deviceId, thiết kế **partition by deviceId + sort by eventTime** có thể tốt hơn sharding toàn cục bằng eventTime.

## 9. Hash sharding: cân bằng giá trị key, đánh đổi range locality

Một routing khái niệm:

\[
shard = hash(key) \bmod S
\]

Với S=8, những key độc lập có hash phân bố tốt có thể được chia trên 8 shard.

Lợi ích:
- Giảm việc tăng tuần tự đẩy mọi write vào tail range.
- Phân tán key đa dạng, đặc biệt khi key có cardinality cao.
- Routing point lookup có thể nhanh khi biết full key.

Đánh đổi:
- Dữ liệu gần nhau theo time/ID có thể nằm trên các shard khác.
- Một range scan không có shard key cụ thể có thể fan-out.
- **Một hot key** vẫn là một hot key, hash không chia một giá trị thành nhiều giá trị.
- Nếu dùng modulo đơn giản, tăng S có thể remap rất nhiều key; engine thực thường dùng virtual partitions, token ranges hoặc consistent hashing/placement riêng.

### 9.1. Hashing không tự chia nhỏ elephant tenant

Nếu:

~~~~text
key = tenantId
hash(T-LARGE) = shard-5
~~~~

thì 40% traffic của T-LARGE vẫn có thể tập trung trên shard-5, dù hash function hoàn hảo. Hash chỉ giúp **phân bố nhiều key khác nhau**, không phân rã lưu lượng của **một key đơn lẻ**.

### 9.2. Hash prefix và tính năng sản phẩm

Một số engine hỗ trợ **hashed shard key** trực tiếp; một số yêu cầu application sinh suffix/bucket; một số tự chia physical partition trong giới hạn riêng.

Không nên giả định cú pháp **hash(tenantId)** trong một database có cùng khả năng với **partition key = tenantId** của database khác. Routing semantics phải được kiểm chứng ở chính engine.

### 9.3. Không dùng hàm hash không ổn định giữa các phiên bản

Nếu application tự tạo suffix:

~~~~text
bucket = hash(orderId) mod 16
~~~~

phải xác định:
- Hash algorithm ổn định giữa Java, Python, Go.
- Encoding UTF-8 và normalization của key.
- Signed vs unsigned hash.
- Số bucket được version hóa.
- Cách truy xuất dữ liệu cũ sau khi đổi bucket count.
- Đường phục hồi nếu config các service không đồng nhất.

Một thay đổi **16 → 32 bucket** bằng modulo mà không có migration có thể làm read tìm ở bucket mới trong khi dữ liệu vẫn nằm ở bucket cũ.

## 10. Compound shard key: thứ tự thành phần quyết định cách định tuyến

Một khóa ghép có thể là:

~~~~text
(tenantId, userId)
(tenantId, monthBucket)
(tenantId, roomId, dayBucket)
(region, tenantId, eventId)
(tenantId, bucketId, createdAt)
~~~~

Mục đích thường gặp:
- Thu hẹp truy vấn tới tenant.
- Tách dữ liệu lớn thành bucket.
- Giữ một số record liên quan gần nhau.
- Hỗ trợ range query trong phạm vi một group.
- Phân bố writes vượt giới hạn của một key đơn.

### 10.1. Có đủ predicate để route không?

Giả sử shard key được định nghĩa theo một thứ tự cụ thể:

~~~~text
(tenantId, bucketId)
~~~~

Request biết tenantId nhưng không biết bucketId có thể phải query **tất cả bucket của tenant** hoặc dựa vào routing/index đặc biệt.

Request biết cả tenantId và bucketId có thể đi tới một tập nhỏ hơn.

Tuy nhiên **quy tắc dùng prefix, hash, range và targeted routing phụ thuộc engine**. Không suy từ hành vi compound index trong SQL sang mọi NoSQL composite shard key.

### 10.2. Đặt timestamp cuối key có tự phân phối ghi?

Không nếu prefix xác định một logical partition quá lớn và timestamp chỉ là **clustering/sort key bên trong partition**.

Ví dụ một mô hình partition key = tenantId và sort key = createdAt:

~~~~text
Partition key: T-LARGE
Sort key: 2026-11-14T09:00:01
Sort key: 2026-11-14T09:00:02
...
~~~~

Các event vẫn cùng logical partition T-LARGE theo semantics đó. Sort theo thời gian làm query range thuận tiện nhưng không tự phân chia tải giữa nhiều partition.

### 10.3. Colocation và phân phối là hai mục tiêu xung đột

Nếu tất cả booking của một user trong một partition:
- Lấy lịch sử nhanh.
- Nhưng user cực nóng có thể quá tải.

Nếu chia booking theo nhiều bucket:
- Ingest phân tán.
- Lịch sử phải fan-out và merge.

Một cách tiếp cận là giữ **đường ghi phân phối** và xây **read projection/materialized view** tối ưu truy vấn lịch sử. Điều đó tăng storage, processing, eventual freshness và yêu cầu idempotency.

## 11. Time bucketing: chia theo thời gian để giới hạn partition

Với dữ liệu time-series/IoT/logs, key theo thiết bị mà không thêm bucket có thể tạo partition tăng vô hạn.

~~~~text
deviceId = D-42
eventTime: 2020 -> 2026 -> 2030 ...
~~~~

Một cách thiết kế:

~~~~text
Partition key = (deviceId, dayBucket)
Clustering/sort key = (eventTime, eventId)
~~~~

Ví dụ:

~~~~text
(D-42, 2026-11-14) -> events sorted by time
(D-42, 2026-11-15) -> next day's events
~~~~

Lợi ích:
- Giới hạn kích thước một partition theo window.
- Query “24 giờ gần nhất của D-42” thường cần một hoặc hai bucket.
- Retention/archival theo window có thể thuận tiện hơn.
- Dữ liệu cũ không làm một partition duy nhất phát triển mãi.

Rủi ro:
- Query “toàn bộ lịch sử 5 năm” phải đọc nhiều bucket.
- Device cực nóng vẫn có thể làm **bucket của ngày hôm nay** quá tải.
- Dữ liệu đến muộn làm ghi vào bucket cũ.
- Phải quyết định theo **eventTime hay ingestionTime**.
- TTL hỗn hợp và update lịch sử có thể ảnh hưởng cleanup/compaction.

### 11.1. Chọn kích thước bucket bằng tải và query

Giả sử một thiết bị tạo 1.000 event/s, mỗi event ~1 KiB:

\[
B_{\text{day}}=1.000\times86.400\times1.024
\]

Tương đương ~**82,4 GiB payload/ngày** cho một thiết bị. **Daily bucket** có thể quá lớn đối với nhiều engine hoặc gây hotspot dù có nhiều device khác.

Nếu bucket theo giờ:

\[
B_{\text{hour}}=1.000\times3.600\times1.024
\approx3{,}43\text{ GiB/hour}
\]

Vẫn có thể quá lớn tùy engine/hệ thống, nhưng giảm đáng kể kích thước **một logical bucket**.

Cần đo cả **write QPS trên active bucket**: đổi day → hour không làm 1.000 write/s giảm nếu tất cả ghi của thiết bị trong cùng giờ vẫn tới một partition. Để chia **tải hiện tại**, có thể phải thêm hash suffix/salt và fan-out query.

### 11.2. Bucket theo thời gian không tự chống hot current window

~~~~text
Partition: (deviceId=D-42, hour=09)
  toàn bộ 1.000 write/s trong giờ 09
~~~~

Lựa chọn:
- **(deviceId, hour, bucketId)** với bucketId dựa trên eventId để phân phối.
- Giảm/đệm/batch ingestion theo hợp đồng.
- Tách một thiết bị cực nóng thành nhiều producer channels.
- Điều chỉnh partitioning theo tải và query cardinality.

Nếu thêm 16 bucket, query “latest 100” cần lấy candidate từ nhiều bucket và **merge theo eventTime/eventId**, không được chỉ đọc bucket 0.

### 11.3. Event time và ingestion time

Một event được tạo lúc 23:58 ngày D nhưng đến server lúc 00:05 ngày D+1:

- Bucketing theo **eventTime** giúp query theo thời gian phát sinh, nhưng tạo late writes vào bucket cũ.
- Bucketing theo **ingestionTime** giúp đường ghi tăng theo lúc nhận, nhưng query theo eventTime phải biết mapping/bổ sung index.
- Event timestamp từ thiết bị có thể sai hoặc bị giả mạo; cần policy kiểm tra/canonicalization.

Một thiết kế time-series cần định nghĩa **độ trễ sự kiện tối đa**, retention và cách xử lý event out-of-order ngay từ đầu.

## 12. Salting và synthetic buckets: giải quyết hot key có giá đọc

**Salting** thêm một thành phần phân phối nhân tạo vào key.

Giả sử tenant T-LARGE có 40.000 write/s, một partition chỉ chịu ổn định 5.000 write/s trong workload đo được. Một thiết kế có thể dùng **16 bucket**:

~~~~text
T-LARGE#00
T-LARGE#01
...
T-LARGE#15
~~~~

Nếu thực sự phân bố đều, tải trung bình một bucket:

\[
40.000/16 = 2.500\text{ write/s}
\]

Đây là **kỳ vọng giả định**, chưa trừ overhead hay xét phân bố key.

### 12.1. Random salt hay deterministic salt?

**Random salt**:
- Phân phối writes tương đối đều.
- Muốn tìm một entity cụ thể phải biết salt đã dùng hoặc lưu mapping.
- Không nên random mới mỗi lần retry, vì một operation có thể rơi bucket khác.

**Deterministic salt**:
- Ví dụ bucketId = stableHash(orderId) mod 16.
- Tìm order theo ID có thể tính lại bucket.
- Nếu các order độc lập, phân bố writes tương đối đều.
- Query theo tenant không biết orderId phải đọc nhiều bucket.

### 12.2. Một key thứ cấp không được nhân đôi logical identity

Nếu reservation OP-101 được tạo trong bucket=3 nhưng retry tính ra bucket=7 do hashing không ổn định, cả hai request có thể tạo hai reservation. Cần:
- Hash deterministic/được version hóa.
- Operation ID ổn định.
- Unique/conditional guard theo đúng phạm vi.
- Cách tra dedup ledger không bị phá bởi bucket mới.
- Migration rules khi thay thuật toán phân bucket.

### 12.3. Buckets không nhất thiết phải cố định cho mọi tenant

Một tenant nhỏ có thể chỉ cần 1 bucket, tenant lớn cần 16 hoặc 64. Có thể dùng **routing metadata**:

~~~~json
{
  "tenantId": "T-LARGE",
  "bucketCount": 16,
  "routingVersion": 3
}
~~~~

Nhưng application cần:
- Xác minh version routing nhất quán.
- Xử lý thay đổi bucketCount qua migration.
- Tránh writer dùng version cũ sau cutover.
- Tra cả dữ liệu cũ nếu lịch sử đã trải qua nhiều bucket counts.
- Có cơ chế chống duplicate và missing record.

Routing metadata được quản lý sai có thể tạo lỗi dữ liệu khó phát hiện hơn một hot shard ban đầu.

## 13. Thiết kế dữ liệu theo truy vấn và mô hình read/write riêng

Một dataset thường có nhiều access patterns **không thể cùng tối ưu bằng một shard key duy nhất**.

Ví dụ:
- Đọc booking theo bookingId.
- Lịch sử booking theo userId.
- Lịch phòng theo roomId và time.
- Đơn bị PENDING theo tenant/status.

Một lựa chọn có thể là **source of truth** tập trung tính đúng, kèm read projections:

~~~~mermaid
flowchart LR
    API["Booking API"] --> SOURCE[("Booking authority: routing theo slot/order")]
    SOURCE --> OUT["Outbox / CDC"]
    OUT --> U[("BookingsByUser")]
    OUT --> R[("BookingsByRoom")]
    OUT --> S[("PendingByTenant")]
~~~~

Mỗi projection có thể dùng partition/routing key khác nhau:
- **BookingsByUser:** (tenantId, userId, monthBucket).
- **BookingsByRoom:** (tenantId, roomId, dayBucket).
- **PendingByTenant:** (tenantId, status, timeBucket), có bucket khi tenant lớn.

Lợi ích: query nhanh và không bắt nguồn source xử lý mọi fan-out.

Chi phí:
- Ghi thêm/index amplification.
- Eventual lag.
- Retry/out-of-order/duplicate events.
- Rebuild và reconciliation.
- Nguồn dữ liệu phải có operationId/version rõ.
- Không dùng read projection trễ làm điểm quyết định cuối về unique room slot.

**Denormalization và sharding phải thiết kế cùng nhau**: nếu 4 query quan trọng xung đột nặng về locality, thường cần nhiều access paths chứ không có một khóa phép màu.

## 14. Colocation: những gì cần transaction có nên cùng shard?

Nếu hai bản ghi luôn được cập nhật cùng nhau, đặt cùng shard **có thể** giảm chi phí network hoặc cho phép dùng transaction/atomicity trong phạm vi engine hỗ trợ.

Ví dụ lưu một room slot:

~~~~json
{
  "slotKey": "TENANT#T-42#ROOM#R-08#DAY#2026-12-01",
  "status": "FREE",
  "bookingId": null,
  "version": 17
}
~~~~

Một request giữ slot dùng conditional update trên **slotKey**:

~~~~text
IF status == FREE
THEN status = RESERVED, bookingId = B-901, version += 1
~~~~

Ở mô hình hỗ trợ atomic item update, một logical slot là điểm **phân xử cạnh tranh**.

### 14.1. Cùng shard không tự đồng nghĩa transaction

Một hệ có thể chỉ bảo đảm atomicity:
- Trong một document.
- Trong một item.
- Trong một partition.
- Trong một transaction có phạm vi xác định.

Nếu hai entity nằm cùng physical shard nhưng API không cung cấp multi-row transaction tương ứng, **không được suy ra chúng commit cùng nhau**.

### 14.2. Khác shard không tự nghĩa không thể transaction

Một số NoSQL cung cấp **distributed transactions** qua nhiều shard, với giới hạn và chi phí riêng. Có thể đúng về mặt tính nguyên tử nhưng tăng:
- Coordination và lock/metadata.
- Round trips.
- Retry/abort dưới tranh chấp.
- Complexity của commit outcome khi mất kết nối.
- Latency p99 và khả năng phục vụ khi một shard thiếu quorum.

Vì vậy colocation là một biến tối ưu **đường transaction**, không phải quy tắc “khác shard thì vô phương cứu”.

### 14.3. Thiết kế aggregate theo invariant

Nếu nghiệp vụ yêu cầu:
- Mỗi room slot có tối đa một booking active.
- Một operationId chỉ giữ chỗ một lần.
- Không vượt quota tenant.

Cần xác định **mỗi invariant được bảo vệ ở object/transaction nào** trước khi chọn key. Chỉ có dữ liệu cùng tenant không đủ nếu hai operation khác nhau có thể cùng tranh một slot.

## 15. Unique constraints, idempotency và định tuyến

Một shard key có thể ảnh hưởng cách hệ thực thi **unique index hoặc conditional guard**.

Giả sử yêu cầu **email unique trên toàn hệ**. Nếu dữ liệu người dùng được chia theo tenantId, cùng normalizedEmail có thể xuất hiện trên nhiều shard. Một unique constraint **local từng shard** không nhất thiết ngăn duplicate global.

Những khả năng cần phân tích:
- Engine có global unique index được hỗ trợ không?
- Unique key có yêu cầu chứa shard key không?
- Có thể đưa invariant về phạm vi tenant không?
- Có thể xây một registry/authority theo email để claim uniqueness?
- Có thể dùng ID cấp từ một nguồn có thẩm quyền và duplicate check?
- Việc lookup registry có tạo hot partition không?

### 15.1. Business uniqueness cần ghi rõ phạm vi

Hai hợp đồng khác nhau:
1. **(tenantId, normalizedEmail)** unique: cùng email được dùng ở hai tenant khác nhau.
2. **normalizedEmail** global unique: không cho hai tenant dùng chung email.

Chọn shard key tenantId thuận tiện cho (1) hơn (2), nhưng kết luận chi tiết phụ thuộc cơ chế unique indexes/transactions của engine.

### 15.2. Idempotency ledger phải tìm được bằng key ổn định

Nếu mỗi retry tạo booking với operationId OP-101:
- Cùng OP-101 phải tìm về **cùng logical operation record**.
- Routing key nên xác định ổn định.
- Ledger và side effect cần ranh giới atomicity/consistency phù hợp.
- Resharding phải giữ khả năng tra OP-101 cũ.
- Không được random một bucket mới trong mỗi HTTP attempt.

**Sharding có thể làm hỏng chống retry nếu phép định tuyến của cùng một operation không ổn định.**

## 16. Shard-key mutability và vòng đời record

Một field rất hấp dẫn để filter có thể **thường xuyên thay đổi**:
- orderStatus: PENDING → CONFIRMED → CANCELLED.
- User tier: FREE → PREMIUM.
- Tenant region: VN → EU do migration.
- Owner/team của document.
- Timestamp “lastUpdatedAt”.

Nếu shard key chứa những field mutable, mỗi update có thể phải **di chuyển record sang shard khác** hoặc bị engine giới hạn tùy sản phẩm.

### 16.1. Chọn status làm shard key dễ tạo hotspot và di chuyển

~~~~text
Key: status

Mọi order mới ban đầu ở PENDING.
Sau vài giây, chuyển sang CONFIRMED.
~~~~

Vấn đề:
- Cardinality status thấp.
- PENDING có write hotspot.
- Record đổi partition khi trạng thái đổi.
- Query theo status có locality tốt nhưng ít chọn lọc.
- Một shard có thể nhận phần lớn write mới.

Tốt hơn thường là:
- Dùng key ổn định, có cardinality đủ và phân phối tốt cho source.
- Xây index hoặc **PendingOrders projection** theo status/time.
- Dùng bucket để chia dashboard admin khi cần.

### 16.2. Tenant region có thể thay đổi do residency policy

Nếu chọn (region, tenantId):
- Dữ liệu có thể được đặt theo region khi engine hỗ trợ.
- Nhưng di chuyển tenant cần migration/cutover.
- Yêu cầu pháp lý có thể ảnh hưởng việc copy backup, log và replicas sang region khác.
- Đổi region metadata mà không chuyển data không tự đáp ứng data residency.

**Location-aware sharding** là một kế hoạch vận hành và compliance, không chỉ thêm một field region vào khóa.

## 17. Query sort và pagination có liên quan shard key

Một truy vấn:

~~~~http
GET /users/U-77/orders?sort=createdAt_desc&limit=20
~~~~

Nếu những order của U-77 nằm gần nhau trong một partition hoặc tập bucket nhỏ, storage engine có thể đọc theo sort key/range với chi phí thấp.

Nếu order phân tán trên 128 shard:
- Mỗi shard phải trả candidate.
- Router merge theo createdAt.
- Có thể tốn nhiều read hơn 20.
- Cursor cần giữ thứ tự và tie-breaker ổn định.
- Pagination nhiều trang dễ bị duplicate/missing khi dữ liệu đang thay đổi.

### 17.1. Pagination theo cursor

Một cursor hợp lý có thể mang:
- createdAt của bản cuối.
- orderId tie-breaker.
- Shard routing/version.
- Snapshot/consistency token nếu engine hỗ trợ.

Không nên dùng offset rất lớn trên scatter-gather query mà không đo chi phí.

### 17.2. Range sort theo thời gian trong một partition

Nếu key = (tenantId, userId, monthBucket) và sort key = (createdAt, orderId), một query lịch sử 30 ngày có thể đọc một/vài bucket, nhưng cross-month query cần merge.

Nếu query “latest 20” phải đọc 16 salted bucket:
- Yêu cầu top-k candidates từ từng bucket.
- Merge toàn cục theo (createdAt, orderId).
- Xử lý pages/cursors nhất quán.
- Tránh missing events ở bucket chưa bắt kịp.

**Tính đúng của sort/pagination là phần thiết kế access pattern**, không chỉ hiệu năng.

## 18. Ví dụ MongoDB: chọn shard key theo query shape

Trong MongoDB sharding, người thiết kế thường cân nhắc:
- **Ranged shard key** để hỗ trợ locality của range query.
- **Hashed shard key** để phân phối giá trị thay vì dồn vào range cuối.
- **Compound shard key** có prefix/fields phù hợp với common query shapes.
- **Zone sharding** khi cần placement theo rule hỗ trợ.
- **Targeted queries** khi router suy ra được shard/range.
- Các cơ chế di chuyển chunk, resharding và unique index constraints theo phiên bản.

Ví dụ source collection:

~~~~json
{
  "_id": "O-901",
  "tenantId": "T-42",
  "userId": "U-77",
  "createdAt": "2026-11-14T09:30:00Z",
  "status": "CONFIRMED",
  "totalMinor": 1390000
}
~~~~

### 18.1. Một shard key chỉ theo createdAt

Có thể hỗ trợ một số range query theo thời gian, nhưng nếu key tăng tuần tự, write mới có nguy cơ dồn vào vùng cuối theo **range routing**. Muốn hiểu tác động cần xem chunk/range placement và độ phân bố thực của write.

### 18.2. Một hashed key theo _id

Ví dụ cú pháp minh họa trong MongoDB shell khi collection và điều kiện hệ đã chuẩn bị thích hợp:

~~~~javascript
sh.shardCollection(
  "commerce.orders",
  { _id: "hashed" }
);
~~~~

Điều này có thể phân phối point writes theo hashed _id, nhưng query chỉ có tenantId hoặc createdAt **không tự có targeted routing**. Những index khác có thể tăng tốc local scan nhưng không thay đổi yêu cầu routing nếu không có kế hoạch khác.

Không copy lệnh vào production khi chưa xem:
- Collection/index tồn tại.
- Unique constraint mong muốn.
- Cluster/shard topology.
- Dữ liệu hiện có và resharding plan.
- Phiên bản hỗ trợ và giới hạn shard key đã chọn.

### 18.3. Compound key theo tenant

Một ứng viên khác:

~~~~javascript
sh.shardCollection(
  "commerce.orders",
  { tenantId: 1, orderId: 1 }
);
~~~~

Ví dụ dựa trên giả định có trường orderId đã được chuẩn hóa và các preconditions về index/uniqueness phù hợp. Nó có thể giúp định tuyến những query có tenantId theo cơ chế range/compound sharding, nhưng tenant cực lớn hoặc thứ tự orderId vẫn cần phân tích skew và hotspot.

**Một compound shard key không tự bảo đảm mỗi tenant nằm trọn trên một shard**, vì range có thể được chia/chuyển giữa các shard; đồng thời query targeting phụ thuộc predicate và shard map.

### 18.4. Explain và targeted routing

Với các câu query thường gặp:

~~~~javascript
db.orders.find({
  tenantId: "T-42",
  orderId: "O-901"
});

db.orders.find({
  tenantId: "T-42",
  status: "PENDING"
}).sort({createdAt: -1}).limit(20);
~~~~

Cần xem **explain/query plan** và metrics:
- Số shard được target.
- Index được dùng trên từng shard.
- Keys/documents examined.
- Bytes returned.
- Merge/sort overhead.
- p99 khi tenant nhỏ và tenant lớn.

Không suy từ việc một query “có index” rằng nó chỉ chạm một shard.

## 19. Ví dụ DynamoDB: partition key và sort key

Trong DynamoDB, **partition key** của table là thành phần quan trọng của phân phối/routing; nếu table dùng composite primary key, **sort key** tổ chức/sắp xếp item trong cùng partition-key value theo mô hình của dịch vụ.

Ví dụ bảng **EventsByDevice**:

~~~~text
PK = DEVICE#D-42#DAY#2026-11-14
SK = TIME#2026-11-14T09:30:00Z#EVENT#E-901
~~~~

Query một ngày của thiết bị có thể dùng PK chính xác và điều kiện sort key phù hợp.

### 19.1. Một partition key cực nóng

Nếu:

~~~~text
PK = TENANT#T-LARGE
~~~~

và tenant ấy tạo hàng chục nghìn writes/s trên cùng giá trị logical key, cần cân nhắc hot-key behavior, cấu trúc partition nội bộ do dịch vụ quản lý, adaptive capacity và **giới hạn workload thực**; không mặc định thêm provisioned capacity là mọi hot key được chia vô hạn.

Một thiết kế salted:

~~~~text
PK = TENANT#T-LARGE#BUCKET#07
SK = ORDER#O-901
~~~~

Query toàn tenant cần fan-out qua bucket trừ khi có index/projection khác.

### 19.2. Sort key không tự phân phối partition-key traffic

Nếu mọi item có PK giống nhau và SK tăng theo timestamp, **SK phù hợp với range query bên trong key**, nhưng không nên suy SK làm nhiều logical partition keys mới. Đây là điểm dễ nhầm khi so với một compound shard key kiểu range của MongoDB.

### 19.3. GSI là access path khác và có độ mới riêng

Một **Global Secondary Index** có partition/sort key riêng, phục vụ pattern khác, nhưng được cập nhật bất đồng bộ theo hợp đồng của DynamoDB.

Ví dụ:
- Source table theo PK = ORDER#orderId.
- GSI theo GSI_PK = TENANT#tenantId, GSI_SK = CREATED#timestamp.

Có thể truy vấn orders của tenant qua GSI, nhưng:
- GSI có thể lag.
- GSI có thể có hot key của riêng nó.
- GSI tăng storage/write cost.
- Không dùng GSI stale để quyết định giữ inventory hay xác nhận commit.

**Index key cũng cần phân tích cardinality và skew**, không chỉ shard key nguồn.

## 20. Ví dụ Cassandra: partition key và clustering columns

Trong Cassandra, **partition key** quyết định việc băm token và placement của partition; **clustering columns** quyết định tổ chức/sắp xếp hàng trong partition theo schema.

Ví dụ:

~~~~sql
CREATE TABLE events_by_device_day (
    device_id text,
    day_bucket date,
    event_time timestamp,
    event_id timeuuid,
    temperature double,
    PRIMARY KEY (
        (device_id, day_bucket),
        event_time,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC,
    event_id DESC
);
~~~~

Ở đây:
- **Partition key:** (device_id, day_bucket).
- **Clustering columns:** event_time, event_id.
- Query theo device/day có thể định vị partition và đọc bản ghi theo time.
- Chỉ có event_time không đủ để tự định tuyến tới partition chứa mọi device.

### 20.1. Một partition lớn gây gì?

Khi một device có dữ liệu nhiều năm trong một partition:
- SSTable/row index/tombstones có thể làm scan nặng.
- Read và write vào cùng partition có thể quá tập trung.
- Compact/repair/TTL có thể tốn tài nguyên.
- Query full history có thể kéo dài.

Time bucketing theo ngày/giờ giúp giới hạn một partition, nhưng cần kiểm tra **partition size, read patterns và late events**.

### 20.2. Clustering key không sửa hot partition

Nếu một device phát 50.000 events/s và tất cả cùng (device_id, day_bucket), việc chọn event_time làm clustering column không tự chia load thành nhiều partition. Có thể phải thêm **bucket_id vào partition key** hoặc thay ingestion architecture.

~~~~sql
-- Mô hình thay thế, cần cân nhắc query fan-out:
PRIMARY KEY (
    (device_id, day_bucket, bucket_id),
    event_time,
    event_id
)
~~~~

Để lấy toàn bộ sự kiện một ngày phải query nhiều bucket và merge kết quả. BucketId phải ổn định theo eventId/đường routing, không random lại cho retries.

### 20.3. Không dùng ALLOW FILTERING như lời giải cho shard key sai

Nếu access pattern thường xuyên query không có partition key, cố quét nhiều dữ liệu bằng **ALLOW FILTERING** hoặc một scan không đo đạc có thể không đáp ứng production SLO. Cần thiết kế table/query model theo pattern hoặc secondary index phù hợp với khả năng phiên bản và workload.

**CQL data modeling là query-first**, không coi mọi SQL-style filter đều có chi phí giống nhau.

## 21. Ví dụ HBase: row key, region split và hotspot

Trong HBase, **row key** có thứ tự từ điển và ảnh hưởng tới phạm vi region/table scan. Nếu row key tăng tuần tự:

~~~~text
20261114090000#event-1
20261114090001#event-2
20261114090002#event-3
~~~~

Ghi mới có thể tập trung vào **region cuối** do tính liên tục của khóa.

Các kỹ thuật cần cân nhắc:
- Hash/salt prefix để phân tán ghi.
- Reverse timestamp hoặc đảo chiều thành phần để phục vụ thứ tự truy vấn cụ thể.
- Pre-splitting region có kế hoạch.
- Compound row key chứa tenant/device/time bucket.
- Thiết kế scan và fan-out khi thêm salt.

### 21.1. Salting cải thiện write nhưng làm range scan khó hơn

Nếu row key:

~~~~text
<bucket>#<deviceId>#<timestamp>#<eventId>
~~~~

thì để scan toàn bộ sự kiện một device theo thời gian có thể phải đọc nhiều bucket, hoặc đã có quy tắc xác định bucket theo device/event.

**Tối ưu write distribution phải kèm kế hoạch đọc lại dữ liệu**, không chỉ đo write throughput.

### 21.2. Region split không phải phương án vô hạn cho một hot key

Hệ có thể tự split region khi đạt ngưỡng size, nhưng một tập write tập trung vào **một row key** hoặc một dải key cực hẹp vẫn cần thiết kế ứng dụng phù hợp. Đừng mặc định tự split sẽ luôn chữa được hot row.

## 22. Ví dụ Redis Cluster: hash slot và hash tags

Redis Cluster chia key theo **hash slots** và phân bổ slots tới node; việc đặt các key liên quan cùng slot có thể quan trọng với multi-key operations.

Ví dụ:

~~~~text
order:{T-42}:O-901
inventory:{T-42}:SKU-9
operation:{T-42}:OP-101
~~~~

Phần nằm trong **{...}** được dùng làm hash tag trong cơ chế slot của Redis Cluster, khiến những key có cùng tag được hash tới **cùng slot** theo quy tắc Redis Cluster.

### 22.1. Colocation có giá của nó

Nếu mọi key của tenant T-LARGE có cùng tag **{T-LARGE}**, chúng có thể dồn vào cùng slot, gây **slot hotspot**. Điều này giúp những multi-key operations cần cùng slot nhưng hạn chế phân tán tenant lớn.

Một cách khác là tag theo bucket:

~~~~text
order:{T-LARGE#07}:O-901
inventory:{T-LARGE#07}:SKU-9
~~~~

Nhưng nay những key thuộc bucket khác nhau không tự cùng slot; transaction/script multi-key có thể gặp ràng buộc cross-slot. Phải chọn theo **invariant nào cần nằm cùng execution boundary**.

### 22.2. Redis cluster key không tương đương NoSQL sharding transaction chung

Một command/script atomic tại một slot/node không tự bảo vệ:
- Inventory ở slot khác.
- MongoDB Order source.
- Payment provider.
- Search index.
- Replica failover durability trong mọi trường hợp.

**Đừng dùng hash tag để ngụ ý cross-service ACID transaction.**

## 23. Ví dụ OpenSearch/Elasticsearch: routing và shard fan-out

Ở công cụ tìm kiếm, primary shards và routing quyết định document được lưu tại shard nào. Mặc định routing có thể dựa trên document ID; một số hệ hỗ trợ **custom routing** theo tenant hoặc thuộc tính khác.

Nếu mọi tài liệu tenant T-42 có routing T-42, query mang routing tương ứng có thể chỉ chạm shard được route, giảm fan-out.

Nhưng:
- Tenant quá lớn có thể tạo shard hotspot.
- Query toàn cục không có routing vẫn phải tới nhiều shard.
- Một document cần routing nhất quán khi index, update và delete.
- Search index có refresh/query-visibility lag.
- Shard sizing và replica count ảnh hưởng heap, CPU, merge và p99.

### 23.1. Chọn routing không chữa được query plan kém

Một query target đúng shard nhưng phải quét hàng triệu document vẫn có thể chậm. Cần kết hợp:
- Mapping/index design.
- Filter selectivity.
- Search sort/aggregation.
- Shard sizing và cache.
- Query routing và fan-out.
- Freshness SLO.

Đừng xem số shards touched là metric hiệu năng duy nhất.

## 24. Data locality và đặt shard theo vùng địa lý

Một candidate key có thể gồm region:

~~~~text
region = VN | EU | US
tenantId = ...
~~~~

Nhưng **region đơn thuần có cardinality thấp**, không phù hợp làm khóa phân phối cho hàng trăm shard nếu đó là đơn vị key không thể split.

Một mô hình có thể có:
- Region quyết định **placement policy** hoặc namespace.
- TenantId/bucketId quyết định logical partition trong vùng.
- Replica group trải qua những availability zones theo yêu cầu.
- Read replicas hoặc caches phục vụ gần người dùng.
- Cross-region replication theo durability/freshness contract.

### 24.1. Geo-routing không tự giải quyết luật cư trú dữ liệu

Nếu hệ thống có yêu cầu một tenant không được đưa PII ra khỏi VN, phải kiểm tra:
- Primary shard placement.
- Replicas.
- Backup/snapshot.
- Logs, metrics và CDC.
- Search/read models.
- Support exports.
- Disaster recovery destinations.

Một shard key region=VN không tự ngăn hệ gửi bản sao hoặc backup tới EU.

### 24.2. Vùng của người dùng có thể khác vùng của dữ liệu

Một người dùng du lịch từ VN tới EU:
- Dữ liệu tenant vẫn có source VN theo policy.
- EU có thể đọc cache/projection eventual nếu cho phép.
- Checkout hoặc update nhạy cảm có thể phải round-trip tới authority VN.
- Session consistency/read-your-writes cần context phù hợp.

**Chọn shard key theo vị trí client hiện tại** có thể gây migration không cần thiết và phá định danh ổn định; cần phân biệt user location với **home region/data ownership**.

## 25. Tính toán dung lượng cho các key ứng viên

Một hệ IoT giả định:
- 12 triệu event/ngày.
- Mỗi event payload ~1 KiB trước index/compression.
- Hot retention 30 ngày.
- Replication factor = 3.
- 24 logical shards.

### 25.1. Payload logic mỗi ngày

\[
12.000.000\times1.024
=12.288.000.000\text{ byte}
\]

Theo GiB:

\[
\frac{12.288.000.000}{1024^3}\approx11{,}44\text{ GiB/ngày}
\]

### 25.2. 30 ngày và replication

\[
11{,}44\times30\approx343{,}32\text{ GiB logic}
\]

\[
343{,}32\times3\approx1.029{,}97\text{ GiB}
\]

Tức xấp xỉ **1,01 TiB payload đã nhân bản**, trước compression, index, WAL, compaction temp, snapshots, tombstones và chênh lệch placement.

### 25.3. Trung bình một shard

Nếu 24 logical shards cân bằng tuyệt đối:

\[
343{,}32/24\approx14{,}31\text{ GiB logic/shard}
\]

Nhưng nếu shard nóng giữ **22% bytes**:

\[
343{,}32\times0{,}22\approx75{,}53\text{ GiB}
\]

Một shard có thể lớn gấp **5,28 lần** trung bình dù tổng cụm còn nhiều headroom.

### 25.4. Storage skew và traffic skew không giống nhau

Một shard có 75 GiB lịch sử lạnh chưa chắc làm p99 tệ, trong khi một shard 10 GiB có key bị update 50.000 lần/s có thể là bottleneck.

Vì vậy sizing phải có ít nhất:
- Bytes per shard/partition.
- Read QPS/CPU/IO per shard.
- Write QPS/IO per shard.
- Index/compaction amplification.
- Max/hot percentile, không chỉ average.
- Replica placement và node headroom.
- Burst và recovery traffic.

## 26. Một ma trận chấm điểm candidate key

Giả sử ba candidate cho Bookings:
- **A:** hash(bookingId).
- **B:** tenantId.
- **C:** (tenantId, monthBucket, hashBucket).

Ví dụ chấm điểm **giả định** trên thang 1–5, cao là tốt hơn theo mục tiêu đã định:

| Tiêu chí | Trọng số | A | B | C |
| --- | ---: | ---: | ---: | ---: |
| Point lookup bookingId | 25% | 5 | 3 | 4 |
| Danh sách booking tenant/time | 20% | 1 | 5 | 4 |
| Cân bằng write của tenant lớn | 25% | 5 | 1 | 4 |
| Đơn giản routing/migration | 10% | 4 | 5 | 2 |
| Giới hạn kích thước partition | 10% | 5 | 1 | 4 |
| Colocation cho workflow | 10% | 2 | 4 | 3 |

Điểm tổng có thể tính:

\[
Score(candidate)=\sum_i weight_i\times score_i
\]

Ví dụ với A:

\[
0{,}25(5)+0{,}20(1)+0{,}25(5)+0{,}10(4)+0{,}10(5)+0{,}10(2)=3{,}80
\]

Với B:

\[
0{,}25(3)+0{,}20(5)+0{,}25(1)+0{,}10(5)+0{,}10(1)+0{,}10(4)=3{,}00
\]

Với C:

\[
0{,}25(4)+0{,}20(4)+0{,}25(4)+0{,}10(2)+0{,}10(4)+0{,}10(3)=3{,}70
\]

Các điểm là **minh họa chủ quan**, không phải đánh giá sản phẩm. A và C gần nhau, vì vậy quyết định cần dựa vào:
- SLO thực tế.
- Cost của read model cần thêm.
- Mức skew dự báo.
- Migration risk.
- Transaction/uniqueness constraints.
- Benchmark trên engine cụ thể.

**Chấm điểm chỉ giúp làm rõ tradeoff; nó không thay được test về correctness và capacity.**

## 27. Thiết kế một chiến lược routing ổn định

Khi application tự tính bucket, phải tránh tạo logic rời rạc ở nhiều service.

Một cấu trúc metadata:

~~~~json
{
  "routingAlgorithm": "stable-hash-v1",
  "routingVersion": 3,
  "tenantId": "T-42",
  "bucketCount": 16,
  "effectiveFrom": "2026-11-01T00:00:00Z"
}
~~~~

Một booking có:
- bookingId.
- tenantId.
- routingVersion.
- bucketId được xác định lúc tạo.
- createdAt.
- operationId.

### 27.1. Mã Java minh họa deterministic bucket

~~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public final class BucketRouter {
    private BucketRouter() {}

    public static int bucketFor(String immutableId, int bucketCount) {
        if (immutableId == null || immutableId.isBlank()) {
            throw new IllegalArgumentException("immutableId is required");
        }
        if (bucketCount <= 0) {
            throw new IllegalArgumentException("bucketCount must be positive");
        }

        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(immutableId.getBytes(StandardCharsets.UTF_8));
            long first64 = ByteBuffer.wrap(digest).getLong();

            // Modulo trên số nguyên unsigned, deterministic cho cùng input.
            return (int) Long.remainderUnsigned(first64, bucketCount);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~~

Ví dụ dùng:

~~~~java
String bookingId = "O-901";
int bucket = BucketRouter.bucketFor(bookingId, 16);

// Cùng bookingId và cùng bucketCount sẽ cho cùng bucket.
String logicalPartition = "TENANT#T-42#BUCKET#" + bucket;
~~~~

Đây là **helper giáo dục**, không phải thuật toán shard placement do MongoDB/DynamoDB/Cassandra/Redis áp dụng. Không nên thay đổi cách encode, hash, modulo hoặc bucket count của dữ liệu production mà không version hóa routing và migration.

### 27.2. Stable routing còn cần stable input

Nếu một client retry tạo booking mà sinh **bookingId mới**, dù hash deterministic, nó vẫn có thể chọn bucket khác. Nên:
- Chọn operationId trước khi gửi.
- Đảm bảo logical booking identity ổn định qua retry.
- Ghi operation ledger/unique guard đúng scope.
- Không lấy timestamp mới mỗi attempt làm một phần routing key nếu muốn cùng ý định.
- Không dựa vào random salt thay đổi qua lần retry.

### 27.3. Một router cần biết phiên bản data cũ

Nếu hệ chuyển từ 16 sang 32 buckets:
- Dữ liệu tạo trước cutover vẫn dùng mapping cũ.
- Dữ liệu tạo sau cutover dùng mapping mới.
- Read theo bookingId cần biết routingVersion hoặc tra metadata.
- Query toàn tenant cần đọc đủ bucket của các version.
- Migration có thể di chuyển dần và đánh dấu completion.

**Đổi cấu hình router mà không có khả năng tra record cũ là lỗi định tuyến**, không chỉ là sự giảm hiệu năng.

## 28. Resharding: vì sao chọn sai khóa đắt để sửa?

**Resharding** có thể là:
- Tăng số node/physical partitions nhưng giữ cùng logical key.
- Di chuyển chunk/range giữa nodes.
- Đổi shard key của collection/table.
- Chia một tenant lớn thành nhiều bucket.
- Chuyển dữ liệu tenant tới region khác.
- Tách một read model mới để giảm fan-out.

Không phải thao tác nào cũng có cùng độ khó.

### 28.1. Những việc có thể cần khi đổi shard key

1. Thiết kế key/routing mới.
2. Tạo index/schema cần thiết.
3. Di chuyển hoặc copy dữ liệu từ mapping cũ.
4. Theo dõi những write mới trong lúc copy.
5. Replay CDC/outbox theo thứ tự/version.
6. Kiểm tra row counts, checksums và business invariants.
7. Cutover read/write routing.
8. Có rollback hoặc dual-read strategy.
9. Giữ mapping cũ đủ lâu cho retry/message đến muộn.
10. Thu hồi dữ liệu cũ theo retention/backup đúng quy trình.

### 28.2. Dual-write có thể gây inconsistency

Một kế hoạch ngây thơ:

~~~~text
Write old shard
Write new shard
Return success
~~~~

Nếu old thành công, new timeout, dữ liệu lệch. Nếu retry với operationId mới, có thể duplicate.

Cần cơ chế migration đáng tin hơn:
- Single authoritative source trong từng giai đoạn.
- Snapshot + CDC hoặc transaction/outbox theo khả năng engine.
- Versioned apply và idempotency.
- Verification/reconciliation.
- Hàng rào chống writer cũ sau cutover.

### 28.3. Online resharding cũng có giá

Dù sản phẩm hỗ trợ reshard online, vẫn cần dự phòng:
- Network copy/egress.
- CPU và disk I/O.
- Index maintenance/compaction.
- Chậm query và p99.
- Dung lượng tạm.
- Conflict với transaction/DDL.
- Failover/rollback behavior.

Không coi “engine tự rebalance” là lý do bỏ qua kiểm soát growth và hot keys.

### 28.4. Một logical hot key có thể không chữa được bằng rebalance

Nếu một userId duy nhất có 80.000 write/s và mọi cập nhật bắt buộc đi vào **một record atomic**, di chuyển record sang node khỏe hơn chỉ chuyển hotspot sang nơi khác. Cần xem:
- Có thể phân rã semantics thành event log/partitions?
- Có thể batch? Với yêu cầu mất dữ liệu nào?
- Có thể sharded counter và merge nếu eventual phù hợp?
- Có thể phân quyền kiểu escrow/bounded counter?
- Có thể giảm contention bằng cách thay invariant/API?

**Thêm node giải quyết phân phối giữa các key, không mặc định giải quyết contention bên trong một key.**

## 29. Hot shard và hot key: runbook phân loại

Một dashboard báo:
- p99 write tăng.
- Node A CPU 95%.
- Node B,C,D dưới 40%.
- Cluster storage chỉ 55%.

Không vội tăng cluster size hoặc reshard.

### Bước 1 — Xác định nóng về cái gì

- CPU, disk IOPS, WAL/fsync, network hay memory?
- Read hay write path?
- Có compaction, repair, migration, snapshot đang chạy không?
- Chỉ một API hoặc tenant cụ thể?
- Request rate theo key có tập trung không?

### Bước 2 — Xác định cấp hotspot

- Một row/document?
- Một logical partition key?
- Một physical partition/chunk/tablet?
- Một node do đặt nhiều shard nóng?
- Một region do traffic routing?
- Một coordinator do scatter-gather?

### Bước 3 — Kiểm tra query routing

- Query nào không có shard key?
- Fan-out count p50/p95/p99?
- Local index selectivity?
- Per-shard documents examined/bytes scanned?
- Coordinator merge/sort cost?
- Có một tenant cực lớn hoặc time bucket quá dày?

### Bước 4 — Chọn cách sửa phù hợp

| Nguyên nhân | Hướng xử lý có thể cân nhắc |
| --- | --- |
| Một physical shard chứa nhiều key nóng | Rebalance/split/migrate theo engine |
| Một logical tenant key quá nóng | Tenant bucketing/salting, projection theo query |
| Current time range là tail hotspot | Hash prefix hoặc time+bucket, xem range read cost |
| Query status thiếu routing | Read projection/index theo status/tenant |
| Một counter row cực nóng | Batch/sharded counter nếu semantics cho phép; guard khác nếu strict |
| Một node chậm do compaction | Tune maintenance/capacity trước khi đổi shard key |
| Cross-shard transaction quá nhiều | Đổi aggregate boundary hoặc batching có kiểm soát |
| Search shard quá lớn | Shard sizing/index/query design, replica/routing review |

### Bước 5 — Đặt tiêu chí thành công

Không chỉ hỏi “CPU đã giảm chưa?”. Cần:
- Hot shard QPS/CPU/I/O giảm.
- p99 của critical API đạt SLO.
- Fan-out và bytes scanned trong ngân sách.
- Không mất/duplicate record khi migrate.
- Invariant nghiệp vụ vẫn đúng.
- Có headroom cho peak 2–3 lần và recovery.
- Dữ liệu phân bố ổn định sau growth 6–12 tháng.

## 30. Benchmark shard key trên phân bố dữ liệu thật

Chọn shard key bằng một mẫu dữ liệu hoàn toàn uniform thường gây tự tin giả. Cần mô phỏng:
- Nhiều tenant nhỏ và một vài tenant rất lớn.
- Zipfian popularity ở sản phẩm/user.
- Time-based bursts, giờ cao điểm.
- Writes tăng tuần tự theo timestamp/ID.
- Query theo tenant và query xuyên tenant.
- Random + sequential point lookups.
- Range query 1 ngày, 7 ngày, 30 ngày.
- Late arrivals/updates/deletes.
- Transaction và operationId retries.
- Failover, rebalance và index lag.

### 30.1. Benchmark matrix

| Kịch bản | Candidate key | Điều cần ghi |
| --- | --- | --- |
| Uniform IDs | hash(bookingId) | Shard balance, point read |
| Zipfian tenant | tenantId | Hot tenant/write p99 |
| Tenant + hash buckets | (tenantId,bucketId) | Fan-out tenant list, write distribution |
| Sequential IDs | range(createdAt) | Tail hotspot, chunk splits |
| IoT devices | (deviceId, dayBucket) | Partition size, latest events read |
| Hot IoT device | (deviceId, dayBucket, hashBucket) | Write balancing, merge latest |
| Room slot | (tenantId, roomId, day) | Conditional reserve contention |
| Global status query | source key vs projection | Scatter count and index lag |
| Growing cluster | 8 → 16 → 32 shards | Remap/migration/rebalance cost |
| Region failure | geo-aware placement | RPO/RTO và routing |
| Retry after timeout | stable vs changed bucket | Duplicate-operation risk |
| Data skew drift | tenant popularity changes | Max/avg load over time |

### 30.2. Các metric tối thiểu

**Query routing:**
- Number of shards contacted per request.
- Fraction targeted vs scatter-gather.
- Coordinator merge/sort CPU.
- Network bytes across shards.
- p50/p95/p99 latency theo endpoint/query shape.

**Data and load distribution:**
- Rows/bytes per logical key/physical shard/node.
- Reads/writes per key/shard.
- p95/p99/max key size.
- Top-N key QPS và skew ratio.
- Per-shard disk, CPU, cache, IO queue và compaction backlog.

**Correctness and operational behavior:**
- Duplicate/missing records qua reshard.
- Unique constraint/invariant violations.
- Cross-shard transaction abort/latency.
- Retry/timeout/UNKNOWN operation count.
- Replica lag/failover time.
- Read model freshness.
- Migration duration và extra network/storage footprint.

### 30.3. Đặc tả thử nghiệm minh họa

~~~~yaml
experiment: shard-key-selection-access-patterns
dataset:
  tenants: 80000
  users: 10000000
  bookings: 120000000
  largeTenantWriteSharePercent: 35
  zipfianPopularity: true
  hotRetentionDays: 90
workload:
  offeredReadsPerSecond: 40000
  offeredWritesPerSecond: 15000
  peakMultiplier: 3
  operations:
    - get_booking_by_tenant_and_id
    - list_user_bookings_last_30_days
    - list_room_bookings_by_day
    - create_booking_conditional_slot
    - list_pending_by_tenant
    - global_audit_batch
candidates:
  - hash_booking_id
  - tenant_id
  - tenant_month_hash_bucket
  - room_day_bucket_with_user_projection
faults:
  - leader_failover
  - hot_tenant_burst
  - slow_shard
  - reshard_during_ingest
  - lost_commit_ack
measure:
  - per_query_shard_fanout
  - per_shard_rows_bytes_qps
  - max_to_avg_load_ratio
  - latency_p50_p95_p99
  - scanned_bytes_and_documents
  - cross_shard_transaction_cost
  - index_projection_lag
  - migration_duration_and_headroom
  - correctness_and_duplicate_operation_count
~~~~

Đây là **tập mô tả benchmark**, không phải cấu hình trực tiếp cho MongoDB/Cassandra/DynamoDB. Những tên biến và con số phải được hiện thực trong load generator và điều chỉnh theo engine.

### 30.4. Kết quả giả định

| Candidate | Write p99 | Read latest user p99 | Shards per user query | Hot shard / avg load | Lưu ý |
| --- | ---: | ---: | ---: | ---: | --- |
| hash(bookingId) | 80 ms | 420 ms | 32 | 1,3× | Writes đều, lịch sử fan-out |
| tenantId | 380 ms | 70 ms | 1 | 8,0× | Mega-tenant gây hotspot |
| tenantId + 16 buckets | 115 ms | 140 ms | 16 | 1,7× | Cần merge trên buckets |
| tenantId + 4 buckets | 190 ms | 100 ms | 4 | 3,2× | Ít fan-out, phân tải kém hơn |
| room-day + projection by user | 130 ms | 95 ms | 1–2 trên projection | 1,8× | Có index/read model lag |

**Số liệu hoàn toàn giả định**. Cần ghi rõ read p99 từ source hay projection, freshness của projection và tỷ lệ request vượt SLO. Không chọn chỉ theo một cột.

## 31. Kiểm chứng shard key khi lỗi mạng và thay đổi topology

Shard routing có thể bị tác động bởi:
- Cluster topology update chậm.
- Node relocation/failover.
- Metadata cache ở router lỗi thời.
- Request timeout khi chunk/tablet di chuyển.
- Concurrent writes lúc cutover.
- Retry với routing algorithm version khác.
- Replica chưa apply update mới.

### 31.1. Topology change không được làm mất logical identity

Nếu shard A chuyển ownership của range K sang shard B:
- Client có thể gửi request tới A theo metadata cũ.
- A/router cần redirect/retry theo protocol, không tự tạo dữ liệu xung đột.
- Write đã commit và ACK bị mất cần được xác định bằng operationId.
- Không được trả hai bản nghiệp vụ khác nhau cho cùng key sau cutover.

### 31.2. Một successful reroute không chứng minh transaction idempotent

Giả sử lệnh **increment +1** được gửi tới shard cũ, đã commit nhưng ACK mất; router retry tới shard mới. Nếu không có operation identity/dedup, +1 có thể áp dụng thêm lần nữa.

**Shard routing correctness và operation idempotency phải được kiểm chứng riêng.**

### 31.3. Test rollback/cutover

Một thử nghiệm nên:
1. Tạo dữ liệu seed có operationId/version.
2. Chạy concurrent inserts, updates, deletes.
3. Bắt đầu di chuyển shard/range.
4. Cho client dùng routing metadata cũ và mới.
5. Drop ACK của một số write đã commit.
6. Failover node đang giữ range.
7. Kiểm tra counts, checksums, operation ledger và invariants.
8. Xác nhận stale router được redirect an toàn.
9. Đo p99, error rate, backlog và thời gian cutover.

Không chạy fault injection phá dữ liệu trên production khi chưa có kế hoạch/ủy quyền phù hợp.

## 32. Bẫy thiết kế shard key thường gặp

1. **“Chọn trường unique nhất là đủ.”** Chưa xét query routing, locality và hotspot.
2. **“Cardinality cao nghĩa tải đều.”** Một key có thể chiếm 40% traffic.
3. **“Dữ liệu đều thì CPU cũng đều.”** Key nhỏ nhưng rất hot vẫn gây bottleneck.
4. **“Dùng timestamp tăng để phân phối ghi.”** Range sharding có thể dồn vào tail.
5. **“Hash timestamp thì range scan vẫn như cũ.”** Hash phá locality theo range.
6. **“Hash tenantId sẽ chia một tenant lớn.”** Một tenantId vẫn là một hash key.
7. **“Sort key tự chia logical partition.”** Không đúng với nhiều mô hình partition+sort.
8. **“Thêm 32 shard chữa được mọi hot key.”** Không nếu một key vẫn không thể split tải.
9. **“Dùng status=PENDING làm shard key để query nhanh.”** Cardinality thấp, mutable và dễ dồn writes.
10. **“Mọi query có index đều chỉ chạm một shard.”** Routing và local index khác nhau.
11. **“Không có shard key trong query thì chắc chắn full table scan.”** Có thể có global index/read model; phải xem query plan.
12. **“TenantId chỉ phục vụ security.”** Nó còn có thể là routing dimension, nhưng không thay authorization.
13. **“Cùng shard tự có transaction.”** Atomicity do engine/API quyết định.
14. **“Khác shard không bao giờ có transaction.”** Một số hệ có distributed transaction với chi phí riêng.
15. **“Chỉ có 1% query global nên bỏ qua.”** Ít query nhưng mỗi query có thể scan hàng GiB.
16. **“Một salted key giúp read nhanh hơn.”** Nó có thể làm fan-out tăng.
17. **“Random bucket cho mỗi retry vẫn an toàn.”** Có thể tạo duplicate business effect.
18. **“Đổi modulo 16→32 là thay config đơn giản.”** Mapping cũ cần versioning/migration.
19. **“Bài toán unique toàn hệ tự giải khi hash ID.”** Unique constraints có phạm vi riêng.
20. **“Shard key mutable không có chi phí.”** Có thể buộc move record hoặc bị giới hạn.
21. **“Đặt region trong key tự bảo đảm residency.”** Replicas/logs/backups cũng phải kiểm soát.
22. **“Read projection có thể quyết định stock cuối.”** Projection có thể stale.
23. **“Auto-rebalancing luôn xử lý được moving hotspot.”** Cần xem grain và speed của split.
24. **“Cassandra clustering columns chia dữ liệu sang node khác.”** Partition key mới quyết định token/placement.
25. **“HBase rowkey timestamp tăng giúp cân bằng write.”** Thường có tail hotspot.
26. **“Redis hash tag theo tenant vừa co-locate vừa phân tải vô hạn.”** Một hash slot có giới hạn.
27. **“MongoDB hashed key giúp query time range target 1 shard.”** Không tự bảo đảm.
28. **“GSI không có hotspot vì không phải source table.”** GSI có key/load riêng.
29. **“Đo average shard QPS là đủ.”** Cần max/p99 và top-N keys.
30. **“Khi p99 cao phải đổi shard key ngay.”** Có thể là compaction, disk hoặc query plan.
31. **“Reshard online không cần thử.”** Migration vẫn có tác động correctness/cost.
32. **“Chỉ test uniform random IDs là đủ.”** Production thường có Zipfian skew và time bursts.
33. **“Fan-out 16 shards luôn chậm hơn point lookup.”** Tùy query/index/cache; cần benchmark.
34. **“Có thể lưu routing info chỉ trong RAM.”** Sau restart/cutover có thể mất mapping.
35. **“Shard key là một lựa chọn độc lập với replication.”** Placement, quorum và failure domains ảnh hưởng latency/availability.
36. **“Một shard key phục vụ tất cả access patterns.”** Nhiều hệ cần read model/index riêng.

## 33. Bài tập thực hành: lựa chọn shard key cho hệ thống booking

Một hệ thống đặt chỗ dùng Java 21 và NoSQL, với các giả định:

- **80.000 tenant**.
- **120 triệu booking** lưu trong hệ.
- **40.000 read/s**, **15.000 write/s** bình thường; giờ đỉnh gấp **3 lần**.
- Tenant lớn nhất chiếm **35% writes**.
- 60% query theo **tenantId + bookingId hoặc tenantId + userId**.
- 20% query theo **tenantId + roomId + date range**.
- 10% admin query theo **tenantId + status**.
- 10% analytics/batch truy vấn toàn hệ.
- Một room slot chỉ được có một booking active.
- Write sau timeout phải không tạo duplicate booking.
- 32 logical shards, nhiều replica theo chính sách hệ.
- Listing p99 dưới **200 ms**, checkout p99 dưới **250 ms**.
- Đường analytics có thể chạy phút; search/read models có freshness SLO riêng.

### Phần A — Xây ma trận access pattern

Lập bảng:
- Operation.
- Predicate/filter.
- Sort/range.
- QPS ở peak.
- Records returned.
- SLO.
- Atomicity/invariant.
- Candidate routing key.

Phân biệt **đường đọc để khám phá** với **đường ghi quyết định giữ slot**.

### Phần B — Ba candidate keys

Phân tích:
1. Hash theo bookingId.
2. Chỉ tenantId.
3. (tenantId, monthBucket, hashBucket).

Với mỗi candidate, nêu:
- Point lookup.
- List by user.
- List by room/day.
- Tenant-wide admin query.
- Storage/write skew.
- Transaction locality.
- Resharding complexity.

Không kết luận chỉ bằng cardinality.

### Phần C — Tính hot tenant

Peak write traffic:

\[
15.000\times3=45.000\text{ write/s}
\]

Tenant lớn chiếm 35% peak (giả định tỷ lệ không đổi):

\[
45.000\times0{,}35=15.750\text{ write/s}
\]

Nếu một logical partition có ngưỡng phục vụ ổn định giả định **2.500 write/s** trong benchmark, tenantId đơn có đáp ứng không? Cần ít nhất bao nhiêu bucket nếu phân bố hoàn hảo, chưa có overhead/headroom?

**Gợi ý:** 15.750/2.500 = **6,3**; về lý thuyết cần ít nhất **7 buckets**, nhưng production có thể chọn nhiều hơn để có headroom và tránh skew.

### Phần D — Fan-out theo bucket

Nếu tenant dùng 16 buckets, query 20 booking mới nhất cần:
- Query bao nhiêu bucket?
- Lấy bao nhiêu candidate từ mỗi bucket để merge?
- Sort theo (createdAt, bookingId) thế nào?
- Có thể bỏ sót/duplicate khi paginate trong lúc nhiều write không?
- Có phương án read projection by user/room nào tốt hơn?

Đừng tự kết luận mỗi bucket bắt buộc trả đúng 20 record trong mọi query plan; hãy mô tả chiến lược top-k/cursor và kiểm thử.

### Phần E — Source và projection

Thiết kế bảng/collection cho:
- **Booking authority**.
- **RoomSlot guard**.
- **BookingsByUser**.
- **BookingsByRoom**.
- **PendingByTenant**.
- **OperationResult** và outbox.

Nêu chính xác ranh giới transaction/conditional write bảo vệ slot, phần nào eventual, và cách không dựa vào projection stale để xác nhận booking.

### Phần F — Java deterministic routing

Dùng helper Java tạo bucket theo **bookingId ổn định** và số bucket được version hóa. Mô tả điều gì xảy ra khi:
- Client retry với cùng operationId.
- Routing version đổi 16 → 32.
- Client ở instance cũ gửi theo mapping cũ.
- Một booking cần lookup mà không biết tenantId.
- Admin query toàn tenant phải đi qua nhiều bucket.

### Phần G — Multi-region và residency

Tenant T-42 thuộc home region VN, người dùng đang ở EU. Hãy đề xuất:
- Authority ở đâu?
- Có đọc local cache/projection được không?
- Checkout có thể đợi/quay về home region ra sao?
- Replication, backup và logs phải tuân thủ policy nào?
- Khi mất mạng EU↔VN, UI phải báo gì để không xác nhận booking sai?

### Phần H — Benchmark và fault injection

Thiết kế test:
1. Uniform booking IDs.
2. Một tenant chiếm 35% writes.
3. Một user chiếm 20% reads.
4. Query lịch sử 30 ngày.
5. Room/day conflict concurrent.
6. Failover đúng lúc tạo booking.
7. Mất ACK sau commit và retry.
8. Reshard 16 → 32 buckets.
9. Search indexer dừng 10 phút.
10. HBase-style sequential timestamp hotspot hoặc một NoSQL range-sharding tương đương.

Với mỗi test, ghi **p99, max/avg shard load, fan-out count, bytes scanned, timeout, duplicate/missing records, invariant violations và migration cost**.

### Phần I — Phản biện thiết kế

Một đồng nghiệp đề xuất:

> “Dùng tenantId làm shard key vì query nào cũng có tenant. Nếu tenant lớn quá cứ thêm node. Không cần quan tâm index vì NoSQL tự phân phối. Khi cần báo cáo thì scan 32 shard cũng không đáng kể.”

Hãy chỉ ra:
- TenantId có cardinality cao nhưng tải theo tenant bị lệch.
- Thêm node không chia một logical hot key nếu engine không hỗ trợ.
- Query status/user/room có access pattern khác.
- Scatter-gather có chi phí network/merge/tail latency.
- Bucket cải thiện phân phối nhưng tăng fan-out.
- Read projection giúp nhưng có lag và chi phí vận hành.
- Cần kiểm chứng engine-specific routing, indexes và benchmark.

### Gợi ý hướng giải

Một kiến trúc phù hợp có thể dùng **slot key** làm authority cho tính đúng của một lần giữ chỗ, **operationId** để tránh duplicate, và **read projections** theo user/room/status để tối ưu các truy vấn đặc thù. Nếu tenant lớn gây hotspot, thêm bucket theo định danh ổn định cùng routing version; chấp nhận fan-out có kiểm soát hoặc dùng projection để giảm chi phí đọc. Với IoT/time-series, bucket theo thời gian giới hạn partition size nhưng cần thêm salt/bucket nếu active window cực nóng. Không được bỏ qua **quorum, region placement, migration và query visibility** khi lựa chọn key.

## 34. Checklist quyết định shard key trước production

1. **Đã có ma trận access pattern thực tế và forecast chưa?**
2. **Những query nào nhất thiết phải target ít shard?**
3. **Có đo QPS/bytes/latency theo mỗi key không?**
4. **Top tenant/user/device chiếm bao nhiêu tải ở peak?**
5. **Cardinality có đủ và phân bố có thực sự đều không?**
6. **Key có tăng tuần tự gây tail hotspot không?**
7. **Hash/range/compound routing cụ thể của engine là gì?**
8. **Sort/range query có bị phá bởi hash/salt không?**
9. **Một logical key có thể bị split thành nhiều physical partitions không?**
10. **Một key nóng có cần bucketId bổ sung không?**
11. **BucketId có deterministic và ổn định qua retry không?**
12. **Có version hóa bucket count và routing metadata không?**
13. **Bất biến nào cần colocation hoặc transaction?**
14. **Unique constraint là global, tenant-local hay per-shard?**
15. **Idempotency ledger có được route ổn định không?**
16. **Shard key có đổi theo vòng đời record không?**
17. **Query thiếu routing field được hỗ trợ bằng index/read model nào?**
18. **Read projection có freshness SLO và reconciliation không?**
19. **Cross-shard query có p99/CPU/network budget rõ không?**
20. **Có test with skew, bursts và hot current time bucket không?**
21. **Có headroom cho compaction, repair, rebalance và recovery không?**
22. **Replica placement có đúng failure domain và residency không?**
23. **Có test mất ACK, failover và duplicate operation khi reshard không?**
24. **Tăng số shards có làm chi phí fan-out vượt SLO không?**
25. **Có con đường migration, cutover, rollback và audit được chưa?**

**Kết luận:** Chọn shard key trong NoSQL không phải bài toán “lấy cột unique nhất” hoặc “hash mọi thứ cho đều”, mà là **tối ưu có ràng buộc giữa mẫu truy cập, phân bố dung lượng, phân bố tải, locality, ranh giới nguyên tử và chi phí vận hành**. Một khóa tốt phải giúp những truy vấn quan trọng **định tuyến đúng phạm vi**, không để vài tenant/key/time range kéo cả cụm vào hotspot, đồng thời giữ đường xử lý **idempotency, transaction, failover và migration** đủ rõ. Khi các access pattern mâu thuẫn, hãy tách **source of truth** và **read projections/indexes** với hợp đồng độ mới minh bạch. Đánh giá trên **dữ liệu lệch thật và tải giờ cao điểm**, theo dõi **max shard load, fan-out, bytes scanned, p99 và correctness**, rồi chọn key theo bằng chứng thay vì theo tên trường.
