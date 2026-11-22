# Cân bằng số index, tốc độ đọc, tốc độ ghi và dung lượng

MongoDB dùng **index** để giảm số document phải kiểm tra khi truy vấn, hỗ trợ tìm kiếm theo điều kiện, sắp xếp, kiểm tra tính duy nhất và một số chức năng chuyên biệt. Index có thể khiến một API đọc dữ liệu nhanh hơn rất nhiều, nhưng **không miễn phí**: nó phải được lưu trữ, duy trì khi dữ liệu thay đổi, chiếm chỗ trong bộ nhớ đệm và làm phức tạp việc triển khai/vận hành.

Một hệ thống có hàng chục index trên mỗi collection chưa chắc nhanh hơn một hệ thống có vài index được thiết kế đúng theo workload. Ngược lại, xóa hết index để tăng tốc ghi thường khiến các truy vấn quan trọng chuyển thành collection scan và làm CPU, I/O, tail latency tăng mạnh.

Bài học **“Cân bằng số index, tốc độ đọc, tốc độ ghi và dung lượng”** thuộc chương **Tối ưu hiệu năng** tập trung vào việc tìm **điểm cân bằng** giữa bốn yếu tố:

1. **Số lượng và cấu trúc index:** mỗi index giải quyết yêu cầu nào, có trùng lặp hay không?
2. **Tốc độ đọc:** các truy vấn quan trọng có dùng index hiệu quả và trả kết quả đúng SLO không?
3. **Tốc độ ghi:** việc duy trì index gây thêm chi phí cho insert, update, delete và replication ra sao?
4. **Dung lượng:** index chiếm disk, WiredTiger cache, backup/restore và chi phí hạ tầng ở mức nào?

Mục tiêu cuối là **thiết kế tập index nhỏ nhưng đủ**, đáp ứng đúng các truy vấn và ràng buộc nghiệp vụ với chi phí ghi/lưu trữ chấp nhận được.

> **Không có “số index tối ưu” cố định cho mọi collection.** Số index phù hợp phụ thuộc vào tỷ lệ đọc/ghi, query shapes, độ chọn lọc, thứ tự sort, kích thước collection, phân bố giá trị, loại index và mục tiêu latency/cost. Quyết định phải dựa trên dữ liệu đo được, không dựa vào việc đếm index đơn thuần.

---

## 1. Mô hình tổng quát: một index giúp gì và tốn gì?

Giả sử collection `orders` có 20 triệu document. Một API thường xuyên chạy:

```javascript
db.orders.find({
  tenantId: "TENANT-A",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20);
```

Nếu không có index thích hợp, MongoDB có thể phải kiểm tra nhiều document và xử lý sort tốn tài nguyên. Một compound index:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

có thể giúp lọc theo tenant/status, đọc dữ liệu theo `createdAt` gần như đúng thứ tự cần trả và dừng sớm theo limit.

Nhưng khi tạo một đơn hàng mới, MongoDB phải ghi document **và** duy trì key tương ứng trong các index. Khi xóa đơn hàng, các key cũng phải được gỡ. Khi cập nhật `status`, index có `status` thường phải thay key cũ bằng key mới.

Tóm tắt:

```text
                           MongoDB Collection
                                  │
                     ┌────────────┴────────────┐
                     │                         │
                Truy vấn đọc              Thao tác ghi
                     │                         │
                Index lookup             Document change
                     │                         │
          Ít document phải xét       Cập nhật index keys
          Sort/limit hiệu quả        Journal, cache, I/O
                     │                         │
              Read latency ↓           Write cost ↑
                     └────────────┬────────────┘
                                  │
                           Disk + RAM
                           + vận hành
```

Một index đáng tạo khi **lợi ích đo được** lớn hơn **chi phí bổ sung** cho toàn bộ workload và các ràng buộc dữ liệu.

### 1.1. Các lợi ích có thể đo

- Số documents examined giảm.
- Số keys examined giảm hoặc phù hợp với phạm vi query.
- Tránh collection scan trên đường truy vấn quan trọng.
- Tránh blocking sort hoặc giảm chi phí sort.
- Query kết thúc sớm với `limit`.
- Một số query có thể được phục vụ chỉ bằng index (*covered query*).
- Read latency p50/p95/p99 giảm.
- CPU và disk reads giảm.
- Unique index bảo vệ invariant nghiệp vụ.
- TTL index tự phục vụ vòng đời xóa dữ liệu theo điều kiện.

### 1.2. Các chi phí cần tính

- Disk space của index.
- Working set của index trong WiredTiger cache.
- Thêm công việc khi insert/delete.
- Thêm công việc khi update làm thay đổi indexed values.
- Journal/checkpoint/I/O và replication liên quan.
- Initial index build và rebuild sau sự cố/restore.
- Backup size hoặc restore/recovery time, tùy công cụ.
- Index management, monitoring và migration risk.
- Write latency/tail latency khi tài nguyên đang bão hòa.

Không phải mọi khoản đều tăng theo một tỷ lệ tuyến tính cố định. Một index hẹp, partial và ít thay đổi có chi phí khác xa một multikey index chứa nhiều giá trị trên mỗi document.

## 2. Chọn tối ưu theo workload, không theo một câu query

Tối ưu một query hiếm gặp bằng index mới có thể làm **mọi lệnh ghi** của collection tốn thêm chi phí. Vì thế cần phân loại workload.

### 2.1. Ví dụ một ngày hoạt động

| Loại thao tác | Tần suất minh họa | Mục tiêu |
|---|---:|---|
| Tìm 20 orders mới nhất của tenant | 800.000/ngày | p95 dưới 80 ms |
| Tìm orders theo customer | 300.000/ngày | p95 dưới 120 ms |
| Xem order theo `_id` | 1.000.000/ngày | p95 dưới 40 ms |
| Tạo order mới | 150.000/ngày | p95 dưới 100 ms |
| Cập nhật `status` | 450.000/ngày | p95 dưới 100 ms |
| Cập nhật `lastViewedAt` | 2.000.000/ngày | Không làm nghẽn writes |
| Báo cáo cũ theo chiến dịch | 20/ngày | Chấp nhận chạy batch |

Đây là dữ liệu **giả định để luyện cách ra quyết định**, không phải benchmark của MongoDB.

Một index chỉ phục vụ báo cáo 20 lần/ngày có thể không đáng tạo nếu nó làm hàng triệu updates mỗi ngày chậm hơn. Báo cáo đó có thể chạy offline, dùng aggregation khác hoặc cần một index chuyên biệt nếu business SLO thực sự bắt buộc.

### 2.2. Read-heavy, write-heavy và mixed

| Kiểu workload | Đặc điểm | Hướng cân bằng |
|---|---|---|
| Read-heavy | Nhiều `find`, `aggregate`, ít writes | Có thể chấp nhận nhiều index phục vụ query hot |
| Write-heavy | Nhiều inserts/updates/deletes, ít query shapes | Giữ tập index gọn, ưu tiên index thực sự cần |
| Mixed | Ghi và đọc đều quan trọng | Tối ưu trọng số theo SLO, đo trade-off |
| Analytical batch | Ít jobs, scan nhiều dữ liệu | Cân nhắc pipeline/analytics riêng |
| Time-series/event ingestion | Ghi liên tục, query theo time/window | Thiết kế index theo thời gian và retention |
| Multi-tenant | Query theo tenant, phân bố không đều | Compound indexes, tránh tenant hotspot |
| Search-heavy | Text/vector retrieval | Search/Vector Search indexes riêng và chi phí riêng |

**Tỷ lệ đọc/ghi không đủ một mình.** Một read cần scan 5 triệu records tốn nhiều hơn một read `_id`; một update `lastSeenAt` khác update hàng trăm array elements.

## 3. Chi phí index trong thao tác ghi: hiểu đúng bản chất

MongoDB duy trì các database indexes theo quá trình thay đổi document.

### 3.1. Insert

Khi insert một document mới:

```javascript
db.orders.insertOne({
  _id: "O-001",
  tenantId: "TENANT-A",
  orderNo: "2026-0001",
  status: "NEW",
  createdAt: new Date(),
  total: 250000
});
```

MongoDB phải cập nhật `_id` index tự động và những secondary indexes áp dụng cho document này.

Một collection có nhiều index nghĩa là **cùng một insert** có thể yêu cầu nhiều index-key insertions, làm tăng:

- CPU cho key extraction/encoding;
- Thao tác trên B-tree structure;
- Dirty cache pages;
- Write-ahead journal/checkpoint work;
- Disk/replication-related overhead;
- Cơ hội phát sinh uniqueness constraint errors.

### 3.2. Delete

Khi xóa một document:

```javascript
db.orders.deleteOne({
  _id: "O-001",
  tenantId: "TENANT-A"
});
```

MongoDB phải gỡ các keys tương ứng ở indexes có document đó. Vì vậy xóa một triệu bản ghi cũng có thể tốn đáng kể I/O khi index nhiều.

### 3.3. Update

**Không phải mọi update đều chạm tất cả index.**

Ví dụ index:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

Thay một field không được index:

```javascript
db.orders.updateOne(
  { _id: "O-001" },
  { $set: { note: "Đã gọi xác nhận" } }
);
```

có thể không cần thay key của index trên `tenantId/status/createdAt`, nếu không có thay đổi khác ảnh hưởng index membership. MongoDB vẫn phải thực hiện document write và các công việc liên quan.

Thay field được index:

```javascript
db.orders.updateOne(
  { _id: "O-001" },
  { $set: { status: "PAID" } }
);
```

thường tạo thay đổi trong key của index có `status`.

