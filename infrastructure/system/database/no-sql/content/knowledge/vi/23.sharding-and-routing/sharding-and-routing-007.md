# Truy vấn một phân mảnh so với truy vấn nhiều phân mảnh

## 1. Bài toán mở đầu: cùng bảng Orders, vì sao hai truy vấn có chi phí khác xa nhau?

Giả sử một nền tảng thương mại điện tử có **120 triệu đơn hàng** được phân phối trên **12 shard**. Hệ cần phục vụ hai chức năng:

1. Khách hàng mở trang **“Đơn hàng của tôi”**.
2. Quản trị viên xem **“Tất cả đơn đã thanh toán trong 24 giờ qua”**.

Hai truy vấn minh họa:

~~~javascript
// Truy vấn A: chỉ quan tâm một tenant cụ thể.
db.orders.find({
  tenantId: "tenant-7",
  status: "PAID"
});

// Truy vấn B: không chỉ rõ tenant.
db.orders.find({
  status: "PAID"
});
~~~

Nếu collection được phân mảnh theo `tenantId` và quy tắc định tuyến có thể suy ra vị trí từ điều kiện bằng nhau trên shard key:

- Truy vấn A có thể là **targeted query**, được gửi đến **một shard**.
- Truy vấn B thường cần gửi đến **nhiều shard**, vì đơn `PAID` có thể nằm ở bất kỳ shard nào.

Không nên kết luận ngay “A nhanh còn B chậm”. A vẫn có thể chậm nếu tenant quá lớn hoặc không có index phù hợp; B có thể chạy hiệu quả nếu mỗi shard xử lý song song với index tốt. Tuy nhiên, B có thêm bài toán **fan-out, thu thập, tổng hợp, sắp xếp và kiểm soát tính nhất quán của kết quả**.

**Trọng tâm bài học:** hiểu khi nào hệ NoSQL định tuyến được request tới một phân mảnh, khi nào phải truy vấn nhiều phân mảnh, chi phí và bảo đảm khác nhau ở đâu, và cách thiết kế shard key cùng access pattern để tránh những fan-out không cần thiết.

### 1.1. Mục tiêu học tập

Sau bài, người đọc có thể:

1. Phân biệt **logical partition**, **physical shard**, **replica** và **router/coordinator**.
2. Xác định điều kiện nào giúp một truy vấn được **target** đến một hay vài shard.
3. Hiểu **scatter–gather**, **partition pruning**, fan-out và merge kết quả.
4. Phân tích chi phí latency, network, CPU, I/O, memory và tail latency.
5. Hiểu cách hoạt động của `ORDER BY`, `LIMIT`, aggregate, pagination và count khi dữ liệu trải nhiều shard.
6. Đánh giá shard key, composite key, hashed key, range key, time bucket và hotspot.
7. Đọc đúng ví dụ MongoDB sharding, Cassandra partition key, DynamoDB Query/Scan, Redis Cluster hash slot và Elasticsearch routing.
8. Thiết kế API Java chuyển access pattern thành truy vấn có định tuyến tốt.
9. Nhận diện sự khác biệt về consistency, transaction, failover và secondary index khi fan-out.
10. Xây bài đo hiệu năng và checklist vận hành dựa trên **số shard thực sự được truy cập**, không dựa trên tên truy vấn.

---

## 2. Thuật ngữ trước khi so sánh

| Thuật ngữ | Ý nghĩa trong bài | Điều không nên nhầm |
|---|---|---|
| **Logical partition** | Nhóm dữ liệu cùng khóa phân vùng logic | Không phải lúc nào cũng nằm trọn trên một máy vật lý |
| **Shard** | Đơn vị dữ liệu/hạ tầng được phân phối trong mô hình sharding của hệ | Không nhất thiết chỉ có một replica |
| **Shard key** | Thuộc tính dùng xác định vị trí/phạm vi phân mảnh | Không tự là một index đáp ứng mọi filter |
| **Partition key** | Khóa quy định phân phối dữ liệu trong Cassandra/DynamoDB và hệ tương tự | Cú pháp/semantics không giống shard key của mọi sản phẩm |
| **Routing key** | Thông tin giúp router xác định nơi gửi request | Không phải bằng chứng authorization |
| **Router / coordinator** | Thành phần xác định node/shard cần hỏi và gom kết quả | Không nhất thiết lưu toàn bộ dữ liệu |
| **Targeted query** | Truy vấn có thể gửi đến một tập shard nhỏ được xác định trước | Không mặc định một RPC hay một physical node |
| **Scatter–gather** | Phát truy vấn tới nhiều shard rồi gom/trộn kết quả | Không phải lúc nào cũng quét toàn bộ record |
| **Partition pruning** | Loại bớt partition/shard không thể chứa kết quả | Phụ thuộc cách đặt khóa và biểu thức filter |
| **Replica** | Bản sao cho cùng một shard/partition | Tăng replica không làm tăng số phân mảnh logic tương ứng |
| **Fan-out** | Số nhánh truy vấn được gửi tới các shard/partition/node | Không luôn bằng tổng số shard của cluster |
| **Hot shard** | Phân mảnh nhận tải hoặc dữ liệu lệch quá cao | Có thể xảy ra ngay cả với truy vấn một shard |

### 2.1. Một phân mảnh không nhất thiết là một máy

Một shard có thể có nhiều replica. Một node vật lý có thể chứa dữ liệu của nhiều logical partition hoặc nhiều shard. Hệ có thể chuyển vị trí shard khi rebalance.

~~~mermaid
flowchart LR
    C["Client"] --> R["Query router"]
    R --> S1["Shard 1"]
    R --> S2["Shard 2"]
    R --> S3["Shard 3"]
    S1 --- S1b["Replica 1B"]
    S2 --- S2b["Replica 2B"]
    S3 --- S3b["Replica 3B"]
~~~

Sơ đồ là **khái niệm**: trong một số DBMS, coordinator liên lạc replica theo read consistency, trong hệ khác nó chọn một bản copy của mỗi shard để thực thi truy vấn. Không dùng sơ đồ làm tài liệu mô tả giao thức của mọi NoSQL.

### 2.2. Tên gọi phụ thuộc sản phẩm

- MongoDB dùng **shard key**, `mongos` định tuyến dựa trên metadata/chunk placement.
- Cassandra dùng **partition key** để xác định các replica chịu trách nhiệm.
- DynamoDB dùng **partition key** trong mô hình dữ liệu, nhưng ánh xạ sang physical storage partition do dịch vụ quản lý.
- Redis Cluster định tuyến theo **hash slot**.
- Elasticsearch/OpenSearch có **primary shards**, replica shards và cơ chế **custom routing**.

Vì vậy, “truy vấn một phân mảnh” là mô hình chung. Để khẳng định chính xác nó truy cập bao nhiêu node, phải xem **query plan và contract của sản phẩm cụ thể**.

---

## 3. Sharding hoạt động như thế nào?

Giả sử ứng dụng có các đơn hàng:

~~~text
tenant-1 -> 12.000 orders
tenant-2 -> 25.000 orders
tenant-3 ->  9.000 orders
...
tenant-7 -> 80.000 orders
~~~

Một chiến lược đặt dữ liệu theo `tenantId` có thể phân phối:

~~~text
Shard A: tenant-1, tenant-7, ...
Shard B: tenant-2, tenant-8, ...
Shard C: tenant-3, tenant-9, ...
~~~

Router cần quy tắc:

\[
\text{targetShard}=f(\text{shardKey},\text{metadata/topology}).
\]

Hàm `f` có thể dựa trên hash, range/chunk mapping, partition tokens hoặc routing table. Không phải lúc nào cũng tính từ khóa bằng modulo đơn giản; khi rebalancing, vị trí vật lý có thể thay đổi.

### 3.1. Phân mảnh theo hash

Ví dụ minh họa:

\[
\mathrm{bucket}=\mathrm{hash}(\mathrm{tenantId})\bmod S
\]

với \(S\) là số bucket trong mô hình đơn giản.

Ưu điểm:

- Có xu hướng phân tán nhiều khóa tương đối đều khi phân bố tốt.
- Điều kiện bằng nhau trên toàn bộ hash key thường dễ target.
- Tránh một số điểm nóng do khóa tăng tuần tự.

Đánh đổi:

- Range của khóa gốc không nhất thiết nằm cạnh nhau.
- Query một khoảng nhiều khóa có thể phải chạm nhiều shard.
- Một khóa cực nóng vẫn nóng dù hash của khóa đó phân phối đều **giữa các khóa khác nhau**.
- Sơ đồ modulo thô không đại diện đầy đủ cơ chế chunk/token/placement của các sản phẩm thực.

### 3.2. Phân mảnh theo range

Ví dụ:

~~~text
Shard A: orderId [0000..2999]
Shard B: orderId [3000..5999]
Shard C: orderId [6000..8999]
~~~

Ưu điểm:

- Query theo một khoảng key có thể được **partition pruning**.
- Có thể hữu ích cho workload theo thời gian hoặc miền ID.

Đánh đổi:

- Nếu orderId/timestamp tăng dần, write mới có thể tập trung vào shard cuối.
- Dữ liệu và tải không đều khi range có phân bố lệch.
- Query trên thuộc tính khác shard key vẫn có thể scatter.

### 3.3. Composite shard key

Ví dụ key logic:

~~~text
(tenantId, orderMonth)
(tenantId, bucketId)
(region, productId)
~~~

Lợi ích: phục vụ một số truy vấn theo tenant, tháng hoặc bucket.

Nhưng **có điều kiện trên một phần composite key** chưa chắc chỉ target một shard. Điều này phụ thuộc thứ tự trường, hash/range semantics, chunk placement và query planner.

Chẳng hạn:

~~~text
Query tenantId = tenant-7, orderMonth = 2026-11
  -> có thể định tuyến hẹp.

Query tenantId = tenant-7, không có orderMonth
  -> có thể cần nhiều bucket/shard.

Query orderMonth = 2026-11, không có tenantId
  -> có thể phải fan-out rộng.
~~~

Không thể suy ra từ tên hai trường rằng mọi query với `tenantId` đều chạm một physical shard.

---

## 4. Targeted query: khi router biết nơi cần hỏi

Một **targeted query** là truy vấn có điều kiện đủ để router xác định một hoặc một số shard có khả năng chứa kết quả.

Ví dụ hệ có shard key đơn trường `tenantId`, hash theo tenant:

~~~json
{
  "tenantId": "tenant-7",
  "orderId": "order-9001",
  "status": "PAID",
  "createdAt": "2026-11-14T08:00:00Z"
}
~~~

Query:

~~~javascript
db.orders.find({
  tenantId: "tenant-7",
  status: "PAID"
});
~~~

Nếu `tenantId="tenant-7"` ánh xạ tới một shard trong cấu hình đang xét, router không cần gửi query tới mọi shard.

### 4.1. Điều kiện đủ để target phụ thuộc shard key

Câu hỏi quan trọng:

- Filter có ràng buộc **đúng trường shard key** không?
- Ràng buộc là equality hay range?
- Có đầy đủ các thành phần composite key cần thiết không?
- Filter ở dạng mà planner có thể suy luận/partition prune không?
- Metadata định tuyến có cập nhật không?
- Có rebalancing hoặc migration khiến query cần phối hợp bổ sung không?

Không chỉ hỏi: “Trong WHERE có tenantId không?”

### 4.2. Targeted không có nghĩa query nhanh nếu thiếu index

Giả sử tenant-7 chứa 50 triệu Order trong cùng shard.

