# Hệ thống hóa quan hệ giữa document, index, aggregation và topology trong MongoDB

## 1. Một bức tranh chung thay vì bốn chủ đề tách rời

Khi thiết kế MongoDB, các câu hỏi sau thường xuất hiện:

- **Document:** Mỗi bản ghi nên chứa những field nào? Có nên nhúng mảng phòng vào tin đăng hay lưu collection riêng?
- **Index:** Truy vấn tìm tin theo tenant, trạng thái, thành phố và thời gian tạo cần index gì?
- **Aggregation:** Làm thế nào đếm lượt xem, tính doanh thu hoặc thống kê theo thành phố mà không kéo toàn bộ documents về ứng dụng?
- **Topology:** Một replica set có đáp ứng được lưu lượng không? Khi nào phải sharding? Làm sao tránh truy vấn quét mọi shard?

Các quyết định này phụ thuộc lẫn nhau. Một document model có thể làm truy vấn đơn giản nhưng dẫn tới mảng phình to. Một index có thể tăng tốc tìm kiếm nhưng làm writes chậm hơn. Một aggregation có thể tính báo cáo đúng nhưng tiêu thụ nhiều RAM/disk. Một shard key có thể phân bố writes tốt nhưng khiến truy vấn theo tenant phải chạy trên nhiều shards.

Tư duy xuyên suốt:

~~~text
Nhu cầu nghiệp vụ + SLO + khối lượng dữ liệu
                   |
                   v
           Access patterns
                   |
         +---------+----------+
         |                    |
         v                    v
   Document model        Read/write shapes
         |                    |
         +----------+---------+
                    |
                    v
             Index design
                    |
                    v
          Query / aggregation
                    |
                    v
         Replica set / sharding
                    |
                    v
     Explain, profiler, metrics, tests
                    |
                    v
          Điều chỉnh thiết kế
~~~

**Không có lựa chọn document/index/aggregation/topology tối ưu độc lập với workload.** Một hệ thống ổn định được thiết kế từ cách nó thực sự đọc và ghi dữ liệu, rồi kiểm chứng bằng kế hoạch thực thi và chỉ số đo.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích mối liên hệ nhân quả giữa **document shape, access pattern, index, aggregation và topology**.
2. Chọn **embedding hay referencing** dựa trên tính cùng vòng đời, kích thước, tần suất thay đổi, quan hệ và số lượng phần tử.
3. Thiết kế **compound/multikey/partial/unique/TTL indexes** gắn với query shapes và write cost.
4. Dự đoán vì sao **$match/$sort/$group/$lookup/$unwind/$facet** làm tăng hoặc giảm chi phí.
5. Phân biệt **index-backed query**, **blocking aggregation**, **application-side join** và **materialized summary**.
6. Hiểu vai trò **replica set, primary/secondary, read preference, read/write concern, elections và rollback**.
7. Chọn hoặc đánh giá **shard key** theo read targeting, write distribution, cardinality, hot spots và data locality.
8. Lập ma trận quyết định cho workload CRUD, search, analytics và multi-tenant.
9. Sử dụng **mongosh** trong một lab có ba collections để so sánh nhiều phương án.
10. Xây kế hoạch kiểm chứng với **explain("executionStats"), metrics, tests, rollout và rollback**.

> **Ngữ cảnh:** Bài thuộc **Database Engine Document MongoDB → Tổng kết và tra cứu**. Đây là bài tổng hợp, không yêu cầu bạn đã đọc những bài trước. Ví dụ dùng một ứng dụng cho thuê nhà đa tenant; không diễn giải rằng MongoDB chỉ dành cho lĩnh vực này. Các tính năng, giới hạn và tối ưu hóa thay đổi theo MongoDB version/FCV/topology, vì vậy cần đối chiếu tài liệu chính thức khi triển khai. Lab chỉ ghi vào **mongo_system_map_lab_469** với các collections mang hậu tố **_469**; không chạy lệnh thao tác topology hoặc xóa dữ liệu production.

## 2. Bốn tầng là bốn loại quyết định khác nhau

| Tầng | Câu hỏi trung tâm | Đơn vị thường phải tối ưu | Hậu quả khi chọn sai |
| --- | --- | --- | --- |
| **Document** | Dữ liệu được gom/tách như thế nào? | Một document và quan hệ giữa documents | Truy vấn phải join nhiều, mảng vô hạn, update tranh chấp |
| **Index** | Cách truy cập dữ liệu nhanh hơn scan? | Index keys, sort order, selectivity | COLLSCAN, blocking SORT, write amplification |
| **Aggregation** | Tính kết quả từ tập documents bằng cách nào? | Stages, group cardinality, join fan-out | RAM/disk spill, output quá lớn, kết quả sai |
| **Topology** | Dữ liệu và reads/writes chạy trên nodes nào? | Replica members, shards, routing | Hot primary/shard, scatter-gather, lag, mất khả dụng |

Không thể dùng một tầng thay thế mọi tầng khác:

- Thêm index không khiến một document chứa array 20 MiB trở nên hợp lệ.
- Sharding không sửa được query $group có $push gom mọi documents thành một output BSON document.
- Embedded document không tự giảm số lượng writes nếu parent bị cập nhật liên tục.
- Chọn read preference secondary không đảm bảo dữ liệu mới ghi được nhìn thấy ngay.
- Aggregation $lookup không tự làm biến mất chi phí của một join không có index/phân bố qua shards.

### 2.1. Các đại lượng cần theo dõi

~~~text
Document size            | Kích thước BSON và mức tăng trưởng
Read amplification       | Bao nhiêu documents/bytes phải đọc cho 1 request
Write amplification      | Bao nhiêu index/data changes cho 1 write
Index selectivity        | Bao nhiêu records được lọc bởi điều kiện
Aggregation state        | Số group keys, sort entries, joined items
Network amplification    | Bao nhiêu dữ liệu chuyển giữa app/nodes/shards
Shard skew               | Lệch dữ liệu/traffic giữa shards
Consistency requirement  | Kết quả có cần thấy write mới hoặc snapshot không
SLO                     | p95/p99 latency, throughput, availability, cost
~~~

Thiết kế tốt không phải “càng nhiều index càng nhanh”, mà là tối ưu tổng các chi phí theo SLO ưu tiên.

## 3. Bắt đầu từ workload, không bắt đầu từ collection

Giả sử một dịch vụ có các chức năng:

| ID | Hành vi | Độ thường xuyên | Đặc điểm |
| --- | --- | --- | --- |
| Q1 | Xem chi tiết một listing theo ID và tenant | Rất cao | Đọc một document, độ trễ thấp |
| Q2 | Tìm listing PUBLISHED theo thành phố và trang mới nhất | Cao | Filter + sort + pagination |
| Q3 | Sửa giá/đổi trạng thái một listing | Trung bình | Atomic single-document update |
| Q4 | Cập nhật phòng hoặc amenities | Trung bình | Embedded array update |
| Q5 | Ghi sự kiện lượt xem | Rất cao | Append-heavy, nhiều documents nhỏ |
| Q6 | Đếm views/listing trong một ngày | Trung bình | Range scan + group |
| Q7 | Xem booking theo tenant và listing | Cao | Quan hệ một-nhiều có thể tăng |
| Q8 | Báo cáo doanh thu hằng tháng | Thấp | Aggregation nhiều dữ liệu |

Với mỗi workload, ghi:

- **Filter fields:** tenantId, listingId, status, cityCode, createdAt...
- **Sort fields và hướng sort:** createdAt DESC, _id DESC.
- **Projection:** những field nào thật sự cần.
- **Page/limit:** một bản ghi, 20 bản ghi hay xuất mọi records.
- **Cardinality:** một listing có bao nhiêu rooms, bookings, view events.
- **Write frequency:** một ngày có bao nhiêu cập nhật và ghi mới.
- **Consistency:** có cần read-your-writes, transactional invariant, snapshot không.
- **Growth:** số documents, kích thước, retention theo thời gian.
- **Tenant isolation:** quyền được thực thi ở đâu.
- **Latency/cost target:** p99 và giới hạn tài nguyên.

Đây là **access-pattern inventory**. Nếu bỏ qua inventory, rất dễ làm schema đẹp trên sơ đồ nhưng chậm trong production.

## 4. Case study tổng thể: ba loại dữ liệu

Ứng dụng cho thuê nhà có:

1. **listings:** tin đăng, metadata, phòng, trạng thái.
2. **view_events:** lượt xem append-only, tăng rất nhanh.
3. **bookings:** yêu cầu đặt xem nhà, có trạng thái và lịch sử xử lý nghiệp vụ.

~~~text
Tenant
  |
  +-- Listings
  |      |
  |      +-- rooms[]        Nhúng: thường đọc cùng listing
  |      +-- tags[]         Nhúng: giới hạn số lượng
  |
  +-- View events          Tham chiếu listingId
  |      |
  |      +-- time / event type / device
  |
  +-- Bookings             Tham chiếu listingId, tenantId
         |
         +-- status, requestedAt, revision
~~~

Lý do sơ bộ:

- **rooms** là phần tử tương đối nhỏ, thường hiển thị cùng listing và cùng vòng đời. Có thể embed nếu số lượng có giới hạn.
- **view_events** tăng không giới hạn theo traffic; không nhúng vào listing vì document growth, contention và BSON limit.
- **bookings** có workflow, index, quyền và tần suất thay đổi riêng; thường tách collection, lưu listingId/tenantId để truy vấn.

Đây là giả định cho case study, không phải một khuôn mẫu bắt buộc. Nếu mỗi phòng có inventory độc lập với hàng nghìn thay đổi/giây, room có thể cần collection riêng.

## 5. Document model: đơn vị đọc và đơn vị cập nhật

### 5.1. Một BSON document listing

~~~javascript
{
  _id: "l469-001-01",
  labTag: "system469-v1",
  tenantId: "tenant-001",
  title: "Căn hộ có ban công",
  cityCode: "HCM",
  status: "PUBLISHED",
  monthlyRentVnd: NumberDecimal("9500000.00"),
  rooms: [
    { roomId: "bed-1", type: "BEDROOM", areaSqm: 18 },
    { roomId: "kitchen-1", type: "KITCHEN", areaSqm: 8 }
  ],
  tags: ["FURNISHED", "BALCONY"],
  createdAt: ISODate("2026-01-15T09:00:00Z"),
  revision: NumberLong("1")
}
~~~

MongoDB có **atomicity ở mức một document** cho một update operation. Điều này giúp cập nhật nhiều fields trong listing cùng lúc:

~~~javascript
db.listings_469.updateOne(
  { _id: "l469-001-01", tenantId: "tenant-001" },
  {
    $set: { status: "PUBLISHED", monthlyRentVnd: NumberDecimal("9700000.00") },
    $inc: { revision: NumberLong("1") }
  }
);
~~~

Trong lab thực tế, thêm labTag như các lệnh phía sau. **Single-document atomicity không tự giải quyết lost update giữa hai writes**, nên vẫn cần revision/CAS hoặc atomic operators đúng mục đích.

### 5.2. Embedding giảm read joins

Với detail API cần listing + rooms:

~~~text
Embedded:
  1 query -> 1 listing BSON -> rooms[] đã có

Referenced:
  query listing
  query rooms by listingId
  hoặc $lookup trong aggregation
~~~

Embedding thường có lợi khi related data:

- Được đọc cùng nhau.
- Có số lượng bounded.
- Có lifecycle cùng parent.
- Không có quyền/retention phức tạp khác nhau.
- Cần update nhiều fields nguyên tử trong một root document.

### 5.3. Referencing tránh unbounded growth

Không nên lưu:

~~~javascript
{
  _id: "listing-x",
  views: [
    // Một phần tử cho từng lượt xem trong nhiều năm
  ]
}
~~~

Nếu view rate tăng, mảng phình to, write contention và document BSON size limit trở thành bottleneck. Tách:

~~~javascript
{
  _id: "evt-1",
  tenantId: "tenant-001",
  listingId: "listing-x",
  createdAt: ISODate("2026-01-15T09:01:00Z"),
  eventType: "VIEW"
}
~~~

Khi cần hiển thị tổng views, có thể aggregate hoặc duy trì summary có kiểm soát.

