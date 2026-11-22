# Truy vấn định tuyến đúng shard và truy vấn scatter-gather trong MongoDB

Khi dữ liệu tăng đến mức một máy chủ khó đáp ứng đủ dung lượng hoặc lưu lượng, MongoDB cho phép phân phối document của một collection trên nhiều **shard**. Nhưng việc thêm shard chỉ có ý nghĩa khi ứng dụng hiểu **một truy vấn được gửi tới shard nào**. Một câu `find()` có thể chỉ cần đi đến đúng shard chứa document, hoặc phải gửi yêu cầu tới mọi shard rồi chờ hợp nhất kết quả.

Hai cách thực thi thường được gọi là:

- **Targeted query**: bộ định tuyến có thể xác định một shard hoặc một **tập con** các shard cần truy vấn nhờ điều kiện trên shard key. Khi xác định được **duy nhất một shard**, ta có một *single-shard query*.
- **Scatter-gather query**: bộ định tuyến phải **phát tán yêu cầu** đến nhiều shard, thường là tất cả shard đang liên quan tới collection, rồi **thu thập và hợp nhất** các kết quả.

Chủ đề của bài học là **Truy vấn định tuyến đúng shard và truy vấn scatter gather**, trong chương **Sharding** của module **Database Engine Document MongoDB**. Mục tiêu không chỉ là nhớ “có shard key thì nhanh”, mà là hiểu **điều kiện nào giúp `mongos` thu hẹp phạm vi**, các trường hợp compound/hashed/range shard key, vai trò của index trên từng shard, cách đọc `explain()` và cách tránh tối ưu làm sai ngữ nghĩa nghiệp vụ.

## 1. Sharding thay đổi đường đi của một truy vấn như thế nào?

Trong một replica set không sharding, driver chọn một member phù hợp với read preference và gửi truy vấn đến replica set đó. Trong một **sharded cluster**, ứng dụng thông thường kết nối tới **`mongos`**, thành phần định tuyến truy vấn đến các shard:

```text
                ỨNG DỤNG / JAVA DRIVER
                         |
                         v
                     mongos
                   /    |    \
                  /     |     \
                 v      v      v
              Shard A Shard B Shard C
              (RS)    (RS)    (RS)
                 \      |      /
                  \     |     /
                     mongos
                        |
                        v
                  KẾT QUẢ CHUNG
```

**Shard** thông thường là một replica set lưu **một phần** dữ liệu của sharded collection. **Config servers** lưu metadata cấu hình/routing; `mongos` sử dụng thông tin này để biết những **khoảng giá trị shard key** đang thuộc shard nào. Ở các phiên bản MongoDB hiện đại, dữ liệu được quản lý theo các khoảng shard key (*shard key ranges*, thường gắn với khái niệm *chunks*).

Khi ứng dụng truy vấn `orders`:

1. `mongos` nhận lệnh và kiểm tra collection có được sharding hay không.
2. Nếu collection được sharding, `mongos` phân tích **predicate** của truy vấn để xác định phạm vi shard key có thể thỏa mãn.
3. Từ metadata phân phối dữ liệu, nó xác định shard nào đang sở hữu các khoảng cần xét.
4. `mongos` gửi truy vấn đến **một, một vài hoặc tất cả shard**.
5. Các shard chạy phần truy vấn được giao và trả dữ liệu/thống kê.
6. `mongos` hoặc một bước merge thích hợp tổng hợp, sắp xếp, giới hạn và trả kết quả cho client.

Trong thực tế, placement của các khoảng dữ liệu có thể thay đổi khi cân bằng hoặc di chuyển dữ liệu. Ứng dụng không nên **tự hard-code host của shard theo tenant**. Bộ định tuyến `mongos` theo dõi metadata và xử lý các tình huống metadata cần làm mới.

### Phân biệt ba khái niệm

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| **Shard key** | Dựa vào field/giá trị nào để phân phối document? | `{tenantId: 1, orderId: 1}` |
| **Shard targeting** | Lệnh truy vấn cần gửi tới những shard nào? | Chỉ một shard, một tập con, hoặc toàn bộ |
| **Local query plan** | Trên từng shard được chọn, dùng index hay quét collection? | `IXSCAN`, `FETCH`, `COLLSCAN` |

Một truy vấn có thể được **target tới đúng shard nhưng vẫn chậm** vì shard đó quét nhiều document. Ngược lại, truy vấn có thể **scatter-gather nhưng mỗi shard dùng index tốt**. Hai chiều tối ưu này phải được đo riêng.

## 2. Targeted query và scatter-gather: hình dung trực quan

Giả sử sharded collection có dữ liệu của nhiều khách hàng thuê hệ thống (*tenant*), các khoảng shard key đang được phân phối trên ba shard.

### 2.1. Targeted query

Ứng dụng biết đầy đủ shard key của đơn cần tìm:

```javascript
db.orders.findOne({
  tenantId: "T01",
  orderId: 104
})
```

Với shard key dạng ranged `{tenantId: 1, orderId: 1}`, điều kiện equality trên **đủ các thành phần** cho `mongos` khả năng xác định khoảng chứa khóa đó, rồi gửi yêu cầu đến shard sở hữu khoảng.

```text
                  mongos
                     |
          tenantId=T01, orderId=104
                     |
          Shard-key range lookup
                     |
          +----------+----------+
          |          |          |
       Shard A     Shard B    Shard C
          |          |          |
          X          v          X
                  Tìm document
                      |
                      v
                 Trả kết quả
```

Shard B ở đây là **minh họa**, không phải một địa chỉ cố định. Giá trị thật được định tuyến tới shard nào còn phụ thuộc metadata phân phối hiện tại.

### 2.2. Scatter-gather query

Ứng dụng chỉ biết đơn có trạng thái `"paid"`, không biết shard key:

```javascript
db.orders.find({ status: "paid" })
```

Với collection được sharding theo `{tenantId: 1, orderId: 1}`, field `status` không cung cấp thông tin xác định khoảng shard key.

```text
                    mongos
          filter: status = "paid"
                       |
             +---------+---------+
             |         |         |
             v         v         v
          Shard A   Shard B   Shard C
             |         |         |
           lọc       lọc       lọc
             |         |         |
             +---------+---------+
                       |
                 merge results
                       |
                       v
                    Client
```

Mỗi shard vẫn có thể sử dụng index `{status: 1}` để lọc nhanh. Nhưng yêu cầu phải đến nhiều shard, kéo theo thêm network, xử lý phân tán và bước hợp nhất đầu ra.

### Targeted không nhất thiết là một shard

Một truy vấn có **một phần** shard key hoặc một khoảng giá trị shard key có thể chỉ cần **một số shard**. Chẳng hạn:

```javascript
db.orders.find({ tenantId: "T01" })
```

Với shard key ghép `{tenantId: 1, orderId: 1}`, các order của `T01` có thể nằm trên **nhiều khoảng** được phân cho các shard khác nhau. Query có điều kiện prefix nên `mongos` có thể thu hẹp phạm vi, nhưng **không bảo đảm chỉ một shard**.

Đây là phân biệt quan trọng giữa:

- **Targeting được một khoảng hoặc tập các khoảng** từ predicate.
- **Targeting chính xác một shard** sau khi đối chiếu các khoảng đó với placement hiện tại.

## 3. Chuẩn bị môi trường và dữ liệu thực hành

Để quan sát routing thực sự trên nhiều shard, cần một **sharded cluster** có `mongos`, config server replica set và tối thiểu hai shard thích hợp. Không thể nhìn thấy scatter-gather nhiều shard khi chỉ có standalone `mongod` hoặc replica set đơn.

Các ví dụ dưới đây tách thành **hai mức thực hành**:

1. Trên một database lab riêng, tạo document và học ý nghĩa của filter.
2. Khi có quyền quản trị trên **sharded cluster lab**, shard collection để xem `mongos` định tuyến và dùng explain.

Nếu không có sharded cluster, vẫn có thể đọc pipeline và thiết kế shard key, nhưng **không được coi số shard được liên hệ trên một replica set thường là bằng chứng routing**.

### 3.1. Tạo dữ liệu mẫu

Kết nối qua `mongos` của cụm lab hoặc vào môi trường MongoDB riêng dành cho thực hành:

