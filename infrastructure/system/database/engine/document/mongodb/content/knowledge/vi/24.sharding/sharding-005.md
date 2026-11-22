# Ranged sharding, hashed sharding và khóa ghép trong MongoDB

## 1. Vì sao chọn chiến lược sharding lại quan trọng?

Khi dữ liệu và lưu lượng vượt khả năng phục vụ hiệu quả của một MongoDB replica set, **sharding** cho phép phân phối dữ liệu của collection trên nhiều **shard**. Mỗi shard lưu một phần dữ liệu, thường dưới dạng replica set riêng. Ứng dụng truy cập sharded cluster qua **`mongos`**, router chịu trách nhiệm định tuyến request đến các shard liên quan.

Nhưng “đã có nhiều shard” không đồng nghĩa dữ liệu hoặc tải tự chia đều. **Shard key** quyết định document nằm trong khoảng dữ liệu nào; chiến lược **ranged**, **hashed** và cách xếp field trong **khóa ghép** ảnh hưởng trực tiếp tới:

- Phân phối dung lượng và insert/update workload giữa các shard.
- Khả năng truy vấn **target một hoặc ít shard**, thay vì gửi tới toàn bộ shard.
- Hiệu quả truy vấn equality, range và sort.
- Nguy cơ một giá trị khóa quá phổ biến tạo **hot chunk/hot shard**.
- Mức độ phù hợp với yêu cầu zone sharding, data locality và ràng buộc unique.
- Chi phí của balancer, chunk migrations, thay đổi shard key và mở rộng cluster.

Ví dụ một ứng dụng đơn hàng ghi:

```javascript
{
  _id: ObjectId("6927b73c0000000000000001"),
  tenantId: "TENANT-A",
  orderId: "ORD-1001",
  customerId: "CUS-42",
  createdAt: ISODate("2026-11-14T09:15:00Z"),
  amountMinor: NumberLong("259000"),
  status: "PAID"
}
```

Nếu phần lớn query là “lấy đơn của một tenant theo thời gian”, chọn `{ createdAt: 1 }` có thể thuận tiện cho range query nhưng phát sinh hotspot khi timestamp tăng liên tục. Chọn `{ orderId: "hashed" }` có thể tản insert tốt hơn nhưng mất locality theo tenant/thời gian. Chọn `{ tenantId: 1, orderId: "hashed" }` lại tạo một sự đánh đổi khác: giữ được khả năng khoanh vùng theo tenant, rồi phân phối theo hash của order.

> **Kết luận nền tảng:** shard key tốt phải cân bằng **phân phối dữ liệu**, **phân phối tải** và **khả năng định tuyến theo query thực tế**. Không có một kiểu khóa đúng cho mọi collection.

Bài sẽ đi từ kiến trúc, ba chiến lược chính, ví dụ `mongosh` và Java Sync Driver, đến cách quan sát và thay đổi khóa khi hệ thống phát triển.

---

## 2. Các thành phần của sharded cluster

```text
                  Application / Java Driver
                            |
                            v
                    +---------------+
                    | mongos router |
                    +---------------+
                      /      |      \
                     v       v       v
                 Shard A  Shard B  Shard C
                 (RS)     (RS)     (RS)
                    \       |       /
                     \      |      /
                  Config Server Replica Set
                    Metadata: ranges, shards,
                    routing / placement info
```

- **`mongos`** nhận query, dựa vào shard key và metadata để tìm shard phù hợp.
- **Config server replica set** duy trì metadata của sharded cluster.
- **Shard** thực sự lưu dữ liệu. Trong triển khai hiện đại, mỗi shard là một replica set phục vụ tính sẵn sàng cao.
- **Shard key** là một field hoặc tổ hợp field trong document dùng để phân chia tập giá trị.
- **Chunk/range** là một khoảng liên tục của **không gian shard key** được gán cho một shard.
- **Balancer** có thể di chuyển các range giữa shard nhằm cải thiện cân bằng và đáp ứng zone placement.

Một document không bị cắt làm nhiều phần giữa các shard. Một document thuộc **một shard** tại một thời điểm, dù replica set của shard đó có thể lưu các bản sao để phục vụ replication.

### 2.1. Chunk có khoảng nửa mở

Một range thường có:

```text
[lowerBound, upperBound)
```

Nghĩa là lower bound **inclusive**, upper bound **exclusive**.

Ví dụ trên khóa `orderNumber`:

```text
Shard A: [MinKey, 10000)
Shard B: [10000, 20000)
Shard C: [20000, MaxKey)
```

Một order có `orderNumber = 10000` nằm trong khoảng của shard B, **không** phải A. Trong thực tế, range boundaries và placement do cluster quản lý, có thể thay đổi khi chunk được split/migrate.

### 2.2. Shard key không giống tên index tùy ý

Một collection có thể có nhiều index phục vụ filter/sort, nhưng chỉ có **một shard key pattern đang có hiệu lực** để phân phối document. Ví dụ:

```javascript
// Các index phục vụ truy vấn:
{ tenantId: 1, createdAt: -1 }
{ customerId: 1, status: 1 }

// Shard key có thể là:
{ tenantId: 1, orderId: "hashed" }
```

Đừng nhầm việc tạo `createIndex({ userId: "hashed" })` với việc **đã shard collection**. Index hashed là cấu trúc chỉ mục; collection chỉ trở thành sharded sau thao tác quản trị như `sh.shardCollection(...)` trên deployment phù hợp.

---

## 3. Ranged sharding: chia theo khoảng giá trị

**Ranged sharding** (range-based sharding) chia không gian shard key thành những khoảng kề nhau.

Ví dụ shard key:

```javascript
{ customerId: 1 }
```

Có thể hình dung:

```text
Không gian giá trị customerId (sắp theo thứ tự so sánh BSON)

MinKey ---- C100 ---- C500 ---- C900 ---- MaxKey
   |          |         |         |
   +--Range 1-+--Range 2+--Range 3+--Range 4
        |           |          |          |
      Shard A     Shard B    Shard C    Shard A
```

Ranh giới và shard trong sơ đồ chỉ là **minh họa**. Một shard có thể sở hữu nhiều range không liền nhau. Mongos dựa vào shard key của query để xác định những range cần xem.

**Đặc tính:** các giá trị shard key gần nhau về thứ tự so sánh thường có xu hướng nằm trong cùng hoặc các range lân cận. Vì vậy range predicate trên shard key có thể được định tuyến tới **một tập shard hẹp hơn** so với truy vấn broadcast.

### 3.1. Tạo collection ranged-sharded

Các lệnh quản trị sau phải chạy trên **`mongos` của sharded cluster**, với quyền phù hợp:

```javascript
// Ví dụ collection trống hoặc đã có index hỗ trợ.
sh.shardCollection(
  "commerce.orders",
  { customerId: 1 }
);
```

Nếu collection đã có dữ liệu, phải tạo index hỗ trợ shard key **trước khi** shard:

```javascript
db.getSiblingDB("commerce").orders.createIndex({
  customerId: 1
});

sh.shardCollection(
  "commerce.orders",
  { customerId: 1 }
);
```

Nếu collection trống, MongoDB có thể tạo index hỗ trợ shard key khi cần. Cấu hình sharding **không** nên chạy vô điều kiện trong application startup. Đây là thao tác migration/administration cần kế hoạch triển khai.

### 3.2. Ranged giúp truy vấn khoảng có định hướng

Giả sử shard key `{ createdAt: 1 }`:

```javascript
db.orders.find({
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
});
```

Mongos có thể định vị **những range chứa tháng 11**, rồi chỉ gửi tới shard sở hữu các range đó. Số shard thực sự được truy cập phụ thuộc việc phân bố range ở thời điểm query, **không chắc là một shard**.

### 3.3. Khi nào ranged phù hợp?

Ranged thường hữu ích nếu:

- Query quan trọng có range predicate trên **shard key hoặc prefix tương thích**.
- Cần locality theo một thuộc tính có thứ tự, ví dụ thời gian, tenant hoặc ID nhóm.
- Có quy tắc zone placement dựa trên khoảng giá trị thật.
- Shard key có cardinality cao và tần suất mỗi giá trị không quá lớn.
- Workload ghi **không dồn liên tục vào đầu/cuối không gian khóa**.

Tuy nhiên, chọn `{ createdAt: 1 }` đơn lẻ cho hệ thống ghi sự kiện liên tục thường tiềm ẩn hotspot.

---

## 4. Hotspot do shard key tăng đơn điệu

Giả sử mỗi order được gán `orderNumber` liên tục tăng:

```text
100001, 100002, 100003, 100004, ...
```

Nếu shard key là:

```javascript
{ orderNumber: 1 }
```

các giá trị mới liên tục rơi vào range ở **đầu cao nhất** có upper bound `MaxKey`:

```text
Các range đang tồn tại:
[MinKey, 100000)    -> Shard A
[100000, 200000)    -> Shard B
[200000, MaxKey)    -> Shard C  <-- toàn bộ insert mới ở đây
```

Trong khoảng thời gian đó, shard C có thể nhận phần lớn insert dù ba shard có dung lượng tổng thể tương đối cân bằng.

MongoDB có thể split/migrate range khi phù hợp, nhưng **việc di chuyển range không bảo đảm khắc phục hoàn toàn hotspot phát sinh do tính đơn điệu ở từng thời điểm**.

### 4.1. Những field dễ tăng/giảm đơn điệu

- `createdAt` hoặc timestamp sự kiện.
- `_id` dùng ObjectId sinh theo thời gian (không phải hoàn toàn ngẫu nhiên).
- Mã auto-increment hoặc sequence.
- Thứ tự log hoặc số phiên bản tăng dần.
- Counter liên tục giảm cũng có rủi ro tương tự ở range `MinKey`.

### 4.2. Đọc range tốt không đồng nghĩa ghi đều

Đây là đánh đổi quan trọng:

```text
Shard key = { createdAt: 1 }

Đọc  [10:00, 11:00)  -> có thể target ít range/shard.
Ghi  current timestamp -> dồn vào range phía cuối.
```

Tối ưu **đường đọc** bằng ranged sharding có thể làm **đường ghi** bị nghẽn. Nếu một shard saturate CPU/IOPS trong khi các shard khác rảnh, phải xem shard key và phân phối write, không chỉ số document mỗi shard.

### 4.3. Tại sao thêm một index phụ chưa đủ?

Tạo:

```javascript
db.orders.createIndex({ createdAt: 1 });
```

giúp một số query trên từng shard, nhưng **không đổi** cách phân phối dữ liệu nếu shard key vẫn là `{ orderNumber: 1 }`. Đường routing và hotspot vẫn được quyết định bởi shard key.

---

## 5. Hashed sharding: chia theo giá trị hash

**Hashed sharding** dùng hash tính từ giá trị của một field, rồi phân phối các document theo **khoảng của giá trị hash**, không theo thứ tự của giá trị gốc.

Ví dụ:

```javascript
sh.shardCollection(
  "commerce.orders",
  { orderId: "hashed" }
);
```

Mongos và server tự tính hash. Ứng dụng **không cần** băm ID trước để router hoạt động.

Hình dung:

```text
orderId gốc:
  ORD-1001  ORD-1002  ORD-1003  ORD-1004  ORD-1005
      |         |         |         |         |
      v         v         v         v         v
  hash(...)  hash(...)  hash(...)  hash(...) ...
      \         /           \          /      /
     Range hash A         Range hash B     Range hash C
         |                    |                |
       Shard A              Shard B          Shard C
```

Hash trong sơ đồ không phản ánh giá trị hoặc shard placement cụ thể.

### 5.1. Vì sao hashed phù hợp cho khóa tăng đơn điệu?

Hai order có ID kề nhau không nhất thiết có hash gần nhau. Vì vậy, khi `orderId` tăng theo thứ tự, hash có thể rải các insert tới nhiều range/shard, giúp tránh một range `MaxKey` luôn nhận toàn bộ ghi mới như ranged.

Điều kiện để đạt phân phối tốt:

- Field có **nhiều giá trị khác nhau**.
- Không có giá trị khóa đơn lẻ xuất hiện quá nhiều.
- Phân phối hash và chunks đủ phát triển/cân bằng.
- Workload không tập trung quá lớn ở một phần khác của hệ thống.

**Hashed không bảo đảm mọi shard luôn có đúng 1/N lưu lượng**. Có thể có chênh lệch do kích thước document, phân phối request, balancer, chunk migrations, hot tenants và các yếu tố tài nguyên.

### 5.2. Equality lookup thường được target tốt

Với key `{ orderId: "hashed" }`:

```javascript
db.orders.findOne({
  orderId: "ORD-1001"
});
```

Router tính hash của giá trị equality và xác định range/hash-chunk tương ứng. Thông thường query đầy đủ như vậy có thể target **một shard** theo routing metadata.

### 5.3. Range lookup trên khóa gốc thường tệ hơn

```javascript
db.orders.find({
  orderId: {
    $gte: "ORD-1000",
    $lt: "ORD-2000"
  }
});
```

Các giá trị nằm kề trong thứ tự chuỗi **không nằm gần nhau sau hash**, nên query range theo `orderId` gốc khó được target vào một số range hash hẹp. Router thường phải gửi query tới nhiều hoặc mọi shard.

Nếu API thường quét theo thời gian hoặc range ID, hashed trên trường đó có thể là đánh đổi tốn chi phí đọc.

### 5.4. Hashed không có nghĩa MongoDB tạo random key

Ứng dụng vẫn lưu:

```javascript
{ orderId: "ORD-1001" }
```

MongoDB dùng giá trị hash ở index và routing. **Không cần** thêm field `orderIdHash` vào document bằng code Java chỉ để bật hashed sharding.

---

## 6. Những giới hạn quan trọng của hashed index

### 6.1. Không tạo unique hashed index

Không hợp lệ:

```javascript
// Không được dùng unique trên hashed index:
db.orders.createIndex(
  { orderId: "hashed" },
  { unique: true }
);
```

Và không dùng:

```javascript
// Không được unique: true với hashed shard key:
sh.shardCollection(
  "commerce.orders",
  { orderId: "hashed" },
  true
);
```

MongoDB không cho unique constraint trực tiếp trên hashed index/shard key. Điều này **không có nghĩa `orderId` không bao giờ được duy nhất**, mà nghĩa là bài toán uniqueness cần thiết kế bằng key/index hợp lệ khác theo các ràng buộc của sharded collection.

### 6.2. Không hỗ trợ hashed multikey

Hashed index không hỗ trợ field mảng:

```javascript
{ userIds: ["U1", "U2"] }
```

Không shard theo:

```javascript
{ userIds: "hashed" }
```

nếu field chứa array và cần multikey semantics. Compound hashed index cũng **không được trở thành multikey index**, kể cả khi mảng nằm ở field khác của compound index.

### 6.3. Floating-point hash bị chuyển về integer

MongoDB **cắt phần thập phân của floating-point về số nguyên 64-bit trước khi hash**. Vì vậy, các giá trị Double như `2.2`, `2.3`, `2.9` có thể có cùng hash.

```text
Double 2.2 --> integer 2 --> hash(2)
Double 2.3 --> integer 2 --> hash(2)
Double 2.9 --> integer 2 --> hash(2)
```

Đây là một dạng **hash collision do quy tắc chuyển đổi**, không phải điều mong muốn cho khóa cần phân biệt các phần thập phân. Hashed index còn có ràng buộc với floating-point vượt phạm vi chính xác quy định (trong tài liệu có ngưỡng 2^53).

**Không chọn `price`, `temperature`, `score` dạng Double có phần lẻ làm hashed shard key** nếu mục tiêu là phân phối theo từng giá trị thập phân phân biệt.

### 6.4. Không dùng hashed index để cover query

Hashed index không hỗ trợ **covered queries** theo cách một index B-tree thông thường có thể cung cấp toàn bộ field cần trả. Một số truy vấn vẫn cần truy cập document gốc.

Hashed index cũng không được hiểu là đã tối ưu range sort theo **giá trị gốc** của field. Nếu API cần:

```javascript
db.orders.find({ customerId: "C1" })
  .sort({ createdAt: -1 });
```

có thể cần index phụ phù hợp với filter/sort trên từng shard. **Shard key index phục vụ routing chưa chắc là index tối ưu cho mọi query**.

---

## 7. Ranged và hashed: bảng so sánh

| Tiêu chí | Ranged sharding | Hashed sharding |
| --- | --- | --- |
| Cơ sở chia dữ liệu | Thứ tự giá trị shard key gốc | Thứ tự hash của một field |
| Equality full shard key | Có thể target đúng range/shard | Có thể target hash range/shard |
| Range predicate trên key gốc | Thường target tốt hơn | Thường phải truy cập nhiều shard |
| Monotonic inserts | Nguy cơ dồn vào MinKey/MaxKey range | Giảm nguy cơ nếu field có nhiều giá trị |
| Gần nhau về giá trị gốc | Có thể chung hoặc gần range | Thường phân tán sau hash |
| Locality theo tenant/region | Có thể giữ locality với prefix | Hash thuần làm mất locality gốc |
| Zone sharding theo range thật | Tự nhiên hơn | Range của hashed value không phản ánh range thật |
| Unique trực tiếp trên shard key | Có thể với điều kiện phù hợp | Không được unique trên hashed index |
| Chi phí đọc | Phù hợp query range có shard key | Phù hợp equality/lookup key |
| Rủi ro | Hot end-range, low cardinality, skew | Scatter-gather range, collisions, mất locality |
| Có thể dùng compound key? | Có | Có; một field được đánh dấu `"hashed"` |

Không chọn ranged chỉ vì đọc nhanh hoặc hashed chỉ vì ghi đều. Cần quan sát cả **số shard mỗi request chạm** và **tỷ lệ lưu lượng trên từng shard**.

---

## 8. Khóa ghép (compound shard key) là gì?

**Compound shard key** gồm từ hai field trở lên theo **thứ tự xác định**.

Ví dụ ranged compound key:

```javascript
{
  tenantId: 1,
  orderId: 1
}
```

Hoặc:

```javascript
{
  region: 1,
  createdAt: 1,
  orderId: 1
}
```

Thứ tự field ảnh hưởng:

- Cách các giá trị được **sắp xếp theo thứ tự từ trái sang phải**.
- Những prefix có thể giúp router thu hẹp range.
- Các query nào có khả năng target ít shard.
- Phân phối document trong cùng một giá trị prefix.
- Độ chọn lọc, uniqueness và chiến lược zone placement.

### 8.1. Thứ tự khóa ghép là thứ tự từ điển

Với key:

```javascript
{ tenantId: 1, orderId: 1 }
```

không gian khóa được sắp theo:

```text
(TENANT-A, ORD-1)
(TENANT-A, ORD-2)
(TENANT-A, ORD-3)
(TENANT-B, ORD-1)
(TENANT-B, ORD-2)
...
```

Tức là `tenantId` quyết định miền chính; `orderId` chia nhỏ trong miền tenant.

Với key đảo:

```javascript
{ orderId: 1, tenantId: 1 }
```

trật tự lại ưu tiên `orderId`. Hai key có **cùng field nhưng không cùng cách phân phối hoặc routing**.

### 8.2. Khóa ghép tăng cardinality

Giả sử:

```text
tenantId có 100 giá trị.
Mỗi tenant có 1.000.000 orderId phân biệt.
```

Chọn `{ tenantId: 1 }` chỉ có 100 giá trị shard key, và mỗi tenant có thể chiếm một khoảng không thể chia nhỏ hơn theo key đó.

Chọn:

```javascript
{ tenantId: 1, orderId: 1 }
```

tăng số tổ hợp phân biệt. MongoDB có thêm không gian để split chunks **trong cùng tenant** theo `orderId`.

