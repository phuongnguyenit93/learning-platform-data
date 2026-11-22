# Nhận diện phân mảnh chịu tải tập trung (hot shard) và kiểm chứng bằng số đo

## 1. Bối cảnh và mục tiêu

Trong hệ thống dùng **Spring Data MongoDB**, ứng dụng thường truy cập MongoDB qua `MongoTemplate` hoặc repository. Khi dữ liệu tăng, một collection có thể được **shard** để phân bố dữ liệu và xử lý yêu cầu trên nhiều shard. Tuy vậy, số lượng shard lớn hơn không bảo đảm tải được chia đều.

Một **hot shard** là shard đang nhận hoặc xử lý lượng công việc lớn bất thường so với các shard khác trong cùng một khoảng đo, gây tắc nghẽn tài nguyên hoặc tăng độ trễ. **Hot chunk/range** là vùng khóa shard đang tập trung truy cập; nó có thể là nguyên nhân khiến shard chứa vùng đó bị nóng. Hiện tượng này có thể xảy ra dù dung lượng và số document được phân phối khá đều.

Bài học tập trung vào bốn năng lực:

1. Phân biệt mất cân bằng **dữ liệu** với mất cân bằng **lưu lượng và chi phí xử lý**.
2. Thu thập số đo đủ tin cậy để xác nhận shard nào bị nóng, trong thời điểm nào, do thao tác nào.
3. Dùng định tuyến truy vấn, phân tích shard key và chỉ số ứng dụng Spring Data MongoDB để lần ra nguyên nhân.
4. Kiểm chứng biện pháp cải thiện bằng phép đo trước/sau trên workload tương đương.

> Phạm vi: ví dụ dùng cluster sharded gồm ba shard, mỗi shard là một replica set, ứng dụng Java/Spring Data MongoDB kết nối qua `mongos`. Tên shard, database và các số liệu bên dưới chỉ dùng để minh họa.

## 2. Hot shard trông như thế nào?

Xét collection `shop.orders` nhận nhiều đơn hàng mới. Nếu dùng shard key dạng range `{ createdAt: 1 }`, các đơn hàng có thời điểm tăng liên tục thường được ghi vào vùng khóa ở đầu cuối dải giá trị. Một chunk có thể nhận phần lớn ghi mới tại từng thời điểm; shard đang giữ chunk đó dễ trở thành hot shard. Nếu các màn hình cũng chủ yếu đọc đơn hàng gần đây, tải đọc có thể dồn vào cùng shard.

Các loại mất cân bằng cần phân biệt:

| Hiện tượng | Dấu hiệu | Ý nghĩa |
|---|---|---|
| **Data skew** | Một shard giữ nhiều document/dung lượng hơn hẳn | Phân bố lưu trữ không đều; chưa đủ chứng minh tải cao |
| **Workload skew / hot shard** | Một shard có ops/s, CPU, I/O, hàng đợi hoặc độ trễ cao hơn phần còn lại | Tải thực thi tập trung; cần tìm query shape và khóa shard gây ra |
| **Hot chunk / hot range** | Một vùng shard key nhận phần lớn yêu cầu trong mẫu thời gian | Nguyên nhân tiềm năng của hot shard; chuyển chunk chỉ có thể chuyển điểm nóng |
| **Scatter-gather** | Một truy vấn được gửi tới nhiều hoặc tất cả shard | Có thể làm cả cluster tốn tài nguyên; không đồng nghĩa chỉ một shard nóng |
| **Nghẽn phần cứng hoặc sự cố riêng shard** | Một shard chậm dù lượng yêu cầu gần tương đương | Có thể do ổ đĩa, bộ nhớ, cache, replica set, index hoặc tác vụ nền |

Một shard có 40% dữ liệu trên cluster ba shard chưa chắc là hot shard. Ngược lại, shard có 33% dữ liệu nhưng xử lý 80% yêu cầu ghi và CPU luôn trên 90% có bằng chứng mạnh hơn về tải tập trung. Kết luận cuối cùng cần xem **đồng thời** cường độ truy cập, sử dụng tài nguyên và ảnh hưởng đến độ trễ.

### Những nguyên nhân thường gặp