### 5.4. Trade-off của nhúng dữ liệu

| Câu hỏi | Embedding có xu hướng phù hợp | Referencing có xu hướng phù hợp |
| --- | --- | --- |
| Số phần tử tối đa | Nhỏ/bounded | Rất lớn hoặc unbounded |
| Đọc cùng parent | Gần như luôn | Hiếm khi |
| Cập nhật mỗi phần tử | Thấp/vừa | Rất cao/độc lập |
| Cùng lifecycle | Có | Không |
| Atomic update | Một root document | Nhiều documents có thể cần transaction |
| Trùng lặp metadata | Giảm joins | Có thể phải đọc nhiều sources |
| Query theo phần tử | Multikey index có thể giúp | Index collection con độc lập |
| Shard placement | Toàn embedded data cùng parent | Có thể phân bố riêng theo key |

### 5.5. 16 MiB không phải “mục tiêu kích thước”

Giới hạn BSON document thông thường là **16 MiB**. Nhưng không nên để documents tăng gần giới hạn rồi mới tách. Một document vài MiB có thể đã gây:

- Chuyển dữ liệu thừa cho detail/list API.
- Tốn cache/working set.
- Tăng chi phí update và network.
- Khó projection/index và contention.

Chọn ngưỡng dữ liệu phù hợp workload và đo document-size distribution.

### 5.6. Dữ liệu lặp có thể là chủ đích

Event chứa **cityCodeAtView** là snapshot thành phố lúc xảy ra lượt xem:

~~~javascript
{
  listingId: "l469-001-01",
  cityCodeAtView: "HCM",
  createdAt: ISODate("2026-01-15T09:01:00Z")
}
~~~

Nếu listing sau này đổi thành phố, báo cáo lịch sử vẫn đúng theo sự kiện. Nhưng snapshot field cần contract về thời điểm, nguồn và migration; không tự sao chép mọi field chỉ để “denormalize”.

## 6. Document model quyết định index nào cần thiết

### 6.1. Query listing theo city và trạng thái

~~~javascript
db.listings_469.find({
  tenantId: "tenant-001",
  status: "PUBLISHED",
  cityCode: "HCM"
}).sort({ createdAt: -1, _id: -1 }).limit(20);
~~~

Một candidate index:

~~~javascript
{
  tenantId: 1,
  status: 1,
  cityCode: 1,
  createdAt: -1,
  _id: -1
}
~~~

Index được thiết kế theo **equality predicates trước các sort keys** của workload này. Nếu API không lọc cityCode, index có field cityCode trước createdAt có thể không hỗ trợ thứ tự sort theo kỳ vọng. Cần một index khác cho query phổ biến không có city filter, hoặc điều chỉnh yêu cầu.

### 6.2. Index thay đổi theo mô hình dữ liệu

Nếu cityCode nằm sâu trong:

~~~javascript
{ address: { cityCode: "HCM" } }
~~~

thì query/index path là:

~~~javascript
{ "address.cityCode": 1 }
~~~

Không thể đổi code Java field names rồi mặc định các index MongoDB cũ tự di chuyển. Schema migration và index migration là hai phần của cùng một rollout.

### 6.3. Mảng rooms dẫn đến multikey index

~~~javascript
db.listings_469.createIndex({
  tenantId: 1,
  "rooms.type": 1,
  "rooms.areaSqm": 1
});
~~~

MongoDB tạo **multikey index** khi indexed path đi qua mảng. Điều này giúp một số array queries nhưng có constraints riêng.

Đặc biệt:

- Query muốn nhiều điều kiện **trên cùng một phần tử** nên xem xét **$elemMatch**.
- Multikey indexes có giới hạn với các compound key patterns chứa nhiều independent arrays; không tự tạo một compound index từ hai array fields bất kỳ.
- Unique multikey index **không tự đảm bảo roomId duy nhất bên trong cùng một listing** theo business invariant mong muốn.
- Sort và index bounds của array fields cần phân tích bằng explain.

### 6.4. Đếm số room bằng array không cần query join

Nếu room array nhỏ:

~~~javascript
{
  $project: {
    title: 1,
    roomCount: { $size: "$rooms" }
  }
}
~~~

Nhưng nếu list API thường xuyên yêu cầu roomCount và rooms rất lớn, có thể cân nhắc field đếm được duy trì có invariant, hoặc tách data. Việc thêm field tổng hợp đặt ra **consistency maintenance** khi rooms thay đổi.

## 7. Từ predicate tới compound index: sơ đồ tra cứu

~~~text
Business request
  tenant=001, PUBLISHED, HCM
  order newest first
  pageSize=20
         |
         v
Predicate equality:
  tenantId, status, cityCode
         |
         v
Sort:
  createdAt DESC, _id DESC
         |
         v
Index candidate:
  tenantId ASC
  status ASC
  cityCode ASC
  createdAt DESC
  _id DESC
         |
         v
EXPLAIN:
  Does it avoid COLLSCAN/blocking SORT?
  How many keys/docs examined per returned item?
~~~

### 7.1. ESR heuristic

**Equality–Sort–Range (ESR)** là heuristic hữu ích khi chọn thứ tự fields trong compound index:

1. Equality predicates cố định nhóm tài liệu.
2. Sort suffix có thể cho phép trả dữ liệu có thứ tự.
3. Range giúp giới hạn hoặc lọc dữ liệu bổ sung.

Đây **không phải luật tuyệt đối**. Range predicate chọn lọc rất cao đôi khi nên được ưu tiên; collation, query shape, multikey và optimizer có thể thay đổi kế hoạch tốt nhất.

### 7.2. Prefix matters

Index:

~~~javascript
{ tenantId: 1, status: 1, cityCode: 1, createdAt: -1 }
~~~

thường có ích với prefix tenantId, hoặc tenantId+status, hoặc tenantId+status+cityCode. Query chỉ filter **cityCode** khó tận dụng phần đầu của index như một access path tối ưu.

Tương tự, nếu query bỏ status nhưng sort theo createdAt, index này không mặc nhiên cung cấp thứ tự mong muốn vì các index keys giữa không được ràng buộc bằng equality.

### 7.3. Sort ổn định

Nếu nhiều documents cùng createdAt, chỉ sort **createdAt DESC** không cho total ordering. Thêm **_id DESC** làm tie-breaker:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

Điều này còn ảnh hưởng **keyset pagination** và index suffix, không chỉ hiển thị.

### 7.4. Partial index

Nếu hệ thống chủ yếu tìm listings còn hiệu lực:

~~~javascript
db.listings_469.createIndex(
  {
    tenantId: 1,
    cityCode: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "active_published_listings",
    partialFilterExpression: {
      status: "PUBLISHED"
    }
  }
);
~~~

Đây là candidate **partial index** cho documents PUBLISHED. Query phải có predicate phù hợp để optimizer có thể dùng index mà không bỏ sót records. Index không chứa DRAFT nên không dùng tùy tiện cho query toàn bộ trạng thái.

Trong lab, nếu index này được tạo, vẫn không có nghĩa soft-deleted PUBLISHED tự bị loại: schema/partial predicate phải bao gồm chính xác điều kiện đang dùng.

### 7.5. Unique index

Booking có idempotency key theo tenant:

~~~javascript
db.bookings_469.createIndex(
  { tenantId: 1, requestKey: 1 },
  { unique: true, name: "uq469_tenant_request_key" }
);
~~~

Nó bảo vệ một tổ hợp khóa ở server. Tuy nhiên:

- Các documents thiếu requestKey/null có semantics unique index cần xét.
- Trên sharded collection, **unique index có các yêu cầu liên quan shard key**; không tự giả định unique toàn cluster với một index tùy ý.
- Không dùng unique index như thay thế cho authorization hoặc kiểm tra payload retry.

### 7.6. TTL index

Events cũ có thể cần retention:

~~~javascript
db.view_events_469.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 60 * 60 * 24 * 90 }
);
~~~

TTL deletion **bất đồng bộ**, không xảy ra đúng mili giây hết hạn. Với retention pháp lý hoặc yêu cầu kiểm toán, phải có chính sách chính xác, archive và verification. **Không tự tạo TTL trên dữ liệu lab trước khi kiểm ý nghĩa retention**, vì nó có thể làm biến mất dữ liệu thực hành khi thời điểm tạo đã cũ.

### 7.7. Index chi phí ở đường ghi

Mỗi index bổ sung có:

- Disk footprint.
- Memory/cache footprint.
- Write amplification khi indexed fields thay đổi.
- Chi phí build và maintenance.
- Khả năng ảnh hưởng replication/lag.

Index nên xuất phát từ workload thật và được theo dõi usage, không “index mọi field” để cảm thấy an toàn.

## 8. Explain: nối index với thực thi thực tế

Chạy:

~~~javascript
db.listings_469.find({
  tenantId: "tenant-001",
  status: "PUBLISHED",
  cityCode: "HCM"
}).sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
~~~

Các chỉ số quan trọng:

| Chỉ số/dấu hiệu | Câu hỏi |
| --- | --- |
| **winningPlan** | Dùng IXSCAN hay COLLSCAN? Có SORT không? |
| **totalKeysExamined** | Đã duyệt bao nhiêu index keys? |
| **totalDocsExamined** | Đã tải bao nhiêu documents? |
| **nReturned** | Trả bao nhiêu kết quả? |
| **executionTimeMillis** | Thời gian server-side lần đo đó? |
| **indexBounds** khi có | Range index có hẹp như kỳ vọng không? |
| **usedDisk/spills** khi có | Stage nào dùng temporary disk? |

**Tỷ lệ keys/documents examined so với nReturned** là dấu hiệu để phát hiện scan thừa, nhưng không có một ngưỡng cố định đúng cho mọi aggregation. Với grouped queries, nReturned thấp là bình thường dù phải đọc tất cả documents liên quan.

### 8.1. Có index nhưng planner không dùng

Các lý do có thể:

- Collection rất nhỏ; COLLSCAN rẻ hơn.
- Predicate không đủ selective.
- Query thiếu index prefix.
- Collation không phù hợp.
- Sort/aggregation stage trước đó phá indexed ordering.
- Multikey constraints.
- Stats/planner/version khác môi trường dự đoán.

Không ép hint index trong production chỉ để output explain “đẹp” mà chưa benchmark và kiểm tra correctness.

### 8.2. Covered query

Nếu projection/filter/sort có thể được phục vụ bằng index keys mà không cần fetch document, có thể giảm reads. Nhưng không coi đây là đích tối thượng; một index quá rộng để cover mọi field có thể tăng write cost/disk và làm hệ chậm tổng thể.

### 8.3. Explain không đo toàn bộ application latency

Explain không bao gồm đầy đủ:

- Queue trong connection pool.
- Serialization và network tới app.
- HTTP/auth processing.
- Contention với workloads khác.
- Cache warm/cold và peak traffic.

Vì vậy đo **query metrics và end-to-end p95/p99** song song.

## 9. Aggregation: bước biến access path thành thống kê

Giả sử collection **view_events** có từng event:

~~~javascript
{
  _id: "ev469-0001",
  tenantId: "tenant-001",
  listingId: "l469-001-01",
  eventType: "VIEW",
  createdAt: ISODate("2026-01-15T09:05:00Z")
}
~~~

Yêu cầu: top listings theo số VIEW trong một ngày.