```javascript
use sharding_lab

db.orders.insertMany([
  {
    _id: "T01-100", tenantId: "T01", orderId: 100,
    status: "paid", region: "north", total: 120,
    createdAt: ISODate("2026-11-10T08:00:00Z")
  },
  {
    _id: "T01-101", tenantId: "T01", orderId: 101,
    status: "pending", region: "north", total: 50,
    createdAt: ISODate("2026-11-10T09:00:00Z")
  },
  {
    _id: "T01-102", tenantId: "T01", orderId: 102,
    status: "paid", region: "south", total: 240,
    createdAt: ISODate("2026-11-11T08:00:00Z")
  },
  {
    _id: "T01-103", tenantId: "T01", orderId: 103,
    status: "cancelled", region: "north", total: 80,
    createdAt: ISODate("2026-11-11T09:00:00Z")
  },
  {
    _id: "T01-104", tenantId: "T01", orderId: 104,
    status: "paid", region: "north", total: 170,
    createdAt: ISODate("2026-11-12T08:00:00Z")
  },
  {
    _id: "T01-105", tenantId: "T01", orderId: 105,
    status: "paid", region: "south", total: 130,
    createdAt: ISODate("2026-11-12T09:00:00Z")
  },
  {
    _id: "T02-200", tenantId: "T02", orderId: 200,
    status: "paid", region: "north", total: 310,
    createdAt: ISODate("2026-11-10T10:00:00Z")
  },
  {
    _id: "T02-201", tenantId: "T02", orderId: 201,
    status: "pending", region: "south", total: 95,
    createdAt: ISODate("2026-11-10T11:00:00Z")
  },
  {
    _id: "T02-202", tenantId: "T02", orderId: 202,
    status: "paid", region: "south", total: 200,
    createdAt: ISODate("2026-11-11T10:00:00Z")
  },
  {
    _id: "T02-203", tenantId: "T02", orderId: 203,
    status: "paid", region: "north", total: 170,
    createdAt: ISODate("2026-11-12T10:00:00Z")
  },
  {
    _id: "T02-204", tenantId: "T02", orderId: 204,
    status: "pending", region: "north", total: 60,
    createdAt: ISODate("2026-11-12T11:00:00Z")
  },
  {
    _id: "T03-300", tenantId: "T03", orderId: 300,
    status: "paid", region: "south", total: 220,
    createdAt: ISODate("2026-11-10T12:00:00Z")
  },
  {
    _id: "T03-301", tenantId: "T03", orderId: 301,
    status: "paid", region: "north", total: 190,
    createdAt: ISODate("2026-11-11T11:00:00Z")
  },
  {
    _id: "T03-302", tenantId: "T03", orderId: 302,
    status: "pending", region: "south", total: 85,
    createdAt: ISODate("2026-11-11T12:00:00Z")
  },
  {
    _id: "T03-303", tenantId: "T03", orderId: 303,
    status: "paid", region: "north", total: 140,
    createdAt: ISODate("2026-11-12T12:00:00Z")
  }
])
```

Bộ dữ liệu có 15 document của ba tenant. Các tổng số giúp đối chiếu khi chạy truy vấn thông thường:

| Tenant | Tổng đơn | Đơn `paid` | Doanh thu `paid` |
| --- | ---: | ---: | ---: |
| `T01` | 6 | 4 | 660 |
| `T02` | 5 | 3 | 680 |
| `T03` | 4 | 3 | 550 |
| **Toàn bộ** | **15** | **10** | **1.890** |

Document `"T01-104"` có `tenantId: "T01"`, `orderId: 104`. Các ví dụ truy vấn khóa đầy đủ sẽ sử dụng nó.

**Lưu ý vận hành:** chỉ chèn dữ liệu vào collection lab mới/trống. Chạy lại `insertMany()` với cùng `_id` có thể gặp duplicate key. Không xóa hay shard lại collection đang phục vụ dữ liệu thật để thực hành.

### 3.2. Chỉ trên sharded cluster lab: khai báo shard key

Giả sử quyết định shard collection theo ranged compound key:

```javascript
{ tenantId: 1, orderId: 1 }
```

Trên `mongos` với quyền quản trị phù hợp, có thể chuẩn bị index rồi shard collection:

```javascript
use sharding_lab

db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { name: "idx_tenant_order" }
)

sh.shardCollection(
  "sharding_lab.orders",
  { tenantId: 1, orderId: 1 }
)
```

Nếu collection đã được shard hoặc môi trường không hỗ trợ/cấp quyền, không chạy lại lệnh chỉ để ép kết quả theo bài. Trong MongoDB, sharding một collection có dữ liệu còn phụ thuộc ràng buộc index, unique index, trạng thái collection và phiên bản server; ví dụ trên giả định collection lab đáp ứng điều kiện.

**Một điểm dễ gây hiểu nhầm:** 15 document rất ít, nên việc khai báo sharding **không bảo đảm dữ liệu được chia đều ra ba shard ngay lập tức**. Có thể chỉ có một khoảng dữ liệu nhỏ và toàn bộ vẫn nằm ở một shard. Muốn xem fan-out thực tế giữa nhiều shard, cần một môi trường lab đã phân phối các khoảng dữ liệu liên quan trên nhiều shard. Không tùy tiện dùng `moveChunk`/thao tác cân bằng thủ công trên production để “làm đẹp” sơ đồ.

Để kiểm tra metadata ở môi trường có quyền:

```javascript
sh.status()
```

Trên những phiên bản `mongosh` có helper tương ứng, có thể xem phân bố collection:

```javascript
db.orders.getShardDistribution()
```

Đây là những lệnh quan sát. Chúng giúp kiểm tra collection có shard key nào, có những shard nào và dữ liệu/ranges đang phân bố ra sao trước khi diễn giải explain.

## 4. Vì sao `mongos` phải nhìn vào shard key?

Với ranged shard key:

```javascript
{ tenantId: 1, orderId: 1 }
```

MongoDB sắp giá trị shard key theo thứ tự khóa ghép, sau đó phân phối **các khoảng** trên shard. Hình dung:

```text
Thứ tự logic của shard key:

(T01, 100) ... (T01, 999)
       (T02, 100) ... (T02, 999)
             (T03, 100) ... (T03, 999)
                         ...

Các shard-key ranges:
   R1 ------------ R2 ----------- R3 ----------
      |                |              |
      v                v              v
    Shard A          Shard C        Shard B
```

Sơ đồ không đại diện cho phân bổ vật lý thực của dữ liệu mẫu. Điều quan trọng là **các giá trị trong predicate có thể ánh xạ thành một hoặc nhiều khoảng khóa**.

### Equality trên đầy đủ shard key

```javascript
db.orders.find({
  tenantId: "T01",
  orderId: 104
})
```

Đây là một **point lookup** đối với shard key: có thể xác định khoảng chứa cặp giá trị và shard đang sở hữu khoảng đó. Trong điều kiện định tuyến thông thường, `mongos` không cần hỏi mọi shard.

### Equality trên prefix của compound shard key

```javascript
db.orders.find({ tenantId: "T01" })
```

Đây là điều kiện trên **thành phần đứng đầu** của compound key. Các cặp `(T01, orderId)` liên tiếp trong thứ tự shard key, nên `mongos` có thể dùng prefix này để xác định các khoảng liên quan. Nhưng các khoảng của T01 có thể nằm ở nhiều shard.

### Chỉ lọc thành phần phía sau

```javascript
db.orders.find({ orderId: 104 })
```

Không có `tenantId`, nên `orderId:104` có thể xuất hiện dưới nhiều tenant và nằm ở các vị trí khác nhau trong thứ tự khóa ghép. Predicate này **không tận dụng được prefix** để xác định một khoảng chung theo shard key. Thông thường bộ định tuyến phải liên hệ mọi shard liên quan tới collection.

**Quy tắc trực giác:** với compound ranged shard key, **thứ tự field quyết định khả năng target theo tiền tố**. Có field cuối mà thiếu field đầu không tương đương có đủ shard key.

## 5. Bảng so sánh các mẫu truy vấn với ranged compound shard key

Giả sử shard key của `orders` là `{tenantId: 1, orderId: 1}`:

| Bộ lọc | Thông tin shard key có sẵn | Khả năng định tuyến |
| --- | --- | --- |
| `{tenantId:"T01",orderId:104}` | Đầy đủ equality | Thường target **một shard** sở hữu cặp khóa |
| `{tenantId:"T01"}` | Equality trên prefix | Target các khoảng của T01, có thể **một hoặc nhiều shard** |
| `{tenantId:"T01",orderId:{$gte:103}}` | Prefix equality + range | Target những khoảng liên quan trong T01, có thể nhiều shard |
| `{tenantId:{$in:["T01","T03"]}}` | Một số giá trị của prefix | Có thể thu hẹp vào **hợp các khoảng** tương ứng |
| `{tenantId:{$gte:"T02",$lt:"T04"}}` | Range trên prefix | Có thể bỏ các khoảng ngoài phạm vi, tùy placement |
| `{orderId:104}` | Chỉ field thứ hai | Thường phải scatter-gather |
| `{status:"paid"}` | Không có shard-key predicate | Thường phải scatter-gather |
| `{_id:"T01-104"}` | Không có shard key trong filter | Thường phải scatter-gather dù `_id` có index |
| `{tenantId:"T01",status:"paid"}` | Prefix equality, thêm filter thường | Target các khoảng của T01; `status` lọc trên shard |
| `{}` | Không có điều kiện | Quét phạm vi collection trên các shard cần thiết |

**Không sử dụng bảng như cam kết về đúng số shard trong mọi lần chạy.** Shard placement, phiên bản optimizer, kiểu shard key, giá trị filter và tình huống migration đều ảnh hưởng kế hoạch cụ thể. `explain()` là cách xác nhận bộ định tuyến đã chọn những shard nào.

### Lưu ý về `_id`

Mỗi document trong MongoDB có `_id`, và MongoDB tạo index `_id_` theo cấu hình thông thường. Nhưng nếu **shard key không phải `_id`**, truy vấn:

```javascript
db.orders.findOne({ _id: "T01-104" })
```

không cho `mongos` biết chắc shard nào đang chứa cặp `(tenantId,orderId)`. Nó có thể phải phát query tới nhiều shard; trên **mỗi shard**, index `_id_` vẫn có thể khiến tìm kiếm rất nhanh.

Đây là ví dụ rõ nhất về việc **có index tốt không đồng nghĩa định tuyến đúng shard**. Nếu ứng dụng thường xuyên đọc đơn theo ID, cần cân nhắc thiết kế ID/shard key và việc có thể kèm tenant ID trong mọi lời gọi.

## 6. Compound shard key: chỉ có prefix chưa chắc đã đến một shard

Giả sử dữ liệu của tenant `T01` rất lớn, nên các khoảng khóa của T01 được chia:

```text
Shard key: {tenantId:1, orderId:1}

Khoảng của T01:
  (T01, MinKey)  ... (T01, 199)  -> Shard A
  (T01, 200)     ... (T01, 499) -> Shard B
  (T01, 500)     ... (T01, MaxKey) -> Shard C
```

Sơ đồ là **giả định để giải thích**, không phải dữ liệu lab thực tế.

Truy vấn:

```javascript
db.orders.find({ tenantId: "T01" })
```

có thể phải liên hệ **A, B và C**, dù predicate có prefix shard key. Trong khi:

```javascript
db.orders.find({
  tenantId: "T01",
  orderId: 235
})
```

có thể định tuyến tới **B**.

### Range trên thành phần cuối

```javascript
db.orders.find({
  tenantId: "T01",
  orderId: { $gte: 200, $lt: 300 }
})
```

có thể thu hẹp phạm vi so với toàn bộ T01; nếu range 200–299 nằm gọn trên B, chỉ B cần xử lý trong sơ đồ. Nếu range cắt qua hai shard-key ranges, `mongos` phải liên hệ cả hai shard.

Mục tiêu khi viết API là đưa vào filter **đúng thông tin shard key mà ứng dụng đã biết**, không tự “đoán thêm” `tenantId` dựa trên một ID không được bảo đảm.

### Những điều kiện làm mất khả năng target

Một ví dụ:

```javascript
db.orders.find({
  $or: [
    { tenantId: "T01" },
    { status: "pending" }
  ]
})
```

Nhánh thứ hai `status:"pending"` có thể khớp document ở **bất kỳ shard nào**, nên toàn bộ `$or` không thể chỉ target các khoảng của T01. Có thể phải scatter-gather.

Trái lại:

```javascript
db.orders.find({
  $or: [
    { tenantId: "T01", orderId: 104 },
    { tenantId: "T02", orderId: 202 }
  ]
})
```

có hai nhánh đều ràng buộc **đầy đủ shard key**. Mongos có thể dùng hợp các target của hai điểm khóa, thay vì bắt buộc hỏi mọi shard. Hai điểm có thể nằm trên cùng shard hoặc hai shard khác nhau.

**Đừng coi mỗi `$or`, `$in` hoặc điều kiện range đều tự động scatter.** Khả năng định tuyến phụ thuộc liệu toàn bộ predicate có thể được suy ra thành một tập shard-key ranges hẹp hay không.

## 7. Hashed shard key: equality và range hành xử khác nhau

Một collection khác có thể được shard theo khóa hash:

```javascript
{ tenantId: "hashed" }
```

Với hashed sharding, MongoDB tính giá trị hash của shard key để quyết định khoảng dữ liệu. Giá trị `tenantId` gần nhau theo thứ tự chữ **không nhất thiết** nằm gần nhau về mặt shard-key range.

```text
tenantId gốc:     T01    T02    T03    T04
                      |     |      |      |
                      v     v      v      v
giá trị hash:      h(T01) h(T02) h(T03) h(T04)
                   phân tán theo không gian hash
```

### Equality trên hashed key

```javascript
db.orders.find({ tenantId: "T01" })
```

Khi shard key chính là `{tenantId:"hashed"}`, điều kiện equality trên tenantId giúp `mongos` tính hash và xác định shard-key range tương ứng. Trong điều kiện bình thường, đây là targeted query tới shard sở hữu giá trị hash đó.

Với hashed shard key **ghép**, cần xem thứ tự và các thành phần của khóa; không suy rằng equality trên một field bất kỳ là đủ để target chính xác một shard.

### Range trên giá trị gốc của hashed key

```javascript
db.orders.find({
  tenantId: { $gte: "T01", $lt: "T50" }
})
```

Các giá trị tenant trong khoảng chữ `T01`–`T49` có thể có hash phân bố khắp không gian khóa. Vì vậy, **range trên giá trị gốc của một hashed shard key không cho một khoảng hash liên tục thuận tiện**, và thường gây scatter-gather.

Đây là sự đánh đổi:

| Đặc tính | Ranged shard key | Hashed shard key |
| --- | --- | --- |
| Equality trên đầy đủ key | Thường target một shard | Thường target một shard |
| Range trên key | Có khả năng target các khoảng liên quan | Range trên giá trị gốc thường không định tuyến hẹp |
| Thứ tự vật lý theo giá trị key | Giữ quan hệ thứ tự khóa | Phá tính liền kề của giá trị gốc |
| Phân phối các giá trị tăng dần | Có thể tạo hotspot nếu thiết kế không phù hợp | Có thể phân tán tốt hơn với pattern phù hợp |
| Báo cáo theo khoảng shard key | Thường thuận lợi hơn | Có thể cần truy vấn nhiều shard |

Hashed sharding không phải cách “làm mọi query targeted”. Nó phù hợp khi workload chủ yếu có **equality lookups** và mong muốn phân phối dữ liệu/ghi, nhưng cần đánh đổi đối với **range scans**.

## 8. Query có index ở mọi shard vẫn có thể scatter-gather

Giả sử shard key là:

```javascript
{ tenantId: 1, orderId: 1 }
```

và tạo index phục vụ truy vấn theo trạng thái:

```javascript
db.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_status_created" }
)
```

Chạy:

```javascript
db.orders.find({ status: "paid" })
  .sort({ createdAt: -1 })
  .limit(10)
```

Query **thiếu shard-key condition**, nên `mongos` có thể phải hỏi mọi shard có dữ liệu liên quan. Trên mỗi shard, MongoDB có thể dùng `idx_status_created` để lọc/sort rất hiệu quả.