- **Shard key tăng đơn điệu** (timestamp, sequence, ID tăng dần) với range sharding, tạo vùng ghi mới tập trung.
- **Khóa có ít giá trị hoặc phân bố lệch**, ví dụ trạng thái đơn hàng hoặc một tenant quá lớn; nhiều thao tác cùng nhắm tới một miền khóa.
- **Truy cập thiên về dữ liệu mới**: dữ liệu lịch sử phân đều nhưng phần lớn request chỉ xem một khoảng thời gian ngắn.
- **Truy vấn hay cập nhật có dạng giống nhau** (query shape) dồn vào một shard, dù toàn bộ workload khác phân đều.
- **Chunk lớn/khó chia, di chuyển dữ liệu, balancer hoặc tác vụ nền** làm kết quả quan sát bị lệch tạm thời.
- **Khác biệt về năng lực shard** (CPU, đĩa, tài nguyên replica set, index, cache) khiến cùng số ops/s cho độ trễ khác nhau.

Lưu ý: shard key có dạng hash không tự động giải quyết mọi hot shard. Nếu phần lớn lưu lượng thuộc **một tenant** và hash toàn bộ theo tenantId, các thao tác của tenant đó vẫn có thể tập trung vào một dải khóa.

## 3. Thiết kế phép đo: nhìn đúng phạm vi, đúng thời gian

Bắt đầu với một khung quan sát cố định, chẳng hạn **15 phút**, lấy mẫu mỗi 30–60 giây và so sánh với cùng giờ của ngày bình thường. Nên có cả giai đoạn cao điểm và giai đoạn ít tải. Ghi rõ số shard, cấu hình phần cứng, topology, phiên bản MongoDB, read preference, phạm vi collection và khoảng thời gian.

| Lớp quan sát | Số đo / dấu hiệu | Nguồn thường dùng | Cần tránh hiểu nhầm |
|---|---|---|---|
| Phân bố lưu trữ | Docs, bytes, chunk/range trên mỗi shard | `getShardDistribution()`, `sh.getShardedDataDistribution()` | Phản ánh lưu trữ, **không** trực tiếp phản ánh QPS |
| Tốc độ thao tác | Reads/s, writes/s, insert/update/delete, command, getMore | Giám sát shard, `serverStatus`, logs/profiler | Counter của `mongod` tính theo **instance**, không mặc nhiên riêng collection |
| Mức sử dụng tài nguyên | CPU, disk IOPS/latency, network, WiredTiger cache, connection pressure | Atlas/Prometheus/host metrics | CPU cao vì migration hoặc index build cũng có thể xảy ra |
| Độ trễ | p50/p95/p99 theo query shape, số lỗi/timeout, `docsExamined` | Tracing/Micrometer, slow query logs, profiler, `explain` | p95 toàn hệ thống không xác định shard gây chậm |
| Định tuyến | Số shard được nhắm tới, scatter-gather, phân bố theo shard-key range | `explain("executionStats")`, `analyzeShardKey`, `mongos` metrics | “Target một shard” là đặc tính tốt, nhưng **cùng một shard** nhận gần hết traffic vẫn có thể nóng |
| Tác vụ nền | Migration, election, balancer, compaction, backup, index build | Telemetry và log vận hành | Nên đánh dấu thời điểm xảy ra để không quy sai nguyên nhân |

Để so sánh công bằng:

- Đo cùng khoảng thời gian trên các **primary** khi so tải ghi. Nếu đọc từ secondary, đo đúng secondary phục vụ đọc và tách riêng read/write.
- Chuẩn hóa số liệu theo **ops/giây** từ chênh lệch counter; kiểm tra counter có reset sau restart hoặc failover hay không.
- Nếu shard có cấu hình khác nhau, so cả tải thực tế **và** tỷ lệ dùng công suất; raw QPS cao không mặc nhiên là quá tải.
- Đo theo **collection và query shape** khi có thể. Chỉ số host toàn shard dùng để sàng lọc; profiler/tracing/mẫu truy vấn giúp quy trách nhiệm cho `orders`.
- Phân tích độ trễ theo cùng endpoint/query shape và cùng kích thước kết quả; không lấy trung bình các giá trị p95 của các shard để tạo p95 toàn cluster.

## 4. Đọc số liệu mẫu và tính độ lệch

Giả sử các số sau đã được tổng hợp cho **chính collection `shop.orders`** trong giờ cao điểm. Tốc độ thao tác xuất phát từ mẫu logs/profiler và phép đếm theo thời gian; CPU được lấy từ primary tương ứng.