~~~javascript
db.orders.find({
  tenantId: "tenant-7",
  status: "PAID"
});
~~~

Nếu không có index hỗ trợ, shard được target vẫn có thể phải đọc/quét rất nhiều record. Một query vào một shard có thể chậm hơn query vào 8 shard mà mỗi shard lọc hiệu quả theo index.

Do đó cần đo ít nhất **hai chiều độc lập**:

1. **Routing:** chạm bao nhiêu shard?
2. **Execution:** trên mỗi shard đọc bao nhiêu record/index key và tốn bao nhiêu I/O?

### 4.3. Targeted có thể là một vài shard, không nhất thiết đúng một

Ví dụ range shard key trên order date:

~~~text
Shard A: tháng 01-04
Shard B: tháng 05-08
Shard C: tháng 09-12
~~~

Truy vấn tháng 10–11 có thể chỉ cần C, còn tháng 08–10 chạm B và C. Chúng đều là kết quả của **partition pruning**, dù một truy vấn chạm hơn một shard.

### 4.4. Không bỏ qua replica

Một query logic target một shard vẫn có thể liên quan nhiều replica để đạt consistency level; ví dụ Cassandra `LOCAL_QUORUM` đọc nhiều replica cho **một partition**.

Vì vậy phải phân biệt:

- Số **logical partitions/shards** được target.
- Số **replicas** được liên hệ.
- Số **RPCs** và coordinator stages.

---

## 5. Scatter–gather: khi phải hỏi nhiều shard

Nếu filter không ràng buộc shard key, router có thể không biết shard nào chứa kết quả.

~~~javascript
db.orders.find({
  status: "PAID"
});
~~~

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Query router
    participant A as Shard A
    participant B as Shard B
    participant D as Shard C

    C->>R: Find status=PAID
    R->>A: Execute local filter
    R->>B: Execute local filter
    R->>D: Execute local filter
    A-->>R: Local results
    B-->>R: Local results
    D-->>R: Local results
    R->>R: Merge / sort / aggregate
    R-->>C: Global result
~~~

Các bước:

1. **Scatter:** gửi truy vấn tới các shard có khả năng chứa dữ liệu.
2. **Local execution:** mỗi shard áp dụng filter, index, aggregation hoặc sort tương ứng.
3. **Gather:** trả record hoặc partial results về coordinator.
4. **Merge:** phối hợp để tạo kết quả logic cuối.
5. **Respond:** gửi về client theo pagination/streaming và consistency policy.

### 5.1. Scatter không tự là full table scan

Nếu `status` được index tốt trên từng shard, mỗi shard có thể dùng local index để tìm những record phù hợp. Query có thể fan-out tới 12 shard nhưng **không đọc hết 120 triệu document**.

Điều ngược lại cũng đúng: nếu không có index, cả 12 shard có thể scan nhiều record, gây chi phí khổng lồ.

### 5.2. Fan-out không phải luôn bằng số shard toàn cluster

Router có thể loại bớt những shard không liên quan thông qua:

- Equality hoặc range trên shard key.
- Partition/bucket theo ngày/tháng.
- Routing metadata.
- Query trên một tập tenant/key nhỏ biết trước.
- Index-level hoặc partition-level pruning mà hệ hỗ trợ.

Vì vậy cần đo **actual shards contacted**, không lấy tổng cluster size làm số fan-out mặc định.

### 5.3. Khi scatter–gather là cần thiết

Một số nghiệp vụ vốn cần xem toàn cục:

- Tổng doanh thu tất cả tenant.
- Top 100 sản phẩm bán chạy toàn hệ.
- Tìm kiếm theo từ khóa xuyên mọi tenant được phép.
- Phát hiện gian lận liên vùng.
- Báo cáo tháng toàn doanh nghiệp.
- Dữ liệu quản trị hoặc phân tích offline.

Mục tiêu không phải **loại bỏ mọi multi-shard query**, mà là đặt chúng ở đúng hạ tầng, thời gian và giới hạn tài nguyên.

---

## 6. So sánh targeted và scatter–gather

| Tiêu chí | Targeted query | Multi-shard query |
|---|---|---|
| Định tuyến | Thường xác định shard từ key/metadata | Phải gửi đến nhiều shard có thể liên quan |
| Số nhánh | Thường thấp | Tăng theo số shard/bucket được hỏi |
| Network | Ít đầu mối trao đổi hơn | Nhiều RPC và trả kết quả partial |
| Query planning | Ít phạm vi phối hợp | Cần scatter/merge và đôi khi multi-stage |
| Local index | Vẫn cực kỳ quan trọng | Quan trọng trên **từng shard** |
| Latency | Ít phụ thuộc slow shard khác | Thường bị ảnh hưởng bởi nhánh chậm nhất cần chờ |
| Aggregate | Có thể tính cục bộ | Cần tổng hợp partials |
| Global sort | Dễ hơn nếu toàn data đã đủ | Cần merge sort/top-K |
| Pagination | Cursor/index cục bộ thường đơn giản hơn | Có thể cần nhiều cursor/merge state |
| Failure | Lỗi shard đích ảnh hưởng request | Một shard lỗi có thể ảnh hưởng kết quả toàn cục |
| Consistency | Phạm vi hẹp hơn | Snapshot/watermark toàn cục khó hơn |
| Công suất | Hot shard có thể là điểm nghẽn | Coordinator, mạng và nhiều shard chịu tải |
| Tối ưu điển hình | Index, key, tránh hot key | Pruning, pre-aggregation, bounded fan-out |
| Chi phí | Tùy lượng dữ liệu trong shard | Tùy tổng lượng đọc và merge overhead |

**Không có quy tắc “1 shard luôn tốt hơn 2 shard”.** Câu trả lời đúng phụ thuộc access pattern, index, lượng dữ liệu và SLO.

---

## 7. Mô hình chi phí và tail latency

Giả sử một request target \(S\) shard, những shard đó chạy song song.

Một mô hình đơn giản:

\[
T_{\text{query}}
\approx
T_{\text{route}}
+
\max_{i=1..S} T_{\text{shard},i}
+
T_{\text{merge}}
+
T_{\text{network}}.
\]

Đây là **mô hình trực giác**, không phải công thức chính xác cho mọi engine. Khi concurrency bị giới hạn, có nhiều vòng scatter hoặc streaming pipeline, thời gian có thể phụ thuộc cả scheduling, queue và số batch.

### 7.1. Vì sao phải chờ shard chậm?

Nếu request cần **kết quả đầy đủ**, coordinator thường không thể kết thúc khi còn một shard chưa trả phần dữ liệu cần thiết.

Ví dụ:

~~~text
Shard A:  8 ms
Shard B: 12 ms
Shard C: 35 ms
Shard D: 10 ms

Coordinator phải có kết quả cả bốn shard.
~~~

Khi xử lý song song, phần chờ local-result có thể gần với nhánh chậm nhất **35 ms**, chưa tính routing/merge/network.

Nếu query contract cho phép partial results hoặc approximate answer, hành vi khác; phải ghi rõ với người dùng.

### 7.2. Tail latency tăng khi fan-out

Giả sử mỗi shard độc lập có xác suất 99% phản hồi trước mốc 100 ms. Nếu cần **cả 12 shard**:

\[
P(\text{mọi shard dưới 100 ms})
\approx0.99^{12}
\approx0.886.
\]

Khoảng **88,6%**, không còn 99%, trong giả định độc lập và cùng phân bố.

Đây là phép tính minh họa. Trên hệ thật, latency giữa các shard có thể tương quan do cùng network, disk, GC, coordinator hoặc overload; không dùng con số trên làm SLA sản phẩm.

### 7.3. Có thể tăng throughput nhờ song song

Một truy vấn nhiều shard có thể xử lý nhanh hơn một single-shard scan khổng lồ, vì các shard cùng sử dụng tài nguyên CPU/I/O độc lập.

Nhưng điều đó không có nghĩa nó “rẻ”: tổng I/O và tác động đến tải của các tenant khác có thể tăng.

### 7.4. Chi phí coordinator

Coordinator có thể cần:

- Giữ buffer kết quả.
- Merge theo sort key.
- Aggregate partial states.
- Theo dõi cursor nhiều shard.
- Retry nhánh lỗi.
- Giữ session/consistency metadata.
- Phân bổ memory cho group-by hoặc distinct.

Nếu nhiều truy vấn toàn cục chạy đồng thời, **coordinator trở thành bottleneck** dù từng shard chưa đầy tải.

### 7.5. Đo theo request class

Phải phân biệt:

~~~text
GET /orders/me         -> thường target nhỏ
GET /orders/search     -> có thể target subset
GET /admin/all-orders  -> thường fan-out
GET /analytics/revenue -> nên có read model/OLAP riêng
~~~

SLO riêng giúp tránh tối ưu nhầm đường quan trọng nhất.

---

## 8. Shard key và access pattern: quyết định từ đầu

Một shard key tốt phải dựa vào **những câu hỏi ứng dụng cần trả lời**, không chỉ làm dữ liệu chia đều.

### 8.1. Bắt đầu từ danh sách truy vấn

Ví dụ:

| Truy vấn | Tần suất | Có giới hạn tenant? | Thời gian mong muốn |
|---|---|---|---|
| Đơn của một khách trong tenant | Rất cao | Có | p99 thấp |
| Chi tiết một Order theo ID | Cao | Có nếu thiết kế API tốt | p99 thấp |
| Báo cáo tuần trong tenant | Trung bình | Có | Có thể vài giây |
| Top sản phẩm mọi tenant | Thấp | Không | Batch/analytics |
| Tra cứu theo payment ID | Trung bình | Có thể không | Cần index hoặc lookup table |
| Tìm đơn trong một ngày toàn hệ | Thấp/trung bình | Không | Cần chấp nhận fan-out hoặc read model |

Chọn shard key để **những truy vấn quan trọng nhất** có routing rõ. Không thể làm tất cả truy vấn bất kỳ thành single-shard chỉ với một shard key.

### 8.2. Shard key tenantId

Ưu:

- Các truy vấn theo tenant thường dễ target.
- Dễ áp dụng tenant boundary trong API.
- Locality tốt cho một số thao tác cùng tenant.

Nhược:

- Tenant cực lớn/hot có thể không phân phối tải đều nếu mọi dữ liệu của tenant bị buộc ở một shard.
- Truy vấn theo `orderId` không có tenantId có thể phải scatter.
- Truy vấn toàn hệ cần fan-out.

### 8.3. Shard key orderId hashed

Ưu:

- Phân tán write theo nhiều giá trị order ID.
- Lookup theo orderId có thể target shard khi key đầy đủ.
- Tránh một số hotspot do orderId tăng tuyến tính.

Nhược:

- `GET /tenants/{id}/orders` không biết orderId nên có thể fan-out.
- Báo cáo theo tenant/thời gian khó giữ locality.
- Query range theo orderId không được định tuyến như range gốc.

### 8.4. Composite key tenant + bucket

Ví dụ:

~~~text
tenantId = tenant-7
bucket = 2026-11
orderId = order-9001
~~~

Lợi ích:

- Có thể truy vấn một tenant + tháng với phạm vi tương đối hẹp.
- Giới hạn độ lớn của một partition/bucket.
- Phù hợp dữ liệu time-series hoặc order history.

Đánh đổi:

- Query 24 tháng phải hỏi tối đa 24 bucket logic.
- Tenant cực nóng trong một tháng vẫn có thể là hotspot.
- Nếu orderId chỉ được biết mà không biết bucket, phải có cách tìm bucket hoặc lookup index.
- Một bucket logic không nhất thiết tương đương một physical shard trên mọi sản phẩm.