Điều này có thể cải thiện khả năng mở rộng khi tenant lớn; song phải xem `orderId` tăng liên tục và hệ thống có dồn insert vào phần cuối miền của một tenant không.

### 8.3. Không phải cứ nhiều field là tốt hơn

Khóa:

```javascript
{ tenantId: 1, region: 1, status: 1, createdAt: 1, orderId: 1 }
```

không tự tốt hơn khóa ngắn. Nhiều field làm tăng kích thước key, phức tạp hóa routing/upsert/updates và có thể không mang lợi ích nếu các query thực tế chỉ dùng field không phải prefix.

Cần ưu tiên field theo **access patterns** và mục tiêu phân phối, không tối đa hóa số field.

---

## 9. Prefix rule trong compound shard key

Nếu shard key là:

```javascript
{ tenantId: 1, orderId: 1 }
```

hãy so sánh:

```javascript
// Có equality trên toàn shard key:
db.orders.findOne({
  tenantId: "TENANT-A",
  orderId: "ORD-1001"
});
```

Query này thường target **một chunk/shard**.

```javascript
// Chỉ có prefix tenantId:
db.orders.find({
  tenantId: "TENANT-A"
});
```

Router có thể thu hẹp đến các range thuộc tenant A, nhưng tenant A có thể trải **nhiều chunks và shards**. Không bảo đảm chỉ một shard.

```javascript
// Thiếu prefix:
db.orders.find({
  orderId: "ORD-1001"
});
```

Vì không có `tenantId`, router thường **không thể xác định một miền prefix hẹp**, nên có thể scatter-gather qua nhiều shard.

### 9.1. Bảng routing minh họa

| Query | Có đầy đủ key? | Nhận xét |
| --- | --- | --- |
| `{ tenantId: "A", orderId: "O1" }` | Có | Thường target một shard. |
| `{ tenantId: "A" }` | Có prefix | Thu hẹp các range của tenant A; có thể nhiều shard. |
| `{ orderId: "O1" }` | Không | Thường phải broadcast hoặc target rộng. |
| `{ tenantId: "A", orderId: { $gte: "O1", $lt: "O9" } }` | Equality prefix + range | Có thể target những chunks giao với khoảng yêu cầu. |
| `{ tenantId: { $in: ["A", "B"] }, orderId: "O1" }` | Nhiều giá trị prefix | Có thể target tập range của A và B. |
| `{ status: "PAID" }` | Không | Không có điều kiện trên shard key, thường scatter-gather. |

Đây là dự đoán về routing, **không phải một kết quả `explain` cố định**. Placement thay đổi khi balancer chạy, và query planner có thể thêm những tối ưu khác tùy phiên bản.

### 9.2. Prefix của shard key khác prefix của index phụ

MongoDB cần một index hỗ trợ shard key, nhưng các query nghiệp vụ vẫn có thể cần index khác:

```javascript
// Shard key:
{ tenantId: 1, orderId: 1 }

// Index riêng để liệt kê đơn mới nhất của tenant:
{ tenantId: 1, createdAt: -1, _id: -1 }
```

Query:

```javascript
db.orders.find({
  tenantId: "TENANT-A",
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
```

Query có thể chỉ target các shard chứa tenant A; trên **mỗi shard được target**, index phụ giúp filter/sort. Không nhầm việc có shard key prefix với việc đã có một compound index tối ưu cho mọi `sort`.

---

## 10. Compound hashed shard key: kết hợp locality và phân phối

MongoDB hỗ trợ **compound hashed index** và dùng làm shard key. Chỉ **một field** trong một compound index được đánh dấu `"hashed"`; các field còn lại là ranged/non-hashed fields.

Ví dụ:

```javascript
{ tenantId: 1, orderId: "hashed" }
```

Hoặc:

```javascript
{ orderId: "hashed", createdAt: 1 }
```

Hoặc:

```javascript
{ region: 1, tenantId: 1, orderId: "hashed" }
```

**Hash chỉ áp lên field được chỉ định `"hashed"`**, không phải tự hash toàn bộ tuple `{ tenantId, orderId }` thành một giá trị duy nhất.

### 10.1. Mẫu A — non-hashed prefix, hashed suffix

```javascript
{
  tenantId: 1,
  orderId: "hashed"
}
```

Ý nghĩa sắp xếp:

```text
tenantId gốc
    |
    +--> hash(orderId) trong miền tenant
```

Tác dụng:

- Query có `tenantId` có thể thu hẹp những range thuộc tenant đó.
- `orderId` hashed có thể giúp tản document/insert **bên trong miền tenant**, nếu có đủ chunks và balancer phân bổ chúng.
- Hợp với hệ multi-tenant muốn giữ khả năng quản lý phạm vi tenant, có tenant lớn cần phân phối.
- Có thể hỗ trợ zone ranges trên prefix không hashed khi thiết kế zone hợp lệ.

Đánh đổi:

- Một tenant có ít document vẫn có thể nằm trên một shard, không tự tản đều.
- Một tenant cực lớn có thể trải nhiều shards, nên query chỉ theo tenant vẫn có thể chạm nhiều shards.
- Range query theo `orderId` gốc không còn có locality như `{ tenantId: 1, orderId: 1 }`.
- Hotspot theo **một giá trị orderId xuất hiện quá nhiều** không tự được phá ra thành nhiều chunk vì mọi document có cùng full shard key vẫn ở cùng một miền key.

### 10.2. Mẫu B — hashed prefix, non-hashed suffix

```javascript
{
  orderId: "hashed",
  createdAt: 1
}
```

Ý nghĩa:

```text
hash(orderId)
    |
    +--> createdAt sắp theo thứ tự trong từng hash prefix
```

Mẫu này có thể hữu ích khi phần lớn request truy cập theo `orderId`, muốn phân phối insert/order groups trước, rồi tận dụng suffix thời gian cho các query có đủ prefix.

Đánh đổi:

- Query chỉ có `createdAt` **không có `orderId`** thường target rộng.
- Không dùng hashed prefix để zone theo thứ tự `createdAt` gốc.
- Nếu tất cả document cho một orderId xuất hiện cùng lúc với cùng `createdAt`, key có thể vẫn thiếu khả năng tách workload.

### 10.3. Mẫu C — zone-friendly prefix

```javascript
{
  region: 1,
  customerId: "hashed"
}
```

Có thể dùng `region` làm non-hashed prefix để tổ chức zone ranges theo khu vực, trong khi `customerId` hashed giúp phân phối trong khu vực.

Tuy nhiên, việc tạo zone và pre-splitting compound hashed key **có điều kiện riêng**; không phải chỉ thêm `region` vào đầu là MongoDB tự ghim mọi dữ liệu EU vào một data center. Phải định nghĩa zone ranges, gán shards vào zones và kiểm tra balancer đã hội tụ.

---

## 11. So sánh ba lựa chọn khóa cho collection đơn hàng

Giả sử workload:

```text
40%  Lấy order theo tenantId + orderId.
30%  Liệt kê order mới nhất theo tenantId.
20%  Ghi orderId mới liên tục tăng.
10%  Báo cáo tổng hợp theo thời gian toàn hệ thống.
```

Ba phương án:

### Phương án 1 — `{ tenantId: 1, orderId: 1 }`

Ưu điểm:

- Full equality target tốt.
- Query chỉ `tenantId` có thể thu hẹp miền tenant.
- Range `orderId` trong tenant có locality.

Nhược điểm:

- Với tenant rất lớn đang có insert `orderId` tăng đơn điệu, có thể nóng ở cuối miền tenant.
- Nếu ghi tập trung vào một tenant, prefix này có thể tạo skew.

### Phương án 2 — `{ orderId: "hashed" }`

Ưu điểm:

- Tản insert trên các orderId phân biệt.
- Equality theo orderId target tốt.

Nhược điểm:

- Query chỉ theo tenant thường broadcast, vì tenantId **không nằm trong shard key**.
- Không đảm bảo locality cho các request liệt kê theo tenant.
- Range/orderId gốc không target tốt.

### Phương án 3 — `{ tenantId: 1, orderId: "hashed" }`

Ưu điểm:

- Query full tenant + orderId có thể target tốt.
- Có cơ hội phân phối ghi của tenant lớn theo hash.
- Query có prefix tenantId có thể giới hạn phạm vi so với hashed orderId thuần.

Nhược điểm:

- Query theo tenant có thể phải chạy trên nhiều shards nếu tenant trải rộng.
- Range theo orderId trong tenant mất lợi thế.
- Độ hiệu quả phụ thuộc cardinality, số chunks, initial distribution và tải từng tenant.

**Không có đáp án tuyệt đối.** Nếu 80% request là range `orderId` theo tenant, ranged compound có thể thắng. Nếu ghi theo orderId mới rất cao và lookup equality chiếm ưu thế, compound hashed thường đáng thử.

---

## 12. Phân phối đều không chỉ là số lượng document

Một shard chứa 1 triệu document nhỏ có thể dùng ít dung lượng và CPU hơn shard khác chứa 200.000 document rất lớn hoặc phải phục vụ query nặng.

Khi đánh giá shard key, phân biệt:

- **Data distribution:** số document, bytes và chunk ownership trên từng shard.
- **Read distribution:** số request và CPU/I/O cho reads trên mỗi shard.
- **Write distribution:** insert/update/delete, throughput và lock/IO pressure.
- **Query targeting:** trung bình một query chạm bao nhiêu shard.
- **Latency:** p50/p95/p99 từ góc nhìn ứng dụng, không chỉ độ trễ của một shard.
- **Range migration:** chunk moves, thời gian cân bằng, jumbo chunks và các operation bị ảnh hưởng.

Shard key tạo data distribution cân bằng **không đủ** nếu 90% query liên tục đọc dữ liệu của cùng một khách hàng/tenant, dẫn tới hot read shard.

### 12.1. Cardinality

Cardinality là số giá trị shard key phân biệt. Khóa ít giá trị:

```javascript
{ status: 1 } // "NEW", "PAID", "CANCELLED"...
```

thường rất kém để shard một collection lớn. Dù có 10 shard, số giá trị rất ít giới hạn khả năng chia nhỏ không gian shard key.

### 12.2. Frequency và skew

Giả sử `tenantId` có một triệu giá trị nhưng **một tenant chiếm 70% dữ liệu**. Cardinality cao ở toàn hệ thống không giải quyết riêng “hot tenant”.

Thêm field đủ phân biệt:

```javascript
{ tenantId: 1, orderId: "hashed" }
```

có thể mở khả năng phân chia dữ liệu của tenant lớn trên nhiều range/shard, nhưng cần đo sau khi balancer phân phối thật.

### 12.3. Monotonicity

Nếu field khóa luôn tăng, ranged sharding có nguy cơ hot range ở cuối. Hashed value thường giải quyết tốt hơn **vấn đề thứ tự tăng**, nhưng không giải quyết frequency nếu một giá trị khóa bị lặp lại quá nhiều.

### 12.4. Query patterns

Đếm workload theo query shape:

```text
GET /orders/{orderId}
GET /tenants/{tenantId}/orders
GET /tenants/{tenantId}/orders?from=...&to=...
POST /orders
GET /reports/orders?from=...&to=...
```

Shard key phải được chọn theo **trọng số thực của các request và chi phí của chúng**, không theo field “trông phân phối ngẫu nhiên nhất”.

---

## 13. Scatter-gather: khi nào router phải hỏi nhiều shard?

**Targeted query**: mongos dùng shard key condition để xác định các shard có thể chứa kết quả.

**Scatter-gather/broadcast**: mongos phải gửi query tới nhiều hoặc toàn bộ shard vì không thể xác định miền shard key đủ hẹp.

Ví dụ shard key:

```javascript
{ tenantId: 1, orderId: "hashed" }
```

Các truy vấn:

```javascript
// Equality toàn shard key: targeted.
db.orders.findOne({
  tenantId: "T1",
  orderId: "O100"
});

// Prefix tenantId: có thể chỉ các ranges của T1,
// nhưng T1 có thể trải trên nhiều shards.
db.orders.find({
  tenantId: "T1"
});

// Không có tenantId; chỉ orderId.
// Thường không target hiệu quả theo compound key.
db.orders.findOne({
  orderId: "O100"
});

// Không có shard key:
// thường scatter-gather.
db.orders.find({
  status: "PAID"
});
```

### 13.1. Scatter-gather không luôn sai

Một báo cáo phân tích toàn bộ dữ liệu có thể **cố ý** dùng parallel reads across shards:

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$region", total: { $sum: 1 } } }
]);
```

Nếu bài toán thật sự phải đọc toàn cluster, broadcast là hợp lý. Vấn đề là **request online tần suất cao** như “chi tiết một order” lại phải broadcast chỉ vì API không có shard key.

### 13.2. Có index phụ vẫn có thể broadcast

Ngay cả khi tạo:

```javascript
db.orders.createIndex({ status: 1 });
```

query chỉ theo `status` vẫn có thể được gửi tới mọi shard, rồi từng shard dùng index local. **Index local** giảm công việc trên một shard; **shard key** giúp giảm số shard phải liên hệ. Hai lớp tối ưu khác nhau.

### 13.3. Không bỏ qua filter shard key khi gọi Java

Nếu API biết cả `tenantId` và `orderId`, đừng chỉ gửi `orderId` vì nó “đã unique về business”. Full shard key predicate thường cải thiện target và đôi khi đáp ứng điều kiện của thao tác update/upsert. Thiết kế API/DTO nên giữ các field định tuyến cần thiết.

---

## 14. Quan hệ với sort, pagination và index

Giả sử query nóng:

```javascript
db.orders.find({
  tenantId: "T1",
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
```

Shard key:

```javascript
{ tenantId: 1, orderId: "hashed" }
```

không tự đảm bảo query đã dùng index hỗ trợ sort mới nhất. Có thể tạo **index phụ**:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
```

Cần hiểu:

- Shard key giúp mongos xác định **những shard có thể chứa tenant T1**.
- Index phụ giúp mỗi shard lọc và sort hiệu quả.
- Nếu tenant có dữ liệu trên nhiều shards, mongos có thể phải **merge-sort kết quả từ nhiều shard**.
- `limit(20)` không biến việc target nhiều shard thành chi phí bằng một shard.
- Deep pagination bằng `skip(100000)` có thể vẫn tốn tài nguyên dù index tốt.

### 14.1. Keyset pagination

Đối với thứ tự `(createdAt desc, _id desc)`, có thể dùng cursor pagination:

```javascript
const lastTs = ISODate("2026-11-14T07:00:00Z");
const lastId = ObjectId("6927b73c0000000000000002");

db.orders.find({
  tenantId: "T1",
  status: "PAID",
  $or: [
    { createdAt: { $lt: lastTs } },
    {
      createdAt: lastTs,
      _id: { $lt: lastId }
    }
  ]
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
```

Đây là mẫu pagination minh họa. Nếu `_id` có kiểu khác, phải truyền `lastId` cùng kiểu BSON. Trên nhiều shard, pagination/merge logic vẫn phải kiểm thử tính ổn định dưới concurrent writes.

---

## 15. Ràng buộc về index hỗ trợ shard key

MongoDB yêu cầu sharded collection có **index hỗ trợ shard key**:

- Index có thể là index đúng shard key.
- Hoặc compound index trong đó **shard key là prefix** của index.
- Nếu collection **trống**, thao tác `sh.shardCollection()` có thể tạo index hỗ trợ khi chưa có.
- Nếu collection **đã có dữ liệu**, phải tạo index hỗ trợ **trước khi** shard collection.
- Không tự drop/hide index cuối cùng còn hỗ trợ shard key, trừ những trường hợp hashed shard key index đặc biệt được MongoDB hỗ trợ theo phiên bản.

Ví dụ:

```javascript
// Shard key:
{ tenantId: 1, orderId: 1 }

// Index hỗ trợ, key là prefix:
{ tenantId: 1, orderId: 1, createdAt: -1 }

// Không hỗ trợ shard key theo prefix vì đảo thứ tự:
{ orderId: 1, tenantId: 1 }
```

### 15.1. Index tạo ra không phải shard key được chọn tự động

```javascript
db.orders.createIndex({ tenantId: 1, orderId: 1 });
```

chưa có nghĩa collection sharded. Cần thực hiện:

```javascript
sh.shardCollection(
  "commerce.orders",
  { tenantId: 1, orderId: 1 }
);
```

Trên `mongos` với quyền và điều kiện hợp lệ.

### 15.2. Hashed index và compound hashed

```javascript
// Chuẩn bị index:
db.orders.createIndex({
  tenantId: 1,
  orderId: "hashed"
});

// Dùng shard key tương ứng:
sh.shardCollection(
  "commerce.orders",
  { tenantId: 1, orderId: "hashed" }
);
```

Ví dụ tách thành hai phần để làm rõ khái niệm. Khi chạy thật, cần bảo đảm `db` đang là `commerce`, collection phù hợp, unique/index hiện có không xung đột và version hỗ trợ compound hashed shard key.

### 15.3. Collation

Nếu collection có default collation khác `"simple"`, việc shard có những yêu cầu riêng về collation và index supporting shard key. Có trường hợp `sh.shardCollection()` cần khai báo `{ locale: "simple" }` theo cú pháp `options`.

Không nên bỏ qua điều kiện này khi sharding collection có dữ liệu chuỗi/locale-specific. Shard key cần có cách so sánh ổn định trên cluster.

---

## 16. Unique index trong sharded collection

Đây là nguồn lỗi thiết kế phổ biến, đặc biệt với order ID và idempotency key.

### 16.1. Ranged sharded collection

MongoDB có thể enforce unique constraint khi unique index dùng **shard key hoặc compound index có shard key là prefix** theo điều kiện được hỗ trợ.

Ví dụ shard key:

```javascript
{ tenantId: 1, orderId: 1 }
```

Unique trên **toàn bộ cặp** có thể hợp lý:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { unique: true }
);
```

Điều đó đảm bảo `(tenantId, orderId)` duy nhất, **không** đảm bảo `orderId` duy nhất trên toàn bộ tenants.

Trong trường hợp shardCollection với unique trên chính shard key:

```javascript
sh.shardCollection(
  "commerce.orders",
  { tenantId: 1, orderId: 1 },
  true
);
```

Cần đáp ứng các yêu cầu về index đã có và collection status. Đừng chạy lệnh nếu chưa kiểm tra dữ liệu trùng.

### 16.2. Hashed shard key không thể `unique: true`

```javascript
// Không hợp lệ:
sh.shardCollection(
  "commerce.orders",
  { orderId: "hashed" },
  true
);
```

Hashed index không hỗ trợ uniqueness trực tiếp. Nếu `orderId` là business identity phải global-unique, cần **thiết kế id generation và cơ chế ràng buộc riêng được hỗ trợ**; đừng cho rằng hash routing tự chứng minh unique.

### 16.3. `_id` chưa chắc unique toàn cluster nếu không là shard key

Trong sharded collection mà `_id` **không phải shard key**, default `_id` index áp ràng buộc uniqueness **trong từng shard**, không mặc định trên toàn bộ cluster.

Nếu ứng dụng tự gán `_id` từ một bộ sequence không được điều phối, hai shard có thể lưu cùng `_id` trong những điều kiện phù hợp. Vì vậy:

- Tạo `_id` có độ unique đủ cao ở ứng dụng (ObjectId/UUID theo contract).
- Nếu business yêu cầu hard uniqueness toàn cluster, chọn kiến trúc key/index phù hợp.
- Không xem `_id` unique trên từng shard là bằng chứng đủ cho global business invariant.

### 16.4. Idempotency trong hệ multi-tenant

Giả sử mỗi tenant có `requestId` riêng:

```javascript
{
  tenantId: "T1",
  requestId: "REQ-123"
}
```

Unique phù hợp có thể là `(tenantId, requestId)`. Nếu yêu cầu duy nhất toàn cầu theo `requestId`, đây là quy tắc khác và phải được giải quyết ở thiết kế dữ liệu. Transaction không tự tạo unique constraint cho một field không phù hợp shard key.

---

## 17. `null`, missing và khóa có cardinality thấp

Sharded collection có thể có document thiếu một hay nhiều shard key fields. MongoDB xử lý các field thiếu tương tự giá trị `null` **khi phân chia chunk ranges**, nhưng việc định tuyến query còn có quy tắc riêng.

Ví dụ khóa ghép:

```javascript
{ tenantId: 1, orderId: 1 }
```

Các document:

```javascript
{ tenantId: "T1" }
{ tenantId: "T1", orderId: null }
```

có thể nằm trong cùng khoảng shard-key values tương đương `(T1, null)`.

### 17.1. Tại sao nguy hiểm?

Nếu 40% document thiếu `tenantId`, một lượng dữ liệu lớn có thể dồn vào những range có giá trị prefix `null`, làm giảm hiệu quả phân phối và khó target query.

Trong domain bắt buộc có tenant/order, **phải validation**:

```javascript
db.runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["tenantId", "orderId"],
      properties: {
        tenantId: { bsonType: "string", minLength: 1 },
        orderId: { bsonType: "string", minLength: 1 }
      }
    }
  },
  validationAction: "error"
});
```

Đây là **ví dụ validation** cho một collection đã tồn tại; không chạy lên production mà chưa hợp nhất schema hiện hành. Validator cần xét các rule khác có trong hệ thống.

### 17.2. Không dùng hashed để “chữa” mọi low-cardinality field

```javascript
{ status: "hashed" }
```

với 3 giá trị trạng thái vẫn chỉ có ít **distinct input values**, và vì vậy ít distinct hash values. Hash không biến mọi document có cùng status thành các giá trị hash khác nhau; tần suất của một giá trị vẫn cao.

Muốn phân phối tốt hơn, cần key có cardinality đủ lớn, có thể dùng compound key với field phân biệt khác.

---

## 18. Zone sharding và khóa ghép

**Zones** cho phép gắn các shard hoặc nhóm shard với những range shard key, phục vụ mục tiêu như locality, residency và phân phối tải.

Ví dụ muốn những tenant theo `region` được lưu ở các vùng được chỉ định:

```javascript
{ region: 1, customerId: "hashed" }
```

`region` là prefix **không hashed**, nên có thể thiết kế zone ranges theo region, còn `customerId` hashed giúp phân phối trong khu vực.

### 18.1. Zone ranges là khoảng nửa mở

Ví dụ minh họa về khái niệm trên một key đơn:

```text
Zone EU: ["EU", "US")
Zone US: ["US", "ZZ")
```

Khoảng cụ thể phải được chọn theo thứ tự so sánh của BSON/field, không tự lấy nhãn string làm một bản đồ địa lý.

Với key ghép, zone bounds phải có đủ cấu trúc prefix theo yêu cầu MongoDB. Chẳng hạn có thể phải dùng `MinKey`/`MaxKey` ở những trường phía sau để biểu diễn trọn miền prefix.

### 18.2. Hashed field không hỗ trợ locality theo giá trị gốc

Nếu key đơn:

```javascript
{ region: "hashed" }
```

thì các zone ranges trên shard key áp lên **giá trị hash của region**, không phải thứ tự `"EU" < "US"` trong domain. Khó dùng nó để gắn miền region thật vào data center một cách trực quan.

Do đó, nếu **data residency theo khu vực** là bắt buộc, cấu trúc có non-hashed prefix thường đáng xem xét hơn.

### 18.3. Pre-splitting compound hashed zones có điều kiện riêng

Khi shard một collection trống có **non-hashed prefix trước hashed field** và yêu cầu **initial distribution theo zones**, MongoDB đòi xác định các zone ranges và sử dụng option như `presplitHashedZones` đúng trường hợp.

Không nên giả định MongoDB tự chia đều mọi tenant/region tại thời điểm tạo collection. Tài liệu có quy định chi tiết và khác biệt giữa:

```javascript
{ hashedField: "hashed", region: 1 }    // hashed prefix
{ region: 1, hashedField: "hashed" }    // non-hashed prefix
```

Trong production, nên thiết kế zone range, kiểm tra balancer và kiểm thử placement trước khi nhận traffic.

---

## 19. Initial chunks và balancer: không phải mọi chiến lược khởi tạo giống nhau

MongoDB chia collection thành các chunks/ranges và balancer có thể di chuyển chúng giữa shard.

### 19.1. Shard collection đã có dữ liệu

Với collection populated, `sh.shardCollection` có thể khởi tạo một range lớn ban đầu rồi để balancer thực hiện phân phối theo điều kiện phù hợp. Không kết luận rằng sau khi sharding, dữ liệu đã lập tức cân bằng trên mọi shard.

### 19.2. Collection trống với ranged key

Khi không cấu hình zones, MongoDB có thể tạo **một chunk ban đầu bao phủ toàn không gian khóa**. Trong thời gian dữ liệu tăng, splitting/balancing dần phân bố chunks.

### 19.3. Collection trống với hashed key

Hashed sharding có thể hỗ trợ tạo các initial empty chunks và phân phối ban đầu trên nhiều shard, nhất là với hashed field ở prefix. Chi tiết **số chunks mặc định** phụ thuộc cấu trúc compound hashed key và phiên bản (ví dụ hành vi compound hashed-prefix thay đổi ở MongoDB 8.0).

Do đó, không hardcode giả định “mỗi shard luôn có hai chunk” trong tài liệu vận hành. Hãy xem phân phối thực tế sau thao tác và theo dõi balancer.

### 19.4. Balancer không tự sửa một key kém

Nếu mọi document có cùng shard key value, chunk không thể split ở giữa **một giá trị khóa duy nhất**. Hashing trên giá trị đó cũng cho cùng hash. Khi ấy có thể xuất hiện chunk lớn không thể chia hữu ích (*indivisible/jumbo* theo bối cảnh), và thêm shard không tự giải quyết được.

Phải tăng khả năng phân biệt của shard key, đổi key hoặc thay đổi mô hình dữ liệu.

---

## 20. Các ví dụ thiết lập trong `mongosh`

**Lưu ý an toàn:** tất cả lệnh `sh.shardCollection` dưới đây là ví dụ lựa chọn **độc lập**, không chạy tuần tự trên cùng `commerce.orders`. Một collection chỉ có một shard key pattern đang hoạt động ở một thời điểm. Chỉ chạy trên sharded cluster thử nghiệm với quyền phù hợp, qua `mongos`.

### 20.1. Phương án A — ranged key đơn

```javascript
// Trên mongos, collection thử nghiệm có dữ liệu cần index trước.
db.getSiblingDB("commerce").orders.createIndex({
  createdAt: 1
});

