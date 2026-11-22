# Backfill theo lô với giới hạn tốc độ, checkpoint và khả năng chạy lại trong MongoDB

## 1. Bài toán: thêm trường mới cho hàng triệu documents mà ứng dụng vẫn hoạt động

Một hệ thống thương mại điện tử dùng MongoDB để lưu đơn hàng. Schema cũ:

```javascript
{
  _id: ObjectId("673400000000000000000001"),
  tenantId: "shop-a",
  status: "PAID",
  lineItemsRevision: NumberLong("7"),
  lineItems: [
    { sku: "P01", quantity: 2, unitPriceMinor: NumberLong("125000") },
    { sku: "P02", quantity: 1, unitPriceMinor: NumberLong("80000") }
  ],
  createdAt: ISODate("2026-10-01T10:00:00Z")
}
```

Phiên bản ứng dụng mới muốn đọc nhanh **tổng tiền hàng trước phí vận chuyển, thuế và giảm giá**. Nó cần trường `itemsSubtotalMinor`:

```javascript
{
  _id: ObjectId("673400000000000000000001"),
  lineItemsRevision: NumberLong("7"),
  lineItems: [
    { sku: "P01", quantity: 2, unitPriceMinor: NumberLong("125000") },
    { sku: "P02", quantity: 1, unitPriceMinor: NumberLong("80000") }
  ],
  itemsSubtotalMinor: NumberLong("330000"),
  migrations: {
    orderItemsSubtotalV2: {
      version: 2,
      sourceRevision: NumberLong("7"),
      calculatedAt: ISODate("2026-11-14T06:00:00Z")
    }
  }
}
```

Phép tính:

\[
\text{itemsSubtotalMinor} = \sum_{i=1}^{n} \text{quantity}_i \times \text{unitPriceMinor}_i
\]

Ở đây `unitPriceMinor` là đơn vị tiền nhỏ nhất do hệ thống quy định; ví dụ chỉ tính tổng dòng hàng, **không** tự nhận đây là số tiền phải thu cuối cùng. Việc dùng `NumberLong` còn giúp tránh một số sai số của số thực dấu phẩy động. Với số lượng lớn, Java cần kiểm tra overflow bằng `Math.multiplyExact` và `Math.addExact`.

Ứng dụng đang hoạt động 24/7, liên tục tạo và cập nhật orders. Collection có 40 triệu documents. Không thể dừng hệ thống rồi chạy một `updateMany()` tùy tiện mà không quan tâm:

- Nhiều documents có cấu trúc khác nhau hoặc thiếu các trường cũ.
- Một số orders bị chỉnh sửa trong lúc migration chạy.
- Backfill có thể kéo dài nhiều giờ/ngày.
- Có thể mất kết nối giữa một lô ghi.
- Primary có thể chuyển trong lúc chạy.
- Hệ thống production phải giữ độ trễ ghi/đọc ổn định.
- Migration cần dừng, tiếp tục, triển khai lại worker mà không tính tổng tiền hai lần.
- Một lần quét xong chưa chắc mọi document mới hoặc thay đổi đồng thời đã được xử lý.

**Giải pháp:** một backfill **theo lô có kích thước giới hạn**, **pacing/rate limit**, **checkpoint bền vững**, **idempotent updates**, **optimistic concurrency** và **reconciliation** trước khi chuyển toàn bộ traffic sang schema mới.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đặt backfill vào tiến trình **expand → deploy compatible writers → backfill → verify → contract**.
2. Chọn cách scan bằng **keyset pagination**, với thứ tự ổn định và chỉ mục phù hợp.
3. Phân biệt `cursor.batchSize()`, `limit()`, số thao tác trong `bulkWrite()` và giới hạn tốc độ.
4. Chứng minh một phép migration **idempotent** khi chạy lại hoặc nhận cùng batch nhiều lần.
5. Thiết kế **checkpoint high-water mark**, `lastScannedId`, progress state và job ownership.
6. Xử lý crash giữa write và checkpoint theo at-least-once processing.
7. Giữ dữ liệu đúng khi ứng dụng cập nhật cùng document bằng revision/CAS hoặc protocol dual-write phù hợp.
8. Tính throughput, chọn docs/s hoặc bytes/s budget, giảm tải khi latency/replication lag tăng.
9. Viết worker Java Sync Driver xử lý một lô, rate limit và checkpoint với MongoDB.
10. Phân loại lỗi transient/permanent/unknown, đặt retry budget và xử lý poison documents.
11. Đối chiếu tiến độ bằng metrics, kiểm tra sau migration và thiết kế rollback/forward-fix.
12. Phân biệt backfill trên replica set, sharded cluster và Atlas về định tuyến/độ trễ/đảm bảo dữ liệu.

**Phạm vi:** ví dụ tên database `migration_lab_426` dùng cho môi trường kiểm thử. Các lệnh thay dữ liệu trong bài **không được chạy lên production** khi chưa có change plan, backup/PITR, quyền được duyệt và kiểm thử với workload thực.

## 3. Backfill là gì, khác gì migration schema?

**Schema migration** là thay đổi dạng/ý nghĩa dữ liệu mà ứng dụng lưu và đọc. **Backfill** là thao tác điền/cập nhật dữ liệu cũ để phù hợp schema hoặc read model mới.

Ví dụ:

```text
Old:
  orders.lineItems

New:
  orders.lineItems
  orders.itemsSubtotalMinor
  orders.migrations.orderItemsSubtotalV2

Backfill:
  scan old orders
  compute new value
  conditionally write new fields
  verify
```

Backfill khác:

- **Backup/restore:** sao lưu hoặc phục hồi dữ liệu, không nhất thiết biến đổi schema.
- **One-time DDL:** tạo index/validator, có thể cần nhưng không tự điền dữ liệu cũ.
- **Online query transform:** tính trường mới lúc đọc, không lưu kết quả.
- **Change Data Capture (CDC):** phát hiện thay đổi liên tục; có thể hỗ trợ catch-up khi backfill chạy.
- **ETL batch:** chuyển dữ liệu giữa nguồn/đích; nếu chạy trên MongoDB vẫn cần idempotency/checkpoints.
- **Full collection rewrite:** ghi lại toàn bộ document; không phải lựa chọn mặc định khi chỉ cần thêm vài field.

### 3.1. Khi nào không cần backfill?

Nếu trường mới có thể được tính lúc đọc với chi phí chấp nhận được, hoặc chỉ documents mới cần field đó, có thể không cần cập nhật toàn bộ lịch sử.

Ví dụ:

```java
long subtotal = order.containsKey("itemsSubtotalMinor")
    ? order.getLong("itemsSubtotalMinor")
    : computeFromLineItems(order);
```

Read fallback này cho phép triển khai dần; nhưng cần đo chi phí, xác định thời gian giữ fallback và tránh tạo các đường logic khó bảo trì.

### 3.2. Không phải mọi backfill đều an toàn

Backfill xóa field cũ, đổi nghĩa currency, tính sai tax hoặc sửa một bản ghi lịch sử đã chốt có thể gây hại. Trước khi chạy phải xác định semantic của field đích và bằng chứng cách tính.

## 4. Toàn cảnh: expand → backfill → verify → contract

```text
    Phase 0: Plan & backup
              |
              v
    Phase 1: Expand schema
       - app reads old/new
       - add new fields/indexes
       - validators allow transition
              |
              v
    Phase 2: Deploy compatible writers
       - writes maintain new fields
       - source revision changes
       - optional CDC/outbox
              |
              v
    Phase 3: Rate-limited backfill
       - keyset scan
       - CAS update
       - checkpoint after each completed batch
              |
              v
    Phase 4: Reconcile
       - new & concurrently edited docs
       - missing/stale/invalid values
       - DLQ handling
              |
              v
    Phase 5: Verify & switch reads
              |
              v
    Phase 6: Contract
       - require new schema when safe
       - retire old fallback
       - keep rollback evidence
```

### 4.1. Vì sao cập nhật ứng dụng trước backfill?

Nếu worker tính xong subtotal rồi ứng dụng cũ thay `lineItems` mà **không cập nhật subtotal hoặc revision**, dữ liệu mới trở nên sai dù job đã báo hoàn tất.

Do đó cần một trong các chính sách:

1. **Dual-write:** application writers cập nhật trường nguồn và trường mới atomically khi cùng document.
2. **Invalidate-and-recompute:** writer tăng source revision, xóa/đánh dấu computed field stale; worker recompute.
3. **CDC + catch-up:** thu các writes trong và sau snapshot, đảm bảo không có gap rồi cập nhật derived data theo thứ tự/idempotency.
4. **Maintenance freeze** được chấp thuận: tạm ngừng loại thay đổi liên quan; thường khó dùng với hệ thống luôn hoạt động.

### 4.2. Không cắt read fallback quá sớm

Các tài liệu cũ có thể chưa backfill, hoặc đang gặp lỗi poison data. Ứng dụng phải hỗ trợ dữ liệu hỗn hợp trong giai đoạn chuyển tiếp.

### 4.3. Không dùng `status=COMPLETED` thay bằng chứng verify

Job checkpoint chỉ chứng minh đã quét tới một vị trí theo protocol. Nó không tự bảo đảm field mới đúng trên toàn bộ active data hay mọi thay đổi concurrent đã được hợp nhất.

## 5. Bốn đặc tính cần giữ

| Đặc tính | Ý nghĩa trong backfill | Cách đạt được |
|---|---|---|
| **Bounded** | Một lô có giới hạn tài nguyên | `limit()`, bounded bulk, timeout |
| **Throttled** | Không chiếm toàn bộ I/O và write capacity | docs/s, bytes/s, feedback controller |
| **Resumable** | Crash/restart không bắt đầu từ đầu | Durable checkpoint, ordered scan |
| **Idempotent** | Chạy lại không gây double effect | `$set` deterministic, revision CAS, unique IDs |

Ba thuộc tính khác quan trọng:

- **Observable:** biết batch, progress, errors, lag, throughput.
- **Correct under concurrency:** writer đang chạy không bị worker ghi đè.
- **Verifiable:** có phương pháp đối chiếu kết quả cuối.

### 5.1. Exactly-once không tự đến từ checkpoint

Giữa “đã ghi batch” và “đã ghi checkpoint” là hai bước riêng biệt:

```text
worker writes batch
        |
        X process crashes
        |
checkpoint not written
```

Sau restart, batch được xử lý lại. Đây là **at-least-once processing**. Mục tiêu là làm thao tác migration **an toàn khi chạy lại**, không cố giả định batch chỉ thực thi một lần.

### 5.2. “Một lần thực thi” khác “một kết quả cuối đúng”

Hai lần gọi `$set: {itemsSubtotalMinor:330000}` thường không gây tăng gấp đôi, nhưng nếu nguồn đã đổi, ghi lại giá trị cũ vẫn có thể sai. **Idempotency còn cần guard đối với nguồn biến động.**

## 6. Thiết kế schema migration và dữ liệu nguồn

Một order có:

```javascript
{
  _id: ObjectId("673400000000000000000001"),
  tenantId: "shop-a",
  lineItemsRevision: NumberLong("7"),
  lineItems: [
    { sku: "P01", quantity: 2, unitPriceMinor: NumberLong("125000") },
    { sku: "P02", quantity: 1, unitPriceMinor: NumberLong("80000") }
  ]
}
```

Giả định nghiệp vụ:

- `quantity` là số nguyên dương.
- `unitPriceMinor` là số nguyên 64-bit không âm.
- `lineItemsRevision` luôn tăng khi lineItems thay đổi.
- Tất cả writers có thể sửa lineItems đã được cập nhật để tuân thủ quy tắc revision.
- Backfill **không** tự sửa lineItems hay revision.
- `itemsSubtotalMinor` chỉ bằng tổng `quantity × unitPriceMinor`, chưa gồm tax/discount/shipping.
- Các trường mới nằm trong document order nên một single-document update có tính atomic.

### 6.1. Vì sao cần `lineItemsRevision`?

Worker đọc revision=7 và tính tổng. Trong lúc tính, API sửa lineItems và tăng revision=8. Nếu worker dùng:

```javascript
db.orders.updateOne(
  { _id: orderId },
  { $set: { itemsSubtotalMinor: 330000 } }
);
```

worker có thể **ghi đè giá trị hợp lệ** bằng kết quả tính từ dữ liệu cũ.

Với filter revision:

```javascript
db.orders.updateOne(
  {
    _id: orderId,
    lineItemsRevision: NumberLong("7")
  },
  {
    $set: {
      itemsSubtotalMinor: NumberLong("330000"),
      "migrations.orderItemsSubtotalV2.version": 2,
      "migrations.orderItemsSubtotalV2.sourceRevision":
        NumberLong("7")
    },
    $currentDate: {
      "migrations.orderItemsSubtotalV2.calculatedAt": true
    }
  }
);
```

Lệnh chỉ match khi revision vẫn là 7. Nếu revision đã đổi, worker phải **đọc lại rồi tính lại**. Đây là **compare-and-set (CAS)** dựa trên trạng thái nguồn.

### 6.2. CAS chỉ đúng khi mọi writer tăng revision

Nếu một code path sửa `lineItems` nhưng không tăng `lineItemsRevision`, worker không thể phát hiện thay đổi. Không tuyên bố “dùng CAS là đủ” nếu chưa triển khai và kiểm thử invariant của toàn bộ writers.

### 6.3. Document cũ chưa có revision

Trước khi dùng ví dụ CAS, cần mở rộng schema để cấp revision hoặc chuyển sang một protocol khác kiểm soát concurrency.

Không tự cho rằng thiếu `lineItemsRevision` đồng nghĩa revision=0 trên mọi document rồi so `eq("lineItemsRevision",0)`; MongoDB phân biệt missing và số 0. Có thể cần bước stamp revision với điều kiện `$exists:false`, đồng thời điều chỉnh writers.

### 6.4. Dữ liệu lịch sử bất biến

Nếu orders `PAID` là snapshot bất biến và policy không cho sửa lineItems, tính đơn giản hơn. Nhưng phải bảo đảm invariant này bằng thực tế code/permissions, không dựa vào tên `status`.