| Chỉ số | shard-a | shard-b | shard-c |
|---|---:|---:|---:|
| Số document (triệu) | 3,4 | 3,2 | 3,3 |
| Ghi/giây | **950** | 120 | 130 |
| Đọc/giây | **730** | 180 | 190 |
| CPU primary trung bình | **91%** | 32% | 36% |
| p95 truy vấn được định tuyến tới shard (ms) | **240** | 29 | 35 |

Tổng ghi là `950 + 120 + 130 = 1.200` thao tác/giây. Với `N = 3` shard, nếu tải phân bố đều thì mỗi shard sẽ nhận khoảng `1/3 = 33,3%` tổng ghi. Trong ví dụ:

```text
writeShare(shard-a) = 950 / 1200 × 100% = 79,2%
hotFactor          = 79,2% / 33,3% ≈ 2,38 lần mức phân bố đều
max/min write rate = 950 / 120 ≈ 7,92
```

Có thể áp dụng công thức chung:

\[
\operatorname{share}_i=\frac{\operatorname{ops}_i}{\sum_{j=1}^{N}\operatorname{ops}_j},\qquad
\operatorname{hotFactor}=N\cdot\max_i(\operatorname{share}_i)
\]

**Nhận định:** tài liệu lưu trữ gần đều (khoảng 32–34% mỗi shard) nhưng shard-a xử lý gần 80% lượng ghi và có CPU, p95 tăng mạnh. Đây là **bằng chứng hợp lý để điều tra hot shard**, nhất là nếu kéo dài qua nhiều cửa sổ đo và tăng đồng thời với traffic mới. Vẫn phải chứng minh thao tác nào gây ra tải và loại trừ sự cố tài nguyên riêng shard.

Không có ngưỡng phổ quát như “trên 60% là lỗi”. Ngưỡng cảnh báo phải dựa trên baseline, độ lệch mong đợi, SLO độ trễ và năng lực từng shard. Ví dụ đặt cảnh báo điều tra khi một shard có **tỷ lệ ghi lớn hơn 2 lần mức chia đều trong ba cửa sổ liên tiếp**, đồng thời CPU hoặc p95 vượt ngưỡng nội bộ. Đây là ví dụ vận hành, không phải quy tắc MongoDB.

## 5. Quy trình điều tra trên cluster thật

### Bước 1 — Xác nhận topology và phân bố dữ liệu

Dùng `mongosh` kết nối tới **`mongos`**, chọn database/collection đúng và chạy:

```javascript
// Chạy trên mongos của sharded cluster.
sh.status();

const orders = db.getSiblingDB("shop").orders;
orders.getShardDistribution();

// MongoDB >= 6.0.3, chạy từ mongos để xem toàn bộ phân bố.
// Tùy quyền và phiên bản triển khai:
sh.getShardedDataDistribution();
```

Quan sát shard key hiện tại, các shard tham gia, lượng docs/bytes/chunk và chênh lệch dung lượng. `getShardDistribution()` là helper trong `mongosh`, **không** phải API của Spring Data. Một số dịch vụ/cluster nhỏ có giới hạn với các lệnh này.

Dữ liệu phân bố đều nhưng hiệu năng mất cân bằng là tín hiệu cần chuyển từ kiểm tra phân bố **storage** sang kiểm tra phân bố **workload**. Nếu dữ liệu lệch nhiều, ghi nhận nhưng chưa kết luận nguyên nhân chỉ từ bảng dung lượng.

### Bước 2 — So sánh thao tác trên từng shard

Truy cập **primary của từng shard** (thay vì chỉ kết nối `mongos`) để đọc `serverStatus`. Ví dụ mẫu nhanh trên **một primary**, sau đó lặp lại trên các primary còn lại trong cùng cửa sổ đo:

```javascript
// Trong mongosh nối tới primary của một shard.
// Dùng cho quan sát ngắn; không áp dụng lên tất cả collection.
const t0 = Date.now();
const before = db.getSiblingDB("admin").serverStatus().opcounters;

sleep(60_000);

const t1 = Date.now();
const after = db.getSiblingDB("admin").serverStatus().opcounters;
const seconds = (t1 - t0) / 1000;

function perSecond(name) {
  return (Number(after[name]) - Number(before[name])) / seconds;
}

printjson({
  insertPerSecond: perSecond("insert"),
  updatePerSecond: perSecond("update"),
  deletePerSecond: perSecond("delete"),
  queryPerSecond: perSecond("query")
});
```