sh.shardCollection(
  "commerce.orders",
  { createdAt: 1 }
);
```

Phù hợp cho thử nghiệm query range thời gian nhưng cần đặc biệt đo nguy cơ write hotspot.

### 20.2. Phương án B — hashed key đơn

```javascript
db.getSiblingDB("commerce").orders.createIndex({
  orderId: "hashed"
});

sh.shardCollection(
  "commerce.orders",
  { orderId: "hashed" }
);
```

Tốt cho lookup equality và insert IDs đa dạng, nhưng range theo `orderId` hoặc queries tenant-only có thể target rộng.

### 20.3. Phương án C — ranged compound

```javascript
db.getSiblingDB("commerce").orders.createIndex({
  tenantId: 1,
  orderId: 1
});

sh.shardCollection(
  "commerce.orders",
  { tenantId: 1, orderId: 1 }
);
```

Thử với query theo tenant, range orderId; theo dõi hotspot khi orderId tăng tuần tự trong tenant lớn.

### 20.4. Phương án D — compound hashed

```javascript
db.getSiblingDB("commerce").orders.createIndex({
  tenantId: 1,
  orderId: "hashed"
});

sh.shardCollection(
  "commerce.orders",
  { tenantId: 1, orderId: "hashed" }
);
```

Thử với lookup tenant + orderId và workload write multi-tenant; theo dõi phân phối chunks của những tenant lớn.

### 20.5. Phương án E — hashed prefix

```javascript
db.getSiblingDB("commerce").orders.createIndex({
  orderId: "hashed",
  createdAt: 1
});