## 7. Định nghĩa idempotency rõ ràng

Một thao tác `f` idempotent nếu áp dụng lặp lại trên cùng trạng thái nguồn không thay đổi cho cùng trạng thái đích mong muốn:

\[
f(f(x)) = f(x)
\]

### 7.1. An toàn khi lặp

```javascript
// Cùng giá trị từ cùng sourceRevision:
db.orders.updateOne(
  { _id: orderId, lineItemsRevision: NumberLong("7") },
  {
    $set: {
      itemsSubtotalMinor: NumberLong("330000"),
      "migrations.orderItemsSubtotalV2.sourceRevision":
        NumberLong("7")
    }
  }
);
```

Nếu source vẫn revision=7, chạy lại cho cùng kết quả về trường nghiệp vụ.

### 7.2. Không an toàn khi lặp

```javascript
db.orders.updateOne(
  { _id: orderId },
  { $inc: { itemsSubtotalMinor: 330000 } }
);
```

Sau hai lần sẽ cộng 660000, sai nghĩa computed field.

### 7.3. Timestamp có làm mất idempotency không?

`$currentDate` trên `calculatedAt` khiến metadata thay đổi giữa các lần lặp, nhưng không làm subtotal bị nhân đôi. Tuy vậy nếu yêu cầu **bitwise identical state** hoặc audit semantics chặt, cần tránh ghi lại metadata trên những document đã hoàn tất đúng revision.

### 7.4. Marker/version

Một marker có thể ghi:

```javascript
migrations: {
  orderItemsSubtotalV2: {
    version: 2,
    sourceRevision: NumberLong("7"),
    calculatedAt: ISODate("2026-11-14T06:00:00Z")
  }
}
```

Worker có thể bỏ qua khi:

```text
marker.version == 2
AND marker.sourceRevision == order.lineItemsRevision
AND itemsSubtotalMinor có kiểu/giá trị hợp lệ
```

Marker là công cụ tối ưu/reconcile, không thay việc kiểm tra business invariant.

## 8. Backfill bằng `updateMany()`: có phù hợp không?

Một trường mặc định đơn giản:

```javascript
db.orders.updateMany(
  { archived: { $exists: false } },
  { $set: { archived: false } }
);
```

Lệnh này có thể hợp lệ nếu `archived=false` đúng với mọi document thiếu field.

### 8.1. Vì sao không dùng một updateMany cho mọi migration?

Với hàng triệu documents:

- Khó chia nhỏ thời gian và rate limit.
- Khó checkpoint theo vị trí đã xử lý.
- Một số documents cần transform riêng từ nhiều trường.
- Lỗi dữ liệu/validation có thể gây khó theo dõi những document nào cần xử lý lại.
- Với concurrent updates, cần filter/semantics đủ rõ.

### 8.2. `updateMany()` không là một transaction lớn

Mỗi document update đơn lẻ có tính atomic, nhưng `updateMany()` không tự biến cả collection thành một atomic unit. Nếu lệnh bị lỗi giữa chừng, có thể một số documents đã được cập nhật.

### 8.3. Khi nào `updateMany()` vẫn tốt?

- Thay đổi nhỏ, đơn giản, idempotent và có filter chặt.
- Số documents hợp lý và thời gian/throttle không thành vấn đề.
- Có khả năng chạy lại và kiểm chứng.
- Đã hiểu scan/index/write impact.

Không phải cứ migration là bắt buộc viết Java worker phức tạp.

## 9. Chia theo lô: batch cần giới hạn điều gì?

Một worker có thể làm:

```text
Read 100 documents
   |
Compute 100 new values
   |
Write 100 guarded updates
   |
Verify batch outcome
   |
Commit checkpoint
   |
Sleep/pacing
   |
Repeat
```

### 9.1. Những giới hạn khác nhau

| Giới hạn | Đơn vị | Công dụng |
|---|---|---|
| Scan page size | Documents/page | RAM và memory của worker |
| Cursor batch size | Documents/fetch request, tùy server/size | Network round trips |
| Write bulk size | Write models/call | Network overhead và error handling |
| In-flight batches | Batches | Concurrency và backpressure |
| Write rate | Docs/s hoặc ops/s | Đỡ áp lực MongoDB |
| Byte rate | MiB/s | Bảo vệ network/disk |
| Deadline | Seconds | Không giữ resource vô hạn |
| Checkpoint interval | Batches/time | Replay cost sau crash |

**`cursor.batchSize(100)` không tự giới hạn writes ở 100 ops/s.** Nó chỉ ảnh hưởng cách nhận dữ liệu từ cursor.

### 9.2. Ví dụ batch 100

```javascript
db.orders.find({
  _id: {
    $gt: ObjectId("673400000000000000000000"),
    $lte: ObjectId("6734ffffffffffffffffffff")
  }
}).sort({ _id: 1 })
  .limit(100)
  .batchSize(100);
```

Đây là phép đọc; phải có phần tính toán/ghi riêng. Đừng nhầm `limit(100)` với “toàn job chỉ cập nhật 100 documents”.

### 9.3. Kích thước batch động

Ban đầu dùng 100 docs/batch, theo dõi:

- p95/p99 write latency.
- Docs/s thực tế.
- Replication lag.
- CPU/disk IOPS và cache pressure.
- Tỷ lệ conflict/retry.
- Độ lớn document p95/p99.

Nếu quá tải, giảm batch size/concurrency hoặc rate limit; nếu dư capacity có thể tăng có kiểm soát.

## 10. Phân trang bằng `skip()` không thích hợp cho quét lớn

Ví dụ:

```javascript
db.orders.find().sort({ _id: 1 })
  .skip(10000000)
  .limit(100);
```

### 10.1. Vấn đề

- Offset lớn có thể khiến server phải duyệt/bỏ qua nhiều entries.
- Inserts/deletes có thể làm vị trí offset dịch.
- Khi worker restart, một offset số học khó bảo đảm xử lý đúng tài liệu đã quét.

### 10.2. Dùng keyset pagination

```javascript
db.orders.find({
  _id: {
    $gt: lastScannedId,
    $lte: highWatermarkId
  }
}).sort({ _id: 1 }).limit(100);
```

Sau khi xử lý xong batch, checkpoint `lastScannedId` bằng `_id` cuối cùng.

### 10.3. Vì sao `_id` thường phù hợp?

`_id` có unique index mặc định và thường bất biến, cho phép range scan/sort ổn định nếu tất cả documents có **cùng BSON type phù hợp**.

### 10.4. Cạm bẫy BSON type

Nếu collection trộn `ObjectId`, `String`, `NumberLong` làm `_id`, quy tắc thứ tự BSON không tương đương thứ tự thời gian và code `getObjectId("_id")` sẽ lỗi cho loại khác.

Phải chọn đúng key schema thực tế hoặc thiết kế cursor composite. Ví dụ Java phía sau **giả định `_id` là ObjectId**.

## 11. Khi nào dùng composite keyset?

Nếu migrate theo `tenantId` và `createdAt`, nhiều document có cùng timestamp, không nên chỉ checkpoint `createdAt`.

### 11.1. Cặp sort keys

```javascript
db.orders.createIndex({
  tenantId: 1,
  createdAt: 1,
  _id: 1
});
```

Query một tenant:

```javascript
db.orders.find({
  tenantId: "shop-a",
  $or: [
    { createdAt: { $gt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $gt: lastId }
    }
  ]
}).sort({
  createdAt: 1,
  _id: 1
}).limit(100);
```

### 11.2. Checkpoint phải lưu **cả cặp**

```javascript
{
  lastCreatedAt: ISODate("2026-10-01T10:00:00Z"),
  lastId: ObjectId("673400000000000000000001")
}
```

Chỉ lưu `lastCreatedAt` có thể bỏ qua các documents cùng timestamp ở ranh giới.

### 11.3. Nếu sort key thay đổi?

Keyset pagination chỉ an toàn hơn khi **scan key bất biến trong suốt lần quét**. Nếu `createdAt` bị sửa, document có thể chuyển vị trí trước/sau cursor, dẫn đến bỏ sót hoặc quét lặp.

### 11.4. Tenant partitioning

Với nhiều tenants, một checkpoint mỗi tenant/range có thể giúp giới hạn phạm vi, nhưng cần fairness/rate budget tổng và tránh xử lý cùng document bởi nhiều partitions.

## 12. High-water mark: giới hạn phạm vi quét

Trong nhiều backfill dài, nên chốt `highWatermarkId` tại lúc bắt đầu:

```text
Start:
  highWatermarkId = max(_id) observed
  lastScannedId   = null

Each batch:
  _id > lastScannedId
  _id <= highWatermarkId
```

### 12.1. Mục tiêu

- Có ranh giới kết thúc lô quét.
- Dữ liệu mới liên tục sinh sau đó không khiến vòng quét chạy mãi.
- Có thể báo tiến độ đến một cutoff định nghĩa được.

### 12.2. High-water mark không phải snapshot nhất quán

`max(_id)` tại T0 chỉ chốt **giá trị khóa**; nó không đóng băng dữ liệu, không đảm bảo mọi document mới có `_id` lớn hơn cutoff.

Ví dụ một process chèn ObjectId được tạo từ trước, hoặc ứng dụng dùng ID tùy chỉnh có thể chèn document mới với khóa nhỏ hơn cutoff. Khi đó nó nằm trong range cũ nhưng có thể được insert sau khi cursor đi qua vị trí ấy.

### 12.3. Không suy rằng ObjectId là total order của thời điểm commit

ObjectId thường chứa thành phần timestamp và có xu hướng tăng theo thời gian, nhưng không là đồng hồ commit toàn cầu, cũng không chứng minh **một write đã tới DB trước** một write khác.

### 12.4. Cách khép khoảng trống

Phải bổ sung một trong những cơ chế:

- Application writers đảm bảo mọi new/changed documents đã tạo trường đích hợp lệ.
- Một reconciliation pass sau lần quét.
- CDC/change streams với resume token/cutover protocol.
- Cơ chế snapshot/handoff được thiết kế riêng.

High-water mark chỉ là **ranh giới scan**, không phải chứng nhận toàn bộ collection đã migrate.

## 13. Checkpoint: ghi những thông tin nào?

Ví dụ collection `migrationProgress`:

```javascript
{
  _id: "orders-items-subtotal-v2:segment-000",
  migrationVersion: 2,
  collection: "orders",
  state: "RUNNING",
  highWatermarkId: ObjectId("6734ffffffffffffffffffff"),
  lastScannedId: ObjectId("673400000000000000000001"),
  scanKeyType: "ObjectId",
  processedDocuments: NumberLong("10000"),
  matchedUpdates: NumberLong("9980"),
  skippedUpToDate: NumberLong("20"),
  conflictedRetries: NumberLong("7"),
  updatedAt: ISODate("2026-11-14T06:00:00Z"),
  owner: "migration-worker-01",
  leaseEpoch: NumberLong("3")
}
```

### 13.1. Trường thiết yếu

| Field | Vai trò |
|---|---|
| `_id` | Identity cố định của job/segment |
| `migrationVersion` | Phân biệt code logic/version |
| `state` | RUNNING, PAUSED, FAILED, SCAN_DONE, VERIFIED |
| `highWatermarkId` | Ranh giới lần scan |
| `lastScannedId` | Khóa cuối **đã xử lý hoàn tất** |
| `updatedAt` | Quan sát heartbeat/progress |
| `owner/leaseEpoch` | Chống hai workers cùng claim job (nếu triển khai) |

### 13.2. Phân biệt last read và last committed

`lastReadId` chỉ nói đã **đọc** document. `lastScannedId` trong checkpoint đúng phải biểu diễn **đã giải quyết đầy đủ mọi document tới khóa này** theo protocol.

Nếu ghi cursor sau khi đọc nhưng trước khi cập nhật, crash sẽ bỏ qua dữ liệu chưa xử lý.

### 13.3. Checkpoint phải bền vững

Không chỉ giữ `lastScannedId` trong RAM hay file local của một container CI. Ghi vào storage bền vững (thường một MongoDB collection riêng) với write concern phù hợp.

### 13.4. Checkpoint không thay audit

Checkpoint là progress marker. Muốn phân tích ai chạy, image version, tham số, failures và phê duyệt, nên có execution metadata/logs riêng.

## 14. Vị trí ghi checkpoint: sau hay trước batch?

### 14.1. Sai: checkpoint trước

```text
Read batch IDs 101..200
Save lastScannedId=200
Process crashes before writes
Restart begins from 201

=> 101..200 bị bỏ sót.
```

### 14.2. Đúng: checkpoint sau khi hoàn tất

```text
Read batch IDs 101..200
Apply guarded updates
Resolve retries/conflicts
Confirm batch outcome
Save lastScannedId=200

If crash after writes but before checkpoint:
  repeat 101..200 safely.
```

### 14.3. Một batch có 1 lỗi

Nếu 99 documents thành công, 1 document chưa xử lý do lỗi:

- **Không checkpoint qua document lỗi** rồi coi toàn batch hoàn tất.
- Hoặc lưu một **durable retry/DLQ record có identity** và định nghĩa rõ rằng job chưa VERIFIED cho tới khi retry record được giải quyết.

### 14.4. Atomicity giữa data và checkpoint?

Có thể dùng transaction nếu thật sự cần atomic across documents và batch rất nhỏ, nhưng thường không cần biến hàng triệu updates thành các transactions lớn.

Pattern phổ biến là **at-least-once + idempotent guarded updates + checkpoint sau batch**. Dễ phục hồi hơn và tránh transaction overhead dài hạn.

## 15. Checkpoint state machine

```text
PENDING
   |
   v
RUNNING -----> PAUSED
   |             |
   |             +-----> RUNNING
   |
   +---- transient failure -> RETRYING -> RUNNING
   |
   +---- permanent error --> FAILED
   |
   v
SCAN_DONE
   |
   v
RECONCILING
   |
   +---- unresolved issues -> PAUSED/FAILED
   |
   v
VERIFIED
   |
   v
COMPLETED (application cutover approved)
```

### 15.1. State names là contract của ứng dụng

MongoDB không tự có các trạng thái này. Chúng là schema **do migration worker định nghĩa**; cần tránh các bước bỏ qua validation.