~~~javascript
db.view_events_469.aggregate([
  {
    $match: {
      tenantId: "tenant-001",
      eventType: "VIEW",
      createdAt: {
        $gte: ISODate("2026-01-15T00:00:00Z"),
        $lt: ISODate("2026-01-16T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$listingId",
      views: { $sum: 1 }
    }
  },
  { $sort: { views: -1, _id: 1 } },
  { $limit: 10 }
]);
~~~

Lưu ý:

1. **$match** thu hẹp theo tenant/type/time.
2. Index giúp chọn documents cần đưa vào pipeline.
3. **$group** tích lũy views theo listingId.
4. Sort trên **các groups đã tính**, không sort mọi raw events.
5. Limit lấy top 10 groups sau khi tính chính xác count.

### 9.1. Vì sao index vẫn quan trọng cho aggregation?

Aggregation không phải hộp đen chạy “bên ngoài index”. Các stages đầu như $match và một số $sort có thể tận dụng indexes. Khi optimizer push-down điều kiện phù hợp, số documents/bytes đưa vào blocking stages giảm.

### 9.2. Vì sao index không thể làm tất cả?

Index có thể giới hạn **input range**, nhưng exact count/group có thể vẫn phải quét mọi qualifying events. Nếu có 20 triệu VIEW events của tháng:

- Index giúp tránh quét events ngoài tenant/time.
- $group vẫn phải tích lũy số views theo listing hoặc tận dụng các tối ưu phù hợp.
- Duy trì **daily summary** có thể giảm read cost cho báo cáo thường xuyên.

### 9.3. $unwind và multikey

~~~javascript
[
  { $unwind: "$rooms" },
  {
    $group: {
      _id: "$rooms.type",
      n: { $sum: 1 }
    }
  }
]
~~~

Sau $unwind, một listing có hai rooms tạo hai rows. Nếu mục tiêu là **số listings có bedroom**, đếm sau unwind có thể double count khi một listing có nhiều bedrooms. Muốn đúng phải xác định đơn vị thống kê: **rooms** hay **distinct listings**.

### 9.4. $lookup và mô hình referencing

Nếu events chỉ có listingId, báo cáo cần tiêu đề listing có thể dùng $lookup:

~~~javascript
{
  $lookup: {
    from: "listings_469",
    localField: "_id",
    foreignField: "_id",
    as: "listing"
  }
}
~~~

Đoạn trên giả định stage trước đã group theo listingId. Chi phí join phụ thuộc:

- Foreign key/index.
- Cardinality.
- Các fields cần project.
- Tenant isolation.
- Sharded topology và routing/placement.

Đối với multi-tenant, một join chỉ so ID đôi khi chưa đủ nếu ID không unique toàn cục hoặc tenant boundary cần explicit filter. Trong ứng dụng thật cần kiểm cả **tenantId** và quyền đọc.

### 9.5. $facet và một document quá lớn

$facet trả một result document có arrays. Nếu nhánh data chứa hàng triệu documents, có thể vượt:

- Giới hạn của bản thân **$facet** (không thể spill cho facet result).
- **16 MiB BSON output document** cuối cùng.

Đừng dùng $facet để gói toàn bộ paginated listings thành một document duy nhất. Bound mỗi nhánh hoặc tách details/summary APIs.

### 9.6. $setWindowFields

Window functions phù hợp với rolling metrics hoặc running total **cho từng row**. Nhưng nếu chỉ cần tổng theo ngày/listing, $group thường đơn giản hơn. Partition/order/window state có thể dùng memory đáng kể; lựa chọn đúng semantics trước khi tối ưu.

### 9.7. 100 MB memory, allowDiskUse

Nhiều stages blocking có giới hạn memory riêng và có thể spill temporary files khi được phép. Từ MongoDB 6.0, **allowDiskUseByDefault** ảnh hưởng default behavior; command option **allowDiskUse** có thể override trong điều kiện hỗ trợ.

Nhưng:

- **allowDiskUse không xóa giới hạn 16 MiB BSON output**.
- Một số accumulator như $push có memory restrictions riêng.
- $facet không spill its 100 MB facet result document.
- Spill có thể tăng disk I/O và latency.
- Các memory limits có thể thay đổi theo version (ví dụ per-operation memory limits từ các phiên bản mới).

Muốn sửa, ưu tiên thay đổi query shape/index, không chỉ bật spill.

## 10. Aggregation và summary/materialized view

### 10.1. Tính mỗi lần request

~~~text
GET /analytics/top-listings
  -> scan qualifying view_events
  -> group
  -> sort
  -> response
~~~

Đơn giản, dữ liệu có thể mới nhất theo read semantics, nhưng có thể quá tốn kém khi cùng báo cáo chạy nhiều lần.

### 10.2. Summary cập nhật theo lịch hoặc sự kiện

~~~javascript
{
  _id: "tenant-001|l469-001-01|2026-01-15",
  tenantId: "tenant-001",
  listingId: "l469-001-01",
  dayUtc: ISODate("2026-01-15T00:00:00Z"),
  viewCount: NumberLong("125"),
  updatedAt: ISODate("2026-01-16T00:02:00Z")
}
~~~

~~~text
Raw view_events
      |
 Batch/stream aggregation
      |
 daily_view_summary
      |
 Dashboard reads small number of summaries
~~~

Đánh đổi:

- Read rẻ hơn.
- Ghi/duy trì summary tốn thêm.
- Có **freshness lag** và reconciliation.
- Late events cần cập nhật lại bucket.
- Duplicated events/retries có thể double count nếu consumer không idempotent.

### 10.3. $merge không phải phép tối ưu vô tác dụng phụ

Một pipeline kết thúc bằng **$merge** hoặc **$out** có thể thay đổi collection đích. Không thêm stage ghi chỉ để “làm aggregation nhanh hơn” trên production. Phải kiểm:

- Quyền ghi và target namespace.
- Key uniqueness và on/matched semantics.
- Idempotency khi job chạy lại.
- Trùng lịch jobs.
- Memory/disk/concurrency.
- Rollback và reconciliation.

### 10.4. Khi summary tốt hơn query thô

Tổng hợp trước có ích khi:

- Dashboard được đọc rất nhiều lần.
- Dữ liệu raw quá lớn và append-heavy.
- Business chấp nhận độ trễ vài phút.
- Có cách reconcile count.

Nếu quyết định cần tính mới nhất từng mili giây và update đến từ nhiều sources, cần phân tích consistency/transaction semantics, không mặc định async summary đáp ứng.

## 11. Topology mức 1: replica set và độ tin cậy

~~~text
                 Application
                      |
                  Driver URI
                      |
          +-----------+-----------+
          |           |           |
        Primary    Secondary A  Secondary B
        writes       replica      replica
          |             ^           ^
          +----- oplog --+-----------+
~~~

**Replica set** duy trì nhiều bản sao dữ liệu, thường có một primary nhận writes và các secondary sao chép. Khi primary không còn khả dụng, election có thể chọn primary mới tùy cấu hình và điều kiện.

### 11.1. Replica set không chia dữ liệu thành các phần nhỏ để scale writes

Mỗi data-bearing member của một replica set thường chứa bản sao đầy đủ của tập dữ liệu replica set. Thêm secondary:

- Tăng khả năng sẵn sàng/dự phòng.
- Có thể phục vụ read workloads phù hợp.
- Không tự chia một write workload lớn trên nhiều primaries độc lập.

Nếu một primary bị giới hạn write throughput hoặc data size không phù hợp một replica set, sharding có thể cần được đánh giá.

### 11.2. Read preference

| Read preference | Đặc điểm |
| --- | --- |
| **primary** | Đọc từ primary, thường phù hợp consistency expectations của ứng dụng |
| **primaryPreferred** | Ưu tiên primary, fallback theo semantics |
| **secondary** | Đọc secondary; có thể thấy dữ liệu trễ |
| **secondaryPreferred** | Ưu tiên secondary, fallback khi cần |
| **nearest** | Chọn member dựa trên tiêu chí độ trễ/driver selection, không tự là latest data |

Đọc secondary có thể giảm tải primary trong workload thích hợp nhưng **replication lag** khiến dữ liệu vừa ghi chưa hiện ngay. Các read concerns/sessions/causal consistency ảnh hưởng guarantee thực tế.

### 11.3. Write concern

**w:1**: write được acknowledged theo semantics của một member (thường primary).  
**w:"majority"**: đợi acknowledgment bởi majority theo write concern semantics, bền vững hơn qua một số failover/rollback scenarios.

Không xem w:"majority" là backup hay bảo đảm không thể mất dữ liệu trong mọi thảm họa. Cần hiểu journaling/defaults/timeout và backup/restore chính sách.

### 11.4. Read concern

Các mức như **local, majority, snapshot, linearizable** có guarantees và điều kiện khác nhau. Không dùng thuật ngữ “consistent” chung chung.

- **local** có thể thấy dữ liệu chưa majority committed tùy trường hợp.
- **majority** đọc dữ liệu đã majority-committed theo semantics tương ứng.
- **snapshot** phục vụ nhu cầu đọc một snapshot nhất quán trong những context được hỗ trợ.
- **linearizable** có điều kiện/chi phí riêng và không phải default cho mọi read.

Lựa chọn cần gắn với workflow. Ví dụ booking vừa được confirm rồi đọc status nên xác định kỳ vọng **read-your-writes**, session/causal semantics và read preference.

### 11.5. Không nhầm replication với backup

Một lệnh delete nhầm có thể được replicate rất nhanh tới mọi members. Replica set không thay thế:

- Backup định kỳ và retention.
- Restore drills.
- Point-in-time recovery khi cần.
- Permission separation.
- Disaster recovery plans.

### 11.6. Index trên replica set

Indexes cần được xây và duy trì trên members theo quy trình server; index operations ảnh hưởng:

- Disk/CPU/write amplification.
- Replication/workload capacity.
- Query latency khi chuyển traffic sang secondary.

Không tạo hàng chục index lớn trong incident khi disk đang căng.

## 12. Topology mức 2: sharded cluster

~~~text
                   Application
                        |
                      mongos
                        |
          +-------------+-------------+
          |             |             |
        Shard A       Shard B       Shard C
      (replica set) (replica set) (replica set)
          |             |             |
       Data subset   Data subset    Data subset

        Config server replica set
             (cluster metadata)
~~~

Sharding phân bố dữ liệu giữa nhiều **shards**, thường mỗi shard là một replica set. **mongos** nhận operations và route dựa vào shard key/metadata; config server replica set lưu metadata cluster.

### 12.1. Hai chiều scale khác nhau

| Cần | Replica set | Sharding |
| --- | --- | --- |
| HA/failover | Mục tiêu chính | Thường mỗi shard là replica set |
| Scale read phù hợp | Có thể dùng secondary | Có thể phân bố read workload trên shards |
| Scale tổng data size | Mỗi member giữ đầy đủ replica set data | Data phân bố theo shards |
| Scale write throughput | Primary là điểm nhận writes | Writes có thể phân bố theo shard key |
| Cross-node query complexity | Tương đối thấp | Có routing, merge và scatter-gather |
| Vận hành | Election/replication/backup | Thêm balancing/shard key/chunks/metadata |

Thêm shards không giải quyết một request phải quét **toàn bộ** dữ liệu nếu shard key/query không hỗ trợ targeting.

### 12.2. Shard key là quyết định lâu dài

Shard key ảnh hưởng:

- Document nào thuộc shard nào.
- Các reads/writes có target một shard không.
- Distribution và hot spots.
- Chunk/range management và balancing.
- Một số constraints của unique index và updates.
- Co-location của related data.

Không chọn shard key chỉ vì field có cardinality cao mà bỏ qua query patterns.

### 12.3. Range-based shard key

Ví dụ dựa trên tenantId:

~~~text
Shard key: { tenantId: 1 }
~~~

Lợi ích tiềm năng:

- Query có equality tenantId có thể được target phù hợp.
- Các documents liên quan tenant có locality theo range policy.

Rủi ro:

- Một tenant cực lớn/hot có thể gây lệch.
- Nếu một tenant có rất nhiều writes, phân bố một tenant trên nhiều shards bị hạn chế tùy shard key cardinality/chunk.
- Monotonic key có thể tạo hotspot khi inserts tập trung vào range mới.

### 12.4. Hashed shard key

~~~text
Shard key: { tenantId: "hashed" }
~~~

Hash giúp phân bố key values đều hơn khi có nhiều giá trị, giảm một số dạng sequential hot spots. Nhưng:

- Một tenant rất nóng vẫn có thể tập trung nhiều requests vào vị trí dữ liệu tương ứng.
- Range queries theo tenantId không có lợi như range-based key.
- Không tự giữ địa lý/nhóm dữ liệu liên quan cùng shard theo ý bạn.

**Hashed không phải phép chia một tenant hot thành nhiều shards** nếu tất cả documents của tenant dùng cùng một hashed key value.

### 12.5. Compound shard key

Có thể xem xét thêm một thành phần đủ phân tán như listingId/bucket, tùy query patterns và yêu cầu transaction/locality:

~~~text
{ tenantId: 1, listingId: 1 }
~~~

Không kết luận nó luôn tốt hơn tenantId đơn lẻ; các reads chỉ có tenantId có thể target nhiều chunks/shards và các documents cùng listing có thể/không thể được co-locate theo thiết kế thực tế.

### 12.6. Targeted vs scatter-gather

~~~text
Query with shard key equality
  -> mongos có thể target shard chứa key

Query thiếu shard key
  -> có thể phải gửi tới nhiều shards
  -> merge results ở cluster
~~~

Một index trên từng shard **không tự loại bỏ scatter-gather**. Mỗi shard có thể chạy index hiệu quả nhưng toàn request vẫn chờ nhiều shards, trả nhiều network results và merge/sort.

### 12.7. Balancer không giải quyết mọi hot key

Balancer có thể di chuyển chunks/ranges để cân bằng dữ liệu, nhưng:

- Single highly active key có thể vẫn gây hotspot.
- Data skew do tenant/traffic cần nhìn theo workload chứ không chỉ bytes.
- Chunk migrations có operational overhead.

Theo dõi per-shard CPU/IOPS, ops/s, data size và routing distribution.

### 12.8. Sharding và uniqueness

Unique constraints trên sharded collections có điều kiện về shard key/index prefix theo MongoDB manual. Một business uniqueness constraint như **(tenantId, requestKey)** phải được thiết kế cùng shard key/topology hoặc bảo vệ qua kiến trúc khác; đừng chỉ gọi createIndex(unique:true) rồi giả định toàn cluster đảm bảo theo mọi cấu hình.

## 13. Quan hệ giữa document và shard key

Một embedded document luôn nằm cùng root document:

~~~text
Listing document
  _id, tenantId, rooms[]
           |
         shard by root key
           |
  rooms[] nằm trong cùng BSON document
~~~

Điều này giúp cập nhật rooms atomic trong một root document và không cần cross-shard join. Nhưng nếu rooms quá lớn hoặc cập nhật cạnh tranh, mọi writes có thể tập trung vào cùng root document.

Ngược lại:

~~~text
listings collection: listingId
rooms collection: listingId + roomId
~~~

cho phép rooms phát triển độc lập, nhưng cần:

- Index lookup trên rooms.
- Chính sách xóa/cascade.
- Consistency khi thay nhiều documents.
- Shard key alignment nếu cần locality hoặc targeted joins.

### 13.1. Quan hệ một-nhiều có hai tính chất riêng

Hỏi đồng thời:

1. **Kích thước một quan hệ:** 2 rooms hay 2 triệu view events?
2. **Tần suất thay đổi:** một lần/tháng hay hàng nghìn updates/giây?

Đây là lý do hai quan hệ đều “listing có nhiều X” nhưng model tốt có thể khác nhau.

### 13.2. Tenant partitioning không chỉ là schema

TenantId cần xuất hiện nhất quán trong:

- Authorization.
- Query filters.
- Relevant compound indexes.
- Shard key decision nếu có.
- Aggregation $match và $lookup joins.
- Backups/restores/retention policies.
- Logs/metrics có giới hạn cardinality.

TenantId trong document nhưng **không có ở query** sẽ không giúp routing hay isolation.

## 14. Aggregation trên sharded cluster

~~~text
           Query from app
                  |
                mongos
                  |
      +-----------+-----------+
      |                       |
   Shard A                 Shard B
  $match/$group           $match/$group
      |                       |
      +-----------+-----------+
                  |
             Merge stage
             sort/limit
                  |
                Client
~~~

MongoDB có thể chia pipeline giữa shards và merging pipeline. Vị trí mỗi stage được thực thi phụ thuộc version, topology và semantics.

### 14.1. Push filtering tới shard

Một $match sớm có filter shard key và selective predicates có thể giảm:

- Data scanned.
- Documents truyền giữa nodes.
- Merge-stage memory.

Nhưng nếu query thiếu shard key, mongos vẫn có thể phải route đến nhiều shards.

### 14.2. $group có thể tính partial

Với một số accumulators có khả năng kết hợp, server có thể tính một phần ở shards rồi merge. Ví dụ count per listing:

~~~text
Shard A: listing-1 -> 120 views
Shard B: listing-1 -> 80 views
Merge:   listing-1 -> 200 views
~~~

Nhưng các pipelines chứa operations phụ thuộc order hoặc non-combinable state có constraints riêng; không suy luận mọi group đều tự tối ưu lý tưởng.

### 14.3. $sort cần merge order

Một global sort/top-K có thể yêu cầu merging sorted streams hoặc blocking sort ở merge site. Từ “mỗi shard có index” không đủ để khẳng định toàn query không có merge overhead.

### 14.4. $lookup cross-shard

Tính hiệu quả của $lookup phụ thuộc collection được join có sharded không, query predicates/indexes, server version và placement. Có thể hỗ trợ join với sharded foreign collections ở các phiên bản hiện đại nhưng **không miễn phí**. Đôi khi denormalization hoặc pre-aggregation là lựa chọn tốt hơn.

### 14.5. Resharding là chiến dịch vận hành

Nếu shard key hiện tại gây hotspot, các phiên bản MongoDB hiện đại cung cấp khả năng thay đổi shard key/resharding trong những điều kiện nhất định. Điều này không nên xem như thay một index đơn giản: phải đánh giá disk, I/O, timeline, application compatibility và rollback.

## 15. Consistency gắn với bốn tầng

Một tính năng booking cần:

1. Tạo booking REQUESTED.
2. Chặn hai booking xung đột theo policy.
3. Lưu trạng thái CONFIRMED.
4. API đọc ngay sau confirm phải thấy trạng thái phù hợp.
5. Dashboard thống kê số booking có thể cập nhật trễ.

Các kỳ vọng không giống nhau.

### 15.1. Trong một document

Nếu listing lưu availability và cần một update atomic trên chính document đó:

~~~javascript
db.listings_469.updateOne(
  {
    _id: listingId,
    tenantId,
    availableSlots: { $gt: 0 }
  },
  {
    $inc: {
      availableSlots: -1,
      revision: NumberLong("1")
    }
  }
);
~~~

Đây là ví dụ conceptual, **listing mẫu lab không có availableSlots**. Atomic conditional update có thể bảo vệ một invariant đơn giản trong một root document.

### 15.2. Giữa hai documents/collections

Nếu phải cập nhật listing availability và insert booking **cùng một transaction**, cần dùng multi-document transaction trên deployment hỗ trợ, hoặc thiết kế event/outbox/saga nếu phù hợp. Transaction có chi phí và semantics riêng, nhất là cross-shard; không dùng mọi nơi chỉ vì dễ hiểu.

### 15.3. Secondary reads

Sau khi booking được confirm ở primary, một secondary có thể chưa replicate write đó. Vì vậy một GET ngay sau POST/PATCH có thể thấy trạng thái cũ nếu app đọc secondary mà không có consistency policy phù hợp.

### 15.4. Aggregation summary có độ trễ riêng

Một materialized daily count được cập nhật mỗi năm phút là **eventually consistent view** theo policy, dù source booking được majority committed. Không nên mô tả dashboard count là real-time nếu pipeline/consumer có lag.

### 15.5. Mỗi API nên có lời hứa consistency

| API | Kỳ vọng ví dụ | Hướng thiết kế |
| --- | --- | --- |
| Confirm booking | Kết quả transition phải đúng | Atomic condition/transaction |
| Read booking ngay sau confirm | Read-your-writes | Session/primary/read concern policy |
| Search listings | Có thể chấp nhận cập nhật chậm rất ngắn | Index + appropriate read preference |
| Analytics dashboard | Chấp nhận lag 5 phút | Materialized summaries và freshness timestamp |
| Financial export | Snapshot có thể kiểm toán | Read concern/snapshot job/reconciliation |

Không gán một cấu hình readConcern/writeConcern cho mọi API mà không biết business requirement.

## 16. Keyset pagination liên hệ với index và topology

### 16.1. Offset pagination

~~~javascript
db.listings_469.find({
  tenantId: "tenant-001",
  status: "PUBLISHED"
}).sort({ createdAt: -1, _id: -1 })
  .skip(100000).limit(20);
~~~

Skip sâu có thể tốn công duyệt keys/records. Khi có insert/delete ở đầu danh sách giữa các requests, offsets dịch và có thể dẫn đến duplicate/missing items.

### 16.2. Keyset với tuple

Sort:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

Sau last returned tuple (lastAt,lastId), điều kiện:

~~~javascript
{
  $or: [
    { createdAt: { $lt: lastAt } },
    {
      createdAt: lastAt,
      _id: { $lt: lastId }
    }
  ]
}
~~~

Đây là logic cho **DESC/DESC** với cùng BSON types. Nếu sort direction đổi, phép so sánh phải đổi.

### 16.3. Vì sao pageSize+1?

Truy vấn tối đa **pageSize+1** documents:

- Trả **pageSize** records đầu.
- Nếu còn một record thừa, hasNext=true.
- Cursor mới lấy từ **record cuối đã trả**, không từ record thừa.

Đây là phần quan trọng để không bỏ sót record ngay sau page boundary.

### 16.4. Index cho keyset

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
~~~

Nếu query còn cityCode equality thường xuyên, index với cityCode có thể cần thiết. Khi sharding, chỉ có index tốt không đủ nếu cursor query thiếu shard key và phải merge kết quả nhiều shards.

### 16.5. Stable order không phải snapshot

Keyset với immutable createdAt và unique _id giúp thứ tự xác định. Nhưng giữa hai HTTP requests:

- Document bị xóa sẽ không xuất hiện.
- DRAFT mới được publish phía sau cursor có thể xuất hiện.
- Backdated insert có thể xuất hiện.
- Nếu sort key mutable, record có thể chuyển vị trí.

**Keyset không tự đóng băng dataset.** Nếu cần export snapshot cố định, phải thiết kế snapshot-consistent job/operation với giới hạn read history và topology phù hợp.

### 16.6. Cursor là security boundary

Một opaque cursor nên chứa/bind:

- Tuple theo đúng BSON type.
- Sort specification.
- Tenant từ authenticated principal.
- Filter fingerprint.
- Page-size policy.
- Expiry/token schema version.
- Integrity protection như HMAC.

Base64 đơn thuần không chống sửa token. Dù token được ký, backend **vẫn phải enforce tenant filter**.

## 17. Change Streams, downstream views và topology

MongoDB Change Streams có thể phát sự kiện khi source documents thay đổi trên deployment được hỗ trợ (thường replica set/sharded cluster).

~~~text
Booking write -> MongoDB
                     |
                Change Stream
                     |
              Event consumer
                     |
         Search index / summary / cache
~~~

### 17.1. Khi nào cần?

Nếu search index hay dashboard phải phản ánh thay đổi bookings/listings, một consumer có thể nghe change events và cập nhật read model. Nhưng:

- Consumer có thể đọc lại events/retry.
- Cần idempotency.
- Resume token/retention/lag cần giám sát.
- Không mặc định exactly-once end-to-end.
- Schema evolution ảnh hưởng event payload/consumer.

### 17.2. Outbox pattern

Nếu một business event phải gắn với DB state transition, có thể dùng outbox document ghi trong cùng transaction phù hợp, rồi consumer phát ra broker. Điều này giảm một số dạng **dual write** thất bại giữa MongoDB và external messaging, nhưng tăng complexity và phải có idempotent consumers.

### 17.3. Read model có cùng shard key không?

Một summary collection có thể có shard key khác source collection vì access pattern khác. Quyết định cần xét:

- Cách ghi summary phân phối.
- Cách đọc dashboard filter/target shards.
- Có cần cross-shard transaction không.
- Tenant isolation và retention.

Không copy shard key source sang mọi derived collection theo quán tính.

## 18. Ma trận lựa chọn liên tầng

| Workload | Document model | Index trọng tâm | Aggregation | Topology/consistency |
| --- | --- | --- | --- | --- |
| Detail listing + rooms | Embed bounded rooms | _id, tenant scope nếu cần | Ít hoặc không | Primary/read policy phù hợp |
| Search PUBLISHED mới nhất | Listing root document | tenant/status/city/time/_id | $match/$sort/$limit | Target shard key nếu sharded |
| Ghi VIEW tần suất cao | Event riêng | tenant/listing/time | Không trên write path | Đánh giá write distribution |
| Top listing views/ngày | Raw events hoặc summary | tenant/type/time/listing | $group/$sort | Batch/read replicas/shard merge |
| Booking workflow | Booking riêng, revision | tenant/listing/status/time | Thống kê riêng | Atomic transitions/transaction khi cần |
| Rooms inventory đổi liên tục | Có thể tách rooms | listingId/roomId | Lookup nếu cần | Co-location vs independent writes |
| Admin export lớn | Cursor/batch | Filter/order keys | Projection/group theo nhu cầu | Snapshot/read concern/async job |
| Retention view events | Time-based events | TTL index nếu hợp lệ | Pre-archive summary | Disk/backup/legal policy |

Ma trận là điểm khởi đầu. Một quyết định phải được kiểm chứng với số liệu kích thước, query frequency, hot keys và SLO thực tế.

## 19. Kịch bản A: tìm kiếm hàng triệu listings

**Yêu cầu:** Tenant quản lý hàng triệu listings; user lọc PUBLISHED, cityCode=HCM, lấy 20 tin mới nhất.

### 19.1. Document

Listing root chứa những thông tin cần cho list card: title, cityCode, price, status, createdAt, thumbnailRef. Rooms có thể được nhúng nhưng **list API chỉ project fields cần**.

### 19.2. Index

Ứng viên:

~~~javascript
{
  tenantId: 1,
  status: 1,
  cityCode: 1,
  createdAt: -1,
  _id: -1
}
~~~

### 19.3. Query

~~~javascript
db.listings_469.find({
  tenantId: "tenant-001",
  status: "PUBLISHED",
  cityCode: "HCM"
}, {
  _id: 1, title: 1, cityCode: 1,
  monthlyRentVnd: 1, createdAt: 1
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

### 19.4. Topology

Nếu dữ liệu nằm trong một replica set đủ tải, chưa cần sharding. Nếu sharded, đánh giá shard key có giúp filter tenant target shard(s) không. Scatter-gather trên nhiều shards có thể tăng p99 ngay cả khi mỗi shard có index.

### 19.5. Kiểm chứng

- Explain first/next page.
- p95/p99 theo tenant size.
- Index bytes và write overhead.
- Pagination consistency khi inserts/deletes.
- Tenant isolation và response projection.

## 20. Kịch bản B: analytics VIEW tăng 100 triệu events/ngày

**Yêu cầu:** Ghi lượt xem rất nhiều; dashboard cần số views theo listing mỗi ngày.

### 20.1. Document

Không nhúng 100 triệu events vào listings. Lưu event riêng với tenant/listing/time/type và những snapshot fields thực sự cần. Nếu workload time series phù hợp, đánh giá **time-series collection** theo server version/ràng buộc, không mặc định mọi event log đều phải time series.

### 20.2. Index

Candidate:

~~~javascript
{ tenantId: 1, eventType: 1, createdAt: -1, listingId: 1 }
~~~

cho các báo cáo lọc tenant/type/time. Một workload đọc theo listingId/time có thể cần index khác. Append-heavy workload nhạy với write amplification nên mỗi index phải có lý do.

### 20.3. Aggregation

Group by listingId/day, không $push toàn bộ events. Có thể dùng $dateTrunc theo UTC hoặc timezone nghiệp vụ.

### 20.4. Summary

Nếu dashboard query liên tục, duy trì daily summary:

~~~text
Raw events -> scheduled/stream group -> daily_view_summary
~~~

Late events và duplicates phải có handling/reconciliation; summary có freshness SLA.

### 20.5. Topology

Khi write throughput vượt khả năng shard/replica set, đánh giá sharding dựa trên distribution theo tenant/listing/time. Shard key chỉ có monotonically increasing timestamp dễ dẫn tới hot range. Hashed hoặc compound key có trade-offs với range analytics; benchmark theo real workload.

## 21. Kịch bản C: booking và invariant nhiều documents

**Yêu cầu:** Một slot xem nhà không được đặt trùng theo policy; mỗi booking có trạng thái REQUESTED/CONFIRMED/CANCELLED.

### 21.1. Document

Booking có lifecycle riêng, nên tách collection là hợp lý:

~~~javascript
{
  _id: "b469-001-01",
  tenantId: "tenant-001",
  listingId: "l469-001-01",
  requestedAt: ISODate("2026-01-15T10:00:00Z"),
  status: "REQUESTED",
  revision: NumberLong("1")
}
~~~

### 21.2. Index

Query booking của listing:

~~~javascript
{ tenantId: 1, listingId: 1, requestedAt: -1 }
~~~

Nếu có unique booking key, thiết kế index riêng đúng business rule, tenant scope và sharding constraints.

### 21.3. Concurrency

Một updateOne với filter **_id + tenantId + status + revision** có thể thực hiện atomic state transition trong một document. Nếu invariant trải qua listing availability và booking insert, cân nhắc transaction hoặc thiết kế reservation token trong cùng document theo workload.

### 21.4. Read concern/preference

Ngay sau confirm, UI cần hiển thị trạng thái mới theo consistency contract. Không tự route GET tới lagging secondary rồi xem đó là lỗi mapping/index.

### 21.5. Analytics

Booking dashboard theo tháng có thể chấp nhận summary lag khác với transaction workflow. Không trộn hai loại consistency requirements.

## 22. Kịch bản D: tenant nhỏ và tenant cực lớn

**Yêu cầu:** 10.000 tenants nhỏ, một tenant enterprise có 40% traffic.

### 22.1. Document

TenantId phải luôn có và được xác thực. Collections có thể chứa multi-tenant documents nếu isolation/retention/access policy hỗ trợ.

### 22.2. Index

Compound index bắt đầu tenantId hỗ trợ common scoped queries. Nhưng index không tự tách traffic của hot tenant.

### 22.3. Topology

Shard key chỉ **tenantId** có thể phân bố 10.000 tenants nhưng toàn traffic tenant lớn vẫn concentrated. Hashed tenantId không tự chia một key thành nhiều shards. Có thể đánh giá compound key/hot tenant placement/zone strategies tùy workload.

### 22.4. Analytics

Một query group by tenant trên tất cả events có thể phát sinh merge/sort, đặc biệt khi data phân bố nhiều shards. Nên có quotas/async jobs cho enterprise reports lớn.

### 22.5. Capacity

Không chỉ đo data bytes per shard, mà còn **read/write ops per tenant, p99 latency, working set và IOPS**.

## 23. Lab an toàn: ba collections, cùng một câu chuyện

### 23.1. Phạm vi

Database chỉ dành cho thực hành:

~~~text
mongo_system_map_lab_469
  listings_469       24 listings / 3 tenants
  view_events_469    240 synthetic events
  bookings_469       12 booking requests
~~~

Mỗi document có **labTag:"system469-v1"**. Seed có thể chạy lại để **reset đúng bộ fixtures có _id tương ứng**, không drop DB/collections. Nếu các IDs trùng document lạ không có labTag, lệnh upsert có thể lỗi duplicate key thay vì ghi đè.

### 23.2. Seed mongosh

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_system_map_lab_469");
  const listings = lab.getCollection("listings_469");
  const events = lab.getCollection("view_events_469");
  const bookings = lab.getCollection("bookings_469");
  const tag = "system469-v1";
  const listingOps = [];
  const eventOps = [];
  const bookingOps = [];

  for (let tenantNo = 1; tenantNo <= 3; tenantNo++) {
    const t = String(tenantNo).padStart(3, "0");
    const tenantId = "tenant-" + t;

    for (let i = 1; i <= 8; i++) {
      const j = String(i).padStart(2, "0");
      const id = "l469-" + t + "-" + j;
      const cityCode = ["HCM", "HN", "DN"][
        (tenantNo + i) % 3
      ];
      const createdAt = new Date(Date.UTC(
        2026, 0, 15, 8 + Math.floor((i - 1) / 2), 0, 0
      ));
      const doc = {
        _id: id,
        labTag: tag,
        tenantId,
        title: "Listing " + t + "-" + j,
        cityCode,
        status: i % 3 === 0 ? "DRAFT" : "PUBLISHED",
        monthlyRentVnd: NumberDecimal(
          String(7000000 + tenantNo * 1000000 + i * 250000)
          + ".00"
        ),
        rooms: [
          {
            roomId: "bed-1",
            type: "BEDROOM",
            areaSqm: 15 + i,
            amenities: ["WIFI"]
          },
          {
            roomId: "kitchen-1",
            type: "KITCHEN",
            areaSqm: 8,
            amenities: ["STOVE"]
          }
        ],
        tags: ["FURNISHED", cityCode],
        createdAt,
        updatedAt: createdAt,
        revision: NumberLong("1")
      };
      listingOps.push({
        replaceOne: {
          filter: { _id: id, labTag: tag },
          replacement: doc,
          upsert: true
        }
      });
    }

    for (let k = 1; k <= 4; k++) {
      const id = "b469-" + t + "-" + String(k).padStart(2, "0");
      const listingId = "l469-" + t + "-"
        + String(k).padStart(2, "0");
      bookingOps.push({
        replaceOne: {
          filter: { _id: id, labTag: tag },
          replacement: {
            _id: id,
            labTag: tag,
            tenantId,
            listingId,
            requestKey: "request-" + t + "-" + k,
            requestedAt: new Date(Date.UTC(2026, 0, 15, 9, k, 0)),
            status: k % 2 === 0 ? "CONFIRMED" : "REQUESTED",
            revision: NumberLong("1")
          },
          upsert: true
        }
      });
    }
  }

  const base = Date.UTC(2026, 0, 15, 0, 0, 0);
  for (let i = 0; i < 240; i++) {
    const tenantNo = 1 + (i % 3);
    const t = String(tenantNo).padStart(3, "0");
    const listingNo = 1 + (Math.floor(i / 3) % 8);
    const listingId = "l469-" + t + "-"
      + String(listingNo).padStart(2, "0");
    const id = "e469-" + String(i).padStart(4, "0");
    const doc = {
      _id: id,
      labTag: tag,
      tenantId: "tenant-" + t,
      listingId,
      eventType: i % 5 === 0 ? "CONTACT" : "VIEW",
      createdAt: new Date(base + i * 180000),
      durationMs: 200 + (i % 12000)
    };
    eventOps.push({
      replaceOne: {
        filter: { _id: id, labTag: tag },
        replacement: doc,
        upsert: true
      }
    });
  }

  listings.bulkWrite(listingOps, { ordered: false });
  events.bulkWrite(eventOps, { ordered: false });
  bookings.bulkWrite(bookingOps, { ordered: false });

  printjson({
    listings: listings.countDocuments({ labTag: tag }),
    events: events.countDocuments({ labTag: tag }),
    bookings: bookings.countDocuments({ labTag: tag })
  });
})();
~~~

Kỳ vọng khi lab sạch: **listings:24, events:240, bookings:12**; mỗi tenant có **8 listings, 80 events, 4 bookings**. Hai listings liên tiếp trong một tenant chia sẻ createdAt để kiểm tra sort tie-breaker.

Với events, **240 records là 240 events đủ loại**, không phải 240 VIEW; i chia hết cho 5 là CONTACT. Khi đếm views phải filter eventType:"VIEW".

## 24. Lab document + CRUD: đọc một listing, sửa một room

### 24.1. Đọc theo tenant và ID

~~~javascript
const lab = db.getSiblingDB("mongo_system_map_lab_469");
const listings = lab.getCollection("listings_469");

printjson(listings.findOne({
  _id: "l469-001-01",
  labTag: "system469-v1",
  tenantId: "tenant-001"
}));
~~~

Đối với API thật, tenantId phải đến từ authenticated principal, không tin header tự khai báo.

### 24.2. Cập nhật room với arrayFilters

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l469-001-01",
    labTag: "system469-v1",
    tenantId: "tenant-001",
    revision: NumberLong("1")
  },
  {
    $set: {
      "rooms.$[room].areaSqm": 21
    },
    $inc: {
      revision: NumberLong("1")
    },
    $currentDate: {
      updatedAt: true
    }
  },
  {
    arrayFilters: [
      { "room.roomId": "bed-1" }
    ]
  }
));
~~~