### 8.5. Đừng chọn chỉ vì cardinality cao

Cardinality cao có thể giúp phân tán, nhưng phải xem:

- Tỷ lệ request theo key có lệch không?
- Query cần cùng nhóm dữ liệu nào?
- Một partition có bị quá lớn không?
- Có cần transaction theo nhóm dữ liệu không?
- Client có biết shard key ở request không?
- Key có thay đổi theo thời gian không?
- Cần global search/secondary index bao nhiêu?
- Khi tăng shard count, routing và migration ra sao?

**Shard key là quyết định đồng thời về phân phối tải và khả năng định tuyến.**

---

## 9. MongoDB: targeted query so với scatter–gather

MongoDB sharded cluster thường dùng `mongos` để định tuyến tới shard dựa trên **shard key và metadata về chunk placement**.

### 9.1. Ví dụ collection Orders

Giả sử dữ liệu:

~~~json
{
  "_id": "order-9001",
  "tenantId": "tenant-7",
  "customerId": "customer-42",
  "status": "PAID",
  "totalVnd": 750000,
  "createdAt": "2026-11-14T08:00:00Z"
}
~~~

Với một collection đã được shard theo **hashed shard key `tenantId`**:

~~~javascript
// Minh họa thao tác cấu hình sharding.
// Chỉ sử dụng sau khi đã lập kế hoạch index,
// dữ liệu, phiên bản và topology MongoDB phù hợp.
sh.shardCollection(
  "shop.orders",
  { tenantId: "hashed" }
);
~~~

Đây là ví dụ minh họa schema. Cấu hình một sharded collection thực tế cần kiểm tra các điều kiện index, uniqueness, shard key, dữ liệu sẵn có và hành vi phiên bản MongoDB. Không chạy trực tiếp trên production chỉ vì ví dụ.

### 9.2. Query đủ shard key: có thể target một shard

~~~javascript
db.orders.find({
  tenantId: "tenant-7",
  status: "PAID"
});
~~~

Với equality trên **toàn bộ single-field hashed shard key**, router có thể xác định shard chịu trách nhiệm cho giá trị key đó.

### 9.3. Query thiếu shard key: thường scatter

~~~javascript
db.orders.find({
  status: "PAID"
});
~~~

Nếu `status` không xác định vị trí shard, router thường phải gửi tới những shard có thể chứa bản ghi phù hợp.

### 9.4. Compound index cho local execution

Ngay cả khi router target đúng shard, cần index hỗ trợ filter/sort:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

Ví dụ:

~~~javascript
db.orders.find({
  tenantId: "tenant-7",
  status: "PAID"
})
.sort({
  createdAt: -1,
  _id: -1
})
.limit(50);
~~~

Index thường giúp shard lọc và trả theo thứ tự hiệu quả hơn. Cần kiểm tra actual execution plan, selectivity, cardinality và khả năng dùng index thay vì suy luận chỉ từ thứ tự trường.

### 9.5. Dùng explain để quan sát routing

~~~javascript
db.orders.find({
  tenantId: "tenant-7",
  status: "PAID"
}).explain("executionStats");
~~~

Và:

~~~javascript
db.orders.find({
  status: "PAID"
}).explain("executionStats");
~~~

Tùy phiên bản MongoDB và dạng kế hoạch, kết quả có thể thể hiện các shard tham gia, số document/index key được đọc, merge stage và execution statistics. **Cấu trúc JSON của explain thay đổi theo phiên bản/kế hoạch**; mục tiêu là nhận ra **targeted vs scatter và lượng công việc thực**, không hard-code một field explain duy nhất.

### 9.6. Range query với hashed shard key

~~~javascript
db.orders.find({
  tenantId: { $gte: "tenant-1", $lt: "tenant-9" }
});
~~~

Không nên suy luận truy vấn range trên giá trị tenant gốc được target vào một khoảng shard liền kề khi key được hash. Hash giữ equality routing nhưng không bảo toàn thứ tự range của giá trị gốc.

### 9.7. Một tenant quá lớn

Sharding chỉ theo `tenantId` có thể khiến mọi Order của tenant cực lớn tập trung vào một giá trị shard key, tạo hotspot hoặc giới hạn khả năng tách tải theo một số layout.

Một phương án khác có thể dùng thêm `orderId`, time bucket hoặc virtual bucket vào shard key. Nhưng khi đó query chỉ có tenantId **có thể phải truy cập nhiều shard**. Đây là đánh đổi thực tế giữa **locality và khả năng phân tán hot tenant**.

### 9.8. Khi cần update nhiều document/shard

MongoDB hỗ trợ transaction trong các phạm vi/topology phù hợp, kể cả một số tình huống transaction xuyên shard, nhưng chi phí/giới hạn khác thao tác một document. Không kết luận “targeted query” đồng nghĩa transaction hoặc aggregation nhiều document tự atomic.

---

## 10. Cassandra: partition key quyết định access path

Cassandra hướng đến truy cập theo **partition key**. Tổ chức schema phải bắt đầu từ những truy vấn cần phục vụ.

### 10.1. Bảng theo tenant và tháng

~~~sql
CREATE TABLE orders_by_tenant_month (
  tenant_id text,
  order_month text,
  created_at timestamp,
  order_id text,
  customer_id text,
  status text,
  total_vnd bigint,
  PRIMARY KEY (
    (tenant_id, order_month),
    created_at,
    order_id
  )
) WITH CLUSTERING ORDER BY (
  created_at DESC,
  order_id ASC
);
~~~

Trong bảng này:

- Partition key là **`(tenant_id, order_month)`**.
- Clustering columns là **`created_at`, `order_id`**.
- Các row thuộc một tenant và tháng được nhóm trong cùng **logical partition**.
- Đặt tháng vào partition key nhằm giới hạn kích thước partition theo thời gian.

### 10.2. Truy vấn một partition

~~~sql
SELECT order_id, created_at, status, total_vnd
FROM orders_by_tenant_month
WHERE tenant_id = 'tenant-7'
  AND order_month = '2026-11'
LIMIT 50;
~~~

Đủ hai thành phần partition key nên Cassandra xác định được nhóm replica chịu trách nhiệm. Query có thể được phục vụ từ một hoặc nhiều replica tùy consistency level.

**Một partition logic không đồng nghĩa một RPC hoặc một physical máy**, đặc biệt khi `LOCAL_QUORUM` cần nhiều replica.

### 10.3. Range trên clustering column

~~~sql
SELECT order_id, created_at, status, total_vnd
FROM orders_by_tenant_month
WHERE tenant_id = 'tenant-7'
  AND order_month = '2026-11'
  AND created_at >= '2026-11-10T00:00:00Z'
  AND created_at <  '2026-11-15T00:00:00Z';
~~~

Khi biết partition key đầy đủ, truy vấn có thể tìm một khoảng clustering key bên trong partition.

### 10.4. Truy vấn 12 tháng

Yêu cầu:

~~~text
Hiển thị 50 đơn hàng mới nhất
của tenant-7 trong 12 tháng.
~~~

Với mô hình trên, ứng dụng thường cần đọc nhiều `order_month` partitions rồi merge kết quả. Không thể bỏ `order_month` trong partition key và giả định Cassandra tự làm một truy vấn toàn bảng tối ưu.

Một chiến lược là fan-out có giới hạn 12 partition:

~~~text
P1 = (tenant-7, 2026-11)
P2 = (tenant-7, 2026-10)
...
P12 = (tenant-7, 2025-12)
~~~

Nếu dữ liệu được sắp mới nhất trước, ứng dụng có thể truy vấn tháng gần nhất và mở rộng dần tới tháng cũ theo quy tắc đảm bảo đủ kết quả; cách làm này thường tốt hơn phát 12 query ngay nếu 50 đơn đều nằm trong tháng hiện tại.

Nhưng nếu query cần **global aggregate toàn kỳ**, vẫn phải xem tất cả partition có dữ liệu liên quan hoặc có summary/read model phù hợp.

### 10.5. Không dùng ALLOW FILTERING để “sửa” schema bất hợp lý

Một truy vấn thiếu partition key hoặc filter không được index hỗ trợ có thể cần truy cập lượng dữ liệu lớn và gặp hạn chế CQL.

`ALLOW FILTERING` không làm scan toàn cluster tự trở nên rẻ. Nó cho phép những kiểu filter nhất định với chi phí có thể lớn. Cần thiết kế thêm table theo access pattern, materialized view hoặc search/analytics layer thay vì ép OLTP table phục vụ mọi query.

### 10.6. Cassandra có nhiều replica cho một partition

Nếu RF=3 và CL=`LOCAL_QUORUM`, một query logic một partition có thể cần phối hợp nhiều replica. Phạm vi **partition routing** và **replica consistency** là hai chiều khác nhau.

### 10.7. Bảng thứ hai cho truy vấn khác

Nếu API thường tìm Order theo `order_id`, có thể cần một bảng truy cập khác:

~~~sql
CREATE TABLE order_by_id (
  order_id text PRIMARY KEY,
  tenant_id text,
  order_month text,
  status text,
  total_vnd bigint
);
~~~

Đây là dạng **query-driven denormalization**. Hệ phải quản lý cập nhật nhiều bảng và tính nhất quán giữa chúng theo workflow phù hợp. Tạo bảng riêng giúp truy vấn nhanh theo order ID nhưng không tự làm các bảng cập nhật atomic như một SQL transaction đa partition.

---

## 11. DynamoDB: Query theo partition key khác Scan toàn bảng

DynamoDB sử dụng **partition key** và tùy chọn **sort key** làm primary key của table/index.

### 11.1. Thiết kế khóa theo tenant và tháng

Ví dụ schema logic:

~~~text
PK = TENANT#tenant-7#MONTH#2026-11
SK = ORDER#2026-11-14T08:00:00Z#order-9001
~~~

Các item trong cùng PK có sort key phục vụ truy vấn theo thời gian.

### 11.2. Query với key condition

AWS SDK JavaScript v3 minh họa:

~~~javascript
import { QueryCommand } from "@aws-sdk/lib-dynamodb";

const result = await documentClient.send(
  new QueryCommand({
    TableName: "Orders",
    KeyConditionExpression:
      "PK = :pk AND SK BETWEEN :start AND :end",
    ExpressionAttributeValues: {
      ":pk": "TENANT#tenant-7#MONTH#2026-11",
      ":start": "ORDER#2026-11-01",
      ":end": "ORDER#2026-11-30~"
    },
    ScanIndexForward: false,
    Limit: 50
  })
);
~~~

Đoạn minh họa dùng sort key chuỗi có thứ tự lexicographic phù hợp với format thời gian/ID nhất quán. Trong production cần thiết kế cận range chính xác, timezone và pagination; `~` chỉ là ví dụ ký tự cận trên, không phải phương pháp phổ quát cho mọi schema.

Điểm chính: `Query` yêu cầu partition key equality, cho phép tập trung vào một **logical item collection**. DynamoDB có thể quản lý physical partition/split nội bộ; **không suy ra một PK = đúng một physical shard duy nhất**.

### 11.3. Query nhiều tháng

Để lấy dữ liệu 12 tháng, ứng dụng có thể cần nhiều Query theo các PK khác nhau. Có thể dừng sớm nếu access pattern cho phép, hoặc merge top-K giữa các tháng khi cần chính xác.

Với hệ lớn, cần giới hạn fan-out và xử lý **một hoặc nhiều `LastEvaluatedKey`**, thay vì cho rằng một response Query đã chứa toàn bộ dữ liệu.