### 15.2. `SCAN_DONE` không phải `VERIFIED`

Một scan hoàn tất chỉ nói đã duyệt qua khóa cuối trong cutoff. Cần reconcile writes concurrent, poison records, dữ liệu mới và business invariants.

### 15.3. Pause và resume

Pause nên xảy ra **giữa các batches** hoặc sau khi xử lý/ghi trạng thái an toàn. Nếu dừng ở giữa một batch, restart lặp batch là hợp lệ nếu updates idempotent.

## 16. Ownership và lease khi có nhiều workers

Nếu một scheduler lỗi và chạy hai instances cho cùng job, cả hai có thể lấy cùng checkpoint.

### 16.1. Một cách dùng lease

```javascript
{
  _id: "orders-items-subtotal-v2",
  owner: "worker-A",
  leaseUntil: ISODate("2026-11-14T06:10:00Z"),
  leaseEpoch: NumberLong("4"),
  state: "RUNNING"
}
```

Worker chỉ được claim khi:

- Job chưa có owner **hoặc**
- Lease đã hết hạn theo cơ chế thời gian nhất quán được chọn **hoặc**
- Owner hiện tại renew chính lease của mình.

### 16.2. Vì sao cần fencing token?

Worker A giữ lease rồi mất network, lease hết hạn; B claim lease epoch=5. A tỉnh lại và cố checkpoint, nếu không có kiểm tra epoch, A có thể ghi đè progress của B.

Checkpoint update nên filter:

```javascript
{
  _id: jobId,
  owner: workerId,
  leaseEpoch: expectedEpoch,
  lastScannedId: previousId
}
```

Nếu match=0, worker **mất quyền sở hữu hoặc checkpoint đã đổi**; phải dừng thay vì cập nhật mù.

### 16.3. Lease không chặn mọi stale data write

Lease bảo vệ progress/ownership. Một worker A bị treo rồi tỉnh lại có thể vẫn gửi **data updates** nếu data write không có fencing logic. Idempotent CAS làm giảm nguy cơ, nhưng với side effects cần kiểm soát thêm.

### 16.4. Một worker có thể là đủ

Nếu throughput một worker đáp ứng kế hoạch, giữ single-worker với scheduler lock đơn giản có thể ít rủi ro hơn chia 100 workers. Chỉ parallelize khi có bằng chứng bottleneck.

## 17. Rate limiting: tốc độ phải được chọn theo capacity

Một backfill không nên ăn hết CPU/disk/network chỉ vì có hàng triệu documents cần sửa.

### 17.1. Ba cách đặt budget

| Loại | Ví dụ | Khi hữu ích |
|---|---|---|
| Docs/s | 300 docs/s | Documents kích thước tương đối đồng đều |
| Write ops/s | 100 updates/s | Mỗi operation chi phí gần tương đương |
| Bytes/s | 4 MiB/s | Documents/updates có kích thước rất khác |

Ngoài ra cần **concurrency cap** vì 1.000 updates/s tuần tự khác 1.000 updates/s bắn đồng thời.

### 17.2. Tính thời gian ước lượng

Với 40 triệu documents và tốc độ **300 docs/s duy trì**:

\[
\frac{40{,}000{,}000}{300} \approx 133{,}333 \text{ giây}
\]

Tương đương xấp xỉ **37 giờ** xử lý thuần, chưa tính initial scanning, conflicts, downtime, validation, throttling động hoặc long-tail documents.

Không chốt lịch cutover chỉ dựa trên ước lượng này.

### 17.3. Rate limit khác batch size

```text
batchSize = 100
rateLimit = 300 docs/s

=> Có thể xử lý tối đa khoảng 3 batches/s
   nếu mỗi document cần một write và không có delay khác.
```

Nhưng nếu xử lý batch mất 0,5 giây, throughput thực có thể thấp hơn rate limit. Rate limiter là **trần**, không phải cam kết đạt đúng tốc độ.

### 17.4. Đừng dùng sleep sau 10.000 writes

Một burst lớn rồi ngủ dài có thể gây spikes ở primary/secondary. Thường ưu tiên pacing mượt hơn hoặc token bucket có burst capacity giới hạn.

### 17.5. Đo cả write lag

Backfill ghi lên primary và được replicate, có thể tăng replication lag/oplog pressure. Nếu secondary chậm, cần giảm tốc ngay cả khi p95 writes trên primary vẫn tốt.

## 18. Pacing, token bucket và điều chỉnh tốc độ tự động

### 18.1. Fixed pacing

Giới hạn 200 docs/giây nghĩa trung bình cho phép mỗi document bắt đầu sau khoảng:

\[
\Delta t = \frac{1}{200} = 0.005\,\text{s} = 5\,\text{ms}
\]

Worker một luồng có thể chờ đến mốc tiếp theo trước khi xử lý document. Đây là **pacing**, không phải token bucket đầy đủ.

### 18.2. Token bucket

```text
Tokens are refilled at 200 per second.
Bucket capacity = 50 tokens.
Each processed document consumes 1 token.
No tokens -> wait for refill.
```

Token bucket cho phép burst tối đa bằng capacity, hữu ích khi công việc có độ trễ không đều. Nhưng nếu capacity quá lớn, một burst ghi lớn vẫn gây giật latency.

### 18.3. Global limit và per-worker limit

Nếu có 10 workers, mỗi worker 200 docs/s, cluster có thể nhận tới **2.000 docs/s**, không phải 200.

Để giới hạn toàn hệ thống cần:

- Chia budget theo worker/partition có kiểm soát.
- Hoặc distributed limiter/central scheduler.
- Hoặc feedback controller đo tổng write load.

### 18.4. Adaptive throttling

Một policy đơn giản:

```text
If API write p95 above threshold:
  reduce backfill limit by 50%

Else if replication lag too high:
  reduce backfill limit by 50%

Else if stable for 5 minutes:
  increase by 10%

Never exceed approved max.
```

Đây là **mẫu thiết kế**, không phải ngưỡng dùng nguyên cho mọi production. Dùng hysteresis/cooldown để tránh tăng-giảm liên tục theo nhiễu metrics.

### 18.5. Priority của ứng dụng

Backfill là background maintenance. Khi tài nguyên hạn chế, ưu tiên **user-facing transactions** và giữ error rate/SLO ổn định; migration có thể chạy chậm hoặc pause.

## 19. Không chỉ giảm writes: còn cần kiểm soát reads

### 19.1. Index-friendly scan

```javascript
db.orders.find({
  _id: { $gt: lastScannedId, $lte: highWatermarkId }
}).sort({ _id: 1 }).limit(100);
```

Vì `_id` có index, range/sort này thường có kế hoạch tốt hơn một full scan rồi sort khi dataset lớn; vẫn cần đo `explain("executionStats")` trên dữ liệu thực.

### 19.2. Projection

Nếu giai đoạn scan chỉ cần IDs:

```javascript
db.orders.find(
  { _id: { $gt: lastScannedId, $lte: highWatermarkId } },
  { _id: 1 }
).sort({ _id: 1 }).limit(100);
```

Worker có thể đọc lại từng document theo ID ngay trước CAS. Cách này giảm payload của bước scan nhưng tăng số read calls. Nếu document nhỏ/cold, đọc trực tiếp source fields theo batch có thể hiệu quả hơn.

### 19.3. Quét toàn bộ document vs IDs-only

| Cách đọc | Ưu điểm | Đánh đổi |
|---|---|---|
| ID-only page rồi fetch từng doc | Progress nhẹ, dễ refetch conflict | N+1 reads |
| Page gồm source fields | Ít round trips hơn | Lộ stale gap trước CAS |
| Stream cursor dài | Ít overhead phân trang | Cursor lifecycle, restart khó |
| Batch aggregation pipeline | Offload transform vào server | Phải kiểm soát load/checkpoints |

Không chọn chỉ dựa trên số queries; phải đo network bytes, IOPS, batch duration và CAS conflict.

### 19.4. Secondary reads có thể stale

Đọc nguồn từ secondary để giảm tải primary có thể thấy dữ liệu cũ. CAS revision ở primary vẫn bảo vệ khỏi ghi đè nguồn mới **nếu invariant revision được giữ**, nhưng retry/conflict có thể tăng và việc suy ra tiến độ có thể phức tạp.

Đối với migration đòi cập nhật mới nhất, ưu tiên read strategy nhất quán với correctness requirement; không mặc định chuyển mọi reads sang secondary.

## 20. Bulk writes: ordered và unordered

Java Sync Driver hỗ trợ:

```java
collection.bulkWrite(
    java.util.List.of(
        new com.mongodb.client.model.UpdateOneModel<>(
            com.mongodb.client.model.Filters.eq("_id", id1),
            com.mongodb.client.model.Updates.set("migrated", true)),
        new com.mongodb.client.model.UpdateOneModel<>(
            com.mongodb.client.model.Filters.eq("_id", id2),
            com.mongodb.client.model.Updates.set("migrated", true))
    ),
    new com.mongodb.client.model.BulkWriteOptions()
        .ordered(false)
);
```

### 20.1. `ordered(true)`

Các operations theo thứ tự input; lỗi write có thể làm dừng những operations phía sau. Dễ xác định thứ tự xử lý nhưng có thể kém hiệu quả khi batch lớn hoặc sharded.

### 20.2. `ordered(false)`

Operations có thể được xử lý theo thứ tự khác và nhiều operations không lỗi vẫn được thử ngay cả khi một operation lỗi. Phù hợp khi:

- Mỗi update độc lập.
- Không phụ thuộc thứ tự.
- Có identity và idempotency rõ.
- Có logic phân tích **partial success**.

### 20.3. `bulkWrite()` không tự atomic toàn batch

Nếu một phần thành công rồi connection mất, không thể kết luận toàn batch chưa chạy. Cần kiểm tra trạng thái từng document hoặc chạy lại idempotent operations.

### 20.4. Vì sao không commit checkpoint chỉ dựa vào số matched?

Với filter CAS, `matchedCount=0` có thể có nghĩa:

- Source revision đổi trong lúc worker tính.
- Document bị xóa.
- Dữ liệu đã có marker đúng version.
- Filter schema sai.

Không tự coi “0 matches” là thành công hoặc lỗi chung. Phải quyết định theo invariant.

### 20.5. `updateMany` bên trong bulk vẫn không đảm bảo retryability

Không phải mọi write operation là retryable ở protocol-level; multi-updates thường không có cùng retry semantics với eligible single-document writes. Dù driver tự retry một số lệnh, business-level idempotency vẫn phải được thiết kế riêng.

## 21. Chọn bulk hay từng `updateOne()`?

| Tiêu chí | Từng `updateOne` | `bulkWrite` nhiều `UpdateOneModel` |
|---|---|---|
| Mỗi document cần recompute riêng | Dễ | Vẫn làm được |
| Phân loại conflict theo document | Rất rõ | Phải map index/result |
| Network round trips | Nhiều hơn | Thường ít hơn |
| Ordered/unordered partial success | Đơn giản hơn | Phải xử lý đầy đủ |
| Chặn khi poison document | Dễ | Có thể partial success |
| Throttle mượt theo document | Dễ | Thường theo group |
| Phù hợp high throughput | Phụ thuộc latency | Có thể tốt hơn |

**Chiến lược thực tế:** bắt đầu với worker tuần tự ít phức tạp và tốc độ chậm; nếu network round trips là bottleneck, thêm bulk với các guard vẫn giữ idempotent, theo dõi partial failures và checkpoint semantics.

### 21.1. Batch 100 không bắt buộc bulk 100

Có thể scan 100 IDs, chia thành hai bulks 50, rate limit từng bulk, rồi checkpoint batch scan chỉ khi cả hai bulks đã giải quyết.

### 21.2. Update models không cần sửa cả document

Ưu tiên `$set` các trường mới và marker, không dùng `replaceOne` toàn document nếu không cần. Full replacement từ snapshot cũ dễ làm mất thay đổi ở các fields khác.

## 22. Java Sync Driver: worker single-process có checkpoint bền vững

Phần này cung cấp **mẫu triển khai đầy đủ ở mức single worker**, có những giới hạn công khai:

- Chỉ chạy trên database **`migration_lab_426`**, không phải production.
- Tất cả `orders._id` có type `ObjectId`.
- `lineItemsRevision` là BSON Int64/Java `Long`, luôn tăng khi lineItems bị sửa.
- `lineItems` chứa array documents với `quantity` Int32 dương và `unitPriceMinor` Int64 không âm.
- Application writers đã triển khai dual-write hoặc revision invalidation.
- Worker duy nhất được chạy cho checkpoint `orders-items-subtotal-v2`; cluster-wide lease chưa nằm trong ví dụ.
- Mục tiêu minh họa **200 scanned documents/giây**, một worker/luồng.
- Tất cả cập nhật dữ liệu và checkpoint dùng `WriteConcern.MAJORITY`.
- Retry CAS bounded; các MongoDB exceptions ngoài loại CAS không bị nuốt: job dừng, restart sẽ replay batch.

### 22.1. Java imports và cấu hình

```java
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Updates;
import com.mongodb.client.model.UpdateOptions;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

public final class OrderSubtotalBackfill426 {
    private static final String DB = "migration_lab_426";
    private static final String JOB = "orders-items-subtotal-v2";
    private static final int PAGE_SIZE = 100;
    private static final int MAX_CAS_ATTEMPTS = 8;
    private static final int DOCS_PER_SECOND = 200;

    private final MongoCollection<Document> orders;
    private final MongoCollection<Document> progress;
    private final Pacer pacer = new Pacer(DOCS_PER_SECOND);

    public OrderSubtotalBackfill426(MongoClient client) {
        this.orders = client.getDatabase(DB)
            .getCollection("orders")
            .withWriteConcern(WriteConcern.MAJORITY);
        this.progress = client.getDatabase(DB)
            .getCollection("migrationProgress")
            .withWriteConcern(WriteConcern.MAJORITY);
    }

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI missing");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            new OrderSubtotalBackfill426(client).run();
        }
    }

    // Phần thân lớp tiếp ở các mục sau.
}
```