Các counter `opcounters` tích lũy từ lúc `mongod` khởi động; khác phiên bản có thể có trường khác. Nếu có số âm, failover/restart hay khoảng thời gian sai thì **bỏ mẫu**. Counter `query` không đại diện cho toàn bộ lưu lượng đọc; `getMore` và aggregate cũng cần xem theo phiên bản và tình huống. Đây là phép **sàng lọc tải instance**: không được ghi kết luận “`orders` nhận X writes/s” chỉ từ `opcounters` nếu shard còn phục vụ các collection khác.

Trong vận hành thực, ưu tiên biểu đồ giám sát từng shard theo thời gian, đối chiếu slow query logs/profiler, tracing hoặc mẫu truy vấn cho `shop.orders`. Kiểm tra network, disk IOPS/latency, CPU, cache, replication lag và các sự kiện migration/election trong cùng giai đoạn.

### Bước 3 — Xem truy vấn thực tế được route ra sao

Trên `mongos`, phân tích **đúng query shape** mà ứng dụng gửi đi:

```javascript
use shop

db.orders.find({
  tenantId: "tenant-A",
  createdAt: {
    $gte: ISODate("2026-11-20T00:00:00Z"),
    $lt: ISODate("2026-11-21T00:00:00Z")
  }
}).explain("executionStats");
```

Tìm thông tin về shard được nhắm tới và các thống kê như `totalKeysExamined`, `totalDocsExamined`, `nReturned`, thời gian thực thi và plan theo từng shard (cấu trúc `explain` thay đổi giữa phiên bản và loại query). Hãy trả lời:

1. Query chỉ chạy trên một shard hay phải gửi tới nhiều shard?
2. Các query nóng liên tục tìm đến **cùng shard** hay thay đổi theo giá trị shard key?
3. Query có sử dụng index phù hợp và tỷ lệ `docsExamined / nReturned` có hợp lý không?
4. Có query dạng `sort`, `aggregate`, `getMore` hoặc update nhiều document làm một shard phải xử lý nhiều công hơn không?

`explain("executionStats")` có thể thực thi truy vấn để lấy số liệu; dùng bộ lọc có giới hạn và đo ở môi trường phù hợp, tránh chạy tùy tiện truy vấn nặng trên production.

### Bước 4 — Phân tích shard key bằng mẫu truy vấn (MongoDB 7.0+)

MongoDB 7.0 trở lên hỗ trợ query sampling và `analyzeShardKey`. Trên môi trường thử nghiệm được cấp quyền, có thể bật sampling tốc độ nhỏ trong thời gian đủ đại diện:

```javascript
// Chạy trên mongos; thay namespace và sample rate cho workload thực.
db.adminCommand({
  configureQueryAnalyzer: "shop.orders",
  mode: "full",
  samplesPerSecond: 5
});

// Sau khi hệ thống đã thu thập đủ một khoảng mẫu đại diện:
db.getSiblingDB("shop").orders.analyzeShardKey(
  { createdAt: 1 },
  {
    keyCharacteristics: true,
    readWriteDistribution: true
  }
);

// Kết thúc phiên đo ở môi trường lab:
db.adminCommand({
  configureQueryAnalyzer: "shop.orders",
  mode: "off"
});
```

Trong production, trước khi thay cấu hình, phải xem `oldConfiguration` và **khôi phục chế độ sampling đã có**; không tắt một cấu hình mà đội vận hành đang dùng. Sampling tạo dữ liệu bổ sung và cần quyền phù hợp. Để phân tích đặc trưng shard key phải có supporting index; kết quả phân bố đọc/ghi chỉ có ý nghĩa khi lượng sampled queries đủ lớn và phản ánh giờ cao điểm.

Chú ý các trường `readDistribution`, `writeDistribution`, `percentageOfSingleShardReads/Writes`, `percentageOfScatterGatherReads/Writes` và `numReadsByRange` / `numWritesByRange`. Những mảng `...ByRange` phản ánh **mức độ nóng của các khoảng shard key trong phân tích**, không phải là bảng ops/s trực tiếp của từng shard đang chạy. Kết hợp chúng với topology và telemetry theo shard mới đủ kết luận.