Lần đầu sau seed có thể matchedCount=1. Lần hai filter revision=1 sẽ không match. Đây là **optimistic concurrency** ở single-document level.

Nếu các phần tử rooms có roomId trùng, arrayFilters có thể match nhiều phần tử; roomId uniqueness là invariant ứng dụng cần kiểm riêng.

### 24.3. Đọc lại các rooms

~~~javascript
printjson(listings.findOne({
  _id: "l469-001-01",
  labTag: "system469-v1",
  tenantId: "tenant-001"
}, {
  _id: 1,
  rooms: 1,
  revision: 1,
  updatedAt: 1
}));
~~~

Kiểm bedroom area đổi, kitchen area không đổi. Đây là minh họa quan hệ giữa **document modeling** (rooms embed) và **atomic array update**.

## 25. Lab index + query: search listings

### 25.1. Định nghĩa index ứng viên

~~~javascript
listings.createIndex(
  {
    labTag: 1,
    tenantId: 1,
    status: 1,
    cityCode: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "ix469_tag_tenant_status_city_time_id"
  }
);

listings.createIndex(
  {
    labTag: 1,
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "ix469_tag_tenant_status_time_id"
  }
);
~~~

Hai indexes mô phỏng **hai query families**: một có city equality, một không có city. Với production, phải đo tần suất và chi phí trước khi giữ cả hai.