Các đoạn code ở các mục 22.2–22.7 cần được **ghép thành cùng class** `OrderSubtotalBackfill426`; đây là cách chia trình bày, không phải nhiều class trùng tên trong một file.

### 22.2. Khởi tạo checkpoint một lần

```java
private Document initializeCheckpoint() {
    // Chốt cutoff trước khi bắt đầu scan mới.
    Document latest = orders.find()
        .sort(Sorts.descending("_id"))
        .projection(Projections.include("_id"))
        .limit(1)
        .first();

    if (latest == null) {
        // Ví dụ cho rằng namespace rỗng là no-op có thể báo riêng.
        throw new IllegalStateException(
            "No orders in test namespace; seed test data first");
    }

    ObjectId proposedHigh = latest.getObjectId("_id");

    progress.updateOne(
        Filters.eq("_id", JOB),
        Updates.combine(
            Updates.setOnInsert("migrationVersion", 2),
            Updates.setOnInsert("state", "RUNNING"),
            Updates.setOnInsert("highWatermarkId", proposedHigh),
            Updates.setOnInsert("createdAt", new java.util.Date())
        ),
        new UpdateOptions().upsert(true)
    );

    Document cp = progress.find(Filters.eq("_id", JOB)).first();
    if (cp == null
            || !Integer.valueOf(2).equals(
                cp.getInteger("migrationVersion"))
            || cp.getObjectId("highWatermarkId") == null) {
        throw new IllegalStateException("Invalid checkpoint");
    }
    return cp;
}
```

**Lưu ý:** `setOnInsert` không thay cutoff khi restart, vì checkpoint đã tồn tại; đó là hành vi mong muốn. Trong hệ thống production nên định nghĩa khi collection trống và xử lý khởi tạo status `SCAN_DONE` riêng.

### 22.3. Pacer một luồng

```java
private static final class Pacer {
    private final long nanosBetweenPermits;
    private long nextAllowedNano = System.nanoTime();

    private Pacer(int permitsPerSecond) {
        if (permitsPerSecond <= 0) {
            throw new IllegalArgumentException("Invalid rate");
        }
        nanosBetweenPermits =
            Math.max(1L, TimeUnit.SECONDS.toNanos(1)
                / permitsPerSecond);
    }

    // Không dùng đồng thời từ nhiều luồng.
    void awaitPermit() {
        long now = System.nanoTime();
        long remaining = nextAllowedNano - now;
        if (remaining > 0L) {
            LockSupport.parkNanos(remaining);
        }
        if (Thread.currentThread().isInterrupted()) {
            throw new IllegalStateException(
                "Backfill worker interrupted");
        }
        nextAllowedNano = Math.max(
            System.nanoTime(), nextAllowedNano)
                + nanosBetweenPermits;
    }
}
```

Pacer giới hạn **tốc độ bắt đầu xử lý documents** cho worker một luồng, không phải distributed quota cho MongoDB write ops. Một document conflict có thể tạo nhiều reads; throughput thực còn tùy DB latency. Production nên dùng rate limiter/library được kiểm thử và feedback control.

### 22.4. Tính subtotal có kiểm tra kiểu/overflow

```java
private static long computeSubtotal(Document order) {
    Object raw = order.get("lineItems");
    if (!(raw instanceof List<?> items)) {
        throw new IllegalArgumentException(
            "lineItems missing or not an array");
    }

    long subtotal = 0L;
    for (Object rawItem : items) {
        if (!(rawItem instanceof Document item)) {
            throw new IllegalArgumentException(
                "line item not a Document");
        }

        Integer quantity = item.getInteger("quantity");
        Long unitPrice = item.getLong("unitPriceMinor");

        if (quantity == null || quantity <= 0
                || unitPrice == null || unitPrice < 0L) {
            throw new IllegalArgumentException(
                "Invalid quantity or unit price");
        }

        long lineTotal =
            Math.multiplyExact(quantity.longValue(), unitPrice);
        subtotal = Math.addExact(subtotal, lineTotal);
    }
    return subtotal;
}
```

Khi overflow hoặc data type sai, **dừng và điều tra**, không ép `Double` thành `long` rồi chấp nhận số tiền mất độ chính xác. Điều chỉnh validation cho dữ liệu tiền tệ thực tế (currency, decimal precision, discounts) trước khi áp dụng.

### 22.5. Một document: đọc mới, CAS, retry bounded

```java
private void migrateOne(ObjectId id) {
    for (int attempt = 1; attempt <= MAX_CAS_ATTEMPTS; attempt++) {
        Document current = orders.find(eq("_id", id)).first();

        if (current == null) {
            // Document đã được xóa hợp lệ; không tạo lại.
            return;
        }

        Long revision = current.getLong("lineItemsRevision");
        if (revision == null || revision < 0L) {
            throw new IllegalStateException(
                "Missing/invalid lineItemsRevision for " + id);
        }

        long subtotal = computeSubtotal(current);
        Document migrations = current.get(
            "migrations", Document.class);
        Document marker = migrations == null
            ? null
            : migrations.get("orderItemsSubtotalV2", Document.class);

        boolean upToDate = marker != null
            && Integer.valueOf(2).equals(marker.getInteger("version"))
            && revision.equals(marker.getLong("sourceRevision"))
            && Long.valueOf(subtotal)
                .equals(current.getLong("itemsSubtotalMinor"));

        if (upToDate) {
            return;
        }

        UpdateResult result = orders.updateOne(
            and(
                eq("_id", id),
                eq("lineItemsRevision", revision)
            ),
            combine(
                set("itemsSubtotalMinor", subtotal),
                set("migrations.orderItemsSubtotalV2.version", 2),
                set("migrations.orderItemsSubtotalV2.sourceRevision",
                    revision),
                currentDate(
                    "migrations.orderItemsSubtotalV2.calculatedAt")
            )
        );

        if (result.getMatchedCount() == 1L) {
            return;
        }
        // Source changed concurrently; refetch and recompute.
    }

    throw new IllegalStateException(
        "CAS conflicts exhausted for order " + id);
}
```

**Giới hạn:** sau khi đọc marker là up-to-date, source có thể đổi ngay trước return. **Writers phải duy trì/invalidates derived field** theo quy tắc trong Phase 2; không thể chỉ dựa vào check của worker để đảm bảo vĩnh viễn.

### 22.6. Scan một page, hoàn tất rồi mới checkpoint

```java
private void scanLoop(Document initial) {
    ObjectId high = initial.getObjectId("highWatermarkId");
    ObjectId last = initial.getObjectId("lastScannedId");

    while (true) {
        var range = last == null
            ? lte("_id", high)
            : and(gt("_id", last), lte("_id", high));

        List<Document> batch = orders.find(range)
            .sort(Sorts.ascending("_id"))
            .projection(Projections.include("_id"))
            .limit(PAGE_SIZE)
            .batchSize(PAGE_SIZE)
            .into(new ArrayList<>());

        if (batch.isEmpty()) {
            UpdateResult done = progress.updateOne(
                and(
                    eq("_id", JOB),
                    eq("state", "RUNNING"),
                    eq("lastScannedId", last)
                ),
                combine(
                    set("state", "SCAN_DONE"),
                    currentDate("updatedAt")
                )
            );
            if (done.getMatchedCount() != 1L) {
                throw new IllegalStateException(
                    "Checkpoint ownership changed");
            }
            System.out.println("Scan finished. Reconcile before cutover.");
            return;
        }

        for (Document row : batch) {
            pacer.awaitPermit();
            migrateOne(row.getObjectId("_id"));
        }

        ObjectId end = batch.get(batch.size() - 1)
            .getObjectId("_id");

        UpdateResult saved = progress.updateOne(
            and(
                eq("_id", JOB),
                eq("state", "RUNNING"),
                eq("lastScannedId", last)
            ),
            combine(
                set("lastScannedId", end),
                inc("processedDocuments", batch.size()),
                currentDate("updatedAt")
            )
        );

        if (saved.getMatchedCount() != 1L) {
            throw new IllegalStateException(
                "Checkpoint moved; stop stale worker");
        }

        System.out.println(
            "Checkpoint saved up to " + end.toHexString());
        last = end;
    }
}
```

### 22.7. Điểm vào `run()`

```java
public void run() {
    Document cp = initializeCheckpoint();
    String state = cp.getString("state");

    if ("SCAN_DONE".equals(state)) {
        System.out.println(
            "Already scanned. Run reconciliation/verification.");
        return;
    }
    if (!"RUNNING".equals(state)) {
        throw new IllegalStateException(
            "Job not RUNNING: " + state);
    }

    scanLoop(cp);
}
```

### 22.8. Vì sao code có thể tiếp tục sau crash?

Giả sử:

```text
Checkpoint = _id 100
Worker writes 101..180
Worker crashes before checkpoint 200

Restart:
  reads 101..200 again
  101..180 already have valid version+revision marker -> skip
  181..200 processed
  checkpoint moves to 200
```

Không có double increment vì worker dùng `$set` derived value và CAS.

### 22.9. Khi nào checkpoint **không** được ghi?

- Dữ liệu đầu vào không hợp lệ.
- Overflow khi tính tiền.
- Hết số lần CAS retry.
- MongoDB write error/timeout không được giải quyết.
- Một document trong batch chưa xác nhận hoàn tất.
- Job state/ownership thay đổi.

Trong các tình huống này, worker fail và batch được replay khi khởi động lại; không bỏ qua poison document trừ khi có durable exception process được định nghĩa.

### 22.10. Những giới hạn cần bổ sung trước production

Mẫu trên cố ý **không** có:

- Distributed lease/fencing cho nhiều workers.
- Durable per-document DLQ.
- Adaptive rate limit/global budget.
- Incremental CDC catch-up.
- Cancellation hook và graceful pause command.
- Detailed metrics/histograms.
- Configurable checkpoint namespace/run manifest.
- Background reconciliation.
- Handling cho `_id` không phải ObjectId.
- Empty-collection no-op state.
- Recovery sau `SCAN_DONE` nếu còn concurrent/new documents.

Nó là **nền tảng minh họa an toàn theo giả định**, không phải script production-ready có thể sao chép mà bỏ qua preflight.

## 23. Seed dữ liệu thử cho Java worker

Chỉ trong database lab mới, ví dụ:

```javascript
use migration_lab_426;

db.orders.insertMany([
  {
    _id: ObjectId("673400000000000000000001"),
    tenantId: "shop-a",
    lineItemsRevision: NumberLong("1"),
    lineItems: [
      {
        sku: "P01",
        quantity: 2,
        unitPriceMinor: NumberLong("125000")
      },
      {
        sku: "P02",
        quantity: 1,
        unitPriceMinor: NumberLong("80000")
      }
    ]
  },
  {
    _id: ObjectId("673400000000000000000002"),
    tenantId: "shop-b",
    lineItemsRevision: NumberLong("3"),
    lineItems: [
      {
        sku: "P09",
        quantity: 3,
        unitPriceMinor: NumberLong("90000")
      }
    ]
  },
  {
    _id: ObjectId("673400000000000000000003"),
    tenantId: "shop-a",
    lineItemsRevision: NumberLong("2"),
    lineItems: []
  }
]);
```

Kết quả mong đợi:

| ID cuối | Subtotal |
|---|---:|
| ...001 | 330000 |
| ...002 | 270000 |
| ...003 | 0 |

### 23.1. Không reset bằng drop trên database không rõ owner

Đây là lab seed. Nếu database `migration_lab_426` đã có dữ liệu của đồng nghiệp, **không** dùng `dropDatabase()` tùy tiện. Tạo namespace mới theo run hoặc dùng test container cô lập.

### 23.2. Kiểm tra marker

```javascript
db.orders.find(
  {},
  {
    lineItemsRevision: 1,
    itemsSubtotalMinor: 1,
    "migrations.orderItemsSubtotalV2": 1
  }
).sort({ _id: 1 });
```

### 23.3. Khởi động lần hai

Sau lần chạy hoàn tất scan, start worker lại sẽ nhìn state `SCAN_DONE`. Để kiểm tra replay **giữa batch**, dùng fault-injection lab trước checkpoint và khôi phục bằng process mới; không sửa trực tiếp `state` của production checkpoint để tạo test.

## 24. Nếu cần chạy lại toàn job sau khi SCAN_DONE

Một cách thiết kế **không xóa checkpoint cũ** là tạo **runId mới**:

```text
orders-items-subtotal-v2:run-2026-11-14-a
orders-items-subtotal-v2:run-2026-11-16-reconcile
```

### 24.1. Vì sao giữ run history?

Giúp audit:

- Cutoff mỗi lần.
- Số documents đã xử lý.
- Thời gian bắt đầu/kết thúc.
- Code version/checksum.
- Lỗi và quyết định bỏ qua.
- Chứng cứ reconciliation/cutover.

### 24.2. Chạy lại cùng migration không đồng nghĩa chạy lại cùng checkpoint

Một run `SCAN_DONE` có thể cần reconciliation trên dataset hiện tại; tạo run mới/quét theo predicate marker missing/stale sẽ phù hợp hơn việc “rewind” checkpoint production mà không rõ effect.

### 24.3. Idempotent update vẫn là nền tảng

Run mới phải không double count hoặc ghi đè dữ liệu mới. Một checkpoint mới không tự tạo correctness; semantics được giữ bởi deterministic transform, revision và writer protocol.

## 25. CAS conflict và cách giải quyết

### 25.1. Timeline

```text
T0 worker reads order revision=7, subtotal=330000
T1 API updates lineItems, revision=8, subtotal=350000
T2 worker update where revision=7 -> matchedCount=0
T3 worker refetch revision=8
T4 worker compute subtotal=350000
T5 worker CAS where revision=8 -> success
```

### 25.2. Vì sao không bỏ qua conflicts ngay?

Nếu cứ gặp `matchedCount=0` là tăng `lastScannedId`, document có thể chưa có derived field tương ứng với revision mới.

### 25.3. Chiến lược

1. Refetch/recompute bounded.
2. Nếu document bị xóa, phân loại deleted hợp lệ.
3. Nếu biến đổi quá thường xuyên, hoãn và ghi durable retry ID.
4. Đừng chờ vô hạn một hot document rồi giữ job mãi.
5. Reconcile đủ những deferred IDs trước khi `VERIFIED`.