```text
             mongos (scatter)
              /     |     \
             v      v      v
         Shard A Shard B Shard C
          IXSCAN  IXSCAN  IXSCAN
             \      |      /
              \     |     /
          merge / global sort / limit
                    |
                 10 kết quả
```

Tùy pipeline và index, các shard có thể gửi kết quả đã sort một phần để bước merge lựa chọn top 10 toàn cục, thay vì mongos nhận mọi document rồi mới sort. Nhưng vẫn có chi phí nhiều shard, fan-out, network và hợp nhất.

**Hai mục tiêu tối ưu cần tách:**

1. **Giảm số shard bị liên hệ** bằng shard-key predicate phù hợp.
2. **Giảm việc trên mỗi shard** bằng index, predicate, projection và sort phù hợp.

Chỉ giải quyết mục (2) sẽ không tự loại bỏ scatter-gather nếu `mongos` vẫn không biết shard nào có thể chứa kết quả.

## 9. Thực hành `explain()` để xác nhận targeted hay scatter

Không nên kết luận một truy vấn là targeted chỉ từ việc “bộ lọc có vẻ chứa tenantId”. Hãy chạy explain qua **`mongos`** và xem số shard/thành phần tham gia thực thi.

### 9.1. Truy vấn point lookup đủ shard key

```javascript
db.orders.find({
  tenantId: "T01",
  orderId: 104
})
  .explain("queryPlanner")
```

Hoặc lấy thêm thống kê:

```javascript
db.orders.find({
  tenantId: "T01",
  orderId: 104
})
  .explain("executionStats")
```

Ở sharded cluster, explain có thể chứa **thông tin theo shard** và những stage thể hiện quá trình định tuyến/merge. Nếu có đúng một shard tham gia, truy vấn đạt tính chất single-shard ở lần explain đó.

### 9.2. Truy vấn scatter theo status

```javascript
db.orders.find({ status: "paid" })
  .explain("executionStats")
```

Đối chiếu số shard được báo với explain của point lookup. Nếu collection có các khoảng dữ liệu trên ba shard và status không ràng buộc shard key, plan có thể cho thấy yêu cầu được gửi tới nhiều shard.

### 9.3. Truy vấn prefix

```javascript
db.orders.find({ tenantId: "T01" })
  .explain("executionStats")
```

Xem đây là trường hợp **một hoặc nhiều targeted shards**. Nếu tất cả khoảng của T01 đang ở một shard, số shard tham gia có thể bằng 1; nếu T01 đã được phân tán, có thể nhiều hơn. Không lấy kết quả một lần trong lab để khẳng định rằng prefix luôn chỉ liên hệ đúng một shard.

### 9.4. Cấu trúc explain không cố định giữa các phiên bản

Kết quả `explain` của sharded query có thể chứa những cấu trúc như:

```text
explain (hình dung)
├── queryPlanner
│   └── winningPlan
│       ├── các stage định tuyến / merge
│       └── các nhánh hoặc phần thông tin theo shard
├── executionStats
│   ├── executionStages
│   ├── totalKeysExamined / totalDocsExamined khi có
│   └── các thống kê từng shard
├── shards (ở một số loại explain)
└── metadata khác
```

Bạn có thể bắt gặp tên stage như `SHARD_MERGE`, `SHARD_MERGE_SORT`, `SINGLE_SHARD`, `SHARDING_FILTER`, `IXSCAN`, `FETCH` hoặc `COLLSCAN`, tùy MongoDB version, query engine và dạng truy vấn. **Không có một đường dẫn JSON cố định** áp dụng cho mọi phiên bản và mọi `find`/`aggregate`.

Một số phiên bản còn có biểu diễn của **slot-based execution engine (SBE)** như `queryPlan`/`slotBasedPlan`, khiến cây stage khác ví dụ trong tài liệu cũ. Khi đọc, nên trả lời những câu hỏi:

1. Có **bao nhiêu shard thực sự nhận yêu cầu**?
2. Mỗi shard dùng index nào, có `COLLSCAN` hoặc `SORT` không?
3. Có bước merge/sort/limit ở phía router hay merge shard không?
4. `nReturned`, `totalKeysExamined`, `totalDocsExamined` ở **phạm vi nào**: từng shard hay toàn query?
5. Có dấu hiệu router phải hỏi mọi shard dù kết quả cuối chỉ có một document không?

### Chỉ số examined không đủ để nhận biết targeting

Giả sử hai kế hoạch giả định:

```text
A: 1 shard,  totalDocsExamined = 15000, nReturned = 1
B: 3 shards, mỗi shard totalDocsExamined = 1, nReturned tổng = 1
```

A được target đúng một shard nhưng có thể thiếu index lọc cục bộ, nên đọc 15.000 document. B là scatter-gather nhưng các shard có index tốt và đọc rất ít. Không thể kết luận **routing hiệu quả** chỉ từ một số `docsExamined` hay **độ trễ toàn cục** chỉ từ số shard. Phải quan sát cả hai.

## 10. Đọc `explain` cho aggregation trên sharded collection

Aggregation pipeline có thể chia công việc giữa các shard và một bước merge:

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "paid" } },
  {
    $group: {
      _id: "$tenantId",
      paidOrders: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  },
  { $sort: { revenue: -1 } }
])
```

Với dữ liệu mẫu, các nhóm là:

```javascript
{ _id: "T02", paidOrders: 3, revenue: 680 }
{ _id: "T01", paidOrders: 4, revenue: 660 }
{ _id: "T03", paidOrders: 3, revenue: 550 }
```

Nhưng filter `status:"paid"` **không ràng buộc shard key**, nên phần đọc ban đầu thường cần nhiều shard. MongoDB có thể thực hiện một số thao tác tổng hợp cục bộ trên các shard và hợp nhất kết quả ở bước merge, tùy optimizer và pipeline.

```text
                mongos / router
                      |
                scatter $match
            +---------+---------+
            |         |         |
          Shard A   Shard B    Shard C
          $match    $match     $match
          partial   partial    partial
          $group    $group     $group
            |         |         |
            +---------+---------+
                      |
                 merge $group
                      |
                   $sort
                      |
                3 tenant totals
```

Sơ đồ là **một chiến lược khả dĩ**, không cam kết server luôn tách group thành đúng hai giai đoạn. Explain của aggregation có thể có `splitPipeline`, `shardsPart`, `mergerPart` hoặc các cấu trúc stage khác theo phiên bản. Điều cần xác định là **bước nào chạy trên shard và bước nào hợp nhất kết quả**.

### Aggregation chỉ cho một tenant

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "T01", status: "paid" } },
  {
    $group: {
      _id: "$tenantId",
      paidOrders: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  }
])
```

Kết quả logic là **một nhóm T01 có 4 đơn và doanh thu 660**. Nhưng vì shard key ghép còn `orderId`, `tenantId:"T01"` chỉ ràng buộc prefix, nên có thể cần **một hoặc nhiều shard** nếu T01 trải trên nhiều ranges.

### Đặt `$match` vào vị trí giúp routing