### 25.2. Filter city và sort

~~~javascript
const cityQuery = {
  labTag: "system469-v1",
  tenantId: "tenant-001",
  status: "PUBLISHED",
  cityCode: "HCM"
};

printjson(listings.find(cityQuery, {
  _id: 1,
  title: 1,
  createdAt: 1,
  monthlyRentVnd: 1
}).sort({
  createdAt: -1,
  _id: -1
}).limit(5).toArray());
~~~

### 25.3. Explain

~~~javascript
printjson(
  listings.find(cityQuery)
    .sort({ createdAt: -1, _id: -1 })
    .limit(5)
    .explain("executionStats")
);
~~~

Trong lab chỉ có 24 documents, optimizer có thể chọn plan khác index mong đợi vì COLLSCAN rẻ hơn. Điều quan trọng là biết đọc explain, không ép một kết quả cố định trên dữ liệu quá nhỏ.

### 25.4. Query không có city

~~~javascript
printjson(
  listings.find({
    labTag: "system469-v1",
    tenantId: "tenant-001",
    status: "PUBLISHED"
  }).sort({
    createdAt: -1,
    _id: -1
  }).limit(5).explain("executionStats")
);
~~~

So sánh index candidates và xem field **cityCode** có làm thay đổi việc hỗ trợ sort khi bị bỏ khỏi equality filter không.