### 25.4. “Hot” source

Một document được cập nhật hàng trăm lần/giây có thể tạo CAS conflicts liên tục. Có thể tách field nóng, dùng application dual-write, hoặc chuyển riêng work item sang queue có policy, không tăng attempts vô hạn.

## 26. Poison documents và durable retry queue

Một document gây lỗi:

```javascript
{
  _id: ObjectId("673400000000000000000004"),
  lineItemsRevision: NumberLong("2"),
  lineItems: [
    { quantity: "many", unitPriceMinor: "100000" }
  ]
}
```

Java `getInteger("quantity")` không đúng type; migration không nên tự parse `"many"` thành số tùy đoán.

### 26.1. Hai chế độ vận hành

**Fail-fast:** dừng batch ngay, checkpoint không tiến. Ưu điểm: không bỏ sót, dễ giữ invariant.

**Continue-with-DLQ:** ghi durable record mô tả document ID, error category, retry policy, source revision. Chỉ khi DLQ write **được xác nhận** và policy cho phép mới tiến checkpoint.

### 26.2. Ví dụ DLQ schema

```javascript
{
  _id: "orders-items-subtotal-v2:673400000000000000000004",
  jobId: "orders-items-subtotal-v2",
  documentId: ObjectId("673400000000000000000004"),
  sourceRevision: NumberLong("2"),
  reasonCode: "INVALID_LINE_ITEM_TYPE",
  attempts: 1,
  state: "OPEN",
  recordedAt: ISODate("2026-11-14T06:30:00Z")
}
```

### 26.3. Đừng log toàn raw document vào DLQ

Document có thể chứa thông tin cá nhân, giá, địa chỉ, secret. Ghi ID, reason code và metadata đã kiểm soát; nếu cần payload bảo mật, áp RBAC/retention nghiêm.

### 26.4. Durable enqueue không tự atomic với checkpoint

Nếu DLQ record ghi xong nhưng checkpoint chưa ghi, worker có thể xử lý lại, nên dùng deterministic DLQ ID/upsert. Nếu checkpoint ghi xong khi DLQ record chưa bền vững, ta mất work item.

### 26.5. Không đánh dấu VERIFIED với DLQ còn OPEN

“Scan xong 40 triệu docs” không đồng nghĩa migration hoàn tất nếu có 200 poison records chưa được xử lý/waive theo phê duyệt.

## 27. Lỗi mạng, retryable writes và kết quả chưa chắc chắn

### 27.1. Lỗi xảy ra ở nhiều bước

```text
Fetch document
Compute value
Send update
Wait for majority
Receive response
Save checkpoint
```

Lỗi ở bước nào có ảnh hưởng khác nhau:

- Không đọc được: chưa thực hiện data update.
- Validation failed: phải sửa dữ liệu/logic.
- Connection mất sau gửi update: **có thể đã ghi**.
- Majority write concern timeout: write có thể đã áp dụng nhưng chưa đạt acknowledgement trong thời hạn.
- Checkpoint timeout: checkpoint có thể đã được ghi; phải đọc lại trước khi quyết định.

### 27.2. Driver retryable writes

MongoDB driver có protocol retryable writes cho những eligible single-document write operations trên topology hỗ trợ. Nhưng không phải mọi command/bulk case đều được retry tự động giống nhau.

### 27.3. Vì sao backfill vẫn cần idempotency?

Process crash, scheduler chạy lại hoặc business retry mới có thể diễn ra **bên ngoài driver retry protocol**.

### 27.4. `UnknownTransactionCommitResult`

Nếu chọn transaction cho một phần migration, commit response bị mất không chứng minh transaction chưa commit. Phải xử lý retry commit theo transaction API, tránh chạy lại side effects không idempotent.

### 27.5. Backoff có giới hạn

Policy ví dụ:

```text
attempts <= 5
initial delay 200 ms
exponential backoff
random jitter
total request deadline
retry only classified transient failures
```

Không áp cố định các con số vào production. Quan trọng là **có deadline/budget**, và không retry validation/permission errors vô hạn.

## 28. Tính nhất quán khi có ghi đồng thời

Vấn đề chính của online backfill:

```text
Worker snapshot of document at T0
Application updates source at T1
Worker writes derived fields at T2
```

### 28.1. Các lựa chọn

| Chiến lược | Ưu điểm | Rủi ro |
|---|---|---|
| Application dual-write | Derived field được cập nhật cùng business write | Phải thay tất cả writers |
| Revision + worker recompute | Ngăn worker ghi đè source mới | Cần quy tắc tăng revision |
| Change streams catch-up | Bù thay đổi trong lúc scan | Token/oplog/idempotency |
| Freeze updates | Dễ tạo snapshot logic | Có thể gây downtime |
| Chuyển đổi tại read time | Không cần migrate ngay | Read cost/fallback lâu dài |

### 28.2. Ví dụ dual-write atomic

Nếu API đã tính lại subtotal từ lineItems mới:

```javascript
db.orders.updateOne(
  {
    _id: orderId,
    lineItemsRevision: NumberLong("7")
  },
  {
    $set: {
      lineItems: newLineItems,
      itemsSubtotalMinor: newSubtotal
    },
    $inc: { lineItemsRevision: NumberLong("1") },
    $unset: { "migrations.orderItemsSubtotalV2": "" }
  }
);
```

Các thay đổi trên cùng document được thực hiện atomically. Bỏ marker có thể khiến backfill quét lại và đóng dấu revision mới; hoặc application cũng có thể ghi marker version=2/sourceRevision mới trong cùng update nếu đã hoàn toàn tin tưởng code mới.

### 28.3. Không dual-write bằng hai independent writes nếu cần atomic

```javascript
// Không đủ an toàn nếu readers cần hai trường đồng bộ ngay.
db.orders.updateOne({ _id: orderId }, { $set: { lineItems: newItems } });
db.orders.updateOne({ _id: orderId }, { $set: { itemsSubtotalMinor: newTotal } });
```

Giữa hai lệnh có thể xảy ra lỗi/network split; readers thấy giá trị không đồng bộ. Dùng cùng một `updateOne` khi các trường ở cùng document và nghiệp vụ cho phép.

### 28.4. Recompute từ source-of-truth

Nếu derived value sai, recompute từ `lineItems` authoritative; không cố “trừ bù” một tổng không rõ đã tăng bao nhiêu lần.

## 29. Change streams cho catch-up sau backfill

Nếu ứng dụng còn writers chưa dual-write hoặc cần tái cấu trúc sang collection khác, có thể phối hợp backfill với CDC.

### 29.1. Vấn đề gap

```text
T0 begin backfill
T1 app updates order #42
T2 backfill scans #42 before/after T1 unpredictably
T3 backfill ends
```

Không có cơ chế bàn giao, một phần changes có thể bị bỏ lỡ.

### 29.2. Protocol khái niệm

1. Khởi tạo change stream hoặc xác định resume/start point **trước khi dữ liệu có thể thay đổi vượt quá điểm chụp**.
2. Lưu resume token/checkpoint trong store bền vững theo semantics phù hợp.
3. Chạy backfill theo bounded pages.
4. Tiếp tục xử lý các change events liên quan, idempotent theo document/revision.
5. Chạy catch-up tới mốc đã xác định, kiểm tra data parity và event lag.
6. Cut over readers khi không còn gap, rồi duy trì writer/CDC hoặc đổi write path.

### 29.3. Resume token không tồn tại mãi

Change streams cần oplog history đủ để resume từ token. Nếu worker nghỉ lâu hơn oplog window, resume có thể thất bại; phải có phương án re-snapshot/reconciliation, không đơn giản tăng retry count.

### 29.4. Không dùng token của event chưa apply

Nếu lưu token rồi crash trước khi apply event vào target, resume sau token đó có thể **bỏ mất event**. Checkpoint event progress **sau khi side effect đã được xác nhận**, hoặc dùng transaction/atomicity appropriate.

### 29.5. At-least-once event processing

Nếu apply event thành công nhưng chưa lưu token, consumer có thể xử lý lại. Vì vậy target update phải idempotent/revision-aware.

### 29.6. CDC không tự tạo total order của mọi target business updates

Xử lý song song, network retries, sharded topology và multiple partitions có thể gây arrival ordering khác. Cần source revision/sequence theo domain nếu correctness đòi thứ tự.

## 30. High-watermark scan kết hợp CDC: hai luồng tiến độ

Một thiết kế rõ:

```text
Scan progress:
  highWatermarkId = ...
  lastScannedId   = ...
  scanState       = SCAN_DONE

CDC progress:
  resumeToken     = ...
  lastAppliedRev  = per document
  changeLag       = ...

Cutover:
  Scan complete
  AND CDC caught up
  AND validation passing
  AND no unresolved DLQ
```

### 30.1. Không gộp ObjectId và resume token thành một khóa

`lastScannedId` là checkpoint của **keyset scan**. `resumeToken` là token của **change stream**. Hai thứ có semantics hoàn toàn khác nhau.

### 30.2. Chọn source of truth

Nếu source là `orders.lineItems`, kết quả từ CDC và batch đều phải được xác định bởi cùng rule transform; tránh batch tính subtotal theo version A, stream consumer tính theo version B.

### 30.3. Chống stale update

Target có thể lưu `sourceRevision` để chỉ accept update khi revision mới hơn trạng thái đã materialize. Nếu revision có thể reset/reuse, phải thêm epoch/version nguồn.

### 30.4. “CDC lag = 0” chưa chắc toàn bộ data đúng

Consumer có thể bắt kịp events nhưng batch còn chưa quét xong, hoặc có poison events bị DLQ. Cần đủ điều kiện kết hợp.

## 31. Backfill sang collection mới và deterministic IDs

Không phải migration nào cũng update cùng document. Ví dụ tách search read model:

```text
orders (source)
   |
   v
orderSummaries (target)
```

### 31.1. Upsert theo key ổn định

```javascript
db.orderSummaries.updateOne(
  { _id: sourceOrder._id },
  {
    $set: {
      tenantId: sourceOrder.tenantId,
      itemsSubtotalMinor: computedSubtotal,
      sourceRevision: sourceOrder.lineItemsRevision
    }
  },
  { upsert: true }
);
```

Stable `_id` giúp retry không tạo hai summary documents cho một order.

### 31.2. Cẩn thận stale overwrite

Nếu CDC cập nhật target revision=9, một batch đọc source revision=7 chạy muộn rồi `$set` target revision=7 có thể ghi đè state mới.

Phải có **conditional target update** dựa trên version hoặc sequencing policy:

```javascript
db.orderSummaries.updateOne(
  {
    _id: sourceOrder._id,
    $or: [
      { sourceRevision: { $lt: sourceOrder.lineItemsRevision } },
      { sourceRevision: { $exists: false } }
    ]
  },
  {
    $set: {
      sourceRevision: sourceOrder.lineItemsRevision,
      itemsSubtotalMinor: computedSubtotal
    }
  }
);
```

Ví dụ này chỉ cho **existing target documents**, không dùng upsert khi filter chứa revision predicate khác `_id` mà không xử lý unique conflicts và concurrent insert semantics.

### 31.3. Cách insert + conflict

Một protocol có thể:

1. Thử insert với deterministic `_id`.
2. Nếu duplicate key, đọc target current revision.
3. Chỉ update nếu sourceRevision mới hơn.
4. Dùng CAS trên target revision để tránh race.

### 31.4. Không đổi _id mỗi lần chạy

`insertOne({_id:ObjectId(), ...})` trong mỗi replay tạo bản sao mới. Khi migrate sang collection khác, identity deterministic là một phần quan trọng của idempotency.

### 31.5. Xóa nguồn và tombstone

Nếu source doc bị xóa sau khi batch đọc, target có thể trở thành orphan. Cần CDC delete propagation/tombstones hoặc periodic reconciliation; không chỉ xử lý inserts/updates.

## 32. Checkpoint ở collection riêng hay cùng collection nguồn?

| Cách | Ưu điểm | Hạn chế |
|---|---|---|
| `migrationProgress` riêng | Dễ theo dõi, phân quyền, atomic update một document | Cần bảo vệ ownership |
| Marker trên từng source doc | Biết document đã migrate chưa | Không có global cursor/throughput |
| Durable work queue per ID | Chia nhỏ/retry poison docs | Tốn storage/coordination |
| External orchestrator checkpoint | Có sẵn scheduler/leases | Cần nhất quán với MongoDB writes |

### 32.1. Kết hợp hai tầng

Một thiết kế thực dụng:

- **Global/segment checkpoint:** `lastScannedId` để resume scan.
- **Per-document marker:** sourceRevision/version để skip và detect stale.
- **DLQ/retry:** durable IDs chưa giải quyết.
- **Verification report:** business invariants và remaining count.

### 32.2. Không phụ thuộc chỉ vào marker

Query mỗi lần trên predicate `"migrations.orderItemsSubtotalV2.version": {$ne:2}` có thể không tận dụng index nếu không thiết kế phù hợp và có thể bỏ sót documents revision mới nhưng marker version cũ còn 2.

### 32.3. Index marker nếu cần

Index phục vụ queue các documents chưa migrate có thể hữu ích, nhưng index trên field bị thay đổi hàng triệu lần cũng tạo write amplification. Đo query shape và planned index drop/retention.

## 33. Sharded cluster: scan, routing và checkpoint

### 33.1. Shard key quan trọng

Trong sharded collection, một query chỉ có range `_id` nhưng thiếu shard key có thể thành scatter-gather qua nhiều shards. Không giả định `_id` mặc định giúp target một shard.

### 33.2. Partition theo shard/tenant

Một chiến lược:

```text
worker-1: tenant range A–F
worker-2: tenant range G–M
worker-3: tenant range N–Z
```

Nhưng tenant sizes có thể rất lệch; cần xem skew, shard key distribution và per-worker rate budget.

### 33.3. Checkpoint per partition