Thông thường nên để điều kiện có shard key **sớm trong pipeline**:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "T01" } },
  { $match: { status: "paid" } },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } }
])
```

MongoDB có aggregation optimizer có thể gộp hoặc đẩy một số `$match` lên trước các stage tương đương, nên không thể khẳng định đổi thứ tự văn bản luôn cải thiện tốc độ. Nhưng **lọc đúng shard key trước các phép biến đổi phụ thuộc dữ liệu** giúp diễn đạt ý định rõ ràng và thường tạo điều kiện cho routing/scan tối ưu.

Ngược lại, nếu trước `$match` có stage **loại bỏ hoặc đổi tên shard key**, bạn có thể mất khả năng áp dụng predicate gốc hoặc làm thay đổi ý nghĩa:

```javascript
// Cẩn thận: project trước đã loại tenantId
db.orders.aggregate([
  { $project: { status: 1, total: 1 } },
  { $match: { tenantId: "T01" } }
])
```

Pipeline này không giống việc lọc tenant trước rồi project. Không đưa `$match` qua stage làm thay đổi ý nghĩa hoặc sự tồn tại của field một cách máy móc.

## 11. `$sort`, `$skip`, `$limit`: chi phí hợp nhất giữa các shard

Giả sử ứng dụng cần mười đơn `paid` mới nhất trong toàn hệ thống:

```javascript
db.orders.find({ status: "paid" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(10)
```

Query không ràng buộc shard key, nên có thể scatter tới các shard. Để trả **top 10 toàn cục**, router/merger không thể chỉ lấy top 10 từ một shard tùy ý rồi bỏ qua các shard khác.

Một kế hoạch hiệu quả có thể yêu cầu **mỗi shard trả các ứng viên theo thứ tự**, sau đó bước merge chọn top 10:

```text
Shard A:  12:00, 11:00, 08:00, ...
Shard B:  11:30, 10:30, 09:00, ...
Shard C:  11:45, 11:15, 07:00, ...
                    |
                    v
            Global merge sort
                    |
                    v
            10 dòng mới nhất
```

### `limit` không bảo đảm chỉ đọc 10 document

Nếu shard không có index phù hợp với filter/sort, nó có thể phải xem rất nhiều document rồi mới xác định các ứng viên mới nhất. Vì thế cần kiểm tra index phục vụ **local sort** trên mỗi shard, ví dụ:

```javascript
db.orders.createIndex(
  { status: 1, createdAt: -1, _id: -1 },
  { name: "idx_status_created_id" }
)
```

Index này có thể hỗ trợ lọc/sort cục bộ, nhưng **không giúp `mongos` biết chỉ một shard có đơn paid**. Nó xử lý một phần khác của bài toán hiệu năng.

### `skip` lớn vẫn tốn chi phí

```javascript
db.orders.find({ status: "paid" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(100000)
  .limit(20)
```

Đây là truy vấn cần tìm các bản ghi đứng sau một offset lớn **trên thứ tự toàn cục**. Dù có tối ưu sort/skip/limit, hệ thống vẫn phải xử lý đủ ứng viên để bỏ qua 100.000 kết quả đầu. Trên sharded cluster, chi phí fan-out và merge có thể tăng.

Khi ứng dụng chỉ cần “xem trang tiếp theo”, hãy cân nhắc **keyset pagination** theo `createdAt` và khóa tie-break ổn định, đồng thời đưa shard key vào filter nếu trang dữ liệu được giới hạn theo tenant.

Ví dụ cho danh sách **của một tenant**:

```javascript
db.orders.find({
  tenantId: "T01",
  $or: [
    { createdAt: { $lt: ISODate("2026-11-12T09:00:00Z") } },
    {
      createdAt: ISODate("2026-11-12T09:00:00Z"),
      _id: { $lt: "T01-105" }
    }
  ]
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
```

Trong ví dụ, `tenantId:"T01"` ở cấp chung ràng buộc cả hai nhánh `$or`. Nó giúp **không mở rộng truy vấn sang tenant khác**, nhưng vì shard key còn `orderId`, vẫn có thể liên hệ nhiều shard chứa dữ liệu của T01.

## 12. Thiết kế API để truyền shard key từ đầu đến cuối

Một cách thường dùng để cải thiện khả năng target là đặt **tenant context** trong đường đi của API:

```text
GET /tenants/T01/orders/104
           |         |
           v         v
        tenantId   orderId
           \         /
            \       /
    find({tenantId:"T01",orderId:104})
```

So với API:

```text
GET /orders/T01-104
         |
         v
  find({_id:"T01-104"})
```

API thứ hai chỉ đưa giá trị `_id` vào filter. Dù `_id` chứa chuỗi trông giống tenant ID, `mongos` không tự tách `"T01-104"` để suy ra `tenantId` và `orderId` nếu truy vấn không biểu diễn các field đó.

### Nên lấy tenant context từ đâu?

Trong hệ thống nhiều khách hàng, tenantId cần đến từ **ngữ cảnh xác thực/ủy quyền đáng tin cậy**, hoặc được kiểm tra quyền khi client cung cấp. Không nên tin một tenantId tùy ý từ request rồi coi đó là bằng chứng người dùng được phép đọc dữ liệu tenant đó.

Một truy vấn targeted và nhanh nhưng **thiếu kiểm tra quyền** vẫn là lỗi an toàn dữ liệu nghiêm trọng. Thiết kế tốt kết hợp:

1. Xác minh tenant được phép truy cập.
2. Truyền `tenantId` đúng kiểu BSON vào filter.
3. Thêm orderId hay các thành phần khác của shard key khi có.
4. Chạy explain/metrics trên workload thật để kiểm tra số shard bị liên hệ.

### Không tự giả định ID là shard key

Một ID như `"T01-104"` có thể là convention nghiệp vụ, nhưng MongoDB chỉ dùng **shard key thực sự được khai báo** cho routing. Nếu sharded collection có key `{tenantId:1,orderId:1}`, bộ lọc chỉ có `_id` vẫn thiếu thông tin key. Nếu thiết kế key khác, kết luận routing có thể khác. Hãy xem metadata thay vì suy đoán từ hình dạng ID.

## 13. `$in`, `$or`, biểu thức và kiểu dữ liệu: vì sao cùng field nhưng routing khác

Những predicate sau không tương đương về khả năng định tuyến:

```javascript
// A. Equality trên full shard key
{ tenantId: "T01", orderId: 104 }

// B. Equality trên prefix của compound shard key
{ tenantId: "T01" }

// C. Danh sách giá trị prefix
{ tenantId: { $in: ["T01", "T03"] } }

// D. Chỉ có một field không phải prefix
{ orderId: 104 }

// E. Điều kiện tính toán dùng biểu thức
{ $expr: { $eq: ["$tenantId", "T01"] } }
```

MongoDB có thể tối ưu một số dạng biểu thức, nhưng **không nên mặc nhiên cho rằng mọi cách viết tương đương về logic đều có cùng khả năng shard targeting**. Đối với API đơn giản, predicate equality trực tiếp trên shard key thường rõ ràng và dễ quan sát hơn một biểu thức phức tạp phải tính khi thực thi.

### Kiểu BSON của shard-key predicate phải đúng

Nếu collection lưu:

```javascript
{ tenantId: "T01", orderId: 104 }
```

thì:

```javascript
db.orders.find({
  tenantId: "T01",
  orderId: "104"
})
```

không tương đương với equality trên **số** `104`. Shard key chứa giá trị có kiểu BSON; string và number khác nhau cả về ngữ nghĩa equality lẫn vị trí trong không gian khóa.

MongoDB có thể vẫn **target được một shard dựa trên giá trị sai kiểu** — nhưng rồi không tìm thấy document mong muốn. Vì thế, “query single-shard” không có nghĩa bộ lọc ứng dụng đã đúng dữ liệu.

### Collation và biểu diễn string

Nếu shard key chứa string, các quy tắc về collation, chuẩn hóa chữ hoa/thường và kiểu giá trị có thể ảnh hưởng cách so sánh và khả năng suy ra bounds cho routing. Một truy vấn dùng collation khác với cách shard key được phân phối có thể không tận dụng targeting như một equality thông thường.

Đừng tự kết luận rằng `"t01"` và `"T01"` là cùng tenant nếu schema không định nghĩa như vậy. Nên chuẩn hóa ID nhất quán khi ghi và khi đọc, đồng thời xem `explain` nếu query dùng collation không mặc định.

## 14. Một điểm quan trọng: shard targeting và query selectivity khác nhau

**Targeting** trả lời “cần liên hệ shard nào?”. **Selectivity** trả lời “trên shard đó có bao nhiêu dữ liệu khớp và phải xem bao nhiêu mục?”.

Giả sử hai truy vấn:

```javascript
// A. Targeted theo full shard key
db.orders.find({
  tenantId: "T01",
  orderId: 104
})

// B. Không theo shard key nhưng lọc status chọn lọc
db.orders.find({
  status: "cancelled"
})
```

A có thể chỉ liên hệ một shard và dùng index phù hợp để tìm nhanh. B có thể liên hệ tất cả shard, nhưng nếu `status:"cancelled"` rất hiếm và có index phù hợp trên mỗi shard, tổng số document đọc có thể nhỏ.

### Đặt index cho cả shard key và query shape

Shard key/routing index:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { name: "idx_tenant_order" }
)
```

Index phục vụ danh sách đơn paid theo thời gian trong tenant:

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "idx_tenant_status_created" }
)
```

Hai index có công dụng khác nhau. Index thứ hai có thể giúp truy vấn:

```javascript
db.orders.find({
  tenantId: "T01",
  status: "paid"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(10)
```

lọc/sort cục bộ hiệu quả. Tuy nhiên chỉ có `tenantId` trong filter của compound shard key `{tenantId:1,orderId:1}`, nên số shard liên hệ vẫn phụ thuộc phạm vi và phân bố của tenant T01.

**Không bắt buộc mỗi index phục vụ query phải chứa mọi thành phần shard key** trong mọi trường hợp. Việc chọn index phải xét workload, selectivity, sort, độ phủ và chi phí ghi/index storage.

## 15. Những truy vấn không tránh khỏi fan-out

Không phải mọi ứng dụng đều có thể hoặc nên bổ sung shard key vào tất cả query. Những báo cáo toàn hệ thống thường cần tổng hợp **đa tenant**.

Ví dụ báo cáo doanh thu theo vùng:

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$total" }
    }
  },
  { $sort: { revenue: -1 } }
])
```

Nếu `region` và `status` không nằm trong shard key, truy vấn có thể cần dữ liệu từ tất cả shard. Điều đó **không tự là thiết kế sai**: câu hỏi nghiệp vụ cần tổng trên toàn hệ thống, nên nhiều shard phải đóng góp.

Các hướng giảm chi phí có thể gồm:

- Index phù hợp cho filter và các stage có khả năng sử dụng index **trên từng shard**.
- Chọn khoảng thời gian cần báo cáo thay vì quét toàn bộ lịch sử.
- Thiết kế aggregate theo từng shard rồi hợp nhất có hiệu quả khi optimizer hỗ trợ.
- Tạo bảng báo cáo đã tổng hợp (*materialized summary*) được duy trì theo cơ chế phù hợp nếu báo cáo rất thường xuyên.
- Tách workload phân tích khối lượng lớn sang hạ tầng/phương pháp thích hợp, thay vì ép OLTP lookup tối ưu như báo cáo đa chiều.

**Không thêm shard key giả** vào filter chỉ để `explain` bớt shard nếu nó làm bỏ sót dữ liệu. Targeting chỉ có ích khi vẫn **trả đúng kết quả nghiệp vụ**.

## 16. Chọn shard key dựa trên mẫu truy vấn

Việc chọn shard key là quyết định dài hạn, ảnh hưởng phân bố dữ liệu, cân bằng tải, hotspot và khả năng target. Hãy xuất phát từ **những query chạy nhiều nhất**.

Giả sử hệ thống có ba mẫu truy vấn:

| Mẫu | Tần suất | Điều kiện chính | Mục tiêu |
| --- | --- | --- | --- |
| Tra một đơn | Rất cao | `tenantId + orderId` | Point lookup targeted |
| Liệt kê đơn một tenant | Cao | `tenantId + status`, sort theo thời gian | Hạn chế shard fan-out và index/local sort |
| Báo cáo mọi tenant | Thấp hơn | `status + createdAt` | Tối ưu scan/tổng hợp, chấp nhận nhiều shard |

Khi đó `{tenantId:1,orderId:1}` là một **ứng viên hợp lý** cho point lookup, nhưng sẽ cần kiểm tra liệu một tenant lớn có trải qua nhiều shards hay không. Nếu workload chủ yếu đọc theo `tenantId`, có thể cân nhắc các dạng key khác hoặc chiến lược phân bố phù hợp, dựa trên cardinality, độ lệch tenant và khả năng tăng trưởng.

### Tránh khóa đơn điệu gây hotspot ghi

Nếu shard key chỉ là một giá trị luôn tăng (ví dụ timestamp/sequence tăng dần trong ranged sharding), các ghi mới có thể tập trung vào phần cuối của không gian khóa và một shard trong một giai đoạn. Đây là **write hotspot** chứ không chỉ là vấn đề query targeting.

Hashed key có thể phân phối các giá trị tăng tốt hơn trong một số workload, nhưng range queries trên key gốc khó target hơn. Không có shard key tối ưu cho mọi truy vấn; cần cân bằng read/write distribution và query patterns.

### Cardinality và tenant quá lớn

Nếu chỉ shard theo `tenantId` và một tenant cực lớn chiếm phần lớn dữ liệu, tenant đó có thể tạo mất cân bằng/hotspot. Một compound shard key có thể chia dữ liệu một tenant thành nhiều shard-key ranges, nhưng đổi lại một truy vấn chỉ có tenantId có thể phải tới nhiều shard.

Điểm này giải thích vì sao mục tiêu “mọi truy vấn theo tenant chỉ đến một shard” **không phải lúc nào cũng phù hợp** với mục tiêu phân tán dữ liệu của tenant lớn. Phải đo lượng dữ liệu và traffic thực của từng tenant.

### Tính ổn định của shard key

Shard key nên có ý nghĩa ổn định, được đưa vào phần lớn những query quan trọng và có giá trị phân phối tốt. Nếu nghiệp vụ thường xuyên thay shard-key value, việc cập nhật/di chuyển dữ liệu có thể phức tạp hơn những field thông thường.

Trước khi chọn, hãy lập danh sách các route API, thống kê tỷ lệ query có đủ shard key, tỷ lệ query cross-tenant và phân bố ghi/đọc, thay vì chỉ chọn field có cardinality cao nhất trên giấy.

## 17. Phân biệt read preference với shard routing

Một sharded cluster có thể gồm các shard là replica set:

```text
                     mongos
                       |
       +---------------+----------------+
       |                                |
    Shard A                          Shard B
   +--------+                       +--------+
   | P  S S |                       | P  S S |
   +--------+                       +--------+
```

Có **hai bước định tuyến khác nhau**:

1. `mongos` quyết định **shard nào cần xử lý** dựa trên shard key/predicate.
2. Trong mỗi shard replica set, **read preference** ảnh hưởng member nào được dùng để thực hiện phần đọc theo chính sách.

```javascript
// Chỉ minh họa một policy đọc ngoài transaction
db.orders.find({ tenantId: "T01", orderId: 104 })
  .readPref("secondaryPreferred")
```

Read preference `secondaryPreferred` không làm `mongos` bỏ qua điều kiện shard key và không biến scatter-gather thành targeted. Nó ảnh hưởng lựa chọn **replica member trong mỗi shard được liên hệ**, không thay đổi dữ liệu phân phối theo shard key.

Đọc từ secondary có thể nhìn dữ liệu chậm hơn primary theo replication lag và read concern. Đối với giao dịch có thao tác đọc, còn có quy tắc riêng về read preference `primary`. Không lấy `readPreference` làm công cụ chữa một truy vấn đang fan-out trên quá nhiều shards.

## 18. Ví dụ Java MongoDB Sync Driver

Trong Java, truy vấn nên luôn truyền những giá trị shard key mà nghiệp vụ đã biết. MongoDB Java Sync Driver gửi lệnh qua topology được cấu hình; nếu kết nối tới `mongos`, chính router của cluster quyết định shard cần liên hệ.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

public class ShardTargetingExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("sharding_lab");
            MongoCollection<Document> orders =
                db.getCollection("orders");

            // A. Đủ hai field của ranged compound shard key
            Bson targeted = Filters.and(
                Filters.eq("tenantId", "T01"),
                Filters.eq("orderId", 104)
            );
            Document order = orders.find(targeted).first();
            System.out.println("Targeted lookup: " + order);

            // B. Thiếu shard key: thường cần nhiều shard
            Bson scatter = Filters.eq("status", "paid");
            for (Document d : orders.find(scatter).limit(5)) {
                System.out.println("Paid order: " + d.get("_id"));
            }
        }
    }
}
```

Ví dụ yêu cầu dependency `mongodb-driver-sync` phù hợp và biến môi trường `MONGODB_URI` trỏ tới **sharded cluster lab** nếu muốn khảo sát routing. Khi chạy trên replica set thường, hai lệnh vẫn đọc dữ liệu nhưng không thể hiện khác biệt target/scatter giữa shards.

**Một lưu ý quan trọng:** `first()` trên query thiếu shard key không tự khiến router biết shard chính xác. Giới hạn kết quả trả về 1 hoặc 5 không phải là bằng chứng truy vấn chỉ cần một shard.

### 18.1. Gọi `explain` từ Java

Để xem plan trực tiếp từ Java, có thể gửi database command `explain`:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class ExplainShardQuery {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("sharding_lab");

            Document findCommand = new Document("find", "orders")
                .append("filter",
                    new Document("tenantId", "T01")
                        .append("orderId", 104));

            Document explainCommand =
                new Document("explain", findCommand)
                    .append("verbosity", "executionStats");

            Document explainResult = db.runCommand(explainCommand);
            System.out.println(explainResult.toJson());
        }
    }
}
```

Để nghiên cứu scatter-gather, thay `filter` bằng:

```java
new Document("status", "paid")
```

Rồi so sánh **số shard tham gia, index được chọn và stage merge**. Cấu trúc BSON trả về tùy phiên bản, vì vậy mã giám sát production không nên parse một đường dẫn cố định như `queryPlanner.winningPlan.shards[0]` khi chưa kiểm tra schema explain.

### 18.2. Vì sao Java Driver không nên tự chọn shard?

Không hard-code kiểu:

```java
// Ý tưởng không phù hợp với sharded collection thông thường:
// "T01 luôn thuộc mongo-shard-b:27017"
```

MongoDB có thể di chuyển dữ liệu khi balancing; ứng dụng kết nối trực tiếp vào một shard riêng có nguy cơ đọc thiếu, ghi sai đường routing hoặc không tôn trọng metadata. Khi ứng dụng làm việc với sharded cluster, dùng URI/endpoint được thiết kế cho `mongos` hoặc entry point quản lý tương ứng. Router xử lý metadata và điều phối query đến các shard.

## 19. Khảo sát hiệu năng trước khi thay đổi shard key hay API

Khi một truy vấn MongoDB chậm trong sharded cluster, đừng mặc định nguyên nhân là thiếu index. Hãy phân tích theo thứ tự:

1. **Xác định query shape thật**: filter, type BSON, sort, skip, limit, projection, aggregate pipeline, collation, read preference.
2. **Đọc shard key thực tế**: không đoán từ tên ID; kiểm tra collection metadata và vị trí shard-key ranges.
3. **Xác định phạm vi routing qua `explain`**: một shard, một tập con hay tất cả.
4. **Xem local plan trên từng shard**: `IXSCAN`, `COLLSCAN`, `FETCH`, `SORT`, bounds và số examined.
5. **Xem bước merge**: `SHARD_MERGE`, merge sort, group, skip/limit và khối lượng dữ liệu trung gian theo output thực tế.
6. **Đối chiếu phân bố dữ liệu**: có tenant quá lớn, hotspot write, chunk/range imbalance hay shard đang chịu tải bất thường không?
7. **Thử phương án đúng ngữ nghĩa**: thêm shard key predicate nếu ứng dụng thực sự biết và được phép dùng; thêm index cục bộ; tối ưu pipeline hoặc phân trang; cân nhắc summary cho cross-shard report.
8. **So sánh trên dữ liệu đại diện**: đo nhiều lần, có ghi nhận cache, replication lag, concurrency và mạng. Một lần explain trên 15 document không đủ để dự báo latency production.

### Bảng quan sát

| Dấu hiệu | Khả năng nguyên nhân | Hướng điều tra |
| --- | --- | --- |
| `find({_id:...})` liên hệ mọi shard | `_id` không nằm trong shard key | Có thể bổ sung shard key đáng tin cậy vào API/filter? |
| Query có `tenantId` nhưng liên hệ nhiều shard | Compound key có thêm field; tenant spans ranges | Có đủ full key cho point lookup không? |
| Query targeted nhưng rất chậm | Shard chứa nhiều dữ liệu, local index không phù hợp | Đọc local explain, keys/docs examined, sort |
| Scatter-gather nhưng mỗi shard đọc rất ít | Local index tốt, thiếu shard-key predicate | Xem nhu cầu toàn cluster, fan-out và merge |
| Sort global chậm dù có `limit` | Thiếu index local hoặc merge nhiều shard | Xem index filter/sort và kế hoạch top-K |
| Range trên hashed shard key fan-out | Hash phá tính liền kề của raw range | Xem lại access pattern, giữ key thay thế cho range report |
| Query `$or` fan-out bất ngờ | Một nhánh không giới hạn shard key | Xem điều kiện của từng nhánh |
| Aggregation `$match` không target như mong đợi | Filter phụ thuộc field được tính/đổi tên hoặc không sargable | Đọc pipeline tối ưu và explain |
| Một shard quá tải | Phân bố key lệch hoặc hotspot | Xem cardinality, split/placement và workload |
| Tốc độ thay đổi sau balancing | Placement/ranges và cache thay đổi | Xem metadata và thời điểm đo |

## 20. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “Có shard key trong filter thì luôn chỉ hỏi một shard” | Prefix/range của compound key có thể trải trên nhiều shards | Full-key equality thường single-shard; prefix chỉ có thể thu hẹp phạm vi |
| “Chỉ `orderId` đủ vì compound key có `orderId`” | Thiếu thành phần đầu `tenantId` | Với ranged compound key, prefix quan trọng |
| “Có `_id` là MongoDB biết shard ngay” | `_id` không nhất thiết là shard key | `_id` index và shard routing là hai cơ chế riêng |
| “`IXSCAN` nghĩa là query targeted” | Mỗi shard trong scatter cũng có thể dùng index | Đọc số shard tham gia |
| “Scatter-gather luôn là lỗi” | Báo cáo toàn hệ thống có thể cần dữ liệu từ mọi shard | Tối ưu phần việc cục bộ/merge, hoặc thiết kế summary |
| “Hashed shard key giúp mọi range query đến đúng shard” | Hash không bảo toàn thứ tự raw value | Equality tốt hơn range trên hashed key |
| “`limit(1)` sẽ chỉ hỏi một shard” | Router chưa biết shard nào chứa kết quả | Limit không thay thế shard-key predicate |
| “Thêm index trên status sẽ làm `status` target một shard” | Index cục bộ không đổi shard key | Cần shard-key constraint để thu hẹp router |
| “`tenantId` đúng chữ nhưng sai BSON type vẫn tìm được” | BSON string và number có ngữ nghĩa khác | Chuẩn hóa kiểu shard key |
| “Read preference secondary khiến query không scatter” | Read preference chọn member trong shard | Routing theo shard key vẫn giữ nguyên |
| “Sau sharding, 15 document tự chia đều lên ba shard” | Dữ liệu ít có thể nằm ở một range/shard | Xem phân bố thật; không bịa fan-out |
| “Đổi `$match` lên trước mọi stage luôn đúng” | Có stage tính/đổi tên/lọc mảng làm ngữ nghĩa khác | Chỉ hoán đổi khi bảo toàn kết quả |
| “Top 10 global chỉ cần top 10 từ một shard” | Các shard khác có thể chứa bản ghi mới hơn | Cần merge có hiểu thứ tự toàn cục |
| “Tự ghi nhớ tenant nằm ở shard B sẽ nhanh hơn mongos” | Chunk/range có thể migrate | Dùng router và metadata chính thức |
| “Một lần explain là đủ để kết luận hiệu năng” | Dữ liệu, cache, balancing, mạng thay đổi | Đo trên workload đại diện và xem cả shard/local plan |

## 21. Bài tập thực hành có đáp án

### Bài 1. Full-key lookup

Collection có ranged shard key:

```javascript
{ tenantId: 1, orderId: 1 }
```

Truy vấn nào có khả năng point lookup tới đúng một shard hơn?

```javascript
// A
db.orders.find({ orderId: 104 })

// B
db.orders.find({ tenantId: "T01", orderId: 104 })
```

**Đáp án:** B. Nó có equality trên **toàn bộ shard key**. A thiếu prefix `tenantId`, thường khiến router phải liên hệ mọi shard liên quan.

### Bài 2. Có tenantId nhưng vẫn nhiều shard

Một tenant T01 có hàng triệu đơn trải trên ba shard-key ranges ở hai shard khác nhau. Truy vấn:

```javascript
db.orders.find({ tenantId: "T01" })
```

có chắc chỉ liên hệ một shard không?

**Đáp án:** Không. Với compound key `{tenantId:1,orderId:1}`, tenantId là prefix, nên router có thể thu hẹp theo tenant, nhưng các khoảng của T01 có thể thuộc **nhiều shard**. Muốn point lookup khi biết orderId, dùng đủ hai trường.

### Bài 3. Index không thay routing

Collection shard theo `{tenantId:1,orderId:1}`, có index `{status:1}` trên collection. Truy vấn:

```javascript
db.orders.find({ status: "paid" })
```

có chắc tránh được scatter-gather không?

**Đáp án:** Không. Index có thể giúp lọc nhanh **trên từng shard**, nhưng `status` không đủ để `mongos` biết shard-key ranges nào có kết quả. Query vẫn có thể fan-out.

### Bài 4. Hashed equality và range

Collection shard theo:

```javascript
{ tenantId: "hashed" }
```

So sánh:

```javascript
// A
db.orders.find({ tenantId: "T01" })

// B
db.orders.find({ tenantId: { $gte: "T01", $lt: "T50" } })
```

**Đáp án:** A có equality trên hashed key, giúp router tính hash và target shard chứa giá trị. B là raw-value range, không tương ứng một khoảng hash liên tục nên thường cần scatter-gather.

### Bài 5. `$or` có một nhánh không giới hạn shard key

```javascript
db.orders.find({
  $or: [
    { tenantId: "T01", orderId: 104 },
    { status: "pending" }
  ]
})
```

Vì sao truy vấn này có thể phải hỏi mọi shard?

**Đáp án:** Nhánh đầu có full-key equality nhưng nhánh thứ hai có thể khớp đơn `pending` của **bất kỳ tenant nào trên bất kỳ shard nào**. Tổng thể `$or` phải tính cả nhánh đó.

### Bài 6. Tính tổng paid của tenant T01

Viết aggregation tổng số đơn paid và doanh thu paid cho T01 trên dữ liệu mẫu.

**Đáp án:**

```javascript
db.orders.aggregate([
  { $match: { tenantId: "T01", status: "paid" } },
  {
    $group: {
      _id: "$tenantId",
      count: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  }
])
```

Kết quả logic: `{_id:"T01", count:4, revenue:660}`. Vì chỉ ràng buộc prefix `tenantId` của shard key ghép, routing có thể liên quan một hoặc nhiều shard chứa T01.

### Bài 7. Vì sao `findOne({_id:...})` vẫn scatter?

Shard key là `{tenantId:1,orderId:1}`; `_id` có unique index. Ứng dụng:

```javascript
db.orders.findOne({ _id: "T01-104" })
```

Hỏi index `_id_` có bảo đảm mongos đi đúng một shard không?

**Đáp án:** Không. Index `_id_` giúp tìm **trong một shard** nhưng không cho router biết shard-key range. Nếu đã xác thực tenant T01 và biết orderId 104, thêm `tenantId` và `orderId` vào filter.

### Bài 8. Đọc hai chiều của explain

Kết quả đo giả định:

```text
Query A: 1 shard, 40.000 documents examined
Query B: 3 shards, tổng 30 documents examined
```

Query nào targeted hơn? Query nào chắc chắn nhanh hơn?

**Đáp án:** A targeted hơn vì chỉ một shard. Không thể khẳng định query nào nhanh hơn chỉ từ hai con số: A có thể thiếu index nội bộ; B có fan-out/network/merge nhưng đọc rất ít dữ liệu. Cần xem local plans, thời gian, cache và môi trường.

### Bài 9. Global sort và limit

Một truy vấn `status:"paid"` được gửi tới ba shard và cần 10 đơn mới nhất toàn hệ thống. Vì sao chỉ lấy 10 đơn mới nhất từ Shard A không đủ?

**Đáp án:** Shard B hoặc C có thể chứa đơn mới hơn đơn trên A. Router cần kết hợp kết quả từ các shard, thường bằng merge sort/top-K theo kế hoạch tối ưu. `limit(10)` không làm query tự target một shard.

### Bài 10. API biết tenant nhưng quên truyền vào filter

Endpoint xác thực thành công tenant T01, nhưng code truy vấn:

```javascript
db.orders.find({ orderId: 104 })
```

Có vấn đề nào ngoài hiệu năng?

**Đáp án:** Về hiệu năng, thiếu prefix shard key nên có thể scatter. Về nghiệp vụ/bảo mật, `orderId` có thể trùng giữa các tenant; nếu không lọc tenant, có nguy cơ trả dữ liệu ngoài phạm vi được phép. Cần dùng tenant context đã xác thực và bộ lọc phù hợp.

### Bài 11. Dữ liệu nhỏ và số shard tham gia

Bạn đã shard một collection lab chỉ có 15 document và chạy explain trên query `status:"paid"`. Explain chỉ cho thấy một shard tham gia. Có thể kết luận status được target theo shard key không?

**Đáp án:** Không. Collection có thể mới được shard nhưng mọi shard-key ranges liên quan vẫn ở một shard vì quá ít dữ liệu. Cần xem metadata/placement. Không tự suy rằng việc liên hệ một shard trong lab chứng minh predicate `status` đủ để target trong một cluster đã phân phối thật.

### Bài 12. Chọn hướng cải thiện báo cáo toàn hệ thống

Báo cáo tổng doanh thu paid của mọi tenant chạy theo giờ; shard key là `{tenantId:1,orderId:1}`. Có nên thêm `tenantId:"T01"` vào query để giảm số shard?

**Đáp án:** Không, vì nó sẽ làm sai yêu cầu “mọi tenant”. Thay vào đó, cân nhắc index local theo `status` và thời gian, lọc kỳ báo cáo, kiểm tra aggregation split/merge hoặc duy trì bảng tổng hợp riêng khi phù hợp.

## 22. Quy trình thực tế để tránh fan-out không cần thiết

Khi thiết kế hoặc tối ưu truy vấn trên sharded collection:

1. **Viết rõ câu hỏi nghiệp vụ**: một đơn, một tenant, một dải thời gian hay toàn bộ tenants?
2. **Xác nhận shard key thật**: field, thứ tự các field, ranged/hashed và type BSON.
3. **Đối chiếu filter với shard key**: có equality đầy đủ, prefix, range, `$in` hay thiếu shard-key condition?
4. **Xác nhận quyền tenant** trước khi đưa tenantId vào filter; không hi sinh an toàn dữ liệu để tối ưu.
5. **Chạy `explain` qua `mongos`**: xem một shard, subset hay nhiều shard; không đoán từ index.
6. **Xem từng local plan**: index phù hợp, số keys/docs examined, sort, covered query nếu có.
7. **Quan sát merge**: sorting, grouping, skip/limit và dữ liệu truyền giữa shards.
8. **Kiểm tra dữ liệu phân bố thật**: collection nhỏ chưa chắc đã phân ra nhiều shard; tenant lớn có thể trải rộng hơn dự kiến.
9. **Cân nhắc thay đổi query shape trước thay shard key**: bổ sung key đã biết, giữ kiểu đúng, tối ưu index và pagination.
10. **Đo với workload thực tế**: latency, fan-out, network, cache, balancing và độ lệch dữ liệu; một explain không thay thế monitoring dài hạn.

## Kết luận

Trong MongoDB sharding, **`mongos` định tuyến dựa trên shard key và metadata phân phối dữ liệu**, không phải dựa vào việc một field có index hay một ID “trông giống” tenant ID. Với **equality trên đầy đủ shard key**, truy vấn thường có thể đến đúng một shard; với **prefix/range**, router có thể thu hẹp vào một tập shard; còn truy vấn **thiếu điều kiện shard key** thường phải **scatter-gather**.

Tuy nhiên, một targeted query có thể chậm vì thiếu index trên shard, và scatter-gather có thể hợp lý cho báo cáo toàn hệ thống. Compound shard key, hashed shard key, `$or`, kiểu BSON và cách phân phối shard-key ranges đều có thể thay đổi khả năng định tuyến. Thực hành tốt là **đưa shard-key predicate hợp lệ vào những query thật sự biết key, kiểm tra bằng `explain`, rồi tối ưu công việc trên từng shard và bước merge** mà vẫn bảo toàn kết quả nghiệp vụ.

### Nguồn tham khảo chính thức

- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Manual — Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-shard-key/)
- [MongoDB Manual — Sharded Cluster Query Router](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Sharded Collection Operations](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/#query-routing)