sh.shardCollection(
  "commerce.orders",
  { orderId: "hashed", createdAt: 1 }
);
```

Thử với query theo orderId và các thao tác cần khoảng thời gian **trong cùng orderId**; không kỳ vọng query chỉ theo `createdAt` target tốt.

### 20.6. Không cần `sh.enableSharding` trong mọi phiên bản

Từ MongoDB 6.0, khi shard một collection không còn bắt buộc phải gọi trước `sh.enableSharding()` để bật sharding cho database theo cách cũ. Tuy nhiên, **không nên bỏ qua đặc tính của phiên bản đang dùng**; tài liệu hoặc automation cho cluster cũ có thể khác.

---

## 21. Kiểm tra topology và phân phối sau khi shard

Trên `mongos`:

```javascript
db.hello();
sh.status();
```

Đây là công cụ xem cluster metadata; các field output tùy MongoDB version.

Một helper hữu ích:

```javascript
db.getSiblingDB("commerce").orders.getShardDistribution();
```

Nó in thống kê phân phối dữ liệu/chunks giữa các shard. Cần lưu ý output có thể là estimates, và một số trường hợp sau shutdown không sạch có thể tạo thống kê lệch tạm thời.

### 21.1. Đọc query plan để biết shard targeting

```javascript
db.getSiblingDB("commerce").orders.find({
  tenantId: "T1",
  orderId: "O100"
}).explain("executionStats");
```

So với:

```javascript
db.getSiblingDB("commerce").orders.find({
  status: "PAID"
}).explain("executionStats");
```

Trên sharded cluster, explain có thể hiển thị thông tin theo shard/stage, và số shard thực sự tham gia. Cách trình bày chi tiết thay đổi theo phiên bản và execution engine.

Điều nên quan sát:

- Query target bao nhiêu shard?
- Mỗi shard scan bao nhiêu keys/documents?
- Có index phù hợp filter/sort không?
- Trả bao nhiêu document và byte?
- Thời gian ở router và các shard có khác nhau nhiều không?
- Query trả ít kết quả có đang broadcast tới cả cluster không?

**Một lần `explain` nhanh chưa chứng minh p99 API nhanh**; phải quan sát workload thực tế dưới concurrency.

### 21.2. Đừng chỉ nhìn kích thước chunk

Một cluster cân bằng bytes nhưng mất cân bằng read/write operations có thể vẫn bị nóng một shard. Cần kết hợp metrics shard-level CPU, I/O, ops/sec, query latency, cursor/connection pool và network.

---

## 22. Dùng `analyzeShardKey` để đánh giá ứng viên

Từ MongoDB **7.0**, có khả năng phân tích shard key dựa trên **đặc tính khóa và sampled query workload**.

Trên collection được hỗ trợ:

```javascript
db.getSiblingDB("commerce").orders.analyzeShardKey({
  tenantId: 1,
  orderId: "hashed"
});
```

Kết quả có thể chứa:

- **`keyCharacteristics`**: cardinality, frequency, monotonicity.
- **`readWriteDistribution`**: ước lượng phân phối đọc/ghi theo sampled queries.

Muốn có metrics read/write hữu ích, cần cấu hình query sampling qua `configureQueryAnalyzer` theo tài liệu và quyền hạn phù hợp. Không nên lấy kết quả “không có sample” làm bằng chứng workload sẽ cân bằng.

### 22.1. Một quy trình đánh giá ứng viên

1. Lấy các query shape phổ biến từ tracing/profiler/log đã ẩn dữ liệu nhạy cảm.
2. Liệt kê ứng viên ranged, hashed và compound.
3. Phân tích cardinality/frequency và monotonicity.
4. Ước lượng targeted vs scatter-gather cho các query quan trọng.
5. Thử mẫu dữ liệu và concurrency sát sản xuất trong cluster staging.
6. Xem writes/sec/CPU, số chunks, phân phối theo shard.
7. So sánh p95/p99 latency, không chỉ throughput tổng.
8. Đánh giá chi phí migration/resharding và ràng buộc unique/zones.

Không chọn key chỉ bằng cách tìm field có giá trị ngẫu nhiên nhất. Nếu app luôn query theo `tenantId`, hashed `orderId` thuần có thể khiến query tenant-only tốn hơn dù dữ liệu chia đều.

---

## 23. Đổi shard key: refine khác reshard

Shard key chọn ban đầu không phải bất biến vĩnh viễn, nhưng thay đổi nó có **chi phí vận hành đáng kể**.

### 23.1. `refineCollectionShardKey`: thêm suffix

Ví dụ key hiện tại:

```javascript
{ tenantId: 1 }
```

Muốn tăng số tổ hợp phân biệt:

```javascript
{ tenantId: 1, orderId: 1 }
```

Có thể dùng cơ chế refine:

```javascript
db.adminCommand({
  refineCollectionShardKey: "commerce.orders",
  key: { tenantId: 1, orderId: 1 }
});
```

Ví dụ mang tính **mô tả**; trước khi chạy phải có index hỗ trợ key mới và đáp ứng mọi điều kiện refine của version/cluster.

Refine **chỉ thêm field ở phần cuối**, không đổi thứ tự/type của prefix hiện hữu. Không dùng refine để đổi:

```text
{ tenantId: 1 }
    -->
{ tenantId: "hashed" }
```

vì đó là thay đổi kiểu của field đầu, không phải thêm suffix.

### 23.2. `reshardCollection`: chọn key khác

Từ MongoDB **5.0**, hỗ trợ reshard collection để chuyển sang shard key khác, ví dụ:

```javascript
// Thay key ranged bằng compound hashed (minh họa):
sh.reshardCollection(
  "commerce.orders",
  { tenantId: 1, orderId: "hashed" }
);
```

Resharding có những điều kiện về version, tài nguyên, disk, replication, index, migration và phạm vi collection. Không nên chạy như một query tùy ý giữa giờ cao điểm.

### 23.3. Chọn refine hay reshard?

- **Refine**: khi muốn bổ sung suffix để tăng cardinality/mức phân giải nhưng vẫn giữ prefix và kiểu key hiện tại.
- **Reshard**: khi cần thay đổi chiến lược phân phối thực sự, ví dụ ranged sang hashed, đảo field hoặc đổi field chính.
- Refine **không tự bảo đảm** dữ liệu đang lệch sẽ được phân phối lại tối ưu ngay.
- Reshard thường xử lý vấn đề phân phối mạnh hơn nhưng tốn tài nguyên/đòi kế hoạch chặt chẽ hơn.

Theo MongoDB, cần đánh giá khả năng reshard khi mục tiêu là sửa data distribution lệch nghiêm trọng; refine hữu ích khi chỉ cần key phân biệt tốt hơn và không thể/không cần thay toàn bộ key.

### 23.4. Đừng thay shard key bằng một `createIndex`

Tạo index:

```javascript
db.orders.createIndex({ tenantId: 1, orderId: "hashed" });
```

không thay shard key nếu collection hiện đang shard theo `{ createdAt: 1 }`. Việc đổi placement phải qua cơ chế refine/reshard được hỗ trợ.

---

## 24. Java MongoDB Sync Driver: query có shard key

Trong Java, phần lớn CRUD trên sharded cluster được thực hiện giống collection thường. Điều quan trọng là **kết nối tới `mongos`/endpoint sharded cluster hợp lệ** và đưa predicate định tuyến khi có thể.

### 24.1. Tạo MongoClient

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public final class ShardedClientExample {

    public static MongoClient createClient() {
        return MongoClients.create(
            "mongodb://router1.example.net:27017," +
            "router2.example.net:27017/" +
            "?retryWrites=true"
        );
    }

    public static MongoCollection<Document> orders(
            MongoClient client
    ) {
        return client.getDatabase("commerce")
            .getCollection("orders");
    }
}
```

URI minh họa. Production phải có TLS, auth, secret management, replica/sharded topology đúng và timeout phù hợp. Không dùng trực tiếp hostname một `mongod` shard làm thay thế cho mongos, đặc biệt khi cần truy cập nhiều shard.

### 24.2. Query targeted theo compound hashed key

Giả sử shard key:

```javascript
{ tenantId: 1, orderId: "hashed" }
```

Java:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import static com.mongodb.client.model.Filters.*;

public class OrderQueries {

    public static Document findOrder(
            MongoCollection<Document> orders,
            String tenantId,
            String orderId
    ) {
        return orders.find(
            and(
                eq("tenantId", tenantId),
                eq("orderId", orderId)
            )
        ).first();
    }
}
```

Ứng dụng không cần tính hash; mongos/server tự làm. `tenantId` + `orderId` là thông tin giúp router xác định full shard key tuple.

### 24.3. Liệt kê đơn của một tenant

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import java.util.ArrayList;
import java.util.List;

public class TenantOrders {

    public static List<Document> latest(
            MongoCollection<Document> orders,
            String tenantId
    ) {
        return orders.find(
            Filters.eq("tenantId", tenantId)
        ).sort(
            Sorts.orderBy(
                Sorts.descending("createdAt"),
                Sorts.descending("_id")
            )
        ).limit(20).into(new ArrayList<>());
    }
}
```

Nếu tenant có data trên nhiều shards, truy vấn có thể phải merge kết quả từ các shards ấy. Để sort/filter hiệu quả, cần index phù hợp với query trên các shard. Trong API thật, nên phân trang với cursor thay vì lặp `skip` sâu.