Nếu 95% thao tác **mỗi thao tác** chỉ cần target một shard (các thao tác có thể target các shard khác nhau), đây là đặc tính định tuyến hiệu quả; nhưng nếu hầu hết thao tác trong mẫu đều nhắm **cùng một khoảng khóa** và primary chứa khoảng đó bị quá tải, đó mới là bằng chứng về điểm nóng.

### Bước 5 — Liên hệ tới thao tác Spring Data MongoDB

Ứng dụng có thể gửi query qua `MongoTemplate`:

```java
// Các biến mongoTemplate, from và to đã được tạo trong service.
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-A")
        .and("createdAt").gte(from).lt(to)
);

List<Order> orders = mongoTemplate.find(query, Order.class);
```

Trong ví dụ này, `Order` là entity `@Document(collection = "orders")`. Spring Data MongoDB xây dựng truy vấn qua Java driver; **shard được chọn bởi MongoDB dựa trên shard key, bộ lọc và routing metadata**, chứ `MongoTemplate` không tự cân bằng truy vấn giữa các shard.

Khi cần xem execution plan của thao tác tương đương, có thể dùng Java driver thông qua `MongoTemplate.execute`:

```java
Document filter = new Document("tenantId", "tenant-A")
    .append("createdAt",
        new Document("$gte", Date.from(from))
            .append("$lt", Date.from(to)));

Document plan = mongoTemplate.execute(
    "orders",
    collection -> collection.find(filter)
        .explain(ExplainVerbosity.EXECUTION_STATS)
);

System.out.println(plan.toJson());
```

Đo ở tầng Spring bằng Micrometer/Observability cho **query shape** hoặc tên thao tác, ví dụ `orders.findRecent`, rồi tương quan theo thời gian với dashboards của shard:

```java
Timer.Sample sample = Timer.start(meterRegistry);
try {
    return mongoTemplate.find(query, Order.class);
} finally {
    sample.stop(
        Timer.builder("mongo.orders.findRecent")
            .tag("shape", "tenantAndTimeRange")
            .register(meterRegistry)
    );
}
```

Không thêm giá trị `tenantId`, `orderId` hoặc khóa người dùng vào metrics tags vì cardinality có thể bùng nổ và lộ ngữ cảnh nhạy cảm. Nếu cần điều tra tenant lớn, dùng truy vết/log được kiểm soát, mẫu tổng hợp theo nhóm tenant hoặc thống kê truy vấn có phân quyền. **App metric không tự biết shard thực thi**: phải đối chiếu `explain`, logs hoặc dữ liệu giám sát MongoDB.

## 6. Phân biệt nguyên nhân bằng bằng chứng

| Quan sát | Giả thuyết có thể kiểm tra | Bước kiểm chứng tiếp |
|---|---|---|
| Dung lượng gần đều, ghi mới dồn vào một shard | Range key đơn điệu hoặc hot range | Xem shard key, `numWritesByRange`, bộ lọc ghi, lịch sử vùng khóa |
| Dung lượng lệch lớn, shard nhiều dữ liệu cũng bận | Phân bố key lệch hoặc tài nguyên hết chỗ | `getShardDistribution()`, cardinality/frequency, CPU và I/O |
| Một tenant chiếm đa số request | Tenant nóng và key chưa phân tán được tải tenant | Tách workload theo tenant/cohort; kiểm tra hướng route và phân bố trong tenant |
| Nhiều shard đều bận, mỗi query fan-out | Scatter-gather, thiếu thành phần shard key trong query | `explain`, `percentageOfScatterGatherReads`, thiết kế lại query/index |
| QPS tương đương nhưng một shard p95/CPU cao | Index lệch, phần cứng, cache miss, ổ đĩa, election/migration | So cấu hình, explain của cùng query shape, logs/sự kiện |
| Đột biến chỉ xuất hiện lúc balancer chạy | Migration hoặc tác vụ nền tạm thời | Đánh dấu thời điểm migration; đo lại sau khi ổn định |
| Chỉ đọc từ một secondary chậm | Read preference/replica lag hoặc thành viên nghẽn | Đo secondary riêng, role, lag và connection routing |

Một cách suy luận hợp lý là: **bất thường lặp lại → shard cụ thể → collection/query shape cụ thể → vùng shard key hoặc chi phí thực thi cụ thể → biện pháp thay đổi có thể đo lại**. Nếu mắt xích nào thiếu dữ liệu, ghi giả thuyết kèm mức độ chắc chắn, không gọi đó là nguyên nhân đã xác nhận.