```javascript
{
  _id: "subtotal-v2:tenant-shop-a",
  tenantId: "shop-a",
  highWatermarkId: ObjectId("6734ffffffffffffffffffff"),
  lastScannedId: ObjectId("673400000000000000000001"),
  state: "RUNNING"
}
```

Mỗi partition phải không overlap hoặc có idempotent protocol đủ an toàn khi overlap.

### 33.4. Rebalancing và chunk migrations

Chunk movement không tự động làm keyset scan sai, nhưng có thể ảnh hưởng latency và targeting. Cần đánh giá behavior khi balancer hoạt động; không tự disable balancer production chỉ vì worker thấy chậm.

### 33.5. Không tự thêm sharding cho collection checkpoint

Checkpoint thường ít documents, có thể lưu collection riêng tùy deployment; nếu sharded, unique/transaction constraints phải được cân nhắc. Chọn schema theo ownership/scale.

## 34. Write concern, read concern và dữ liệu đã được xác nhận

### 34.1. Data write vs checkpoint write

Nếu update data chỉ `w:1` rồi checkpoint `w:"majority"`, primary mất có thể rollback data write chưa majority committed nhưng checkpoint vẫn đã majority acknowledged.

Kết quả: checkpoint trỏ qua một document mà actual data update không còn.

### 34.2. Lựa chọn trong ví dụ

Java worker dùng:

```java
MongoCollection<Document> orders = client.getDatabase("migration_lab_426")
    .getCollection("orders")
    .withWriteConcern(com.mongodb.WriteConcern.MAJORITY);

MongoCollection<Document> progress = client.getDatabase("migration_lab_426")
    .getCollection("migrationProgress")
    .withWriteConcern(com.mongodb.WriteConcern.MAJORITY);
```

Mục tiêu là không coi checkpoint bền vững hơn data writes mà nó đại diện. Đây không phải bảo đảm snapshot multi-document; mỗi update riêng vẫn là một operation.

### 34.3. Write concern timeout

Nếu `w:"majority"` chưa được đáp ứng trong timeout, lệnh **có thể đã áp dụng** trên primary. Worker không được checkpoint batch như đã thành công cho tới khi outcome được xử lý.

### 34.4. Read concern

Read concern phù hợp phụ thuộc yêu cầu correctness, lag và transaction/snapshot design. `readConcern:"majority"` có thể giúp đọc dữ liệu majority-committed, nhưng **không biến nhiều queries thành cùng một snapshot**.

### 34.5. Transaction cho từng batch?

MongoDB hỗ trợ multi-document transactions; nhưng transaction hàng nghìn documents kéo dài có overhead và khả năng conflict. Không lấy atomicity làm lý do để biến toàn bộ 40 triệu updates thành một transaction.

## 35. Quan sát tiến độ: processed khác modified

Một backfill có thể đọc 100.000 documents nhưng chỉ cập nhật 20.000 vì 80.000 đã có marker đúng. Vì vậy cần tách metrics:

| Metric | Đơn vị | Ý nghĩa |
|---|---|---|
| `scanned_docs_total` | Docs | Đã đọc/duyệt qua |
| `updated_docs_total` | Docs | Đã thay đổi thực |
| `already_current_docs_total` | Docs | Đã hợp lệ, không cần sửa |
| `deleted_docs_total` | Docs | Không còn document khi refetch |
| `cas_conflicts_total` | Attempts | Lỗi match do revision đổi |
| `retried_docs_total` | Docs | Document được thử lại |
| `poison_docs_total` | Docs | Không tính/validate được |
| `dlq_open` | Docs | Còn chờ giải quyết |
| `checkpoint_advances_total` | Batches | Checkpoint commit thành công |
| `batch_duration_seconds` | Seconds | Thời gian xử lý một batch |
| `actual_docs_per_second` | Docs/s | Throughput thực |
| `throttle_sleep_seconds` | Seconds | Thời gian worker tự giảm tốc |
| `estimate_remaining_docs` | Docs | Ước lượng, có sai số |
| `verification_mismatches` | Docs | Source/target không khớp |

### 35.1. `matchedCount` không đồng nghĩa `modifiedCount`

Trong một write, một document match filter nhưng giá trị được set giống hệt có thể trả `matchedCount=1`, `modifiedCount=0`. Đừng cộng “đã sửa” bằng `matchedCount` khi reporting chính xác số modified.

### 35.2. Throughput tức thời vs trung bình

Một dashboard nên hiển thị docs/s gần nhất và tổng lượng theo thời gian. Nếu worker bị throttled vào giờ cao điểm, trung bình cả ngày có thể che đoạn giảm tốc.

### 35.3. ETA không là cam kết

```text
ETA ≈ remaining estimated documents / recent processed docs/sec
```

ETA đổi khi traffic ứng dụng, conflicts, dữ liệu lớn, replication lag và số workers thay đổi.

### 35.4. Checkpoint stagnation

Nếu `lastScannedId` không đổi 20 phút trong khi worker vẫn gửi heartbeat, có thể:

- Một poison document chặn batch.
- CAS conflict trên hot document.
- Network retry kéo dài.
- Wait limiter đang quá thấp.
- Checkpoint ownership lost.

Không mặc định nâng rate để chữa mọi stagnation; phải xem nguyên nhân.

## 36. Metrics từ MongoDB phải đặt cạnh application SLO

Backfill có thể “chạy đúng” nhưng gây hại API production. Dashboard cần ghép:

```text
+---------------------------------------------------+
| Backfill dashboard                                |
+---------------------------------------------------+
| progress: lastScannedId / highWatermarkId         |
| scanned, updated, skipped, failed, DLQ            |
| actual docs/sec, batch duration, throttled time   |
+---------------------------------------------------+
| MongoDB                                           |
| primary CPU, WiredTiger cache, disk IOPS          |
| network throughput, write concern latency        |
| replication lag, oplog window, flow control       |
| slow queries, connections, write errors           |
+---------------------------------------------------+
| Application                                       |
| API p95/p99 latency, error rate, checkout failures|
| queue depth, request timeouts, business SLO       |
+---------------------------------------------------+
```

### 36.1. Replication lag

Nếu write bursts từ backfill khiến secondaries theo không kịp, lag tăng. Trong hệ thống dùng secondary reads/CDC, tác động có thể xuất hiện ở nơi khác dù primary vẫn còn khỏe.

### 36.2. Oplog window

Backfill tạo nhiều oplog entries (nếu documents được cập nhật). Khi tốc độ oplog tăng, window hiệu dụng có thể co; change stream consumers và secondary đang offline có ít headroom hơn.

### 36.3. Disk/cache

Range scan đọc lượng lớn dữ liệu lạnh và write updates có thể làm thay đổi cache residency, tăng disk reads/evictions và ảnh hưởng query hot. Không chỉ quan sát CPU.

### 36.4. Command monitoring

Java Driver `CommandListener` và `ConnectionPoolListener` có thể cho biết command duration, pool wait, retries; tránh log raw BSON payload chứa PII.

### 36.5. Dùng stable labels

Metrics labels: migration ID, collection đã allowlist, result, error family, partition. Tránh dùng mỗi document ID, tenantId không giới hạn, raw exception message làm Prometheus labels.

## 37. Preflight trước khi chạy production

### 37.1. Business contract

1. Định nghĩa chính xác giá trị trường mới, kể cả edge cases.
2. Có schema compatibility cho ứng dụng cũ/mới.
3. Xác nhận source-of-truth và ai có quyền cập nhật.
4. Có version/epoch tăng đơn điệu trên mọi source write path.
5. Có policy cho deleted documents, archived records và invalid source.
6. Có cách verify độc lập với migration worker.
7. Có rollback/forward-fix.

### 37.2. MongoDB readiness

1. Backup/PITR theo chính sách và đã diễn tập restore.
2. Cluster healthy, không có election/recovery bất thường.
3. Secondary replication lag và oplog window đáp ứng SLO.
4. Đủ disk/headroom cho tăng kích thước data/index/oplog.
5. Query scan có index phù hợp, `explain` không quá tốn.
6. Write concern và checkpoint durability được định nghĩa.
7. Chỉ có quyền tối thiểu cho collections cần đọc/ghi.

### 37.3. Worker readiness

1. Deploy image version/code SHA đã pin.
2. Chốt job ID, cutoff policy, batch size, global rate budget.
3. Có operator owner, maintenance window hoặc thời gian nền được chấp thuận.
4. Có pause/resume/stop và không checkpoint khi partial failure.
5. Có metrics, logs an toàn và alerts.
6. Có DLQ/reconciliation policy.
7. Có stress test và crash/restart test trên môi trường tương tự.

### 37.4. Stop conditions phải định trước

Không tự quyết “chờ xem thêm” khi API error rate vượt SLO hoặc replication lag tăng liên tục. Đặt ngưỡng dừng/giảm tốc trước khi khởi chạy và xác định ai được đổi ngưỡng.

## 38. Dry-run: đo trước khi ghi

### 38.1. Dry-run đúng nghĩa

Một chế độ dry-run có thể:

- Quét một subset đại diện.
- Tính giá trị target trong RAM.
- Validate type/overflow/business rules.
- Đếm số documents cần sửa.
- Báo kích thước write dự kiến.
- **Không gửi update/data checkpoint như đã thực hiện.**

### 38.2. Vì sao cần đại diện cho dữ liệu outlier?

Sampling ngẫu nhiên có thể bỏ qua tài liệu lớn hoặc một tenant có schema cũ. Nên cố ý bao gồm:

- Những documents cũ nhất.
- Những documents mới.
- Những documents có mảng lineItems dài.
- Những tenant lớn và nhỏ.
- Những documents từng qua schema version trung gian.
- Những giá trị missing/null/sai type.

### 38.3. Dry-run không chứng minh write performance

Đọc/tính toán không có chi phí index maintenance/oplog/replication của writes. Cần chạy **canary write** với giới hạn tốc độ thấp để đo tác động thật.

### 38.4. Thống kê schema trước

```javascript
db.orders.aggregate([
  {
    $project: {
      lineItemsType: { $type: "$lineItems" },
      revisionType: { $type: "$lineItemsRevision" },
      subtotalType: { $type: "$itemsSubtotalMinor" }
    }
  },
  {
    $group: {
      _id: {
        lineItemsType: "$lineItemsType",
        revisionType: "$revisionType",
        subtotalType: "$subtotalType"
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

Đây là aggregation đọc collection, có thể đắt trên dữ liệu lớn; chạy theo capacity/production policy hoặc sample/range trước, không tự chạy toàn bộ giờ cao điểm.

## 39. Verify: đếm missing, stale và sai giá trị

### 39.1. Thiếu trường

```javascript
db.orders.countDocuments({
  itemsSubtotalMinor: { $exists: false }
});
```

### 39.2. Marker thiếu version đúng

```javascript
db.orders.countDocuments({
  "migrations.orderItemsSubtotalV2.version": { $ne: 2 }
});
```

### 39.3. Marker và source revision khác nhau

```javascript
db.orders.countDocuments({
  $expr: {
    $ne: [
      "$migrations.orderItemsSubtotalV2.sourceRevision",
      "$lineItemsRevision"
    ]
  }
});
```

### 39.4. Không gộp counts tùy tiện

Một document thiếu subtotal có thể đồng thời thiếu marker và stale revision. Tổng ba con số trên có thể **đếm trùng**, không phải tổng documents cần sửa.

### 39.5. Verify được phép tốn chi phí

`countDocuments` và `$expr` trên hàng chục triệu docs có thể gây quét lớn. Cần điều chỉnh thời điểm/chia partitions/compute budget, không chạy liên tục mỗi giây.

### 39.6. Recompute độc lập

Nên verify một sample và eventually toàn bộ phù hợp bằng một code path độc lập:

```text
expected = calculateFrom(lineItems)
actual   = itemsSubtotalMinor

assert actual == expected
AND marker.sourceRevision == lineItemsRevision
AND marker.version == 2
```

Nếu verifier chỉ kiểm tra marker=2 mà không tính lại số tiền, lỗi transform có thể đi qua.

### 39.7. Aggregation minh họa check số tiền

Với documents có `lineItems` là array đúng schema:

```javascript
db.orders.aggregate([
  { $match: { lineItems: { $type: "array" } } },
  {
    $project: {
      actual: "$itemsSubtotalMinor",
      expected: {
        $reduce: {
          input: "$lineItems",
          initialValue: NumberLong("0"),
          in: {
            $add: [
              "$$value",
              {
                $multiply: [
                  "$$this.quantity",
                  "$$this.unitPriceMinor"
                ]
              }
            ]
          }
        }
      }
    }
  },
  { $match: { $expr: { $ne: ["$actual", "$expected"] } } },
  { $limit: 100 }
]);
```

Pipeline kiểm tra này dành cho dữ liệu đã qua validation; nếu gặp malformed/overflow, aggregation có thể lỗi hoặc semantics số học khác tính toán Java. Cần báo riêng invalid documents. Không coi kết quả 0 rows từ một sample là chứng minh toàn collection đúng.

## 40. Canary rollout: giới hạn phạm vi trước khi mở rộng

### 40.1. Trình tự gợi ý

```text
1. Unit tests for transform
2. Disposable MongoDB integration test
3. Staging benchmark with production-like data
4. Production dry-run on bounded sample
5. Canary: a small partition at low docs/s
6. Verify business values and operational metrics
7. Gradually expand partitions/rate
8. Full scan
9. Catch-up/reconciliation
10. Cutover approval
```

### 40.2. Canary selection

Không chỉ lấy 100 docs đầu và kết luận an toàn. Chọn các phân phối:

- Đơn hàng có ít và nhiều line items.
- Document kích thước nhỏ/lớn.
- Các schema versions trước đây.
- Tenant quan trọng/vừa/nhỏ trong giới hạn cho phép.

### 40.3. Rate ladder

Một lịch ví dụ:

```text
50 docs/s  -> 10 minutes
100 docs/s -> 20 minutes
200 docs/s -> observe
... increase only if safe
```

Các số chỉ minh họa; không lấy làm tiêu chuẩn performance nếu chưa có baseline.

### 40.4. Hold points

Mỗi bước tăng rate phải có xác nhận của operator hoặc policy tự động với metrics đáng tin. Nếu metrics pipeline mất dữ liệu, không tự tăng tốc.

## 41. Pause và resume đúng cách

### 41.1. Pause giữa batches

Một worker nên hỗ trợ:

```text
Check pause flag
  |
  +-- RUNNING -> process next batch
  |
  +-- PAUSED  -> finish/abort current safe unit, stop