### 24.4. Update và full shard key

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public class OrderUpdates {

    public static UpdateResult markPaid(
            MongoCollection<Document> orders,
            String tenantId,
            String orderId
    ) {
        return orders.updateOne(
            Filters.and(
                Filters.eq("tenantId", tenantId),
                Filters.eq("orderId", orderId),
                Filters.eq("status", "PENDING")
            ),
            Updates.set("status", "PAID")
        );
    }
}
```

Ví dụ dùng equality trên full compound shard key, giúp định tuyến và tránh đổi trạng thái không đúng. Để bảo vệ các bất biến phức tạp, còn phải xét concurrency, unique index, retry và idempotency.

Một số update/upsert có quy tắc đặc biệt khi thiếu shard key hoặc thay shard key; không áp chung mọi quy tắc phiên bản cũ cho driver mới. Luôn đối chiếu operation contract trong MongoDB version đang vận hành.

### 24.5. Không cố băm field ở Java

Không làm:

```java
int hash = orderId.hashCode();
```

rồi coi đó là MongoDB hashed shard key. `String.hashCode()` của Java **không phải** hash function dùng cho MongoDB hashed index.

Truyền giá trị gốc; mongos tự tính hash. Nếu cần quan sát hashed value để debug, dùng công cụ được MongoDB cung cấp như `convertShardKeyToHashed()` trong `mongosh`, không tự tái tạo bằng hash ngôn ngữ tùy ý.

---

## 25. Case study 1: SaaS đa tenant

Hệ thống có:

- 50.000 tenants.
- 1% tenants chiếm 60% số đơn.
- Hầu hết request chứa `tenantId`.
- Các tenant lớn ghi rất nhiều order mới mỗi giây.
- Báo cáo chủ yếu xem đơn của một tenant.

Ba lựa chọn:

| Shard key | Điểm mạnh | Rủi ro |
| --- | --- | --- |
| `{ tenantId: 1 }` | Tenant-local routing đơn giản. | Tenant lớn có thể thành hot key/chunk không chia nhỏ. |
| `{ tenantId: 1, createdAt: 1 }` | Range/time trong tenant thuận lợi. | Timestamp tăng trong tenant lớn có thể nóng ở range cuối. |
| `{ tenantId: 1, orderId: "hashed" }` | Có thể chia tenant lớn theo hash của ID. | Range theo thời gian/orderId không còn local như ranged; tenant có thể trải nhiều shards. |

**Hướng đánh giá**: lấy sampled read/write patterns, đo các tenant lớn, so số shard per query và p99 của request “latest orders”. Nếu buộc dùng hashed suffix, tạo index phụ `{tenantId:1, createdAt:-1}` cho sort, rồi đo merge cost.

### 25.1. Một tenant có thể trải nhiều shard

Nếu tenant rất lớn, compound hashed key có thể cho phép tách các order của tenant thành nhiều chunks thuộc nhiều shards. Đây là lợi thế về write distribution nhưng là đánh đổi khi query `"tất cả order của tenant"`.

Đừng hứa “có tenantId prefix nên mọi read chỉ chạm đúng một shard”.

### 25.2. Một tenant quá nóng vẫn có thể vượt khả năng hệ thống

Nếu mọi request đều cập nhật **cùng một document counter** của tenant, thay shard key để phân phối order **không làm update trên một document trở thành nhiều update song song**. Phải thiết kế counter sharding, batching hoặc model khác nếu đúng bottleneck là một document duy nhất.

---

## 26. Case study 2: event log theo thời gian

Dữ liệu:

```javascript
{
  _id: ObjectId(),
  applicationId: "APP-A",
  ts: ISODate("2026-11-14T09:15:00Z"),
  eventId: "EVT-1001",
  level: "INFO"
}
```

Write stream: hàng trăm nghìn events mỗi phút, `ts` tăng liên tục.

### 26.1. Key `{ ts: 1 }`

Lợi thế: truy vấn theo khoảng thời gian có khả năng target các ranges phù hợp.

Rủi ro: tất cả write mới tập trung vào MaxKey range, dễ tạo hot shard.

### 26.2. Key `{ eventId: "hashed" }`

Lợi thế: phân tán event IDs đa dạng.

Rủi ro: query “tất cả events trong 5 phút” thiếu shard key sẽ broadcast, có thể tốn nhiều I/O/CPU và network.

### 26.3. Key `{ applicationId: 1, eventId: "hashed" }`

Lợi thế: gắn ứng dụng với prefix, có thể phân phối events nhiều theo hash.

Rủi ro: truy vấn theo thời gian trong từng application vẫn có thể chạy trên nhiều shards và cần index khác `{ applicationId:1, ts:-1 }`.

### 26.4. Khi nào nên xem mô hình khác?

Với logs/time-series, có thể phù hợp sử dụng **time series collections**, retention/TTL, pre-aggregation hoặc pipeline ingestion riêng. Time-series sharding có **quy tắc shard key riêng theo phiên bản**; không áp dụng mọi nhận xét về ordinary collection một cách nguyên xi.

---

## 27. Time series collections: lưu ý đặc biệt

Nếu dữ liệu là time-series collection:

```javascript
{
  ts: ISODate("2026-11-14T09:15:00Z"),
  meta: {
    sensorId: "S1",
    region: "VN"
  },
  temperature: 28.5
}
```

MongoDB có các ràng buộc shard key riêng đối với `metaField` và `timeField`:

- `metaField` có thể được dùng làm ranged hoặc hashed shard key theo những điều kiện được hỗ trợ.
- `timeField` nếu được dùng trong shard key phải ở vị trí thích hợp của pattern và theo kiểu ranged.
- **Từ MongoDB 8.0, shard key có `timeField` đối với time series collection bị đánh dấu deprecated.**
- Một field thời gian tăng đơn điệu thường không nên là shard key đơn độc vì hotspot.

**Không lấy ví dụ `sh.shardCollection("logs.events",{ts:1})` dành cho ordinary collection rồi áp trực tiếp vào time series collection mà bỏ qua constraints riêng.** Cần tra tài liệu version và thiết kế theo metadata cùng query workload.

---

## 28. Những sai lầm phổ biến

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Chọn hashed luôn nhanh hơn ranged.” | Hashed cải thiện phân phối trong nhiều trường hợp, nhưng range queries có thể scatter-gather. |
| “Ranged luôn chỉ target một shard.” | Range predicate có thể giao với nhiều chunks trên nhiều shards. |
| “Dùng `createdAt` làm ranged key là tối ưu cho mọi ứng dụng logs.” | Timestamp tăng liên tục có nguy cơ hot MaxKey range. |
| “Hash luôn tản đều cả khi key chỉ có ba giá trị.” | Cardinality thấp vẫn giới hạn số distinct hash values. |
| “Một hot tenant được giải quyết chỉ bằng `{tenantId:1}`.” | Cùng giá trị tenantId có thể nằm trong một chunk không tách nhỏ. |
| “Compound key dùng cùng field thì thứ tự không quan trọng.” | `{tenantId:1,orderId:1}` và `{orderId:1,tenantId:1}` có routing/locality khác nhau. |
| “Prefix equality chắc chắn target một shard.” | Prefix có thể bao trùm nhiều chunks/shards. |
| “Cần tự hash orderId trong Java.” | MongoDB tự tính; Java `hashCode()` không tương thích. |
| “Hashed index có thể `unique:true`.” | MongoDB không hỗ trợ unique constraint trên hashed index. |
| “Default `_id` index bảo đảm unique toàn cluster khi `_id` không phải shard key.” | `_id` uniqueness có thể chỉ được enforce trên từng shard. |
| “Shard key index luôn đủ cho mọi query sort.” | Thường cần index phụ trên mỗi shard. |
| “Có index `status` thì query status chỉ gửi một shard.” | Index local không thay shard-key routing; vẫn có thể broadcast. |
| “Dùng field mảng làm hashed shard key.” | Hashed indexes không hỗ trợ multikey/array. |
| “Hash Double 2.2 khác 2.3.” | Floating-point bị cắt về integer trước hash, có thể collision. |
| “Compound hashed nghĩa là hash toàn bộ tuple.” | Chỉ một field được đánh dấu `"hashed"`. |
| “`{region:"hashed"}` zone được theo alphabet region.” | Zones trên hashed field dùng hash ranges, không giá trị gốc. |
| “Sharding xong dữ liệu ngay lập tức cân bằng.” | Initial chunks/balancer có quá trình phân phối, phụ thuộc version/topology. |
| “Dữ liệu đều đồng nghĩa traffic đều.” | Read/write hotspots có thể còn dù bytes cân bằng. |
| “Collection trống thì cần tạo mọi index trước.” | MongoDB có thể tạo supporting shard key index khi cần. |
| “Collection đã có dữ liệu không cần shard key index.” | Populated collection phải có supporting index trước. |
| “`createIndex` làm đổi shard key.” | Chỉ tạo chỉ mục; cần shard/refine/reshard riêng. |
| “Refine có thể đổi ranged thành hashed.” | Refine chỉ thêm suffix, không đổi prefix/type. |
| “Reshard luôn nhẹ và miễn phí.” | Là tác vụ thay đổi placement, tốn tài nguyên, cần kế hoạch. |
| “Một lần `explain` là đủ chọn key.” | Cần workload sampling, phân phối write và p95/p99 dưới tải. |

---

## 29. Bài tập vận dụng

### Bài 1 — Key tăng đơn điệu

Collection `events` có 100 triệu bản ghi, mỗi giờ thêm vài triệu document. Mọi insert mới có `ts` tăng.

**Hỏi:** Rủi ro của key `{ ts: 1 }`?

**Gợi ý:** Insert mới tập trung vào range đầu cao `MaxKey`, tạo write hotspot dù query theo thời gian được target tốt.

### Bài 2 — Equality và range với hashed

Shard key:

```javascript
{ userId: "hashed" }
```

So sánh:

```javascript
db.users.findOne({ userId: "U100" });

db.users.find({
  userId: { $gte: "U100", $lt: "U900" }
});
```

**Gợi ý:** Equality có thể target một hash range, còn range trên userId gốc không tương ứng range hash nên thường chạm nhiều shard.

### Bài 3 — Cardinality thấp

Collection có 800 triệu document, field `status` chỉ có 4 giá trị. Có nên shard theo `{ status: "hashed" }` để tản đều hơn không?

**Đáp án:** Không phù hợp. Hash vẫn chỉ tạo các giá trị hash ứng với bốn distinct statuses; frequency cao, chunk có thể không chia thêm hữu ích. Cần field có cardinality cao hơn.

### Bài 4 — Query theo compound key

Key:

```javascript
{ tenantId: 1, orderId: 1 }
```

**Hỏi:** Query nào có thể target tốt hơn?

```javascript
// A
{ tenantId: "T1", orderId: "O10" }

// B
{ tenantId: "T1" }