## 7. Cách xử lý và giới hạn của mỗi lựa chọn

Không có một lệnh cân bằng nào sửa được mọi dạng hot shard. Chọn cách xử lý dựa trên nguyên nhân đã đo:

1. **Sửa query/index trước khi đổi shard key**, nếu `docsExamined` cao, sort không có index, aggregate tốn CPU hoặc query scatter-gather. Index phù hợp giảm công việc trên mỗi request, nhưng không nhất thiết thay đổi tỷ lệ request đến từng shard.
2. **Giảm áp lực truy cập lặp** bằng cache, phân trang, giới hạn concurrency, gom ghi phù hợp hoặc điều tiết batch; chỉ dùng khi không làm sai tính nhất quán/độ mới dữ liệu và phải đo hiệu quả.
3. **Đánh giá lại shard key** dựa trên cardinality, frequency, monotonicity, targeting của read/write. Với key timestamp tăng liên tục, một key dạng hash có thể phân tán ghi tốt hơn nhưng làm truy vấn range theo thời gian khó target hiệu quả hơn. Phải đo toàn bộ tập query chính.
4. **Đối với tenant cực lớn**, chỉ hash `tenantId` có thể vẫn khiến cùng tenant tập trung. Có thể cần thêm thành phần phân tán phù hợp theo workload, thay mô hình lưu trữ hoặc giới hạn tải riêng tenant; kiểm chứng tác động tới truy vấn theo tenant và transaction.
5. **Di chuyển chunk hoặc chờ balancer** có thể giúp phân bố bytes/chunks, nhưng nếu một hot chunk vẫn chứa mọi ghi mới thì việc di chuyển có thể chỉ **chuyển điểm nóng sang shard khác**. Không coi “balanced chunks” là kết luận hết nóng.
6. **Resharding** là thay đổi có tác động lớn về dữ liệu, index, tài nguyên và vận hành. Chỉ thực hiện khi có phương án key mới, phép đo trước/sau, chiến lược rollback và cửa sổ vận hành phù hợp.

Ví dụ so sánh thiết kế:

| Shard key ứng viên | Ưu điểm có thể có | Rủi ro cần đo |
|---|---|---|
| `{ createdAt: 1 }` (range) | Hỗ trợ định tuyến truy vấn thời gian theo khoảng | Ghi mới tăng đơn điệu dễ dồn một hot range |
| `{ orderId: "hashed" }` | Thường phân tán ghi khi ID phân bố tốt | Truy vấn chỉ theo thời gian/tenant có thể phải fan-out |
| `{ tenantId: 1, createdAt: 1 }` | Truy vấn có tenant và time range có thể target tốt | Tenant lớn và ghi tăng theo thời gian vẫn có thể nóng |
| `{ tenantId: "hashed", createdAt: 1 }` | Phân tán nhiều tenant theo hash | Một tenant lớn có thể vẫn nóng; thời gian không là tiền tố shard key |

Các ứng viên trong bảng **không** phải cấu hình khuyến nghị mặc định. Với một workload hỗn hợp, cần kiểm tra truy vấn quan trọng nhất, mức phân tán của từng tenant, index và đặc tính của phiên bản triển khai trước khi quyết định.

## 8. Kiểm chứng sau thay đổi bằng số đo trước/sau

Dùng cùng bộ dashboard, thời gian cửa sổ và phân loại query shape trước/sau. Trong môi trường thử nghiệm, chạy tải tái lập có tỷ lệ đọc/ghi, số tenant, phân phối khóa và kích thước document gần với sản xuất. Trên production, so các khung giờ tương đồng và đánh dấu các sự kiện bất thường.

Bảng mẫu minh họa một kết quả **có khả năng cải thiện**:

| KPI | Trước thay đổi | Sau thay đổi | Mục tiêu đánh giá |
|---|---:|---:|---|
| Tỷ lệ ghi tối đa trên một shard | 79,2% | 38% | Gần mức chia đều hơn |
| CPU primary cao nhất | 91% | 58% | Giảm nguy cơ bão hòa |
| p95 của `orders.findRecent` | 240 ms | 85 ms | Đạt SLO theo endpoint |
| Tỷ lệ lỗi/timeout | 1,8% | 0,2% | Giảm rõ rệt |
| Tỷ lệ scatter-gather đọc | 8% | 9% | Không tăng mạnh như tác dụng phụ |
| Tổng throughput | 1.200 writes/s | 1.230 writes/s | So trong điều kiện tải tương đương |