## 26. Lab pagination: dùng tuple thay offset

~~~javascript
function page469(
    listings,
    tenantId,
    pageSize,
    after = null) {
  if (!/^tenant-[0-9]{3}$/.test(tenantId)) {
    throw new Error("Invalid tenantId");
  }
  if (!Number.isInteger(pageSize)
      || pageSize < 1 || pageSize > 10) {
    throw new Error("pageSize must be 1..10");
  }

  const base = {
    labTag: "system469-v1",
    tenantId,
    status: "PUBLISHED"
  };

  let query = base;
  if (after !== null) {
    if (!(after.createdAt instanceof Date)
        || Number.isNaN(after.createdAt.getTime())
        || typeof after.id !== "string"
        || after.id.length === 0) {
      throw new Error("Invalid cursor");
    }
    query = {
      $and: [
        base,
        {
          $or: [
            { createdAt: { $lt: after.createdAt } },
            {
              createdAt: after.createdAt,
              _id: { $lt: after.id }
            }
          ]
        }
      ]
    };
  }

  const rows = listings.find(query, {
    _id: 1, title: 1, tenantId: 1, createdAt: 1
  }).sort({
    createdAt: -1,
    _id: -1
  }).limit(pageSize + 1).toArray();

  const hasNext = rows.length > pageSize;
  const items = rows.slice(0, pageSize);
  const last = items[items.length - 1];
  return {
    items,
    hasNext,
    nextAfter: hasNext && last
      ? { createdAt: last.createdAt, id: last._id }
      : null
  };
}

const p1 = page469(listings, "tenant-001", 2);
printjson(p1);
if (p1.nextAfter) {
  const p2 = page469(
    listings, "tenant-001", 2, p1.nextAfter
  );
  printjson(p2);
  if (p2.nextAfter) {
    printjson(page469(
      listings, "tenant-001", 2, p2.nextAfter
    ));
  }
}
~~~

Sau seed, tenant-001 có **6 PUBLISHED listings**, nên ba pages size=2 sẽ trả sáu IDs nếu dataset chưa bị đổi status. Lab mô phỏng API pagination, không triển khai signed cursor. Production phải ký token/bind auth/filter và giới hạn page size.

### 26.1. Liên hệ topology

Nếu listings được sharding theo field không xuất hiện trong filter, cùng một keyset query có thể là scatter-gather. Index giúp từng shard xử lý tốt nhưng toàn request vẫn phải merge và chờ các shards. Đó là ví dụ **index đúng nhưng topology routing chưa chắc đúng**.

## 27. Lab aggregation: đếm VIEW theo listing

### 27.1. Index sự kiện

~~~javascript
const events = lab.getCollection("view_events_469");

events.createIndex(
  {
    labTag: 1,
    tenantId: 1,
    eventType: 1,
    createdAt: -1,
    listingId: 1
  },
  {
    name: "ix469_tag_tenant_type_date_listing"
  }
);

events.createIndex(
  {
    labTag: 1,
    tenantId: 1,
    listingId: 1,
    createdAt: -1
  },
  {
    name: "ix469_tag_tenant_listing_date"
  }
);
~~~

Index đầu cho báo cáo lọc tenant/type/date, index thứ hai cho truy vấn lịch sử một listing. Ở production append-heavy cần đo write amplification trước khi giữ cả hai.

### 27.2. Pipeline chính xác

~~~javascript
const report = [
  {
    $match: {
      labTag: "system469-v1",
      tenantId: "tenant-001",
      eventType: "VIEW",
      createdAt: {
        $gte: ISODate("2026-01-15T00:00:00Z"),
        $lt: ISODate("2026-01-16T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$listingId",
      views: { $sum: 1 },
      latestAt: { $max: "$createdAt" }
    }
  },
  { $sort: { views: -1, _id: 1 } },
  { $limit: 10 }
];

printjson(events.aggregate(report, {
  allowDiskUse: true,
  maxTimeMS: 15000,
  comment: "system469-top-views"
}).toArray());
~~~

Trong seed, mỗi tenant có **80 events** rải theo 8 listings, và mỗi event thứ năm toàn cục là CONTACT. Báo cáo đếm chỉ VIEW, không cộng CONTACT.

### 27.3. Explain aggregation

~~~javascript
printjson(
  events.explain("executionStats")
    .aggregate(report, { allowDiskUse: true })
);
~~~

Quan sát input matching, scan/index, group/sort state, output. allowDiskUse:true **không chứng minh query đã spill**, nhất là với dataset nhỏ.

### 27.4. Vì sao cần $match trước $group?

Nếu $group tất cả tenants rồi mới filter tenant, server có thể phải tích lũy trên tập dữ liệu lớn hơn, đồng thời query có thể mất cơ hội dùng index tốt. Optimizer có thể reorder một số predicates, nhưng cách viết rõ ràng từ access pattern vẫn có lợi.

## 28. Lab aggregation + $lookup: ghép kết quả thống kê với listing

**Mục tiêu:** top views theo listing cùng title và cityCode, không lấy mọi event documents.

~~~javascript
const enrichedReport = [
  {
    $match: {
      labTag: "system469-v1",
      tenantId: "tenant-001",
      eventType: "VIEW",
      createdAt: {
        $gte: ISODate("2026-01-15T00:00:00Z"),
        $lt: ISODate("2026-01-16T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        listingId: "$listingId"
      },
      views: { $sum: 1 }
    }
  },
  { $sort: { views: -1, "_id.listingId": 1 } },
  { $limit: 10 },
  {
    $lookup: {
      from: "listings_469",
      let: {
        listingKey: "$_id.listingId",
        tenantKey: "$_id.tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$listingKey"] },
                { $eq: ["$tenantId", "$$tenantKey"] }
              ]
            }
          }
        },
        {
          $project: {
            title: 1,
            cityCode: 1,
            status: 1
          }
        }
      ],
      as: "listing"
    }
  },
  {
    $project: {
      _id: 0,
      tenantId: "$_id.tenantId",
      listingId: "$_id.listingId",
      views: 1,
      listing: { $first: "$listing" }
    }
  }
];

printjson(events.aggregate(enrichedReport, {
  maxTimeMS: 15000,
  allowDiskUse: true
}).toArray());
~~~

### 28.1. Tại sao group rồi mới lookup?

Nếu lookup title cho từng raw event, có thể thực hiện nhiều joins/repeated work. Khi group trước thành 8 listings, join chỉ cần phục vụ một số groups đã chọn. **Đổi thứ tự này chỉ đúng khi title/city là thuộc tính hiện tại của listing và báo cáo không yêu cầu snapshot metadata tại thời điểm từng event.**

### 28.2. Tenant guard trong lookup

Pipeline $lookup ràng buộc cả **listingId và tenantId**. Dù lab _id có vẻ chứa tenant, không nên lấy pattern ID làm chứng cứ authorization. Security boundary vẫn cần kiểm trong ứng dụng API trước khi chạy report.

### 28.3. Nếu listing đã bị xóa?

Khi không còn foreign match, listing trở thành null/missing theo projection semantics. Business phải quyết định:

- Vẫn trả view count với title “Listing không còn tồn tại”.
- Lưu snapshot title trong event.
- Bỏ row (nếu report định nghĩa như vậy).

Không âm thầm bỏ dữ liệu thống kê vì join không còn kết quả nếu report cần completeness.

## 29. Lab booking: index, idempotency và atomic state transition

### 29.1. Index

~~~javascript
const bookings = lab.getCollection("bookings_469");

bookings.createIndex(
  {
    labTag: 1,
    tenantId: 1,
    listingId: 1,
    requestedAt: -1
  },
  {
    name: "ix469_tag_tenant_listing_requested"
  }
);

bookings.createIndex(
  { tenantId: 1, requestKey: 1 },
  {
    unique: true,
    name: "uq469_tenant_request_key"
  }
);
~~~

Lưu ý: lab seed có requestKey cho mọi booking. Trên production legacy collection có missing keys, cần rà soát duplicates/null/partial index trước khi build unique index.

### 29.2. Read bookings của một listing

~~~javascript
printjson(bookings.find({
  labTag: "system469-v1",
  tenantId: "tenant-001",
  listingId: "l469-001-01"
}).sort({ requestedAt: -1 }).toArray());
~~~

### 29.3. Confirm khi REQUESTED và revision=1

~~~javascript
printjson(bookings.updateOne(
  {
    _id: "b469-001-01",
    labTag: "system469-v1",
    tenantId: "tenant-001",
    status: "REQUESTED",
    revision: NumberLong("1")
  },
  {
    $set: { status: "CONFIRMED" },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  }
));
~~~

Lần đầu sau seed có thể match, lần hai không vì status/revision thay đổi. Đây là ví dụ **atomic state transition** trên một booking document. Nó chưa chứng minh invariant về availability trên một listing khác, vốn có thể cần transaction hoặc giải pháp đồng bộ riêng.

### 29.4. Unique constraint là index + topology concern

Nếu booking collection sau này sharded, phải kiểm tra khả năng enforce unique (tenantId, requestKey) theo shard key. Đây là ví dụ **business requirement ảnh hưởng cả index và shard key**, không chỉ Java validation.

## 30. Lab: tự xem thông số collection/index

Các lệnh quan sát trong môi trường lab:

~~~javascript
printjson(listings.getIndexes());
printjson(events.getIndexes());
printjson(bookings.getIndexes());