### 11.4. Scan với filter

~~~javascript
import { ScanCommand } from "@aws-sdk/lib-dynamodb";

const result = await documentClient.send(
  new ScanCommand({
    TableName: "Orders",
    FilterExpression: "#s = :paid",
    ExpressionAttributeNames: {
      "#s": "status"
    },
    ExpressionAttributeValues: {
      ":paid": "PAID"
    }
  })
);
~~~

`Scan` có thể đọc trên phạm vi rộng của table và chỉ **lọc sau khi đọc**. `FilterExpression` không biến nó thành key-based Query, cũng không tự giảm số item đã được đọc để tính read capacity như một index phù hợp.

Không dùng Scan cho request latency thấp có volume lớn chỉ vì response cuối cùng trả ít record.

### 11.5. GSI cho access pattern khác

Nếu cần tìm Order theo payment ID hoặc status, một Global Secondary Index có thể tạo access path riêng.

Nhưng:

- GSI sử dụng key và storage/access structure riêng.
- GSI có **eventual-consistent reads**, không hỗ trợ strongly consistent reads như base table.
- Một GSI với partition key `status` rất ít giá trị có thể tạo hot key khi status như `PAID` tập trung mạnh.
- Query GSI theo status không tự giúp các aggregate toàn hệ rẻ nếu giá trị quá phổ biến.

### 11.6. Chi tiết trang và giới hạn xử lý

Một Query/Scan response có thể bị phân trang bởi giới hạn của dịch vụ (trong DynamoDB có giới hạn dữ liệu đọc mỗi trang trước khi filter) và dùng `LastEvaluatedKey` để tiếp tục. Giá trị `Limit` của Query/Scan liên quan **số item được đánh giá**, không phải bảo đảm đúng số item sau khi filter.

Không được coi số item trả về ít hơn `Limit` là chứng cứ đã đọc hết nếu còn `LastEvaluatedKey`.

### 11.7. Strong read không đồng nghĩa global snapshot

Base-table `GetItem`/`Query` có thể yêu cầu `ConsistentRead: true` khi được hỗ trợ. Điều này không biến chuỗi Query qua 12 PK và nhiều region thành một snapshot atomic xuyên toàn dữ liệu.

---

## 12. Redis Cluster: hash slot và ranh giới nhiều key

Redis Cluster phân phối key vào **16.384 hash slot** theo quy tắc hash của Redis Cluster; các slot được gán cho các node.

### 12.1. Một key có slot xác định

~~~text
Key: order:9001
Hash slot: CRC16(key) mod 16384
~~~

Một client Redis Cluster hỗ trợ topology sẽ định tuyến lệnh theo slot và xử lý redirect phù hợp khi placement thay đổi.

### 12.2. Hash tags để đặt key cùng slot

Các key:

~~~text
{tenant-7}:orders:9001
{tenant-7}:orders:9002
{tenant-7}:orders:index
~~~

có cùng nội dung trong `{...}`, nên được hash theo `tenant-7` theo semantics hash tag, giúp các thao tác multi-key hợp lệ của Redis Cluster cùng slot.

**Đây là chiến lược locality**, nhưng cũng có thể tạo **hot slot** nếu mọi key của một tenant khổng lồ cùng nằm tại một node.

### 12.3. Multi-key operation cross-slot

Ví dụ `MGET` hoặc Lua script tham chiếu nhiều key thuộc slot khác nhau có thể bị Redis Cluster từ chối với lỗi `CROSSSLOT` tùy loại thao tác.

Redis Cluster không mặc định chạy một transaction/aggregation phân tán tùy ý trên tất cả slot như một SQL engine. Ứng dụng hoặc tầng truy vấn phải chủ động fan-out và merge khi cần đọc nhiều key thuộc nhiều slot.

### 12.4. MOVED và ASK

Khi cluster topology thay đổi, client có thể nhận redirect như `MOVED` hoặc `ASK` theo giao thức Redis Cluster. Routing cache ở client có thể cần cập nhật.

Không nên hard-code node ID từ hash rồi gọi trực tiếp bất chấp thay đổi topology; sử dụng Redis Cluster client phù hợp.

### 12.5. Độ bền và consistency là câu hỏi khác

Một key được route đúng slot không tự có nghĩa:

- Replica đã nhận write.
- AOF đã fsync.
- Read từ replica không stale.
- Multi-key workflow trở thành atomic xuyên slot.

Routing giải quyết “gửi đi đâu”; durability/replication/atomicity giải quyết những thuộc tính khác.

---

## 13. Elasticsearch/OpenSearch: định tuyến và fan-out khi tìm kiếm

Elasticsearch/OpenSearch thường tìm kiếm trên các **primary shard groups** của index và phối hợp kết quả từ các shard liên quan. Một search có thể là fan-out tới nhiều shard, sau đó merge partial results.

### 13.1. Query mặc định trên index

~~~http
GET /orders/_search
Content-Type: application/json

{
  "query": {
    "term": {
      "status.keyword": "PAID"
    }
  },
  "size": 20
}
~~~

Ví dụ này có thể cần tìm trên nhiều shard của `orders`, tùy index topology, alias/filter và query planner. Số shard search được chọn không nhất thiết là mọi replica copy; search có thể dùng một bản phù hợp của mỗi shard group.

### 13.2. Custom routing khi index và search thống nhất

Khi document đã được **index với routing key `tenant-7`**, query có thể cung cấp routing tương ứng:

~~~http
GET /orders/_search?routing=tenant-7
Content-Type: application/json

{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId.keyword": "tenant-7" } }
      ]
    }
  },
  "size": 20
}
~~~

Routing có thể giảm tập shard cần tìm theo quy tắc của index. Tuy nhiên:

- Routing **phải khớp cách document đã được index**, nếu không có thể bỏ sót dữ liệu.
- Một số chế độ phân hoạch routing có thể target nhiều shard.
- `routing=tenant-7` **không phải kiểm tra phân quyền**; filter và authorization vẫn bắt buộc.
- Một tenant quá nóng có thể tạo shard hotspot.
- Cần xem phiên bản và cấu hình index cụ thể.

### 13.3. Search engine không thay thế source transaction

Một document mới được commit ở source DB có thể chưa xuất hiện trong search index do CDC/index lag hoặc refresh semantics.

Kết quả search cũ là vấn đề **index freshness**, không tự chứng minh source write thất bại.

### 13.4. Nhiều shard và top-K

Một search top 20 có thể thu các ứng viên từ nhiều shard rồi merge theo score/sort. Tài nguyên cần cho truy vấn phụ thuộc số shard, hit count, scoring, aggregations và cấu hình search engine. Không suy rằng chỉ trả 20 kết quả nghĩa engine đọc đúng 20 document.

---

## 14. Global ORDER BY và LIMIT: không thể lấy ngẫu nhiên 20 kết quả

Truy vấn:

~~~sql
SELECT *
FROM Orders
WHERE status = 'PAID'
ORDER BY createdAt DESC, orderId DESC
LIMIT 20;
~~~

Nếu dữ liệu nằm trên 8 shard, mỗi shard có dữ liệu theo thời gian khác nhau. Muốn **global top 20**, coordinator không thể chỉ lấy 20 record bất kỳ từ một shard.

### 14.1. K-way merge

Giả sử mỗi shard đã lọc và sắp xếp theo cùng khóa toàn phần:

~~~text
Shard A: [99, 94, 70, ...]
Shard B: [98, 95, 90, ...]
Shard C: [97, 93, 89, ...]
~~~

Cần merge:

~~~text
Global: [99, 98, 97, 95, 94, 93, 90, 89, ...]
~~~

Một thuật toán k-way merge sử dụng heap có thể tốn gần:

\[
O(K\log S)
\]

cho K kết quả đầu với S luồng đã sắp xếp, bỏ qua chi phí local sort/filter và đọc thêm dữ liệu.

### 14.2. Mỗi shard lấy top-K có đủ không?

Với **cùng filter**, **cùng total ordering xác định**, và mỗi shard trả **top K đầy đủ theo local order**, mọi record thuộc global top K đều nằm trong top K của shard chứa nó.

Do đó có thể:

~~~text
S=12 shards
K=20
Mỗi shard gửi tối đa 20 candidates.
Coordinator merge tối đa 240 candidates -> global top 20.
~~~

Đây là một cách giảm lượng dữ liệu truyền về, nhưng **không có nghĩa mỗi shard chỉ đọc 20 record**. Nó có thể phải sử dụng index hoặc quét nhiều dữ liệu để tìm top K hợp lệ.

### 14.3. Cần tie-breaker ổn định

Nếu nhiều Order có cùng `createdAt`, sort chỉ theo `createdAt DESC` có thể khiến thứ tự giữa các request không ổn định.

Nên thêm một khóa duy nhất/tổng thứ tự, ví dụ:

~~~text
ORDER BY createdAt DESC, orderId DESC
~~~

trong phạm vi hệ hỗ trợ. Với dữ liệu phân tán, hai shard cần cùng quy tắc so sánh; không được dùng local insertion order làm tie-breaker.

### 14.4. LIMIT không thay thế việc lọc đúng

Nếu filter chỉ được áp dụng **sau** khi shard đã cắt top 20, kết quả toàn cục có thể thiếu những record đáng lẽ phải có. Muốn đúng, planner phải xét filter và sort trong thứ tự hợp lệ.

### 14.5. OFFSET sâu rất tốn

Ví dụ:

~~~text
OFFSET 500000 LIMIT 20
~~~

Coordinator có thể phải xử lý rất nhiều ứng viên trước khi bỏ qua phần đầu. Fan-out và sort memory tăng mạnh.

Hãy cân nhắc **keyset pagination**, cursor hoặc search-after với thứ tự ổn định, tùy database hỗ trợ.

---

## 15. Pagination xuyên nhiều shard

Giả sử client tải hai page, mỗi page 20 Order. Page 1 và page 2 có thể xảy ra ở hai thời điểm.

### 15.1. OFFSET pagination và dữ liệu đang thay đổi

~~~text
T1: Page 1 lấy record 1..20.
T2: Có 3 Order mới chèn đầu danh sách.
T3: Page 2 dùng OFFSET 20.
~~~

Page 2 có thể trùng record đã thấy trong page 1 hoặc bỏ sót record khác, tùy thứ tự và thay đổi.

Tình huống này có thể xảy ra cả trong một shard, nhưng ở nhiều shard còn có **nhiều cursor và trạng thái merge**, khiến khó quan sát hơn.

### 15.2. Keyset pagination

Dùng sort:

~~~text
createdAt DESC, orderId DESC
~~~

Response page đầu trả cursor gồm:

~~~json
{
  "lastCreatedAt": "2026-11-14T08:00:00Z",
  "lastOrderId": "order-9001"
}
~~~

Page tiếp theo dùng điều kiện “nhỏ hơn cặp sort key đã trả” theo thứ tự giảm:

~~~text
createdAt < lastCreatedAt
OR (createdAt == lastCreatedAt AND orderId < lastOrderId)
~~~

Đây là mẫu logic; syntax cụ thể phụ thuộc DBMS/index. Cursor cần được kiểm tra integrity, tenant scope, sort/filter version và expire policy.

### 15.3. Keyset không tự tạo snapshot

Nếu record bị update/xóa hoặc các record mới xuất hiện giữa hai page, keyset giúp giảm một số trùng/skip do OFFSET nhưng **không tự đảm bảo mọi page là cùng một snapshot**.