**Không chỉ nhìn “shard-a bớt nóng”:** phải kiểm tra có tạo hot shard mới, throughput tổng có giảm, độ trễ p99 có tăng, fan-out có cao hơn, chi phí index và thao tác ghi có tăng, tính nhất quán ứng dụng có đổi hay không.

Để tránh kết luận nhầm:

- So **tỷ lệ tải trên từng shard** cùng với absolute ops/s và tổng throughput; hệ thống bớt request tự nhiên sẽ làm CPU giảm dù chưa chữa nguyên nhân.
- Chờ giai đoạn di chuyển dữ liệu/catch-up hoàn tất trước khi ghi nhận steady state, đồng thời lưu metrics lúc chuyển đổi để đánh giá rủi ro.
- Có đủ mẫu cho p95/p99 và tách query shape quan trọng; kiểm tra read/write riêng.
- Ghi nhận phiên bản MongoDB, cấu hình shard, read preference, index và dữ liệu trước/sau để giải thích khác biệt.

## 9. Mẫu báo cáo điều tra có thể tái sử dụng

```text
Thời gian đo: 2026-11-20 09:00–09:15 UTC
Phạm vi: shop.orders, 3 shard, cùng cấu hình primary
Triệu chứng: p95 orders.findRecent tăng, timeout tăng
Phân bố dữ liệu: ~34% / 32% / 33% số document
Phân bố ghi: 79,2% / 10,0% / 10,8% tổng writes/s
Tài nguyên: shard-a CPU ~91%, shard-b/c < 40%
Bằng chứng routing: query gần đây tập trung vào range createdAt mới
Giả thuyết: hot range trên shard key createdAt tăng đơn điệu
Loại trừ: không có election/migration kéo dài trong cửa sổ đo
Hành động đề xuất: thử nghiệm key ứng viên, đo fan-out, p95 và writeShare
Tiêu chí đạt: CPU/p95 dưới SLO; không tạo hot shard khác
Mức độ chắc chắn: cao/trung bình/thấp, kèm link dashboard và explain
```

Đây là **mẫu báo cáo**, không phải sự cố đã xảy ra. Trong thực tế, phải đính kèm dữ liệu đo gốc hoặc link dashboard và `explain` tương ứng. Nếu chỉ có `getShardDistribution()` mà thiếu số đo throughput/latency, kết luận phù hợp là *“đã kiểm tra phân bố dữ liệu, chưa đủ bằng chứng xác định hot shard”*.

## 10. Ghi nhớ khi vận hành Spring Data MongoDB

- Shard key quyết định khả năng target của query; repository hay `MongoTemplate` không tự biết cách “điều tải” giữa shard.
- **Phân bố document ≠ phân bố request ≠ phân bố chi phí xử lý**. Cần ít nhất ba nhóm số liệu: tốc độ truy cập, tài nguyên, độ trễ.
- Đo đúng phạm vi và lấy **chênh lệch counter theo thời gian**, thay vì so số counter tích lũy giữa các shard.
- Một query target đúng một shard vẫn có thể gây hot shard nếu phần lớn truy cập lặp lại cùng shard/range.
- Kiểm chứng thành công bằng **đường cơ sở trước/sau trên cùng workload**, không chỉ bằng việc chunk được phân bố lại.

### Tài liệu MongoDB tham khảo

- [Troubleshoot Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-troubleshooting-shard-keys/) — hot shard, hot chunk, key tăng đơn điệu và query scatter-gather.
- [db.collection.getShardDistribution()](https://www.mongodb.com/docs/manual/reference/method/db.collection.getsharddistribution/) — số liệu phân bố dữ liệu của sharded collection.
- [sh.getShardedDataDistribution()](https://www.mongodb.com/docs/manual/reference/method/sh.getshardeddatadistribution/) — thông tin phân bố trên cluster.
- [analyzeShardKey](https://www.mongodb.com/docs/manual/reference/command/analyzeshardkey/) — kiểm tra đặc tính shard key và phân bố read/write dựa trên query sampling (MongoDB 7.0+).
- [configureQueryAnalyzer](https://www.mongodb.com/docs/manual/reference/command/configurequeryanalyzer/) — cấu hình lấy mẫu truy vấn và chi phí sampling.
- [serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverstatus/) — chỉ số của instance và giới hạn của các counter.