MongoDB ghi nhận rằng với insert/delete, index keys tương ứng được thêm/gỡ; với update, **một tập con indexes có thể bị ảnh hưởng** tùy trường/key thay đổi. Partial/sparse indexes chỉ được cập nhật khi document thuộc phạm vi index tương ứng, kể cả các trường hợp đi vào/ra khỏi phạm vi. Xem [Write Operation Performance](https://www.mongodb.com/docs/manual/core/write-performance/).

### 3.4. Field cập nhật liên tục là điểm rủi ro

Ví dụ:

```javascript
db.sessions.updateOne(
  { _id: sessionId },
  { $set: { lastSeenAt: new Date() } }
);
```

Nếu mỗi user heartbeat liên tục và `lastSeenAt` được index phục vụ một query hiếm, MongoDB có thể phải duy trì index rất thường xuyên.

Trước khi index một field có update frequency cao, cần xác định:

- Query nào thật sự dùng nó?
- Có thể dùng `createdAt`/`expiresAt` riêng không?
- Có thể gom updates hoặc thay data model?
- Có cần query real-time theo field không?
- Có partial index giảm số document tham gia không?
- Index có làm write p99 tăng đáng kể không?

Đừng tự bỏ một TTL index nếu nó phục vụ chính sách retention; phải cân nhắc đúng chức năng.

## 4. Tại sao nhiều index có thể làm writes chậm?

Giả sử một collection có:

```text
_id_
tenantId_1
status_1
createdAt_-1
tenantId_1_status_1
tenantId_1_status_1_createdAt_-1
customerId_1
tenantId_1_customerId_1
tenantId_1_customerId_1_createdAt_-1
orderNo_1
lastSeenAt_1
```

Nếu nhiều index không phục vụ query thường xuyên, overhead tồn tại trên toàn collection dù chúng ít được dùng.

Một mô hình chi phí khái quát:

\[
T_{\text{write}} \approx T_{\text{document}} +
\sum_{i \in \text{affected indexes}} T_{\text{index},i} +
T_{\text{other}}
\]

`T_other` có thể gồm durability/replication, contention và network. Công thức này chỉ là **khung lý giải**, không phải công thức tuyến tính để dự báo số milliseconds.

### 4.1. Không thể suy ra tăng gấp đôi index thì write chậm gấp đôi

Chi phí phụ thuộc:

- Kích thước và loại index;
- Số index keys trên mỗi document;
- Compression/caching;
- Độ chọn lọc và thứ tự key;
- Giá trị thay đổi hay giữ nguyên;
- RAM/disk load;
- Batch size;
- CPU/replication topology;
- Primary vs secondary;
- Concurrent workloads.

Có thể 3 index mới gần như không tác động một update cụ thể, nhưng lại ảnh hưởng đáng kể đến inserts liên tục. **Benchmark chính thao tác ứng dụng đang dùng** mới cho kết luận.

### 4.2. Indexing còn xảy ra trên replica set

Khi primary thực hiện write, các secondary members duy trì bản sao dữ liệu và index theo cơ chế replication. Dung lượng index và resource usage có thể xuất hiện trên nhiều data-bearing nodes.

Không báo cáo “index chiếm 5 GB toàn cluster” chỉ vì một primary có index 5 GB, cũng không cộng mọi copies thành logical data size. Phân biệt:

- **Logical index footprint per dataset**;
- **Physical footprint across replicas**;
- **Backup/snapshot overhead**;
- **Working set theo node**.

## 5. Số lượng index không nói lên kích thước

Hai indexes cùng là một index trong `getIndexes()`, nhưng dung lượng có thể rất khác nhau.

Ví dụ:

```javascript
db.products.createIndex({ category: 1 });

db.products.createIndex({
  title: 1,
  description: 1,
  createdAt: -1
});
```

Index trên nhiều fields/giá trị dài thường có cấu trúc key lớn hơn. Nhưng dữ liệu thực, prefix compression và phân bố cũng ảnh hưởng kích thước.

### 5.1. Những yếu tố ảnh hưởng dung lượng

- Số documents được index;
- Số keys được tạo trên mỗi document;
- Độ dài/kiểu BSON values;
- Số fields trong compound key;
- Multi-key arrays;
- Duplicate values/compression;
- Loại index (B-tree, geospatial, wildcard, text, Search);
- Partial filter;
- Mức cập nhật/churn;
- Storage engine và trạng thái dữ liệu.

Một index ít dùng nhưng chứa một mảng dài ở mỗi document có thể chiếm nhiều dung lượng hơn vài index hẹp khác.

### 5.2. Disk footprint và RAM working set khác nhau

- **Disk index size:** dung lượng dữ liệu index tồn tại trên storage.
- **Index working set:** phần index pages được workload thường xuyên truy cập.
- **WiredTiger cache usage:** memory cache đang được storage engine dùng cho dữ liệu/index pages và metadata liên quan.

Index lớn hơn RAM không tự nghĩa query luôn chậm; nếu phần index thường dùng nhỏ và nằm trong cache, read có thể tốt. Ngược lại, một index nhỏ nhưng query thiếu selectivity vẫn có thể kém hiệu quả.

## 6. Bộ dữ liệu ví dụ xuyên suốt

Ta dùng collection **thử nghiệm** `indexTradeoffLab.ordersBench`. Không chạy `drop()` hoặc `deleteMany({})` trên production chỉ để thử các ví dụ.

Một mẫu document:

```javascript
{
  _id: "ORD-1001",
  tenantId: "T-01",
  orderNo: "2026-1001",
  customerId: "C-07",
  status: "PAID",
  createdAt: ISODate("2026-11-10T08:00:00Z"),
  updatedAt: ISODate("2026-11-11T09:00:00Z"),
  amount: 249000,
  channel: "WEB",
  tags: ["priority", "gift"],
  archived: false,
  expireAt: null
}
```

Các query shapes điển hình:

**Q1 — Đơn hàng mới nhất theo tenant và trạng thái:**

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20);
```

**Q2 — Lịch sử đơn của một khách hàng:**

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  customerId: "C-07"
})
.sort({ createdAt: -1 })
.limit(20);
```

**Q3 — Tìm order theo số đơn trong tenant:**

```javascript
db.ordersBench.findOne({
  tenantId: "T-01",
  orderNo: "2026-1001"
});
```

**Q4 — Tổng hợp doanh thu một lần mỗi đêm:**

```javascript
db.ordersBench.aggregate([
  {
    $match: {
      tenantId: "T-01",
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$channel",
      amount: { $sum: "$amount" }
    }
  }
]);
```

**Q5 — Cập nhật trạng thái thường xuyên:**

```javascript
db.ordersBench.updateOne(
  { _id: "ORD-1001", tenantId: "T-01" },
  {
    $set: {
      status: "SHIPPED",
      updatedAt: new Date()
    }
  }
);
```

Bây giờ câu hỏi là: tạo **bao nhiêu** index và **trên những fields nào** để phục vụ năm kiểu workload này?

## 7. Bắt đầu từ những index bắt buộc

MongoDB tự tạo `_id` index cho collection thông thường theo quy tắc loại collection.

```javascript
db.ordersBench.getIndexes();
```

Với collection mới, thường thấy:

```javascript
[
  {
    v: 2,
    key: { _id: 1 },
    name: "_id_"
  }
]
```

`_id` index phục vụ tìm theo `_id` và bảo đảm uniqueness của `_id` trong phạm vi quy định. Không cần tạo thêm `{_id:1}` chỉ vì một query `findOne({_id: ...})`.

### 7.1. Unique index là ràng buộc dữ liệu

Nếu `orderNo` chỉ cần duy nhất **trong tenant**, dùng:

```javascript
db.ordersBench.createIndex(
  { tenantId: 1, orderNo: 1 },
  {
    unique: true,
    name: "uq_tenant_orderNo"
  }
);
```

Index này không chỉ phục vụ query Q3; nó ngăn trùng `(tenantId, orderNo)` theo unique semantics của MongoDB.

**Không bỏ unique index chỉ vì `$indexStats` báo ít truy vấn.** Nó có thể là một **correctness constraint**, không phải chỉ là công cụ performance.

### 7.2. Unique và optional fields

Nếu field optional/missing/null, unique semantics có thể tạo kết quả bất ngờ. Cần xác định liệu uniqueness chỉ áp dụng cho records có field hay cho mọi records. Một partial unique index có thể phù hợp trong trường hợp được thiết kế đúng.

Khi chuyển sang partial unique, cần kiểm tra dữ liệu trùng, điều kiện filter và phạm vi ràng buộc. Không thay constraint đang phục vụ nghiệp vụ chỉ để giảm dung lượng index.

## 8. Compound index thay cho nhiều single-field indexes

Để phục vụ Q1:

```javascript
db.ordersBench.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1
  },
  {
    name: "idx_tenant_status_created_desc"
  }
);
```

Để phục vụ Q2:

```javascript
db.ordersBench.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    createdAt: -1
  },
  {
    name: "idx_tenant_customer_created_desc"
  }
);
```

Để bảo vệ Q3:

```javascript
db.ordersBench.createIndex(
  { tenantId: 1, orderNo: 1 },
  { unique: true, name: "uq_tenant_orderNo" }
);
```

Ba index này có các mục tiêu khác nhau. Có thể không cần đồng thời tạo thêm tất cả:

```javascript
{ tenantId: 1 }
{ status: 1 }
{ createdAt: -1 }
{ customerId: 1 }
{ orderNo: 1 }
```

nếu chúng không phục vụ những query shapes độc lập có ý nghĩa.

### 8.1. Không kết luận compound index luôn thay thế single-field index

Index `{tenantId:1,status:1,createdAt:-1}` hỗ trợ tốt những điều kiện phù hợp với **prefix** của index, nhưng không bảo đảm tối ưu cho query chỉ có:

```javascript
db.ordersBench.find({ status: "PAID" });
```

Vì `status` không phải leading field, query planner có thể cần index khác hoặc chọn đường đọc khác.

Đừng xóa `{status:1}` chỉ vì thấy `status` xuất hiện trong một compound index; hãy xem workload cụ thể và explain.

### 8.2. Compound key order quan trọng

Với index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

Một query có equality trên `tenantId/status` và sort `createdAt:-1` có thể tận dụng tốt prefix/ordering.

Nhưng nếu đổi thành:

```javascript
{ createdAt: -1, tenantId: 1, status: 1 }
```

query Q1 có thể phải duyệt phạm vi lớn hơn, vì leading field đã thay đổi. Không chọn thứ tự key dựa vào thứ tự viết JSON trong một query; cần hiểu **equality, sort, range** và phân bố dữ liệu.

## 9. Quy tắc ESR: Equality, Sort, Range

Một heuristic phổ biến khi thiết kế compound B-tree index là:

1. **Equality (E):** những fields có equality filter;
2. **Sort (S):** thứ tự sắp xếp cần hỗ trợ;
3. **Range (R):** fields có phạm vi như `$gte`, `$lt`.

Ví dụ:

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  status: "PAID",
  amount: { $gte: 100000 }
})
.sort({ createdAt: -1 })
.limit(20);
```

Một index ứng viên:

```javascript
{
  tenantId: 1,
  status: 1,
  createdAt: -1,
  amount: 1
}
```

Nhưng ESR **không phải quy tắc tuyệt đối**. Nếu range theo `amount` cực kỳ chọn lọc, một thứ tự **ERS** có thể scan ít keys hơn dù phải xử lý sort khác đi. Trên dữ liệu thật nên thử hai ứng viên bằng explain và latency/load tests.

### 9.1. Một compound index quá rộng có thể phản tác dụng

Index trên sáu fields có thể làm index key lớn, tăng write cost và vẫn không giải quyết những query shapes chỉ lọc field giữa. Không “thêm mọi field vào một index” để giảm số index một cách cơ học.

### 9.2. Prefix và sort đảo chiều

MongoDB có thể quét một số compound B-tree indexes theo chiều ngược để hỗ trợ sort ngược tương ứng. Nhưng không phải mọi tổ hợp tăng/giảm của từng field đều hỗ trợ như nhau; cần đối chiếu index sort pattern và equality filters.

**Luôn dùng explain và kết quả query để kiểm tra**, thay vì đoán chỉ từ số lượng `1`/`-1` trong index definition.

## 10. Covered query: tăng tốc đọc bằng cách tránh fetch document

Một query được gọi là **covered** khi các điều kiện truy vấn và fields cần trả được phục vụ bằng index theo quy tắc MongoDB, không cần đọc document nguồn cho phần đó.

Ví dụ index:

```javascript
db.ordersBench.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

Query:

```javascript
db.ordersBench.find(
  {
    tenantId: "T-01",
    status: "PAID"
  },
  {
    _id: 0,
    tenantId: 1,
    status: 1,
    createdAt: 1
  }
)
.sort({ createdAt: -1 })
.limit(20);
```

Nếu planner dùng index phù hợp và query đủ điều kiện coverage, `totalDocsExamined` có thể là **0**.

### 10.1. Vì sao cần `_id: 0`?

Mặc định, MongoDB `find()` có thể trả `_id`. Nếu `_id` không có trong compound index, projection mặc định có thể buộc FETCH document. Loại `_id` khi không cần giúp tạo điều kiện cho covered query.

### 10.2. Không nên thêm mọi field chỉ để đạt coverage

Giả sử UI còn muốn trả:

```text
customerName
shippingAddress
items
paymentDetails
```

Đưa tất cả vào index có thể khiến index quá lớn, write overhead tăng mạnh, thậm chí có những loại field không phù hợp với index key.

Một chiến lược khác:

1. Dùng index hẹp để tìm đúng 20 documents;
2. FETCH 20 documents;
3. Project chỉ những fields cần.

Thường tốt hơn index khổng lồ chỉ để tránh FETCH 20 records. Quyết định phải dựa trên measurements.

### 10.3. Covered query có điều kiện đặc biệt với multikey

Không tự giả định mọi query trên array đều có thể covered như scalar field. Multikey indexing có những giới hạn riêng về projection và `$elemMatch`. Hãy kiểm tra explain và tài liệu của index type/version.

## 11. Đo hiệu quả index bằng `explain("executionStats")`

Trong môi trường thử nghiệm đã được cấp phép, chạy:

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
```

Các trường cần quan sát:

| Trường/khái niệm | Ý nghĩa |
|---|---|
| `winningPlan` | Đường truy vấn được planner chọn |
| `IXSCAN` hoặc stage tương đương | Có dùng index scan không |
| `COLLSCAN` | Có scan collection không |
| `FETCH` | Có đọc documents nguồn không |
| `SORT`/blocking sort | Có phải xử lý sort ngoài index không |
| `nReturned` | Số kết quả trả |
| `totalKeysExamined` | Số index entries được duyệt |
| `totalDocsExamined` | Số documents được kiểm tra |
| `executionTimeMillis` | Thời gian execution theo phạm vi explain |

Các stage names/output thay đổi theo query engine và MongoDB version; đừng viết hệ thống monitoring chỉ nhận đúng một tên stage.

### 11.1. Documents examined / returned

Một phép đo hữu ích:

\[
R_{\text{docs}}=
\frac{\text{totalDocsExamined}}{\max(1,\text{nReturned})}
\]

Ví dụ:

```text
nReturned = 20
totalDocsExamined = 1.000.000
R_docs = 50.000
```

Tức MongoDB examine trung bình 50.000 documents để trả một document. Đây là tín hiệu cần xem query/index.

Tuy vậy, ratio cao không tự là lỗi: query tìm **0 kết quả** hoặc kiểm tra phân tích dữ liệu lớn có thể hợp lý. Kết hợp business intent, latency và resource usage.

### 11.2. Keys examined cũng quan trọng

Một index scan có thể chỉ FETCH 20 documents nhưng duyệt hàng triệu keys để tìm chúng. Khi đó `totalDocsExamined` thấp chưa chắc index hiệu quả. Hãy xem **cả keys examined và docs examined**.

### 11.3. Một lần `explain` không đo p99

`explain("executionStats")` chỉ là quan sát một execution/query shape. Nó không phản ánh toàn bộ:

- Driver pool wait;
- Network latency;
- Concurrent traffic;
- Cache warm/cold;
- Replication;
- Application serialization;
- Retry và request fan-out.

Dùng explain để hiểu query plan, rồi kiểm tra APM/load tests để thấy end-to-end SLO.

## 12. Kiểm tra số lượng index và cấu hình của chúng

Dùng:

```javascript
db.ordersBench.getIndexes();
```

Đây là thông tin **định nghĩa**, chẳng hạn key, name, unique, partial, sparse, TTL, collation hoặc hidden (nếu có).

Ví dụ:

```javascript
[
  { name: "_id_", key: { _id: 1 } },
  {
    name: "idx_tenant_status_created_desc",
    key: { tenantId: 1, status: 1, createdAt: -1 }
  },
  {
    name: "idx_tenant_customer_created_desc",
    key: { tenantId: 1, customerId: 1, createdAt: -1 }
  }
]
```

Lệnh `getIndexes()` **không cho biết index nào đang sử dụng nhiều**, và không trực tiếp cho biết size của từng index.

### 12.1. Phân nhóm index theo mục đích

Trong inventory nên có:

```text
Index name
Index key
Unique/TTL/partial/hidden?
Query shapes được bảo vệ
SLO/owner
Accesses theo thời gian
Index size
Write-frequency của indexed fields
Ghi chú về business constraints
```

Nếu không có owner/query shape cho một index, đó là **ứng viên cần điều tra**, chưa phải bằng chứng phải xóa.

## 13. `$indexStats`: tìm index ít được truy cập

MongoDB cung cấp `$indexStats` để xem thống kê sử dụng từng index.

```javascript
db.ordersBench.aggregate([
  {
    $indexStats: {}
  },
  {
    $project: {
      name: 1,
      key: 1,
      host: 1,
      accesses: 1
    }
  }
]);
```

Output có thể có:

```javascript
{
  name: "idx_tenant_status_created_desc",
  key: { tenantId: 1, status: 1, createdAt: -1 },
  host: "mongo1.example:27017",
  accesses: {
    ops: NumberLong("23500"),
    since: ISODate("2026-11-10T00:00:00Z")
  }
}
```

`accesses.ops` là số **user operations** dùng index trên host/điểm đo theo ngữ nghĩa của `$indexStats`, không phải tổng số keys examined hay số index writes.

### 13.1. Các giới hạn quan trọng

- `$indexStats` **phải là stage đầu** của aggregation pipeline.
- Không dùng `$indexStats` bên trong transaction.
- Thống kê có phạm vi **node/host**, không tự tổng hợp mọi members.
- Các counters có mốc bắt đầu `accesses.since`, không phải toàn bộ lịch sử index.
- `mongod` restart, drop/recreate index hoặc sửa một số thuộc tính index có thể reset thống kê.
- Các hoạt động nội bộ như TTL deletion, oplog apply hoặc index builds không được đếm thành user index access theo `accesses.ops`.
- Một index không được query planner chọn vẫn có thể phục vụ **uniqueness, TTL hoặc yêu cầu vận hành**.

Các điểm này được mô tả trong [MongoDB `$indexStats`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexstats/).

### 13.2. Không xóa ngay khi `accesses.ops = 0`

Ví dụ:

```text
Index A: accesses.ops=0
Index B: accesses.ops=3
Index C: accesses.ops=1.000.000
```

Câu hỏi cần hỏi:

1. Server mới restart không?
2. Index này phục vụ batch chạy mỗi tháng/quý?
3. Ứng dụng có query chỉ tại failover/DR không?
4. Index có unique/TTL constraint không?
5. Metric này lấy ở primary hay secondary?
6. Một shard/tenant khác có dùng không?
7. Có query `hint()` hoặc code path ít gặp?
8. Có khung quan sát bao trùm chu kỳ kinh doanh không?
9. Có index mới vừa tạo chưa có traffic?
10. Có thể hidden thử và theo dõi SLO không?

Không dùng zero access của một node trong một giờ để quyết định xóa index production toàn cluster.

## 14. Đo kích thước index và collection

Một nguồn phổ biến là `collStats`/`db.collection.stats()` theo version và quyền phù hợp.

Ví dụ:

```javascript
db.ordersBench.stats({
  scale: 1024 * 1024
});
```

Trong output có thể có:

```text
count
size
storageSize
totalIndexSize
indexSizes
nindexes
```

Các giá trị size thường được scale theo `scale` được chọn. Cần đọc định nghĩa field và storage engine/version thực tế.

Một cách đọc tường minh bằng command:

```javascript
const stats = db.runCommand({
  collStats: "ordersBench",
  scale: 1024 * 1024
});

printjson({
  count: stats.count,
  logicalDataMB: stats.size,
  storageMB: stats.storageSize,
  totalIndexMB: stats.totalIndexSize,
  indexSizesMB: stats.indexSizes
});
```

Các lệnh này chỉ mang tính tham khảo cho phiên bản/deployment hỗ trợ; metric availability trên Atlas tier có thể khác. Không coi con số `size` luôn là physical bytes thực trên disk.

### 14.1. Phân biệt các size

| Metric | Tư duy |
|---|---|
| `size` | Kích thước logical data theo định nghĩa stats |
| `storageSize` | Dung lượng cấp phát/lưu trữ cho collection theo storage engine |
| `totalIndexSize` | Tổng footprint của indexes theo thống kê |
| `indexSizes` | Footprint theo từng index |
| Disk used của node/volume | Toàn bộ disk: database, index, journal, logs, metadata... |

Không cộng tùy ý các metrics có định nghĩa trùng hoặc khác phạm vi rồi gọi đó là tổng bill.

### 14.2. Một báo cáo footprint nên ghi đủ

```text
Collection: ordersBench
Count: 20,000,000 documents
Storage size: 18.3 GiB
Total index size: 12.4 GiB
Largest index: 5.1 GiB
Primary node: mongo-rs-01
Measured at: 2026-11-14 09:00 UTC
Server/FCV: ...
```

Các số là **minh họa**. Khi làm thực tế, cần lấy số tại đúng server, timezone, unit và phiên bản.

### 14.3. Index size không bằng lượng RAM được dùng

Một index 5 GiB có thể chỉ có 100 MiB hot pages, hoặc hầu như toàn bộ keys được quét liên tục làm cache thrash. `indexSizes` không cho biết “toàn bộ index đang nằm trong RAM”.

Để hiểu memory pressure cần xem WiredTiger cache metrics, page reads/evictions và query latency.

## 15. WiredTiger cache, index và read latency

WiredTiger sử dụng cache để giảm disk I/O cho dữ liệu và index pages. Khi working set vượt khả năng cache hoặc nhiều queries tranh pages, hiệu năng có thể giảm.

### 15.1. Những triệu chứng thường gặp

- Read p95/p99 tăng dù QPS không đổi.
- Disk reads tăng.
- WiredTiger cache eviction pressure tăng.
- Một query mới làm nhiều index pages lạnh bị đọc.
- Backup/index build cạnh tranh I/O.
- Page cache của OS và WiredTiger cache bị ép bởi resource limits.

### 15.2. “Cache gần đầy” có chắc là xấu?

Không. Cache thường được tận dụng để giữ dữ liệu nóng. Cần xem **eviction rate, disk read latency, dirty bytes, contention** và workload. Đừng tự coi cache 80–90% sử dụng là bằng chứng cần tăng RAM nếu p99 vẫn trong SLO và eviction không có vấn đề.

### 15.3. Index hẹp có thể cải thiện cache locality

Nếu hai query shapes đều được đáp ứng bởi một index nhỏ, hiệu quả cache có thể tốt hơn giữ nhiều index gần tương đương. Nhưng nếu gộp thành một index quá rộng làm key lớn hơn nhiều, working set có thể tệ hơn.

**Giảm số index không tự đồng nghĩa giảm working set**; cần so physical size và access pattern.

## 16. Partial indexes: ít documents tham gia hơn

Partial index chỉ index những documents khớp một `partialFilterExpression`.

Giả sử chỉ 10% orders đang active:

```javascript
db.ordersBench.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1
  },
  {
    name: "idx_active_tenant_status_created",
    partialFilterExpression: {
      archived: false
    }
  }
);
```

Những documents `archived: true` không có entry trong index này. Lợi ích có thể gồm:

- Ít index keys;
- Index nhỏ hơn;
- Ít overhead cho writes vào các document không thuộc phạm vi;
- Cache footprint nhỏ hơn;
- Query đang tìm active orders có thể hiệu quả.

### 16.1. Query phải chứng minh thuộc phạm vi partial index

Ví dụ có thể dùng index:

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  archived: false,
  status: "PAID"
})
.sort({ createdAt: -1 });
```