Nếu ứng dụng yêu cầu một báo cáo nhất quán tại T0, cần snapshot/read timestamp hoặc cơ chế đóng băng dữ liệu tương ứng với DBMS, có thể với chi phí cao hơn.

### 15.4. Cursor nhiều shard

Một coordinator có thể phải lưu:

- Vị trí ở mỗi shard.
- Sort key cuối toàn cục.
- Query/filter.
- Phiên bản topology.
- Snapshot/consistency context.
- Thông tin shard đã hết dữ liệu.

Không nên tự tạo một cursor chỉ bằng `page=2` rồi kỳ vọng global order bất biến.

---

## 16. COUNT, SUM, AVG, GROUP BY và DISTINCT

Các aggregate phân tán thường có hai pha: **partial aggregation trên shard** và **merge tại coordinator**.

### 16.1. COUNT

Mỗi shard đếm local:

~~~text
A:  120 records
B:   80 records
C:  200 records
~~~

Coordinator cộng:

\[
COUNT_{\text{global}}=120+80+200=400.
\]

Điều này đúng về phép cộng khi các shard biểu diễn tập record không trùng, query filter giống nhau và phạm vi snapshot/thời gian hợp lệ.

Nếu read chạm các shard ở các thời điểm khác nhau trong lúc write liên tục, kết quả có thể không tương ứng với **một snapshot toàn cục**.

### 16.2. SUM

Mỗi shard tính local sum rồi coordinator cộng:

\[
SUM_{\text{global}}=\sum_{i=1}^S SUM_i.
\]

Cần chú ý numeric overflow, precision tiền tệ và biến đổi currency, không chỉ vấn đề shard.

### 16.3. AVG

Không được lấy trung bình đơn giản của các local average nếu các shard có số record khác nhau.

Sai:

\[
AVG\ne\frac{AVG_A+AVG_B}{2}
\]

trong trường hợp số record A/B khác nhau.

Đúng:

\[
AVG_{\text{global}}
=\frac{\sum_i SUM_i}{\sum_i COUNT_i}.
\]

Ví dụ:

~~~text
Shard A: 100 orders, avg=10
Shard B:  10 orders, avg=100
~~~

\[
AVG_{\text{global}}
=\frac{100\cdot10+10\cdot100}{110}
=\frac{2000}{110}
\approx18.18.
\]

Trung bình hai local avg là 55, **sai**.

### 16.4. GROUP BY

Mỗi shard có thể tạo partial states theo nhóm:

~~~text
A: status=PAID -> 150, CANCELLED -> 20
B: status=PAID ->  80, CANCELLED -> 30
~~~

Coordinator hợp nhất theo group key. Với **group cardinality cao**, memory/network có thể lớn vì phải truyền nhiều nhóm chứ không chỉ vài scalar.

### 16.5. DISTINCT

Exact global DISTINCT có thể yêu cầu trao đổi hoặc deduplicate lượng lớn key nếu giá trị lặp giữa các shard.

Một số engine hỗ trợ approximate distinct, ví dụ cấu trúc kiểu HyperLogLog, để giảm memory/network nhưng có **sai số**. Chỉ dùng nếu nghiệp vụ cho phép; số lượng giao dịch, tiền hoặc quota có thể cần tính đúng tuyệt đối.

### 16.6. Pre-aggregation

Với dashboard phổ biến:

~~~text
Doanh thu mỗi ngày theo tenant
~~~

Có thể duy trì aggregate table:

~~~text
(tenantId, day) -> paidOrderCount, revenueVnd
~~~

khi nguồn Order thay đổi. Điều này giảm fan-out của read API, nhưng phải giải quyết cập nhật trễ, retry event, refund, bù trừ, idempotency và freshness SLO.

Không được coi materialized summary là snapshot hoàn hảo chỉ vì lookup một key nhanh.

---

## 17. JOIN và truy vấn quan hệ xuyên shard

NoSQL thường tối ưu theo access pattern và dữ liệu denormalized. Khi có hai collection/table phân mảnh khác nhau:

~~~text
Orders  sharded by tenantId
Users   sharded by userId
~~~

Một query cần ghép Order với User theo customerId có thể yêu cầu:

- Nhiều round trips.
- Coordinator-side join.
- Dịch chuyển dữ liệu giữa shard.
- Query ở hai hệ khác nhau.
- Read model chứa snapshot của thông tin cần hiển thị.

### 17.1. Local join

Nếu những record cần join được **colocate** theo một khóa phù hợp, việc join có thể dễ hơn. Nhưng cơ sở dữ liệu phải thực sự hỗ trợ join/lookup và routing theo điều kiện đó.

Không suy rằng “hai collection cùng tenantId” là đủ để mọi JOIN tự local nếu shard key, chunk placement hoặc execution strategy khác nhau.

### 17.2. Denormalization có chủ đích

Order có thể lưu:

~~~json
{
  "orderId": "order-9001",
  "tenantId": "tenant-7",
  "customerId": "customer-42",
  "customerDisplayNameAtPurchase": "An Nguyễn",
  "totalVnd": 750000
}
~~~

Lưu tên tại thời điểm mua có thể đúng về nghiệp vụ (historical snapshot). Nhưng nếu cần tên mới nhất, phải xác định cập nhật/làm mới field denormalized ra sao.

### 17.3. Multi-shard transactions

Một số NoSQL hỗ trợ transaction xuyên shard trong phạm vi xác định, nhưng thường có chi phí cao hơn single-item operation. Không thể suy từ “query fan-out được” sang “transaction across shards cũng tự động được”.

### 17.4. Khi nào tách OLTP và OLAP?

Nếu query toàn cục, join và aggregate phức tạp liên tục tranh CPU/I/O với đường checkout, có thể cân nhắc:

~~~text
Operational NoSQL (OLTP)
  -> CDC / event pipeline
    -> Analytics warehouse / OLAP / search read model
~~~

Phải chấp nhận/kiểm soát lag và khác biệt consistency giữa nguồn và báo cáo. Đây là đánh đổi kiến trúc, không phải miễn phí.

---

## 18. Consistency của một shard và nhiều shard khác nhau thế nào?

Khi data nằm trên nhiều shard, có ít nhất hai lớp cần phân biệt:

1. **Replica consistency trong một shard/partition.**
2. **Snapshot/transaction consistency giữa nhiều shard/partition.**

### 18.1. Một partition, nhiều replica

Cassandra query một partition tại CL=`LOCAL_QUORUM` có thể cần các replica trong datacenter. Đó là một logical partition query nhưng nhiều replica tham gia.

### 18.2. Nhiều shard, mỗi shard đọc một mốc khác nhau

Giả sử dashboard sum doanh thu:

~~~text
Shard A read at T1
Shard B read at T2
Shard C read at T3
~~~

Trong lúc giao dịch diễn ra, kết quả có thể là hỗn hợp các mốc thời gian nếu không có snapshot toàn cục.

Một global SUM đúng về phép cộng **không tự là một snapshot nhất quán tại cùng một thời điểm**.

### 18.3. Read-your-writes

Nếu người dùng vừa lưu Order ở shard A nhưng màn hình danh sách lấy từ search index hoặc replica trễ, có thể chưa thấy Order.

Targeted routing tới shard A có thể giúp giảm độ phức tạp, nhưng RYW vẫn đòi **read/write consistency policy và đường đọc phù hợp**.

### 18.4. Transaction xuyên shard

Muốn trừ stock ở shard X và tạo Order ở shard Y all-or-nothing, cần một **transaction protocol** bao phủ cả hai hoặc workflow có compensation/reconciliation. Một scatter–gather SELECT không tạo atomic write.

### 18.5. Network partition và partial result

Nếu 1 trong 12 shard không phản hồi:

- Một strong/global query có thể phải fail hoặc timeout.
- Một search UI có thể chấp nhận partial hits nếu sản phẩm/engine cho phép và response ghi rõ.
- Một báo cáo tài chính không nên im lặng bỏ dữ liệu shard lỗi rồi trả tổng như thể đầy đủ.

**Completeness của kết quả là một phần của API contract.**

### 18.6. Durability khác visibility

Một write ở shard A đã được ACK và journal-sync theo policy không có nghĩa một global search index hoặc shard B đã có version tương ứng. Tính bền của nguồn và độ mới của read model là hai câu hỏi riêng.

---

## 19. Failure mode: truy vấn nhiều shard có thêm điểm thất bại

Giả sử request cần 8 shard, nhưng một shard gặp timeout:

~~~text
Shard A: success
Shard B: success
Shard C: success
Shard D: timeout
Shard E: success
Shard F: success
Shard G: success
Shard H: success
~~~

### 19.1. Ba chính sách phổ biến

**All-or-nothing read:** trả lỗi nếu thiếu một shard cần thiết. Phù hợp báo cáo cần đầy đủ, nhưng availability giảm khi một nhánh lỗi.

**Partial read:** trả kết quả những shard đã có, kèm metadata rõ `partial=true` hoặc phần thiếu. Phù hợp một số tìm kiếm hoặc dashboard có chú thích, **không phù hợp mọi nghiệp vụ**.

**Retry/fallback:** retry shard lỗi, chọn replica khác hoặc chờ. Có thể tăng latency và tải nếu làm thiếu kiểm soát.

### 19.2. Một shard chậm kéo dài cả request

Trong fan-out, một shard đang compaction, GC, disk saturation hoặc cold cache có thể gây tail latency cho kết quả toàn cục.

Cần theo dõi latency **theo shard** chứ không chỉ p99 API.

### 19.3. Retry storm

Nếu cả 12 shard đang tải cao và client retry toàn bộ query sau timeout, mỗi lần retry phát thêm 12 nhánh. Một retry storm có thể làm quá tải nặng hơn.

Giải pháp:

- Deadline và retry budget.
- Backoff/jitter.
- Circuit breaker.
- Giới hạn fan-out/concurrency.
- Hủy nhánh khi request client đã timeout nếu engine hỗ trợ.
- Cache/read model cho query phổ biến.
- Không retry thao tác ghi không idempotent một cách mù quáng.

### 19.4. Rebalance và thay đổi placement

Khi shard được di chuyển, routing metadata có thể tạm cũ; router/client phải xử lý redirect/retry theo protocol để không mất/nhân đôi dữ liệu.

Không giữ một bảng ánh xạ `tenantId -> hostname` cứng trong source code nếu DBMS đã quản lý placement động.

### 19.5. Quorum không tự là một shard duy nhất

Khi query target một partition, read consistency có thể yêu cầu quorum replica. Khi query nhiều partition, coordinator có thể phải thực hiện quorum read **ở mỗi partition**, làm tăng số RPC đáng kể.

Không được đồng nhất `fanout=12 logical partitions` với `12 network requests` trong mọi consistency mode.

---

## 20. Hot shard: single-shard query có thể gây nghẽn

Một sai lầm phổ biến là cố gom **mọi dữ liệu một tenant** lên một shard để tăng locality mà bỏ qua tenant rất lớn.

Ví dụ:

~~~text
Tenant A: 100 request/giây
Tenant B: 200 request/giây
Tenant C: 50.000 request/giây
~~~

Nếu toàn bộ tenant C ở một shard, shard đó có thể quá tải dù các shard khác rảnh.

### 20.1. Phân biệt data skew và workload skew

- **Data skew:** một shard chứa nhiều dữ liệu hơn đáng kể.
- **Workload skew:** một shard nhận nhiều request/CPU/I/O hơn.
- **Hot key:** một key hoặc partition được truy cập quá thường xuyên.
- **Hot range:** một khoảng giá trị (ví dụ timestamp mới nhất) tập trung write.
- **Hot query:** một truy vấn fan-out được gọi quá nhiều gây tải trên nhiều shard.