printjson(lab.runCommand({
  collStats: "listings_469"
}));

printjson(lab.runCommand({
  collStats: "view_events_469"
}));
~~~

Các metrics có thể khác theo MongoDB version, FCV và quyền. Không cần chạy serverStatus hoặc thao tác cluster admin để hoàn thành lab; những lệnh đó có thể không được cấp trên managed services.

### 30.1. Đọc chỉ số thay vì đoán

- Collection size và average object size.
- Number/index sizes.
- Document count theo tenant.
- Query scans vs returned.
- Update frequency và write amplification.
- Working set/cache pressure ở môi trường đại diện.

Với 276 synthetic documents, **không suy ra performance ở 100 triệu documents**. Lab chứng minh semantics và cách quan sát, không thay load test.

## 31. Index maintenance và schema evolution

### 31.1. Đổi field path là đổi query và index

Giả sử v1 lưu:

~~~javascript
{ cityCode: "HCM" }
~~~

v2 lưu:

~~~javascript
{ address: { cityCode: "HCM" } }
~~~

Nếu collection còn v1/v2, query:

~~~javascript
{ "address.cityCode": "HCM" }
~~~

bỏ sót v1. Query may need **$or** trên hai paths hoặc migrate/backfill một canonical field. Indexes có thể cần hỗ trợ cả hai trong quá trình chuyển tiếp.

### 31.2. Expand–migrate–contract

~~~text
1. Expand reader hỗ trợ old+new
2. Rollout tới toàn bộ readers
3. Switch writer sang schema mới
4. Backfill dữ liệu cũ, có CAS/checkpoint
5. Verify all data và rollback policy
6. Drop legacy query/index support khi an toàn
~~~

Không bật writer mới ngay khi vẫn có old readers không hiểu new BSON shape trong rolling deployment.

### 31.3. Index cleanup

Sau khi schema cũ không còn, legacy indexes có thể trở thành gánh nặng write/disk. Trước khi drop:

- Kiểm query usage.
- Kiểm data version distribution.
- Kiểm backup/restore compatibility.
- Đo explain sau dự kiến index removal.
- Có change window/rollback plan.

### 31.4. Shard key migration khó hơn đổi field thường

Nếu field đang làm shard key đổi tên/kiểu, ảnh hưởng routing và data placement. Không coi việc dùng $rename trên documents là đủ để tự đổi shard key/topology. Phải lập kế hoạch theo MongoDB server version và sharding procedures.

## 32. Chọn mô hình theo đặc tính tăng trưởng

| Dữ liệu | Mức tăng trưởng | Mô hình đề xuất khởi điểm | Vì sao |
| --- | --- | --- | --- |
| Listing title, city, rent | Vài fields/document | Root listing fields | Đọc/sửa cùng nhau |
| 2–10 rooms/listing | Bounded | Embedded array | Detail read và atomic update |
| Hàng nghìn rooms/listing, thay đổi liên tục | Lớn/độc lập | Room collection | Tránh document growth/contention |
| Views liên tục | Unbounded append | Events collection | Write throughput và retention |
| Daily view count | Số bucket hữu hạn | Summary collection | Dashboard read nhanh |
| Booking workflow | Independent lifecycle | Booking collection | Index, trạng thái, quyền riêng |
| User comments hàng triệu | Unbounded | Comments collection | Pagination/retention độc lập |
| Một số tags cố định | Bounded | Array trong listing | Không cần join |

Đây chỉ là candidate patterns. Cần đo dữ liệu thực và kiểm tra access patterns trước khi quyết định.

## 33. Quy trình tối ưu khi một truy vấn chậm

### 33.1. Đừng nhảy thẳng tới sharding

~~~text
Query chậm
   |
   v
Đúng business result và tenant scope?
   |
   v
Explain có COLLSCAN/SORT nhiều?
   |
   +-- Có -> Xem index/filter/sort/order
   |
   v
Aggregation state quá lớn?
   |
   +-- Có -> Group cardinality, $push, lookup fan-out
   |
   v
Document shape quá lớn / join nhiều?
   |
   +-- Có -> Embed/reference/projection redesign
   |
   v
Read/write contention, disk, cache, CPU?
   |
   +-- Có -> Concurrency budget, scaling, retention
   |
   v
Data/traffic vượt replica set?
   |
   +-- Có -> Đánh giá shard key và routing
~~~

### 33.2. Đầu tiên xác nhận query đúng

Một query nhanh hơn 10 lần vì đặt $limit trước $group và bỏ 90% dữ liệu là **sai**. Luôn có correctness tests/expected outputs trước và sau optimization.

### 33.3. Kiểm tra index

- Filter fields và sort direction.
- Equality/range selective.
- Index prefixes và collation.
- Multikey behavior.
- Covered query có đáng đánh đổi write cost không.
- Index size/usage.

### 33.4. Kiểm tra aggregation

- Blocking stages.
- Memory/spill.
- Group key cardinality.
- $push/$addToSet size.
- $lookup fan-out.
- $unwind multiply.
- $facet output bounds.

### 33.5. Kiểm tra topology

- Query có shard key target không.
- Một shard/tenant có nóng bất thường không.
- Merge stage tốn gì.
- Secondary lag/read preference.
- Replica set elections và retry.
- Disk/data distribution và backups.

### 33.6. Kiểm tra application

- Connection pool saturation.
- Cursor batch sizes và materialization.
- HTTP/request timeouts.
- N+1 queries từ application.
- Cache invalidation.
- Unbounded pagination/export.

## 34. Dấu hiệu sự cố và tầng cần xem

| Triệu chứng | Khả năng gốc | Tầng ưu tiên điều tra |
| --- | --- | --- |
| Detail listing cần 12 database calls | Model tách quá nhiều, N+1 | Document/query |
| List API quét hàng triệu docs | Thiếu index/filter | Index |
| Sort mất rất lâu | Blocking SORT | Index/aggregation |
| Group báo memory limit | Cardinality/accumulator | Aggregation |
| $push array lớn hơn BSON limit | Unbounded embedding/output | Document/aggregation |
| $lookup chậm | Join fan-out/foreign index | Document/index/aggregation |
| CRUD writes chậm sau thêm indexes | Write amplification | Index |
| Writes tập trung vào một node | Replica-set primary limit hoặc shard hot key | Topology |
| Sharded query chậm dù IXSCAN | Scatter-gather/merge | Topology/query |
| Đọc secondary thấy giá cũ | Replication lag/read preference | Topology/consistency |
| Booking cập nhật mất dữ liệu | Lost update/revision guard thiếu | Document/transaction |
| Unique key không được enforce trên sharded data | Index/shard key constraints | Index/topology |
| Dashboard count chậm 2 phút | Recompute raw events quá thường | Aggregation/summary |
| Dashboard count trễ 5 phút | Async summary freshness | Pipeline/consistency |
| Pagination trùng IDs | Offset shifts hoặc mutable sort | Query/index/data model |
| Tenant A thấy data Tenant B | Thiếu authorization predicate | Security/query |
| Server đầy disk | Data/index/spill/retention | Index/aggregation/topology |
| TTL chưa xóa ngay | Asynchronous TTL behavior | Data lifecycle |
| Restore rồi reader lỗi | Schema evolution incompatible | Document/application |

## 35. Observability: đo cả bốn tầng

### 35.1. Document metrics

- Document count, size distribution.
- Embedded array lengths.
- Field missing/null/BSON types.
- Schema-version distribution.
- Growth/retention.
- Hot document contention.

### 35.2. Index metrics

- Index sizes/usage.
- KeysExamined vs DocsExamined vs nReturned.
- Index build duration.
- Write latency/index maintenance.
- Blocking sort presence.

### 35.3. Aggregation metrics

- Stage execution stats.
- Group cardinality, joined rows.
- Spill/usedDisk khi server expose.
- Query duration và returned data size.
- Materialized view lag/reconciliation.

### 35.4. Topology metrics

- Primary/secondary state và replication lag.
- Elections/failover events.
- Read/write ops per node/shard.
- Disk free/IOPS/cache pressure.
- Chunk/data/traffic skew.
- Targeted vs scatter-gather queries khi có telemetry.

### 35.5. SLO gắn endpoint

| API | Ví dụ SLO cần định nghĩa | Evidence |
| --- | --- | --- |
| GET listing detail | p99 latency và lỗi | APM + query explain |
| GET listing search | p95/p99 per filter/page | Cursor metrics + index plan |
| PATCH booking | Error/409 rate, write latency | Application logs + database metrics |
| Analytics dashboard | Latency + freshness | Batch/stream metrics + source reconciliation |
| Export | Completion time và completeness | Job metrics + snapshot policy |

Không đặt một con số p99 tùy ý làm “chuẩn MongoDB”; SLO phải phù hợp workload, hạ tầng và business need.

## 36. Testing matrix liên tầng

| Test | Document | Index | Aggregation | Topology |
| --- | --- | --- | --- | --- |
| Unit business rule | Validate schema/invariants | Không chứng minh index | Verify pure transforms | Mock lỗi theo policy |
| MongoDB integration | BSON type, atomic update | Index presence/unique | Pipeline results/edge cases | Single-node replica set có giới hạn |
| API E2E | Tenant isolation/DTO | Quan sát gián tiếp | Report JSON/correctness | Real service/data flow |
| Performance | Document size/working set | Query plan/load | Spill/group latency | CPU/IOPS/shard routing |
| Resilience | Retry/idempotency | Index rebuild/deployment | Long-running query behavior | Elections/partitions/failover |
| Migration rehearsal | Old/new schema | Index rollout | Mixed-version reports | Shard key implications |

### 36.1. Unit test không thay integration

Mock repository không chứng minh:

- BSON Decimal128 được lưu đúng.
- Multikey/arrayFilters semantics.
- Unique index server enforcement.
- Query plan dùng index.
- Transaction rollback.

### 36.2. Integration test không thay capacity test

Một test với 24 listings và 240 events có thể xác minh kết quả query, nhưng không chứng minh p99 với 50 triệu events và nhiều shards. Phải dùng dataset/traffic đại diện cho performance.

### 36.3. Single-node Testcontainers không thử full HA

MongoDBContainer được dựng để hỗ trợ nhiều integration scenarios và có thể dùng replica-set URI, nhưng **không chứng minh failover của replica set nhiều nodes**. Cần topology/resilience tests riêng khi ứng dụng có HA requirements.

## 37. Quy trình thiết kế tính năng mới

### Bước 1 — Viết truy vấn trước

Tạo bảng access patterns: fields filter/sort, read/write ratio, cardinalities, SLO.

### Bước 2 — Chọn document boundary

Xác định cái gì có thể nhúng, cái gì phát triển vô hạn, và invariant nào cần single-document atomicity.

### Bước 3 — Thiết kế indexes tối thiểu

Mỗi index phải gắn với một query family hoặc constraint. Tính write/disk cost và duy trì naming convention.

### Bước 4 — Tạo aggregation đúng ngữ nghĩa

Xác định group key, timezone, null/missing behavior, fan-out, output bound và consistency/freshness.

### Bước 5 — Chọn topology theo capacity

Bắt đầu với replica set khi đủ. Nếu sharding, đánh giá shard key và routing bằng data/traffic thực, không chỉ kích thước collection.

### Bước 6 — Thiết kế consistency và failure handling

Chọn read preference/concern, write concern, transactional boundary, idempotency/retries, backups và restore.

### Bước 7 — Benchmark, observe, iterate

EXPLAIN + test dữ liệu đại diện + p95/p99 + resource cost + security/tenant checks. Lưu decision record và rollback.

## 38. Bản đồ quyết định ngắn gọn

### Câu hỏi 1: Có nên embed?

**Có xu hướng embed** nếu related data nhỏ, bounded, đọc cùng nhau, cùng lifecycle và cần atomic update.  
**Có xu hướng reference** nếu unbounded, nhiều readers/writers độc lập, cần retention/index riêng hoặc quyền khác.

### Câu hỏi 2: Có nên thêm index?

Thêm khi nó giải quyết **query shape/constraint rõ ràng** với lợi ích read vượt chi phí write/storage. Kiểm explain và workload trước/sau. Không index mọi field.