Nhưng query:

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  status: "PAID"
});
```

không đảm bảo chỉ muốn orders `archived:false`, vì vậy query planner **không thể dùng partial index nếu nó khiến kết quả thiếu records**.

Điều này rất quan trọng: **partial index nhỏ không phải index thay thế cho mọi query trên cùng fields**.

### 16.2. Khi record chuyển trạng thái

```javascript
db.ordersBench.updateOne(
  { _id: "ORD-1001" },
  { $set: { archived: true } }
);
```

Document có thể **rời khỏi** phạm vi partial index; MongoDB phải loại key khỏi index. Nếu `archived` được chuyển qua lại liên tục, việc vào/ra index cũng có chi phí.

### 16.3. Partial và sparse khác nhau

- `sparse`: thường dựa trên sự hiện diện của field, theo loại index/compound semantics.
- `partial`: cho phép điều kiện filter rõ ràng hơn, như `archived:false`, `status:"ACTIVE"` hoặc phạm vi hợp lệ.

MongoDB khuyến nghị partial index trong nhiều trường hợp cần kiểm soát chính xác phạm vi. Không dùng `partialFilterExpression` cùng `sparse:true` trên một index. Xem [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/).

### 16.4. Partial unique có ràng buộc khác

Một unique partial index chỉ enforce uniqueness đối với **những document thuộc partial filter**. Nếu nghiệp vụ yêu cầu uniqueness trên mọi records, thay unique toàn collection bằng partial unique có thể gây lỗi dữ liệu.

## 17. Multikey index: số keys có thể lớn hơn số documents

Khi index một array field, MongoDB sử dụng **multikey index** theo điều kiện hỗ trợ.

Ví dụ:

```javascript
{
  _id: "ORD-1001",
  tenantId: "T-01",
  tags: ["priority", "gift", "mobile"]
}
```

Index:

```javascript
db.ordersBench.createIndex({
  tenantId: 1,
  tags: 1
});
```

Một document có thể tạo nhiều index keys tương ứng các giá trị trong array.

### 17.1. Một document có 100 tags không tương đương một scalar field

Khi tags nhiều, index key count và disk cost có thể tăng đáng kể. Một update thêm/xóa tags có thể làm nhiều keys thay đổi.

Nếu index tags ít được truy vấn nhưng mọi order có hàng trăm tags, đây là một ứng viên chi phí cao.

### 17.2. Giới hạn compound multikey

MongoDB có các giới hạn đối với **compound multikey indexes**, đặc biệt khi nhiều indexed fields cùng là arrays trong một document. Không mặc định có thể index mọi tổ hợp array fields mà không giới hạn.

Nếu thiết kế:

```javascript
{
  categories: ["A", "B"],
  colors: ["red", "blue"]
}
```

và muốn compound index cả hai arrays, phải kiểm tra quy tắc multikey của MongoDB; trong những trường hợp không được hỗ trợ, thao tác tạo index hoặc ghi document có thể thất bại.

### 17.3. Query trên array có cần index không?

Có thể, nhưng cần đo:

- Số key entries;
- Số docs examined;
- Query frequency;
- Độ chọn lọc;
- Sort behavior;
- Có `$elemMatch` và multikey bounds phù hợp không;
- Index size và write cost.

Đừng index array field chỉ vì schema có array.

## 18. Chọn giữa compound index và index intersection

MongoDB query planner có những khả năng kết hợp dữ liệu từ nhiều indexes trong các tình huống được hỗ trợ (*index intersection*), nhưng điều đó **không bảo đảm hiệu năng tương đương compound index**.

Giả sử:

```javascript
db.ordersBench.createIndex({ tenantId: 1 });
db.ordersBench.createIndex({ status: 1 });
```

Một query:

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  status: "PAID"
});
```

Có thể có các kế hoạch dùng một index, intersection nếu planner thấy phù hợp, hoặc lựa chọn khác theo dữ liệu/statistics.

Index:

```javascript
db.ordersBench.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

còn hỗ trợ thứ tự keys và có thể phục vụ filter+sort tốt hơn.

### 18.1. Không tạo indexes đôi chỉ để “planner tự ghép”

Nếu Q1 là query nóng, benchmark compound index trực tiếp. Không giả định MongoDB sẽ luôn intersect hai single-field indexes và đạt cùng read latency.

### 18.2. Không gộp thành compound nếu workload không có query kết hợp

Nếu 99% query độc lập theo `customerId` hoặc `createdAt`, có thể cần các single-field indexes riêng. **Mẫu truy vấn thực tế** quyết định.

## 19. Collation và index dùng cho string sorting

Index trên string chịu ảnh hưởng của **collation** khi cần so sánh/sort theo ngôn ngữ, dấu và chữ hoa/thường.

Ví dụ ứng dụng muốn tìm/sort sản phẩm tên không phân biệt chữ hoa:

```javascript
db.products.createIndex(
  { tenantId: 1, title: 1 },
  {
    name: "idx_tenant_title_ci",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
```

Query cần collation tương thích theo điều kiện MongoDB:

```javascript
db.products.find({
  tenantId: "T-01",
  title: "Keyboard"
})
.collation({
  locale: "en",
  strength: 2
});
```

Index collation khác nhau có thể làm query planner không dùng index như mong đợi. Việc tạo thêm index chỉ khác collation để phục vụ các UI sort patterns có thể làm tăng disk và write cost.

**Không dùng collation tiếng Anh như giải pháp mặc định cho tiếng Việt**. Chọn locale/strength theo business expectation và benchmark với dữ liệu có dấu.

## 20. TTL index: chi phí có thể được biện minh bằng retention

TTL index giúp MongoDB tự xóa document đã hết hạn theo cơ chế chạy nền.

Ví dụ collection sessions:

```javascript
db.sessionsLab.createIndex(
  { expireAt: 1 },
  {
    expireAfterSeconds: 0,
    name: "ttl_expireAt"
  }
);
```

Document có `expireAt` kiểu Date hợp lệ sẽ đủ điều kiện hết hạn theo mốc thời gian phù hợp.

### 20.1. TTL không chỉ là index cho read

Một TTL index có thể có `accesses.ops = 0` vì tiến trình xóa TTL là hoạt động nội bộ không được tính như user query access. Nó vẫn cần thiết cho retention.

**Không xóa TTL index chỉ vì báo “không có truy vấn nào dùng”.**

### 20.2. TTL delete cũng làm tăng write load

Khi xóa hàng loạt documents hết hạn, MongoDB phải ghi xóa documents và gỡ keys từ các indexes liên quan. Có thể quan sát:

- Delete operations;
- Disk I/O;
- Replication activity;
- Write latency;
- TTL queue/load;
- Disk capacity.

TTL không bảo đảm xóa đúng từng millisecond. Nếu retention nhạy cảm về pháp lý, phải thiết kế thêm quy trình và xác minh phù hợp.

### 20.3. Partial TTL cần kiểm tra điều kiện

MongoDB có những hình thức partial TTL index theo phiên bản và loại collection, nhưng không phải mọi combination là hợp lệ. Không mặc định mọi compound key+partial expression đều có thể dùng làm TTL. Hãy đọc tài liệu TTL/partial TTL của MongoDB release đang chạy.

## 21. Wildcard indexes: linh hoạt nhưng có giá

Nếu collection có fields thay đổi theo từng tenant:

```javascript
{
  tenantId: "T-01",
  attributes: {
    color: "blue",
    memoryGB: 16,
    keyboardLayout: "US"
  }
}
```

Một wildcard index ứng viên:

```javascript
db.products.createIndex({
  "attributes.$**": 1
});
```

Wildcard index có thể hỗ trợ query trên những paths không biết trước và được MongoDB hỗ trợ theo quy tắc riêng.

### 21.1. Không coi wildcard index là index “miễn phí cho mọi field”

Index nhiều paths động có thể:

- Tạo nhiều index entries;
- Chiếm disk/cache đáng kể;
- Tốn chi phí inserts/updates;
- Không tối ưu mọi sort/query như compound indexes chuyên biệt;
- Không thay uniqueness constraints;
- Có những giới hạn đối với arrays, projections, compound structures theo phiên bản.

Nếu workload thực tế chỉ dùng `attributes.color` và `attributes.memoryGB`, index trên hai paths cụ thể có thể rẻ và dự đoán được hơn.

### 21.2. Chọn từ telemetry

Dùng query logs/Atlas insights để tìm các paths nóng, sau đó so sánh wildcard với indexes cụ thể. Không tạo wildcard index chỉ vì schema linh hoạt.

## 22. Geospatial, text, hashed và Search indexes cũng có trade-off

Không phải mọi index đều là B-tree thường.

| Index/engine | Nhu cầu chính | Đánh đổi cần xem |
|---|---|---|
| B-tree single/compound | Equality/range/sort | Write + disk + planner complexity |
| Multikey | Truy vấn arrays | Nhiều keys/document |
| 2dsphere | Tìm kiếm vị trí địa lý | Geometry/index footprint |
| 2d | Tọa độ phẳng | Giới hạn ngữ nghĩa và cấu hình |
| Hashed | Equality/hash-distributed patterns | Không thay range/sort thông thường |
| Text index (`$text`) | Full-text cơ bản | Index maintenance, hạn chế Search |
| Wildcard | Query dynamic paths | Index nhiều fields, storage overhead |
| MongoDB Search | Lucene full-text/relevance | Search index riêng, indexing lag, tài nguyên Search |
| MongoDB Vector Search | Similarity retrieval | Vector storage/index, ANN/ENN cost, sync lag |

### 22.1. MongoDB Search index không hiện như B-tree index thường

Nếu dùng:

```javascript
db.products.createSearchIndex(...);
```

Search index có vòng đời và metrics riêng. `db.products.getIndexes()` không phải danh sách đầy đủ của MongoDB Search indexes.

Khi lập capacity plan cho một collection, phải tính cả:

- Database indexes;
- Search/Vector Search indexes;
- Dedicated Search Nodes hoặc co-located resources;
- Backfill/rebuild;
- Dữ liệu vector embeddings nếu ứng dụng lưu.

### 22.2. Text và Vector Search có độ trễ đồng bộ

Search index thường được đồng bộ bất đồng bộ với source. Một record mới được ghi thành công có thể chưa xuất hiện ngay trong kết quả Search/Vector Search.

Không dùng Search index làm nguồn xác nhận ràng buộc nghiệp vụ có yêu cầu read-after-write hoặc authorization tức thì.

## 23. Hidden index: thử loại bỏ khỏi query planner trước khi drop

MongoDB có **hidden indexes** để đánh giá tác động nếu planner không được dùng index đó.

Giả sử đã có:

```text
idx_tenant_status_created_desc
```

Một thao tác quản trị có thể ẩn index:

```javascript
db.ordersBench.hideIndex(
  "idx_tenant_status_created_desc"
);
```

Sau khi hidden:

- Query planner **không chọn index đó**;
- Không thể dùng `hint()` để ép query sử dụng hidden index;
- **Index vẫn được duy trì khi ghi**;
- **Index vẫn chiếm disk và memory**;
- Unique constraint vẫn được enforce nếu là unique index;
- TTL index vẫn thực hiện expiration;
- Index có thể được unhide nhanh hơn nhiều so với rebuild từ đầu;
- Thống kê `$indexStats` của index có thể reset khi hide/unhide.

Xem [Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/).

### 23.1. Hidden index chỉ thử tác động tới reads

Nếu hidden index vẫn được cập nhật cho mọi write, quá trình hide **không đo được lợi ích write/storage của việc drop thật**.

Đây là điểm rất dễ nhầm:

```text
Hide index:
  Read behavior thay đổi
  Write index maintenance vẫn tồn tại
  Disk index vẫn tồn tại

Drop index:
  Read behavior thay đổi
  Không còn index maintenance tương ứng
  Không còn index structure tương ứng
```

Vì vậy, một thử nghiệm hidden giúp giảm rủi ro đọc, còn write-gain phải được đo ở staging/benchmark hoặc sau rollout có kiểm soát.

### 23.2. Kế hoạch thử hidden

1. Inventory query shapes/owner của index.
2. Xem `$indexStats` đủ dài.
3. Xác định indexes thuộc correctness/TTL.
4. Thử workload với index hidden trên staging.
5. Nếu production thử, có change window và SLO alarms.
6. So p95/p99, query scans, CPU/I/O.
7. Nếu xấu, unhide.
8. Chỉ sau khi đủ bằng chứng mới cân nhắc drop.

### 23.3. Hiding cũng là thao tác thay đổi production

Lệnh `hideIndex()` **không phải read-only**. Nó có thể khiến query planner chuyển sang COLLSCAN, tăng latency ngay. Không chạy để “kiểm tra” trên cluster đang phục vụ người dùng nếu chưa được phê duyệt.

### 23.4. Không thể hide `_id` index

`_id` index có ràng buộc riêng và không thể hide theo quy tắc MongoDB. Không thử “giảm index count” bằng việc can thiệp `_id`.

## 24. Drop index: thao tác vận hành phải có rollback

Xóa một index có thể giảm overhead ghi và dung lượng logical index theo thời gian, nhưng cũng có thể làm API đọc chậm hoặc mất constraint.

Ví dụ cú pháp **chỉ chạy khi đã phê duyệt**:

```javascript
db.ordersBench.dropIndex(
  "idx_tenant_status_created_desc"
);
```

Trước drop cần trả lời:

- Index có unique/TTL/partial business invariant không?
- Query nào dùng? Query khẩn cấp ít gặp có cần không?
- Có index khác hỗ trợ cùng query shapes không?
- Có ảnh hưởng tới shard key/indexing constraints không?
- Có report jobs/batch jobs phụ thuộc không?
- Có thể rebuild trong RTO không?
- Có đủ disk/CPU/I/O cho rebuild nếu rollback không?
- Có window/owner/alert/runbook không?

### 24.1. Rollback sau drop không tức thì

Nếu drop rồi cần khôi phục, phải **tạo lại index**. Với collection lớn, index build có thể tốn đáng kể thời gian và tài nguyên, kể cả khi database vẫn phục vụ traffic.

Do đó hidden index là bước thăm dò có ích trước drop, nhưng không thay thế kế hoạch khôi phục.

### 24.2. Disk usage sau drop

Việc xóa index sẽ thay đổi footprint dữ liệu index, nhưng **disk free do OS/volume báo cáo không nhất thiết giảm theo cùng thời điểm/mức độ** bởi cách storage engine/volume quản lý cấp phát, snapshots và file reuse. Đo lại metrics phù hợp sau thao tác; không hứa số GB trên volume sẽ giảm đúng bằng `indexSizes` ngay lập tức.

### 24.3. Không drop index chỉ vì có index khác cùng prefix

Ví dụ:

```text
A: { tenantId: 1 }
B: { tenantId: 1, status: 1, createdAt: -1 }
```

Có thể B thay thế A cho phần lớn query tenant-only, nhưng A nhỏ hơn, có thể được cache tốt hơn và có chi phí khác. Xem explain trên workload để quyết định.

## 25. Duplicates, redundant indexes và index inventory

Có thể gặp:

```text
Index A: { tenantId: 1 }
Index B: { tenantId: 1, status: 1 }
Index C: { tenantId: 1, status: 1, createdAt: -1 }
Index D: { tenantId: 1, status: 1, createdAt: -1, orderNo: 1 }
```

Mỗi index có lợi ích riêng trong một số query. Nhưng cũng có nguy cơ giữ quá nhiều index gần giống.

### 25.1. Phân loại redundancy

**Exact equivalent:** cùng key và các thuộc tính quan trọng, có thể là duplicate không cần thiết (và có những giới hạn tạo equivalent indexes theo version).

**Prefix-overlap:** một index là tiền tố của index khác; có thể dư nhưng chưa chắc.

**Same fields, different order:** ví dụ `{tenantId,createdAt}` và `{createdAt,tenantId}`; phục vụ query shapes khác nhau, không mặc định dư.

**Different sort direction:** một số chiều đảo có thể hỗ trợ bằng reverse scan, nhưng cần kiểm tra compound sort semantics.

**Different collation/partial/unique:** hai indexes có cùng key nhưng khác thuộc tính có thể phục vụ nhu cầu/ràng buộc khác nhau.

### 25.2. Bảng inventory mẫu

| Index | Được tạo để làm gì? | Reads sử dụng? | Business constraint? | Ứng viên |
|---|---|---|---|---|
| `_id_` | Lookup theo ID | Cao | Có | Giữ |
| `uq_tenant_orderNo` | Tra số đơn/unique | Trung bình | Có | Giữ |
| `idx_tenant_status_created_desc` | Q1 hot | Cao | Không | Giữ |
| `idx_tenant_customer_created_desc` | Q2 hot | Cao | Không | Giữ |
| `idx_status_1` | Filter status-only cũ | Thấp | Không | Kiểm tra |
| `idx_lastSeenAt_1` | Dashboard cũ | Gần 0 | Không | Kiểm tra kỹ |
| `ttl_expireAt` | Retention sessions | 0 user accesses | Có | Giữ theo policy |

Đây là bảng minh họa, không phải kết quả đo của một hệ thống thực.

### 25.3. Không chỉ đếm số index, cần “giá trị theo workload”

Một index được dùng 1.000.000 lần/ngày nhưng chỉ tiết kiệm 0.1 ms mỗi query có thể có lợi ích ít hơn một index được dùng 100.000 lần/ngày nhưng giảm mỗi query từ 2 giây xuống 20 ms. Tần suất cần kết hợp **impact**.

## 26. Ước lượng lợi ích và chi phí bằng mô hình định lượng

Một công thức định hướng:

\[
B_{\text{read}} =
\sum_{q \in Q}
f_q \cdot
\left(t_{q,\text{without}} - t_{q,\text{with}}\right)
\]

Trong đó:

- \(Q\): các query shapes liên quan;
- \(f_q\): số lần query shape \(q\) được gọi trong một khoảng;
- \(t\): thời gian đo trên workload đại diện.

Tương tự, chi phí ghi:

\[
C_{\text{write}} =
\sum_{w \in W}
f_w \cdot
\left(t_{w,\text{with}} - t_{w,\text{without}}\right)
\]

Các phép tính này cho **tổng chênh lệch thời gian công việc tương đối**, không tự bằng năng lực CPU hay chi phí tiền vì các requests có thể chạy đồng thời và resource contention phi tuyến.

### 26.1. Ví dụ minh họa

Giả sử index X:

```text
Giảm 8 ms cho 500.000 reads/ngày
Tăng 0,6 ms cho 1.000.000 writes/ngày
Tốn thêm 5 GiB index storage
```

Lợi ích thời gian đọc cộng dồn theo mô hình đơn giản:

\[
500.000 \times 0.008 = 4000\text{ giây/ngày}
\]

Chi phí thời gian ghi cộng dồn:

\[
1.000.000 \times 0.0006 = 600\text{ giây/ngày}
\]

Không có nghĩa hệ thống tiết kiệm “3400 giây wall-clock” vì concurrency, caching và resource usage khác nhau. Nhưng đó là tín hiệu định lượng ban đầu để **đặt câu hỏi và thử nghiệm sâu hơn**.

### 26.2. Trọng số nghiệp vụ

Một read báo cáo hiếm và một write thanh toán quan trọng có thể có trọng số khác nhau.

Ví dụ bảng chấm điểm:

| Chiều | Câu hỏi |
|---|---|
| Latency SLO | Index có giúp đường nóng đạt p95/p99? |
| Write throughput | Ghi có bị chậm dưới tải đỉnh? |
| Storage budget | Index có vượt quota/disk headroom? |
| Reliability | Index build/restore ảnh hưởng availability? |
| Correctness | Index có unique/TTL/invariant phải giữ? |
| Business criticality | Endpoint nào ảnh hưởng trực tiếp doanh thu? |
| Operational complexity | Có thể rollback an toàn không? |

Không dùng một “điểm tổng” giả tạo để bỏ qua bắt buộc bảo mật/uniqueness.

## 27. Tối ưu index cho workload nhiều updates

Một collection `users` có:

```javascript
{
  _id: "U101",
  tenantId: "T-01",
  emailNormalized: "u101@example.com",
  plan: "PRO",
  lastSeenAt: ISODate("2026-11-14T10:00:00Z")
}
```

Workload:

```text
Lookup email: 100.000/ngày
Update lastSeenAt: 10.000.000/ngày
Filter lastSeenAt range: 100/ngày
```

Có thể cần unique/index cho `tenantId + emailNormalized`, nhưng index `lastSeenAt` có thể rất đắt so với lợi ích 100 queries/ngày.

### 27.1. Các lựa chọn

- Chấp nhận scan/batch cho báo cáo hiếm, nếu phù hợp.
- Materialize aggregate theo ngày/giờ.
- Tách heartbeat events sang collection phù hợp.
- Giảm tần suất update `lastSeenAt` theo business policy.
- Dùng index partial cho subset nếu truy vấn hợp lệ.
- Đo rõ read benefit vs write penalty trước khi quyết định.

### 27.2. Không đổi business semantics chỉ để tăng hiệu năng

Nếu `lastSeenAt` dùng cho chính sách an ninh hoặc logout, việc giảm tần suất update phải được review. Tối ưu hiệu năng không cho phép làm sai tính mới và tính đúng của dữ liệu bảo mật.

## 28. Đánh đổi với bulk ingest và batch writes

Một batch import hàng triệu documents vào collection có nhiều indexes có thể chậm vì index maintenance.

### 28.1. Vì sao import ít indexes có thể nhanh hơn?

Khi insert mỗi document, MongoDB phải duy trì indexes đã tồn tại. Một số hệ import offline có thể chọn:

1. Chuẩn bị collection mới;
2. Insert dữ liệu;
3. Tạo indexes sau;
4. Verify readiness và query plans;
5. Chuyển ứng dụng sang collection mới.

Nhưng cách này chỉ phù hợp khi:

- Không phục vụ concurrent queries cần index;
- Không cần unique constraint trong quá trình ingest hoặc có validation khác;
- Có đủ disk/time cho index build;
- Có rollback;
- Dữ liệu không bị trùng/lỗi làm index build fail;
- Được phê duyệt khi cutover.

### 28.2. Production online import khác offline load

Không nên drop indexes khỏi collection production đang có traffic để import nhanh, vì:

- Query plans thay đổi đột ngột;
- Unique/TTL invariants có thể mất;
- Rebuild gây tải lớn;
- Dữ liệu trùng có thể khiến unique index không tạo lại được;
- Backup/replication và operational SLO bị ảnh hưởng.

Đối với online writes, tối ưu batch size, concurrency, network và indexes **có kiểm soát**.

### 28.3. `ordered` và write efficiency

Khi dùng `insertMany`, options `ordered:true`/`false` ảnh hưởng hành vi khi gặp lỗi trong batch. Không dùng unordered như một cách “bỏ qua hết mọi validation/unique errors”. Cần báo cáo failed documents và bảo đảm idempotency.

## 29. Sharded cluster: index là chi phí theo từng shard

Trong sharded MongoDB:

```text
Application
    │
  mongos
    │
    ├── Shard A
    ├── Shard B
    └── Shard C
```

Database indexes trên sharded collection cần được xem theo query routing và phân bố dữ liệu.

### 29.1. Shard key và query targeting

Nếu shard key là `tenantId` hoặc một compound key phù hợp, query có điều kiện đúng shard key có thể target tập shards nhỏ hơn. Một index tối ưu trên từng shard **không tự sửa** scatter-gather query nếu router không thể target.

Ví dụ:

```javascript
db.ordersBench.find({
  status: "PAID"
});
```

không có tenant/shard key có thể gửi tới nhiều shards dù mỗi shard có index `{status:1}`.

### 29.2. Tổng storage trên cluster

Với sharding, mỗi shard lưu subset dữ liệu và indexes tương ứng; replica sets còn lưu copies. Cần phân biệt:

- Logical index size theo collection;
- Sum index size across shards;
- Per-member storage;
- Replication factor;
- Backups;
- Search index footprint nếu có.

Không tính nhầm một index 2 GiB trên ba secondary copies thành “6 GiB logical index data”, nhưng physical disk capacity cần phản ánh mọi copies.

### 29.3. Unique index trên sharded collection có ràng buộc đặc biệt

MongoDB có yêu cầu về shard-key prefix/unique index trong nhiều cấu hình. Không thêm một unique index chỉ theo `orderNo` trên sharded collection rồi mặc định uniqueness được enforce toàn cluster theo ý muốn.

Trước khi tạo/xóa unique index ở sharded collection, xem tài liệu phiên bản và thiết kế shard key. Đó là **correctness constraint**, không chỉ performance choice.

## 30. Index build: chi phí của việc thêm index

Tạo index trên collection lớn là một công việc đáng kể.

```javascript
db.ordersBench.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created_desc" }
);
```

Khi build, MongoDB cần đọc dữ liệu, trích xuất keys, sắp xếp/cấu trúc index và commit index theo quy trình tương ứng.

Các tác động có thể thấy:

- CPU/RAM/disk I/O tăng;
- Disk headroom giảm;
- Query/write latency bị ảnh hưởng;
- Replication/secondary build workload;
- Thời gian build kéo dài;
- Index không sẵn sàng ngay nếu management API xử lý bất đồng bộ;
- Build fail vì dữ liệu không hợp lệ/duplicate key nếu unique.

### 30.1. Cần thời điểm triển khai

Nếu API peak lúc 20:00, không nên tự tạo một index khổng lồ đúng giờ cao điểm chỉ vì query đang chậm. Cần xem:

- Maintenance/low-traffic window;
- Dung lượng còn lại;
- Resource headroom;
- Rollback;
- Monitoring;
- Index build status;
- Replica set/quorum considerations;
- Kịch bản thất bại.

Không áp dụng quy trình build index của phiên bản cũ cho mọi phiên bản MongoDB mới; đặc tính concurrency/build locking đã thay đổi theo release.

### 30.2. `createIndex()` có thể thành công mà query vẫn không nhanh

Index tồn tại không bảo đảm planner dùng nó. Query shape, collation, selectivity, partial predicate, sort order và cache có thể khiến MongoDB chọn đường khác. Sau build cần **verify explain trên representative queries**.

### 30.3. Build chiếm dung lượng tạm thời

Kế hoạch capacity nên có headroom cho index build và sorting/temp artifacts theo phiên bản/config. Đừng cấp disk vừa đúng với tổng `storageSize + totalIndexSize` hiện tại rồi thêm một index lớn.

## 31. Benchmark đúng cách trước và sau khi đổi index

Một phép đo đáng tin cần **cùng workload, cùng dữ liệu và điều kiện được ghi rõ**.

### 31.1. Ghi baseline trước thay đổi

Lưu:

```text
MongoDB version / FCV
Cluster topology / tier / node size
Dataset count / distribution / size
Current indexes / index sizes
Traffic mix read-write / query shapes
p50/p95/p99 read latency
p50/p95/p99 insert/update/delete latency
ops/sec, concurrency
CPU/RAM/cache/disk I/O
Replication lag
Driver pool wait
```

### 31.2. Dữ liệu thử phải có phân bố thực

Một collection 10.000 documents với tenant IDs phân bố đều không đại diện 100 triệu documents mà một tenant chiếm 70% và một số status rất phổ biến.

Cần mô phỏng:

- Tenant lớn/nhỏ;
- Hot vs cold records;
- Field cardinality;
- Missing/null values;
- Arrays dài/ngắn;
- Data skew;
- Range query;
- Các khoảng ngày cao điểm;
- Realistic document size.

### 31.3. Tách warm cache và cold cache

Chạy một query lần đầu sau index build có thể đọc nhiều pages từ disk. Chạy lại có thể được cache phục vụ nhanh hơn.

Cần định nghĩa thí nghiệm rõ:

- Cold-cache scenario;
- Warm-cache steady state;
- Load concurrency;
- Tail latency;
- Thời gian ổn định trước đo;
- Volume/tier;
- Background workload.

Không chọn chỉ một lần chạy nhanh nhất làm bằng chứng.

### 31.4. Tránh thử destructive trên production

Các thao tác như hideIndex, dropIndex, rebuild hoặc load cao phải được kiểm soát. Dùng staging có dữ liệu tương đương hoặc synthetic dataset được thiết kế đúng. Nếu thử production, phải có change window, owner, risk review và rollback.

### 31.5. So sánh nhiều chiều

| Chỉ số | Baseline | Candidate A | Candidate B |
|---|---:|---:|---:|
| Read p95 | 180 ms | 80 ms | 65 ms |
| Update p95 | 22 ms | 29 ms | 45 ms |
| Insert throughput | 8.000/s | 7.200/s | 5.300/s |
| Index size | 4 GiB | 7 GiB | 13 GiB |
| CPU p95 | 65% | 70% | 90% |
| Disk read p95 | 12 ms | 8 ms | 8 ms |

**Các số giả lập.** Trong ví dụ, B nhanh hơn về read nhưng có write/storage penalty lớn. Nếu cập nhật đơn hàng có SLO chặt, A có thể là lựa chọn phù hợp hơn B.

Không có “index tốt nhất” nếu chưa nêu **ưu tiên nghiệp vụ**.

## 32. Tránh đo sai do cache, plan cache và statistics

Khi so sánh plan/indexes, kết quả có thể thay đổi bởi:

- Data cache đã được làm nóng;
- Query plan cache;
- Background compaction/checkpoint;
- Concurrent writes;
- Network jitter;
- Shard rebalancing;
- Primary election;
- Index build;
- Application deployment;
- Garbage collection;
- Load generator bottleneck.

### 32.1. Khi thay đổi index, plan selection có thể thay đổi

Planner có thể chọn index khác sau create/hide/drop, tạo ra sự thay đổi latency không chỉ từ footprint.

Cần ghi lại `winningPlan` trước/sau, không chỉ so wall-clock time.

### 32.2. `hint()` để thử plan có giới hạn

Trong môi trường được phép, có thể dùng hint để thăm dò một index cụ thể:

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.hint("idx_tenant_status_created_desc")
.explain("executionStats");
```

Nhưng:

- `hint()` có thể ép planner chọn kế hoạch kém;
- Hidden index không thể dùng với `hint()`;
- Partial index có điều kiện coverage;
- Lệnh trên không chứng minh planner mặc định sẽ chọn index;
- `hint` trong application production làm query dễ phụ thuộc index name;
- Nên dùng hint như công cụ chẩn đoán, không phải sửa mọi vấn đề planner bằng hardcode.

## 33. Ưu tiên index cho các query shapes nóng

Một cách triển khai thực tiễn:

1. Lấy top query shapes theo total execution time, p95/p99 và tần suất.
2. Xác định business impact/SLO.
3. Với mỗi query, xem `explain()`.
4. Tạo candidate indexes theo equality/range/sort.
5. Kiểm tra overlap với indexes hiện tại.
6. Ước lượng write/storage cost.
7. Benchmark dưới read/write mix.
8. Chọn tập index nhỏ nhất đáp ứng SLO.
9. Đưa vào staging, quan sát behavior.
10. Rollout có alert/rollback.

### 33.1. Không tối ưu đồng thời 100 query shapes

Ưu tiên 5–10 query shapes có đóng góp lớn nhất vào p99/user impact. Một số query hiếm có thể chuyển sang batch/analytics hoặc cần giới hạn frequency.

### 33.2. Tối ưu schema/query trước khi thêm index

Có lúc vấn đề không phải thiếu index:

- Trả quá nhiều fields;
- Query không có `limit`;
- N+1 queries;
- Regex không thể tận dụng index tốt;
- Aggregation làm `unwind` quá lớn;
- Embedded arrays không giới hạn;
- Thiếu pagination;
- Truy vấn sai tenant/shard key;
- Sort không cần thiết;
- Tạo nhiều MongoClient;
- Mỗi request gọi nhiều round trips.

Một thay đổi query/data model có thể tạo lợi ích lớn mà không cần thêm index nào.

## 34. Phân trang và sort: tác động tới thiết kế index

Một endpoint thường cần:

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

Nếu cần thứ tự ổn định khi nhiều orders có cùng `createdAt`, thêm `_id` như tie-breaker là hợp lý.

Index ứng viên:

```javascript
db.ordersBench.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
```

### 34.1. `skip()` offset lớn có thể đắt

```javascript
db.ordersBench.find({
  tenantId: "T-01"
})
.sort({ createdAt: -1 })
.skip(100000)
.limit(20);
```

Offset pagination có thể phải đi qua nhiều entries dù có index. Với dataset lớn, **keyset/cursor pagination** dựa trên `{createdAt,_id}` có thể hiệu quả hơn.

### 34.2. Keyset pagination cần index và điều kiện phù hợp

Một query kế tiếp có thể dùng điều kiện “nhỏ hơn cặp createdAt/_id cuối trang” theo thứ tự sắp giảm, nhưng cần xử lý hai fields và trường hợp thời điểm trùng. Đừng đơn giản dùng `createdAt: {$lt: lastCreatedAt}` rồi làm mất orders cùng timestamp.

Việc đổi pagination có thể giảm nhiều công hơn so với thêm một index chỉ để tăng tốc `skip()`.

## 35. Time-series và vòng đời dữ liệu

Với telemetry/logs/events ghi liên tục:

```javascript
{
  sensorId: "S-101",
  ts: ISODate("2026-11-14T10:00:00Z"),
  temperature: 25.3
}
```

Workload thường gồm inserts liên tục, query theo sensor/time window, retention.

Một mô hình:

```text
Write rate cao
Read chủ yếu theo sensor + khoảng thời gian
Data expiration theo policy
```

Cần chọn schema, collection type và indexes phù hợp.

### 35.1. Time-series collection có thiết kế index riêng

MongoDB time-series collections sử dụng bucket-based storage và có quy tắc index/tùy chọn riêng theo server version. Đừng bê nguyên mọi B-tree/index/TTL example của regular collection sang time-series mà không kiểm tra hỗ trợ.

### 35.2. Retention có thể giảm dung lượng tổng thể

Nếu giữ dữ liệu logs 30 ngày thay vì vô hạn, policy TTL/retention có thể giảm footprint. Nhưng xóa dữ liệu là quyết định pháp lý/nghiệp vụ, và TTL deletes cũng tạo write activity. Không tự rút retention chỉ để đạt một KPI disk.

## 36. Chi phí index trong backup, restore và DR

Index footprint ảnh hưởng tới vận hành khi:

- Tạo snapshots/backups;
- Restore một dataset lớn;
- Rebuild indexes tùy phương thức restore;
- Initial sync của replica set members;
- Tạo node mới;
- Reshard/rebalance;
- Thay tiers/volume size;
- Chuyển vùng cloud.

Không phải mọi phương pháp backup đều lưu/phục hồi index files giống nhau; cần kiểm tra giải pháp cụ thể (Atlas snapshots, logical backup, storage-level snapshot).

### 36.1. Không mặc định mọi restore sẽ phải rebuild tất cả indexes

Một physical snapshot có thể lưu dữ liệu/index khác với logical export/import. RTO phụ thuộc cách backup và restore, dung lượng, network và hardware. Đo qua **restore drill**, không ước lượng chỉ từ `totalIndexSize`.

### 36.2. Budget storage theo physical copies

Ví dụ:

```text
Logical data:             40 GiB
Logical indexes:          20 GiB
Replica set:              3 data-bearing nodes
```

Rất sơ bộ, ba copies có thể cần hàng trăm GiB physical storage trước khi tính journal, compression, snapshot, free space, temporary index build. Đây không phải công thức bill chính xác; phải dựa trên Atlas/cloud/storage metrics.

## 37. Vai trò của monitoring và cảnh báo

Không thể cân bằng lâu dài nếu chỉ benchmark khi tạo index rồi không theo dõi nữa.

Một dashboard nên có:

### Đọc

- Query p50/p95/p99 theo endpoint/query shape;
- Operations/s;
- `totalDocsExamined`/`nReturned`;
- `totalKeysExamined`;
- COLLSCAN/slow query rate;
- Sort spills;
- Read IOPS/cache misses.

### Ghi

- Insert/update/delete operations/s;
- Write p95/p99;
- Write errors/duplicate key;
- Replication lag;
- Journal/checkpoint/disk write pressure;
- Concurrent operations/locks;
- Change stream/CDC lag khi có.

### Index/storage

- Số index theo collection;
- Tổng index size;
- Index sizes theo tên;
- `$indexStats` accesses trong window;
- Hidden/partial/TTL/unique flags;
- Index build status;
- Free disk/headroom;
- WiredTiger cache/eviction;
- Backup/restore size/time.

### Application

- HTTP latency/error rate;
- Driver command time;
- Connection pool checkout wait;
- Retry count;
- Read/write ratio theo nghiệp vụ;
- Deployment annotations.

### 37.1. Alert phải gắn SLO

Ví dụ:

```text
Write p99 > 150 ms for 10 minutes
AND traffic > minimum volume
```

có thể hữu ích hơn một alert “collection có hơn 10 indexes”, vì số lượng index chỉ là điều kiện thiết kế chứ không tự là sự cố.

Một index mới làm write p99 tăng nhưng reads p95 giảm phải được đánh giá so với **cả hai SLO**.

## 38. Decision matrix: khi nào nên thêm, gộp hay bỏ index?

| Tình huống | Hành động ưu tiên | Điều cần kiểm |
|---|---|---|
| Query nóng có COLLSCAN, p99 xấu | Thử index phù hợp | Read benefit, write penalty |
| Nhiều single-field trùng prefix | Xem compound candidate | Query shapes độc lập có còn cần không |
| Index ít query accesses | Điều tra/hidden thử | Unique/TTL/rare batch/restart |
| Index chứa field update liên tục | Đánh giá lại | Query business value, write latency |
| Dataset nhiều archived docs | Cân nhắc partial index | Query có predicate khớp không |
| Index trên arrays dài | Đo multikey footprint | Keys per doc và updates |
| Query trả nhiều fields | Projection/limit trước | Index coverage có đáng không |
| Full-text semantics | Dùng Search khi phù hợp | Lucene index lifecycle/cost |
| 2dsphere geo query | Geo index phù hợp | Geometry validity/index size |
| Write-heavy ingest | Giữ indexes cần thiết | Unique/TTL và load window |
| Sharded query scatter | Xem shard targeting | Index trên shard không thay routing |
| Index build làm tăng I/O | Lập change window | Resource headroom/rollback |
| Disk gần đầy | Phân tích size/retention | Không drop constraint tùy tiện |
| Planner chọn index lạ | Explain/benchmark | Không hardcode hint mù quáng |

Một index được **giữ** không chỉ vì có nhiều accesses. Nó có thể bảo vệ tính đúng đắn hoặc đáp ứng một truy vấn hiếm nhưng bắt buộc.

## 39. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách hiểu đúng |
|---|---|---|
| “Nhiều index luôn nhanh hơn” | Writes và storage tăng | Chọn theo workload |
| “Ít index luôn tốt hơn” | Hot reads scan quá nhiều | Giữ index phục vụ SLO |
| “Mỗi field cần một index” | Index trùng/khó bảo trì | Thiết kế theo query shapes |
| “Compound index thay mọi single index” | Missing leading prefix queries | Kiểm tra prefix/use cases |
| “ESR là quy tắc tuyệt đối” | Có thể scan nhiều keys | Benchmark ESR/ERS |
| “Index dùng 0 lần phải xóa” | Mất unique/TTL hoặc rare queries | Inventory/đo theo chu kỳ |
| “Hidden index giảm write overhead” | Sai: hidden vẫn maintained | Hidden chỉ thử planner effect |
| “Drop index xong rollback ngay” | Rebuild chậm/tốn tài nguyên | Có rollback plan |
| “Update luôn thay mọi index” | Đánh giá chi phí sai | Xem indexed keys bị ảnh hưởng |
| “Partial index thay mọi query cùng fields” | Query thiếu records | Predicate phải imply partial filter |
| “Multikey array là một key” | Underestimate storage | Có thể nhiều keys/document |
| “Index size bằng cache RAM” | Capacity plan sai | Disk footprint khác working set |
| “Query có IXSCAN chắc chắn tối ưu” | Có thể examine hàng triệu keys | Xem keys/docs/latency |
| “Explain 20 ms nghĩa API p99 20 ms” | Bỏ pool/network/app | Đo end-to-end |
| “Read p95 tốt thì không cần đo writes” | Write SLO bị phá | Benchmark cả read/write |
| “Cộng mọi replica metrics là số business writes” | Đếm lặp | Tách node/internal operations |
| “Xóa index sẽ giảm disk tức thì đúng số GB” | Dự báo sai | Đo storage lifecycle |
| “Index build không ảnh hưởng traffic” | I/O/CPU spikes | Capacity/change window |
| “Tạo unique index không thể fail” | Dữ liệu trùng | Validate trước |
| “TTL index zero accesses là vô dụng” | Mất retention | TTL internal operations |
| “Index intersection luôn như compound” | Plan kém | Đo query shape |
| “Wildcard index thay mọi index cụ thể” | Index phình to | Dùng khi dynamic queries thật |
| “Search index giống B-tree index” | Thiếu capacity/indexing lag | Quản lý riêng |
| “Index giải quyết mọi API chậm” | Có thể do N+1/pool | Tracing toàn request |
| “Một benchmark 100 docs đại diện production” | Kết luận không đáng tin | Dữ liệu/phân bố đại diện |

## 40. Bài tập thực hành

### Bài 1 — Xác định index nào có giá trị

Một collection có:

```text
_id_
tenantId_1
status_1
tenantId_1_status_1
tenantId_1_status_1_createdAt_-1
customerId_1
tenantId_1_customerId_1_createdAt_-1
```

Trong ngày:

```text
Q1: tenantId + status + createdAt sort: 500.000 lần
Q2: tenantId + customerId + createdAt sort: 200.000 lần
Q3: status-only: 10 lần
```

1. Những indexes nào rõ ràng phục vụ query nóng?
2. Index nào là ứng viên kiểm tra redundancy?
3. Vì sao không xóa `status_1` ngay?
4. Cần đo gì trước/sau khi ẩn index?
5. Chi phí index có thể ảnh hưởng thao tác ghi thế nào?

### Bài 2 — Chi phí insert/update/delete

Collection có `_id_` và năm secondary indexes.

1. Insert một document ảnh hưởng những index nào?
2. Delete một document thì sao?
3. Update field không indexed có nhất thiết thay key của cả năm không?
4. Update field tham gia ba indexes ảnh hưởng gì?
5. Partial index có thể giảm chi phí trong điều kiện nào?

### Bài 3 — ESR và ERS

Query:

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  amount: { $gte: 1000000 }
})
.sort({ createdAt: -1 })
.limit(20);
```

1. Đề xuất index theo ESR.
2. Đề xuất index theo ERS nếu `amount` rất chọn lọc.
3. Benchmark `totalKeysExamined`, sort và latency.
4. Khi nào ERS có thể thắng?
5. Vì sao không có thứ tự key tối ưu cho mọi data distribution?

### Bài 4 — Covered query

Với index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

1. Viết query chỉ trả ba fields đó và không trả `_id`.
2. Dùng explain xem `totalDocsExamined`.
3. Thêm `shippingAddress` vào projection.
4. Điều gì có thể thay đổi ở FETCH?
5. Có nên thêm `shippingAddress` vào index chỉ để covered không?

### Bài 5 — Đọc `$indexStats`

Output:

```text
Index A accesses.ops=0 since 10 minutes ago
Index B accesses.ops=1000 since 90 days ago
Index C accesses.ops=0 since 90 days ago, unique=true
```

1. Index nào có đủ bằng chứng để xóa ngay?
2. Vì sao `since` quan trọng?
3. Hidden index có được cập nhật khi ghi không?
4. Vì sao unique index khác ordinary query index?
5. Metric ở primary có đại diện secondary reads không?

### Bài 6 — Partial index

90% orders có `archived:true`.

1. Tạo partial index `{tenantId,status,createdAt}` chỉ cho `archived:false`.
2. Viết query có thể dùng nó.
3. Viết query không thể dùng vì kết quả sẽ thiếu.
4. Khi `archived:false` chuyển thành true, index maintenance xảy ra thế nào?
5. Tại sao partial filter giúp giảm storage nhưng không bảo đảm nhanh mọi query?

### Bài 7 — Multikey cost

Mỗi document có trung bình 80 tags.

1. Index `{tenantId:1,tags:1}` ảnh hưởng index key count thế nào?
2. Update thêm 20 tags gây chi phí gì?
3. Hãy đo `indexSizes` và benchmark inserts.
4. Có thể dùng một index `{tags:1,otherArray:1}` tùy ý không?
5. Khi nào nên thiết kế lại dữ liệu?

### Bài 8 — Tính throughput từ `opLatencies`

Hai mẫu:

```text
T1: reads.ops=200000
T2: reads.ops=212000
Interval=120 seconds
```

1. Tính reads/s.
2. Nếu server restart ở giữa thì có điều gì?
3. Lấy số này làm HTTP RPS được không?
4. Nếu writes tăng mà reads giảm, đánh giá trade-off ra sao?

### Bài 9 — Ước lượng tổng chi phí

Một index mới:

```text
Giảm read latency 10 ms ở 300.000 reads/ngày
Tăng write latency 1 ms ở 800.000 writes/ngày
Thêm 8 GiB storage
```

1. Tính tổng chênh lệch thời gian theo mô hình đơn giản.
2. Vì sao không suy trực tiếp ra CPU-seconds?
3. Nếu write SLO là 50 ms, cần đo gì?
4. Nếu index unique bắt buộc, quyết định có khác không?
5. Khi workload tăng ba lần, nên thử gì?

### Bài 10 — TTL index ít được đọc

Một index `ttl_expireAt` có `accesses.ops=0`.

1. Có xóa nó không?
2. TTL worker tác động gì tới writes?
3. Khi bulk expiration, metrics nào có thể tăng?
4. TTL có bảo đảm xóa đúng millisecond không?
5. Retention là quyết định kỹ thuật hay business/compliance?

### Bài 11 — Hidden index experiment

1. Chọn một ordinary non-unique non-TTL index ít dùng.
2. Ghi baseline p95/p99.
3. Hidden thử trên staging có tải đại diện.
4. So explain và SLO.
5. Nếu query chậm, unhide.
6. Vì sao hide không đo được write gain sau drop?
7. Vì sao không tự làm thí nghiệm này trên production?

### Bài 12 — Capacity trên replica set

Một collection có index footprint 10 GiB per data-bearing member, replica set ba members.

1. Phân biệt logical và physical index footprint.
2. Tính ước lượng physical copies trước các overhead khác.
3. Disk headroom cho index build cần bao nhiêu?
4. Backup/restore có bắt buộc lưu index theo một cách duy nhất không?
5. Vì sao size trên `stats()` không phải toàn bộ disk usage?

### Bài 13 — Hot shard

Một sharded collection có:

```text
Shard A: 70% writes, CPU 95%
Shard B: 15% writes, CPU 35%
Shard C: 15% writes, CPU 30%
```

1. Thêm một index có thể làm A nặng hơn thế nào?
2. Query targeting/shard key ảnh hưởng gì?
3. Vì sao một index tốt trên từng shard không giải quyết scatter-gather?
4. Metrics nào cần đo theo shard?
5. Nên cân nhắc dữ liệu phân bố lại khi nào?

### Bài 14 — Application N+1

Một API trả 100 orders và chạy thêm một query cho mỗi customer.

1. MongoDB command count mỗi request bao nhiêu?
2. Tại sao thêm index chưa chắc giải quyết p99?
3. Có thể tối ưu data access pattern như thế nào?
4. Cần đo pool wait và network round trips gì?
5. So sánh trước/sau bằng distributed tracing.

### Bài 15 — Tạo benchmark thực tế

Dùng một collection staging với:

- 1 triệu orders;
- 10 tenants có phân bố không đồng đều;
- 70% reads, 30% writes;
- Query Q1/Q2 và update status;
- So ba tập indexes.

Yêu cầu:

1. Ghi dataset generation methodology.
2. Ghi baseline indexes/size.
3. Dùng explain cho mỗi query shape.
4. Đo read/write p95/p99.
5. Đo CPU/disk/cache.
6. Đo index size và build duration.
7. Chọn cấu hình theo SLO và giải thích.

### Bài 16 — Quyết định giữ hay drop

Một index không unique/TTL có:

```text
Accesses gần 0 trong 60 ngày
Size 12 GiB
Insert p99 120 ms, SLO 100 ms
Báo cáo quý có thể dùng index này
```

1. Có thể drop ngay không?
2. Cần hỏi owner báo cáo gì?
3. Hidden index thử giúp xác nhận điều gì?
4. Hidden index không giúp xác nhận điều gì?
5. Thiết kế change window và rollback.
6. Sau drop đo lợi ích viết thế nào?

## 41. Checklist quyết định một index mới

### Trước khi tạo

- [ ] Có query shape cụ thể và owner.
- [ ] Biết tần suất query và business SLO.
- [ ] Có `explain()` trước thay đổi.
- [ ] Đã xem indexes hiện có và prefix overlap.
- [ ] Đã xem field order theo equality/sort/range.
- [ ] Đã đánh giá covered query có đáng không.
- [ ] Đã kiểm tra array/multikey/partial/collation.
- [ ] Có dữ liệu thử đại diện về cardinality và skew.
- [ ] Có baseline read/write p95/p99.
- [ ] Có disk/CPU/cache headroom cho index build.
- [ ] Có kế hoạch tạo index và rollback.

### Sau khi tạo

- [ ] Index build đã hoàn thành.
- [ ] Query planner có dùng index như dự kiến.
- [ ] `keysExamined`/`docsExamined` giảm hợp lý.
- [ ] Read latency/SLO cải thiện.
- [ ] Insert/update/delete latency vẫn đạt mục tiêu.
- [ ] Disk/index size tăng trong budget.
- [ ] Replication lag và background I/O chấp nhận được.
- [ ] Query không được phục vụ bởi index vẫn ổn.
- [ ] Metrics và index inventory được cập nhật.
- [ ] Có owner cho vòng đời index.

## 42. Checklist rà soát index hiện có

- [ ] Liệt kê indexes bằng `getIndexes()`.
- [ ] Đo từng index size bằng stats phù hợp.
- [ ] Đọc `$indexStats` và mốc `since`.
- [ ] Lấy số liệu trên nodes/shards cần thiết.
- [ ] Phân biệt unique/TTL với query-performance indexes.
- [ ] Xem unused indexes qua nhiều chu kỳ workload.
- [ ] Kiểm tra prefix/sort/collation overlap.
- [ ] Đo ảnh hưởng write trên fields indexed.
- [ ] Kiểm tra multikey/index-entry explosion.
- [ ] Xác nhận partial predicate không gây thiếu kết quả.
- [ ] Ẩn thử index ứng viên trên staging khi cần.
- [ ] Có kế hoạch unhide hoặc rebuild.
- [ ] Không drop `_id` hay constraint quan trọng tùy tiện.
- [ ] Theo dõi kết quả sau thay đổi.
- [ ] Có review định kỳ khi query shapes thay đổi.

## 43. Tài liệu chính thức tham khảo

- [MongoDB Indexes Overview](https://www.mongodb.com/docs/manual/indexes/)
- [Create Indexes](https://www.mongodb.com/docs/manual/core/indexes/create-index/)
- [Indexing Strategies](https://www.mongodb.com/docs/manual/applications/indexes/)
- [Write Operation Performance](https://www.mongodb.com/docs/manual/core/write-performance/)
- [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [Equality, Sort, Range Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/)
- [Covered Queries](https://www.mongodb.com/docs/manual/core/query-optimization/)
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/)
- [$indexStats Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexstats/)
- [collStats Command](https://www.mongodb.com/docs/manual/reference/command/collStats/)
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [Wildcard Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-wildcard/)
- [MongoDB Performance Tuning](https://www.mongodb.com/docs/manual/administration/performance-tuning/)
- [MongoDB Atlas Performance Advisor](https://www.mongodb.com/docs/atlas/performance-advisor/)
- [MongoDB Search](https://www.mongodb.com/docs/search/)
- [MongoDB Vector Search](https://www.mongodb.com/docs/vector-search/)

## Kết luận

Cân bằng số index, tốc độ đọc, tốc độ ghi và dung lượng là một **bài toán tối ưu toàn hệ thống**, không phải việc tạo index cho từng field hoặc xóa mọi index có lượt sử dụng thấp.

Một index tốt phải chứng minh được nó phục vụ **query shapes có giá trị** với read latency, sort và số keys/documents examined tốt hơn, đồng thời giữ **insert/update/delete throughput** và **disk/cache footprint** trong giới hạn chấp nhận được. MongoDB phải duy trì index keys khi insert/delete; các updates chỉ ảnh hưởng những indexes liên quan theo giá trị/index membership. Vì vậy chi phí thay đổi theo cấu trúc index, loại dữ liệu và tần suất thay đổi fields.

**Compound indexes**, **covered queries**, **partial indexes** và thiết kế query đúng thường đem lại lợi ích lớn hơn việc tăng số indexes tùy tiện. **Multikey/wildcard indexes** cần được quan sát kỹ vì có thể tạo nhiều keys. **Unique và TTL indexes** còn bảo vệ tính đúng đắn/vòng đời dữ liệu, nên không được xóa chỉ vì `$indexStats` không ghi nhận lượt truy vấn.

Hãy kết hợp `getIndexes()`, `$indexStats`, `stats()/collStats`, `explain("executionStats")`, driver/APM metrics và benchmark đọc/ghi trên workload đại diện. Dùng **hidden indexes** để kiểm tra tác động tới query planner, nhưng nhớ rằng chúng **vẫn tiêu tốn storage và write maintenance**; drop thật cần change window và kế hoạch rebuild/rollback.

**Tập index phù hợp nhất là tập index nhỏ nhất vẫn đáp ứng các SLO đọc, ghi, tính đúng đắn và yêu cầu lưu trữ của hệ thống — được chứng minh bằng measurements, không phải bằng số lượng index.**