```

### 41.2. Không mất checkpoint khi SIGTERM

Trong container orchestrator, SIGTERM có thể đến trong deployment. Worker cần:

- Ngừng nhận batch mới.
- Hoàn tất hoặc dừng batch theo idempotent replay policy.
- Không checkpoint một batch chưa xử lý hết.
- Đóng MongoClient/cursors.
- Log last durable checkpoint ID.

### 41.3. Restart

Sau restart:

1. Đọc checkpoint bền vững.
2. Xác minh migrationVersion/code compatibility.
3. Xác minh lease/ownership.
4. Xác minh highWatermarkId và scanKeyType.
5. Tiếp tục từ `lastScannedId` đã commit.
6. Replay batch chưa checkpoint an toàn.

### 41.4. Không reset progress khi version mới đổi logic

Nếu đổi công thức tính subtotal từ V2 sang V3, không chạy binary mới với checkpoint V2 như thể output vẫn tương thích. Cần explicit migrationVersion mới, rollback/cutover policy và kiểm tra phạm vi.

## 42. Runbook A — Worker crash giữa batch

### Dấu hiệu

```text
Checkpoint lastScannedId=1000
Data updates applied through 1077
Process killed before checkpoint 1100
```

### Phản ứng

1. Xác nhận durable checkpoint thực tế.
2. Kiểm tra job ownership/lease trước khi restart.
3. Khởi động lại **cùng migration version**.
4. Worker quét lại 1001..1100, dùng marker+CAS để skip những doc đã đúng.
5. Xác nhận checkpoint tiến lên chỉ sau batch hoàn tất.

### Không làm

Không sửa thủ công checkpoint thành 1100 chỉ vì logs báo “last updated 1077”, và không chạy `$inc` để “bù” các documents đã thử.

## 43. Runbook B — Primary election hoặc network timeout

### Dấu hiệu

- `MongoTimeoutException` chọn primary.
- `MongoSocketException` sau gửi update.
- Write concern timeout.
- Checkpoint write trả network error.

### Phản ứng

1. Dừng tăng concurrency/rate.
2. Xem MongoDB topology/quorum và application error metrics.
3. Phân loại uncertain data update; không coi thất bại đồng nghĩa chưa ghi.
4. Đọc durable checkpoint sau recovery.
5. Replay phần chưa checkpoint bằng idempotent writes.
6. Reconcile vùng bị ảnh hưởng theo sourceRevision/marker.

### Không làm

Không gọi một business `$inc` tương tự như request mới, không force primary change chỉ để worker tiếp tục, không hạ write concern tùy tiện.

## 44. Runbook C — Replication lag tăng vì backfill

### Dấu hiệu

```text
Backfill actual 1500 docs/s
Primary write latency stable
Secondary lag grows 1s -> 90s
CDC backlog grows
```

### Phản ứng

1. Giảm rate rõ rệt hoặc pause worker.
2. Kiểm tra oplog write volume/window và secondary I/O.
3. Xem disk, network, CPU, WiredTiger cache.
4. Theo dõi lag có hồi về baseline không.
5. Restart với budget thấp hơn sau khi có headroom.

### Không làm

Không tăng docs/s chỉ vì primary p95 còn thấp; secondary/CDC có thể chịu tác động trễ.

## 45. Runbook D — Một document gây lỗi liên tục

### Dấu hiệu

```text
Batch starts at _id 1001
Every retry hits document 1037
Validation error: unitPriceMinor string
Checkpoint remains 1000
```

### Phản ứng

1. Xác định document ID an toàn, không log raw PII.
2. Kiểm tra schema lịch sử và business semantics.
3. Quyết định sửa source theo procedure hay cập nhật transform code.
4. Nếu cần bỏ qua có kiểm soát, ghi durable DLQ với reason/owner.
5. Tiếp tục batch khi đảm bảo không mất work item.
6. Giải quyết DLQ và verify trước cutover.

### Không làm

Không ép kiểu số thập phân bằng `parseInt` tùy tiện, không tăng checkpoint qua lỗi khi không có durable record.

## 46. Runbook E — CAS conflicts tăng cao

### Dấu hiệu

```text
High conflict rate on recently edited orders
matchedCount=0 often
time spent refetching increases
```

### Phản ứng

- Kiểm tra writer rollout; mọi mutation có tăng revision?
- Giảm concurrency trên cùng hot keys.
- Đặt bounded retry/backoff.
- Thử split partition theo trạng thái `archived`/`active` nếu business cho phép.
- Chuyển hot IDs sang retry queue có checkpoint durable nếu được thiết kế.
- Kiểm tra writer có đang unset marker liên tục không.

### Không làm

Không xóa filter revision để “giảm conflicts”: nó chính là cơ chế tránh stale overwrite.

## 47. Runbook F — Job báo SCAN_DONE nhưng dữ liệu còn thiếu

### Nguyên nhân có thể

- High-water mark không bao phủ các inserts/backdated IDs sau khi quét qua.
- Writers chưa dual-write đúng.
- Có source changes sau scan.
- DLQ còn mở.
- Transform code chưa bao quát schema cũ.
- Scanner chạy với filter loại nhầm documents.

### Phản ứng

1. Giữ read fallback, chưa cắt schema cũ.
2. Chạy missing/stale/semantic verification.
3. Kiểm tra source revisions, writer rollout và CDC lag.
4. Chạy reconciliation pass/new run trên những documents còn sai.
5. Giải quyết DLQ.
6. Chỉ khi invariant đạt mức được duyệt mới chuyển `VERIFIED`.

### Không làm

Không đổi state thủ công thành COMPLETED vì “đã chạy tới cuối `_id`”.

## 48. Runbook G — Checkpoint update thất bại hoặc mất quyền lease

### Dấu hiệu

```text
data batch completed
checkpoint update matchedCount=0
another owner/epoch observed
```

### Phản ứng

1. Dừng worker stale ngay.
2. Đọc checkpoint thật và owner/lease epoch.
3. Xác định có scheduler duplicate, lease hết hạn, timeout hay config drift.
4. Không ghi đè checkpoint bằng unguarded `$set`.
5. Worker hợp lệ có thể replay các documents đã được worker cũ ghi bởi vì migration idempotent.
6. Điều tra overlapping writes nếu source/target version controls chưa chặt.

### Không làm

Không cho hai workers tranh nhau update cùng `lastScannedId` rồi dùng “last write wins”.

## 49. Test plan: chứng minh chạy lại an toàn

### 49.1. Test idempotency

Với 1.000 test orders:

1. Seed nguồn và revision.
2. Chạy backfill.
3. Ghi snapshot expected values/markers.
4. Chạy lại một reconciliation pass.
5. Assert subtotals không nhân đôi/không thay sai nghĩa.

### 49.2. Test crash sau write trước checkpoint

```text
Read batch 100 docs
Apply first 65 updates
Inject process termination
Restart worker with same checkpoint
Verify all 100 docs correct
Verify no double increments/duplicates
```

### 49.3. Test concurrent update

Chạy writer cập nhật `lineItems` và `lineItemsRevision` cùng lúc worker xử lý.

Assertions:

- Không xuất hiện subtotal của revision cũ được đánh dấu revision mới.
- CAS mismatches được refetch/retry hoặc durable defer.
- Kết quả cuối đúng với source authoritative.

### 49.4. Test poison data

Thêm document thiếu `lineItemsRevision` hoặc sai BSON type; xác nhận checkpoint **không nhảy qua** và DLQ/stop policy đúng.

### 49.5. Test network/error

Trong Testcontainers replica set lab được phép:

- Restart MongoDB node hoặc inject network error.
- Checkpoint phải không tiến nếu dữ liệu batch chưa confirmed.
- Sau restart, worker tiếp tục đúng.
- Check result khi MongoDB update timeout không bị giả định là chưa ghi.

### 49.6. Test tốc độ

Chạy 10.000 docs với limiter 200 docs/s, đo observed docs/s theo cửa sổ đủ dài; cho phép sai số do timer/scheduler/DB load, không assert chính xác mỗi 5 ms.

### 49.7. Test empty dataset

Sự kiện không có documents trong range phải chuyển sang scan-done hoặc no-op theo contract, không crash/restart vô hạn. Mẫu Java mục 22 cố ý yêu cầu seed; production cần bổ sung case này.

### 49.8. Test multiple workers

Nếu dùng partition+lease:

- Hai workers claim cùng partition.
- Chỉ một ownership hợp lệ được commit checkpoint.
- Worker hết lease không ghi checkpoint mới.
- Replayed data writes không làm sai state.

## 50. Testcontainers và JUnit: lớp kiểm thử nhẹ cho backfill

Một integration test có thể dùng Testcontainers Java MongoDB module để có MongoDB thật.

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.mongodb.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class BackfillReplay426IT {
    @Container
    static MongoDBContainer mongo =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"))
            .withReplicaSet();

    @Test
    void shouldComputeSubtotal() {
        try (MongoClient client =
                 MongoClients.create(mongo.getReplicaSetUrl())) {
            var orders = client.getDatabase("migration_lab_426")
                .getCollection("orders");

            orders.insertOne(new Document(
                    "_id", new org.bson.types.ObjectId())
                .append("lineItemsRevision", 1L)
                .append("lineItems", java.util.List.of(
                    new Document("quantity", 2)
                        .append("unitPriceMinor", 125000L)
                )));

            new OrderSubtotalBackfill426(client).run();

            Document current = orders.find().first();
            assertNotNull(current);
            assertEquals(250000L,
                current.getLong("itemsSubtotalMinor"));
        }
    }
}
```

### 50.1. Những điều cần bảo đảm

- Testcontainers dependency/API/import phải khớp version; ví dụ dùng Testcontainers Java 2.x package `org.testcontainers.mongodb`.
- Một single-node replica set đủ test core transaction/write concern behavior của worker, nhưng **không** mô phỏng election sang primary khác.
- Test cần dùng namespace fresh và cleanup được sở hữu.
- Để test crash/restart giữa batch, phải có hook/fault injector ở worker; ví dụ trên chỉ là smoke test end-to-end.

### 50.2. Không chạy test destructive trên production

Không thay MongoDB test URI bằng production credentials. Các lệnh cleanup/seed của test phải chỉ tác động tới container/database do test sở hữu.

## 51. Các kịch bản production có thể thay đổi thiết kế

### 51.1. Collection có 500 triệu documents

Một worker vẫn có thể chạy, nhưng ETA có thể dài. Partition theo tenant/shard key/immutable range giúp scale nếu đảm bảo non-overlap và global budget.

### 51.2. Document có mảng rất lớn

Compute cost và read payload p99 cao. Batch size nên thích ứng theo byte size hoặc phân loại outlier, không chỉ “100 docs” mặc định.

### 51.3. Data source thay đổi nhiều lần/giây

CAS conflict cao; application dual-write/CDC có thể phù hợp hơn việc worker liên tục đua với writer.

### 51.4. Migration làm tăng document size đáng kể

Thêm trường lớn/index có thể tăng disk/cache pressure và nguy cơ vượt giới hạn BSON document 16 MiB. Preflight cần đo p99 document size, compression/IO và index growth.

### 51.5. Target mới là sharded collection

Targeting, shard key, unique index, bulkWrite ordering và data distribution ảnh hưởng throughput/semantics. Cần kiểm tra lệnh update/upsert có đủ shard key theo version.

### 51.6. Muốn đổi tiền tệ

Không chỉ nhân một số mặc định. Cần tỷ giá thời điểm nghiệp vụ, precision, rounding, currency code và audit. Nếu không có thông tin lịch sử, **không tự bịa kết quả backfill**.

### 51.7. Schema không có source revision

Có thể dùng một migration phase bổ sung revision/dual-write protocol trước khi chạy computed backfill. Không cố che thiếu revision bằng chỉ đọc `updatedAt` nếu timestamp không được bảo đảm unique/monotonic.

## 52. Cutover: khi nào ứng dụng có thể bỏ read fallback?

Một checklist chấp nhận:

| Điều kiện | Bằng chứng mong đợi |
|---|---|
| All writers compatible | Deployment inventory, integration tests |
| Scan completed | Durable progress, cutoff, metadata |
| New changes covered | Dual-write/CDC lag và protocol |
| No unresolved poison docs | DLQ count = 0 hoặc waiver approved |
| Values verified | Missing/stale/mismatch checks |
| API correctness | Canary reads/outputs |
| Operational health | p95/p99, write rate, replication lag |
| Recovery possible | Backup/PITR, rollback/forward-fix plan |
| Ownership confirmed | Change ticket, operator approval |

### 52.1. Hai trạng thái cutover

**Read cutover:** application bắt đầu ưu tiên field mới, vẫn có fallback hoặc guard.

**Contract cutover:** bỏ code hỗ trợ schema cũ và có thể thêm schema validation/index rules mới.

Không buộc hai bước xảy ra cùng lúc.

### 52.2. Deployment dần

Cho phép percent-based rollout/canary tenants. Nhưng nếu tenants có data mix và consistency policy khác, cần xác định điều kiện từng group đạt đủ, không chỉ dựa vào tỷ lệ documents toàn cluster.

### 52.3. Backfill không thay đổi lịch sử theo ý mình

Nếu order immutable, computed field được phép bổ sung để tăng tốc đọc; nếu nghiệp vụ xem order là chứng từ đã ký, cần xem audit/legal requirements trước khi ghi thêm fields.

## 53. Rollback và forward-fix

### 53.1. Rollback code chưa chắc rollback dữ liệu

Nếu ứng dụng mới và worker đã thêm `itemsSubtotalMinor`, rollback application code có thể không yêu cầu xóa field đó. Thậm chí xóa ngược có thể làm hỏng một service khác đã dùng.

### 53.2. Forward-fix

Nếu công thức V2 sai, thường nên:

1. Dừng worker V2.
2. Giữ old/new compatibility.
3. Tạo transform V3 đúng và marker version mới.
4. Recompute từ source-of-truth.
5. Verify lại, rồi cutover theo phê duyệt.

### 53.3. Không đảo ngược bằng phép bù thiếu chứng cứ

Nếu V2 sai vì rounding, trừ một khoản cố định khỏi mọi record thường không đủ; phải dựa trên input gốc/contract.

### 53.4. Backup/PITR

Backup giúp khôi phục khi dữ liệu hỏng/mất nghiêm trọng. Nhưng restore toàn cluster có thể mất writes hợp lệ sau thời điểm backup; chỉ dùng trong recovery plan được đánh giá kỹ, không coi là nút Undo đơn giản.

## 54. Anti-patterns thường gặp

| Anti-pattern | Rủi ro | Giải pháp |
|---|---|---|
| Một `updateMany({})` toàn collection tùy tiện | Khó throttle/checkpoint | Bounded batches hoặc idempotent scoped updates |
| `skip(10000000)` | Scan lớn, offset dịch | Keyset |
| Cursor sort thiếu tie-breaker | Mất/đúp records | Composite stable key |
| Checkpoint trước writes | Bỏ sót khi crash | Checkpoint sau batch |
| Checkpoint khi 1 doc còn lỗi | Mất work item | Fail batch hoặc durable DLQ |
| Chỉ lưu cursor trong RAM | Restart từ đầu | Durable progress |
| Không có high-water mark | Quét mãi khi dữ liệu mới liên tục | Chốt cutoff + catch-up |
| Coi high-water mark là snapshot | Miss concurrent inserts/updates | Writers/CDC/reconciliation |
| Dùng ObjectId như commit timestamp tuyệt đối | Sai ordering assumption | Nêu giới hạn/correct handoff |
| Dùng `$inc` cho derived subtotal | Double count khi retry | Deterministic `$set` |
| Dùng `replaceOne` từ snapshot cũ | Overwrite concurrent changes | Field-level CAS update |
| Không tăng source revision khi mutation | CAS mất hiệu lực | Enforce writer invariant |
| Bỏ CAS khi conflict nhiều | Stale overwrite | Rate/partition/defer |
| Infinite retry | Load storm, job treo | Bounded retries + DLQ |
| Dùng TTL để xóa poison records | Mất bằng chứng lỗi | Durable triage/retention |
| Coi `bulkWrite` atomic cả batch | Partial success nguy hiểm | Per-document idempotency |
| `ordered(false)` nhưng phụ thuộc thứ tự | Dữ liệu không xác định | Independent operations |
| Throttle bằng batch size đơn thuần | Không có docs/s cap | Pacing/token bucket |
| 10 workers, mỗi worker dùng full cluster budget | Quá tải toàn cluster | Global rate budget |
| Tăng tốc khi metrics thiếu | Blind spot | Pause hoặc safe default |
| Chỉ xem primary latency | Secondary lag/CDC kẹt | Replication/oplog metrics |
| Data write `w:1`, checkpoint majority | Rollback data sau checkpoint | Consistent durability policy |
| Cho hai workers ghi checkpoint unguarded | Progress bị ghi đè | Lease/fencing/CAS |
| Coi lease bảo vệ mọi data writes | Stale worker vẫn có thể ghi | Revision guard/fencing |
| Stale CDC event overwrite target mới | Dữ liệu lùi phiên bản | Monotonic target revision |
| Token saved trước apply event | Bỏ event khi crash | Commit event checkpoint sau apply |
| Dùng resume token như scan cursor | Sai semantics | Hai checkpoints riêng |
| Quét xong là bỏ fallback | Missing/stale/dlq còn | Verify/cutover gate |
| Chỉ count marker, không verify subtotal | Sai transform lọt qua | Independent recompute |
| Log raw orders trên monitoring | Lộ thông tin | IDs/reason codes/redaction |
| Dùng production URI trong integration test | Phá dữ liệu thật | Test-owned container/namespace |
| Rollback bằng drop fields trên diện rộng | Mất dữ liệu dùng chung | Planned forward-fix |

## 55. Bài tập thực hành

### Bài 1 — Xác định dữ liệu nguồn và trường đích

Cho orders với lineItems, discount và shipping. Hãy định nghĩa chính xác `itemsSubtotalMinor` và phân biệt với `grandTotalMinor`.

### Bài 2 — Tính toán

LineItems có (2×125000) và (1×80000). Tính subtotal; nêu trường hợp cần `Math.multiplyExact`.

### Bài 3 — Thiết kế expand–contract

Viết kế hoạch từ code chỉ đọc lineItems sang code đọc subtotal mới, gồm fallback, dual-write, backfill, verify và contract.

### Bài 4 — Không cần backfill?

Khi nào có thể tính subtotal lúc đọc mà không cần ghi hàng chục triệu documents? Nêu read latency trade-off.

### Bài 5 — Idempotency

So sánh `$set` subtotal với `$inc` subtotal khi cùng document bị chạy lại ba lần.

### Bài 6 — CAS

Worker đọc revision=5, API sửa lineItems thành revision=6. Viết `updateOne` chỉ ghi subtotal khi revision vẫn là 5.

### Bài 7 — Revision invariant

Một import job sửa lineItems nhưng không tăng revision. Vì sao CAS vẫn có thể ghi stale total? Thiết kế cách sửa rollout.

### Bài 8 — Keyset

Viết query lấy 100 documents có `_id` lớn hơn checkpoint và không vượt high-water mark, sort tăng.

### Bài 9 — Composite cursor

Document có cùng `createdAt`. Vì sao checkpoint chỉ theo createdAt bỏ sót records? Viết filter với createdAt và `_id`.

### Bài 10 — BSON type

Collection có `_id` là ObjectId và String. Những giả định nào của Java worker không còn đúng?

### Bài 11 — High-water mark

Worker chốt max(ObjectId), nhưng API insert một document có ObjectId được tạo từ 1 ngày trước. Rủi ro bỏ sót nằm ở đâu?

### Bài 12 — Checkpoint ordering

Mô tả crash khi checkpoint trước data write và crash khi checkpoint sau data write. Trường hợp nào phục hồi được bằng idempotency?

### Bài 13 — Durable state

Thiết kế document checkpoint có `migrationVersion`, `state`, `highWatermarkId`, `lastScannedId`, `updatedAt`.

### Bài 14 — Lease

Worker A hết lease, worker B claim epoch=9. Viết filter checkpoint để A không ghi đè progress của B.

### Bài 15 — Throttle

Cần xử lý 12 triệu docs trong 8 giờ. Tính tốc độ trung bình tối thiểu (bỏ qua overhead), rồi giải thích vì sao không đặt ngay rate limit đúng kết quả phép chia.

### Bài 16 — Token bucket

Thiết kế token bucket 100 docs/s, capacity 20; so với sleep sau mỗi 1.000 writes.

### Bài 17 — Batch size

So sánh scan 100 docs/batch với 5.000 docs/batch khi documents có kích thước rất khác nhau và yêu cầu checkpoint thường xuyên.

### Bài 18 — Bulk ordered

Một ordered bulk 100 updates gặp duplicate/validation error tại operation thứ 37. Những operations nào có thể đã được chạy? Có nên checkpoint tới doc 100 không?

### Bài 19 — Bulk unordered

Một unordered bulk có partial success. Thiết kế cách xác định những IDs cần retry mà không làm double effects.

### Bài 20 — Poison data

Một order có quantity="two". Nêu lựa chọn fail-fast, DLQ và vì sao không tự động coi nó là 2.

### Bài 21 — Crash test

Worker ghi 78/100 docs rồi crash trước checkpoint. Thiết kế test bằng Testcontainers để chứng minh replay an toàn.

### Bài 22 — Unknown write outcome

`updateOne` trả network timeout sau khi gửi request. Có thể khẳng định chưa ghi không? Cần kiểm tra gì trước khi checkpoint?

### Bài 23 — CDC token

Giải thích vì sao lưu resume token trước khi apply event có thể làm mất dữ liệu, và vì sao apply trước token cần idempotency.

### Bài 24 — Hai progress streams

Thiết kế checkpoint riêng cho scan `lastScannedId` và CDC `resumeToken`. Khi nào cutover được phép?

### Bài 25 — Sharding

Collection shard theo tenantId; một range scan chỉ lọc `_id` có rủi ro gì? Thiết kế partition/query theo tenantId phù hợp.

### Bài 26 — Write concern

Data updates dùng `w:1` còn checkpoint dùng `w:majority`. Primary failover có thể khiến progress sai thế nào?

### Bài 27 — Metrics

Thiết kế dashboard có scanned/updated/skipped/errors, checkpoint, p95 API, MongoDB disk IOPS, replication lag và CDC lag.

### Bài 28 — Adaptive throttling

Backfill đạt 800 docs/s nhưng API p99 tăng và oplog window giảm. Đề xuất policy reduce/pause và điều kiện tăng trở lại.

### Bài 29 — Verification

Viết ba truy vấn đếm missing subtotal, marker version không đúng và sourceRevision stale. Tại sao cộng ba counts có thể double count?

### Bài 30 — Recompute độc lập

Viết một verifier không tin marker mà tính lại subtotal từ lineItems, bao gồm test overflow/sai type.

### Bài 31 — Rollback

Migration V2 tính sai vì bỏ qua một loại lineItem. Có nên trừ một số cố định khỏi mọi subtotal? Thiết kế forward-fix V3.

### Bài 32 — Capstone

Thiết kế backfill 50 triệu orders trong production đang ghi liên tục, yêu cầu không vượt thêm 5% p99 latency:

1. Access pattern và source-of-truth.
2. Writer compatibility/dual-write rollout.
3. Deterministic transform và version marker.
4. Keyset/high-water mark và cursor schema.
5. Batch size/rate/global budget.
6. Checkpoint/lease/fencing.
7. Retry/CAS/DLQ policy.
8. CDC hoặc reconciliation cho concurrent writes.
9. Metrics/alerts/stop conditions.
10. Load test, crash/restart test, verify/cutover/rollback.

## 56. Quy trình thực thi tóm lược

### Chuẩn bị

```text
1. Define business invariant
2. Confirm source schemas and type distributions
3. Deploy backward-compatible readers/writers
4. Validate backup/recovery and production capacity
5. Select immutable scan key and cutoff strategy
6. Fix version, job ID, checkpoint and rate budget
7. Run dry-run and canary
```

### Mỗi batch

```text
Read durable checkpoint
      |
      v
Select next bounded page in stable key order
      |
      v
For each document:
  throttle
  fetch current source
  validate transform
  skip if already correct
  guarded write with CAS
  retry/defer only under defined policy
      |
      v
All documents resolved?
      |
   No +-----> Stop or durable DLQ, no unsafe advance
      |
     Yes
      |
      v
Persist checkpoint with majority write concern + ownership CAS
      |
      v
Continue or pause
```

### Kết thúc

```text
Scan reaches cutoff
      |
      v
Reconcile concurrent inserts/updates/deletes
      |
      v
Resolve DLQ and stale revisions
      |
      v
Independent validation
      |
      v
Canary read cutover
      |
      v
Contract after approval
```

## 57. Tổng kết

**Backfill online thành công không phải là một lệnh ghi nhiều documents thật nhanh.** Đó là một tiến trình thay đổi schema có khả năng chạy song song với ứng dụng, giới hạn tài nguyên, khôi phục được sau sự cố và có bằng chứng dữ liệu cuối đúng.

**Batch và rate limit** giúp phân chia mức tải có kiểm soát: `limit()` và `batchSize()` chỉ điều chỉnh cách quét/đọc, trong khi token bucket/pacing/global budget quyết định tốc độ tác động lên MongoDB. Phải theo dõi ứng dụng, disk/cache, replication lag và oplog window, không chỉ throughput worker.

**Checkpoint phải tiến sau khi batch được giải quyết đầy đủ**. Nếu crash trước checkpoint, xử lý lặp lại là bình thường; thiết kế phải có idempotent `$set` và CAS revision để kết quả không nhân đôi hay ghi đè dữ liệu mới. Nếu có nhiều workers, dùng partition ownership, lease/fencing và checkpoint CAS.

**High-water mark không là snapshot**. Inserts/updates/deletes trong lúc quét có thể tạo khoảng trống; ứng dụng cần dual-write, CDC catch-up hoặc reconciliation có tính toán rõ. `SCAN_DONE` không đồng nghĩa `VERIFIED`.

**Cutover cần điều kiện kiểm chứng**, không chỉ một progress bar đạt 100%: marker/sourceRevision hợp lệ, computed values đúng, DLQ được giải quyết, CDC bắt kịp, API SLO an toàn và recovery plan sẵn sàng. Khi công thức sai, ưu tiên forward-fix có version mới thay vì xóa hoặc cộng/trừ bù tùy đoán.

Một backfill đáng tin cậy cho MongoDB là backfill mà **có thể pause, restart, replay và giải thích chính xác từng đoạn dữ liệu đã xử lý**, trong khi hệ thống vẫn duy trì tính đúng đắn nghiệp vụ.

## 58. Tài liệu tham khảo

- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): single-document atomicity và CAS conditions.
- [MongoDB Manual — updateMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/): multi-document update không atomic toàn batch, idempotent retries.
- [MongoDB Manual — bulkWrite()](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/): ordered/unordered operations và partial failures.
- [MongoDB Java Sync Driver — Bulk Write Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/bulk/): `UpdateOneModel`, `BulkWriteOptions` và xử lý bulk writes.
- [MongoDB Java Sync Driver — Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update/): updateOne và UpdateResult.
- [MongoDB Manual — Update with an Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/): transforms trên server khi phù hợp.
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/): resume token, oplog retention và resumability.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): protocol retry, giới hạn operation.
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/): dữ liệu majority-committed và consistency.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): majority acknowledgments, durability và timeout.
- [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/): ObjectId/Int64/Decimal128 và BSON ordering.
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): đánh giá scan/index plan.
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/): shard targeting, range migration và phân bố load.
- [MongoDB Manual — Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/): oplog window và replication.
- [Testcontainers Java — MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/): MongoDB integration tests và local replica set setup.