Một hệ có dữ liệu chia đều vẫn có thể bị workload skew.

### 20.2. Chiến lược xử lý

- Chọn shard key phân phối request tốt hơn.
- Dùng time bucket cho dữ liệu lớn theo thời gian.
- Dùng virtual bucket hoặc salt cho tenant cực nóng, với cách query/merge phù hợp.
- Cache các read được phép stale.
- Pre-aggregate/maintain materialized view.
- Rate-limit/fairness cho tenant gây tải.
- Tách workload analytics khỏi transactional path.
- Repartition chỉ sau khi hiểu contract/chi phí migration.

### 20.3. Trade-off locality và phân tán

Nếu tách tenant C thành 16 bucket:

~~~text
(tenant-C, bucket-0)
...
(tenant-C, bucket-15)
~~~

Một write có thể phân phối đều hơn. Nhưng query “mọi Order của tenant C” phải hỏi tối đa 16 bucket logic và merge.

Không có giải pháp miễn phí: **giảm contention thường làm tăng chi phí query theo nhóm**.

### 20.4. Chọn bucket dựa vào nhu cầu

- Nếu query hay xem theo ngày: bucket theo ngày/tháng.
- Nếu hot tenant không giới hạn theo thời gian: hash bucket có thể phù hợp.
- Nếu cần truy vấn theo Order ID: lưu hoặc tính mapping sang bucket.
- Nếu cần toàn tenant aggregate thường xuyên: duy trì summary table.

---

## 21. Bounded fan-out và truy vấn theo giai đoạn

Không phải multi-shard query nào cũng cần gửi đến mọi shard ngay từ đầu.

### 21.1. Query gần nhất trước

Một API lịch sử Order 50 mục:

~~~text
1. Query tháng hiện tại.
2. Nếu đã đủ 50 Order, dừng.
3. Nếu chưa đủ, query tháng trước.
4. Tiếp tục tới giới hạn thời gian do sản phẩm định nghĩa.
~~~

Nếu `createdAt` và partition buckets phản ánh thứ tự thời gian đúng, cách này có thể giảm fan-out đáng kể.

**Điều kiện đúng:** các bucket cũ không thể chứa record mới hơn các bucket mới khi sort theo event date tương ứng. Nếu bucket theo ingestion date nhưng sort theo business event date có backfill, cần kiểm tra; không tự giả định có thể dừng an toàn.

### 21.2. Query một tập tenant rõ ràng

Nếu frontend biết tenant IDs `{7,8,9}`, router có thể target tập shard chứa ba tenant đó thay vì mọi shard.

Khi query là một tập key, nhiều key có thể ánh xạ tới cùng shard: fan-out vật lý có thể nhỏ hơn số key logic.

### 21.3. Budget fan-out

Một API có thể đặt:

~~~text
maxShardsPerInteractiveQuery = 8
maxTimeRangeMonths = 6
maxReturnedRows = 100
deadlineMs = 500
~~~

Các giá trị là **ví dụ thiết kế**, không phải khuyến nghị chung. Nếu client yêu cầu range lớn, API có thể chuyển sang async report thay vì làm tắc đường interactive.

### 21.4. Progressive results

Đối với search có contract cho phép, có thể stream hoặc hiển thị partial results cùng nhãn completeness. Nhưng nếu rank toàn cục chưa được tính xong, không được trình bày partial top-20 như top-20 chính xác.

### 21.5. Fan-out concurrency limit

Nếu một backend đồng thời phát 1000 request x 24 shards, số nhánh có thể thành 24.000. Cần giới hạn concurrency tại API/coordinator, tránh làm sập tất cả shard.

---

## 22. Thiết kế API Java: luôn truyền khóa định tuyến khi có thể

Giả sử API:

~~~http
GET /tenants/{tenantId}/orders?status=PAID&limit=50
~~~

Backend nên lấy `tenantId` từ path đã được xác thực và kiểm tra authorization, rồi thêm nó vào filter DB.

### 22.1. Ví dụ MongoDB Java driver

~~~java
import com.mongodb.client.FindIterable;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

public final class OrderQueries {

    private final MongoCollection<Document> orders;

    public OrderQueries(MongoCollection<Document> orders) {
        this.orders = orders;
    }

    public FindIterable<Document> listPaidOrders(
        String authorizedTenantId,
        int requestedLimit
    ) {
        if (authorizedTenantId == null ||
                authorizedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                "Tenant is required"
            );
        }

        int limit = Math.max(1, Math.min(100, requestedLimit));

        return orders.find(
                Filters.and(
                    Filters.eq("tenantId", authorizedTenantId),
                    Filters.eq("status", "PAID")
                )
            )
            .sort(
                Sorts.orderBy(
                    Sorts.descending("createdAt"),
                    Sorts.descending("_id")
                )
            )
            .limit(limit);
    }
}
~~~

Đây là mã minh họa filter, sort và limit, không phải HTTP handler production. Nếu collection được shard theo `tenantId` như ví dụ MongoDB ở phần 9, điều kiện equality này cho phép router thu hẹp phạm vi.

### 22.2. Không chấp nhận tenantId tùy tiện

Sai:

~~~java
String tenantId = request.queryParam("tenantId");
// Dùng trực tiếp mà không kiểm tra quyền.
~~~

Đúng hơn:

~~~text
authenticate request
authorize access to tenantId
use authorized tenantId as routing/filter key
~~~

**Routing key không thay thế authorization.** Một endpoint có thể rất nhanh nhưng làm lộ dữ liệu tenant khác nếu kiểm soát quyền sai.

### 22.3. Truy vấn thiếu tenantId phải là endpoint riêng

Ví dụ:

~~~http
GET /admin/reports/orders?from=...&to=...
~~~

Không nên dùng cùng handler mặc định cho phép bỏ `tenantId`, vì một lỗi client có thể biến query targeted thành scatter toàn cluster.

API toàn cục có thể cần:

- Quyền admin riêng.
- Time-range bắt buộc.
- Rate limit/concurrency budget.
- Async report cho range lớn.
- Monitoring fan-out và chi phí.
- Dữ liệu từ analytics read model.

### 22.4. Đừng tự đoán placement trong Java

Thay vì hard-code `tenantId % 12` rồi gửi trực tiếp đến hostname, dùng driver/router hỗ trợ topology khi DBMS quản lý sharding. Nếu tổ chức tự sharding ở tầng ứng dụng, phải có metadata service/epoch và giao thức migration, không chỉ phép modulo cố định.

### 22.5. API có thể trả thông tin truy vấn

Trong nội bộ/trace, có thể lưu:

~~~json
{
  "queryClass": "TENANT_ORDER_HISTORY",
  "routingKeyPresent": true,
  "targetedShardCount": 1,
  "resultCount": 50,
  "durationMs": 24
}
~~~

Đây là metadata **minh họa**; số shard thực tế phải lấy từ plan/telemetry, không gán 1 chỉ vì request có tenantId.

---

## 23. Index và shard key giải quyết hai bước khác nhau

### 23.1. Shard key giải quyết “ở đâu?”

Router dùng shard key và metadata để xác định nơi có khả năng chứa record.

### 23.2. Index giải quyết “tìm thế nào trong shard?”

Khi request đến shard, local index hỗ trợ:

- Filter theo status.
- Range theo thời gian.
- Sort theo createdAt.
- Lookup theo orderId.
- Projection/covering query tùy DBMS.

Một index trên `status` không tự giúp router biết shard nào có status đó nếu shard key là `tenantId` và status không quyết định tenant.

### 23.3. Hai câu hỏi của explain

Một query plan nên được đọc theo thứ tự:

1. **Shard targeting:** bao nhiêu shard đã được liên hệ?
2. **Local execution:** mỗi shard dùng index hay scan, đọc bao nhiêu keys/docs, trả bao nhiêu rows?
3. **Merge:** coordinator làm gì?
4. **Latency/cost:** shard chậm nhất, network bytes và memory?
5. **Consistency:** read concern/CL/read path nào?

### 23.4. Secondary index có thể là local hoặc global

Ở các hệ khác nhau:

- Local secondary index có thể giúp filter trong một partition.
- Global secondary index có thể tạo một access path phân phối khác.
- Search index có thể ở engine riêng.
- Materialized view có thể được cập nhật eventual.

**Đừng suy ra “có index thì query sẽ chỉ một shard”**, vì điều đó phụ thuộc index placement và routing semantics của sản phẩm.

---

## 24. Tối ưu truy vấn nhiều shard theo loại workload

### 24.1. Truy vấn interactive

Ưu tiên:

- Filter trên shard/partition key khi có thể.
- Index phù hợp.
- Limit nhỏ và cursor ổn định.
- Bounded time range.
- Timeout rõ ràng.
- Tránh cross-tenant scan không cần thiết.
- Quan sát p99 và số shard được gọi.

### 24.2. Dashboard aggregate

Ưu tiên:

- Daily/hourly summary.
- CDC/outbox để cập nhật read model.
- Chỉ tính lại vùng dữ liệu cần thiết.
- Cache kết quả nếu stale được phép.
- Freshness watermark trong response.
- Đối soát khi event trùng hoặc bỏ sót.

### 24.3. Search toàn hệ

Ưu tiên:

- Engine search phù hợp.
- Tối ưu routing/alias/index.
- Global top-K và sort rõ.
- Giới hạn query phức tạp.
- Dự phòng shard timeout.
- Nêu partial result nếu cho phép.

### 24.4. Báo cáo tài chính/batch

Ưu tiên:

- Snapshot/watermark rõ.
- Idempotent export.
- Dữ liệu đầy đủ, không bỏ shard lỗi.
- OLAP hoặc data warehouse nếu cần join/aggregate lớn.
- Độ chính xác số học và reconciliation.
- Báo cáo thời gian khóa/snapshot khi cung cấp kết quả.

### 24.5. Admin repair/audit

Ưu tiên:

- Partition boundaries đã xác định.
- Quét theo batch có checkpoint.
- Throttle để không ảnh hưởng OLTP.
- Audit số record xử lý.
- Retry/idempotency.
- Không giả định mỗi batch bao phủ toàn bộ dataset.

---

## 25. Migration và đổi shard key

Shard key không phải quyết định dễ thay đổi trong mọi DBMS. Ngay cả khi sản phẩm có hỗ trợ resharding, công việc có thể ảnh hưởng:

- Placement metadata.
- Network và disk I/O.
- Query routing.
- Duplicate read/write trong quá trình chuyển.
- Transaction/consistency behavior.
- Secondary index và CDC.
- Latency của tenant đang nóng.
- Rollback/khôi phục khi migration thất bại.

### 25.1. Khi nào cần reshard?

Dấu hiệu:

- Một shard chiếm phần lớn CPU/I/O.
- Tenant lớn không thể phân phối.
- Query target giảm, fan-out tăng sau thay đổi sản phẩm.
- Mỗi partition quá lớn.
- Cross-shard transactions chiếm tỷ lệ cao.
- Không thể đáp ứng SLO p99 với index hiện tại.

### 25.2. Đo trước khi di chuyển

Trước resharding, thử:

1. Query plan targeted/scatter của các endpoint chính.
2. Top keys và phân phối request.
3. Index selectivity và cache hit rate.
4. Size distribution per shard/partition.
5. Fan-out, p95/p99 và coordinator memory.
6. Tần suất cross-shard transaction.
7. Tính cần thiết của read model mới so với đổi khóa nguồn.