// C
{ orderId: "O10" }
```

**Đáp án:** A có full key, target hẹp nhất về lý thuyết; B có prefix, có thể chạm nhiều shards; C không có prefix nên thường target rộng.

### Bài 5 — Khóa ghép đảo thứ tự

So sánh:

```javascript
{ tenantId: 1, orderId: 1 }
{ orderId: 1, tenantId: 1 }
```

**Hỏi:** Nếu 80% API filter theo tenant, key nào có locality/query targeting phù hợp hơn?

**Gợi ý:** Đặt `tenantId` làm prefix, nhưng vẫn phải xem tải của tenant lớn và tính đơn điệu của suffix.

### Bài 6 — Compound hashed

Key:

```javascript
{ region: 1, customerId: "hashed" }
```

**Hỏi:** Có phải MongoDB băm cả `region + customerId` thành một hash?

**Đáp án:** Không. `region` giữ giá trị gốc/range, chỉ `customerId` được hashed.

### Bài 7 — Global uniqueness

Sharded collection dùng `{ orderId: "hashed" }`; nhóm phát triển muốn `sh.shardCollection(..., true)` để chắc chắn `orderId` duy nhất.

**Đáp án:** Không được, hashed shard key không hỗ trợ unique constraint trực tiếp. Cần thiết kế ràng buộc identity khác theo quy tắc sharded collection.

### Bài 8 — Dùng `_id` làm bằng chứng uniqueness

Collection shard theo `{ tenantId: 1 }`, `_id` không thuộc shard key. Có chắc `_id` được MongoDB enforce duy nhất toàn cluster không?

**Đáp án:** Không; mặc định `_id` index có thể chỉ enforce trong từng shard. Cần cơ chế sinh ID và constraints thích hợp.

### Bài 9 — Hash Double

Nếu field numeric chứa các Double `2.2`, `2.3`, `2.9`, hashed index có cho hash khác nhau không?

**Gợi ý:** MongoDB cắt floating-point về integer 64-bit trước hash; cả ba có thể cùng hash. Không chọn field này như hashed key có độ phân biệt cao.

### Bài 10 — Refine hay reshard?

Key hiện tại:

```javascript
{ tenantId: 1 }
```

Đề xuất A:

```javascript
{ tenantId: 1, orderId: 1 }
```

Đề xuất B:

```javascript
{ orderId: "hashed" }
```

**Gợi ý:** A có thể là **refine** nếu thỏa điều kiện; B cần **reshard** vì đổi key hoàn toàn.

### Bài 11 — Zone placement

Một doanh nghiệp phải giữ dữ liệu ở các region khác nhau và đồng thời muốn phân phối customer trong mỗi region.

**Gợi ý:** Cân nhắc non-hashed region prefix cùng hashed customer suffix và cấu hình zones hợp lệ; cần kiểm thử initial splitting/balancer chứ không chỉ tạo key pattern.

### Bài 12 — Index phụ

Shard key `{tenantId:1,orderId:"hashed"}`; query nóng liệt kê đơn mới theo tenant và `createdAt`.

**Gợi ý:** Thêm index phụ thích hợp như `{tenantId:1,createdAt:-1}` trên collection và đo merge sort khi tenant trải nhiều shards.

### Bài 13 — Hot tenant không chia nhỏ

Một tenant chiếm 80% traffic, mọi request cập nhật cùng document thống kê tồn kho.

**Gợi ý:** Hashing `orderId` của collection orders không phân phối những update vào **cùng một document**. Cần thiết kế lại counter/workload, không chỉ thay shard key orders.

### Bài 14 — Initial distribution

Collection ranged sharded mới trống, team kỳ vọng ngay lập tức có 100 chunks cân bằng trên 10 shards.

**Gợi ý:** Không được mặc định. Phân phối ban đầu phụ thuộc loại key, zones, version và balancer; phải quan sát `sh.status()`/distribution thực.

### Bài 15 — Kiểm tra trước production

Bạn có hai ứng viên:

```javascript
A: { tenantId: 1, createdAt: 1 }
B: { tenantId: 1, orderId: "hashed" }
```

Hãy đề xuất một phép thử so sánh.

**Gợi ý:** Sinh workload đại diện có tenant lớn, đo inserts/sec theo shard, p95/p99 của query full key và latest orders, số shard per query, chunks/data skew, CPU/I/O và thời gian migration.

---

## 30. Quy trình chọn shard key cho một hệ thống thật

### Bước 1 — Xác định điều kiện phải giữ

Ghi rõ:

- Khóa business nào phải unique, phạm vi uniqueness là gì?
- Có yêu cầu data residency/zones không?
- Có collection time-series với hạn chế key riêng không?
- Có tenant cực lớn hoặc document hot không?
- Query nào phải đáp ứng p99 cụ thể?

### Bước 2 — Liệt kê top query shapes

Ví dụ:

| Query shape | Tỷ trọng | Yêu cầu |
| --- | ---: | --- |
| `tenantId + orderId` | 40% | Single lookup nhanh. |
| `tenantId + createdAt range` | 30% | Lọc/sort gần đây. |
| Insert order mới | 20% | Write phân phối. |
| Báo cáo toàn cluster | 10% | Có thể chấp nhận aggregate cross-shard. |

Số liệu giả định để minh họa. Trong thực tế phải thu từ tracing/sampling và cân nhắc cost per query chứ không chỉ request count.

### Bước 3 — Lập danh sách ứng viên

```javascript
{ tenantId: 1, orderId: 1 }
{ orderId: "hashed" }
{ tenantId: 1, orderId: "hashed" }
{ tenantId: 1, createdAt: 1 }
```

Không đưa một ứng viên vào production trước khi kiểm tra version/index/unique/zones.

### Bước 4 — Ước lượng phân phối

Với mỗi key, phân tích:

- Cardinality.
- Frequency của các giá trị phổ biến nhất.
- Monotonicity của thành phần ranged.
- Hot tenants.
- Dung lượng/chunk histogram.
- Dự báo query targeting theo prefix và range.

### Bước 5 — Đo trên workload giống production

Chạy trên staging có số shard và tỷ lệ dữ liệu đủ đại diện. Theo dõi:

- Throughput insert/update/read.
- Số shard bị chạm cho từng query.
- p50/p95/p99 latency.
- CPU/disk/network theo shard.
- Tốc độ và chi phí chunk migrations.
- Performance của index phụ và sort.
- Ảnh hưởng lên transaction/uniqueness nếu có.

### Bước 6 — Chuẩn bị triển khai

1. Xác nhận cluster/topology/router.
2. Kiểm tra supporting shard key index.
3. Kiểm tra dữ liệu trùng, thiếu key, null và multikey.
4. Kiểm tra collation và unique constraints.
5. Xác nhận zone placement nếu cần.
6. Đánh giá initial chunk distribution/balancer.
7. Có backup, rollback/reshard plan và giám sát.
8. Thực hiện migration theo change management.
9. Xác nhận query routing sau triển khai.

### Bước 7 — Giám sát sau khi đưa vào chạy

Ngay cả shard key hợp lý ban đầu cũng có thể trở nên kém khi:

- Có tenant mới chiếm phần lớn traffic.
- API chuyển từ lookup equality sang nhiều range queries.
- Dung lượng tăng và key xuất hiện nhiều null.
- Collection được thêm index mới, đổi query shape.
- Thay đổi số shard hoặc zone policies.
- Workload hot read chuyển sang một vùng dữ liệu cụ thể.

Theo dõi định kỳ `analyzeShardKey`, `getShardDistribution()`, query profiler/tracing và các chỉ số theo shard. Nếu key không còn phù hợp, xem refine hoặc reshard có kế hoạch.

---

## 31. Tài liệu MongoDB chính thức

- [Ranged Sharding](https://www.mongodb.com/docs/manual/core/ranged-sharding/): chia khoảng theo shard key.
- [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/): hashed index và compound hashed shard keys.
- [Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/): cardinality, frequency, monotonicity và routing.
- [Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-shard-key/): vai trò, cập nhật và các hạn chế của shard key.
- [Shard Key Indexes](https://www.mongodb.com/docs/manual/core/sharding-shard-key-indexes/): index hỗ trợ, unique constraints và version-dependent exceptions.
- [Hashed Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-hashed/): floating point, arrays, uniqueness và covered query limitations.
- [Data Partitioning with Chunks](https://www.mongodb.com/docs/manual/core/sharding-data-partitioning/): chunk boundaries, initial distribution và migration.
- [Zones](https://www.mongodb.com/docs/manual/core/zone-sharding/): zone ranges và placement.
- [`sh.shardCollection()`](https://www.mongodb.com/docs/manual/reference/method/sh.shardCollection/): cú pháp shard collection, unique, collation và options.
- [`db.collection.analyzeShardKey()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.analyzeShardKey/): đánh giá shard key trên sampled workload.
- [`db.collection.getShardDistribution()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.getShardDistribution/): xem phân bố dữ liệu giữa các shard.
- [Change a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-change-a-shard-key/): refine và reshard.
- [Refine a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-refine-a-shard-key/): thêm suffix vào shard key.
- [Reshard a Collection](https://www.mongodb.com/docs/manual/core/sharding-reshard-a-collection/): đổi shard key hoặc phân phối lại dữ liệu theo phiên bản được hỗ trợ.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/): kết nối và CRUD qua driver.

Một số chi tiết về initial chunks, balancer, time-series collections, index restrictions và resharding thay đổi giữa các phiên bản. Trước khi triển khai, đối chiếu tài liệu đúng **server version, FCV, mongosh và Java driver** của cluster đang dùng.

---

## 32. Kết luận

**Ranged sharding** chia theo những khoảng liên tục của shard key gốc: thuận lợi cho query theo range và locality, nhưng có nguy cơ hot range khi field tăng/giảm đơn điệu.

**Hashed sharding** dùng hash của một field để phân phối các giá trị khác nhau rộng hơn: thường có lợi cho insert tăng tuần tự và equality lookups, nhưng giảm khả năng định tuyến chính xác các truy vấn range trên field gốc; hashed index còn có giới hạn về unique, multikey và floating-point.

**Compound shard key** kết hợp nhiều field để tăng cardinality và cân bằng routing với phân phối. Thứ tự prefix rất quan trọng. Với **compound hashed shard key**, chỉ một field được hash: `{tenantId:1,orderId:"hashed"}` và `{orderId:"hashed",tenantId:1}` không có cùng hiệu quả locality/targeting.

Để chọn khóa phù hợp, cần đo **cardinality + frequency + monotonicity + query shapes + uniqueness + zone requirements** dưới tải đại diện. Index phụ giải quyết access pattern **trên shard**, shard key giải quyết **data placement và mongos routing**. Đừng đánh đồng hai vai trò.

**Shard key tốt không chỉ chia dữ liệu thành nhiều phần — nó còn giúp phần lớn request tìm đúng phần dữ liệu với ít công việc phân tán nhất.**