### Câu hỏi 3: Aggregation chạy online hay materialize?

Online khi query nhẹ hoặc cần dữ liệu mới theo semantics. Materialize khi scan/group lớn lặp lại thường xuyên và business chấp nhận freshness lag cùng reconciliation.

### Câu hỏi 4: Dùng replica set hay sharding?

Replica set nếu data và throughput đáp ứng cùng HA requirement. Sharding khi cần scale-out dữ liệu/write/load với shard key hợp lý; đừng dùng nó để che query/index shape sai.

### Câu hỏi 5: Khi đọc secondary?

Khi nghiệp vụ chấp nhận khả năng lag và có consistency policy rõ. Critical read-after-write cần chọn session/read preference/concern phù hợp.

### Câu hỏi 6: Khi nào nên dùng transaction?

Khi invariant thực sự trải qua nhiều documents/collections và không thể mô hình hóa bằng một atomic single-document operation hoặc giải pháp khác hợp lý. Cân nhắc chi phí nhất là cross-shard.

### Câu hỏi 7: Có nên dùng $lookup?

Khi join frequency/size/index cho phép và query được tối ưu. Nếu lặp lại ở traffic lớn, cân nhắc denormalized snapshot/materialized read model, nhưng phải quản lý đồng bộ.

## 39. Bài tập tự luyện

### Bài 1 — Bốn tầng

Vẽ luồng request từ REST API đến document, index, aggregation và replica set/shards. Mỗi tầng quyết định điều gì?

### Bài 2 — Access patterns

Với chức năng tìm tin theo tenant, trạng thái, city và newest sort, lập bảng filter/sort/projection/cardinality/SLO.

### Bài 3 — Embedded rooms

Vì sao một listing có 2–5 rooms thường phù hợp embedding? Nếu một tòa nhà có 20.000 rooms và inventory updates liên tục thì sao?

### Bài 4 — Unbounded view events

Tại sao không lưu views[] vô hạn trong listing document? Liệt kê ít nhất bốn hậu quả.

### Bài 5 — Document atomicity

Một update sửa giá và status trong cùng listing có atomicity nào? Hai concurrent requests cùng đọc revision cũ được bảo vệ thế nào?

### Bài 6 — Decimal128

Giải thích vì sao monthlyRentVnd dùng Decimal128 thay vì Double. Kiểm BSON thực bằng integration test ra sao?

### Bài 7 — Multikey

Thiết kế query tìm listing có một BEDROOM areaSqm>=20. Vì sao $elemMatch quan trọng?

### Bài 8 — Unique roomId

Vì sao unique multikey index không tự đảm bảo roomId unique trong cùng một listing?

### Bài 9 — Compound index

Tạo index cho tenant/status/city equality và createdAt DESC, _id DESC sort. Giải thích thứ tự keys.

### Bài 10 — Bỏ city filter

Query không có cityCode nhưng index có cityCode trước createdAt. Điều gì có thể xảy ra với sort? Đề xuất index cho query phổ biến.

### Bài 11 — Explain

Đọc winningPlan, totalKeysExamined, totalDocsExamined, nReturned. Vì sao collection 24 docs có thể chọn COLLSCAN?

### Bài 12 — Partial index

Thiết kế partial index cho PUBLISHED. Query DRAFT có được phép sử dụng nó để trả đầy đủ kết quả không?

### Bài 13 — Unique booking

Lập unique constraint theo tenantId + requestKey. Khi sharding, cần kiểm điều kiện gì của shard key?

### Bài 14 — TTL

Vì sao TTL phù hợp một số event-retention policies nhưng không đảm bảo xóa đúng giây và không thay backup/legal review?

### Bài 15 — Aggregation top views

Viết $match tenant/type/time, $group listingId, $sort views, $limit top 10. Điều gì sai nếu limit đặt trước group?

### Bài 16 — Group cardinality

So group theo tenantId với group theo eventId; memory state thay đổi thế nào?

### Bài 17 — $push

Tại sao $group {$push:"$$ROOT"} trên hàng triệu events có nguy cơ giới hạn memory và 16 MiB BSON output?

### Bài 18 — $unwind

Một listing có ba rooms. Sau unwind, tính count documents kiểu gì để đếm rooms và kiểu gì để đếm listings?

### Bài 19 — $lookup

Khi nào group events trước $lookup listings tốt hơn lookup từng event? Nếu report cần cityCode tại thời điểm view, có vấn đề ngữ nghĩa nào?

### Bài 20 — $facet

Một facet trả một triệu rows và totals. Vì sao allowDiskUse không giải quyết output document limit?

### Bài 21 — Daily summary

Thiết kế summary viewCount per tenant/listing/day. Xử lý late events, duplicates và job retries.

### Bài 22 — Replica set

Giải thích primary, secondaries, election và replication lag. Thêm secondary có scale write throughput như sharding không?

### Bài 23 — Concerns

So w:1 với w:"majority" và local với majority read concern. Vì sao majority không thay thế backup?

### Bài 24 — Read-your-writes

Sau khi confirm booking, UI đọc secondary và nhận REQUESTED. Giải thích nguyên nhân và design consistency policy.

### Bài 25 — Sharding

Phân biệt mongos, config server replica set và shards. Vì sao một index đúng trên mỗi shard vẫn có thể dẫn tới scatter-gather?

### Bài 26 — Shard key

So shard key tenantId range, hashed tenantId và compound tenantId+listingId cho workload 10.000 tenants.

### Bài 27 — Hot tenant

Một tenant tạo 40% traffic. Hashed tenantId có tự phân phối traffic của tenant đó lên nhiều shards không? Vì sao?

### Bài 28 — Merge aggregation

Vẽ partial group trên hai shards và merge. Những khoản chi phí network/memory nào vẫn còn?

### Bài 29 — Pagination

Viết keyset predicate cho createdAt DESC, _id DESC và giải thích pageSize+1.

### Bài 30 — Snapshot

Giữa page 1 và page 2, một DRAFT được publish. Vì sao keyset không bảo đảm snapshot danh sách?

### Bài 31 — Lab seed

Chạy seed ba collections. Kiểm 24 listings, 240 events, 12 bookings và ba tenants.

### Bài 32 — Lab room update

Chạy arrayFilters cập nhật bed-1 và revision. Kiểm kitchen không đổi và lần chạy hai không match revision=1.

### Bài 33 — Lab indexes

Chạy hai query families (có/không city equality) và compare explain/index candidates.

### Bài 34 — Lab cursor

Lấy ba pages size=2 của PUBLISHED tenant-001. Assert IDs không trùng và sort tuple giảm dần.

### Bài 35 — Lab report

Chạy top VIEW report. Kiểm chỉ đếm VIEW không đếm CONTACT.

### Bài 36 — Lab join

Chạy enrichedReport; vì sao $lookup ràng buộc tenant và listing, và vì sao group trước join?

### Bài 37 — Lab booking

Chạy atomic REQUESTED→CONFIRMED với revision, rồi chạy lại. Giải thích matchedCount=0.

### Bài 38 — Schema migration

Đổi cityCode thành address.cityCode trên dữ liệu có nhiều phiên bản. Lập kế hoạch reader/query/index expand–migrate–contract.

### Bài 39 — Performance

Một query quét nhiều docs, sort memory, và hot shard. Lập trình tự điều tra từ query correctness qua explain tới topology.

### Bài 40 — Capacity planning

Ước lượng storage cho 100 triệu events/ngày trong 90 ngày: cần xem document size, index overhead, replication factor, compression và retention như thế nào? Không chỉ nhân số docs với payload size.

### Bài 41 — Observability

Thiết kế dashboard gồm BSON sizes, index sizes, query examined/returned, spill, replication lag, per-shard ops và API p99.

### Bài 42 — Security

Một listing _id có thể đoán được. Vì sao index, shard key và signed cursor đều không thay tenant authorization predicate?

### Bài 43 — Consistency

Tách consistency requirements cho booking confirmation, listing search, dashboard summary và financial export.

### Bài 44 — Rollback

Sau deploy v3 schema và index mới, rollback code về v2 có thể lỗi gì? Lập compatibility/backup/restore plan.

### Bài 45 — Tổng hợp kiến trúc

Thiết kế một ứng dụng đa tenant có 5 triệu listings, 500 triệu view events, 1 triệu bookings, search p99 thấp, analytics lag tối đa năm phút và high availability. Giải thích document boundaries, index families, aggregation/summary, replica set hoặc sharding, shard key, consistency, test matrix, observability và migration plan. Không đưa kết luận “phải sharding” trước khi kiểm tra workload/capacity thực tế.

## 40. Tài liệu tham khảo

- MongoDB Manual — [Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/): cách mô hình document theo access patterns.
- MongoDB Manual — [Embedded Data Models](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/): embedding và referencing.
- MongoDB Manual — [BSON Documents](https://www.mongodb.com/docs/manual/core/document/): document semantics và BSON.
- MongoDB Manual — [Indexes](https://www.mongodb.com/docs/manual/indexes/): compound, multikey, partial, unique và TTL.
- MongoDB Manual — [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/).
- MongoDB Manual — [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/).
- MongoDB Manual — [Index Optimization](https://www.mongodb.com/docs/manual/tutorial/analyze-query-plan/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Manual — [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/).
- MongoDB Manual — [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/).
- MongoDB Manual — [Aggregation Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/).
- MongoDB Manual — [$group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/).
- MongoDB Manual — [$lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/).
- MongoDB Manual — [$facet](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/).
- MongoDB Manual — [Replica Sets](https://www.mongodb.com/docs/manual/replication/).
- MongoDB Manual — [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/).
- MongoDB Manual — [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/).
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).
- MongoDB Manual — [Sharding](https://www.mongodb.com/docs/manual/sharding/).
- MongoDB Manual — [Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-shard-key/).
- MongoDB Manual — [Atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/).
- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/).
- MongoDB Manual — [Change Streams](https://www.mongodb.com/docs/manual/changeStreams/).
- MongoDB Manual — [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/).
- MongoDB Java Sync Driver — [CRUD](https://www.mongodb.com/docs/drivers/java/sync/current/crud/).
- Spring Data MongoDB Reference — [MongoTemplate](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html).
- Spring Data MongoDB Reference — [Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html).

## 41. Tổng kết: tư duy hệ thống khi thiết kế MongoDB

Không nên học **document, index, aggregation và topology** như bốn danh sách API rời rạc. Chúng là bốn mặt của một quyết định kiến trúc:

~~~text
Document shape
    -> quyết định query/read/write boundaries
        -> quyết định index keys và write amplification
            -> quyết định aggregation input/state/output
                -> quyết định routing và tài nguyên từng node/shard
                    -> quyết định latency, consistency và cost
~~~

**Document** là lựa chọn ranh giới dữ liệu: embed phần nhỏ/cùng vòng đời, reference tập dữ liệu lớn hoặc có lifecycle độc lập. **Index** là cấu trúc truy cập phục vụ query shapes và constraints, nhưng tiêu tốn disk/write budget. **Aggregation** tận dụng indexing ở đầu pipeline rồi có thể cần group/sort/join state lớn; hãy tối ưu theo semantics và cân nhắc summary khi workload lặp lại. **Replica set** chủ yếu giải quyết HA/replication/consistency choices; **sharding** phân phối dữ liệu và tải nhưng đem lại quyết định shard key, routing và merge complexity. Mọi tầng đều phải tuân **tenant isolation, type correctness, concurrency control, backup và observability**.

Nguyên tắc bền vững nhất là **bắt đầu từ access patterns và yêu cầu đúng của nghiệp vụ, thiết kế toàn chuỗi, đo bằng explain/metrics/test, rồi điều chỉnh có kiểm soát**. Khi một query chậm, đừng đoán nguyên nhân chỉ nằm ở index hay số nodes. Khi dữ liệu tăng, đừng tự nhúng mọi thứ hoặc tự sharding trước khi hiểu cardinality. Và khi kết quả đúng nhưng latency tăng, hãy nhìn đồng thời **hình dạng document, số index, aggregation state và vị trí thực thi trong topology**. Đó là cách thiết kế MongoDB có thể mở rộng mà vẫn giữ đúng dữ liệu và chi phí dự đoán được.