### 25.3. Không khẳng định reshard xong mọi query thành single-shard

Một shard key mới tối ưu tập truy vấn A thường làm tập truy vấn B khó hơn. Cần bảng đánh đổi bằng **access patterns cụ thể**.

---

## 26. Bài toán minh họa: 120 triệu Order trên 12 shard

Giả sử:

~~~text
Total orders: 120.000.000
Shard count: 12
Số Order trung bình nếu phân phối đều: 10.000.000/shard
Global top-K: K=25
~~~

### 26.1. Query theo tenant có shard key phù hợp

~~~text
Targeted shards: 1
Local indexed candidates: 25
Global merge: không cần nhiều luồng
~~~

Đây là ví dụ lý tưởng; tenant hot/size lớn, replica policy và index vẫn ảnh hưởng thực tế.

### 26.2. Query status toàn hệ

~~~text
Targeted shards: 12
Local top-K: tối đa 25/shard
Potential merge candidates: tối đa 12 x 25 = 300
Global result: 25
~~~

Số 300 chỉ là số **ứng viên truyền để merge theo top-K strategy**, không phải số record mà từng shard đã scan/index lookup.

### 26.3. Nếu thêm điều kiện ngày

Giả sử sharding/bucketing theo tháng giúp router chỉ cần 3 trong 12 shard cho một range. Khi đó coordinator có thể giảm fan-out từ 12 xuống 3 nếu planner/placement thực sự hỗ trợ pruning.

Nhưng nếu shard key chỉ là `tenantId` hashed, filter `createdAt` dù có index **không tự giảm số shard** khi query thiếu tenantId.

### 26.4. Nếu mỗi shard chậm 1% thời gian

Giả định độc lập và threshold latency:

\[
P(\text{cả 12 kịp})=0.99^{12}\approx0.886.
\]

Đây là minh họa tail amplification. Thêm replica hoặc tăng concurrency không đảm bảo loại bỏ bottleneck nếu nguyên nhân là shared network/coordinator.

### 26.5. Nếu một shard chứa 50% dữ liệu

Dù 12 shard tồn tại, công việc có thể bị **data skew**:

~~~text
Shard 1: 60 triệu Order
11 shard còn lại: tổng 60 triệu Order
~~~

Một query global có thể bị chi phối bởi shard 1. Thêm parallel fan-out không giải quyết nếu shard chậm nhất vẫn gánh nửa dataset. Cần xem repartition/index/summary.

---

## 27. Lập bảng quyết định từ access pattern

Cho mỗi API, điền:

| API | Routing key có sẵn? | Targeted hay multi-shard? | Index? | Consistency? | Fallback |
|---|---|---|---|---|---|
| `GET /tenants/{id}/orders` | tenantId | Targeted nếu shard key phù hợp | Tenant+time | Theo nguồn | Lỗi/retry |
| `GET /orders/{id}` | orderId, có thể tenantId | Tùy key thiết kế | Order ID lookup | Theo nghiệp vụ | Lookup table |
| `GET /admin/orders?status=PAID` | Không | Multi-shard/read model | Status+time | Freshness policy | Async report |
| `GET /tenants/{id}/monthly-revenue` | tenant+month | Một hoặc vài bucket | Summary PK | Eventual/strong tùy nguồn | Recompute |
| `POST /reservations` | resourceId | Cần điểm authoritative | Conditional update | Mạnh theo invariant | Reject/unknown |
| `GET /search?q=...` | Không rõ | Search fan-out | Search index | Eventual | Partial nếu cho phép |

### 27.1. Câu hỏi bắt buộc

- Nếu chỉ có `orderId` nhưng shard key là `tenantId`, API tìm tenant thế nào?
- Có thể đưa `tenantId` vào path/header sau authorization không?
- Có cần một lookup/index theo orderId?
- Truy vấn report có cần realtime không?
- Query bao nhiêu tháng? Giới hạn fan-out?
- Có hot tenant hoặc hot time bucket không?
- Search index có đáp ứng yêu cầu đọc sau ghi không?
- Nếu một shard lỗi, API được trả kết quả một phần không?

---

## 28. Monitoring và khả năng quan sát

| Chỉ số | Ý nghĩa |
|---|---|
| Shards targeted per query | Fan-out thực tế |
| Single-shard query ratio | Tỷ lệ query có routing hẹp |
| Scatter–gather count/s | Tải toàn cluster |
| Documents/keys examined | Công việc scan/index |
| Returned rows / examined rows | Tính chọn lọc |
| Per-shard p95/p99 | Phát hiện slow/hot shard |
| Coordinator CPU/memory | Chi phí merge |
| Network bytes between shards | Chi phí dữ liệu trao đổi |
| Query timeout by shard count | Tail amplification |
| Partition size distribution | Skew và risk của partition lớn |
| Hot partition/key rate | Workload skew |
| Cross-shard transaction rate | Chi phí coordination |
| Pagination deep-page rate | Query khó tối ưu |
| Search/index lag | Freshness của read model |
| Replica lag, quorum errors | Consistency/availability |
| Rebalance/migration latency | Chi phí thay placement |
| Partial-result responses | Completeness của search/report |
| Query cost by tenant | Fairness và capacity planning |

### 28.1. Log phải đủ ngữ cảnh

Một trace hữu ích:

~~~json
{
  "requestId": "trace-9001",
  "queryClass": "ORDER_HISTORY",
  "tenantScoped": true,
  "routingKeyUsed": true,
  "shardsContacted": 1,
  "rowsReturned": 50,
  "documentsExamined": 62,
  "durationMs": 26,
  "partialResult": false
}
~~~

Đây là JSON minh họa. Trong production, số liệu cần đến từ driver/plan/telemetry đáng tin; không tự ghi `shardsContacted=1` chỉ vì lập trình viên kỳ vọng.

### 28.2. Đặt cảnh báo theo thay đổi hành vi

Một endpoint trước đây target 1 shard nhưng sau release tăng lên 12 shards có thể gây tăng latency/cost đột ngột.

Các thay đổi dễ làm mất routing:

- Bỏ điều kiện tenantId trong một refactor.
- Thay schema query sang OR không còn ràng buộc shard key.
- Đọc qua read model/index khác.
- Thay shard key mà không cập nhật API.
- Quên truyền bucket/month.
- Bỏ index giúp local sort.
- Tăng khoảng thời gian tìm kiếm không giới hạn.

Monitoring nên cảnh báo **routing regression** chứ không chỉ CPU khi cluster đã quá tải.

---

## 29. Kiểm thử query routing trong môi trường được phép

**Chỉ chạy load test có kiểm soát trên môi trường được cho phép; không phát truy vấn scan toàn cluster hoặc fault injection vào production nếu chưa được duyệt.**

### 29.1. Chuẩn bị dataset

Ví dụ:

~~~text
12 shards
100 tenants
Tenant bình thường: 100.000 orders
Tenant hot: 5.000.000 orders
Order có status, createdAt, orderId
Index phục vụ query theo tenant/time
~~~

Đây là cấu hình giả định; chọn cỡ dữ liệu phù hợp test environment.

### 29.2. Test A — targeted equality

~~~text
Filter: tenantId = tenant-7
Sort: createdAt DESC, orderId DESC
Limit: 50
~~~

Ghi actual shards contacted, scanned/index keys, p99, memory, network bytes.

### 29.3. Test B — thiếu routing key

~~~text
Filter: status = PAID
Sort: createdAt DESC
Limit: 50
~~~

So sánh số shard, local index usage, merge và chi phí.

### 29.4. Test C — range pruning

~~~text
Filter: tenant-7 và tháng 2026-09..2026-11
~~~

Đo những tháng/partitions nào thực sự cần. Đừng tự giả định 3 logical buckets nghĩa đúng 3 physical shards trong mọi DBMS.

### 29.5. Test D — skew

Cho một tenant nhận 60% traffic, xem:

- Shard nào tăng CPU/IOPS?
- Query p99 có tệ hơn?
- Có queue/throttling?
- Có cần bucket/shard key khác không?

### 29.6. Test E — một shard chậm

Trong staging, mô phỏng latency ở một shard theo công cụ được cấp phép, rồi đo:

- Global query p99.
- Partial-result policy.
- Timeout/retry fan-out.
- Tải coordinator.
- Khả năng hủy request/nhánh.

### 29.7. Test F — pagination và aggregate

- Query top 50, page 2, page 3 khi data đang được ghi.
- Kiểm tra duplicate/skip theo contract.
- Tính COUNT/SUM/AVG từ các partition và so kết quả nguồn đối soát.
- Kiểm tra kết quả khi một shard timeout.
- Nếu cần snapshot, thử API đọc snapshot của engine.

Kết quả của test phải nói rõ **scope và failure model**. Một test nhanh không chứng minh mọi query tương lai đều nhanh.

---

## 30. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Cách hiểu đúng |
|---|---|---|
| “Có shard key trong document là mọi query được target.” | Query thiếu điều kiện key vẫn fan-out | Filter phải giúp router suy ra placement |
| “Một partition luôn là một máy.” | Sai khi có replica/physical split | Phân biệt logical và physical |
| “Một shard query luôn nhanh.” | Hot shard hoặc thiếu index | Đo local execution cost |
| “Multi-shard query luôn full scan.” | Bỏ qua local index và pruning | Fan-out khác số document đọc |
| “Index trên status làm query status một shard.” | Index local không tự thay shard key | Xem index placement/routing |
| “LIMIT 20 nghĩa mỗi shard đọc 20 row.” | Sort/filter có thể cần đọc nhiều hơn | Phân biệt candidates với examined |
| “ORDER BY ở mỗi shard là global ORDER BY.” | Kết quả thiếu merge | Cần global merge theo total order |
| “AVG global = avg các AVG cục bộ.” | Sai khi shard count khác nhau | Tổng SUM chia tổng COUNT |
| “Một page Query trả hết dữ liệu.” | Bỏ qua continuation token | Theo dõi cursor/LastEvaluatedKey |
| “Scan với FilterExpression rẻ như Query.” | Scan đọc nhiều trước khi lọc | Dùng key/index đúng access pattern |
| “CQL ALLOW FILTERING sửa được mọi schema.” | Scan lớn và unpredictable | Thiết kế query-driven table |
| “MongoDB filter theo status tự target.” | Không nếu shard key là tenant | Kiểm tra explain |
| “DynamoDB một PK luôn một physical partition.” | Dịch vụ có quản lý partition nội bộ | Hiểu logical PK vs physical storage |
| “Redis Cluster tự scatter MGET cross-slot.” | Có thể CROSSSLOT | Thiết kế slot/client fan-out |
| “ES routing có thể khác routing lúc index.” | Mất kết quả | Routing phải nhất quán |
| “Routing key đồng nghĩa quyền truy cập.” | Lộ dữ liệu đa tenant | Authorization độc lập |
| “Keyset pagination là snapshot.” | Record thay đổi vẫn ảnh hưởng | Snapshot/watermark khi cần |
| “Targeted read luôn RYW.” | Replica/cache có thể stale | Read consistency riêng |
| “Fan-out 12 shard chỉ là 12 RPC.” | Quorum/retry/merge có thể tăng | Đo actual network calls |
| “Trả 7/8 shard vẫn là báo cáo đầy đủ.” | Sai số liệu | Có policy completeness |
| “Tăng shard count luôn nhanh hơn.” | Merge overhead tăng | Benchmark p99 và cost |
| “Hash key tự loại hot tenant.” | Một key cực nóng vẫn tập trung | Bucket/escrow/read model |
| “Đổi shard key không ảnh hưởng ứng dụng.” | Routing và query plan đổi | Đánh giá mọi access pattern |
| “Quorum đồng nghĩa snapshot toàn shard.” | Consistency scope khác | Xét per-partition vs cross-partition |
| “Cache sau write chắc chắn cập nhật.” | Read model lag | Watermark/fallback/invalidation |

---

## 31. Bài tập 1: phân loại đường định tuyến

Một collection được phân mảnh theo **hashed key `tenantId`**, có 8 shard.

Với từng query, phân loại **có thể targeted** hay **có thể scatter**, và giải thích:

~~~javascript
// A
db.orders.find({ tenantId: "tenant-7" });

// B
db.orders.find({ status: "PAID" });

// C
db.orders.find({
  tenantId: "tenant-7",
  createdAt: { $gte: ISODate("2026-11-01") }
});

// D
db.orders.find({
  tenantId: { $gte: "tenant-1", $lt: "tenant-9" }
});

// E
db.orders.find({ _id: "order-9001" });
~~~

Câu hỏi thêm:

1. Vì sao có index trên `_id` không nhất thiết giúp router target shard nếu `_id` không thuộc shard key?
2. Nếu tenant-7 có 50 triệu order, query A có chắc nhanh không?
3. Compound index nào phù hợp với C khi cần sort `createdAt DESC`?
4. Cần dùng công cụ nào để thấy actual shard targeting?
5. Nếu thay shard key thành orderId hashed, query nào hưởng lợi và query nào xấu đi?

**Gợi ý:** equality trên hashed tenant key có thể target; filter không chứa key thường scatter; range trên giá trị trước hash không giữ locality.

## 32. Bài tập 2: Cassandra partition key

Schema:

~~~sql
CREATE TABLE orders_by_tenant_month (
  tenant_id text,
  month text,
  created_at timestamp,
  order_id text,
  amount bigint,
  PRIMARY KEY (
    (tenant_id, month),
    created_at,
    order_id
  )
);
~~~

Hãy trả lời:

1. Query chỉ có `tenant_id` đã xác định **một partition** chưa?
2. Query có đủ `tenant_id` và `month` thì sao?
3. Range trên `created_at` khi đã có partition key khác gì range trên `month` thiếu `tenant_id`?
4. Muốn xem 12 tháng gần nhất phải xử lý thế nào?
5. Vì sao không dùng `ALLOW FILTERING` làm mặc định?
6. Một partition read với `LOCAL_QUORUM` có thể liên hệ bao nhiêu replica?
7. Khi một tenant có 20 triệu Order/tháng, cần thay đổi schema/bucketing gì?

## 33. Bài tập 3: tính latency và số ứng viên

Một global query:

~~~text
S = 12 shards
K = 25 records
Mỗi shard trả top K theo cùng total order.
Các shard được chạy song song.
~~~

Trả lời:

1. Số candidate tối đa coordinator có thể nhận để merge top K là bao nhiêu?
2. Có thể kết luận mỗi shard chỉ đọc K record không?
3. Nếu một shard mất 200 ms, còn 11 shard mất 15 ms, global query cần tất cả 12 shard thì tail latency ảnh hưởng thế nào?
4. Nếu thiếu một shard, có thể trả chính xác top 25 toàn cục không?
5. Tính \(0.99^{12}\) và giải thích ý nghĩa trong mô hình độc lập.
6. Nếu mỗi shard có index theo sort key, điều gì cải thiện?

**Đáp án gợi ý:** tối đa \(12\times25=300\) ứng viên; tổng chi phí local execution có thể lớn hơn rất nhiều; kết quả thiếu shard không được gọi là global top 25 chính xác nếu shard thiếu có thể chứa record đứng đầu.

## 34. Bài tập 4: global average

Ba shard lưu doanh số theo đơn:

~~~text
Shard A: 100 order, tổng 10.000.000 VND
Shard B:  20 order, tổng  6.000.000 VND
Shard C:   5 order, tổng  2.000.000 VND
~~~

Hãy tính:

1. AVG của từng shard.
2. AVG toàn cục đúng.
3. Trung bình của ba local AVG có bằng AVG global không?
4. Nếu shard C timeout, báo cáo có thể gọi số còn lại là average toàn hệ không?
5. Nếu các shard đọc tại những thời điểm khác nhau khi có Order mới, cần làm gì để bảo đảm một báo cáo snapshot nhất quán?

**Gợi ý:**

\[
AVG_{\text{global}}
=\frac{10\,000\,000+6\,000\,000+2\,000\,000}{100+20+5}
=\frac{18\,000\,000}{125}
=144\,000\ \text{VND/order}.
\]

## 35. Bài tập 5: thiết kế Order API đa tenant

Bối cảnh:

~~~text
100.000 tenants
120 triệu Orders
20% traffic đến từ 10 tenants rất lớn
90% user queries hỏi đơn của một tenant
5% query tìm theo orderId
5% query là admin report toàn hệ
SLO p99 trang Orders: 200 ms
~~~

Yêu cầu:

1. Đề xuất shard/partition key và giải thích.
2. Xử lý hot tenant như thế nào?
3. Khi chỉ biết `orderId` làm sao xác định tenant/bucket?
4. Thêm index/read model nào cho các query quan trọng?
5. Report toàn hệ nên chạy trên OLTP hay analytics store?
6. Khi đổi shard key, SLO p99 nào có nguy cơ thay đổi?
7. Có nên cho `tenantId` thiếu ở endpoint `/tenants/{id}/orders` không?
8. Cần metric nào đo fan-out regression?

Không có một đáp án duy nhất. Hãy ghi **đánh đổi giữa locality, phân tải, read consistency, write throughput và complexity**.

## 36. Bài tập 6: hoàn thiện Java Query Service

Đề bài: xây API:

~~~text
listOrders(tenantId, status, limit)
listOrdersAcrossTenants(adminQuery, limit)
~~~

Yêu cầu:

- `tenantId` đã được authorization trước khi query.
- `listOrders` luôn có điều kiện routing key.
- Limit bị chặn tối đa 100.
- Sort có tie-breaker duy nhất.
- Không dùng deep offset pagination mặc định.
- `listOrdersAcrossTenants` chỉ dành cho admin.
- Admin query bắt buộc time range, có async mode khi rộng.
- Log actual shards contacted và local scanned records.
- Có deadline/retry budget.
- Kết quả partial phải được đánh dấu nếu contract cho phép.
- Không trả kết quả thiếu shard như báo cáo đầy đủ.

Thảo luận: tại sao việc tách hai method/API có thể ngăn một refactor làm mất shard key và gây scatter toàn cluster?

## 37. Bài tập 7: phân mảnh theo thời gian

Một hệ telemetry nhận 500.000 sự kiện/phút, lưu theo device và ngày:

~~~text
Partition key = (deviceId, UTC_DAY)
Clustering = eventTime
~~~

Các truy vấn:

1. 100 sự kiện mới nhất trong ngày của một thiết bị.
2. 100 sự kiện gần nhất trong 30 ngày.
3. Tổng sự kiện toàn fleet trong 24 giờ.
4. Tìm sự kiện có errorCode=E42 ở mọi thiết bị.
5. Truy vấn một device không biết timezone/ngày.

Hãy phân tích:

- Truy vấn nào target một partition?
- Truy vấn nào fan-out theo ngày hoặc device?
- Partition quá lớn có thể xảy ra với device cực nóng không?
- Có cần time bucket nhỏ hơn ngày?
- Cần index/read model/analytics riêng cho câu 3 và 4?
- Sự khác nhau giữa **thời gian sự kiện** và **thời gian ghi nhận** ảnh hưởng chiến lược query gần nhất thế nào?

---

## 38. Checklist áp dụng trên hệ thống thật

Trước khi chấp nhận một thiết kế query NoSQL, hãy xác nhận:

1. **Access patterns:** người dùng thường truy vấn theo trường nào?
2. **Shard/partition key:** có xuất hiện dưới dạng filter có thể route được không?
3. **Actual targeting:** query plan liên hệ bao nhiêu logical shards?
4. **Index:** local filter, sort và projection có index phù hợp không?
5. **Data distribution:** kích thước các shard/partition có lệch không?
6. **Workload distribution:** có hot tenant, hot key hoặc hot range không?
7. **Concurrency:** bao nhiêu fan-out queries có thể chạy đồng thời?
8. **Top-K:** merge có total ordering và tie-breaker đúng không?
9. **Pagination:** cursor có ổn định và có snapshot nếu nghiệp vụ yêu cầu không?
10. **Aggregate:** partial state có được hợp nhất bằng công thức đúng không?
11. **Completeness:** khi một shard timeout, API trả lỗi hay partial có nhãn?
12. **Consistency:** per-shard read policy có đáp ứng read-your-writes hay snapshot toàn cục không?
13. **Durability:** write được xác nhận theo policy nào, failover ảnh hưởng ra sao?
14. **Rebalance:** routing metadata và client xử lý chuyển shard thế nào?
15. **Authorization:** tenant/routing key có được xác thực không?
16. **Cost:** tổng I/O, network bytes, coordinator CPU/memory, p99 và read units?
17. **Observability:** actual shard count có nằm trong trace/metrics không?
18. **Tối ưu kiến trúc:** cần index mới, materialized view hay OLAP thay vì sharding lại?
19. **Error budget:** deadline, retry, throttling và async mode cho query rộng?
20. **Validation:** đã đo với workload và dữ liệu lệch thực tế trong môi trường phù hợp chưa?

## 39. Tổng kết

**Truy vấn một phân mảnh** và **truy vấn nhiều phân mảnh** khác nhau chủ yếu ở khả năng **định tuyến** và chi phí **phối hợp kết quả**.

Những nguyên tắc cốt lõi:

1. **Targeted query** sử dụng shard/partition key hoặc metadata giúp router chỉ hỏi shard có khả năng chứa dữ liệu.
2. **Scatter–gather** hỏi nhiều shard, thực hiện local filter/aggregation/sort rồi merge kết quả.
3. **Shard key và index có vai trò khác nhau:** key giúp biết *ở đâu*, index giúp biết *tìm như thế nào*.
4. **Một shard không tự nhanh**, vì hot key, partition quá lớn hoặc thiếu index vẫn có thể gây chậm.
5. **Multi-shard không tự là full scan**, vì local index, partition pruning và top-K có thể giảm chi phí.
6. **Global ORDER BY, LIMIT, AVG, DISTINCT và pagination phải có logic merge đúng**, không được lấy kết quả từng shard rồi ghép tùy tiện.
7. **Tail latency và availability** phụ thuộc số nhánh cần chờ; một shard lỗi có thể làm query toàn cục thiếu dữ liệu.
8. **Consistency của replica và snapshot xuyên shard là hai câu hỏi riêng**, cũng như source DB và search/cache có freshness riêng.
9. **Shard key là đánh đổi giữa locality và phân tải:** tối ưu truy vấn một tenant có thể tạo hot tenant, còn tách bucket làm truy vấn tenant cần fan-out.
10. **Đo actual routing từ query plan và telemetry**, không suy luận hiệu năng chỉ từ số shard của cluster hoặc tên database.

**Câu cần nhớ: “Muốn truy vấn NoSQL nhanh và đúng, hãy thiết kế để hệ biết dữ liệu ở đâu; khi phải hỏi nhiều phân mảnh, hãy chủ động kiểm soát lượng fan-out, cách merge, tính đầy đủ và mức nhất quán của kết quả.”**
